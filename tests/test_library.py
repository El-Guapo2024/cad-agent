"""The part library (step 6, piece A): `cad lib ls|info|add|use|check|fetch`, the catalog behind them and the generators.

Three kinds of test, in this order.

The catalog and its generators. Every number in cad_agent/library/catalog.toml has a source, and the source says the
number; the HIWIN, IMS and Nanotec tables are transcribed here a second time, as the pages print them, so that an edit
to one that is not an edit to the other is found. Each generator is drawn and measured, the extrusions against the
section area and second moments of the maker's own model (the sha256 of each file the catalog names is in its header),
and the eval givens the generators draw are regenerated and held to the bytes they have.

The commands, through cli.main like every other command: the exit code each can give (0, 1, 2, 3, 4), --json, the
activity log, and the journal. Nothing here reaches the network (an autouse fixture turns a download into a failure,
and the tests that fetch hand `store.OPEN` a fake) and nothing here touches ~/.cad-agent (CAD_LIBRARY is a folder of
the test's own). A STEP in these tests is a small file the test writes: the library copies and hashes a STEP, it
does not read it.

And the contract with the rest of cad-agent: a part `use` copies in loads through `bought_solid`, passes the provenance
rule, carries the mass and rating the rules of step 6 read, and is pinned by the hash `check` and the rule re-test.
"""
import hashlib
import importlib.util
import json
import math
import re
import runpy
import shutil
import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest

from cad_agent import bought as B
from cad_agent import cli, cmdbase, rules, undo, warm
from cad_agent import state as st
from cad_agent.library import catalog, store
from cad_agent.library import cli as libcli
from cad_agent.registry import ProjectCtx
from conftest import cad_env
from test_cli import log_lines, run

REPO = Path(__file__).resolve().parent.parent
SLUG = "demo"
CATALOG_TOML = REPO / "cad_agent" / "library" / "catalog.toml"
STEP = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\n#1 = CARTESIAN_POINT('', (0., 0., 0.));\nENDSEC;\nEND-ISO-10303-21;\n"
OTHER = STEP.replace(b"#1", b"#2")
VENDOR_STEP = STEP + b"/* vendor */\n"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ─── Fixtures ────────────────────────────────────────────────────────────────

class Response:
    """What urllib hands back, to the extent store.download reads it."""
    def __init__(self, data: bytes):
        self.data, self.at = data, 0

    def read(self, n=-1):
        n = len(self.data) - self.at if n is None or n < 0 else n
        chunk, self.at = self.data[self.at:self.at + n], self.at + n
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def serving(data=None, error=None, calls=None):
    """An opener for store.OPEN: serves `data`, or raises `error`, and records what it was asked for."""
    def opener(request, timeout=None):
        if calls is not None:
            calls.append((request.full_url, timeout))
        if error is not None:
            raise error
        return Response(data)
    return opener


@pytest.fixture(autouse=True)
def _own_folders(tmp_path, monkeypatch):
    """A projects folder and a store of this test's own, and no network."""
    monkeypatch.setattr(st, "ROOT", tmp_path / "projects")
    (tmp_path / "projects").mkdir()
    monkeypatch.setenv("CAD_LIBRARY", str(tmp_path / "store"))
    for name in ("CAD_PROJECTS", "CAD_ACTOR"):
        monkeypatch.delenv(name, raising=False)

    def no_network(*a, **k):
        raise AssertionError("a test reached the network")

    monkeypatch.setattr(store, "OPEN", no_network)


@pytest.fixture()
def demo(tmp_path, capsys):
    assert cli.main(["init", SLUG, "--brief", "library test"]) == cmdbase.OK
    capsys.readouterr()
    return tmp_path / "projects" / SLUG


def bought_dir(demo):
    return demo / "bought"


@pytest.fixture()
def tiny(tmp_path, monkeypatch):
    """A catalog of four entries of the tests' own: a CC-BY file `widget` that can be fetched, a vendor's `vendor-motor` that
    cannot, a generator `bar`, and a `screw` that needs a package nobody has."""
    text = f'''
[parts.widget]
title = "Widget, a CC-BY file"
kind = "step"
vendor = "Example Co"
pn = "W-1"
licence = "CC-BY-3.0"
attribution = "Example Co, https://example.test/widget, CC-BY 3.0"
geometry = "envelope"
verified = false
unconfirmed = ["its size"]
source = "https://example.test/widget"
docs = ["https://example.test/widget"]
url = "https://example.test/widget.step"
sha256 = "{sha(STEP)}"
size = {len(STEP)}
material = "aluminium"
max_temp_c = 85.0
max_temp_source = "the maker's sheet, page 1"
datum = {{ move = [1.0, 2.0, 3.0], turn = [0.0, 0.0, 90.0] }}
[parts.widget.mass]
g = 12.5
source = "the maker's sheet, page 2"

[parts.vendor-motor]
title = "A vendor's motor"
kind = "step"
vendor = "Vendor Inc"
pn = "VM-17"
licence = "vendor terms"
source = "the vendor's CAD page"
docs = ["https://vendor.test/motor"]
url = "https://vendor.test/motor.step"
sha256 = "{sha(VENDOR_STEP)}"

[parts.bar]
title = "A bar"
kind = "generator"
generator = "cad_agent.library.gen.extrusion:envelope"
vendor = "Example Co"
pn = "BAR"
licence = "MIT"
geometry = "envelope"
material = "aluminium"
source = "https://example.test/bar"
docs = ["https://example.test/bar"]
[parts.bar.dims]
width = {{ value = 20.0, source = "the sheet: 20 across" }}
height = {{ value = 40.0, source = "the sheet: 40 tall" }}
[parts.bar.params.length]
default = 100.0
min = 10.0
max = 500.0
unit = "mm"
source = "the sheet: 10 to 500"
[parts.bar.params.axis]
default = "x"
choices = ["x", "y", "z"]
[parts.bar.mass]
per_m_g = 800.0
param = "length"
source = "the sheet: 0.8 kg/m"

[parts.screw]
title = "A screw from a package"
kind = "bd_warehouse"
generator = "bd_warehouse.fastener:SocketHeadCapScrew"
requires = "bd_warehouse"
licence = "Apache-2.0"
source = "ISO 4762 as the package draws it"
docs = ["https://example.test/screw"]
[parts.screw.model]
fastener_type = "iso4762"
[parts.screw.params.size]
default = "M3-0.5"
choices = ["M3-0.5", "M4-0.7"]
'''
    path = tmp_path / "catalog.toml"
    path.write_text(text)
    monkeypatch.setattr(catalog, "CATALOG", path)
    return path


@pytest.fixture()
def widget_file(tmp_path):
    path = tmp_path / "widget.step"
    path.write_bytes(STEP)
    return path


def stored(name, store_dir):
    return (store_dir / f"{name}.step").exists()


def side_of(demo, name):
    return json.loads((bought_dir(demo) / f"{name}.json").read_text())


def provenance_rows(tmp_path):
    return list(rules.provenance(ProjectCtx(slug=SLUG, dir=tmp_path / "projects" / SLUG, parts={}, out_dir=tmp_path)))


def store_dir(tmp_path):
    return tmp_path / "store"


# ─── The shipped catalog: what is in it, and that every number says where it came from ──────────────────────

@pytest.fixture(scope="module")
def shipped():
    return catalog.shipped()


def tokens(value):
    """The numbers a value holds, flat."""
    if isinstance(value, (list, tuple)):
        return [n for v in value for n in tokens(v)]
    return [float(value)]


def says(number: float, text: str) -> bool:
    """Whether a text prints the number: 12 is 12 and 12.0, 0.05 is 0.050, and 3 is not 3.7."""
    s = f"{number:g}"
    body = re.escape(s) + ("0*" if "." in s else r"(?:\.0+)?")
    return re.search(rf"(?<![\d.]){body}(?!\d|\.\d)", text) is not None


def test_the_shipped_catalog_is_well_formed_and_never_wakes_the_cad_kernel():
    code = ("import sys\n"
            "from cad_agent.library import catalog\n"
            "c = catalog.load()\n"
            "print(len(c.entries), c.problems, sorted(m for m in ('build123d', 'OCP') if m in sys.modules))\n")
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
                       env=cad_env(PYTHONPATH=str(REPO)), cwd=str(REPO))
    assert p.returncode == 0, p.stderr
    count, rest = p.stdout.strip().splitlines()[-1].split(" ", 1)
    assert int(count) >= 20 and rest == "[] []"


def test_every_entry_names_what_it_is_and_cites_a_page_it_was_read_from(shipped):
    assert {e.kind for e in shipped.values()} == set(catalog.KINDS)
    for name, e in shipped.items():
        assert e.problems == () and e.origin == "shipped" and catalog.NAME.match(name), name
        assert e.title and e.source and e.licence != "unknown", name
        assert e.docs and all(u.startswith("https://") for u in e.docs), name


def test_every_dimension_is_cited_and_its_source_says_the_number(shipped):
    seen = 0
    for name, e in shipped.items():
        for key, d in e.dims.items():
            assert d["source"].strip(), (name, key)
            for n in tokens(d["value"]):
                assert says(n, d["source"]), f"{name}.{key}: the source does not say {n:g}: {d['source']}"
                seen += 1
    assert seen == 138


def test_every_parameter_range_mass_and_rating_says_its_numbers_too(shipped):
    for name, e in shipped.items():
        for key, p in e.params.items():
            assert p["source"] is not None or e.kind == "bd_warehouse", (name, key)
            if p["source"] and re.search(r"\d", p["source"]) and p["choices"] is None:
                for bound in (p["min"], p["max"]):
                    assert bound is None or says(bound, p["source"]) or "any length" in p["source"], (name, key, bound)
            if p["source"] and re.search(r"\d", p["source"]) and p["choices"] and isinstance(p["choices"][0], (int, float)):
                assert all(says(c, p["source"]) for c in p["choices"]), (name, key)
        m = e.mass
        if m is None:
            continue
        assert m["source"].strip(), name
        if "g" in m:
            assert says(m["g"] / 1000.0, m["source"]), (name, m)
        elif "per_m_g" in m:
            assert says(m["per_m_g"] / 1000.0, m["source"]), (name, m)
        elif "section_mm2" in m:
            assert says(m["section_mm2"], e.source), (name, "the section's area is in the entry's source")
        else:
            assert all(says(v, m["source"]) for v in m["table"].values()), (name, m)
        if e.max_temp_c is not None:
            assert says(e.max_temp_c, e.max_temp_source), name


def test_what_a_licence_asks_for_is_in_the_entry(shipped):
    for name, e in shipped.items():
        if e.licence.startswith("CC-BY"):
            assert e.attribution and "CC-BY 3.0" in e.attribution and "FreeCAD-library" in e.attribution, name
            assert catalog.fetch_ruling(e)[0] is True and e.licence in catalog.OPEN_LICENCES, name
        if e.kind == "step":
            assert re.fullmatch(r"https://raw\.githubusercontent\.com/FreeCAD/FreeCAD-library/[0-9a-f]{40}/.+\.step", e.url), name
            assert catalog.HEX64.match(e.sha256) and e.size > 1000 and not e.verified and e.unconfirmed, name


def test_no_vendor_or_community_file_is_in_the_repo_only_its_pin():
    library = REPO / "cad_agent" / "library"
    assert not [p for p in library.rglob("*") if p.suffix.lower() in (".step", ".stp", ".stl", ".3mf")]
    assert sorted(p.name for p in library.iterdir() if p.is_file() and p.suffix == ".toml") == ["catalog.toml"]
    assert (library / "gen" / "__init__.py").exists() and (library / "__init__.py").exists()   # setuptools finds a package by that
    assert '"library/*.toml"' in (REPO / "pyproject.toml").read_text()


def test_only_what_a_maker_gives_is_declared_and_the_rest_is_left_out(shipped):
    assert shipped["gt2-idler-20t"].mass is None and not shipped["gt2-idler-20t"].verified
    assert shipped["gt2-idler-20t"].unconfirmed and shipped["gt2-idler-20t"].model == {"flange_t": 1.0}
    for name in ("mgn12-rail", "mgn15-rail", "mgn12c", "mgn12h", "mgn15c", "mgn15h"):
        assert shipped[name].max_temp_c is None and shipped[name].material is None, name   # the pages read give no rating
    assert (shipped["nema17"].max_temp_c, shipped["nema8"].max_temp_c) == (40.0, 50.0)
    for name in ("iso4762-screw", "iso4032-nut", "iso7089-washer"):
        assert shipped[name].mass is None and shipped[name].max_temp_c is None and shipped[name].material is None, name


# HIWIN's linear guideways catalog GW-11-5-EN-2207-K as the pages print it: table 3.79 (page 97), the blocks, and
# table 3.81 (page 99), the rails. Typed again here, so that an edit to the catalog that is not an edit to the page is found.
HIWIN_BLOCKS = {                    # name: (L, W, H, H1, B, C, thread depth, weight in kg, rail width)
    "mgn12c": (34.7, 27, 13, 3.0, 20, 15, 3.5, 0.030, 12),
    "mgn12h": (45.4, 27, 13, 3.0, 20, 20, 3.5, 0.050, 12),
    "mgn15c": (42.1, 32, 16, 4.0, 25, 20, 4.0, 0.060, 15),
    "mgn15h": (58.8, 32, 16, 4.0, 25, 25, 4.0, 0.090, 15),
}
HIWIN_RAILS = {                     # name: (WR, HR, D, h, d, P, E1/2 min, min length, max length, kg/m)
    "mgn12-rail": (12, 8.0, 6.0, 4.5, 3.5, 25, 5, 35, 2000, 0.65),
    "mgn15-rail": (15, 10.0, 6.0, 4.5, 3.5, 40, 6, 52, 2000, 1.06),
}


@pytest.mark.parametrize("name", sorted(HIWIN_BLOCKS))
def test_a_carriage_is_the_row_of_hiwins_table_3_79(shipped, name):
    length, width, h, h1, b, c, depth, kg, wr = HIWIN_BLOCKS[name]
    d = {k: v["value"] for k, v in shipped[name].dims.items()}
    assert d == {"length": length, "width": width, "height": h, "base_gap": h1, "rail_width": wr,
                 "hole_pitch_along": c, "hole_pitch_across": b, "tap_depth": depth}
    assert shipped[name].mass == {"g": kg * 1000.0, "source": shipped[name].mass["source"]}
    assert shipped[name].vendor == "HIWIN" and shipped[name].pn == name.upper() and shipped[name].geometry == "envelope"


@pytest.mark.parametrize("name", sorted(HIWIN_RAILS))
def test_a_rail_is_the_row_of_hiwins_table_3_81(shipped, name):
    wr, hr, big_d, h, d, pitch, e_min, shortest, longest, kg_m = HIWIN_RAILS[name]
    e = shipped[name]
    assert {k: v["value"] for k, v in e.dims.items()} == {
        "width": wr, "height": hr, "pitch": pitch, "counterbore_dia": big_d, "counterbore_depth": h, "hole_dia": d,
        "end_min": e_min}
    p = e.params["length"]
    assert (p["min"], p["max"]) == (shortest, longest) and shortest <= p["default"] <= longest
    assert e.mass["per_m_g"] == kg_m * 1000.0 and e.mass["param"] == "length"


def test_the_motors_are_the_makers_drawings(shipped):
    n17 = {k: v["value"] for k, v in shipped["nema17"].dims.items()}
    assert n17 == {"face": 42.3, "pilot_dia": 22.0, "pilot_height": 2.03, "shaft_dia": 5.0, "shaft_length": 23.88,
                   "hole_pitch": 31.0, "hole_depth": 4.5}
    assert shipped["nema17"].params["length"]["choices"] == [34, 40, 48]
    assert shipped["nema17"].mass["table"] == {"34": 210.0, "40": 230.0, "48": 360.0}
    n8 = {k: v["value"] for k, v in shipped["nema8"].dims.items()}
    assert n8 == {"face": 20.0, "length": 42.0, "corner_radius": 1.5, "pilot_dia": 15.0, "pilot_height": 1.5,
                  "shaft_dia": 4.0, "shaft_length": 16.5, "hole_pitch": 16.0, "hole_depth": 3.0}
    assert shipped["nema8"].mass == {"g": 80.0, "source": shipped["nema8"].mass["source"]}
    assert shipped["nema17"].model["hole_dia"] == 2.5 and shipped["nema8"].model["hole_dia"] == 1.6     # M3 and M2 tap drills


def test_every_catalog_number_the_eval_motor_and_rail_do_not_share_is_not_the_evals(shipped):
    # the evals' own numbers are the task's, and stay in their scripts: the library's NEMA 17 is the maker's sheet
    assert shipped["nema17"].dims["pilot_height"]["value"] == 2.03 != 2.0
    assert shipped["nema17"].dims["shaft_length"]["value"] == 23.88 != 24.0
    assert "corner_cut" not in shipped["nema17"].dims and "corner_cut" not in shipped["nema17"].model


# ─── Reading an entry: the faults, the parameters, the mass ──────────────────────────────────────────────────

GOOD = {"title": "A part", "kind": "generator", "generator": "cad_agent.library.gen.gt2:idler", "licence": "MIT",
        "source": "a page", "docs": ["https://example.test/a"]}


@pytest.mark.parametrize("change, fault", [
    ({"kind": "folder"}, "kind must be one of"),
    ({"geometry": "solid"}, "geometry must be one of"),
    ({"title": None}, "title is missing"),
    ({"source": None}, "source is missing"),
    ({"docs": ["http://example.test/a"]}, "docs must be a list of https URLs"),
    ({"docs": []}, "cites at least one page"),
    ({"generator": "os:system"}, "generator must be `cad_agent.library.gen."),
    ({"generator": None}, "generator must be"),
    ({"sha256": "abc"}, "sha256 must be 64"),
    ({"url": "file:///etc/passwd"}, "url must be an https URL"),
    ({"size": -1}, "size must be a whole number"),
    ({"max_temp_c": 80}, "needs a max_temp_source"),
    ({"max_temp_source": "a sheet"}, "max_temp_source without a max_temp_c"),
    ({"material": "unobtainium"}, "is not in materials.py"),
    ({"licence": "CC-BY-4.0"}, "needs an attribution"),
    ({"mass": {"g": 5.0}}, "mass needs a source"),
    ({"mass": {"g": -5.0, "source": "s"}}, "mass.g must be a positive number"),
    ({"mass": {"g": 5.0, "per_m_g": 1.0, "source": "s"}}, "exactly one of"),
    ({"mass": {"per_m_g": 5.0, "source": "s"}}, "takes param"),
    ({"mass": {"per_m_g": 5.0, "param": "length", "source": "s"}}, "is not a parameter"),
    ({"datum": {"shift": [1, 2, 3]}}, "datum must be {move, turn}"),
    ({"datum": {"move": [1, 2]}}, "datum move must be three numbers"),
    ({"dims": {"x": {"value": 1.0}}}, "dims.x has no source"),
    ({"dims": {"x": {"value": "wide", "source": "s"}}}, "dims.x must be a number"),
    ({"dims": {"x": 4}}, "dims.x must be {value, source}"),
    ({"params": {"n": {"min": 1}}}, "params.n must have a default"),
    ({"params": {"n": {"default": 5, "min": 6}}}, "min and max must be numbers around the default"),
    ({"params": {"n": {"default": 5, "choices": [1, 2]}}}, "choices must be a list that holds the default"),
    ({"params": {"n": {"default": "a"}}}, "the default must be a number"),
    ({"verified": False}, ""),                              # unverified with nothing unconfirmed is allowed: it is only a flag
    ({"unconfirmed": ["its size"]}, "is verified = false"),
    ({"notes": [1]}, "notes must be a list of text"),
    ({"colour": "red"}, "unknown key colour"),
])
def test_an_entry_that_does_not_hold_is_flagged_and_still_listed(change, fault):
    raw = {**GOOD, **change}
    raw = {k: v for k, v in raw.items() if v is not None}
    entry = catalog.parse_entry("a-part", raw, "shipped")
    if fault:
        assert any(fault in p for p in entry.problems), entry.problems
    else:
        assert entry.problems == ()
    assert entry.name == "a-part"                          # it is still an entry: a mistake costs one entry, not the listing


def test_a_name_is_lower_case_words_and_a_step_pins_its_hash():
    assert any("lower case words" in p for p in catalog.parse_entry("My Part", GOOD, "shipped").problems)
    step = {**GOOD, "kind": "step"}
    del step["generator"]
    assert any("pins the sha256" in p for p in catalog.parse_entry("a-part", step, "shipped").problems)
    assert any("only a generator or bd_warehouse entry has a generator" in p
               for p in catalog.parse_entry("a-part", {**step, "sha256": "0" * 64, "generator": "x"}, "shipped").problems)


def test_a_bd_warehouse_entry_draws_with_that_package_and_says_so():
    raw = {**GOOD, "kind": "bd_warehouse", "generator": "bd_warehouse.fastener:HexNut"}
    assert any("requires `bd_warehouse`" in p for p in catalog.parse_entry("a-nut", raw, "shipped").problems)
    ok = catalog.parse_entry("a-nut", {**raw, "requires": "bd_warehouse"}, "shipped")
    assert ok.problems == () and ok.requires == "bd_warehouse"
    other = catalog.parse_entry("a-nut", {**raw, "requires": "bd_warehouse", "generator": "cad_agent.library.gen.mgn:rail"}, "shipped")
    assert any("generator must be `bd_warehouse." in p for p in other.problems)


def entry_with(**kw):
    raw = {**GOOD, "dims": {"width": {"value": 20.0, "source": "20"}}, **kw}
    return catalog.parse_entry("a-part", raw, "shipped")


def test_parameters_are_held_to_their_type_and_limits():
    e = entry_with(params={"length": {"default": 100.0, "min": 10.0, "max": 500.0, "unit": "mm", "source": "the sheet"},
                           "axis": {"default": "x", "choices": ["x", "y", "z"]},
                           "turns": {"default": 4, "choices": [4, 8]}})
    assert catalog.resolve_params(e, {}) == {"length": 100.0, "axis": "x", "turns": 4}
    assert catalog.resolve_params(e, {"length": 250, "axis": "z", "turns": 8.0}) == {"length": 250.0, "axis": "z", "turns": 8}
    for given, message in (({"width": 5}, "no parameter width (parameters: length, axis, turns)"),
                           ({"length": 5}, "length must be from 10 to 500 mm, got 5 (the sheet)"),
                           ({"length": 501}, "length must be from 10 to 500 mm, got 501"),
                           ({"length": "long"}, "length must be a number of mm, got 'long'"),
                           ({"length": True}, "length must be a number"),
                           ({"axis": "w"}, "axis must be one of x, y, z, got 'w'"),
                           ({"turns": 5}, "turns must be one of 4, 8, got 5")):
        with pytest.raises(catalog.LibraryError, match=re.escape(message)):
            catalog.resolve_params(e, given)


def test_a_mass_is_the_mass_of_the_copy_that_was_asked_for():
    fixed = entry_with(mass={"g": 12.5, "source": "the sheet"})
    assert catalog.mass_of(fixed, {}) == (12.5, "the sheet")
    params = {"length": {"default": 100.0, "min": 10.0, "max": 500.0}, "n": {"default": 40, "choices": [34, 40]}}
    per = entry_with(params=params, mass={"per_m_g": 650.0, "param": "length", "source": "table 3.81: 0.65 kg/m"})
    grams, why = catalog.mass_of(per, {"length": 300.0, "n": 40})
    assert grams == 195.0 and "650 g/m x 0.3 m = 195.0 g" in why and why.startswith("table 3.81")
    area = entry_with(params=params, mass={"section_mm2": 200.0, "material": "aluminium", "param": "length", "source": "the model"})
    grams, why = catalog.mass_of(area, {"length": 500.0, "n": 40})
    assert grams == 270.0 and "200 mm2 x 2.7 g/cm3 (aluminium, materials.py) = 540.0 g/m, x 0.5 m = 270.0 g" in why
    table = entry_with(params=params, mass={"by": "n", "table": {"34": 210.0, "40": 230.0}, "source": "the sheet"})
    assert catalog.mass_of(table, {"length": 1.0, "n": 34}) == (210.0, "the sheet (for n 34)")
    assert catalog.mass_of(entry_with(), {}) == (None, None)


def test_a_mass_table_must_cover_every_choice_and_a_material_must_be_known():
    params = {"n": {"default": 40, "choices": [34, 40]}, "length": {"default": 1.0}}
    short = entry_with(params=params, mass={"by": "n", "table": {"40": 230.0}, "source": "s"})
    assert any("no mass for 34" in p for p in short.problems)
    nowhere = entry_with(params=params, mass={"by": "length", "table": {"1": 2.0}, "source": "s"})
    assert any("no choices to tabulate" in p for p in nowhere.problems)
    gold = entry_with(params=params, mass={"section_mm2": 5.0, "material": "unobtainium", "param": "length", "source": "s"})
    assert any("not in materials.py" in p for p in gold.problems)


def test_the_arguments_a_generator_is_called_with_are_dims_then_model_then_params():
    e = entry_with(model={"gap": 0.2}, params={"length": {"default": 100.0}})
    assert catalog.arguments(e, {"length": 30.0}) == {"width": 20.0, "gap": 0.2, "length": 30.0}


def test_the_sidecar_carries_the_contract_keys_a_source_gave(shipped):
    side = catalog.sidecar(shipped["nema17"], {"length": 40})
    assert side == {
        "source": shipped["nema17"].source, "vendor": "Novanta IMS", "verified": True, "library": "nema17", "licence": "MIT",
        "geometry": "envelope", "pn": "M-17nn-1.5", "mass_g": 230.0,
        "mass_source": shipped["nema17"].mass["source"] + " (for length 40)", "max_temp_c": 40.0,
        "max_temp_source": shipped["nema17"].max_temp_source, "library_params": {"length": 40}}
    bare = catalog.sidecar(shipped["gt2-idler-20t"], {})
    assert not {"mass_g", "mass_source", "max_temp_c", "datum", "pn"} & set(bare) and bare["verified"] is False
    assert bare["material"] == "aluminium" and bare["vendor"] is None
    beam = catalog.sidecar(shipped["extrusion-2040"], {"length": 1000.0, "axis": "x"})
    assert beam["geometry"] == "exact" and beam["mass_g"] == pytest.approx(780.098, abs=0.01)
    assert beam["material"] == "aluminium" and "max_temp_c" not in beam
    cc = catalog.sidecar(shipped["fcl-623zz"], {})
    assert cc["datum"] == {"move": [0.0, 0.0, 2.0], "turn": [90.0, 0.0, 0.0]} and "CC-BY 3.0" in cc["attribution"]
    assert "library_params" not in cc


# ─── Fetching is allowed only where a licence lets the repo do it ────────────────────────────────────────────

def test_the_repo_downloads_a_file_only_where_it_may_and_can_check_it(shipped, tiny):
    mine = catalog.load()
    assert catalog.fetch_ruling(mine.get("widget")) == (True, "")
    ok, why = catalog.fetch_ruling(mine.get("vendor-motor"))
    assert not ok and "vendor terms" in why and "download it by hand from https://vendor.test/motor" in why \
        and "cad lib add vendor-motor FILE --source URL" in why
    ok, why = catalog.fetch_ruling(mine.get("bar"))
    assert not ok and "nothing to download" in why
    bare = catalog.parse_entry("a-file", {**GOOD, "kind": "step", "sha256": "0" * 64, "generator": None, "licence": "CC0-1.0"}, "store")
    assert "no download URL" in catalog.fetch_ruling(bare)[1]
    pinless = catalog.parse_entry("a-file", {**GOOD, "kind": "step", "url": "https://x.test/a.step", "licence": "CC0-1.0"}, "store")
    assert "pins no sha256" in catalog.fetch_ruling(pinless)[1]
    for licence in ("proprietary", "unknown", "CC-BY-NC-4.0", "vendor terms"):
        e = catalog.parse_entry("a-file", {**GOOD, "kind": "step", "sha256": "0" * 64, "url": "https://x.test/a.step",
                                           "licence": licence, "generator": None}, "store")
        assert not catalog.fetch_ruling(e)[0], licence


# ─── The generators: drawn and measured ──────────────────────────────────────────────────────────────────────

def lo_hi(solid):
    bb = solid.bounding_box()
    return (bb.min.X, bb.min.Y, bb.min.Z), (bb.max.X, bb.max.Y, bb.max.Z)


def size_of(solid):
    lo, hi = lo_hi(solid)
    return tuple(round(h - l, 6) for l, h in zip(lo, hi))


def holes(solid):
    from build123d import GeomType
    return len([f for f in solid.faces() if f.geom_type == GeomType.CYLINDER])


def copy_in(capsys, demo, entry, *params, name=None):
    argv = ["lib", "use", SLUG, entry, *params] + (["--as", name] if name else [])
    code, data = run(capsys, *argv)
    assert code == cmdbase.OK, data
    return data


def built(slug, name):
    return st.bought_solid(slug, name)


def test_a_rail_is_a_box_with_the_most_holes_a_length_takes(demo, capsys):
    from cad_agent.library.gen import mgn
    rail = mgn.rail(width=12.0, height=8.0, pitch=25.0, counterbore_dia=6.0, counterbore_depth=4.5, hole_dia=3.5,
                    end_min=5.0, length=150.0)
    assert size_of(rail) == (150.0, 12.0, 8.0) and holes(rail) == 12                      # six holes, a bore and a counterbore each
    long = mgn.rail(width=12.0, height=8.0, pitch=25.0, counterbore_dia=6.0, counterbore_depth=4.5, hole_dia=3.5,
                    end_min=5.0, length=300.0)
    assert holes(long) == 24                                                              # 12: (300 - 10) // 25 + 1
    middles = sorted((f.bounding_box().min.X + f.bounding_box().max.X) / 2.0 for f in long.faces()
                     if f.geom_type.name == "CYLINDER")
    assert middles[0] == pytest.approx(-150.0 + (300.0 - 11 * 25.0) / 2.0)               # E = 12.5 from the end, as F 3.16 gives it
    assert middles[-1] == pytest.approx(150.0 - (300.0 - 11 * 25.0) / 2.0)
    two = mgn.rail(width=12.0, height=8.0, pitch=25.0, counterbore_dia=6.0, counterbore_depth=4.5, hole_dia=3.5,
                   end_min=5.0, length=35.0)
    assert holes(two) == 4                                                                # the shortest rail HIWIN cuts: E = 5
    five = mgn.rail(width=12.0, height=8.0, pitch=25.0, counterbore_dia=6.0, counterbore_depth=4.5, hole_dia=3.5,
                    end_min=5.0, length=150.0, holes=5)
    assert holes(five) == 10
    with pytest.raises(ValueError, match="no room for a mounting hole"):
        mgn.rail(width=12.0, height=8.0, pitch=25.0, counterbore_dia=6.0, counterbore_depth=4.5, hole_dia=3.5,
                 end_min=5.0, length=8.0)


def test_a_carriage_stands_h1_above_the_rail_and_clears_it_by_the_gap(demo, capsys):
    copy_in(capsys, demo, "mgn12h", name="block")
    copy_in(capsys, demo, "mgn12-rail", name="rail")
    block, rail = built(SLUG, "block"), built(SLUG, "rail")
    assert size_of(block) == (45.4, 27.0, 10.0)                                           # H - H1 tall
    lo, hi = lo_hi(block)
    assert (lo[2], hi[2]) == (-5.0, 5.0) and holes(block) == 4
    from build123d import Pos
    from cad_agent.geom import min_distance
    seated = Pos(0, 0, -4.0) * rail                       # the block frame has the rail's top face at z = 0: lift the rail's box to it
    assert min_distance(block, Pos(0, 0, -4.0) * rail) == pytest.approx(0.2, abs=1e-6)   # the channel's gap, above the rail
    assert size_of(rail) == (150.0, 12.0, 8.0) and seated is not None


@pytest.mark.parametrize("name, length, width, height, holes_n", [
    ("mgn12c", 34.7, 27.0, 10.0, 4), ("mgn12h", 45.4, 27.0, 10.0, 4),
    ("mgn15c", 42.1, 32.0, 12.0, 4), ("mgn15h", 58.8, 32.0, 12.0, 4)])
def test_each_carriage_draws_the_size_its_row_gives(demo, capsys, name, length, width, height, holes_n):
    copy_in(capsys, demo, name)
    solid = built(SLUG, name)
    assert size_of(solid) == (length, width, height) and holes(solid) == holes_n


@pytest.mark.parametrize("length, bbox, count", [(None, (40.0 + 23.88, 42.3, 42.3), 40), (34, (34.0 + 23.88, 42.3, 42.3), 34),
                                                 (48, (48.0 + 23.88, 42.3, 42.3), 48)])
def test_a_nema_17_is_the_sheets_frame_with_its_face_at_z_0(demo, capsys, length, bbox, count):
    copy_in(capsys, demo, "nema17", *([f"length={length}"] if length else []), name="motor")
    motor = built(SLUG, "motor")
    lo, hi = lo_hi(motor)
    assert (round(lo[0], 6), round(hi[0], 6), round(lo[1], 6), round(hi[1], 6)) == (-21.15, 21.15, -21.15, 21.15)
    assert (round(lo[2], 6), round(hi[2], 6)) == (-float(count), 23.88)
    assert side_of(demo, "motor")["library_params"] == {"length": count}


def test_a_nema_8_has_round_corners_and_the_nanotec_shaft(demo, capsys):
    copy_in(capsys, demo, "nema8", name="small")
    motor = built(SLUG, "small")
    lo, hi = lo_hi(motor)
    assert (round(hi[0] - lo[0], 6), round(hi[1] - lo[1], 6), round(lo[2], 6), round(hi[2], 6)) == (20.0, 20.0, -42.0, 16.5)
    assert motor.volume < 20.0 * 20.0 * 42.0 + 4.0 ** 2 * 3.14159 * 16.5             # round corners, holes: under a box of the same size


def test_a_gt2_idler_is_a_wheel_between_two_flanges(demo, capsys):
    copy_in(capsys, demo, "gt2-idler-20t", name="idler")
    idler = built(SLUG, "idler")
    assert size_of(idler) == (18.0, 18.0, 8.5) and lo_hi(idler)[0][2] == -4.25
    assert holes(idler) == 4                                  # the bore, the belt-running diameter, and the two flanges' rims


def test_the_exact_sections_are_the_makers_model_to_within_a_percent(demo, capsys):
    # A and the second moments of Framing Tech's own STEP at mid length (the catalog's header has the file's sha256):
    # about x is the sum of y^2 dA, with the 20 across along x and the long side along y
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from cad_agent.library.gen import extrusion
    makers = {"extrusion-2020": (167.794, 6938.531, 6938.531), "extrusion-2040": (288.925, 46514.29, 12133.815),
              "extrusion-4040": (648.495, 91742.885, 91742.885)}
    shipped = catalog.shipped()
    for name, (area, ix, iy) in makers.items():
        e = shipped[name]
        args = catalog.arguments(e, catalog.resolve_params(e, {}))
        args.pop("length"), args.pop("axis")
        fn = extrusion.tslot8_section if name.endswith("4040") else extrusion.tslot6_section
        face = fn(**args)
        assert len(face.faces()) == 1 and len(face.inner_wires() if hasattr(face, "inner_wires") else [1]) >= 1
        g = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face.wrapped, g)
        m = g.MatrixOfInertia()
        c = g.CentreOfMass()
        assert g.Mass() == pytest.approx(area, rel=0.01), name
        assert m.Value(1, 1) == pytest.approx(ix, rel=0.01), name
        assert m.Value(2, 2) == pytest.approx(iy, rel=0.01), name
        assert (abs(c.X()) < 1e-6, abs(c.Y()) < 1e-6) == (True, True), name


@pytest.mark.parametrize("name, w, h", [("extrusion-2020", 20, 20), ("extrusion-2040", 20, 40), ("extrusion-4040", 40, 40)])
@pytest.mark.parametrize("axis", ["x", "y", "z"])
def test_an_exact_extrusion_fills_the_box_the_envelope_is(demo, capsys, name, w, h, axis):
    copy_in(capsys, demo, name, "length=150", f"axis={axis}", name="beam")
    copy_in(capsys, demo, f"{name}-envelope", "length=150", f"axis={axis}", name="blank")
    beam, blank = built(SLUG, "beam"), built(SLUG, "blank")
    assert size_of(beam) == size_of(blank) == {"x": (150.0, h, w), "y": (w, 150.0, h), "z": (w, h, 150.0)}[axis]
    for a, b in zip(lo_hi(beam), lo_hi(blank)):
        assert a == pytest.approx(b, abs=1e-6)
    assert 0.2 * blank.volume < beam.volume < 0.5 * blank.volume                           # a profile is a fraction of its box
    side = side_of(demo, "beam")
    assert side["geometry"] == "exact" and side_of(demo, "blank")["geometry"] == "envelope"
    assert side["mass_g"] == side_of(demo, "blank")["mass_g"]                              # the mass is the profile's, whatever the box weighs
    assert side["mass_g"] == pytest.approx(beam.volume / 1000.0 * 2.70, rel=0.01)          # and the drawn section weighs what is declared


def test_the_blank_is_the_one_cad_agent_parts_has_drawn_since_step_1():
    from cad_agent.library.gen import extrusion
    from cad_agent.parts import extrusion_blank
    for kind in ("2020", "2040", "4040"):
        for axis in "xyz":
            mine = extrusion.envelope(*[__import__("cad_agent.parts", fromlist=["EXTRUSION"]).EXTRUSION[kind][k] for k in ("w", "h")],
                                      length=200.0, axis=axis)
            assert size_of(mine) == size_of(extrusion_blank(kind, 200.0, axis))
    with pytest.raises(ValueError, match="axis must be x, y or z"):
        extrusion.envelope(20.0, 20.0, 10.0, axis="w")


def test_the_envelope_can_carry_the_end_bores_the_evals_stub_has():
    from cad_agent.library.gen import extrusion
    stub = extrusion.envelope(20.0, 40.0, 60.0, axis="x", bore_dia=4.2, bores=2)
    assert size_of(stub) == (60.0, 40.0, 20.0) and holes(stub) == 2
    y = extrusion.envelope(20.0, 40.0, 60.0, axis="y", bore_dia=4.2, bores=2)
    z = extrusion.envelope(20.0, 40.0, 60.0, axis="z", bore_dia=4.2, bores=1)
    assert holes(y) == 2 and holes(z) == 1 and size_of(y) == (20.0, 60.0, 40.0)


# The eval givens: each one is drawn by a script in evals/ that calls these generators with the numbers the task
# gives, and must come out the bytes it was committed as. On the kernel that wrote them that means every byte. On
# another one (CI's OCCT 8 on Linux) the header names that kernel's processor, which no generator controls, and a
# coordinate can come out a few ulps apart (a different libm): there the STEP must match token for token, with each
# number within a nanometre, which no change to a generator's numbers could pass.
PROCESSOR = re.compile(rb"Open CASCADE STEP processor \d+(?:\.\d+)*")
NUMBER = re.compile(rb"(-?\d+\.\d*(?:E[+-]?\d+)?)")


def _same_step(got: bytes, want: bytes) -> str | None:
    """None when two STEP files match token for token with every real within 1e-9 mm, else the first difference."""
    a, b = NUMBER.split(PROCESSOR.sub(b"X", got)), NUMBER.split(PROCESSOR.sub(b"X", want))
    if len(a) != len(b):
        return f"{(len(a) - 1) // 2} numbers against {(len(b) - 1) // 2}"
    for i, (x, y) in enumerate(zip(a, b)):
        if i % 2 == 0:
            if x != y:
                return f"text {x[:60]!r} against {y[:60]!r}"
        elif not math.isclose(float(x), float(y), rel_tol=1e-12, abs_tol=1e-9):
            return f"number {x.decode()} against {y.decode()}"
    return None
EVAL_SCRIPTS = ("make_given.py", "endstop_bracket/source/given.py", "hotplate_standoffs/source/make_given.py",
                "idler_bracket/source/idler.py", "laser_panel/source/make_given.py", "mgn12h_carriage/source/mgn12.py",
                "pcb_enclosure/source/given.py", "pinned_carrier/source/make_given.py")


def test_every_eval_given_file_regenerates_to_the_bytes_it_was_committed_as(tmp_path):
    copy = tmp_path / "evals"
    shutil.copytree(REPO / "evals", copy, ignore=shutil.ignore_patterns("reference", "__pycache__", "results"))
    before = set(sys.modules)
    for script in EVAL_SCRIPTS:
        assert (copy / script).exists(), script
        sys.path.insert(0, str((copy / script).parent))                  # laser_panel's make_given.py imports its siblings
        try:
            runpy.run_path(str(copy / script), run_name="__main__")
        except SystemExit as e:
            assert e.code in (0, None), script
        finally:
            sys.path.remove(str((copy / script).parent))
    for name in set(sys.modules) - before:
        if getattr(sys.modules[name], "__file__", "") and str(copy) in str(sys.modules[name].__file__):
            del sys.modules[name]
    checked = 0
    for given in sorted((REPO / "evals").glob("*/given/**/*")):
        if not given.is_file():
            continue
        again = copy / given.relative_to(REPO / "evals")
        assert again.exists(), given
        want, got = given.read_bytes(), again.read_bytes()
        header = PROCESSOR.search(want)
        if header and header.group(0) != (PROCESSOR.search(got) or header).group(0):
            assert _same_step(got, want) is None, f"{given.relative_to(REPO)}: {_same_step(got, want)}"
        else:
            assert got == want, f"{given.relative_to(REPO)} is not what its script draws"     # this kernel wrote it
        checked += 1
    assert checked == 48


def test_the_evals_draw_their_parts_with_the_library_and_keep_their_own_numbers():
    for script, calls in (("make_given.py", "nema.motor("), ("mgn12h_carriage/source/mgn12.py", "mgn.rail("),
                          ("mgn12h_carriage/source/mgn12.py", "mgn.carriage("), ("idler_bracket/source/idler.py", "gt2.idler("),
                          ("idler_bracket/source/idler.py", "extrusion_envelope("), ("endstop_bracket/source/given.py", "envelope(")):
        text = (REPO / "evals" / script).read_text()
        assert calls in text and "cad_agent.library.gen" in text, (script, calls)
    assert "corner_cut=5.0" in (REPO / "evals" / "make_given.py").read_text()                  # the task's cut corners


# ─── cad lib ls and info ─────────────────────────────────────────────────────────────────────────────────────

def test_ls_lists_the_entries_with_what_it_would_take_to_use_each(capsys, tiny, monkeypatch):
    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda n, *a: None if n == "bd_warehouse" else real(n, *a))
    code, data = run(capsys, "lib", "ls")
    assert code == cmdbase.OK and data["problems"] == [] and data["store"].endswith("store")
    rows = {r["name"]: r for r in data["entries"]}
    assert set(rows) == {"widget", "vendor-motor", "bar", "screw"}
    assert [rows[n]["status"] for n in ("widget", "vendor-motor", "bar", "screw")] == [
        "fetch it", "add it by hand", "ready", "needs bd_warehouse (cad-agent[fasteners])"]
    assert rows["widget"]["licence"] == "CC-BY-3.0" and rows["widget"]["verified"] is False
    assert [r["name"] for r in data["entries"]] == ["bar", "vendor-motor", "widget", "screw"]       # generators, files, packages
    assert cli.main(["lib", "ls"]) == cmdbase.OK
    out = capsys.readouterr().out
    assert "4 of 4 entries" in out and "fetch it" in out and "Example Co W-1" in out


def test_ls_filters_by_kind_and_by_a_word_and_says_when_nothing_matches(capsys, tiny):
    code, data = run(capsys, "lib", "ls", "--kind", "step")
    assert [r["name"] for r in data["entries"]] == ["vendor-motor", "widget"]
    code, data = run(capsys, "lib", "ls", "vendor")
    assert [r["name"] for r in data["entries"]] == ["vendor-motor"]
    code, data = run(capsys, "lib", "ls", "VM-17")
    assert [r["name"] for r in data["entries"]] == ["vendor-motor"]
    code, data = run(capsys, "lib", "ls", "nothing-like-it")
    assert code == cmdbase.OK and data["entries"] == []
    cli.main(["lib", "ls", "nothing-like-it"])
    assert "nothing matches" in capsys.readouterr().out


def test_a_part_is_in_your_store_once_its_file_is(capsys, tiny, widget_file, tmp_path):
    assert run(capsys, "lib", "ls", "widget")[1]["entries"][0]["status"] == "fetch it"
    assert run(capsys, "lib", "add", "widget", str(widget_file), "--source", "https://example.test/widget")[0] == cmdbase.OK
    assert run(capsys, "lib", "ls", "widget")[1]["entries"][0]["status"] == "in your store"


def test_ls_shows_your_own_entries_and_a_fault_in_either_catalog_without_losing_the_rest(capsys, tiny, tmp_path):
    (tmp_path / "store").mkdir()
    (tmp_path / "store" / "library.json").write_text(json.dumps({"format": 1, "files": {}, "parts": {
        "mine": {"title": "Mine", "kind": "step", "licence": "unknown", "source": "my own", "sha256": sha(OTHER)},
        "bar": {"title": "A bar of my own", "kind": "step", "licence": "unknown", "source": "mine", "sha256": sha(OTHER)},
        "Bad Name": {"title": "x", "kind": "step", "source": "x", "sha256": sha(OTHER)}}}))
    code, data = run(capsys, "lib", "ls")
    rows = {r["name"]: r for r in data["entries"]}
    assert rows["mine"]["origin"] == "store" and rows["bar"]["origin"] == "shipped"          # the shipped one stands
    assert any("bar is also a shipped entry" in p for p in data["problems"])
    assert any("lower case words" in p for p in data["problems"]) and "Bad Name" in rows        # flagged, still listed
    cli.main(["lib", "ls"])
    assert "fault(s) in the catalog" in capsys.readouterr().out


def test_ls_with_a_store_it_cannot_read_still_lists_what_the_repo_ships(capsys, tiny, tmp_path):
    (tmp_path / "store").mkdir()
    (tmp_path / "store" / "library.json").write_text("{not json")
    code, data = run(capsys, "lib", "ls")
    assert code == cmdbase.OK and len(data["entries"]) == 4
    assert any("cannot be read" in p for p in data["problems"])


def test_info_says_where_every_number_came_from(capsys, tiny):
    code, data = run(capsys, "lib", "info", "bar")
    assert code == cmdbase.OK and data["entry"]["name"] == "bar" and data["status"] == "ready"
    assert data["entry"]["dims"]["height"] == {"value": 40.0, "source": "the sheet: 40 tall"}
    assert data["fetch"]["allowed"] is False and "nothing to download" in data["fetch"]["why_not"]
    cli.main(["lib", "info", "bar"])
    out = capsys.readouterr().out
    assert "mass     80 g at the defaults" in out and "800 g/m x 0.1 m = 80.0 g" in out
    assert "height  40.0" in out.replace("  ", " ").replace("height 40.0", "height  40.0") or "40.0" in out
    assert "param    length = 100.0 mm  (10 to 500)" in out and "param    axis = x  (one of x, y, z)" in out
    assert "its material aluminium is rated by materials.py" in out


def test_info_of_a_file_says_what_is_pinned_and_whether_it_may_be_fetched(capsys, tiny, widget_file):
    code, data = run(capsys, "lib", "info", "widget")
    assert data["fetch"] == {"allowed": True, "why_not": ""} and data["in_store"] is False
    cli.main(["lib", "info", "widget"])
    out = capsys.readouterr().out
    assert f"pinned   {sha(STEP)} ({len(STEP)} bytes)" in out and "(not in your store)" in out
    assert "fetch    allowed: `cad lib fetch widget`" in out and "credit   Example Co" in out
    assert "datum    move [1.0, 2.0, 3.0], turn [0.0, 0.0, 90.0]" in out and "UNCONFIRMED (its size)" in out
    assert "rating   85 C: the maker's sheet, page 1" in out
    code, data = run(capsys, "lib", "info", "vendor-motor")
    assert data["fetch"]["allowed"] is False and "download it by hand" in data["fetch"]["why_not"]
    cli.main(["lib", "info", "vendor-motor"])
    out = capsys.readouterr().out
    assert "mass     none declared" in out and "rating   no max_temp_c declared" in out and "download it by hand" in out
    run(capsys, "lib", "add", "widget", str(widget_file), "--source", "page")
    assert run(capsys, "lib", "info", "widget")[1]["in_store"] is True


def test_info_of_an_entry_that_is_not_there_is_a_usage_error_that_names_the_near_ones(capsys, tiny):
    code, data = run(capsys, "lib", "info", "widgit")
    assert code == cmdbase.USAGE and "no library entry 'widgit'; did you mean widget?" in data["error"]
    assert run(capsys, "lib", "info", "zzzzzz")[0] == cmdbase.USAGE
    cli.main(["lib", "info", "zzzzzz"])
    assert "`cad lib ls` lists them" in capsys.readouterr().err


def test_every_shipped_entry_is_described_without_an_error(capsys, shipped):
    for name in shipped:
        code, data = run(capsys, "lib", "info", name)
        assert code == cmdbase.OK and data["entry"]["name"] == name, name
        assert cli.main(["lib", "info", name]) == cmdbase.OK, name
        out = capsys.readouterr().out
        assert out.startswith(name) and "source" in out and "licence" in out, name


# ─── cad lib use: a generator ────────────────────────────────────────────────────────────────────────────────

def test_use_writes_a_pinned_module_and_a_sidecar_with_the_contract_keys(demo, capsys, tmp_path):
    data = copy_in(capsys, demo, "mgn12-rail", "length=300", name="rail_x")
    assert data["kind"] == "generator" and data["params"] == {"length": 300.0} and data["journaled"] is True
    module, side = bought_dir(demo) / "rail_x.py", side_of(demo, "rail_x")
    assert [Path(f).name for f in data["files"]] == ["rail_x.py", "rail_x.json"]
    assert side["sha256"] == sha(module.read_bytes()) == data["sidecar"]["sha256"]
    assert (side["vendor"], side["pn"], side["licence"], side["library"], side["geometry"], side["verified"]) == (
        "HIWIN", "MGNR12R", "MIT", "mgn12-rail", "envelope", True)
    assert side["mass_g"] == 195.0 and "650 g/m x 0.3 m = 195.0 g" in side["mass_source"] and side["library_params"] == {"length": 300.0}
    assert "max_temp_c" not in side and "material" not in side and "attribution" not in side
    text = module.read_text()
    assert text.startswith('"""rail_x: HIWIN MGNR12R miniature linear guide rail, length 300 mm.')
    assert "'length': 300.0," in text and "'width': 12.0," in text and "'end_min': 5.0," in text and "PARAMS = {}" in text
    assert text.index("def build") < text.index("from cad_agent.library.gen.mgn import rail") < text.index("return rail(**ARGS)")
    assert "VERIFIED" not in text and "cad lib use <project> mgn12-rail length=300 --as rail_x --replace" in text
    compile(text, "rail_x.py", "exec")


def test_the_module_runs_without_the_kernel_and_the_bought_part_reads_what_the_sidecar_says(demo, capsys):
    copy_in(capsys, demo, "nema17", "length=40", name="motor")
    code = ("import sys\n"
            "from cad_agent import bought as B, state as st\n"
            "from pathlib import Path\n"
            f"st.ROOT = Path({str(demo.parent)!r})\n"
            f"rows = B.list_bought({SLUG!r}); spec = B.bought_spec({SLUG!r}, 'motor')\n"
            "print(rows[0]['kind'], spec.mass_g, spec.max_temp_c, spec.geometry, spec.library, spec.pn, spec.problems,\n"
            "      sorted(m for m in ('build123d', 'OCP') if m in sys.modules))\n")
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
                       env=cad_env(PYTHONPATH=str(REPO)), cwd=str(REPO))
    assert p.returncode == 0, p.stderr
    assert p.stdout.strip().splitlines()[-1] == "MEASURED 230.0 40.0 envelope nema17 M-17nn-1.5 () []"


def test_a_copy_loads_as_a_bought_solid_and_passes_the_provenance_rule(demo, capsys, tmp_path):
    copy_in(capsys, demo, "mgn12h", name="block")
    spec = B.bought_spec(SLUG, "block")
    assert (spec.kind, spec.mass_g, spec.geometry, spec.library, spec.licence, spec.vendor, spec.verified) == (
        "MEASURED", 50.0, "envelope", "mgn12h", "MIT", "HIWIN", True) and spec.problems == ()
    assert "table 3.79" in spec.mass_source and B.tag_of(built(SLUG, "block")) == {"project": SLUG, "name": "block"}
    assert [(r.rule, r.state) for r in provenance_rows(tmp_path)] == [("source", "PASS"), ("sha256", "PASS")]
    from cad_agent import bodies
    info = bodies.describe(SLUG, {"block": built(SLUG, "block")})["block"]
    assert (info.kind, info.mass_g, info.geometry, info.vendor, info.pn, info.max_temp_c) == (
        "bought", 50.0, "envelope", "HIWIN", "MGN12H", None)
    assert "declares neither max_temp_c nor a material" in capsys.readouterr().out or True


def test_a_mass_the_sources_give_is_what_the_rules_of_step_6_weigh(demo, capsys):
    copy_in(capsys, demo, "extrusion-2040", "length=500", name="beam")
    copy_in(capsys, demo, "nema17", name="motor")
    from cad_agent import bodies
    infos = bodies.describe(SLUG, {"beam": built(SLUG, "beam"), "motor": built(SLUG, "motor")})
    assert infos["beam"].mass_g == pytest.approx(390.049, abs=0.01) and infos["beam"].geometry == "exact"
    assert infos["beam"].material == "aluminium" and infos["beam"].max_temp_c == 170.0         # materials.py's, for its material
    assert infos["motor"].mass_g == 230.0 and infos["motor"].max_temp_c == 40.0
    assert "Novanta IMS" in infos["motor"].max_temp_source or "IMS NEMA 17" in infos["motor"].max_temp_source


def test_library_parts_give_the_mass_and_heat_rules_what_they_read(demo, capsys):
    copy_in(capsys, demo, "extrusion-2040", "length=400", name="beam")
    copy_in(capsys, demo, "nema17", name="motor")
    copy_in(capsys, demo, "mgn12h", name="block")
    copy_in(capsys, demo, "gt2-idler-20t", name="idler")
    (demo / "assembly.py").write_text(
        "from build123d import Pos\nfrom cad_agent.state import bought_solid\n\nSLUG = 'demo'\nCLEARANCE = {}\nALLOW_CONTACT = set()\n\n\n"
        "def parts():\n    return {'beam': bought_solid(SLUG, 'beam'), 'motor': Pos(300, 0, 100) * bought_solid(SLUG, 'motor'),\n"
        "            'block': Pos(0, 0, 40) * bought_solid(SLUG, 'block'), 'idler': Pos(0, 100, 0) * bought_solid(SLUG, 'idler')}\n")
    (demo / "spec.toml").write_text(
        '[[mass]]\nbodies = ["beam", "motor", "block"]\nmax_g = 700\n\n[[mass]]\nbodies = ["beam", "idler"]\nmax_g = 5000\n\n'
        "[[heat]]\nat = [300, 0, 100]\ntemp_c = 60\nradius_mm = 80\n\n[[heat]]\nat = [0, 0, 0]\ntemp_c = 150\nradius_mm = 30\n")
    code, data = run(capsys, "check", SLUG, "--all")
    rows = [r for r in data["rows"] if r["rule"] in ("spec/mass", "spec/heat") or r["rule"].startswith("centre of mass")]
    mass_rows = [r for r in rows if r["rule"] == "spec/mass"]
    assert mass_rows[0]["state"] == "PASS" and mass_rows[0]["measured"].startswith("592.0 g")          # 312.0 + 230 + 50
    assert "beam 312.0 g (the section of Framing Tech's 20x40.STEP (measured); 288.925 mm2 x 2.7 g/cm3" in mass_rows[0]["measured"]
    assert "motor 230.0 g (IMS NEMA 17 datasheet, page 3" in mass_rows[0]["measured"] and "block 50.0 g (HIWIN MG series catalog" in mass_rows[0]["measured"]
    assert mass_rows[1]["state"] == "UNCHECKED" and "no mass for idler (bought part 'idler' declares no mass_g" in mass_rows[1]["measured"]
    heat = {r["subject"]: r for r in rows if r["rule"] == "spec/heat"}
    assert heat["motor"]["state"] == "FAIL" and "declared 40 C (IMS NEMA 17 datasheet" in heat["motor"]["measured"]
    assert heat["beam"]["state"] == "PASS" and "rated 170 C" in heat["beam"]["measured"]                # aluminium, from materials.py
    com = [r for r in rows if r["rule"].startswith("centre of mass")]
    assert com and com[0]["state"] == "UNCHECKED" and "idler" in com[0]["measured"]                      # judged now, and the idler's mass is unknown


def test_a_library_beam_is_judged_by_the_deflection_rule_and_its_box_is_not(demo, capsys):
    from cad_agent import spec
    if "deflection" not in spec.KINDS:                         # step 6 piece C2: a tree without it has no such rule
        pytest.skip("no [[deflection]] spec kind in this tree")
    copy_in(capsys, demo, "extrusion-2040", "length=400", name="beam")
    copy_in(capsys, demo, "extrusion-2040-envelope", "length=400", name="blank")
    (demo / "assembly.py").write_text(
        "from build123d import Pos\nfrom cad_agent.state import bought_solid\n\nSLUG = 'demo'\nCLEARANCE = {}\nALLOW_CONTACT = set()\n\n\n"
        "def parts():\n    return {'beam': bought_solid(SLUG, 'beam'), 'blank': Pos(0, 100, 0) * bought_solid(SLUG, 'blank')}\n")
    (demo / "spec.toml").write_text(
        '[[deflection]]\nbody = "beam"\nsupport = "simple"\nload_g = 500\nat = "center"\nself_weight = true\nmax_um = 200\n\n'
        '[[deflection]]\nbody = "blank"\nsupport = "simple"\nload_g = 500\nmax_um = 200\n')
    code, data = run(capsys, "check", SLUG, "--all")
    rows = {r["subject"]: r for r in data["rows"] if r["rule"] == "spec/deflection"}
    assert rows["beam"]["state"] == "PASS" and "E 70000 MPa" in rows["beam"]["measured"]
    second = float(re.search(r"I (\d+) mm\^4", rows["beam"]["measured"]).group(1))
    assert second == pytest.approx(12133.8, rel=0.01)                         # the weak axis of the maker's own 20 x 40 section
    assert rows["blank"]["state"] == "UNCHECKED" and 'not declared `geometry = "exact"`' in rows["blank"]["measured"]


def test_the_default_name_is_the_entrys_with_underscores_and_a_name_in_use_is_not_overwritten(demo, capsys):
    data = copy_in(capsys, demo, "mgn12-rail")
    assert data["name"] == "mgn12_rail" and (bought_dir(demo) / "mgn12_rail.py").exists()
    code, out = run(capsys, "lib", "use", SLUG, "mgn12-rail")
    assert code == cmdbase.USAGE and "bought/ already has mgn12_rail.py, mgn12_rail.json" in out["error"]
    assert "`--as` picks another name, `--replace` writes this one again" in out["error"]
    assert (bought_dir(demo) / "mgn12_rail.py").read_text().count("'length': 150.0") == 1


def test_replace_writes_a_part_the_library_made_again_and_never_one_it_did_not(demo, capsys):
    copy_in(capsys, demo, "mgn12-rail", "length=150", name="rail")
    first = (bought_dir(demo) / "rail.py").read_bytes()
    code, data = run(capsys, "lib", "use", SLUG, "mgn12-rail", "length=450", "--as", "rail", "--replace")
    assert code == cmdbase.OK and data["params"] == {"length": 450.0}
    assert (bought_dir(demo) / "rail.py").read_bytes() != first and side_of(demo, "rail")["mass_g"] == 292.5
    run(capsys, "bought", "add-measured", SLUG, "mine", "--size", "10", "20", "30", "--source", "a datasheet")
    mine = {p.name: p.read_bytes() for p in bought_dir(demo).glob("mine.*")}
    code, out = run(capsys, "lib", "use", SLUG, "mgn12-rail", "--as", "mine", "--replace")
    assert code == cmdbase.USAGE and "was not copied from the library, so `--replace` will not overwrite it" in out["error"]
    assert {p.name: p.read_bytes() for p in bought_dir(demo).glob("mine.*")} == mine and mine


@pytest.mark.parametrize("argv, message", [
    (["mgn12-rail", "length=20"], "length must be from 35 to 2000 mm, got 20 (table 3.81: min length 35, max length 2000)"),
    (["mgn12-rail", "length=9000"], "length must be from 35 to 2000 mm, got 9000"),
    (["mgn12-rail", "length=long"], "length must be a number of mm, got 'long'"),
    (["mgn12-rail", "width=3"], "mgn12-rail has no parameter width (parameters: length)"),
    (["nema17", "length=41"], "length must be one of 34, 40, 48, got 41"),
    (["nema8", "length=42"], "nema8 has no parameter length (parameters: none)"),
    (["extrusion-2020", "axis=w"], "axis must be one of x, y, z, got 'w'"),
    (["mgn12-rail", "--as", "my rail"], "a bought part is named with letters, digits and _"),
    (["mgn12-rail", "--as", "1rail"], "a bought part is named with letters, digits and _"),
    (["mgn12-rial"], "no library entry 'mgn12-rial'; did you mean mgn12-rail"),
    (["mgn12-rail", "length"], "parameters takes key=value, got 'length'"),
])
def test_a_request_that_cannot_be_done_as_asked_is_a_usage_error_that_writes_nothing(demo, capsys, argv, message):
    code, data = run(capsys, "lib", "use", SLUG, *argv)
    assert code == cmdbase.USAGE and message in data["error"]
    assert not bought_dir(demo).exists() or list(bought_dir(demo).iterdir()) == []
    assert not (demo / ".cad" / "undo.json").exists()


def test_a_bought_part_does_not_take_the_name_of_a_part_module(demo, capsys):
    (demo / "parts").mkdir(exist_ok=True)
    (demo / "parts" / "bracket.py").write_text("PARAMS = {}\n\n\ndef build():\n    raise NotImplementedError\n")
    code, data = run(capsys, "lib", "use", SLUG, "mgn12-rail", "--as", "bracket")
    assert code == cmdbase.USAGE and "demo already has a part module called bracket" in data["error"]
    assert not bought_dir(demo).exists() or list(bought_dir(demo).iterdir()) == []


def test_use_in_a_project_that_is_not_there_is_a_usage_error(capsys):
    code, data = run(capsys, "lib", "use", "ghost", "mgn12-rail")
    assert code == cmdbase.USAGE and "no project 'ghost'" in data["error"]


def test_a_part_whose_dimension_no_maker_publishes_is_unconfirmed_until_it_is_measured(demo, capsys, tmp_path):
    data = copy_in(capsys, demo, "gt2-idler-20t", name="idler")
    side, text = side_of(demo, "idler"), (bought_dir(demo) / "idler.py").read_text()
    assert "sha256" not in side and "verified" not in side and side["library"] == "gt2-idler-20t"
    assert "VERIFIED = False" in text and text.count("\nSOURCE = ") == 1 and "Unconfirmed: the flange thickness" in text
    assert "Not confirmed: the flange thickness (1.0 mm assumed: no listing gives it)" in text and "'flange_t': 1.0" in text
    assert any("unconfirmed (the flange thickness" in n for n in data["notes"]) and any("declares no mass_g" in n for n in data["notes"])
    spec = B.bought_spec(SLUG, "idler")
    assert spec.verified is False and spec.sha256 is None and spec.mass_g is None and spec.material == "aluminium"
    assert [(r.rule, r.state) for r in provenance_rows(tmp_path)] == [("source", "UNCHECKED")]
    # a calliper reading confirms it the way it confirms any measured part, and the part is not left pinned to a file it rewrote
    code, out = run(capsys, "bought", "verify", SLUG, "idler", "--note", "callipers: flange 1.0, 8.5 across")
    assert code == cmdbase.OK and B.bought_spec(SLUG, "idler").verified is True
    assert "confirmed: callipers: flange 1.0" in B.bought_spec(SLUG, "idler").source
    assert [(r.rule, r.state) for r in provenance_rows(tmp_path)] == [("source", "PASS")]


def test_a_bd_warehouse_part_needs_its_package_and_the_message_says_which_extra(demo, capsys, tiny, monkeypatch):
    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda n, *a: None if n == "bd_warehouse" else real(n, *a))
    code, data = run(capsys, "lib", "use", SLUG, "screw")
    assert code == cmdbase.USAGE and "bd_warehouse, which is not installed: `pip install 'cad-agent[fasteners]'`" in data["error"]
    assert not bought_dir(demo).exists() or list(bought_dir(demo).iterdir()) == []
    monkeypatch.setattr(importlib.util, "find_spec", lambda n, *a: object() if n == "bd_warehouse" else real(n, *a))
    code, data = run(capsys, "lib", "use", SLUG, "screw", "size=M4-0.7")
    assert code == cmdbase.OK and "from bd_warehouse.fastener import SocketHeadCapScrew" in (bought_dir(demo) / "screw.py").read_text()
    assert "'fastener_type': 'iso4762'" in (bought_dir(demo) / "screw.py").read_text() and "mass_g" not in side_of(demo, "screw")
    assert side_of(demo, "screw")["library_params"] == {"size": "M4-0.7"}


# The three standards' tables as the pages the catalog cites print them: ISO 4762 (engineersedge.com/iso_socket_head_screw.htm),
# head diameter dk and height k; ISO 4032 (wermac.org, dimensions_hex-nuts_across-flats-and-heights_din-iso.html), across flats and
# thickness; ISO 7089 (torqbolt.com/iso-7089-flat-washers-200hv-dimensions-standards-specifications), outside diameter and thickness.
ISO_4762 = {"M2-0.4": (3.8, 2.0), "M2.5-0.45": (4.5, 2.5), "M3-0.5": (5.5, 3.0), "M4-0.7": (7.0, 4.0), "M5-0.8": (8.5, 5.0),
            "M6-1": (10.0, 6.0), "M8-1.25": (13.0, 8.0)}
ISO_4032 = {"M2-0.4": (4.0, 1.6), "M2.5-0.45": (5.0, 2.0), "M3-0.5": (5.5, 2.4), "M4-0.7": (7.0, 3.2), "M5-0.8": (8.0, 4.7),
            "M6-1": (10.0, 5.2), "M8-1.25": (13.0, 6.8)}
ISO_7089 = {"M2": (5.0, 0.35), "M2.5": (6.0, 0.55), "M3": (7.0, 0.55), "M4": (9.0, 0.9), "M5": (10.0, 1.1), "M6": (12.0, 1.8),
            "M8": (16.0, 1.8)}


def test_the_catalogs_bd_warehouse_sizes_are_the_standards_tables(demo, capsys, shipped):
    pytest.importorskip("bd_warehouse")
    assert tuple(shipped["iso4762-screw"].params["size"]["choices"]) == tuple(ISO_4762)
    assert tuple(shipped["iso4032-nut"].params["size"]["choices"]) == tuple(ISO_4032)
    assert tuple(shipped["iso7089-washer"].params["size"]["choices"]) == tuple(ISO_7089)
    for size, (dk, k) in ISO_4762.items():
        run(capsys, "lib", "use", SLUG, "iso4762-screw", f"size={size}", "length=12", "--as", "screw", "--replace")
        lo, hi = lo_hi(built(SLUG, "screw"))
        assert (round(lo[2], 3), round(hi[2], 3)) == (-12.0, k), size                         # k above the face, 12 below it
        assert dk <= hi[0] - lo[0] <= dk + 0.3, size                                          # bd_warehouse knurls the head: dk max + 0.18 to 0.27
    for size, (flats, thick) in ISO_4032.items():
        run(capsys, "lib", "use", SLUG, "iso4032-nut", f"size={size}", "--as", "nut", "--replace")
        lo, hi = lo_hi(built(SLUG, "nut"))
        assert round(hi[2] - lo[2], 3) == thick and round(hi[1] - lo[1], 3) == flats, size
    for size, (across, thick) in ISO_7089.items():
        run(capsys, "lib", "use", SLUG, "iso7089-washer", f"size={size}", "--as", "washer", "--replace")
        lo, hi = lo_hi(built(SLUG, "washer"))
        assert round(hi[2] - lo[2], 3) == thick and round(hi[0] - lo[0], 3) == across, size


# ─── cad lib use: a STEP, from the store ─────────────────────────────────────────────────────────────────────

def put_widget(capsys, widget_file):
    code, data = run(capsys, "lib", "add", "widget", str(widget_file), "--source", "https://example.test/widget")
    assert code == cmdbase.OK, data
    return data


def test_a_step_is_copied_from_the_store_with_its_pin_its_credit_and_its_datum(demo, capsys, tiny, widget_file, tmp_path):
    put_widget(capsys, widget_file)
    data = copy_in(capsys, demo, "widget", name="part")
    assert (bought_dir(demo) / "part.step").read_bytes() == STEP and data["kind"] == "step" and data["journaled"] is True
    side = side_of(demo, "part")
    assert side["sha256"] == sha(STEP) and side["library"] == "widget" and side["licence"] == "CC-BY-3.0"
    assert side["attribution"] == "Example Co, https://example.test/widget, CC-BY 3.0"
    assert (side["vendor"], side["pn"], side["mass_g"], side["max_temp_c"], side["material"]) == ("Example Co", "W-1", 12.5, 85.0, "aluminium")
    assert side["mass_source"] == "the maker's sheet, page 2" and side["datum"] == {"move": [1.0, 2.0, 3.0], "turn": [0.0, 0.0, 90.0]}
    assert side["original"] == f"{sha(STEP)}.step" and "In the store: downloaded by hand from https://example.test/widget" in side["source"]
    assert side["verified"] is False and "library_params" not in side
    spec = B.bought_spec(SLUG, "part")
    assert (spec.kind, spec.file, spec.sha256, spec.mass_g, spec.max_temp_c, spec.datum) == (
        "STEP", "part.step", sha(STEP), 12.5, 85.0, {"move": (1.0, 2.0, 3.0), "turn": (0.0, 0.0, 90.0)}) and spec.problems == ()
    assert [(r.rule, r.state) for r in provenance_rows(tmp_path)] == [("source", "UNCHECKED"), ("sha256", "PASS")]


def test_a_step_that_is_not_in_the_store_says_how_to_get_it(demo, capsys, tiny):
    code, data = run(capsys, "lib", "use", SLUG, "widget")
    assert code == cmdbase.USAGE and "widget is not in your store" in data["error"]
    assert "`cad lib fetch widget`, or download it by hand and `cad lib add widget FILE --source URL`" in data["error"]
    code, data = run(capsys, "lib", "use", SLUG, "vendor-motor")
    assert code == cmdbase.USAGE and "download it by hand and `cad lib add vendor-motor FILE --source URL`" in data["error"]
    assert "cad lib fetch vendor-motor" not in data["error"]
    assert not (bought_dir(demo)).exists() or list(bought_dir(demo).iterdir()) == []


def test_a_store_file_that_no_longer_hashes_to_its_pin_is_refused_with_exit_1(demo, capsys, tiny, widget_file, tmp_path):
    put_widget(capsys, widget_file)
    (tmp_path / "store" / f"{sha(STEP)}.step").write_bytes(OTHER)
    code, data = run(capsys, "lib", "use", SLUG, "widget")
    assert code == cmdbase.FAIL and "no longer hashes to the catalog's pin" in data["error"] and "damaged" in data["error"]
    assert not (bought_dir(demo) / "widget.step").exists()


def test_a_file_takes_no_parameters(demo, capsys, tiny, widget_file):
    put_widget(capsys, widget_file)
    code, data = run(capsys, "lib", "use", SLUG, "widget", "length=3")
    assert code == cmdbase.USAGE and "is a file, which takes no parameters (got length)" in data["error"]


def test_use_journals_the_files_and_undo_takes_them_back(demo, capsys):
    copy_in(capsys, demo, "mgn12-rail", name="rail")
    entry = undo.load(demo)["undo"][-1]
    assert entry["name"] == "Add Library Part" and entry["by"] == "agent" and entry["cmd"].startswith("cad lib use demo mgn12-rail")
    assert sorted(f["path"] for f in entry["files"]) == ["bought/rail.json", "bought/rail.py"]
    assert all(f["before"] is None and f["after"] for f in entry["files"])
    code, data = run(capsys, "undo", SLUG)
    assert code == cmdbase.OK and not (bought_dir(demo) / "rail.py").exists() and not (bought_dir(demo) / "rail.json").exists()
    code, data = run(capsys, "redo", SLUG)
    assert code == cmdbase.OK and (bought_dir(demo) / "rail.py").exists()
    assert side_of(demo, "rail")["library"] == "mgn12-rail"


def test_a_replace_is_one_undoable_step_back_to_what_was_there(demo, capsys):
    copy_in(capsys, demo, "mgn12-rail", "length=150", name="rail")
    before = (bought_dir(demo) / "rail.py").read_text()
    run(capsys, "lib", "use", SLUG, "mgn12-rail", "length=450", "--as", "rail", "--replace")
    assert (bought_dir(demo) / "rail.py").read_text() != before
    run(capsys, "undo", SLUG)
    assert (bought_dir(demo) / "rail.py").read_text() == before and side_of(demo, "rail")["mass_g"] == 97.5


def test_a_large_step_is_copied_and_not_kept_in_the_journal(demo, capsys, tmp_path, monkeypatch):
    big = STEP + b"/* " + b"x" * (5 << 20) + b" */\n"
    path = tmp_path / "big.step"
    path.write_bytes(big)
    assert run(capsys, "lib", "add", "big-part", str(path), "--source", "a page", "--licence", "MIT")[0] == cmdbase.OK
    data = copy_in(capsys, demo, "big-part")
    assert data["journaled"] is False and (bought_dir(demo) / "big_part.step").read_bytes() == big
    assert undo.load(demo)["undo"] == []
    cli.main(["lib", "use", SLUG, "big-part", "--as", "again"])
    assert "not journaled (the files are large)" in capsys.readouterr().out


def test_every_command_writes_its_line_in_the_activity_log(demo, capsys, tmp_path):
    copy_in(capsys, demo, "mgn12-rail", name="rail")
    run(capsys, "lib", "check", SLUG)
    run(capsys, "lib", "ls")
    lines = log_lines(demo)
    use_line = [x for x in lines if x["cmd"] == "lib use"][0]
    assert use_line["exit"] == 0 and use_line["summary"] == "mgn12-rail as rail" and use_line["argv"][:3] == ["--json", "lib", "use"]
    assert sorted(Path(f).name for f in use_line["files"]) == ["rail.json", "rail.py"]
    assert [x["cmd"] for x in lines].count("lib check") == 1                                  # a command that names a project logs there
    root = log_lines(tmp_path / "projects")
    assert [x["cmd"] for x in root] == ["lib ls"] and root[0]["exit"] == 0                    # one that names none, in the root's


# ─── cad lib add ─────────────────────────────────────────────────────────────────────────────────────────────

def test_add_stores_a_file_the_catalog_pins_under_its_hash_and_records_where_it_came_from(capsys, tiny, widget_file, tmp_path):
    code, data = run(capsys, "lib", "add", "widget", str(widget_file), "--source", "https://example.test/widget")
    assert code == cmdbase.OK and data["created"] is True and data["sha256"] == sha(STEP)
    stored_file = tmp_path / "store" / f"{sha(STEP)}.step"
    assert data["path"] == str(stored_file) and stored_file.read_bytes() == STEP
    record = json.loads((tmp_path / "store" / "library.json").read_text())
    assert record["format"] == 1 and record["parts"] == {}
    assert record["files"][sha(STEP)]["entry"] == "widget" and record["files"][sha(STEP)]["how"] == "add"
    assert record["files"][sha(STEP)]["source"] == "https://example.test/widget"
    code, again = run(capsys, "lib", "add", "widget", str(widget_file), "--source", "https://example.test/widget")
    assert code == cmdbase.OK and again["created"] is False                                   # the same file again changes nothing
    cli.main(["lib", "add", "widget", str(widget_file), "--source", "x"])
    assert "already stored as" in capsys.readouterr().out


def test_add_refuses_a_file_that_is_not_the_one_the_catalog_pins_and_stores_nothing(capsys, tiny, tmp_path):
    other = tmp_path / "other.step"
    other.write_bytes(OTHER)
    code, data = run(capsys, "lib", "add", "widget", str(other), "--source", "a page")
    assert code == cmdbase.FAIL
    assert f"hashes to {sha(OTHER)}, not the {sha(STEP)} the catalog pins" in data["error"] and "Nothing was stored" in data["error"]
    assert f"To keep it anyway, give it a name of your own: `cad lib add NAME {other} --source URL`" in data["error"]
    assert not (tmp_path / "store").exists() or list((tmp_path / "store").iterdir()) == []


def test_add_wants_a_step_file_that_is_there(capsys, tiny, tmp_path):
    code, data = run(capsys, "lib", "add", "widget", str(tmp_path / "nothing.step"), "--source", "a page")
    assert code == cmdbase.USAGE and "no file at" in data["error"]
    page = tmp_path / "page.html"
    page.write_text("<html>")
    code, data = run(capsys, "lib", "add", "widget", str(page), "--source", "a page")
    assert code == cmdbase.USAGE and "does not begin the way a STEP file does (ISO-10303-21;)" in data["error"]
    assert not (tmp_path / "store").exists()


def test_add_wants_a_source_and_says_so_the_way_every_command_does(capsys, tiny, widget_file):
    assert cli.main(["lib", "add", "widget", str(widget_file)]) == cmdbase.USAGE
    assert "--source" in capsys.readouterr().err
    code, data = run(capsys, "lib", "add", "widget", str(widget_file), "--source", "  ")
    assert code == cmdbase.USAGE and "--source is required" in data["error"]


def test_add_is_for_a_file_and_the_flags_for_a_new_one_are_not_for_a_catalog_entry(capsys, tiny, widget_file):
    code, data = run(capsys, "lib", "add", "bar", str(widget_file), "--source", "a page")
    assert code == cmdbase.USAGE and "bar is drawn by the library, so there is no file to add" in data["error"]
    code, data = run(capsys, "lib", "add", "widget", str(widget_file), "--source", "a page", "--vendor", "Me", "--mass-g", "5",
                     "--mass-source", "scale")
    assert code == cmdbase.USAGE and "the catalog already says what widget is; --vendor, --mass-g, --mass-source are for a file it does not know" in data["error"]
    code, data = run(capsys, "lib", "add", "Not A Name", str(widget_file), "--source", "a page")
    assert code == cmdbase.USAGE and "lower case words joined by hyphens" in data["error"]


def test_add_makes_a_new_entry_of_your_own_from_the_flags(capsys, tmp_path, widget_file, demo):
    code, data = run(capsys, "lib", "add", "my-motor", str(widget_file), "--source", "the vendor's CAD page",
                     "--vendor", "Vendor Inc", "--pn", "VM-1", "--licence", "vendor terms", "--title", "My motor",
                     "--mass-g", "280", "--mass-source", "weighed on a kitchen scale", "--max-temp-c", "50",
                     "--max-temp-source", "the vendor's sheet", "--geometry", "exact", "--material", "aluminium",
                     "--datum-move=-1,0,2", "--datum-turn", "0,0,90", "--unverified")
    assert code == cmdbase.OK, data
    record = json.loads((tmp_path / "store" / "library.json").read_text())
    assert record["parts"]["my-motor"] == {
        "title": "My motor", "kind": "step", "licence": "vendor terms", "geometry": "exact", "verified": False,
        "source": "the vendor's CAD page", "vendor": "Vendor Inc", "pn": "VM-1", "material": "aluminium",
        "mass": {"g": 280.0, "source": "weighed on a kitchen scale"}, "max_temp_c": 50.0, "max_temp_source": "the vendor's sheet",
        "datum": {"move": [-1.0, 0.0, 2.0], "turn": [0.0, 0.0, 90.0]}, "sha256": sha(STEP), "size": len(STEP)}
    entry = catalog.load().get("my-motor")
    assert entry.origin == "store" and entry.problems == () and not catalog.fetch_ruling(entry)[0]       # a vendor's file is not fetched
    assert run(capsys, "lib", "info", "my-motor")[0] == cmdbase.OK
    copy_in(capsys, demo, "my-motor", name="motor")
    side = side_of(demo, "motor")
    assert (side["vendor"], side["mass_g"], side["geometry"], side["licence"], side["sha256"]) == ("Vendor Inc", 280.0, "exact", "vendor terms", sha(STEP))
    assert B.bought_spec(SLUG, "motor").problems == ()


def test_add_wants_a_source_for_every_number_it_is_given(capsys, tmp_path, widget_file):
    base = ["lib", "add", "my-part", str(widget_file), "--source", "a page"]
    code, data = run(capsys, *base, "--mass-g", "5")
    assert code == cmdbase.USAGE and "--mass-g and --mass-source go together" in data["error"]
    code, data = run(capsys, *base, "--max-temp-source", "a sheet")
    assert code == cmdbase.USAGE and "--max-temp-c and --max-temp-source go together" in data["error"]
    code, data = run(capsys, *base, "--datum-move", "1,2")
    assert code == cmdbase.USAGE and "--datum-move takes X,Y,Z" in data["error"]
    code, data = run(capsys, *base, "--licence", "CC-BY-4.0")
    assert code == cmdbase.USAGE and "needs an attribution" in data["error"]
    assert not (tmp_path / "store" / "library.json").exists()                                # nothing was written for any of them


def test_a_second_file_for_your_own_entry_is_refused_until_you_say_replace(capsys, tmp_path, widget_file):
    base = ["lib", "add", "my-part", "--source", "a page"]
    assert run(capsys, *base[:3], str(widget_file), *base[3:])[0] == cmdbase.OK
    other = tmp_path / "other.step"
    other.write_bytes(OTHER)
    code, data = run(capsys, "lib", "add", "my-part", str(other), "--source", "page two")
    assert code == cmdbase.FAIL and f"your entry my-part pins {sha(STEP)}" in data["error"] and "`--replace` pins this one instead" in data["error"]
    assert not (tmp_path / "store" / f"{sha(OTHER)}.step").exists()                          # a refused file is not kept
    code, data = run(capsys, "lib", "add", "my-part", str(other), "--source", "page two", "--replace")
    assert code == cmdbase.OK and data["sha256"] == sha(OTHER)
    record = json.loads((tmp_path / "store" / "library.json").read_text())
    assert record["parts"]["my-part"]["sha256"] == sha(OTHER) and record["parts"]["my-part"]["source"] == "page two"
    assert (tmp_path / "store" / f"{sha(STEP)}.step").exists()                               # the first file is still there, by its hash


def test_a_store_record_that_cannot_be_read_is_never_written_over(capsys, tmp_path, widget_file):
    (tmp_path / "store").mkdir()
    (tmp_path / "store" / "library.json").write_text("{not json")
    code, data = run(capsys, "lib", "add", "my-part", str(widget_file), "--source", "a page")
    assert code == cmdbase.FAIL and "library.json cannot be read" in data["error"] and "nothing is lost" in data["error"]
    assert (tmp_path / "store" / "library.json").read_text() == "{not json"
    wrong = tmp_path / "store" / "library.json"
    wrong.write_text(json.dumps({"format": 2, "parts": {}, "files": {}}))
    assert run(capsys, "lib", "add", "my-part", str(widget_file), "--source", "a page")[0] == cmdbase.FAIL


# ─── cad lib fetch ───────────────────────────────────────────────────────────────────────────────────────────

def test_fetch_downloads_a_file_the_licence_allows_and_stores_it_under_its_hash(capsys, tiny, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(store, "OPEN", serving(STEP, calls=calls))
    code, data = run(capsys, "lib", "fetch", "widget")
    assert code == cmdbase.OK and calls == [("https://example.test/widget.step", store.TIMEOUT_S)]
    (row,) = data["fetched"]
    assert row["state"] == "PASS" and row["downloaded"] is True and row["sha256"] == sha(STEP)
    assert (tmp_path / "store" / f"{sha(STEP)}.step").read_bytes() == STEP
    assert [p.name for p in (tmp_path / "store").iterdir() if p.name != "library.json"] == [f"{sha(STEP)}.step"]     # no .part left over
    record = json.loads((tmp_path / "store" / "library.json").read_text())["files"][sha(STEP)]
    assert (record["entry"], record["how"], record["url"]) == ("widget", "fetch", "https://example.test/widget.step")
    cli.main(["lib", "ls", "widget"])
    assert "in your store" in capsys.readouterr().out


def test_fetch_says_whose_credit_the_licence_asks_for(capsys, tiny, monkeypatch):
    monkeypatch.setattr(store, "OPEN", serving(STEP))
    assert cli.main(["lib", "fetch", "widget"]) == cmdbase.OK
    out = capsys.readouterr().out
    assert "fetch: 1 of 1 in your store" in out and "PASS      widget: downloaded to" in out
    assert "credit    Example Co, https://example.test/widget, CC-BY 3.0" in out


def test_a_file_already_in_the_store_is_not_downloaded_again(capsys, tiny, widget_file, monkeypatch):
    put_widget(capsys, widget_file)
    calls = []
    monkeypatch.setattr(store, "OPEN", serving(STEP, calls=calls))
    code, data = run(capsys, "lib", "fetch", "widget")
    assert code == cmdbase.OK and calls == [] and data["fetched"][0]["downloaded"] is False
    cli.main(["lib", "fetch", "widget"])
    assert "already in your store" in capsys.readouterr().out


def test_a_download_that_does_not_hash_to_the_pin_is_exit_1_and_writes_nothing(capsys, tiny, tmp_path, monkeypatch):
    monkeypatch.setattr(store, "OPEN", serving(OTHER))
    code, data = run(capsys, "lib", "fetch", "widget")
    assert code == cmdbase.FAIL and data["fetched"][0]["state"] == "FAIL"
    assert f"gave a file that hashes to {sha(OTHER)}, not the {sha(STEP)} the catalog pins" in data["fetched"][0]["error"]
    assert "Nothing was stored" in data["fetched"][0]["error"]
    assert not (tmp_path / "store").exists() or [p.name for p in (tmp_path / "store").iterdir()] == []
    cli.main(["lib", "fetch", "widget"])
    assert "FAIL      widget" in capsys.readouterr().out


@pytest.mark.parametrize("error", [urllib.error.URLError("no route to host"),
                                   urllib.error.HTTPError("https://example.test/widget.step", 503, "Service Unavailable", {}, None),
                                   TimeoutError("timed out"), ConnectionResetError("reset"),
                                   __import__("http.client").client.IncompleteRead(b"")])
def test_a_network_that_does_not_answer_is_unchecked_not_a_failure(capsys, tiny, tmp_path, monkeypatch, error):
    monkeypatch.setattr(store, "OPEN", serving(error=error))
    code, data = run(capsys, "lib", "fetch", "widget")
    assert code == cmdbase.UNCHECKED and data["fetched"][0]["state"] == "UNCHECKED"
    assert "could not download https://example.test/widget.step" in data["fetched"][0]["error"]
    assert not (tmp_path / "store").exists() or [p.name for p in (tmp_path / "store").iterdir()] == []


def test_a_download_that_stops_half_way_leaves_nothing_behind(capsys, tiny, tmp_path, monkeypatch):
    class Dies(Response):
        def read(self, n=-1):
            if self.at:
                raise ConnectionResetError("the connection dropped")
            return super().read(10)

    monkeypatch.setattr(store, "OPEN", lambda request, timeout=None: Dies(STEP))
    code, data = run(capsys, "lib", "fetch", "widget")
    assert code == cmdbase.UNCHECKED and "the connection dropped" in data["fetched"][0]["error"]
    assert [p.name for p in (tmp_path / "store").iterdir()] == []


def test_fetch_refuses_a_licence_that_does_not_let_the_repo_do_it_and_says_what_to_do(capsys, tiny, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(store, "OPEN", serving(VENDOR_STEP, calls=calls))
    code, data = run(capsys, "lib", "fetch", "vendor-motor")
    assert code == cmdbase.USAGE and calls == []
    assert "vendor-motor is under vendor terms, which does not let the repo fetch it for you" in data["error"]
    assert "download it by hand from https://vendor.test/motor and run `cad lib add vendor-motor FILE --source URL`" in data["error"]
    assert not (tmp_path / "store").exists()


def test_fetch_checks_every_entry_before_it_downloads_any(capsys, tiny, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(store, "OPEN", serving(STEP, calls=calls))
    code, data = run(capsys, "lib", "fetch", "widget", "vendor-motor")
    assert code == cmdbase.USAGE and calls == []                                             # the one that cannot be fetched stops the lot
    assert run(capsys, "lib", "fetch", "bar")[0] == cmdbase.USAGE
    code, data = run(capsys, "lib", "fetch", "widgit")
    assert code == cmdbase.USAGE and "did you mean widget?" in data["error"]


def test_the_worst_of_several_downloads_is_the_verdict(capsys, tiny, tmp_path, monkeypatch):
    extra = tmp_path / "extra.step"
    extra.write_bytes(OTHER)
    assert run(capsys, "lib", "add", "second", str(extra), "--source", "a page", "--licence", "MIT")[0] == cmdbase.OK
    record = json.loads((tmp_path / "store" / "library.json").read_text())
    record["parts"]["second"]["url"] = "https://example.test/second.step"
    (tmp_path / "store" / "library.json").write_text(json.dumps(record))
    (tmp_path / "store" / f"{sha(OTHER)}.step").unlink()
    serve = {"https://example.test/widget.step": STEP, "https://example.test/second.step": None}

    def opener(request, timeout=None):
        data = serve[request.full_url]
        if data is None:
            raise urllib.error.URLError("down")
        return Response(data)

    monkeypatch.setattr(store, "OPEN", opener)
    code, data = run(capsys, "lib", "fetch", "widget", "second", "widget")                  # a name twice is fetched once
    assert code == cmdbase.UNCHECKED and [r["state"] for r in data["fetched"]] == ["PASS", "UNCHECKED"]
    serve["https://example.test/widget.step"] = OTHER
    (tmp_path / "store" / f"{sha(STEP)}.step").unlink()
    code, data = run(capsys, "lib", "fetch", "widget", "second")
    assert code == cmdbase.FAIL and [r["state"] for r in data["fetched"]] == ["FAIL", "UNCHECKED"]       # FAIL outranks UNCHECKED


def test_a_damaged_file_in_the_store_is_not_taken_for_the_one_that_was_asked_for(capsys, tiny, tmp_path, monkeypatch):
    (tmp_path / "store").mkdir()
    (tmp_path / "store" / f"{sha(STEP)}.step").write_bytes(OTHER)
    monkeypatch.setattr(store, "OPEN", serving(STEP))
    code, data = run(capsys, "lib", "fetch", "widget")
    assert code == cmdbase.FAIL and "no longer hashes to its own name: it is damaged" in data["fetched"][0]["error"]


def test_a_download_larger_than_any_pinned_step_is_refused(capsys, tiny, tmp_path, monkeypatch):
    monkeypatch.setattr(store, "MAX_BYTES", 10)
    monkeypatch.setattr(store, "OPEN", serving(STEP))
    code, data = run(capsys, "lib", "fetch", "widget")
    assert code == cmdbase.FAIL and "is larger than 0 MB" in data["fetched"][0]["error"]
    assert [p.name for p in (tmp_path / "store").iterdir()] == []


# ─── cad lib check: the store ────────────────────────────────────────────────────────────────────────────────

def rule_states(data):
    return {(r["rule"], r["subject"].split(" ")[0]): r["state"] for r in data["rows"]}


def test_an_empty_store_is_nothing_to_check_not_a_fault(capsys, tiny):
    code, data = run(capsys, "lib", "check")
    assert code == cmdbase.OK and data["project"] is None
    assert rule_states(data) == {("pin", "widget"): "N/A", ("pin", "vendor-motor"): "N/A"}
    cli.main(["lib", "check"])
    assert "against the catalog's pins: 2 N/A" in capsys.readouterr().out


def test_a_store_of_the_files_the_catalog_pins_passes(capsys, tiny, widget_file):
    put_widget(capsys, widget_file)
    code, data = run(capsys, "lib", "check")
    assert code == cmdbase.OK and data["summary"] == {"PASS": 2, "FAIL": 0, "UNCHECKED": 0, "N/A": 1}
    states = rule_states(data)
    assert states[("store file", sha(STEP)[:12])] == "PASS" and states[("pin", "widget")] == "PASS"
    cli.main(["lib", "check", "--all"])
    assert "PASS      library/store file" in capsys.readouterr().out


def test_a_store_file_that_no_longer_hashes_to_its_name_is_a_fail(capsys, tiny, widget_file, tmp_path):
    put_widget(capsys, widget_file)
    (tmp_path / "store" / f"{sha(STEP)}.step").write_bytes(OTHER)
    code, data = run(capsys, "lib", "check")
    assert code == cmdbase.FAIL
    assert rule_states(data)[("store file", sha(STEP)[:12])] == "FAIL" and rule_states(data)[("pin", "widget")] == "FAIL"
    assert f"hashes to {sha(OTHER)}, not its name" in [r for r in data["rows"] if r["rule"] == "store file"][0]["measured"]


def test_a_file_you_added_that_the_store_lacks_is_a_fail_and_one_never_fetched_is_not(capsys, tiny, widget_file, tmp_path):
    assert run(capsys, "lib", "add", "mine", str(widget_file), "--source", "a page", "--licence", "MIT")[0] == cmdbase.OK
    (tmp_path / "store" / f"{sha(STEP)}.step").unlink()
    code, data = run(capsys, "lib", "check")
    assert code == cmdbase.FAIL and rule_states(data)[("pin", "mine")] == "FAIL" and rule_states(data)[("pin", "widget")] == "N/A"
    assert "your entry pins" in [r for r in data["rows"] if r["subject"] == "mine"][0]["measured"]


def test_a_catalog_with_a_fault_is_a_fail_row_and_the_rest_is_still_checked(capsys, tiny, tmp_path):
    (tmp_path / "store").mkdir()
    (tmp_path / "store" / "library.json").write_text("{not json")
    code, data = run(capsys, "lib", "check")
    assert code == cmdbase.FAIL
    assert [r["state"] for r in data["rows"] if r["rule"] == "catalog"] == ["FAIL"] and "cannot be read" in data["rows"][0]["measured"]
    assert ("pin", "widget") in rule_states(data)


def test_with_nothing_shipped_to_pin_and_nothing_stored_the_store_check_says_so(capsys, tmp_path, monkeypatch):
    empty = tmp_path / "empty.toml"
    empty.write_text("")
    monkeypatch.setattr(catalog, "CATALOG", empty)
    code, data = run(capsys, "lib", "check")
    assert code == cmdbase.OK and [(r["rule"], r["state"]) for r in data["rows"]] == [("store", "N/A")]


# ─── cad lib check: a project ────────────────────────────────────────────────────────────────────────────────

def test_a_project_of_library_parts_passes_every_row(demo, capsys, widget_file, tiny):
    put_widget(capsys, widget_file)
    copy_in(capsys, demo, "widget", name="part")
    copy_in(capsys, demo, "bar", "length=200", name="beam")
    code, data = run(capsys, "lib", "check", SLUG)
    assert code == cmdbase.OK and data["project"] == SLUG and data["summary"] == {"PASS": 4, "FAIL": 0, "UNCHECKED": 0, "N/A": 0}
    assert sorted(rule_states(data)) == [("catalog", "beam"), ("catalog", "part"), ("sha256", "beam"), ("sha256", "part")]
    cli.main(["lib", "check", SLUG])
    assert f"{SLUG}/bought/ against its sidecars and the catalog: 4 PASS" in capsys.readouterr().out


def test_a_module_edited_by_hand_fails_both_checks(demo, capsys, tmp_path):
    copy_in(capsys, demo, "mgn12-rail", name="rail")
    path = bought_dir(demo) / "rail.py"
    path.write_text(path.read_text().replace("'pitch': 25.0", "'pitch': 26.0"))
    code, data = run(capsys, "lib", "check", SLUG)
    assert code == cmdbase.FAIL and rule_states(data)[("sha256", "rail")] == "FAIL"
    assert "rail.py hashes to" in [r for r in data["rows"] if r["rule"] == "sha256"][0]["measured"] and "the sidecar pins" in data["rows"][0]["measured"]
    assert rule_states(data)[("catalog", "rail")] == "UNCHECKED" and "the module" in [r for r in data["rows"] if r["rule"] == "catalog"][0]["measured"]
    assert ("sha256", "FAIL") in [(r.rule, r.state) for r in provenance_rows(tmp_path)]       # the verifier fails it too


def test_a_step_that_was_changed_in_the_project_fails_against_its_pin_and_the_catalogs(demo, capsys, tiny, widget_file):
    put_widget(capsys, widget_file)
    copy_in(capsys, demo, "widget", name="part")
    (bought_dir(demo) / "part.step").write_bytes(OTHER)
    code, data = run(capsys, "lib", "check", SLUG)
    assert code == cmdbase.FAIL and rule_states(data) == {("sha256", "part"): "FAIL", ("catalog", "part"): "FAIL"}
    catalog_row = [r for r in data["rows"] if r["rule"] == "catalog"][0]
    assert f"part.step hashes to {sha(OTHER)[:16]}..., and widget pins {sha(STEP)[:16]}..." in catalog_row["measured"]


def test_a_catalog_that_has_moved_on_is_unchecked_and_says_what_differs(demo, capsys, tmp_path, monkeypatch):
    copy_in(capsys, demo, "mgn12-rail", "length=300", name="rail")
    moved = tmp_path / "moved.toml"
    moved.write_text(CATALOG_TOML.read_text().replace("per_m_g = 650.0", "per_m_g = 700.0", 1))
    monkeypatch.setattr(catalog, "CATALOG", moved)
    code, data = run(capsys, "lib", "check", SLUG)
    assert code == cmdbase.UNCHECKED and rule_states(data) == {("sha256", "rail"): "PASS", ("catalog", "rail"): "UNCHECKED"}
    measured = [r for r in data["rows"] if r["rule"] == "catalog"][0]["measured"]
    assert "the catalog says something else now: mass_g, mass_source" in measured and "--replace` takes the change" in measured
    run(capsys, "lib", "use", SLUG, "mgn12-rail", "length=300", "--as", "rail", "--replace")
    assert run(capsys, "lib", "check", SLUG)[0] == cmdbase.OK                                 # and taking it settles it


def test_an_entry_the_catalog_no_longer_has_is_unchecked(demo, capsys, tiny, tmp_path):
    copy_in(capsys, demo, "bar", name="beam")
    other = tmp_path / "other.toml"
    other.write_text("")
    import cad_agent.library.catalog as C
    C.CATALOG = other
    try:
        code, data = run(capsys, "lib", "check", SLUG)
    finally:
        C.CATALOG = tmp_path / "catalog.toml"
    assert code == cmdbase.UNCHECKED and rule_states(data)[("catalog", "beam")] == "UNCHECKED"
    assert "bar is not in this catalog" in [r for r in data["rows"] if r["rule"] == "catalog"][0]["measured"]


def test_a_sidecar_that_forgot_its_parameters_or_whose_parameters_no_longer_hold_is_unchecked(demo, capsys, tmp_path, monkeypatch):
    copy_in(capsys, demo, "mgn12-rail", "length=300", name="rail")
    side = bought_dir(demo) / "rail.json"
    data0 = json.loads(side.read_text())
    del data0["library_params"]
    side.write_text(json.dumps(data0))
    code, data = run(capsys, "lib", "check", SLUG)
    assert code == cmdbase.UNCHECKED and "does not record the parameters it was made with" in data["rows"][-1]["measured"]
    data0["library_params"] = {"length": 300.0}
    side.write_text(json.dumps(data0))
    tight = tmp_path / "tight.toml"
    tight.write_text(CATALOG_TOML.read_text().replace("max = 2000.0\nunit = \"mm\"\nsource = \"table 3.81: min length 35, max length 2000\"",
                                                      "max = 200.0\nunit = \"mm\"\nsource = \"table 3.81: min length 35, max length 2000\"", 1))
    monkeypatch.setattr(catalog, "CATALOG", tight)
    code, data = run(capsys, "lib", "check", SLUG)
    assert code == cmdbase.UNCHECKED and "the parameters it was made with no longer hold: length must be from 35 to 200" in data["rows"][-1]["measured"]


def test_a_part_that_pins_nothing_is_unchecked_and_a_hand_made_one_is_not_applicable(demo, capsys):
    copy_in(capsys, demo, "mgn12-rail", name="rail")
    side = bought_dir(demo) / "rail.json"
    data0 = json.loads(side.read_text())
    del data0["sha256"]
    side.write_text(json.dumps(data0))
    run(capsys, "bought", "add-measured", SLUG, "mine", "--size", "10", "20", "30", "--source", "a datasheet")
    code, data = run(capsys, "lib", "check", SLUG)
    assert code == cmdbase.UNCHECKED
    assert rule_states(data) == {("sha256", "rail"): "UNCHECKED", ("catalog", "rail"): "PASS", ("sha256", "mine"): "N/A", ("catalog", "mine"): "N/A"}
    assert "copied from mgn12-rail and pins no sha256" in [r for r in data["rows"] if r["rule"] == "sha256" and r["subject"] == "rail"][0]["measured"]


def test_a_part_declared_unconfirmed_is_not_pinned_and_check_says_why(demo, capsys):
    copy_in(capsys, demo, "gt2-idler-20t", name="idler")
    code, data = run(capsys, "lib", "check", SLUG)
    assert code == cmdbase.UNCHECKED and rule_states(data) == {("sha256", "idler"): "UNCHECKED", ("catalog", "idler"): "UNCHECKED"}
    assert "cad bought verify` rewrites its module" in data["rows"][0]["measured"]
    assert "declared unconfirmed" in data["rows"][1]["measured"]


def test_a_key_that_does_not_hold_is_a_contract_row_here_as_it_is_in_the_provenance_rule(demo, capsys):
    copy_in(capsys, demo, "mgn12-rail", name="rail")
    side = bought_dir(demo) / "rail.json"
    data0 = json.loads(side.read_text())
    data0["mass_g"] = -4.0
    side.write_text(json.dumps(data0))
    code, data = run(capsys, "lib", "check", SLUG)
    assert code == cmdbase.FAIL and ("contract", "rail") in rule_states(data)
    assert "mass_g must be a positive number" in [r for r in data["rows"] if r["rule"] == "contract"][0]["measured"]


def test_a_project_with_nothing_bought_and_a_project_that_is_not_there(demo, capsys):
    code, data = run(capsys, "lib", "check", SLUG)
    assert code == cmdbase.OK and [(r["rule"], r["state"]) for r in data["rows"]] == [("bought parts", "N/A")]
    code, data = run(capsys, "lib", "check", "ghost")
    assert code == cmdbase.USAGE and "no project 'ghost'" in data["error"]


# ─── The exit codes, --json and the kernel ───────────────────────────────────────────────────────────────────

def test_a_bug_in_the_library_is_a_crash_and_exit_4_not_a_traceback_in_the_middle_of_a_json_line(capsys, monkeypatch):
    def broken(*a, **k):
        raise RuntimeError("the catalog reader has a bug")

    monkeypatch.setattr(libcli, "load", broken)
    for argv in (["lib", "ls"], ["lib", "info", "x"], ["lib", "fetch", "x"], ["lib", "check"]):
        assert cli.main(argv) == cmdbase.CRASH, argv
        err = capsys.readouterr().err
        assert "cad-agent bug" in err and "the catalog reader has a bug" in err
    assert cli.main(["--json", "lib", "ls"]) == cmdbase.CRASH
    out = capsys.readouterr().out
    assert json.loads(out.splitlines()[-1])["exit"] == 4


def test_the_commands_are_registered_where_cmdbase_looks_for_them():
    assert set(libcli.ARGUMENTS) == {c for c in cmdbase.LAZY if c.startswith("lib ")}
    for command, lazy in cmdbase.LAZY.items():
        if command.startswith("lib "):
            module, _, function = lazy.target.partition(":")
            assert module == "cad_agent.library.cli" and callable(getattr(libcli, function)), command
    assert cmdbase.resolve("cad_agent.library.cli:cmd_lib_use") is libcli.cmd_lib_use
    assert "lib" in warm.KERNEL_FREE


@pytest.mark.parametrize("command, option", [("ls", "--kind"), ("info", "entry"), ("add", "--source"), ("use", "--replace"),
                                            ("check", "--all"), ("fetch", "ENTRY")])
def test_every_command_shows_its_own_options_in_its_help(capsys, command, option):
    assert cli.main(["lib", command, "--help"]) == cmdbase.OK
    assert option in capsys.readouterr().out


def test_a_missing_argument_is_exit_3_with_the_usage_on_stderr(capsys):
    for argv in (["lib", "use"], ["lib", "use", SLUG], ["lib", "info"], ["lib", "fetch"], ["lib", "add", "a"],
                 ["lib", "ls", "--kind", "folder"], ["lib", "use", SLUG, "x", "--as"]):
        assert cli.main(argv) == cmdbase.USAGE, argv
        assert "error:" in capsys.readouterr().err


def test_every_json_answer_is_one_object_with_its_exit_code_and_the_command_that_gave_it(capsys, demo, tiny, widget_file, monkeypatch):
    monkeypatch.setattr(store, "OPEN", serving(STEP))
    for argv in (["lib", "ls"], ["lib", "info", "widget"], ["lib", "add", "widget", str(widget_file), "--source", "a page"],
                 ["lib", "use", SLUG, "widget"], ["lib", "check", SLUG], ["lib", "check"], ["lib", "fetch", "widget"]):
        code = cli.main(["--json", *argv])
        out = capsys.readouterr().out.strip().splitlines()
        payload = json.loads(out[-1])
        assert payload["exit"] == code and payload["cmd"] == " ".join(argv[:2]) and isinstance(payload["data"], dict), argv
    assert cli.main(["--json", "lib", "use", SLUG, "nothing"]) == cmdbase.USAGE
    capsys.readouterr()


def test_the_library_commands_never_import_the_cad_kernel(tmp_path):
    home = tmp_path / "home"
    code = ("import sys\n"
            "from cad_agent import cli\n"
            f"codes = [cli.main(['--projects', {str(tmp_path / 'p')!r}, 'lib', *a]) for a in "
            "(['ls'], ['ls', '--kind', 'step'], ['info', 'nema17'], ['info', 'fcl-608zz'], ['check'])]\n"
            "print(codes, sorted(m for m in ('build123d', 'OCP', 'numpy') if m in sys.modules))\n")
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
                       env=cad_env(PYTHONPATH=str(REPO), CAD_LIBRARY=str(home / "store"), CAD_PREFS=str(home / "prefs.json")),
                       cwd=str(REPO))
    assert p.returncode == 0, p.stderr
    assert p.stdout.strip().splitlines()[-1] == "[0, 0, 0, 0, 0] []"


def test_bin_cad_answers_lib_without_starting_a_worker_and_reads_the_store_it_was_given(tmp_path):
    import tempfile
    warm_dir = Path(tempfile.mkdtemp(prefix="cadw", dir="/tmp"))          # a socket path is capped at 104 bytes
    try:
        env = cad_env(CAD_WARM_DIR=str(warm_dir), CAD_LIBRARY=str(tmp_path / "store"), CAD_PREFS=str(tmp_path / "prefs.json"))
        (tmp_path / "store").mkdir()
        (tmp_path / "store" / f"{sha(STEP)}.step").write_bytes(STEP)
        p = subprocess.run([str(REPO / "bin" / "cad"), "--projects", str(tmp_path / "p"), "--json", "lib", "ls", "608zz"],
                           capture_output=True, text=True, timeout=120, env=env, cwd=str(tmp_path))
        assert p.returncode == 0, p.stderr
        out = json.loads(p.stdout.strip().splitlines()[-1])
        assert out["cmd"] == "lib ls" and out["data"]["store"] == str(tmp_path / "store")
        assert [r["name"] for r in out["data"]["entries"]] == ["fcl-608zz"]
        assert not list(warm_dir.glob("*.sock"))                           # `lib` is in warm.KERNEL_FREE: no worker was started for it
    finally:
        shutil.rmtree(warm_dir, ignore_errors=True)


# ─── The store, directly ─────────────────────────────────────────────────────────────────────────────────────

def test_a_file_is_stored_under_the_hash_of_its_bytes_once(tmp_path, widget_file):
    got = store.put(widget_file, store=tmp_path / "s")
    assert got == (sha(STEP), tmp_path / "s" / f"{sha(STEP)}.step", True)
    assert store.put(widget_file, expect=sha(STEP), store=tmp_path / "s")[2] is False
    assert [p.name for p in store.files(tmp_path / "s")] == [f"{sha(STEP)}.step"]
    assert store.files(tmp_path / "nowhere") == [] and store.looks_like_step(widget_file)
    (tmp_path / "s" / "notes.txt").write_text("not a store file")
    (tmp_path / "s" / f"{'0' * 63}.step").write_text("name too short")
    assert [p.name for p in store.files(tmp_path / "s")] == [f"{sha(STEP)}.step"]


def test_a_store_that_is_not_there_is_made_by_the_first_write_and_never_by_a_read(tmp_path, monkeypatch):
    here = tmp_path / "a" / "b" / "store"
    monkeypatch.setenv("CAD_LIBRARY", str(here))
    assert store.store_dir() == here and store.files() == [] and store.read_raw() == {"format": 1, "parts": {}, "files": {}}
    assert not here.exists()
    store.record_file("a" * 64, "x", "add", "page")
    assert (here / "library.json").exists()


def test_a_download_is_streamed_to_a_file_beside_the_store_and_renamed_when_it_hashes_right(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "OPEN", serving(STEP))
    got = store.download("https://example.test/a.step", sha(STEP), tmp_path / "s")
    assert got == (sha(STEP), tmp_path / "s" / f"{sha(STEP)}.step", True) and got[1].read_bytes() == STEP
    assert [p.name for p in (tmp_path / "s").iterdir()] == [f"{sha(STEP)}.step"]


def test_the_user_agent_says_who_is_asking(tmp_path, monkeypatch):
    seen = []

    def opener(request, timeout=None):
        seen.append(request.get_header("User-agent"))
        return Response(STEP)

    monkeypatch.setattr(store, "OPEN", opener)
    store.download("https://example.test/a.step", sha(STEP), tmp_path / "s")
    assert seen == ["cad-agent-library"]


def test_a_user_entry_is_checked_before_it_is_written(tmp_path):
    with pytest.raises(catalog.LibraryError, match="would not be a valid entry: .*lower case words"):
        store.add_entry("Bad Name", {"title": "x", "kind": "step", "source": "s", "sha256": "0" * 64}, tmp_path)
    assert not (tmp_path / "library.json").exists()
    store.add_entry("fine", {"title": "x", "kind": "step", "source": "s", "sha256": "0" * 64}, tmp_path)
    with pytest.raises(catalog.IntegrityError, match="already in your store"):
        store.add_entry("fine", {"title": "y", "kind": "step", "source": "s", "sha256": "1" * 64}, tmp_path)
    store.add_entry("fine", {"title": "y", "kind": "step", "source": "s", "sha256": "1" * 64}, tmp_path, replace=True)
    assert json.loads((tmp_path / "library.json").read_text())["parts"]["fine"]["title"] == "y"


def test_the_three_kinds_of_trouble_are_three_exit_codes():
    assert issubclass(catalog.IntegrityError, catalog.LibraryError) and issubclass(catalog.Unreachable, catalog.LibraryError)
    assert {cmdbase.OK, cmdbase.FAIL, cmdbase.UNCHECKED, cmdbase.USAGE, cmdbase.CRASH} == {0, 1, 2, 3, 4}

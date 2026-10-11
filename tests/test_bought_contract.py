"""What a bought part may declare beyond its source: mass, material, temperature, geometry, datum, hash.

The rules of step 6 read these keys (bodies.describe turns them into a BodyInfo), so a key that is
malformed must be a FAIL row and never a quietly different number, a mass or a temperature with no
source must not be used, and a pinned hash that no longer matches the file must fail the gate.
"""
import copy
import hashlib
import json
import textwrap
from pathlib import Path

import pytest
from build123d import Box, Pos, export_step

from cad_agent import bought as B
from cad_agent import placements, rules
from cad_agent import state as st
from cad_agent.geom import bbox
from cad_agent.registry import ProjectCtx
from cad_agent.runner import check_all

SLUG = "_test_contract"


@pytest.fixture()
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "ROOT", tmp_path)
    st.project_dir(SLUG, create=True)
    step = tmp_path / "vendor_widget.step"
    export_step(Box(10, 20, 30), str(step))
    return tmp_path, step


def sidecar(slug_dir, name, **keys):
    """Add keys to a bought part's sidecar (writing it if it has none)."""
    path = slug_dir / "bought" / f"{name}.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    data.update(keys)
    path.write_text(json.dumps(data))
    return path


def provenance_rows(tmp):
    return list(rules.provenance(ProjectCtx(slug=SLUG, dir=tmp / SLUG, parts={}, out_dir=tmp)))


def widget(project, **keys):
    tmp, step = project
    B.register_step(SLUG, "widget", str(step), source="vendor drawing", vendor="Example Co")
    if keys:
        sidecar(tmp / SLUG, "widget", **keys)
    return tmp / SLUG


GENERATOR = textwrap.dedent('''\
    """A rail, generated."""
    from build123d import Box

    VENDOR = "Example"
    PARAMS = {"length": 100.0, "width": 12.0}


    def build(length, width):
        return Box(length, width, 8)
''')


# ─── Reading the keys ────────────────────────────────────────────────────────

def test_a_part_that_declares_nothing_has_the_defaults_and_no_problems(project):
    widget(project)
    s = B.bought_spec(SLUG, "widget")
    assert (s.name, s.kind, s.file, s.source, s.vendor, s.verified) == (
        "widget", "STEP", "widget.step", "vendor drawing", "Example Co", True)
    assert (s.mass_g, s.mass_source, s.material, s.max_temp_c, s.max_temp_source) == (None,) * 5
    assert (s.geometry, s.datum, s.sha256, s.pn, s.licence, s.library, s.problems) == (
        "envelope", None, None, None, None, None, ())


def test_every_key_in_a_sidecar_is_read(project):
    widget(project, mass_g=12.5, mass_source="datasheet p.3", material="Aluminium", max_temp_c=120,
           max_temp_source="datasheet p.1", geometry="exact", pn="W-7", licence="CC0", library="mgn12",
           sha256="AB" * 32, datum={"move": [1, 2, 3], "turn": [0, 0, 90]})
    s = B.bought_spec(SLUG, "widget")
    assert (s.mass_g, s.mass_source, s.material) == (12.5, "datasheet p.3", "Aluminium")
    assert (s.max_temp_c, s.max_temp_source, s.geometry) == (120.0, "datasheet p.1", "exact")
    assert (s.pn, s.licence, s.library, s.sha256) == ("W-7", "CC0", "mgn12", "ab" * 32)
    assert s.datum == {"move": (1.0, 2.0, 3.0), "turn": (0.0, 0.0, 90.0)} and s.problems == ()
    assert json.loads(json.dumps(s.as_dict()))["datum"] == {"move": [1.0, 2.0, 3.0], "turn": [0.0, 0.0, 90.0]}


def test_a_module_declares_them_as_constants_and_they_win_over_its_sidecar(project):
    tmp, _ = project
    (tmp / SLUG / "bought").mkdir(exist_ok=True)
    (tmp / SLUG / "bought" / "rail.py").write_text(GENERATOR + 'SOURCE = "catalog p.9"\nMASS_G = 20.0\nMASS_SOURCE = "catalog p.9"\n')
    sidecar(tmp / SLUG, "rail", mass_g=99.0, mass_source="the sidecar", pn="R-1", geometry="exact")
    s = B.bought_spec(SLUG, "rail")
    assert (s.kind, s.file, s.mass_g, s.mass_source) == ("MEASURED", "rail.py", 20.0, "catalog p.9")
    assert (s.pn, s.geometry, s.vendor, s.source) == ("R-1", "exact", "Example", "catalog p.9")   # the sidecar fills the gaps


def test_a_generated_module_may_keep_its_whole_record_in_the_sidecar(project):
    tmp, _ = project
    (tmp / SLUG / "bought").mkdir(exist_ok=True)
    (tmp / SLUG / "bought" / "rail.py").write_text(GENERATOR.replace('VENDOR = "Example"\n', ""))
    sidecar(tmp / SLUG, "rail", source="library: mgn12 generator", vendor="HIWIN", verified=True)
    (row,) = B.list_bought(SLUG)
    assert (row["source"], row["vendor"], row["verified"]) == ("library: mgn12 generator", "HIWIN", True)
    assert B.load_bought(SLUG, "rail") is not None                       # no SOURCE constant, and it still loads
    with_nothing = tmp / SLUG / "bought" / "rail.json"
    with_nothing.unlink()
    with pytest.raises(B.MissingProvenance):
        B.load_bought(SLUG, "rail")


def test_list_bought_and_bought_info_have_the_keys_they_always_had(project):
    widget(project, mass_g=1.0, mass_source="x", geometry="exact", sha256="0" * 64)
    (row,) = B.list_bought(SLUG)
    assert set(row) == {"name", "kind", "file", "source", "vendor", "verified"}
    assert set(B.bought_info(SLUG, "widget")) == {"name", "kind", "source", "vendor", "verified",
                                                  "bbox_mm", "origin_mm", "volume_cm3"}


def test_a_part_that_is_not_there_is_a_file_not_found(project):
    with pytest.raises(FileNotFoundError, match="register_step"):
        B.bought_spec(SLUG, "ghost")


def test_a_module_that_will_not_load_is_a_spec_not_an_exception(project):
    tmp, _ = project
    (tmp / SLUG / "bought").mkdir(exist_ok=True)
    (tmp / SLUG / "bought" / "bad.py").write_text("def build(:\n")
    s = B.bought_spec(SLUG, "bad")
    assert s.verified is False and s.source.startswith("cannot load:") and s.problems == ()


# ─── What does not hold ──────────────────────────────────────────────────────

@pytest.mark.parametrize("keys, fault", [
    ({"mass_g": 12.5}, "mass_g is declared without a mass_source"),
    ({"mass_g": -3, "mass_source": "x"}, "mass_g must be a positive number"),
    ({"mass_g": "heavy", "mass_source": "x"}, "mass_g must be a positive number"),
    ({"mass_g": True, "mass_source": "x"}, "mass_g must be a positive number"),
    ({"max_temp_c": 85}, "max_temp_c is declared without a max_temp_source"),
    ({"max_temp_c": "hot", "max_temp_source": "x"}, "max_temp_c must be a temperature"),
    ({"max_temp_c": -300, "max_temp_source": "x"}, "max_temp_c must be a temperature"),
    ({"geometry": "solid"}, "geometry must be one of exact, envelope"),
    ({"datum": [1, 2, 3]}, "datum must be {move, turn}"),
    ({"datum": {"shift": [0, 0, 1]}}, "datum has unknown key shift"),
    ({"datum": {"move": [1, 2]}}, "datum move must be three numbers"),
    ({"sha256": "abc"}, "sha256 must be 64 hexadecimal characters"),
    ({"sha256": 12}, "sha256 must be 64 hexadecimal characters"),
    ({"material": 7}, "material must be text"),
    ({"pn": ["a"]}, "pn must be text"),
])
def test_a_key_that_does_not_hold_is_a_fault_and_the_value_is_not_used(project, keys, fault):
    tmp = widget(project, **keys)
    s = B.bought_spec(SLUG, "widget")
    assert len(s.problems) == 1 and fault in s.problems[0]
    assert s.mass_g is None and s.max_temp_c is None and s.geometry == "envelope"
    assert s.datum is None and s.sha256 is None and s.material is None and s.pn is None
    (contract,) = [r for r in provenance_rows(tmp.parent) if r.rule == "contract"]
    assert contract.state == "FAIL" and fault in contract.measured and contract.subject == "widget"


def test_a_datum_that_cannot_be_read_stops_the_part_loading_in_the_wrong_place(project):
    widget(project, datum={"move": [1, 2]})
    with pytest.raises(ValueError, match="datum move must be three numbers"):
        B.load_bought(SLUG, "widget")


def test_an_all_zero_datum_is_no_datum(project):
    widget(project, datum={"move": [0, 0, 0], "turn": [0, 0, 0]})
    assert B.bought_spec(SLUG, "widget").datum is None


# ─── The datum, the parameters and the tag ───────────────────────────────────

def test_the_datum_moves_the_part_into_its_own_frame(project):
    widget(project)
    plain = bbox(B.load_bought(SLUG, "widget"))
    sidecar(project[0] / SLUG, "widget", datum={"move": [5, -2, 1]})
    moved = bbox(B.load_bought(SLUG, "widget"))
    assert [moved[0][i] - plain[0][i] for i in range(3)] == pytest.approx([5, -2, 1], abs=1e-6)
    sidecar(project[0] / SLUG, "widget", datum={"turn": [0, 0, 90]})                  # a quarter turn about z: x and y swap
    turned = bbox(B.load_bought(SLUG, "widget"))
    assert [turned[1][i] - turned[0][i] for i in range(3)] == pytest.approx([20, 10, 30], abs=1e-6)
    sidecar(project[0] / SLUG, "widget", datum={"move": [100, 0, 0], "turn": [0, 0, 90]})      # turn, then move
    both = bbox(B.load_bought(SLUG, "widget"))
    assert both[0][0] == pytest.approx(100 - 10, abs=1e-6)
    assert B.bought_info(SLUG, "widget")["origin_mm"][0] == pytest.approx(90.0)


def test_bought_solid_passes_parameters_to_a_generator_and_refuses_what_it_does_not_take(project):
    tmp, step = project
    (tmp / SLUG / "bought").mkdir(exist_ok=True)
    (tmp / SLUG / "bought" / "rail.py").write_text(GENERATOR + 'SOURCE = "generator"\n')
    long_rail = st.bought_solid(SLUG, "rail", length=300)
    lo, hi = bbox(long_rail)
    assert hi[0] - lo[0] == pytest.approx(300) and hi[1] - lo[1] == pytest.approx(12)    # width kept its default
    lo, hi = bbox(st.bought_solid(SLUG, "rail"))
    assert hi[0] - lo[0] == pytest.approx(100)
    with pytest.raises(ValueError, match="no parameter height.*params: length, width"):
        st.bought_solid(SLUG, "rail", height=3)
    B.register_step(SLUG, "widget", str(step), source="vendor drawing")
    with pytest.raises(ValueError, match="STEP file, which takes no parameters"):
        st.bought_solid(SLUG, "widget", length=3)


def test_the_solid_carries_a_tag_that_survives_moves_and_copies(project):
    widget(project)
    solid = st.bought_solid(SLUG, "widget")
    assert B.tag_of(solid) == {"project": SLUG, "name": "widget"}
    for derived in (Pos(1, 2, 3) * solid, solid.moved(solid.location), copy.deepcopy(solid), copy.copy(solid)):
        assert B.tag_of(derived) == {"project": SLUG, "name": "widget"}
    moved = placements.apply({"w": solid}, {"w": {"move": (1.0, 0.0, 0.0), "turn": (0.0, 0.0, 0.0), "about": (0.0, 0.0, 0.0)}})
    assert B.tag_of(moved["w"]) == {"project": SLUG, "name": "widget"}
    assert B.tag_of(Box(1, 1, 1)) is None
    assert B.tag_of(solid + Box(1, 1, 1)) is None                        # a body made of two things is neither


# ─── The hash ────────────────────────────────────────────────────────────────

def test_a_pinned_hash_that_matches_is_a_pass_row(project):
    tmp = widget(project)
    digest = hashlib.sha256((tmp / "bought" / "widget.step").read_bytes()).hexdigest()
    sidecar(tmp, "widget", sha256=digest)
    rows = provenance_rows(tmp.parent)
    assert [(r.rule, r.state) for r in rows] == [("source", "PASS"), ("sha256", "PASS")]
    assert B.pin_status(SLUG, "widget") == (digest, digest)
    assert B.file_sha256(tmp / "bought" / "widget.step") == digest


def test_a_file_that_no_longer_hashes_to_its_pin_fails_the_gate(project):
    tmp = widget(project)
    digest = hashlib.sha256((tmp / "bought" / "widget.step").read_bytes()).hexdigest()
    sidecar(tmp, "widget", sha256=digest)
    (tmp / "bought" / "widget.step").write_bytes((tmp / "bought" / "widget.step").read_bytes() + b"\n")
    (row,) = [r for r in provenance_rows(tmp.parent) if r.rule == "sha256"]
    assert row.state == "FAIL" and digest[:16] in row.measured and "widget.step hashes to" in row.measured
    payload = check_all(SLUG, render_views=("iso",))
    assert payload["summary"]["ok"] is False
    assert any(r["rule"] == "sha256" and r["state"] == "FAIL" and r["check"] == "provenance" for r in payload["rows"])


def test_a_modules_hash_is_the_hash_of_its_source_and_a_pin_on_it_is_checked_too(project):
    tmp, _ = project
    (tmp / SLUG / "bought").mkdir(exist_ok=True)
    path = tmp / SLUG / "bought" / "rail.py"
    path.write_text(GENERATOR + 'SOURCE = "generator"\n')
    sidecar(tmp / SLUG, "rail", sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    assert [r.state for r in provenance_rows(tmp) if r.rule == "sha256"] == ["PASS"]
    path.write_text(path.read_text().replace("100.0", "101.0"))
    assert [r.state for r in provenance_rows(tmp) if r.rule == "sha256"] == ["FAIL"]


def test_a_part_that_pins_nothing_has_no_sha_row_and_old_projects_read_as_they_did(project):
    tmp = widget(project)
    assert [(r.rule, r.state) for r in provenance_rows(tmp.parent)] == [("source", "PASS")]
    assert B.pin_status(SLUG, "widget") is None


# ─── The store ───────────────────────────────────────────────────────────────

def test_the_library_is_the_users_store_unless_cad_library_names_another(monkeypatch, tmp_path):
    monkeypatch.delenv("CAD_LIBRARY", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert B.library_dir() == Path.home() / ".cad-agent" / "library"
    monkeypatch.setenv("CAD_LIBRARY", "~/vendor-steps")
    assert B.library_dir() == Path.home() / "vendor-steps"
    monkeypatch.setenv("CAD_LIBRARY", str(tmp_path / "elsewhere"))
    assert B.library_dir() == tmp_path / "elsewhere" and not B.library_dir().exists()      # read, never made here
    assert B.LIBRARY_ENV == "CAD_LIBRARY"

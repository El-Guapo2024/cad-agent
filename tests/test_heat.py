"""[[heat]]: every body in a hot zone is rated for it, and the service temperatures that rating comes from.

The rig is a hot plate on four standoffs over a base, the shape of the hotplate_standoffs task: the plate
is the source, the standoffs touch it, the base is 20 mm away. Each test writes a spec, loads the machine
the way a run does (bodies.py says what every body is) and reads back the rows `cad check` and `cad verify`
see. The numbers in materials.py were each read off the sheet they cite when they were put there; what
these tests hold is that the text of every source still says its number, and what that makes the rule do.
"""
import json
import re
import textwrap

import pytest
from build123d import Box, Cylinder, Pos, Rot, export_step

from cad_agent import materials
from cad_agent import state as st
from cad_agent.materials import MATERIALS, MAX_TEMP_BASES
from cad_agent.runner import check_all
from cad_agent.spec import check_spec

SLUG = "dock"
ZONE_NOTE = "a zone, not a thermal model"

STANDOFF = textwrap.dedent('''\
    """A standoff: a bar with one M3 bore."""
    from build123d import Cylinder

    MATERIAL = "MATERIAL_NAME"
    PROCESS = "cnc"
    MIN_FEATURE_MM = 3.3
    PARAMS = {"height": 20.0, "od": 10.0}


    def build(height, od):
        return Cylinder(od / 2.0, height) - Cylinder(1.7, height + 2.0)
''')

ASSEMBLY = textwrap.dedent('''\
    from build123d import Pos
    from cad_agent.state import build_part, bought_solid

    SLUG = "dock"
    CORNERS = [(-43, -43), (43, -43), (-43, 43), (43, 43)]
    ALLOW_CONTACT = {f"standoff_{i}|{p}" for i in range(1, 5) for p in ("hot_plate", "base_plate")}


    def parts():
        standoff, _ = build_part(SLUG, "standoff")
        out = {"base_plate": bought_solid(SLUG, "base_plate"), "hot_plate": Pos(0, 0, 20) * bought_solid(SLUG, "hot_plate")}
        for i, (x, y) in enumerate(CORNERS, 1):
            out[f"standoff_{i}"] = Pos(x, y, 10) * standoff
        return out
''')

SIDECAR = {"source": "the test rig, drawn here", "vendor": None, "verified": True}


@pytest.fixture()
def dock(tmp_path, monkeypatch):
    """A hot plate (z 20 to 30) on four polyimide standoffs over a base (z -6 to 0), as a project."""
    monkeypatch.setattr(st, "ROOT", tmp_path)
    d = st.project_dir(SLUG, create=True)
    standoff(d, "polyimide")
    export_step(Pos(0, 0, 5) * Box(100, 100, 10), str(d / "bought" / "hot_plate.step"))
    export_step(Pos(0, 0, -3) * Box(160, 160, 6), str(d / "bought" / "base_plate.step"))
    for name in ("hot_plate", "base_plate"):
        (d / "bought" / f"{name}.json").write_text(json.dumps(SIDECAR))
    (d / "assembly.py").write_text(ASSEMBLY)
    return d


def standoff(d, material):
    (d / "parts" / "standoff.py").write_text(STANDOFF.replace("MATERIAL_NAME", material))


def declare(d, name, **keys):
    """Add what a bought part declares to its sidecar."""
    side = json.loads((d / "bought" / f"{name}.json").read_text())
    (d / "bought" / f"{name}.json").write_text(json.dumps({**side, **keys}))


def rows(d, text):
    """The spec's rows for the rig as a run would load it."""
    (d / "spec.toml").write_text(text)
    with st.reusing_builds():
        machine = st.load_machine(SLUG)
    return list(check_spec(SLUG, machine.parts, machine=machine))


def heat(d, text):
    return {r.subject: r for r in rows(d, text) if r.rule == "spec/heat"}


PLATE_250 = '[[heat]]\nsource = "hot_plate"\ntemp_c = 250\nradius_mm = 15\n'
STANDOFFS = ["standoff_1", "standoff_2", "standoff_3", "standoff_4"]


# ─── The service temperatures ────────────────────────────────────────────────

def celsius(text):
    """Every temperature in C a sheet's text gives, both ends of a range among them."""
    out = []
    for lo, hi in re.findall(r"(\d+(?:\.\d+)?)(?:\s*-\s*(\d+(?:\.\d+)?))?\s*°C", text):
        out += [float(lo)] + ([float(hi)] if hi else [])
    return out


def slots():
    for name, material in MATERIALS.items():
        yield name, material["max_service_temp_c"]


def test_every_material_has_a_service_temperature_with_a_basis_and_a_sheet():
    for name, slot in slots():
        assert slot is not None, f"{name} has no maximum service temperature, so every rule that needs one is UNCHECKED"
        value, source, basis = slot
        assert isinstance(value, float) and -273.15 < value < 1000, name
        assert re.match(r"https://\S+: .+", source) and basis in MAX_TEMP_BASES, (name, slot)


def test_a_source_says_the_number_it_is_cited_for_and_the_kind_of_number_it_is():
    for name, (value, source, basis) in slots():
        url, what = source.split(": ", 1)
        assert value in celsius(what), (name, value, what)                 # the sheet's own text gives it, in C
        if basis == "HDT ISO 75-2 B":
            assert "0.45 MPa" in what and "ISO 75" in what, (name, what)    # method B is 0.45 MPa
        elif basis == "Tg":
            assert "glass transition" in what, (name, what)
        elif basis == "stated service limit":
            assert any(w in what for w in ("Maximum Temperature: Mechanical", "Max Operating Temp", "Temperature Index")), name
        else:
            pytest.fail(f"{name}: a basis with no check: {basis}")


def test_the_metals_are_one_kind_of_number_from_one_source_and_the_plastics_come_from_their_sheets():
    for name in ("aluminium", "steel", "stainless", "brass", "copper"):
        value, source, basis = MATERIALS[name]["max_service_temp_c"]
        assert source.startswith("https://www.makeitfrom.com/material-properties/") and basis == "stated service limit"
        assert "Maximum Temperature: Mechanical" in source, name
    for name in ("pla", "petg", "abs", "nylon", "acrylic", "fr4", "polyimide"):
        assert not MATERIALS[name]["max_service_temp_c"][1].startswith("https://www.makeitfrom.com/"), name


def test_the_plastics_order_themselves_as_they_do_in_the_world():
    t = {n: materials.prop(n, "max_service_temp_c").value for n in MATERIALS}
    assert t["pla"] < t["petg"] < t["abs"] < t["nylon"]                    # 55, 68, 99, 190 (HDT at 0.45 MPa)
    assert t["polyimide"] > t["nylon"] and t["fr4"] > t["abs"]
    assert t["pla"] == 55.0 and t["petg"] == 68.0 and t["abs"] == 99.0     # their sheets, to the digit


def test_what_clears_a_250_c_zone_is_steel_stainless_and_polyimide():
    # The hotplate_standoffs brief lists aluminium, brass and copper too; their handbook limits are 170, 120 and
    # 200 C, so a loaded part of any of them at a 250 C heater is what [[heat]] is there to refuse.
    clears = {n for n in MATERIALS if materials.prop(n, "max_service_temp_c").value >= 250}
    assert clears == {"steel", "stainless", "polyimide"}


def test_a_material_the_table_has_no_number_for_has_no_rating(monkeypatch):
    monkeypatch.setitem(MATERIALS["petg"], "max_service_temp_c", None)
    assert materials.prop("petg", "max_service_temp_c") is None


# ─── The rule: a hot plate on standoffs ──────────────────────────────────────

def test_pla_standoffs_under_a_250_c_plate_fail_and_say_what_they_are_rated_for(dock):
    standoff(dock, "pla")
    got = heat(dock, PLATE_250)
    assert sorted(got) == STANDOFFS                                       # the base is 20 mm away, outside 15 mm
    for r in got.values():
        assert r.state == "FAIL" and r.check == "" and r.source == "spec.toml [[heat]] #1"
        assert r.measured == "pla (HDT ISO 75-2 B) rated 55 C, 0.00 mm from hot_plate"
        assert r.limit == f">= 250 C, {ZONE_NOTE}"


def test_polyimide_stainless_and_steel_standoffs_pass_the_same_zone(dock):
    for material, rated, basis in (("polyimide", 360, "Tg"), ("stainless", 710, "stated service limit"),
                                   ("steel", 400, "stated service limit")):
        standoff(dock, material)
        got = heat(dock, PLATE_250)
        assert sorted(got) == STANDOFFS and {r.state for r in got.values()} == {"PASS"}, material
        assert got["standoff_1"].measured == f"{material} ({basis}) rated {rated} C, 0.00 mm from hot_plate"


def test_every_material_is_held_to_its_own_number_in_the_zone(dock):
    for material in MATERIALS:
        standoff(dock, material)
        want = materials.prop(material, "max_service_temp_c").value >= 250
        got = heat(dock, PLATE_250)
        assert {r.state for r in got.values()} == {"PASS" if want else "FAIL"}, material


def test_aluminium_passes_a_zone_it_is_rated_for_and_fails_the_one_it_is_not(dock):
    standoff(dock, "aluminium")
    cool = '[[heat]]\nsource = "hot_plate"\ntemp_c = 150\nradius_mm = 15\n'
    assert {r.state for r in heat(dock, cool).values()} == {"PASS"}
    assert {r.state for r in heat(dock, PLATE_250).values()} == {"FAIL"}
    assert heat(dock, PLATE_250)["standoff_2"].measured.startswith("aluminium (stated service limit) rated 170 C")


def test_the_rating_has_to_reach_the_zone_plus_the_margin(dock):
    zone = '[[heat]]\nsource = "hot_plate"\ntemp_c = 250\nradius_mm = 15\nmargin_c = {}\n'
    r = heat(dock, zone.format(110))["standoff_1"]                        # 360 C against 250 + 110: exactly enough
    assert r.state == "PASS" and r.limit == f">= 360 C (250 + 110 margin), {ZONE_NOTE}"
    r = heat(dock, zone.format(111))["standoff_1"]
    assert r.state == "FAIL" and r.limit.startswith(">= 361 C (250 + 111 margin)")
    assert heat(dock, zone.format(0))["standoff_1"].limit == f">= 250 C, {ZONE_NOTE}"


def test_the_source_is_exempt_and_everything_in_the_radius_is_judged(dock):
    got = heat(dock, '[[heat]]\nsource = "hot_plate"\ntemp_c = 250\nradius_mm = 25\n')
    assert "hot_plate" not in got and sorted(got) == ["base_plate"] + STANDOFFS
    # the base is 20.00 mm from the plate and is bought with no material and no rating: UNCHECKED, and why
    base = got["base_plate"]
    assert base.state == "UNCHECKED" and base.measured.startswith("no rated temperature: bought part 'base_plate' declares neither")
    assert base.measured.endswith("20.00 mm from hot_plate")
    assert {got[n].state for n in STANDOFFS} == {"PASS"}


def test_a_radius_the_gap_just_misses_and_one_it_just_reaches(dock):
    assert sorted(heat(dock, '[[heat]]\nsource = "hot_plate"\ntemp_c = 250\nradius_mm = 19.99\n')) == STANDOFFS
    assert "base_plate" in heat(dock, '[[heat]]\nsource = "hot_plate"\ntemp_c = 250\nradius_mm = 20\n')   # on the limit is in


def test_a_bought_body_is_rated_by_what_it_declares_before_its_material(dock):
    declare(dock, "base_plate", max_temp_c=300, max_temp_source="vendor drawing 4, operating range", material="pla")
    r = heat(dock, '[[heat]]\nsource = "hot_plate"\ntemp_c = 250\nradius_mm = 25\n')["base_plate"]
    assert r.state == "PASS" and r.measured == "declared 300 C (vendor drawing 4, operating range), 20.00 mm from hot_plate"
    declare(dock, "base_plate", max_temp_c=200)
    r = heat(dock, '[[heat]]\nsource = "hot_plate"\ntemp_c = 250\nradius_mm = 25\n')["base_plate"]
    assert r.state == "FAIL" and "declared 200 C" in r.measured


def test_a_bought_body_that_names_only_a_material_is_rated_by_the_table(dock):
    declare(dock, "base_plate", material="aluminium")
    r = heat(dock, '[[heat]]\nsource = "hot_plate"\ntemp_c = 150\nradius_mm = 25\n')["base_plate"]
    assert r.state == "PASS" and r.measured == "aluminium (stated service limit) rated 170 C, 20.00 mm from hot_plate"
    assert heat(dock, '[[heat]]\nsource = "hot_plate"\ntemp_c = 180\nradius_mm = 25\n')["base_plate"].state == "FAIL"


def test_a_point_is_a_zone_too_and_no_body_is_exempt_from_it(dock):
    got = heat(dock, '[[heat]]\nat = [0, 0, 25]\ntemp_c = 250\nradius_mm = 20\n')      # inside the plate; the base is 25 down
    assert sorted(got) == ["hot_plate"]                                                # the standoffs are 56 mm out
    assert got["hot_plate"].state == "UNCHECKED" and got["hot_plate"].measured.endswith("0.00 mm from (0, 0, 25)")
    got = heat(dock, '[[heat]]\nat = [46.5, 43, 10]\ntemp_c = 250\nradius_mm = 1\n')   # in the wall of standoff_4
    assert sorted(got) == ["standoff_4"] and got["standoff_4"].state == "PASS"
    got = heat(dock, '[[heat]]\nat = [46.5, 43, 10]\ntemp_c = 250\nradius_mm = 1\nmargin_c = 200\n')
    assert got["standoff_4"].state == "FAIL" and got["standoff_4"].limit == f">= 450 C (250 + 200 margin), {ZONE_NOTE}"
    got = heat(dock, '[[heat]]\nat = [43, 43, 10]\ntemp_c = 250\nradius_mm = 1\n')      # on the axis, in the bore: 1.7 mm off
    assert got.keys() == {"zone (43, 43, 10)"}


BAR = textwrap.dedent('''
    _parts = parts


    def parts():
        from build123d import Box, Pos, Rot
        out = _parts()
        out["bar"] = Pos(0, 0, 100) * Rot(0, 0, 45) * Box(100, 2, 2)      # along the diagonal y = x
        return out
''')


SUNK = textwrap.dedent('''
    _parts = parts


    def parts():
        from build123d import Box, Pos
        out = _parts()
        out["pin"] = Pos(0, 0, -3) * Box(4, 4, 2)                          # wholly inside the base plate
        return out
''')


def test_a_body_sunk_into_the_source_is_in_its_zone_though_no_surfaces_are_near(dock):
    (dock / "assembly.py").write_text(ASSEMBLY + SUNK)
    r = heat(dock, '[[heat]]\nsource = "base_plate"\ntemp_c = 250\nradius_mm = 1\n')["pin"]
    assert r.state == "UNCHECKED" and r.measured.endswith("0.00 mm from base_plate")   # the kernel says 2 mm, to the nearest face


def test_the_distance_is_the_exact_one_and_not_the_bounding_box(dock):
    (dock / "assembly.py").write_text(ASSEMBLY + BAR)
    # (36, -36) is inside the bar's bounding box and 50 mm from the bar
    assert "bar" not in heat(dock, '[[heat]]\nat = [36, -36, 100]\ntemp_c = 250\nradius_mm = 10\n')
    assert heat(dock, '[[heat]]\nat = [0, 0, 100]\ntemp_c = 250\nradius_mm = 1\n')["bar"].state == "UNCHECKED"   # on it


def test_a_zone_with_nothing_in_it_says_so(dock):
    got = heat(dock, '[[heat]]\nat = [500, 500, 500]\ntemp_c = 250\nradius_mm = 10\n')
    assert list(got) == ["zone (500, 500, 500)"]
    r = got["zone (500, 500, 500)"]
    assert r.state == "PASS" and r.measured == "no other body within 10 mm of (500, 500, 500) (6 checked)"
    assert heat(dock, '[[heat]]\nsource = "hot_plate"\ntemp_c = 250\nradius_mm = 0.5\n').keys() >= set(STANDOFFS)
    only = heat(dock, '[[heat]]\nsource = "base_plate"\ntemp_c = 100\nradius_mm = 5\n')       # only the standoffs touch it
    assert sorted(only) == STANDOFFS


# ─── clear ───────────────────────────────────────────────────────────────────

def test_a_body_listed_in_clear_must_stay_outside_whatever_it_is_rated(dock):
    declare(dock, "base_plate", max_temp_c=900, max_temp_source="a very hot base")
    far = heat(dock, PLATE_250 + 'clear = ["base_plate"]\n')
    assert far["base_plate"].state == "PASS" and far["base_plate"].measured == "20.00 mm from hot_plate, outside the 15 mm zone"
    assert far["base_plate"].limit == f"outside 15 mm of hot_plate, {ZONE_NOTE}"
    near = heat(dock, '[[heat]]\nsource = "hot_plate"\ntemp_c = 250\nradius_mm = 25\nclear = ["base_plate"]\n')
    assert near["base_plate"].state == "FAIL" and near["base_plate"].measured == "20.00 mm from hot_plate, inside the 25 mm zone"
    assert {near[n].state for n in STANDOFFS} == {"PASS"}                                # the others are still rated


def test_clear_all_asks_for_nothing_in_the_zone_and_the_rest_are_not_rated(dock):
    got = heat(dock, PLATE_250 + 'clear = "all"\n')
    assert {got[n].state for n in STANDOFFS} == {"FAIL"} and got["base_plate"].state == "PASS"
    assert "rated" not in got["standoff_1"].measured and "hot_plate" not in got


def test_an_entry_with_only_clear_bodies_outside_still_gets_its_zone_row(dock):
    got = heat(dock, '[[heat]]\nat = [500, 500, 500]\ntemp_c = 250\nradius_mm = 10\nclear = ["base_plate"]\n')
    assert sorted(got) == ["base_plate", "zone (500, 500, 500)"] and {r.state for r in got.values()} == {"PASS"}


# ─── Why a rating is missing ─────────────────────────────────────────────────

def test_a_body_with_no_rating_is_unchecked_and_says_why(dock, monkeypatch):
    (dock / "parts" / "standoff.py").write_text(STANDOFF.replace('MATERIAL = "MATERIAL_NAME"\n', ""))
    r = heat(dock, PLATE_250)["standoff_1"]
    assert r.state == "UNCHECKED" and "its part module 'standoff' declares no MATERIAL" in r.measured
    standoff(dock, "unobtainium")
    assert "material 'unobtainium' is not in materials.py" in heat(dock, PLATE_250)["standoff_1"].measured
    standoff(dock, "pla")
    monkeypatch.setitem(MATERIALS["pla"], "max_service_temp_c", None)
    r = heat(dock, PLATE_250)["standoff_1"]
    assert r.state == "UNCHECKED" and "materials.py has no maximum service temperature for pla" in r.measured


def test_a_stock_body_in_the_zone_is_unchecked(dock):
    (dock / "assembly.py").write_text(ASSEMBLY + textwrap.dedent('''
        _parts = parts

        def parts():
            from build123d import Box, Pos
            out = _parts()
            out["spacer"] = Pos(0, 0, 18) * Box(5, 5, 4)
            return out
    '''))
    r = heat(dock, PLATE_250)["spacer"]
    assert r.state == "UNCHECKED" and "assembly.py builds it itself, so it has no material and no rating" in r.measured


def test_a_bought_rating_with_no_source_is_not_used(dock):
    declare(dock, "base_plate", max_temp_c=300)
    r = heat(dock, '[[heat]]\nsource = "hot_plate"\ntemp_c = 250\nradius_mm = 25\n')["base_plate"]
    assert r.state == "UNCHECKED" and "max_temp_c is declared without a max_temp_source" in r.measured


# ─── An entry that cannot be used ────────────────────────────────────────────

@pytest.mark.parametrize("body, says", [
    ('source = "hot_plate"\nat = [0, 0, 0]\ntemp_c = 250\nradius_mm = 15\n', "takes `source` (a body) or `at` (a point), not both"),
    ('temp_c = 250\nradius_mm = 15\n', "is missing `source` (a body) or `at` (a point)"),
    ('source = "furnace"\ntemp_c = 250\nradius_mm = 15\n', "no body 'furnace' in the assembly (bodies: "),
    ('source = 7\ntemp_c = 250\nradius_mm = 15\n', "`source` must name a body"),
    ('source = "hot_plate"\nradius_mm = 15\n', "[[heat]] is missing `temp_c`"),
    ('source = "hot_plate"\ntemp_c = 250\n', "[[heat]] is missing `radius_mm`"),
    ('source = "hot_plate"\ntemp_c = "hot"\nradius_mm = 15\n', "temp_c must be a number, got 'hot'"),
    ('source = "hot_plate"\ntemp_c = true\nradius_mm = 15\n', "temp_c must be a number, got True"),
    ('source = "hot_plate"\ntemp_c = -300\nradius_mm = 15\n', "temp_c must be above absolute zero"),
    ('source = "hot_plate"\ntemp_c = 250\nradius_mm = -1\n', "radius_mm must be at least 0, got -1"),
    ('source = "hot_plate"\ntemp_c = 250\nradius_mm = 15\nmargin_c = -5\n', "margin_c must be at least 0, got -5"),
    ('source = "hot_plate"\ntemp_c = 250\nradius_mm = 15\nmargin = 20\n', "[[heat]] does not take margin (keys: source, at, temp_c, radius_mm, margin_c, clear)"),
    ('at = [0, 0]\ntemp_c = 250\nradius_mm = 15\n', "at must be [x, y, z]"),
    ('source = "hot_plate"\ntemp_c = 250\nradius_mm = 15\nclear = []\n', '`clear` must be a list of body names, or "all"'),
    ('source = "hot_plate"\ntemp_c = 250\nradius_mm = 15\nclear = ["ghost"]\n', "no body 'ghost' in the assembly"),
    ('source = "hot_plate"\ntemp_c = 250\nradius_mm = 15\nclear = ["hot_plate"]\n', "`clear` names the source itself"),
])
def test_an_entry_that_cannot_be_judged_is_one_unchecked_row_that_says_why(dock, body, says):
    got = rows(dock, "[[heat]]\n" + body)
    assert len(got) == 1
    assert (got[0].subject, got[0].rule, got[0].state) == ("[[heat]] #1", "spec/heat", "UNCHECKED")
    assert says in got[0].measured, got[0].measured


def test_each_entry_is_judged_on_its_own(dock):
    standoff(dock, "pla")
    got = rows(dock, PLATE_250 + '[[heat]]\nsource = "hot_plate"\ntemp_c = 40\nradius_mm = 15\n[[heat]]\ntemp_c = 1\n')
    states = [(r.source, r.state) for r in got if r.rule == "spec/heat"]
    assert states[:4] == [("spec.toml [[heat]] #1", "FAIL")] * 4
    assert states[4:8] == [("spec.toml [[heat]] #2", "PASS")] * 4              # 55 C holds a 40 C zone
    assert states[8] == ("spec.toml [[heat]] #3", "UNCHECKED") and len(states) == 9


def test_rows_come_after_the_sections_that_registered_before_it(dock):
    got = rows(dock, PLATE_250 + '[[mass]]\nbodies = ["standoff_1"]\nmax_g = 10\n[envelope]\nmax_mm = [200, 200, 100]\n')
    assert [r.rule for r in got if r.rule != "spec/heat"] == ["spec/envelope", "spec/mass"]
    assert [r.rule for r in got][-4:] == ["spec/heat"] * 4                      # heat is order 80, after mass at 70


# ─── In a run ────────────────────────────────────────────────────────────────

def test_a_run_reports_the_zone_through_the_spec_rule_and_the_gate_fails_on_pla(dock):
    standoff(dock, "pla")
    (dock / "spec.toml").write_text(PLATE_250)
    payload = check_all(SLUG, render_views=("iso",))
    heat_rows = [r for r in payload["rows"] if r["rule"] == "spec/heat"]
    assert [r["state"] for r in heat_rows] == ["FAIL"] * 4 and {r["check"] for r in heat_rows} == {"spec"}
    assert payload["summary"]["ok"] is False
    standoff(dock, "stainless")
    payload = check_all(SLUG, render_views=("iso",))
    assert [r["state"] for r in payload["rows"] if r["rule"] == "spec/heat"] == ["PASS"] * 4

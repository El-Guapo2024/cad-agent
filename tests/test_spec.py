"""spec.toml: every entry is checked, and anything that cannot be checked fails closed.

The geometry is built here: a top plate with M3 clearance holes sitting on a
base plate with M3 tap holes, and a block far off to one side. Each test writes
a spec and reads back the rows, the same rows `cad check` and `cad verify` see.
"""
import pytest
from build123d import Box, Cylinder, Pos

from cad_agent import spec as sp
from cad_agent import state as st
from cad_agent.parts import CLEARANCE_HOLE, TAP_DRILL

HOLES = [(-20.0, 0.0), (20.0, 0.0)]

TOP_PLATE = '''"""Top plate of the test rig."""
from build123d import Box, Cylinder, Pos

MATERIAL = "petg"
PROCESS = "fdm"
MIN_FEATURE_MM = 1.2
PARAMS = {}


def build():
    p = Box(60, 40, 4)
    for x in (-20, 20):
        p -= Pos(x, 0, 0) * Cylinder(1.7, 6)
    return p
'''


def plate(w, d, t, holes, dia):
    p = Box(w, d, t)
    for x, y in holes:
        p -= Pos(x, y, 0) * Cylinder(dia / 2, t + 2)
    return p


def bodies(shift=0.0, base_holes=HOLES, base_dia=TAP_DRILL["M3"]):
    # The base spans z -2.5..2.5; the top sits on it, z 2.5..6.5.
    top = Pos(0, 0, 4.5) * plate(60, 40, 4, [(x + shift, y) for x, y in HOLES],
                                 CLEARANCE_HOLE["M3"])
    return {"top": top, "base": plate(60, 40, 5, base_holes, base_dia),
            "far": Pos(200, 0, 10) * Box(10, 10, 20)}


@pytest.fixture()
def rig(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "ROOT", tmp_path)
    d = st.project_dir("rig", create=True)
    (d / "parts" / "top_plate.py").write_text(TOP_PLATE)
    return d


def check(rig, text, parts=None):
    (rig / "spec.toml").write_text(text)
    return list(sp.check_spec("rig", bodies() if parts is None else parts))


def by_rule(rows, rule):
    return [r for r in rows if r.rule == f"spec/{rule}"]


# ─── Fail closed ─────────────────────────────────────────────────────────────

def test_no_spec_is_unchecked(rig):
    rows = list(sp.check_spec("rig", bodies()))
    assert [(r.rule, r.state) for r in rows] == [("spec/present", "UNCHECKED")]


def test_a_spec_that_does_not_parse_is_unchecked(rig):
    rows = check(rig, "[envelope\nmax_mm = 1")
    assert rows[0].state == "UNCHECKED" and "does not parse" in rows[0].measured


def test_unknown_sections_and_empty_specs_are_unchecked(rig):
    rows = check(rig, "[colour]\nred = 1\n")
    assert {r.measured for r in rows} >= {"unknown section [colour]",
                                          "spec.toml states no requirement"}
    assert all(r.state == "UNCHECKED" for r in rows)


def test_one_broken_entry_does_not_hide_the_rest(rig):
    rows = check(rig, '[envelope]\nmax_mm = [300, 50, 30]\n\n'
                      '[[clearance]]\na = "top"\nb = "ghost"\nmin_mm = 1\n')
    assert by_rule(rows, "envelope")[0].state == "PASS"
    bad = by_rule(rows, "clearance")[0]
    assert bad.state == "UNCHECKED" and "ghost" in bad.measured and "far" in bad.measured


# ─── Envelope and clearance ──────────────────────────────────────────────────

def test_envelope_measures_the_whole_assembly(rig):
    ok = by_rule(check(rig, "[envelope]\nmax_mm = [300, 50, 30]\n"), "envelope")[0]
    assert ok.state == "PASS" and ok.measured.startswith("235.0 x 40.0 x 22.5 mm")
    tight = by_rule(check(rig, "[envelope]\nmax_mm = [200, 50, 30]\n"), "envelope")[0]
    assert tight.state == "FAIL" and "too big in x" in tight.measured


def test_clearance_gap_and_interference(rig):
    text = ('[[clearance]]\na = "top"\nb = "far"\nmin_mm = 5\n\n'
            '[[clearance]]\na = "top"\nb = "base"\nmin_mm = 1\n')
    far, touching = by_rule(check(rig, text), "clearance")
    assert far.state == "PASS"
    assert touching.state == "FAIL" and touching.measured.startswith("0.000 mm")
    parts = bodies() | {"lump": Box(5, 5, 5)}             # buried in the base
    inside = by_rule(check(rig, '[[clearance]]\na = "base"\nb = "lump"\nmin_mm = 1\n', parts),
                     "clearance")[0]
    assert inside.state == "FAIL" and "interfere" in inside.measured


# ─── Keep-outs ───────────────────────────────────────────────────────────────

CONE = 'tool = "laser_cone"\nparams = { focal_length = 100, field = 50, lens_dia = 20 }\nat = [0, 0, 10]\n'


def test_keepout_passes_bodies_outside_the_beam(rig):
    rows = by_rule(check(rig, f'[[keepout]]\n{CONE}clear = "all"\n'), "keepout")
    assert len(rows) == 3 and all(r.state == "PASS" for r in rows)


def test_keepout_fails_a_body_inside_the_beam(rig):
    parts = bodies() | {"clamp": Pos(0, 0, 50) * Box(5, 5, 5)}
    row = by_rule(check(rig, f'[[keepout]]\n{CONE}clear = ["clamp"]\n', parts), "keepout")[0]
    assert row.state == "FAIL" and "inside the laser_cone envelope" in row.measured


def test_keepout_with_an_unknown_tool_or_bad_params_is_unchecked(rig):
    wrench = check(rig, '[[keepout]]\ntool = "wrench"\nclear = "all"\n')
    assert wrench[0].state == "UNCHECKED" and "unknown tool" in wrench[0].measured
    short = check(rig, '[[keepout]]\ntool = "laser_cone"\nparams = { focal_length = 100 }\nclear = "all"\n')
    assert short[0].state == "UNCHECKED" and "params" in short[0].measured


# ─── Mass ────────────────────────────────────────────────────────────────────

def test_mass_budget_over_part_modules(rig):
    # 60 x 40 x 4 mm less two 3.4 mm holes, PETG at 1.27 g/cm^3: 12.10 g each.
    ok = by_rule(check(rig, '[[mass]]\nparts = { top_plate = 2 }\nmax_g = 30\n'), "mass")[0]
    assert ok.state == "PASS" and ok.measured.startswith("24.2 g")
    heavy = by_rule(check(rig, '[[mass]]\nparts = { top_plate = 2 }\nmax_g = 20\n'), "mass")[0]
    assert heavy.state == "FAIL"
    ghost = check(rig, '[[mass]]\nparts = { ghost = 1 }\nmax_g = 20\n')[0]
    assert ghost.state == "UNCHECKED" and "top_plate" in ghost.measured


# ─── Interfaces ──────────────────────────────────────────────────────────────

IFACE = '[[interface]]\na = "top"\nb = "base"\nfastener = "M3"\n'


def test_aligned_holes_of_the_right_sizes_pass(rig):
    rows = by_rule(check(rig, IFACE), "interface")
    assert len(rows) == 2 and all(r.state == "PASS" for r in rows)
    assert all("clearance over tap" in r.measured for r in rows)


def test_a_half_millimetre_offset_fails(rig):
    rows = by_rule(check(rig, IFACE, bodies(shift=0.5)), "interface")
    assert rows and all(r.state == "FAIL" and "offset 0.500" in r.measured for r in rows)


def test_a_missing_hole_fails(rig):
    rows = by_rule(check(rig, IFACE, bodies(base_holes=[HOLES[0]])), "interface")
    assert [r.state for r in rows] == ["PASS", "FAIL"]
    assert "no hole in base under it" in rows[1].measured


def test_holes_the_fastener_does_not_suit_fail(rig):
    rows = by_rule(check(rig, IFACE, bodies(base_dia=5.0)), "interface")
    assert rows and all(r.state == "FAIL" and "do not suit M3" in r.measured for r in rows)


def test_a_body_with_no_facing_hole_is_unchecked(rig):
    row = check(rig, '[[interface]]\na = "far"\nb = "base"\n')[0]
    assert row.state == "UNCHECKED" and "no hole in far points into base" in row.measured


def test_holes_are_told_from_bosses():
    boss_and_hole = Box(20, 20, 6) - Pos(5, 0, 0) * Cylinder(1.7, 6) + Pos(-5, 0, 5) * Cylinder(2, 4)
    found = sp.holes(boss_and_hole)
    assert [round(h["dia"], 2) for h in found] == [3.4]


# ─── Through the runner ──────────────────────────────────────────────────────

def test_check_all_runs_the_spec(rig):
    from cad_agent.runner import check_all
    (rig / "assembly.py").write_text(
        "from build123d import Pos\nfrom cad_agent.state import build_part\n\n"
        "def parts():\n    top, _ = build_part('rig', 'top_plate')\n    return {'top': top}\n")
    (rig / "spec.toml").write_text("[envelope]\nmax_mm = [70, 50, 10]\n")
    rows = [r for r in check_all("rig")["rows"] if r["check"] == "spec"]
    assert [(r["rule"], r["state"]) for r in rows] == [("spec/envelope", "PASS")]

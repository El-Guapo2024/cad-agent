"""spec.toml: every entry is checked, and anything that cannot be checked fails closed.

The geometry is built here: a top plate with M3 clearance holes sitting on a
base plate with M3 tap holes, and a block far off to one side. Each test writes
a spec and reads back the rows, the same rows `cad check` and `cad verify` see.
"""
import math

import pytest
from build123d import Axis, Box, Compound, Cylinder, Pos, Rot, Vector

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


def counterbored(w, d, t, holes, dia, bore=6.4, depth=2.0):
    """A plate whose holes widen to `bore` over the top `depth` mm."""
    p = plate(w, d, t, holes, dia)
    for x, y in holes:
        p -= Pos(x, y, t / 2 - depth / 2 + 0.5) * Cylinder(bore / 2, depth + 1)
    return p


def slot_tool(x, y, length, width, t, turn=0.0):
    """What cuts a slot: round ends `length` apart, centre to centre, and the box between."""
    r = width / 2
    cutter = (Pos(-length / 2, 0, 0) * Cylinder(r, t + 2) + Pos(length / 2, 0, 0) * Cylinder(r, t + 2)
              + Box(length, width, t + 2))
    return Pos(x, y, 0) * Rot(0, 0, turn) * cutter


def rounded_window(w, d, t, window_w, window_d, r):
    """A plate with a window through it, its four inside corners rounded to radius r."""
    p = Box(w, d, t) - Box(window_w, window_d, t + 2)
    corners = [e for e in p.edges().filter_by(Axis.Z)
               if abs(e.center().X) < window_w / 2 + 1 and abs(e.center().Y) < window_d / 2 + 1]
    return p.fillet(r, corners)


def split_faces(solid, degrees=100):
    """The same solid with every cylinder cut into pieces, the way some CAD programs export one."""
    from OCP.ShapeUpgrade import ShapeUpgrade_ShapeDivideAngle
    divide = ShapeUpgrade_ShapeDivideAngle(math.radians(degrees), solid.wrapped)
    divide.Perform()
    return Compound(divide.Result())


def with_top(top, base=None):
    """The rig's bodies with another top plate (built about its own centre) and maybe base."""
    return bodies() | {"top": Pos(0, 0, 4.5) * top} | ({"base": base} if base is not None else {})


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


def test_clearance_max_pins_a_gap_from_above(rig):
    # "touches" and "grips" are max_mm: the top plate sits on the base, 0 mm apart.
    on = by_rule(check(rig, '[[clearance]]\na = "top"\nb = "base"\nmax_mm = 0.2\n'), "clearance")[0]
    assert on.state == "PASS" and on.limit == "<= 0.2 mm"
    far = by_rule(check(rig, '[[clearance]]\na = "top"\nb = "far"\nmax_mm = 100\n'), "clearance")[0]
    assert far.state == "FAIL" and far.measured.startswith("165.000 mm, too far")
    band = ('[[clearance]]\na = "top"\nb = "far"\nmin_mm = 1\nmax_mm = 200\n\n'
            '[[clearance]]\na = "top"\nb = "base"\nmin_mm = 1\nmax_mm = 200\n')
    fits, close = by_rule(check(rig, band), "clearance")
    assert fits.state == "PASS" and fits.limit == ">= 1 mm, <= 200 mm"
    assert close.state == "FAIL" and close.measured == "0.000 mm, too close"


def test_overlap_fails_a_max_only_clearance_too(rig):
    parts = bodies() | {"lump": Box(5, 5, 5)}             # buried in the base
    row = by_rule(check(rig, '[[clearance]]\na = "base"\nb = "lump"\nmax_mm = 5\n', parts),
                  "clearance")[0]
    assert row.state == "FAIL" and "interfere" in row.measured and row.limit == "<= 5 mm"


def test_a_clearance_without_a_bound_or_with_crossed_bounds_is_unchecked(rig):
    bare = check(rig, '[[clearance]]\na = "top"\nb = "far"\n')[0]
    assert bare.state == "UNCHECKED" and "min_mm` and/or `max_mm" in bare.measured
    crossed = check(rig, '[[clearance]]\na = "top"\nb = "far"\nmin_mm = 5\nmax_mm = 1\n')[0]
    assert crossed.state == "UNCHECKED" and "above max_mm" in crossed.measured


# ─── Size and position: pinning a given body ─────────────────────────────────

def test_size_holds_a_body_to_its_bounding_box(rig):
    ok = by_rule(check(rig, '[[size]]\nbody = "far"\nmin_mm = [9.9, 9.9, 19.9]\n'
                            'max_mm = [10.1, 10.1, 20.1]\n'), "size")[0]
    assert ok.state == "PASS" and ok.subject == "far" and ok.measured == "10.0 x 10.0 x 20.0 mm"
    big = by_rule(check(rig, '[[size]]\nbody = "far"\nmax_mm = [10, 10, 15]\n'), "size")[0]
    assert big.state == "FAIL" and "too big in z" in big.measured and big.limit == "<= 10 x 10 x 15 mm"
    small = by_rule(check(rig, '[[size]]\nbody = "far"\nmin_mm = [12, 10, 20]\n'), "size")[0]
    assert small.state == "FAIL" and "too small in x" in small.measured
    assert small.limit == ">= 12 x 10 x 20 mm"


def test_a_size_with_no_bound_no_body_or_a_bad_vector_is_unchecked(rig):
    none = check(rig, '[[size]]\nbody = "far"\n')[0]
    assert none.state == "UNCHECKED" and "min_mm` and/or `max_mm" in none.measured
    ghost = check(rig, '[[size]]\nbody = "ghost"\nmax_mm = [1, 1, 1]\n')[0]
    assert ghost.state == "UNCHECKED" and "ghost" in ghost.measured
    flat = check(rig, '[[size]]\nbody = "far"\nmax_mm = [10, 10]\n')[0]
    assert flat.state == "UNCHECKED" and "[x, y, z]" in flat.measured
    nameless = check(rig, '[[size]]\nmax_mm = [1, 1, 1]\n')[0]
    assert nameless.state == "UNCHECKED" and "missing `body`" in nameless.measured


def test_position_measures_the_center_and_the_offset(rig):
    ok = by_rule(check(rig, '[[position]]\nbody = "far"\ncenter_mm = [200, 0, 10]\n'), "position")[0]
    assert ok.state == "PASS" and ok.measured == "center (200.00, 0.00, 10.00) mm, offset 0.000 mm"
    assert ok.limit == "center (200, 0, 10) mm within 0.1 mm"
    moved = by_rule(check(rig, '[[position]]\nbody = "far"\ncenter_mm = [200, 0, 10.5]\n'),
                    "position")[0]
    assert moved.state == "FAIL" and "offset 0.500 mm" in moved.measured and "dz -0.50" in moved.measured
    loose = by_rule(check(rig, '[[position]]\nbody = "far"\ncenter_mm = [200, 0, 10.5]\n'
                               'tol_mm = 0.6\n'), "position")[0]
    assert loose.state == "PASS"


def test_position_is_the_distance_not_the_worst_axis(rig):
    # 0.08 off in x and y is 0.113 mm away: past the default 0.1 mm.
    row = by_rule(check(rig, '[[position]]\nbody = "far"\ncenter_mm = [200.08, 0.08, 10]\n'),
                  "position")[0]
    assert row.state == "FAIL" and "offset 0.113 mm" in row.measured


def test_a_position_that_cannot_be_checked_is_unchecked(rig):
    cases = ['[[position]]\nbody = "far"\n',                                # no center
             '[[position]]\ncenter_mm = [0, 0, 0]\n',                       # no body
             '[[position]]\nbody = "ghost"\ncenter_mm = [0, 0, 0]\n',       # no such body
             '[[position]]\nbody = "far"\ncenter_mm = [0, 0]\n',            # not x, y, z
             '[[position]]\nbody = "far"\ncenter_mm = [200, 0, 10]\ntol_mm = -1\n']
    for text in cases:
        row = by_rule(check(rig, text), "position")[0]
        assert row.state == "UNCHECKED", text


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


# ─── Interfaces: counterbores, slots and fillets are not extra holes ─────────

def test_a_counterbore_is_part_of_its_hole(rig):
    top = counterbored(60, 40, 4, HOLES, CLEARANCE_HOLE["M3"])
    rows = by_rule(check(rig, IFACE, with_top(top)), "interface")
    assert len(rows) == 2 and all(r.state == "PASS" for r in rows)          # two holes, not four
    assert all("clearance over tap" in r.measured for r in rows)           # the 3.4 bore is the size
    assert all("hole dia 3.40 (stepped, widest 6.40)" in r.measured for r in rows)
    found = sp.holes(top)
    assert [round(h["dia"], 2) for h in found] == [3.4, 3.4]
    assert [[round(b, 2) for b in h["bores"]] for h in found] == [[3.4, 6.4]] * 2


def test_the_mate_is_judged_by_its_smallest_bore_too(rig):
    base = counterbored(60, 40, 5, HOLES, TAP_DRILL["M3"], bore=6.0)       # the step faces the top plate
    rows = by_rule(check(rig, IFACE, with_top(plate(60, 40, 4, HOLES, CLEARANCE_HOLE["M3"]), base)),
                   "interface")
    assert len(rows) == 2 and all(r.state == "PASS" for r in rows)
    assert all("clearance over tap" in r.measured for r in rows)


def test_a_step_on_the_other_side_and_two_steps_are_still_one_hole():
    both = counterbored(60, 40, 6, [(5, 0)], 3.4) - Pos(5, 0, -2.5) * Cylinder(4.5, 2)
    (found,) = sp.holes(both)
    assert [round(b, 2) for b in found["bores"]] == [3.4, 6.4, 9.0] and round(found["dia"], 2) == 3.4


def test_a_hole_cut_into_pieces_is_one_hole_and_a_slot_one_slot():
    cut = split_faces(plate(60, 40, 4, [(5, 0)], 3.4))
    assert len(sp._concave_cylinders(cut)) == 4                             # four faces of a quarter turn
    assert [(h["kind"], round(h["dia"], 2)) for h in sp.holes(cut)] == [("hole", 3.4)]
    slotted = split_faces(Box(60, 40, 4) - slot_tool(0, 0, 12, 3.4, 4), degrees=50)
    assert len(sp._concave_cylinders(slotted)) > 2
    assert [(h["kind"], round(h["dia"], 2)) for h in sp.holes(slotted)] == [("slot", 3.4)]


def test_a_slot_passes_when_the_mate_is_on_its_centre_line(rig):
    top = Box(60, 40, 4) - slot_tool(0, 0, 10, 3.4, 4)
    for x in (0.0, 3.0, 5.0, -5.0):                                         # anywhere between its centres
        base = plate(60, 40, 5, [(x, 0)], TAP_DRILL["M3"])
        (row,) = by_rule(check(rig, IFACE, with_top(top, base)), "interface")
        assert row.state == "PASS", x
        assert "slot 3.40 wide, axes 10.0 apart" in row.measured and "clearance over tap" in row.measured


def test_a_slot_fails_when_the_mate_is_off_its_centre_line(rig):
    top = Box(60, 40, 4) - slot_tool(0, 0, 10, 3.4, 4)
    for hole, off in (((8.0, 0), 3.0), ((-9.0, 0), 4.0), ((0.0, 2.0), 2.0)):   # past an end, past the other, beside
        base = plate(60, 40, 5, [hole], TAP_DRILL["M3"])
        (row,) = by_rule(check(rig, IFACE, with_top(top, base)), "interface")
        assert row.state == "FAIL" and f"offset {off:.3f}" in row.measured, hole
    bare = by_rule(check(rig, IFACE, with_top(top, Box(60, 40, 5))), "interface")
    assert [r.state for r in bare] == ["FAIL"] and "no hole in base under it" in bare[0].measured


def test_a_slot_is_sized_by_its_width(rig):
    base = plate(60, 40, 5, [(0, 0)], TAP_DRILL["M3"])
    fits = by_rule(check(rig, IFACE, with_top(Box(60, 40, 4) - slot_tool(0, 0, 10, 3.4, 4), base)), "interface")
    wide = by_rule(check(rig, IFACE, with_top(Box(60, 40, 4) - slot_tool(0, 0, 10, 5.0, 4), base)), "interface")
    assert [r.state for r in fits] == ["PASS"] and [r.state for r in wide] == ["FAIL"]
    assert "5.00/2.50 do not suit M3" in wide[0].measured                  # its ends are no holes of their own


def test_a_slot_is_a_slot_however_it_is_turned(rig):
    top = Box(60, 40, 4) - slot_tool(0, 0, 10, 3.4, 4, turn=30)
    on = plate(60, 40, 5, [(4.0 * math.cos(math.radians(30)), 4.0 * math.sin(math.radians(30)))],
               TAP_DRILL["M3"])
    off = plate(60, 40, 5, [(4.0 * math.cos(math.radians(30)), -4.0 * math.sin(math.radians(30)))],
                TAP_DRILL["M3"])
    assert [r.state for r in by_rule(check(rig, IFACE, with_top(top, on)), "interface")] == ["PASS"]
    assert [r.state for r in by_rule(check(rig, IFACE, with_top(top, off)), "interface")] == ["FAIL"]


def test_a_hole_over_a_slot_is_judged_the_same_way(rig):
    top = plate(60, 40, 4, [(3.0, 0)], CLEARANCE_HOLE["M3"])
    base = Box(60, 40, 5) - slot_tool(0, 0, 10, 2.5, 5)
    (row,) = by_rule(check(rig, IFACE, with_top(top, base)), "interface")
    assert row.state == "PASS" and "to base slot 2.50 wide" in row.measured and "clearance over tap" in row.measured
    far = plate(60, 40, 4, [(9.0, 0)], CLEARANCE_HOLE["M3"])
    (row,) = by_rule(check(rig, IFACE, with_top(far, base)), "interface")
    assert row.state == "FAIL" and "offset 4.000" in row.measured


def test_slots_that_cross_pass_and_slots_that_miss_fail(rig):
    top = Box(60, 40, 4) - slot_tool(0, 0, 20, 3.4, 4)
    cross = Box(60, 40, 5) - slot_tool(0, 0, 20, 2.5, 5, turn=90)
    apart = Box(60, 40, 5) - slot_tool(0, 15, 20, 2.5, 5)
    assert [r.state for r in by_rule(check(rig, IFACE, with_top(top, cross)), "interface")] == ["PASS"]
    assert [r.state for r in by_rule(check(rig, IFACE, with_top(top, apart)), "interface")] == ["FAIL"]


def test_inside_corner_fillets_are_not_holes(rig):
    window = rounded_window(60, 40, 4, 20, 10, 2.0)
    assert sp.holes(window) == []                                           # four quarter turns
    top = window
    for x, y in HOLES:
        top = top - Pos(x, y, 0) * Cylinder(CLEARANCE_HOLE["M3"] / 2, 6)
    rows = by_rule(check(rig, IFACE, with_top(top)), "interface")
    assert len(rows) == 2 and all(r.state == "PASS" for r in rows)          # the corners have no mates, and need none
    only = check(rig, IFACE, with_top(window))[0]                          # but nothing else to judge
    assert only.state == "UNCHECKED" and "no hole in top points into base" in only.measured


def test_arcs_that_are_not_a_whole_turn_are_not_holes():
    # Two windows stacked on one block put their rounded corners on shared axes: two quarter
    # turns on each axis never add up to a bore. A notch cut into an edge is half a turn, alone.
    block = Box(40, 30, 12) - Pos(0, 0, 4) * Box(20, 10, 4) - Pos(0, 0, -4) * Box(20, 10, 4)
    corners = [e for e in block.edges().filter_by(Axis.Z) if abs(e.center().X) < 11 and abs(e.center().Y) < 6]
    assert len(sp._concave_cylinders(block.fillet(2.0, corners))) == 8
    assert sp.holes(block.fillet(2.0, corners)) == []
    assert sp.holes(Box(40, 30, 6) - Pos(19, 0, 0) * Cylinder(3, 8)) == []


def test_segments_are_measured_to_each_other():
    v, gap = Vector, sp._segment_gap
    assert gap(v(0, 0, 0), v(10, 0, 0), v(5, 3, 0), v(5, 3, 0)) == pytest.approx(3)       # a point beside
    assert gap(v(0, 0, 0), v(10, 0, 0), v(12, 0, 0), v(12, 0, 0)) == pytest.approx(2)     # a point past the end
    assert gap(v(0, 0, 0), v(10, 0, 0), v(5, -4, 0), v(5, 4, 0)) == pytest.approx(0)      # crossing
    assert gap(v(0, 0, 0), v(10, 0, 0), v(8, 5, 0), v(20, 5, 0)) == pytest.approx(5)       # parallel, overlapping
    assert gap(v(0, 0, 0), v(10, 0, 0), v(13, 4, 0), v(20, 4, 0)) == pytest.approx(5)      # parallel, past the end
    assert gap(v(1, 1, 0), v(1, 1, 0), v(4, 5, 0), v(4, 5, 0)) == pytest.approx(5)         # two points


# ─── Through the runner ──────────────────────────────────────────────────────

def test_check_all_runs_the_spec(rig):
    from cad_agent.runner import check_all
    (rig / "assembly.py").write_text(
        "from build123d import Pos\nfrom cad_agent.state import build_part\n\n"
        "def parts():\n    top, _ = build_part('rig', 'top_plate')\n    return {'top': top}\n")
    (rig / "spec.toml").write_text("[envelope]\nmax_mm = [70, 50, 10]\n")
    rows = [r for r in check_all("rig")["rows"] if r["check"] == "spec"]
    assert [(r["rule"], r["state"]) for r in rows] == [("spec/envelope", "PASS")]

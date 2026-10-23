"""[[holes]] counts a body's holes from its B-rep, and [[shaft_fit]] holds a shaft to its bores.

The rig is test_spec's: a top plate with two M3 clearance holes on a base with two M3 tap holes, and a
block off to one side. The shaft tests add a pin and a plate with a bore on its axis.
"""
from build123d import Axis, Box, Cylinder, Pos, Rot

from cad_agent.parts import CLEARANCE_HOLE
from test_spec import (bodies, by_rule, check, counterbored, plate, rig, rounded_window, slot_tool,  # noqa: F401
                       teardrop_tool)


def holes_row(rig, body, extra, parts=None):
    rows = by_rule(check(rig, f'[[holes]]\nbody = "{body}"\n{extra}', parts), "holes")
    assert len(rows) == 1
    return rows[0]


# ─── [[holes]] ───────────────────────────────────────────────────────────────

def test_holes_counts_and_sizes(rig):
    row = holes_row(rig, "top", 'count = 2\nmin_dia_mm = 3.2\nmax_dia_mm = 3.6\naxis = "z"\n')
    assert row.state == "PASS" and row.measured.startswith("2 holes dia 3.2 to 3.6 along z: hole dia 3.40")
    assert row.limit == "exactly 2 holes dia 3.2 to 3.6 along z"
    # The base's holes are tap size, none a clearance hole: a hole left out is caught on either body.
    none = holes_row(rig, "base", "count = 2\nmin_dia_mm = 3.2\nmax_dia_mm = 3.6\n")
    assert none.state == "FAIL" and none.measured == "0 holes dia 3.2 to 3.6"
    assert holes_row(rig, "base", "count = 2\n").state == "PASS"
    assert holes_row(rig, "base", "count = 3\n").state == "FAIL"
    assert holes_row(rig, "base", 'count = 2\naxis = "x"\n').state == "FAIL"
    assert holes_row(rig, "base", "count = 2\naxis = [0, 0, -1]\n").state == "PASS"
    assert holes_row(rig, "base", "min_count = 1\nmax_count = 2\n").state == "PASS"
    assert holes_row(rig, "far", "max_count = 0\n").state == "PASS"


def test_holes_reads_holes_as_interface_does(rig):
    # A counterbore is one hole of its through size, a teardrop is a hole, a slot counts only as a slot.
    top = counterbored(60, 40, 4, [(-20, 0), (20, 0)], CLEARANCE_HOLE["M3"])
    top -= Pos(0, 10, 0) * teardrop_tool(1.7, 4)
    top -= slot_tool(0, -10, 8, 3.4, 4)
    parts = bodies() | {"top": top}
    assert holes_row(rig, "top", "count = 3\nmax_dia_mm = 3.6\n", parts).state == "PASS"
    assert holes_row(rig, "top", 'count = 1\nkind = "slot"\n', parts).state == "PASS"
    assert holes_row(rig, "top", 'count = 4\nkind = "any"\n', parts).state == "PASS"
    # A window's rounded corners and a box's rounded edges are no holes.
    window = rounded_window(60, 40, 4, 20, 10, 2)
    rounded = Box(20, 20, 4)
    rounded = rounded.fillet(2, rounded.edges().filter_by(Axis.Z))
    assert holes_row(rig, "far", 'count = 0\nkind = "any"\n', bodies() | {"far": window}).state == "PASS"
    assert holes_row(rig, "far", 'count = 0\nkind = "any"\n', bodies() | {"far": rounded}).state == "PASS"


def test_holes_entries_it_cannot_read(rig):
    for extra, words in (("", "needs `count`"), ("count = 2\nmin_count = 1\n", "not both"),
                         ("count = -1\n", "whole number"), ("count = 2.5\n", "whole number"),
                         ("min_count = 3\nmax_count = 1\n", "above max_count"),
                         ("count = 1\nmin_dia_mm = 4\nmax_dia_mm = 3\n", "above max_dia_mm"),
                         ('count = 1\naxis = "w"\n', "`axis`"), ("count = 1\naxis = [0, 0, 0]\n", "`axis`"),
                         ('count = 1\nkind = "pocket"\n', "`kind`"), ("count = 1\ndia = 3\n", "does not take")):
        rows = by_rule(check(rig, f'[[holes]]\nbody = "top"\n{extra}'), "holes")
        assert [r.state for r in rows] == ["UNCHECKED"] and words in rows[0].measured, extra
    rows = by_rule(check(rig, '[[holes]]\nbody = "nope"\ncount = 1\n'), "holes")
    assert rows[0].state == "UNCHECKED" and "no body 'nope'" in rows[0].measured


# ─── [[shaft_fit]] ───────────────────────────────────────────────────────────

def fit_parts(bore=5.4, shaft=5.0, off=0.0, cheeks=1):
    """A pin along y through `cheeks` 4 mm plates, each with a bore on the pin's axis (x = 0, z = 30)."""
    pin = Pos(off, 0, 30) * Rot(90, 0, 0) * Cylinder(shaft / 2, 30)
    plates = None
    for i in range(cheeks):
        y = -8 + 16 * i if cheeks > 1 else 0
        p = Pos(0, y, 30) * Rot(90, 0, 0) * plate(20, 20, 4, [(0, 0)], bore)
        plates = p if plates is None else plates + p
    return bodies() | {"pin": pin, "cheek": plates}


def fit_rows(rig, extra, parts):
    return by_rule(check(rig, f'[[shaft_fit]]\nshaft = "pin"\nbore = "cheek"\n{extra}', parts), "shaft_fit")


def test_shaft_fit_is_the_difference_of_diameters(rig):
    (row,) = fit_rows(rig, "min_mm = 0.2\nmax_mm = 1.0\n", fit_parts())
    assert row.state == "PASS", row.measured
    assert row.measured.startswith("bore 5.400 at (0.0, 0.0, 30.0) over shaft 5.000: 0.400 mm (0.200 a side")
    assert row.limit == "bore minus shaft >= 0.2 mm, <= 1 mm, coaxial within 0.1 mm"
    (loose,) = fit_rows(rig, "max_mm = 0.2\n", fit_parts(bore=6.0))
    assert loose.state == "FAIL" and "too loose" in loose.measured
    (tight,) = fit_rows(rig, "min_mm = 0.2\n", fit_parts(bore=5.1))
    assert tight.state == "FAIL" and "too tight" in tight.measured
    # Every bore that holds the shaft is a row: both cheeks of a fork.
    assert [r.state for r in fit_rows(rig, "max_mm = 0.5\n", fit_parts(cheeks=2))] == ["PASS", "PASS"]
    # and [[holes]] counts them as two, though an interface reads one hole on one axis.
    fork = holes_row(rig, "cheek", 'count = 2\naxis = "y"\n', fit_parts(cheeks=2))
    assert fork.state == "PASS" and "(0.0, -8.0, 30.0)" in fork.measured and "(0.0, 8.0, 30.0)" in fork.measured


def test_shaft_fit_catches_the_loose_bore_a_clearance_passes(rig):
    # The pin rests on one side of a 6.0 bore: closest approach 0, which a "grips" clearance passes.
    parts = fit_parts(bore=6.0, off=0.5)
    grip = by_rule(check(rig, '[[clearance]]\na = "pin"\nb = "cheek"\nmax_mm = 0.1\n', parts), "clearance")[0]
    assert grip.state == "PASS"
    (row,) = fit_rows(rig, "max_mm = 0.2\ntol_mm = 0.6\n", parts)
    assert row.state == "FAIL" and "too loose" in row.measured and "axis offset 0.500" in row.measured


def test_shaft_fit_axis_and_missing_bore(rig):
    (off,) = fit_rows(rig, "max_mm = 1\n", fit_parts(off=0.15))
    assert off.state == "FAIL" and "axis 0.150 mm off" in off.measured
    (wall,) = fit_rows(rig, "max_mm = 1\ntol_mm = 1\n", fit_parts(bore=5.2, off=0.3))
    assert wall.state == "FAIL" and "into the wall" in wall.measured
    (press,) = fit_rows(rig, "min_mm = -0.05\nmax_mm = 0\n", fit_parts(bore=4.98))
    assert press.state == "PASS" and "interference" in press.measured
    parts = fit_parts() | {"cheek": Pos(0, 0, 30) * Box(20, 4, 20)}       # no bore at all
    (none,) = fit_rows(rig, "max_mm = 1\n", parts)
    assert none.state == "FAIL" and none.measured.startswith("no bore of cheek holds pin")


def test_shaft_fit_entries_it_cannot_read(rig):
    parts = fit_parts()
    for extra, words in (("", "needs `min_mm`"), ("min_mm = 1\nmax_mm = 0.5\n", "above max_mm"),
                         ("max_mm = 1\ntol_mm = -1\n", "negative"),
                         ('max_mm = 1\nclass = "H7"\n', "does not take")):
        rows = fit_rows(rig, extra, parts)
        assert [r.state for r in rows] == ["UNCHECKED"] and words in rows[0].measured, extra
    rows = by_rule(check(rig, '[[shaft_fit]]\nshaft = "far"\nbore = "cheek"\nmax_mm = 1\n', parts), "shaft_fit")
    assert rows[0].state == "UNCHECKED" and "no round shaft" in rows[0].measured

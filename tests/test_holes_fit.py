"""[[holes]] counts a body's holes from its B-rep, and [[shaft_fit]] holds a shaft to its bores.

The rig is test_spec's: a top plate with two M3 clearance holes on a base with two M3 tap holes, and a
block off to one side. The shaft tests add a pin and a plate with a bore on its axis.
"""
import math

from build123d import Axis, Box, Cone, Cylinder, Pos, Rot

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


def block_with(*cutters):
    """A 30 x 20 x 10 block, top face at z = 5, less the cutters."""
    b = Box(30, 20, 10)
    for c in cutters:
        b -= c
    return b


def bore(x, top, bottom, dia):
    """A cylinder that cuts a bore from z = bottom up, on past z = top."""
    return Pos(x, 0, (bottom + top + 1) / 2) * Cylinder(dia / 2, top + 1 - bottom)


def drill_point(x, at, dia, angle=118.0):
    """A drill point's cone, its shoulder at z = at, its tip below."""
    h = dia / 2 / math.tan(math.radians(angle / 2))
    return Pos(x, 0, at - h / 2) * Cone(0.001, dia / 2, h)


def test_holes_through_and_blind(rig):
    # Through, blind 6 deep flat, blind 4 deep with a drill point, all dia 4.
    part = block_with(bore(-10, 5, -6, 4), bore(0, 5, -1, 4), bore(10, 5, 1, 4), drill_point(10, 1, 4))
    parts = bodies() | {"far": part}
    row = holes_row(rig, "far", "count = 1\nthrough = true\n", parts)
    assert row.state == "PASS", row.measured
    assert row.measured.startswith("1 holes, through: hole dia 4.00, through at (-10.0, 0.0, 0.0)")
    assert "not counted, 2 of the size and axis" in row.measured and "blind 6.00 deep" in row.measured
    assert row.limit == "exactly 1 holes, through"
    assert holes_row(rig, "far", "count = 2\nthrough = false\n", parts).state == "PASS"
    assert holes_row(rig, "far", "count = 3\nthrough = true\n", parts).state == "FAIL"
    # The depth is to the shoulder, as FreeCAD's Depth: the drill point's cone is not counted.
    deep = holes_row(rig, "far", "count = 1\ndepth_mm = 6\n", parts)
    assert deep.state == "PASS" and deep.limit == "exactly 1 holes, blind 6 +-0.1 deep", deep.measured
    assert holes_row(rig, "far", "count = 1\ndepth_mm = 4\n", parts).state == "PASS"
    assert holes_row(rig, "far", "count = 1\ndepth_mm = 4.3\n", parts).state == "FAIL"
    assert holes_row(rig, "far", "count = 1\ndepth_mm = 4.3\ndepth_tol_mm = 0.5\n", parts).state == "PASS"
    # Without `through` or a depth, the row reads as it always did.
    assert holes_row(rig, "far", "count = 3\n", parts).measured.startswith("3 holes: hole dia 4.00 at")


def test_holes_through_and_blind_with_a_counterbore_or_countersink(rig):
    # A counterbored through hole, a blind counterbored hole 6 deep, a blind countersunk one 5 deep: all dia 3.4.
    sink = Pos(10, 0, 4.25) * Cone(1.45, 3.45, 2.0)         # 90 degrees, z 3.25 to 5.25: 6.4 across at the face
    part = block_with(bore(-10, 5, -6, 3.4), bore(-10, 5, 3, 6.4), bore(0, 5, -1, 3.4), bore(0, 5, 3, 6.4),
                      bore(10, 5, 0, 3.4), sink)
    parts = bodies() | {"far": part}
    assert holes_row(rig, "far", "count = 3\nmax_dia_mm = 3.6\n", parts).state == "PASS"
    through = holes_row(rig, "far", "count = 1\nthrough = true\nmax_dia_mm = 3.6\n", parts)
    assert through.state == "PASS" and "(-10.0, 0.0, 0.0)" in through.measured.split("not counted")[0]
    assert holes_row(rig, "far", "count = 2\nthrough = false\n", parts).state == "PASS"
    blind = holes_row(rig, "far", "count = 1\ndepth_mm = 6\n", parts)
    assert blind.state == "PASS" and "hole dia 3.40 (stepped, widest 6.40), blind 6.00 deep" in blind.measured
    sunk = holes_row(rig, "far", "count = 1\ndepth_mm = 5\n", parts)        # from the face, past the countersink
    assert sunk.state == "PASS", sunk.measured
    # A hole on its side opens on both faces, and both cheeks of a fork are through.
    assert holes_row(rig, "cheek", 'count = 2\naxis = "y"\nthrough = true\n', fit_parts(cheeks=2)).state == "PASS"


def test_holes_entries_it_cannot_read(rig):
    for extra, words in (("", "needs `count`"), ("count = 2\nmin_count = 1\n", "not both"),
                         ("count = -1\n", "whole number"), ("count = 2.5\n", "whole number"),
                         ("min_count = 3\nmax_count = 1\n", "above max_count"),
                         ("count = 1\nmin_dia_mm = 4\nmax_dia_mm = 3\n", "above max_dia_mm"),
                         ('count = 1\naxis = "w"\n', "`axis`"), ("count = 1\naxis = [0, 0, 0]\n", "`axis`"),
                         ('count = 1\nkind = "pocket"\n', "`kind`"), ("count = 1\ndia = 3\n", "does not take"),
                         ('count = 1\nthrough = "yes"\n', "true or false"),
                         ("count = 1\nthrough = true\ndepth_mm = 3\n", "does not go with"),
                         ("count = 1\ndepth_mm = 0\n", "above 0"), ("count = 1\ndepth_tol_mm = 1\n", "needs `depth_mm`"),
                         ("count = 1\ndepth_mm = 3\ndepth_tol_mm = -1\n", "negative"),
                         ('count = 1\nkind = "slot"\nthrough = true\n', "judge holes")):
        rows = by_rule(check(rig, f'[[holes]]\nbody = "top"\n{extra}'), "holes")
        assert [r.state for r in rows] == ["UNCHECKED"] and words in rows[0].measured, extra
    rows = by_rule(check(rig, '[[holes]]\nbody = "nope"\ncount = 1\n'), "holes")
    assert rows[0].state == "UNCHECKED" and "no body 'nope'" in rows[0].measured


# ─── [[shaft_fit]] ───────────────────────────────────────────────────────────

def fit_parts(bore=5.4, shaft=5.0, off=0.0, cheeks=1, width=20):
    """A pin along y through `cheeks` 4 mm plates, each with a bore on the pin's axis (x = 0, z = 30)."""
    pin = Pos(off, 0, 30) * Rot(90, 0, 0) * Cylinder(shaft / 2, 30)
    plates = None
    for i in range(cheeks):
        y = -8 + 16 * i if cheeks > 1 else 0
        p = Pos(0, y, 30) * Rot(90, 0, 0) * plate(width, width, 4, [(0, 0)], bore)
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


# ─── [[shaft_fit]] fit = "H7/g6" ─────────────────────────────────────────────

def test_shaft_fit_takes_an_iso_286_fit(rig):
    # 10 H7/g6: H7 0/+15, g6 -5/-14, so 0.005 to 0.029 mm.
    (row,) = fit_rows(rig, 'fit = "H7/g6"\n', fit_parts(bore=10.01, shaft=9.99))
    assert row.state == "PASS", row.measured
    assert row.limit == "H7/g6 at 10 mm: bore minus shaft >= 0.005 mm, <= 0.029 mm, coaxial within 0.1 mm"
    (loose,) = fit_rows(rig, 'fit = "H7/g6"\n', fit_parts(bore=10.02, shaft=9.98))
    assert loose.state == "FAIL" and "too loose" in loose.measured
    # A machined part drawn at nominal fails by design: the model is one size, and 0 is below 0.005.
    (drawn,) = fit_rows(rig, 'fit = "H7/g6"\n', fit_parts(bore=10.0, shaft=10.0))
    assert drawn.state == "FAIL" and "too tight" in drawn.measured
    # A press fit: 10 H7/s6 is -0.032 to -0.008.
    (press,) = fit_rows(rig, 'fit = "H7/s6"\n', fit_parts(bore=10.0, shaft=10.02))
    assert press.state == "PASS" and "interference" in press.measured, press.measured
    # 25 H7/g6 is 0.007 to 0.041 mm, and so is the shaft-basis G7/h6.
    for fit in ("H7/g6", "G7/h6"):
        (big,) = fit_rows(rig, f'fit = "{fit}"\n', fit_parts(bore=25.03, shaft=24.99, width=40))
        assert big.state == "PASS", big.measured
        assert big.limit.startswith(f"{fit} at 25 mm: bore minus shaft >= 0.007 mm, <= 0.041 mm")


def test_shaft_fit_nominal_size(rig):
    # 10 H11/c11 is 0.080 to 0.260; over 10, in 10 to 18, it is 0.095 to 0.315.
    parts = fit_parts(bore=10.04, shaft=9.95)
    assert fit_rows(rig, 'fit = "H11/c11"\n', parts)[0].state == "PASS"
    (over,) = fit_rows(rig, 'fit = "H11/c11"\nnominal_mm = 10.5\n', parts)
    assert over.state == "FAIL" and over.limit.startswith("H11/c11 at 10.5 mm: bore minus shaft >= 0.095 mm")


def test_shaft_fit_fits_it_cannot_read(rig):
    parts = fit_parts()
    for extra, words in (('fit = "H7/g6"\nmin_mm = 0\n', "not both"), ('fit = "H7/g6"\nmax_mm = 1\n', "not both"),
                         ('fit = "H7"\n', "a hole class over a shaft class"), ('fit = "H7/q6"\n', "shaft class 'q6'"),
                         ('fit = "H5/g6"\n', "hole class 'H5'"), ('fit = "h7/G6"\n', "hole class 'h7'"),
                         ("max_mm = 1\nnominal_mm = 5\n", "there is no `fit`"),
                         ('fit = "H7/g6"\nnominal_mm = 600\n', "up to 500 mm")):
        rows = fit_rows(rig, extra, parts)
        assert [r.state for r in rows] == ["UNCHECKED"] and words in rows[0].measured, (extra, rows[0].measured)


# What published reproductions of ISO 286-2 give, upper and lower deviation in micrometres, for the size ranges
# over 3 to 6, 6 to 10, 10 to 18, 18 to 30, 30 to 50, 50 to 80, 80 to 120, 120 to 180, 180 to 250, 250 to 315
# and 315 to 400 (cadforum.cz/en/tolerance.asp, simplybearings.co.uk's ISO 286 page).
SIZES = (5, 8, 14, 24, 40, 65, 100, 150, 200, 280, 350)
PUBLISHED = {
    "H7": ((12, 0), (15, 0), (18, 0), (21, 0), (25, 0), (30, 0), (35, 0), (40, 0), (46, 0), (52, 0), (57, 0)),
    "H11": ((75, 0), (90, 0), (110, 0), (130, 0), (160, 0), (190, 0), (220, 0), (250, 0), (290, 0), (320, 0),
            (360, 0)),
    "F7": ((22, 10), (28, 13), (34, 16), (41, 20), (50, 25), (60, 30), (71, 36), (83, 43), (96, 50), (108, 56),
           (119, 62)),
    "G7": ((16, 4), (20, 5), (24, 6), (28, 7), (34, 9), (40, 10), (47, 12), (54, 14), (61, 15), (69, 17), (75, 18)),
    "JS7": ((6, -6), (7.5, -7.5), (9, -9), (10.5, -10.5), (12.5, -12.5), (15, -15), (17.5, -17.5), (20, -20),
            (23, -23), (26, -26), (28.5, -28.5)),
    "K7": ((3, -9), (5, -10), (6, -12), (6, -15), (7, -18), (9, -21), (10, -25), (12, -28), (13, -33), (16, -36),
           (17, -40)),
    "N7": ((-4, -16), (-4, -19), (-5, -23), (-7, -28), (-8, -33), (-9, -39), (-10, -45), (-12, -52), (-14, -60),
           (-14, -66), (-16, -73)),
    "P7": ((-8, -20), (-9, -24), (-11, -29), (-14, -35), (-17, -42), (-21, -51), (-24, -59), (-28, -68), (-33, -79),
           (-36, -88), (-41, -98)),
    "g6": ((-4, -12), (-5, -14), (-6, -17), (-7, -20), (-9, -25), (-10, -29), (-12, -34), (-14, -39), (-15, -44),
           (-17, -49), (-18, -54)),
    "f7": ((-10, -22), (-13, -28), (-16, -34), (-20, -41), (-25, -50), (-30, -60), (-36, -71), (-43, -83),
           (-50, -96), (-56, -108), (-62, -119)),
    "h11": ((0, -75), (0, -90), (0, -110), (0, -130), (0, -160), (0, -190), (0, -220), (0, -250), (0, -290),
            (0, -320), (0, -360)),
    "js6": ((4, -4), (4.5, -4.5), (5.5, -5.5), (6.5, -6.5), (8, -8), (9.5, -9.5), (11, -11), (12.5, -12.5),
            (14.5, -14.5), (16, -16), (18, -18)),
    "k6": ((9, 1), (10, 1), (12, 1), (15, 2), (18, 2), (21, 2), (25, 3), (28, 3), (33, 4), (36, 4), (40, 4)),
    "p6": ((20, 12), (24, 15), (29, 18), (35, 22), (42, 26), (51, 32), (59, 37), (68, 43), (79, 50), (88, 56),
           (98, 62)),
}


def test_iso_286_against_published_tables():
    from cad_agent import iso286
    for cls, rows in PUBLISHED.items():
        look = iso286.hole if cls[0].isupper() else iso286.shaft
        for size, (upper, lower) in zip(SIZES, rows):
            assert look(cls, size) == (lower, upper), (cls, size)
    # Miki Pulley's JIS B 0401 excerpt (ISO 286's numbers): d9 and e8, 10 to 50 and 400 to 500.
    for size, d9, e8 in ((14, (-93, -50), (-59, -32)), (24, (-117, -65), (-73, -40)), (40, (-142, -80), (-89, -50)),
                         (450, (-385, -230), (-232, -135))):
        assert iso286.shaft("d9", size) == d9 and iso286.shaft("e8", size) == e8, size
    # The usual examples, and the classes taken from Table 2 alone.
    assert iso286.hole("H7", 10) == (0, 15) and iso286.shaft("g6", 10) == (-14, -5)
    assert iso286.clearance("H7/g6", 25) == (0.007, 0.041)
    assert iso286.clearance("H11/c11", 40) == (0.12, 0.44)
    assert iso286.shaft("s6", 20) == (35, 48) and iso286.shaft("s6", 450) == (232, 272)
    assert iso286.hole("K7", 2) == (-10, 0) and iso286.hole("N7", 2) == (-14, -4)       # no delta up to 3 mm

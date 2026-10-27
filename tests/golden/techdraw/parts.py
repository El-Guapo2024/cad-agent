"""The parts tests/golden/techdraw draws, built with build123d and written as BREP (prep.py), so FreeCAD (make.py)
and cad_agent (tests/test_techdraw_golden.py) project exactly the same shape."""
from build123d import (Axis, Box, Cylinder, Locations, Plane, Pos, Rot, chamfer, extrude, fillet, Polyline,
                       make_face, revolve, Sketch, Rectangle, Circle)


def plate():
    """A 40 x 30 x 10 plate, a 8 mm hole through it off centre and one vertical edge rounded r 3."""
    b = Box(40, 30, 10)
    b = b - Pos(10, 8, 0) * Cylinder(4, 20)
    return fillet(b.edges().filter_by(Axis.Z)[0:1], 3)


def bracket():
    """An L bracket: a 50 x 30 x 6 foot, a 6 x 30 x 40 wall, a hole in each, the foot's outer edge chamfered 5."""
    foot = Box(50, 30, 6, align=None)
    wall = Pos(-22, 0, 23) * Box(6, 30, 40)
    b = Pos(0, 0, 3) * foot + wall
    b = b - Pos(10, 0, 0) * Cylinder(5, 30)
    b = b - Pos(-22, 0, 30) * (Rot(0, 90, 0) * Cylinder(4, 20))
    e = b.edges().filter_by(Axis.Y).sort_by(Axis.X)[-1:]
    return chamfer(e, 5)


def shaft():
    """A stepped shaft along z: r 10 for 30 mm, then r 6 for 20 mm, with a 2 mm chamfer at the thin end."""
    a = Cylinder(10, 30, align=None)
    a = a + Pos(0, 0, 30) * Cylinder(6, 20, align=None)
    top = a.edges().sort_by(Axis.Z)[-1:]
    return chamfer(top, 2)


def big():
    """A 600 x 400 x 20 plate: too big for an A4 at 1:1 (ScaleType Automatic scales it)."""
    return Box(600, 400, 20) - Cylinder(50, 40)


PARTS = {"plate": plate, "bracket": bracket, "shaft": shaft, "big": big}

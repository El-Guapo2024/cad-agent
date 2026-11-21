"""Belt pulley: the flanged roller the flat belt wraps, at each rail's ends (idlers on axles) and below
the exit end (the drive pulley, hex-bored, sliding along the shared hex shaft so the moving rail stays driven).

Axis along y. One flange, on its +y side (away from the rail): the rail's face is the other. The flange stays
under the belt's outer face so it never reaches the board. y 0 at the core's rail-side face. Machined aluminium.
"""
from build123d import Cylinder, Pos, Rot
from build123d import RegularPolygon, extrude, Plane

MATERIAL = "aluminium"
PROCESS = "cnc"
MIN_FEATURE_MM = 1.0

PARAMS = {"dia": 20.0, "width": 4.2, "flange": 1.0, "flange_dia": 22.6, "bore": 6.0, "hex": 0.0}


def build(dia, width, flange, flange_dia, bore, hex):
    p = Pos(0, width / 2.0, 0) * Rot(90, 0, 0) * Cylinder(dia / 2.0, width)
    p += Pos(0, width + flange / 2.0, 0) * Rot(90, 0, 0) * Cylinder(flange_dia / 2.0, flange)
    span = width + flange
    if hex:
        p -= extrude(Plane.XZ.offset(-span - 1) * RegularPolygon(hex / 2.0, 6, major_radius=False), span + 2)
    else:
        p -= Pos(0, span / 2.0, 0) * Rot(90, 0, 0) * Cylinder(bore / 2.0, span + 2)
    return p

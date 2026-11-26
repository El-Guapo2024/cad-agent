"""Trapezoidal nut for the Tr12 x 3 screw, held in the rear carriage's bore: what turns the screws into the rail's
travel. Axis along y; y 0 at one end, running +y. UNVERIFIED envelope (a plain 22 OD body, flange not drawn).
"""
from build123d import Cylinder, Pos, Rot

SOURCE = "class-typical Tr12 x 3 nut body, OD 22; flange and fixing holes to the maker's drawing"
VENDOR = None
VERIFIED = False

PARAMS = {"od": 22.0, "bore": 12.0, "length": 40.0}


def build(od, bore, length):
    return Pos(0, length / 2.0, 0) * Rot(90, 0, 0) * (Cylinder(od / 2.0, length) - Cylinder(bore / 2.0, length + 2))

"""608 deep-groove ball bearing (8 x 22 x 7), one in each rail's drive bore, carrying the drive shaft. Axis along y,
centred. 8 x 22 x 7 is the ISO 15 boundary size of a 608; UNVERIFIED until a maker's datasheet is named.
"""
from build123d import Cylinder, Rot

SOURCE = "608 boundary dimensions 8 x 22 x 7 (ISO 15 dimension series 02); maker not chosen"
VENDOR = None
VERIFIED = False

PARAMS = {"bore": 8.0, "od": 22.0, "width": 7.0}


def build(bore, od, width):
    return Rot(90, 0, 0) * (Cylinder(od / 2.0, width) - Cylinder(bore / 2.0, width + 2))

"""Ball bearing with a hex bore, for the 10 mm hex drive shaft: one in each rail's drive bore. The rear rail's slides
along the shaft with the rail. Axis along y, centred. UNVERIFIED: an OD 22 x 7 envelope (608 size class) with a
10 mm hex bore; confirm a maker stocks that bore, or switch to a round shaft with a feather key.
"""
from build123d import Cylinder, RegularPolygon, Plane, Rot, extrude

SOURCE = "608-class envelope (22 x 7) with a 10 mm A/F hex bore; maker not found yet"
VENDOR = None
VERIFIED = False

PARAMS = {"od": 22.0, "width": 7.0, "hex": 10.2}


def build(od, width, hex):
    b = Rot(90, 0, 0) * Cylinder(od / 2.0, width)
    return b - extrude(Plane.XZ.offset(-width / 2.0 - 1) * RegularPolygon(hex / 2.0, 6, major_radius=False),
                       width + 2)

"""Dock: the rail that guides boards onto the hot plate, bolted to the base 3 mm off the plate's long edge.

AISI 304 stainless, because the plate runs at 250 C and the rail stands inside the 15 mm zone: `cad tables materials`
gives stainless a stated service limit of 710 C, where aluminium has 170 C and every printable plastic is far under
250. It is also the least conductive of the metals on that list, so little of the plate's heat goes down the two bolts
into the base. Milled from flat bar, with two M4 clearance holes on the base plate's tapped pattern.
"""
from build123d import Box, Cylinder, Pos
from cad_agent.parts import CLEARANCE_HOLE

MATERIAL = "stainless"
PROCESS = "cnc"             # milled from flat bar
MIN_FEATURE_MM = 4.7        # the wall between a bolt hole and the rail's long edge: (14 - 4.5) / 2 = 4.75
EXPECT_FEATURES = 2         # the two bolt holes

PARAMS = {
    "length": 100.0,        # along the plate's long edge, past both bolts
    "width": 14.0,          # across: the bolt line is its middle
    "height": 12.0,         # 2 mm taller than the plate, so it guides a board lying on the plate's top face
    "pitch": 80.0,          # the base plate's holes are 80 mm apart along x
    "screw": "M4",
}


def build(length, width, height, pitch, screw):
    body = Box(length, width, height)
    for sx in (-1, 1):
        body -= Pos(sx * pitch / 2.0, 0, 0) * Cylinder(CLEARANCE_HOLE[screw] / 2.0, height + 2.0)
    return body

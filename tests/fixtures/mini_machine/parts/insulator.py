"""Insulator: a 6 mm polyimide plate between the hot plate and the base.

Polyimide (Vespel SP-1 and its relatives): `cad tables materials` gives it 360 C (the low end of its glass transition),
which clears the hot plate's 180 C with the 20 C of headroom the spec asks for, and it conducts far less than the steel
under it. 90 x 70 mm, 5 mm larger than the plate each way, so the plate sits inside its edge. Plain: nothing is
screwed through it, the plate's own screws are not modelled.
"""
from build123d import Box

MATERIAL = "polyimide"
PROCESS = "cnc"             # machined from plate
MIN_FEATURE_MM = 6.0
EXPECT_FEATURES = 0

PARAMS = {
    "width": 90.0,          # x
    "length": 70.0,         # y
    "thickness": 6.0,       # z
}


def build(width, length, thickness):
    return Box(width, length, thickness)

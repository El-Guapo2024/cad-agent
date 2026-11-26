"""F-theta lens under the galvo head: PLACEHOLDER. A 110 x 110 mm field lens (f about 160) is the usual choice and
gives the ~20-30 um spot; its working distance (lens bottom to the board) is the number that sets the Z height,
taken here as 185 mm until the chosen lens's datasheet gives it. Frame: its top at z 0 (the galvo's bottom), axis z.
"""
from build123d import Cylinder, Pos

SOURCE = "placeholder: 110 x 110 field f-theta lens, 355 nm, OD 80, length 45; working distance ~185 (UNVERIFIED)"
VENDOR = None
VERIFIED = False
MATERIAL = "aluminium"

PARAMS = {"od": 80.0, "length": 45.0}


def build(od, length):
    return Pos(0, 0, -length / 2.0) * Cylinder(od / 2.0, length)

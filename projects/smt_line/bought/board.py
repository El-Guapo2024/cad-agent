"""A bare board on the line: FR4 1.6, 150 long (along the line) by 140 across. The conveyor's guides are set 143.9
apart for it, and its edges ride the two 4 mm belts (Rapid Star carries boards up to 165 wide).

Frame: its bottom at z 0, its front-left corner at x 0, y 0.
"""
from build123d import Box, Pos

SOURCE = "FR4 copper clad 1.6 mm, cut to 150 x 140"
VENDOR = None
VERIFIED = True
MATERIAL = "fr4"

PARAMS = {"length": 150.0, "width": 140.0, "thick": 1.6}


def build(length, width, thick):
    return Pos(length / 2, width / 2, thick / 2) * Box(length, width, thick)

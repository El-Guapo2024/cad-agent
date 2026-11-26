"""The 2-layer board blank: FR4 1.6, 1 oz both sides, 150 x 150, in the carrier's pocket, with the two 3.0 flip
holes the laser drills on side A (at +-69, through the carrier's flip holes). Frame: its bottom at z 0,
centred in x and y.
"""
from build123d import Box, Cylinder, Pos

SOURCE = "FR4 copper clad 1.6 mm, 1 oz double-sided, 150 x 150 (cut to size)"
VENDOR = None
VERIFIED = True
MATERIAL = "fr4"

PARAMS = {"size": 150.0, "thick": 1.6, "flip_hole": 3.0, "flip_x": 69.0}


def build(size, thick, flip_hole, flip_x):
    b = Pos(0, 0, thick / 2.0) * Box(size, size, thick)
    for sx in (-1, 1):
        b -= Pos(sx * flip_x, 0, thick / 2.0) * Cylinder(flip_hole / 2.0, thick + 2)
    return b

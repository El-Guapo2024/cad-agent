"""Enclosure front: 3 mm aluminium over the frame's front, with the door's opening.

Lies in x-z (y is its thickness; `thickness` is its height). The door closes the opening from outside.
"""
from build123d import Box, Cylinder, Pos, Rot

MATERIAL = "aluminium"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 3.0
EXPECT_FEATURES = 1

PARAMS = {'size_x': 880.0, 'size_y': 3.0, 'thickness': 631.0, 'open_w': 700.0, 'open_h': 500.0, 'open_z': 25.0}


def build(size_x, size_y, thickness, open_w, open_h, open_z):
    p = Box(size_x, size_y, thickness)
    p -= Pos(0, 0, open_z) * Box(open_w, size_y + 2, open_h)
    return p

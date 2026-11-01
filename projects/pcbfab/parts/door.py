"""Enclosure door: 3 mm aluminium over the front's opening, 20 mm over it all round, with the window's opening.

Hinged on its left edge (hinges not drawn); two interlock switches on its right edge cut the laser and the UV lamp
in hardware when it opens. Lies in x-z.
"""
from build123d import Box, Cylinder, Pos, Rot

MATERIAL = "aluminium"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 3.0
EXPECT_FEATURES = 1

PARAMS = {'size_x': 740.0, 'size_y': 3.0, 'thickness': 585.0, 'win_w': 260.0, 'win_h': 260.0, 'win_z': 20.0}


def build(size_x, size_y, thickness, win_w, win_h, win_z):
    p = Box(size_x, size_y, thickness)
    p -= Pos(0, 0, win_z) * Box(win_w, size_y + 2, win_h)
    return p

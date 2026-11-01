"""Enclosure top: 3 mm aluminium over the frame's top rails.

Closes the roof over the bridge and the gantry.
"""
from build123d import Box, Cylinder, Pos, Rot

MATERIAL = "aluminium"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 3.0
EXPECT_FEATURES = 0

PARAMS = {'size_x': 880.0, 'size_y': 1085.0, 'thickness': 3.0}


def build(size_x, size_y, thickness):
    p = Box(size_x, size_y, thickness)
    return p

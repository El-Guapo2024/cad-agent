"""Enclosure side: 3 mm aluminium over one side of the frame.

Lies in y-z (x is its thickness).
"""
from build123d import Box, Cylinder, Pos, Rot

MATERIAL = "aluminium"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 3.0
EXPECT_FEATURES = 0

PARAMS = {'size_x': 3.0, 'size_y': 1085.0, 'thickness': 676.0}


def build(size_x, size_y, thickness):
    p = Box(size_x, size_y, thickness)
    return p

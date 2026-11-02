"""Tool ear: the aluminium block on the tool carrier's left end that carries the lift screw's Tr8x8 nut.
"""
from build123d import Box, Cylinder, Pos

MATERIAL = "aluminium"
PROCESS = "cnc"
MIN_FEATURE_MM = 1.0
EXPECT_FEATURES = 1

PARAMS = {"size_x": 22.0, "size_y": 32.0, "height": 12.0, "bore": 11.0, "bore_y": -5.0}


def build(size_x, size_y, height, bore, bore_y):
    return Box(size_x, size_y, height) - Pos(0, bore_y, 0) * Cylinder(bore / 2.0, height + 2)

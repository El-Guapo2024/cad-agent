"""Trunnion block: the stainless block screwed to each end of the flip frame that holds its 8 mm shaft on the flip
axis (the board's mid-plane). A blind 8 mm bore along y; the shaft is pressed and pinned in it.
"""
from build123d import Box, Cylinder, Pos, Rot

MATERIAL = "stainless"
PROCESS = "cnc"
MIN_FEATURE_MM = 1.0
EXPECT_FEATURES = 0

PARAMS = {"size_x": 24.0, "size_y": 10.0, "size_z": 20.0, "bore": 8.0, "depth": 8.0}


def build(size_x, size_y, size_z, bore, depth):
    b = Box(size_x, size_y, size_z)
    return b - Pos(0, size_y / 2.0 - depth / 2.0 + 0.5, 0) * Rot(90, 0, 0) * Cylinder(bore / 2.0, depth + 1)

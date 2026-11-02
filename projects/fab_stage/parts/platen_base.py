"""Platen base: the bottom layer of the platen, closing the plenum; the mica heater is clamped flat under it by the
clamp plate. The Selco cut-out is clamped to its -x side. 4 mm 6061, laser cut.
"""
from build123d import Box

MATERIAL = "aluminium"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 1.0
EXPECT_FEATURES = 0

PARAMS = {"size_x": 215.0, "size_y": 295.0, "thick": 4.0}


def build(size_x, size_y, thick):
    return Box(size_x, size_y, thick)

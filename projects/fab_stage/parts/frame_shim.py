"""Flip frame shim: the 1.6 stainless middle layer of the flip frame, its window the board itself (0.2 slip), so the
two rings either side grip the board's edge (frame_ring.py).
"""
from build123d import Box

MATERIAL = "stainless"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 1.0
EXPECT_FEATURES = 1

PARAMS = {"outer_x": 257.4, "outer_y": 333.4, "window_x": 229.4, "window_y": 305.4, "thick": 1.6}


def build(outer_x, outer_y, window_x, window_y, thick):
    return Box(outer_x, outer_y, thick) - Box(window_x, window_y, thick + 2)

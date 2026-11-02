"""Shaft: an 8 mm ground steel trunnion shaft, the flip frame's axle, pressed into its trunnion block and turning in a
608 bearing in the post. Along z, centred.
"""
from build123d import Cylinder

MATERIAL = "steel"
PROCESS = "cnc"
MIN_FEATURE_MM = 1.0
EXPECT_FEATURES = 0

PARAMS = {"dia": 8.0, "length": 50.0}


def build(dia, length):
    return Cylinder(dia / 2.0, length)

"""Lift arm: the stainless block joining a carrier tab to its MGN12 carriage (or to its T8 nut) on the post.

A plate standing in the XZ plane, bolted to the carriage's top face (M3, 20 x 15 apart for MGN12H) at its top and to
the carrier's tab at its foot. The nut version carries the Tr8x8 flange nut on a shelf.
"""
from build123d import Box, Pos

MATERIAL = "stainless"
PROCESS = "cnc"
MIN_FEATURE_MM = 1.0
EXPECT_FEATURES = 0

PARAMS = {"width": 27.0, "thick": 6.0, "height": 45.4}


def build(width, thick, height):
    return Box(width, thick, height)

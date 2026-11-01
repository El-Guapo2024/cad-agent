"""Galvo spacer: an aluminium block between the laser plate and the galvo, putting the galvo's input on the beam axis.

13.8 = half the UV source's height (121.2) minus half the galvo's (93.6), both hanging from the same plate.
"""
from build123d import Box

MATERIAL = "aluminium"
PROCESS = "cnc"
MIN_FEATURE_MM = 3.0

PARAMS = {"size_x": 118.5, "size_y": 96.5, "thickness": 13.8}


def build(size_x, size_y, thickness):
    return Box(size_x, size_y, thickness)

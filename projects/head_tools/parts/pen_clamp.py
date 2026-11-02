"""Pen clamp: the aluminium block that holds an eco-PEN to the tool carrier, bored to its 33 mm body
(a slit and a screw close it; not drawn).
"""
from build123d import Box, Cylinder, Pos

MATERIAL = "aluminium"
PROCESS = "cnc"
MIN_FEATURE_MM = 1.0
EXPECT_FEATURES = 1

PARAMS = {"size_x": 42.0, "size_y": 42.0, "height": 20.0, "bore": 33.2, "bore_y": 0.0}


def build(size_x, size_y, height, bore, bore_y):
    return Box(size_x, size_y, height) - Pos(0, bore_y, 0) * Cylinder(bore / 2.0, height + 2)

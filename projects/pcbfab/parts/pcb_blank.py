"""The work: a 130 x 110 x 1.6 FR4 copper-clad blank with two 3.1 mm tooling holes, the 100 x 100 board inside it.

Modelled so the gates can hold the tool heads clear of it and the pins in its holes.
"""
from build123d import Box, Cylinder, Pos

MATERIAL = "fr4"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 3.0
EXPECT_FEATURES = 2

PARAMS = {"size_x": 130.0, "size_y": 110.0, "thickness": 1.6, "hole_pitch": 116.0, "hole": 3.1}


def build(size_x, size_y, thickness, hole_pitch, hole):
    b = Box(size_x, size_y, thickness)
    for sx in (-1, 1):
        b -= Pos(sx * hole_pitch / 2.0, 0, 0) * Cylinder(hole / 2.0, thickness + 2)
    return b

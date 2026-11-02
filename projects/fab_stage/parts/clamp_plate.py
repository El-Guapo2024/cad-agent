"""Clamp plate: the stainless sheet that presses the mica heater flat to the platen's underside and seals the plenum.

Four M3 screws into the platen's corners; the heater lies between. 3 mm stainless, laser cut.
"""
from build123d import Box, Cylinder, Pos

MATERIAL = "stainless"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 1.0
EXPECT_FEATURES = 4

PARAMS = {"size_x": 215.0, "size_y": 295.0, "thick": 3.0, "inset": 5.0, "hole": 3.4}


def build(size_x, size_y, thick, inset, hole):
    b = Box(size_x, size_y, thick)
    for sx in (-1, 1):
        for sy in (-1, 1):
            b -= Pos(sx * (size_x / 2.0 - inset), sy * (size_y / 2.0 - inset), 0) * Cylinder(hole / 2.0, thick + 2)
    return b

"""Nut block: the stainless block on the carrier's -x tab that carries the Tr8x8 flange nut on its top.

Bored 11 through for the screw and counterbored 22 from below to 6 under its top, so when the platen is down the
screw's coupling (20 OD, above the X plate) stands inside it. The nut's flange screws to the top, its body up.
"""
from build123d import Box, Cylinder, Pos

MATERIAL = "stainless"
PROCESS = "cnc"
MIN_FEATURE_MM = 1.0
EXPECT_FEATURES = 1

PARAMS = {"size_x": 30.0, "size_y": 25.0, "height": 32.0, "bore": 11.0, "counterbore": 22.0, "top": 6.0}


def build(size_x, size_y, height, bore, counterbore, top):
    b = Box(size_x, size_y, height) - Cylinder(bore / 2.0, height + 2)
    return b - Pos(0, 0, -top / 2.0 - 0.5) * Cylinder(counterbore / 2.0, height - top + 1)

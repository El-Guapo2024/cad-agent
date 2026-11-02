"""Nut bracket: the machined aluminium block a ball screw's nut flange bolts to, hung under its carriage plate; bored
25 for the nut's 24 body. The X and the Y one are alike.
"""
from build123d import Box, Cylinder, Pos, Rot

MATERIAL = "aluminium"
PROCESS = "cnc"
MIN_FEATURE_MM = 1.0

EXPECT_FEATURES = 1

PARAMS = {"size_x": 20.0, "size_y": 50.0, "size_z": 30.0, "bore": 25.0, "bore_z": -1.0}


def build(size_x, size_y, size_z, bore, bore_z):
    return Box(size_x, size_y, size_z) - Pos(0, 0, bore_z) * Rot(0, 90, 0) * Cylinder(bore / 2.0, size_x + 2)

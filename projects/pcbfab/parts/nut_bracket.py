"""Nut bracket: the machined aluminium block the tool carriage's ball nut flange bolts to, bolted to the back of the
tool plate; bored 25 for the nut's 24 body, the bore off centre toward the beam so the block reaches the plate.
"""
from build123d import Box, Cylinder, Pos, Rot

MATERIAL = "aluminium"
PROCESS = "cnc"
MIN_FEATURE_MM = 1.0

EXPECT_FEATURES = 1

PARAMS = {"size_x": 20.0, "size_y": 58.0, "size_z": 38.0, "bore": 25.0, "bore_y": -4.0, "bore_z": 0.0}


def build(size_x, size_y, size_z, bore, bore_y, bore_z):
    return Box(size_x, size_y, size_z) - Pos(0, bore_y, bore_z) * Rot(0, 90, 0) * Cylinder(bore / 2.0, size_x + 2)

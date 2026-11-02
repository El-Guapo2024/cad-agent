"""Motor mount: a 6 mm aluminium plate a NEMA 17's face bolts to (pilot in its 22 bore), standing on or hung from
a plate. Sized per use in assembly.py (the X, the Y and the flip motor).
"""
from build123d import Box, Cylinder, Pos, Rot

MATERIAL = "aluminium"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 1.0

EXPECT_FEATURES = 1

PARAMS = {"size_x": 6.0, "size_y": 60.0, "size_z": 40.0, "bore": 22.0, "bore_z": 0.0}


def build(size_x, size_y, size_z, bore, bore_z):
    return Box(size_x, size_y, size_z) - Pos(0, 0, bore_z) * Rot(0, 90, 0) * Cylinder(bore / 2.0, size_x + 2)

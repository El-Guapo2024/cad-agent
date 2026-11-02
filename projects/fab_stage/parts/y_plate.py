"""Y plate: the 10 mm 6061 plate the Y carriages carry; the X rails' risers, the X screw's supports and the X motor
stand on it. Cut by waterjet or fibre laser; screw holes are drilled to the parts on it.
"""
from build123d import Box

MATERIAL = "aluminium"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 1.0
EXPECT_FEATURES = 0

PARAMS = {"size_x": 440.0, "size_y": 310.0, "thick": 10.0}


def build(size_x, size_y, thick):
    return Box(size_x, size_y, thick)

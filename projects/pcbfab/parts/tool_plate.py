"""Tool plate: the 6 mm aluminium carriage plate of the tool bridge, on two MGN12 blocks and the ball nut's bracket
behind it; the process tools' air slides, the height sensor, the camera and the three UV lamps bolt to its front.
Waterjet cut.
"""
from build123d import Box

MATERIAL = "aluminium"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 1.0
EXPECT_FEATURES = 0

PARAMS = {"size_x": 335.0, "thick": 6.0, "size_z": 140.0}


def build(size_x, thick, size_z):
    return Box(size_x, thick, size_z)

"""Electronics plate: a 3 mm aluminium plate across the cabinet's bottom rails that the supplies, the boards and the
pump stand on (four, left and right of the stage, front and back). Sized per plate in assembly.py.
"""
from build123d import Box

MATERIAL = "aluminium"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 1.0
EXPECT_FEATURES = 0

PARAMS = {"size_x": 163.0, "size_y": 466.0, "thick": 3.0}


def build(size_x, size_y, thick):
    return Box(size_x, size_y, thick)

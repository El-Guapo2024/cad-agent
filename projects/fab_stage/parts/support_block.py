"""Support block: a 6061 block (cut from 18 mm plate) under the Y ball screw's BK10 or BF10 on the cabinet floor,
setting the screw's axis 2 mm under the Y plate's nut flats. Bolted down through two holes.
"""
from build123d import Box, Cylinder, Pos

MATERIAL = "aluminium"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 1.0
EXPECT_FEATURES = 2

PARAMS = {"size_x": 70.0, "size_y": 50.0, "height": 18.0, "pitch": 56.0, "hole": 6.6}


def build(size_x, size_y, height, pitch, hole):
    b = Box(size_x, size_y, height)
    for s in (-1, 1):
        b -= Pos(s * pitch / 2.0, 0, 0) * Cylinder(hole / 2.0, height + 2)
    return b

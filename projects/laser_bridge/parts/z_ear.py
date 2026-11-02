"""Z ear: the aluminium block on the -y side of each end plate that carries the Tr8x8 flange nut of that post's
focus screw, bored 11 through for the screw.
"""
from build123d import Box, Cylinder

MATERIAL = "aluminium"
PROCESS = "cnc"
MIN_FEATURE_MM = 1.0
EXPECT_FEATURES = 1

PARAMS = {"size_x": 18.0, "size_y": 30.0, "height": 12.0, "bore": 11.0}


def build(size_x, size_y, height, bore):
    return Box(size_x, size_y, height) - Cylinder(bore / 2.0, height + 2)

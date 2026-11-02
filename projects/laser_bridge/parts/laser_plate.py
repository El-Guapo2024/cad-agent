"""Laser plate: 10 mm aluminium (waterjet cut) under the two bridge beams, carrying the UV source and the galvo in line.

As in the commercial UV marking machines built on a JPT Lark and an SG7110: the source's beam (0.7 mm, its 10x
expander built in) goes straight into the galvo's input, so the two hang from one rigid plate, and the plate from
the bridge. The galvo hangs under a spacer (galvo_spacer.py) so its input sits on the source's beam axis.
"""
from build123d import Box

MATERIAL = "aluminium"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 1.0
EXPECT_FEATURES = 0

PARAMS = {"size_x": 428.0, "size_y": 150.0, "thickness": 10.0}


def build(size_x, size_y, thickness):
    return Box(size_x, size_y, thickness)

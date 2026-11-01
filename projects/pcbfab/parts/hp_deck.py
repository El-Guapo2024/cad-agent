"""Hot-plate deck: a 6 mm aluminium plate on four 2020 legs from the table, under LumenPnP's head.

It stands on the table between LumenPnP's feeder rails, so no feeder slot is lost; four standoffs hold the hot plate over it.
"""
from build123d import Box

MATERIAL = "aluminium"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 3.0
EXPECT_FEATURES = 0

PARAMS = {'size_x': 180.0, 'size_y': 170.0, 'thickness': 6.0}


def build(size_x, size_y, thickness):
    return Box(size_x, size_y, thickness)

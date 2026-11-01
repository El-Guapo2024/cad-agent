"""Laser deck: a 6 mm aluminium plate on four 2020 legs from the table, in the laser zone behind the PnP area.

Its legs stand wide enough for the fiber source to lie on the table between them; four standoffs hold the laser
bed over it.
"""
from build123d import Box

MATERIAL = "aluminium"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 3.0
EXPECT_FEATURES = 0

PARAMS = {'size_x': 230.0, 'size_y': 290.0, 'thickness': 6.0}


def build(size_x, size_y, thickness):
    return Box(size_x, size_y, thickness)

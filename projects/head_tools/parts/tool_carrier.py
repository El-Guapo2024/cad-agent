"""Tool carrier: the 6 mm aluminium plate on the lift's MGN12 carriage that the dispensers, the jet and the height
sensor bolt to; it lowers them 8 mm to work and lifts them clear of the flip frame (42.2) to travel. Waterjet cut.
"""
from build123d import Box

MATERIAL = "aluminium"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 1.0
EXPECT_FEATURES = 0

PARAMS = {"size_x": 190.0, "thick": 6.0, "size_z": 80.0}


def build(size_x, thick, size_z):
    return Box(size_x, thick, size_z)

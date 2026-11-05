"""Tool plate: the 6 mm aluminium plate bolted to the front face of LumenPnP's head plate, left of the head's own
nozzle motors, that the process tools' air slides and the height sensor bolt to. Its right end overlaps the head plate by 11 mm for the bolts (Opulo's model: the head plate x 398.8 to 488.8).
Waterjet cut.
"""
from build123d import Box

MATERIAL = "aluminium"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 1.0
EXPECT_FEATURES = 0

PARAMS = {"size_x": 205.0, "thick": 6.0, "size_z": 140.0}


def build(size_x, thick, size_z):
    return Box(size_x, thick, size_z)

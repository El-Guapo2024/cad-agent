"""End plate: the 10 mm aluminium plate at each end of the bridge beams, bolted to an MGN15 carriage on its post.

The bridge is its own focus axis: the beams, the laser plate and everything under it ride up and down 20 mm on the
two posts' rails (CircuitJet IV and LPKF's ProtoLaser focus to the board; boards run 0.2 to 3 mm and the lens's
depth of focus is a few tenths). Waterjet cut.
"""
from build123d import Box

MATERIAL = "aluminium"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 1.0
EXPECT_FEATURES = 0

PARAMS = {"thick": 10.0, "width": 100.0, "height": 60.0}


def build(thick, width, height):
    return Box(thick, width, height)

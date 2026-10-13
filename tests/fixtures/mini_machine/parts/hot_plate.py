"""Hot plate: the 180 C aluminium plate the machine works over, 80 x 60 x 10 mm.

It is the source of the heat zone in spec.toml (its own material, 6061, is rated 170 C: a source is exempt). It lies on
the insulator, 6 mm over the base. A plain plate: the heater element and its screws are not modelled.
"""
from build123d import Box

MATERIAL = "aluminium"
PROCESS = "cnc"             # milled from plate
MIN_FEATURE_MM = 10.0
EXPECT_FEATURES = 0

PARAMS = {
    "width": 80.0,          # x
    "length": 60.0,         # y
    "thickness": 10.0,      # z
}


def build(width, length, thickness):
    return Box(width, length, thickness)

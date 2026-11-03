"""Door: one of the enclosure's two front doors (the lower front tiles), 3 mm aluminium, hinged on the outer post
and closing on the middle one, each with an Omron D4NS interlock switch: open, the laser and the UV lamps are cut in
hardware (the G9SE safety relay). The board goes in and out of the flip frame through them. Hinges and handles are
bought and not drawn.
"""
from build123d import Box

MATERIAL = "aluminium"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 1.0
EXPECT_FEATURES = 0

PARAMS = {"size_a": 445.0, "size_b": 342.0, "thick": 3.0}


def build(size_a, size_b, thick):
    return Box(size_a, size_b, thick)

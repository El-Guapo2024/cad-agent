"""Pen clamp: the aluminium block that holds an eco-PEN to the tool carrier, bored to its 33 mm body along the
pen's axis, which leans 35 degrees forward so its top stays low under the laser's lens (a slit and a screw close it;
not drawn). `bore_y` is where the axis crosses the block's mid-height plane, from the block's centre.
"""
from build123d import Box, Cylinder, Pos, Rot

MATERIAL = "aluminium"
PROCESS = "cnc"
MIN_FEATURE_MM = 1.0
EXPECT_FEATURES = 1

PARAMS = {"size_x": 40.0, "size_y": 80.0, "height": 20.0, "bore": 33.2, "bore_y": -12.0, "tilt": 35.0}


def build(size_x, size_y, height, bore, bore_y, tilt):
    return Box(size_x, size_y, height) - Pos(0, bore_y, 0) * Rot(tilt, 0, 0) * Cylinder(bore / 2.0, 4 * height)

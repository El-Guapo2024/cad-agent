"""Lead screw support block: one at each end of each screw, on the cross beam's top, holding the screw's bearing
(a fixed end and a floating end, BK/BF class; the bearing is drawn as the bore). Machined aluminium.

Frame: its bottom at z 0 (the beam's top), the screw's axis along y at z `axis_h`, centred in x and y.
"""
from build123d import Box, Cylinder, Pos, Rot

MATERIAL = "aluminium"
PROCESS = "cnc"
MIN_FEATURE_MM = 2.0

PARAMS = {"size_x": 30.0, "size_y": 10.0, "height": 28.0, "axis_h": 16.0, "bore": 12.0, "hole": 5.5}


def build(size_x, size_y, height, axis_h, bore, hole):
    b = Pos(0, 0, height / 2.0) * Box(size_x, size_y, height)
    b -= Pos(0, 0, axis_h) * Rot(90, 0, 0) * Cylinder(bore / 2.0, size_y + 2)
    for sx in (-1, 1):
        b -= Pos(sx * (size_x / 2.0 - 5.0), 0, 3.0) * Cylinder(hole / 2.0, 8.0)
    return b

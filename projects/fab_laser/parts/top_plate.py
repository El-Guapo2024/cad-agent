"""Caps the column and carries the Z stepper over the lead screw; the coupler passes through its hole. Frame: its
bottom at z 0 (the column's top); x 0 y 0 on the column's axis.
"""
from build123d import Box, Cylinder, Pos

MATERIAL = "aluminium"
PROCESS = "cnc"
MIN_FEATURE_MM = 2.0

PARAMS = {"x0": -20.0, "x1": 70.0, "d": 50.0, "t": 8.0, "screw_x": 45.0, "hole": 29.0}


def build(x0, x1, d, t, screw_x, hole):
    p = Pos((x0 + x1) / 2.0, 0, t / 2.0) * Box(x1 - x0, d, t)
    return p - Pos(screw_x, 0, t / 2.0) * Cylinder(hole / 2.0, t + 2)

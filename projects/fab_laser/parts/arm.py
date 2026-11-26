"""The laser arm: a horizontal aluminium plate from the Z carriage forward over the board, carrying the galvo head
(over a hole the lens hangs through) and the UV source beside it. Frame: its back edge (on the carriage) at y 0,
running -y; its bottom at z 0; x 0 on the lens axis.
"""
from build123d import Box, Cylinder, Pos

MATERIAL = "aluminium"
PROCESS = "cnc_long"
MIN_FEATURE_MM = 2.0

PARAMS = {"x0": -70.0, "x1": 410.0, "depth": 177.0, "t": 12.0, "lens_y": 122.0, "lens_hole": 85.0}


def build(x0, x1, depth, t, lens_y, lens_hole):
    a = Pos((x0 + x1) / 2.0, -depth / 2.0, t / 2.0) * Box(x1 - x0, depth, t)
    return a - Pos(0, -lens_y, t / 2.0) * Cylinder(lens_hole / 2.0, t + 2)

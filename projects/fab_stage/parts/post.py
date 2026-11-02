"""Trunnion post: the upright at each end of the X plate that carries the flip frame's shaft and the platen's lift.

A 12 mm 6061 plate standing on the X plate. The frame's 8 mm shaft turns in a 608 bearing (22 mm bore) at the board's
mid-plane, so the board's two faces swap places about the same line and the stage's registration holds through the
flip. On its inner face, one MGN12 rail (the platen's lift guide) and, beside the shaft, the lift's T8 screw.
"""
from build123d import Box, Cylinder, Pos, Rot

MATERIAL = "aluminium"
PROCESS = "cnc"
MIN_FEATURE_MM = 1.0
EXPECT_FEATURES = 1

PARAMS = {"width": 110.0, "thick": 12.0, "height": 188.0, "bore": 22.0, "bore_z": 173.2, "screw_x": -35.0,
          "screw_clear": 10.0}


def build(width, thick, height, bore, bore_z, screw_x, screw_clear):
    b = Box(width, thick, height)
    b -= Pos(0, 0, -height / 2.0 + bore_z) * Rot(90, 0, 0) * Cylinder(bore / 2.0, thick + 2.0)
    return b

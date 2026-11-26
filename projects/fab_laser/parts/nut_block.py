"""Holds the Z lead nut behind the carriage, beside the column, so the screw runs clear of the column and the rail.
Frame: its front face (on the carriage's back) at y 0, running +y; the nut bore's axis at x 0, y bore_y; centred in z.
"""
from build123d import Box, Cylinder, Pos

MATERIAL = "aluminium"
PROCESS = "cnc"
MIN_FEATURE_MM = 2.0

PARAMS = {"w": 32.0, "depth": 48.0, "h": 40.0, "bore": 22.0, "bore_y": 33.0, "x_back": 18.0}


def build(w, depth, h, bore, bore_y, x_back):
    b = Pos(0, depth / 2.0, 0) * Box(w, depth, h)
    b += Pos(-(w / 2.0 + x_back) / 2.0, 6.0, 0) * Box(x_back, 12.0, h)      # a tab back along the carriage, to bolt it
    return b - Pos(0, bore_y, 0) * Cylinder(bore / 2.0, h + 2)

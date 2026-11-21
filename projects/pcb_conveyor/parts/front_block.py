"""Front rail mount: the block that fixes the front (SMEMA: fixed) rail to a cross beam's top. Machined aluminium.

Frame: its top at z 0 (the rail's bottom), its inner face at y 0 (under the rail's inner face), centred in x.
"""
from build123d import Box, Cylinder, Pos

MATERIAL = "aluminium"
PROCESS = "cnc"
MIN_FEATURE_MM = 2.0

PARAMS = {"size_x": 40.0, "size_y": 30.0, "height": 30.0, "hole": 6.6}


def build(size_x, size_y, height, hole):
    b = Pos(0, -size_y / 2.0, -height / 2.0) * Box(size_x, size_y, height)
    for y in (-size_y / 2.0 + 8.0,):
        b -= Pos(0, y, -height / 2.0) * Cylinder(hole / 2.0, height + 2)
    return b

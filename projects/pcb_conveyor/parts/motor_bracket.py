"""Drive gearmotor bracket: a plate bolted to the front rail's mount block, the gearbox's face bolted to it, the hex
shaft passing through. Machined aluminium.

Frame: its +y face at y 0 (against the front block's outer face), the shaft's axis at x 0, z 0; the plate runs -y.
"""
from build123d import Box, Cylinder, Pos, Rot

MATERIAL = "aluminium"
PROCESS = "cnc"
MIN_FEATURE_MM = 2.0

PARAMS = {"size_x": 50.0, "thick": 12.0, "z0": -50.0, "z1": 25.0, "x0": -30.0, "shaft_hole": 14.0}


def build(size_x, thick, z0, z1, x0, shaft_hole):
    p = Pos(x0 + size_x / 2.0, -thick / 2.0, (z0 + z1) / 2.0) * Box(size_x, thick, z1 - z0)
    return p - Rot(90, 0, 0) * Cylinder(shaft_hole / 2.0, thick * 3)

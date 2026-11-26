"""Belt motor mount: a plate the stepper's face bolts to, held off the front rail's outer face by two legs so the
coupler fits between. Machined aluminium.

Frame: the shaft's axis along y at x 0, z 0; the legs' ends at y 0 (against the rail), the plate's motor face at
y -depth.
"""
from build123d import Box, Cylinder, Pos, Rot

MATERIAL = "aluminium"
PROCESS = "cnc"
MIN_FEATURE_MM = 2.0

PARAMS = {"size": 46.0, "plate_t": 5.0, "depth": 26.0, "leg": 8.0, "hole": 23.0}


def build(size, plate_t, depth, leg, hole):
    m = Pos(0, -depth + plate_t / 2.0, 0) * (Box(size, plate_t, size) - Rot(90, 0, 0) * Cylinder(hole / 2.0, plate_t + 2))
    for sx in (-1, 1):
        m += Pos(sx * (size / 2.0 - leg / 2.0), -(depth - plate_t) / 2.0, 0) * Box(leg, depth - plate_t, size)
    return m

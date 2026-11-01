"""Enclosure back: 3 mm aluminium with the fume port, high up behind the laser zone.

The port takes a 55 mm extractor hose (HEPA + carbon, two stages). Lies in x-z.
"""
from build123d import Box, Cylinder, Pos, Rot

MATERIAL = "aluminium"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 3.0
EXPECT_FEATURES = 1

PARAMS = {'size_x': 880.0, 'size_y': 3.0, 'thickness': 631.0, 'port': 56.0, 'port_x': 160.0, 'port_z': 180.0}


def build(size_x, size_y, thickness, port, port_x, port_z):
    p = Box(size_x, size_y, thickness)
    p -= Pos(port_x, 0, port_z) * Rot(90, 0, 0) * Cylinder(port / 2.0, size_y + 2)
    return p

"""Platen ring: the middle layer of the platen, its window the vacuum plenum under the skin's hole grid.

The hose port is a slot cut from the window out through its -y end, where a push-in fitting's adapter screws on.
The +x wall is wider, and a 3.2 slot along it, 75 deep from the -y end, takes the PT1000 probe between the skin and
the base, sealed from the plenum by the wall.
"""
from build123d import Box, Pos

MATERIAL = "aluminium"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 1.0
EXPECT_FEATURES = 0

PARAMS = {"size_x": 215.0, "size_y": 295.0, "thick": 6.0, "wall": 5.0, "probe_wall": 15.0, "port_w": 6.0,
          "probe_slot": 3.2, "probe_depth": 75.0}


def build(size_x, size_y, thick, wall, probe_wall, port_w, probe_slot, probe_depth):
    wx = size_x - wall - probe_wall
    b = Box(size_x, size_y, thick) - Pos((wall - probe_wall) / 2.0, 0, 0) * Box(wx, size_y - 2 * wall, thick + 2)
    b -= Pos(0, -size_y / 2.0 + wall / 2.0, 0) * Box(port_w, wall + 2.0, thick + 2)
    px = size_x / 2.0 - probe_wall / 2.0
    return b - Pos(px, -size_y / 2.0 + probe_depth / 2.0 - 1.0, 0) * Box(probe_slot, probe_depth + 2.0, thick + 2)

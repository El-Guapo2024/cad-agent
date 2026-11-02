"""X plate: the 10 mm 6061 plate the X carriages carry, the posts, the platen's lift and the flip motor stand on.

Cut by waterjet or fibre laser. Two holes pass the lift motors' pilots and shafts up to their couplings.
"""
from build123d import Box, Cylinder, Pos

MATERIAL = "aluminium"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 1.0

EXPECT_FEATURES = 2

PARAMS = {"size_x": 150.0, "size_y": 415.4, "thick": 10.0, "holes": [[-35.0, -181.2, 22.5], [-35.0, 181.2, 22.5]]}


def build(size_x, size_y, thick, holes):
    b = Box(size_x, size_y, thick)
    for x, y, d in holes:
        b -= Pos(x, y, 0) * Cylinder(d / 2.0, thick + 2)
    return b

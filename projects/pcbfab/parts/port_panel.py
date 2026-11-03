"""Port panel: the lower-right back tile, with the 56 mm fume port the BOFA extractor's 50 mm hose clamps to, and the
IEC inlet's 47 x 28 cutout (Schurter KM00, fused and switched) for the mains.
"""
from build123d import Box, Cylinder, Pos

MATERIAL = "aluminium"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 1.0
EXPECT_FEATURES = 2

PARAMS = {"size_a": 445.0, "size_b": 342.0, "thick": 3.0, "port": 56.0, "port_a": 120.0, "port_b": 40.0,
          "inlet": (47.0, 28.0), "inlet_a": -150.0, "inlet_b": -100.0}


def build(size_a, size_b, thick, port, port_a, port_b, inlet, inlet_a, inlet_b):
    p = Box(size_a, size_b, thick) - Pos(port_a, port_b, 0) * Cylinder(port / 2.0, thick + 2)
    return p - Pos(inlet_a, inlet_b, 0) * Box(inlet[0], inlet[1], thick + 2)

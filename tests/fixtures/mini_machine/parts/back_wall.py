"""Back wall: a 3 mm laser-cut acrylic plate that stands at the end of the gantry's slide, a stop and a guard.

200 mm along y and 80 high, thin along x. A 30 x 20 window takes a cable gland, and two M4 holes 10 mm up from its
bottom edge take the brackets that hold it to the base. Built with its thin axis along x, ready to stand in a plane
x = const: assembly.py puts it 88 mm from the middle.
"""
from build123d import Axis, Box, Cylinder, Pos, Rot, fillet
from cad_agent.parts import CLEARANCE_HOLE

MATERIAL = "acrylic"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 3.0        # the web between the window and the plate's edge: (80 - 20) / 2 = 30, or a hole's 5 mm - 2.25

EXPECT_FEATURES = 3         # the window and two holes

PARAMS = {
    "thickness": 3.0,       # x, sheet as bought
    "length": 200.0,        # y
    "height": 80.0,         # z
    "corner_r": 3.0,
    "screw": "M4",
    "hole_y": 90.0,         # the two holes are at y = +-90, 10 mm up from the bottom edge
    "hole_z": -30.0,
    "window_w": 30.0,       # along y
    "window_h": 20.0,       # along z
    "window_r": 1.0,
}


def build(thickness, length, height, corner_r, screw, hole_y, hole_z, window_w, window_h, window_r):
    wall = fillet(Box(thickness, length, height).edges().filter_by(Axis.X), corner_r)
    d = CLEARANCE_HOLE[screw]
    for sy in (-1, 1):
        wall -= Pos(0, sy * hole_y, hole_z) * Rot(0, 90, 0) * Cylinder(d / 2.0, thickness + 2.0)
    window = fillet(Box(thickness + 2.0, window_w, window_h).edges().filter_by(Axis.X), window_r)
    wall -= window
    return wall

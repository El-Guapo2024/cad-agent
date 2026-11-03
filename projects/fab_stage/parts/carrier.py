"""Carrier: the stainless plate the platen stands on, with the four tabs the lift lifts it by.

The platen sits on four stainless standoffs over it . Two tabs at each end reach out
under the flip frame's end bars to the lift: one under the arm on the MGN12 carriage (+x), one under the T8 nut block
(-x), notched 22 there so the screw's coupling passes when the platen is down. 4 mm stainless, laser cut.
"""
from build123d import Box, Cylinder, Pos

MATERIAL = "stainless"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 1.0
EXPECT_FEATURES = 4

PARAMS = {"size_x": 215.0, "size_y": 295.0, "thick": 4.0, "tab_w": 30.0, "tab_reach": 180.0, "screw_reach": 194.7,
          "tab_x": 35.0, "screw_x": -35.0, "screw_y": 181.2, "coupling_hole": 22.0, "standoff_inset": 15.0,
          "hole": 3.4}


def build(size_x, size_y, thick, tab_w, tab_reach, screw_reach, tab_x, screw_x, screw_y, coupling_hole,
          standoff_inset, hole):
    b = Box(size_x, size_y, thick)
    for s in (-1, 1):
        for x, reach in ((tab_x, tab_reach), (screw_x, screw_reach)):
            run = reach - size_y / 2.0
            b += Pos(x, s * (size_y / 2.0 + run / 2.0 - 0.5), 0) * Box(tab_w, run + 1.0, thick)
        b -= Pos(screw_x, s * screw_y, 0) * Cylinder(coupling_hole / 2.0, thick + 2)    # a U notch, open at the end
        b -= Pos(screw_x, s * (screw_y + screw_reach) / 2.0 + 0.0, 0) * Box(coupling_hole, screw_reach - screw_y + 2,
                                                                             thick + 2)
    for sx in (-1, 1):
        for sy in (-1, 1):
            b -= Pos(sx * (size_x / 2.0 - standoff_inset), sy * (size_y / 2.0 - standoff_inset), 0) * Cylinder(
                hole / 2.0, thick + 2)
    return b

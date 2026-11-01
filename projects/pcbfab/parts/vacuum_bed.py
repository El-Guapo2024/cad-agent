"""Vacuum laser bed: the pinned aluminium block the board lies on in the laser zone, and the via-fill vacuum table.

The via paste goes in the way LPKF's ProConduct does it (https://www.lpkfusa.com/products-technologies/pcb-prototyping-
equipment/products/lpkf-proconduct): paste squeegeed over a film on the board, and a vacuum under the board pulls it
through the drilled holes, then the board is flipped and done again, and cured on the hot plate (160 C, 30 min).
So the bed is a plenum: a pocket from below under the 100 x 100 board area, a grid of 1 mm holes through its top
skin, a hose port in its side. It sits straight on the laser deck (a gasket seals the pocket's open face), in place
of the plate and standoffs before, with its top where the plate's was. The two registration-pin holes are blind, in
the solid wall either side of the pocket, on the hot plate's pitch, so a board here drops onto the hot plate's pins
in the same place. Four M3 tapped holes from below bolt it to the deck.
"""
from build123d import Box, Cylinder, Pos, Rot
from cad_agent.parts import TAP_DRILL

MATERIAL = "aluminium"
PROCESS = "cnc"
MIN_FEATURE_MM = 1.0
EXPECT_FEATURES = 88         # 81 vacuum holes, 2 pin holes, 1 port, 4 mount holes

PARAMS = {
    "size_x": 150.0,
    "size_y": 150.0,
    "height": 34.525,        # the plate (9.525) and standoffs (25) it replaces
    "pocket": 100.0,         # the board's own area
    "skin": 6.525,           # the top over the pocket
    "hole": 1.0,
    "hole_pitch": 10.0,
    "holes_per_side": 9,
    "pin_pitch": 116.0,
    "pin_hole": 3.0,
    "pin_depth": 10.0,
    "port": 8.0,             # a push-in fitting for the pump's hose
    "mount_inset": 7.0,
}


def build(size_x, size_y, height, pocket, skin, hole, hole_pitch, holes_per_side, pin_pitch, pin_hole, pin_depth,
          port, mount_inset):
    top = height / 2.0
    b = Box(size_x, size_y, height)
    depth = height - skin
    b -= Pos(0, 0, -top + depth / 2.0) * Box(pocket, pocket, depth)
    first = -(holes_per_side - 1) * hole_pitch / 2.0
    for i in range(holes_per_side):
        for j in range(holes_per_side):
            b -= Pos(first + i * hole_pitch, first + j * hole_pitch, top - skin / 2.0) * Cylinder(hole / 2.0, skin + 2)
    for sx in (-1, 1):
        b -= Pos(sx * pin_pitch / 2.0, 0, top - pin_depth / 2.0) * Cylinder(pin_hole / 2.0, pin_depth)
        for sy in (-1, 1):
            b -= (Pos(sx * (size_x / 2.0 - mount_inset), sy * (size_y / 2.0 - mount_inset), -top + 5.0)
                  * Cylinder(TAP_DRILL["M3"] / 2.0, 10.0))
    run = (size_x - pocket) / 2.0 + 2.0
    b -= Pos(size_x / 2.0 - run / 2.0 + 1.0, 0, -top + depth / 2.0) * Rot(0, 90, 0) * Cylinder(port / 2.0, run)
    return b

"""Hot-plate bed: the 250 C reflow and via-cure plate the board lies on, with the two registration-pin holes.

Recycled from cad-agent's desk_fab_line hot plate (a flat mica heater clamped underneath, so the underside stays
plain), grown to 150 x 150 x 3/8" (9.525, stock 6061-T651 plate) to match the Misumi MPHK-150-150 500 W mica heater
(300 C) that clamps under it; mains through an SSR, a PT1000 in the plate, a KSD301 cut-out on its edge.
The two pin holes lie on the plate's x centre line, symmetric about its middle: the board is flipped about that line,
so after the flip its two tooling holes land on the same pins and side B registers to side A. The machine drills
those tooling holes itself in the board's first step.
Four corner holes are tapped M3 from below for the standoffs.
"""
from build123d import Box, Cylinder, Pos
from cad_agent.parts import TAP_DRILL

MATERIAL = "aluminium"
PROCESS = "cnc"
MIN_FEATURE_MM = 4.0
EXPECT_FEATURES = 6          # 4 standoff holes, 2 pin holes

PARAMS = {
    "size_x": 150.0,
    "size_y": 150.0,
    "thickness": 9.525,
    "pin_pitch": 116.0,      # the two pins, either side of the middle along x
    "pin_hole": 3.0,         # a 3 mm dowel, pressed in
    "mount_inset": 7.0,
}


def build(size_x, size_y, thickness, pin_pitch, pin_hole, mount_inset):
    plate = Box(size_x, size_y, thickness)
    for sx in (-1, 1):
        plate -= Pos(sx * pin_pitch / 2.0, 0, 0) * Cylinder(pin_hole / 2.0, thickness + 2)
        for sy in (-1, 1):
            plate -= (Pos(sx * (size_x / 2.0 - mount_inset), sy * (size_y / 2.0 - mount_inset), 0)
                      * Cylinder(TAP_DRILL["M3"] / 2.0, thickness + 2))
    return plate

"""Carrier block that locates on two dowel pins and clears the screw head.

Two round holes take the pins, 0.01 mm to spare all round (4 F7: 4.010 to 4.022 mm, mid-range
4.016, on a 4 m6 pin), so the block is located to a few hundredths of a millimetre but still lifts
off by hand. A round relief pocket in the underside, concentric with the clamp screw, clears its
head by 1 mm on every side and above: without it the block would sit on the screw head instead of
the base. The origin is the centre of the underside, so the block is placed as it is.
"""
from build123d import Box, Cylinder, Pos

MATERIAL = "aluminium"
PROCESS = "cnc"
MIN_FEATURE_MM = 7.0        # the web between a pin hole and the block's end

# Both pin holes cut the mid-plane; the pocket stops short of it.
EXPECT_FEATURES = 2

PARAMS = {
    "length": 70.0,
    "width": 30.0,
    "height": 12.0,
    "pin_pitch": 50.0,      # the pins stand at x = +-25 on the base
    "pin_hole": 4.02,
    "pocket_dia": 9.0,      # the M4 head is 7.0 across
    "pocket_depth": 5.0,    # and 4.0 high
}


def build(length, width, height, pin_pitch, pin_hole, pocket_dia, pocket_depth):
    body = Pos(0, 0, height / 2.0) * Box(length, width, height)
    for sx in (-1, 1):
        body -= Pos(sx * pin_pitch / 2.0, 0, height / 2.0) * Cylinder(pin_hole / 2.0, height + 2.0)
    body -= Pos(0, 0, (pocket_depth - 1.0) / 2.0) * Cylinder(pocket_dia / 2.0, pocket_depth + 1.0)
    return body

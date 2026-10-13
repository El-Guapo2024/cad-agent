"""Base: the machine's floor, a 3 mm laser-cut steel plate that everything else stands on.

200 x 300 mm with R5 corners, four M4 clearance holes near the corners to bolt it down, and two slots along x, 4.5 mm
wide (the M4 clearance size) and 150 long, at y = +-120. The gantry's posts stand over the slots, with their M4 bolts
through them, so a post can be bolted anywhere along the slide's 120 mm of travel (and 10 mm either side of it). Steel,
because the hot plate is only 6 mm above it: 400 C is what `cad tables materials` rates it for.
"""
from build123d import Axis, Box, Cylinder, Pos, SlotOverall, extrude, fillet
from cad_agent.parts import CLEARANCE_HOLE

MATERIAL = "steel"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 7.5        # the narrowest web: a corner hole to the plate's edge, 10 - 2.25 = 7.75

EXPECT_FEATURES = 6         # four corner holes and two slots

PARAMS = {
    "width": 200.0,         # x
    "length": 300.0,        # y
    "thickness": 3.0,       # z, sheet as bought
    "corner_r": 5.0,
    "screw": "M4",
    "hole_x": 90.0,         # the corner holes are at (+-90, +-140)
    "hole_y": 140.0,
    "slot_y": 120.0,        # the slots are at y = +-120, along x
    "slot_length": 150.0,
    "slot_width": 4.5,
}


def build(width, length, thickness, corner_r, screw, hole_x, hole_y, slot_y, slot_length, slot_width):
    base = fillet(Box(width, length, thickness).edges().filter_by(Axis.Z), corner_r)
    d = CLEARANCE_HOLE[screw]
    for sx in (-1, 1):
        for sy in (-1, 1):
            base -= Pos(sx * hole_x, sy * hole_y, 0) * Cylinder(d / 2.0, thickness + 2.0)
    for sy in (-1, 1):
        base -= Pos(0, sy * slot_y, 0) * extrude(SlotOverall(slot_length, slot_width), amount=thickness + 2.0, both=True)
    return base

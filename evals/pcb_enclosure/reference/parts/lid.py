"""Lid: a flat plate on the walls, with a row of vent slots over the board.

It sits at z = 20.8, the top of the base's walls, so its underside is 2.2 mm
above the tallest part of the board (the DC jack) and 2.55 mm above the plug.
Built in assembly coordinates, so the assembly places nothing: the outline and
the height match parts/base.py.

Vent slots only, no screw holes: how the lid is held on is outside this task.
"""
from build123d import Box, Pos

MATERIAL = "petg"
PROCESS = "fdm"
MIN_FEATURE_MM = 1.2

PARAMS = {
    "x_min": -44.1,        # outer faces of the base's walls
    "x_max": 37.5,
    "y_half": 29.87,
    "z0": 20.8,            # top of the walls
    "thickness": 2.0,
    "slots": 5,
    "slot_w": 2.0,
    "slot_l": 24.0,
    "slot_pitch": 5.0,
    "slot_x": -3.2,        # middle of the slot row, over the middle of the board
}

# Five slots through the plate: the gate fails if one eats another.
EXPECT_FEATURES = 5


def build(x_min, x_max, y_half, z0, thickness, slots, slot_w, slot_l, slot_pitch, slot_x):
    plate = Pos((x_min + x_max) / 2.0, 0, z0 + thickness / 2.0) * Box(
        x_max - x_min, 2.0 * y_half, thickness)
    for i in range(slots):
        x = slot_x + (i - (slots - 1) / 2.0) * slot_pitch
        plate -= Pos(x, 0, z0 + thickness / 2.0) * Box(slot_w, slot_l, thickness + 2.0)
    return plate

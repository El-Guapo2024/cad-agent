"""Chassis plate: the one part everything else bolts to.

A flat 3 mm plate, laser cut, so every feature is a 2D cut and there is no
machining. Layout front to back: a caster ball at the nose, the battery bay
across the middle where its mass sits between the axles, the two motors on
the underside at the rear, and the Arduino on top behind them.

Width is set by the wheels, not by what fits on top: at 84 mm the plate edge
clears the inner face of a 65 mm wheel on its motor axle. The battery bay and
the caster circle were moved after a top view showed the bay swallowing two of
the four caster holes, and the motor slots were brought inboard after the same
view left under 3 mm of acrylic beside a 3.4 mm hole.

The motors mount from below through slotted holes. Slots rather than round
holes because the TT gearbox bolt spacing is unverified, so the slots let the
brackets shift a few millimetres either way rather than making the plate scrap
if the motor measures differently when it arrives.

Arduino holes come from the datasheet drawing via the bought module, so the
pattern is never retyped here. Moving the board is one number, `arduino_x`.
"""
from build123d import Box, Cylinder, Pos, Rot, Align

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bought"))
from arduino_uno import hole_positions as uno_holes, PARAMS as UNO

MATERIAL = "acrylic"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 3.0

PARAMS = {
    "length": 170.0,
    "width": 82.0,            # narrow enough that the wheels clear the plate
    "thickness": 3.0,
    "corner_r": 10.0,
    "arduino_x": 44.0,        # board centre, +x is toward the rear
    "arduino_hole_dia": 3.4,  # M3 clearance, board holes are 3.20
    "motor_x": -6.0,          # axle line, from plate centre
    "motor_spacing": 51.0,    # bracket centres, on the motor centreline
    "motor_slot_len": 8.0,
    "motor_slot_dia": 3.4,
    "caster_x": -70.0,
    "caster_pcd": 26.0,
    "caster_hole_dia": 3.4,
    "battery_bay_l": 56.0,
    "battery_bay_w": 34.0,
    "wire_slot_w": 5.0,
    "wire_slot_l": 26.0,
    "wire_slot_y": 34.0,
}

# Cutouts expected at the mid-plane: 4 Arduino holes, 4 motor slots, 4 caster
# holes, the battery bay, and 2 wire slots. The gate fails if this count
# changes, which is what a cutout swallowing another one looks like.
EXPECT_FEATURES = 15


def build(length, width, thickness, corner_r, arduino_x, arduino_hole_dia,
          motor_x, motor_spacing, motor_slot_len, motor_slot_dia,
          caster_x, caster_pcd, caster_hole_dia,
          battery_bay_l, battery_bay_w, wire_slot_w, wire_slot_l,
          wire_slot_y):
    plate = Box(length, width, thickness)

    # Rounded corners, cut as a square minus a cylinder at each corner.
    for sx in (-1, 1):
        for sy in (-1, 1):
            cx = sx * (length / 2.0 - corner_r)
            cy = sy * (width / 2.0 - corner_r)
            corner = Pos(sx * (length / 2.0 - corner_r / 2.0),
                         sy * (width / 2.0 - corner_r / 2.0), 0) * Box(
                corner_r, corner_r, thickness + 2)
            corner -= Pos(cx, cy, 0) * Cylinder(corner_r, thickness + 4)
            plate -= corner

    # Arduino mounting pattern, taken from the datasheet-backed bought module.
    for hx, hy in uno_holes():
        plate -= Pos(arduino_x + hx, hy, 0) * Cylinder(
            arduino_hole_dia / 2.0, thickness + 2)

    # Motor bracket slots: a slot is two end circles plus the rectangle between.
    for sy in (-1, 1):
        for dx in (-14.0, 14.0):
            cy = sy * motor_spacing / 2.0
            cx = motor_x + dx
            plate -= Pos(cx, cy, 0) * Box(
                motor_slot_len, motor_slot_dia, thickness + 2)
            for e in (-motor_slot_len / 2.0, motor_slot_len / 2.0):
                plate -= Pos(cx + e, cy, 0) * Cylinder(
                    motor_slot_dia / 2.0, thickness + 2)

    # Caster mounting circle at the nose.
    import math
    for i in range(4):
        a = math.radians(45 + 90 * i)
        plate -= Pos(caster_x + caster_pcd / 2.0 * math.cos(a),
                     caster_pcd / 2.0 * math.sin(a), 0) * Cylinder(
            caster_hole_dia / 2.0, thickness + 2)

    # Battery bay: a cut-through so the pack drops in and is strapped, which
    # keeps its mass low rather than stacked on top of the plate.
    plate -= Pos(-18.0, 0, 0) * Box(battery_bay_l, battery_bay_w, thickness + 2)

    # Wire slots outboard of the motor slots. Their width and position are set
    # by the web left either side: at 8 mm wide on y = 32 they passed within
    # 0.8 mm of a motor slot, which the in-plane gate caught at (5, -27.6).
    for sy in (-1, 1):
        plate -= Pos(18.0, sy * wire_slot_y, 0) * Box(
            wire_slot_l, wire_slot_w, thickness + 2)

    return plate


CUTLIST = [{"kind": "acrylic_3mm", "size_mm": [170.0, 84.0], "qty": 1}]

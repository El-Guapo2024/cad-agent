"""L-bracket clamping a TT gearmotor to the underside of the chassis.

One vertical face takes the gearbox, one horizontal face bolts up through the
chassis slots. Printed, because it is a low-load part with an awkward shape
and two perpendicular bolt patterns.

The gearbox bolt spacing is unverified, so the bracket carries a slot on the
motor face too. Between that and the chassis slots, the motor can move in both
axes without recutting anything.
"""
from build123d import Box, Cylinder, Pos, Rot

MATERIAL = "petg"
PROCESS = "fdm"
MIN_FEATURE_MM = 3.0

PARAMS = {
    "base_l": 40.0,
    "base_w": 22.0,
    "wall": 3.0,
    "upright_h": 26.0,
    "chassis_hole_dia": 3.4,
    "chassis_hole_pitch": 28.0,
    "motor_slot_len": 6.0,
    "motor_slot_dia": 3.4,
    "motor_hole_pitch": 17.0,
    "rib": 8.0,
}


def build(base_l, base_w, wall, upright_h, chassis_hole_dia, chassis_hole_pitch,
          motor_slot_len, motor_slot_dia, motor_hole_pitch, rib):
    # Base lies in XY, upright rises in +Z at the -x end.
    base = Pos(0, 0, wall / 2.0) * Box(base_l, base_w, wall)
    upright = Pos(-base_l / 2.0 + wall / 2.0, 0, upright_h / 2.0) * Box(
        wall, base_w, upright_h)
    part = base + upright

    # Gusset so the upright does not hinge off the base at the layer line.
    gusset = Pos(-base_l / 2.0 + wall + rib / 2.0, 0, wall + rib / 2.0) * Box(
        rib, base_w - 6.0, rib)
    gusset -= Pos(-base_l / 2.0 + wall + rib, 0, wall + rib) * Rot(0, 0, 0) * Cylinder(
        rib, base_w, rotation=(90, 0, 0))
    part += gusset

    for sx in (-1, 1):
        part -= Pos(sx * chassis_hole_pitch / 2.0 + 6.0, 0, wall / 2.0) * Cylinder(
            chassis_hole_dia / 2.0, wall + 2)

    # Slots on the upright face, horizontal so the motor slides in y.
    for sy in (-1, 1):
        cy = sy * motor_hole_pitch / 2.0
        cx = -base_l / 2.0 + wall / 2.0
        cz = upright_h * 0.62
        part -= Pos(cx, cy, cz) * Rot(0, 90, 0) * Box(
            motor_slot_dia, motor_slot_len, wall + 2)
        for e in (-motor_slot_len / 2.0, motor_slot_len / 2.0):
            part -= Pos(cx, cy + e, cz) * Rot(0, 90, 0) * Cylinder(
                motor_slot_dia / 2.0, wall + 2)
    return part

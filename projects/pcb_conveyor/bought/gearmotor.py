"""Belt drive gearmotor, envelope: square gearbox and round motor can along -y from the output shaft, which couples
straight to the hex shaft. Origin at the output shaft's end face, centred on its axis.

DIMENSIONS ARE UNVERIFIED: a placeholder envelope until the motor is chosen (speed set by SMEMA conveyor practice,
torque by the carrier's mass).
"""
from build123d import Box, Cylinder, Pos, Rot

SOURCE = "placeholder envelope; motor not chosen"
VENDOR = None
VERIFIED = False

PARAMS = {"box": 36.0, "box_l": 40.0, "can_dia": 36.0, "can_l": 60.0, "shaft_l": 12.0}


def build(box, box_l, can_dia, can_l, shaft_l):
    m = Pos(0, -shaft_l - box_l / 2.0, 0) * Box(box, box_l, box)
    m += Pos(0, -shaft_l - box_l - can_l / 2.0, 0) * Rot(90, 0, 0) * Cylinder(can_dia / 2.0, can_l)
    m += Pos(0, -shaft_l / 2.0, 0) * Rot(90, 0, 0) * Cylinder(4.0, shaft_l)
    return m

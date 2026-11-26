"""NEMA 17 stepper (the Z motor), envelope; shaft along +y, origin at the mounting face, centred on the shaft.

The 42.3 mm square face is the NEMA ICS 16 size 17 frame; body length and shaft are class-typical (UNVERIFIED).
"""
from build123d import Box, Cylinder, Pos, Rot

SOURCE = "NEMA 17 frame 42.3 square; length 40 and shaft 5 x 20 class-typical, motor not chosen"
VENDOR = None
VERIFIED = False

PARAMS = {"face": 42.3, "body_l": 40.0, "shaft": 5.0, "shaft_l": 20.0}


def build(face, body_l, shaft, shaft_l):
    m = Pos(0, -body_l / 2.0, 0) * Box(face, body_l, face)
    return m + Pos(0, shaft_l / 2.0, 0) * Rot(90, 0, 0) * Cylinder(shaft / 2.0, shaft_l)

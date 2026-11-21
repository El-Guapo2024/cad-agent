"""Levelling foot, M10, under each leg: sets the conveyor to SMEMA's 37-38 in board height on an uneven floor.

Origin at the top of its threaded stem (the leg's bottom), z down to the floor. UNVERIFIED class-typical envelope.
"""
from build123d import Cylinder, Pos

SOURCE = "class-typical M10 levelling foot, pad 50, total 50 at mid adjustment"
VENDOR = None
VERIFIED = False

PARAMS = {"pad": 50.0, "pad_t": 10.0, "stem": 10.0, "height": 50.0}


def build(pad, pad_t, stem, height):
    f = Pos(0, 0, -height + pad_t / 2.0) * Cylinder(pad / 2.0, pad_t)
    return f + Pos(0, 0, -(height - pad_t) / 2.0) * Cylinder(stem / 2.0, height - pad_t)

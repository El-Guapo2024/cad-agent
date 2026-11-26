"""Drive shaft, 8 mm ground steel (h6), cut to length: across both rails in 608 bearings, the drive pulleys fixed on
it. Axis along y, centred. UNVERIFIED stock size; length to the design.
"""
from build123d import Cylinder, Rot

SOURCE = "stock 8 mm h6 ground shaft; length to the design"
VENDOR = None
VERIFIED = False

PARAMS = {"length": 220.0, "dia": 8.0}


def build(length, dia):
    return Rot(90, 0, 0) * Cylinder(dia / 2.0, length)

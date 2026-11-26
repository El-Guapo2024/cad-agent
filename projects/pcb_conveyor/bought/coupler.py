"""Shaft coupler joining the width stepper's 5 mm shaft to the rear lead screw's 12 mm end. Axis along y; y 0 at the
screw end, running +y. UNVERIFIED class-typical clamp coupler envelope.
"""
from build123d import Cylinder, Pos, Rot

SOURCE = "class-typical 5-12 clamp coupler, OD 25, length 25"
VENDOR = None
VERIFIED = False

PARAMS = {"od": 25.0, "length": 25.0, "bore_a": 12.0, "depth_a": 11.0, "bore_b": 5.0}


def build(od, length, bore_a, depth_a, bore_b):
    c = Pos(0, length / 2.0, 0) * Rot(90, 0, 0) * Cylinder(od / 2.0, length)
    c -= Pos(0, depth_a / 2.0, 0) * Rot(90, 0, 0) * Cylinder(bore_a / 2.0, depth_a)
    return c - Pos(0, length / 2.0, 0) * Rot(90, 0, 0) * Cylinder(bore_b / 2.0, length + 2)

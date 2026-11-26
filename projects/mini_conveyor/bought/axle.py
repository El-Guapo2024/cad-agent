"""Shoulder bolt used as a pulley axle (ISO 7379 class, 6 mm shoulder): through the rail, the pulley turning on its
shoulder. Axis along y; y 0 at the head's underside, the shoulder running -y into the rail. UNVERIFIED sizes.
"""
from build123d import Cylinder, Pos, Rot

SOURCE = "class-typical ISO 7379 shoulder bolt, 6 mm shoulder, head 10 x 4.5; choose length to the rail"
VENDOR = None
VERIFIED = False

PARAMS = {"shoulder": 6.0, "length": 18.0, "head": 10.0, "head_t": 4.5}


def build(shoulder, length, head, head_t):
    b = Pos(0, -length / 2.0, 0) * Rot(90, 0, 0) * Cylinder(shoulder / 2.0, length)
    return b + Pos(0, head_t / 2.0, 0) * Rot(90, 0, 0) * Cylinder(head / 2.0, head_t)

"""Sync belt idler bracket: a plate on the rear long beam's back face carrying the idler's axle in a vertical slot,
so sliding the idler down tensions the screws' sync belt. Machined aluminium.

Frame: its -y face at y 0 (against the beam), the idler's axis at x 0, z 0 (mid-slot); the plate runs +y.
"""
from build123d import Box, Cylinder, Pos, Rot

MATERIAL = "aluminium"
PROCESS = "cnc"
MIN_FEATURE_MM = 2.0

PARAMS = {"size_x": 40.0, "thick": 4.0, "z0": -46.0, "z1": 14.0, "slot": 6.0, "slot_l": 10.0}


def build(size_x, thick, z0, z1, slot, slot_l):
    p = Pos(0, thick / 2.0, (z0 + z1) / 2.0) * Box(size_x, thick, z1 - z0)
    p -= Pos(0, thick / 2.0, 0) * Box(slot, thick + 2, slot_l)
    for s in (-1, 1):
        p -= Pos(0, thick / 2.0, s * slot_l / 2.0) * Rot(90, 0, 0) * Cylinder(slot / 2.0, thick + 2)
    return p

"""Pulley: a GT2 timing pulley, drawn at its tip diameter with its hub, for the flip drive (40T on the shaft, 20T on
the motor: 2:1). Along z, the hub below the toothed part. The tip diameter is the pitch diameter (teeth x 2 / pi)
less 0.508 (GT2's pitch line offset, twice 0.254).
"""
from build123d import Cylinder, Pos
import math

MATERIAL = "aluminium"
PROCESS = "cnc"
MIN_FEATURE_MM = 1.0

PARAMS = {"teeth": 40, "width": 7.0, "hub_dia": 16.0, "hub_len": 7.0, "bore": 8.0}


def build(teeth, width, hub_dia, hub_len, bore):
    tip = teeth * 2.0 / math.pi - 0.508
    p = Pos(0, 0, width / 2.0) * Cylinder(tip / 2.0, width) + Pos(0, 0, -hub_len / 2.0) * Cylinder(hub_dia / 2.0,
                                                                                                    hub_len)
    return p - Pos(0, 0, (width - hub_len) / 2.0) * Cylinder(bore / 2.0, width + hub_len + 2)

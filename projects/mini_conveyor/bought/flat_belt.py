"""Endless flat transport belt (antistatic, 4 x 1.5) around pulleys whose centres are `pts` (x, z) and radius `r` (pitch). The loop is the
pulleys' hull, so every pulley must be on it (none inside). Frame: y 0 at the belt's near edge, running +y.
UNVERIFIED: class-typical size; length from the path.
"""
from build123d import Polygon, Pos, Rot, extrude, offset

SOURCE = "class-typical antistatic flat conveyor belt, 4 x 1.5; length from the pulley path"
VENDOR = None
VERIFIED = False

PARAMS = {"pts": ((0.0, 0.0), (100.0, 0.0), (50.0, -30.0)), "r": 10.0, "t": 1.5, "w": 4.0}


def build(pts, r, t, w):
    core = Polygon(*[tuple(p) for p in pts], align=None)
    ring = extrude(offset(core, r + t), w) - extrude(offset(core, r), w)
    return Rot(90, 0, 0) * ring              # XY to XZ; the turn sends the extrusion along +y

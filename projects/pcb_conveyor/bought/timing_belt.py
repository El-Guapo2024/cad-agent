"""Closed GT2 timing belt (6 mm) around pulleys whose centres are `pts` (x, z) and radius `r` (pitch). The loop is the
pulleys' hull, so every pulley must be on it (none inside). Frame: y 0 at the belt's near edge, running +y.
UNVERIFIED: 6 wide, 1.4 thick class-typical; length from the path.
"""
from build123d import Polygon, Pos, Rot, extrude, offset

SOURCE = "GT2 6 mm class (1.38 thick); length from the pulley path"
VENDOR = None
VERIFIED = False

PARAMS = {"pts": ((0.0, 0.0), (100.0, 0.0), (50.0, -30.0)), "r": 6.365, "t": 1.4, "w": 6.0}


def build(pts, r, t, w):
    core = Polygon(*[tuple(p) for p in pts], align=None)
    ring = extrude(offset(core, r + t), w) - extrude(offset(core, r), w)
    return Rot(90, 0, 0) * ring              # XY to XZ; the turn sends the extrusion along +y

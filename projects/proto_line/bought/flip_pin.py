"""A 3 mm dowel pin, ISO 8734 3 m6 x 6, loose: dropped through the carrier's flip holes for side B, it stands on the
nest and its top is flush with the board's. UNVERIFIED stock size. Frame: its bottom at z 0.
"""
from build123d import Cylinder, Pos

SOURCE = "ISO 8734 dowel 3 m6 x 6; any supplier"
VENDOR = None
VERIFIED = False
MATERIAL = "steel"

PARAMS = {"dia": 2.98, "length": 6.0}


def build(dia, length):
    return Pos(0, 0, length / 2.0) * Cylinder(dia / 2.0, length)

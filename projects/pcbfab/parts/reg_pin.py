"""Registration pin: a 3 mm hardened dowel pressed through the hot plate, standing 3 mm proud of the 9.525 plate.

The board's two tooling holes drop over the pair, before and after the flip. 3 mm proud is more than the 1.6 mm
board, and little enough that a tool head hovering a few mm over the board still clears it.
"""
from build123d import Cylinder

MATERIAL = "stainless"
PROCESS = "cnc"
MIN_FEATURE_MM = 3.0

PARAMS = {"dia": 3.0, "length": 12.5}


def build(dia, length):
    return Cylinder(dia / 2.0, length)

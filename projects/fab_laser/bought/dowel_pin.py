"""A 4 mm dowel pin, ISO 8734 4 m6 x 16, hardened: pressed 10 into the nest, 6 standing: flush with the carrier's top, outside the laser's field.
The right-hand one is a 4 mm diamond (relieved) locating pin of the same size; drawn round. UNVERIFIED part numbers.
Frame: its bottom at z 0.
"""
from build123d import Cylinder, Pos

SOURCE = "ISO 8734 dowel 4 m6 x 16 (left); a 4 mm diamond locating pin (right); any supplier"
VENDOR = None
VERIFIED = False
MATERIAL = "steel"

PARAMS = {"dia": 4.0, "length": 16.0}


def build(dia, length):
    return Pos(0, 0, length / 2.0) * Cylinder(dia / 2.0, length)

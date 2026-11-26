"""A 4 mm dowel pin, ISO 8734 4 m6 x 20, hardened: pressed 10 into the nest, 10 standing: through the carrier (6) and up into the stencil frame.
The right-hand one is a 4 mm diamond (relieved) locating pin of the same size; drawn round. UNVERIFIED part numbers.
Frame: its bottom at z 0.
"""
from build123d import Cylinder, Pos

SOURCE = "ISO 8734 dowel 4 m6 x 20 (left); a 4 mm diamond locating pin (right); any supplier"
VENDOR = None
VERIFIED = False
MATERIAL = "steel"

PARAMS = {"dia": 4.0, "length": 20.0}


def build(dia, length):
    return Pos(0, 0, length / 2.0) * Cylinder(dia / 2.0, length)

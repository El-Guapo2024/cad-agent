"""t8_screw: a Tr8x2 single-start lead screw (self-locking; see t8_nut.py), drawn at its 8 mm outside diameter
(no thread), along z centred.
"""
from build123d import Cylinder

SOURCE = "Tr8x8 lead screw for the Handsontec T8 copper nut (8 mm, 4-start, 2 mm pitch, 8 mm lead): https://handsontec.com/dataspecs/linear%20motion/T8-Copper-Nut.pdf"
VENDOR = "Handsontec"
VERIFIED = True

PARAMS = {"dia": 8.0, "length": 175.0}


def build(dia, length):
    return Cylinder(dia / 2.0, length)

"""t8_nut: Tr8x8 brass flange nut (Handsontec MCH1178), flange 22 x 3.5, body 10.2, 15 long

Bought part, an envelope along z, the flange's face at z = 0 and the body below it.
"""
from build123d import Cylinder, Pos

SOURCE = "Handsontec T8 copper nut data sheet: flange 22, body 10.2, length 15, flange 3.5, bolt circle 16, 4 x 3.5: https://handsontec.com/dataspecs/linear%20motion/T8-Copper-Nut.pdf"
VENDOR = "Handsontec"
VERIFIED = True

PARAMS = {"flange": 22.0, "flange_t": 3.5, "body": 10.2, "length": 15.0, "bore": 8.0}


def build(flange, flange_t, body, length, bore):
    n = Pos(0, 0, -flange_t / 2.0) * Cylinder(flange / 2.0, flange_t)
    n += Pos(0, 0, -length / 2.0) * Cylinder(body / 2.0, length - 0.01)
    return n - Pos(0, 0, -length / 2.0) * Cylinder(bore / 2.0 + 0.1, length + 2)

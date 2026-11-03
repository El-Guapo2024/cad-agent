"""t8_nut: a single-start Tr8x2 brass flange nut (DIN 103), drawn at the Tr8x8 nut's envelope (Handsontec MCH1178,
flange 22 x 3.5, body 10.2, 15 long)

A vertical axis takes Tr8x2, not Tr8x8: its 5.2 degree helix is under bronze-on-steel's ~8.5 degree friction angle,
so the screw holds its load with the motor off (the 15 kg bridge, the platen, the tools would run down a Tr8x8's
20 degrees). No Tr8x2 flange nut's drawing was found, so the envelope is the Tr8x8 nut's, UNVERIFIED; Essentra's
TR8x1.5 bronze nut (20 flange, single start) is the fallback (essentracomponents.com, flanged bronze nuts).

Bought part, an envelope along z, the flange's face at z = 0 and the body below it.
"""
from build123d import Cylinder, Pos

SOURCE = "Handsontec T8 copper nut data sheet: flange 22, body 10.2, length 15, flange 3.5, bolt circle 16, 4 x 3.5: https://handsontec.com/dataspecs/linear%20motion/T8-Copper-Nut.pdf"
VENDOR = "Handsontec"
VERIFIED = False

PARAMS = {"flange": 22.0, "flange_t": 3.5, "body": 10.2, "length": 15.0, "bore": 8.0}


def build(flange, flange_t, body, length, bore):
    n = Pos(0, 0, -flange_t / 2.0) * Cylinder(flange / 2.0, flange_t)
    n += Pos(0, 0, -length / 2.0) * Cylinder(body / 2.0, length - 0.01)
    return n - Pos(0, 0, -length / 2.0) * Cylinder(bore / 2.0 + 0.1, length + 2)

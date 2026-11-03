"""coupling: Oriental Motor MCL200508 flexible coupling, 5 mm to 8 mm, OD 20 x 29

Bought part, an envelope: a cylinder along z centred on its middle, bored 5 from below (the motor's shaft) and 8
from above (the screw's journal), each half its length.
"""
from build123d import Cylinder, Pos

SOURCE = "Oriental Motor MCL200508: OD 20, length 29, 5 Nm: https://catalog.orientalmotor.com/item/all-categories-accessories-peripherals/flexible-couplings/mcl200508"
VENDOR = "Oriental Motor"
VERIFIED = True

PARAMS = {"dia": 20.0, "length": 29.0, "bore_a": 5.0, "bore_b": 8.0}


def build(dia, length, bore_a, bore_b):
    c = Cylinder(dia / 2.0, length)
    c -= Pos(0, 0, -length / 4.0) * Cylinder(bore_a / 2.0, length / 2.0 + 0.01)
    return c - Pos(0, 0, length / 4.0) * Cylinder(bore_b / 2.0, length / 2.0 + 0.01)

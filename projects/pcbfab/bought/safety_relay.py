"""safety_relay: Omron G9SE-201 safety relay: the door switches, key switch and e-stop cut the laser and the UV lamps through it

Bought part, an envelope: its box, its base at z = 0.
"""
from build123d import Box, Pos

SOURCE = "Omron G9SE-201: 17.5 W x 111.6 D, approx. 150 g; its height is not readable on the drawing, 100 reserved: https://datasheet.chipsmall.com/G9SE-201/340981.pdf"
VENDOR = "Omron"
VERIFIED = False
MASS_G = 150.0
MASS_SOURCE = "Omron G9SE data sheet: approx. 150 g"
PARAMS = {"length": 17.5, "width": 111.6, "height": 100.0}


def build(length, width, height):
    return Pos(0, 0, height / 2.0) * Box(length, width, height)

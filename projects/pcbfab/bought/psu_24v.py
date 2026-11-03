"""psu_24v: Mean Well LRS-350-24, 24 V 14.6 A: motion, vacuum pump and valve, fans, the head's dispensers and sensor

Bought part, an envelope: its box, its base at z = 0.
"""
from build123d import Box, Pos

SOURCE = "Mean Well LRS-350-24: 215 x 115 x 30 mm, 0.76 kg (distributor listing): https://www.power-supplies-australia.com.au/mean-well-lrs-350-24-enclosed-power-supply ; 3D: https://www.meanwell.com/upload/pdf/LRS-350/LRS-350-3D.zip"
VENDOR = "Mean Well"
VERIFIED = True
MASS_G = 760.0
MASS_SOURCE = "distributor listing: 0.76 kg"
PARAMS = {"length": 215.0, "width": 115.0, "height": 30.0}


def build(length, width, height):
    return Pos(0, 0, height / 2.0) * Box(length, width, height)

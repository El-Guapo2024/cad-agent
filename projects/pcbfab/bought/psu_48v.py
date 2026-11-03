"""psu_48v: Mean Well LRS-600-48, 48 V 12.5 A: the three 395 nm UV lamps (48 V 3 A each)

Bought part, an envelope: its box, its base at z = 0.
"""
from build123d import Box, Pos

SOURCE = "Mean Well LRS-600-48: 225 x 124 x 41 mm, 0.95 kg (distributor listing): https://www.power-supplies-australia.com.au/mean-well-lrs-600-48-enclosed-power-supply"
VENDOR = "Mean Well"
VERIFIED = True
MASS_G = 950.0
MASS_SOURCE = "distributor listing: 0.95 kg"
PARAMS = {"length": 225.0, "width": 124.0, "height": 41.0}


def build(length, width, height):
    return Pos(0, 0, height / 2.0) * Box(length, width, height)

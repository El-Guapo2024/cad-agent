"""psu_12v: Mean Well LRS-350-12, 12 V 29 A: the JPT Lark UV source (12 V DC, under 200 W)

Bought part, an envelope: its box, its base at z = 0.
"""
from build123d import Box, Pos

SOURCE = "Mean Well LRS-350-12, drawn as LRS-350-24's 215 x 115 x 30 case (the LRS-350 family's; not checked for the 12 V model): https://www.power-supplies-australia.com.au/mean-well-lrs-350-24-enclosed-power-supply"
VENDOR = "Mean Well"
VERIFIED = False

PARAMS = {"length": 215.0, "width": 115.0, "height": 30.0}


def build(length, width, height):
    return Pos(0, 0, height / 2.0) * Box(length, width, height)

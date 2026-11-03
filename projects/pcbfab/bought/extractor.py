"""extractor: BOFA V250 fume extractor: HEPA (99.997 % at 0.3 um) and 2 kg activated carbon, 180 m3/h, 115 V 135 W

Bought part, an envelope: its box, its base at z = 0.
"""
from build123d import Box, Pos

SOURCE = "BOFA V250 data sheet: 420 H x 290 W x 270 D, 180 m3/h at 30 mbar, 135 W 115 V, 10 kg, 50 mm duct: https://cdn.shopify.com/s/files/1/0575/0872/4908/files/V-250.pdf"
VENDOR = "BOFA"
VERIFIED = True
MASS_G = 10000.0
MASS_SOURCE = "BOFA V250 data sheet: 10 kg"
PARAMS = {"length": 290.0, "width": 270.0, "height": 420.0}


def build(length, width, height):
    return Pos(0, 0, height / 2.0) * Box(length, width, height)

"""rtd_amp: Adafruit MAX31865 PT1000 amplifier (product 3648), the platen's temperature

Bought part, an envelope: its box, its base at z = 0.
"""
from build123d import Box, Pos

SOURCE = "Adafruit 3648: 28.0 x 25.0 x 2.4 mm, 2.6 g: https://www.adafruit.com/product/3648"
VENDOR = "Adafruit"
VERIFIED = True
MASS_G = 2.6
MASS_SOURCE = "Adafruit product page: 2.6 g"
PARAMS = {"length": 28.0, "width": 25.0, "height": 2.4}


def build(length, width, height):
    return Pos(0, 0, height / 2.0) * Box(length, width, height)

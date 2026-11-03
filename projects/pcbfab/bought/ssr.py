"""ssr: Omron G3NA-210B solid-state relay, the platen heater's switch (zero cross)

Bought part, an envelope: its box, its base at z = 0.
"""
from build123d import Box, Pos

SOURCE = "Omron G3NA data sheet, G3NA-210B: 58 max x 43 max x 27 max, two M4 at 47.6, approx. 60 g: https://lh.pe/file/G3NA.pdf"
VENDOR = "Omron"
VERIFIED = True
MASS_G = 60.0
MASS_SOURCE = "Omron G3NA data sheet: approx. 60 g"
PARAMS = {"length": 58.0, "width": 43.0, "height": 27.0}


def build(length, width, height):
    return Pos(0, 0, height / 2.0) * Box(length, width, height)

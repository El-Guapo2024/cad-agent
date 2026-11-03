"""heatsink: Omron Y92B-N50 DIN-track heat sink for the hot plate's SSR

Bought part, an envelope: its box, its base at z = 0.
"""
from build123d import Box, Pos

SOURCE = "Omron G3NA data sheet, Y92B-N50: 100 max x 47 max x 51 max, approx. 200 g: https://lh.pe/file/G3NA.pdf"
VENDOR = "Omron"
VERIFIED = False
MASS_G = 200.0
MASS_SOURCE = "Omron G3NA data sheet: approx. 200 g"
PARAMS = {"length": 100.0, "width": 47.0, "height": 51.0}


def build(length, width, height):
    return Pos(0, 0, height / 2.0) * Box(length, width, height)

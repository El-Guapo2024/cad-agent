"""height_sensor: Panasonic HG-C1030 laser displacement sensor, 30 +/- 5 mm, 10 um repeatability

Bought part, an envelope: W 20 x D 25 x H 44 (a search excerpt of Panasonic's drawing, UNVERIFIED), its emitting
face at z = 0 (the bottom). Reads the board's height for the laser's focus and the flatness map, as CircuitJet IV's.
"""
from build123d import Box, Pos

SOURCE = "Panasonic HG-C1030: 30 +/- 5 mm, 10 um, 30 g without cable, 24 V DC, Class 2 655 nm: https://industry.panasonic.com/global/en/products/fasys/sensor/photoelectric/hg-c1000l ; W20 x H44 x D25 from a search excerpt (drawing not read)"
VENDOR = "Panasonic"
VERIFIED = False
MASS_G = 30.0
MASS_SOURCE = "Panasonic HG-C1000 series page: 30 g without cable"

PARAMS = {"width": 20.0, "depth": 25.0, "height": 44.0}


def build(width, depth, height):
    return Pos(0, 0, height / 2.0) * Box(width, depth, height)

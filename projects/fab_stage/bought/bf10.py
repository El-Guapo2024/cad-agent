"""bf10: BF10 floating-end support (608ZZ, 8 mm shaft), Aluflex

Bought part, an envelope: L 20 along the screw (x here), B 60, H 39, the bore at h 22. Base at z = 0.
"""
from build123d import Box, Cylinder, Pos, Rot

SOURCE = "Aluflex bearing unit BF10: L 20, B 60, H 39, h 22, b 30, P 46, 608ZZ, 0.3 kg: https://www.aluflex.com/productcategory/bearing-unit-bf/"
VENDOR = "Aluflex"
VERIFIED = True
MASS_G = 300.0
MASS_SOURCE = "Aluflex BF10 page: 0.3 kg"

PARAMS = {"length": 20.0, "width": 60.0, "height": 39.0, "centre": 22.0, "bore": 8.0}


def build(length, width, height, centre, bore):
    b = Pos(0, 0, height / 2.0) * Box(length, width, height)
    return b - Pos(0, 0, centre) * Rot(0, 90, 0) * Cylinder(bore / 2.0, length + 2)

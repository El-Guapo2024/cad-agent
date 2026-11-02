"""bk10: BK10 fixed-end support for a 12 mm ball screw (Sorotec 0510-003-0106, two 7000AC bearings)

Bought part, an envelope: L 40 along the screw (x here), B 60 across, H 39, the bore 10 at h 22 above its base.
The base is z = 0; the screw's axis is the line y = 0, z = 22.
"""
from build123d import Box, Cylinder, Pos, Rot

SOURCE = "Sorotec BK bearing block data sheet, BK10: d1 10, L 40, B 60, H 39, h 22, P 46, holes 6.6 / 5.5: https://www.upload.sorotec.de/doku/manuals/Datasheet_BearingBlock_BK_en_210119_soro.pdf"
VENDOR = "Sorotec"
VERIFIED = True

PARAMS = {"length": 40.0, "width": 60.0, "height": 39.0, "centre": 22.0, "bore": 10.0}


def build(length, width, height, centre, bore):
    b = Pos(0, 0, height / 2.0) * Box(length, width, height)
    return b - Pos(0, 0, centre) * Rot(0, 90, 0) * Cylinder(bore / 2.0, length + 2)

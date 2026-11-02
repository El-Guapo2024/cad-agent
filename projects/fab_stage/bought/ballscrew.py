"""ballscrew: SFU1204 rolled ball screw (Sorotec, C7), 12 mm, 4 mm lead, with its ends machined for BK10/BF10

Bought part, an envelope along z: from z = 0 at the motor end, the 8 h6 journal into the coupling, the 10 section
through the BK10 fixed support, the 12 screw, and the 8 journal of the floating end into the BF10. The threads are
not drawn. The journal lengths are ordered to fit (Sorotec machines the ends to the drawing): the coupling's half and
the BK10's 40 plus 1.
"""
from build123d import Cylinder, Pos

SOURCE = "Sorotec ball screw data sheet, SFU1204: 12 mm, 4 mm lead, fixed end 8 h6 / 10, floating end 8: https://www.upload.sorotec.de/doku/manuals/Datasheet_Ball_Spindles_en_Soro.pdf"
VENDOR = "Sorotec"
VERIFIED = True

PARAMS = {"length": 300.0, "dia": 12.0, "drive": 14.5, "drive_dia": 8.0, "fixed": 41.0, "fixed_dia": 10.0,
          "float_len": 10.0, "float_dia": 8.0}


def build(length, dia, drive, drive_dia, fixed, fixed_dia, float_len, float_dia):
    z, s = 0.0, None
    for d, l in ((drive_dia, drive), (fixed_dia, fixed), (dia, length), (float_dia, float_len)):
        c = Pos(0, 0, z + l / 2.0) * Cylinder(d / 2.0, l)
        s = c if s is None else s + c
        z += l
    return s

"""ballnut: SFU1204 ball screw nut (Sorotec 1001-204-xxxx, C7), flange 42, body 24 x 35 long

Bought part, an envelope: the flange (8 thick, two flats 30 apart) and the body, along z with the flange face at z = 0
and the body below it, bored to the screw's 12. Four 4.5 mm holes on a 32 mm circle bolt it to the carriage's nut bracket.
"""
from build123d import Box, Cylinder, Pos

SOURCE = "Sorotec ball screw data sheet, SFU1204 nut: DN1 42, DN2 32, DN3 24, LN 35, FN 8, BN 30, 4 x 4.5: https://www.upload.sorotec.de/doku/manuals/Datasheet_Ball_Spindles_en_Soro.pdf"
VENDOR = "Sorotec"
VERIFIED = True

PARAMS = {"flange": 42.0, "flats": 30.0, "flange_t": 8.0, "body": 24.0, "length": 35.0, "bolt_circle": 32.0,
          "bolt": 4.5, "bore": 12.0}


def build(flange, flats, flange_t, body, length, bolt_circle, bolt, bore):
    f = Pos(0, 0, -flange_t / 2.0) * (Cylinder(flange / 2.0, flange_t) & Box(flange, flats, flange_t))
    for x, y in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
        r = bolt_circle / 2.0 / 2 ** 0.5
        f -= Pos(x * r, y * r, -flange_t / 2.0) * Cylinder(bolt / 2.0, flange_t + 2)
    n = f + Pos(0, 0, -length / 2.0) * Cylinder(body / 2.0, length - 0.01)
    return n - Pos(0, 0, -length / 2.0) * Cylinder(bore / 2.0, length + 2)      # the screw's outside diameter

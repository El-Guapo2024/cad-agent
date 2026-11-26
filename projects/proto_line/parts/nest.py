"""A station's nest: the plate every station (laser, paste, LumenPnP) carries, that the carrier drops onto by hand.
Machined aluminium, 10 thick, bolted to the station's bed.

Two pins pressed in at the carrier's tooling holes locate it (bought: a round 4 mm dowel on the left, a diamond pin
on the right, so the pair locates without binding on the holes' spacing error: the usual two-pin jig practice).
The carrier lies flat on the plate; the flip pins dropped through the carrier stand on it.

Mounting: four 5.5 holes, counterbored 9.5 x 5.5 for M5 socket heads, at 85 x 75 from the middle: to be matched
to each station's bed (UNVERIFIED for the LumenPnP and the laser; slotted adapters if they differ).

Frame: the plate's top at z 0, the carrier's front edge at y 0, centred in x.
"""
from build123d import Box, Cylinder, Pos

MATERIAL = "aluminium"
PROCESS = "cnc"
MIN_FEATURE_MM = 2.0

PARAMS = {"size_x": 200.0, "front": 10.0, "back": 180.0, "thick": 10.0, "pin": 4.0, "pin_edge": 7.62,
          "pin_x": 70.0, "bolt": 5.5, "cbore": 9.5, "cbore_d": 5.5, "bolt_x": 85.0, "bolt_y": 75.0}


def build(size_x, front, back, thick, pin, pin_edge, pin_x, bolt, cbore, cbore_d, bolt_x, bolt_y):
    ymid = (back - front) / 2.0
    n = Pos(0, ymid, -thick / 2.0) * Box(size_x, back + front, thick)
    for sx in (-1, 1):
        n -= Pos(sx * pin_x, pin_edge, -thick / 2.0) * Cylinder(pin / 2.0, thick + 2)      # press fit, pins bought
        for sy in (-1, 1):
            x, y = sx * bolt_x, 85.0 + sy * bolt_y
            n -= Pos(x, y, -thick / 2.0) * Cylinder(bolt / 2.0, thick + 2)
            n -= Pos(x, y, -cbore_d / 2.0 + 0.005) * Cylinder(cbore / 2.0, cbore_d + 0.01)
    return n

"""Rear rail carriage: carries the moving rear rail on a linear guide block and takes the lead screw's nut, so turning
the screws moves the rail across (SMEMA: the rear rail is the adjustable one). Machined aluminium.

Frame: its top at z 0 (the rail's bottom), y 0 at the rail's inner face (the carriage runs back in +y under the
rail), x 0 on the guide's centre. The nut boss hangs at +x over the lead screw, bored for a flanged trapezoidal nut.
"""
from build123d import Box, Cylinder, Pos, Rot

MATERIAL = "aluminium"
PROCESS = "cnc"
MIN_FEATURE_MM = 2.0

PARAMS = {"plate_t": 17.0, "size_y": 40.0, "x0": -15.0, "x1": 47.0, "screw_x": 30.0, "screw_z": -14.0,
          "boss_w": 32.0, "boss_bot": -28.0, "nut_bore": 22.0}


def build(plate_t, size_y, x0, x1, screw_x, screw_z, boss_w, boss_bot, nut_bore):
    c = Pos((x0 + x1) / 2.0, size_y / 2.0, -plate_t / 2.0) * Box(x1 - x0, size_y, plate_t)
    c += Pos(screw_x, size_y / 2.0, boss_bot / 2.0) * Box(boss_w, size_y, -boss_bot)
    c -= Pos(screw_x, size_y / 2.0, screw_z) * Rot(90, 0, 0) * Cylinder(nut_bore / 2.0, size_y + 2)
    return c

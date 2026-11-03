"""motion_board: BIGTREETECH Octopus Pro: Klipper's MCU for LumenPnP's, the stage's, the lifts' and the bridge's steppers and the I/O

Bought part, an envelope: its box, its base at z = 0.
"""
from build123d import Box, Pos

SOURCE = "BIGTREETECH Octopus Pro: board 160 x 100 mm, holes 150 x 90 (wiki); its height with drivers is not published, 25 reserved: https://global.bttwiki.com/Octopus%20Pro.html"
VENDOR = "BIGTREETECH"
VERIFIED = False

PARAMS = {"length": 160.0, "width": 100.0, "height": 25.0}


def build(length, width, height):
    return Pos(0, 0, height / 2.0) * Box(length, width, height)

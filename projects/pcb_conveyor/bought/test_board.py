"""The board as it rides, for the clearance checks: W - 1 wide (0.5 off each rail's face), 1.6 thick, its bottom on
the belts. Not a part to buy; it stands for the carrier until the carrier is designed. Frame: its bottom at z 0,
its front edge at y 0, centred in x.
"""
from build123d import Box, Pos

SOURCE = "a 1.6 mm board (MG Chemicals 555 class), sized to the rails' gap; stands in for the carrier"
VENDOR = None
VERIFIED = True

PARAMS = {"length": 150.0, "width": 169.0, "thick": 1.6}


def build(length, width, thick):
    return Pos(0, width / 2.0, thick / 2.0) * Box(length, width, thick)

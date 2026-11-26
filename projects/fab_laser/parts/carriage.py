"""The Z carriage: an aluminium plate bolted to the two guide blocks on the column's rail; the laser arm hangs off its
front and the nut block off its back. Frame: its back face (on the blocks) at y 0, running -y; centred in x and z.
"""
from build123d import Box, Pos

MATERIAL = "aluminium"
PROCESS = "cnc"
MIN_FEATURE_MM = 2.0

PARAMS = {"w": 100.0, "h": 140.0, "t": 10.0}


def build(w, h, t):
    return Pos(0, -t / 2.0, 0) * Box(w, t, h)

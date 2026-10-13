"""Tool plate: the printed plate that rides on the carriage and carries the motor.

50 x 40 x 4 mm of PETG, with four M3 clearance holes on the carriage's 20 x 20 mm pattern. The motor lies on it
along x and is held by its own clamp, which is not modelled. Printed flat on its 50 x 40 face, so it has no overhang.
"""
from build123d import Box, Cylinder, Pos
from cad_agent.parts import CLEARANCE_HOLE

MATERIAL = "petg"
PROCESS = "fdm"
MIN_FEATURE_MM = 1.2
EXPECT_FEATURES = 4         # the four bolt holes

PARAMS = {
    "length": 50.0,         # along the beam
    "width": 40.0,
    "thickness": 4.0,
    "pitch": 20.0,          # the MGN12H block's four M3 holes are 20 x 20 apart
    "screw": "M3",
}


def build(length, width, thickness, pitch, screw):
    body = Box(length, width, thickness)
    for sx in (-1, 1):
        for sy in (-1, 1):
            body -= Pos(sx * pitch / 2.0, sy * pitch / 2.0, 0) * Cylinder(CLEARANCE_HOLE[screw] / 2.0, thickness + 2.0)
    return body

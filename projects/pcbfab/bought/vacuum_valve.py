"""vacuum_valve: SMC VT307V-5G1-01 3-port solenoid valve, vacuum version, 24 V DC

Bought part, an envelope: body 33.2 x 29.5 x 54.5 with its 37 wide coil, base at z = 0. Switches the platen between
the pump and air (to let the board go). 0.15 kg.
"""
from build123d import Box, Pos

SOURCE = "SMC VT307 catalogue pp 1433-1436, VT307V-5G1-01: body 33.2 L x 29.5 W x 54.5 H, coil 37 wide, 0.15 kg, -101.2 kPa to 0.1 MPa: https://cdn.snway.cn//pic/20240816/67435ff5110320898bf22871f43962a9.pdf"
VENDOR = "SMC"
VERIFIED = True
MASS_G = 150.0
MASS_SOURCE = "SMC VT307 catalogue: 0.15 kg"

PARAMS = {"length": 33.2, "width": 37.0, "height": 54.5}


def build(length, width, height):
    return Pos(0, 0, height / 2.0) * Box(length, width, height)

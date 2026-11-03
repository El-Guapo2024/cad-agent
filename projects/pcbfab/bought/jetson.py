"""jetson: NVIDIA Jetson Orin Nano Developer Kit: the host (Klipper + Moonraker, cameras and AOI, the laser job, the MCP server)

Bought part, an envelope: its box, its base at z = 0.
"""
from build123d import Box, Pos

SOURCE = "NVIDIA Jetson Orin Nano Developer Kit: 100 x 79 x 21 mm including feet, carrier, module and thermal solution (NVIDIA data sheet, quoted): https://forums.developer.nvidia.com/t/mechanical-dimensions-jetson-orin-nano-development-kit/316529"
VENDOR = "NVIDIA"
VERIFIED = True

PARAMS = {"length": 100.0, "width": 79.0, "height": 21.0}


def build(length, width, height):
    return Pos(0, 0, height / 2.0) * Box(length, width, height)

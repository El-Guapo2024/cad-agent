"""The UV laser's galvo scan head (two mirrors), envelope only: PLACEHOLDER until the laser is chosen. The beam comes
in from the source on its +x side; the f-theta lens screws under it. Frame: its bottom at z 0, the lens axis at x 0
y 0. Sized from typical 10 mm-aperture galvo heads on 3-5 W UV marking machines (UNVERIFIED).
"""
from build123d import Box, Pos

SOURCE = "placeholder: typical 10 mm galvo head on a 3-5 W 355 nm marking machine; replace with the chosen laser's drawing"
VENDOR = None
VERIFIED = False
MATERIAL = "aluminium"

PARAMS = {"x": 110.0, "y": 100.0, "z": 100.0}


def build(x, y, z):
    return Pos(0, 0, z / 2.0) * Box(x, y, z)

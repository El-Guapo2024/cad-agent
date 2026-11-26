"""The 355 nm UV laser source, 3-5 W air-cooled class: PLACEHOLDER envelope. Its beam leaves its -x end straight into
the galvo head, so source and head ride the Z carriage together (UV has no fibre delivery). Frame: its bottom at z 0,
its -x end at x 0, centred in y.
"""
from build123d import Box, Pos

SOURCE = "placeholder: typical 3-5 W 355 nm air-cooled source with beam expander, 340 x 110 x 110 (UNVERIFIED)"
VENDOR = None
VERIFIED = False
MATERIAL = "aluminium"
MASS_G = 9000
MASS_SOURCE = "placeholder: class-typical 3-5 W air-cooled UV source, 8-10 kg (UNVERIFIED)"

PARAMS = {"x": 340.0, "y": 110.0, "z": 110.0}


def build(x, y, z):
    return Pos(x / 2.0, 0, z / 2.0) * Box(x, y, z)

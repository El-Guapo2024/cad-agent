"""cutout: Selco ORA-500-QC disc thermostat, the hot plate's hardware over-temperature cut-out

Bought part. Normally closed, opens at 500 F +/- 20 (249-271 C), UL recognised, about USD 8.75; in series with the
heater's SSR output, so the plate cannot run away whatever the controller does. Its disc face clamps to the plate's
-x edge. The body size is a parts listing's (1.18 x 0.570 x 0.395 in), NOT Selco's drawing, which has the bracket:
https://cn.elcodis.com/parts/5411400/ORA-500-QC.html. The geometry is an envelope.
"""
from build123d import Box

SOURCE = "Selco ORA-500-QC, opens 500 F +/- 20 (249-271 C), 125 VAC 15 A; body 1.18 x 0.570 x 0.395 in per https://cn.elcodis.com/parts/5411400/ORA-500-QC.html (a parts listing; the bracket is on Selco's drawing)"
VENDOR = "Selco"
VERIFIED = False

PARAMS = {"length": 30.0, "width": 14.5, "height": 10.0}


def build(length, width, height):
    return Box(length, width, height)    # length along y, width along z, height (out of the disc face) along x

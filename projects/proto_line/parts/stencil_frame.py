"""The paste station's stencil frame: a printed stiffener the mylar foil is taped under, so the foil lies flat on
the board and the carrier (the board is flush with the carrier's top, which is what makes this work). The frame's
holes clear the nest's pins (4.6 on 4.0); the foil's own holes, cut by the UV laser in the same job as its
apertures, are what register it. A 150 window over the board; the squeegee runs inside it.

Frame: the frame's bottom at z 0 (the foil's top), the carrier's front edge at y 0, centred in x.
"""
from build123d import Box, Cylinder, Pos

MATERIAL = "petg"
PROCESS = "fdm"
MIN_FEATURE_MM = 1.2

PARAMS = {"size_x": 196.0, "size_y": 176.0, "y0": -3.0, "thick": 4.0, "window": 152.0, "board_y": 85.0,
          "pin_x": 70.0, "pin_edge": 7.62, "hole": 4.6}


def build(size_x, size_y, y0, thick, window, board_y, pin_x, pin_edge, hole):
    f = Pos(0, y0 + size_y / 2.0, thick / 2.0) * Box(size_x, size_y, thick)
    f -= Pos(0, board_y, thick / 2.0) * Box(window, window, thick + 2)
    for sx in (-1, 1):
        f -= Pos(sx * pin_x, pin_edge, thick / 2.0) * Cylinder(hole / 2.0, thick + 2)
    return f

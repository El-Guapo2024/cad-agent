"""Base: a tray with four standoffs under the board and a window for the USB plug.

The board rests on four standoffs 6.0 mm tall, each with a 2.5 mm hole (the M3
tapping drill, 5 mm deep). Their positions are read from the given board's own
mounting holes instead of being typed: the UNO's lower-left hole sits 1.3 mm
nearer the edge than its upper-left twin, so a remembered rectangle is wrong.

The inner faces stand 0.8 mm off the board on three sides. On the USB side the
wall is 1.0 mm beyond the socket's front face, so the plug's housing passes
through it. The window is 14.0 x 13.0 mm round a plug of 11.4 x 10.5, which
leaves 1.3 mm on every side.
"""
from build123d import Box, Cylinder, Pos

from cad_agent.spec import holes
from cad_agent.state import bought_solid

SLUG = "pcb_enclosure"

MATERIAL = "petg"
PROCESS = "fdm"
MIN_FEATURE_MM = 1.2

PARAMS = {
    "wall": 2.4,
    "floor": 2.0,
    "inner_x_min": -41.7,    # 1.0 mm beyond the socket's front face
    "inner_x_max": 35.1,     # 0.8 mm beyond the board's right edge
    "inner_y": 27.47,        # half width, 0.8 mm beyond the board's long edges
    "inner_h": 20.8,         # floor top to the lid's underside: 2.2 above the jack
    "standoff_h": 6.0,       # floor top to the underside of the board
    "standoff_d": 7.5,
    "tap_d": 2.5,            # M3 tapping drill, `cad tables`
    "tap_depth": 5.0,
    "window_y": 11.43,       # plug axis across the board
    "window_z": 13.0,        # plug axis above the floor
    "window_w": 14.0,
    "window_h": 13.0,
}


def board_holes():
    """Mounting hole centres of the given board, in its own frame."""
    found = holes(bought_solid(SLUG, "arduino_uno_r3"))
    return sorted((round(h["point"].X, 3), round(h["point"].Y, 3)) for h in found)


def build(wall, floor, inner_x_min, inner_x_max, inner_y, inner_h, standoff_h,
          standoff_d, tap_d, tap_depth, window_y, window_z, window_w, window_h):
    x0, x1, y1 = inner_x_min - wall, inner_x_max + wall, inner_y + wall
    tray = Pos((x0 + x1) / 2.0, 0, (inner_h - floor) / 2.0) * Box(
        x1 - x0, 2.0 * y1, inner_h + floor)
    tray -= Pos((inner_x_min + inner_x_max) / 2.0, 0, inner_h / 2.0 + 0.5) * Box(
        inner_x_max - inner_x_min, 2.0 * inner_y, inner_h + 1.0)

    for x, y in board_holes():
        tray += Pos(x, y, standoff_h / 2.0) * Cylinder(standoff_d / 2.0, standoff_h)
        tray -= Pos(x, y, standoff_h - tap_depth / 2.0 + 0.5) * Cylinder(
            tap_d / 2.0, tap_depth + 1.0)

    # The plug's window, cut through the wall on the USB side.
    tray -= Pos(x0 + wall / 2.0, window_y, window_z) * Box(wall + 2.0, window_w, window_h)
    return tray

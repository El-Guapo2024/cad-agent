"""Arduino UNO R3 board: outline, mounting holes, and the tall connectors.

Modelled as the envelope a chassis has to mount and clear, not as a board.
The two tall parts, the USB-B socket and the barrel jack, overhang the left
edge and are what actually collide with things, so they are included.

Mounting holes come straight off the official drawing, and the four figures
below are read from it rather than recalled. Datum is the top-left corner of
the board, x to the right and y downward, which is how the drawing dimensions
them:

    4 x 3.20 mm holes
    left pair    x = 15.24,  y = 2.54 and 50.80
    right pair   x = 66.04,  y = 17.78 and 45.72

Cross-check that they are consistent: measured from the bottom edge of a
53.34 mm board these become (15.24, 50.80), (15.24, 2.54), (66.04, 35.56) and
(66.04, 7.62), which is the standard R3 pattern shields are built to.

VERIFIED is False for one reason only: page 12 dimensions the holes but not
the board outline, so 68.58 x 53.34 and the corner chamfer did not come from
the drawing. The holes are what the chassis mounts to and those are solid;
the outline only affects clearance. Confirm it with callipers on a real board.
"""
from build123d import Box, Cylinder, Pos

SOURCE = ("Arduino UNO R3 User Manual, SKU A000066, section 5.4 Board Outline "
          "& Mounting Holes, page 12 (modified 07/09/2026), read from the "
          "drawing at 420 dpi. Outline dimensions are NOT on that page.")
VENDOR = "Arduino S.r.l."
VERIFIED = False

PARAMS = {
    "length": 68.58,
    "width": 53.34,
    "pcb_thickness": 1.6,
    "hole_dia": 3.20,
    "usb_w": 16.0, "usb_d": 12.0, "usb_h": 11.0,
    "jack_w": 14.0, "jack_d": 9.0, "jack_h": 11.0,
    "header_h": 9.0,
}

# Hole centres from the top-left corner of the board, y downward.
HOLES = [(15.24, 2.54), (15.24, 50.80), (66.04, 17.78), (66.04, 45.72)]


def hole_positions(length=PARAMS["length"], width=PARAMS["width"]):
    """Hole centres in the board's own centred coordinates, for a chassis to use."""
    return [(x - length / 2.0, width / 2.0 - y) for x, y in HOLES]


def build(length, width, pcb_thickness, hole_dia,
          usb_w, usb_d, usb_h, jack_w, jack_d, jack_h, header_h):
    board = Box(length, width, pcb_thickness)
    for cx, cy in hole_positions(length, width):
        board -= Pos(cx, cy, 0) * Cylinder(hole_dia / 2.0, pcb_thickness + 2)

    # Connectors sit on top and overhang the left edge, which is the side that
    # has to stay clear of anything the chassis puts next to it.
    top = pcb_thickness / 2.0
    board += Pos(-length / 2.0 - usb_w / 2.0 + 6.0, width / 2.0 - 14.0,
                 top + usb_h / 2.0) * Box(usb_w, usb_d, usb_h)
    board += Pos(-length / 2.0 - jack_w / 2.0 + 5.0, -width / 2.0 + 12.0,
                 top + jack_h / 2.0) * Box(jack_w, jack_d, jack_h)
    # Header strips, as one envelope per side.
    board += Pos(0, width / 2.0 - 3.0, top + header_h / 2.0) * Box(length - 12, 5.0, header_h)
    board += Pos(0, -width / 2.0 + 3.0, top + header_h / 2.0) * Box(length - 20, 5.0, header_h)
    return board

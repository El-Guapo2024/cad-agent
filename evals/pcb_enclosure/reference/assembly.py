"""The UNO in its box, with the USB cable plugged in.

Coordinates are the given board's own frame lifted by 6.0 mm: z = 0 is the
floor's top face, the board's underside is z = 6.0, the top of the standoffs.
+x runs along the long edge, the USB socket is at -x, and the plug leaves the
box through the window in the -x wall.

The board and the plug are placed with the same transform, so the plug stays
seated in the socket. The base and the lid are built in these coordinates.
"""
from build123d import Pos

from cad_agent.state import build_part, bought_solid

SLUG = "pcb_enclosure"
BOARD_Z = 6.0

CLEARANCE = {
    "lid|pcb": 1.5,          # the lid stays this far off the tallest part, the DC jack
    "base|usb_plug": 1.0,    # the window leaves room round the plug
    "lid|usb_plug": 1.0,
}

ALLOW_CONTACT = {
    "base|pcb",              # the board rests on the standoffs
    "base|lid",              # the lid sits on the walls
    "pcb|usb_plug",          # the plug is seated in the socket
}


def parts():
    base, _ = build_part(SLUG, "base")
    lid, _ = build_part(SLUG, "lid")
    lift = Pos(0, 0, BOARD_Z)
    return {
        "base": base,
        "lid": lid,
        "pcb": lift * bought_solid(SLUG, "arduino_uno_r3"),
        "usb_plug": lift * bought_solid(SLUG, "usb_b_plug"),
    }

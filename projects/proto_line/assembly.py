"""The bare-bones 2-layer prototype line (2026-11-26): the board rides one carrier, carried by hand from station to
station; every station has the same nest, so the board is in the same place under the laser, the stencil and the
LumenPnP. Drawn here: the paste station, the fullest stack (nest, carrier, board on side B with its flip pins,
stencil foil and frame).

The line, and whose ideas each station takes:
  1. UV laser, side A: isolate the copper, drill the holes and the two flip holes. Bought laser; the nest on a
     riser at its focus (height to the laser's working distance, not yet known).
  2. Turn the board over about y, drop the flip pins in, laser side B. (Flip-pin registration: the usual
     double-sided PCB-milling practice.)
  3. Vias: rivets by hand, or conductive paste through the LumenPnP's dispenser, cured.
  4. Paste: this stack. A mylar stencil cut by the same laser (the DIY-stencil practice: laser-cut mylar; the
     board flush with the carrier, as in commercial stencil jigs, so the foil lies flat).
  5. LumenPnP (Opulo, open source): the nest bolted on its bed; OpenPnP fiducials take out what is left.
  6. Reflow: the board out of the carrier onto a rack in a toaster oven with an open controller (Reflowduino
     class); the 0.5 kg carrier would lag the profile.

Frame: the nest's top at z 0, the carrier's front edge at y 0, centred in x.
"""
from build123d import Pos

from cad_agent.state import build_part, bought_solid

SLUG = "proto_line"

CARRIER_T = 6.0
BOARD_T = 1.6
POCKET_Z = CARRIER_T - BOARD_T
BOARD_Y = 85.0
PIN_X = 70.0
PIN_EDGE = 7.62
FLIP_X = 69.0
FOIL_T = 0.125

CLEARANCE = {}
ALLOW_CONTACT = {
    "carrier|nest", "nest|pin_left", "nest|pin_right", "carrier|pin_left", "carrier|pin_right",
    "foil|pin_left", "foil|pin_right", "board|carrier", "carrier|foil", "board|foil", "foil|stencil_frame",
    *{f"{a}|flip_pin_{s}" for s in ("left", "right") for a in ("nest", "carrier", "board", "foil")},
}

MECHANISM = {"static": {"pin_left": "pressed into the nest", "pin_right": "pressed into the nest",
                        "flip_pin_left": "dropped in for side B", "flip_pin_right": "dropped in for side B"}}


def parts():
    p = lambda n, **o: build_part(SLUG, n, o or None)[0]
    b = lambda n, **o: bought_solid(SLUG, n, **o)
    out = {"nest": p("nest"), "carrier": p("carrier")}
    for s, sx in (("left", -1), ("right", 1)):
        out[f"pin_{s}"] = Pos(sx * PIN_X, PIN_EDGE, -10.0) * b("dowel_pin")
        out[f"flip_pin_{s}"] = Pos(sx * FLIP_X, BOARD_Y, 0) * b("flip_pin")
    out["board"] = Pos(0, BOARD_Y, POCKET_Z) * b("board")
    out["foil"] = Pos(0, 0, CARRIER_T) * b("stencil_foil")
    out["stencil_frame"] = Pos(0, 0, CARRIER_T + FOIL_T) * p("stencil_frame")
    return out

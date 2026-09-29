"""Flat mica heating element clamped under the reflow plate.

Chosen over cartridge heaters after a 2026-09-13 survey found 6 mm cartridge
heaters at 80-100 mm length in mains voltage to be rare: stock is either
6 x 20-50 mm or a diameter too large for a 10 mm plate. A flat element needs
no bores at all, spreads heat over the whole face rather than two lines, and
is the usual choice on DIY reflow plates.

DIMENSIONS ARE UNVERIFIED. Vendor pages for this class of part publish a
wattage and little else, and the survey was blocked from the listings that
might have had more. Confirm every number with callipers on arrival.
"""
from build123d import Box

SOURCE = ("class-typical mica heater for a 100 mm reflow plate; no vendor "
          "page surveyed on 2026-09-13 published a dimensioned drawing")
VENDOR = None
VERIFIED = False

PARAMS = {
    "width": 100.0,
    "depth": 100.0,
    "thickness": 1.5,
}


def build(width, depth, thickness):
    return Box(width, depth, thickness)

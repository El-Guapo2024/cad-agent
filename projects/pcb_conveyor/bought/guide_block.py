"""Miniature linear guide block (MGN12H class) on guide_rail.py. Frame: the rail's bottom at z 0, its top at z h.

DIMENSIONS ARE UNVERIFIED: class-typical MGN12H sizes, to be checked against HIWIN's MGN catalogue page.
"""
from build123d import Box, Pos

SOURCE = "class-typical MGN12H block (width 27, length 45.4, top 13 over the rail's bottom, 3 clear of it); check against HIWIN's MGN catalogue"
VENDOR = None
VERIFIED = False

PARAMS = {"w": 27.0, "l": 45.4, "h": 13.0, "under": 3.0, "rail_w": 12.0, "rail_h": 8.0}


def build(w, l, h, under, rail_w, rail_h):
    b = Pos(0, 0, (h + under) / 2.0) * Box(w, l, h - under)
    return b - Pos(0, 0, rail_h / 2.0) * Box(rail_w + 0.2, l + 2, rail_h + 0.01)

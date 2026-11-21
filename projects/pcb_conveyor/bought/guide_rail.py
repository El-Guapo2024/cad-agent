"""Miniature linear guide rail, 12 mm (MGN12 class), cut to length: the rear rail's carriages run on it.

Axis along y, its bottom at z 0, centred. DIMENSIONS ARE UNVERIFIED: class-typical MGN12 sizes, to be checked against
the maker's catalogue (HIWIN MGN series) before anything is ordered.
"""
from build123d import Box, Pos

SOURCE = "class-typical MGN12 rail (width 12, height 8); check against HIWIN's MGN catalogue page"
VENDOR = None
VERIFIED = False

PARAMS = {"length": 400.0, "w": 12.0, "h": 8.0}


def build(length, w, h):
    return Pos(0, 0, h / 2.0) * Box(w, length, h)

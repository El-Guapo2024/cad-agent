"""Stainless standoff that holds a pinned bed plate 25 mm over its deck or shelf.

Recycled from desk_fab_line's plate_standoff, in stainless instead of G10: it touches a 250 C plate, and stainless
is rated past that and conducts heat poorly for a metal. Thin wall, so little heat reaches the platform.
"""
from build123d import Cylinder
from cad_agent.parts import CLEARANCE_HOLE

MATERIAL = "stainless"
PROCESS = "cnc"
MIN_FEATURE_MM = 2.0

PARAMS = {"height": 25.0, "dia": 8.0, "screw": "M3"}


def build(height, dia, screw):
    return Cylinder(dia / 2.0, height) - Cylinder(CLEARANCE_HOLE[screw] / 2.0, height + 2)

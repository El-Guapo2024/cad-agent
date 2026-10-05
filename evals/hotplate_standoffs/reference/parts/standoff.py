"""Standoff that holds the hot plate 20 mm above the base.

A plain bar with one M3 clearance bore. Polyimide (Vespel SP-1, operating temperature to 300 C
per https://en.wikipedia.org/wiki/Vespel, read 2026-10-04), because the plate runs at 250 C,
which rules out PLA, PETG, ABS and nylon, and because its low conductivity is the point of an
air gap: little heat reaches the base. The screw comes up from under the base through this bore
and threads into the plate's tapped hole, so the plate's top face stays free for the board.
"""
from build123d import Cylinder
from cad_agent.parts import CLEARANCE_HOLE

MATERIAL = "polyimide"
PROCESS = "cnc"             # turned from rod
MIN_FEATURE_MM = 3.3        # wall between the bore and the outside diameter

PARAMS = {
    "height": 20.0,         # the air gap; the bar stands between base top and plate underside
    "od": 10.0,
    "screw": "M3",
}


def build(height, od, screw):
    body = Cylinder(od / 2.0, height)
    body -= Cylinder(CLEARANCE_HOLE[screw] / 2.0, height + 2.0)
    return body

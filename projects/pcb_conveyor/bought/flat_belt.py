"""Endless flat transport belt (antistatic), one per rail, as it runs: over the two end idlers, down and under the
drive pulley and the return idler. Frame as rail.py's: z 0 at the belt's top (the board's bottom); the belt's inner
edge at y 0.5 off the rail's face, running +y.

DIMENSIONS ARE UNVERIFIED: 4 mm wide, 1.5 thick is class-typical for SMT edge conveyors; length from the path.
"""
from build123d import Polygon, Pos, Rot, extrude, offset

SOURCE = "class-typical antistatic flat conveyor belt, 4 x 1.5; length from the pulley path"
VENDOR = None
VERIFIED = False

PARAMS = {"t": 1.5, "w": 4.0, "r": 10.0, "end_x": 290.0, "low_x": 260.0, "top_z": -11.5, "low_z": -50.0, "y0": 0.5}


def build(t, w, r, end_x, low_x, top_z, low_z, y0):
    # the pulley centres, as a polygon in XY (x along, y up), offset by the radius to the belt's inner face
    core = Polygon((-end_x, top_z), (end_x, top_z), (low_x, low_z), (-low_x, low_z), align=None)
    ring = extrude(offset(core, r + t), w) - extrude(offset(core, r), w)
    return Pos(0, y0, 0) * Rot(90, 0, 0) * ring          # XY to XZ; the turn sends the extrusion along +y

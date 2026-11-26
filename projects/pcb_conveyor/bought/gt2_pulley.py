"""GT2 timing pulley (20 tooth class) on each lead screw's rear end: the sync belt keeps the two screws in step, so the
rear rail stays parallel. Axis along y; y 0 at one face, running +y. Drawn at the belt's pitch radius; UNVERIFIED.
"""
from build123d import Cylinder, Pos, Rot

SOURCE = "GT2 20T class: pitch diameter 12.73 (20 x 2 mm / pi), width 6 belt; bore to the screw's journal"
VENDOR = None
VERIFIED = False

PARAMS = {"pitch_dia": 12.73, "width": 6.0, "bore": 12.0}


def build(pitch_dia, width, bore):
    hub = Cylinder(pitch_dia / 2.0, width) - Cylinder(bore / 2.0, width + 2)
    return Pos(0, width / 2.0, 0) * Rot(90, 0, 0) * hub

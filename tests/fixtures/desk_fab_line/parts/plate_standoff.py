"""Ceramic-insulator standoff that carries the hot plate off the box B floor.

Four of these hold the plate at working height while keeping conducted heat
out of the frame. Printed parts would creep at plate temperature, so these are
machined from machinable glass-ceramic or turned from PTFE-free G10 rod. The
shoulder locates in the floor panel; the M3 stud passes up into the plate.
"""
from build123d import Cylinder, Pos, Rot
from cad_agent.parts import CLEARANCE_HOLE

MATERIAL = "fr4"          # G10 rod, same density class
PROCESS = "cnc"
MIN_FEATURE_MM = 2.5      # wall between bore and outside diameter

PARAMS = {
    "height": 25.0,
    "body_dia": 12.0,
    "shoulder_dia": 16.0,
    "shoulder_h": 3.0,
    "screw": "M3",
}


def build(height, body_dia, shoulder_dia, shoulder_h, screw):
    body = Cylinder(body_dia / 2.0, height)
    shoulder = Pos(0, 0, -height / 2.0 + shoulder_h / 2.0) * Cylinder(
        shoulder_dia / 2.0, shoulder_h)
    part = body + shoulder
    # Through bore for the mounting screw.
    part -= Cylinder(CLEARANCE_HOLE[screw] / 2.0, height + 2)
    return part


CUTLIST = [{"kind": "G10 rod 16 mm", "length_mm": 30.0, "qty": 4}]

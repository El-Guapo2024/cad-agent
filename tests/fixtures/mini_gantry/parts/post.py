"""Post: one of the gantry's two uprights, a block of 6061 aluminium that holds the beam 50 mm off the base.

20 x 40 x 50 mm, milled from bar, with two M4 clearance holes along its height for the screws that bolt it to the slide
under it. The holes are on the 40 mm side's middle, 20 mm apart, 10 mm from each end.
"""
from build123d import Box, Cylinder, Pos
from cad_agent.parts import CLEARANCE_HOLE

MATERIAL = "aluminium"
PROCESS = "cnc"
MIN_FEATURE_MM = 7.5        # the wall between a bolt hole and the post's side: (20 - 4.5) / 2 = 7.75

PARAMS = {
    "width": 20.0,          # x: the beam rests on this face
    "depth": 40.0,          # y
    "height": 50.0,         # z
    "hole_pitch": 20.0,     # between the two bolt holes, along y
    "screw": "M4",
}


def build(width, depth, height, hole_pitch, screw):
    body = Box(width, depth, height)
    for sy in (-1, 1):
        body -= Pos(0, sy * hole_pitch / 2.0, 0) * Cylinder(CLEARANCE_HOLE[screw] / 2.0, height + 2.0)
    return body

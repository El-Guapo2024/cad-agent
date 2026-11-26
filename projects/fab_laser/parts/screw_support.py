"""The lead screw's bottom support: a block on the back beam with a bearing bore (a 12 mm bearing, drawn as the bore
the screw's journal runs in). Frame: its bottom at z 0, the bore's axis at x 0 y 0.
"""
from build123d import Box, Cylinder, Pos

MATERIAL = "aluminium"
PROCESS = "cnc"
MIN_FEATURE_MM = 2.0

PARAMS = {"w": 34.0, "d": 34.0, "h": 20.0, "bore": 12.0}


def build(w, d, h, bore):
    return Pos(0, 0, h / 2.0) * (Box(w, d, h) - Cylinder(bore / 2.0, h + 2))

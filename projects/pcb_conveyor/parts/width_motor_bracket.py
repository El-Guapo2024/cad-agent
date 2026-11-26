"""Width stepper bracket: an L whose foot sits on the rear long beam's top and whose upright takes the stepper's
face, the coupler passing through. Machined aluminium.

Frame: the stepper's shaft axis along y at x 0, z 0; the upright's -y face at y 0; the foot runs -y to `foot_y`
and its underside is at z `foot_z`.
"""
from build123d import Box, Cylinder, Pos, Rot

MATERIAL = "aluminium"
PROCESS = "cnc"
MIN_FEATURE_MM = 2.0

PARAMS = {"size_x": 44.0, "thick": 6.0, "top": 26.0, "foot_z": -56.0, "foot_y": -50.0, "foot_t": 6.0,
          "hole": 26.0, "foot_x0": -8.0}


def build(size_x, thick, top, foot_z, foot_y, foot_t, hole, foot_x0):
    up = Pos(0, thick / 2.0, (top + foot_z) / 2.0) * Box(size_x, thick, top - foot_z)
    up -= Rot(90, 0, 0) * Cylinder(hole / 2.0, thick * 3)
    fx = size_x / 2.0 - foot_x0                               # the foot keeps to +x of foot_x0 (clear of the beam)
    foot = Pos(foot_x0 + fx / 2.0, (foot_y + thick) / 2.0, foot_z + foot_t / 2.0) * Box(fx, thick - foot_y, foot_t)
    return up + foot

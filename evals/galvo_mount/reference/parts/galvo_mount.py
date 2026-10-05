"""Mount that holds the galvo head over the bench, standing outside the beam.

An upright with a foot on the bench, an arm across the top and a plate that bolts to
the head's side face. The upright cannot stand close to the head: the beam cone is
106 mm from the axis where it meets the bench (the corner of a 150 mm field), and
narrows to the 30 mm lens only at the top, so anything below the lens that is closer
to the axis than the cone's radius at its height is in the beam. The upright's inner
face is 112 mm out, 6 mm past the cone at the bench, and the arm crosses at
z = 255-265, well above the lens at z = 210.

The arm meets the plate between the two rows of bolts, not across them, so a driver
reaches every bolt head. The foot is wider than the upright (90 against 40 mm) and
reaches outward, away from the head, so its own weight works against the head's
tipping moment. Built in the bench frame (z = 0 on the bench top, the beam axis on
x = y = 0), so it is placed at the origin.
"""
from build123d import Box, Cylinder, Pos, Rot
from cad_agent.parts import CLEARANCE_HOLE

MATERIAL = "aluminium"
PROCESS = "cnc"
MIN_FEATURE_MM = 5.0     # the narrowest metal: 5.75 mm, a bolt hole to the plate's top or bottom edge

PARAMS = {
    "column_x": 112.0,       # inner face of the upright, from the beam axis
    "column_t": 8.0,
    "column_w": 40.0,
    "foot_len": 60.0,        # outward from the upright's inner face
    "foot_w": 90.0,
    "foot_t": 8.0,
    "arm_z": 255.0,          # underside of the arm
    "arm_t": 10.0,
    "plate_x": 50.0,         # the head's +x face
    "plate_t": 8.0,
    "plate_w": 60.0,         # the head face is 70 mm across
    "plate_z0": 232.0,
    "plate_z1": 288.0,
    "bolt": "M4",
    "bolt_pitch": 40.0,      # the head's square pattern
    "bolt_z": 260.0,         # its centre: the middle of the head's side face
}


def build(column_x, column_t, column_w, foot_len, foot_w, foot_t, arm_z, arm_t,
          plate_x, plate_t, plate_w, plate_z0, plate_z1, bolt, bolt_pitch, bolt_z):
    def block(x0, x1, width, z0, z1):
        return Pos((x0 + x1) / 2.0, 0, (z0 + z1) / 2.0) * Box(x1 - x0, width, z1 - z0)

    top = arm_z + arm_t
    mount = block(column_x, column_x + foot_len, foot_w, 0.0, foot_t)             # foot
    mount += block(column_x, column_x + column_t, column_w, 0.0, top)              # upright
    mount += block(plate_x + plate_t, column_x + column_t, column_w, arm_z, top)   # arm
    mount += block(plate_x, plate_x + plate_t, plate_w, plate_z0, plate_z1)        # head plate

    d = CLEARANCE_HOLE[bolt]
    for sy in (-1, 1):
        for sz in (-1, 1):
            mount -= (Pos(plate_x + plate_t / 2.0, sy * bolt_pitch / 2.0,
                          bolt_z + sz * bolt_pitch / 2.0)
                      * Rot(0, 90, 0) * Cylinder(d / 2.0, plate_t + 2.0))
    return mount

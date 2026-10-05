"""Idler bracket: a fork that bolts to a 2040 end and holds an M5 shaft at both ends.

Printed in PETG. The back plate sits on the extrusion's end face and is held by
two M5 screws into the profile's own end bores, 20 mm apart. Two arms run out
from it, one above and one below the idler, and the shaft goes through a hole in
each. The arms are 0.75 mm clear of the idler's flanges on both sides (the idler
is 8.5 wide), so it spins freely; the shaft holes are the 5.5 mm M5 clearance.

The part is modelled in place: its origin is the centre of the extrusion's end
face, x runs out along the extrusion's axis, z is the shaft direction. The back
plate is as wide as the profile (40) and the stack is 16 tall, inside the 20 mm
face, so the shaft's 20 mm sticks out 2 mm past each arm.

The only round holes are the two mounting holes and the shaft hole: the checker
reads every other one that points at the extrusion or the idler as a bolt hole.
"""
from build123d import Box, Cylinder, Pos, Rot
from cad_agent.parts import CLEARANCE_HOLE

MATERIAL = "petg"
PROCESS = "fdm"
MIN_FEATURE_MM = 3.0     # narrowest remaining PETG: shaft hole to the arm edge is 5.75

PARAMS = {
    "back_t": 4.0,           # x, the plate against the end face
    "width": 40.0,           # y, the profile's long side
    "arm_t": 3.0,            # z, each arm
    "arm_w": 17.0,           # y, each arm, with a full round end
    "idler_w": 8.5,          # the idler between flanges
    "gap": 0.75,             # arm face to idler flange, each side; the brief wants 0.5 at least
    "shaft_x": 22.0,         # from the end face to the shaft axis
    "mount_bolt": "M5",
    "mount_pitch": 20.0,     # the profile's two end bores, 10 either side of the centre
    "shaft_bolt": "M5",
}


def build(back_t, width, arm_t, arm_w, idler_w, gap, shaft_x, mount_bolt, mount_pitch, shaft_bolt):
    inner = idler_w / 2.0 + gap              # shaft axis to the face of an arm
    half = inner + arm_t                     # and to the outside of it
    body = Pos(back_t / 2.0, 0, 0) * Box(back_t, width, 2.0 * half)
    for sz in (-1, 1):
        zc = sz * (inner + arm_t / 2.0)
        body += Pos(shaft_x / 2.0, 0, zc) * Box(shaft_x, arm_w, arm_t)
        body += Pos(shaft_x, 0, zc) * Cylinder(arm_w / 2.0, arm_t)

    dm = CLEARANCE_HOLE[mount_bolt]
    for sy in (-1, 1):
        body -= Pos(back_t / 2.0, sy * mount_pitch / 2.0, 0) * Rot(0, 90, 0) * Cylinder(dm / 2.0, back_t + 2.0)

    ds = CLEARANCE_HOLE[shaft_bolt]
    body -= Pos(shaft_x, 0, 0) * Cylinder(ds / 2.0, 2.0 * half + 2.0)
    return body

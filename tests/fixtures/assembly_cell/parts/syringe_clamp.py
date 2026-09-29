"""Clamp holding the paste syringe barrel on the shared carriage.

Printed, not machined, and deliberately so. The barrel is a consumable that
changes diameter between suppliers, so this is the part expected to be
reprinted rather than the plate it bolts to. Everything dimensional that the
machine depends on lives in x_carriage; this only has to grip.

The bore is a C rather than a full circle. A split clamp needs a pinch bolt
and a slot wide enough to close, which is more part than a syringe needs: the
C opens by the print's own flex, the barrel pushes in, and the lip retains it.
The gap is therefore a real functional dimension, not a modelling shortcut,
and it is the first thing to change if a barrel will not seat.
"""
from build123d import Box, Cylinder, Pos, Rot
from cad_agent.parts import HEATSET_BORE

MATERIAL = "petg"          # near the plate, which sits under a hot-air head
PROCESS = "fdm"
MIN_FEATURE_MM = 2.4       # the C wall behind the barrel

# 4 mounting bores, 1 barrel bore, 1 opening slot.
EXPECT_FEATURES = 6

PARAMS = {
    "barrel_dia": 23.5,     # 10 cc syringe barrel, nominal
    "wall": 4.0,
    "height": 26.0,         # z, the grip length
    "back": 8.0,            # solid thickness behind the barrel, y
    "mount_bolt": "M3",
    "mount_pitch_x": 24.0,  # matches x_carriage clamp_pitch_x
    "mount_pitch_z": 30.0,  # matches x_carriage clamp_pitch_z
    "opening": 14.0,        # width of the C mouth, front face
}


def build(barrel_dia, wall, height, back, mount_bolt, mount_pitch_x,
          mount_pitch_z, opening):
    outer = barrel_dia + 2 * wall
    width = max(outer, mount_pitch_x + 2 * wall)
    depth = back + outer
    body = Box(width, depth, max(height, mount_pitch_z + 2 * wall))

    # Barrel bore, axis vertical, sitting forward of the mounting face.
    bore_y = depth / 2.0 - outer / 2.0
    body -= Pos(0, bore_y, 0) * Cylinder(barrel_dia / 2.0, height + 20)

    # The mouth: a slot out of the front face so the barrel can be pushed in.
    body -= Pos(0, depth / 2.0, 0) * Box(opening, outer, height + 20)

    # Mounting bores, heat-set inserts, from the back face into the solid web.
    d = HEATSET_BORE[mount_bolt]
    for sx in (-1, 1):
        for sz in (-1, 1):
            body -= (Pos(sx * mount_pitch_x / 2.0, -depth / 2.0 + back / 2.0,
                         sz * mount_pitch_z / 2.0)
                     * Rot(90, 0, 0) * Cylinder(d / 2.0, back + 2))
    return body

"""Bracket: a plate on the extrusion's +x face and a block that carries the switch out to the flag.

The plate lies flat on the extrusion and takes two M5 screws into slot nuts
(the slots are not in the model, so these holes are not graded). The block
stands out from it to x = 24 mm, where the switch is screwed to its outer face
with two M2 screws into 1.6 mm holes, the M2 tapping drill. The holes are 9.5 mm
apart, the switch's pitch, at the height the gate needs: the switch's lever top
is 8.8 mm above its hole axes, and the flag's underside is at z = 40, so the
axes are at z = 31.0 and the lever stops 0.2 mm short of the flag.

Both top faces stop at z = 38.5, 1.5 mm under the flag. The plate reaches 10 mm
lower than the block, so the two M5 screws sit below it where a driver can get at them.
"""
from build123d import Box, Cylinder, Pos, Rot

MATERIAL = "petg"
PROCESS = "fdm"
MIN_FEATURE_MM = 1.2

PARAMS = {
    "face_x": 10.0,        # the extrusion's +x face
    "plate_t": 4.0,
    "plate_w": 30.0,       # across y, centred on the extrusion
    "plate_z0": 14.0,
    "top_z": 38.5,         # top of the plate and of the block
    "block_x": 24.0,       # the outer face the switch is screwed to
    "block_w": 21.0,
    "block_z0": 24.0,
    "axis_z": 31.0,        # height of the switch's hole axes
    "pitch": 9.5,          # the switch's hole spacing, from the datasheet
    "tap_d": 1.6,          # M2 tapping drill, `cad tables`
    "tap_depth": 6.0,
    "m5_d": 5.5,           # M5 clearance, `cad tables`
    "m5_y": 10.0,          # the two slots of a 2040's wide face sit 10 mm either side of centre
    "m5_z": 18.0,
}


def along_x(x, y, z, d, depth):
    """A cylinder of diameter d standing along x, centred on (x, y, z)."""
    return Pos(x, y, z) * Rot(0, 90, 0) * Cylinder(d / 2.0, depth)


def build(face_x, plate_t, plate_w, plate_z0, top_z, block_x, block_w, block_z0,
          axis_z, pitch, tap_d, tap_depth, m5_d, m5_y, m5_z):
    plate = Pos(face_x + plate_t / 2.0, 0, (plate_z0 + top_z) / 2.0) * Box(
        plate_t, plate_w, top_z - plate_z0)
    block_x0 = face_x + plate_t
    block = Pos((block_x0 + block_x) / 2.0, 0, (block_z0 + top_z) / 2.0) * Box(
        block_x - block_x0, block_w, top_z - block_z0)
    part = plate + block
    for sy in (-1, 1):
        part -= along_x(block_x - tap_depth / 2.0 + 0.5, sy * pitch / 2.0, axis_z,
                        tap_d, tap_depth + 1.0)
        part -= along_x(face_x + plate_t / 2.0, sy * m5_y, m5_z, m5_d, plate_t + 2.0)
    return part

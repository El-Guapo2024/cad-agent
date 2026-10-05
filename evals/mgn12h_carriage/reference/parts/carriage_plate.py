"""Carriage plate: bolts to an MGN12H block and carries a 30 x 30 tool flange.

Printed in PETG, 8 mm thick so the heat-set insert bores (4.0 mm, 6.5 deep)
keep 1.5 mm of floor. Two bolt patterns, both centred on the block:

  20 x 20   four plain 3.4 mm clearance holes down into the block's tapped M3
            holes. HIWIN's H block has a 20 x 20 pattern, the C block 20 x 15,
            so the pattern is the first thing to check when the block changes.
            No counterbores: the cap-screw heads sit on top, inside the relief
            under the tool flange.
  30 x 30   four 4.0 mm insert bores from the top face, for the tool flange.

The plate is 50 x 50, which is what the 30 x 30 square needs (3 mm of PETG
beyond each bore) and what keeps it short of both the 30 g budget and the
66 mm the 40 mm stroke leaves between the end stops.
"""
from build123d import Box, Cylinder, Pos, fillet, Axis
from cad_agent.parts import CLEARANCE_HOLE, HEATSET_BORE

MATERIAL = "petg"
PROCESS = "fdm"
MIN_FEATURE_MM = 3.0     # narrowest remaining PETG: insert bore to plate edge

# Cutouts at mid-thickness: 4 bolt holes through, and the 4 insert bores,
# which are deep enough to cross the mid-plane.
EXPECT_FEATURES = 8

PARAMS = {
    "length": 50.0,          # x, along the rail
    "width": 50.0,           # y, across it
    "thickness": 8.0,
    "bolt": "M3",
    "bolt_pitch_x": 20.0,    # MGN12H block: C = 20 along the rail
    "bolt_pitch_y": 20.0,    # and B = 20 across it
    "tool_bolt": "M3",
    "tool_pitch": 30.0,
    "insert_depth": 6.5,     # M3 x 5.7 insert plus a 0.8 mm floor
    "corner_r": 3.0,
}


def build(length, width, thickness, bolt, bolt_pitch_x, bolt_pitch_y,
          tool_bolt, tool_pitch, insert_depth, corner_r):
    plate = Box(length, width, thickness)
    plate = fillet(plate.edges().filter_by(Axis.Z), corner_r)

    d = CLEARANCE_HOLE[bolt]
    for sx in (-1, 1):
        for sy in (-1, 1):
            plate -= Pos(sx * bolt_pitch_x / 2.0, sy * bolt_pitch_y / 2.0, 0) \
                * Cylinder(d / 2.0, thickness + 2.0)

    # Insert bores from the top face (+z), blind.
    di = HEATSET_BORE[tool_bolt]
    top = thickness / 2.0
    for sx in (-1, 1):
        for sy in (-1, 1):
            plate -= Pos(sx * tool_pitch / 2.0, sy * tool_pitch / 2.0,
                         top - insert_depth / 2.0 + 0.5) \
                * Cylinder(di / 2.0, insert_depth + 1.0)
    return plate

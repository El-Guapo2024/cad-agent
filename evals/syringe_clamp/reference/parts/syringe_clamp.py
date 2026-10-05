"""Clamp that holds a 10 mL syringe barrel off the carriage plate.

A ring around the barrel on a web that bolts to the plate. The barrel's axis is 10 mm
off the middle of the bolt pattern, so the web is lopsided: it runs from past the left
bolts to past the far side of the ring, and the right bolts sit behind the ring while
the left ones sit beside it. Bolts come from behind through the plate's clearance holes
into M3 heat-set inserts in the web, which is why the web is 8 mm deep: the inserts
take 5.5 and leave 2.5 mm before the ring's bore.

The bore is 0.4 mm over the barrel, 0.2 mm a side, which is what a printed bore needs
to slide on and still hold the barrel square. The syringe goes in from below, tip
first; the flange stops it. Built with its back face on y = 0 and the bolt pattern
centred on x = 0, z = 0, so it is placed at the origin.
"""
from build123d import Box, Cylinder, Pos, Rot
from cad_agent.parts import HEATSET_BORE

MATERIAL = "petg"
PROCESS = "fdm"
MIN_FEATURE_MM = 2.0     # the ring wall is 3, the web behind an insert 2.5

PARAMS = {
    "barrel_dia": 16.0,      # 10 mL luer-lock syringe
    "fit": 0.4,              # bore minus barrel
    "wall": 3.0,             # ring wall
    "height": 38.0,          # z: the bolt pitch plus a 4 mm rim above and below
    "barrel_y": 16.2,        # barrel axis, in front of the plate's face
    "bore_x": 10.0,          # barrel axis from the middle of the bolt pattern
    "bolt": "M3",
    "pitch_x": 24.0,         # the plate's bolt pattern
    "pitch_z": 30.0,
    "insert_depth": 5.5,
    "rim": 4.0,              # metal beyond an insert bore's axis
}


def build(barrel_dia, fit, wall, height, barrel_y, bore_x, bolt, pitch_x, pitch_z,
          insert_depth, rim):
    bore_r = (barrel_dia + fit) / 2.0
    back = barrel_y - bore_r                      # web depth: the plate to the nearest point of the bore
    bore_y = -barrel_y
    x0 = -(pitch_x / 2.0 + rim)                   # web: past the left bolts ...
    x1 = bore_x + bore_r + wall                   # ... to the far side of the ring

    web = Pos((x0 + x1) / 2.0, -back / 2.0, 0) * Box(x1 - x0, back, height)
    ring = Pos(bore_x, bore_y, 0) * Cylinder(bore_r + wall, height)
    body = web + ring
    body -= Pos(bore_x, bore_y, 0) * Cylinder(bore_r, height + 2.0)

    d = HEATSET_BORE[bolt]
    for sx in (-1, 1):
        for sz in (-1, 1):
            body -= (Pos(sx * pitch_x / 2.0, -insert_depth / 2.0 + 0.5, sz * pitch_z / 2.0)
                     * Rot(90, 0, 0) * Cylinder(d / 2.0, insert_depth + 1.0))
    return body

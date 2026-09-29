"""Gantry end plate: ties one end of the beam to a Y rail carriage.

Two of these carry the whole moving gantry, so they set the machine's squareness
and they are the parts most likely to be wrong. An L would be the obvious
shape; this is a flat plate with the beam bolted to its face instead, because a
bent L relies on the bend angle being 90 degrees and a laser-cut flat plate
relies on nothing but the cut.

Squareness then comes from the beam bolt pattern being cut square to the rail
bolt pattern in the same file, which is a thing the machine can hold and a
bender cannot.

The tall slot is not decoration: it is the belt path. The Y belt runs up the
inside face and terminates on the plate, so the pull is in line with the rail
rather than offset above it, which is what stops the gantry from racking on
acceleration.
"""
from build123d import Box, Cylinder, Pos, Rot
from cad_agent.parts import CLEARANCE_HOLE

MATERIAL = "aluminium"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 4.0

# 4 rail bolts, 4 beam bolts, 1 belt slot, 2 belt anchor holes.
EXPECT_FEATURES = 11

PARAMS = {
    "width": 70.0,           # y, along the rail
    "height": 120.0,         # z, rail up to beam
    "thickness": 6.0,        # x
    "rail_bolt": "M3",
    "rail_pitch_y": 20.0,
    "rail_pitch_z": 20.0,
    "rail_z": -42.0,         # rail block centre, low on the plate
    "beam_bolt": "M5",       # into the extrusion end tap
    "beam_pitch_y": 20.0,    # 2040 end taps, 20 mm apart across the 40 mm face
    "beam_z": 40.0,          # beam centre height above plate centre
    "belt_slot_w": 8.0,
    "belt_slot_h": 26.0,
    "belt_slot_z": -5.0,
    "anchor_bolt": "M3",
    "anchor_pitch": 34.0,
}


def build(width, height, thickness, rail_bolt, rail_pitch_y, rail_pitch_z,
          rail_z, beam_bolt, beam_pitch_y, beam_z, belt_slot_w, belt_slot_h,
          belt_slot_z, anchor_bolt, anchor_pitch):
    plate = Box(thickness, width, height)

    def thru(y, z, dia):
        return Pos(0, y, z) * Rot(0, 90, 0) * Cylinder(dia / 2.0, thickness + 2)

    d = CLEARANCE_HOLE[rail_bolt]
    for sy in (-1, 1):
        for sz in (-1, 1):
            plate -= thru(sy * rail_pitch_y / 2.0, rail_z + sz * rail_pitch_z / 2.0, d)

    # Beam end taps: two rows of two, into the 2040 end face.
    db = CLEARANCE_HOLE[beam_bolt]
    for sy in (-1, 1):
        for sz in (-1, 1):
            plate -= thru(sy * beam_pitch_y / 2.0, beam_z + sz * 10.0, db)

    # Belt slot and its two anchor bolts, in line with the rail.
    plate -= Pos(0, 0, belt_slot_z) * Box(thickness + 2, belt_slot_w, belt_slot_h)
    da = CLEARANCE_HOLE[anchor_bolt]
    for sy in (-1, 1):
        plate -= thru(sy * anchor_pitch / 2.0, belt_slot_z, da)
    return plate

"""X carriage: the plate that rides the gantry beam and carries both heads.

This part is the whole reason the assembly cell has one gantry instead of
two. Paste dispensing and part placement never happen at the same instant, so
they can share a carriage; what they cannot share is a nozzle, so the plate
carries two tool stations side by side and the machine picks one by moving in
x. The cost of that decision is paid here, in plate width.

Layout across the plate, left to right:

  two MGN12 block patterns          the rail interface, top of the plate
  place station bore                theta motor spigot, on the plate centre
  syringe station bores             the paste clamp bolts on, offset in +x

The plate is the datum for both stations, so the two bolt patterns are cut in
one setup and their spacing is a machined dimension rather than an assembly
tolerance. That spacing is what the firmware calls the tool offset, and
getting it from geometry instead of from a calibration routine is worth the
wider plate.

Cut from 6 mm aluminium on the same laser cell this machine belongs to, which
is the point: the fab line makes its own brackets.
"""
from build123d import Box, Cylinder, Pos, Rot
from cad_agent.parts import CLEARANCE_HOLE

MATERIAL = "aluminium"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 3.0     # narrowest remaining metal: bore to plate edge

# Cutouts through the plate at mid-depth: 8 rail bolts, 4 theta bolts,
# 1 nozzle clearance bore, 4 syringe-clamp bolts, 1 cable pass-through.
EXPECT_FEATURES = 18

PARAMS = {
    "width": 150.0,          # x, set by the two tool stations side by side
    "height": 86.0,          # z, set by keeping three bolt patterns apart
    "thickness": 6.0,        # y
    "rail_bolt": "M3",
    "rail_pitch_x": 20.0,    # MGN12H block bolt pattern, along the rail
    "rail_pitch_z": 20.0,    # across the rail
    "block_spacing": 60.0,   # centre to centre of the two carriage blocks
    # Two faults lived in this one number, and the feature count found both by
    # counting 14, then 17, cutouts where 18 were declared. At 24 the upper
    # bolt row broke out through the top edge with 1 mm of metal left. At 16
    # it cleared the edge but landed 2.2 mm from the theta motor pattern, and
    # the two holes merged. The plate grew to 86 mm so all three patterns fit.
    "rail_bolt_z": 26.0,
    "theta_bolt": "M3",
    "theta_pcd": 28.0,       # NEMA8 face bolt circle, square pattern
    "nozzle_bore": 16.0,     # clearance for the hollow shaft and rotary union
    "place_x": -35.0,        # place station centre, left of plate middle
    "syringe_x": 40.0,       # paste station centre. Difference is the tool offset.
    "clamp_bolt": "M3",
    "clamp_pitch_x": 24.0,
    "clamp_pitch_z": 30.0,
    "cable_slot": 14.0,      # pass-through for the head loom
    "station_z": -14.0,      # both stations sit below plate centre
}


def build(width, height, thickness, rail_bolt, rail_pitch_x, rail_pitch_z,
          block_spacing, rail_bolt_z, theta_bolt, theta_pcd, nozzle_bore,
          place_x, syringe_x, clamp_bolt, clamp_pitch_x, clamp_pitch_z,
          cable_slot, station_z):
    plate = Box(width, thickness, height)

    def thru(x, z, dia):
        return Pos(x, 0, z) * Rot(90, 0, 0) * Cylinder(dia / 2.0, thickness + 2)

    # Rail interface: two MGN12H blocks, each a four-bolt rectangle. The z row
    # is high on the plate so the load path from rail to tool is short.
    d = CLEARANCE_HOLE[rail_bolt]
    for bx in (-block_spacing / 2.0, block_spacing / 2.0):
        for sx in (-1, 1):
            for sz in (-1, 1):
                plate -= thru(bx + sx * rail_pitch_x / 2.0,
                              rail_bolt_z + sz * rail_pitch_z / 2.0, d)

    # Place station: nozzle bore with the theta motor bolted around it.
    plate -= thru(place_x, station_z, nozzle_bore)
    dt = CLEARANCE_HOLE[theta_bolt]
    for sx in (-1, 1):
        for sz in (-1, 1):
            plate -= thru(place_x + sx * theta_pcd / 2.0,
                          station_z + sz * theta_pcd / 2.0, dt)

    # Paste station: the syringe clamp bolts on here.
    dc = CLEARANCE_HOLE[clamp_bolt]
    for sx in (-1, 1):
        for sz in (-1, 1):
            plate -= thru(syringe_x + sx * clamp_pitch_x / 2.0,
                          station_z + sz * clamp_pitch_z / 2.0, dc)

    # Cable pass-through between the stations, well clear of both patterns.
    plate -= thru((place_x + syringe_x) / 2.0, station_z, cable_slot)
    return plate

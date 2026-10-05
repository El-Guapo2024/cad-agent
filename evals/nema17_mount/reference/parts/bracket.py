"""Motor plate: a NEMA 17 hangs under this plate, and the plate lies on top of a 2040 rail.

One flat plate is the whole bracket. Its underside is the datum for both jobs: the
rail's top face and the motor's mounting face are in the same plane, so the plate
touches both with no spacer, and the motor's 2 mm pilot drops into the bore from
below. The motor sits beside the rail, not under it, so the plate runs past the
rail's side to carry it; the bore is on the plate's centreline, 10 mm toward that
end from the plate's middle.

Machined from 4 mm 6061 plate. The bore is 0.5 mm over the pilot so the motor seats
without a press fit.
"""
from build123d import Box, Cylinder, Pos
from cad_agent.parts import CLEARANCE_HOLE

MATERIAL = "aluminium"
PROCESS = "cnc"
MIN_FEATURE_MM = 3.0     # the narrowest metal left: 5.25 mm, a rail screw hole to the plate's side edge

# 1 pilot bore, 4 motor screws, 2 rail screws.
EXPECT_FEATURES = 7

PARAMS = {
    "length": 70.0,          # x: rail outer edge to the far side of the motor holes
    "width": 46.0,           # y: the motor face is 42.3 mm across
    "thickness": 4.0,        # z
    "motor_dx": 10.0,        # bore centre from the plate's middle, along x
    "pilot_bore": 22.5,      # pilot is 22.0 mm
    "motor_pitch": 31.0,     # NEMA 17 square pattern
    "motor_bolt": "M3",
    "rail_dx": -25.0,        # rail screws sit on the rail's centreline: 25 mm from the middle
    "rail_pitch": 30.0,      # along the rail
    "rail_bolt": "M5",
}


def build(length, width, thickness, motor_dx, pilot_bore, motor_pitch, motor_bolt,
          rail_dx, rail_pitch, rail_bolt):
    plate = Box(length, width, thickness)

    def thru(x, y, dia):
        return Pos(x, y, 0) * Cylinder(dia / 2.0, thickness + 2.0)

    plate -= thru(motor_dx, 0.0, pilot_bore)
    d = CLEARANCE_HOLE[motor_bolt]
    for sx in (-1, 1):
        for sy in (-1, 1):
            plate -= thru(motor_dx + sx * motor_pitch / 2.0, sy * motor_pitch / 2.0, d)
    d = CLEARANCE_HOLE[rail_bolt]
    for sy in (-1, 1):
        plate -= thru(rail_dx, sy * rail_pitch / 2.0, d)
    return plate

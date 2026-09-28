"""The whole car, positioned.

Layout, nose to tail: ball caster, battery bay, drive axle, Arduino. The
battery sits between the caster and the axle so its mass loads the driven
wheels rather than the caster.

Coordinates: +x toward the rear, +y to the left, +z up. The chassis plate is
centred on the origin, so z = 0 is the middle of the plate and the ground
plane falls out of the wheel radius and the axle height.

Motors and wheels are built with their axis along x, so both are turned a
quarter turn to put the drive axle across the car.

Clearances below are requirements, not observations. The wheel-to-chassis gap
is the one that sets the plate width: too little and a wheel rubs the edge on
a bump, and nothing else in the layout can fix it once the plate is cut.
"""
from build123d import Plane, Pos, Rot, mirror

from cad_agent.state import build_part, bought_solid

SLUG = "arduino_car"

AXLE_X = -6.0        # drive axle, from plate centre
AXLE_Z = -17.0       # below the plate; low enough that the motor can clears
                     # the bracket base, which the gate caught at -14
MOTOR_Y = 25.5       # motor centreline, each side
WHEEL_Y = 56.0       # wheel centreline, outboard of the plate edge at 41
ARDUINO_X = 44.0
CASTER_X = -70.0
PLATE_T = 3.0

CLEARANCE = {
    "chassis|wheel_left": 2.0,      # plate edge to wheel face, for bumps
    "chassis|wheel_right": 2.0,
    "arduino|wheel_left": 5.0,      # keep the board well clear of rotating parts
    "arduino|wheel_right": 5.0,
    "motor_left|motor_right": 5.0,  # room for wiring between the gearboxes
    "arduino|motor_left": 3.0,
    "arduino|motor_right": 3.0,
}

ALLOW_CONTACT = {
    "chassis|bracket_left", "chassis|bracket_right",
    "chassis|caster",
    "caster|caster_ball",
    "motor_left|wheel_left", "motor_right|wheel_right",
    "motor_left|bracket_left", "motor_right|bracket_right",
    "chassis|arduino",
}


def parts():
    chassis, _ = build_part(SLUG, "chassis")
    wheel, _ = build_part(SLUG, "wheel")
    bracket, _ = build_part(SLUG, "motor_bracket")
    caster, _ = build_part(SLUG, "caster")
    motor = bought_solid(SLUG, "tt_motor")
    uno = bought_solid(SLUG, "arduino_uno")
    ball = bought_solid(SLUG, "caster_ball")

    out = {"chassis": chassis}

    # Build the left side, then mirror it for the right. Rotating the right
    # side instead got this wrong twice: a negative quarter turn swung the
    # gearbox forward into the bracket, and an equal turn left the single
    # output shaft pointing inboard across the centreline. A mirror cannot
    # make either mistake, and it guarantees the two sides match.
    out["motor_left"] = Pos(AXLE_X, MOTOR_Y, AXLE_Z) * Rot(0, 0, 90) * motor
    out["wheel_left"] = Pos(AXLE_X, WHEEL_Y, AXLE_Z) * Rot(0, 0, 90) * wheel
    out["bracket_left"] = (Pos(AXLE_X + 4.0, MOTOR_Y, -PLATE_T / 2.0)
                           * Rot(180, 0, 0) * bracket)
    for key in ("motor", "wheel", "bracket"):
        out[f"{key}_right"] = mirror(out[f"{key}_left"], Plane.XZ)

    # Flange sits flat under the plate, so the whole caster hangs below it.
    out["caster"] = Pos(CASTER_X, 0, -PLATE_T / 2.0 - CASTER_FLANGE) * caster
    out["caster_ball"] = Pos(
        CASTER_X, 0, -PLATE_T / 2.0 - CASTER_FLANGE - CASTER_DROP + 8.3 - 2.0) * ball
    out["arduino"] = Pos(ARDUINO_X, 0, PLATE_T / 2.0 + UNO_STANDOFF + 0.8) * uno
    return out


UNO_STANDOFF = 6.0     # nylon spacers between plate and board
CASTER_FLANGE = 4.0    # caster flange thickness, it bolts under the plate
CASTER_DROP = 42.3     # matches parts/caster.py; sets the ball on the same
                       # ground plane as the wheels, at z = AXLE_Z - 32.5

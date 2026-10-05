"""NEMA 17 on a 2040 rail: the motor hangs beside the rail under a plate that lies on both.

Coordinates. z = 0 is the rail's top face, the plate's underside and the motor's
mounting face, all one plane. x runs across the rail, y along it, origin on the rail's
centreline. The motor is given: its STEP origin is the middle of its mounting face
with the shaft toward +z, so it goes in by translation alone.
"""
from build123d import Pos
from cad_agent.parts import extrusion_blank
from cad_agent.state import bought_solid, build_part

SLUG = "nema17_mount"

RAIL_LEN = 60.0
MOTOR_X = 35.0          # the body (42.3 mm) clears the rail's side face at x = 10 by 3.85 mm
PLATE_T = 4.0
PLATE_MID_X = 25.0      # the plate runs from the rail's outer edge (x = -10) to x = 60


def parts():
    bracket, _ = build_part(SLUG, "bracket")
    return {
        "extrusion": Pos(0, 0, -20.0) * extrusion_blank("2040", RAIL_LEN, axis="y"),
        "nema17_motor": Pos(MOTOR_X, 0, 0) * bought_solid(SLUG, "nema17_motor"),
        "bracket": Pos(PLATE_MID_X, 0, PLATE_T / 2.0) * bracket,
    }

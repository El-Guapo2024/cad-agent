"""A stepper motor of a NEMA frame, drawn as an envelope.

The origin is the middle of the mounting face, the shaft points +z and the body is behind it (z < 0), so a bracket
that holds the motor is placed against z = 0 whatever the motor's length. The pieces are the ones every frame drawing
dimensions: the square body with its corners cut or rounded, the pilot (the centring boss) on the face, the round
shaft out of it, and the four tapped holes on the bolt square. The shaft's flat, the connector, the wires and the
body's own steps are not drawn: they are not on the frame, a source gives some of them for one motor and not for the
frame, and an envelope that adds a detail for one maker's motor is wrong for the next.

`shaft_length` is the distance from the mounting face to the shaft's end, pilot included, which is how the makers'
drawings dimension it. A corner is cut with `corner_cut` (a chamfer that long on each side) or rounded with
`corner_radius`; neither is on a frame drawing that does not dimension it, and then the body keeps its square corners,
which is the larger envelope and so the safe one for a clearance.
"""
from __future__ import annotations

from build123d import Axis, Box, Cylinder, Pos


def motor(face, length, pilot_dia, pilot_height, shaft_dia, shaft_length, hole_pitch, hole_dia, hole_depth,
          corner_cut=None, corner_radius=None):
    """A `face` x `face` x `length` motor with its pilot, shaft and four holes on a `hole_pitch` square."""
    body = Pos(0, 0, -length / 2.0) * Box(face, face, length)
    if corner_cut:
        body = body.chamfer(corner_cut, None, body.edges().filter_by(Axis.Z))
    elif corner_radius:
        body = body.fillet(corner_radius, body.edges().filter_by(Axis.Z))
    motor = body + Pos(0, 0, pilot_height / 2.0) * Cylinder(pilot_dia / 2.0, pilot_height)
    motor += Pos(0, 0, shaft_length / 2.0) * Cylinder(shaft_dia / 2.0, shaft_length)
    for sx in (-1, 1):
        for sy in (-1, 1):
            motor -= Pos(sx * (hole_pitch / 2.0), sy * (hole_pitch / 2.0), -hole_depth / 2.0 + 0.5) \
                * Cylinder(hole_dia / 2.0, hole_depth + 1.0)
    return motor

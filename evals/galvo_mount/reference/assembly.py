"""Galvo head over the bench, held by one mount that stands outside the beam cone.

Coordinates. z = 0 is the bench top, which is also the work plane the laser focuses on;
x and y run across it with the origin under the beam axis. The head is given and goes in
by translation alone: its STEP origin is where the beam leaves the lens, so putting that
at z = 210 (the lens focal length) puts the lens barrel's lower face on the top of the
beam cone. The mount is built in this same frame and is not moved.
"""
from build123d import Box, Pos
from cad_agent.state import bought_solid, build_part

SLUG = "galvo_mount"


def parts():
    mount, _ = build_part(SLUG, "galvo_mount")
    return {
        "bench": Pos(0, 0, -6.0) * Box(400.0, 300.0, 12.0),
        "galvo_head": Pos(0, 0, 210.0) * bought_solid(SLUG, "galvo_head"),
        "galvo_mount": mount,
    }

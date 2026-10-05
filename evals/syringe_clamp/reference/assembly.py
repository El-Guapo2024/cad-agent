"""Syringe clamp on the carriage plate.

Coordinates. The plate's front face is y = 0 and the middle of its bolt pattern is the
origin; x runs across the plate, z up, and the plate's thickness runs toward +y behind
that face. Both given parts come in with their STEP origins where the brief says, so
the plate goes in as it is and the syringe by translation alone: its axis 10 mm off
the bolt pattern's middle and 16.2 mm in front of the plate, its flange underside 35 mm
above the pattern. The clamp is built in the same frame and is not moved.
"""
from build123d import Pos
from cad_agent.state import bought_solid, build_part

SLUG = "syringe_clamp"


def parts():
    clamp, _ = build_part(SLUG, "syringe_clamp")
    return {
        "carriage_plate": bought_solid(SLUG, "carriage_plate"),
        "syringe": Pos(10.0, -16.2, 35.0) * bought_solid(SLUG, "syringe"),
        "syringe_clamp": clamp,
    }

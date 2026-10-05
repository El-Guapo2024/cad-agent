"""A Z-axis lower endstop: the carriage's flag comes down onto the switch's lever.

Coordinates: the extrusion stands on z = 0 and runs up to z = 200, centred on x = y = 0.
The carriage (not modelled) rides on the +x face, and at the bottom of its travel
its flag, the given block, sits at x 24.5..30.5, y -2..10, z 40..54. The bracket
holds the switch just below it.

The switch is turned a quarter turn about z, so its 19.8 mm length runs along y,
its screws run along x into the bracket's outer face at x = 24, and its lever
points up. Its hole axes are at z = 31.0, which puts the lever's top 0.2 mm
under the flag.
"""
from build123d import Pos, Rot

from cad_agent.state import build_part, bought_solid

SLUG = "endstop_bracket"

SWITCH_AT = (27.2, 0.0, 31.0)     # midpoint of the switch's holes: 24 + half its 6.4 thickness

CLEARANCE = {
    "bracket|flag": 1.0,         # the flag only ever touches the lever
}

ALLOW_CONTACT = {
    "bracket|extrusion",         # the plate lies on the extrusion
    "bracket|switch",            # the switch is screwed to the block
}


def parts():
    bracket, _ = build_part(SLUG, "bracket")
    return {
        "extrusion": Pos(0, 0, 100) * bought_solid(SLUG, "extrusion_2040"),
        "flag": Pos(27.5, 4.0, 47.0) * bought_solid(SLUG, "carriage_flag"),
        "switch": Pos(*SWITCH_AT) * Rot(0, 0, 90) * bought_solid(SLUG, "omron_ss5gl"),
        "bracket": bracket,
    }

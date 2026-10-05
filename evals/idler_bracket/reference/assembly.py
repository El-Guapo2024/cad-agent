"""Idler bracket: the fork on a 2040 end, with the idler and its shaft between the arms.

Frame: x along the extrusion, with its end face on x = 0 and the stub running to
x = -60; y across the 40 mm side; z up, which is the shaft direction. The idler
and shaft axis is at x = 22, y = 0, z = 0. The given STEP files are centred on
their own boxes, so each is only translated here, to the centre the brief states.
The bracket is modelled in place (origin at the middle of the end face).

The back plate rests on the end face and the shaft sits in the idler's bore, so
those two pairs are allowed to touch. The idler must stay 0.5 mm off the bracket
so it spins.
"""
from cad_agent.state import build_part, bought_solid
from build123d import Pos

SLUG = "idler_bracket"
IDLER_X = 22.0

CLEARANCE = {
    "idler|bracket": 0.5,
}

ALLOW_CONTACT = {
    "bracket|extrusion",
    "idler|shaft",
}


def parts():
    bracket, _ = build_part(SLUG, "bracket")
    return {
        "extrusion": Pos(-30.0, 0, 0) * bought_solid(SLUG, "extrusion_2040"),
        "idler": Pos(IDLER_X, 0, 0) * bought_solid(SLUG, "gt2_idler"),
        "shaft": Pos(IDLER_X, 0, 0) * bought_solid(SLUG, "m5_shaft"),
        "bracket": bracket,
    }

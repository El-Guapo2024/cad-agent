"""The reflow hot plate on four standoffs, 20 mm above its base.

Coordinates: the base's top face is z = 0 and the plate's underside is z = GAP, both
centred on x = y = 0. The given STEPs are already built with those datums, so the
base is placed as it is and the plate is lifted by the gap. The standoffs sit at the
plate's four tapped holes, standing from the base top to the plate underside.
"""
from build123d import Pos
from cad_agent.state import build_part, bought_solid

SLUG = "hotplate_standoffs"

GAP = 20.0        # still air between a 250 C plate and the base
HOLE = 43.0       # hole centres at +-43 mm, from the given plate

CLEARANCE = {"hot_plate|base_plate": GAP}

# The standoffs are screwed to both plates: they are meant to touch.
CORNERS = {"standoff_1": (-1, -1), "standoff_2": (1, -1),
           "standoff_3": (-1, 1), "standoff_4": (1, 1)}
ALLOW_CONTACT = {f"{s}|{p}" for s in CORNERS for p in ("hot_plate", "base_plate")}


def parts():
    standoff, _ = build_part(SLUG, "standoff")
    out = {
        "base_plate": bought_solid(SLUG, "base_plate"),
        "hot_plate": Pos(0, 0, GAP) * bought_solid(SLUG, "hot_plate"),
    }
    for name, (sx, sy) in CORNERS.items():
        out[name] = Pos(sx * HOLE, sy * HOLE, GAP / 2.0) * standoff
    return out

"""A carrier block located on two dowel pins and seated flat on the base.

Coordinates: the base's top face is z = 0, centred on x = y = 0; the pins stand at x = +-25
and the clamp screw at the origin. The given STEPs already carry those datums, so the base and
the screw are placed as they are, each pin is pressed 6 mm in (its bottom end at z = -6), and the
carrier's origin is its underside centre, so it is placed as it is too.
"""
from build123d import Pos
from cad_agent.state import build_part, bought_solid

SLUG = "pinned_carrier"

PIN_X = 25.0       # pin centres, from the given base
PIN_IN = 6.0       # how far the pins are pressed into the base

# The relief pocket must leave 0.5 mm round the screw head.
CLEARANCE = {"carrier|clamp_screw": 0.5}

# Meant to touch: the carrier on the base, the pins and the screw in the base.
ALLOW_CONTACT = {"carrier|base_plate", "base_plate|pin_1", "base_plate|pin_2",
                 "base_plate|clamp_screw"}


def parts():
    pin = bought_solid(SLUG, "dowel_pin")
    carrier, _ = build_part(SLUG, "carrier")
    return {
        "base_plate": bought_solid(SLUG, "base_plate"),
        "pin_1": Pos(-PIN_X, 0, -PIN_IN) * pin,
        "pin_2": Pos(PIN_X, 0, -PIN_IN) * pin,
        "clamp_screw": bought_solid(SLUG, "clamp_screw"),
        "carrier": carrier,
    }

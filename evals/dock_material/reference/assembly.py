"""A dock beside the hot plate, on the base plate.

Coordinates: the base plate's top face is z = 0, centred on x = y = 0, and the hot plate stands on it, centred
too: both given STEPs are built with those datums, so they are placed as they are. The dock stands on the base on
the +y side, its near face 3 mm off the plate's edge (the plate is 60 wide, so y = 30), with its bolts on the
base plate's holes at (+-40, 40).
"""
from build123d import Pos
from cad_agent.state import build_part, bought_solid

SLUG = "dock_material"

PLATE_HALF_Y = 30.0     # the hot plate is 60 mm across y
GAP = 3.0               # air between the plate's edge and the dock: the plate grows when it is hot
WIDTH, HEIGHT = 14.0, 12.0     # the dock's PARAMS

ALLOW_CONTACT = {"hot_plate|base_plate", "dock|base_plate"}
CLEARANCE = {"dock|hot_plate": 2.0}


def parts():
    dock, _ = build_part(SLUG, "dock")
    return {
        "base_plate": bought_solid(SLUG, "base_plate"),
        "hot_plate": bought_solid(SLUG, "hot_plate"),
        "dock": Pos(0, PLATE_HALF_Y + GAP + WIDTH / 2.0, HEIGHT / 2.0) * dock,
    }

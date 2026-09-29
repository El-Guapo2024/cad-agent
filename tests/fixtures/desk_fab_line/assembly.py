"""Box B dock: the hot plate carried on four standoffs.

Placements put the plate's underside at standoff height. The gate that matters
is the one between the plate and the frame floor: the standoffs set an air gap
that has to stay above the minimum, or conducted heat reaches the extrusion.
"""
from build123d import Pos
from cad_agent.parts import extrusion_blank
from cad_agent.state import build_part

SLUG = "desk_fab_line"

# Required clearances in mm. The plate-to-floor gap is a thermal requirement,
# not a mechanical one: 20 mm of still air between a 250 C plate and the frame.
CLEARANCE = {
    "hot_plate|floor_rail_front": 20.0,
    "hot_plate|floor_rail_back": 20.0,
}

# Pairs that are meant to touch: the screwed joints.
ALLOW_CONTACT = {
    "hot_plate|standoff_fl", "hot_plate|standoff_fr",
    "hot_plate|standoff_bl", "hot_plate|standoff_br",
    "standoff_fl|floor_rail_front", "standoff_fr|floor_rail_front",
    "standoff_bl|floor_rail_back", "standoff_br|floor_rail_back",
}

MOUNT_INSET = 7.0          # matches hot_plate PARAMS
STANDOFF_HEIGHT = 25.0     # matches plate_standoff PARAMS
PLATE_SIZE = 100.0
PLATE_T = 10.0


def parts():
    plate, _ = build_part(SLUG, "hot_plate")
    standoff, _ = build_part(SLUG, "plate_standoff")

    half = PLATE_SIZE / 2.0 - MOUNT_INSET
    # Plate underside sits at z = 0; standoffs hang below it.
    out = {"hot_plate": Pos(0, 0, PLATE_T / 2.0) * plate}
    for key, (sx, sy) in {
        "standoff_fl": (-1, -1), "standoff_fr": (1, -1),
        "standoff_bl": (-1, 1), "standoff_br": (1, 1),
    }.items():
        out[key] = Pos(sx * half, sy * half, -STANDOFF_HEIGHT / 2.0) * standoff

    # Frame floor rails the standoffs land on, 2040 laid flat.
    # 2040 laid flat: 40 mm across the box, 20 mm tall, length running in x.
    rail = extrusion_blank("2040", 300.0, axis="x")
    floor_z = -STANDOFF_HEIGHT - 10.0   # rail top face meets the standoff feet
    for key, sy in {"floor_rail_front": -1, "floor_rail_back": 1}.items():
        out[key] = Pos(0, sy * half, floor_z) * rail
    return out

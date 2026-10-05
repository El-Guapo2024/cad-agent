"""MGN12H carriage: plate on the block, tool on the plate, 80 mm of travel between two stops.

Frame: x along the rail, y across it, z up. The rail's base is z = 0 (the
surface it is screwed to); the rail runs x -75 to 75 with the block at home
in the middle. The given STEP files are centred on their own boxes, so each one
is only translated here, to the centre the brief states.

The plate sits on the block's top face (13 above the base) and the tool flange
on the plate's top face. Both stay in contact through the whole travel, so
those pairs are allowed to touch; every other gap is a requirement.

The stops stand 75 mm out from the middle. The plate is 50 long, so at +-40 mm
of travel its end is 10 mm from a stop; CLEARANCE holds 2 mm in the sweep.
"""
from build123d import Pos
from cad_agent.state import build_part, bought_solid

SLUG = "mgn12h_carriage"

RAIL_Z = 4.0           # rail centre: 8 high on the base
BLOCK_Z = 8.0          # block centre: 3 (H1) + 5 half its height
BLOCK_TOP = 13.0       # H: top face of the block
PLATE_T = 8.0          # matches carriage_plate PARAMS thickness
TOOL_T = 6.0           # the tool flange
STOP_X = 79.0          # 75 to the rail end + 4 to the middle of an 8 mm stop
STOP_Z = 10.0          # 20 tall on the base

TRAVEL = (-40.0, 40.0)     # from home; the stroke the brief asks for

AXES = {
    "x": {
        "moves": ("block", "carriage_plate", "tool"),
        "direction": (1, 0, 0),
        "travel": TRAVEL,
        "work": TRAVEL,
        "tool": "tool",
        "tool_point": (0.0, 0.0, BLOCK_TOP + PLATE_T + TOOL_T),   # top of the flange
    },
}

CLEARANCE = {
    "carriage_plate|stop_left": 2.0,
    "carriage_plate|stop_right": 2.0,
    "tool|stop_left": 2.0,
    "tool|stop_right": 2.0,
    "carriage_plate|rail": 3.0,
}

ALLOW_CONTACT = {
    "carriage_plate|block", "carriage_plate|tool",
    "rail|stop_left", "rail|stop_right",
}


def parts():
    plate, _ = build_part(SLUG, "carriage_plate")
    return {
        "rail": Pos(0, 0, RAIL_Z) * bought_solid(SLUG, "mgn12_rail"),
        "block": Pos(0, 0, BLOCK_Z) * bought_solid(SLUG, "mgn12h_block"),
        "stop_left": Pos(-STOP_X, 0, STOP_Z) * bought_solid(SLUG, "end_stop"),
        "stop_right": Pos(STOP_X, 0, STOP_Z) * bought_solid(SLUG, "end_stop"),
        "carriage_plate": Pos(0, 0, BLOCK_TOP + PLATE_T / 2.0) * plate,
        "tool": Pos(0, 0, BLOCK_TOP + PLATE_T + TOOL_T / 2.0) * bought_solid(SLUG, "tool_flange"),
    }

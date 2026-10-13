"""The gantry of mini_machine: two posts, a 2020 beam across them, a rail on the beam, a carriage on the rail and a
motor on the carriage's plate. It is a project of its own, and mini_machine links it.

Frame: x along the beam, y across it, z up; z = 0 is what the posts stand on, centred on x = y = 0.

The posts are 20 x 40 x 50 mm at x = +-120, so the beam, 260 mm long, rests on both and has 220 mm of span between
them. The MGN12 rail is on the beam's top face (z 70 to 78) and the carriage rides it with its top face at z = 83; the
tool plate lies on that and the NEMA 8 motor on the plate, along x, its shaft pointing +x past the plate's end. The one
axis, x, moves the carriage, its plate and the motor 45 mm either way.
"""
from build123d import Pos, Rot
from cad_agent.state import build_part, bought_solid

SLUG = "mini_gantry"

POST_X = 120.0          # the posts' centres; their inner faces are 220 mm apart
POST_H = 50.0
BEAM_H = 20.0           # the 2020's side
RAIL_H = 8.0            # MGNR12R
BLOCK_BODY = 10.0       # MGN12H: H 13 less H1 3
PLATE_T = 4.0
MOTOR_FACE = 20.0       # NEMA 8: a 20 mm square flange, 42 mm long
MOTOR_BODY = 42.0

BEAM_TOP = POST_H + BEAM_H                      # 70
RAIL_TOP = BEAM_TOP + RAIL_H                    # 78: the carriage's frame has the rail's top face at its origin
CARRIAGE_TOP = RAIL_TOP + BLOCK_BODY / 2.0      # 83
PLATE_TOP = CARRIAGE_TOP + PLATE_T              # 87
TRAVEL = 45.0

AXES = {
    "x": {
        "moves": ("carriage", "tool_plate", "motor"),
        "direction": (1, 0, 0),
        "travel": (-TRAVEL, TRAVEL),
        "work": (-40.0, 40.0),
        "tool": "tool_plate",
        "tool_point": (0.0, 0.0, PLATE_TOP),        # the middle of the plate's top face, where the work is done
    },
}
POSES = {"park": {"x": -TRAVEL}}

CLEARANCE = {"carriage|beam": 3.0}              # H1: the block stands 3 mm clear of the rail's base
ALLOW_CONTACT = {
    "post_left|beam", "post_right|beam", "beam|rail", "tool_plate|carriage", "motor|tool_plate",
}


def parts():
    post, _ = build_part(SLUG, "post")
    plate, _ = build_part(SLUG, "tool_plate")
    return {
        "post_left": Pos(-POST_X, 0, POST_H / 2.0) * post,
        "post_right": Pos(POST_X, 0, POST_H / 2.0) * post,
        "beam": Pos(0, 0, POST_H + BEAM_H / 2.0) * bought_solid(SLUG, "extrusion_2020"),
        "rail": Pos(0, 0, BEAM_TOP + RAIL_H / 2.0) * bought_solid(SLUG, "mgn12_rail"),
        "carriage": Pos(0, 0, RAIL_TOP) * bought_solid(SLUG, "mgn12h"),
        "tool_plate": Pos(0, 0, CARRIAGE_TOP + PLATE_T / 2.0) * plate,
        # lying on the plate, shaft along +x, its body over the plate: the face is 20 square, so the axis is 10 up
        "motor": Pos(MOTOR_BODY / 2.0, 0, PLATE_TOP + MOTOR_FACE / 2.0) * Rot(0, 90, 0) * bought_solid(SLUG, "nema8"),
    }

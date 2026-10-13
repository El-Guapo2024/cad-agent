"""mini_machine: a hot plate under a two-axis gantry, small enough to check in seconds and big enough to use every part
of step 6 (the library, heat, deflection, mass and centre of mass, a sub-assembly with axes and poses, the shop files
and a drawing). It is a regression fixture, not a design anyone will build.

Frame: x across the machine, y along its length, z up; z = 0 is the base's top face, centred on x = y = 0.

    base         3 mm laser-cut steel plate, 200 x 300, z -3 to 0
    insulator    6 mm polyimide, 90 x 70, on the base
    hot_plate    10 mm aluminium, 80 x 60, on the insulator (z 6 to 16): the heat source
    back_wall    3 mm laser-cut acrylic, 200 x 80, standing on the base at x = 88 to 91
    gantry/...   the project mini_gantry (a sibling folder), turned a quarter about z: its beam, 260 mm long, runs along
                 y over the hot plate, 50 mm up on two posts at y = +-120, and its carriage runs along y on the beam

Two axes. `slide` moves the whole gantry along x on the base, 60 mm either way; `gantry/x` is the gantry's own carriage
axis, which the quarter turn has made an axis along y. POSES name the two together: `park`, the gantry at the wall end
with its carriage back, and `work`, the carriage over the plate.
"""
from build123d import Pos
from cad_agent.state import build_part

SLUG = "mini_machine"

SUBASSEMBLIES = {
    "gantry": {"project": "mini_gantry", "at": [0, 0, 0], "turn": [0, 0, 90]},
}

SLIDE = 60.0                # the gantry's travel along x, from where assembly.py leaves it

AXES = {
    "slide": {
        "moves": ("gantry/*",),                     # every body of the sub-assembly: its names are the child's to choose
        "direction": (1, 0, 0),
        "travel": (-SLIDE, SLIDE),
        "work": (-40.0, 40.0),                      # the hot plate is 80 wide
        "tool": "gantry/tool_plate",
        "tool_point": (0.0, 0.0, 87.0),             # the middle of the plate's top face at home
    },
}

POSES = {
    "park": {"slide": SLIDE, "gantry/x": -45.0},    # at the wall, carriage back
    "work": {"slide": 0.0, "gantry/x": 30.0},       # over the plate
}

# The pairs that touch on purpose; the gantry's own are listed in mini_gantry and come with it
ALLOW_CONTACT = {
    "base|insulator", "insulator|hot_plate", "back_wall|base",
    "gantry/post_left|base", "gantry/post_right|base",
}

CLEARANCE = {
    "gantry/beam|back_wall": 15.0,                  # held by the slide's sweep, over all of its travel
}


def parts():
    base, _ = build_part(SLUG, "base")
    wall, _ = build_part(SLUG, "back_wall")
    insulator, _ = build_part(SLUG, "insulator")
    plate, _ = build_part(SLUG, "hot_plate")
    return {
        "base": Pos(0, 0, -1.5) * base,
        "insulator": Pos(0, 0, 3.0) * insulator,
        "hot_plate": Pos(0, 0, 11.0) * plate,
        "back_wall": Pos(89.5, 0, 40.0) * wall,
    }

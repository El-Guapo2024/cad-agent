"""Assembly cell: one gantry over a bed, carrying both the place and paste heads.

Coordinates. The bed's top face is z = 0 and the board sits on it, so every
tool height in the firmware is measured to that plane and nothing has to know
how thick the bed is. x runs across the machine, y front to back, origin at the
bed centre. Both nozzles sit on y = 0 at home, so the y axis is symmetric and
the two tools differ only in x.

What moves:

    y   the whole gantry, on two rails outboard of the bed
    x   the carriage, along the beam

That ordering is deliberate: the gantry is heavy and moves slowly in y, the
carriage is light and does the fast moves in x. The reverse puts the heavy mass
on the fast axis.

**The machine is much wider than its work area, and that is forced.** Two tool
stations 75 mm apart on one carriage means the carriage must travel 75 mm past
the work area in each direction for both tools to reach every corner, and the
carriage's own 150 mm width goes past that again. A 200 mm work area therefore
needs roughly 540 mm of frame. Sharing a gantry saved an axis and spent bench
width buying it. The sweep rule is what makes that trade visible instead of
discovering it when the head hits an end plate.
"""
from build123d import Box, Pos, Rot
from cad_agent.parts import extrusion_blank
from cad_agent.state import build_part

SLUG = "assembly_cell"

# ── work area, and the tool offsets that size the machine around it ──────────
WORK = (-100.0, 100.0)      # the promise: 200 x 200 mm of board
PLACE_X = -35.0             # place nozzle, in carriage-plate coordinates
SYRINGE_X = 40.0            # paste nozzle. The gap is the firmware tool offset.
PLATE_W = 150.0

# Travel follows from those. The place nozzle must reach +100, so the carriage
# goes to WORK[1] - PLACE_X; the syringe must reach -100, so it goes to
# WORK[0] - SYRINGE_X. Asymmetric travel is the honest consequence of two
# tools on one carriage, not a modelling slip.
X_TRAVEL = (WORK[0] - SYRINGE_X, WORK[1] - PLACE_X)     # (-140, +135)
Y_TRAVEL = WORK                                          # nozzles are on y = 0

# ── frame ────────────────────────────────────────────────────────────────────
BED = (240.0, 240.0, 10.0)
RAIL_X = 248.0          # y rail extrusions, outboard of everything
RAIL_LEN = 420.0
END_X = 222.0           # gantry end plates, 13 mm inboard of the rail face for
                        # the MGN block stack, which is not modelled
BEAM_LEN = 438.0        # ends butt the inner faces of the end plates
BEAM_Y = 58.0
BEAM_Z = 110.0
CARRIAGE_Y = 34.0       # plate rear face 1 mm off the beam front face
CARRIAGE_Z = 100.0
STATION_Z = -14.0       # matches x_carriage station_z

# The nozzle tip at home, in machine coordinates. This is the only place the
# tool's own offset is written down, and the reach rule sweeps exactly it.
NOZZLE = (PLACE_X, 0.0, 5.0)

AXES = {
    "x": {
        "moves": ("x_carriage", "syringe_clamp"),
        "direction": (1, 0, 0),
        "travel": X_TRAVEL,
        "work": WORK,
        "tool": "x_carriage",
        "tool_point": NOZZLE,
    },
    "y": {
        "moves": ("x_carriage", "syringe_clamp", "gantry_beam",
                  "gantry_end_left", "gantry_end_right"),
        "direction": (0, 1, 0),
        "travel": Y_TRAVEL,
        "work": WORK,
        "tool": "x_carriage",
        "tool_point": NOZZLE,
    },
}

# Bolted joints, which touch by design and must keep touching through travel.
ALLOW_CONTACT = {
    "gantry_beam|gantry_end_left", "gantry_beam|gantry_end_right",
    "syringe_clamp|x_carriage",
}

# Gaps that are requirements rather than accidents.
CLEARANCE = {
    # The carriage rides the beam on MGN blocks that are not in this model, so
    # the plate itself must never come nearer than the block leaves it.
    "gantry_beam|x_carriage": 1.0,
    # Head-to-bed: a board and its paste sit in this gap.
    "bed|x_carriage": 5.0,
    "bed|syringe_clamp": 5.0,
    # End plate to rail: the MGN block stack lives here, so the space must
    # stay open even though nothing in the model occupies it.
    "gantry_end_left|rail_left": 12.0,
    "gantry_end_right|rail_right": 12.0,
    # Carriage to end plate at the travel limits. Nothing forced this gap, so
    # nothing was holding it: the first build of this assembly drove the
    # carriage straight through both end plates and only the sweep rule said so.
    "gantry_end_left|x_carriage": 3.0,
    "gantry_end_right|x_carriage": 3.0,
    "gantry_end_left|syringe_clamp": 3.0,
    "gantry_end_right|syringe_clamp": 3.0,
}


def parts():
    carriage, _ = build_part(SLUG, "x_carriage")
    end, _ = build_part(SLUG, "gantry_end")
    clamp, _ = build_part(SLUG, "syringe_clamp")

    # The clamp is modelled with its mounting face on -y; turn it to face the
    # carriage plate behind it.
    clamp = Rot(0, 0, 180) * clamp
    clamp_depth = 8.0 + 23.5 + 2 * 4.0          # back + barrel + two walls

    return {
        "bed": Pos(0, 0, -BED[2] / 2.0) * Box(*BED),
        "rail_left": Pos(-RAIL_X, 0, 10.0) * extrusion_blank("2040", RAIL_LEN, axis="y"),
        "rail_right": Pos(RAIL_X, 0, 10.0) * extrusion_blank("2040", RAIL_LEN, axis="y"),
        "gantry_beam": Pos(0, BEAM_Y, BEAM_Z) * extrusion_blank("2040", BEAM_LEN, axis="x"),
        "gantry_end_left": Pos(-END_X, BEAM_Y, BEAM_Z - 40.0) * end,
        "gantry_end_right": Pos(END_X, BEAM_Y, BEAM_Z - 40.0) * end,
        "x_carriage": Pos(0, CARRIAGE_Y, CARRIAGE_Z) * carriage,
        "syringe_clamp": Pos(SYRINGE_X,
                             CARRIAGE_Y - 3.0 - clamp_depth / 2.0,
                             CARRIAGE_Z + STATION_Z) * clamp,
    }

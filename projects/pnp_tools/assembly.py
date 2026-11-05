"""The PCB line's pick-and-place: a stock LumenPnP with the board's process tools on its head (Juan, 2026-11-05).

The line is three machines, bought and retrofitted: a 5 W UV galvo marker drills, etches, opens the mask and marks the
legend; this LumenPnP dispenses (via paste, mask, finish, solder paste), cures the mask under its lamps and places;
a T-962A oven cures the via paste and reflows. The board goes between them on its fixture (board_fixture.py).

    lumenpnp_stock  Opulo's LumenPnP v4.2.0, as sold, in two bodies by what moves
    here            the tools on its head (_tools below: two paste dispensers, a mask jet, a gold finish / legend
                    jet, each on its own air slide, and a height sensor), the three 395 nm UV lamps behind the X
                    cable chain's tray, and the board on its fixture across the feeder rails

The frame is LumenPnP's (x along its front feeder rail, its feet at z -100). The board's top is at z 37.
"""
import math

from build123d import Pos, Rot
from cad_agent.state import build_part, bought_solid

SLUG = "pnp_tools"

SUBASSEMBLIES = {"lumenpnp_stock": {"project": "lumenpnp_stock", "at": [0, 0, 0], "turn": [0, 0, 0]}}

B_TOP = 37.0                            # the board's top: the tools are set for it
BOARD_C = (275.0, 182.5)                # the board's middle: inside the head's reach with the gantry's Y travel
RAIL_TOP = 20.0                         # the feeder rails' tops (Opulo's model)
FIXTURE_T = B_TOP - 1.6 - RAIL_TOP      # 15.4
FIXTURE_Y = (0.0, 440.0)                # across both feeder rails (front y -28.7 to 20, rear 410.1 to 470.1)
# the UV lamps behind the X chain's tray (they move with the gantry)
UV_Y, UV_BOT = (302.0, 322.0), 57.0     # their bottoms 20 over the board
TRAY = (240.0, 292.0, 134.758)          # lamp_plate.py's corner: 0.01 under the tray's underside (134.768, measured)
UV_X = (-55.0, 55.0, 0.0)

# the process tools on LumenPnP's head (what CircuitJet IV's print heads do, as dispensers)
TOOL_LIFT = 16.0                         # each slide's working stroke: raised, the tips 16 over the board
HEAD_PLATE_Y = 179.1                     # LumenPnP's head plate's front face (Opulo's model: x 398.8 to 488.8)
TOOL_PLATE_X, TOOL_PLATE_Z = (205.0, 410.0), (60.0, 200.0)   # to 11 over the head plate, left of its nozzle motors
SLIDE_H, SLIDE_Z = 23.0, 110.0           # slide.py: the body's depth; the slides' middles
PEN_X, PEN_TILT, NEEDLE = (338.0, 378.0), 35.0, 25.4   # the clamps 40 wide; 35 degrees forward; a 1 in Luer needle
JET_X, JET_GAP = (295.0, 269.0), 1.5     # the mask jet; the finish / legend jet
SENSOR_X, SENSOR_RANGE = 240.0, 30.0
TOOLS = ("eco_pen_1", "eco_pen_2", "pico_jet_1", "pico_jet_2")
TOOL_CONTACT = {"height_sensor|tool_plate", "eco_pen_1|pen_clamp_1", "eco_pen_2|pen_clamp_2",
                "pen_clamp_1|slide_1", "pen_clamp_2|slide_2", "pico_jet_1|slide_3", "pico_jet_2|slide_4"} | {
    f"slide_{i}|tool_plate" for i in range(1, 5)}

GANTRY = ("lumenpnp_stock/gantry", "lamp_plate", "uv_lamp_1", "uv_lamp_2", "uv_lamp_3",
          "tool_plate", "height_sensor") + tuple(f"slide_{i}" for i in range(1, 5)) + (
          "eco_pen_1", "eco_pen_2", "pen_clamp_1", "pen_clamp_2", "pico_jet_1", "pico_jet_2")  # what LumenPnP's Y moves
AXES = {"y": {"moves": GANTRY, "direction": (0, 1, 0), "travel": (-170.0, 230.0), "work": (-170.0, 230.0)}}
AXES.update({f"{t}_z": {"moves": (t,) + ((f"pen_clamp_{t[-1]}",) if t.startswith("eco") else ()),
                        "direction": (0, 0, 1), "travel": (-TOOL_LIFT, 0.0), "work": (-TOOL_LIFT, 0.0)}
             for t in TOOLS})
POSES = {"front": {"y": -170.0}, "back": {"y": 230.0},
         "uv_cure": {"y": BOARD_C[1] - sum(UV_Y) / 2.0}}               # the lamps over the board's middle
POSES.update({f"{t}_down": {f"{t}_z": -TOOL_LIFT} for t in TOOLS})

CLEARANCE = {}
ALLOW_CONTACT = {"uv_lamp_1|lamp_plate", "uv_lamp_2|lamp_plate",
                 "uv_lamp_1|uv_lamp_2", "uv_lamp_1|uv_lamp_3", "uv_lamp_2|uv_lamp_3",
                 "lamp_plate|lumenpnp_stock/gantry", "tool_plate|lumenpnp_stock/gantry",
                 "board_fixture|lumenpnp_stock/frame", "pcb_blank|board_fixture"} | TOOL_CONTACT


def parts():
    p = lambda n, **o: build_part(SLUG, n, o or None)[0]
    b = lambda n, **o: bought_solid(SLUG, n, **o)
    out = {}
    fy = sum(FIXTURE_Y) / 2.0
    out["board_fixture"] = Pos(BOARD_C[0], fy, RAIL_TOP + FIXTURE_T / 2.0) * p(
        "board_fixture", size_y=FIXTURE_Y[1] - FIXTURE_Y[0], thick=FIXTURE_T, board_dy=BOARD_C[1] - fy)
    out["pcb_blank"] = Pos(BOARD_C[0], BOARD_C[1], B_TOP - 0.8) * b("pcb_blank")
    out["lamp_plate"] = Pos(BOARD_C[0], TRAY[1], TRAY[2]) * p("lamp_plate")
    for i, (dx, y) in enumerate(zip(UV_X, (UV_Y[0], UV_Y[0], UV_Y[1])), 1):
        out[f"uv_lamp_{i}"] = Pos(BOARD_C[0] + dx, y, UV_BOT + 59.0) * b("uv_lamp")
    _tools(out, p, b)
    return out


def _tools(out, p, b):
    """The process tools on LumenPnP's head, beside its two nozzles: what CircuitJet IV's print heads do, as dispensers.

    eco_pen_1    solder paste (ViscoTec eco-PEN300, volumetric, 1 ul): no stencil, as CircuitJet's syringe
    eco_pen_2    via paste (silver), dotted onto each drilled hole; the oven cures it
    pico_jet_1   UV solder mask (Agfa DiPaMAT SM G01 cures at 395 nm), jetted as dots, then cured by the gantry's
                 lamps; the laser opens the pads after
    pico_jet_2   the gold finish over the opened pads, as CircuitJet's ENIG ink: PV Nano Cell's gold ink for inkjet
                 and aerosol printing (Sicrys IAu20W, water based; pvnanocell.com, 2020 launch), cured in the oven if
                 its profile fits, else the UV laser sinters it pad by pad; or white legend ink (Agfa DiPaMat Wh04,
                 395 nm) when the laser does not mark the legend
    height_sensor  board height and flatness (Panasonic HG-C1030, 30 mm, 10 um), fixed

Each dispenser and jet rides its own SMC MXH10 air slide (16 of its 20 mm), the way LumenPnP gives each nozzle its own
Z: only the working tool comes down. The slides are on a plate bolted to the head plate's front face (LumenPnP's
model: the head plate x 398.8 to 488.8, its face y 179.1; its nozzle motors fill x 398 up, y 131 to 173, so the tools
hang left of them). The model has no X axis, so this is placed with the head where Opulo's model has it. The pens
lean 35 degrees forward (their clamps were drawn so for a lens over them; it costs nothing here).
    """
    out["tool_plate"] = Pos(sum(TOOL_PLATE_X) / 2.0, HEAD_PLATE_Y - 3.0, sum(TOOL_PLATE_Z) / 2.0) * p("tool_plate")
    front = HEAD_PLATE_Y - 6.0                                       # 173.1: the tool plate's front, the slides' backs
    table = front - SLIDE_H                                          # 150.1: the slides' tables, the tools' backs
    for i, x in enumerate(PEN_X + JET_X, 1):
        out[f"slide_{i}"] = Pos(x, front, SLIDE_Z) * b("slide")
    c, s_ = math.cos(math.radians(PEN_TILT)), math.sin(math.radians(PEN_TILT))
    pen_bot = B_TOP + 0.2 + NEEDLE * c + TOOL_LIFT
    yc = table - 40.0                                                # the clamp: 80 deep from the slide's table
    pen_y = yc + 26.0                                                # the pen's bottom centre: its back 1 off the table
    for i, x in enumerate(PEN_X, 1):
        out[f"eco_pen_{i}"] = Pos(x, pen_y, pen_bot) * Rot(PEN_TILT, 0, 0) * b("eco_pen")
        t = 40.0                                                     # the clamp's middle, up the pen's axis
        cy, cz = pen_y - t * s_, pen_bot + t * c
        out[f"pen_clamp_{i}"] = Pos(x, yc, cz) * p("pen_clamp", bore_y=cy - yc)
    for i, x in enumerate(JET_X, 1):
        out[f"pico_jet_{i}"] = Pos(x, table, B_TOP + JET_GAP + TOOL_LIFT) * b("pico_jet")
    out["height_sensor"] = Pos(SENSOR_X, front - 12.5, B_TOP + SENSOR_RANGE) * b("height_sensor")

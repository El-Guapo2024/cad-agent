"""The process tools on LumenPnP's head, beside its two nozzles: what CircuitJet IV's print heads do, as dispensers.

    eco_pen_1    solder paste (ViscoTec eco-PEN300, volumetric, 1 ul): no stencil, as CircuitJet's syringe
    eco_pen_2    via paste (silver), dotted onto each drilled hole while the platen's vacuum pulls it through
    pico_jet_1   UV solder mask (Agfa DiPaMAT SM G01 cures at 395 nm), jetted as dots, then cured by the gantry's
                 lamps; the laser opens the pads after
    pico_jet_2   the second fluid: the gold finish over the opened pads, as CircuitJet's ENIG ink: PV Nano Cell's
                 gold ink for inkjet and aerosol printing, which it lists for PCBs and soldered joints
                 (pvnanocell.com, 2020 launch), sintered on the platen, or by the laser if it needs more than the
                 platen's 240 C (its sintering temperature is not published); or white legend ink (Agfa DiPaMat
                 Wh04, 395 nm) when the laser does not mark the legend
    height_sensor  board height and flatness for the laser's focus (Panasonic HG-C1030, 30 mm, 10 um), fixed

Each dispenser and jet rides its own SMC MXH10 air slide (16 of its 20 mm), the way LumenPnP gives each nozzle its own
Z: only the working tool comes down, so its neighbours stay clear of the flip frame's edge bars and the stage's posts
wherever it works. The slides are on a plate bolted to the head plate's front face (LumenPnP's model:
the head plate x 398.8 to 488.8, its face y 179.1; its nozzle motors fill x 398 up, y 131 to 173, so the tools hang
left of them). The model has no X axis, so this is placed with the head where Opulo's model has it.
Heights are the lens's: the pens lean 35 degrees forward so their tops stay under the lens (z 272.7), because the
head passes under the laser when it reaches the board's far end. Raised (the model's state): the tips 16 over their
work, clear of the stage's posts when the head works the board's ends.

The frame is the machine's (x, y, z as LumenPnP's model); the parent places this at its origin.
"""
import math

from build123d import Pos, Rot
from cad_agent.state import build_part, bought_solid

SLUG = "head_tools"

B_TOP = 37.0                             # the board's top
LIFT = 16.0                              # each slide's working stroke: raised, the tips clear the stage's posts (51)
PLATE_Y = 179.1                          # the head plate's front face
PLATE_X = (205.0, 410.0)                 # the tool plate: to 11 over the head plate (398.8)
PLATE_Z = (60.0, 200.0)
SLIDE_H = 23.0                           # slide.py: the body's depth
PEN_X = (338.0, 378.0)                   # the clamps 40 wide right of the jets
PEN_TILT = 35.0                          # forward (toward -y): the tops under the lens
NEEDLE = 25.4                            # a 1 in Luer needle on the pen's outlet, along its axis
JET_X, JET_GAP = (295.0, 269.0), 1.5     # the mask jet; the finish / legend jet
SENSOR_X, SENSOR_RANGE = 240.0, 30.0
SLIDE_Z = 110.0                          # the slides' middles

CLEARANCE = {}
TOOLS = ("eco_pen_1", "eco_pen_2", "pico_jet_1", "pico_jet_2")
ALLOW_CONTACT = {"height_sensor|tool_plate", "eco_pen_1|pen_clamp_1",
                 "eco_pen_2|pen_clamp_2"} | {f"slide_{i}|tool_plate" for i in range(1, 5)} | {
    "pen_clamp_1|slide_1", "pen_clamp_2|slide_2", "pico_jet_1|slide_3", "pico_jet_2|slide_4"}


def parts():
    p = lambda n, **o: build_part(SLUG, n, o or None)[0]
    b = lambda n, **o: bought_solid(SLUG, n, **o)
    out = {}
    out["tool_plate"] = Pos(sum(PLATE_X) / 2.0, PLATE_Y - 3.0, sum(PLATE_Z) / 2.0) * p("tool_plate")
    front = PLATE_Y - 6.0                                            # 173.1: the tool plate's front, the slides' backs
    table = front - SLIDE_H                                          # 150.1: the slides' tables, the tools' backs
    for i, x in enumerate(PEN_X + JET_X, 1):
        out[f"slide_{i}"] = Pos(x, front, SLIDE_Z) * b("slide")
    c, s_ = math.cos(math.radians(PEN_TILT)), math.sin(math.radians(PEN_TILT))
    pen_bot = B_TOP + 0.2 + NEEDLE * c + LIFT
    yc = table - 40.0                                                # the clamp: 80 deep from the slide's table
    pen_y = yc + 26.0                                                # the pen's bottom centre: its back 1 off the table
    for i, x in enumerate(PEN_X, 1):
        out[f"eco_pen_{i}"] = Pos(x, pen_y, pen_bot) * Rot(PEN_TILT, 0, 0) * b("eco_pen")
        t = 40.0                                                     # the clamp's middle, up the pen's axis
        cy, cz = pen_y - t * s_, pen_bot + t * c
        out[f"pen_clamp_{i}"] = Pos(x, yc, cz) * p("pen_clamp", bore_y=cy - yc)
    for i, x in enumerate(JET_X, 1):
        out[f"pico_jet_{i}"] = Pos(x, table, B_TOP + JET_GAP + LIFT) * b("pico_jet")
    out["height_sensor"] = Pos(SENSOR_X, front - 12.5, B_TOP + SENSOR_RANGE) * b("height_sensor")
    return out


AXES = {f"{t}_z": {"moves": (t,) + ((f"pen_clamp_{t[-1]}",) if t.startswith("eco") else ()),
                   "direction": (0, 0, 1), "travel": (-LIFT, 0.0), "work": (-LIFT, 0.0)} for t in TOOLS}
POSES = {f"{t}_down": {f"{t}_z": -LIFT} for t in TOOLS}

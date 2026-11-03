"""The process tools on LumenPnP's head, beside its two nozzles: what CircuitJet IV's print heads do, as dispensers.

    eco_pen_1    solder paste (ViscoTec eco-PEN300, volumetric, 1 ul): no stencil, as CircuitJet's syringe
    eco_pen_2    via paste (silver), dotted onto each drilled hole while the platen's vacuum pulls it through
    pico_jet_1   UV solder mask (Agfa DiPaMAT SM G01 cures at 395 nm), jetted as dots, then cured by the gantry's
                 lamps; the laser opens the pads after
    pico_jet_2   the second fluid: white legend ink (Agfa DiPaMat Wh04, 395 nm), or a finish ink over the opened
                 pads (CircuitJet jets its own ENIG ink; ours is still to choose), cured on the platen
    height_sensor  board height and flatness for the laser's focus (Panasonic HG-C1030, 30 mm, 10 um)

They ride an 16 mm lift (MGN12, Tr8x8, NEMA 17) on a plate bolted to the head plate's front face (LumenPnP's
model: the head plate x 398.8 to 488.8, its face y 179.1; its nozzle motors fill x 398 up, y 131 to 173, so the
tools hang left of them). The model has no X axis, so this is placed with the head where Opulo's model has it.
Heights are the lens's: the pens lean 35 degrees forward so their tops stay 12 mm under the lens (z 272.7), because
the head passes under the laser when it reaches the board's far end. Raised (the model's state): the tips 16 over
their work, clear of the stage's posts when the head works the board's ends.

The frame is the machine's (x, y, z as LumenPnP's model); the parent places this at its origin.
"""
import math

from build123d import Pos, Rot
from cad_agent.state import build_part, bought_solid

SLUG = "head_tools"

B_TOP = 37.0                             # the board's top
LIFT = 16.0                              # raised, the tips clear the stage's posts (51) by 2
PLATE_Y = 179.1                          # the head plate's front face
PLATE_X = (205.0, 410.0)                 # the tool plate: to 11 over the head plate (398.8)
PLATE_Z = (60.0, 200.0)
CARRIER_Y = PLATE_Y - 6.0 - 13.0         # 160.1: the MGN12 block's top face (H 13 over the rail's base)
CARRIER_X, CARRIER_Z = (207.0, 397.0), (70.0, 150.0)
RAIL_X = 330.0
PEN_X, PEN_Y = (338.0, 378.0), 138.0     # the clamps 40 wide right of the jet; PEN_Y: the pen's bottom centre
PEN_TILT = 35.0                          # forward (toward -y): the tops 12 under the lens
NEEDLE = 25.4                            # a 1 in Luer needle on the pen's outlet, along its axis
JET_X, JET_GAP = (295.0, 269.0), 1.5     # the mask jet; the finish / legend jet
SENSOR_X, SENSOR_RANGE = 244.0, 30.0
SCREW_X, SCREW_Y = 220.0, 133.0

CLEARANCE = {}
ALLOW_CONTACT = {"tool_rail|tool_plate", "tool_block|tool_rail", "tool_carrier|tool_block",
                 "pen_clamp_1|tool_carrier", "pen_clamp_2|tool_carrier", "eco_pen_1|pen_clamp_1",
                 "eco_pen_2|pen_clamp_2", "pico_jet_1|tool_carrier", "pico_jet_2|tool_carrier", "height_sensor|tool_carrier",
                 "tool_ear|tool_carrier", "t8_nut|tool_ear", "t8_nut|tool_screw", "tool_coupling|tool_screw",
                 "tool_coupling|tool_motor", "tool_motor|motor_mount", "motor_mount|tool_plate"}


def parts():
    p = lambda n, **o: build_part(SLUG, n, o or None)[0]
    b = lambda n, **o: bought_solid(SLUG, n, **o)
    out = {}
    yp = PLATE_Y - 3.0
    out["tool_plate"] = Pos(sum(PLATE_X) / 2.0, yp, sum(PLATE_Z) / 2.0) * p("tool_plate")
    out["tool_rail"] = Pos(RAIL_X, PLATE_Y - 6.0 - 4.0, 130.0) * Rot(0, 0, 90) * Rot(0, -90, 0) * b("tool_rail")
    zc = sum(CARRIER_Z) / 2.0
    out["tool_block"] = Pos(RAIL_X, PLATE_Y - 6.0 - 8.0, zc) * Rot(0, 0, 90) * Rot(0, -90, 0) * b("tool_block")
    front = CARRIER_Y - 6.0                                          # 154.1: the carrier's front face
    out["tool_carrier"] = Pos(sum(CARRIER_X) / 2.0, CARRIER_Y - 3.0, zc) * p("tool_carrier")
    c, s_ = math.cos(math.radians(PEN_TILT)), math.sin(math.radians(PEN_TILT))
    pen_bot = B_TOP + 0.2 + NEEDLE * c + LIFT
    for i, x in enumerate(PEN_X, 1):
        out[f"eco_pen_{i}"] = Pos(x, PEN_Y, pen_bot) * Rot(PEN_TILT, 0, 0) * b("eco_pen")
        t = 40.0                                                     # the clamp's middle, up the pen's axis
        cy, cz = PEN_Y - t * s_, pen_bot + t * c
        yc = front - 40.0                                            # the clamp: 80 deep from the carrier's face
        out[f"pen_clamp_{i}"] = Pos(x, yc, cz) * p("pen_clamp", bore_y=cy - yc)
    for i, x in enumerate(JET_X, 1):
        out[f"pico_jet_{i}"] = Pos(x, front, B_TOP + JET_GAP + LIFT) * b("pico_jet")
    out["height_sensor"] = Pos(SENSOR_X, front - 12.5, B_TOP + SENSOR_RANGE + LIFT) * b("height_sensor")
    ear_z = CARRIER_Z[1] - 6.0
    out["tool_ear"] = Pos(SCREW_X, front - 16.0, ear_z) * p("tool_ear", bore_y=SCREW_Y - (front - 16.0))
    nut = ear_z + 6.0
    out["t8_nut"] = Pos(SCREW_X, SCREW_Y, nut) * Rot(180, 0, 0) * b("t8_nut")
    mface = PLATE_Z[1] + 6.0                                         # the motor stands on its mount, shaft down
    half = PLATE_Y - 6.0 - SCREW_Y                                   # to the tool plate's face, centred on the screw
    out["motor_mount"] = Pos(SCREW_X, SCREW_Y, PLATE_Z[1] + 3.0) * Rot(0, 90, 0) * p(
        "motor_mount", size_y=2 * half, size_z=42.0, bore_z=0.0)
    out["tool_motor"] = Pos(SCREW_X, SCREW_Y, mface) * Rot(180, 0, 0) * b("tool_motor")
    tip = mface - 23.88                                              # the motor's shaft end: the coupling's middle
    out["tool_coupling"] = Pos(SCREW_X, SCREW_Y, tip) * Rot(180, 0, 0) * b("coupling")
    s1 = tip
    s0 = ear_z - 6.0 - LIFT - 2.0
    out["tool_screw"] = Pos(SCREW_X, SCREW_Y, (s0 + s1) / 2.0) * b("t8_screw", length=s1 - s0)
    return out


AXES = {"tool_z": {"moves": ("tool_block", "tool_carrier", "pen_clamp_1", "pen_clamp_2", "eco_pen_1", "eco_pen_2",
                             "pico_jet_1", "pico_jet_2", "height_sensor", "tool_ear", "t8_nut"),
                   "direction": (0, 0, 1), "travel": (-LIFT, 0.0), "work": (-LIFT, 0.0)}}
POSES = {"dispense": {"tool_z": -LIFT}}

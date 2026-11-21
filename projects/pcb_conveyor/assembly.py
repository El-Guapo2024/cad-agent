"""One conveyor module of the open PCB line, positioned (2026-11-21).

A production-grade SMEMA edge-belt conveyor: the board rides on two flat belts, one along each rail, the way
SuperHouse's PCBCONVEYOR (Jonathan Oxer, TAPR OHL) and the commercial SMT conveyors carry it. Where SuperHouse prints
its parts and uses 1 in tube, this is built to last: 4040 extrusion frame, machined aluminium rails and mounts, one
motor driving both belts through a hex shaft, the rear rail on linear guides moved by two lead screws.

SMEMA Mechanical Equipment Interface Standard 1.2 (in SuperHouse's repo, Resources/smema1.2.pdf) sets:
  board bottom 37 to 38 in (939.8 to 965.2) off the floor, adjustable   -> the feet; nominal 952.5 here
  front rail fixed, rear rail adjustable                                 -> rear_carriage on guides
  edge clearance no more than 0.187 in (4.75)                            -> the rail's 4.5 ledge
  gap between machines' track ends at most 0.375 in (9.5)                -> the rails run the module's full length
  lead-in at least 0.125 in (3.2)                                        -> the rails' 4 mm end chamfers

Frame: x along the board's travel (+x out), y across from the front rail's inner face (y 0) to the back, z up from
the floor. W is the gap between the rails' inner faces: the board's (or its carrier's) width.
"""
from build123d import Plane, Pos, Rot, mirror

from cad_agent.state import build_part, bought_solid

SLUG = "pcb_conveyor"

ZB = 952.5                   # the board's bottom: SMEMA's 37.5 in, mid-range
L = 600.0                    # the module's track length (design choice)
W = 50.0                     # the rails' gap as drawn: the narrowest, so the width sweep opens away from the board
W_CARRIER = 170.0            # a 150 board on its carrier (the carrier is not designed yet): pose "carrier"
W_RANGE = (50.0, 350.0)      # what the width screws reach (design choice)
EXT = 40.0                   # 4040
BEAM_X = L / 2.0 - 60.0      # the cross beams (and the guides, the front blocks)
BEAM_TOP = ZB - 100.0
Y_BACK = W_RANGE[1] + 12.0 + 40.0          # the cross beams' rear end
LEG_X = L / 2.0 - 20.0
FOOT_H = 50.0
DRIVE = (L / 2.0 - 40.0, -50.0)            # the drive pulleys and hex shaft (x, z off ZB)
RETURN = (-(L / 2.0 - 40.0), -50.0)
IDLER = (L / 2.0 - 10.0, -11.5)
SCREW_DX, SCREW_DZ = 30.0, -84.0           # the lead screws: beside each guide, z off ZB
SCREW_Y = (10.0, Y_BACK - 2.0)
SHAFT_Y = (-20.0, W_RANGE[1] + 22.0)

CLEARANCE = {"hex_shaft|lead_screw_2": 5.0}
ALLOW_CONTACT = {
    "front_rail|front_block_1", "front_rail|front_block_2", "front_block_1|cross_beam_1", "front_block_2|cross_beam_2",
    "cross_beam_1|long_beam_front", "cross_beam_1|long_beam_rear", "cross_beam_2|long_beam_front",
    "cross_beam_2|long_beam_rear", "guide_rail_1|cross_beam_1", "guide_rail_2|cross_beam_2",
    "guide_block_1|guide_rail_1", "guide_block_2|guide_rail_2", "rear_carriage_1|guide_block_1",
    "rear_carriage_2|guide_block_2", "rear_rail|rear_carriage_1", "rear_rail|rear_carriage_2",
    "hex_shaft|gearmotor", "test_board|front_belt", "test_board|rear_belt"} | {f"leg_{i}|long_beam_{s}" for i, s in ((1, "front"), (2, "front"), (3, "rear"), (4, "rear"))} | {
    f"foot_{i}|leg_{i}" for i in range(1, 5)} | {f"{s}_belt|{s}_rail" for s in ("front", "rear")} | {
    f"{s}_belt|{s}_{p}" for s in ("front", "rear") for p in ("idler_in", "idler_out", "return", "drive")} | {
    f"hex_shaft|{s}_drive" for s in ("front", "rear")}

AXES = {"width": {"moves": ("rear_rail", "rear_belt", "rear_idler_in", "rear_idler_out", "rear_return", "rear_drive",
                            "rear_carriage_1", "rear_carriage_2", "guide_block_1", "guide_block_2"),
                  "direction": (0, 1, 0), "travel": (W_RANGE[0] - W, W_RANGE[1] - W),
                  "work": (W_RANGE[0] - W, W_RANGE[1] - W)}}
POSES = {"carrier": {"width": W_CARRIER - W}, "wide": {"width": W_RANGE[1] - W}}


def _side(p, b):
    """A rail with its belt and pulleys, in the front rail's frame (inner face y 0, belt top z 0)."""
    s = {"rail": p("rail", drive_x=DRIVE[0], drive_z=DRIVE[1], idler_x=IDLER[0], idler_z=IDLER[1],
                   return_x=-RETURN[0])}
    s["belt"] = b("flat_belt", end_x=IDLER[0], low_x=DRIVE[0], top_z=IDLER[1], low_z=DRIVE[1], y0=0.5)
    y = 0.3
    s["idler_in"] = Pos(-IDLER[0], y, IDLER[1]) * p("pulley")
    s["idler_out"] = Pos(IDLER[0], y, IDLER[1]) * p("pulley")
    s["return"] = Pos(RETURN[0], y, RETURN[1]) * p("pulley")
    s["drive"] = Pos(DRIVE[0], y, DRIVE[1]) * p("pulley", hex=10.2)
    return s


def parts():
    p = lambda n, **o: build_part(SLUG, n, o or None)[0]
    b = lambda n, **o: bought_solid(SLUG, n, **o)
    out = {}
    for k, v in _side(p, b).items():
        out[f"front_{k}"] = Pos(0, 0, ZB) * v
        out[f"rear_{k}"] = Pos(0, W, ZB) * mirror(v, Plane.XZ)
    # the frame: two cross beams on two long beams on four legs, on feet
    yc = (Y_BACK - EXT) / 2.0
    for i, x in enumerate((-BEAM_X, BEAM_X), 1):
        out[f"cross_beam_{i}"] = Pos(x, yc, BEAM_TOP - EXT / 2.0) * Rot(90, 0, 0) * b(
            "extrusion_4040", length=Y_BACK + EXT)
        out[f"front_block_{i}"] = Pos(x, 0, ZB - 70.0) * p("front_block")
        out[f"guide_rail_{i}"] = Pos(x, (20.0 + Y_BACK) / 2.0, BEAM_TOP) * b("guide_rail", length=Y_BACK - 20.0)
        out[f"guide_block_{i}"] = Pos(x, W + 20.0, BEAM_TOP) * b("guide_block")
        out[f"rear_carriage_{i}"] = Pos(x, W, ZB - 70.0) * p("rear_carriage")
        out[f"lead_screw_{i}"] = Pos(x + SCREW_DX, sum(SCREW_Y) / 2.0, ZB + SCREW_DZ) * b(
            "lead_screw", length=SCREW_Y[1] - SCREW_Y[0])
    low = BEAM_TOP - EXT
    for s, y in (("front", -EXT / 2.0), ("rear", Y_BACK - EXT / 2.0)):
        out[f"long_beam_{s}"] = Pos(0, y, low - EXT / 2.0) * Rot(0, 90, 0) * b("extrusion_4040", length=L)
    leg_top, leg_bot = low - EXT, FOOT_H
    for i, (x, y) in enumerate(((-LEG_X, -EXT / 2.0), (LEG_X, -EXT / 2.0),
                                (-LEG_X, Y_BACK - EXT / 2.0), (LEG_X, Y_BACK - EXT / 2.0)), 1):
        out[f"leg_{i}"] = Pos(x, y, (leg_top + leg_bot) / 2.0) * b("extrusion_4040", length=leg_top - leg_bot)
        out[f"foot_{i}"] = Pos(x, y, leg_bot) * b("foot")
    # the drive: one gearmotor on the hex shaft, which turns both belts' drive pulleys
    out["hex_shaft"] = Pos(DRIVE[0], sum(SHAFT_Y) / 2.0, ZB + DRIVE[1]) * b(
        "hex_shaft", length=SHAFT_Y[1] - SHAFT_Y[0])
    out["gearmotor"] = Pos(DRIVE[0], SHAFT_Y[0], ZB + DRIVE[1]) * b("gearmotor")
    # the width: a stepper on the exit-end screw (the two screws are belted together: not drawn yet)
    out["width_motor"] = Pos(BEAM_X + SCREW_DX, SCREW_Y[1] + 25.0, ZB + SCREW_DZ) * Rot(0, 0, 180) * b("stepper")
    out["test_board"] = Pos(0, 0.5, ZB) * b("test_board", width=W - 1.0)   # the narrowest board
    return out

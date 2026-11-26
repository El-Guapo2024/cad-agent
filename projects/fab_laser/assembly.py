"""Machine 1, the fab machine, v1: the UV laser only (2026-11-26). It turns a blank (pre-plated via grid blanks to
start) into a board with its copper isolated, both sides; machine 2 (paste, place, reflow) takes the same carrier.

A fixed galvo laser over the board, the board still: LPKF's ProtoLaser layout, with the laser riding a motorised Z
column (the usual galvo marking-machine column) so any lens's working distance and any board thickness can be
focused. The source and the galvo head ride together (UV has no fibre delivery). The board sits in the line's
carrier on the line's nest (two pins), so it is located the same way here and in machine 2. Laser parts are
PLACEHOLDERS (bought/*.py say so) until the laser is chosen: their working distance sets the Z height.

To add later: the enclosure (laser class 4 open beam: interlocked, 355 nm-blocking windows), fume extraction and
air assist, the camera that finds the board's holes, the flip frame.

Frame: z up from the bench, the nest's front at y -10, the laser's field centred on the board (x 0, y 85).
"""
from build123d import Pos, Rot

from cad_agent.state import build_part, bought_solid

SLUG = "fab_laser"

BOARD_Y = 85.0
NEST_Z = 50.0                 # the nest's top: on the 40 mm base beams
CARRIER_T, BOARD_T = 6.0, 1.6
BOARD_TOP = NEST_Z + CARRIER_T
WD = 185.0                    # lens bottom to the board: PLACEHOLDER, the chosen lens's working distance
LENS_L, ARM_T = 45.0, 12.0
COL_Y = 250.0                 # the column's axis; its front face at y 230
COL_TOP = 580.0
TOP_T = 15.0                  # the top plate: thick enough that the motor shaft (20) and the screw end (11) meet in the coupler
SCREW_TOP = 574.0
SCREW_X = 45.0
FAR_X = 330.0                 # the far base beam, under the UV source
RAIL_FACE = COL_Y - 20.0
BLOCK_FACE = RAIL_FACE - 13.0
CAR_T, CAR_H = 10.0, 140.0
ZC = BOARD_TOP + WD + LENS_L - ARM_T + CAR_H / 2.0   # the carriage centre that puts the lens bottom WD over the board
ARM_Z = ZC - CAR_H / 2.0      # the arm's bottom, level with the carriage's

CLEARANCE = {}
ALLOW_CONTACT = {
    "back_beam|y_beam_l", "back_beam|y_beam_r", "back_beam|y_beam_far",
    "front_beam|y_beam_l", "front_beam|y_beam_r", "front_beam|y_beam_far", "back_beam|column", "nest|y_beam_l", "nest|y_beam_r",
    "nest|pin_l", "nest|pin_r", "carrier|nest", "carrier|pin_l", "carrier|pin_r", "board|carrier",
    "column|rail", "block_upper|rail", "block_lower|rail", "block_upper|carriage", "block_lower|carriage",
    "arm|carriage", "arm|galvo", "galvo|lens", "arm|uv_source", "galvo|uv_source", "carriage|nut_block",
    "lead_nut|nut_block", "lead_nut|lead_screw", "lead_screw|screw_support", "back_beam|screw_support",
    "column|top_plate", "coupler|lead_screw", "coupler|stepper", "stepper|top_plate", "coupler|top_plate",
}

Z_MOVES = ("block_upper", "block_lower", "carriage", "arm", "galvo", "lens", "uv_source", "nut_block", "lead_nut")
AXES = {"z": {"moves": Z_MOVES, "direction": (0, 0, 1), "travel": (-80.0, 100.0)}}

MECHANISM = {
    "rotating": {"lead_screw": {"axis": (0, 0, 1), "supports": ["screw_support", "coupler"]}},
    "axes": {"z": {"guides": [["block_upper", "rail"], ["block_lower", "rail"]], "drive": "lead_screw",
                   "actuator": "stepper"}},
}


def parts():
    p = lambda n, **o: build_part(SLUG, n, o or None)[0]
    b = lambda n, **o: bought_solid(SLUG, n, **o)
    up = Rot(90, 0, 0)                                    # a part drawn along y, stood up along z (its +z to -y)
    out = {}
    for k, x in (("y_beam_l", -80.0), ("y_beam_r", 80.0)):
        out[k] = Pos(x, 130.0, 20.0) * up * b("extrusion_4040", length=300.0)
    # the base runs out under the source (about 9 kg at x ~225) so the machine cannot tip over to the right
    out["y_beam_far"] = Pos(FAR_X, 130.0, 20.0) * up * b("extrusion_4040", length=300.0)
    out["front_beam"] = Pos((FAR_X - 100.0) / 2.0 + 10.0, -40.0, 20.0) * Rot(0, 90, 0) * b(
        "extrusion_4040", length=FAR_X + 120.0)
    out["back_beam"] = Pos((FAR_X - 120.0) / 2.0, COL_Y, 60.0) * Rot(0, 90, 0) * b("extrusion_4040", length=FAR_X + 140.0)
    out["column"] = Pos(0, COL_Y, (80.0 + COL_TOP) / 2.0) * b("extrusion_4040", length=COL_TOP - 80.0)

    out["nest"] = Pos(0, 0, NEST_Z) * p("nest")
    out["carrier"] = Pos(0, 0, NEST_Z) * p("carrier")
    for k, sx in (("pin_l", -1), ("pin_r", 1)):
        out[k] = Pos(sx * 70.0, 7.62, NEST_Z - 10.0) * b("dowel_pin")
    out["board"] = Pos(0, BOARD_Y, BOARD_TOP - BOARD_T) * b("board")

    out["rail"] = Pos(0, RAIL_FACE, 320.0) * up * b("guide_rail", length=400.0)
    for k, dz in (("block_upper", 40.0), ("block_lower", -40.0)):
        out[k] = Pos(0, RAIL_FACE, ZC + dz) * up * b("guide_block")
    out["carriage"] = Pos(0, BLOCK_FACE, ZC) * p("carriage", h=CAR_H, t=CAR_T)
    arm_y = BLOCK_FACE - CAR_T
    out["arm"] = Pos(0, arm_y, ARM_Z) * p("arm", t=ARM_T, lens_y=arm_y - BOARD_Y)
    top = ARM_Z + ARM_T
    out["galvo"] = Pos(0, BOARD_Y, top) * b("galvo_head")
    out["lens"] = Pos(0, BOARD_Y, top) * b("f_theta_lens", length=LENS_L)
    out["uv_source"] = Pos(55.0, BOARD_Y, top) * b("uv_source")

    out["nut_block"] = Pos(SCREW_X, BLOCK_FACE, ZC) * p("nut_block", bore_y=COL_Y - BLOCK_FACE)
    out["lead_nut"] = Pos(SCREW_X, COL_Y, ZC - 20.0) * up * b("lead_nut")
    out["screw_support"] = Pos(SCREW_X, COL_Y, 80.0) * p("screw_support")
    out["lead_screw"] = Pos(SCREW_X, COL_Y, (85.0 + SCREW_TOP) / 2.0) * up * b("lead_screw", length=SCREW_TOP - 85.0)
    out["top_plate"] = Pos(0, COL_Y, COL_TOP) * p("top_plate", t=TOP_T)
    out["coupler"] = Pos(SCREW_X, COL_Y, SCREW_TOP - 11.0) * up * b("coupler")
    out["stepper"] = Pos(SCREW_X, COL_Y, COL_TOP + TOP_T) * Rot(-90, 0, 0) * b("stepper")
    return out

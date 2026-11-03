"""The fab's one fixture: the board in a flip frame over a heated vacuum platen, on an XY stage.

CircuitJet IV keeps the board in one fixture for every step and flips it there; LPKF's ProtoLaser U4 stitches a small
telecentric field over a 229 x 305 board by moving the board under a fixed galvo. This does both:

    the stage    Y (205 mm, the stitching and the reach under the pick-and-place head) on MGN15 rails and an
                 SFU1204 ball screw, X (130 mm) on top of it the same way: 100 x 100 field (Jenoptik's lens) over
                 229 x 305 in 3 x 4 tiles. Each a NEMA 17 through a 5 to 8 mm coupling.
    the frame    a stainless ring (flip_frame.py) holds the board by its edges and turns on two 8 mm trunnion shafts
                 in the posts, about the board's mid-plane: a GT2 belt (20T to 40T) from a NEMA 17 under the X plate.
    the platen   heated (Tempco 625 W mica heater) vacuum table (via fill, hold-down); on a stainless carrier the
                 lift moves 135 mm: up, it meets the board through the frame's window; down, it is clear of the
                 frame's 128.8 mm swing so the frame can turn over. Two MGN12 rails and two Tr8x2 screws, one of
                 each per post, each screw on its own NEMA 17 (34 mm) under the X plate.

The frame: x, y from the optical axis with both axes at 0, z the machine's (the board's top at 37.0, LumenPnP's
staging-plate height, so its nozzles reach it). The parent places this at the laser's optical axis.
"""
from build123d import Pos, Rot
from cad_agent.state import build_part, bought_solid

SLUG = "fab_stage"

BOARD = (229.0, 305.0, 1.6)
B_TOP = 37.0
PIV = B_TOP - BOARD[2] / 2.0             # the flip axis: the board's mid-plane, along y
RING_T, SHIM_T = 5.2, BOARD[2]           # frame_ring.py: two rings and the shim between, 12 in all
FRAME_END = BOARD[1] / 2.0 + 0.2 + 14.0  # 166.7: the frame's end face
DROP = 135.0                             # the lift's travel: the platen top from 35.4 to -99.6, under the swing (-92.6)
TRAVEL_X, TRAVEL_Y = 65.0, 102.5         # (229 - 100) / 2, (305 - 100) / 2

# the platen stack, work position, top down
PLATEN_TOP = B_TOP - BOARD[2]            # 35.4: the board's underside
SKIN_T, RING_PT, BASE_T = 5.0, 6.0, 4.0  # platen_skin, platen_ring, platen_base
HEATER_T, CLAMP_T, STANDOFF_H, CARRIER_T = 4.5, 3.0, 10.0, 4.0
HEATER_TOP = PLATEN_TOP - SKIN_T - RING_PT - BASE_T
CLAMP_TOP = HEATER_TOP - HEATER_T
STANDOFF_TOP = CLAMP_TOP - CLAMP_T
CARRIER_TOP = STANDOFF_TOP - STANDOFF_H  # 2.9
# the posts and the lift
POST_IN, POST_T = 195.7, 12.0            # the post's inner face (y), its thickness
XP_TOP, PLATE_T = -139.0, 10.0           # the X plate: 3 mm under the dropped carrier (-136.1)
POST_BOT, POST_TOP = XP_TOP, 51.0        # its top 6 under the gantry's UV lamps' bottoms (57)
RAIL_X, SCREW_X = 35.0, -35.0            # the lift's MGN12 rail and Tr8x2 screw, either side of the shaft
LIFT_RAIL_H, LIFT_BLOCK_H = 8.0, 13.0    # MGN12: rail height, H (base to the block's top)
LIFT_BLOCK_Z = 24.0                      # the lift block's centre at work (45.4 long: 1.3 to 46.7)
SCREW_Y = 181.2                          # the nut block (26 deep) between the frame's swing and the post
NUT_BLOCK_H = 32.0                       # nut_shelf.py
COUPLING_L = 29.0
SCREW_TOP = 50.0
# the X stage under the X plate
XP_Y = POST_IN + POST_T                  # 207.7: the X plate's half length
XP_X = 75.0
X_RAIL_Y, X_BLOCK_X = 120.0, 40.0        # the X rails (along x) at y +-120, a block each side at x +-40
MGN15_H, MGN15_BLOCK = 10.0, 6.0         # rail height; the block's half height about the rail's top
RISER_H = 22.0
YP_TOP = XP_TOP - PLATE_T - MGN15_BLOCK - MGN15_H - RISER_H     # -187
BK_H = 22.0                              # BK10 / BF10 centre height
X_SCREW_Z = YP_TOP + BK_H                # -165: the nut's flats (30) clear the X plate by 1
YP_X0, YP_X1, YP_Y = -175.0, 265.0, 155.0
# the Y stage on the cabinet's floor
Y_RAIL_X, Y_BLOCK_Y = 150.0, 100.0
FLOOR = YP_TOP - PLATE_T - MGN15_BLOCK - MGN15_H - 40.0           # -253: under the 4040 beams
Y_SCREW_Z = -213.0                       # the nut's flats clear the Y plate (-197) by 1
FLIP_MOTOR = (30.0, 200.0, -173.0)       # its face (y) and axis: under the X plate, clear of BF10's top (-197)

CLEARANCE = {}


def _contact():
    c = set()
    for s in (1, 2):
        c |= {f"post_{s}|x_plate", f"lift_rail_{s}|post_{s}", f"lift_block_{s}|lift_rail_{s}",
              f"lift_arm_{s}|lift_block_{s}", f"lift_arm_{s}|carrier", f"nut_block_{s}|carrier",
              f"t8_nut_{s}|nut_block_{s}", f"t8_nut_{s}|lift_screw_{s}", f"lift_coupling_{s}|lift_screw_{s}",
              f"lift_coupling_{s}|lift_motor_{s}", f"lift_motor_{s}|x_plate", f"lift_coupling_{s}|x_plate",
              f"shaft_{s}|trunnion_{s}", f"riser_{s}|y_plate", f"x_rail_{s}|riser_{s}", f"y_rail_{s}|y_beam_{s}"}
        c |= {f"trunnion_{s}|{f}" for f in ("frame_ring_lower", "frame_shim", "frame_ring_upper")}
        for k in (1, 2):
            c |= {f"y_block_{s}{k}|y_rail_{s}", f"y_block_{s}{k}|y_plate", f"x_block_{s}{k}|x_rail_{s}",
                  f"x_block_{s}{k}|x_plate"}
    for i in range(1, 5):
        c |= {f"standoff_{i}|carrier", f"standoff_{i}|clamp_plate"}
    c |= {"heater|platen", "heater|clamp_plate", "clamp_plate|platen", "frame_ring_lower|frame_shim",
          "frame_shim|frame_ring_upper", "pcb_blank|frame_shim", "pcb_blank|frame_ring_lower",
          "pcb_blank|frame_ring_upper",
          "pcb_blank|platen", "pt1000_probe|platen", "cutout|platen", "pulley_40|shaft_2", "pulley_20|flip_motor",
          "flip_motor|motor_mount_3", "motor_mount_3|x_plate",
          "x_nut|nut_bracket_1", "nut_bracket_1|x_plate", "x_nut|x_screw", "x_screw|x_bk10", "x_screw|x_bf10",
          "x_bk10|y_plate", "x_bf10|y_plate", "x_coupling|x_screw", "x_coupling|x_motor", "x_motor|motor_mount_1",
          "motor_mount_1|y_plate",
          "y_nut|nut_bracket_2", "nut_bracket_2|y_plate", "y_nut|y_screw", "y_screw|y_bk10", "y_screw|y_bf10",
          "y_bk10|support_block_1", "y_bf10|support_block_2", "y_coupling|y_screw", "y_coupling|y_motor", "y_motor|motor_mount_2"}
    return c


ALLOW_CONTACT = _contact()


def parts():
    p = lambda n, **o: build_part(SLUG, n, o or None)[0]
    b = lambda n, **o: bought_solid(SLUG, n, **o)
    out = {}
    # the board in its frame, on the flip axis
    out["pcb_blank"] = Pos(0, 0, PIV) * b("pcb_blank")
    half = SHIM_T / 2.0 + RING_T / 2.0
    out["frame_ring_lower"] = Pos(0, 0, PIV - half) * p("frame_ring")
    out["frame_shim"] = Pos(0, 0, PIV) * p("frame_shim")
    out["frame_ring_upper"] = Pos(0, 0, PIV + half) * p("frame_ring")
    for s, sy in ((1, -1), (2, 1)):
        out[f"trunnion_{s}"] = Pos(0, sy * (FRAME_END + 5.0), PIV) * Rot(0, 0, 90 - 90 * sy) * p("trunnion")
        inner = FRAME_END + 10.0 - 8.0                                   # the block's 8 deep bore
        outer = POST_IN + POST_T + (15.3 if s == 2 else 0.0)            # the +y one carries the 40T pulley
        out[f"shaft_{s}"] = Pos(0, sy * (inner + outer) / 2.0, PIV) * Rot(90, 0, 0) * p("shaft", dia=8.0,
                                                                                    length=outer - inner)
    # the platen (three layers bonded into one body) and what hangs under it
    out["platen"] = (Pos(0, 0, PLATEN_TOP - SKIN_T / 2.0) * p("platen_skin")
                     + Pos(0, 0, PLATEN_TOP - SKIN_T - RING_PT / 2.0) * p("platen_ring")
                     + Pos(0, 0, HEATER_TOP + BASE_T / 2.0) * p("platen_base"))
    out["heater"] = Pos(0, 0, HEATER_TOP - HEATER_T / 2.0) * b("heater")
    out["clamp_plate"] = Pos(0, 0, CLAMP_TOP - CLAMP_T / 2.0) * p("clamp_plate")
    for i, (sx, sy) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1)), 1):
        out[f"standoff_{i}"] = Pos(sx * (215.0 / 2.0 - 15.0), sy * (295.0 / 2.0 - 15.0),
                                   STANDOFF_TOP - STANDOFF_H / 2.0) * p("standoff")
    out["carrier"] = Pos(0, 0, CARRIER_TOP - CARRIER_T / 2.0) * p("carrier")
    ring_z = PLATEN_TOP - SKIN_T - RING_PT / 2.0
    out["pt1000_probe"] = (Pos(215.0 / 2.0 - 7.5, -295.0 / 2.0 - 25.0 + 50.0, ring_z) * Rot(90, 0, 0)
                           * b("pt1000_probe"))                 # 75 in the ring's slot, 25 out of the -y end
    out["cutout"] = Pos(-215.0 / 2.0 - 5.0, -60.0, 20.0) * Rot(0, 90, 0) * Rot(0, 0, 90) * b("cutout")
    # the posts, the lift
    for s, sy in ((1, -1), (2, 1)):
        out[f"post_{s}"] = Pos(0, sy * (POST_IN + POST_T / 2.0), (POST_BOT + POST_TOP) / 2.0) * p(
            "post", height=POST_TOP - POST_BOT, bore_z=PIV - POST_BOT)
        turn = Rot(0, 0, 90 * sy) * Rot(0, -90, 0)                    # along z, its height toward the frame
        out[f"lift_rail_{s}"] = Pos(RAIL_X, sy * (POST_IN - LIFT_RAIL_H / 2.0), POST_BOT + 2.0 + 185.0 / 2.0) * turn * b(
            "lift_rail")
        out[f"lift_block_{s}"] = Pos(RAIL_X, sy * (POST_IN - LIFT_RAIL_H), LIFT_BLOCK_Z) * turn * b("lift_block")
        top = POST_IN - LIFT_BLOCK_H                                  # 182.7: the block's top face
        arm_bot, arm_top = CARRIER_TOP, LIFT_BLOCK_Z + 45.4 / 2.0
        out[f"lift_arm_{s}"] = Pos(RAIL_X, sy * (top - 3.0), (arm_bot + arm_top) / 2.0) * p(
            "lift_arm", height=arm_top - arm_bot)
        out[f"nut_block_{s}"] = Pos(SCREW_X, sy * SCREW_Y, CARRIER_TOP + NUT_BLOCK_H / 2.0) * p("nut_block")
        out[f"t8_nut_{s}"] = Pos(SCREW_X, sy * SCREW_Y, CARRIER_TOP + NUT_BLOCK_H) * Rot(180, 0, 0) * b("t8_nut")
        out[f"lift_coupling_{s}"] = Pos(SCREW_X, sy * SCREW_Y, XP_TOP + COUPLING_L / 2.0) * b("coupling")
        s0 = XP_TOP + COUPLING_L / 2.0
        out[f"lift_screw_{s}"] = Pos(SCREW_X, sy * SCREW_Y, (s0 + SCREW_TOP) / 2.0) * b("t8_screw",
                                                                                     length=SCREW_TOP - s0)
        out[f"lift_motor_{s}"] = Pos(SCREW_X, sy * SCREW_Y, XP_TOP - PLATE_T) * b("lift_motor")
    # the flip drive: 40T on the +y shaft outside its post, 20T on the motor under the X plate
    out["pulley_40"] = Pos(0, XP_Y + 1.0 + 7.0, PIV) * Rot(90, 0, 0) * p("pulley", teeth=40)
    fx, fy, fz = FLIP_MOTOR
    out["flip_motor"] = Pos(fx, fy, fz) * Rot(-90, 0, 0) * b("lift_motor")
    out["pulley_20"] = Pos(fx, XP_Y + 1.0 + 7.0, fz) * Rot(90, 0, 0) * p("pulley", teeth=20, bore=5.0, hub_dia=12.0)
    m0, m1 = XP_TOP - PLATE_T, YP_TOP - PLATE_T + 2.0                 # under the X plate to 2 over BF10's top
    out["motor_mount_3"] = Pos(fx, fy + 3.0, (m0 + m1) / 2.0) * Rot(0, 0, 90) * p(
        "motor_mount", size_z=m0 - m1, bore_z=fz - (m0 + m1) / 2.0)
    # the X plate, its carriages, rails, risers and screw on the Y plate
    out["x_plate"] = Pos(0, 0, XP_TOP - PLATE_T / 2.0) * p("x_plate")
    rail_top = XP_TOP - PLATE_T - MGN15_BLOCK
    for s, sy in ((1, -1), (2, 1)):
        for k, sx in ((1, -1), (2, 1)):
            out[f"x_block_{s}{k}"] = Pos(sx * X_BLOCK_X, sy * X_RAIL_Y, rail_top) * b("rail_block")
        out[f"x_rail_{s}"] = Pos(0, sy * X_RAIL_Y, rail_top - MGN15_H / 2.0) * b("x_rail")
        out[f"riser_{s}"] = Pos(0, sy * X_RAIL_Y, YP_TOP + RISER_H / 2.0) * p("riser")
    _screw(out, b, p, "x", (1, 0, 0), XP_X + TRAVEL_X + 5.0, YP_TOP, X_SCREW_Z)
    out["x_nut"] = Pos(-8.0, 0, X_SCREW_Z) * Rot(0, -90, 0) * Rot(0, 0, 90) * b("ballnut")
    out["nut_bracket_1"] = Pos(10.0, 0, XP_TOP - PLATE_T - 15.0) * p("nut_bracket")
    # the Y plate, its carriages, rails and screw on two 4040 beams on the floor
    out["y_plate"] = Pos((YP_X0 + YP_X1) / 2.0, 0, YP_TOP - PLATE_T / 2.0) * p("y_plate")
    rail_top = YP_TOP - PLATE_T - MGN15_BLOCK
    for s, sx in ((1, -1), (2, 1)):
        for k, sy in ((1, -1), (2, 1)):
            out[f"y_block_{s}{k}"] = Pos(sx * Y_RAIL_X, sy * Y_BLOCK_Y, rail_top) * Rot(0, 0, 90) * b("rail_block")
        out[f"y_rail_{s}"] = Pos(sx * Y_RAIL_X, 0, rail_top - MGN15_H / 2.0) * Rot(0, 0, 90) * b("y_rail")
        out[f"y_beam_{s}"] = Pos(sx * Y_RAIL_X, -45.0, FLOOR + 20.0) * b("y_beam")
    _screw(out, b, p, "y", (0, -1, 0), YP_Y + TRAVEL_Y + 5.0, Y_SCREW_Z - BK_H, Y_SCREW_Z)
    out["y_nut"] = Pos(0, -8.0, Y_SCREW_Z) * Rot(90, 0, 0) * b("ballnut")
    out["nut_bracket_2"] = Pos(0, 10.0, YP_TOP - PLATE_T - 15.0) * Rot(0, 0, 90) * p("nut_bracket")
    bz = Y_SCREW_Z - BK_H
    for i, n in ((1, "y_bk10"), (2, "y_bf10")):
        out[f"support_block_{i}"] = Pos(0, out[n].center().Y, (FLOOR + bz) / 2.0) * Rot(0, 0, 90) * p("support_block")
    return out


def _screw(out, b, p, ax, toward, clear, base_z, axis_z):
    """A ball screw, its BK10 (the motor end) and BF10, coupling, motor mount and motor, along one axis.

    `toward` is the unit vector from the floating end to the motor end; `clear` how far from the middle the supports
    stand (clear of the carriage plate at full travel); `base_z` where the supports stand.
    """
    u = toward
    along = lambda d: (u[0] * d, u[1] * d, 0.0)
    turn = Rot(0, 0, 90) if u[1] else Rot(0, 0, 0)                   # the supports' and brackets' x along the axis
    bk, bf = clear + 20.0, -(clear + 10.0)                             # their centres
    out[f"{ax}_bk10"] = Pos(*along(bk)) * Pos(0, 0, base_z) * turn * b("bk10")
    out[f"{ax}_bf10"] = Pos(*along(bf)) * Pos(0, 0, base_z) * turn * b("bf10")
    tip = bk + 20.0 + 1.0 + 14.5                                       # the drive journal's end, in the coupling
    main = 2.0 * clear - 1.0                                          # 1 short of BF10's inner face
    lay = Rot(0, -90, 0) if u[0] else Rot(-90, 0, 0)                    # the screw's z toward -u
    out[f"{ax}_screw"] = Pos(*along(tip)) * Pos(0, 0, axis_z) * lay * b("ballscrew", length=main)
    cc = bk + 20.0 + 1.0 + 14.5                                         # the coupling's middle at the journal's end
    out[f"{ax}_coupling"] = Pos(*along(cc)) * Pos(0, 0, axis_z) * lay * b("coupling")
    face = cc + 14.5 + (23.88 - 14.5)                                   # the motor's face: its shaft 14.5 in
    mount = face - 3.0
    m0 = base_z if ax == "x" else FLOOR
    m1 = axis_z + 21.15
    out[f"motor_mount_{1 if ax == 'x' else 2}"] = Pos(*along(mount)) * Pos(0, 0, (m0 + m1) / 2.0) * turn * p(
        "motor_mount", size_z=m1 - m0, bore_z=axis_z - (m0 + m1) / 2.0)
    out[f"{ax}_motor"] = Pos(*along(face)) * Pos(0, 0, axis_z) * lay * b("axis_motor")


def _axes():
    lift = ["platen", "heater", "clamp_plate", "carrier", "pt1000_probe", "cutout"] + [f"standoff_{i}" for i in
                                                                                        range(1, 5)]
    lift += [f"{n}_{s}" for n in ("lift_arm", "lift_block", "nut_block", "t8_nut") for s in (1, 2)]
    x = lift + ["pcb_blank", "frame_ring_lower", "frame_shim", "frame_ring_upper", "trunnion_1", "trunnion_2", "shaft_1",
                "shaft_2", "pulley_40", "pulley_20", "flip_motor",
                "motor_mount_3", "x_plate", "x_nut", "nut_bracket_1"]
    x += [f"{n}_{s}" for n in ("post", "lift_rail", "lift_coupling", "lift_screw", "lift_motor") for s in (1, 2)]
    x += [f"x_block_{s}{k}" for s in (1, 2) for k in (1, 2)]
    y = x + ["x_rail_1", "x_rail_2", "riser_1", "riser_2", "x_bk10", "x_bf10", "x_screw", "x_coupling",
             "motor_mount_1", "x_motor", "y_plate", "y_nut", "nut_bracket_2"]
    y += [f"y_block_{s}{k}" for s in (1, 2) for k in (1, 2)]
    return {"y": {"moves": tuple(y), "direction": (0, 1, 0), "travel": (-TRAVEL_Y, TRAVEL_Y), "work": (-TRAVEL_Y, TRAVEL_Y)},
            "x": {"moves": tuple(x), "direction": (1, 0, 0), "travel": (-TRAVEL_X, TRAVEL_X), "work": (-TRAVEL_X, TRAVEL_X)},
            "lift": {"moves": tuple(lift), "direction": (0, 0, 1), "travel": (-DROP, 0.0), "work": (-DROP, 0.0)}}


AXES = _axes()
POSES = {"flip": {"lift": -DROP}, "corner_far": {"x": TRAVEL_X, "y": TRAVEL_Y},
         "corner_near": {"x": -TRAVEL_X, "y": -TRAVEL_Y}}

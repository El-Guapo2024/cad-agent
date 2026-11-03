"""The PCB fab: one bench machine that drills, plates, etches, masks, marks, pastes, places and reflows a two-layer
board, as CircuitJet IV does, built on Opulo's LumenPnP (v4.2.0, its Y axis 300 mm longer).

    lumenpnp_long  the pick-and-place gantry, its head, nozzles, cameras and feeders, standing on the cabinet
    fab_stage      the one fixture: the board in a flip frame over a heated vacuum platen that drops away for the
                   flip, on an XY ball-screw stage that stitches the laser's 100 mm field over a 229 x 305 board
                   and brings each part of it under the head; under the gantry, in the middle of LumenPnP's bed
    laser_bridge   the 5 W 355 nm UV laser (JPT Lark), SG7110 galvo and Jenoptik telecentric lens on a bridge
                   over the bed that is its own 20 mm focus axis; its posts outside LumenPnP's frame
    head_tools     solder-paste and via-paste dispensers, a mask/legend jet and a laser height sensor on the head
    here           the cabinet (a 4040 base everything stands on: legs straight under the bridge's posts, cross
                   rails under the stage, so laser and board share one structure), the electronics on four plates
                   in it, the three 395 nm UV lamps on the gantry for the mask cure, the enclosure (a 2020 frame,
                   3 mm tiles, two interlocked doors, an OD 8 window) and the HEPA + carbon extractor beside it

The process, CircuitJet's order: drill (laser), via paste dotted into the holes and pulled through by the platen's
vacuum, cured on the platen (160 C), flip, again; etch (laser); mask jetted, UV-cured by the lamps, opened over the
pads and marked with the legend by the laser; flip for the second side; paste, place, reflow on the platen (240 C
cap, tin-bismuth). The camera finds the fiducials after every flip; the height sensor sets the focus.

The frame is LumenPnP's (x along its front feeder rail, its feet at z -100). The board's top is at z 37.
"""
from build123d import Pos, Rot
from cad_agent.state import build_part, bought_solid

SLUG = "pcbfab"

LC = (260.0, 365.0)                     # the optical axis: the stage's home and the lens's centre
SUBASSEMBLIES = {
    "lumenpnp_long": {"project": "lumenpnp_long", "at": [0, 0, 0], "turn": [0, 0, 0]},
    "fab_stage": {"project": "fab_stage", "at": [260.0, 365.0, 0], "turn": [0, 0, 0]},
    "laser_bridge": {"project": "laser_bridge", "at": [260.0, 365.0, 0], "turn": [0, 0, 0]},
    "head_tools": {"project": "head_tools", "at": [0, 0, 0], "turn": [0, 0, 0]},
}

# the cabinet: 4040, a top ring LumenPnP and the bridge stand on, a bottom ring with cross rails the stage stands on
CAB_TOP, FLOOR, P40 = -100.02, -253.0, 40.0   # LumenPnP's feet reach -100.011 (measured)
CAB_X, CAB_Y = (-140.0, 750.0), (-145.0, 925.0)
RING_Y = (-125.0, 905.0)                # the front and back rails' centres
TOP_Y_RAILS = (-100.0, 5.0, 595.0, 710.0)   # under the bridge posts, under LumenPnP's feet (x -10 to 20, 580 to 610)
SIDE_X = (-100.0, 710.0)                # the bottom side rails and the legs, under the bridge posts
CROSS_Y = (26.1, 82.5, 365.0, 637.5)    # under the stage's Y motor mount, its BK10 block, its middle, its BF10 block
LEG_Y = (-125.0, 365.0, 905.0)
PLATE_T = 3.0
PLATES = (((-78.0, 85.0), (-103.0, 363.0)), ((-78.0, 85.0), (367.0, 883.0)),
          ((435.0, 688.0), (-103.0, 363.0)), ((435.0, 688.0), (367.0, 883.0)))
# the enclosure: 2020 posts and rails on the cabinet's top ring, 3 mm tiles outside them
P20 = 20.0
ENC_X, ENC_Y, ENC_MID_Y = (-130.0, 305.0, 740.0), (-125.0, 905.0), 400.0
ENC_Z = (CAB_TOP + 10.0, 242.0, 575.0)  # the rails' centres: on the ring, the middle, the top (its underside 565,
                                        # over the bridge posts' tops at 560)
ENC_TOP = ENC_Z[2] + 10.0
TOP_SPLIT_Y = (222.0, 558.0)
# the UV lamps behind the X chain's tray (they move with the gantry)
UV_Y, UV_BOT = (302.0, 322.0), 57.0     # their bottoms 20 over the board (z 37), 6 over the stage's posts (51)
TRAY = (240.0, 292.0, 134.758)          # lamp_plate.py's corner: 0.01 under the tray's underside (134.768, measured)
UV_X = (-55.0, 55.0, 0.0)
EXTRACTOR = (905.0, 735.0)              # beside the cabinet on the bench, its hose to the back's fume port

GANTRY = ("lumenpnp_long/x_gantry", "lumenpnp_long/x_drag_chain_asm", "lamp_plate", "uv_lamp_1", "uv_lamp_2",
          "uv_lamp_3", "head_tools/*")  # what LumenPnP's Y moves
GANTRY_Y = 190.0                        # the head's y in Opulo's model, about
AXES = {"y": {"moves": GANTRY, "direction": (0, 1, 0), "travel": (-100.0, 240.0), "work": (-100.0, 240.0)}}
POSES = {"park": {"y": -100.0}, "under_lens": {"y": LC[1] - GANTRY_Y},
         "uv_cure": {"y": LC[1] - sum(UV_Y) / 2.0}}               # the lamps over the board

CLEARANCE = {}

CAB = [f"cab_top_x_{i}" for i in (1, 2)] + [f"cab_top_y_{i}" for i in range(1, 5)] + \
      [f"cab_bot_x_{i}" for i in (1, 2)] + [f"cab_bot_y_{i}" for i in (1, 2)] + \
      [f"cross_rail_{i}" for i in range(1, 5)] + [f"cab_leg_{i}" for i in range(1, 7)]
ELEC = ("psu_24v", "psu_48v", "psu_12v", "jetson", "motion_board", "galvo_card", "heatsink", "ssr", "rtd_amp",
        "safety_relay", "vacuum_pump", "vacuum_valve")
SKIN = ("door_1", "door_2", "window_panel", "port_panel") + tuple(f"panel_{i}" for i in range(1, 27))


def _enc_frame():
    """The enclosure frame's members: name -> (bought part, centre)."""
    m = {}
    k = 0
    for y in ENC_Y:
        for x in ENC_X:
            k += 1
            m[f"enc_post_{k}"] = ("enc_post", (x, y, (CAB_TOP + ENC_TOP) / 2.0))
    for x in (ENC_X[0], ENC_X[2]):
        k += 1
        m[f"enc_post_{k}"] = ("enc_post", (x, ENC_MID_Y, (CAB_TOP + ENC_TOP) / 2.0))
    k = 0
    for y in ENC_Y:
        for xm in ((ENC_X[0] + ENC_X[1]) / 2.0, (ENC_X[1] + ENC_X[2]) / 2.0):
            for z in ENC_Z:
                k += 1
                m[f"enc_rail_x_{k}"] = ("enc_rail_x", (xm, y, z))
    for y in TOP_SPLIT_Y:
        for xm in ((ENC_X[0] + ENC_X[1]) / 2.0, (ENC_X[1] + ENC_X[2]) / 2.0):
            k += 1
            m[f"enc_rail_x_{k}"] = ("enc_rail_x", (xm, y, ENC_Z[2]))
    k = 0
    for x in (ENC_X[0], ENC_X[2]):
        for part, y0, y1 in (("enc_rail_y1", ENC_Y[0], ENC_MID_Y), ("enc_rail_y2", ENC_MID_Y, ENC_Y[1])):
            for z in ENC_Z:
                k += 1
                m[f"enc_rail_y_{k}"] = (part, (x, (y0 + y1) / 2.0, z))
    m["enc_rail_top"] = ("enc_rail_top", (ENC_X[1], (ENC_Y[0] + ENC_Y[1]) / 2.0, ENC_Z[2]))
    return m


ENC = tuple(_enc_frame())


def _contact():
    c = set()
    c |= {f"{a}|{b}" for a in CAB for b in CAB if a < b}                    # the cabinet's joints
    c |= {f"{a}|{b}" for a in ENC for b in ENC if a < b}                    # the enclosure frame's
    c |= {f"{a}|{b}" for a in ENC for b in CAB}                             # the frame on the cabinet's top ring
    c |= {f"{a}|{b}" for a in SKIN for b in ENC + tuple(CAB)} | {f"{a}|{b}" for a in SKIN for b in SKIN if a < b}
    c |= {"laser_window|window_panel"}
    c |= {f"elec_plate_{i}|{r}" for i in range(1, 5) for r in CAB}
    c |= {f"{e}|elec_plate_{i}" for e in ELEC for i in range(1, 5)} | {"ssr|heatsink"}
    c |= {"lumenpnp_long/y_gantry_left|cab_top_y_2", "lumenpnp_long/y_gantry_right|cab_top_y_3",
          "laser_bridge/bridge_post_1|cab_top_y_1", "laser_bridge/bridge_post_2|cab_top_y_4"}
    c |= {f"laser_bridge/bridge_post_{i}|{e}" for i in (1, 2) for e in ENC}   # the side rails bolt to the posts
    c |= {f"fab_stage/y_beam_{i}|cross_rail_{k}" for i in (1, 2) for k in range(1, 5)}
    c |= {"fab_stage/support_block_1|cross_rail_2", "fab_stage/support_block_2|cross_rail_4",
          "fab_stage/motor_mount_2|cross_rail_1"}
    c |= {"uv_lamp_1|lamp_plate", "uv_lamp_2|lamp_plate",
          "uv_lamp_1|uv_lamp_2", "uv_lamp_1|uv_lamp_3", "uv_lamp_2|uv_lamp_3",
          "head_tools/tool_plate|lumenpnp_long/x_gantry"}
    return c


ALLOW_CONTACT = _contact()


def parts():
    p = lambda n, **o: build_part(SLUG, n, o or None)[0]
    b = lambda n, **o: bought_solid(SLUG, n, **o)
    out = {}
    # the cabinet
    top_z, bot_z = CAB_TOP - P40 / 2.0, FLOOR - P40 / 2.0
    xm, ym = sum(CAB_X) / 2.0, (RING_Y[0] + RING_Y[1]) / 2.0
    for i, y in enumerate(RING_Y, 1):
        out[f"cab_top_x_{i}"] = Pos(xm, y, top_z) * b("cab_rail_x")
        out[f"cab_bot_x_{i}"] = Pos(xm, y, bot_z) * b("cab_rail_x")
    for i, x in enumerate(TOP_Y_RAILS, 1):
        out[f"cab_top_y_{i}"] = Pos(x, ym, top_z) * b("cab_rail_y")
    for i, x in enumerate(SIDE_X, 1):
        out[f"cab_bot_y_{i}"] = Pos(x, ym, bot_z) * b("cab_rail_y")
    for i, y in enumerate(CROSS_Y, 1):
        out[f"cross_rail_{i}"] = Pos(sum(SIDE_X) / 2.0, y, bot_z) * b("cross_rail")
    k = 0
    for x in SIDE_X:
        for y in LEG_Y:
            k += 1
            out[f"cab_leg_{k}"] = Pos(x, y, (FLOOR + CAB_TOP - P40) / 2.0) * b("cab_leg")
    # the electronics, on four plates over the bottom rails
    pz = FLOOR + PLATE_T
    for i, ((x0, x1), (y0, y1)) in enumerate(PLATES, 1):
        out[f"elec_plate_{i}"] = Pos((x0 + x1) / 2.0, (y0 + y1) / 2.0, FLOOR + PLATE_T / 2.0) * p(
            "elec_plate", size_x=x1 - x0, size_y=y1 - y0)
    r = Rot(0, 0, 90)
    out["psu_24v"] = Pos(3.5, 15.0, pz) * r * b("psu_24v")
    out["psu_48v"] = Pos(3.5, 247.0, pz) * r * b("psu_48v")
    out["psu_12v"] = Pos(3.5, 485.0, pz) * r * b("psu_12v")
    out["jetson"] = Pos(3.5, 650.0, pz) * b("jetson")
    out["motion_board"] = Pos(3.5, 760.0, pz) * b("motion_board")
    out["galvo_card"] = Pos(610.0, 700.0, pz) * b("galvo_card")
    out["heatsink"] = Pos(623.5, 820.0, pz) * r * b("heatsink")
    out["ssr"] = Pos(623.5, 820.0, pz + 51.0) * r * b("ssr")
    out["rtd_amp"] = Pos(669.0, 795.0, pz) * b("rtd_amp")
    out["safety_relay"] = Pos(548.75, 820.0, pz) * b("safety_relay")
    out["vacuum_pump"] = Pos(600.0, -40.0, pz + 49.0) * r * b("vacuum_pump")
    out["vacuum_valve"] = Pos(650.0, 60.0, pz) * b("vacuum_valve")
    out["extractor"] = Pos(EXTRACTOR[0], EXTRACTOR[1], FLOOR - P40) * b("extractor")
    # the UV lamps, behind the X chain's tray
    out["lamp_plate"] = Pos(LC[0], TRAY[1], TRAY[2]) * p("lamp_plate")
    for i, (dx, y) in enumerate(zip(UV_X, (UV_Y[0], UV_Y[0], UV_Y[1])), 1):
        out[f"uv_lamp_{i}"] = Pos(LC[0] + dx, y, UV_BOT + 59.0) * b("uv_lamp")
    # the enclosure's frame and skin
    for n, (part, c) in _enc_frame().items():
        out[n] = Pos(*c) * b(part)
    xs = ((CAB_X[0], ENC_X[1]), (ENC_X[1], CAB_X[1]))
    zs = ((CAB_TOP, ENC_Z[1]), (ENC_Z[1], ENC_TOP))
    y_front, y_back = ENC_Y[0] - P20 / 2.0 - 1.5, ENC_Y[1] + P20 / 2.0 + 1.5
    x_left, x_right = ENC_X[0] - P20 / 2.0 - 1.5, ENC_X[2] + P20 / 2.0 + 1.5
    face_y = Rot(90, 0, 0)                                         # a tile's a along x, b along z
    face_x = Rot(0, 0, 90) * Rot(90, 0, 0)                         # a along y, b along z
    k = 0

    def tile(name, part, a, bb, at, turn):
        out[name] = Pos(*at) * turn * p(part, size_a=a[1] - a[0], size_b=bb[1] - bb[0])

    for xi, (x0, x1) in enumerate(xs):
        for zi, (z0, z1) in enumerate(zs):
            front = ("door_1", "door") if (xi, zi) == (0, 0) else ("door_2", "door") if (xi, zi) == (1, 0) else \
                ("window_panel", "window_panel") if (xi, zi) == (0, 1) else None
            if front is None:
                k += 1
                front = (f"panel_{k}", "panel")
            tile(front[0], front[1], (x0, x1), (z0, z1), ((x0 + x1) / 2.0, y_front, (z0 + z1) / 2.0), face_y)
            back = ("port_panel", "port_panel") if (xi, zi) == (1, 0) else None
            if back is None:
                k += 1
                back = (f"panel_{k}", "panel")
            tile(back[0], back[1], (x0, x1), (z0, z1), ((x0 + x1) / 2.0, y_back, (z0 + z1) / 2.0), face_y)
    for y0, y1 in ((CAB_Y[0] + 10.0, ENC_MID_Y), (ENC_MID_Y, CAB_Y[1] - 10.0)):
        for z0, z1 in zs:
            for x in (x_left, x_right):
                k += 1
                tile(f"panel_{k}", "panel", (y0, y1), (z0, z1), (x, (y0 + y1) / 2.0, (z0 + z1) / 2.0), face_x)
    ty = ((CAB_Y[0] + 10.0, TOP_SPLIT_Y[0]), TOP_SPLIT_Y, (TOP_SPLIT_Y[1], CAB_Y[1] - 10.0))
    for x0, x1 in xs:
        for y0, y1 in ty:
            k += 1
            tile(f"panel_{k}", "panel", (x0, x1), (y0, y1), ((x0 + x1) / 2.0, (y0 + y1) / 2.0, ENC_TOP + 1.5),
                 Rot(0, 0, 0))
    # the cabinet's skin: the same tiles round the base, under the enclosure's (the bench to the top ring)
    cz = (FLOOR - P40, CAB_TOP)
    cab_xs, cab_ys = xs, ((CAB_Y[0], ENC_MID_Y), (ENC_MID_Y, CAB_Y[1]))
    for x0, x1 in cab_xs:
        for y in (CAB_Y[0] - 1.5, CAB_Y[1] + 1.5):
            k += 1
            tile(f"panel_{k}", "panel", (x0, x1), cz, ((x0 + x1) / 2.0, y, sum(cz) / 2.0), face_y)
    for y0, y1 in cab_ys:
        for x in (CAB_X[0] - 1.5, CAB_X[1] + 1.5):
            k += 1
            tile(f"panel_{k}", "panel", (y0, y1), cz, (x, (y0 + y1) / 2.0, sum(cz) / 2.0), face_x)
    wp = out["window_panel"].bounding_box()
    out["laser_window"] = Pos((wp.min.X + wp.max.X) / 2.0 - 40.0, ENC_Y[0] - P20 / 2.0 + 2.5,
                              (wp.min.Z + wp.max.Z) / 2.0) * p("laser_window")
    return out

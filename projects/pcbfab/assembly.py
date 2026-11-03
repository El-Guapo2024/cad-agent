"""The board machine: it drills, fills the vias, etches, masks, finishes, marks and pastes a two-layer board, as
CircuitJet IV does; a stock pick-and-place (LumenPnP or a desktop one, its own machine) places the parts after, and a
bought hot plate cures the via paste and reflows (Juan, 2026-11-03: two machines, the hot plate bought).

    fab_stage      the one fixture: the board in a flip frame over a vacuum platen that drops away for the flip, on an
                   XY ball-screw stage that stitches the laser's 100 mm field over a 229 x 305 board and carries it
                   under the tools in front of the lens
    laser_bridge   the 5 W 355 nm UV laser (JPT Lark), SG7110 galvo and Jenoptik telecentric lens on a bridge that
                   is its own 20 mm focus axis
    here           the tool bridge (_tools below): a 4040 beam in front of the lens on two posts, an MGN12 rail and an
                   SFU1204 screw under it, and the carriage: two paste dispensers (via paste and solder paste), a mask
                   jet, a gold finish / legend jet, each on its own air slide, the height sensor, the fiducial camera
                   (the board comes back from the hot plate) and the three 395 nm UV lamps for the mask cure. Then the
                   cabinet (a 4040 base everything stands on: legs under both bridges' posts, cross rails under the
                   stage), the electronics on four plates in it, the enclosure (a 2020 frame, 3 mm tiles, two
                   interlocked doors, an OD 8 window) and the HEPA + carbon extractor beside it

The process, CircuitJet's order: drill (laser); via paste dotted into the holes and pulled through by the platen's
vacuum; out to the hot plate (160 C), back, found by its fiducials; flip, again; etch (laser); mask jetted, UV-cured
under the lamps, opened over the pads and marked with the legend by the laser; the finish jetted on the pads; flip for
the second side; solder paste dotted on the pads. Then to the pick-and-place, and back to the hot plate to reflow.

The frame: x, y from the lens's optical axis, z the board's (its top at 37). The stage's middle is 117 in front.
"""
import math

from build123d import Pos, Rot
from cad_agent.state import build_part, bought_solid

SLUG = "pcbfab"

STAGE_Y = -117.0                        # the stage's middle: its y = +117 puts the board under the lens
B_TOP = 37.0                            # the board's top (fab_stage)
SUBASSEMBLIES = {
    "fab_stage": {"project": "fab_stage", "at": [0.0, -117.0, 0], "turn": [0, 0, 0]},
    "laser_bridge": {"project": "laser_bridge", "at": [0.0, 0.0, 0], "turn": [0, 0, 0]},
}

# the cabinet: 4040, a top ring the bridges stand on, a bottom ring with cross rails the stage stands on
CAB_TOP, FLOOR, P40 = -100.02, -253.0, 40.0   # the laser bridge's posts stand at -100.02
CAB_X, CAB_Y = (-400.0, 490.0), (-685.0, 405.0)
RING_Y = (-665.0, 385.0)                # the front and back rails' centres
SIDE_X = (-360.0, 450.0)                # the side rails, top and bottom, and the legs: under both bridges' posts
CROSS_Y = tuple(STAGE_Y + d for d in (-466.38, -410.0, 0.0, 400.0))   # under the stage's Y motor mount, its BK10,
                                        # its middle, its BF10 (fab_stage: the screw's supports 390 out)
LEG_Y = (-665.0, -140.0, 385.0)
PLATE_T = 3.0
PLATES = (((-338.0, -175.0), (-640.0, -121.0)), ((-338.0, -175.0), (-113.0, 360.0)),
          ((175.0, 428.0), (-640.0, -121.0)), ((175.0, 428.0), (-113.0, 360.0)))
# the enclosure: 2020 posts and rails on the cabinet's top ring, 3 mm tiles outside them
P20 = 20.0
ENC_X, ENC_Y, ENC_MID_Y = (-390.0, 45.0, 480.0), (-665.0, 385.0), -140.0
ENC_Z = (CAB_TOP + 10.0, 242.0, 575.0)  # the rails' centres: on the ring, the middle, the top (its underside 565,
                                        # over the laser bridge's posts' tops at 560)
ENC_TOP = ENC_Z[2] + 10.0
TOP_SPLIT_Y = (-315.0, 35.0)
EXTRACTOR = (645.0, 150.0)              # beside the cabinet on the bench, its hose to the back's fume port

# the tool bridge, in front of the lens: clear of the beam's swept cone (the keepout in spec.toml)
TB_Y, TB_Z = -95.0, 180.0               # the beam's centre line
TB_BOT = TB_Z - P40 / 2.0               # 160: the screw's supports hang from here
TB_POST_X = SIDE_X                      # on the top side rails, in front of the laser bridge's posts
RAIL_H, BLOCK_H = 8.0, 13.0             # MGN12: rail height, H (the rail's base to the block's top)
PLATE_BACK = TB_Y - P40 / 2.0 - BLOCK_H     # -128: the tool plate's back face, on the blocks
TOOL_PLATE_X, TOOL_PLATE_Z = (-190.0, 145.0), (60.0, 200.0)   # from the carriage's middle (its x = the axis's)
BLOCK_X = (-130.0, 80.0)
TOOL_X = (-170.0, 165.0)                # the carriage's travel: each tool, the camera and the lamps reach the whole
                                        # board with the stage's own +-65 in x
SCREW_X, SCREW_CLEAR = 7.0, 190.0       # the screw's middle and its supports' inner faces' distance from it
NUT_X = -8.0                            # the nut's flange face from the carriage's middle (as fab_stage's X nut)

# the process tools on the carriage, x from its middle (what CircuitJet IV's print heads do, as dispensers)
TOOL_LIFT = 16.0                         # each slide's working stroke: raised, the tips clear the stage's posts (51)
SLIDE_H, SLIDE_Z = 23.0, 110.0           # slide.py: the body's depth; the slides' middles
PEN_X, PEN_TILT, NEEDLE = (30.5, 70.5), 35.0, 25.4   # the clamps 40 wide; 35 degrees forward; a 1 in Luer needle
JET_X, JET_GAP = (-12.5, -38.5), 1.5     # the mask jet; the finish / legend jet
SENSOR_X, SENSOR_RANGE = -67.5, 30.0
CAMERA_X, CAMERA_BOT = 120.0, 57.0       # the fiducial camera, looking down; its lens 20 over the board
UV_X, UV_BOT = (-170.0, -147.5, -125.0), 57.0   # the lamps, long along y, side by side: their bottoms 20 over the board
TOOLS = ("eco_pen_1", "eco_pen_2", "pico_jet_1", "pico_jet_2")
CARRIAGE = ("tool_plate", "height_sensor", "camera", "uv_lamp_1", "uv_lamp_2", "uv_lamp_3", "tool_block_1",
            "tool_block_2", "tool_nut", "nut_bracket") + tuple(f"slide_{i}" for i in range(1, 5)) + (
            "eco_pen_1", "eco_pen_2", "pen_clamp_1", "pen_clamp_2", "pico_jet_1", "pico_jet_2")
TOOL_CONTACT = {"height_sensor|tool_plate", "camera|tool_plate", "eco_pen_1|pen_clamp_1", "eco_pen_2|pen_clamp_2",
                "pen_clamp_1|slide_1", "pen_clamp_2|slide_2", "pico_jet_1|slide_3", "pico_jet_2|slide_4",
                "uv_lamp_1|tool_plate", "uv_lamp_2|tool_plate", "uv_lamp_3|tool_plate"} | {
    f"slide_{i}|tool_plate" for i in range(1, 5)}
TB_CONTACT = {"tool_post_1|tool_beam", "tool_post_2|tool_beam", "tool_rail|tool_beam", "tool_block_1|tool_rail",
              "tool_block_2|tool_rail", "tool_block_1|tool_plate", "tool_block_2|tool_plate",
              "tool_bk10|tool_beam", "tool_bf10|tool_beam", "tool_screw|tool_bk10", "tool_screw|tool_bf10",
              "tool_nut|tool_screw", "tool_nut|nut_bracket", "nut_bracket|tool_plate",
              "tool_coupling|tool_screw", "tool_coupling|tool_motor", "tool_motor|motor_mount",
              "motor_mount|tool_beam"}

AXES = {"tool_x": {"moves": CARRIAGE, "direction": (1, 0, 0), "travel": TOOL_X, "work": TOOL_X}}
AXES.update({f"{t}_z": {"moves": (t,) + ((f"pen_clamp_{t[-1]}",) if t.startswith("eco") else ()),
                        "direction": (0, 0, 1), "travel": (-TOOL_LIFT, 0.0), "work": (-TOOL_LIFT, 0.0)}
             for t in TOOLS})
UV_Y = PLATE_BACK - 6.0 - 55.0          # the lamps' middle: 110 long in front of the plate
POSES = {"under_lens": {"fab_stage/y": -STAGE_Y},
         "uv_cure": {"fab_stage/y": UV_Y - STAGE_Y, "tool_x": -UV_X[1]},   # the middle lamp over the board's middle
         "flip": {"fab_stage/y": 230.0, "fab_stage/lift": -135.0}}
POSES.update({f"{t}_down": {f"{t}_z": -TOOL_LIFT} for t in TOOLS})

CLEARANCE = {}

CAB = [f"cab_top_x_{i}" for i in (1, 2)] + [f"cab_top_y_{i}" for i in (1, 2)] + \
      [f"cab_bot_x_{i}" for i in (1, 2)] + [f"cab_bot_y_{i}" for i in (1, 2)] + \
      [f"cross_rail_{i}" for i in range(1, 5)] + [f"cab_leg_{i}" for i in range(1, 7)]
ELEC = ("psu_24v", "psu_48v", "psu_12v", "jetson", "motion_board", "galvo_card", "safety_relay", "vacuum_pump",
        "vacuum_valve")
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
    c |= {f"{e}|elec_plate_{i}" for e in ELEC for i in range(1, 5)}
    c |= {"laser_bridge/bridge_post_1|cab_top_y_1", "laser_bridge/bridge_post_2|cab_top_y_2",
          "tool_post_1|cab_top_y_1", "tool_post_2|cab_top_y_2"}
    c |= {f"laser_bridge/bridge_post_{i}|{e}" for i in (1, 2) for e in ENC}   # the side rails bolt to the posts
    c |= {f"fab_stage/y_beam_{i}|cross_rail_{k}" for i in (1, 2) for k in range(1, 5)}
    c |= {"fab_stage/support_block_1|cross_rail_2", "fab_stage/support_block_2|cross_rail_4",
          "fab_stage/motor_mount_2|cross_rail_1"}
    c |= {"uv_lamp_1|uv_lamp_2", "uv_lamp_2|uv_lamp_3"} | TOOL_CONTACT | TB_CONTACT
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
    for i, x in enumerate(SIDE_X, 1):
        out[f"cab_top_y_{i}"] = Pos(x, ym, top_z) * b("cab_rail_y")
        out[f"cab_bot_y_{i}"] = Pos(x, ym, bot_z) * b("cab_rail_y")
    for i, y in enumerate(CROSS_Y, 1):
        out[f"cross_rail_{i}"] = Pos(sum(SIDE_X) / 2.0, y, bot_z) * b("cross_rail")
    k = 0
    for x in SIDE_X:
        for y in LEG_Y:
            k += 1
            out[f"cab_leg_{k}"] = Pos(x, y, (FLOOR + CAB_TOP - P40) / 2.0) * b("cab_leg")
    # the electronics, on four plates on the cross rails
    pz = FLOOR + PLATE_T
    for i, ((x0, x1), (y0, y1)) in enumerate(PLATES, 1):
        out[f"elec_plate_{i}"] = Pos((x0 + x1) / 2.0, (y0 + y1) / 2.0, FLOOR + PLATE_T / 2.0) * p(
            "elec_plate", size_x=x1 - x0, size_y=y1 - y0)
    r = Rot(0, 0, 90)
    out["psu_24v"] = Pos(-256.5, -522.0, pz) * r * b("psu_24v")
    out["psu_48v"] = Pos(-256.5, -290.0, pz) * r * b("psu_48v")
    out["psu_12v"] = Pos(-256.5, 5.0, pz) * r * b("psu_12v")
    out["jetson"] = Pos(-256.5, 170.0, pz) * b("jetson")
    out["motion_board"] = Pos(-256.5, 280.0, pz) * b("motion_board")
    out["galvo_card"] = Pos(350.0, 220.0, pz) * b("galvo_card")
    out["safety_relay"] = Pos(288.75, -300.0, pz) * b("safety_relay")
    out["vacuum_pump"] = Pos(340.0, -577.0, pz + 49.0) * r * b("vacuum_pump")
    out["vacuum_valve"] = Pos(390.0, -477.0, pz) * b("vacuum_valve")
    out["extractor"] = Pos(EXTRACTOR[0], EXTRACTOR[1], FLOOR - P40) * b("extractor")
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
    _bridge(out, p, b)
    _tools(out, p, b)
    wp = out["window_panel"].bounding_box()
    out["laser_window"] = Pos((wp.min.X + wp.max.X) / 2.0 - 40.0, ENC_Y[0] - P20 / 2.0 + 2.5,
                              (wp.min.Z + wp.max.Z) / 2.0) * p("laser_window")
    return out


def _seat(solid, x=None, y=None, z=None, **faces):
    """Move a solid so its bounding box's centre or named faces land where given (x_min=..., y_max=... and so on)."""
    bb = solid.bounding_box()
    d = [0.0, 0.0, 0.0]
    for i, (axis, c) in enumerate((("X", x), ("Y", y), ("Z", z))):
        lo, hi = getattr(bb.min, axis), getattr(bb.max, axis)
        if c is not None:
            d[i] = c - (lo + hi) / 2.0
        for side, v in faces.items():
            if side == f"{axis.lower()}_min":
                d[i] = v - lo
            elif side == f"{axis.lower()}_max":
                d[i] = v - hi
    return Pos(*d) * solid


def _bridge(out, p, b):
    """The tool bridge: two 4040 posts on the top side rails, the beam between them, an MGN12 rail on its front face
    and an SFU1204 screw hung under it (BK10 at the motor end, +x), as fab_stage's X screw upside down."""
    x0, x1 = TB_POST_X[0] + P40 / 2.0, TB_POST_X[1] - P40 / 2.0        # the posts' inner faces
    for i, x in enumerate(TB_POST_X, 1):
        out[f"tool_post_{i}"] = _seat(b("tool_post"), x=x, y=TB_Y, z_min=CAB_TOP)
    out["tool_beam"] = Pos((x0 + x1) / 2.0, TB_Y, TB_Z) * b("tool_beam")
    rail = Rot(90, 0, 0) * b("tool_rail")                                 # along x, its height toward -y
    out["tool_rail"] = _seat(rail, x=(BLOCK_X[0] + BLOCK_X[1]) / 2.0 + sum(TOOL_X) / 2.0, z=TB_Z,
                             y_max=TB_Y - P40 / 2.0)
    # the screw, in a frame upright on the beam's underside (its base z = 0, its axis y = 0, z = 22, x from SCREW_X),
    # turned over onto it
    hang = Pos(SCREW_X, TB_Y, TB_BOT) * Rot(180, 0, 0)
    up = {}
    clear, h = SCREW_CLEAR, 22.0
    up["tool_bk10"] = Pos(clear + 20.0, 0, 0) * b("bk10")
    up["tool_bf10"] = Pos(-(clear + 10.0), 0, 0) * b("bf10")
    lay = Rot(0, -90, 0)                                                 # the screw's z toward -x
    tip = clear + 40.0 + 1.0 + 14.5                                      # the drive journal's end, in the coupling
    up["tool_screw"] = Pos(tip, 0, h) * lay * b("ballscrew", length=2.0 * clear - 1.0)
    up["tool_coupling"] = Pos(tip, 0, h) * lay * b("coupling")
    face = tip + 14.5 + (23.88 - 14.5)                                   # the motor's face: its shaft 14.5 in
    m1 = h + 21.15
    up["motor_mount"] = Pos(face - 3.0, 0, m1 / 2.0) * p("motor_mount", size_z=m1, bore_z=h - m1 / 2.0)
    up["tool_motor"] = Pos(face, 0, h) * lay * b("tool_motor")
    for n, s in up.items():
        out[n] = hang * s


def _tools(out, p, b):
    """The tool carriage: what CircuitJet IV's print heads do, as dispensers, and what the board needs found again.

    eco_pen_1    solder paste (ViscoTec eco-PEN300, volumetric, 1 ul): no stencil, as CircuitJet's syringe
    eco_pen_2    via paste (silver), dotted onto each drilled hole while the platen's vacuum pulls it through
    pico_jet_1   UV solder mask (Agfa DiPaMAT SM G01 cures at 395 nm), jetted as dots, then cured by the lamps; the
                 laser opens the pads after
    pico_jet_2   the gold finish over the opened pads, as CircuitJet's ENIG ink: PV Nano Cell's gold ink for inkjet
                 and aerosol printing (Sicrys IAu20W, water based; pvnanocell.com, 2020 launch), cured on the hot
                 plate if its profile fits, else the UV laser sinters it pad by pad; or white legend ink (Agfa
                 DiPaMat Wh04, 395 nm) when the laser does not mark the legend
    height_sensor  board height and flatness for the laser's focus (Panasonic HG-C1030, 30 mm, 10 um), fixed
    camera       the fiducials, each time the board comes back from the hot plate and after each flip
    uv_lamp_1-3  the mask cure (LedWV 395 nm), side by side, long along y

Each dispenser and jet rides its own SMC MXH10 air slide (16 of its 20 mm): only the working tool comes down, so its
neighbours stay clear of the flip frame's edge bars and the stage's posts wherever it works. The slides, the sensor,
the camera and the lamps are on the carriage plate's front; the plate rides the tool bridge's rail (_bridge).
Raised (the model's state): the tips 16 over their work, clear of the stage's posts.
    """
    pl = p("tool_plate", size_x=TOOL_PLATE_X[1] - TOOL_PLATE_X[0])
    out["tool_plate"] = Pos(sum(TOOL_PLATE_X) / 2.0, PLATE_BACK - 3.0, sum(TOOL_PLATE_Z) / 2.0) * pl
    blk = Rot(90, 0, 0) * b("tool_block")
    for i, x in enumerate(BLOCK_X, 1):
        out[f"tool_block_{i}"] = _seat(blk, x=x, z=TB_Z, y_min=PLATE_BACK)
    # the nut on the screw and its bracket to the plate's back (fab_stage's X nut, upside down with the screw)
    hang = Pos(0, TB_Y, TB_BOT) * Rot(180, 0, 0)
    out["tool_nut"] = hang * Pos(NUT_X, 0, 22.0) * Rot(0, -90, 0) * Rot(0, 0, 90) * b("ballnut")
    reach = TB_Y - PLATE_BACK                                            # 33: the axis to the plate's back
    y0, y1 = -25.0, reach                                                # in the upright frame (y turned over)
    out["nut_bracket"] = hang * Pos(10.0, (y0 + y1) / 2.0, 22.0) * p(
        "nut_bracket", size_y=y1 - y0, bore_y=-(y0 + y1) / 2.0)
    front = PLATE_BACK - 6.0                                             # the plate's front, the slides' backs
    table = front - SLIDE_H                                              # the slides' tables, the tools' backs
    for i, x in enumerate(PEN_X + JET_X, 1):
        out[f"slide_{i}"] = Pos(x, front, SLIDE_Z) * b("slide")
    c, s_ = math.cos(math.radians(PEN_TILT)), math.sin(math.radians(PEN_TILT))
    pen_bot = B_TOP + 0.2 + NEEDLE * c + TOOL_LIFT
    yc = table - 40.0                                                    # the clamp: 80 deep from the slide's table
    pen_y = yc + 26.0                                                    # the pen's bottom centre: its back 1 off the table
    for i, x in enumerate(PEN_X, 1):
        out[f"eco_pen_{i}"] = Pos(x, pen_y, pen_bot) * Rot(PEN_TILT, 0, 0) * b("eco_pen")
        t = 40.0                                                         # the clamp's middle, up the pen's axis
        cy, cz = pen_y - t * s_, pen_bot + t * c
        out[f"pen_clamp_{i}"] = Pos(x, yc, cz) * p("pen_clamp", bore_y=cy - yc)
    for i, x in enumerate(JET_X, 1):
        out[f"pico_jet_{i}"] = Pos(x, table, B_TOP + JET_GAP + TOOL_LIFT) * b("pico_jet")
    out["height_sensor"] = Pos(SENSOR_X, front - 12.5, B_TOP + SENSOR_RANGE) * b("height_sensor")
    out["camera"] = _seat(b("camera"), x=CAMERA_X, y_max=front, z_min=CAMERA_BOT)
    lamp = Rot(0, 0, 90) * b("uv_lamp")
    for i, x in enumerate(UV_X, 1):
        out[f"uv_lamp_{i}"] = _seat(lamp, x=x, y_max=front, z_min=UV_BOT)

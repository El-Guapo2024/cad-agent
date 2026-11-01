"""The PCB fab: one machine. LumenPnP v4.2.0 with its Y axis 300 mm longer, a laser zone behind its PnP area.

    pnp zone     the hot plate on four standoffs over a deck on four 2020 legs from the table, between the feeder
                 rails under the head: solder paste, via silver, pick-and-place, then reflow / cure in place.
    laser zone   behind it, in the length the stretch added: the vacuum bed (pinned like the hot plate, a plenum
                 under a hole grid for the via paste) on a deck on four legs; the UV
                 laser (JPT Lark 355 nm, as CircuitJet IV and LPKF's ProtoLaser U4 use UV) and the SG7110 galvo hang
                 in line from a plate under a bridge of two 4040s on two 4040 posts outside the frame, Jenoptik's telecentric 355 nm F170 lens down (straight vias across the field),
                 its focus on the board top. Drill, etch, fill vias, open the solder mask
                 over the pads and mark the legend.
    uv lamp      a 395 nm LED lamp beside the head: the gantry sweeps it over the board on the vacuum bed to cure
                 the solder mask (coated by hand, as the flip is).
    enclosure    a 2020 frame round the whole machine, 3 mm aluminium panels, a door with a 1064 nm ALS-YAG window
                 (OD 8 at 355 nm; interlocked: it cuts the laser and the lamps in hardware), the fume port in the back.
The gantry passes between the two: the laser board's top is set so the lens clears the gantry's top (z 240.4 in
Opulo's model) and the pins clear the head's lowest point (z ~90), so the head can carry the board from the laser
bed to the hot plate. The flip stays by hand, onto the same two 3 mm pins.
LumenPnP is the `lumenpnp_long` project at its own origin (x along the front feeder rail, the table at z -101).

The laser stack, bottom up: the board top (LASER_TOP); the lens's 315.8 flange-to-focus (Jenoptik JENar
170-355-140, its input end screwed up into the galvo); the SG7110 93.6; the spacer; the laser plate, the UV source hanging from it beside the galvo; the
bridge beam on top.
"""
from build123d import Pos, Rot
from cad_agent.state import build_part, bought_solid

SLUG = "pcbfab"

SUBASSEMBLIES = {"lumenpnp_long": {"project": "lumenpnp_long", "at": [0, 0, 0], "turn": [0, 0, 0]}}

TABLE = -101.0                          # LumenPnP's feet
BOARD_T, PLATE_T, STANDOFF_H, DECK_T = 1.6, 9.525, 25.0, 6.0
VBED_H = PLATE_T + STANDOFF_H            # vacuum_bed.py: in place of the plate and standoffs, its top where the plate's was
MOUNT = (68.0, 68.0)                    # the plate's standoff holes, from its centre (hot_plate.py: 150 square, inset 7)
PIN_X, PIN_L = 58.0, 12.5               # half the pin pitch; reg_pin.py: through the plate, 3 proud
# pnp zone
HC = (230.0, 110.0)                     # the hot plate's centre: clear of the staging plate, feeders and nozzle rack
HP_TOP = 35.925                         # 1.5 over LumenPnP's staging plate top (z 34.4); legs 96.4
HP_LEG = (80.0, 75.0)
# laser zone
LC = (230.0, 560.0)                     # the laser bed's centre: left of mid-frame so the UV source, in line with the
                                        # galvo, ends clear of the right bridge post; in the added length in y
LASER_TOP = 80.0                        # the board top: pins at 81.4 under the head's ~90, lens at 315.8 over 240.4
GALVO_H = 93.6                          # SG7110 (UV mirrors)
LENS_WD, LENS_FF = 235.8, 315.8         # Jenoptik JENar 170-355-140: back working distance, flange to focus (data sheet)
LENS_OUT = 129.1                        # its STEP's output face, z in the file (input end at 22.51, 106.6 long)
LENS_SHIFT = 118.5 / 2.0 - 45.0         # the lens under the galvo's output end, not its middle
SOURCE = (348.5, 126.2)                 # JPT Lark-355-5A: length, height (beam axis at mid-height)
SPACER_T = SOURCE[1] / 2.0 - GALVO_H / 2.0                      # galvo_spacer.py: the galvo's input on the beam axis
LPLATE_T = 10.0                         # laser_plate.py
LASER_LEG = (105.0, 135.0)
LBED_TOP = LASER_TOP - BOARD_T
LDECK_TOP = LBED_TOP - PLATE_T - STANDOFF_H                     # 43.875; legs 138.875
GALVO_TOP = LASER_TOP + LENS_FF + GALVO_H                        # 489.4: the lens's flange on the galvo's underside
LPLATE_BOT = GALVO_TOP + SPACER_T                                # the source and the spacer hang from here
BEAM_BOT = LPLATE_BOT + LPLATE_T                                 # 515.7: the 4040 bridge beams' underside
BRIDGE_X = (-100.0, 680.0)              # the 4040 posts: 15 clear of the gantry's left end (x -65), 18 of its right (x 642)

UV_Y, UV_BOT = (302.0, 322.0), 95.0     # the UV lamps' two rows behind the X chain; their bottoms 15 over the board
TRAY = (240.0, 292.0, 134.768)          # lamp_plate.py's corner: the tray's underside (z 134.768, measured), the web behind the links (y 286)
UV_X = (-55.0, 55.0, 0.0)               # from LC: two in the front row, one behind between them, so the 72 mm beams overlap
PUMP = (470.0, 560.0)                   # the vacuum pump on the table, beside the laser deck's legs
# the enclosure: 2020 post centres, the frame from the table to ENC_TOP
ENC_X, ENC_Y, ENC_TOP = (-140.0, 720.0), (-140.0, 925.0), 575.0
DOOR_Z = 25.0                           # front_panel.py open_z; door.py win_z 20

GANTRY = ("lumenpnp_long/x_gantry", "lumenpnp_long/x_drag_chain_asm", "lamp_plate", "uv_lamp_1", "uv_lamp_2",
          "uv_lamp_3")                  # what Y moves
GANTRY_Y = 190.0                        # the head's y in Opulo's model, about
AXES = {"y": {"moves": GANTRY, "direction": (0, 1, 0), "travel": (-100.0, LC[1] - GANTRY_Y + 40.0)}}
POSES = {"pick_laser": {"y": LC[1] - GANTRY_Y}, "place_hot": {"y": HC[1] - GANTRY_Y},
         "uv_cure": {"y": LC[1] - sum(UV_Y) / 2.0}}               # the lamps over the laser board

CLEARANCE = {}


def _contact():
    c = {"galvo|galvo_spacer", "galvo_spacer|laser_plate", "uv_source|laser_plate", "laser_plate|bridge_beam_1",
         "laser_plate|bridge_beam_2", "bridge_beam_1|bridge_beam_2", "bridge_post_1|bridge_beam_1",
         "bridge_post_1|bridge_beam_2", "bridge_post_2|bridge_beam_1", "bridge_post_2|bridge_beam_2",
         "ftheta_lens|galvo", "lamp_plate|lumenpnp_long/x_drag_chain_asm", "uv_lamp_1|lamp_plate",
         "uv_lamp_2|lamp_plate", "uv_lamp_1|uv_lamp_2", "uv_lamp_1|uv_lamp_3", "uv_lamp_2|uv_lamp_3", 
         "pcb_blank|vacuum_bed", "reg_pin_1|vacuum_bed", "reg_pin_2|vacuum_bed", "vacuum_bed|laser_deck",
         "reg_pin_3|hot_plate", "reg_pin_4|hot_plate", "door|front_panel", "laser_window|door"}
    for i in range(1, 5):
        c |= {f"laser_leg_{i}|laser_deck", f"standoff_{i}|hp_deck", f"standoff_{i}|hot_plate", f"leg_{i}|hp_deck"}
    frame = {f"encl_post_{i}" for i in range(1, 5)} | {f"encl_rail_{a}{i}" for a in "xy" for i in range(1, 5)}
    c |= {f"{a}|{b}" for a in frame for b in frame if a < b}         # the frame's joints
    skin = {"front_panel", "back_panel", "side_panel_1", "side_panel_2", "top_panel"}
    c |= {f"{a}|{b}" for a in skin for b in frame}                   # panels screwed to the frame's outer faces
    c |= {f"{a}|{b}" for a in skin for b in skin if a < b}           # panels meet at the edges
    return c


ALLOW_CONTACT = _contact()

CORNERS = ((-1, -1), (1, -1), (-1, 1), (1, 1))


def parts():
    p = lambda n: build_part(SLUG, n)[0]
    b = lambda n: bought_solid(SLUG, n)
    out = {}
    # laser zone: the vacuum bed
    out["laser_deck"] = Pos(LC[0], LC[1], LDECK_TOP - DECK_T / 2.0) * p("laser_deck")
    for i, (sx, sy) in enumerate(CORNERS, 1):
        out[f"laser_leg_{i}"] = Pos(LC[0] + sx * LASER_LEG[0], LC[1] + sy * LASER_LEG[1],
                                    (TABLE + LDECK_TOP - DECK_T) / 2.0) * b("laser_leg")
    out["vacuum_bed"] = Pos(LC[0], LC[1], LDECK_TOP + VBED_H / 2.0) * p("vacuum_bed")
    for i, sx in ((1, -1), (2, 1)):
        out[f"reg_pin_{i}"] = Pos(LC[0] + sx * PIN_X, LC[1], LBED_TOP - PLATE_T + PIN_L / 2.0) * p("reg_pin")
    out["vacuum_pump"] = Pos(PUMP[0], PUMP[1], TABLE + 49.0) * Rot(0, 0, 90) * b("vacuum_pump")
    out["pcb_blank"] = Pos(LC[0], LC[1], LASER_TOP - BOARD_T / 2.0) * p("pcb_blank")
    # laser zone: the bridge, the plate, the UV source in line with the galvo, and the lens
    for i, x in enumerate(BRIDGE_X, 1):
        out[f"bridge_post_{i}"] = Pos(x, LC[1], (TABLE + BEAM_BOT) / 2.0) * b("bridge_post")
    for i, dy in ((1, -20.0), (2, 20.0)):              # two 4040s side by side: one sagged 175 um under the laser
        out[f"bridge_beam_{i}"] = Pos(sum(BRIDGE_X) / 2.0, LC[1] + dy, BEAM_BOT + 20.0) * b("bridge_beam")
    gx = LC[0] + LENS_SHIFT
    g0, s1 = gx - 118.5 / 2.0, gx + 118.5 / 2.0 + 2.0 + SOURCE[0]     # the plate's ends: the galvo's left, the source's right
    out["laser_plate"] = Pos((g0 + s1) / 2.0, LC[1], LPLATE_BOT + LPLATE_T / 2.0) * p("laser_plate")
    out["galvo_spacer"] = Pos(gx, LC[1], GALVO_TOP + SPACER_T / 2.0) * p("galvo_spacer")
    out["uv_source"] = Pos(s1 - SOURCE[0] / 2.0, LC[1], LPLATE_BOT - SOURCE[1] / 2.0) * b("uv_source")
    out["galvo"] = Pos(gx, LC[1], GALVO_TOP - GALVO_H / 2.0) * b("galvo")
    flange = LENS_OUT - (LENS_FF - LENS_WD)                      # the flange's z in the STEP: 49.1
    out["ftheta_lens"] = Pos(LC[0], LC[1], GALVO_TOP - GALVO_H + flange) * Rot(180, 0, 0) * b("ftheta_lens")
    # pnp zone: the hot plate
    out["hp_deck"] = Pos(HC[0], HC[1], HP_TOP - PLATE_T - STANDOFF_H - DECK_T / 2.0) * p("hp_deck")
    for i, (sx, sy) in enumerate(CORNERS, 1):
        out[f"leg_{i}"] = Pos(HC[0] + sx * HP_LEG[0], HC[1] + sy * HP_LEG[1],
                              (TABLE + HP_TOP - PLATE_T - STANDOFF_H - DECK_T) / 2.0) * b("leg")
        out[f"standoff_{i}"] = Pos(HC[0] + sx * MOUNT[0], HC[1] + sy * MOUNT[1],
                                       HP_TOP - PLATE_T - STANDOFF_H / 2.0) * p("standoff")
    out["hot_plate"] = Pos(HC[0], HC[1], HP_TOP - PLATE_T / 2.0) * p("hot_plate")
    for i, sx in ((3, -1), (4, 1)):
        out[f"reg_pin_{i}"] = Pos(HC[0] + sx * PIN_X, HC[1], HP_TOP - PLATE_T + PIN_L / 2.0) * p("reg_pin")
    # the uv lamps, behind the X chain's tray (they move with the gantry)
    out["lamp_plate"] = Pos(LC[0], TRAY[1], TRAY[2]) * p("lamp_plate")
    for i, (dx, y) in enumerate(zip(UV_X, (UV_Y[0], UV_Y[0], UV_Y[1])), 1):
        out[f"uv_lamp_{i}"] = Pos(LC[0] + dx, y, UV_BOT + 59.0) * b("uv_lamp")
    # the enclosure: the 2020 frame
    (x0, x1), (y0, y1) = ENC_X, ENC_Y
    zm = (TABLE + ENC_TOP) / 2.0
    for i, (x, y) in enumerate(((x0, y0), (x1, y0), (x0, y1), (x1, y1)), 1):
        out[f"encl_post_{i}"] = Pos(x, y, zm) * b("encl_post")
    for i, (y, z) in enumerate(((y0, TABLE + 10.0), (y1, TABLE + 10.0), (y0, ENC_TOP - 10.0), (y1, ENC_TOP - 10.0)), 1):
        out[f"encl_rail_x{i}"] = Pos((x0 + x1) / 2.0, y, z) * b("encl_rail_x")
    for i, (x, z) in enumerate(((x0, TABLE + 10.0), (x1, TABLE + 10.0), (x0, ENC_TOP - 10.0), (x1, ENC_TOP - 10.0)), 1):
        out[f"encl_rail_y{i}"] = Pos(x, (y0 + y1) / 2.0, z) * b("encl_rail_y")
    # ... and its skin
    xm, ym = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    out["front_panel"] = Pos(xm, y0 - 11.5, zm) * p("front_panel")
    out["door"] = Pos(xm, y0 - 14.5, zm + DOOR_Z) * p("door")
    out["laser_window"] = Pos(xm, y0 - 10.5, zm + DOOR_Z + 20.0) * p("laser_window")
    out["back_panel"] = Pos(xm, y1 + 11.5, zm) * p("back_panel")
    out["side_panel_1"] = Pos(x0 - 11.5, ym, zm) * p("side_panel")
    out["side_panel_2"] = Pos(x1 + 11.5, ym, zm) * p("side_panel")
    out["top_panel"] = Pos(xm, ym, ENC_TOP + 1.5) * p("top_panel")
    return out

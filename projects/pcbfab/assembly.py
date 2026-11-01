"""The PCB fab: one machine. LumenPnP v4.2.0 with its Y axis 300 mm longer, a laser zone behind its PnP area.

    pnp zone     the hot plate on four standoffs over a deck on four 2020 legs from the table, between the feeder
                 rails under the head: solder paste, via silver, pick-and-place, then reflow / cure in place.
    laser zone   behind it, in the length the stretch added: the laser bed (the hot plate's design, not heated) on a
                 deck whose legs straddle the fiber source on the table; the galvo hangs from a 2040 bridge (on edge: a 2020 sagged 538 um under it) on two
                 posts outside the frame, the F160 lens down, its focus on the board top. Etch and drill.
The gantry passes between the two: the laser board's top is set so the lens clears the gantry's top (z 240.4 in
Opulo's model) and the pins clear the head's lowest point (z ~90), so the head can carry the board from the laser
bed to the hot plate. The flip stays by hand, onto the same two 3 mm pins.
LumenPnP is the `lumenpnp_long` project at its own origin (x along the front feeder rail, the table at z -101).

The laser stack, bottom up: the board top (LASER_TOP); the lens's 175.72 working distance; the lens 52.26
(Spectral Products EFL 160); the SG7110 93.6; the bridge beam on top of it.
"""
from build123d import Pos, Rot
from cad_agent.state import build_part, bought_solid

SLUG = "pcbfab"

SUBASSEMBLIES = {"lumenpnp_long": {"project": "lumenpnp_long", "at": [0, 0, 0], "turn": [0, 0, 0]}}

TABLE = -101.0                          # LumenPnP's feet
BOARD_T, PLATE_T, STANDOFF_H, DECK_T = 1.6, 9.525, 25.0, 6.0
MOUNT = (68.0, 68.0)                    # the plate's standoff holes, from its centre (hot_plate.py: 150 square, inset 7)
PIN_X, PIN_L = 58.0, 12.5               # half the pin pitch; reg_pin.py: through the plate, 3 proud
# pnp zone
HC = (230.0, 110.0)                     # the hot plate's centre: clear of the staging plate, feeders and nozzle rack
HP_TOP = 35.925                         # 1.5 over LumenPnP's staging plate top (z 34.4); legs 96.4
HP_LEG = (80.0, 75.0)
# laser zone
LC = (300.0, 560.0)                     # the laser bed's centre: mid-frame in x, in the added length in y
LASER_TOP = 80.0                        # the board top: pins at 81.4 under the head's ~90, lens at 255.7 over 240.4
GALVO_H, LENS_H, LENS_WD = 93.6, 52.26, 175.72
LENS_SHIFT = 118.5 / 2.0 - 45.0         # the lens under the galvo's output end, not its middle
LASER_LEG = (105.0, 135.0)              # wide enough for the fiber source (200 x 245 this way round) between them
LBED_TOP = LASER_TOP - BOARD_T
LDECK_TOP = LBED_TOP - PLATE_T - STANDOFF_H                     # 43.875; legs 138.875
GALVO_TOP = LASER_TOP + LENS_WD + LENS_H + GALVO_H              # 401.58: the beam's underside
BRIDGE_X = (-100.0, 680.0)              # the posts: 25 clear of the gantry's left end (x -65) and the right side frame (x 620)

GANTRY = ("lumenpnp_long/x_gantry", "lumenpnp_long/x_drag_chain_asm")    # what Y moves (the head rides on it)
GANTRY_Y = 190.0                        # the head's y in Opulo's model, about
AXES = {"y": {"moves": GANTRY, "direction": (0, 1, 0), "travel": (-100.0, LC[1] - GANTRY_Y + 40.0)}}
POSES = {"pick_laser": {"y": LC[1] - GANTRY_Y}, "place_hot": {"y": HC[1] - GANTRY_Y}}

CLEARANCE = {}


def _contact():
    c = {"galvo|bridge_beam", "ftheta_lens|galvo", "bridge_post_1|bridge_beam", "bridge_post_2|bridge_beam",
         "pcb_blank|laser_bed", "reg_pin_1|laser_bed", "reg_pin_2|laser_bed", "reg_pin_3|hot_plate",
         "reg_pin_4|hot_plate"}
    for i in range(1, 5):
        c |= {f"standoff_{i}|laser_deck", f"standoff_{i}|laser_bed", f"laser_leg_{i}|laser_deck",
              f"standoff_{i + 4}|hp_deck", f"standoff_{i + 4}|hot_plate", f"leg_{i}|hp_deck"}
    return c


ALLOW_CONTACT = _contact()

CORNERS = ((-1, -1), (1, -1), (-1, 1), (1, 1))


def parts():
    p = lambda n: build_part(SLUG, n)[0]
    b = lambda n: bought_solid(SLUG, n)
    out = {}
    # laser zone: the bed
    out["laser_deck"] = Pos(LC[0], LC[1], LDECK_TOP - DECK_T / 2.0) * p("laser_deck")
    for i, (sx, sy) in enumerate(CORNERS, 1):
        out[f"laser_leg_{i}"] = Pos(LC[0] + sx * LASER_LEG[0], LC[1] + sy * LASER_LEG[1],
                                    (TABLE + LDECK_TOP - DECK_T) / 2.0) * b("laser_leg")
        out[f"standoff_{i}"] = Pos(LC[0] + sx * MOUNT[0], LC[1] + sy * MOUNT[1],
                                   LDECK_TOP + STANDOFF_H / 2.0) * p("standoff")
    out["laser_bed"] = Pos(LC[0], LC[1], LBED_TOP - PLATE_T / 2.0) * p("laser_bed")
    for i, sx in ((1, -1), (2, 1)):
        out[f"reg_pin_{i}"] = Pos(LC[0] + sx * PIN_X, LC[1], LBED_TOP - PLATE_T + PIN_L / 2.0) * p("reg_pin")
    out["pcb_blank"] = Pos(LC[0], LC[1], LASER_TOP - BOARD_T / 2.0) * p("pcb_blank")
    out["fiber_source"] = Pos(LC[0], LC[1], TABLE + 32.5) * Rot(0, 0, 90) * b("fiber_source")
    # laser zone: the bridge, the galvo and the lens
    for i, x in enumerate(BRIDGE_X, 1):
        out[f"bridge_post_{i}"] = Pos(x, LC[1], (TABLE + GALVO_TOP) / 2.0) * b("bridge_post")
    out["bridge_beam"] = Pos(sum(BRIDGE_X) / 2.0, LC[1], GALVO_TOP + 20.0) * Rot(90, 0, 0) * b("bridge_beam")   # 2040 on edge
    out["galvo"] = Pos(LC[0] + LENS_SHIFT, LC[1], GALVO_TOP - GALVO_H / 2.0) * b("galvo")
    out["ftheta_lens"] = Pos(LC[0], LC[1], GALVO_TOP - GALVO_H - LENS_H / 2.0) * b("ftheta_lens")
    # pnp zone: the hot plate
    out["hp_deck"] = Pos(HC[0], HC[1], HP_TOP - PLATE_T - STANDOFF_H - DECK_T / 2.0) * p("hp_deck")
    for i, (sx, sy) in enumerate(CORNERS, 1):
        out[f"leg_{i}"] = Pos(HC[0] + sx * HP_LEG[0], HC[1] + sy * HP_LEG[1],
                              (TABLE + HP_TOP - PLATE_T - STANDOFF_H - DECK_T) / 2.0) * b("leg")
        out[f"standoff_{i + 4}"] = Pos(HC[0] + sx * MOUNT[0], HC[1] + sy * MOUNT[1],
                                       HP_TOP - PLATE_T - STANDOFF_H / 2.0) * p("standoff")
    out["hot_plate"] = Pos(HC[0], HC[1], HP_TOP - PLATE_T / 2.0) * p("hot_plate")
    for i, sx in ((3, -1), (4, 1)):
        out[f"reg_pin_{i}"] = Pos(HC[0] + sx * PIN_X, HC[1], HP_TOP - PLATE_T + PIN_L / 2.0) * p("reg_pin")
    return out

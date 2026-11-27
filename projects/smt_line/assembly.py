"""The SMT line, v0 (2026-11-27): modules that dock along one board path, every one borrowed.

    [pick-and-place + its conveyor]  --SMEMA gap-->  [conveyor reflow oven]          boards flow +x

  pnp_v4        the LumenPnP v4 (Opulo, CERN-OHL-W v2), its own CAD, read by tools/fcstd_read.py.
  pnp_conveyor  Opulo's 2021 conveyor prototype for the Index (lumenpnp-archive, `conveyor` branch, GPL-3.0),
                every body unchanged, turned from the Index's y-up frame and clamped on the LumenPnP's lower side
                extrusions as it was on the Index's, slid 90 mm back so its front mounts clear the control box.
                It crosses the machine through the side windows (between the extrusions at z 40 and z 90) over
                where the two rear staging plates were; the feeders move to the front plate.
  reflow_oven   the NeoDen IN6's published outline and tunnel (260 wide, 30 clear, left to right), an envelope.
  riser         any stand that lifts the pick-and-place to the oven's belt height.
  board_*       a board on the conveyor's ledges, and one in the oven.

SMEMA 1.2 sets how modules hand a board over: the front rail fixed (here, the conveyor's front rail, the one
without knobs), boards edge-carried, the gap between modules at most 9.5 mm. Its floor height (940-965) is for
floor-standing machines; on a bench, the line height is whatever the oven's belt is, and that is not published
for the IN6 (see bought/reflow_oven.py). LINE_Z holds it, from the one desktop oven that does publish it.

Frame: the bench top at z 0; x and y are the pick-and-place's own (x across it, y front to back), so its
parts read the same numbers as in Opulo's CAD.

"LumenPnP is (c) by Opulo. This notice must be included in any distributions of this project or derivative works."
"""
from build123d import Pos

from cad_agent.state import bought_solid

SLUG = "smt_line"

LINE_Z = 300.0          # board bottom above the bench: the 3-zone desktop oven's published belt height
LEDGE_Z = 41.654936218  # both ledges' top in the pick-and-place frame, as borrow.py prints it
FOOT_Z = -100.011092377    # the bottoms of the LumenPnP's front leg extensions, from their faces (the back ones are 0.11 higher)
PNP_Z = LINE_Z - LEDGE_Z                 # where the pick-and-place frame's z 0 sits above the bench
RISER = PNP_Z + FOOT_Z                   # 158.33: the stand's height

RAIL_END_X = 605.52     # the front rail's far end (Index z -585, + 20.5, + 0.02 seating)
SMEMA_GAP = 9.5         # SMEMA 1.2: the most a board may jump between modules
LANE_Y = (270.6, 414.5) # between the rails' walls
LANE_MID = sum(LANE_Y) / 2

CLEARANCE = {}
ALLOW_CONTACT = {
    "pnp_v4|pnp_conveyor",      # its mounts clamp the side extrusions and its rails rest on them, as Opulo drew it
    "pnp_v4|riser",             # the feet stand on it
    "board_pnp|pnp_conveyor",   # on the ledges
    "board_oven|reflow_oven",   # on the belt
}

MECHANISM = {"static": {"pnp_v4": "a whole machine, its own CAD; its axes are Opulo's",
                        "pnp_conveyor": "Opulo's prototype; its rollers turn, but its belt and motor were never drawn",
                        "reflow_oven": "an envelope", "riser": "a stand"}}


def parts():
    b = lambda n, **o: bought_solid(SLUG, n, **o)
    up = Pos(0, 0, PNP_Z)
    oven_x = RAIL_END_X + SMEMA_GAP
    return {
        "riser": Pos(0, 0, RISER) * b("riser", height=RISER),
        "pnp_v4": up * b("pnp_v4"),
        "pnp_conveyor": up * b("pnp_conveyor"),
        "board_pnp": Pos(230.0, LANE_Y[0] + 2.0, LINE_Z) * b("board"),
        "reflow_oven": Pos(oven_x, LANE_MID, 0) * b("reflow_oven", belt_z=LINE_Z),
        "board_oven": Pos(oven_x + 400.0, LANE_MID - 70.0, LINE_Z) * b("board"),
    }

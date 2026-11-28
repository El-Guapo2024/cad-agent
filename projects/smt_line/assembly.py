"""The SMT line, v0 (2026-11-27): modules that dock along one board path, every one borrowed.

    [pick-and-place + its conveyor]  --SMEMA gap-->  [conveyor reflow oven]          boards flow +x

  pnp_v4        the LumenPnP v4 (Opulo, CERN-OHL-W v2), its own CAD, read by tools/fcstd_read.py.
  pnp_conveyor  the PCB conveyor of Deltaprintr's Rapid Star (CC BY-NC-SA 4.0, used with Deltaprintr's
                permission), both rails as drawn: each a 2020 x 640 extrusion carrying a 4 mm flat belt driven
                by an N20 gear motor, with a guide, hoods, a servo gripper and a board-stop switch (and on the
                front rail, a stop solenoid). Moved only: the rails span the LumenPnP's lower side extrusions
                (600 apart) on rail_blocks, the front guide where Opulo's own prototype had its front wall, the
                back one 143.9 behind it, and the belts end 8.0 short of the oven's end roller. The guide plates
                are cut 2.2 shorter at the oven end, with Deltaprintr's permission. Opulo's 2021
                prototype was here until v0.3; it never had its drive drawn.
  rail_blocks   four bought 20 x 20 x 23 blocks, one under each rail end on a side extrusion. Rapid Star rests its
                rails straight on its own side extrusions, 640 apart; the LumenPnP's are 600 apart, which puts the
                guide's low lobe (it carries the lower pulleys, 21.6 below the rail) on the right one. The blocks
                lift it 1.4 clear without changing the guide.
  reflow_oven   the NeoDen IN6, its outline from its manual and its shape and belt measured off the manual's
                photos (bought/reflow_oven.py).
  oven_stand    any block that lifts the oven so its belt meets the pick-and-place's board height.
  board_*       a board on the conveyor's belts, and one in the oven.

SMEMA 1.2 sets how modules hand a board over: the front rail fixed (here, the conveyor's front rail),
boards edge-carried, the gap between modules at most 9.5 mm. Its floor height (940-965) is for
floor-standing machines. On a bench, the LumenPnP stands on its own feet as Opulo built it, which puts its board
180.1 above the bench (LINE_Z). The IN6's belt is 66 above its own bottom, measured off its manual's photos,
so the oven stands on a 114.1 block.

Frame: the bench top at z 0; x and y are the pick-and-place's own (x across it, y front to back), so its
parts read the same numbers as in Opulo's CAD.

"LumenPnP is (c) by Opulo. This notice must be included in any distributions of this project or derivative works."
Rapid Star conveyor by Deltaprintr (deltaprintr.com), CC BY-NC-SA 4.0. Deltaprintr and Rapid Star are trademarks of
Deltaprinter Inc.
"""
from build123d import Part, Pos

from cad_agent.state import bought_solid

SLUG = "smt_line"

BELT_Z = 80.067436      # the conveyor belts' top in the pick-and-place frame, as borrow.py prints it
FOOT_Z = -100.011092377    # the bottoms of the LumenPnP's front leg extensions, from their faces (the back ones are 0.11 higher)
PNP_Z = -FOOT_Z                          # the pick-and-place stands on the bench
LINE_Z = PNP_Z + BELT_Z                  # 180.08: board bottom above the bench
OVEN_BELT = 66.0                         # the IN6's belt above its own bottom (bought/reflow_oven.py)
OVEN_STAND = LINE_Z - OVEN_BELT          # 114.08

GUIDE_END_X = 655.95    # the guides' far end, cut short there (borrow.py RS_GUIDE_END_X): 1.05 from the oven's end roller (x 657.00)
BELT_END_X = 649.0      # the belts' far end (borrow.py RS_BELT_END_X): 8.0 from the roller, inside SMEMA's 9.5
SMEMA_GAP = 9.5         # SMEMA 1.2: the most a board may jump between modules
PNP_MOTOR_X = 641.8     # the LumenPnP's right Y motor sticks out to here, 194-265 above the bench
LANE_Y = (270.6, 414.5) # between the two guides
LANE_MID = sum(LANE_Y) / 2
RAILS_Y = (LANE_Y[0] - 11.5, LANE_Y[1] + 11.5)   # each 2020 rail's middle: 1.5 to 21.5 outside its guide's face
EXTRUSIONS_X = (9.9363, 590.0685)  # the LumenPnP's lower side extrusions' middles, from their faces (borrow.py notes)
EXTRUSION_TOP = 40.0674           # the higher (left) one's top, as borrow.py measures it; the right one's is 0.063 lower
RS_LIFT = 23.0                    # borrow.py RS_LIFT. The blocks are drawn 1 um short, their tops on the rails, so the
                                  # two CADs' rounding (tenths of a um) doesn't read as overlap

CLEARANCE = {}
ALLOW_CONTACT = {
    "pnp_v4|rail_blocks",       # the blocks stand on the side extrusions
    "pnp_conveyor|rail_blocks", # the rails stand on the blocks
    "oven_stand|reflow_oven",   # the oven stands on it
    "board_pnp|pnp_conveyor",   # on the belts
    "board_oven|reflow_oven",   # on the belt
}

MECHANISM = {"static": {"pnp_v4": "a whole machine, its own CAD; its axes are Opulo's",
                        "pnp_conveyor": "Rapid Star's belts, driven by their N20s; drawn still",
                        "reflow_oven": "a bought oven; its belt is its own",
                        "oven_stand": "a stand", "rail_blocks": "blocks"}}


def parts():
    b = lambda n, **o: bought_solid(SLUG, n, **o)
    up = Pos(0, 0, PNP_Z)
    oven_x = PNP_MOTOR_X + 3.2   # the oven's end can't come closer than the PnP's motor; the belts reach into its pocket
    return {
        "pnp_v4": up * b("pnp_v4"),
        "pnp_conveyor": up * b("pnp_conveyor"),
        "rail_blocks": sum((Pos(x, y, PNP_Z + EXTRUSION_TOP + RS_LIFT) * b("riser", length=20.0, depth=20.0, height=RS_LIFT - 0.001)
                            for x in EXTRUSIONS_X for y in RAILS_Y), start=Part()),
        "board_pnp": Pos(230.0, LANE_Y[0] + 2.0, LINE_Z) * b("board"),
        "oven_stand": Pos(oven_x + 510.0, LANE_MID, OVEN_STAND) * b("riser", height=OVEN_STAND),
        "reflow_oven": Pos(oven_x, LANE_MID, OVEN_STAND) * b("reflow_oven", belt_z=OVEN_BELT),
        "board_oven": Pos(oven_x + 400.0, LANE_MID - 70.0, LINE_Z) * b("board"),
    }

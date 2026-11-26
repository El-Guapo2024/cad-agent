"""The line's board carrier: one per board, carried by hand from station to station and located at each the same
way, on a nest's two pins (nest.py). Machined aluminium. Copied from mini_conveyor, whose conveyor carries it later.

A 150 x 150 board drops into a pocket as deep as the board, so the board's top is the carrier's top. Two tooling
holes on the front edge, at SMEMA 1.2's tooling-pin size and edge distance (0.156 in, 0.300 in from the edge), are
what a station's lift pins locate; here reamed 4.0 H7 for stock 4 mm dowels (SMEMA's 0.156 in is 3.96, no stock
pin fits it). Finger notches at the pocket's sides lift the board out.

Flip holes: two 3.0 holes through the pocket floor at (+-69, the pocket's middle). The laser drills the board through
them on side A; for side B the board is turned over about y and two 3 mm pins dropped in the holes take it back to
the same place. A turned-over board's holes swap, which the holes' symmetry about x 0 allows.

Frame: the carrier's bottom at z 0, its front edge at y 0 (the fixed rail's side), centred in x (the travel).
"""
from build123d import Box, Cylinder, Pos

MATERIAL = "aluminium"
PROCESS = "cnc"
MIN_FEATURE_MM = 2.0

PARAMS = {"size_x": 170.0, "size_y": 170.0, "thick": 6.0, "board": 150.0, "board_t": 1.6, "fit": 0.2,
          "pin_hole": 4.0, "pin_edge": 7.62, "pin_x": 70.0, "notch": 12.0,
          "flip_hole": 3.0, "flip_x": 69.0}


def build(size_x, size_y, thick, board, board_t, fit, pin_hole, pin_edge, pin_x, notch, flip_hole, flip_x):
    c = Pos(0, size_y / 2.0, thick / 2.0) * Box(size_x, size_y, thick)
    pocket = board + 2 * fit
    c -= Pos(0, size_y / 2.0, thick - board_t / 2.0) * Box(pocket, pocket, board_t + 0.01)
    for sx in (-1, 1):                                                   # finger notches, left and right
        c -= Pos(sx * pocket / 2.0, size_y / 2.0, thick - board_t / 2.0 - 1.0) * Cylinder(notch / 2.0, board_t + 2.01)
        c -= Pos(sx * pin_x, pin_edge, thick / 2.0) * Cylinder(pin_hole / 2.0, thick + 2)   # tooling holes
    for sx in (-1, 1):                                                   # flip holes through the pocket floor
        c -= Pos(sx * flip_x, size_y / 2.0, thick / 2.0) * Cylinder(flip_hole / 2.0, thick + 2)
    return c

"""Board fixture: the aluminium plate the board travels on between the laser, the pick-and-place and the oven.

It bridges LumenPnP's front and rear feeder rails (their tops at z 20), so the board's top sits at 37, the height the
head's tools are set for. Three 3 mm pin holes locate the board 3-2-1 (two on its -x edge, one on its -y edge); the
pins are pressed in, the board pushed against them. Waterjet cut, 15.4 thick.
"""
from build123d import Box, Cylinder, Pos

MATERIAL = "aluminium"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 1.0
EXPECT_FEATURES = 3

PARAMS = {"size_x": 260.0, "size_y": 440.0, "thick": 15.4, "pin": 3.0, "board_x": 229.0, "board_y": 305.0,
          "board_dy": -37.5}


def build(size_x, size_y, thick, pin, board_x, board_y, board_dy):
    plate = Box(size_x, size_y, thick)
    x0, y0 = -board_x / 2.0 - pin / 2.0, board_dy - board_y / 2.0 - pin / 2.0
    for x, y in ((x0, board_dy - 100.0), (x0, board_dy + 100.0), (-board_x / 2.0 + 40.0, y0)):
        plate -= Pos(x, y, 0) * Cylinder(pin / 2.0, thick + 2)
    return plate

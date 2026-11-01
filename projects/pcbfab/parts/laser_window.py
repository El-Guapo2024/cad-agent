"""Laser window: OptoSigma YL-510C-Y2(5) acrylic, 300 x 300, OD 8 at 355 nm (OD 7 at 1064), inside the door's opening.

27% visible transmission: the board can be watched while the UV laser runs. 20 mm over the door's opening all round.
https://www.optosigma.com/us_en/laser-safety-new/laser-safety-window/300x300mm-laser-safety-window-acrylic-resin-27-vtl-
ndyag-yl-510c-y2-5.html (USD 945). Its thickness is NOT on that page: 5 here, read from the part number's (5); confirm.
"""
from build123d import Box, Cylinder, Pos, Rot

MATERIAL = "acrylic"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 3.0
EXPECT_FEATURES = 0

PARAMS = {'size_x': 300.0, 'size_y': 5.0, 'thickness': 300.0}


def build(size_x, size_y, thickness):
    p = Box(size_x, size_y, thickness)
    return p

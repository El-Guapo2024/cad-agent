"""Platen skin: the top layer of the heated vacuum platen, the 1 mm hole grid the board lies on.

The platen is three 6061 layers screwed and sealed together (a laminated vacuum table): this 5 mm skin, a 6 mm ring
whose window is the plenum, and a 4 mm base the mica heater is clamped under. It does what the old vacuum bed and hot
plate did apart: LPKF ProConduct's vacuum table for the via paste, the hold-down for the laser and the parts, and the
reflow plate. 215 x 295: it rises through the flip frame's window with 3 mm to spare each side.
"""
from build123d import Box, Cylinder, Pos

MATERIAL = "aluminium"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 1.0
EXPECT_FEATURES = 234        # 13 x 18 vacuum holes

PARAMS = {"size_x": 215.0, "size_y": 295.0, "thick": 5.0, "hole": 1.0, "pitch": 15.0, "nx": 13, "ny": 18}


def build(size_x, size_y, thick, hole, pitch, nx, ny):
    b = Box(size_x, size_y, thick)
    for i in range(nx):
        for j in range(ny):
            b -= Pos((i - (nx - 1) / 2.0) * pitch, (j - (ny - 1) / 2.0) * pitch, 0) * Cylinder(hole / 2.0, thick + 2)
    return b

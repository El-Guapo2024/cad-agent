"""UV lamp bracket: a 6 mm aluminium angle under the back of the X cable chain's tray, carrying the three UV lamps.

The tray runs the gantry's whole length and moves only with Y, so the lamps sweep the board as Y moves and the head
keeps its whole X travel. The flange bolts up under the tray; the web drops behind the chain's links (they overhang
the tray to y 285), so nothing reaches the chain's moving loop above them. The lamps bolt to the web's back face.
"""
from build123d import Box, Pos

MATERIAL = "aluminium"
PROCESS = "cnc"
MIN_FEATURE_MM = 1.0
EXPECT_FEATURES = 0

PARAMS = {"length": 240.0, "flange": 52.0, "web": 46.0, "thickness": 6.0}


def build(length, flange, web, thickness):
    # origin: the angle's outer corner, top back (flange top face, web back face); flange along -y, web along -z
    f = Pos(0, -flange / 2.0, -thickness / 2.0) * Box(length, flange, thickness)
    w = Pos(0, -thickness / 2.0, -web / 2.0) * Box(length, thickness, web)
    return f + w

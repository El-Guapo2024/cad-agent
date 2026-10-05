"""Front panel: 3 mm laser-cut acrylic that screws onto the frame and carries the button and the OLED.

One flat sheet, so every feature is a 2D cut: four M3 clearance holes over the frame's
tapped holes, a round hole for the 16 mm button's barrel, and a window for the OLED glass.

The button hole is the 16.0 mm the product is sold for. The barrel measures 15.56, so it
leaves 0.22 mm all round: enough to slide in, not enough to show. The window is the glass
(26.7 x 19.26, +-0.2 on both) plus 0.25 mm a side, with R0.4 corners so the acrylic does not
crack at a sharp inside corner. A rounded corner pulls the cut back toward the glass corner,
so the closest approach is at the corners (0.19 mm), not at the sides (0.25).

The M3 holes are the clearance size from cad_agent.parts (3.4 mm), over the frame's 2.5 mm
tap holes. Their 5 mm edge distance leaves 3.3 mm of acrylic, and the R5 corner is
concentric with them, so the narrowest web stays well above the laser-cut limit.
"""
from build123d import Axis, Box, Cylinder, Pos, fillet
from cad_agent.parts import CLEARANCE_HOLE

MATERIAL = "acrylic"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 3.0     # narrowest remaining acrylic: an M3 hole to the edge, 3.3 mm

# Cutouts through the sheet: 4 M3 holes, 1 button hole, 1 OLED window.
EXPECT_FEATURES = 6

PARAMS = {
    "width": 100.0,          # x, the frame's outline
    "height": 60.0,          # y
    "thickness": 3.0,        # z, sheet as bought
    "corner_r": 5.0,         # concentric with the M3 holes
    "screw": "M3",
    "screw_x": 45.0,         # hole centres from the middle: the frame's 90 x 50 rectangle
    "screw_y": 25.0,
    "button_x": -22.5,       # button barrel axis
    "button_y": 0.0,
    "button_hole": 16.0,
    "oled_x": 17.5,          # OLED module centre, which is the glass centre
    "oled_y": 0.0,
    "window_w": 27.2,        # glass 26.7 + 2 x 0.25
    "window_h": 19.76,       # glass 19.26 + 2 x 0.25
    "window_r": 0.4,
}


def build(width, height, thickness, corner_r, screw, screw_x, screw_y,
          button_x, button_y, button_hole, oled_x, oled_y, window_w, window_h,
          window_r):
    panel = fillet(Box(width, height, thickness).edges().filter_by(Axis.Z), corner_r)

    d = CLEARANCE_HOLE[screw]
    for sx in (-1, 1):
        for sy in (-1, 1):
            panel -= Pos(sx * screw_x, sy * screw_y, 0) * Cylinder(d / 2.0, thickness + 2)

    panel -= Pos(button_x, button_y, 0) * Cylinder(button_hole / 2.0, thickness + 2)

    window = fillet(Box(window_w, window_h, thickness + 2).edges().filter_by(Axis.Z), window_r)
    panel -= Pos(oled_x, oled_y, 0) * window
    return panel


CUTLIST = [{"kind": "acrylic_3mm", "size_mm": [100.0, 60.0], "qty": 1}]

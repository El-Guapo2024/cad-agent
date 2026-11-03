"""Window panel: the upper-left front tile, cut 290 x 290 for the OptoSigma laser-safety window behind it (5 mm
of the window under the panel all round), so the laser and the cure can be watched. The e-stop and the key switch
(22.5 mm holes) are in it beside the window.
"""
from build123d import Box, Cylinder, Pos

MATERIAL = "aluminium"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 1.0
EXPECT_FEATURES = 3

PARAMS = {"size_a": 445.0, "size_b": 343.0, "thick": 3.0, "window": 290.0, "window_a": -40.0, "button": 22.5,
          "button_a": 175.0, "button_b": (60.0, -60.0)}


def build(size_a, size_b, thick, window, window_a, button, button_a, button_b):
    p = Box(size_a, size_b, thick) - Pos(window_a, 0, 0) * Box(window, window, thick + 2)
    for b in button_b:
        p -= Pos(button_a, b, 0) * Cylinder(button / 2.0, thick + 2)
    return p

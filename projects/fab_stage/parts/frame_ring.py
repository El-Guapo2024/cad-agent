"""Flip frame ring: one layer of the stainless frame the board lives in for the whole job.

CircuitJet IV's one-fixture idea: the board is never unclamped between steps, so laser, paste, placement and reflow
all see it in the same place, and the flip is a half turn of the frame about the board's own mid-plane (the shaft
line), so the second side lands where the first was. The frame is three laser-cut stainless layers screwed together:
an outer ring above and one below whose windows are 4 mm (sides) and 2 mm (ends) inside the board's edge, and a 1.6
shim between them whose window is the board (0.2 slip): the board's edge is held in the groove they make. The platen
rises through the window from below. Stainless: it sits 3 mm from the 240 C platen. Trunnion blocks bolt to its ends.
"""
from build123d import Box

MATERIAL = "stainless"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 1.0
EXPECT_FEATURES = 1

PARAMS = {"outer_x": 257.4, "outer_y": 333.4, "window_x": 221.4, "window_y": 301.4, "thick": 5.2}


def build(outer_x, outer_y, window_x, window_y, thick):
    return Box(outer_x, outer_y, thick) - Box(window_x, window_y, thick + 2)

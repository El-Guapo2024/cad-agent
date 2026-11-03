"""Panel: a 3 mm aluminium tile of the enclosure's skin, screwed to the 2020 frame's outer faces.

The enclosure is a 2020 frame with mid rails, so each tile is under 600 x 400 (a sheet that a laser or a waterjet
cuts in one piece): 2 x 2 tiles a side, 2 x 3 on top. Drawn flat in its own XY, sized per tile in assembly.py, and
laid on its face there. Blackened (anodised) inside: no stray UV reflections.
"""
from build123d import Box

MATERIAL = "aluminium"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 1.0
EXPECT_FEATURES = 0

PARAMS = {"size_a": 445.0, "size_b": 342.0, "thick": 3.0}


def build(size_a, size_b, thick):
    return Box(size_a, size_b, thick)

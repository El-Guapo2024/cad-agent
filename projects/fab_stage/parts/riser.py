"""Rail riser: a 6061 bar (cut from 20 mm plate) a miniature rail is screwed down to, lifting it clear of the ball screw between the rails.

The MGN15 rail's counterbored holes (d 3.5, every 40 mm, HIWIN table 3.81) land on M3 tapped holes along its top, so
the rail can be screwed down where it sits; the bar is bolted to its plate from below. The 22 mm rise is what the
ball screw's end supports need under the carriage plate (assembly.py).
"""
from build123d import Box, Cylinder, Pos
from cad_agent.parts import TAP_DRILL

MATERIAL = "aluminium"
PROCESS = "laser_cut"
MIN_FEATURE_MM = 1.0
EXPECT_FEATURES = 0

PARAMS = {"length": 320.0, "width": 20.0, "height": 22.0, "pitch": 40.0, "end_min": 6.0, "tap_depth": 8.0}


def build(length, width, height, pitch, end_min, tap_depth):
    b = Box(length, width, height)
    n = int((length - 2 * end_min) // pitch) + 1                 # the rail's own rule (mgn.py, HIWIN note 2)
    end = (length - (n - 1) * pitch) / 2.0
    for i in range(n):
        b -= Pos(-length / 2.0 + end + i * pitch, 0, height / 2.0 - tap_depth / 2.0) * Cylinder(TAP_DRILL["M3"] / 2.0,
                                                                                               tap_depth)
    return b

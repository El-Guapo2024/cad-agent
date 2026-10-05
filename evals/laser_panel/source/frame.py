"""Front frame of the control box: the part the panel screws onto.

Given by the task, not bought: a 100 x 60 x 8 mm rim with an 80 x 40 mm opening, outer corners R5, and
four blind M3 tapped holes in its front face on a 90 x 50 mm rectangle. The holes sit 5 mm in from the
edges, so each one is centred on the 10 mm rim and the R5 corner is concentric with it.

The tap holes are drilled to the M3 tapping size in cad_agent.parts (TAP_DRILL, 2.5 mm), 6 mm deep. The
task checks the panel's holes against them, so they come from the same table the interface rule reads.

Origin: the middle of the box (its bounding-box centre). The front face is at +4 mm, so
`Pos(0, 0, -4) * frame` puts the front face at z = 0. make_given.py writes the STEP.
"""
from build123d import Axis, Box, Cylinder, Pos, fillet

VENDOR = "task brief"
SOURCE = ("Given by the laser_panel task brief: front frame 100 x 60 x 8 mm, 80 x 40 mm opening, "
          "outer corners R5, four M3 tapped holes (2.5 mm tap drill, 6 mm deep) in the front face "
          "at x = +-45, y = +-25 mm")

LENGTH, WIDTH, THICK = 100.0, 60.0, 8.0
OPENING = (80.0, 40.0)
CORNER_R = 5.0
HOLE_X, HOLE_Y = 45.0, 25.0
TAP_DIA, TAP_DEPTH = 2.5, 6.0           # M3 tap drill, from cad_agent.parts.TAP_DRILL


def build():
    frame = fillet(Box(LENGTH, WIDTH, THICK).edges().filter_by(Axis.Z), CORNER_R)
    frame -= Box(OPENING[0], OPENING[1], THICK + 2)
    # Each drill starts 1 mm above the front face so the hole opens cleanly.
    for sx in (-1, 1):
        for sy in (-1, 1):
            frame -= (Pos(sx * HOLE_X, sy * HOLE_Y, THICK / 2.0 - TAP_DEPTH / 2.0 + 0.5)
                      * Cylinder(TAP_DIA / 2.0, TAP_DEPTH + 1.0))
    return frame

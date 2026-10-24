"""Mounting plate: a part made as FreeCAD's PartDesign makes it, a Body of sketches, pads and pockets.

60 x 40 x 6 mm aluminium, four M4 clearance holes through the corners, a 16 mm boss in the middle with a
blind 8 mm bore, and a slot pocket for a cable tie. The shape is FEATURES (cad_agent.feature); the app's
tree and Sketcher edit it in place (cad_agent.feature_edit), and `cad set` edits PARAMS as for any part.
Each sketch stores its solved geometry: the dimensions bound to PARAMS hold for these values, so building
needs no solver until one of them changes.
"""
from cad_agent.feature import (ArcOfCircle, Body, Circle, Constraint, LineSegment, Pad, Pocket, Point,
                               Sketch)

MATERIAL = "aluminium"
PROCESS = "cnc"
MIN_FEATURE_MM = 2.0
EXPECT_FEATURES = 6         # four holes, the bore and the tie slot

PARAMS = {
    "width": 60.0,          # x
    "depth": 40.0,          # y
    "thick": 6.0,           # z
    "boss_h": 4.0,          # the boss stands this far above the plate
}

FEATURES = [
    Sketch("Sketch", support="XY",
           geometry=[
               LineSegment((-30.0, -20.0), (30.0, -20.0)),
               LineSegment((30.0, -20.0), (30.0, 20.0)),
               LineSegment((30.0, 20.0), (-30.0, 20.0)),
               LineSegment((-30.0, 20.0), (-30.0, -20.0)),
               Point((0.0, 0.0), construction=True),
           ],
           constraints=[
               Constraint("Coincident", 0, 2, 1, 1),
               Constraint("Coincident", 1, 2, 2, 1),
               Constraint("Coincident", 2, 2, 3, 1),
               Constraint("Coincident", 3, 2, 0, 1),
               Constraint("Horizontal", 0),
               Constraint("Horizontal", 2),
               Constraint("Vertical", 1),
               Constraint("Vertical", 3),
               Constraint("Symmetric", 0, 1, 1, 2, 4, 1),
               Constraint("Coincident", 4, 1, -1, 1),
               Constraint("DistanceX", 0, 1, 0, 2, "width"),
               Constraint("DistanceY", 1, 1, 1, 2, "depth"),
           ]),
    Pad("Pad", "Sketch", length="thick"),
    Sketch("Holes", support="XY", attachment_offset=(0.0, 0.0, 6.0),
           geometry=[
               Circle((-24.0, -14.0), 2.25),
               Circle((24.0, -14.0), 2.25),
               Circle((24.0, 14.0), 2.25),
               Circle((-24.0, 14.0), 2.25),
           ],
           constraints=[
               Constraint("Diameter", 0, 4.5),        # M4 clearance, medium (ISO 273)
               Constraint("Equal", 0, 1),
               Constraint("Equal", 0, 2),
               Constraint("Equal", 0, 3),
           ]),
    Pocket("Holes001", "Holes", type="ThroughAll"),
    Sketch("BossSketch", support="XY", attachment_offset=(0.0, 0.0, 6.0),
           geometry=[Circle((0.0, 0.0), 8.0)],
           constraints=[Constraint("Diameter", 0, 16.0), Constraint("Coincident", 0, 3, -1, 1)]),
    Pad("Boss", "BossSketch", length="boss_h"),
    Sketch("Bore", support="XY", attachment_offset=(0.0, 0.0, 10.0),
           geometry=[Circle((0.0, 0.0), 4.0)],
           constraints=[Constraint("Diameter", 0, 8.0)]),
    Pocket("BorePocket", "Bore", length=6.0),
    Sketch("TieSlot", support="XY", attachment_offset=(0.0, 0.0, 6.0),
           geometry=[
               LineSegment((23.0, 4.0), (15.0, 4.0)),
               ArcOfCircle((15.0, 0.0), 4.0, 1.5707963268, 4.7123889804),
               LineSegment((15.0, -4.0), (23.0, -4.0)),
               ArcOfCircle((23.0, 0.0), 4.0, -1.5707963268, 1.5707963268),
           ]),
    Pocket("TiePocket", "TieSlot", length=2.0),
]
TIP = "TiePocket"


def build(**p):
    return Body(FEATURES, p, tip=TIP)

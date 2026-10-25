"""Part's Reverse, Scale, Face and RuledSurface (cad_agent/feature_part_misc.py): the documents FreeCAD builds, its
answers recorded in freecad_misc.json (make.py misc).

A Reverse takes its source's Placement, a Scale scales the source's placed shape about the origin, a Face makes faces
from the wires of its Sources through a face maker, and a RuledSurface fills between two edges or wires (Automatic
reversing the second when the fill would be twisted).
"""
from cad_agent import feature_part as Part
from cad_agent.feature import Circle, LineSegment, Sketch  # noqa: F401

from cases import rect

# cases.py's P, spelled out here: when the whole suite is collected another golden area's `cases` module can be the one
# `cases` resolves to (tests/golden/feature/cases.py has rect but no P).
P = ((5.0, -3.0, 2.0), (30.0, 15.0, -10.0))         # a placement off the axes, turned on all three

CASES = {}

# ── Reverse: the source's own geometry reversed, at the source's Placement ──
CASES["reverse"] = {"objects": [
    Part.Box("Box", length=10, width=20, height=5, placement=P),
    Part.Reverse("Box_rev", "Box")]}
CASES["reverse_cut"] = {"objects": [
    Part.Box("Box", length=20, width=20, height=10),
    Part.Cylinder("Cylinder", radius=5, height=20, placement=((10, 10, -5), (0, 0, 0))),
    Part.Cut("Cut", "Box", "Cylinder"),
    Part.Reverse("Cut_rev", "Cut")]}
CASES["reverse_chain"] = {"objects": [
    Part.Box("Box", length=10, width=20, height=5, placement=P),
    Part.Reverse("Box_rev", "Box"),
    Part.Reverse("Box_rev_rev", "Box_rev")]}
# A Reverse with no Source is not in the goldens: FreeCAD's recompute leaves it Valid with a null Shape, never running
# Reverse::execute ("No part object linked."); tests/test_feature_part.py holds our error to the execute's message.

# ── Scale: the base's placed shape scaled about the origin ──
CASES["scale_uniform"] = {"objects": [
    Part.Box("Box", length=10, width=20, height=5, placement=P),
    Part.Scale("Scale", "Box", uniform_scale=2.5)]}
CASES["scale_nonuniform"] = {"objects": [
    Part.Cylinder("Cylinder", radius=4, height=10, placement=((5, -3, 2), (0, 0, 30))),
    Part.Scale("Scale", "Cylinder", uniform=False, x_scale=2.0, y_scale=0.5, z_scale=1.5)]}
CASES["scale_chain"] = {"objects": [
    Part.Box("Box", length=10, width=20, height=5),
    Part.Scale("Scale", "Box", uniform_scale=3.0),
    Part.Scale("Scale2", "Scale", uniform=False, x_scale=0.5, y_scale=1.0, z_scale=2.0)]}
CASES["scale_error"] = {"objects": [Part.Scale("Scale")]}

# ── Face from wires: one maker over the sources' wires ──
SQUARE = Sketch("Square", support="XY", geometry=rect(0, 0, 20, 10))
OTHER = Sketch("Other", support="XY", attachment_offset=(0, 0, 5), geometry=rect(30, 0, 40, 6))
CASES["face_wire"] = {"objects": [SQUARE, Part.Face("Face", ["Square"])]}
CASES["face_two"] = {"objects": [SQUARE, OTHER, Part.Face("Face", ["Square", "Other"])]}
HOLED = Sketch("Holed", support="XY", geometry=rect(0, 0, 20, 10) + [Circle((10, 5), 3)])
CASES["face_hole_simple"] = {"objects": [HOLED, Part.Face("Face", ["Holed"],
                                                           face_maker_class="Part::FaceMakerSimple")]}
CASES["face_hole_unified"] = {"objects": [HOLED, Part.Face("Face", ["Holed"])]}
CASES["face_compound"] = {"objects": [
    Part.Circle("C1", radius=3),
    Part.Circle("C2", radius=2, placement=((10, 0, 0), (0, 0, 0))),
    Part.Compound("Compound", ["C1", "C2"]),
    Part.Face("Face", ["Compound"])]}
CASES["face_vertex"] = {"objects": [
    Part.Vertex("Vertex", x=1, y=2, z=0), Part.Face("Face", ["Vertex"])]}
CASES["face_none"] = {"objects": [Part.Face("Face")]}

# ── Ruled surface: a face between two edges, a shell between two wires ──
LINES = [Part.Line("LineA", x1=0, y1=0, z1=0, x2=10, y2=0, z2=0),
         Part.Line("LineB", x1=0, y1=10, z1=5, x2=10, y2=10, z2=5)]
CASES["ruled_edges"] = {"objects": LINES + [
    Part.RuledSurface("Ruled", ("LineA", "Edge1"), ("LineB", "Edge1"))]}
CASES["ruled_whole"] = {"objects": LINES + [Part.RuledSurface("Ruled", "LineA", "LineB")]}
RA, RB = (Sketch("RectA", support="XY", geometry=rect(0, 0, 10, 6)),
          Sketch("RectB", support="XY", attachment_offset=(2, 1, 8), geometry=rect(0, 0, 10, 6)))
CASES["ruled_wires"] = {"objects": [RA, RB, Part.RuledSurface("Ruled", "RectA", "RectB")]}
CASES["ruled_forward"] = {"objects": [RA, RB, Part.RuledSurface("Ruled", "RectA", "RectB",
                                                                orientation="Forward")]}
CASES["ruled_reversed"] = {"objects": [RA, RB, Part.RuledSurface("Ruled", "RectA", "RectB",
                                                                 orientation="Reversed")]}
CASES["ruled_box_edges"] = {"objects": [
    Part.Box("Box", length=20, width=10, height=5),
    Part.RuledSurface("Ruled", ("Box", "Edge9"), ("Box", "Edge10"))]}
CASES["ruled_two_wires"] = {"objects": LINES + [
    Part.Compound("Compound", ["LineA", "LineB"]),
    Part.RuledSurface("Ruled", "Compound", "LineA")]}
CASES["ruled_no_edge"] = {"objects": [
    Part.Vertex("Vertex", x=0, y=0, z=0),
    Part.Line("Line", x1=0, y1=0, z1=0, x2=10, y2=0, z2=0),
    Part.RuledSurface("Ruled", "Vertex", "Line")]}
CASES["ruled_none"] = {"objects": [Part.RuledSurface("Ruled")]}

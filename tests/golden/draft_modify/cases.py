"""Draft_Move, Draft_Rotate, Draft_Scale and Draft_Offset on part-file objects (cad_agent/draft_modify.py): each case is
a document and a list of Draft calls; make.py runs them with FreeCAD's own Draft in freecadcmd 26.3 and records every
object's properties (freecad.json), tests/test_draft_modify.py the same through cad_agent.draft_modify.
"""
from cad_agent import feature_draft as Draft
from cad_agent import feature_part as Part

CASES = {}
BASE = [Draft.Rectangle("Rectangle", length=25, height=12),
        Draft.Circle("Circle", radius=3, placement=((20, 0, 0), (0, 0, 0))),
        Draft.Wire("Wire", points=[(0, 0, 0), (5, 0, 0), (5, 5, 0)]),
        Draft.Polygon("Polygon", faces_number=6, radius=4, placement=((0, 30, 0), (0, 0, 0))),
        Part.Box("Box", length=4, width=3, height=2, placement=((40, 0, 0), (0, 0, 0)))]
# (op, names, keywords) as cad feature draft takes them
CASES["move"] = {"objects": BASE, "steps": [("move", ["Rectangle", "Circle"], {"vector": "0,10,0"})]}
CASES["move_copy"] = {"objects": BASE, "steps": [("move", ["Circle", "Wire"], {"vector": "5,0,0", "copy": True})]}
CASES["move_part"] = {"objects": BASE, "steps": [("move", ["Box"], {"vector": "1,2,3"})]}
CASES["rotate"] = {"objects": BASE, "steps": [("rotate", ["Rectangle"], {"angle": 90})]}
CASES["rotate_center_axis"] = {"objects": BASE, "steps": [
    ("rotate", ["Polygon", "Box"], {"angle": 30, "center": "5,5,0", "axis": "1,0,0"})]}
CASES["rotate_copy"] = {"objects": BASE, "steps": [("rotate", ["Circle"], {"angle": 45, "copy": True})]}
CASES["scale"] = {"objects": BASE, "steps": [("scale", ["Rectangle"], {"vector": "2,2,1"})]}
CASES["scale_center"] = {"objects": BASE, "steps": [("scale", ["Circle", "Wire"], {"vector": "3,3,3", "center": "1,1,0"})]}
CASES["scale_polygon"] = {"objects": BASE, "steps": [("scale", ["Polygon"], {"vector": "1.5,1.5,1"})]}
CASES["offset_wire"] = {"objects": BASE, "steps": [("offset", ["Wire"], {"vector": "0,-1,0", "copy": True})]}
CASES["offset_rect"] = {"objects": BASE, "steps": [("offset", ["Rectangle"], {"vector": "0,-2,0"})]}
CASES["offset_circle"] = {"objects": BASE, "steps": [("offset", ["Circle"], {"radius": 5})]}
CASES["chain"] = {"objects": BASE, "steps": [
    ("move", ["Rectangle"], {"vector": "0,10,0"}), ("rotate", ["Rectangle"], {"angle": 90}),
    ("scale", ["Rectangle"], {"vector": "2,2,1"})]}

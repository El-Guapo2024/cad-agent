"""Runs inside freecadcmd for make.py: each case of $SKETCHTEXT_CASES done as Sketcher_CreateText and
EditTextDialog do it (DrawSketchHandlerText::executeCommands, EditTextDialog::on_buttonBox_accepted): the handle line
added as construction, Sketcher.Constraint('Text', [handle, 0], text, font, isHeight), setTextAndFont; then the
case's edits (setTextAndFont again, constraints on the handle) with a recompute after each. Writes the sketch after
every step to $SKETCHTEXT_ANSWERS. Not a test; make.py starts it."""
import html
import json
import os
import re
import sys
import traceback

import FreeCAD
import Part
import Sketcher

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "sketcher"))
from freecad_side_geo import part, read  # noqa: E402  (the sketcher golden's builders)

DIMENSIONAL = ("Distance", "DistanceX", "DistanceY", "Radius", "Diameter", "Angle")


def constraint_out(c):
    """A constraint's fields from its Content: every element, and a Text's MetaData."""
    a = dict(re.findall(r'(\w+)="([^"]*)"', c.Content))
    ids = [int(x) for x in a.get("ElementIds", "").split()]
    pos = [int(x) for x in a.get("ElementPositions", "").split()]
    d = {"type": c.Type, "elements": [v for e in zip(ids, pos) for v in e]}
    if c.Type == "Text":
        meta = json.loads(html.unescape(a["MetaData"]))
        d.update(text=meta.get("text"), font=meta.get("font"), is_text_height=meta.get("isTextHeight", True))
    if c.Type in DIMENSIONAL:
        d["value"] = c.Value
    return d


def state(sk):
    return {"geometry": [dict(read(g), construction=sk.getConstruction(i)) for i, g in enumerate(sk.Geometry)],
            "constraints": [constraint_out(c) for c in sk.Constraints]}


def run(doc, case):
    sk = doc.addObject("Sketcher::SketchObject", "Sketch")
    for g in case.get("before", []):
        sk.addGeometry(part(g), bool(g.get("construction", False)))
    (x1, y1), (x2, y2) = case["p1"], case["p2"]
    sk.addGeometry(Part.LineSegment(FreeCAD.Vector(x1, y1, 0), FreeCAD.Vector(x2, y2, 0)), True)
    handle = len(sk.Geometry) - 1
    sk.addConstraint(Sketcher.Constraint("Text", [handle, 0], case["text"], case["font"], case["height"]))
    sk.setTextAndFont(len(sk.Constraints) - 1, case["text"], case["font"], case["height"], case["construction"])
    doc.recompute()
    out = [state(sk)]
    for e in case.get("edits", []):
        if e["op"] == "set":                            # EditTextDialog: setTextAndFont(index, text, font, h, c)
            sk.setTextAndFont(e["index"], e["text"], e["font"], e["height"], e["construction"])
        elif e["op"] == "geometry":                    # geometry drawn after the text
            sk.addGeometry(part(e["geo"]), bool(e["geo"].get("construction", False)))
        elif e["op"] == "constraint":                  # a constraint on the handle; the solve moves the text
            args = list(e["args"]) + ([float(e["value"])] if "value" in e else [])
            sk.addConstraint(Sketcher.Constraint(e["type"], *args))
        doc.recompute()
        out.append(state(sk))
    return out


cases = json.load(open(os.environ["SKETCHTEXT_CASES"]))
answers = []
for case in cases:
    doc = FreeCAD.newDocument("sketchtext_golden")
    try:
        answers.append({"steps": run(doc, case)})
    except Exception:
        answers.append({"error": traceback.format_exc()})
    finally:
        FreeCAD.closeDocument(doc.Name)
json.dump(answers, open(os.environ["SKETCHTEXT_ANSWERS"], "w"))

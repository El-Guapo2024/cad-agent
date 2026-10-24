"""Runs inside freecadcmd for make.py: each case of $SKETCHXFORM_CASES is a sketch and one of SketchObject's transform
operations (addSymmetric, addCopy, addMove, addRectangularArray, removeAxesAlignment), done in a
Sketcher::SketchObject; writes the sketch before it (as FreeCAD solved it on adding the constraints) and the geometry
and constraints after it to $SKETCHXFORM_ANSWERS. Not a test; make.py starts it."""
import json
import os
import re
import sys
import traceback

import FreeCAD
import Sketcher

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sketcher"))
from freecad_side_geo import part, read  # noqa: E402  (the sketcher golden's builders)

V = FreeCAD.Vector
ALIGNMENTS = {1: "EllipseMajorDiameter", 2: "EllipseMinorDiameter", 3: "EllipseFocus1", 4: "EllipseFocus2",
              5: "HyperbolaMajor", 6: "HyperbolaMinor", 7: "HyperbolaFocus", 8: "ParabolaFocus",
              9: "BSplineControlPoint", 10: "BSplineKnotPoint", 11: "ParabolaFocalAxis"}
DIMENSIONAL = ("Distance", "DistanceX", "DistanceY", "Radius", "Diameter", "Angle", "Weight")


def constraint_out(c):
    """Every field of a constraint, from its Content (the Python attributes leave out the alignment)."""
    a = dict(re.findall(r'(\w+)="([^"]*)"', c.Content))
    d = {"type": c.Type, "elements": [c.First, c.FirstPos, c.Second, c.SecondPos, c.Third, c.ThirdPos],
         "name": c.Name, "driving": bool(c.Driving)}
    if c.Type == "InternalAlignment":
        d["alignment"] = ALIGNMENTS.get(int(a.get("InternalAlignmentType", 0)), "Undef")
        d["index"] = int(a.get("InternalAlignmentIndex", -1))
    if c.Type in DIMENSIONAL:
        d["value"] = c.Value
    elif c.Type in ("Tangent", "Perpendicular"):
        d["lock"] = c.Value  # AutoLockTangencyAndPerpty's angle (the port leaves it to the solver)
    if "Orientation" in a:
        d["orientation"] = int(a["Orientation"])
    return d


def python_args(c):
    return list(c)


def state(sk):
    return {"geometry": [read(g) for g in sk.Geometry],
            "constructions": [sk.getConstruction(i) for i in range(sk.GeometryCount)],
            "constraints": [constraint_out(c) for c in sk.Constraints]}


def run(case):
    doc = FreeCAD.newDocument("sketchxform_golden")
    try:
        sk = doc.addObject("Sketcher::SketchObject", "Sketch")
        for g in case["geometry"]:
            sk.addGeometry(part(g), bool(g.get("construction", False)))
        if case["constraints"]:
            sk.addConstraint([Sketcher.Constraint(*python_args(c)) for c in case["constraints"]])
        for i in case.get("reference", []):
            sk.setDriving(i, False)
        for i, name in case.get("names", {}).items():
            sk.renameConstraint(int(i), name)
        for g in case.get("expose", []):
            sk.exposeInternalGeometry(g)
        before = state(sk)
        op, args = case["op"]
        try:
            if op == "symmetric":
                ids, ref, pos = args
                sk.addSymmetric(ids, ref, pos)
            elif op == "copy":
                ids, v, clone = args
                sk.addCopy(ids, V(v[0], v[1], 0), clone)
            elif op == "move":
                ids, v = args
                sk.addMove(ids, V(v[0], v[1], 0))
            elif op == "array":
                ids, v, clone, rows, cols, disp, perp = args
                sk.addRectangularArray(ids, V(v[0], v[1], 0), clone, rows, cols, disp, perp)
            elif op == "removeAxes":
                sk.removeAxesAlignment(args[0])
            ok = True
        except Exception as e:  # FreeCAD refuses the operation
            ok = f"{type(e).__name__}: {e}"
        return {"ok": ok, "input": before, **state(sk)}
    finally:
        FreeCAD.closeDocument(doc.Name)


cases = json.load(open(os.environ["SKETCHXFORM_CASES"]))
answers = []
for case in cases:
    try:
        answers.append(run(case))
    except Exception:
        answers.append({"error": traceback.format_exc()})
json.dump(answers, open(os.environ["SKETCHXFORM_ANSWERS"], "w"))

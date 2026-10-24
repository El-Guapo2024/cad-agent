"""Runs inside freecadcmd for make.py: each case of $SKETCHOPS_CASES is a sketch and one of SketchObject's editing
operations (trim, split, extend, fillet), done in a Sketcher::SketchObject; writes the geometry and constraints after it
to $SKETCHOPS_ANSWERS. Not a test; make.py starts it."""
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


def constraint_out(c):
    """Every field of a constraint, from its Content (the Python attributes leave out the alignment)."""
    a = dict(re.findall(r'(\w+)="([^"]*)"', c.Content))
    d = {"type": c.Type, "elements": [c.First, c.FirstPos, c.Second, c.SecondPos, c.Third, c.ThirdPos]}
    if c.Type == "InternalAlignment":
        d["alignment"] = ALIGNMENTS.get(int(a.get("InternalAlignmentType", 0)), "Undef")
        d["index"] = int(a.get("InternalAlignmentIndex", -1))
    if c.Type in ("Distance", "DistanceX", "DistanceY", "Radius", "Diameter", "Angle", "Weight"):
        d["value"] = c.Value
    return d


def python_args(c):
    if isinstance(c, list):
        return c
    args = [c["type"], *c["args"]]
    if "value" in c:
        args.append(float(c["value"]))
    return args


def run(case):
    doc = FreeCAD.newDocument("sketchops_golden")
    try:
        sk = doc.addObject("Sketcher::SketchObject", "Sketch")
        for g in case["geometry"]:
            sk.addGeometry(part(g), bool(g.get("construction", False)))
        if case["constraints"]:
            sk.addConstraint([Sketcher.Constraint(*python_args(c)) for c in case["constraints"]])
        op, args = case["op"]
        try:
            if op == "trim":
                g, p, axes = args
                sk.trim(g, V(p[0], p[1], 0), axes)
            elif op == "split":
                g, p = args
                sk.split(g, V(p[0], p[1], 0))
            elif op == "extend":
                g, inc, pos = args
                sk.extend(g, inc, pos)
            elif op == "fillet":
                g1, g2, r1, r2, radius, trim, corner, chamfer = args
                sk.fillet(g1, g2, V(r1[0], r1[1], 0), V(r2[0], r2[1], 0), radius, trim, corner, chamfer)
            elif op == "fillet_point":
                g, pos, radius, trim, corner, chamfer = args
                sk.fillet(g, pos, radius, trim, corner, chamfer)
            ok = True
        except Exception as e:  # FreeCAD refuses the operation
            ok = f"{type(e).__name__}: {e}"
        return {"ok": ok, "geometry": [read(g) for g in sk.Geometry],
                "constructions": [sk.getConstruction(i) for i in range(sk.GeometryCount)],
                "constraints": [constraint_out(c) for c in sk.Constraints]}
    finally:
        FreeCAD.closeDocument(doc.Name)


cases = json.load(open(os.environ["SKETCHOPS_CASES"]))
answers = []
for case in cases:
    try:
        answers.append(run(case))
    except Exception:
        answers.append({"error": traceback.format_exc()})
json.dump(answers, open(os.environ["SKETCHOPS_ANSWERS"], "w"))

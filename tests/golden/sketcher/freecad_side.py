"""Runs inside freecadcmd for make.py: solves every case of $SKETCHER_CASES in a Sketcher::SketchObject
and writes FreeCAD's answers to $SKETCHER_ANSWERS. Not a test; make.py starts it."""
import json
import os
import re
import traceback

import FreeCAD
import Part
import Sketcher

V = FreeCAD.Vector


def python_args(c):
    """A constraint of the solver's JSON as Sketcher.Constraint's argument list."""
    if isinstance(c, list):
        return c
    args = [c["type"], *c["args"]]
    if "value" in c:
        args.append(float(c["value"]))
    if "active" in c or "driving" in c:
        args += [bool(c.get("active", True)), bool(c.get("driving", True))]
    return args


def part(g):
    t = g["type"]
    if t == "Point":
        return Part.Point(V(g["at"][0], g["at"][1], 0))
    if t == "LineSegment":
        return Part.LineSegment(V(*g["start"], 0), V(*g["end"], 0))
    if t == "Circle":
        return Part.Circle(V(*g["center"], 0), V(0, 0, 1), g["radius"])
    if t == "ArcOfCircle":
        circle = Part.Circle(V(*g["center"], 0), V(0, 0, 1), g["radius"])
        return Part.ArcOfCircle(circle, g["start_angle"], g["end_angle"])
    if t in ("Ellipse", "ArcOfEllipse"):
        e = Part.Ellipse(V(*g["center"], 0), g["major_radius"], g["minor_radius"])
        e.XAxis = V(*g.get("x_axis", [1, 0]), 0)
        return e if t == "Ellipse" else Part.ArcOfEllipse(e, g["start_angle"], g["end_angle"])
    if t == "ArcOfHyperbola":
        h = Part.Hyperbola()
        h.Location = V(*g["center"], 0)
        h.MajorRadius = g["major_radius"]
        h.MinorRadius = g["minor_radius"]
        h.XAxis = V(*g.get("x_axis", [1, 0]), 0)
        return Part.ArcOfHyperbola(h, g["start_angle"], g["end_angle"])
    if t == "ArcOfParabola":
        p = Part.Parabola()
        p.Location = V(*g["center"], 0)
        p.Focal = g["focal"]
        p.XAxis = V(*g.get("x_axis", [1, 0]), 0)
        return Part.ArcOfParabola(p, g["start_angle"], g["end_angle"])
    if t == "BSplineCurve":
        return Part.BSplineCurve([V(*q, 0) for q in g["poles"]], g["mults"], g["knots"], g.get("periodic", False),
                                 g["degree"], g.get("weights"))
    raise ValueError(t)


def xy(v):
    return [v.x, v.y]


def read(g):
    t = type(g).__name__
    if t == "Point":
        return {"type": "Point", "at": [g.X, g.Y]}
    if t == "LineSegment":
        return {"type": "LineSegment", "start": xy(g.StartPoint), "end": xy(g.EndPoint)}
    if t == "Circle":
        return {"type": "Circle", "center": xy(g.Center), "radius": g.Radius}
    if t == "ArcOfCircle":
        return {"type": "ArcOfCircle", "center": xy(g.Center), "radius": g.Radius,
                "start_angle": g.FirstParameter, "end_angle": g.LastParameter,
                "start_point": xy(g.StartPoint), "end_point": xy(g.EndPoint)}
    if t in ("Ellipse", "ArcOfEllipse", "ArcOfHyperbola", "ArcOfParabola"):
        d = {"type": t, "center": xy(g.Location)}
        if t == "ArcOfParabola":
            d["focal"] = g.Focal
        else:
            d["major_radius"], d["minor_radius"] = g.MajorRadius, g.MinorRadius
        d["x_axis"] = xy(g.XAxis)
        if t != "Ellipse":
            d.update({"start_angle": g.FirstParameter, "end_angle": g.LastParameter,
                      "start_point": xy(g.StartPoint), "end_point": xy(g.EndPoint)})
        return d
    if t == "BSplineCurve":
        return {"type": t, "poles": [xy(q) for q in g.getPoles()], "weights": list(g.getWeights()),
                "knots": list(g.getKnots()), "mults": list(g.getMultiplicities()), "degree": g.Degree,
                "periodic": g.isPeriodic()}
    return {"type": t}


ALIGNMENTS = {1: "EllipseMajorDiameter", 2: "EllipseMinorDiameter", 3: "EllipseFocus1", 4: "EllipseFocus2",
              5: "HyperbolaMajor", 6: "HyperbolaMinor", 7: "HyperbolaFocus", 8: "ParabolaFocus",
              9: "BSplineControlPoint", 10: "BSplineKnotPoint", 11: "ParabolaFocalAxis"}


def constraint_args(c):
    """A constraint FreeCAD made (exposeInternalGeometry) as Sketcher.Constraint's argument list."""
    attrs = dict(re.findall(r'(\w+)="([^"]*)"', c.Content))
    if c.Type == "InternalAlignment":
        kind = int(attrs["InternalAlignmentType"])
        name = "InternalAlignment:" + ALIGNMENTS[kind]
        if kind in (1, 2, 5, 6, 11):
            return [name, c.First, c.Second]
        if kind in (3, 4, 7, 8):
            return [name, c.First, c.FirstPos, c.Second]
        return [name, c.First, c.FirstPos, c.Second, int(attrs["InternalAlignmentIndex"])]
    if c.Type == "Equal":
        return ["Equal", c.First, c.Second]
    if c.Type == "Weight":
        return ["Weight", c.First, c.Value]
    raise ValueError(f"constraint {c.Type} from exposeInternalGeometry")


def state(sk):
    return {
        "geometry": [read(g) for g in sk.Geometry],
        "constructions": [sk.getConstruction(i) for i in range(sk.GeometryCount)],
        "values": [c.Value for c in sk.Constraints],
    }


def run(case):
    doc = FreeCAD.newDocument("sketcher_golden")
    try:
        sk = doc.addObject("Sketcher::SketchObject", "Sketch")
        for g in case["geometry"]:
            sk.addGeometry(part(g), bool(g.get("construction", False)))
        if "expose" in case:
            # make.py's first pass: the internal geometry exposeInternalGeometry adds, as the
            # Sketcher's tools add it, written back as a case
            for geo in case["expose"]:
                sk.exposeInternalGeometry(geo)
            return {"geometry": [{**read(g), "construction": sk.getConstruction(i)}
                                 for i, g in enumerate(sk.Geometry)],
                    "constraints": [constraint_args(c) for c in sk.Constraints]}
        try:
            sk.addConstraint([Sketcher.Constraint(*python_args(c)) for c in case["constraints"]])
        except Exception as e:  # invalid indices or arguments
            return {"error": f"{type(e).__name__}: {e}"}
        status = sk.solve()
        out = {
            "status": status,
            "dof": sk.DoF,
            "conflicting": list(sk.ConflictingConstraints),
            "redundant": list(sk.RedundantConstraints),
            "partially_redundant": list(sk.PartiallyRedundantConstraints),
            "malformed": list(sk.MalformedConstraints),
            **state(sk),
            "drags": [],
        }
        for d in case.get("drags", []):
            try:
                sk.moveGeometry(d["geo"], d["pos"], V(d["to"][0], d["to"][1], 0), int(d.get("relative", False)))
                ok = True
            except ValueError:
                ok = False
            out["drags"].append({"ok": ok, **state(sk)})
        return out
    finally:
        FreeCAD.closeDocument(doc.Name)


cases = json.load(open(os.environ["SKETCHER_CASES"]))
answers = []
for case in cases:
    try:
        answers.append(run(case))
    except Exception:
        answers.append({"error": traceback.format_exc()})
json.dump(answers, open(os.environ["SKETCHER_ANSWERS"], "w"))

"""Runs inside freecadcmd for make.py: each case of $SKETCHCURVES_CASES is a sketch and one of the Sketcher's curve
tools, done as the tool's command does it in a Sketcher::SketchObject (CommandSketcherBSpline.cpp,
DrawSketchHandlerBSpline.h, the Trim, Split and Fillet tools); writes the geometry and constraints after it to
$SKETCHCURVES_ANSWERS. Not a test; make.py starts it."""
import json
import math
import os
import re
import sys
import traceback

import FreeCAD
import Part
import Sketcher

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "sketcher"))
from freecad_side_geo import ALIGNMENTS, part, read  # noqa: E402  (the sketcher golden's builders)

V = FreeCAD.Vector
TWO_PI = 2 * math.pi


def read_ccw(g):
    """read(), an arc of circle's angles as the Sketcher reads them (GeomArcOfCircle::getRange with emulateCCWXY):
    counter-clockwise about +Z from +X, its start in [0, 2pi), whatever the circle's own X axis and normal."""
    d = read(g)
    if type(g).__name__ == "ArcOfCircle":
        a, b = (g.StartPoint, g.EndPoint) if g.Axis.z > 0 else (g.EndPoint, g.StartPoint)
        c = g.Center
        a1 = math.atan2(a.y - c.y, a.x - c.x)
        a1 -= math.floor(a1 / TWO_PI) * TWO_PI
        d.update({"start_angle": a1, "end_angle": a1 + (g.LastParameter - g.FirstParameter),
                  "start_point": [a.x, a.y], "end_point": [b.x, b.y]})
    return d


def constraint_out(c):
    """Every field of a constraint, from its Content (as tests/golden/sketchops/freecad_side.py reads it)."""
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


def by_tag(sk, tag):
    for i, g in enumerate(sk.Geometry):
        if g.Tag == tag:
            return i
    return -1


def bspline_by_knots(sk, points, multiplicities, periodic, construction):
    """DrawSketchHandlerBSpline::executeCommands, Knots method, as its Python commands run (no autoconstraints)."""
    first = sk.GeometryCount
    ids = []
    for p in points:
        ids.append(sk.addGeometry(Part.Point(V(float("%f" % p[0]), float("%f" % p[1]), 0)), True))
    degree = 3
    mults = list(multiplicities)
    if not periodic:
        mults[0] = degree + 1
        mults[-1] = degree + 1
    g6 = lambda v: float("%.6g" % v)  # noqa: E731  (C++'s default stream output)
    pts = [V(g6(x), g6(y), 0) for x, y in points]
    pieces = [[pts[0]]]
    for i in range(1, len(pts) - 1):
        pieces[-1].append(pts[i])
        if mults[i] >= degree:
            pieces.append([pts[i]])
    pieces[-1].append(pts[-1])
    between = [0 < i < len(pts) - 1 and mults[i - 1] >= degree and mults[i + 1] >= degree for i in range(len(pts))]
    fpoles, fknots, fmults = [], [], []
    for n, piece in enumerate(pieces):
        b = Part.BSplineCurve()
        b.interpolate(piece, PeriodicFlag=periodic)
        b.increaseDegree(degree)
        if n == 0:
            fpoles += b.getPoles()
            fknots += b.getKnots()
            fmults += b.getMultiplicities()
        else:
            fpoles += b.getPoles()[1:]
            fknots += [fknots[-1] + k for k in b.getKnots()[1:]]
            fmults[-1] = 3
            fmults += b.getMultiplicities()[1:]
    cur = sk.addGeometry(Part.BSplineCurve(fpoles, fmults, fknots, periodic, degree, None, False), construction)
    cons = []
    knot = 0
    for i in range(len(points)):
        if between[i]:
            cons.append(Sketcher.Constraint("PointOnObject", ids[i], 1, cur))
        else:
            cons.append(Sketcher.Constraint("InternalAlignment:Sketcher::BSplineKnotPoint", ids[i], 1, cur, knot))
            if 1 < mults[i] < degree:
                sk.modifyBSplineKnotMultiplicity(cur, knot + 1, mults[i] - 1)
            knot += 1
    sk.addConstraint(cons)
    sk.exposeInternalGeometry(cur)


def run_op(sk, op, args):
    if op == "convert":
        for g in args[0]:
            sk.convertToNURBS(g)
        for g in args[0]:
            sk.exposeInternalGeometry(g)
    elif op == "degree_up":
        sk.increaseBSplineDegree(args[0])
        sk.exposeInternalGeometry(args[0])
    elif op == "degree_down":
        sk.decreaseBSplineDegree(args[0])
    elif op in ("knot_mult", "insert_knot"):
        g = args[0]
        tag = sk.Geometry[g].Tag
        if op == "knot_mult":
            sk.modifyBSplineKnotMultiplicity(g, args[1], args[2])
        else:
            sk.insertBSplineKnot(g, args[1], args[2])
        ng = by_tag(sk, tag)
        if ng >= 0:
            sk.exposeInternalGeometry(ng)
    elif op == "join":
        sk.join(*args)
    elif op == "trim":
        g, p, axes = args
        sk.trim(g, V(p[0], p[1], 0), axes)
    elif op == "split":
        g, p = args
        sk.split(g, V(p[0], p[1], 0))
    elif op == "fillet":
        g1, g2, r1, r2, radius, trim, corner, chamfer = args
        sk.fillet(g1, g2, V(r1[0], r1[1], 0), V(r2[0], r2[1], 0), radius, trim, corner, chamfer)
    elif op == "bspline_by_knots":
        bspline_by_knots(sk, *args)
    elif op == "carbon_copy":
        geometry, constraints, self_pl, src_pl, construction = args
        P = lambda pl: FreeCAD.Placement(V(*pl["base"]), FreeCAD.Rotation(*pl["rotation"]))  # noqa: E731
        sk.Placement = P(self_pl)
        src = sk.Document.addObject("Sketcher::SketchObject", "Source")
        src.Placement = P(src_pl)
        for g in geometry:
            src.addGeometry(part(g), bool(g.get("construction", False)))
        if constraints:
            src.addConstraint([Sketcher.Constraint(*python_args(c)) for c in constraints])
        # CarbonCopySelection::allow without Ctrl or Alt held: neither another body nor unaligned sketches
        sk.setAllowUnaligned(False)
        sk.carbonCopy("Source", construction)
    else:
        raise ValueError(op)


def run(case):
    doc = FreeCAD.newDocument("sketchcurves_golden")
    try:
        sk = doc.addObject("Sketcher::SketchObject", "Sketch")
        for g in case["geometry"]:
            sk.addGeometry(part(g), bool(g.get("construction", False)))
        if case["constraints"]:
            sk.addConstraint([Sketcher.Constraint(*python_args(c)) for c in case["constraints"]])
        for g in case.get("expose", []):
            sk.exposeInternalGeometry(g)
        op, args = case["op"]
        try:
            run_op(sk, op, args)
            ok = True
        except Exception as e:  # FreeCAD refuses the operation
            ok = f"{type(e).__name__}: {e}"
        return {"ok": ok, "geometry": [read_ccw(g) for g in sk.Geometry],
                "constructions": [sk.getConstruction(i) for i in range(sk.GeometryCount)],
                "constraints": [constraint_out(c) for c in sk.Constraints]}
    finally:
        FreeCAD.closeDocument(doc.Name)


cases = json.load(open(os.environ["SKETCHCURVES_CASES"]))
answers = []
for case in cases:
    try:
        answers.append(run(case))
    except Exception:
        answers.append({"error": traceback.format_exc()})
json.dump(answers, open(os.environ["SKETCHCURVES_ANSWERS"], "w"))

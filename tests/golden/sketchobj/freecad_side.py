"""Runs inside freecadcmd for make.py: each case of $SKETCHOBJ_CASES (a sketch, or several, and a command: mirror,
merge, validate) done in Sketcher::SketchObjects as Sketcher/Gui/Command.cpp and TaskSketcherValidation.cpp do it;
writes what FreeCAD makes to $SKETCHOBJ_ANSWERS. Not a test; make.py starts it."""
import json
import os
import re
import sys
import traceback

import FreeCAD
import Sketcher

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "sketcher"))
from freecad_side_geo import ALIGNMENTS, part, read  # noqa: E402  (the sketcher golden's builders)

DIMENSIONAL = ("Distance", "DistanceX", "DistanceY", "Radius", "Diameter", "Angle", "Weight", "SnellsLaw")
REFS = {"X": (-1, 0), "Y": (-2, 0), "origin": (-1, 1)}


def constraint_out(c):
    """Every field of a constraint, from its Content (as tests/golden/sketchops/freecad_side.py reads it)."""
    a = dict(re.findall(r'(\w+)="([^"]*)"', c.Content))
    d = {"type": c.Type, "elements": [c.First, c.FirstPos, c.Second, c.SecondPos, c.Third, c.ThirdPos]}
    if c.Type == "InternalAlignment":
        d["alignment"] = ALIGNMENTS.get(int(a.get("InternalAlignmentType", 0)), "Undef")
        d["index"] = int(a.get("InternalAlignmentIndex", -1))
    if c.Type in DIMENSIONAL:
        d["value"] = c.Value
    return d


def build(doc, name, sketch):
    """A sketch from a case's geometry and constraints (feature_edit's dicts), recomputed (solved)."""
    sk = doc.addObject("Sketcher::SketchObject", name)
    for g in sketch["geometry"]:
        sk.addGeometry(part(g), bool(g.get("construction", False)))
    cs = []
    for c in sketch["constraints"]:
        args = [c["type"], *c["args"]] + ([float(c["value"])] if c["type"] in DIMENSIONAL else [])
        cs.append(Sketcher.Constraint(*args))
    if cs:
        sk.addConstraint(cs)
    for i, c in enumerate(sketch["constraints"]):
        if c.get("name"):
            sk.renameConstraint(i, c["name"])
        if c.get("driving") is False:
            sk.setDriving(i, False)
    doc.recompute()
    return sk


def state(sk):
    return {"geometry": [dict(read(g), construction=sk.getConstruction(i)) for i, g in enumerate(sk.Geometry)],
            "constraints": [dict(constraint_out(c), name=c.Name, driving=c.Driving) for c in sk.Constraints]}


def mirror(doc, case):
    """CmdSketcherMirrorSketch::activated for one sketch, through the Python API."""
    src = build(doc, "Sketch", case)
    out = {"source": state(src)}
    ref, pos = REFS[case["ref"]]
    tmp = doc.addObject("Sketcher::SketchObject", "Temp")
    n = len(src.Geometry)
    nc = len(src.Constraints)
    if n:
        tmp.addGeometry(src.Geometry)
    if nc:
        tmp.addConstraint(src.Constraints)
    tmp.addSymmetric(list(range(n)), ref, pos)
    geo = tmp.Geometry[n:]
    cons = tmp.Constraints[nc:]
    for c in cons:
        if c.First != -2000:
            c.First -= n
        if c.Second != -2000:
            c.Second -= n
        if c.Third != -2000:
            c.Third -= n
    m = doc.addObject("Sketcher::SketchObject", "MirroredSketch")
    if geo:
        m.addGeometry(geo)
    if cons:
        m.addConstraint(cons)
    out["mirrored"] = state(m)
    doc.recompute()
    out["solved"] = state(m)
    return out


def merge(doc, case):
    """CmdSketcherMergeSketches::activated (no external geometry), through the Python API."""
    srcs = [build(doc, f"Sketch{i}", s) for i, s in enumerate(case["sketches"])]
    out = {"sources": [state(s) for s in srcs]}
    m = doc.addObject("Sketcher::SketchObject", "Merged")
    base = 0
    for s in srcs:
        if s.Geometry:
            m.addGeometry(s.Geometry)
        cons = s.Constraints
        for c in cons:
            for k in ("First", "Second", "Third"):
                g = getattr(c, k)
                if g >= 0:
                    setattr(c, k, g + base)
        if cons:
            m.addConstraint(cons)
        base += len(s.Geometry)
    out["merged"] = state(m)
    doc.recompute()
    out["solved"] = state(m)
    return out


TOLERANCES = (1e-9, 1e-8, 1e-7, 1e-6, 1e-5, 1e-4, 1e-3, 1e-2)


def validate(doc, case):
    """The Sketch Validation panel's analysis and fixes."""
    sk = build(doc, "Sketch", case)
    out = {"source": state(sk), "missing": {}}
    for tol in TOLERANCES:
        for incl in (True, False):
            n = sk.detectMissingPointOnPointConstraints(tol, incl)
            out["missing"][f"{tol!r} {incl}"] = {"count": n, "list": [list(t) for t in sk.MissingPointOnPointConstraints]}
    out["open"] = [list(v)[:2] for v in sk.OpenVertices]
    out["valid"] = sk.evaluateConstraints()
    out["degenerated"] = sk.detectDegeneratedGeometries(1e-7)
    out["lock"] = sk.changeConstraintsLocking(True)
    out["unlock"] = sk.changeConstraintsLocking(False)
    # removeDegeneratedGeometries, on a copy of the sketch as solved
    dg = build(doc, "Degenerated", {"geometry": [{k: v for k, v in g.items() if k not in ("start_point", "end_point")}
                                                 for g in out["source"]["geometry"]],
                                    "constraints": case["constraints"]})
    dg.removeDegeneratedGeometries(1e-7)
    doc.recompute()
    out["removed"] = state(dg)
    # Fix (missing coincidences, the panel's defaults: 0.0001, construction ignored) on the sketch, then the recompute
    sk.detectMissingPointOnPointConstraints(1e-4, False)
    sk.makeMissingPointOnPointCoincident()
    doc.recompute()
    out["fixed"] = state(sk)
    return out


cases = json.load(open(os.environ["SKETCHOBJ_CASES"]))
answers = []
for case in cases:
    doc = FreeCAD.newDocument("sketchobj_golden")
    try:
        answers.append({"mirror": mirror, "merge": merge, "validate": validate}[case["kind"]](doc, case))
    except Exception:
        answers.append({"error": traceback.format_exc()})
    finally:
        FreeCAD.closeDocument(doc.Name)
json.dump(answers, open(os.environ["SKETCHOBJ_ANSWERS"], "w"))

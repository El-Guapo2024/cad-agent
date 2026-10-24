"""Runs inside freecadcmd for make.py: solves every case of $SKETCHER_CASES in a Sketcher::SketchObject
and writes FreeCAD's answers to $SKETCHER_ANSWERS. Not a test; make.py starts it."""
import json
import os
import sys
import traceback

import FreeCAD
import Sketcher

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from freecad_side_geo import constraint_args, part, read  # noqa: E402

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

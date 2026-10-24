"""Writes freecad.json: what FreeCAD's PartDesign builds from each body of dressup_cases.py, for
tests/test_feature_dressup.py to hold cad_agent/feature_dressup.py to.

    $FREECAD/freecadcmd tests/golden/dressup/make.py        (FREECAD: FreeCAD's bin folder, 26.3 at 3160daf1e2b6)

Run it from the repository's root. As tests/golden/feature/make.py: each case's FEATURES go to FreeCAD through
cad_agent.feature.to_freecad into a fresh document, which is recomputed. Recorded for the Body's shape: volume,
area, the optimal bounding box, the centre of mass, solids, faces and edges, each face's area and centre and each
edge's length and centre in FreeCAD's Face1, ... and Edge1, ... order; and the same lists for every solid feature
of the body ("bases"), so the names the cases use are checked to be FreeCAD's for each base. A case FreeCAD
refuses is recorded with its error.

FOLLOW cases: the body is built, its "edit" applied to the open document (so FreeCAD's topological naming sees
an edit, not a new body), recomputed, and each dress-up's Base recorded as FreeCAD then holds it.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.getcwd())
if not (ROOT / "cad_agent" / "feature.py").exists():
    sys.exit("run make.py from the repository's root")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "golden" / "dressup"))

import FreeCAD as App  # noqa: E402
import Part  # noqa: E402

from cad_agent import feature  # noqa: E402
from dressup_cases import CASES, FOLLOW  # noqa: E402


def r(x):
    return round(x, 9)


def elements(shape):
    faces = [[r(f.Area)] + [r(getattr(f.CenterOfMass, k)) for k in "xyz"] for f in shape.Faces]
    edges = [[r(e.Length)] + [r(getattr(e.CenterOfMass, k)) for k in "xyz"] for e in shape.Edges]
    return faces, edges


def measure(shape):
    solids = shape.Solids
    vol = sum(s.Volume for s in solids)
    com = [sum(getattr(s.CenterOfMass, k) * s.Volume for s in solids) / vol for k in "xyz"] if vol else [0, 0, 0]
    bb = shape.optimalBoundingBox(False, False)
    faces, edges = elements(shape)
    return {
        "volume": r(shape.Volume), "area": r(shape.Area),
        "bbox": [r(bb.XMin), r(bb.YMin), r(bb.ZMin), r(bb.XMax), r(bb.YMax), r(bb.ZMax)],
        "center_of_mass": [r(c) for c in com],
        "solids": len(solids), "faces": len(shape.Faces), "edges": len(shape.Edges), "valid": shape.isValid(),
        "face_list": faces, "edge_list": edges,
    }


def build(name, case):
    doc = App.newDocument(name)
    base = None
    if case.get("base"):
        _, p, s = case["base"]
        base = Part.makeBox(s[0], s[1], s[2], App.Vector(*p))
    body = feature.to_freecad(case["features"], case.get("params"), doc=doc, base=base)
    doc.recompute()
    return doc, body


def record(body):
    bad = [f"{o.Name}: {o.getStatusString()}" for o in body.Group if not o.isValid()]
    if bad:
        return {"error": "; ".join(bad)}
    out = measure(body.Shape)
    out["bases"] = {}
    for o in body.Group:
        if o.isDerivedFrom("PartDesign::Feature") and not o.Shape.isNull():
            f, e = elements(o.Shape)
            out["bases"][o.Name] = {"face_list": f, "edge_list": e}
    return out


out = {"freecad": ".".join(App.Version()[:3]) + " " + App.Version()[3], "cases": {}, "follow": {}}
for name, case in CASES.items():
    doc, body = build(name, case)
    out["cases"][name] = record(body)
    print(name, out["cases"][name].get("volume", out["cases"][name].get("error")))
    App.closeDocument(doc.Name)

for name, case in FOLLOW.items():
    doc, body = build(name, case)
    for op in case["edit"]:
        obj = doc.getObject(op[1])
        if op[0] == "reorder":
            g = obj.Geometry
            obj.Geometry = [g[i] for i in op[2]]
        elif op[0] == "set":
            setattr(obj, op[2], op[3])
        elif op[0] == "append_circle":
            obj.addGeometry(Part.Circle(App.Vector(op[2][0], op[2][1], 0), App.Vector(0, 0, 1), op[3]), False)
    doc.recompute()
    bases = {}
    for o in body.Group:
        if o.isDerivedFrom("PartDesign::DressUp"):
            b = o.Base
            bases[o.Name] = [b[0].Name, list(b[1])] if b else None
    out["follow"][name] = {"bases": bases, "result": record(body)}
    print(name, bases)
    App.closeDocument(doc.Name)

Path(ROOT / "tests" / "golden" / "dressup" / "freecad.json").write_text(json.dumps(out, indent=1) + "\n")
print(len(out["cases"]), "cases,", len(out["follow"]), "follow cases")

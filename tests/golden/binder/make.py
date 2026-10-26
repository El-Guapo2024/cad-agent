"""Writes freecad.json: what FreeCAD's PartDesign builds from each body of cases.py (a ShapeBinder in a Body), for
tests/test_feature_binder.py to hold cad_agent/feature.py to.

    $FREECAD/freecadcmd tests/golden/binder/make.py   (FREECAD: FreeCAD's bin folder, 26.3 at 3160daf1e2b6)

Run it from the repository's root. As tests/golden/feature/make.py: each case's FEATURES go to FreeCAD through
cad_agent.feature.to_freecad into a fresh document, it is recomputed and the Body, every ShapeBinder in it and every
sketch recorded. A binder is not a solid: its own Shape has a placement (ShapeBinder::execute sets it to
shape.getTransform()), its Support is the list groups of sub-elements getFilteredReferences reads, and the Body's Tip
is still the last solid feature.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.getcwd())
if not (ROOT / "cad_agent" / "feature.py").exists():
    sys.exit("run make.py from the repository's root")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "golden" / "binder"))

import FreeCAD as App  # noqa: E402

from cad_agent import feature  # noqa: E402
from cases import CASES  # noqa: E402


ORIGIN_TYPES = ("App::Line", "App::Plane", "App::Point")


def r(x):
    return round(x, 9) + 0.0                     # -0.0 is 0.0


def placement(pl):
    return [r(c) for c in (pl.Base.x, pl.Base.y, pl.Base.z, *pl.Rotation.toEulerAngles("YawPitchRoll"))]


def measure(shape):
    """A shape as the test measures it: kind, counts, size and placement; an infinite one has no bbox or area."""
    if shape.isNull():
        return {"null": True}
    m = {"type": shape.ShapeType, "solids": len(shape.Solids), "faces": len(shape.Faces),
         "edges": len(shape.Edges), "vertices": len(shape.Vertexes), "placement": placement(shape.Placement)}
    bb = shape.BoundBox
    corn = [bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax]
    if any(abs(c) > 1e99 for c in corn):
        m["infinite"] = True
        if shape.ShapeType == "Edge":                # the line's direction, the plane's normal
            m["axis"] = [r(c) for c in shape.Curve.Direction]
        elif shape.ShapeType == "Face":
            m["axis"] = [r(c) for c in shape.Surface.Axis]
    else:
        m.update({"bbox": [r(c) for c in corn], "area": r(shape.Area), "volume": r(shape.Volume)})
    return m


out = {"freecad": ".".join(App.Version()[:3]) + " " + App.Version()[3], "cases": {}}
for name, case in CASES.items():
    doc = App.newDocument(name)
    body = feature.to_freecad(case["features"], case.get("params"), doc=doc)
    doc.recompute()
    bad = [f"{o.Name}: {o.getStatusString()}" for o in body.Group if not o.isValid()]
    res = {"error": "; ".join(bad)} if bad else {}
    res["tip"] = body.Tip.Name if body.Tip else None
    res["binders"] = {}
    res["sketches"] = {}
    for o in body.Group:
        if o.TypeId == "PartDesign::ShapeBinder":
            res["binders"][o.Name] = {
                # an Origin feature by its Role, the name the FEATURES give it (FreeCAD's point is Origin001)
                "support": [[v.Role if v.TypeId in ORIGIN_TYPES else v.Name, list(s)] for v, s in o.Support],
                "trace_support": bool(o.TraceSupport),
                **measure(o.Shape),
            }
        elif o.TypeId == "Sketcher::SketchObject":
            res["sketches"][o.Name] = {"placement": placement(o.Placement), "solve": o.solve(), "dof": o.DoF}
    if "error" not in res:
        res["body"] = measure(body.Shape)
    out["cases"][name] = res
    print(name, res.get("error") or res.get("body", {}).get("volume"))
    App.closeDocument(doc.Name)

Path(ROOT / "tests" / "golden" / "binder" / "freecad.json").write_text(json.dumps(out, indent=1) + "\n")
print(len(out["cases"]), "cases")

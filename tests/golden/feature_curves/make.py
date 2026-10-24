"""Writes freecad.json: what FreeCAD's PartDesign builds from each body of cases.py (conics and B-splines), for
tests/test_feature_curves.py to hold cad_agent/feature.py to.

    $FREECAD/freecadcmd tests/golden/feature_curves/make.py   (FREECAD: FreeCAD's bin folder, 26.3 at 3160daf1e2b6)

Run it from the repository's root. As tests/golden/feature/make.py: each case's FEATURES go to FreeCAD through
cad_agent.feature.to_freecad into a fresh document, it is recomputed and the Body's shape recorded (volume,
area, optimal bounding box, centre of mass, solids, faces, edges, each face's area and centre). Each sketch's
geometry after the recompute (FreeCAD's solver ran on it) is recorded too, with its status, so the test can
check that FreeCAD left the stored geometry where it was: that it satisfies the constraints as FreeCAD sees them.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.getcwd())
if not (ROOT / "cad_agent" / "feature.py").exists():
    sys.exit("run make.py from the repository's root")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "golden" / "feature_curves"))

import FreeCAD as App  # noqa: E402

from cad_agent import feature  # noqa: E402
from cases import CASES  # noqa: E402


def r(x):
    return round(x, 9)


def xy(v):
    return [r(v.x), r(v.y)]


def read(g):
    """A sketch geometry as cad_agent.feature's as_dict() writes it (tests/golden/sketcher/freecad_side.py)."""
    t = type(g).__name__
    if t == "Point":
        return {"type": t, "at": [r(g.X), r(g.Y)]}
    if t == "LineSegment":
        return {"type": t, "start": xy(g.StartPoint), "end": xy(g.EndPoint)}
    if t == "Circle":
        return {"type": t, "center": xy(g.Center), "radius": r(g.Radius)}
    if t == "ArcOfCircle":
        return {"type": t, "center": xy(g.Center), "radius": r(g.Radius), "start_angle": r(g.FirstParameter),
                "end_angle": r(g.LastParameter)}
    if t in ("Ellipse", "ArcOfEllipse", "ArcOfHyperbola", "ArcOfParabola"):
        d = {"type": t, "center": xy(g.Location)}
        if t == "ArcOfParabola":
            d["focal"] = r(g.Focal)
        else:
            d["major_radius"], d["minor_radius"] = r(g.MajorRadius), r(g.MinorRadius)
        d["x_axis"] = xy(g.XAxis)
        if t != "Ellipse":
            d.update({"start_angle": r(g.FirstParameter), "end_angle": r(g.LastParameter)})
        return d
    if t == "BSplineCurve":
        return {"type": t, "poles": [xy(q) for q in g.getPoles()], "weights": [r(w) for w in g.getWeights()],
                "knots": [r(k) for k in g.getKnots()], "mults": list(g.getMultiplicities()), "degree": g.Degree,
                "periodic": g.isPeriodic()}
    return {"type": t}


def measure(shape):
    solids = shape.Solids
    vol = sum(s.Volume for s in solids)
    com = [sum(getattr(s.CenterOfMass, k) * s.Volume for s in solids) / vol for k in "xyz"]
    bb = shape.optimalBoundingBox(False, False)
    return {
        "volume": r(shape.Volume), "area": r(shape.Area),
        "bbox": [r(bb.XMin), r(bb.YMin), r(bb.ZMin), r(bb.XMax), r(bb.YMax), r(bb.ZMax)],
        "center_of_mass": [r(c) for c in com],
        "solids": len(solids), "faces": len(shape.Faces), "edges": len(shape.Edges), "valid": shape.isValid(),
        "face_list": [[r(f.Area)] + [r(getattr(f.CenterOfMass, k)) for k in "xyz"] for f in shape.Faces],
    }


out = {"freecad": ".".join(App.Version()[:3]) + " " + App.Version()[3], "cases": {}}
for name, case in CASES.items():
    doc = App.newDocument(name)
    body = feature.to_freecad(case["features"], case.get("params"), doc=doc)
    doc.recompute()
    bad = [f"{o.Name}: {o.getStatusString()}" for o in body.Group if not o.isValid()]
    if bad:
        res = {"error": "; ".join(bad)}
    else:
        res = measure(body.Shape)
    res["sketches"] = {}
    for o in body.Group:
        if o.TypeId == "Sketcher::SketchObject":
            geometry = [read(g) for g in o.Geometry]           # as the recompute's solve left it
            res["sketches"][o.Name] = {"geometry": geometry, "solve": o.solve(), "dof": o.DoF,
                                       "malformed": list(o.MalformedConstraints),
                                       "conflicting": list(o.ConflictingConstraints),
                                       "redundant": list(o.RedundantConstraints)}
    out["cases"][name] = res
    print(name, res.get("volume", res.get("error")))
    App.closeDocument(doc.Name)

Path(ROOT / "tests" / "golden" / "feature_curves" / "freecad.json").write_text(json.dumps(out, indent=1) + "\n")
print(len(out["cases"]), "cases")

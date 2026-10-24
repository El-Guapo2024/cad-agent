"""Writes bodies.json: what FreeCAD's PartDesign builds from each body of bodies.py, for tests/test_feature_attach.py.

    $FREECAD/freecadcmd tests/golden/attach/make_bodies.py     (FREECAD: FreeCAD's bin folder, 26.3 at 3160daf1e2b6)

Run it from the repository's root. Each case goes to FreeCAD through cad_agent.feature.to_freecad (the same lines
a part file holds) and is recomputed. Recorded: the Body's shape as tests/golden/feature/make.py measures it;
each sketch's Placement (AttachExtension's result), its ExternalGeo after the two axes and its Geometry after
FreeCAD's solve; each datum's Placement. A placement is its position and quaternion. A case FreeCAD refuses is
recorded with its error.

Each case runs in a freecadcmd of its own (this script starts one per case, ATTACH_CASE naming it):
Part::Feature::getTopoShape (PartFeature.cpp) keeps one shape for every App::Line in a static, made from the
first App::Line it is asked for, so a Part::DatumLine (along Z) and an origin's or a local coordinate system's
axis (along X) shaped in one session share an edge, and the later one's answer depends on what came first.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.getcwd())
HERE = ROOT / "tests" / "golden" / "attach"
if not (HERE / "make_bodies.py").exists():
    sys.exit("run make_bodies.py from the repository's root")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tests" / "golden" / "feature"))

import FreeCAD as App  # noqa: E402

from bodies import CASES  # noqa: E402
from cad_agent import feature  # noqa: E402


def r(x):
    return round(x, 9)


def measure(shape):
    """tests/golden/feature/make.py's measure (copied: importing that script would run it)."""
    solids = shape.Solids
    vol = sum(s.Volume for s in solids)
    com = [sum(getattr(s.CenterOfMass, k) * s.Volume for s in solids) / vol for k in "xyz"]
    bb = shape.optimalBoundingBox(False, False)
    return {
        "volume": r(shape.Volume), "area": r(shape.Area),
        "bbox": [r(bb.XMin), r(bb.YMin), r(bb.ZMin), r(bb.XMax), r(bb.YMax), r(bb.ZMax)],
        "center_of_mass": [r(c) for c in com],
        "solids": len(solids), "faces": len(shape.Faces), "valid": shape.isValid(),
        "face_list": [[r(f.Area)] + [r(getattr(f.CenterOfMass, k)) for k in "xyz"] for f in shape.Faces],
    }


def place(p):
    return [list(p.Base), list(p.Rotation.Q)]


def geo(g):
    t = g.TypeId
    if t == "Part::GeomLineSegment":
        return {"type": "LineSegment", "start": [g.StartPoint.x, g.StartPoint.y], "end": [g.EndPoint.x, g.EndPoint.y]}
    if t == "Part::GeomCircle":
        return {"type": "Circle", "center": [g.Location.x, g.Location.y], "radius": g.Radius}
    if t == "Part::GeomArcOfCircle":
        return {"type": "ArcOfCircle", "center": [g.Location.x, g.Location.y], "radius": g.Radius,
                "start": [g.StartPoint.x, g.StartPoint.y], "end": [g.EndPoint.x, g.EndPoint.y],
                "axis_z": g.Axis.z}
    if t == "Part::GeomPoint":
        return {"type": "Point", "at": [g.X, g.Y]}
    return {"type": t}


ONLY = os.environ.get("ATTACH_CASE")
if not ONLY:
    import subprocess
    import tempfile
    exe = os.path.join(App.getHomePath(), "bin", "freecadcmd")
    out = {"freecad": ".".join(App.Version()[:3]) + " " + App.Version()[3], "cases": {}}
    with tempfile.TemporaryDirectory() as tmp:
        for name in CASES:
            part = os.path.join(tmp, name + ".json")
            subprocess.run([exe, __file__], env={**os.environ, "ATTACH_CASE": name, "ATTACH_OUT": part},
                           check=True, capture_output=True)
            out["cases"][name] = json.loads(Path(part).read_text())
            rec = out["cases"][name]
            print(name, rec.get("volume", rec.get("error")))
    (HERE / "bodies.json").write_text(json.dumps(out, indent=1) + "\n")
    print(len(out["cases"]), "cases")
    sys.stdout.flush()
    sys.exit(0)

out = {"cases": {}}
for name, case in [(ONLY, CASES[ONLY])]:
    doc = App.newDocument(name)
    body = feature.to_freecad(case["features"], case.get("params"), doc=doc)
    doc.recompute()
    bad = [f"{o.Name}: {o.getStatusString()}" for o in body.Group if not o.isValid()]
    rec = {"error": "; ".join(bad)} if bad else measure(body.Shape)
    rec["objects"] = {}
    for o in body.Group:
        ob = {"type": o.TypeId, "placement": place(o.Placement)}
        if hasattr(o, "MapMode"):
            ob["map_mode"] = o.MapMode
        if o.TypeId == "Sketcher::SketchObject":
            ob["external"] = [geo(g) for g in o.ExternalGeo[2:]]
            ob["geometry"] = [geo(g) for g in o.Geometry]
            ob["dof"] = o.solve() if not bad else None
        rec["objects"][o.Name] = ob
    App.closeDocument(doc.Name)
    Path(os.environ["ATTACH_OUT"]).write_text(json.dumps(rec))

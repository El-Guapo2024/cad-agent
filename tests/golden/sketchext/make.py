"""Writes freecad.json: what FreeCAD's Sketcher makes of each body of cases.py, for tests/test_sketch_ext.py.

    $FREECAD/freecadcmd tests/golden/sketchext/make.py     (FREECAD: FreeCAD's bin folder, 26.3 at 3160daf1e2b6)

Run it from the repository's root. Each case goes to FreeCAD through cad_agent.feature.to_freecad (the same lines a
part file holds: a reference's type is addExternal's intersection flag) and is recomputed, in a freecadcmd of its
own (as tests/golden/attach/make_bodies.py, whose geometry record this is). Recorded for Sketch001: ExternalTypes,
its ExternalGeo after the two axes (an arc's axis_z -1 is a reversed arc), its Geometry after FreeCAD's solve, the
degrees of freedom and the constraints' elements. port_reversedExternalArcs is not in SketchObject's Python: Swap
Endpoints in Constraints is checked against the GUI (scripts/sketchcheck.mjs --suite ext).
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.getcwd())
HERE = ROOT / "tests" / "golden" / "sketchext"
if not (HERE / "make.py").exists():
    sys.exit("run make.py from the repository's root")
sys.path.insert(0, str(ROOT))

import importlib.util  # noqa: E402

import FreeCAD as App  # noqa: E402

_spec = importlib.util.spec_from_file_location("sketchext_cases", HERE / "cases.py")
_cases = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cases)
CASES = _cases.CASES
from cad_agent import feature  # noqa: E402


def geo(g):
    t = g.TypeId
    if t == "Part::GeomLineSegment":
        return {"type": "LineSegment", "start": [g.StartPoint.x, g.StartPoint.y], "end": [g.EndPoint.x, g.EndPoint.y]}
    if t == "Part::GeomCircle":
        return {"type": "Circle", "center": [g.Location.x, g.Location.y], "radius": g.Radius, "axis_z": g.Axis.z}
    if t == "Part::GeomArcOfCircle":
        return {"type": "ArcOfCircle", "center": [g.Location.x, g.Location.y], "radius": g.Radius,
                "start": [g.StartPoint.x, g.StartPoint.y], "end": [g.EndPoint.x, g.EndPoint.y],
                "axis_z": g.Axis.z}
    if t == "Part::GeomPoint":
        return {"type": "Point", "at": [g.X, g.Y]}
    if t in ("Part::GeomEllipse", "Part::GeomArcOfEllipse"):
        d = {"type": t[len("Part::Geom"):], "center": [g.Center.x, g.Center.y], "major_radius": g.MajorRadius,
             "minor_radius": g.MinorRadius, "x_axis": [g.XAxis.x, g.XAxis.y], "axis_z": g.Axis.z}
        if t == "Part::GeomArcOfEllipse":
            d.update({"start": [g.StartPoint.x, g.StartPoint.y], "end": [g.EndPoint.x, g.EndPoint.y]})
        return d
    if t == "Part::GeomBSplineCurve":
        return {"type": "BSplineCurve", "poles": [[q.x, q.y] for q in g.getPoles()], "weights": list(g.getWeights()),
                "knots": list(g.getKnots()), "mults": list(g.getMultiplicities()), "degree": g.Degree,
                "periodic": g.isPeriodic()}
    return {"type": t}


def cons(sk):
    return [[c.Type, c.First, c.FirstPos, c.Second, c.SecondPos, c.Third, c.ThirdPos] for c in sk.Constraints]


ONLY = os.environ.get("SKETCHEXT_CASE")
if not ONLY:
    import subprocess
    import tempfile
    exe = os.path.join(App.getHomePath(), "bin", "freecadcmd")
    out = {"freecad": ".".join(App.Version()[:3]) + " " + App.Version()[3], "cases": {}}
    with tempfile.TemporaryDirectory() as tmp:
        for name in CASES:
            part = os.path.join(tmp, name + ".json")
            subprocess.run([exe, __file__], env={**os.environ, "SKETCHEXT_CASE": name, "SKETCHEXT_OUT": part},
                           check=True, capture_output=True)
            out["cases"][name] = json.loads(Path(part).read_text())
            rec = out["cases"][name]
            print(name, rec.get("error") or [g["type"] for g in rec["external"]])
    (HERE / "freecad.json").write_text(json.dumps(out, indent=1) + "\n")
    print(len(out["cases"]), "cases")
    sys.stdout.flush()
    sys.exit(0)

case = CASES[ONLY]
doc = App.newDocument(ONLY)
body = feature.to_freecad(case["features"], case.get("params"), doc=doc)
doc.recompute()
sk = doc.getObject("Sketch001")
bad = [f"{o.Name}: {o.getStatusString()}" for o in body.Group if not o.isValid()]
rec = {"error": "; ".join(bad)} if bad else {}
rec["types"] = list(sk.ExternalTypes)
rec["refs"] = [[o.Name, s] for o, subs in sk.ExternalGeometry for s in subs]
rec["external"] = [geo(g) for g in sk.ExternalGeo[2:]]
rec["dof"] = sk.solve()
rec["geometry"] = [geo(g) for g in sk.Geometry]
rec["constraints"] = cons(sk)
App.closeDocument(doc.Name)
Path(os.environ["SKETCHEXT_OUT"]).write_text(json.dumps(rec))

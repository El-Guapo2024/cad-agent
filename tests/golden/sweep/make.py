"""Writes freecad.json: what FreeCAD's PartDesign builds from each body of cases.py (Loft, Pipe and Helix), for
tests/test_feature_sweep.py to hold cad_agent/feature_sweep.py to.

    $FREECAD/freecadcmd tests/golden/sweep/make.py        (FREECAD: FreeCAD's bin folder, 26.3 at 3160daf1e2b6)

Run it from the repository's root. As tests/golden/feature/make.py: each case's FEATURES go to FreeCAD through
cad_agent.feature.to_freecad into a fresh document, which is recomputed, and the Body's shape is recorded (volume, area,
optimal bounding box, centre of mass, solids, faces, each face's area and centre). For ERRORS, the status string of the
feature FreeCAD refuses.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.getcwd())
if not (ROOT / "cad_agent" / "feature.py").exists():
    sys.exit("run make.py from the repository's root")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "golden" / "sweep"))

import FreeCAD as App  # noqa: E402

from cad_agent import feature  # noqa: E402
from cases import CASES, ERRORS  # noqa: E402


def r(x):
    return round(x, 9)


def measure(shape):
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


def build(name, features, params=None):
    doc = App.newDocument(name)
    try:
        body = feature.to_freecad(features, params, doc=doc)
        doc.recompute()
        bad = [f"{o.Name}: {o.getStatusString()}" for o in body.Group if not o.isValid()]
        return {"error": "; ".join(bad)} if bad else measure(body.Shape)
    except Exception as e:                         # a property FreeCAD refuses as it is set
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        App.closeDocument(doc.Name)


out = {"freecad": ".".join(App.Version()[:3]) + " " + App.Version()[3], "cases": {}, "errors": {}}
for name, case in CASES.items():
    out["cases"][name] = build(name, case["features"], case.get("params"))
    print(name, out["cases"][name].get("volume", out["cases"][name].get("error")))
for name, features in ERRORS.items():
    out["errors"][name] = build(name, features).get("error", "built")
    print(name, out["errors"][name])

Path(ROOT / "tests" / "golden" / "sweep" / "freecad.json").write_text(json.dumps(out, indent=1) + "\n")
print(len(out["cases"]), "cases,", len(out["errors"]), "errors")

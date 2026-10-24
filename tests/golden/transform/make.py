"""Writes freecad.json: what FreeCAD's PartDesign builds from each body of cases.py, for tests/test_feature_transform.py to
hold cad_agent/feature_transform.py and feature_primitive.py to.

    $FREECAD/freecadcmd tests/golden/transform/make.py        (FREECAD: FreeCAD's bin folder, 26.3 at 3160daf1e2b6)

Run it from the repository's root. As tests/golden/feature/make.py: each case's FEATURES go to FreeCAD through
cad_agent.feature.to_freecad, into a fresh document; it is recomputed and the Body's shape recorded (volume, area, the
optimal bounding box, the centre of mass, the number of solids and faces, each face's area and centre). A case FreeCAD
refuses is recorded with the first invalid feature's message.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.getcwd())
if not (ROOT / "cad_agent" / "feature.py").exists():
    sys.exit("run make.py from the repository's root")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "golden" / "transform"))

import FreeCAD as App  # noqa: E402

from cad_agent import feature  # noqa: E402
from cases import CASES  # noqa: E402


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


only = sys.argv[-1] if len(sys.argv) > 1 and sys.argv[-1] in CASES else None
path = ROOT / "tests" / "golden" / "transform" / "freecad.json"
out = {"freecad": ".".join(App.Version()[:3]) + " " + App.Version()[3], "cases": {}}
if only and path.exists():
    out = json.loads(path.read_text())
for name, case in CASES.items():
    if only and name != only:
        continue
    doc = App.newDocument(name)
    try:
        body = feature.to_freecad(case["features"], case.get("params"), doc=doc)
        doc.recompute()
        bad = [f"{o.Name}: {o.getStatusString()}" for o in body.Group
               if hasattr(o, "isValid") and not o.isValid()]
        if bad:
            out["cases"][name] = {"error": "; ".join(bad)}
        elif body.Shape.isNull() or not body.Shape.Solids:
            out["cases"][name] = {"error": "the Body has no solid"}
        else:
            out["cases"][name] = measure(body.Shape)
    except Exception as e:                       # noqa: BLE001 - a property FreeCAD refuses to take
        out["cases"][name] = {"error": f"{type(e).__name__}: {e}"}
    print(name, out["cases"][name].get("volume", out["cases"][name].get("error")))
    App.closeDocument(doc.Name)

path.write_text(json.dumps(out, indent=1) + "\n")
print(len(out["cases"]), "cases")

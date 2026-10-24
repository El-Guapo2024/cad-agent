"""Writes freecad.json: what FreeCAD's PartDesign builds from each body of cases.py, for tests/test_feature.py to
hold cad_agent/feature.py to.

    $FREECAD/freecadcmd tests/golden/feature/make.py        (FREECAD: FreeCAD's bin folder, 26.3 at 3160daf1e2b6)

Run it from the repository's root. Each case's FEATURES go to FreeCAD through cad_agent.feature.to_freecad, the
same lines the part files hold, into a fresh document; it is recomputed and the Body's shape recorded: volume,
area, the optimal bounding box (no triangulation, no shape tolerance), the centre of mass, the number of solids
and faces, and each face's area and centre in FreeCAD's Face1, Face2, ... order. A case FreeCAD refuses is
recorded with its error.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.getcwd())
if not (ROOT / "cad_agent" / "feature.py").exists():
    sys.exit("run make.py from the repository's root")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "golden" / "feature"))

import FreeCAD as App  # noqa: E402
import Part  # noqa: E402

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


out = {"freecad": ".".join(App.Version()[:3]) + " " + App.Version()[3], "cases": {}}
for name, case in CASES.items():
    doc = App.newDocument(name)
    base = None
    if case.get("base"):
        _, p, s = case["base"]
        base = Part.makeBox(s[0], s[1], s[2], App.Vector(*p))
    body = feature.to_freecad(case["features"], case.get("params"), doc=doc, base=base)
    doc.recompute()
    bad = [f"{o.Name}: {o.getStatusString()}" for o in body.Group if not o.isValid()]
    if bad:
        out["cases"][name] = {"error": "; ".join(bad)}
    else:
        out["cases"][name] = measure(body.Shape)
    print(name, out["cases"][name].get("volume", out["cases"][name].get("error")))
    App.closeDocument(doc.Name)

Path(ROOT / "tests" / "golden" / "feature" / "freecad.json").write_text(json.dumps(out, indent=1) + "\n")
print(len(out["cases"]), "cases")

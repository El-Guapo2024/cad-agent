"""Writes freecad.json: what FreeCAD's PartDesign::Hole makes of each case of cases.py, for tests/test_feature_hole.py.

    $FREECAD/freecadcmd tests/golden/hole/make.py        (FREECAD: FreeCAD's bin folder, 26.3 at 3160daf1e2b6)

Run it from the repository's root. STATES: a Hole on the 40 x 20 x 10 plate, made as feature_hole.Hole.to_freecad makes
one (newObject in the Body, its Profile, a recompute), then the chosen properties set in feature_hole.ORDER; recorded:
every property's value, editor mode and enumeration list. CASES and ERRORS: as tests/golden/revolve/make.py, the
Body's shape or the refused feature's status string.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.getcwd())
if not (ROOT / "cad_agent" / "feature.py").exists():
    sys.exit("run make.py from the repository's root")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "golden" / "hole"))

import FreeCAD as App  # noqa: E402

from cad_agent import feature  # noqa: E402
from cad_agent.feature_hole import ORDER, SNAKE  # noqa: E402
from cases import CASES, ERRORS, ONE, STATES, plate, top  # noqa: E402

PROPS = ORDER + ["ThreadDiameter"]


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


def state(name, given):
    doc = App.newDocument(name)
    try:
        body = feature.to_freecad(plate() + [top(ONE)], doc=doc)
        doc.recompute()
        h = body.newObject("PartDesign::Hole", "Hole")
        h.Profile = doc.getObject("Holes")
        doc.recompute()
        for p in ORDER:
            k = SNAKE[p]
            if k in given:
                setattr(h, p, given[k])
        out = {}
        for p in PROPS:
            v = getattr(h, p)
            v = getattr(v, "Value", v)
            out[SNAKE[p]] = {"value": r(v) if isinstance(v, float) else v, "read_only": "ReadOnly" in h.getEditorMode(p)}
            if h.getTypeIdOfProperty(p) == "App::PropertyEnumeration":
                out[SNAKE[p]]["enums"] = h.getEnumerationsOfProperty(p)
        doc.recompute()
        out["_valid"] = h.isValid()
        out["_status"] = h.getStatusString()
        return out
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        App.closeDocument(doc.Name)


def build(name, features, params=None):
    doc = App.newDocument(name)
    try:
        body = feature.to_freecad(features, params, doc=doc)
        doc.recompute()
        bad = [f"{o.Name}: {o.getStatusString()}" for o in body.Group if not o.isValid()]
        return {"error": "; ".join(bad)} if bad else measure(body.Shape)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        App.closeDocument(doc.Name)


out = {"freecad": ".".join(App.Version()[:3]) + " " + App.Version()[3], "states": {}, "cases": {}, "errors": {}}
for name, given in STATES.items():
    out["states"][name] = state(name, given)
    s = out["states"][name]
    print(name, s.get("error") or (s["diameter"]["value"], s["hole_cut_diameter"]["value"], s["hole_cut_depth"]["value"]))
for name, case in CASES.items():
    out["cases"][name] = build(name, case["features"], case.get("params"))
    print(name, out["cases"][name].get("volume", out["cases"][name].get("error")))
for name, features in ERRORS.items():
    out["errors"][name] = build(name, features).get("error", "built")
    print(name, out["errors"][name])

Path(ROOT / "tests" / "golden" / "hole" / "freecad.json").write_text(json.dumps(out, indent=1) + "\n")
print(len(out["states"]), "states,", len(out["cases"]), "cases,", len(out["errors"]), "errors")

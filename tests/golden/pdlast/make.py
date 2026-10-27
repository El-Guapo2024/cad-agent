"""Writes freecad.json: what FreeCAD's PartDesign builds from each body of cases.py (PartDesign's last commands: the
Involute Gear and Sprocket, ...), for tests/test_feature_pdlast.py to hold cad_agent/feature.py to.

    $FREECAD/freecadcmd tests/golden/pdlast/make.py   (FREECAD: FreeCAD's bin folder, 26.3 at 3160daf1e2b6)

Run it from the repository's root. As tests/golden/feature/make.py: each case's FEATURES go to FreeCAD through
cad_agent.feature.to_freecad into a fresh document, it is recomputed, and the Body and every object of it recorded:
its type, Shape (kind, counts, length or volume and area, box, centre of mass) and Placement. SprocketFeature.Sprocket
reads its task panel's .ui for the names of its SprocketReference enumeration; headless there is no Qt, so the combo
box's items (SprocketFeature.ui, in its order) stand in for it.
"""
import json
import os
import sys
import types
from pathlib import Path

ROOT = Path(os.getcwd())
if not (ROOT / "cad_agent" / "feature.py").exists():
    sys.exit("run make.py from the repository's root")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "golden" / "pdlast"))

import FreeCAD as App  # noqa: E402

from cad_agent import feature  # noqa: E402
from cad_agent.feature_gear import SPROCKET_REFERENCES  # noqa: E402
from cases import CASES  # noqa: E402


def _headless_sprocket():
    """SprocketFeature.Sprocket.__init__ loads SprocketFeature.ui to read comboBox_SprocketReference's items."""
    import SprocketFeature

    class Combo:
        i = 0

        def setCurrentIndex(self, i):
            self.i = i

        def currentText(self):
            return SPROCKET_REFERENCES[self.i][0]

    form = types.SimpleNamespace(comboBox_SprocketReference=Combo())
    SprocketFeature.FreeCADGui = types.SimpleNamespace(PySideUic=types.SimpleNamespace(loadUi=lambda path: form))


_headless_sprocket()


def r(x):
    return round(x, 9) + 0.0                     # -0.0 is 0.0


def placement(pl):
    return [r(c) for c in (pl.Base.x, pl.Base.y, pl.Base.z, *pl.Rotation.toEulerAngles("YawPitchRoll"))]


def measure(shape):
    if shape.isNull():
        return {"null": True}
    bb = shape.BoundBox
    m = {"type": shape.ShapeType, "solids": len(shape.Solids), "faces": len(shape.Faces),
         "edges": len(shape.Edges), "vertices": len(shape.Vertexes), "placement": placement(shape.Placement),
         "bbox": [r(c) for c in (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax)]}
    if shape.Solids:
        vol = sum(s.Volume for s in shape.Solids)
        c = sum((s.CenterOfMass * s.Volume for s in shape.Solids), App.Vector()) * (1.0 / vol)
        m.update(volume=r(shape.Volume), area=r(shape.Area), center=[r(x) for x in c])
    elif shape.Faces:
        m.update(area=r(shape.Area))
    else:
        m.update(length=r(shape.Length), closed=bool(shape.isClosed()) if shape.ShapeType == "Wire" else None)
    return m


out = {"freecad": ".".join(App.Version()[:3]) + " " + App.Version()[3], "cases": {}}
only = sys.argv[1:] if len(sys.argv) > 1 and not sys.argv[-1].endswith(".py") else None
old = ROOT / "tests" / "golden" / "pdlast" / "freecad.json"
if only and old.exists():                        # make.py NAME ...: those cases again, the rest kept
    out["cases"] = json.loads(old.read_text())["cases"]
for name, case in CASES.items():
    if only and name not in only:
        continue
    doc = App.newDocument(name)
    for other, oc in (case.get("others") or {}).items():     # the document's other Bodies, under their own names
        feature.to_freecad(oc["features"], oc.get("params"), doc=doc, name=other)
        doc.recompute()
    body = feature.to_freecad(case["features"], case.get("params"), doc=doc, name=case.get("body", "Body"))
    doc.recompute()
    bad = [f"{o.Name}: {o.getStatusString()}" for o in body.Group if not o.isValid()]
    res = {"error": "; ".join(bad)} if bad else {}
    res["tip"] = body.Tip.Name if body.Tip else None
    res["objects"] = {}
    for o in body.Group:
        if o.TypeId == "Sketcher::SketchObject" or o.TypeId.startswith("App::"):
            continue
        rec = {"type": o.TypeId, "placement": placement(o.Placement), "valid": o.isValid()}
        if o.isValid() and hasattr(o, "Shape"):
            rec["shape"] = measure(o.Shape)
        res["objects"][o.Name] = rec
    if not bad:
        res["body"] = measure(body.Shape)
    out["cases"][name] = res
    print(name, res.get("error") or res.get("body", {}).get("volume"))
    App.closeDocument(doc.Name)

old.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
print(len(out["cases"]), "cases")

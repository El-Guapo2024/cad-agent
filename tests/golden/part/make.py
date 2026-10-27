"""Writes freecad.json: what FreeCAD's Part workbench builds from each document of cases.py, for tests/test_feature_part.py
to hold cad_agent/feature_part*.py to.

    $FREECAD/freecadcmd tests/golden/part/make.py [AREA] [CASE]   (FREECAD: FreeCAD's bin folder, 26.3 at 3160daf1e2b6)

AREA picks the cases: none (or "base") is cases.py into freecad.json, "split" is cases_split.py into
freecad_split.json, and so on; CASE remakes that one case and keeps the rest of the file.

Run it from the repository's root. Each case's OBJECTS (and FEATURES, a Body) go to FreeCAD through
cad_agent.feature_part.to_freecad, into a fresh document, which is recomputed; every object's shape is recorded
(volume, area, length, the optimal bounding box, the centre of mass, the counts of solids ... vertices, the shape type
and validity), or the object's error when FreeCAD's recompute marks it invalid. "defaults" holds, for every type, a
fresh object's properties as FreeCAD gives them, which the test holds each class's DEFAULTS to.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.getcwd())
if not (ROOT / "cad_agent" / "feature.py").exists():
    sys.exit("run make.py from the repository's root")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "golden" / "part"))

import FreeCAD as App  # noqa: E402

from cad_agent import feature_part as Part  # noqa: E402
import importlib  # noqa: E402

args = [a for a in sys.argv[1:] if not a.endswith(".py")]
AREA = args[0] if args and (Path(__file__).with_name(f"cases_{args[0]}.py").exists() or args[0] == "base") else "base"
if args and args[0] == AREA:
    args = args[1:]
CASES = importlib.import_module("cases" if AREA == "base" else f"cases_{AREA}").CASES


def r(x):
    return round(x, 9)


def com(shape):
    """The centre of mass the test computes too: volume-weighted over the solids, else area-weighted over the faces,
    else length-weighted over the edges, else the vertices' mean."""
    for parts, w in ((shape.Solids, "Volume"), (shape.Faces, "Area"), (shape.Edges, "Length")):
        tot = sum(getattr(p, w) for p in parts)
        if parts and tot > 1e-12:
            return [r(sum(getattr(p.CenterOfMass, k) * getattr(p, w) for p in parts) / tot) for k in "xyz"]
    vs = shape.Vertexes
    return [r(sum(getattr(v.Point, k) for v in vs) / len(vs)) for k in "xyz"] if vs else None


def measure(shape):
    bb = shape.optimalBoundingBox(False, False)
    return {
        "type": shape.ShapeType, "valid": shape.isValid(),
        "volume": r(shape.Volume), "area": r(shape.Area), "length": r(shape.Length),
        "bbox": [r(bb.XMin), r(bb.YMin), r(bb.ZMin), r(bb.XMax), r(bb.YMax), r(bb.ZMax)],
        "center_of_mass": com(shape),
        "solids": len(shape.Solids), "shells": len(shape.Shells), "faces": len(shape.Faces),
        "wires": len(shape.Wires), "edges": len(shape.Edges), "vertices": len(shape.Vertexes),
    }


def plain(v):
    """A property's value as JSON (FreeCAD's Vector, Quantity, Placement ...)."""
    if isinstance(v, (bool, int, float, str)) or v is None:
        return v
    if hasattr(v, "Value") and hasattr(v, "Unit"):
        return v.Value
    if isinstance(v, App.Placement):
        return [list(v.Base), list(v.Rotation.toEuler())]
    if isinstance(v, App.Vector):
        return [v.x, v.y, v.z]
    if isinstance(v, (list, tuple)):
        return [plain(x) for x in v]
    return repr(v)


def defaults(only=None):
    """{TypeId: {property: value}} of a fresh object of each type, made as the Part commands make it (only: those kinds)."""
    out = {}
    doc = App.newDocument("defaults")
    for kind, cls in sorted(Part.OBJECTS.items()):
        if only is not None and kind not in only:
            continue
        try:
            obj = doc.addObject(getattr(cls, "FC_TYPE", cls.TYPE_ID), kind.split(".")[1])
            cls.fc_setup(Part.KwFeature.__new__(cls), obj, None)
            out[cls.TYPE_ID] = {p: plain(obj.getPropertyByName(p)) for p in obj.PropertiesList
                                if p not in ("Shape", "Label2", "ExpressionEngine", "Visibility", "History")}
            if obj.TypeId in ("Part::FeaturePython",):
                out[cls.TYPE_ID]["_TypeId"] = obj.TypeId
        except Exception as e:  # noqa: BLE001
            out[cls.TYPE_ID] = {"error": f"{type(e).__name__}: {e}"}
    App.closeDocument(doc.Name)
    return out


def extension_defaults(only=None):
    """{TypeId: {property: value}} of AttachExtension on a fresh object of each type: its properties where the type has
    the extension, else those Part::AttachExtensionPython gives it, added as TaskAttachmentEditor.__init__ adds it. The
    Attachment editor of Part_EditAttachment works on any object with a Placement."""
    out = {}
    doc = App.newDocument("extension")
    for kind, cls in sorted(Part.OBJECTS.items()):
        if only is not None and kind not in only:
            continue
        try:
            obj = doc.addObject(getattr(cls, "FC_TYPE", cls.TYPE_ID), kind.split(".")[1])
            if not hasattr(obj, "AttacherType"):
                obj.addExtension("Part::AttachExtensionPython")
            out[cls.TYPE_ID] = {p: plain(obj.getPropertyByName(p)) for p in
                                ("AttachmentSupport", "MapMode", "AttachmentOffset", "MapReversed",
                                 "MapPathParameter")}
        except Exception as e:  # noqa: BLE001
            out[cls.TYPE_ID] = {"error": f"{type(e).__name__}: {e}"}
    App.closeDocument(doc.Name)
    return out


only = args[0] if args and args[0] in CASES else None
path = ROOT / "tests" / "golden" / "part" / ("freecad.json" if AREA == "base" else f"freecad_{AREA}.json")
out = {"freecad": ".".join(App.Version()[:3]) + " " + App.Version()[3], "cases": {}}
if only and path.exists():
    out = json.loads(path.read_text())
elif AREA == "base":
    out["defaults"] = defaults()
if AREA == "attach":
    out["extension"] = extension_defaults()
if AREA == "static":                              # the new types' fresh objects, which the base file does not hold
    _kinds = {o.kind for c in CASES.values() for o in c["objects"] if hasattr(o, "kind")}
    out["defaults"], out["extension"] = defaults(_kinds), extension_defaults(_kinds)
for name, case in CASES.items():
    if only and name != only:
        continue
    doc = App.newDocument(name)
    res = {}
    try:
        made = Part.to_freecad(case["objects"], case.get("params"), doc=doc, features=case.get("features"))
        doc.recompute()
        for o in case["objects"]:
            obj = made[o.name]
            if hasattr(obj, "isValid") and not obj.isValid():
                res[o.name] = {"error": obj.getStatusString()}
            elif obj.Shape.isNull():
                res[o.name] = {"error": "null shape"}
            else:
                res[o.name] = measure(obj.Shape)
                pl = obj.Placement
                res[o.name]["placement"] = [list(pl.Base), list(pl.Rotation.toEuler())]
        if case.get("features") is not None:
            res["Body"] = measure(made["Body"].Shape) if not made["Body"].Shape.isNull() else {"error": "null"}
    except Exception as e:                       # noqa: BLE001 - a property FreeCAD refuses to take
        res = {"_error": f"{type(e).__name__}: {e}"}
    out["cases"][name] = res
    print(name, {k: v.get("volume", v.get("length", v.get("error"))) if isinstance(v, dict) else v
                 for k, v in res.items()})
    App.closeDocument(doc.Name)

path.write_text(json.dumps(out, indent=1) + "\n")
print(len(out["cases"]), "cases")

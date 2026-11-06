"""Writes freecad_path.json: each element's Placement of each case of cases_path.py, as FreeCAD 26.3 computes it.

    $FREECAD/freecadcmd tests/golden/link_array/make_path.py      (from the repository's root)

Each case: a Part::Feature "pin" (a box, the linked object), a Part::Feature "path" with the case's shape, the array
made as Part_LinkArrayPath / Part_LinkArrayPoint makes it (addObject, then LinkedObject), Path = (path, subs) or
PointObject = path, its properties set, the document recomputed.
"""
import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(os.getcwd())
sys.path.insert(0, str(ROOT / "tests" / "golden" / "link_array"))
import FreeCAD as App  # noqa: E402
import Part  # noqa: E402

from cases_path import CASES  # noqa: E402

V = App.Vector


def shape(spec):
    kind = spec[0]
    if kind == "polygon":
        return Part.makePolygon([V(*p) for p in spec[1]])
    if kind == "circle":
        return Part.Wire([Part.makeCircle(spec[1])])
    if kind == "arc":
        return Part.Wire([Part.makeCircle(spec[1], V(0, 0, 0), V(0, 0, 1), 0, spec[2])])
    if kind == "bspline":
        b = Part.BSplineCurve()
        b.interpolate([V(*p) for p in spec[1]])
        return Part.Wire([b.toShape()])
    if kind == "box":
        return Part.makeBox(*spec[1:])
    raise ValueError(kind)


out = {}
for name, (type_id, props, spec) in CASES.items():
    doc = App.newDocument("Unnamed")
    pin = doc.addObject("Part::Feature", "pin")
    pin.Shape = Part.makeBox(4, 3, 2)
    path = doc.addObject("Part::Feature", "path")
    path.Shape = shape(spec)
    a = doc.addObject(type_id, "PathLinkArray" if type_id.endswith("Path") else "PointLinkArray")
    a.LinkedObject = pin
    if type_id.endswith("Path"):
        a.Path = (path, props.get("Path") or [""])
    else:
        a.PointObject = path
    for k, v in props.items():
        if k != "Path":
            setattr(a, k, V(*v) if isinstance(v, tuple) else v)
    doc.recompute()
    out[name] = [[*e.Placement.Base, *e.Placement.Rotation.Q] for e in a.ElementList]
    if not a.isValid():
        out[name] = {"error": a.getStatusString()}
    App.closeDocument(doc.Name)
    print(name, len(out[name]) if isinstance(out[name], list) else out[name])
(ROOT / "tests" / "golden" / "link_array" / "freecad_path.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")

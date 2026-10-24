"""Writes engine.json and shapes/*.brep: what FreeCAD's attachment engine (Part.AttachEngine, Attacher.cpp) answers
for a set of references, for tests/test_attacher.py to hold cad_agent/attacher.py to.

    $FREECAD/freecadcmd tests/golden/attach/make.py        (FREECAD: FreeCAD's bin folder, 26.3 at 3160daf1e2b6)

Run it from the repository's root. The references are elements of a few placed Part::Feature objects (a box, a
cylinder, a cone, a sphere, a torus, conic and spline edges, four lines for Folding) and a Body's origin
features. Each object's shape is written as BREP, placed, so the test resolves the very same faces, edges and
vertices (FreeCAD's Face1, Edge1, ... are TopExp::MapShapes' order, which the test uses too). For each of the
four engines (AttacherType) and each reference set, it records suggestModes() and, for every mode that suggests
as applicable, calculateAttachedPlacement() twice: plainly, and with an AttachmentOffset, Reverse (Flip sides)
and a Parameter (MapPathParameter). A placement is its position and quaternion; a refusal its message.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.getcwd())
OUT = ROOT / "tests" / "golden" / "attach"
if not (OUT / "make.py").exists():
    sys.exit("run make.py from the repository's root")

import FreeCAD as App  # noqa: E402
import Part  # noqa: E402

V = App.Vector
doc = App.newDocument("attach")


def feature(name, shape, placement):
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = shape
    obj.Placement = placement
    return obj


def fold():
    import math
    edges = []
    for a in (0.0, 40.0, 80.0, 130.0):
        r = math.radians(a)
        edges.append(Part.makeLine(V(0, 0, 0), V(10 * math.cos(r), 10 * math.sin(r), 0)))
    return Part.Compound(edges)


def spline():
    c = Part.BSplineCurve()
    c.interpolate([V(0, 0, 0), V(4, 3, 1), V(8, 1, 3), V(12, 5, 2)])
    return c.toShape()


def hyperbola():
    h = Part.Hyperbola()
    h.MajorRadius, h.MinorRadius = 4.0, 2.0
    return h.toShape(-1.5, 1.5)


def parabola():
    p = Part.Parabola()
    p.Focal = 2.0
    return p.toShape(-3.0, 3.0)


OBJECTS = {
    "Box": (Part.makeBox(10, 6, 4), App.Placement(V(1, 2, 3), App.Rotation(10, 20, 30))),
    "Cyl": (Part.makeCylinder(3, 8), App.Placement(V(5, -2, 1), App.Rotation(0, 30, 0))),
    "Cone": (Part.makeCone(4, 1, 6), App.Placement(V(-6, 0, 0), App.Rotation(0, 0, 25))),
    "Sphere": (Part.makeSphere(5), App.Placement(V(0, 0, 20), App.Rotation())),
    "Torus": (Part.makeTorus(6, 2), App.Placement(V(0, 15, 0), App.Rotation(30, 0, 0))),
    "Ellipse": (Part.Ellipse(V(0, 0, 0), 6, 3).toShape(), App.Placement(V(2, 2, 2), App.Rotation(0, 45, 0))),
    "Hyper": (hyperbola(), App.Placement(V(0, -10, 0), App.Rotation(0, 0, 0))),
    "Parab": (parabola(), App.Placement(V(0, -20, 5), App.Rotation(15, 0, 0))),
    "Spline": (spline(), App.Placement(V(0, 0, -5), App.Rotation(0, 0, 0))),
    "Fold": (fold(), App.Placement(V(3, 3, 3), App.Rotation(0, 0, 0))),
}
objs = {name: feature(name, s, p) for name, (s, p) in OBJECTS.items()}
body = doc.addObject("PartDesign::Body", "Body")
doc.recompute()
for o in body.Origin.OriginFeatures:
    objs[o.Role] = o

(OUT / "shapes").mkdir(exist_ok=True)
shapes = {}
for name in OBJECTS:
    path = OUT / "shapes" / f"{name}.brep"
    objs[name].Shape.exportBrep(str(path))
    p = objs[name].Placement
    shapes[name] = {"placement": [list(p.Base), list(p.Rotation.Q)]}
origin = {}
for role in ("X_Axis", "Y_Axis", "Z_Axis", "XY_Plane", "XZ_Plane", "YZ_Plane", "Origin"):
    p = objs[role].Placement
    origin[role] = {"placement": [list(p.Base), list(p.Rotation.Q)], "type": objs[role].TypeId}

REFS = [
    # one reference
    [("Box", "")], [("Box", "Face1")], [("Box", "Face6")], [("Box", "Edge1")], [("Box", "Edge5")],
    [("Box", "Vertex1")], [("Cyl", "")], [("Cyl", "Face1")], [("Cyl", "Face2")], [("Cyl", "Edge1")],
    [("Cone", "Face1")], [("Sphere", "Face1")], [("Torus", "Face1")], [("Ellipse", "Edge1")],
    [("Hyper", "Edge1")], [("Parab", "Edge1")], [("Spline", "Edge1")], [("Spline", "")],
    [("XY_Plane", "")], [("XZ_Plane", "")], [("YZ_Plane", "")], [("X_Axis", "")], [("Y_Axis", "")],
    [("Z_Axis", "")], [("Origin", "")],
    # two
    [("Box", "Face1"), ("Box", "Vertex7")], [("Box", "Vertex7"), ("Box", "Face1")],
    [("Cyl", "Face1"), ("Box", "Vertex3")], [("Sphere", "Face1"), ("Box", "Vertex1")],
    [("Box", "Edge1"), ("Box", "Vertex2")], [("Box", "Vertex2"), ("Box", "Edge1")],
    [("Cyl", "Edge1"), ("Box", "Vertex1")], [("Spline", "Edge1"), ("Box", "Vertex4")],
    [("Box", "Vertex4"), ("Spline", "Edge1")],
    [("Box", "Vertex1"), ("Box", "Vertex2")], [("Box", "Edge1"), ("Box", "Edge2")],
    [("Box", "Edge1"), ("Box", "Edge11")], [("Box", "Face1"), ("Box", "Face2")],
    [("Box", "Face1"), ("Box", "Face3")], [("Box", "Face5"), ("Box", "Face6")], [("Box", ""), ("Box", "Vertex5")],
    [("XY_Plane", ""), ("Box", "Vertex2")], [("Box", "Face2"), ("Spline", "Edge1")],
    [("Box", "Face1"), ("Box", "Face5")], [("Box", "Edge1"), ("Cyl", "Edge1")],
    [("XY_Plane", ""), ("XZ_Plane", "")], [("Box", "Vertex1"), ("Z_Axis", "")],
    [("Box", "Face4"), ("Cyl", "Face1")],
    # three
    [("Box", "Vertex1"), ("Box", "Vertex2"), ("Box", "Vertex3")],
    [("Box", "Vertex1"), ("Box", "Vertex2"), ("Box", "Edge3")],
    [("Box", "Vertex1"), ("Box", "Edge1"), ("Box", "Vertex3")],
    [("Box", "Vertex1"), ("Box", "Edge1"), ("Box", "Edge4")],
    [("Box", "Face1"), ("Box", "Face2"), ("Box", "Face3")],
    # four
    [("Fold", "Edge1"), ("Fold", "Edge2"), ("Fold", "Edge3"), ("Fold", "Edge4")],
    [("Box", "Vertex1"), ("Box", "Vertex2"), ("Box", "Vertex3"), ("Box", "Vertex5")],
]
ENGINES = {"3D": "Attacher::AttachEngine3D", "Plane": "Attacher::AttachEnginePlane",
           "Line": "Attacher::AttachEngineLine", "Point": "Attacher::AttachEnginePoint"}
OFFSET = App.Placement(V(1.5, -2.0, 0.75), App.Rotation(15, -25, 40))


def place(p):
    return [list(p.Base), list(p.Rotation.Q)]


cases = []
suggestions = []
for engine, typ in ENGINES.items():
    for refs in REFS:
        eng = Part.AttachEngine(typ)
        eng.References = [(objs[o], s) for o, s in refs]
        sug = eng.suggestModes()
        suggestions.append({"engine": engine, "refs": refs, "message": sug["message"],
                            "best": sug["bestFitMode"], "all": list(sug["allApplicableModes"]),
                            "reachable": {k: [list(x) for x in v] for k, v in sug["reachableModes"].items()},
                            "hints": sorted(sug["nextRefTypeHint"]), "types": list(sug["references_Types"])})
        for mode in sug["allApplicableModes"]:
            for variant in ("plain", "offset"):
                eng = Part.AttachEngine(typ)
                eng.References = [(objs[o], s) for o, s in refs]
                eng.Mode = mode
                if variant == "offset":
                    eng.AttachmentOffset = OFFSET
                    eng.Reverse = True
                    eng.Parameter = 0.3
                case = {"engine": engine, "refs": refs, "mode": mode, "variant": variant}
                try:
                    pl = eng.calculateAttachedPlacement(App.Placement(V(0, 0, 0), App.Rotation(5, 6, 7)))
                    case["placement"] = place(pl) if pl is not None else None
                except Exception as e:
                    case["error"] = str(e)
                cases.append(case)

out = {"freecad": ".".join(App.Version()[:3]) + " " + App.Version()[3], "shapes": shapes, "origin": origin,
       "offset": place(OFFSET), "orig": place(App.Placement(V(0, 0, 0), App.Rotation(5, 6, 7))),
       "suggestions": suggestions, "cases": cases}
(OUT / "engine.json").write_text(json.dumps(out, indent=0) + "\n")
print(len(suggestions), "suggestions,", len(cases), "placements,",
      sum(1 for c in cases if "error" in c), "refused")

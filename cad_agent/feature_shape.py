"""cad feature shape: a Body's feature built as it would be after some ops, without writing anything.

    cad feature shape SLUG PART [--ops JSON] [--feature NAME]

The task panels of features that the page cannot build itself (Fillet, Chamfer, Draft, Thickness) ask for this:
the ops go through cad_agent/feature_edit.py on the part's source in memory (and follow_src, as an apply does),
the module is run and its feature list evaluated, and the data carries, in the part's own frame:

    {"feature": NAME, "base_name": the solid before it (FreeCAD's BaseFeature) or None,
     "shape": {...} the feature's solid, "base": {...} the solid before it, "error": FreeCAD's message or None,
     "doc": read() of the edited source}

each shape as {"faces": [{"name": "Face1", "points": [x, y, z, ...], "index": [i, j, k, ...]}, ...],
"edges": [{"name": "Edge1", "points": [x, y, z, ...]}, ...]}, the faces and edges named as FreeCAD names them
(TopExp::MapShapes order), so the page picks a sub-element of the base by the name the feature's Base takes.
NAME defaults to the Tip.
"""
from __future__ import annotations

import json
from pathlib import Path

from .cmdbase import OK, Result, UsageError, part, project


def mesh(shape, deflection: float | None = None) -> dict:
    """Faces as triangles and edges as polylines, by FreeCAD's names."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.GCPnts import GCPnts_TangentialDeflection
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_REVERSED
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS

    from . import feature as F
    if shape is None or shape.IsNull():
        return {"faces": [], "edges": []}
    if deflection is None:
        box = Bnd_Box()
        BRepBndLib.Add_s(shape, box)
        lo, hi = box.CornerMin(), box.CornerMax()
        size = max(hi.X() - lo.X(), hi.Y() - lo.Y(), hi.Z() - lo.Z(), 1e-3)
        deflection = max(size * 1e-3, 1e-3)
    BRepMesh_IncrementalMesh(shape, deflection, False, 0.3, True)

    def r(x):
        return round(x, 5) + 0.0

    faces = []
    for i, f in enumerate(F._faces(shape), 1):
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(f, loc)
        pts, idx = [], []
        if tri is not None:
            t = loc.Transformation()
            for k in range(1, tri.NbNodes() + 1):
                p = tri.Node(k).Transformed(t)
                pts += [r(p.X()), r(p.Y()), r(p.Z())]
            rev = f.Orientation() == TopAbs_REVERSED
            for k in range(1, tri.NbTriangles() + 1):
                a, b, c = tri.Triangle(k).Get()
                idx += [a - 1, c - 1, b - 1] if rev else [a - 1, b - 1, c - 1]
        faces.append({"name": f"Face{i}", "points": pts, "index": idx})
    edges = []
    for i, e in enumerate(F._subs(shape, TopAbs_EDGE), 1):
        edge = TopoDS.Edge(e)
        pts = []
        if not BRep_Tool.Degenerated_s(edge):
            c = BRepAdaptor_Curve(edge)
            d = GCPnts_TangentialDeflection(c, 0.2, deflection)
            for k in range(1, d.NbPoints() + 1):
                p = d.Value(k)
                pts += [r(p.X()), r(p.Y()), r(p.Z())]
        edges.append({"name": f"Edge{i}", "points": pts})
    return {"faces": faces, "edges": edges}


def shapes_after(path: Path, ops: list, name: str | None):
    """(doc, feature name, base name, feature solid, base solid, error) for the part at path after ops."""
    from . import feature as F
    from . import feature_edit as E
    src = path.read_text()
    new = E.apply_src(src, ops) if ops else src
    new = E.follow_src(src, new, path)
    doc = E.read_src(new, path.stem)
    if name and name in [o["name"] for o in doc.get("objects") or []]:     # a Part object (feature_edit_part.py)
        from .feature_edit_part import object_shape
        shape, error = object_shape(new, path, name)
        return doc, name, None, shape, None, error
    feats, params, base = E._run(new, path)
    target = name or doc.get("tip") or (doc["features"][-1]["name"] if doc["features"] else None)
    names = [f["name"] for f in doc["features"]]
    if target not in names:
        raise UsageError(f"{path.stem} has no feature {target!r}")
    i = names.index(target)
    base_name = next((f["name"] for f in reversed(doc["features"][:i]) if f["type"] != "Sketcher::SketchObject"),
                     "BaseFeature" if doc.get("base") else None)
    error = None
    shapes = {}
    try:
        shapes = F.evaluate(feats, params, base, tip=target)
    except F.FeatureError as e:
        error = str(e)
        if base_name is not None:
            try:
                shapes = F.evaluate(feats, params, base, tip=base_name)
            except F.FeatureError:
                shapes = {}
    return doc, target, base_name, shapes.get(target), shapes.get(base_name) if base_name else None, error


def _children(shape) -> int:
    """The shapes a compound holds at its first level (Part_Fuse of one compound, Part_ExplodeCompound), 0 for another."""
    if shape is None or shape.IsNull():
        return 0
    from OCP.TopAbs import TopAbs_COMPOUND
    from OCP.TopoDS import TopoDS_Iterator
    if shape.ShapeType() != TopAbs_COMPOUND:
        return 0
    n, it = 0, TopoDS_Iterator(shape)
    while it.More():
        n += 1
        it.Next()
    return n


def cmd_feature_shape(a) -> Result:
    project(a.slug)
    path = part(a.slug, a.part)
    ops = []
    if a.ops:
        text = Path(a.ops[1:]).read_text() if a.ops.startswith("@") else a.ops
        try:
            ops = json.loads(text)
        except ValueError as e:
            raise UsageError(f"--ops is JSON: {e}") from None
    try:
        doc, target, base_name, solid, base, error = shapes_after(path, ops, a.feature)
    except ValueError as e:                       # FeatureEditError: the ops do not apply
        raise UsageError(str(e)) from None
    data = {"project": a.slug, "part": a.part, "feature": target, "base_name": base_name,
            "shape": mesh(solid) if solid is not None and not error else None,
            "base": mesh(base) if base is not None else None, "error": error, "doc": doc,
            "children": _children(solid)}
    text = f"{a.part}/{target}: " + (error or f"{len(data['shape']['faces'])} faces") + \
        (f"; base {base_name}" if base_name else "")
    return Result(OK, data, text, f"{a.part}/{target} shape")


def add_parser(add, fsub) -> None:
    """featurecmd.add_parsers hands its subparsers here."""
    sp = add("shape", cmd_feature_shape, "a feature's solid and its base's, tessellated by FreeCAD's face and edge "
             "names, after --ops (nothing is written): what a dress-up's task panel shows and picks from",
             parent=fsub)
    sp.set_defaults(cmd_name="feature shape", feature_cmd="shape")
    sp.add_argument("slug")
    sp.add_argument("part")
    sp.add_argument("--ops", metavar="JSON", help="ops as `cad feature apply` takes them, applied in memory")
    sp.add_argument("--feature", metavar="NAME", help="the feature (default: the Tip)")

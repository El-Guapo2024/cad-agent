# SPDX-License-Identifier: LGPL-2.1-or-later
# A port of FreeCAD's face makers (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), each file
# LGPL-2.1-or-later as it states:
#   src/Mod/Part/App/FaceMaker.cpp, FaceMakerCheese.cpp: Copyright (c) 2016 Victor Titov (DeepSOIC)
#   src/Mod/Part/App/FaceMakerBuildFace.cpp, FaceMakerUnified.cpp: Copyright (c) 2026 the FreeCAD project
#   src/Mod/Part/App/FeatureExtrusion.cpp (FaceMakerExtrusion): Copyright (c) 2008 Werner Mayer
#   src/Mod/Part/App/TopoShapeExpansion.cpp (makeElementFace): Copyright (c) 2022 Zheng, Lei; 2023 Ondsel
"""TopoShape::makeElementFace with FreeCAD's face makers, by their class names:

    Part::FaceMakerSimple     a plane face of every closed wire
    Part::FaceMakerCheese     faces with holes, the wires sorted by their boxes (no islands in holes)
    Part::FaceMakerExtrusion  Cheese, from the wires (or the edges) of the whole input
    Part::FaceMakerBullseye   nested holes and islands (feature.py's port, a PartDesign profile's maker)
    Part::FaceMakerUnified    the default of a new Part Extrude and Revolve: the edges split where they cross, every
                              bounded region a face, kept by even-odd counting over groups of overlapping wires

make_face(shape, maker) takes a wire, an edge or a compound of them (a sketch's Shape) as FaceMaker::addTopoShape
does: a compound in the input is made into faces by a face maker of its own and kept as a compound.
"""
from __future__ import annotations

from . import feature as F

try:
    from OCP.BOPAlgo import BOPAlgo_BuilderFace
    from OCP.BOPTools import BOPTools_AlgoTools3D
    from OCP.BRep import BRep_Builder, BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepAlgoAPI import BRepAlgoAPI_BuilderAlgo, BRepAlgoAPI_Common
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy, BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, \
        BRepBuilderAPI_MakeWire
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepFill import BRepFill_Filling
    from OCP.BRepGProp import BRepGProp
    from OCP.BRepLib import BRepLib, BRepLib_FindSurface
    from OCP.Bnd import Bnd_Box
    from OCP.GProp import GProp_GProps
    from OCP.Geom import Geom_Conic, Geom_Line, Geom_Plane
    from OCP.Geom2dAPI import Geom2dAPI_InterCurveCurve, Geom2dAPI_ProjectPointOnCurve
    from OCP.GeomAPI import GeomAPI
    from OCP.GeomAbs import GeomAbs_C0, GeomAbs_Plane
    from OCP.GeomAdaptor import GeomAdaptor_Surface
    from OCP.IntTools import IntTools_Context, IntTools_FClass2d
    from OCP.ShapeAnalysis import ShapeAnalysis, ShapeAnalysis_Surface
    from OCP.ShapeFix import ShapeFix_Shape, ShapeFix_ShapeTolerance, ShapeFix_Wire
    from OCP.TopAbs import TopAbs_COMPOUND, TopAbs_EDGE, TopAbs_FACE, TopAbs_FORWARD, TopAbs_IN, TopAbs_REVERSED, \
        TopAbs_SHAPE, TopAbs_VERTEX, TopAbs_WIRE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Iterator
    from OCP.gp import gp_Dir, gp_Pnt, gp_Pnt2d
except ImportError:                     # pragma: no cover - only FreeCAD's Python lands here
    pass

CONFUSION = 1e-7
MAKERS = ("Part::FaceMakerSimple", "Part::FaceMakerCheese", "Part::FaceMakerExtrusion", "Part::FaceMakerBullseye",
          "Part::FaceMakerUnified")


def _area(s):
    p = GProp_GProps()
    BRepGProp.SurfaceProperties_s(s, p)
    return p.Mass()


def _compound(shapes):
    b = BRep_Builder()
    c = TopoDS_Compound()
    b.MakeCompound(c)
    for s in shapes:
        b.Add(c, s)
    return c


def _children(shape):
    out = []
    it = TopoDS_Iterator(shape)
    while it.More():
        out.append(it.Value())
        it.Next()
    return out


def _explore(shape, kind):
    out = []
    ex = TopExp_Explorer(shape, kind)
    while ex.More():
        out.append(ex.Current())
        ex.Next()
    return out


class _Maker:
    """FaceMaker: the input sorted into wires, faces and compounds (addTopoShape), then Build."""

    def __init__(self, kind):
        self.kind = kind
        self.wires, self.faces, self.compounds, self.sources = [], [], [], []

    def add(self, sh):
        t = sh.ShapeType()
        if t == TopAbs_COMPOUND:
            self.compounds.append(sh)
        elif t == TopAbs_WIRE:
            self.wires.append(TopoDS.Wire(sh))
        elif t == TopAbs_EDGE:
            self.wires.append(BRepBuilderAPI_MakeWire(TopoDS.Edge(sh)).Wire())
        elif t == TopAbs_FACE:
            self.faces.append(sh)
        elif t == TopAbs_VERTEX:
            pass                            # a stand-alone point of a sketch is ignored
        else:
            raise F.FeatureError("Shape must be a wire, edge or compound. Something else was supplied.")
        self.sources.append(sh)

    def build(self):
        if self.kind == "Part::FaceMakerExtrusion":     # FaceMakerExtrusion::Build: its own, over the whole input
            r = _extrusion_maker(self)
            return r[0] if r else None
        out = list(self.faces)
        out += ESSENCE[self.kind](self)
        for cmp in self.compounds:
            sub = _Maker(self.kind)
            for c in _children(cmp):         # useCompound
                sub.add(c)
            r = sub.build()
            if r is None:
                continue
            out.append(r if r.ShapeType() == TopAbs_COMPOUND else _compound([r]))
        if not out:
            return None
        return out[0] if len(out) == 1 else _compound(out)


# ── FaceMakerSimple ──
def _simple(m):
    return [BRepBuilderAPI_MakeFace(w).Shape() for w in m.wires]


# ── FaceMakerCheese ──
def _validate(face):
    if BRepCheck_Analyzer(face).IsValid():
        return face
    outer = ShapeAnalysis.OuterWire_s(face)
    fix = ShapeFix_Wire()
    fix.SetFace(face)
    fix.Load(outer)
    fix.Perform()
    mk = BRepBuilderAPI_MakeFace(fix.WireAPIMake())
    for w in _explore(face, TopAbs_WIRE):
        if not w.IsSame(outer):
            fix.Load(TopoDS.Wire(w))
            fix.Perform()
            mk.Add(fix.WireAPIMake())
    if not BRepCheck_Analyzer(mk.Face()).IsValid():
        sf = ShapeFix_Shape(mk.Face())
        sf.SetPrecision(CONFUSION)
        sf.SetMaxTolerance(CONFUSION)
        sf.Perform()
        sf.FixWireTool().Perform()
        sf.FixFaceTool().Perform()
        fixed = TopoDS.Face(sf.Shape())
        if not BRepCheck_Analyzer(fixed).IsValid():
            raise F.FeatureError("Failed to validate broken face")
        return fixed
    return mk.Face()


def _extent(w):
    box = Bnd_Box()
    if not w.IsNull():
        BRepBndLib.Add_s(w, box)
        box.SetGap(0.0)
    return box.SquareExtent()


def _is_inside(w1, w2):
    b1, b2 = Bnd_Box(), Bnd_Box()
    BRepBndLib.Add_s(w1, b1)
    b1.SetGap(0.0)
    BRepBndLib.Add_s(w2, b2)
    b2.SetGap(0.0)
    if b1.IsOut(b2):
        return False
    mk = BRepBuilderAPI_MakeFace(w1)
    if not mk.IsDone():
        raise F.FeatureError("Failed to create a face from wire in sketch")
    face = _validate(mk.Face())
    adapt = BRepAdaptor_Surface(face)
    class2d = IntTools_FClass2d(face, CONFUSION)
    sa = ShapeAnalysis_Surface(Geom_Plane(adapt.Plane()))
    for v in _explore(w2, TopAbs_VERTEX):
        uv = sa.ValueOfUV(BRep_Tool.Pnt_s(TopoDS.Vertex(v)), CONFUSION)
        return class2d.Perform(uv) == TopAbs_IN
    return False


def _cheese_face(wires):
    mk = BRepBuilderAPI_MakeFace(wires[0])
    face = mk.Face()
    if face.IsNull():
        return face
    axis = gp_Dir(0, 0, 1)
    adapt = BRepAdaptor_Surface(face)
    if adapt.GetType() == GeomAbs_Plane:
        axis = adapt.Plane().Axis().Direction()
    for w in wires[1:]:
        inner = BRepBuilderAPI_MakeFace(w).Face()
        if inner.IsNull():
            return inner
        ia = gp_Dir(0, 0, 1)
        ad = BRepAdaptor_Surface(inner)
        if ad.GetType() == GeomAbs_Plane:
            ia = ad.Plane().Axis().Direction()
        if axis.Dot(ia) < 0:
            w = TopoDS.Wire(w.Reversed())
        mk.Add(w)
    return _validate(mk.Face())


def cheese(wires):
    """FaceMakerCheese::makeFace(std::vector<TopoDS_Wire>)."""
    if not wires:
        return None
    ws = sorted(wires, key=_extent)                 # std::sort, smallest box first
    left = list(reversed(ws))                       # the largest first
    groups = []
    while left:
        w = left.pop(0)
        group = [w]
        rest = []
        for o in left:
            if _is_inside(w, o):
                group.append(o)
            else:
                rest.append(o)
        left = rest
        groups.append(group)
    if len(groups) == 1:
        return _cheese_face(groups[0])
    return _compound([f for f in (_cheese_face(g) for g in groups) if not f.IsNull()])


def _cheese(m):
    r = cheese(m.wires)
    if r is None or r.IsNull():
        return []
    return _explore(r, TopAbs_FACE) if r.ShapeType() == TopAbs_COMPOUND else [r]


def _extrusion_maker(m):
    """FaceMakerExtrusion::Build: Cheese over every wire of the whole input (its edges when it has none)."""
    shapes = m.sources
    inp = shapes[0] if len(shapes) == 1 else _compound(shapes)
    wires = [TopoDS.Wire(w) for w in F._subs(inp, TopAbs_WIRE)]
    if not wires:
        wires = [BRepBuilderAPI_MakeWire(TopoDS.Edge(e)).Wire() for e in F._subs(inp, TopAbs_EDGE)]
    r = cheese(wires) if wires else None
    if r is None or r.IsNull():
        return []
    return [r]


# ── FaceMakerBullseye ──
def _bullseye(m):
    if not m.wires:
        return []
    r = F._bullseye(m.wires)
    if r is None:
        return []
    return _children(r) if r.ShapeType() == TopAbs_COMPOUND else [r]


# ── FaceMakerBuildFace / FaceMakerUnified ──
def _find_plane(edges):
    comp = _compound([BRepBuilderAPI_Copy(e).Shape() for e in edges])
    finder = BRepLib_FindSurface(comp, -1, True)
    if not finder.Found():
        return None
    return GeomAdaptor_Surface(finder.Surface()).Plane()


def _split_self_intersecting(edges, plane):
    out = []
    for e in edges:
        edge = TopoDS.Edge(e)
        try:
            first, last = BRep_Tool.Range_s(edge)
            curve = BRep_Tool.Curve_s(edge, first, last)
            if curve is None or isinstance(curve, (Geom_Line, Geom_Conic)) or \
                    curve.IsKind(Geom_Line.get_type_descriptor()) or curve.IsKind(Geom_Conic.get_type_descriptor()):
                out.append(e)
                continue
            c2d = GeomAPI.To2d_s(curve, plane)
            if c2d is None:
                out.append(e)
                continue
            inter = Geom2dAPI_InterCurveCurve(c2d, CONFUSION)
            if inter.NbPoints() == 0:
                out.append(e)
                continue
            params = []
            for i in range(1, inter.NbPoints() + 1):
                proj = Geom2dAPI_ProjectPointOnCurve(inter.Point(i), c2d, first, last)
                for j in range(1, proj.NbPoints() + 1):
                    p = proj.Parameter(j)
                    if p - first > CONFUSION and last - p > CONFUSION:
                        params.append(p)
            if not params:
                out.append(e)
                continue
            params.sort()
            uniq = [params[0]]
            for p in params[1:]:
                if p - uniq[-1] >= CONFUSION:
                    uniq.append(p)
            prev, frags = first, []
            for p in uniq:
                if p - prev > CONFUSION:
                    me = BRepBuilderAPI_MakeEdge(curve, prev, p)
                    if me.IsDone():
                        frags.append(me.Edge())
                    prev = p
            if last - prev > CONFUSION:
                me = BRepBuilderAPI_MakeEdge(curve, prev, last)
                if me.IsDone():
                    frags.append(me.Edge())
            out += frags or [e]
        except Exception:  # noqa: BLE001 - Standard_Failure: the edge is kept as it was, as FreeCAD keeps it
            out.append(e)
    return out


def _split_at_intersections(edges):
    if len(edges) <= 1:
        return edges
    sp = BRepAlgoAPI_BuilderAlgo()
    lst = F.TopTools_ListOfShape()
    for e in edges:
        lst.Append(e)
    sp.SetArguments(lst)
    sp.SetRunParallel(True)
    sp.SetNonDestructive(True)
    sp.Build()
    if not sp.IsDone():
        return edges
    return _explore(sp.Shape(), TopAbs_EDGE)


def _bounded_faces(edges, plane):
    if not edges:
        return []
    box = Bnd_Box()
    for e in edges:
        BRepBndLib.Add_s(e, box)
    amax = max(1.0e8, 10.0 * box.SquareExtent() ** 0.5)
    base = BRepBuilderAPI_MakeFace(plane, -amax, amax, -amax, amax).Face()
    base.Orientation(TopAbs_FORWARD)
    face_edges = F.TopTools_ListOfShape()
    for e in edges:
        face_edges.Append(e.Oriented(TopAbs_FORWARD))
        face_edges.Append(e.Oriented(TopAbs_REVERSED))
    for e in face_edges:                    # BRepLib::BuildPCurveForEdgesOnPlane, edge by edge
        BRepLib.BuildPCurveForEdgeOnPlane_s(TopoDS.Edge(e), base)
    fb = BOPAlgo_BuilderFace()
    fb.SetFace(base)
    fb.SetShapes(face_edges)
    fb.SetAvoidInternalShapes(True)
    fb.Perform()
    if fb.HasErrors():
        return []
    out = []
    for a in fb.Areas():
        b = Bnd_Box()
        BRepBndLib.Add_s(a, b)
        if b.SquareExtent() > amax * amax:
            continue
        if _area(a) < CONFUSION:
            continue
        out.append(TopoDS.Face(a))
    return out


def _overlap_groups(wires, plane):
    n = len(wires)
    groups = list(range(n))
    faces = [None] * n
    boxes = [Bnd_Box() for _ in range(n)]
    areas = [0.0] * n

    def root(i):
        while groups[i] != i:
            groups[i] = groups[groups[i]]
            i = groups[i]
        return i

    closed = 0
    for i, w in enumerate(wires):
        if not BRep_Tool.IsClosed_s(w):
            continue
        mf = BRepBuilderAPI_MakeFace(plane, w)
        faces[i] = mf.Face() if mf.IsDone() else None
        if faces[i] is not None:
            BRepBndLib.AddOptimal_s(w, boxes[i], False)
            areas[i] = _area(faces[i])
            closed += 1
    if closed < 2:
        return groups, faces
    for i in range(n):
        if faces[i] is None:
            continue
        for j in range(i + 1, n):
            if faces[j] is None or boxes[i].IsOut(boxes[j]):
                continue
            common = BRepAlgoAPI_Common(faces[i], faces[j])
            if not common.IsDone() or common.Shape().IsNull():
                continue
            ca = _area(common.Shape())
            if CONFUSION < ca < areas[i] - CONFUSION and ca < areas[j] - CONFUSION:
                groups[root(i)] = root(j)
    return [root(i) for i in range(n)], faces


def _unified(m):
    if not m.wires:
        return []
    edges = [e for w in m.wires for e in _explore(w, TopAbs_EDGE)]
    plane = _find_plane(edges)
    if plane is not None:
        edges = _split_self_intersecting(edges, plane)
        edges = _split_at_intersections(edges)
        faces = _bounded_faces(edges, plane)
        if not faces:
            return []
        groups, wire_faces = _overlap_groups(m.wires, plane)
        ctx = IntTools_Context()
        out = []
        for face in faces:
            pt, pt2d = gp_Pnt(), gp_Pnt2d()
            if BOPTools_AlgoTools3D.PointInFace_s(face, pt, pt2d, ctx) != 0:
                out.append(face)
                continue
            inside = {groups[i] for i, wf in enumerate(wire_faces)
                      if wf is not None and ctx.IsPointInFace(pt, wf, CONFUSION)}
            if not inside or len(inside) % 2 == 1:
                out.append(face)
        return out
    out = []
    for w in m.wires:                       # non-planar: MakeFace, then BRepFill_Filling for a closed wire
        mf = BRepBuilderAPI_MakeFace(w)
        face = mf.Face() if mf.IsDone() else None
        if face is None and BRep_Tool.IsClosed_s(w):
            try:
                fill = BRepFill_Filling()
                for e in _explore(w, TopAbs_EDGE):
                    fill.Add(TopoDS.Edge(e), GeomAbs_C0)
                fill.Build()
                face = fill.Face() if fill.IsDone() else None
            except Exception:  # noqa: BLE001
                face = None
        if face is not None and _area(face) > CONFUSION:
            out.append(face)
    return out


def _build_face(m):
    """FaceMakerBuildFace::Build_Essence: the edges split where they cross themselves and each other, every bounded
    region a face (what a Sub-Shape Binder makes of wires, feature_subbinder.py; not offered to a Part Extrude here)."""
    edges = [e for w in m.wires for e in _explore(w, TopAbs_EDGE)]
    if not edges:
        return []
    plane = _find_plane(edges)
    if plane is None:
        return []
    edges = _split_self_intersecting(edges, plane)
    edges = _split_at_intersections(edges)
    return _bounded_faces(edges, plane)


ESSENCE = {"Part::FaceMakerSimple": _simple, "Part::FaceMakerCheese": _cheese,
           "Part::FaceMakerExtrusion": _extrusion_maker, "Part::FaceMakerBullseye": _bullseye,
           "Part::FaceMakerUnified": _unified, "Part::FaceMakerBuildFace": _build_face}


def make_face(shape, maker="Part::FaceMakerBullseye"):
    """TopoShape::makeElementFace(shape, maker): faces from a wire, an edge or a compound of them; None when the face
    maker makes none. An invalid result is repaired as makeElementFace repairs it."""
    if shape is None or shape.IsNull():
        raise F.FeatureError("Null shape")
    maker = maker or "Part::FaceMakerBullseye"
    if maker not in ESSENCE:
        raise F.FeatureError(f"{maker} is not a face maker ({', '.join(MAKERS)})")
    m = _Maker(maker)
    for s in (_children(shape) if shape.ShapeType() == TopAbs_COMPOUND else [shape]):
        if s.ShapeType() == TopAbs_COMPOUND:            # useTopoCompound: its children added one by one
            for c in _children(s):
                m.add(c)
        else:
            m.add(s)
    r = m.build()
    if r is not None and not BRepCheck_Analyzer(r).IsValid():
        ShapeFix_ShapeTolerance().LimitTolerance(r, CONFUSION, CONFUSION, TopAbs_SHAPE)
        fx = ShapeFix_Shape(r)
        fx.Perform()
        r = fx.Shape()
    return r

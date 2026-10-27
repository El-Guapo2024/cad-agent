# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses FreeCAD's TechDraw view geometry and keeps FreeCAD's licence, the GNU Lesser
# General Public License, version 2.1 or (at your option) any later version; the text is in ../ui/LICENSE.
#
#   Derived from: src/Mod/TechDraw/App/DrawViewPart.cpp (Copyright (c) 2002 Jürgen Riegel, 2013 Luke Parry, 2016 WandererFan),
#                 src/Mod/TechDraw/App/GeometryObject.cpp (Copyright (c) 2013 Luke Parry),
#                 src/Mod/TechDraw/App/ShapeUtils.cpp (Copyright (c) 2023 WandererFan),
#                 src/Mod/TechDraw/App/ShapeExtractor.cpp (Copyright (c) 2019 WandererFan),
#                 src/Mod/TechDraw/App/DrawProjectSplit.cpp (Copyright (c) 2016 WandererFan),
#                 src/Mod/TechDraw/App/Geometry.cpp (Copyright (c) 2012 Luke Parry),
#                 src/Mod/TechDraw/App/DrawUtil.cpp (Copyright (c) 2015 WandererFan),
#                 src/Mod/TechDraw/App/DrawProjGroup.cpp (Copyright (c) 2014 Joe Dowsett),
#                 src/Mod/TechDraw/App/DrawViewSection.cpp (Copyright (c) 2002 Jürgen Riegel, 2013 Luke Parry),
#                 src/Mod/TechDraw/App/EdgeWalker.cpp (Copyright (c) 2016 WandererFan)
#                 FreeCAD (https://github.com/FreeCAD/FreeCAD), commit 3160daf1e2b62b0472854da4848255c6b3ad554c
#
#   This library is free software; you can redistribute it and/or modify it under the terms of the GNU Library
#   General Public License as published by the Free Software Foundation; either version 2 of the License, or
#   (at your option) any later version.
#
#   This library is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the
#   implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Library General Public
#   License for more details.
#
# See ../NOTICE.
"""A TechDraw view's geometry, as DrawViewPart::execute makes it: what a page draws, and what EdgeN / VertexN name.

    project(shape, direction, x_direction, scale=1, rotation=0, flags) -> ViewGeometry

does what DrawViewPart::makeGeometryForShape and GeometryObject::projectShape do, with the same OCCT classes:

  1. the source is a compound of the sources' shapes (ShapeExtractor::getShapes), copied (BRepBuilderAPI_Copy)
  2. its centroid is the centre of its optimal bounding box in the projection CS (ShapeUtils::findCentroid), and the
     copy is moved so that centroid is at the origin (centerShape), scaled about the origin (scaleShape) and, with a
     Rotation, turned about the view direction (rotateShape)
  3. HLRBRep_Algo with HLRAlgo_Projector(gp_Ax2(0, Direction, XDirection)); HLRBRep_HLRToShape's ten compounds, each
     BRepLib::BuildCurves3d'd and mirrored in y (invertGeometry: the page's y points down, as Qt's)
  4. makeTDGeometry: the visible hard, outline, smooth (SmoothVisible), seam (SeamVisible) and iso lines, then with
     HardHidden the hidden hard and outline ones, then the hidden smooth, seam and iso ones as their properties ask;
     each compound scrubbed ScrubCount times (DrawProjectSplit::removeOverlapEdges, ScrubCount 1 in a fresh
     profile), its zero-length and "crazy" edges dropped (DrawUtil::isZeroEdge, isCrazy), and the vertices of each
     edge (its ends, a circle's centre) added once (Vertex::isEqual within Precision::Confusion)

so Edge<i> and Vertex<i> are the i-th of those lists, as References2D names them, and the coordinates are FreeCAD's:
millimetres on the paper (scaled), y down, the view's centre at the origin. OCP is imported inside the functions, so
the CLI's parser never loads the kernel.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

CONFUSION = 1e-7                    # Precision::Confusion()
VERTEXTOLERANCE = 2.0 * CONFUSION   # DrawUtil.h
EWTOLERANCE = 0.0001                # DrawUtil.h
FUZZYADJUST = 4.0                   # DrawUtil.h
SCRUB_COUNT = 1                     # Preferences::scrubCount(): General/ScrubCount

# GeometryObject::makeTDGeometry's order: (HLRBRep_HLRToShape compound, EdgeClass, visible)
CLASSES = ("hard", "outline", "smooth", "seam", "iso")
COMPOUND = {("hard", True): "VCompound", ("smooth", True): "Rg1LineVCompound", ("seam", True): "RgNLineVCompound",
            ("outline", True): "OutLineVCompound", ("iso", True): "IsoLineVCompound",
            ("hard", False): "HCompound", ("smooth", False): "Rg1LineHCompound", ("seam", False): "RgNLineHCompound",
            ("outline", False): "OutLineHCompound", ("iso", False): "IsoLineHCompound"}


@dataclass
class Flags:
    """The DrawViewPart properties GeometryObject reads (their defaults are a fresh profile's, DrawViewPart.cpp)."""
    smooth_visible: bool = True
    seam_visible: bool = False
    iso_visible: bool = False
    hard_hidden: bool = False
    smooth_hidden: bool = False
    seam_hidden: bool = False
    iso_hidden: bool = False
    iso_count: int = 0
    scrub_count: int = SCRUB_COUNT


@dataclass
class Edge:
    occ: object                     # the TopoDS_Edge, paper coordinates, y down
    kind: str                       # GeomType: GENERIC, CIRCLE, ARCOFCIRCLE, ELLIPSE, ARCOFELLIPSE, BSPLINE, BEZIER
    cls: str                        # hard, outline, smooth, seam, iso; cosmetic, centerline
    visible: bool
    source_index: int = 0
    cosmetic_tag: str = ""


@dataclass
class Vertex:
    x: float
    y: float
    z: float = 0.0
    visible: bool = True
    center: bool = False
    cosmetic_tag: str = ""


@dataclass
class ViewGeometry:
    edges: list = field(default_factory=list)
    vertices: list = field(default_factory=list)
    centroid: tuple = (0.0, 0.0, 0.0)       # m_saveCentroid, model space
    box: tuple = (0.0, 0.0, 0.0, 0.0)       # calcBoundingBox's x0, y0, x1, y1 (paper, y down)
    cs: object = None                       # the projection CS (gp_Ax2 at the origin)
    scale: float = 1.0
    faces: list = field(default_factory=list)   # section faces (TopoDS_Face, paper coords), DrawViewSection only
    comps: dict = field(default_factory=dict)   # HLRBRep_HLRToShape's compounds as GeometryObject keeps them (getVisHard ...)


# ─── ShapeExtractor, ShapeUtils ──────────────────────────────────────────────────────────────────────────────

def source_compound(shapes):
    """ShapeExtractor::getShapes: the sources' shapes in a compound. A compound source is added stripped of its
    infinite shapes and then once more as it is, as getShapes does (its `else if` has no `continue` before the add)."""
    from OCP.BRep import BRep_Builder
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopoDS import TopoDS_Compound
    b = BRep_Builder()
    comp = TopoDS_Compound()
    b.MakeCompound(comp)
    for s in shapes:
        if s is None or s.IsNull():
            continue
        if int(s.ShapeType().value) < int(TopAbs_SOLID.value):
            b.Add(comp, _strip_infinite(s))
        b.Add(comp, s)
    return comp


def _strip_infinite(s):
    """ShapeFinder::stripInfiniteShapes: the compound without its infinite members (a part never has any)."""
    from OCP.BRep import BRep_Builder
    from OCP.TopAbs import TopAbs_COMPOUND
    from OCP.TopoDS import TopoDS_Compound, TopoDS_Iterator
    b = BRep_Builder()
    comp = TopoDS_Compound()
    b.MakeCompound(comp)
    it = TopoDS_Iterator(s)
    while it.More():
        v = it.Value()
        if v.ShapeType() == TopAbs_COMPOUND:
            b.Add(comp, _strip_infinite(v))
        elif not _infinite(v):
            b.Add(comp, v)
        it.Next()
    return comp


def _infinite(s) -> bool:
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    box = Bnd_Box()
    BRepBndLib.Add_s(s, box)
    return box.IsOpenXmin() or box.IsOpenXmax() or box.IsOpenYmin() or box.IsOpenYmax() or box.IsOpenZmin() \
        or box.IsOpenZmax()


def projection_cs(direction, x_direction, origin=(0.0, 0.0, 0.0)):
    """DrawViewPart::getProjectionCS: gp_Ax2(origin, Direction, XDirection), or (origin, Direction) when that fails."""
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
    o, d = gp_Pnt(*origin), gp_Dir(*direction)
    try:
        return gp_Ax2(o, d, gp_Dir(*x_direction))
    except Exception:
        return gp_Ax2(o, d)


def find_centroid(shape, cs):
    """ShapeUtils::findCentroid(shape, viewAxis): the middle of the optimal box of the shape in the CS, in model space."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.gp import gp_Ax3, gp_Pnt, gp_Trsf
    t = gp_Trsf()
    t.SetTransformation(gp_Ax3(cs))
    moved = BRepBuilderAPI_Transform(shape, t).Shape()
    box = Bnd_Box()
    box.SetGap(0.0)
    BRepBndLib.AddOptimal_s(moved, box, True, False)
    x0, y0, z0, x1, y1, z1 = _box(box)
    p = gp_Pnt((x0 + x1) / 2.0, (y0 + y1) / 2.0, (z0 + z1) / 2.0)
    p.Transform(t.Inverted())
    return (p.X(), p.Y(), p.Z())


def _box(box):
    """Bnd_Box::Get (OCP 8 returns Limits, which it cannot convert): xmin, ymin, zmin, xmax, ymax, zmax."""
    a, b = box.CornerMin(), box.CornerMax()
    return a.X(), a.Y(), a.Z(), b.X(), b.Y(), b.Z()


def move_shape(shape, v):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.gp import gp_Trsf, gp_Vec
    t = gp_Trsf()
    t.SetTranslation(gp_Vec(*v))
    return BRepBuilderAPI_Transform(shape, t).Shape()


def scale_shape(shape, scale):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.gp import gp_Pnt, gp_Trsf
    t = gp_Trsf()
    t.SetScale(gp_Pnt(0, 0, 0), scale)
    return BRepBuilderAPI_Transform(shape, t).Shape()


def rotate_shape(shape, cs, degrees):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.gp import gp_Trsf
    t = gp_Trsf()
    t.SetRotation(cs.Axis(), math.radians(degrees))
    return BRepBuilderAPI_Transform(shape, t).Shape()


def invert_geometry(shape):
    """ShapeUtils::invertGeometry: mirrored in the XZ plane (gp_Ax2(origin, Y)), copying the geometry."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf
    if shape is None or shape.IsNull():
        return shape
    t = gp_Trsf()
    t.SetMirror(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 1, 0)))
    return BRepBuilderAPI_Transform(shape, t, True).Shape()


def project_point(cs_dir, cs_x, pt, invert=False):
    """DrawViewPart::projectPoint: a model point (already moved by the centroid) on the paper, x right, y up
    (or y down with invert)."""
    from OCP.gp import gp_Pnt, gp_Pnt2d
    from OCP.HLRAlgo import HLRAlgo_Projector
    pr = HLRAlgo_Projector(projection_cs(cs_dir, cs_x))
    p2 = gp_Pnt2d()
    pr.Project(gp_Pnt(*pt), p2)
    return (p2.X(), -p2.Y() if invert else p2.Y())


# ─── DrawUtil, Geometry's baseFactory ────────────────────────────────────────────────────────────────────────

def _length(edge) -> float:
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GCPnts import GCPnts_AbscissaPoint
    return GCPnts_AbscissaPoint.Length_s(BRepAdaptor_Curve(edge), CONFUSION)


def _ends(edge):
    from OCP.BRep import BRep_Tool
    from OCP.TopExp import TopExp
    a, b = BRep_Tool.Pnt_s(TopExp.FirstVertex_s(edge)), BRep_Tool.Pnt_s(TopExp.LastVertex_s(edge))
    return (a.X(), a.Y(), a.Z()), (b.X(), b.Y(), b.Z())


def is_zero_edge(edge, tol=VERTEXTOLERANCE) -> bool:
    a, b = _ends(edge)
    if math.dist(a, b) > tol:
        return False
    return _length(edge) <= tol


def is_crazy(edge) -> bool:
    """DrawUtil::isCrazy: edges too short or too long to be real, flat ellipses and wild B-splines."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_BSplineCurve, GeomAbs_Ellipse
    if edge is None or edge.IsNull():
        return True
    a = BRepAdaptor_Curve(edge)
    length = _length(edge)
    if length < 0.00001 or length > 9999.9:
        return True
    ps, pe = a.Value(a.FirstParameter()), a.Value(a.LastParameter())
    distance = ps.Distance(pe)
    ratio = length / distance if distance else math.inf
    if a.GetType() == GeomAbs_BSplineCurve and distance > 0.001 and ratio > 9999.9:
        return True
    if a.GetType() == GeomAbs_Ellipse:
        e = a.Ellipse()
        if e.MinorRadius() < 0.001 or e.MajorRadius() > 9999.9:
            return True
    return False


def geom_kind(edge) -> str:
    """BaseGeom::baseFactory's choice of type for an edge."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_BezierCurve, GeomAbs_BSplineCurve, GeomAbs_Circle, GeomAbs_Ellipse
    a = BRepAdaptor_Curve(edge)
    t = a.GetType()
    if t in (GeomAbs_Circle, GeomAbs_Ellipse):
        f, l = a.FirstParameter(), a.LastParameter()
        closed = abs(l - f) > 1.0 and a.Value(f).SquareDistance(a.Value(l)) < 0.001
        if t == GeomAbs_Circle:
            return "CIRCLE" if closed else "ARCOFCIRCLE"
        return "ELLIPSE" if closed else "ARCOFELLIPSE"
    if t == GeomAbs_BezierCurve:
        return "BEZIER"
    if t == GeomAbs_BSplineCurve:
        if _bspline_is_line(edge):
            return "GENERIC"
        return "BSPLINE"
    return "GENERIC"


def _bspline_is_line(edge) -> bool:
    """GeometryUtils::isLine: a B-spline whose poles all lie on the line from its first to its last."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    a = BRepAdaptor_Curve(edge)
    spline = a.BSpline()
    n = spline.NbPoles()
    p0, p1 = spline.Pole(1), spline.Pole(n)
    d = p0.Distance(p1)
    if d < CONFUSION:
        return False
    from OCP.gp import gp_Lin, gp_Dir, gp_Vec
    line = gp_Lin(p0, gp_Dir(gp_Vec(p0, p1)))
    return all(line.Distance(spline.Pole(i)) <= EWTOLERANCE for i in range(1, n + 1))


# ─── DrawProjectSplit::removeOverlapEdges ────────────────────────────────────────────────────────────────────

def _boxes_intersect(e0, e1) -> bool:
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    b0, b1 = Bnd_Box(), Bnd_Box()
    BRepBndLib.Add_s(e0, b0)
    b0.SetGap(0.1)
    BRepBndLib.Add_s(e1, b1)
    b1.SetGap(0.1)
    return not b0.IsOut(b1)


def _curves_coincide(e0, e1, tol) -> bool:
    from OCP.BRep import BRep_Tool
    from OCP.GeomAPI import GeomAPI_ProjectPointOnCurve
    c0, f0, l0 = _curve(e0)
    c1, f1, l1 = _curve(e1)
    if c0 is None or c1 is None:
        return False

    def on_other(src, sf, sl, dst, df, dl):
        for i in range(1, 5):
            t = sf + (sl - sf) * i / 5
            p = src.Value(t)
            proj = GeomAPI_ProjectPointOnCurve(p, dst, df, dl)
            if proj.NbPoints() == 0 or proj.LowerDistance() > tol:
                return False
        return True
    return on_other(c0, f0, l0, c1, f1, l1) and on_other(c1, f1, l1, c0, f0, l0)


def _curve(e):
    """BRep_Tool::Curve(edge, first, last) (OCP returns the curve only; the range comes from BRep_Tool::Range)."""
    from OCP.BRep import BRep_Tool
    c = BRep_Tool.Curve_s(e, 0.0, 0.0)
    if c is None:
        return None, 0.0, 0.0
    f, l = BRep_Tool.Range_s(e)
    return c, f, l


def _vertex_equal(p, q) -> bool:
    """DrawUtil::vertexEqual (vectorLess both ways false)."""
    def less(a, b):
        if math.dist(a, b) > EWTOLERANCE:
            if abs(a[0] - b[0]) >= 2.0 * EWTOLERANCE:
                return a[0] < b[0]
            if abs(a[1] - b[1]) >= 2.0 * EWTOLERANCE:
                return a[1] < b[1]
            return a[2] < b[2]
        return False
    return not less(p, q) and not less(q, p)


def _same_end_points(e1, e2) -> bool:
    a1, b1 = _ends(e1)
    a2, b2 = _ends(e2)
    return (_vertex_equal(a1, a2) and _vertex_equal(b1, b2)) or (_vertex_equal(a1, b2) and _vertex_equal(b1, a2))


E0_SUBSET, E1_SUBSET, OVERLAP, NOT_SUBSET = 0, 1, 2, 3


def _edges_of(shape) -> list:
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    out = []
    ex = TopExp_Explorer(shape, TopAbs_EDGE)
    while ex.More():
        out.append(TopoDS.Edge(ex.Current()))
        ex.Next()
    return out


def _bool_edges(op: str, e0, e1):
    from .topo_boolean import _build
    return _edges_of(_build(op, [e0], [e1], FUZZYADJUST * EWTOLERANCE))


def is_subset(e0, e1) -> int:
    if not _boxes_intersect(e0, e1):
        return NOT_SUBSET
    if not _curves_coincide(e0, e1, FUZZYADJUST * EWTOLERANCE):
        return NOT_SUBSET
    try:
        common = _bool_edges("common", e0, e1)
    except Exception:
        return NOT_SUBSET
    if not common:
        return NOT_SUBSET
    c = common[0]
    if _same_end_points(e1, c):
        return E1_SUBSET
    if _same_end_points(e0, c):
        return E0_SUBSET
    return OVERLAP


def remove_overlap_edges(edges: list) -> list:
    """DrawProjectSplit::removeOverlapEdges: an edge lying inside another is dropped; two that overlap in part are
    replaced, at the end, by their fuse's edges."""
    skip = [False] * len(edges)
    overlap = []
    for i in range(len(edges)):
        if skip[i]:
            continue
        for j in range(i + 1, len(edges)):
            if skip[j]:
                continue
            rc = is_subset(edges[i], edges[j])
            if rc == E0_SUBSET:
                skip[i] = True
                break
            if rc == E1_SUBSET:
                skip[j] = True
            elif rc == OVERLAP:
                skip[i] = skip[j] = True
                try:
                    overlap += _bool_edges("fuse", edges[i], edges[j])
                except Exception:
                    pass
                break
    return [e for e, s in zip(edges, skip) if not s] + overlap


# ─── GeometryObject ──────────────────────────────────────────────────────────────────────────────────────────

def hlr_compounds(shape, cs, iso_count=0) -> dict:
    """GeometryObject::projectShape: HLRBRep_HLRToShape's compounds, BuildCurves3d'd and inverted, by name."""
    from OCP.BRepLib import BRepLib
    from OCP.HLRAlgo import HLRAlgo_Projector
    from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
    algo = HLRBRep_Algo()
    algo.Add(shape, iso_count)
    algo.Projector(HLRAlgo_Projector(cs))
    algo.Update()
    algo.Hide()
    h = HLRBRep_HLRToShape(algo)
    out = {}
    for name in COMPOUND.values():
        c = getattr(h, name)()
        if c is None or c.IsNull():
            out[name] = None
            continue
        BRepLib.BuildCurves3d_s(c)
        out[name] = invert_geometry(c)
    return out


def _compound(edges):
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound
    b = BRep_Builder()
    comp = TopoDS_Compound()
    b.MakeCompound(comp)
    for e in edges:
        b.Add(comp, e)
    return comp


def circle_center(edge):
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    c = BRepAdaptor_Curve(edge).Circle().Location()
    return (c.X(), c.Y(), c.Z())


def add_geom_from_compound(geo: ViewGeometry, comp, cls: str, visible: bool, scrub: int):
    """GeometryObject::addGeomFromCompound."""
    if comp is None or comp.IsNull():
        return
    edges = _edges_of(comp)
    if scrub > 0:
        for _ in range(scrub):
            edges = remove_overlap_edges(edges)
        edges = _edges_of(_compound(edges))
    for i, e in enumerate(edges):
        if e.IsNull() or is_zero_edge(e) or is_crazy(e):
            continue
        kind = geom_kind(e)
        geo.edges.append(Edge(e, kind, cls, visible, i))
        a, b = _ends(e)
        center = circle_center(e) if kind in ("CIRCLE", "ARCOFCIRCLE") else None
        # the vertex test is done for all three against the list as it stood (addGeomFromCompound)
        found = [any(math.dist((v.x, v.y, v.z), p) <= CONFUSION for v in geo.vertices) for p in (a, b)]
        cfound = center is not None and any(math.dist((v.x, v.y, v.z), center) <= CONFUSION for v in geo.vertices)
        if not found[0]:
            geo.vertices.append(Vertex(*a, visible=visible))
        if not found[1]:
            geo.vertices.append(Vertex(*b, visible=visible))
        if center is not None and not cfound:
            geo.vertices.append(Vertex(*center, visible=visible, center=True))


def make_td_geometry(geo: ViewGeometry, comps: dict, flags: Flags):
    """GeometryObject::makeTDGeometry."""
    s = flags.scrub_count
    add = lambda cls, vis: add_geom_from_compound(geo, comps.get(COMPOUND[(cls, vis)]), cls, vis, s)  # noqa: E731
    add("hard", True)
    add("outline", True)
    if flags.smooth_visible:
        add("smooth", True)
    if flags.seam_visible:
        add("seam", True)
    if flags.iso_visible and flags.iso_count > 0:
        add("iso", True)
    if flags.hard_hidden:
        add("hard", False)
        add("outline", False)
    if flags.smooth_hidden:
        add("smooth", False)
    if flags.seam_hidden:
        add("seam", False)
    if flags.iso_hidden and flags.iso_count > 0:
        add("iso", False)


def bounding_box(edges) -> tuple:
    """GeometryObject::calcBoundingBox: the optimal box of every edge (0s when there are none)."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    box = Bnd_Box()
    box.SetGap(0.0)
    for e in edges:
        BRepBndLib.AddOptimal_s(e.occ, box, True, False)
    if box.IsVoid():
        return (0.0, 0.0, 0.0, 0.0)
    x0, y0, _, x1, y1, _ = _box(box)
    return (x0, y0, x1, y1)


def prepare(shape):
    """BRepBuilderAPI_Copy of the shape (DrawViewPart::makeGeometryForShape copies before it centres)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
    return BRepBuilderAPI_Copy(shape, True, False).Shape()


def project(shape, direction, x_direction, scale=1.0, rotation=0.0, flags: Flags | None = None,
            centroid=None) -> ViewGeometry:
    """DrawViewPart::makeGeometryForShape + GeometryObject::projectShape + makeTDGeometry + calcBoundingBox.
    centroid: move by this instead of the shape's own (DrawViewSection moves by its SectionOrigin)."""
    flags = flags or Flags()
    cs = projection_cs(direction, x_direction)
    local = prepare(shape)
    c = find_centroid(local, cs) if centroid is None else tuple(centroid)
    centered = move_shape(local, (-c[0], -c[1], -c[2]))
    return project_centered(centered, cs, scale, rotation, flags, c)


def project_centered(centered, cs, scale, rotation, flags, centroid) -> ViewGeometry:
    s = scale_shape(centered, scale)
    if abs(rotation) >= 1e-12:              # DrawUtil::fpCompare(Rotation, 0.0)
        s = rotate_shape(s, cs, rotation)
    geo = ViewGeometry(centroid=tuple(centroid), cs=cs, scale=scale)
    geo.comps = hlr_compounds(s, cs, flags.iso_count)
    make_td_geometry(geo, geo.comps, flags)
    geo.box = bounding_box(geo.edges)
    return geo


# ─── what a page draws ───────────────────────────────────────────────────────────────────────────────────────

def edge_json(e: Edge, samples: int = 48) -> dict:
    """An edge as the page draws it and the goldens compare it: its ends, a circle's centre and radius, an arc's
    angles and sense (AOC: cw from the mid point), and a polyline for any other curve."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    a = BRepAdaptor_Curve(e.occ)
    s, t = _ends(e.occ)
    d = {"kind": e.kind, "cls": e.cls, "visible": e.visible, "start": [s[0], s[1]], "end": [t[0], t[1]]}
    if e.cosmetic_tag:
        d["tag"] = e.cosmetic_tag
    if e.kind in ("CIRCLE", "ARCOFCIRCLE"):
        circ = a.Circle()
        c = circ.Location()
        d["center"] = [c.X(), c.Y()]
        d["radius"] = circ.Radius()
        if e.kind == "ARCOFCIRCLE":
            f, l = a.FirstParameter(), a.LastParameter()
            ps, pm, pe = a.Value(f), a.Value((f + l) / 2), a.Value(l)
            v1 = (ps.X() - pm.X(), ps.Y() - pm.Y())
            v2 = (pe.X() - pm.X(), pe.Y() - pm.Y())
            d["cw"] = (v1[0] * v2[1] - v1[1] * v2[0]) < 0
            d["large"] = abs(l - f) > math.pi
            d["mid"] = [pm.X(), pm.Y()]
            d["start"], d["end"] = [ps.X(), ps.Y()], [pe.X(), pe.Y()]
    elif e.kind == "GENERIC" and a.GetType() == 0:       # GeomAbs_Line
        pass
    else:
        f, l = a.FirstParameter(), a.LastParameter()
        pts = []
        for i in range(samples + 1):
            p = a.Value(f + (l - f) * i / samples)
            pts.append([p.X(), p.Y()])
        d["points"] = pts
        if e.kind in ("ELLIPSE", "ARCOFELLIPSE"):
            el = a.Ellipse()
            c = el.Location()
            d["center"] = [c.X(), c.Y()]
            d["major"], d["minor"] = el.MajorRadius(), el.MinorRadius()
    return d


def geometry_json(geo: ViewGeometry) -> dict:
    return {"edges": [edge_json(e) for e in geo.edges],
            "vertices": [{"x": v.x, "y": v.y, "visible": v.visible, **({"center": True} if v.center else {}),
                          **({"tag": v.cosmetic_tag} if v.cosmetic_tag else {})} for v in geo.vertices],
            "box": list(geo.box), "centroid": list(geo.centroid), "scale": geo.scale,
            "faces": [face_json(f) for f in geo.faces]}


def face_json(face) -> dict:
    """A section face as loops of points (paper coordinates, y down), the outer one first, and its area."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepGProp import BRepGProp
    from OCP.BRepTools import BRepTools_WireExplorer
    from OCP.GProp import GProp_GProps
    from OCP.TopAbs import TopAbs_REVERSED, TopAbs_WIRE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    loops = []
    ex = TopExp_Explorer(face, TopAbs_WIRE)
    while ex.More():
        wire = TopoDS.Wire(ex.Current())
        pts = []
        we = BRepTools_WireExplorer(wire)
        while we.More():
            edge = we.Current()
            a = BRepAdaptor_Curve(edge)
            f, l = a.FirstParameter(), a.LastParameter()
            n = 1 if a.GetType() == 0 else 24
            seq = [f + (l - f) * i / n for i in range(n + 1)]
            if edge.Orientation() == TopAbs_REVERSED:
                seq.reverse()
            for t in seq[:-1]:
                p = a.Value(t)
                pts.append([p.X(), p.Y()])
            we.Next()
        loops.append(pts)
        ex.Next()
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    return {"loops": loops, "area": abs(props.Mass())}


# ─── DrawViewPart::getDirsFromFront, DrawProjGroup ───────────────────────────────────────────────────────────

PROJ_TYPES = ("Front", "Left", "Right", "Rear", "Top", "Bottom", "FrontTopLeft", "FrontTopRight", "FrontBottomLeft",
              "FrontBottomRight")


def dirs_from_front(direction, x_direction, view_type: str):
    """DrawViewPart::getDirsFromFront: the Direction and XDirection of a projection from the anchor's."""
    from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Vec
    cs = projection_cs(direction, x_direction)
    d, x, y = cs.Direction(), cs.XDirection(), cs.YDirection()
    up = gp_Ax1(gp_Pnt(0, 0, 0), y)
    v = lambda g: (g.X(), g.Y(), g.Z())  # noqa: E731
    if view_type == "Front":
        return v(d), v(x)
    if view_type == "Right":
        n = cs.Rotated(up, math.pi / 2.0)
        return v(n.Direction()), v(n.XDirection())
    if view_type == "Left":
        n = cs.Rotated(up, -math.pi / 2.0)
        return v(n.Direction()), v(n.XDirection())
    if view_type == "Top":
        return v(y), v(x)
    if view_type == "Bottom":
        return v(y.Reversed()), v(x)
    if view_type == "Rear":
        return v(d.Reversed()), v(x.Reversed())
    gd, gx, gy = gp_Vec(d), gp_Vec(x), gp_Vec(y)
    if view_type == "FrontTopLeft":
        return v(gp_Dir(gd - gx + gy)), v(gp_Dir(gx + gd))
    if view_type == "FrontTopRight":
        return v(gp_Dir(gd + gx + gy)), v(gp_Dir(gx - gd))
    if view_type == "FrontBottomLeft":
        return v(gp_Dir(gd - gx - gy)), v(gp_Dir(gx + gd))
    if view_type == "FrontBottomRight":
        return v(gp_Dir(gd + gx - gy)), v(gp_Dir(gx - gd))
    raise ValueError(f"{view_type!r} is not a projection type ({', '.join(PROJ_TYPES)})")


def view_index(view_type: str, third_angle: bool) -> int:
    """DrawProjGroup::getViewIndex (and arrangeViewPointers): where a projection sits in the 3 x 4 grid."""
    table = {"Front": (4, 4), "Left": (3, 5), "Right": (5, 3), "Top": (1, 8), "Bottom": (8, 1), "Rear": (6, 6),
             "FrontTopLeft": (0, 9), "FrontTopRight": (2, 7), "FrontBottomLeft": (7, 2), "FrontBottomRight": (9, 0)}
    if view_type not in table:
        raise ValueError("Unknown view type in DrawProjGroup::getViewIndex()")
    return table[view_type][0 if third_angle else 1]


def group_position(view_type: str, boxes: dict, third_angle: bool, spacing_x: float, spacing_y: float):
    """DrawProjGroup::getXYPosition for an auto-distributed, unlocked item: boxes is {type: (width, height)} of the
    group's items (scaled), the view's offset from the group's X, Y."""
    if view_type == "Front":
        return (0.0, 0.0)
    grid: dict = {}
    for t, wh in boxes.items():
        grid[view_index(t, third_angle)] = wh
    w = lambda i: grid[i][0] if i in grid else 0.0  # noqa: E731
    h = lambda i: grid[i][1] if i in grid else 0.0  # noqa: E731
    row = lambda ids: max([h(i) for i in ids if i in grid] or [0.0])  # noqa: E731
    col = lambda ids: max([w(i) for i in ids if i in grid] or [0.0])  # noqa: E731
    top, mid, bot = row((0, 1, 2)), row((3, 4, 5)), row((7, 8, 9))
    left, middle, right = col((0, 3, 7)), col((1, 4, 8)), col((2, 5, 9))
    far = w(6) if 6 in grid else 0.0
    i = view_index(view_type, third_angle)
    have = lambda k: k in grid  # noqa: E731
    pos = {4: (0.0, 0.0)}
    if have(3) and have(4):
        pos[3] = (-(0.5 * middle + spacing_x + 0.5 * left), 0.0)
    if have(5) and have(4):
        pos[5] = (0.5 * middle + spacing_x + 0.5 * right, 0.0)
    if have(6):
        if have(5):
            pos[6] = (0.5 * middle + spacing_x + right + spacing_x + 0.5 * far, 0.0)
        elif have(4):
            pos[6] = (0.5 * middle + spacing_x + 0.5 * right, 0.0)
    if have(1) and have(4):
        pos[1] = (0.0, 0.5 * mid + spacing_y + 0.5 * top)
    if have(8) and have(4):
        pos[8] = (0.0, -(0.5 * mid + spacing_y + 0.5 * bot))
    if have(0):
        pos[0] = (-(0.5 * middle + spacing_x + 0.5 * left), 0.5 * mid + spacing_y + 0.5 * top)
    if have(2):
        pos[2] = (0.5 * middle + spacing_x + 0.5 * right, 0.5 * mid + spacing_y + 0.5 * top)
    if have(7):
        pos[7] = (-(0.5 * middle + spacing_x + 0.5 * left), -(0.5 * mid + spacing_y + 0.5 * bot))
    if have(9):
        pos[9] = (0.5 * middle + spacing_x + 0.5 * right, -(0.5 * mid + spacing_y + 0.5 * bot))
    return pos.get(i, (0.0, 0.0))


# ─── DrawViewSection ─────────────────────────────────────────────────────────────────────────────────────────

def section_cs(normal, x_direction, origin):
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
    try:
        return gp_Ax2(gp_Pnt(*origin), gp_Dir(*normal), gp_Dir(*x_direction))
    except Exception:
        return gp_Ax2(gp_Pnt(*origin), gp_Dir(*normal))


def cs_from_base(base_dir, base_x, section_origin, name: str, normal=None, x_dir=None):
    """DrawViewSection::getCSFromBase: the section's (Direction, XDirection) for a SectionDirection."""
    cs = projection_cs(base_dir, base_x, section_origin)
    d, up, right = cs.Direction(), cs.YDirection(), cs.XDirection()
    v = lambda g: (g.X(), g.Y(), g.Z())  # noqa: E731
    if name == "Up":
        return v(up.Reversed()), v(right)
    if name == "Down":
        return v(up), v(right)
    if name == "Left":
        return v(right), v(d.Reversed())
    if name == "Right":
        return v(right.Reversed()), v(d)
    if name == "Aligned":
        return tuple(normal), tuple(x_dir)
    return v(right), v(d)


def cutting_tool(normal, x_direction, origin, shape_size):
    """DrawViewSection::makeCuttingTool: a prism of the section plane's square, shape_size along the normal."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.gp import gp_Ax3, gp_Pln, gp_Vec
    pln = gp_Pln(gp_Ax3(section_cs(normal, x_direction, origin)))
    n = pln.Axis().Direction()
    face = BRepBuilderAPI_MakeFace(pln, -shape_size, shape_size, -shape_size, shape_size).Face()
    return BRepPrimAPI_MakePrism(face, gp_Vec(n).Multiplied(shape_size), False, True).Shape()


def section_cut(shape, normal, x_direction, origin):
    """DrawViewSection::execute's m_shapeSize and makeSectionCut: every solid cut by the tool, in a compound."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRep import BRep_Builder
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS_Compound
    from .topo_boolean import _build, auto_fuzzy
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, True, False)
    box.SetGap(0.0)
    size = box.SquareExtent() ** 0.5
    tool = cutting_tool(normal, x_direction, origin, size)
    my = BRepBuilderAPI_Copy(shape).Shape()
    b = BRep_Builder()
    pieces = TopoDS_Compound()
    b.MakeCompound(pieces)
    ex = TopExp_Explorer(my, TopAbs_SOLID)
    while ex.More():
        s = ex.Current()
        try:
            b.Add(pieces, _build("cut", [s], [tool], auto_fuzzy([s, tool])))
        except Exception:
            pass
        ex.Next()
    return pieces, size


def section_plane_faces(shape, normal, x_direction, origin):
    """DrawViewSection::findSectionPlaneIntersections: the cut's planar faces that lie in the section plane."""
    from OCP.BRep import BRep_Builder
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane
    from OCP.gp import gp_Ax3, gp_Pln
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS, TopoDS_Compound
    pln = gp_Pln(gp_Ax3(section_cs(normal, x_direction, origin)))
    b = BRep_Builder()
    out = TopoDS_Compound()
    b.MakeCompound(out)
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        f = TopoDS.Face(ex.Current())
        a = BRepAdaptor_Surface(f)
        if a.GetType() == GeomAbs_Plane:
            fp = a.Plane()
            if pln.Contains(fp.Location(), CONFUSION) and fp.Axis().IsParallel(pln.Axis(), 1e-12):
                b.Add(out, f)
        ex.Next()
    return out


def project_simple(shape, cs, invert=True):
    """GeometryObject::projectSimpleShape: the visible hard edges of a simple shape, inverted."""
    from OCP.BRepLib import BRepLib
    from OCP.HLRAlgo import HLRAlgo_Projector
    from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
    algo = HLRBRep_Algo()
    algo.Add(shape, 0)
    algo.Projector(HLRAlgo_Projector(cs))
    algo.Update()
    algo.Hide()
    hard = HLRBRep_HLRToShape(algo).VCompound()
    if hard is None or hard.IsNull():
        return None
    BRepLib.BuildCurves3d_s(hard)
    return invert_geometry(hard) if invert else hard


def _clean_wire(edges, tol):
    """EdgeWalker::makeCleanWire: ShapeFix_Wire on the edges (Precision 2 * EWTOLERANCE, MaxTolerance tol, reorder and
    close; OCP cannot set the fixer's other modes, which keep OCCT's defaults), WireAPIMake."""
    from OCP.ShapeExtend import ShapeExtend_WireData
    from OCP.ShapeFix import ShapeFix_Wire
    data = ShapeExtend_WireData()
    for e in edges:
        data.Add(e)
    fixer = ShapeFix_Wire()
    fixer.Load(data)
    fixer.SetPrecision(2.0 * EWTOLERANCE)
    fixer.SetMaxTolerance(tol)
    fixer.Perform()
    w = fixer.WireAPIMake()
    return None if w is None or w.IsNull() else w


def section_faces(faces_comp, cs, origin, scale, rotation):
    """DrawViewSection::alignSectionFaces + mapToPage (face finder v0.17, a fresh profile's): the section faces moved
    by SectionOrigin, scaled and rotated, each wire projected and made a face again, the biggest wire outside."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.ShapeAnalysis import ShapeAnalysis
    from OCP.ShapeFix import ShapeFix_Shape
    from OCP.TopAbs import TopAbs_FACE, TopAbs_FORWARD, TopAbs_REVERSED, TopAbs_WIRE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    s = move_shape(faces_comp, (-origin[0], -origin[1], -origin[2]))
    s = scale_shape(s, scale)
    if abs(rotation) >= 1e-12:
        s = rotate_shape(s, cs, rotation)
    out = []
    ex = TopExp_Explorer(s, TopAbs_FACE)
    while ex.More():
        face = TopoDS.Face(ex.Current())
        wires = []
        wx = TopExp_Explorer(face, TopAbs_WIRE)
        while wx.More():
            proj = project_simple(wx.Current(), cs)
            if proj is not None:
                w = _clean_wire(_edges_of(proj), 2 * EWTOLERANCE)
                if w is not None and BRep_Tool.IsClosed_s(w) and abs(ShapeAnalysis.ContourArea_s(w)) > 0.000001:
                    wires.append(w)
            wx.Next()
        ex.Next()
        if not wires:
            continue
        wires.sort(key=lambda w: -ShapeAnalysis.ContourArea_s(w))      # EdgeWalker::wireCompare (signed)
        outer = TopoDS.Wire(wires[0].Oriented(TopAbs_FORWARD))
        mk = BRepBuilderAPI_MakeFace(outer)
        blank = mk.Face()
        if len(wires) > 1:
            mk = BRepBuilderAPI_MakeFace(blank)
            for w in wires[1:]:
                mk.Add(TopoDS.Wire(w.Oriented(TopAbs_REVERSED)))
            if not mk.IsDone():
                continue
            blank = mk.Face()
        fix = ShapeFix_Shape()
        fix.Init(blank)
        fix.Perform()
        f2 = fix.Shape()
        fx = TopExp_Explorer(f2, TopAbs_FACE)
        if fx.More():
            out.append(TopoDS.Face(fx.Current()))
    return out


def project_section(shape, normal, x_direction, origin, direction, view_x, scale=1.0, rotation=0.0,
                    flags: Flags | None = None) -> ViewGeometry:
    """DrawViewSection's recompute: the cut, its geometry moved by SectionOrigin (prepareShape), the section faces."""
    flags = flags or Flags()
    pieces, _size = section_cut(shape, normal, x_direction, origin)
    cs = projection_cs(direction, view_x)
    centered = move_shape(pieces, (-origin[0], -origin[1], -origin[2]))
    centroid = find_centroid(pieces, cs)
    geo = project_centered(centered, cs, scale, rotation, flags, centroid)
    geo.faces = section_faces(section_plane_faces(pieces, normal, x_direction, origin), cs, origin, scale, rotation)
    return geo

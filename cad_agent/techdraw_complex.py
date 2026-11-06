# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses FreeCAD's TechDraw complex section and keeps FreeCAD's licence, the GNU Lesser
# General Public License, version 2.1 or (at your option) any later version; the text is in ../ui/LICENSE.
#
#   Derived from: src/Mod/TechDraw/App/DrawComplexSection.cpp (Copyright (c) 2022 WandererFan),
#                 src/Mod/TechDraw/App/GeometryObject.cpp (Copyright (c) 2013 Luke Parry)
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
"""A complex section, ProjectionStrategy Offset: DrawViewSection's recompute with DrawComplexSection's cutting tool,
the profile (CuttingToolWireObject, here its points in model space) closed and extruded along the base view's
direction (makeCuttingTool, cuttingToolFromProfile, closeProfileForCut, profileToSolid), and its section faces the cut's
faces where they meet the profile extruded as a sheet (singleToolIntersections). Aligned and NoParallel are not ported."""
from __future__ import annotations

import math

from .techdraw_broken import closest_basis_oriented
from .techdraw_view import EWTOLERANCE, Flags, find_centroid, move_shape, project_centered, projection_cs, \
    section_faces


def _v(p):
    from OCP.gp import gp_Pnt
    return gp_Pnt(*p)


def _edge(a, b):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    return BRepBuilderAPI_MakeEdge(_v(a), _v(b)).Edge()


def _wire(edges):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeWire
    mk = BRepBuilderAPI_MakeWire()
    for e in edges:
        mk.Add(e)
    return mk.Wire()


def profile_wire(points):
    """makeProfileWire: the profile's polyline as a wire (makeNoseToTailWire keeps a polyline's order)."""
    pts = [tuple(map(float, p)) for p in points]
    return _wire([_edge(a, b) for a, b in zip(pts, pts[1:])]), pts


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def _len(a):
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def _unit(a):
    n = _len(a)
    return _mul(a, 1.0 / n) if n > 0 else a


def _flat(points, base_dir):
    """GeometryObject::simpleProjection onto the base view's paper plane through the origin: each point moved along
    the plane's normal onto it."""
    n = _unit(base_dir)
    return [_sub(p, _mul(n, p[0] * n[0] + p[1] * n[1] + p[2] * n[2])) for p in points]


def close_profile_for_cut(points, base_dir, section_normal, dmax):
    """closeProfileForCut: the profile flattened onto the base view's plane, its first and last segment pushed out to
    dMax from the middle of its ends, closed by an arc through the point dMax away towards SectionNormal * dMax."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from OCP.GC import GC_MakeArcOfCircle
    flat = _flat(points, base_dir)
    first, last = flat[0], flat[-1]
    mid = _mul(_add(first, last), 0.5)
    away = _unit(_sub(_mul(section_normal, dmax), mid))
    segs = list(zip(flat, flat[1:]))
    if len(segs) == 1:
        return _close_single(segs[0], section_normal, dmax)
    a, b = segs[0]
    d = _unit(_sub(a, b))
    first_end = _add(b, _mul(d, dmax - _len(_sub(mid, b))))
    first_edge = _edge(b, first_end)
    a, b = segs[-1]
    d = _unit(_sub(b, a))
    last_end = _add(a, _mul(d, dmax - _len(_sub(mid, a))))
    last_edge = _edge(a, last_end)
    on_arc = _add(mid, _mul(away, dmax))
    mk = GC_MakeArcOfCircle(_v(last_end), _v(on_arc), _v(first_end))
    if not mk.IsDone():
        raise ValueError("Complex section failed to create circular arc to close profile")
    arc = BRepBuilderAPI_MakeEdge(mk.Value()).Edge()
    edges = [first_edge] + [_edge(p, q) for p, q in segs[1:-1]] + [last_edge, arc]
    return _wire(edges)


def _close_single(seg, section_normal, dmax):
    """closeSingleEdgeProfile, its midpoint as FreeCAD computes it (first + second / 2)."""
    a, b = seg
    mid = _add(a, _mul(b, 0.5))
    away = _unit(_sub(_mul(section_normal, dmax), mid))
    far0, far1 = _add(a, _mul(away, dmax)), _add(b, _mul(away, dmax))
    return _wire([_edge(a, b), _edge(b, far1), _edge(far1, far0), _edge(far0, a)])


def cutting_tool(points, base_dir, section_normal, dmax):
    """makeCuttingTool: the tool solid (an open profile closed and extruded 2 dMax along the reference axis, moved
    back dMax; a closed one extruded along its face's normal) and the tool face shape (the profile itself extruded the
    same way), which singleToolIntersections meets the cut with."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.gp import gp_Vec
    wire, pts = profile_wire(points)
    ref = closest_basis_oriented(_unit(base_dir))                # getReferenceAxis
    closed = _len(_sub(pts[0], pts[-1])) < 1e-7
    if closed:
        face = BRepBuilderAPI_MakeFace(wire).Face()
        n = _face_normal(face)
        tool = BRepPrimAPI_MakePrism(face, gp_Vec(*_mul(n, 2 * dmax))).Shape()
        return move_shape(tool, _mul(n, -dmax)), None
    closed_wire = close_profile_for_cut(pts, base_dir, section_normal, dmax)
    face = BRepBuilderAPI_MakeFace(closed_wire).Face()
    solid = BRepPrimAPI_MakePrism(face, gp_Vec(*_mul(ref, 2 * dmax))).Shape()
    solid = move_shape(solid, _mul(ref, -dmax))
    sheet = BRepPrimAPI_MakePrism(wire, gp_Vec(*_mul(ref, 2 * dmax))).Shape()
    sheet = move_shape(sheet, _mul(ref, -dmax))
    from OCP.TopAbs import TopAbs_COMPOUND, TopAbs_COMPSOLID
    if solid.ShapeType() in (TopAbs_COMPSOLID, TopAbs_COMPOUND):
        solid = _remove_empty(solid)
    return solid, sheet


def _face_normal(face):
    """getFaceNormal: the normal at the middle of the face's parameter range (BRepLProp_SLProps, tolerance 0.01), Z when
    it has none."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepLProp import BRepLProp_SLProps
    a = BRepAdaptor_Surface(face)
    u = (a.FirstUParameter() + a.LastUParameter()) / 2
    v = (a.FirstVParameter() + a.LastVParameter()) / 2
    prop = BRepLProp_SLProps(a, u, v, 1, 0.01)
    if prop.IsNormalDefined():
        n = prop.Normal()
        return (n.X(), n.Y(), n.Z())
    return (0.0, 0.0, 1.0)


def _remove_empty(shape):
    """removeEmptyShapes: the solids of more than EWTOLERANCE volume."""
    from OCP.BRep import BRep_Builder
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS_Compound
    comp = TopoDS_Compound()
    b = BRep_Builder()
    b.MakeCompound(comp)
    ex = TopExp_Explorer(shape, TopAbs_SOLID)
    while ex.More():
        g = GProp_GProps()
        BRepGProp.VolumeProperties_s(ex.Current(), g)
        if g.Mass() > EWTOLERANCE:
            b.Add(comp, ex.Current())
        ex.Next()
    return comp


def _cut(shape, tool):
    """DrawViewSection::makeSectionCut: each solid less the tool (FCBRepAlgoAPI_Cut), in a compound."""
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS_Compound
    from .topo_boolean import _build, auto_fuzzy
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
    return pieces


def tool_intersections(cut, sheet):
    """singleToolIntersections: each face of the cut whose box meets the tool face shape's (0.1 gap), its Common with
    it (fuzzy EWTOLERANCE), the faces of that."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRep import BRep_Builder
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.BRepBndLib import BRepBndLib
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS_Compound, TopoDS_Iterator
    try:
        from OCP.TopTools import TopTools_ListOfShape
    except ImportError:
        from OCP.collections import List_TopoDS_Shape as TopTools_ListOfShape
    b = BRep_Builder()
    out = TopoDS_Compound()
    b.MakeCompound(out)
    if sheet is None:
        return out
    box1 = Bnd_Box()
    BRepBndLib.Add_s(sheet, box1)
    box1.SetGap(0.1)
    ex = TopExp_Explorer(cut, TopAbs_FACE)
    while ex.More():
        face = ex.Current()
        box0 = Bnd_Box()
        BRepBndLib.Add_s(face, box0)
        box0.SetGap(0.1)
        if not box0.IsOut(box1):
            op = BRepAlgoAPI_Common()
            op.SetFuzzyValue(EWTOLERANCE)
            a1, a2 = TopTools_ListOfShape(), TopTools_ListOfShape()
            a1.Append(face)
            a2.Append(sheet)
            op.SetArguments(a1)
            op.SetTools(a2)
            op.Build()
            res = op.Shape()
            if not res.IsNull() and TopoDS_Iterator(res).More():
                fx = TopExp_Explorer(res, TopAbs_FACE)
                while fx.More():
                    b.Add(out, fx.Current())
                    fx.Next()
        ex.Next()
    return out


def project_complex_section(shape, points, base_dir, section_normal, x_direction, origin, direction, view_x,
                            scale=1.0, rotation=0.0, flags: Flags | None = None):
    """DrawComplexSection's recompute, Offset: m_shapeSize, the tool, the cut, its geometry moved by SectionOrigin, the
    section faces where the cut meets the profile."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    flags = flags or Flags()
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, True, False)
    box.SetGap(0.0)
    dmax = box.SquareExtent() ** 0.5
    tool, sheet = cutting_tool(points, base_dir, tuple(section_normal), dmax)
    pieces = _cut(shape, tool)
    cs = projection_cs(direction, view_x)
    centered = move_shape(pieces, (-origin[0], -origin[1], -origin[2]))
    centroid = find_centroid(pieces, cs)
    geo = project_centered(centered, cs, scale, rotation, flags, centroid)
    geo.faces = section_faces(tool_intersections(pieces, sheet), cs, origin, scale, rotation)
    return geo


# ── ProjectionStrategy Aligned (and NoParallel): makeAlignedPieces ─────────────────────────────────────────────────

def _segment_ends(e):
    from OCP.BRep import BRep_Tool
    from OCP.TopExp import TopExp
    from OCP.TopoDS import TopoDS_Vertex
    a, b = TopoDS_Vertex(), TopoDS_Vertex()
    TopExp.Vertices_s(e, a, b)
    p, q = BRep_Tool.Pnt_s(a), BRep_Tool.Pnt_s(b)
    return (p.X(), p.Y(), p.Z()), (q.X(), q.Y(), q.Z())


def _unique_edges(wire):
    """getUniqueEdges: the wire's edges, each once (TopTools_IndexedMapOfShape over an explorer)."""
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    out = []
    ex = TopExp_Explorer(wire, TopAbs_EDGE)
    while ex.More():
        e = ex.Current()
        if not any(e.IsSame(o) for o in out):
            out.append(e)
        ex.Next()
    return [TopoDS.Edge(e) for e in out]


def _point_on_face(p, face) -> bool:
    """pointOnFace: within EWTOLERANCE of the face (DrawUtil::simpleMinDist)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    v = BRepBuilderAPI_MakeVertex(_v(p)).Vertex()
    d = BRepExtrema_DistShapeShape(v, face)
    return d.IsDone() and d.Value() < EWTOLERANCE


def _contains_ends(edge, face) -> bool:
    a, b = _segment_ends(edge)
    return _point_on_face(a, face) and _point_on_face(b, face)


def _is_planar(face) -> bool:
    from OCP.BRep import BRep_Tool
    from OCP.GeomLib import GeomLib_IsPlanarSurface
    return GeomLib_IsPlanarSurface(BRep_Tool.Surface_s(face)).IsPlanar()


def _faces(shape):
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    out = []
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        out.append(TopoDS.Face(ex.Current()))
        ex.Next()
    return out


def segment_view_directions(wire, points, base_dir, section_normal, dmax):
    """getSegmentViewDirections: for each profile segment, the outward normal of the side of the profile's tool solid
    that holds it (a FORWARD face's normal turned round), the top and bottom faces skipped; by segment index."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.TopAbs import TopAbs_FORWARD
    from OCP.gp import gp_Vec
    ref = closest_basis_oriented(_unit(base_dir))
    closed = close_profile_for_cut(points, base_dir, section_normal, dmax)
    solid = BRepPrimAPI_MakePrism(BRepBuilderAPI_MakeFace(closed).Face(), gp_Vec(*_mul(ref, 2 * dmax))).Shape()
    solid = move_shape(solid, _mul(ref, -dmax))
    edges = _unique_edges(wire)
    out = []
    for face in _faces(solid):
        n = _face_normal(face)
        if face.Orientation() == TopAbs_FORWARD:
            n = _mul(n, -1.0)
        if abs(abs(n[0] * ref[0] + n[1] * ref[1] + n[2] * ref[2]) - 1.0) < EWTOLERANCE:
            continue
        if not _is_planar(face):
            continue
        for i, seg in enumerate(edges):
            if _contains_ends(seg, face):
                out.append((i, n))
                break
    out.sort(key=lambda kv: kv[0])          # std::sort with normalLess (by index; equal ones may come either way)
    return out


def _common(a, b):
    """shapeShapeIntersect: BRepAlgoAPI_Common, fuzzy EWTOLERANCE; None when it is empty."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.TopoDS import TopoDS_Iterator
    try:
        from OCP.TopTools import TopTools_ListOfShape
    except ImportError:
        from OCP.collections import List_TopoDS_Shape as TopTools_ListOfShape
    op = BRepAlgoAPI_Common()
    op.SetFuzzyValue(EWTOLERANCE)
    a1, a2 = TopTools_ListOfShape(), TopTools_ListOfShape()
    a1.Append(a)
    a2.Append(b)
    op.SetArguments(a1)
    op.SetTools(a2)
    op.Build()
    r = op.Shape()
    return None if r.IsNull() or not TopoDS_Iterator(r).More() else r


def _box(shape):
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from .techdraw_view import _box as box_of
    b = Bnd_Box()
    b.SetGap(0.0)
    BRepBndLib.AddOptimal_s(shape, b, True, False)
    return box_of(b)


def _centroid(shape):
    """ShapeUtils::findCentroid(shape): the middle of its optimal box."""
    x0, y0, z0, x1, y1, z1 = _box(shape)
    return ((x0 + x1) / 2.0, (y0 + y1) / 2.0, (z0 + z1) / 2.0)


def _translate(shape, v):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.gp import gp_Trsf, gp_Vec
    t = gp_Trsf()
    t.SetTranslation(gp_Vec(*v))
    return BRepBuilderAPI_Transform(shape, t, True).Shape()


def _mask(v, d):
    """DrawUtil::maskDirection: v with its component along the cardinal direction d zeroed."""
    for k in range(3):
        if abs(abs(d[k]) - 1.0) < EWTOLERANCE:
            return tuple(0.0 if i == k else v[i] for i in range(3))
    return (0.0, 0.0, 0.0)


def aligned_pieces(shape, points, base_dir, section_normal, x_direction, origin, direction, view_x, dmax, strategy):
    """makeAlignedPieces: the shape cut by each profile segment's piece of the tool face shape pushed along the
    segment's view direction, each piece centred, turned so its segment faces the section direction, laid on the paper
    plane and placed one after another along the profile's direction, the whole centred and set in the projection CS."""
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy, BRepBuilderAPI_Transform
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.TopoDS import TopoDS_Compound
    from OCP.gp import gp_Ax1, gp_Ax3, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
    from .techdraw_view import section_cs
    wire, pts = profile_wire(points)
    scs = section_cs(section_normal, x_direction, origin)
    sn = _unit(tuple(section_normal))
    vec = _unit(_sub(pts[-1], pts[0]))                               # makeProfileVector
    closed = _len(_sub(pts[0], pts[-1])) < 1e-7
    sd = scs.Direction()
    if not closed and abs(abs(vec[0] * sd.X() + vec[1] * sd.Y() + vec[2] * sd.Z()) - 1.0) < EWTOLERANCE:
        raise ValueError("Profile is parallel to Section Normal")    # canBuild
    edges = _unique_edges(wire)
    if not edges:
        raise ValueError("Complex section: profile wire has no edges.")
    # getReversers
    sx, sy = scs.XDirection(), scs.YDirection()
    vdot = vec[0] * sy.X() + vec[1] * sy.Y() + vec[2] * sy.Z()
    vertical = not abs(vdot) < EWTOLERANCE
    horiz_rev = -1.0 if vec[0] * sx.X() + vec[1] * sx.Y() + vec[2] * sx.Z() < 0.0 else 1.0
    vert_rev = -1.0 if vdot < 0.0 else 1.0
    n = len(edges)
    pieces = [None] * n
    xs, ys, verticals = [0.0] * n, [0.0] * n, [0.0] * n
    ref = closest_basis_oriented(_unit(base_dir))
    normals = segment_view_directions(wire, pts, base_dir, tuple(section_normal), dmax)
    _tool, sheet = cutting_tool(points, base_dir, tuple(section_normal), dmax)
    pcs = projection_cs(direction, view_x)
    std = gp_Ax3()
    for face in (_faces(sheet) if sheet is not None else []):
        if not _is_planar(face):
            continue
        idx = next((i for i, seg in enumerate(edges) if _contains_ends(seg, face)), -1)     # findNormalForFace
        if idx < 0:
            raise ValueError("DCS::findNormalForFace - did not find normal for face!")
        kv = next((kv for kv in normals if kv[0] == idx), None)
        if kv is None:
            raise ValueError("DCS::findNormalForFace - no keyValue pair for segment!")
        seg_n = _unit(_mul(kv[1], -1.0))
        if strategy == "NoParallel" and abs(sn[0] * seg_n[0] + sn[1] * seg_n[1] + sn[2] * seg_n[2]) < EWTOLERANCE:
            continue                                                  # showSegment
        # cutAndRotatePiece
        tool = BRepPrimAPI_MakePrism(face, gp_Vec(*_mul(seg_n, dmax))).Shape()
        inter = _common(tool, shape)
        if inter is None:
            continue
        c = _centroid(inter)
        masked = _sub(c, _mask(c, ref))
        verticals[idx] = masked[0] + masked[1] + masked[2]
        centred = _translate(inter, _mul(c, -1.0))
        angle = gp_Vec(scs.Direction().Reversed()).AngleWithRef(gp_Vec(*seg_n), gp_Vec(*ref))
        piece_cs = gp_Ax3()
        piece_cs.Rotate(gp_Ax1(gp_Pnt(0.0, 0.0, 0.0), gp_Dir(*ref)), angle)
        rot = gp_Trsf()
        rot.SetTransformation(std, piece_cs)
        rotated = BRepBuilderAPI_Transform(centred, rot, True).Shape()
        # getAlignedSize
        al = gp_Trsf()
        al.SetTransformation(std, gp_Ax3(pcs))
        aligned = BRepBuilderAPI_Transform(BRepBuilderAPI_Copy(rotated).Shape(), al).Shape()
        ac = _centroid(aligned)
        aligned = _translate(aligned, _mul(ac, -1.0))
        x0, y0, z0, x1, y1, z1 = _box(aligned)
        xs[idx], ys[idx] = x1 - x0, y1 - y0
        pieces[idx] = _translate(aligned, (0.0, 0.0, -z1))           # movePieceToPaperPlane
    if not any(p is not None for p in pieces):
        return TopoDS_Compound()
    rev = vert_rev if vertical else horiz_rev
    move_axis, align_axis = ((0.0, 1.0, 0.0), (1.0, 0.0, 0.0)) if vertical else ((1.0, 0.0, 0.0), (0.0, -1.0, 0.0))
    mv = _mul(move_axis, rev)
    cursor = 0.0
    for i in range(n):
        size = ys[i] if vertical else xs[i]
        if pieces[i] is not None:                                     # distributePiece
            total = cursor + size / 2
            pieces[i] = _translate(pieces[i], _add(_mul(mv, total), _mul(align_axis, -verticals[i])))
        cursor += size
    comp = TopoDS_Compound()
    b = BRep_Builder()
    b.MakeCompound(comp)
    for p in pieces:
        if p is not None:
            b.Add(comp, p)
    centred = move_shape(comp, _mul(mv, cursor / -2))
    t = gp_Trsf()
    t.SetTransformation(gp_Ax3(pcs), std)
    return BRepBuilderAPI_Transform(centred, t).Shape()


def aligned_intersections(prepared, section_normal):
    """alignedToolIntersections: the prepared shape's faces in common with the plane through the origin normal to
    SectionNormal (getSectionPlane for Aligned)."""
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.Precision import Precision
    from OCP.TopoDS import TopoDS_Compound
    from OCP.gp import gp_Ax3, gp_Dir, gp_Pln, gp_Pnt
    inf = Precision.Infinite_s()
    plane = BRepBuilderAPI_MakeFace(gp_Pln(gp_Ax3(gp_Pnt(0, 0, 0), gp_Dir(*section_normal))), -inf, inf, -inf, inf).Face()
    pbox = Bnd_Box()
    BRepBndLib.Add_s(plane, pbox)
    pbox.SetGap(0.1)
    out = TopoDS_Compound()
    b = BRep_Builder()
    b.MakeCompound(out)
    for face in _faces(prepared):
        fb = Bnd_Box()
        BRepBndLib.Add_s(face, fb)
        fb.SetGap(0.1)
        if fb.IsOut(pbox):
            continue
        r = _common(face, plane)
        if r is not None:
            for f in _faces(r):
                b.Add(out, f)
    return out


def project_aligned_section(shape, points, base_dir, section_normal, x_direction, origin, direction, view_x,
                            scale=1.0, rotation=0.0, flags: Flags | None = None, strategy="Aligned"):
    """DrawComplexSection's recompute, Aligned or NoParallel: the aligned pieces (prepareShape scales and turns them),
    their projection, the section faces where they meet the paper plane, projected as they are (mapToPage)."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from .techdraw_view import rotate_shape, scale_shape
    flags = flags or Flags()
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, True, False)
    box.SetGap(0.0)
    dmax = box.SquareExtent() ** 0.5
    aligned = aligned_pieces(shape, points, base_dir, section_normal, x_direction, origin, direction, view_x, dmax,
                             strategy)
    cs = projection_cs(direction, view_x)
    centroid = find_centroid(shape, cs)
    geo = project_centered(aligned, cs, scale, rotation, flags, centroid)
    prepared = scale_shape(aligned, scale)
    if abs(rotation) >= 1e-12:
        prepared = rotate_shape(prepared, cs, rotation)
    geo.faces = section_faces(aligned_intersections(prepared, tuple(section_normal)), cs, (0.0, 0.0, 0.0), 1.0, 0.0)
    return geo

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

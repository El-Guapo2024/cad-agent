# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses FreeCAD's TechDraw face finder and keeps FreeCAD's licence, the GNU Lesser
# General Public License, version 2.1 or (at your option) any later version; the text is in ../ui/LICENSE.
#
#   Derived from: src/Mod/TechDraw/App/DrawViewPart.cpp (Copyright (c) 2002 Jürgen Riegel, 2013 Luke Parry, 2016 WandererFan),
#                 src/Mod/TechDraw/App/DrawProjectSplit.cpp (Copyright (c) 2016 WandererFan),
#                 src/Mod/TechDraw/App/EdgeWalker.cpp (Copyright (c) 2016 WandererFan),
#                 src/Mod/TechDraw/App/DrawUtil.cpp (Copyright (c) 2015 WandererFan),
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
"""A view's faces: DrawViewPart::extractFaces with the face finder of a fresh profile (Preferences > TechDraw >
General, FaceFinderVersion unset: v0.17, findFacesV0_17).

Face<n> is the n-th closed wire of the view's visible edges (hard and outline ones, the smooth and seam ones when the
view draws them, and its cosmetic edges: GeometryObject::getVisibleFaceEdges): the edges are copied, split where a
vertex of another edge lies on them (isOnEdge), made unique (removeDuplicateEdges), and EdgeWalker walks the planar
graph they make: the face of every cycle, the outside of each connected piece as well, a wire used twice kept once,
sorted by the area it encloses, the biggest first (a hole is not cut out of the face around it: each wire is a face).
FreeCAD walks boost::planar_face_traversal over the embedding the incidence angles give; this walks the same
embedding (the edges at a vertex ordered by the angle they come in at), so the wires are the same, and their order
too where the areas differ. Only the order of faces of equal area (std::sort's) is not FreeCAD's guarantee.
"""
from __future__ import annotations

import math
from functools import cmp_to_key

from .techdraw_view import CONFUSION, EWTOLERANCE, _clean_wire, _edges_of, _ends, is_zero_edge

DEFAULT_VISIBLE = ("hard", "outline")


def face_edges(geo, smooth_visible: bool = True, seam_visible: bool = False) -> list:
    """GeometryObject::getVisibleFaceEdges: the view's visible edges that bound faces."""
    out = []
    for e in geo.edges:
        if not e.visible:
            continue
        if e.cls in DEFAULT_VISIBLE or e.cls == "cosmetic":
            out.append(e.occ)
        elif e.cls == "smooth" and smooth_visible:
            out.append(e.occ)
        elif e.cls == "seam" and seam_visible:
            out.append(e.occ)
    return out


def find_faces(edges: list) -> list:
    """findFacesV0_17: the wires of the faces the edges make (TopoDS_Wire list)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
    from OCP.TopoDS import TopoDS
    copies = [TopoDS.Edge(BRepBuilderAPI_Copy(e, True, False).Shape()) for e in edges]
    non_zero = [e for e in copies if not is_zero_edge(e)]
    new_edges = remove_duplicate_edges(split_edges(non_zero))
    if not new_edges:
        return []
    return walk(new_edges)


# ─── DrawProjectSplit ────────────────────────────────────────────────────────────────────────────────────────

def _vertex_pnt(v):
    from OCP.BRep import BRep_Tool
    p = BRep_Tool.Pnt_s(v)
    return p


def _is_on_edge(edge, vertex, allow_ends: bool):
    """isOnEdge: (True, parameter) when the vertex lies on the edge (within Precision::Confusion)."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.GeomAPI import GeomAPI_ProjectPointOnCurve
    from OCP.TopExp import TopExp
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(edge, box, True, False)
    box.SetGap(0.1)
    pt = _vertex_pnt(vertex)
    if not box.IsVoid() and box.IsOut(pt):
        return False, -2.0
    d = BRepExtrema_DistShapeShape(vertex, edge)
    if not d.IsDone() or d.Value() >= CONFUSION:
        return False, -2.0
    adapt = BRepAdaptor_Curve(edge)
    curve = adapt.Curve().Curve()
    proj = GeomAPI_ProjectPointOnCurve(pt, curve)
    param = proj.LowerDistanceParameter() if proj.NbPoints() else -2.0
    ends = (TopExp.FirstVertex_s(edge), TopExp.LastVertex_s(edge))
    if any(_vertex_pnt(v).Distance(pt) <= CONFUSION for v in ends):
        if not allow_ends:
            return False, param
    return True, param


def split_edges(edges: list) -> list:
    """The splitting of findFacesV0_17: each edge split at the parameters where a vertex of another edge touches it,
    the splits sorted by edge then parameter, the repeated ones dropped."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from OCP.TopExp import TopExp
    boxes = []
    for e in edges:
        b = Bnd_Box()
        BRepBndLib.AddOptimal_s(e, b)
        b.SetGap(0.1)
        boxes.append(b)
    splits = []
    for io, outer in enumerate(edges):
        if boxes[io].IsVoid() or is_zero_edge(outer):
            continue
        ends = (TopExp.FirstVertex_s(outer), TopExp.LastVertex_s(outer))
        for ii, inner in enumerate(edges):
            if ii == io or is_zero_edge(inner) or boxes[ii].IsVoid() or boxes[io].IsOut(boxes[ii]):
                continue
            for v in ends:
                on, param = _is_on_edge(inner, v, False)
                if on:
                    splits.append((ii, param))
    splits.sort(key=lambda s: (s[0], s[1]))
    uniq = []
    for s in splits:
        if uniq and uniq[-1][0] == s[0] and abs(uniq[-1][1] - s[1]) < CONFUSION:
            continue
        uniq.append(s)
    by_edge: dict = {}
    for i, p in uniq:
        by_edge.setdefault(i, []).append(p)
    out = []
    for i, e in enumerate(edges):
        if i not in by_edge:
            out.append(e)
            continue
        adapt = BRepAdaptor_Curve(e)
        c = adapt.Curve().Curve()
        first, last = adapt.FirstParameter(), adapt.LastParameter()
        if first > last:
            continue
        parms = [first] + by_edge[i] + [last]
        for a, b in zip(parms, parms[1:]):
            try:
                mk = BRepBuilderAPI_MakeEdge(c, a, b)
                if mk.IsDone():
                    out.append(mk.Edge())
            except Exception:
                pass
    return out


def _angle_with_x(edge, at_first: bool) -> float:
    """DrawUtil::angleWithX(edge, vertex): the angle of the tangent at the first or last end."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.gp import gp_Pnt, gp_Vec
    adapt = BRepAdaptor_Curve(edge)
    param = adapt.FirstParameter() if at_first else adapt.LastParameter()
    p, d = gp_Pnt(), gp_Vec()
    adapt.Curve().Curve().D1(param, p, d)
    a = math.atan2(d.Y(), d.X())
    return a + 2.0 * math.pi if a < 0 else a


def _vector_less(a, b) -> bool:
    """DrawUtil::vectorLess."""
    if math.dist(a, b) > EWTOLERANCE:
        if abs(a[0] - b[0]) >= 2.0 * EWTOLERANCE:
            return a[0] < b[0]
        if abs(a[1] - b[1]) >= 2.0 * EWTOLERANCE:
            return a[1] < b[1]
        return a[2] < b[2]
    return False


def remove_duplicate_edges(edges: list) -> list:
    """removeDuplicateEdges: the edges sorted (edgeLess, then reversed) and the equal ones taken out."""
    items = []
    for idx, e in enumerate(edges):
        s, t = _ends(e)
        it = {"start": s, "end": t, "sa": _angle_with_x(e, True), "ea": _angle_with_x(e, False), "idx": idx}
        if _vector_less(it["end"], it["start"]):
            it["start"], it["end"], it["sa"], it["ea"] = it["end"], it["start"], it["ea"], it["sa"]
        items.append(it)

    def fp(a, b):
        return abs(a - b) < 1e-7

    def less(a, b) -> bool:
        if not math.dist(a["start"], b["start"]) < CONFUSION:
            if _vector_less(a["start"], b["start"]):
                return True
        elif not fp(a["sa"], b["sa"]):
            if a["sa"] < b["sa"]:
                return True
        elif not fp(a["ea"], b["ea"]):
            if a["ea"] < b["ea"]:
                return True
        elif a["idx"] < b["idx"]:
            return True
        return False

    def cmp(a, b):
        return -1 if less(a, b) else (1 if less(b, a) else 0)

    srt = sorted(items, key=cmp_to_key(cmp))
    srt.reverse()
    out, last = [], None
    for it in srt:
        if last is not None and math.dist(it["start"], last["start"]) < CONFUSION and \
                math.dist(it["end"], last["end"]) < CONFUSION and fp(it["sa"], last["sa"]) and fp(it["ea"], last["ea"]):
            continue
        out.append(it)
        last = it
    return [edges[it["idx"]] for it in out]


# ─── EdgeWalker ──────────────────────────────────────────────────────────────────────────────────────────────

def _incidence_angle(edge, at_first: bool) -> float:
    """DrawUtil::incidenceAngleAtVertex: the angle of the vector from a point a hundredth of the parameter range in
    from the end to the end."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    adapt = BRepAdaptor_Curve(edge)
    f, l = adapt.FirstParameter(), adapt.LastParameter()
    off = (l - f) / 100.0
    end = adapt.Value(f if at_first else l)
    inner = adapt.Value(f + off if at_first else l - off)
    a = math.atan2(end.Y() - inner.Y(), end.X() - inner.X())
    return a + 2.0 * math.pi if a < 0 else a


def walk(edges: list) -> list:
    """EdgeWalker::execute(edges, biggest included): the closed wires of the faces of the planar graph, biggest first."""
    from OCP.BRep import BRep_Tool
    from OCP.ShapeAnalysis import ShapeAnalysis
    pts: list = []

    def vid(p):
        for i, q in enumerate(pts):
            if math.dist(p, q) <= EWTOLERANCE:
                return i
        pts.append(p)
        return len(pts) - 1
    ev = []
    for e in edges:
        a, b = _ends(e)
        ev.append((vid(a), vid(b)))
    # half edges (edge, 0) leaves its first vertex and arrives at its last, (edge, 1) the reverse
    keep = list(range(len(edges)))
    rows: dict = {}
    for i in keep:
        e = edges[i]
        v0, v1 = ev[i]
        rows.setdefault(v0, []).append((_incidence_angle(e, True), i, 0))
        rows.setdefault(v1, []).append((_incidence_angle(e, False), i, 1))
    for v in rows:
        rows[v].sort(key=lambda r: -r[0])          # incidenceItem::iiCompare: the bigger angle first (stable)
    pos = {}
    for v, row in rows.items():
        for k, (_, i, end) in enumerate(row):
            pos[(i, end)] = (v, k)
    visited = set()
    faces = []
    for i in keep:
        for d in (0, 1):
            if (i, d) in visited:
                continue
            walk_edges = []
            cur = (i, d)               # leaving along edge i: from its first vertex (d 0) or its last (d 1)
            while cur not in visited:
                visited.add(cur)
                walk_edges.append(cur[0])
                # arrive at the other end of the edge, take the next one around that vertex after the one we came in by
                arrive = (cur[0], 1 - cur[1])
                v, k = pos[arrive]
                row = rows[v]
                _, j, end = row[(k + 1) % len(row)]
                cur = (j, end)
            faces.append(walk_edges)
    # removeDuplicateWires: a wire made of the same edges as an earlier one is dropped
    unique, seen = [], []
    for f in faces:
        key = sorted(f)
        if key in seen:
            continue
        seen.append(key)
        unique.append(f)
    wires = []
    for f in unique:
        w = _clean_wire([edges[i] for i in f], EWTOLERANCE)
        if w is not None and BRep_Tool.IsClosed_s(w):
            wires.append(w)
    wires.sort(key=lambda w: -abs(ShapeAnalysis.ContourArea_s(w)))
    return wires

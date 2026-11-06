# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses FreeCAD's TechDraw.findShapeOutline and keeps FreeCAD's licence, the GNU Lesser
# General Public License, version 2.1 or (at your option) any later version; the text is in ../ui/LICENSE.
#
#   Derived from: src/Mod/TechDraw/App/AppTechDrawPy.cpp (Copyright (c) 2002 Jürgen Riegel),
#                 src/Mod/TechDraw/App/DrawProjectSplit.cpp (Copyright (c) 2016 WandererFan),
#                 src/Mod/TechDraw/App/ShapeUtils.cpp (Copyright (c) 2013 Luke Parry, 2022 WandererFan),
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
"""TechDraw.findShapeOutline(shape, scale, direction): the outer wire of a shape seen along direction, in the
projection's 2D frame. CAM's Adaptive op asks it for the stock's outline. The projection, the edge split and the walk
are the view code's (techdraw_view.py, techdraw_faces.py); this adds DrawProjectSplit's getEdgesForWalker and
scrubEdges, and ShapeUtils::legacyViewAxis1."""
from __future__ import annotations

import math

from .techdraw_faces import walk
from .techdraw_view import EWTOLERANCE, FUZZYADJUST, Flags, ViewGeometry, _ends, hlr_compounds, is_zero_edge, \
    make_td_geometry, scale_shape


def legacy_view_axis1(origin, direction, flip: bool = False):
    """ShapeUtils::legacyViewAxis1: the view axis with X across the direction, mirrored in the XZ plane."""
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf
    center = gp_Pnt(*origin)
    d = (direction[0], -direction[1], direction[2]) if flip else tuple(direction)
    n = math.sqrt(sum(c * c for c in d))
    u = tuple(c / n for c in d)
    if abs(abs(u[2]) - 1.0) < 1e-7:                  # DU::checkParallel(flipDirection, stdZ)
        cross = (1.0, 0.0, 0.0)
    else:
        cross = (u[1], -u[0], 0.0)                   # normalized direction ^ (0, 0, 1)
    if all(abs(c) <= 1.1920929e-07 for c in cross):  # IsEqual(stdOrg, float epsilon)
        return gp_Ax2(center, gp_Dir(*d))
    axis = gp_Ax2(center, gp_Dir(*d), gp_Dir(*cross))
    mirror = gp_Trsf()
    mirror.SetMirror(gp_Ax2(center, gp_Dir(0, -1, 0)))
    return axis.Transformed(mirror)


def edges_for_walker(shape, scale: float, direction) -> list:
    """DrawProjectSplit::getEdgesForWalker: the shape copied, scaled and projected by a GeometryObject with no view
    (hard and outline edges only, GeometryObject::makeTDGeometry without a DrawViewPart), its visible face edges, the
    zero-length ones dropped."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
    if shape.IsNull():
        return []
    copy = BRepBuilderAPI_Copy(shape).Shape()
    scaled = scale_shape(copy, scale)
    axis = legacy_view_axis1((0.0, 0.0, 0.0), direction, False)
    geo = ViewGeometry()
    flags = Flags(smooth_visible=False, scrub_count=0)          # GeometryObject's m_scrubCount(0)
    make_td_geometry(geo, hlr_compounds(scaled, axis, 0), flags)
    edges = [e.occ for e in geo.edges if e.visible and e.cls in ("hard", "outline")]
    return [e for e in edges if not is_zero_edge(e, 2.0 * EWTOLERANCE)]


def _same(p, q) -> bool:
    """Two keys of DrawProjectSplit's vertexMap (std::map with DrawUtil::vectorLess) are one key."""
    return math.dist(p, q) <= EWTOLERANCE


def scrub_edges(edges: list):
    """DrawProjectSplit::scrubEdges: the edges fused with each other (BOPAlgo_Builder, fuzzy FUZZYADJUST *
    EWTOLERANCE), split into closed and open ones; of the open ones, those connected at both ends. Returns
    (open, closed)."""
    from OCP.BOPAlgo import BOPAlgo_Builder, BOPAlgo_GlueOff
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    try:
        from OCP.TopTools import TopTools_ListOfShape
    except ImportError:                              # OCP 7.9's name for it
        from OCP.collections import List_TopoDS_Shape as TopTools_ListOfShape
    closed, open_ = [], []
    if len(edges) < 2:
        for e in edges:
            (closed if BRep_Tool.IsClosed_s(e) else open_).append(e)
        return open_, closed
    args = TopTools_ListOfShape()
    for e in edges:
        args.Append(e)
    bop = BOPAlgo_Builder()
    bop.SetArguments(args)
    bop.SetFuzzyValue(FUZZYADJUST * EWTOLERANCE)
    bop.SetNonDestructive(False)
    bop.SetGlue(BOPAlgo_GlueOff)
    bop.SetCheckInverted(False)
    bop.SetUseOBB(True)
    bop.SetRunParallel(True)
    bop.Perform()
    if bop.HasErrors():
        return [], closed
    res = bop.Shape()
    if not res.IsNull():
        ex = TopExp_Explorer(res, TopAbs_EDGE)
        while ex.More():
            e = TopoDS.Edge(ex.Current())
            (closed if BRep_Tool.IsClosed_s(e) else open_).append(e)
            ex.Next()
    # getUniqueVertexes, then pruneUnconnected: an edge stays when both its ends are used at least twice
    keys: list = []
    counts: list = []
    ends = [_ends(e) for e in open_]
    for pair in ends:
        for p in pair:
            for i, k in enumerate(keys):
                if _same(k, p):
                    counts[i] += 1
                    break
            else:
                keys.append(p)
                counts.append(1)

    def count(p):
        for k, c in zip(keys, counts):
            if _same(k, p):
                return c
        return 0
    return [e for e, (a, b) in zip(open_, ends) if count(a) > 1 and count(b) > 1], closed


def find_shape_outline(shape, scale: float, direction):
    """AppTechDrawPy findShapeOutline: the first (biggest) wire EdgeWalker finds in the scrubbed edges, closed
    edges included; None when there is none."""
    edges = edges_for_walker(shape, scale, direction)
    if not edges:
        return None
    open_, closed = scrub_edges(edges)
    wires = walk(open_ + closed)
    return wires[0] if wires else None

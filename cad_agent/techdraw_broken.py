# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses FreeCAD's TechDraw broken view and keeps FreeCAD's licence, the GNU Lesser
# General Public License, version 2.1 or (at your option) any later version; the text is in ../ui/LICENSE.
#
#   Derived from: src/Mod/TechDraw/App/DrawBrokenView.cpp (Copyright (c) 2024 WandererFan),
#                 src/Mod/TechDraw/Gui/QGIBreakLine.cpp (Copyright (c) 2024 WandererFan),
#                 src/Mod/TechDraw/App/DrawUtil.cpp (Copyright (c) 2015 WandererFan)
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
"""A broken view's shape: DrawBrokenView::execute before partExec. Each break (two points, the ends of a straight edge
in the 3D document, as breakPointsFromEdge reads it) cuts the shape into the part before its first point and the part
after its second (apply1Break: two half spaces); then the pieces are moved together along the view's X and Y
(compressHorizontal, compressVertical), each break's removed length less the Gap. The view projects what is left."""
from __future__ import annotations

import math

from .techdraw_view import EWTOLERANCE, projection_cs

STD = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _norm(v):
    n = math.sqrt(_dot(v, v))
    return (v[0] / n, v[1] / n, v[2] / n) if n > 0 else v


def _angle(a, b):
    """Base::Vector3d::GetAngle."""
    la, lb = math.sqrt(_dot(a, a)), math.sqrt(_dot(b, b))
    if la <= 1e-16 or lb <= 1e-16:
        return float("nan")
    c = max(-1.0, min(1.0, _dot(a, b) / (la * lb)))
    return math.acos(c)


def _fp(a, b, tol=EWTOLERANCE):
    return abs(a - b) < tol


def closest_basis(v):
    """DrawUtil::closestBasis(Vector3d): +X, +Y or +Z."""
    if any(_dot(v, s) == 1.0 for s in STD):
        return v
    if any(_dot(v, s) == -1.0 for s in STD):
        return (-v[0], -v[1], -v[2])
    angles = [_angle(s, v) for s in STD] + [_angle(tuple(-c for c in s), v) for s in STD]
    m = min(angles)
    for i, a in enumerate(angles):
        if a == m:
            return STD[i % 3]
    return STD[0]


def closest_basis_oriented(v):
    """DrawUtil::closestBasisOriented: +/- X, Y or Z."""
    if any(_dot(v, s) == 1.0 for s in STD) or any(_dot(v, s) == -1.0 for s in STD):
        return v
    cands = list(STD) + [tuple(-c for c in s) for s in STD]
    angles = [_angle(s, v) for s in cands]
    m = min(angles)
    for s, a in zip(cands, angles):
        if a == m:
            return s
    return STD[0]


def _axis_index(direction):
    """Which of X, Y, Z a basis direction is along (the else branches of getPieceLimits/makeSortedBreakList)."""
    if _fp(abs(_dot(direction, STD[0])), 1.0):
        return 0
    if _fp(abs(_dot(direction, STD[1])), 1.0):
        return 1
    return 2


def is_direction_reversed(direction) -> bool:
    for s in STD:
        if _fp(abs(_dot(direction, s)), 1.0):
            return _fp(_dot(direction, s), -1.0)
    return False


class Breaks:
    """The view's breaks (Breaks: each a straight edge, its two ends) and its Gap, with DrawBrokenView's queries."""

    def __init__(self, breaks, gap: float):
        self.breaks = [(tuple(map(float, a)), tuple(map(float, b))) for a, b in breaks]
        self.gap = float(gap)

    @staticmethod
    def direction(b):
        """directionFromObj: closestBasis of the edge's direction."""
        return closest_basis(_norm(_sub(b[1], b[0])))

    @staticmethod
    def removed(b):
        """removedLengthFromObj: the length of the break edge."""
        d = _sub(b[1], b[0])
        return math.sqrt(_dot(d, d))

    def sorted_breaks(self, direction, descend=False):
        """makeSortedBreakList: the breaks along direction, low and high limits on its axis, by lowLimit."""
        out = []
        k = _axis_index(direction)
        for b in self.breaks:
            if _fp(abs(_dot(direction, self.direction(b))), 1.0):
                lo, hi = min(b[0][k], b[1][k]), max(b[0][k], b[1][k])
                out.append({"break": b, "low": lo, "high": hi, "net": self.removed(b) - self.gap})
        out.sort(key=lambda e: e["low"])        # std::sort with breakLess
        if descend:
            out.reverse()
        return out


def half_space(point, normal, inside):
    """makeHalfSpace: the half space on inside's side of the plane through point."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeHalfSpace
    from OCP.gp import gp_Dir, gp_Pln, gp_Pnt
    face = BRepBuilderAPI_MakeFace(gp_Pln(gp_Pnt(*point), gp_Dir(*normal))).Face()
    return BRepPrimAPI_MakeHalfSpace(face, gp_Pnt(*inside)).Solid()


def apply_one_break(b, shape):
    """apply1Break: the shape less the half space from the first point towards the second, and less the one from the
    second towards the first, as one compound; None when a cut fails."""
    from OCP.BRep import BRep_Builder
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.TopoDS import TopoDS_Compound
    p0, p1 = b
    if math.dist(p0, p1) < EWTOLERANCE:          # Vector3d::IsEqual(.., EWTOLERANCE)
        return shape
    d0 = closest_basis_oriented(_norm(_sub(p1, p0)))
    cut0 = BRepAlgoAPI_Cut(shape, half_space(p0, d0, p1))
    if not cut0.IsDone() or cut0.Shape().IsNull():
        return None
    d1 = closest_basis_oriented(_norm(_sub(p0, p1)))
    cut1 = BRepAlgoAPI_Cut(shape, half_space(p1, d1, p0))
    if not cut1.IsDone() or cut1.Shape().IsNull():
        return None
    comp = TopoDS_Compound()
    bld = BRep_Builder()
    bld.MakeCompound(comp)
    bld.Add(comp, cut0.Shape())
    bld.Add(comp, cut1.Shape())
    return comp


def break_shape(shape, breaks: Breaks, warn=None):
    """breakShape: each break applied in turn; one that fails is left out (a warning)."""
    out = shape
    for b in breaks.breaks:
        prev = out
        out = apply_one_break(b, out)
        if out is None:
            if warn:
                warn("Failed to apply break")
            out = prev
    return out


def _pieces(shape):
    """getPieces: the solids, then shells, faces, wires and edges that are not in the type before."""
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID, TopAbs_WIRE
    from OCP.TopExp import TopExp_Explorer

    def by_type(want, avoid=None):
        ex = TopExp_Explorer(shape, want, avoid) if avoid is not None else TopExp_Explorer(shape, want)
        out = []
        while ex.More():
            out.append(ex.Current())
            ex.Next()
        return out
    return (by_type(TopAbs_SOLID) + by_type(TopAbs_SHELL, TopAbs_SOLID) + by_type(TopAbs_FACE, TopAbs_SHELL)
            + by_type(TopAbs_WIRE, TopAbs_FACE) + by_type(TopAbs_EDGE, TopAbs_WIRE))


def _limits(pieces, direction):
    """getPieceLimits: each piece's optimal box along the direction's axis."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from .techdraw_view import _box
    k = _axis_index(direction)
    out = []
    for p in pieces:
        box = Bnd_Box()
        box.SetGap(0.0)
        BRepBndLib.AddOptimal_s(p, box)
        x = _box(box)
        out.append((x[k], x[3 + k]))
    return out


def _move_this(limit, brk, direction) -> bool:
    """moveThisPiece: a piece wholly before the break (after it, against a reversed direction)."""
    lo, hi = limit
    if is_direction_reversed(direction):
        return lo > brk["high"] or _fp(lo, brk["high"])
    return hi < brk["low"] or _fp(hi, brk["low"])


def _compress(shape, breaks: Breaks, direction):
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound
    from .techdraw_view import move_shape
    pieces = _pieces(shape)
    limits = _limits(pieces, direction)
    for brk in breaks.sorted_breaks(direction):
        f = breaks.removed(brk["break"]) - breaks.gap
        disp = (direction[0] * f, direction[1] * f, direction[2] * f)
        for i, lim in enumerate(limits):
            if _move_this(lim, brk, direction):
                pieces[i] = move_shape(pieces[i], disp)
    comp = TopoDS_Compound()
    bld = BRep_Builder()
    bld.MakeCompound(comp)
    for p in pieces:
        bld.Add(comp, p)
    return comp


def compress_shape(shape, breaks: Breaks, cs):
    """compressShape: compressHorizontal along the view's X direction, then compressVertical along its Y."""
    xd, yd = cs.XDirection(), cs.YDirection()
    h = _compress(shape, breaks, closest_basis_oriented((xd.X(), xd.Y(), xd.Z())))
    return _compress(h, breaks, closest_basis_oriented((yd.X(), yd.Y(), yd.Z())))


def broken_shape(shape, breaks, gap, direction, x_direction, warn=None):
    """DrawBrokenView::execute's shape: a copy of the source, broken, then compressed in the view's CS."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
    b = Breaks(breaks, gap)
    safe = BRepBuilderAPI_Copy(shape).Shape()
    broken = break_shape(safe, b, warn)
    return compress_shape(broken, b, projection_cs(direction, x_direction))


def break_lines(o, scale: float) -> list:
    """QGIViewPart::drawBreakLines for edge breaks, with ViewProviderViewPart's defaults (BreakLineType Simple,
    Preferences::BreakType 2; a continuous BreakLineStyle; black): for each break the two lines across the view at its
    bounds, in the view's paper coordinates (mm about the view's origin, y down), before the view's Rotation.

    breakBoundsFromEdge projects the break edge straight onto the paper plane through the model origin
    (DrawViewPart::projectEdge) and takes the projected ends' x and y (in model space: in a view along Y the plane is
    XZ, so its y is 0), the lines' length being the edge's; the bounds are neither centred on the view nor
    compressed, as FreeCAD 3160daf1e2b6 draws them."""
    from .techdraw_view import project_point
    n = _norm(tuple(o.direction))
    out = []
    for b in Breaks(o.breaks, o.gap).breaks:
        # projectEdge: each end moved along the normal onto the plane through the origin
        start, end = (tuple(p[i] - _dot(p, n) * n[i] for i in range(3)) for p in b)
        d = _sub(end, start)
        length = math.sqrt(_dot(d, d))
        du = _norm(d) if length > 0 else d
        if _fp(abs(_dot(du, STD[0])), 1.0):
            tl = (min(start[0], end[0]), start[1] + length)
            br = (max(start[0], end[0]), start[1] - length)
        else:
            tl = (start[0] - length, max(start[1], end[1]))
            br = (start[0] + length, min(start[1], end[1]))
        # scalePair, then drawBreakLines' Rez::guiX(DU::invertY(..)) and QGIBreakLine::setBounds
        tl, br = (tl[0] * scale, -tl[1] * scale), (br[0] * scale, -br[1] * scale)
        left, right = min(tl[0], br[0]), max(tl[0], br[0])
        bottom, top = min(tl[1], br[1]), max(tl[1], br[1])
        # guiDirectionFromObj: the break's basis direction projected (projectPoint, y inverted)
        gd = project_point(o.direction, o.x_direction, Breaks.direction(b))
        if _fp(abs(gd[0]), 1.0):            # drawSimpleLines: horizontal, two lines up the view at left and right
            lines = [[[left, bottom], [left, top]], [[right, bottom], [right, top]]]
        else:                               # two lines across at bottom and top
            lines = [[[left, bottom], [right, bottom]], [[left, top], [right, top]]]
        out.append({"lines": lines, "rotation": -o.rotation})
    return out

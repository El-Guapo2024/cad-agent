# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses what FreeCAD's TechDraw extension commands do and keeps FreeCAD's licence, the GNU
# Lesser General Public License, version 2.1 or (at your option) any later version; the text is in ../ui/LICENSE.
#
#   Derived from: src/Mod/TechDraw/Gui/CommandExtensionPack.cpp (Copyright (c) 2021 edi),
#                 src/Mod/TechDraw/Gui/CommandExtensionDims.cpp (Copyright (c) 2021 edi),
#                 src/Mod/TechDraw/Gui/CommandAnnotate.cpp (Copyright (c) 2019 WandererFan),
#                 src/Mod/TechDraw/Gui/TaskSelectLineAttributes.cpp (Copyright (c) 2021 edi),
#                 src/Mod/TechDraw/TechDrawTools/CommandPositionSectionView.py (Copyright (c) 2021 edi),
#                 src/Mod/TechDraw/App/DrawUtil.cpp (Copyright (c) 2013 Luke Parry),
#                 src/Mod/Part/App/Geometry2d.cpp (Copyright (c) 2011 Werner Mayer, Yorik van Havre)
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
"""The ops of TechDraw's extension commands (the Attributes/Modifications, Centerlines/Threading and Format/Organize
Dimensions menus). They work on cosmetic geometry and dimensions the port already has; every number is the C++'s, float
arithmetic included (FreeCAD does a good part of it in `float`: `f32` rounds as it does).

  {"op": "cosmetic_circle2",  "view": v, "vertices": ["Vertex6", "Vertex8"]}      centre and a point of the rim
  {"op": "cosmetic_circle3",  "view": v, "vertices": [3 names]}                    through three points
  {"op": "cosmetic_arc",      "view": v, "vertices": [centre, start, end]}         anticlockwise
  {"op": "cosmetic_pline",    "view": v, "subs": ["Edge2", "Vertex8"], "parallel": true|false}
  {"op": "extend_line",       "view": v, "sub": "Edge9", "extend": true|false}      TechDraw_ExtensionExtendLine / ShortenLine
  {"op": "circle_centerlines","view": v, "edges": [...]}                           TechDraw_ExtensionCircleCenterLines
  {"op": "bolt_circle",       "view": v, "edges": [3 or more circles]}             TechDraw_ExtensionHoleCircle
  {"op": "thread",            "view": v, "kind": "hole_side"|"bolt_side"|"hole_bottom"|"bolt_bottom", "subs": [...]}
  {"op": "line_attributes",   "view": v, "subs": [...]}                             TechDraw_ExtensionChangeLineAttributes
  {"op": "lock_view",         "names": [...]}                                       TechDraw_ExtensionLockUnlockView
  {"op": "show_all_edges",    "view": v}                                            TechDraw_ShowAll (Toggle Edge Visibility)
  {"op": "position_section",  "section": s} or {"section": s, "edge": "EdgeN", "base": b, "vertex": "VertexM"}
  {"op": "chain_dim"|"coord_dim", "view": v, "vertices": [...], "dir": "h"|"v"|"o"}
  {"op": "chamfer_dim",       "view": v, "vertices": [a, b], "dir": "h"|"v"}
  {"op": "arc_length_dim",    "view": v, "edge": "Edge1"}
  {"op": "dim_position",      "names": [...], "dir": "h"|"v"|"o", "cascade": bool}  chain (align) and cascade
  {"op": "dim_prefix",        "names": [...], "prefix": "⌀"}  /  {"op": "dim_remove_prefix", "names": [...]}
  {"op": "dim_decimals",      "names": [...], "delta": 1|-1}
  {"op": "area_annotation",   "view": v, "faces": ["Face0", ...]}
  {"op": "arc_length_annotation", "view": v, "edges": ["Edge1", ...]}

Any op may carry "active": {"style", "weight", "color", "visible", "line_number"}, "line_stretch" and "cascade_spacing":
the session's line attributes (TaskSelectLineAttributes; LineFormat::getCurrentLineFormat and activeDimAttributes),
which default to FreeCAD's. A point of a view is read from its geometry (paper, y down, scaled and rotated) and the lines
are kept the way the page file holds them (techdraw_cosmetic.py: unscaled, unrotated, y up).
This module imports without OCP.
"""
from __future__ import annotations

import math
import struct

from . import techdraw as T
from . import techdraw_annot as A
from . import techdraw_cosmetic as C

STEP_NAMES = {"cosmetic_circle2": "Cosmetic Circle", "cosmetic_circle3": "Cosmetic Circle 3 Points", "cosmetic_arc": "Cosmetic arc",
              "cosmetic_pline": "Cosmetic Line Parallel/Perpendicular", "extend_line": "Extend/shorten line",
              "circle_centerlines": "Circle Centerlines", "bolt_circle": "Bolt circle centerlines",
              "thread:hole_side": "Cosmetic Thread Hole Side", "thread:bolt_side": "Cosmetic Thread Bolt Side",
              "thread:hole_bottom": "Cosmetic thread hole bottom", "thread:bolt_bottom": "Cosmetic Thread Bolt Bottom",
              "line_attributes": "Change line attributes", "lock_view": "Lock/Unlock View", "show_all_edges": "Toggle Edge Visibility",
              "position_section": "Position Section View",
              "chain_dim:h": "Create Horizontal Chain Dimension", "chain_dim:v": "Create Vert Chain dimension",
              "chain_dim:o": "Create oblique chain dimension", "coord_dim:h": "Create Horizontal Coord Dimension",
              "coord_dim:v": "Create vert coord dimension", "coord_dim:o": "Create oblique coord dimension",
              "chamfer_dim:h": "Create Horizontal Chamfer Dimension", "chamfer_dim:v": "Create Vert Chamfer Dimension",
              "arc_length_dim": "Create Arc Length Dimension", "dim_prefix": "Insert Prefix", "dim_remove_prefix": "Remove Prefix",
              "dim_decimals": "Increase/Decrease Decimal",
              "dim_position:h": "Position Horizontal Chain Dimension", "dim_position:v": "Position Vert Chain Dimension",
              "dim_position:o": "Position Oblique Chain Dimension", "cascade:h": "Cascade Horizontal Dimension",
              "cascade:v": "Cascade Vertical Dimension", "cascade:o": "Cascade Oblique Dimension",
              "area_annotation": "Calculate Face Area", "arc_length_annotation": "Calculate Edge Length"}
OPS = ("cosmetic_circle2", "cosmetic_circle3", "cosmetic_arc", "cosmetic_pline", "extend_line", "circle_centerlines", "bolt_circle",
       "thread", "line_attributes", "lock_view", "show_all_edges", "position_section", "chain_dim", "coord_dim", "chamfer_dim",
       "arc_length_dim", "dim_position", "dim_prefix", "dim_remove_prefix", "dim_decimals", "area_annotation",
       "arc_length_annotation")

THIN, GRAPHIC, THICK = 0.35, 0.5, 0.7           # LineGroup::getDefaultWidth("Thin" | "Graphic" | "Thick")
CASCADE_SPACING = 7.0                           # activeDimAttributes: TaskSelectLineAttributes.cpp
LINE_STRETCH = 2.0
THREAD_HOLE, THREAD_BOLT = 1.176, 0.85
TYPE_NAMES = {"GENERIC": "Line", "CIRCLE": "Circle", "ARCOFCIRCLE": "Arc of Circle", "ELLIPSE": "Ellipse",
              "ARCOFELLIPSE": "Arc of Ellipse", "BEZIER": "Bezier Curve", "BSPLINE": "B-spline Curve"}


# FreeCAD makes no undo step for these (they change an object or a view provider, not a property; the Python command
# sets X and Y outside a transaction): here each is a step, named as the command's transaction would be
NO_STEP_IN_FREECAD = ("line_attributes", "show_all_edges", "position_section")


def step_name(op: dict) -> str | None:
    """The undo step a command makes."""
    k = op["op"]
    if k == "dim_position":
        k = "cascade" if op.get("cascade") else "dim_position"
    for key in (k + ":" + str(op.get("kind") or op.get("dir") or ""), k):
        if key in STEP_NAMES:
            return STEP_NAMES[key]
    return None


def f32(x: float) -> float:
    """A C++ `float`."""
    return struct.unpack("f", struct.pack("f", x))[0]


from .techdraw_edit import TechDrawEditError as ExtError  # noqa: E402


def run(s, op: dict) -> str:
    from . import techdraw_edit as E
    return globals()["_" + op["op"]](s, E, op)


# ── session attributes ───────────────────────────────────────────────────────────────────────────────────────

def current_format(op: dict) -> dict:
    """LineFormat::getCurrentLineFormat: dashed, Graphic, Preferences::normalColor, visible, line number 2."""
    f = dict(C.DEFAULT_FORMAT)
    for k, v in (op.get("active") or {}).items():
        if k in f:
            f[k] = v
    return C.format_of({"format": f})


def _stretch(op) -> float:
    return float(op.get("line_stretch", LINE_STRETCH))


def _spacing(op) -> float:
    return float(op.get("cascade_spacing", CASCADE_SPACING))


# ── a view's geometry ────────────────────────────────────────────────────────────────────────────────────────

def _view(s, op, key="view"):
    return s.get(op.get(key), T.DrawViewPart, "view")


def _geo(s, E, v):
    return A._geo(s, E, v)


def _names(op, key, kind):
    return [n for n in (op.get(key) or []) if isinstance(n, str) and n.startswith(kind)]


def _vertex_paper(geo, name):
    i = A._index(name, "Vertex", geo.vertices, "vertices")
    v = geo.vertices[i]
    return (v.x, v.y)


def _vertex_points(geo, names):
    """_getVertexPoints: the paper points (scaled, rotated, y down) of the vertices among the names."""
    return [_vertex_paper(geo, n) for n in names if n.startswith("Vertex")]


def _edge(geo, name):
    return geo.edges[A._index(name, "Edge", geo.edges, "edges")]


def _ends(e):
    from .techdraw_view import _ends
    return _ends(e.occ)


def _circle(e):
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    c = BRepAdaptor_Curve(e.occ).Circle()
    loc = c.Location()
    return (loc.X(), loc.Y()), c.Radius()


def _stored(geo, v, p):
    """CosmeticVertex::makeCanonicalPointInverted: a paper point unscaled and unrotated, still y down."""
    u = A._user_from_paper(geo, v, p[0], p[1])
    return [u[0], -u[1], 0.0]


def _user(geo, v, p):
    return A._user_from_paper(geo, v, p[0], p[1])


def _line(a, b, fmt):
    """addCosmeticEdge(a, b): the points are kept as they are, in the stored (y down) space; the page file holds y up."""
    return C.make_line([a[0], -a[1], 0.0], [b[0], -b[1], 0.0], None, fmt)


def _add_edges(s, E, v, new):
    A._replace(s, E, v, cosmetic_edges=A._list(v, "cosmetic_edges") + new)


def _norm(p):
    n = math.hypot(p[0], p[1])
    return [p[0] / n, p[1] / n, 0.0] if n > 0.0 else [0.0, 0.0, 0.0]


def _need_line(e, what):
    if e.kind != "GENERIC":
        raise ExtError(f"Can not make {what} for {TYPE_NAMES.get(e.kind, 'Not Defined')}")


# ── CommandExtensionPack: circles and arcs ───────────────────────────────────────────────────────────────────

def circle_center(p1, p2, p3):
    """Part::Geom2dCircle::getCircleCenter."""
    u = (p2[0] - p1[0], p2[1] - p1[1])
    v = (p3[0] - p2[0], p3[1] - p2[1])
    w = (p1[0] - p3[0], p1[1] - p3[1])
    uu, vv, ww = u[0] * u[0] + u[1] * u[1], v[0] * v[0] + v[1] * v[1], w[0] * w[0] + w[1] * w[1]
    if min(uu, vv, ww) < 1e-14:
        raise ExtError("Two points are coincident")
    uv, vw, uw = -(u[0] * v[0] + u[1] * v[1]), -(v[0] * w[0] + v[1] * w[1]), -(u[0] * w[0] + u[1] * w[1])
    w0 = 2 * math.sqrt(abs(uu * ww - uw * uw)) * uw / (uu * ww)
    w1 = 2 * math.sqrt(abs(uu * vv - uv * uv)) * uv / (uu * vv)
    w2 = 2 * math.sqrt(abs(vv * ww - vw * vw)) * vw / (vv * ww)
    wx = w0 + w1 + w2
    if abs(wx) < 1e-7:
        raise ExtError("Points are collinear")
    return ((w0 * p1[0] + w1 * p2[0] + w2 * p3[0]) / wx, (w0 * p1[1] + w1 * p2[1] + w2 * p3[1]) / wx)


def _cosmetic_circle2(s, E, op):
    """execDrawCosmCircle: the first vertex is the centre, the second a point of the rim."""
    v = _view(s, op)
    geo = _geo(s, E, v)
    pts = _vertex_points(geo, op.get("vertices") or [])
    if len(pts) < 2:
        return f"nothing made on {v.name}"
    r = math.dist(pts[1], pts[0]) / geo.scale
    ce = C.make_circle(_user(geo, v, pts[0]), r, None, current_format(op))
    _add_edges(s, E, v, [ce])
    return f"made a cosmetic circle on {v.name}"


def _cosmetic_circle3(s, E, op):
    """execDrawCosmCircle3Points."""
    v = _view(s, op)
    geo = _geo(s, E, v)
    pts = _vertex_points(geo, op.get("vertices") or [])
    if len(pts) < 3:
        return f"nothing made on {v.name}"
    c = circle_center(pts[0], pts[1], pts[2])
    r = math.dist(pts[0], c) / geo.scale
    _add_edges(s, E, v, [C.make_circle(_user(geo, v, c), r, None, current_format(op))])
    return f"made a cosmetic circle on {v.name}"


def _cosmetic_arc(s, E, op):
    """execDrawCosmArc: an anticlockwise arc about the first vertex from the second to the third."""
    v = _view(s, op)
    geo = _geo(s, E, v)
    pts = _vertex_points(geo, op.get("vertices") or [])
    if len(pts) < 3:
        return f"nothing made on {v.name}"
    c, e1, e2 = (_user(geo, v, p) for p in pts[:3])

    def angle(p):                              # _getAngle: DrawUtil::angleWithX in degrees, [0, 360)
        a = math.atan2(p[1] - c[1], p[0] - c[0])
        return (a + 2.0 * math.pi if a < 0 else a) * 180.0 / math.pi
    r = math.hypot(e1[0] - c[0], e1[1] - c[1])
    _add_edges(s, E, v, [C.make_arc(c, r, angle(e1), angle(e2), None, current_format(op))])
    return f"made a cosmetic arc on {v.name}"


def _cosmetic_pline(s, E, op):
    """execLineParallelPerpendicular: the line through the vertex, as long as the edge, parallel or turned a quarter."""
    v = _view(s, op)
    geo = _geo(s, E, v)
    subs = list(op.get("subs") or [])
    if len(subs) < 2:
        return "nothing made"
    kinds = [n[:4] for n in subs[:2]]
    if kinds == ["Edge", "Vert"]:
        e_name, v_name = subs[0], subs[1]
    elif kinds == ["Vert", "Edge"]:
        e_name, v_name = subs[1], subs[0]
    else:
        return "nothing made"
    e = _edge(geo, e_name)
    _need_line(e, "a line")
    a, b = _ends(e)
    start, end = _stored(geo, v, a), _stored(geo, v, b)
    vp = _stored(geo, v, _vertex_paper(geo, v_name))
    half = [(end[0] - start[0]) / 2.0, (end[1] - start[1]) / 2.0]
    if not op.get("parallel", True):
        half = [-half[1], f32(half[0])]
    p0 = [vp[0] + half[0], vp[1] + half[1]]
    p1 = [vp[0] - half[0], vp[1] - half[1]]
    _add_edges(s, E, v, [_line(p0, p1, current_format(op))])
    return f"made a cosmetic line on {v.name}"


def _extend_line(s, E, op):
    """execExtendShortenLine: a cosmetic line is replaced by the longer or shorter one (at the end of the list, with the
    old line's pen); a centre line grows by the delta distance."""
    v = _view(s, op)
    geo = _geo(s, E, v)
    sub = op.get("sub") or (op.get("subs") or [None])[0]
    if not (isinstance(sub, str) and sub.startswith("Edge")):
        return "nothing changed"
    i = A._index(sub, "Edge", geo.edges, "edges")
    e = geo.edges[i]
    _need_line(e, "centerlines")
    if e.cls not in ("cosmetic", "centerline"):
        return "nothing changed"
    extend = op.get("extend", True)
    stretch = _stretch(op)
    if e.cls == "centerline":
        lines = A._list(v, "center_lines")
        k = next(n for n, c in enumerate(lines) if c["tag"] == e.cosmetic_tag)
        lines[k] = C.clean("centerline", {**lines[k], "extend": lines[k]["extend"] + (stretch if extend else -stretch)})
        A._replace(s, E, v, center_lines=lines)
        return f"{'extended' if extend else 'shortened'} the centre line on {v.name}"
    edges = A._list(v, "cosmetic_edges")
    k = next(n for n, c in enumerate(edges) if c["tag"] == e.cosmetic_tag)
    old = edges[k]
    a, b = _ends(e)
    p0, p1 = _stored(geo, v, a), _stored(geo, v, b)
    d = _norm([p1[0] - p0[0], p1[1] - p0[1]])
    delta = [d[0] * stretch, d[1] * stretch]
    sign = -1.0 if extend else 1.0
    q0 = [p0[0] + sign * delta[0], p0[1] + sign * delta[1]]
    q1 = [p1[0] - sign * delta[0], p1[1] - sign * delta[1]]
    of = C.format_of(old)
    fmt = {**current_format(op), "style": of["line_number"], "line_number": of["line_number"], "weight": of["weight"],
           "color": of["color"]}
    del edges[k]
    edges.append(_line(q0, q1, fmt))
    A._replace(s, E, v, cosmetic_edges=edges)
    return f"{'extended' if extend else 'shortened'} the cosmetic line on {v.name}"


# ── centre lines and threads ─────────────────────────────────────────────────────────────────────────────────

def _circle_centerlines(s, E, op):
    """execCircleCenterLines: a cross through each circle and arc, 2 mm beyond it."""
    v = _view(s, op)
    geo = _geo(s, E, v)
    new = []
    for n in _names(op, "edges", "Edge"):
        e = _edge(geo, n)
        if e.kind not in ("CIRCLE", "ARCOFCIRCLE"):
            raise ExtError(f"Can not make centerlines for {TYPE_NAMES.get(e.kind, 'Not Defined')}")
        pc, r = _circle(e)
        c = _stored(geo, v, pc)
        r /= geo.scale
        out = 2.0
        right, left = [c[0] + r + out, c[1]], [c[0] - r - out, c[1]]
        top, bottom = [c[0], c[1] + r + out], [c[0], c[1] - r - out]
        fmt = {**current_format(op), "line_number": C.CENTER_LINE_NUMBER}
        new += [_line(right, left, fmt), _line(top, bottom, fmt)]
    _add_edges(s, E, v, new)
    return f"made {len(new)} centre lines on {v.name}"


def _bolt_circle(s, E, op):
    """execHoleCircle: the circle through the centres of the first three circles, and a line through each circle's
    centre along the radius."""
    v = _view(s, op)
    geo = _geo(s, E, v)
    circles = []
    for n in _names(op, "edges", "Edge"):
        e = _edge(geo, n)
        if e.kind in ("CIRCLE", "ARCOFCIRCLE"):
            circles.append(_circle(e))
        else:
            raise ExtError(f"Can not make hole circle for {TYPE_NAMES.get(e.kind, 'Not Defined')}")
    if len(circles) <= 2:
        raise ExtError("Fewer than three circles selected")
    big = circle_center(circles[0][0], circles[1][0], circles[2][0])
    big_r = math.dist(circles[0][0], big)
    bc = _stored(geo, v, big)
    fmt = current_format(op)
    new = [C.make_circle([bc[0], -bc[1], 0.0], big_r / geo.scale, None, fmt)]
    for pc, r in circles:
        c = _stored(geo, v, pc)
        d = _norm([c[0] - bc[0], c[1] - bc[1]])
        k = (r / geo.scale) * 1.1
        new.append(_line([c[0] + d[0] * k, c[1] + d[1] * k], [c[0] - d[0] * k, c[1] - d[1] * k], fmt))
    _add_edges(s, E, v, new)
    return f"made a bolt circle on {v.name}"


def _thread_circle(geo, v, e, factor, op):
    """_createThreadCircle: the three quarter arc, 15 to 285 degrees about the centre, as FreeCAD stores it."""
    if e.kind != "CIRCLE":
        raise ExtError(f"Can not make thread circle for {TYPE_NAMES.get(e.kind, 'Not Defined')}")
    pc, r = _circle(e)
    c = _stored(geo, v, pc)
    radius = f32(r * factor / geo.scale)
    fmt = {**current_format(op), "style": 1, "line_number": 1, "weight": THIN}
    return C.make_arc([c[0], -c[1], 0.0], radius, 15.0, 285.0, None, fmt, stored=True)


def _thread_lines(geo, v, e0, e1, factor, end_line, op):
    """_createThreadLines: the two lines moved apart by the factor, and the line that closes them."""
    if e0.kind != "GENERIC" or e1.kind != "GENERIC":
        raise ExtError("Select 2 straight lines")
    a0, b0 = _ends(e0)
    a1, b1 = _ends(e1)
    start0, end0 = _stored(geo, v, a0), _stored(geo, v, b0)
    start1, end1 = _stored(geo, v, a1), _stored(geo, v, b1)

    def circulation(p, q, r):
        return p[0] * q[1] + p[1] * r[0] + q[0] * r[1] - r[0] * q[1] - r[1] * p[0] - q[0] * p[1] > 0.0
    if circulation(start0, end0, start1) != circulation(end0, end1, start1):
        start1, end1 = end1, start1
    kernel = f32(math.dist(start1, start0))
    k = f32((kernel * factor - kernel) / 2.0)
    d = _norm([start1[0] - start0[0], start1[1] - start0[1]])
    delta = [d[0] * k, d[1] * k]
    thin = {**current_format(op), "style": 1, "line_number": 1, "weight": THIN}
    out = [_line([start0[0] - delta[0], start0[1] - delta[1]], [end0[0] - delta[0], end0[1] - delta[1]], thin),
           _line([start1[0] + delta[0], start1[1] + delta[1]], [end1[0] + delta[0], end1[1] + delta[1]], thin)]
    if end_line:
        graphic = {**thin, "weight": GRAPHIC}
        out.append(_line([end0[0] - delta[0], end0[1] - delta[1]], [end1[0] + delta[0], end1[1] + delta[1]], graphic))
    return out


def _thread(s, E, op):
    v = _view(s, op)
    geo = _geo(s, E, v)
    kind = op.get("kind")
    if kind not in ("hole_side", "bolt_side", "hole_bottom", "bolt_bottom"):
        raise ExtError(f"{kind!r} is not a thread (hole_side, bolt_side, hole_bottom, bolt_bottom)")
    subs = list(op.get("subs") or [])
    new = []
    if kind.endswith("side"):
        if len(subs) >= 2 and subs[0].startswith("Edge") and subs[1].startswith("Edge"):
            new = _thread_lines(geo, v, _edge(geo, subs[0]), _edge(geo, subs[1]), THREAD_HOLE if kind == "hole_side" else THREAD_BOLT,
                                kind == "hole_side", op)         # only a hole's thread is closed by a line
    else:
        for n in subs:
            if n.startswith("Edge"):
                new.append(_thread_circle(geo, v, _edge(geo, n), THREAD_HOLE if kind == "hole_bottom" else THREAD_BOLT, op))
    _add_edges(s, E, v, new)
    return f"made {len(new)} thread lines on {v.name}"


def _line_attributes(s, E, op):
    """TechDraw_ExtensionChangeLineAttributes: the cosmetic lines and centre lines among the edges take the session's
    attributes (no undo step in FreeCAD: only the object changes, not the property)."""
    v = _view(s, op)
    geo = _geo(s, E, v)
    fmt = current_format(op)
    tags = {"cosmetic": set(), "centerline": set()}
    for n in _names(op, "subs", "Edge"):
        e = _edge(geo, n)
        if e.cls in tags:
            tags[e.cls].add(e.cosmetic_tag)
    edges = [C.clean("edge", {**c, "format": fmt}) if c["tag"] in tags["cosmetic"] else c for c in A._list(v, "cosmetic_edges")]
    lines = [C.clean("centerline", {**c, "format": fmt}) if c["tag"] in tags["centerline"] else c for c in A._list(v, "center_lines")]
    A._replace(s, E, v, cosmetic_edges=edges, center_lines=lines)
    return f"changed the line attributes of {len(tags['cosmetic']) + len(tags['centerline'])} lines of {v.name}"


def _lock_view(s, E, op):
    """TechDraw_ExtensionLockUnlockView: LockPosition of each selected part view turned over."""
    done = []
    for n in op.get("names") or []:
        o = s.get(n)
        if isinstance(o, T.DrawViewPart):
            d = T.as_dict(o)
            d["lock_position"] = not d["lock_position"]
            s.objs[s.objs.index(o)] = E._rebuilt(o, d)
            done.append(n)
    return "toggled the lock of " + ", ".join(done) if done else "nothing toggled"


def _show_all_edges(s, E, op):
    """TechDraw_ShowAll: ViewProviderViewPart.ShowAllEdges turned over (the invisible lines drawn or not)."""
    v = _view(s, op)
    d = T.as_dict(v)
    d["show_all_edges"] = not d["show_all_edges"]
    s.objs[s.objs.index(v)] = E._rebuilt(v, d)
    return f"ShowAllEdges of {v.name} is {d['show_all_edges']}"


# ── TechDrawTools/CommandPositionSectionView.py ──────────────────────────────────────────────────────────────

def _triangle_point(p1, d, p2):
    """DrawUtil::getTrianglePoint (and the Python command's copy), in `float` as the C++ has it."""
    a, b = f32(-d[1]), f32(d[0])
    c1 = f32(p1[0] * a + p1[1] * b)             # p1 is double: the sum is, and is rounded to float
    c2 = f32(-p2[0] * b + p2[1] * a)
    ab = f32(f32(a * a) + f32(b * b))
    x = f32(f32(f32(c1 * a) - f32(c2 * b)) / ab)
    y = f32(f32(f32(c2 * a) + f32(c1 * b)) / ab)
    return [x, y, 0.0]


def _py_triangle_point(p1, d, p2):
    """The Python command's getTrianglePoint: doubles."""
    a, b = -d[1], d[0]
    c1 = p1[0] * a + p1[1] * b
    c2 = -p2[0] * b + p2[1] * a
    ab = a * a + b * b
    return [(c1 * a - c2 * b) / ab, (c2 * a + c1 * b) / ab, 0.0]


def _position_base(s, E, view):
    """`baseView = sectionView.BaseView; if a DrawProjGroupItem: baseView = baseView.InList[0]`: the group of an item (a
    single view's first dependent is the page, which has no X)."""
    base = s.get(view.base_view)
    if isinstance(base, T.DrawProjGroupItem):
        g = s.doc().group_of(base.name)
        if g is None:
            raise E.TechDrawEditError("'TechDraw.DrawPage' object has no attribute 'X'")
        return g
    return base


def _position_section(s, E, op):
    """TechDraw_ExtensionPositionSectionView: a section view moved in line with its base view, or the selected edge of
    the section moved in line with the selected vertex of its base view."""
    sec = s.get(op.get("section"), T.DrawViewSection, "section view")
    if op.get("edge"):
        base = s.get(op["base"], T.DrawViewPart, "base view")
        base_view = s.doc().group_of(base.name) if isinstance(base, T.DrawProjGroupItem) else base
        if base_view is None:
            raise E.TechDrawEditError("'TechDraw.DrawPage' object has no attribute 'X'")
        doc = T.PageDocument(s.objs, s.shape_of).recompute()
        gs, gb = doc.geo[sec.name], doc.geo[base.name]
        e = _edge(gs, op["edge"])
        if e.kind != "GENERIC":
            raise E.TechDrawEditError("the edge has no Direction")
        a, b = _ends(e)
        d = [(b[0] - a[0]), -(b[1] - a[1])]
        n = math.hypot(*d)
        d = [d[0] / n, d[1] / n]
        sec_pt = (a[0] / gs.scale, -a[1] / gs.scale)        # Python's vertices: unscaled, y up
        bv = _vertex_paper(gb, op["vertex"])
        base_pt = (bv[0] / gb.scale, -bv[1] / gb.scale)
        scale = base_view.scale
        cb = (base_view.x, base_view.y)
        cs = (sec.x, sec.y)
        bp = [cb[0] + base_pt[0] * scale, cb[1] + base_pt[1] * scale, 0.0]
        sp = [cs[0] + sec_pt[0] * scale, cs[1] + sec_pt[1] * scale, 0.0]
        sp = _py_triangle_point(sp, d, bp)
        move = [sp[0] - bp[0], sp[1] - bp[1]]
    else:
        base_view = _position_base(s, E, sec)
        move = [sec.x - base_view.x, sec.y - base_view.y]
        if abs(move[0]) > abs(move[1]):
            move[0] = 0.0
        else:
            move[1] = 0.0
    d = T.as_dict(sec)
    d["x"], d["y"] = sec.x - move[0], sec.y - move[1]
    s.objs[s.objs.index(sec)] = E._rebuilt(sec, d)
    return f"positioned {sec.name}"


# ── CommandExtensionDims.cpp ─────────────────────────────────────────────────────────────────────────────────

def _dim_font() -> float:
    from . import techdraw_dim as D
    return D.DIM_FONT_SIZE


def _lin_dim(s, E, v, a, b, typ, geo):
    """_createLinDimension: a dimension of Type on two vertices, its points read for the place of its text."""
    from . import techdraw_dim as D
    n = s.name("Dimension")
    dim = T.DrawViewDimension(n, type=typ, references_2d=((v.name, a), (v.name, b)), measure_type="Projected")
    try:
        p0, p1 = D.linear_points(dim, geo)
    except D.DimensionError:
        p0 = p1 = (0.0, 0.0)
    return dim, p0, p1


def _vertex_info(geo, names):
    """_getVertexInfo: name and paper point of each vertex among the names."""
    return [(n, _vertex_paper(geo, n)) for n in names if n.startswith("Vertex")]


def _put(s, E, dim, x, y, **props):
    d = T.as_dict(dim)
    d.update(x=float(x), y=float(y), **props)
    s.add(E._rebuilt(dim, d))


def _mid(p0, p1):
    return ((p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0)


def _chain_dim(s, E, op):
    d = op.get("dir", "h")
    v = _view(s, op)
    geo = _geo(s, E, v)
    verts = _vertex_info(geo, op.get("vertices") or [])
    if len(verts) < 2:
        return "nothing made"
    if d == "o":
        return _oblique(s, E, v, geo, verts, op, False)
    key = (lambda t: t[1][0]) if d == "h" else (lambda t: t[1][1])
    verts.sort(key=key)
    x_master = y_master = 0.0
    fs = _dim_font()
    for n in range(len(verts) - 1):
        dim, p0, p1 = _lin_dim(s, E, v, verts[n][0], verts[n + 1][0], "DistanceX" if d == "h" else "DistanceY", geo)
        mid = _mid(p0, p1)
        if d == "h":
            if n == 0:
                y_master = f32(-mid[1])
            _put(s, E, dim, mid[0], y_master)
        else:
            if n == 0:
                x_master = f32(mid[0])
            _put(s, E, dim, x_master, -mid[1] + 0.5 * fs)
    return f"made {len(verts) - 1} chain dimensions on {v.name}"


def _oblique(s, E, v, geo, verts, op, coord):
    """makeObliqueChainDimension / makeObliqueCoordDimension: each vertex is carried by a cosmetic vertex on the line
    through the first one (a thin cosmetic line from the vertex to it), then the carriers are dimensioned."""
    spacing = f32(_spacing(op))
    p_master = verts[0][1]
    dir_master = (p_master[0] - verts[1][1][0], p_master[1] - verts[1][1][1])
    delta = _triangle_point((p_master[0], p_master[1]), dir_master, (0.0, 0.0))
    delta = _norm(delta)
    delta = [delta[0] * spacing, delta[1] * spacing]
    carriers, new_v, new_e = [], [], []
    count = len(geo.vertices)
    thin = {"style": 1, "line_number": 1, "weight": THIN, "color": [0.0, 0.0, 0.0, 1.0], "visible": True}
    for name, pt in verts:
        nxt = _triangle_point(p_master, dir_master, pt)
        if math.dist(pt[:2], nxt[:2]) > 0.01:
            cv = _stored(geo, v, nxt)
            new_v.append(C.make_vertex([cv[0], -cv[1], 0.0]))
            carriers.append((f"Vertex{count + len(new_v) - 1}", (nxt[0], nxt[1])))
            old = _stored(geo, v, pt)
            new_e.append(_line(old, cv, thin))
        else:
            carriers.append((name, pt))
    v = A._replace(s, E, v, cosmetic_vertexes=A._list(v, "cosmetic_vertexes") + new_v,
                   cosmetic_edges=A._list(v, "cosmetic_edges") + new_e)
    geo = _geo(s, E, v)
    fs = _dim_font()
    n_dims = len(verts) - 1
    if not coord:
        carriers.sort(key=lambda t: t[1][0])
        for n in range(n_dims):
            dim, p0, p1 = _lin_dim(s, E, v, carriers[n][0], carriers[n + 1][0], "Distance", geo)
            mid = _mid(p0, p1)
            _put(s, E, dim, mid[0] + delta[0], -(mid[1] + delta[1]) + 0.5 * fs)
    else:
        first, second = carriers[0], carriers[1]
        carriers.sort(key=lambda t: t[1][0])
        if first[1][0] > second[1][0]:
            carriers.reverse()
        for n in range(n_dims):
            dim, p0, p1 = _lin_dim(s, E, v, carriers[0][0], carriers[n + 1][0], "Distance", geo)
            mid = _mid(p0, p1)
            _put(s, E, dim, mid[0] + delta[0] * (n + 1), -(mid[1] + delta[1] * (n + 1)) + 0.5 * fs)
    return f"made {n_dims} oblique dimensions on {v.name}"


def _coord_dim(s, E, op):
    d = op.get("dir", "h")
    v = _view(s, op)
    geo = _geo(s, E, v)
    verts = _vertex_info(geo, op.get("vertices") or [])
    if len(verts) < 2:
        return "nothing made"
    if d == "o":
        return _oblique(s, E, v, geo, verts, op, True)
    first, second = verts[0], verts[1]
    axis = 0 if d == "h" else 1
    verts.sort(key=lambda t: t[1][axis])
    if first[1][axis] > second[1][axis]:
        verts.reverse()
    spacing = f32(_spacing(op))
    fs = _dim_font()
    if d == "h":
        y_master = f32(verts[0][1][1] - spacing)
        if math.copysign(1.0, y_master) < 0:
            spacing = -spacing
    else:
        x_master = f32(verts[0][1][0] + spacing)
        if math.copysign(1.0, x_master) < 0:
            spacing = -spacing
    for n in range(len(verts) - 1):
        dim, p0, p1 = _lin_dim(s, E, v, verts[0][0], verts[n + 1][0], "DistanceX" if d == "h" else "DistanceY", geo)
        mid = _mid(p0, p1)
        if d == "h":
            _put(s, E, dim, mid[0], f32(f32(-y_master) - f32(spacing * n)))
        else:
            _put(s, E, dim, f32(x_master + f32(spacing * n)), -mid[1] + 0.5 * fs)
    return f"made {len(verts) - 1} coordinate dimensions on {v.name}"


def _chamfer_dim(s, E, op):
    d = op.get("dir", "h")
    v = _view(s, op)
    geo = _geo(s, E, v)
    verts = _vertex_info(geo, op.get("vertices") or [])
    if len(verts) < 2:
        return "nothing made"
    dim, p0, p1 = _lin_dim(s, E, v, verts[0][0], verts[1][0], "DistanceX" if d == "h" else "DistanceY", geo)
    a, b = verts[0][1], verts[1][1]
    mid = _mid(p0, p1)
    dx, dy = f32(a[0] - b[0]), f32(a[1] - b[1])
    if d == "h":
        y_max = f32(max(abs(a[1]), abs(b[1])) + 7.0)
        if math.copysign(1.0, a[1]) < 0:
            y_max = -y_max
        x, y = mid[0], -y_max
        ratio = _fdiv(dy, dx)
    else:
        x_max = f32(max(abs(a[0]), abs(b[0])) + 7.0)
        if math.copysign(1.0, a[0]) < 0:
            x_max = -x_max
        x, y = x_max, -mid[1]
        ratio = _fdiv(dx, dy)
    alpha = round_half_away(f32(math.degrees(abs(f32(math.atan(ratio))))))
    from . import techdraw_dim as D
    spec = D.default_format_spec("DistanceX" if d == "h" else "DistanceY")
    _put(s, E, dim, x, y, format_spec=f"{spec} x{int(alpha)}°")
    return f"made a chamfer dimension on {v.name}"


def _fdiv(a, b):
    if b == 0.0:
        return math.copysign(math.inf, a) if a != 0.0 else math.nan
    return f32(a / b)


def round_half_away(x: float) -> float:
    """std::round."""
    return math.floor(x + 0.5) if x >= 0 else -math.floor(-x + 0.5)


def _arc_length_dim(s, E, op):
    """makeArcLengthDimension: a dimension between cosmetic vertices at the edge's ends, its text the arc's length."""
    v = _view(s, op)
    geo = _geo(s, E, v)
    e = _edge(geo, op.get("edge"))
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    props = GProp_GProps()
    BRepGProp.LinearProperties_s(e.occ, props)
    length = props.Mass() / geo.scale
    a, b = _ends(e)
    count = len(geo.vertices)
    new = [C.make_vertex(_user(geo, v, a)), C.make_vertex(_user(geo, v, b))]
    v = A._replace(s, E, v, cosmetic_vertexes=A._list(v, "cosmetic_vertexes") + new)
    geo = _geo(s, E, v)
    dim, p0, p1 = _lin_dim(s, E, v, f"Vertex{count}", f"Vertex{count + 1}", "Distance", geo)
    mid = _mid(p0, p1)
    _put(s, E, dim, mid[0], -mid[1], arbitrary=True, format_spec="◠ " + "%g" % length)
    return f"made an arc length dimension on {v.name}"


def _dims(s, op, typ=None):
    out = []
    for n in op.get("names") or []:
        o = next((x for x in s.objs if x.name == n), None)
        if isinstance(o, T.DrawViewDimension) and (typ is None or o.type == typ):
            out.append(o)
    return out


def _points_of(s, E, dims):
    doc = T.PageDocument(s.objs, s.shape_of).recompute()
    from . import techdraw_dim as D
    out = {}
    for dim in dims:
        geo = doc.geo.get(dim.view())
        try:
            out[dim.name] = D.linear_points(dim, geo)
        except (D.DimensionError, AttributeError):
            out[dim.name] = ((0.0, 0.0), (0.0, 0.0))
    return out


def _set_xy(s, E, dim, x, y):
    d = T.as_dict(dim)
    d["x"], d["y"] = float(x), float(y)
    new = E._rebuilt(dim, d)
    s.objs[s.objs.index(dim)] = new
    return new


def _dim_position(s, E, op):
    """execPos*ChainDimension and execCascade*Dimension: the dimensions of one kind lined up on the first one's
    line (and, cascading, one spacing further each)."""
    d = op.get("dir", "h")
    cascade = bool(op.get("cascade"))
    dims = _dims(s, op, {"h": "DistanceX", "v": "DistanceY", "o": "Distance"}[d])
    if not dims:
        raise ExtError({"h": "No horizontal dimensions selected", "v": "No vertical dimensions selected",
                        "o": "No oblique dimensions selected"}[d])
    pts = _points_of(s, E, dims)
    fs = _dim_font()
    spacing = f32(_spacing(op))
    if d == "h":
        y_master = f32(dims[0].y)
        if cascade and math.copysign(1.0, y_master) < 0:
            spacing = -spacing
        for dim in dims:
            p1, p2 = pts[dim.name]
            _set_xy(s, E, dim, (p1[0] + p2[0]) / 2.0, y_master)
            if cascade:
                y_master = f32(y_master + spacing)
    elif d == "v":
        x_master = f32(dims[0].x)
        if cascade and math.copysign(1.0, x_master) < 0:
            spacing = -spacing
        for dim in dims:
            p1, p2 = pts[dim.name]
            _set_xy(s, E, dim, x_master, (p1[1] + p2[1]) / -2.0 + 0.5 * fs)
            if cascade:
                x_master = f32(x_master + spacing)
    else:
        first = dims[0]
        p_master = (f32(first.x), f32(first.y), 0.0)
        p1, p2 = pts[first.name]
        dir_master = (p2[0] - p1[0], -(p2[1] - p1[1]), 0.0)
        delta = [0.0, 0.0]
        if cascade:
            ip = _triangle_point(p_master, dir_master, (0.0, 0.0))
            n = _norm(ip)
            delta = [n[0] * spacing, n[1] * spacing]
        for i, dim in enumerate(dims):
            p3 = _triangle_point(p_master, dir_master, (f32(dim.x), f32(dim.y)))
            _set_xy(s, E, dim, p3[0] + delta[0] * i, p3[1] + delta[1] * i)
    return f"{'cascaded' if cascade else 'positioned'} {len(dims)} dimensions"


def _dim_prefix(s, E, op):
    """execInsertPrefixChar: the prefix put in front of each dimension's FormatSpec (n× takes the count, "%s× ")."""
    prefix = op.get("prefix", "⌀")
    if prefix.startswith("%s"):
        prefix = str(op.get("text", "")) + prefix[2:]
    n = 0
    for dim in _dims(s, op):
        d = T.as_dict(dim)
        d["format_spec"] = prefix + dim.format_spec
        s.objs[s.objs.index(dim)] = E._rebuilt(dim, d)
        n += 1
    return f"inserted {prefix!r} into {n} dimensions"


def _dim_remove_prefix(s, E, op):
    """execRemovePrefixChar: everything before the first "%." removed."""
    n = 0
    for dim in _dims(s, op):
        pos = dim.format_spec.find("%.")
        if pos > 0:
            d = T.as_dict(dim)
            d["format_spec"] = dim.format_spec[pos:]
            s.objs[s.objs.index(dim)] = E._rebuilt(dim, d)
            n += 1
    return f"removed the prefix of {n} dimensions"


def _dim_decimals(s, E, op):
    """execIncreaseDecreaseDecimal: the digit after "%." changed by delta while it stays 0 to 9."""
    delta = int(op.get("delta", 1))
    n = 0
    for dim in _dims(s, op):
        spec = dim.format_spec
        i = spec.find("%.") + 2
        if i < 2 or i >= len(spec) or not spec[i].isdigit():
            raise ExtError(f"invalid format {spec!r}")
        k = int(spec[i]) + delta
        if 0 <= k <= 9:
            d = T.as_dict(dim)
            d["format_spec"] = spec[:i] + str(k) + spec[i + 1:]
            s.objs[s.objs.index(dim)] = E._rebuilt(dim, d)
            n += 1
    return f"changed the decimals of {n} dimensions"


# ── CommandExtensionPack.cpp: area and arc length annotations ────────────────────────────────────────────────

def _balloon(s, E, v, text, x, y, ox, oy, shape, end, kink, vp):
    page = s.page_obj()
    n = s.name("Balloon")
    s.add(T.DrawViewBalloon(n, source_view=v.name, origin_x=float(ox), origin_y=float(oy), bubble_shape=shape, end_type=end,
                            kink_length=float(kink), text=text, x=float(x), y=float(y), **vp))
    return n


def _area_annotation(s, E, op):
    """The area of the faces, the centre of mass as the balloon's place; the balloon is a red frameless rectangle."""
    from . import techdraw_dim as D
    v = _view(s, op)
    geo = _geo(s, E, v)
    names = _names(op, "faces", "Face")
    if not names:
        raise ExtError("No faces in selection")
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    wires = C.faces_of(geo, v)
    total, cx, cy = 0.0, 0.0, 0.0
    for n in names:
        i = A._index(n, "Face", wires, "faces")
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(BRepBuilderAPI_MakeFace(wires[i], True).Face(), props)
        area = props.Mass()
        total += area
        c = props.CentreOfMass()
        cx += area * c.X()
        cy += area * c.Y()
    if total > 0.0:
        cx, cy = cx / total, cy / total
    scale = geo.scale
    cx, cy = cx / scale, -(cy / scale)
    total = total / (scale * scale)
    unit, factor = D._user_rows(D.AREA_ROWS, total)
    text = f"{total / factor:.{D.GLOBAL_DECIMALS}f} " + unit.replace("^2", "²")
    _balloon(s, E, v, text, cx, cy, cx, cy, "Rectangle", "None", 0.0,
             {"font_size": 2.0, "line_width": GRAPHIC, "line_visible": False, "color": (1.0, 0.0, 0.0, 1.0)})
    return f"made an area balloon on {v.name}"


def _arc_length_annotation(s, E, op):
    """The length of the edges in a row, a balloon at the middle of their path with a leader to it."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepGProp import BRepGProp
    from OCP.GCPnts import GCPnts_AbscissaPoint
    from OCP.GProp import GProp_GProps
    from . import techdraw_dim as D
    v = _view(s, op)
    geo = _geo(s, E, v)
    names = _names(op, "edges", "Edge")
    if not names:
        raise ExtError("No edges in selection")
    lengths, total = [], 0.0
    for n in names:
        props = GProp_GProps()
        BRepGProp.LinearProperties_s(_edge(geo, n).occ, props)
        total += props.Mass()
        lengths.append(total)
    anchor_len = total * 0.5
    i = 0
    while i < len(lengths) and lengths[i] < anchor_len:
        i += 1
    if i > 0:
        anchor_len -= lengths[i - 1]
    curve = BRepAdaptor_Curve(_edge(geo, names[min(i, len(names) - 1)]).occ)
    mid = curve.Value(curve.LastParameter())
    ab = GCPnts_AbscissaPoint(1e-7, curve, anchor_len, curve.FirstParameter())
    if ab.IsDone():
        mid = curve.Value(ab.Parameter())
    scale = geo.scale
    ax, ay = mid.X() / scale, -(mid.Y() / scale)
    total /= scale
    helper = T.DrawViewDimension("helper", type="Distance")
    text = "◠ " + D.format_value(helper, total, helper.format_spec, "FORMATTED")
    off = 20.0 / scale
    line_width = THIN
    _balloon(s, E, v, text, ax + off, ay + off, ax, ay, "Line", "Filled arrow", 1.0 * line_width,
             {"font_size": 5.0, "line_width": line_width, "line_visible": True, "color": C.DEFAULT_FORMAT["color"]})
    return f"made an arc length balloon on {v.name}"

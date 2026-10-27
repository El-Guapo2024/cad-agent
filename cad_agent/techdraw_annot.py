# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses what FreeCAD's TechDraw annotation commands do to a view and keeps FreeCAD's
# licence, the GNU Lesser General Public License, version 2.1 or (at your option) any later version; the text is in
# ../ui/LICENSE.
#
#   Derived from: src/Mod/TechDraw/Gui/CommandAnnotate.cpp (Copyright (c) 2019 WandererFan),
#                 src/Mod/TechDraw/Gui/TaskCosVertex.cpp (Copyright (c) 2019 Wanderer Fan),
#                 src/Mod/TechDraw/Gui/TaskCosmeticLine.cpp (Copyright (c) 2019 Wanderer Fan),
#                 src/Mod/TechDraw/Gui/TaskCosmeticCircle.cpp (Copyright (c) 2019 Wanderer Fan),
#                 src/Mod/TechDraw/Gui/TaskCenterLine.cpp (Copyright (c) 2019 Wanderer Fan),
#                 src/Mod/TechDraw/Gui/CommandExtensionPack.cpp (Copyright (c) 2022 Wanderer Fan)
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
"""The annotation ops of techdraw_edit.run_ops: cosmetic vertices, lines and circles, centre lines, and the eraser.

    {"op": "cosmetic_vertex", "view": v, "point": [x, y]}            TechDraw_CosmeticVertex (TaskCosVertex)
    {"op": "midpoints"|"quadrants", "view": v, "edges": ["Edge1", ...]}   TechDraw_Midpoints, TechDraw_Quadrants
    {"op": "cosmetic_line", "view": v, "p0": [x, y], "p1": [x, y]}   TechDraw_2PointCosmeticLine (TaskCosmeticLine);
        or "vertices": ["Vertex1", "Vertex2"] for the points
    {"op": "cosmetic_line_edit", "view": v, "edge": "Edge7", "p0", "p1"}   the same panel on a cosmetic line
    {"op": "cosmetic_circle", "view": v, "center": [x, y], "radius": r, "arc"?: bool, "start_angle"?, "end_angle"?}
        TechDraw_CosmeticCircle (TaskCosmeticCircle); or "vertices": [centre, rim] for the centre and radius
    {"op": "cosmetic_circle_edit", "view": v, "edge": "Edge7", ...}  the same panel on a cosmetic circle
    {"op": "centerline", "view": v, "subs": ["Face0"] | ["Edge1", "Edge2"] | ["Vertex1", "Vertex2"], "mode"?,
     "h_shift"?, "v_shift"?, "rotate"?, "extend"?, "format"?}         TechDraw_FaceCenterLine, _2LineCenterLine,
                                                                      _2PointCenterLine (TaskCenterLine)
    {"op": "centerline_edit", "view": v, "edge": "Edge7", ...}       TaskCenterLine on a centre line
    {"op": "erase", "view": v, "subs": ["Edge7", "Vertex9"]}         TechDraw_CosmeticEraser

A point is conventional (y up), unscaled, unrotated, about the view's centre, as the task panels show it. An
"EdgeN" or "VertexN" is the number in the view's geometry, which counts the cosmetic ones after the HLR ones.
This module imports without OCP.
"""
from __future__ import annotations

import math

from . import techdraw as T
from . import techdraw_cosmetic as C

STEP_NAMES = {"cosmetic_vertex": "Add Cosmetic Vertex", "midpoints": "Add midpoint vertices",
              "quadrants": "Add Quadrant vertices", "cosmetic_line": "Create Cosmetic Line",
              "cosmetic_line_edit": "Update Cosmetic Line", "cosmetic_circle": "Create Cosmetic Circle",
              "cosmetic_circle_edit": "Update Cosmetic Circle", "centerline": "Create Centerline",
              "centerline_edit": "Edit Centerline", "erase": "Remove Cosmetic Object"}
OPS = tuple(STEP_NAMES)


def run(s, op: dict) -> str:
    from . import techdraw_edit as E
    kind = op["op"]
    v = s.get(op.get("view"), T.DrawViewPart, "view")
    fn = globals()["_" + kind]
    return fn(s, E, v, op)


# ── helpers ──────────────────────────────────────────────────────────────────────────────────────────────────

def _geo(s, E, v):
    doc = T.PageDocument(s.objs, s.shape_of).recompute()
    geo = doc.geo.get(v.name)
    if geo is None:
        raise E.TechDrawEditError(f"{v.name} has no geometry: {doc.errors.get(v.name, 'nothing to draw')}")
    return geo


def _scale_rot(geo, v):
    return geo.scale, v.rotation


def _user_from_paper(geo, v, x, y):
    """CosmeticVertex::makeCanonicalPointInverted then the panel's own flip: a point of the view's paper geometry
    (scaled, rotated, y down) as the panels show it: unscaled, unrotated, y up."""
    scale, rot = _scale_rot(geo, v)
    px, py = x, -y
    if rot != 0.0:
        a = math.radians(rot)
        px, py = px * math.cos(a) + py * math.sin(a), -px * math.sin(a) + py * math.cos(a)
    return [px / scale, py / scale, 0.0]


def _point(p, what):
    if not (isinstance(p, (list, tuple)) and len(p) in (2, 3)):
        raise ValueError(f"{what}: {p!r} is not a point (x, y)")
    return C.v3(p)


def _index(name, prefix, geo_list, what):
    if not (isinstance(name, str) and name.startswith(prefix) and name[len(prefix):].isdigit()):
        raise ValueError(f"{name!r} is not {prefix}<n>")
    i = int(name[len(prefix):])
    if i >= len(geo_list):
        raise ValueError(f"the view has no {name} ({len(geo_list)} {what})")
    return i


def _replace(s, E, v, **props):
    d = T.as_dict(v)
    d.update(props)
    new = E._rebuilt(v, d)
    s.objs[s.objs.index(v)] = new
    return new


def _list(v, key):
    return [C._thaw(x) if not isinstance(x, dict) else dict(x) for x in v.source_value(key)]


def _vertex_user(geo, v, name):
    i = _index(name, "Vertex", geo.vertices, "vertices")
    vt = geo.vertices[i]
    return _user_from_paper(geo, v, vt.x, vt.y)


# ── the ops ──────────────────────────────────────────────────────────────────────────────────────────────────

def _cosmetic_vertex(s, E, v, op):
    """TaskCosVertex::addCosVertex: the panel's X, Y (conventional) become a CosmeticVertex."""
    p = _point(op.get("point"), "point")
    cv = C.make_vertex(p, op.get("tag"))
    _replace(s, E, v, cosmetic_vertexes=_list(v, "cosmetic_vertexes") + [cv])
    return f"made a cosmetic vertex at ({p[0]:.6g}, {p[1]:.6g}) on {v.name}"


def _edge_points(s, E, v, op, quads: bool):
    """execMidpoints / execQuadrants: for each selected edge, its mid point (or 1/4, 1/2 and 3/4 points), as
    cosmetic vertices."""
    geo = _geo(s, E, v)
    names = op.get("edges") or []
    if not names:
        raise E.TechDrawEditError("Select an edge first")
    out = []
    for n in names:
        i = _index(n, "Edge", geo.edges, "edges")
        pts = _quad_points(geo.edges[i].occ) if quads else [_mid_point(geo.edges[i].occ)]
        for p in pts:
            out.append(C.make_vertex(_user_from_paper(geo, v, p[0], p[1])))
    return out


def _mid_point(edge):
    """BaseGeom::getMidPoint: the point at half the edge's length."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GCPnts import GCPnts_AbscissaPoint
    c = BRepAdaptor_Curve(edge)
    mid_param = (c.FirstParameter() + c.LastParameter()) / 2.0
    length = GCPnts_AbscissaPoint.Length_s(c)
    ab = GCPnts_AbscissaPoint(1e-7, c, length / 2.0, c.FirstParameter())
    if ab.IsDone():
        mid_param = ab.Parameter()
    p = c.Value(mid_param)
    return (p.X(), p.Y())


def _quad_points(edge):
    """BaseGeom::getQuads: the points at a quarter, a half and three quarters of the parameter range."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    c = BRepAdaptor_Curve(edge)
    u, w = c.FirstParameter(), c.LastParameter()
    r = w - u
    out = []
    for t in (u + r / 4.0, u + r / 2.0, u + 3.0 * r / 4.0):
        p = c.Value(t)
        out.append((p.X(), p.Y()))
    return out


def _midpoints(s, E, v, op):
    new = _edge_points(s, E, v, op, False)
    _replace(s, E, v, cosmetic_vertexes=_list(v, "cosmetic_vertexes") + new)
    return f"made {len(new)} midpoint vertices on {v.name}"


def _quadrants(s, E, v, op):
    new = _edge_points(s, E, v, op, True)
    _replace(s, E, v, cosmetic_vertexes=_list(v, "cosmetic_vertexes") + new)
    return f"made {len(new)} quadrant vertices on {v.name}"


def _line_points(s, E, v, op):
    if op.get("vertices"):
        geo = _geo(s, E, v)
        names = op["vertices"]
        if len(names) != 2:
            raise E.TechDrawEditError("You must select 2 vertices")
        return [_vertex_user(geo, v, n) for n in names]
    return [_point(op.get("p0"), "p0"), _point(op.get("p1"), "p1")]


def _cosmetic_line(s, E, v, op):
    """TaskCosmeticLine::createCosmeticLine: addCosmeticEdge(start, end) with the current line format."""
    p0, p1 = _line_points(s, E, v, op)
    ce = C.make_line(p0, p1, op.get("tag"), op.get("format"))
    _replace(s, E, v, cosmetic_edges=_list(v, "cosmetic_edges") + [ce])
    return f"made a cosmetic line on {v.name}"


def _edit_target(s, E, v, op, kinds, what):
    geo = _geo(s, E, v)
    i = _index(op.get("edge"), "Edge", geo.edges, "edges")
    e = geo.edges[i]
    edges = _list(v, "cosmetic_edges")
    k = next((n for n, c in enumerate(edges) if c["tag"] == e.cosmetic_tag and e.cls == "cosmetic"), None)
    if k is None or edges[k]["geom"] not in kinds:
        raise E.TechDrawEditError(f"Selection is not a {what}")
    return edges, k


def _cosmetic_line_edit(s, E, v, op):
    """TaskCosmeticLine::updateCosmeticLine: the end points replaced."""
    edges, k = _edit_target(s, E, v, op, ("line",), "cosmetic line")
    p0, p1 = _line_points(s, E, v, op)
    edges[k] = C.make_line(p0, p1, edges[k]["tag"], op.get("format", edges[k].get("format")))
    _replace(s, E, v, cosmetic_edges=edges)
    return f"updated a cosmetic line on {v.name}"


def _circle_params(s, E, v, op):
    if op.get("vertices"):
        geo = _geo(s, E, v)
        names = op["vertices"]
        pts = [_vertex_user(geo, v, n) for n in names]
        center = pts[0]
        # TaskCosmeticCircle::setUiPrimary: the radius is the distance of the first two points, unscaled
        radius = math.dist(pts[0][:2], pts[1][:2]) if len(pts) > 1 else 0.0
    else:
        center = _point(op.get("center"), "center")
        radius = float(op.get("radius", 0.0))
    if not radius > 0.0:
        raise E.TechDrawEditError(f"cannot create a circle with radius: {radius:.3f}")
    return center, radius


def _circle_dict(op, center, radius, tag, fmt):
    if op.get("arc"):
        return C.make_arc(center, radius, op.get("start_angle", 0.0), op.get("end_angle", 360.0), tag, fmt)
    return C.make_circle(center, radius, tag, fmt)


def _cosmetic_circle(s, E, v, op):
    """TaskCosmeticCircle::createCosmeticCircle: a Circle (or an arc, anticlockwise from the start angle to the end
    angle) added inverted, with the current line format."""
    center, radius = _circle_params(s, E, v, op)
    ce = _circle_dict(op, center, radius, op.get("tag"), op.get("format"))
    _replace(s, E, v, cosmetic_edges=_list(v, "cosmetic_edges") + [ce])
    return f"made a cosmetic {'arc' if op.get('arc') else 'circle'} on {v.name}"


def _cosmetic_circle_edit(s, E, v, op):
    edges, k = _edit_target(s, E, v, op, ("circle", "arc"), "Cosmetic Circle or a Cosmetic Arc of Circle")
    old = edges[k]
    base = {"center": old["center"], "radius": old["radius"], "arc": old["geom"] == "arc",
            "start_angle": old.get("start_angle", 0.0), "end_angle": old.get("end_angle", 360.0)}
    base.update({a: op[a] for a in ("center", "radius", "arc", "start_angle", "end_angle") if a in op})
    center, radius = _circle_params(s, E, v, base)
    edges[k] = _circle_dict(base, center, radius, old["tag"], op.get("format", old.get("format")))
    _replace(s, E, v, cosmetic_edges=edges)
    return f"updated a cosmetic circle on {v.name}"


# centre lines

def _cl_params(op, base=None):
    b = dict(base or {})
    for k in ("mode", "h_shift", "v_shift", "rotate", "extend", "flip"):
        if k in op:
            b[k] = op[k]
    return b


def _centerline(s, E, v, op):
    """TaskCenterLine::createCenterLine: CenterLineBuilder with the panel's mode, shifts, rotation and extension;
    a pathological orientation is corrected as checkPathologicalEdges / checkPathologicalVertices do."""
    subs = list(op.get("subs") or [])
    if not subs:
        raise E.TechDrawEditError("You must select faces or an existing centerline")
    kind = subs[0].rstrip("0123456789")
    typ = {"Face": "Face", "Edge": "Edge", "Vertex": "Vertex"}.get(kind)
    if typ is None:
        raise E.TechDrawEditError(f"{subs[0]!r} is not a Face, an Edge or a Vertex of the view")
    mode = op.get("mode", "Vertical")
    if mode not in C.MODES:
        raise E.TechDrawEditError(f"{mode!r} is not a centerline mode ({', '.join(C.MODES)})")
    if typ == "Face" and len(subs) < 1:
        raise E.TechDrawEditError("CenterLine wrong number of faces.")
    if typ == "Edge" and len(subs) != 2:
        raise E.TechDrawEditError("Select 2 edges for a centerline between 2 lines")
    if typ == "Vertex" and len(subs) != 2:
        raise E.TechDrawEditError("You must select 2 vertices or an existing centerline")
    geo = _geo(s, E, v)
    mode = _pathological(geo, v, typ, subs, mode, E)
    cl = C.make_centerline(typ, mode, subs, op.get("tag"), op.get("h_shift", 0.0), op.get("v_shift", 0.0),
                           op.get("rotate", 0.0), op.get("extend", 0.0), False, op.get("format"))
    # CenterLineBuilder returns nothing for end points that coincide (a vertical line of two points on one vertical)
    ends = C.center_line_ends({**cl, "extend": 0.0, "h_shift": 0.0, "v_shift": 0.0, "rotate": 0.0}, geo, v,
                              geo.scale, v.rotation, _faces(s, E, v))
    if ends is None or math.dist(ends[0], ends[1]) < 1e-7:
        raise E.TechDrawEditError("the centerline's end points are equal: check the orientation")
    _replace(s, E, v, center_lines=_list(v, "center_lines") + [cl])
    return f"made a {typ.lower()} centerline on {v.name}"


def _faces(s, E, v):
    return None


def _pathological(geo, v, typ, subs, mode, E):
    """TaskCenterLine::checkPathologicalEdges / checkPathologicalVertices."""
    if typ == "Edge":
        ok = []
        for n in (subs[0], subs[-1]):
            i = _index(n, "Edge", geo.edges, "edges")
            from .techdraw_view import _ends
            a, b = _ends(geo.edges[i].occ)
            ok.append((abs(a[0] - b[0]) < 1e-4, abs(a[1] - b[1]) < 1e-4))
        if ok[0][0] and ok[1][0]:
            return "Vertical"
        if ok[0][1] and ok[1][1]:
            return "Horizontal"
    elif typ == "Vertex":
        i1 = _index(subs[0], "Vertex", geo.vertices, "vertices")
        i2 = _index(subs[-1], "Vertex", geo.vertices, "vertices")
        p1, p2 = geo.vertices[i1], geo.vertices[i2]
        if abs(p1.x - p2.x) < 1e-4:
            return "Horizontal"
        if abs(p1.y - p2.y) < 1e-4:
            return "Vertical"
    return mode


def _centerline_edit(s, E, v, op):
    """TaskCenterLine on an existing centre line: the panel's values replace the line's."""
    geo = _geo(s, E, v)
    i = _index(op.get("edge"), "Edge", geo.edges, "edges")
    e = geo.edges[i]
    lines = _list(v, "center_lines")
    k = next((n for n, c in enumerate(lines) if c["tag"] == e.cosmetic_tag and e.cls == "centerline"), None)
    if k is None:
        raise E.TechDrawEditError("Selection is not a centerline")
    cl = dict(lines[k])
    for key in ("mode", "h_shift", "v_shift", "rotate", "extend", "flip"):
        if key in op:
            cl[key] = op[key]
    if "format" in op:
        cl["format"] = op["format"]
    if cl["mode"] not in C.MODES:
        raise E.TechDrawEditError(f"{cl['mode']!r} is not a centerline mode ({', '.join(C.MODES)})")
    lines[k] = C.clean("centerline", cl)
    _replace(s, E, v, center_lines=lines)
    return f"edited a centerline of {v.name}"


def _erase(s, E, v, op):
    """CmdTechDrawCosmeticEraser: the cosmetic edges, centre lines and vertices among the selection removed."""
    geo = _geo(s, E, v)
    subs = list(op.get("subs") or [])
    if not subs:
        raise E.TechDrawEditError("Nothing selected")
    cv_tags, ce_tags, cl_tags = set(), set(), set()
    for n in subs:
        if n.startswith("Edge"):
            e = geo.edges[_index(n, "Edge", geo.edges, "edges")]
            if e.cls == "cosmetic":
                ce_tags.add(e.cosmetic_tag)
            elif e.cls == "centerline":
                cl_tags.add(e.cosmetic_tag)
        elif n.startswith("Vertex"):
            vt = geo.vertices[_index(n, "Vertex", geo.vertices, "vertices")]
            if vt.cosmetic_tag:
                cv_tags.add(vt.cosmetic_tag)
        else:
            raise E.TechDrawEditError("Unknown object type in selection")
    props = {}
    if cv_tags:
        props["cosmetic_vertexes"] = [c for c in _list(v, "cosmetic_vertexes") if c["tag"] not in cv_tags]
    if ce_tags:
        props["cosmetic_edges"] = [c for c in _list(v, "cosmetic_edges") if c["tag"] not in ce_tags]
    if cl_tags:
        props["center_lines"] = [c for c in _list(v, "center_lines") if c["tag"] not in cl_tags]
    if props:
        _replace(s, E, v, **props)
    return f"removed {len(cv_tags) + len(ce_tags) + len(cl_tags)} cosmetic object(s) from {v.name}"

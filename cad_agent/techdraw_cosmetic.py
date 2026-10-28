# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses FreeCAD's TechDraw cosmetic geometry and keeps FreeCAD's licence, the GNU
# Lesser General Public License, version 2.1 or (at your option) any later version; the text is in ../ui/LICENSE.
#
#   Derived from: src/Mod/TechDraw/App/Cosmetic.cpp (Copyright (c) 2019 WandererFan, 2022 Benjamin Bræstrup Sayoc),
#                 src/Mod/TechDraw/App/CosmeticVertex.cpp (Copyright (c) 2019 WandererFan, 2022 Benjamin Bræstrup Sayoc),
#                 src/Mod/TechDraw/App/CosmeticExtension.cpp (Copyright (c) 2019 WandererFan),
#                 src/Mod/TechDraw/App/CenterLine.cpp (Copyright (c) 2019 WandererFan, 2022 Benjamin Bræstrup Sayoc),
#                 src/Mod/TechDraw/App/GeometryObject.cpp (Copyright (c) 2013 Luke Parry),
#                 src/Mod/TechDraw/App/Geometry.cpp (Copyright (c) 2012 Luke Parry),
#                 src/Mod/TechDraw/App/LineFormat.cpp (Copyright (c) 2024 wandererfan; LGPL-2.0-or-later),
#                 src/Mod/TechDraw/App/ShapeUtils.cpp (Copyright (c) 2023 WandererFan),
#                 src/Mod/TechDraw/Gui/CommandAnnotate.cpp (Copyright (c) 2019 WandererFan)
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
"""A view's cosmetic geometry: CosmeticVertexes, CosmeticEdges and CenterLines (DrawViewPart's CosmeticExtension).

They are stored unscaled and unrotated in conventional coordinates (y up), the view's centre at the origin, which is
what FreeCAD's Python shows (CosmeticVertex.Point, CosmeticEdge.Start ...); the page file holds them in that form:

    cosmetic_vertexes=[{"tag": "...", "point": [x, y, 0.0]}]
    cosmetic_edges=[{"tag": "...", "geom": "line", "start": [x, y, 0.0], "end": [x, y, 0.0]},
                    {"tag": "...", "geom": "circle", "center": [x, y, 0.0], "radius": r},
                    {"tag": "...", "geom": "arc", "center": [x, y, 0.0], "radius": r, "start_angle": a, "end_angle": b}]
    center_lines=[{"tag": "...", "type": "Face" | "Edge" | "Vertex", "mode": "Vertical" | "Horizontal" | "Aligned",
                   "faces": [...], "edges": [...], "vertexes": [...], "h_shift", "v_shift", "rotate", "extend", "flip"}]

A cosmetic edge or a centre line may carry "format": {"style", "weight", "color", "visible"} (LineFormat) when it is
not the default. apply() puts them into a recomputed view's geometry the way DrawViewPart::postHlrTasks does: the
cosmetic vertices, the cosmetic edges (EdgeClass hard, hlr visible, scaled and rotated by the view's), then the centre
lines (CenterLine::scaledAndRotatedGeometry), after the HLR edges, so Edge<n> and Vertex<n> are FreeCAD's.
"""
from __future__ import annotations

import math
import uuid

from .techdraw_view import EWTOLERANCE, Edge, Vertex, _ends, geom_kind, invert_geometry

MODES = ("Vertical", "Horizontal", "Aligned")
TYPES = ("Face", "Edge", "Vertex")
GEOMS = ("line", "circle", "arc")
# LineFormat's defaults of a fresh profile: Decorations/CenterLineStyle 2 (dashed), the "Graphic" width of the default
# line group, Preferences::normalColor (black)
DEFAULT_FORMAT = {"style": 2, "weight": 0.5, "color": [0.0, 0.0, 0.0, 1.0], "visible": True, "line_number": 2}
CENTER_LINE_NUMBER = 5            # Preferences::CenterLineStyle(): TaskCenterLine's style box opens on "Symmetry"
CENTER_EXTEND = 3.0               # Decorations/CosmoCLExtend


class CosmeticError(ValueError):
    pass


def new_tag() -> str:
    return str(uuid.uuid4())


def v3(p) -> list:
    if not (isinstance(p, (list, tuple)) and len(p) in (2, 3)):
        raise CosmeticError(f"{p!r} is not a point (x, y, z)")
    return [float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.0]


def format_of(d: dict) -> dict:
    """The LineFormat of a cosmetic edge or centre line dict (the default where it holds none)."""
    f = dict(DEFAULT_FORMAT)
    f.update(d.get("format") or {})
    f["color"] = [float(c) for c in f["color"]]
    f["style"], f["line_number"], f["weight"] = int(f["style"]), int(f["line_number"]), float(f["weight"])
    f["visible"] = bool(f["visible"])
    return f


# ─── the dicts ───────────────────────────────────────────────────────────────────────────────────────────────

def make_vertex(point, tag=None) -> dict:
    return {"tag": tag or new_tag(), "point": v3(point)}


def make_line(start, end, tag=None, fmt=None) -> dict:
    d = {"tag": tag or new_tag(), "geom": "line", "start": v3(start), "end": v3(end)}
    return _with_format(d, fmt)


def make_circle(center, radius, tag=None, fmt=None) -> dict:
    return _with_format({"tag": tag or new_tag(), "geom": "circle", "center": v3(center), "radius": float(radius)}, fmt)


def make_arc(center, radius, start_angle, end_angle, tag=None, fmt=None, stored=False) -> dict:
    """An arc: anticlockwise from the start angle to the end angle in the conventional (y up) plane; with `stored` the
    angles are those of the arc FreeCAD keeps, which is in the plane turned over (the thread arcs of TechDraw's
    extension pack are added that way): the same points, the other way round."""
    d = {"tag": tag or new_tag(), "geom": "arc", "center": v3(center), "radius": float(radius),
         "start_angle": float(start_angle), "end_angle": float(end_angle)}
    if stored:
        d["stored"] = True
    return _with_format(d, fmt)


def make_geomformat(index, fmt=None) -> dict:
    """A GeomFormat: the format of the HLR edge Edge<index> (TaskLineDecor)."""
    return {"index": int(index), **format_of({"format": fmt})}


def make_centerline(type_, mode, subs, tag=None, h_shift=0.0, v_shift=0.0, rotate=0.0, extend=0.0, flip=False,
                    fmt=None) -> dict:
    if type_ not in TYPES:
        raise CosmeticError(f"{type_!r} is not a centre line type ({', '.join(TYPES)})")
    if mode not in MODES:
        raise CosmeticError(f"{mode!r} is not a centre line mode ({', '.join(MODES)})")
    key = {"Face": "faces", "Edge": "edges", "Vertex": "vertexes"}[type_]
    d = {"tag": tag or new_tag(), "type": type_, "mode": mode, "faces": [], "edges": [], "vertexes": [],
         "h_shift": float(h_shift), "v_shift": float(v_shift), "rotate": float(rotate), "extend": float(extend),
         "flip": bool(flip)}
    d[key] = list(subs)
    return _with_format(d, fmt)


def _with_format(d: dict, fmt) -> dict:
    if fmt:
        f = format_of({"format": fmt})
        if f != DEFAULT_FORMAT:
            d["format"] = f
    return d


def clean(kind: str, d: dict) -> dict:
    """The dict as the page file holds it: known keys only, numbers as floats, the default format left out."""
    if kind == "vertex":
        return make_vertex(d["point"], d.get("tag"))
    if kind == "edge":
        g = d.get("geom")
        if g == "line":
            return make_line(d["start"], d["end"], d.get("tag"), d.get("format"))
        if g == "circle":
            return make_circle(d["center"], d["radius"], d.get("tag"), d.get("format"))
        if g == "arc":
            return make_arc(d["center"], d["radius"], d["start_angle"], d["end_angle"], d.get("tag"), d.get("format"),
                            bool(d.get("stored")))
        raise CosmeticError(f"{g!r} is not a cosmetic edge ({', '.join(GEOMS)})")
    if kind == "geomformat":
        return make_geomformat(d["index"], {k: d[k] for k in DEFAULT_FORMAT if k in d})
    if kind == "centerline":
        t = d.get("type", "Face")
        subs = d.get({"Face": "faces", "Edge": "edges", "Vertex": "vertexes"}[t]) or []
        return make_centerline(t, d.get("mode", "Vertical"), subs, d.get("tag"), d.get("h_shift", 0.0),
                               d.get("v_shift", 0.0), d.get("rotate", 0.0), d.get("extend", 0.0), d.get("flip", False),
                               d.get("format"))
    raise CosmeticError(kind)


# ─── OCC shapes ──────────────────────────────────────────────────────────────────────────────────────────────

def _stored_edge(ce: dict):
    """CosmeticEdge's geometry as the property holds it: the conventional edge inverted in y (BaseGeom::inverted)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from OCP.Geom import Geom_Circle
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
    g = ce["geom"]
    if g == "line":
        s, e = ce["start"], ce["end"]
        return BRepBuilderAPI_MakeEdge(gp_Pnt(s[0], -s[1], s[2]), gp_Pnt(e[0], -e[1], e[2])).Edge()
    c, r = ce["center"], ce["radius"]
    circ = Geom_Circle(gp_Ax2(gp_Pnt(*c), gp_Dir(0, 0, 1)), r)
    if g == "circle":
        edge = BRepBuilderAPI_MakeEdge(circ, 0.0, 2.0 * math.pi).Edge()
    else:
        if ce.get("stored"):                    # the angles are those of the plane turned over: the arc as it is kept
            circ = Geom_Circle(gp_Ax2(gp_Pnt(c[0], -c[1], c[2]), gp_Dir(0, 0, 1)), r)
            return BRepBuilderAPI_MakeEdge(circ, math.radians(ce["start_angle"]), math.radians(ce["end_angle"])).Edge()
        edge = BRepBuilderAPI_MakeEdge(circ, math.radians(ce["start_angle"]), math.radians(ce["end_angle"])).Edge()
    return invert_geometry(edge)


def _mirror_scale(shape, scale: float):
    """ShapeUtils::mirrorShape(shape, origin, scale): scaled about the origin and mirrored in the XZ plane."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf
    o = gp_Pnt(0, 0, 0)
    t = gp_Trsf()
    t.SetScale(o, scale if scale > 0.0 else 1.0)
    m = gp_Trsf()
    m.SetMirror(gp_Ax2(o, gp_Dir(0, -1, 0)))
    t.Multiply(m)
    return BRepBuilderAPI_Transform(shape, t).Shape()


def _rotate_z(shape, degrees: float):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf
    t = gp_Trsf()
    t.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), math.radians(degrees))
    return BRepBuilderAPI_Transform(shape, t).Shape()


def scaled_and_rotated(stored, scale: float, rotation: float):
    """CosmeticEdge::scaledAndRotatedGeometry: mirrored and scaled, turned by the view's Rotation, mirrored back."""
    from OCP.TopoDS import TopoDS
    s = _mirror_scale(stored, scale)
    s = _rotate_z(s, rotation)
    s = _mirror_scale(s, 1.0)
    return TopoDS.Edge(s)


def vertex_point(cv: dict, scale: float, rotation: float) -> tuple:
    """CosmeticVertex::rotatedAndScaled: the stored (inverted) point scaled, turned by Rotation."""
    x, y, z = cv["point"]
    sx, sy = x * scale, -y * scale
    if rotation != 0.0:
        sy = -sy
        a = math.radians(rotation)
        sx, sy = sx * math.cos(a) - sy * math.sin(a), sx * math.sin(a) + sy * math.cos(a)
        sy = -sy
    return (sx, sy, z * scale)


# ─── a view's geometry ───────────────────────────────────────────────────────────────────────────────────────

def apply(geo, o, scale: float, rotation: float, faces=None) -> None:
    """addCosmeticVertexesToGeom, addCosmeticEdgesToGeom, then addCenterLinesToGeom (DrawViewPart::postHlrTasks and
    execute): geo's vertices and edges get the view's cosmetic ones appended."""
    for cv in o.cosmetic_vertexes:
        cv = _thaw(cv)
        x, y, _ = vertex_point(cv, scale, rotation)
        geo.vertices.append(Vertex(x, y, 0.0, visible=True, cosmetic_tag=cv["tag"]))
    for ce in o.cosmetic_edges:
        ce = _thaw(ce)
        occ = scaled_and_rotated(_stored_edge(ce), scale, rotation)
        e = Edge(occ, geom_kind(occ), "cosmetic", True, -1, ce["tag"])
        e.format = format_of(ce)
        geo.edges.append(e)
    for gf in o.geom_formats:           # DrawViewPart::GeomFormats: the HLR edge with that index looks as it says
        gf = _thaw(gf)
        if 0 <= gf["index"] < len(geo.edges) and geo.edges[gf["index"]].cls not in ("cosmetic", "centerline"):
            geo.edges[gf["index"]].format = format_of({"format": gf})
    for cl in o.center_lines:
        cl = _thaw(cl)
        try:
            ends = center_line_ends(cl, geo, o, scale, rotation, faces)
        except CosmeticError:
            continue
        if ends is None:
            continue
        p1, p2 = ends
        occ = _center_edge(cl, p1, p2, scale, rotation)
        e = Edge(occ, geom_kind(occ), "centerline", True, -1, cl["tag"])
        e.format = format_of(cl)
        geo.edges.append(e)


def _thaw(d):
    """A dict from the normalised (hashable) form techdraw.TDObject keeps."""
    if isinstance(d, dict):
        return d
    from .techdraw import _thawed
    return _thawed(d)


def _center_edge(cl: dict, p1, p2, scale: float, rotation: float):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from OCP.gp import gp_Pnt
    from OCP.TopoDS import TopoDS
    if cl["type"] == "Face":
        e = BRepBuilderAPI_MakeEdge(gp_Pnt(*p1), gp_Pnt(*p2)).Edge()
        s = _mirror_scale(e, scale)
        s = _rotate_z(s, -rotation)
        return TopoDS.Edge(s)
    q1, q2 = (p1[0] * scale, -p1[1] * scale, p1[2] * scale), (p2[0] * scale, -p2[1] * scale, p2[2] * scale)
    return BRepBuilderAPI_MakeEdge(gp_Pnt(*q1), gp_Pnt(*q2)).Edge()


# ─── CenterLine::calcEndPoints ───────────────────────────────────────────────────────────────────────────────

def _sub_index(name: str) -> int:
    digits = "".join(c for c in name if c.isdigit())
    return int(digits) if digits else -1


def _rotate_around_mid(p1, p2, mid, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)

    def one(p):
        return [(p[0] - mid[0]) * c - (p[1] - mid[1]) * s + mid[0], (p[0] - mid[0]) * s + (p[1] - mid[1]) * c + mid[1], 0.0]
    return one(p1), one(p2)


def _circulation(a, b, c) -> bool:
    return a[0] * b[1] + a[1] * c[0] + b[0] * c[1] - c[0] * b[1] - c[1] * a[0] - b[0] * a[1] > 0.0


def _shift_and_unscale(p1, p2, mid, cl, scale):
    clen = [p2[i] - p1[i] for i in range(3)]
    n = math.sqrt(sum(c * c for c in clen))
    if n > 0.0:
        d = [c / n for c in clen]
    else:
        d = clen
    ext = cl["extend"]
    p1 = [p1[i] - d[i] * ext for i in range(3)]
    p2 = [p2[i] + d[i] * ext for i in range(3)]
    return p1, p2, d


def _finish(p1, p2, mid, cl, scale):
    if abs(cl["rotate"]) >= 1e-12:
        p1, p2 = _rotate_around_mid(p1, p2, mid, cl["rotate"])
    if abs(cl["h_shift"]) >= 1e-12:
        p1[0] += cl["h_shift"] * scale
        p2[0] += cl["h_shift"] * scale
    if abs(cl["v_shift"]) >= 1e-12:
        p1[1] += cl["v_shift"] * scale
        p2[1] += cl["v_shift"] * scale
    return [c / scale for c in p1], [c / scale for c in p2]


def center_line_ends(cl: dict, geo, o, scale: float, rotation: float, faces=None):
    """CenterLine::scaledAndRotatedGeometry's end points (unscaled, conventional y), None where FreeCAD's give up."""
    t = cl["type"]
    if t == "Face":
        return _ends_faces(cl, geo, o, scale, rotation, faces)
    if t == "Edge":
        return _ends_2lines(cl, geo, o, scale, rotation)
    return _ends_2points(cl, geo, o, scale, rotation)


def _edge_ends_y_up(geo, name):
    i = _sub_index(name)
    if not (0 <= i < len(geo.edges)):
        raise CosmeticError(f"{name} is not an edge of the view")
    a, b = _ends(geo.edges[i].occ)
    return [a[0], -a[1], 0.0], [b[0], -b[1], 0.0]


def _ends_2lines(cl, geo, o, scale, rotation):
    """CenterLine::calcEndPoints2Lines."""
    names = list(cl["edges"])
    if len(names) != 2:
        raise CosmeticError("CenterLine wrong number of edges.")
    l1p1, l1p2 = _edge_ends_y_up(geo, names[0])
    l2p1, l2p2 = _edge_ends_y_up(geo, names[-1])
    if _circulation(l1p1, l1p2, l2p1) != _circulation(l1p2, l2p2, l2p1):
        l1p1, l1p2 = l1p2, l1p1
    p1 = [(l1p1[i] + l2p1[i]) / 2.0 for i in range(3)]
    p2 = [(l1p2[i] + l2p2[i]) / 2.0 for i in range(3)]
    mid = [(p1[i] + p2[i]) / 2.0 for i in range(3)]
    inhibit_v = abs(p1[1] - p2[1]) < EWTOLERANCE
    inhibit_h = abs(p1[0] - p2[0]) < EWTOLERANCE
    if rotation == 0.0:
        if cl["mode"] == "Vertical" and not inhibit_v:
            p1[0] = p2[0] = mid[0]
        elif cl["mode"] == "Horizontal" and not inhibit_h:
            p1[1] = p2[1] = mid[1]
    p1, p2, _ = _shift_and_unscale(p1, p2, mid, cl, scale)
    return _finish(p1, p2, mid, cl, scale)


def _ends_2points(cl, geo, o, scale, rotation):
    """CenterLine::calcEndPoints2Points."""
    names = list(cl["vertexes"])
    pts = []
    for n in names:
        i = _sub_index(n)
        if 0 <= i < len(geo.vertices):
            v = geo.vertices[i]
            pts.append((v.x, v.y))
    if len(pts) != 2:
        raise CosmeticError("CenterLine wrong number of points.")
    v1 = [pts[0][0], -pts[0][1], 0.0]
    v2 = [pts[1][0], -pts[1][1], 0.0]
    mid = [(v1[i] + v2[i]) / 2.0 for i in range(3)]
    d = [v2[i] - v1[i] for i in range(3)]      # taken before the orientation below, which therefore changes nothing
    inhibit_v = abs(v1[0] - v2[0]) < EWTOLERANCE
    inhibit_h = abs(v1[1] - v2[1]) < EWTOLERANCE
    if rotation == 0.0:
        if cl["mode"] == "Vertical" and not inhibit_v:
            v1[0] = v2[0] = mid[0]
        elif cl["mode"] == "Horizontal" and not inhibit_h:
            v1[1] = v2[1] = mid[1]
    length = math.sqrt(sum(c * c for c in d))
    if length > 0.0:
        d = [c / length for c in d]
    cld = [d[1], -d[0], d[2]]
    p1 = [mid[i] + cld[i] * (length / 2.0) for i in range(3)]
    p2 = [mid[i] - cld[i] * (length / 2.0) for i in range(3)]
    if cl["flip"]:
        p1, p2 = p2, p1
    ext = cl["extend"]
    p1 = [p1[i] + cld[i] * ext for i in range(3)]
    p2 = [p2[i] - cld[i] * ext for i in range(3)]
    return _finish(p1, p2, mid, cl, scale)


def faces_of(geo, o):
    """The view's faces (techdraw_faces.py), found once: the wires of Face0, Face1, ..."""
    if getattr(geo, "face_wires", None) is None:
        from . import techdraw_faces as F
        geo.face_wires = F.find_faces(F.face_edges(geo, o.smooth_visible, o.seam_visible))
    return geo.face_wires


def _ends_faces(cl, geo, o, scale, rotation, faces):
    """CenterLine::calcEndPoints: the box of the faces' edges (turned back by the view's Rotation, centred on
    ShapeUtils::findCentroid, which measures it in the view's CS), a line through its middle, vertical or horizontal."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepTools import BRepTools_WireExplorer
    from .techdraw_view import _compound, _box, find_centroid, move_shape, projection_cs, rotate_shape
    wires = faces_of(geo, o)
    edges = []
    for name in cl["faces"]:
        i = _sub_index(name)
        if not (0 <= i < len(wires)):
            continue
        ex = BRepTools_WireExplorer(wires[i])
        while ex.More():
            edges.append(ex.Current())
            ex.Next()
    if not edges:
        raise CosmeticError("CenterLine wrong number of faces.")
    comp = invert_geometry(_compound(edges))    # FreeCAD's face wires are y up here
    cs = projection_cs(o.direction, o.x_direction)
    if rotation != 0.0:
        comp = rotate_shape(comp, cs, -rotation)
    center = find_centroid(comp, cs)
    comp = move_shape(comp, (-center[0], -center[1], -center[2]))
    box = Bnd_Box()
    box.SetGap(0.0)
    BRepBndLib.AddOptimal_s(comp, box, True, False)
    if box.IsVoid():
        raise CosmeticError("faceBox is void!")
    x0, y0, _, x1, y1, _ = _box(box)
    xs, ys = abs(x1 - x0) / 2.0, abs(y1 - y0) / 2.0
    if cl["mode"] == "Horizontal":
        p1, p2 = [-xs, 0.0, 0.0], [xs, 0.0, 0.0]
    else:                                   # vertical; aligned means nothing for a face
        p1, p2 = [0.0, ys, 0.0], [0.0, -ys, 0.0]
    p1 = [p1[i] + center[i] for i in range(3)]
    p2 = [p2[i] + center[i] for i in range(3)]
    mid = [(p1[i] + p2[i]) / 2.0 for i in range(3)]
    p1, p2, _ = _shift_and_unscale(p1, p2, mid, cl, scale)
    return _finish(p1, p2, mid, cl, scale)

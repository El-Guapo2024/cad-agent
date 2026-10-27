# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses FreeCAD's TechDraw dimensions and keeps FreeCAD's licence, the GNU Lesser
# General Public License, version 2.1 or (at your option) any later version; the text is in ../ui/LICENSE.
#
#   Derived from: src/Mod/TechDraw/App/DrawViewDimension.cpp (Copyright (c) 2013 Luke Parry),
#                 src/Mod/TechDraw/App/DimensionFormatter.cpp (Copyright (c) 2023 WandererFan),
#                 src/Mod/TechDraw/App/Geometry.cpp (Generic::apparentInter; Copyright (c) 2012 Luke Parry),
#                 src/Base/UnitsSchemasData.h (the Standard schema's length, area and angle rows)
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
"""A TechDraw dimension's measure and text, as DrawViewDimension::execute and DimensionFormatter make them.

    measure(dim, geo) -> {"kind": "linear"|"arc"|"angle", points..., "value": mm or degrees}
    text(dim, value)  -> (the dimension's text, (under, over) tolerance texts or None)

A 2D reference names the view's geometry (techdraw_view.ViewGeometry: EdgeN, VertexN), whose coordinates are on the
paper (scaled) with y down; the value is unscaled (getProjectedDimValue divides by the view's Scale). The text is
DimensionFormatter::getFormattedDimensionValue(FORMATTED) in the Standard unit schema with Preferences > General >
Units' two decimals: FormatSpec's %.Nf / %w / %r / %g with its prefix and suffix, " ± tol" for an equal tolerance,
and the separate over and under tolerances (getFormattedToleranceValues) otherwise.
"""
from __future__ import annotations

import math
import re

GLOBAL_DECIMALS = 2                 # Base::UnitsApi::getDecimals(), a fresh profile
DIM_FONT_SIZE = 5.0                 # Preferences::dimFontSizeMM()
DIAMETER_SYMBOL = "⌀"          # Preferences Dimensions/DiameterSymbol ("⌀")

# UnitsSchemasData.h, the Internal (Standard) schema: (threshold, unit, factor), the first threshold above the value
LENGTH_ROWS = ((1e-06, "mm", 1.0), (0.001, "nm", 1e-06), (0.1, "µm", 0.001), (10000.0, "mm", 1.0),
               (10000000.0, "m", 1000.0), (10000000000.0, "km", 1000000.0), (0.0, "m", 1000.0))
AREA_ROWS = ((100.0, "mm^2", 1.0), (1000000.0, "cm^2", 100.0), (1000000000000.0, "m^2", 1000000.0),
             (0.0, "km^2", 1000000000000.0))
ANGLE_ROWS = ((0.0, "°", 1.0),)


class DimensionError(ValueError):
    pass


def index_of(sub: str) -> int:
    """DrawUtil::getIndexFromName: Edge12 -> 12."""
    m = re.search(r"(\d+)$", sub or "")
    if not m:
        raise DimensionError(f"{sub!r} is not a geometry name (Edge0, Vertex3)")
    return int(m.group(1))


def geom_type_of(sub: str) -> str:
    m = re.match(r"^([A-Za-z]+)", sub or "")
    return m.group(1) if m else ""


def ref_type(refs) -> str:
    """DrawViewDimension::getRefTypeSubElements: oneEdge, twoEdge, twoVertex, vertexEdge, threeVertex, oneFace."""
    subs = [r[1] for r in refs]
    kinds = [geom_type_of(s) for s in subs]
    if len(subs) == 1:
        return {"Edge": "oneEdge", "Face": "oneFace", "Vertex": "oneVertex"}.get(kinds[0], "invalid")
    if len(subs) == 2:
        if kinds == ["Edge", "Edge"]:
            return "twoEdge"
        if kinds == ["Vertex", "Vertex"]:
            return "twoVertex"
        if sorted(kinds) == ["Edge", "Vertex"]:
            return "vertexEdge"
    if len(subs) == 3 and kinds == ["Vertex"] * 3:
        return "threeVertex"
    return "invalid"


def _edge(geo, sub):
    i = index_of(sub)
    if i >= len(geo.edges):
        raise DimensionError(f"{sub} is not an edge of the view (it has {len(geo.edges)})")
    return geo.edges[i]


def _vertex(geo, sub):
    i = index_of(sub)
    if i >= len(geo.vertices):
        raise DimensionError(f"{sub} is not a vertex of the view (it has {len(geo.vertices)})")
    v = geo.vertices[i]
    return (v.x, v.y, 0.0)


def _generic_points(e):
    """Generic::points: the edge's Polygon3D nodes, or its two vertices."""
    from .techdraw_view import _ends
    a, b = _ends(e.occ)
    return a, b


def closest_points(s1, s2):
    """DrawViewDimension::closestPoints: BRepExtrema_DistShapeShape's first solution."""
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    ex = BRepExtrema_DistShapeShape(s1, s2)
    if not ex.IsDone():
        raise DimensionError("DVD::closestPoints - BRepExtrema_DistShapeShape failed")
    if ex.NbSolution() == 0:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
    p, q = ex.PointOnShape1(1), ex.PointOnShape2(1)
    return (p.X(), p.Y(), p.Z()), (q.X(), q.Y(), q.Z())


def _vertex_shape(p):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.gp import gp_Pnt
    return BRepBuilderAPI_MakeVertex(gp_Pnt(*p)).Vertex()


def _is_circle(e) -> bool:
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_Circle
    return BRepAdaptor_Curve(e.occ).GetType() == GeomAbs_Circle


def _points_two_circles(dim_type, e0, e1):
    """getPointsTwoCircles on paper (OXYZ): each circle's centre shifted by its radius along X (DistanceX) or Y."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    c0, c1 = BRepAdaptor_Curve(e0.occ).Circle(), BRepAdaptor_Curve(e1.occ).Circle()
    align = (1.0, 0.0) if dim_type == "DistanceX" else (0.0, 1.0)
    p0 = [c0.Location().X(), c0.Location().Y()]
    p1 = [c1.Location().X(), c1.Location().Y()]
    d = (p1[0] - p0[0], p1[1] - p0[1])
    n = math.hypot(*d)
    if n == 0:                      # concentric: gp_Dir centerDir of a zero vector throws, the dimension fails
        raise DimensionError("gp_Dir() - input vector has zero norm")
    dot = (d[0] * align[0] + d[1] * align[1]) / n
    if dot == 0:
        return closest_points(e0.occ, e1.occ)
    s = 1.0 if dot > 0 else -1.0
    p0 = (p0[0] + s * align[0] * c0.Radius(), p0[1] + s * align[1] * c0.Radius(), 0.0)
    p1 = (p1[0] - s * align[0] * c1.Radius(), p1[1] - s * align[1] * c1.Radius(), 0.0)
    return p0, p1


def linear_points(dim, geo):
    """m_linearPoints for Distance, DistanceX and DistanceY, then getLinearPoints' flip of an upward Distance."""
    refs = dim.references_2d
    rt = ref_type(refs)
    if rt == "oneEdge":
        e = _edge(geo, refs[0][1])
        if e.kind != "GENERIC":
            raise DimensionError(f"{dim.name} 2d reference is a {e.kind}")
        pts = _generic_points(e)
    elif rt == "twoEdge":
        e0, e1 = _edge(geo, refs[0][1]), _edge(geo, refs[1][1])
        if dim.type in ("DistanceX", "DistanceY") and _is_circle(e0) and _is_circle(e1):
            pts = _points_two_circles(dim.type, e0, e1)
        else:
            pts = closest_points(e0.occ, e1.occ)
    elif rt == "twoVertex":
        pts = (_vertex(geo, refs[0][1]), _vertex(geo, refs[1][1]))
    elif rt == "vertexEdge":
        if geom_type_of(refs[0][1]) == "Edge":
            e, v = _edge(geo, refs[0][1]), _vertex(geo, refs[1][1])
        else:
            e, v = _edge(geo, refs[1][1]), _vertex(geo, refs[0][1])
        pts = _project_on_edge(e, v)
    else:
        raise DimensionError(f"{dim.name}: a {dim.type} dimension takes one edge, two edges, two vertices or a "
                             "vertex and an edge")
    first, second = pts
    if dim.type == "Distance":
        dv = (second[0] - first[0], second[1] - first[1])
        n = math.hypot(*dv)
        if n > 0 and dv[1] / n > 0:          # dimVec points up: the text would read from the left
            first, second = second, first
    return first, second


def _project_on_edge(e, v):
    """getPointsEdgeVert: the vertex and its projection on the edge's curve (Geom2dAPI_ProjectPointOnCurve)."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAPI import GeomAPI_ProjectPointOnCurve
    from OCP.gp import gp_Pnt
    from .techdraw_view import _curve
    c, f, l = _curve(e.occ)
    if c is None:
        return closest_points(e.occ, _vertex_shape(v))
    proj = GeomAPI_ProjectPointOnCurve(gp_Pnt(*v), c)
    if proj.NbPoints() > 0:
        p = proj.NearestPoint()
        return (v[0], v[1], 0.0), (p.X(), p.Y(), 0.0)
    return closest_points(e.occ, _vertex_shape(v))


def arc_points(dim, geo) -> dict:
    """arcPointsFromBaseGeom for a circle or an arc of one (ellipses: the mean of the radii)."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    refs = dim.references_2d
    if ref_type(refs) != "oneEdge":
        raise DimensionError(f"{dim.name}: a {dim.type} dimension takes one circular edge")
    e = _edge(geo, refs[0][1])
    a = BRepAdaptor_Curve(e.occ)
    out = {"isArc": False}
    if e.kind in ("CIRCLE", "ARCOFCIRCLE"):
        circ = a.Circle()
        c = circ.Location()
        out["center"] = (c.X(), c.Y(), 0.0)
        out["radius"] = circ.Radius()
    elif e.kind in ("ELLIPSE", "ARCOFELLIPSE"):
        el = a.Ellipse()
        c = el.Location()
        out["center"] = (c.X(), c.Y(), 0.0)
        out["radius"] = (el.MinorRadius() + el.MajorRadius()) / 2.0
    else:
        raise DimensionError(f"{dim.name} 2d reference is a {e.kind}")
    cx, cy, _ = out["center"]
    r = out["radius"]
    if e.kind in ("ARCOFCIRCLE", "ARCOFELLIPSE"):
        f, l = a.FirstParameter(), a.LastParameter()
        ps, pm, pe = a.Value(f), a.Value((f + l) / 2), a.Value(l)
        out["isArc"] = True
        out["arcEnds"] = ((ps.X(), ps.Y(), 0.0), (pe.X(), pe.Y(), 0.0))
        out["midArc"] = (pm.X(), pm.Y(), 0.0)
        v1 = (ps.X() - pm.X(), ps.Y() - pm.Y())
        v2 = (pe.X() - pm.X(), pe.Y() - pm.Y())
        out["arcCW"] = (v1[0] * v2[1] - v1[1] * v2[0]) < 0
        out["onCurve"] = ((pm.X(), pm.Y(), 0.0), (cx - r, cy, 0.0))
    else:
        out["onCurve"] = ((cx + r, cy, 0.0), (cx - r, cy, 0.0))
    return out


def _apparent_inter(a0, a1, b0, b1):
    """Generic::apparentInter: where the two lines (not the segments) cross, in the plane."""
    d0 = (a1[0] - a0[0], a1[1] - a0[1])
    d1 = (b1[0] - b0[0], b1[1] - b0[1])
    den = d0[0] * d1[1] - d0[1] * d1[0]
    if abs(den) < 1e-12:
        return a0
    t = ((b0[0] - a0[0]) * d1[1] - (b0[1] - a0[1]) * d1[0]) / den
    return (a0[0] + t * d0[0], a0[1] + t * d0[1], 0.0)


def angle_points(dim, geo) -> dict:
    """getAnglePointsTwoEdges: the apex where the two lines meet and each line's end farthest from it."""
    refs = dim.references_2d
    if ref_type(refs) != "twoEdge":
        raise DimensionError("Angle dimension has non-edge references")
    e0, e1 = _edge(geo, refs[0][1]), _edge(geo, refs[1][1])
    for e in (e0, e1):
        if e.kind != "GENERIC":
            raise DimensionError(f"{dim.name} 2d reference is a {e.kind}")
    s0, t0 = _generic_points(e0)
    s1, t1 = _generic_points(e1)
    apex = _apparent_inter(s0, t0, s1, t1)
    far0 = s0 if math.dist(s0, apex) > math.dist(t0, apex) else t0
    far1 = s1 if math.dist(s1, apex) > math.dist(t1, apex) else t1
    return {"vertex": apex, "first": far0, "second": far1}


def _leg_angle(p, v, q) -> float:
    a = (p[0] - v[0], p[1] - v[1], p[2] - v[2])
    b = (q[0] - v[0], q[1] - v[1], q[2] - v[2])
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    c = max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b)) / (na * nb)))
    return math.degrees(math.acos(c))


def measure(dim, geo) -> dict:
    """DrawViewDimension::execute + getDimValue (Projected) for a dimension on a view's geometry."""
    scale = geo.scale
    t = dim.type
    if t in ("Distance", "DistanceX", "DistanceY"):
        p0, p1 = linear_points(dim, geo)
        d = (p0[0] - p1[0], p0[1] - p1[1])
        value = (math.hypot(*d) if t == "Distance" else abs(d[0]) if t == "DistanceX" else abs(d[1])) / scale
        out = {"kind": "linear", "first": list(p0[:2]), "second": list(p1[:2])}
    elif t in ("Radius", "Diameter"):
        ap = arc_points(dim, geo)
        value = (ap["radius"] if t == "Radius" else 2 * ap["radius"]) / scale
        out = {"kind": "arc", "center": list(ap["center"][:2]), "radius": ap["radius"], "isArc": ap["isArc"],
               "onCurve": [list(p[:2]) for p in ap["onCurve"]]}
        if ap["isArc"]:
            out.update(arcEnds=[list(p[:2]) for p in ap["arcEnds"]], midArc=list(ap["midArc"][:2]), arcCW=ap["arcCW"])
    elif t == "Angle":
        ap = angle_points(dim, geo)
        value = _leg_angle(ap["first"], ap["vertex"], ap["second"])
        out = {"kind": "angle", "vertex": list(ap["vertex"][:2]), "first": list(ap["first"][:2]),
               "second": list(ap["second"][:2])}
    elif t == "Angle3Pt":
        refs = dim.references_2d
        if ref_type(refs) != "threeVertex":
            raise DimensionError("3 point angle dimension has non-vertex references")
        p, v, q = (_vertex(geo, r[1]) for r in refs)
        value = _leg_angle(p, v, q)
        out = {"kind": "angle", "vertex": list(v[:2]), "first": list(p[:2]), "second": list(q[:2])}
    else:
        raise DimensionError(f"{t!r} dimensions are not ported (Distance, DistanceX, DistanceY, Radius, Diameter, "
                             "Angle, Angle3Pt)")
    value = abs(value)
    if dim.show_supplementary and t in ("Angle", "Angle3Pt"):
        value = 180.0 - value
    if dim.inverted:
        value = 360.0 - value if t in ("Angle", "Angle3Pt") else -value
    out["value"] = value
    return out


# ─── DimensionFormatter ──────────────────────────────────────────────────────────────────────────────────────

FORMAT_RE = re.compile(r"%[+-]?[0-9]*\.*[0-9]*[aefgrwAEFGRW]")
NUMERIC_RE = re.compile(r"%[+-]?[0-9]*\.*[0-9]*[aefgwAEFGW]")
WR_RE = re.compile(r"%(?P<dec>.*)(?P<spec>[wWrR])")


def prefix_for(dim_type: str) -> str:
    """DrawViewDimension::getPrefixForDimType."""
    return "R" if dim_type == "Radius" else DIAMETER_SYMBOL if dim_type == "Diameter" else ""


def default_format_spec(dim_type: str, tolerance: bool = False) -> str:
    """DimensionFormatter::getDefaultFormatSpec with Preferences > Dimensions' formatSpec "%.2w"."""
    spec = prefix_for(dim_type) + "%.2w"
    return spec.replace("%", "%+") if tolerance else spec


def prefix_suffix_spec(fspec: str):
    m = FORMAT_RE.search(fspec)
    if not m:
        return "", "", fspec
    return fspec[:m.start()], fspec[m.end():], m.group(0)


def _user_rows(rows, value):
    for threshold, unit, factor in rows:
        if threshold == 0.0 or abs(value) < threshold:
            return unit, factor
    return rows[-1][1], rows[-1][2]


def printf(spec: str, value: float) -> str:
    """printfFormat: a printf floating point conversion (%f %e %g %a with flags, width, precision)."""
    m = re.fullmatch(r"%([-+ #0]*)(\d*)(?:\.(\d*))?([aAeEfFgG])", spec)
    if not m:
        raise ValueError(f"{spec!r} is not a floating point conversion")
    flags, width, prec, conv = m.groups()
    if conv in "aA":
        text = float.hex(value)
        return text.upper() if conv == "A" else text
    py = "%" + flags + width + ("." + prec if prec is not None else "") + conv
    return py % value


def format_value_to_spec(value: float, spec: str) -> str:
    """DimensionFormatter::formatValueToSpec: printf, and %w (as %f without trailing zeros) and %r (rounded)."""
    m = WR_RE.search(spec)
    if not m:
        return printf(spec, value) if NUMERIC_RE.search(spec) else ""
    kind, dec = m.group("spec").lower(), m.group("dec")
    if kind == "w":
        out = printf("%" + dec + "f", value)
        if "." in out:
            out = out.rstrip("0")
            if out.endswith("."):
                out = out[:-1]
        return out
    rounder = float(dec) if dec else 0.0
    rounded = round(value / rounder) * rounder if rounder else value
    n = 0
    if "." in dec:
        d = dec.rstrip("0")
        n = len(d) - d.index(".") - 1
    return printf(f"%.{n}f", rounded)


def format_value(dim, value: float, qspec: str, partial: str = "FORMATTED", is_dim: bool = True) -> str:
    """DimensionFormatter::formatValue (Standard schema, a '.' decimal point)."""
    angular = dim.type in ("Angle", "Angle3Pt")
    area = dim.type == "Area"
    rows = ANGLE_ROWS if angular else AREA_ROWS if area else LENGTH_ROWS
    prefix, suffix, spec = prefix_suffix_spec(qspec)
    unit, factor = _user_rows(rows, value)
    if partial == "UNALTERED":
        return prefix + _user_string(value, unit, factor) + suffix
    if not FORMAT_RE.search(qspec):
        return qspec
    if re.search("%g", spec, re.I):
        spec = re.sub("%g", f"%.{GLOBAL_DECIMALS}f", spec, flags=re.I)
    user = value if angular else value / factor
    if area:
        unit = unit.replace("^2", "²")
    formatted = format_value_to_spec(user, spec)
    if partial == "FORMATTED":
        unit_str = ""
        if angular:
            unit_str = "°"
        elif (dim.show_units or area) and not (is_dim and have_tolerance(dim)):
            unit_str = " " + unit
        return prefix + formatted + unit_str + suffix
    if partial == "UNIT":
        return unit if (angular or dim.show_units or area) else ""
    return formatted


def _user_string(value, unit, factor) -> str:
    """Quantity::getUserString in the Standard schema: the value in the unit, Decimals places, a space before the
    unit but for the degree sign."""
    return f"{value / factor:.{GLOBAL_DECIMALS}f}" + ("" if unit == "°" else " ") + unit


def have_tolerance(dim) -> bool:
    return (abs(dim.over_tolerance) >= 1e-12 or abs(dim.under_tolerance) >= 1e-12) and not dim.arbitrary_tolerances


def has_over_under(dim) -> bool:
    return dim.arbitrary_tolerances or abs(dim.over_tolerance) >= 1e-12 or abs(dim.under_tolerance) >= 1e-12


def tolerance_values(dim, partial="FORMATTED"):
    """getFormattedToleranceValues: (under, over)."""
    if dim.arbitrary_tolerances:
        return dim.format_spec_under_tolerance, dim.format_spec_over_tolerance
    return (format_value(dim, dim.under_tolerance, dim.format_spec_under_tolerance, partial, False),
            format_value(dim, dim.over_tolerance, dim.format_spec_over_tolerance, partial, False))


def formatted_value(dim, value: float, partial: str = "FORMATTED") -> str:
    """DimensionFormatter::getFormattedDimensionValue."""
    if dim.arbitrary:
        return dim.format_spec
    if dim.equal_tolerance and not dim.theoretical_exact and \
            (abs(dim.over_tolerance) >= 1e-12 or dim.arbitrary_tolerances):
        label = format_value(dim, value, dim.format_spec, "FORMATTED", True)
        tol = dim.format_spec_over_tolerance if dim.arbitrary_tolerances else \
            format_value(dim, dim.over_tolerance, dim.format_spec_over_tolerance, "FORMATTED", False)
        tol = re.sub(r"^\s*\+", "", tol)
        return label + " ± " + tol
    return format_value(dim, value, dim.format_spec, partial, True)


def text(dim, value: float):
    """What the dimension shows: its text, and (under, over) when it has unequal tolerances
    (QGIViewDimension's QGIDatumLabel draws them beside the text)."""
    main = formatted_value(dim, value)
    tol = None
    if has_over_under(dim) and not dim.equal_tolerance and not dim.theoretical_exact and not dim.arbitrary:
        tol = tolerance_values(dim)
    return main, tol

"""The OpenCascade side of Sketcher_Offset (DrawSketchHandlerOffset.h, Mod/Sketcher/Gui at 3160daf1e2b6, 2023 Pierre-Louis
Boyer, LGPL-2.1-or-later), for the sketch kernel (cad_agent/sketch_kernel.py): the request

    {"op": "offset", "curves": [[geo, ...], ...], "join": 0 | 2, "point": [x, y] or "length": d}

holds the selected curves grouped as the tool groups them (generatevCC, done by the page: ui/src/sketchoffset.ts), the
join type (OCC's Arc 0 or Intersection 2, the tool's construction method) and either the cursor (the length is then
findOffsetLength's: the distance to the nearest source wire, negative inside a closed one) or the length. The answer:

    {"length": d, "on_wire": [x, y], "geometry": [geo or null, ...]}

the offset curves of BRepOffsetAPI_MakeOffset in TopExp_Explorer's order of the result's edges, each as the tool
converts it (curveToLine, curveToCircleOrArc; null for an edge of another kind, which the tool skips but counts),
and on_wire the nearest point on the source wire (where the on-view parameter's dimension starts).
"""
from __future__ import annotations

import math

from .sketch_kernel import CONFUSION, KernelError, geom

try:
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
    from OCP.BRepBuilderAPI import (BRepBuilderAPI_Copy, BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace,
                                    BRepBuilderAPI_MakeVertex, BRepBuilderAPI_MakeWire)
    from OCP.BRepClass import BRepClass_FaceClassifier
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffset
    from OCP.GeomAbs import GeomAbs_Arc, GeomAbs_Circle, GeomAbs_Intersection, GeomAbs_Line, GeomAbs_Plane
    from OCP.gp import gp, gp_Pln, gp_Pnt
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_IN
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
except ImportError:                     # pragma: no cover
    pass


def _edge(d):
    """Part::GeomCurve::toShape: BRepBuilderAPI_MakeEdge(curve, FirstParameter, LastParameter)."""
    c = geom(d)
    return BRepBuilderAPI_MakeEdge(c, c.FirstParameter(), c.LastParameter()).Edge()


def source_wires(curves: list[list[dict]]):
    """generateSourceWires: a wire of each continuous curve, a closed one turned counter-clockwise about +Z; a single
    line's wire after the others, the others first (inserted at the front). Also onlySingleLines."""
    wires, only_lines = [], True
    for cc in curves:
        mk = BRepBuilderAPI_MakeWire()
        for g in cc:
            mk.Add(_edge(g))
        wire = mk.Wire()
        if wire.Closed():
            face = BRepBuilderAPI_MakeFace(wire)
            if face.IsDone():
                surf = BRepAdaptor_Surface(face.Face())
                if surf.GetType() == GeomAbs_Plane and surf.Plane().Axis().Direction().Z() < 0:
                    wire.Reverse()
        if len(cc) == 1 and cc[0]["type"] == "LineSegment":
            wires.append(wire)
        else:
            wires.insert(0, wire)
            only_lines = False
    return wires, only_lines


def offset_length(wires, point):
    """findOffsetLength: the distance from the cursor to the nearest source wire (the last of equals), negative when the
    cursor is inside a closed one; and the nearest point on it. None when there is none."""
    best, on = float("inf"), None
    vertex = BRepBuilderAPI_MakeVertex(gp_Pnt(point[0], point[1], 0.0)).Vertex()
    for wire in wires:
        dist = BRepExtrema_DistShapeShape(wire, vertex)
        if not dist.IsDone():
            continue
        d = dist.Value()
        if d == min(d, best):
            best = d
            p = dist.PointOnShape1(1)
            on = [p.X(), p.Y()]
            if BRep_Tool.IsClosed_s(wire):
                face = BRepBuilderAPI_MakeFace(wire).Face()
                if BRepClass_FaceClassifier(face, gp_Pnt(point[0], point[1], 0.0), CONFUSION).State() == TopAbs_IN:
                    best = -best
    return (None, None) if on is None else (best, on)


def make_offset(wires, only_lines: bool, join: int, length: float):
    """makeOffsetShape(allowOpenResult=false): BRepOffsetAPI_MakeOffset of the wires (on the XY plane's face when every
    wire is a single line), Arc or Intersection joins, copied (BRepBuilderAPI_Copy)."""
    if only_lines:
        mk = BRepOffsetAPI_MakeOffset(BRepBuilderAPI_MakeFace(gp_Pln(gp.Origin_s(), gp.DZ_s())).Face())
    else:
        mk = BRepOffsetAPI_MakeOffset()
    mk.Init(GeomAbs_Arc if join == 0 else GeomAbs_Intersection, False)
    for w in wires:
        mk.AddWire(w)
    mk.Perform(length)
    shape = mk.Shape()
    if shape.IsNull():
        return None
    return BRepBuilderAPI_Copy(shape).Shape()


def _to_geo(edge):
    """curveToLine and curveToCircleOrArc (None for the other kinds)."""
    curve = BRepAdaptor_Curve(edge)
    t = curve.GetType()
    if t == GeomAbs_Line:
        first, last = curve.FirstParameter(), curve.LastParameter()
        first = -10000.0 if abs(first) > 1e99 else first
        last = 10000.0 if abs(last) > 1e99 else last
        p1, p2 = curve.Value(first), curve.Value(last)
        return {"type": "LineSegment", "start": [p1.X(), p1.Y()], "end": [p2.X(), p2.Y()]}
    if t == GeomAbs_Circle:
        circ = curve.Circle()
        cnt = circ.Location()
        beg, end = curve.Value(curve.FirstParameter()), curve.Value(curve.LastParameter())
        if beg.SquareDistance(end) < CONFUSION:
            return {"type": "Circle", "center": [cnt.X(), cnt.Y()], "radius": circ.Radius()}
        # GeomArcOfCircle of Geom_TrimmedCurve(circle, u1, u2), reverseIfReversed: counter-clockwise about +Z, so on a
        # circle whose axis is -Z it runs from the trim's end to its start; its angles as the Sketcher reads them
        # (getRange with emulateCCWXY: from +X)
        a, b = (beg, end) if circ.Axis().Direction().Z() > 0 else (end, beg)
        two = 2 * math.pi
        a1 = math.atan2(a.Y() - cnt.Y(), a.X() - cnt.X())
        a1 -= math.floor(a1 / two) * two
        a2 = a1 + (curve.LastParameter() - curve.FirstParameter())
        return {"type": "ArcOfCircle", "center": [cnt.X(), cnt.Y()], "radius": circ.Radius(),
                "start_angle": a1, "end_angle": a2}
    return None


def offset(req: dict) -> dict:
    curves = req.get("curves") or []
    if not curves:
        raise KernelError("Selection has no valid geometries.")
    wires, only_lines = source_wires(curves)
    on = None
    if "length" in req:
        length = float(req["length"])
    else:
        length, on = offset_length(wires, req["point"])
        if length is None:
            length = 1.0
    out = {"length": length, "on_wire": on, "geometry": []}
    if abs(length) <= CONFUSION:
        return out
    shape = make_offset(wires, only_lines, int(req.get("join", 0)), length)
    if shape is None:
        return out
    ex = TopExp_Explorer(shape, TopAbs_EDGE)
    while ex.More():
        out["geometry"].append(_to_geo(TopoDS.Edge(ex.Current())))
        ex.Next()
    return out

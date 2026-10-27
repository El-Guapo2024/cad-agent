"""External geometry FreeCAD makes besides the projection of an edge, a vertex or a flat face: the branches of
SketchObject::rebuildExternalGeometry (Mod/Sketcher/App/SketchObjectExternal.cpp at 3160daf1e2b6, 2008 Jürgen
Riegel, LGPL-2.0-or-later) that cad_agent/feature_attach.py's project() hands here:

    a face that is not flat, projected   -> projectShape: OCCT's hidden-line removal (HLRBRep_Algo) seen along the
                                            sketch's normal, every edge it gives (visible and hidden, sharp, smooth
                                            and outline) as processEdge2 makes it
    an intersection (Sketcher_Intersection, ExternalTypes 1, or 2 for both)
                                         -> FCBRepAlgoAPI_Section of the reference and the sketch's plane, each
                                            edge as processEdge makes it, the arcs of a face fitted into one
                                            circle (fitArcs), the section's lone vertices as points

and SketchObject::port_reversedExternalArcs (SketchObjectConstraints.cpp), Validate's Swap Endpoints in
Constraints: an arc FreeCAD keeps on a circle whose axis is -Z (GeomArcOfConic::isReversed) is "reversed": True in
its geometry dict.
"""
from __future__ import annotations

import math

from .feature import FeatureError

try:
    from OCP.BRep import BRep_Tool
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.HLRAlgo import HLRAlgo_Projector
    from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
    from OCP.TopExp import TopExp, TopExp_Explorer
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Lin, gp_Trsf
except ImportError:                     # pragma: no cover
    pass

KINDS = ("Projection", "Intersection", "Both")      # Sketcher::SketchObject::ExtType, ExternalTypes' values
CONFUSION = 1e-7
ARC_FIT_TOLERANCE = CONFUSION * 10.0                 # ArcFitTolerance's default (Mod/Sketcher/General)


# ── projectShape and processFace's other branch: a face that is not flat ───────────────────────────────────────

def project_shape(shape, pr) -> list:
    """projectShape(inShape, sketchAx3): HLRBRep_Algo with the projector of the sketch's axes; the visible, smooth,
    outline and iso compounds, then the hidden ones, in the sketch's coordinates (the projector's)."""
    algo = HLRBRep_Algo()
    algo.Add(shape)
    trsf = gp_Trsf()
    trsf.SetTransformation(pr.ax3)
    algo.Projector(HLRAlgo_Projector(trsf, False, 1.0))
    algo.Update()
    algo.Hide()
    to = HLRBRep_HLRToShape(algo)
    res = []
    for get in (to.VCompound, to.Rg1LineVCompound, to.OutLineVCompound, to.IsoLineVCompound,
                to.HCompound, to.Rg1LineHCompound, to.OutLineHCompound, to.IsoLineHCompound):
        s = get()
        if not s.IsNull():
            res.append(s)
    return res


def curved_face(face, pr) -> list[dict]:
    from .feature_attach_curves import process_edge2
    geos = []
    for s in project_shape(face, pr):
        ex = TopExp_Explorer(s, TopAbs_EDGE)
        while ex.More():
            geos += process_edge2(TopoDS.Edge(ex.Current()))
            ex.Next()
    return geos


def edge_on_fallback(plane, pr, project_line) -> list[dict]:
    """processFace, a flat face edge-on to the sketch whose edges gave no line: the line through the face's plane
    along the two planes' crossing, as projectLine draws an infinite line (20000 long)."""
    d = plane.Axis().Direction().Crossed(pr.plane.Axis().Direction())
    mk = BRepBuilderAPI_MakeEdge(gp_Lin(plane.Location(), d))
    if not mk.IsDone():
        return []
    c = BRepAdaptor_Curve(mk.Edge())
    return [project_line(c, pr)]


# ── the intersection with the sketch's plane ─────────────────────────────────────────────────────────────────

def section(shape, pr):
    """FCBRepAlgoAPI_Section(refSubShape, sketchPlane): checked valid, auto fuzzy (getBooleanFuzzy times the
    inputs' box diagonal times Confusion), run parallel and built in the constructor, so that the Approximation
    rebuildExternalGeometry asks for afterwards changes nothing."""
    from .topo_boolean import auto_fuzzy
    if not BRepCheck_Analyzer(shape).IsValid():
        raise FeatureError("Base shape is not valid for boolean operation")
    mk = BRepAlgoAPI_Section(shape, pr.plane, False)
    shapes = list(mk.Arguments()) + list(mk.Tools())
    mk.SetFuzzyValue(auto_fuzzy(shapes))
    mk.SetRunParallel(True)
    mk.Build()
    if not mk.IsDone():
        raise FeatureError("Failed to get intersection")
    return mk.Shape()


def _sub_shapes(shape, kind):
    """TopoShape::getSubTopoShapes(kind): TopExp::MapShapes' order (the explorer's, each shape once)."""
    out = []
    ex = TopExp_Explorer(shape, kind)
    while ex.More():
        s = ex.Current()
        if not any(s.IsSame(o) for o in out):
            out.append(s)
        ex.Next()
    return out


def _lone_vertices(shape):
    """getSubShapes(TopAbs_VERTEX, TopAbs_EDGE): the vertices not on an edge."""
    out = []
    ex = TopExp_Explorer(shape, TopAbs_VERTEX, TopAbs_EDGE)
    while ex.More():
        out.append(TopoDS.Vertex(ex.Current()))
        ex.Next()
    return out


def _one_wire(edges) -> bool:
    """makeElementWires(edges).countSubShapes(TopAbs_WIRE) == 1: the section's edges chain into one wire."""
    if not edges:
        return False
    ends = []
    for e in edges:
        ed = TopoDS.Edge(e)
        ends.append([BRep_Tool.Pnt_s(TopExp.FirstVertex_s(ed)), BRep_Tool.Pnt_s(TopExp.LastVertex_s(ed))])
    seen, todo = {0}, [0]
    while todo:
        i = todo.pop()
        for j in range(len(edges)):
            if j not in seen and any(p.Distance(q) < CONFUSION for p in ends[i] for q in ends[j]):
                seen.add(j)
                todo.append(j)
    return len(seen) == len(edges)


def fit_arcs(geos: list[dict]) -> dict | None:
    """fitArcs(arcs, P1, P2, ArcFitTolerance): arcs of one radius made one circle. FreeCAD's wire explorer loop
    (`while (!exp.More()) exp.Next();`) never moves, so the wire's first and last vertex are the same one and
    the arcs always become a whole circle, about the first arc's centre."""
    radius, center = 0.0, None
    for g in geos:
        if g.get("type") != "ArcOfCircle":
            return None
        if radius == 0.0:
            radius, center = g["radius"], g["center"]
        elif abs(radius - g["radius"]) > ARC_FIT_TOLERANCE:
            return None
    if radius == 0.0:
        return None
    return {"type": "Circle", "center": list(center), "radius": radius, "construction": True}


def intersection(shape, pr, process_edge, geos: list[dict], where) -> list[dict]:
    """rebuildExternalGeometry's intersection: geos (the projection's, for ExtType Both) followed by the section's
    edges, fitted into a circle for a face, and its lone vertices."""
    from .feature_attach import _point
    sec = section(shape, pr)
    edges = _sub_shapes(sec, TopAbs_EDGE)
    geos = list(geos)
    for e in edges:
        geos += process_edge(TopoDS.Edge(e), pr, where)
    if shape.ShapeType() == TopAbs_FACE and len(geos) > 1 and _one_wire(edges):
        fit = fit_arcs(geos)
        if fit is not None:
            geos = [fit]
    for v in _lone_vertices(sec):
        geos.append(_point(pr.local(pr.near(BRep_Tool.Pnt_s(v)))))
    return geos


# ── port_reversedExternalArcs ────────────────────────────────────────────────────────────────────────────────

def swap_reversed(external: list[dict], cons: list[dict]) -> tuple[list[dict], int]:
    """SketchObject::port_reversedExternalArcs(false): every constraint naming the start or end of a reversed
    external arc of circle (GeoId -3 - i) names the other end instead. The constraints and how many changed."""
    from .sketch_commands import END, REF_EXT, START
    rev = {REF_EXT - i for i, g in enumerate(external) if g.get("type") == "ArcOfCircle" and g.get("reversed")}
    out, n = [], 0
    for c in cons:
        c2, hit = dict(c), False
        for k in ("first", "second", "third"):
            g, p = c.get(k), c.get(k + "_pos")
            if g in rev and p in (START, END):
                c2[k + "_pos"] = END if p == START else START
                hit = True
        out.append(c2)
        n += hit
    return out, n


def kind_flags(kind: str) -> tuple[bool, bool]:
    """(projection, intersection) of an ExternalTypes value."""
    if kind not in KINDS:
        raise FeatureError(f"external geometry type {kind!r} is not one of {', '.join(KINDS)}")
    return kind in ("Projection", "Both"), kind in ("Intersection", "Both")

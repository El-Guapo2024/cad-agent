"""External geometry of the curves other than lines and circles in the sketch's plane: the branches of
SketchObject::rebuildExternalGeometry's processEdge (Mod/Sketcher/App/SketchObjectExternal.cpp at 3160daf1e2b6, 2008
Jürgen Riegel, LGPL-2.0-or-later) that cad_agent/feature_attach.py's _process_edge hands here:

    a circle at an angle to the sketch     -> an ellipse (or an arc of one), its major axis along the planes' crossing
    an ellipse                             -> its projection: an ellipse, a circle, or a line when edge-on
    any other edge (a B-spline, ...)       -> a line when its plane is edge-on to the sketch; the edge moved onto the
                                              sketch when its plane is parallel; else BRepOffsetAPI_NormalProjection,
                                              each projected edge as processEdge2 makes it

The geometry comes back in the sketch's coordinates as the solver's JSON, construction (external geometry is). An arc
whose curve runs clockwise about the sketch's normal (its own axis -Z) is given as the Sketcher reads it
(GeomArc*::getRange with emulateCCWXY): counter-clockwise from its other end.
"""
from __future__ import annotations

import math

from .feature import FeatureError

try:
    from OCP.Bnd import Bnd_Box
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy, BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_Transform
    from OCP.BRepLib import BRepLib_FindSurface
    from OCP.BRepOffsetAPI import BRepOffsetAPI_NormalProjection
    from OCP.Geom import Geom_Circle, Geom_Ellipse, Geom_TrimmedCurve
    from OCP.GeomAbs import (GeomAbs_BezierCurve, GeomAbs_BSplineCurve, GeomAbs_Circle, GeomAbs_Ellipse,
                             GeomAbs_Hyperbola, GeomAbs_Line, GeomAbs_OffsetCurve, GeomAbs_Parabola)
    from OCP.GeomAdaptor import GeomAdaptor_Surface
    from OCP.GeomAPI import GeomAPI_ProjectPointOnCurve, GeomAPI_ProjectPointOnSurf
    from OCP.GeomConvert import GeomConvert
    from OCP.gp import gp_Ax1, gp_Ax2, gp_Dir, gp_Elips, gp_Pnt, gp_Trsf, gp_Vec, gp_XYZ
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp, TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS
except ImportError:                     # pragma: no cover
    pass

CONFUSION = 1e-7
PCONFUSION = CONFUSION * 0.01
ANGULAR = 1e-12
TWO_PI = 2 * math.pi


def _adjust_periodic(ufirst, ulast, preci, u1, u2):
    """ElCLib::AdjustPeriodic (OCP's binding of it loses U1 and U2)."""
    period = ulast - ufirst
    u1 -= math.floor((u1 - ufirst) / period) * period
    if ulast - u1 < preci:
        u1 -= period
    u2 -= math.floor((u2 - u1) / period) * period
    if u2 - u1 < preci:
        u2 += period
    return u1, u2


def _xy(p):
    return [p.X(), p.Y()]


# ── the Sketcher's view of a curve in the sketch's coordinates ────────────────────────────────────────────────────

def _ccw_angles(start, end, center, span):
    """An arc's angles counter-clockwise about +Z from +X, from its counter-clockwise start point."""
    a1 = math.atan2(start.Y() - center.Y(), start.X() - center.X())
    a1 -= math.floor(a1 / TWO_PI) * TWO_PI
    return a1, a1 + span


def circle_dict(c, first=None, last=None):
    """A Geom_Circle (trimmed to [first, last] for an arc) as the sketch's Circle or ArcOfCircle."""
    cnt = c.Location()
    if first is None:
        return {"type": "Circle", "center": _xy(cnt), "radius": c.Radius(), "construction": True}
    tc = Geom_TrimmedCurve(c, first, last)
    s, e = tc.StartPoint(), tc.EndPoint()
    rev = c.Position().Direction().Z() < 0
    if rev:
        s, e = e, s
    a1, a2 = _ccw_angles(s, e, cnt, tc.LastParameter() - tc.FirstParameter())
    d = {"type": "ArcOfCircle", "center": _xy(cnt), "radius": c.Radius(), "start_angle": a1, "end_angle": a2,
         "construction": True}
    if rev:                                         # GeomArcOfConic::isReversed (Validate's reversed arcs)
        d["reversed"] = True
    return d


def conic_dict(kind, c, first=None, last=None):
    """A Geom_Ellipse, Geom_Hyperbola or Geom_Parabola (trimmed for an arc) as the sketch's conic: on an axis -Z the
    frame's Y turns over, so the parameter u is -u in the sketch's own (counter-clockwise) frame."""
    pos = c.Position()
    xd = pos.XDirection()
    d = {"type": kind, "center": _xy(c.Location()), "x_axis": [xd.X(), xd.Y()], "construction": True}
    if kind == "ArcOfParabola":
        d["focal"] = c.Focal()
    else:
        d["major_radius"], d["minor_radius"] = c.MajorRadius(), c.MinorRadius()
    if first is not None:
        tc = Geom_TrimmedCurve(c, first, last)
        u1, u2 = tc.FirstParameter(), tc.LastParameter()
        if pos.Direction().Z() < 0:
            u1, u2 = -u2, -u1
        d["start_angle"], d["end_angle"] = u1, u2
    return d


def bspline_dict(b):
    from .sketch_kernel import bspline_dict as bd
    return {**bd(b), "construction": True}


# ── processEdge2: an edge projected (and moved into the sketch's coordinates) ─────────────────────────────────────

def process_edge2(edge) -> list[dict]:
    pc = BRepAdaptor_Curve(edge)
    t = pc.GetType()
    f, l = pc.FirstParameter(), pc.LastParameter()
    p1, p2 = pc.Value(f), pc.Value(l)
    if t == GeomAbs_Line:
        if p1.Distance(p2) < CONFUSION:
            return [{"type": "Point", "at": [(p1.X() + p2.X()) / 2, (p1.Y() + p2.Y()) / 2], "construction": True}]
        return [{"type": "LineSegment", "start": _xy(p1), "end": _xy(p2), "construction": True}]
    if t == GeomAbs_Circle:
        c = Geom_Circle(pc.Circle())
        if p1.SquareDistance(p2) < CONFUSION:
            # GeomCircle(): setRadius, setCenter: on +Z whatever the projection's axis
            return [{"type": "Circle", "center": _xy(c.Location()), "radius": c.Radius(), "construction": True}]
        return [circle_dict(c, f, l)]
    if t == GeomAbs_BSplineCurve:
        # (FreeCAD splits it at its C2 discontinuities, GeomConvert_BSplineCurveKnotSplitting, and uses none of it)
        return [bspline_dict(pc.BSpline())]
    if t in (GeomAbs_Hyperbola, GeomAbs_Parabola):
        from OCP.Geom import Geom_Hyperbola, Geom_Parabola
        kind = "ArcOfHyperbola" if t == GeomAbs_Hyperbola else "ArcOfParabola"
        c = Geom_Hyperbola(pc.Hyperbola()) if t == GeomAbs_Hyperbola else Geom_Parabola(pc.Parabola())
        if p1.SquareDistance(p2) < CONFUSION:
            raise FeatureError("external geometry: a whole hyperbola or parabola is not sketch geometry")
        return [conic_dict(kind, c, f, l)]
    if t == GeomAbs_Ellipse:
        c = Geom_Ellipse(pc.Ellipse())
        if p1.SquareDistance(p2) < CONFUSION:
            return [conic_dict("Ellipse", c)]
        return [conic_dict("ArcOfEllipse", c, f, l)]
    if t == GeomAbs_BezierCurve:
        return [bspline_dict(GeomConvert.CurveToBSplineCurve_s(pc.Bezier()))]
    if t == GeomAbs_OffsetCurve:
        return [bspline_dict(GeomConvert.CurveToBSplineCurve_s(pc.OffsetCurve()))]
    raise FeatureError("Not yet supported geometry for external geometry")


# ── adjustParameterRange ──────────────────────────────────────────────────────────────────────────────────────────

def _adjust_parameter_range(edge, pr, curve):
    """Which way round a periodic projected curve is trimmed: the original edge's ends and middle projected onto
    it, the trim swapped when the middle falls outside."""
    orig = BRepAdaptor_Curve(edge).Curve().Curve()
    e = TopoDS.Edge(edge.Located(TopLoc_Location()))
    fp = BRep_Tool.Pnt_s(TopExp.FirstVertex_s(e))
    lp = BRep_Tool.Pnt_s(TopExp.LastVertex_s(e))
    f = GeomAPI_ProjectPointOnCurve(fp, orig).LowerDistanceParameter()
    l = GeomAPI_ProjectPointOnCurve(lp, orig).LowerDistanceParameter()

    def adjust(c, a, b):
        if c.IsPeriodic():
            return _adjust_periodic(c.FirstParameter(), c.LastParameter(), min(abs(a - b) / 2, PCONFUSION), a, b)
        return a, b

    f, l = adjust(orig, f, l)
    m = (l - f) * 0.5 + f
    mid = orig.Value(m)
    trsf = edge.Location().Transformation()
    pts = []
    for p in (mid, fp, lp):
        q = gp_Pnt(p.XYZ())
        q.Transform(trsf)
        q = GeomAPI_ProjectPointOnSurf(q, pr.gplane).NearestPoint()
        q.Transform(pr.mov)
        pts.append(q)
    pm, pf, pl = pts
    f2 = GeomAPI_ProjectPointOnCurve(pf, curve).LowerDistanceParameter()
    l2 = GeomAPI_ProjectPointOnCurve(pl, curve).LowerDistanceParameter()
    m2 = GeomAPI_ProjectPointOnCurve(pm, curve).LowerDistanceParameter()
    first, last = f2, l2
    f2, l2 = adjust(curve, f2, l2)
    f2, m2 = adjust(curve, f2, m2)
    if m2 > l2:
        first, last = last, first
    return first, last


def oblique_circle(edge, pr) -> list[dict]:
    """processEdge's general case of a circle: its projection is an ellipse (or an arc of one) whose major radius is the
    circle's and minor its radius times the cosine of the planes' angle, the major axis along the planes' crossing."""
    curve = BRepAdaptor_Curve(edge)
    circ = curve.Circle()
    vec1 = pr.plane.Axis().Direction()
    vec2 = circ.Axis().Direction()
    cnt = GeomAPI_ProjectPointOnSurf(circ.Location(), pr.gplane).NearestPoint()
    p = pr.local(cnt)
    major = vec1.Crossed(vec2)                          # gp_Dir ^ gp_Dir: normalized
    cos_t = abs(vec1.Dot(vec2))
    minor = circ.Radius() * cos_t
    m = pr.inv.rot.mult_vec((major.X(), major.Y(), major.Z()))
    ref = gp_Ax2(gp_Pnt(p[0], p[1], p[2]), gp_Dir(0, 0, 1), gp_Dir(gp_Vec(m[0], m[1], m[2])))
    el = gp_Elips()
    el.SetPosition(ref)
    el.SetMajorRadius(circ.Radius())
    el.SetMinorRadius(minor)
    proj = Geom_Ellipse(el)
    # isFullCircle: |last - first - 2 pi| below gp::Resolution() (DBL_MIN)
    if abs(curve.LastParameter() - curve.FirstParameter() - TWO_PI) < 2.2250738585072014e-308:
        return [conic_dict("Ellipse", proj)]
    first, last = _adjust_parameter_range(edge, pr, proj)
    return [conic_dict("ArcOfEllipse", proj, first, last)]


def _uv(v, pr):
    """ProjVecOnPlane_UV: a vector's coordinates along the sketch plane's X and Y directions."""
    pos = pr.plane.Position()
    return gp_Vec(v.Dot(gp_Vec(pos.XDirection())), v.Dot(gp_Vec(pos.YDirection())), 0.0)


def _point_uv(p, pr):
    return _uv(gp_Vec(pr.plane.Location(), p), pr)


def ellipse(edge, pr) -> list[dict]:
    """processEdge's GeomAbs_Ellipse branch: the projected ellipse's axes found from the original's (the general
    construction), a circle when they come out equal, a line when the ellipse is edge-on."""
    curve = BRepAdaptor_Curve(edge)
    p1, p2 = curve.Value(curve.FirstParameter()), curve.Value(curve.LastParameter())
    orig = curve.Ellipse()
    dest_c = _point_uv(orig.Location(), pr)
    dest_center = gp_Pnt(dest_c.X(), dest_c.Y(), 0.0)
    amaj = gp_Vec(orig.XAxis().Direction()).Multiplied(orig.MajorRadius())
    amin = gp_Vec(orig.YAxis().Direction()).Multiplied(orig.MinorRadius())
    pa, pb = _uv(amaj, pr), _uv(amin, pr)
    t_max = 0.0
    d = pa.SquareMagnitude() - pb.SquareMagnitude()
    if abs(d) > 2.220446049250313e-16:
        t_max = 0.5 * math.atan(2.0 * pa.Dot(pb) / d)
    t_min = t_max + 0.5 * math.pi
    on_max = amaj.Multiplied(math.cos(t_max)).Added(amin.Multiplied(math.sin(t_max)))
    on_min = amaj.Multiplied(math.cos(t_min)).Added(amin.Multiplied(math.sin(t_min)))
    dmaj, dmin = _uv(on_max, pr), _uv(on_min, pr)
    R, r = dmaj.Magnitude(), dmin.Magnitude()
    if R < r:
        R, r, dmaj, dmin = r, R, dmin, dmaj
    sens = pr.ax3.Direction().Dot(orig.Position().Direction())
    flip = 1.0 if sens > 0.0 else -1.0
    ax2 = gp_Ax2(dest_center, gp_Dir(0, 0, flip), gp_Dir(dmaj))
    if R - r < CONFUSION:
        c = Geom_Circle(ax2, 0.5 * (r + R))
        if p1.SquareDistance(p2) < CONFUSION:
            return [{"type": "Circle", "center": _xy(c.Location()), "radius": c.Radius(), "construction": True}]
        first, last = _adjust_parameter_range(edge, pr, c)
        return [circle_dict(c, first, last)]
    if pr.plane.Position().Direction().IsNormal(orig.Position().Direction(), ANGULAR):
        s = gp_Vec(dest_center.XYZ()).Added(dmaj)
        e = gp_Vec(dest_center.XYZ()).Subtracted(dmaj)
        return [{"type": "LineSegment", "start": [s.X(), s.Y()], "end": [e.X(), e.Y()], "construction": True}]
    el = gp_Elips()
    el.SetPosition(ax2)
    el.SetMajorRadius(dmaj.Magnitude())
    el.SetMinorRadius(dmin.Magnitude())
    proj = Geom_Ellipse(el)
    if p1.SquareDistance(p2) < CONFUSION:
        return [conic_dict("Ellipse", proj)]
    first, last = _adjust_parameter_range(edge, pr, proj)
    return [conic_dict("ArcOfEllipse", proj, first, last)]


def _find_plane(edge):
    """TopoShape::findPlane of one edge: BRepLib_FindSurface on a copy, planes only (None when it is not planar)."""
    finder = BRepLib_FindSurface(BRepBuilderAPI_Copy(edge).Shape(), CONFUSION, True)
    if not finder.Found():
        return None
    return GeomAdaptor_Surface(finder.Surface()).Plane()


def _to_local(shape, pr):
    """TopoShape::transformShape(invPlm) of a copy: into the sketch's coordinates."""
    return BRepBuilderAPI_Transform(shape, pr.mov, True).Shape()


def other(edge, pr) -> list[dict]:
    """processEdge's last branch: a line when the edge's plane is edge-on to the sketch (from its optimal bounding box),
    the edge itself moved onto the sketch when its plane is parallel, else its normal projection."""
    curve = BRepAdaptor_Curve(edge)
    plane = _find_plane(edge)
    sk_plane = pr.plane
    if plane is not None and plane.Axis().IsNormal(sk_plane.Axis(), ANGULAR):
        shape = _to_local(edge, pr)
        angle = plane.Axis().Direction().Angle(sk_plane.Position().YDirection())
        trsf = gp_Trsf()
        if abs(angle) > ANGULAR:
            trsf.SetRotation(gp_Ax1(gp_Pnt(), gp_Dir(0, 0, 1)), angle)
            shape = BRepBuilderAPI_Transform(shape, trsf, True).Shape()
        shape = BRepBuilderAPI_Copy(shape).Shape()
        box = Bnd_Box()
        BRepBndLib.AddOptimal_s(shape, box, False, False)
        box.SetGap(0.0)
        if box.IsVoid():
            raise FeatureError("Invalid bounding box")
        lo, hi = box.CornerMin(), box.CornerMax()
        xmin, ymin, xmax, ymax = lo.X(), lo.Y(), hi.X(), hi.Y()
        q1, q2 = gp_Pnt(xmin, ymin, 0), gp_Pnt(xmax, ymax, 0)
        if abs(angle) > ANGULAR:
            trsf.SetRotation(gp_Ax1(gp_Pnt(), gp_Dir(0, 0, 1)), -angle)
            q1.Transform(trsf)
            q2.Transform(trsf)
        y = (q1.Y() + q2.Y()) / 2.0
        if q1.SquareDistance(q2) < CONFUSION * CONFUSION:
            return [{"type": "Point", "at": [(q1.X() + q2.X()) / 2, y], "construction": True}]
        return [{"type": "LineSegment", "start": [q1.X(), y], "end": [q2.X(), y], "construction": True}]
    if plane is not None and plane.Axis().Direction().IsParallel(sk_plane.Axis().Direction(), CONFUSION):
        proj = edge
        if curve.GetType() == GeomAbs_BSplineCurve:
            a, b = curve.FirstParameter(), curve.LastParameter()
            if a > b:
                a, b = b, a
            bs = curve.BSpline()
            if b - a > CONFUSION:
                bs.Segment(a, b)
                proj = BRepBuilderAPI_MakeEdge(bs).Edge()
        ap, aloc, adir = sk_plane.Location(), plane.Location(), plane.Axis().Direction()
        d = adir.X() * (ap.X() - aloc.X()) + adir.Y() * (ap.Y() - aloc.Y()) + adir.Z() * (ap.Z() - aloc.Z())
        trsf = gp_Trsf()
        trsf.SetTranslation(gp_Vec(adir).Multiplied(d))
        proj = BRepBuilderAPI_Transform(proj, trsf, False).Shape()
    else:
        face = BRepBuilderAPI_MakeFace(sk_plane).Face()
        mk = BRepOffsetAPI_NormalProjection(face)
        mk.Add(edge)
        mk.Build()
        proj = mk.Projection()
    out = []
    if proj is None or proj.IsNull():
        return out
    ex = TopExp_Explorer(proj, TopAbs_EDGE)
    while ex.More():
        out += process_edge2(TopoDS.Edge(_to_local(ex.Current(), pr)))
        ex.Next()
    return out

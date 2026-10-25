"""The OpenCascade side of the Sketcher's curve tools: what FreeCAD's Part::Geom* classes compute with OCCT for
SketchObject's operations, for the page's port of those operations (ui/src/sketchkernel.ts) to ask for.

    cad feature sketchkernel SLUG --req '[{"op": "nurbs", "geo": {...}}, ...]'     (or --req @file.json)

The page keeps SketchObject's own logic (which pieces a trim leaves, which constraints follow them, the internal
geometry) in TypeScript; the numbers OCCT makes it here, by the same calls on the same OCCT (8.0.1, as FreeCAD
26.3 at 3160daf1e2b6 is built with), so a B-spline the page gets is FreeCAD's to the bit. Each request is a dict
with an "op" and the curves as the solver's JSON (cad_agent/feature_curves.py's vocabulary); each answer a dict,
{"error": message} when OCCT (or FreeCAD's check before it) refuses. The ops, after Mod/Part/App/Geometry.cpp,
Part2DObject.cpp and Mod/Sketcher/App/SketchObjectOperations.cpp:

    nurbs {geo}                          GeomCurve::toNurbs(first, last) as SketchObject::convertToNURBS calls it
    degree {geo, degree}                 GeomBSplineCurve::increaseDegree (Geom_BSplineCurve::IncreaseDegree)
    approximate {geo, degree}            GeomBSplineCurve::approximate(Confusion, 20, degree, C0) (decreaseBSplineDegree)
    multiplicity {geo, index, mult}      increaseMultiplicity, or removeKnot(index, mult, 1E6) when it goes down
    insert_knot {geo, u, mult}           GeomBSplineCurve::insertKnot
    trim {geo, u, v}                     GeomBSplineCurve::Trim (createArc of a B-spline)
    closest {geo, p}                     GeomCurve::closestParameter
    seek {geometry, id, p, axes}         Part2DObject::seekTrimPoints on the sketch's curves (+ the axes)
    fillet {geo1, geo2, ref1, ref2, radius}   createFilletGeometry for two bounded curves (not two lines)
    join {geo1, pos1, geo2, pos2, continuity} the new B-spline of SketchObject::join
    interpolate {points, periodic}       Part.BSplineCurve().interpolate(points, PeriodicFlag) then increaseDegree(3)
    offset {...}                         see cad_agent/sketch_offset.py

Copyright of the FreeCAD sources ported here: Geometry.cpp 2008 Werner Mayer, Part2DObject.cpp 2008 Jürgen
Riegel, SketchObjectOperations.cpp 2008 Jürgen Riegel (LGPL-2.0-or-later).
"""
from __future__ import annotations

import json
import math

from .cmdbase import OK, Result, UsageError

try:
    from OCP.Approx import Approx_Curve3d
    from OCP.BSplCLib import BSplCLib
    from OCP.GC import GC_MakeSegment
    from OCP.Geom import Geom_BSplineCurve, Geom_Circle, Geom_Line, Geom_OffsetCurve, Geom_TrimmedCurve
    from OCP.Geom2dAPI import Geom2dAPI_InterCurveCurve, Geom2dAPI_ProjectPointOnCurve
    from OCP.GeomAbs import GeomAbs_C0
    from OCP.GeomAdaptor import GeomAdaptor_Curve
    from OCP.GeomAPI import GeomAPI, GeomAPI_ExtremaCurveCurve, GeomAPI_Interpolate, GeomAPI_ProjectPointOnCurve
    from OCP.GeomConvert import GeomConvert
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pln, gp_Pnt, gp_Pnt2d, gp_Vec
    from OCP.ShapeConstruct import ShapeConstruct_Curve
    try:
        from OCP.TColgp import TColgp_Array1OfPnt, TColgp_HArray1OfPnt
        from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal
    except ImportError:                 # OCP 8 moved OCCT's collections
        from OCP.collections import Array1_double as TColStd_Array1OfReal
        from OCP.collections import Array1_gp_Pnt as TColgp_Array1OfPnt
        from OCP.collections import Array1_int as TColStd_Array1OfInteger
        from OCP.collections import HArray1_gp_Pnt as TColgp_HArray1OfPnt
except ImportError:                     # pragma: no cover - only FreeCAD's Python lands here
    pass

CONFUSION = 1e-7                        # Precision::Confusion()
APPROXIMATION = 1e-6                    # Precision::Approximation()
PI = math.pi


class KernelError(Exception):
    """OCCT (or FreeCAD's check before calling it) refused: the message FreeCAD reports."""


# ── the curves as Part::Geometry holds them ───────────────────────────────────────────────────────────────────

def geom(d: dict):
    """The Geom_Curve of Part::Geometry::handle() for a geometry dict: GeomLineSegment's Geom_TrimmedCurve of a
    Geom_Line (GC_MakeSegment), Geom_Circle on gp_Ax2(center, +Z), GeomArcOfCircle's Geom_TrimmedCurve (sense
    true), the conics and B-splines as cad_agent/feature_curves.py builds them. None for a point."""
    t = d["type"]
    if t == "Point":
        return None
    if t == "LineSegment":
        return GC_MakeSegment(gp_Pnt(*d["start"], 0), gp_Pnt(*d["end"], 0)).Value()
    if t in ("Circle", "ArcOfCircle"):
        c = Geom_Circle(gp_Ax2(gp_Pnt(*d["center"], 0), gp_Dir(0, 0, 1)), d["radius"])
        return c if t == "Circle" else Geom_TrimmedCurve(c, d["start_angle"], d["end_angle"], True)
    from . import feature_curves as FC
    return FC.curve(FC.from_dict(d))


def _xy(p) -> list[float]:
    return [p.X(), p.Y()]


def bspline_dict(c, construction: bool = False) -> dict:
    """A Geom_BSplineCurve as the solver's JSON (Part.BSplineCurve's poles, weights, knots, mults, degree)."""
    n, k = c.NbPoles(), c.NbKnots()
    out = {"type": "BSplineCurve", "poles": [_xy(c.Pole(i)) for i in range(1, n + 1)],
           "weights": [c.Weight(i) for i in range(1, n + 1)], "knots": [c.Knot(i) for i in range(1, k + 1)],
           "mults": [c.Multiplicity(i) for i in range(1, k + 1)], "degree": c.Degree(), "periodic": c.IsPeriodic()}
    if construction:
        out["construction"] = True
    return out


def _bspline(d: dict):
    c = geom(d)
    if not isinstance(c, Geom_BSplineCurve):
        raise KernelError("The Geometry Index (GeoId) provided is not a B-spline.")
    return c


def _copy(c):
    return c.Copy()


# ── GeomCurve::toNurbs (convertToNURBS) ───────────────────────────────────────────────────────────────────────

def _range(c):
    return c.FirstParameter(), c.LastParameter()


def _to_bspline(c, first, last):
    """GeomCurve::toBSpline: ShapeConstruct_Curve::ConvertToBSpline."""
    s = ShapeConstruct_Curve().ConvertToBSpline(c, first, last, CONFUSION)
    if s is None:
        raise KernelError("Conversion to B-spline failed")
    return s


def _conic_to_nurbs(conic, first, last):
    """GeomConic::toNurbs: GeomConvert::CurveToBSplineCurve of the trimmed conic, its knots stretched back onto
    [first, last] when the conversion moved them."""
    curve = Geom_TrimmedCurve(conic, first, last)
    b = GeomConvert.CurveToBSplineCurve_s(curve)
    fnew, lnew = b.FirstParameter(), b.LastParameter()
    if not b.IsPeriodic():
        utol = b.Resolution(CONFUSION)[0]    # Resolution(Precision::Confusion(), UTol)
        if abs(first - fnew) > utol or abs(last - lnew) > utol:
            n = b.NbKnots()
            knots = TColStd_Array1OfReal(1, n)
            b.Knots(knots)
            BSplCLib.Reparametrize_s(first, last, knots)
            b.SetKnots(knots)
    return b


def _full_conic(c, a, b, knots):
    """GeomCircle::toNurbs and GeomEllipse::toNurbs for the whole curve: seven poles, weights 3 at the ends of
    the two halves, knots 0, k, 2k with multiplicities 4, 3, 4."""
    pts = [(a, 0), (a, 2 * b), (-a, 2 * b), (-a, 0), (-a, -2 * b), (a, -2 * b), (a, 0)]
    from OCP.gp import gp_Ax3, gp_Trsf
    trsf = gp_Trsf()
    trsf.SetTransformation(gp_Ax3(c.Position()), gp_Ax3())
    poles, weights = TColgp_Array1OfPnt(1, 7), TColStd_Array1OfReal(1, 7)
    for i, (x, y) in enumerate(pts):
        p = gp_Pnt(x, y, 0)
        p.Transform(trsf)
        poles.SetValue(i + 1, p)
        weights.SetValue(i + 1, 3.0 if i in (0, 3, 6) else 1.0)
    m, k = TColStd_Array1OfInteger(1, 3), TColStd_Array1OfReal(1, 3)
    for i, (mm, kk) in enumerate(zip((4, 3, 4), knots)):
        m.SetValue(i + 1, mm)
        k.SetValue(i + 1, kk)
    return Geom_BSplineCurve(poles, weights, k, m, 3, False, True)


def to_nurbs(d: dict):
    """The B-spline SketchObject::convertToNURBS puts in place of a curve (GeomCurve::toNurbs(first, last) of
    each Part class; an arc of conic is never reversed in a sketch, its normal being +Z)."""
    t = d["type"]
    c = geom(d)
    if c is None:
        raise KernelError("A point cannot be converted to a B-spline")
    first, last = _range(c)
    if t == "Circle":
        if first != 0 or last != 2 * PI:
            return _conic_to_nurbs(c, first, last)
        return _full_conic(c, c.Radius(), c.Radius(), (0.0, PI, 2 * PI))
    if t == "ArcOfCircle":
        basis = c.BasisCurve()
        if first != 0 or last != 2 * PI:
            return _conic_to_nurbs(basis, first, last)
        return _full_conic(basis, basis.Radius(), basis.Radius(), (0.0, PI, 2 * PI))
    if t in ("Ellipse", "ArcOfEllipse"):
        basis = c if t == "Ellipse" else c.BasisCurve()
        if first != 0 or last != 2 * PI:
            return _conic_to_nurbs(basis, first, last)
        return _full_conic(basis, basis.MajorRadius(), basis.MinorRadius(), (0.0, 1.0, 2.0))
    if t == "ArcOfHyperbola":
        return _conic_to_nurbs(c.BasisCurve(), first, last)
    if t == "ArcOfParabola":       # GeomParabola::toNurbs: the default, on the basis parabola
        return _to_bspline(c.BasisCurve(), first, last)
    return _to_bspline(c, first, last)      # a line segment, a B-spline: GeomCurve::toNurbs


# ── the B-spline tools ─────────────────────────────────────────────────────────────────────────────────────────

def increase_degree(d: dict, degree: int):
    c = _copy(_bspline(d))
    c.IncreaseDegree(degree)
    return c


def approximate(d: dict, degree: int):
    """GeomBSplineCurve::approximate(Precision::Confusion(), 20, degree, GeomAbs_C0)."""
    c = _bspline(d)
    approx = Approx_Curve3d(GeomAdaptor_Curve(c), CONFUSION, GeomAbs_C0, 20, degree)
    if approx.IsDone():
        return approx.Curve()
    if approx.HasResult():
        raise KernelError("Approximation of B-Spline succeeded but is outside of tolerance")
    raise KernelError("Approximation of B-Spline failed")


def multiplicity(d: dict, index: int, mult: int):
    """modifyBSplineKnotMultiplicity's OCCT part: the knot (OCC's index, from 1) to multiplicity mult."""
    c = _copy(_bspline(d))
    if mult > c.Multiplicity(index):
        c.IncreaseMultiplicity(index, mult)
        return c
    # GeomBSplineCurve::removeKnot(index, mult, 1E6)
    if not c.RemoveKnot(index, mult, 1e6) or any(c.Weight(i) <= 1e-290 for i in range(1, c.NbPoles() + 1)):
        raise KernelError("OCC is unable to decrease the multiplicity within the maximum tolerance.")
    return c


def insert_knot(d: dict, u: float, mult: int):
    c = _copy(_bspline(d))
    c.InsertKnot(u, mult)
    return c


def trim(d: dict, u: float, v: float):
    """GeomBSplineCurve::Trim(u, v): GeomConvert::SplitBSplineCurve, a periodic one taking a lap more when v < u."""
    c = _bspline(d)
    if c.IsPeriodic() and v < u:
        v = v + (c.LastParameter() - c.FirstParameter())
    return GeomConvert.SplitBSplineCurve_s(c, u, v, CONFUSION)


def closest(d: dict, p) -> float:
    """GeomCurve::closestParameter: GeomAPI_ProjectPointOnCurve's nearest; when it finds none, the nearer end of a
    bounded curve."""
    c = geom(d)
    pnt = gp_Pnt(p[0], p[1], 0)
    ppc = GeomAPI_ProjectPointOnCurve(pnt, c)
    if ppc.NbPoints() > 0:
        return ppc.LowerDistanceParameter()
    if d["type"] in ("Circle", "Ellipse"):
        raise KernelError("closestParameter: no projection")
    f, l = _range(c)
    return f if c.Value(f).Distance(pnt) < c.Value(l).Distance(pnt) else l


# ── Part2DObject::seekTrimPoints ───────────────────────────────────────────────────────────────────────────────

BOUNDED = ("LineSegment", "ArcOfCircle", "ArcOfEllipse", "ArcOfHyperbola", "ArcOfParabola", "BSplineCurve")


def seek(geometry: list[dict], geo_id: int, point, axes: bool = False) -> dict | None:
    """The cut points either side of the picked point on curve geo_id and the indices of the curves cutting it
    there (-1 for none; with axes, len(geometry) and len(geometry) + 1 are the H and V axes, as infinite lines),
    or None when nothing cuts it."""
    plane = gp_Pln(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1))
    curves = [geom(g) for g in geometry]
    if axes:
        curves += [Geom_Line(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0)), Geom_Line(gp_Pnt(0, 0, 0), gp_Dir(0, 1, 0))]
    bounded = [g["type"] in BOUNDED for g in geometry] + ([False, False] if axes else [])
    if curves[geo_id] is None:
        return None
    primary = GeomAPI.To2d_s(curves[geo_id], plane)
    periodic = primary.IsPeriodic()
    period = primary.Period() if periodic else 0.0
    projector = Geom2dAPI_ProjectPointOnCurve(gp_Pnt2d(point[0], point[1]), primary)
    picked = projector.LowerDistanceParameter()
    i1 = i2 = -1
    param1, param2 = -1e10, 1e10
    p1 = p2 = None
    for i, c3 in enumerate(curves):
        if i == geo_id or c3 is None:
            continue
        secondary = GeomAPI.To2d_s(c3, plane)
        pts = []
        if bounded[i]:                 # #2463: the ends of a bounded secondary curve
            s, e = c3.Value(c3.FirstParameter()), c3.Value(c3.LastParameter())
            pts += [gp_Pnt2d(s.X(), s.Y()), gp_Pnt2d(e.X(), e.Y())]
        inter = Geom2dAPI_InterCurveCurve(primary, secondary, 1.0e-12)
        pts += [inter.Point(k) for k in range(1, inter.NbPoints() + 1)]
        if inter.NbSegments() > 0:
            g = inter.Intersector()
            for k in range(1, g.NbSegments() + 1):
                seg = g.Segment(k)
                if seg.HasFirstPoint():
                    pts.append(seg.FirstPoint().Value())
                if seg.HasLastPoint():
                    pts.append(seg.LastPoint().Value())
        for p in pts:
            projector.Init(p, primary)
            if projector.NbPoints() < 1 or projector.LowerDistance() > CONFUSION:
                continue
            param = projector.LowerDistanceParameter()
            if periodic:
                param = param - period * math.ceil((param - picked) / period)
                if param > param1:
                    param1, p1, i1 = param, p, i
                param -= period
                if param < param2:
                    param2, p2, i2 = param, p, i
            elif picked > param > param1:
                param1, p1, i1 = param, p, i
            elif picked < param < param2:
                param2, p2, i2 = param, p, i
    if periodic and abs(param2 - param1 - period) < 1e-10:
        if param2 - picked >= picked - param1:
            i2 = -1
        else:
            i1 = -1
    if i1 < 0 and i2 < 0:
        return None
    return {"ids": [i1, i2], "points": [[p1.X(), p1.Y()] if i1 >= 0 else [0.0, 0.0],
                                        [p2.X(), p2.Y()] if i2 >= 0 else [0.0, 0.0]]}


# ── createFilletGeometry for two bounded curves (Geometry.cpp) ────────────────────────────────────────────────

def _intersect(c1, c2, tol=CONFUSION):
    """GeomCurve::intersect: the bounded curves' touching ends, then GeomAPI_ExtremaCurveCurve's extrema within
    tol, as (point on c1, point on c2) pairs."""
    from OCP.Geom import Geom_BoundedCurve
    points = []
    if isinstance(c1, Geom_BoundedCurve) and isinstance(c2, Geom_BoundedCurve):
        b1, b2 = c1, c2
        for p, q in ((b1.StartPoint(), b2.StartPoint()), (b1.StartPoint(), b2.EndPoint()),
                     (b1.EndPoint(), b2.StartPoint()), (b1.EndPoint(), b2.EndPoint())):
            if p.Distance(q) < tol:
                points.append((p, q))
    try:
        ex = GeomAPI_ExtremaCurveCurve(c1, c2)
        if ex.NbExtrema() == 0 or ex.LowerDistance() > tol:
            return []
        for k in range(1, ex.NbExtrema() + 1):
            if ex.Distance(k) > tol:
                continue
            p, q = gp_Pnt(), gp_Pnt()
            ex.Points(k, p, q)
            points.append((p, q))
    except Exception as e:  # noqa: BLE001 - Standard_Failure: keep what the ends gave
        if not points:
            raise KernelError(str(e)) from None
    return points


def _closest_c(c, p):
    ppc = GeomAPI_ProjectPointOnCurve(p, c)
    if ppc.NbPoints() > 0:
        return ppc.LowerDistanceParameter()
    f, l = _range(c)
    return f if c.Value(f).Distance(p) < c.Value(l).Distance(p) else l


def _v(p):
    return (p.X(), p.Y(), p.Z())


def fillet(geo1: dict, geo2: dict, ref1, ref2, radius: float) -> dict | None:
    """createFilletGeometry's branch for two GeomBoundedCurves (not two lines): the fillet arc, the ends of the
    curves it replaces (pos1, pos2: 1 start, 2 end), reverse, and the corner point; None when it cannot be made."""
    c1, c2 = geom(geo1), geom(geo2)
    r1, r2 = gp_Pnt(ref1[0], ref1[1], 0), gp_Pnt(ref2[0], ref2[1], 0)
    dist_refs = lambda a, b: a.Distance(r1) + b.Distance(r2)     # noqa: E731

    def select(points):
        if not points:
            return None
        best, si = dist_refs(*points[0]), 0
        for i, (a, b) in enumerate(points):
            d = dist_refs(a, b)
            if d < best:
                si, best = i, d
        return points[si]

    refparam1 = _closest_c(c1, r1)
    refparam2 = _closest_c(c2, r2)
    pos1 = pos2 = 0
    inter = None
    dist = math.inf
    s1, e1, s2, e2 = c1.StartPoint(), c1.EndPoint(), c2.StartPoint(), c2.EndPoint()
    for a, b, q1, q2 in ((s1, s2, 1, 1), (e1, s2, 2, 1), (s1, e2, 1, 2), (e1, e2, 2, 2)):
        if a.Distance(b) < CONFUSION:      # the first of the four that touch (an else-if chain)
            d = dist_refs(a, b)
            if d < dist:
                dist, inter, pos1, pos2 = d, (a, b), q1, q2
            break
    if dist == math.inf:
        # no touching ends: the basis curves' intersection, for two GeomTrimmedCurves (a line segment is one; a
        # B-spline is not)
        if geo1["type"] == "BSplineCurve" or geo2["type"] == "BSplineCurve":
            return None
        try:
            pts = _intersect(c1.BasisCurve(), c2.BasisCurve())
        except KernelError:
            raise KernelError("Unable to guess intersection of curves. Try adding a coincident constraint between "
                              "the vertices of the curves you are intending to fillet.") from None
        inter = select(pts)
        if inter is None:
            return None
    corner = inter[0]
    intparam1, intparam2 = _closest_c(c1, inter[0]), _closest_c(c2, inter[1])
    spc1, spc2 = c1.FirstParameter(), c2.FirstParameter()
    ref21 = gp_Vec(r1, r2)
    if radius == 0.0:
        try:
            t1, t2 = gp_Vec(), gp_Vec()
            p = gp_Pnt()
            c1.D1(refparam1, p, t1)
            c2.D1(refparam2, p, t2)
            if t1.Magnitude() <= 1e-12 or t2.Magnitude() <= 1e-12:
                return None
            t1.Normalize()
            t2.Normalize()
            d1, d2 = (t1.Y(), -t1.X()), (t2.Y(), -t2.X())
            det = -d1[0] * d2[1] + d2[0] * d1[1]
            if abs(det) < CONFUSION:
                raise ValueError("No intersection of normals")
            q1, q2 = c1.Value(refparam1), c2.Value(refparam2)
            nx = (-d1[0] * d2[0] * q1.Y() + d1[0] * d2[0] * q2.Y() - d1[0] * d2[1] * q2.X()
                  + d2[0] * d1[1] * q1.X()) / det
            ny = (-d1[0] * d2[1] * q1.Y() + d2[0] * d1[1] * q2.Y() + d1[1] * d2[1] * q1.X()
                  - d1[1] * d2[1] * q2.X()) / det
            ni = gp_Pnt(nx, ny, 0)
            radius = (q1.Distance(ni) + q2.Distance(ni)) / 2
        except ValueError:
            radius = ref21.Magnitude()
    t1, t2, p = gp_Vec(), gp_Vec(), gp_Pnt()
    c1.D1(refparam1, p, t1)
    c2.D1(refparam2, p, t2)
    vn = gp_Vec(0, 0, 1)
    sdir1 = t1.Crossed(ref21).Dot(vn)
    sdir2 = t2.Crossed(ref21.Reversed()).Dot(vn)
    o1 = Geom_OffsetCurve(c1, radius if sdir1 < 0 else -radius, gp_Dir(0, 0, 1))
    o2 = Geom_OffsetCurve(c2, radius if sdir2 < 0 else -radius, gp_Dir(0, 0, 1))
    try:
        centre = select(_intersect(o1, o2))
    except KernelError:
        raise KernelError("Unable to find intersection between offset curves.") from None
    if centre is None:
        return None
    refoparam1, refoparam2 = _closest_c(c1, centre[0]), _closest_c(c2, centre[1])
    q1, q2 = c1.Value(refoparam1), c2.Value(refoparam2)
    cf = centre[0]
    rd1 = (q1.X() - cf.X(), q1.Y() - cf.Y(), q1.Z() - cf.Z())
    rd2 = (q2.X() - cf.X(), q2.Y() - cf.Y(), q2.Z() - cf.Z())
    start = math.atan2(rd1[1], rd1[0])
    rng = math.atan2(-rd1[1] * rd2[0] + rd1[0] * rd2[1], rd1[0] * rd2[0] + rd1[1] * rd2[1])
    if math.fmod(abs(rng), 2 * PI) < APPROXIMATION:
        return None
    end = start + rng
    if end < start:
        start, end = end, start
    if end > 2 * PI:
        end -= 2 * PI
    if start < 0:
        end += 2 * PI
    r = math.sqrt(rd1[0] ** 2 + rd1[1] ** 2 + rd1[2] ** 2)
    # GeomArcOfCircle: setRadius, setCenter, setRange(start, end, emulateCCWXY) (SetTrim on the circle)
    circle = Geom_Circle(gp_Ax2(gp_Pnt(cf.X(), cf.Y(), cf.Z()), gp_Dir(0, 0, 1)), r)
    arc = Geom_TrimmedCurve(circle, start, end, True)

    def select_end(intparam, refparam, startparam):
        return 1 if (intparam > refparam and startparam >= refparam) or (intparam < refparam and startparam <= refparam) else 2

    if pos1 == 0:
        pos1 = select_end(intparam1, refoparam1, spc1)
        pos2 = select_end(intparam2, refoparam2, spc2)
    a1, a2 = arc.StartPoint(), arc.EndPoint()
    reverse = q1.Distance(a1) < q1.Distance(a2)
    return {"arc": {"type": "ArcOfCircle", "center": [cf.X(), cf.Y()], "radius": r,
                    "start_angle": arc.FirstParameter(), "end_angle": arc.LastParameter()},
            "pos1": pos1, "pos2": pos2, "reverse": reverse, "corner": [corner.X(), corner.Y()]}


# ── SketchObject::join's new B-spline ──────────────────────────────────────────────────────────────────────────

def join(geo1: dict, pos1: int, geo2: dict, pos2: int, continuity: int):
    """The B-spline SketchObject::join makes of two curves joined at (geo1, pos1) and (geo2, pos2)."""
    b1, b2 = to_nurbs(geo1), to_nurbs(geo2)
    if b1.IsPeriodic() or b2.IsPeriodic():
        raise KernelError("It is only possible to join non-periodic curves.")
    if pos1 == 1:
        b1.Reverse()
    if pos2 == 2:
        b2.Reverse()
    if b1.Degree() < b2.Degree():
        b1.IncreaseDegree(b2.Degree())
    elif b2.Degree() < b1.Degree():
        b2.IncreaseDegree(b1.Degree())
    c1 = continuity >= 1
    if c1:
        p, s1, s2 = gp_Pnt(), gp_Vec(), gp_Vec()
        b1.D1(b1.LastParameter(), p, s1)
        b2.D1(b2.FirstParameter(), p, s2)
        scale = s2.Magnitude() / s1.Magnitude()
        _scale_knots(b2, 0, scale * (b2.LastParameter() - b2.FirstParameter()))
    d1, d2 = bspline_dict(b1), bspline_dict(b2)
    poles = d1["poles"][:-1] if c1 else list(d1["poles"])
    poles += d2["poles"][1:]
    weights = d1["weights"][:-1] if c1 else list(d1["weights"])
    weights += d2["weights"][1:]
    offset = d1["knots"][-1] - d2["knots"][0]
    knots = list(d1["knots"]) + [k + offset for k in d2["knots"][1:]]
    mults = list(d1["mults"])
    if b1.Degree() < mults[-1]:
        mults[-1] = b1.Degree() - (1 if c1 else 0)
    mults += d2["mults"][1:]
    # Part::GeomBSplineCurve(poles, weights, knots, mults, degree, periodic=false, checkRational=true)
    n = len(poles)
    P, W = TColgp_Array1OfPnt(1, n), TColStd_Array1OfReal(1, n)
    for i, ((x, y), w) in enumerate(zip(poles, weights)):
        P.SetValue(i + 1, gp_Pnt(x, y, 0))
        W.SetValue(i + 1, w)
    K, M = TColStd_Array1OfReal(1, len(knots)), TColStd_Array1OfInteger(1, len(knots))
    for i, (k, m) in enumerate(zip(knots, mults)):
        K.SetValue(i + 1, k)
        M.SetValue(i + 1, m)
    return Geom_BSplineCurve(P, W, K, M, b1.Degree(), False, True)


def _scale_knots(c, u0, u1):
    """GeomBSplineCurve::scaleKnotsToBounds."""
    n = c.NbKnots()
    k = TColStd_Array1OfReal(1, n)
    c.Knots(k)
    if abs(u0 - k.First()) > CONFUSION or abs(u1 - k.Last()) > CONFUSION:
        BSplCLib.Reparametrize_s(u0, u1, k)
        c.SetKnots(k)


# ── B-spline by interpolation (DrawSketchHandlerBSpline, Knots method) ─────────────────────────────────────────

def interpolate(points, periodic: bool, degree: int | None = 3):
    """Part.BSplineCurve().interpolate(points, PeriodicFlag=periodic) (GeomAPI_Interpolate, tolerance
    Precision::Approximation()), then increaseDegree(degree) as the tool does (none for the preview)."""
    n = len(points)
    if n < 2:
        raise KernelError("not enough points given")
    pts = TColgp_HArray1OfPnt(1, n)
    for i, (x, y) in enumerate(points):
        pts.SetValue(i + 1, gp_Pnt(x, y, 0))
    gi = GeomAPI_Interpolate(pts, bool(periodic), APPROXIMATION)
    gi.Perform()
    if not gi.IsDone():
        raise KernelError("failed to interpolate points")
    c = gi.Curve()
    if degree is not None:
        c.IncreaseDegree(degree)
    return c


# ── the request seam ──────────────────────────────────────────────────────────────────────────────────────────

def run(req: dict) -> dict:
    """One request: its answer, {"error": message} when it is refused."""
    op = req.get("op")
    try:
        if op == "nurbs":
            return {"geo": bspline_dict(to_nurbs(req["geo"]))}
        if op == "degree":
            return {"geo": bspline_dict(increase_degree(req["geo"], int(req["degree"])))}
        if op == "approximate":
            return {"geo": bspline_dict(approximate(req["geo"], int(req["degree"])))}
        if op == "multiplicity":
            return {"geo": bspline_dict(multiplicity(req["geo"], int(req["index"]), int(req["mult"])))}
        if op == "insert_knot":
            return {"geo": bspline_dict(insert_knot(req["geo"], float(req["u"]), int(req["mult"])))}
        if op == "trim":
            return {"geo": bspline_dict(trim(req["geo"], float(req["u"]), float(req["v"])))}
        if op == "closest":
            return {"u": closest(req["geo"], req["p"])}
        if op == "seek":
            return {"seek": seek(req["geometry"], int(req["id"]), req["p"], bool(req.get("axes")))}
        if op == "fillet":
            return {"fillet": fillet(req["geo1"], req["geo2"], req["ref1"], req["ref2"], float(req["radius"]))}
        if op == "join":
            return {"geo": bspline_dict(join(req["geo1"], int(req["pos1"]), req["geo2"], int(req["pos2"]),
                                             int(req.get("continuity", 0))))}
        if op == "interpolate":
            return {"geo": bspline_dict(interpolate(req["points"], bool(req.get("periodic")), req.get("degree", 3)))}
        if op == "offset":
            from .sketch_offset import offset
            return offset(req)
        return {"error": f"unknown op {op!r}"}
    except KernelError as e:
        return {"error": str(e)}
    except Exception as e:  # noqa: BLE001 - Standard_Failure and its kin: FreeCAD reports the message
        return {"error": f"{type(e).__name__}: {e}"}


def run_all(reqs: list[dict]) -> list[dict]:
    return [run(r) for r in reqs]


def cmd_sketchkernel(a) -> Result:
    """OCCT's numbers for the Sketcher's curve tools (no project file is read or written)."""
    text = a.req
    if text.startswith("@"):
        with open(text[1:], encoding="utf-8") as f:
            text = f.read()
    try:
        reqs = json.loads(text)
    except ValueError as e:
        raise UsageError(f"--req: {e}") from None
    if isinstance(reqs, dict):
        reqs = [reqs]
    out = run_all(reqs)
    bad = sum(1 for r in out if "error" in r)
    return Result(OK, {"answers": out}, f"{len(out)} answer(s), {bad} refused", "sketch kernel")


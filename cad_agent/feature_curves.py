"""The Sketcher's conics and B-splines for cad_agent/feature.py: Part.Ellipse, Part.ArcOfEllipse,
Part.ArcOfHyperbola, Part.ArcOfParabola and Part.BSplineCurve, in a FEATURES list's vocabulary.

    Ellipse((cx, cy), major_radius, minor_radius, x_axis=(1.0, 0.0), construction=False)
    ArcOfEllipse((cx, cy), major_radius, minor_radius, start_angle, end_angle, x_axis=..., construction=...)
    ArcOfHyperbola((cx, cy), major_radius, minor_radius, start_angle, end_angle, x_axis=..., construction=...)
    ArcOfParabola((vx, vy), focal, start_angle, end_angle, x_axis=..., construction=...)
    BSplineCurve([(x, y), ...], mults, knots, periodic=False, degree=3, weights=None, construction=False)

x_axis is Part's XAxis: the major axis towards the first focus (a parabola's axis, towards its focus);
the centre of an ArcOfParabola is its vertex, Part's Location. start_angle and end_angle are the conic's
own trim parameters (FirstParameter and LastParameter, as Part.ArcOfEllipse(ellipse, u1, u2) takes them),
counter-clockwise about +Z as the Sketcher's arcs are: a point of the conic at u is OCCT's
center + A1(u) X + A2(u) Y with Y = Z x X, A1, A2 = (a cos u, b sin u) on an ellipse, (a cosh u, b sinh u)
on a hyperbola (its main branch) and (u^2 / 4f, u) on a parabola (gp_Elips, gp_Hypr, gp_Parab via
ElCLib). A BSplineCurve takes Part.BSplineCurve(poles, mults, knots, periodic, degree, weights)'s
arguments in that order; weights None is a non-rational curve (all 1).

The Sketcher's points (SketchObject::getPoint, Sketch.cpp addEllipse ... addBSpline): an Ellipse has
only its centre (3); a conic arc has its start (1), end (2) and centre or vertex (3); a B-spline has its
start (1) and end (2), the first and last pole when it is clamped and its value at the first knot when
it is periodic.

The internal geometry FreeCAD exposes for them (SketchObject::exposeInternalGeometry) is ordinary
construction geometry held by InternalAlignment constraints, written as Sketcher.Constraint takes them:
Constraint("InternalAlignment:EllipseMajorDiameter", line, ellipse), ("InternalAlignment:EllipseFocus1",
point, 1, ellipse), ("InternalAlignment:BSplineControlPoint", circle, 3, spline, index),
("InternalAlignment:BSplineKnotPoint", point, 1, spline, index), and Constraint("Weight", circle, w).
residual() checks them against the stored geometry as PlaneGCS defines them (GCS.cpp's
addConstraintInternalAlignment*, Constraints.cpp's ConstraintInternalAlignmentPoint2Ellipse and
Point2Hyperbola, Sketch.cpp's addInternalAlignment*), so a sketch whose stored geometry satisfies its
constraints builds without the solver.

The geometry classes import without OCP (FreeCAD's Python reads them); edge(), intersections() and the
B-spline projection need it.
"""
from __future__ import annotations

import math

from .feature import FeatureError, _Geometry, _xy

try:                                    # the kernel; FreeCAD's Python reads the vocabulary without it
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from OCP.Geom import (Geom_BSplineCurve, Geom_Ellipse, Geom_Hyperbola, Geom_Parabola,
                          Geom_TrimmedCurve)
    from OCP.Geom2dAPI import Geom2dAPI_InterCurveCurve
    from OCP.Geom2dAdaptor import Geom2dAdaptor_Curve
    from OCP.Geom2dInt import Geom2dInt_GInter
    from OCP.GeomAPI import GeomAPI, GeomAPI_ProjectPointOnCurve
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pln, gp_Pnt
    try:
        from OCP.TColgp import TColgp_Array1OfPnt
        from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal
    except ImportError:                 # OCP 8 moved OCCT's collections
        from OCP.collections import Array1_double as TColStd_Array1OfReal
        from OCP.collections import Array1_gp_Pnt as TColgp_Array1OfPnt
        from OCP.collections import Array1_int as TColStd_Array1OfInteger
except ImportError:                     # pragma: no cover - only FreeCAD's Python lands here
    pass


def _num(v):
    return repr(float(v))


def _unit(v, where):
    x, y = _xy(v, where)
    n = math.hypot(x, y)
    if n <= 1e-12:
        raise FeatureError(f"{where}: {v!r} is not a direction")
    return (x / n, y / n)


def _positive(v, where, zero_ok=False):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise FeatureError(f"{where}: {v!r} is not a number")
    v = float(v)
    if v < 0 or (v == 0 and not zero_ok):
        raise FeatureError(f"{where}: {v!r} must be {'0 or more' if zero_ok else 'more than 0'}")
    return v


def _angle(v, where):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise FeatureError(f"{where}: {v!r} is not an angle in radians")
    return float(v)


def _pt_src(p, num):
    return f"({num(p[0])}, {num(p[1])})"


# ── the conics ────────────────────────────────────────────────────────────────────────────────────────

class _Conic(_Geometry):
    """A conic in the sketch's plane, about +Z: center, x_axis (Part's XAxis) and y_axis = Z x X."""

    def _axes(self, x_axis):
        self.x_axis = _unit(x_axis, f"{self.kind} x_axis")
        self.y_axis = (-self.x_axis[1], self.x_axis[0])

    def _off(self, a1, a2):
        """center + a1 X + a2 Y."""
        (cx, cy), (xx, xy), (yx, yy) = self.center, self.x_axis, self.y_axis
        return (cx + a1 * xx + a2 * yx, cy + a1 * xy + a2 * yy)

    def at(self, u):
        """The point at parameter u, as ElCLib computes it."""
        return self._off(*self._coords(u))

    def derivative(self, u):
        d1, d2 = self._dcoords(u)
        (xx, xy), (yx, yy) = self.x_axis, self.y_axis
        return (d1 * xx + d2 * yx, d1 * xy + d2 * yy)

    def local(self, p):
        """p in the conic's own frame: (along x_axis, along y_axis) from its centre."""
        dx, dy = p[0] - self.center[0], p[1] - self.center[1]
        return (dx * self.x_axis[0] + dy * self.x_axis[1], dx * self.y_axis[0] + dy * self.y_axis[1])

    def points(self):
        if not hasattr(self, "start_angle"):
            return {3: self.center}
        return {1: self.at(self.start_angle), 2: self.at(self.end_angle), 3: self.center}

    def _axis_dict(self):
        return {"x_axis": list(self.x_axis)}

    def _axis_src(self, num):
        return "" if self.x_axis == (1.0, 0.0) else f", x_axis={_pt_src(self.x_axis, num)}"


class _EllipseBase(_Conic):
    def _radii(self, a, b):
        self.major_radius = _positive(a, f"{self.kind} major_radius")
        self.minor_radius = _positive(b, f"{self.kind} minor_radius")
        if self.minor_radius > self.major_radius:
            # Part.Ellipse / Geom_Ellipse: the major radius is the larger
            raise FeatureError(f"{self.kind}: the major radius {self.major_radius!r} is smaller than the "
                               f"minor radius {self.minor_radius!r}")

    def _coords(self, u):
        return (self.major_radius * math.cos(u), self.minor_radius * math.sin(u))

    def _dcoords(self, u):
        return (-self.major_radius * math.sin(u), self.minor_radius * math.cos(u))

    def foci(self):
        c = math.sqrt(max(self.major_radius ** 2 - self.minor_radius ** 2, 0.0))
        return self._off(c, 0.0), self._off(-c, 0.0)

    def on_error(self, p):
        """ConstraintPointOnEllipse: |PF1| + |PF2| - 2a, a length."""
        f1, f2 = self.foci()
        return math.dist(p, f1) + math.dist(p, f2) - 2 * self.major_radius


class Ellipse(_EllipseBase):
    """Part.Ellipse(center, major_radius, minor_radius) with its XAxis set: the whole ellipse."""
    kind = "Ellipse"

    def __init__(self, center, major_radius, minor_radius, x_axis=(1.0, 0.0), construction: bool = False):
        self.center = _xy(center, "Ellipse center")
        self._radii(major_radius, minor_radius)
        self._axes(x_axis)
        self.construction = bool(construction)

    def as_dict(self):
        return {"type": self.kind, "center": list(self.center), "major_radius": self.major_radius,
                "minor_radius": self.minor_radius, **self._axis_dict(), "construction": self.construction}

    def source(self, num=_num):
        return (f"Ellipse({_pt_src(self.center, num)}, {num(self.major_radius)}, {num(self.minor_radius)}"
                f"{self._axis_src(num)}{', construction=True' if self.construction else ''})")


class ArcOfEllipse(_EllipseBase):
    """Part.ArcOfEllipse(ellipse, start_angle, end_angle): counter-clockwise, the ellipse's parameters."""
    kind = "ArcOfEllipse"

    def __init__(self, center, major_radius, minor_radius, start_angle, end_angle, x_axis=(1.0, 0.0),
                 construction: bool = False):
        self.center = _xy(center, "ArcOfEllipse center")
        self._radii(major_radius, minor_radius)
        self.start_angle = _angle(start_angle, "ArcOfEllipse start_angle")
        self.end_angle = _angle(end_angle, "ArcOfEllipse end_angle")
        self._axes(x_axis)
        self.construction = bool(construction)

    def as_dict(self):
        return {"type": self.kind, "center": list(self.center), "major_radius": self.major_radius,
                "minor_radius": self.minor_radius, **self._axis_dict(), "start_angle": self.start_angle,
                "end_angle": self.end_angle, "construction": self.construction}

    def source(self, num=_num):
        return (f"ArcOfEllipse({_pt_src(self.center, num)}, {num(self.major_radius)}, "
                f"{num(self.minor_radius)}, {num(self.start_angle)}, {num(self.end_angle)}"
                f"{self._axis_src(num)}{', construction=True' if self.construction else ''})")


class ArcOfHyperbola(_Conic):
    """Part.ArcOfHyperbola(hyperbola, start_angle, end_angle): the main branch, from u1 to u2."""
    kind = "ArcOfHyperbola"

    def __init__(self, center, major_radius, minor_radius, start_angle, end_angle, x_axis=(1.0, 0.0),
                 construction: bool = False):
        self.center = _xy(center, "ArcOfHyperbola center")
        self.major_radius = _positive(major_radius, "ArcOfHyperbola major_radius")
        self.minor_radius = _positive(minor_radius, "ArcOfHyperbola minor_radius")
        self.start_angle = _angle(start_angle, "ArcOfHyperbola start_angle")
        self.end_angle = _angle(end_angle, "ArcOfHyperbola end_angle")
        if self.start_angle == self.end_angle:
            raise FeatureError("ArcOfHyperbola: start_angle and end_angle are the same (Geom_TrimmedCurve: "
                               "U1 == U2)")
        self._axes(x_axis)
        self.construction = bool(construction)

    def _coords(self, u):
        return (self.major_radius * math.cosh(u), self.minor_radius * math.sinh(u))

    def _dcoords(self, u):
        return (self.major_radius * math.sinh(u), self.minor_radius * math.cosh(u))

    def focus(self):
        c = math.hypot(self.major_radius, self.minor_radius)
        return (self.center[0] + c * self.x_axis[0], self.center[1] + c * self.x_axis[1])

    def on_error(self, p):
        """ConstraintPointOnHyperbola: |PF2| - |PF1| - 2a, a length."""
        f1 = self.focus()
        f2 = (2 * self.center[0] - f1[0], 2 * self.center[1] - f1[1])
        return math.dist(p, f2) - math.dist(p, f1) - 2 * self.major_radius

    def as_dict(self):
        return {"type": self.kind, "center": list(self.center), "major_radius": self.major_radius,
                "minor_radius": self.minor_radius, **self._axis_dict(), "start_angle": self.start_angle,
                "end_angle": self.end_angle, "construction": self.construction}

    def source(self, num=_num):
        return (f"ArcOfHyperbola({_pt_src(self.center, num)}, {num(self.major_radius)}, "
                f"{num(self.minor_radius)}, {num(self.start_angle)}, {num(self.end_angle)}"
                f"{self._axis_src(num)}{', construction=True' if self.construction else ''})")


class ArcOfParabola(_Conic):
    """Part.ArcOfParabola(parabola, start_angle, end_angle); center is the vertex (Part's Location)."""
    kind = "ArcOfParabola"

    def __init__(self, center, focal, start_angle, end_angle, x_axis=(1.0, 0.0), construction: bool = False):
        self.center = _xy(center, "ArcOfParabola center")
        self.focal = _positive(focal, "ArcOfParabola focal")
        self.start_angle = _angle(start_angle, "ArcOfParabola start_angle")
        self.end_angle = _angle(end_angle, "ArcOfParabola end_angle")
        if self.start_angle == self.end_angle:
            raise FeatureError("ArcOfParabola: start_angle and end_angle are the same (Geom_TrimmedCurve: "
                               "U1 == U2)")
        self._axes(x_axis)
        self.construction = bool(construction)

    def _coords(self, u):
        return (u * u / (4 * self.focal), u)

    def _dcoords(self, u):
        return (u / (2 * self.focal), 1.0)

    def focus(self):
        return (self.center[0] + self.focal * self.x_axis[0], self.center[1] + self.focal * self.x_axis[1])

    def on_error(self, p):
        """ConstraintPointOnParabola: |PF| - 2f - (P - F).X, a length."""
        f = self.focus()
        return math.dist(p, f) - 2 * self.focal - ((p[0] - f[0]) * self.x_axis[0] + (p[1] - f[1]) * self.x_axis[1])

    def as_dict(self):
        return {"type": self.kind, "center": list(self.center), "focal": self.focal, **self._axis_dict(),
                "start_angle": self.start_angle, "end_angle": self.end_angle, "construction": self.construction}

    def source(self, num=_num):
        return (f"ArcOfParabola({_pt_src(self.center, num)}, {num(self.focal)}, {num(self.start_angle)}, "
                f"{num(self.end_angle)}{self._axis_src(num)}{', construction=True' if self.construction else ''})")


# ── the B-spline ──────────────────────────────────────────────────────────────────────────────────────

class BSplineCurve(_Geometry):
    """Part.BSplineCurve(poles, mults, knots, periodic, degree, weights), as Geom_BSplineCurve takes it."""
    kind = "BSplineCurve"

    def __init__(self, poles, mults, knots, periodic: bool = False, degree: int = 3, weights=None,
                 construction: bool = False):
        w = "BSplineCurve"
        if not isinstance(poles, (list, tuple)) or len(poles) < 2:
            raise FeatureError(f"{w}: poles {poles!r} is not a list of two or more points (x, y)")
        self.poles = [_xy(p, f"{w} pole") for p in poles]
        if isinstance(degree, bool) or not isinstance(degree, int) or degree < 1:
            raise FeatureError(f"{w}: degree {degree!r} is not a whole number 1 or more")
        self.degree, self.periodic = degree, bool(periodic)
        if not (isinstance(knots, (list, tuple)) and isinstance(mults, (list, tuple))
                and len(knots) == len(mults) >= 2):
            raise FeatureError(f"{w}: knots and mults must be lists of the same length, two or more")
        self.knots = [float(_angle(k, f"{w} knot")) for k in knots]
        self.mults = []
        for m in mults:
            if isinstance(m, bool) or not isinstance(m, int) or m < 1:
                raise FeatureError(f"{w}: multiplicity {m!r} is not a whole number 1 or more")
            self.mults.append(m)
        if any(b <= a for a, b in zip(self.knots, self.knots[1:])):
            raise FeatureError(f"{w}: the knots {self.knots!r} do not increase")
        n = len(self.poles)
        # Geom_BSplineCurve's checks (BSplCLib::NbPoles): "# Poles and degree mismatch"
        want = sum(self.mults[:-1]) if self.periodic else sum(self.mults) - degree - 1
        if want != n or (self.periodic and self.mults[0] != self.mults[-1]) \
                or any(m > degree for m in self.mults[1:-1]) or any(m > degree + 1 for m in self.mults) \
                or (self.periodic and self.mults[0] > degree):
            raise FeatureError(f"{w}: {n} poles, mults {self.mults} and degree {degree} do not make a "
                               f"{'periodic' if self.periodic else 'clamped'} B-spline (Geom_BSplineCurve: "
                               "# Poles and degree mismatch)")
        if weights is None:
            self.weights = [1.0] * n
        else:
            if not isinstance(weights, (list, tuple)) or len(weights) != n:
                raise FeatureError(f"{w}: weights {weights!r} is not one number per pole")
            self.weights = [_positive(x, f"{w} weight") for x in weights]
        self.construction = bool(construction)
        self._flat()

    def _flat(self):
        """The curve as a clamped-style de Boor problem: control points and flat knots, one domain.

        A periodic curve's flat knots repeat with the period T = last knot - first; OCCT ties pole k to
        the basis function that starts (degree + 1 - mults[0]) flat knots before the first knot, so the
        unrolled control points are the poles from the first, wrapping round (checked against
        Geom_BSplineCurve::D0)."""
        d, n = self.degree, len(self.poles)
        hom = [(x * w, y * w, w) for (x, y), w in zip(self.poles, self.weights)]
        if not self.periodic:
            self._t = [k for k, m in zip(self.knots, self.mults) for _ in range(m)]
            self._q = hom
            return
        core = [k for k, m in zip(self.knots[:-1], self.mults[:-1]) for _ in range(m)]
        period = self.knots[-1] - self.knots[0]
        m0 = self.mults[0]
        count = n + d - m0 + 1
        self._q = [hom[k % n] for k in range(count)]
        shift = m0 - 1 - d
        self._t = [core[(k + shift) % n] + period * ((k + shift) // n) for k in range(count + d + 1)]

    @property
    def first(self):
        return self.knots[0]

    @property
    def last(self):
        return self.knots[-1]

    def _deboor(self, u, q, t, d):
        i = d
        while i < len(q) - 1 and t[i + 1] <= u:
            i += 1
        pts = [list(q[j]) for j in range(i - d, i + 1)]
        for r in range(1, d + 1):
            for k in range(d, r - 1, -1):
                j = i - d + k
                den = t[j + d + 1 - r] - t[j]
                a = 0.0 if den == 0 else (u - t[j]) / den
                pts[k] = [(1 - a) * pts[k - 1][c] + a * pts[k][c] for c in range(3)]
        return pts[d]

    def _wrap(self, u):
        if self.periodic:
            period = self.last - self.first
            if not self.first <= u <= self.last:
                u = self.first + (u - self.first) % period
        return min(max(u, self.first), self.last)

    def value(self, u):
        """The point at parameter u (Geom_BSplineCurve::D0)."""
        x, y, w = self._deboor(self._wrap(u), self._q, self._t, self.degree)
        return (x / w, y / w)

    def derivative(self, u):
        """The first derivative at u (Geom_BSplineCurve::D1), from the end's side at the last knot."""
        u = self._wrap(u)
        d, t, q = self.degree, self._t, self._q
        if d == 0:
            return (0.0, 0.0)
        dq = []
        for j in range(len(q) - 1):
            den = t[j + d + 1] - t[j + 1]
            f = d / den if den else 0.0
            dq.append(tuple(f * (q[j + 1][c] - q[j][c]) for c in range(3)))
        A = self._deboor(u, q, t, d)
        dA = self._deboor(u, dq, t[1:-1], d - 1) if d > 1 else self._deboor(u, dq, t[1:-1], 0)
        x, y, w = A
        return ((dA[0] - dA[2] * x / w) / w, (dA[1] - dA[2] * y / w) / w)

    def points(self):
        return {1: self.value(self.first), 2: self.value(self.last)}

    def as_dict(self):
        return {"type": self.kind, "poles": [list(p) for p in self.poles], "weights": list(self.weights),
                "knots": list(self.knots), "mults": list(self.mults), "degree": self.degree,
                "periodic": self.periodic, "construction": self.construction}

    def source(self, num=_num):
        poles = "[" + ", ".join(_pt_src(p, num) for p in self.poles) + "]"
        knots = "[" + ", ".join(num(k) for k in self.knots) + "]"
        out = f"BSplineCurve({poles}, {list(self.mults)!r}, {knots}"
        if self.periodic:
            out += ", periodic=True"
        if self.degree != 3:
            out += f", degree={self.degree}"
        if any(w != 1.0 for w in self.weights):
            out += ", weights=[" + ", ".join(num(w) for w in self.weights) + "]"
        return out + (", construction=True" if self.construction else "") + ")"


CURVES = (Ellipse, ArcOfEllipse, ArcOfHyperbola, ArcOfParabola, BSplineCurve)
GEOMETRY = {g.kind: g for g in CURVES}

for _g in CURVES:                       # repr is the part file's own line, which reads back the same
    _g.__repr__ = lambda self: self.source()


def from_dict(d: dict):
    """geometry_from_dict for these kinds: the solver's JSON (start_point and end_point ignored)."""
    kind, c = d.get("type"), bool(d.get("construction", False))
    ax = d.get("x_axis", (1.0, 0.0))
    if kind == "Ellipse":
        return Ellipse(d["center"], d["major_radius"], d["minor_radius"], ax, c)
    if kind in ("ArcOfEllipse", "ArcOfHyperbola"):
        return GEOMETRY[kind](d["center"], d["major_radius"], d["minor_radius"], d["start_angle"],
                              d["end_angle"], ax, c)
    if kind == "ArcOfParabola":
        return ArcOfParabola(d["center"], d["focal"], d["start_angle"], d["end_angle"], ax, c)
    if kind == "BSplineCurve":
        return BSplineCurve(d["poles"], d["mults"], d["knots"], d.get("periodic", False), d["degree"],
                            d.get("weights"), c)
    raise FeatureError(f"unknown geometry type {kind!r}")


def source(d: dict, num=_num) -> str:
    """The part file's line for a geometry dict of these kinds, numbers written by num."""
    return from_dict(d).source(num)


# ── what FreeCAD's Python builds of them (feature.to_freecad) ──────────────────────────────────────────

def part_geometry(g, Part, V):
    """The Part geometry SketchObject.addGeometry takes, built as Part's Python builds it."""
    if isinstance(g, BSplineCurve):
        return Part.BSplineCurve([V(x, y, 0) for x, y in g.poles], g.mults, g.knots, g.periodic, g.degree,
                                 g.weights)
    if isinstance(g, _EllipseBase):
        e = Part.Ellipse(V(*g.center, 0), g.major_radius, g.minor_radius)
        e.XAxis = V(*g.x_axis, 0)
        return e if isinstance(g, Ellipse) else Part.ArcOfEllipse(e, g.start_angle, g.end_angle)
    if isinstance(g, ArcOfHyperbola):
        h = Part.Hyperbola()
        h.Location = V(*g.center, 0)
        h.MajorRadius = g.major_radius
        h.MinorRadius = g.minor_radius
        h.XAxis = V(*g.x_axis, 0)
        return Part.ArcOfHyperbola(h, g.start_angle, g.end_angle)
    p = Part.Parabola()
    p.Location = V(*g.center, 0)
    p.Focal = g.focal
    p.XAxis = V(*g.x_axis, 0)
    return Part.ArcOfParabola(p, g.start_angle, g.end_angle)


# ── the kernel ────────────────────────────────────────────────────────────────────────────────────────

def curve(g):
    """The Geom_Curve of Part::Geometry's handle: Geom_Ellipse on gp_Ax2(center, +Z, x_axis), a
    Geom_TrimmedCurve of Geom_Ellipse, Geom_Hyperbola or Geom_Parabola (GC_MakeArcOf*, sense true), or
    the Geom_BSplineCurve."""
    if isinstance(g, BSplineCurve):
        n = len(g.poles)
        poles, weights = TColgp_Array1OfPnt(1, n), TColStd_Array1OfReal(1, n)
        for i, ((x, y), w) in enumerate(zip(g.poles, g.weights)):
            poles.SetValue(i + 1, gp_Pnt(x, y, 0))
            weights.SetValue(i + 1, w)
        knots, mults = TColStd_Array1OfReal(1, len(g.knots)), TColStd_Array1OfInteger(1, len(g.knots))
        for i, (k, m) in enumerate(zip(g.knots, g.mults)):
            knots.SetValue(i + 1, k)
            mults.SetValue(i + 1, m)
        return Geom_BSplineCurve(poles, weights, knots, mults, g.degree, g.periodic)
    ax = gp_Ax2(gp_Pnt(*g.center, 0), gp_Dir(0, 0, 1), gp_Dir(*g.x_axis, 0))
    if isinstance(g, _EllipseBase):
        basis = Geom_Ellipse(ax, g.major_radius, g.minor_radius)
    elif isinstance(g, ArcOfHyperbola):
        basis = Geom_Hyperbola(ax, g.major_radius, g.minor_radius)
    else:
        basis = Geom_Parabola(ax, g.focal)
    if isinstance(g, Ellipse):
        return basis
    return Geom_TrimmedCurve(basis, g.start_angle, g.end_angle, True)


def edge(g):
    """Part::GeomCurve::toShape(): BRepBuilderAPI_MakeEdge(curve, FirstParameter, LastParameter)."""
    c = curve(g)
    return BRepBuilderAPI_MakeEdge(c, c.FirstParameter(), c.LastParameter()).Edge()


def _curve2d(g, edge_of):
    """The 2D curve of a sketch curve's edge in the XY plane (GeomAPI::To2d)."""
    c = curve(g) if isinstance(g, CURVES) else BRepAdaptor_Curve(edge_of(g)).Curve().Curve()
    if not isinstance(g, CURVES) and not (g.kind == "Circle"):
        e = BRepAdaptor_Curve(edge_of(g))
        c = Geom_TrimmedCurve(c, e.FirstParameter(), e.LastParameter())
    return GeomAPI.To2d_s(c, gp_Pln(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)))


SNAP = 1e-4      # a hit this near an end point both curves share is that end point (tangent contacts
#                  there are found to about the square root of the tolerance)


def intersections(g1, g2, edge_of, overlap):
    """Where two sketch curves meet, by Geom2dAPI_InterCurveCurve on their 2D curves, or overlap when
    they share a stretch. g2 None: where g1 crosses itself."""
    c1 = _curve2d(g1, edge_of)
    if g2 is None:
        # Geom2dInt_GInter on one curve: its self-intersections as parameter pairs, less the seam of a
        # closed curve (its first and last parameter meeting)
        inter = Geom2dInt_GInter(Geom2dAdaptor_Curve(c1), 1e-7, 1e-7)
        lo, hi = c1.FirstParameter(), c1.LastParameter()
        eps = 1e-9 * max(1.0, abs(lo), abs(hi))
        out = []
        for i in range(1, inter.NbPoints() + 1):
            ip = inter.Point(i)
            u, w = sorted((ip.ParamOnFirst(), ip.ParamOnSecond()))
            if not (abs(u - lo) <= eps and abs(w - hi) <= eps):
                out.append((ip.Value().X(), ip.Value().Y()))
        return out + ([overlap] if inter.NbSegments() else [])
    c2 = _curve2d(g2, edge_of)
    inter = Geom2dAPI_InterCurveCurve(c1, c2, 1e-7)
    if inter.NbSegments():
        return overlap
    hits = [(inter.Point(i).X(), inter.Point(i).Y()) for i in range(1, inter.NbPoints() + 1)]
    e1 = [p for k, p in g1.points().items() if k != 3]
    e2 = [p for k, p in g2.points().items() if k != 3]
    shared = [p for p in e1 if any(math.dist(p, q) <= 1e-7 for q in e2)]
    out = []
    for h in hits:
        near = [s for s in shared if math.dist(h, s) <= SNAP]
        out.append(near[0] if near else h)
    return out


def tangent_at(g, pos):
    """The unit tangent at the start (1) or end (2), along increasing parameter; None at the centre."""
    if pos not in (1, 2) or isinstance(g, Ellipse):
        return None
    if isinstance(g, BSplineCurve):
        d = g.derivative(g.first if pos == 1 else g.last)
    else:
        d = g.derivative(g.start_angle if pos == 1 else g.end_angle)
    n = math.hypot(*d)
    return (d[0] / n, d[1] / n) if n else None


# ── the constraints on them ───────────────────────────────────────────────────────────────────────────

# Sketcher.Constraint("InternalAlignment:<name>", ...)'s names (ConstraintPy.cpp) and argument counts.
ALIGNMENTS = {"EllipseMajorDiameter": 2, "EllipseMinorDiameter": 2, "EllipseFocus1": 3, "EllipseFocus2": 3,
              "HyperbolaMajor": 2, "HyperbolaMinor": 2, "HyperbolaFocus": 3, "ParabolaFocus": 3,
              "ParabolaFocalAxis": 2, "BSplineControlPoint": 4, "BSplineKnotPoint": 4}


def alignment_counts(type_):
    """The argument counts Constraint(type_, ...) takes when type_ is an InternalAlignment:<name>."""
    if isinstance(type_, str) and type_.startswith("InternalAlignment:"):
        n = ALIGNMENTS.get(type_.split(":", 1)[1])
        if n is not None:
            return (n,)
    return None


def _pair(line, p, q):
    """A line's ends on p and q, either way round (GCS assigns them by which is nearer)."""
    return min(max(math.dist(line.start, p), math.dist(line.end, q)),
               max(math.dist(line.start, q), math.dist(line.end, p)))


def residual(sk, c, v, tol, geo, pt):
    """The check of a constraint that involves these curves, '' when it holds, 'unsupported' when only
    the solver can say, None when it is not about them (feature._residual checks it)."""
    from .feature import Circle, LineSegment
    t, a = c.type, c.args

    def off(measured, wanted=0.0, unit="mm"):
        return "" if abs(measured - wanted) <= tol else f"is {measured:.9g} {unit}, wants {wanted:.9g}"

    if t.startswith("InternalAlignment:"):
        kind = t.split(":", 1)[1]
        if kind in ("EllipseMajorDiameter", "EllipseMinorDiameter", "HyperbolaMajor", "HyperbolaMinor",
                    "ParabolaFocalAxis"):
            line, conic = geo(sk, a[0]), geo(sk, a[1])
            if not isinstance(line, LineSegment):
                return "unsupported"
            if kind.startswith("Ellipse") and isinstance(conic, _EllipseBase):
                r = conic.major_radius if kind == "EllipseMajorDiameter" else conic.minor_radius
                ax = (1, 0) if kind == "EllipseMajorDiameter" else (0, 1)
                return off(_pair(line, conic._off(r * ax[0], r * ax[1]), conic._off(-r * ax[0], -r * ax[1])))
            if kind.startswith("Hyperbola") and isinstance(conic, ArcOfHyperbola):
                A, B = conic.major_radius, conic.minor_radius
                ends = ((A, 0), (-A, 0)) if kind == "HyperbolaMajor" else ((A, B), (A, -B))
                return off(_pair(line, conic._off(*ends[0]), conic._off(*ends[1])))
            if kind == "ParabolaFocalAxis" and isinstance(conic, ArcOfParabola):
                # Sketch.cpp addInternalAlignmentParabolaFocalDistance: start on the vertex, end on the focus
                return off(max(math.dist(line.start, conic.center), math.dist(line.end, conic.focus())))
            return "unsupported"
        if kind in ("EllipseFocus1", "EllipseFocus2", "HyperbolaFocus", "ParabolaFocus"):
            p, conic = pt(sk, a[0], a[1]), geo(sk, a[2])
            if kind.startswith("Ellipse") and isinstance(conic, _EllipseBase):
                return off(math.dist(p, conic.foci()[0 if kind == "EllipseFocus1" else 1]))
            if kind == "HyperbolaFocus" and isinstance(conic, ArcOfHyperbola):
                return off(math.dist(p, conic.focus()))
            if kind == "ParabolaFocus" and isinstance(conic, ArcOfParabola):
                return off(math.dist(p, conic.focus()))
            return "unsupported"
        if kind == "BSplineControlPoint":
            circle, spline, i = geo(sk, a[0]), geo(sk, a[2]), a[3]
            if not (isinstance(circle, Circle) and isinstance(spline, BSplineCurve)
                    and 0 <= i < len(spline.poles)):
                return "unsupported"
            # GCS addConstraintInternalAlignmentBSplineControlPoint: the centre on the pole, the
            # radius the pole's weight
            return off(math.dist(circle.center, spline.poles[i])) or off(circle.radius, spline.weights[i])
        if kind == "BSplineKnotPoint":
            p, spline, i = pt(sk, a[0], a[1]), geo(sk, a[2]), a[3]
            if not (isinstance(spline, BSplineCurve) and 0 <= i < len(spline.knots)):
                return "unsupported"
            return off(math.dist(p, spline.value(spline.knots[i])))
        return "unsupported"
    if t == "Weight":
        g = geo(sk, a[0])
        return off(g.radius, v) if isinstance(g, Circle) else "unsupported"
    if t == "PointOnObject":
        g = geo(sk, a[2])
        if not isinstance(g, CURVES):
            return None
        p = pt(sk, a[0], a[1])
        if isinstance(g, BSplineCurve):
            proj = GeomAPI_ProjectPointOnCurve(gp_Pnt(p[0], p[1], 0), curve(g))
            d = min(([proj.LowerDistance()] if proj.NbPoints() else [])
                    + [math.dist(p, q) for q in g.points().values()])
            return off(d)
        return off(g.on_error(p))
    if t == "Equal":
        g1, g2 = geo(sk, a[0]), geo(sk, a[1])
        if not (isinstance(g1, CURVES) or isinstance(g2, CURVES)):
            return None
        # Sketch.cpp addEqualConstraint: ellipses (and their arcs) and hyperbolas equal radii,
        # parabolas equal focal distances
        if isinstance(g1, _EllipseBase) and isinstance(g2, _EllipseBase) or \
                isinstance(g1, ArcOfHyperbola) and isinstance(g2, ArcOfHyperbola):
            return off(g2.major_radius, g1.major_radius) or off(g2.minor_radius, g1.minor_radius)
        if isinstance(g1, ArcOfParabola) and isinstance(g2, ArcOfParabola):
            return off(g2.focal, g1.focal)
        return "unsupported"
    return None


def unsolved(sk) -> list[str]:
    """The geometry FreeCAD changes before it solves, so that only the solver can say where it ends:
    a B-spline with exactly one weight of 1, which Sketch.cpp's "OCC hack" (Sketch::addBSpline) sets to
    0.99 times the last other weight, as ui/planegcs/sketch.cpp does too. Without a constraint pulling it
    back, FreeCAD's sketch keeps the changed weight."""
    return [f"geometry {i} (BSplineCurve): exactly one weight is 1, which FreeCAD's solve changes first"
            for i, g in enumerate(sk.geometry) if isinstance(g, BSplineCurve) and g.weights.count(1.0) == 1]


def _register():
    """Make these kinds part of cad_agent.feature's vocabulary (feature.Ellipse, feature.GEOMETRY), also
    when this module is imported before cad_agent.feature finished importing it."""
    import sys
    feature = sys.modules[__name__.rsplit(".", 1)[0] + ".feature"]
    for g in CURVES:
        setattr(feature, g.__name__, g)
    if hasattr(feature, "GEOMETRY"):
        feature.GEOMETRY.update(GEOMETRY)


_register()

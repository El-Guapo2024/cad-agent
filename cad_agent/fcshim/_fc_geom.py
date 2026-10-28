# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses FreeCAD's Part geometry classes and keeps FreeCAD's licence, the GNU Lesser
# General Public License, version 2.1 or (at your option) any later version; the text is in ../../ui/LICENSE.
#
#   Derived from: src/Mod/Part/App/Geometry.cpp (Copyright (c) 2008 Werner Mayer), GeometryCurvePyImp.cpp,
#                 LinePyImp.cpp, LineSegmentPyImp.cpp, CirclePyImp.cpp, ArcOfCirclePyImp.cpp, ConicPyImp.cpp,
#                 BSplineCurvePyImp.cpp, PlanePyImp.cpp, CylinderPyImp.cpp, GeometrySurfacePyImp.cpp
#                 FreeCAD (https://github.com/FreeCAD/FreeCAD), commit 3160daf1e2b62b0472854da4848255c6b3ad554c
#
# See ../../NOTICE.
"""Part's geometry (Part.Line, LineSegment, Circle, ArcOfCircle, Ellipse, BSplineCurve, BezierCurve, Plane, Cylinder,
Cone, Sphere, Toroid, SurfaceOfExtrusion, SurfaceOfRevolution, BSplineSurface) over OCCT's Geom handles, through OCP."""
from __future__ import annotations

import math

from OCP.GC import GC_MakeArcOfCircle, GC_MakeCircle, GC_MakeSegment
from OCP.GCPnts import GCPnts_AbscissaPoint, GCPnts_UniformAbscissa
from OCP.Geom import (Geom_BezierCurve, Geom_BSplineCurve, Geom_BSplineSurface, Geom_Circle, Geom_ConicalSurface,
                      Geom_Curve, Geom_CylindricalSurface, Geom_Ellipse, Geom_Hyperbola, Geom_Line, Geom_OffsetCurve,
                      Geom_Parabola, Geom_Plane, Geom_SphericalSurface, Geom_SurfaceOfLinearExtrusion,
                      Geom_SurfaceOfRevolution, Geom_ToroidalSurface, Geom_TrimmedCurve)
from OCP.GeomAdaptor import GeomAdaptor_Curve
from OCP.GeomAPI import GeomAPI_ProjectPointOnCurve
from OCP.GeomConvert import GeomConvert
from OCP.gp import gp_Ax1, gp_Ax2, gp_Circ, gp_Dir, gp_Lin, gp_Pnt, gp_Vec
from OCP.Precision import Precision

from ._fc_base import Vector, vec

OCC_ERROR = RuntimeError


def P(v) -> gp_Pnt:
    v = vec(v)
    return gp_Pnt(v.x, v.y, v.z)


def D(v) -> gp_Dir:
    v = vec(v)
    return gp_Dir(v.x, v.y, v.z)


def V(p) -> Vector:
    return Vector(p.X(), p.Y(), p.Z())


class Geometry:
    """Part::Geometry: a Geom handle in .h."""

    def __init__(self, h=None):
        self.h = h
        self.Construction = False
        self.Tag = ""

    def copy(self):
        return wrap_curve(self.h.Copy()) if isinstance(self.h, Geom_Curve) else wrap_surface(self.h.Copy())

    def transform(self, m):
        from ._fc_part import _gp_trsf
        self.h.Transform(_gp_trsf(m))

    def translate(self, v):
        self.h.Translate(gp_Vec(*vec(v)))

    def isSame(self, o, tol, atol):
        return False

    def getExtensions(self):
        return []

    def __repr__(self):
        return f"<{type(self).__name__} object>"


class Curve(Geometry):
    """Part::GeomCurve."""

    @property
    def FirstParameter(self):
        return self.h.FirstParameter()

    @property
    def LastParameter(self):
        return self.h.LastParameter()

    def value(self, u):
        return V(self.h.Value(float(u)))

    def tangent(self, u):
        p, v = gp_Pnt(), gp_Vec()
        self.h.D1(float(u), p, v)
        if v.Magnitude() > Precision.Confusion_s():
            v.Normalize()
        return (Vector(v.X(), v.Y(), v.Z()),)

    def parameter(self, pt):
        """GeomCurve::closestParameter."""
        proj = GeomAPI_ProjectPointOnCurve(P(pt), self.h)
        if proj.NbPoints() > 0:
            return proj.LowerDistanceParameter()
        # an endpoint: the nearer of first and last
        pt = vec(pt)
        a, b = self.h.FirstParameter(), self.h.LastParameter()
        da = (self.value(a) - pt).Length
        db = (self.value(b) - pt).Length
        return a if da <= db else b

    def isClosed(self):
        return self.h.IsClosed()

    def isPeriodic(self):
        return self.h.IsPeriodic()

    def length(self, u1=None, u2=None, tol=1e-7):
        a = GeomAdaptor_Curve(self.h)
        u1 = self.h.FirstParameter() if u1 is None else u1
        u2 = self.h.LastParameter() if u2 is None else u2
        return GCPnts_AbscissaPoint.Length_s(a, u1, u2, tol)

    def toShape(self, *args):
        from ._fc_part import Edge
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
        if args:
            u1, u2 = float(args[0]), float(args[1])
        else:
            u1, u2 = self.h.FirstParameter(), self.h.LastParameter()
        mk = BRepBuilderAPI_MakeEdge(self.h, u1, u2)
        if not mk.IsDone():
            raise OCC_ERROR("Failed to create edge")
        return Edge(mk.Edge())

    def discretize(self, *args, **kw):
        from ._fc_part import Edge
        return self.toShape().discretize(*args, **kw)

    def toBSpline(self, *args):
        u1 = args[0] if args else self.h.FirstParameter()
        u2 = args[1] if len(args) > 1 else self.h.LastParameter()
        c = GeomConvert.CurveToBSplineCurve_s(Geom_TrimmedCurve(self.h, u1, u2))
        return BSplineCurve(c)

    def reverse(self):
        self.h.Reverse()

    def reversedParameter(self, u):
        return self.h.ReversedParameter(u)

    @property
    def Continuity(self):
        return str(self.h.Continuity())


class Line(Curve):
    """Part.Line: an infinite line (GeomLine)."""

    def __init__(self, *args):
        if len(args) == 1 and isinstance(args[0], Geom_Line):
            super().__init__(args[0])
            return
        if not args:
            super().__init__(Geom_Line(gp_Lin(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1))))
        elif len(args) == 1 and isinstance(args[0], (Line, LineSegment)):
            if isinstance(args[0], LineSegment):
                p1, p2 = args[0].StartPoint, args[0].EndPoint
                super().__init__(Geom_Line(P(p1), D(p2 - p1)))
            else:
                super().__init__(Geom_Line(args[0].h.Lin()))
        else:
            p1, p2 = vec(args[0]), vec(args[1])
            if (p2 - p1).Length < Precision.Confusion_s():
                raise OCC_ERROR("Both points are equal")
            super().__init__(Geom_Line(gp_Lin(P(p1), D(p2 - p1))))

    @property
    def Location(self):
        return V(self.h.Position().Location())

    @Location.setter
    def Location(self, v):
        self.h.SetLocation(P(v))

    @property
    def Direction(self):
        d = self.h.Position().Direction()
        return Vector(d.X(), d.Y(), d.Z())

    @Direction.setter
    def Direction(self, v):
        self.h.SetDirection(D(v))


class TrimmedCurve(Curve):
    def __init__(self, h=None):
        super().__init__(h)

    @property
    def StartPoint(self):
        return V(self.h.StartPoint())

    @property
    def EndPoint(self):
        return V(self.h.EndPoint())

    def setParameterRange(self, u1, u2):
        self.h.SetTrim(u1, u2)

    @property
    def BasisCurve(self):
        return wrap_curve(self.h.BasisCurve())


class LineSegment(TrimmedCurve):
    def __init__(self, *args):
        if len(args) == 1 and isinstance(args[0], Geom_TrimmedCurve):
            super().__init__(args[0])
            return
        if not args:
            super().__init__(Geom_TrimmedCurve(Geom_Line(gp_Lin(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0))), 0.0, 1.0))
            return
        if len(args) == 1 and isinstance(args[0], LineSegment):
            super().__init__(Geom_TrimmedCurve.DownCast(args[0].h.Copy()) if hasattr(Geom_TrimmedCurve, "DownCast")
                             else args[0].h.Copy())
            return
        if len(args) == 3 and isinstance(args[0], (Line, LineSegment)):
            base = args[0].h if isinstance(args[0], Line) else args[0].h.BasisCurve()
            super().__init__(Geom_TrimmedCurve(base, float(args[1]), float(args[2])))
            return
        p1, p2 = vec(args[0]), vec(args[1])
        if (p2 - p1).Length < Precision.Confusion_s():
            raise OCC_ERROR("Both points are equal")
        ms = GC_MakeSegment(P(p1), P(p2))
        if not ms.IsDone():
            raise OCC_ERROR("Failed to create line segment")
        super().__init__(ms.Value())

    @property
    def Direction(self):
        d = self.EndPoint - self.StartPoint
        return d.normalize() if d.Length > 0 else d


class Conic(Curve):
    def _conic(self):
        return self.h

    @property
    def Center(self):
        return V(self._conic().Location())

    @Center.setter
    def Center(self, v):
        self._conic().SetLocation(P(v))

    Location = Center

    @property
    def Axis(self):
        d = self._conic().Axis().Direction()
        return Vector(d.X(), d.Y(), d.Z())

    @Axis.setter
    def Axis(self, v):
        c = self._conic()
        c.SetAxis(gp_Ax1(c.Location(), D(v)))

    @property
    def XAxis(self):
        d = self._conic().XAxis().Direction()
        return Vector(d.X(), d.Y(), d.Z())

    @property
    def YAxis(self):
        d = self._conic().YAxis().Direction()
        return Vector(d.X(), d.Y(), d.Z())

    @property
    def AngleXU(self):
        """GeomConic::getAngleXU."""
        c = self._conic()
        center, normal = c.Axis().Location(), c.Axis().Direction()
        xdir = c.XAxis().Direction()
        return -xdir.AngleWithRef(gp_Ax2(center, normal).XDirection(), normal)

    @AngleXU.setter
    def AngleXU(self, angle):
        """GeomConic::setAngleXU."""
        c = self._conic()
        center, normal = c.Axis().Location(), c.Axis().Direction()
        ref = gp_Ax2(center, normal)
        ref.Rotate(gp_Ax1(center, normal), float(angle))
        c.SetPosition(ref)


class Circle(Conic):
    def __init__(self, *args):
        if len(args) == 1 and isinstance(args[0], Geom_Circle):
            super().__init__(args[0])
            return
        if not args:
            super().__init__(Geom_Circle(gp_Circ(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), 1.0)))
            return
        if len(args) == 1 and isinstance(args[0], Circle):
            super().__init__(Geom_Circle(args[0].h.Circ()))
            return
        if len(args) == 2 and isinstance(args[0], Circle):      # (circle, distance): a parallel circle
            c = args[0].h.Circ()
            super().__init__(Geom_Circle(gp_Circ(c.Position(), c.Radius() + float(args[1]))))
            return
        if len(args) == 3 and all(isinstance(a, Vector) for a in args):
            mc = GC_MakeCircle(P(args[0]), P(args[1]), P(args[2]))
            if not mc.IsDone():
                raise OCC_ERROR("Failed to create circle")
            super().__init__(mc.Value())
            return
        if len(args) == 3:
            center, normal, radius = vec(args[0]), vec(args[1]), float(args[2])
            mc = GC_MakeCircle(P(center), D(normal), radius)
            if not mc.IsDone():
                raise OCC_ERROR("Failed to create circle")
            super().__init__(mc.Value())
            return
        raise TypeError("Circle constructor accepts: -- empty parameter list -- Circle -- Circle, Distance -- "
                        "Center, Normal, Radius -- Point1, Point2, Point3")

    @property
    def Radius(self):
        return self.h.Radius()

    @Radius.setter
    def Radius(self, r):
        self.h.SetRadius(float(r))


class Ellipse(Conic):
    def __init__(self, *args):
        if len(args) == 1 and isinstance(args[0], Geom_Ellipse):
            super().__init__(args[0])
            return
        raise NotImplementedError("Part.Ellipse(...)")

    @property
    def MajorRadius(self):
        return self.h.MajorRadius()

    @property
    def MinorRadius(self):
        return self.h.MinorRadius()


class Hyperbola(Conic):
    pass


class Parabola(Conic):
    pass


class ArcOfConic(TrimmedCurve):
    def _conic(self):
        return self.h.BasisCurve()

    Center = Conic.Center
    Location = Conic.Center
    Axis = Conic.Axis
    XAxis = Conic.XAxis
    YAxis = Conic.YAxis
    AngleXU = Conic.AngleXU


class ArcOfCircle(ArcOfConic):
    def __init__(self, *args):
        if len(args) == 1 and isinstance(args[0], Geom_TrimmedCurve):
            super().__init__(args[0])
            return
        if len(args) in (3, 4) and isinstance(args[0], Circle):
            sense = bool(args[3]) if len(args) == 4 else True
            super().__init__(Geom_TrimmedCurve(Geom_Circle(args[0].h.Circ()), float(args[1]), float(args[2]), sense))
            return
        if len(args) == 3 and all(isinstance(a, Vector) for a in args):
            ma = GC_MakeArcOfCircle(P(args[0]), P(args[1]), P(args[2]))
            if not ma.IsDone():
                raise OCC_ERROR("Failed to create arc of circle")
            super().__init__(ma.Value())
            return
        raise TypeError("ArcOfCircle constructor expects a circle curve and a parameter range or three points")

    @property
    def Radius(self):
        return self.h.BasisCurve().Radius()

    @property
    def Circle(self):
        return Circle(Geom_Circle(self.h.BasisCurve().Circ()))


Arc = ArcOfCircle


class ArcOfEllipse(ArcOfConic):
    pass


class BSplineCurve(Curve):
    def __init__(self, *args):
        if len(args) == 1 and isinstance(args[0], Geom_BSplineCurve):
            super().__init__(args[0])
            return
        if not args:
            from OCP.TColgp import TColgp_Array1OfPnt
            from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal
            poles = TColgp_Array1OfPnt(1, 2)
            poles.SetValue(1, gp_Pnt(0, 0, 0))
            poles.SetValue(2, gp_Pnt(1, 0, 0))
            knots = TColStd_Array1OfReal(1, 2)
            knots.SetValue(1, 0.0)
            knots.SetValue(2, 1.0)
            mults = TColStd_Array1OfInteger(1, 2)
            mults.SetValue(1, 2)
            mults.SetValue(2, 2)
            super().__init__(Geom_BSplineCurve(poles, knots, mults, 1))
            return
        raise NotImplementedError("Part.BSplineCurve(...)")

    @property
    def StartPoint(self):
        return V(self.h.StartPoint())

    @property
    def EndPoint(self):
        return V(self.h.EndPoint())

    @property
    def Degree(self):
        return self.h.Degree()

    @property
    def NbPoles(self):
        return self.h.NbPoles()

    def getPoles(self):
        return [V(self.h.Pole(i)) for i in range(1, self.h.NbPoles() + 1)]

    def getKnots(self):
        return [self.h.Knot(i) for i in range(1, self.h.NbKnots() + 1)]

    def getMultiplicities(self):
        return [self.h.Multiplicity(i) for i in range(1, self.h.NbKnots() + 1)]

    def getWeights(self):
        return [self.h.Weight(i) for i in range(1, self.h.NbPoles() + 1)]

    def isRational(self):
        return self.h.IsRational()

    def toBiArcs(self, tolerance):
        from . import _fc_biarcs
        return _fc_biarcs.to_biarcs(self, tolerance)


class BezierCurve(Curve):
    @property
    def StartPoint(self):
        return V(self.h.StartPoint())

    @property
    def EndPoint(self):
        return V(self.h.EndPoint())


class OffsetCurve(Curve):
    pass


# ─── surfaces ───────────────────────────────────────────────────────────────────────────────────────────────────────

class GeometrySurface(Geometry):
    def value(self, u, v):
        return V(self.h.Value(u, v))

    def normal(self, u, v):
        from OCP.GeomLProp import GeomLProp_SLProps
        prop = GeomLProp_SLProps(self.h, u, v, 1, Precision.Confusion_s())
        n = prop.Normal()
        return Vector(n.X(), n.Y(), n.Z())

    def toShape(self, *args):
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
        from ._fc_part import Face
        if args:
            mk = BRepBuilderAPI_MakeFace(self.h, *[float(a) for a in args], Precision.Confusion_s())
        else:
            u1, u2, v1, v2 = self.h.Bounds()
            mk = BRepBuilderAPI_MakeFace(self.h, u1, u2, v1, v2, Precision.Confusion_s())
        return Face(mk.Face())


class _Elementary(GeometrySurface):
    @property
    def Axis(self):
        d = self.h.Position().Direction()
        return Vector(d.X(), d.Y(), d.Z())

    @property
    def Position(self):
        return V(self.h.Position().Location())

    Center = Position


class Plane(_Elementary):
    def __init__(self, *args):
        if len(args) == 1 and isinstance(args[0], Geom_Plane):
            super().__init__(args[0])
            return
        if not args:
            super().__init__(Geom_Plane(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)))
            return
        if len(args) == 2:
            super().__init__(Geom_Plane(P(args[0]), D(args[1])))
            return
        raise NotImplementedError("Part.Plane(...)")


class Cylinder(_Elementary):
    @property
    def Radius(self):
        return self.h.Radius()


class Cone(_Elementary):
    @property
    def Apex(self):
        return V(self.h.Apex())

    @property
    def SemiAngle(self):
        return self.h.SemiAngle()

    @property
    def Radius(self):
        return self.h.RefRadius()


class Sphere(_Elementary):
    @property
    def Radius(self):
        return self.h.Radius()


class Toroid(_Elementary):
    @property
    def MajorRadius(self):
        return self.h.MajorRadius()

    @property
    def MinorRadius(self):
        return self.h.MinorRadius()


class SurfaceOfExtrusion(GeometrySurface):
    @property
    def Direction(self):
        d = self.h.Direction()
        return Vector(d.X(), d.Y(), d.Z())


class SurfaceOfRevolution(GeometrySurface):
    @property
    def Direction(self):
        d = self.h.Direction()
        return Vector(d.X(), d.Y(), d.Z())


class BSplineSurface(GeometrySurface):
    pass


class BezierSurface(GeometrySurface):
    pass


class OffsetSurface(GeometrySurface):
    pass


class PlateSurface(GeometrySurface):
    pass


def wrap_curve(h):
    """Part's Python object for a Geom_Curve handle (GeomCurve::createFromHandle's types)."""
    for cls, pycls in ((Geom_Line, Line), (Geom_Circle, Circle), (Geom_Ellipse, Ellipse), (Geom_Hyperbola, Hyperbola),
                       (Geom_Parabola, Parabola), (Geom_BSplineCurve, BSplineCurve), (Geom_BezierCurve, BezierCurve),
                       (Geom_OffsetCurve, OffsetCurve)):
        if isinstance(h, cls):
            o = object.__new__(pycls)
            Geometry.__init__(o, h)
            return o
    if isinstance(h, Geom_TrimmedCurve):
        b = h.BasisCurve()
        pycls = LineSegment if isinstance(b, Geom_Line) else ArcOfCircle if isinstance(b, Geom_Circle) else (
            ArcOfEllipse if isinstance(b, Geom_Ellipse) else TrimmedCurve)
        o = object.__new__(pycls)
        Geometry.__init__(o, h)
        return o
    o = object.__new__(Curve)
    Geometry.__init__(o, h)
    return o


def wrap_surface(h):
    for cls, pycls in ((Geom_Plane, Plane), (Geom_CylindricalSurface, Cylinder), (Geom_ConicalSurface, Cone),
                       (Geom_SphericalSurface, Sphere), (Geom_ToroidalSurface, Toroid),
                       (Geom_SurfaceOfLinearExtrusion, SurfaceOfExtrusion),
                       (Geom_SurfaceOfRevolution, SurfaceOfRevolution), (Geom_BSplineSurface, BSplineSurface)):
        if isinstance(h, cls):
            o = object.__new__(pycls)
            Geometry.__init__(o, h)
            return o
    o = object.__new__(GeometrySurface)
    Geometry.__init__(o, h)
    return o

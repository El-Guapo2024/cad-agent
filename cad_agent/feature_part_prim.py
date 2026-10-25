# SPDX-License-Identifier: LGPL-2.1-or-later
# A port of FreeCAD's Part primitives (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), each file
# LGPL-2.1-or-later as it states:
#   src/Mod/Part/App/PrimitiveFeature.cpp: Copyright (c) 2002 Jürgen Riegel
#   src/Mod/Part/App/FeaturePartBox.cpp, FeaturePartCircle.cpp, FeaturePartPolygon.cpp: Copyright (c) 2002 Jürgen Riegel
#   src/Mod/Part/App/TopoShape.cpp (makeSpiralHelix): Copyright (c) 2002 Jürgen Riegel
#   src/Mod/Part/BasicShapes/Shapes.py (Tube): Copyright (c) 2019 Werner Mayer
#   src/Mod/Part/Gui/CommandParametric.cpp, DlgPrimitives.cpp: the Labels and transactions their commands give
"""Part's primitives: Box, Cylinder, Sphere, Cone, Torus, Tube, Prism, Wedge, Helix, Spiral, Ellipsoid, Plane, Circle,
Ellipse, Line, Vertex (Part's Point), RegularPolygon and Polygon.

    Part.Box("Box", length=40, width=20, height=5, label="Cube")
    Part.Cylinder("Cylinder", radius=3, height=5, placement=((8, 10, 0), (0, 0, 0)))
    Part.Helix("Helix", pitch=2, height=10, radius=3, local_coord="Left-handed")

Property names and defaults are FreeCAD's (PrimitiveFeature.cpp), in snake_case: Box length, width, height 10;
Cylinder radius 2, height 10, angle 360, first_angle, second_angle 0 (PrismExtension); Sphere radius 5, angle1 -90,
angle2 90, angle3 360; Cone radius1 2, radius2 4, height 10, angle 360; Torus radius1 10, radius2 2, angle1 -180,
angle2 180, angle3 360; Tube outer_radius 5, inner_radius 2, height 10; Prism polygon 6, circumradius 2, height 10,
first_angle, second_angle; Wedge xmin, ymin, zmin 0, x2min, z2min 2, xmax, ymax, zmax 10, x2max, z2max 8; Helix
pitch 1, height 2, radius 1, segment_length 0, angle 0, local_coord "Right-handed"; Spiral growth 1, radius 1,
rotations 2, segment_length 1; Ellipsoid radius1 2, radius2 4, radius3 0, angle1 -90, angle2 90, angle3 360; Plane
length, width 100; Circle radius 2, angle1 0, angle2 360; Ellipse major_radius, minor_radius 4, angle1 0, angle2 360;
Line x1, y1, z1, x2, y2 0 and z2 1; Vertex x, y, z 0; RegularPolygon polygon 6, circumradius 2; Polygon nodes
[(0, 0, 0)], close False. Every primitive has placement, ((x, y, z), (yaw, pitch, roll)), and label.

The shapes are made by the same OCCT calls in the same order as FreeCAD's, mostly by the PartDesign primitives' code
(feature_primitive.py: FreeCAD's Part::Box and PartDesign::Box run the same lines). Out-of-range values clamp as
FreeCAD's constrained properties clamp them.
"""
from __future__ import annotations

import math

from . import feature as F
from . import feature_primitive as PD
from .feature_part import Placed, PartObject, register

try:
    from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon,
                                    BRepBuilderAPI_MakeVertex, BRepBuilderAPI_MakeWire)
    from OCP.BRepLib import BRepLib
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
    from OCP.Geom2d import Geom2d_Line, Geom2d_TrimmedCurve
    from OCP.Geom import Geom_BezierCurve, Geom_Plane, Geom_SurfaceOfRevolution
    from OCP.GeomAbs import GeomAbs_C1
    try:
        from OCP.TColgp import TColgp_Array1OfPnt
    except ImportError:                 # OCP 8 moved OCCT's collections
        from OCP.collections import Array1_gp_Pnt as TColgp_Array1OfPnt
    from OCP.gp import gp, gp_Ax1, gp_Circ, gp_Dir, gp_Elips, gp_Pnt, gp_Dir2d, gp_Pnt2d, gp_Vec2d
except ImportError:                     # pragma: no cover - only FreeCAD's Python lands here
    pass

CONFUSION = 1e-7
FLT_MAX = 3.4028234663852886e38
LEN = (0.0, math.inf)                    # App::PropertyLength
QRANGE = (0.0, FLT_MAX)                  # quantityRange
ANGLE_U = (0.0, 360.0)
ANGLE_V = (-90.0, 90.0)
TORUS_V = (-180.0, 180.0)
APEX = (-89.9, 89.9)
SKEW = (-89.99999, 89.99999)


class Primitive(Placed):
    """Part::Primitive: AttachExtension's Placement (MapMode Deactivated), and a shape of its own."""
    PD = None                            # the PartDesign class whose shape() is FreeCAD's same code

    def validate(self):
        super().validate()
        for k in self.DEFAULTS:
            if k in ("placement", "label", "visibility") or k in self.ATTACH or k in self.ENUMS:
                continue
            val = getattr(self, k)
            if isinstance(val, bool) or not isinstance(val, (int, float, str)):
                raise F.FeatureError(f"{self.name}: {k} is {val!r}, not a number or a PARAMS expression")

    def local(self, params):
        return self.PD.shape(self, params)

    def fc_props(self):
        for prop, k, val in super().fc_props():
            if k == "polygon" and not isinstance(val, str):
                val = int(round(val))
            yield prop, k, val


def _prim(kind, dims, ranges=None, pd=None, label=None, transaction=None, enums=None, base=Primitive, **extra):
    name = kind
    cls = type(name, (base,), {
        "__doc__": f"Part::{name}.", "kind": f"Part.{name}", "TYPE_ID": f"Part::{name}",
        "DEFAULTS": {**dims, **base.COMMON}, "RANGES": ranges or {}, "PD": pd, "LABEL": label,
        "ENUMS": enums or {}, "TRANSACTION": transaction or (label or name), **extra})
    return cls


Box = _prim("Box", {"length": 10.0, "width": 10.0, "height": 10.0},
            {"length": LEN, "width": LEN, "height": LEN}, PD.Box, label="Cube")
Cylinder = _prim("Cylinder", {"radius": 2.0, "height": 10.0, "angle": 360.0, "first_angle": 0.0, "second_angle": 0.0},
                 {"radius": LEN, "height": LEN, "angle": ANGLE_U, "first_angle": SKEW, "second_angle": SKEW},
                 PD.Cylinder)
Sphere = _prim("Sphere", {"radius": 5.0, "angle1": -90.0, "angle2": 90.0, "angle3": 360.0},
               {"radius": QRANGE, "angle1": ANGLE_V, "angle2": ANGLE_V, "angle3": ANGLE_U}, PD.Sphere)
Ellipsoid = _prim("Ellipsoid", {"radius1": 2.0, "radius2": 4.0, "radius3": 0.0, "angle1": -90.0, "angle2": 90.0,
                                "angle3": 360.0},
                  {"radius1": QRANGE, "radius2": QRANGE, "radius3": QRANGE, "angle1": ANGLE_V, "angle2": ANGLE_V,
                   "angle3": ANGLE_U}, PD.Ellipsoid)
Torus = _prim("Torus", {"radius1": 10.0, "radius2": 2.0, "angle1": -180.0, "angle2": 180.0, "angle3": 360.0},
              {"radius1": QRANGE, "radius2": QRANGE, "angle1": TORUS_V, "angle2": TORUS_V, "angle3": ANGLE_U},
              PD.Torus)
class _Prism(Primitive):
    def local(self, params):
        """Prism::execute: the polygon's sides at least 3, as its PropertyIntegerConstraint (polygonRange) holds it."""
        n = max(3, int(round(F.value(self.polygon, params, f"{self.name}.polygon"))))
        R, h = self.v("circumradius", params), self.v("height", params)
        if R < CONFUSION:
            raise F.FeatureError("Circumradius of the polygon, of the prism, is too small")
        if h < CONFUSION:
            raise F.FeatureError("Height of prism is too small")
        return PD._prism(h, BRepBuilderAPI_MakeFace(_polygon(n, R)).Face(), self.v("first_angle", params),
                         self.v("second_angle", params))


def _polygon(n, R):
    """The n-gon of circumradius R, its vertex turned by Base::Matrix4D::rotZ again and again, closed."""
    a = math.radians(360.0 / n)
    c, s = math.cos(a), math.sin(a)
    poly = BRepBuilderAPI_MakePolygon()
    x, y = R, 0.0
    for _ in range(n):
        poly.Add(gp_Pnt(x, y, 0.0))
        x, y = c * x - s * y, s * x + c * y
    poly.Add(gp_Pnt(x, y, 0.0))
    return poly.Wire()


Prism = _prim("Prism", {"polygon": 6, "circumradius": 2.0, "height": 10.0, "first_angle": 0.0, "second_angle": 0.0},
              {"circumradius": LEN, "height": LEN, "first_angle": SKEW, "second_angle": SKEW}, base=_Prism)
Wedge = _prim("Wedge", {"xmin": 0.0, "ymin": 0.0, "zmin": 0.0, "x2min": 2.0, "z2min": 2.0, "xmax": 10.0,
                        "ymax": 10.0, "zmax": 10.0, "x2max": 8.0, "z2max": 8.0}, None, PD.Wedge)
Wedge.DIMS = {k: v for k, v in Wedge.DEFAULTS.items() if k not in Primitive.COMMON}   # PD.Wedge.shape reads DIMS


class _Cone(Primitive):
    def local(self, params):
        r1, r2, h, a = (self.v(k, params) for k in ("radius1", "radius2", "height", "angle"))
        if r1 < 0 or r2 < 0:
            raise F.FeatureError("Radius of cone too small")
        if h < CONFUSION:
            raise F.FeatureError("Height of cone too small")
        return PD.Cone.shape(self, params)


Cone = _prim("Cone", {"radius1": 2.0, "radius2": 4.0, "height": 10.0, "angle": 360.0},
             {"radius1": LEN, "radius2": LEN, "height": LEN, "angle": ANGLE_U}, base=_Cone)


class _Plane(Primitive):
    def local(self, params):
        L, W = self.v("length", params), self.v("width", params)
        if L < CONFUSION:
            raise F.FeatureError("Length of plane too small")
        if W < CONFUSION:
            raise F.FeatureError("Width of plane too small")
        mk = BRepBuilderAPI_MakeFace(Geom_Plane(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), 0.0, L, 0.0, W, CONFUSION)
        if not mk.IsDone():
            raise F.FeatureError("no face")
        return mk.Shape()


Plane = _prim("Plane", {"length": 100.0, "width": 100.0}, {"length": LEN, "width": LEN}, base=_Plane)


def _segment(a, b):
    """GCE2d_MakeSegment(a, b): the line from a towards b, trimmed to [0, |ab|]."""
    return Geom2d_TrimmedCurve(Geom2d_Line(a, gp_Dir2d(b.X() - a.X(), b.Y() - a.Y())), 0.0, a.Distance(b))


def spiral_helix(radiusbottom, radiustop, height, nbturns, breakperiod, left_handed):
    """TopoShape::makeSpiralHelix: a 2D line on a surface of revolution of a Bezier meridian, in pieces of breakperiod
    turns, its 3D curves built."""
    if breakperiod < 0 or breakperiod > 1000:
        raise F.FeatureError("Break period must be in [0, 1000]")
    if breakperiod == 0:
        breakperiod = 1000
    if nbturns <= 0:
        raise F.FeatureError("Number of turns must be greater than 0")
    nb_periods = nbturns / breakperiod
    nb_full = math.floor(nb_periods)
    part = nb_periods - nb_full
    poles = TColgp_Array1OfPnt(1, 2)
    poles.SetValue(1, gp_Pnt(radiusbottom, 0, 0))
    poles.SetValue(2, gp_Pnt(radiustop, 0, height))
    meridian = Geom_BezierCurve(poles)
    surf = Geom_SurfaceOfRevolution(meridian, gp_Ax1(gp_Pnt(0.0, 0.0, 0.0), gp.DZ_s()))
    beg = gp_Pnt2d(0, 0)
    d = gp_Vec2d((-1 if left_handed else 1) * breakperiod * 2.0 * math.pi, 1 / nb_periods)
    mk = BRepBuilderAPI_MakeWire()
    for _ in range(int(nb_full)):
        end = beg.Translated(d)
        mk.Add(BRepBuilderAPI_MakeEdge(_segment(beg, end), surf).Edge())
        beg = end
    if part > CONFUSION:
        d.Scale(part)
        end = beg.Translated(d)
        mk.Add(BRepBuilderAPI_MakeEdge(_segment(beg, end), surf).Edge())
    wire = mk.Wire()
    BRepLib.BuildCurves3d_s(wire, CONFUSION * 1e-6 * (radiusbottom + radiustop), GeomAbs_C1, 14, 10000)
    return wire


class _Helix(Primitive):
    def local(self, params):
        pitch, height, radius, angle, seg = (self.v(k, params) for k in
                                              ("pitch", "height", "radius", "angle", "segment_length"))
        if pitch < CONFUSION:
            raise F.FeatureError("Pitch too small")
        turns = height / pitch
        if turns > 1e4:
            raise F.FeatureError("Number of turns too high (> 1e4)")
        top = radius + height * math.tan(math.radians(angle))
        return spiral_helix(radius, top, height, turns, seg, self.local_coord != "Right-handed")


HANDS = ("Right-handed", "Left-handed")
Helix = _prim("Helix", {"pitch": 1.0, "height": 2.0, "radius": 1.0, "segment_length": 0.0, "angle": 0.0,
                        "local_coord": "Right-handed"},
              {"pitch": QRANGE, "height": QRANGE, "radius": QRANGE, "segment_length": QRANGE, "angle": APEX},
              base=_Helix, enums={"local_coord": HANDS})


class _Spiral(Primitive):
    def local(self, params):
        rot, radius, growth, seg = (self.v(k, params) for k in ("rotations", "radius", "growth", "segment_length"))
        if rot < CONFUSION:
            raise F.FeatureError("Number of rotations too small")
        return spiral_helix(radius, radius + growth * rot, 0, rot, seg, False)


Spiral = _prim("Spiral", {"growth": 1.0, "radius": 1.0, "rotations": 2.0, "segment_length": 1.0},
               {"growth": QRANGE, "radius": QRANGE, "rotations": QRANGE, "segment_length": QRANGE}, base=_Spiral)


class _Circle(Primitive):
    def local(self, params):
        c = gp_Circ()
        c.SetRadius(self.v("radius", params))
        return BRepBuilderAPI_MakeEdge(c, math.radians(self.v("angle1", params)),
                                       math.radians(self.v("angle2", params))).Edge()


Circle = _prim("Circle", {"radius": 2.0, "angle1": 0.0, "angle2": 360.0},
               {"radius": LEN, "angle1": ANGLE_U, "angle2": ANGLE_U}, base=_Circle)


class _Ellipse(Primitive):
    def local(self, params):
        a, b = self.v("major_radius", params), self.v("minor_radius", params)
        if b > a:
            raise F.FeatureError("Minor radius greater than major radius")
        if b < CONFUSION:
            raise F.FeatureError("Minor radius of ellipse too small")
        e = gp_Elips()
        e.SetMajorRadius(a)
        e.SetMinorRadius(b)
        return BRepBuilderAPI_MakeEdge(e, math.radians(self.v("angle1", params)),
                                       math.radians(self.v("angle2", params))).Edge()


Ellipse = _prim("Ellipse", {"major_radius": 4.0, "minor_radius": 4.0, "angle1": 0.0, "angle2": 360.0},
                {"major_radius": LEN, "minor_radius": LEN, "angle1": ANGLE_U, "angle2": ANGLE_U}, base=_Ellipse)


class _Line(Primitive):
    def local(self, params):
        p1 = gp_Pnt(*(self.v(k, params) for k in ("x1", "y1", "z1")))
        p2 = gp_Pnt(*(self.v(k, params) for k in ("x2", "y2", "z2")))
        mk = BRepBuilderAPI_MakeEdge(p1, p2)
        if not mk.IsDone():
            raise F.FeatureError("Failed to create edge")
        return mk.Edge()


Line = _prim("Line", {"x1": 0.0, "y1": 0.0, "z1": 0.0, "x2": 0.0, "y2": 0.0, "z2": 1.0}, base=_Line)


class _Vertex(Primitive):
    def local(self, params):
        return BRepBuilderAPI_MakeVertex(gp_Pnt(*(self.v(k, params) for k in ("x", "y", "z")))).Vertex()


Vertex = _prim("Vertex", {"x": 0.0, "y": 0.0, "z": 0.0}, base=_Vertex, label="Point", transaction="Point")


class _RegularPolygon(Primitive):
    def local(self, params):
        n = max(3, int(round(F.value(self.polygon, params, f"{self.name}.polygon"))))    # PropertyIntegerConstraint
        R = self.v("circumradius", params)
        if R < CONFUSION:
            raise F.FeatureError("Circumradius of the polygon is too small")
        return _polygon(n, R)


RegularPolygon = _prim("RegularPolygon", {"polygon": 6, "circumradius": 2.0}, {"circumradius": LEN},
                       base=_RegularPolygon)


class _Tube(Primitive):
    """BasicShapes.Shapes.TubeFeature: a Part::FeaturePython with AttachExtensionPython; makeTube."""
    FC_TYPE = "Part::FeaturePython"

    def local(self, params):
        outer, inner, h = (self.v(k, params) for k in ("outer_radius", "inner_radius", "height"))
        if inner >= outer:
            raise F.FeatureError("Inner radius must be smaller than outer radius")
        shape = BRepPrimAPI_MakeCylinder(outer, h).Shape()          # Part.makeCylinder
        if 0 < inner < outer:
            from .feature_part_bool import fc_boolean
            shape = fc_boolean("cut", shape, BRepPrimAPI_MakeCylinder(inner, h).Shape())   # TopoShape.cut
        return shape

    def fc_setup(self, obj, fc):
        from BasicShapes import Shapes
        Shapes.TubeFeature(obj)


Tube = _prim("Tube", {"outer_radius": 5.0, "inner_radius": 2.0, "height": 10.0},
             {"outer_radius": LEN, "inner_radius": LEN, "height": LEN}, base=_Tube)


class Polygon(PartObject):
    """Part::Polygon: a polyline through nodes, closed when close is True (FeaturePartPolygon.cpp)."""
    kind = "Part.Polygon"
    TYPE_ID = "Part::Polygon"
    DEFAULTS = {"nodes": ((0.0, 0.0, 0.0),), "close": False, **PartObject.COMMON}
    TRANSACTION = "Polygon"

    def normalize(self, key, v):
        if key == "nodes":
            try:
                return tuple(tuple(float(c) for c in p) for p in v)
            except (TypeError, ValueError):
                raise F.FeatureError(f"{self.name}: nodes {v!r} is not a list of (x, y, z)") from None
        return super().normalize(key, v)

    def shape(self, ctx, params):
        poly = BRepBuilderAPI_MakePolygon()
        for p in self.nodes:
            poly.Add(gp_Pnt(*p))
        if self.close:
            poly.Close()
        if not poly.IsDone():
            raise F.FeatureError("Cannot create polygon because less than two vertices are given")
        return poly.Wire()


PRIMITIVES = (Box, Cylinder, Sphere, Cone, Torus, Tube, Prism, Wedge, Helix, Spiral, Ellipsoid, Plane, Circle, Ellipse,
              Line, Vertex, RegularPolygon, Polygon)
register(*PRIMITIVES)

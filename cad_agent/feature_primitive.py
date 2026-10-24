# SPDX-License-Identifier: LGPL-2.1-or-later
# A port of FreeCAD's PartDesign primitives (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), each file
# LGPL-2.1-or-later as it states:
#   src/Mod/PartDesign/App/FeaturePrimitive.cpp: Copyright (c) 2015 Stefan Tröger
#   src/Mod/Part/App/PrismExtension.cpp: Copyright (c) 2021 Werner Mayer
#   src/Mod/Part/App/TopoShape.cpp (makeTorus): Copyright (c) 2002 Jürgen Riegel
"""PartDesign's additive and subtractive primitives in a FEATURES list: Box, Cylinder, Sphere, Cone, Ellipsoid, Torus,
Prism and Wedge, each as PartDesign::Additive<Shape> and PartDesign::Subtractive<Shape>.

    AdditiveBox("Box", length=40, width=20, height=5)
    SubtractiveCylinder("Cylinder", radius=3, height=5, placement=((8, 10, 0), (0, 0, 0)))
    SubtractiveSphere("Sphere", radius=4, placement=((20, 10, 5), (0, 0, 0)), operation="Common")

Property names are FreeCAD's in snake_case with FreeCAD's defaults (FeaturePrimitive.cpp): Box length, width, height
(10 each); Cylinder radius 10, height 10, angle 360, first_angle and second_angle 0 (Part::PrismExtension's skew);
Sphere radius 5, angle1 -90, angle2 90, angle3 360; Cone radius1 2, radius2 4, height 10, angle 360; Ellipsoid
radius1 2 (along z), radius2 4 (x), radius3 0 (y; 0 is radius2), angle1 -90, angle2 90, angle3 360; Torus radius1 10,
radius2 2, angle1 -180, angle2 180, angle3 360; Prism polygon 6, circumradius 2, height 10, first_angle, second_angle;
Wedge xmin 0, ymin 0, zmin 0, x2min 2, z2min 2, xmax 10, ymax 10, zmax 10, x2max 8, z2max 8. Every one has refine
(True) and placement, FreeCAD's Placement as ((x, y, z), (yaw, pitch, roll)) in mm and degrees, App.Rotation's order;
a subtractive one has operation, "Subtraction" or "Common" (FeatureAddSub's Operation). Angles are degrees. A value may
be a PARAMS name or an expression, as a Pad's length may. Values outside a property's range are clamped to it, as
FreeCAD's PropertyQuantityConstraint clamps them (a cylinder's angle at most 360, a box's length at least 2e-7 mm).

Placement: FreeCAD positions a primitive by its Attachment (Part::AttachExtension); with MapMode Deactivated, the default
the command leaves, the Placement is the user's. That is what placement holds; placement_of() is the one function an
attachment engine replaces when MapMode and AttachmentSupport come.
"""
from __future__ import annotations

import math

from . import feature as F
from .feature_kw import KwFeature
from .feature_transform import element_boolean, transformed

try:
    from OCP.BRepBuilderAPI import (BRepBuilderAPI_GTransform, BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace,
                                    BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeSolid, BRepBuilderAPI_MakeVertex,
                                    BRepBuilderAPI_MakeWire)
    from OCP.BRepPrim import BRepPrim_Wedge
    from OCP.BRepPrimAPI import (BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCone, BRepPrimAPI_MakeCylinder,
                                 BRepPrimAPI_MakePrism, BRepPrimAPI_MakeRevol, BRepPrimAPI_MakeSphere)
    from OCP.gp import gp_Ax1, gp_Ax2, gp_Circ, gp_Dir, gp_GTrsf, gp_Pnt, gp_Trsf, gp_Vec
except ImportError:                     # pragma: no cover - only FreeCAD's Python lands here
    pass

CONFUSION = 1e-7
FLT_MAX = 3.4028234663852886e38
LENGTH = (2 * CONFUSION, FLT_MAX)        # quantityRange
LENGTH0 = (0.0, FLT_MAX)                 # quantityRangeZero
ANGLE_U = (0.0, 360.0)                   # angleRangeU
ANGLE_V = (-90.0, 90.0)                  # angleRangeV
TORUS_V = (-180.0, 180.0)                # torusRangeV
SKEW = (-89.99999, 89.99999)             # PrismExtension's angleConstraint
OPERATIONS = ("Subtraction", "Common")


def placement_of(feat, shapes):
    """The primitive's placement as a gp_Trsf in the Body's frame. Today its Placement; with an attachment engine,
    Attacher's placement from the support times AttachmentOffset (FeatureAddSub::execute positions it so)."""
    pos, ypr = feat.placement or ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    r = F._ypr(*ypr)
    t = gp_Trsf()
    t.SetValues(r[0][0], r[0][1], r[0][2], pos[0], r[1][0], r[1][1], r[1][2], pos[1], r[2][0], r[2][1], r[2][2], pos[2])
    return t


def _prism(height, face, first_angle, second_angle):
    """Part::PrismExtension::makePrism: the face swept by the height, skewed by the two angles."""
    return BRepPrimAPI_MakePrism(face, gp_Vec(height * math.tan(math.radians(first_angle)),
                                              height * math.tan(math.radians(second_angle)), height)).Shape()


class Primitive(KwFeature):
    """PartDesign::FeaturePrimitive: a primitive shape, placed, added to or cut from the Body."""
    PRIMITIVE = ""
    ADDITIVE = True
    POS = ()
    RANGES: dict = {}
    COMMON = {"placement": None, "refine": True}

    def normalize(self, key, v):
        if key == "placement":
            if v is None:
                return None
            try:
                if len(v) == 3 and all(isinstance(c, (int, float)) for c in v):
                    return (tuple(float(c) for c in v), (0.0, 0.0, 0.0))
                pos, ypr = v
                return (tuple(float(c) for c in pos), tuple(float(c) for c in ypr))
            except (TypeError, ValueError):
                raise F.FeatureError(f"{self.name}: placement {v!r} is not (x, y, z) or ((x, y, z), "
                                     "(yaw, pitch, roll))") from None
        return super().normalize(key, v)

    def validate(self):
        if not self.ADDITIVE and self.operation not in OPERATIONS:
            raise F.FeatureError(f"{self.name}: operation {self.operation!r} is not one of {', '.join(OPERATIONS)}")
        for k in self.DEFAULTS:
            if k not in ("placement", "refine", "operation") and not isinstance(getattr(self, k), (int, float, str)):
                raise F.FeatureError(f"{self.name}: {k} is {getattr(self, k)!r}, not a number or a PARAMS expression")

    def v(self, key, params):
        """A property's value in mm or degrees, clamped to its range as FreeCAD's property clamps it."""
        x = F.value(getattr(self, key), params, f"{self.name}.{key}")
        lo, hi = self.RANGES.get(key, (-math.inf, math.inf))
        return min(max(x, lo), hi)

    def shape(self, params):
        raise NotImplementedError

    def execute(self, solid, shapes, params):
        """FeaturePrimitive::execute, in the global frame."""
        prim = transformed(self.shape(params), placement_of(self, shapes))
        shapes.setdefault("_addsub", {})[self.name] = (prim, self.ADDITIVE)   # AddSubShape, not refined
        if solid is None:
            if self.ADDITIVE:
                return prim
            raise F.FeatureError("Cannot subtract primitive feature without base feature")
        maker = "fuse" if self.ADDITIVE else "cut" if self.operation == "Subtraction" else "common"
        try:
            result = element_boolean(maker, [solid, prim])
        except F.FeatureError:
            raise F.FeatureError("Failed to perform boolean operation") from None
        if result is None or result.IsNull():
            raise F.FeatureError("Resulting shape is not a solid")
        return F._refine(result) if self.refine else result

    def to_freecad(self, ctx):
        obj = ctx.doc.addObject(self.TYPE_ID, self.name)     # CmdPrimtiveCompAdditive: addObject, then the Body's
        ctx.body.addObject(obj)
        for k in self.DEFAULTS:
            if k in ("placement", "refine", "operation"):
                continue
            prop = "".join(w[:1].upper() + w[1:] for w in k.split("_"))
            if k == "polygon":
                ctx.setint(obj, "Polygon", self.polygon)
            else:
                ctx.setv(obj, prop, getattr(self, k))
        if self.placement is not None:
            (x, y, z), ypr = self.placement
            obj.Placement = ctx.App.Placement(ctx.App.Vector(x, y, z), ctx.App.Rotation(*ypr))
        if not self.ADDITIVE:
            obj.Operation = self.operation
        obj.Refine = self.refine
        return obj


class Box(Primitive):
    PRIMITIVE = "Box"
    DIMS = {"length": 10.0, "width": 10.0, "height": 10.0}
    RANGES = {"length": LENGTH, "width": LENGTH, "height": LENGTH}

    def shape(self, params):
        L, W, H = self.v("length", params), self.v("width", params), self.v("height", params)
        for n, x in (("Length", L), ("Width", W), ("Height", H)):
            if x < CONFUSION:
                raise F.FeatureError(f"{n} of box too small")
        return BRepPrimAPI_MakeBox(L, W, H).Shape()


class Cylinder(Primitive):
    PRIMITIVE = "Cylinder"
    DIMS = {"radius": 10.0, "height": 10.0, "angle": 360.0, "first_angle": 0.0, "second_angle": 0.0}
    RANGES = {"radius": LENGTH, "height": LENGTH, "angle": ANGLE_U, "first_angle": SKEW, "second_angle": SKEW}

    def shape(self, params):
        r, h, a = self.v("radius", params), self.v("height", params), self.v("angle", params)
        if r < CONFUSION:
            raise F.FeatureError("Radius of cylinder too small")
        if h < CONFUSION:
            raise F.FeatureError("Height of cylinder too small")
        if a < CONFUSION:
            raise F.FeatureError("Rotation angle of cylinder too small")
        mk = BRepPrimAPI_MakeCylinder(r, h, math.radians(a))
        return _prism(h, mk.Cylinder().BottomFace(), self.v("first_angle", params), self.v("second_angle", params))


class Sphere(Primitive):
    PRIMITIVE = "Sphere"
    DIMS = {"radius": 5.0, "angle1": -90.0, "angle2": 90.0, "angle3": 360.0}
    RANGES = {"radius": LENGTH, "angle1": ANGLE_V, "angle2": ANGLE_V, "angle3": ANGLE_U}

    def shape(self, params):
        r = self.v("radius", params)
        if r < CONFUSION:
            raise F.FeatureError("Radius of sphere too small")
        return BRepPrimAPI_MakeSphere(r, *(math.radians(self.v(k, params)) for k in ("angle1", "angle2", "angle3"))) \
            .Shape()


class Cone(Primitive):
    PRIMITIVE = "Cone"
    DIMS = {"radius1": 2.0, "radius2": 4.0, "height": 10.0, "angle": 360.0}
    RANGES = {"radius1": LENGTH0, "radius2": LENGTH0, "height": LENGTH, "angle": ANGLE_U}

    def shape(self, params):
        r1, r2, h, a = (self.v(k, params) for k in ("radius1", "radius2", "height", "angle"))
        if r1 < 0.0 or r2 < 0.0:
            raise F.FeatureError("Radius of cone cannot be negative")
        if h < CONFUSION:
            raise F.FeatureError("Height of cone too small")
        if abs(r1 - r2) < CONFUSION:
            return BRepPrimAPI_MakeCylinder(r1, h, math.radians(a)).Shape()
        return BRepPrimAPI_MakeCone(r1, r2, h, math.radians(a)).Shape()


class Ellipsoid(Primitive):
    PRIMITIVE = "Ellipsoid"
    DIMS = {"radius1": 2.0, "radius2": 4.0, "radius3": 0.0, "angle1": -90.0, "angle2": 90.0, "angle3": 360.0}
    RANGES = {"radius1": LENGTH, "radius2": LENGTH, "radius3": LENGTH0, "angle1": ANGLE_V, "angle2": ANGLE_V,
              "angle3": ANGLE_U}

    def shape(self, params):
        r1, r2, r3 = (self.v(k, params) for k in ("radius1", "radius2", "radius3"))
        if r1 < CONFUSION or r2 < CONFUSION:
            raise F.FeatureError("Radius of ellipsoid too small")
        sphere = BRepPrimAPI_MakeSphere(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), r2,
                                        *(math.radians(self.v(k, params)) for k in ("angle1", "angle2", "angle3")))
        mat = gp_GTrsf()
        sy = r3 / r2 if r3 >= CONFUSION else 1.0
        for (i, j), x in {(1, 1): 1.0, (2, 1): 0.0, (3, 1): 0.0, (1, 2): 0.0, (2, 2): sy, (3, 2): 0.0,
                          (1, 3): 0.0, (2, 3): 0.0, (3, 3): r1 / r2}.items():
            mat.SetValue(i, j, x)
        return BRepBuilderAPI_GTransform(sphere.Shape(), mat).Shape()


class Torus(Primitive):
    PRIMITIVE = "Torus"
    DIMS = {"radius1": 10.0, "radius2": 2.0, "angle1": -180.0, "angle2": 180.0, "angle3": 360.0}
    RANGES = {"radius1": LENGTH, "radius2": LENGTH, "angle1": TORUS_V, "angle2": TORUS_V, "angle3": ANGLE_U}

    def shape(self, params):
        r1, r2 = self.v("radius1", params), self.v("radius2", params)
        if r1 < CONFUSION or r2 < CONFUSION:
            raise F.FeatureError("Radius of torus too small")
        a1, a2, a3 = (self.v(k, params) for k in ("angle1", "angle2", "angle3"))
        # TopoShape::makeTorus (solid): the section circle in the XZ plane, revolved about Z
        pos = gp_Pnt(r1, 0, 0)
        circle = gp_Circ()
        circle.SetRadius(r2)
        circle.SetAxis(gp_Ax1(pos, gp_Dir(0, 1, 0)))
        mk_edge = BRepBuilderAPI_MakeEdge(circle, math.radians(a1), math.radians(a2))
        wire = BRepBuilderAPI_MakeWire()
        wire.Add(mk_edge.Edge())
        if a1 > -180.0 or a2 < 180.0:
            v = BRepBuilderAPI_MakeVertex(pos).Vertex()
            wire.Add(BRepBuilderAPI_MakeEdge(v, mk_edge.Vertex1()).Edge())
            wire.Add(BRepBuilderAPI_MakeEdge(v, mk_edge.Vertex2()).Edge())
        face = BRepBuilderAPI_MakeFace(wire.Wire()).Face()
        return BRepPrimAPI_MakeRevol(face, gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), math.radians(a3), True).Shape()


class Prism(Primitive):
    PRIMITIVE = "Prism"
    DIMS = {"polygon": 6, "circumradius": 2.0, "height": 10.0, "first_angle": 0.0, "second_angle": 0.0}
    RANGES = {"circumradius": LENGTH, "height": LENGTH, "first_angle": SKEW, "second_angle": SKEW}

    def shape(self, params):
        n = int(round(F.value(self.polygon, params, f"{self.name}.polygon")))
        R, h = self.v("circumradius", params), self.v("height", params)
        if n < 3:
            raise F.FeatureError("Polygon of prism is invalid, must have 3 or more sides")
        if R < CONFUSION:
            raise F.FeatureError("Circumradius of the polygon, of the prism, is too small")
        if h < CONFUSION:
            raise F.FeatureError("Height of prism is too small")
        a = math.radians(360.0 / n)          # Base::Matrix4D::rotZ, applied to the vertex again and again
        c, s = math.cos(a), math.sin(a)
        poly = BRepBuilderAPI_MakePolygon()
        x, y = R, 0.0
        for _ in range(n):
            poly.Add(gp_Pnt(x, y, 0.0))
            x, y = c * x - s * y, s * x + c * y
        poly.Add(gp_Pnt(x, y, 0.0))
        face = BRepBuilderAPI_MakeFace(poly.Wire()).Face()
        return _prism(h, face, self.v("first_angle", params), self.v("second_angle", params))


class Wedge(Primitive):
    PRIMITIVE = "Wedge"
    DIMS = {"xmin": 0.0, "ymin": 0.0, "zmin": 0.0, "x2min": 2.0, "z2min": 2.0,
            "xmax": 10.0, "ymax": 10.0, "zmax": 10.0, "x2max": 8.0, "z2max": 8.0}

    def shape(self, params):
        xmin, ymin, zmin, x2min, z2min, xmax, ymax, zmax, x2max, z2max = (self.v(k, params) for k in self.DIMS)
        if xmax - xmin < CONFUSION:
            raise F.FeatureError("delta x of wedge too small")
        if ymax - ymin < CONFUSION:
            raise F.FeatureError("delta y of wedge too small")
        if zmax - zmin < CONFUSION:
            raise F.FeatureError("delta z of wedge too small")
        if z2max - z2min < 0:
            raise F.FeatureError("delta z2 of wedge is negative")
        if x2max - x2min < 0:
            raise F.FeatureError("delta x2 of wedge is negative")
        w = BRepPrim_Wedge(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), xmin, ymin, zmin, z2min, x2min,
                           xmax, ymax, zmax, z2max, x2max)
        mk = BRepBuilderAPI_MakeSolid()
        mk.Add(w.Shell())
        return mk.Solid()


SHAPES = (Box, Cylinder, Sphere, Cone, Ellipsoid, Torus, Prism, Wedge)


def _make(shape_cls, additive: bool):
    side = "Additive" if additive else "Subtractive"
    defaults = {**shape_cls.DIMS, **Primitive.COMMON, **({} if additive else {"operation": "Subtraction"})}
    doc = (f"PartDesign::{side}{shape_cls.PRIMITIVE}: a {shape_cls.PRIMITIVE.lower()} "
           f"{'added to' if additive else 'cut from'} the Body.")
    return type(f"{side}{shape_cls.PRIMITIVE}", (shape_cls,), {
        "__doc__": doc, "kind": f"{side}{shape_cls.PRIMITIVE}", "TYPE_ID": f"PartDesign::{side}{shape_cls.PRIMITIVE}",
        "ADDITIVE": additive, "DEFAULTS": defaults,
        "TRANSACTION": f"Make {'additive' if additive else 'subtractive'} {shape_cls.PRIMITIVE}"})


PRIMITIVES = {c.kind: c for c in (_make(s, a) for a in (True, False) for s in SHAPES)}
globals().update(PRIMITIVES)
__all__ = sorted(PRIMITIVES) + ["placement_of", "PRIMITIVES"]

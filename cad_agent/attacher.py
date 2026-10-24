# SPDX-License-Identifier: LGPL-2.0-or-later
#
# This file is not MIT. It re-expresses FreeCAD's attachment engine function by function and keeps FreeCAD's
# licence, the GNU Lesser General Public License (FreeCAD calls it the GNU Library General Public License),
# version 2 or (at your option) any later version. It is distributed here under version 2.1 of that licence,
# which "or any later version" allows; the text is in ../ui/LICENSE.
#
#   Derived from: src/Mod/Part/App/Attacher.cpp (AttachEngine, AttachEngine3D, AttachEnginePlane,
#                 AttachEngineLine, AttachEnginePoint), src/Mod/Part/App/AttachExtension.cpp
#                 (positionBySupport), src/Mod/Part/App/Tools.cpp (getNormal), src/Base/Rotation.cpp and
#                 src/Base/Placement.cpp (the quaternion arithmetic the placements are made with)
#                 FreeCAD (https://github.com/FreeCAD/FreeCAD), commit 3160daf1e2b62b0472854da4848255c6b3ad554c
#
#   Copyright (c) 2015 Victor Titov (DeepSOIC) <vv.titov@gmail.com>
#   Copyright (c) 2011 Juergen Riegel <FreeCAD@juergen-riegel.net> (Base::Rotation, Base::Placement)
#
#   This file is part of the FreeCAD CAx development system.
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
"""FreeCAD's attachment engine: where an attached object goes, from its AttachmentSupport and MapMode.

Every attachable object in FreeCAD (a sketch, a datum plane, line or point, a local coordinate system, a
PartDesign primitive) carries the same five properties of AttachExtension: AttachmentSupport (a list of
references, each an object and one of its elements: ("Pad", "Face6"), ("XY_Plane", "")), MapMode (one of
MODES below), AttachmentOffset (a placement in the attached frame), MapReversed (Flip sides) and
MapPathParameter (where along a curve, 0 to 1). The engine turns them into the object's Placement. This module
is that engine, mode by mode as Attacher.cpp computes it, over the same OCCT calls:

    from cad_agent import attacher as A

    refs = [A.Ref(face, feature_placement)]              # the shapes the support resolves to
    pl = A.attach("Plane", "FlatFace", refs, offset=A.Placement((0, 0, 5)))
    pl.pos, pl.rot.matrix()                               # the placement: origin, then 3x3 (columns x, y, z)

attach() is the one function a feature calls (AttachExtension::positionBySupport): it returns the attached
Placement, or None when the mode is Deactivated (the object keeps its own Placement then), and raises
AttachError, worded as FreeCAD words it, when the references do not fit the mode. suggest() is
AttachEngine::suggestMapModes, what the Attachment panel lists for a set of references; shape_type() is
AttachEngine::getShapeType. The engines are FreeCAD's AttacherType: "3D" (Attacher::AttachEngine3D, a local
coordinate system), "Plane" (AttachEnginePlane, sketches and datum planes; the same modes as 3D), "Line"
(AttachEngineLine, datum lines) and "Point" (AttachEnginePoint, datum points).

A Ref is what Feature::getTopoShape gives the engine for one reference: the shape (global coordinates, the
element itself when an element is named, else the object's whole shape, which may be None for an empty
object), the object's global Placement (App::GeoFeature::getGlobalPlacement), whether a whole object is
referenced (no element: the rtFlagHasPlacement bit) and whether the object is an App::Plane (MidPoint's special
case). The caller resolves names to Refs; cad_agent/feature_attach.py does that for a Body.

Placement and Rotation are Base::Placement and Base::Rotation, quaternions multiplied as FreeCAD multiplies
them, so the numbers agree with FreeCAD's to the last bits (tests/golden/attach holds them to freecadcmd's).
"""
from __future__ import annotations

import math

try:                                    # the kernel; FreeCAD's Python reads the vocabulary without it
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.BRepGProp import BRepGProp
    from OCP.BRepIntCurveSurface import BRepIntCurveSurface_Inter
    from OCP.BRepLProp import BRepLProp_SLProps
    from OCP.CSLib import CSLib, CSLib_NormalStatus
    from OCP.Geom import Geom_Line, Geom_Plane
    from OCP.GeomAPI import GeomAPI_IntSS, GeomAPI_ProjectPointOnCurve, GeomAPI_ProjectPointOnSurf
    from OCP.GeomAbs import (GeomAbs_Circle, GeomAbs_Cone, GeomAbs_Cylinder, GeomAbs_Ellipse,
                             GeomAbs_Hyperbola, GeomAbs_Line, GeomAbs_Parabola, GeomAbs_Plane, GeomAbs_Sphere,
                             GeomAbs_SurfaceOfRevolution, GeomAbs_Torus)
    from OCP.GeomAdaptor import GeomAdaptor, GeomAdaptor_Curve
    from OCP.GeomLib import GeomLib_IsPlanarSurface
    from OCP.GProp import GProp_GProps, GProp_PGProps
    from OCP.ShapeExtend import ShapeExtend_Explorer
    from OCP.TopAbs import (TopAbs_COMPOUND, TopAbs_COMPSOLID, TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED,
                            TopAbs_SHAPE, TopAbs_SHELL, TopAbs_SOLID, TopAbs_VERTEX, TopAbs_WIRE)
    from OCP.TopoDS import TopoDS, TopoDS_Iterator
    from OCP.gp import gp_Ax1, gp_Ax3, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
except ImportError:                     # pragma: no cover - only FreeCAD's Python lands here
    pass

CONFUSION = 1e-7                    # Precision::Confusion()
SQUARE_CONFUSION = CONFUSION * CONFUSION
PLANAR_PRECISION = 2.0e-7           # AttachEnginePlane::planarPrecision(), what Part2DObject (a sketch) uses


class AttachError(ValueError):
    """The references do not fit the mode, in FreeCAD's words (Base::ValueError, AttachEngineException)."""


# ── Base::Rotation and Base::Placement ────────────────────────────────────────────────────────────────

class Rotation:
    """Base::Rotation: a unit quaternion (x, y, z, w)."""
    __slots__ = ("q",)

    def __init__(self, q=(0.0, 0.0, 0.0, 1.0), normalize: bool = True):
        x, y, z, w = (float(c) for c in q)
        if normalize:
            n = math.sqrt(x * x + y * y + z * z + w * w)
            if n > 0.0:
                x, y, z, w = x / n, y / n, z / n, w / n
        self.q = (x, y, z, w)

    @classmethod
    def from_axis_angle(cls, axis, angle):
        """Rotation::setValue(axis, angle), the angle in radians."""
        the = angle - math.floor(angle / (2.0 * math.pi)) * (2.0 * math.pi)
        n = math.sqrt(sum(c * c for c in axis))
        ax = tuple(c / n for c in axis) if n > 0.0 else (0.0, 0.0, 1.0)
        s = math.sin(the / 2.0)
        r = cls.__new__(cls)
        r.q = (ax[0] * s, ax[1] * s, ax[2] * s, math.cos(the / 2.0))   # setValue(axis, angle) does not normalize
        return r

    @classmethod
    def from_vectors(cls, frm, to):
        """Rotation(rotateFrom, rotateTo)."""
        u = _unit(frm)
        v = _unit(to)
        dot = _dot(u, v)
        w = _cross(u, v)
        wlen = _norm(w)
        if wlen == 0.0:
            if dot > 0.0:
                return cls((0.0, 0.0, 0.0, 1.0))
            t = _cross(u, (1.0, 0.0, 0.0))
            if _norm(t) < 1e-12:                    # Vector3d::epsilon()
                t = _cross(u, (0.0, 1.0, 0.0))
            return cls((t[0], t[1], t[2], 0.0))
        return cls.from_axis_angle(w, math.acos(dot))

    @classmethod
    def from_normal(cls, normal):
        """Rotation::fromNormalVector: Z turned onto normal."""
        return cls.from_vectors((0.0, 0.0, 1.0), normal)

    @classmethod
    def from_ypr(cls, yaw, pitch, roll):
        """Rotation::setYawPitchRoll, in degrees."""
        y, p, r = (math.radians(a) for a in (yaw, pitch, roll))
        c1, s1 = math.cos(y / 2.0), math.sin(y / 2.0)
        c2, s2 = math.cos(p / 2.0), math.sin(p / 2.0)
        c3, s3 = math.cos(r / 2.0), math.sin(r / 2.0)
        return cls((c1 * c2 * s3 - s1 * s2 * c3, c1 * s2 * c3 + s1 * c2 * s3,
                    s1 * c2 * c3 - c1 * s2 * s3, c1 * c2 * c3 + s1 * s2 * s3))

    @classmethod
    def from_matrix(cls, m):
        """Rotation::setValue(Matrix4D): m is a 3x3 row matrix; its rotation part (Matrix4D::decompose, which
        for the orthonormal matrices placements are made of is their Gram-Schmidt) to a quaternion."""
        c0 = [m[i][0] for i in range(3)]
        c1 = [m[i][1] for i in range(3)]
        d0 = _unit(c0)
        cross = _unit(_cross(d0, c1))
        d1 = _cross(cross, d0)
        cols = (d0, d1, cross)
        mc = [[cols[j][i] for j in range(3)] for i in range(3)]
        trace = mc[0][0] + mc[1][1] + mc[2][2]
        q = [0.0, 0.0, 0.0, 0.0]
        if trace > 0.0:
            s = math.sqrt(1.0 + trace)
            q[3] = 0.5 * s
            s = 0.5 / s
            q[0] = (mc[2][1] - mc[1][2]) * s
            q[1] = (mc[0][2] - mc[2][0]) * s
            q[2] = (mc[1][0] - mc[0][1]) * s
        else:
            i = 0
            if mc[1][1] > mc[0][0]:
                i = 1
            if mc[2][2] > mc[i][i]:
                i = 2
            j, k = (i + 1) % 3, (i + 2) % 3
            s = math.sqrt((mc[i][i] - (mc[j][j] + mc[k][k])) + 1.0)
            q[i] = s * 0.5
            s = 0.5 / s
            q[3] = (mc[k][j] - mc[j][k]) * s
            q[j] = (mc[j][i] + mc[i][j]) * s
            q[k] = (mc[k][i] + mc[i][k]) * s
        r = cls.__new__(cls)
        r.q = tuple(q)                              # setValue(Matrix4D) does not normalize either
        return r

    @classmethod
    def by_axes(cls, xdir, ydir, zdir, order: str = "ZXY"):
        """Rotation::makeRotationByAxes: the directions given, the first of order kept exactly, the second
        made perpendicular to it, the third their cross product."""
        tol = CONFUSION
        o = [ord(c) - ord("X") for c in order]
        dirs = [tuple(xdir), tuple(ydir), tuple(zdir)]

        def drop(index):
            if index == 0:
                o[0], o[1], o[2] = o[1], o[2], o[0]
            elif index == 1:
                o[1], o[2] = o[2], o[1]

        main = None
        for i in range(3):
            main = dirs[o[0]]
            if _norm(main) > tol:
                break
            drop(0)
            if i == 2:
                raise AttachError("makeRotationByAxes: all directions supplied are zero")
        main = _unit(main)
        hint = (0.0, 0.0, 0.0)
        for i in range(2):
            hint = dirs[o[1]]
            if _norm(_cross(hint, main)) > tol:
                break
            drop(1)
            if i == 1:
                hint = (0.0, 0.0, 0.0)
        if _norm(hint) == 0.0:
            if o[0] == 0:
                o[1], o[2] = 2, 1
                hint = (0.0, 0.0, 1.0)
                if _norm(_cross(hint, main)) <= tol:
                    hint, o[1], o[2] = (0.0, 1.0, 0.0), 1, 2
            elif o[0] == 1:
                o[1], o[2] = 2, 0
                hint = (0.0, 0.0, 1.0) if main[2] > -tol else (0.0, 0.0, -1.0)
                if _norm(_cross(hint, main)) <= tol:
                    hint, o[1], o[2] = (1.0, 0.0, 0.0), 0, 2
            else:
                o[1], o[2] = 1, 0
                hint = (0.0, 0.0, 1.0)
                if _norm(_cross(hint, main)) <= tol:
                    hint, o[1], o[2] = (1.0, 0.0, 0.0), 0, 1
        hint = _unit(hint)
        last = _unit(_cross(main, hint))
        hint = _unit(_cross(last, main))
        final = [None, None, None]
        final[o[0]], final[o[1]], final[o[2]] = main, hint, last
        if _dot(_cross(final[0], final[1]), final[2]) < 0.0:
            final[o[2]] = tuple(-c for c in final[o[2]])
        return cls.from_matrix([[final[j][i] for j in range(3)] for i in range(3)])

    def __mul__(self, other: "Rotation") -> "Rotation":
        """Rotation::multRight: self then other in self's frame."""
        x0, y0, z0, w0 = self.q
        x1, y1, z1, w1 = other.q
        return Rotation((w0 * x1 + x0 * w1 + y0 * z1 - z0 * y1,
                         w0 * y1 - x0 * z1 + y0 * w1 + z0 * x1,
                         w0 * z1 + x0 * y1 - y0 * x1 + z0 * w1,
                         w0 * w1 - x0 * x1 - y0 * y1 - z0 * z1))

    def inverse(self) -> "Rotation":
        x, y, z, w = self.q
        r = Rotation.__new__(Rotation)
        r.q = (-x, -y, -z, w)
        return r

    def mult_vec(self, v):
        x, y, z, w = self.q
        x2, y2, z2, w2 = x * x, y * y, z * z, w * w
        return ((x2 + w2 - y2 - z2) * v[0] + 2.0 * (x * y - z * w) * v[1] + 2.0 * (x * z + y * w) * v[2],
                2.0 * (x * y + z * w) * v[0] + (w2 - x2 + y2 - z2) * v[1] + 2.0 * (y * z - x * w) * v[2],
                2.0 * (x * z - y * w) * v[0] + 2.0 * (x * w + y * z) * v[1] + (w2 - x2 - y2 + z2) * v[2])

    def matrix(self):
        """Rotation::getValue(Matrix4D): the 3x3 row matrix, its columns the rotated x, y and z axes."""
        x, y, z, w = self.q
        n = math.sqrt(x * x + y * y + z * z + w * w)
        x, y, z, w = x / n, y / n, z / n, w / n
        return ((1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)),
                (2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)),
                (2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)))

    def ypr(self):
        """Rotation::getYawPitchRoll, in degrees."""
        q0, q1, q2, q3 = self.q
        q00, q11, q22, q33 = q0 * q0, q1 * q1, q2 * q2, q3 * q3
        q01, q02, q03, q12, q13, q23 = q0 * q1, q0 * q2, q0 * q3, q1 * q2, q1 * q3, q2 * q3
        qd2 = 2.0 * (q13 - q02)
        tol = 16 * 2.220446049250313e-16
        if abs(qd2 - 1.0) <= tol:
            y, p, r = 0.0, math.pi / 2.0, 2.0 * math.atan2(q0, q3)
        elif abs(qd2 + 1.0) <= tol:
            y, p, r = 0.0, -math.pi / 2.0, 2.0 * math.atan2(q0, q3)
        else:
            y = math.atan2(2.0 * (q01 + q23), (q00 + q33) - (q11 + q22))
            p = math.pi / 2.0 if qd2 > 1.0 else -math.pi / 2.0 if qd2 < -1.0 else math.asin(qd2)
            r = math.atan2(2.0 * (q12 + q03), (q22 + q33) - (q00 + q11))
        return math.degrees(y), math.degrees(p), math.degrees(r)

    def __repr__(self):
        return f"Rotation({self.q!r})"


class Placement:
    """Base::Placement: a position and a Rotation; p1 * p2 is p2 in p1's frame."""
    __slots__ = ("pos", "rot")

    def __init__(self, pos=(0.0, 0.0, 0.0), rot: Rotation | None = None):
        self.pos = tuple(float(c) for c in pos)
        self.rot = rot if rot is not None else Rotation()

    @classmethod
    def from_trsf(cls, t: gp_Trsf) -> "Placement":
        """Placement(Matrix4D) of TopoShape::convertToMatrix(trsf)."""
        m = [[t.Value(i, j) for j in range(1, 4)] for i in range(1, 4)]
        return cls((t.Value(1, 4), t.Value(2, 4), t.Value(3, 4)), Rotation.from_matrix(m))

    @classmethod
    def from_offset(cls, off) -> "Placement":
        """A part file's attachment_offset: None, (x, y, z), or ((x, y, z), (yaw, pitch, roll)) in degrees, as
        App.Placement(App.Vector(x, y, z), App.Rotation(yaw, pitch, roll))."""
        if off is None:
            return cls()
        if isinstance(off, Placement):
            return off
        if len(off) == 3 and all(isinstance(c, (int, float)) for c in off):
            return cls(off)
        pos, ypr = off
        return cls(pos, Rotation.from_ypr(*ypr))

    def __mul__(self, other: "Placement") -> "Placement":
        rp = self.rot.mult_vec(other.pos)
        return Placement((self.pos[0] + rp[0], self.pos[1] + rp[1], self.pos[2] + rp[2]), self.rot * other.rot)

    def inverse(self) -> "Placement":
        r = self.rot.inverse()
        p = r.mult_vec(self.pos)
        return Placement((-p[0], -p[1], -p[2]), r)

    def mult_vec(self, v):
        r = self.rot.mult_vec(v)
        return (r[0] + self.pos[0], r[1] + self.pos[1], r[2] + self.pos[2])

    def trsf(self) -> gp_Trsf:
        """The placement as a gp_Trsf (TopoShape::convertTogpTrsf of toMatrix())."""
        m = self.rot.matrix()
        t = gp_Trsf()
        t.SetValues(m[0][0], m[0][1], m[0][2], self.pos[0], m[1][0], m[1][1], m[1][2], self.pos[1],
                    m[2][0], m[2][1], m[2][2], self.pos[2])
        return t

    def as_dict(self) -> dict:
        """For JSON: position, quaternion (x, y, z, w), the 3x3 matrix and yaw-pitch-roll in degrees."""
        return {"position": list(self.pos), "rotation": list(self.rot.q),
                "matrix": [list(r) for r in self.rot.matrix()], "ypr": list(self.rot.ypr())}

    def __repr__(self):
        y, p, r = self.rot.ypr()
        return f"Placement(pos={self.pos!r}, ypr=({y:.9g}, {p:.9g}, {r:.9g}))"


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def _unit(a):
    n = _norm(a)
    return (a[0] / n, a[1] / n, a[2] / n) if n > 0.0 else tuple(float(c) for c in a)


def _v(p) -> tuple:
    return (p.X(), p.Y(), p.Z())


# ── modes and reference types (Attacher.h's eMapMode and eRefType) ─────────────────────────────────────

MODES = (
    "Deactivated", "Translate", "ObjectXY", "ObjectXZ", "ObjectYZ", "FlatFace", "TangentPlane",
    "NormalToEdge", "FrenetNB", "FrenetTN", "FrenetTB", "Concentric", "SectionOfRevolution",
    "ThreePointsPlane", "ThreePointsNormal", "Folding",
    "ObjectX", "ObjectY", "ObjectZ", "AxisOfCurvature", "Directrix1", "Directrix2", "Asymptote1",
    "Asymptote2", "Tangent", "Normal", "Binormal", "TangentU", "TangentV", "TwoPointLine",
    "IntersectionLine", "ProximityLine",
    "ObjectOrigin", "Focus1", "Focus2", "OnEdge", "CenterOfCurvature", "CenterOfMass", "IntersectionPoint",
    "Vertex", "ProximityPoint1", "ProximityPoint2",
    "AxisOfInertia1", "AxisOfInertia2", "AxisOfInertia3",
    "InertialCS",
    "FaceNormal",
    "OZX", "OZY", "OXY", "OXZ", "OYZ", "OYX",
    "ParallelPlane", "MidPoint", "MidPlane",
)
M = {name: i for i, name in enumerate(MODES)}      # eMapMode by name

# eRefType, and AttachEngine::eRefTypeStrings (the Python names)
(rtAnything, rtVertex, rtEdge, rtFace, rtLine, rtCurve, rtCircle, rtConic, rtEllipse, rtParabola,
 rtHyperbola, rtFlatFace, rtSphericalFace, rtSurfaceRev, rtCylindricalFace, rtToroidalFace, rtConicalFace,
 rtPart, rtSolid, rtWire) = range(20)
rtFlagHasPlacement = 0x0100
REF_TYPES = ("Any", "Vertex", "Edge", "Face", "Line", "Curve", "Circle", "Conic", "Ellipse", "Parabola",
             "Hyperbola", "Plane", "Sphere", "Revolve", "Cylinder", "Torus", "Cone", "Object", "Solid", "Wire")
ENGINES = ("3D", "Plane", "Line", "Point")
# AttacherType, as FreeCAD writes it
ENGINE_TYPES = {"3D": "Attacher::AttachEngine3D", "Plane": "Attacher::AttachEnginePlane",
                "Line": "Attacher::AttachEngineLine", "Point": "Attacher::AttachEnginePoint"}


def ref_type_name(t: int) -> str:
    """AttachEngine::getRefTypeName: "Plane", "Object|Placement", ..."""
    s = REF_TYPES[t & 0xFF]
    return s + "|Placement" if t & rtFlagHasPlacement else s


def ref_type_by_name(name: str) -> int:
    base, _, flags = name.partition("|")
    t = REF_TYPES.index(base)
    if flags == "Placement":
        return t | rtFlagHasPlacement
    if flags:
        raise AttachError(f"RefType flag not recognized: {flags}")
    return t


def downgrade(t: int) -> int:
    """AttachEngine::downgradeType."""
    t &= rtFlagHasPlacement - 1
    if t in (rtVertex, rtEdge, rtFace, rtAnything, rtPart):
        return rtAnything
    if t in (rtLine, rtCurve):
        return rtEdge
    if t in (rtConic, rtCircle):
        return rtCurve
    if t in (rtEllipse, rtParabola, rtHyperbola):
        return rtConic
    if t in (rtFlatFace, rtSphericalFace, rtSurfaceRev):
        return rtFace
    if t in (rtCylindricalFace, rtToroidalFace, rtConicalFace):
        return rtSurfaceRev
    if t in (rtSolid, rtWire):
        return rtPart
    raise AttachError("AttachEngine::downgradeType: unknown type")


def type_rank(t: int) -> int:
    t &= rtFlagHasPlacement - 1
    rank = 0
    while t != rtAnything:
        t = downgrade(t)
        rank += 1
    return rank


def is_shape_of_type(shape_type: int, requirement: int) -> int:
    """AttachEngine::isShapeOfType: -1 no, 0 the topology fits but not the geometry, 1 and up yes (the higher
    the more specific)."""
    if requirement & rtFlagHasPlacement and not shape_type & rtFlagHasPlacement:
        return -1
    shape_type &= rtFlagHasPlacement - 1
    requirement &= rtFlagHasPlacement - 1
    if requirement == rtAnything:
        return 1
    rank = type_rank(requirement)
    d = shape_type
    while d != rtAnything:
        if d == requirement:
            return rank
        d = downgrade(d)
    requirement = downgrade(requirement)
    if requirement != rtAnything:
        d = shape_type
        while d != rtAnything:
            if d == requirement:
                return 0
            d = downgrade(d)
    return -1


def _refs_3d() -> list:
    """AttachEngine3D's constructor: modeRefTypes, in the order it fills them (suggest's ties go to the
    first)."""
    mr = [[] for _ in MODES]
    P = rtFlagHasPlacement
    mr[M["Translate"]].append((rtVertex,))
    ss = [(rtAnything | P,), (rtConic,)]
    for m in ("ObjectXY", "ObjectXZ", "ObjectYZ"):
        mr[M[m]] = list(ss)
    mr[M["ParallelPlane"]].append((rtFlatFace | P, rtVertex))
    mr[M["ParallelPlane"]].append((rtAnything | P, rtVertex))
    for n in range(1, 5):
        mr[M["InertialCS"]].append((rtAnything,) * n)
    mr[M["FlatFace"]].append((rtFlatFace,))
    mr[M["MidPlane"]].append((rtFlatFace, rtFlatFace))
    mr[M["TangentPlane"]].append((rtFace, rtVertex))
    mr[M["TangentPlane"]].append((rtVertex, rtFace))
    mr[M["NormalToEdge"]].append((rtEdge,))
    for m in ("FrenetNB", "FrenetTN", "FrenetTB", "SectionOfRevolution", "Concentric"):
        mr[M[m]].append((rtCurve,))
    for m in ("SectionOfRevolution", "Concentric"):
        mr[M[m]].append((rtCircle,))
    mr[M["NormalToEdge"]].append((rtEdge, rtVertex))
    mr[M["NormalToEdge"]].append((rtVertex, rtEdge))
    for m in ("FrenetNB", "FrenetTN", "FrenetTB", "SectionOfRevolution", "Concentric"):
        mr[M[m]].append((rtCurve, rtVertex))
    for m in ("SectionOfRevolution", "Concentric"):
        mr[M[m]].append((rtCircle, rtVertex))
    for m in ("FrenetNB", "FrenetTN", "FrenetTB", "SectionOfRevolution", "Concentric"):
        mr[M[m]].append((rtVertex, rtCurve))
    for m in ("SectionOfRevolution", "Concentric"):
        mr[M[m]].append((rtVertex, rtCircle))
    for s in ((rtVertex, rtVertex, rtVertex), (rtLine, rtVertex), (rtVertex, rtLine), (rtLine, rtLine)):
        mr[M["ThreePointsPlane"]].append(s)
        mr[M["ThreePointsNormal"]].append(s)
    for m in ("OZX", "OZY", "OXY", "OXZ", "OYZ", "OYX"):
        mr[M[m]] += [(rtVertex, rtVertex, rtVertex), (rtVertex, rtVertex, rtLine), (rtVertex, rtLine, rtVertex),
                     (rtVertex, rtLine, rtLine), (rtVertex, rtVertex), (rtVertex, rtLine)]
    mr[M["Folding"]].append((rtLine, rtLine, rtLine, rtLine))
    return mr


def _refs_line(r3) -> list:
    mr = [[] for _ in MODES]
    mr[M["ObjectX"]] = list(r3[M["ObjectYZ"]])
    mr[M["ObjectY"]] = list(r3[M["ObjectXZ"]])
    mr[M["ObjectZ"]] = list(r3[M["ObjectXY"]])
    mr[M["AxisOfCurvature"]] = list(r3[M["SectionOfRevolution"]])
    mr[M["Binormal"]] = list(r3[M["FrenetTN"]])
    mr[M["Normal"]] = list(r3[M["FrenetTB"]])
    mr[M["Tangent"]] = list(r3[M["NormalToEdge"]])
    mr[M["TwoPointLine"]] += [(rtVertex, rtVertex), (rtLine,)]
    mr[M["Asymptote1"]].append((rtHyperbola,))
    mr[M["Asymptote2"]].append((rtHyperbola,))
    mr[M["Directrix1"]].append((rtConic,))
    mr[M["Directrix2"]] += [(rtEllipse,), (rtHyperbola,)]
    mr[M["ProximityLine"]].append((rtAnything, rtAnything))
    for n in range(1, 5):
        mr[M["AxisOfInertia1"]].append((rtAnything,) * n)
    mr[M["AxisOfInertia2"]] = list(mr[M["AxisOfInertia1"]])
    mr[M["AxisOfInertia3"]] = list(mr[M["AxisOfInertia1"]])
    mr[M["FaceNormal"]] = list(r3[M["TangentPlane"]])
    mr[M["IntersectionLine"]].append((rtFace, rtFace))
    return mr


def _refs_point(r3) -> list:
    mr = [[] for _ in MODES]
    mr[M["ObjectOrigin"]] = list(r3[M["ObjectXY"]])
    mr[M["CenterOfCurvature"]] = list(r3[M["SectionOfRevolution"]])
    mr[M["OnEdge"]] = list(r3[M["NormalToEdge"]])
    mr[M["Vertex"]] += [(rtVertex,), (rtLine,)]
    mr[M["Focus1"]].append((rtConic,))
    mr[M["Focus2"]] += [(rtEllipse,), (rtHyperbola,)]
    mr[M["ProximityPoint1"]].append((rtAnything, rtAnything))
    mr[M["ProximityPoint2"]].append((rtAnything, rtAnything))
    for n in range(1, 5):
        mr[M["CenterOfMass"]].append((rtAnything,) * n)
    return mr


_R3 = _refs_3d()
MODE_REFS = {"3D": _R3, "Plane": _R3, "Line": _refs_line(_R3), "Point": _refs_point(_R3)}


def modes(engine: str) -> list[str]:
    """The modes an engine has (EnableAllSupportedModes: those with reference lists), and Deactivated."""
    return ["Deactivated"] + [MODES[i] for i, r in enumerate(MODE_REFS[_engine(engine)]) if r]


def _engine(engine: str) -> str:
    if engine not in MODE_REFS:
        raise AttachError(f"attacher type {engine!r} is not one of {', '.join(ENGINES)}")
    return engine


def suggest(engine: str, types) -> dict:
    """AttachEngine::suggestMapModes for references of the given types (ints, or names as ref_type_name):
    {"message": "OK" | "NoModesFit" | "IncompatibleGeometry", "best": mode, "all": [modes], "reachable":
    {mode: [[type names to add], ...]}, "hints": [type names], "types": [type names]}."""
    ts = [ref_type_by_name(t) if isinstance(t, str) else int(t) for t in types]
    best_score, best, message = -1, "Deactivated", "NoModesFit"
    out_all: list = []
    reachable: dict = {}
    hints: set = set()
    for i, lists in enumerate(MODE_REFS[_engine(engine)]):
        for s in lists:
            score = 1
            for k in range(min(len(s), len(ts))):
                match = is_shape_of_type(ts[k], s[k])
                if match == -1:
                    score = -1
                    break
                if match == 0:
                    score = 0
                elif match >= 2 and score > 0:
                    score += match
            if score > 0 and len(s) > len(ts):
                hints.add(s[len(ts)])
                reachable.setdefault(MODES[i], []).append([ref_type_name(t) for t in s[len(ts):]])
            if len(s) != len(ts):
                score = -1
            if score > -1 and score > best_score:
                best_score, best = score, MODES[i]
                message = "OK" if score > 0 else "IncompatibleGeometry"
            if score > 0 and (not out_all or out_all[-1] != MODES[i]):
                out_all.append(MODES[i])
    for m in out_all:
        reachable.pop(m, None)
    return {"message": message, "best": best, "all": out_all, "reachable": reachable,
            "hints": [ref_type_name(t) for t in sorted(hints)], "types": [ref_type_name(t) for t in ts]}


# ── references ─────────────────────────────────────────────────────────────────────────────────────────

class Ref:
    """One resolved reference: shape (TopoDS_Shape in global coordinates, None for an object with no shape),
    placement (the object's global Placement), whole (no element named: the object itself), plane (the
    object is an App::Plane: an origin plane)."""
    __slots__ = ("shape", "placement", "whole", "plane")

    def __init__(self, shape, placement: Placement | None = None, whole: bool = False, plane: bool = False):
        self.shape = shape
        self.placement = placement if placement is not None else Placement()
        self.whole = bool(whole)
        self.plane = bool(plane)

    def type(self) -> int:
        """readLinks' type of this reference."""
        if self.shape is None or self.shape.IsNull():
            return rtPart | rtFlagHasPlacement
        t = shape_type(self.shape)
        return t | rtFlagHasPlacement if self.whole else t


def shape_type(sh) -> int:
    """AttachEngine::getShapeType (never sets rtFlagHasPlacement)."""
    if sh is None or sh.IsNull():
        return rtAnything
    st = sh.ShapeType()
    if st == TopAbs_SHAPE:
        return rtAnything
    if st == TopAbs_SOLID:
        return rtSolid
    if st == TopAbs_COMPOUND:
        it = TopoDS_Iterator(sh, False, False)
        if not it.More():
            return rtAnything
        first = it.Value()
        it.Next()
        return rtAnything if it.More() else shape_type(first)
    if st in (TopAbs_COMPSOLID, TopAbs_SHELL):
        return rtAnything
    if st == TopAbs_FACE:
        t = BRepAdaptor_Surface(TopoDS.Face(sh), False).GetType()
        return {GeomAbs_Plane: rtFlatFace, GeomAbs_Cylinder: rtCylindricalFace, GeomAbs_Cone: rtConicalFace,
                GeomAbs_Sphere: rtSphericalFace, GeomAbs_Torus: rtToroidalFace,
                GeomAbs_SurfaceOfRevolution: rtSurfaceRev}.get(t, rtFace)
    if st == TopAbs_EDGE:
        t = BRepAdaptor_Curve(TopoDS.Edge(sh)).GetType()
        return {GeomAbs_Line: rtLine, GeomAbs_Circle: rtCircle, GeomAbs_Ellipse: rtEllipse,
                GeomAbs_Hyperbola: rtHyperbola, GeomAbs_Parabola: rtParabola}.get(t, rtCurve)
    if st == TopAbs_WIRE:
        return rtWire
    if st == TopAbs_VERTEX:
        return rtVertex
    raise AttachError("AttachEngine::getShapeType: unexpected TopoDS_Shape::ShapeType")


def _single(sh):
    """extractSubShape: a compound of one shape is that shape."""
    while sh is not None and not sh.IsNull() and sh.ShapeType() == TopAbs_COMPOUND:
        it = TopoDS_Iterator(sh)
        if not it.More():
            break
        first = it.Value()
        it.Next()
        if it.More():
            break
        sh = first
    return sh


def _vertex(sh, where):
    if sh is None or sh.IsNull() or sh.ShapeType() != TopAbs_VERTEX:
        raise AttachError(f"Null vertex in {where}!")
    return BRep_Tool.Pnt_s(TopoDS.Vertex(sh))


def _edge(sh, where):
    if sh is None or sh.IsNull() or sh.ShapeType() != TopAbs_EDGE:
        raise AttachError(f"Null edge in {where}!")
    return TopoDS.Edge(sh)


def _face(sh, what="face", where="AttachEngine3D::calculateAttachedPlacement()"):
    if sh is None or sh.IsNull() or sh.ShapeType() != TopAbs_FACE:
        raise AttachError(f"Null {what} in {where}!")
    return TopoDS.Face(sh)


def _is_inf(u) -> bool:
    return abs(u) >= 2e100                     # Precision::IsInfinite: |u| >= 0.5 * Precision::Infinite()


def _planar_face_info(sh, precision):
    """getPlanarFaceInfo: (gp_Pln, normal gp_Dir, centre gp_Pnt)."""
    face = TopoDS.Face(sh) if sh is not None and not sh.IsNull() and sh.ShapeType() == TopAbs_FACE else None
    reverse = False
    if face is None:
        raise AttachError("No planar face in AttachEngine3D::calculateAttachedPlacement()!")
    adapt = BRepAdaptor_Surface(face)
    if adapt.GetType() == GeomAbs_Plane:
        plane = adapt.Plane()
    else:
        check = GeomLib_IsPlanarSurface(BRep_Tool.Surface_s(face), precision)
        if not check.IsPlanar():
            raise AttachError("No planar face in AttachEngine3D::calculateAttachedPlacement()!")
        plane = check.Plan()
    reverse = face.Orientation() == TopAbs_REVERSED
    if not plane.Direct():
        plane.UReverse()
        reverse = not reverse
    normal = plane.Axis()
    if reverse:
        normal.Reverse()
    center = plane.Location()
    if not face.Infinite():
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, props)
        center = props.CentreOfMass()
    return plane, normal.Direction(), center


def _mid_plane(f1, f2):
    """getMidPlane: (normal gp_Vec, offset) of the dihedral bisector that separates the two centres."""
    n1, n2 = gp_Vec(f1[1]), gp_Vec(f2[1])
    o1 = n1.Dot(gp_Vec(f1[2].XYZ()))
    o2 = n2.Dot(gp_Vec(f2[2].XYZ()))
    s = (n1.Added(n2), o1 + o2)
    d = (n1.Subtracted(n2), o1 - o2)
    if s[0].SquareMagnitude() < SQUARE_CONFUSION:
        return d
    if d[0].SquareMagnitude() < SQUARE_CONFUSION:
        return s
    cd = gp_Vec(f1[2], f2[2])
    sep = cd.Dot(n1) * cd.Dot(n2)
    if sep > 0.0:
        return s
    if sep < 0.0:
        return d
    return s if s[0].SquareMagnitude() >= d[0].SquareMagnitude() else d


def _inertial_props(shapes):
    """AttachEngine::getInertialPropsOfShape."""
    seq = []
    for sh in shapes:
        if sh is None or sh.IsNull():
            continue
        hs = ShapeExtend_Explorer().SeqFromCompound(sh, True)
        seq += [hs.Value(i) for i in range(1, hs.Length() + 1)]
    if not seq:
        raise AttachError("AttachEngine::getInertialPropsOfShape: no geometry provided")
    t0 = seq[0].ShapeType()
    if t0 == TopAbs_VERTEX:
        g = GProp_PGProps()
        for sh in seq:
            if sh.ShapeType() != TopAbs_VERTEX:
                raise AttachError("AttachEngine::getInertialPropsOfShape: provided shapes are incompatible "
                                  "(not only vertices)")
            g.AddPoint(BRep_Tool.Pnt_s(TopoDS.Vertex(sh)))
        return g
    kinds = {TopAbs_EDGE: ((TopAbs_EDGE, TopAbs_WIRE), BRepGProp.LinearProperties_s, "edges/wires"),
             TopAbs_WIRE: ((TopAbs_EDGE, TopAbs_WIRE), BRepGProp.LinearProperties_s, "edges/wires"),
             TopAbs_FACE: ((TopAbs_FACE, TopAbs_SHELL), BRepGProp.SurfaceProperties_s, "faces/shells"),
             TopAbs_SHELL: ((TopAbs_FACE, TopAbs_SHELL), BRepGProp.SurfaceProperties_s, "faces/shells"),
             TopAbs_SOLID: ((TopAbs_SOLID, TopAbs_COMPSOLID), BRepGProp.VolumeProperties_s, "solids/compsolids"),
             TopAbs_COMPSOLID: ((TopAbs_SOLID, TopAbs_COMPSOLID), BRepGProp.VolumeProperties_s,
                                "solids/compsolids")}
    if t0 not in kinds:
        raise AttachError("AttachEngine::getInertialPropsOfShape: unexpected shape type")
    ok, fn, what = kinds[t0]
    acc = GProp_GProps()
    for sh in seq:
        if sh.ShapeType() not in ok:
            raise AttachError(f"AttachEngine::getInertialPropsOfShape: provided shapes are incompatible "
                              f"(not only {what})")
        if sh.Infinite():
            raise AttachError("AttachEngine::getInertialPropsOfShape: infinite shape provided")
        g = GProp_GProps()
        fn(sh, g)
        acc.Add(g)
    return acc


def _normal_by_props(prop, tol):
    """Tools.cpp's getNormalBySLProp: the props' normal, or CSLib::Normal's from the second derivatives at a
    singular point. (OCP does not hand back CSLib's status, so the flip FreeCAD makes at the far u or v bound
    of a singular point is not made: only the apex of a cone or a sphere's pole at that bound would differ.)"""
    if prop.D1U().Magnitude() > tol and prop.D1V().Magnitude() > tol and prop.IsNormalDefined():
        return prop.Normal(), True
    d = gp_Dir(0, 0, 1)
    try:
        res = CSLib.Normal_s(prop.D1U(), prop.D1V(), prop.D2U(), prop.D2V(), prop.DUV(), tol,
                             CSLib_NormalStatus.CSLib_Singular, d)
        done = bool(res[0]) if isinstance(res, tuple) else True
    except Exception:                           # pragma: no cover - a derivative OCCT cannot give
        done = False
    return d, done


def _normal(face, u, v, tol):
    """Part::Tools::getNormal(face, u, v, tol, dir, done)."""
    prop = BRepLProp_SLProps(BRepAdaptor_Surface(face), u, v, 2, tol)
    d, done = _normal_by_props(prop, tol)
    if face.Orientation() == TopAbs_REVERSED:
        d.Reverse()
    return d, done


# ── the engines ───────────────────────────────────────────────────────────────────────────────────────

def _factory(z, x, origin, ref_org=None, use_ref_line=False, use_ref_plane=False, y_vertical=False,
             legacy_flat_face=False, place_of_ref: Placement | None = None, reverse=False) -> Placement:
    """AttachEngine::placementFactory."""
    if use_ref_line:
        rv, ov, zv = gp_Vec(ref_org.XYZ()), gp_Vec(origin.XYZ()), gp_Vec(z)
        origin = gp_Pnt(ov.Added(zv.Multiplied(zv.Dot(rv.Subtracted(ov)))).XYZ())
    if use_ref_plane:
        rv, ov, zv = gp_Vec(ref_org.XYZ()), gp_Vec(origin.XYZ()), gp_Vec(z)
        origin = gp_Pnt(rv.Added(zv.Multiplied(zv.Dot(ov.Subtracted(rv)))).XYZ())
    if x.Magnitude() < CONFUSION:
        y_vertical = True
    if not y_vertical:
        ax3 = gp_Ax3(origin, z, gp_Dir(x))
    elif not legacy_flat_face:
        y = gp_Vec(0.0, 0.0, 1.0)
        x = y.Crossed(gp_Vec(z))
        if x.Magnitude() < CONFUSION:
            x = gp_Vec(1, 0, 0).Multiplied(z.Z()).Normalized()
        ax3 = gp_Ax3(origin, z, gp_Dir(x))
    else:
        if place_of_ref is None:
            raise AttachError("AttachEngine::placementFactory: for Legacy mode, placement of the reference "
                              "must be supplied. Got null instead!")
        r = place_of_ref.rot
        dx, dy, dz = (gp_Dir(*r.mult_vec(a)) for a in ((1, 0, 0), (0, 1, 0), (0, 0, 1)))
        cx, cy, cz = z.Dot(dx), z.Dot(dy), z.Dot(dz)
        cs = [abs(cx), abs(cy), abs(cz)]
        pos = cs.index(max(cs))
        if pos == 0:
            ax3 = gp_Ax3(origin, z, dy if cx > 0 else dy.Reversed())
        elif pos == 1:
            ax3 = gp_Ax3(origin, z, dx.Reversed() if cy > 0 else dx)
        else:
            ax3 = gp_Ax3(origin, z, dx)
    if reverse:
        ax3.ZReverse()
        ax3.XReverse()
    t = gp_Trsf()
    t.SetTransformation(ax3)
    t.Invert()
    t.SetScaleFactor(1.0)
    return Placement.from_trsf(t)


def _shapes(refs):
    return [_single(r.shape) if r.shape is not None else None for r in refs]


def _calc_3d(mode: str, refs, offset: Placement, reverse: bool, parameter: float, orig: Placement,
             precision: float) -> Placement | None:
    """AttachEngine3D::_calculateAttachedPlacement (AttachEnginePlane's is the same)."""
    where = "AttachEngine3D::calculateAttachedPlacement"
    if mode == "Deactivated" or not refs:
        return None
    shapes = _shapes(refs)
    types = [r.type() for r in refs]
    place = refs[0].placement
    ref_org = gp_Pnt(*place.pos)
    normal = None                      # gp_Dir SketchNormal
    xaxis = gp_Vec(0, 0, 0)            # SketchXAxis
    base = gp_Pnt()                    # SketchBasePoint

    if mode == "Translate":
        sh = shapes[0]
        if sh is None or sh.IsNull():
            raise AttachError(f"Null shape in {where}()!")
        if sh.ShapeType() != TopAbs_VERTEX:
            raise AttachError(f"{where}: no subobjects specified (need one vertex).")
        p = BRep_Tool.Pnt_s(TopoDS.Vertex(sh))
        op = offset.pos
        return Placement((p.X() + op[0], p.Y() + op[1], p.Z() + op[2]), orig.rot)

    if mode in ("ObjectXY", "ObjectXZ", "ObjectYZ", "ParallelPlane"):
        if types[0] & rtFlagHasPlacement:
            r = place.rot
            dx, dy, dz = (gp_Dir(*r.mult_vec(a)) for a in ((1, 0, 0), (0, 1, 0), (0, 0, 1)))
            base = gp_Pnt(*place.pos)
        elif is_shape_of_type(types[0], rtConic) > 0:
            adapt = BRepAdaptor_Curve(TopoDS.Edge(shapes[0]))
            t = adapt.GetType()
            cc = adapt.Ellipse() if t == GeomAbs_Ellipse else adapt.Hyperbola() if t == GeomAbs_Hyperbola \
                else adapt.Parabola()
            pos = gp_Ax3(cc.Position())
            dx, dy, dz = pos.XDirection(), pos.YDirection(), pos.Axis().Direction()
            base = pos.Location()
        else:
            raise AttachError(f"{where}: need either a conic section edge, or a whole object for "
                              "ObjectXY-like modes.")
        if mode == "ObjectXY":
            normal, xaxis = dz, gp_Vec(dx)
        elif mode == "ObjectXZ":
            normal, xaxis = dy.Reversed(), gp_Vec(dx)
        elif mode == "ObjectYZ":
            normal, xaxis = dx, gp_Vec(dy)
        else:
            if len(shapes) < 2:
                raise AttachError(f"{where}: not enough subshapes (need one plane and one vertex).")
            p = _vertex(shapes[1], f"{where}()")
            normal, xaxis = dz, gp_Vec(dx)
            base = GeomAPI_ProjectPointOnCurve(p, Geom_Line(base, dz)).NearestPoint()

    elif mode == "InertialCS":
        g = _inertial_props(shapes)
        pr = g.PrincipalProperties()
        if pr.HasSymmetryPoint():
            raise AttachError(f"{where}:InertialCS: inertia tensor is trivial, principal axes are undefined.")
        if pr.HasSymmetryAxis():
            i1, i2, i3 = pr.Moments()
            d12, d23, d31 = abs(i1 - i2), abs(i2 - i3), abs(i3 - i1)
            if d12 < d23 and d12 < d31:
                normal = gp_Dir(pr.ThirdAxisOfInertia())
            elif d23 < d31 and d23 < d12:
                normal = gp_Dir(pr.FirstAxisOfInertia())
            else:
                normal = gp_Dir(pr.SecondAxisOfInertia())
        else:
            normal = gp_Dir(pr.FirstAxisOfInertia())
            xaxis = pr.SecondAxisOfInertia()
        base = g.CentreOfMass()

    elif mode == "FlatFace":
        plane, n, _ = _planar_face_info(shapes[0], precision)
        normal = n
        base = GeomAPI_ProjectPointOnSurf(ref_org, Geom_Plane(plane)).NearestPoint()

    elif mode == "MidPlane":
        if len(shapes) != 2:
            raise AttachError(f"{where}: need exactly two planar faces.")
        f1 = _planar_face_info(shapes[0], precision)
        f2 = _planar_face_info(shapes[1], precision)
        nvec, off = _mid_plane(f1, f2)
        mid = gp_Vec(f1[2].XYZ()).Added(gp_Vec(f2[2].XYZ())).Multiplied(0.5)
        normal = gp_Dir(nvec)
        base = gp_Pnt(mid.Added(nvec.Multiplied((off - nvec.Dot(mid)) / nvec.SquareMagnitude())).XYZ())

    elif mode == "TangentPlane":
        if len(shapes) < 2:
            raise AttachError(f"{where}: not enough subshapes (need one face and one vertex).")
        thru = False
        if shapes[0] is not None and shapes[0].ShapeType() == TopAbs_VERTEX:
            shapes[0], shapes[1] = shapes[1], shapes[0]
            thru = True
        face = _face(shapes[0], "face", f"{where}()")
        p = _vertex(shapes[1], f"{where}()")
        proj = GeomAPI_ProjectPointOnSurf(p, BRep_Tool.Surface_s(face))
        if proj.NbPoints() == 0:
            raise AttachError(f"{where}: projecting point onto surface failed.")
        u, v = proj.LowerDistanceParameters()
        prop = BRepLProp_SLProps(BRepAdaptor_Surface(face), u, v, 1, CONFUSION)
        normal, done = _normal(face, u, v, CONFUSION)
        if not done:
            raise AttachError(f"{where}: finding normal to surface at projected point failed.")
        if prop.IsTangentUDefined():
            dirx = gp_Dir()
            prop.TangentU(dirx)
            if face.Orientation() == TopAbs_REVERSED:
                dirx.Reverse()
        else:
            diry = gp_Dir()
            prop.TangentV(diry)
            dirx = diry.Crossed(normal)
        xaxis = gp_Vec(dirx).Reversed()
        base = p if thru else proj.NearestPoint()

    elif mode in ("NormalToEdge", "FrenetNB", "FrenetTN", "FrenetTB", "SectionOfRevolution", "Concentric"):
        thru = False
        if shapes[0] is not None and shapes[0].ShapeType() == TopAbs_VERTEX and len(shapes) >= 2:
            shapes[0], shapes[1] = shapes[1], shapes[0]
            thru = True
        if shapes[0] is None or shapes[0].IsNull() or shapes[0].ShapeType() != TopAbs_EDGE:
            raise AttachError(f"Null path in {where}()!")
        path = TopoDS.Edge(shapes[0])
        adapt = BRepAdaptor_Curve(path)
        u1, u2 = adapt.FirstParameter(), adapt.LastParameter()
        if _is_inf(u1) or _is_inf(u2):
            u1, u2 = 0.0, 1.0
        p_in = gp_Pnt()
        if len(shapes) >= 2:
            p_in = _vertex(shapes[1], f"{where}()")
            curve = BRep_Tool.Curve_s(path, u1, u2)
            proj = GeomAPI_ProjectPointOnCurve(p_in, curve)
            if proj.NbPoints() < 1:
                raise AttachError(f"{where}: projecting point onto curve failed.")
            u = proj.LowerDistanceParameter()
        else:
            u = u1 + parameter * (u2 - u1)
        p, d = gp_Pnt(), gp_Vec()
        adapt.D1(u, p, d)
        if d.Magnitude() < CONFUSION:
            raise AttachError(f"{where}: path curve derivative is below 1e-7, too low, can't align")
        base = p_in if thru else p
        if mode != "NormalToEdge":
            dd = gp_Vec()
            try:
                adapt.D2(u, p, d, dd)
            except Exception:
                dd = gp_Vec(0.0, 0.0, 0.0)
            T = d.Normalized()
            N = dd.Subtracted(T.Multiplied(dd.Dot(T)))
            if N.Magnitude() > SQUARE_CONFUSION:
                N.Normalize()
                B = T.Crossed(N)
            else:
                N, B = gp_Vec(0.0, 0.0, 0.0), gp_Vec(0.0, 0.0, 0.0)
            if mode in ("FrenetNB", "SectionOfRevolution"):
                normal, xaxis = gp_Dir(T.Reversed()), N.Reversed()
            elif mode in ("FrenetTN", "Concentric"):
                if N.Magnitude() == 0.0:
                    raise AttachError(f"{where}: Frenet-Serret normal is undefined. Can't align to TN plane.")
                normal, xaxis = gp_Dir(B), T
            else:
                if N.Magnitude() == 0.0:
                    raise AttachError(f"{where}: Frenet-Serret normal is undefined. Can't align to TB plane.")
                normal, xaxis = gp_Dir(N.Reversed()), T
            if mode in ("SectionOfRevolution", "Concentric"):
                if N.Magnitude() == 0.0:
                    raise AttachError(f"{where}: path has infinite radius of curvature at the point. Can't "
                                      "align for revolving.")
                curvature = dd.Dot(N) / d.Magnitude() ** 2
                base = gp_Pnt(gp_Vec(p.XYZ()).Added(N.Multiplied(1 / curvature)).XYZ())
        else:
            normal = gp_Dir(d.Reversed())

    elif mode in ("ThreePointsPlane", "ThreePointsNormal"):
        points = []
        for sh in shapes:
            if sh is None or sh.IsNull():
                raise AttachError(f"Null shape in {where}()!")
            if sh.ShapeType() == TopAbs_VERTEX:
                points.append(BRep_Tool.Pnt_s(TopoDS.Vertex(sh)))
            elif sh.ShapeType() == TopAbs_EDGE:
                crv = BRepAdaptor_Curve(TopoDS.Edge(sh))
                u1, u2 = crv.FirstParameter(), crv.LastParameter()
                if _is_inf(u1) or _is_inf(u2):
                    u1, u2 = 0.0, 1.0
                points += [crv.Value(u1), crv.Value(u2)]
            if len(points) >= 3:
                break
        if len(points) < 3:
            raise AttachError(f"{where}: less than 3 points are specified, cannot derive the plane.")
        p0, p1, p2 = points[:3]
        v01, v02 = gp_Vec(p0, p1), gp_Vec(p0, p2)
        if v01.Magnitude() < CONFUSION or v02.Magnitude() < CONFUSION:
            raise AttachError(f"{where}: some of 3 points are coincident. Can't make a plane")
        v01.Normalize()
        v02.Normalize()
        if mode == "ThreePointsPlane":
            norm = v01.Crossed(v02)
            if norm.Magnitude() < CONFUSION:
                raise AttachError(f"{where}: points are collinear. Can't make a plane")
            base = gp_Pnt(gp_Vec(p0.XYZ()).Added(gp_Vec(p1.XYZ())).Added(gp_Vec(p2.XYZ()))
                          .Multiplied(1.0 / 3.0).XYZ())
        else:
            norm = v02.Subtracted(v01.Multiplied(v02.Dot(v01))).Reversed()
            if norm.Magnitude() < CONFUSION:
                raise AttachError(f"{where}: points are collinear. Can't make a plane")
            base = GeomAPI_ProjectPointOnSurf(p2, Geom_Plane(p0, gp_Dir(norm))).NearestPoint()
        norm.Normalize()
        normal = gp_Dir(norm)

    elif mode == "Folding":
        if len(shapes) < 4:
            raise AttachError(f"{where}: not enough shapes (need 4 lines: edgeA, axisA, axisB, edgeB).")
        adapts, lines = [], []
        for i in range(4):
            e = _edge(shapes[i], f"{where}()")
            a = BRepAdaptor_Curve(e)
            if a.GetType() != GeomAbs_Line:
                raise AttachError(f"{where}: Folding - non-straight edge.")
            adapts.append(a)
            lines.append(a.Line())
        p1, p2 = adapts[0].Value(adapts[0].FirstParameter()), adapts[0].Value(adapts[0].LastParameter())
        p3, p4 = adapts[1].Value(adapts[1].FirstParameter()), adapts[1].Value(adapts[1].LastParameter())
        signs = [0.0] * 4
        if p1.Distance(p3) < CONFUSION:
            p, signs[0], signs[1] = p3, 1.0, 1.0
        elif p1.Distance(p4) < CONFUSION:
            p, signs[0], signs[1] = p4, 1.0, -1.0
        elif p2.Distance(p3) < CONFUSION:
            p, signs[0], signs[1] = p3, -1.0, 1.0
        elif p2.Distance(p4) < CONFUSION:
            p, signs[0], signs[1] = p4, -1.0, -1.0
        else:
            raise AttachError(f"{where}: Folding - edges to not share a vertex.")
        for i in (2, 3):
            a1, a2 = adapts[i].Value(adapts[i].FirstParameter()), adapts[i].Value(adapts[i].LastParameter())
            if p.Distance(a1) < CONFUSION:
                signs[i] = 1.0
            elif p.Distance(a2) < CONFUSION:
                signs[i] = -1.0
            else:
                raise AttachError(f"{where}: Folding - edges to not share a vertex.")
        dirs = [gp_Vec(lines[i].Direction()).Multiplied(signs[i]) for i in range(4)]
        ang = _fold_angle(dirs[1], dirs[2], dirs[0], dirs[3])
        norm = dirs[1].Crossed(dirs[2])
        norm.Rotate(gp_Ax1(gp_Pnt(), gp_Dir(dirs[1])), -ang)
        normal, xaxis, base = gp_Dir(norm.Reversed()), dirs[1], p

    elif mode in ("OZX", "OZY", "OXY", "OXZ", "OYZ", "OYX"):
        order = {"OZX": "ZXY", "OZY": "ZYX", "OXY": "XYZ", "OXZ": "XZY", "OYZ": "YZX", "OYX": "YXZ"}[mode]
        idx = [ord(c) - ord("X") for c in order]
        if len(shapes) < 2:
            raise AttachError(f"{where}: not enough shapes linked (at least two are required).")
        if shapes[0] is None or shapes[0].IsNull():
            raise AttachError(f"{where}: null shape!")
        if shapes[0].ShapeType() != TopAbs_VERTEX:
            raise AttachError(f"{where}: first reference must be a vertex, it's not")
        origin = BRep_Tool.Pnt_s(TopoDS.Vertex(shapes[0]))
        dirs = [gp_Vec(0, 0, 0)] * 3
        dirs = list(dirs)
        for i in range(1, min(3, len(shapes))):
            sh = shapes[i]
            if sh is None or sh.IsNull():
                raise AttachError(f"{where}: null shape!")
            if sh.ShapeType() == TopAbs_VERTEX:
                dirs[idx[i - 1]] = gp_Vec(origin, BRep_Tool.Pnt_s(TopoDS.Vertex(sh)))
            elif sh.ShapeType() == TopAbs_EDGE:
                crv = BRepAdaptor_Curve(TopoDS.Edge(sh))
                u1, u2 = crv.FirstParameter(), crv.LastParameter()
                if _is_inf(u1) or _is_inf(u2):
                    u1, u2 = 0.0, 1.0
                dirs[idx[i - 1]] = gp_Vec(crv.Value(u1), crv.Value(u2))
        rot = Rotation.by_axes(*(_v(d) for d in dirs), order)
        if reverse:
            rot = rot * Rotation.from_axis_angle((0, 1, 0), math.pi)
        return Placement(_v(origin), rot) * offset

    elif mode == "MidPoint":
        return _midpoint(refs, shapes) * offset

    else:
        raise AttachError(f"Attachment mode {mode} is not implemented." if mode in MODES
                          else f"Attachment mode {mode!r} is undefined.")

    pl = _factory(normal, xaxis, base, legacy_flat_face=(mode == "FlatFace"), place_of_ref=place,
                  reverse=reverse)
    return pl * offset


def _fold_angle(axA, axB, edA, edB):
    """AttachEngine3D::calculateFoldAngle."""
    axA, axB, edA, edB = (v.Normalized() for v in (axA, axB, edA, edB))
    norm = axA.Crossed(axB)
    if norm.Magnitude() < CONFUSION:
        raise AttachError("calculateFoldAngle: Folding axes are parallel, folding angle cannot be computed.")
    norm.Normalize()
    a = edA.Dot(axA)
    ra = edA.Crossed(axA).Magnitude()
    if abs(ra) < CONFUSION:
        raise AttachError("calculateFoldAngle: axisA and edgeA are parallel, folding can't be computed.")
    b = edB.Dot(axB)
    costheta = axB.Dot(axA)
    sintheta = axA.Crossed(axB).Dot(norm)
    singama, cosgama = -costheta, sintheta
    k = b * cosgama
    l = a + b * singama
    xa = k + l * singama / cosgama
    cos_unfold = -xa / ra
    if abs(cos_unfold) > 0.999:
        raise AttachError("calculateFoldAngle: cosine of folding angle is too close to or above 1.")
    return math.acos(cos_unfold)


def _midpoint(refs, shapes) -> Placement:
    """AttachEngine3D's MidPoint mode: the middle of a vertex, an edge or a face, Z along its normal."""
    if refs[0].plane:
        return refs[0].placement
    sh = shapes[0]
    pl = Placement()
    if sh is None or sh.IsNull():
        raise AttachError("AttachEngine3D::calculateAttachedPlacement: Unsupported shape type, must be one "
                          "of: Vertex, Edge, Face")
    st = sh.ShapeType()
    if st == TopAbs_VERTEX:
        return Placement(_v(BRep_Tool.Pnt_s(TopoDS.Vertex(sh))))
    if st == TopAbs_EDGE:
        edge = TopoDS.Edge(sh)
        adapt = BRepAdaptor_Curve(edge)
        t = adapt.GetType()
        if t == GeomAbs_Circle:                     # the circle's own special case, last in FreeCAD's
            c = adapt.Circle()
            return Placement(_v(c.Location()), Rotation.from_normal(_v(c.Axis().Direction())))
        if t in (GeomAbs_Ellipse, GeomAbs_Hyperbola, GeomAbs_Parabola) and BRep_Tool.IsClosed_s(edge):
            # Geometry::fromShape makes a whole conic a GeomConic: its location and GeomConic::getRotation
            cc = adapt.Ellipse() if t == GeomAbs_Ellipse else adapt.Hyperbola() if t == GeomAbs_Hyperbola \
                else adapt.Parabola()
            ax = cc.Position()
            m = [[c[i] for c in (_v(ax.XDirection()), _v(ax.YDirection()), _v(ax.Direction()))]
                 for i in range(3)]
            return Placement(_v(ax.Location()), Rotation.from_matrix(m))
        from OCP.GeomLProp import GeomLProp_CLProps
        u1, u2 = adapt.FirstParameter(), adapt.LastParameter()
        mid = (u1 + u2) / 2
        curve = BRep_Tool.Curve_s(edge, u1, u2)
        direction = None
        try:                                        # GeomCurve::normalAt, else GeomCurve::tangent
            n = gp_Dir()
            GeomLProp_CLProps(curve, mid, 2, CONFUSION).Normal(n)
            direction = _v(n)
        except Exception:
            prop = GeomLProp_CLProps(curve, mid, 1, CONFUSION)
            tdir = gp_Dir(0, 0, 1)
            if prop.IsTangentDefined():
                prop.Tangent(tdir)
            direction = _v(tdir)
        return Placement(_v(curve.Value(mid)), Rotation.from_normal(direction))
    if st == TopAbs_FACE:
        face = TopoDS.Face(sh)
        adapt = BRepAdaptor_Surface(face, True)
        u1, u2, v1, v2 = (adapt.FirstUParameter(), adapt.LastUParameter(), adapt.FirstVParameter(),
                          adapt.LastVParameter())
        mu, mv = (u1 + u2) / 2, (v1 + v2) / 2
        if adapt.GetType() == GeomAbs_Cylinder:
            ax = adapt.Cylinder().Axis()
            o, d = ax.Location(), ax.Direction()
            mp = adapt.Value(mu, mv)
            t = gp_Vec(o, mp).Dot(gp_Vec(d))
            c = o.Translated(gp_Vec(d).Multiplied(t))
            return Placement(_v(c), Rotation.from_normal(_v(d)))
        surf = BRep_Tool.Surface_s(face)
        if adapt.GetType() == GeomAbs_Sphere:
            pos = _v(adapt.Sphere().Location())
        elif adapt.GetType() == GeomAbs_Cone:
            pos = _v(adapt.Cone().Apex())
        else:
            pos = _v(surf.Value(mu, mv))
        from OCP.GeomLProp import GeomLProp_SLProps
        nd, _ = _normal_by_props(GeomLProp_SLProps(surf, mu, mv, 2, CONFUSION), CONFUSION)   # GeomSurface::normal
        n = _v(nd)
        if face.Orientation() == TopAbs_REVERSED:
            n = tuple(-c for c in n)
        return Placement(pos, _aligned_to_normal(Rotation(), n))
    raise AttachError("AttachEngine3D::calculateAttachedPlacement: Unsupported shape type, must be one of: "
                      "Vertex, Edge, Face")


def _aligned_to_normal(rotation: Rotation, normal, eps=CONFUSION) -> Rotation:
    """rotationAlignedToNormal: Z along normal, X the old X projected, with minimal twist."""
    if _norm(normal) < eps:
        return rotation
    n = _unit(normal)
    xo = rotation.mult_vec((1, 0, 0))
    yo = rotation.mult_vec((0, 1, 0))
    xp = tuple(xo[i] - n[i] * _dot(xo, n) for i in range(3))
    if _norm(xp) < eps:
        xp = tuple(yo[i] - n[i] * _dot(yo, n) for i in range(3))
    if _norm(xp) < eps:
        xp = (1.0, 0.0, 0.0)
        if abs(_dot(xp, n)) > 1.0 - eps:
            xp = (0.0, 1.0, 0.0)
    xp = _unit(xp)
    yn = _unit(_cross(n, xp))
    return Rotation.from_matrix([[xp[i], yn[i], n[i]] for i in range(3)])


_LINE_REUSE = {"ObjectX": "ObjectYZ", "ObjectY": "ObjectXZ", "ObjectZ": "ObjectXY",
               "AxisOfCurvature": "SectionOfRevolution", "Binormal": "FrenetTN", "Normal": "FrenetTB",
               "Tangent": "NormalToEdge", "FaceNormal": "TangentPlane"}


def _calc_line(mode, refs, offset, reverse, parameter, orig, precision):
    """AttachEngineLine::_calculateAttachedPlacement."""
    where = "AttachEngineLine::calculateAttachedPlacement"
    if mode == "Deactivated" or not refs:
        return None
    if mode in _LINE_REUSE:
        pl = _calc_3d(_LINE_REUSE[mode], refs, Placement(), reverse, parameter, orig, precision)
        if mode == "AxisOfCurvature":
            pl = pl * Placement((0, 0, 0), Rotation.from_vectors((0.0, 0.0, 1.0), (0.0, 1.0, 0.0)))
        return pl * offset
    shapes = _shapes(refs)
    ref_org = gp_Pnt(*refs[0].placement.pos)
    if mode in ("AxisOfInertia1", "AxisOfInertia2", "AxisOfInertia3"):
        g = _inertial_props(shapes)
        base = g.CentreOfMass()
        pr = g.PrincipalProperties()
        if pr.HasSymmetryPoint():
            raise AttachError(f"{where}:AxisOfInertia: inertia tensor is trivial, principal axes are undefined.")
        i1, i2, i3 = pr.Moments()
        d12, d23, d31 = abs(i1 - i2), abs(i2 - i3), abs(i3 - i1)
        if mode == "AxisOfInertia1":
            d = gp_Dir(pr.FirstAxisOfInertia())
            if pr.HasSymmetryAxis() and not (d23 < d31 and d23 < d12):
                raise AttachError(f"{where}:AxisOfInertia: inertia tensor has axis of symmetry; first axis of "
                                  "inertia is undefined.")
        elif mode == "AxisOfInertia2":
            d = gp_Dir(pr.SecondAxisOfInertia())
            if pr.HasSymmetryAxis() and not (d31 < d12 and d31 < d23):
                raise AttachError(f"{where}:AxisOfInertia: inertia tensor has axis of symmetry; second axis "
                                  "of inertia is undefined.")
        else:
            d = gp_Dir(pr.ThirdAxisOfInertia())
            if pr.HasSymmetryAxis() and not (d12 < d23 and d12 < d31):
                raise AttachError(f"{where}:AxisOfInertia: inertia tensor has axis of symmetry; third axis of "
                                  "inertia is undefined.")
    elif mode == "TwoPointLine":
        points = []
        for sh in shapes:
            if sh is None or sh.IsNull():
                raise AttachError(f"Null shape in {where}()!")
            if sh.ShapeType() == TopAbs_VERTEX:
                points.append(BRep_Tool.Pnt_s(TopoDS.Vertex(sh)))
            elif sh.ShapeType() == TopAbs_EDGE:
                crv = BRepAdaptor_Curve(TopoDS.Edge(sh))
                u1, u2 = crv.FirstParameter(), crv.LastParameter()
                if _is_inf(u1) or _is_inf(u2):
                    u1, u2 = 0.0, 1.0
                points += [crv.Value(u1), crv.Value(u2)]
            if len(points) >= 2:
                break
        if len(points) < 2:
            raise AttachError(f"{where}: less than 2 points are specified, cannot derive the line.")
        d, base = gp_Dir(gp_Vec(points[0], points[1])), points[0]
    elif mode in ("Asymptote1", "Asymptote2"):
        e = _edge(shapes[0], f"{where}()")
        a = BRepAdaptor_Curve(e)
        if a.GetType() != GeomAbs_Hyperbola:
            raise AttachError(f"{where}: Asymptotes are available only for hyperbola-shaped edges, the one "
                              "supplied is not.")
        h = a.Hyperbola()
        d = (h.Asymptote1() if mode == "Asymptote1" else h.Asymptote2()).Direction()
        base = h.Location()
    elif mode in ("Directrix1", "Directrix2"):
        e = _edge(shapes[0], f"{where}()")
        a = BRepAdaptor_Curve(e)
        t = a.GetType()
        if t == GeomAbs_Ellipse:
            cc = a.Ellipse()
            dx1, dx2 = cc.Directrix1(), cc.Directrix2()
        elif t == GeomAbs_Hyperbola:
            cc = a.Hyperbola()
            dx1, dx2 = cc.Directrix1(), cc.Directrix2()
        elif t == GeomAbs_Parabola:
            dx1 = dx2 = a.Parabola().Directrix()
            if mode == "Directrix2":
                raise AttachError(f"{where}: Parabola has no second directrix")
        else:
            raise AttachError(f"{where}: referenced edge is not a conic section with a directrix")
        ax = dx1 if mode == "Directrix1" else dx2
        d, base = ax.Direction(), ax.Location()
    elif mode == "IntersectionLine":
        if len(shapes) < 2:
            raise AttachError(f"{where}: Intersection mode requires two shapes; only one is supplied")
        if shapes[0] is None or shapes[1] is None or shapes[0].IsNull() or shapes[1].IsNull():
            raise AttachError(f"Null shape in {where}()!")
        s1 = BRep_Tool.Surface_s(TopoDS.Face(shapes[0]))
        s2 = BRep_Tool.Surface_s(TopoDS.Face(shapes[1]))
        inter = GeomAPI_IntSS(s1, s2, CONFUSION)
        if not inter.IsDone():
            raise AttachError(f"{where}: Intersection failed")
        n = inter.NbLines()
        if n == 0:
            raise AttachError(f"{where}: The two shapes don't intersect")
        if n != 1:
            raise AttachError(f"{where}: Intersection is not a single curve")
        a = GeomAdaptor_Curve(inter.Line(1))
        if a.GetType() != GeomAbs_Line:
            raise AttachError(f"{where}: Intersection is not a straight line")
        base, d = a.Line().Location(), a.Line().Direction()
    elif mode == "ProximityLine":
        if len(shapes) < 2:
            raise AttachError(f"{where}: Proximity mode requires two shapes; only one is supplied")
        if any(s is None or s.IsNull() for s in shapes[:2]):
            raise AttachError(f"Null shape in {where}()!")
        dist = BRepExtrema_DistShapeShape(shapes[0], shapes[1])
        if not dist.IsDone():
            raise AttachError(f"{where}: proximity calculation failed.")
        p1, p2 = dist.PointOnShape1(1), dist.PointOnShape2(1)
        base = p1
        v = gp_Vec(p1, p2)
        if v.Magnitude() < CONFUSION:
            raise AttachError(f"{where}: can't make proximity line, because shapes touch or intersect")
        d = gp_Dir(v)
    else:
        raise AttachError(f"Attachment mode {mode} is not implemented." if mode in MODES
                          else f"Attachment mode {mode!r} is undefined.")
    pl = _factory(d, gp_Vec(), base, ref_org, use_ref_line=True, reverse=reverse)
    return pl * offset


_POINT_REUSE = {"ObjectOrigin": "ObjectXY", "CenterOfCurvature": "SectionOfRevolution",
                "OnEdge": "NormalToEdge"}


def _calc_point(mode, refs, offset, reverse, parameter, orig, precision):
    """AttachEnginePoint::_calculateAttachedPlacement."""
    where = "AttachEnginePoint::calculateAttachedPlacement"
    if mode == "Deactivated" or not refs:
        return None
    if mode in _POINT_REUSE:
        return _calc_3d(_POINT_REUSE[mode], refs, Placement(), reverse, parameter, orig, precision) * offset
    shapes = _shapes(refs)
    if mode == "Vertex":
        sh = shapes[0]
        if sh is None or sh.IsNull():
            raise AttachError(f"Null shape in {where}()!")
        if sh.ShapeType() == TopAbs_VERTEX:
            base = BRep_Tool.Pnt_s(TopoDS.Vertex(sh))
        elif sh.ShapeType() == TopAbs_EDGE:
            crv = BRepAdaptor_Curve(TopoDS.Edge(sh))
            u = crv.FirstParameter()
            if _is_inf(u):
                raise AttachError("Edge is infinite")
            base = crv.Value(u)
        else:
            base = gp_Pnt()
    elif mode in ("Focus1", "Focus2"):
        e = _edge(shapes[0], f"{where}()")
        a = BRepAdaptor_Curve(e)
        t = a.GetType()
        if t == GeomAbs_Ellipse:
            cc = a.Ellipse()
            f1, f2 = cc.Focus1(), cc.Focus2()
        elif t == GeomAbs_Hyperbola:
            cc = a.Hyperbola()
            f1, f2 = cc.Focus1(), cc.Focus2()
        elif t == GeomAbs_Parabola:
            f1 = f2 = a.Parabola().Focus()
            if mode == "Focus2":
                raise AttachError(f"{where}: Parabola has no second focus")
        else:
            raise AttachError(f"{where}: referenced edge is not a conic section with a directrix")
        base = f1 if mode == "Focus1" else f2
    elif mode in ("ProximityPoint1", "ProximityPoint2"):
        if len(shapes) < 2:
            raise AttachError(f"{where}: Proximity mode requires two shapes; only one is supplied")
        if any(s is None or s.IsNull() for s in shapes[:2]):
            raise AttachError(f"Null shape in {where}()!")
        base = _proximity_point(mode, shapes[0], shapes[1], where)
    elif mode == "CenterOfMass":
        base = _inertial_props(shapes).CentreOfMass()
    else:
        raise AttachError(f"Attachment mode {mode} is not implemented." if mode in MODES
                          else f"Attachment mode {mode!r} is undefined.")
    pl = _factory(gp_Dir(0.0, 0.0, 1.0), gp_Vec(1.0, 0.0, 0.0), base, gp_Pnt(), reverse=reverse)
    return pl * offset


def _proximity_point(mode, s1, s2, where):
    """AttachEnginePoint::getProximityPoint: an edge and a face meet first, else the closest points."""
    try:
        face = edge = None
        if s1.ShapeType() == TopAbs_FACE and s2.ShapeType() == TopAbs_EDGE:
            face, edge = s1, s2
        elif s1.ShapeType() == TopAbs_EDGE and s2.ShapeType() == TopAbs_FACE:
            edge, face = s1, s2
        if edge is not None and face is not None:
            crv = BRepAdaptor_Curve(TopoDS.Edge(edge))
            typed = GeomAdaptor_Curve(GeomAdaptor.MakeCurve_s(crv))
            inter = BRepIntCurveSurface_Inter()
            inter.Init(face, typed, CONFUSION)
            pts = []
            while inter.More():
                pts.append(inter.Pnt())
                inter.Next()
            if pts:
                return pts[0]
    except Exception:
        pass
    dist = BRepExtrema_DistShapeShape(s1, s2)
    if not dist.IsDone():
        raise AttachError(f"{where}: proximity calculation failed.")
    return dist.PointOnShape1(1) if mode == "ProximityPoint1" else dist.PointOnShape2(1)


_CALC = {"3D": _calc_3d, "Plane": _calc_3d, "Line": _calc_line, "Point": _calc_point}


def attach(engine: str, mode: str, refs, offset=None, reversed: bool = False, parameter: float = 0.0,
           orig: Placement | None = None, precision: float | None = None) -> Placement | None:
    """AttachExtension::positionBySupport: the Placement the references and mode give (offset applied: an
    AttachmentOffset Placement, or a part file's (x, y, z) / ((x, y, z), (yaw, pitch, roll))), or None when the
    mode is Deactivated or there are no references (the object keeps its own Placement). orig is that own
    Placement, which Translate keeps the rotation of. Raises AttachError."""
    engine = _engine(engine)
    if mode not in MODES:
        raise AttachError(f"AttachEngine::getModeByName: mode with this name doesn't exist: {mode}")
    if mode != "Deactivated" and not MODE_REFS[engine][M[mode]]:
        raise AttachError(f"Attachment mode {mode} is not implemented.")
    if precision is None:
        precision = PLANAR_PRECISION if engine == "Plane" else 1.0e-7
    try:
        return _CALC[engine](mode, list(refs), Placement.from_offset(offset), bool(reversed), float(parameter),
                             orig if orig is not None else Placement(), precision)
    except AttachError:
        raise
    except Exception as e:                      # Standard_Failure: OCCT's own exceptions
        raise AttachError(f"{type(e).__name__}: {e}") from e

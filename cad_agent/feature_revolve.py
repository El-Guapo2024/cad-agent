# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses FreeCAD's PartDesign Revolution and Groove (PartDesign::Revolved and the two
# features on it) function by function and keeps FreeCAD's licence, the GNU Lesser General Public License, version 2.1
# or (at your option) any later version; the text is in ../ui/LICENSE.
#
#   Derived from: src/Mod/PartDesign/App/FeatureRevolved.cpp, FeatureRevolution.cpp, FeatureGroove.cpp
#                 (Copyright (c) 2010 Juergen Riegel <FreeCAD@juergen-riegel.net>; FeatureGroove.cpp
#                 Copyright (c) 2012 Jan Rheinländer <jrheinlaender@users.sourceforge.net>),
#                 src/Mod/PartDesign/App/FeatureSketchBased.cpp (ProfileBased::getAxis, checkLineCrossesFace,
#                 getReversedAngle, the axis form of getUpToFace; Copyright (c) 2010 Juergen Riegel),
#                 src/Mod/Part/App/PartFeature.cpp (findAllFacesCutBy along an axis; Copyright (c) 2002 Jürgen Riegel),
#                 src/Mod/Part/App/TopoShapeExpansion.cpp (makeElementRevolve, makeElementRevolution;
#                 Copyright (c) 2022 Zheng, Lei), src/Mod/Sketcher/App/SketchObjectGeometry.cpp (getAxis,
#                 getAxisCount; Copyright (c) 2008 Jürgen Riegel) and src/Mod/PartDesign/Gui/Command.cpp
#                 (CmdPartDesignRevolution, CmdPartDesignGroove; Copyright (c) 2008 Jürgen Riegel)
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
"""PartDesign::Revolution and PartDesign::Groove for a FEATURES list (cad_agent/feature.py).

    Revolution("Revolution", "Sketch", reference_axis=("Sketch", "V_Axis"), angle=360.0)
    Groove("Groove", "Sketch001", reference_axis="Y_Axis", angle=90.0, side_type="Symmetric")

The properties are FreeCAD's in snake_case, with FreeCAD's defaults (FeatureRevolution.cpp, FeatureGroove.cpp):

    reference_axis   ReferenceAxis: (sketch, "V_Axis" | "H_Axis" | "N_Axis" | "Axis0", "Axis1", ...) for the profile
                     sketch's own axes and construction lines (SketchObject::getAxis), "X_Axis" | "Y_Axis" | "Z_Axis"
                     for the Body's origin axes, or (feature, "EdgeN") for a straight or circular edge of a sketch or
                     of a solid before it. Left out, it is (profile, "V_Axis"), what PartDesign_Revolution and
                     PartDesign_Groove set.
    angle, angle2    Angle (360 deg) and Angle2 (0 deg), in degrees, a number or a PARAMS expression
    side_type        "One side" | "Two sides" | "Symmetric"; midplane=True is the deprecated Symmetric
    type, type2      Revolution: Angle, UpToLast, UpToFirst, UpToFace; Groove: Angle, ThroughAll, UpToFirst,
                     UpToFace; the deprecated type="TwoAngles" is SideType "Two sides" (onDocumentRestored)
    up_to_face(2)    ("Pad", "Face6") or an origin plane ("XY_Plane"), for UpToFace
    reversed, project_axis, start_type ("Profile plane" | "Offset"), start_offset (degrees), refine (True)

What is built is what Revolved::tryExecuteRevolved builds, in the same OCCT calls: BRepPrimAPI_MakeRevol for the
angular types (and a Groove's ThroughAll, a full turn), BRepFeat_MakeRevol for the up-to types, then the fuse
(Revolution, BaseFirst) or the cut (Groove) with the solid before it, refined as FreeCAD refines.
"""
from __future__ import annotations

import math

try:                                    # the kernel; FreeCAD's Python reads the vocabulary without it
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_Transform
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape, BRepExtrema_IsOnEdge, BRepExtrema_IsVertex
    from OCP.BRepFeat import BRepFeat_MakeRevol
    from OCP.BRepGProp import BRepGProp
    from OCP.BRepIntCurveSurface import BRepIntCurveSurface_Inter
    from OCP.BRepLib import BRepLib_FindSurface
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeRevol
    from OCP.GProp import GProp_GProps
    from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Line, GeomAbs_Plane
    from OCP.GeomAdaptor import GeomAdaptor_Curve, GeomAdaptor_Surface
    from OCP.Geom import Geom_Circle
    from OCP.ShapeAnalysis import ShapeAnalysis
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SOLID, TopAbs_VERTEX, TopAbs_WIRE
    from OCP.TopExp import TopExp
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS, TopoDS_Face
    from OCP.gce import gce_MakeCirc, gce_MakeDir
    from OCP.gp import gp_Ax1, gp_Ax2, gp_Ax3, gp_Dir, gp_Lin, gp_Pnt, gp_Trsf, gp_Vec
    try:
        from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape
    except ImportError:                 # OCP 8 moved OCCT's collections
        from OCP.collections import (
            IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher as
            TopTools_IndexedDataMapOfShapeListOfShape)
except ImportError:                     # pragma: no cover - only FreeCAD's Python lands here
    pass

ANGULAR = 1e-12           # Precision::Angular()
CONFUSION = 1e-7          # Precision::Confusion()
SIDE_TYPES = ("One side", "Two sides", "Symmetric")    # Revolved::SideTypesEnums
START_TYPES = ("Profile plane", "Offset")              # ProfileBased::StartTypesEnums, but Reference
ORIGIN_AXES = {"X_Axis": (1.0, 0.0, 0.0), "Y_Axis": (0.0, 1.0, 0.0), "Z_Axis": (0.0, 0.0, 1.0)}
SKETCH_AXES = ("V_Axis", "H_Axis", "N_Axis")


class _Revolved:
    """PartDesign::Revolved: what Revolution and Groove share."""
    kind = ""
    TYPES: tuple = ()
    additive = True
    # feature_edit.py: the properties as read() names them and the part file's keyword for each, and the keywords that
    # name other features (for rename, delete and the order check).
    EDIT_PROPS = {"reference_axis": "reference_axis", "angle": "angle", "angle2": "angle2", "side_type": "side_type",
                  "type1": "type", "type2": "type2", "reversed": "reversed", "up_to_face": "up_to_face",
                  "up_to_face2": "up_to_face2", "project_axis": "project_axis", "start_type": "start_type",
                  "start_offset": "start_offset", "refine": "refine"}
    EDIT_EXTRA = {"midplane"}
    REF_KEYS = ("reference_axis", "up_to_face", "up_to_face2")

    def __init__(self, name: str, profile: str, *, reference_axis=None, angle=360.0, angle2=0.0,
                 side_type: str = "One side", type: str = "Angle", type2: str = "Angle", midplane: bool = False,
                 reversed: bool = False, up_to_face=None, up_to_face2=None, project_axis: bool = False,
                 start_type: str = "Profile plane", start_offset=0.0, refine: bool = True):
        self.name, self.profile = name, profile
        if type in ("TwoAngles", "?TwoAngles"):
            # Revolved::onDocumentRestored: the deprecated TwoAngles is SideType "Two sides", both types Angle
            type, type2, side_type = "Angle", "Angle", "Two sides"
        if type2 in ("TwoAngles", "?TwoAngles"):
            type2 = "Angle"
        if midplane:
            side_type = "Symmetric"              # Revolved::onChanged: Midplane is SideType Symmetric
        if side_type not in SIDE_TYPES:
            raise FeatureError(f"{name}: side_type {side_type!r} is not one of {', '.join(SIDE_TYPES)}")
        for k, t in (("type", type), ("type2", type2)):
            if t not in self.TYPES:
                raise FeatureError(f"{name}: {k} {t!r} is not one of {', '.join(self.TYPES)} "
                                   f"(PartDesign::{self.kind}'s Type)")
        if start_type not in START_TYPES:
            raise FeatureError(f"{name}: start_type {start_type!r} is not supported, only {', '.join(START_TYPES)}")
        self.reference_axis = (profile, "V_Axis") if reference_axis is None else _axis_ref(reference_axis, name)
        self.angle, self.angle2 = angle, angle2
        self.side_type, self.type, self.type2 = side_type, type, type2
        self.midplane = side_type == "Symmetric"
        self.reversed, self.project_axis = bool(reversed), bool(project_axis)
        self.up_to_face, self.up_to_face2 = up_to_face, up_to_face2
        self.start_type, self.start_offset = start_type, start_offset
        self.refine = bool(refine)

    def __repr__(self):
        return f"{self.kind}({self.name!r}, {self.profile!r}, reference_axis={self.reference_axis!r}, " \
               f"type={self.type!r}, angle={self.angle!r})"

    # ── feature.py's evaluate() and to_freecad() call these ──
    def build(self, sketches, base, shapes, params):
        if self.profile not in sketches:
            raise FeatureError(f"{self.name}: no sketch {self.profile!r} before it" if self.profile not in shapes
                               else f"{self.name}: profile {self.profile!r} is not a sketch")
        return _revolve(self, sketches[self.profile], base, shapes, sketches, params)

    def to_freecad(self, body, made, planes, setv, ref):
        """The same feature in a FreeCAD Body, as CmdPartDesignRevolution leaves it with these properties set."""
        obj = body.newObject(f"PartDesign::{self.kind}", self.name)
        obj.Profile = made[self.profile]
        r = self.reference_axis
        if isinstance(r, str):
            obj.ReferenceAxis = (planes[r], [""])
        else:
            obj.ReferenceAxis = (made[r[0]], [r[1]])
        obj.Refine = self.refine
        obj.SideType = self.side_type
        obj.Type = self.type
        obj.Type2 = self.type2
        setv(obj, "Angle", self.angle)
        setv(obj, "Angle2", self.angle2)
        obj.Reversed = self.reversed
        obj.ProjectAxis = self.project_axis
        obj.StartType = self.start_type
        setv(obj, "StartOffset", self.start_offset)
        for prop, rr in (("UpToFace", self.up_to_face), ("UpToFace2", self.up_to_face2)):
            if rr is not None:
                o, subs = ref(rr)
                setattr(obj, prop, (o, subs))
        return obj


class Revolution(_Revolved):
    """PartDesign::Revolution: revolves the profile about the reference axis and adds it to the body."""
    kind = "Revolution"
    TYPES = ("Angle", "UpToLast", "UpToFirst", "UpToFace")          # Revolution::TypeEnums, without ?TwoAngles
    additive = True


class Groove(_Revolved):
    """PartDesign::Groove: revolves the profile about the reference axis and removes it from the body."""
    kind = "Groove"
    TYPES = ("Angle", "ThroughAll", "UpToFirst", "UpToFace")        # Groove::TypeEnums, without ?TwoAngles
    additive = False


def _axis_ref(r, where):
    if isinstance(r, str):
        if r not in ORIGIN_AXES:
            raise FeatureError(f"{where}: reference_axis {r!r} is not X_Axis, Y_Axis, Z_Axis or (feature, sub)")
        return r
    try:
        obj, sub = r
    except (TypeError, ValueError):
        raise FeatureError(f"{where}: reference_axis {r!r} is not an origin axis or (feature, sub)") from None
    if isinstance(sub, (list, tuple)):
        sub = sub[0] if sub else ""
    if not (isinstance(obj, str) and isinstance(sub, str)):
        raise FeatureError(f"{where}: reference_axis {r!r} is not (feature, sub)")
    return (obj, sub)


# ── the axis: ProfileBased::getAxis ──────────────────────────────────────────────────────────────────────

def _sketch_edges(sketch):
    """The sketch's Shape's edges in FreeCAD's Edge1, Edge2, ... order: its non-construction curves made into wires as
    SketchObject::buildShape makes them (TopoShape::makeElementWires), in the wires' edge order."""
    idx = [i for i, g in enumerate(sketch.geometry) if not g.construction and not isinstance(g, F.Point)]
    loc = TopLoc_Location(F._trsf(sketch))
    edges = [TopoDS.Edge(F._edge(sketch.geometry[i]).Moved(loc)) for i in idx]
    out = []
    for w in F._wires(edges):
        out += F._subs(w, TopAbs_EDGE)
    return out


def _axis_from_edge(edge):
    if edge is None or edge.IsNull():
        raise FeatureError("Failed to extract rotation edge")
    adapt = BRepAdaptor_Curve(TopoDS.Edge(edge))
    if adapt.GetType() == GeomAbs_Line:
        lin = adapt.Line()
        return lin.Location(), lin.Direction()
    if adapt.GetType() == GeomAbs_Circle:
        c = adapt.Circle()
        return c.Location(), c.Axis().Direction()
    raise FeatureError("Edge must be a straight line, circle or arc of circle")


def get_axis(feat, sketch, shapes, sketches):
    """(base, dir) as gp_Pnt and gp_Vec (dir unnormalised, as Base::Axis keeps it) in the body's frame, or raises with
    FreeCAD's words. ForbiddenAxis::NotParallelWithNormal unless project_axis (Revolved::updateAxis)."""
    r = feat.reference_axis
    origin, rot = sketch.placement()
    normal = gp_Dir(*sketch.normal())

    def verify(d):
        if not feat.project_axis and normal.IsParallel(gp_Dir(d), ANGULAR):
            raise FeatureError("Axis must not be perpendicular to the sketch plane")

    if isinstance(r, str):                               # App::Line of the Body's Origin
        d = gp_Vec(*ORIGIN_AXES[r])
        verify(d)
        return gp_Pnt(0, 0, 0), d
    obj, sub = r
    if obj == sketch.name:
        local = None
        if sub == "V_Axis":
            local = ((0.0, 0.0), (0.0, 1.0, 0.0))
        elif sub == "H_Axis":
            local = ((0.0, 0.0), (1.0, 0.0, 0.0))
        elif sub == "N_Axis":
            local = ((0.0, 0.0), (0.0, 0.0, 1.0))
        elif sub.startswith("Axis"):
            try:
                ax_id = int(sub[4:])
            except ValueError:
                ax_id = -1
            lines = [g for g in sketch.geometry if g.construction and isinstance(g, F.LineSegment)]
            if 0 <= ax_id < len(lines):
                g = lines[ax_id]
                local = (g.start, (g.end[0] - g.start[0], g.end[1] - g.start[1], 0.0))
        if local is not None:                            # axis *= SketchPlm; no check, as FreeCAD's
            (bx, by), dv = local
            b = F._matvec(rot, (bx, by, 0.0))
            d = F._matvec(rot, dv)
            return gp_Pnt(origin[0] + b[0], origin[1] + b[1], origin[2] + b[2]), gp_Vec(*d)
    if not (isinstance(sub, str) and sub.startswith("Edge") and sub[4:].isdigit()):
        if obj in sketches or obj in shapes:
            raise FeatureError("Unsupported geometry type to get reference axis")
        raise FeatureError(f"{feat.name}: reference_axis names {obj!r}, which is not before it")
    if obj in sketches:
        edges = _sketch_edges(sketches[obj])
    elif obj in shapes and obj not in ("Tip", "_sketches") and shapes[obj] is not None:
        edges = F._subs(shapes[obj], TopAbs_EDGE)
    else:
        raise FeatureError(f"{feat.name}: reference_axis names {obj!r}, which is not before it")
    i = int(sub[4:])
    if not 1 <= i <= len(edges):
        raise FeatureError("Failed to extract rotation edge")
    b, d = _axis_from_edge(edges[i - 1])
    dv = gp_Vec(d)
    verify(dv)
    return b, dv


def _project_axis(base, dirv, face):
    """Revolved::updateAxis with ProjectAxis: the axis put into the profile's plane."""
    pln = _find_plane(face)
    if pln is None:
        raise FeatureError("Cannot project the axis because the profile is not planar")
    n, o = gp_Vec(pln.Axis().Direction()), gp_Vec(pln.Location().XYZ())
    d = dirv.Normalized()
    d = d - n * d.Dot(n)
    if d.Magnitude() <= ANGULAR:
        raise FeatureError("Cannot project an axis perpendicular to the profile plane")
    d.Normalize()
    bv = gp_Vec(base.XYZ())
    bv = bv - n * (bv - o).Dot(n)
    return gp_Pnt(bv.XYZ()), d


def _find_plane(shape):
    finder = BRepLib_FindSurface(shape, -1, True)
    if not finder.Found():
        return None
    adapt = GeomAdaptor_Surface(finder.Surface())
    return adapt.Plane() if adapt.GetType() == GeomAbs_Plane else None


def suggest_reversed(feat, sketch, shapes=None, sketches=None) -> bool:
    """Revolved::suggestReversed, what PartDesign_Revolution and PartDesign_Groove set Reversed to: the sign of the
    sketch normal against axis x (centre of gravity off the axis); Revolution reversed when negative, Groove when
    positive. False when the axis cannot be had (FreeCAD reports it and goes on)."""
    sketches = dict(sketches or {}, **{sketch.name: sketch})
    try:
        b, v = get_axis(feat, sketch, shapes or {}, sketches)
        face = F.profile_face(sketch)
    except FeatureError:
        return False
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    cog = props.CentreOfMass()
    p = gp_Vec(cog.XYZ())
    bv = gp_Vec(b.XYZ())
    t = (p - bv).Dot(v) / v.Dot(v)                     # Vector3::Perpendicular
    perp = p - (bv + v * t)
    cross = v.Crossed(perp)
    angle = gp_Vec(*sketch.normal()).Dot(cross)
    return angle < 0.0 if feat.additive else angle > 0.0


# ── ProfileBased::checkLineCrossesFace ───────────────────────────────────────────────────────────────────

def _dist_params(dss, i):
    t = dss.ParOnEdgeS1(i)
    return t[0] if isinstance(t, tuple) else t


def check_line_crosses_face(line, face) -> bool:
    edge = BRepBuilderAPI_MakeEdge(line).Shape()
    wire = ShapeAnalysis.OuterWire_s(face)
    dss = BRepExtrema_DistShapeShape(wire, edge, CONFUSION)
    if not dss.IsDone():
        return False
    if dss.Value() > CONFUSION:
        return False
    v2e = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(wire, TopAbs_VERTEX, TopAbs_EDGE, v2e)
    fnormal = BRepAdaptor_Surface(face).Plane().Axis().Direction()
    for i in range(1, dss.NbSolution() + 1):
        if dss.PointOnShape1(i).Distance(dss.PointOnShape2(i)) > CONFUSION:
            continue
        kind = dss.SupportTypeShape1(i)
        if kind == BRepExtrema_IsOnEdge:
            e = TopoDS.Edge(dss.SupportOnShape1(i))
            adapt = BRepAdaptor_Curve(e)
            d = gp_Vec(line.Direction().Crossed(fnormal))
            pnt = dss.PointOnShape1(i)
            t = _dist_params(dss, i)
            p1 = adapt.Value(max(adapt.FirstParameter(), t - 10 * CONFUSION))
            p2 = adapt.Value(min(adapt.LastParameter(), t + 10 * CONFUSION))
            d1, d2 = gp_Vec(p1, pnt).Dot(d), gp_Vec(p2, pnt).Dot(d)
            if abs(d1) > 5 * CONFUSION and abs(d2) > 5 * CONFUSION and d1 * d2 < 0:
                return True
        elif kind == BRepExtrema_IsVertex:
            vtx = TopoDS.Vertex(dss.SupportOnShape1(i))
            edges = v2e.FindFromKey(vtx)
            if edges.Extent() == 2:
                d = gp_Vec(line.Direction().Crossed(fnormal))
                pnt = dss.PointOnShape1(i)

                def near(e):
                    a = BRepAdaptor_Curve(TopoDS.Edge(e))
                    f, l = a.FirstParameter(), a.LastParameter()
                    if a.Value(f).SquareDistance(pnt) < a.Value(l).SquareDistance(pnt):
                        return a.Value(f + 2 * CONFUSION)
                    return a.Value(l - 2 * CONFUSION)
                p1, p2 = near(edges.First()), near(edges.Last())
                d1, d2 = gp_Vec(p1, pnt).Dot(d), gp_Vec(p2, pnt).Dot(d)
                if abs(d1) > CONFUSION and abs(d2) > CONFUSION and d1 * d2 < 0:
                    return True
    return False


# ── the up-to faces: findAllFacesCutBy along a circle, getUpToFace with an axis ──────────────────────────

def _faces_cut_by_axis(shape, face, axis):
    """Part::findAllFacesCutBy(shape, face, gp_Ax1): [(distsq, face)], distsq being the arc length from the profile's
    centre of gravity round the axis to where the circle through it meets each face."""
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    cog = props.CentreOfMass()
    loc, ad = axis.Location(), axis.Direction()
    a = cog.XYZ().Subtracted(loc.XYZ())
    par = a.Dot(ad.XYZ())
    center = gp_Pnt(loc.XYZ().Added(ad.XYZ().Multiplied(par)))
    line = gp_Lin(axis)
    radius = line.Distance(cog)
    out = []
    if radius < CONFUSION:
        return out
    circle = Geom_Circle(gce_MakeCirc(center, ad, radius).Value())
    adaptor = GeomAdaptor_Curve(circle)
    vx = gp_Dir(gp_Vec(center, cog))
    lcs = gp_Ax3(gp_Ax2(center, ad, vx))
    mat = gp_Trsf()
    mat.SetTransformation(lcs)
    inter = BRepIntCurveSurface_Inter()
    inter.Init(shape, adaptor, CONFUSION)
    while inter.More():
        ip = inter.Pnt()
        dsq = cog.SquareDistance(ip)
        if dsq >= CONFUSION:
            mk = gce_MakeDir(cog, ip)
            if mk.IsDone() and not mk.Value().IsParallel(ad, CONFUSION):
                il = ip.Transformed(mat)
                x = max(-radius, min(radius, il.X()))
                ang = math.acos(x / radius)
                if il.Y() < 0.0:
                    ang = 2.0 * math.pi - ang
                out.append((ang * radius, inter.Face()))
        inter.Next()
    return out


def _get_up_to_face_axis(upto, support, sketchshape, method, axis):
    """ProfileBased::getUpToFace(..., gp_Ax1)."""
    if method in ("UpToLast", "UpToFirst"):
        cut = _faces_cut_by_axis(support, sketchshape, axis) if support is not None else []
        if not cut:
            raise FeatureError("SketchBased: No faces found in this direction")
        cut = sorted(cut, key=lambda c: c[0])
        upto = cut[-1][1] if method == "UpToLast" else cut[0][1]
    if upto.ShapeType() != TopAbs_FACE:
        fs = F._faces(upto)
        if not fs:
            raise FeatureError("SketchBased: Up to face: No face found")
        upto = fs[0]
    face = TopoDS.Face(upto)
    adapt = BRepAdaptor_Surface(face)
    if adapt.GetType() == GeomAbs_Plane and \
            axis.Direction().IsParallel(adapt.Plane().Axis().Direction(), CONFUSION):
        raise FeatureError("SketchBased: Up to face: Must not be normal to rotation axis!")
    return face


# ── Revolved::tryExecuteRevolved ─────────────────────────────────────────────────────────────────────────

CUT, FUSE, NONE = 0, 1, 2                 # Part::RevolMode: CutFromBase, FuseWithBase, None


def _moved(shape, trsf):
    return shape.Moved(TopLoc_Location(trsf))


def _revol(face, axis, angle_total):
    """TopoShape::makeElementRevolve: BRepPrimAPI_MakeRevol."""
    mk = BRepPrimAPI_MakeRevol(face, axis, angle_total)
    mk.Build()
    if not mk.IsDone():
        raise FeatureError("Could not revolve the sketch!")
    return mk.Shape()


def _generate_revolution(sketchshape, axis, angle, angle2, midplane, method):
    """Revolved::generateRevolution, the angular form."""
    total, offset = angle, 0.0
    if method == "TwoAngles":
        total += angle2
        offset = -angle2
    elif method == "ThroughAll":
        total = 2 * math.pi
    elif midplane:
        offset = -angle / 2
    if abs(total) < ANGULAR:
        raise FeatureError("Cannot create a revolution with zero angle.")
    frm = sketchshape
    if method == "TwoAngles" or midplane:
        t = gp_Trsf()
        t.SetRotation(axis, offset)
        frm = _moved(frm, t)
    return _revol(frm, axis, total)


def _make_revolution(base, profile, axis, upto, mode, modify):
    """TopoShape::makeElementRevolution: BRepFeat_MakeRevol per profile face, from no support face."""
    if mode == NONE:
        modify = False
    if base is None:
        raise FeatureError("Null shape")
    m = mode
    result = base
    for f in F._faces(profile):
        mk = BRepFeat_MakeRevol()
        mk.Init(result, f, TopoDS_Face(), axis, m, modify)
        mk.Perform(upto)
        if not mk.IsDone():
            raise FeatureError("Revolution: Up to face: Could not revolve the sketch!")
        result = mk.Shape()
        if mode == NONE:
            m = FUSE
    if result is None or result.IsNull():
        raise FeatureError("Could not revolve the sketch!")
    return result


def _try_revolve_to_face(upto, axis, base, sketchshape, revol_mode):
    """Revolved::tryToRevolveToFace (the support face of a sketch on an origin plane has no wire: none)."""
    def generated(r):
        if base is None:
            return r
        return F._bool("cut", r, [base])

    if revol_mode == CUT:
        try:
            return F._bool("cut", base, [_make_revolution(base, sketchshape, axis, upto, CUT, True)])
        except Exception:
            pass                       # a side that removes nothing: go on and make the cutter itself
    try:
        return generated(_make_revolution(base, sketchshape, axis, upto, NONE, False))
    except Exception:
        pass
    try:
        return generated(_make_revolution(base, sketchshape, axis, upto, FUSE, True))
    except Exception:
        raise FeatureError("Could not revolve the sketch!") from None


def _uses_brepfeat(method, revol_mode):
    return method in ("UpToFirst", "UpToFace") or (method == "UpToLast" and revol_mode == FUSE)


def _clamp(deg, lo=-360.0, hi=360.0):
    """PropertyQuantityConstraint::setPyObject: a value past the constraint's bound is the bound."""
    return hi if deg > hi else lo if deg < lo else deg


def _revolve(feat: _Revolved, sketch, base, shapes, sketches, params):
    where = feat.name
    revol_mode = FUSE if feat.additive else CUT
    side, method, method2 = feat.side_type, feat.type, feat.type2
    # Angle, Angle2 and StartOffset are App::PropertyAngle with Revolved::floatAngle {-360, 360}: setting one from
    # Python (or an expression) clamps it to that range, so the too-large check below is FreeCAD's but never fires.
    angle_deg = _clamp(value(feat.angle, params, f"{where}.angle"))
    if abs(angle_deg) > 360.0:
        raise FeatureError("Angle of revolution too large")
    angle = math.radians(angle_deg)
    if side != "Two sides" and abs(angle) < ANGULAR and method == "Angle":
        raise FeatureError("Angle of revolution too small")
    angle2_deg = _clamp(value(feat.angle2, params, f"{where}.angle2"))
    if abs(angle2_deg) > 360.0:
        raise FeatureError("Angle of revolution too large")
    angle2 = math.radians(angle2_deg)
    if not feat.additive and base is None:
        # Groove with nothing to cut: getBaseTopoShape fails and FreeCAD's tryGetBaseShape leaves it null, so the
        # groove is the tool alone, as a Groove first in a Body is in FreeCAD.
        pass

    sketchshape = F.profile_face(sketch)
    pnt, dirv = get_axis(feat, sketch, shapes, sketches)
    if feat.project_axis and dirv.Magnitude() > 0:
        pnt, dirv = _project_axis(pnt, dirv, sketchshape)
    if dirv.Magnitude() < 1e-300:
        raise FeatureError("Reference axis is invalid")
    d = gp_Dir(dirv)
    if feat.reversed:
        d = d.Reversed()
    axis = gp_Ax1(pnt, d)
    start = math.radians(_clamp(value(feat.start_offset, params, f"{where}.start_offset"))) \
        if feat.start_type == "Offset" else 0.0
    if abs(start) >= ANGULAR:                             # Revolved::rotateProfileToStart
        t = gp_Trsf()
        t.SetRotation(axis, start)
        sketchshape = _moved(sketchshape, t)
    for f in F._faces(sketchshape):
        if check_line_crosses_face(gp_Lin(pnt, d), f):
            raise FeatureError("Revolve axis intersects the sketch")

    revolutions, fuse_sides = [], False

    def add(s):
        if s is not None and not s.IsNull():
            revolutions.append(s)

    def single(m, ang, utf, dd):
        """Revolved::generateSingleRevolutionSide."""
        through = m == "ThroughAll" and revol_mode == CUT
        if m == "Angle" or through:
            if m == "Angle" and abs(ang) < ANGULAR:
                return None
            return _generate_revolution(sketchshape, gp_Ax1(pnt, dd), ang, 0.0, False, m)
        if m in ("UpToFirst", "UpToFace") or (m == "UpToLast" and revol_mode == FUSE):
            ax = gp_Ax1(pnt, dd)
            upto = _up_to(m, utf, ax)
            return _try_revolve_to_face(upto, ax, base, sketchshape, revol_mode)
        raise FeatureError("ProfileBased: Internal error: Unknown method for generateSingleRevolutionSide()")

    def _up_to(m, utf, ax):
        if m == "UpToFace":
            if utf is None:
                raise FeatureError("SketchBased: No face selected")
            face = F._ref_face(utf, shapes, where)
        else:
            face = None
        return _get_up_to_face_axis(face, base, sketchshape, m, ax)

    if side == "Two sides":
        full = 2.0 * math.pi
        combined = angle + angle2
        through = revol_mode == CUT and (method == "ThroughAll" or method2 == "ThroughAll")
        covers = method == "Angle" and method2 == "Angle" and abs(combined) >= full - ANGULAR
        if through or covers:
            add(single("ThroughAll" if through else "Angle", full, feat.up_to_face, d))
        elif method == "Angle" and method2 == "Angle" and abs(combined) >= ANGULAR:
            add(_generate_revolution(sketchshape, gp_Ax1(pnt, d), angle, angle2, False, "TwoAngles"))
        else:
            fuse_sides = _uses_brepfeat(method, revol_mode) or _uses_brepfeat(method2, revol_mode)
            add(single(method, angle, feat.up_to_face, d))
            add(single(method2, angle2, feat.up_to_face2, d.Reversed()))
    elif side == "Symmetric":
        through = method == "ThroughAll" and revol_mode == CUT
        if method == "Angle" or through:
            add(_generate_revolution(sketchshape, gp_Ax1(pnt, d), angle, 0.0, True, method))
        else:
            fuse_sides = _uses_brepfeat(method, revol_mode)
            ax = gp_Ax1(pnt, d)
            upto = _up_to(method, feat.up_to_face, ax)
            one = _try_revolve_to_face(upto, ax, base, sketchshape, revol_mode)
            if one is not None and not one.IsNull():
                add(one)
                pln = _find_plane(sketchshape)
                if pln is None:
                    raise FeatureError("Could not determine the sketch plane!")
                mirror = gp_Trsf()
                mirror.SetMirror(gp_Ax2(pln.Location(), pln.Axis().Direction()))
                mirrored = BRepBuilderAPI_Transform(upto, mirror).Shape()
                add(_try_revolve_to_face(TopoDS.Face(mirrored), gp_Ax1(pnt, d.Reversed()), base, sketchshape,
                                         revol_mode))
    else:
        add(single(method, angle, feat.up_to_face, d))

    if not revolutions:
        raise FeatureError("No revolution geometry was generated")
    if len(revolutions) == 1:
        result = revolutions[0]
    elif fuse_sides:
        result = F._bool("fuse", revolutions[0], revolutions[1:])
    else:
        result = F._xor(revolutions)
    return _set_result(feat, base, result)


def _set_result(feat, base, revolved):
    """Revolved::setResult: the tool refined, then fused to (Revolution, BaseFirst) or cut from (Groove) the base and
    refined again."""
    if revolved is None or revolved.IsNull():
        raise FeatureError("Could not revolve the sketch!")
    refine = F._refine if feat.refine else (lambda s: s)
    result = refine(revolved)
    if base is not None:
        result = F._bool("fuse" if feat.additive else "cut", base, [result])
        result = refine(result)
    if not F._count(result, TopAbs_SOLID):
        raise FeatureError("Resulting shape is not a solid")
    return result


def command_defaults(feature: dict, sketch=None) -> dict:
    """What CmdPartDesignRevolution / CmdPartDesignGroove set on a new feature before its panel opens: ReferenceAxis
    the profile's V_Axis, Angle 360, and Reversed as suggestReversed says (feature_edit's add without them)."""
    out = dict(feature)
    out.setdefault("reference_axis", [feature.get("profile"), "V_Axis"])
    out.setdefault("angle", 360.0)
    if "reversed" not in feature and sketch is not None:
        cls = Revolution if feature.get("type") == "PartDesign::Revolution" else Groove
        try:
            f = cls("x", sketch.name, reference_axis=tuple(out["reference_axis"])
                    if isinstance(out["reference_axis"], list) else out["reference_axis"])
            out["reversed"] = suggest_reversed(f, sketch)
        except FeatureError:
            out["reversed"] = False
    return out


_Revolved.command_defaults = staticmethod(command_defaults)      # feature_edit's add calls it

# Last, so that importing this module first works: feature.py imports it back at its end, and finds it complete.
from . import feature as F  # noqa: E402
from .feature import FeatureError, value  # noqa: E402

__all__ = ["Revolution", "Groove", "get_axis", "suggest_reversed", "command_defaults", "check_line_crosses_face"]

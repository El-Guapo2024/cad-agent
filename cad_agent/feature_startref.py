# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses FreeCAD's start reference (StartType "Reference" with StartReference) for
# sketch-based features and keeps FreeCAD's licence, the GNU Lesser General Public License, version 2.1 or (at your
# option) any later version; the text is in ../ui/LICENSE.
#
#   Derived from: src/Mod/PartDesign/App/FeatureSketchBased.cpp (ProfileBased::getStartReferenceOffset,
#                 getPlanarStartReferenceDistance, getUpToFaceFromLinkSub, normalizeAngleRadians; Copyright (c) 2010
#                 Juergen Riegel <FreeCAD@juergen-riegel.net>) and src/Mod/PartDesign/App/FeatureRevolved.cpp
#                 (Revolved::getStartReferenceAngle, getPlanarStartReferenceAngle, getProfileOrbit; Copyright (c) 2010
#                 Juergen Riegel) and src/Mod/Part/App/TopoShape.cpp (getCenterOfGravity, getShapeProperties;
#                 Copyright (c) 2002 Jürgen Riegel)
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
"""Where a Pad, Pocket, Revolution or Groove starts when its StartType is "Reference".

    start_reference="XY_Plane" | ("Pad", "Face6") | ("Sketch001", "")

The profile is moved along the extrusion's direction (rotated about the revolution's axis) to the reference, then by
StartOffset. A planar reference takes the distance (angle) along the direction to its plane from the profile's centre of
gravity; any other face the nearest place the line (circle) through it meets the face, in either direction for an
extrusion, else "SketchBased: Start reference does not intersect the profile direction" ("Revolved: Start reference
does not intersect the profile path"). A sketch as the reference is its face (getTopoShapeVerifiedFace). With no
reference the offset is 0, as FreeCAD's. A Hole's profile is its sketch's shape (circles, points), not a face.
"""
from __future__ import annotations

import math

from . import feature as F

try:
    from OCP.BRep import BRep_Builder, BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.GeomAbs import GeomAbs_Plane
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SOLID, TopAbs_VERTEX
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS, TopoDS_Compound
    from OCP.gp import gp_Pnt, gp_Vec
except ImportError:                     # pragma: no cover - only FreeCAD's Python lands here
    pass

CONFUSION = 1e-7                        # Precision::Confusion()
ANGULAR = 1e-12                         # Precision::Angular()


def reference_shape(ref, shapes, where):
    """The StartReference as getStartReferenceOffset reads it: a sketch's face, or the face getUpToFaceFromLinkSub
    gives (an origin plane, a feature's FaceN)."""
    sketches = shapes.get("_sketches", {})
    name = ref if isinstance(ref, str) else ref[0] if isinstance(ref, (list, tuple)) and ref else None
    if name in sketches:                               # Part2DObject: its sub-element, else its verified face
        return F.profile_face(sketches[name])
    return F._ref_face(ref, shapes, where)


def center_of_gravity(shape):
    """TopoShape::getCenterOfGravity (getShapeProperties): a solid's, a face's, an edge's centre of mass, or the mean
    of the vertices."""
    props = GProp_GProps()
    if TopExp_Explorer(shape, TopAbs_SOLID).More():
        BRepGProp.VolumeProperties_s(shape, props)
    elif TopExp_Explorer(shape, TopAbs_FACE).More():
        BRepGProp.SurfaceProperties_s(shape, props)
    elif TopExp_Explorer(shape, TopAbs_EDGE).More():
        BRepGProp.LinearProperties_s(shape, props)
    else:
        xp, n, s = TopExp_Explorer(shape, TopAbs_VERTEX), 0, [0.0, 0.0, 0.0]
        while xp.More():
            p = BRep_Tool.Pnt_s(TopoDS.Vertex(xp.Current()))
            s, n = [s[0] + p.X(), s[1] + p.Y(), s[2] + p.Z()], n + 1
            xp.Next()
        return gp_Pnt(s[0] / n, s[1] / n, s[2] / n) if n else None
    return props.CentreOfMass()


def sketch_shape(sketch):
    """The sketch's Shape as a Hole's getProfileShape reads it: its curves as SketchObject joins them into wires, and
    its points, in the sketch's frame with the sketch's placement as the shape's location (Part::Feature's Shape keeps
    the Placement so; BRepGProp's surface properties of a shape with no face then centre on that location, which is
    where findAllFacesCutBy's line starts for a Hole)."""
    from OCP.TopLoc import TopLoc_Location
    builder, comp = BRep_Builder(), TopoDS_Compound()
    builder.MakeCompound(comp)
    edges = [F._edge(g) for g in sketch.geometry if not g.construction and not isinstance(g, F.Point)]
    for w in F._wires(edges):
        builder.Add(comp, w)
    for g in sketch.geometry:
        if isinstance(g, F.Point) and not g.construction:
            builder.Add(comp, BRepBuilderAPI_MakeVertex(gp_Pnt(g.point[0], g.point[1], 0.0)).Vertex())
    return comp.Moved(TopLoc_Location(F._trsf(sketch)))


def _first_face(shape):
    if shape.ShapeType() == TopAbs_FACE:
        return TopoDS.Face(shape)
    faces = F._faces(shape)
    return faces[0] if faces else None


def _planar_distance(profile, reference, d):
    """getPlanarStartReferenceDistance."""
    face = _first_face(reference)
    if face is None:
        return None
    surface = BRepAdaptor_Surface(face)
    if surface.GetType() != GeomAbs_Plane:
        return None
    centre = center_of_gravity(profile)
    if centre is None:
        return None
    normal = surface.Plane().Axis().Direction()
    den = gp_Vec(d).Dot(gp_Vec(normal))
    if abs(den) <= CONFUSION:
        return None
    return gp_Vec(centre, surface.Plane().Location()).Dot(gp_Vec(normal)) / den


def extrude_offset(profile, ref, d, offset: float, shapes, where) -> float:
    """ProfileBased::getStartReferenceOffset: how far along d the profile moves to start at ref, plus offset."""
    if ref is None:
        return 0.0
    reference = reference_shape(ref, shapes, where)
    distance = _planar_distance(profile, reference, d)
    if distance is not None:
        return distance + offset
    faces, factor = F._faces_cut_by(reference, profile, d), 1.0
    if not faces:
        faces, factor = F._faces_cut_by(reference, profile, d.Reversed()), -1.0
    if not faces:
        raise F.FeatureError("SketchBased: Start reference does not intersect the profile direction")
    return factor * math.sqrt(min(f[0] for f in faces)) + offset


def normalize_angle(angle: float) -> float:
    """PartDesign::normalizeAngleRadians: into [0, 2 pi), a hair below 2 pi as 0 (Base::fmod is never negative)."""
    full = 2.0 * math.pi
    angle = math.fmod(angle, full)
    if angle < 0.0:
        angle += full
    return 0.0 if full - angle < ANGULAR else angle


def _orbit(profile, axis):
    """getProfileOrbit: the foot of the profile's centre on the axis and the radial vector to it, or None."""
    p = center_of_gravity(profile)
    if p is None:
        return None
    av = gp_Vec(axis.Direction())
    t = gp_Vec(axis.Location(), p).Dot(av)
    centre = gp_Pnt(axis.Location().XYZ())
    centre.Translate(av.Multiplied(t))
    radial = gp_Vec(centre, p)
    return (centre, radial) if radial.Magnitude() > CONFUSION else None


def _planar_angle(profile, reference, axis):
    """getPlanarStartReferenceAngle: the smaller turn about the axis that brings the profile's centre onto the
    reference plane, or None."""
    face = _first_face(reference)
    if face is None:
        return None
    surface = BRepAdaptor_Surface(face)
    if surface.GetType() != GeomAbs_Plane:
        return None
    orbit = _orbit(profile, axis)
    if orbit is None:
        return None
    centre, radial = orbit
    plane = surface.Plane()
    normal = gp_Vec(plane.Axis().Direction())
    tangent = gp_Vec(axis.Direction()).Crossed(radial)
    cos_c, sin_c = radial.Dot(normal), tangent.Dot(normal)
    constant = gp_Vec(plane.Location(), centre).Dot(normal)
    amplitude = math.hypot(cos_c, sin_c)
    if amplitude <= CONFUSION:
        return 0.0 if abs(constant) <= CONFUSION else None
    solution = -constant / amplitude
    if solution < -1.0 - CONFUSION or solution > 1.0 + CONFUSION:
        return None
    phase = math.atan2(sin_c, cos_c)
    delta = math.acos(max(-1.0, min(1.0, solution)))
    return min(normalize_angle(phase + delta), normalize_angle(phase - delta))


def revolve_angle(profile, ref, axis, offset: float, shapes, where) -> float:
    """Revolved::getStartReferenceAngle (radians): the turn about axis to the reference, plus offset."""
    if ref is None:
        return 0.0
    from .feature_revolve import _faces_cut_by_axis
    reference = reference_shape(ref, shapes, where)
    angle = _planar_angle(profile, reference, axis)
    if angle is not None:
        return angle + offset
    orbit = _orbit(profile, axis)
    if orbit is None:
        raise F.FeatureError("Revolved: Cannot determine the profile path around the axis")
    faces = _faces_cut_by_axis(reference, profile, axis)
    if not faces:
        raise F.FeatureError("Revolved: Start reference does not intersect the profile path")
    return min(f[0] for f in faces) / orbit[1].Magnitude() + offset

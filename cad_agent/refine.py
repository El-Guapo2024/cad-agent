# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses FreeCAD's model refine (Part's BRepBuilderAPI_RefineModel and the
# ModelRefine namespace) function by function and keeps FreeCAD's licence, the GNU Lesser General Public License,
# version 2.1 or (at your option) any later version; the text is in ../ui/LICENSE.
#
#   Derived from: src/Mod/Part/App/modelRefine.cpp, modelRefine.h
#                 (Copyright (c) 2011 Thomas Anderson <blobfish[at]gmx.com>),
#                 src/Mod/Part/App/TopoShapeExpansion.cpp (TopoShape::makeElementRefine, fixSolidOrientation;
#                 Copyright (c) 2022 Zheng, Lei), src/Mod/Part/App/TopoShape.cpp (TopoShape::isClosed;
#                 Copyright (c) 2002 Jürgen Riegel) and src/Mod/PartDesign/App/FeatureRefine.cpp
#                 (FeatureRefine::refineShapeIfActive)
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
"""FreeCAD's own refine ("Refine shape (clean up redundant edges) after operations"), which PartDesign runs after
every feature whose Refine is true: TopoShape::makeElementRefine over Part::BRepBuilderAPI_RefineModel.

    refine(shape) -> shape

Per shell (FaceUniter::process): the faces of each surface type FreeCAD handles (plane, cylinder, B-spline) are split
into groups on the same surface (splitEqual), each group into edge-connected runs (FaceAdjacencySplitter), each run of
two or more faces is rebuilt as one face from its boundary (buildFace), the old faces are removed and the new ones sewn
in (BRepBuilderAPI_Sewing), and the edges between them fused (BRepLib_FuseEdges). The same OCCT calls in the same
order, so the faces come out in FreeCAD's order. FreeCAD is built on OCCT 8.0.1 here, as OCP is; modelRefine.cpp's
collectConicEdges branch (`#if OCC_VERSION_HEX <= 0x7fffff`, meant for OCCT 7) is taken there too, since 8.0.1 is 0x080001:
the edges on circles, ellipses and the other conics are kept from BRepLib_FuseEdges (AvoidEdges), so two arcs of one circle
that a refine puts on one face stay two edges, as in FreeCAD. The history FreeCAD keeps for
its element names (modifiedShapes, LogModifications) has no effect on the shape and is left out.
"""
from __future__ import annotations

import math

from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeSolid, BRepBuilderAPI_Sewing
from OCP.BRepGProp import BRepGProp
from OCP.BRepLib import (BRepLib, BRepLib_FaceDone, BRepLib_FuseEdges, BRepLib_MakeFace, BRepLib_MakeWire,
                         BRepLib_WireDone)
from OCP.BRepTools import BRepTools_ReShape
from OCP.Bnd import Bnd_Box
from OCP.GProp import GProp_GProps
from OCP.Geom import Geom_BSplineSurface, Geom_CylindricalSurface, Geom_Plane, Geom_RectangularTrimmedSurface
from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
from OCP.GeomAbs import GeomAbs_BSplineSurface, GeomAbs_Circle, GeomAbs_Cylinder, GeomAbs_Line, GeomAbs_Plane
from OCP.GeomAdaptor import GeomAdaptor_Surface
from OCP.Precision import Precision
from OCP.ShapeAnalysis import ShapeAnalysis_Curve, ShapeAnalysis_Shell
from OCP.ShapeBuild import ShapeBuild_ReShape
from OCP.ShapeExtend import ShapeExtend_Status
from OCP.ShapeFix import ShapeFix_Face
from OCP.Standard import Standard_Failure
from OCP.TopAbs import (TopAbs_COMPOUND, TopAbs_COMPSOLID, TopAbs_EDGE, TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID,
                        TopAbs_VERTEX, TopAbs_WIRE)
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_CompSolid, TopoDS_Iterator, TopoDS_Shell
from OCP.gp import gp_Ax3, gp_Pnt, gp_Vec
try:
    from OCP.TColgp import TColgp_Array2OfPnt, TColgp_SequenceOfPnt
    from OCP.TColStd import TColStd_Array1OfReal
except ImportError:                     # OCP 8 moved OCCT's collections
    from OCP.collections import Array1_double as TColStd_Array1OfReal
    from OCP.collections import Array2_gp_Pnt as TColgp_Array2OfPnt, Sequence_gp_Pnt as TColgp_SequenceOfPnt
try:
    from OCP.TopTools import (TopTools_DataMapOfShapeShape, TopTools_IndexedDataMapOfShapeListOfShape,
                              TopTools_ListOfShape, TopTools_MapOfShape)
except ImportError:
    from OCP.collections import (DataMap_TopoDS_Shape_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_DataMapOfShapeShape,
                                 IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher
                                 as TopTools_IndexedDataMapOfShapeListOfShape,
                                 List_TopoDS_Shape as TopTools_ListOfShape,
                                 Map_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_MapOfShape)

CONFUSION = Precision.Confusion_s()
ANGULAR = Precision.Angular_s()


class RefineFailed(Exception):
    """Standard_Failure("Removing splitter failed") and its kin: FreeCAD then keeps the shape unrefined."""


def _edges_of(shape) -> list:
    out, it = [], TopExp_Explorer(shape, TopAbs_EDGE)
    while it.More():
        out.append(TopoDS.Edge(it.Current()))
        it.Next()
    return out


def _faces_of(shape) -> list:
    out, it = [], TopExp_Explorer(shape, TopAbs_FACE)
    while it.More():
        out.append(TopoDS.Face(it.Current()))
        it.Next()
    return out


def get_face_edges(face) -> list:
    """ModelRefine::getFaceEdges: the face's edges in explorer order (a seam twice)."""
    return _edges_of(face)


def boundary_edges(faces) -> list:
    """ModelRefine::boundaryEdges: the edges that belong to one face of the group only (an edge met twice cancels)."""
    edges: list = []
    for face in faces:
        for fe in get_face_edges(face):
            for i, e in enumerate(edges):
                if e.IsSame(fe):
                    del edges[i]
                    break
            else:
                edges.append(fe)
    return edges


def remove_faces(shell, faces):
    """ModelRefine::removeFaces."""
    rebuilder = ShapeBuild_ReShape()
    for f in faces:
        rebuilder.Remove(f)
    out = rebuilder.Apply(shell)
    if out.IsNull() or out.ShapeType() != TopAbs_SHELL:
        raise RefineFailed("Removing splitter failed")
    return TopoDS.Shell(out)


def _square_extent(wire) -> float:
    box = Bnd_Box()
    BRepBndLib.Add_s(wire, box)
    return box.SquareExtent()


def _wire_sort(wires) -> list:
    """std::sort(wires, ModelRefine::WireSort()): the largest box first. libstdc++ sorts fewer than 17 elements by
    insertion, which keeps equal ones in order, as Python's stable sort does."""
    return sorted(wires, key=lambda w: -_square_extent(w))


def _fail(fixer) -> bool:
    return fixer.Status(ShapeExtend_Status.ShapeExtend_FAIL)


class FaceTypedBase:
    """ModelRefine::FaceTypedBase."""
    surface_type = None

    def is_equal(self, one, two) -> bool:
        raise NotImplementedError

    def build_face(self, faces):
        raise NotImplementedError

    @staticmethod
    def get_face_type(face):
        return GeomAdaptor_Surface(BRep_Tool.Surface_s(face)).GetType()

    def boundary_split(self, faces_in) -> list:
        """FaceTypedBase::boundarySplit: the boundary edges chained into closed loops, from the front of the list."""
        boundaries = []
        edges = boundary_edges(faces_in)
        while edges:
            destination = TopExp.FirstVertex_s(edges[0], True)
            last_vertex = TopExp.LastVertex_s(edges[0], True)
            boundary = [edges.pop(0)]
            if destination.IsSame(last_vertex):      # single edge closed check
                boundaries.append(boundary)
                continue
            closed = False
            i = 0
            while i < len(edges):
                current = TopExp.FirstVertex_s(edges[i], True)
                if last_vertex.IsSame(current):
                    boundary.append(edges[i])
                    last_vertex = TopExp.LastVertex_s(edges[i], True)
                    del edges[i]
                    i = 0
                    if last_vertex.IsSame(destination):
                        closed = True
                        break
                    continue
                i += 1
            if closed:
                boundaries.append(boundary)
        return boundaries

    def split_equal(self, faces) -> list:
        """FaceTypedBase::splitEqual: faces grouped with the first face of a group they equal; groups of two or more."""
        groups: list = []
        for face in faces:
            for g in groups:
                if self.is_equal(g[0], face):
                    g.append(face)
                    break
            else:
                groups.append([face])
        return [g for g in groups if len(g) >= 2]


def _surface_of(face, cls):
    """getGeomPlane / getGeomCylinder: the face's surface as cls, or the basis of a rectangular trimmed one."""
    surface = BRep_Tool.Surface_s(face)
    if surface is None:
        return None
    if isinstance(surface, cls):
        return surface
    if isinstance(surface, Geom_RectangularTrimmedSurface):
        basis = surface.BasisSurface()
        if isinstance(basis, cls):
            return basis
    return None


def _wires_of(boundaries, check=False):
    wires = []
    for boundary in boundaries:
        mk = BRepLib_MakeWire()
        for e in boundary:
            mk.Add(e)
        if check and mk.Error() != BRepLib_WireDone:
            return None
        wires.append(mk.Wire())
    return wires


class FaceTypedPlane(FaceTypedBase):
    surface_type = GeomAbs_Plane

    def is_equal(self, one, two) -> bool:
        s1, s2 = _surface_of(one, Geom_Plane), _surface_of(two, Geom_Plane)
        if s1 is None or s2 is None:
            return False
        p1, p2 = s1.Pln(), s2.Pln()
        return (p1.Position().Direction().IsParallel(p2.Position().Direction(), CONFUSION)
                and p1.Distance(p2.Position().Location()) < CONFUSION)

    def build_face(self, faces):
        split = self.boundary_split(faces)
        if not split:
            return None
        wires = _wire_sort(_wires_of(split))
        maker = BRepLib_MakeFace(wires[0], True)
        if maker.Error() != BRepLib_FaceDone:
            return None
        current = maker.Face()
        if len(wires) > 1:
            fix = ShapeFix_Face(current)
            fix.SetContext(ShapeBuild_ReShape())
            for w in wires[1:]:
                fix.Add(w)
            fix.Perform()
            if _fail(fix):
                return None
            fix.FixOrientation()
            fix.Perform()
            if _fail(fix):
                return None
            current = fix.Face()
        return current


def _fix_face(f):
    """fixFace: ShapeFix_Face, then the missing seam, then the orientation, each with a fresh context."""
    fixer = ShapeFix_Face(f)
    fixer.SetContext(ShapeBuild_ReShape())
    fixer.Perform()
    if _fail(fixer):
        return None
    fixer.FixMissingSeam()
    fixer.SetContext(ShapeBuild_ReShape())
    fixer.Perform()
    if _fail(fixer):
        return None
    fixer.FixOrientation()
    fixer.SetContext(ShapeBuild_ReShape())
    fixer.Perform()
    if _fail(fixer):
        return None
    return fixer.Face()


def _wire_encircles_axis(wire, cylinder) -> bool:
    """wireEncirclesAxis: the wire's length around the axis, signed; more than half a turn means it goes round."""
    radius = cylinder.Radius()
    ax = cylinder.Axis()
    cv = gp_Vec(ax.Location().X(), ax.Location().Y(), ax.Location().Z())
    av = gp_Vec(ax.Direction().X(), ax.Direction().Y(), ax.Direction().Z())
    plane = Geom_Plane(gp_Ax3(ax.Location(), ax.Direction()))
    total = 0.0
    first_segment = second_segment = False
    first = last = None
    it = TopExp_Explorer(wire, TopAbs_EDGE)
    while it.More():
        segment = TopoDS.Edge(it.Current())
        it.Next()
        adapt = BRepAdaptor_Curve(segment)
        fp, lp = adapt.FirstParameter(), adapt.LastParameter()
        seg_first, seg_tangent = gp_Pnt(), gp_Vec()
        adapt.D1(fp, seg_first, seg_tangent)
        seg_last = adapt.Value(lp)
        length = 0.0
        if adapt.GetType() == GeomAbs_Line:
            length = 0.0
        elif adapt.GetType() == GeomAbs_Circle:
            length = (lp - fp) * radius
            proj = GeomAPI_ProjectPointOnSurf(seg_first, plane)
            p = proj.Point(1)
            bv = gp_Vec(p.X(), p.Y(), p.Z())
            if (bv - cv).Crossed(seg_tangent).IsOpposite(av, CONFUSION):
                length = -length
        else:
            seq = TColgp_SequenceOfPnt()
            if adapt.IsCurveOnSurface():
                if BRepLib.BuildCurves3d_s(segment):
                    adapt.Initialize(segment)
            if adapt.Is3DCurve():
                ShapeAnalysis_Curve.GetSamplePoints_s(adapt.Curve().Curve(), fp, lp, seq)
            begin = None
            for j in range(1, seq.Length() + 1):
                end = seq.Value(j)
                proj = GeomAPI_ProjectPointOnSurf(end, plane)
                if not proj.IsDone():
                    return False
                pend = proj.Point(1)
                if j > 1:
                    bv = gp_Vec(begin.X(), begin.Y(), begin.Z())
                    dv = gp_Vec(pend.X(), pend.Y(), pend.Z()) - bv
                    dist = dv.Magnitude()
                    if dist > 0:
                        if (bv - cv).Crossed(dv).IsOpposite(av, CONFUSION):
                            dist = -dist
                        length += dist
                begin = pend
        if not first_segment:
            first_segment = True
            first, last = seg_first, seg_last
        elif not second_segment:
            second_segment = True
            if last.IsEqual(seg_first, CONFUSION):
                last = seg_last
            elif last.IsEqual(seg_last, CONFUSION):
                last = seg_first
                length = -length
            elif first.IsEqual(seg_last, CONFUSION):
                last = seg_first
                total = -total
                length = -length
            else:
                last = seg_last
                total = -total
        else:
            if not last.IsEqual(seg_first, CONFUSION):
                length = -length
                last = seg_first
            else:
                last = seg_last
        total += length
    return abs(total) > math.pi * radius


class FaceTypedCylinder(FaceTypedBase):
    surface_type = GeomAbs_Cylinder

    def is_equal(self, one, two) -> bool:
        s1, s2 = _surface_of(one, Geom_CylindricalSurface), _surface_of(two, Geom_CylindricalSurface)
        if s1 is None or s2 is None:
            return False
        c1, c2 = s1.Cylinder(), s2.Cylinder()
        if abs(c1.Radius() - c2.Radius()) > CONFUSION:
            return False
        if (not c1.Axis().IsCoaxial(c2.Axis(), ANGULAR, CONFUSION)
                and not c1.Axis().IsCoaxial(c2.Axis().Reversed(), ANGULAR, CONFUSION)):
            return False
        return True

    def build_face(self, faces):
        boundaries = self.boundary_split(faces)
        if not boundaries:
            return None
        all_wires = _wires_of(boundaries, check=True)
        if not all_wires:
            return None
        all_wires = _wire_sort(all_wires)
        surface = _surface_of(faces[0], Geom_CylindricalSurface)
        if surface is None:
            return None
        inner, encircling = [], []
        for w in all_wires:
            (encircling if _wire_encircles_axis(w, surface) else inner).append(w)
        if not encircling:
            maker = BRepBuilderAPI_MakeFace(surface, all_wires[0])
            if not maker.IsDone():
                return None
            for w in all_wires[1:]:
                maker.Add(w)
                if not maker.IsDone():
                    return None
            return _fix_face(maker.Face())
        if len(encircling) != 2:
            return None
        if not inner:
            maker = BRepBuilderAPI_MakeFace(surface, encircling[0])
            if not maker.IsDone():
                return None
            maker.Add(encircling[-1])
            if not maker.IsDone():
                return None
            return _fix_face(maker.Face())
        # the inner wires first, because otherwise those that cut the seam edge will fail
        maker = BRepBuilderAPI_MakeFace(surface, inner[0], False)
        if not maker.IsDone():
            return None
        for w in inner[1:]:
            maker.Add(w)
            if not maker.IsDone():
                return None
        maker.Add(encircling[0])
        if not maker.IsDone():
            return None
        maker.Add(encircling[-1])
        if not maker.IsDone():
            return None
        return _fix_face(maker.Face())

    def boundary_split(self, faces_in) -> list:
        """FaceTypedCylinder::boundarySplit: from the back of the list, a seam's twin skipped."""
        boundaries = []
        edges = boundary_edges(faces_in)
        while edges:
            destination = TopExp.FirstVertex_s(edges[-1], True)
            last_vertex = TopExp.LastVertex_s(edges[-1], True)
            closed = False
            boundary = [edges.pop()]
            if destination.IsSame(last_vertex):
                closed = True
            else:
                i = 0
                while i < len(edges):
                    current = TopExp.FirstVertex_s(edges[i], True)
                    if edges[i].IsSame(boundary[-1]):
                        i += 1
                        continue
                    if last_vertex.IsSame(current):
                        boundary.append(edges[i])
                        last_vertex = TopExp.LastVertex_s(edges[i], True)
                        if last_vertex.IsSame(destination):
                            closed = True
                            del edges[i]
                            break
                        del edges[i]
                        i = 0
                        continue
                    i += 1
            if closed:
                boundaries.append(boundary)
        return boundaries


class _BSplineHelper:
    """BSplineEqulityHelper: the surface, its poles and closedness, read once."""

    def __init__(self, face):
        self.surface = BRep_Tool.Surface_s(face)
        if not isinstance(self.surface, Geom_BSplineSurface):
            self.surface = None
            return
        s = self.surface
        self.poles = TColgp_Array2OfPnt(1, s.NbUPoles(), 1, s.NbVPoles())
        s.Poles(self.poles)
        self.u_closed, self.v_closed = s.IsUClosed(), s.IsVClosed()


def _knots(n, getter):
    a = TColStd_Array1OfReal(1, n)
    getter(a)
    return [a.Value(i) for i in range(1, n + 1)]


def _knot_sequence_size(s, u: bool) -> int:
    poles, degree = (s.NbUPoles(), s.UDegree()) if u else (s.NbVPoles(), s.VDegree())
    if (s.IsUPeriodic() if u else s.IsVPeriodic()):
        return poles + 2 * degree - (s.UMultiplicity(1) if u else s.VMultiplicity(1)) + 2
    return poles + degree + 1


def _bspline_equal(h1: _BSplineHelper, h2: _BSplineHelper) -> bool:
    """FaceTypedBSplineIsEqual: the same rationality, periodicity, closedness, degrees, poles, knots and sequences."""
    s1, s2 = h1.surface, h2.surface
    if s1 is None or s2 is None:
        return False
    if (s1.IsURational() != s2.IsURational() or s1.IsVRational() != s2.IsVRational()
            or s1.IsUPeriodic() != s2.IsUPeriodic() or s1.IsVPeriodic() != s2.IsVPeriodic()
            or h1.u_closed != h2.u_closed or h1.v_closed != h2.v_closed
            or s1.UDegree() != s2.UDegree() or s1.VDegree() != s2.VDegree()):
        return False
    nu, nv = s1.NbUPoles(), s1.NbVPoles()
    if nu != s2.NbUPoles() or nv != s2.NbVPoles():
        return False
    for i in range(1, nu + 1):
        for j in range(1, nv + 1):
            if not h1.poles.Value(i, j).IsEqual(h2.poles.Value(i, j), CONFUSION):
                return False
    if s1.NbUKnots() != s2.NbUKnots() or s1.NbVKnots() != s2.NbVKnots():
        return False
    if _knots(s1.NbUKnots(), s1.UKnots) != _knots(s2.NbUKnots(), s2.UKnots):
        return False
    if _knots(s1.NbVKnots(), s1.VKnots) != _knots(s2.NbVKnots(), s2.VKnots):
        return False
    nus, nvs = _knot_sequence_size(s1, True), _knot_sequence_size(s1, False)
    if nus != _knot_sequence_size(s2, True) or nvs != _knot_sequence_size(s2, False):
        return False
    if _knots(nus, s1.UKnotSequence) != _knots(nus, s2.UKnotSequence):
        return False
    return _knots(nvs, s1.VKnotSequence) == _knots(nvs, s2.VKnotSequence)


class FaceTypedBSpline(FaceTypedBase):
    surface_type = GeomAbs_BSplineSurface

    def is_equal(self, one, two) -> bool:
        try:
            return _bspline_equal(_BSplineHelper(one), _BSplineHelper(two))
        except Standard_Failure:
            return False

    def build_face(self, faces):
        split = self.boundary_split(faces)
        if not split:
            return None
        wires = _wire_sort(_wires_of(split))
        surface = BRep_Tool.Surface_s(faces[0])
        if not isinstance(surface, Geom_BSplineSurface):
            return None
        maker = BRepBuilderAPI_MakeFace(surface, wires[0])
        if not maker.IsDone():
            return None
        for w in wires[1:]:
            maker.Add(w)
            if not maker.IsDone():
                return None
        fixer = ShapeFix_Face(maker.Face())
        fixer.SetContext(ShapeBuild_ReShape())
        fixer.Perform()
        if _fail(fixer):
            return None
        fixer.FixOrientation()
        fixer.Perform()
        if _fail(fixer):
            return None
        return fixer.Face()

    def split_equal(self, faces) -> list:
        try:
            groups: list = []
            for face in faces:
                h = _BSplineHelper(face)
                for g in groups:
                    if _bspline_equal(g[0][1], h):
                        g.append((face, h))
                        break
                else:
                    groups.append([(face, h)])
            return [[f for f, _ in g] for g in groups if len(g) >= 2]
        except Standard_Failure:
            return []


TYPE_OBJECTS = (FaceTypedPlane(), FaceTypedCylinder(), FaceTypedBSpline())   # FaceUniter::process's typeObjects


class FaceAdjacencySplitter:
    """ModelRefine::FaceAdjacencySplitter: runs of faces that share an edge, found depth first."""

    def __init__(self, shell):
        self.face_to_edge = TopTools_IndexedDataMapOfShapeListOfShape()
        for face in _faces_of(shell):
            lst = TopTools_ListOfShape()
            for e in _edges_of(face):
                lst.Append(e)
            self.face_to_edge.Add(face, lst)
        self.edge_to_face = TopTools_IndexedDataMapOfShapeListOfShape()
        TopExp.MapShapesAndAncestors_s(shell, TopAbs_EDGE, TopAbs_FACE, self.edge_to_face)

    def split(self, faces_in) -> list:
        self.faces_in = TopTools_MapOfShape()
        self.processed = TopTools_MapOfShape()
        groups = []
        for f in faces_in:
            self.faces_in.Add(f)
        for f in faces_in:
            if self.processed.Contains(f):
                continue
            temp: list = []
            self.processed.Add(f)
            self._find(f, temp)
            if len(temp) > 1:
                groups.append(temp)
        return groups

    def _find(self, face, out: list) -> None:
        out.append(face)
        for edge in self.face_to_edge.FindFromKey(face):
            for f in self.edge_to_face.FindFromKey(edge):
                if not self.faces_in.Contains(f):
                    continue
                if self.processed.Contains(f):
                    continue
                self.processed.Add(f)
                self._find(TopoDS.Face(f), out)


def collect_conic_edges(shell):
    """collectConicEdges: the shell's edges (TopExp::MapShapes order) whose 3D curve is a Geom_Conic."""
    from OCP.Geom import Geom_Conic
    from OCP.TopExp import TopExp
    from OCP.TopoDS import TopoDS
    try:
        from OCP.TopTools import TopTools_IndexedMapOfShape
    except ImportError:                     # OCP 8 moved OCCT's collections
        from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedMapOfShape
    edges, out = TopTools_IndexedMapOfShape(), TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shell, TopAbs_EDGE, edges)
    for i in range(1, edges.Extent() + 1):
        e = edges.FindKey(i)
        if e.IsNull():
            continue
        curve = BRep_Tool.Curve_s(TopoDS.Edge(e), 0.0, 0.0)
        if curve is not None and isinstance(curve, Geom_Conic):
            out.Add(e)
    return out


def _sewn_shell(shape):
    if shape.IsNull() or shape.ShapeType() != TopAbs_SHELL:
        raise RefineFailed("Removing splitter failed")
    return TopoDS.Shell(shape)


class FaceUniter:
    """ModelRefine::FaceUniter."""

    def __init__(self, shell):
        self.work_shell = shell
        self.modified = False

    def process(self) -> bool:
        if self.work_shell.IsNull():
            return False
        check_final_shell = False
        typed: dict = {t.surface_type: [] for t in TYPE_OBJECTS}         # FaceTypeSplitter
        for face in _faces_of(self.work_shell):
            kind = FaceTypedBase.get_face_type(face)
            if kind in typed:
                typed[kind].append(face)
        faces_to_remove: list = []
        faces_to_sew: list = []
        adjacency = FaceAdjacencySplitter(self.work_shell)
        for t in TYPE_OBJECTS:
            for group in t.split_equal(typed[t.surface_type]):
                for run in adjacency.split(group):
                    new_face = t.build_face(run)
                    if new_face is not None and not new_face.IsNull():
                        if run and new_face.Orientation() != run[0].Orientation():
                            check_final_shell = True
                        faces_to_sew.append(new_face)
                        faces_to_remove.extend(run)
        if not faces_to_sew:
            return True
        self.modified = True
        self.work_shell = remove_faces(self.work_shell, faces_to_remove)
        empty = not TopExp_Explorer(self.work_shell, TopAbs_FACE).More()
        if not empty or len(faces_to_sew) > 1:
            sew = BRepBuilderAPI_Sewing()
            sew.Add(self.work_shell)
            for f in faces_to_sew:
                sew.Add(f)
            sew.Perform()
            sewed = sew.SewedShape()
            if sewed.IsNull() or sewed.ShapeType() != TopAbs_SHELL:
                return False                     # TopoDS::Shell throws: Standard_Failure caught, false
            self.work_shell = TopoDS.Shell(sewed)
        else:
            builder = BRep_Builder()
            shell = TopoDS_Shell()
            builder.MakeShell(shell)
            for f in faces_to_sew:
                builder.Add(shell, f)
            self.work_shell = shell
        fuse = BRepLib_FuseEdges(self.work_shell)
        fuse.AvoidEdges(collect_conic_edges(self.work_shell))     # OCC_VERSION_HEX 0x080001 <= 0x7fffff
        affected = TopTools_DataMapOfShapeShape()
        fuse.Faces(affected)
        for value in _values(affected):
            ShapeFix_Face(TopoDS.Face(value)).Perform()
        self.work_shell = _sewn_shell(fuse.Shape())
        if check_final_shell:
            check = ShapeAnalysis_Shell()
            check.LoadShells(self.work_shell)
            if not check.HasFreeEdges():
                props = GProp_GProps()
                BRepGProp.VolumeProperties_s(self.work_shell, props)
                if props.Mass() < 0:
                    self.work_shell = TopoDS.Shell(self.work_shell.Reversed())
        return True

    def fix_orientation(self, shell) -> None:
        if shell.Orientation() != self.work_shell.Orientation():
            self.work_shell.Reverse()


def _values(datamap) -> list:
    """A DataMap's values in its iterator's order (NCollection_DataMap's begin() gives the values)."""
    return list(datamap)


def refine_model(shape):
    """Part::BRepBuilderAPI_RefineModel::Build: each shell of a solid, a shell, or each solid and free shell of a
    compound, with the compound's faces, wires, edges and vertices carried over."""
    if shape.IsNull():
        raise RefineFailed("Cannot remove splitter from empty shape")
    kind = shape.ShapeType()
    if kind == TopAbs_SOLID:
        mk = BRepBuilderAPI_MakeSolid()
        it = TopExp_Explorer(shape, TopAbs_SHELL)
        while it.More():
            current = TopoDS.Shell(it.Current())
            it.Next()
            uniter = FaceUniter(current)
            if not uniter.process():
                raise RefineFailed("Removing splitter failed")
            mk.Add(uniter.work_shell if uniter.modified else current)
        return mk.Solid()
    if kind == TopAbs_SHELL:
        uniter = FaceUniter(TopoDS.Shell(shape))
        if not uniter.process():
            raise RefineFailed("Removing splitter failed")
        return uniter.work_shell
    if kind == TopAbs_COMPOUND:
        builder = BRep_Builder()
        comp = TopoDS_Compound()
        builder.MakeCompound(comp)
        xp = TopExp_Explorer(shape, TopAbs_SOLID)
        while xp.More():
            solid = xp.Current()
            xp.Next()
            reshape = BRepTools_ReShape()
            count = 0
            it = TopExp_Explorer(solid, TopAbs_SHELL)
            while it.More():
                count += 1
                current = TopoDS.Shell(it.Current())
                it.Next()
                uniter = FaceUniter(current)
                if uniter.process() and uniter.modified:
                    if count > 1:
                        uniter.fix_orientation(current)
                    reshape.Replace(current, uniter.work_shell)
            builder.Add(comp, reshape.Apply(solid))
        xp = TopExp_Explorer(shape, TopAbs_SHELL, TopAbs_SOLID)
        while xp.More():
            uniter = FaceUniter(TopoDS.Shell(xp.Current()))
            xp.Next()
            if uniter.process():
                builder.Add(comp, uniter.work_shell)
        for kind, avoid in ((TopAbs_FACE, TopAbs_SHELL), (TopAbs_WIRE, TopAbs_FACE), (TopAbs_EDGE, TopAbs_WIRE),
                            (TopAbs_VERTEX, TopAbs_EDGE)):
            xp = TopExp_Explorer(shape, kind, avoid)
            while xp.More():
                if not xp.Current().IsNull():
                    builder.Add(comp, xp.Current())
                xp.Next()
        return comp
    return shape


def is_closed(shape) -> bool:
    """TopoShape::isClosed."""
    if shape is None or shape.IsNull():
        return False
    kind = shape.ShapeType()
    if kind in (TopAbs_SHELL, TopAbs_WIRE, TopAbs_EDGE):
        return bool(BRep_Tool.IsClosed_s(shape))
    if kind in (TopAbs_COMPSOLID, TopAbs_SOLID):
        closed = True
        xp = TopExp_Explorer(shape, TopAbs_SHELL)
        while xp.More():
            closed &= bool(BRep_Tool.IsClosed_s(xp.Current()))
            xp.Next()
        return closed
    if kind == TopAbs_COMPOUND:
        closed = True
        for k, avoid in ((TopAbs_SHELL, None), (TopAbs_FACE, TopAbs_SHELL), (TopAbs_WIRE, TopAbs_FACE),
                         (TopAbs_EDGE, TopAbs_WIRE), (TopAbs_VERTEX, TopAbs_EDGE)):
            xp = TopExp_Explorer(shape, k) if avoid is None else TopExp_Explorer(shape, k, avoid)
            while xp.More():
                closed &= bool(BRep_Tool.IsClosed_s(xp.Current()))
                xp.Next()
        return closed
    return bool(BRep_Tool.IsClosed_s(shape))       # a face, a vertex


def fix_solid_orientation(shape):
    """TopoShape::fixSolidOrientation: BRepLib::OrientClosedSolid on a solid, or on each child of a compound."""
    if shape is None or shape.IsNull():
        return shape, False
    kind = shape.ShapeType()
    if kind == TopAbs_SOLID:
        solid = TopoDS.Solid(shape)
        BRepLib.OrientClosedSolid_s(solid)
        if solid.IsEqual(shape):
            return shape, False
        return solid, True
    if kind in (TopAbs_COMPOUND, TopAbs_COMPSOLID):
        subs, touched = [], False
        it = TopoDS_Iterator(shape)
        while it.More():
            s, t = fix_solid_orientation(it.Value())
            subs.append(s)
            touched |= t
            it.Next()
        if not touched:
            return shape, False
        builder = BRep_Builder()
        comp = TopoDS_Compound() if kind == TopAbs_COMPOUND else TopoDS_CompSolid()
        (builder.MakeCompound if kind == TopAbs_COMPOUND else builder.MakeCompSolid)(comp)
        for s in subs:
            if not s.IsNull():
                builder.Add(comp, s)
        return comp, True
    return shape, False


def refine(shape):
    """FeatureRefine::refineShapeIfActive over TopoShape::makeElementRefine: the refined shape with its solids
    oriented, or the shape as it was when the refine fails ("Refine failed: ..." is FreeCAD's warning) or changes
    whether it is closed."""
    if shape is None or shape.IsNull():
        return shape
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
    from OCP.BRepCheck import BRepCheck_Analyzer
    closed = is_closed(shape)
    # Not FreeCAD's: a refine that leaves a valid shape invalid is not kept. RefineModel's cylinder uniter is sensitive to
    # the last digits of its input (a helix fused to a cylinder whose edges differ from FreeCAD's by 1e-12 in tolerance:
    # FreeCAD's own removeSplitter makes the same invalid face from it), and the unrefined shape is FreeCAD's there. The
    # refine runs on a copy then, since its ShapeFix calls change the edges they fix in place.
    valid = BRepCheck_Analyzer(shape).IsValid()
    work = BRepBuilderAPI_Copy(shape).Shape() if valid else shape
    try:
        out = refine_model(work)
    except (RefineFailed, Standard_Failure):
        return shape
    out, _ = fix_solid_orientation(out)
    if is_closed(out) != closed:
        return shape
    if valid and not BRepCheck_Analyzer(out).IsValid():
        return shape
    return out

# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses FreeCAD's Part module (AppPartPy.cpp's functions, Copyright (c) 2002 Juergen
# Riegel) and keeps FreeCAD's licence, the GNU Lesser General Public License, version 2.1 or (at your option) any later
# version; the text is in ../../ui/LICENSE. FreeCAD (https://github.com/FreeCAD/FreeCAD), commit 3160daf1e2b6. See
# ../../NOTICE.
"""FreeCAD's Part module for the CAM workbench's Python (cad_agent/fcshim): shapes (_fc_part.py), geometry
(_fc_geom.py) and AppPartPy's functions."""
from __future__ import annotations

import math

from OCP.BRep import BRep_Tool
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakePolygon
from OCP.BRepLib import BRepLib
from OCP.BRepPrimAPI import (BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCone, BRepPrimAPI_MakeCylinder,
                             BRepPrimAPI_MakeSphere)
from OCP.Geom import Geom_Circle
from OCP.TopAbs import TopAbs_EDGE, TopAbs_VERTEX
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Ax2, gp_Circ, gp_Dir, gp_Pnt

from cad_agent.fcshim._fc_base import Vector, vec
from cad_agent.fcshim._fc_geom import (Arc, ArcOfCircle, ArcOfConic, ArcOfEllipse, BezierCurve, BezierSurface, BSplineCurve,  # noqa: F401
                       BSplineSurface, Circle, Cone, Conic, Curve, Cylinder, Ellipse, Geometry, GeometrySurface,
                       Hyperbola, Line, LineSegment, OffsetCurve, OffsetSurface, Parabola, Plane, PlateSurface,
                       Sphere, SurfaceOfExtrusion, SurfaceOfRevolution, Toroid, TrimmedCurve)
from cad_agent.fcshim._fc_part import (Compound, CompSolid, Edge, Face, OCCError, Shape, Shell, Solid, Vertex, Wire,  # noqa: F401
                       topods, wrap)

GeomCurve = Curve
GeomSurface = GeometrySurface


def _pnt(v):
    v = vec(v)
    return gp_Pnt(v.x, v.y, v.z)


def _dir(v):
    v = vec(v)
    return gp_Dir(v.x, v.y, v.z)


def show(shape, name=None):
    return None


def makeLine(p1, p2):
    mk = BRepBuilderAPI_MakeEdge(_pnt(p1), _pnt(p2))
    if not mk.IsDone():
        raise OCCError("Failed to create line")
    return Edge(mk.Edge())


def makePolygon(points, closed=False):
    mk = BRepBuilderAPI_MakePolygon()
    for p in points:
        mk.Add(_pnt(p))
    if not mk.IsDone():
        raise OCCError("Cannot create polygon because less than two vertices are given")
    if closed and not mk.FirstVertex().IsSame(mk.LastVertex()):
        mk.Add(mk.FirstVertex())
    return Wire(mk.Wire())


def makeCircle(radius, pnt=None, dir=None, angle1=0.0, angle2=360.0):  # noqa: A002
    loc = _pnt(pnt) if pnt is not None else gp_Pnt(0, 0, 0)
    d = _dir(dir) if dir is not None else gp_Dir(0, 0, 1)
    circ = gp_Circ(gp_Ax2(loc, d), float(radius))
    curve = Geom_Circle(circ)
    if angle1 == 0.0 and angle2 == 360.0:
        mk = BRepBuilderAPI_MakeEdge(curve)
    else:
        mk = BRepBuilderAPI_MakeEdge(curve, math.radians(angle1), math.radians(angle2))
    return Edge(mk.Edge())


def makeBox(length, width, height, pnt=None, dir=None):  # noqa: A002
    p = _pnt(pnt) if pnt is not None else gp_Pnt(0, 0, 0)
    d = _dir(dir) if dir is not None else gp_Dir(0, 0, 1)
    if length < 1e-7:
        raise OCCError("length of box too small")
    if width < 1e-7:
        raise OCCError("width of box too small")
    if height < 1e-7:
        raise OCCError("height of box too small")
    return Solid(BRepPrimAPI_MakeBox(gp_Ax2(p, d), float(length), float(width), float(height)).Shape())


def makeCylinder(radius, height, pnt=None, dir=None, angle=360.0):  # noqa: A002
    p = _pnt(pnt) if pnt is not None else gp_Pnt(0, 0, 0)
    d = _dir(dir) if dir is not None else gp_Dir(0, 0, 1)
    return Solid(BRepPrimAPI_MakeCylinder(gp_Ax2(p, d), float(radius), float(height),
                                          math.radians(float(angle))).Shape())


def makeCone(radius1, radius2, height, pnt=None, dir=None, angle=360.0):  # noqa: A002
    p = _pnt(pnt) if pnt is not None else gp_Pnt(0, 0, 0)
    d = _dir(dir) if dir is not None else gp_Dir(0, 0, 1)
    return Solid(BRepPrimAPI_MakeCone(gp_Ax2(p, d), float(radius1), float(radius2), float(height),
                                      math.radians(float(angle))).Shape())


def makeSphere(radius, pnt=None, dir=None, angle1=-90.0, angle2=90.0, angle3=360.0):  # noqa: A002
    p = _pnt(pnt) if pnt is not None else gp_Pnt(0, 0, 0)
    d = _dir(dir) if dir is not None else gp_Dir(0, 0, 1)
    return Solid(BRepPrimAPI_MakeSphere(gp_Ax2(p, d), float(radius), math.radians(angle1), math.radians(angle2),
                                        math.radians(angle3)).Shape())


def makeCompound(shapes, force=True, op=None):
    return Compound(list(shapes))


def makeShell(faces):
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Shell
    b, sh = BRep_Builder(), TopoDS_Shell()
    b.MakeShell(sh)
    for f in faces:
        b.Add(sh, topods(f))
    return wrap(sh)


def makeSolid(shape):
    return Solid(shape)


def makeFace(shapes, maker="Part::FaceMakerSimple", op=None):
    from cad_agent.feature_part_face import make_face
    if isinstance(shapes, Shape):
        comp = topods(shapes)
    else:
        comp = topods(Compound(list(shapes)))
    return wrap(make_face(comp, maker))


def makeHelix(pitch, height, radius, angle=-1.0, leftHanded=False, vertHeight=False):
    from cad_agent.feature_sweep import make_helix
    return wrap(make_helix(pitch, height, radius, angle, leftHanded, vertHeight))


def _edge_points(e):
    xp = TopExp_Explorer(e, TopAbs_VERTEX)
    v1 = BRep_Tool.Pnt_s(TopoDS.Vertex(xp.Current()))
    xp.Next()
    v2 = BRep_Tool.Pnt_s(TopoDS.Vertex(xp.Current()))
    return v1, v2


def _sort_edges(tol3d, edges):
    """Part::sort_Edges: one chain of the edges, taken from the list (reversed where they run the other way)."""
    tol3d = tol3d * tol3d
    pts = [(e, *_edge_points(e)) for e in edges]
    if not pts:
        return []
    sorted_ = [pts[0][0]]
    first, last = pts[0][1], pts[0][2]
    edges.remove(pts[0][0])
    pts.pop(0)
    while pts:
        found = None
        for k, (e, v1, v2) in enumerate(pts):
            if v1.SquareDistance(last) <= tol3d:
                last = v2
                sorted_.append(e)
                found = k
                break
            if v2.SquareDistance(first) <= tol3d:
                first = v1
                sorted_.insert(0, e)
                found = k
                break
            if v2.SquareDistance(last) <= tol3d:
                last = v1
                sorted_.append(_reversed_edge(e))
                found = k
                break
            if v1.SquareDistance(first) <= tol3d:
                first = v2
                sorted_.insert(0, _reversed_edge(e))
                found = k
                break
        if found is None:
            return sorted_
        e = pts[found][0]
        edges.remove(e)
        pts.pop(found)
        if last.SquareDistance(first) <= tol3d:
            return sorted_
    return sorted_


def _reversed_edge(e):
    BRepLib.BuildCurves3d_s(e)
    curve, first, last = BRep_Tool.Curve_s(TopoDS.Edge(e), 0.0, 0.0), None, None
    a, b = BRep_Tool.Range_s(TopoDS.Edge(e))
    first = curve.ReversedParameter(a)
    last = curve.ReversedParameter(b)
    return BRepBuilderAPI_MakeEdge(curve.Reversed(), last, first).Edge()


def _edges_of(lst):
    out = []
    for item in lst:
        if not isinstance(item, Shape):
            raise TypeError("item is not a shape")
        if item._s.ShapeType() != TopAbs_EDGE:
            raise TypeError("shape is not an edge")
        out.append(TopoDS.Edge(item._s))
    return out


def __sortEdges__(edges):
    lst = _edges_of(edges)
    return [Edge(e) for e in _sort_edges(1e-7, lst)]


def sortEdges(edges, tol3d=1e-7):
    lst = _edges_of(edges)
    out = []
    while lst:
        out.append([Edge(e) for e in _sort_edges(tol3d, lst)])
    return out


def getSortedClusters(edges):
    from cad_agent.fcshim import _fc_clusters
    return _fc_clusters.sorted_clusters(edges)


def read(path):
    from OCP.BRep import BRep_Builder
    from OCP.BRepTools import BRepTools
    from OCP.TopoDS import TopoDS_Shape
    s = TopoDS_Shape()
    BRepTools.Read_s(s, str(path), BRep_Builder())
    return wrap(s)


def getShape(obj, subname="", mat=None, needSubElement=False, transform=True, retType=0, noElementMap=False,
             refine=False):
    s = obj.Shape
    if subname:
        return s.getElement(subname.rstrip("."))
    return s


def isLinked(obj):
    return False

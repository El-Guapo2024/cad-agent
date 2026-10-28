# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses FreeCAD's Part TopoShape Python API and keeps FreeCAD's licence, the GNU Lesser
# General Public License, version 2.1 or (at your option) any later version; the text is in ../../ui/LICENSE.
#
#   Derived from: src/Mod/Part/App/TopoShape.cpp, TopoShapeExpansion.cpp (Copyright (c) 2002 Juergen Riegel,
#                 2022 Zheng, Lei), TopoShapePyImp.cpp, TopoShapeEdgePyImp.cpp, TopoShapeWirePyImp.cpp,
#                 TopoShapeFacePyImp.cpp, TopoShapeSolidPyImp.cpp, TopoShapeVertexPyImp.cpp,
#                 TopoShapeCompoundPyImp.cpp, AppPartPy.cpp (Copyright (c) 2002 Juergen Riegel)
#                 FreeCAD (https://github.com/FreeCAD/FreeCAD), commit 3160daf1e2b62b0472854da4848255c6b3ad554c
#
# See ../../NOTICE.
"""Part.Shape and its kinds (Vertex, Edge, Wire, Face, Shell, Solid, CompSolid, Compound) over a TopoDS_Shape, with the
methods and properties FreeCAD's CAM Python uses, computed as TopoShape computes them (sub-shapes in TopExp::MapShapes
order, booleans through cad_agent/topo_boolean.py, removeSplitter through refine.py, offsets and slices through the
Part workbench's ports)."""
from __future__ import annotations

import math

from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import (BRepBuilderAPI_Copy, BRepBuilderAPI_GTransform, BRepBuilderAPI_MakeEdge,
                                BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeVertex, BRepBuilderAPI_MakeWire,
                                BRepBuilderAPI_Transform)
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.BRepExtrema import BRepExtrema_DistShapeShape, BRepExtrema_IsInFace, BRepExtrema_IsOnEdge, BRepExtrema_IsVertex
from OCP.BRepGProp import BRepGProp, BRepGProp_Face
from OCP.BRepLProp import BRepLProp_CLProps
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism, BRepPrimAPI_MakeRevol
from OCP.BRepTools import BRepTools, BRepTools_WireExplorer
from OCP.Bnd import Bnd_Box
from OCP.GCPnts import (GCPnts_AbscissaPoint, GCPnts_QuasiUniformAbscissa, GCPnts_QuasiUniformDeflection,
                        GCPnts_TangentialDeflection, GCPnts_UniformAbscissa, GCPnts_UniformDeflection)
from OCP.GProp import GProp_GProps
from OCP.ShapeAnalysis import ShapeAnalysis
from OCP.TopAbs import (TopAbs_COMPOUND, TopAbs_COMPSOLID, TopAbs_EDGE, TopAbs_FACE, TopAbs_FORWARD, TopAbs_IN,
                        TopAbs_INTERNAL, TopAbs_EXTERNAL, TopAbs_REVERSED, TopAbs_SHELL, TopAbs_SOLID, TopAbs_VERTEX,
                        TopAbs_WIRE, TopAbs_SHAPE)
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Iterator, TopoDS_Shape
try:
    from OCP.TopTools import TopTools_IndexedMapOfShape
except ImportError:                     # OCP 8 moved OCCT's collections
    from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedMapOfShape
from OCP.gp import gp_Ax1, gp_Dir, gp_GTrsf, gp_Pnt, gp_Trsf, gp_Vec

from ._fc_base import BoundBox, Matrix, Placement, Rotation, Vector, vec
from . import _fc_geom as G

TYPE_NAMES = {TopAbs_COMPOUND: "Compound", TopAbs_COMPSOLID: "CompSolid", TopAbs_SOLID: "Solid", TopAbs_SHELL: "Shell",
              TopAbs_FACE: "Face", TopAbs_WIRE: "Wire", TopAbs_EDGE: "Edge", TopAbs_VERTEX: "Vertex",
              TopAbs_SHAPE: "Shape"}
NAME_TYPES = {"Vertex": TopAbs_VERTEX, "Edge": TopAbs_EDGE, "Wire": TopAbs_WIRE, "Face": TopAbs_FACE,
              "Shell": TopAbs_SHELL, "Solid": TopAbs_SOLID, "CompSolid": TopAbs_COMPSOLID, "Compound": TopAbs_COMPOUND}


class OCCError(RuntimeError):
    """Part.OCCError."""


def _gp_trsf(m) -> gp_Trsf:
    """A Matrix or Placement as a gp_Trsf (TopoShape::convert, the rotation and translation parts)."""
    if isinstance(m, Placement):
        m = m.toMatrix()
    t = gp_Trsf()
    a = m.m
    t.SetValues(a[0][0], a[0][1], a[0][2], a[0][3], a[1][0], a[1][1], a[1][2], a[1][3], a[2][0], a[2][1], a[2][2],
                a[2][3])
    return t


def _matrix_of(t: gp_Trsf) -> Matrix:
    m = Matrix()
    for r in range(3):
        for c in range(4):
            m.m[r][c] = t.Value(r + 1, c + 1)
    return m


def bnd_get(b):
    """Bnd_Box::Get (OCP for OCCT 8 cannot return Bnd_Box::Limits): the corners, or None for a void box."""
    if b.IsVoid():
        return None
    lo, hi = b.CornerMin(), b.CornerMax()
    return lo.X(), lo.Y(), lo.Z(), hi.X(), hi.Y(), hi.Z()


def _subs(shape, kind):
    if shape is None or shape.IsNull():
        return []
    m = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, kind, m)
    return [m.FindKey(i) for i in range(1, m.Extent() + 1)]


def wrap(s):
    """shape2pyshape: the Python class for a TopoDS_Shape's type."""
    if s is None:
        return Shape()
    if s.IsNull():
        return Shape(s)
    cls = {TopAbs_VERTEX: Vertex, TopAbs_EDGE: Edge, TopAbs_WIRE: Wire, TopAbs_FACE: Face, TopAbs_SHELL: Shell,
           TopAbs_SOLID: Solid, TopAbs_COMPSOLID: CompSolid, TopAbs_COMPOUND: Compound}[s.ShapeType()]
    o = object.__new__(cls)
    o._s = s
    o.Tag = 0
    return o


def topods(x):
    if isinstance(x, Shape):
        return x._s
    if isinstance(x, TopoDS_Shape):
        return x
    raise TypeError(f"expected a shape, got {type(x).__name__}")


def _props(s):
    """getShapeProperties: volume, surface or linear properties by what the shape holds."""
    prop = GProp_GProps()
    if TopExp_Explorer(s, TopAbs_SOLID).More():
        BRepGProp.VolumeProperties_s(s, prop)
        return prop
    if TopExp_Explorer(s, TopAbs_FACE).More():
        BRepGProp.SurfaceProperties_s(s, prop)
        return prop
    if TopExp_Explorer(s, TopAbs_EDGE).More():
        BRepGProp.LinearProperties_s(s, prop)
        return prop
    pts = [BRep_Tool.Pnt_s(TopoDS.Vertex(v)) for v in _iter_explore(s, TopAbs_VERTEX)]
    if pts:
        x = sum(p.X() for p in pts) / len(pts)
        y = sum(p.Y() for p in pts) / len(pts)
        z = sum(p.Z() for p in pts) / len(pts)
        return GProp_GProps(gp_Pnt(x, y, z))
    return None


def _iter_explore(s, kind):
    ex = TopExp_Explorer(s, kind)
    while ex.More():
        yield ex.Current()
        ex.Next()


class Shape:
    """Part.Shape (TopoShapePy)."""

    def __init__(self, s=None):
        if isinstance(s, Shape):
            s = s._s
        self._s = s if s is not None else TopoDS_Shape()
        self.Tag = 0

    # ── identity ──
    def isNull(self):
        return self._s.IsNull()

    def isValid(self):
        return not self._s.IsNull() and BRepCheck_Analyzer(self._s).IsValid()

    def isSame(self, o):
        return self._s.IsSame(topods(o))

    def isEqual(self, o):
        return self._s.IsEqual(topods(o))

    def isPartner(self, o):
        return self._s.IsPartner(topods(o))

    def hashCode(self, upper=2147483647):
        return hash(self._s) % upper

    def __hash__(self):
        return hash(self._s)

    def __eq__(self, o):
        return isinstance(o, Shape) and self._s.IsEqual(o._s)

    def __repr__(self):
        return f"<{type(self).__name__} object>"

    @property
    def ShapeType(self):
        if self._s.IsNull():
            raise OCCError("cannot determine type of null shape")
        return TYPE_NAMES[self._s.ShapeType()]

    @property
    def Orientation(self):
        return {TopAbs_FORWARD: "Forward", TopAbs_REVERSED: "Reversed", TopAbs_INTERNAL: "Internal",
                TopAbs_EXTERNAL: "External"}[self._s.Orientation()]

    @Orientation.setter
    def Orientation(self, v):
        self._s.Orientation({"Forward": TopAbs_FORWARD, "Reversed": TopAbs_REVERSED, "Internal": TopAbs_INTERNAL,
                             "External": TopAbs_EXTERNAL}[v])

    # ── sub-shapes ──
    def _subs(self, kind):
        return [wrap(x) for x in _subs(self._s, kind)]

    @property
    def Vertexes(self):
        return self._subs(TopAbs_VERTEX)

    @property
    def Edges(self):
        return self._subs(TopAbs_EDGE)

    @property
    def Wires(self):
        return self._subs(TopAbs_WIRE)

    @property
    def Faces(self):
        return self._subs(TopAbs_FACE)

    @property
    def Shells(self):
        return self._subs(TopAbs_SHELL)

    @property
    def Solids(self):
        return self._subs(TopAbs_SOLID)

    @property
    def CompSolids(self):
        return self._subs(TopAbs_COMPSOLID)

    @property
    def SubShapes(self):
        out = []
        if self._s.IsNull():
            return out
        it = TopoDS_Iterator(self._s)
        while it.More():
            out.append(wrap(it.Value()))
            it.Next()
        return out

    def childShapes(self, cumOri=True, cumLoc=True):
        out = []
        it = TopoDS_Iterator(self._s, cumOri, cumLoc)
        while it.More():
            out.append(wrap(it.Value()))
            it.Next()
        return out

    def getElement(self, name):
        import re
        m = re.fullmatch(r"(Vertex|Edge|Wire|Face|Shell|Solid|CompSolid)(\d+)", name)
        if not m:
            raise ValueError(f"Invalid element name {name!r}")
        kind = NAME_TYPES[m.group(1)]
        lst = _subs(self._s, kind)
        i = int(m.group(2))
        if not 1 <= i <= len(lst):
            raise IndexError(f"Index out of bound: {name}")
        return wrap(lst[i - 1])

    def __getattr__(self, name):
        """TopoShapePy::getCustomAttributes: shape.Face3, shape.Edge12 ... are its sub-shapes."""
        import re
        if re.fullmatch(r"(Vertex|Edge|Wire|Face|Shell|Solid|CompSolid)\d+", name):
            try:
                return self.getElement(name)
            except (IndexError, ValueError):
                pass
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def countElement(self, kind):
        return len(_subs(self._s, NAME_TYPES[kind]))

    # ── geometry ──
    @property
    def BoundBox(self):
        box = BoundBox()
        try:
            b = Bnd_Box()
            BRepBndLib.Add_s(self._s, b)
            b.SetGap(0.0)
            got = bnd_get(b)
            if got:
                box.XMin, box.YMin, box.ZMin, box.XMax, box.YMax, box.ZMax = got
        except Exception:  # noqa: BLE001 - Standard_Failure on an empty shape: the void box
            pass
        return box

    def optimalBoundingBox(self, useTriangulation=True, useShapeTolerance=False):
        box = BoundBox()
        b = Bnd_Box()
        BRepBndLib.AddOptimal_s(self._s, b, useTriangulation, useShapeTolerance)
        b.SetGap(0.0)
        got = bnd_get(b)
        if got:
            box.XMin, box.YMin, box.ZMin, box.XMax, box.YMax, box.ZMax = got
        return box

    @property
    def Placement(self):
        loc = self._s.Location()
        return Placement(_matrix_of(loc.Transformation()))

    @Placement.setter
    def Placement(self, pl):
        self._s.Location(TopLoc_Location(_gp_trsf(pl)))

    @property
    def Matrix(self):
        return _matrix_of(self._s.Location().Transformation())

    @property
    def Length(self):
        p = GProp_GProps()
        BRepGProp.LinearProperties_s(self._s, p)
        return p.Mass()

    @property
    def Area(self):
        p = GProp_GProps()
        BRepGProp.SurfaceProperties_s(self._s, p)
        return p.Mass()

    @property
    def Volume(self):
        p = GProp_GProps()
        BRepGProp.VolumeProperties_s(self._s, p)
        return p.Mass()

    @property
    def Mass(self):
        p = _props(self._s)
        return p.Mass() if p else 0.0

    @property
    def CenterOfGravity(self):
        p = _props(self._s)
        if p is None:
            raise OCCError("shape has no center of gravity")
        return G.V(p.CentreOfMass())

    @property
    def CenterOfMass(self):
        return self.CenterOfGravity

    @property
    def Tolerance(self):
        """TopoShape::getTolerance (the maximum of its sub-shapes')."""
        from OCP.ShapeAnalysis import ShapeAnalysis_ShapeTolerance
        return ShapeAnalysis_ShapeTolerance().Tolerance(self._s, 1, TopAbs_SHAPE)

    def isClosed(self):
        """TopoShape::isClosed."""
        s = self._s
        if s.IsNull():
            return False
        t = s.ShapeType()
        if t == TopAbs_WIRE:
            return BRep_Tool.IsClosed_s(TopoDS.Wire(s))
        if t == TopAbs_EDGE:
            return BRep_Tool.IsClosed_s(TopoDS.Edge(s))
        if t in (TopAbs_SHELL, TopAbs_SOLID, TopAbs_COMPSOLID, TopAbs_COMPOUND, TopAbs_FACE):
            from cad_agent.refine import is_closed
            return is_closed(s)
        return False

    # ── transformations (TopoShapePy) ──
    def copy(self, copyGeom=True, copyMesh=False):
        if self._s.IsNull():
            return wrap(self._s)
        return wrap(BRepBuilderAPI_Copy(self._s, copyGeom, copyMesh).Shape())

    def translate(self, v):
        v = vec(v)
        t = gp_Trsf()
        t.SetTranslation(gp_Vec(v.x, v.y, v.z))
        self._s.Move(TopLoc_Location(t))
        return self

    def translated(self, v):
        c = self.copy()
        return c.translate(v)

    def rotate(self, base, direction, degree=0.0):
        if isinstance(base, Placement):
            raise TypeError("rotate(base, direction, degree)")
        b, d = vec(base), vec(direction)
        t = gp_Trsf()
        t.SetRotation(gp_Ax1(gp_Pnt(b.x, b.y, b.z), gp_Dir(d.x, d.y, d.z)), math.radians(float(degree)))
        self._s.Move(TopLoc_Location(t))
        return self

    def rotated(self, *a):
        c = self.copy()
        return c.rotate(*a)

    def transformShape(self, m, copy=False, checkScale=False):
        if isinstance(m, Placement):
            m = m.toMatrix()
        self._s = _transform(self._s, m, copy)
        return self

    def transformed(self, m, copy=False, checkScale=False, op=None):
        return wrap(_transform(self._s, m if not isinstance(m, Placement) else m.toMatrix(), copy))

    def transformGeometry(self, m):
        return wrap(_transform(self._s, m, True, force_g=True))

    def scale(self, factor, base=None):
        b = vec(base) if base is not None else Vector()
        t = gp_Trsf()
        t.SetScale(gp_Pnt(b.x, b.y, b.z), float(factor))
        self._s = BRepBuilderAPI_Transform(self._s, t, True).Shape()
        return self

    def scaled(self, factor, base=None):
        return self.copy().scale(factor, base)

    def reverse(self):
        self._s.Reverse()
        return self

    def reversed(self):
        return wrap(self._s.Reversed())

    def complement(self):
        self._s.Complement()

    def fix(self, w=1e-7, a=1e-7, b=1e-7):
        from OCP.ShapeFix import ShapeFix_Shape
        f = ShapeFix_Shape(self._s)
        f.SetPrecision(w)
        f.SetMinTolerance(a)
        f.SetMaxTolerance(b)
        f.Perform()
        self._s = f.Shape()
        return True

    # ── booleans (TopoShape::makeElementBoolean, tolerance 0 as TopoShapePy passes it) ──
    def _bool(self, op, tools, tol=0.0):
        from cad_agent.topo_boolean import element_boolean
        if isinstance(tools, Shape):
            tools = [tools]
        shapes = [self._s] + [topods(t) for t in tools]
        return wrap(element_boolean(op, shapes, float(tol)))

    def cut(self, tools, tol=0.0):
        return self._bool("cut", tools, tol)

    def fuse(self, tools, tol=0.0):
        return self._bool("fuse", tools, tol)

    def common(self, tools, tol=0.0):
        return self._bool("common", tools, tol)

    def section(self, tools, approx=False, tol=0.0):
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
        if isinstance(tools, Shape):
            tools = [tools]
        res = self._s
        for t in tools:
            mk = BRepAlgoAPI_Section(res, topods(t), False)
            mk.Approximation(approx)
            mk.Build()
            if not mk.IsDone():
                raise OCCError("Section failed")
            res = mk.Shape()
        return wrap(res)

    def removeSplitter(self):
        from cad_agent.refine import refine_model
        try:
            return wrap(refine_model(self._s))
        except Exception:  # noqa: BLE001 - TopoShape::removeSplitter throws; Python sees the error
            raise OCCError("Refine failed") from None

    # ── making ──
    def extrude(self, v):
        v = vec(v)
        mk = BRepPrimAPI_MakePrism(self._s, gp_Vec(v.x, v.y, v.z))
        if not mk.IsDone():
            raise OCCError("BRepPrimAPI_MakePrism failed")
        return wrap(mk.Shape())

    def revolve(self, base, direction, angle=360.0):
        b, d = vec(base), vec(direction)
        mk = BRepPrimAPI_MakeRevol(self._s, gp_Ax1(gp_Pnt(b.x, b.y, b.z), gp_Dir(d.x, d.y, d.z)),
                                   math.radians(angle), True)
        return wrap(mk.Shape())

    def makeOffset2D(self, offset, join=0, fill=False, openResult=False, intersection=False):
        from cad_agent.feature_part_sweep import make_offset2d
        return wrap(make_offset2d(self._s, float(offset), int(join), bool(fill), bool(openResult), bool(intersection)))

    def makeOffsetShape(self, offset, tolerance, inter=False, self_inter=False, offsetMode=0, join=0, fill=False):
        from cad_agent.feature_part_sweep import make_offset
        return wrap(make_offset(self._s, float(offset), float(tolerance), bool(inter), bool(self_inter),
                                int(offsetMode), int(join), bool(fill)))

    def slice(self, direction, d):
        from cad_agent.feature_part_static import slice_shape
        dd = vec(direction)
        return [wrap(w) for w in slice_shape(self._s, (dd.x, dd.y, dd.z), float(d))]

    def slices(self, direction, ds):
        from OCP.BRep import BRep_Builder as _B
        b, comp = _B(), TopoDS_Compound()
        b.MakeCompound(comp)
        for d in ds:
            for w in self.slice(direction, d):
                b.Add(comp, w._s)
        return wrap(comp)

    def makeParallelProjection(self, shape, direction):
        from OCP.BRepProj import BRepProj_Projection
        d = vec(direction)
        proj = BRepProj_Projection(topods(shape), self._s, gp_Dir(d.x, d.y, d.z))
        return wrap(proj.Shape())

    def distToShape(self, other, tol=1e-7):
        """TopoShapePy::distToShape: (distance, [(p1, p2) ...], [(type1, index1, param1, type2, index2, param2) ...])."""
        ext = BRepExtrema_DistShapeShape(self._s, topods(other))
        if not ext.IsDone():
            raise OCCError("BRepExtrema_DistShapeShape failed")
        pts, infos = [], []
        for i in range(1, ext.NbSolution() + 1):
            pts.append((G.V(ext.PointOnShape1(i)), G.V(ext.PointOnShape2(i))))
            infos.append(_support(ext, i, 1, self._s) + _support(ext, i, 2, topods(other)))
        return (ext.Value(), pts, infos)

    def isInside(self, point, tol, checkFace=False):
        p = vec(point)
        pnt = gp_Pnt(p.x, p.y, p.z)
        s = self._s
        if s.IsNull():
            raise OCCError("Cannot handle null shape")
        if s.ShapeType() in (TopAbs_VERTEX, TopAbs_EDGE, TopAbs_WIRE, TopAbs_FACE):
            ext = BRepExtrema_DistShapeShape(BRepBuilderAPI_MakeVertex(pnt).Vertex(), s)
            if not ext.Perform() if hasattr(ext, "Perform") and False else not ext.IsDone():
                raise OCCError("Failed to determine distance to shape")
            return ext.Value() <= tol
        cl = BRepClass3d_SolidClassifier(s)
        cl.Perform(pnt, float(tol))
        test = cl.State() == TopAbs_IN
        if checkFace and cl.IsOnAFace():
            test = True
        return test

    def exportBrep(self, path):
        BRepTools.Write_s(self._s, str(path))

    def exportBrepToString(self):
        import io
        import tempfile
        import os
        fd, p = tempfile.mkstemp(suffix=".brep")
        os.close(fd)
        try:
            BRepTools.Write_s(self._s, p)
            return open(p).read()
        finally:
            os.unlink(p)

    def importBrepFromString(self, text, checkInput=True):
        import tempfile
        import os
        from OCP.BRep import BRep_Builder as _B
        fd, p = tempfile.mkstemp(suffix=".brep")
        os.close(fd)
        try:
            open(p, "w").write(text)
            s = TopoDS_Shape()
            BRepTools.Read_s(s, p, _B())
            self._s = s
        finally:
            os.unlink(p)

    def dumps(self):
        return self.exportBrepToString()

    def loads(self, text):
        self.importBrepFromString(text)

    def tessellate(self, tol, *a):
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        BRepMesh_IncrementalMesh(self._s, tol)
        pts, tris = [], []
        from OCP.TopLoc import TopLoc_Location as _L
        for f in self.Faces:
            loc = _L()
            tri = BRep_Tool.Triangulation_s(TopoDS.Face(f._s), loc)
            if tri is None:
                continue
            t = loc.Transformation()
            base = len(pts)
            for i in range(1, tri.NbNodes() + 1):
                pts.append(G.V(tri.Node(i).Transformed(t)))
            for i in range(1, tri.NbTriangles() + 1):
                a, b, c = tri.Triangle(i).Get()
                if f._s.Orientation() == TopAbs_REVERSED:
                    a, b = b, a
                tris.append((base + a - 1, base + b - 1, base + c - 1))
        return (pts, tris)

    def check(self, runBopCheck=False):
        if not BRepCheck_Analyzer(self._s).IsValid():
            raise ValueError("shape is invalid")

    def removeShape(self, shapes):
        from OCP.BRepTools import BRepTools_ReShape
        r = BRepTools_ReShape()
        for s in shapes:
            r.Remove(topods(s))
        return wrap(r.Apply(self._s, TopAbs_SHAPE))

    def makeFillet(self, radius, edges):
        from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
        mk = BRepFilletAPI_MakeFillet(self._s)
        for e in edges:
            mk.Add(float(radius), TopoDS.Edge(topods(e)))
        return wrap(mk.Shape())

    def findPlane(self, tol=-1):
        from OCP.BRepLib import BRepLib_FindSurface
        from OCP.Geom import Geom_Plane
        f = BRepLib_FindSurface(self._s, tol, True)
        if not f.Found():
            return None
        s = f.Surface()
        if not isinstance(s, Geom_Plane):
            return None
        pl = G.Plane(s)
        return pl


def _support(ext, i, which, shape):
    """BRepExtrema's support of a solution: (type, index in the shape's map, parameter(s))."""
    st = ext.SupportTypeShape1(i) if which == 1 else ext.SupportTypeShape2(i)
    sup = ext.SupportOnShape1(i) if which == 1 else ext.SupportOnShape2(i)
    if st == BRepExtrema_IsVertex:
        lst = _subs(shape, TopAbs_VERTEX)
        idx = next((k for k, x in enumerate(lst) if x.IsSame(sup)), -1)
        return ("Vertex", idx, None)
    if st == BRepExtrema_IsOnEdge:
        lst = _subs(shape, TopAbs_EDGE)
        idx = next((k for k, x in enumerate(lst) if x.IsSame(sup)), -1)
        t = ext.ParOnEdgeS1(i) if which == 1 else ext.ParOnEdgeS2(i)
        return ("Edge", idx, t)
    lst = _subs(shape, TopAbs_FACE)
    idx = next((k for k, x in enumerate(lst) if x.IsSame(sup)), -1)
    uv = ext.ParOnFaceS1(i) if which == 1 else ext.ParOnFaceS2(i)
    return ("Face", idx, tuple(uv) if uv is not None else None)


def _transform(s, m, copy, force_g=False):
    """TopoShape::transformShape: BRepBuilderAPI_Transform for a rigid transformation, GTransform with a scale."""
    a = m.m
    det = (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1]) - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
           + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))
    if not force_g and abs(abs(det) - 1.0) < 1e-9:
        mk = BRepBuilderAPI_Transform(s, _gp_trsf(m), copy)
        return mk.Shape()
    g = gp_GTrsf()
    for r in range(3):
        for c in range(4):
            g.SetValue(r + 1, c + 1, a[r][c])
    return BRepBuilderAPI_GTransform(s, g, copy).Shape()


class Vertex(Shape):
    def __init__(self, *args):
        if len(args) == 1 and isinstance(args[0], Shape):
            super().__init__(args[0]._s)
            return
        if len(args) == 1 and isinstance(args[0], TopoDS_Shape):
            super().__init__(args[0])
            return
        if not args:
            p = Vector()
        elif len(args) == 3:
            p = Vector(*args)
        else:
            p = vec(args[0])
        super().__init__(BRepBuilderAPI_MakeVertex(gp_Pnt(p.x, p.y, p.z)).Vertex())

    @property
    def Point(self):
        return G.V(BRep_Tool.Pnt_s(TopoDS.Vertex(self._s)))

    @property
    def X(self):
        return self.Point.x

    @property
    def Y(self):
        return self.Point.y

    @property
    def Z(self):
        return self.Point.z


class Edge(Shape):
    def __init__(self, *args):
        if not args:
            super().__init__(None)
            return
        a = args[0]
        if isinstance(a, TopoDS_Shape):
            super().__init__(a)
            return
        if isinstance(a, Shape):
            if a.ShapeType != "Edge":
                raise TypeError("Shape is not an edge")
            super().__init__(a._s)
            return
        if isinstance(a, G.Curve):
            if len(args) == 3:
                mk = BRepBuilderAPI_MakeEdge(a.h, float(args[1]), float(args[2]))
            else:
                mk = BRepBuilderAPI_MakeEdge(a.h, a.h.FirstParameter(), a.h.LastParameter())
            if not mk.IsDone():
                raise OCCError("Failed to create edge from curve")
            super().__init__(mk.Edge())
            return
        if isinstance(a, Vertex) and len(args) == 2:
            mk = BRepBuilderAPI_MakeEdge(TopoDS.Vertex(a._s), TopoDS.Vertex(args[1]._s))
            super().__init__(mk.Edge())
            return
        raise TypeError("Edge constructor: unsupported arguments")

    def _adapt(self):
        return BRepAdaptor_Curve(TopoDS.Edge(self._s))

    @property
    def Curve(self):
        """TopoShapeEdgePy::getCurve: the edge's curve as Part's geometry, its location applied."""
        from OCP.Geom import Geom_Line, Geom_Circle, Geom_Ellipse, Geom_Hyperbola, Geom_Parabola
        from OCP.GeomAbs import (GeomAbs_Line, GeomAbs_Circle, GeomAbs_Ellipse, GeomAbs_Hyperbola, GeomAbs_Parabola,
                                 GeomAbs_BezierCurve, GeomAbs_BSplineCurve, GeomAbs_OffsetCurve, GeomAbs_OtherCurve)
        a = self._adapt()
        t = a.GetType()
        if t == GeomAbs_Line:
            return G.Line(Geom_Line(a.Line()))
        if t == GeomAbs_Circle:
            return G.Circle(Geom_Circle(a.Circle()))
        if t == GeomAbs_Ellipse:
            return G.Ellipse(Geom_Ellipse(a.Ellipse()))
        if t == GeomAbs_Hyperbola:
            return G.wrap_curve(Geom_Hyperbola(a.Hyperbola()))
        if t == GeomAbs_Parabola:
            return G.wrap_curve(Geom_Parabola(a.Parabola()))
        if t == GeomAbs_BezierCurve:
            return G.wrap_curve(a.Bezier())
        if t == GeomAbs_BSplineCurve:
            return G.wrap_curve(a.BSpline())
        loc = TopLoc_Location()
        c, f, l = BRep_Tool.Curve_s(TopoDS.Edge(self._s), loc, 0.0, 0.0) if False else (None, 0, 0)
        h = BRep_Tool.Curve_s(TopoDS.Edge(self._s), 0.0, 0.0)
        return G.wrap_curve(h)

    @property
    def FirstParameter(self):
        return self._adapt().FirstParameter()

    @property
    def LastParameter(self):
        return self._adapt().LastParameter()

    @property
    def ParameterRange(self):
        a = self._adapt()
        return (a.FirstParameter(), a.LastParameter())

    def valueAt(self, u):
        return G.V(self._adapt().Value(float(u)))

    def tangentAt(self, u):
        prop = BRepLProp_CLProps(self._adapt(), float(u), 2, 1e-7)
        if prop.IsTangentDefined():
            d = gp_Dir()
            prop.Tangent(d)
            return Vector(d.X(), d.Y(), d.Z())
        raise OCCError("Tangent not defined at this position!")

    def derivative1At(self, u):
        p, v = gp_Pnt(), gp_Vec()
        self._adapt().D1(float(u), p, v)
        return Vector(v.X(), v.Y(), v.Z())

    def normalAt(self, u):
        prop = BRepLProp_CLProps(self._adapt(), float(u), 2, 1e-7)
        d = gp_Dir()
        prop.Normal(d)
        return Vector(d.X(), d.Y(), d.Z())

    def curvatureAt(self, u):
        prop = BRepLProp_CLProps(self._adapt(), float(u), 2, 1e-7)
        return prop.Curvature()

    def parameterAt(self, vertex, face=None):
        return BRep_Tool.Parameter_s(TopoDS.Vertex(topods(vertex)), TopoDS.Edge(self._s))

    def getParameterByLength(self, length, tol=1e-7):
        a = self._adapt()
        first, last = a.FirstParameter(), a.LastParameter()
        stretch = GCPnts_AbscissaPoint.Length_s(a, first, last, tol)
        if length < -stretch:
            length = 0
        elif length > stretch:
            length = stretch
        elif length < 0:
            length += stretch
        ap = GCPnts_AbscissaPoint(tol, a, length, first)
        return ap.Parameter()

    @property
    def Length(self):
        a = self._adapt()
        return GCPnts_AbscissaPoint.Length_s(a)

    def isSeam(self, face):
        return BRep_Tool.IsClosed_s(TopoDS.Edge(self._s), TopoDS.Face(topods(face)))

    def isDegenerated(self):
        return BRep_Tool.Degenerated_s(TopoDS.Edge(self._s))

    def firstVertex(self, orientation=False):
        return wrap(TopExp.FirstVertex_s(TopoDS.Edge(self._s), orientation))

    def lastVertex(self, orientation=False):
        return wrap(TopExp.LastVertex_s(TopoDS.Edge(self._s), orientation))

    def discretize(self, *args, **kw):
        return _discretize(self._adapt(), args, kw)

    def split(self, params):
        raise NotImplementedError("Edge.split")

    def common(self, tools, tol=0.0):
        return Shape.common(self, tools, tol)

    def toNurbs(self):
        from OCP.BRepBuilderAPI import BRepBuilderAPI_NurbsConvert
        return wrap(BRepBuilderAPI_NurbsConvert(self._s, True).Shape())


def _discretize(adapt, args, kw):
    """TopoShapeEdgePy::discretize / TopoShapeWirePy::discretize over a curve adaptor."""
    first, last = kw.get("First", adapt.FirstParameter()), kw.get("Last", adapt.LastParameter())
    if args and not kw:
        x = args[0]
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            raise TypeError("Either int or float expected")
        d = GCPnts_UniformAbscissa()
        if isinstance(x, int):
            d.Initialize(adapt, int(x), first, last)
        else:
            d.Initialize(adapt, float(x), first, last)
        if d.IsDone() and d.NbPoints() > 0:
            return [G.V(adapt.Value(d.Parameter(i))) for i in range(1, d.NbPoints() + 1)]
        raise OCCError("Discretization of edge failed")
    if len(args) > 1:
        first = args[1]
    if len(args) > 2:
        last = args[2]
    if "Number" in kw or "Distance" in kw:
        d = GCPnts_UniformAbscissa()
        if "Number" in kw:
            d.Initialize(adapt, int(kw["Number"]), first, last)
        else:
            d.Initialize(adapt, float(kw["Distance"]), first, last)
        if d.IsDone() and d.NbPoints() > 0:
            return [G.V(adapt.Value(d.Parameter(i))) for i in range(1, d.NbPoints() + 1)]
        raise OCCError("Discretization of edge failed")
    if "Deflection" in kw:
        d = GCPnts_UniformDeflection(adapt, float(kw["Deflection"]), first, last)
        if d.IsDone() and d.NbPoints() > 0:
            return [G.V(d.Value(i)) for i in range(1, d.NbPoints() + 1)]
        raise OCCError("Discretization of edge failed")
    if "Angular" in kw:
        d = GCPnts_TangentialDeflection(adapt, first, last, float(kw["Angular"]), float(kw["Curvature"]),
                                        int(kw.get("Minimum", 2)))
        return [G.V(d.Value(i)) for i in range(1, d.NbPoints() + 1)]
    if "QuasiNumber" in kw:
        d = GCPnts_QuasiUniformAbscissa(adapt, int(kw["QuasiNumber"]), first, last)
        return [G.V(adapt.Value(d.Parameter(i))) for i in range(1, d.NbPoints() + 1)]
    if "QuasiDeflection" in kw:
        d = GCPnts_QuasiUniformDeflection(adapt, float(kw["QuasiDeflection"]), first, last)
        return [G.V(d.Value(i)) for i in range(1, d.NbPoints() + 1)]
    raise TypeError("Wrong arguments")


class Wire(Shape):
    def __init__(self, *args):
        if not args:
            super().__init__(None)
            return
        a = args[0]
        if isinstance(a, TopoDS_Shape):
            super().__init__(a)
            return
        mk = BRepBuilderAPI_MakeWire()
        items = [a] if isinstance(a, Shape) else list(a)
        for it in items:
            if not isinstance(it, Shape) or it.isNull():
                raise TypeError("given shape is invalid")
            t = it._s.ShapeType()
            if t == TopAbs_EDGE:
                mk.Add(TopoDS.Edge(it._s))
            elif t == TopAbs_WIRE:
                mk.Add(TopoDS.Wire(it._s))
            else:
                raise TypeError("shape is neither edge nor wire")
        if not mk.IsDone():
            from OCP.BRepBuilderAPI import (BRepBuilderAPI_DisconnectedWire, BRepBuilderAPI_NonManifoldWire,
                                            BRepBuilderAPI_EmptyWire)
            err = mk.Error()
            msg = {BRepBuilderAPI_EmptyWire: "List of edges is empty",
                   BRepBuilderAPI_DisconnectedWire: "Unconnected edges",
                   BRepBuilderAPI_NonManifoldWire: "Non-manifold edges"}.get(err, "BRepBuilderAPI_MakeWire failed")
            raise OCCError(msg)
        super().__init__(mk.Wire())

    @property
    def OrderedEdges(self):
        out = []
        xp = BRepTools_WireExplorer(TopoDS.Wire(self._s))
        while xp.More():
            out.append(wrap(xp.Current()))
            xp.Next()
        return out

    @property
    def OrderedVertexes(self):
        out = []
        xp = BRepTools_WireExplorer(TopoDS.Wire(self._s))
        while xp.More():
            out.append(wrap(xp.CurrentVertex()))
            xp.Next()
        # the last vertex, for an open wire
        if not BRep_Tool.IsClosed_s(TopoDS.Wire(self._s)):
            v1, v2 = TopoDS_Shape(), TopoDS_Shape()
            from OCP.TopoDS import TopoDS_Vertex
            a, b = TopoDS_Vertex(), TopoDS_Vertex()
            TopExp.Vertices_s(TopoDS.Wire(self._s), a, b)
            if not b.IsNull():
                out.append(wrap(b))
        return out

    def discretize(self, *args, **kw):
        from OCP.BRepAdaptor import BRepAdaptor_CompCurve
        return _discretize(BRepAdaptor_CompCurve(TopoDS.Wire(self._s)), args, kw)

    def makeOffset(self, *a):
        raise NotImplementedError("Wire.makeOffset")

    def approximate(self, *a, **k):
        raise NotImplementedError("Wire.approximate")

    def fixWire(self, face=None, tolerance=1e-7):
        from OCP.ShapeFix import ShapeFix_Wire
        from OCP.ShapeExtend import ShapeExtend_WireData
        fx = ShapeFix_Wire()
        fx.Load(TopoDS.Wire(self._s))
        if face is not None:
            fx.SetFace(TopoDS.Face(face._s))
        fx.SetPrecision(tolerance)
        fx.Perform()
        fx.FixReorder()
        fx.FixConnected()
        fx.FixClosed()
        self._s = fx.WireAPIMake()
        return self


class Face(Shape):
    def __init__(self, *args):
        if not args:
            super().__init__(None)
            return
        a = args[0]
        if isinstance(a, TopoDS_Shape):
            super().__init__(a)
            return
        if isinstance(a, Shape) and len(args) == 1:
            t = a._s.ShapeType()
            if t == TopAbs_WIRE:
                mk = BRepBuilderAPI_MakeFace(TopoDS.Wire(a._s))
                if not mk.IsDone():
                    raise OCCError("Failed to create face from wire")
                super().__init__(mk.Face())
                return
            if t == TopAbs_FACE:
                super().__init__(a._s)
                return
            raise TypeError("Face(shape): a wire or a face expected")
        if isinstance(a, G.GeometrySurface):
            if len(args) == 2:
                w = args[1]
                mk = BRepBuilderAPI_MakeFace(a.h, TopoDS.Wire(w._s), True)
                super().__init__(mk.Face())
                return
            super().__init__(a.toShape()._s)
            return
        if isinstance(a, (list, tuple)):
            from cad_agent.feature_part_face import make_face
            ws = [x._s for x in a]
            from OCP.BRep import BRep_Builder as _B
            b, comp = _B(), TopoDS_Compound()
            b.MakeCompound(comp)
            for w in ws:
                b.Add(comp, w)
            super().__init__(make_face(comp, args[1] if len(args) > 1 else "Part::FaceMakerSimple"))
            return
        raise TypeError("Face constructor: unsupported arguments")

    def _adapt(self):
        return BRepAdaptor_Surface(TopoDS.Face(self._s))

    @property
    def Surface(self):
        """TopoShapeFacePy::getSurface: the face's surface, its location applied."""
        from OCP.Geom import Geom_Plane, Geom_CylindricalSurface, Geom_ConicalSurface, Geom_SphericalSurface, \
            Geom_ToroidalSurface
        from OCP.GeomAbs import GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_Cone, GeomAbs_Sphere, GeomAbs_Torus
        a = self._adapt()
        t = a.GetType()
        if t == GeomAbs_Plane:
            return G.Plane(Geom_Plane(a.Plane()))
        if t == GeomAbs_Cylinder:
            return G.wrap_surface(Geom_CylindricalSurface(a.Cylinder()))
        if t == GeomAbs_Cone:
            return G.wrap_surface(Geom_ConicalSurface(a.Cone()))
        if t == GeomAbs_Sphere:
            return G.wrap_surface(Geom_SphericalSurface(a.Sphere()))
        if t == GeomAbs_Torus:
            return G.wrap_surface(Geom_ToroidalSurface(a.Torus()))
        loc = TopLoc_Location()
        h = BRep_Tool.Surface_s(TopoDS.Face(self._s), loc)
        h = h.Transformed(loc.Transformation()) if not loc.IsIdentity() else h
        return G.wrap_surface(h)

    @property
    def ParameterRange(self):
        u1, u2, v1, v2 = BRepTools.UVBounds_s(TopoDS.Face(self._s))
        return (u1, u2, v1, v2)

    def valueAt(self, u, v):
        return G.V(self._adapt().Value(float(u), float(v)))

    def normalAt(self, u, v):
        """TopoShapeFacePy::normalAt: the surface normal, reversed for a reversed face."""
        from OCP.BRepLProp import BRepLProp_SLProps
        prop = BRepLProp_SLProps(self._adapt(), float(u), float(v), 2, 1e-7)
        if not prop.IsNormalDefined():
            raise OCCError("normal not defined")
        n = prop.Normal()
        if self._s.Orientation() == TopAbs_REVERSED:
            n.Reverse()
        return Vector(n.X(), n.Y(), n.Z())

    def tangentAt(self, u, v):
        from OCP.BRepLProp import BRepLProp_SLProps
        prop = BRepLProp_SLProps(self._adapt(), float(u), float(v), 2, 1e-7)
        du, dv = gp_Dir(), gp_Dir()
        prop.TangentU(du)
        prop.TangentV(dv)
        return (Vector(du.X(), du.Y(), du.Z()), Vector(dv.X(), dv.Y(), dv.Z()))

    def Surface_(self):
        return self.Surface

    @property
    def OuterWire(self):
        return wrap(BRepTools.OuterWire_s(TopoDS.Face(self._s)))

    def isPartOfDomain(self, u, v):
        from OCP.BRepTopAdaptor import BRepTopAdaptor_FClass2d
        from OCP.gp import gp_Pnt2d
        from OCP.TopAbs import TopAbs_ON
        cl = BRepTopAdaptor_FClass2d(TopoDS.Face(self._s), 1e-7)
        st = cl.Perform(gp_Pnt2d(u, v))
        return st in (TopAbs_IN, TopAbs_ON)

    def Surface_parameter(self, p):
        from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
        loc = TopLoc_Location()
        h = BRep_Tool.Surface_s(TopoDS.Face(self._s), loc)
        q = vec(p)
        proj = GeomAPI_ProjectPointOnSurf(gp_Pnt(q.x, q.y, q.z), h)
        return proj.LowerDistanceParameters()

    def validate(self):
        from OCP.ShapeFix import ShapeFix_Face
        f = ShapeFix_Face(TopoDS.Face(self._s))
        f.Perform()
        self._s = f.Face()

    def cutHoles(self, wires):
        mk = BRepBuilderAPI_MakeFace(TopoDS.Face(self._s))
        for w in wires:
            mk.Add(TopoDS.Wire(w._s))
        self._s = mk.Face()


class Shell(Shape):
    pass


class Solid(Shape):
    def __init__(self, *args):
        if not args:
            super().__init__(None)
            return
        a = args[0]
        if isinstance(a, TopoDS_Shape):
            super().__init__(a)
            return
        if isinstance(a, Shape):
            t = a._s.ShapeType()
            if t == TopAbs_SOLID:
                super().__init__(a._s)
                return
            if t == TopAbs_SHELL:
                from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid
                mk = BRepBuilderAPI_MakeSolid(TopoDS.Shell(a._s))
                super().__init__(mk.Solid())
                return
            sols = _subs(a._s, TopAbs_SOLID)
            if sols:
                super().__init__(sols[0])
                return
        raise TypeError("Solid(shape): a shell or solid expected")


class CompSolid(Shape):
    pass


class Compound(Shape):
    def __init__(self, *args):
        if args and isinstance(args[0], TopoDS_Shape):
            super().__init__(args[0])
            return
        b, comp = BRep_Builder(), TopoDS_Compound()
        b.MakeCompound(comp)
        for s in (args[0] if args else []):
            if not s.isNull():
                b.Add(comp, topods(s))
        super().__init__(comp)

    def add(self, s):
        BRep_Builder().Add(self._s, topods(s))

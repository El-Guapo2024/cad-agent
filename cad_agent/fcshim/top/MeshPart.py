# SPDX-License-Identifier: LGPL-2.1-or-later
"""Stand-in for FreeCAD's MeshPart module: meshFromShape with LinearDeflection and AngularDeflection, the standard
mesher CAM's Surface and Waterline tessellate a model with (Path/Op/SurfaceSupport.py _makeSTL). Ported from FreeCAD
3160daf1e2b6 (LGPL-2.1-or-later, no copyright line in the files' headers other than the FreeCAD authors'):
src/Mod/MeshPart/App/AppMeshPartPy.cpp (meshFromShape), Mesher.cpp (createStandard, BrepMesh::create),
src/Mod/Part/App/TopoShape.cpp (getDomains), Tools.cpp (getTriangulation) and BRepMesh.cpp (getFacesFromDomains,
MergeVertex). The mesh's points are single precision, as MeshCore keeps them.
"""
from __future__ import annotations

import struct

from cad_agent.fcshim._fc_base import Vector

_CONFUSION = 1e-7               # Precision::Confusion()


def _f32(x):
    return struct.unpack("f", struct.pack("f", x))[0]


class MeshPoint:
    def __init__(self, x, y, z, index):
        self.x, self.y, self.z, self.Index = x, y, z, index

    @property
    def Vector(self):
        return Vector(self.x, self.y, self.z)


class Facet:
    def __init__(self, mesh, i, idx):
        self._mesh, self.Index, self.PointIndices = mesh, i, idx

    @property
    def Points(self):
        return [(p.x, p.y, p.z) for p in (self._mesh.Points[i] for i in self.PointIndices)]


class _Facets(list):
    @property
    def Points(self):
        return [f.Points for f in self]


class Mesh:
    def __init__(self, points, facets):
        self.Points = [MeshPoint(_f32(x), _f32(y), _f32(z), i) for i, (x, y, z) in enumerate(points)]
        self.Facets = _Facets(Facet(self, i, f) for i, f in enumerate(facets))

    @property
    def CountPoints(self):
        return len(self.Points)

    @property
    def CountFacets(self):
        return len(self.Facets)

    @property
    def Topology(self):
        return [(p.Vector) for p in self.Points], [f.PointIndices for f in self.Facets]


def _domains(shape):
    """TopoShape::getDomains with Tools::getTriangulation: each face's nodes, placed, and its triangles, the first two
    corners swapped on a face that is not FORWARD."""
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_FACE, TopAbs_FORWARD
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS
    out = []
    xp = TopExp_Explorer(shape, TopAbs_FACE)
    while xp.More():
        face = TopoDS.Face(xp.Current())
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is None:
            out.append(([], []))
        else:
            trsf = None if loc.IsIdentity() else loc.Transformation()
            pts = []
            for i in range(1, tri.NbNodes() + 1):
                p = tri.Node(i)
                if trsf is not None:
                    p = p.Transformed(trsf)
                pts.append((p.X(), p.Y(), p.Z()))
            fwd = face.Orientation() == TopAbs_FORWARD
            facets = []
            for i in range(1, tri.NbTriangles() + 1):
                n1, n2, n3 = tri.Triangle(i).Get()
                n1, n2, n3 = n1 - 1, n2 - 1, n3 - 1
                if not fwd:
                    n1, n2 = n2, n1
                facets.append((n1, n2, n3))
            out.append((pts, facets))
        xp.Next()
    return out


def _faces_from_domains(domains):
    """BRepMesh::getFacesFromDomains: one point per distinct coordinate (numbered in first-seen order), facets that
    are not degenerate, then MergeVertex's merge of points within Precision::Confusion()."""
    index, faces = {}, []
    for pts, facets in domains:
        for f in facets:
            idx = tuple(index.setdefault(pts[n], len(index)) for n in f)
            if idx[0] != idx[1] and idx[1] != idx[2] and idx[2] != idx[0]:
                faces.append(idx)
    points = [None] * len(index)
    for p, i in index.items():
        points[i] = p
    return _merge(points, faces, _CONFUSION)


def _merge(points, faces, tol):
    import functools

    def less(a, b):
        for k in range(3):
            if abs(a[k] - b[k]) >= tol:
                return a[k] < b[k]
        return False

    order = sorted(range(len(points)), key=functools.cmp_to_key(
        lambda i, j: -1 if less(points[i], points[j]) else (1 if less(points[j], points[i]) else 0)))
    mapping = list(range(len(points)))
    dup = 0
    k = 0
    while k < len(order) - 1:
        first = order[k]
        j = k + 1
        while j < len(order) and not less(points[first], points[order[j]]) and not less(points[order[j]], points[first]):
            mapping[order[j]] = first
            dup += 1
            j += 1
        k = j
    if not dup:
        return points, faces
    faces = [tuple(mapping[i] for i in f) for f in faces]
    degree = [0] * len(points)
    for f in faces:
        for i in f:
            degree[i] += 1
    dec, d = [0] * len(points), 0
    for pos in range(len(points)):
        dec[pos] = d
        if degree[pos] == 0:
            d += 1
    faces = [tuple(i - dec[i] for i in f) for f in faces]
    return [p for p, n in zip(points, degree) if n > 0], faces


def meshFromShape(Shape=None, LinearDeflection=None, AngularDeflection=0.5, Relative=False, Segments=False,
                  GroupColors=None, **kw):
    """Mesher::createStandard: BRepTools::Clean, BRepMesh_IncrementalMesh(shape, deflection, relative, angular), the
    faces' triangulations joined."""
    if Shape is None or LinearDeflection is None or kw:
        raise NotImplementedError("MeshPart.meshFromShape: only (Shape, LinearDeflection, AngularDeflection, Relative)")
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRepTools import BRepTools
    from cad_agent.fcshim._fc_part import topods
    s = topods(Shape)
    if not s.IsNull():
        BRepTools.Clean_s(s)
        BRepMesh_IncrementalMesh(s, float(LinearDeflection), bool(Relative), float(AngularDeflection))
    points, faces = _faces_from_domains(_domains(s))
    return Mesh(points, faces)

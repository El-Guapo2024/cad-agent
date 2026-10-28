# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses FreeCAD's Part::Edgecluster (src/Mod/Part/App/edgecluster.cpp,
# Copyright (c) 2010 Joachim Zettler) and keeps FreeCAD's licence, the GNU Lesser General Public License, version 2.1
# or (at your option) any later version; the text is in ../../ui/LICENSE. FreeCAD commit 3160daf1e2b6.
# See ../../NOTICE.
"""Part.getSortedClusters: the edges grouped into chains of connected edges (Edgecluster), each chain in order."""
from __future__ import annotations

from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.TopAbs import TopAbs_EDGE, TopAbs_REVERSED
from OCP.TopExp import TopExp
from OCP.TopoDS import TopoDS, TopoDS_Vertex

CONFUSION = 1e-7


def _less(a, b):
    """Edgesort_gp_Pnt_Less."""
    for i in range(3):
        if abs(a[i] - b[i]) > CONFUSION:
            return a[i] < b[i]
    return False


class _Map:
    """std::map<gp_Pnt, edges, Edgesort_gp_Pnt_Less>: keys kept sorted, a key equal to another when neither is less."""

    def __init__(self):
        self.keys, self.vals = [], []

    def _lower(self, p):
        lo, hi = 0, len(self.keys)
        while lo < hi:
            mid = (lo + hi) // 2
            if _less(self.keys[mid], p):
                lo = mid + 1
            else:
                hi = mid
        return lo

    def find(self, p):
        i = self._lower(p)
        if i < len(self.keys) and not _less(p, self.keys[i]):
            return i
        return -1

    def insert(self, p):
        i = self._lower(p)
        if i < len(self.keys) and not _less(p, self.keys[i]):
            return i
        self.keys.insert(i, p)
        self.vals.insert(i, [])
        return i

    def erase(self, i):
        del self.keys[i]
        del self.vals[i]


def _pts(e):
    a, b = TopoDS_Vertex(), TopoDS_Vertex()
    TopExp.Vertices_s(e, a, b)
    pa, pb = BRep_Tool.Pnt_s(a), BRep_Tool.Pnt_s(b)
    return (pa.X(), pa.Y(), pa.Z()), (pb.X(), pb.Y(), pb.Z())


def _valid(e):
    if e.IsNull() or BRep_Tool.Degenerated_s(e):
        return False
    c = BRepAdaptor_Curve(e)
    f, l = c.FirstParameter(), c.LastParameter()
    fp, lp, mp = c.Value(f), c.Value(l), c.Value((f + l) * 0.5)
    return mp.Distance(lp) > CONFUSION and mp.Distance(fp) > CONFUSION


def clusters(edges):
    m = _Map()
    for e in edges:
        if _valid(e):
            p1, p2 = _pts(e)
            m.vals[m.insert(p1)].append(e)
            m.vals[m.insert(p2)].append(e)
    out = []
    while m.keys:
        chain = []
        start = next((i for i, v in enumerate(m.vals) if len(v) == 1), 0)
        point = m.keys[start]
        while True:
            i = m.find(point)
            if i < 0:
                break
            es = m.vals[i]
            if not es:
                m.erase(i)
                break
            edge = es.pop(0)
            if not es:
                m.erase(i)
            p1, p2 = _pts(edge)
            if edge.Orientation() == TopAbs_REVERSED:
                p1, p2 = p2, p1
            if sum((p2[k] - point[k]) ** 2 for k in range(3)) ** 0.5 <= CONFUSION:
                edge = TopoDS.Edge(edge.Reversed())
                nxt = p1
            else:
                nxt = p2
            j = m.find(nxt)
            if j >= 0:
                for k, x in enumerate(m.vals[j]):
                    if edge.IsSame(x):
                        del m.vals[j][k]
                        break
            chain.append(edge)
            point = nxt
        out.append(chain)
    return out


def sorted_clusters(edges):
    from cad_agent.fcshim._fc_part import Edge, Shape
    es = []
    for x in edges:
        if not isinstance(x, Shape):
            raise TypeError("item is not a shape")
        if x._s.ShapeType() != TopAbs_EDGE:
            raise TypeError("shape is not an edge")
        es.append(TopoDS.Edge(x._s))
    return [[Edge(e) for e in c] for c in clusters(es)]

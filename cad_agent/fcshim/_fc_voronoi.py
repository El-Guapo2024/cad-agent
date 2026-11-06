# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses what FreeCAD's Path.Voronoi makes in C++ besides the diagram (src/Mod/CAM/App/
# VoronoiEdgePyImp.cpp's makeLineSegment and toShape's arc of a parabola, over src/Mod/Part/App/Geometry.cpp's
# GeomLineSegment::setPoints and GeomArcOfParabola) and keeps FreeCAD's licence, the GNU Lesser General Public License,
# version 2.1 or (at your option) any later version; the text is in ../../ui/LICENSE. FreeCAD
# (https://github.com/FreeCAD/FreeCAD), commit 3160daf1e2b6. See ../../NOTICE.
"""Path.Voronoi: Diagram, Edge, Cell and Vertex from the cam_voronoi module (ui/libarea/voronoi_py.cpp over FreeCAD's
Voronoi classes), which makes its vectors and edges with the three functions here."""
from __future__ import annotations

from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
from OCP.GC import GC_MakeSegment
from OCP.Geom import Geom_Parabola, Geom_TrimmedCurve
from OCP.gp import gp, gp_Ax2, gp_Dir, gp_Pnt

from ._fc_base import Vector

import cam_voronoi as _V


def _edge(curve):
    """BRepBuilderAPI_MakeEdge(h, h->FirstParameter(), h->LastParameter()) wrapped as TopoShapeEdgePy does."""
    from ._fc_part import wrap
    return wrap(BRepBuilderAPI_MakeEdge(curve, curve.FirstParameter(), curve.LastParameter()).Shape())


def _line(p0, p1):
    """Part::GeomLineSegment::setPoints, then the edge."""
    a, b = gp_Pnt(p0.x, p0.y, p0.z), gp_Pnt(p1.x, p1.y, p1.z)
    if a.Distance(b) < gp.Resolution_s():
        raise ValueError("Both points are equal")
    ms = GC_MakeSegment(a, b)
    if not ms.IsDone():
        raise RuntimeError("GC_MakeSegment failed")
    return _edge(ms.Value())


def _parabola(locn, norm, xdir, focal, u, v):
    """toShape's Geom_Parabola(gp_Ax2(locn, norm, xdir), focal) as Part::GeomArcOfParabola: setHandle (a trimmed curve
    over the whole parabola), setRange(u, v, false) (SetTrim), then the edge."""
    p = Geom_Parabola(gp_Ax2(gp_Pnt(*locn), gp_Dir(*norm), gp_Dir(*xdir)), focal)
    t = Geom_TrimmedCurve(p, p.FirstParameter(), p.LastParameter())
    t.SetTrim(u, v)
    return _edge(t)


_V.set_factories(Vector, _line, _parabola)

Diagram = _V.Diagram
Edge = _V.Edge
Cell = _V.Cell
Vertex = _V.Vertex

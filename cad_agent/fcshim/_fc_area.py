# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses FreeCAD's Path::Area and keeps FreeCAD's licence, the GNU Lesser General
# Public License, version 2.1 or (at your option) any later version; the text is in ../../ui/LICENSE.
#
#   Derived from: src/Mod/CAM/App/Area.cpp, Area.h, AreaParams.h, AreaPyImp.cpp, AppPathPy.cpp (fromShapes,
#                 sortWires) (Copyright (c) 2017 Zheng, Lei <realthunder.dev@gmail.com>),
#                 src/Mod/Part/App/CrossSection.cpp (Copyright (c) 2012 Werner Mayer),
#                 src/Mod/Part/App/FaceMakerBullseye.cpp (Copyright (c) 2016 Victor Titov (DeepSOIC))
#                 FreeCAD (https://github.com/FreeCAD/FreeCAD), commit 3160daf1e2b62b0472854da4848255c6b3ad554c
#
# See ../../NOTICE.
"""Path.Area, Path.fromShapes and Path.sortWires: Area.cpp line by line over OCP and FreeCAD's own libarea (the
cam_areaext module, ui/libarea/areaext.cpp, for the CArea calls Area.cpp makes in C++).

Where Area.cpp leans on containers whose order is an implementation detail, the port keeps the order FreeCAD's build
shows: boost::geometry rtree nearest queries with ties answer in insertion order, and the std::set / std::map keyed by
an object's address (WireJoiner's edgesToVisit, sortWires' RResults) in allocation order, which is the order the
objects were made in."""
from __future__ import annotations

import math

from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Section
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeVertex,
                                BRepBuilderAPI_MakeWire, BRepBuilderAPI_DisconnectedWire)
from OCP.BRepExtrema import BRepExtrema_DistShapeShape, BRepExtrema_IsOnEdge
from OCP.BRepLib import BRepLib, BRepLib_FindSurface, BRepLib_MakeFace
from OCP.BRepPrimAPI import BRepPrimAPI_MakeHalfSpace
from OCP.BRepTools import BRepTools_WireExplorer
from OCP.Bnd import Bnd_Box
from OCP.GCPnts import GCPnts_AbscissaPoint, GCPnts_UniformAbscissa, GCPnts_UniformDeflection
from OCP.Geom import Geom_TrimmedCurve
from OCP.GeomAbs import (GeomAbs_BezierCurve, GeomAbs_BSplineCurve, GeomAbs_Circle, GeomAbs_Ellipse,
                         GeomAbs_Hyperbola, GeomAbs_Line, GeomAbs_Parabola, GeomAbs_Plane)
from OCP.GeomAdaptor import GeomAdaptor_Curve, GeomAdaptor_Surface
from OCP.GeomAPI import GeomAPI_ProjectPointOnCurve
from OCP.HLRAlgo import HLRAlgo_Projector
from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
from OCP.Precision import Precision
from OCP.ShapeAnalysis import ShapeAnalysis_FreeBounds
from OCP.ShapeExtend import ShapeExtend_WireData
from OCP.ShapeFix import ShapeFix_ShapeTolerance, ShapeFix_Wire
from OCP.TopAbs import (TopAbs_COMPOUND, TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED, TopAbs_SOLID, TopAbs_VERTEX,
                        TopAbs_WIRE, TopAbs_SHELL)
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Shape
try:
    from OCP.TopTools import TopTools_HSequenceOfShape
except ImportError:                     # OCP 8 moved OCCT's collections
    from OCP.collections import HSequence_TopoDS_Shape as TopTools_HSequenceOfShape
from OCP.gp import gp, gp_Ax1, gp_Ax2, gp_Ax3, gp_Circ, gp_Dir, gp_Pln, gp_Pnt, gp_Trsf, gp_Vec

try:
    from OCP.TopTools import TopTools_IndexedMapOfShape
except ImportError:                     # OCP 8 moved OCCT's collections
    from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedMapOfShape

import cam_areaext as X

CONFUSION = 1e-7
SQ_CONFUSION = CONFUSION * CONFUSION
DBL_MAX = 1.7976931348623157e308

# ─── parameters (AreaParams.h) ──────────────────────────────────────────────────────────────────────────────────────

# the enum lists of AREA_PARAMS_*, by NAME
ENUMS = {
    "Fill": ("None", "Face", "Auto"), "Coplanar": ("None", "Check", "Force"), "OpenMode": ("None", "Union", "Edges"),
    "PocketMode": ("None", "ZigZag", "Offset", "Spiral", "ZigZagOffset", "Line", "Grid", "Triangle"),
    "SectionMode": ("Absolute", "BoundBox", "Workplane"),
    "SubjectFill": ("NonZero", "EvenOdd", "Positive", "Negative"),
}
FILL_RULE = {"EvenOdd": 0, "NonZero": 1, "Positive": 2, "Negative": 3}      # Clipper2Lib::FillRule's values
CLIP_OP = {0: 2, 1: 3, 2: 1, 3: 4}           # OperationUnion/Difference/Intersection/Xor -> Clipper2Lib::ClipType

FillNone, FillFace, FillAuto = 0, 1, 2
CoplanarNone, CoplanarCheck, CoplanarForce = 0, 1, 2
OpenModeNone, OpenModeUnion, OpenModeEdges = 0, 1, 2
(PocketModeNone, PocketModeZigZag, PocketModeOffset, PocketModeSpiral, PocketModeZigZagOffset, PocketModeLine,
 PocketModeGrid, PocketModeTriangle) = range(8)
OperationUnion, OperationDifference, OperationIntersection, OperationXor, OperationCompound = range(5)
SectionModeAbsolute, SectionModeBoundBox, SectionModeWorkplane = range(3)
ArcPlaneNone, ArcPlaneAuto, ArcPlaneXY, ArcPlaneZX, ArcPlaneYZ, ArcPlaneVariable = range(6)
SortModeNone, SortMode2D5, SortMode3D, SortModeGreedy = range(4)
OrientationNormal, OrientationReversed = range(2)
(DirectionNone, DirectionXPositive, DirectionXNegative, DirectionYPositive, DirectionYNegative, DirectionZPositive,
 DirectionZNegative) = range(7)
RetractAxisX, RetractAxisY, RetractAxisZ = range(3)

# AREA_PARAMS_CONF: CAREA, then BASE, OFFSET, POCKET, SECTION, in AreaParams.h's order, with their defaults
CONF_DEFAULTS = {
    "Tolerance": CONFUSION, "FitArcs": True, "Accuracy": 0.01, "ClipperScale": 1e7,
    "Fill": 2, "Coplanar": 2, "Reorient": True, "Outline": False, "Explode": False, "OpenMode": 0,
    "Deflection": 0.01, "SubjectFill": "NonZero",
    "Offset": 0.0, "ExtraPass": 0, "Stepover": 0.0,
    "PocketMode": 0, "ToolRadius": 1.0, "PocketExtraOffset": 0.0, "PocketStepover": 0.0, "FromCenter": False,
    "Angle": 45.0, "AngleShift": 0.0, "Shift": 0.0, "ForceMaxStepover": False,
    "SectionCount": 0, "Stepdown": 1.0, "SectionOffset": 0.0, "SectionTolerance": 1e-6, "SectionMode": 2,
    "Project": False,
}
CONF_TYPES = {k: type(v) for k, v in CONF_DEFAULTS.items()}
CONF_TYPES["ExtraPass"] = int
CONF_TYPES["SectionCount"] = int

# AREA_PARAMS_PATH by ARG name, with their defaults
PATH_DEFAULTS = {
    "arc_plane": 1, "sort_mode": 1, "min_dist": 0.0, "abscissa": 3.0, "nearest_k": 3, "orientation": 0,
    "direction": 0, "threshold": 0.0, "retract_axis": 2, "retraction": 0.0, "resume_height": 0.0,
    "segmentation": 0.0, "feedrate": 0.0, "feedrate_v": 0.0, "verbose": True, "abs_center": False, "preamble": True,
    "deflection": 0.01,
}
SORT_ARGS = ("sort_mode", "min_dist", "abscissa", "nearest_k", "orientation", "direction", "threshold",
             "retract_axis")


class AreaError(ValueError):
    """Base::ValueError from Area.cpp."""


def _float(name, v):
    if isinstance(v, bool):
        return float(v)
    if hasattr(v, "Value") and not isinstance(v, (int, float)):
        return float(v.Value)
    return float(v)


def _check_params(p):
    """PARAM_ENUM_CHECK: each enum within its list."""
    for k, vals in ENUMS.items():
        v = p[k]
        if k == "SubjectFill":
            if v not in vals:
                raise AreaError(f"invalid value for enum {k}")
            continue
        if not isinstance(v, int) or not 0 <= v < len(vals):
            raise AreaError(f"invalid value for enum {k}")


class AreaConfig:
    """CAreaConfig: libarea's parameters saved, set from the area's, and restored on leaving."""

    def __init__(self, params, no_fit_arcs=False):
        self.p, self.no_fit = params, no_fit_arcs

    def __enter__(self):
        self.saved = (X.get_tolerance(), X.get_fit_arcs(), X.get_accuracy(), X.get_clipper_scale())
        X.set_tolerance(self.p["Tolerance"])
        X.set_fit_arcs(bool(self.p["FitArcs"]))
        X.set_accuracy(self.p["Accuracy"])
        X.set_clipper_scale(self.p["ClipperScale"])
        if self.no_fit:
            X.set_fit_arcs(False)
        return self

    def __exit__(self, *a):
        t, f, acc, sc = self.saved
        X.set_tolerance(t)
        X.set_fit_arcs(f)
        X.set_accuracy(acc)
        X.set_clipper_scale(sc)


def _fill(p):
    return FILL_RULE[p["SubjectFill"]]


# ─── small OCC helpers ──────────────────────────────────────────────────────────────────────────────────────────────

def _subs(shape, kind):
    m = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, kind, m)
    return [m.FindKey(i) for i in range(1, m.Extent() + 1)]


def _explore(shape, kind, avoid=None):
    ex = TopExp_Explorer(shape, kind, avoid) if avoid is not None else TopExp_Explorer(shape, kind)
    while ex.More():
        yield ex.Current()
        ex.Next()


def _has(shape, kind):
    return TopExp_Explorer(shape, kind).More()


def _compound(shapes=()):
    b, c = BRep_Builder(), TopoDS_Compound()
    b.MakeCompound(c)
    for s in shapes:
        b.Add(c, s)
    return c


def _copy_trsf(t):
    """A gp_Trsf's copy (OCP has no copy constructor): the identity multiplied by it, which gp_Trsf::Multiply
    copies member by member."""
    r = gp_Trsf()
    r.Multiply(t)
    return r


def _moved(shape, trsf):
    return shape.Moved(TopLoc_Location(trsf))


def _bnd(b):
    lo, hi = b.CornerMin(), b.CornerMax()
    return lo.X(), lo.Y(), lo.Z(), hi.X(), hi.Y(), hi.Z()


def _end_points_edge(e):
    e = TopoDS.Edge(e)
    return BRep_Tool.Pnt_s(TopExp.FirstVertex_s(e)), BRep_Tool.Pnt_s(TopExp.LastVertex_s(e))


def _end_points_wire(w):
    xp = BRepTools_WireExplorer(TopoDS.Wire(w))
    p1 = BRep_Tool.Pnt_s(TopoDS.Vertex(xp.CurrentVertex()))
    while xp.More():
        xp.Next()
    p2 = BRep_Tool.Pnt_s(TopoDS.Vertex(xp.CurrentVertex()))
    return p1, p2


def _is_closed(s):
    if s.ShapeType() == TopAbs_WIRE:
        return BRep_Tool.IsClosed_s(TopoDS.Wire(s))
    if s.ShapeType() == TopAbs_EDGE:
        return BRep_Tool.IsClosed_s(TopoDS.Edge(s))
    return BRep_Tool.IsClosed_s(s)


def get_shape_plane(shape):
    """getShapePlane: the plane of a planar face, or BRepLib_FindSurface's for anything else; None if not planar."""
    if shape is None or shape.IsNull():
        return None
    if shape.ShapeType() == TopAbs_FACE:
        adapt = BRepAdaptor_Surface(TopoDS.Face(shape))
        if adapt.GetType() != GeomAbs_Plane:
            return None
        return adapt.Plane()
    finder = BRepLib_FindSurface(shape.Located(TopLoc_Location()), -1, True)
    if not finder.Found():
        return None
    pln = GeomAdaptor_Surface(finder.Surface()).Plane()
    pln.Transform(shape.Location().Transformation())
    return pln


def is_coplanar(s1, s2):
    if s1 is None or s2 is None or s1.IsNull() or s2.IsNull():
        return False
    if s1.IsSame(s2):
        return True
    p1, p2 = get_shape_plane(s1), get_shape_plane(s2)
    if p1 is None or p2 is None:
        return False
    return p1.Position().IsCoplanar(p2.Position(), CONFUSION, CONFUSION)


def discretize(curve, reversed_, deflection):
    """Area.cpp's discretize: the curve's points by GCPnts_UniformDeflection, first and last exactly."""
    first, last = curve.FirstParameter(), curve.LastParameter()
    ret = [curve.Value(last if reversed_ else first)]
    d = GCPnts_UniformDeflection(curve, deflection, first, last)
    if not d.IsDone():
        raise RuntimeError("Curve discretization failed")
    n = d.NbPoints()
    if n > 1:
        if reversed_:
            for i in range(n - 1, 0, -1):
                ret.append(d.Value(i))
        else:
            for i in range(2, n + 1):
                ret.append(d.Value(i))
    ret.append(curve.Value(first if reversed_ else last))
    return ret


# ─── FaceMakerBullseye and Part::CrossSection (as Area.cpp calls them) ─────────────────────────────────────────────

def face_maker_bullseye(wires, plane=None):
    """Part::FaceMakerBullseye with setPlane and addWire, Build(): its Shape (a face, a compound of faces, or None)."""
    from cad_agent import feature as F
    from OCP.BRepBndLib import BRepBndLib as _BB
    if not wires:
        return None
    for w in wires:
        if not BRep_Tool.IsClosed_s(TopoDS.Wire(w)):
            raise AreaError("Wire is not closed.")
    if plane is None:
        comp = _compound(wires)
        finder = BRepLib_FindSurface(comp, -1, True)
        if not finder.Found():
            raise AreaError("Wires are not coplanar.")
        plane = GeomAdaptor_Surface(finder.Surface()).Plane()
    infos = []
    for w in wires:
        box = Bnd_Box()
        _BB.AddOptimal_s(w, box, False)
        if not box.IsVoid():
            infos.append((math.sqrt(box.SquareExtent()), TopoDS.Wire(w)))
    infos = F._stable_sort_desc(infos)
    faces = []
    for _, w in infos:
        found = None
        for f in reversed(faces):
            if f.hit_test(w) == "hit":
                found = f
        if found is not None:
            found.add_hole(w)
        else:
            faces.append(F._Driller(plane, w))
    shapes = [f.face for f in faces]
    if not shapes:
        return None
    return shapes[0] if len(shapes) == 1 else _compound(shapes)


def _fix_wire(wire):
    """CrossSection::fixWire."""
    fx = ShapeFix_Wire()
    fx.SetPrecision(CONFUSION)
    fx.Load(TopoDS.Wire(wire))
    fx.FixReorder()
    fx.FixConnected()
    fx.FixClosed()
    return fx.Wire()


def _fc_boolean(mk, args, tools):
    from cad_agent.topo_boolean import TopTools_ListOfShape
    a, t = TopTools_ListOfShape(), TopTools_ListOfShape()
    for s in args:
        a.Append(s)
    for s in tools:
        t.Append(s)
    mk.SetArguments(a)
    mk.SetTools(t)
    mk.SetRunParallel(True)
    mk.SetNonDestructive(True)
    mk.SetFuzzyValue(0.0)          # FuzzyHelper::withBooleanFuzzy(.0): Area.cpp slices without fuzziness
    mk.Build()
    return mk


def cross_section(a, b, c, shape, d):
    """Part::CrossSection(a, b, c, shape).slice(d): the solids cut by the half space, their faces on the plane's
    wires; then the shells' and faces' section edges joined; duplicates removed."""
    wires = []
    for s in _explore(shape, TopAbs_SOLID):
        _slice_solid(a, b, c, d, s, wires)
    for s in _explore(shape, TopAbs_SHELL, TopAbs_SOLID):
        _slice_non_solid(a, b, c, d, s, wires)
    for s in _explore(shape, TopAbs_FACE, TopAbs_SHELL):
        _slice_non_solid(a, b, c, d, s, wires)
    out = []
    for w in wires:
        e1 = _subs(w, TopAbs_EDGE)
        dup = False
        for x in out:
            e2 = _subs(x, TopAbs_EDGE)
            if len(e1) == len(e2) and all(p.IsSame(q) for p, q in zip(e1, e2)):
                dup = True
                break
        if not dup:
            out.append(w)
    return out


def _slice_non_solid(a, b, c, d, shape, wires):
    mk = _fc_boolean(BRepAlgoAPI_Section(), [shape], [BRepBuilderAPI_MakeFace(gp_Pln(a, b, c, -d)).Face()])
    if mk.IsDone():
        edges = [TopoDS.Edge(e) for e in _explore(mk.Shape(), TopAbs_EDGE)]
        while edges:
            mkw = BRepBuilderAPI_MakeWire()
            mkw.Add(edges.pop(0))
            new_wire = mkw.Wire()
            found = True
            while found:
                found = False
                for k, e in enumerate(edges):
                    mkw.Add(e)
                    if mkw.Error() != BRepBuilderAPI_DisconnectedWire:
                        found = True
                        edges.pop(k)
                        new_wire = mkw.Wire()
                        break
            wires.append(_fix_wire(new_wire))


def _slice_solid(a, b, c, d, shape, wires):
    plane = gp_Pln(a, b, c, -d)
    face = BRepBuilderAPI_MakeFace(plane).Face()
    v = gp_Vec(a, b, c)
    v.Normalize()
    v.Multiply(d + 1.0)
    ref = gp_Pnt(0.0, 0.0, 0.0)
    ref.Translate(v)
    half = BRepPrimAPI_MakeHalfSpace(face, ref).Solid()
    mk = _fc_boolean(BRepAlgoAPI_Cut(), [shape], [half])
    if not mk.IsDone():
        return
    fuzzy = mk.FuzzyValue()
    for f in _subs(mk.Shape(), TopAbs_FACE):
        adapt = BRepAdaptor_Surface(TopoDS.Face(f))
        if adapt.GetType() == GeomAbs_Plane:
            pl = adapt.Plane()
            tol = BRep_Tool.Tolerance_s(TopoDS.Face(f)) + fuzzy
            if pl.Axis().IsParallel(plane.Axis(), CONFUSION) and pl.Distance(plane.Location()) < tol:
                hw = TopTools_HSequenceOfShape()
                for w in _subs(f, TopAbs_WIRE):
                    hw.Append(w)
                sorted_ = TopTools_HSequenceOfShape()
                ShapeAnalysis_FreeBounds.ConnectWiresToWires_s(hw, CONFUSION, False, sorted_)
                for i in range(1, sorted_.Length() + 1):
                    wires.append(_fix_wire(sorted_.Value(i)))


# ─── WireJoiner (Area.cpp) ──────────────────────────────────────────────────────────────────────────────────────────

class _EdgeInfo:
    __slots__ = ("edge", "p1", "p2", "box", "iteration", "iStart", "iEnd", "used", "hasBox", "serial")

    def __init__(self, e, p1, p2, bbox, serial):
        self.edge, self.p1, self.p2 = e, p1, p2
        self.hasBox = False
        self.box = None
        self.serial = serial
        if bbox:
            b = Bnd_Box()
            BRepBndLib.Add_s(e, b)
            b.SetGap(0.1)
            if not b.IsVoid():
                self.box = _bnd(b)
                self.hasBox = True
        self.reset()

    def reset(self):
        self.iteration = 0
        self.used = False
        self.iStart = [-1, -1]
        self.iEnd = [-1, -1]


class WireJoiner:
    def __init__(self):
        self.edges = []          # the std::list, front first
        self.builder = BRep_Builder()
        self.comp = TopoDS_Compound()
        self.builder.MakeCompound(self.comp)
        self._serial = 0

    def add_edge(self, e, bbox=False):
        p1, p2 = _end_points_edge(e)
        self._serial += 1
        self.edges.insert(0, _EdgeInfo(TopoDS.Edge(e), p1, p2, bbox, self._serial))   # emplace_front

    def add(self, shape, bbox=False):
        for e in _explore(shape, TopAbs_EDGE):
            self.add_edge(e, bbox)

    def _vertices(self):
        """vmap's entries, in insertion order: (info, start)."""
        out = []
        for info in sorted(self.edges, key=lambda i: i.serial):
            out.append((info, True))
            out.append((info, False))
        return out

    @staticmethod
    def _pt(v):
        return v[0].p1 if v[1] else v[0].p2

    def join(self, tol):
        tol = tol * tol
        while self.edges:
            info0 = self.edges.pop(0)
            mk = BRepBuilderAPI_MakeWire()
            mk.Add(info0.edge)
            pstart, pend = info0.p1, info0.p2
            done = False
            for idx in range(2):
                if done:
                    break
                while self.edges:
                    pt = pstart if idx == 0 else pend
                    best = None
                    for v in self._vertices():
                        d = self._pt(v).SquareDistance(pt)
                        if best is None or d < best[0]:
                            best = (d, v)
                    d, v = best
                    if d > tol:
                        break
                    info, start = v
                    if d > SQ_CONFUSION:
                        p = self._pt(v)
                        if idx:
                            mk.Add(BRepBuilderAPI_MakeEdge(pend, p).Edge())
                        else:
                            mk.Add(BRepBuilderAPI_MakeEdge(p, pstart).Edge())
                    if idx == 1 and start:
                        pend = info.p2
                        mk.Add(info.edge)
                    elif idx == 0 and not start:
                        pstart = info.p1
                        mk.Add(info.edge)
                    elif idx == 0 and start:
                        pstart = info.p2
                        mk.Add(TopoDS.Edge(info.edge.Reversed()))
                    else:
                        pend = info.p1
                        mk.Add(TopoDS.Edge(info.edge.Reversed()))
                    self.edges.remove(info)
                    if pstart.SquareDistance(pend) <= SQ_CONFUSION:
                        done = True
                        break
            self.builder.Add(self.comp, mk.Wire())

    def split_edges(self):
        """splitEdges: an edge with another edge's end point inside it is split there."""
        i = 0
        while i < len(self.edges):
            info = self.edges[i]
            if not info.hasBox:
                i += 1
                continue
            pstart, pend = info.p1, info.p2
            pt = None
            intersects = False
            for other in sorted(self.edges, key=lambda x: x.serial):
                if intersects:
                    break
                if not other.hasBox or not _boxes_intersect(info.box, other.box):
                    continue
                if info.edge.IsSame(other.edge):
                    continue
                for k in range(2):
                    p = other.p1 if k else other.p2
                    if pstart.SquareDistance(p) <= SQ_CONFUSION or pend.SquareDistance(p) <= SQ_CONFUSION:
                        continue
                    ext = BRepExtrema_DistShapeShape(BRepBuilderAPI_MakeVertex(p).Vertex(), info.edge)
                    if ext.IsDone() and ext.NbSolution():
                        pp = ext.PointOnShape2(1)
                        if ext.SupportTypeShape2(1) == BRepExtrema_IsOnEdge:
                            par = ext.ParOnEdgeS2(1)
                            curve, first, last = _curve(info.edge)
                            if par < first or par > last:
                                pp = curve.Value(max(first, min(last, par)))
                        if pp.SquareDistance(p) <= SQ_CONFUSION:
                            pt = pp
                            intersects = True
                            break
            if not intersects:
                i += 1
                continue
            curve, first, last = _curve(info.edge)
            reversed_ = pstart.SquareDistance(curve.Value(last)) <= SQ_CONFUSION
            if reversed_:
                m1, m2 = BRepBuilderAPI_MakeEdge(curve, pt, pstart), BRepBuilderAPI_MakeEdge(curve, pend, pt)
            else:
                m1, m2 = BRepBuilderAPI_MakeEdge(curve, pstart, pt), BRepBuilderAPI_MakeEdge(curve, pt, pend)
            if not m1.IsDone() or not m2.IsDone():
                i += 1
                continue
            self.edges.pop(i)
            for k, e in enumerate((m1.Edge(), m2.Edge())):
                p1, p2 = _end_points_edge(e)
                self._serial += 1
                self.edges.insert(i + k, _EdgeInfo(e, p1, p2, True, self._serial))
            # the loop goes on with the first half (it = edges.emplace(itNext, edge1))

    def find_closed_wires(self, tol=CONFUSION):
        adjacent = []
        to_visit = []
        skips = 0
        for info in self.edges:
            info.reset()
        verts = self._vertices()
        for info in self.edges:
            if BRep_Tool.IsClosed_s(info.edge):
                self.builder.Add(self.comp, BRepBuilderAPI_MakeWire(info.edge).Wire())
                continue
            pts = (info.p1, info.p2)
            for i in range(2):
                if info.iStart[i] >= 0:
                    continue
                info.iEnd[i] = info.iStart[i] = len(adjacent)
                near = sorted(verts, key=lambda v: self._pt(v).SquareDistance(pts[i]))     # stable: ties in order
                for v in near:
                    if self._pt(v).SquareDistance(pts[i]) > tol:
                        break
                    adjacent.append(v)
                    info.iEnd[i] += 1
                for j in range(info.iStart[i], info.iEnd[i]):
                    o_info, o_start = adjacent[j]
                    if o_info is not info:
                        k = 0 if o_start else 1
                        o_info.iStart[k] = info.iStart[i]
                        o_info.iEnd[k] = info.iEnd[i]
            if info.iStart[0] != info.iEnd[0] and info.iStart[1] != info.iEnd[1]:
                to_visit.append(info)
            else:
                skips += 1
        to_visit.sort(key=lambda x: x.serial, reverse=True)        # std::set<EdgeInfo*>: allocation order
        iteration = 0
        while to_visit:
            iteration += 1
            current = to_visit.pop(0)
            cur_idx = 1
            e = current.edge
            pstart, pend = current.p1, current.p2
            current.used = True
            current.iteration = iteration
            stack, vstack = [], []
            while True:
                stack.append([len(vstack), len(vstack), len(vstack)])      # iStart, iEnd, iCurrent
                r = stack[-1]
                for i in range(current.iStart[cur_idx], current.iEnd[cur_idx]):
                    inf = adjacent[i][0]
                    if inf.iteration != iteration:
                        inf.iteration = iteration
                        vstack.append(adjacent[i])
                        r[1] += 1
                while True:
                    r = stack[-1]
                    if r[2] < r[1]:
                        v = vstack[r[2]]
                        pend = v[0].p2 if v[1] else v[0].p1
                        current = v[0]
                        cur_idx = 1 if v[1] else 0
                        break
                    del vstack[r[0]:]
                    stack.pop()
                    if not stack:
                        break
                    stack[-1][2] += 1
                if not stack:
                    skips += 1
                    break
                if pstart.SquareDistance(pend) > tol:
                    continue
                wd = ShapeExtend_WireData()
                wd.Add(e)
                for r in stack:
                    inf, start = vstack[r[2]]
                    wd.Add(inf.edge if start else TopoDS.Edge(inf.edge.Reversed()))
                wire = _make_clean_wire(wd, 0.01)
                if not BRep_Tool.IsClosed_s(wire):
                    skips += 1
                else:
                    for r in stack:
                        inf = vstack[r[2]][0]
                        if not inf.used:
                            inf.used = True
                            if inf in to_visit:
                                to_visit.remove(inf)
                    self.builder.Add(self.comp, wire)
                break
        return skips


def _boxes_intersect(a, b):
    return not (a[3] < b[0] or b[3] < a[0] or a[4] < b[1] or b[4] < a[1] or a[5] < b[2] or b[5] < a[2])


def _curve(edge):
    e = TopoDS.Edge(edge)
    first, last = BRep_Tool.Range_s(e)
    return BRep_Tool.Curve_s(e, 0.0, 0.0), first, last


def _make_clean_wire(wd, tol):
    """WireJoiner::makeCleanWire (TechDraw::EdgeWalker's)."""
    mk = BRepBuilderAPI_MakeWire()
    stol = ShapeFix_ShapeTolerance()
    fixer = ShapeFix_Wire()
    fixer.Load(wd)
    fixer.Perform()
    fixer.FixReorder()
    fixer.SetMaxTolerance(tol)
    fixer.ClosedWireMode = True            # fixer->ClosedWireMode() = Standard_True (a property in OCP)
    fixer.FixConnected(CONFUSION)
    fixer.FixClosed(CONFUSION)
    for i in range(1, wd.NbEdges() + 1):
        edge = fixer.WireData().Edge(i)
        stol.SetTolerance(edge, tol, TopAbs_VERTEX)
        mk.Add(edge)
    return mk.Wire()


# ─── Area ───────────────────────────────────────────────────────────────────────────────────────────────────────────

class Area:
    """Path.Area (Path::Area and AreaPy)."""

    def __init__(self, **kw):
        self.myShapes = []                # [(op, shape)]
        self.myTrsf = gp_Trsf()
        self.myParams = dict(CONF_DEFAULTS)
        self.myWorkPlane = TopoDS_Shape()
        self.myShapePlane = TopoDS_Shape()
        self.myHaveFace = False
        self.myHaveSolid = False
        self.myShapeDone = False
        self.myProjecting = False
        self.mySkippedShapes = 0
        self.myArea = None
        self.myAreaOpen = None
        self.mySections = []
        self.myShape = TopoDS_Shape()
        if kw:
            self.setParams(**kw)

    def _copy(self, deep=True):
        """Area(const Area&, deep_copy)."""
        o = Area()
        o.myShapes = list(self.myShapes)
        o.myTrsf = _copy_trsf(self.myTrsf)
        o.myParams = dict(self.myParams)
        o.myWorkPlane = self.myWorkPlane
        o.myHaveFace, o.myHaveSolid = self.myHaveFace, self.myHaveSolid
        if not deep or not self.isBuilt():
            return o
        if self.myArea is not None:
            o.myArea = X.Area(self.myArea)
        o.myShapePlane = self.myShapePlane
        o.myShape = self.myShape
        o.myShapeDone = self.myShapeDone
        o.mySections = [s._copy(True) for s in self.mySections]
        return o

    # ── AreaPy ──
    def setPlane(self, shape):
        sh = _topo(shape)
        self.clean()
        if sh is None or sh.IsNull():
            self.myWorkPlane = TopoDS_Shape()
            return self
        plane, trsf = self.findPlane(sh)
        if plane is None:
            raise AreaError("shape is not planar")
        self.myWorkPlane = plane
        self.myTrsf = trsf
        return self

    def add(self, shape, op=0):
        if isinstance(shape, (list, tuple)):
            for s in shape:
                if _topo(s) is None:
                    raise TypeError("non-shape object in sequence")
            for s in shape:
                self._add(_topo(s), op)
            return self
        sh = _topo(shape)
        if sh is None:
            raise TypeError("shape must be 'TopoShape' or list of 'TopoShape'")
        self._add(sh, op)
        return self

    def _add(self, shape, op):
        if shape is None or shape.IsNull():
            raise AreaError("null shape")
        if op != OperationCompound and op not in CLIP_OP:
            raise AreaError("invalid Operation")
        have_solid = _has(shape, TopAbs_SOLID)
        if (not have_solid and self.myHaveSolid) or (have_solid and not self.myHaveSolid and self.myShapes):
            raise AreaError("mixing solid and planar shapes is not allowed")
        self.myHaveSolid = have_solid
        self.clean()
        if op != OperationCompound and not self.myShapes:
            op = OperationUnion
        self.myShapes.append((op, shape))

    def setParams(self, **kw):
        p = dict(self.myParams)
        for k, v in kw.items():
            if k not in CONF_DEFAULTS:
                raise TypeError(f"'{k}' is an invalid keyword argument")
            t = CONF_TYPES[k]
            if t is bool:
                p[k] = bool(v)
            elif t is int:
                p[k] = int(v)
            elif k == "SubjectFill":
                p[k] = ENUMS["SubjectFill"][v] if isinstance(v, int) else v
            elif t is float:
                p[k] = _float(k, v)
            else:
                p[k] = v
        for k in ("Fill", "Coplanar", "OpenMode", "PocketMode", "SectionMode"):
            p[k] = int(p[k])
        _check_params(p)
        if p != self.myParams:
            self.clean()
            self.myParams = p
        return self

    def getParams(self):
        out = dict(self.myParams)
        out["SubjectFill"] = ENUMS["SubjectFill"].index(out["SubjectFill"])
        return out

    def getShape(self, index=-1, rebuild=False):
        from cad_agent.fcshim._fc_part import wrap
        if rebuild:
            self.clean()
        return wrap(self._get_shape(index))

    def makeOffset(self, index=-1, offset=0.0, extra_pass=0, stepover=0.0):
        from cad_agent.fcshim._fc_part import wrap
        return wrap(self._make_offset_shape(index, float(offset), int(extra_pass), float(stepover)))

    def makePocket(self, index=-1, mode=PocketModeZigZagOffset, tool_radius=1.0, extra_offset=0.0, stepover=0.0,
                   from_center=False, angle=45.0, angle_shift=0.0, shift=0.0, force_max_stepover=False):
        from cad_agent.fcshim._fc_part import wrap
        return wrap(self._make_pocket(index, int(mode), float(tool_radius), float(extra_offset), float(stepover),
                                      bool(from_center), float(angle), float(angle_shift), float(shift)))

    def makeSections(self, mode=SectionModeWorkplane, project=False, heights=None, plane=None):
        h = []
        if heights is not None:
            if isinstance(heights, float):
                h = [heights]
            elif isinstance(heights, (list, tuple)):
                for x in heights:
                    if not isinstance(x, float):
                        raise TypeError("heights must only contain float type")
                h = list(heights)
            else:
                raise TypeError("heights must be of type float or list/tuple of float")
        pl = _topo(plane) if plane is not None else TopoDS_Shape()
        return [s._copy(True) for s in self._make_sections(int(mode), bool(project), h, pl)]

    def getRestArea(self, cleared, diameter):
        raise NotImplementedError("Path.Area.getRestArea (rest machining) is not ported")

    def toTopoShape(self):
        from cad_agent.fcshim._fc_part import wrap
        self.build()
        return wrap(self._to_shape_area(self.myArea, False, self.myTrsf.Inverted()))

    @property
    def Sections(self):
        from cad_agent.fcshim._fc_part import wrap
        return [wrap(self._get_shape(i)) for i in range(len(self.mySections))]

    @property
    def Shapes(self):
        from cad_agent.fcshim._fc_part import wrap
        return [(wrap(s), op) for op, s in self.myShapes]

    @property
    def Workplane(self):
        from cad_agent.fcshim._fc_part import wrap
        return wrap(self.getPlane())

    @Workplane.setter
    def Workplane(self, s):
        self.setPlane(s)

    # ── Area.cpp ──
    def clean(self, delete_shapes=False):
        self.myShapeDone = False
        self.mySections = []
        self.myShape = TopoDS_Shape()
        self.myArea = None
        self.myAreaOpen = None
        self.myShapePlane = TopoDS_Shape()
        if delete_shapes:
            self.myShapes = []
            self.myHaveFace = False
            self.myHaveSolid = False

    def isBuilt(self):
        return self.myArea is not None or bool(self.mySections)

    @staticmethod
    def findPlane(shape):
        state = {"plane": None, "trsf": gp_Trsf(), "z": 0.0}
        _foreach_subshape(shape, lambda s, t: _find_plane(state, s), TopAbs_FACE)
        return state["plane"], state["trsf"]

    def getPlane(self, want_trsf=False):
        if not self.myWorkPlane.IsNull():
            return (self.myWorkPlane, _copy_trsf(self.myTrsf)) if want_trsf else self.myWorkPlane
        if self.myShapePlane.IsNull():
            if not self.myShapes:
                raise AreaError("no shape added")
            state = {"plane": None, "trsf": self.myTrsf, "z": 0.0}
            for _, s in self.myShapes:
                _foreach_subshape(s, lambda sh, t: _find_plane(state, sh), TopAbs_FACE)
            self.myTrsf = state["trsf"]
            if state["plane"] is None:
                raise AreaError("shapes are not planar")
            self.myShapePlane = state["plane"]
        return (self.myShapePlane, _copy_trsf(self.myTrsf)) if want_trsf else self.myShapePlane

    @staticmethod
    def add_wire(area, wire, trsf, deflection, to_edges=False):
        """Area::addWire: a wire's edges into a CCurve, in the plane trsf maps to XY."""
        c = X.Curve()
        w = TopoDS.Wire(_moved(wire, trsf) if trsf is not None else wire)
        xp = BRepTools_WireExplorer(w)
        if not xp.More():
            return
        p = BRep_Tool.Pnt_s(xp.CurrentVertex())
        c.append(0, p.X(), p.Y())
        while xp.More():
            edge = TopoDS.Edge(xp.Current())
            curve = BRepAdaptor_Curve(edge)
            reversed_ = xp.Current().Orientation() == TopAbs_REVERSED
            p = curve.Value(curve.FirstParameter() if reversed_ else curve.LastParameter())

            def append_discretized(cv):
                pts = discretize(cv, reversed_, deflection)
                for pt in pts[1:]:
                    c.append(0, pt.X(), pt.Y())

            def append_arc(arc):
                first, last = arc.FirstParameter(), arc.LastParameter()
                circ = arc.Circle()
                if not circ.Axis().Direction().IsParallel(gp.DZ_s(), CONFUSION):
                    append_discretized(arc)
                    return
                center = circ.Location()
                t = -1 if circ.Axis().Direction().Z() < 0 else 1
                if reversed_:
                    t = -t
                if abs(first - last) > math.pi:
                    mid = arc.Value((first + last) * 0.5)
                    c.append(t, mid.X(), mid.Y(), center.X(), center.Y())
                end = arc.Value(first if reversed_ else last)
                c.append(t, end.X(), end.Y(), center.X(), center.Y())

            gt = curve.GetType()
            if gt == GeomAbs_Line:
                c.append(0, p.X(), p.Y())
            elif gt == GeomAbs_Circle:
                append_arc(curve)
            elif gt in (GeomAbs_BSplineCurve, GeomAbs_BezierCurve, GeomAbs_Ellipse, GeomAbs_Hyperbola,
                        GeomAbs_Parabola):
                if not curve.Is3DCurve() or (gt == GeomAbs_BSplineCurve and curve.Degree() == 1):
                    append_discretized(curve)
                elif GCPnts_AbscissaPoint.Length_s(curve) < CONFUSION:
                    c.append(0, p.X(), p.Y())
                else:
                    segs = None
                    try:
                        from cad_agent.fcshim import _fc_biarcs
                        trimmed = Geom_TrimmedCurve(curve.Curve().Curve(), curve.FirstParameter(),
                                                    curve.LastParameter())
                        trimmed.Transform(curve.Trsf())
                        segs = _fc_biarcs.to_biarcs_handles(trimmed, deflection)
                    except Exception:  # noqa: BLE001 - biarcs failed: discretize, as Area.cpp does
                        segs = None
                    if segs is None:
                        append_discretized(curve)
                    else:
                        for seg in (list(reversed(segs)) if reversed_ else segs):
                            sc = GeomAdaptor_Curve(seg)
                            if sc.GetType() == GeomAbs_Circle:
                                append_arc(sc)
                            else:
                                pt = sc.Value(sc.FirstParameter() if reversed_ else sc.LastParameter())
                                c.append(0, pt.X(), pt.Y())
            else:
                append_discretized(curve)
            xp.Next()
        if to_edges:
            c.Discretize()
            vs = c.vertices()
            for k in range(1, len(vs)):
                cc = X.Curve()
                cc.set_vertices([vs[k - 1], vs[k]])
                area.append(cc)
        else:
            if BRep_Tool.IsClosed_s(TopoDS.Wire(wire)) and not c.IsClosed():
                vs = c.vertices()
                c.append(*vs[0])
            area.append(c)

    @staticmethod
    def add_shape(area, shape, trsf, deflection, plane, force_coplanar, area_open=None, to_edges=False,
                  reorient=True):
        """Area::addShape: faces' wires; else closed and open wires; else edges."""
        have_shape = False
        skipped = 0
        for face in _explore(shape, TopAbs_FACE):
            have_shape = True
            if plane is not None and not is_coplanar(face, plane):
                skipped += 1
                if force_coplanar:
                    continue
            for w in _explore(face, TopAbs_WIRE):
                Area.add_wire(area, w, trsf, deflection)
        if have_shape:
            return skipped
        a, a_open = X.Area(), X.Area()
        for w in _explore(shape, TopAbs_WIRE):
            have_shape = True
            if plane is not None and not is_coplanar(w, plane):
                skipped += 1
                if force_coplanar:
                    continue
            if BRep_Tool.IsClosed_s(TopoDS.Wire(w)):
                Area.add_wire(a, w, trsf, deflection)
            elif to_edges:
                for e in _explore(w, TopAbs_EDGE):
                    Area.add_wire(a_open, BRepBuilderAPI_MakeWire(TopoDS.Edge(e)).Wire(), trsf, deflection, True)
            else:
                Area.add_wire(a_open, w, trsf, deflection)
        if not have_shape:
            for e in _explore(shape, TopAbs_EDGE):
                if plane is not None and not is_coplanar(e, plane):
                    skipped += 1
                    if force_coplanar:
                        continue
                wire = BRepBuilderAPI_MakeWire(TopoDS.Edge(e)).Wire()
                Area.add_wire(a if BRep_Tool.IsClosed_s(wire) else a_open, wire, trsf, deflection)
        if reorient:
            a.Reorder()
        area.splice(a)
        if area_open is not None:
            area_open.splice(a_open)
        else:
            area.splice(a_open)
        return skipped

    def _add_to_build(self, area, shape):
        p = self.myParams
        if p["Fill"] == FillAuto and not self.myHaveFace:
            self.myHaveFace = _has(shape, TopAbs_FACE)
        plane = self.getPlane()
        a_open = X.Area()
        self.mySkippedShapes += Area.add_shape(area, shape, self.myTrsf, p["Deflection"],
                                               None if p["Coplanar"] == CoplanarNone else plane,
                                               self.myHaveSolid or p["Coplanar"] == CoplanarForce, a_open,
                                               p["OpenMode"] == OpenModeEdges, p["Reorient"])
        if self.myProjecting:
            area.reverse_closed_clockwise()
        if a_open.num_curves():
            if area is self.myArea or p["OpenMode"] == OpenModeNone:
                self.myAreaOpen.splice(a_open)

    def _explode(self, shape):
        plane = self.getPlane()
        p = self.myParams
        have_shape = False
        for f in _explore(shape, TopAbs_FACE):
            have_shape = True
            if p["Coplanar"] != CoplanarNone and not is_coplanar(f, plane):
                self.mySkippedShapes += 1
                if p["Coplanar"] == CoplanarForce:
                    continue
            for w in _explore(f, TopAbs_WIRE):
                xp = BRepTools_WireExplorer(TopoDS.Wire(w))
                while xp.More():
                    Area.add_wire(self.myArea, BRepBuilderAPI_MakeWire(TopoDS.Edge(xp.Current())).Wire(),
                                  self.myTrsf, p["Deflection"], True)
                    xp.Next()
        if have_shape:
            return
        for e in _explore(shape, TopAbs_EDGE):
            if p["Coplanar"] != CoplanarNone and not is_coplanar(e, plane):
                self.mySkippedShapes += 1
                if p["Coplanar"] == CoplanarForce:
                    continue
            Area.add_wire(self.myArea, BRepBuilderAPI_MakeWire(TopoDS.Edge(e)).Wire(), self.myTrsf,
                          p["Deflection"], True)

    def build(self):
        if self.isBuilt():
            return
        if not self.myShapes:
            raise AreaError("no shape added")
        p = self.myParams
        if self.myHaveSolid and p["SectionCount"]:
            self.mySections = self._make_sections(p["SectionMode"], p["Project"], [], TopoDS_Shape())
            return
        _, trsf = self.getPlane(True)
        try:
            self.myArea = X.Area()
            self.myAreaOpen = X.Area()
            with AreaConfig(p):
                area_clip = X.Area()
                self.mySkippedShapes = 0
                op = OperationUnion
                pending = False
                exploding = p["Explode"]
                shapes = (self._get_projected_shapes(trsf) if (p["Outline"] and not self.myProjecting)
                          else self.myShapes)
                for s_op, s in shapes:
                    if exploding:
                        exploding = False
                        self._explode(s)
                        continue
                    elif op != s_op:
                        if p["OpenMode"] != OpenModeNone:
                            self.myArea.splice(self.myAreaOpen)
                        pending = False
                        if area_clip.num_curves():
                            if op == OperationCompound:
                                self.myArea.splice(area_clip)
                            else:
                                self.myArea.Clip(CLIP_OP[op], area_clip, _fill(p))
                                area_clip.clear()
                        op = s_op
                    self._add_to_build(self.myArea if op == OperationUnion else area_clip, s)
                    pending = True
                if pending:
                    if p["OpenMode"] != OpenModeNone:
                        self.myArea.splice(self.myAreaOpen)
                    if op == OperationCompound:
                        self.myArea.splice(area_clip)
                    else:
                        self.myArea.Clip(CLIP_OP[op], area_clip, _fill(p))
                self.myArea.splice(self.myAreaOpen)
                if p["Explode"]:
                    joiner = WireJoiner()
                    inv = self.myTrsf.Inverted()
                    for c in self.myArea.curves():
                        w = Area.to_shape_curve(c, inv)
                        if w is not None and not w.IsNull():
                            joiner.add(w)
                    joiner.join(CONFUSION)
                    area = Area()
                    area.myParams = dict(p)
                    area.myParams["Explode"] = False
                    area.myParams["Coplanar"] = CoplanarNone
                    area.myWorkPlane, area.myTrsf = self.getPlane(True)
                    area._add(joiner.comp, OperationCompound)
                    area.build()
                    self.myArea = area.myArea
                if p["Outline"]:
                    self.myArea.Reorder()
                    self.myArea.remove_closed_clockwise()
        except BaseException:
            self.clean()
            raise

    def _get_projected_shapes(self, trsf, inverse=True):
        ret = []
        loc = TopLoc_Location(trsf)
        inv = TopLoc_Location(loc.Inverted())
        self.mySkippedShapes = 0
        for op, s in self.myShapes:
            skipped, out = Area.project(s.Moved(loc), self.myParams, self.myWorkPlane)
            if skipped < 0:
                self.mySkippedShapes += 1
                continue
            self.mySkippedShapes += skipped
            if out is not None and not out.IsNull():
                ret.append((op, out.Moved(inv) if inverse else out))
        return ret

    @staticmethod
    def project(shape_in, params, work_plane=None):
        """Area::project: the shape's outline seen along Z (HLR), its visible edges joined into closed wires and
        united. Returns (skips, shape)."""
        try:
            hlr = HLRBRep_Algo()
            hlr.Add(shape_in, 0)
            hlr.Projector(HLRAlgo_Projector(gp_Ax2(gp_Pnt(), gp_Dir(0, 0, 1))))
            hlr.Update()
            hlr.Hide()
        except Exception:  # noqa: BLE001
            return -1, None
        joiner = WireJoiner()
        try:
            to_shape = HLRBRep_HLRToShape(hlr)
            for s in (to_shape.VCompound(), to_shape.OutLineVCompound()):
                if s is not None and not s.IsNull():
                    BRepLib.BuildCurves3d_s(s)
                    joiner.add(s, True)
        except Exception:  # noqa: BLE001
            return -1, None
        joiner.split_edges()
        tol = params["Tolerance"] if params else CONFUSION
        skips = joiner.find_closed_wires(tol)
        area = Area()
        area.myParams = dict(params)
        area.myParams.update(SectionCount=0, Offset=0.0, PocketMode=0, Explode=False, Reorient=False, Outline=True,
                             Fill=FillFace if _has(shape_in, TopAbs_FACE) else FillNone, Coplanar=CoplanarNone)
        area.myProjecting = True
        if work_plane is not None and not work_plane.IsNull():
            area.myWorkPlane = work_plane
        area._add(joiner.comp, OperationUnion)
        shape = area._get_shape(-1)
        if shape is None or shape.IsNull():
            return -1, None
        return skips, shape

    def _make_sections(self, mode, project, heights_in, section_plane):
        p = self.myParams
        if section_plane is not None and not section_plane.IsNull():
            plane, trsf = self.findPlane(section_plane)
        else:
            plane, trsf = self.getPlane(True)
        if plane is None or plane.IsNull():
            raise AreaError("failed to obtain section plane")
        loc = TopLoc_Location(trsf)
        bounds = Bnd_Box()
        for _, s in self.myShapes:
            BRepBndLib.Add_s(s.Moved(loc), bounds, False)
        bounds.SetGap(0.0)
        x_min, y_min, z_min, x_max, y_max, z_max = _bnd(bounds)
        heights = []
        tolerance = 0.0
        if not heights_in:
            d = abs(p["Stepdown"])
            if p["SectionCount"] > 1 and d < CONFUSION:
                raise AreaError("invalid stepdown")
            if mode == SectionModeBoundBox:
                z = z_max - p["SectionOffset"] if p["Stepdown"] > 0.0 else z_min + p["SectionOffset"]
            elif mode == SectionModeWorkplane:
                z = -p["SectionOffset"] if p["Stepdown"] > 0.0 else p["SectionOffset"]
            else:
                z = gp_Pnt(0, 0, p["SectionOffset"]).Transformed(loc.Transformation()).Z()
            if z > z_max:
                z = z_max
            elif z < z_min:
                z = z_min
            if p["Stepdown"] > 0.0:
                dz = z - z_min
                tolerance = p["SectionTolerance"]
            else:
                dz = z_max - z
                tolerance = -p["SectionTolerance"]
            count = p["SectionCount"]
            if count < 0 or count * d > dz:
                count = int(math.floor(dz / d)) + 1
            for _ in range(count):
                height = z - tolerance
                if z - z_min < p["SectionTolerance"]:
                    heights.append(z_min + p["SectionTolerance"])
                    if p["Stepdown"] > 0.0:
                        break
                elif z_max - z < p["SectionTolerance"]:
                    heights.append(z_max - p["SectionTolerance"])
                    if p["Stepdown"] < 0.0:
                        break
                else:
                    heights.append(height)
                z -= p["Stepdown"]
        else:
            hit_min = hit_max = False
            for z in heights_in:
                if mode == SectionModeAbsolute:
                    z = gp_Pnt(0, 0, z).Transformed(loc.Transformation()).Z()
                elif mode == SectionModeBoundBox:
                    z = z_max - z
                elif mode == SectionModeWorkplane:
                    z = -z
                else:
                    raise AreaError("invalid section mode")
                if z - z_min < p["SectionTolerance"]:
                    if hit_min:
                        continue
                    hit_min = True
                    z = z_min + p["SectionTolerance"]
                elif z_max - z < p["SectionTolerance"]:
                    if hit_max:
                        continue
                    z = z_max - p["SectionTolerance"]
                heights.append(z)
        if not heights:
            raise AreaError("no sections")
        sections = []
        projected = []
        if project:
            projected = self._get_projected_shapes(trsf, False)
            if not projected:
                return sections
        tolerance *= 2.0
        can_retry = abs(tolerance) > CONFUSION
        loc_inv = TopLoc_Location(loc.Inverted())
        for z in heights:
            retried = not can_retry
            while True:
                pln = gp_Pln(gp_Pnt(0, 0, z), gp_Dir(0, 0, 1))
                a, b, c, d = pln.Coefficients()
                face = BRepLib_MakeFace(pln, x_min, x_max, y_min, y_max).Face()
                area = Area()
                area.myParams = dict(p)
                area.myParams["Outline"] = False
                area.setPlane_raw(face.Moved(loc_inv))
                if project:
                    for op, s in projected:
                        t = gp_Trsf()
                        t.SetTranslation(gp_Vec(0, 0, -d))
                        area._add(s.Moved(TopLoc_Location(t)).Moved(loc_inv), op)
                    sections.append(area)
                    break
                for k, (op, s) in enumerate(self.myShapes):
                    comp = TopoDS_Compound()
                    builder = BRep_Builder()
                    builder.MakeCompound(comp)
                    for solid in _explore(s.Moved(loc), TopAbs_SOLID):
                        wires = cross_section(-a, -b, -c, solid, d)
                        if not wires:
                            continue
                        closed = [w for w in wires if BRep_Tool.IsClosed_s(TopoDS.Wire(w))]
                        try:
                            shape = face_maker_bullseye(closed, pln)
                            if shape is not None and not shape.IsNull():
                                wires = [w for w in wires if not BRep_Tool.IsClosed_s(TopoDS.Wire(w))]
                                kind = TopAbs_WIRE if p["Fill"] == FillNone else TopAbs_FACE
                                for x in _explore(shape, kind):
                                    builder.Add(comp, x)
                        except Exception:  # noqa: BLE001 - "FaceMakerBullseye failed on section"
                            pass
                        for w in wires:
                            builder.Add(comp, w)
                    if _has(comp, TopAbs_EDGE):
                        area._add(comp.Moved(loc_inv), op)
                    elif not area.myShapes:
                        if k + 1 < len(self.myShapes) and self.myShapes[k + 1][0] in (OperationIntersection,
                                                                                     OperationDifference):
                            break
                if area.myShapes:
                    sections.append(area)
                    break
                if retried:
                    break
                z += tolerance
                retried = True
        return sections

    def setPlane_raw(self, shape):
        self.clean()
        plane, trsf = self.findPlane(shape)
        if plane is None:
            raise AreaError("shape is not planar")
        self.myWorkPlane = plane
        self.myTrsf = trsf

    def _to_shape(self, area, fill, reorient=0):
        """Area::toShape(CArea&, short fill, int reorient)."""
        inv = self.myTrsf.Inverted()
        b_fill = self.myHaveFace if fill == FillAuto else (fill == FillFace)
        return self._to_shape_area(area, b_fill, inv, reorient)

    def _section_shape(self, op, index, *args):
        """AREA_SECTION."""
        if index >= len(self.mySections):
            return TopoDS_Shape()
        if index < 0:
            comp = _compound()
            builder = BRep_Builder()
            for a in self.mySections:
                s = getattr(a, op)(index, *args)
                if s is None or s.IsNull():
                    continue
                builder.Add(comp, s)
            return comp if _has(comp, TopAbs_EDGE) else TopoDS_Shape()
        return getattr(self.mySections[index], op)(index, *args)

    def _get_shape(self, index=-1):
        self.build()
        if self.mySections:
            return self._section_shape("_get_shape", index)
        if self.myShapeDone:
            return self.myShape
        if self.myArea is None:
            return TopoDS_Shape()
        p = self.myParams
        with AreaConfig(p):
            if abs(p["Offset"]) < CONFUSION:
                if p["PocketMode"] == PocketModeNone:
                    self.myShape = self._to_shape(self.myArea, p["Fill"])
                    self.myShapeDone = True
                    return self.myShape
                self.myShape = self._make_pocket(index, p["PocketMode"], p["ToolRadius"], p["PocketExtraOffset"],
                                                 p["PocketStepover"], p["FromCenter"], p["Angle"], p["AngleShift"],
                                                 p["Shift"])
                self.myShapeDone = True
                return self.myShape
            if p["PocketMode"] == PocketModeNone:
                self.myShape = self._make_offset_shape(index, p["Offset"], p["ExtraPass"], p["Stepover"])
                self.myShapeDone = True
                return self.myShape
            areas = self._make_offsets(p["Offset"], p["ExtraPass"], p["Stepover"])
            if not areas:
                areas.append(X.Area(self.myArea))
            area_pocket = Area()
            area_pocket.myParams = dict(p)
            front = True
            if len(areas) > 1:
                step = p["Stepover"]
                if abs(step) < CONFUSION:
                    step = p["Offset"]
                front = step > 0
            if front:
                area_pocket._add(self._to_shape(areas[0], p["Fill"]), OperationUnion)
                areas.pop()
            else:
                area_pocket._add(self._to_shape(areas[-1], p["Fill"]), OperationUnion)
                areas.pop(0)
            comp = _compound()
            builder = BRep_Builder()
            for a in areas:
                s = self._to_shape(a, FillNone)
                if s is None or s.IsNull():
                    continue
                builder.Add(comp, s)
            if _has(comp, TopAbs_EDGE):
                builder.Add(comp, area_pocket._make_pocket(-1, p["PocketMode"], p["ToolRadius"],
                                                           p["PocketExtraOffset"], p["PocketStepover"],
                                                           p["FromCenter"], p["Angle"], p["AngleShift"], p["Shift"]))
                self.myShape = comp
            self.myShapeDone = True
            return self.myShape

    def _make_offset_shape(self, index, offset, extra_pass, stepover, reorient=0, from_center=False):
        self.build()
        if self.mySections:
            return self._section_shape("_make_offset_shape", index, offset, extra_pass, stepover, reorient,
                                       from_center)
        areas = self._make_offsets(offset, extra_pass, stepover, from_center)
        if not areas:
            return TopoDS_Shape()
        comp = _compound()
        builder = BRep_Builder()
        for a in areas:
            fill = self.myParams["Fill"] if len(areas) == 1 else FillNone
            s = self._to_shape(a, fill, reorient)
            if s is None or s.IsNull():
                continue
            builder.Add(comp, s)
        return comp if _has(comp, TopAbs_EDGE) else TopoDS_Shape()

    def _single_offset(self, offset):
        a = X.Area(self.myArea)
        a.Offset(offset)
        return a

    def _make_offsets(self, offset, extra_pass, stepover, from_center=False):
        """Area::makeOffset(list<CArea>&, ...): the offset passes, with the gap search of a large stepover."""
        areas = []
        if abs(offset) < CONFUSION:
            return areas
        p = self.myParams
        count = 1
        if extra_pass:
            if abs(stepover) < CONFUSION:
                stepover = offset
            if extra_pass > 0:
                count += extra_pass
            else:
                if stepover > 0 or offset > 0:
                    raise AreaError("invalid extra count")
                count = -1
        previous = None
        tool_radius = p["ToolRadius"]
        check_gaps = not p["ForceMaxStepover"] and abs(stepover) > tool_radius
        gap_tol = p["Accuracy"]
        sign = 1.0 if stepover > 0 else -1.0
        i = 0
        while count < 0 or i < count:
            prev_offset = offset - stepover
            area = self._single_offset(offset)
            if previous is not None and check_gaps:
                opp = X.Area(area)
                opp.Offset(-sign * tool_radius)
                gap = X.Area(previous)
                gap.Subtract(opp)
                if gap.num_curves():
                    o_min = prev_offset + sign * tool_radius
                    o_max = offset
                    while abs(o_max - o_min) > gap_tol:
                        o_mid = (o_min + o_max) / 2.0
                        test = self._single_offset(o_mid)
                        opp = X.Area(test)
                        opp.Offset(-sign * tool_radius)
                        gap = X.Area(previous)
                        gap.Subtract(opp)
                        if gap.num_curves():
                            o_max = o_mid
                        else:
                            o_min = o_mid
                    offset = o_min - sign * p["Accuracy"]
                    area = self._single_offset(offset)
                previous = X.Area(area)
                previous.Offset(sign * tool_radius)
                if not previous.num_curves():
                    o_min, o_max = prev_offset, offset
                    while abs(o_max - o_min) > gap_tol:
                        o_mid = (o_min + o_max) / 2.0
                        test = self._single_offset(o_mid + sign * tool_radius)
                        if not test.num_curves():
                            o_max = o_mid
                        else:
                            o_min = o_mid
                    offset = (offset + o_max) / 2
                    area = self._single_offset(offset)
                    previous.clear()
            if check_gaps and previous is None:
                previous = X.Area(area)
                previous.Offset(sign * tool_radius)
            if not area.num_curves():
                break
            if from_center:
                areas.insert(0, area)
            else:
                areas.append(area)
            if previous is not None and not previous.num_curves():
                break
            i += 1
            offset += stepover
        return areas

    def _make_pocket(self, index, mode, tool_radius, extra_offset, stepover, from_center, angle, angle_shift, shift):
        if tool_radius < CONFUSION:
            raise AreaError("tool radius too small")
        if stepover == 0.0:
            stepover = tool_radius
        if stepover < CONFUSION:
            raise AreaError("stepover too small")
        if mode == PocketModeNone:
            return TopoDS_Shape()
        self.build()
        if self.mySections:
            return self._section_shape("_make_pocket", index, mode, tool_radius, extra_offset, stepover, from_center,
                                       angle, angle_shift, shift)
        done = False
        if index >= 0:
            if abs(angle_shift) >= CONFUSION:
                angle += index * angle_shift
            if abs(shift) >= CONFUSION:
                shift *= index
        if angle < -360.0:
            angle += math.ceil(abs(angle) / 360.0) * 360.0
        elif angle > 360.0:
            angle -= math.floor(angle / 360.0) * 360.0
        elif angle < 0.0:
            angle += 360.0
        if shift < -stepover:
            shift += math.ceil(abs(shift) / stepover) * stepover
        elif shift > stepover:
            shift -= math.floor(shift / stepover) * stepover
        elif shift < 0.0:
            shift += stepover
        p = self.myParams
        with AreaConfig(p):
            out = X.Area()
            if mode == PocketModeZigZag:
                pm = 1
            elif mode == PocketModeSpiral:
                pm = 0
            elif mode == PocketModeOffset:
                return self._make_offset_shape(index, -tool_radius - extra_offset - shift, -1, -stepover, -1,
                                               from_center)
            elif mode == PocketModeZigZagOffset:
                pm = 3
            elif mode in (PocketModeLine, PocketModeGrid, PocketModeTriangle):
                valid, bx0, by0, bx1, by1 = self.myArea.GetBox()
                if not valid:
                    raise AreaError("failed to get bound box")
                angles = [0.0]
                if mode == PocketModeGrid:
                    angles.append(90.0)
                    if shift < CONFUSION:
                        angles += [180.0, 270.0]
                elif mode == PocketModeTriangle:
                    angles += [120.0, 240.0]
                else:
                    shift = 0.0
                cx, cy = (bx0 + bx1) * 0.5, (by0 + by1) * 0.5
                r = _box_radius(bx0, by0, bx1, by1) + stepover
                if extra_offset > 0:
                    r += extra_offset
                steps = int(math.ceil(r * 2.0 / stepover))
                for a0 in angles:
                    a = angle + a0
                    if a > 360.0:
                        a -= 360.0
                    off = -r + shift
                    for _ in range(steps):
                        p1, p2 = (-r, off), (r, off)
                        if a > CONFUSION:
                            rr = math.radians(a)
                            p1, p2 = _rotate(p1, rr), _rotate(p2, rr)
                        c = X.Curve()
                        c.append(0, p1[0] + cx, p1[1] + cy)
                        c.append(0, p2[0] + cx, p2[1] + cy)
                        out.append(c)
                        off += stepover
                area = X.Area(self.myArea)
                area.Offset(-tool_radius - extra_offset)
                out.Clip(1, area, _fill(p))
                done = True
            else:
                raise AreaError("unknown pocket mode")
            if not done:
                inp = X.Area(self.myArea)
                inp.Reorder()
                out = inp.MakePocketToolpath(tool_radius, extra_offset, stepover, from_center, pm, angle)
            return self._to_shape(out, FillNone)

    @staticmethod
    def to_shape_curve(c, trsf=None, reorient=0):
        """Area::toShape(const CCurve&, trsf, reorient): the curve's spans as edges joined into wires."""
        if reorient:
            if c.IsClosed() and ((reorient > 0 and c.IsClockwise()) or (reorient < 0 and not c.IsClockwise())):
                c = X.Curve(c)
                c.Reverse()
        h_edges = TopTools_HSequenceOfShape()
        first = True
        pt = None
        accuracy = X.get_accuracy()
        for t, x, y, cx, cy in c.vertices():
            if first:
                first = False
                pt = gp_Pnt(x, y, 0)
                continue
            pnext = gp_Pnt(x, y, 0)
            if pnext.SquareDistance(pt) <= SQ_CONFUSION:
                continue
            if t == 0:
                h_edges.Append(BRepBuilderAPI_MakeEdge(pt, pnext).Edge())
            else:
                center = gp_Pnt(cx, cy, 0)
                r = center.Distance(pt)
                r2 = center.Distance(pnext)
                d = pt.Distance(pnext)
                minor = _is_left(pt, pnext, center) == (t > 0)
                small_dev = d * d / (8.0 * r) < CONFUSION
                small_circle = 2 * max(r, r2) < accuracy
                if (minor and small_dev) or small_circle:
                    h_edges.Append(BRepBuilderAPI_MakeEdge(pt, pnext).Edge())
                    pt = pnext
                    continue
                fix_arc = abs(r - r2) > CONFUSION
                while True:
                    if fix_arc:
                        rr = r * r
                        dd = d * d * 0.25
                        q = 0 if rr <= dd else math.sqrt(rr - dd)
                        mx = (pt.X() + pnext.X()) * 0.5
                        my = (pt.Y() + pnext.Y()) * 0.5
                        dx = q * (pt.Y() - pnext.Y()) / d
                        dy = q * (pnext.X() - pt.X()) / d
                        nc = gp_Pnt(mx + dx, my + dy, 0)
                        if _is_left(pt, pnext, center) != _is_left(pt, pnext, nc):
                            nc.SetX(mx - dx)
                            nc.SetY(my - dy)
                        center = nc
                    axis = gp_Ax2(center, gp_Dir(0, 0, t))
                    try:
                        mk = BRepBuilderAPI_MakeEdge(gp_Circ(axis, r), pt, pnext)
                        if not mk.IsDone():
                            raise RuntimeError("arc")
                        h_edges.Append(mk.Edge())
                        break
                    except Exception:  # noqa: BLE001 - Standard_Failure: retry with the centre fixed
                        if not fix_arc:
                            fix_arc = True
                        else:
                            raise
            pt = pnext
        h_wires = TopTools_HSequenceOfShape()
        ShapeAnalysis_FreeBounds.ConnectEdgesToWires_s(h_edges, CONFUSION, False, h_wires)
        n = h_wires.Length()
        if not n:
            return TopoDS_Shape()
        shape = h_wires.Value(1) if n == 1 else _compound([h_wires.Value(i) for i in range(1, n + 1)])
        if trsf is not None:
            shape.Move(TopLoc_Location(trsf))
        return shape

    @staticmethod
    def _to_shape_area(area, fill, trsf=None, reorient=0):
        """Area::toShape(const CArea&, bool fill, trsf, reorient)."""
        comp = _compound()
        builder = BRep_Builder()
        for c in area.curves():
            w = Area.to_shape_curve(c, trsf, reorient)
            if w is not None and not w.IsNull():
                builder.Add(comp, w)
        if not _has(comp, TopAbs_EDGE):
            return TopoDS_Shape()
        if fill:
            try:
                pln = gp_Pln()
                if trsf is not None:
                    pln = pln.Transformed(trsf)
                wires = list(_explore(comp, TopAbs_WIRE))
                s = face_maker_bullseye(wires, pln)
                return s if s is not None else TopoDS_Shape()
            except Exception:  # noqa: BLE001 - "FaceMakerBullseye failed": the wires instead
                pass
        return comp


def _is_left(a, b, c):
    return ((b.X() - a.X()) * (c.Y() - a.Y()) - (b.Y() - a.Y()) * (c.X() - a.X())) > 0


def _rotate(p, angle):
    """libarea Point::Rotate(angle)."""
    if abs(angle) < 1.0e-09:
        return p
    c, s = math.cos(angle), math.sin(angle)
    return (c * p[0] - s * p[1], s * p[0] + c * p[1])


def _box_radius(x0, y0, x1, y1):
    """CBox2D::Radius: half the diagonal."""
    w, h = x1 - x0, y1 - y0
    return math.sqrt(w * w + h * h) / 2


def _topo(s):
    if s is None:
        return None
    if isinstance(s, TopoDS_Shape):
        return s
    return getattr(s, "_s", None)


def _find_plane(state, shape):
    """FindPlane: the shape's plane, its normal made positive along an axis it is parallel to; the topmost XY one."""
    pln = get_shape_plane(shape)
    if pln is None:
        return
    pos = pln.Position()
    if not pos.Direct():
        pos = gp_Ax3(pos.Ax2())
    d = pos.Direction()
    x0, y0, z0 = abs(d.X()) < CONFUSION, abs(d.Y()) < CONFUSION, abs(d.Z()) < CONFUSION
    if x0 and y0:
        d.SetZ(abs(d.Z()))
    elif x0 and z0:
        d.SetY(abs(d.Y()))
    elif y0 and z0:
        d.SetX(abs(d.X()))
    pos.SetDirection(d)
    trsf = gp_Trsf()
    trsf.SetTransformation(pos)
    if x0 and y0:
        v = next(_explore(shape, TopAbs_VERTEX))
        z = BRep_Tool.Pnt_s(TopoDS.Vertex(v)).Z()
        if state["plane"] is not None and state["z"] > z:
            return
        state["z"] = z
    elif state["plane"] is not None:
        return
    state["plane"] = shape
    state["trsf"] = trsf


def _foreach_subshape(shape, func, kind=TopAbs_FACE, group_open_edges=False):
    """foreachSubshape: the solids, else faces, else wires, else edges (open ones grouped into one compound)."""
    res = None
    open_shapes = []
    order = [TopAbs_SOLID, TopAbs_FACE, TopAbs_WIRE, TopAbs_EDGE]
    start = order.index(kind) if kind in order else 3
    for k in order[start:]:
        for s in _explore(shape, k):
            res = k
            if k == TopAbs_WIRE and group_open_edges and not BRep_Tool.IsClosed_s(TopoDS.Wire(s)):
                open_shapes.append(s)
                continue
            if k == TopAbs_EDGE and group_open_edges:
                p1, p2 = _end_points_edge(s)
                if p1.SquareDistance(p2) > SQ_CONFUSION:
                    open_shapes.append(s)
                    continue
            func(s, k)
        if res is not None:
            break
    if not open_shapes:
        return res
    func(_compound(open_shapes), TopAbs_COMPOUND)
    return TopAbs_COMPOUND


# ─── sortWires and toPath ───────────────────────────────────────────────────────────────────────────────────────────

class _WireInfo:
    __slots__ = ("wire", "points", "pt_end", "isClosed", "serial")

    def pstart(self):
        return self.points[0]

    def pend(self):
        return self.pstart() if self.isClosed else self.pt_end


class _ShapeInfo:
    def __init__(self, shape, params, pln=None):
        self.myPln = pln
        self.myWires = []
        self.myRTree = []          # [(wire_info, index)] in insertion order
        self.myShape = shape
        self.myBestPt = gp_Pnt()
        self.myStartPt = gp_Pnt(1e20, 1e20, 1e20)
        self.myBestWire = None
        self.mySupport = None
        self.myParams = params
        self.myBestParameter = 0.0
        self.mySupportEdge = False
        self.myPlanar = pln is not None
        self.myRebase = False
        self.myStart = False
        self._serial = 0

    def _get_wires(self, shape, kind):
        """GetWires."""
        p = self.myParams
        info = _WireInfo()
        self._serial += 1
        info.serial = self._serial
        info.wire = TopoDS.Wire(shape) if kind == TopAbs_WIRE else BRepBuilderAPI_MakeWire(TopoDS.Edge(shape)).Wire()
        info.isClosed = BRep_Tool.IsClosed_s(info.wire)
        info.points = []
        info.pt_end = gp_Pnt()
        if info.isClosed and p["orientation"] == OrientationReversed:
            info.wire.Reverse()
        if p["abscissa"] < CONFUSION or not info.isClosed:
            p1, p2 = _end_points_wire(info.wire)
            if not info.isClosed and p["direction"] != DirectionNone:
                rev = _direction_reverse(p["direction"], p1, p2)
                if rev:
                    info.wire.Reverse()
                    p1, p2 = p2, p1
            info.points.append(p1)
            if not info.isClosed and p["direction"] == DirectionNone:
                info.points.append(p2)
            info.pt_end = p2
        else:
            xp = BRepTools_WireExplorer(info.wire)
            while xp.More():
                info.points.append(BRep_Tool.Pnt_s(xp.CurrentVertex()))
                curve = BRepAdaptor_Curve(xp.Current())
                d = GCPnts_UniformAbscissa(curve, p["abscissa"], curve.FirstParameter(), curve.LastParameter())
                if d.IsDone():
                    for i in range(2, d.NbPoints()):
                        info.points.append(curve.Value(d.Parameter(i)))
                xp.Next()
        self.myWires.append(info)
        for i in range(len(info.points)):
            self.myRTree.append((info, i))

    def nearest(self, pt):
        self.myStartPt = pt
        if not self.myWires:
            _foreach_subshape(self.myShape, self._get_wires, TopAbs_WIRE)
        # bgi::nearest(pt, k) into a map keyed by the wire (allocation order)
        k = self.myParams["k"]
        cand = sorted(self.myRTree, key=lambda r: r[0].points[r[1]].SquareDistance(pt))[:k]
        ret = {}
        for w, i in cand:
            ret.setdefault(id(w), (w, i))
        v = BRepBuilderAPI_MakeVertex(pt).Vertex()
        first = True
        best_d = 1e20
        self.myBestWire = self.myWires[0] if self.myWires else None
        for w, _i in sorted(ret.values(), key=lambda r: r[0].serial):
            wire = w.wire
            d = 0.0
            p = None
            done = False
            is_start = False
            support = None
            support_edge = False
            if BRep_Tool.IsClosed_s(TopoDS.Wire(wire)):
                ext = BRepExtrema_DistShapeShape(v, wire)
                if ext.IsDone() and ext.NbSolution():
                    d = ext.Value()
                    d *= d
                    p = ext.PointOnShape2(1)
                    support = ext.SupportOnShape2(1)
                    support_edge = ext.SupportTypeShape2(1) == BRepExtrema_IsOnEdge
                    done = True
            if not done:
                d1 = pt.SquareDistance(w.pstart())
                if self.myParams["direction"] != DirectionNone:
                    d, p, is_start = d1, w.pstart(), True
                else:
                    d2 = pt.SquareDistance(w.pend())
                    if d1 < d2:
                        d, p, is_start = d1, w.pstart(), True
                    else:
                        d, p, is_start = d2, w.pend(), False
            if not first and d >= best_d:
                continue
            first = False
            self.myBestPt = p
            self.myBestWire = w
            best_d = d
            self.myRebase = done
            self.myStart = is_start
            if done:
                self.mySupport = support
                self.mySupportEdge = support_edge
        return best_d

    def rebase_wire(self, pend, min_dist):
        """rebaseWire: the best wire started at the best point (an edge split there when it is inside one).
        pend is the caller's (sortWires sets it to the best point first). Returns (wire, pend)."""
        min_dist *= min_dist
        mk = BRepBuilderAPI_MakeWire()
        estart = None
        eend = None
        best = self.myBestWire
        state = 0
        while state < 3:
            xp = BRepTools_WireExplorer(TopoDS.Wire(best.wire))
            pprev = BRep_Tool.Pnt_s(xp.CurrentVertex())
            if state == 0 and not self.mySupportEdge and pprev.SquareDistance(self.myBestPt) <= SQ_CONFUSION:
                return best.wire, best.pend()
            pt = None
            while xp.More():
                edge = xp.Current()
                if state == 2 and estart.IsEqual(edge):
                    break
                curve, first, last = _curve(edge)
                pt = curve.Value(last)
                if pprev.SquareDistance(pt) <= SQ_CONFUSION:
                    reversed_ = True
                    pt = curve.Value(first)
                else:
                    reversed_ = False
                if state:
                    mk.Add(TopoDS.Edge(edge))
                elif self.mySupportEdge:
                    if edge.IsEqual(self.mySupport):
                        gpp = GeomAPI_ProjectPointOnCurve()
                        gpp.Init(self.myBestPt, curve)
                        gpp.Perform(self.myBestPt)
                        self.myBestPt = gpp.NearestPoint()
                        gpp.Perform(pprev)
                        pprev = gpp.NearestPoint()
                        gpp.Perform(pt)
                        pt = gpp.NearestPoint()
                        d1 = pprev.SquareDistance(self.myBestPt)
                        d2 = pt.SquareDistance(self.myBestPt)
                        split = False
                        if d1 > min_dist and d2 > min_dist:
                            if reversed_:
                                m1 = BRepBuilderAPI_MakeEdge(curve, self.myBestPt, pprev)
                                m2 = BRepBuilderAPI_MakeEdge(curve, pt, self.myBestPt)
                            else:
                                m1 = BRepBuilderAPI_MakeEdge(curve, pprev, self.myBestPt)
                                m2 = BRepBuilderAPI_MakeEdge(curve, self.myBestPt, pt)
                            if m1.IsDone() and m2.IsDone():
                                if reversed_:
                                    eend = TopoDS.Edge(m1.Edge().Reversed())
                                    mk.Add(TopoDS.Edge(m2.Edge().Reversed()))
                                else:
                                    eend = m1.Edge()
                                    mk.Add(m2.Edge())
                                pend = self.myBestPt
                                estart = self.mySupport
                                state = 1
                                split = True
                        if not split:
                            if d1 < d2:
                                pend = pprev
                                estart = edge
                                state = 1
                                mk.Add(TopoDS.Edge(edge))
                            else:
                                self.mySupportEdge = False
                                self.myBestPt = pt
                elif self.myBestPt.SquareDistance(pprev) <= SQ_CONFUSION:
                    pend = pprev
                    estart = edge
                    state = 1
                    mk.Add(TopoDS.Edge(edge))
                xp.Next()
                pprev = pt
            if state == 0:
                return best.wire, best.pend()
            state += 1
        if eend is not None:
            mk.Add(eend)
        if mk.IsDone():
            return mk.Wire(), pend
        return best.wire, best.pend()

    def sort_wires(self, pstart, min_dist, max_dist):
        wires = []
        pend = gp_Pnt(pstart.X(), pstart.Y(), pstart.Z())
        if not self.myWires or pstart.SquareDistance(self.myStartPt) > SQ_CONFUSION:
            self.nearest(pstart)
            if not self.myWires:
                return wires, pend, None
        pentry = self.myBestPt
        if min_dist < 0.01:
            min_dist = 0.01
        while True:
            if self.myRebase:
                w, pend = self.rebase_wire(self.myBestPt, min_dist)
                wires.append(w)
            elif not self.myStart:
                wires.append(self.myBestWire.wire.Reversed())
                pend = self.myBestWire.pstart()
            else:
                wires.append(self.myBestWire.wire)
                pend = self.myBestWire.pend()
            best = self.myBestWire
            self.myRTree = [r for r in self.myRTree if r[0] is not best]
            self.myWires.remove(best)
            if not self.myWires:
                break
            d = self.nearest(pend)
            if max_dist > 0 and d > max_dist:
                break
        return wires, pend, pentry


def _direction_reverse(direction, p1, p2):
    return {DirectionXPositive: p1.X() > p2.X(), DirectionXNegative: p1.X() < p2.X(),
            DirectionYPositive: p1.Y() > p2.Y(), DirectionYNegative: p1.Y() < p2.Y(),
            DirectionZPositive: p1.Z() > p2.Z(), DirectionZNegative: p1.Z() < p2.Z()}.get(direction, False)


def _axis(retract_axis):
    if retract_axis == RetractAxisX:
        return (lambda p: p.X()), (lambda p, v: p.SetX(v))
    if retract_axis == RetractAxisY:
        return (lambda p: p.Y()), (lambda p, v: p.SetY(v))
    return (lambda p: p.Z()), (lambda p, v: p.SetZ(v))


def sort_wires_impl(shapes, has_start, pstart, arc_plane, sp, want_hint=False):
    """Area::sortWires: (wires, pstart, pend, stepdown_hint, arc_plane)."""
    wires = []
    pend = gp_Pnt()
    if not shapes:
        return wires, pstart, pend, None, arc_plane
    getter, setter = _axis(sp["retract_axis"])
    sort_mode = sp["sort_mode"]
    if sort_mode == SortModeGreedy and sp["threshold"] < CONFUSION:
        sort_mode = SortMode2D5
    if sort_mode == SortModeNone:
        if arc_plane not in (ArcPlaneYZ, ArcPlaneZX):
            arc_plane = ArcPlaneXY
        for shape in shapes:
            if shape is not None and not shape.IsNull():
                def orient(s, kind, _w=wires):
                    w = s if kind == TopAbs_WIRE else BRepBuilderAPI_MakeWire(TopoDS.Edge(s)).Wire()
                    if BRep_Tool.IsClosed_s(TopoDS.Wire(w)):
                        if sp["orientation"] == OrientationReversed:
                            w = w.Reversed()
                    elif sp["direction"] != DirectionNone:
                        p1, p2 = _end_points_wire(w)
                        if _direction_reverse(sp["direction"], p1, p2):
                            w = w.Reversed()
                    _w.append(w)
                _foreach_subshape(shape, orient, TopAbs_WIRE)
        return wires, pstart, pend, None, arc_plane
    rparams = {"abscissa": sp["abscissa"], "k": sp["nearest_k"] if sp["nearest_k"] > 0 else 1,
               "orientation": sp["orientation"], "direction": sp["direction"]}
    shape_list = []
    trsf = gp_Trsf()
    arc = {"plane": arc_plane, "found": False}
    if sort_mode == SortMode3D:
        comp = _compound([s for s in shapes if s is not None and not s.IsNull()])
        if _has(comp, TopAbs_EDGE):
            shape_list.append(_ShapeInfo(comp, rparams))
    else:
        for shape in shapes:
            if shape is not None and not shape.IsNull():
                _foreach_subshape(shape, lambda s, t: _shape_info_builder(s, t, shape_list, rparams, arc, trsf),
                                  TopAbs_FACE, True)
    arc_plane = arc["plane"]
    if not shape_list:
        return wires, pstart, pend, None, arc_plane
    bounds = Bnd_Box()
    use_bound = not has_start or pstart is None
    pstart = gp_Pnt(pstart.X(), pstart.Y(), pstart.Z()) if pstart is not None else gp_Pnt()
    for info in shape_list:
        if arc["found"]:
            info.myShape.Move(TopLoc_Location(trsf))
            if info.myPlanar:
                info.myPln.Transform(trsf)
        BRepBndLib.Add_s(info.myShape, bounds, False)
    if use_bound or sort_mode in (SortMode2D5, SortModeGreedy):
        i = 0
        while i < len(shape_list):
            it = shape_list[i]
            if not it.myPlanar:
                i += 1
                continue
            comp = _compound()
            builder = BRep_Builder()
            empty = True
            j = i + 1
            while j < len(shape_list):
                other = shape_list[j]
                if not other.myPlanar or not it.myPln.Position().IsCoplanar(other.myPln.Position(), CONFUSION,
                                                                          CONFUSION):
                    j += 1
                    continue
                builder.Add(comp, other.myShape)
                shape_list.pop(j)
                empty = False
            if not empty:
                builder.Add(comp, it.myShape)
                it.myShape = comp
            i += 1
    bounds.SetGap(0.0)
    x_min, y_min, z_min, x_max, y_max, z_max = _bnd(bounds)
    if use_bound:
        pstart = gp_Pnt(x_max, y_max, z_max)
    else:
        if sp["retract_axis"] == RetractAxisX:
            if pstart.X() < x_max:
                pstart.SetX(x_max)
        elif sp["retract_axis"] == RetractAxisY:
            if pstart.Y() < y_max:
                pstart.SetY(y_max)
        else:
            if pstart.Z() < z_max:
                pstart.SetZ(z_max)
    out_pstart = gp_Pnt(pstart.X(), pstart.Y(), pstart.Z())
    pln = None
    hint = 0.0
    hint_first = True
    current = None
    current_height = getter(pstart)
    max_dist = sp["threshold"] * sp["threshold"] if sort_mode == SortModeGreedy else 0
    first_entry = use_bound
    while shape_list:
        best_d = DBL_MAX
        best = shape_list[0]
        for it in shape_list:
            if it.myPlanar and current is None:
                d = it.myPln.SquareDistance(pstart)
            else:
                d = it.nearest(pstart)
            if d < best_d:
                best = it
                best_d = d
        if sort_mode == SortModeGreedy:
            if current is None:
                current = best
                current_height = getter(pstart)
            elif best_d > max_dist:
                setter(pstart, current_height)
                current.nearest(pstart)
                best = current
        ws, pend, pentry = best.sort_wires(pstart, sp["min_dist"], max_dist)
        wires.extend(ws)
        if first_entry:
            first_entry = False
            if pentry is not None:
                out_pstart = pentry
        if sort_mode in (SortMode2D5, SortMode3D) and want_hint:
            if not best.myPlanar:
                hint_first = True
            elif hint_first:
                hint_first = False
            else:
                P = pln.Position().Location()
                loc = best.myPln.Position().Location()
                dd = best.myPln.Position().Direction()
                d = dd.X() * (P.X() - loc.X()) + dd.Y() * (P.Y() - loc.Y()) + dd.Z() * (P.Z() - loc.Z())
                if d < 0:
                    d = -d
                if d > hint:
                    hint = d
            pln = best.myPln
        pstart = pend
        if not best.myWires:
            if current is best:
                current = None
            shape_list.remove(best)
    return wires, out_pstart, pend, (hint if hint != 0.0 else None), arc_plane


def _shape_info_builder(shape, kind, shape_list, params, arc, trsf):
    """ShapeInfoBuilder."""
    pln = get_shape_plane(shape)
    if pln is None:
        shape_list.append(_ShapeInfo(shape, params))
        return
    shape_list.append(_ShapeInfo(shape, params, pln))
    if arc["found"] or arc["plane"] in (ArcPlaneNone, ArcPlaneVariable):
        return
    if kind == TopAbs_EDGE:
        if BRepAdaptor_Curve(TopoDS.Edge(shape)).GetType() != GeomAbs_Circle:
            return
    else:
        if not any(BRepAdaptor_Curve(TopoDS.Edge(e)).GetType() == GeomAbs_Circle for e in _explore(shape, TopAbs_EDGE)):
            return
    pos = shape_list[-1].myPln.Position()
    if not pos.Direct():
        pos = gp_Ax3(pos.Ax2())
    d = pos.Direction()
    x0, y0, z0 = abs(d.X()) <= CONFUSION, abs(d.Y()) <= CONFUSION, abs(d.Z()) <= CONFUSION
    ap = arc["plane"]
    dst = None
    if ap == ArcPlaneAuto:
        if x0 and y0:
            arc["plane"] = ArcPlaneXY
        elif x0 and z0:
            arc["plane"] = ArcPlaneZX
        elif z0 and y0:
            arc["plane"] = ArcPlaneYZ
        else:
            arc["plane"] = ArcPlaneXY
            dst = gp_Ax3(pos.Location(), gp_Dir(0, 0, 1))
        if dst is None:
            arc["found"] = True
            return
    elif ap == ArcPlaneXY:
        if x0 and y0:
            arc["found"] = True
            return
        dst = gp_Ax3(pos.Location(), gp_Dir(0, 0, 1))
    elif ap == ArcPlaneZX:
        if x0 and z0:
            arc["found"] = True
            return
        dst = gp_Ax3(pos.Location(), gp_Dir(0, 1, 0))
    elif ap == ArcPlaneYZ:
        if z0 and y0:
            arc["found"] = True
            return
        dst = gp_Ax3(pos.Location(), gp_Dir(1, 0, 0))
    else:
        return
    trsf.SetTransformation(pos)
    t = gp_Trsf()
    t.SetTransformation(dst)
    trsf.PreMultiply(t.Inverted())
    arc["found"] = True


def _add_param(verbose, params, name, last, nxt, relative=False):
    """addParameter."""
    if math.isnan(nxt):
        return
    if math.isnan(last) and relative:
        raise ValueError("trying to add relative parameter with unknown last value")
    d = nxt - last
    if not verbose and abs(d) <= CONFUSION:
        return
    params[name] = d if relative else nxt


def to_path(shapes, pstart_in, kw):
    """Area::toPath: (Path.Path, pend)."""
    from cad_agent.fcshim._fc_path import Command, Path
    path = Path()
    cmds = path._cmds
    has_start = pstart_in is not None
    pstart = gp_Pnt(pstart_in.X(), pstart_in.Y(), pstart_in.Z()) if has_start else gp_Pnt()
    sp = {k: kw[k] for k in SORT_ARGS}
    wires, pstart, pend, _hint, arc_plane = sort_wires_impl(shapes, has_start, pstart, kw["arc_plane"], sp, True)
    if not wires:
        return path, pend
    current_arc_plane = arc_plane

    def add_cmd(name, params=None):
        c = Command()
        object.__setattr__(c, "_name", name)
        c._params.update(params or {})
        cmds.append(c)
        return c
    if kw["preamble"]:
        add_cmd("G90")
        if kw["abs_center"]:
            add_cmd("G90.1")
        if arc_plane == ArcPlaneZX:
            add_cmd("G18")
        elif arc_plane == ArcPlaneYZ:
            add_cmd("G19")
        else:
            current_arc_plane = ArcPlaneXY
            add_cmd("G17")
    getter, setter = _axis(kw["retract_axis"])
    threshold = abs(kw["threshold"])
    if threshold < CONFUSION:
        threshold = CONFUSION
    threshold *= threshold
    retraction, resume = kw["retraction"], kw["resume_height"]
    verbose, abs_center, segmentation = kw["verbose"], kw["abs_center"], kw["segmentation"]
    if not has_start or pstart.SquareDistance(pstart_in) > SQ_CONFUSION:
        setter(pstart, resume)
    nan = float("nan")

    def add_gcode(verb, last, nxt, name):
        params = {}
        _add_param(verb, params, "X", last.X(), nxt.X())
        _add_param(verb, params, "Y", last.Y(), nxt.Y())
        _add_param(verb, params, "Z", last.Z(), nxt.Z())
        return add_cmd(name, params)

    def add_g0(last, nxt, height):
        pt = gp_Pnt(nxt.X(), nxt.Y(), nxt.Z())
        setter(pt, height)
        if not last.IsEqual(pt, CONFUSION):
            add_gcode(False, last, pt, "G0")

    state = {"f": 0.0}

    def add_g1(last, nxt, f):
        c = add_gcode(verbose, last, nxt, "G1")
        if f > CONFUSION:
            _add_param(verbose, c._params, "F", state["f"], f)
            state["f"] = f

    def add_garc(ps, pe, center, cw, f):
        params = {}
        if abs_center:
            _add_param(verbose, params, "I", 0.0, center.X())
            _add_param(verbose, params, "J", 0.0, center.Y())
            _add_param(verbose, params, "K", 0.0, center.Z())
        else:
            _add_param(verbose, params, "I", ps.X(), center.X(), True)
            _add_param(verbose, params, "J", ps.Y(), center.Y(), True)
            _add_param(verbose, params, "K", ps.Z(), center.Z(), True)
        _add_param(verbose, params, "X", ps.X(), pe.X())
        _add_param(verbose, params, "Y", ps.Y(), pe.Y())
        _add_param(verbose, params, "Z", ps.Z(), pe.Z())
        if f > CONFUSION:
            _add_param(verbose, params, "F", state["f"], f)
            state["f"] = f
        add_cmd("G2" if cw else "G3", params)

    plast = gp_Pnt(nan, nan, nan)
    p = gp_Pnt(nan, nan, nan)
    setter(p, max(retraction, getter(pstart)))
    add_gcode(False, plast, p, "G0")
    plast = p
    p = gp_Pnt(pstart.X(), pstart.Y(), pstart.Z())
    setter(p, retraction)
    add_gcode(False, plast, p, "G0")
    plast = p
    first = True
    nf = abs(kw["feedrate"])
    vf = abs(kw["feedrate_v"])
    if vf < CONFUSION:
        vf = nf
    deflection = kw["deflection"]
    for wire in wires:
        xp = BRepTools_WireExplorer(TopoDS.Wire(wire))
        p = BRep_Tool.Pnt_s(xp.CurrentVertex())
        pt_tmp = gp_Pnt(p.X(), p.Y(), p.Z())
        pl_tmp = gp_Pnt(plast.X(), plast.Y(), plast.Z())
        setter(pt_tmp, 0.0)
        setter(pl_tmp, 0.0)
        if first:
            # addG0 takes `last` by value: both moves are written against plast
            add_g0(plast, p, retraction)
            add_g0(plast, p, resume)
        elif pt_tmp.SquareDistance(pl_tmp) > threshold:
            add_g0(plast, plast, retraction)
            add_g0(plast, p, retraction)
            add_g0(plast, p, resume)
        add_g1(plast, p, vf)
        plast = p
        first = False
        while xp.More():
            edge = xp.Current()
            curve = BRepAdaptor_Curve(TopoDS.Edge(edge))
            reversed_ = edge.Orientation() == TopAbs_REVERSED
            p = curve.Value(curve.FirstParameter() if reversed_ else curve.LastParameter())
            gt = curve.GetType()
            handled = False
            if gt == GeomAbs_Line:
                if segmentation > CONFUSION:
                    d = GCPnts_UniformAbscissa(curve, segmentation, curve.FirstParameter(), curve.LastParameter())
                    if d.IsDone() and d.NbPoints() > 2:
                        n = d.NbPoints()
                        rng = range(n - 1, 0, -1) if reversed_ else range(2, n + 1)
                        for i in rng:
                            pt = curve.Value(d.Parameter(i))
                            add_g1(plast, pt, nf)
                            plast = pt
                        handled = True
                if not handled:
                    add_g1(plast, p, nf)
                handled = True
            elif gt == GeomAbs_Circle:
                circle = curve.Circle()
                dr = circle.Axis().Direction()
                plane = ArcPlaneNone
                cw = False
                cmd = ""
                if abs(dr.X()) < CONFUSION and abs(dr.Y()) < CONFUSION:
                    cw, plane, cmd = dr.Z() < 0, ArcPlaneXY, "G17"
                elif abs(dr.Z()) < CONFUSION and abs(dr.X()) < CONFUSION:
                    cw, plane, cmd = dr.Y() < 0, ArcPlaneZX, "G18"
                elif abs(dr.Y()) < CONFUSION and abs(dr.Z()) < CONFUSION:
                    cw, plane, cmd = dr.X() < 0, ArcPlaneYZ, "G19"
                if plane != ArcPlaneNone and (plane == current_arc_plane or arc_plane == ArcPlaneVariable):
                    if plane != current_arc_plane:
                        add_cmd(cmd)
                    if reversed_:
                        cw = not cw
                    center = circle.Location()
                    fst, lst = curve.FirstParameter(), curve.LastParameter()
                    seg_done = False
                    if segmentation > CONFUSION:
                        d = GCPnts_UniformAbscissa(curve, segmentation, fst, lst)
                        if d.IsDone() and d.NbPoints() > 2:
                            n = d.NbPoints()
                            rng = range(n - 1, 0, -1) if reversed_ else range(2, n + 1)
                            for i in rng:
                                pt = curve.Value(d.Parameter(i))
                                add_garc(plast, pt, center, cw, nf)
                                plast = pt
                            seg_done = True
                    if not seg_done:
                        if abs(fst - lst) > math.pi:
                            mid = curve.Value((lst - fst) * 0.5 + fst)
                            add_garc(plast, mid, center, cw, nf)
                            plast = mid
                        add_garc(plast, p, center, cw, nf)
                    handled = True
            if not handled:
                pts = discretize(curve, reversed_, deflection)
                for pt in pts[1:]:
                    add_g1(plast, pt, nf)
                    plast = pt
            plast = p
            xp.Next()
    return path, pend


def _shapes_arg(shapes):
    from cad_agent.fcshim._fc_part import Shape
    if isinstance(shapes, Shape):
        return [shapes._s]
    if isinstance(shapes, (list, tuple)):
        out = []
        for s in shapes:
            if not isinstance(s, Shape):
                raise TypeError("non-shape object in sequence")
            out.append(s._s)
        return out
    return []


def fromShapes(shapes, start=None, return_end=False, **kw):
    """Path.fromShapes."""
    from cad_agent.fcshim._fc_base import Vector
    args = dict(PATH_DEFAULTS)
    for k, v in kw.items():
        if k not in PATH_DEFAULTS:
            raise TypeError(f"'{k}' is an invalid keyword argument for fromShapes()")
        d = PATH_DEFAULTS[k]
        args[k] = bool(v) if isinstance(d, bool) else (int(v) if isinstance(d, int) else _float(k, v))
    ps = gp_Pnt(start.x, start.y, start.z) if start is not None else None
    path, pend = to_path(_shapes_arg(shapes), ps, args)
    if not return_end:
        return path
    return path, Vector(pend.X(), pend.Y(), pend.Z())


def sortWires(shapes, start=None, **kw):
    """Path.sortWires: (wires, end) or (wires, end, arc_plane)."""
    from cad_agent.fcshim._fc_base import Vector
    from cad_agent.fcshim._fc_part import wrap
    args = {"arc_plane": 1, **{k: PATH_DEFAULTS[k] for k in SORT_ARGS}}
    for k, v in kw.items():
        if k not in args:
            raise TypeError(f"'{k}' is an invalid keyword argument for sortWires()")
        d = args[k]
        args[k] = bool(v) if isinstance(d, bool) else (int(v) if isinstance(d, int) else _float(k, v))
    need_arc = args["arc_plane"] == ArcPlaneAuto
    ps = gp_Pnt(start.x, start.y, start.z) if start is not None else gp_Pnt()
    sp = {k: args[k] for k in SORT_ARGS}
    wires, _, pend, _, arc_plane = sort_wires_impl(_shapes_arg(shapes), start is not None, ps, args["arc_plane"], sp)
    lst = [wrap(TopoDS.Wire(w)) for w in wires]
    end = Vector(pend.X(), pend.Y(), pend.Z())
    return (lst, end, arc_plane) if need_arc else (lst, end)


FeatureArea = None
FeatureAreaView = None

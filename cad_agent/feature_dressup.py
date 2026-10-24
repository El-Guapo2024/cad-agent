# SPDX-License-Identifier: LGPL-2.1-or-later
#
# A translation of FreeCAD's PartDesign dress-up features (src/Mod/PartDesign/App/FeatureDressUp.cpp,
# FeatureFillet.cpp, FeatureChamfer.cpp, FeatureDraft.cpp, FeatureThickness.cpp) and the TopoShape calls they
# make (src/Mod/Part/App/TopoShapeExpansion.cpp: makeElementFillet, makeElementChamfer, makeElementDraft,
# makeElementThickSolid, fixSolidOrientation) at FreeCAD 3160daf1e2b6. FreeCAD is (c) its contributors
# (Juergen Riegel and others), under the GNU Lesser General Public License, version 2.1 or (at your option)
# any later version; so is this file. See ../NOTICE.
"""PartDesign's dress-up features, Fillet, Chamfer, Draft and Thickness, for cad_agent.feature's FEATURES.

Each takes FreeCAD's Base, the feature before it and the sub-elements it works on, as FreeCAD's Python
writes it (`fillet.Base = (pad, ["Edge3", "Face2"])`), and FreeCAD's properties in snake_case:

    Fillet("Fillet", ("Pad", ["Edge3", "Edge5"]), radius=2.0)          Radius 1, UseAllEdges, Refine
    Chamfer("Chamfer", ("Pad", ["Face6"]), chamfer_type="Two distances", size=1.0, size2=2.0)
                                     ChamferType "Equal distance" | "Two distances" | "Distance and Angle",
                                     Size 1, Size2 1, Angle 45 (degrees), FlipDirection, UseAllEdges, Refine
    Draft("Draft", ("Pad", ["Face1", "Face2"]), angle=3.0, neutral_plane="XY_Plane")
                                     Angle 1.5 (degrees), NeutralPlane ("Pad", "Face5") or an origin plane,
                                     PullDirection ("Pad", "Edge3") or an origin axis ("Z_Axis"), Reversed
    Thickness("Thickness", ("Pad", ["Face6"]), value=1.0)
                                     Value 1, Reversed (True: inwards), Mode "Skin" | "Pipe" | "RectoVerso",
                                     Join "Arc" | "Intersection", Intersection, Refine

A value may be a number or a PARAMS name or expression, as Pad's length is. Sub-element names are FreeCAD's:
FaceN and EdgeN number the base feature's faces and edges in TopExp::MapShapes order, which is the order
FreeCAD's TopoShape numbers them in (tests/golden/dressup holds ours to freecadcmd's on the same bodies).

FreeCAD keeps those names alive across edits with its topological naming: the Base also stores each element's
history name, so when an earlier edit renumbers the base's edges FreeCAD finds the same edge and writes its
new number back (a Fillet on Edge7 becomes a Fillet on Edge4 after the sketch's lines are reordered). The
part file has only the numbers, so follow() below does the same by geometry after every edit: each named
element of the base before the edit is found again in the base after it (same vertices and same curve or
surface, as Feature::relinkToMatchingSubelements matches when FreeCAD reroutes a feature's base; failing
that, the one element on the same line, circle, plane or cylinder) and the name is rewritten. An element
that cannot be found keeps its old number, which may then name another element (ui/PARITY.md, PartDesign).

The base is the solid before the feature, as FreeCAD's Body makes BaseFeature the previous solid feature;
Base names it. A Base naming another feature is an error, as it is in FreeCAD ("Invalid edge link").
"""
from __future__ import annotations

import math

from . import feature as F
from .feature import FeatureError, value

try:                                     # the kernel; FreeCAD's Python reads the vocabulary without it
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
    from OCP.BRepAlgo import BRepAlgo
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepFilletAPI import BRepFilletAPI_MakeChamfer, BRepFilletAPI_MakeFillet
    from OCP.BRepGProp import BRepGProp
    from OCP.BRepLib import BRepLib
    from OCP.BRepOffset import BRepOffset_Pipe, BRepOffset_RectoVerso, BRepOffset_Skin
    from OCP.BRepOffsetAPI import BRepOffsetAPI_DraftAngle, BRepOffsetAPI_MakeThickSolid
    from OCP.Geom import Geom_Line, Geom_Plane
    from OCP.GeomAbs import (GeomAbs_Arc, GeomAbs_C0, GeomAbs_Circle, GeomAbs_Cone, GeomAbs_Cylinder,
                             GeomAbs_Intersection, GeomAbs_Line, GeomAbs_Plane, GeomAbs_Sphere)
    from OCP.GeomAPI import GeomAPI_IntSS
    from OCP.GProp import GProp_GProps
    from OCP.Message import Message_ProgressRange
    from OCP.ShapeFix import ShapeFix_ShapeTolerance
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SHAPE, TopAbs_SOLID, TopAbs_VERTEX, TopAbs_WIRE
    from OCP.TopExp import TopExp, TopExp_Explorer
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Dir, gp_Lin, gp_Pln, gp_Pnt
    try:
        from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape as _AncestorMap
        from OCP.TopTools import TopTools_ListOfShape
    except ImportError:                  # OCP 8 moved OCCT's collections
        from OCP.collections import (
            IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher as _AncestorMap)
        from OCP.collections import List_TopoDS_Shape as TopTools_ListOfShape
except ImportError:                      # pragma: no cover - only FreeCAD's Python lands here
    pass


CHAMFER_TYPES = ("Equal distance", "Two distances", "Distance and Angle")
THICKNESS_MODES = ("Skin", "Pipe", "RectoVerso")
THICKNESS_JOINS = ("Arc", "Intersection")
ORIGIN_PLANES = ("XY_Plane", "XZ_Plane", "YZ_Plane")
ORIGIN_AXES = {"X_Axis": (1.0, 0.0, 0.0), "Y_Axis": (0.0, 1.0, 0.0), "Z_Axis": (0.0, 0.0, 1.0)}


def _sub_ok(s) -> bool:
    for k in ("Edge", "Face", "Vertex", "Solid", "Wire"):
        if isinstance(s, str) and s.startswith(k) and s[len(k):].isdigit() and int(s[len(k):]) >= 1:
            return True
    return False


def parse_base(base, where):
    """Base as (feature, [subs]): ("Pad", ["Edge1"]), ("Pad", "Edge1"), "Pad", or None (the solid before)."""
    if base is None:
        return None, []
    if isinstance(base, str):
        return base, []
    try:
        obj, subs = base
    except (TypeError, ValueError):
        raise FeatureError(f"{where}: Base {base!r} is not (feature, ['Edge1', 'Face2', ...])") from None
    if isinstance(subs, str):
        subs = [subs]
    subs = [s for s in subs if s != ""]
    if not isinstance(obj, str) or not all(_sub_ok(s) for s in subs):
        raise FeatureError(f"{where}: Base {base!r} is not (feature, ['Edge1', 'Face2', ...])")
    return obj, list(subs)


def _ref(r, where, prop, kinds):
    """A link-sub of Draft: an origin plane or axis name, or (feature, "FaceN"/"EdgeN")."""
    if r is None:
        return None
    if isinstance(r, str):
        if r in ORIGIN_PLANES or r in ORIGIN_AXES:
            return r
        raise FeatureError(f"{where}: {prop} {r!r} is not an origin plane or axis or (feature, 'Face1')")
    try:
        obj, sub = r
    except (TypeError, ValueError):
        raise FeatureError(f"{where}: {prop} {r!r} is not (feature, 'Face1')") from None
    if isinstance(sub, (list, tuple)):
        sub = sub[0] if sub else ""
    if not (isinstance(obj, str) and any(isinstance(sub, str) and sub.startswith(k) and _sub_ok(sub)
                                         for k in kinds)):
        raise FeatureError(f"{where}: {prop} {r!r} is not (feature, '{kinds[0]}1')")
    return (obj, sub)


class _DressUp:
    """PartDesign::DressUp: Base (feature, subs) and Refine (FeatureRefine's, FreeCAD's default True)."""
    kind = ""
    type_id = ""
    POS = ("name", "base")
    # The properties read() gives and the part file's keyword for each (here the same snake_case names).
    PROPS: dict = {}
    REFS = ("base",)

    def __init__(self, name: str, base=None, *, refine: bool = True):
        self.name = name
        self.base_name, self.subs = parse_base(base, name)
        self.refine = bool(refine)

    @property
    def base(self):
        if self.base_name is None:
            return None
        return (self.base_name, list(self.subs))

    def as_dict(self) -> dict:
        d = {"name": self.name, "type": self.type_id, "base": self.base}
        for key in self.PROPS:
            if key == "base":
                continue
            v = getattr(self, key)
            d[key] = list(v) if isinstance(v, tuple) else v
        return d

    def __repr__(self):
        return f"{self.kind}({self.name!r}, {self.base!r})"

    # ── evaluate() calls this: the solid before it (FreeCAD's BaseFeature) to its own ──
    def build_shape(self, solid, shapes, params, prev: str | None):
        where = self.name
        if solid is None:
            raise FeatureError("Base feature's shape is not a solid")
        if self.base_name is not None and self.base_name != prev:
            if self.base_name not in shapes:
                raise FeatureError(f"{where}: Base names {self.base_name!r}, which is not a solid before it")
            raise FeatureError(f"{where}: Invalid edge link: its Base is {self.base_name}, but the feature "
                               f"before it is {prev}")
        if F._count(solid, TopAbs_SOLID) == 0:
            raise FeatureError("Base feature's shape is not a solid")
        return self._make(solid, shapes, params)

    def _make(self, base, shapes, params):
        raise NotImplementedError

    def _refined(self, shape):
        return F._refine(shape) if self.refine else shape

    # ── to_freecad: the same object in a FreeCAD Body ──
    def to_freecad(self, body, made, planes, setv):
        obj = body.newObject(self.type_id, self.name)
        if self.base_name is not None:
            obj.Base = (made[self.base_name], list(self.subs))
        obj.Refine = self.refine
        return obj


# ── the shape's elements, as TopoShape names them ─────────────────────────────────────────────────────

def _sub_shape(shape, name, where):
    """TopoShape::getSubShape("Edge3"): the third edge in TopExp::MapShapes order."""
    for k, t in (("Face", TopAbs_FACE), ("Edge", TopAbs_EDGE), ("Vertex", TopAbs_VERTEX),
                 ("Solid", TopAbs_SOLID), ("Wire", TopAbs_WIRE)):
        if name.startswith(k):
            subs = F._subs(shape, t)
            i = int(name[len(k):])
            if not 1 <= i <= len(subs):
                return None
            return subs[i - 1]
    return None


def _ancestors(shape, sub_type, anc_type):
    m = _AncestorMap()
    TopExp.MapShapesAndAncestors_s(shape, sub_type, anc_type, m)
    return m


def _anc_list(m, s) -> list:
    i = m.FindIndex(s)
    if not i:
        return []
    return list(m.FindFromIndex(i))


def continuous_edges(feat, shape) -> list:
    """DressUp::getContinuousEdges(const TopoShape&): the edges of Base's subs in order, a face's or a solid's
    edges as TopExp_Explorer meets them, each once; an edge without two faces or not C0 between them is left
    out (FreeCAD warns "skip edge ...")."""
    out, seen = [], []
    faces_of = _ancestors(shape, TopAbs_EDGE, TopAbs_FACE)

    def add(e):
        if any(e.IsSame(x) for x in seen):
            return
        seen.append(e)
        faces = _anc_list(faces_of, e)
        if len(faces) != 2:
            return
        cont = BRep_Tool.Continuity_s(TopoDS.Edge(e), TopoDS.Face(faces[0]), TopoDS.Face(faces[-1]))
        if cont != GeomAbs_C0:
            return
        out.append(e)

    for ref in feat.subs:
        sub = _sub_shape(shape, ref, feat.name)
        if sub is None:
            raise FeatureError(f"Invalid edge link: {ref}")
        t = sub.ShapeType()
        if t == TopAbs_EDGE:
            add(sub)
        elif t in (TopAbs_FACE, TopAbs_WIRE, TopAbs_SOLID):
            ex = TopExp_Explorer(sub, TopAbs_EDGE)
            while ex.More():
                add(ex.Current())
                ex.Next()
    return out


def _faces_of_base(feat, shape):
    """DressUp::getFaces: the Base's FaceN subs, in order."""
    out = []
    for ref in feat.subs:
        if not ref.startswith("Face"):
            continue
        f = _sub_shape(shape, ref, feat.name)
        if f is None:
            raise FeatureError("Invalid Invalid face link")
        out.append(f)
    return out


def _limit_tolerance(base, shape):
    """Fillet/Chamfer::execute: a result BRepAlgo::IsValid does not pass gets its tolerance limited."""
    args = TopTools_ListOfShape()
    args.Append(base)
    if not BRepAlgo.IsValid_s(args, shape, False, False):
        ShapeFix_ShapeTolerance().LimitTolerance(shape, F.CONFUSION, F.CONFUSION, TopAbs_SHAPE)


def _all_edges(shape):
    return F._subs(shape, TopAbs_EDGE)


# ── Fillet ────────────────────────────────────────────────────────────────────────────────────────────

class Fillet(_DressUp):
    """PartDesign::Fillet (FeatureFillet.cpp): Radius 1 mm, UseAllEdges False."""
    kind = "Fillet"
    type_id = "PartDesign::Fillet"
    PROPS = {"base": "base", "radius": "radius", "use_all_edges": "use_all_edges", "refine": "refine"}

    def __init__(self, name, base=None, *, radius=1.0, use_all_edges: bool = False, refine: bool = True):
        super().__init__(name, base, refine=refine)
        self.radius, self.use_all_edges = radius, bool(use_all_edges)

    def _make(self, base, shapes, params):
        edges = _all_edges(base) if self.use_all_edges else continuous_edges(self, base)
        if not edges:
            raise FeatureError("Fillet not possible on selected shapes")
        r = value(self.radius, params, f"{self.name}.radius")
        if r <= 0:
            raise FeatureError("Fillet radius must be greater than zero")
        mk = BRepFilletAPI_MakeFillet(base)                      # TopoShape::makeElementFillet
        for e in edges:
            mk.Add(r, r, TopoDS.Edge(e))
        try:
            mk.Build()
            if not mk.IsDone():
                raise RuntimeError
            shape = mk.Shape()
        except Exception:
            raise FeatureError("Fillet operation failed. The selected edges may contain geometry that cannot "
                               "be filleted together. Try filleting edges individually or with a smaller "
                               "radius.") from None
        if shape.IsNull():
            raise FeatureError("Resulting shape is null")
        _limit_tolerance(base, shape)
        return self._refined(shape)

    def to_freecad(self, body, made, planes, setv):
        obj = super().to_freecad(body, made, planes, setv)
        setv(obj, "Radius", self.radius)
        obj.UseAllEdges = self.use_all_edges
        return obj


# ── Chamfer ───────────────────────────────────────────────────────────────────────────────────────────

class Chamfer(_DressUp):
    """PartDesign::Chamfer (FeatureChamfer.cpp): ChamferType Equal distance, Size 1 mm, Size2 1 mm,
    Angle 45 degrees, FlipDirection False, UseAllEdges False."""
    kind = "Chamfer"
    type_id = "PartDesign::Chamfer"
    PROPS = {"base": "base", "chamfer_type": "chamfer_type", "size": "size", "size2": "size2", "angle": "angle",
             "flip_direction": "flip_direction", "use_all_edges": "use_all_edges", "refine": "refine"}

    def __init__(self, name, base=None, *, chamfer_type: str = "Equal distance", size=1.0, size2=1.0,
                 angle=45.0, flip_direction: bool = False, use_all_edges: bool = False, refine: bool = True):
        super().__init__(name, base, refine=refine)
        if chamfer_type not in CHAMFER_TYPES:
            raise FeatureError(f"{name}: chamfer_type {chamfer_type!r} is not one of {', '.join(CHAMFER_TYPES)}")
        self.chamfer_type, self.size, self.size2, self.angle = chamfer_type, size, size2, angle
        self.flip_direction, self.use_all_edges = bool(flip_direction), bool(use_all_edges)

    def _make(self, base, shapes, params):
        edges = _all_edges(base) if self.use_all_edges else continuous_edges(self, base)
        if not edges:
            raise FeatureError("No edges specified")
        t = CHAMFER_TYPES.index(self.chamfer_type)
        size = value(self.size, params, f"{self.name}.size")
        size2 = value(self.size2, params, f"{self.name}.size2")
        angle = value(self.angle, params, f"{self.name}.angle")
        if size <= 0:                                            # validateParameters
            raise FeatureError("Size must be greater than zero")
        if t == 1 and size2 <= 0:
            raise FeatureError("Size2 must be greater than zero")
        if t == 2 and (angle <= 0 or angle >= 180.0):
            raise FeatureError("Angle must be greater than 0 and less than 180")
        if t == 2:
            size2 = angle
        faces_of = _ancestors(base, TopAbs_EDGE, TopAbs_FACE)
        mk = BRepFilletAPI_MakeChamfer(base)                     # TopoShape::makeElementChamfer
        for e in edges:
            edge = TopoDS.Edge(e)
            if BRep_Tool.Degenerated_s(edge):
                raise FeatureError("chamfer edge is degenerated")
            faces = _anc_list(faces_of, e)
            if not faces:
                raise FeatureError("chamfer edge has no adjacent face")
            face = TopoDS.Face(faces[-1] if self.flip_direction else faces[0])
            if t == 0:
                mk.Add(size, size, edge, face)
            elif t == 1:
                mk.Add(size, size2, edge, face)
            else:
                mk.AddDA(size, math.radians(size2), edge, face)
        try:
            mk.Build()
            if not mk.IsDone():
                raise RuntimeError
            shape = mk.Shape()
        except Exception:
            raise FeatureError("Chamfer failed: OCC kernel error in chamfer computation") from None
        if shape.IsNull():
            raise FeatureError("Failed to create chamfer")
        _limit_tolerance(base, shape)
        return self._refined(shape)

    def to_freecad(self, body, made, planes, setv):
        obj = super().to_freecad(body, made, planes, setv)
        obj.ChamferType = self.chamfer_type
        setv(obj, "Size", self.size)
        setv(obj, "Size2", self.size2)
        setv(obj, "Angle", self.angle)
        obj.FlipDirection = self.flip_direction
        obj.UseAllEdges = self.use_all_edges
        return obj


# ── Draft ─────────────────────────────────────────────────────────────────────────────────────────────

class Draft(_DressUp):
    """PartDesign::Draft (FeatureDraft.cpp): Angle 1.5 degrees, NeutralPlane and PullDirection empty (guessed
    from the first face), Reversed False. FreeCAD's Draft has a Refine property but never refines."""
    kind = "Draft"
    type_id = "PartDesign::Draft"
    PROPS = {"base": "base", "angle": "angle", "neutral_plane": "neutral_plane",
             "pull_direction": "pull_direction", "reversed": "reversed", "refine": "refine"}
    REFS = ("base", "neutral_plane", "pull_direction")

    def __init__(self, name, base=None, *, angle=1.5, neutral_plane=None, pull_direction=None,
                 reversed: bool = False, refine: bool = True):
        super().__init__(name, base, refine=refine)
        self.angle, self.reversed = angle, bool(reversed)
        self.neutral_plane = _ref(neutral_plane, name, "neutral_plane", ("Face", "Edge"))
        self.pull_direction = _ref(pull_direction, name, "pull_direction", ("Edge",))
        if isinstance(self.neutral_plane, str) and self.neutral_plane in ORIGIN_AXES:
            raise FeatureError(f"{name}: Neutral plane reference must be face of a feature or a datum plane")
        if isinstance(self.pull_direction, str) and self.pull_direction in ORIGIN_PLANES:
            raise FeatureError(f"{name}: Pull direction reference must be an edge of a feature or a datum line")

    def _ref_shape(self, r, shapes):
        obj, sub = r
        if obj not in shapes or shapes[obj] is None:
            raise FeatureError(f"{self.name}: no feature {obj!r} before it")
        s = _sub_shape(shapes[obj], sub, self.name)
        if s is None:
            raise FeatureError(f"{self.name}: {obj} has no {sub}")
        return s

    def _make(self, base, shapes, params):
        subs = [s for s in self.subs if s.startswith("Face")]
        if not subs:                       # no face: a copy of the previous feature
            return base
        angle = math.radians(value(self.angle, params, f"{self.name}.angle"))
        pull = None
        if self.pull_direction is not None:
            if isinstance(self.pull_direction, str):
                pull = gp_Dir(*ORIGIN_AXES[self.pull_direction])
            else:
                ref = self._ref_shape(self.pull_direction, shapes)
                if ref.ShapeType() != TopAbs_EDGE:
                    raise FeatureError("Pull direction reference must be an edge or a datum line")
                c = BRepAdaptor_Curve(TopoDS.Edge(ref))
                if c.GetType() != GeomAbs_Line:
                    raise FeatureError("Pull direction reference edge must be linear")
                pull = c.Line().Direction()
        if self.neutral_plane is None:
            face = _sub_shape(base, subs[0], self.name)
            if face is None:
                raise FeatureError("Invalid Invalid face link")
            plane = self._guess_plane(face)
        elif isinstance(self.neutral_plane, str):
            n = F.PLANES[self.neutral_plane[:-6]][2]          # Feature::makePlnFromPlane on the origin plane
            plane = gp_Pln(gp_Pnt(0, 0, 0), gp_Dir(*n))
        else:
            ref = self._ref_shape(self.neutral_plane, shapes)
            if ref.ShapeType() == TopAbs_FACE:
                a = BRepAdaptor_Surface(TopoDS.Face(ref))
                if a.GetType() != GeomAbs_Plane:
                    raise FeatureError("Neutral plane reference face must be planar")
                plane = a.Plane()
            elif ref.ShapeType() == TopAbs_EDGE:
                if pull is None:
                    raise FeatureError("Neutral plane reference can only be an edge if pull direction is defined")
                c = BRepAdaptor_Curve(TopoDS.Edge(ref))
                if c.GetType() != GeomAbs_Line:
                    raise FeatureError("Neutral plane reference edge must be linear")
                a = c.Line().Angle(gp_Lin(c.Value(c.FirstParameter()), pull))
                if abs(a - math.pi / 2) > F.CONFUSION:
                    raise FeatureError("Neutral plane reference edge must be normal to pull direction")
                plane = gp_Pln(c.Value(c.FirstParameter()), pull)
            else:
                raise FeatureError("Neutral plane reference must be a face")
        if pull is None:
            pull = plane.Axis().Direction()
        if self.reversed:
            angle = -angle
        faces = _faces_of_base(self, base)
        mk = BRepOffsetAPI_DraftAngle()                           # TopoShape::makeElementDraft, retry on
        while True:
            if not faces:
                raise FeatureError("no faces can be used")
            mk.Init(base)
            done = True
            for i, f in enumerate(faces):
                mk.Add(TopoDS.Face(f), pull, angle, plane)
                if not mk.AddDone():
                    done = False                                  # "Failed to add some face for drafting, skip"
                    del faces[i]
                    break
            if done or not self.reversed:
                break
        try:
            mk.Build(Message_ProgressRange())
            if not mk.IsDone():
                raise RuntimeError
            shape = mk.Shape()
        except Exception:
            raise FeatureError("BRep_API: command not done") from None
        if shape.IsNull():
            raise FeatureError("Resulting shape is null")
        return shape

    @staticmethod
    def _guess_plane(face):
        """Draft::execute without a NeutralPlane: from the first edge of the first face that gives one."""
        for e in F._subs(face, TopAbs_EDGE):
            c = BRepAdaptor_Curve(TopoDS.Edge(e))
            p1, p2 = c.Value(c.FirstParameter()), c.Value(c.LastParameter())
            if c.IsClosed():
                if c.GetType() == GeomAbs_Circle:
                    return gp_Pln(p1, c.Circle().Axis().Direction())
            else:
                pm = c.Value((c.FirstParameter() + c.LastParameter()) / 2.0)
                aux = Geom_Plane(pm, gp_Dir(p2.X() - p1.X(), p2.Y() - p1.Y(), p2.Z() - p1.Z()))
                adapt = BRepAdaptor_Surface(TopoDS.Face(face), False)
                sf = adapt.Surface().Surface()
                inter = GeomAPI_IntSS(aux, sf, F.CONFUSION)
                if not inter.IsDone() or inter.NbLines() < 1:
                    continue
                curve = inter.Line(1)
                if not isinstance(curve, Geom_Line):
                    try:
                        curve = Geom_Line.DownCast(curve) if hasattr(Geom_Line, "DownCast") else None
                    except Exception:
                        curve = None
                    if curve is None:
                        continue
                return gp_Pln(pm, curve.Lin().Direction())
        raise FeatureError("No neutral plane specified and none can be guessed")

    def to_freecad(self, body, made, planes, setv):
        obj = super().to_freecad(body, made, planes, setv)
        setv(obj, "Angle", self.angle)
        obj.Reversed = self.reversed
        axes = {o.Role: o for o in body.Origin.OriginFeatures}
        for prop, r in (("NeutralPlane", self.neutral_plane), ("PullDirection", self.pull_direction)):
            if r is None:
                continue
            if isinstance(r, str):
                setattr(obj, prop, (axes[r], [""]))
            else:
                setattr(obj, prop, (made[r[0]], [r[1]]))
        return obj


# ── Thickness ─────────────────────────────────────────────────────────────────────────────────────────

class Thickness(_DressUp):
    """PartDesign::Thickness (FeatureThickness.cpp): Value 1 mm, Reversed True (inwards), Mode Skin, Join Arc,
    Intersection False."""
    kind = "Thickness"
    type_id = "PartDesign::Thickness"
    PROPS = {"base": "base", "value": "value", "reversed": "reversed", "mode": "mode", "join": "join",
             "intersection": "intersection", "refine": "refine"}

    def __init__(self, name, base=None, *, value=1.0, reversed: bool = True, mode: str = "Skin",
                 join: str = "Arc", intersection: bool = False, refine: bool = True):
        super().__init__(name, base, refine=refine)
        if mode not in THICKNESS_MODES:
            raise FeatureError(f"{name}: mode {mode!r} is not one of {', '.join(THICKNESS_MODES)}")
        if join not in THICKNESS_JOINS:
            raise FeatureError(f"{name}: join {join!r} is not one of {', '.join(THICKNESS_JOINS)}")
        self.value, self.reversed, self.mode, self.join = value, bool(reversed), mode, join
        self.intersection = bool(intersection)

    def _make(self, base, shapes, params):
        if not self.subs:                      # no sub-elements: a copy of the base
            return base
        solids = F._subs(base, TopAbs_SOLID)
        solid_of = _ancestors(base, TopAbs_FACE, TopAbs_SOLID)
        close: dict[int, list] = {}
        for ref in self.subs:
            face = _sub_shape(base, ref, self.name)
            if face is None:
                raise FeatureError("Invalid face reference")
            anc = _anc_list(solid_of, face)
            idx = next((i + 1 for i, s in enumerate(solids) if anc and s.IsSame(anc[0])), 0)
            if not idx:
                continue                       # FreeCAD: "Ignore non-solid face"
            close.setdefault(idx, []).append(face)
        thick = (-1.0 if self.reversed else 1.0) * value(self.value, params, f"{self.name}.value")
        tol = F.CONFUSION
        mode = THICKNESS_MODES.index(self.mode)
        join = GeomAbs_Arc if self.join == "Arc" else GeomAbs_Intersection
        if not solids:
            raise FeatureError("No solid")
        out = []
        if abs(thick) > 2 * tol:
            keys = sorted(close)
            k = 0
            for loop in range(1, len(solids) + 1):
                faces, solid = [], base
                if k < len(keys) and loop >= keys[k]:
                    faces, solid = close[keys[k]], solids[keys[k] - 1]
                try:
                    if mode == 2:
                        res = _recto_verso(solid, faces, thick, tol, self.intersection, join)
                    else:
                        res = _thick_solid(solid, faces, thick, tol, self.intersection,
                                           (BRepOffset_Skin, BRepOffset_Pipe)[mode], join)
                except FeatureError:
                    raise
                except Exception:
                    raise FeatureError("Failed to make thick solid") from None
                out.append(res)
                if k < len(keys):
                    k += 1
        if len(out) > 1:
            result = F._bool("fuse", out[0], out[1:])
        elif not out:
            result = base
        else:
            result = out[0]
        return self._refined(result)

    def to_freecad(self, body, made, planes, setv):
        obj = super().to_freecad(body, made, planes, setv)
        setv(obj, "Value", self.value)
        obj.Reversed = self.reversed
        obj.Mode = self.mode
        obj.Join = self.join
        obj.Intersection = self.intersection
        return obj


def _thick_solid(shape, faces, offset, tol, intersection, mode, join):
    """TopoShape::makeElementThickSolid."""
    if not faces:
        raise FeatureError("Null input shape")
    if abs(offset) <= 2 * tol:
        return shape
    rem = TopTools_ListOfShape()
    for f in faces:
        rem.Append(f)
    mk = BRepOffsetAPI_MakeThickSolid()
    mk.MakeThickSolidByJoin(shape, rem, offset, tol, mode, intersection, False, join)
    mk.Build()
    if not mk.IsDone():
        raise FeatureError("Failed to make thick solid")
    return mk.Shape()


def _valid_wall(wall, message):
    if wall.IsNull() or not BRepCheck_Analyzer(wall).IsValid() or F._count(wall, TopAbs_SOLID) != 1:
        raise FeatureError(message)


def _recto_verso(solid, faces, thickness, tol, intersection, join):
    """FeatureThickness.cpp's makeRectoVersoThickness: two skins of half the thickness, one each way, fused."""
    d = abs(thickness) / 2.0
    if d <= tol:
        raise FeatureError("Recto-verso half-thickness must exceed the modeling tolerance")
    oriented = solid
    if solid.ShapeType() == TopAbs_SOLID:                    # TopoShape::fixSolidOrientation
        s = TopoDS.Solid(solid)
        BRepLib.OrientClosedSolid_s(s)
        oriented = s
    recto = _thick_solid(oriented, faces, d, tol, intersection, BRepOffset_Skin, join)
    verso = _thick_solid(oriented, faces, -d, tol, intersection, BRepOffset_Skin, join)
    _valid_wall(recto, "Recto-verso positive-side wall is invalid")
    _valid_wall(verso, "Recto-verso negative-side wall is invalid")
    args, tools = TopTools_ListOfShape(), TopTools_ListOfShape()
    args.Append(recto)
    tools.Append(verso)
    mk = BRepAlgoAPI_Fuse()
    mk.SetRunParallel(True)
    mk.SetArguments(args)
    mk.SetTools(tools)
    mk.SetFuzzyValue(tol)
    mk.Build()
    result = mk.Shape() if mk.IsDone() else None
    if result is None or result.IsNull() or not BRepCheck_Analyzer(result).IsValid() \
            or F._count(result, TopAbs_SOLID) != 1:
        raise FeatureError("Recto-verso thickness produced an invalid solid")
    return result


DRESSUPS = {c.kind: c for c in (Fillet, Chamfer, Draft, Thickness)}


# ── following renumbered elements (FreeCAD's topological naming, by geometry) ─────────────────────────

def _vertices(s):
    return [BRep_Tool.Pnt_s(TopoDS.Vertex(v)) for v in F._subs(s, TopAbs_VERTEX)]


def _same_points(a, b, tol):
    if len(a) != len(b):
        return False
    left = list(b)
    for p in a:
        j = next((j for j, q in enumerate(left) if p.Distance(q) <= tol), None)
        if j is None:
            return False
        left.pop(j)
    return True


def _centre(s):
    props = GProp_GProps()
    if s.ShapeType() == TopAbs_FACE:
        BRepGProp.SurfaceProperties_s(s, props)
    else:
        BRepGProp.LinearProperties_s(s, props)
    return props.CentreOfMass(), props.Mass()


def _carrier(s):
    """The infinite line, circle, plane, cylinder ... an edge or face lies on, as a comparable tuple."""
    def r(x):
        return round(x, 6) + 0.0

    def axis(p, d):          # a line as its point nearest the origin and its direction up to sign
        dx, dy, dz = d.X(), d.Y(), d.Z()
        if (dx, dy, dz) < (0, 0, 0) and not (abs(dx) < 1e-9 and abs(dy) < 1e-9 and dz > 0):
            pass
        sgn = -1.0 if (dx < -1e-9 or (abs(dx) <= 1e-9 and (dy < -1e-9 or (abs(dy) <= 1e-9 and dz < 0)))) else 1.0
        dx, dy, dz = sgn * dx, sgn * dy, sgn * dz
        t = p.X() * dx + p.Y() * dy + p.Z() * dz
        q = (p.X() - t * dx, p.Y() - t * dy, p.Z() - t * dz)
        return tuple(map(r, q)) + tuple(map(r, (dx, dy, dz)))

    if s.ShapeType() == TopAbs_EDGE:
        c = BRepAdaptor_Curve(TopoDS.Edge(s))
        t = c.GetType()
        if t == GeomAbs_Line:
            ln = c.Line()
            return ("line",) + axis(ln.Location(), ln.Direction())
        if t == GeomAbs_Circle:
            ci = c.Circle()
            return ("circle", r(ci.Radius())) + axis(ci.Location(), ci.Axis().Direction())
        return None
    a = BRepAdaptor_Surface(TopoDS.Face(s))
    t = a.GetType()
    if t == GeomAbs_Plane:
        pl = a.Plane()
        n = pl.Axis().Direction()
        if s.Orientation() == 1:                         # TopAbs_REVERSED: the face's normal is the other way
            n = n.Reversed()
        p = pl.Location()
        return ("plane", r(n.X()), r(n.Y()), r(n.Z()), r(p.X() * n.X() + p.Y() * n.Y() + p.Z() * n.Z()))
    if t == GeomAbs_Cylinder:
        cy = a.Cylinder()
        return ("cylinder", r(cy.Radius())) + axis(cy.Location(), cy.Axis().Direction())
    if t == GeomAbs_Cone:
        co = a.Cone()
        return ("cone", r(co.SemiAngle()), r(co.Apex().X()), r(co.Apex().Y()), r(co.Apex().Z()))
    if t == GeomAbs_Sphere:
        sp = a.Sphere()
        return ("sphere", r(sp.Radius()), r(sp.Location().X()), r(sp.Location().Y()), r(sp.Location().Z()))
    return None


def match(old_shape, name: str, new_shape, tol: float = 1e-6) -> str | None:
    """The name, in new_shape, of the element old_shape calls name: the one with the same vertices and the
    same centre (Feature::relinkToMatchingSubelements' findSubShapesWithSharedVertex with CheckGeometry), else
    the one on the same carrier line, circle, plane or cylinder. None when there is no single one."""
    old = _sub_shape(old_shape, name, "")
    if old is None:
        return None
    kind = "Face" if name.startswith("Face") else "Edge" if name.startswith("Edge") else \
        "Vertex" if name.startswith("Vertex") else None
    if kind is None:
        return None
    t = {"Face": TopAbs_FACE, "Edge": TopAbs_EDGE, "Vertex": TopAbs_VERTEX}[kind]
    cands = F._subs(new_shape, t)
    if kind == "Vertex":
        p = BRep_Tool.Pnt_s(TopoDS.Vertex(old))
        hits = [i for i, v in enumerate(cands) if BRep_Tool.Pnt_s(TopoDS.Vertex(v)).Distance(p) <= tol]
        return f"Vertex{hits[0] + 1}" if len(hits) == 1 else None
    ov, (oc, om) = _vertices(old), _centre(old)
    exact = []
    for i, c in enumerate(cands):
        cc, cm = _centre(c)
        if abs(cm - om) <= tol * max(1.0, om) and cc.Distance(oc) <= tol * 10 and _same_points(ov, _vertices(c), tol):
            exact.append(i)
    if len(exact) == 1:
        return f"{kind}{exact[0] + 1}"
    if exact:
        return None
    key = _carrier(old)
    if key is None:
        return None
    same = [i for i, c in enumerate(cands) if _carrier(c) == key]
    if len(same) == 1:
        return f"{kind}{same[0] + 1}"
    return None


def _solid_before(features, name):
    """The name of the last solid feature before name in a list (FreeCAD's BaseFeature), or None."""
    prev = None
    for g in features:
        if getattr(g, "name", None) == name:
            return prev
        if not isinstance(g, F.Sketch):
            prev = g.name
    return prev


def _with_base(f, base_name, subs):
    g = type(f).__new__(type(f))
    g.__dict__.update(f.__dict__)
    g.base_name, g.subs = base_name, list(subs)
    return g


def follow(features_before, features_after, params_before=None, params_after=None, base_before=None,
           base_after=None) -> dict:
    """{dress-up name: its new Base (feature, subs)} after an edit took features_before to features_after.
    For each dress-up whose base solid changed, every sub-element name is found again in the new base
    (match()); a Base naming a feature that is no longer the solid before it is pointed at the one that is
    (FreeCAD's onBaseFeatureRerouted). Dress-ups that need nothing are left out; an element that cannot be
    found keeps its name. Nothing is followed past a feature that does not build."""
    try:
        old = F.evaluate(features_before, params_before, base_before)
    except Exception:
        return {}
    before = {getattr(f, "name", None): f for f in features_before}
    params = dict(params_after or {})
    solid = getattr(base_after, "wrapped", base_after) if base_after is not None else None
    prev = "BaseFeature" if solid is not None else None
    shapes = {"BaseFeature": solid} if solid is not None else {}
    sketches, out = {}, {}
    for f in features_after:
        name = getattr(f, "name", None)
        if isinstance(f, F.Sketch):
            try:
                sketches[name] = f.solved(params)
            except Exception:
                return out
            continue
        if isinstance(f, _DressUp) and f.base_name is not None and solid is not None:
            subs = list(f.subs)
            b = before.get(name)
            if isinstance(b, _DressUp) and b.base_name is not None:
                old_base = old.get(b.base_name) if b.base_name == _solid_before(features_before, name) else None
                if old_base is not None and subs and not _same_elements(old_base, solid):
                    subs = [match(old_base, s, solid) or s for s in subs]
            if subs != list(f.subs) or f.base_name != prev:
                out[name] = (prev, subs)
                f = _with_base(f, prev, subs)
        try:
            if hasattr(f, "build_shape"):
                solid = f.build_shape(solid, shapes, params, prev)
            elif hasattr(f, "profile") and f.profile in sketches:
                solid = F._extrude(f, sketches[f.profile], solid, shapes, params)
            else:
                return out
        except Exception:
            return out
        shapes[name] = solid
        prev = name
    return out


def _signature(shape):
    out = []
    for t in (TopAbs_FACE, TopAbs_EDGE):
        for s in F._subs(shape, t):
            c, m = _centre(s)
            out.append((t, round(m, 6), round(c.X(), 6), round(c.Y(), 6), round(c.Z(), 6)))
    return out


def _same_elements(a, b) -> bool:
    """Whether two solids number the same faces and edges alike (so no name needs following)."""
    return _signature(a) == _signature(b)

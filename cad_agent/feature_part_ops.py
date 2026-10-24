# SPDX-License-Identifier: LGPL-2.1-or-later
# A port of FreeCAD's Part features (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), each file
# LGPL-2.1-or-later as it states:
#   src/Mod/Part/App/FeatureExtrusion.cpp: Copyright (c) 2008 Werner Mayer
#   src/Mod/Part/App/FeatureRevolution.cpp: Copyright (c) 2008 Werner Mayer
#   src/Mod/Part/App/FeatureMirroring.cpp: Copyright (c) 2009 Werner Mayer
#   src/Mod/Part/App/FeatureFillet.cpp, FeatureChamfer.cpp: Copyright (c) 2008 Werner Mayer
#   src/Mod/Part/App/FeatureCompound.cpp: Copyright (c) 2008 Werner Mayer
#   src/Mod/Part/App/PartFeatures.cpp (Refine): Copyright (c) 2009 Werner Mayer
#   src/Mod/Part/App/TopoShapeExpansion.cpp (makeElementPrism, makeElementRevolve, makeElementMirror):
#   Copyright (c) 2022 Zheng, Lei; 2023 Ondsel
"""Part's operations on other objects: Extrusion (Part_Extrude), Revolution (Part_Revolve), Mirroring (Part_Mirror),
Fillet, Chamfer, Compound and Refine (Part_RefineShape).

    Part.Extrusion("Extrude", "Sketch", dir_mode="Normal", length_fwd=10, solid=True)
    Part.Revolution("Revolve", "Sketch", axis=(0, 1, 0), angle=180, solid=True)
    Part.Mirroring("Mirror", "Box", normal=(1, 0, 0), label="Box (Mirror #1)")
    Part.Fillet("Fillet", "Box", edges=[(1, 2.0, 2.0), (3, 2.0, 2.0)])
    Part.Chamfer("Chamfer", "Box", edges=[(1, 1.0, 1.0)])
    Part.Compound("Compound", ["Box", "Sphere"])
    Part.Refine("Refine", "Fusion")

Property names and defaults are FreeCAD's: an Extrusion's base, dir (0, 0, 1), dir_mode "Custom" ("Edge", "Normal"),
dir_link, length_fwd and length_rev 0 (both 0: Dir's length), solid, reversed, symmetric False, taper_angle and
taper_angle_rev 0, face_maker_mode "Unified" (a new Extrude's; FaceMakerClass follows it), inner_wire_taper
"Inverted"; a Revolution's source, base (0, 0, 0), axis (0, 0, 1), axis_link, angle 360, symmetric and solid False,
face_maker_class "Part::FaceMakerUnified"; a Mirroring's source, base (0, 0, 0), normal (0, 0, 1), mirror_plane; a
Fillet's or Chamfer's base and edges, FreeCAD's Edges: (edge number, radius1 or size1, radius2 or size2) each; a
Compound's links; a Refine's source.
"""
from __future__ import annotations

import math

from . import feature as F
from .feature_part import PartObject, compound, register, sub_shape
from .feature_part_bool import _children
from .feature_part_face import MAKERS, make_face

try:
    from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy, BRepBuilderAPI_Transform
    from OCP.BRepFilletAPI import BRepFilletAPI_MakeChamfer, BRepFilletAPI_MakeFillet
    from OCP.BRepLib import BRepLib_FindSurface
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism, BRepPrimAPI_MakeRevol
    from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Line, GeomAbs_Plane
    from OCP.GeomAdaptor import GeomAdaptor_Surface
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED, TopAbs_VERTEX, TopAbs_WIRE
    from OCP.TopExp import TopExp, TopExp_Explorer
    from OCP.TopoDS import TopoDS
    from OCP.BRep import BRep_Tool
    from OCP.gp import gp_Ax1, gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
except ImportError:                     # pragma: no cover - only FreeCAD's Python lands here
    pass

CONFUSION = 1e-7
ANGULAR = 1e-12
DIR_MODES = ("Custom", "Edge", "Normal")
FACE_MAKERS = ("Simple", "Cheese", "Extrusion", "Bullseye", "Unified")
INNER_TAPER = ("Inverted", "SameAsOuter")


def _vec(v, where):
    try:
        x, y, z = (float(c) for c in v)
    except (TypeError, ValueError):
        raise F.FeatureError(f"{where}: {v!r} is not (x, y, z)") from None
    return (x, y, z)


def _copy(shape):
    return BRepBuilderAPI_Copy(shape).Shape()


def _has(shape, kind):
    ex = TopExp_Explorer(shape, kind)
    return ex.More()


def _moved(shape, vec):
    t = gp_Trsf()
    t.SetTranslation(vec)
    from .feature_transform import transformed
    return transformed(shape, t)


def _line_link(ctx, link, where):
    """Extrusion::fetchAxisLink: the start point and the vector of a straight edge."""
    e = ctx.shape(link, where)
    if e.ShapeType() != TopAbs_EDGE:
        raise F.FeatureError("DirLink shape is not an edge")
    crv = BRepAdaptor_Curve(TopoDS.Edge(e))
    if crv.GetType() != GeomAbs_Line:
        raise F.FeatureError("DirLink edge is not a line.")
    a, b = crv.Value(crv.FirstParameter()), crv.Value(crv.LastParameter())
    if e.Orientation() == TopAbs_REVERSED:
        a, b = b, a
    return (a.X(), a.Y(), a.Z()), (b.X() - a.X(), b.Y() - a.Y(), b.Z() - a.Z())


class Extrusion(PartObject):
    """Part::Extrusion (Part_Extrude): its base pushed along a direction, a solid from closed wires when solid."""
    kind, TYPE_ID, TRANSACTION = "Part.Extrusion", "Part::Extrusion", "Extrude"
    POS = ("base",)
    REFS = ("base", "dir_link")
    INPUTS = ("base",)
    DEFAULTS = {"base": None, "dir": (0.0, 0.0, 1.0), "dir_mode": "Custom", "dir_link": None, "length_fwd": 0.0,
                "length_rev": 0.0, "solid": False, "reversed": False, "symmetric": False, "taper_angle": 0.0,
                "taper_angle_rev": 0.0, "face_maker_mode": "Unified", "inner_wire_taper": "Inverted",
                **PartObject.COMMON}
    ENUMS = {"dir_mode": DIR_MODES, "face_maker_mode": FACE_MAKERS, "inner_wire_taper": INNER_TAPER}

    def normalize(self, key, v):
        if key == "dir":
            return _vec(v, f"{self.name}.dir")
        return super().normalize(key, v)

    def direction(self, ctx, params):
        """Extrusion::computeFinalParameters' direction, before Reversed."""
        if self.dir_mode == "Custom":
            return self.dir
        if self.dir_mode == "Edge":
            if self.dir_link is None:
                raise F.FeatureError("DirMode is set to use edge, but no edge is linked.")
            return _line_link(ctx, self.dir_link, f"{self.name}.DirLink")[1]
        return shape_normal(ctx, self.base)

    def shape(self, ctx, params):
        if self.base is None:
            raise F.FeatureError("No object linked")
        d = self.direction(ctx, params)
        n = math.sqrt(sum(c * c for c in d))
        if n < CONFUSION:
            raise F.FeatureError("Direction is zero-length")
        u = gp_Dir(*d)
        if self.reversed:
            u.Reverse()
        fwd, rev = F.value(self.length_fwd, params, "LengthFwd"), F.value(self.length_rev, params, "LengthRev")
        if abs(fwd) < CONFUSION and abs(rev) < CONFUSION:
            fwd = n
        if self.symmetric:
            fwd, rev = fwd * 0.5, fwd * 0.5
        if abs(fwd + rev) < CONFUSION:
            raise F.FeatureError("Total length of extrusion is zero.")
        t1 = math.radians(F.value(self.taper_angle, params, "TaperAngle"))
        t2 = math.radians(F.value(self.taper_angle_rev, params, "TaperAngleRev"))
        for t in (t1, t2):
            if abs(t) > math.pi * 0.5 - ANGULAR:
                raise F.FeatureError("Magnitude of taper angle matches or exceeds 90 degrees. That is too much.")
        source = ctx.shape(self.base, f"{self.name}.Base")
        maker = "Part::FaceMaker" + self.face_maker_mode
        if abs(t1) >= ANGULAR or abs(t2) >= ANGULAR:
            from .feature_part_taper import tapered
            return tapered(source, u, fwd, rev, t1, t2, self.solid, maker, self.inner_wire_taper)
        return extrude(source, u, fwd, rev, self.solid, maker)


def extrude(source, u, fwd, rev, solid, maker):
    """Extrusion::extrudeShape, untapered."""
    vec = gp_Vec(u).Multiplied(fwd + rev)
    if source is None or source.IsNull():
        raise F.FeatureError("Cannot extrude empty shape")
    shape = _copy(source)
    if abs(rev) > CONFUSION:
        shape = _moved(shape, gp_Vec(u).Multiplied(-rev))
    if solid and not _has(shape, TopAbs_FACE):
        shape = make_face(shape, maker)
        if shape is None:
            raise F.FeatureError("Null shape")
    return BRepPrimAPI_MakePrism(shape, vec).Shape()


def shape_normal(ctx, link):
    """Extrusion::calculateShapeNormal: a sketch's own Z; else the plane of the shape, oriented by its first face."""
    name = link if isinstance(link, str) else link[0]
    obj = ctx.obj(name)
    sk = None
    if isinstance(obj, F.Sketch):
        sk = obj
    elif ctx.body is not None and name in ctx.body.get("_sketches", {}):
        sk = ctx.body["_sketches"][name]
    if sk is not None:
        _, r = sk.placement()
        return (r[0][2], r[1][2], r[2][2])
    sh = ctx.shape(link, "Base")
    finder = BRepLib_FindSurface(sh, -1, True)
    if not finder.Found():
        raise F.FeatureError("Can't find normal direction, because the shape is not on a plane.")
    normal = GeomAdaptor_Surface(finder.Surface()).Plane().Axis().Direction()
    ex = TopExp_Explorer(sh, TopAbs_FACE)
    if ex.More():
        normal = BRepAdaptor_Surface(TopoDS.Face(ex.Current())).Plane().Axis().Direction()
        if ex.Current().Orientation() == TopAbs_REVERSED:
            normal.Reverse()
    return (normal.X(), normal.Y(), normal.Z())


class Revolution(PartObject):
    """Part::Revolution (Part_Revolve): its source turned about an axis."""
    kind, TYPE_ID, TRANSACTION = "Part.Revolution", "Part::Revolution", "Revolve"
    POS = ("source",)
    REFS = ("source", "axis_link")
    INPUTS = ("source",)
    DEFAULTS = {"source": None, "base": (0.0, 0.0, 0.0), "axis": (0.0, 0.0, 1.0), "axis_link": None, "angle": 360.0,
                "symmetric": False, "solid": False, "face_maker_class": "Part::FaceMakerUnified",
                **PartObject.COMMON}
    RANGES = {"angle": (0.0, 360.0)}
    ENUMS = {"face_maker_class": MAKERS + ("",)}

    def normalize(self, key, v):
        if key in ("base", "axis"):
            return _vec(v, f"{self.name}.{key}")
        return super().normalize(key, v)

    def shape(self, ctx, params):
        if self.source is None:
            raise F.FeatureError("No object linked")
        b, v, angle_edge = self.base, self.axis, 0.0
        if self.axis_link is not None:
            b, v, angle_edge = axis_link(ctx, self.axis_link)
        ax = gp_Ax1(gp_Pnt(*b), gp_Dir(*v))
        angle = math.radians(self.v("angle", params))
        if abs(angle) < ANGULAR:
            angle = angle_edge
        shape = ctx.shape(self.source, f"{self.name}.Source")
        if shape is None or shape.IsNull():
            raise F.FeatureError("Cannot revolve null shape")
        if shape.Infinite():
            raise F.FeatureError("Cannot revolve infinite shape")
        if self.symmetric:
            t = gp_Trsf()
            t.SetRotation(ax, angle * -0.5)
            from OCP.TopLoc import TopLoc_Location
            shape = shape.Moved(TopLoc_Location(t))
        maker = self.face_maker_class if self.solid else None
        if maker and not _has(shape, TopAbs_FACE):
            if not _has(shape, TopAbs_WIRE):
                shape = compound(F._wires([e for e in F._subs(shape, TopAbs_EDGE)]))
            shape = make_face(shape, maker)
            if shape is None:
                raise F.FeatureError("Null shape")
        res = BRepPrimAPI_MakeRevol(shape, ax, angle).Shape()
        if res is None or res.IsNull():
            raise F.FeatureError("Resulting shape is null")
        return res


def axis_link(ctx, link):
    """Revolution::fetchAxisLink: a line's end point (its start when reversed) and direction, or an arc's axis and
    its angle."""
    e = ctx.shape(link, "AxisLink")
    if e.ShapeType() != TopAbs_EDGE:
        raise F.FeatureError("AxisLink shape is not an edge")
    crv = BRepAdaptor_Curve(TopoDS.Edge(e))
    rev = e.Orientation() == TopAbs_REVERSED
    angle = 0.0
    if crv.GetType() == GeomAbs_Line:
        base = crv.Value(crv.FirstParameter() if rev else crv.LastParameter())
        d = crv.Line().Direction()
    elif crv.GetType() == GeomAbs_Circle:
        base = crv.Circle().Axis().Location()
        d = crv.Circle().Axis().Direction()
        angle = crv.LastParameter() - crv.FirstParameter()
    else:
        raise F.FeatureError("AxisLink edge is neither line nor arc of circle.")
    if rev:
        d.Reverse()
    return (base.X(), base.Y(), base.Z()), (d.X(), d.Y(), d.Z()), angle


class Mirroring(PartObject):
    """Part::Mirroring (Part_Mirror): its source mirrored in a plane, Base and Normal or a MirrorPlane reference."""
    kind, TYPE_ID, TRANSACTION = "Part.Mirroring", "Part::Mirroring", "Mirroring"
    POS = ("source",)
    REFS = ("source", "mirror_plane")
    INPUTS = ("source",)
    DEFAULTS = {"source": None, "base": (0.0, 0.0, 0.0), "normal": (0.0, 0.0, 1.0), "mirror_plane": None,
                **PartObject.COMMON}

    def normalize(self, key, v):
        if key in ("base", "normal"):
            return _vec(v, f"{self.name}.{key}")
        return super().normalize(key, v)

    def plane(self, ctx):
        if self.mirror_plane is None:
            return self.base, self.normal
        name, sub = (self.mirror_plane, "") if isinstance(self.mirror_plane, str) else self.mirror_plane
        obj = ctx.obj(name)
        from .feature_part_prim import Plane
        if isinstance(obj, Plane):                  # a Part::Plane: its Placement's origin and Z
            pos, ypr = obj.placement or ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
            r = F._ypr(*ypr)
            return pos, (r[0][2], r[1][2], r[2][2])
        if name in ("XY_Plane", "XZ_Plane", "YZ_Plane") and obj is None:
            from .feature_transform import ORIGIN_DIRS
            return (0.0, 0.0, 0.0), ORIGIN_DIRS[name]
        label = ctx.label(name)
        shape = ctx.shape(self.mirror_plane, f"{self.name}.MirrorPlane")
        is_face, is_edge = sub.startswith("Face"), sub.startswith("Edge")
        face = edge = None
        if is_face:
            face = TopoDS.Face(shape)
        elif F._count(shape, TopAbs_FACE) == 1:
            face, is_face = TopoDS.Face(sub_shape(shape, "Face1")), True
        if not is_face and is_edge:
            edge = TopoDS.Edge(shape)
        elif F._count(shape, TopAbs_EDGE) == 1:
            edge, is_edge = TopoDS.Edge(sub_shape(shape, "Edge1")), True
        if not is_face and not is_edge:
            raise F.FeatureError(f"{label}: Failed to extract mirror plane, unable to determine which face or edge "
                                 "to use.")
        if is_face:
            ad = BRepAdaptor_Surface(face)
            if ad.GetType() != GeomAbs_Plane:
                raise F.FeatureError(f"{label}: Mirror plane face must be planar")
            ex = TopExp_Explorer(face, TopAbs_VERTEX)
            p = BRep_Tool.Pnt_s(TopoDS.Vertex(ex.Current())) if ex.More() else gp_Pnt()
            d = ad.Plane().Axis().Direction()
        else:
            c = BRepAdaptor_Curve(edge)
            if c.GetType() != GeomAbs_Circle:
                raise F.FeatureError(f"{label}: Only circle edge types are supported")
            d, p = c.Circle().Axis().Direction(), c.Circle().Location()
        return (p.X(), p.Y(), p.Z()), (d.X(), d.Y(), d.Z())

    def shape(self, ctx, params):
        if self.source is None:
            raise F.FeatureError("No object linked")
        base, normal = self.plane(ctx)
        shape = ctx.shape(self.source, f"{self.name}.Source")
        if shape is None or shape.IsNull():
            raise F.FeatureError("Cannot mirror empty shape")
        t = gp_Trsf()
        t.SetMirror(gp_Ax2(gp_Pnt(*base), gp_Dir(*normal)))
        return BRepBuilderAPI_Transform(shape, t).Shape()


class _FilletBase(PartObject):
    """Part::FilletBase: Base and Edges, FreeCAD's PropertyFilletEdges as (edge number, r1, r2)."""
    POS = ("base",)
    REFS = ("base",)
    INPUTS = ("base",)
    DEFAULTS = {"base": None, "edges": (), **PartObject.COMMON}

    def normalize(self, key, v):
        if key == "edges":
            out = []
            for e in v or ():
                try:
                    i, r1, r2 = e
                    if isinstance(i, bool) or not isinstance(i, int) or i < 1:
                        raise ValueError
                    out.append((i, r1, r2))
                except (TypeError, ValueError):
                    raise F.FeatureError(f"{self.name}: edges holds {e!r}, not (edge number, radius1, radius2)") \
                        from None
            return tuple(out)
        return super().normalize(key, v)

    def source_value(self, key, v=None):
        if key == "edges":
            return [tuple(e) for e in (getattr(self, key) if v is None else v)]
        return super().source_value(key, v)

    def elements(self, ctx, params):
        if self.base is None:
            raise F.FeatureError("No object linked")
        base = ctx.shape(self.base, f"{self.name}.Base")
        edges = F._subs(base, TopAbs_EDGE)
        out = []
        for i, r1, r2 in self.edges:
            if i > len(edges):
                raise F.FeatureError(f"Missing edge link: Edge{i}\n")
            out.append((TopoDS.Edge(edges[i - 1]), F.value(r1, params, "radius1"), F.value(r2, params, "radius2")))
        return base, out

    def to_freecad(self, fc):
        obj = fc.doc.addObject(self.TYPE_ID, self.name)
        obj.Base = fc.link(self.base)
        obj.Edges = [(i, F.value(r1, fc.params, "r1"), F.value(r2, fc.params, "r2")) for i, r1, r2 in self.edges]
        if self.label:
            obj.Label = self.label
        return obj


class Fillet(_FilletBase):
    """Part::Fillet (Part_Fillet): BRepFilletAPI_MakeFillet over the chosen edges."""
    kind, TYPE_ID, TRANSACTION = "Part.Fillet", "Part::Fillet", "Fillet"

    def shape(self, ctx, params):
        base, els = self.elements(ctx, params)
        mk = BRepFilletAPI_MakeFillet(base)
        for e, r1, r2 in els:
            mk.Add(r1, r2, e)
        try:
            res = mk.Shape()
        except Exception:  # noqa: BLE001 - StdFail_NotDone, as FreeCAD's catch reports it
            raise F.FeatureError("BRep_API: command not done") from None
        if res.IsNull():
            raise F.FeatureError("Resulting shape is null")
        return res


class Chamfer(_FilletBase):
    """Part::Chamfer (Part_Chamfer): BRepFilletAPI_MakeChamfer, each edge on the first face that has it."""
    kind, TYPE_ID, TRANSACTION = "Part.Chamfer", "Part::Chamfer", "Chamfer"

    def shape(self, ctx, params):
        base, els = self.elements(ctx, params)
        from .feature_dressup import _AncestorMap
        anc = _AncestorMap()
        TopExp.MapShapesAndAncestors_s(base, TopAbs_EDGE, TopAbs_FACE, anc)
        mk = BRepFilletAPI_MakeChamfer(base)
        for e, r1, r2 in els:
            mk.Add(r1, r2, e, TopoDS.Face(anc.FindFromKey(e).First()))
        try:
            res = mk.Shape()
        except Exception:  # noqa: BLE001
            raise F.FeatureError("BRep_API: command not done") from None
        if res.IsNull():
            raise F.FeatureError("Resulting shape is null")
        return res


class Compound(PartObject):
    """Part::Compound (Part_Compound): its links' shapes in one compound, each object once."""
    kind, TYPE_ID, TRANSACTION = "Part.Compound", "Part::Compound", "Compound"
    POS = ("links",)
    REFS = ("links",)
    INPUTS = ("links",)
    DEFAULTS = {"links": (), **PartObject.COMMON}

    def shape(self, ctx, params):
        seen, shapes = set(), []
        for r in self.links:
            if r in seen:
                continue
            seen.add(r)
            s = ctx.shape(r, f"{self.name}.Links")
            if s is not None and not s.IsNull():
                shapes.append(s)
        return compound(shapes)


class Refine(PartObject):
    """Part::Refine (Part_RefineShape, its parametric form): the source's faces merged where they are one surface."""
    kind, TYPE_ID, TRANSACTION = "Part.Refine", "Part::Refine", "Refine shape"
    POS = ("source",)
    REFS = ("source",)
    INPUTS = ()                     # no claimChildren: the tree shows its source beside it, hidden (Part_RefineShape)
    HIDES = ("source",)
    DEFAULTS = {"source": None, **PartObject.COMMON}

    def shape(self, ctx, params):
        if self.source is None:
            raise F.FeatureError("No part object linked.")
        s = ctx.shape(self.source, f"{self.name}.Source")
        from .feature_part_bool import refine
        return refine(s)


OPS = (Extrusion, Revolution, Mirroring, Fillet, Chamfer, Compound, Refine)
register(*OPS)
_ = (_children,)

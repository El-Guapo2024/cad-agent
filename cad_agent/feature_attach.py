"""Attachment in a PartDesign Body: sketches on faces and datums, datum features, and a sketch's external geometry.

FreeCAD attaches a sketch, a datum plane, line or point and a local coordinate system the same way: by
AttachExtension's properties, which the part file writes in snake_case (cad_agent/feature.py's vocabulary):

    Sketch("Sketch001", attachment_support=[("Pad", "Face6")], map_mode="FlatFace",
           attachment_offset=((0, 0, 0), (0, 0, 0)), map_reversed=False, map_path_parameter=0.0,
           external_geometry=[("Pad", "Edge3")], geometry=[...], constraints=[...])
    DatumPlane("DatumPlane", attachment_support=[("XY_Plane", "")], map_mode="FlatFace",
               attachment_offset=((0, 0, 12), (0, 0, 0)))
    DatumLine("DatumLine", attachment_support=[("Pad", "Vertex1"), ("Pad", "Vertex7")], map_mode="TwoPointLine")
    DatumPoint("DatumPoint", attachment_support=[("Pad", "Edge2")], map_mode="OnEdge", map_path_parameter=0.25)
    LocalCoordinateSystem("LCS", attachment_support=[("Pad", "Vertex3"), ("Pad", "Edge1")], map_mode="OXY")
    DatumPlane("DatumPlane001", placement=((0, 0, 30), (0, 45, 0)))     # MapMode Deactivated: placed by hand

attachment_support is AttachmentSupport: a list of (object, element) pairs, the object a feature before it (a
Pad's solid, a sketch, a datum), the Body's origin ("XY_Plane", "XZ_Plane", "YZ_Plane", "X_Axis", "Y_Axis",
"Z_Axis", "Origin") or "BaseFeature"; the element "Face6", "Edge3", "Vertex1" in FreeCAD's numbering, or "" for
the object itself. map_mode is MapMode, one of cad_agent.attacher.modes() for the object's engine (a sketch and a
datum plane: "Plane"; a datum line: "Line"; a datum point: "Point"; a coordinate system: "3D"); without it, a
support takes the mode FreeCAD's Create datum command suggests (bestFitMode), a sketch FlatFace. attachment_offset
is AttachmentOffset, map_reversed MapReversed (the Attachment panel's Flip sides), map_path_parameter
MapPathParameter; placement is the Placement an unattached object keeps. The old sketch form, support="XY", is
attachment_support=[("XY_Plane", "")] with FlatFace.

Context is the Body as evaluate() builds it, what a reference resolves against: each object's shape and
Placement as FreeCAD has them (a solid feature's Placement is ProfileBased::positionByPrevious's, which a
FlatFace sketch on its face orients by). attach() and project() are the two things features call:
Context.attach(f, engine) gives f's Placement from its attachment (cad_agent.attacher.attach), and
project(placement, shape) is SketchObject::rebuildExternalGeometry's projection of an edge, vertex or planar
face onto a sketch's plane, in the sketch's own coordinates, as cad_agent.planegcs takes geometry.
"""
from __future__ import annotations

import math
import re

try:                                    # the kernel; FreeCAD's Python reads the vocabulary without it
    from OCP.BRep import BRep_Builder, BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeVertex
    from OCP.Geom import Geom_Line, Geom_Plane
    from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Ellipse, GeomAbs_Line, GeomAbs_Plane
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS, TopoDS_Compound
    from OCP.gp import gp_Ax3, gp_Dir, gp_Lin, gp_Pln, gp_Pnt, gp_Vec
except ImportError:                     # pragma: no cover - only FreeCAD's Python lands here
    pass

from . import attacher as A
from .feature import FeatureError, _subs

ELEMENT = re.compile(r"^(Face|Edge|Vertex)([1-9][0-9]*)$")

# The Body's origin features, as App::Origin makes them (their Placement, measured in FreeCAD 26.3: the golden's
# tests/golden/attach/engine.json "origin"): App::Line along its local X, App::Plane its local XY, App::Point.
ORIGIN = {
    "X_Axis": ("App::Line", (0.0, 0.0, 0.0, 1.0)),
    "Y_Axis": ("App::Line", (0.5, 0.5, 0.5, 0.5000000000000001)),
    "Z_Axis": ("App::Line", (0.5, -0.5, 0.5, 0.5000000000000001)),
    "XY_Plane": ("App::Plane", (0.0, 0.0, 0.0, 1.0)),
    "XZ_Plane": ("App::Plane", (0.7071067811865475, 0.0, 0.0, 0.7071067811865475)),
    "YZ_Plane": ("App::Plane", (0.5, 0.5, 0.5, 0.5000000000000001)),
    "Origin": ("App::Point", (0.0, 0.0, 0.0, 1.0)),
}
SHORT = {"XY": "XY_Plane", "XZ": "XZ_Plane", "YZ": "YZ_Plane"}


def sub_shape(shape, sub: str):
    """TopoShape::getSubShape: Face6, Edge3, Vertex1 of a shape, numbered as TopExp::MapShapes numbers them."""
    m = ELEMENT.match(sub or "")
    if not m:
        raise FeatureError(f"{sub!r} is not an element name (Face1, Edge1, Vertex1, ...)")
    items = _subs(shape, {"Face": TopAbs_FACE, "Edge": TopAbs_EDGE, "Vertex": TopAbs_VERTEX}[m.group(1)])
    i = int(m.group(2))
    if i > len(items):
        raise FeatureError(f"there is no {sub}: the shape has {len(items)} {m.group(1).lower()}s")
    return items[i - 1]


# ── the properties ────────────────────────────────────────────────────────────────────────────────────

def support_list(where: str, sup, most: int | None = 4) -> list[tuple[str, str]]:
    """AttachmentSupport as a part file writes it, normalised to [(object, element), ...]: a name alone is
    (name, ""), "Pad.Face6" is ("Pad", "Face6"), (name, [e1, e2]) is two references, and the old "XY" is
    ("XY_Plane", ""). most is how many AttachmentSupport takes; a ShapeBinder's Support has no limit (None)."""
    if sup is None:
        return []
    if isinstance(sup, str):
        sup = [sup]
    if isinstance(sup, (tuple, list)) and len(sup) == 2 and isinstance(sup[0], str) and "." not in sup[0] and (
            (isinstance(sup[1], str) and (sup[1] == "" or ELEMENT.match(sup[1])))
            or (isinstance(sup[1], list) and all(isinstance(x, str) for x in sup[1]))):
        sup = [tuple(sup)]                              # one reference: ("Pad", "Face6") or ("Pad", ["Face6", ...])
    out = []
    for r in sup:
        if isinstance(r, str):
            obj, _, sub = r.partition(".")              # "Pad.Face6", FreeCAD's subname, or a whole object
            r = (obj, sub)
        try:
            obj, sub = r
        except (TypeError, ValueError):
            raise FeatureError(f"{where}: attachment reference {r!r} is not (object, element)") from None
        if not isinstance(obj, str):
            raise FeatureError(f"{where}: attachment reference {r!r}: the object is a name")
        subs = [sub] if isinstance(sub, str) or sub is None else list(sub)
        for s in subs or [""]:
            if s and not ELEMENT.match(s) and s not in ("X", "Y", "Z") and not any(s.startswith(r) for r in ORIGIN):
                raise FeatureError(f"{where}: {s!r} is not an element name (Face1, Edge1, Vertex1, ..., or an LCS's "
                                   "XY_Plane, X_Axis, ..., Origin)")
            out.append((SHORT.get(obj, obj), s or ""))
    if most is not None and len(out) > most:
        raise FeatureError(f"{where}: an attachment takes at most four references (FreeCAD's Reference 1 to 4)")
    return out


def placement_of(where: str, value, what: str = "placement") -> A.Placement:
    try:
        return A.Placement.from_offset(value)
    except (TypeError, ValueError):
        raise FeatureError(f"{where}: {what} {value!r} is not (x, y, z) or ((x, y, z), (yaw, pitch, roll))") \
            from None


from .feature_kw import KwFeature  # noqa: E402


class Attachable:
    """AttachExtension's properties on a feature: set by init_attachment() from the part file's keywords."""
    engine = "Plane"
    attachment_support: list = []
    map_mode = "Deactivated"

    def init_attachment(self, where, attachment_support=None, map_mode=None, attachment_offset=None,
                        map_reversed=False, map_path_parameter=0.0, placement=None, default_mode=None):
        self.attachment_support = support_list(where, attachment_support)
        if map_mode is None:
            if not self.attachment_support:
                map_mode = "Deactivated"
            elif default_mode is not None:
                map_mode = default_mode
            else:
                map_mode = None                           # resolved by suggestion when the Body is built
        if map_mode is not None and map_mode not in A.modes(self.engine):
            raise FeatureError(f"{where}: map_mode {map_mode!r} is not one of {', '.join(A.modes(self.engine))} "
                               f"({A.ENGINE_TYPES[self.engine]}'s MapMode)")
        self.map_mode = map_mode
        self.attachment_offset = attachment_offset
        self._offset_pl = placement_of(where, attachment_offset, "attachment_offset")
        self.map_reversed = bool(map_reversed)
        try:
            self.map_path_parameter = float(map_path_parameter)
        except (TypeError, ValueError):
            raise FeatureError(f"{where}: map_path_parameter {map_path_parameter!r} is not a number") from None
        self.own_placement = placement                    # the part file's placement=, the Placement kept unattached
        self._own_pl = placement_of(where, placement)

    def attachment_kwargs(self) -> dict:
        return {"attachment_support": list(self.attachment_support), "map_mode": self.map_mode,
                "attachment_offset": self.attachment_offset, "map_reversed": self.map_reversed,
                "map_path_parameter": self.map_path_parameter, "placement": self.own_placement}

    def references(self) -> list[str]:
        return [o.split(".")[0] for o, _ in self.attachment_support]


# ── datum features ────────────────────────────────────────────────────────────────────────────────────

ATTACH_DEFAULTS = {"attachment_support": (), "map_mode": None, "attachment_offset": None, "map_reversed": False,
                   "map_path_parameter": 0.0, "placement": None}


class _Datum(KwFeature, Attachable):
    """A datum: reference geometry placed by its attachment, its shape moved to its Placement. SIZE are the
    properties only its view uses (PartDesign::Plane's ResizeMode, Length, Width).

    A feature_kw.KwFeature: its properties are AttachExtension's (ATTACH_DEFAULTS; map_mode None is the best fit
    for its references, as UnifiedDatumCommand picks it) and SIZE, which feature_edit reads, writes and edits as it
    does every KwFeature's."""
    kind = ""
    is_datum = True
    SIZE: dict = {}
    REFS = ("attachment_support",)
    plane = False                       # an App::Plane (MidPoint's special case, the plane flag of a reference)

    def __init_subclass__(cls, **kw):
        super().__init_subclass__(**kw)
        if getattr(cls, "type_id", None):
            cls.TYPE_ID = cls.type_id
            cls.DEFAULTS = {**ATTACH_DEFAULTS, **cls.SIZE}

    def normalize(self, key, v):
        if key == "attachment_support":
            v = support_list(self.name, v)
        elif key in ("map_mode", "attachment_offset", "placement", "map_path_parameter"):
            return v
        return super().normalize(key, v)

    def validate(self):
        mode = self.map_mode
        self.init_attachment(self.name, list(self.attachment_support), mode, self.attachment_offset,
                             self.map_reversed, self.map_path_parameter, self.placement)
        self.attachment_support = tuple(self.attachment_support)
        for k in self.SIZE:
            v = getattr(self, k)
            if k == "resize_mode":
                if v not in ("Automatic", "Manual"):
                    raise FeatureError(f"{self.name}: resize_mode {v!r} is not Automatic or Manual")
            else:
                try:
                    setattr(self, k, float(v))
                except (TypeError, ValueError):
                    raise FeatureError(f"{self.name}: {k} {v!r} is not a number") from None

    def source_value(self, key, v=None):
        v = getattr(self, key) if v is None else v
        if key in ("attachment_offset", "placement") and isinstance(v, (list, tuple)):    # ((x, y, z), (y, p, r))
            return tuple(tuple(x) if isinstance(x, (list, tuple)) else x for x in v)
        return super().source_value(key, v)

    def source_props(self) -> list[str]:
        """What the part file writes: what is not FreeCAD's default (an unattached datum's Deactivated is implied)."""
        return [k for k in self.DEFAULTS if not self.is_default(k)
                and not (k == "map_mode" and self.map_mode == "Deactivated" and not self.attachment_support)]

    def references(self) -> list[str]:
        """The features it is attached to; the Body's origin features left out (an LCS's role is the LCS's)."""
        return [n for n in Attachable.references(self) if n not in ORIGIN]

    def local_shape(self):
        raise NotImplementedError

    def element(self, sub, pl: A.Placement):
        """(shape, placement, whole, plane) of one of its elements; a datum has its shape's own Face1, Edge1,
        Vertex1."""
        return sub_shape(_moved(self.local_shape(), pl), sub), pl, False, False

    def __repr__(self):
        return f"{self.kind}({self.name!r}, map_mode={self.map_mode!r}, support={self.attachment_support!r})"


def _infinite(shape):
    shape.Infinite(True)
    return shape


def _plane_face(normal=(0, 0, 1)):
    return BRepBuilderAPI_MakeFace(gp_Pln(gp_Pnt(0, 0, 0), gp_Dir(*normal))).Shape()


def _line_edge(direction=(0, 0, 1)):
    return BRepBuilderAPI_MakeEdge(gp_Lin(gp_Pnt(0, 0, 0), gp_Dir(*direction))).Shape()


# What FreeCAD 26.3's Edit > Datums (the Structure toolbar's Part_Datums) makes, in the active Body: Part's datums,
# App::Plane, App::Line and App::Point with AttachExtension (Mod/Part/App/Datums.cpp), shaped as
# Part::Feature::getTopoShape shapes an App datum (PartFeature.cpp).

class DatumPlane(_Datum):
    """Part::DatumPlane (Part_DatumPlane, Datum Plane): an App::Plane, an infinite face on its placement's XY."""
    kind = "DatumPlane"
    TRANSACTION = "Add datum plane"
    type_id = "Part::DatumPlane"
    engine = "Plane"
    plane = True

    def local_shape(self):
        return _infinite(_plane_face())


class DatumLine(_Datum):
    """Part::DatumLine (Part_DatumLine, Datum Line): an App::Line whose base direction is Z, an infinite edge."""
    kind = "DatumLine"
    TRANSACTION = "Add datum line"
    type_id = "Part::DatumLine"
    engine = "Line"

    def local_shape(self):
        return _infinite(_line_edge())


class DatumPoint(_Datum):
    """Part::DatumPoint (Part_DatumPoint, Datum Point): an App::Point, a vertex at its placement."""
    kind = "DatumPoint"
    TRANSACTION = "Add datum point"
    type_id = "Part::DatumPoint"
    engine = "Point"

    def local_shape(self):
        return BRepBuilderAPI_MakeVertex(gp_Pnt(0, 0, 0)).Shape()


class LocalCoordinateSystem(_Datum):
    """Part::LocalCoordinateSystem (Part_CoordinateSystem, Coordinate System; FreeCAD names it LCS): an
    App::LocalCoordinateSystem placed by the 3D engine. It has no shape of its own; its elements are its
    origin's features by role, X_Axis, Y_Axis, Z_Axis, XY_Plane, XZ_Plane, YZ_Plane and Origin, placed as the
    Body's origin is (LocalCoordinateSystem::getSetupData), in the LCS's frame."""
    kind = "LocalCoordinateSystem"
    TRANSACTION = "Add coordinate system"
    type_id = "Part::LocalCoordinateSystem"
    engine = "3D"

    def local_shape(self):
        return None

    def element(self, sub, pl: A.Placement):
        role = next((r for r in ORIGIN if sub.startswith(r)), None)    # extensionGetSubObject: XY_Plane001 too
        if role is None:
            raise FeatureError(f"LocalCoordinateSystem \"{self.name}\" doesn't contain feature with role \"{sub}\"")
        kind, q = ORIGIN[role]
        child = pl * A.Placement((0, 0, 0), A.Rotation(q, normalize=False))
        shape = _origin_local(kind)
        # "XY_Plane" is an element (typed Plane); "XY_Plane." (what the GUI's TaskAttacher stores, with FreeCAD's
        # own name XY_Plane001.) is the sub-object itself (Plane|Placement), placed through the LCS
        whole = sub.endswith(".")
        return _moved(shape, child), child, whole, False


# The PartDesign workbench's own datums (Mod/PartDesign/App/DatumPlane.cpp and its neighbours): FreeCAD 26.3 still
# has them (PartDesign_Plane, ...: no longer in its menus, and in every file made before Part's datums).

class PartDesignPlane(_Datum):
    """PartDesign::Plane: an infinite face on its placement's XY. ResizeMode, Length and Width (20 x 20) are how
    its view draws it."""
    kind = "PartDesignPlane"
    TRANSACTION = "Create DatumPlane"
    type_id = "PartDesign::Plane"
    engine = "Plane"
    SIZE = {"resize_mode": "Automatic", "length": 20.0, "width": 20.0}

    def local_shape(self):
        return _infinite(_plane_face())


class PartDesignLine(_Datum):
    """PartDesign::Line: an infinite edge along its placement's Z."""
    kind = "PartDesignLine"
    TRANSACTION = "Create DatumLine"
    type_id = "PartDesign::Line"
    engine = "Line"
    SIZE = {"resize_mode": "Automatic", "length": 20.0}

    def local_shape(self):
        return _infinite(_line_edge())


class PartDesignPoint(_Datum):
    """PartDesign::Point: a vertex at its placement."""
    kind = "PartDesignPoint"
    TRANSACTION = "Create DatumPoint"
    type_id = "PartDesign::Point"
    engine = "Point"

    def local_shape(self):
        return BRepBuilderAPI_MakeVertex(gp_Pnt(0, 0, 0)).Shape()


class PartDesignCoordinateSystem(_Datum):
    """PartDesign::CoordinateSystem (Local_CS): placed by the 3D engine; its shape is the XY plane's face
    (DatumCS.cpp), its elements X, Y and Z the planes normal to those axes (getSubObject)."""
    kind = "PartDesignCoordinateSystem"
    TRANSACTION = "Create Local_CS"
    type_id = "PartDesign::CoordinateSystem"
    engine = "3D"

    def local_shape(self, axis: str = ""):
        return _plane_face({"X": (1, 0, 0), "Y": (0, 1, 0)}.get(axis, (0, 0, 1)))

    def element(self, sub, pl: A.Placement):
        if sub in ("X", "Y", "Z"):
            return _moved(self.local_shape(sub), pl), pl, False, False
        return super().element(sub, pl)


DATUMS = {c.kind: c for c in (DatumPlane, DatumLine, DatumPoint, LocalCoordinateSystem, PartDesignPlane,
                              PartDesignLine, PartDesignPoint, PartDesignCoordinateSystem)}
# FreeCAD's default object name for each (getUniqueObjectName's base): Part_DatumPlane's DatumPlane, ...
DEFAULT_NAMES = {"DatumPlane": "DatumPlane", "DatumLine": "DatumLine", "DatumPoint": "DatumPoint",
                 "LocalCoordinateSystem": "LCS", "PartDesignPlane": "DatumPlane", "PartDesignLine": "DatumLine",
                 "PartDesignPoint": "DatumPoint", "PartDesignCoordinateSystem": "Local_CS"}


def _origin_local(kind):
    if kind == "App::Plane":
        return _infinite(_plane_face())
    if kind == "App::Line":
        return _infinite(_line_edge((1, 0, 0)))
    return BRepBuilderAPI_MakeVertex(gp_Pnt(0, 0, 0)).Shape()


# ── the Body's objects, as references resolve them ────────────────────────────────────────────────────

def _moved(shape, pl: A.Placement):
    return shape.Moved(TopLoc_Location(pl.trsf()))


class Context:
    """The objects of a Body so far, in its order: shapes (global) and Placements by name."""

    def __init__(self, base=None):
        self.shapes: dict = {}
        self.placements: dict = {}
        self.kinds: dict = {}
        self.datums: dict = {}
        self.sketches: dict = {}
        self.external: dict = {}
        self.modes: dict = {}
        for role, (kind, q) in ORIGIN.items():
            self.placements[role] = A.Placement((0, 0, 0), A.Rotation(q, normalize=False))
            self.kinds[role] = kind
        if base is not None:
            self.add_solid("BaseFeature", base, A.Placement())

    def add_solid(self, name, shape, placement: A.Placement):
        self.shapes[name] = shape
        self.placements[name] = placement
        self.kinds[name] = "solid"

    def add_sketch(self, sketch, placement: A.Placement):
        self.sketches[sketch.name] = sketch
        self.placements[sketch.name] = placement
        self.kinds[sketch.name] = "sketch"

    def add_binder(self, f) -> A.Placement:
        """PartDesign::ShapeBinder: it copies its support's shape, which is its Shape and Placement
        (ShapeBinder::execute), and a later feature can reference it; it is not a solid feature, so the Body's Tip
        stays where it was."""
        if f.name in self.kinds:
            raise FeatureError(f"two features are named {f.name!r}")
        from .feature_binder import binder_shape
        shape = binder_shape(f, self)
        pl = A.Placement.from_trsf(shape.Location().Transformation()) \
            if shape is not None and not shape.IsNull() else A.Placement()
        self.shapes[f.name] = shape
        self.placements[f.name] = pl
        self.kinds[f.name] = "binder"
        return pl

    def first_placement(self, sketch) -> A.Placement:
        """ProfileBased::positionByPrevious for the Body's first solid feature: the Placement of its sketch's
        first support object (an origin plane, a datum), else the sketch's own."""
        sup = getattr(sketch, "attachment_support", None) or \
            ([(sketch.support + "_Plane", "")] if getattr(sketch, "support", None) else [])
        if sup and sup[0][0] in self.placements and self.kinds.get(sup[0][0]) != "sketch":
            return self.placements[sup[0][0]]
        return self.placements.get(sketch.name, A.Placement())

    def own_placement(self, f) -> A.Placement:
        """A feature's own Placement: where its attachment put it (attach_feature), else its placement keyword."""
        pl = getattr(f, "_attached_pl", None)
        if pl is not None:
            return pl
        try:
            return placement_of(f.name, getattr(f, "placement", None))
        except FeatureError:
            return A.Placement()

    def origin_shape(self, role):
        return _moved(_origin_local(ORIGIN[role][0]), self.placements[role])

    def sketch_shape(self, name, sub=""):
        """A sketch's Shape: its non-construction edges, placed; EdgeN is its geometry N-1."""
        from .feature import Point, _edge
        sk = self.sketches[name]
        loc = TopLoc_Location(self.placements[name].trsf())
        if sub:
            m = ELEMENT.match(sub)
            if not m or m.group(1) != "Edge":
                raise FeatureError(f"{sub!r} of a sketch: only its edges (Edge1 is geometry 0) can be referenced")
            i = int(m.group(2)) - 1
            if i >= len(sk.geometry) or isinstance(sk.geometry[i], Point):
                raise FeatureError(f"the sketch {name} has no edge {sub}")
            return TopoDS.Edge(_edge(sk.geometry[i]).Moved(loc))
        edges = [_edge(g).Moved(loc) for g in sk.geometry if not g.construction and not isinstance(g, Point)]
        if not edges:
            return None
        comp, b = TopoDS_Compound(), BRep_Builder()
        b.MakeCompound(comp)
        for e in edges:
            b.Add(comp, e)
        return comp

    def resolve(self, obj, sub, where):
        """(shape, placement, whole, plane) of a reference, as readLinks finds them: the shape extractSubShape
        gives (None for an object with no shape), the Placement getGlobalPlacement gives, whether it names an
        object rather than an element (rtFlagHasPlacement), and whether that object is an App::Plane."""
        if obj in ORIGIN:
            if sub:
                raise FeatureError(f"{where}: the origin's {obj} has no element {sub!r}")
            return self.origin_shape(obj), self.placements[obj], True, ORIGIN[obj][0] == "App::Plane"
        kind = self.kinds.get(obj)
        if kind is None:
            raise FeatureError(f"{where}: no {obj!r} before it (a feature, a datum, or the Body's origin: "
                               f"{', '.join(ORIGIN)})")
        pl = self.placements[obj]
        try:
            if kind == "sketch":
                return self.sketch_shape(obj, sub), pl, not sub, False
            if kind == "datum":
                d = self.datums[obj]
                return d.element(sub, pl) if sub else (self.shapes[obj], pl, True, d.plane)
            return (sub_shape(self.shapes[obj], sub) if sub else self.shapes[obj]), pl, not sub, False
        except FeatureError as e:
            raise FeatureError(f"{where}: {obj}.{sub}: {e}") from None

    def element(self, obj, sub, where):
        """The shape a reference names (None for an object with no shape)."""
        return self.resolve(obj, sub, where)[0]

    def ref(self, obj, sub, where) -> A.Ref:
        shape, pl, whole, plane = self.resolve(obj, sub, where)
        return A.Ref(shape, pl, whole=whole, plane=plane)

    def attach(self, f, where=None, orig: A.Placement | None = None) -> A.Placement | None:
        """f's Placement by its attachment, or None when it is not attached (Deactivated, no support)."""
        where = where or f.name
        refs = [self.ref(o, s, where) for o, s in f.attachment_support]
        mode = f.map_mode
        if mode is None:                                  # UnifiedDatumCommand: the best fit for the support
            sug = A.suggest(f.engine, [r.type() for r in refs])
            if sug["message"] != "OK":
                raise FeatureError(f"{where}: There are no attachment modes that fit selected objects. Select "
                                   "something else.")
            mode = sug["best"]
        self.modes[f.name] = mode
        if mode == "Deactivated" or not refs:
            return None
        try:
            return A.attach(f.engine, mode, refs, offset=f._offset_pl, reversed=f.map_reversed,
                            parameter=f.map_path_parameter, orig=orig)
        except A.AttachError as e:
            raise FeatureError(f"{where}: {e}") from None

    def add_datum(self, d):
        if d.name in self.kinds:
            raise FeatureError(f"two features are named {d.name!r}")
        pl = self.attach(d, orig=d._own_pl)
        pl = pl if pl is not None else d._own_pl
        self.datums[d.name] = d
        self.placements[d.name] = pl
        self.kinds[d.name] = "datum"
        local = d.local_shape()
        self.shapes[d.name] = _moved(local, pl) if local is not None else None
        return pl

    def external_shape(self, obj, sub, where):
        """rebuildExternalGeometry's refSubShape: a datum's own shape, an origin feature's plane, line or point,
        else the element of the object's shape."""
        return self.element(obj, sub, where)


# ── external geometry (SketchObject::rebuildExternalGeometry, SketchObjectExternal.cpp) ─────────────────

class _Proj:
    def __init__(self, pl: A.Placement):
        self.pl = pl
        self.inv = pl.inverse()
        dn = pl.rot.mult_vec((0, 0, 1))
        dx = pl.rot.mult_vec((1, 0, 0))
        self.ax3 = gp_Ax3(gp_Pnt(*pl.pos), gp_Dir(*dn), gp_Dir(*dx))
        self.plane = gp_Pln(self.ax3)
        self.gplane = Geom_Plane(self.plane)
        self.mov = self.inv.trsf()

    def near(self, p):
        return GeomAPI_ProjectPointOnSurf(p, self.gplane).NearestPoint()

    def local(self, p):
        """invPlm.multVec of a global point: (x, y) in the sketch, z dropped."""
        v = self.inv.mult_vec((p.X(), p.Y(), p.Z()))
        return v

    def xyz(self, p):
        """ProjPointOnPlane_XYZ: p projected onto the plane through its own axes."""
        o = self.plane.Location()
        op = gp_Vec(o, p)
        xd, yd = gp_Vec(self.plane.Position().XDirection()), gp_Vec(self.plane.Position().YDirection())
        u, v = op.Dot(xd), op.Dot(yd)
        return gp_Pnt(xd.Multiplied(u).Added(yd.Multiplied(v)).Added(gp_Vec(o.XYZ())).XYZ())


def _point(p, construction=True):
    return {"type": "Point", "at": [p[0], p[1]], "construction": construction}


def _segment(p1, p2, construction=True):
    return {"type": "LineSegment", "start": [p1[0], p1[1]], "end": [p2[0], p2[1]], "construction": construction}


def _project_line(curve, pr: _Proj):
    """projectLine."""
    first, last = curve.FirstParameter(), curve.LastParameter()
    if abs(first) > 1e99:
        first = -10000.0
    if abs(last) > 1e99:
        last = 10000.0
    p1 = pr.local(pr.near(curve.Value(first)))
    p2 = pr.local(pr.near(curve.Value(last)))
    if math.dist(p1, p2) < A.CONFUSION:
        return _point(tuple((a + b) / 2 for a, b in zip(p1, p2)))
    return _segment(p1, p2)


def _process_edge(edge, pr: _Proj, where):
    """processEdge, for the curves the sketch has (lines and circles); an ellipse, a B-spline and the other
    curves FreeCAD projects are not sketch geometry here yet."""
    from . import feature_attach_curves as FAC         # the other curves' branches of processEdge
    curve = BRepAdaptor_Curve(edge)
    t = curve.GetType()
    if t == GeomAbs_Line:
        return [_project_line(curve, pr)]
    if t == GeomAbs_Ellipse:
        return FAC.ellipse(edge, pr)
    if t != GeomAbs_Circle:
        return FAC.other(edge, pr)
    vec1 = pr.plane.Axis().Direction()
    circ = curve.Circle()
    vec2 = circ.Axis().Direction()
    f, l = curve.FirstParameter(), curve.LastParameter()
    beg, end = curve.Value(f), curve.Value(l)
    if vec1.IsParallel(vec2, A.CONFUSION):
        cnt = pr.near(circ.Location())
        c = pr.local(cnt)
        r = circ.Radius()
        if beg.SquareDistance(end) < A.CONFUSION:
            return [{"type": "Circle", "center": [c[0], c[1]], "radius": r, "construction": True}]
        # Geom_TrimmedCurve(circle moved into the sketch, f, l): counter-clockwise about the sketch's normal
        # when the circle's axis agrees with it; otherwise it runs clockwise, and the Sketcher sees it from end
        # to start (GeomArcOfCircle's emulateCCWXY).
        pb, pe = pr.local(beg), pr.local(end)
        a_b = math.atan2(pb[1] - c[1], pb[0] - c[0])
        a_e = math.atan2(pe[1] - c[1], pe[0] - c[0])
        span = l - f
        same = vec1.Dot(vec2) > 0
        a0 = a_b if same else a_e
        return [{"type": "ArcOfCircle", "center": [c[0], c[1]], "radius": r, "start_angle": a0,
                 "end_angle": a0 + span, "construction": True}]
    if vec1.IsNormal(vec2, 1e-12):                  # Precision::Angular()
        cnt = pr.near(circ.Location())
        orient = vec1.Crossed(vec2)
        line = Geom_Line(cnt, orient)
        P1, P2 = line.Value(-circ.Radius()), line.Value(circ.Radius())
        if not curve.IsClosed():
            alpha = orient.AngleWithRef(circ.XAxis().Direction(), circ.Axis().Direction())
            base = f
            tours = 0
            start = base + alpha
            pi = math.pi
            while start < -pi / 2.0 and tours < 10:
                tours += 1
                start = base + tours * 2.0 * pi + alpha
            while start >= 3.0 * pi / 2.0 and tours > -10:
                tours -= 1
                start = base + tours * 2.0 * pi + alpha
            endA = l + start - base
            X = pr.xyz
            if start <= 0.0:
                if endA <= 0.0:
                    P1, P2 = X(beg), X(end)
                elif endA <= abs(start):
                    P1 = X(beg)
                elif endA < pi:
                    P1 = X(end)
            elif start < pi:
                if endA < pi:
                    P1, P2 = X(beg), X(end)
                elif endA < 2.0 * pi - start:
                    P2 = X(beg)
                elif endA < 2.0 * pi:
                    P2 = X(end)
            else:
                if endA < 2 * pi:
                    P1, P2 = X(beg), X(end)
                elif endA < 4 * pi - start:
                    P1 = X(beg)
                elif endA < 3 * pi:
                    P2 = X(end)
        return [_segment(pr.local(P1), pr.local(P2))]
    return FAC.oblique_circle(edge, pr)                  # the general case: an ellipse


def project(pl: A.Placement, shape, where: str = "external geometry") -> list[dict]:
    """The external geometry FreeCAD makes of one reference for a sketch placed at pl: a vertex gives a point,
    an edge its projection, a planar face the projections of its edges (one line when the face is edge-on to
    the sketch). Geometry dicts in the sketch's coordinates, construction (as GeometryFacade::setConstruction
    marks them)."""
    pr = _Proj(pl)
    if shape is None or shape.IsNull():
        raise FeatureError(f"{where}: the reference has no shape")
    st = shape.ShapeType()
    if st == TopAbs_VERTEX:
        p = pr.local(pr.near(BRep_Tool.Pnt_s(TopoDS.Vertex(shape))))
        return [_point(p)]
    if st == TopAbs_EDGE:
        return _process_edge(TopoDS.Edge(shape), pr, where)
    if st == TopAbs_FACE:
        face = TopoDS.Face(shape)
        surf = BRepAdaptor_Surface(face)
        if surf.GetType() != GeomAbs_Plane:
            raise FeatureError(f"{where}: a face that is not flat projects through hidden-line removal, which "
                               "is not supported yet")
        dnormal = surf.Plane().Axis().Direction()
        geos = []
        ex = TopExp_Explorer(face, TopAbs_EDGE)
        while ex.More():
            geos += _process_edge(TopoDS.Edge(ex.Current()), pr, where)
            ex.Next()
        if abs(dnormal.Angle(pr.plane.Axis().Direction()) - math.pi / 2) < A.CONFUSION:
            start = end = None
            for g in geos:
                if g["type"] != "LineSegment":
                    continue
                s, e = tuple(g["start"]), tuple(g["end"])
                if start is None:
                    start, end = s, e
                    continue
                for p in (s, e):
                    if math.dist(p, start) < math.dist(p, end):
                        if math.dist(p, end) > math.dist(end, start):
                            start = p
                    elif math.dist(p, start) > math.dist(end, start):
                        end = p
            if start is not None:
                return [{"type": "LineSegment", "start": list(start), "end": list(end), "construction": False}]
        return geos
    raise FeatureError(f"{where}: Unknown type of geometry")


def external_geometry(sketch, pl: A.Placement, ctx: Context) -> list[dict]:
    """A sketch's ExternalGeo after the H and V axes: GeoId -3, -4, ... in the order of its
    external_geometry references."""
    out = []
    for obj, sub in getattr(sketch, "external_geometry", None) or []:
        where = f"{sketch.name}: external geometry {obj}.{sub}" if sub else f"{sketch.name}: external geometry {obj}"
        out += project(pl, ctx.external_shape(obj, sub, where), where)
    return out


def external_list(where: str, ext) -> list[tuple[str, str]]:
    """ExternalGeometry as a part file writes it: [(object, element), ...]."""
    if not ext:
        return []
    out = []
    for r in ext:
        if isinstance(r, str):
            r = tuple(r.partition(".")[::2])            # "Pad.Edge3"
        try:
            obj, sub = r
        except (TypeError, ValueError):
            raise FeatureError(f"{where}: external geometry {r!r} is not (object, element)") from None
        if not isinstance(obj, str) or not isinstance(sub, str) or (sub and not ELEMENT.match(sub)):
            raise FeatureError(f"{where}: external geometry {r!r} is not (object, 'Edge1' / 'Vertex1' / 'Face1')")
        out.append((SHORT.get(obj, obj), sub))
    return out


# ── a part's Body, for `cad feature list` and `cad feature attach` ─────────────────────────────────────

def _load(path):
    """(the part module, its FEATURES, PARAMS, the base shape, its OBJECTS): a part of Part objects, of a Body, or
    both (a Part object attached to a Body feature)."""
    from . import state
    mod = state._load_module(path)
    features = list(getattr(mod, "FEATURES", None) or [])
    objects = list(getattr(mod, "OBJECTS", None) or [])
    if not features and not objects:
        raise FeatureError("the part has no FEATURES")
    params = dict(getattr(mod, "PARAMS", {}) or {})
    base = mod.build_base(**params) if hasattr(mod, "build_base") else None
    return mod, features, params, base, objects


def _evaluate_upto(features, params, base):
    """feature.evaluate of the features, and the first error if one stops it: (shapes, error or None). What
    builds before the error is kept, as FreeCAD's tree keeps it."""
    from .feature import evaluate
    try:
        return evaluate(features, params, base), None
    except FeatureError as e:
        err = str(e)
    for i in range(len(features) - 1, -1, -1):          # the longest prefix that builds
        try:
            return evaluate(features[:i], params, base), err
        except FeatureError:
            continue
    return evaluate([], params, base), err


def needs_body(doc: dict) -> bool:
    """Whether a feature list (feature_edit.read()) has something only the built document places: a datum, a sketch
    attached to anything but an origin plane with FlatFace, a sketch with external geometry, or a Part object the
    Attachment editor attached (feature_part.py's Part objects)."""
    datum_types = {c.type_id for c in DATUMS.values()}
    for f in doc.get("features") or []:
        if f.get("type") in datum_types:
            return True
        if f.get("type") == "Sketcher::SketchObject" and (not f.get("support") or f.get("external_geometry")):
            return True
    for o in doc.get("objects") or []:
        if o.get("attachment_support") or o.get("map_mode") not in (None, "Deactivated"):
            return True
    return False


def body_info(path) -> dict:
    """Every object's Placement as the document places it (the Body attaches its features, a Part object its
    attachment), each attached object's MapMode, and each sketch's external geometry: {"objects": {name:
    {"placement": ..., "map_mode": ..., "external": [...]}}, "error"}. Built past the Tip, as FreeCAD recomputes every
    feature of a Body, and every Part object after the objects it links."""
    try:
        _, features, params, base, part_objects = _load(path)
    except Exception as e:                              # a part that does not load says why; the tree still shows
        return {"objects": {}, "error": f"{type(e).__name__}: {e}"}
    if part_objects:
        return _part_info(part_objects, features, params, base)
    shapes, err = _evaluate_upto(features, params, base)
    ctx = shapes["_attach"]
    objects = {}
    for name, pl in ctx.placements.items():
        if name in ORIGIN:
            continue
        rec = {"placement": pl.as_dict()}
        if name in ctx.modes:
            rec["map_mode"] = ctx.modes[name]
        sk = shapes["_sketches"].get(name)
        if sk is not None:
            rec["external"] = list(sk._external)
        objects[name] = rec
    return {"objects": objects, "error": err}


def _part_info(part_objects, features, params, base) -> dict:
    """body_info of a part with Part objects: feature_part.evaluate places them, and the Body it holds."""
    from . import feature_part as Part
    body, body_err = _evaluate_upto(features, params, base) if features else ({}, None)
    try:
        shapes = Part.evaluate(part_objects, params, features, base, body=body, keep_going=True)
    except FeatureError as e:                           # OBJECTS that do not load: a duplicate name, a bad entry
        return {"objects": {}, "error": str(e)}
    ctx = shapes["_ctx"]
    sketches = (ctx.body or {}).get("_sketches", {})
    objects = {}
    sources = [(ctx.placements, ctx.modes)]
    if ctx.attach_ctx is not None:
        sources.insert(0, (ctx.attach_ctx.placements, ctx.attach_ctx.modes))
    for placements, modes in sources:
        for name, pl in placements.items():
            if name in ORIGIN or name == Part.BODY:
                continue
            rec = {"placement": pl.as_dict()}
            if name in modes:
                rec["map_mode"] = modes[name]
            sk = sketches.get(name)
            if sk is not None:
                rec["external"] = list(sk._external)
            objects[name] = rec
    err = body_err or next(iter(ctx.errors.values()), None)
    return {"objects": objects, "error": err}


def project_query(path, sketch: str, refs) -> dict:
    """What Sketcher_External adds for references picked while a sketch is in edit: each one projected onto the
    sketch as the Body places it (rebuildExternalGeometry), resolved in the Body before the sketch.
    {"placement": the sketch's, "external": [[geometry, ...] per reference], "errors": [message or None, ...]}"""
    _, features, params, base, _objects = _load(path)
    names = [getattr(f, "name", None) for f in features]
    if sketch not in names:
        raise FeatureError(f"there is no sketch {sketch!r}")
    f = features[names.index(sketch)]
    shapes, err = _evaluate_upto(features[:names.index(sketch)], params, base)
    ctx = shapes["_attach"]
    pl = ctx.attach(f, f"Sketch {sketch}", orig=f._own_pl) or f._own_pl     # as feature._place_sketch places it
    out = {"placement": pl.as_dict(), "external": [], "errors": [], "build_error": err}
    for r in external_list(f"Sketch {sketch}", refs):
        where = f"{sketch}: external geometry {r[0]}.{r[1]}" if r[1] else f"{sketch}: external geometry {r[0]}"
        try:
            out["external"].append(project(pl, ctx.external_shape(r[0], r[1], where), where))
            out["errors"].append(None)
        except FeatureError as e:
            out["external"].append([])
            out["errors"].append(str(e))
    return out


def attach_query(path, support, engine: str = "Plane", mode: str | None = None, offset=None,
                 reversed: bool = False, parameter: float = 0.0, before: str | None = None,
                 prefer: str | None = None) -> dict:
    """What FreeCAD's Attachment panel shows for a set of references (TaskAttacher::updatePreview): their types,
    suggestMapModes' answer, and the Placement of the mode (the best fit when none is given). The references
    resolve in the Body as it stands before `before` (the feature being edited), or with all of it; a Part object
    (`before` in a part with OBJECTS) resolves them among the objects before it, and uses its own engine, the
    AttacherEngine the editor shows (Attacher::AttachEngine3D for every Part object)."""
    _, features, params, base, part_objects = _load(path)
    body_err = None
    if part_objects:
        from . import feature_part as Part
        target = next((o for o in part_objects if o.name == before), None)
        if target is not None:
            engine = target.engine
            part_objects = part_objects[:[o.name for o in part_objects].index(before)]
        body, body_err = _evaluate_upto(features, params, base) if features else ({}, None)
        try:
            shapes = Part.evaluate(part_objects, params, features, base, body=body, keep_going=True)
        except FeatureError as e:
            return {"engine": engine, "message": "LinkBroken", "error": str(e)}
        ctx, err = shapes["_ctx"], body_err
    else:
        names = [getattr(f, "name", None) for f in features]
        if before is not None and before in names:
            features = features[:names.index(before)]
        shapes, err = _evaluate_upto(features, params, base)
        ctx = shapes["_attach"]
    out = {"engine": engine, "build_error": err}
    try:
        refs = support_list("attachment", support)
        out["references"] = [list(r) for r in refs]
        resolved = [ctx.ref(o, s, "attachment") for o, s in refs]
    except FeatureError as e:
        out.update({"message": "LinkBroken", "error": str(e)})
        return out
    sug = A.suggest(engine, [r.type() for r in resolved])
    out.update({"types": sug["types"], "suggestion": sug, "message": sug["message"]})
    # TaskAttacher::addToReference: the mode chosen before stays while it still fits, else the best fit
    use = mode or (prefer if prefer in sug["all"] else sug["best"] if sug["message"] == "OK" else "Deactivated")
    out["mode"] = use
    out["placement"] = None
    if use == "Deactivated" or not resolved:
        return out
    try:
        pl = A.attach(engine, use, resolved, offset=placement_of("attachment", offset, "attachment_offset"),
                      reversed=reversed, parameter=parameter)
        out["placement"] = pl.as_dict() if pl is not None else None
    except (A.AttachError, FeatureError) as e:
        out["error"] = str(e)
    return out

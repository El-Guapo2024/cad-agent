"""A part's shape as FreeCAD's PartDesign feature list: sketches, pads and pockets, in plain Python.

A part made in the app is still a part module, parts/<name>.py, with PARAMS and build(). Its shape is a
FEATURES list, the Body's tree in FreeCAD's order, written with FreeCAD's own Python vocabulary so a
FreeCAD user reads it as their tree and the same lines can be fed to FreeCAD (to_freecad below):

    from cad_agent.feature import (ArcOfCircle, Body, Circle, Constraint, LineSegment, Pad, Pocket,
                                   Point, Sketch)

    PARAMS = {"width": 40.0, "height": 20.0, "thick": 5.0}

    FEATURES = [
        Sketch("Sketch", support="XY",
               geometry=[
                   LineSegment((0.0, 0.0), (40.0, 0.0)),
                   LineSegment((40.0, 0.0), (40.0, 20.0)),
                   LineSegment((40.0, 20.0), (0.0, 20.0)),
                   LineSegment((0.0, 20.0), (0.0, 0.0)),
               ],
               constraints=[
                   Constraint("Coincident", 0, 2, 1, 1),
                   ...
                   Constraint("Horizontal", 0),
                   Constraint("DistanceX", 0, 1, 0, 2, "width"),
               ]),
        Pad("Pad", "Sketch", length="thick"),
    ]
    TIP = "Pad"                      # optional: Body.Tip; without it, the last feature


    def build(**p):
        return Body(FEATURES, p, tip=TIP)

A part that also has hand-written build123d keeps it as build_base(**p), and the Body takes its solid as
FreeCAD's BaseFeature: `return Body(FEATURES, p, base=build_base(**p), tip=TIP)`. feature_edit converts a
hand-written part to that form on its first added feature.

One list, not SKETCHES and FEATURES apart: FreeCAD's Body is one ordered Group in which a sketch sits
before the features that use it, and an up-to-face or a later sketch can only name what comes before it.
The order is the history, so it is kept in one place. Every entry is a call whose first argument is its
name, so an agent and cad_agent/feature_edit.py both find an entry by its name. feature_edit is what the
app's server calls: read(part_path) gives the tree as JSON-ready dicts and apply(part_path, ops) adds,
sets, deletes, renames, moves and sets the tip, rewriting only the literals it changes (its docstring has
the dict format).

The vocabulary, as FreeCAD's Python API has it:

    geometry     LineSegment((x1, y1), (x2, y2)), Circle((cx, cy), r),
                 ArcOfCircle((cx, cy), r, start_angle, end_angle)  (radians, counter-clockwise, as
                 Part.ArcOfCircle(circle, a0, a1)), Point((x, y)), each with construction=False;
                 the conics and B-splines Ellipse, ArcOfEllipse, ArcOfHyperbola, ArcOfParabola and
                 BSplineCurve are cad_agent/feature_curves.py's (its docstring has their arguments)
    constraints  Constraint(type, *args) with Sketcher.Constraint's argument lists: geometry indices
                 from 0 in list order, -1 the sketch's H axis, -2 its V axis (point 1 of -1 is the
                 origin); point positions 1 start, 2 end, 3 centre. A value (the last argument of a
                 dimensional constraint) is a number in mm or radians, or a string: the name of a PARAMS
                 entry or an arithmetic expression over them, like FreeCAD's expression binding. An
                 expression gives an angle in degrees, as a unitless FreeCAD expression does.
    Sketch       Sketch(name, support="XY" | "XZ" | "YZ", attachment_offset=(x, y, z) or
                 ((x, y, z), (yaw, pitch, roll)), geometry=[...], constraints=[...]), attached FlatFace
                 to the body's origin plane as FreeCAD attaches it. The planes are FreeCAD's: XZ has the
                 sketch's x along X, its y along Z and its normal along -Y; YZ has x along Y, y along Z
                 and its normal along +X. The offset is the AttachmentOffset placement, in the plane's
                 own frame (z along the normal), degrees for the rotation as App.Rotation(yaw, pitch, roll).
    Pad, Pocket  PartDesign::Pad and PartDesign::Pocket with their property names in snake_case and
                 FreeCAD's defaults (FeaturePad.cpp, FeaturePocket.cpp and FeatureExtrude.cpp at FreeCAD
                 3160daf1e2b6): side_type "One side" | "Two sides" | "Symmetric", type and type2 (a Pad:
                 Length, UpToLast, UpToFirst, UpToFace, UpToShape; a Pocket: Length, ThroughAll,
                 UpToFirst, UpToFace, UpToShape), length (Pad 10, Pocket 5), length2, offset, offset2,
                 reversed, up_to_face / up_to_face2 (("Pad", "Face6"), or "XY_Plane" and the other origin
                 planes), up_to_shape / up_to_shape2 (["Pad"] or [("Pad", ["Face3", "Face6"])]),
                 use_custom_vector, direction, along_sketch_normal, start_type ("Profile plane" or
                 "Offset") and start_offset, refine (FreeCAD's default, True), and the deprecated forms
                 FreeCAD still reads: midplane=True (SideType Symmetric) and type="TwoLengths" (SideType
                 Two sides).
    Revolution, Groove, Hole
                 PartDesign::Revolution, ::Groove and ::Hole, in their own modules (feature_revolve.py,
                 feature_hole.py, whose docstrings list their properties) and imported from here too.
    Body         Body(FEATURES, params, base=None) builds the tip's solid; base is a hand-built solid,
                 FreeCAD's BaseFeature, which the first feature adds to or cuts from.
    Mirrored, LinearPattern, PolarPattern, MultiTransform
                 PartDesign's transformed features (feature_transform.py has their properties)
    AdditiveBox ... SubtractiveWedge
                 the 16 primitives (feature_primitive.py); both written as feature_kw.KwFeature calls

What is built is the solid FreeCAD would build, because the same OCCT calls build it in the same order:
the sketch's edges are joined to wires as TopoShape::makeElementWires joins them, the face is made as
FaceMakerBullseye makes it (Pad and Pocket's default, since a Body's features have AllowMultiFace on),
the prism is BRepPrimAPI_MakePrism or, for the up-to types, BRepFeat_MakePrism as
TopoShape::makeElementPrismUntil drives it, and the boolean and the refine follow buildExtrusion.
tests/test_feature.py holds the volume, area, bounding box and centre of mass of a few dozen bodies to
what freecadcmd builds from the same lines (tests/golden/feature/make.py).

Solving: a sketch stores its solved coordinates, as SketchObject stores its Geometry, so a build needs no
solver while the geometry satisfies the constraints. When it does not (a PARAMS value or a constraint
value changed, or a coordinate was edited), the sketch is re-solved by FreeCAD's PlaneGCS through
cad_agent.planegcs; _solve() is the one place that calls it.

Errors are worded as FreeCAD words them ("Wire is not closed.", "SketchBased: No faces found in this
direction", ...). One is stricter than FreeCAD: crossing or overlapping profile wires, which FreeCAD pads
into whatever the face maker makes of them (two overlapping squares pad to a solid of no volume), are an
error here, in the words FreeCAD uses when a face cannot be made from a sketch.

This module imports without build123d or OCP, so FreeCAD's own Python can read a FEATURES list and
to_freecad() can build it there.
"""
from __future__ import annotations

import ast
import copy
import importlib
import math
import operator

try:                                    # the kernel; FreeCAD's Python reads the vocabulary without it
    from OCP.BRep import BRep_Builder, BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepBuilderAPI import (BRepBuilderAPI_Copy, BRepBuilderAPI_DisconnectedWire,
                                    BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace,
                                    BRepBuilderAPI_MakeWire, BRepBuilderAPI_Transform)
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepClass import BRepClass_FaceClassifier
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.BRepFeat import BRepFeat_MakePrism
    from OCP.BRepGProp import BRepGProp
    from OCP.BRepIntCurveSurface import BRepIntCurveSurface_Inter
    from OCP.BRepLib import BRepLib_FindSurface
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.BRepProj import BRepProj_Projection
    from OCP.BRepTools import BRepTools
    from OCP.Bnd import Bnd_Box
    from OCP.GProp import GProp_GProps
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
    from OCP.GeomAbs import GeomAbs_Plane
    from OCP.GeomAdaptor import GeomAdaptor_Surface
    from OCP.Geom import Geom_Circle, Geom_Plane, Geom_TrimmedCurve
    from OCP.ShapeFix import ShapeFix_Shape, ShapeFix_ShapeTolerance
    from OCP.TopAbs import (TopAbs_COMPOUND, TopAbs_FACE, TopAbs_IN, TopAbs_ON,
                            TopAbs_OUT, TopAbs_SHAPE, TopAbs_SOLID, TopAbs_VERTEX, TopAbs_WIRE)
    from OCP.TopExp import TopExp
    from OCP.TopLoc import TopLoc_Location
    try:
        from OCP.TopTools import TopTools_IndexedMapOfShape, TopTools_ListOfShape
    except ImportError:                 # OCP 8 moved OCCT's collections
        from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedMapOfShape
        from OCP.collections import List_TopoDS_Shape as TopTools_ListOfShape
    from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Face, TopoDS_Iterator
    from OCP.gp import gp_Ax2, gp_Dir, gp_Lin, gp_Pln, gp_Pnt, gp_Pnt2d, gp_Trsf, gp_Vec
    from OCP.gce import gce_MakeDir, gce_MakeLin
except ImportError:                     # pragma: no cover - only FreeCAD's Python lands here
    pass


class FeatureError(ValueError):
    """A feature list FreeCAD would refuse too, worded as FreeCAD words it where it has words for it."""


# ── values: a number, or a PARAMS name or expression (FreeCAD's expression binding) ──────────────────

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.Mod: operator.mod, ast.USub: operator.neg, ast.UAdd: operator.pos}


def value(v, params: dict | None, where: str = "value") -> float:
    """A number as given, or a string evaluated over PARAMS: a name ("thick") or arithmetic ("width / 2")."""
    if isinstance(v, bool):
        raise FeatureError(f"{where}: {v!r} is not a number")
    if isinstance(v, (int, float)):
        return float(v)
    if not isinstance(v, str):
        raise FeatureError(f"{where}: {v!r} is not a number or the name of a PARAMS entry")
    params = params or {}
    try:
        tree = ast.parse(v.strip(), mode="eval")
    except SyntaxError:
        raise FeatureError(f"{where}: {v!r} is not an expression") from None

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            return float(n.value)
        if isinstance(n, ast.Name):
            if n.id not in params:
                raise FeatureError(f"{where}: PARAMS has no {n.id!r}")
            x = params[n.id]
            if isinstance(x, bool) or not isinstance(x, (int, float)):
                raise FeatureError(f"{where}: PARAMS[{n.id!r}] is {x!r}, not a number")
            return float(x)
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.operand))
        raise FeatureError(f"{where}: {v!r} can only use numbers, PARAMS names and + - * / ** %")
    return ev(tree)


def _xy(p, where):
    if not (isinstance(p, (tuple, list)) and len(p) == 2
            and all(isinstance(c, (int, float)) and not isinstance(c, bool) for c in p)):
        raise FeatureError(f"{where}: {p!r} is not a point (x, y)")
    return (float(p[0]), float(p[1]))


# ── geometry, as Part.LineSegment, Part.Circle, Part.ArcOfCircle and Part.Point ─────────────────────

class _Geometry:
    kind = ""
    construction = False

    def points(self) -> dict:
        """{position: (x, y)}: 1 start, 2 end, 3 centre, as Sketcher's PointPos."""
        raise NotImplementedError

    def as_dict(self) -> dict:
        raise NotImplementedError

    def __eq__(self, other):
        return type(self) is type(other) and self.as_dict() == other.as_dict()

    def __repr__(self):
        d = self.as_dict()
        d.pop("type")
        c = d.pop("construction")
        args = ", ".join(repr(tuple(v)) if isinstance(v, list) else repr(v) for v in d.values())
        return f"{self.kind}({args}{', construction=True' if c else ''})"


class LineSegment(_Geometry):
    kind = "LineSegment"

    def __init__(self, start, end, construction: bool = False):
        self.start, self.end = _xy(start, "LineSegment start"), _xy(end, "LineSegment end")
        self.construction = bool(construction)

    def points(self):
        return {1: self.start, 2: self.end}

    def as_dict(self):
        return {"type": self.kind, "start": list(self.start), "end": list(self.end),
                "construction": self.construction}


class Circle(_Geometry):
    kind = "Circle"

    def __init__(self, center, radius, construction: bool = False):
        self.center, self.radius = _xy(center, "Circle center"), float(radius)
        self.construction = bool(construction)

    def points(self):
        return {3: self.center}

    def as_dict(self):
        return {"type": self.kind, "center": list(self.center), "radius": self.radius,
                "construction": self.construction}


class ArcOfCircle(_Geometry):
    """An arc counter-clockwise from start_angle to end_angle (radians), as Part.ArcOfCircle."""
    kind = "ArcOfCircle"

    def __init__(self, center, radius, start_angle, end_angle, construction: bool = False):
        self.center, self.radius = _xy(center, "ArcOfCircle center"), float(radius)
        self.start_angle, self.end_angle = float(start_angle), float(end_angle)
        self.construction = bool(construction)

    def at(self, a):
        return (self.center[0] + self.radius * math.cos(a), self.center[1] + self.radius * math.sin(a))

    def points(self):
        return {1: self.at(self.start_angle), 2: self.at(self.end_angle), 3: self.center}

    def as_dict(self):
        return {"type": self.kind, "center": list(self.center), "radius": self.radius,
                "start_angle": self.start_angle, "end_angle": self.end_angle,
                "construction": self.construction}


class Point(_Geometry):
    kind = "Point"

    def __init__(self, point, construction: bool = False):
        self.point = _xy(point, "Point")
        self.construction = bool(construction)

    def points(self):
        return {1: self.point}

    def as_dict(self):
        return {"type": self.kind, "at": list(self.point), "construction": self.construction}


GEOMETRY = {g.kind: g for g in (LineSegment, Circle, ArcOfCircle, Point)}

# The conics and B-splines (Part.Ellipse, ArcOfEllipse, ArcOfHyperbola, ArcOfParabola, BSplineCurve) live in
# feature_curves.py, which adds them to GEOMETRY; _curves is its seam into the checks and the kernel below.
from . import feature_curves as _curves  # noqa: E402
try:
    from .feature_curves import ArcOfEllipse, ArcOfHyperbola, ArcOfParabola, BSplineCurve, Ellipse  # noqa: E402,F401
except ImportError:                     # feature_curves was imported first: it adds these names itself
    pass


def geometry_from_dict(d: dict) -> _Geometry:
    """The inverse of as_dict(), for what a solver hands back."""
    kind = d.get("type")
    c = bool(d.get("construction", False))
    if kind == "LineSegment":
        return LineSegment(d["start"], d["end"], c)
    if kind == "Circle":
        return Circle(d["center"], d["radius"], c)
    if kind == "ArcOfCircle":
        return ArcOfCircle(d["center"], d["radius"], d["start_angle"], d["end_angle"], c)
    if kind == "Point":
        return Point(d["at"] if "at" in d else d["point"], c)
    if kind in _curves.GEOMETRY:
        return _curves.from_dict(d)
    raise FeatureError(f"unknown geometry type {kind!r}")


# ── constraints, as Sketcher.Constraint ───────────────────────────────────────────────────────────────

# The types with a value, and the argument counts (value included) each accepts.
DIMENSIONAL = {"Distance": (2, 4, 5), "DistanceX": (2, 3, 5), "DistanceY": (2, 3, 5), "Radius": (2,),
               "Diameter": (2,), "Angle": (2, 3, 5), "Weight": (2,), "SnellsLaw": (7,)}
GEOMETRIC = {"Coincident": (4,), "Horizontal": (1, 4), "Vertical": (1, 4), "Parallel": (2,),
             "Perpendicular": (2, 3, 4), "Tangent": (2, 3, 4), "Equal": (2,), "PointOnObject": (3,),
             "Symmetric": (5, 6), "Block": (1,), "InternalAlignment": (3, 4, 5)}


class Constraint:
    """Sketcher.Constraint(type, *args): FreeCAD's argument lists, a value last on dimensional ones.
    name and driving are SketchObject's Name and Driving (a reference dimension has driving=False)."""

    def __init__(self, type: str, *args, name: str | None = None, driving: bool = True):
        aligned = _curves.alignment_counts(type)          # "InternalAlignment:EllipseMajorDiameter", ...
        if type not in DIMENSIONAL and type not in GEOMETRIC and aligned is None:
            raise FeatureError(f"Constraint type {type!r} is not one of "
                               f"{', '.join(sorted({**DIMENSIONAL, **GEOMETRIC}))}")
        counts = DIMENSIONAL.get(type) or GEOMETRIC.get(type) or aligned
        if len(args) not in counts:
            raise FeatureError(f"Constraint {type!r} takes {' or '.join(map(str, counts))} arguments, "
                               f"not {len(args)}: {args!r}")
        self.type, self.name, self.driving = type, name, bool(driving)
        if type in DIMENSIONAL:
            self.args, self.value = tuple(args[:-1]), args[-1]
        else:
            self.args, self.value = tuple(args), None
        for a in self.args:
            if isinstance(a, bool) or not isinstance(a, int):
                raise FeatureError(f"Constraint {type!r}: {a!r} is not a geometry index or point position")

    @property
    def dimensional(self) -> bool:
        return self.type in DIMENSIONAL

    def resolved(self, params) -> float | None:
        """The value in FreeCAD's internal units: mm, or radians for an angle. A string is an expression
        over PARAMS, and for an angle it is in degrees, as a unitless FreeCAD expression is."""
        if self.value is None:
            return None
        v = value(self.value, params, f"Constraint {self.type!r}")
        if self.type == "Angle" and isinstance(self.value, str):
            v = math.radians(v)
        return v

    def __repr__(self):
        args = [repr(self.type), *map(repr, self.args)] + ([repr(self.value)] if self.dimensional else [])
        if self.name:
            args.append(f"name={self.name!r}")
        if not self.driving:
            args.append("driving=False")
        return f"Constraint({', '.join(args)})"


# ── the sketch ────────────────────────────────────────────────────────────────────────────────────────

# FreeCAD's origin planes as a FlatFace sketch takes them: (sketch x, sketch y, normal) in global axes.
PLANES = {
    "XY": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    "XZ": ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, -1.0, 0.0)),
    "YZ": ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0)),
}


def _plane_key(support) -> str:
    key = support[:-6] if isinstance(support, str) and support.endswith("_Plane") else support
    if key not in PLANES:
        raise FeatureError(f"support {support!r} is not one of XY, XZ, YZ (FreeCAD's XY_Plane, XZ_Plane, "
                           "YZ_Plane); a sketch on a face is not supported yet")
    return key


def _ypr(yaw, pitch, roll):
    """App.Rotation(yaw, pitch, roll) in degrees: Rz(yaw) Ry(pitch) Rx(roll), as a 3x3 row matrix."""
    y, p, r = (math.radians(a) for a in (yaw, pitch, roll))
    cy, sy, cp, sp, cr, sr = math.cos(y), math.sin(y), math.cos(p), math.sin(p), math.cos(r), math.sin(r)
    return ((cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr),
            (sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr),
            (-sp, cp * sr, cp * cr))


def _matmul(a, b):
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3))


def _matvec(a, v):
    return tuple(sum(a[i][k] * v[k] for k in range(3)) for i in range(3))


class Sketch:
    """Sketcher::SketchObject. geometry holds the solved coordinates, as the SketchObject's Geometry property
    does. It is attached as AttachExtension attaches it (cad_agent/feature_attach.py): support="XY" (or "XZ",
    "YZ") is FlatFace on that origin plane, the form every sketch had before faces could be supports;
    attachment_support=[("Pad", "Face6")] with map_mode, attachment_offset, map_reversed and map_path_parameter is
    FreeCAD's whole set, and map_mode="Deactivated" with placement=((x, y, z), (yaw, pitch, roll)) a sketch placed
    by hand. external_geometry=[("Pad", "Edge3"), ...] is ExternalGeometry: the edges and vertices projected onto
    the sketch, GeoId -3, -4, ... in its constraints."""
    kind = "Sketch"
    engine = "Plane"

    def __init__(self, name: str, support: str | None = None, geometry=(), constraints=(), *,
                 attachment_offset=None, map_mode: str | None = None, plane: str | None = None,
                 attachment_support=None, map_reversed: bool = False, map_path_parameter=0.0,
                 placement=None, external_geometry=None):
        from .feature_attach import Attachable, external_list
        self.name = name
        sup = plane if plane is not None else support
        if sup is not None and attachment_support is not None:
            raise FeatureError(f"Sketch {name}: give support or attachment_support, not both")
        if sup is None and attachment_support is None and map_mode in (None, "FlatFace"):
            sup = "XY"                                  # Sketch(name): on the XY plane, as before
        if sup is not None:
            attachment_support = [(_plane_key(sup) + "_Plane", "")]
        Attachable.init_attachment(self, f"Sketch {name}", attachment_support, map_mode, attachment_offset,
                                   map_reversed, map_path_parameter, placement, default_mode="FlatFace")
        # support: the origin plane of a plain FlatFace sketch (the form PLANES places without the engine)
        one = self.attachment_support[0] if len(self.attachment_support) == 1 else None
        self.support = one[0][:-6] if (one and one[1] == "" and one[0][:-6] in PLANES and one[0].endswith("_Plane")
                                       and self.map_mode == "FlatFace" and not self.map_reversed) else None
        self.external_geometry = external_list(f"Sketch {name}", external_geometry)
        self._placed = None                             # the Placement the Body attached it at (attacher.Placement)
        self._external = []                             # ExternalGeo after the axes, as geometry dicts
        self.geometry = list(geometry)
        self.constraints = list(constraints)
        for i, g in enumerate(self.geometry):
            if not isinstance(g, _Geometry):
                raise FeatureError(f"Sketch {name}: geometry {i} is {g!r}, not LineSegment, Circle, "
                                   "ArcOfCircle or Point")
        for i, c in enumerate(self.constraints):
            if not isinstance(c, Constraint):
                raise FeatureError(f"Sketch {name}: constraint {i} is {c!r}, not a Constraint")
        self.attachment_offset = attachment_offset
        self._offset = self._parse_offset(attachment_offset)

    def _parse_offset(self, off):
        if off is None:
            return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
        try:
            if len(off) == 3 and all(isinstance(c, (int, float)) for c in off):
                return tuple(float(c) for c in off), (0.0, 0.0, 0.0)
            pos, ypr = off
            return tuple(float(c) for c in pos), tuple(float(c) for c in ypr)
        except (TypeError, ValueError):
            raise FeatureError(f"Sketch {self.name}: attachment_offset {off!r} is not (x, y, z) or "
                               "((x, y, z), (yaw, pitch, roll))") from None

    def placement(self):
        """(origin, 3x3 rotation whose columns are the sketch's x, y and normal) in global coordinates: where the
        Body attached it, or, for a plain sketch on an origin plane, where that plane puts it."""
        if self._placed is not None:
            return self._placed.pos, self._placed.rot.matrix()
        if self.support is None:
            if self.map_mode == "Deactivated" or not self.attachment_support:
                return self._own_pl.pos, self._own_pl.rot.matrix()
            raise FeatureError(f"Sketch {self.name}: its placement comes from {self.attachment_support[0][0]}, "
                               "so it is known once the Body is built")
        ex, ey, ez = PLANES[self.support]
        base = tuple(tuple(col[i] for col in (ex, ey, ez)) for i in range(3))
        pos, ypr = self._offset
        return _matvec(base, pos), _matmul(base, _ypr(*ypr))

    def normal(self):
        return tuple(r[2] for r in self.placement()[1])

    def placed(self, placement, external=()) -> "Sketch":
        """This sketch where the Body attached it (an attacher.Placement), with its external geometry."""
        s = copy.copy(self)
        s._placed = placement
        s._external = list(external)
        return s

    def as_dict(self, params=None) -> dict:
        """The sketch as cad_agent.planegcs.solve() takes it: geometry as stored, constraints with their
        values resolved to mm and radians, and the external geometry after the axes."""
        out = {"name": self.name,
               "geometry": [g.as_dict() for g in self.geometry],
               "constraints": [{"type": c.type, "args": list(c.args),
                                **({"value": c.resolved(params)} if c.dimensional else {}),
                                "driving": c.driving, "name": c.name or ""}
                               for c in self.constraints]}
        if self._external:
            out["external"] = list(self._external)
        return out

    def unsatisfied(self, params=None, tol: float = 1e-7, unchecked: bool = True) -> list[str]:
        """The constraints the stored geometry does not satisfy, as 'constraint i (type): why'; empty
        when none. A constraint this module cannot check (an InternalAlignment, a tangent at a point of
        a circle) counts as unsatisfied unless unchecked=False: only the solver can say."""
        out = []
        for i, c in enumerate(self.constraints):
            if not c.driving:
                continue
            why = _residual(self, c, c.resolved(params), tol)
            if why == "unsupported":
                why = "cannot be checked without the solver" if unchecked else ""
            if why:
                out.append(f"constraint {i} ({c.type}): {why}")
        if unchecked:
            out += _curves.unsolved(self)           # geometry FreeCAD's solve changes before it solves
        return out

    def solved(self, params=None) -> "Sketch":
        """This sketch with geometry that satisfies its constraints: itself when it already does, else
        what the solver makes of it."""
        bad = self.unsatisfied(params)
        if not bad:
            return self
        out = _solve(self.as_dict(params), reason="; ".join(bad))
        geometry = [geometry_from_dict(g) for g in out["geometry"]]
        if len(geometry) != len(self.geometry):
            raise FeatureError(f"Sketch {self.name}: the solver returned {len(geometry)} geometries "
                               f"for {len(self.geometry)}")
        s = copy.copy(self)                         # the same attachment, placement and external geometry
        s.geometry = geometry
        still = s.unsatisfied(params, tol=1e-6, unchecked=False)
        if still:
            raise FeatureError(f"Sketch {self.name}: the solver's result still misses "
                               + "; ".join(still))
        return s

    def references(self) -> list[str]:
        """The objects it is attached to and takes external geometry from."""
        return [o for o, _ in self.attachment_support] + [o for o, _ in self.external_geometry]

    def __repr__(self):
        return f"Sketch({self.name!r}, support={self.support!r}, {len(self.geometry)} geometries, " \
               f"{len(self.constraints)} constraints)"


def _solve(sketch: dict, reason: str = "") -> dict:
    """The one seam to FreeCAD's PlaneGCS: cad_agent.planegcs.solve(sketch) -> dict.

    It takes Sketch.as_dict(): {"name", "geometry": [{"type": "LineSegment", "start": [x, y], "end": [x, y]},
    {"type": "Circle", "center": [x, y], "radius": r}, {"type": "ArcOfCircle", "center", "radius",
    "start_angle", "end_angle"}, {"type": "Point", "at": [x, y]}, each with "construction"], "constraints":
    [{"type": "DistanceX", "args": [0, 1, 0, 2], "value": 40.0, "driving": True, "name": ""}, ...]} (the
    argument list after the type as Sketcher.Constraint takes it, the value apart and resolved to mm or
    radians), and returns {"status": "solved" | "failed" | "conflicting" | "redundant" | "malformed",
    "geometry": [the same form], "dof", "conflicting", "redundant", "partially_redundant", "malformed"}
    (constraint indices from 0). Anything but "solved" is reported as SketchObject::execute words it."""
    try:                    # by name, so a stand-in in sys.modules wins over an already imported module
        planegcs = importlib.import_module("cad_agent.planegcs")
    except ImportError as e:
        raise FeatureError(
            f"Sketch {sketch.get('name')}: its stored geometry does not satisfy its constraints "
            f"({reason}), so it must be re-solved, and cad_agent.planegcs (FreeCAD's PlaneGCS) is not "
            "installed") from e
    out = planegcs.solve(sketch)
    status = out.get("status")
    if status != "solved":
        words = {"failed": "Solving the sketch failed", "conflicting": "Sketch with conflicting constraints",
                 "redundant": "Sketch with redundant constraints",
                 "malformed": "Sketch with malformed constraints"}.get(status, f"Solving the sketch: {status}")
        which = out.get(status) if isinstance(out.get(status), list) else None
        if which:
            words += " (constraints " + ", ".join(str(i) for i in which) + ")"
        raise FeatureError(f"Sketch {sketch.get('name')}: {words}")
    return out


# The geometric check of a constraint against stored geometry: '' when it holds, else why not.

def _pt(sk: Sketch, g: int, pos: int):
    if g == -1:
        if pos != 1:
            raise FeatureError("the H axis (-1) has only point 1, the origin")
        return (0.0, 0.0)
    if g <= -3:
        try:
            return _external(sk, g).points()[pos]
        except KeyError:
            raise FeatureError(f"Sketch {sk.name}: external geometry {g} has no point {pos}") from None
    if g < 0:
        raise FeatureError(f"geometry {g} has no point {pos}")
    try:
        return sk.geometry[g].points()[pos]
    except IndexError:
        raise FeatureError(f"Sketch {sk.name}: there is no geometry {g}") from None
    except KeyError:
        raise FeatureError(f"Sketch {sk.name}: geometry {g} ({sk.geometry[g].kind}) has no point "
                           f"{pos}") from None


def _external(sk: Sketch, g: int):
    """External geometry -3, -4, ...: the projections the Body made for the sketch (Sketch.placed)."""
    i = -g - 3
    ext = getattr(sk, "_external", None) or []
    if i >= len(ext):
        raise FeatureError(f"Sketch {sk.name}: there is no external geometry {g} (it has {len(ext)}"
                           + ("" if ext else "; external geometry is projected when the Body is built") + ")")
    return geometry_from_dict(ext[i])


def _geo(sk: Sketch, g: int):
    """A LineSegment, Circle, ArcOfCircle or Point; the axes as infinite lines through the origin."""
    if g == -1:
        return LineSegment((0.0, 0.0), (1.0, 0.0))
    if g == -2:
        return LineSegment((0.0, 0.0), (0.0, 1.0))
    if g <= -3:
        return _external(sk, g)
    if g < 0 or g >= len(sk.geometry):
        raise FeatureError(f"Sketch {sk.name}: there is no geometry {g}")
    return sk.geometry[g]


def _dir(line):
    dx, dy = line.end[0] - line.start[0], line.end[1] - line.start[1]
    n = math.hypot(dx, dy)
    return (dx / n, dy / n) if n else (0.0, 0.0)


def _line_dist(p, line):
    d = _dir(line)
    return (p[0] - line.start[0]) * d[1] - (p[1] - line.start[1]) * d[0]   # signed, left negative


def _angle_diff(a, b):
    return abs((a - b + math.pi) % (2 * math.pi) - math.pi)


def _tangent_at(g, pos):
    """The unit tangent of g at point pos, along increasing parameter."""
    if isinstance(g, LineSegment):
        return _dir(g)
    if isinstance(g, ArcOfCircle):
        a = g.start_angle if pos == 1 else g.end_angle
        return (-math.sin(a), math.cos(a))
    if isinstance(g, _curves.CURVES):
        return _curves.tangent_at(g, pos)
    return None


def _residual(sk: Sketch, c: Constraint, v, tol) -> str:
    t, a = c.type, c.args

    def off(measured, wanted, unit="mm"):
        return "" if abs(measured - wanted) <= tol else f"is {measured:.9g} {unit}, wants {wanted:.9g}"

    try:
        why = _curves.residual(sk, c, v, tol, _geo, _pt)    # conics, B-splines, internal alignments
        if why is not None:
            return why
        if t == "Coincident":
            p, q = _pt(sk, a[0], a[1]), _pt(sk, a[2], a[3])
            return off(math.dist(p, q), 0.0)
        if t in ("Horizontal", "Vertical"):
            k = 1 if t == "Horizontal" else 0
            if len(a) == 1:
                g = _geo(sk, a[0])
                if not isinstance(g, LineSegment):
                    return "unsupported"
                p, q = g.start, g.end
            else:
                p, q = _pt(sk, a[0], a[1]), _pt(sk, a[2], a[3])
            return off(q[k] - p[k], 0.0)
        if t in ("Parallel", "Perpendicular") and len(a) == 2:
            g1, g2 = _geo(sk, a[0]), _geo(sk, a[1])
            if not (isinstance(g1, LineSegment) and isinstance(g2, LineSegment)):
                return "unsupported"
            d1, d2 = _dir(g1), _dir(g2)
            m = d1[0] * d2[1] - d1[1] * d2[0] if t == "Parallel" else d1[0] * d2[0] + d1[1] * d2[1]
            return off(m, 0.0, "")
        if t == "Equal":
            g1, g2 = _geo(sk, a[0]), _geo(sk, a[1])
            if isinstance(g1, LineSegment) and isinstance(g2, LineSegment):
                return off(math.dist(g2.start, g2.end), math.dist(g1.start, g1.end))
            if isinstance(g1, (Circle, ArcOfCircle)) and isinstance(g2, (Circle, ArcOfCircle)):
                return off(g2.radius, g1.radius)
            return "unsupported"
        if t == "PointOnObject":
            p, g = _pt(sk, a[0], a[1]), _geo(sk, a[2])
            if isinstance(g, LineSegment):
                return off(_line_dist(p, g), 0.0)
            if isinstance(g, (Circle, ArcOfCircle)):
                return off(math.dist(p, g.center), g.radius)
            return "unsupported"
        if t == "Tangent":
            if len(a) == 2:
                g1, g2 = _geo(sk, a[0]), _geo(sk, a[1])
                if isinstance(g2, LineSegment) and not isinstance(g1, LineSegment):
                    g1, g2 = g2, g1
                if isinstance(g1, LineSegment) and isinstance(g2, (Circle, ArcOfCircle)):
                    return off(abs(_line_dist(g2.center, g1)), g2.radius)
                if isinstance(g1, (Circle, ArcOfCircle)) and isinstance(g2, (Circle, ArcOfCircle)):
                    d = math.dist(g1.center, g2.center)
                    return off(min(abs(d - g1.radius - g2.radius), abs(d - abs(g1.radius - g2.radius))), 0.0)
                return "unsupported"
            if len(a) == 4:                       # endpoint to endpoint: coincident, and smooth
                p, q = _pt(sk, a[0], a[1]), _pt(sk, a[2], a[3])
                t1, t2 = _tangent_at(_geo(sk, a[0]), a[1]), _tangent_at(_geo(sk, a[2]), a[3])
                if t1 is None or t2 is None:
                    return "unsupported"
                why = off(math.dist(p, q), 0.0)
                return why or off(t1[0] * t2[1] - t1[1] * t2[0], 0.0, "")
            return "unsupported"
        if t == "Symmetric":
            p, q = _pt(sk, a[0], a[1]), _pt(sk, a[2], a[3])
            mid = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
            if len(a) == 6:
                return off(math.dist(mid, _pt(sk, a[4], a[5])), 0.0)
            g = _geo(sk, a[4])
            if not isinstance(g, LineSegment):
                return "unsupported"
            d = _dir(g)
            return off(_line_dist(mid, g), 0.0) or off((q[0] - p[0]) * d[0] + (q[1] - p[1]) * d[1], 0.0)
        if t == "Block":
            return ""
        if t in ("DistanceX", "DistanceY"):
            k = 0 if t == "DistanceX" else 1
            if len(a) == 1:
                g = _geo(sk, a[0])
                if not isinstance(g, LineSegment):
                    return "unsupported"
                return off(g.end[k] - g.start[k], v)
            if len(a) == 2:
                return off(_pt(sk, a[0], a[1])[k], v)
            return off(_pt(sk, a[2], a[3])[k] - _pt(sk, a[0], a[1])[k], v)
        if t == "Distance":
            if len(a) == 1:
                g = _geo(sk, a[0])
                if not isinstance(g, LineSegment):
                    return "unsupported"
                return off(math.dist(g.start, g.end), v)
            if len(a) == 3:
                p, g = _pt(sk, a[0], a[1]), _geo(sk, a[2])
                if isinstance(g, LineSegment):
                    return off(abs(_line_dist(p, g)), v)
                if isinstance(g, (Circle, ArcOfCircle)):
                    return off(abs(math.dist(p, g.center) - g.radius), v)
                return "unsupported"
            return off(math.dist(_pt(sk, a[0], a[1]), _pt(sk, a[2], a[3])), v)
        if t in ("Radius", "Diameter"):
            g = _geo(sk, a[0])
            if not isinstance(g, (Circle, ArcOfCircle)):
                return "unsupported"
            return off(g.radius * (2 if t == "Diameter" else 1), v)
        if t == "Angle":
            if len(a) == 1:
                g = _geo(sk, a[0])
                if isinstance(g, LineSegment):
                    d = _dir(g)
                    m = math.atan2(d[1], d[0])
                elif isinstance(g, ArcOfCircle):
                    m = g.end_angle - g.start_angle
                else:
                    return "unsupported"
                return "" if _angle_diff(m, v) <= tol else f"is {m:.9g} rad, wants {v:.9g}"
            if len(a) == 2:
                g1, g2 = _geo(sk, a[0]), _geo(sk, a[1])
                if not (isinstance(g1, LineSegment) and isinstance(g2, LineSegment)):
                    return "unsupported"
                d1, d2 = _dir(g1), _dir(g2)
                m = math.atan2(d1[0] * d2[1] - d1[1] * d2[0], d1[0] * d2[0] + d1[1] * d2[1])
                return "" if _angle_diff(m, v) <= tol else f"is {m:.9g} rad, wants {v:.9g}"
            return "unsupported"
    except FeatureError:
        raise
    return "unsupported"


# ── Pad and Pocket ────────────────────────────────────────────────────────────────────────────────────

SIDE_TYPES = ("One side", "Two sides", "Symmetric")
START_TYPES = ("Profile plane", "Offset")


class _Extrude:
    kind = ""
    TYPES: tuple = ()
    LENGTH = 10.0

    def __init__(self, name: str, profile: str, *, side_type: str = "One side", type: str = "Length",
                 type2: str = "Length", length=None, length2=None, offset=0.0, offset2=0.0,
                 reversed: bool = False, midplane: bool = False, up_to_face=None, up_to_face2=None,
                 up_to_shape=None, up_to_shape2=None, use_custom_vector: bool = False,
                 direction=(1.0, 1.0, 1.0), along_sketch_normal: bool = True,
                 start_type: str = "Profile plane", start_offset=0.0, taper_angle=0.0, taper_angle2=0.0,
                 refine: bool = True):
        self.name, self.profile = name, profile
        if type == "TwoLengths":
            # FeatureExtrude::onDocumentRestored: the deprecated TwoLengths is SideType "Two sides".
            # Its old Length along the direction and Length2 against it is what Two sides builds.
            type, side_type = "Length", "Two sides"
        if midplane:
            # FeatureExtrude::onChanged: Midplane is deprecated, SideType Symmetric replaces it.
            side_type = "Symmetric"
        if side_type not in SIDE_TYPES:
            raise FeatureError(f"{name}: side_type {side_type!r} is not one of {', '.join(SIDE_TYPES)}")
        for k, t in (("type", type), ("type2", type2)):
            if t not in self.TYPES:
                raise FeatureError(f"{name}: {k} {t!r} is not one of {', '.join(self.TYPES)} "
                                   f"(PartDesign::{self.kind}'s Type)")
        if start_type not in START_TYPES:
            raise FeatureError(f"{name}: start_type {start_type!r} is not supported, only "
                               f"{', '.join(START_TYPES)}")
        self.side_type, self.type, self.type2 = side_type, type, type2
        self.length = self.LENGTH if length is None else length
        self.length2 = self.LENGTH if length2 is None else length2
        self.offset, self.offset2 = offset, offset2
        self.reversed, self.midplane = bool(reversed), side_type == "Symmetric"
        self.up_to_face, self.up_to_face2 = up_to_face, up_to_face2
        self.up_to_shape, self.up_to_shape2 = up_to_shape, up_to_shape2
        self.use_custom_vector, self.direction = bool(use_custom_vector), tuple(direction)
        self.along_sketch_normal = bool(along_sketch_normal)
        self.start_type, self.start_offset = start_type, start_offset
        if taper_angle or taper_angle2:
            raise FeatureError(f"{name}: a taper angle is not supported yet")
        self.taper_angle, self.taper_angle2 = 0.0, 0.0
        self.refine = bool(refine)

    def __repr__(self):
        return f"{self.kind}({self.name!r}, {self.profile!r}, side_type={self.side_type!r}, " \
               f"type={self.type!r}, length={self.length!r})"


class Pad(_Extrude):
    """PartDesign::Pad: adds the profile's prism to the body. Length 10 mm by default, as FreeCAD's."""
    kind = "Pad"
    TYPES = ("Length", "UpToLast", "UpToFirst", "UpToFace", "UpToShape")
    LENGTH = 10.0


class Pocket(_Extrude):
    """PartDesign::Pocket: cuts the profile's prism from the body, against the sketch's normal unless
    reversed. Length 5 mm by default, as FreeCAD's."""
    kind = "Pocket"
    TYPES = ("Length", "ThroughAll", "UpToFirst", "UpToFace", "UpToShape")
    LENGTH = 5.0


FEATURES = {"Sketch": Sketch, "Pad": Pad, "Pocket": Pocket}
# More features register themselves at the end of this file, one module per area.


# ── the kernel: what FreeCAD's C++ does, in the same OCCT calls ───────────────────────────────────────

CONFUSION = 1e-7          # Precision::Confusion()


def _faces(shape) -> list:
    """The faces in TopExp::MapShapes order: FreeCAD's Face1, Face2, ..."""
    m = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_FACE, m)
    return [TopoDS.Face(m.FindKey(i)) for i in range(1, m.Extent() + 1)]


def _subs(shape, kind) -> list:
    m = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, kind, m)
    return [m.FindKey(i) for i in range(1, m.Extent() + 1)]


def _count(shape, kind) -> int:
    if shape is None or shape.IsNull():
        return 0
    return len(_subs(shape, kind))


def _trsf(sketch: Sketch):
    (ox, oy, oz), r = sketch.placement()
    t = gp_Trsf()
    t.SetValues(r[0][0], r[0][1], r[0][2], ox, r[1][0], r[1][1], r[1][2], oy, r[2][0], r[2][1], r[2][2], oz)
    return t


def _edge(g):
    """Part::Geometry::toShape(): the edge of a sketch geometry, in the sketch's own plane."""
    z = gp_Dir(0, 0, 1)
    if isinstance(g, _curves.CURVES):
        return _curves.edge(g)
    if isinstance(g, LineSegment):
        return BRepBuilderAPI_MakeEdge(gp_Pnt(*g.start, 0), gp_Pnt(*g.end, 0)).Edge()
    circ = Geom_Circle(gp_Ax2(gp_Pnt(*g.center, 0), z, gp_Dir(1, 0, 0)), g.radius)
    if isinstance(g, Circle):
        return BRepBuilderAPI_MakeEdge(circ).Edge()
    a0, a1 = g.start_angle, g.end_angle
    while a1 < a0:                        # Part.ArcOfCircle: counter-clockwise from a0 to a1
        a1 += 2 * math.pi
    return BRepBuilderAPI_MakeEdge(Geom_TrimmedCurve(circ, a0, a1)).Edge()


def _fix(shape):
    """TopoShape::fix(): ShapeFix_Shape, kept only when what it makes is valid."""
    f = ShapeFix_Shape(BRepBuilderAPI_Copy(shape).Shape())
    f.Perform()
    if not BRepCheck_Analyzer(f.Shape()).IsValid():
        return shape
    f = ShapeFix_Shape(shape)
    f.Perform()
    return f.Shape() if BRepCheck_Analyzer(f.Shape()).IsValid() else shape


def _wires(edges) -> list:
    """TopoShape::makeElementWires (mergeWithTolerance): each wire grows from the first edge left by
    adding whichever edge connects next, in list order, until none does."""
    left, wires = list(edges), []
    while left:
        mk = BRepBuilderAPI_MakeWire()
        mk.Add(left.pop(0))
        wire = mk.Wire()                   # the wire as it was after the last edge that joined
        found = True
        while found:
            found = False
            for i, e in enumerate(left):
                mk.Add(e)
                if mk.Error() != BRepBuilderAPI_DisconnectedWire:
                    left.pop(i)
                    found = True
                    wire = mk.Wire()
                    break
        wires.append(TopoDS.Wire(_fix(wire)))
    return wires


def _wire_direction(pln, wire) -> int:
    """FaceMakerBullseye::FaceDriller::getWireDirection: +1 counter-clockwise about the plane's normal."""
    face = BRepBuilderAPI_MakeFace(pln, wire, True).Face()
    it = TopoDS_Iterator(face, False)
    return 1 if it.Value().Orientation() == wire.Orientation() else -1


class _Driller:
    """FaceMakerBullseye::FaceDriller, without reuseInnerWire (Bullseye's own setting)."""

    def __init__(self, pln, outer):
        self.pln = pln
        if _wire_direction(pln, outer) < 0:
            outer = TopoDS.Wire(outer.Reversed())
        self.hplane = Geom_Plane(pln)
        self.face = TopoDS_Face()
        b = BRep_Builder()
        b.MakeFace(self.face, self.hplane, CONFUSION)
        b.Add(self.face, outer)
        self.bound = None

    def _has_vertex(self, shape, vertex):
        return any(v.IsSame(vertex) for v in _subs(shape, TopAbs_VERTEX))

    def hit_test(self, wire) -> str:
        vertex = TopoDS.Vertex(_subs(wire, TopAbs_VERTEX)[0])
        if self.bound is not None:
            if self._has_vertex(self.bound, vertex):
                return "none"
        elif self._has_vertex(self.face, vertex):
            return "none"
        tol = BRep_Tool.Tolerance_s(vertex)
        proj = GeomAPI_ProjectPointOnSurf(BRep_Tool.Pnt_s(vertex), self.hplane)
        u, v = proj.LowerDistanceParameters()
        hit = "none"
        if self.bound is not None:
            st = BRepClass_FaceClassifier(self.bound, gp_Pnt2d(u, v), tol).State()
            if st in (TopAbs_OUT, TopAbs_ON):
                return "none"
            if st != TopAbs_IN:
                raise FeatureError("FaceMakerBullseye::FaceDriller::hitTest: result unknown")
            hit = "outer"
        st = BRepClass_FaceClassifier(self.face, gp_Pnt2d(u, v), tol).State()
        if st == TopAbs_IN:
            return "hit"
        if st == TopAbs_ON:
            return "hit" if hit == "outer" else "none"
        if st == TopAbs_OUT:
            return hit
        raise FeatureError("FaceMakerBullseye::FaceDriller::hitTest: result unknown")

    def add_hole(self, w):
        if _wire_direction(self.pln, w) > 0:
            w = TopoDS.Wire(w.Reversed())
        if self.bound is None:
            outer = TopoDS.Wire(_subs(self.face, TopAbs_WIRE)[0])
            self.bound = BRepBuilderAPI_MakeFace(self.hplane, outer).Face()
        BRep_Builder().Add(self.face, w)


def _bullseye(wires):
    """FaceMakerBullseye::Build_Essence, then TopoShape::makeElementFace's repair of an invalid result."""
    if not wires:
        return None
    for w in wires:
        if not BRep_Tool.IsClosed_s(w):
            raise FeatureError("Wire is not closed.")
    comp = TopoDS_Compound()
    b = BRep_Builder()
    b.MakeCompound(comp)
    for w in wires:
        b.Add(comp, BRepBuilderAPI_Copy(w).Shape())
    finder = BRepLib_FindSurface(comp, -1, True)
    if not finder.Found():
        raise FeatureError("Wires are not coplanar")
    pln = GeomAdaptor_Surface(finder.Surface()).Plane()
    infos = []
    for w in wires:
        box = Bnd_Box()
        BRepBndLib.AddOptimal_s(w, box, False)
        if not box.IsVoid():
            infos.append((math.sqrt(box.SquareExtent()), w))
    # std::stable_sort with a < b when a's extent is larger by more than Confusion: largest first
    infos = _stable_sort_desc(infos)
    faces = []
    for _, w in infos:
        found = None
        for f in reversed(faces):          # no early exit: the first face in the list that is hit wins
            if f.hit_test(w) == "hit":
                found = f
        if found is not None:
            found.add_hole(w)
        else:
            faces.append(_Driller(pln, w))
    shapes = [f.face for f in faces]
    if len(shapes) == 1:
        result = shapes[0]
    else:
        result = TopoDS_Compound()
        b.MakeCompound(result)
        for s in shapes:
            b.Add(result, s)
    if not BRepCheck_Analyzer(result).IsValid():
        ShapeFix_ShapeTolerance().LimitTolerance(result, CONFUSION, CONFUSION, TopAbs_SHAPE)
        fx = ShapeFix_Shape(result)
        fx.Perform()
        result = fx.Shape()
    return result


def _stable_sort_desc(infos):
    out = []
    for item in infos:                     # insertion sort: stable, and Confusion-tolerant as FreeCAD's
        i = len(out)
        while i > 0 and item[0] - out[i - 1][0] > CONFUSION:
            i -= 1
        out.insert(i, item)
    return out


# Crossing wires: FreeCAD makes some face of them; here they are an error.

OVERLAP = "overlap"


def _on_arc(g, p, eps=1e-9):
    if isinstance(g, Circle):
        return True
    a = math.atan2(p[1] - g.center[1], p[0] - g.center[0])
    span = (g.end_angle - g.start_angle) % (2 * math.pi) or 2 * math.pi
    return (a - g.start_angle) % (2 * math.pi) <= span + eps or \
        (a - g.start_angle) % (2 * math.pi) >= 2 * math.pi - eps


def _on_seg(g, p, eps=1e-9):
    d = math.dist(g.start, g.end)
    if not d:
        return False
    along = ((p[0] - g.start[0]) * (g.end[0] - g.start[0]) + (p[1] - g.start[1]) * (g.end[1] - g.start[1])) / d
    return -eps <= along <= d + eps


def _intersections(g1, g2):
    """The points where two sketch curves meet (tangent contacts too), or OVERLAP when they share a
    stretch of curve."""
    if isinstance(g1, _curves.CURVES) or isinstance(g2, _curves.CURVES):
        return _curves.intersections(g1, g2, _edge, OVERLAP)
    if isinstance(g1, LineSegment) and isinstance(g2, LineSegment):
        p, r = g1.start, (g1.end[0] - g1.start[0], g1.end[1] - g1.start[1])
        q, s = g2.start, (g2.end[0] - g2.start[0], g2.end[1] - g2.start[1])
        den = r[0] * s[1] - r[1] * s[0]
        qp = (q[0] - p[0], q[1] - p[1])
        lr, ls = math.hypot(*r), math.hypot(*s)
        if abs(den) <= 1e-12 * lr * ls:
            if abs(qp[0] * r[1] - qp[1] * r[0]) > 1e-9 * lr:
                return []                                       # parallel, apart
            ts = sorted(((x[0] - p[0]) * r[0] + (x[1] - p[1]) * r[1]) / lr for x in (g2.start, g2.end))
            lo, hi = max(ts[0], 0.0), min(ts[1], lr)
            if hi - lo > 1e-7:
                return OVERLAP
            return [x for x in (g2.start, g2.end) if _on_seg(g1, x)]
        t = (qp[0] * s[1] - qp[1] * s[0]) / den
        u = (qp[0] * r[1] - qp[1] * r[0]) / den
        if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
            return [(p[0] + t * r[0], p[1] + t * r[1])]
        return []
    if isinstance(g1, LineSegment) or isinstance(g2, LineSegment):
        line, c = (g1, g2) if isinstance(g1, LineSegment) else (g2, g1)
        d = _dir(line)
        f = (line.start[0] - c.center[0], line.start[1] - c.center[1])
        bq = f[0] * d[0] + f[1] * d[1]
        disc = bq * bq - (f[0] ** 2 + f[1] ** 2 - c.radius ** 2)
        if disc < -1e-9:
            return []
        roots = {-bq} if abs(disc) <= 1e-12 else {-bq - math.sqrt(max(disc, 0.0)), -bq + math.sqrt(max(disc, 0.0))}
        pts = [(line.start[0] + t * d[0], line.start[1] + t * d[1]) for t in roots]
        return [p for p in pts if _on_seg(line, p) and _on_arc(c, p)]
    d = math.dist(g1.center, g2.center)
    if d <= 1e-9 and abs(g1.radius - g2.radius) <= 1e-9:          # one circle: do the arcs share a stretch?
        if isinstance(g1, Circle) or isinstance(g2, Circle):
            return OVERLAP
        for a, b in ((g1, g2), (g2, g1)):
            span = (a.end_angle - a.start_angle) % (2 * math.pi) or 2 * math.pi
            for k in range(1, 8):
                if _on_arc(b, a.at(a.start_angle + span * k / 8), -1e-9):
                    return OVERLAP
        return [p for p in (g1.at(g1.start_angle), g1.at(g1.end_angle)) if _on_arc(g2, p)]
    if d <= 1e-12 or d > g1.radius + g2.radius + 1e-9 or d < abs(g1.radius - g2.radius) - 1e-9:
        return []
    a = (g1.radius ** 2 - g2.radius ** 2 + d * d) / (2 * d)
    h = math.sqrt(max(g1.radius ** 2 - a * a, 0.0))
    ex = ((g2.center[0] - g1.center[0]) / d, (g2.center[1] - g1.center[1]) / d)
    m = (g1.center[0] + a * ex[0], g1.center[1] + a * ex[1])
    pts = {(m[0] - h * ex[1], m[1] + h * ex[0]), (m[0] + h * ex[1], m[1] - h * ex[0])}
    return [p for p in pts if _on_arc(g1, p) and _on_arc(g2, p)]


def _crossing(sketch: Sketch, edges: list[int]):
    """The first two edges that cross, overlap, or touch anywhere but at an end point they share."""
    geos = sketch.geometry
    for i, a in enumerate(edges):
        if isinstance(geos[a], _curves.BSplineCurve) and _curves.intersections(geos[a], None, _edge, OVERLAP):
            return a, a                    # a B-spline that crosses itself
        for b in edges[i + 1:]:
            ga, gb = geos[a], geos[b]
            hits = _intersections(ga, gb)
            if hits == OVERLAP:
                return a, b
            ends = [p for k, p in ga.points().items() if k != 3]
            shared = [p for k, p in gb.points().items() if k != 3 and any(math.dist(p, e) <= 1e-7 for e in ends)]
            if any(not any(math.dist(p, s) <= 1e-6 for s in shared) for p in hits):
                return a, b
    return None


def profile_face(sketch: Sketch):
    """ProfileBased::getTopoShapeVerifiedFace with AllowMultiFace (a Body feature's default): the
    sketch's non-construction edges joined to wires and made a face by FaceMakerBullseye, placed. One
    face, or a compound of faces for loops side by side."""
    idx = [i for i, g in enumerate(sketch.geometry) if not g.construction and not isinstance(g, Point)]
    if not idx:
        raise FeatureError("Linked shape object is empty")
    loc = TopLoc_Location(_trsf(sketch))
    edges = [TopoDS.Edge(_edge(sketch.geometry[i]).Moved(loc)) for i in idx]
    wires = _wires(edges)
    for w in wires:
        if not BRep_Tool.IsClosed_s(w):
            raise FeatureError("Wire is not closed.")
    cross = _crossing(sketch, idx)
    if cross:
        raise FeatureError("Could not create face from sketch.\nIntersecting sketch entities or multiple "
                           f"faces in a sketch are not allowed. (Sketch {sketch.name}: geometry "
                           f"{cross[0]} and {cross[1]} cross or overlap)")
    face = _bullseye(wires)
    if face is None or _count(face, TopAbs_FACE) == 0:
        raise FeatureError("Cannot make face from profile")
    return face


def _cog(shape):
    """TopoShape::getCenterOfGravity / the surface centre FreeCAD's findAllFacesCutBy takes."""
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, props)
    return props.CentreOfMass()


def _faces_cut_by(shape, face, d):
    """Part::findAllFacesCutBy: [(distsq, face)] for each face of shape the line through the profile's
    centre of gravity along d meets on the side d points to."""
    cog = _cog(face)
    line = gce_MakeLin(cog, d).Value()
    out = []
    inter = BRepIntCurveSurface_Inter()
    inter.Init(shape, line, CONFUSION)
    while inter.More():
        p = inter.Pnt()
        dsq = cog.SquareDistance(p)
        if dsq >= CONFUSION:
            mk = gce_MakeDir(cog, p)
            if mk.IsDone() and not mk.Value().IsOpposite(d, CONFUSION):
                out.append((dsq, inter.Face()))
        inter.Next()
    return out


def _bool(kind, base, tools, fuzzy=-1.0):
    """TopoShape::makeElementBoolean(kind, {base, *tools}, tol) (cad_agent/topo_boolean.py); fuzzy -1 is FreeCAD's
    default tolerance (the auto fuzzy value), 0 a feature's FuzzyTolerance."""
    from .topo_boolean import BooleanError, element_boolean
    try:
        out = element_boolean(kind, [base, *tools], fuzzy)
    except BooleanError as e:
        raise FeatureError(str(e)) from None
    if out is None:
        raise FeatureError(f"Boolean {kind} failed")
    return out


def _refine(shape):
    """FeatureRefine::refineShapeIfActive: FreeCAD's own refine, BRepBuilderAPI_RefineModel (cad_agent/refine.py)."""
    from .refine import refine
    return refine(shape)


def _through_all(base, profile) -> float:
    """ProfileBased::getThroughAllLength: 2.02 times the diagonal of the base and profile's box."""
    box = Bnd_Box()
    if base is not None:
        BRepBndLib.Add_s(base, box)
    BRepBndLib.Add_s(profile, box)
    box.SetGap(0.0)
    return 2.02 * math.sqrt(box.SquareExtent())


def _is_concave(face, p, d) -> bool:
    """Part::Tools::isConcave."""
    surf = BRep_Tool.Surface_s(face)
    if GeomAdaptor_Surface(surf).GetType() == GeomAbs_Plane:
        return False
    inter = BRepIntCurveSurface_Inter()
    inter.Init(face, gp_Lin(p, d), CONFUSION)
    pnt, du, dv = gp_Pnt(), gp_Vec(), gp_Vec()
    surf.D1(inter.U(), inter.V(), pnt, du, dv)
    res = (gp_Dir(du).Angle(d) - math.pi / 2) <= CONFUSION
    return res or (gp_Dir(dv).Angle(d) - math.pi / 2) <= CONFUSION


def _prism_until(base, profile, upto, d):
    """TopoShape::makeElementPrismUntil(base, profile, no support face, upto, d, PrismMode::None,
    checkLimits=True): BRepFeat_MakePrism per profile face, the first alone, the rest fused on."""
    _upto = upto
    check = True
    if _upto.ShapeType() == TopAbs_FACE:
        check = not _is_concave(TopoDS.Face(_upto), _cog(profile), d)
    if check and _upto.ShapeType() == TopAbs_FACE and not BRep_Tool.NaturalRestriction_s(TopoDS.Face(_upto)):
        _upto = BRepBuilderAPI_Copy(_upto).Shape()
        BRep_Builder().NaturalRestriction(TopoDS.Face(_upto), True)
    uptoface = _upto
    sbase = profile if base is None else base
    if check and uptoface.ShapeType() == TopAbs_FACE and _count(uptoface, TopAbs_WIRE):
        face = TopoDS.Face(uptoface)
        remove = False
        for sf in _faces(profile):
            proj = BRepProj_Projection(BRepTools.OuterWire_s(sf), face, d)
            if not proj.More() or not proj.Current().Closed():
                remove = True
                break
        if not remove:
            outer = BRepTools.OuterWire_s(face)
            for w in _subs(face, TopAbs_WIRE):
                if w.IsSame(outer):
                    continue
                if BRepProj_Projection(TopoDS.Wire(w), profile, d.Reversed()).More():
                    remove = True
                    break
        if remove:
            adapt = BRepAdaptor_Surface(face, False)
            mk = BRepBuilderAPI_MakeFace(adapt.Surface().Surface(), CONFUSION)
            if mk.IsDone():
                uptoface = mk.Shape().Located(TopLoc_Location(adapt.Trsf()))
    first_upto = uptoface
    tried_base = False
    while True:
        try:
            result = sbase
            mode = 2                                   # PrismMode::None: the feature alone
            pieces = _faces(profile) if _count(profile, TopAbs_FACE) else _subs(profile, TopAbs_WIRE)
            for f in pieces:
                if result.Infinite():
                    result = f
                pm = BRepFeat_MakePrism()
                pm.Init(result, f, TopoDS_Face(), d, mode, False)
                mode = 1                               # PrismMode::FuseWithBase for the next faces
                pm.Perform(uptoface)
                if not pm.IsDone() or pm.Shape().IsNull():
                    raise FeatureError("BRepFeat_MakePrism: extrusion failed")
                result = pm.Shape()
            return result
        except Exception:
            if not uptoface.IsSame(_upto):
                uptoface = _upto
                continue
            if not tried_base:
                tried_base = True
                uptoface = first_upto
                sbase = BRepPrimAPI_MakePrism(_upto, d, True).Shape()
                continue
            raise


def _plane_face(name):
    key = _plane_key(name)
    n = PLANES[key][2]
    return BRepBuilderAPI_MakeFace(gp_Pln(gp_Pnt(0, 0, 0), gp_Dir(*n))).Face()


def _ref_face(ref, shapes, where):
    """("Pad", "Face6") or "XY_Plane": the face an UpToFace names."""
    if isinstance(ref, str):
        return _plane_face(ref)
    try:
        obj, sub = ref
    except (TypeError, ValueError):
        raise FeatureError(f"{where}: {ref!r} is not (feature, 'FaceN') or an origin plane") from None
    if isinstance(sub, (list, tuple)):
        sub = sub[0]
    if obj not in shapes:
        raise FeatureError(f"{where}: no feature {obj!r} before it")
    if not (isinstance(sub, str) and sub.startswith("Face") and sub[4:].isdigit()):
        raise FeatureError(f"{where}: {sub!r} is not a face name (Face1, Face2, ...)")
    faces = _faces(shapes[obj])
    i = int(sub[4:])
    if not 1 <= i <= len(faces):
        raise FeatureError("SketchBased: Up to face: Failed to extract face")
    return faces[i - 1]


def _up_to_shape(refs, shapes, where):
    """ProfileBased::getUpToShapeFromLinkSubList: (shape, face count); 2 for one whole shape."""
    if not refs:
        return None, 0
    if isinstance(refs, (str, tuple)):
        refs = [refs]
    if len(refs) == 1 and isinstance(refs[0], str) and not refs[0].endswith("_Plane"):
        if refs[0] not in shapes:
            raise FeatureError(f"{where}: no feature {refs[0]!r} before it")
        return shapes[refs[0]], 2
    faces = []
    for r in refs:
        if isinstance(r, str) and r.endswith("_Plane"):
            faces.append(_plane_face(r))
        elif isinstance(r, str):
            if r not in shapes:
                raise FeatureError(f"{where}: no feature {r!r} before it")
            faces.extend(_faces(shapes[r]))
        else:
            obj, subs = r
            for s in ([subs] if isinstance(subs, str) else subs):
                faces.append(_ref_face((obj, s), shapes, where))
    if len(faces) == 1:
        return faces[0], 1
    comp = TopoDS_Compound()
    b = BRep_Builder()
    b.MakeCompound(comp)
    for f in faces:
        b.Add(comp, f)
    return comp, len(faces)


def _get_up_to_face(upto, support, sketchshape, method, d):
    """ProfileBased::getUpToFace: the face, and the direction (turned when the face is behind)."""
    if method in ("UpToLast", "UpToFirst"):
        cut = _faces_cut_by(support, sketchshape, d) if support is not None else []
        if not cut:
            raise FeatureError("SketchBased: No faces found in this direction")
        near = far = cut[0]
        for c in cut:
            if c[0] > far[0]:
                far = c
            elif c[0] < near[0]:
                near = c
        upto = far[1] if method == "UpToLast" else near[1]
    elif not _faces_cut_by(upto, sketchshape, d):
        d = d.Reversed()
    if upto.ShapeType() != TopAbs_FACE:
        fs = _faces(upto)
        if not fs:
            raise FeatureError("SketchBased: Up to face: No face found")
        upto = fs[0]
    face = TopoDS.Face(upto)
    adapt = BRepAdaptor_Surface(face)
    if adapt.GetType() == GeomAbs_Plane and d.IsNormal(adapt.Plane().Axis().Direction(), CONFUSION):
        raise FeatureError("SketchBased: Up to face: Must not be parallel to extrusion direction!")
    dist = BRepExtrema_DistShapeShape(sketchshape, face)
    if dist.Value() < CONFUSION:
        raise FeatureError("SketchBased: Up to face: Must not intersect sketch!")
    return face, d


def _moved(shape, vec):
    t = gp_Trsf()
    t.SetTranslation(vec)
    return shape.Moved(TopLoc_Location(t))


def _shell_from_up_to_shape(shape, sketchshape, d):
    """FeatureExtrude::makeShellFromUpToShape: the shape without its farthest face, so OCC works."""
    cut = _faces_cut_by(shape, sketchshape, d)
    if not cut:
        d = d.Reversed()
        cut = _faces_cut_by(shape, sketchshape, d)
    if not cut:
        return shape, d
    near = far = cut[0]
    for c in cut:
        if c[0] > far[0]:
            far = c
        elif c[0] < near[0]:
            near = c
    if near is far:
        return shape, d
    comp = TopoDS_Compound()
    b = BRep_Builder()
    b.MakeCompound(comp)
    for f in _faces(shape):
        if not f.IsEqual(far[1]):
            b.Add(comp, f)
    return comp, d


def _side(feat, sketchshape, method, length, d, offset, up_to_face, up_to_shape, base, shapes, additive,
          where):
    """FeatureExtrude::generateSingleExtrusionSide."""
    if method in ("UpToFirst", "UpToLast", "UpToFace", "UpToShape"):
        count = 1
        upto = None
        if method == "UpToFace":
            if up_to_face is None:
                raise FeatureError("SketchBased: No face selected")
            upto = _ref_face(up_to_face, shapes, where)
        elif method == "UpToShape":
            upto, count = _up_to_shape(up_to_shape, shapes, where)
            if count == 0:
                upto = base
        if count == 1:
            upto, d = _get_up_to_face(upto, base, sketchshape, method, d)
            if abs(offset) > CONFUSION:
                upto = _moved(upto, gp_Vec(d).Multiplied(offset))
        else:
            if upto is None:
                raise FeatureError("SketchBased: No faces found in this direction")
            if abs(offset) > CONFUSION:
                raise FeatureError("Extrude: Can only offset one face")
            upto, d = _shell_from_up_to_shape(upto, sketchshape, d)
        try:
            return _prism_until(base if additive else None, sketchshape, upto, d)
        except Exception:
            if method == "UpToShape" and count > 1:
                raise FeatureError("Extrude: Unable to reach the selected shape, please select faces") \
                    from None
            raise
    try:
        return BRepPrimAPI_MakePrism(sketchshape, gp_Vec(d).Multiplied(length)).Shape()
    except Exception:
        raise FeatureError("FeatureExtrusion: Length: Could not extrude the sketch!") from None


def _xor(prisms):
    """TopoShape::makeElementXor: Cut(Union, Common), pairwise."""
    result = prisms[0]
    for p in prisms[1:]:
        union = _bool("fuse", result, [p])
        common = _bool("common", result, [p])
        result = _bool("fuse", result, [p]) if common.IsNull() else _bool("cut", union, [common])
    return result


def _extrude(feat: _Extrude, sketch: Sketch, base, shapes, params, out: dict | None = None):
    """FeatureExtrude::buildExtrusion, in the global frame (FreeCAD works in the feature's own placement
    and moves the result back, which is the same solid). out, when given, gets "addsub": the refined prism,
    FreeCAD's AddSubShape, which a pattern of this feature moves."""
    where = feat.name
    additive = isinstance(feat, Pad)
    side, method, method2 = feat.side_type, feat.type, feat.type2
    sketchshape = profile_face(sketch)

    def length(v, k):
        return value(v, params, f"{where}.{k}")

    through = _through_all(base, sketchshape)
    L = through if method == "ThroughAll" else length(feat.length, "length") if method == "Length" else 0.0
    L2 = 0.0
    if side == "Two sides":
        L2 = through if method2 == "ThroughAll" else length(feat.length2, "length2") \
            if method2 == "Length" else 0.0
    if ((side == "One side" and method == "Length")
            or (side == "Two sides" and method == "Length" and method2 == "Length")) \
            and abs(L + L2) < CONFUSION:
        raise FeatureError(f"Cannot create a {'pad' if additive else 'pocket'} with a total length of zero.")
    if not additive and base is None:
        raise FeatureError(f"{where}: a Pocket needs a solid to cut: a Pad or a base before it")

    normal = gp_Dir(*sketch.normal())
    if not additive:
        normal = normal.Reversed()                  # Pocket::getProfileNormal
    if feat.use_custom_vector:
        dv = feat.direction
        d = normal if all(abs(c) < CONFUSION for c in dv) else gp_Dir(*dv)
    else:
        d = normal
    factor = abs(d.Dot(normal))
    if factor < CONFUSION:
        raise FeatureError("Creation failed because direction is orthogonal to sketch's normal vector")
    if feat.along_sketch_normal:
        L, L2 = L / factor, L2 / factor
    if feat.reversed:
        d = d.Reversed()

    start = length(feat.start_offset, "start_offset") if feat.start_type == "Offset" else 0.0
    start_sketch = _moved(sketchshape, gp_Vec(d).Multiplied(start)) if abs(start) >= CONFUSION \
        else sketchshape
    off1 = length(feat.offset, "offset")
    prisms = []

    def one(shape, m, ln, dd, off, utf, uts):
        return _side(feat, shape, m, ln, dd, off, utf, uts, base, shapes, additive, where)

    if side == "One side":
        prisms.append(one(start_sketch, method, L, d, off1, feat.up_to_face, feat.up_to_shape))
    elif side == "Symmetric":
        if method == "Length":
            moved = _moved(start_sketch, gp_Vec(d).Reversed().Multiplied(L / 2.0))
            prisms.append(one(moved, method, L, d, off1, feat.up_to_face, feat.up_to_shape))
        else:
            p1 = one(start_sketch, method, L, d, off1, feat.up_to_face, feat.up_to_shape)
            box = Bnd_Box()
            BRepBndLib.Add_s(start_sketch, box)
            lo, hi = box.CornerMin(), box.CornerMax()
            mirror = gp_Trsf()
            mirror.SetMirror(gp_Ax2(gp_Pnt((lo.X() + hi.X()) / 2, (lo.Y() + hi.Y()) / 2, (lo.Z() + hi.Z()) / 2),
                                    gp_Dir(*sketch.normal())))
            prisms += [p1, BRepBuilderAPI_Transform(p1, mirror).Shape()]
    else:
        off2 = length(feat.offset2, "offset2")
        d2 = d.Reversed()
        has_start = abs(start) > CONFUSION
        if not has_start and method in ("Length", "ThroughAll") and method2 != "UpToFirst":
            moved = _moved(sketchshape, gp_Vec(d).Multiplied(L))
            prisms.append(one(moved, method2, L + L2, d2, off2, feat.up_to_face2, feat.up_to_shape2))
        elif not has_start and method2 in ("Length", "ThroughAll") and method != "UpToFirst":
            moved = _moved(sketchshape, gp_Vec(d).Reversed().Multiplied(L2))
            prisms.append(one(moved, method, L + L2, d, off1, feat.up_to_face, feat.up_to_shape))
        else:
            prisms.append(one(start_sketch, method, L, d, off1, feat.up_to_face, feat.up_to_shape))
            prisms.append(one(start_sketch, method2, L2, d2, off2, feat.up_to_face2, feat.up_to_shape2))
    prisms = [p for p in prisms if p is not None and not p.IsNull()]
    if not prisms:
        raise FeatureError("No extrusion geometry was generated.")
    prism = prisms[0] if len(prisms) == 1 else _xor(prisms)
    refine = _refine if feat.refine else (lambda s: s)
    prism = refine(prism)                           # buildExtrusion: the boolean takes the refined prism
    if out is not None:
        out["addsub"] = prism
    if base is not None:
        result = _bool("fuse" if additive else "cut", base, [prism], 0.0)      # FuzzyTolerance
        if not _count(result, TopAbs_SOLID):
            raise FeatureError("Resulting shape is not a solid")
        return refine(result)
    if _count(prism, TopAbs_SOLID):
        solids = _subs(prism, TopAbs_SOLID)
        if len(solids) > 1:
            prism = _bool("fuse", solids[0], solids[1:])
        return refine(prism)
    return refine(prism)


# ── the body ──────────────────────────────────────────────────────────────────────────────────────────

def evaluate(features, params: dict | None = None, base=None, tip: str | None = None) -> dict:
    """{name: TopoDS_Shape} of every Pad and Pocket in order, up to and including tip (all of them when
    tip is None), with "BaseFeature" for the base, "Tip" for the tip's solid and "_sketches" holding each
    sketch solved. The UI's tree reads this. "_addsub" holds each additive or subtractive feature's tool
    ({name: (shape, additive)}, FreeCAD's AddSubShape), "_before" the solid before each feature and "_order"
    the features' names, which the transformed features (feature_transform.py) read.

    A feature that is not a Sketch, Pad or Pocket builds itself: its execute(solid, shapes, params) returns
    the Body's solid after it (feature_kw.py, feature_transform.py, feature_primitive.py).
    "_attach" is the Body as attachment sees it (feature_attach.Context): each object's shape and Placement,
    which a sketch, a datum and an attached primitive resolve their references in."""
    from .feature_attach import Context                 # attachment, datums (cad_agent/feature_attach.py)

    params = dict(params or {})
    names = [getattr(f, "name", None) for f in features]
    if tip is not None and tip not in names and tip != "BaseFeature":
        raise FeatureError(f"the tip {tip!r} is not a feature of the Body")
    sketches: dict = {}
    shapes: dict = {"_addsub": {}, "_before": {}, "_order": names, "_sketches": sketches}
    solid = None
    if base is not None:
        solid = getattr(base, "wrapped", base)
        shapes["BaseFeature"] = solid
    ctx = Context(solid)
    shapes["_attach"] = ctx
    previous = "BaseFeature" if solid is not None else None     # the solid feature before (getBaseObject)
    for f in ([] if tip == "BaseFeature" else features):
        name = getattr(f, "name", None)
        if not isinstance(f, (Sketch, _Extrude)) and not hasattr(f, "execute") and not getattr(f, "is_datum", False):
            raise FeatureError(f"FEATURES holds {f!r}, not a Sketch, Pad or Pocket")
        if name in shapes or name in sketches or name in ctx.kinds:
            raise FeatureError(f"two features are named {name!r}" if name not in ctx.placements or
                               ctx.kinds.get(name) in ("solid", "sketch", "datum")
                               else f"{name!r} is the name of the Body's origin {ctx.kinds[name]}")
        if isinstance(f, Sketch):
            sketches[name] = _place_sketch(f, ctx, params)
        elif getattr(f, "is_datum", False):
            ctx.add_datum(f)
        elif not isinstance(f, _Extrude):
            shapes["_before"][name] = solid
            solid = f.execute(solid, shapes, params)
            shapes[name] = solid
            # positionByPrevious: the solid before's Placement, or the profile's support's for a first profile feature
            prof = sketches.get(getattr(f, "profile", None)) if isinstance(getattr(f, "profile", None), str) else None
            # a primitive keeps its own (attached) Placement (FeaturePrimitive)
            ctx.add_solid(name, solid, ctx.own_placement(f) if getattr(f, "PRIMITIVE", "") else
                          ctx.placements[previous] if previous else
                          ctx.first_placement(prof) if prof is not None else ctx.own_placement(f))
            previous = name
        else:
            if f.profile not in sketches:
                raise FeatureError(f"{name}: no sketch {f.profile!r} before it" if f.profile not in shapes
                                   else f"{name}: profile {f.profile!r} is not a sketch")
            shapes["_before"][name] = solid
            out: dict = {}
            solid = _extrude(f, sketches[f.profile], solid, shapes, params, out)
            shapes["_addsub"][name] = (out.get("addsub"), isinstance(f, Pad))
            shapes[name] = solid
            # ProfileBased::positionByPrevious: the Placement of the solid before, or of the first one's support
            ctx.add_solid(name, solid, ctx.placements[previous] if previous else
                          ctx.first_placement(sketches[f.profile]))
            previous = name
        if name == tip:
            break
    shapes["Tip"] = solid
    shapes["_sketches"] = sketches
    shapes["_attach"] = ctx
    return shapes


def _place_sketch(f: Sketch, ctx, params) -> Sketch:
    """SketchObject::execute's order: positionBySupport, rebuildExternalGeometry, then the solve."""
    from . import attacher as A
    from .feature_attach import external_geometry
    if f.support is not None and not f.external_geometry:
        pos, rot = f.placement()                  # a plain sketch on an origin plane, as PLANES places it
        pl = A.Placement(pos, A.Rotation.from_matrix(rot))
        s = f
    else:
        pl = ctx.attach(f, f"Sketch {f.name}", orig=f._own_pl)
        pl = pl if pl is not None else f._own_pl
        s = f.placed(pl, external_geometry(f, pl, ctx))
    s = s.solved(params)
    ctx.add_sketch(s, pl)
    return s


def Body(features, params: dict | None = None, base=None, tip: str | None = None):
    """PartDesign::Body: the tip's solid, as a build123d Part. base is the BaseFeature, a hand-built solid
    (a build123d shape or a TopoDS_Shape) that the first feature adds to or cuts from. tip is Body.Tip, the
    feature whose solid the Body is (None: the last); the features after it are not built, and a sketch
    as the tip leaves the solid before it, as in FreeCAD."""
    from build123d import Compound, Part, Solid
    solid = evaluate(features, params, base, tip)["Tip"]
    if solid is None:
        raise FeatureError("the Body has no solid: FEATURES has no Pad before its tip and there is no base")
    solids = [Solid(s) for s in _subs(solid, TopAbs_SOLID)]
    if not solids:
        raise FeatureError("the Body's tip is not a solid")
    return Part(Compound(solids).wrapped)


# ── the same lines, fed to FreeCAD ────────────────────────────────────────────────────────────────────

def to_freecad(features, params: dict | None = None, doc=None, name: str = "Body", base=None):
    """Build FEATURES as a PartDesign Body in a FreeCAD document (run inside FreeCAD: freecadcmd).
    PARAMS become a spreadsheet, Params, and every value given as a PARAMS name or expression is bound
    to it by an expression, as a FreeCAD user would bind it. base is a Part.Shape for BaseFeature.
    Returns the Body; recompute the document to build it."""
    import FreeCAD as App
    import Part
    import Sketcher
    V = App.Vector
    doc = doc or App.newDocument(name)
    params = dict(params or {})
    sheet = None
    if params:
        sheet = doc.addObject("Spreadsheet::Sheet", "Params")
        for i, (k, v) in enumerate(params.items()):
            cell = f"A{i + 1}"
            sheet.set(cell, repr(float(v)) if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v))
            sheet.setAlias(cell, k)
        doc.recompute()

    def expr(v):
        tree = ast.parse(v, mode="eval")

        class _R(ast.NodeTransformer):
            def visit_Name(self, n):
                return ast.copy_location(ast.Name(id=f"Params.{n.id}", ctx=n.ctx), n)
        return ast.unparse(_R().visit(tree))

    def setv(obj, prop, v, scale=1.0):
        if isinstance(v, str):
            setattr(obj, prop, value(v, params, prop) * scale)
            obj.setExpression(prop, expr(v))
        else:
            setattr(obj, prop, float(v) * scale)

    body = doc.addObject("PartDesign::Body", name)
    if base is not None:
        bf = doc.addObject("Part::Feature", "BaseFeature")
        bf.Shape = base
        body.BaseFeature = bf
    planes = {o.Role: o for o in body.Origin.OriginFeatures}
    made = {"BaseFeature": body.BaseFeature} if base is not None else {}

    def ref(r):
        if isinstance(r, str):
            if r.endswith("_Plane") or r in PLANES:
                return planes[_plane_key(r) + "_Plane"], [""]
            return made[r], [""]
        obj, sub = r
        return made[obj], ([sub] if isinstance(sub, str) else list(sub))

    def obj_of(name):
        return planes[name] if name in planes else made[name]

    def attach(obj, f):
        """AttachExtension's properties, as feature_attach.Attachable holds them."""
        sup = [(obj_of(o), sb) for o, sb in f.attachment_support]
        if sup:
            obj.AttachmentSupport = sup
        mode = f.map_mode
        if mode is None:                          # UnifiedDatumCommand: the mode FreeCAD suggests
            doc.recompute()                       # for the references as built, as in the GUI
            eng = Part.AttachEngine(obj.AttacherType)
            eng.References = sup
            mode = eng.suggestModes()["bestFitMode"]
        obj.MapMode = mode
        off = f._offset_pl
        obj.AttachmentOffset = App.Placement(V(*off.pos), App.Rotation(*off.rot.q))
        obj.MapReversed = f.map_reversed
        obj.MapPathParameter = f.map_path_parameter
        if mode == "Deactivated" or not sup:
            own = f._own_pl
            obj.Placement = App.Placement(V(*own.pos), App.Rotation(*own.rot.q))

    import types
    ctx = types.SimpleNamespace(App=App, doc=doc, body=body, made=made, params=params, setv=setv, ref=ref,
                                origin={o.Role: o for o in body.Origin.OriginFeatures},
                                setint=lambda obj, prop, v: (setattr(obj, prop, int(round(value(v, params, prop)))),
                                                             isinstance(v, str) and obj.setExpression(prop, expr(v))))
    ctx.attach = attach                             # AttachExtension's properties, for a feature that has them
    for f in features:
        if getattr(f, "is_datum", False):
            obj = body.newObject(f.type_id, f.name)
            attach(obj, f)
            if hasattr(obj, "ResizeMode"):
                obj.ResizeMode = f.resize_mode
                obj.Length = f.length
                if hasattr(obj, "Width"):
                    obj.Width = f.width
            made[f.name] = obj
            continue
        if hasattr(f, "to_freecad"):                # a feature that writes itself (feature_kw.py)
            made[f.name] = f.to_freecad(ctx)
            continue
        if isinstance(f, Sketch):
            sk = body.newObject("Sketcher::SketchObject", f.name)
            attach(sk, f)
            for g in f.geometry:
                if isinstance(g, LineSegment):
                    pg = Part.LineSegment(V(*g.start, 0), V(*g.end, 0))
                elif isinstance(g, Circle):
                    pg = Part.Circle(V(*g.center, 0), V(0, 0, 1), g.radius)
                elif isinstance(g, ArcOfCircle):
                    pg = Part.ArcOfCircle(Part.Circle(V(*g.center, 0), V(0, 0, 1), g.radius),
                                          g.start_angle, g.end_angle)
                elif isinstance(g, _curves.CURVES):
                    pg = _curves.part_geometry(g, Part, V)
                else:
                    pg = Part.Point(V(*g.point, 0))
                sk.addGeometry(pg, g.construction)
            if f.external_geometry:                  # what it projects must be built first, as in the GUI
                doc.recompute()
            for o, sb in f.external_geometry:        # Sketcher_External: GeoId -3, -4, ... in this order
                sk.addExternal(obj_of(o).Name, sb)
            for i, c in enumerate(f.constraints):
                args = list(c.args) + ([c.resolved(params)] if c.dimensional else [])
                sk.addConstraint(Sketcher.Constraint(c.type, *args))
                if c.name:
                    sk.renameConstraint(i, c.name)
                if not c.driving:
                    sk.setDriving(i, False)
                if c.dimensional and isinstance(c.value, str):
                    e = expr(c.value)
                    sk.setExpression(f"Constraints[{i}]", e + (" * 1 deg" if c.type == "Angle" else ""))
            made[f.name] = sk
            continue
        obj = body.newObject(f"PartDesign::{f.kind}", f.name)
        obj.Profile = made[f.profile]
        obj.Refine = f.refine
        obj.SideType = f.side_type
        obj.Type = f.type
        obj.Type2 = f.type2
        setv(obj, "Length", f.length)
        setv(obj, "Length2", f.length2)
        setv(obj, "Offset", f.offset)
        setv(obj, "Offset2", f.offset2)
        obj.Reversed = f.reversed
        obj.UseCustomVector = f.use_custom_vector
        obj.Direction = V(*f.direction)
        obj.AlongSketchNormal = f.along_sketch_normal
        obj.StartType = f.start_type
        setv(obj, "StartOffset", f.start_offset)
        for prop, r in (("UpToFace", f.up_to_face), ("UpToFace2", f.up_to_face2)):
            if r is not None:
                o, subs = ref(r)
                setattr(obj, prop, (o, subs))
        for prop, rs in (("UpToShape", f.up_to_shape), ("UpToShape2", f.up_to_shape2)):
            if rs:
                rs = [rs] if isinstance(rs, (str, tuple)) else rs
                setattr(obj, prop, [ref(r) for r in rs])
        made[f.name] = obj
    return body


# ── the features in modules of their own ──────────────────────────────────────────────────────────────────────────
from .feature_transform import LinearPattern, Mirrored, MultiTransform, PolarPattern, TRANSFORMED  # noqa: E402

FEATURES.update(TRANSFORMED)
from .feature_primitive import PRIMITIVES  # noqa: E402  AdditiveBox ... SubtractiveWedge

FEATURES.update(PRIMITIVES)
globals().update(PRIMITIVES)
from .feature_dressup import DRESSUPS, Chamfer, Draft, Fillet, Thickness  # noqa: E402  (PartDesign's dress-ups)

FEATURES.update(DRESSUPS)
from .feature_revolve import Groove, Revolution  # noqa: E402  PartDesign::Revolution, PartDesign::Groove
FEATURES.update(Revolution=Revolution, Groove=Groove)
from .feature_hole import Hole  # noqa: E402  PartDesign::Hole
FEATURES.update(Hole=Hole)
# The datum features (Part::DatumPlane, DatumLine, DatumPoint, LocalCoordinateSystem, and PartDesign::Plane, ...)
# live with the attachment that places them, and are part of this vocabulary: `from cad_agent.feature import DatumPlane`.
from .feature_attach import (DatumLine, DatumPlane, DatumPoint, LocalCoordinateSystem,  # noqa: E402,F401
                             PartDesignCoordinateSystem, PartDesignLine, PartDesignPlane, PartDesignPoint)
from .feature_attach import DATUMS as _DATUMS  # noqa: E402

FEATURES.update(_DATUMS)

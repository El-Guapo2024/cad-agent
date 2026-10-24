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
    CoordinateSystem("Local_CS", attachment_support=[("Pad", "Vertex3"), ("Pad", "Edge1")], map_mode="OXY")
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
    from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Line, GeomAbs_Plane
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

def support_list(where: str, sup) -> list[tuple[str, str]]:
    """AttachmentSupport as a part file writes it, normalised to [(object, element), ...]: a name alone is
    (name, ""), (name, [e1, e2]) is two references, and the old "XY" is ("XY_Plane", "")."""
    if sup is None:
        return []
    if isinstance(sup, str):
        sup = [sup]
    if isinstance(sup, tuple) and len(sup) == 2 and isinstance(sup[0], str) and \
            (isinstance(sup[1], (str, list, tuple))) and not isinstance(sup[1], tuple):
        sup = [sup]
    out = []
    for r in sup:
        if isinstance(r, str):
            out.append((SHORT.get(r, r), ""))
            continue
        try:
            obj, sub = r
        except (TypeError, ValueError):
            raise FeatureError(f"{where}: attachment reference {r!r} is not (object, element)") from None
        if not isinstance(obj, str):
            raise FeatureError(f"{where}: attachment reference {r!r}: the object is a name")
        subs = [sub] if isinstance(sub, str) or sub is None else list(sub)
        for s in subs or [""]:
            if s and not ELEMENT.match(s) and s not in ("X", "Y", "Z"):
                raise FeatureError(f"{where}: {s!r} is not an element name (Face1, Edge1, Vertex1, ...)")
            out.append((SHORT.get(obj, obj), s or ""))
    if len(out) > 4:
        raise FeatureError(f"{where}: an attachment takes at most four references (FreeCAD's Reference 1 to 4)")
    return out


def placement_of(where: str, value, what: str = "placement") -> A.Placement:
    try:
        return A.Placement.from_offset(value)
    except (TypeError, ValueError):
        raise FeatureError(f"{where}: {what} {value!r} is not (x, y, z) or ((x, y, z), (yaw, pitch, roll))") \
            from None


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
        return [o for o, _ in self.attachment_support]


# ── datum features ────────────────────────────────────────────────────────────────────────────────────

class _Datum(Attachable):
    """Part::Datum: a reference geometry placed by its attachment. Its shape, as DatumPlane.cpp and its
    neighbours make it, moved to its Placement."""
    kind = ""
    is_datum = True
    SIZE = ()

    def __init__(self, name: str, *, attachment_support=None, map_mode=None, attachment_offset=None,
                 map_reversed=False, map_path_parameter=0.0, placement=None, resize_mode="Automatic",
                 length=20.0, width=20.0):
        self.name = name
        self.init_attachment(name, attachment_support, map_mode, attachment_offset, map_reversed,
                             map_path_parameter, placement)
        if resize_mode not in ("Automatic", "Manual"):
            raise FeatureError(f"{name}: resize_mode {resize_mode!r} is not Automatic or Manual")
        self.resize_mode, self.length, self.width = resize_mode, float(length), float(width)

    def local_shape(self):
        raise NotImplementedError

    def __repr__(self):
        return f"{self.kind}({self.name!r}, map_mode={self.map_mode!r}, support={self.attachment_support!r})"


def _infinite(shape):
    shape.Infinite(True)
    return shape


class DatumPlane(_Datum):
    """PartDesign::Plane (Datum Plane): an infinite face, its normal the placement's Z. ResizeMode, Length and
    Width (20 x 20) are how the view draws it."""
    kind = "DatumPlane"
    type_id = "PartDesign::Plane"
    engine = "Plane"

    def local_shape(self):
        return _infinite(BRepBuilderAPI_MakeFace(gp_Pln(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1))).Shape())


class DatumLine(_Datum):
    """PartDesign::Line (Datum Line): an infinite edge along the placement's Z."""
    kind = "DatumLine"
    type_id = "PartDesign::Line"
    engine = "Line"

    def local_shape(self):
        return _infinite(BRepBuilderAPI_MakeEdge(gp_Lin(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1))).Shape())


class DatumPoint(_Datum):
    """PartDesign::Point (Datum Point): a vertex at the placement's origin."""
    kind = "DatumPoint"
    type_id = "PartDesign::Point"
    engine = "Point"

    def local_shape(self):
        return BRepBuilderAPI_MakeVertex(gp_Pnt(0, 0, 0)).Shape()


class CoordinateSystem(_Datum):
    """PartDesign::CoordinateSystem (Local Coordinate System, Local_CS): placed by the 3D engine; its shape is
    the XY plane's face (DatumCS.cpp), its X, Y and Z the planes normal to them."""
    kind = "CoordinateSystem"
    type_id = "PartDesign::CoordinateSystem"
    engine = "3D"

    def local_shape(self, axis: str = ""):
        d = {"X": (1, 0, 0), "Y": (0, 1, 0)}.get(axis, (0, 0, 1))
        return BRepBuilderAPI_MakeFace(gp_Pln(gp_Pnt(0, 0, 0), gp_Dir(*d))).Shape()


DATUMS = {c.kind: c for c in (DatumPlane, DatumLine, DatumPoint, CoordinateSystem)}


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

    def first_placement(self, sketch) -> A.Placement:
        """ProfileBased::positionByPrevious for the Body's first solid feature: the Placement of its sketch's
        first support object (an origin plane, a datum), else the sketch's own."""
        sup = getattr(sketch, "attachment_support", None) or \
            ([(sketch.support + "_Plane", "")] if getattr(sketch, "support", None) else [])
        if sup and sup[0][0] in self.placements and self.kinds.get(sup[0][0]) != "sketch":
            return self.placements[sup[0][0]]
        return self.placements.get(sketch.name, A.Placement())

    def origin_shape(self, role):
        kind, _ = ORIGIN[role]
        if kind == "App::Plane":
            s = _infinite(BRepBuilderAPI_MakeFace(gp_Pln(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1))).Shape())
        elif kind == "App::Line":
            s = _infinite(BRepBuilderAPI_MakeEdge(gp_Lin(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0))).Shape())
        else:
            s = BRepBuilderAPI_MakeVertex(gp_Pnt(0, 0, 0)).Shape()
        return _moved(s, self.placements[role])

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

    def element(self, obj, sub, where):
        """The shape a reference names, as extractSubShape finds it (None for an object with no shape)."""
        if obj in ORIGIN:
            if sub:
                raise FeatureError(f"{where}: the origin's {obj} has no element {sub!r}")
            return self.origin_shape(obj)
        kind = self.kinds.get(obj)
        if kind is None:
            raise FeatureError(f"{where}: no {obj!r} before it (a feature, a datum, or the Body's origin: "
                               f"{', '.join(ORIGIN)})")
        if kind == "sketch":
            return self.sketch_shape(obj, sub)
        if kind == "datum":
            d = self.datums[obj]
            if isinstance(d, CoordinateSystem) and sub in ("X", "Y", "Z"):
                return _moved(d.local_shape(sub), self.placements[obj])
            if sub:
                return sub_shape(self.shapes[obj], sub)
            return self.shapes[obj]
        if not sub:
            return self.shapes[obj]
        try:
            return sub_shape(self.shapes[obj], sub)
        except FeatureError as e:
            raise FeatureError(f"{where}: {obj}.{sub}: {e}") from None

    def ref(self, obj, sub, where) -> A.Ref:
        shape = self.element(obj, sub, where)
        return A.Ref(shape, self.placements[obj], whole=not sub, plane=self.kinds.get(obj) == "App::Plane")

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
        self.shapes[d.name] = _moved(d.local_shape(), pl)
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
    curve = BRepAdaptor_Curve(edge)
    t = curve.GetType()
    if t == GeomAbs_Line:
        return [_project_line(curve, pr)]
    if t != GeomAbs_Circle:
        raise FeatureError(f"{where}: external geometry of this kind of edge (not a line or a circle) is not "
                           "supported yet")
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
    raise FeatureError(f"{where}: a circle at an angle to the sketch projects to an ellipse, which the sketch "
                       "cannot hold yet")


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
        try:
            obj, sub = r
        except (TypeError, ValueError):
            raise FeatureError(f"{where}: external geometry {r!r} is not (object, element)") from None
        if not isinstance(obj, str) or not isinstance(sub, str) or (sub and not ELEMENT.match(sub)):
            raise FeatureError(f"{where}: external geometry {r!r} is not (object, 'Edge1' / 'Vertex1' / 'Face1')")
        out.append((SHORT.get(obj, obj), sub))
    return out

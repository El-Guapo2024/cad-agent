# SPDX-License-Identifier: LGPL-2.1-or-later
# Port of FreeCAD 3160daf1e2b6's link arrays (src/Mod/Part/App/LinkArray.cpp and LinkArrayLinear.cpp, Copyright (c)
# 2026 Boyer Pierre-Louis; LinkArrayPolar.cpp, Copyright (c) 2026 FreeCAD Project Association; their pattern arithmetic
# is LinearPatternExtension and PolarPatternExtension's, ported in cad_agent/feature_transform.py; the circular one,
# CircularPatternExtension.cpp, no copyright line, is ported here; LinkArrayPath.cpp, LinkArrayPoint.cpp,
# PathPatternExtension.cpp and PointPatternExtension.cpp, SPDX LGPL-2.1-or-later with no copyright line, are ported here
# too) and
# Part_LinkArrayLinear / Part_LinkArrayPolar's activateLinkArrayCommand (src/Mod/Part/Gui/Command.cpp, Copyright (c)
# 2002 Jürgen Riegel).
"""Link arrays of an Assembly: Part_LinkArrays' Linear and Polar Link Array in a project's ASSEMBLY.

    Assembly.LinkArrayLinear("LinearLinkArray", "pin", direction="X_Axis", occurrences=3, length=40),
    Assembly.LinkArrayPolar("PolarLinkArray", "bolt", axis="Z_Axis", occurrences=6),
    Assembly.LinkArrayPath("PathLinkArray", "bolt", path=("rail", ["Edge1"]), count=5),
    Assembly.LinkArrayPoint("PointLinkArray", "bolt", point_object="holes"),

An array is a component (an App::Link with ElementCount elements, UtilsAssembly.isLinkArray): the solver moves it as one
body, its part repeated at each element's placement (LinkArray::getElementPlacements, then syncGeneratedElementPlacements
writes them onto the elements). A direction or axis is a role of the Assembly's Origin ("X_Axis", "Y_Axis", "Z_Axis");
none is X (the second direction Y) for a linear array, Z for a polar one, as LinkArrayLinear's
calculateOffsetVectorWithDefault and LinkArrayPolar::getRotation default them.

A Path or Point Link Array's Path / PointObject is an object with a shape (a Part::Feature: FreeCAD refuses a Link), so
here a part of the project, its shape where its part file builds it (as FreeCAD links the Body itself, not the placed
component), with the path's edges by name ("Edge1"; none: its first wire, else its edges) or the points' vertices.
"""
from __future__ import annotations

from . import assembly_wb as W

AXES = ("X_Axis", "Y_Axis", "Z_Axis")
MODES = ("Extent", "Spacing")


class LinkArray(W.Link):
    """Part::LinkArray: an App::Link whose elements are its part at the placements the pattern computes."""
    PATTERN: dict = {}

    def validate(self):
        super().validate()
        for k in self.REF_KEYS:
            v = getattr(self, k)
            if v is not None and v not in AXES:
                raise W.AssemblyError(f"{self.name}: {k} is one of the Origin's axes ({', '.join(AXES)}), not {v!r}")
        for k in ("mode", "mode2"):
            if k in self.DEFAULTS and getattr(self, k) not in MODES:
                raise W.AssemblyError(f"{self.name}: {k} {getattr(self, k)!r} is not one of {', '.join(MODES)}")

    def pattern(self):
        raise NotImplementedError

    def needs(self) -> list[str]:
        """The parts besides its own whose shapes its placements read (a Path's path, a Point's points)."""
        return []

    def _shape_of(self, part, what):
        doc = getattr(self, "_doc", None)
        shapes = doc.shapes if doc is not None else self.__dict__.setdefault("_shapes", {})
        slug = doc.document if doc is not None else getattr(self, "_slug", None)
        if part not in shapes and slug:
            from .state import build_part
            shapes[part] = build_part(slug, part)[0].wrapped
        if part not in shapes:
            raise W.AssemblyError(f"{self.name}: {what} {part!r} is not built")
        return shapes[part]

    def element_placements(self) -> list:
        """getElementPlacements: each element's Placement in the array (Placement first, then each of them)."""
        from . import feature  # noqa: F401  (feature_transform is imported through it)
        from . import feature as F
        from .attacher import Placement
        try:
            trsfs = self.pattern().get_transformations({}, {}, [])
        except F.FeatureError as e:
            raise W.AssemblyError(f"{self.name}: {e}") from None
        return [Placement.from_trsf(t) for t in trsfs]

    def shape(self, base):
        """The array as the solver and the 3D view see it: base at every element placement, one compound."""
        from OCP.BRep import BRep_Builder
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
        from OCP.TopoDS import TopoDS_Compound
        comp = TopoDS_Compound()
        b = BRep_Builder()
        b.MakeCompound(comp)
        for p in self.element_placements():
            b.Add(comp, BRepBuilderAPI_Transform(base, p.trsf(), True).Shape())
        return comp


class LinkArrayLinear(LinkArray):
    """Part::LinkArrayLinear (Part_LinkArrayLinear, "Linear Link Array")."""
    kind = "LinkArrayLinear"
    TYPE_ID = "Part::LinkArrayLinear"
    REF_KEYS = ("direction", "direction2")
    DEFAULTS = {**W.Link.DEFAULTS, "direction": None, "reversed": False, "mode": "Extent", "length": 100.0,
                "offset": 10.0, "spacings": (-1.0,), "spacing_pattern": (0.0,), "occurrences": 2,
                "direction2": None, "reversed2": False, "mode2": "Extent", "length2": 100.0, "offset2": 10.0,
                "spacings2": (0.0,), "spacing_pattern2": (0.0,), "occurrences2": 1}
    TRANSACTION = "Linear Link Array"

    def pattern(self):
        from . import feature_transform as FT
        # calculateOffsetVectorWithDefault: no direction is X (the second Y)
        return FT.LinearPattern(self.name, direction=self.direction or "X_Axis",
                                direction2=self.direction2 or "Y_Axis",
                                **{k: getattr(self, k) for k in ("reversed", "mode", "length", "offset", "occurrences",
                                                                 "reversed2", "mode2", "length2", "offset2",
                                                                 "occurrences2")},
                                spacings=tuple(self.spacings), spacing_pattern=tuple(self.spacing_pattern),
                                spacings2=tuple(self.spacings2), spacing_pattern2=tuple(self.spacing_pattern2))


class LinkArrayPolar(LinkArray):
    """Part::LinkArrayPolar (Part_LinkArrayPolar, "Polar Link Array")."""
    kind = "LinkArrayPolar"
    TYPE_ID = "Part::LinkArrayPolar"
    REF_KEYS = ("axis",)
    DEFAULTS = {**W.Link.DEFAULTS, "axis": None, "reversed": False, "mode": "Extent", "angle": 360.0,
                "offset": 120.0, "spacings": (-1.0, -1.0), "spacing_pattern": (0.0,), "occurrences": 3}
    TRANSACTION = "Polar Link Array"

    def pattern(self):
        from . import feature_transform as FT
        # getRotation: no axis is gp_Ax2(), the Z axis through the origin
        return FT.PolarPattern(self.name, axis=self.axis,
                               **{k: getattr(self, k) for k in ("reversed", "mode", "angle", "offset", "occurrences")},
                               spacings=tuple(self.spacings), spacing_pattern=tuple(self.spacing_pattern))


class LinkArrayCircular(LinkArray):
    """Part::LinkArrayCircular (Part_LinkArrayCircular, "Circular Link Array"): concentric circles about an axis,
    CircularPatternExtension::calculateTransformations."""
    kind = "LinkArrayCircular"
    TYPE_ID = "Part::LinkArrayCircular"
    REF_KEYS = ("axis",)
    DEFAULTS = {**W.Link.DEFAULTS, "axis": None, "radial_distance": 50.0, "tangential_distance": 25.0,
                "number_circles": 3, "symmetry": 1}
    TRANSACTION = "Circular Link Array"
    MAXIMUM_OCCURRENCES = 10000          # PatternConstants::MaximumOccurrences

    def element_placements(self) -> list:
        import math
        from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
        from .attacher import Placement
        radial, tangential = float(self.radial_distance), float(self.tangential_distance)
        circles, symmetry = int(self.number_circles), max(1, int(self.symmetry))
        conf = 1e-7
        if not math.isfinite(radial) or radial <= conf:
            raise W.AssemblyError(f"{self.name}: Radial distance must be greater than zero")
        if not math.isfinite(tangential) or tangential <= conf:
            raise W.AssemblyError(f"{self.name}: Tangential distance must be greater than zero")
        if circles < 2:
            raise W.AssemblyError(f"{self.name}: At least two concentric circles are required")
        if circles > self.MAXIMUM_OCCURRENCES:
            raise W.AssemblyError(f"{self.name}: Circular pattern would create more than "
                                  f"{self.MAXIMUM_OCCURRENCES} circles")
        # getRotation: no reference, the role's axis through the origin (Z for none or Z_Axis: gp_Ax2())
        d = {"X_Axis": (1.0, 0.0, 0.0), "Y_Axis": (0.0, 1.0, 0.0)}.get(self.axis, (0.0, 0.0, 1.0))
        direction, center = gp_Dir(*d), gp_Pnt()
        lead = gp_Dir(1.0, 0.0, 0.0) if abs(direction.X()) <= conf and abs(direction.Z()) <= conf \
            else gp_Dir(0.0, 1.0, 0.0)
        radial_dir = gp_Vec(direction).Crossed(gp_Vec(lead))
        radial_dir.Normalize()
        out = [gp_Trsf()]
        full = 2.0 * math.acos(-1.0)
        for circle in range(1, circles):
            radius = circle * radial
            requested = math.floor(full * radius / tangential)
            if not math.isfinite(requested) or requested > self.MAXIMUM_OCCURRENCES \
                    or len(out) + requested > self.MAXIMUM_OCCURRENCES:
                raise W.AssemblyError(f"{self.name}: Circular pattern would create more than "
                                      f"{self.MAXIMUM_OCCURRENCES} occurrences")
            count = int(requested) // symmetry * symmetry
            if count == 0:
                continue
            translation = gp_Trsf()
            translation.SetTranslation(radial_dir.Multiplied(radius))
            step = full / count
            for k in range(count):
                rotation = gp_Trsf()
                rotation.SetRotation(gp_Ax1(center, direction), k * step)
                rotation.Multiply(translation)
                out.append(rotation)
        return [Placement.from_trsf(t) for t in out]


CONF = 1e-7                              # Precision::Confusion()


def _ref(v):
    """A Path: "part", ("part", "Edge1") or ("part", ["Edge1", "Edge2"]), as (part, (subs...))."""
    if v is None:
        return None
    if isinstance(v, str):
        return (v, ())
    part, subs = v
    return (str(part), tuple([subs] if isinstance(subs, str) else (subs or ())))


class LinkArrayPath(LinkArray):
    """Part::LinkArrayPath (Part_LinkArrayPath, "Path Link Array"): PathPatternExtension's occurrences along a path."""
    kind = "LinkArrayPath"
    TYPE_ID = "Part::LinkArrayPath"
    REF_KEYS = ()
    SPACING = ("Fixed count", "Fixed spacing", "Fixed count and spacing")
    DEFAULTS = {**W.Link.DEFAULTS, "path": None, "count": 4, "spacing_mode": "Fixed count", "spacing": 20.0,
                "start_offset": 0.0, "end_offset": 0.0, "reverse_path": False, "align": False,
                "vertical_vector": (0.0, 0.0, 1.0)}
    TRANSACTION = "Path Link Array"

    def normalize(self, key, v):
        if key == "path":
            return _ref(v)
        if key == "vertical_vector":
            return tuple(float(c) for c in v)
        if key == "count":
            return max(1, int(v))                    # intCount: {1, max, 1}
        return super().normalize(key, v)

    def validate(self):
        super().validate()
        if self.spacing_mode not in self.SPACING:
            raise W.AssemblyError(f"{self.name}: spacing_mode {self.spacing_mode!r} is not one of {', '.join(self.SPACING)}")

    def needs(self):
        return [self.path[0]] if self.path else []

    def source_value(self, key, v=None):
        v = getattr(self, key) if v is None else v
        if key == "path" and v is not None:
            return v[0] if not v[1] else (v[0], v[1][0] if len(v[1]) == 1 else list(v[1]))
        if key == "vertical_vector":
            return list(v)
        return super().source_value(key, v)

    def element_placements(self) -> list:
        from .attacher import Placement
        if self.path is None:                        # calculateTransformations: no Path, no occurrences
            return []
        try:
            trsfs = path_transformations(self._shape_of(self.path[0], "path"), self.path[1], self)
        except ValueError as e:
            raise W.AssemblyError(f"{self.name}: {e}") from None
        return [Placement.from_trsf(t) for t in trsfs]


def _path_edges(shape, subs):
    """getPathEdges: the named edges, else the first wire's (BRepTools_WireExplorer), else every edge; chained end to
    end, each reversed where it runs the other way."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepTools import BRepTools_WireExplorer
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_WIRE
    from OCP.TopExp import TopExp
    from OCP.TopoDS import TopoDS, TopoDS_Vertex
    from . import feature as F
    from .feature_part import sub_shape
    if shape is None or shape.IsNull():
        raise ValueError("Path shape is empty")
    edges = []
    for sub in subs:
        if not sub:
            continue
        try:
            e = sub_shape(shape, sub)
        except F.FeatureError as err:
            raise ValueError(str(err)) from None
        if e.ShapeType() != TopAbs_EDGE:
            raise ValueError("Path subelements must be edges")
        edges.append(TopoDS.Edge(e))
    if not edges:
        wires = F._subs(shape, TopAbs_WIRE)
        if wires:
            ex = BRepTools_WireExplorer(TopoDS.Wire(wires[0]))
            while ex.More():
                edges.append(ex.Current())
                ex.Next()
        else:
            edges = [TopoDS.Edge(e) for e in F._subs(shape, TopAbs_EDGE)]
    if not edges:
        raise ValueError("Path does not contain edges")

    def ends(e):
        a, b = TopoDS_Vertex(), TopoDS_Vertex()
        TopExp.Vertices_s(e, a, b, True)
        return a, b

    def same(a, b):
        return BRep_Tool.Pnt_s(a).Distance(BRep_Tool.Pnt_s(b)) <= CONF

    out = [edges.pop(0)]
    while edges:
        first, last = ends(out[0])[0], ends(out[-1])[1]
        for i, c in enumerate(edges):
            cf, cl = ends(c)
            if same(last, cf):
                out.append(c)
            elif same(last, cl):
                out.append(TopoDS.Edge(c.Reversed()))
            elif same(first, cl):
                out.insert(0, c)
            elif same(first, cf):
                out.insert(0, TopoDS.Edge(c.Reversed()))
            else:
                continue
            edges.pop(i)
            break
        else:
            raise ValueError("Path edges must form one connected path")
    return out


def _edge_length(e):
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GCPnts import GCPnts_AbscissaPoint
    c = BRepAdaptor_Curve(e)
    return GCPnts_AbscissaPoint.Length_s(c, c.FirstParameter(), c.LastParameter(), CONF)


def path_transformations(shape, subs, a) -> list:
    """PathPatternExtension::calculateTransformations(false): a frame at each distance along the path."""
    import bisect
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GCPnts import GCPnts_AbscissaPoint
    from OCP.TopAbs import TopAbs_REVERSED
    from OCP.TopExp import TopExp
    from OCP.TopoDS import TopoDS, TopoDS_Vertex
    from OCP.gp import gp_Dir, gp_Mat, gp_Pnt, gp_Quaternion, gp_Trsf, gp_Vec
    from OCP.BRep import BRep_Tool
    edges = _path_edges(shape, subs)
    if a.reverse_path:
        edges = [TopoDS.Edge(e.Reversed()) for e in reversed(edges)]
    ends, total = [], 0.0
    for e in edges:
        total += _edge_length(e)
        ends.append(total)
    if total <= CONF:
        raise ValueError("Path length must be greater than zero")
    v0, v1, ign = TopoDS_Vertex(), TopoDS_Vertex(), TopoDS_Vertex()
    TopExp.Vertices_s(edges[0], v0, ign, True)
    TopExp.Vertices_s(edges[-1], ign, v1, True)
    closed = not v0.IsNull() and not v1.IsNull() and BRep_Tool.Pnt_s(v0).Distance(BRep_Tool.Pnt_s(v1)) <= CONF
    start, end, count, spacing = float(a.start_offset), float(a.end_offset), int(a.count), float(a.spacing)
    # calculateDistances
    if start < 0.0 or end < 0.0:
        raise ValueError("Path offsets cannot be negative")
    if start + end > total + CONF:
        raise ValueError("Path offsets exceed the path length")
    available = max(0.0, total - start - end)
    dist = []
    if a.spacing_mode == "Fixed count":
        segments = max(1, count if closed and start == 0.0 and end == 0.0 else count - 1)
        step = available / segments
        dist = [start + i * step for i in range(count)]
    else:
        if spacing <= CONF:
            raise ValueError("Path spacing must be greater than zero")
        maximum = count if a.spacing_mode == "Fixed count and spacing" else None
        i = 0
        while maximum is None or i < maximum:
            d = start + i * spacing
            if d > start + available + CONF:
                break
            dist.append(d)
            if len(dist) > LinkArrayCircular.MAXIMUM_OCCURRENCES:
                raise ValueError(f"Path pattern would create more than {LinkArrayCircular.MAXIMUM_OCCURRENCES} "
                                 "occurrences")
            i += 1
    if not dist:
        raise ValueError("Path pattern produced no occurrences")
    out = []
    vert = gp_Vec(*a.vertical_vector)
    for d in dist:
        # frameAt
        k = bisect.bisect_left(ends, d - CONF)
        index = len(edges) - 1 if k == len(ends) else k
        edge_start = 0.0 if index == 0 else ends[index - 1]
        local = min(max(d - edge_start, 0.0), _edge_length(edges[index]))
        c = BRepAdaptor_Curve(edges[index])
        rev = edges[index].Orientation() == TopAbs_REVERSED
        p0 = c.LastParameter() if rev else c.FirstParameter()
        u = p0
        if local > CONF:
            pt = GCPnts_AbscissaPoint(c, -local if rev else local, p0)
            if not pt.IsDone():
                raise ValueError("Failed to evaluate point on path")
            u = pt.Parameter()
        pos, tan = gp_Pnt(), gp_Vec()
        c.D1(u, pos, tan)
        if rev:
            tan.Reverse()
        t = gp_Trsf()
        if a.align:
            if tan.Magnitude() <= CONF:
                raise ValueError("Path tangent is null")
            x = gp_Dir(tan)
            z = gp_Vec(vert.X(), vert.Y(), vert.Z())
            z = z.Subtracted(gp_Vec(x).Multiplied(z.Dot(gp_Vec(x))))      # (OCP's -= returns None)
            if z.Magnitude() <= CONF:
                z = gp_Vec(0.0, 0.0, 1.0) if abs(x.Z()) < 0.9 else gp_Vec(0.0, 1.0, 0.0)
                z = z.Subtracted(gp_Vec(x).Multiplied(z.Dot(gp_Vec(x))))
            zd = gp_Dir(z)
            yd = gp_Dir(gp_Vec(zd).Crossed(gp_Vec(x)))
            t.SetRotation(gp_Quaternion(gp_Mat(x.X(), yd.X(), zd.X(), x.Y(), yd.Y(), zd.Y(), x.Z(), yd.Z(), zd.Z())))
        t.SetTranslationPart(gp_Vec(pos.X(), pos.Y(), pos.Z()))
        out.append(t)
    return out


class LinkArrayPoint(LinkArray):
    """Part::LinkArrayPoint (Part_LinkArrayPoint, "Point Link Array"): an occurrence at each distinct vertex of the
    PointObject (PointPatternExtension::calculateTransformations(false))."""
    kind = "LinkArrayPoint"
    TYPE_ID = "Part::LinkArrayPoint"
    REF_KEYS = ()
    DEFAULTS = {**W.Link.DEFAULTS, "point_object": None}
    TRANSACTION = "Point Link Array"

    def needs(self):
        return [self.point_object] if self.point_object else []

    def element_placements(self) -> list:
        from OCP.BRep import BRep_Tool
        from OCP.TopAbs import TopAbs_VERTEX
        from OCP.TopoDS import TopoDS
        from OCP.gp import gp_Trsf, gp_Vec
        from .attacher import Placement
        if not self.point_object:
            return []
        shape = self._shape_of(self.point_object, "point object")
        if shape is None or shape.IsNull():
            raise W.AssemblyError(f"{self.name}: Point object shape is empty")
        pts = []
        from . import feature as F
        for v in F._subs(shape, TopAbs_VERTEX):           # getSubShapes(TopAbs_VERTEX): the indexed map's order
            p = BRep_Tool.Pnt_s(TopoDS.Vertex(v))
            if not any(p.Distance(q) <= CONF for q in pts):
                pts.append(p)
        if not pts:
            raise W.AssemblyError(f"{self.name}: Point object does not contain vertices")
        out = []
        for p in pts:
            t = gp_Trsf()
            t.SetTranslation(gp_Vec(p.X(), p.Y(), p.Z()))
            out.append(Placement.from_trsf(t))
        return out


# activateLinkArrayCommand's object names
NAMES = {"LinkArrayLinear": "LinearLinkArray", "LinkArrayPolar": "PolarLinkArray", "LinkArrayCircular": "CircularLinkArray",
         "LinkArrayPath": "PathLinkArray", "LinkArrayPoint": "PointLinkArray"}


def insert_array(doc, kind: str, part: str | None, shape, props: dict | None = None, name: str | None = None):
    """Part_LinkArrayLinear / Part_LinkArrayPolar with a part selected, the Assembly active: addObject(type, name),
    LinkedObject = the part, activeAsm.addObject(obj); then the panel's settings. Its Label is its Name (LinkArray's
    onChanged keeps the Label when LinkedObject is set)."""
    cls = W.CLASSES.get(kind)
    if cls is None or not issubclass(cls, LinkArray):
        raise W.AssemblyError(f"{kind!r} is not a link array ({', '.join(NAMES)})")
    if not part:
        raise W.AssemblyError("a link array here repeats a part of the project: select one")
    name = name or W.unique_name(doc.all_names(), NAMES[kind])
    a = cls(name, part, **(props or {}))
    a._doc = doc
    if shape is not None:
        doc.shapes[part] = shape
    doc.objects.append(a)
    doc.plc[a.name] = W.to_placement(a.placement)
    return a


W.CLASSES[LinkArrayLinear.kind] = LinkArrayLinear
W.CLASSES[LinkArrayPolar.kind] = LinkArrayPolar
W.CLASSES[LinkArrayCircular.kind] = LinkArrayCircular
W.LinkArray, W.LinkArrayLinear, W.LinkArrayPolar = LinkArray, LinkArrayLinear, LinkArrayPolar
W.LinkArrayCircular = LinkArrayCircular
W.CLASSES[LinkArrayPath.kind] = LinkArrayPath
W.CLASSES[LinkArrayPoint.kind] = LinkArrayPoint
W.LinkArrayPath, W.LinkArrayPoint = LinkArrayPath, LinkArrayPoint

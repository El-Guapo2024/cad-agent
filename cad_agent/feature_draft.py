# SPDX-License-Identifier: LGPL-2.1-or-later
# Draft workbench objects in a part file. Their shapes are FreeCAD's own Draft Python (cad_agent/fcdraft/Mod/Draft,
# https://github.com/FreeCAD/FreeCAD commit 3160daf1e2b6, LGPL-2.1-or-later, vendored unchanged): each object's proxy
# (draftobjects/rectangle.py, array.py, clone.py, ...) runs its execute over the stand-ins (cad_agent/fcshim).
"""FreeCAD's Draft objects beside the Part objects of a part file's OBJECTS, under the name Draft:

    from cad_agent import feature_draft as Draft

    OBJECTS = [
        Draft.Rectangle("Rectangle", length=40, height=20, fillet_radius=2),
        Draft.Wire("Wire", points=[(0, 0, 0), (10, 0, 0), (10, 5, 0)], closed=True),
        Draft.Circle("Circle", radius=5, placement=((20, 10, 0), (0, 0, 0))),
        Draft.Array("Array", "Circle", array_type="polar", number_polar=6),
        Draft.Clone("Clone", ["Rectangle"], scale=(2, 1, 1)),
    ]

Every object is its proxy's FreeCAD object (Part::Part2DObjectPython or Part::FeaturePython with draftobjects' class
as Proxy, as its draftmake maker adds it; its TypeId here is "Draft::" and the proxy's type, as a FeaturePython's names
no type), the keywords its properties in snake_case with the defaults the proxy's __init__ gives a fresh object (not
the Draft preferences the GUI commands read: a Draft_Rectangle's MakeFace comes from "fillmode", here it is the
property's own True). Read-only results (Area, a Wire's Length, an Array's Count and PlacementList) are not keywords.

The shapes are built by running the proxies: the document's Draft objects, in order, in one stand-in document, a
linked Part object or sketch as a Part::Feature holding its placed shape. An object's Placement is the one its execute
leaves (an Array or a Clone may set it); attachment of a Draft object is not supported (MapMode stays Deactivated).
"""
from __future__ import annotations

from . import feature as F
from .feature_part import PartObject, snake

OBJECTS: dict = {}

_SKIP = ("Area", "ShapeMaterial", "_ElementMapVersion", "PlacementList", "Count")


class DraftObject(PartObject):
    """A Draft object: PROXY (draftobjects module, class) on FC_TYPE, its properties set, then the proxy's execute."""
    FC_TYPE = "Part::Part2DObjectPython"
    PROXY: tuple = ()
    VECTORS: tuple = ()             # keys that are a Vector ((x, y, z))
    VECTOR_LISTS: tuple = ()        # keys that are a list of Vectors
    ATTACH_EXT = False              # its maker adds Part::AttachExtensionPython to a Part::FeaturePython
    TYPE_ID = ""                    # "Draft::" and the proxy's type (FreeCAD's utils.get_type), one per kind
    INPUTS: tuple = ()
    HIDES: tuple = ()

    def normalize(self, key, v):
        if key in self.VECTORS:
            try:
                return tuple(float(c) for c in v)
            except (TypeError, ValueError):
                raise F.FeatureError(f"{self.name}: {key} {v!r} is not (x, y, z)") from None
        if key in self.VECTOR_LISTS:
            try:
                return tuple(tuple(float(c) for c in p) for p in (v or ()))
            except (TypeError, ValueError):
                raise F.FeatureError(f"{self.name}: {key} {v!r} is not a list of (x, y, z)") from None
        return super().normalize(key, v)

    def validate(self):
        super().validate()
        if self.attachment_support or self.map_mode != "Deactivated":
            raise F.FeatureError(f"{self.name}: a Draft object's attachment is not supported here")

    # ── the build: the proxy's execute over the stand-ins ──
    def _built(self, ctx, params):
        cache = ctx.__dict__.setdefault("_draft", {})
        if self.name not in cache:
            cache[self.name] = _run(self, ctx, params)
        return cache[self.name]

    def built_shape(self, ctx, params):
        from OCP.TopLoc import TopLoc_Location
        obj, pl = self._built(ctx, params)
        s = obj.Shape._s
        if s.IsNull():
            raise F.FeatureError(f"{self.name}: no shape")
        return s.Moved(TopLoc_Location(pl.inverse().trsf()))

    def base_placement(self, ctx, params):
        return self._built(ctx, params)[1]

    def fc_type(self, linked):
        """The FreeCAD type its maker adds, given the objects it links (a Clone's depends on them)."""
        return self.FC_TYPE

    # ── freecadcmd, for the goldens ──
    def to_freecad(self, fc):
        linked = [fc.made[n] for k in self.REFS if k not in self.ATTACH
                  for n in (getattr(self, k) if self.is_ref_list(k) else [getattr(self, k)]) if n]
        self.FC_TYPE = self.fc_type(linked)
        return super().to_freecad(fc)

    def fc_setup(self, obj, fc):
        import importlib
        if self.ATTACH_EXT and obj.TypeId == _PY:       # make_wire, make_bspline, make_bezcurve, make_clone
            obj.addExtension("Part::AttachExtensionPython")
        getattr(importlib.import_module("draftobjects." + self.PROXY[0]), self.PROXY[1])(obj)

    def fc_props(self):
        for k in self.DEFAULTS:
            if k in self.REFS or k in ("label", "placement", "visibility") or k in self.ATTACH:
                continue
            yield self.prop_name(k), k, getattr(self, k)


def _value(o, key, v, params, App):
    if key in o.VECTORS:
        return App.Vector(*v)
    if key in o.VECTOR_LISTS:
        return [App.Vector(*p) for p in v]
    if isinstance(v, str) and key not in o.ENUMS:
        return F.value(v, params, f"{o.name}.{key}")
    if isinstance(v, tuple):
        return list(v)
    return v


def _run(o, ctx, params):
    """The object made in the context's stand-in document, its properties and links set, recomputed: (object, the
    Placement it is left at, as attacher.Placement)."""
    from . import attacher as A
    from . import draft_runtime
    draft_runtime.activate()
    import FreeCAD as App
    import Part
    st = ctx.__dict__.setdefault("_draft_doc", {})
    if "doc" not in st:
        st["doc"], st["objs"] = App.newDocument("DraftParts"), {}
    doc, objs = st["doc"], st["objs"]

    def link(name):
        if name in objs:
            return objs[name]
        f = doc.addObject("Part::Feature", name)
        f.Shape = Part.Shape(ctx.shape(name, f"{o.name}: link"))
        objs[name] = f
        return f

    links = {}
    for key in o.REFS:
        v = getattr(o, key)
        if key in o.ATTACH or v in (None, (), []):
            continue
        links[key] = [link(n) for n in v] if o.is_ref_list(key) else link(v)
    linked = [x for v in links.values() for x in (v if isinstance(v, list) else [v])]
    obj = doc.addObject(o.fc_type(linked), o.name)
    o.fc_setup(obj, None)
    for prop, key, v in o.fc_props():
        setattr(obj, prop, _value(o, key, v, params, App))
    for key, v in links.items():
        setattr(obj, o.prop_name(key), v)
    if o.placement is not None:
        (x, y, z), ypr = o.placement
        obj.Placement = App.Placement(App.Vector(x, y, z), App.Rotation(*ypr))
    objs[o.name] = obj
    doc.recompute()
    err = [e for e in getattr(doc, "_errors", []) if e[0] == o.name]
    if err:
        raise F.FeatureError(f"{o.name}: {err[-1][1]}")
    p = obj.Placement
    q = p.Rotation.Q
    return obj, A.Placement((p.Base.x, p.Base.y, p.Base.z), A.Rotation(tuple(q)))


def register(*classes):
    from . import feature_part as Part
    for c in classes:
        OBJECTS[c.kind] = c
        globals()[c.kind.split(".", 1)[1]] = c
        F.FEATURES[c.kind] = c
        for t in (_2D, _PY):                # the FreeCAD type the object is made as (a Clone's is either)
            Part.ENUM_PROPS[t] = set(Part.ENUM_PROPS.get(t, ())) | {c.prop_name(k) for k in c.ENUMS}
    return classes


def _kind(name, proxy, fc_type, defaults, refs=(), ref_lists=(), vectors=(), vector_lists=(), enums=None, pos=()):
    cls = type(name, (DraftObject,), {
        "__doc__": f"Draft's {name} (draftobjects/{proxy[0]}.py, {proxy[1]}) on a {fc_type}.",
        "kind": f"Draft.{name}", "TYPE_ID": f"Draft::{name}", "FC_TYPE": fc_type, "PROXY": proxy,
        "TRANSACTION": f"Create {name}", "POS": pos, "REFS": tuple(refs) + tuple(ref_lists),
        "INPUTS": tuple(refs) + tuple(ref_lists), "HIDES": tuple(refs) + tuple(ref_lists),
        "VECTORS": tuple(vectors), "VECTOR_LISTS": tuple(vector_lists), "ENUMS": enums or {},
        "DEFAULTS": {**defaults, **PartObject.COMMON}})
    return cls


_2D = "Part::Part2DObjectPython"
_PY = "Part::FeaturePython"
Rectangle = _kind("Rectangle", ("rectangle", "Rectangle"), _2D, {
    "length": 1.0, "height": 1.0, "fillet_radius": 0.0, "chamfer_size": 0.0, "make_face": True,
    "rows": 1, "columns": 1})
Wire = _kind("Wire", ("wire", "Wire"), _PY, {
    "points": (), "closed": False, "make_face": True, "fillet_radius": 0.0, "chamfer_size": 0.0,
    "subdivisions": 0}, vector_lists=("points",))
Circle = _kind("Circle", ("circle", "Circle"), _2D, {
    "radius": 0.0, "first_angle": 0.0, "last_angle": 0.0, "make_face": True})
Ellipse = _kind("Ellipse", ("ellipse", "Ellipse"), _2D, {
    "major_radius": 0.0, "minor_radius": 0.0, "first_angle": 0.0, "last_angle": 0.0, "make_face": True})
Polygon = _kind("Polygon", ("polygon", "Polygon"), _2D, {
    "faces_number": 0, "radius": 1.0, "draw_mode": "inscribed", "fillet_radius": 0.0, "chamfer_size": 0.0,
    "make_face": True}, enums={"draw_mode": ("inscribed", "circumscribed")})
BSpline = _kind("BSpline", ("bspline", "BSpline"), _PY, {
    "points": (), "closed": False, "make_face": True, "parameterization": 1.0}, vector_lists=("points",))
BezCurve = _kind("BezCurve", ("bezcurve", "BezCurve"), _PY, {
    "points": (), "degree": 3, "continuity": (), "closed": False, "make_face": True}, vector_lists=("points",))
Point = _kind("Point", ("point", "Point"), _PY, {"x": 0.0, "y": 0.0, "z": 0.0})
Array = _kind("Array", ("array", "Array"), _PY, {
    "base": None, "array_type": "ortho", "fuse": False,
    "number_x": 2, "number_y": 2, "number_z": 1, "interval_x": (50.0, 0.0, 0.0), "interval_y": (0.0, 50.0, 0.0),
    "interval_z": (0.0, 0.0, 50.0), "axis": (0.0, 0.0, 1.0), "center": (0.0, 0.0, 0.0), "number_polar": 5,
    "angle": 360.0, "interval_axis": (0.0, 0.0, 0.0), "radial_distance": 50.0, "tangential_distance": 25.0,
    "number_circles": 3, "symmetry": 1}, refs=("base",), pos=("base",),
    vectors=("interval_x", "interval_y", "interval_z", "axis", "center", "interval_axis"),
    enums={"array_type": ("ortho", "polar", "circular")})
PathArray = _kind("PathArray", ("patharray", "PathArray"), _PY, {
    "base": None, "path_object": None, "count": 4, "align": False, "align_mode": "Original", "fuse": False,
    "spacing_mode": "Fixed count", "spacing_unit": 20.0, "use_spacing_pattern": False, "spacing_pattern": (1.0, 2.0),
    "start_offset": 0.0, "end_offset": 0.0, "extra_translation": (0.0, 0.0, 0.0), "tangent_vector": (1.0, 0.0, 0.0),
    "force_vertical": False, "vertical_vector": (0.0, 0.0, 1.0), "reverse_path": False},
    refs=("base", "path_object"), pos=("base", "path_object"),
    vectors=("extra_translation", "tangent_vector", "vertical_vector"),
    enums={"align_mode": ("Original", "Frenet", "Tangent"),
           "spacing_mode": ("Fixed count", "Fixed spacing", "Fixed count and spacing")})
PointArray = _kind("PointArray", ("pointarray", "PointArray"), _PY, {
    "base": None, "point_object": None, "fuse": False}, refs=("base", "point_object"), pos=("base", "point_object"))
Clone = _kind("Clone", ("clone", "Clone"), _2D, {
    "objects": (), "scale": (1.0, 1.0, 1.0), "fuse": False, "force_compound": False},
    ref_lists=("objects",), pos=("objects",), vectors=("scale",))



def _clone_type(self, linked):
    """make_clone: a Part::Part2DObjectPython ("Clone2D") for one Part2DObject that is not a BezCurve, BSpline or Wire,
    else a Part::FeaturePython."""
    import importlib
    utils = importlib.import_module("draftutils.utils")
    if len(linked) == 1 and linked[0].isDerivedFrom("Part::Part2DObject") \
            and utils.get_type(linked[0]) not in ("BezCurve", "BSpline", "Wire"):
        return _2D
    return _PY


Clone.fc_type = _clone_type
# the array makers hide their Base (make_array, make_path_array, make_point_array: Base.ViewObject.hide()), the tree
# shows it under the array; make_clone hides nothing
Array.HIDES = PathArray.HIDES = PointArray.HIDES = ("base",)
Array.INPUTS = PathArray.INPUTS = PointArray.INPUTS = ("base",)
Clone.INPUTS, Clone.HIDES = ("objects",), ()      # ViewProviderDraft.claimChildren: Base and Objects
Wire.ATTACH_EXT = BSpline.ATTACH_EXT = BezCurve.ATTACH_EXT = Clone.ATTACH_EXT = True
# a PathArray's Count is a property the user sets (the number of copies), not the read-only result an Array's is
PathArray.PROPS = {"count": "Count"}
register(Rectangle, Wire, Circle, Ellipse, Polygon, BSpline, BezCurve, Point, Array, PathArray, PointArray, Clone)

assert all(snake(c.prop_name(k)) == k for c in OBJECTS.values() for k in c.DEFAULTS
           if k not in PartObject.COMMON), "a Draft keyword that is not its property's snake_case"

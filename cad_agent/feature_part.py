# SPDX-License-Identifier: LGPL-2.1-or-later
# A port of FreeCAD's Part workbench objects (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), each file
# LGPL-2.1-or-later as it states:
#   src/Mod/Part/App/PartFeature.cpp: Copyright (c) 2002 Jürgen Riegel
#   src/App/Document.cpp: Copyright (c) 2002 Jürgen Riegel
#   src/Mod/Part/Gui/ViewProviderBoolean.cpp, ViewProviderExtrusion.cpp, ...: claimChildren, which inputs the tree hides
"""FreeCAD's Part workbench objects in a part file: a document of Part objects outside any Body.

PartDesign's Body is one ordered history (cad_agent/feature.py's FEATURES). Part objects are not: each one is built
from the objects it links (a Cut from its Base and Tool, a Fusion from its Shapes, an Extrude from its Base), so the
document is a graph. A part file holds them as a second list, OBJECTS, in FreeCAD's document order (the order they
were made in, each one after the objects it links), with FreeCAD's Python vocabulary under the name Part:

    from cad_agent import feature_part as Part
    from cad_agent.feature import Constraint, LineSegment, Sketch

    PARAMS = {"r": 3.0}

    OBJECTS = [
        Part.Box("Box", length=40, width=20, height=5, label="Cube"),
        Part.Cylinder("Cylinder", radius="r", height=5, placement=((8, 10, 0), (0, 0, 0))),
        Part.Cut("Cut", "Box", "Cylinder"),
        Sketch("Sketch", support="XY", geometry=[...], constraints=[...]),
        Part.Extrusion("Extrude", "Sketch", length_fwd=10, solid=True),
    ]


    def build(**p):
        return Part.Document(OBJECTS, p)

- Every object is a call whose first argument is its Name; the keywords are FreeCAD's properties in snake_case
  (LengthFwd -> length_fwd), with FreeCAD's defaults, which the file leaves out. A link is the linked object's Name,
  a link with sub-elements (name, "Edge3") or (name, ["Edge1", "Edge2"]) as FreeCAD's Python writes PropertyLinkSub.
  label= is FreeCAD's Label when it is not the Name (Part_Box names its object Box and labels it "Cube").
  visibility= is the object's ViewObject.Visibility once someone toggled it; left out, an object is shown unless an
  object that links it hides it, as that object's FreeCAD command does (a Cut hides its Base and Tool, a Mirror leaves
  its source shown).
- A sketch outside a Body is a Sketcher::SketchObject in the document (Part workbench's Sketcher_NewSketch), the
  same Sketch(...) call as in FEATURES. Its Shape is its wires, as SketchObject::buildShape makes them.
- A part file with a PartDesign Body keeps it as FEATURES and TIP; the Body is named "Body" and an object links it
  by that name (Part.Cut("Cut", "Body", "Cylinder")), or links a feature of it by the feature's name. build() is
  then `return Part.Document(OBJECTS, p, FEATURES, tip=TIP)` (and base=build_base(**p) for a hand-written base).
- The part's shape, what build() returns, is what FreeCAD shows: every visible object (and the Body, unless an object
  that hides its input links it), as one compound. Sketches are left out, as a Body's are: they are drawn, not built.

Why the namespace: a hand-written part imports build123d's Box, Cylinder, Sphere, Plane, ... and a part file that
gets Part objects on top must keep those working. `Part` is not a name any part file binds (FreeCAD's own scripts
write `import Part`, so Part.Box reads as FreeCAD's Python reads).

The objects are cad_agent.feature_kw.KwFeature classes, so cad_agent/feature_edit.py reads and writes them as it
does a Body's features (only what is not a default, in place). Their TypeId is FreeCAD's ("Part::Cut"); for the
objects FreeCAD makes in Python (Part::FeaturePython with a Proxy: Tube, BooleanFragments, Slice, XOR, the join
features, CompoundFilter) it is "Part::" and the Proxy's type, since a FeaturePython's TypeId names no type.

This module imports without build123d or OCP, as feature.py does; to_freecad() builds OBJECTS in freecadcmd.
"""
from __future__ import annotations

import ast
import math

from . import feature as F
from .feature_kw import KwFeature, ref, ref_name

try:
    from OCP.BRep import BRep_Builder
    from OCP.TopAbs import TopAbs_COMPOUND, TopAbs_EDGE, TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID, TopAbs_VERTEX, \
        TopAbs_WIRE
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS_Compound
    from OCP.gp import gp_Trsf
except ImportError:                     # pragma: no cover - only FreeCAD's Python lands here
    pass

BODY = "Body"            # the PartDesign Body's Name, when the part file has FEATURES
SUBS = {"Vertex": "TopAbs_VERTEX", "Edge": "TopAbs_EDGE", "Face": "TopAbs_FACE", "Wire": "TopAbs_WIRE",
        "Shell": "TopAbs_SHELL", "Solid": "TopAbs_SOLID"}
OBJECTS: dict = {}       # {kind ("Part.Box"): class}, every Part object


def register(*classes):
    for c in classes:
        OBJECTS[c.kind] = c
        globals()[c.kind.split(".", 1)[1]] = c
        F.FEATURES[c.kind] = c          # feature_kw.kw_class finds it, feature_edit reads and writes it
    return classes[0] if len(classes) == 1 else classes


def snake(prop: str) -> str:
    """FreeCAD's property name to the part file's keyword: LengthFwd -> length_fwd, Angle1 -> angle1."""
    out = ""
    for i, ch in enumerate(prop):
        if ch.isupper() and i and (prop[i - 1].islower() or (i + 1 < len(prop) and prop[i + 1].islower())):
            out += "_"
        out += ch.lower()
    return out


def camel(key: str) -> str:
    """The part file's keyword to FreeCAD's property name: length_fwd -> LengthFwd."""
    return "".join(w[:1].upper() + w[1:] for w in key.split("_"))


class PartObject(KwFeature):
    """A Part::Feature in the document: its shape built from its properties and the objects it links.

    A subclass declares, besides KwFeature's kind, TYPE_ID, POS, DEFAULTS and REFS:
        LABEL       the Label FreeCAD's command gives it when that is not its Name ("Cube" for Part_Box), or None
        INPUTS      the link properties whose objects the tree shows under it (its ViewProvider's claimChildren)
        HIDES       the link properties whose objects its command hides (None: INPUTS; a Mirror hides none)
        PROPS       {key: FreeCAD's property name} where camel(key) is not the name
        and shape(ctx, params): the TopoDS_Shape it makes, in the document's frame; ctx.shape(link) is a linked
        object's shape (or its sub-element's), ctx.obj(name) the object itself.
    """
    LABEL = None
    INPUTS: tuple = ()
    HIDES: tuple | None = None
    PROPS: dict = {}
    ENUMS: dict = {}                 # {key: FreeCAD's enumeration}, checked on construction
    RANGES: dict = {}                # {key: (lo, hi)}: FreeCAD's constraint, a value clamped to it
    # Every Part object has a Placement, and the Attachment editor (Part_EditAttachment) gives each one
    # AttachExtension's properties: on a Part::Primitive and a Tube FreeCAD defines them, on the others the editor adds
    # Part::AttachExtensionPython. attachment_support is AttachmentSupport, map_mode MapMode, attachment_offset
    # AttachmentOffset, map_reversed MapReversed and map_path_parameter MapPathParameter; placement is the Placement an
    # object with MapMode Deactivated keeps.
    engine = "3D"                    # AttacherEngine: Attacher::AttachEngine3D for every Part object
    ATTACH = ("attachment_support", "map_mode", "attachment_offset", "map_reversed", "map_path_parameter")
    COMMON = {"placement": None, "label": None, "visibility": None, "attachment_support": (),
              "map_mode": "Deactivated", "attachment_offset": None, "map_reversed": False,
              "map_path_parameter": 0.0}
    REFS = ("attachment_support",)

    def __init_subclass__(cls, **kw):
        super().__init_subclass__(**kw)
        cls.REFS = tuple(dict.fromkeys((*cls.REFS, "attachment_support")))

    @classmethod
    def prop_name(cls, key):
        return cls.PROPS.get(key) or camel(key)

    def normalize(self, key, v):
        if key == "placement":
            if v is None:
                return None
            try:
                if len(v) == 3 and all(isinstance(c, (int, float)) for c in v):
                    return (tuple(float(c) for c in v), (0.0, 0.0, 0.0))
                pos, ypr = v
                return (tuple(float(c) for c in pos), tuple(float(c) for c in ypr))
            except (TypeError, ValueError):
                raise F.FeatureError(f"{self.name}: placement {v!r} is not (x, y, z) or ((x, y, z), "
                                     "(yaw, pitch, roll))") from None
        if key == "attachment_support":
            from .feature_attach import support_list
            return support_list(f"{self.name}: attachment_support", v)
        if key == "map_mode":
            return v
        if key == "attachment_offset":
            return v
        if key == "map_reversed":
            return bool(v)
        if key == "map_path_parameter":
            try:
                return float(v)
            except (TypeError, ValueError):
                raise F.FeatureError(f"{self.name}: map_path_parameter {v!r} is not a number") from None
        return super().normalize(key, v)

    def validate(self):
        for k, items in self.ENUMS.items():
            v = getattr(self, k)
            if v not in items:
                raise F.FeatureError(f"{self.name}: {k} {v!r} is not one of {', '.join(map(str, items))}")
        if not isinstance(self.map_mode, str):
            raise F.FeatureError(f"{self.name}: map_mode {self.map_mode!r} is not a name")
        try:
            from . import attacher as A
        except ImportError:              # no OCP: the file is read, not built (this module imports without it)
            return
        if self.map_mode not in A.modes(self.engine):
            raise F.FeatureError(f"{self.name}: map_mode {self.map_mode!r} is not one of "
                                 f"{', '.join(A.modes(self.engine))}")

    def v(self, key, params):
        """A number property's value (a PARAMS name or expression evaluated), clamped to its range."""
        x = F.value(getattr(self, key), params, f"{self.name}.{key}")
        lo, hi = self.RANGES.get(key, (-math.inf, math.inf))
        return min(max(x, lo), hi)

    def inputs(self) -> list[str]:
        """The names of the objects the tree shows under this one (ViewProvider::claimChildren)."""
        out = []
        for k in self.INPUTS:
            val = getattr(self, k)
            for r in (val if self.is_ref_list(k) else [val]):
                n = ref_name(r)
                if n and n not in out:
                    out.append(n)
        return out

    def hidden_inputs(self) -> list[str]:
        """The objects its command hides (HIDES, INPUTS when it says nothing)."""
        keys = self.INPUTS if self.HIDES is None else self.HIDES
        out = []
        for k in keys:
            val = getattr(self, k)
            for r in (val if self.is_ref_list(k) else [val]):
                n = ref_name(r)
                if n and n not in out:
                    out.append(n)
        return out

    def shape(self, ctx, params):
        raise NotImplementedError

    def built_shape(self, ctx, params):
        """The object's shape before its Placement: its own, built from its links (evaluate places it)."""
        return self.shape(ctx, params)

    def base_placement(self, ctx, params):
        """The Placement the object sits at before its attachment: its placement=, or its Source's (a Reverse's, as
        Reverse::execute leaves the source's Placement on the object)."""
        from . import attacher as A
        return A.Placement.from_offset(getattr(self, "placement", None))

    # ── freecadcmd, for the goldens ──
    def fc_props(self):
        """(FreeCAD property, value) for each property to set on the object, links left to fc_links."""
        for k in self.DEFAULTS:
            if k in self.REFS or k in ("label", "placement", "visibility") or k in self.ATTACH:
                continue
            yield self.prop_name(k), k, getattr(self, k)

    def to_freecad(self, fc):
        obj = fc.doc.addObject(self.FC_TYPE if hasattr(self, "FC_TYPE") else self.TYPE_ID, self.name)
        self.fc_setup(obj, fc)
        for prop, k, val in self.fc_props():
            fc.setv(obj, prop, val)
        for k in self.REFS:
            if k in self.ATTACH:            # fc_attach writes AttachmentSupport, after adding the extension
                continue
            val = getattr(self, k)
            if val in (None, (), []):
                continue
            prop = self.prop_name(k)
            if self.is_ref_list(k):
                setattr(obj, prop, [fc.link(r) for r in val])
            else:
                setattr(obj, prop, fc.link(val))
        if getattr(self, "placement", None) is not None:
            (x, y, z), ypr = self.placement
            obj.Placement = fc.App.Placement(fc.App.Vector(x, y, z), fc.App.Rotation(*ypr))
        if self.attachment_support or self.map_mode != "Deactivated" or self.attachment_offset is not None \
                or self.map_reversed or self.map_path_parameter:
            self.fc_attach(obj, fc)
        if self.label:
            obj.Label = self.label
        return obj

    def fc_attach(self, obj, fc):
        """AttachExtension's properties, as the Attachment editor writes them (writeParametersToFeature): the support,
        the offset, Flip sides and the path parameter, then the MapMode that positions the object. An object FreeCAD
        does not give the extension gets Part::AttachExtensionPython, as the editor adds it."""
        App = fc.App
        if not hasattr(obj, "AttacherType"):
            obj.addExtension("Part::AttachExtensionPython")
        if self.attachment_support:
            obj.AttachmentSupport = [fc.link(r) for r in self.attachment_support]
        off = self.attachment_offset
        if off is not None:
            pos, ypr = (off, (0.0, 0.0, 0.0)) if len(off) == 3 and all(isinstance(c, (int, float)) for c in off) \
                else off
            obj.AttachmentOffset = App.Placement(App.Vector(*pos), App.Rotation(*ypr))
        obj.MapReversed = self.map_reversed
        obj.MapPathParameter = self.map_path_parameter
        obj.MapMode = self.map_mode

    def fc_setup(self, obj, fc):
        """A FeaturePython's Proxy, before its properties are set (Tube, BooleanFragments, ...)."""


class Placed(PartObject):
    """A primitive: its shape made at the origin and moved by its Placement (Part::Primitive, AttachExtension with
    MapMode Deactivated, as the commands leave it). placement is ((x, y, z), (yaw, pitch, roll)), mm and degrees."""
    def local(self, params):
        raise NotImplementedError

    def shape(self, ctx, params):
        return placed(self.local(params), self.placement)

    def built_shape(self, ctx, params):
        """The shape before its Placement: the primitive's own, at the origin."""
        return self.local(params)


def placement_trsf(placement):
    pos, ypr = placement or ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    r = F._ypr(*ypr)
    t = gp_Trsf()
    t.SetValues(r[0][0], r[0][1], r[0][2], pos[0], r[1][0], r[1][1], r[1][2], pos[1], r[2][0], r[2][1], r[2][2], pos[2])
    return t


def placed(shape, placement):
    """The shape with the Placement as its location, as Part::Feature's Shape carries it (TopoShape::setTransform)."""
    if placement is None or shape is None:
        return shape
    return shape.Moved(TopLoc_Location(placement_trsf(placement)))


# ── the document ─────────────────────────────────────────────────────────────────────────────────────────────────

class Context:
    """The document as an object sees it while it builds: the shapes made so far, by name, and the Placement each
    object sits at (its attachment's, or its placement=)."""

    def __init__(self, objects, params, features=None, base=None, tip=None, body=None):
        from . import attacher as A
        self.params = dict(params or {})
        self.objects = {}
        self.shapes: dict = {}
        self.placements: dict = {}
        self.modes: dict = {}            # {name: the MapMode its attachment used}
        self.errors: dict = {}
        self.body = None
        self.attach_ctx = None
        self.features = features
        if features is not None or body is not None:
            self.body = body if body is not None else F.evaluate(features, self.params, base, tip)
            self.attach_ctx = self.body.get("_attach")
            sk = self.body.get("_sketches", {})
            for n, s in sk.items():
                self.shapes[n] = sketch_shape(s)
            for f in features or ():
                n = getattr(f, "name", None)
                if n in self.body and n not in self.shapes:
                    self.shapes[n] = self.body[n]
            self.shapes[BODY] = self.body.get("Tip")
            self.placements[BODY] = A.Placement()
        for o in objects:
            self.objects[o.name] = o

    def obj(self, name):
        return self.objects.get(name)

    def sketch_placement(self, o):
        """A document sketch's Placement: where its support plane and offset put it (Sketch.placement)."""
        from . import attacher as A
        try:
            pos, m = o.placement()
        except F.FeatureError as e:
            raise F.FeatureError(str(e)) from None
        return A.Placement(pos, A.Rotation.from_matrix(m))

    def resolve(self, name, sub, where):
        """(shape, placement, whole, plane) of a reference, as AttachExtension's readLinks reads it: an object of this
        document or one of the Body's (a feature, a sketch, a datum, an origin feature; the Body itself is its Tip).
        Only what is before the attached object can be referenced, as every link in a part file."""
        from . import attacher as A
        if name == BODY:
            if self.body is None or self.shapes.get(BODY) is None:
                raise F.FeatureError(f"{where}: no {BODY!r} in this document")
            shape, pl, whole, plane = self.shapes[BODY], A.Placement(), not sub, False
        elif name in self.objects:
            if name in self.errors:
                raise F.FeatureError(f"{where}: {name} failed: {self.errors[name]}")
            if name not in self.shapes:
                raise F.FeatureError(f"{where}: no object {name!r} before it")
            shape, pl, whole, plane = self.shapes[name], self.placements.get(name, A.Placement()), not sub, False
        elif self.attach_ctx is not None:
            return self.attach_ctx.resolve(name, sub, where)
        else:
            raise F.FeatureError(f"{where}: no object {name!r} before it")
        if shape is None or shape.IsNull():
            raise F.FeatureError(f"{where}: {name} has no shape")
        return (sub_shape(shape, sub, where) if sub else shape), pl, whole, plane

    def ref(self, obj, sub, where):
        from . import attacher as A
        shape, pl, whole, plane = self.resolve(obj, sub, where)
        return A.Ref(shape, pl, whole=whole, plane=plane)

    def attach(self, f, where=None, orig=None):
        """f's Placement by its attachment, or None when it is not attached (Deactivated, or no support): the
        Attachment editor's AttachExtension::positionBySupport."""
        from . import attacher as A
        from .feature_attach import placement_of
        where = where or f.name
        refs = [self.ref(o, s, where) for o, s in f.attachment_support]
        mode = f.map_mode
        if mode == "Deactivated" or not refs:
            return None
        self.modes[f.name] = mode
        try:
            return A.attach(f.engine, mode, refs, offset=placement_of(where, f.attachment_offset, "attachment_offset"),
                            reversed=f.map_reversed, parameter=f.map_path_parameter, orig=orig)
        except A.AttachError as e:
            raise F.FeatureError(f"{where}: {e}") from None

    def add(self, o, params):
        """Build one object as a recompute does: its shape before its Placement (a primitive's own, else one built
        from its links) and the Placement its attachment gives it (else its placement=)."""
        from . import attacher as A
        if isinstance(o, F.Sketch):
            sk = _place_sketch(o, params)
            self.shapes[o.name] = sketch_shape(sk)
            self.placements[o.name] = self.sketch_placement(o)
            return self.shapes[o.name]
        local = o.built_shape(self, params)
        orig = o.base_placement(self, params)
        pl = self.attach(o, f"{o.name}: attachment", orig=orig)
        if pl is None:
            pl = orig
        self.placements[o.name] = pl
        moved = pl.pos != (0.0, 0.0, 0.0) or pl.rot.q != (0.0, 0.0, 0.0, 1.0)
        self.shapes[o.name] = local.Moved(TopLoc_Location(pl.trsf())) \
            if local is not None and not local.IsNull() and moved else local
        return self.shapes[o.name]

    def label(self, link):
        """The Label of a linked object, as FreeCAD's messages name it."""
        name = link if isinstance(link, str) else link[0]
        o = self.objects.get(name)
        return (getattr(o, "label", None) or name) if o is not None else name

    def shape(self, link, where="link"):
        """The shape a link names: an object's, the Body's, a Body feature's, or one of its sub-elements."""
        if link is None:
            return None
        name, sub = (link, "") if isinstance(link, str) else link
        if isinstance(sub, (list, tuple)):
            subs = [s for s in sub if s]
            if len(subs) > 1:
                return compound([self.shape((name, s), where) for s in subs])
            sub = subs[0] if subs else ""
        if name in self.errors:
            raise F.FeatureError(f"{where}: {name} failed: {self.errors[name]}")
        if name not in self.shapes:
            raise F.FeatureError(f"{where}: no object {name!r} before it")
        sh = self.shapes[name]
        if sh is None or sh.IsNull():
            raise F.FeatureError(f"{where}: {name} has no shape")
        return sub_shape(sh, sub, where) if sub else sh


def sub_shape(shape, sub, where="link"):
    """TopoShape::getSubShape: "Face3" is the third face of TopExp::MapShapes's order."""
    from OCP import TopAbs
    for prefix, kind in SUBS.items():
        if sub.startswith(prefix) and sub[len(prefix):].isdigit():
            subs = F._subs(shape, getattr(TopAbs, kind))
            i = int(sub[len(prefix):])
            if not 1 <= i <= len(subs):
                raise F.FeatureError(f"{where}: {sub} is not in the shape ({len(subs)} {prefix.lower()}s)")
            return subs[i - 1]
    raise F.FeatureError(f"{where}: {sub!r} is not a sub-element name (Face3, Edge1, Vertex2)")


def compound(shapes):
    b = BRep_Builder()
    c = TopoDS_Compound()
    b.MakeCompound(c)
    for s in shapes:
        if s is not None and not s.IsNull():
            b.Add(c, s)
    return c


def sketch_shape(sk):
    """SketchObject::buildShape: the non-construction edges joined to wires (makeElementWires), the points as
    vertices, placed by the sketch's Placement; one wire alone is the shape, more make a compound."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Pnt
    loc = TopLoc_Location(F._trsf(sk))
    edges = [TopoDS.Edge(F._edge(g).Moved(loc)) for g in sk.geometry
             if not g.construction and not isinstance(g, F.Point)]
    verts = [BRepBuilderAPI_MakeVertex(gp_Pnt(*g.point, 0)).Vertex().Moved(loc) for g in sk.geometry
             if not g.construction and isinstance(g, F.Point)]
    wires = F._wires(edges) if edges else []
    if not verts and len(wires) == 1:
        return wires[0]
    if not wires and not verts:
        return None
    return compound(wires + verts)


def _place_sketch(f, params):
    """A document-level sketch: placed on its origin plane (support "XY", "XZ", "YZ") with its offset, solved."""
    if f.support is None or f.external_geometry:
        raise F.FeatureError(f"Sketch {f.name}: a sketch outside a Body is placed on the XY, XZ or YZ plane here")
    return f.solved(params)


def evaluate(objects, params=None, features=None, base=None, tip=None, upto=None, keep_going=False,
             body=None) -> dict:
    """{name: TopoDS_Shape} of every object in order (up to and including upto), with "Body" and the Body's features
    when there are FEATURES (or body, an already evaluated feature.evaluate dict: what feature_attach's queries pass
    when the Body stops at an error), "_errors" {name: FreeCAD's message} when keep_going (a failed object has no shape,
    and the objects that link it fail too, as a recompute leaves them), else the first error raised."""
    params = dict(params or {})
    objects = list(objects or [])
    ctx = Context(objects, params, features, base, tip, body)
    names = set(ctx.shapes) | ({BODY} if features is not None or body is not None else set())
    for o in objects:
        n = getattr(o, "name", None)
        if not isinstance(o, (PartObject, F.Sketch)):
            raise F.FeatureError(f"OBJECTS holds {o!r}, not a Part object or a Sketch")
        if n in names:
            raise F.FeatureError(f"two objects are named {n!r}")
        names.add(n)
        try:
            ctx.add(o, params)
        except F.FeatureError as e:
            msg = str(e) if str(e).startswith(f"{n}:") else f"{n}: {e}"
            if not keep_going:
                raise F.FeatureError(msg) from None
            ctx.errors[n] = msg
        except Exception as e:  # noqa: BLE001 - OCCT's Standard_Failure, as FreeCAD reports it
            msg = getattr(e, "GetMessageString", lambda: str(e) or type(e).__name__)()
            if not keep_going:
                raise F.FeatureError(f"{n}: {msg}") from None
            ctx.errors[n] = msg
        if n == upto:
            break
    out = dict(ctx.shapes)
    out["_errors"] = ctx.errors
    out["_ctx"] = ctx
    return out


def hidden_by(objects) -> set:
    """The names the objects' commands hide: what each object that links them hides (HIDES)."""
    out = set()
    for o in objects:
        if isinstance(o, PartObject):
            out |= set(o.hidden_inputs())
    return out


def visible(objects, features=None) -> list[str]:
    """What FreeCAD shows, in order: "Body" first when the part has one, then every object, each unless its
    visibility says False or (left out) an object that links it hides it. Sketches are drawn, not built."""
    hid = hidden_by(objects)
    by = {o.name: o for o in objects}
    out = [BODY] if features is not None and BODY not in hid else []
    for o in objects:
        if isinstance(o, F.Sketch):
            continue
        v = getattr(o, "visibility", None)
        if v is True or (v is None and o.name not in hid):
            out.append(o.name)
    return [n for n in out if n == BODY or n in by]


def roots(objects, features=None) -> list[str]:
    """The objects no other object links (the tree's top level), and "Body" first when nothing links it. What an
    object is attached to is not a link: AttachExtension's support shows in the dependency graph, not the tree."""
    used = set()
    for o in objects:
        if isinstance(o, PartObject):
            used |= set(o.inputs())
    out = [BODY] if features is not None and BODY not in used and not (used & {getattr(f, "name", None)
                                                                         for f in features}) else []
    return out + [o.name for o in objects if o.name not in used]


def Document(objects, params=None, features=None, base=None, tip=None):
    """The part's shape: every object nothing links (and the Body when nothing links it), one compound of them, as a
    build123d Part. features, base and tip are the Body's, as feature.Body takes them."""
    from build123d import Compound, Part
    shapes = evaluate(objects, params, features, base, tip)
    shown = []
    for n in visible(objects, features):
        s = shapes.get(n)
        if s is not None and not s.IsNull():
            shown.append(s)
    if not shown:
        raise F.FeatureError("the document has no shape: OBJECTS is empty" if not objects else
                             "the document shows no shape")
    one = shown[0] if len(shown) == 1 and shown[0].ShapeType() == TopAbs_COMPOUND else compound(shown)
    return Part(Compound(one).wrapped)          # a compound always, as feature.Body returns its solids


# ── the same lines, fed to FreeCAD ───────────────────────────────────────────────────────────────────────────────

def to_freecad(objects, params=None, doc=None, features=None, base=None, name="Document"):
    """Build OBJECTS (and the Body of FEATURES) in a FreeCAD document (run inside freecadcmd). Values given as PARAMS
    names or expressions are bound to a spreadsheet, Params, by expressions, as feature.to_freecad binds them.
    Returns {name: the FreeCAD object}; recompute the document to build them."""
    import types

    import FreeCAD as App
    doc = doc or App.newDocument(name)
    params = dict(params or {})
    made = {}
    if features is not None:
        body = F.to_freecad(features, params, doc=doc, base=base)
        made[BODY] = body
        for o in body.Group:
            made[o.Name] = o
        for o in body.Origin.OriginFeatures:   # AttachExtension's references to "XY_Plane", "X_Axis", ...
            made[o.Role] = o
    elif params:
        sheet = doc.addObject("Spreadsheet::Sheet", "Params")
        for i, (k, val) in enumerate(params.items()):
            cell = f"A{i + 1}"
            sheet.set(cell, repr(float(val)) if isinstance(val, (int, float)) and not isinstance(val, bool) else str(val))
            sheet.setAlias(cell, k)
        doc.recompute()

    def expr(v):
        tree = ast.parse(v, mode="eval")

        class _R(ast.NodeTransformer):
            def visit_Name(self, n):
                return ast.copy_location(ast.Name(id=f"Params.{n.id}", ctx=n.ctx), n)
        return ast.unparse(_R().visit(tree))

    def setv(obj, prop, v):
        if isinstance(v, str) and prop not in ENUM_PROPS.get(obj.TypeId, ()) and _is_expr(v, params):
            x = F.value(v, params, prop)
            setattr(obj, prop, int(round(x)) if isinstance(getattr(obj, prop), int) else x)
            obj.setExpression(prop, expr(v))
        elif isinstance(v, (list, tuple)) and v and isinstance(v[0], (list, tuple)):
            setattr(obj, prop, [App.Vector(*p) for p in v])
        elif isinstance(v, (list, tuple)) and len(v) == 3 and all(isinstance(c, (int, float)) for c in v):
            setattr(obj, prop, App.Vector(*v))
        else:
            setattr(obj, prop, v)

    def link(r):
        if isinstance(r, str):
            return made[r]
        o, sub = r
        return (made[o], list(sub) if isinstance(sub, (list, tuple)) else [sub])

    fc = types.SimpleNamespace(App=App, doc=doc, made=made, params=params, setv=setv, link=link, expr=expr)
    for o in objects:
        if isinstance(o, F.Sketch):
            made[o.name] = _sketch_to_freecad(o, params, doc, fc)
        else:
            made[o.name] = o.to_freecad(fc)
    return made


ENUM_PROPS: dict = {}           # {TypeId: the enumeration properties}, which take strings that are not expressions


def _is_expr(v, params):
    try:
        F.value(v, params, "x")
        return True
    except F.FeatureError:
        return False


def _sketch_to_freecad(f, params, doc, fc):
    """A sketch at the document's root (Sketcher_NewSketch with no Body): feature.to_freecad's sketch lines, in a
    throwaway Body's stead the document itself."""
    import Part as FCPart
    import Sketcher
    App = fc.App
    V = App.Vector
    sk = doc.addObject("Sketcher::SketchObject", f.name)
    pos, rot = f.placement()
    from . import attacher as A
    q = A.Rotation.from_matrix(rot).q
    sk.Placement = App.Placement(V(*pos), App.Rotation(*q))
    for g in f.geometry:
        if isinstance(g, F.LineSegment):
            pg = FCPart.LineSegment(V(*g.start, 0), V(*g.end, 0))
        elif isinstance(g, F.Circle):
            pg = FCPart.Circle(V(*g.center, 0), V(0, 0, 1), g.radius)
        elif isinstance(g, F.ArcOfCircle):
            pg = FCPart.ArcOfCircle(FCPart.Circle(V(*g.center, 0), V(0, 0, 1), g.radius), g.start_angle, g.end_angle)
        elif isinstance(g, F._curves.CURVES):
            pg = F._curves.part_geometry(g, FCPart, V)
        else:
            pg = FCPart.Point(V(*g.point, 0))
        sk.addGeometry(pg, g.construction)
    for i, c in enumerate(f.constraints):
        args = list(c.args) + ([c.resolved(params)] if c.dimensional else [])
        sk.addConstraint(Sketcher.Constraint(c.type, *args))
        if c.dimensional and isinstance(c.value, str):
            sk.setExpression(f"Constraints[{i}]", fc.expr(c.value) + (" * 1 deg" if c.type == "Angle" else ""))
    return sk


# ── the objects, in modules of their own ─────────────────────────────────────────────────────────────────────────
from . import feature_part_prim  # noqa: E402,F401  Box ... Vertex, Polygon, Tube
from . import feature_part_bool  # noqa: E402,F401  Cut, Fuse, Common, Section, BooleanFragments, Slice, XOR, joins
from . import feature_part_ops  # noqa: E402,F401  Extrusion, Revolution, Mirroring, Fillet, ..., Compound, Refine
from . import feature_part_split  # noqa: E402,F401  BooleanFragments, Slice, XOR, Connect, Embed, Cutout, CompoundFilter
from . import feature_part_sweep  # noqa: E402,F401  Loft, Sweep, Offset, Offset2D, Thickness, ProjectOnSurface
from . import feature_part_misc  # noqa: E402,F401  Reverse, Scale, Face, RuledSurface
from . import feature_part_static  # noqa: E402,F401  Feature (copies), MakeSolid, CrossSections, ShapeBuilder, ToleranceSet

# What each command hides, where it is not what the tree shows under the object (Gui/Command.cpp, TaskLoft.cpp,
# TaskSweep.cpp, TaskOffset.cpp, DlgProjectionOnSurface.cpp, Mirroring.cpp: they leave their inputs shown).
for _kind in ("Part.Loft", "Part.Sweep", "Part.Offset", "Part.Offset2D", "Part.ProjectOnSurface", "Part.Mirroring"):
    if _kind in OBJECTS:
        OBJECTS[_kind].HIDES = ()

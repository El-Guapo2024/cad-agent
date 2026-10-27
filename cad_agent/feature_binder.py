# SPDX-License-Identifier: LGPL-2.1-or-later
# A port of FreeCAD's PartDesign ShapeBinder (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), the file
# LGPL-2.1-or-later as it states:
#   src/Mod/PartDesign/App/ShapeBinder.cpp: Copyright (c) 2015 Stefan Tröger
"""PartDesign::ShapeBinder in a FEATURES list: a reference in the Body to geometry another object has.

    ShapeBinder("Binder", support=[("Pad", "Face6")])
    ShapeBinder("Binder001", support=[("Pad", "")])                  # the whole Pad
    ShapeBinder("Binder002", support=[("Pad", "Face1"), ("Pad", "Edge1")])   # a compound of both
    ShapeBinder("Binder003", support=[("XY_Plane", "")], trace_support=True)

support is FreeCAD's Support, a PropertyLinkSubList: (object, element) pairs, the element "" for the object's whole
shape (as a sketch's attachment_support is written). ShapeBinder copies the geometry of the first Part::Feature it
names (a Pad, a Pocket, a sketch, another binder), its whole shape when that object's first entry has no element,
else a compound of the elements; with no Part::Feature it copies the first App::Plane, App::Line or App::Point it
names (an Origin feature, a Part datum: an infinite face, an infinite line along its Placement's Z, a vertex).
TraceSupport is kept for FreeCAD: it moves the copied shape from one container to another,
and a Body is one container, so here it changes nothing. The binder's Placement is its shape's, as
ShapeBinder::execute sets it; it is not a property of the part file, and the binder is never the Body's Tip.

A binder is not a solid feature: feature.evaluate() adds it to the Body's attachment Context (kind "binder") and
the Body's solid is unchanged. A later sketch can attach to its face, a Pad's UpToFace can name it (the copied face
is in the Body's coordinates), and another binder can copy it.
"""
from __future__ import annotations

from . import feature as F
from . import feature_attach as FA
from .feature_kw import KwFeature

BINDER_KINDS = ("ShapeBinder", "SubShapeBinder")    # a feature of the Body that is not its solid (feature_edit's Tip)


def _support(where: str, v) -> tuple:
    """Support normalised to ((object, element), ...): a name alone is the whole object, "Pad.Face6" an element,
    and (object, [e1, e2]) is one reference per element, as a sketch's attachment_support is written."""
    try:
        return tuple(FA.support_list(where, v, most=None))
    except F.FeatureError as e:
        raise F.FeatureError(f"{where}: {e}") from None


class ShapeBinder(KwFeature):
    kind = "ShapeBinder"
    TYPE_ID = "PartDesign::ShapeBinder"
    TRANSACTION = "Create Shape Binder"          # Gui/Command.cpp: openCommand("Create Shape Binder")
    POS: tuple = ()
    DEFAULTS = {"support": (), "trace_support": False}
    REFS = ("support",)                          # PropertyLinkSubList: a list of references, not one
    is_binder = True

    def normalize(self, key, v):
        if key == "support":
            return _support(f"{self.name}.support", v)
        return super().normalize(key, v)

    def support_groups(self) -> list:
        """Support as to_freecad writes it, as FreeCAD's PropertyLinkSubList reads back: [(object, [elements])], one
        entry per object in the order first named, an Origin feature's elements [""]."""
        groups: dict = {}
        for o, s in self.support:
            groups.setdefault(o, []).append(s)
        return [(o, [""] if o in FA.ORIGIN else subs) for o, subs in groups.items()]

    def to_freecad(self, ctx):
        """PartDesign::ShapeBinder with Support (one entry per object, all its elements) and TraceSupport; its shape
        and Placement follow on the recompute, at execute()."""
        obj = ctx.body.newObject(self.TYPE_ID, self.name)
        sup = [(ctx.origin[o], subs) if o in ctx.origin else ctx.ref((o, subs)) for o, subs in self.support_groups()]
        if sup:
            obj.Support = sup
        if self.trace_support and sup:
            # ShapeBinder::execute reads its support's globalPlacement when tracing; recompute the support first,
            # as a Body built in the GUI already is (with TraceSupport on an object never computed FreeCAD's
            # recompute leaves the whole Body null)
            ctx.doc.recompute()
        obj.TraceSupport = bool(self.trace_support)
        return obj


def _part_feature(ctx, support) -> str | None:
    """getFilteredReferences: the first object in Support that is a Part::Feature (a Body feature, another binder,
    a sketch, and PartDesign's Plane, Line, Point and CoordinateSystem, which are Part::Datum and so Part::Feature;
    not an Origin feature or a Part::DatumPlane), else None."""
    for o, _ in support:
        kind = ctx.kinds.get(o)
        if kind in ("solid", "sketch", "binder"):
            return o
        if kind == "datum" and getattr(ctx.datums.get(o), "TYPE_ID", "").startswith("PartDesign::"):
            return o
    return None


# Part's datums are App::Plane, App::Line and App::Point (Part/App/Datums.h), as the Body's Origin features are
_APP_KINDS = {"Part::DatumPlane": "App::Plane", "Part::DatumLine": "App::Line", "Part::DatumPoint": "App::Point"}


def _app_kind(ctx, o) -> str | None:
    """App::Plane, App::Line or App::Point when the object is one (an Origin feature, a Part datum), else None."""
    if o in FA.ORIGIN:
        return FA.ORIGIN[o][0]
    if ctx.kinds.get(o) == "datum":
        return _APP_KINDS.get(getattr(ctx.datums.get(o), "TYPE_ID", ""))
    return None


def filtered_support(ctx, support) -> tuple[str | None, list[str]]:
    """ShapeBinder::getFilteredReferences: (object, elements) of a binder's Support. The whole shape when that
    object's own entry has no element, else every element Support gives for it; with no Part::Feature, the first
    App::Line, App::Plane or App::Point (an Origin feature, a Part datum) and no elements."""
    if not support:
        return None, []
    obj = _part_feature(ctx, support)
    if obj is not None:
        if not next(s for o, s in support if o == obj):
            return obj, []
        return obj, [s for o, s in support if o == obj and s]
    for o, _ in support:
        if _app_kind(ctx, o) is not None:
            return o, []
    return None, []


def _app_shape(kind):
    """buildShapeFromReferences of an App::Line, App::Plane or App::Point, before its Placement: an edge on gp_Lin()
    (the Z axis, whatever direction the Origin's own line has), a face on gp_Pln() (XY), a vertex at gp_Pnt()."""
    if kind == "App::Line":
        return FA._infinite(FA._line_edge((0, 0, 1)))
    if kind == "App::Plane":
        return FA._infinite(FA._plane_face())
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.gp import gp_Pnt
    return BRepBuilderAPI_MakeVertex(gp_Pnt(0, 0, 0)).Shape()


def _located(shape, pl):
    """A global shape as a Part::Feature's Shape holds it, located at the object's Placement (getTransform() is then
    that Placement) with every element where it was: a Pad's TopoShape is built from its sketch moved by the inverse
    Placement and then placed, so an element's location is the Placement times its own within the shape. Here the
    shape is rebuilt one level down, each child moved by the inverse, and the copy located at the Placement; the two
    cancel (one TopLoc datum), so its elements keep their exact global locations."""
    if shape is None or shape.IsNull() or \
            (tuple(pl.pos) == (0.0, 0.0, 0.0) and tuple(pl.rot.q) == (0.0, 0.0, 0.0, 1.0)):
        return shape
    from OCP.BRep import BRep_Builder
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS_Iterator
    loc = TopLoc_Location(pl.trsf())
    inv, own = loc.Inverted(), shape.Location()
    out = shape.EmptyCopied()
    out.Location(TopLoc_Location())
    b = BRep_Builder()
    it = TopoDS_Iterator(shape, False, False)
    while it.More():
        b.Add(out, it.Value().Moved(own).Moved(inv))
        it.Next()
    out.Location(loc)
    return out


def binder_shape(f, ctx):
    """ShapeBinder::buildShapeFromReferences, in the Body's coordinates: the object's whole shape, one element, or
    a compound of the elements; None for a binder with nothing usable in its Support. Its location is what
    FreeCAD's TopoShape carries, which ShapeBinder::execute makes the binder's Placement: a whole object's own
    Placement (Part::Feature's Shape carries it), one element's own location within it, the identity for a
    compound of several, and an App::Line/Plane/Point's Placement."""
    obj, subs = filtered_support(ctx, f.support)
    if obj is None:
        return None
    where = f"{f.name}: support"
    kind = _app_kind(ctx, obj)
    if kind is not None:
        return FA._moved(_app_shape(kind), ctx.placements[obj])
    if not subs:
        if ctx.kinds.get(obj) == "sketch":
            # SketchObject::buildShape: the whole sketch is its wires (a Wire, not a compound of loose edges)
            from .feature_part import sketch_shape
            return _located(sketch_shape(ctx.sketches[obj]), ctx.placements[obj])
        shape = ctx.element(obj, "", where)
        if ctx.kinds.get(obj) == "solid":           # held global here, at the identity
            return _located(shape, ctx.placements[obj])
        return shape                                 # a binder's, a datum's: already at its Placement
    shapes = [ctx.element(obj, s, where) for s in subs]
    if any(s is None or s.IsNull() for s in shapes):
        return None
    if len(shapes) == 1:
        return shapes[0]
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound
    comp, b = TopoDS_Compound(), BRep_Builder()
    b.MakeCompound(comp)
    for s in shapes:
        b.Add(comp, s)
    return comp

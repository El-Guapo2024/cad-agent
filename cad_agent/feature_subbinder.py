# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It ports FreeCAD's PartDesign::SubShapeBinder and keeps FreeCAD's licence, the GNU Lesser General
# Public License, version 2.1 or (at your option) any later version; the text is in ../ui/LICENSE.
#
#   Derived from FreeCAD (https://github.com/FreeCAD/FreeCAD), commit 3160daf1e2b62b0472854da4848255c6b3ad554c:
#     src/Mod/PartDesign/App/ShapeBinder.cpp: Copyright (c) 2015 Stefan Tröger (SubShapeBinder's properties, their
#         defaults, update())
#     src/Mod/Part/App/FaceMakerBuildFace.cpp: Copyright (c) 2026 the FreeCAD project (the face maker update() uses)
#
#   This library is free software; you can redistribute it and/or modify it under the terms of the GNU Library
#   General Public License as published by the Free Software Foundation; either version 2 of the License, or
#   (at your option) any later version.
#
#   This library is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the
#   implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Library General Public
#   License for more details.
#
# See ../NOTICE.
"""PartDesign::SubShapeBinder in a FEATURES list: a copy of other objects' geometry, whole or by sub-elements, which
it can fuse, make faces of and offset:

    SubShapeBinder("Binder", support=[("Pad", ["Face6"])])
    SubShapeBinder("Binder001", support=["Pad"])                          # the whole Pad: a compound holding its solid
    SubShapeBinder("Binder002", support=["Sketch"], offset=2.0)            # the sketch's wires made a face, offset
    SubShapeBinder("Binder003", support=[("Pad", ["Edge1", "Edge2"])], make_face=False)

Properties (SubShapeBinder::SubShapeBinder): support (Support, a PropertyXLinkSubList: (object, [elements]), an object
alone for its whole shape), fuse (Fuse, False), make_face (MakeFace, True), offset (Offset, 0.0), offset_join_type
(OffsetJoinType "Arcs" | "Tangent" | "Intersection"), offset_fill, offset_open_result, offset_intersection (False),
claim_children (ClaimChildren, False: the tree shows the bound objects under it), relative (Relative, True), bind_mode
(BindMode, "Synchronized"), partial_load (PartialLoad, False), bind_copy_on_change (BindCopyOnChange, "Disabled"),
refine (Refine, True) and placement (Placement, the identity: an offset the binder's shape is set at).

update() as FreeCAD runs it for a binder in a Body of the document: each Support entry's elements, each once and in
the order a std::set keeps them (Edge10 before Edge2), each the element's shape in the document's frame (an object
alone, its whole shape); an element that has edges but no face copied; all of them one compound; with Fuse, its solids
fused; else with MakeFace (or an Offset), wires made of the edges of a shape with no face and a face of them by
FaceMakerBuildFace (a face maker that cannot make one leaves the wires); an Offset by makeElementOffset2D; the refine;
and the binder's Placement as the result's. Like a ShapeBinder it is a Part::Feature but not a solid feature: the Body's
solid and Tip are unchanged, and a later sketch, UpToFace or binder may use its shape.

Not here: BindMode Frozen and Detached keep a shape that no longer follows its support (Frozen until synchronised by
hand, Detached for ever), and BindCopyOnChange copies its support into a hidden document; a part file is rebuilt from
its source, so it holds neither (only "Synchronized" and "Disabled" are taken). PartialLoad and Context concern bound
objects of other documents, which a part file does not have.
"""
from __future__ import annotations

from . import feature as F
from .feature_binder import _support
from .feature_kw import KwFeature

JOIN_TYPES = ("Arcs", "Tangent", "Intersection")
BIND_MODES = ("Synchronized", "Frozen", "Detached")
COPY_ON_CHANGE = ("Disabled", "Enabled", "Mutated")


class SubShapeBinder(KwFeature):
    kind = "SubShapeBinder"
    TYPE_ID = "PartDesign::SubShapeBinder"
    TRANSACTION = "Create Sub-Shape Binder"      # CmdPartDesignSubShapeBinder: openCommand("Create Sub-Shape Binder")
    POS: tuple = ()
    DEFAULTS = {"support": (), "fuse": False, "make_face": True, "offset": 0.0, "offset_join_type": "Arcs",
                "offset_fill": False, "offset_open_result": False, "offset_intersection": False, "claim_children": False,
                "relative": True, "bind_mode": "Synchronized", "partial_load": False, "bind_copy_on_change": "Disabled",
                "refine": True, "placement": None}
    REFS = ("support",)
    is_binder = True

    def normalize(self, key, v):
        if key == "support":
            return _support(f"{self.name}.support", v)
        if key == "placement":
            return v
        return super().normalize(key, v)

    def validate(self):
        for key, allowed in (("offset_join_type", JOIN_TYPES), ("bind_mode", BIND_MODES),
                             ("bind_copy_on_change", COPY_ON_CHANGE)):
            if getattr(self, key) not in allowed:
                raise F.FeatureError(f"{self.name}: {key} {getattr(self, key)!r} is not one of {', '.join(allowed)}")
        if self.bind_mode != "Synchronized":
            raise F.FeatureError(f"{self.name}: bind_mode {self.bind_mode!r} keeps a shape that no longer follows its "
                                 "support, which a part file rebuilt from its source cannot hold: only Synchronized")
        if self.bind_copy_on_change != "Disabled":
            raise F.FeatureError(f"{self.name}: bind_copy_on_change {self.bind_copy_on_change!r} copies the support "
                                 "into a hidden document, which a part file does not have: only Disabled")
        from .feature_attach import placement_of
        self._pl = placement_of(self.name, self.placement)

    def source_value(self, key, v=None):
        v = getattr(self, key) if v is None else v
        if key == "placement" and isinstance(v, (list, tuple)):
            return tuple(tuple(x) if isinstance(x, (list, tuple)) else x for x in v)
        return super().source_value(key, v)

    def support_groups(self) -> list:
        """Support as FreeCAD's PropertyXLinkSubList holds it: [(object, [elements])], one entry per object in the
        order first named, [] for an object named whole."""
        groups: dict = {}
        for o, s in self.support:
            groups.setdefault(o, [])
            if s:
                groups[o].append(s)
        return list(groups.items())

    # ── the shape ──
    def bound_shape(self, ctx):
        """SubShapeBinder::update, for a binder whose support is in its own Body (the Body at the document's root, so
        every relative transformation is the identity): the shape, located at the binder's Placement, or None."""
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
        from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SOLID, TopAbs_WIRE
        from OCP.TopLoc import TopLoc_Location
        from .feature_part import compound
        shapes = []
        for obj, subs in self.support_groups():
            for sub in (sorted(set(subs)) if subs else [""]):
                shape = _shape_of(ctx, obj, sub, f"{self.name}: support")
                if shape is None or shape.IsNull():
                    continue
                if sub:
                    # each element is got on its own (getTopoShape per sub-element), so two faces of one solid share
                    # no edge in the compound
                    shape = BRepBuilderAPI_Copy(shape).Shape()
                elif not F._count(shape, TopAbs_FACE) and F._count(shape, TopAbs_EDGE):
                    shape = BRepBuilderAPI_Copy(shape).Shape()        # makeElementCopy
                shapes.append(shape)
        if not shapes:
            return None
        if len(shapes) == 1 and not self.relative:
            shapes[0] = shapes[0].Located(TopLoc_Location())          # setPlacement(Base::Placement())
        result = compound(shapes)
        fused = False
        if self.fuse:
            solids = F._subs(result, TopAbs_SOLID)
            if len(solids) > 1:
                result = _fuse(solids[0], solids[1:])
                fused = True
            elif solids:
                result = compound([solids[0]])
                fused = True
        offset = float(self.offset)
        if not fused and (self.make_face or offset != 0.0) and not F._count(result, TopAbs_FACE) \
                and F._count(result, TopAbs_EDGE):
            from .feature_part_sweep import make_wires
            result = make_wires(result)
            if self.make_face:
                try:
                    from .feature_part_face import make_face
                    face = make_face(result, "Part::FaceMakerBuildFace")
                    if face is not None and not face.IsNull():
                        result = face
                except Exception:  # noqa: BLE001 - FreeCAD's catch (...): the wires stay
                    pass
        if not fused and F._count(result, TopAbs_WIRE) and offset != 0.0:
            from .feature_part_sweep import make_offset2d
            try:
                result = make_offset2d(result, offset, JOIN_TYPES.index(self.offset_join_type), self.offset_fill,
                                       self.offset_open_result, self.offset_intersection)
            except Exception:  # noqa: BLE001 - FreeCAD reports "failed to make 2D offset" and goes on
                pass
        if self.refine:
            result = F._refine(result)
        pl = self._pl
        if pl.pos != (0.0, 0.0, 0.0) or pl.rot.q != (0.0, 0.0, 0.0, 1.0):
            result = result.Located(TopLoc_Location(pl.trsf()))      # result.setPlacement(Placement)
        return result

    def to_freecad(self, ctx):
        """CmdPartDesignSubShapeBinder: newObject in the Body, then setLinks (Support), and the properties."""
        obj = ctx.body.newObject(self.TYPE_ID, self.name)
        sup = []
        for o, subs in self.support_groups():
            target = ctx.origin[o] if o in ctx.origin else ctx.made[o]
            sup.append((target, list(subs)))
        if sup:
            obj.Support = sup
        for key, prop in (("fuse", "Fuse"), ("make_face", "MakeFace"), ("offset_join_type", "OffsetJoinType"),
                          ("offset_fill", "OffsetFill"), ("offset_open_result", "OffsetOpenResult"),
                          ("offset_intersection", "OffsetIntersection"), ("claim_children", "ClaimChildren"),
                          ("relative", "Relative"), ("partial_load", "PartialLoad"), ("refine", "Refine")):
            setattr(obj, prop, getattr(self, key))
        ctx.setv(obj, "Offset", self.offset)
        if self.placement is not None:
            p = self._pl
            obj.Placement = ctx.App.Placement(ctx.App.Vector(*p.pos), ctx.App.Rotation(*p.rot.q))
        return obj


def _fuse(first, rest):
    """TopoShape::fuse: BRepAlgoAPI_Fuse of the first solid with the others."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
    args, tools = F.TopTools_ListOfShape(), F.TopTools_ListOfShape()
    args.Append(first)
    for s in rest:
        tools.Append(s)
    mk = BRepAlgoAPI_Fuse()
    mk.SetArguments(args)
    mk.SetTools(tools)
    mk.SetRunParallel(True)
    mk.Build()
    if not mk.IsDone():
        raise F.FeatureError("Multi fusion failed")
    return mk.Shape()


def _shape_of(ctx, obj, sub, where):
    """Part::Feature::getTopoShape(obj, NeedSubElement | ResolveLink | Transform, sub), in the Body: an element of a
    feature's shape, or the whole shape (a sketch's wires, as SketchObject's Shape holds them)."""
    kind = ctx.kinds.get(obj)
    if kind is None:
        raise F.FeatureError(f"{where}: no {obj!r} before it")
    if kind == "sketch" and not sub:
        from .feature_part import sketch_shape
        return sketch_shape(ctx.sketches[obj])
    return ctx.element(obj, sub, where)        # an Origin feature's or a datum's: its infinite plane, line or point

# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It ports FreeCAD's PartDesign Boolean and Clone and keeps FreeCAD's licence, the GNU Lesser
# General Public License, version 2.1 or (at your option) any later version; the text is in ../ui/LICENSE.
#
#   Derived from FreeCAD (https://github.com/FreeCAD/FreeCAD), commit 3160daf1e2b62b0472854da4848255c6b3ad554c:
#     src/Mod/PartDesign/App/FeatureBoolean.cpp: Copyright (c) 2013 Jan Rheinländer (Boolean::execute, its Type)
#     src/Mod/PartDesign/App/FeatureBase.cpp: Copyright (c) 2017 Stefan Tröger (FeatureBase::execute)
#     src/Mod/PartDesign/Gui/Command.cpp: Copyright (c) 2008 Jürgen Riegel (CmdPartDesignClone, CmdPartDesignBoolean)
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
"""PartDesign's Boolean and Clone in a FEATURES list: features that take other Bodies.

A Body here is a part module (New Body writes parts/Body001.py, and the tree lists every part's Body as FreeCAD lists the
Bodies of a document), so a link to another Body is its part's name, and to a feature of it "Part.Feature":

    # parts/Body.py: the Body, with Body001 cut out of it
    FEATURES = [..., Boolean("Boolean", ["Body001"], type="Cut")]

    # parts/Body001.py, made by PartDesign_Clone on Body: a new Body whose base is Body's shape
    FEATURES = [Clone("Clone", "Body")]

Boolean (PartDesign::Boolean, FeatureBoolean.cpp): group (Group, the tool Bodies, by position), type ("Fuse", "Cut",
"Common"), refine (Refine, True). execute: the solid before it is the base (a Cut with none is "Cannot do boolean cut
without BaseFeature"; with none the last tool is the base); no tools leaves the base as it is; else
makeElementBoolean(Type, [base, tools...]) and the refine. A tool is the other Body's Shape (its Tip's solid) in this
Body's frame: both Bodies sit at the document's origin here, as two Bodies FreeCAD makes do until one is moved
(UseLegacyBodyPlacement False, getTopoShapeInLocalCoordinates).

Clone (PartDesign::FeatureBase, the object CmdPartDesignClone puts in a new Body): base_feature (BaseFeature, by
position): the other Body (its Shape) or one of its features (that feature's solid), copied as this Body's first solid;
its Placement is the source's (the identity for a Body). A Clone is the Body's Tip, as the command makes it.

The other part is built from its own source as its own build() would build it: its FEATURES with its PARAMS, BaseFeature
and TIP (a part without FEATURES is its build()'s shape, a Part::Feature as FreeCAD would take it). A Body that, through
these links, reaches itself is refused ("Link cycle"), as FreeCAD refuses a dependency loop.
"""
from __future__ import annotations

import contextvars
import sys
from pathlib import Path

from . import feature as F
from .feature_kw import KwFeature

TYPES = ("Fuse", "Cut", "Common")
MAKERS = {"Fuse": "fuse", "Cut": "cut", "Common": "common"}

# {Body name: a function giving its Shape (a TopoDS_Shape) and its features' shapes}, set by a caller that has the
# other Bodies at hand (tests/golden/pdlast, a check); a part file's are found next to it, in its parts/ folder
OTHERS: contextvars.ContextVar = contextvars.ContextVar("pd_other_bodies", default=None)
_BUILDING: contextvars.ContextVar = contextvars.ContextVar("pd_bodies_building", default=())


def _caller_file() -> str | None:
    """The part module whose FEATURES this feature is in: the first frame up the stack that runs a file in a parts/
    folder (state._load_module and feature_edit's _run set the module's __file__ to the part's path)."""
    f = sys._getframe(1)
    while f is not None:
        path = f.f_globals.get("__file__")
        if path and Path(path).parent.name == "parts":
            return path
        f = f.f_back
    return None


def _split(link: str) -> tuple[str, str | None]:
    body, _, feat = link.partition(".")
    return body, (feat or None)


def other_shapes(link: str, origin: str | None, where: str) -> tuple:
    """(the other Body's Shape, {feature: solid}) for a link to it, built from its part module."""
    body, _ = _split(link)
    if body in _BUILDING.get():
        raise F.FeatureError(f"{where}: Link cycle: {' -> '.join(_BUILDING.get() + (body,))}")
    others = OTHERS.get()
    token = _BUILDING.set(_BUILDING.get() + (body,))
    try:
        if others is not None and body in others:
            return others[body]()
        if origin is None:
            raise F.FeatureError(f"{where}: no Body {body!r}: a part file links another Body by its part's name")
        path = Path(origin).parent / f"{body}.py"
        if not path.exists():
            raise F.FeatureError(f"{where}: no Body {body!r} (parts/{body}.py)")
        return part_shapes(path)
    finally:
        _BUILDING.reset(token)


def part_shapes(path: Path) -> tuple:
    """A part module built as its build() builds it: (its Body's Shape, {feature: solid})."""
    from . import state
    mod = state._load_module(path)
    params = dict(getattr(mod, "PARAMS", {}) or {})
    feats = getattr(mod, "FEATURES", None)
    if feats is None or getattr(mod, "OBJECTS", None):
        shape = mod.build(**params)
        return getattr(shape, "wrapped", shape), {}
    base = mod.build_base(**params) if hasattr(mod, "build_base") else None
    shapes = F.evaluate(list(feats), params, base, getattr(mod, "TIP", None))
    solids = {k: v for k, v in shapes.items() if isinstance(k, str) and not k.startswith("_") and v is not None}
    return shapes["Tip"], solids


def _tool(link, origin, where):
    body, feat = _split(link)
    shape, solids = other_shapes(link, origin, where)
    if feat is not None:
        if feat not in solids:
            raise F.FeatureError(f"{where}: {body} has no feature {feat!r}")
        shape = solids[feat]
    if shape is None or shape.IsNull():
        raise F.FeatureError("Tool shape is null")
    return shape


def _link(v, where):
    if not isinstance(v, str) or not v or v.startswith(".") or v.count(".") > 1:
        raise F.FeatureError(f"{where}: {v!r} is not a Body (its part's name) or a feature of one (\"Body.Pad\")")
    return v


class _Linked(KwFeature):
    """A feature that links other Bodies: where its part file is, for finding them."""
    _origin = None

    def validate(self):
        self._origin = _caller_file()


class Boolean(_Linked):
    kind = "Boolean"
    TYPE_ID = "PartDesign::Boolean"
    TRANSACTION = "Create Boolean"         # CmdPartDesignBoolean: openCommand("Create Boolean")
    POS = ("group",)
    DEFAULTS = {"group": (), "type": "Fuse", "refine": True}
    DICT_KEYS = {"type": "type1"}          # read()'s "type" is the TypeId, as a Pad's Type is "type1"

    def normalize(self, key, v):
        if key == "group":
            if isinstance(v, str):
                v = [v]
            out = []
            for x in (v or ()):
                x = _link(x, f"{self.name}.group")
                if x not in out:                       # Boolean::addObjects: each tool once
                    out.append(x)
            return tuple(out)
        return super().normalize(key, v)

    def validate(self):
        super().validate()
        if self.type not in TYPES:
            raise F.FeatureError(f"{self.name}: type {self.type!r} is not one of {', '.join(TYPES)}")

    def references(self) -> list[str]:
        return []                                      # other Bodies, not features of this one

    def bodies(self) -> list[str]:
        return [_split(x)[0] for x in self.group]

    def execute(self, solid, shapes, params):
        """Boolean::execute."""
        where = self.name
        base = solid
        if base is None and self.type == "Cut":
            raise F.FeatureError("Cannot do boolean cut without BaseFeature")
        tools = list(self.group)
        if not tools:
            return base
        if base is None:
            base = _tool(tools.pop(), self._origin, where)
        if base is None or base.IsNull():
            raise F.FeatureError("Cannot do boolean operation with invalid base shape")
        shapes_ = [_tool(t, self._origin, where) for t in tools]
        result = base
        if shapes_:
            try:
                result = F._bool(MAKERS[self.type], base, shapes_, 0.0)    # FuzzyTolerance
            except F.FeatureError:
                raise
            except Exception:  # noqa: BLE001 - Standard_Failure
                raise F.FeatureError("Boolean operation failed") from None
        return F._refine(result) if self.refine else result

    def to_freecad(self, ctx):
        """newObject('PartDesign::Boolean'), addObjects(the tools), Type; the tool Bodies are already in the document,
        under their own names."""
        obj = ctx.body.newObject(self.TYPE_ID, self.name)
        tools = []
        for x in self.group:
            body, feat = _split(x)
            tools.append(ctx.doc.getObject(feat or body))
        if tools:
            obj.addObjects(tools)
        obj.Type = self.type
        obj.Refine = self.refine
        return obj


class Clone(_Linked):
    kind = "Clone"
    TYPE_ID = "PartDesign::FeatureBase"
    TRANSACTION = "Create Clone"           # CmdPartDesignClone: openCommand("Create Clone")
    POS = ("base_feature",)
    DEFAULTS = {"base_feature": None}

    def normalize(self, key, v):
        if key == "base_feature":
            return None if v is None else _link(v, f"{self.name}.base_feature")
        return super().normalize(key, v)

    def references(self) -> list[str]:
        return []

    def bodies(self) -> list[str]:
        return [_split(self.base_feature)[0]] if self.base_feature else []

    def execute(self, solid, shapes, params):
        """FeatureBase::execute: the BaseFeature's shape, its placement baked in (a Body's is the identity here)."""
        if not self.base_feature:
            raise F.FeatureError("BaseFeature link is not set")
        shape = _tool(self.base_feature, self._origin, self.name)
        if shape is None or shape.IsNull():
            raise F.FeatureError("BaseFeature has an empty shape")
        return shape

    def to_freecad(self, ctx):
        """CmdPartDesignClone: addObject('PartDesign::FeatureBase'), the Body's Group [clone] and Tip, BaseFeature the
        source and the source's Placement."""
        obj = ctx.doc.addObject(self.TYPE_ID, self.name)
        ctx.body.Group = ctx.body.Group + [obj]
        ctx.body.Tip = obj
        body, feat = _split(self.base_feature)
        src = ctx.doc.getObject(feat or body)
        obj.BaseFeature = src
        obj.Placement = src.Placement
        return obj


LINKED = {c.kind: c for c in (Boolean, Clone)}
LINK_CALLS = tuple(LINKED)        # buildcache: a part that calls these builds another part


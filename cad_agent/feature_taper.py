# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses FreeCAD's tapered extrusion (Part::ExtrusionHelper::makeElementDraft and
# what it calls) function by function and keeps FreeCAD's licence, the GNU Lesser General Public License, version
# 2.1 or (at your option) any later version; the text is in ../ui/LICENSE.
#
#   Derived from: src/Mod/Part/App/ExtrusionHelper.cpp (makeElementDraft, createTaperedPrismOffset;
#                 Copyright (c) 2022 Uwe Stöhr <uwestoehr@lyx.org>), src/Mod/Part/App/BRepOffsetAPI_MakeOffsetFix.cpp
#                 (Copyright (c) 2019 Werner Mayer <wmayer[at]users.sourceforge.net>) and
#                 src/Mod/Part/App/TopoShapeExpansion.cpp (TopoShape::splitWires; Copyright (c) 2022 Zheng, Lei)
#                 FreeCAD (https://github.com/FreeCAD/FreeCAD), commit 3160daf1e2b62b0472854da4848255c6b3ad554c
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
"""A Pad's or Pocket's TaperAngle: FeatureExtrude::generateSingleExtrusionSide's tapered branch.

    draft(profile, direction, length, taper_degrees) -> the tapered solid (or a compound of them)

Part::ExtrusionHelper::makeElementDraft with PartDesign's parameters (solid, InnerWireTaper::SameAsOuter, forward
only): each face's outer wire, made forward (splitWires with ReorientForward), is lofted by BRepOffsetAPI_ThruSections
(solid, ruled) to its copy moved by length along the direction and offset in its plane by tan(taper) * length
(createTaperedPrismOffset, with Part's BRepOffsetAPI_MakeOffsetFix and Intersection joins); each inner wire is
drafted the same way and cut from it.
"""
from __future__ import annotations

import math

from OCP.BRep import BRep_Builder
from OCP.BRepBuilderAPI import BRepBuilderAPI_DisconnectedWire, BRepBuilderAPI_MakeWire
from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffset, BRepOffsetAPI_ThruSections
from OCP.BRepTools import BRepTools
from OCP.GeomAbs import GeomAbs_Arc, GeomAbs_Intersection
from OCP.ShapeFix import ShapeFix_Wire
from OCP.TopAbs import TopAbs_COMPOUND, TopAbs_EDGE, TopAbs_FACE, TopAbs_FORWARD, TopAbs_VERTEX, TopAbs_WIRE
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Iterator
from OCP.gp import gp_Trsf, gp_Vec
try:
    from OCP.TopTools import TopTools_IndexedMapOfShape, TopTools_MapOfShape
except ImportError:                     # OCP 8 moved OCCT's collections
    from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedMapOfShape
    from OCP.collections import Map_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_MapOfShape

from .topo_boolean import element_boolean

CONFUSION = 1e-7                        # Precision::Confusion()
ANGULAR = 1e-12                         # Precision::Angular()
MAX_ANGLE = 90 - math.degrees(ANGULAR)  # FeatureExtrude::maxAngle, TaperAngle's constraint


class DraftError(ValueError):
    """What makeElementDraft throws (Standard_Failure), with its words."""


def _subs(shape, kind) -> list:
    m = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, kind, m)
    return [m.FindKey(i) for i in range(1, m.Extent() + 1)]


def clamp_angle(deg: float) -> float:
    """PropertyAngle's constraint {-maxAngle, maxAngle}: a value set from Python past it is the bound."""
    return max(-MAX_ANGLE, min(MAX_ANGLE, float(deg)))


# ── TopoShape::splitWires(&inner, ReorientForward) ──

def _reoriented(wire, orient=TopAbs_FORWARD):
    edges = _subs(wire, TopAbs_EDGE)
    if len(edges) == 1:
        # a single edge wire: BRepFill_OffsetWire offsets a circle by its edge's orientation, not the wire's
        edge = edges[0]
        if edge.Orientation() == orient:
            if wire.Orientation() == orient:
                return wire
        else:
            edge = edge.Oriented(orient)
        return BRepBuilderAPI_MakeWire(TopoDS.Edge(edge)).Shape()
    if wire.Orientation() != orient:
        return wire.Oriented(orient)
    return wire


def split_wires(face):
    """The face's outer wire (BRepTools::OuterWire) and its inner ones, every one forward."""
    outer = BRepTools.OuterWire_s(TopoDS.Face(face))
    if outer.IsNull():
        return None, []
    result, inner = None, []
    for w in _subs(face, TopAbs_WIRE):
        if w.IsSame(outer):
            result = _reoriented(w)
            continue
        inner.append(_reoriented(w))
    return result, inner


# ── Part::BRepOffsetAPI_MakeOffsetFix ──

class _MakeOffsetFix:
    """BRepOffsetAPI_MakeOffset with a one-edge wire's location taken off its edge and put back on the result."""

    def __init__(self):
        self.mk = BRepOffsetAPI_MakeOffset()
        self.locations: list = []           # [(edge without its location, the location)]

    def init(self, join, open_result=False):
        self.mk.Init(join, open_result)

    def add_wire(self, spine):
        wire = spine
        edges = []
        xp = TopExp_Explorer(wire, TopAbs_EDGE)
        while xp.More():
            edges.append(xp.Current())
            xp.Next()
        if len(edges) == 1:
            mk = BRepBuilderAPI_MakeWire()
            for e in edges:
                edge = TopoDS.Edge(e)
                loc = edge.Location()
                edge.Location(TopLoc_Location())
                mk.Add(edge)
                self.locations.append((edge, loc))
            wire = mk.Wire()
            wire.Orientation(spine.Orientation())   # the same orientation, or the offset shrinks the wire
        self.mk.AddWire(TopoDS.Wire(wire))

    def perform(self, offset, alt=0.0):
        self.mk.Perform(offset, alt)

    def is_done(self):
        return self.mk.IsDone()

    def _make_wire(self, wire):
        present = TopTools_MapOfShape()
        xp = TopExp_Explorer(wire, TopAbs_EDGE)
        while xp.More():
            present.Add(xp.Current())
            xp.Next()
        edges = []
        for edge, loc in self.locations:
            new = list(self.mk.Generated(edge))
            xv = TopExp_Explorer(edge, TopAbs_VERTEX)
            while xv.More():
                new += list(self.mk.Generated(xv.Current()))
                xv.Next()
            for s in new:
                if present.Contains(s):
                    s = s.Moved(loc)
                    edges.append(TopoDS.Edge(s))
        if not edges:
            return wire
        mk = BRepBuilderAPI_MakeWire()
        mk.Add(edges.pop(0))
        wire = mk.Wire()
        found = True
        while found:
            found = False
            for i, e in enumerate(edges):
                mk.Add(e)
                if mk.Error() != BRepBuilderAPI_DisconnectedWire:
                    found = True
                    del edges[i]
                    wire = mk.Wire()
                    break
        return wire

    def shape(self):
        result = self.mk.Shape()
        if result.IsNull():
            return result
        if result.ShapeType() == TopAbs_WIRE:
            return self._make_wire(result)
        if result.ShapeType() == TopAbs_COMPOUND:
            builder, comp = BRep_Builder(), TopoDS_Compound()
            builder.MakeCompound(comp)
            xp = TopExp_Explorer(result, TopAbs_WIRE)
            while xp.More():
                builder.Add(comp, self._make_wire(TopoDS.Wire(xp.Current())))
                xp.Next()
            return comp
        return result


# ── Part::ExtrusionHelper ──

def tapered_prism_offset(source, translation: gp_Vec, offset: float, second: bool = False):
    """ExtrusionHelper::createTaperedPrismOffset: the wire moved by translation and offset by offset."""
    t = gp_Trsf()
    t.SetTranslation(translation)
    moved = source.Moved(TopLoc_Location(t))
    if abs(offset) > CONFUSION:
        mk = _MakeOffsetFix()
        mk.init(GeomAbs_Arc)
        mk.init(GeomAbs_Intersection)
        mk.add_wire(moved)
        try:
            mk.perform(offset)
            shape = mk.shape()
        except Exception:
            raise DraftError("Extrusion: Offset could not be created") from None
        if not mk.is_done():
            raise DraftError("Extrusion: Offset could not be created")
    else:
        shape = moved
    if shape.IsNull():
        raise DraftError("Extrusion: end face of tapered extrusion is empty")
    if shape.ShapeType() == TopAbs_WIRE:
        return TopoDS.Wire(shape)
    if shape.ShapeType() == TopAbs_EDGE:
        return BRepBuilderAPI_MakeWire(TopoDS.Edge(shape)).Wire()
    # usually a compound: the angle is too large or small for the profile. FreeCAD logs "Extrusion: type of along
    # extrusion is not supported." and goes on with a null wire, which the loft then refuses
    return None


def make_element_draft(direction, length: float, taper: float, shape, drafts: list) -> None:
    """ExtrusionHelper::makeElementDraft(params, shape, drafts) for PartDesign: params.solid, lengthFwd = length,
    taperAngleFwd = taper (radians), innerWireTaper SameAsOuter, no reverse side."""
    distance = math.tan(taper) * length
    vec = gp_Vec(direction).Multiplied(length)
    fwd = abs(length) > CONFUSION
    if shape is None or shape.IsNull():
        raise DraftError("Not a valid shape")
    source = None
    if shape.ShapeType() == TopAbs_FACE:
        outer, inner = split_wires(shape)
        if outer is None:
            raise DraftError("Missing outer wire")
        if not inner:
            shape = outer
        else:
            pos = len(drafts)
            make_element_draft(direction, length, taper, outer, drafts)
            if len(drafts) != pos + 1:
                raise DraftError("Failed to make drafted extrusion")
            holes: list = []
            for w in inner:                      # lofted into solids of their own, then cut from the outer one
                make_element_draft(direction, length, taper, w, holes)
            if not holes:
                raise DraftError("Failed to make drafted extrusion with inner hole")
            drafts[-1] = element_boolean("cut", [drafts[-1], *holes])
            return
    if shape.ShapeType() == TopAbs_WIRE:
        fix = ShapeFix_Wire()
        fix.Load(TopoDS.Wire(shape))
        fix.FixReorder()
        fix.FixConnected()
        fix.FixClosed()
        source = fix.Wire()
    elif shape.ShapeType() == TopAbs_COMPOUND:
        it = TopoDS_Iterator(shape)
        while it.More():
            make_element_draft(direction, length, taper, it.Value(), drafts)
            it.Next()
    else:
        raise DraftError("Only a wire or a face is supported")
    if source is not None:
        sections = [source]                      # the source wire as the middle section; no reverse side here
        if fwd:
            sections.append(tapered_prism_offset(source, vec, distance))
        if any(s is None for s in sections):
            raise DraftError("BRep_API: command not done")     # StdFail_NotDone from the loft's Shape()
        mk = BRepOffsetAPI_ThruSections(True, True)
        for s in sections:
            mk.AddWire(s)
        try:
            mk.Build()
        except Exception:
            raise DraftError("BRep_API: command not done") from None
        if not mk.IsDone():
            raise DraftError("BRep_API: command not done")
        drafts.append(mk.Shape())


def draft(profile, direction, length: float, taper_degrees: float):
    """generateSingleExtrusionSide's tapered branch: None (no prism) past 90 degrees, else the drafts' compound, or
    the one draft (SingleShapeCompoundCreationPolicy::returnShape)."""
    taper = math.radians(taper_degrees)
    if abs(taper) > math.pi * 0.5 - ANGULAR:
        return None
    drafts: list = []
    make_element_draft(direction, length, taper, profile, drafts)
    if not drafts:
        return None
    if len(drafts) == 1:
        return drafts[0]
    builder, comp = BRep_Builder(), TopoDS_Compound()
    builder.MakeCompound(comp)
    for d in drafts:
        builder.Add(comp, d)
    return comp

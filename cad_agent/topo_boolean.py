# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses FreeCAD's boolean entry point (TopoShape::makeElementBoolean for Fuse, Cut
# and Common, over FCBRepAlgoAPI_BooleanOperation) and keeps FreeCAD's licence, the GNU Lesser General Public
# License, version 2.1 or (at your option) any later version; the text is in ../ui/LICENSE.
#
#   Derived from: src/Mod/Part/App/TopoShapeExpansion.cpp (makeElementBoolean, expandCompound;
#                 Copyright (c) 2022 Zheng, Lei) and src/Mod/Part/App/FCBRepAlgoAPI_BooleanOperation.cpp
#                 (Copyright (c) 2024 Eric Price (CorvusCorax))
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
"""FreeCAD's booleans, as PartDesign calls them: element_boolean("fuse" | "cut" | "common", [shape, tool, ...]).

TopoShape::makeElementBoolean expands compounds (for a fuse every input's, the first one's too; for a cut or a common
the tools'), makes the first input the argument and the rest the tools, and builds with FCBRepAlgoAPI_*: run in
parallel and non-destructive (SetNonDestructive, so a tool that shares sub-shapes with the argument, as a
BRepFeat_MakePrism up to a face of the base does, leaves both untouched and the result comes out in FreeCAD's order),
a fuzzy value when one is given, and a cut of a compound argument done child by child (RecursiveCutCompound).
"""
from __future__ import annotations

from OCP.BRep import BRep_Builder
from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_Box
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.TopAbs import TopAbs_COMPOUND
from OCP.TopoDS import TopoDS_Compound, TopoDS_Iterator
try:
    from OCP.TopTools import TopTools_ListOfShape
except ImportError:                     # OCP 8 moved OCCT's collections
    from OCP.collections import List_TopoDS_Shape as TopTools_ListOfShape

BOOLEAN_FUZZY = 1.0                     # Part::FuzzyHelper::getBooleanFuzzy()'s default
CONFUSION = 1e-7                        # Precision::Confusion()
MAKERS = {"fuse": BRepAlgoAPI_Fuse, "cut": BRepAlgoAPI_Cut, "common": BRepAlgoAPI_Common}


class BooleanError(ValueError):
    """What makeElementBoolean throws: a null input, or OCCT's boolean not done."""


def expand_compound(shape, out: list) -> None:
    """expandCompound: a compound's children, recursively; anything else as it is."""
    if shape is None or shape.IsNull():
        raise BooleanError("Null input shape")
    if shape.ShapeType() != TopAbs_COMPOUND:
        out.append(shape)
        return
    it = TopoDS_Iterator(shape)
    while it.More():
        expand_compound(it.Value(), out)
        it.Next()


def _inputs(maker: str, shapes: list):
    expanded: list = []
    if maker == "fuse":
        for i, s in enumerate(shapes):
            if s is None or s.IsNull():
                if i == 0:
                    return None                  # pre-TNP <null shape>.fuse() gives the null shape
                raise BooleanError("Null input shape")
            if s.ShapeType() == TopAbs_COMPOUND:
                if not expanded:
                    expanded += shapes[:i]
                expand_compound(s, expanded)
            elif expanded:
                expanded.append(s)
    else:
        for i in range(1, len(shapes)):
            s = shapes[i]
            if s is None or s.IsNull():
                raise BooleanError("Null input shape")
            if s.ShapeType() == TopAbs_COMPOUND:
                if not expanded:
                    expanded += shapes[:i]
                before = len(expanded)
                expand_compound(s, expanded)
                if maker == "common" and len(expanded) == before:
                    expanded.append(s)
            elif expanded:
                expanded.append(s)
    return expanded or shapes


def auto_fuzzy(shapes: list) -> float:
    """FCBRepAlgoAPIHelper::setAutoFuzzy: getBooleanFuzzy() times the diagonal of the inputs' box times Confusion."""
    box = Bnd_Box()
    for s in shapes:
        BRepBndLib.Add_s(s, box)
    return BOOLEAN_FUZZY * box.SquareExtent() ** 0.5 * CONFUSION


def _build(maker: str, args: list, tools: list, fuzzy: float):
    """One FCBRepAlgoAPI_* Build."""
    mk = MAKERS[maker]()
    mk.SetRunParallel(True)
    mk.SetNonDestructive(True)
    a, t = TopTools_ListOfShape(), TopTools_ListOfShape()
    for s in args:
        a.Append(s)
    for s in tools:
        t.Append(s)
    mk.SetArguments(a)
    mk.SetTools(t)
    if fuzzy > 0.0:
        mk.SetFuzzyValue(fuzzy)
    mk.Build()
    if not mk.IsDone():
        raise BooleanError(f"Boolean {maker} failed")
    return mk.Shape()


def element_boolean(maker: str, shapes: list, fuzzy: float = -1.0):
    """TopoShape::makeElementBoolean(maker, shapes, op, tolerance) for "fuse", "cut" and "common". fuzzy is its
    tolerance: -1, the default of makeElementFuse/Cut/Xor and makeElementBoolean, sets the auto fuzzy value; a
    feature's FuzzyTolerance (0 unless set) is passed by Pad, Pocket, Groove, Hole and the primitives."""
    if not shapes:
        raise BooleanError("Null shape")
    inputs = _inputs(maker, list(shapes))
    if inputs is None:
        return None
    if len(inputs) == 1:
        return inputs[0]
    for s in inputs:
        if s is None or s.IsNull():
            raise BooleanError("Null input shape")
    args, tools = [inputs[0]], list(inputs[1:])
    if fuzzy < 0.0:
        fuzzy = auto_fuzzy(inputs)
    if maker == "cut" and args[0].ShapeType() == TopAbs_COMPOUND:
        # FCBRepAlgoAPI_BooleanOperation::RecursiveCutCompound: each child cut by the tools, in a compound
        builder, comp = BRep_Builder(), TopoDS_Compound()
        builder.MakeCompound(comp)
        it = TopoDS_Iterator(args[0])
        while it.More():
            builder.Add(comp, _build("cut", [it.Value()], tools, fuzzy))
            it.Next()
        return comp
    return _build(maker, args, tools, fuzzy)

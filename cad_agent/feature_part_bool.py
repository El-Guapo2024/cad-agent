# SPDX-License-Identifier: LGPL-2.1-or-later
# A port of FreeCAD's Part booleans (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), each file
# LGPL-2.1-or-later as it states:
#   src/Mod/Part/App/FeaturePartBoolean.cpp, FeaturePartCut.cpp, FeaturePartFuse.cpp, FeaturePartCommon.cpp,
#   FeaturePartSection.cpp: Copyright (c) 2002 Jürgen Riegel
#   src/Mod/Part/App/FCBRepAlgoAPI_BooleanOperation.cpp, FCBRepAlgoAPI_Section.cpp: Copyright (c) 2024 Eric Price
#   src/Mod/Part/App/TopoShapeExpansion.cpp (makeElementBoolean): Copyright (c) 2022 Zheng, Lei; 2023 Ondsel
#   src/Mod/Part/BOPTools/BOPFeatures.py: Copyright (c) 2023 Werner Mayer
"""Part's booleans: Cut, Fuse and MultiFuse, Common and MultiCommon, Section.

    Part.Cut("Cut", "Box", "Cylinder")                    Part::Cut, Base and Tool
    Part.MultiFuse("Fusion", ["Box", "Sphere"])           Part::MultiFuse, Shapes (Part_Fuse makes this one)
    Part.MultiCommon("Common", ["Box", "Sphere"])         Part::MultiCommon (Part_Common)
    Part.Fuse("Fusion", "Box", "Sphere"), Part.Common(...) Part::Fuse and Part::Common, Base and Tool
    Part.Section("Section", "Box", "Sphere")              Part::Section, the intersection edges

Each has refine (FreeCAD's Refine, True as Preferences > Part/Part Design > Boolean has it by default); a Section also
approximation (False); a MultiCommon behavior ("CommonOfAllShapes"). The operation is FCBRepAlgoAPI's: the boolean
fuzzy value FreeCAD sets from the inputs' bounding box (BooleanFuzzy 1.0 x diagonal x Precision::Confusion), parallel
and non-destructive, a Cut by a compound tool fusing the tool's pieces first, then the check FreeCAD runs
(Preferences' CheckModel, on by default: "Resulting shape is invalid") and the refine. The builds, the fuzzy value and
makeElementBoolean are pd-kernel's ports (cad_agent/topo_boolean.py), the refine its BRepBuilderAPI_RefineModel
(cad_agent/refine.py), shared with PartDesign; what is Part's own here is Part::Cut's Build of a compound tool (its
pieces fused first, RecursiveCutFusedTools) and the Section.
"""
from __future__ import annotations

import math

from . import feature as F
from .feature_part import PartObject, register

try:
    from OCP.BRep import BRep_Builder
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.TopAbs import TopAbs_COMPOUND, TopAbs_FACE, TopAbs_SOLID
    from OCP.TopoDS import TopoDS_Compound, TopoDS_Iterator
except ImportError:                     # pragma: no cover - only FreeCAD's Python lands here
    pass

CONFUSION = 1e-7


def _list(shapes):
    out = F.TopTools_ListOfShape()
    for s in shapes:
        out.Append(s)
    return out


def _children(shape):
    out = []
    it = TopoDS_Iterator(shape)
    while it.More():
        out.append(it.Value())
        it.Next()
    return out


def _flatten(shape, out):
    """FCBRepAlgoAPI_BooleanOperation::RecursiveAddTools."""
    for c in _children(shape):
        if c.ShapeType() == TopAbs_COMPOUND:
            _flatten(c, out)
        else:
            out.append(c)
    return out


def auto_fuzzy(shapes) -> float:
    """FCBRepAlgoAPIHelper::setAutoFuzzy (cad_agent/topo_boolean.py, pd-kernel's port)."""
    from .topo_boolean import auto_fuzzy as fuzzy
    return fuzzy(list(shapes))


def _run(kind, args, tools, fuzzy):
    """One FCBRepAlgoAPI_* Build (topo_boolean._build: parallel, non-destructive, the fuzzy value); None when OCCT did
    not finish."""
    from .topo_boolean import BooleanError, _build
    try:
        return _build(kind, list(args), list(tools), fuzzy)
    except BooleanError:
        return None


def fc_boolean(kind, base, tool, fuzzy=None):
    """FCBRepAlgoAPI_Fuse/Cut/Common(base, tool): the shape, or None when OCCT did not finish."""
    fuzzy = auto_fuzzy([base, tool]) if fuzzy is None else fuzzy
    if kind == "cut" and tool.ShapeType() == TopAbs_COMPOUND:          # RecursiveCutFusedTools
        tools = _flatten(tool, [])
        if len(tools) >= 2:
            fused = _run("fuse", tools[:1], tools[1:], fuzzy)
            if fused is None:
                return None
            tools = _flatten(fused, []) if fused.ShapeType() == TopAbs_COMPOUND else [fused]
        return _run("cut", [base], tools, fuzzy)
    if kind == "cut" and base.ShapeType() == TopAbs_COMPOUND:          # RecursiveCutCompound
        b = BRep_Builder()
        comp = TopoDS_Compound()
        b.MakeCompound(comp)
        for c in _children(base):
            r = _run("cut", [c], [tool], fuzzy)
            if r is None:
                return None
            b.Add(comp, r)
        return comp
    return _run(kind, [base], [tool], fuzzy)


def check_model(shape):
    """throwIfInvalidIfCheckModel: Preferences' CheckModel, on by default."""
    if not BRepCheck_Analyzer(shape).IsValid():
        raise F.FeatureError("Resulting shape is invalid")


def refine(shape):
    """TopoShape::makeElementRefine (BRepBuilderAPI_RefineModel merges faces; a shape with none is left as it is)."""
    if shape is None or not F._count(shape, TopAbs_FACE):
        return shape
    return F._refine(shape)


class _Boolean(PartObject):
    """Part::Boolean: Base and Tool, Refine."""
    POS = ("base", "tool")
    REFS = ("base", "tool")
    INPUTS = ("base", "tool")
    OP = ""
    DEFAULTS = {"base": None, "tool": None, "refine": True, **PartObject.COMMON}

    def shape(self, ctx, params):
        if self.base is None or self.tool is None:
            raise F.FeatureError("Linked object is not a Part object")
        base, tool = ctx.shape(self.base, f"{self.name}.Base"), ctx.shape(self.tool, f"{self.name}.Tool")
        res = self.operate(base, tool)
        if res is None:
            msg = "Boolean operation failed"
            if base.ShapeType() != TopAbs_SOLID:
                msg += f"\n{ctx.label(self.base)} is not a solid"
            if tool.ShapeType() != TopAbs_SOLID:
                msg += f"\n{ctx.label(self.tool)} is not a solid"
            raise F.FeatureError(msg)
        if res.IsNull():
            raise F.FeatureError("Resulting shape is null")
        check_model(res)
        return refine(res) if self.refine else res

    def operate(self, base, tool):
        return fc_boolean(self.OP, base, tool)


class Cut(_Boolean):
    """Part::Cut: Base minus Tool (Part_Cut, BOPFeatures.make_cut)."""
    kind, TYPE_ID, OP, TRANSACTION = "Part.Cut", "Part::Cut", "cut", "Part Cut"


class Fuse(_Boolean):
    """Part::Fuse: Base and Tool united (BOPFeatures.make_fuse)."""
    kind, TYPE_ID, OP, TRANSACTION = "Part.Fuse", "Part::Fuse", "fuse", "Fusion"


class Common(_Boolean):
    """Part::Common: what Base and Tool have in common (BOPFeatures.make_common)."""
    kind, TYPE_ID, OP, TRANSACTION = "Part.Common", "Part::Common", "common", "Common"


class Section(_Boolean):
    """Part::Section: the edges where Base and Tool meet (Part_Section)."""
    kind, TYPE_ID, TRANSACTION = "Part.Section", "Part::Section", "Section"
    DEFAULTS = {**_Boolean.DEFAULTS, "approximation": False}

    def operate(self, base, tool):
        mk = BRepAlgoAPI_Section()               # FCBRepAlgoAPI_Section(): parallel, non-destructive
        mk.SetRunParallel(True)
        mk.SetNonDestructive(True)
        mk.Init1(base)
        mk.Init2(tool)
        mk.Approximation(self.approximation)
        mk.SetFuzzyValue(auto_fuzzy([base, tool]))
        mk.Build()
        if not mk.IsDone():
            raise F.FeatureError("Section failed")
        return mk.Shape()


class MultiFuse(PartObject):
    """Part::MultiFuse: all of Shapes united; one compound alone is its children united (Part_Fuse)."""
    kind, TYPE_ID, TRANSACTION = "Part.MultiFuse", "Part::MultiFuse", "Fusion"
    POS = ("shapes",)
    REFS = ("shapes",)
    INPUTS = ("shapes",)
    DEFAULTS = {"shapes": (), "refine": True, **PartObject.COMMON}

    def shape(self, ctx, params):
        shapes = [ctx.shape(s, f"{self.name}.Shapes") for s in self.shapes]
        while len(shapes) == 1 and shapes[0] is not None and shapes[0].ShapeType() == TopAbs_COMPOUND:
            shapes = _children(shapes[0])
        if len(shapes) < 2:
            raise F.FeatureError("Not enough shape objects linked")
        for s in shapes:
            if s is None or s.IsNull():
                raise F.FeatureError("Input shape is null")
        res = _run("fuse", shapes[:1], shapes[1:], auto_fuzzy(shapes))
        if res is None:
            raise F.FeatureError("MultiFusion failed")
        if res.IsNull():
            raise F.FeatureError("Resulting shape is null")
        check_model(res)
        return refine(res) if self.refine else res


BEHAVIORS = ("CommonOfAllShapes", "CommonOfFirstAndRest")


class MultiCommon(PartObject):
    """Part::MultiCommon: what all of Shapes have in common (Part_Common); one compound alone, its children's."""
    kind, TYPE_ID, TRANSACTION = "Part.MultiCommon", "Part::MultiCommon", "Common"
    POS = ("shapes",)
    REFS = ("shapes",)
    INPUTS = ("shapes",)
    DEFAULTS = {"shapes": (), "refine": True, "behavior": "CommonOfAllShapes", **PartObject.COMMON}
    ENUMS = {"behavior": BEHAVIORS}

    def shape(self, ctx, params):
        from .feature_transform import element_boolean      # makeElementBoolean (cad_agent/topo_boolean.py)
        shapes = [ctx.shape(s, f"{self.name}.Shapes") for s in self.shapes]
        for s in shapes:
            if s is None or s.IsNull():
                raise F.FeatureError("Input shape is null")
        if not shapes:
            raise F.FeatureError("Resulting shape is null")
        if self.behavior == "CommonOfAllShapes":
            if len(shapes) == 1 and shapes[0].ShapeType() == TopAbs_COMPOUND:
                shapes = _children(shapes[0])
            res = shapes[0]
            for tool in shapes:                   # one at a time, the first with itself too, as FreeCAD does
                res = element_boolean("common", [res, tool])
        else:
            res = element_boolean("common", shapes)
        if res is None or res.IsNull():
            raise F.FeatureError("Resulting shape is null")
        check_model(res)
        return refine(res) if self.refine else res


BOOLEANS = (Cut, Fuse, Common, Section, MultiFuse, MultiCommon)
register(*BOOLEANS)

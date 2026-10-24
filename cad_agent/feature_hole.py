# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses FreeCAD's PartDesign Hole function by function and keeps FreeCAD's licence, the
# GNU Lesser General Public License, version 2.1 or (at your option) any later version; the text is in ../ui/LICENSE.
#
#   Derived from: src/Mod/PartDesign/App/FeatureHole.cpp (Copyright (c) 2011 Juergen Riegel
#                 <FreeCAD@juergen-riegel.net>): the properties and their defaults, onChanged and what it calls
#                 (updateHoleCutParams, determineDiameter, findClosestDesignation, updateThreadDepthParam, ...),
#                 execute, findHoles, makeThread; src/Mod/Part/App/TopoShape.cpp (makeLongHelix; Copyright (c) 2002
#                 Jürgen Riegel), src/Mod/Part/App/FaceMakerCheese.cpp (makeFace for one wire; Copyright (c) 2016
#                 Victor Titov (DeepSOIC)), src/App/Enumeration.cpp and PropertyStandard.cpp (how an enumeration
#                 keeps its value when its list changes)
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
"""PartDesign::Hole for a FEATURES list (cad_agent/feature.py).

    Hole("Hole", "Sketch001", thread_type="ISOMetricProfile", thread_size="M6x1.0", threaded=True,
         depth_type="ThroughAll", hole_cut_type="ISO 4762")

A hole is drilled at the centre of every circle and arc of its sketch, and at every point (BaseProfileType 7, what a
new Hole gets), down the sketch's normal unless reversed. The properties are FreeCAD's in snake_case:

    threaded, model_thread, cosmetic_thread, thread_type (None, ISOMetricProfile, ISOMetricFineProfile, UNC, UNF, UNEF,
    NPT, BSP, BSW, BSF, ISOTyre), thread_size ("M6x1.0", "1/4", ...), thread_class, thread_fit, thread_direction,
    diameter, use_custom_thread_clearance, custom_thread_clearance, depth_type (Dimension, ThroughAll), depth,
    thread_depth_type (Hole Depth, Dimension, Tapped (DIN76)), thread_depth, hole_cut_type (None, Counterbore,
    Countersink, Counterdrill, and for ISO threads the screw norms: ISO 4762, ISO 10642, DIN 7984, ...),
    hole_cut_custom_values, hole_cut_diameter, hole_cut_depth, hole_cut_countersink_angle, drill_point (Flat, Angled),
    drill_point_angle, drill_for_depth, tapered, tapered_angle, base_profile_type, reversed, start_type
    ("Profile plane" | "Offset"), start_offset, refine.

In FreeCAD these follow from each other as they are set (Hole::onChanged): choosing a thread size sets the diameter from
FreeCAD's tables (the tap drill for a threaded hole, the ISO 273 / ASME B18.2.8 clearance otherwise), choosing a screw's
counterbore sets its diameter and depth. HoleState here is that cascade, ported call for call, so the part file holds
only what was chosen and the rest comes out as FreeCAD's: Hole(...) sets the given properties in one fixed order
(ORDER), as to_freecad() sets them in FreeCAD, and the values are what FreeCAD's properties then hold. Hole.minimal()
leaves out a value the others give anyway, so the file says `thread_size="M6x1.0"` and not the 6.6 mm it means.
"""
from __future__ import annotations

import math

from . import feature_hole_tables as T

try:                                    # the kernel; FreeCAD's Python reads the vocabulary without it
    from OCP.BRep import BRep_Builder
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeSolid,
                                    BRepBuilderAPI_MakeWire, BRepBuilderAPI_Sewing, BRepBuilderAPI_Transformed)
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.BRepLib import BRepLib
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipeShell
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeRevol
    from OCP.GC import GC_MakeArcOfCircle
    try:
        from OCP.GCE2d import GCE2d_MakeSegment
    except ImportError:                 # OCCT 7.9 folds GCE2d into GC: GC_MakeSegment2d
        from OCP.GC import GC_MakeSegment2d as GCE2d_MakeSegment
    from OCP.Geom import Geom_ConicalSurface, Geom_CylindricalSurface
    from OCP.Geom2d import Geom2d_Line
    from OCP.GeomAbs import GeomAbs_Circle
    from OCP.TopAbs import TopAbs_IN, TopAbs_SOLID
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS, TopoDS_Compound
    from OCP.gp import gp, gp_Ax1, gp_Ax2, gp_Ax2d, gp_Ax3, gp_Dir, gp_Dir2d, gp_Pnt, gp_Pnt2d, gp_Trsf, gp_Vec
    try:
        from OCP.TopTools import TopTools_ListOfShape
    except ImportError:                 # OCP 8 moved OCCT's collections
        from OCP.collections import List_TopoDS_Shape as TopTools_ListOfShape
except ImportError:                     # pragma: no cover - only FreeCAD's Python lands here
    pass

CONFUSION = 1e-7          # Precision::Confusion()
START_TYPES = ("Profile plane", "Offset")              # ProfileBased::StartTypesEnums, but Reference
ANGULAR = 1e-12
E = T.ENUMS
THREAD_TYPES = E["ThreadTypeEnums"]
# Hole::addCutType: the screw norms join the ISO metric (coarse and fine) lists, keyed by (thread type, name).
CUTS: dict = {}
_ISO_CUT_TYPES = list(E["HoleCutType_ISOmetric_Enums"])
_ISOFINE_CUT_TYPES = list(E["HoleCutType_ISOmetricfine_Enums"])
for _c in T.CUT_DEFINITIONS:
    _t = "ISOMetricProfile" if _c["thread_type"] == "metric" else "ISOMetricFineProfile"
    CUTS.setdefault((_t, _c["name"]), _c)                      # std::map::emplace: the first one stays
    _lst = _ISO_CUT_TYPES if _t == "ISOMetricProfile" else _ISOFINE_CUT_TYPES
    if _c["name"] not in _lst:
        _lst.append(_c["name"])
FLOAT_ANGLE = (math.degrees(ANGULAR), 180.0 - math.degrees(ANGULAR))   # Hole::floatAngle
DIAMETER_MIN = 10 * CONFUSION                                          # diameterRange

# The order Hole(...) and to_freecad() set the given properties in: a thread before what follows from it, the depth
# before the thread depth it bounds, the diameter before the cut that must be wider.
ORDER = ["ThreadType", "ThreadSize", "Threaded", "ModelThread", "CosmeticThread", "ThreadClass", "ThreadFit",
         "ThreadDirection", "UseCustomThreadClearance", "CustomThreadClearance", "Diameter", "DepthType", "Depth",
         "ThreadDepthType", "ThreadDepth", "HoleCutType", "HoleCutCustomValues", "HoleCutDiameter", "HoleCutDepth",
         "HoleCutCountersinkAngle", "DrillPoint", "DrillPointAngle", "DrillForDepth", "Tapered", "TaperedAngle",
         "BaseProfileType", "Reversed", "StartType", "StartOffset", "Refine"]
KIND = {"Threaded": bool, "ModelThread": bool, "CosmeticThread": bool, "HoleCutCustomValues": bool, "DrillForDepth": bool,
        "Tapered": bool, "UseCustomThreadClearance": bool, "Reversed": bool, "Refine": bool, "BaseProfileType": int}
ENUM_PROPS = ("ThreadType", "ThreadSize", "ThreadClass", "ThreadFit", "ThreadDirection", "HoleCutType", "DepthType",
              "ThreadDepthType", "DrillPoint", "StartType")
LENGTHS = ("Diameter", "ThreadDiameter", "HoleCutDiameter", "HoleCutDepth", "Depth", "ThreadDepth",
           "CustomThreadClearance", "StartOffset")
ANGLES = ("HoleCutCountersinkAngle", "DrillPointAngle", "TaperedAngle")


def snake(name: str) -> str:
    out = ""
    for i, c in enumerate(name):
        out += ("_" if i and c.isupper() and not name[i - 1].isupper() else "") + c.lower()
    return out


SNAKE = {p: snake(p) for p in ORDER + ["ThreadDiameter"]}
CAMEL = {v: k for k, v in SNAKE.items()}


def designations(thread_type_index):
    return [t[0] for t in T.THREADS[THREAD_TYPES[thread_type_index]]]


class _Enum:
    """App::Enumeration: an index into a list; a new list keeps the value by its name, or falls to the first."""

    def __init__(self, items, index=0):
        self.items, self.index = list(items), index

    def valid(self):
        return bool(self.items) and 0 <= self.index < len(self.items)

    def text(self):
        if not self.valid():
            raise FeatureError("Cannot get value from invalid enumeration")
        return self.items[self.index]

    def set_text(self, v):
        self.index = 0
        for i, s in enumerate(self.items):
            if s == v:
                self.index = i
                break

    def set_items(self, items):
        preserve = self.valid()
        old = self.text() if preserve else None
        self.items = list(items)
        if self.index < 0:
            self.index = 0
        if preserve:
            self.set_text(old)


class HoleState:
    """PartDesign::Hole's properties and what setting one does to the others (Hole::onChanged), from a new Hole (the
    constructor's values and setupObject's BaseProfileType 7). through_all is ProfileBased::getThroughAllLength for the
    body the hole cuts, or None where there is no shape (the part file read without building): the values that need it
    then stay as they were."""

    def __init__(self, through_all=None):
        self.through_all = through_all
        self.unknown = False                      # a value wanted the through-all length and did not get it
        self.v = {"Threaded": False, "ModelThread": False, "CosmeticThread": True, "ThreadPitch": 0.0,
                  "Diameter": 6.0, "ThreadDiameter": 0.0, "HoleCutCustomValues": False, "HoleCutDiameter": 0.0,
                  "HoleCutDepth": 0.0, "HoleCutCountersinkAngle": 90.0, "Depth": 25.0, "ThreadDepth": 23.5,
                  "DrillPointAngle": 118.0, "DrillForDepth": False, "Tapered": False, "TaperedAngle": 90.0,
                  "UseCustomThreadClearance": False, "CustomThreadClearance": 0.0, "BaseProfileType": 7,
                  "StartOffset": 0.0, "Reversed": False, "Refine": True}
        self.e = {"ThreadType": _Enum(THREAD_TYPES), "ThreadSize": _Enum(designations(0)),
                  "ThreadClass": _Enum(E["ThreadClass_None_Enums"]), "ThreadFit": _Enum(E["ClearanceMetricEnums"]),
                  "ThreadDirection": _Enum(E["ThreadDirectionEnums"]),
                  "HoleCutType": _Enum(E["HoleCutType_None_Enums"]), "DepthType": _Enum(E["DepthTypeEnums"]),
                  "ThreadDepthType": _Enum(E["ThreadDepthTypeEnums"]), "DrillPoint": _Enum(E["DrillPointEnums"], 1),
                  "StartType": _Enum(START_TYPES + ("Reference",))}
        # ReadOnly as a new Hole has it (the constructor's setReadOnly calls)
        self.ro = {"ThreadDiameter", "ThreadDirection", "HoleCutCustomValues", "HoleCutDiameter", "HoleCutDepth",
                   "HoleCutCountersinkAngle"}

    # ── App::Property: get, set (which calls onChanged), setEnums, setReadOnly ──
    def __getitem__(self, p):
        return self.e[p].text() if p in self.e else self.v[p]

    def index(self, p):
        return self.e[p].index if self.e[p].valid() else -1

    def set(self, p, val):
        if p in self.e:
            if isinstance(val, int) and not isinstance(val, bool):
                self.e[p].index = val
            else:
                self.e[p].set_text(val)
        else:
            self.v[p] = val
        self.on_changed(p)

    def set_enums(self, p, items):
        self.e[p].set_items(items)
        self.on_changed(p)

    def read_only(self, p, on=True):
        (self.ro.add if on else self.ro.discard)(p)

    def length_through_all(self):
        if self.through_all is None:
            self.unknown = True
            return None
        return self.through_all

    def assign(self, p, raw):
        """A property set from Python (PartDesign's to_freecad, a script): the value checked and clamped as
        setPyObject does, then set."""
        if p in self.e:
            if raw not in self.e[p].items:
                raise FeatureError(f"Hole.{SNAKE[p]}: {raw!r} is not one of {', '.join(self.e[p].items)}")
            self.set(p, raw)
            return
        kind = KIND.get(p, float)
        if kind is bool:
            self.set(p, bool(raw))
        elif kind is int:
            self.set(p, int(raw))
        else:
            x = float(raw)
            if p in ANGLES:
                x = min(max(x, FLOAT_ANGLE[0]), FLOAT_ANGLE[1])
            elif p == "Diameter":
                x = max(x, DIAMETER_MIN)
            self.set(p, x)

    # ── Hole's helpers ──
    def thread(self):
        t, s = self.index("ThreadType"), self.index("ThreadSize")
        if t < 0:
            raise FeatureError("Thread type out of range")
        if s < 0:
            raise FeatureError("Thread size out of range")
        return T.THREADS[THREAD_TYPES[t]][s]

    def thread_pitch(self):
        return self.thread()[2]

    def countersink_angle(self):
        t = self["ThreadType"]
        if t in ("BSW", "BSF"):
            return 100.0
        if t in ("UNC", "UNF", "UNEF"):
            return 82.0
        return 90.0

    def thread_class_clearance(self):
        pitch = self.thread_pitch()
        cls = self["ThreadClass"]
        if len(cls) > 1 and cls[1] == "G":
            for p, g in T.THREAD_CLASS_ISO_DATA:
                if pitch <= p:
                    return g
        return 0.0

    def thread_runout(self, mode=1):
        pitch = self.thread_pitch()
        sf = {1: 1.0, 2: 0.625, 3: 1.6}[mode]
        for p, e1 in T.THREAD_RUNOUT:
            if pitch <= p:
                return sf * e1
        return 4 * pitch

    def is_dynamic_counterbore(self, thread, cut):
        c = CUTS.get((thread, cut))
        return bool(c) and c["cut_type"] == "counterbore"

    def is_dynamic_countersink(self, thread, cut):
        c = CUTS.get((thread, cut))
        return bool(c) and c["cut_type"] == "countersink"

    @staticmethod
    def bore(cut, thread):
        for row in cut["data"]:
            if row[0] == thread:
                return row
        return ("None", 0.0, 0.0)

    @staticmethod
    def sink(cut, thread):
        for row in cut["data"]:
            if row[0] == thread:
                return row
        return ("None", 0.0)

    def calculate_and_set_counterbore(self):
        d = self.v["Diameter"]
        self.set("HoleCutDiameter", 1.5 * d + 1.0)
        self.set("HoleCutDepth", d)

    def calculate_and_set_countersink(self):
        self.set("HoleCutDiameter", 2.24 * self.v["Diameter"])

    def update_hole_cut_params(self):
        cut = self["HoleCutType"]
        if cut == "None":
            return
        if self.index("ThreadType") < 0:
            raise FeatureError("Thread type out of range")
        dia = self.v["Diameter"]
        ttype = self["ThreadType"]
        if ttype in ("ISOMetricProfile", "ISOMetricFineProfile"):
            if self.index("ThreadSize") < 0:
                raise FeatureError("Thread size out of range")
            size = self["ThreadSize"]
            if cut == "Counterbore":
                counter = CUTS[(ttype, "ISO 4762")]
                dimen = self.bore(counter, size)
                if self.v["HoleCutDiameter"] == 0.0 or self.v["HoleCutDiameter"] <= dia:
                    if dimen[1] != 0.0:
                        self.set("HoleCutDiameter", dimen[1])
                        self.set("HoleCutDepth", dimen[2])
                    else:
                        self.calculate_and_set_counterbore()
                if self.v["HoleCutDepth"] == 0.0:
                    self.set("HoleCutDepth", dimen[2])
                self.read_only("HoleCutDiameter", False)
                self.read_only("HoleCutDepth", False)
                self.read_only("HoleCutCountersinkAngle", True)
            elif cut in ("Countersink", "Counterdrill"):
                counter = CUTS[(ttype, "ISO 10642")]
                if self.v["HoleCutDiameter"] == 0.0 or self.v["HoleCutDiameter"] <= dia:
                    dimen = self.sink(counter, size)
                    self.set("HoleCutCountersinkAngle", counter["angle"])
                    if dimen[1] != 0.0:
                        self.set("HoleCutDiameter", dimen[1])
                    else:
                        self.calculate_and_set_countersink()
                if self.v["HoleCutCountersinkAngle"] == 0.0:
                    self.set("HoleCutCountersinkAngle", counter["angle"])
                if self.v["HoleCutDepth"] == 0.0:
                    if cut == "Counterdrill":
                        self.set("HoleCutDepth", 1.0)
                self.read_only("HoleCutDiameter", False)
                self.read_only("HoleCutDepth", False)
                self.read_only("HoleCutCountersinkAngle", False)
            counter = CUTS.get((ttype, cut))
            if counter is not None:
                if counter["cut_type"] == "counterbore":
                    self.set("HoleCutCountersinkAngle", 90.0)
                    self.read_only("HoleCutCountersinkAngle", True)
                    dimen = self.bore(counter, size)
                    if dimen[0] == "None":
                        self.calculate_and_set_counterbore()
                        self.read_only("HoleCutCustomValues", True)
                        if not self.v["HoleCutCustomValues"]:
                            self.set("HoleCutCustomValues", True)
                            self.read_only("HoleCutDiameter", False)
                            self.read_only("HoleCutDepth", False)
                    else:
                        custom, custom_ro = self.v["HoleCutCustomValues"], "HoleCutCustomValues" in self.ro
                        if not custom or (custom and custom_ro):
                            self.set("HoleCutDiameter", dimen[1])
                            self.set("HoleCutDepth", dimen[2])
                            self.read_only("HoleCutDiameter", True)
                            self.read_only("HoleCutDepth", True)
                            if self.v["HoleCutCustomValues"] and "HoleCutCustomValues" in self.ro:
                                self.set("HoleCutCustomValues", False)
                        else:
                            self.read_only("HoleCutDiameter", False)
                            self.read_only("HoleCutDepth", False)
                        self.read_only("HoleCutCustomValues", False)
                else:
                    dimen = self.sink(counter, size)
                    if dimen[0] == "None":
                        if self.v["HoleCutCountersinkAngle"] == 0.0:
                            self.set("HoleCutCountersinkAngle", counter["angle"])
                        self.calculate_and_set_countersink()
                        self.read_only("HoleCutCustomValues", True)
                        if not self.v["HoleCutCustomValues"]:
                            self.set("HoleCutCustomValues", True)
                            self.read_only("HoleCutDiameter", False)
                            self.read_only("HoleCutDepth", False)
                            self.read_only("HoleCutCountersinkAngle", False)
                    else:
                        custom, custom_ro = self.v["HoleCutCustomValues"], "HoleCutCustomValues" in self.ro
                        if not custom or (custom and custom_ro):
                            self.set("HoleCutDiameter", dimen[1])
                            self.read_only("HoleCutDiameter", True)
                            self.read_only("HoleCutDepth", True)
                            self.set("HoleCutCountersinkAngle", counter["angle"])
                            self.read_only("HoleCutCountersinkAngle", True)
                            if self.v["HoleCutCustomValues"] and "HoleCutCustomValues" in self.ro:
                                self.set("HoleCutCustomValues", False)
                        else:
                            self.read_only("HoleCutDiameter", False)
                            self.read_only("HoleCutDepth", False)
                            self.read_only("HoleCutCountersinkAngle", False)
                        self.read_only("HoleCutCustomValues", False)
        else:
            if cut == "Counterbore":
                if self.v["HoleCutDiameter"] == 0.0 or self.v["HoleCutDiameter"] <= dia:
                    self.set("HoleCutDiameter", dia * 1.6)
                    self.set("HoleCutDepth", dia * 0.9)
                if self.v["HoleCutDepth"] == 0.0:
                    self.set("HoleCutDepth", dia * 0.9)
                self.read_only("HoleCutDiameter", False)
                self.read_only("HoleCutDepth", False)
            elif cut in ("Countersink", "Counterdrill"):
                if self.v["HoleCutDiameter"] == 0.0 or self.v["HoleCutDiameter"] <= dia:
                    self.set("HoleCutDiameter", dia * 1.7)
                    self.set("HoleCutCountersinkAngle", self.countersink_angle())
                if self.v["HoleCutCountersinkAngle"] == 0.0:
                    self.set("HoleCutCountersinkAngle", self.countersink_angle())
                if self.v["HoleCutDepth"] == 0.0:
                    if cut == "Counterdrill":
                        self.set("HoleCutDepth", 1.0)
                self.read_only("HoleCutDiameter", False)
                self.read_only("HoleCutDepth", False)
                self.read_only("HoleCutCountersinkAngle", False)

    def update_thread_depth_param(self):
        method, depth = self["ThreadDepthType"], self["DepthType"]
        if depth == "Dimension":
            if method == "Hole Depth":
                self.set("ThreadDepth", self.v["Depth"])
            elif method == "Dimension":
                if self.v["ThreadDepth"] > self.v["Depth"]:
                    self.set("ThreadDepth", self.v["Depth"])
                else:
                    self.set("ThreadDepth", self.v["ThreadDepth"])
            elif method == "Tapped (DIN76)":
                self.set("ThreadDepth", self.v["Depth"] - self.thread_runout())
        elif depth == "ThroughAll":
            length = self.length_through_all()
            if length is None:
                return
            if method != "Dimension":
                self.set("ThreadDepth", length)
            elif self.v["ThreadDepth"] > length:
                self.set("ThreadDepth", length)
            else:
                self.set("ThreadDepth", self.v["ThreadDepth"])

    def determine_diameter(self):
        t, s = self.index("ThreadType"), self.index("ThreadSize")
        if t < 0:
            raise FeatureError("Thread type out of range")
        if s < 0:
            raise FeatureError("Thread size out of range")
        if t == 0:
            return None
        name, diameter, pitch, tap = T.THREADS[THREAD_TYPES[t]][s]
        ttype = self["ThreadType"]
        clearance = 0.0
        if self.v["Threaded"]:
            if self.v["ModelThread"]:
                clearance = self.v["CustomThreadClearance"] if self.v["UseCustomThreadClearance"] \
                    else self.thread_class_clearance()
            if tap > 0:
                return tap + clearance
            if ttype in ("BSP", "BSW", "BSF"):
                thread = 2 * (0.640327 * pitch)
                return diameter - thread * 0.75 + clearance
            if ttype == "NPT":
                thread = 2 * (0.8 * pitch)
                return diameter - thread * 0.75 + clearance
            return diameter - pitch + clearance
        fit = self.index("ThreadFit")
        if fit not in (0, 1, 2):
            raise FeatureError("Thread fit out of range")
        if ttype in ("ISOMetricProfile", "ISOMetricFineProfile"):
            col, factor = {0: (2, 1.10), 1: (1, 1.06), 2: (3, 1.16)}[fit]
            for row in T.METRIC_HOLE_DIAMETERS:
                if row[0] == diameter:
                    return row[col]
            return diameter * factor
        if ttype in ("UNC", "UNF", "UNEF"):
            col, factor = {0: (2, 1.08), 1: (1, 1.04), 2: (3, 1.12)}[fit]
            for row in T.UTS_HOLE_DIAMETERS:
                if row[0] == name:
                    return row[col]
            return diameter * factor
        return diameter * {0: 1.1, 1: 1.05, 2: 1.15}[fit]

    def update_diameter_param(self):
        t, s = self.index("ThreadType"), self.index("ThreadSize")
        if t > 0 and s > 0:
            self.set("ThreadDiameter", T.THREADS[THREAD_TYPES[t]][s][1])
        d = self.determine_diameter()
        if d is not None:
            self.set("Diameter", d)

    def find_closest_designation(self):
        t = self.index("ThreadType")
        if t < 0 or t >= len(THREAD_TYPES):
            raise FeatureError("Thread type is invalid")
        diameter = self.v["ThreadDiameter"]
        if diameter == 0.0:
            diameter = self.v["Diameter"]
        old = self.e["ThreadSize"].index
        options = T.THREADS[THREAD_TYPES[t]]
        target = options[old][2] if 0 <= old < len(options) else 0.0
        best = 0
        if target == 0.0:
            bd = math.inf
            for i, o in enumerate(options):
                dd = abs(o[1] - diameter)
                if dd < bd:
                    bd, best = dd, i
        else:
            bm = math.inf
            for i, o in enumerate(options):
                m = math.hypot(o[1] - diameter, o[2] - target)
                if m < bm:
                    bm, best = m, i
        self.set("ThreadSize", best)

    # ── Hole::onChanged ──
    def on_changed(self, p):
        if p == "StartType":
            has_offset = self["StartType"] != "Profile plane"
            self.read_only("StartOffset", not has_offset)
        elif p == "ThreadType":
            kind = ""
            if self.e["ThreadType"].valid():
                kind = self["ThreadType"]
                self.set_enums("ThreadSize", designations(self.index("ThreadType")))
                if kind != "None":
                    self.find_closest_designation()
            lists = {"None": ("ThreadClass_None_Enums", "HoleCutType_None_Enums", "ClearanceNoneEnums"),
                     "ISOMetricProfile": ("ThreadClass_ISOmetric_Enums", None, "ClearanceMetricEnums"),
                     "ISOMetricFineProfile": ("ThreadClass_ISOmetricfine_Enums", None, "ClearanceMetricEnums"),
                     "UNC": ("ThreadClass_UNC_Enums", "HoleCutType_UNC_Enums", "ClearanceUTSEnums"),
                     "UNF": ("ThreadClass_UNF_Enums", "HoleCutType_UNF_Enums", "ClearanceUTSEnums"),
                     "UNEF": ("ThreadClass_UNEF_Enums", "HoleCutType_UNEF_Enums", "ClearanceUTSEnums"),
                     "BSP": ("ThreadClass_None_Enums", "HoleCutType_BSP_Enums", "ClearanceMetricEnums"),
                     "NPT": ("ThreadClass_None_Enums", "HoleCutType_NPT_Enums", "ClearanceUTSEnums"),
                     "BSW": ("ThreadClass_BSW_Enums", "HoleCutType_BSW_Enums", "ClearanceOtherEnums"),
                     "BSF": ("ThreadClass_BSF_Enums", "HoleCutType_BSF_Enums", "ClearanceOtherEnums"),
                     "ISOTyre": ("ThreadClass_None_Enums", "HoleCutType_None_Enums", None)}.get(kind)
            if lists:
                cls, cut, fit = lists
                self.set_enums("ThreadClass", E[cls])
                cuts = _ISO_CUT_TYPES if kind == "ISOMetricProfile" else _ISOFINE_CUT_TYPES \
                    if kind == "ISOMetricFineProfile" else E[cut]
                self.set_enums("HoleCutType", cuts)
                if kind == "None":
                    self.set("Threaded", False)
                    self.set("ModelThread", False)
                    self.set("UseCustomThreadClearance", False)
                if fit:
                    self.set_enums("ThreadFit", E[fit])
            none, threaded = kind == "None", self.v["Threaded"]
            self.read_only("Diameter", not none)
            self.read_only("Threaded", none)
            self.read_only("ThreadSize", none)
            self.read_only("ThreadFit", none or threaded)
            self.read_only("ThreadClass", none or not threaded)
            self.read_only("ThreadDepthType", none or not threaded)
            self.read_only("ThreadDepth", none or not threaded)
            self.read_only("ModelThread", none or not threaded)
            self.read_only("UseCustomThreadClearance", none or not threaded or not self.v["ModelThread"])
            self.read_only("CustomThreadClearance", not self.v["UseCustomThreadClearance"]
                           or "UseCustomThreadClearance" in self.ro)
            # FeatureHole.cpp declares holeCutTypeStr again inside its `if`, so the one tested here is always empty
            # and every thread type takes the last branch ("screw definition").
            self.read_only("HoleCutCustomValues", False)
            if self.v["HoleCutCustomValues"]:
                self.read_only("HoleCutDiameter", False)
                self.read_only("HoleCutDepth", False)
                self.update_hole_cut_params()
            else:
                self.read_only("HoleCutDiameter", True)
                self.read_only("HoleCutDepth", True)
                self.read_only("HoleCutCountersinkAngle", True)
            if kind != "None":
                self.update_diameter_param()
        elif p == "Threaded":
            kind = self["ThreadType"]
            if self.v["Threaded"]:
                for q in ("CosmeticThread", "ThreadClass", "ThreadDirection", "ModelThread", "UseCustomThreadClearance",
                          "ThreadDepthType"):
                    self.read_only(q, False)
                self.read_only("ThreadFit", True)
                self.read_only("CustomThreadClearance", not self.v["UseCustomThreadClearance"])
                self.read_only("ThreadDepth", self["ThreadDepthType"] != "Dimension")
                if self.v["Tapered"] and self.v["TaperedAngle"] == 90:
                    self.set("TaperedAngle", 90 - 1.79)          # getThreadProfileAngle
            else:
                self.set("CosmeticThread", False)
                for q in ("CosmeticThread", "ThreadClass", "ThreadDirection", "ModelThread", "UseCustomThreadClearance",
                          "CustomThreadClearance", "ThreadDepthType", "ThreadDepth"):
                    self.read_only(q, True)
                self.read_only("ThreadFit", kind == "None")
            self.update_diameter_param()
        elif p == "ModelThread":
            self.update_diameter_param()
            self.read_only("UseCustomThreadClearance", not self.v["ModelThread"])
            if self.v["CosmeticThread"] and self.v["ModelThread"]:
                self.set("CosmeticThread", False)
        elif p == "CosmeticThread":
            if self.v["CosmeticThread"] and self.v["ModelThread"]:
                self.set("ModelThread", False)
        elif p == "DrillPoint":
            angled = self.index("DrillPoint") == 1
            self.read_only("DrillPointAngle", not angled)
            self.read_only("DrillForDepth", not angled)
        elif p == "Tapered":
            if self.v["Tapered"]:
                self.read_only("TaperedAngle", False)
                if self.v["Threaded"] and self.v["TaperedAngle"] == 90:
                    self.set("TaperedAngle", 90 - 1.79)
            else:
                self.set("TaperedAngle", 90)
                self.read_only("TaperedAngle", True)
        elif p == "ThreadSize":
            self.update_diameter_param()
            self.update_thread_depth_param()
        elif p == "ThreadFit":
            self.update_diameter_param()
        elif p == "Diameter":
            self.update_hole_cut_params()
            if self.index("ThreadType") == 0:
                self.set("ThreadDiameter", self.v["Diameter"])
        elif p == "HoleCutType":
            self.update_hole_cut_params()
        elif p == "HoleCutCustomValues":
            self.update_hole_cut_params()
        elif p in ("HoleCutDiameter", "HoleCutCountersinkAngle"):
            cut, ttype = self["HoleCutType"], self["ThreadType"]
            if not (cut == "Countersink" or self.is_dynamic_countersink(ttype, cut)):
                return
            angle = math.radians(self.v["HoleCutCountersinkAngle"])
            if angle <= 0.0 or angle >= math.pi:
                self.set("HoleCutDepth", 2.0)
            else:
                th = math.tan(angle / 2.0)
                if abs(th) < 1e-6:
                    self.set("HoleCutDepth", 2.0)
                else:
                    self.set("HoleCutDepth", (self.v["HoleCutDiameter"] / 2.0) / th)
        elif p == "DepthType":
            not_dim = self["DepthType"] != "Dimension"
            for q in ("Depth", "DrillPoint", "DrillPointAngle", "DrillForDepth"):
                self.read_only(q, not_dim)
            if not_dim:
                length = self.length_through_all()
                if length is not None:
                    self.set("Depth", length)
            self.update_thread_depth_param()
        elif p == "Depth":
            length = self.length_through_all()
            if length is not None and self.v["Depth"] > length:
                self.set("Depth", length)
            if self["ThreadDepthType"] != "Dimension":
                self.update_diameter_param()
            self.update_thread_depth_param()
        elif p == "ThreadDepthType":
            self.update_thread_depth_param()
            self.read_only("ThreadDepth", self.v["Threaded"] and self["ThreadDepthType"] != "Dimension")
        elif p == "ThreadDepth":
            if self.v["ThreadDepth"] > self.v["Depth"]:
                self.set("ThreadDepth", self.v["Depth"])
        elif p in ("UseCustomThreadClearance",):
            self.update_diameter_param()
            self.read_only("CustomThreadClearance", not self.v["UseCustomThreadClearance"])
        elif p == "CustomThreadClearance":
            self.update_diameter_param()

    # ── what the part file and the UI read ──
    def values(self) -> dict:
        out = {}
        for p in ORDER + ["ThreadDiameter"]:
            out[SNAKE[p]] = self[p]
        return out


def resolve(given: dict, through_all=None) -> HoleState:
    """A new Hole with the given properties (snake_case) set in ORDER, each from Python as to_freecad sets it."""
    st = HoleState(through_all)
    for p in ORDER:
        k = SNAKE[p]
        if k in given and given[k] is not None:
            st.assign(p, given[k])
    return st


# ── the feature ──────────────────────────────────────────────────────────────────────────────────────────

EDIT_KEYS = [SNAKE[p] for p in ORDER]


class Hole:
    """PartDesign::Hole. The keywords are the properties chosen; every property's value (what FreeCAD's would hold) is
    an attribute of the same name. A value given as a PARAMS name or expression is resolved when the body is built."""
    kind = "Hole"
    additive = False
    EDIT_PROPS = {k: k for k in EDIT_KEYS}
    EDIT_EXTRA: set = set()
    EDIT_DERIVED = ("thread_diameter", "read_only", "enums", "through_all_unknown", "minimal")
    REF_KEYS: tuple = ()

    def __init__(self, name: str, profile: str, **props):
        self.name, self.profile = name, profile
        unknown = set(props) - set(EDIT_KEYS)
        if unknown:
            raise FeatureError(f"{name}: {', '.join(sorted(unknown))} is not a property of a Hole")
        if props.get("start_type", "Profile plane") not in START_TYPES:
            raise FeatureError(f"{name}: start_type {props['start_type']!r} is not supported, only "
                               f"{', '.join(START_TYPES)}")
        self.given = {k: v for k, v in props.items() if v is not None}
        state = resolve({k: (0.0 if isinstance(v, str) and k not in _TEXT else v) for k, v in self.given.items()})
        self._state = state
        for k, v in state.values().items():
            setattr(self, k, self.given.get(k, v) if isinstance(self.given.get(k), str) and k not in _TEXT else v)

    def __repr__(self):
        return f"Hole({self.name!r}, {self.profile!r}, {', '.join(f'{k}={v!r}' for k, v in self.given.items())})"

    # feature_edit
    def edit_extra(self):
        return _extra(self._state)

    @staticmethod
    def resolved(feature: dict, through_all=None) -> dict:
        """feature_edit.resolve_feature: the chosen properties of a task panel, every property as FreeCAD's would then
        be, what is read-only, each enumeration's list, and the choices the part file would keep."""
        given = {k: feature[k] for k in EDIT_KEYS if feature.get(k) is not None}
        st = resolve({k: v for k, v in given.items() if not (isinstance(v, str) and k not in _TEXT)}, through_all)
        return {**st.values(), **_extra(st), "minimal": Hole.minimal(given)}

    @staticmethod
    def minimal(given: dict) -> dict:
        """The given properties less those whose value the others give anyway: what the part file needs to say."""
        given = {k: v for k, v in given.items() if k in EDIT_KEYS and v is not None}
        if any(isinstance(v, str) and k not in _TEXT for k, v in given.items()):
            exprs = {k: v for k, v in given.items() if isinstance(v, str) and k not in _TEXT}
            rest = Hole.minimal({k: v for k, v in given.items() if k not in exprs})
            return {**rest, **exprs}
        try:
            want = resolve(given).values()
        except FeatureError:
            return given
        keep, changed = dict(given), True
        while changed:                  # one left out can make another redundant (Threaded=False clears CosmeticThread)
            changed = False
            for p in reversed(ORDER):
                k = SNAKE[p]
                if k not in keep:
                    continue
                trial = {a: b for a, b in keep.items() if a != k}
                try:
                    if resolve(trial).values() == want:
                        keep, changed = trial, True
                except FeatureError:
                    pass
        return keep

    def build(self, sketches, base, shapes, params):
        if self.profile not in sketches:
            raise FeatureError(f"{self.name}: no sketch {self.profile!r} before it" if self.profile not in shapes
                               else f"{self.name}: profile {self.profile!r} is not a sketch")
        return _hole(self, sketches[self.profile], base, params)

    def to_freecad(self, body, made, planes, setv, ref):
        """The same Hole in a FreeCAD Body: made by PartDesign_Hole's way (newObject in the Body, Profile, a recompute
        so the base and through-all length are there), then the chosen properties set in ORDER."""
        obj = body.newObject("PartDesign::Hole", self.name)
        obj.Profile = made[self.profile]
        body.Document.recompute()
        for p in ORDER:
            k = SNAKE[p]
            if k not in self.given:
                continue
            v = self.given[k]
            if isinstance(v, str) and k not in _TEXT:
                setv(obj, p, v)
            else:
                setattr(obj, p, v)
        return obj


_TEXT = {SNAKE[p] for p in ENUM_PROPS}


# ── Hole::execute ────────────────────────────────────────────────────────────────────────────────────────

def _pnt(v):
    return gp_Pnt(v.X(), v.Y(), v.Z())


def _intersection(pa1, pa2, pb1, pb2):
    """computeIntersection: where the lines (pa1, pa2) and (pb1, pb2) cross, in x and y."""
    vx1, vy1 = pa1[0] - pa2[0], pa1[1] - pa2[1]
    vx2, vy2 = pb1[0] - pb2[0], pb1[1] - pb2[1]
    x1, y1, x2, y2 = pa1[0], pa1[1], pb1[0], pb1[1]
    f = 1 / ((vx1 * -vy2) - (-vx2 * vy1))
    t1 = -vy2 * f * (x2 - x1) + vx2 * f * (y2 - y1)
    return x1 + t1 * vx1, y1 + t1 * vy1


def _perpendicular(z):
    """Hole::computePerpendicular."""
    if abs(z.Z() - z.X()) > CONFUSION:
        x = gp_Vec(z.Z(), 0, -z.X())
    elif abs(z.Z() - z.Y()) > CONFUSION:
        x = gp_Vec(z.Y(), -z.X(), 0)
    else:
        x = gp_Vec(0, -z.Z(), z.Y())
    x.Normalize()
    return x


def _through_all(base, sketch):
    """ProfileBased::getThroughAllLength: 2.02 x the diagonal of the base and the profile's face (when its edges make
    one; getTopoShapeVerifiedFace(true) is silent when they do not)."""
    try:
        face = F.profile_face(sketch)
    except FeatureError:
        face = None
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    box = Bnd_Box()
    BRepBndLib.Add_s(base, box)
    if face is not None:
        BRepBndLib.Add_s(face, box)
    box.SetGap(0.0)
    return 2.02 * math.sqrt(box.SquareExtent())


def _profile_points(sketch, base_profile_type):
    """Hole::findHoles: the centre of each circle and arc (OnCircles 2, OnArcs 4) in the sketch's edge order, then each
    point (OnPoints 1), in the body's frame."""
    out = []
    from . import feature_revolve as R
    if base_profile_type & 2 or base_profile_type & 4:
        for e in R._sketch_edges(sketch):
            a = BRepAdaptor_Curve(TopoDS.Edge(e))
            if a.GetType() != GeomAbs_Circle:
                continue
            closed = a.IsClosed()
            if not base_profile_type & 2 and closed:
                continue
            if not base_profile_type & 4 and not closed:
                continue
            out.append(a.Circle().Axis().Location())
    if base_profile_type & 1:
        origin, rot = sketch.placement()
        for g in sketch.geometry:
            if isinstance(g, F.Point) and not g.construction:
                p = F._matvec(rot, (g.point[0], g.point[1], 0.0))
                out.append(gp_Pnt(origin[0] + p[0], origin[1] + p[1], origin[2] + p[2]))
    return out


def _hole(feat: Hole, sketch, base, params):
    if base is None:
        raise FeatureError("The requested feature cannot be created. The reason may be that:\n"
                           "  - the active Body does not contain a base shape, so there is no\n"
                           "  material to be removed;\n"
                           "  - the selected sketch does not belong to the active Body.")
    through_all = _through_all(base, sketch)
    given = {k: (value(v, params, f"{feat.name}.{k}") if isinstance(v, str) and k not in _TEXT else v)
             for k, v in feat.given.items()}
    st = resolve(given, through_all)
    if st.v["Diameter"] < DIAMETER_MIN:
        raise FeatureError("Hole error: Diameter too small")
    method = st["DepthType"]
    normal = gp_Vec(*sketch.normal())
    if st.v["Reversed"]:
        normal = normal.Reversed()
    z = normal
    x = _perpendicular(z)
    hole_dir = gp_Dir(z).Reversed()
    start = st.v["StartOffset"] if st["StartType"] == "Offset" else 0.0
    if method == "Dimension":
        length = st.v["Depth"]
    elif method == "ThroughAll":
        length = through_all
    else:
        raise FeatureError("Hole error: Unsupported length specification")
    if length <= 0.0:
        raise FeatureError("Hole error: Invalid hole depth")
    cut, ttype = st["HoleCutType"], st["ThreadType"]
    is_sink = cut == "Countersink" or st.is_dynamic_countersink(ttype, cut)
    is_bore = cut == "Counterbore" or st.is_dynamic_counterbore(ttype, cut)
    is_drill = cut == "Counterdrill"
    tapered = math.radians(st.v["TaperedAngle"]) if st.v["Tapered"] else math.radians(90.0)
    radius_bottom = st.v["Diameter"] / 2.0 - length / math.tan(tapered)
    radius = st.v["Diameter"] / 2.0
    if tapered <= 0.0 or tapered > math.radians(180.0):
        raise FeatureError("Hole error: Invalid taper angle")
    mk = BRepBuilderAPI_MakeWire()
    first = last = gp_Pnt(0, 0, 0)

    def to(v):
        nonlocal last
        p = _pnt(v)
        mk.Add(BRepBuilderAPI_MakeEdge(last, p).Edge())
        last = p

    length_counter = 0.0
    if is_sink or is_bore or is_drill:
        cut_r, cut_depth = st.v["HoleCutDiameter"] / 2.0, st.v["HoleCutDepth"]
        sink = math.radians(st.v["HoleCutCountersinkAngle"] / 2.0)
        if is_bore:
            sink = math.radians(90.0)
        if is_sink:
            cut_depth = 0.0
        if cut_r < radius:
            raise FeatureError("Hole error: Hole cut diameter too small")
        if cut_depth > length:
            raise FeatureError("Hole error: Hole cut depth must be less than hole depth")
        if cut_depth < 0.0:
            raise FeatureError("Hole error: Hole cut depth must be greater or equal to zero")
        to(x * cut_r)
        if cut_depth > 0.0:
            to(x * cut_r - z * cut_depth)
        xc, zc = _intersection((cut_r, -cut_depth), (cut_r - math.sin(sink), -math.cos(sink) - cut_depth),
                               (radius, 0), (radius_bottom, -length))
        if -length > zc:
            raise FeatureError("Hole error: Invalid countersink")
        length_counter = zc
        to(x * xc + z * zc)
    else:
        to(x * radius)
    drill = st["DrillPoint"]
    if drill == "Flat":
        to(x * radius_bottom + z * -length)
        to(z * -length)
    else:
        dpa = math.radians((180.0 - st.v["DrillPointAngle"]) / 2.0)
        if dpa <= 0.0 or dpa >= math.radians(180.0):
            raise FeatureError("Hole error: Invalid drill point angle")
        if st.v["DrillForDepth"]:
            xd, zd = _intersection((0, -length), (radius, radius * math.tan(dpa) - length), (radius, 0),
                                   (radius_bottom, -length))
            if zd > 0 or zd >= length_counter:
                raise FeatureError("Hole error: Invalid drill point")
            to(x * xd + z * zd)
            to(z * -length)
        else:
            to(x * radius_bottom + z * -length)
            to(z * (-length - radius * math.tan(dpa)))
    mk.Add(BRepBuilderAPI_MakeEdge(last, first).Edge())
    face = BRepBuilderAPI_MakeFace(mk.Wire()).Face()
    revol = BRepPrimAPI_MakeRevol(face, gp_Ax1(first, gp_Dir(z)), math.radians(360.0))
    if not revol.IsDone():
        raise FeatureError("Hole error: Could not revolve sketch")
    proto = revol.Shape()
    if proto.IsNull():
        raise FeatureError("Hole error: Resulting shape is empty")
    if st.v["Threaded"] and st.v["ModelThread"]:
        thread = _make_thread(st, x, z, length)
        comp = TopoDS_Compound()
        b = BRep_Builder()
        b.MakeCompound(comp)
        b.Add(comp, proto)
        b.Add(comp, thread)
        proto = comp
    holes = []
    move = gp_Vec(hole_dir).Multiplied(start) if abs(start) >= CONFUSION else gp_Vec(0, 0, 0)
    for loc in _profile_points(sketch, st.v["BaseProfileType"]):
        t = gp_Trsf()
        t.SetTranslation(gp_Pnt(0, 0, 0), gp_Pnt(loc.X() + move.X(), loc.Y() + move.Y(), loc.Z() + move.Z()))
        holes.append(proto.Moved(TopLoc_Location(t)))
    if not holes:
        raise FeatureError("Hole error: Finding axis failed")
    comp = TopoDS_Compound()
    b = BRep_Builder()
    b.MakeCompound(comp)
    for h in holes:
        b.Add(comp, h)
    try:
        # TopoShape::makeElementBoolean expands a compound tool of a cut into what it holds (expandCompound), so a
        # threaded hole's two solids, the drill and the thread, are two tools
        result = F._bool("cut", base, _expand(comp))
        if not F._count(result, TopAbs_SOLID):
            raise FeatureError("Resulting shape is not a solid")
    except Exception:                        # one at a time, as FreeCAD retries
        result = base
        for i, h in enumerate(holes, 1):
            try:
                result = F._bool("cut", result, _expand(h))
            except Exception:
                raise FeatureError(f"Boolean operation failed on profile Edge{i}") from None
            if not F._count(result, TopAbs_SOLID):
                raise FeatureError(f"Boolean operation produced non-solid on profile Edge{i}")
    if st.v["Refine"]:
        result = F._refine(result)
    return result


def _expand(shape):
    """TopoShape::expandCompound: a compound's shapes, compounds within it opened too."""
    from OCP.TopAbs import TopAbs_COMPOUND
    from OCP.TopoDS import TopoDS_Iterator
    if shape.ShapeType() != TopAbs_COMPOUND:
        return [shape]
    out = []
    it = TopoDS_Iterator(shape)
    while it.More():
        out += _expand(it.Value())
        it.Next()
    return out


# ── Hole::makeThread ─────────────────────────────────────────────────────────────────────────────────────

def _long_helix(pitch, height, radius, angle, left):
    """TopoShape::makeLongHelix."""
    if pitch < CONFUSION:
        raise FeatureError("Pitch of helix too small")
    if height < CONFUSION:
        raise FeatureError("Height of helix too small")
    ax = gp_Ax2(gp_Pnt(0, 0, 0), gp.DZ_s())
    if abs(angle) < CONFUSION:
        if radius < CONFUSION:
            raise FeatureError("Radius of helix too small")
        surf, cyl = Geom_CylindricalSurface(gp_Ax3(ax), radius), True
    else:
        angle = math.radians(angle)
        surf, cyl = Geom_ConicalSurface(gp_Ax3(ax), angle, radius), False
    turns = height / pitch
    whole = math.floor(turns)
    part = turns - whole
    d = gp_Dir2d(-2. * math.pi, pitch) if left else gp_Dir2d(2. * math.pi, pitch)
    cone = -1.0 if left else 1.0
    line = Geom2d_Line(gp_Ax2d(gp_Pnt2d(0, 0), d))
    beg = line.Value(0)
    mk = BRepBuilderAPI_MakeWire()
    step = math.sqrt(4.0 * math.pi * math.pi + pitch * pitch)
    for i in range(whole):
        end = line.Value(step * (i + 1)) if cyl else gp_Pnt2d(cone * (i + 1) * 2.0 * math.pi,
                                                              ((i + 1) * pitch) / math.cos(angle))
        mk.Add(BRepBuilderAPI_MakeEdge(GCE2d_MakeSegment(beg, end).Value(), surf).Edge())
        beg = end
    if part > CONFUSION:
        end = line.Value(step * turns) if cyl else gp_Pnt2d(cone * turns * 2.0 * math.pi, height / math.cos(angle))
        mk.Add(BRepBuilderAPI_MakeEdge(GCE2d_MakeSegment(beg, end).Value(), surf).Edge())
    wire = mk.Wire()
    BRepLib.BuildCurves3d_s(wire)
    return wire


def _rotate_to_normal(helix_axis, normal, shape):
    """Hole::rotateToNormal."""
    if helix_axis.IsEqual(normal, ANGULAR):
        return shape
    angle = math.acos(max(-1.0, min(1.0, helix_axis.Dot(normal))))
    if helix_axis.IsOpposite(normal, ANGULAR):
        x, y, zz = helix_axis.X(), helix_axis.Y(), helix_axis.Z()
        if abs(x) <= abs(y) and abs(x) <= abs(zz):
            x = 1.0
        elif abs(y) <= abs(x) and abs(y) <= abs(zz):
            y = 1.0
        else:
            zz = 1.0
        rot = helix_axis.Crossed(gp_Dir(x, y, zz))
    else:
        rot = helix_axis.Crossed(normal)
    mov = shape.Location().Transformation()
    mov.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), rot), angle)
    return shape.Moved(TopLoc_Location(mov))


def _make_thread(st: HoleState, x, z, length):
    left = st.index("ThreadDirection") == 1
    name, dia, _, _ = st.thread()
    rmaj = dia / 2
    pitch = st.thread_pitch()
    clearance = (st.v["CustomThreadClearance"] if st.v["UseCustomThreadClearance"] else st.thread_class_clearance()) / 2
    rmajc = rmaj + clearance
    margin_z = 0.001
    mk = BRepBuilderAPI_MakeWire()
    kind = st["ThreadType"]

    def P(r, h):
        return _pnt(x * r + z * h)
    if kind in ("BSP", "BSW", "BSF"):
        H = 0.960491 * pitch
        crest_r = 0.137329 * pitch
        margin_x = math.tan(math.radians(62.5)) * margin_z
        p1 = P(rmajc - 5 * H / 6 + margin_x, margin_z)
        p4 = P(rmajc - 5 * H / 6 + margin_x, pitch - margin_z)
        p23 = rmajc - crest_r * 0.58284013094
        p2, p3 = P(p23, 3 * pitch / 8), P(p23, 5 * pitch / 8)
        crest = P(rmajc, pitch / 2)
        mk.Add(BRepBuilderAPI_MakeEdge(p1, p2).Edge())
        mk.Add(BRepBuilderAPI_MakeEdge(GC_MakeArcOfCircle(p2, crest, p3).Value()).Edge())
        mk.Add(BRepBuilderAPI_MakeEdge(p3, p4).Edge())
        mk.Add(BRepBuilderAPI_MakeEdge(p4, p1).Edge())
    else:
        H = math.sqrt(3) / 2 * pitch
        h = 7 * H / 8
        margin_x = math.tan(math.radians(60.0)) * margin_z
        p1 = P(rmajc - h + margin_x, margin_z)
        p2, p3 = P(rmajc, 7 * pitch / 16), P(rmajc, 9 * pitch / 16)
        p4 = P(rmajc - h + margin_x, pitch - margin_z)
        mk.Add(BRepBuilderAPI_MakeEdge(p1, p2).Edge())
        if kind == "ISOTyre":
            crest = P(rmajc + pitch / 32, pitch / 2)
            mk.Add(BRepBuilderAPI_MakeEdge(GC_MakeArcOfCircle(p2, crest, p3).Value()).Edge())
        else:
            mk.Add(BRepBuilderAPI_MakeEdge(p2, p3).Edge())
        mk.Add(BRepBuilderAPI_MakeEdge(p3, p4).Edge())
        mk.Add(BRepBuilderAPI_MakeEdge(p4, p1).Edge())
    mk.Build()
    profile = mk.Wire()
    thread_depth = st.v["ThreadDepth"]
    helix_len = thread_depth + pitch / 2
    hole_depth = st.v["Depth"]
    tmethod, dmethod = st["ThreadDepthType"], st["DepthType"]
    if tmethod != "Dimension":
        if dmethod == "ThroughAll":
            thread_depth = length
            st.set("ThreadDepth", thread_depth)
            helix_len = thread_depth + 2 * pitch
        elif tmethod == "Tapped (DIN76)":
            thread_depth = hole_depth - st.thread_runout()
            st.set("ThreadDepth", thread_depth)
            helix_len = thread_depth + pitch / 2
        else:
            thread_depth = hole_depth
            st.set("ThreadDepth", thread_depth)
            helix_len = thread_depth + pitch / 8
    elif dmethod == "Dimension" and thread_depth > hole_depth - pitch / 2:
        helix_len = hole_depth + pitch / 8
    helix_angle = st.v["TaperedAngle"] - 90 if st.v["Tapered"] else 0.0
    helix = _long_helix(pitch, helix_len, rmaj, helix_angle, left)
    mov = gp_Trsf()
    mov.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0)), math.pi)
    helix = helix.Moved(TopLoc_Location(mov))
    helix = _rotate_to_normal(gp_Dir(0, 0, 1), gp_Dir(z), helix)
    ps = BRepOffsetAPI_MakePipeShell(TopoDS.Wire(helix))
    ps.SetTolerance(CONFUSION)
    ps.SetTransitionMode(BRepBuilderAPI_Transformed)
    ps.SetMode(True)
    ps.Add(profile)
    if not ps.IsReady():
        raise FeatureError("Error: Thread could not be built")
    ps.Build()
    shell = ps.Shape()
    sim = TopTools_ListOfShape()
    ps.Simulate(2, sim)
    front = _cheese_face(TopoDS.Wire(sim.First()))
    back = _cheese_face(TopoDS.Wire(sim.Last()))
    sewer = BRepBuilderAPI_Sewing()
    sewer.SetTolerance(CONFUSION)
    sewer.Add(front)
    sewer.Add(back)
    sewer.Add(shell)
    sewer.Perform()
    ms = BRepBuilderAPI_MakeSolid()
    ms.Add(TopoDS.Shell(sewer.SewedShape()))
    if not ms.IsDone():
        raise FeatureError("Error: Result is not a solid")
    result = ms.Shape()
    sc = BRepClass3d_SolidClassifier(result)
    sc.PerformInfinitePoint(CONFUSION)
    if sc.State() == TopAbs_IN:
        result.Reverse()
    return result


def _cheese_face(wire):
    """FaceMakerCheese::makeFace for one wire: BRepBuilderAPI_MakeFace, then validateFace."""
    face = BRepBuilderAPI_MakeFace(wire).Face()
    if BRepCheck_Analyzer(face).IsValid():
        return face
    from OCP.ShapeFix import ShapeFix_Shape
    fx = ShapeFix_Shape(face)
    fx.SetPrecision(CONFUSION)
    fx.SetMaxTolerance(CONFUSION)
    fx.Perform()
    return fx.Shape()


__all__ = ["Hole", "HoleState", "resolve", "ORDER", "SNAKE"]

def _extra(st: HoleState) -> dict:
    """What read() reports of a Hole beyond its keywords: ThreadDiameter, the read-only properties, the enumerations."""
    return {"thread_diameter": st["ThreadDiameter"], "read_only": sorted(SNAKE.get(p, snake(p)) for p in st.ro),
            "enums": {SNAKE[p]: list(st.e[p].items) for p in ENUM_PROPS}, "through_all_unknown": st.unknown}


# Last, so that importing this module first works: feature.py imports it back at its end, and finds it complete.
from . import feature as F  # noqa: E402
from .feature import FeatureError, value  # noqa: E402

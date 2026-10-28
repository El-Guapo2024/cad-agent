# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses what FreeCAD's TechDraw extension commands do and keeps FreeCAD's licence, the GNU
# Lesser General Public License, version 2.1 or (at your option) any later version; the text is in ../ui/LICENSE.
#
#   Derived from: src/Mod/TechDraw/Gui/CommandExtensionPack.cpp (Copyright (c) 2021 edi),
#                 src/Mod/TechDraw/Gui/CommandExtensionDims.cpp (Copyright (c) 2021 edi)
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
"""cad techdraw cosmetic-circle2|cosmetic-circle3|cosmetic-arc|cosmetic-parallel|cosmetic-perpendicular|extend-line|shorten-line|
circle-centerlines|bolt-circle|thread|line-attributes|lock-view|toggle-edges|position-section|chain-dim|coord-dim|chamfer-dim|
arc-length-dim|dim-position|dim-prefix|dim-remove-prefix|dim-decimals|area-note|arc-length-note: the extension commands as
techdraw_ext.py's ops (cad_agent/techdrawcmd.py hands them its `one`)."""
from __future__ import annotations

from .cmdbase import UsageError


def _attrs(sp):
    sp.add_argument("--line-style", type=int, metavar="N", help="Select Line Attributes: the line number (1 Visible ... 17 Chain; default 2)")
    sp.add_argument("--line-weight", type=float, metavar="MM", help="the line width in mm (default 0.5)")
    sp.add_argument("--line-color", metavar="R,G,B", help="the colour, 0 to 1 each")
    sp.add_argument("--cascade-spacing", type=float, metavar="MM", help="Select Line Attributes' Cascade spacing (default 7)")
    sp.add_argument("--delta-distance", type=float, metavar="MM", help="Select Line Attributes' Delta distance (default 2)")


def _session(a, op: dict) -> dict:
    active = {}
    if getattr(a, "line_style", None) is not None:
        active.update(style=a.line_style, line_number=a.line_style)
    if getattr(a, "line_weight", None) is not None:
        active["weight"] = a.line_weight
    if getattr(a, "line_color", None):
        try:
            c = [float(x) for x in a.line_color.split(",")]
        except ValueError:
            c = []
        if len(c) != 3:
            raise UsageError("--line-color is R,G,B")
        active["color"] = c + [1.0]
    if active:
        op["active"] = active
    if getattr(a, "cascade_spacing", None) is not None:
        op["cascade_spacing"] = a.cascade_spacing
    if getattr(a, "delta_distance", None) is not None:
        op["line_stretch"] = a.delta_distance
    return op


# command -> (help, op, which argument holds the selection, extra options)
VERTICES = {
    "cosmetic-circle2": ("TechDraw_ExtensionDrawCosmCircle: a circle about the first vertex through the second", "cosmetic_circle2"),
    "cosmetic-circle3": ("TechDraw_ExtensionDrawCosmCircle3Points: a circle through three vertices", "cosmetic_circle3"),
    "cosmetic-arc": ("TechDraw_ExtensionDrawCosmArc: an anticlockwise arc about the first vertex, from the second to the third",
                     "cosmetic_arc"),
}
EDGES = {
    "circle-centerlines": ("TechDraw_ExtensionCircleCenterLines: a cross on each circle or arc", "circle_centerlines"),
    "bolt-circle": ("TechDraw_ExtensionHoleCircle: the bolt circle through three or more circles and a line through each",
                    "bolt_circle"),
}
THREADS = {"thread-hole-side": "hole_side", "thread-bolt-side": "bolt_side", "thread-hole-bottom": "hole_bottom",
           "thread-bolt-bottom": "bolt_bottom"}
CHAINS = {"chain-dim": ("TechDraw_ExtensionCreate{Horiz,Vert,Oblique}ChainDimension: a chain of dimensions between the vertices", "chain_dim"),
          "coord-dim": ("TechDraw_ExtensionCreate{Horiz,Vert,Oblique}CoordDimension: dimensions from the first vertex to the others",
                        "coord_dim")}


def add(one, apply_ops, cmd) -> None:
    def run(a, op, *words):
        return apply_ops(a, a.page, [_session(a, op)], cmd(a, a.page, *words), None)

    for name, (help, kind) in VERTICES.items():
        sp = one(name, lambda a, kind=kind: run(a, {"op": kind, "view": a.view, "vertices": a.vertices}, a.view, *a.vertices), help)
        sp.add_argument("view")
        sp.add_argument("vertices", nargs="+", metavar="VertexN")
        _attrs(sp)
    for name, (help, kind) in EDGES.items():
        sp = one(name, lambda a, kind=kind: run(a, {"op": kind, "view": a.view, "edges": a.edges}, a.view, *a.edges), help)
        sp.add_argument("view")
        sp.add_argument("edges", nargs="+", metavar="EdgeN")
        _attrs(sp)
    for name in ("cosmetic-parallel", "cosmetic-perpendicular"):
        sp = one(name, lambda a, par=name.endswith("parallel"): run(
            a, {"op": "cosmetic_pline", "view": a.view, "subs": [a.edge, a.vertex], "parallel": par}, a.view, a.edge, a.vertex),
            "TechDraw_ExtensionLine" + ("Parallel" if name.endswith("parallel") else "Perpendicular") +
            ": a line through the vertex, parallel or at right angles to the edge")
        sp.add_argument("view")
        sp.add_argument("edge", metavar="EdgeN")
        sp.add_argument("vertex", metavar="VertexN")
        _attrs(sp)
    for name, ext in (("extend-line", True), ("shorten-line", False)):
        sp = one(name, lambda a, ext=ext: run(a, {"op": "extend_line", "view": a.view, "sub": a.edge, "extend": ext}, a.view, a.edge),
                 f"TechDraw_Extension{'Extend' if ext else 'Shorten'}Line: a cosmetic line or centre line "
                 f"{'longer' if ext else 'shorter'} by the delta distance (--delta-distance, default 2 mm)")
        sp.add_argument("view")
        sp.add_argument("edge", metavar="EdgeN")
        _attrs(sp)
    for name, kind in THREADS.items():
        sp = one(name, lambda a, kind=kind: run(a, {"op": "thread", "view": a.view, "kind": kind, "subs": a.subs}, a.view, *a.subs),
                 "TechDraw_Extension" + "".join(w.title() for w in name.split("-")) +
                 (": two lines a thread's width apart" if "side" in name else ": the three quarter arc of the thread on a circle"))
        sp.add_argument("view")
        sp.add_argument("subs", nargs="+", metavar="EdgeN")
        _attrs(sp)
    sp = one("line-attributes", lambda a: run(a, {"op": "line_attributes", "view": a.view, "subs": a.edges}, a.view, *a.edges),
             "TechDraw_ExtensionChangeLineAttributes: the cosmetic lines and centre lines take the --line-* attributes")
    sp.add_argument("view")
    sp.add_argument("edges", nargs="+", metavar="EdgeN")
    _attrs(sp)
    sp = one("lock-view", lambda a: run(a, {"op": "lock_view", "names": a.views}, *a.views),
             "TechDraw_ExtensionLockUnlockView: LockPosition of each view turned over")
    sp.add_argument("views", nargs="+", metavar="VIEW")
    sp = one("toggle-edges", lambda a: run(a, {"op": "show_all_edges", "view": a.view}, a.view),
             "TechDraw_ShowAll (Toggle Edge Visibility): the invisible lines of the view drawn or not")
    sp.add_argument("view")
    sp = one("position-section", lambda a: run(a, _position(a), a.section, *([a.edge, a.base, a.vertex] if a.edge else [])),
             "TechDraw_ExtensionPositionSectionView: a section view in line with its base view, or its EDGE in line with the "
             "base view's VERTEX")
    sp.add_argument("section")
    sp.add_argument("edge", nargs="?", metavar="EdgeN")
    sp.add_argument("base", nargs="?", metavar="BASE_VIEW")
    sp.add_argument("vertex", nargs="?", metavar="VertexM")
    for name, (help, kind) in CHAINS.items():
        sp = one(name, lambda a, kind=kind: run(a, {"op": kind, "view": a.view, "vertices": a.vertices, "dir": a.dir},
                                                a.view, *a.vertices, "--dir", a.dir), help)
        sp.add_argument("view")
        sp.add_argument("vertices", nargs="+", metavar="VertexN")
        sp.add_argument("--dir", choices=["h", "v", "o"], default="h", help="horizontal, vertical or oblique")
        _attrs(sp)
    sp = one("chamfer-dim", lambda a: run(a, {"op": "chamfer_dim", "view": a.view, "vertices": a.vertices, "dir": a.dir},
                                          a.view, *a.vertices, "--dir", a.dir),
             "TechDraw_ExtensionCreate{Horiz,Vert}ChamferDimension: the leg of a chamfer with its angle in the text")
    sp.add_argument("view")
    sp.add_argument("vertices", nargs=2, metavar="VertexN")
    sp.add_argument("--dir", choices=["h", "v"], default="h")
    sp = one("arc-length-dim", lambda a: run(a, {"op": "arc_length_dim", "view": a.view, "edge": a.edge}, a.view, a.edge),
             "TechDraw_ExtensionCreateLengthArc: a dimension showing the length of an arc")
    sp.add_argument("view")
    sp.add_argument("edge", metavar="EdgeN")
    sp = one("dim-position", lambda a: run(a, {"op": "dim_position", "names": a.dims, "dir": a.dir, "cascade": a.cascade,
                                               **({"cascade_spacing": a.spacing} if a.spacing is not None else {})},
                                           *a.dims, "--dir", a.dir, *(["--cascade"] if a.cascade else [])),
             "TechDraw_ExtensionPos{Horiz,Vert,Oblique}ChainDimension (line the dimensions up) and "
             "TechDraw_ExtensionCascade{...}Dimension (--cascade: one spacing further each)")
    sp.add_argument("dims", nargs="+", metavar="DIMENSION")
    sp.add_argument("--dir", choices=["h", "v", "o"], default="h")
    sp.add_argument("--cascade", action="store_true")
    sp.add_argument("--spacing", type=float, help="the cascade spacing (default 7 mm)")
    sp = one("dim-prefix", lambda a: run(a, _prefix(a), *a.dims, "--prefix", a.prefix),
             "TechDraw_ExtensionInsert{Diameter,Square,Repetition}: a prefix in front of the dimensions' FormatSpec")
    sp.add_argument("dims", nargs="+", metavar="DIMENSION")
    sp.add_argument("--prefix", required=True, help="'⌀', '□' or '%%s× ' (--text N asks for the count)")
    sp.add_argument("--text", help="the count of 'n×'")
    sp = one("dim-remove-prefix", lambda a: run(a, {"op": "dim_remove_prefix", "names": a.dims}, *a.dims),
             "TechDraw_ExtensionRemovePrefixChar")
    sp.add_argument("dims", nargs="+", metavar="DIMENSION")
    sp = one("dim-decimals", lambda a: run(a, {"op": "dim_decimals", "names": a.dims, "delta": a.delta}, *a.dims, "--delta", str(a.delta)),
             "TechDraw_ExtensionIncreaseDecimal / DecreaseDecimal: one more or one fewer decimal place")
    sp.add_argument("dims", nargs="+", metavar="DIMENSION")
    sp.add_argument("--delta", type=int, choices=[-1, 1], default=1)
    sp = one("area-note", lambda a: run(a, {"op": "area_annotation", "view": a.view, "faces": a.faces}, a.view, *a.faces),
             "TechDraw_ExtensionAreaAnnotation: a balloon with the area of the faces")
    sp.add_argument("view")
    sp.add_argument("faces", nargs="+", metavar="FaceN")
    sp = one("arc-length-note", lambda a: run(a, {"op": "arc_length_annotation", "view": a.view, "edges": a.edges}, a.view, *a.edges),
             "TechDraw_ExtensionArcLengthAnnotation: a balloon with the length of the edges")
    sp.add_argument("view")
    sp.add_argument("edges", nargs="+", metavar="EdgeN")


def _position(a) -> dict:
    op = {"op": "position_section", "section": a.section}
    if a.edge:
        if not (a.base and a.vertex):
            raise UsageError("position-section SECTION EDGE BASE_VIEW VERTEX: the edge needs the base view and its vertex")
        op.update(edge=a.edge, base=a.base, vertex=a.vertex)
    return op


def _prefix(a) -> dict:
    op = {"op": "dim_prefix", "names": a.dims, "prefix": a.prefix}
    if a.text is not None:
        op["text"] = a.text
    return op

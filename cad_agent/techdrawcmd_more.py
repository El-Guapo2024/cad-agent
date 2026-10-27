# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses what FreeCAD's TechDraw annotation commands do and keeps FreeCAD's licence, the GNU
# Lesser General Public License, version 2.1 or (at your option) any later version; the text is in ../ui/LICENSE.
#
#   Derived from: src/Mod/TechDraw/Gui/CommandAnnotate.cpp (Copyright (c) 2019 WandererFan),
#                 src/Mod/TechDraw/Gui/Command.cpp (Copyright (c) 2002 Jürgen Riegel, 2014 Luke Parry),
#                 src/Mod/TechDraw/Gui/CommandDecorate.cpp (Copyright (c) 2014 Luke Parry),
#                 src/Mod/TechDraw/Gui/CommandExtensionPack.cpp (Copyright (c) 2021 edi)
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
"""cad techdraw leader | rich-text | symbol | weld | surface | image | clip | clip-add | clip-remove: the commands of
techdraw_more.py's ops (cad_agent/techdrawcmd.py hands them its `one`)."""
from __future__ import annotations

from .cmdbase import UsageError


def _points(text: str) -> list:
    out = []
    for p in text.split(";"):
        try:
            v = [float(x) for x in p.split(",")]
        except ValueError:
            v = []
        if len(v) != 2:
            raise UsageError(f"--points is X,Y;X,Y;... in page mm (y up), got {text!r}")
        out.append(v)
    return out


def add(one, apply_ops, cmd) -> None:
    sp = one("leader", lambda a: _leader(a, apply_ops, cmd), "TechDraw_LeaderLine: a leader line on a view, through --points")
    sp.add_argument("view")
    sp.add_argument("--points", required=True, metavar="X,Y;X,Y", help="page mm from the lower left, y up; the first is the arrow's tip")
    sp.add_argument("--start", help="the start symbol: Filled arrow, Open arrow, Tick, Dot, Open circle, Fork, Filled triangle, None")
    sp.add_argument("--end", help="the end symbol (default None)")
    sp.add_argument("--width", type=float, help="the line width in mm")
    sp.add_argument("--style", choices=["NoLine", "Continuous", "Dash", "Dot", "DashDot", "DashDotDot"])
    sp = one("rich-text", lambda a: _rich(a, apply_ops, cmd), "TechDraw_RichTextAnnotation: a rich text block (HTML as Qt writes it)")
    sp.add_argument("text", metavar="HTML")
    sp.add_argument("--at", metavar="X,Y", help="page mm, y up")
    sp.add_argument("--parent", help="the view or leader line it belongs to")
    sp.add_argument("--max-width", dest="max_width", type=float)
    sp.add_argument("--frame", choices=["true", "false"])
    sp = one("symbol", lambda a: _symbol(a, apply_ops, cmd), "TechDraw_Symbol: an SVG symbol (a file of the shipped symbols or of the project)")
    sp.add_argument("file", help="misc/North.svg (FreeCAD's symbols) or a project file")
    sp.add_argument("--owner")
    sp.add_argument("--at", metavar="X,Y")
    sp = one("weld", lambda a: _weld(a, apply_ops, cmd), "TechDraw_WeldSymbol: a weld symbol on a leader line")
    sp.add_argument("leader")
    sp.add_argument("--arrow", metavar="SYMBOL", help="the arrow side's symbol: Welding/AWS/filletDown.svg")
    sp.add_argument("--arrow-text", nargs=3, metavar=("LEFT", "CENTER", "RIGHT"))
    sp.add_argument("--other", metavar="SYMBOL")
    sp.add_argument("--other-text", nargs=3, metavar=("LEFT", "CENTER", "RIGHT"))
    sp.add_argument("--tail", default="", help="the tail text")
    sp.add_argument("--all-around", action="store_true")
    sp.add_argument("--field-weld", action="store_true")
    sp.add_argument("--alternating", action="store_true")
    sp = one("surface", lambda a: _surface(a, apply_ops, cmd), "TechDraw_SurfaceFinishSymbols: a surface finish symbol")
    sp.add_argument("--owner", help="a view (View), a view's element (View.Edge3) or the page")
    sp.add_argument("--icon", type=int, default=0, choices=range(6), metavar="0-5",
                    help="any method, removal prohibited, removal required, and each with the circle")
    sp.add_argument("--asme", action="store_true", help="the ASME template (default ISO)")
    sp.add_argument("--method", default="")
    sp.add_argument("--ra", type=int, default=0, metavar="0-11", help="ISO: the index of Ra50 ... Ra0, 025")
    sp.add_argument("--lay", default="")
    sp.add_argument("--addition", default="")
    sp.add_argument("--sample-length", dest="sample_length", default="")
    sp.add_argument("--min-rough", dest="min_rough", default="")
    sp.add_argument("--max-rough", dest="max_rough", default="")
    sp.add_argument("--angle", type=float, default=0.0)
    sp = one("image", lambda a: _image(a, apply_ops, cmd), "TechDraw_Image: a bitmap of the project")
    sp.add_argument("file", help="a png, jpg or bmp file of the project")
    sp.add_argument("--owner")
    sp.add_argument("--at", metavar="X,Y")
    one("clip", lambda a: apply_ops(a, a.page, [{"op": "clip"}], cmd(a, a.page)), "TechDraw_ClipGroup: a clip group at the page's centre")
    sp = one("clip-add", lambda a: apply_ops(a, a.page, [{"op": "clip_add", "clip": a.clip, "view": a.view}], cmd(a, a.page, a.clip, a.view)),
             "TechDraw_ClipGroupAdd: a view into a clip group")
    sp.add_argument("clip")
    sp.add_argument("view")
    sp = one("clip-remove", lambda a: apply_ops(a, a.page, [{"op": "clip_remove", "view": a.view}], cmd(a, a.page, a.view)),
             "TechDraw_ClipGroupRemove: a view out of its clip group")
    sp.add_argument("view")


def _xy(text):
    try:
        v = [float(x) for x in text.split(",")]
    except ValueError:
        v = []
    if len(v) != 2:
        raise UsageError(f"{text!r} is X,Y")
    return v


def _leader(a, apply_ops, cmd):
    op = {"op": "leader", "view": a.view, "points": _points(a.points)}
    if a.start:
        op["start_symbol"] = a.start
    if a.end:
        op["end_symbol"] = a.end
    if a.width is not None:
        op["line_width"] = a.width
    if a.style:
        op["line_style"] = a.style
    return apply_ops(a, a.page, [op], cmd(a, a.page, a.view, "--points", a.points))


def _rich(a, apply_ops, cmd):
    op = {"op": "richanno", "text": a.text}
    if a.at:
        op["at"] = _xy(a.at)
    if a.parent:
        op["parent"] = a.parent
    if a.max_width is not None:
        op["max_width"] = a.max_width
    if a.frame:
        op["show_frame"] = a.frame == "true"
    return apply_ops(a, a.page, [op], cmd(a, a.page, a.text))


def _symbol(a, apply_ops, cmd):
    op = {"op": "symbol", "file": a.file}
    if a.owner:
        op["owner"] = a.owner
    if a.at:
        op["at"] = _xy(a.at)
    return apply_ops(a, a.page, [op], cmd(a, a.page, a.file))


def _side(symbol, texts):
    out = {}
    if symbol:
        out["symbol"] = symbol
    if texts:
        out.update(left=texts[0], center=texts[1], right=texts[2])
    return out


def _weld(a, apply_ops, cmd):
    op = {"op": "weld", "leader": a.leader, "arrow": _side(a.arrow, a.arrow_text), "other": _side(a.other, a.other_text),
          "tail_text": a.tail, "all_around": a.all_around, "field_weld": a.field_weld, "alternating": a.alternating}
    return apply_ops(a, a.page, [op], cmd(a, a.page, a.leader))


def _surface(a, apply_ops, cmd):
    op = {"op": "surface", "icon": a.icon, "iso": not a.asme, "method": a.method, "ra": a.ra, "lay": a.lay, "addition": a.addition,
          "sample_length": a.sample_length, "min_rough": a.min_rough, "max_rough": a.max_rough, "angle": a.angle}
    if a.owner:
        op["owner"] = a.owner
    return apply_ops(a, a.page, [op], cmd(a, a.page))


def _image(a, apply_ops, cmd):
    op = {"op": "image", "file": a.file}
    if a.owner:
        op["owner"] = a.owner
    if a.at:
        op["at"] = _xy(a.at)
    return apply_ops(a, a.page, [op], cmd(a, a.page, a.file))

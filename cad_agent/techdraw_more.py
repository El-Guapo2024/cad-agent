# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses what FreeCAD's TechDraw annotation commands do to a page and keeps FreeCAD's
# licence, the GNU Lesser General Public License, version 2.1 or (at your option) any later version; the text is in
# ../ui/LICENSE.
#
#   Derived from: src/Mod/TechDraw/Gui/CommandAnnotate.cpp (Copyright (c) 2019 WandererFan),
#                 src/Mod/TechDraw/Gui/Command.cpp (Copyright (c) 2002 Jürgen Riegel, 2014 Luke Parry),
#                 src/Mod/TechDraw/Gui/CommandDecorate.cpp (Copyright (c) 2014 Luke Parry),
#                 src/Mod/TechDraw/Gui/TaskLeaderLine.cpp, TaskRichAnno.cpp, TaskWeldingSymbol.cpp (Copyright (c) 2019 WandererFan),
#                 src/Mod/TechDraw/Gui/TaskSurfaceFinishSymbols.cpp (Copyright (c) 2021 Adrian Insaurralde),
#                 src/Mod/TechDraw/Gui/QGILeaderLine.cpp, QGIRichAnno.cpp, QGIWeldSymbol.cpp, QGITile.cpp, QGIArrow.cpp,
#                 QGIViewSymbol.cpp, QGIViewImage.cpp, QGIViewClip.cpp (Copyright (c) 2019 WandererFan, 2012 Luke Parry),
#                 src/Mod/TechDraw/App/DrawLeaderLine.cpp (Copyright (c) 2019 WandererFan),
#                 src/Mod/TechDraw/App/DrawViewClip.cpp (Copyright (c) 2002 Jürgen Riegel, 2013 Luke Parry)
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
"""The ops of leader lines, rich text, symbols, weld symbols, surface finish symbols, images and clip groups, and how the
page draws them.

    {"op": "leader", "view": v, "points": [[x, y], ...], "start_symbol"?, "end_symbol"?, "color"?, "line_width"?, "line_style"?}
        TechDraw_LeaderLine (TaskLeaderLine::createLeaderFeature): points are page mm, y up, the first the arrow's tip
    {"op": "leader_edit", "name": n, "start_symbol"?, "end_symbol"?, "color"?, "line_width"?, "line_style"?}   the same panel on a leader
    {"op": "richanno", "parent"?: v, "at"?: [x, y], "text"?: html, "max_width"?, "show_frame"?, "line_color"?, ...}
        TechDraw_RichTextAnnotation (TaskRichAnno): AnnoText is QTextDocument::toHtml's
    {"op": "richanno_edit", "name": n, "text"?, ...}                            the same panel on an annotation
    {"op": "symbol", "file"?: "Welding/AWS/filletUp.svg", "svg"?: text, "owner"?: v, "at"?: [x, y]}   TechDraw_Symbol
    {"op": "weld", "leader": n, "arrow"?: {"symbol", "left", "center", "right"}, "other"?: {...}, "all_around"?, "field_weld"?,
     "alternating"?, "tail_text"?}                                              TechDraw_WeldSymbol (TaskWeldingSymbol)
    {"op": "weld_edit", "name": weld, ...}                                      the same panel on a weld symbol
    {"op": "surface", "owner"?: "View" | "View.Edge3" | "Page", "icon"?: 0..5, "iso"?: bool, "method"?, "ra"?, "lay"?, ...}
        TechDraw_SurfaceFinishSymbols (TaskSurfaceFinishSymbols): a DrawViewSymbol "SurfaceSymbol"
    {"op": "image", "file": "refs/logo.png", "owner"?: v}                       TechDraw_Image
    {"op": "clip"} / {"op": "clip_add", "clip": c, "view": v} / {"op": "clip_remove", "view": v}   TechDraw_ClipGroup, ...Add, ...Remove

This module imports without OCP.
"""
from __future__ import annotations

import math
import struct
from pathlib import Path

from . import techdraw as T
from . import techdraw_objs as O

STEP_NAMES = {"leader": "Create Leader", "leader_edit": "Edit Leader", "richanno": "Create Annotation",
              "richanno_edit": "Edit Annotation", "symbol": "Create Symbol", "weld": "Create Weld Symbol",
              "weld_edit": "Edit Weld Symbol", "surface": "Surface Finish Symbols", "image": "Create Image",
              "clip": "Create clip", "clip_add": "Add clip group", "clip_remove": "Remove clip group"}
OPS = tuple(STEP_NAMES)
DEGREES_HALF_CIRCLE = 180.0
ARROW_MM = 3.5


def run(s, op: dict) -> str:
    from . import techdraw_edit as E
    return globals()["_" + op["op"]](s, E, op)


# ── geometry helpers (DrawUtil::invertY, Base::Vector3d::RotateZ) ─────────────────────────────────────────────

def invert_y(p):
    return (p[0], -p[1])


def rotate_z(p, rad):
    c, s = math.cos(rad), math.sin(rad)
    return (p[0] * c - p[1] * s, p[0] * s + p[1] * c)


def _view_state(s, o):
    """A view's place on the page (mm, y up), scale and rotation, as the page draws it."""
    if isinstance(o, (T.DrawViewPart, T.DrawProjGroup)):
        doc = T.PageDocument(s.objs, s.shape_of).recompute() if (
            isinstance(o, T.DrawProjGroupItem) and s.doc().group_of(o.name) is not None) else None
        if doc is not None:
            x, y = doc.pos.get(o.name, (o.x, o.y))
            return x, y, doc.view_scale(o), getattr(o, "rotation", 0.0)
        d = s.doc()
        return o.x, o.y, d.view_scale(o), getattr(o, "rotation", 0.0)
    return getattr(o, "x", 0.0), getattr(o, "y", 0.0), getattr(o, "scale", 1.0), getattr(o, "rotation", 0.0)


def _need_page(s, E):
    return s.page_obj()


# ── leaders (TaskLeaderLine) ──────────────────────────────────────────────────────────────────────────────

def _arrow_name(v, what):
    if isinstance(v, int) and not isinstance(v, bool):
        if 0 <= v < len(T.END_TYPES):
            return T.END_TYPES[v]
    if v in T.END_TYPES:
        return v
    raise ValueError(f"{what}: {v!r} is not an arrow ({', '.join(T.END_TYPES)})")


def _leader(s, E, op):
    base = s.get(op.get("view"), T.DrawViewPart, "view") if op.get("view") else None
    if base is None:
        # any DrawView will do as the parent (CmdTechDrawLeaderLine: DrawView), a part view in practice
        base = s.get(op.get("parent"), None, "view")
    page = _need_page(s, E)
    n = s.name("LeaderLine", op.get("name"))
    bx, by, scale, rot = _view_state(s, base)
    pts = [tuple(float(c) for c in p[:2]) for p in op.get("points") or ()]
    x = y = 0.0
    way = ((0.0, 0.0, 0.0),)
    if pts:
        # the attach point: the first pick in the parent's frame, unscaled and unrotated (onTrackerFinished, createLeaderFeature)
        ax, ay = (pts[0][0] - bx) / scale, -(pts[0][1] - by) / scale          # scene coordinates: y down
        if rot != 0:
            px, py = rotate_z(invert_y((ax, ay)), -math.radians(rot))
            ax, ay = invert_y((px, py))
        x, y = ax, -ay
        way = []
        for p in pts:
            dx, dy = p[0] - pts[0][0], -(p[1] - pts[0][1])                      # scenePointsToDeltas: unrotated
            if rot != 0:
                px, py = rotate_z(invert_y((dx, dy)), -math.radians(rot))
                dx, dy = invert_y((px, py))
            way.append((dx, dy, 0.0))
        way = tuple(way)
    kw = {k: op[k] for k in ("color", "line_width", "line_style", "scalable", "auto_horizontal", "rotates_with_parent") if k in op}
    for k in ("start_symbol", "end_symbol"):
        if k in op:
            kw[k] = _arrow_name(op[k], k)
    s.add(O.DrawLeaderLine(n, leader_parent=base.name, x=x, y=y, way_points=way, label=n, **kw))
    del page
    return f"made {n} on {base.name}"


def _leader_edit(s, E, op):
    o = s.get(op.get("name"), O.DrawLeaderLine, "leader line")
    d = T.as_dict(o)
    for k in ("start_symbol", "end_symbol"):
        if k in op:
            d[k] = _arrow_name(op[k], k)
    for k in ("color", "line_width", "line_style", "scalable", "auto_horizontal", "rotates_with_parent"):
        if k in op:
            d[k] = op[k]
    if op.get("points"):
        # QGEPath: the tip moved and the way points edited; the same maths as createLeaderFeature
        base = s.get(o.leader_parent, None, "view")
        bx, by, scale, rot = _view_state(s, base)
        pts = [tuple(float(c) for c in p[:2]) for p in op["points"]]
        ax, ay = (pts[0][0] - bx) / scale, -(pts[0][1] - by) / scale
        if rot != 0:
            px, py = rotate_z(invert_y((ax, ay)), -math.radians(rot))
            ax, ay = invert_y((px, py))
        d["x"], d["y"] = ax, -ay
        way = []
        for p in pts:
            dx, dy = p[0] - pts[0][0], -(p[1] - pts[0][1])
            if rot != 0:
                px, py = rotate_z(invert_y((dx, dy)), -math.radians(rot))
                dx, dy = invert_y((px, py))
            way.append([dx, dy, 0.0])
        d["way_points"] = way
    s.objs[s.objs.index(o)] = E._rebuilt(o, d)
    return f"edited {o.name}"


# ── rich text (TaskRichAnno) ──────────────────────────────────────────────────────────────────────────────

def _richanno(s, E, op):
    page = _need_page(s, E)
    n = s.name("RichTextAnnotation", op.get("name"))
    parent = s.get(op["parent"], None, "view") if op.get("parent") else None
    kw = {k: op[k] for k in ("show_frame", "max_width", "line_color", "line_width", "line_style") if k in op}
    if "text" in op:
        kw["anno_text"] = op["text"]
    width = kw.get("max_width", -1.0)
    if op.get("at") is not None:
        x, y = float(op["at"][0]), float(op["at"][1])      # the click: Rez::appX(scenePos.x()), -Rez::appX(scenePos.y())
    elif parent is not None:
        text_w = width if width > 0 else 100.0
        if isinstance(parent, O.DrawLeaderLine):
            way = parent.way_points
            end = way[-1]
            prev = way[-2] if len(way) > 1 else end
            x = end[0] - 5.0 - text_w / 2.0 if end[0] < prev[0] else end[0] + 5.0 + text_w / 2.0
            y = end[1] - 20.0 / 2.0
        else:
            bx = getattr(parent, "x", 0.0)
            by = getattr(parent, "y", 0.0)
            x, y = bx + text_w / 2.0 + 5.0, by + 20.0 / 2.0
    else:
        w, h = T.PageDocument(s.objs).page_size()
        x, y = w / 2.0, h / 2.0
    s.add(O.DrawRichAnno(n, anno_parent=parent.name if parent else None, x=x, y=y, label=n, **kw))
    del page
    return f"made {n}"


def _richanno_edit(s, E, op):
    o = s.get(op.get("name"), O.DrawRichAnno, "rich text annotation")
    d = T.as_dict(o)
    if "text" in op:
        d["anno_text"] = op["text"]
    for k in ("show_frame", "max_width", "line_color", "line_width", "line_style", "x", "y"):
        if k in op:
            d[k] = op[k]
    s.objs[s.objs.index(o)] = E._rebuilt(o, d)
    return f"edited {o.name}"


# ── symbols ───────────────────────────────────────────────────────────────────────────────────────────────

def _project_file(s, rel, what):
    """A file of the project (a bitmap for TechDraw_Image, an SVG for TechDraw_Symbol), by its path under the project."""
    if not isinstance(rel, str) or not rel or rel.startswith("/") or ".." in Path(rel).parts:
        raise ValueError(f"{what}: {rel!r} is not a file of the project")
    p = (s.pdir / rel)
    if not p.is_file():
        raise ValueError(f"{what}: the project has no file {rel!r}")
    return p


def _symbol(s, E, op):
    page = _need_page(s, E)
    n = s.name("Symbol", op.get("name"))
    if op.get("svg") is not None:
        svg = op["svg"]
    elif op.get("file"):
        f = op["file"]
        try:
            svg = O.symbol_path(f).read_text(encoding="utf-8")
        except T.TechDrawError:
            svg = _project_file(s, f, "file").read_text(encoding="utf-8")
    else:
        raise ValueError("a symbol needs a file (an SVG of the symbols or of the project) or its svg text")
    owner = s.get(op["owner"], None, "view") if op.get("owner") else None
    if op.get("at") is not None:
        x, y = float(op["at"][0]), float(op["at"][1])
    elif owner is not None:
        x, y = 0.0, 0.0                                     # DrawPage::addView leaves a view that has an owner where it is
    else:
        w, h = T.PageDocument(s.objs).page_size()
        x, y = w / 2.0, h / 2.0
    del page
    s.add(O.DrawViewSymbol(n, symbol=svg, owner=owner.name if owner else None, x=x, y=y, label=n))
    return f"made {n}"


# ── weld symbols (TaskWeldingSymbol) ──────────────────────────────────────────────────────────────────────

def _tile_kw(side: dict | None, dirty: bool):
    side = side or {}
    kw = {"left_text": side.get("left", ""), "right_text": side.get("right", ""), "center_text": side.get("center", "")}
    if side.get("symbol"):
        kw["symbol_file"] = side["symbol"]
    elif dirty:
        kw["symbol_file"] = ""                              # updateTiles: SymbolFile.setValue("") on the other side
    return kw


def _weld(s, E, op):
    lead = s.get(op.get("leader"), O.DrawLeaderLine, "leader line")
    _need_page(s, E)
    # the tiles are made with the symbol, before it in the document (DrawWeldSymbol::onSettingDocument)
    tile1 = s.name("TileWeld")
    tile2 = s.name("TileWeld001" if tile1 == "TileWeld" else "TileWeld")
    if tile2 == tile1:
        tile2 = s.name("TileWeld")
    wn = s.name("WeldSymbol", op.get("name"))
    s.add(O.DrawTileWeld(tile1, tile_parent=wn, label=tile1, **_tile_kw(op.get("arrow"), False)))
    s.add(O.DrawTileWeld(tile2, tile_parent=wn, tile_row=-1, label=tile2, **_tile_kw(op.get("other"), True)))
    kw = {k: op[k] for k in ("all_around", "field_weld", "tail_text", "font", "font_size", "tile_font_size") if k in op}
    if "alternating" in op:
        kw["alternating_weld"] = op["alternating"]
    s.add(O.DrawWeldSymbol(wn, leader=lead.name, label=wn, **kw))
    return f"made {wn} on {lead.name}"


def _weld_edit(s, E, op):
    w = s.get(op.get("name"), O.DrawWeldSymbol, "weld symbol")
    d = T.as_dict(w)
    for k in ("all_around", "field_weld", "tail_text", "font", "font_size", "tile_font_size"):
        if k in op:
            d[k] = op[k]
    if "alternating" in op:
        d["alternating_weld"] = op["alternating"]
    s.objs[s.objs.index(w)] = E._rebuilt(w, d)
    tiles = {t.tile_row: t for t in s.objs if isinstance(t, O.DrawTileWeld) and t.tile_parent == w.name}
    for side, row in (("arrow", 0), ("other", -1)):
        if side not in op or row not in tiles:
            continue
        t = tiles[row]
        td = T.as_dict(t)
        data = op[side]
        for key, prop in (("left", "left_text"), ("right", "right_text"), ("center", "center_text")):
            if key in data:
                td[prop] = data[key]
        if "symbol" in data:
            td["symbol_file"] = data["symbol"]
        s.objs[s.objs.index(t)] = E._rebuilt(t, td)
    if op.get("flip"):                                       # onFlipSidesClicked: the two tiles swap their texts and symbols
        a, b = tiles.get(0), tiles.get(-1)
        if a is not None and b is not None:
            ad, bd = T.as_dict(s.get(a.name)), T.as_dict(s.get(b.name))
            for k in ("left_text", "right_text", "center_text", "symbol_file"):
                ad[k], bd[k] = bd[k], ad[k]
            s.objs[s.objs.index(s.get(a.name))] = E._rebuilt(a, ad)
            s.objs[s.objs.index(s.get(b.name))] = E._rebuilt(b, bd)
    return f"edited {w.name}"


# ── surface finish symbols (TaskSurfaceFinishSymbols) ─────────────────────────────────────────────────────

RA_VALUES = ["Ra50", "Ra25", "Ra12, 5", "Ra6, 3", "Ra3, 2", "Ra1, 6", "Ra0, 8", "Ra0, 4", "Ra0, 2", "Ra0, 1", "Ra0, 05", "Ra0, 025"]
LAY_SYMBOLS = ["", "=", "⟂", "X", "M", "C", "R"]
ROUGH_GRADES = ["", "N1", "N2", "N3", "N4", "N5", "N6", "N7", "N8", "N9", "N10", "N11"]
# SymbolType: AnyMethod, RemoveProhibit, RemoveRequired, AnyMethodAll, RemoveProhibitAll, RemoveRequiredAll
ICONS = ("AnyMethod", "RemoveProhibit", "RemoveRequired", "AnyMethodAll", "RemoveProhibitAll", "RemoveRequiredAll")


def surface_svg(icon: int = 0, iso: bool = True, method: str = "", ra: str | int = 0, lay: str = "", addition: str = "",
                sample_length: str = "", min_rough: str = "", max_rough: str = "") -> str:
    """TaskSurfaceFinishSymbols::completeSymbol: the symbol as the SVG string the DrawViewSymbol holds."""
    out = ["<?xml version='1.0'?>\n<svg width='150' height='64'>\n"]

    def line(x0, y0, x1, y1):
        out.append(f"<path stroke='#000' stroke-width='1' d=' M{x0}, {y0} L{x1}, {y1}' />\n")

    def circle(cx, cy, r):
        out.append(f"<circle cx='{cx}' cy='{cy}' r='{r}' fill='none' stroke='#000' stroke-width='1'/>\n")

    def text(x, y, t):
        out.append(f"<text x='{x}' y='{y}' style='font-size:18px'>{t}</text>\n")
    line(0, 44, 12, 64)
    line(12, 64, 42, 14)
    move_left = 0
    if icon in (1, 4):
        circle(12, 46, 9)
    if icon in (2, 5):
        line(0, 44, 24, 44)
    if icon in (3, 4, 5):
        circle(42, 14, 6)
        move_left = 5
    text(42 + move_left, 11, method)
    n_method = len(method.encode("utf-8"))                   # std::string::length: bytes
    if iso:
        ra_text = RA_VALUES[ra] if isinstance(ra, int) else ra
        text(42 + move_left, 30, ra_text)
        max_len = int(max(n_method, len(ra_text.encode("utf-8"))) * 9.25 + move_left)
    else:
        text(42 + move_left, 30, sample_length)
        max_len = int(max(n_method, len(sample_length.encode("utf-8"))) * 9.25 + move_left)
        text(-10, 35, min_rough)
        text(-10, 20, max_rough)
    line(42, 14, 42 + max_len, 14)
    text(20, 60, lay)
    text(-25, 60, addition)
    out.append("</svg>\n")
    return "".join(out)


def _surface_owner(s, spec):
    """CmdTechDrawSurfaceFinishSymbols: the owner (a part view, a leader line or the page) and the sub-element named."""
    name, _, sub = (spec or "").partition(".")
    o = s.get(name, None, "view") if name else None
    return o, sub


def _surface(s, E, op):
    page = _need_page(s, E)
    owner, sub = _surface_owner(s, op.get("owner") or page.name)
    x = y = 0.0
    view = None
    if isinstance(owner, T.DrawPage):
        w, h = T.PageDocument(s.objs).page_size()
        x, y = w / 2.0, h / 2.0
    elif isinstance(owner, (T.DrawViewPart, O.DrawLeaderLine)):
        view = owner
        if sub and isinstance(owner, T.DrawViewPart):
            geo = E_geo(s, E, owner)
            i = int(sub.lstrip("EdgeVertxFac"))
            if sub.startswith("Vertex"):
                v = geo.vertices[i]
                px, py = v.x, v.y
            elif sub.startswith("Edge"):
                px, py = _edge_mid(geo.edges[i].occ)
            elif sub.startswith("Face"):
                px, py = _face_center(geo, i)
            else:
                px = py = 0.0
            x, y = px, -py                                    # DrawUtil::invertY(placement)
    else:
        raise E.TechDrawEditError("Selected object is not a part view, nor a leader line")
    n = s.name("SurfaceSymbol", op.get("name"))
    svg = surface_svg(int(op.get("icon", 0)), bool(op.get("iso", True)), op.get("method", ""), op.get("ra", 0), op.get("lay", ""),
                      op.get("addition", ""), op.get("sample_length", ""), op.get("min_rough", ""), op.get("max_rough", ""))
    s.add(O.DrawViewSymbol(n, symbol=svg, rotation=float(op.get("angle", 0.0)), owner=view.name if view else None, x=x, y=y,
                           label=n, stack_order=110))
    return f"made {n}"


def E_geo(s, E, v):
    doc = T.PageDocument(s.objs, s.shape_of).recompute()
    geo = doc.geo.get(v.name)
    if geo is None:
        raise E.TechDrawEditError(f"{v.name} has no geometry: {doc.errors.get(v.name, 'nothing to draw')}")
    return geo


def _edge_mid(edge):
    from .techdraw_annot import _mid_point
    return _mid_point(edge)


def _face_center(geo, i):
    """Face::getCenter: the centre of the face's outer wire's points."""
    faces = getattr(geo, "faces", None)
    if not faces or i >= len(faces):
        return 0.0, 0.0
    pts = [p for loop in faces[i].get("loops", faces[i].loops if hasattr(faces[i], "loops") else []) for p in loop] \
        if isinstance(faces[i], dict) else []
    if not pts:
        return 0.0, 0.0
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


# ── images (TechDraw_Image) ───────────────────────────────────────────────────────────────────────────────

def image_size(path: Path):
    """The pixel size of a PNG, JPEG or BMP (the header, without a decoder)."""
    b = path.read_bytes()
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", b[16:24])
    if b[:2] == b"BM":
        w, h = struct.unpack("<ii", b[18:26])
        return abs(w), abs(h)
    if b[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(b):
            if b[i] != 0xFF:
                i += 1
                continue
            m = b[i + 1]
            if m in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">HH", b[i + 5:i + 9])
                return w, h
            i += 2 + struct.unpack(">H", b[i + 2:i + 4])[0]
    raise ValueError(f"{path.name} is not a bitmap the app reads (png, jpeg, bmp)")


def _image(s, E, op):
    page = _need_page(s, E)
    f = op.get("file")
    if op.get("upload"):                                 # a file the person picked: kept in the project's techdraw/images
        import shutil
        src = Path(op["upload"])
        if not src.is_file():
            raise E.TechDrawEditError(f"the upload {src.name!r} is gone")
        dest_dir = s.pdir / "techdraw" / "images"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        i = 1
        while dest.exists() and dest.read_bytes() != src.read_bytes():
            dest = dest_dir / f"{src.stem}{i}{src.suffix}"
            i += 1
        if not dest.exists():
            shutil.copyfile(src, dest)
        f = f"techdraw/images/{dest.name}"
    _project_file(s, f, "file")
    O.DrawViewImage("check", image_file=f)                   # the extension
    n = s.name("Image", op.get("name"))
    owner = s.get(op["owner"], None, "view") if op.get("owner") else None
    if op.get("at") is not None:
        x, y = float(op["at"][0]), float(op["at"][1])
    elif owner is not None:
        x, y = 0.0, 0.0
    else:
        w, h = T.PageDocument(s.objs).page_size()
        x, y = w / 2.0, h / 2.0
    del page
    s.add(O.DrawViewImage(n, image_file=f, owner=owner.name if owner else None, x=x, y=y, label=n))
    return f"made {n}"


# ── clip groups (DrawViewClip) ────────────────────────────────────────────────────────────────────────────

def _clip(s, E, op):
    _need_page(s, E)
    n = s.name("Clip", op.get("name"))
    w, h = T.PageDocument(s.objs).page_size()
    s.add(O.DrawViewClip(n, x=w / 2.0, y=h / 2.0, label=n))
    return f"made {n}"


def _in_clip(s, name):
    return next((c for c in s.objs if isinstance(c, O.DrawViewClip) and name in c.views), None)


def _clip_add(s, E, op):
    clip = s.get(op.get("clip"), O.DrawViewClip, "clip group")
    view = s.get(op.get("view"))
    if not hasattr(view, "x") or isinstance(view, (T.DrawPage, T.DrawSVGTemplate)):
        raise E.TechDrawEditError("Select exactly one view to add to clip group")
    if view.name in clip.views or _in_clip(s, view.name):
        raise E.TechDrawEditError("the view is in a clip group already")
    d = T.as_dict(view)
    contains = _view_rect_contains(s, view, clip.x, clip.y)
    if contains:                                           # DrawViewClip::addView keeps the overlapped part of the view in the frame
        d["x"], d["y"] = view.x - clip.x, view.y - clip.y
    else:
        d["x"], d["y"] = 0.0, 0.0
    s.objs[s.objs.index(view)] = E._rebuilt(view, d)
    cd = T.as_dict(clip)
    cd["views"] = list(clip.views) + [view.name]
    s.objs[s.objs.index(clip)] = E._rebuilt(clip, cd)
    return f"added {view.name} to {clip.name}"


def view_rect(s, view):
    """DrawView::getRect(): the width and height of the rectangle a view occupies about its place (mm)."""
    if isinstance(view, T.DrawViewPart):
        try:
            geo = E_geo(s, None, view)
            return geo.box[2] - geo.box[0], geo.box[3] - geo.box[1]
        except Exception:
            return 0.0, 0.0
    if isinstance(view, T.DrawViewAnnotation):
        chars = max([1] + [len(t) for t in view.text])
        size = max(1, int(view.text_size))
        scale = s.page_obj().scale
        return scale * chars * size, scale * len(view.text) * size
    if isinstance(view, O.DrawViewSymbol):
        return 64.0, 64.0
    if isinstance(view, O.DrawViewImage):
        return view.width, view.height
    if isinstance(view, O.DrawViewClip):
        return view.width, view.height
    return 1.0, 1.0


def _view_rect_contains(s, view, px, py):
    """DrawViewClip::addView: whether getRectAligned() holds the clip's place (QRectF::contains: the edges count)."""
    w, h = view_rect(s, view)
    if w == 0.0 or h == 0.0:
        return False
    return view.x - w / 2.0 <= px <= view.x + w / 2.0 and view.y - h / 2.0 <= py <= view.y + h / 2.0


def _clip_remove(s, E, op):
    view = s.get(op.get("view"))
    clip = _in_clip(s, view.name)
    if clip is None:
        raise E.TechDrawEditError("View does not belong to a clip")
    cd = T.as_dict(clip)
    cd["views"] = [v for v in clip.views if v != view.name]
    s.objs[s.objs.index(clip)] = E._rebuilt(clip, cd)
    return f"removed {view.name} from {clip.name}"

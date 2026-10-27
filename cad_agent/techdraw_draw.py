# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses how FreeCAD's TechDraw draws its leader lines, rich text, symbols, weld symbols,
# images and clip groups and keeps FreeCAD's licence, the GNU Lesser General Public License, version 2.1 or (at your option)
# any later version; the text is in ../ui/LICENSE.
#
#   Derived from: src/Mod/TechDraw/Gui/QGILeaderLine.cpp (Copyright (c) 2019 WandererFan),
#                 src/Mod/TechDraw/Gui/QGIRichAnno.cpp (Copyright (c) 2019 WandererFan),
#                 src/Mod/TechDraw/Gui/QGIWeldSymbol.cpp, QGITile.cpp (Copyright (c) 2019 WandererFan),
#                 src/Mod/TechDraw/Gui/QGIArrow.cpp (Copyright (c) 2019 WandererFan),
#                 src/Mod/TechDraw/Gui/QGIViewSymbol.cpp (Copyright (c) 2012 Luke Parry),
#                 src/Mod/TechDraw/Gui/QGIViewImage.cpp (Copyright (c) 2012 Luke Parry),
#                 src/Mod/TechDraw/Gui/QGIViewClip.cpp (Copyright (c) 2012 Luke Parry),
#                 src/Mod/TechDraw/App/DrawLeaderLine.cpp (Copyright (c) 2019 WandererFan)
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
"""Where the page puts the leader lines, rich text, symbols, weld symbols, images and clip groups (results) and what it
draws for them (display, as techdraw_export.display's primitives).

All page coordinates here are mm with y down, as the export's primitives are. A leader's points follow
DrawLeaderLine::getScaledAndRotatedPoints, horizLastSegment and QGILeaderLine::getAttachPoint; the weld symbol's tiles
QGIWeldSymbol::drawTile and QGITile::calcTilePosition. Text is set with an estimated advance (Qt's metrics are not
available): ui/PARITY.md lists the differences.
"""
from __future__ import annotations

import base64
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from . import techdraw as T
from . import techdraw_objs as O
from .techdraw_export import Prim, REZ, _hex, view_origin

FONT_ADVANCE = 0.55                 # an estimated glyph advance in em (osifont is narrow)
SYMBOL_FACTOR = 1.25                # Decorations/SymbolFactor
SYMBOL_SIZE = 64.0                  # Dimensions/SymbolSize, scene units
FILLED, OPEN, TICK, DOT, OPEN_CIRCLE, FORK, TRIANGLE, NONE = T.END_TYPES


# ── leaders ──────────────────────────────────────────────────────────────────────────────────────────────

def overlap_adjust(style: str, size: float) -> float:
    """QGIArrow::getOverlapAdjust."""
    return {FILLED: 0.5 * size, OPEN: 0.1 * size, OPEN_CIRCLE: 0.25 * size, TRIANGLE: size}.get(style, 0.0)


def horiz_last_segment(wp, rotation_deg):
    """DrawLeaderLine::horizLastSegment (points y down)."""
    wp = list(wp)
    if len(wp) > 1:
        last, pen = wp[-1], wp[-2]
        seg = (last[0] - pen[0], -(last[1] - pen[1]))
        long = math.hypot(*seg)
        a = math.radians(rotation_deg)
        rx = seg[0] * math.cos(a) - seg[1] * math.sin(a)
        ry = seg[0] * math.sin(a) + seg[1] * math.cos(a)
        n = math.hypot(rx, ry) or 1.0
        dot = rx / n
        wp[-1] = (pen[0] + long, pen[1]) if dot >= 0 else (pen[0] - long, pen[1])
    return wp


def scaled_rotated(o, base_scale, base_rot, do_scale=None, do_rotate=None):
    """DrawLeaderLine::getScaledAndRotatedPoints: the way points (y down, mm), scaled when Scalable and rotated with the parent."""
    do_scale = o.scalable if do_scale is None else do_scale
    do_rotate = o.rotates_with_parent if do_rotate is None else do_rotate
    scale = base_scale if (o.scalable and do_scale) else 1.0
    rad = math.radians(base_rot) if do_rotate else 0.0
    out = []
    for p in o.way_points:
        x, y = p[0] * scale, -(p[1] * scale)                # invertY
        if rad:
            c, s = math.cos(rad), math.sin(rad)
            x, y = x * c - y * s, x * s + y * c
        out.append((x, -y))
    return out


def transformed(o, base_scale, base_rot):
    """DrawLeaderLine::getTransformedWayPoints: with AutoHorizontal's last segment."""
    pts = scaled_rotated(o, base_scale, base_rot)
    if o.auto_horizontal:
        pts = horiz_last_segment(pts, base_rot)
    return pts


def attach_point(o, base_scale, base_rot):
    """QGILeaderLine::getAttachPoint, in mm: the leader's origin relative to its parent's origin (y down)."""
    x, y = o.x * base_scale, o.y * base_scale
    rad = math.radians(base_rot)
    if rad:
        c, s = math.cos(rad), math.sin(rad)
        x, y = x * c - y * s, x * s + y * c
    return (x, -y)


def _object_origin(doc, res, name):
    """A parent's origin on the page and its scale and rotation."""
    o = doc.get(name)
    if o is None:
        return 0.0, res["height"], 1.0, 0.0
    if name in res["views"]:
        ox, oy = view_origin(res, name)
        return ox, oy, res["views"][name].get("scale", 1.0), getattr(o, "rotation", 0.0)
    x, y = _own_origin(doc, res, o)
    return x, y, getattr(o, "scale", 1.0) if not isinstance(o, O.DrawLeaderLine) else 1.0, getattr(o, "rotation", 0.0)


def _own_origin(doc, res, o):
    """The page point (y down) the object's X, Y name: relative to its owner when it has one (it is drawn in its group)."""
    owner = O.owner_of(o) if not isinstance(o, (O.DrawLeaderLine, O.DrawWeldSymbol, O.DrawTileWeld)) else None
    if isinstance(o, O.DrawLeaderLine):
        return leader_geometry(doc, res, o)["origin"]
    if owner and doc.get(owner) is not None and not isinstance(o, O.DrawRichAnno):
        px, py, _s, _r = _object_origin(doc, res, owner)
        return px + o.x, py - o.y
    return o.x, res["height"] - o.y


def leader_geometry(doc, res, o):
    px, py, scale, rot = _object_origin(doc, res, o.leader_parent) if o.leader_parent else (0.0, res["height"], 1.0, 0.0)
    ax, ay = attach_point(o, scale, rot)
    origin = (px + ax, py + ay)
    pts = transformed(o, scale, rot)
    page_pts = [(origin[0] + p[0], origin[1] + p[1]) for p in pts]
    tail = page_pts[-1] if page_pts else origin
    kink = page_pts[-2] if len(page_pts) > 1 else origin
    mid = ((tail[0] + kink[0]) / 2.0, (tail[1] + kink[1]) / 2.0) if len(page_pts) > 1 else origin
    # lastSegmentDirection: from the tail to the kink (y down); local axes: x along it, y a quarter turn off it
    if len(pts) > 1:
        d = (pts[-2][0] - pts[-1][0], pts[-2][1] - pts[-1][1])
        n = math.hypot(*d) or 1.0
        d = (d[0] / n, d[1] / n)
    else:
        d = (1.0, 0.0)
    ly = (d[0], -d[1])                                          # localY: invertY(localX) rotated 90 degrees, inverted again
    ly = (-ly[1], ly[0])
    ly = (ly[0], -ly[1])
    return {"origin": origin, "points": page_pts, "tail": tail, "kink": kink, "tile_origin": mid, "dir": d, "axes": [d, ly]}


def arrow_prims(style, tip, direction, size, width, attrs):
    """QGIArrow in direction mode: the head with its tip at tip, direction pointing out of the line (y down)."""
    if style == NONE:
        return []
    dx, dy = direction
    n = math.hypot(dx, dy) or 1.0
    dx, dy = dx / n, dy / n
    neg = (-dx, -dy)
    perp = (-neg[1], neg[0])
    black = "#000000"

    def at(v):
        return (tip[0] + v[0], tip[1] + v[1])
    if style == FILLED:
        w = size / 6.0
        b1 = at((neg[0] * size + perp[0] * w, neg[1] * size + perp[1] * w))
        b2 = at((neg[0] * size - perp[0] * w, neg[1] * size - perp[1] * w))
        return [Prim("path", [("M", *tip), ("L", *b1), ("L", *b2), ("Z",)], width=0.0, fill=black, stroke="none", attrs=attrs)]
    if style == OPEN:
        w = size / 3.0
        b1 = at((neg[0] * size + perp[0] * w, neg[1] * size + perp[1] * w))
        b2 = at((neg[0] * size - perp[0] * w, neg[1] * size - perp[1] * w))
        return [Prim("path", [("M", *b1), ("L", *tip), ("L", *b2)], width=width, attrs=attrs)]
    if style == TICK:
        ln, w = size / 2.0, size / 2.0
        b1 = at((neg[0] * ln - perp[0] * w, neg[1] * ln - perp[1] * w))
        b2 = at((dx * ln + perp[0] * w, dy * ln + perp[1] * w))
        return [Prim("path", [("M", *b1), ("L", *b2)], width=width, attrs=attrs)]
    if style in (DOT, OPEN_CIRCLE):
        r = size / 4.0
        segs = [("M", tip[0] + r, tip[1]), ("A", r, 0, 1, tip[0] - r, tip[1]), ("A", r, 0, 1, tip[0] + r, tip[1]), ("Z",)]
        return [Prim("path", segs, width=width, fill=black if style == DOT else "none", attrs=attrs)]
    if style == FORK:
        ln, w = size / 2.0, size / 2.0
        fperp = (-dy, dx)
        b1 = at((dx * ln + fperp[0] * w, dy * ln + fperp[1] * w))
        b2 = at((dx * ln - fperp[0] * w, dy * ln - fperp[1] * w))
        return [Prim("path", [("M", *b1), ("L", *tip), ("L", *b2)], width=width, attrs=attrs)]
    if style == TRIANGLE:
        w = size / 2.0
        top = at((neg[0] * size, neg[1] * size))
        b1 = at((perp[0] * w, perp[1] * w))
        b2 = at((-perp[0] * w, -perp[1] * w))
        return [Prim("path", [("M", *top), ("L", *b1), ("L", *b2), ("Z",)], width=0.0, fill=black, stroke="none", attrs=attrs)]
    return []


PEN_DASH = {"NoLine": None, "Continuous": (), "Dash": (4.0, 2.0), "Dot": (1.0, 2.0), "DashDot": (4.0, 2.0, 1.0, 2.0),
            "DashDotDot": (4.0, 2.0, 1.0, 2.0, 1.0, 2.0)}


def _leader_prims(o, g):
    attrs = {"data-name": o.name}
    pts = [list(p) for p in g["points"]]
    if len(pts) < 2:
        return []
    size = ARROW_MM
    sa = overlap_adjust(o.start_symbol, size) if o.start_symbol != NONE else 0.0
    ea = overlap_adjust(o.end_symbol, size) if o.end_symbol != NONE else 0.0
    drawn = [p[:] for p in pts]
    for i, adj, j in ((0, sa, 1), (-1, ea, -2)):
        d = (pts[j][0] - pts[i][0], pts[j][1] - pts[i][1])
        n = math.hypot(*d) or 1.0
        drawn[i][0] += d[0] / n * adj
        drawn[i][1] += d[1] / n * adj
    dash = PEN_DASH.get(o.line_style, ())
    out = []
    if dash is not None:
        segs = [("M", *drawn[0])] + [("L", *p) for p in drawn[1:]]
        out.append(Prim("path", segs, width=o.line_width, dash=tuple(x * max(o.line_width, 0.35) for x in dash) if dash else (),
                        stroke=_hex(o.color), attrs=attrs))
    out += arrow_prims(o.start_symbol, pts[0], (pts[0][0] - pts[1][0], pts[0][1] - pts[1][1]), size, o.line_width, attrs)
    out += arrow_prims(o.end_symbol, pts[-1], (pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1]), size, o.line_width, attrs)
    return out


# ── rich text ────────────────────────────────────────────────────────────────────────────────────────────

_BLOCK = re.compile(r"<p\b[^>]*>(.*?)</p>", re.S | re.I)
_SPAN = re.compile(r"<span\b([^>]*)>(.*?)</span>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")
_BODY_STYLE = re.compile(r"<body\b[^>]*style=\"([^\"]*)\"", re.I)
_PT = re.compile(r"font-size:\s*([0-9.]+)pt")


def html_unescape(t: str) -> str:
    return t.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&amp;", "&").replace("&nbsp;", " ")


def rich_blocks(html: str):
    """The blocks of QTextDocument::toHtml's output: each a list of (text, bold, italic, underline, colour, size pt)."""
    body_pt = 9.0
    m = _BODY_STYLE.search(html or "")
    if m:
        pm = _PT.search(m.group(1))
        if pm:
            body_pt = float(pm.group(1))
    blocks = []
    for bm in _BLOCK.finditer(html or ""):
        inner = bm.group(1)
        runs, pos = [], 0
        for sm in _SPAN.finditer(inner):
            if sm.start() > pos:
                t = html_unescape(_TAG.sub("", inner[pos:sm.start()]))
                if t:
                    runs.append((t, False, False, False, None, body_pt))
            st = sm.group(1)
            bold = "font-weight:" in st and re.search(r"font-weight:\s*(7|8|9)\d\d|font-weight:\s*bold", st) is not None
            ital = "font-style:italic" in st.replace(" ", "")
            und = "underline" in st
            cm = re.search(r"color:\s*(#[0-9a-fA-F]{6})", st)
            pm = _PT.search(st)
            t = html_unescape(_TAG.sub("", sm.group(2)))
            runs.append((t, bold, ital, und, cm.group(1) if cm else None, float(pm.group(1)) if pm else body_pt))
            pos = sm.end()
        if pos < len(inner):
            t = html_unescape(_TAG.sub("", inner[pos:]))
            if t:
                runs.append((t, False, False, False, None, body_pt))
        blocks.append(runs)
    return blocks


def rich_layout(o):
    """The text's lines (runs placed on baselines) and its size in mm, QGIRichAnno's top-left origin (y down)."""
    mm_pt = 25.4 / 72.0
    blocks = rich_blocks(o.anno_text) or [[]]
    lines, y, width = [], 0.0, 0.0
    for runs in blocks:
        pt = max([r[5] for r in runs] or [9.0])
        h = pt * mm_pt * 1.2
        base = y + pt * mm_pt
        x = 0.0
        placed = []
        for text, bold, ital, und, col, rpt in runs:
            adv = len(text) * rpt * mm_pt * FONT_ADVANCE * (1.08 if bold else 1.0)
            placed.append((x, text, bold, ital, und, col, rpt))
            x += adv
        lines.append((base, placed))
        width = max(width, x)
        y += h
    if o.max_width > 0:
        width = o.max_width
    return lines, width, y


def _richanno_prims(doc, res, o):
    lines, w, h = rich_layout(o)
    px, py = _own_origin(doc, res, o)
    if o.origin_centered:
        px, py = px - w / 2.0, py - h / 2.0
    attrs = {"data-name": o.name}
    out = []
    mm_pt = 25.4 / 72.0
    for base, runs in lines:
        for x, text, bold, ital, und, col, pt in runs:
            out.append(Prim("text", at=(px + x, py + base), size=pt * mm_pt, text=text, anchor="start",
                            attrs={**attrs, **({"font-weight": "bold"} if bold else {}), **({"font-style": "italic"} if ital else {}),
                                   **({"text-decoration": "underline"} if und else {}), **({"data-color": col} if col else {})}))
    if o.show_frame and PEN_DASH.get(o.line_style, ()) is not None:
        dash = PEN_DASH[o.line_style]
        out.append(Prim("path", [("M", px, py), ("L", px + w, py), ("L", px + w, py + h), ("L", px, py + h), ("Z",)],
                        width=o.line_width, dash=tuple(x * max(o.line_width, 0.35) for x in dash) if dash else (),
                        stroke=_hex(o.line_color), attrs=attrs))
    return out


# ── SVG symbols ──────────────────────────────────────────────────────────────────────────────────────────

SVG_NS = "http://www.w3.org/2000/svg"


def _num(v):
    m = re.match(r"\s*([0-9.+-eE]+)\s*([a-z%]*)", v or "")
    return (float(m.group(1)), m.group(2)) if m else (None, "")


def svg_parts(svg: str):
    """(root element, width and height in user px, viewBox, units of the height) of an SVG text."""
    root = ET.fromstring(svg.encode("utf-8"))
    vb = [float(x) for x in re.split(r"[ ,]+", root.get("viewBox", "").strip())] if root.get("viewBox") else None
    w, _wu = _num(root.get("width"))
    h, hu = _num(root.get("height"))
    if w is None:
        w = vb[2] if vb else 100.0
    if h is None:
        h = vb[3] if vb else 100.0
    return root, w, h, vb, hu


def symbol_svg(svg: str, cx: float, cy: float, scale: float, legacy: bool = False, rotation: float = 0.0, attrs=None):
    """The symbol drawn centred at (cx, cy) mm, as a nested svg in the page's scene units (QGIViewSymbol::symbolScaler:
    an SVG in mm is drawn in mm, any other in scene units, a pixel being 0.1 mm)."""
    try:
        root, w, h, vb, hu = svg_parts(svg)
    except ET.ParseError:
        return ""
    if hu == "mm" and not legacy:
        wmm = w * scale
        hmm = h * scale
    elif legacy:
        wmm, hmm = w * scale / 3.78, h * scale / 3.78
    else:
        wmm, hmm = w * scale * 0.1, h * scale * 0.1
    ET.register_namespace("", SVG_NS)
    root.set("x", f"{(cx - wmm / 2.0) * REZ:.4f}")
    root.set("y", f"{(cy - hmm / 2.0) * REZ:.4f}")
    root.set("width", f"{wmm * REZ:.4f}")
    root.set("height", f"{hmm * REZ:.4f}")
    if vb is None:
        root.set("viewBox", f"0 0 {w} {h}")
    root.set("overflow", "visible")
    for k, v in (attrs or {}).items():
        root.set(k, v)
    body = ET.tostring(root, encoding="unicode")
    if rotation:
        return (f'<g transform="rotate({-rotation:.4f} {cx * REZ:.4f} {cy * REZ:.4f})">{body}</g>')
    return body


def _symbol_prims(doc, res, o):
    cx, cy = _own_origin(doc, res, o)
    return [Prim("raw", text=symbol_svg(o.symbol, cx, cy, o.scale, o.legacy_scaling, o.rotation, {"data-name": o.name}))] if o.symbol else []


# ── weld symbols ─────────────────────────────────────────────────────────────────────────────────────────

def _tile_svg(doc, t, centre, rotation_deg, left_x, o_font_mm, color):
    """A tile: its symbol centred, scaled by Decorations/SymbolFactor, turned with the leader's last segment."""
    cx, cy = centre
    out = []
    path = None
    try:
        path = O.symbol_path(t.symbol_file) if t.symbol_file else None
    except T.TechDrawError:
        path = None
    parts = [f'<g transform="rotate({rotation_deg:.4f} {cx * REZ:.4f} {cy * REZ:.4f})">']
    if path is not None:
        txt = path.read_text(encoding="utf-8")
        try:
            root, w, h, vb, hu = svg_parts(txt)
            side = w * SYMBOL_FACTOR * 0.1
            sideh = h * SYMBOL_FACTOR * 0.1
            ET.register_namespace("", SVG_NS)
            root.set("x", f"{(cx - side / 2.0) * REZ:.4f}")
            root.set("y", f"{(cy - sideh / 2.0) * REZ:.4f}")
            root.set("width", f"{side * REZ:.4f}")
            root.set("height", f"{sideh * REZ:.4f}")
            if vb is None:
                root.set("viewBox", f"0 0 {w} {h}")
            root.set("overflow", "visible")
            parts.append(ET.tostring(root, encoding="unicode"))
        except ET.ParseError:
            pass
    half = (SYMBOL_SIZE - 4.0) * SYMBOL_FACTOR * 0.1 / 2.0          # mm
    fs = o_font_mm
    adv = fs * FONT_ADVANCE
    row = t.tile_row

    def text(x, y, s, anchor):
        return (f'<text x="{x * REZ:.4f}" y="{y * REZ:.4f}" font-family="osifont" font-size="{fs * REZ:.4f}" '
                f'text-anchor="{anchor}" fill="{color}">{s}</text>')
    vfudge = 0.10
    if t.left_text:
        hm = half + adv * 1.5
        parts.append(text(cx - hm, cy + (fs * vfudge if row < 0 else 0.0) + fs * 0.35, _esc(t.left_text), "end"))
    if t.right_text:
        hm = half + adv
        parts.append(text(cx + hm, cy + (fs * vfudge if row < 0 else 0.0) + fs * 0.35, _esc(t.right_text), "start"))
    if t.center_text.strip():
        vo = (half * 2) * (1 + vfudge) if row < 0 else -0.5 * (half * 2 + fs)
        parts.append(text(cx, cy + vo + fs * 0.35, _esc(t.center_text), "middle"))
    parts.append("</g>")
    return "".join(parts), out


def _esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _weld_prims(doc, res, w):
    lead = doc.get(w.leader)
    if not isinstance(lead, O.DrawLeaderLine):
        return []
    g = leader_geometry(doc, res, lead)
    if len(g["points"]) < 2:
        return []
    tiles = {t.tile_row: t for t in doc.objects if isinstance(t, O.DrawTileWeld) and t.tile_parent == w.name}
    xdir, ydir = g["axes"]
    dot = xdir[0]
    if dot < 0:
        ydir = (-ydir[0], -ydir[1])
    angle = math.degrees(math.atan2(xdir[1], xdir[0]))
    # QGIWeldSymbol::getLastSegAngle: DU::angleWithX of the (y down) direction, then Qt's clockwise degrees
    rot = angle
    if dot < 0:
        rot -= DEGREES
    tail_right = g["tail"][0] >= g["kink"][0]
    size = (SYMBOL_SIZE - 4.0) * SYMBOL_FACTOR * 0.1
    org = g["tile_origin"]
    color = _hex(getattr(lead, "color", (0, 0, 0, 1)))
    out = []
    for row in (0, -1):
        t = tiles.get(row)
        if t is None:
            continue
        tw = size + (len(t.left_text) + len(t.right_text)) * w.tile_font_size * FONT_ADVANCE
        if row == 0:
            pos = (org[0] + ydir[0] * size * 0.5, org[1] + ydir[1] * size * 0.5)
            pos = (org[0] - 0.0, org[1])
            pos = (org[0] + ydir[0] * size * 0.5, org[1] + ydir[1] * size * 0.5)
        elif w.alternating_weld:
            sgn = 1.0 if tail_right else -1.0
            pos = (org[0] + sgn * xdir[0] * 0.5 * tw - ydir[0] * size * 0.5, org[1] + sgn * xdir[1] * 0.5 * tw - ydir[1] * size * 0.5)
        else:
            pos = (org[0] - ydir[0] * size * 0.5, org[1] - ydir[1] * size * 0.5)
        svg, _ = _tile_svg(doc, t, pos, rot, 0.0, w.tile_font_size, color)
        out.append(Prim("raw", text=f'<g data-name="{w.name}">{svg}</g>'))
    attrs = {"data-name": w.name}
    kink = g["kink"]
    if w.all_around:
        r = w.font_size * 0.5 * 1.0
        r = round(w.font_size * REZ + 0.5) / REZ
        out.append(Prim("path", [("M", kink[0] + r, kink[1]), ("A", r, 0, 1, kink[0] - r, kink[1]), ("A", r, 0, 1, kink[0] + r, kink[1]),
                                 ("Z",)], width=lead.line_width, stroke=color, attrs=attrs))
    if w.field_weld:
        flag = [(0.0, 0.0), (ydir[0] * 3.0, ydir[1] * 3.0), (-xdir[0] * 2.0 + ydir[0] * 2.5, -xdir[1] * 2.0 + ydir[1] * 2.5),
                (ydir[0] * 2.0, ydir[1] * 2.0)]
        sc = round(w.font_size * REZ + 0.5) / 2.0 / REZ
        pts = [(kink[0] + p[0] * sc, kink[1] + p[1] * sc) for p in flag]
        out.append(Prim("path", [("M", *pts[0])] + [("L", *p) for p in pts[1:]], width=lead.line_width, fill=color, stroke=color,
                        attrs=attrs))
    if w.tail_text:
        fs = w.font_size
        brw = len(w.tail_text) * fs * FONT_ADVANCE
        brh = fs * 1.2
        hm = brw / len(w.tail_text) + ARROW_MM
        tail = g["tail"]
        sx = 0.0
        yd = ydir
        if dot < 0:
            sx = 0.0
        else:
            sx = -brw
        tx = tail[0] - xdir[0] * hm + yd[0] * brh * 1.2 / 2 + (xdir[0] * 0 + sx)
        ty = tail[1] - xdir[1] * hm + yd[1] * brh * 1.2 / 2
        out.append(Prim("text", at=(tx, ty), size=fs, text=w.tail_text, anchor="start", angle=-rot, attrs=attrs))
    return out


DEGREES = 180.0
ARROW_MM = 3.5


# ── images ───────────────────────────────────────────────────────────────────────────────────────────────

MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".bmp": "image/bmp"}


def _image_prims(doc, res, o, pdir):
    if not o.image_file or pdir is None:
        return []
    p = Path(pdir) / o.image_file
    if not p.is_file():
        return []
    from .techdraw_more import image_size
    try:
        wpx, hpx = image_size(p)
    except Exception:
        return []
    cx, cy = _own_origin(doc, res, o)
    if o.crop:
        wmm, hmm = o.width, o.height
    else:
        wmm, hmm = wpx * 0.1 * o.scale, hpx * 0.1 * o.scale
    data = base64.b64encode(p.read_bytes()).decode()
    iw, ih = wpx * 0.1 * o.scale, hpx * 0.1 * o.scale
    rot = f' transform="rotate({-o.rotation:.4f} {cx * REZ:.4f} {cy * REZ:.4f})"' if o.rotation else ""
    clip = ""
    if o.crop:
        clip = f'<clipPath id="clip-{o.name}"><rect x="{(cx - wmm / 2) * REZ:.4f}" y="{(cy - hmm / 2) * REZ:.4f}" width="{wmm * REZ:.4f}" height="{hmm * REZ:.4f}"/></clipPath>'
    img = (f'<image x="{(cx - iw / 2) * REZ:.4f}" y="{(cy - ih / 2) * REZ:.4f}" width="{iw * REZ:.4f}" height="{ih * REZ:.4f}" '
           f'preserveAspectRatio="none" href="data:{MIME[p.suffix.lower()]};base64,{data}"'
           f'{f" clip-path=\"url(#clip-{o.name})\"" if o.crop else ""}/>')
    return [Prim("raw", text=f'<g data-name="{o.name}"{rot}>{clip}{img}</g>')]


# ── clip groups ──────────────────────────────────────────────────────────────────────────────────────────

def _clip_prims(doc, res, c):
    out = []
    x, y = c.x, res["height"] - c.y
    x0, y0, w, h = x - c.width / 2.0, y - c.height / 2.0, c.width, c.height
    if c.clip_children:
        out.append(Prim("raw", text=f'<clipPath id="clip-{c.name}"><rect x="{x0 * REZ:.4f}" y="{y0 * REZ:.4f}" '
                                    f'width="{w * REZ:.4f}" height="{h * REZ:.4f}"/></clipPath>'))
    if c.show_frame:
        out.append(Prim("path", [("M", x0, y0), ("L", x0 + w, y0), ("L", x0 + w, y0 + h), ("L", x0, y0 + h), ("Z",)], width=0.35,
                        attrs={"data-name": c.name}))
    return out


# ── the page ─────────────────────────────────────────────────────────────────────────────────────────────

def results(doc) -> dict:
    """What the page, the CLI and the goldens read of these objects: leaders' points and local axes, rich text's size,
    symbols' places. Everything is in the page's mm with y down."""
    objs = [o for o in doc.objects if o.kind in {c.kind for c in O.NEW_CLASSES}]
    if not objs:
        return {}
    w, h = doc.page_size()
    res = {"views": {}, "height": h}
    for name, (x, y) in doc.pos.items():
        res["views"][name] = {"x": x, "y": y, "scale": doc.view_scale(doc.get(name)) if doc.get(name) is not None else 1.0}
    out = {"leaders": {}, "richannos": {}, "symbols": {}, "welds": {}, "images": {}, "clips": {}}
    for o in objs:
        if isinstance(o, O.DrawLeaderLine):
            g = leader_geometry(doc, res, o)
            out["leaders"][o.name] = {k: ([list(p) for p in v] if k == "points" else list(v) if isinstance(v, tuple) else v)
                                      for k, v in g.items() if k != "axes"} | {"axes": [list(a) for a in g["axes"]]}
        elif isinstance(o, O.DrawRichAnno):
            _l, rw, rh = rich_layout(o)
            px, py = _own_origin(doc, res, o)
            out["richannos"][o.name] = {"at": [px, py], "size": [rw, rh]}
        elif isinstance(o, O.DrawViewSymbol):
            cx, cy = _own_origin(doc, res, o)
            out["symbols"][o.name] = {"at": [cx, cy], "editable_texts": o.editable_texts}
        elif isinstance(o, O.DrawWeldSymbol):
            lead = doc.get(o.leader)
            if isinstance(lead, O.DrawLeaderLine):
                g = leader_geometry(doc, res, lead)
                out["welds"][o.name] = {"tile_origin": list(g["tile_origin"]), "kink": list(g["kink"]), "tail": list(g["tail"]),
                                        "dir": list(g["dir"]), "tail_right": g["tail"][0] >= g["kink"][0]}
        elif isinstance(o, O.DrawViewClip):
            out["clips"][o.name] = {"at": [o.x, h - o.y], "views": list(o.views)}
        elif isinstance(o, O.DrawViewImage):
            out["images"][o.name] = {"at": list(_own_origin(doc, res, o))}
    return out


def display(doc, res: dict, pdir=None) -> list:
    """The page's primitives for these objects, after the dimensions, balloons and annotations."""
    out = []
    clipped = {}
    for c in (o for o in doc.objects if isinstance(o, O.DrawViewClip)):
        out += _clip_prims(doc, res, c)
        if c.clip_children:
            for v in c.views:
                clipped[v] = c.name
    for o in doc.objects:
        if isinstance(o, O.DrawLeaderLine):
            out += _leader_prims(o, leader_geometry(doc, res, o))
        elif isinstance(o, O.DrawRichAnno):
            out += _richanno_prims(doc, res, o)
        elif isinstance(o, O.DrawViewSymbol):
            out += _symbol_prims(doc, res, o)
        elif isinstance(o, O.DrawWeldSymbol):
            out += _weld_prims(doc, res, o)
        elif isinstance(o, O.DrawViewImage):
            out += _image_prims(doc, res, o, pdir)
    return out, clipped

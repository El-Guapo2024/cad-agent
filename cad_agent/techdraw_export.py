# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses how FreeCAD's TechDraw draws and exports a page and keeps FreeCAD's licence,
# the GNU Lesser General Public License, version 2.1 or (at your option) any later version; the text is in
# ../ui/LICENSE.
#
#   Derived from: src/Mod/TechDraw/Gui/QGSPage.cpp (Copyright (c) 2020 WandererFan),
#                 src/Mod/TechDraw/Gui/PagePrinter.cpp (Copyright (c) 2023 WandererFan),
#                 src/Mod/TechDraw/Gui/QGIViewPart.cpp (Copyright (c) 2013 Luke Parry),
#                 src/Mod/TechDraw/Gui/QGIViewDimension.cpp (Copyright (c) 2013 Luke Parry),
#                 src/Mod/TechDraw/Gui/QGIViewBalloon.cpp (Copyright (c) 2013 Luke Parry, 2019 Franck Jullien),
#                 src/Mod/TechDraw/Gui/QGIViewAnnotation.cpp (Copyright (c) 2013 Luke Parry, 2014 WandererFan),
#                 src/Mod/TechDraw/Gui/QGISectionLine.cpp (Copyright (c) 2016 WandererFan),
#                 src/Mod/TechDraw/Gui/QGIFace.cpp (Copyright (c) 2013 Luke Parry),
#                 src/Mod/TechDraw/Gui/Rez.cpp (Copyright (c) 2016 WandererFan),
#                 src/Mod/TechDraw/App/AppTechDrawPy.cpp (Copyright (c) 2002 Jürgen Riegel, 2016 WandererFan),
#                 src/Mod/TechDraw/App/DrawSVGTemplate.cpp (Copyright (c) 2002 Jürgen Riegel, 2014 Luke Parry),
#                 src/Mod/TechDraw/LineGroup/LineGroup.csv (no copyright line)
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
"""A TechDraw page drawn, and exported as TechDraw_ExportPageSVG, _ExportPageDXF and _ExportPagePDF do.

    display(doc)          the page as primitives: every view's edges with QGIViewPart's pens, section faces,
                          section lines, dimensions (QGIViewDimension's ISO oriented style), balloons, annotations
    page_svg(doc)         QGSPage::saveSvg: 10 units to the millimetre (Rez::guiX), the template's SVG (its editable
                          texts filled, DrawSVGTemplate::processTemplate) in a group scaled by 10, the drawing over it;
                          each edge a <path> with data-view and data-sub ("Edge3"), which the page selects by
    page_dxf(doc)         TechDraw.writeDXFPage: per view a layer named after it with its visible hard, outline and
                          smooth lines (and the hidden ones with HardHidden), mirrored back to y up and moved to the
                          view's place; an annotation's first line as TEXT; dimensions (below)
    page_pdf(doc)         PagePrinter::printPdf: one page the template's size, the template and the drawing, vector

Dimensions in the DXF are lines, arrowheads and a TEXT, where FreeCAD writes a DIMENSION entity and its block
(CDxfWrite::writeLinearDim ...): the text is FreeCAD's (FORMATTED, as writeDXFPage takes it). The pens are the
line group "FC 0.70mm" (Preferences > TechDraw > Decorations LineGroup 3): visible 0.70, hidden 0.35 dashed,
dimensions 0.35, the text osifont 5 mm (Labels and Dimensions defaults).
"""
from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

REZ = 10.0                      # Rez::guiX(1.0): scene units to the millimetre
THICK, THIN, GRAPHIC, EXTRA = 0.70, 0.35, 0.50, 1.40       # LineGroup.csv "FC 0.70mm"
FONT = "osifont"
FONT_MM = 5.0                   # Preferences::labelFontSizeMM, dimFontSizeMM
ARROW_MM = 3.5                  # Preferences::dimArrowSize
HIDDEN_DASH = (2.0, 1.0)        # ISO 128-20 line type 02 at the thin width (dash 12 d, gap 3 d: drawn here at 2 / 1 mm)
CENTER_DASH = (8.0, 1.0, 1.0, 1.0)
SECTION_LINE = (0.0, 0.0, 0.0)
EXT_OVERSHOOT = 1.5             # ISO 129-1: extension lines run past the dimension line
EXT_GAP = 1.0                   # and start a little off the feature


@dataclass
class Prim:
    kind: str                           # "path" | "text"
    segs: list = field(default_factory=list)   # path: [("M", x, y), ("L", x, y), ("A", r, large, sweep, x, y), ("Z",)]
    width: float = THIN
    dash: tuple = ()
    fill: str | None = None
    stroke: str = "#000000"
    attrs: dict = field(default_factory=dict)
    at: tuple = (0.0, 0.0)              # text
    size: float = FONT_MM
    text: str = ""
    anchor: str = "middle"              # start | middle | end
    angle: float = 0.0                  # degrees, counter-clockwise on the page


# ─── the drawing ─────────────────────────────────────────────────────────────────────────────────────────────

def _edge_segs(ej: dict, ox: float, oy: float) -> list:
    """An edge (techdraw_view.edge_json, view coordinates, y down) as path segments on the page (mm, y down)."""
    P = lambda p: (ox + p[0], oy + p[1])  # noqa: E731
    k = ej["kind"]
    if k == "CIRCLE":
        cx, cy = P(ej["center"])
        r = ej["radius"]
        return [("M", cx + r, cy), ("A", r, 0, 1, cx - r, cy), ("A", r, 0, 1, cx + r, cy), ("Z",)]
    if k == "ARCOFCIRCLE":
        s, e = P(ej["start"]), P(ej["end"])
        # AOC::cw is "clockwise" in the y-down paper frame from the mid point's side: SVG's sweep flag 1 is clockwise
        # on screen, which is the same frame
        return [("M", *s), ("A", ej["radius"], 1 if ej["large"] else 0, 1 if ej["cw"] else 0, *e)]
    if "points" in ej:
        pts = [P(p) for p in ej["points"]]
        return [("M", *pts[0])] + [("L", *p) for p in pts[1:]]
    return [("M", *P(ej["start"])), ("L", *P(ej["end"]))]


def view_origin(res: dict, name: str):
    """A view's centre on the page, y down."""
    v = res["views"][name]
    return v["x"], res["height"] - v["y"]


def _arrow(tip, direction, size=ARROW_MM) -> Prim:
    """A filled arrowhead (ArrowPropEnum "Filled arrow", QGIArrow: length size, half width size / 6)."""
    dx, dy = direction
    n = math.hypot(dx, dy) or 1.0
    dx, dy = dx / n, dy / n
    bx, by = tip[0] - dx * size, tip[1] - dy * size
    w = size / 6.0
    p1 = (bx - dy * w, by + dx * w)
    p2 = (bx + dy * w, by - dx * w)
    return Prim("path", [("M", *tip), ("L", *p1), ("L", *p2), ("Z",)], width=0.0, fill="#000000", stroke="none")


def _text_angle(dx, dy) -> float:
    """The angle a text along (dx, dy) (page, y down) is drawn at, turned so it reads from the bottom or the right
    (ISO oriented)."""
    a = math.degrees(math.atan2(-dy, dx))       # counter-clockwise, y up
    if a > 90.0 + 1e-9:
        a -= 180.0
    elif a <= -90.0 + 1e-9:
        a += 180.0
    return a


def _dim_text_prims(d: dict, at, angle, attrs) -> list:
    out = [Prim("text", at=at, size=FONT_MM, text=d["text"], anchor="middle", angle=angle, attrs=attrs)]
    tol = d.get("tolerances")
    if tol:
        w = len(d["text"]) * FONT_MM * 0.3
        a = math.radians(angle)
        ux, uy = math.cos(a), -math.sin(a)
        nx, ny = -uy, ux
        base = (at[0] + ux * (w + 0.6), at[1] + uy * (w + 0.6))
        size = FONT_MM * 0.6                    # Preferences::toleranceScale 0.6
        out.append(Prim("text", at=(base[0] - nx * size * 0.6, base[1] - ny * size * 0.6), size=size, text=tol[1],
                        anchor="start", angle=angle, attrs=attrs))
        out.append(Prim("text", at=(base[0] + nx * size * 0.4, base[1] + ny * size * 0.4), size=size, text=tol[0],
                        anchor="start", angle=angle, attrs=attrs))
    return out


def _linear_dim(d: dict, ox: float, oy: float, label) -> list:
    """QGIViewDimension::drawDistance, ISO oriented: extension lines from the points to the dimension line through
    the label, arrows inward at its ends, the text over its middle."""
    p0 = (ox + d["first"][0], oy + d["first"][1])
    p1 = (ox + d["second"][0], oy + d["second"][1])
    t = d["type"]
    if t == "DistanceX":
        u = (1.0, 0.0)
    elif t == "DistanceY":
        u = (0.0, 1.0)
    else:
        u = (p1[0] - p0[0], p1[1] - p0[1])
        n = math.hypot(*u) or 1.0
        u = (u[0] / n, u[1] / n)
    nrm = (-u[1], u[0])
    # the dimension line: along u through the label's foot (the text sits on the line)
    gap = FONT_MM * 0.25
    lab = (label[0] + nrm[0] * 0.0, label[1] + nrm[1] * 0.0)
    off0 = (lab[0] - p0[0]) * nrm[0] + (lab[1] - p0[1]) * nrm[1]
    off1 = (lab[0] - p1[0]) * nrm[0] + (lab[1] - p1[1]) * nrm[1]
    # the line through the label point, below its text by the gap
    side = 1.0 if (off0 + off1) >= 0 else -1.0
    line_off = gap * side
    a0 = (p0[0] + nrm[0] * (off0 + line_off), p0[1] + nrm[1] * (off0 + line_off))
    a1 = (p1[0] + nrm[0] * (off1 + line_off), p1[1] + nrm[1] * (off1 + line_off))
    attrs = {"data-dim": d["name"]}
    out = []
    for p, a, off in ((p0, a0, off0 + line_off), (p1, a1, off1 + line_off)):
        s = 1.0 if off >= 0 else -1.0
        start = (p[0] + nrm[0] * s * EXT_GAP, p[1] + nrm[1] * s * EXT_GAP)
        end = (a[0] + nrm[0] * s * EXT_OVERSHOOT, a[1] + nrm[1] * s * EXT_OVERSHOOT)
        if abs(off) > EXT_GAP:
            out.append(Prim("path", [("M", *start), ("L", *end)], width=THIN, attrs=attrs))
    out.append(Prim("path", [("M", *a0), ("L", *a1)], width=THIN, attrs=attrs))
    du = (a1[0] - a0[0], a1[1] - a0[1])
    out.append(_arrow(a0, (-du[0], -du[1])))
    out.append(_arrow(a1, du))
    ang = _text_angle(*du) if math.hypot(*du) > 0 else 0.0
    out += _dim_text_prims(d, label, ang, attrs)
    return out


def _arc_dim(d: dict, ox: float, oy: float, label) -> list:
    """drawRadius / drawDiameter, ISO oriented: a line from the label through the centre (diameter: across the
    circle), arrows on the circle, the text at the label."""
    c = (ox + d["center"][0], oy + d["center"][1])
    r = d["radius"]
    v = (label[0] - c[0], label[1] - c[1])
    n = math.hypot(*v)
    if n < 1e-9:
        v, n = (1.0, 0.0), 1.0
    u = (v[0] / n, v[1] / n)
    on = (c[0] + u[0] * r, c[1] + u[1] * r)
    attrs = {"data-dim": d["name"]}
    out = []
    if d["type"] == "Diameter":
        far = (c[0] - u[0] * r, c[1] - u[1] * r)
        out.append(Prim("path", [("M", *far), ("L", *label)], width=THIN, attrs=attrs))
        out.append(_arrow(far, (-u[0], -u[1])))
        out.append(_arrow(on, u))
    else:
        out.append(Prim("path", [("M", *c), ("L", *label)], width=THIN, attrs=attrs))
        out.append(_arrow(on, u))
    ang = _text_angle(*u)
    out += _dim_text_prims(d, (label[0] - u[1] * 0.0, label[1] - FONT_MM * 0.3), ang, attrs)
    return out


def _angle_dim(d: dict, ox: float, oy: float, label) -> list:
    """drawAngle: an arc about the apex through the label, between the two legs, arrows at its ends."""
    v = (ox + d["vertex"][0], oy + d["vertex"][1])
    f = (ox + d["first"][0], oy + d["first"][1])
    s = (ox + d["second"][0], oy + d["second"][1])
    r = math.hypot(label[0] - v[0], label[1] - v[1]) or 10.0
    a0 = math.atan2(f[1] - v[1], f[0] - v[0])
    a1 = math.atan2(s[1] - v[1], s[0] - v[0])
    sweep = (a1 - a0) % (2 * math.pi)
    if sweep > math.pi:
        a0, a1 = a1, a0
        sweep = 2 * math.pi - sweep
    p0 = (v[0] + r * math.cos(a0), v[1] + r * math.sin(a0))
    p1 = (v[0] + r * math.cos(a1), v[1] + r * math.sin(a1))
    attrs = {"data-dim": d["name"]}
    out = [Prim("path", [("M", *p0), ("A", r, 0, 1, *p1)], width=THIN, attrs=attrs)]
    out.append(_arrow(p0, (math.sin(a0), -math.cos(a0))))
    out.append(_arrow(p1, (-math.sin(a1), math.cos(a1))))
    mid = a0 + sweep / 2
    ang = _text_angle(-math.sin(mid), math.cos(mid))
    out += _dim_text_prims(d, label, ang, attrs)
    return out


def _balloon(b, res: dict) -> list:
    """QGIViewBalloon: a circle about the text (BubbleShape Circular), a leader with a kink to the origin, the end
    symbol there."""
    if b.source_view not in res["views"]:
        return []
    ox, oy = view_origin(res, b.source_view)
    sc = res["views"][b.source_view].get("scale", 1.0)
    at = (ox + b.x, oy - b.y)
    origin = (ox + b.origin_x * sc, oy - b.origin_y * sc)
    attrs = {"data-name": b.name}
    r = max(FONT_MM * 0.75, len(b.text) * FONT_MM * 0.33 + 1.0) * b.shape_scale
    out = []
    if b.bubble_shape != "None":
        out.append(Prim("path", [("M", at[0] + r, at[1]), ("A", r, 0, 1, at[0] - r, at[1]),
                                 ("A", r, 0, 1, at[0] + r, at[1]), ("Z",)], width=THIN, attrs=attrs))
    kink_dir = 1.0 if origin[0] >= at[0] else -1.0
    kink = (at[0] + kink_dir * (r + b.kink_length), at[1])
    start = (at[0] + kink_dir * r, at[1])
    out.append(Prim("path", [("M", *start), ("L", *kink), ("L", *origin)], width=THIN, attrs=attrs))
    if b.end_type == "Filled arrow":
        out.append(_arrow(origin, (origin[0] - kink[0], origin[1] - kink[1]), ARROW_MM * b.end_type_scale))
    out.append(Prim("text", at=(at[0], at[1] + FONT_MM * 0.35), size=FONT_MM, text=b.text, anchor="middle",
                    attrs=attrs))
    return out


def _annotation(a, res: dict) -> list:
    """QGIViewAnnotation: the lines centred on X, Y, LineSpace per cent of the text size apart."""
    h = res["height"]
    n = len(a.text)
    step = a.text_size * a.line_space / 100.0 * 1.2
    top = (h - a.y) - step * (n - 1) / 2.0
    out = []
    for i, line in enumerate(a.text):
        out.append(Prim("text", at=(a.x, top + i * step + a.text_size * 0.35), size=a.text_size, text=line,
                        anchor="middle", angle=a.rotation, attrs={"data-name": a.name}))
    return out


def _section_line(name: str, line: dict, res: dict) -> list:
    """QGISectionLine: a chain line across the base view with the arrows and SectionSymbol at its ends."""
    ox, oy = view_origin(res, line["view"])
    e0 = (ox + line["ends"][0][0], oy + line["ends"][0][1])
    e1 = (ox + line["ends"][1][0], oy + line["ends"][1][1])
    attrs = {"data-name": name}
    out = [Prim("path", [("M", *e0), ("L", *e1)], width=GRAPHIC, dash=CENTER_DASH, attrs=attrs)]
    n = line["normal"]
    for e in (e0, e1):
        tail = (e[0] + n[0] * 8.0, e[1] + n[1] * 8.0)
        out.append(Prim("path", [("M", *e), ("L", *tail)], width=THICK, attrs=attrs))
        out.append(_arrow(tail, n))
        if line.get("symbol"):
            out.append(Prim("text", at=(tail[0] + n[0] * 4.0, tail[1] + n[1] * 4.0 + FONT_MM * 0.35), size=FONT_MM,
                            text=line["symbol"], attrs=attrs))
    return out


def display(doc, frames: bool = False) -> list:
    """The page as primitives, in the order QGSPage stacks them: views, section faces, dimensions, balloons,
    annotations. With frames each view has its frame first (QGIView's border, which the page clicks select the view
    by; an export has none, as QGSPage::saveSvg hides them)."""
    from . import techdraw as T
    res = doc.result()
    out = []
    if frames:          # under every view's lines, so a click on a line finds the line
        for name, v in res["views"].items():
            if "edges" not in v:
                continue
            ox, oy = view_origin(res, name)
            x0, y0, x1, y1 = v["box"]
            m = 5.0                                     # QGIView's frame: a margin about the view's lines
            out.append(Prim("path", [("M", ox + x0 - m, oy + y0 - m), ("L", ox + x1 + m, oy + y0 - m), ("L", ox + x1 + m, oy + y1 + m),
                                     ("L", ox + x0 - m, oy + y1 + m), ("Z",)], width=0.18, dash=(1.0, 1.0), stroke="#c0c0c0",
                            fill="none", attrs={"data-view": name, "class": "td-frame"}))
    for name, v in res["views"].items():
        if "edges" not in v:
            continue
        ox, oy = view_origin(res, name)
        for loop_face in v.get("faces", []):
            segs = []
            for loop in loop_face["loops"]:
                if not loop:
                    continue
                segs.append(("M", ox + loop[0][0], oy + loop[0][1]))
                segs += [("L", ox + p[0], oy + p[1]) for p in loop[1:]]
                segs.append(("Z",))
            out.append(Prim("path", segs, width=0.0, fill="#D3D3D3", stroke="none", attrs={"data-view": name,
                                                                                         "class": "td-face"}))
        for i, e in enumerate(v["edges"]):
            hidden = not e["visible"]
            width = THIN if (hidden or e["cls"] in ("smooth", "seam", "iso")) else THICK
            out.append(Prim("path", _edge_segs(e, ox, oy), width=width, dash=HIDDEN_DASH if hidden else (),
                            attrs={"data-view": name, "data-sub": f"Edge{i}"}))
    for name, line in res.get("sections", {}).items():
        out += _section_line(name, line, res)
    for name, d in res["dimensions"].items():
        if d["view"] not in res["views"]:
            continue
        ox, oy = view_origin(res, d["view"])
        label = (ox + d["x"], oy - d["y"])
        dd = dict(d, name=name)
        if d["kind"] == "linear":
            out += _linear_dim(dd, ox, oy, label)
        elif d["kind"] == "arc":
            out += _arc_dim(dd, ox, oy, label)
        elif d["kind"] == "angle":
            out += _angle_dim(dd, ox, oy, label)
    for o in doc.objects:
        if isinstance(o, T.DrawViewBalloon):
            out += _balloon(o, res)
        elif isinstance(o, T.DrawViewAnnotation):
            out += _annotation(o, res)
    return out


# ─── SVG ─────────────────────────────────────────────────────────────────────────────────────────────────────

def _n(v: float) -> str:
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def _d(segs, k=REZ) -> str:
    out = []
    for s in segs:
        if s[0] == "Z":
            out.append("Z")
        elif s[0] == "A":
            r, large, sweep, x, y = s[1:]
            out.append(f"A{_n(r * k)},{_n(r * k)} 0 {large} {sweep} {_n(x * k)},{_n(y * k)}")
        else:
            out.append(f"{s[0]}{_n(s[1] * k)},{_n(s[2] * k)}")
    return " ".join(out)


def _esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def template_svg(name: str, texts: dict) -> str:
    """DrawSVGTemplate::processTemplate: the template with each editable text's tspan holding its value; the root
    <svg>'s children, for a group of their own."""
    from .techdraw import FREECAD_NS, SVG_NS, template_path
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("freecad", FREECAD_NS)
    for p, u in (("rdf", "http://www.w3.org/1999/02/22-rdf-syntax-ns#"), ("cc", "http://creativecommons.org/ns#"),
                 ("dc", "http://purl.org/dc/elements/1.1/"), ("svg", SVG_NS)):
        ET.register_namespace(p, u)
    root = ET.parse(template_path(name)).getroot()
    edit = f"{{{FREECAD_NS}}}editable"
    for t in root.iter(f"{{{SVG_NS}}}text"):
        key = t.get(edit)
        if key and key in texts:
            span = t.find(f"{{{SVG_NS}}}tspan")
            if span is not None:
                for c in list(span):
                    span.remove(c)
                span.text = texts[key]
    return "".join(ET.tostring(c, encoding="unicode") for c in root
                   if not c.tag.endswith("metadata"))


def prim_svg(p: Prim, k=REZ) -> str:
    attrs = "".join(f' {a}="{_esc(str(v))}"' for a, v in p.attrs.items())
    if p.kind == "text":
        anchor = f' text-anchor="{p.anchor}"' if p.anchor != "start" else ""
        rot = f' transform="rotate({_n(-p.angle)} {_n(p.at[0] * k)} {_n(p.at[1] * k)})"' if p.angle else ""
        return (f'<text x="{_n(p.at[0] * k)}" y="{_n(p.at[1] * k)}" font-family="{FONT}" font-size="{_n(p.size * k)}"'
                f'{anchor}{rot} fill="#000000"{attrs}>{_esc(p.text)}</text>')
    dash = f' stroke-dasharray="{",".join(_n(x * k) for x in p.dash)}"' if p.dash else ""
    fill = p.fill or "none"
    stroke = "none" if p.stroke == "none" else p.stroke
    width = f' stroke-width="{_n(p.width * k)}"' if stroke != "none" else ""
    return (f'<path d="{_d(p.segs, k)}" fill="{fill}" stroke="{stroke}"{width}{dash}'
            f' stroke-linecap="round" stroke-linejoin="round"{attrs}/>')


def page_svg(doc, interactive: bool = False) -> str:
    """QGSPage::saveSvg's file: width and height in mm, a viewBox in scene units, the template group scaled by
    Rez::guiX(1.0), the drawing in a group of its own. With interactive the page also carries data-* attributes
    for the workbench (they are always there; FreeCAD's export has none, which a reader ignores)."""
    res = doc.result()
    w, h = res["width"], res["height"]
    parts = [f'<?xml version="1.0" encoding="UTF-8"?>\n'
             f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:freecad="http://www.freecad.org/wiki/index.php?title=Svg_Namespace"'
             f' width="{_n(w)}mm" height="{_n(h)}mm" viewBox="0 0 {_n(w * REZ)} {_n(h * REZ)}" version="1.2">',
             f'<title>FreeCAD SVG Export</title><desc>Drawing page: {_esc(res["page"] or "")} exported from cad-agent '
             f'(FreeCAD TechDraw)</desc>',
             f'<g id="{_esc(res["page"] or "Page")}">']
    if res.get("template"):
        parts.append(f'<g id="{_esc(res["template"].split("/")[-1])}" style="stroke: none;" '
                     f'transform="scale({_n(REZ)}, {_n(REZ)})">{template_svg(res["template"], res["texts"])}</g>')
    parts.append('<g id="DrawingContent">')
    parts += [prim_svg(p) for p in display(doc, frames=interactive)]
    parts.append("</g></g></svg>\n")
    return "".join(parts)


# ─── DXF ─────────────────────────────────────────────────────────────────────────────────────────────────────

def page_dxf(doc) -> bytes:
    """TechDraw.writeDXFPage: each view's lines on a layer of its name (write1ViewDxf's compounds), an annotation's
    first line, each dimension's lines and text (module docstring)."""
    from . import dxf
    from . import techdraw as T
    from .techdraw_view import invert_geometry
    res = doc.result()
    w, h = res["width"], res["height"]
    layers, items = [], []
    for o in doc.page_views() + [x for x in doc.objects if isinstance(x, T.DrawProjGroupItem)
                                 and doc.group_of(x.name) is not None]:
        if isinstance(o, T.DrawViewPart) and o.name in doc.geo:
            geo = doc.geo[o.name]
            x, y = doc.pos[o.name]
            frame = dxf.frame_at(2, 0.0)
            layers.append(dxf.Layer(o.name))
            from build123d import Edge
            from .techdraw_view import COMPOUND, _edges_of
            # write1ViewDxf: the compounds as HLR gave them (not scrubbed), mirrored back to y up
            want = [("hard", True), ("outline", True)] + ([("smooth", True)] if o.smooth_visible else []) + \
                ([("seam", True)] if o.seam_visible else []) + \
                ([("hard", False), ("outline", False)] if o.hard_hidden else []) + ([("smooth", False)] if o.smooth_hidden else []) + \
                ([("seam", False)] if o.seam_hidden else [])
            for key in want:
                comp = geo.comps.get(COMPOUND[key])
                if comp is None or comp.IsNull():
                    continue
                for occ in _edges_of(invert_geometry(comp)):
                    try:
                        p = dxf.primitive(Edge(occ), frame)
                    except dxf.Unsupported:
                        continue
                    items.append((o.name, _moved(p, x, y)))
            # the cosmetic edges and centre lines (write1ViewDxf adds them moved, not mirrored, and the file has them
            # y up like the others: FreeCAD 26.3's headless writeDXFPage, tests/golden/techdraw)
            for e in geo.edges:
                if e.cls in ("cosmetic", "centerline"):
                    try:
                        p = dxf.primitive(Edge(invert_geometry(e.occ)), frame)
                    except dxf.Unsupported:
                        continue
                    items.append((o.name, _moved(p, x, y)))
        elif isinstance(o, T.DrawViewAnnotation):
            layers.append(dxf.Layer(o.name))
            items.append((o.name, ("text", (o.x, o.y), o.text_size, o.text[0] if o.text else "")))
    for name, d in res["dimensions"].items():
        layers.append(dxf.Layer(name))
        for p in display_of_dimension(doc, res, name, d):
            if p.kind == "text":
                items.append((name, ("text", (p.at[0], h - p.at[1]), p.size, p.text)))
            elif p.fill:
                pts = [(s[1], h - s[2]) for s in p.segs if s[0] in ("M", "L")]
                items.append((name, ("solid", pts)))
            else:
                pts = [(s[1], h - s[2]) for s in p.segs if s[0] in ("M", "L")]
                for a, b in zip(pts, pts[1:]):
                    items.append((name, dxf.Line(*sorted((dxf.snap2(a), dxf.snap2(b))))))
    seen, uniq = set(), []
    for L in layers:
        if L.name not in seen:
            seen.add(L.name)
            uniq.append(L)
    wr = dxf.DxfWriter(f"cad-agent TechDraw page {res['page']}: TechDraw.writeDXFPage as FreeCAD "
                       f"{dxf.FREECAD_COMMIT}; mm", (0.0, 0.0), (w, h), uniq)
    for layer, it in items:
        if isinstance(it, tuple) and it and it[0] == "text":
            wr.text(layer, it[1], it[2], _ascii(it[3]), 0.0, 1, 0)
        elif isinstance(it, tuple) and it and it[0] == "solid":
            wr.solid(layer, it[1][:4])
        else:
            wr.entity(it, layer)
    return wr.finish()


def _ascii(t: str) -> str:
    return t.replace("⌀", "%%c").replace("±", "%%p").replace("°", "%%d").encode("ascii", "replace").decode()


def display_of_dimension(doc, res, name, d):
    ox, oy = view_origin(res, d["view"])
    label = (ox + d["x"], oy - d["y"])
    dd = dict(d, name=name)
    if d["kind"] == "linear":
        return _linear_dim(dd, ox, oy, label)
    if d["kind"] == "arc":
        return _arc_dim(dd, ox, oy, label)
    return _angle_dim(dd, ox, oy, label)


def _moved(p, dx, dy):
    """A dxf.py primitive moved by (dx, dy)."""
    from . import dxf
    m = lambda q: (q[0] + dx, q[1] + dy)  # noqa: E731
    t = type(p)
    if t is dxf.Line:
        return dxf.Line(m(p.a), m(p.b))
    if t is dxf.Circle:
        return dxf.Circle(m(p.c), p.r)
    if t is dxf.Arc:
        return dxf.Arc(m(p.c), p.r, p.a0, p.a1)
    if t is dxf.Ellipse:
        return dxf.Ellipse(m(p.c), p.major, p.ratio, p.t0, p.t1)
    if t is dxf.Spline:
        return dxf.Spline(p.degree, p.knots, tuple(m(q) for q in p.poles))
    if t is dxf.Poly:
        return dxf.Poly(tuple(m(q) for q in p.points), p.closed)
    return p


# ─── PDF ─────────────────────────────────────────────────────────────────────────────────────────────────────

PT = 72.0 / 25.4


def _arc_beziers(x0, y0, r, large, sweep, x1, y1):
    """An SVG arc (circular, x-axis rotation 0) as cubic Beziers: [(c1, c2, end), ...]."""
    if r <= 0 or (x0 == x1 and y0 == y1):
        return []
    dx, dy = (x0 - x1) / 2.0, (y0 - y1) / 2.0
    d2 = dx * dx + dy * dy
    r = max(r, math.sqrt(d2))
    sign = -1.0 if large == sweep else 1.0
    f = sign * math.sqrt(max(0.0, (r * r - d2) / d2)) if d2 else 0.0
    cx, cy = f * dy + (x0 + x1) / 2.0, -f * dx + (y0 + y1) / 2.0
    a0 = math.atan2(y0 - cy, x0 - cx)
    a1 = math.atan2(y1 - cy, x1 - cx)
    da = a1 - a0
    if sweep and da < 0:
        da += 2 * math.pi
    elif not sweep and da > 0:
        da -= 2 * math.pi
    n = max(1, int(math.ceil(abs(da) / (math.pi / 2) - 1e-9)))
    out = []
    step = da / n
    k = 4.0 / 3.0 * math.tan(step / 4.0)
    a = a0
    for _ in range(n):
        b = a + step
        p0 = (cx + r * math.cos(a), cy + r * math.sin(a))
        p3 = (cx + r * math.cos(b), cy + r * math.sin(b))
        c1 = (p0[0] - k * r * math.sin(a), p0[1] + k * r * math.cos(a))
        c2 = (p3[0] + k * r * math.sin(b), p3[1] - k * r * math.cos(b))
        out.append((c1, c2, p3))
        a = b
    return out


def _pdf_str(t: str) -> str:
    t = t.replace("⌀", "\xd8").replace("°", "\xb0").replace("±", "\xb1")
    b = t.encode("latin-1", "replace").decode("latin-1")
    return b.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class _Pdf:
    def __init__(self, h_mm):
        self.h = h_mm
        self.ops: list[str] = []

    def P(self, x, y):
        return f"{x * PT:.3f} {(self.h - y) * PT:.3f}"

    def prim(self, p: Prim, m=None):
        T = (lambda x, y: (x, y)) if m is None else (lambda x, y: (m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]))
        sc = 1.0 if m is None else math.sqrt(abs(m[0] * m[3] - m[1] * m[2]))
        if p.kind == "text":
            x, y = T(*p.at)
            size = p.size * sc * PT
            w = len(p.text) * size * 0.5
            dx = {"start": 0.0, "middle": -w / 2.0, "end": -w}[p.anchor]
            a = math.radians(p.angle)
            c, s = math.cos(a), math.sin(a)
            px, py = x * PT, (self.h - y) * PT
            self.ops.append(f"BT /F1 {size:.3f} Tf {c:.6f} {s:.6f} {-s:.6f} {c:.6f} {px + dx * c:.3f} "
                            f"{py + dx * s:.3f} Tm ({_pdf_str(p.text)}) Tj ET")
            return
        out = []
        cur = (0.0, 0.0)
        start = cur
        for sg in p.segs:
            if sg[0] == "M":
                cur = start = T(sg[1], sg[2])
                out.append(f"{self.P(*cur)} m")
            elif sg[0] == "L":
                cur = T(sg[1], sg[2])
                out.append(f"{self.P(*cur)} l")
            elif sg[0] == "C":
                c1, c2, e = T(sg[1], sg[2]), T(sg[3], sg[4]), T(sg[5], sg[6])
                out.append(f"{self.P(*c1)} {self.P(*c2)} {self.P(*e)} c")
                cur = e
            elif sg[0] == "A":
                r, large, sweep, x, y = sg[1:]
                e = T(x, y)
                for c1, c2, q in _arc_beziers(cur[0], cur[1], r * sc, large, sweep, e[0], e[1]):
                    out.append(f"{self.P(*c1)} {self.P(*c2)} {self.P(*q)} c")
                cur = e
            elif sg[0] == "Z":
                out.append("h")
                cur = start
        if not out:
            return
        if p.fill and p.fill != "none":
            r, g, b = (int(p.fill[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
            self.ops.append(f"{r:.3f} {g:.3f} {b:.3f} rg " + " ".join(out) + " f 0 0 0 rg")
        if p.stroke != "none":
            dash = "[" + " ".join(f"{d * PT:.3f}" for d in p.dash) + "] 0 d" if p.dash else "[] 0 d"
            self.ops.append(f"{max(p.width * sc, 0.1) * PT:.3f} w {dash} 1 J 1 j " + " ".join(out) + " S")


def _svg_path_segs(d: str) -> list:
    """An SVG path's d (M L H V C Z, either case) as absolute segments."""
    toks = re.findall(r"[MmLlHhVvCcZzAaSsQqTt]|-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", d)
    out, i, cmd = [], 0, None
    x = y = sx = sy = 0.0

    def num():
        nonlocal i
        v = float(toks[i])
        i += 1
        return v
    while i < len(toks):
        t = toks[i]
        if re.match(r"[A-Za-z]", t):
            cmd = t
            i += 1
            if cmd in "Zz":
                out.append(("Z",))
                x, y = sx, sy
                continue
        if cmd is None:
            i += 1
            continue
        rel = cmd.islower()
        c = cmd.upper()
        if c == "M":
            nx, ny = num(), num()
            x, y = (x + nx, y + ny) if rel else (nx, ny)
            sx, sy = x, y
            out.append(("M", x, y))
            cmd = "l" if rel else "L"
        elif c == "L":
            nx, ny = num(), num()
            x, y = (x + nx, y + ny) if rel else (nx, ny)
            out.append(("L", x, y))
        elif c == "H":
            nx = num()
            x = x + nx if rel else nx
            out.append(("L", x, y))
        elif c == "V":
            ny = num()
            y = y + ny if rel else ny
            out.append(("L", x, y))
        elif c == "C":
            v = [num() for _ in range(6)]
            if rel:
                v = [v[0] + x, v[1] + y, v[2] + x, v[3] + y, v[4] + x, v[5] + y]
            out.append(("C", *v))
            x, y = v[4], v[5]
        elif c == "A":
            rx, ry, rot, large, sweep, nx, ny = (num() for _ in range(7))
            x, y = (x + nx, y + ny) if rel else (nx, ny)
            out.append(("A", rx, int(large), int(sweep), x, y))
        else:
            i += 1
    return out


def _matrix(tf: str):
    m = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
    for name, args in re.findall(r"(matrix|translate|scale)\s*\(([^)]*)\)", tf or ""):
        a = [float(v) for v in re.split(r"[\s,]+", args.strip()) if v]
        if name == "matrix":
            n = a
        elif name == "translate":
            n = [1, 0, 0, 1, a[0], a[1] if len(a) > 1 else 0.0]
        else:
            n = [a[0], 0, 0, a[1] if len(a) > 1 else a[0], 0, 0]
        m = [m[0] * n[0] + m[2] * n[1], m[1] * n[0] + m[3] * n[1], m[0] * n[2] + m[2] * n[3],
             m[1] * n[2] + m[3] * n[3], m[0] * n[4] + m[2] * n[5] + m[4], m[1] * n[4] + m[3] * n[5] + m[5]]
    return m


def _mul(a, b):
    return [a[0] * b[0] + a[2] * b[1], a[1] * b[0] + a[3] * b[1], a[0] * b[2] + a[2] * b[3],
            a[1] * b[2] + a[3] * b[3], a[0] * b[4] + a[2] * b[5] + a[4], a[1] * b[4] + a[3] * b[5] + a[5]]


def _style(el, key, default=None):
    v = el.get(key)
    if v is None:
        m = re.search(rf"(?:^|;)\s*{re.escape(key)}\s*:\s*([^;]+)", el.get("style", ""))
        v = m.group(1).strip() if m else None
    return default if v is None else v


def template_prims(name: str, texts: dict):
    """The template drawn for the PDF: its paths, rects, circles, lines and texts (the subset FreeCAD's templates
    use), each with its transform."""
    from .techdraw import FREECAD_NS, SVG_NS, template_path
    root = ET.parse(template_path(name)).getroot()
    out = []

    def walk(el, m, inherited):
        tag = el.tag.split("}")[-1]
        m = _mul(m, _matrix(el.get("transform")))
        st = dict(inherited)
        for k in ("stroke", "stroke-width", "fill", "font-size", "text-anchor"):
            v = _style(el, k)
            if v is not None:
                st[k] = v
        width = float(re.sub(r"[a-z]+", "", st.get("stroke-width", "0.35")) or 0.35)
        stroke = st.get("stroke", "none")
        fill = st.get("fill", "#000000")
        if tag == "path" and el.get("d"):
            out.append((Prim("path", _svg_path_segs(el.get("d")), width=width, stroke="none" if stroke == "none" else "#000000",
                             fill=None if fill in ("none", None) else "#000000"), m))
        elif tag == "rect":
            x, y = float(el.get("x", 0)), float(el.get("y", 0))
            w, h = float(el.get("width", 0)), float(el.get("height", 0))
            out.append((Prim("path", [("M", x, y), ("L", x + w, y), ("L", x + w, y + h), ("L", x, y + h), ("Z",)],
                             width=width, stroke="none" if stroke == "none" else "#000000",
                             fill=None if fill in ("none", None) else "#000000"), m))
        elif tag == "circle":
            cx, cy, r = float(el.get("cx", 0)), float(el.get("cy", 0)), float(el.get("r", 0))
            out.append((Prim("path", [("M", cx + r, cy), ("A", r, 0, 1, cx - r, cy), ("A", r, 0, 1, cx + r, cy), ("Z",)],
                             width=width, stroke="none" if stroke == "none" else "#000000",
                             fill=None if fill in ("none", None) else "#000000"), m))
        elif tag == "line":
            out.append((Prim("path", [("M", float(el.get("x1", 0)), float(el.get("y1", 0))),
                                      ("L", float(el.get("x2", 0)), float(el.get("y2", 0)))], width=width), m))
        elif tag == "text":
            key = el.get(f"{{{FREECAD_NS}}}editable")
            spans = el.findall(f"{{{SVG_NS}}}tspan") or [el]
            for span in spans:
                value = texts.get(key) if key else None
                value = value if value is not None else "".join(span.itertext())
                x = float(span.get("x", el.get("x", 0)) or 0)
                y = float(span.get("y", el.get("y", 0)) or 0)
                size = _style(span, "font-size") or st.get("font-size", "3.5")
                size = float(re.sub(r"[a-z]+", "", size) or 3.5)
                anchor = _style(span, "text-anchor") or st.get("text-anchor", "start")
                if value.strip():
                    out.append((Prim("text", at=(x, y), size=size, text=value, anchor=anchor if anchor in
                                     ("start", "middle", "end") else "start"), m))
            return
        for c in el:
            walk(c, m, st)
    walk(root, [1.0, 0.0, 0.0, 1.0, 0.0, 0.0], {})
    return out


def page_pdf(doc) -> bytes:
    """PagePrinter::printPdf: one page of the template's size, the template drawn, the page over it; PDF 1.4 by
    hand (standard Helvetica, vector, uncompressed), the same bytes for the same page."""
    res = doc.result()
    w, h = res["width"], res["height"]
    pdf = _Pdf(h)
    if res.get("template"):
        for p, m in template_prims(res["template"], res["texts"]):
            pdf.prim(p, m)
    for p in display(doc):
        pdf.prim(p)
    content = "\n".join(pdf.ops).encode("latin-1", "replace")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w * PT:.3f} {h * PT:.3f}] "
             f"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>").encode(),
            b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            f"<< /Title ({_pdf_str(res['page'] or 'Page')}) /Creator (cad-agent TechDraw) >>".encode()]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R /Info {len(objs)} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def export(doc, fmt: str):
    if fmt == "svg":
        return page_svg(doc)
    if fmt == "dxf":
        return page_dxf(doc)
    if fmt == "pdf":
        return page_pdf(doc)
    raise ValueError(fmt)

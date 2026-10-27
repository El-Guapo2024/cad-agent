# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses FreeCAD's TechDraw document objects and keeps FreeCAD's licence, the GNU Lesser
# General Public License, version 2.1 or (at your option) any later version; the text is in ../ui/LICENSE.
#
#   Derived from: src/Mod/TechDraw/App/DrawLeaderLine.cpp (Copyright (c) 2019 WandererFan),
#                 src/Mod/TechDraw/App/DrawRichAnno.cpp (Copyright (c) 2019 WandererFan),
#                 src/Mod/TechDraw/App/DrawViewSymbol.cpp (Copyright (c) 2002 Jürgen Riegel, 2013 Luke Parry),
#                 src/Mod/TechDraw/App/DrawWeldSymbol.cpp (Copyright (c) 2019 WandererFan),
#                 src/Mod/TechDraw/App/DrawTile.cpp, DrawTileWeld.cpp (Copyright (c) 2019 WandererFan),
#                 src/Mod/TechDraw/App/DrawViewImage.cpp (Copyright (c) 2002 Jürgen Riegel, 2013 Luke Parry),
#                 src/Mod/TechDraw/App/DrawViewClip.cpp (Copyright (c) 2002 Jürgen Riegel, 2013 Luke Parry),
#                 src/Mod/TechDraw/Gui/ViewProviderLeader.cpp, ViewProviderRichAnno.cpp, ViewProviderWeld.cpp,
#                 ViewProviderSymbol.cpp, ViewProviderImage.cpp, ViewProviderViewClip.cpp (Copyright (c) 2019 WandererFan)
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
"""The TechDraw objects of the annotation, symbol and image tools: DrawLeaderLine, DrawRichAnno, DrawViewSymbol,
DrawWeldSymbol, DrawTileWeld, DrawViewImage and DrawViewClip, as page entries (cad_agent/techdraw.py registers them).

Properties are FreeCAD's, in snake_case, with FreeCAD's defaults left out of the page file. The properties of the objects'
view providers (a leader's colour, line width and style; a weld symbol's font ...) are held beside the object's, as the
hatches' are. Nothing drawn is stored; the page recompute (techdraw_more.py) gives each its geometry.

    TechDraw.DrawLeaderLine("LeaderLine", leader_parent="View", x=12.0, y=-3.0, way_points=[(0.0, 0.0, 0.0), (10.0, -8.0, 0.0)])
    TechDraw.DrawRichAnno("RichTextAnnotation", anno_text="<html>...</html>", x=40.0, y=30.0)
    TechDraw.DrawViewSymbol("Symbol", symbol="<svg ...>", owner="View", x=60.0, y=40.0)
    TechDraw.DrawTileWeld("TileWeld", tile_parent="WeldSymbol", symbol_file="Welding/AWS/filletDown.svg", left_text="3")
    TechDraw.DrawTileWeld("TileWeld001", tile_parent="WeldSymbol", tile_row=-1)
    TechDraw.DrawWeldSymbol("WeldSymbol", leader="LeaderLine", all_around=True, tail_text="T")
    TechDraw.DrawViewImage("Image", image_file="images/logo.png", x=50.0, y=50.0)
    TechDraw.DrawViewClip("Clip", width=80.0, height=60.0, views=["View"], x=100.0, y=100.0)

This module imports without OCP.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from . import techdraw as T

SYMBOLS_DIR = Path(__file__).resolve().parent / "techdraw_symbols"
LINE_STYLES = ("NoLine", "Continuous", "Dash", "Dot", "DashDot", "DashDotDot")
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp")


def symbol_path(name: str) -> Path:
    """A symbol file by its path under FreeCAD's Mod/TechDraw/Symbols ("Welding/AWS/filletDown.svg")."""
    p = (SYMBOLS_DIR / name).resolve()
    if SYMBOLS_DIR.resolve() not in p.parents or not p.is_file():
        raise T.TechDrawError(f"{name!r} is not a symbol file the app has (cad_agent/techdraw_symbols)")
    return p


def symbol_files() -> list[str]:
    """Every symbol file shipped, as paths under Symbols (the folders in FreeCAD's order: sorted by path)."""
    return sorted(str(p.relative_to(SYMBOLS_DIR)) for p in SYMBOLS_DIR.rglob("*.svg"))


class _More(T.TDObject):
    """What these objects share: vectors lists, colours, links."""
    COLORS: tuple = ()

    def normalize(self, key, v):
        if key == "way_points":
            out = []
            for p in v or ():
                if not (isinstance(p, (list, tuple)) and len(p) in (2, 3)):
                    raise T.TechDrawError(f"{self.name}.way_points: {p!r} is not a point (x, y, z)")
                out.append(tuple(float(c) for c in p) + ((0.0,) if len(p) == 2 else ()))
            return tuple(out)
        if key in self.COLORS:
            c = tuple(float(x) for x in v)
            if len(c) == 3:
                c += (1.0,)
            if len(c) != 4:
                raise T.TechDrawError(f"{self.name}.{key}: {v!r} is not a colour (r, g, b)")
            return c
        if key == "views":
            if isinstance(v, str):
                v = [v]
            return tuple(v or ())
        return super().normalize(key, v)

    def source_value(self, key, v=None):
        v = getattr(self, key) if v is None else v
        if key == "way_points":
            return [tuple(p) for p in v]
        if key in self.COLORS:
            return list(v)
        return super().source_value(key, v)


class DrawLeaderLine(_More):
    """TechDraw::DrawLeaderLine: WayPoints are displacements from the first, in page mm, unscaled and unrotated, the y axis
    down (FreeCAD stores them inverted); X, Y the first point's place relative to the parent's origin, unscaled and
    unrotated, y up. TaskLeaderLine makes one (Create Leader); its panel's colour, weight and style are the view provider's."""
    kind = "DrawLeaderLine"
    TYPE_ID = "TechDraw::DrawLeaderLine"
    DEFAULTS = {"leader_parent": None, "way_points": ((0.0, 0.0, 0.0),), "start_symbol": "Filled arrow", "end_symbol": "None",
                "scalable": False, "auto_horizontal": True, "rotates_with_parent": True, "x": 0.0, "y": 0.0,
                "lock_position": True, "label": None,
                "color": (0.0, 0.0, 0.0, 1.0), "line_width": 0.5, "line_style": "Continuous", "use_old_coords": False}
    REFS = ("leader_parent",)
    COLORS = ("color",)
    ENUMS = {"start_symbol": T.END_TYPES, "end_symbol": T.END_TYPES, "line_style": LINE_STYLES}
    PROP_NAMES = {"x": "X", "y": "Y"}
    TRANSACTION = "Create Leader"


class DrawRichAnno(_More):
    """TechDraw::DrawRichAnno: AnnoText is the HTML QTextDocument::toHtml gives (the Rich Text Creator's text)."""
    kind = "DrawRichAnno"
    TYPE_ID = "TechDraw::DrawRichAnno"
    DEFAULTS = {"anno_parent": None, "anno_text": "", "show_frame": True, "origin_centered": False, "max_width": -1.0,
                "x": 0.0, "y": 0.0, "rotation": 0.0, "lock_position": False, "label": None,
                "line_color": (0.0, 0.0, 0.0, 1.0), "line_width": 0.5, "line_style": "Continuous"}
    REFS = ("anno_parent",)
    COLORS = ("line_color",)
    ENUMS = {"line_style": LINE_STYLES}
    PROP_NAMES = {"x": "X", "y": "Y"}
    TRANSACTION = "Create Annotation"


NS_SVG = "http://www.w3.org/2000/svg"
NS_FC = T.FREECAD_NS


def _editable_spans(dom):
    """//text[@freecad:editable]/tspan of DrawViewSymbol, in document order: the attribute by its qualified name, the elements by
    their local names (FreeCAD's symbols use both http: and https: for the namespace)."""
    from xml.dom import Node
    for t in dom.getElementsByTagName("*"):
        if t.localName != "text" or not t.hasAttribute("freecad:editable"):
            continue
        for c in t.childNodes:
            if c.nodeType == Node.ELEMENT_NODE and c.localName == "tspan":
                yield c


def editable_fields(svg: str) -> list[str]:
    """DrawViewSymbol::getEditableFields: the text of each tspan of a text that has freecad:editable."""
    from xml.dom import minidom
    if not svg:
        return []
    try:
        dom = minidom.parseString(svg.encode("utf-8"))
    except Exception:
        return []
    out = []
    for span in _editable_spans(dom):
        first = span.firstChild
        out.append(first.nodeValue if first is not None and first.nodeValue is not None else "")
    return out


def _qdom_text(t: str, attr: bool = False) -> str:
    """QDom's encodeText: & and < always, " in an attribute, > only after ]], and the control characters of a value."""
    t = t.replace("&", "&amp;").replace("<", "&lt;")
    if attr:
        t = t.replace('"', "&quot;").replace("\t", "&#x9;").replace("\n", "&#xa;").replace("\r", "&#xd;")
    else:
        t = t.replace("]]>", "]]&gt;").replace("\r", "&#xd;")
    return t


def qdom_string(doc, indent: int = 1, decl: str = "version='1.0' encoding='UTF-8'") -> str:
    """QDomDocument::toString(indent) of a document parsed with xml.dom.minidom: the XML declaration, a node per line with
    `indent` spaces a level, attributes in name order, an element holding only text kept on one line."""
    from xml.dom import Node
    out: list[str] = []

    def kids(n):
        return [c for c in n.childNodes if not (c.nodeType == Node.TEXT_NODE and not c.data.strip())]

    def save(n, depth, prev, nxt):
        pad = " " * (depth * indent if indent >= 1 else 0)
        t = n.nodeType
        if t == Node.ELEMENT_NODE:
            if not (prev is not None and prev.nodeType == Node.TEXT_NODE):
                out.append(pad)
            attrs = sorted((a.name, a.value) for a in n.attributes.values())
            out.append("<" + n.tagName + "".join(f' {k}="{_qdom_text(v, True)}"' for k, v in attrs))
            ch = kids(n)
            if ch:
                out.append(">")
                if ch[0].nodeType != Node.TEXT_NODE:
                    out.append("\n")
                for i, c in enumerate(ch):
                    save(c, depth + 1, ch[i - 1] if i else None, ch[i + 1] if i + 1 < len(ch) else None)
                if ch[-1].nodeType != Node.TEXT_NODE:
                    out.append(pad)
                out.append("</" + n.tagName + ">")
            else:
                out.append("/>")
            if not (nxt is not None and nxt.nodeType == Node.TEXT_NODE):
                out.append("\n")
        elif t == Node.TEXT_NODE:
            out.append(_qdom_text(n.data))
        elif t == Node.CDATA_SECTION_NODE:
            out.append("<![CDATA[" + n.data + "]]>")
        elif t == Node.COMMENT_NODE:
            out.append(pad + "<!--" + n.data + "-->\n")
        elif t == Node.PROCESSING_INSTRUCTION_NODE:
            out.append(pad + "<?" + n.target + " " + n.data + "?>\n")
    out.append(f"<?xml {decl}?>\n")
    top = [c for c in doc.childNodes if c.nodeType != Node.DOCUMENT_TYPE_NODE]
    for i, c in enumerate(top):
        save(c, 0, top[i - 1] if i else None, top[i + 1] if i + 1 < len(top) else None)
    return "".join(out)


def with_editable_texts(svg: str, texts) -> str:
    """DrawViewSymbol::updateFieldsInSymbol: the text of each editable text's tspans replaced in order, the document written
    as QDom writes it."""
    from xml.dom import minidom, Node
    if not texts or not svg:
        return svg
    try:
        dom = minidom.parseString(svg.encode("utf-8"))
    except Exception:
        return svg
    count = 0
    for span in list(_editable_spans(dom)):
        if count >= len(texts):
            break
        span.setAttribute("xml:space", "preserve")
        while span.lastChild is not None:
            span.removeChild(span.lastChild)
        span.appendChild(dom.createTextNode(texts[count]))
        count += 1
    m = re.match(r"\s*<\?xml\s+([^?]*)\?>", svg)
    decl = "version='1.0' encoding='UTF-8'"
    if m:
        v = re.search(r"version\s*=\s*[\"']([^\"']*)", m.group(1))
        e = re.search(r"encoding\s*=\s*[\"']([^\"']*)", m.group(1))
        sa = re.search(r"standalone\s*=\s*[\"']([^\"']*)", m.group(1))
        decl = f"version='{v.group(1) if v else '1.0'}'" + (f" encoding='{e.group(1)}'" if e else "") + (f" standalone='{sa.group(1)}'" if sa else "")
    return qdom_string(dom, 1, decl)


class DrawViewSymbol(_More):
    """TechDraw::DrawViewSymbol: Symbol is the SVG text itself (the file read by TechDraw_Symbol)."""
    kind = "DrawViewSymbol"
    TYPE_ID = "TechDraw::DrawViewSymbol"
    DEFAULTS = {"symbol": "", "owner": None, "scale": 1.0, "scale_type": "Custom", "rotation": 0.0, "x": 0.0, "y": 0.0,
                "lock_position": False, "caption": "", "label": None, "legacy_scaling": False, "stack_order": 0}
    REFS = ("owner",)
    ENUMS = {"scale_type": T.SCALE_TYPES}
    PROP_NAMES = {"x": "X", "y": "Y"}
    TRANSACTION = "Create Symbol"

    @property
    def editable_texts(self) -> list[str]:
        return editable_fields(self.symbol)


class DrawWeldSymbol(_More):
    """TechDraw::DrawWeldSymbol: always two DrawTileWeld children (the arrow side, TileRow 0, and the other side, -1)."""
    kind = "DrawWeldSymbol"
    TYPE_ID = "TechDraw::DrawWeldSymbol"
    DEFAULTS = {"leader": None, "all_around": False, "field_weld": False, "alternating_weld": False, "tail_text": "",
                "x": 0.0, "y": 0.0, "lock_position": False, "label": None,
                "font": "osifont", "font_size": 5.0, "tile_font_size": 3.75}
    REFS = ("leader",)
    PROP_NAMES = {"x": "X", "y": "Y"}
    TRANSACTION = "Create Weld Symbol"


BLANK_TILE = "Welding/blankTile.svg"


class DrawTileWeld(_More):
    """TechDraw::DrawTileWeld: a tile of a weld symbol; SymbolFile is a path under FreeCAD's Mod/TechDraw/Symbols (the
    default Welding/blankTile.svg), whose text FreeCAD embeds as SymbolIncluded."""
    kind = "DrawTileWeld"
    TYPE_ID = "TechDraw::DrawTileWeld"
    DEFAULTS = {"tile_parent": None, "tile_row": 0, "tile_column": 0, "left_text": "", "right_text": "", "center_text": "",
                "symbol_file": BLANK_TILE, "label": None}
    REFS = ("tile_parent",)
    TRANSACTION = "Create Weld Symbol"

    def validate(self):
        if self.tile_row not in (-1, 0):
            raise T.TechDrawError(f"{self.name}.TileRow: {self.tile_row!r} is not -1 (other side) or 0 (arrow side)")
        if self.symbol_file:
            symbol_path(self.symbol_file)


class DrawViewImage(_More):
    """TechDraw::DrawViewImage: ImageFile is a bitmap of the project (a path under the project's folder)."""
    kind = "DrawViewImage"
    TYPE_ID = "TechDraw::DrawViewImage"
    DEFAULTS = {"image_file": "", "width": 100.0, "height": 100.0, "owner": None, "scale": 1.0, "scale_type": "Custom",
                "rotation": 0.0, "x": 0.0, "y": 0.0, "lock_position": False, "caption": "", "label": None, "crop": False}
    REFS = ("owner",)
    ENUMS = {"scale_type": T.SCALE_TYPES}
    PROP_NAMES = {"x": "X", "y": "Y"}
    TRANSACTION = "Create Image"

    def validate(self):
        f = self.image_file
        if f and (f.startswith("/") or ".." in Path(f).parts or Path(f).suffix.lower() not in IMAGE_EXTENSIONS):
            raise T.TechDrawError(f"{self.name}.ImageFile: {f!r} is not a bitmap (png, jpg, jpeg, bmp) in the project")


class DrawViewClip(_More):
    """TechDraw::DrawViewClip: a frame of Width x Height, centred on X, Y, that clips the views in Views (their X, Y are
    relative to the clip's centre)."""
    kind = "DrawViewClip"
    TYPE_ID = "TechDraw::DrawViewClip"
    DEFAULTS = {"width": 100.0, "height": 100.0, "show_frame": False, "views": (), "x": 0.0, "y": 0.0, "rotation": 0.0,
                "lock_position": False, "caption": "", "label": None, "clip_children": True}
    REFS = ("views",)
    PROP_NAMES = {"x": "X", "y": "Y"}
    TRANSACTION = "Create clip"


NEW_CLASSES = (DrawLeaderLine, DrawRichAnno, DrawViewSymbol, DrawWeldSymbol, DrawTileWeld, DrawViewImage, DrawViewClip)
# the objects DrawPage.Views holds: every one but a tile
PAGE_VIEW_KINDS = ("DrawLeaderLine", "DrawRichAnno", "DrawViewSymbol", "DrawWeldSymbol", "DrawViewImage", "DrawViewClip")
# the link that makes an object another's child in the tree (DrawView::getOwnerProperty)
OWNER_KEYS = {"DrawLeaderLine": "leader_parent", "DrawRichAnno": "anno_parent", "DrawViewSymbol": "owner",
              "DrawViewImage": "owner", "DrawWeldSymbol": "leader", "DrawTileWeld": "tile_parent"}


def owner_of(o) -> str | None:
    k = OWNER_KEYS.get(o.kind)
    return getattr(o, k) if k else None


T.CLASSES.update({c.kind: c for c in NEW_CLASSES})

# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses FreeCAD's TechDraw document objects and keeps FreeCAD's licence, the GNU Lesser
# General Public License, version 2.1 or (at your option) any later version; the text is in ../ui/LICENSE.
#
#   Derived from: src/Mod/TechDraw/App/DrawPage.cpp (Copyright (c) 2002 Jürgen Riegel),
#                 src/Mod/TechDraw/App/DrawSVGTemplate.cpp (Copyright (c) 2002 Jürgen Riegel, 2014 Luke Parry),
#                 src/Mod/TechDraw/App/DrawTemplate.cpp (Copyright (c) 2014 Luke Parry),
#                 src/Mod/TechDraw/App/DrawView.cpp (Copyright (c) 2002 Jürgen Riegel),
#                 src/Mod/TechDraw/App/DrawViewPart.cpp (Copyright (c) 2002 Jürgen Riegel, 2013 Luke Parry, 2016 WandererFan),
#                 src/Mod/TechDraw/App/DrawProjGroup.cpp (Copyright (c) 2014 Joe Dowsett),
#                 src/Mod/TechDraw/App/DrawProjGroupItem.cpp (Copyright (c) 2014 Luke Parry),
#                 src/Mod/TechDraw/App/DrawViewSection.cpp (Copyright (c) 2002 Jürgen Riegel, 2013 Luke Parry),
#                 src/Mod/TechDraw/App/DrawViewDimension.cpp (Copyright (c) 2013 Luke Parry),
#                 src/Mod/TechDraw/App/DrawViewBalloon.cpp (Copyright (c) 2013 Luke Parry),
#                 src/Mod/TechDraw/App/DrawViewAnnotation.cpp (Copyright (c) 2012 Yorik van Havre, 2013 Luke Parry),
#                 src/Mod/TechDraw/App/DrawUtil.cpp (Copyright (c) 2015 WandererFan),
#                 src/Mod/TechDraw/App/Preferences.cpp (Copyright (c) 2020 WandererFan)
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
"""A TechDraw page of a project: techdraw/<Page>.py's PAGE list (docs/EDITING_PLAN.md, "TechDraw pages in a project").

Each entry is one of FreeCAD's TechDraw document objects as a feature_kw.KwFeature: DrawPage, DrawSVGTemplate,
DrawProjGroupItem (TechDraw_View makes one, named View), DrawViewPart, DrawProjGroup, DrawViewSection,
DrawViewDimension, DrawViewBalloon, DrawViewAnnotation. Their keywords are FreeCAD's properties in snake_case, with
the defaults a fresh profile gives them (Preferences > TechDraw) left out.

PageDocument(objects, shape_of, title).recompute() is what FreeCAD's recompute of the page does: each view's
geometry (techdraw_view.py), a projection group's items placed (AutoDistribute), a section's cut, each dimension's
measure and text (techdraw_dim.py), the scales a ScaleType asks for; .result() is that as JSON for the page, the
CLI and the goldens. This module imports without OCP; the recompute loads it.
"""
from __future__ import annotations

import datetime
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from . import feature_kw as KW

FREECAD_COMMIT = "3160daf1e2b6"
TEMPLATES_DIR = Path(__file__).resolve().parent / "techdraw_templates"
DEFAULT_TEMPLATE = "Default_Template_A4_Landscape.svg"     # Preferences::defaultTemplate()
TEMPLATES = ("Default_Template_A4_Landscape.svg", "ISO/A4_Landscape_TD.svg", "ISO/A3_Landscape_TD.svg",
             "ISO/A4_Landscape_ISO5457_minimal.svg", "ISO/A3_Landscape_ISO5457_minimal.svg",
             "ISO/A4_Portrait_ISO5457_minimal.svg")
FREECAD_NS = "http://www.freecad.org/wiki/index.php?title=Svg_Namespace"
SVG_NS = "http://www.w3.org/2000/svg"

PROJECTION_TYPES = ("First angle", "Third angle")
GROUP_PROJECTION_TYPES = ("First angle", "Third angle", "Default")
SCALE_TYPES = ("Page", "Automatic", "Custom")
CAPTION_SNAP = ("Top", "Bottom", "Left", "Right", "NoSnap")
ITEM_TYPES = ("Front", "Left", "Right", "Rear", "Top", "Bottom", "FrontTopLeft", "FrontTopRight", "FrontBottomLeft",
              "FrontBottomRight")
SECTION_DIRECTIONS = ("Right", "Left", "Up", "Down", "Aligned")
CUT_SURFACE = ("Hide", "Color", "SvgHatch", "PatHatch")
DIM_TYPES = ("Distance", "DistanceX", "DistanceY", "DistanceZ", "Radius", "Diameter", "Angle", "Angle3Pt", "Area")
MEASURE_TYPES = ("True", "Projected")
BUBBLE_SHAPES = ("Circular", "None", "Triangle", "Inspection", "Hexagon", "Square", "Rectangle", "Line")
END_TYPES = ("Filled arrow", "Open arrow", "Tick", "Dot", "Open circle", "Fork", "Filled triangle", "None")
TEXT_STYLES = ("Normal", "Bold", "Italic", "Bold-Italic")


class TechDrawError(ValueError):
    pass


# ─── templates ───────────────────────────────────────────────────────────────────────────────────────────────

def template_path(name: str) -> Path:
    if name not in TEMPLATES:
        raise TechDrawError(f"{name!r} is not a template the app has ({', '.join(TEMPLATES)})")
    return TEMPLATES_DIR / name


def _quantity_mm(text: str) -> float:
    """Base::Quantity::parse of an SVG width ("297mm", "11in", "841"), in mm."""
    m = re.fullmatch(r"\s*([0-9.+-eE]+)\s*([a-z]*)\s*", text or "")
    if not m:
        return 0.0
    v, unit = float(m.group(1)), m.group(2)
    return v * {"": 1.0, "mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4, "px": 25.4 / 96.0, "pt": 25.4 / 72.0}.get(unit, 1.0)


def template_info(name: str) -> dict:
    """DrawSVGTemplate::extractTemplateAttributes and getEditableTextsFromTemplate's raw fields: width, height,
    orientation, and each editable text's (name, its tspan's text, its autofill id), in the file's order."""
    root = ET.parse(template_path(name)).getroot()
    w, h = _quantity_mm(root.get("width", "")), _quantity_mm(root.get("height", ""))
    edit, auto = f"{{{FREECAD_NS}}}editable", f"{{{FREECAD_NS}}}autofill"
    fields = []
    for t in root.iter(f"{{{SVG_NS}}}text"):
        key = t.get(edit)
        if not key:
            continue
        span = t.find(f"{{{SVG_NS}}}tspan")
        if span is None:
            continue
        fields.append((key, span.text or "", t.get(auto) or ""))
    return {"width": w, "height": h, "orientation": "Landscape" if h and w / h >= 1.0 else "Portrait",
            "fields": fields}


def nearest_fraction(value: float, max_denominator: int = 999) -> tuple[int, int]:
    """DrawUtil::nearestFraction (a page's scale as n : d)."""
    from fractions import Fraction
    f = Fraction(value).limit_denominator(max_denominator)
    return f.numerator, f.denominator


def autofill(name: str, title: str, author: str = "", company: str = "", today=None) -> dict:
    """The EditableTexts DrawSVGTemplate makes when its Template is set (TechDraw_PageDefault): each field's
    autofill value (DrawTemplate::getAutofillValue: the document's CreatedBy, the date as %x, the Company, the
    document's Label; the scale and sheet before the template belongs to a page) or else the template's own text."""
    today = today or datetime.date.today()
    out = {}
    for key, value, fill in template_info(name)["fields"]:
        v = ""
        if fill == "author":
            v = author
        elif fill == "date":
            v = today.strftime("%m/%d/%y")
        elif fill in ("organization", "organisation", "owner", "company"):
            v = company
        elif fill == "sheet":
            v = "0 / 1"
        elif fill == "title":
            v = title
        out[key] = v or value
    return out


# ─── the objects ─────────────────────────────────────────────────────────────────────────────────────────────

VEC = ("direction", "x_direction", "section_normal", "section_origin", "caption_location", "hatch_offset",
       "area_leader_point", "pattern_offset")


class TDObject(KW.KwFeature):
    """A PAGE entry."""
    ENUMS: dict = {}
    PROP_NAMES: dict = {}           # snake_case -> FreeCAD's name, where it is not CamelCase of the key

    @classmethod
    def prop_name(cls, key: str) -> str:
        return cls.PROP_NAMES.get(key) or "".join(w[:1].upper() + w[1:] for w in key.split("_"))

    def normalize(self, key, v):
        if key in VEC and v is not None:
            if not (isinstance(v, (list, tuple)) and len(v) == 3):
                raise TechDrawError(f"{self.name}.{key}: {v!r} is not a vector (x, y, z)")
            return tuple(float(x) for x in v)
        if key in ("source", "views") and v is not None:
            if isinstance(v, str):
                v = [v]
            return tuple(v)
        if key == "references_2d":
            out = []
            for r in v or ():
                if not (isinstance(r, (list, tuple)) and len(r) == 2 and all(isinstance(x, str) for x in r)):
                    raise TechDrawError(f"{self.name}.references_2d: {r!r} is not (view, \"EdgeN\" | \"VertexN\")")
                out.append((r[0], r[1]))
            return tuple(out)
        if key == "text" and isinstance(self.DEFAULTS.get("text"), tuple):
            if isinstance(v, str):
                v = v.split("\n")
            return tuple(str(x) for x in v)
        if key == "editable_texts":
            return dict(v or {})
        if key in LIST_KEYS:
            from . import techdraw_cosmetic as C
            kind = LIST_KEYS[key]
            try:
                return tuple(_frozen(C.clean(kind, _thawed(x) if not isinstance(x, dict) else x)) for x in (v or ()))
            except (KeyError, C.CosmeticError) as e:
                raise TechDrawError(f"{self.name}.{self.prop_name(key)}: {e!r}") from None
        d = self.DEFAULTS.get(key)
        if isinstance(d, float) and isinstance(v, int) and not isinstance(v, bool):
            return float(v)
        return super().normalize(key, v)

    def validate(self):
        for k, items in self.ENUMS.items():
            v = getattr(self, k)
            if v is not None and v not in items:
                raise TechDrawError(f"{self.name}.{self.prop_name(k)}: {v!r} is not one of {', '.join(items)}")

    def source_value(self, key, v=None):
        v = getattr(self, key) if v is None else v
        if key == "references_2d":
            return [tuple(r) for r in v]
        if key in VEC:
            return tuple(v)
        if key == "editable_texts":
            return dict(v)
        if key in LIST_KEYS:
            return [_thawed(x) for x in v]
        if isinstance(v, tuple):
            return list(v)
        return v

    def references(self) -> list:
        out = []
        for k in self.REFS:
            v = getattr(self, k)
            if isinstance(v, (list, tuple)):
                out += [x[0] if isinstance(x, tuple) else x for x in v]
            elif v:
                out.append(v)
        return out

    def is_default(self, key) -> bool:
        return self.normalize(key, self.DEFAULTS[key]) == getattr(self, key)


def _frozen(x):
    if isinstance(x, dict):
        return tuple(sorted((k, _frozen(v)) for k, v in x.items()))
    if isinstance(x, list):
        return tuple(_frozen(v) for v in x)
    return x


def _thawed(x):
    if isinstance(x, tuple) and x and all(isinstance(p, tuple) and len(p) == 2 and isinstance(p[0], str) for p in x):
        return {k: _thawed(v) for k, v in x}
    if isinstance(x, tuple):
        return [_thawed(v) for v in x]
    return x


class DrawPage(TDObject):
    """TechDraw::DrawPage: TechDraw_PageDefault makes "Page" with a DrawSVGTemplate "Template" of the default
    template (Preferences::defaultTemplate, Default_Template_A4_Landscape.svg)."""
    kind = "DrawPage"
    TYPE_ID = "TechDraw::DrawPage"
    POS = ("template",)
    DEFAULTS = {"template": None, "projection_type": "First angle", "scale": 1.0, "keep_updated": True,
                "next_balloon_index": 1, "label": None}
    REFS = ("template",)
    ENUMS = {"projection_type": PROJECTION_TYPES}
    TRANSACTION = "Drawing create page"


class DrawSVGTemplate(TDObject):
    kind = "DrawSVGTemplate"
    TYPE_ID = "TechDraw::DrawSVGTemplate"
    DEFAULTS = {"template": DEFAULT_TEMPLATE, "editable_texts": {}, "label": None}

    def validate(self):
        template_path(self.template)


VIEW_DEFAULTS = {
    # DrawView
    "x": 0.0, "y": 0.0, "lock_position": False, "rotation": 0.0, "scale_type": "Page", "scale": 1.0, "caption": "",
    "label": None,
    # DrawViewPart (DrawViewPart.cpp, a fresh profile's HLR group)
    "source": (), "direction": (0.0, -1.0, 0.0), "x_direction": (1.0, 0.0, 0.0), "perspective": False, "focus": 100.0,
    "coarse_view": False, "smooth_visible": True, "seam_visible": False, "iso_visible": False, "hard_hidden": False,
    "smooth_hidden": False, "seam_hidden": False, "iso_hidden": False, "iso_count": 0, "scrub_count": 1,
    "cosmetic_edges": (), "center_lines": (), "cosmetic_vertexes": (), "geom_formats": (),
}
# the view's lists of dicts (techdraw_cosmetic.py), and the kind each holds
LIST_KEYS = {"cosmetic_edges": "edge", "center_lines": "centerline", "cosmetic_vertexes": "vertex",
             "geom_formats": "geomformat"}


class DrawViewPart(TDObject):
    kind = "DrawViewPart"
    TYPE_ID = "TechDraw::DrawViewPart"
    DEFAULTS = dict(VIEW_DEFAULTS)
    ENUMS = {"scale_type": SCALE_TYPES}
    TRANSACTION = "Create view"
    PROP_NAMES = {"x": "X", "y": "Y", "x_direction": "XDirection"}

    def flags(self):
        from .techdraw_view import Flags
        return Flags(self.smooth_visible, self.seam_visible, self.iso_visible, self.hard_hidden, self.smooth_hidden,
                     self.seam_hidden, self.iso_hidden, self.iso_count, self.scrub_count)


class DrawProjGroupItem(DrawViewPart):
    """TechDraw::DrawProjGroupItem: a view on its own (TechDraw_View) or one projection of a DrawProjGroup, which
    gives it its Source, Scale and ScaleType and, with AutoDistribute, its X and Y (relative to the group's)."""
    kind = "DrawProjGroupItem"
    TYPE_ID = "TechDraw::DrawProjGroupItem"
    DEFAULTS = {**VIEW_DEFAULTS, "type": "Front"}
    ENUMS = {"scale_type": SCALE_TYPES, "type": ITEM_TYPES}


class DrawProjGroup(TDObject):
    kind = "DrawProjGroup"
    TYPE_ID = "TechDraw::DrawProjGroup"
    DEFAULTS = {"source": (), "anchor": None, "views": (), "projection_type": "First angle", "auto_distribute": True,
                "spacing_x": 15.0, "spacing_y": 15.0, "x": 0.0, "y": 0.0, "lock_position": False,
                "scale_type": "Page", "scale": 1.0, "label": None}
    REFS = ("anchor", "views")
    ENUMS = {"projection_type": GROUP_PROJECTION_TYPES, "scale_type": SCALE_TYPES}
    PROP_NAMES = {"x": "X", "y": "Y", "spacing_x": "spacingX", "spacing_y": "spacingY"}
    TRANSACTION = "Create projection group"


class DrawViewSection(DrawViewPart):
    kind = "DrawViewSection"
    TYPE_ID = "TechDraw::DrawViewSection"
    DEFAULTS = {**VIEW_DEFAULTS, "base_view": None, "section_symbol": "", "section_normal": (0.0, -1.0, 0.0),
                "section_origin": (0.0, 0.0, 0.0), "section_direction": "Right", "fuse_before_cut": False,
                "trim_after_cut": False, "use_previous_cut": False, "cut_surface_display": "SvgHatch",
                "hatch_scale": 1.0, "hatch_rotation": 0.0, "section_line_stretch": 1.0}
    REFS = ("base_view",)
    ENUMS = {"scale_type": SCALE_TYPES, "section_direction": SECTION_DIRECTIONS, "cut_surface_display": CUT_SURFACE}
    TRANSACTION = "Create Section View"


class DrawViewDimension(TDObject):
    kind = "DrawViewDimension"
    TYPE_ID = "TechDraw::DrawViewDimension"
    DEFAULTS = {"type": "Distance", "references_2d": (), "measure_type": "Projected", "format_spec": None,
                "format_spec_over_tolerance": "%+.2w", "format_spec_under_tolerance": "%+.2w", "arbitrary": False,
                "arbitrary_tolerances": False, "over_tolerance": 0.0, "under_tolerance": 0.0,
                "equal_tolerance": True, "inverted": False, "theoretical_exact": False, "show_units": False,
                "show_supplementary": False, "angle_override": False, "line_angle": 0.0, "extension_angle": 0.0,
                "x": 0.0, "y": 0.0, "label": None}
    REFS = ("references_2d",)
    ENUMS = {"type": DIM_TYPES, "measure_type": MEASURE_TYPES}
    PROP_NAMES = {"x": "X", "y": "Y", "references_2d": "References2D"}
    TRANSACTION = "Create dimension"

    def validate(self):
        super().validate()
        if self.format_spec is None:
            from .techdraw_dim import default_format_spec
            self.format_spec = default_format_spec(self.type)
        if self.equal_tolerance:            # onChanged(EqualTolerance / OverTolerance)
            if self.over_tolerance < 0:
                self.over_tolerance = 0.0
            self.under_tolerance = -self.over_tolerance
            self.format_spec_under_tolerance = self.format_spec_over_tolerance

    def is_default(self, key) -> bool:
        if key == "format_spec":
            from .techdraw_dim import default_format_spec
            return self.format_spec == default_format_spec(self.type)
        if key in ("under_tolerance", "format_spec_under_tolerance") and self.equal_tolerance:
            return True
        return super().is_default(key)

    def view(self) -> str | None:
        return self.references_2d[0][0] if self.references_2d else None


class DrawViewBalloon(TDObject):
    kind = "DrawViewBalloon"
    TYPE_ID = "TechDraw::DrawViewBalloon"
    DEFAULTS = {"source_view": None, "text": "", "origin_x": 0.0, "origin_y": 0.0, "bubble_shape": "Circular",
                "end_type": "Filled arrow", "end_type_scale": 1.0, "shape_scale": 1.0, "kink_length": 5.0,
                "text_wrap_len": -1.0, "x": 0.0, "y": 0.0, "lock_position": False, "label": None}
    REFS = ("source_view",)
    ENUMS = {"bubble_shape": BUBBLE_SHAPES, "end_type": END_TYPES}
    PROP_NAMES = {"x": "X", "y": "Y"}
    TRANSACTION = "Create Balloon"


class DrawViewAnnotation(TDObject):
    kind = "DrawViewAnnotation"
    TYPE_ID = "TechDraw::DrawViewAnnotation"
    DEFAULTS = {"text": ("Default Text",), "font": "osifont", "text_size": 5.0, "text_style": "Normal",
                "max_width": -1.0, "line_space": 100, "x": 0.0, "y": 0.0, "rotation": 0.0, "lock_position": False,
                "caption": "", "label": None}
    ENUMS = {"text_style": TEXT_STYLES}
    PROP_NAMES = {"x": "X", "y": "Y"}
    TRANSACTION = "Create Annotation"


class _Hatch(TDObject):
    """What DrawHatch and DrawGeomHatch share: Source is a view and some of its faces (a PropertyLinkSub), kept here as the
    view's name and `faces`, ["Face0", ...]; the properties of their view providers (the colour, the scale ...) are held
    beside the object's, as the property view shows them."""
    REFS = ("source",)

    def normalize(self, key, v):
        if key == "source":
            if v is not None and not isinstance(v, str):
                raise TechDrawError(f"{self.name}.source: {v!r} is not a view's name")
            return v
        if key == "faces":
            out = tuple(v or ())
            for f in out:
                if not (isinstance(f, str) and re.fullmatch(r"Face[0-9]+", f)):
                    raise TechDrawError(f"{self.name}.faces: {f!r} is not \"Face<n>\"")
            return out
        if key in ("hatch_color", "color_pattern"):
            c = tuple(float(x) for x in v)
            if len(c) == 3:
                c += (1.0,)
            if len(c) != 4:
                raise TechDrawError(f"{self.name}.{key}: {v!r} is not a colour (r, g, b)")
            return c
        return super().normalize(key, v)

    def source_value(self, key, v=None):
        v = getattr(self, key) if v is None else v
        if key in ("hatch_color", "color_pattern", "faces"):
            return list(v)
        return super().source_value(key, v)

    def affects(self, face: str) -> bool:
        return face in self.faces


class DrawHatch(_Hatch):
    """TechDraw::DrawHatch: an image (SVG tile) hatch on faces of a view; TaskHatch's HatchColor, HatchScale, HatchRotation
    and HatchOffset belong to its view provider."""
    kind = "DrawHatch"
    TYPE_ID = "TechDraw::DrawHatch"
    DEFAULTS = {"source": None, "faces": (), "hatch_pattern": "simple.svg", "hatch_color": (0.0, 1.0, 0.0, 1.0),
                "hatch_scale": 1.0, "hatch_rotation": 0.0, "hatch_offset": (0.0, 0.0, 0.0), "label": None}
    TRANSACTION = "Create Hatch"

    def validate(self):
        from .techdraw_hatch import svg_path
        svg_path(self.hatch_pattern)


class DrawGeomHatch(_Hatch):
    """TechDraw::DrawGeomHatch: a PAT hatch on faces of a view (techdraw_hatch.py); ColorPattern and WeightPattern belong
    to its view provider."""
    kind = "DrawGeomHatch"
    TYPE_ID = "TechDraw::DrawGeomHatch"
    DEFAULTS = {"source": None, "faces": (), "file_pattern": "FCPAT.pat", "name_pattern": "Diamond", "scale_pattern": 1.0,
                "pattern_rotation": 0.0, "pattern_offset": (0.0, 0.0, 0.0), "color_pattern": (0.0, 1.0, 0.0, 1.0),
                "weight_pattern": 0.5, "label": None}
    TRANSACTION = "Create GeomHatch"

    def validate(self):
        from .techdraw_hatch import pattern_names, pat_path
        pat_path(self.file_pattern)
        if self.name_pattern not in pattern_names(self.file_pattern):
            raise TechDrawError(f"{self.name_pattern!r} is not a pattern of {self.file_pattern} "
                                f"({', '.join(pattern_names(self.file_pattern))})")


CLASSES = {c.kind: c for c in (DrawPage, DrawSVGTemplate, DrawViewPart, DrawProjGroupItem, DrawProjGroup,
                               DrawViewSection, DrawViewDimension, DrawViewBalloon, DrawViewAnnotation, DrawHatch,
                               DrawGeomHatch)}
VIEW_KINDS = ("DrawViewPart", "DrawProjGroupItem", "DrawViewSection")


def as_dict(o: TDObject) -> dict:
    d = {"name": o.name, "kind": o.kind, "type_id": o.TYPE_ID}
    for k in o.DEFAULTS:
        d[k] = KW._json(o.source_value(k) if k in LIST_KEYS
                        else getattr(o, k))
    if isinstance(o, DrawViewDimension):
        d["dim_type"] = d.pop("type")
    if isinstance(o, DrawProjGroupItem):
        d["item_type"] = d.pop("type")
    return d


def from_dict(d: dict) -> TDObject:
    cls = CLASSES.get(d.get("kind"))
    if cls is None:
        raise TechDrawError(f"{d.get('kind')!r} is not a TechDraw object ({', '.join(CLASSES)})")
    kw = {k: v for k, v in d.items() if k not in ("name", "kind", "type_id")}
    if "dim_type" in kw:
        kw["type"] = kw.pop("dim_type")
    if "item_type" in kw:
        kw["type"] = kw.pop("item_type")
    return cls(d.get("name"), **kw)


# ─── DrawUtil::sensibleScale ─────────────────────────────────────────────────────────────────────────────────

def sensible_scale(working: float) -> float:
    if not working > 0.0:
        return 1.0
    exponent = math.floor(math.log10(working))
    working *= 10.0 ** -exponent
    scales = ((1.0, 1.25, 2.0, 2.5, 3.75, 5.0, 7.5, 10.0, 50.0, 100.0),
              (1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 8.0, 10.0, 50.0, 100.0))[exponent >= 0]
    i = 9
    while scales[i] > working:
        i -= 1
    return scales[i] * 10.0 ** exponent


# ─── the document ────────────────────────────────────────────────────────────────────────────────────────────

class PageDocument:
    """A page and its objects, recomputed as FreeCAD's recompute of the page does.

    shape_of(part) -> the part's TopoDS_Shape (its own frame); title is the document's Label (the project)."""

    def __init__(self, objects, shape_of=None, title: str = "Unnamed"):
        self.objects = list(objects)
        self.shape_of = shape_of
        self.title = title
        self.geo: dict = {}             # view name -> ViewGeometry
        self.pos: dict = {}             # view name -> (X, Y) on the page (group items: the group's + theirs)
        self.scales: dict = {}
        self.dims: dict = {}
        self.errors: dict = {}
        self._shapes: dict = {}

    # ── lookups ──
    def get(self, name):
        return next((o for o in self.objects if o.name == name), None)

    @property
    def page(self) -> DrawPage | None:
        return next((o for o in self.objects if isinstance(o, DrawPage)), None)

    @property
    def template(self) -> DrawSVGTemplate | None:
        p = self.page
        t = self.get(p.template) if p and p.template else None
        return t if isinstance(t, DrawSVGTemplate) else None

    def page_size(self) -> tuple[float, float]:
        t = self.template
        if t is None:
            return (297.0, 210.0)
        info = template_info(t.template)
        return (info["width"], info["height"])

    def group_of(self, name):
        return next((o for o in self.objects if isinstance(o, DrawProjGroup) and name in o.views), None)

    def views(self):
        return [o for o in self.objects if isinstance(o, (DrawViewPart, DrawProjGroup, DrawViewDimension,
                                                          DrawViewBalloon, DrawViewAnnotation))]

    def page_views(self):
        """DrawPage.Views: every view no group holds, in the list's order."""
        return [o for o in self.views() if self.group_of(o.name) is None]

    def labels(self):
        return {o.label or o.name for o in self.objects}

    # ── scale ──
    def view_scale(self, o) -> float:
        """DrawView::getScale (a group item takes its group's)."""
        g = self.group_of(o.name) if isinstance(o, DrawProjGroupItem) else None
        if g is not None:
            return self.view_scale(g)
        if o.name in self.scales:
            return self.scales[o.name]
        s = o.scale
        if o.scale_type == "Page" and self.page is not None:
            s = self.page.scale
        return s if s > 0 else 1.0

    def source_of(self, o):
        g = self.group_of(o.name) if isinstance(o, DrawProjGroupItem) else None
        if g is not None:
            return g.source
        if isinstance(o, DrawViewSection) and not o.source and o.base_view:
            b = self.get(o.base_view)
            return self.source_of(b) if b is not None else ()
        return o.source

    def shape(self, parts):
        from .techdraw_view import source_compound
        key = tuple(parts)
        if key not in self._shapes:
            if self.shape_of is None:
                raise TechDrawError("no shapes to draw (PageDocument without shape_of)")
            self._shapes[key] = source_compound([self.shape_of(p) for p in parts])
        return self._shapes[key]

    # ── the recompute ──
    def recompute(self):
        from . import techdraw_view as V
        self.geo, self.pos, self.scales, self.dims, self.errors = {}, {}, {}, {}, {}
        self._result = None
        w, h = self.page_size()
        order = [o for o in self.objects if isinstance(o, DrawViewPart) and not isinstance(o, DrawViewSection)]
        order += [o for o in self.objects if isinstance(o, DrawViewSection)]
        for o in order:
            try:
                self._view(o, w, h)
            except Exception as e:          # a view that fails draws nothing, as a failed recompute
                self.errors[o.name] = str(e) or type(e).__name__
        for g in (o for o in self.objects if isinstance(o, DrawProjGroup)):
            self._group(g, w, h)
        for o in self.objects:
            if isinstance(o, (DrawViewPart,)) and o.name not in self.pos:
                self.pos[o.name] = (o.x, o.y)
        from . import techdraw_dim as D
        for d in (o for o in self.objects if isinstance(o, DrawViewDimension)):
            vname = d.view()
            geo = self.geo.get(vname)
            if geo is None:
                self.errors[d.name] = f"{d.name}: its view {vname!r} has no geometry"
                continue
            try:
                m = D.measure(d, geo)
                txt, tol = D.text(d, m["value"])
                m["text"], m["tolerances"] = txt, tol
                m["unaltered"] = D.formatted_value(d, m["value"], "UNALTERED")   # DrawViewDimension.getText()
                self.dims[d.name] = m
            except Exception as e:
                self.errors[d.name] = str(e) or type(e).__name__
        return self

    def _view(self, o, w, h):
        from . import techdraw_view as V
        parts = self.source_of(o)
        if not parts:
            return
        shape = self.shape(parts)
        scale = self.view_scale(o)
        if isinstance(o, DrawViewSection):
            geo = V.project_section(shape, o.section_normal, o.x_direction, o.section_origin, o.direction,
                                    o.x_direction, scale, o.rotation, o.flags())
        else:
            geo = V.project(shape, o.direction, o.x_direction, scale, o.rotation, o.flags())
        # DrawProjGroupItem::checkFit is always true: only a DrawViewPart or a section scales itself to the page
        if o.scale_type == "Automatic" and not isinstance(o, DrawProjGroupItem):
            bw, bh = geo.box[2] - geo.box[0], geo.box[3] - geo.box[1]
            if bw > w or bh > h:            # postHlrTasks: !checkFit -> autoScale, again
                new = sensible_scale(min(w / (bw / scale), h / (bh / scale)))
                self.scales[o.name] = new
                if isinstance(o, DrawViewSection):
                    geo = V.project_section(shape, o.section_normal, o.x_direction, o.section_origin,
                                            o.direction, o.x_direction, new, o.rotation, o.flags())
                else:
                    geo = V.project(shape, o.direction, o.x_direction, new, o.rotation, o.flags())
        from . import techdraw_cosmetic as C
        C.apply(geo, o, geo.scale, o.rotation)
        self.geo[o.name] = geo

    def _group(self, g, w, h):
        """DrawProjGroup::execute: Automatic scale when it does not fit, then autoPositionChildren."""
        from . import techdraw_view as V
        items = [self.get(n) for n in g.views if isinstance(self.get(n), DrawProjGroupItem)]
        third = self.group_projection(g) == "Third angle"

        def boxes(unscaled=False):
            out = {}
            for it in items:
                geo = self.geo.get(it.name)
                if geo is None:
                    continue
                f = 1.0 / geo.scale if unscaled else 1.0
                out[it.type] = ((geo.box[2] - geo.box[0]) * f, (geo.box[3] - geo.box[1]) * f)
            return out
        if g.scale_type == "Automatic":
            bx = boxes(True)
            grid = {V.view_index(t, third): wh for t, wh in bx.items()}
            cw = lambda ids: max([grid[i][0] for i in ids if i in grid] or [0.0])  # noqa: E731
            rh = lambda ids: max([grid[i][1] for i in ids if i in grid] or [0.0])  # noqa: E731
            width = cw((0, 3, 7)) + cw((1, 4, 8)) + cw((2, 5, 9)) + (grid[6][0] if 6 in grid else 0.0)
            height = rh((0, 1, 2)) + max(rh((3, 4, 5)), grid[6][1] if 6 in grid else 0.0) + rh((7, 8, 9))
            rect_w, rect_h = (width + g.spacing_x * 3.0) * 1.2, (height + g.spacing_y * 2.0) * 1.2
            cur = self.view_scale(g)
            if rect_w * cur > w or rect_h * cur > h:
                new = sensible_scale(min(w / rect_w, h / rect_h))
                if abs(new - cur) >= 0.00001:
                    self.scales[g.name] = new
                    for it in items:
                        self._view(it, w, h)
        bx = boxes()
        for it in items:
            if it.type == "Front" or it.lock_position or not g.auto_distribute:
                dx, dy = (0.0, 0.0) if it.type == "Front" else (it.x, it.y)
            else:
                dx, dy = V.group_position(it.type, bx, third, g.spacing_x, g.spacing_y)
            self.pos[it.name] = (g.x + dx, g.y + dy)
        self.pos[g.name] = (g.x, g.y)

    def group_projection(self, g) -> str:
        if g.projection_type == "Default":
            return self.page.projection_type if self.page else "First angle"
        return g.projection_type

    # ── what the page, the CLI and the goldens read ──
    def result(self) -> dict:
        if getattr(self, "_result", None) is None:
            self._result = self._make_result()
        return self._result

    def _make_result(self) -> dict:
        from .techdraw_view import geometry_json
        w, h = self.page_size()
        t = self.template
        views = {}
        for name, geo in self.geo.items():
            o = self.get(name)
            x, y = self.pos.get(name, (o.x, o.y))
            views[name] = {"x": x, "y": y, "scale": geo.scale, "rotation": o.rotation, **geometry_json(geo)}
        for g in (o for o in self.objects if isinstance(o, DrawProjGroup)):
            views.setdefault(g.name, {"x": g.x, "y": g.y, "scale": self.view_scale(g), "group": True})
            for n in g.views:
                if n in views:
                    views[n]["group"] = g.name
        dims = {}
        for name, m in self.dims.items():
            d = self.get(name)
            dims[name] = {**m, "x": d.x, "y": d.y, "view": d.view(), "type": d.type}
        sections = {}
        for s in (o for o in self.objects if isinstance(o, DrawViewSection)):
            line = self.section_line(s)
            if line is not None:
                sections[s.name] = line
        hatches = {}
        if any(isinstance(o, (DrawHatch, DrawGeomHatch)) for o in self.objects):
            from . import techdraw_hatch as H
            hatches = H.results(self)
        return {"page": self.page.name if self.page else None, "width": w, "height": h,
                "template": t.template if t else None, "texts": dict(t.editable_texts) if t else {},
                "views": views, "dimensions": dims, "sections": sections, "hatches": hatches, "errors": dict(self.errors)}

    def section_line(self, s) -> dict | None:
        """DrawViewSection::sectionLineEnds: the section line on its base view, in the base view's paper
        coordinates (y down), and the direction the arrows point (getSectionDirectionOnBaseView)."""
        from . import techdraw_view as V
        base = self.get(s.base_view)
        bgeo = self.geo.get(s.base_view)
        if base is None or bgeo is None:
            return None
        n, d = s.section_normal, base.direction
        line_dir = (-(d[1] * n[2] - d[2] * n[1]), -(d[2] * n[0] - d[0] * n[2]), -(d[0] * n[1] - d[1] * n[0]))
        ln = math.sqrt(sum(c * c for c in line_dir)) or 1.0
        line_dir = tuple(c / ln for c in line_dir)
        pd = V.project_point(base.direction, base.x_direction, line_dir)
        pn = math.hypot(*pd) or 1.0
        pd = (pd[0] / pn, pd[1] / pn)
        org = tuple(s.section_origin[i] - bgeo.centroid[i] for i in range(3))
        po = V.project_point(base.direction, base.x_direction, org)
        size = self._size_along(bgeo, pd) * s.section_line_stretch / 2.0
        sc = bgeo.scale
        ends = [((po[0] + pd[0] * size) * sc, -(po[1] + pd[1] * size) * sc),
                ((po[0] - pd[0] * size) * sc, -(po[1] - pd[1] * size) * sc)]
        arrow = V.project_point(base.direction, base.x_direction, s.section_normal)
        an = math.hypot(*arrow) or 1.0
        return {"view": base.name, "ends": [list(p) for p in ends], "normal": [arrow[0] / an, -arrow[1] / an],
                "symbol": s.section_symbol}

    @staticmethod
    def _size_along(geo, d) -> float:
        """DrawViewPart::getSizeAlongVector: the width of the view's edges turned so d is along x, unscaled."""
        ang = math.atan2(d[1], d[0])
        c, s = math.cos(-ang), math.sin(-ang)
        xs = []
        from .techdraw_view import edge_json
        for e in geo.edges:
            ej = edge_json(e, 16)
            pts = ej.get("points") or [ej["start"], ej["end"]]
            if "radius" in ej and ej["kind"] == "CIRCLE":
                r = ej["radius"]
                cx, cy = ej["center"]
                pts = [[cx + r, cy], [cx - r, cy], [cx, cy + r], [cx, cy - r]]
            for p in pts:
                xs.append(p[0] * c - (-p[1]) * s)
        return (max(xs) - min(xs)) / geo.scale if xs else 1.0

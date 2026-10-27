# SPDX-License-Identifier: LGPL-2.1-or-later
# Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
# LGPL-2.0-or-later or LGPL-2.1-or-later as it states; NOTICE has them):
#   src/Mod/Part/App/Geometry.cpp: 2008 Werner Mayer (makeTextWires, transformAndConvertToGeometry, and their
#                                  FreeType callbacks, "adapted from FT2FC.cpp")
#   src/Mod/Sketcher/App/SketchObject.cpp: 2008 Jürgen Riegel (setTextAndFont)
#   src/Mod/Sketcher/App/SketchObjectGeometry.cpp, SketchObjectOperations.cpp, SketchObjectConstraints.cpp:
#                                  2008 Jürgen Riegel (delGeometries, delGeometriesExclusiveList,
#                                  changeConstraintAfterDeletingGeo)
#   src/Mod/Sketcher/App/Constraint.cpp: 2008 Jürgen Riegel (setText, setFont, setIsTextHeight)
#   src/Mod/Sketcher/Gui/FontProvider.cpp: 2026 FreeCAD Project Association (findAvailableFontFiles)
#   src/Mod/Sketcher/Gui/DrawSketchHandlerText.h: 2025 Pierre-Louis Boyer (the default font)
"""The Sketcher's text (Sketcher_CreateText), as FreeCAD 26.3 makes it: glyph outlines from FreeType, shaped by
HarfBuzz, built into OpenCascade wires and fitted to the text's handle line.

    fonts()                        FontProvider's findAvailableFontFiles: {name: path}, the shipped osifont first,
                                   then the fonts fontconfig knows on Linux (the folders FreeCAD reads elsewhere)
    make_text_wires(text, path)    Part::makeTextWires: one TopoDS_Wire per glyph contour, 1 unit per em
    to_geometry(wires, p1, p2, h)  Part::transformAndConvertToGeometry: the sketch geometry (LineSegment, and
                                   BSplineCurve for each Bezier) scaled and turned onto the handle p1 -> p2,
                                   p1 - p2 its height (h) or its width
    set_text_and_font(...)         SketchObject::setTextAndFont on a sketch's geometry and constraints (the part
                                   file's dicts): the old glyphs deleted, the new ones added, the Text constraint
                                   naming the handle and them

FreeType and HarfBuzz are the freetype-py and uharfbuzz wheels (pyproject.toml), imported when a command needs
them, as OCP is. `cad feature text` (cmd_text) is the page's way in: --req JSON, a list of requests.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
from pathlib import Path

CONFUSION = 1e-7                                  # Precision::Confusion()
GEO_UNDEF = -2000                                 # Sketcher::GeoEnum::GeoUndef
DEFAULT_TEXT = "Text"                             # DrawSketchHandlerText: QObject::tr("Text")
DEFAULT_FONTS = ("osifont-lgpl3fe", "DejaVu Sans", "Arial")   # configureToolWidget's choice, in order
FONTS_DIR = Path(__file__).parent / "fonts"       # FreeCAD's Mod/TechDraw/Resources/fonts/: the font we ship
SUFFIXES = {"ttf", "otf", "ttc"}


class TextError(ValueError):
    """What FreeCAD refuses, in its words."""


# ── FontProvider: findAvailableFontFiles ─────────────────────────────────────────────────────────────────────

def _files_in(dirs) -> list[str]:
    """filesInDirectories: every file below the folders (QDirIterator, Subdirectories)."""
    out = []
    for d in dirs:
        for root, _, names in os.walk(d):
            out += [os.path.join(root, n) for n in names]
    return out


def _platform_font_files() -> list[str]:
    """platformFontFiles: fontconfig's FcFontList(FC_FILE) on Linux (fc-list is fontconfig's own front end to it);
    the platform's font folders on macOS and Windows."""
    import sys
    if sys.platform.startswith("linux") or "bsd" in sys.platform:
        exe = shutil.which("fc-list")
        if not exe:
            return []
        try:
            r = subprocess.run([exe, "--format", "%{file}\n"], capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.SubprocessError):
            return []
        return [ln for ln in r.stdout.splitlines() if ln]
    if sys.platform == "darwin":
        home = Path.home()
        return _files_in([home / "Library/Fonts", "/Library/Fonts", "/System/Library/Fonts", "/Network/Library/Fonts"])
    if sys.platform == "win32":
        dirs = [os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts")]
        if os.environ.get("LOCALAPPDATA"):
            dirs.append(os.environ["LOCALAPPDATA"] + "/Microsoft/Windows/Fonts")
        return _files_in(dirs)
    return _files_in([Path.home() / ".local/share/fonts", Path.home() / ".fonts"])


def _base_name(path: str) -> str:
    """QFileInfo::baseName: the file name up to its first '.'."""
    return os.path.basename(path).split(".", 1)[0]


def _suffix(path: str) -> str:
    """QFileInfo::suffix: after the last '.'."""
    name = os.path.basename(path)
    return name.rsplit(".", 1)[1] if "." in name else ""


_FONTS: dict | None = None


def fonts(refresh: bool = False) -> dict[str, str]:
    """findAvailableFontFiles: {name: absolute path}, a name being the file's baseName, the first file of a name
    (compared case-folded) winning: the shipped font, then the platform's."""
    global _FONTS
    if _FONTS is not None and not refresh:
        return dict(_FONTS)
    out, names = {}, set()
    for f in _files_in([FONTS_DIR]) + _platform_font_files():
        if not os.path.isfile(f) or _suffix(f).casefold() not in SUFFIXES:
            continue
        key = _base_name(f).casefold()
        if key in names:
            continue
        names.add(key)
        out[_base_name(f)] = os.path.abspath(f)
    _FONTS = dict(sorted(out.items()))                   # a QMap: by name
    return dict(_FONTS)


def font_names() -> list[str]:
    """The Font combo's items: the names sorted case-insensitively (QStringList::sort(Qt::CaseInsensitive))."""
    return sorted(fonts(), key=lambda n: (n.casefold(), n))


def default_font() -> str | None:
    """configureToolWidget's default: osifont-lgpl3fe, else DejaVu Sans, else Arial, else the first name."""
    names = font_names()
    for want in DEFAULT_FONTS:
        for n in names:
            if n.casefold() == want.casefold():
                return n
    return names[0] if names else None


def font_path(font: str) -> str:
    """The file of a font: a path as given, else the font of that name (case-insensitive, as EditTextDialog's
    findText(MatchFixedString) finds it)."""
    if font and os.path.isfile(font):
        return font
    table = fonts()
    for n, p in table.items():
        if n.casefold() == (font or "").casefold():
            return p
    raise TextError(f"The original font '{font}' is not found on your system.")


def file_name_pure(font: str) -> str:
    """Base::FileInfo::fileNamePure, what Constraint::setFont keeps of a path: the file name without its
    extension (after the last '.')."""
    name = font.replace("\\", "/").rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[0] if "." in name else name


# ── Part::makeTextWires ──────────────────────────────────────────────────────────────────────────────────────

def _occ():
    from OCP.BRep import BRep_Tool
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire, BRepBuilderAPI_Transform
    from OCP.BRepLib import BRepLib
    from OCP.Bnd import Bnd_Box
    from OCP.Geom import Geom_BezierCurve, Geom_Line, Geom_Plane, Geom_TrimmedCurve
    from OCP.Geom2d import Geom2d_BezierCurve, Geom2d_Line, Geom2d_TrimmedCurve
    from OCP.gce import gce_MakeLin2d
    from OCP.ShapeFix import ShapeFix_Wire
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp, gp_Pnt, gp_Pnt2d, gp_Trsf, gp_Vec
    try:
        from OCP.TColgp import TColgp_Array1OfPnt2d
    except ImportError:                                  # OCP 8 moved OCCT's collections
        from OCP.collections import Array1_gp_Pnt2d as TColgp_Array1OfPnt2d
    return locals()


def _segment(O, p1, p2):
    """GCE2d_MakeSegment(P1, P2).Value(): Geom2d_TrimmedCurve(Geom2d_Line(gce_MakeLin2d(P1, P2)), 0, |P1 P2|)
    (OCP does not export GCE2d)."""
    return O["Geom2d_TrimmedCurve"](O["Geom2d_Line"](O["gce_MakeLin2d"](p1, p2).Value()), 0.0, p1.Distance(p2), True)


class _Ctx:
    """FTDC_Ctx: the wires so far, the open contour's edges, its last and first points, the XY plane."""

    def __init__(self, O):
        self.O, self.wires, self.edges = O, [], []
        self.last = self.start = (0, 0)
        self.surf = O["Geom_Plane"](O["gp"].Origin_s(), O["gp"].DZ_s())


def _edges_to_wire(O, edges):
    """edgesToWire: BRepBuilderAPI_MakeWire, the 3D curves built, ShapeFix_Wire::FixClosed."""
    if not edges:
        return None
    mk = O["BRepBuilderAPI_MakeWire"]()
    for e in edges:
        mk.Add(e)
    if not mk.IsDone():
        return None
    wire = mk.Wire()
    O["BRepLib"].BuildCurves3d_s(wire)
    sfw = O["ShapeFix_Wire"]()
    sfw.Load(wire)
    sfw.FixClosed()
    return sfw.Wire()


def _flush(ctx):
    """flushContour: a closing segment when the contour does not end where it started, then its wire."""
    O = ctx.O
    if not ctx.edges:
        return
    ps, pe = O["gp_Pnt2d"](*ctx.start), O["gp_Pnt2d"](*ctx.last)
    if not ps.IsEqual(pe, CONFUSION):
        seg = _segment(O, pe, ps)
        ctx.edges.append(O["BRepBuilderAPI_MakeEdge"](seg, ctx.surf).Edge())
    w = _edges_to_wire(O, ctx.edges)
    if w is not None and not w.IsNull():
        ctx.wires.append(w)
    ctx.edges = []


def _decompose(outline, ctx):
    """FT_Outline_Decompose with move_cb, line_cb, quad_cb and cubic_cb (shift 0, delta 0)."""
    O = ctx.O

    def move(p, _):
        _flush(ctx)
        ctx.start = ctx.last = (p.x, p.y)
        return 0

    def line(p, _):
        v1, v2 = O["gp_Pnt2d"](*ctx.last), O["gp_Pnt2d"](p.x, p.y)
        if not v1.IsEqual(v2, CONFUSION):
            seg = _segment(O, v1, v2)
            ctx.edges.append(O["BRepBuilderAPI_MakeEdge"](seg, ctx.surf).Edge())
        ctx.last = (p.x, p.y)
        return 0

    def bezier(*pts):
        poles = O["TColgp_Array1OfPnt2d"](1, len(pts) + 1)
        poles.SetValue(1, O["gp_Pnt2d"](*ctx.last))
        for i, p in enumerate(pts):
            poles.SetValue(i + 2, O["gp_Pnt2d"](p.x, p.y))
        ctx.edges.append(O["BRepBuilderAPI_MakeEdge"](O["Geom2d_BezierCurve"](poles), ctx.surf).Edge())
        ctx.last = (pts[-1].x, pts[-1].y)
        return 0

    outline.decompose(None, move_to=move, line_to=line, conic_to=lambda a, b, _: bezier(a, b),
                      cubic_to=lambda a, b, c, _: bezier(a, b, c), shift=0, delta=0)


def make_text_wires(text: str, font_file: str, height: float = 1.0, tracking: float = 0.0) -> list:
    """Part::makeTextWires: each glyph of the shaped text decomposed into wires in the font's units, scaled to
    height per em and placed at its pen position."""
    if not text:
        return []
    import freetype
    import uharfbuzz as hb
    O = _occ()
    data = Path(font_file).read_bytes()
    face = freetype.Face(font_file)
    upem = float(face.units_per_EM)
    if upem < 1.0:
        upem = 2048.0
    scale = height / upem
    flags = freetype.FT_LOAD_NO_SCALE | freetype.FT_LOAD_NO_BITMAP
    hface = hb.Face(hb.Blob(data), 0)
    font = hb.Font(hface)
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(font, buf, {})
    out, pen, track = [], 0.0, 0.0
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        try:
            face.load_glyph(info.codepoint, flags)
        except freetype.FT_Exception:
            pen += pos.x_advance
            track += tracking
            continue
        g = face.glyph
        if g.format == freetype.FT_GLYPH_FORMAT_OUTLINE and g.outline.n_contours > 0:
            ctx = _Ctx(O)
            _decompose(g.outline, ctx)
            _flush(ctx)
            if ctx.wires:
                t = O["gp_Trsf"]()
                t.SetScale(O["gp"].Origin_s(), scale)
                t.SetTranslationPart(O["gp_Vec"]((pen + pos.x_offset) * scale + track, 0.0, 0.0))
                for w in ctx.wires:
                    p = O["BRepBuilderAPI_Transform"](t)
                    p.Perform(w, True)
                    if p.IsDone():
                        out.append(p.Shape())
        pen += pos.x_advance
        track += tracking
    return out


# ── Part::transformAndConvertToGeometry ──────────────────────────────────────────────────────────────────────

def _xy(p):
    return [p.X(), p.Y()]


def _bounds(O, shapes):
    box = O["Bnd_Box"]()
    for s in shapes:
        if not s.IsNull():
            O["BRepBndLib"].Add_s(s, box)
    if box.IsVoid():
        return None
    lo, hi = box.CornerMin(), box.CornerMax()          # Bnd_Box::Get: the box with its gap
    return lo.X(), lo.Y(), lo.Z(), hi.X(), hi.Y(), hi.Z()


def _curve_dict(O, edge, construction: bool):
    """One edge as sketch geometry: makeFromCurve for a closed edge, a Bezier as GeomTrimmedCurve::toBSpline,
    anything else makeFromTrimmedCurve (a line here: GeomLineSegment)."""
    from . import sketch_kernel as K
    curve = O["BRep_Tool"].Curve_s(edge, 0.0, 0.0)
    if curve is None:
        return None
    first, last = O["BRep_Tool"].Range_s(edge)            # BRep_Tool::Curve(E, First, Last)'s range (OCP
                                                         # cannot hand floats back by reference)
    trimmed = O["Geom_TrimmedCurve"]
    if isinstance(curve, trimmed) or curve.DynamicType().Name() == "Geom_TrimmedCurve":
        curve = trimmed.DownCast(curve).BasisCurve() if hasattr(trimmed, "DownCast") else curve.BasisCurve()
    name = curve.DynamicType().Name()
    if name == "Geom_BezierCurve":
        tc = O["Geom_TrimmedCurve"](curve, first, last, True, False)
        d = K.bspline_dict(K._to_bspline(tc, first, last))
    elif name == "Geom_Line":
        d = {"type": "LineSegment", "start": _xy(curve.Value(first)), "end": _xy(curve.Value(last))}
    elif name == "Geom_BSplineCurve":
        tc = O["Geom_TrimmedCurve"](curve, first, last, True, False)
        d = K.bspline_dict(K._to_bspline(tc, first, last))
    else:                                                # FreeCAD: "Could not create geometry from curve."
        return None
    if construction:
        d["construction"] = True
    return d


def to_geometry(shapes: list, p1, p2, height: bool, construction: bool = False) -> list[dict]:
    """transformAndConvertToGeometry(geos, shapes, p1, p2, height): the shapes' bounding box moved to the origin,
    scaled so its height (or width) is |p2 - p1|, turned to p2 - p1 (minus a quarter turn for the height) and
    moved to p1; each edge as sketch geometry."""
    if not shapes:
        return []
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    length = math.sqrt(dx * dx + dy * dy)
    if length < CONFUSION:
        return []
    O = _occ()
    b = _bounds(O, shapes)
    if b is None:
        return []
    xmin, ymin, _, xmax, ymax, _ = b
    if height:
        if ymax - ymin < CONFUSION:
            return []
        scale, angle = length / (ymax - ymin), math.atan2(dy, dx) - 0.5 * math.pi
    else:
        if xmax - xmin < CONFUSION:
            return []
        scale, angle = length / (xmax - xmin), math.atan2(dy, dx)
    gp, Trsf = O["gp"], O["gp_Trsf"]
    t1, s, r, t2 = Trsf(), Trsf(), Trsf(), Trsf()
    t1.SetTranslation(O["gp_Vec"](-xmin, -ymin, 0.0))
    s.SetScale(gp.Origin_s(), scale)
    r.SetRotation(gp.XOY_s().Axis(), angle)
    t2.SetTranslation(O["gp_Vec"](p1[0], p1[1], 0.0))
    final = t2.Multiplied(r).Multiplied(s).Multiplied(t1)
    out = []
    for shape in shapes:
        p = O["BRepBuilderAPI_Transform"](shape, final, True)
        if not p.IsDone():
            continue
        ex = O["TopExp_Explorer"](p.Shape(), O["TopAbs_EDGE"])
        while ex.More():
            edge = O["TopoDS"].Edge(ex.Current())
            if O["BRep_Tool"].IsClosed_s(edge):
                d = _closed_curve_dict(O, edge, construction)
            else:
                d = _curve_dict(O, edge, construction)
            if d is not None:
                out.append(d)
            ex.Next()
    return out


def _closed_curve_dict(O, edge, construction):
    """makeFromCurve(curve) of a closed edge: the whole curve, its own range (a one-edge glyph contour)."""
    from . import sketch_kernel as K
    res = O["BRep_Tool"].Curve_s(edge, 0.0, 0.0)
    curve = res[0] if isinstance(res, tuple) else res
    if curve is None:
        return None
    name = curve.DynamicType().Name()
    if name == "Geom_TrimmedCurve":
        curve = curve.BasisCurve()
        name = curve.DynamicType().Name()
    if name in ("Geom_BezierCurve", "Geom_BSplineCurve"):
        from OCP.GeomConvert import GeomConvert
        b = GeomConvert.CurveToBSplineCurve_s(curve) if name == "Geom_BezierCurve" else curve
        d = K.bspline_dict(b)
    else:
        return None
    if construction:
        d["construction"] = True
    return d


def text_geometry(text: str, font: str, p1, p2, height: bool, construction: bool = False) -> list[dict]:
    """The glyph geometry setTextAndFont adds for a handle from p1 to p2."""
    return to_geometry(make_text_wires(text, font_path(font)), p1, p2, height, construction)


def base_shapes(text: str, font: str) -> dict:
    """The tool's preview cache (cachedBaseShapes) as plain geometry: every edge of makeTextWires at 1 unit per
    em, and the bounding box transformAndConvertToGeometry fits (Bnd_Box with its gap), so the page can place
    them while the mouse moves."""
    shapes = make_text_wires(text, font_path(font)) if text else []
    if not shapes:
        return {"geometry": [], "box": None}
    O = _occ()
    b = _bounds(O, shapes)
    ident = O["gp_Trsf"]()
    geo = []
    for shape in shapes:
        p = O["BRepBuilderAPI_Transform"](shape, ident, True)
        ex = O["TopExp_Explorer"](p.Shape(), O["TopAbs_EDGE"])
        while ex.More():
            d = _curve_dict(O, O["TopoDS"].Edge(ex.Current()), False)
            if d is not None:
                geo.append(d)
            ex.Next()
    return {"geometry": geo, "box": list(b) if b else None}


# ── SketchObject::setTextAndFont ─────────────────────────────────────────────────────────────────────────────

def elements(c: dict) -> list[tuple[int, int]]:
    """A constraint's elements (GeoId, PosId): a Text or Group constraint's whole list, else First, Second, Third
    as Sketcher.Constraint's argument forms put them (cad_agent/sketch_commands.py's fields())."""
    if c.get("type") in ("Text", "Group"):
        a = [int(x) for x in c.get("args", [])]
        return [(a[i], a[i + 1]) for i in range(0, len(a) - 1, 2)]
    from .sketch_commands import fields
    f = fields(c)
    return [(f["first"], f["first_pos"]), (f["second"], f["second_pos"]), (f["third"], f["third_pos"])]


def text_constraint(elems, text: str, font: str, is_height: bool = True) -> dict:
    """Sketcher.Constraint('Text', [g0, p0, g1, p1, ...], text, font, isHeight) as a part file's dict; the font as
    Constraint::setFont keeps it (fileNamePure)."""
    return {"type": "Text", "args": [int(v) for e in elems for v in e], "text": text, "font": file_name_pure(font),
            "is_text_height": bool(is_height), "driving": True, "name": ""}


def _renumber(c: dict, deleted: int):
    """changeConstraintAfterDeletingGeo: None when the constraint names the deleted geometry, else the
    constraint with the GeoIds above it moved down."""
    from .sketch_commands import args_of, fields
    els = elements(c)
    if any(g == deleted for g, _ in els):
        return None
    if c.get("type") in ("Text", "Group"):
        n = dict(c)
        n["args"] = [v for g, p in els for v in ((g - 1 if g > deleted else g), p)]
        return n
    f = fields(c)
    for k in ("first", "second", "third"):
        if f[k] > deleted:
            f[k] -= 1
    n = {**c, **args_of(f)}
    if "value" in c:
        n["value"] = c["value"]
    return n


def del_geometries(geometry: list[dict], constraints: list[dict], ids) -> tuple[list, list]:
    """SketchObject::delGeometries on internal geometry: the internal geometry of what goes, then
    delGeometriesExclusiveList (each from the last, its coincidences moved to the point that stays, then every
    constraint renumbered or dropped)."""
    from . import sketch_commands as SC
    ids = sorted({int(g) for g in ids if g >= 0})
    for c in constraints:                               # a GeoId with internal geometry takes it along
        if str(c.get("type", "")).startswith("InternalAlignment") and elements(c)[1][0] in ids:
            ids.append(elements(c)[0][0])
    ids = sorted(set(ids))
    if not ids:
        return list(geometry), list(constraints)
    geo = [g for i, g in enumerate(geometry) if i not in ids]
    cons = [dict(c) for c in constraints]
    plain = [c for c in cons if c.get("type") not in ("Text", "Group")]
    if plain:                                           # getDirectlyCoincidentPoints, transferConstraints
        f = [dict(SC.fields(c), _c=c) for c in plain]
        for g in reversed(ids):
            for pos in (SC.START, SC.END, SC.MID):
                lst = SC._directly_coincident(f, g, pos)
                if len(lst) > 1:
                    f = SC._del_constraint_on_point(f, g, pos, True)
                    f = SC._transfer(f, lst[0][0], lst[0][1], lst[1][0], lst[1][1])
        moved = []
        for x in f:
            src = x.pop("_c")
            d = {**src, **SC.args_of(x)}
            if "value" in src:
                d["value"] = src["value"]
            moved.append(d)
        it = iter(moved)
        cons = [c if c.get("type") in ("Text", "Group") else next(it, None) for c in cons]
        cons = [c for c in cons if c is not None] + list(it)
    for g in reversed(ids):
        cons = [n for n in (_renumber(c, g) for c in cons) if n is not None]
    return geo, cons


def set_text_and_font(geometry: list[dict], constraints: list[dict], index: int, text: str, font: str,
                      is_height: bool = True, construction: bool = False) -> dict:
    """SketchObject::setTextAndFont(ConstrId, text, font, isHeight, isConstruction): {"geometry", "constraints",
    "added": the new glyphs' GeoIds}. The Text constraint at index holds the handle (element 0) and, once made,
    its glyphs: they are deleted (which deletes the constraint) and a new constraint is added at the end; for a
    new text (only the handle) the glyphs are added to the constraint in its place. font is a path or a font's
    name (fonts()). FreeCAD then solves, which the caller does."""
    if index < 0 or index >= len(constraints):
        raise TextError(f"Invalid constraint index or not a Text constraint: {index}")
    c = constraints[index]
    els = elements(c)
    if c.get("type") != "Text" or not els:
        raise TextError(f"Invalid constraint index or not a Text constraint: {index}")
    handle = els[0][0]
    first_text = els[1][0] if len(els) > 1 else GEO_UNDEF
    existing = first_text != GEO_UNDEF
    handle_last = handle > first_text
    geo, cons = list(geometry), list(constraints)
    if existing:
        g1 = geo[first_text] if 0 <= first_text < len(geo) else {}
        construction = bool(g1.get("construction", False))
        dele = []
        for g, _ in els[1:]:
            if g == GEO_UNDEF:
                continue
            dele.append(g)
            if handle_last:
                handle -= 1                               # the handle comes after every glyph
        geo, cons = del_geometries(geo, cons, dele)
    line = geo[handle] if 0 <= handle < len(geo) else None
    if not line or line.get("type") != "LineSegment":
        raise TextError(f"Failed to set text/font for constraint with index {index}. The operation would result "
                        "in an invalid sketch.")
    path = font_path(font)
    new = text_geometry(text, path, line["start"], line["end"], is_height, construction)
    last = len(geo) - 1
    geo = geo + new
    added = list(range(last + 1, len(geo)))
    nc = text_constraint([(handle, 0)] + [(g, 0) for g in added], text, path, is_height)
    if existing:
        cons.append(nc)
    else:
        keep = {k: v for k, v in c.items() if k not in ("args", "text", "font", "is_text_height")}
        # the constraint keeps its own elements and gets the glyphs after them
        nc["args"] = [int(v) for v in c["args"]] + [v for g in added for v in (g, 0)]
        cons[index] = {**keep, **nc, "name": c.get("name", ""), "driving": c.get("driving", True)}
    return {"geometry": geo, "constraints": cons, "added": added}


# ── `cad feature text` ───────────────────────────────────────────────────────────────────────────────────────

def run(req: dict) -> dict:
    """One request:
        {"op": "fonts"}                                       {"fonts": [names], "paths": {name: path}, "default"}
        {"op": "shapes", "text", "font"}                      base_shapes (the tool's preview)
        {"op": "geometry", "text", "font", "p1", "p2", "height", "construction"}   the glyphs for a handle
        {"op": "set", "geometry", "constraints", "index", "text", "font", "height", "construction"}
                                                              set_text_and_font
    """
    op = req.get("op")
    try:
        if op == "fonts":
            table = fonts()
            return {"fonts": font_names(), "paths": table, "default": default_font()}
        if op == "shapes":
            return base_shapes(str(req.get("text", "")), str(req.get("font") or default_font() or ""))
        if op == "geometry":
            return {"geometry": text_geometry(str(req.get("text", "")), str(req.get("font") or default_font()),
                                              req["p1"], req["p2"], bool(req.get("height", True)),
                                              bool(req.get("construction", False)))}
        if op == "set":
            return set_text_and_font(req["geometry"], req["constraints"], int(req["index"]), str(req.get("text", "")),
                                     str(req.get("font") or default_font()), bool(req.get("height", True)),
                                     bool(req.get("construction", False)))
    except (TextError, KeyError, ValueError, OSError) as e:
        return {"error": str(e) if not isinstance(e, KeyError) else f"missing {e}"}
    return {"error": f"unknown op {op!r}: fonts, shapes, geometry, set"}


def cmd_text(a):
    """`cad feature text [SLUG] --req JSON`: the Sketcher's text from the server (no project file is read or
    written)."""
    from .cmdbase import OK, Result, UsageError
    text = a.req
    if text.startswith("@"):
        with open(text[1:], encoding="utf-8") as f:
            text = f.read()
    try:
        reqs = json.loads(text)
    except ValueError as e:
        raise UsageError(f"--req: {e}") from None
    if isinstance(reqs, dict):
        reqs = [reqs]
    out = [run(r) for r in reqs]
    bad = sum(1 for r in out if "error" in r)
    return Result(OK, {"answers": out}, f"{len(out)} answer(s), {bad} refused", "sketch text")


def add_parser(add, fsub) -> None:
    """featurecmd.add_parsers hands its `add` and `cad feature`'s subparsers here."""
    sp = add("text", cmd_text, "the Sketcher's text (Sketcher_CreateText): fonts, glyph geometry, setTextAndFont "
             "on a sketch: --req JSON, a list of requests", parent=fsub)
    sp.set_defaults(cmd_name="feature text", feature_cmd="text")
    sp.add_argument("slug", nargs="?")
    sp.add_argument("--req", required=True, metavar="JSON", help="the requests (or @file.json)")

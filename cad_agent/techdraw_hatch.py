# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses FreeCAD's TechDraw hatching and keeps FreeCAD's licence, the GNU Lesser General
# Public License, version 2.1 or (at your option) any later version; the text is in ../ui/LICENSE.
#
#   Derived from: src/Mod/TechDraw/App/DrawGeomHatch.cpp (Copyright (c) 2018 WandererFan),
#                 src/Mod/TechDraw/App/DrawHatch.cpp (Copyright (c) 2018 WandererFan),
#                 src/Mod/TechDraw/App/HatchLine.cpp (Copyright (c) 2018 WandererFan),
#                 src/Mod/TechDraw/Gui/QGIFace.cpp (Copyright (c) 2013 Luke Parry),
#                 src/Mod/TechDraw/Gui/PATPathMaker.cpp (Copyright (c) 2022 WandererFan),
#                 src/Mod/TechDraw/PAT/FCPAT.pat and src/Mod/TechDraw/Patterns/*.svg (FreeCAD, LGPL-2.1-or-later)
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
"""Hatching: the PAT patterns of a geometric hatch (DrawGeomHatch) and the SVG tiles of an image hatch (DrawHatch).

A geometric hatch lays the pattern's lines (a PAT file's `*Name` and its `angle, x, y, shift, delta[, dashes]` rows) over
the face's bounding box (DrawGeomHatch::makeEdgeOverlay) and keeps what the face holds (getTrimmedLines: the Common of the
face and the lines). The patterns and tiles are FreeCAD's (cad_agent/techdraw_templates/PAT and Patterns). This module
imports without OCP.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from .techdraw import TEMPLATES_DIR, TechDrawError

PAT_DIR = TEMPLATES_DIR / "PAT"
PATTERNS_DIR = TEMPLATES_DIR / "Patterns"
DEFAULT_PAT = "FCPAT.pat"            # Preferences::patFile
DEFAULT_PATTERN = "Diamond"          # DrawGeomHatch::prefGeomHatchName
DEFAULT_SVG = "simple.svg"           # Preferences::svgFile
SVG_TILE = 64.0                      # QGIFace's SVGSIZEW, SVGSIZEH: a tile in scene units (a tenth of a millimetre)
MAX_SEGMENTS = 10000                 # Preferences PAT/MaxSeg


def pat_files() -> list:
    return sorted(p.name for p in PAT_DIR.glob("*.pat"))


def svg_files() -> list:
    return sorted(p.name for p in PATTERNS_DIR.glob("*.svg"))


def pat_path(name: str) -> Path:
    if name not in pat_files():
        raise TechDrawError(f"{name!r} is not a PAT file the app has ({', '.join(pat_files())})")
    return PAT_DIR / name


def svg_path(name: str) -> Path:
    if name not in svg_files():
        raise TechDrawError(f"{name!r} is not a hatch pattern the app has ({', '.join(svg_files())})")
    return PATTERNS_DIR / name


@dataclass
class PatSpec:
    """PATLineSpec: one row of a pattern."""
    angle: float = 0.0
    origin: tuple = (0.0, 0.0)
    offset: float = 0.0
    interval: float = 1.0
    dashes: list = field(default_factory=list)


def pattern_names(file: str) -> list:
    """PATLineSpec::getPatternList."""
    return names_in(pat_path(file).read_text(errors="replace").splitlines())


def names_in(lines: list) -> list:
    out = []
    for line in lines:
        if line.startswith("*"):
            comma = line.find(",", 1)
            out.append(line[1:comma] if comma >= 0 else line[1:])
    return out


def pattern_specs(file: str, name: str) -> list:
    """PATLineSpec::getSpecsForPattern for a PAT file the app has."""
    return specs_in(pat_path(file).read_text(errors="replace").splitlines(), name)


def specs_in(lines: list, name: str) -> list:
    """The rows under `*name` until the next pattern (findPatternStart, loadPatternDef, PATLineSpec::load)."""
    start = None
    for i, line in enumerate(lines):
        if line.startswith("*"):
            comma = line.find(",", 1)
            if (line[1:comma] if comma >= 0 else line[1:]) == name:
                start = i + 1
                break
    if start is None:
        return []
    rows = []
    for line in lines[start:]:
        line = line.rstrip()
        if line.startswith("*"):
            break
        if not line or line[0] in "; ":
            continue
        rows.append(line)
    specs = []
    for row in rows:
        vals = []
        for cell in row.split(","):
            try:
                vals.append(float(cell))
            except ValueError:
                vals.append(0.0)
        if len(vals) < 5:
            continue
        specs.append(PatSpec(vals[0], (vals[1], vals[2]), vals[3], vals[4], vals[5:]))
    return specs


def edge_overlay(spec: PatSpec, box, scale: float, rotation: float) -> list:
    """DrawGeomHatch::makeEdgeOverlay: the segments ((x0, y0), (x1, y1)) that cover box = (minX, minY, maxX, maxY)."""
    min_x, min_y, max_x, max_y = box
    top_left, top_right = (min_x, max_y), (max_x, max_y)
    bottom_left, bottom_right = (min_x, min_y), (max_x, min_y)
    ox, oy = spec.origin[0] * scale, spec.origin[1] * scale
    interval, offset = spec.interval * scale, spec.offset * scale
    angle = spec.angle + rotation
    a = math.radians(rotation)
    ox, oy = ox * math.cos(a) - oy * math.sin(a), ox * math.sin(a) + oy * math.cos(a)
    if scale == 0.0 or interval == 0.0:
        return []
    h = math.radians(angle)
    d = (math.cos(h), math.sin(h))
    perp = (-d[1], d[0])
    step = (offset * d[0] + interval * perp[0], offset * d[1] + interval * perp[1])
    proj = [((p[0] - ox) * perp[0] + (p[1] - oy) * perp[1]) / interval for p in (top_left, top_right, bottom_left, bottom_right)]
    first, last = math.ceil(min(proj)), math.floor(max(proj))
    dashes = list(spec.dashes)
    global_step = 0.0
    if not dashes:
        diag = math.dist(top_right, bottom_left)
        dashes = [2.0 * diag]
        global_step = diag
    else:
        dashes = [x * scale for x in dashes]
        global_step = sum(abs(x) for x in dashes)
    if global_step == 0.0:
        return []
    out = []
    for i in range(first, last + 1):
        cx, cy = ox + i * step[0], oy + i * step[1]
        if abs(d[0]) > abs(d[1]):
            if d[0] > 0.0:
                j0, j1 = math.floor((min_x - cx) / (global_step * d[0])), math.ceil((max_x - cx) / (global_step * d[0]))
            else:
                j0, j1 = math.floor((max_x - cx) / (global_step * d[0])), math.ceil((min_x - cx) / (global_step * d[0]))
        else:
            if d[1] > 0.0:
                j0, j1 = math.floor((min_y - cy) / (global_step * d[1])), math.ceil((max_y - cy) / (global_step * d[1]))
            else:
                j0, j1 = math.floor((max_y - cy) / (global_step * d[1])), math.ceil((min_y - cy) / (global_step * d[1]))
        for j in range(j0, j1):
            cur = (cx + j * global_step * d[0], cy + j * global_step * d[1])
            for ln in dashes:
                nxt = (cur[0] + abs(ln) * d[0], cur[1] + abs(ln) * d[1])
                if ln > 0.0 and (cur[0] >= min_x or nxt[0] >= min_x) and (cur[0] <= max_x or nxt[0] <= max_x) \
                        and (cur[1] >= min_y or nxt[1] >= min_y) and (cur[1] <= max_y or nxt[1] <= max_y):
                    out.append((cur, nxt))
                cur, nxt = nxt, cur
        if len(out) > MAX_SEGMENTS:
            return []
    return out


def face_of(wire):
    """DrawGeomHatch::extractFace: the wire's face on the paper plane, mirrored in y (the paper's y is down)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_Transform
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pln, gp_Pnt, gp_Trsf
    mk = BRepBuilderAPI_MakeFace(gp_Pln(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), wire, True)
    if not mk.IsDone():
        return None
    t = gp_Trsf()
    t.SetMirror(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 1, 0)))
    from OCP.TopoDS import TopoDS
    return TopoDS.Face(BRepBuilderAPI_Transform(mk.Face(), t).Shape())


def trimmed_lines(face, specs: list, scale: float, rotation: float = 0.0, offset: tuple = (0.0, 0.0, 0.0)) -> list:
    """DrawGeomHatch::getTrimmedLines: for each row of the pattern the segments ((x0, y0), (x1, y1)) the face holds."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRep import BRep_Builder, BRep_Tool
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_Transform
    from OCP.gp import gp_Pnt, gp_Trsf, gp_Vec
    from OCP.TopExp import TopExp
    from OCP.TopoDS import TopoDS_Compound
    from .techdraw_view import _box, _edges_of
    if face is None or not specs:
        return []
    bbox = Bnd_Box()
    BRepBndLib.AddOptimal_s(face, bbox)
    bbox.SetGap(0.0)
    x0, y0, _, x1, y1, _ = _box(bbox)
    box = (x0 - offset[0], y0 - offset[1], x1 - offset[0], y1 - offset[1])
    out = []
    for spec in specs:
        segs = edge_overlay(spec, box, scale, rotation)
        b = BRep_Builder()
        grid = TopoDS_Compound()
        b.MakeCompound(grid)
        for p, q in segs:
            b.Add(grid, BRepBuilderAPI_MakeEdge(gp_Pnt(p[0], p[1], 0.0), gp_Pnt(q[0], q[1], 0.0)).Edge())
        t = gp_Trsf()
        t.SetTranslation(gp_Vec(offset[0], offset[1], 0.0))
        grid = BRepBuilderAPI_Transform(grid, t, True).Shape()
        common = BRepAlgoAPI_Common(face, grid)
        if not common.IsDone() or common.Shape().IsNull():
            return out
        lines, seen = [], []
        for e in _edges_of(common.Shape()):
            if any(e.IsSame(k) for k in seen):
                continue
            seen.append(e)
            a, c = BRep_Tool.Pnt_s(TopExp.FirstVertex_s(e)), BRep_Tool.Pnt_s(TopExp.LastVertex_s(e))
            lines.append(((a.X(), a.Y()), (c.X(), c.Y())))
        out.append(lines)
    return out


# ── image hatches ────────────────────────────────────────────────────────────────────────────────────────────

SVG_DEFAULT_COLOR = "#000000"        # QGIFace's SVGCOLDEFAULT: what a tile's strokes are replaced from


def tile_svg(name: str, color: str = SVG_DEFAULT_COLOR) -> str:
    """The pattern file as QGIFace uses it as a tile: its content, the strokes in `color` (loadSvgHatch's brute force
    find and replace of `stroke:#000000`)."""
    text = svg_path(name).read_text(errors="replace")
    text = re.sub(r"<\?xml[^>]*\?>", "", text)
    return text.replace("stroke:" + SVG_DEFAULT_COLOR, "stroke:" + color).replace('stroke="' + SVG_DEFAULT_COLOR + '"', 'stroke="' + color + '"')


# ── what a page holds ────────────────────────────────────────────────────────────────────────────────────────

def wire_loop(wire, samples: int = 24) -> list:
    """A face's wire as a polygon in the view's paper coordinates (y down), a curve sampled `samples` times."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepTools import BRepTools_WireExplorer
    from OCP.TopAbs import TopAbs_REVERSED
    pts: list = []
    ex = BRepTools_WireExplorer(wire)
    while ex.More():
        e = ex.Current()
        a = BRepAdaptor_Curve(e)
        f, l = a.FirstParameter(), a.LastParameter()
        n = 1 if a.GetType() == 0 else samples
        seg = [(a.Value(f + (l - f) * k / n).X(), a.Value(f + (l - f) * k / n).Y()) for k in range(n + 1)]
        if e.Orientation() == TopAbs_REVERSED:
            seg.reverse()
        pts += seg if not pts else seg[1:]
        ex.Next()
    return [list(p) for p in pts]


def results(doc) -> dict:
    """Each hatch of a recomputed PageDocument as the page draws it: {name: {"kind", "view", "faces": {"Face0": ...}}} with,
    for a geometric hatch, the segments the pattern leaves in each face ([x0, y0, x1, y1] in the view's paper
    coordinates, y down, millimetres) and for an image hatch the face's outline."""
    from . import techdraw as T
    from . import techdraw_cosmetic as C
    out = {}
    for h in doc.objects:
        if not isinstance(h, (T.DrawHatch, T.DrawGeomHatch)):
            continue
        view, geo = doc.get(h.source), doc.geo.get(h.source)
        if view is None or geo is None:
            continue
        try:
            wires = C.faces_of(geo, view)
        except Exception:
            continue
        faces = {}
        for f in h.faces:
            i = int(f[4:])
            if i >= len(wires):
                continue
            if isinstance(h, T.DrawGeomHatch):
                specs = pattern_specs(h.file_pattern, h.name_pattern)
                sets = trimmed_lines(face_of(wires[i]), specs, h.scale_pattern, h.pattern_rotation, tuple(h.pattern_offset))
                faces[f] = {"lines": [[a[0], -a[1], b[0], -b[1]] for lines in sets for a, b in lines]}
            else:
                faces[f] = {"loop": wire_loop(wires[i])}
        d = {"kind": "geom" if isinstance(h, T.DrawGeomHatch) else "svg", "view": h.source, "faces": faces}
        if isinstance(h, T.DrawGeomHatch):
            d.update(color=list(h.color_pattern), weight=h.weight_pattern)
        else:
            d.update(color=list(h.hatch_color), scale=h.hatch_scale, rotation=h.hatch_rotation, offset=list(h.hatch_offset),
                     pattern=h.hatch_pattern)
        out[h.name] = d
    return out

# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses what FreeCAD's TechDraw commands do to a document and keeps FreeCAD's
# licence, the GNU Lesser General Public License, version 2.1 or (at your option) any later version; the text is in
# ../ui/LICENSE.
#
#   Derived from: src/Mod/TechDraw/Gui/Command.cpp (Copyright (c) 2002 Jürgen Riegel, 2014 Luke Parry),
#                 src/Mod/TechDraw/Gui/CommandCreateDims.cpp (Copyright (c) 2014 Luke Parry, 2022 WandererFan),
#                 src/Mod/TechDraw/Gui/CommandAnnotate.cpp (Copyright (c) 2019 WandererFan),
#                 src/Mod/TechDraw/Gui/TaskProjGroup.cpp (Copyright (c) 2014 Joe Dowsett, 2014 Luke Parry),
#                 src/Mod/TechDraw/Gui/TaskSectionView.cpp (Copyright (c) 2016 WandererFan),
#                 src/Mod/TechDraw/Gui/QGVPage.cpp (Copyright (c) 2013 Luke Parry),
#                 src/Mod/TechDraw/App/DrawPage.cpp (Copyright (c) 2002 Jürgen Riegel),
#                 src/Mod/TechDraw/App/DrawProjGroup.cpp (Copyright (c) 2014 Joe Dowsett),
#                 src/Mod/TechDraw/App/DrawViewPart.cpp (Copyright (c) 2002 Jürgen Riegel, 2013 Luke Parry, 2016 WandererFan)
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
"""The app's and the CLI's edits of a project's TechDraw pages, written back into techdraw/<Page>.py as Python.

read(pdir, page) gives the page as the tree, the property view and the task panels show it (its objects, and with
recompute its geometry); apply(pdir, page, ops) runs FreeCAD's commands on it and writes the PAGE list back, all or
nothing: an entry the edit did not change keeps its text, a changed one is written again, a new one goes in at its
place in the document's order.

The ops (each is what the FreeCAD command named does):

    {"op": "new_page", "template"?}                   TechDraw_PageDefault / _PageTemplate: Page + Template
    {"op": "view", "source": [part], "direction"?, "x_direction"?, "name"?}
                                                      TechDraw_View: a DrawProjGroupItem "View" at the page centre
    {"op": "projgroup", "source": [part], "direction"?, "x_direction"?, "projections"?: ["Top", ...]}
                                                      TechDraw_ProjectionGroup: ProjGroup with its Front, then
                                                      TaskProjGroup's checkboxes (addProjection)
    {"op": "projection", "group": g, "type": "Top", "on": bool}   TaskProjGroup: a projection checked or unchecked
    {"op": "section", "base_view": v, "direction": "Right"|"Left"|"Up"|"Down", "origin"?, "symbol"?}
                                                      TechDraw_SectionView, TaskSectionView's arrow and OK
    {"op": "dimension", "type": "Distance"|"DistanceX"|"DistanceY"|"Radius"|"Diameter"|"Angle"|"Angle3Pt",
     "references": [[view, "Edge3"], ...]}            TechDraw_*Dimension on a selection (dimMaker, positionDimText)
    {"op": "balloon", "view": v, "origin": [x, y], "at"?: [x, y]}  TechDraw_Balloon, clicked at origin (view coords)
    {"op": "annotation", "text"?: [lines], "at"?: [x, y]}         TechDraw_Annotation
    {"op": "set", "name": n, "props": {...}}          the property view
    {"op": "move", "name": n, "x": X, "y": Y}         a view dragged on the page (QGIView::mouseReleaseEvent)
    {"op": "delete", "name": n}                       Std_Delete (a view's dimensions and balloons go with it)
    {"op": "rename", "name": n, "to": m} / {"op": "label", "name": n, "to": text}
"""
from __future__ import annotations

import ast
import json
import math
import re
from pathlib import Path

from . import techdraw as T

DIR = "techdraw"
LIST = "PAGE"
PREFIX = "TechDraw."
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class TechDrawEditError(ValueError):
    pass


# ── reading ───────────────────────────────────────────────────────────────────────────────────────────

def pages(pdir) -> list[str]:
    d = Path(pdir) / DIR
    return sorted(p.stem for p in d.glob("*.py") if not p.stem.startswith(("_", "."))) if d.is_dir() else []


def page_file(pdir, page: str) -> Path:
    if not (isinstance(page, str) and NAME.match(page)):
        raise TechDrawEditError(f"{page!r} is not a page name")
    return Path(pdir) / DIR / f"{page}.py"


def _list_node(tree):
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == LIST for t in node.targets):
            if not isinstance(node.value, ast.List):
                raise TechDrawEditError(f"{LIST} is not a list the app can edit")
            return node.value
    return None


def _kind(call):
    f = call.func
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "TechDraw":
        return f.attr
    return None


def _value(node, src):
    try:
        return ast.literal_eval(node)
    except ValueError:
        raise TechDrawEditError(f"{ast.get_source_segment(src, node)!r} is not a literal the app can read") from None


def entries(src: str):
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        raise TechDrawEditError(f"the page does not parse: {e}") from None
    lst = _list_node(tree)
    if lst is None:
        return None
    out = []
    for e in lst.elts:
        cls = T.CLASSES.get(_kind(e)) if isinstance(e, ast.Call) else None
        if cls is None:
            raise TechDrawEditError(f"{LIST} holds {ast.get_source_segment(src, e)[:60]!r}, not a TechDraw."
                                    f"{'/'.join(T.CLASSES)} call")
        args = [_value(a, src) for a in e.args]
        kw = {k.arg: _value(k.value, src) for k in e.keywords}
        try:
            out.append((cls(*args, **kw), e))
        except (TypeError, ValueError) as err:
            raise TechDrawEditError(str(err)) from None
    return out


def objects_of(src: str):
    es = entries(src)
    return None if es is None else [o for o, _ in es]


TREE_ICONS = {"DrawPage": "TechDraw_TreePage", "DrawSVGTemplate": "TechDraw_TreePageTemplate",
              "DrawViewPart": "TechDraw_TreeView", "DrawProjGroupItem": "TechDraw_TreeView",
              "DrawProjGroup": "TechDraw_TreeProjGroup", "DrawViewSection": "TechDraw_TreeSection",
              "DrawViewDimension": "TechDraw_Dimension", "DrawViewBalloon": "TechDraw_Balloon",
              "DrawViewAnnotation": "TechDraw_TreeAnnotation"}
DIM_ICONS = {"Distance": "TechDraw_LengthDimension", "DistanceX": "TechDraw_HorizontalDimension",
             "DistanceY": "TechDraw_VerticalDimension", "Radius": "TechDraw_RadiusDimension",
             "Diameter": "TechDraw_DiameterDimension", "Angle": "TechDraw_AngleDimension",
             "Angle3Pt": "TechDraw_3PtAngleDimension"}


def tree(objs) -> list:
    """The tree's rows as FreeCAD shows a page (ViewProviderPage::claimChildren: the Template, then the page's views;
    a group claims its items, a view its dimensions and balloons; a section stays on the page)."""
    by = {o.name: o for o in objs}
    page = next((o for o in objs if isinstance(o, T.DrawPage)), None)
    if page is None:
        return []
    doc = T.PageDocument(objs)
    claimed: dict = {}
    for o in objs:
        parent = None
        if isinstance(o, (T.DrawViewDimension,)):
            parent = o.view()
        elif isinstance(o, T.DrawViewBalloon):
            parent = o.source_view
        elif isinstance(o, T.DrawProjGroupItem) and doc.group_of(o.name) is not None:
            parent = doc.group_of(o.name).name
        if parent in by:
            claimed.setdefault(parent, []).append(o.name)
    rows = []

    def add(name, depth):
        o = by[name]
        icon = DIM_ICONS.get(o.type, "TechDraw_Dimension") if isinstance(o, T.DrawViewDimension) else TREE_ICONS[o.kind]
        rows.append({"name": o.name, "label": o.label or o.name, "type": o.TYPE_ID, "kind": o.kind,
                     "depth": depth, "icon": icon})
        for c in claimed.get(name, []):
            add(c, depth + 1)
    rows.append({"name": page.name, "label": page.label or page.name, "type": page.TYPE_ID, "kind": page.kind,
                 "depth": 0, "icon": TREE_ICONS["DrawPage"]})
    if page.template in by:
        add(page.template, 1)
    kids = {n for v in claimed.values() for n in v}
    for o in doc.page_views():
        if o.name not in kids:
            add(o.name, 1)
    return rows


def read_src(src: str, page: str = "", slug: str = "") -> dict:
    objs = objects_of(src) or []
    return {"project": slug, "page": page, "objects": [T.as_dict(o) for o in objs], "tree": tree(objs)}


def read(pdir, page: str) -> dict:
    path = page_file(pdir, page)
    if not path.exists():
        raise TechDrawEditError(f"there is no page {page!r} (techdraw/{page}.py)")
    return read_src(path.read_text(), page, Path(pdir).name)


def shape_loader(slug: str):
    """shape_of(part) for PageDocument: the part built (state.build_part, the build cache), a compound holding one
    solid taken as that solid (a Body's Shape is its solid in FreeCAD)."""
    from .state import build_part
    cache = {}

    def shape_of(part):
        if part not in cache:
            solid, _ = build_part(slug, part)
            s = solid.wrapped
            from OCP.TopAbs import TopAbs_COMPOUND, TopAbs_SOLID
            from OCP.TopoDS import TopoDS_Iterator
            if s.ShapeType() == TopAbs_COMPOUND:
                it = TopoDS_Iterator(s)
                kids = []
                while it.More():
                    kids.append(it.Value())
                    it.Next()
                if len(kids) == 1 and kids[0].ShapeType() == TopAbs_SOLID:
                    s = kids[0]
            cache[part] = s
        return cache[part]
    return shape_of


def recomputed(pdir, page: str, objs=None, svg: bool = False) -> dict:
    """read() and the page recomputed (techdraw.PageDocument.result()); with svg the page drawn
    (techdraw_export.page_svg), which the workbench shows."""
    pdir = Path(pdir)
    out = read(pdir, page) if objs is None else read_src_objs(objs, page, pdir.name)
    objs = objs if objs is not None else objects_of(page_file(pdir, page).read_text())
    doc = T.PageDocument(objs, shape_loader(pdir.name), pdir.name).recompute()
    out["result"] = doc.result()
    if svg:
        from .techdraw_export import page_svg
        out["svg"] = page_svg(doc, interactive=True)
    return out


def page_document(pdir, page: str):
    """The page's techdraw.PageDocument, recomputed."""
    pdir = Path(pdir)
    objs = objects_of(page_file(pdir, page).read_text()) if page_file(pdir, page).exists() else None
    if objs is None:
        raise TechDrawEditError(f"there is no page {page!r} (techdraw/{page}.py)")
    return T.PageDocument(objs, shape_loader(pdir.name), pdir.name).recompute()


def read_src_objs(objs, page, slug):
    return {"project": slug, "page": page, "objects": [T.as_dict(o) for o in objs], "tree": tree(objs)}


# ── writing ───────────────────────────────────────────────────────────────────────────────────────────

def lit(v) -> str:
    if v is None:
        return "None"
    if isinstance(v, bool):
        return "True" if v else "False"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, dict):
        return "{" + ", ".join(f"{lit(k)}: {lit(x)}" for k, x in v.items()) + "}"
    if isinstance(v, (list, tuple)):
        inner = ", ".join(lit(x) for x in v)
        if isinstance(v, tuple):
            return f"({inner},)" if len(v) == 1 else f"({inner})"
        return f"[{inner}]"
    raise TechDrawEditError(f"{v!r} cannot be written in a page file")


def obj_src(o: T.TDObject) -> str:
    keep = {k for k in o.DEFAULTS if not o.is_default(k)}
    if isinstance(o, T.DrawSVGTemplate):
        keep.add("template")
    parts = [json.dumps(o.name)]
    npos = 0
    for k in o.POS:
        if k not in keep:
            break
        parts.append(lit(o.source_value(k)))
        npos += 1
    for k in o.DEFAULTS:
        if k in o.POS[:npos] or k not in keep:
            continue
        parts.append(f"{k}={lit(o.source_value(k))}")
    return f"{PREFIX}{o.kind}({', '.join(parts)})"


def _same(a, b) -> bool:
    return type(a) is type(b) and T.as_dict(a) == T.as_dict(b)


TEMPLATE = '''"""{page}: a TechDraw page of {slug} (FreeCAD's TechDraw workbench).

PAGE is the page's document objects in FreeCAD's order: the DrawPage, its template, its views, dimensions, balloons
and annotations; the app and `cad techdraw ...` edit it (cad_agent/techdraw_edit.py). Nothing drawn is stored: the
views' lines, the dimensions' values and texts are recomputed from the parts.
"""
from cad_agent import techdraw as TechDraw

PAGE = [
]
'''


def write_src(src: str, objects) -> str:
    from .feature_edit import _Text
    t = _Text(src)
    lst = _list_node(t.tree)
    if lst is None:
        raise TechDrawEditError("the page file has no PAGE list")
    old = entries(src)
    by_name = {o.name: (o, call) for o, call in old}
    ind = lst.elts[0].col_offset if lst.elts else 4
    lines = []
    for o in objects:
        prev = by_name.get(o.name)
        if prev is not None and _same(prev[0], o):
            text = t.raw[t.a(prev[1]):t.b(prev[1])].decode()
            end = t.after_comma(t.b(prev[1]))
            rest = t.raw[end:t.line_end(end)].decode().rstrip("\n")
            comment = rest if rest.strip().startswith("#") else ""
            out = text.split("\n")
            col = prev[1].col_offset
            text = "\n".join([out[0]] + [ln[col:] if ln[:col].strip() == "" else ln for ln in out[1:]])
            lines.append(" " * ind + text.replace("\n", "\n" + " " * ind) + "," + comment)
        else:
            lines.append(" " * ind + obj_src(o) + ",")
    body = "[\n" + "".join(line + "\n" for line in lines) + "]" if lines else "[\n]"
    return t.edit([(t.a(lst), t.b(lst), body)])


# ── names ─────────────────────────────────────────────────────────────────────────────────────────────

def project_names(pdir, skip_page: str | None = None) -> set:
    """Every object name of the project's pages but one's (FreeCAD's one document: names are unique)."""
    out = set()
    for p in pages(pdir):
        if p == skip_page:
            continue
        try:
            out |= {o.name for o in objects_of(page_file(pdir, p).read_text()) or []}
        except TechDrawEditError:
            pass
    return out


def unique_name(base: str, taken: set) -> str:
    """App::Document::getUniqueObjectName: base, then base001, base002 ..."""
    if base not in taken:
        return base
    m = re.match(r"^(.*?)(\d+)$", base)
    stem = m.group(1) if m else base
    i = 1
    while f"{stem}{i:03d}" in taken:
        i += 1
    return f"{stem}{i:03d}"


def unique_label(base: str, taken: set) -> str:
    """A Label made unique as FreeCAD does when it would clash (base001, ...)."""
    return unique_name(base, taken)


# ── the ops ───────────────────────────────────────────────────────────────────────────────────────────

class Session:
    """The page being edited: its objects and the names taken in the whole project."""

    def __init__(self, pdir, page, objs, part_names, shape_of=None):
        self.pdir = Path(pdir) if pdir else Path("golden")
        self.page = page
        self.objs = list(objs)
        self.taken = (project_names(pdir, page) if pdir else set()) | {o.name for o in self.objs}
        self.part_names = part_names
        self.shape_of = shape_of or shape_loader(self.pdir.name)

    def doc(self):
        return T.PageDocument(self.objs)

    def get(self, name, cls=None, what="object"):
        o = next((x for x in self.objs if x.name == name), None)
        if o is None or (cls is not None and not isinstance(o, cls)):
            raise TechDrawEditError(f"there is no {what} {name!r} on {self.page}")
        return o

    def name(self, base, want=None):
        if want is not None:
            if not (isinstance(want, str) and NAME.match(want)):
                raise TechDrawEditError(f"{want!r} is not a name FreeCAD takes (letters, digits and _)")
            if want in self.taken:
                raise TechDrawEditError(f"there is already an object {want!r}")
            n = want
        else:
            n = unique_name(base, self.taken)
        self.taken.add(n)
        return n

    def add(self, o, after=None):
        if after is None:
            self.objs.append(o)
        else:
            i = max(i for i, x in enumerate(self.objs) if x.name in after)
            self.objs.insert(i + 1, o)
        return o

    def page_obj(self):
        p = next((o for o in self.objs if isinstance(o, T.DrawPage)), None)
        if p is None:
            raise TechDrawEditError(f"{self.page} has no DrawPage")
        return p

    def center(self):
        w, h = T.PageDocument(self.objs).page_size()
        return w / 2.0, h / 2.0

    def labels(self):
        return {o.label or o.name for o in self.objs}

    def check_parts(self, parts):
        if isinstance(parts, str):
            parts = [parts]
        if not parts:
            raise TechDrawEditError("No shapes, groups, or links in this selection")
        for p in parts:
            if self.part_names is not None and p not in self.part_names:
                raise TechDrawEditError(f"there is no part {p!r} in the project (parts: {', '.join(self.part_names)})")
        return tuple(parts)


def _vec(v, what, default):
    if v is None:
        return default
    if not (isinstance(v, (list, tuple)) and len(v) == 3):
        raise TechDrawEditError(f"{what}: {v!r} is not a vector (x, y, z)")
    return tuple(float(x) for x in v)


def check_direction_vs_basis(d):
    """Command.cpp's checkDirectionVsBasis: a direction within 1e-6 of a basis vector is snapped onto it."""
    out = []
    for axis in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
        for sgn in (1, -1):
            b = tuple(sgn * c for c in axis)
            if math.dist(d, b) < 1e-6:
                return b
    return d


def local_vector_to_cs(direction, x_direction, local):
    """DrawViewPart::localVectorToCS: the CS of a direction given as an (x, y) vector in a view's coordinates."""
    from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Vec
    from .techdraw_view import projection_cs
    cs = projection_cs(direction, x_direction)
    angle = math.atan2(local[1], local[0])
    axis = gp_Ax1(gp_Pnt(0, 0, 0), cs.Direction())
    old_x = gp_Vec(cs.XDirection())
    new_dir = old_x.Rotated(axis, angle)
    new_y = gp_Vec(cs.Direction())
    new_x = new_dir.Crossed(new_y).Reversed()
    if new_x.IsParallel(old_x, 0.0001):
        new_x = old_x
    d, x = gp_Dir(new_dir), gp_Dir(new_x)
    return (d.X(), d.Y(), d.Z()), (x.X(), x.Y(), x.Z())


# TaskSectionView's arrow buttons: the view direction in the base view (VectorEditWidget) and the compass angle
SECTION_ARROWS = {"Up": ((0.0, 1.0, 0.0), 90.0), "Down": ((0.0, -1.0, 0.0), 270.0),
                  "Left": ((-1.0, 0.0, 0.0), 180.0), "Right": ((1.0, 0.0, 0.0), 0.0)}


def required_rotation(angle: float) -> float:
    """TaskSectionView::requiredRotation."""
    r = angle - 90.0
    return 0.0 if r == 180.0 else r


def run_ops(s: Session, ops) -> list:
    done = []
    for k, op in enumerate(ops):
        if not isinstance(op, dict) or "op" not in op:
            raise TechDrawEditError(f"op {k} is not an edit: {op!r}")
        kind = op["op"]
        if kind == "new_page":
            if any(isinstance(o, T.DrawPage) for o in s.objs):
                raise TechDrawEditError(f"{s.page} already has a DrawPage")
            tname = op.get("template") or T.DEFAULT_TEMPLATE
            T.template_path(tname)
            pg = s.name("Page", s.page if s.page not in s.taken else None)
            tp = s.name("Template")
            texts = T.autofill(tname, op.get("title") or s.pdir.name)
            s.add(T.DrawPage(pg, tp))
            s.add(T.DrawSVGTemplate(tp, template=tname, editable_texts=texts))
            done.append(f"made {pg} with {tp} ({tname})")
        elif kind == "view":
            parts = s.check_parts(op.get("source"))
            s.page_obj()
            n = s.name("View", op.get("name"))
            d = check_direction_vs_basis(_vec(op.get("direction"), "direction", (0.0, -1.0, 0.0)))
            x = _vec(op.get("x_direction"), "x_direction", (1.0, 0.0, 0.0))
            cx, cy = s.center()
            s.add(T.DrawProjGroupItem(n, source=parts, direction=d, x_direction=x, x=cx, y=cy,
                                      scale=s.page_obj().scale))
            done.append(f"made {n} of {', '.join(parts)}")
        elif kind == "projgroup":
            parts = s.check_parts(op.get("source"))
            s.page_obj()
            g = s.name("ProjGroup", op.get("name"))
            d = check_direction_vs_basis(_vec(op.get("direction"), "direction", (0.0, -1.0, 0.0)))
            x = _vec(op.get("x_direction"), "x_direction", (1.0, 0.0, 0.0))
            cx, cy = s.center()
            front = s.name("ProjItem")
            s.add(T.DrawProjGroup(g, source=parts, views=(front,), anchor=front, x=cx, y=cy,
                                  scale=s.page_obj().scale))
            s.add(T.DrawProjGroupItem(front, type="Front", direction=d, x_direction=x, lock_position=True,
                                      label=unique_label("Front", s.labels())))
            done.append(f"made {g} of {', '.join(parts)} with {front} (Front)")
            for t in op.get("projections") or ():
                if t != "Front":
                    done.append(_projection(s, s.get(g, T.DrawProjGroup), t, True))
        elif kind == "projection":
            o = s.get(op.get("group"))
            if isinstance(o, T.DrawProjGroupItem) and s.doc().group_of(o.name) is None:
                if not op.get("on", True) or op.get("type") == "Front":
                    done.append(f"{o.name} has no {op.get('type')}")
                    continue
                o = _view_to_group(s, o)          # TaskProjGroup::turnViewToProjGroup, on the first box ticked
                done.append(f"made {o.name} of {o.views[0]}")
            if not isinstance(o, T.DrawProjGroup):
                raise TechDrawEditError(f"there is no projection group {op.get('group')!r} on {s.page}")
            done.append(_projection(s, o, op.get("type"), op.get("on", True)))
            g = s.get(o.name)
            if len(g.views) == 1 and not op.get("on", True):
                done.append(_group_to_view(s, g))  # turnProjGroupToView: only the Front is left
        elif kind == "rotate":
            done.append(_rotate(s, s.get(op.get("name")), op.get("motion")))
        elif kind == "section":
            done.append(_section(s, op))
        elif kind == "section_edit":
            done.append(_section_edit(s, op))
        elif kind == "dimension":
            done.append(_dimension(s, op))
        elif kind == "balloon":
            v = s.get(op.get("view"), T.DrawViewPart, "view")
            n = s.name("Balloon", op.get("name"))
            page = s.page_obj()
            origin = op.get("origin") or [0.0, 0.0]
            at = op.get("at") or [origin[0] + 10.0, origin[1] + 10.0]
            s.add(T.DrawViewBalloon(n, source_view=v.name, origin_x=float(origin[0]), origin_y=float(origin[1]),
                                    text=str(page.next_balloon_index), x=float(at[0]), y=float(at[1])))
            page.next_balloon_index += 1
            done.append(f"made {n} on {v.name}")
        elif kind == "annotation":
            n = s.name("Annotation", op.get("name"))
            s.page_obj()
            cx, cy = s.center()
            at = op.get("at") or [cx, cy]
            text = op.get("text") or ["Default Text"]
            s.add(T.DrawViewAnnotation(n, text=text, x=float(at[0]), y=float(at[1])))
            done.append(f"made {n}")
        elif kind == "set":
            o = s.get(op.get("name"))
            props = dict(op.get("props") or {})
            d = T.as_dict(o)
            for key, v in props.items():
                if key == "type" and isinstance(o, T.DrawViewDimension):
                    d["dim_type"] = v
                    d["format_spec"] = None     # DrawViewDimension::onChanged(Type): the default for the type
                elif key == "type" and isinstance(o, T.DrawProjGroupItem):
                    d["item_type"] = v
                elif key not in o.DEFAULTS:
                    raise TechDrawEditError(f"{key} is not a property of a {o.kind}")
                else:
                    d[key] = v
            new = _rebuilt(o, d)
            s.objs[s.objs.index(o)] = new
            if isinstance(new, T.DrawProjGroup) and "source" in props:
                pass                            # updateChildrenSource: the items take the group's at recompute
            done.append(f"set {o.name}: {', '.join(props)}")
        elif kind == "move":
            o = s.get(op.get("name"))
            if not hasattr(o, "x"):
                raise TechDrawEditError(f"{o.name} has no position")
            if getattr(o, "lock_position", False):
                raise TechDrawEditError(f"{o.name} is locked (LockPosition)")
            d = T.as_dict(o)
            d["x"], d["y"] = float(op.get("x")), float(op.get("y"))
            s.objs[s.objs.index(o)] = _rebuilt(o, d)
            g = s.doc().group_of(o.name)
            if g is not None and g.auto_distribute:      # a dragged item stops auto distributing the group
                gd = T.as_dict(g)
                gd["auto_distribute"] = False
                s.objs[s.objs.index(g)] = _rebuilt(g, gd)
            done.append(f"moved {o.name}")
        elif kind == "delete":
            done.append(_delete(s, op.get("name")))
        elif kind == "rename":
            done.append(_rename(s, op.get("name"), op.get("to")))
        elif kind == "label":
            o = s.get(op.get("name"))
            d = T.as_dict(o)
            d["label"] = op.get("to") or None
            s.objs[s.objs.index(o)] = _rebuilt(o, d)
            done.append(f"labelled {o.name} {op.get('to')!r}")
        else:
            raise TechDrawEditError(f"{kind!r} is not a TechDraw edit (new_page, view, projgroup, projection, "
                                    "section, dimension, balloon, annotation, set, move, delete, rename, label)")
    return done


def _rebuilt(o, d):
    try:
        return T.from_dict(d)
    except (TypeError, ValueError) as e:
        raise TechDrawEditError(str(e)) from None


def _projection(s: Session, g, t, on: bool) -> str:
    """TaskProjGroup::viewToggled: DrawProjGroup::addProjection / removeProjection."""
    if t not in T.ITEM_TYPES:
        raise TechDrawEditError(f"{t!r} is not a projection ({', '.join(T.ITEM_TYPES)})")
    have = {s.get(n).type: n for n in g.views}
    if on:
        if t in have:
            return f"{g.name} already has {t}"
        anchor = s.get(g.anchor, T.DrawProjGroupItem)
        from .techdraw_view import dirs_from_front
        d, x = dirs_from_front(anchor.direction, anchor.x_direction, t)
        n = s.name("ProjItem")
        s.add(T.DrawProjGroupItem(n, type=t, direction=d, x_direction=x, label=unique_label(t, s.labels())),
              after=set(g.views))
        gd = T.as_dict(g)
        gd["views"] = list(g.views) + [n]
        s.objs[s.objs.index(g)] = _rebuilt(g, gd)
        return f"added {n} ({t}) to {g.name}"
    if t not in have:
        return f"{g.name} has no {t}"
    if t == "Front":
        raise TechDrawEditError("the Front projection is the group's anchor and stays")
    n = have[t]
    _delete(s, n)
    gd = T.as_dict(s.get(g.name))
    gd["views"] = [v for v in gd["views"] if v != n]
    s.objs[s.objs.index(s.get(g.name))] = _rebuilt(s.get(g.name), gd)
    return f"removed {n} ({t}) from {g.name}"


def _view_to_group(s: Session, v) -> T.DrawProjGroup:
    """TaskProjGroup::turnViewToProjGroup: a group at the view's place, scale and scale type, with the view as its
    anchor: labelled Front, at the group's origin, ScaleType Custom, its position locked."""
    g = s.name("ProjGroup")
    grp = T.DrawProjGroup(g, source=v.source, views=(v.name,), anchor=v.name, x=v.x, y=v.y, scale=v.scale,
                          scale_type=v.scale_type, projection_type="First angle")   # Preferences::projectionAngle()
    d = T.as_dict(v)
    d.update(x=0.0, y=0.0, scale_type="Custom", label="Front", lock_position=True, source=[])
    i = s.objs.index(v)
    s.objs[i] = _rebuilt(v, d)
    s.objs.insert(i, grp)
    return grp


def _group_to_view(s: Session, g) -> str:
    """TaskProjGroup::turnProjGroupToView: the anchor back on the page at the group's place, the group deleted."""
    a = s.get(g.anchor, T.DrawProjGroupItem)
    d = T.as_dict(a)
    d.update(x=g.x, y=g.y, scale=g.scale, scale_type=g.scale_type, label="View", lock_position=False,
             source=list(g.source))
    i = s.objs.index(g)
    s.objs[s.objs.index(a)] = _rebuilt(a, d)
    s.objs.pop(i)
    return f"{a.name} is a view again"


ROTATIONS = {"Right": "Left", "Left": "Right", "Up": "Bottom", "Down": "Top"}     # DrawViewPart::rotate


def _rotate(s: Session, o, motion) -> str:
    """TaskProjGroup::rotateButtonClicked: DrawViewPart::rotate / spin, or the group's anchor turned and
    updateSecondaryDirs; Front puts the view back to (0, -1, 0)."""
    from .techdraw_view import dirs_from_front
    group = o if isinstance(o, T.DrawProjGroup) else None
    view = s.get(group.anchor, T.DrawProjGroupItem) if group else o
    if not isinstance(view, T.DrawViewPart):
        raise TechDrawEditError(f"{o.name} is not a view or a projection group")
    if motion in ROTATIONS:
        d, x = dirs_from_front(view.direction, view.x_direction, ROTATIONS[motion])
    elif motion in ("CW", "CCW"):
        d = view.direction
        x = _vec_rotate(view.x_direction, math.pi / 2.0 if motion == "CW" else -math.pi / 2.0, d)
    elif motion == "Front":
        d, x = (0.0, -1.0, 0.0), (1.0, 0.0, 0.0)
    else:
        raise TechDrawEditError(f"{motion!r} is not a rotation (Up, Down, Left, Right, CW, CCW, Front)")
    vd = T.as_dict(view)
    vd.update(direction=list(d), x_direction=list(x))
    s.objs[s.objs.index(view)] = _rebuilt(view, vd)
    if group is not None:                   # DrawProjGroup::updateSecondaryDirs
        for n in group.views:
            it = s.get(n)
            if it.name == view.name:
                continue
            nd, nx = dirs_from_front(d, x, it.type)
            itd = T.as_dict(it)
            itd.update(direction=list(nd), x_direction=list(nx))
            s.objs[s.objs.index(it)] = _rebuilt(it, itd)
    return f"turned {o.name} {motion}"


def _vec_rotate(v, angle, axis):
    """DrawUtil::vecRotate about an axis through the origin (Base::Matrix4D::rotLine)."""
    from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
    t = gp_Trsf()
    t.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(*axis)), angle)
    r = gp_Vec(*v).Transformed(t)
    return (r.X(), r.Y(), r.Z())


def _section(s: Session, op) -> str:
    """TaskSectionView: createSectionView with the arrow's view direction (setCSFromBase(localUnit * -1)), the
    Rotation that turns it upright (requiredRotation of the compass angle), OK."""
    base = s.get(op.get("base_view"), T.DrawViewPart, "view")
    arrow = op.get("direction", "Right")
    if arrow not in SECTION_ARROWS:
        raise TechDrawEditError(f"{arrow!r} is not a section direction (Up, Down, Left, Right)")
    local, angle = SECTION_ARROWS[arrow]
    doc = s.doc()
    if op.get("origin") is not None:
        origin = _vec(op.get("origin"), "origin", (0.0, 0.0, 0.0))
    else:                                   # setUiPrimary: the base view's original centroid
        from .techdraw_view import find_centroid, projection_cs
        doc2 = T.PageDocument(s.objs, s.shape_of)
        sh = doc2.shape(doc2.source_of(base))
        origin = find_centroid(sh, projection_cs(base.direction, base.x_direction))
    n = s.name("SectionView", op.get("name"))
    label = "Section" + n[len("SectionView"):]
    normal, xdir = local_vector_to_cs(base.direction, base.x_direction, tuple(-c for c in local))
    cx, cy = s.center()
    scale = doc.view_scale(base)
    stype = base.scale_type if doc.group_of(base.name) is None else doc.group_of(base.name).scale_type
    s.add(T.DrawViewSection(n, base_view=base.name, source=doc.source_of(base), section_symbol=op.get("symbol", ""),
                            section_normal=normal, direction=normal, x_direction=xdir, section_origin=origin,
                            section_direction="Aligned", scale=scale, scale_type=stype,
                            rotation=required_rotation(angle), x=cx, y=cy, label=label,
                            caption="SECTION <REF> - <REF>"))
    return f"made {n} of {base.name}"


def _section_edit(s: Session, op) -> str:
    """TaskSectionView in edit (updateSectionView, "Edit Section View"): a new arrow, origin, symbol or scale."""
    sec = s.get(op.get("name"), T.DrawViewSection, "section view")
    base = s.get(sec.base_view, T.DrawViewPart, "view")
    d = T.as_dict(sec)
    if op.get("direction"):
        if op["direction"] not in SECTION_ARROWS:
            raise TechDrawEditError(f"{op['direction']!r} is not a section direction (Up, Down, Left, Right)")
        local, angle = SECTION_ARROWS[op["direction"]]
        normal, xdir = local_vector_to_cs(base.direction, base.x_direction, tuple(-c for c in local))
        d.update(section_normal=list(normal), direction=list(normal), x_direction=list(xdir),
                 rotation=required_rotation(angle))
    if op.get("origin") is not None:
        d["section_origin"] = list(_vec(op["origin"], "origin", (0.0, 0.0, 0.0)))
    if "symbol" in op:
        d["section_symbol"] = op["symbol"]
    for k in ("scale", "scale_type"):
        if k in op:
            d[k] = op[k]
    s.objs[s.objs.index(sec)] = _rebuilt(sec, d)
    return f"edited {sec.name}"


DIM_REF_KINDS = {"Distance": ("oneEdge", "twoEdge", "twoVertex", "vertexEdge"),
                 "DistanceX": ("oneEdge", "twoEdge", "twoVertex", "vertexEdge"),
                 "DistanceY": ("oneEdge", "twoEdge", "twoVertex", "vertexEdge"),
                 "Radius": ("oneEdge",), "Diameter": ("oneEdge",), "Angle": ("twoEdge",), "Angle3Pt": ("threeVertex",)}


def _dimension(s: Session, op) -> str:
    """dimensionMaker: a DrawViewDimension of Type on the selection's References2D, MeasureType Projected, its
    text placed by positionDimText for the linear and angular ones."""
    from . import techdraw_dim as D
    t = op.get("type")
    if t not in DIM_REF_KINDS:
        raise TechDrawEditError(f"{t!r} is not a dimension the app makes ({', '.join(DIM_REF_KINDS)})")
    refs = [tuple(r) for r in op.get("references") or ()]
    if not refs:
        raise TechDrawEditError("Select an object first")
    views = {r[0] for r in refs}
    if len(views) != 1:
        raise TechDrawEditError("Select elements of one view")
    v = s.get(refs[0][0], T.DrawViewPart, "view")
    if D.ref_type(refs) not in DIM_REF_KINDS[t]:
        raise TechDrawEditError(f"Can not make a {t} dimension from selection")
    n = s.name("Dimension", op.get("name"))
    dim = T.DrawViewDimension(n, type=t, references_2d=refs, measure_type="Projected")
    if t in ("Distance", "DistanceX", "DistanceY", "Angle", "Angle3Pt"):
        doc = T.PageDocument(s.objs, s.shape_of).recompute()
        geo = doc.geo.get(v.name)
        if geo is None:
            raise TechDrawEditError(f"{v.name} has no geometry: {doc.errors.get(v.name, 'nothing to draw')}")
        if t.startswith("Angle"):
            D.measure(dim, geo)                 # a bad selection fails here, as dimMaker's recompute would
            mid = (0.0, 0.0)                    # positionDimText reads getLinearPoints, which an angle leaves at 0, 0
        else:
            try:
                p0, p1 = D.linear_points(dim, geo)
                mid = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
            except D.DimensionError:            # its recompute fails: getLinearPoints is still 0, 0 (it is made all the same)
                mid = (0.0, 0.0)
        dim = T.DrawViewDimension(n, type=t, references_2d=refs, measure_type="Projected", x=mid[0],
                                  y=-mid[1] + 0.5 * D.DIM_FONT_SIZE)
    s.add(dim)
    return f"made {n} ({t}) on {', '.join(r[1] for r in refs)} of {v.name}"


def _dependents(s: Session, name) -> list:
    out = []
    for o in s.objs:
        if isinstance(o, T.DrawViewDimension) and o.view() == name:
            out.append(o)
        elif isinstance(o, T.DrawViewBalloon) and o.source_view == name:
            out.append(o)
    return out


def _delete(s: Session, name) -> str:
    o = s.get(name)
    if isinstance(o, T.DrawPage):
        raise TechDrawEditError("delete the page with `cad techdraw delete-page`")
    if isinstance(o, T.DrawSVGTemplate):
        raise TechDrawEditError("a page's template is replaced, not deleted (set template=...)")
    secs = [x.name for x in s.objs if isinstance(x, T.DrawViewSection) and x.base_view == name]
    if secs:
        raise TechDrawEditError(f"{name} is the base of {', '.join(secs)}: delete them first")
    gone = [o] + _dependents(s, name)
    if isinstance(o, T.DrawProjGroup):
        for n in o.views:
            it = next((x for x in s.objs if x.name == n), None)
            if it is not None:
                gone += [it] + _dependents(s, n)
    else:
        g = s.doc().group_of(name)
        if g is not None:
            if o.type == "Front":
                raise TechDrawEditError("the Front projection is the group's anchor and stays")
            gd = T.as_dict(g)
            gd["views"] = [v for v in g.views if v != name]
            s.objs[s.objs.index(g)] = _rebuilt(g, gd)
    for x in gone:
        if x in s.objs:
            s.objs.remove(x)
    return "deleted " + ", ".join(x.name for x in gone)


def _rename(s: Session, name, to) -> str:
    o = s.get(name)
    if not (isinstance(to, str) and NAME.match(to)) or to in s.taken:
        raise TechDrawEditError(f"{to!r} is not a free name")
    s.taken.add(to)
    new = []
    for x in s.objs:
        d = T.as_dict(x)
        if x is o:
            d["name"] = to
        for k in ("template", "anchor", "base_view", "source_view"):
            if d.get(k) == name and k in x.DEFAULTS and (k != "template" or isinstance(x, T.DrawPage)):
                d[k] = to
        if "views" in d and isinstance(x, T.DrawProjGroup):
            d["views"] = [to if v == name else v for v in d["views"]]
        if "references_2d" in d:
            d["references_2d"] = [[to if r[0] == name else r[0], r[1]] for r in d["references_2d"]]
        new.append(_rebuilt(x, d))
    s.objs = new
    return f"renamed {name} to {to}"


def apply(pdir, page: str, ops, write: bool = True, recompute: bool = True, svg: bool = False) -> dict:
    """The ops on techdraw/<page>.py, all or nothing; returns read() (and the recompute) of the result."""
    from . import state
    pdir = Path(pdir)
    path = page_file(pdir, page)
    src = path.read_text() if path.exists() else None
    ops = list(ops)
    if src is None:
        if not ops or ops[0].get("op") != "new_page":
            raise TechDrawEditError(f"there is no page {page!r}: make it first (cad techdraw new)")
        src = TEMPLATE.format(page=page, slug=pdir.name)
    objs = objects_of(src)
    if objs is None:
        raise TechDrawEditError(f"techdraw/{page}.py has no PAGE list")
    parts_dir = pdir / "parts"
    part_names = sorted(p.stem for p in parts_dir.glob("*.py")) if parts_dir.is_dir() else []
    s = Session(pdir, page, objs, part_names)
    done = run_ops(s, ops)
    new = write_src(src, s.objs)
    if write and new != (path.read_text() if path.exists() else None):
        path.parent.mkdir(exist_ok=True)
        state.write_atomic(path, new)
    out = read_src_objs(s.objs, page, pdir.name)
    if recompute or svg:
        doc = T.PageDocument(s.objs, shape_loader(pdir.name), pdir.name).recompute()
        out["result"] = doc.result()
        if svg:
            from .techdraw_export import page_svg
            out["svg"] = page_svg(doc, interactive=True)
    out["done"] = done
    return out

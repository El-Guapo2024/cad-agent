"""cad techdraw: a project's TechDraw pages (FreeCAD's TechDraw workbench), edited from the CLI and the workbench alike.

A page is techdraw/<Page>.py, its PAGE list (docs/EDITING_PLAN.md, "TechDraw pages in a project"). These commands
edit it through cad_agent/techdraw_edit.py, each change one step of the undo journal named as FreeCAD names the
transaction:

    cad techdraw ls         SLUG                                 the project's pages
    cad techdraw show       SLUG PAGE                            the tree, each view's lines, each dimension's text
    cad techdraw new        SLUG [--page P] [--template T]       TechDraw_PageDefault / _PageTemplate
    cad techdraw view       SLUG PAGE PART... [--direction X,Y,Z] [--x-direction X,Y,Z]
                                                                 TechDraw_View
    cad techdraw projgroup  SLUG PAGE PART... [--direction ...] [--projections Top,Right,...]
                                                                 TechDraw_ProjectionGroup and TaskProjGroup
    cad techdraw projection SLUG PAGE GROUP TYPE [--off]          a projection of a group checked or unchecked
    cad techdraw section    SLUG PAGE VIEW [--direction Right] [--origin X,Y,Z] [--symbol A]
                                                                 TechDraw_SectionView and TaskSectionView
    cad techdraw dimension  SLUG PAGE TYPE VIEW:Edge3 [VIEW:Vertex2 ...]
                                                                 TechDraw_LengthDimension ... _AngleDimension
    cad techdraw balloon    SLUG PAGE VIEW --origin X,Y [--at X,Y]   TechDraw_Balloon
    cad techdraw annotation SLUG PAGE [TEXT...] [--at X,Y]        TechDraw_Annotation
    cad techdraw set        SLUG PAGE NAME KEY=VALUE ...          the property view (FreeCAD's names in snake_case)
    cad techdraw move       SLUG PAGE NAME --at X,Y               a view dragged on the page
    cad techdraw delete     SLUG PAGE NAME ...                    Std_Delete
    cad techdraw rename     SLUG PAGE NAME TO
    cad techdraw apply      SLUG PAGE --ops JSON                  several ops as one step (what the workbench sends)
    cad techdraw export     SLUG PAGE [--format svg,dxf,pdf] [--out DIR]
                                                                 TechDraw_ExportPageSVG / DXF / PDF
    cad techdraw delete-page SLUG PAGE                            Std_Delete of the page and everything on it
    cad techdraw cosmetic-vertex SLUG PAGE VIEW X,Y               TechDraw_CosmeticVertex
    cad techdraw midpoints|quadrants SLUG PAGE VIEW EDGE ...      TechDraw_Midpoints, TechDraw_Quadrants
    cad techdraw cosmetic-line SLUG PAGE VIEW --p0 X,Y --p1 X,Y   TechDraw_2PointCosmeticLine (--vertices V V, --edge E)
    cad techdraw cosmetic-circle SLUG PAGE VIEW --center X,Y --radius R [--arc A,B]   TechDraw_CosmeticCircle
    cad techdraw centerline SLUG PAGE VIEW SUB ... [--mode M]     TechDraw_FaceCenterLine, _2LineCenterLine, _2PointCenterLine
    cad techdraw erase      SLUG PAGE VIEW SUB ...                TechDraw_CosmeticEraser
    cad techdraw format     SLUG PAGE VIEW EDGE ... [--line-number N --weight W --visible false]   TechDraw_DecorateLine
    cad techdraw restore-lines SLUG PAGE VIEW                     TaskRestoreLines

TYPE is Distance, DistanceX, DistanceY, Radius, Diameter, Angle or Angle3Pt (Length, Horizontal, Vertical, Radius,
Diameter, Angle and 3-point Angle Dimension). A view's X and Y are the page's millimetres from its lower left corner;
a balloon's origin and a dimension's X, Y are relative to its view's centre, y up, as FreeCAD stores them.
"""
from __future__ import annotations

import json
import shlex
from pathlib import Path

from . import state as st
from .cmdbase import OK, Result, UsageError, actor, pairs, project

STEP_NAMES = {"new_page": "Drawing create page", "view": "Create view", "projgroup": "Create projection group",
              "projection": "Edit projection group", "section": "Create Section View",
              "dimension": "Create dimension", "balloon": "Create Balloon", "annotation": "Create Annotation",
              "delete": "Delete", "move": "Drag view"}


def step_name(ops: list) -> str:
    from .techdraw_annot import STEP_NAMES as ANNOT
    from .techdraw_more import STEP_NAMES as MORE
    op = ops[-1] if ops else {}
    kind = op.get("op")
    if kind in ANNOT:
        return ANNOT[kind]
    if kind in MORE:
        return MORE[kind]
    from . import techdraw_ext
    if kind in techdraw_ext.OPS:
        return techdraw_ext.step_name(op) or "Edit page"
    if kind in STEP_NAMES:
        return STEP_NAMES[kind]
    if kind in ("rename", "label"):
        return f"Rename {op.get('name')}.Label"
    if kind == "set":
        props = list(op.get("props") or {})
        from .techdraw import TDObject
        first = TDObject.prop_name(props[0]) if props else "property"
        return f"Edit {op.get('name')}.{first}" + ("..." if len(props) > 1 else "")
    return "Edit page"


def _floats(text: str, n: int, what: str):
    try:
        v = [float(x) for x in text.split(",")]
    except ValueError:
        v = []
    if len(v) != n:
        raise UsageError(f"{what} takes {n} numbers separated by commas, got {text!r}")
    return v


def _lines(doc: dict) -> list[str]:
    out = []
    res = doc.get("result") or {}
    views = res.get("views", {})
    dims = res.get("dimensions", {})
    for row in doc.get("tree", []):
        ind = "  " * (row["depth"] + 1)
        label = row["label"] if row["label"] == row["name"] else f"{row['label']} ({row['name']})"
        extra = ""
        v = views.get(row["name"])
        if v and "edges" in v:
            nv = sum(1 for e in v["edges"] if e["visible"])
            extra = (f"  at ({v['x']:.6g}, {v['y']:.6g}) scale {v['scale']:.6g}: {nv} visible and "
                     f"{len(v['edges']) - nv} hidden edges, {len(v['vertices'])} vertices")
            if v.get("faces"):
                extra += f", {len(v['faces'])} section faces"
        d = dims.get(row["name"])
        if d:
            extra = f"  {d['type']} {d['text']!r} ({d['value']:.6g})"
            if d.get("tolerances"):
                extra += f" {d['tolerances'][1]} / {d['tolerances'][0]}"
        out.append(f"{ind}{label}  [{row['type'].split('::')[-1]}]{extra}")
    for name, err in res.get("errors", {}).items():
        out.append(f"  {name}: {err}")
    return out


def apply_ops(a, page: str, ops: list, cmd: str, step: str | None = None) -> Result:
    svg = bool(getattr(a, "svg", False))
    from . import techdraw_edit as E
    if not isinstance(ops, list) or not ops or not all(isinstance(o, dict) and o.get("op") for o in ops):
        raise UsageError('ops is a list of {"op": "view"|"projgroup"|"section"|"dimension"|"set"|..., ...}')
    pdir = project(a.slug)
    try:
        path = E.page_file(pdir, page)
    except E.TechDrawEditError as e:
        raise UsageError(str(e)) from None
    before = path.read_text() if path.exists() else None
    try:
        doc = E.apply(pdir, page, ops, svg=svg)
    except (ValueError, KeyError) as e:
        raise UsageError(str(e)) from None
    except Exception as e:
        if before is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(before)
        raise UsageError(f"the page did not recompute: {st.why(e)}") from None
    after = path.read_text() if path.exists() else None
    name = step or step_name(ops)
    from . import undo as un
    rel = f"{E.DIR}/{page}.py"
    if getattr(a, "amend", False):          # a task panel's edit of what its command just made: the same undo step
        un.amend(pdir, [{"path": rel, "before": before, "after": after}], by=actor(a))
    else:
        un.record(pdir, name, cmd, [{"path": rel, "before": before, "after": after}], by=actor(a))
    lines = [f"{a.slug}/{page}: {name}"] + [f"  {d}" for d in doc.get("done", [])] + _lines(doc)
    data = {"project": a.slug, "page": page, "step": name, "doc": doc, "file": str(path)}
    return Result(OK, data, "\n".join(lines), f"{a.slug}/{page}: {name}", [str(path)])


def _cmd(a, *words: str) -> str:
    return shlex.join(["cad", "techdraw", a.techdraw_cmd, a.slug, *words])


# ── the commands ─────────────────────────────────────────────────────────────────────────────────────────────

def cmd_ls(a) -> Result:
    from . import techdraw_edit as E
    pdir = project(a.slug)
    pages = E.pages(pdir)
    data = {"project": a.slug, "pages": []}
    for p in pages:
        try:
            objs = E.objects_of(E.page_file(pdir, p).read_text()) or []
        except E.TechDrawEditError as e:
            data["pages"].append({"page": p, "error": str(e)})
            continue
        tpl = next((o.template for o in objs if o.kind == "DrawSVGTemplate"), None)
        data["pages"].append({"page": p, "template": tpl, "objects": len(objs)})
    text = "\n".join([f"{a.slug}: {len(pages)} page(s)"] +
                     [f"  {d['page']}  {d.get('template') or d.get('error')}" for d in data["pages"]])
    return Result(OK, data, text, f"{a.slug}: {len(pages)} page(s)")


def cmd_show(a) -> Result:
    from . import techdraw_edit as E
    pdir = project(a.slug)
    try:
        doc = E.recomputed(pdir, a.page, svg=a.svg) if not a.no_recompute else E.read(pdir, a.page)
    except E.TechDrawEditError as e:
        raise UsageError(str(e)) from None
    except Exception as e:
        raise UsageError(f"the page did not recompute: {st.why(e)}") from None
    return Result(OK, doc, "\n".join([f"{a.slug}/{a.page}"] + _lines(doc)), f"{a.slug}/{a.page}")


def cmd_new(a) -> Result:
    from . import techdraw_edit as E
    pdir = project(a.slug)
    page = a.page or E.unique_name("Page", set(E.pages(pdir)) | E.project_names(pdir))
    op = {"op": "new_page"}
    if a.template:
        op["template"] = a.template
    return apply_ops(a, page, [op], _cmd(a, *(["--page", page]) + (["--template", a.template] if a.template else [])),
                     "Drawing create page")


def _dirs(a, op):
    if a.direction:
        op["direction"] = _floats(a.direction, 3, "--direction")
    if a.x_direction:
        op["x_direction"] = _floats(a.x_direction, 3, "--x-direction")
    return op


def cmd_view(a) -> Result:
    op = _dirs(a, {"op": "view", "source": a.parts})
    if a.name:
        op["name"] = a.name
    words = [a.page, *a.parts] + (["--direction", a.direction] if a.direction else []) + \
        (["--x-direction", a.x_direction] if a.x_direction else []) + (["--name", a.name] if a.name else [])
    return apply_ops(a, a.page, [op], _cmd(a, *words))


def cmd_projgroup(a) -> Result:
    op = _dirs(a, {"op": "projgroup", "source": a.parts})
    if a.projections:
        op["projections"] = [p.strip() for p in a.projections.split(",") if p.strip()]
    words = [a.page, *a.parts] + (["--direction", a.direction] if a.direction else []) + \
        (["--x-direction", a.x_direction] if a.x_direction else []) + \
        (["--projections", a.projections] if a.projections else [])
    return apply_ops(a, a.page, [op], _cmd(a, *words))


def cmd_projection(a) -> Result:
    return apply_ops(a, a.page, [{"op": "projection", "group": a.group, "type": a.type, "on": not a.off}],
                     _cmd(a, a.page, a.group, a.type, *(["--off"] if a.off else [])))


def cmd_section(a) -> Result:
    op = {"op": "section", "base_view": a.view, "direction": a.direction}
    if a.origin:
        op["origin"] = _floats(a.origin, 3, "--origin")
    if a.symbol is not None:
        op["symbol"] = a.symbol
    words = [a.page, a.view, "--direction", a.direction] + (["--origin", a.origin] if a.origin else []) + \
        (["--symbol", a.symbol] if a.symbol is not None else [])
    return apply_ops(a, a.page, [op], _cmd(a, *words))


def _ref(text: str):
    view, _, sub = text.partition(":")
    if not view or not sub:
        raise UsageError(f"{text!r} is not VIEW:Edge3 or VIEW:Vertex2")
    return [view, sub]


def cmd_dimension(a) -> Result:
    op = {"op": "dimension", "type": a.type, "references": [_ref(r) for r in a.refs]}
    return apply_ops(a, a.page, [op], _cmd(a, a.page, a.type, *a.refs))


def cmd_balloon(a) -> Result:
    op = {"op": "balloon", "view": a.view, "origin": _floats(a.origin, 2, "--origin")}
    if a.at:
        op["at"] = _floats(a.at, 2, "--at")
    return apply_ops(a, a.page, [op], _cmd(a, a.page, a.view, "--origin", a.origin, *(["--at", a.at] if a.at else [])))


def cmd_annotation(a) -> Result:
    op = {"op": "annotation"}
    if a.text:
        op["text"] = list(a.text)
    if a.at:
        op["at"] = _floats(a.at, 2, "--at")
    return apply_ops(a, a.page, [op], _cmd(a, a.page, *a.text, *(["--at", a.at] if a.at else [])))


def cmd_set(a) -> Result:
    props = pairs(a.props, "cad techdraw")
    if not props:
        raise UsageError("say what to change: cad techdraw set SLUG PAGE NAME key=value ...")
    return apply_ops(a, a.page, [{"op": "set", "name": a.name, "props": props}], _cmd(a, a.page, a.name, *a.props))


def cmd_move(a) -> Result:
    x, y = _floats(a.at, 2, "--at")
    return apply_ops(a, a.page, [{"op": "move", "name": a.name, "x": x, "y": y}], _cmd(a, a.page, a.name, "--at", a.at))


def cmd_delete(a) -> Result:
    return apply_ops(a, a.page, [{"op": "delete", "name": n} for n in a.names], _cmd(a, a.page, *a.names))


def cmd_rename(a) -> Result:
    return apply_ops(a, a.page, [{"op": "rename", "name": a.name, "to": a.to}], _cmd(a, a.page, a.name, a.to))


# ── cosmetic geometry and centre lines (techdraw_annot.py) ──────────────────────────────────────────────────

def cmd_cosmetic_vertex(a) -> Result:
    return apply_ops(a, a.page, [{"op": "cosmetic_vertex", "view": a.view, "point": _floats(a.point, 2, "POINT")}],
                     _cmd(a, a.page, a.view, a.point))


def cmd_points(a) -> Result:
    op = "midpoints" if a.techdraw_cmd == "midpoints" else "quadrants"
    return apply_ops(a, a.page, [{"op": op, "view": a.view, "edges": a.edges}], _cmd(a, a.page, a.view, *a.edges))


def cmd_cosmetic_line(a) -> Result:
    op = {"op": "cosmetic_line", "view": a.view}
    if a.vertices:
        op["vertices"] = a.vertices
    elif a.p0 and a.p1:
        op["p0"], op["p1"] = _floats(a.p0, 2, "--p0"), _floats(a.p1, 2, "--p1")
    else:
        raise UsageError("say the line: --p0 X,Y --p1 X,Y, or --vertices Vertex1 Vertex2")
    if a.edge:
        op["op"], op["edge"] = "cosmetic_line_edit", a.edge
    return apply_ops(a, a.page, [op], _cmd(a, a.page, a.view, *(["--edge", a.edge] if a.edge else []),
                                           *(["--vertices", *a.vertices] if a.vertices else
                                             ["--p0", a.p0, "--p1", a.p1])))


def cmd_cosmetic_circle(a) -> Result:
    op = {"op": "cosmetic_circle_edit" if a.edge else "cosmetic_circle", "view": a.view}
    if a.edge:
        op["edge"] = a.edge
    elif not (a.vertices or (a.center and a.radius is not None)):
        raise UsageError("say the circle: --center X,Y --radius R, or --vertices CENTRE RIM")
    if a.vertices:
        op["vertices"] = a.vertices
    if a.center:
        op["center"] = _floats(a.center, 2, "--center")
    if a.radius is not None:
        op["radius"] = a.radius
    if a.arc:
        op["arc"] = True
        op["start_angle"], op["end_angle"] = _floats(a.arc, 2, "--arc")
    words = [a.page, a.view] + (["--edge", a.edge] if a.edge else []) + (["--vertices", *a.vertices] if a.vertices else []) + \
        (["--center", a.center] if a.center else []) + (["--radius", repr(a.radius)] if a.radius is not None else []) + \
        (["--arc", a.arc] if a.arc else [])
    return apply_ops(a, a.page, [op], _cmd(a, *words))


def cmd_centerline(a) -> Result:
    op = {"op": "centerline", "view": a.view, "subs": a.subs, "mode": a.mode}
    for key in ("h_shift", "v_shift", "rotate", "extend"):
        v = getattr(a, key)
        if v is not None:
            op[key] = v
    words = [a.page, a.view, *a.subs, "--mode", a.mode] + sum(([f"--{k.replace('_', '-')}", repr(getattr(a, k))]
                                                              for k in ("h_shift", "v_shift", "rotate", "extend")
                                                              if getattr(a, k) is not None), [])
    return apply_ops(a, a.page, [op], _cmd(a, *words))


def cmd_erase(a) -> Result:
    return apply_ops(a, a.page, [{"op": "erase", "view": a.view, "subs": a.subs}], _cmd(a, a.page, a.view, *a.subs))


def cmd_format(a) -> Result:
    op = {"op": "format", "view": a.view, "subs": a.subs}
    for key in ("style", "weight", "line_number"):
        if getattr(a, key) is not None:
            op[key] = getattr(a, key)
    if a.visible is not None:
        op["visible"] = a.visible == "true"
    if a.color:
        op["color"] = _floats(a.color, 3, "--color") + [1.0]
    words = [a.page, a.view, *a.subs] + sum(([f"--{k.replace('_', '-')}", str(getattr(a, k))] for k in ("style", "weight", "line_number")
                                              if getattr(a, k) is not None), []) + \
        (["--visible", a.visible] if a.visible else []) + (["--color", a.color] if a.color else [])
    return apply_ops(a, a.page, [op], _cmd(a, *words))


def cmd_restore_lines(a) -> Result:
    kinds = [k.strip() for k in a.kinds.split(",") if k.strip()]
    return apply_ops(a, a.page, [{"op": "restore_lines", "view": a.view, "kinds": kinds}], _cmd(a, a.page, a.view, "--kinds", a.kinds))


def cmd_apply(a) -> Result:
    text = a.ops
    if text.startswith("@"):
        text = Path(text[1:]).read_text()
    try:
        ops = json.loads(text)
    except ValueError as e:
        raise UsageError(f"--ops is JSON: {e}") from None
    if a.dry_run:
        from . import techdraw_edit as E
        try:
            doc = E.apply(project(a.slug), a.page, ops, write=False, svg=a.svg)
        except (ValueError, KeyError) as e:
            raise UsageError(str(e)) from None
        return Result(OK, {"project": a.slug, "page": a.page, "doc": doc, "dry_run": True}, "\n".join(_lines(doc)),
                      f"{a.slug}/{a.page}: preview")
    words = [a.page, "--ops", json.dumps(ops, separators=(",", ":"))] + (["--name", a.name] if a.name else []) + \
        (["--amend"] if getattr(a, "amend", False) else [])
    return apply_ops(a, a.page, ops, _cmd(a, *words), a.name)


def cmd_delete_page(a) -> Result:
    from . import techdraw_edit as E
    pdir = project(a.slug)
    path = E.page_file(pdir, a.page)
    if not path.exists():
        raise UsageError(f"there is no page {a.page!r}")
    before = path.read_text()
    path.unlink()
    from . import undo as un
    un.record(pdir, "Delete", _cmd(a, a.page), [{"path": f"{E.DIR}/{a.page}.py", "before": before, "after": None}],
              by=actor(a))
    return Result(OK, {"project": a.slug, "page": a.page, "deleted": True}, f"{a.slug}: deleted {a.page}",
                  f"{a.slug}: deleted {a.page}")


def cmd_export(a) -> Result:
    from . import techdraw_edit as E
    from . import techdraw_export as X
    pdir = project(a.slug)
    fmts = [f.strip().lower() for f in a.format.split(",") if f.strip()]
    bad = [f for f in fmts if f not in ("svg", "dxf", "pdf")]
    if bad or not fmts:
        raise UsageError(f"--format takes svg, dxf and pdf, got {a.format!r}")
    try:
        doc = E.page_document(pdir, a.page)
    except E.TechDrawEditError as e:
        raise UsageError(str(e)) from None
    out = Path(a.out).expanduser() if a.out else pdir / "out" / "techdraw"
    out.mkdir(parents=True, exist_ok=True)
    wrote = []
    for f in fmts:
        data = X.export(doc, f)
        p = out / f"{a.page}.{f}"
        p.write_bytes(data if isinstance(data, bytes) else data.encode())
        wrote.append(str(p))
    return Result(OK, {"project": a.slug, "page": a.page, "wrote": wrote}, "\n".join(f"wrote {p}" for p in wrote),
                  f"{a.slug}/{a.page}: exported", wrote)


def add_parsers(add, sub) -> None:
    """cli.py's build_parser hands its `add` and the subparsers here."""
    tp = add("techdraw", None, "a project's TechDraw pages (FreeCAD's TechDraw workbench): new, view, projgroup, "
             "section, dimension, balloon, annotation, set, move, delete, export; each change one undo step")
    from .cmdbase import Parser
    tsub = tp.add_subparsers(dest="techdraw_cmd", metavar="<action>", parser_class=Parser)

    def one(name, func, help, page=True):
        sp = add(name, func, help, parent=tsub)
        sp.set_defaults(cmd_name=f"techdraw {name}", techdraw_cmd=name)
        sp.add_argument("slug")
        if page:
            sp.add_argument("page")
        return sp

    def dirs(sp):
        sp.add_argument("--direction", metavar="X,Y,Z", help="the view direction (Direction; default 0,-1,0: Front)")
        sp.add_argument("--x-direction", metavar="X,Y,Z", help="the page's horizontal (XDirection; default 1,0,0)")

    one("ls", cmd_ls, "the project's pages", page=False)
    sp = one("show", cmd_show, "the page's tree, each view's edges and each dimension's text (a recompute)")
    sp.add_argument("--no-recompute", action="store_true", help="the objects only")
    sp.add_argument("--svg", action="store_true", help="the page drawn, as data.svg (what the workbench shows)")
    sp = one("new", cmd_new, "TechDraw_PageDefault: a page with the default template (or --template)", page=False)
    sp.add_argument("--page", help="the page's Name (default Page, Page001, ...)")
    sp.add_argument("--template", help="Default_Template_A4_Landscape.svg, ISO/A4_Landscape_TD.svg, "
                    "ISO/A3_Landscape_TD.svg, ISO/A4_Landscape_ISO5457_minimal.svg, ...")
    sp = one("view", cmd_view, "TechDraw_View: a view of parts, at the page's centre")
    sp.add_argument("parts", nargs="+", metavar="PART")
    dirs(sp)
    sp.add_argument("--name")
    sp = one("projgroup", cmd_projgroup, "TechDraw_ProjectionGroup: a group with its Front (and --projections)")
    sp.add_argument("parts", nargs="+", metavar="PART")
    dirs(sp)
    sp.add_argument("--projections", metavar="TYPES", help="Top,Right,Left,Bottom,Rear,FrontTopLeft,...")
    sp = one("projection", cmd_projection, "TaskProjGroup: check (or --off uncheck) a projection of a group")
    sp.add_argument("group")
    sp.add_argument("type")
    sp.add_argument("--off", action="store_true")
    sp = one("section", cmd_section, "TechDraw_SectionView: a section of a view, looking along an arrow")
    sp.add_argument("view")
    sp.add_argument("--direction", default="Right", choices=["Right", "Left", "Up", "Down"])
    sp.add_argument("--origin", metavar="X,Y,Z", help="SectionOrigin (default: the view's centroid)")
    sp.add_argument("--symbol", help="SectionSymbol")
    sp = one("dimension", cmd_dimension, "TechDraw_*Dimension: TYPE and the selected VIEW:Edge3 / VIEW:Vertex2")
    sp.add_argument("type", help="Distance, DistanceX, DistanceY, Radius, Diameter, Angle, Angle3Pt")
    sp.add_argument("refs", nargs="+", metavar="VIEW:ELEMENT")
    sp = one("balloon", cmd_balloon, "TechDraw_Balloon: a balloon on a view, pointing at --origin")
    sp.add_argument("view")
    sp.add_argument("--origin", required=True, metavar="X,Y", help="where it points, relative to the view's centre")
    sp.add_argument("--at", metavar="X,Y", help="where the bubble goes (default origin + (10, 10))")
    sp = one("cosmetic-vertex", cmd_cosmetic_vertex, "TechDraw_CosmeticVertex: a cosmetic vertex at X,Y of a view")
    sp.add_argument("view")
    sp.add_argument("point", metavar="X,Y", help="unscaled, unrotated, y up, about the view's centre")
    for name, what in (("midpoints", "TechDraw_Midpoints: cosmetic vertices at the midpoints of edges"),
                       ("quadrants", "TechDraw_Quadrants: cosmetic vertices at the quadrant points of edges")):
        sp = one(name, cmd_points, what)
        sp.add_argument("view")
        sp.add_argument("edges", nargs="+", metavar="EDGE")
    sp = one("cosmetic-line", cmd_cosmetic_line, "TechDraw_2PointCosmeticLine: a cosmetic line (--edge: change one)")
    sp.add_argument("view")
    sp.add_argument("--p0", metavar="X,Y")
    sp.add_argument("--p1", metavar="X,Y")
    sp.add_argument("--vertices", nargs=2, metavar="VERTEX")
    sp.add_argument("--edge", metavar="EDGE", help="the cosmetic line to change (TaskCosmeticLine, edit)")
    sp = one("cosmetic-circle", cmd_cosmetic_circle, "TechDraw_CosmeticCircle: a cosmetic circle or arc (--edge: change one)")
    sp.add_argument("view")
    sp.add_argument("--center", metavar="X,Y")
    sp.add_argument("--radius", type=float)
    sp.add_argument("--vertices", nargs=2, metavar="VERTEX", help="the centre and a point on the circle")
    sp.add_argument("--arc", metavar="START,END", help="an arc from START to END degrees, anticlockwise")
    sp.add_argument("--edge", metavar="EDGE")
    sp = one("centerline", cmd_centerline, "TechDraw_FaceCenterLine, _2LineCenterLine, _2PointCenterLine: a centerline on "
             "Face0, or between Edge1 Edge2, or between Vertex1 Vertex2")
    sp.add_argument("view")
    sp.add_argument("subs", nargs="+", metavar="SUB")
    sp.add_argument("--mode", default="Vertical", choices=["Vertical", "Horizontal", "Aligned"])
    sp.add_argument("--h-shift", dest="h_shift", type=float)
    sp.add_argument("--v-shift", dest="v_shift", type=float)
    sp.add_argument("--rotate", type=float, help="degrees")
    sp.add_argument("--extend", type=float)
    sp = one("erase", cmd_erase, "TechDraw_CosmeticEraser: remove cosmetic edges, centerlines and vertices")
    sp.add_argument("view")
    sp.add_argument("subs", nargs="+", metavar="SUB", help="Edge7 / Vertex9 of the view")
    sp = one("format", cmd_format, "TechDraw_DecorateLine: the style, weight, colour and visibility of lines (Edge7 ...)")
    sp.add_argument("view")
    sp.add_argument("subs", nargs="+", metavar="EDGE")
    sp.add_argument("--line-number", dest="line_number", type=int, help="1-17: Visible, Hidden, Section, Center, Symmetry ... Chain")
    sp.add_argument("--style", type=int, help="the Qt pen style (2: dashed)")
    sp.add_argument("--weight", type=float, help="mm")
    sp.add_argument("--visible", choices=["true", "false"])
    sp.add_argument("--color", metavar="R,G,B", help="0 to 1 each")
    sp = one("restore-lines", cmd_restore_lines, "TaskRestoreLines: the lines made invisible visible again")
    sp.add_argument("view")
    sp.add_argument("--kinds", default="all", help="all, or geometry,cosmetic,center")
    sp = one("annotation", cmd_annotation, "TechDraw_Annotation: a text on the page")
    sp.add_argument("text", nargs="*", metavar="LINE")
    sp.add_argument("--at", metavar="X,Y")
    sp = one("set", cmd_set, "change an object's properties (scale=0.5 hard_hidden=true format_spec='%%.1f')")
    sp.add_argument("name")
    sp.add_argument("props", nargs="+", metavar="KEY=VALUE")
    sp = one("move", cmd_move, "a view's X and Y on the page (a drag)")
    sp.add_argument("name")
    sp.add_argument("--at", required=True, metavar="X,Y")
    sp = one("delete", cmd_delete, "delete objects (a view's dimensions and balloons go with it)")
    sp.add_argument("names", nargs="+", metavar="NAME")
    sp = one("rename", cmd_rename, "rename an object, and the references to it")
    sp.add_argument("name")
    sp.add_argument("to")
    sp = one("apply", cmd_apply, "several ops as one undo step: --ops '[{\"op\": \"view\", ...}]' (or --ops @file)")
    sp.add_argument("--ops", required=True, metavar="JSON")
    sp.add_argument("--name", help="the undo step's name (default: FreeCAD's transaction's)")
    sp.add_argument("--dry-run", action="store_true", help="the result, nothing written")
    sp.add_argument("--amend", action="store_true", help="fold the change into the last undo step (a panel's edit of "
                    "what its command just made)")
    sp.add_argument("--svg", action="store_true", help="the page drawn after the ops, as data.doc.svg")
    sp = one("export", cmd_export, "TechDraw_ExportPageSVG / _ExportPageDXF / _ExportPagePDF: out/techdraw/<Page>.*")
    sp.add_argument("--format", default="svg,dxf,pdf")
    sp.add_argument("--out", metavar="DIR")
    one("delete-page", cmd_delete_page, "delete a page and everything on it")
    from . import techdrawcmd_more
    techdrawcmd_more.add(one, apply_ops, _cmd)
    from . import techdrawcmd_ext
    techdrawcmd_ext.add(one, apply_ops, _cmd)

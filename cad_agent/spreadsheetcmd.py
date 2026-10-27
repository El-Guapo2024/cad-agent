"""cad sheet: a project's spreadsheets (FreeCAD's Spreadsheet workbench), edited from the CLI and the workbench alike.

A sheet is spreadsheet/<Name>.py, its SHEET list (docs/EDITING_PLAN.md, "Spreadsheets in a project"). These commands
edit it through cad_agent/spreadsheet_edit.py, each change one step of the undo journal named as FreeCAD names the
transaction:

    cad sheet ls      SLUG                                  the project's sheets
    cad sheet show    SLUG SHEET                            every used cell: content, value, error, what the view shows
    cad sheet new     SLUG [--sheet NAME] [--label L]       Spreadsheet_CreateSheet
    cad sheet set     SLUG SHEET CELL CONTENT               a cell edited ("=B1*2", "'text", "12.5", "3 mm"); CELL may be a range
    cad sheet alias   SLUG SHEET CELL [ALIAS]               Set Alias (no ALIAS: removed)
    cad sheet style   SLUG SHEET RANGE bold|italic|underline [--mode add|remove|replace|invert]
    cad sheet align   SLUG SHEET RANGE left|center|right|top|vcenter|bottom   (Spreadsheet_Align*: 'keep')
    cad sheet color   SLUG SHEET RANGE --text R,G,B | --background R,G,B | --clear-text | --clear-background
    cad sheet unit    SLUG SHEET RANGE [UNIT]               the display unit
    cad sheet merge   SLUG SHEET RANGE / split SLUG SHEET CELL
    cad sheet insert-rows | remove-rows SLUG SHEET ROW [COUNT]; insert-columns | remove-columns SLUG SHEET COL [COUNT]
    cad sheet width   SLUG SHEET COL PIXELS / height SLUG SHEET ROW PIXELS
    cad sheet clear   SLUG SHEET RANGE
    cad sheet import  SLUG SHEET FILE.csv / export SLUG SHEET [FILE.csv]   (tab, ", \\ as FreeCAD's defaults)
    cad sheet bind    SLUG PART PARAM [EXPRESSION] --sheet S   a part's PARAMS entry bound to a cell (EXPRESSIONS)
    cad sheet apply   SLUG SHEET --ops JSON                 several ops as one step (what the workbench sends)
    cad sheet delete  SLUG SHEET                            Std_Delete of the sheet
"""
from __future__ import annotations

import json
import shlex
from pathlib import Path

from . import state as st
from .cmdbase import OK, Result, UsageError, actor, project


def _lines(doc: dict) -> list:
    out = []
    sh = doc.get("sheet") or {}
    for addr, c in (sh.get("cells") or {}).items():
        v = c.get("view") or {}
        shown = v.get("display")
        extra = f"  [{c['alias']}]" if c.get("alias") else ""
        err = f"  ! {c['exception'].splitlines()[0]}" if c.get("exception") else ""
        if c.get("content") is None and shown is None:
            continue
        out.append(f"  {addr:<5} {c.get('content') or '':<28} -> {shown if shown is not None else ''}{extra}{err}")
    for k, msg in (doc.get("recompute") or {}).items():
        out.append(f"  {k}: {msg}")
    return out


def apply_ops(a, sheet: str, ops: list, cmd: str, step: str | None = None, extra_paths=()) -> Result:
    from . import spreadsheet_edit as E
    if not isinstance(ops, list) or not ops or not all(isinstance(o, dict) and o.get("op") for o in ops):
        raise UsageError('ops is a list of {"op": "set"|"setAlias"|"setStyle"|..., "args": [...]}')
    pdir = project(a.slug)
    try:
        path = E.sheet_file(pdir, sheet)
    except E.SpreadsheetEditError as e:
        raise UsageError(str(e)) from None
    watched = {path} | {pdir / "spreadsheet" / f"{n}.py" for n in E.sheets(pdir)} | set(extra_paths)
    watched |= {pdir / "parts" / f"{o['part']}.py" for o in ops if o.get("op") == "bind" and o.get("part")}
    before = {p: (p.read_text() if p.exists() else None) for p in watched}
    try:
        doc = E.apply(pdir, sheet, ops)
    except (ValueError, KeyError, TypeError) as e:
        raise UsageError(str(e)) from None
    changes = []
    for p, b in before.items():
        after = p.read_text() if p.exists() else None
        if after != b:
            changes.append({"path": str(p.relative_to(pdir)), "before": b, "after": after})
    # a part whose EXPRESSIONS a rename changed is written too
    for rel in doc.get("written", []):
        p = pdir / rel
        if p not in before:
            changes.append({"path": rel, "before": None, "after": p.read_text()})
    name = step or E.step_name(ops)
    if changes:
        from . import undo as un
        un.record(pdir, name, cmd, changes, by=actor(a))
    lines = [f"{a.slug}/{sheet}: {name}"] + _lines(doc)
    data = {"project": a.slug, "sheet": sheet, "step": name, "doc": doc, "file": str(path)}
    return Result(OK, data, "\n".join(lines), f"{a.slug}/{sheet}: {name}", [c["path"] for c in changes])


def _cmd(a, *words: str) -> str:
    return shlex.join(["cad", "sheet", a.sheet_cmd, a.slug, *[str(w) for w in words]])


def cmd_ls(a) -> Result:
    from . import spreadsheet_edit as E
    pdir = project(a.slug)
    names = E.sheets(pdir)
    try:
        doc = E.read(pdir)
    except E.SpreadsheetEditError as e:
        raise UsageError(str(e)) from None
    rows = [{"sheet": n, "label": doc["sheets"][n]["label"], "cells": len(doc["sheets"][n]["cells"]),
             "errors": doc["sheets"][n]["errors"]} for n in names if n in doc["sheets"]]
    text = "\n".join([f"{a.slug}: {len(names)} spreadsheet(s)"] +
                     [f"  {r['sheet']}  {r['label']!r}  {r['cells']} cell(s)" + (f", errors in {', '.join(r['errors'])}"
                                                                                  if r["errors"] else "") for r in rows]
                     + [f"  {p}: bound {', '.join(f'{k} = {v}' for k, v in d['expressions'].items())}"
                        for p, d in doc["parts"].items()])
    return Result(OK, {"project": a.slug, "sheets": rows, "parts": doc["parts"], "recompute": doc["recompute"]}, text,
                  f"{a.slug}: {len(names)} spreadsheet(s)")


def cmd_show(a) -> Result:
    from . import spreadsheet_edit as E
    try:
        doc = E.read(project(a.slug), a.sheet)
    except E.SpreadsheetEditError as e:
        raise UsageError(str(e)) from None
    return Result(OK, doc, "\n".join([f"{a.slug}/{a.sheet}"] + _lines(doc)), f"{a.slug}/{a.sheet}")


def cmd_new(a) -> Result:
    from . import spreadsheet_edit as E
    from .spreadsheet_doc import part_files, sheet_files
    pdir = project(a.slug)
    name = a.name or E.unique_name("Spreadsheet", set(sheet_files(pdir)) | set(part_files(pdir)))
    op = {"op": "new"}
    if a.label:
        op["label"] = a.label
    return apply_ops(a, name, [op], _cmd(a, *(["--sheet", name] + (["--label", a.label] if a.label else []))),
                     "Create Spreadsheet")


def _one(a, sheet, op, *words):
    return apply_ops(a, sheet, [op], _cmd(a, sheet, *words))


def cmd_set(a) -> Result:
    return _one(a, a.sheet, {"op": "set", "args": [a.cell, a.content]}, a.cell, a.content)


def cmd_alias(a) -> Result:
    return _one(a, a.sheet, {"op": "setAlias", "args": [a.cell, a.alias or ""]}, a.cell, *([a.alias] if a.alias else []))


def cmd_style(a) -> Result:
    return _one(a, a.sheet, {"op": "setStyle", "args": [a.range, a.style, a.mode]}, a.range, a.style, "--mode", a.mode)


def cmd_align(a) -> Result:
    return _one(a, a.sheet, {"op": "setAlignment", "args": [a.range, a.alignment, "keep"]}, a.range, a.alignment)


def _rgb(text):
    try:
        v = [float(x) for x in text.split(",")]
    except ValueError:
        v = []
    if len(v) not in (3, 4):
        raise UsageError(f"a colour is R,G,B or R,G,B,A between 0 and 1, got {text!r}")
    return v


def cmd_color(a) -> Result:
    ops = []
    if a.text:
        ops.append({"op": "setForeground", "args": [a.range, _rgb(a.text)]})
    if a.background:
        ops.append({"op": "setBackground", "args": [a.range, _rgb(a.background)]})
    if a.clear_text:
        ops.append({"op": "clearForeground", "args": [a.range]})
    if a.clear_background:
        ops.append({"op": "clearBackground", "args": [a.range]})
    if not ops:
        raise UsageError("say which colour: --text, --background, --clear-text or --clear-background")
    words = [a.range] + (["--text", a.text] if a.text else []) + (["--background", a.background] if a.background else []) \
        + (["--clear-text"] if a.clear_text else []) + (["--clear-background"] if a.clear_background else [])
    return apply_ops(a, a.sheet, ops, _cmd(a, a.sheet, *words))


def cmd_unit(a) -> Result:
    return _one(a, a.sheet, {"op": "setDisplayUnit", "args": [a.range, a.unit or ""]}, a.range, *([a.unit] if a.unit else []))


def cmd_merge(a) -> Result:
    return _one(a, a.sheet, {"op": "mergeCells", "args": [a.range]}, a.range)


def cmd_split(a) -> Result:
    return _one(a, a.sheet, {"op": "splitCell", "args": [a.cell]}, a.cell)


def _rows_cols(kind):
    def run(a) -> Result:
        return _one(a, a.sheet, {"op": kind, "args": [a.at, a.count]}, a.at, a.count)
    return run


def cmd_width(a) -> Result:
    return _one(a, a.sheet, {"op": "setColumnWidth", "args": [a.at, a.size]}, a.at, a.size)


def cmd_height(a) -> Result:
    return _one(a, a.sheet, {"op": "setRowHeight", "args": [a.at, a.size]}, a.at, a.size)


def cmd_clear(a) -> Result:
    return _one(a, a.sheet, {"op": "clear", "args": [a.range]}, a.range)


def cmd_import(a) -> Result:
    text = Path(a.file).expanduser().read_text(encoding="utf-8")
    return apply_ops(a, a.sheet, [{"op": "import", "text": text}], _cmd(a, a.sheet, a.file), "Import Spreadsheet")


def cmd_export(a) -> Result:
    from .spreadsheet_doc import Document
    pdir = project(a.slug)
    doc = Document.of_project(pdir)
    doc.recompute()
    sh = doc.objects.get(a.sheet)
    if sh is None or getattr(sh, "cells", None) is None:
        raise UsageError(f"there is no spreadsheet {a.sheet!r}")
    text = sh.export_text()
    out = Path(a.file).expanduser() if a.file else pdir / "out" / "spreadsheet" / f"{a.sheet}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return Result(OK, {"project": a.slug, "sheet": a.sheet, "wrote": str(out), "text": text}, f"wrote {out}",
                  f"{a.slug}/{a.sheet}: exported", [str(out)])


def cmd_bind(a) -> Result:
    from . import spreadsheet_edit as E
    sheet = a.sheet or (E.sheets(project(a.slug)) or [None])[0]
    if sheet is None:
        raise UsageError("the project has no spreadsheet")
    op = {"op": "bind", "part": a.part, "param": a.param, "expression": a.expression}
    return apply_ops(a, sheet, [op], _cmd(a, a.part, a.param, *([a.expression] if a.expression else [])),
                     "Set expression")


def cmd_apply(a) -> Result:
    text = a.ops
    if text.startswith("@"):
        text = Path(text[1:]).read_text()
    try:
        ops = json.loads(text)
    except ValueError as e:
        raise UsageError(f"--ops is JSON: {e}") from None
    if a.dry_run:
        from . import spreadsheet_edit as E
        try:
            doc = E.apply(project(a.slug), a.sheet, ops, write=False)
        except (ValueError, KeyError) as e:
            raise UsageError(str(e)) from None
        return Result(OK, {"project": a.slug, "sheet": a.sheet, "doc": doc, "dry_run": True}, "\n".join(_lines(doc)),
                      f"{a.slug}/{a.sheet}: preview")
    words = [a.sheet, "--ops", json.dumps(ops, separators=(",", ":"))] + (["--name", a.name] if a.name else [])
    return apply_ops(a, a.sheet, ops, _cmd(a, *words), a.name)


def cmd_delete(a) -> Result:
    return apply_ops(a, a.sheet, [{"op": "delete"}], _cmd(a, a.sheet), "Delete")


def add_parsers(add, sub) -> None:
    """cli.py's build_parser hands its `add` and the subparsers here."""
    tp = add("sheet", None, "a project's spreadsheets (FreeCAD's Spreadsheet workbench): new, set, alias, style, align, "
             "color, unit, merge, rows and columns, import, export, bind; each change one undo step")
    from .cmdbase import Parser
    tsub = tp.add_subparsers(dest="sheet_cmd", metavar="<action>", parser_class=Parser)

    def one(name, func, help, sheet=True):
        sp = add(name, func, help, parent=tsub)
        sp.set_defaults(cmd_name=f"sheet {name}", sheet_cmd=name)
        sp.add_argument("slug")
        if sheet:
            sp.add_argument("sheet")
        return sp

    one("ls", cmd_ls, "the project's spreadsheets and the parts bound to them", sheet=False)
    one("show", cmd_show, "every used cell: content, value, error and what the sheet view shows")
    sp = one("new", cmd_new, "Spreadsheet_CreateSheet: a new sheet", sheet=False)
    sp.add_argument("--sheet", dest="name", help="the sheet's Name (default Spreadsheet, Spreadsheet001, ...)")
    sp.add_argument("--label")
    sp = one("set", cmd_set, "a cell's content, as typed in the sheet ('=B1*2', \"'text\", '12.5', '3 mm'; '' clears)")
    sp.add_argument("cell")
    sp.add_argument("content")
    sp = one("alias", cmd_alias, "Set Alias (without ALIAS: the alias removed)")
    sp.add_argument("cell")
    sp.add_argument("alias", nargs="?")
    sp = one("style", cmd_style, "bold, italic or underline ('bold|italic' for several)")
    sp.add_argument("range")
    sp.add_argument("style")
    sp.add_argument("--mode", default="add", choices=["add", "remove", "replace", "invert"])
    sp = one("align", cmd_align, "Spreadsheet_AlignLeft ... _AlignBottom")
    sp.add_argument("range")
    sp.add_argument("alignment", choices=["left", "center", "right", "top", "vcenter", "bottom"])
    sp = one("color", cmd_color, "the text or background colour (R,G,B between 0 and 1)")
    sp.add_argument("range")
    sp.add_argument("--text", metavar="R,G,B")
    sp.add_argument("--background", metavar="R,G,B")
    sp.add_argument("--clear-text", action="store_true")
    sp.add_argument("--clear-background", action="store_true")
    sp = one("unit", cmd_unit, "the display unit (cm, in, deg ...; without UNIT: none)")
    sp.add_argument("range")
    sp.add_argument("unit", nargs="?")
    sp = one("merge", cmd_merge, "Spreadsheet_MergeCells")
    sp.add_argument("range")
    sp = one("split", cmd_split, "Spreadsheet_SplitCell")
    sp.add_argument("cell")
    for name, kind, what in (("insert-rows", "insertRows", "ROW"), ("remove-rows", "removeRows", "ROW"),
                             ("insert-columns", "insertColumns", "COL"), ("remove-columns", "removeColumns", "COL")):
        sp = one(name, _rows_cols(kind), f"{kind}: references, aliases and merged cells follow")
        sp.add_argument("at", metavar=what)
        sp.add_argument("count", nargs="?", type=int, default=1)
    sp = one("width", cmd_width, "a column's width in pixels")
    sp.add_argument("at", metavar="COL")
    sp.add_argument("size", type=int)
    sp = one("height", cmd_height, "a row's height in pixels")
    sp.add_argument("at", metavar="ROW")
    sp.add_argument("size", type=int)
    sp = one("clear", cmd_clear, "Delete: the cells' contents and look")
    sp.add_argument("range")
    sp = one("import", cmd_import, "Spreadsheet_Import: a CSV file into the sheet (it is cleared first)")
    sp.add_argument("file")
    sp = one("export", cmd_export, "Spreadsheet_Export: the sheet's values as CSV (default out/spreadsheet/<Sheet>.csv)")
    sp.add_argument("file", nargs="?")
    sp = add("bind", cmd_bind, "bind a part's PARAMS entry to an expression (EXPRESSIONS; without one: unbound)",
             parent=tsub)
    sp.set_defaults(cmd_name="sheet bind", sheet_cmd="bind")
    sp.add_argument("slug")
    sp.add_argument("part")
    sp.add_argument("param")
    sp.add_argument("expression", nargs="?")
    sp.add_argument("--sheet", help="the sheet the undo step is filed under (default: the first)")
    sp = one("apply", cmd_apply, "several ops as one undo step: --ops '[{\"op\": \"set\", \"args\": [\"A1\", \"5\"]}]'")
    sp.add_argument("--ops", required=True, metavar="JSON")
    sp.add_argument("--name", help="the undo step's name (default: FreeCAD's transaction's)")
    sp.add_argument("--dry-run", action="store_true")
    one("delete", cmd_delete, "Std_Delete of the sheet")

# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses what FreeCAD's Spreadsheet commands do to a document and keeps FreeCAD's
# licence, the GNU Lesser General Public License, version 2.1 or (at your option) any later version; the text is in
# ../ui/LICENSE.
#
#   Derived from: src/Mod/Spreadsheet/Gui/Command.cpp, SheetTableView.cpp, SpreadsheetView.cpp, PropertiesDialog.cpp,
#                 SheetModel.cpp, Workbench.cpp (Copyright (c) 2015 Eivind Kvedalen)
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
"""The app's and the CLI's edits of a project's spreadsheets, written back into spreadsheet/<Name>.py as Python.

read(pdir, name) gives the sheet as the page shows it (each used cell's content, look, computed value, error and what
the view displays), recomputed with the rest of the project's document; apply(pdir, name, ops) runs the ops on the
document and writes back every sheet (and part) it changed, all or nothing: a cell entry the edit did not change keeps
its text.

An op is a Sheet method of FreeCAD's Python API, as the GUI's commands call it (Gui::Command::doCommand lines):

    {"op": "set", "args": ["A1", "=B1 * 2"]}               Edit cell (SheetModel::setCellData), also a range
    {"op": "setAlias", "args": ["A1", "thick"]}            the Alias line edit, Set Alias
    {"op": "setStyle", "args": ["A1:B2", "bold", "add"]}   Spreadsheet_StyleBold ... ('replace', 'add', 'remove', 'invert')
    {"op": "setAlignment", "args": ["A1", "left", "keep"]} Spreadsheet_AlignLeft ... ('replace', 'keep')
    {"op": "setForeground" | "setBackground", "args": ["A1", [r, g, b(, a)]]}, {"op": "clearForeground", ...}
    {"op": "setDisplayUnit", "args": ["A1", "cm"]}         the Properties dialog
    {"op": "mergeCells", "args": ["A1:B2"]}, {"op": "splitCell", "args": ["A1"]}
    {"op": "insertRows" | "removeRows", "args": ["3", 2]}, {"op": "insertColumns" | "removeColumns", "args": ["B", 1]}
    {"op": "setColumnWidth", "args": ["A", 140]}, {"op": "setRowHeight", "args": ["3", 40]}
    {"op": "clear", "args": ["A1:B2"]}, {"op": "recomputeCells", "args": ["A1", "B2"]}
    {"op": "paste", "clip": [...], "to": "C3:D4", "cut": [ranges]?}   SheetTableView::pasteClipboard
    {"op": "import", "text": csv}                           Spreadsheet_Import (Sheet::importFromFile)
    {"op": "new", "label"?}                                 Spreadsheet_CreateSheet
    {"op": "label", "to": text}                             a rename in the tree
    {"op": "delete"}                                        Std_Delete of the sheet
    {"op": "bind", "part": p, "param": k, "expression": e|null}   a part's PARAMS entry bound (or unbound) to an expression
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

from . import fcexpr as X
from . import spreadsheet as SS
from .spreadsheet import DIR, LIST, NAME, SpreadsheetError, string_to_address
from .spreadsheet_doc import Document, DependencyCycle, entries, part_files, sheet_files
from .spreadsheet_sheet import EXPRESSION_SET, display

SHEET_METHODS = {"set", "setAlias", "setStyle", "setAlignment", "setForeground", "setBackground", "clearForeground",
                 "clearBackground", "setDisplayUnit", "mergeCells", "splitCell", "insertRows", "removeRows",
                 "insertColumns", "removeColumns", "setColumnWidth", "setRowHeight", "clear", "recomputeCells",
                 "touchCells"}

# FreeCAD's transaction names (QT_TRANSLATE_NOOP("Command", ...)) for the undo journal
STEP_NAMES = {"new": "Create Spreadsheet", "set": "Edit cell", "setAlias": "Set alias", "mergeCells": "Merge cells",
              "splitCell": "Split cell", "insertRows": "Insert Rows", "removeRows": "Remove Rows",
              "insertColumns": "Insert Columns", "removeColumns": "Remove Columns", "clear": "Clear Cells",
              "paste": "Paste Cell", "import": "Import Spreadsheet", "delete": "Delete",
              "recomputeCells": "Recompute Cells", "setDisplayUnit": "Set cell properties",
              "setForeground": "Set text color", "clearForeground": "Clear text color",
              "setBackground": "Set background color", "clearBackground": "Clear background color",
              "setColumnWidth": "Resize column", "setRowHeight": "Resize row", "bind": "Set expression"}
_ALIGN_STEPS = {"left": "Left-align cell", "center": "Center cell", "right": "Right-align cell", "top": "Top-align cell",
                "vcenter": "Vertically center cells", "bottom": "Bottom-align cell"}
_STYLE_STEPS = {"bold": "Set bold text", "italic": "Set italic text", "underline": "Set underline text"}


def step_name(ops: list) -> str:
    if not ops:
        return "Edit spreadsheet"
    kinds = {o.get("op") for o in ops}
    if len(kinds) > 1 and kinds <= {"setAlignment", "setStyle", "setForeground", "setBackground", "clearForeground",
                                     "clearBackground", "setDisplayUnit", "setAlias"}:
        return "Set cell properties"                 # PropertiesDialog::apply
    op = ops[-1]
    k = op.get("op")
    args = op.get("args") or []
    if k == "setAlignment" and len(args) > 2 and args[2] == "keep" and args[1] in _ALIGN_STEPS:
        return _ALIGN_STEPS[args[1]]
    if k == "setAlignment":
        return "Set cell properties"
    if k == "setStyle" and len(args) > 2 and args[1] in _STYLE_STEPS:
        return _STYLE_STEPS[args[1]]
    if k == "setStyle":
        return "Set cell properties"
    if k == "label":
        return f"Rename {op.get('name', '')}.Label".replace(" .", " ")
    return STEP_NAMES.get(k, "Edit spreadsheet")


class SpreadsheetEditError(SpreadsheetError):
    pass


def sheet_file(pdir, name: str) -> Path:
    if not (isinstance(name, str) and NAME.match(name)):
        raise SpreadsheetEditError(f"{name!r} is not a sheet name")
    return Path(pdir) / DIR / f"{name}.py"


def sheets(pdir) -> list:
    return list(sheet_files(pdir))


# ── writing a sheet back ──────────────────────────────────────────────────────────────────────────────────

TEMPLATE = '''"""{name}: a spreadsheet of {slug} (FreeCAD's Spreadsheet workbench).

SHEET is the Spreadsheet::Sheet and its used cells in FreeCAD's order, each with what a FreeCAD document saves of it:
the content (a formula as "=...", a string as "'...", a number) and the cell's look. The app and `cad sheet ...` edit
it (cad_agent/spreadsheet_edit.py); values are a recompute. A part reads a cell through its EXPRESSIONS, e.g.
EXPRESSIONS = {{"thick": "{name}.thick"}}.
"""
from cad_agent import spreadsheet as Spreadsheet

SHEET = [
]
'''
PREFIX = "Spreadsheet."


def lit(v) -> str:
    if isinstance(v, bool):
        return "True" if v else "False"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, dict):
        return "{" + ", ".join(f"{lit(k)}: {lit(x)}" for k, x in v.items()) + "}"
    raise SpreadsheetEditError(f"{v!r} cannot be written in a sheet file")


def model_entries(sheet) -> list:
    """The SHEET list a sheet is saved as: the Sheet, then each cell Cell::save writes, in CellAddress order."""
    from .spreadsheet import column_name
    head = SS.Sheet(sheet.name, label=sheet.label if sheet.label != sheet.name else None,
                    column_widths={column_name(c): w for c, w in sorted(sheet.column_widths.items())
                                   if w != SS.DEFAULT_WIDTH},
                    row_heights={str(r + 1): h for r, h in sorted(sheet.row_heights.items()) if h != SS.DEFAULT_HEIGHT})
    out = [head]
    for k in sorted(sheet.cells.data):
        cell = sheet.cells.data[k]
        if not cell.saved():
            continue
        attrs = cell.attrs()
        content = cell.string_content(True) if cell.is_used(EXPRESSION_SET) else None
        if content is None and not attrs:
            continue
        out.append(SS.Cell(cell.address.to_string(), content, **attrs))
    return out


def entry_src(e) -> str:
    if isinstance(e, SS.Sheet):
        parts = [json.dumps(e.name)]
        if e.label:
            parts.append(f"label={lit(e.label)}")
        if e.column_widths:
            parts.append(f"column_widths={lit(e.column_widths)}")
        if e.row_heights:
            parts.append(f"row_heights={lit(e.row_heights)}")
        return f"{PREFIX}Sheet({', '.join(parts)})"
    parts = [json.dumps(e.address)]
    if e.content is not None:
        parts.append(lit(e.content))
    for k, v in e.attrs().items():
        parts.append(f"{k}={lit(v)}")
    return f"{PREFIX}Cell({', '.join(parts)})"


def _same(a, b) -> bool:
    return type(a) is type(b) and a.as_dict() == b.as_dict()


def write_src(src: str, new_entries: list) -> str:
    """The SHEET list written again: an entry equal to one already there keeps its text (and its comment)."""
    from .feature_edit import _Text
    t = _Text(src)
    from .spreadsheet_doc import _list_node
    lst = _list_node(t.tree)
    if lst is None:
        raise SpreadsheetEditError(f"the sheet file has no {LIST} list")
    old = entries(src) or []
    by_key = {}
    for o, call in old:
        by_key[("S", o.name) if isinstance(o, SS.Sheet) else ("C", o.address)] = (o, call)
    ind = lst.elts[0].col_offset if lst.elts else 4
    lines = []
    for e in new_entries:
        key = ("S", e.name) if isinstance(e, SS.Sheet) else ("C", e.address)
        prev = by_key.get(key)
        if prev is not None and _same(prev[0], e):
            text = t.raw[t.a(prev[1]):t.b(prev[1])].decode()
            end = t.after_comma(t.b(prev[1]))
            rest = t.raw[end:t.line_end(end)].decode().rstrip("\n")
            comment = rest if rest.strip().startswith("#") else ""
            col = prev[1].col_offset
            out = text.split("\n")
            text = "\n".join([out[0]] + [ln[col:] if ln[:col].strip() == "" else ln for ln in out[1:]])
            lines.append(" " * ind + text.replace("\n", "\n" + " " * ind) + "," + comment)
        else:
            lines.append(" " * ind + entry_src(e) + ",")
    body = "[\n" + "".join(line + "\n" for line in lines) + "]"
    return t.edit([(t.a(lst), t.b(lst), body)])


# ── what the page reads ───────────────────────────────────────────────────────────────────────────────────

def value_json(p):
    """A computed property as JSON: {"kind", "v", "dims"?, "s"} (s: str() of the Python value)."""
    if p is None:
        return None
    v = p.value
    if p.kind == "quantity":
        return {"kind": "quantity", "v": _num(v.value), "dims": list(v.dims), "s": X.py_str(v)}
    if p.kind in ("int", "float"):
        return {"kind": p.kind, "v": _num(v) if p.kind == "float" else v, "s": X.py_str(v)}
    if p.kind == "string":
        return {"kind": "string", "v": v, "s": v}
    return {"kind": "object", "type": type(v).__name__ if v is not None else "NoneType", "s": X.py_str(v)}


def _num(x):
    import math
    return x if math.isfinite(x) else repr(x)


def sheet_json(doc, sheet, prefs=None) -> dict:
    from .spreadsheet import column_name
    cells = {}
    for k in sorted(sheet.cells.data):
        c = sheet.cells.data[k]
        a = c.address
        name = a.to_string()
        d = {"content": c.string_content(), **c.attrs()}
        p = sheet.props.get(name)
        d["value"] = value_json(p)
        if c.has_exception():
            d["exception"] = c.exception
        # what SheetModel::data reads of the cell, for the page's own port of it (src/spreadsheet_model.ts)
        from .spreadsheet_sheet import (ALIAS_SET, BACKGROUND_COLOR_SET, DISPLAY_UNIT_SET, FOREGROUND_COLOR_SET,
                                        STYLE_SET)
        d["raw"] = {"alignment": c.alignment, "style": sorted(c.style) if c.is_used(STYLE_SET) else [],
                    "fg": list(c.foreground) if c.is_used(FOREGROUND_COLOR_SET) else None,
                    "bg": list(c.background) if c.is_used(BACKGROUND_COLOR_SET) else None,
                    "alias": c.alias if c.is_used(ALIAS_SET) else None,
                    "du": {"text": c.display_unit.string_rep, "dims": list(c.display_unit.unit),
                           "scaler": c.display_unit.scaler} if c.is_used(DISPLAY_UNIT_SET) else None,
                    "dirty": a.key in sheet.cells.dirty}
        d["view"] = display(sheet, a, prefs)
        cells[name] = d
    merged = {}
    for k, anchor in sheet.cells.merged.items():
        if k == anchor:
            c = sheet.cells.data.get(anchor)
            if c is not None:
                merged[c.address.to_string()] = [c.row_span, c.col_span]
    return {"name": sheet.name, "label": sheet.label, "type": "Spreadsheet::Sheet", "cells": cells, "merged": merged,
            "column_widths": {column_name(c): w for c, w in sorted(sheet.column_widths.items())},
            "row_heights": {str(r + 1): h for r, h in sorted(sheet.row_heights.items())},
            "errors": sorted(sheet.cells.data[k].address.to_string() for k in sheet.cell_errors if k in sheet.cells.data),
            "used_range": sheet.getUsedRange()}


def doc_json(doc, failed: dict, prefs=None) -> dict:
    from .spreadsheet_sheet import Sheet
    out = {"sheets": {}, "parts": {}, "recompute": failed}
    for o in doc.objects.values():
        if isinstance(o, Sheet):
            out["sheets"][o.name] = sheet_json(doc, o, prefs)
        elif o.expressions:
            out["parts"][o.name] = {"params": o.params, "bound": o.bound, "expressions": o.expressions,
                                    "errors": o.errors}
    return out


def _recompute(doc):
    try:
        return doc.recompute()
    except DependencyCycle as e:
        return {"document": str(e)}


def read(pdir, name: str | None = None, prefs=None) -> dict:
    doc = Document.of_project(pdir)
    failed = _recompute(doc)
    out = doc_json(doc, failed, prefs)
    if name is not None:
        if name not in out["sheets"]:
            raise SpreadsheetEditError(f"there is no spreadsheet {name!r} in {Path(pdir).name}")
        out["sheet"] = out["sheets"][name]
    return out


# ── the ops ────────────────────────────────────────────────────────────────────────────────────────────

def unique_name(base: str, taken) -> str:
    from .techdraw_edit import unique_name as un
    return un(base, set(taken))


def run_op(doc, sheet, op: dict) -> str:
    k = op.get("op")
    args = list(op.get("args") or [])
    if k in SHEET_METHODS:
        fn = getattr(sheet, k)
        if k in ("setForeground", "setBackground") and len(args) > 1 and isinstance(args[1], list):
            args[1] = tuple(args[1])
        try:
            fn(*args)
        except TypeError as e:
            raise SpreadsheetEditError(f"{k}: {e}") from None
        return k
    if k == "paste":
        from .spreadsheet import Range
        for r in op.get("cut") or []:
            sheet.clear(r)
        sheet.paste_cells(op.get("clip") or [], Range(op["to"]))
        return k
    if k == "import":
        sheet.import_text(op.get("text") or "", op.get("delimiter", "\t"), op.get("quote", '"'), op.get("escape", "\\"))
        return k
    if k == "label":
        to = op.get("to")
        if not isinstance(to, str) or not to:
            raise SpreadsheetEditError("a label is a non-empty text")
        sheet.label = to
        return k
    raise SpreadsheetEditError(f"unknown op {k!r}")


def apply(pdir, name: str, ops, write: bool = True, prefs=None) -> dict:
    """The ops on spreadsheet/<name>.py (and the parts they bind), all or nothing; returns read() of the result."""
    from . import state
    pdir = Path(pdir)
    ops = list(ops)
    path = sheet_file(pdir, name)
    created = False
    extra = {}
    if ops and ops[0].get("op") == "new":
        if path.exists():
            raise SpreadsheetEditError(f"there is already a spreadsheet {name!r}")
        taken = set(sheet_files(pdir)) | set(part_files(pdir))
        if name in taken:
            raise SpreadsheetEditError(f"there is already an object {name!r} in the project")
        label = ops[0].get("label")
        src = TEMPLATE.format(name=name, slug=pdir.name)
        head = SS.Sheet(name, label=label)
        src = write_src(src, [head])
        extra[name] = src
        created = True
        ops = ops[1:]
    elif not path.exists():
        raise SpreadsheetEditError(f"there is no spreadsheet {name!r}: make it first (cad sheet new)")
    doc = Document.of_project(pdir, extra)
    try:
        doc.recompute()
    except DependencyCycle:
        pass
    sheet = doc.objects[name]
    done = []
    bound_parts = {}
    for op in ops:
        if op.get("op") == "delete":
            if write:
                path.unlink(missing_ok=True)
            return {"deleted": name, "done": done + ["delete"]}
        if op.get("op") == "bind":
            part = doc.objects.get(op.get("part"))
            if part is None or getattr(part, "kind", "") != "part":
                raise SpreadsheetEditError(f"there is no part {op.get('part')!r}")
            param, expr = op.get("param"), op.get("expression")
            if param not in part.params:
                raise SpreadsheetEditError(f"{part.name} has no parameter {param!r}")
            if expr:
                err = doc.validate_expression(part, param, expr)
                if err:
                    raise SpreadsheetEditError(err)
                part.expressions[param] = expr
            else:
                part.expressions.pop(param, None)
            bound_parts[part.name] = part
            done.append("bind")
            continue
        try:
            done.append(run_op(doc, sheet, op))
        except X.ExprError as e:
            raise SpreadsheetEditError(e.message) from None
    failed = _recompute(doc)
    out = doc_json(doc, failed, prefs)
    out["sheet"] = out["sheets"].get(name)
    out["done"] = done
    if write:
        from .spreadsheet_sheet import Sheet
        writes = {}
        for o in doc.objects.values():
            if not isinstance(o, Sheet):
                continue
            p = sheet_file(pdir, o.name)
            old = extra.get(o.name) if o.name in extra else (p.read_text() if p.exists() else None)
            if old is None:
                continue
            new = write_src(old, model_entries(o))
            if new != old or (created and o.name == name):
                writes[p] = new
        for pn in set(bound_parts) | set(doc.renamed_parts):
            part = doc.objects[pn]
            pp = pdir / "parts" / f"{pn}.py"
            src = pp.read_text()
            new = write_expressions(src, part.expressions)
            if new != src:
                writes[pp] = new
        for p, text in writes.items():
            p.parent.mkdir(exist_ok=True)
            state.write_atomic(p, text)
        out["written"] = sorted(str(p.relative_to(pdir)) for p in writes)
    return out


def write_expressions(src: str, expressions: dict) -> str:
    """A part module's EXPRESSIONS dict written in place (after PARAMS when the module has none yet)."""
    from .feature_edit import _Text
    t = _Text(src)
    node = None
    params = None
    for n in t.tree.body:
        if isinstance(n, ast.Assign) and any(isinstance(x, ast.Name) and x.id == "EXPRESSIONS" for x in n.targets):
            node = n
        if isinstance(n, ast.Assign) and any(isinstance(x, ast.Name) and x.id == "PARAMS" for x in n.targets) \
                and params is None:
            params = n
    body = "{" + ", ".join(f"{json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in expressions.items()) + "}"
    if node is not None:
        if not expressions:
            a = t.line_start(t.a(node))
            return t.edit([(a, t.line_end(t.b(node)), "")])
        return t.edit([(t.a(node.value), t.b(node.value), body)])
    if not expressions:
        return src
    if params is None:
        raise SpreadsheetEditError("the part has no PARAMS to bind")
    at = t.line_end(t.b(params))
    line = f"EXPRESSIONS = {body}   # FreeCAD's ExpressionEngine: PARAMS bound to expressions (spreadsheet cells)\n"
    return t.edit([(at, at, line)])

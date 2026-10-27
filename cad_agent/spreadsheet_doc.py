# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses how FreeCAD's document resolves, orders and recomputes expressions and keeps
# FreeCAD's licence, the GNU Lesser General Public License, version 2.1 or (at your option) any later version; the text
# is in ../ui/LICENSE.
#
#   Derived from: src/App/ObjectIdentifier.cpp (Copyright (c) 2015 Eivind Kvedalen): getDocumentObject, resolve,
#                 resolveAmbiguity, resolveErrorString, access;
#                 src/App/PropertyExpressionEngine.cpp (Copyright (c) 2015 Eivind Kvedalen): validateExpression;
#                 src/App/Document.cpp (Copyright (c) 2002 Jürgen Riegel): recompute's topological order
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
"""The project as FreeCAD's one document of expressions: its spreadsheets (spreadsheet/<Name>.py) and its parts, whose
PARAMS are the Body's properties and whose EXPRESSIONS bind them (docs/EDITING_PLAN.md, "Spreadsheets in a project").

Document(name, sheets={Name: SHEET source}, parts={name: part source}) reads every sheet as FreeCAD restores one
(PropertySheet::Restore, afterRestore, Sheet::onDocumentRestored), resolves names as ObjectIdentifier does (an
identifier by Name then Label, <<x>> by Label), and recompute() runs the objects in dependency order: a sheet's
Sheet::execute, a part's ExpressionEngine. bound_params(part) is a part's PARAMS as its EXPRESSIONS leave them;
bind(module) applies them to a part module that state._load_module has run.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from . import fcexpr as X
from .spreadsheet import DIR, LIST, CellAddress, Range, SpreadsheetError, decode_column, string_to_address, valid_row
from . import spreadsheet as SS

ANGLE = (0, 0, 0, 0, 0, 0, 0, 1)
LENGTH = (1, 0, 0, 0, 0, 0, 0, 0)
ONE = (0, 0, 0, 0, 0, 0, 0, 0)


def param_kind(name: str, value) -> str | None:
    """What property a part's parameter is (the app's panels.tsx paramKind): 'Angle', 'Length' or None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if re.search(r"angle|(^|_)deg|deg($|_)|tilt|twist|draft", name, re.I):
        return "Angle"
    if isinstance(value, int) or re.search(r"ratio|scale|factor|count|frac|percent|(^|_)n($|_)", name, re.I):
        return None
    return "Length"


def param_py(name: str, value):
    """A parameter as the Python value an expression reads: an int is a PropertyInteger, a length or an angle a
    Quantity, any other number a PropertyFloat, a str a PropertyString, a bool a PropertyBool."""
    kind = param_kind(name, value)
    if kind is None:
        if isinstance(value, bool) or isinstance(value, int) or isinstance(value, str):
            return value
        if isinstance(value, float):
            return value
        return value
    return X.Quantity(float(value), ANGLE if kind == "Angle" else LENGTH)


class DependencyCycle(SpreadsheetError):
    pass


# ── the files ─────────────────────────────────────────────────────────────────────────────────────────────

def _list_node(tree):
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == LIST for t in node.targets):
            if not isinstance(node.value, ast.List):
                raise SpreadsheetError(f"{LIST} is not a list the app can edit")
            return node.value
    return None


def _kind(call):
    f = call.func
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "Spreadsheet":
        return f.attr
    return None


def _lit(node, src):
    try:
        return ast.literal_eval(node)
    except ValueError:
        raise SpreadsheetError(f"{ast.get_source_segment(src, node)!r} is not a literal the app can read") from None


def entries(src: str):
    """[(Sheet | Cell, call node)] of a sheet file's SHEET list, or None when it has none."""
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        raise SpreadsheetError(f"the sheet does not parse: {e}") from None
    lst = _list_node(tree)
    if lst is None:
        return None
    out = []
    for e in lst.elts:
        cls = SS.CLASSES.get(_kind(e)) if isinstance(e, ast.Call) else None
        if cls is None:
            raise SpreadsheetError(f"{LIST} holds {ast.get_source_segment(src, e)[:60]!r}, not a Spreadsheet.Sheet or "
                                   "Spreadsheet.Cell call")
        args = [_lit(a, src) for a in e.args]
        kw = {k.arg: _lit(k.value, src) for k in e.keywords}
        try:
            out.append((cls(*args, **kw), e))
        except TypeError as err:
            raise SpreadsheetError(str(err)) from None
    return out


def part_params(src: str) -> tuple[dict, dict]:
    """A part module's literal PARAMS and EXPRESSIONS, read from its source without running it."""
    from .params import read_src
    params = read_src(src)
    expressions = {}
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return params, {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "EXPRESSIONS" for t in node.targets):
            try:
                v = ast.literal_eval(node.value)
            except ValueError:
                v = {}
            if isinstance(v, dict):
                expressions = {str(k): str(x) for k, x in v.items()}
    return params, expressions


def sheet_files(pdir) -> dict:
    d = Path(pdir) / DIR
    if not d.is_dir():
        return {}
    return {p.stem: p for p in sorted(d.glob("*.py")) if not p.stem.startswith(("_", "."))}


def part_files(pdir) -> dict:
    d = Path(pdir) / "parts"
    if not d.is_dir():
        return {}
    return {p.stem: p for p in sorted(d.glob("*.py")) if not p.stem.startswith(("_", "."))}


# ── the document's objects ────────────────────────────────────────────────────────────────────────────────

class PartObject:
    """A part as the document object an expression names: its PARAMS are its properties."""
    kind = "part"

    def __init__(self, name: str, params: dict, expressions: dict):
        self.name = name
        self.label = name
        self.params = dict(params)        # the literal values (what FreeCAD saved)
        self.expressions = dict(expressions)
        self.bound = dict(params)         # after the ExpressionEngine
        self.errors: dict = {}

    def get_property(self, prop: str):
        if prop in self.bound:
            return param_py(prop, self.bound[prop])
        if prop == "Label":
            return self.label
        return _MISSING


_MISSING = object()


class Document:
    """FreeCAD's document of a project: its sheets and parts by Name (spreadsheet/ files and parts/ modules)."""

    def __init__(self, name: str, sheets: dict | None = None, parts: dict | None = None):
        from .spreadsheet_sheet import Sheet
        self.name = name
        self.objects: dict = {}           # Name -> Sheet | PartObject, in document order
        self.sheet_entries: dict = {}     # Name -> the file's (Sheet entry, [Cell entries])
        self._order: list = []
        self.renamed_parts: set = set()
        for pname, src in (parts or {}).items():
            params, exprs = part_params(src) if isinstance(src, str) else src
            self.objects[pname] = PartObject(pname, params, exprs)
        for sname, src in (sheets or {}).items():
            es = entries(src) if isinstance(src, str) else src
            if es is None:
                raise SpreadsheetError(f"spreadsheet/{sname}.py has no {LIST} list")
            es = [e for e, _ in es] if es and isinstance(es[0], tuple) else list(es)
            head = [e for e in es if isinstance(e, SS.Sheet)]
            if len(head) != 1:
                raise SpreadsheetError(f"spreadsheet/{sname}.py: {LIST} needs one Spreadsheet.Sheet, first")
            h = head[0]
            sh = Sheet(h.name, self, h.label)
            self.objects[h.name] = sh
            self.sheet_entries[h.name] = (h, [e for e in es if isinstance(e, SS.Cell)])
        for sname, (h, cells) in self.sheet_entries.items():
            self._restore(self.objects[sname], h, cells)

    def add_sheet(self, name: str, label: str | None = None):
        """doc.addObject("Spreadsheet::Sheet", name)."""
        from .spreadsheet_sheet import Sheet
        if name in self.objects:
            raise SpreadsheetError(f"there is already an object {name!r}")
        sh = Sheet(name, self, label)
        self.objects[name] = sh
        return sh

    @classmethod
    def of_project(cls, pdir, extra_sheets: dict | None = None) -> "Document":
        pdir = Path(pdir)
        sheets = {n: p.read_text() for n, p in sheet_files(pdir).items()}
        sheets.update(extra_sheets or {})
        parts = {n: p.read_text() for n, p in part_files(pdir).items()}
        return cls(pdir.name, sheets, parts)

    def _restore(self, sheet, head, cells):
        """PropertySheet::Restore: each cell's content (kept raw while restoring) and attributes, merged cells; then
        afterRestore sets every content again, so aliases defined later in the file are known."""
        for k, v in head.column_widths.items():
            sheet.column_widths[decode_column(k)] = v
        for k, v in head.row_heights.items():
            sheet.row_heights[valid_row(k)] = v
        ps = sheet.cells
        ps.restoring = True
        for c in cells:
            addr = string_to_address(c.address)
            cell = ps.create_cell(addr)
            cell.restore({"content": c.content if c.content is not None else "", **c.attrs()})
            rows, cols = cell.spans()
            if cell.is_used(SS_SPANS) and (rows > 1 or cols > 1):
                ps.merge_cells(addr, CellAddress(addr.row + rows - 1, addr.col + cols - 1))
        ps.after_restore()

    # ── names, as ObjectIdentifier finds them ──────────────────────────────────────────────────────────
    def find(self, name: str, is_string: bool):
        """ObjectIdentifier::getDocumentObject: (object, how) with how 'id', 'label', 'both', 'ambiguous' or None."""
        by_id = None
        if not is_string:
            by_id = self.objects.get(name)
        by_label = None
        for o in self.objects.values():
            if o.label == name:
                if by_label is not None:
                    return None, "ambiguous"
                by_label = o
        if by_label is None and by_id is None:
            return None, None
        if by_label is None:
            return by_id, "id"
        if by_id is None:
            return by_label, "label"
        if by_label is by_id:
            return by_id, "both"
        return None, "ambiguous"

    def changed(self, obj, prop: str):
        """PropertySheet::slotChangedObject on every other sheet: the cells reading obj.prop are dirty."""
        from .spreadsheet_sheet import Sheet
        base = self.full_name(obj) + "."
        for o in self.objects.values():
            if o is obj or not isinstance(o, Sheet):
                continue
            for name in (base, base + prop):
                for k in sorted(o.cells.prop_to_cells.get(name, ())):
                    o.cells.set_dirty(CellAddress(*k))

    def sheet_object(self, obj):
        from .spreadsheet_sheet import Sheet
        return obj if isinstance(obj, Sheet) else None

    def full_name(self, obj) -> str:
        return f"{self.name}#{obj.name}" if hasattr(obj, "name") else str(obj)

    def ambiguity_hook(self, owner):
        """The parser's `object '.' id_or_cell` (ObjectIdentifier::resolveAmbiguity at parse time): the owner's name is
        dropped, another object's is kept by Name or as <<Label>>, an unknown one is the owner's property."""
        def hook(obj_ref, prop, owner_name=None):
            found, how = self.find(obj_ref.name, obj_ref.str)
            if found is owner:
                return X.VarPath(names=[prop], owner_named=True)
            if found is not None:
                if how in ("id", "both"):
                    return X.VarPath(obj=X.Ref(name=found.name, str=False), names=[prop], forced=True)
                return X.VarPath(obj=X.Ref(name=found.label, str=True), names=[prop], forced=True)
            # the owner's property obj_ref with an attribute: written ".A1.Value" when the owner has that property
            # (ObjectIdentifier::toString), as it was typed when it has not
            if self._owner_has(owner, obj_ref.name):
                return X.VarPath(names=[obj_ref.name, prop])
            return X.VarPath(names=[obj_ref.name, prop], plain=True)
        return hook

    @staticmethod
    def _owner_has(owner, name: str) -> bool:
        from .spreadsheet_sheet import Sheet
        if isinstance(owner, Sheet):
            return (string_to_address(name, True).is_valid() or owner.cells.value_from_alias(name) is not None
                    or name in ("Label", "Label2"))
        return owner.get_property(name) is not _MISSING

    def _target(self, owner, path):
        """(object, property name, rest) a path names, or (None, error message)."""
        if path.obj is not None:
            found, how = self.find(path.obj.name, path.obj.str)
            if found is None:
                if how == "ambiguous":
                    return None, f"Ambiguous document object name '{path.obj.name}' in '{self.name}'", None
                shown = f"<<{path.obj.name}>>" if path.obj.str else path.obj.name
                return None, f"Document object '{shown}' not found in '{self.name}'", None
            return found, path.names[0], path.names[1:]
        if len(path.names) >= 2 and not path.local:
            found, how = self.find(path.names[0], False)
            if found is not None and found is not owner:
                return found, path.names[1], path.names[2:]
        return owner, path.names[0], path.names[1:]

    def _written(self, path, obj) -> str:
        """The object's name as the text gave it (ResolveResults::resolvedDocumentObjectName)."""
        if path.obj is not None:
            return path.obj.name
        if len(path.names) >= 2 and self.objects.get(path.names[0]) is obj or (
                len(path.names) >= 2 and getattr(obj, "label", None) == path.names[0]):
            return path.names[0]
        return obj.name

    def deps_of(self, owner, expr):
        """getIdentifiers + getDep(true): (object, [property]) per name the expression reads; a range's cells are the
        owner's."""
        from .spreadsheet_sheet import Sheet
        if isinstance(owner, Sheet):
            for n in X.walk(expr):
                if isinstance(n, X.Range):
                    for end in (n.a, n.b):
                        if not string_to_address(end, True).is_valid() and owner.cells.value_from_alias(end) is None:
                            raise SpreadsheetError(f"Invalid cell address '{end}': Invalid cell specifier.\n"
                                                   f"in expression: {X.to_text(n)}")
        out = []
        for path in X.identifiers(expr):
            obj, prop, _ = self._target(owner, path)
            if obj is None:
                continue
            out.append((obj, [prop]))
        return out

    def object_deps(self, obj) -> list:
        """The objects obj's expressions read (its in-document dependencies)."""
        from .spreadsheet_sheet import Sheet
        seen = []
        if isinstance(obj, Sheet):
            for cell in obj.cells.data.values():
                if cell.expression is None:
                    continue
                try:
                    got = self.deps_of(obj, cell.expression)
                except SpreadsheetError:
                    continue
                for o, _ in got:
                    if o is not obj and o not in seen:
                        seen.append(o)
        else:
            for text in obj.expressions.values():
                try:
                    node = X.parse(text, owner=obj.name, resolve_ambiguity=self.ambiguity_hook(obj),
                                   names=frozenset(obj.params))
                except X.ExprError:
                    continue
                for o, _ in self.deps_of(obj, node):
                    if o is not obj and o not in seen:
                        seen.append(o)
        return seen

    # ── evaluation ─────────────────────────────────────────────────────────────────────────────────────
    def _value(self, owner, obj, prop, written=None):
        """The property's Python value, or raise FreeCAD's error (ObjectIdentifier::access)."""
        from .spreadsheet_sheet import Sheet
        shown = written or obj.name
        if isinstance(obj, Sheet):
            p = obj.get_property(prop)
            if p is None:
                raise X.ExprError(f"Property '{prop}' not found in '{shown}'", "RuntimeError")
            return p.value
        v = obj.get_property(prop)
        if v is _MISSING:
            raise X.ExprError(f"Property '{prop}' not found in '{shown}'", "RuntimeError")
        return v

    def env(self, owner):
        from .spreadsheet_sheet import Sheet
        doc = self

        class Vars:
            """The owner's properties, found as Sheet::getPropertyByName finds them."""
            def __contains__(self, name):
                if isinstance(owner, Sheet):
                    return owner.get_property(name) is not None
                return owner.get_property(name) is not _MISSING

            def __getitem__(self, name):
                return doc._value(owner, owner, name)

            def get(self, name, default=None):
                return doc._value(owner, owner, name) if self.__contains__(name) else default

            def keys(self):
                return []

        def resolve(path):
            obj, prop, rest = self._target(owner, path)
            if obj is None:
                raise X.ExprError(prop, "RuntimeError")
            return self._value(owner, obj, prop, self._written(path, obj)), rest

        def range_cells(node):
            if not isinstance(owner, Sheet):
                return None
            return self.range_cells(owner, node)

        return X.Env(vars=Vars(), owner=owner.name, doc=self.name, resolve=resolve, range_cells=range_cells)

    def range_cells(self, sheet, node):
        """RangeExpression::getRange (aliases at either end, through getCellFromAlias) and the cells' properties in
        Range order: [(address, value, kind)] of the cells that have one."""
        c1 = string_to_address(node.a, True)
        c2 = string_to_address(node.b, True)
        for side, c in (("a", c1), ("b", c2)):
            if not c.is_valid():
                text = getattr(node, side)
                cell = sheet.cells.value_from_alias(text)
                if cell is None:
                    raise X.ExprError(f"Invalid cell address '{text}': Invalid cell specifier.\nin expression: "
                                      f"{X.to_text(node)}", "RuntimeError")
                if side == "a":
                    c1 = cell.address
                else:
                    c2 = cell.address
        out = []
        for a in Range(c1, c2):
            p = sheet.get_property(a.to_string(absolute=False))
            if p is not None:
                out.append((a.to_string(), p.value, p.kind))
        return out

    def eval_cell(self, sheet, node):
        return X.evaluate(node, self.env(sheet))

    # ── recompute ──────────────────────────────────────────────────────────────────────────────────────
    def order(self, strict=True):
        """Document::recompute's order: each object after what it reads; a cycle is "The graph must be a DAG."
        (strict=False: the objects in document order then, as they stand)."""
        objs = list(self.objects.values())
        deps = {o.name: [d.name for d in self.object_deps(o)] for o in objs}
        state, out = {}, []
        for o in objs:
            if o.name in state:
                continue
            stack = [(o.name, iter(deps[o.name]))]
            state[o.name] = 1
            while stack:
                n, it = stack[-1]
                for d in it:
                    if d not in deps:
                        continue
                    if state.get(d) == 1:
                        cyc = [x for x, _ in stack]
                        cyc = cyc[cyc.index(d):] + [d]
                        if not strict:
                            return list(self.objects.values()), cyc
                        raise DependencyCycle("The graph must be a DAG. (" + " -> ".join(cyc) + ")")
                    if d not in state:
                        state[d] = 1
                        stack.append((d, iter(deps[d])))
                        break
                else:
                    state[n] = 2
                    out.append(self.objects[n])
                    stack.pop()
        return out if strict else (out, None)

    def recompute(self) -> dict:
        """Every object in order; {name: message} of the objects that failed. A dependency cycle fails all."""
        from .spreadsheet_sheet import Sheet
        failed = {}
        objs, cycle = self.order(strict=False)
        if cycle:
            failed["document"] = "The graph must be a DAG. (" + " -> ".join(cycle) + ")"
        for o in objs:
            if isinstance(o, Sheet):
                msg = o.execute()
                if msg:
                    failed[o.name] = msg
            else:
                before = dict(o.bound)
                self._bind_part(o)
                for k, v in o.bound.items():
                    if before.get(k) != v:
                        self.changed(o, k)
                if o.errors:
                    failed[o.name] = "; ".join(f"{k}: {v}" for k, v in o.errors.items())
        return failed

    def _bind_part(self, part: PartObject):
        """PropertyExpressionEngine::execute for a part: each bound parameter set from its expression's value."""
        part.bound = dict(part.params)
        part.errors = {}
        for prop, text in part.expressions.items():
            if prop not in part.params:
                part.errors[prop] = f"Property '{prop}' not found in '{part.name}'"
                continue
            try:
                node = X.parse(text, owner=part.name, resolve_ambiguity=self.ambiguity_hook(part),
                               names=frozenset(part.params))
                v = X.evaluate(node, self.env(part))
                part.bound[prop] = coerce_param(prop, part.params[prop], v)
            except X.ExprError as e:
                part.errors[prop] = e.message
            except SpreadsheetError as e:
                part.errors[prop] = str(e)

    def validate_expression(self, obj, prop: str, text: str) -> str | None:
        """PropertyExpressionEngine::validateExpression (fine-grained): a parse error, or "cyclic reference to ..."
        when the expression reads an object that already depends on obj."""
        try:
            node = X.parse(text, owner=obj.name, resolve_ambiguity=self.ambiguity_hook(obj),
                           names=frozenset(getattr(obj, "params", {}) or {}))
        except X.ExprError as e:
            return e.message
        inlist = self._in_list(obj)
        for o, props in self.deps_of(obj, node):
            if o is not obj and o in inlist:
                return f"cyclic reference to {self.full_name(o)}.{props[0]}"
        return None

    def _in_list(self, obj) -> list:
        """getInListEx(true): every object that depends on obj, directly or not."""
        out, todo = [], [obj]
        while todo:
            cur = todo.pop()
            for o in self.objects.values():
                if o in out or o is obj:
                    continue
                if cur in self.object_deps(o):
                    out.append(o)
                    todo.append(o)
        return out

    def rename_object_identifiers(self, renames: dict, skip: str | None = None):
        """Document::renameObjectIdentifiers: references to the cells that moved (Sheet, old) -> (Sheet, new) in every
        other sheet's cells and every part's EXPRESSIONS."""
        if not renames:
            return
        from .spreadsheet_sheet import Sheet
        renames = {(a, _plain(b)): v for (a, b), v in renames.items()}
        for o in self.objects.values():
            if o.name == skip:
                continue
            if isinstance(o, Sheet):
                for k, cell in o.cells.data.items():
                    if cell.expression is not None and self._rename(o, cell.expression, renames):
                        o.cells.recompute_dependencies(CellAddress(*k))
                        o.cells.set_dirty(CellAddress(*k))
            else:
                for prop, text in list(o.expressions.items()):
                    try:
                        node = X.parse(text, owner=o.name, resolve_ambiguity=self.ambiguity_hook(o),
                                       names=frozenset(o.params))
                    except X.ExprError:
                        continue
                    if self._rename(o, node, renames):
                        o.expressions[prop] = X.to_text(node)
                        self.renamed_parts.add(o.name)

    def _rename(self, owner, node, renames) -> bool:
        """RenameObjectIdentifierExpressionVisitor: VariableExpression::_renameObjectIdentifier (the new path relative to
        the owner; a name that named its object keeps naming it) and RangeExpression's ends."""
        changed = False
        for n in X.walk(node):
            if isinstance(n, X.Var):
                obj, prop, rest = self._target(owner, n.path)
                if obj is None:
                    continue
                key = (obj.name, _plain(prop))
                if key not in renames:
                    continue
                new_obj_name, new_prop = renames[key]
                had_obj = n.path.obj is not None or n.path.owner_named or (len(n.path.names) >= 2 and obj is not owner)
                new_obj = self.objects.get(new_obj_name)
                p = X.VarPath(names=[new_prop] + list(rest), sub=n.path.sub, local=n.path.local)
                if new_obj is not owner:
                    p.obj, p.forced = X.Ref(name=new_obj_name, str=False), True
                if new_obj is obj and had_obj:
                    p.obj, p.forced = (n.path.obj or X.Ref(name=obj.name, str=False)), True
                n.path = p
                changed = True
            elif isinstance(n, X.Range):
                for side in ("a", "b"):
                    key = (owner.name, _plain(getattr(n, side)))
                    if key in renames:
                        setattr(n, side, renames[key][1])
                        changed = True
        return changed


def _plain(prop: str) -> str:
    a = string_to_address(prop, True)
    return a.to_string(absolute=False) if a.is_valid() else prop


SS_SPANS = 0x200


def coerce_param(name: str, old, v):
    """The value FreeCAD would set on the property from the expression's result, in the PARAMS entry's type."""
    kind = param_kind(name, old)
    if isinstance(v, X.Quantity):
        dims = tuple(v.dims)
        if kind == "Length" and dims not in (LENGTH, ONE):
            raise SpreadsheetError(f"{name} is a length, not {X.py_str(v)}")
        if kind == "Angle" and dims not in (ANGLE, ONE):
            raise SpreadsheetError(f"{name} is an angle, not {X.py_str(v)}")
        num = v.value
    elif isinstance(v, bool):
        num = 1 if v else 0
        if isinstance(old, bool):
            return v
    elif isinstance(v, (int, float)):
        num = v
    elif isinstance(v, str):
        if isinstance(old, str):
            return v
        raise SpreadsheetError(f"{name} is a number, not {v!r}")
    else:
        raise SpreadsheetError(f"{name}: {X.py_str(v)} is not a number")
    if isinstance(old, bool):
        return bool(num)
    if isinstance(old, int):
        return int(round(num))
    if isinstance(old, str):
        return X.py_str(v)
    return float(num)


# ── a part module's binding ───────────────────────────────────────────────────────────────────────────────

def bind(mod, path) -> None:
    """Give a part module (run by state._load_module) the PARAMS its EXPRESSIONS bind, from the project's sheets.
    A dependency cycle or an expression that fails is an error, as FreeCAD's recompute fails."""
    exprs = getattr(mod, "EXPRESSIONS", None)
    if not exprs:
        return
    path = Path(path)
    pdir = path.parent.parent
    doc = Document.of_project(pdir)
    part = doc.objects.get(path.stem)
    if part is None:
        return
    part.params = dict(getattr(mod, "PARAMS", {}) or {})
    part.expressions = {str(k): str(v) for k, v in dict(exprs).items()}
    failed = doc.recompute()
    if part.errors:
        raise SpreadsheetError(f"{path.stem}: " + "; ".join(f"{k} = {part.expressions.get(k)}: {v}"
                                                            for k, v in part.errors.items()))
    del failed
    params = dict(getattr(mod, "PARAMS", {}) or {})
    params.update(part.bound)
    mod.PARAMS = params

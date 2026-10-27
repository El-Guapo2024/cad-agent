# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses FreeCAD's Spreadsheet::Sheet and keeps FreeCAD's licence, the GNU Lesser General
# Public License, version 2.1 or (at your option) any later version; the text is in ../ui/LICENSE.
#
#   Derived from: src/Mod/Spreadsheet/App/Sheet.cpp, Cell.cpp, PropertySheet.cpp (Copyright (c) 2015 Eivind Kvedalen),
#                 src/Mod/Spreadsheet/App/SheetPyImp.cpp (Copyright (c) 2015 Eivind Kvedalen),
#                 src/Mod/Spreadsheet/Gui/SheetModel.cpp (Copyright (c) 2015 Eivind Kvedalen),
#                 src/App/Expression.cpp (Copyright (c) 2015 Eivind Kvedalen): RangeExpression and VariableExpression's
#                 _moveCells and _offsetCells
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
"""FreeCAD's Spreadsheet::Sheet: its cells (Cell.cpp), their store and dependencies (PropertySheet.cpp), the sheet's
computed properties and recompute (Sheet.cpp), SheetPy's methods by their Python names, and what the sheet's view shows
of a cell (SheetModel::data).

A cell's expression is a tree of cad_agent/fcexpr.py (src/expr.ts's, run in V8); the sheet evaluates it with itself
as the owner: its properties are its cells' computed values, by address and by alias, as Sheet::getPropertyByName finds
them, and other objects of the document (other sheets, the parts' parameters) come from the Document it belongs to
(spreadsheet_doc.py).
"""
from __future__ import annotations

import csv
import math
from collections import deque

from . import fcexpr as X
from .spreadsheet import (ALIGNMENT_BOTTOM, ALIGNMENT_HCENTER, ALIGNMENT_HIMPLIED, ALIGNMENT_HORIZONTAL, ALIGNMENT_LEFT,
                          ALIGNMENT_RIGHT, ALIGNMENT_TOP, ALIGNMENT_VCENTER, ALIGNMENT_VERTICAL, ALIGNMENT_VIMPLIED,
                          BLACK, DEFAULT_ALIGNMENT, DEFAULT_HEIGHT, DEFAULT_WIDTH, MAX_COLUMNS, MAX_ROWS, WHITE,
                          CellAddress, Range, SpreadsheetError, color, column_name, decode_alignment, decode_color,
                          decode_column, decode_style, encode_alignment, encode_color, encode_style,
                          is_valid_cell_address_name, string_to_address)

# Cell::used's bits
EXPRESSION_SET = 1
ALIGNMENT_SET = 4
STYLE_SET = 8
BACKGROUND_COLOR_SET = 0x10
FOREGROUND_COLOR_SET = 0x20
DISPLAY_UNIT_SET = 0x40
COMPUTED_UNIT_SET = 0x80
ALIAS_SET = 0x100
SPANS_SET = 0x200
MARK_SET = 0x40000000
EXCEPTION_SET = 0x20000000
PARSE_EXCEPTION_SET = 0x80000000
RESOLVE_EXCEPTION_SET = 0x01000000
ONE = (0, 0, 0, 0, 0, 0, 0, 0)


class DisplayUnit:
    """Spreadsheet::DisplayUnit: the text, its unit and scaler (0 when empty)."""
    __slots__ = ("string_rep", "unit", "scaler")

    def __init__(self, string_rep: str = "", unit=ONE, scaler: float = 0.0):
        self.string_rep, self.unit, self.scaler = string_rep, tuple(unit), scaler

    def __eq__(self, o):
        return isinstance(o, DisplayUnit) and (o.string_rep, o.unit, o.scaler) == (self.string_rep, self.unit, self.scaler)

    def is_empty(self) -> bool:
        return not self.string_rep


def parse_display_unit(text: str) -> DisplayUnit:
    """Cell::setDisplayUnit: ExpressionParser::parseUnit, or "Invalid unit"."""
    if not text:
        return DisplayUnit()
    try:
        dims, scaler = X.parse_unit(text)
    except X.ExprError as e:
        raise SpreadsheetError(e.message) from None
    return DisplayUnit(text, dims, scaler)


# ── C's strtod, as Cell::setContent reads a number ────────────────────────────────────────────────────────────

_DBL_MIN = 2.2250738585072014e-308


def c_strtod(s: str):
    """(value, end, erange): what strtod reads from the start of s (glibc: blanks, a sign, inf/nan, hex, decimal)."""
    i, n = 0, len(s)
    while i < n and s[i] in " \t\n\v\f\r":
        i += 1
    start = i
    sign = 1.0
    if i < n and s[i] in "+-":
        sign = -1.0 if s[i] == "-" else 1.0
        i += 1
    low = s[i:].lower()
    if low.startswith("infinity"):
        return sign * math.inf, i + 8, False
    if low.startswith("inf"):
        return sign * math.inf, i + 3, False
    if low.startswith("nan"):
        j = i + 3
        if j < n and s[j] == "(":
            k = j + 1
            while k < n and (s[k].isalnum() or s[k] == "_") and s[k].isascii():
                k += 1
            if k < n and s[k] == ")":
                j = k + 1
        return math.copysign(math.nan, sign), j, False
    if low.startswith("0x"):
        j = i + 2
        digits = ""
        while j < n and s[j] in "0123456789abcdefABCDEF":
            digits += s[j]
            j += 1
        frac = ""
        if j < n and s[j] == ".":
            k = j + 1
            while k < n and s[k] in "0123456789abcdefABCDEF":
                frac += s[k]
                k += 1
            if digits or frac:
                j = k
        if not digits and not frac:
            return 0.0, i + 1, False             # "0x" without digits: the 0 is read
        exp = ""
        if j < n and s[j] in "pP":
            k = j + 1
            if k < n and s[k] in "+-":
                k += 1
            if k < n and s[k].isdigit() and s[k].isascii():
                while k < n and s[k].isdigit() and s[k].isascii():
                    k += 1
                exp = s[j:k]
                j = k
        text = "0x" + (digits or "0") + ("." + frac if frac else "") + (exp or "p0")
        try:
            v = float.fromhex(text)
        except OverflowError:
            return sign * math.inf, j, True
        return sign * v, j, (v == 0 and any(c != "0" for c in digits + frac)) or (0 < v < _DBL_MIN)
    j = i
    while j < n and s[j].isascii() and s[j].isdigit():
        j += 1
    intpart = s[i:j]
    frac = ""
    if j < n and s[j] == ".":
        k = j + 1
        while k < n and s[k].isascii() and s[k].isdigit():
            k += 1
        frac = s[j + 1:k]
        if intpart or frac:
            j = k
    if not intpart and not frac:
        return 0.0, 0, False
    if j < n and s[j] in "eE":
        k = j + 1
        if k < n and s[k] in "+-":
            k += 1
        if k < n and s[k].isascii() and s[k].isdigit():
            while k < n and s[k].isascii() and s[k].isdigit():
                k += 1
            j = k
    text = s[start:j]
    v = float(text)
    mant = (intpart + frac).strip("0")
    erange = (math.isinf(v)) or (v == 0 and bool(mant)) or (0 < abs(v) < _DBL_MIN)
    return v, j, erange


# ── Cell (Cell.cpp) ───────────────────────────────────────────────────────────────────────────────────────

class Cell:
    """Spreadsheet::Cell."""

    def __init__(self, address: CellAddress, owner: "PropertySheet"):
        self.address = CellAddress(address.row, address.col)
        self.owner = owner
        self.used = 0
        self.expression = None          # an fcexpr tree
        self.alignment = DEFAULT_ALIGNMENT
        self.style: set = set()
        self.foreground = BLACK
        self.background = WHITE
        self.display_unit = DisplayUnit()
        self.alias = ""
        self.computed_unit = ONE
        self.row_span = 1
        self.col_span = 1
        self.exception = ""

    # used flags
    def set_used(self, mask, state=True):
        self.used = (self.used | mask) if state else (self.used & ~mask)

    def is_used(self, mask=None) -> bool:
        if mask is None:
            return self.used != 0
        return (self.used & mask) == mask

    def has_exception(self) -> bool:
        return self.is_used(EXCEPTION_SET) or self.is_used(PARSE_EXCEPTION_SET) or self.is_used(RESOLVE_EXCEPTION_SET)

    def set_dirty(self):
        self.owner.set_dirty(self.address)

    # content
    def set_expression(self, expr):
        self.owner.set_dirty(self.address)
        self.owner.remove_dependencies(self.address)
        self.expression = expr
        self.set_used(EXPRESSION_SET, expr is not None)
        self.owner.add_dependencies(self.address)

    def string_content(self, persistent: bool = False) -> str | None:
        """Cell::getStringContent: None when there is no expression."""
        e = self.expression
        if e is None:
            return None
        if isinstance(e, X.Var) and e.comps:
            return "=" + X.to_text(e)
        if isinstance(e, X.Str):
            return "'" + e.s
        if isinstance(e, X.Const):
            return "=" + X.to_text(e)
        if isinstance(e, X.Num):
            return X.to_text(e)
        return "=" + X.to_text(e)

    def set_content(self, value: str | None, restoring: bool = False):
        """Cell::setContent."""
        self.clear_exception()
        sheet = self.owner.sheet
        new = None
        if value is not None:
            if restoring:
                if value == "" or value == "'":
                    return
                self.expression = X.Str(s=value)
                self.set_used(EXPRESSION_SET, True)
                return
            if value.startswith("="):
                try:
                    new = sheet.parse(value[1:])
                except X.ExprError as e:
                    new = X.Str(s=value)
                    self.set_parse_exception(e.message)
            elif value.startswith("'"):
                if value == "'":
                    value = None
                else:
                    new = X.Str(s=value[1:])
            elif value != "":
                fv, end, erange = c_strtod(value)
                if not erange:
                    rest = value[end:]
                    if end > 0 and all(c in " \t\n\r" for c in rest):
                        new = X.Num(v=fv)
                if new is None and end > 0:
                    try:
                        parsed = sheet.parse(value)
                        if isinstance(parsed, X.Op) and parsed.op == "unit":
                            if isinstance(parsed.l, X.Num) and not isinstance(parsed.l, X.Const) and isinstance(parsed.r, X.UnitNode):
                                new = parsed
                        elif isinstance(parsed, X.Op) and parsed.op == "/":
                            num_nom = _is_number(parsed.l)
                            num_den = _is_number(parsed.r)
                            q_nom = isinstance(parsed.l, X.Op) and parsed.l.op == "unit"
                            q_den = isinstance(parsed.r, X.Op) and parsed.r.op == "unit"
                            u_den = isinstance(parsed.r, X.UnitNode) or (isinstance(parsed.r, X.Op) and _is_unit_op(parsed.r))
                            if (num_nom or q_nom) and (num_den or q_den or u_den):
                                new = parsed
                        elif _is_number(parsed):
                            new = parsed
                    except X.ExprError:
                        pass
            if new is None and value:
                new = X.Str(s=value)
        self.set_expression(new)

    def after_restore(self):
        """Cell::afterRestore: a content read while restoring is set again."""
        if isinstance(self.expression, X.Str):
            self.set_content(self.expression.s)

    # look
    def set_alignment(self, alignment: int):
        if alignment != self.alignment:
            self.alignment = alignment
            self.set_used(ALIGNMENT_SET, alignment != DEFAULT_ALIGNMENT)
            self.set_dirty()

    def set_style(self, style: set):
        if set(style) != self.style:
            self.style = set(style)
            self.set_used(STYLE_SET, bool(self.style))
            self.set_dirty()

    def set_foreground(self, c, range_mode=False):
        if range_mode:                       # Cell::_setForeground
            if c != self.foreground:
                self.foreground = c
                self.set_used(FOREGROUND_COLOR_SET, c != BLACK)
                self.set_dirty()
            return
        if not self.is_used(FOREGROUND_COLOR_SET) or c != self.foreground:
            self.foreground = c
            self.set_used(FOREGROUND_COLOR_SET)
            self.set_dirty()

    def clear_foreground(self):
        self.set_used(FOREGROUND_COLOR_SET, False)

    def set_background(self, c, range_mode=False):
        if range_mode:                       # Cell::_setBackground compares with transparent white
            if c != self.background:
                self.background = c
                self.set_used(BACKGROUND_COLOR_SET, c != color(1, 1, 1, 0))
                self.set_dirty()
            return
        if not self.is_used(BACKGROUND_COLOR_SET) or c != self.background:
            self.background = c
            self.set_used(BACKGROUND_COLOR_SET)
            self.set_dirty()

    def clear_background(self):
        self.set_used(BACKGROUND_COLOR_SET, False)

    def set_display_unit(self, text: str):
        du = parse_display_unit(text)
        if du != self.display_unit:
            self.display_unit = du
            self.set_used(DISPLAY_UNIT_SET, not du.is_empty())
            self.set_dirty()

    def set_alias(self, n: str):
        """Cell::setAlias (the owner's maps kept in step)."""
        if self.alias != n:
            o = self.owner
            o.rev_alias.pop(self.alias, None)
            if n:
                o.alias_of[self.address.key] = n
                o.rev_alias[n] = self.address.key
            else:
                o.alias_of.pop(self.address.key, None)
            self.alias = n
            self.set_used(ALIAS_SET, bool(n))
            self.set_dirty()

    def set_computed_unit(self, unit, range_mode=False):
        self.computed_unit = tuple(unit)
        self.set_used(COMPUTED_UNIT_SET, self.computed_unit != ONE)
        self.set_dirty()

    def set_spans(self, rows, cols):
        rows = 1 if rows == -1 else rows
        cols = 1 if cols == -1 else cols
        if rows != self.row_span or cols != self.col_span:
            self.row_span, self.col_span = rows, cols
            self.set_used(SPANS_SET, rows != 1 or cols != 1)
            self.set_dirty()

    def spans(self):
        return self.row_span, self.col_span

    # exceptions
    def set_exception(self, e: str, silent=False):
        self.exception = e
        self.set_used(EXCEPTION_SET)

    def set_parse_exception(self, e: str):
        self.exception = e
        self.set_used(PARSE_EXCEPTION_SET)

    def set_resolve_exception(self, e: str):
        self.exception = e
        self.set_used(RESOLVE_EXCEPTION_SET)

    def clear_resolve_exception(self):
        self.set_used(RESOLVE_EXCEPTION_SET, False)

    def clear_exception(self):
        self.exception = ""
        self.set_used(EXCEPTION_SET, False)
        self.set_used(RESOLVE_EXCEPTION_SET, False)
        self.set_used(PARSE_EXCEPTION_SET, False)

    # the file
    def attrs(self) -> dict:
        """Cell::save's attributes, as the part file's keywords."""
        out = {}
        if self.is_used(ALIGNMENT_SET):
            out["alignment"] = encode_alignment(self.alignment)
        if self.is_used(STYLE_SET):
            out["style"] = encode_style(self.style)
        if self.is_used(FOREGROUND_COLOR_SET):
            out["foreground_color"] = encode_color(self.foreground)
        if self.is_used(BACKGROUND_COLOR_SET):
            out["background_color"] = encode_color(self.background)
        if self.is_used(DISPLAY_UNIT_SET):
            out["display_unit"] = self.display_unit.string_rep
        if self.is_used(ALIAS_SET):
            out["alias"] = self.alias
        if self.is_used(SPANS_SET):
            out["row_span"] = self.row_span
            out["col_span"] = self.col_span
        return out

    def saved(self) -> bool:
        """Cell::save writes a cell whose `used` is not 0."""
        return self.is_used()

    def restore(self, attrs: dict, check_alias=False):
        """Cell::restore from the file's attributes (the content first, as the reader does)."""
        if "content" in attrs:
            self.set_content(attrs["content"] or "", restoring=self.owner.restoring)
        if attrs.get("style") is not None:
            self.set_style(decode_style(attrs["style"]))
        if attrs.get("alignment") is not None:
            a = 0
            for item in attrs["alignment"].split("|"):
                a = decode_alignment(item, a)
            self.set_alignment(a)
        if attrs.get("foreground_color") is not None:
            self.set_foreground(decode_color(attrs["foreground_color"], BLACK))
        if attrs.get("background_color") is not None:
            self.set_background(decode_color(attrs["background_color"], WHITE))
        if attrs.get("display_unit") is not None:
            self.set_display_unit(attrs["display_unit"])
        alias = attrs.get("alias")
        if alias and (not check_alias or alias not in self.owner.rev_alias):
            self.set_alias(alias)
        rs, cs = attrs.get("row_span"), attrs.get("col_span")
        if rs is not None or cs is not None:
            self.set_spans(int(rs) if rs is not None else 1, int(cs) if cs is not None else 1)


def _is_number(n) -> bool:
    return isinstance(n, X.Num)


def _is_unit_op(n) -> bool:
    """A UnitExpression the parser built from units alone (mm/s, m^2): an operator tree over units."""
    if isinstance(n, X.UnitNode):
        return True
    return isinstance(n, X.Op) and n.op in ("*", "/", "^") and _is_unit_op(n.l) and (
        n.op == "^" or _is_unit_op(n.r))


# ── PropertySheet (PropertySheet.cpp) ─────────────────────────────────────────────────────────────────────

class PropertySheet:
    def __init__(self, sheet: "Sheet"):
        self.sheet = sheet
        self.data: dict = {}               # (row, col) -> Cell
        self.merged: dict = {}             # (row, col) -> anchor (row, col)
        self.alias_of: dict = {}           # aliasProp
        self.rev_alias: dict = {}          # revAliasProp
        self.prop_to_cells: dict = {}      # propertyNameToCellMap
        self.cell_to_props: dict = {}      # cellToPropertyNameMap
        self.obj_to_cells: dict = {}       # documentObjectToCellMap
        self.cell_to_objs: dict = {}
        self.dirty: set = set()
        self.restoring = False

    def get(self, addr: CellAddress):
        return self.data.get(addr.key)

    def value_from_alias(self, alias: str):
        k = self.rev_alias.get(alias)
        return self.data.get(k) if k is not None else None

    def is_valid_alias(self, candidate: str) -> bool:
        """PropertySheet::isValidAlias."""
        import re
        if not re.fullmatch(r"[A-Za-z][_A-Za-z0-9]*", candidate or ""):
            return False
        if self.value_from_alias(candidate):
            return False
        if is_valid_cell_address_name(candidate):
            return False
        if X.is_token_a_unit(candidate) or X.is_token_a_constant(candidate):
            return False
        return True

    def used_cells(self):
        return [CellAddress(*k) for k in sorted(self.data) if self.data[k].is_used()]

    def non_empty_cells(self):
        return [CellAddress(*k) for k in sorted(self.data)
                if self.data[k].is_used() and self.data[k].string_content() not in (None, "")]

    @staticmethod
    def _extract_range(cells):
        if not cells:
            return CellAddress(), CellAddress()
        return (CellAddress(min(c.row for c in cells), min(c.col for c in cells)),
                CellAddress(max(c.row for c in cells), max(c.col for c in cells)))

    def used_range(self):
        return self._extract_range(self.used_cells())

    def non_empty_range(self):
        return self._extract_range(self.non_empty_cells())

    def set_dirty(self, addr: CellAddress):
        k = self.merged.get(addr.key, addr.key)
        self.dirty.add(k)

    def clear_dirty(self, addr: CellAddress):
        self.dirty.discard(addr.key)

    def create_cell(self, addr: CellAddress) -> Cell:
        c = Cell(addr, self)
        self.data[addr.key] = c
        return c

    def cell_at(self, addr: CellAddress):
        j = self.merged.get(addr.key)
        if j is not None:
            return self.data.get(j)
        return self.data.get(addr.key)

    def non_null_cell_at(self, addr: CellAddress) -> Cell:
        j = self.merged.get(addr.key)
        if j is not None:
            c = self.data.get(j)
            return c if c is not None else self.create_cell(addr)
        c = self.data.get(addr.key)
        return c if c is not None else self.create_cell(addr)

    def set_content(self, addr, value):
        self.non_null_cell_at(addr).set_content(value)

    def set_alignment(self, addr, alignment):
        c = self.non_null_cell_at(addr)
        if c.address != addr:              # merged: only the anchor
            return
        c.set_alignment(alignment)

    def set_alignment_range(self, rng: Range, alignment):
        for a in rng:
            c = self.non_null_cell_at(a)
            if c.address == a:
                c.set_alignment(alignment)

    def set_alias(self, addr: CellAddress, alias: str):
        """PropertySheet::setAlias."""
        if alias and not self.is_valid_alias(alias):
            raise SpreadsheetError("Invalid alias")
        aliased = self.value_from_alias(alias)
        cell = self.non_null_cell_at(addr)
        if aliased is cell:
            return
        if aliased is not None:
            raise SpreadsheetError("Alias already defined.")
        full = self.sheet.full_name() + "." + addr.to_string()
        for k in sorted(self.prop_to_cells.get(full, ())):
            self.set_dirty(CellAddress(*k))
        old = cell.alias
        cell.set_alias(alias)
        if old:
            self.sheet.document.rename_object_identifiers(
                {(self.sheet.name, old): (self.sheet.name, alias or addr.to_string())})

    def clear_alias(self, addr: CellAddress):
        a = self.alias_of.pop(addr.key, None)
        if a is not None:
            self.rev_alias.pop(a, None)

    def clear(self, addr: CellAddress, to_clear_alias=True):
        if addr.key not in self.data:
            return
        self.split_cell(addr)
        self.remove_dependencies(addr)
        del self.data[addr.key]
        self.dirty.add(addr.key)
        if to_clear_alias:
            self.clear_alias(addr)

    def move_alias(self, cur: CellAddress, new: CellAddress):
        a = self.alias_of.get(cur.key)
        if a is not None:
            self.alias_of[new.key] = a
            self.rev_alias[a] = new.key
            del self.alias_of[cur.key]

    def move_cell(self, cur: CellAddress, new: CellAddress, renames: dict):
        if new.key in self.data:
            self.clear(new, False)
        cell = self.data.get(cur.key)
        if cell is not None:
            rows, cols = cell.spans()
            has_span = cell.is_used(SPANS_SET)
            self.split_cell(cur)
            self.remove_dependencies(cur)
            del self.data[cur.key]
            self.set_dirty(cur)
            cell.address = CellAddress(new.row, new.col)
            self.data[new.key] = cell
            if has_span:
                self.merge_cells(new, CellAddress(new.row + rows - 1, new.col + cols - 1))
            self.add_dependencies(new)
            self.set_dirty(new)
            renames[(self.sheet.name, cur.to_string())] = (self.sheet.name, new.to_string())

    def _visit_cells(self, keys, visit):
        """Run an expression visitor over each cell; when it changed the tree, the cell is dirty and its dependencies
        are recomputed (insertRows' loop)."""
        for k in keys:
            cell = self.data.get(k)
            if cell is None or cell.expression is None:
                continue
            if visit(cell.expression):
                self.set_dirty(CellAddress(*k))
                self.recompute_dependencies(CellAddress(*k))

    def insert_rows(self, row: int, count: int):
        keys = sorted(self.data, key=lambda k: k[0])          # std::sort by row (not stable: ties by insertion)
        keys = _sort_like_std(list(self.data), lambda k: k[0])
        renames = {}
        for k in reversed(keys):
            if k[0] >= row:
                self.move_alias(CellAddress(*k), CellAddress(k[0] + count, k[1]))
        mv = _MoveCells(CellAddress(row, MAX_COLUMNS), count, 0)
        for k in reversed(keys):
            cell = self.data.get(k)
            if cell is not None and cell.expression is not None and mv.visit(cell.expression):
                self.set_dirty(CellAddress(*k))
                self.recompute_dependencies(CellAddress(*k))
            if k[0] >= row:
                self.move_cell(CellAddress(*k), CellAddress(k[0] + count, k[1]), renames)
        self.sheet.document.rename_object_identifiers(renames, skip=self.sheet.name)

    def remove_rows(self, row: int, count: int):
        keys = _sort_like_std(list(self.data), lambda k: k[0])
        renames = {}
        for k in keys:
            if row <= k[0] < row + count:
                self.clear_alias(CellAddress(*k))
            elif k[0] >= row + count:
                self.move_alias(CellAddress(*k), CellAddress(k[0] - count, k[1]))
        mv = _MoveCells(CellAddress(row + count - 1, MAX_COLUMNS), -count, 0)
        for k in keys:
            cell = self.data.get(k)
            if cell is None:
                continue
            if cell.expression is not None and mv.visit(cell.expression):
                self.set_dirty(CellAddress(*k))
                self.recompute_dependencies(CellAddress(*k))
            if row <= k[0] < row + count:
                self.clear(CellAddress(*k), False)
            elif k[0] >= row + count:
                self.move_cell(CellAddress(*k), CellAddress(k[0] - count, k[1]), renames)
            elif cell.is_used(SPANS_SET) and k[0] + cell.row_span >= row:
                sr, sc = cell.spans()
                sr = sr - count if k[0] + sr >= row + count else k[0] - row
                self.merge_cells(CellAddress(*k), CellAddress(k[0] + sr - 1, k[1] + sc - 1))
        self.sheet.document.rename_object_identifiers(renames, skip=self.sheet.name)

    def insert_columns(self, col: int, count: int):
        keys = sorted(self.data)
        renames = {}
        for k in reversed(keys):
            if k[1] >= col:
                self.move_alias(CellAddress(*k), CellAddress(k[0], k[1] + count))
        mv = _MoveCells(CellAddress(MAX_ROWS, col), 0, count)
        for k in reversed(keys):
            cell = self.data.get(k)
            if cell is not None and cell.expression is not None and mv.visit(cell.expression):
                self.set_dirty(CellAddress(*k))
                self.recompute_dependencies(CellAddress(*k))
            if k[1] >= col:
                self.move_cell(CellAddress(*k), CellAddress(k[0], k[1] + count), renames)
        self.sheet.document.rename_object_identifiers(renames, skip=self.sheet.name)

    def remove_columns(self, col: int, count: int):
        keys = _sort_like_std(list(self.data), lambda k: k[1])
        renames = {}
        for k in keys:
            if col <= k[1] < col + count:
                self.clear_alias(CellAddress(*k))
            elif k[1] >= col + count:
                self.move_alias(CellAddress(*k), CellAddress(k[0], k[1] - count))
        mv = _MoveCells(CellAddress(MAX_ROWS, col + count - 1), 0, -count)
        for k in keys:
            cell = self.data.get(k)
            if cell is None:
                continue
            if cell.expression is not None and mv.visit(cell.expression):
                self.set_dirty(CellAddress(*k))
                self.recompute_dependencies(CellAddress(*k))
            if col <= k[1] < col + count:
                self.clear(CellAddress(*k), False)
            elif k[1] >= col + count:
                self.move_cell(CellAddress(*k), CellAddress(k[0], k[1] - count), renames)
            elif cell.is_used(SPANS_SET) and k[1] + cell.col_span >= col:
                sr, sc = cell.spans()
                sc = sc - count if k[1] + sc >= col + count else k[1] - col
                self.merge_cells(CellAddress(*k), CellAddress(k[0] + sr - 1, k[1] + sc - 1))
        self.sheet.document.rename_object_identifiers(renames, skip=self.sheet.name)

    def merge_cells(self, frm: CellAddress, to: CellAddress) -> bool:
        if frm == to:
            self.split_cell(frm)
            return True
        it = self.merged.get(frm.key)
        if it is not None:
            r, c = self.cell_at(CellAddress(*it)).spans()
            if to.row - frm.row + 1 == r and to.col - frm.col + 1 == c:
                return False
        for r in range(frm.row, to.row + 1):
            for c in range(frm.col, to.col + 1):
                self.split_cell(CellAddress(r, c))
        for r in range(frm.row, to.row + 1):
            for c in range(frm.col, to.col + 1):
                if not (r == frm.row and c == frm.col):
                    self.clear(CellAddress(r, c))
        for r in range(frm.row, to.row + 1):
            for c in range(frm.col, to.col + 1):
                self.merged[(r, c)] = frm.key
                self.set_dirty(CellAddress(r, c))
        self.set_spans(frm, to.row - frm.row + 1, to.col - frm.col + 1)
        return True

    def split_cell(self, addr: CellAddress):
        anchor = self.merged.get(addr.key)
        if anchor is None:
            return
        rows, cols = self.cell_at(CellAddress(*anchor)).spans()
        for r in range(anchor[0], anchor[0] + rows):
            for c in range(anchor[1], anchor[1] + cols):
                self.set_dirty(CellAddress(r, c))
                self.merged.pop((r, c), None)
        self.set_spans(CellAddress(*anchor), -1, -1)

    def set_spans(self, addr, rows, cols):
        self.non_null_cell_at(addr).set_spans(rows, cols)

    def get_spans(self, addr: CellAddress):
        anchor = self.merged.get(addr.key)
        if anchor is not None and anchor == addr.key:
            return self.cell_at(CellAddress(*anchor)).spans()
        return 1, 1

    def anchor(self, addr: CellAddress) -> CellAddress:
        a = self.merged.get(addr.key)
        return CellAddress(*a) if a is not None else addr

    def is_merged(self, addr) -> bool:
        return addr.key in self.merged

    def is_hidden(self, addr) -> bool:
        a = self.merged.get(addr.key)
        return a is not None and a != addr.key

    def has_span(self) -> bool:
        return bool(self.merged)

    # dependencies
    def add_dependencies(self, key: CellAddress):
        """PropertySheet::addDependencies."""
        cell = self.data.get(key.key)
        if cell is None:
            return
        cell.clear_resolve_exception()
        expr = cell.expression
        if expr is None:
            return
        doc = self.sheet.document
        for obj, names in self.sheet.deps_of(expr):
            obj_name = doc.full_name(obj)
            self.obj_to_cells.setdefault(obj_name, set()).add(key.key)
            self.cell_to_objs.setdefault(key.key, set()).add(obj_name)
            for name in names:
                prop = name
                addr = string_to_address(prop, True)
                if addr.is_valid():
                    prop = addr.to_string(absolute=False)
                full = obj_name + "." + prop
                self.prop_to_cells.setdefault(full, set()).add(key.key)
                self.cell_to_props.setdefault(key.key, set()).add(full)
                other = doc.sheet_object(obj)
                if prop and other is not None:
                    j = other.cells.rev_alias.get(prop)
                    if j is not None:
                        full = obj_name + "." + CellAddress(*j).to_string()
                        self.prop_to_cells.setdefault(full, set()).add(key.key)
                        self.cell_to_props.setdefault(key.key, set()).add(full)

    def remove_dependencies(self, key: CellAddress):
        props = self.cell_to_props.pop(key.key, None)
        if props:
            for p in props:
                s = self.prop_to_cells.get(p)
                if s is not None:
                    s.discard(key.key)
        objs = self.cell_to_objs.pop(key.key, None)
        if objs:
            for o in objs:
                s = self.obj_to_cells.get(o)
                if s is not None:
                    s.discard(key.key)
                    if not s:
                        del self.obj_to_cells[o]

    def recompute_dependencies(self, key: CellAddress):
        self.remove_dependencies(key)
        self.add_dependencies(key)

    def deps_of_name(self, name: str) -> set:
        """getDeps(name): the cells that read the property `name` (full name)."""
        return self.prop_to_cells.get(name, set())

    def after_restore(self):
        """PropertySheet::afterRestore: each content read while restoring is set again."""
        self.restoring = False
        for k in sorted(self.data):
            self.data[k].after_restore()


def _sort_like_std(keys, keyfn):
    """std::sort with a comparator on one coordinate: introsort is not stable, but on the few dozen cells of a sheet
    (insertion sort below 16 elements, and the map's keys come in row-major order) it keeps equal keys in order."""
    return sorted(keys, key=keyfn)


# ── the expression visitors of the row and column moves (Expression.cpp) ───────────────────────────────────

class _MoveCells:
    """MoveCellsExpressionVisitor: VariableExpression::_moveCells and RangeExpression::_moveCells."""

    def __init__(self, address: CellAddress, row_count: int, col_count: int):
        self.address, self.rows, self.cols = address, row_count, col_count

    def visit(self, node) -> bool:
        changed = False
        for n in X.walk(node):
            if isinstance(n, X.Var):
                if n.path.obj is not None or n.path.doc is not None or not n.path.names:
                    continue
                addr = string_to_address(n.path.names[0], True)
                if not addr.is_valid():
                    continue
                if addr.row >= self.address.row or addr.col >= self.address.col:
                    addr.row += self.rows
                    addr.col += self.cols
                    n.path.names[0] = addr.to_string()
                    changed = True
            elif isinstance(n, X.Range):
                for side in ("a", "b"):
                    addr = string_to_address(getattr(n, side), True)
                    if addr.is_valid() and (addr.row >= self.address.row or addr.col >= self.address.col):
                        addr.row += self.rows
                        addr.col += self.cols
                        setattr(n, side, addr.to_string())
                        changed = True
        return changed


class _OffsetCells:
    """OffsetCellsExpressionVisitor: relative references shifted by a paste's offset ($ parts stay)."""

    def __init__(self, row_offset: int, col_offset: int):
        self.dr, self.dc = row_offset, col_offset

    def visit(self, node) -> bool:
        changed = False
        for n in X.walk(node):
            if isinstance(n, X.Var):
                if n.path.obj is not None or n.path.doc is not None or not n.path.names:
                    continue
                addr = string_to_address(n.path.names[0], True)
                if not addr.is_valid() or (addr.abs_col and addr.abs_row):
                    continue
                if not addr.abs_col:
                    addr.col += self.dc
                if not addr.abs_row:
                    addr.row += self.dr
                if addr.is_valid():
                    n.path.names[0] = addr.to_string()
                    changed = True
            elif isinstance(n, X.Range):
                for side in ("a", "b"):
                    addr = string_to_address(getattr(n, side), True)
                    if addr.is_valid() and (not addr.abs_row or not addr.abs_col):
                        if not addr.abs_row:
                            addr.row += self.dr
                        if not addr.abs_col:
                            addr.col += self.dc
                        setattr(n, side, addr.to_string())
                        changed = True
        return changed


# ── Sheet (Sheet.cpp) ───────────────────────────────────────────────────────────────────────────────────

class Prop:
    """A cell's computed property: kind is 'int' (PropertyInteger), 'float' (PropertyFloat), 'quantity'
    (PropertySpreadsheetQuantity), 'string' (PropertyString) or 'object' (PropertyPythonObject)."""
    __slots__ = ("kind", "value")

    def __init__(self, kind, value):
        self.kind, self.value = kind, value

    def py(self):
        """getPyObject: the Python value an expression reads."""
        return self.value

    def __repr__(self):
        return f"Prop({self.kind}, {self.value!r})"


class Sheet:
    """Spreadsheet::Sheet. `document` is the spreadsheet_doc.Document it belongs to."""

    def __init__(self, name: str, document, label: str | None = None):
        self.name = name
        self.label = label or name
        self.document = document
        self.cells = PropertySheet(self)
        self.props: dict = {}              # "A1" -> Prop
        self.cell_errors: set = set()
        self.column_widths: dict = {}      # col -> width
        self.row_heights: dict = {}        # row -> height
        self.current = None                # (row, col) while a cell is evaluated: CurrentAddressLock
        self.touched = False
        self.copy_cut = ([], True)

    def full_name(self) -> str:
        return f"{self.document.name}#{self.name}"

    # parsing: the expression with this sheet as its owner
    def parse(self, text: str):
        return X.parse(text, owner=self.name, resolve_ambiguity=self.document.ambiguity_hook(self))

    def deps_of(self, expr):
        """(object, [property names]) per identifier of the expression: ObjectIdentifier::getDep."""
        return self.document.deps_of(self, expr)

    # properties
    def get_property(self, name: str):
        """Sheet::getPropertyByName: a cell by alias or address, then the object's own (Label)."""
        addr = self.cells.value_from_alias(name)
        a = addr.address if addr is not None else string_to_address(name, True)
        if a.is_valid():
            p = self.props.get(a.to_string(absolute=False))
            if p is not None:
                return p
        if name == "Label":
            return Prop("string", self.label)
        if name == "Label2":
            return Prop("string", "")
        return None

    def cell_address(self, name: str, silent=True) -> CellAddress:
        c = self.cells.value_from_alias(name)
        if c is not None:
            return c.address
        return string_to_address(name, silent)

    def range_of(self, text: str) -> Range:
        return Range(text)

    # setting computed properties (Sheet::set*Property)
    def _set_prop(self, key: CellAddress, kind, value):
        name = key.to_string(absolute=False)
        old = self.props.get(name)
        self.props[name] = Prop(kind, value)
        if old is None or old.kind != kind or not _same_value(old.value, value):
            self.document.changed(self, name)

    def update_property(self, key: CellAddress):
        """Sheet::updateProperty."""
        cell = self.cells.get(key)
        if cell is not None:
            inp = cell.expression
            if inp is not None:
                self.current = key.key
                try:
                    out = self.document.eval_cell(self, inp)
                finally:
                    self.current = None
            else:
                s = cell.string_content()
                if s:
                    out = s
                else:
                    self.props.pop(key.to_string(absolute=False), None)
                    return
                self._set_prop(key, "string", out)
                return
            kind, value = classify(out)
            if kind == "quantity":
                self.cells.non_null_cell_at(key).set_computed_unit(value.dims)
            self._set_prop(key, kind, value)
        else:
            self.clear(key)

    def recompute_cell(self, p: CellAddress):
        """Sheet::recomputeCell."""
        cell = self.cells.get(p)
        try:
            if cell is not None and cell.has_exception():
                content = cell.string_content() or ""
                cell.set_content(content)
            self.update_property(p)
            if cell is None or not cell.has_exception():
                self.cells.clear_dirty(p)
                self.cell_errors.discard(p.key)
        except (X.ExprError, SpreadsheetError) as e:
            msg = e.message if isinstance(e, X.ExprError) else str(e)
            self._set_prop(p, "string", "ERR: " + msg)
            if cell is not None:
                cell.set_exception(msg)
            self.cell_errors.add(p.key)

    def provides_to(self, addr_key) -> list:
        """The cells reading this one (getDeps(fullName.A1)), in CellAddress order."""
        return sorted(self.cells.deps_of_name(self.full_name() + "." + CellAddress(*addr_key).to_string()))

    def execute(self) -> str | None:
        """Sheet::execute: the dirty cells, those that read them, recomputed in dependency order. Returns FreeCAD's
        recompute message when a cell failed, else None."""
        dirty = set(self.cells.dirty)
        for e in sorted(self.cell_errors):
            self.cells.recompute_dependencies(CellAddress(*e))
            dirty.add(e)
        order, ok, vertices = _topological(sorted(dirty), dirty, self.provides_to)
        if ok:
            for k in order:
                self.recompute_cell(CellAddress(*k))
        else:
            for k in sorted(vertices):
                cell = self.cells.get(CellAddress(*k))
                if cell is not None:
                    self.cell_errors.add(k)
                    cell.set_exception("Pending computation due to cyclic dependency", True)
            remaining = set(dirty)
            while remaining:
                cur = min(remaining)
                remaining.discard(cur)
                verts, edges = [], {}
                index = {}
                queue = deque([cur])
                while queue:
                    pos = queue.popleft()
                    if pos not in index:
                        index[pos] = len(verts)
                        verts.append(pos)
                        edges[pos] = []
                    for dep in self.provides_to(pos):
                        if dep not in index:
                            index[dep] = len(verts)
                            verts.append(dep)
                            edges[dep] = []
                            queue.append(dep)
                            remaining.discard(dep)
                        edges[pos].append(dep)
                if _has_cycle(verts, edges):
                    lines = ["Cyclic dependency"]
                    text = "Cyclic dependency"
                    for i, v in enumerate(sorted(verts)):
                        text += ("\n" if i % 20 == 0 else ", ") + CellAddress(*v).to_string()
                    for v in sorted(verts):
                        cell = self.cells.get(CellAddress(*v))
                        if cell is not None:
                            cell.set_exception(text, True)
                    del lines
        self.touched = False
        if not self.cell_errors:
            return None
        return "One or more cells failed contains errors."

    def must_execute(self) -> bool:
        return bool(self.cell_errors) or bool(self.cells.dirty)

    # SheetPy's methods, by their Python names ──────────────────────────────────────────────────────────
    def set(self, address: str, contents: str):
        alias_addr = self.cells.value_from_alias(address)
        if alias_addr is not None:
            self.set_cell(alias_addr.address, contents)
            return
        for a in Range(address):
            self.set_cell(a, contents)

    def set_cell(self, addr: CellAddress, value: str):
        if value == "":
            self.clear(addr)
            return
        self.cells.set_content(addr, value)

    def get(self, address: str):
        p = self.get_property(address)
        if p is None:
            raise SpreadsheetError(f"Invalid cell address or property: {address}")
        return p.value

    def get_contents(self, address: str) -> str:
        c = self.cells.value_from_alias(address)
        a = c.address if c is not None else string_to_address(address)
        cell = self.cells.get(a)
        return (cell.string_content() or "") if cell is not None else ""

    def clear(self, addr, all_=True):
        if isinstance(addr, str):
            for a in Range(addr):
                self.clear(a, all_)
            return
        cell = self.cells.get(addr)
        if cell is not None:
            self.cells.clear(addr)
        self.props.pop(addr.to_string(absolute=False), None)

    def clear_all(self):
        self.cells = PropertySheet(self)
        self.props = {}
        self.cell_errors = set()
        self.column_widths = {}
        self.row_heights = {}

    def setAlias(self, address: str, alias):
        addr = string_to_address(address)
        alias = alias or ""
        existing = self.cells.rev_alias.get(alias) if alias else None
        if existing is not None:
            if existing == addr.key:
                return
            raise SpreadsheetError("Alias already defined")
        if not alias:
            self.cells.set_alias(addr, "")
        elif self.is_valid_alias(alias):
            self.cells.set_alias(addr, alias)
        else:
            if X.is_token_a_unit(alias):
                raise SpreadsheetError("Invalid alias: name conflicts with a reserved unit token")
            if X.is_token_a_constant(alias):
                raise SpreadsheetError("Invalid alias: name conflicts with a reserved constant token")
            raise SpreadsheetError("Invalid alias")

    def is_valid_alias(self, candidate: str) -> bool:
        """Sheet::isValidAlias."""
        if not self.cells.is_valid_alias(candidate):
            return False
        if self.cells.value_from_alias(candidate) is not None:
            return True
        return self.get_property(candidate) is None and candidate not in ("Label", "Label2", "ExpressionEngine",
                                                                          "Visibility", "cells", "columnWidths",
                                                                          "rowHeights")

    def getAlias(self, address: str):
        c = self.cells.get(string_to_address(address))
        return c.alias if c is not None and c.is_used(ALIAS_SET) else None

    def getCellFromAlias(self, alias: str):
        c = self.cells.value_from_alias(alias)
        return c.address.to_string() if c is not None else None

    def setStyle(self, cell: str, value, options: str = "replace"):
        style = set(value) if isinstance(value, (set, list, tuple)) else decode_style(value)
        rng = Range(cell)
        if options == "replace":
            for a in rng:
                self.cells.non_null_cell_at(a).set_style(style)
        elif options == "add":
            for a in rng:
                c = self.cells.get(a)
                new = set(style) | (c.style if c is not None else set())
                self.cells.non_null_cell_at(a).set_style(new)
        elif options == "remove":
            for a in rng:
                c = self.cells.get(a)
                old = set(c.style) if c is not None else set()
                self.cells.non_null_cell_at(a).set_style(old - style)
        elif options == "invert":
            for a in rng:
                c = self.cells.get(a)
                old = set(c.style) if c is not None else set()
                self.cells.non_null_cell_at(a).set_style(old ^ style)
        else:
            raise SpreadsheetError("Optional parameter must be either 'replace', 'add', 'remove', or 'invert'")

    def getStyle(self, address: str):
        c = self.cells.get(string_to_address(address))
        return set(c.style) if c is not None and c.is_used(STYLE_SET) else None

    def setAlignment(self, cell: str, value, options: str = "replace"):
        alignment = 0
        items = list(value) if isinstance(value, (set, list, tuple)) else [i for i in value.split("|") if i]
        for item in items:
            alignment = decode_alignment(item, alignment)
        if options == "replace":
            self.cells.set_alignment_range(Range(cell), alignment)
        elif options == "keep":
            for a in Range(cell):
                c = self.cells.get(a)
                old = c.alignment if c is not None else 0
                if alignment & ALIGNMENT_VERTICAL:
                    old &= ~ALIGNMENT_VERTICAL
                if alignment & ALIGNMENT_HORIZONTAL:
                    old &= ~ALIGNMENT_HORIZONTAL
                self.cells.set_alignment(a, alignment | old)
        else:
            raise SpreadsheetError("Optional parameter must be either 'replace' or 'keep'")

    def getAlignment(self, address: str):
        c = self.cells.get(string_to_address(address))
        if c is None or not c.is_used(ALIGNMENT_SET):
            return None
        out = set()
        for bit, name in ((ALIGNMENT_LEFT, "left"), (ALIGNMENT_HCENTER, "center"), (ALIGNMENT_RIGHT, "right"),
                          (ALIGNMENT_TOP, "top"), (ALIGNMENT_VCENTER, "vcenter"), (ALIGNMENT_BOTTOM, "bottom")):
            if c.alignment & bit:
                out.add(name)
        return out

    @staticmethod
    def _color(value):
        if not isinstance(value, (tuple, list)):
            raise SpreadsheetError("Tuple required.")
        if len(value) < 3 or len(value) > 4:
            raise SpreadsheetError("Tuple must be either of 3 or 4 floats/ints.")
        return color(*value) if len(value) == 4 else color(value[0], value[1], value[2], 1.0)

    def setForeground(self, cell: str, value):
        c = self._color(value)
        for a in Range(cell):
            self.cells.non_null_cell_at(a).set_foreground(c, range_mode=True)

    def clearForeground(self, cell: str):
        for a in Range(cell):
            self.cells.non_null_cell_at(a).clear_foreground()

    def getForeground(self, address: str):
        c = self.cells.get(string_to_address(address))
        return tuple(c.foreground) if c is not None and c.is_used(FOREGROUND_COLOR_SET) else None

    def setBackground(self, cell: str, value):
        c = self._color(value)
        for a in Range(cell):
            self.cells.non_null_cell_at(a).set_background(c, range_mode=True)

    def clearBackground(self, cell: str):
        for a in Range(cell):
            self.cells.non_null_cell_at(a).clear_background()

    def getBackground(self, address: str):
        c = self.cells.get(string_to_address(address))
        return tuple(c.background) if c is not None and c.is_used(BACKGROUND_COLOR_SET) else None

    def setDisplayUnit(self, cell: str, value: str):
        for a in Range(cell):
            self.cells.non_null_cell_at(a).set_display_unit(value)

    def getDisplayUnit(self, address: str):
        c = self.cells.get(string_to_address(address))
        return c.display_unit.string_rep if c is not None and c.is_used(DISPLAY_UNIT_SET) else None

    def mergeCells(self, rng: str):
        r = Range(rng)
        self.cells.merge_cells(r.from_(), r.to())

    def splitCell(self, address: str):
        self.cells.split_cell(string_to_address(address))

    def getSpans(self, address: str):
        return self.cells.get_spans(string_to_address(address))

    def isMergedCell(self, address: str) -> bool:
        return self.cells.is_merged(string_to_address(address))

    def insertRows(self, row: str, count: int):
        r = _decode_row_arg(row)
        self.cells.insert_rows(r, count)
        self._update_sizes(False, r, count)

    def removeRows(self, row: str, count: int):
        r = _decode_row_arg(row)
        for a in [CellAddress(*k) for k in self.cells.data if r <= k[0] < r + count]:
            pass
        self.cells.remove_rows(r, count)
        self._update_sizes(False, r, -count)
        self._drop_stale_props()

    def insertColumns(self, column: str, count: int):
        c = decode_column(column)
        self.cells.insert_columns(c, count)
        self._update_sizes(True, c, count)

    def removeColumns(self, column: str, count: int):
        c = decode_column(column)
        self.cells.remove_columns(c, count)
        self._update_sizes(True, c, -count)
        self._drop_stale_props()

    def _drop_stale_props(self):
        """The dynamic properties of cells that moved away are recomputed from their dirty marks."""

    def _update_sizes(self, horizontal: bool, section: int, count: int):
        """Sheet::updateColumnsOrRows."""
        sizes = self.column_widths if horizontal else self.row_heights
        keys = sorted(sizes)
        lower = [k for k in keys if k >= section]
        if not lower:
            return
        new = {k: sizes[k] for k in keys if k < section}
        if count > 0:
            for k in lower:
                new[k + count] = sizes[k]
        else:
            for k in [k for k in keys if k >= section - count]:
                new.setdefault(k + count, sizes[k])
        if horizontal:
            self.column_widths = new
        else:
            self.row_heights = new

    def setColumnWidth(self, column: str, width: int):
        a = string_to_address(column + "1")
        self.column_widths[a.col] = int(width)

    def column_widths_named(self) -> dict:
        return {column_name(c): w for c, w in sorted(self.column_widths.items())}

    def getColumnWidth(self, column: str) -> int:
        a = string_to_address(column + "1")
        return self.column_widths.get(a.col, DEFAULT_WIDTH)

    def setRowHeight(self, row: str, height: int):
        a = string_to_address("A" + str(row))
        self.row_heights[a.row] = int(height)

    def getRowHeight(self, row: str) -> int:
        a = string_to_address("A" + str(row))
        return self.row_heights.get(a.row, DEFAULT_HEIGHT)

    def touchCells(self, address: str, address_to: str | None = None):
        a1 = self.getCellFromAlias(address) or address
        a2 = (self.getCellFromAlias(address_to) or address_to) if address_to else a1
        for a in Range(string_to_address(a1), string_to_address(a2)):
            self.cells.set_dirty(a)

    def recomputeCells(self, address: str, address_to: str | None = None):
        a1 = self.getCellFromAlias(address) or address
        a2 = (self.getCellFromAlias(address_to) or address_to) if address_to else a1
        for a in Range(string_to_address(a1), string_to_address(a2)):
            self.recompute_cell(a)

    def getUsedCells(self):
        return [a.to_string() for a in self.cells.used_cells()]

    def getNonEmptyCells(self):
        return [a.to_string() for a in self.cells.non_empty_cells()]

    def getUsedRange(self):
        a, b = self.cells.used_range()
        return None if not a.is_valid() else (a.to_string(), b.to_string())

    def getNonEmptyRange(self):
        a, b = self.cells.non_empty_range()
        return (a.to_string(), b.to_string())

    # copy and paste (PropertySheet::copyCells / pasteCells), the clipboard as plain data
    def copy_cells(self, ranges: list) -> list:
        out = []
        for rng in ranges:
            cells = []
            for a in rng:
                c = self.cells.get(a)
                if c is not None and c.is_used():
                    d = {"address": a.to_string(), **c.attrs()}
                    s = c.string_content(True)
                    if c.is_used(EXPRESSION_SET):
                        d["content"] = s or ""
                    cells.append(d)
            out.append({"from": rng.from_().to_string(), "to": rng.to().to_string(), "cells": cells})
        return out

    def paste_cells(self, clip: list, dst: Range):
        """PropertySheet::pasteCells: each copied range at the destination's top left, repeated to fill it when one
        range was copied, relative references moved by the offset."""
        if not clip:
            return
        dst_rows, dst_cols = dst.row_count(), dst.col_count()
        dfrom = dst.from_()
        roffset = coffset = 0
        for ri, block in enumerate(clip):
            frm, to = string_to_address(block["from"]), string_to_address(block["to"])
            rng = Range(frm, to)
            if ri == 0:
                roffset, coffset = dfrom.row - frm.row, dfrom.col - frm.col
            if len(clip) > 1:
                rcount = ccount = 1
            else:
                rcount = max(1, dst_rows // rng.row_count())
                ccount = max(1, dst_cols // rng.col_count())
            it = iter(rng)
            cur = next(it)
            done_cells = []
            for ci, cd in enumerate(block["cells"]):
                src = string_to_address(cd["address"])
                if ci:
                    cur = next(it, None)
                while cur is not None and src != cur:
                    for r in range(rcount):
                        for c in range(ccount):
                            d = CellAddress(cur.row + roffset + r * rng.row_count(), cur.col + coffset + c * rng.col_count())
                            if d.is_valid():
                                self.clear(d)
                    cur = next(it, None)
                new_addr = None
                for r in range(rcount):
                    for c in range(ccount):
                        d = CellAddress(src.row + roffset + r * rng.row_count(), src.col + coffset + c * rng.col_count())
                        if not d.is_valid():
                            continue
                        cell = self.cells.data.get(d.key) or self.cells.create_cell(d)
                        self.cells.split_cell(d)
                        if new_addr is None:
                            ro, co = roffset, coffset
                            new_addr = d
                            cell.restore(cd, check_alias=True)
                        else:
                            ro, co = r * rng.row_count(), c * rng.col_count()
                            nc = self.cells.get(new_addr)
                            if nc is None or nc.expression is None:
                                raise SpreadsheetError(f"Failed to copy cell {self.full_name()}.{d.to_string()} from "
                                                       f"{new_addr.to_string()}")
                            cell.set_expression(X.copy(nc.expression))
                            # getExpression(true) carries the cell's look in the expression's comment, which
                            # Cell::setExpression restores (an alias already taken is left out)
                            look = nc.attrs()
                            if look:
                                cell.restore(look, check_alias=True)
                        if cell.is_used(SPANS_SET):
                            rs, cs = cell.spans()
                            self.cells.merge_cells(d, CellAddress(d.row + rs - 1, d.col + cs - 1))
                        else:
                            self.cells.split_cell(d)
                        if (ro or co) and cell.expression is not None:
                            if _OffsetCells(ro, co).visit(cell.expression):
                                self.cells.recompute_dependencies(d)
                        self.cells.dirty.add(d.key)
                done_cells.append(src)
            rest = list(it) if block["cells"] else list(rng)
            for cur in rest:
                for r in range(rcount):
                    for c in range(ccount):
                        d = CellAddress(cur.row + roffset + r * rng.row_count(), cur.col + coffset + c * rng.col_count())
                        if d.is_valid():
                            self.clear(d)

    # CSV (Sheet::importFromFile / exportToFile)
    def import_text(self, text: str, delimiter="\t", quote_char='"', escape_char="\\"):
        self.clear_all()
        for row, line in enumerate(text.splitlines()):
            fields = _fields(line, delimiter, quote_char, escape_char)
            for col, f in enumerate(fields):
                if f:
                    self.set_cell(CellAddress(row, col), f)

    def export_text(self, delimiter="\t", quote_char='"', escape_char="\\") -> str:
        out = []
        prev_row = prev_col = -1
        used = self.cells.non_empty_cells()
        first_col = used[0].col if used else 0
        for a in used:
            p = self.props.get(a.to_string(absolute=False))
            if prev_row != -1 and prev_row != a.row:
                out.append("\n" * (a.row - prev_row))
                prev_col = first_col
            if prev_col != -1 and a.col != prev_col:
                out.append(delimiter * (a.col - prev_col))
            field = _stream(p) if p is not None else ""
            # `std::string(quoteChar, delimiter)` is a string of quoteChar copies of the delimiter: FreeCAD quotes a
            # field that holds the delimiter (and never for a quote alone)
            if quote_char and delimiter in field:
                field = quote_char + "".join(escape_char + c if c == quote_char else c for c in field) + quote_char
            out.append(field)
            prev_row, prev_col = a.row, a.col
        out.append("\n")
        return "".join(out)


def _same_value(a, b) -> bool:
    if type(a) is not type(b):
        return False
    if isinstance(a, X.Quantity):
        return a.value == b.value and tuple(a.dims) == tuple(b.dims)
    try:
        return bool(a == b)
    except Exception:
        return False


def _decode_row_arg(row) -> int:
    from .spreadsheet import decode_row
    return decode_row(str(row))


def _stream(p: Prop) -> str:
    """`field << value` of exportToFile: a double at the stream's default precision 6 (%g), an int, the string."""
    if p.kind == "quantity":
        return X.to_number(p.value.value, "Default", 6)
    if p.kind == "float":
        return X.to_number(p.value, "Default", 6)
    if p.kind == "int":
        return str(p.value)
    if p.kind == "string":
        return p.value
    return ""


def _fields(line: str, sep: str, quote: str, escape: str) -> list:
    """One line's fields (FreeCAD reads the file line by line through boost::escaped_list_separator): the standard library's
    csv reader with the same separator, quote and escape (ui/PARITY.md has where the two differ)."""
    try:
        return next(csv.reader([line], delimiter=sep, quotechar=quote or None, escapechar=(escape or None) if quote else None,
                               doublequote=False, quoting=csv.QUOTE_MINIMAL if quote else csv.QUOTE_NONE, strict=False), [])
    except csv.Error as e:
        raise SpreadsheetError(str(e)) from None


def classify(out):
    """What Sheet::updateProperty makes of an expression's value (expressionFromPy, then the property type)."""
    if out is None:
        return "object", None
    if isinstance(out, bool):
        return "object", out
    if isinstance(out, str):
        return "string", out
    if isinstance(out, X.Quantity):
        if tuple(out.dims) != ONE:
            return "quantity", out
        v = out.value
    elif isinstance(out, (int, float)):
        if isinstance(out, int) and not -2 ** 63 <= out < 2 ** 63:
            return "object", out                  # PyLong_AsLong fails: not a number to FreeCAD
        v = float(out)
    else:
        return "object", out
    if math.isfinite(v) and v == math.floor(v) and -9.223372036854776e18 <= v <= 9.223372036854776e18:
        return "int", int(v)
    return "float", v


def _topological(start, dirty: set, provides_to):
    """The graph Sheet::execute builds (vertices in the order the work queue meets them, edges cell -> reader) and
    boost::topological_sort's order: depth first from each vertex in turn, out-edges in the order added, the finishing
    order reversed. Returns (order, ok, vertices)."""
    index, verts, edges = {}, [], []
    queue = deque(start)
    dirty = set(dirty)

    def vertex(k):
        if k not in index:
            index[k] = len(verts)
            verts.append(k)
            edges.append([])
            return True
        return False

    while queue:
        cur = queue.popleft()
        vertex(cur)
        for dep in provides_to(cur):
            if vertex(dep):
                if dep not in dirty:
                    dirty.add(dep)
                    queue.append(dep)
            edges[index[cur]].append(index[dep])
    color = [0] * len(verts)          # 0 white, 1 gray, 2 black
    finished = []
    for s in range(len(verts)):
        if color[s]:
            continue
        stack = [(s, iter(edges[s]))]
        color[s] = 1
        while stack:
            u, it = stack[-1]
            for w in it:
                if color[w] == 1:
                    return [], False, set(verts)
                if color[w] == 0:
                    color[w] = 1
                    stack.append((w, iter(edges[w])))
                    break
            else:
                color[u] = 2
                finished.append(u)
                stack.pop()
    return [verts[i] for i in reversed(finished)], True, set(verts)


def _has_cycle(verts, edges) -> bool:
    index = {v: i for i, v in enumerate(verts)}
    color = {v: 0 for v in verts}
    for s in verts:
        if color[s]:
            continue
        stack = [(s, iter(edges[s]))]
        color[s] = 1
        while stack:
            u, it = stack[-1]
            for w in it:
                if color[w] == 1:
                    return True
                if color[w] == 0:
                    color[w] = 1
                    stack.append((w, iter(edges[w])))
                    break
            else:
                color[u] = 2
                stack.pop()
    del index
    return False


# ── what the view shows (SheetModel::data) ───────────────────────────────────────────────────────────────

# SheetParameter's colours as the "FreeCAD Light" preference pack sets them (the app's theme; FreeCAD's own defaults
# without a pack are #feff9e and #000000)
LIGHT = {"alias_bg": "#bac8ff", "text_fg": "#212529", "positive_fg": "#212529", "negative_fg": "#212529"}


def _qcolor(c) -> str:
    """QColor(255.0 * r, ...): the int conversion of each double."""
    return "#" + "".join(f"{int(255.0 * float(x)) & 0xff:02x}" for x in c[:3]) + (
        "" if int(255.0 * float(c[3])) == 255 else f"{int(255.0 * float(c[3])) & 0xff:02x}")


def display(sheet: Sheet, addr: CellAddress, prefs: dict | None = None) -> dict:
    """SheetModel::data for one cell, the roles the table draws: display (DisplayRole), edit (EditRole), tooltip,
    fg / bg (ForegroundRole / BackgroundRole, None when the role gives nothing), align (Qt flags as names),
    font (bold/italic/underline). prefs: decimals, schema (UnitsApi), show_alias (showAliasName), alias_format."""
    prefs = {**LIGHT, **(prefs or {})}
    decimals = prefs.get("decimals", 2)
    ALIAS_BG = prefs["alias_bg"]
    cell = sheet.cells.get(addr)
    empty = cell is None
    if empty:
        cell = Cell(CellAddress(0, 0), sheet.cells)
    out = {"display": None, "edit": None, "tooltip": None, "fg": None, "bg": None, "align": None, "font": []}
    if not cell.has_exception() and cell.is_used(ALIAS_SET):
        out["tooltip"] = cell.alias
    s = cell.string_content()
    out["edit"] = s
    if cell.has_exception():
        import html
        out["tooltip"] = "<pre>" + html.escape(cell.exception, quote=False).replace('"', "&quot;") + "</pre>"   # toHtmlEscaped
        out["display"] = s if s is not None else "#ERR"
        out["fg"] = "#ff0000"
        out["align"] = ["left", "vcenter"]
        out["exception"] = True
        if cell.is_used(BACKGROUND_COLOR_SET):
            out["bg"] = _qcolor(cell.background)
        elif cell.is_used(ALIAS_SET):
            out["bg"] = ALIAS_BG
        if cell.is_used(STYLE_SET):
            out["font"] = sorted(cell.style)
        return out
    if cell.is_used(BACKGROUND_COLOR_SET):
        out["bg"] = _qcolor(cell.background)
    elif cell.is_used(ALIAS_SET):
        out["bg"] = ALIAS_BG
    a = cell.alignment
    align = []
    for bit, name in ((ALIGNMENT_LEFT, "left"), (ALIGNMENT_HCENTER, "hcenter"), (ALIGNMENT_RIGHT, "right"),
                      (ALIGNMENT_TOP, "top"), (ALIGNMENT_VCENTER, "vcenter"), (ALIGNMENT_BOTTOM, "bottom")):
        if a & bit:
            align.append(name)
    if cell.is_used(STYLE_SET):
        out["font"] = sorted(x for x in cell.style if x in ("bold", "italic", "underline"))
    prop = None if empty else sheet.props.get(addr.to_string(absolute=False))
    dirty = addr.key in sheet.cells.dirty

    def implied(h_default):
        al = list(align)
        if a & ALIGNMENT_HIMPLIED:
            al = [x for x in al if x not in ("left", "hcenter", "right")] + [h_default]
        if a & ALIGNMENT_VIMPLIED:
            al = [x for x in al if x not in ("top", "vcenter", "bottom")] + ["vcenter"]
        return al

    def fmt(text):
        if cell.is_used(ALIAS_SET) and prefs.get("show_alias"):
            f = prefs.get("alias_format", "%V = %A")
            if "%V" in f or "%A" in f:
                return f.replace("%A", cell.alias).replace("%V", text)
        return text

    fg_set = cell.is_used(FOREGROUND_COLOR_SET)
    if prop is None or dirty:
        out["fg"] = "#0000ff"
        out["align"] = ["hcenter", "vcenter"]
        if cell.expression is not None and s is not None:
            out["display"] = "#PENDING" if s.startswith("=") else s
        out["pending"] = True
        return out
    if prop.kind == "string":
        out["fg"] = _qcolor(cell.foreground) if fg_set else prefs["text_fg"]
        out["display"] = fmt(prop.value)
        out["align"] = implied("left")
    elif prop.kind == "quantity":
        q = prop.value
        out["fg"] = _qcolor(cell.foreground) if fg_set else prefs["negative_fg" if q.value < 0 else "positive_fg"]
        out["align"] = implied("right")
        if cell.is_used(DISPLAY_UNIT_SET):
            du = cell.display_unit
            if tuple(q.dims) == ONE or tuple(q.dims) == tuple(du.unit):
                out["display"] = fmt(_qlocale_fixed(q.value / du.scaler, decimals) + " " + du.string_rep)
            else:
                out["display"] = fmt("#ERR: unit")
        else:
            out["display"] = fmt(X.user_string(q, prefs.get("schema", 0), decimals, prefs.get("denominator", 8))[0])
    elif prop.kind in ("float", "int"):
        d = float(prop.value)
        out["fg"] = _qcolor(cell.foreground) if fg_set else prefs["negative_fg" if d < 0 else "positive_fg"]
        out["align"] = implied("right")
        if cell.is_used(DISPLAY_UNIT_SET):
            out["display"] = fmt(_qlocale_fixed(d / cell.display_unit.scaler, decimals) + " " + cell.display_unit.string_rep)
        elif prop.kind == "float":
            out["display"] = fmt(_qlocale_fixed(d, decimals))
        else:
            out["display"] = fmt(str(prop.value))
    else:
        out["fg"] = _qcolor(cell.foreground) if fg_set else prefs["text_fg"]
        out["align"] = implied("hcenter")
        out["display"] = fmt(X.py_str(prop.value))
    return out


def _qlocale_fixed(v: float, decimals: int) -> str:
    """QLocale().toString(v, 'f', decimals) in the C locale: printf's %.*f, no grouping (Qt's default C locale omits
    the group separator)."""
    if math.isnan(v):
        return "nan"
    if math.isinf(v):
        return "inf" if v > 0 else "-inf"
    return X.to_number(v, "Fixed", decimals)

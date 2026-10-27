# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses FreeCAD's spreadsheet cells and keeps FreeCAD's licence, the GNU Lesser General
# Public License, version 2.1 or (at your option) any later version; the text is in ../ui/LICENSE.
#
#   Derived from: src/App/Range.cpp, src/App/Range.h (Copyright (c) 2015 Eivind Kvedalen),
#                 src/Mod/Spreadsheet/App/Cell.cpp (Copyright (c) 2015 Eivind Kvedalen),
#                 src/Mod/Spreadsheet/App/PropertyColumnWidths.cpp, PropertyRowHeights.cpp (Copyright (c) 2015 Eivind
#                 Kvedalen), src/Base/Color.h (Copyright (c) 2005 Werner Mayer)
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
"""A spreadsheet of a project: spreadsheet/<Name>.py's SHEET list (docs/EDITING_PLAN.md, "Spreadsheets in a project").

    from cad_agent import spreadsheet as Spreadsheet

    SHEET = [
        Spreadsheet.Sheet("Spreadsheet", label="Params", column_widths={"A": 140}),
        Spreadsheet.Cell("A1", "'Thickness", style="bold"),
        Spreadsheet.Cell("B1", "=5 mm", alias="thick"),
    ]

Sheet is the Spreadsheet::Sheet (its Name, Label, column widths and row heights), each Cell one used cell of its
PropertySheet with what a FreeCAD document saves of it: the content as Cell::getStringContent gives it, then the <Cell>
element's attributes in FreeCAD's own encoding. This module holds that vocabulary and FreeCAD's cell addresses and ranges
(App/Range.cpp); the sheet itself, its evaluation and recompute are spreadsheet_sheet.py, the project's document of sheets
and parts spreadsheet_doc.py. It imports nothing heavy: a part file may import it.
"""
from __future__ import annotations

import re
import struct

MAX_ROWS = 16384                       # CellAddress::MAX_ROWS
MAX_COLUMNS = 26 * 26 + 26             # CellAddress::MAX_COLUMNS
DEFAULT_WIDTH = 100                    # PropertyColumnWidths::defaultWidth
DEFAULT_HEADER_WIDTH = 50              # PropertyColumnWidths::defaultHeaderWidth
DEFAULT_HEIGHT = 30                    # PropertyRowHeights::defaultHeight
DIR = "spreadsheet"                    # the project's folder of sheets
LIST = "SHEET"
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SpreadsheetError(ValueError):
    """What FreeCAD refuses, in FreeCAD's words where it has words for it."""


# ── CellAddress and Range (App/Range.cpp) ────────────────────────────────────────────────────────────────

class CellAddress:
    """App::CellAddress: a 0-based row and column, with $ flags. Equality and order ignore the flags (asInt())."""
    __slots__ = ("row", "col", "abs_row", "abs_col")

    def __init__(self, row: int = -1, col: int = -1, abs_row: bool = False, abs_col: bool = False):
        self.row, self.col, self.abs_row, self.abs_col = row, col, abs_row, abs_col

    @property
    def key(self) -> tuple:
        return (self.row, self.col)

    def as_int(self) -> int:
        return ((self.row & 0xffff) << 16) | (self.col & 0xffff)

    def is_valid(self) -> bool:
        return 0 <= self.row < MAX_ROWS and 0 <= self.col < MAX_COLUMNS

    def __eq__(self, other):
        return isinstance(other, CellAddress) and self.key == other.key

    def __lt__(self, other):
        return self.key < other.key

    def __hash__(self):
        return hash(self.key)

    def __repr__(self):
        return f"CellAddress({self.to_string()!r})"

    def to_string(self, show_row=True, show_col=True, absolute=True) -> str:
        """CellAddress::toString (ShowFull by default; ShowRowColumn leaves the $ out)."""
        s = ""
        if show_col:
            if self.abs_col and absolute:
                s += "$"
            s += column_name(self.col)
        if show_row:
            if self.abs_row and absolute:
                s += "$"
            s += str(self.row + 1)
        return s

    def __str__(self):
        return self.to_string()


def column_name(col: int) -> str:
    """CellAddress::toString's column: A..Z, then AA..ZZ."""
    if col < 26:
        return chr(ord("A") + col)
    n = col - 26
    return chr(ord("A") + n // 26) + chr(ord("A") + n % 26)


def valid_row(rowstr: str) -> int:
    """App::validRow: strtol of the text, 1..MAX_ROWS and nothing after it; the 0-based row or -1."""
    m = re.match(r"\s*([+-]?\d+)", rowstr)
    if not m or m.end() != len(rowstr):
        return -1
    i = int(m.group(1))
    if i <= 0 or i > MAX_ROWS:
        return -1
    return i - 1


def valid_column(colstr: str) -> bool:
    return re.fullmatch(r"[A-Z]{1,3}", colstr) is not None


def decode_column(colstr: str, silent: bool = False) -> int:
    """App::decodeColumn (columnStringToNum: A is 0, AA is 26)."""
    if valid_column(colstr):
        out = 0
        for pos, ch in enumerate(reversed(colstr)):
            out += (ord(ch) - ord("A") + 1) * 26 ** pos
        return out - 1
    if silent:
        return -1
    raise SpreadsheetError("Invalid column specification")


def decode_row(rowstr: str, silent: bool = False) -> int:
    row = valid_row(rowstr)
    if silent or row >= 0:
        return row
    raise SpreadsheetError("Invalid row specification.")


_ADDR = re.compile(r"(\$?[A-Z]{1,2})(\$?[0-9]{1,5})")


def string_to_address(s: str, silent: bool = False) -> CellAddress:
    """App::stringToAddress: "B3", "$B$3"; an invalid CellAddress (silent) or "Invalid cell specifier."."""
    m = _ADDR.fullmatch(s or "")
    if m:
        c, r = m.group(1), m.group(2)
        abs_col, abs_row = c.startswith("$"), r.startswith("$")
        return CellAddress(decode_row(r.lstrip("$"), silent), decode_column(c.lstrip("$"), silent), abs_row, abs_col)
    if silent:
        return CellAddress()
    raise SpreadsheetError("Invalid cell specifier.")


def is_valid_cell_address_name(candidate: str) -> bool:
    """PropertySheet::isValidCellAddressName."""
    m = re.fullmatch(r"\$?([A-Z]{1,2})\$?([0-9]{1,5})", candidate or "")
    return bool(m) and valid_row(m.group(2)) >= 0 and valid_column(m.group(1))


class Range:
    """App::Range: an iterator over a rectangle of cells, column by column (Range::next). Not normalized unless asked."""

    def __init__(self, a, b=None, normalize: bool = False):
        if isinstance(a, str):
            text = a
            if ":" not in text:
                f = t = text
            else:
                f, t = text.split(":", 1)
            begin, end = string_to_address(f), string_to_address(t)
        elif isinstance(a, CellAddress):
            begin, end = a, (b if b is not None else a)
        else:
            raise TypeError(a)
        self.row_begin, self.col_begin, self.row_end, self.col_end = begin.row, begin.col, end.row, end.col
        if normalize:
            self.normalize()

    @classmethod
    def of(cls, row_begin, col_begin, row_end, col_end, normalize=False) -> "Range":
        r = cls(CellAddress(row_begin, col_begin), CellAddress(row_end, col_end), normalize)
        return r

    def normalize(self):
        if self.row_begin > self.row_end:
            self.row_begin, self.row_end = self.row_end, self.row_begin
        if self.col_begin > self.col_end:
            self.col_begin, self.col_end = self.col_end, self.col_begin

    def __iter__(self):
        """The cells as `do { ... } while (range.next())` visits them: the first, then down each column."""
        r, c = self.row_begin, self.col_begin
        yield CellAddress(r, c)
        while True:
            if r < self.row_end:
                r += 1
            elif c < self.col_end:
                if r == self.row_end + 1:
                    return
                r = self.row_begin
                c += 1
            else:
                return
            yield CellAddress(r, c)

    def from_(self) -> CellAddress:
        return CellAddress(self.row_begin, self.col_begin)

    def to(self) -> CellAddress:
        return CellAddress(self.row_end, self.col_end)

    def row_count(self) -> int:
        return self.row_end - self.row_begin + 1

    def col_count(self) -> int:
        return self.col_end - self.col_begin + 1

    def size(self) -> int:
        return self.row_count() * self.col_count()

    def range_string(self) -> str:
        return f"{self.from_().to_string()}:{self.to().to_string()}"

    def key(self):
        return (self.from_().key, self.to().key)

    def __repr__(self):
        return f"Range({self.range_string()!r})"


# ── the cell's look, as Cell.cpp encodes it ──────────────────────────────────────────────────────────────

ALIGNMENT_LEFT = 0x01
ALIGNMENT_HCENTER = 0x02
ALIGNMENT_RIGHT = 0x04
ALIGNMENT_HIMPLIED = 0x08
ALIGNMENT_HORIZONTAL = 0x0F
ALIGNMENT_TOP = 0x10
ALIGNMENT_VCENTER = 0x20
ALIGNMENT_BOTTOM = 0x40
ALIGNMENT_VIMPLIED = 0x80
ALIGNMENT_VERTICAL = 0xF0
DEFAULT_ALIGNMENT = ALIGNMENT_HIMPLIED | ALIGNMENT_LEFT | ALIGNMENT_VIMPLIED | ALIGNMENT_VCENTER


def decode_alignment(item: str, alignment: int) -> int:
    """Cell::decodeAlignment: one item or'ed into the alignment."""
    if item == "himplied":
        if not alignment & ALIGNMENT_HORIZONTAL:
            alignment |= ALIGNMENT_LEFT
        alignment |= ALIGNMENT_HIMPLIED
    elif item == "left":
        alignment = (alignment & ~ALIGNMENT_HORIZONTAL) | ALIGNMENT_LEFT
    elif item == "center":
        alignment = (alignment & ~ALIGNMENT_HORIZONTAL) | ALIGNMENT_HCENTER
    elif item == "right":
        alignment = (alignment & ~ALIGNMENT_HORIZONTAL) | ALIGNMENT_RIGHT
    elif item == "vimplied":
        if not alignment & ALIGNMENT_VERTICAL:
            alignment |= ALIGNMENT_VCENTER
        alignment |= ALIGNMENT_VIMPLIED
    elif item == "top":
        alignment = (alignment & ~ALIGNMENT_VERTICAL) | ALIGNMENT_TOP
    elif item == "vcenter":
        alignment = (alignment & ~ALIGNMENT_VERTICAL) | ALIGNMENT_VCENTER
    elif item == "bottom":
        alignment = (alignment & ~ALIGNMENT_VERTICAL) | ALIGNMENT_BOTTOM
    elif item:
        raise SpreadsheetError("Invalid alignment.")
    return alignment


def decode_alignment_text(text: str) -> int:
    """The "|"-separated form (boost's escaped_list_separator on '|', as Cell::restore reads it)."""
    a = 0
    for item in text.split("|"):
        a = decode_alignment(item, a)
    return a


def encode_alignment(alignment: int) -> str:
    """Cell::encodeAlignment."""
    s = ""
    if alignment & ALIGNMENT_LEFT:
        s += "left"
    if alignment & ALIGNMENT_HCENTER:
        s += "center"
    if alignment & ALIGNMENT_RIGHT:
        s += "right"
    if alignment & ALIGNMENT_HIMPLIED:
        s += "|himplied"
    if alignment & ALIGNMENT_VERTICAL:
        s += "|"
    if alignment & ALIGNMENT_TOP:
        s += "top"
    if alignment & ALIGNMENT_VCENTER:
        s += "vcenter"
    if alignment & ALIGNMENT_BOTTOM:
        s += "bottom"
    if alignment & ALIGNMENT_VIMPLIED:
        s += "|vimplied"
    return s


def encode_style(style) -> str:
    """Cell::encodeStyle: a std::set<std::string>, so sorted, joined by '|'."""
    return "|".join(sorted(style))


def decode_style(text: str) -> set:
    return {t for t in text.split("|")} if text is not None else set()


def f32(x: float) -> float:
    """Base::Color holds floats (32 bits)."""
    return struct.unpack("f", struct.pack("f", float(x)))[0]


def color(r, g, b, a=1.0) -> tuple:
    return (f32(r), f32(g), f32(b), f32(a))


BLACK = color(0, 0, 0, 1)
WHITE = color(1, 1, 1, 1)


def encode_color(c) -> str:
    """Cell::encodeColor: #rrggbbaa, each int(component * 255.0) (truncated)."""
    return "#" + "".join(f"{int(float(x) * 255.0) & 0xff:02x}" for x in c)


def decode_color(text: str, default):
    """Cell::decodeColor: #rrggbb or #rrggbbaa (setPackedValue: each byte / 255), else the default."""
    if len(text) in (7, 9):
        if text[0] != "#":
            return default
        m = re.match(r"[0-9a-fA-F]*", text[1:])
        value = int(m.group(0), 16) if m and m.group(0) else 0
        if len(text) == 7:
            value = ((value << 8) | 0xFF) & 0xFFFFFFFF
        return color(((value >> 24) & 0xFF) / 255.0, ((value >> 16) & 0xFF) / 255.0, ((value >> 8) & 0xFF) / 255.0,
                     (value & 0xFF) / 255.0)
    return default


# ── the file's vocabulary ─────────────────────────────────────────────────────────────────────────────────

CELL_KEYS = ("alignment", "style", "foreground_color", "background_color", "display_unit", "alias", "row_span",
             "col_span")


class Cell:
    """One used cell as a FreeCAD document saves it (Cell::save): its address and content, then the attributes it has."""
    kind = "Cell"

    def __init__(self, address: str, content: str | None = None, *, alignment: str | None = None,
                 style: str | None = None, foreground_color: str | None = None, background_color: str | None = None,
                 display_unit: str | None = None, alias: str | None = None, row_span: int | None = None,
                 col_span: int | None = None):
        if not isinstance(address, str) or not string_to_address(address, True).is_valid():
            raise SpreadsheetError(f"{address!r} is not a cell address")
        if content is not None and not isinstance(content, str):
            raise SpreadsheetError(f"{address}: the content is a string, not {content!r}")
        self.address = address
        self.content = content
        self.alignment, self.style = alignment, style
        self.foreground_color, self.background_color = foreground_color, background_color
        self.display_unit, self.alias = display_unit, alias
        self.row_span, self.col_span = row_span, col_span

    def attrs(self) -> dict:
        return {k: getattr(self, k) for k in CELL_KEYS if getattr(self, k) is not None}

    def as_dict(self) -> dict:
        return {"address": self.address, "content": self.content, **self.attrs()}

    def __repr__(self):
        return f"Cell({self.address!r}, {self.content!r}, {self.attrs()})"


class Sheet:
    """The Spreadsheet::Sheet: Name, Label and the sizes of the columns and rows that are not the default."""
    kind = "Sheet"
    TYPE_ID = "Spreadsheet::Sheet"

    def __init__(self, name: str, *, label: str | None = None, column_widths: dict | None = None,
                 row_heights: dict | None = None):
        if not isinstance(name, str) or not NAME.match(name):
            raise SpreadsheetError(f"{name!r} is not an object name (letters, digits and _)")
        self.name = name
        self.label = label
        self.column_widths = {str(k): int(v) for k, v in (column_widths or {}).items()}
        self.row_heights = {str(k): int(v) for k, v in (row_heights or {}).items()}
        for k in self.column_widths:
            if not valid_column(k) or decode_column(k) >= MAX_COLUMNS:
                raise SpreadsheetError(f"{name}: {k!r} is not a column")
        for k in self.row_heights:
            if valid_row(k) < 0:
                raise SpreadsheetError(f"{name}: {k!r} is not a row")

    def as_dict(self) -> dict:
        return {"name": self.name, "type": self.TYPE_ID, "label": self.label or self.name,
                "column_widths": dict(self.column_widths), "row_heights": dict(self.row_heights)}

    def __repr__(self):
        return f"Sheet({self.name!r}, label={self.label!r})"


CLASSES = {"Sheet": Sheet, "Cell": Cell}

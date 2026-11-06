# SPDX-License-Identifier: LGPL-2.1-or-later
# Port of FreeCAD 3160daf1e2b6's Bill of Materials object (src/Mod/Assembly/App/BomObject.cpp, Copyright (c) 2023 Ondsel
# <development@ondsel.com>): BomObject::generateBOM, saveCustomColumnData, addObjectChildrenToBom, addObjectToBom,
# getBomPropertyValue, getText and getColumnIndex; CommandCreateBom.py's ColumnNames and the panel's defaults.
"""The Bill of Materials object: Assembly_CreateBom's Assembly::BomObject, a spreadsheet the assembly fills.

It is a sheet of the project (spreadsheet/<Name>.py) whose head is a Spreadsheet.Bom instead of a Spreadsheet.Sheet:

    SHEET = [
        Spreadsheet.Bom("Bill_of_Materials", label="Bill of Materials",
                        columns_names=["Index", "Name", "Description", "File Name", "Quantity"]),
        Spreadsheet.Cell("C2", "'the base plate"),
        ...
    ]

On every recompute the Index, Name, File Name and Quantity columns (and a ".Prop" column, the property Prop of each
object) are written again from the assembly; what was typed in the other columns stays with the object of its row,
found again by the Name column (saveCustomColumnData). A row is a component of the Assembly: a part (an App::Link's
linked object, a Part::Feature, left out with onlyParts) or a sub-assembly (an AssemblyLink's Assembly, its own
components below it with detailSubAssemblies); siblings linking the same thing are one row and the Quantity counts
them. FreeCAD's File Name is the linked object's document's file; here it is the file that defines it (parts/<part>.py,
<project>/assembly.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .spreadsheet import CellAddress

# CommandCreateBom.ColumnNames: the columns a new BOM starts with
COLUMN_NAMES = ["Index", "Name", "Description", "File Name", "Quantity"]
GENERATED = ("Index", "Name", "Quantity", "File Name")
MIRRORED_SUFFIX = " (mirrored)"       # BaseApp/Preferences/Mod/Assembly BomMirroredSuffix


@dataclass
class Node:
    """One child of an Assembly as BomObject sees it after following its link: what it is ("part" for a
    Part::Feature, "assembly" for an AssemblyObject, "group" for an App::Part, "other" for what the BOM skips), the
    object it is (two siblings with the same target are the same thing), its Label, its file, its properties for
    ".Prop" columns, its children (getOutList) and whether it is mirrored (isObjMirrored)."""
    kind: str
    target: str
    label: str
    file: str = ""
    props: dict = field(default_factory=dict)
    children: list = field(default_factory=list)
    mirrored: bool = False
    linked_label: str | None = None    # the linked object's Label (a mirrored row's suffix when it is the same)


def get_text(sheet, row: int, col: int) -> str:
    """BomObject::getText: the cell's string content, its leading ' taken off."""
    cell = sheet.cells.get(CellAddress(row, col))
    text = ""
    if cell is not None:
        text = cell.string_content() or ""
        if text.startswith("'"):
            text = text[1:]
    return text


def column_index(columns, name: str) -> int:
    return columns.index(name) if name in columns else -1


def save_custom_column_data(sheet, columns) -> list:
    """saveCustomColumnData: (Name, column, text) of every cell typed in a column the BOM does not write."""
    data = []
    used = sheet.cells.used_range()
    max_row = used[1].row
    name_col = column_index(columns, "Name")
    for row in range(1, max_row + 1):
        # the header row as it is now, not columnsNames: the columns may have changed
        for col in range(len(columns)):
            column_name = get_text(sheet, 0, col)
            if column_name not in GENERATED:
                text = get_text(sheet, row, col)
                if text != "":
                    data.append((get_text(sheet, row, name_col), column_name, text))
    return data


def property_value(node: Node, base: str, warn=None) -> str:
    """getBomPropertyValue: the property as a string, "N/A" when the object has none."""
    if base not in node.props:
        if warn:
            warn(f"Property not found: {base}\n")
        return "N/A"
    v = node.props[base]
    if isinstance(v, bool):
        return "True" if v else "False"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return f"{v:f}"                     # std::to_string(double)
    return str(v)


class _Gen:
    def __init__(self, sheet, columns, detail_sub_assemblies, detail_parts, only_parts, data, warn):
        self.sheet, self.columns = sheet, list(columns)
        self.detail_sub, self.detail_parts, self.only_parts = detail_sub_assemblies, detail_parts, only_parts
        self.data, self.warn = data, warn
        self.obj_list, self.obj_mirrored = [], []

    def set(self, row, col, text):
        self.sheet.set_cell(CellAddress(row, col), text)

    def children(self, objs, row: int, index: str) -> int:
        """addObjectChildrenToBom; returns the next free row."""
        qty_col = column_index(self.columns, "Quantity")
        has_qty = "Quantity" in self.columns
        first = row
        if index != "":
            index += "."
        sub_i = 1
        for child in objs:
            if child is None or child.kind == "other":
                continue
            if child.kind == "part" and self.only_parts:
                continue
            if has_qty and row != first:
                found = False
                for i in range(first, row + 1):
                    k = i - 1                                    # -1 for the header
                    if k < len(self.obj_list) and child.target == self.obj_list[k] \
                            and k < len(self.obj_mirrored) and child.mirrored == self.obj_mirrored[k]:
                        qty = int(get_text(self.sheet, i, qty_col)) + 1
                        self.set(i, qty_col, str(qty))
                        found = True
                        break
                if found:
                    continue
            sub_index = index + str(sub_i)
            sub_i += 1
            self.add(child, row, sub_index)
            row += 1
            if (child.kind == "assembly" and self.detail_sub) or (child.kind == "group" and self.detail_parts):
                row = self.children(child.children, row, sub_index)
        return row

    def add(self, obj: Node, row: int, index: str):
        """addObjectToBom."""
        self.obj_list.append(obj.target)
        self.obj_mirrored.append(obj.mirrored)
        for col, name in enumerate(self.columns):
            if name == "Index":
                self.set(row, col, "'" + index)
            elif name == "Name":
                text = obj.label
                if obj.mirrored and obj.linked_label is not None and text == obj.linked_label:
                    text += MIRRORED_SUFFIX
                self.set(row, col, text)
            elif name == "File Name":
                self.set(row, col, obj.file)
            elif name == "Quantity":
                self.set(row, col, "1")
            elif name.startswith("."):
                v = property_value(obj, name[1:], self.warn)
                if v:
                    self.set(row, col, v)
            else:
                for o, c, text in self.data:
                    if o == obj.label and c == name:
                        self.set(row, col, text)
                        break


def generate(sheet, roots: list, columns=None, detail_sub_assemblies=True, detail_parts=True, only_parts=False,
             warn=None):
    """BomObject::generateBOM: the custom data saved, the sheet cleared, the header and a row per component of roots
    (the Assembly's getOutList, each Link already followed to what it links)."""
    columns = list(COLUMN_NAMES if columns is None else columns)
    data = save_custom_column_data(sheet, columns)
    sheet.clear_all()
    g = _Gen(sheet, columns, detail_sub_assemblies, detail_parts, only_parts, data, warn)
    for col, name in enumerate(columns):
        g.set(0, col, name)
    g.children(roots, 1, "")
    return g


def project_roots(pdir) -> list:
    """The Assembly of a project (its assembly.py) as generate reads it: each App::Link a "part" row of its part (its
    Label the part's name, its file parts/<part>.py), each AssemblyLink an "assembly" row of the project it links, its
    components below it. FreeCAD labels a sub-assembly's row with the linked Assembly's Label; a sub-assembly here is a
    project, and its row has the project's name. Nothing when the project has no Assembly."""
    from pathlib import Path

    from . import assembly_edit as E
    from . import assembly_wb as W
    from .assembly_link import AssemblyLink

    def objects(d: Path):
        path = d / "assembly.py"
        return (E.objects_of(path.read_text()) if path.exists() else None) or []

    def nodes(objs, prefix: str):
        out = []
        for o in objs:
            if isinstance(o, W.Link):
                part = o.linked_object
                out.append(Node("part", f"{prefix}{part}", part, f"{prefix}parts/{part}.py", {"Label": part}))
            elif isinstance(o, AssemblyLink):
                proj = o.linked_object
                sub = Path(pdir).parent / proj
                out.append(Node("assembly", f"@{proj}", proj, f"{proj}/assembly.py", {"Label": proj},
                                nodes(objects(sub), f"{proj}/")))
            else:
                out.append(Node("other", o.name, getattr(o, "label", None) or o.name))
        return out

    return nodes(objects(Path(pdir)), "")

"""What the sheet view shows of each cell (SheetModel::data, cad_agent.spreadsheet_sheet.display) against the real FreeCAD
GUI's model, recorded by ui/scripts/fcspreadsheet.py into ui/scripts/fcspreadsheet.json: the cells typed as the dump types
them (SheetModel::setCellData: set, then a recompute), with its display units and aliases, then each cell's display
string, edit text, tooltip, colours, alignment and font; a typed formula before its recompute (#PENDING); the cycles."""
import json
from pathlib import Path

import pytest

from cad_agent.spreadsheet import string_to_address
from cad_agent.spreadsheet_doc import Document
from cad_agent.spreadsheet_sheet import display

FC = json.loads((Path(__file__).resolve().parent.parent / "ui" / "scripts" / "fcspreadsheet.json").read_text())
CELLS = {
    "A1": "5", "A2": "-3", "A3": "2.5", "A4": "-2.5", "A5": "1/3", "A6": "12345.678", "A7": "1e-7", "A8": "1e20",
    "A9": "12,5", "A10": "0.005", "A11": "-0.004", "A12": "=1/0", "A13": "=nothing", "A14": "=foo(", "A15": "'text",
    "A16": "hello", "A17": "=True", "A18": "=None", "A19": "=list(1;2)", "A20": "=vector(1;2;3)",
    "B1": "3 mm", "B2": "1 m", "B3": "=1 m * 1 m", "B4": "=2 kg", "B5": "=90 deg", "B6": "=1 s", "B7": "-3 mm",
    "B8": "=1 mm / 1 s", "B9": "=12 in", "B10": "=0.5 mm", "B11": "=1e-4 mm", "B12": "=5 N", "B13": "=3 mm",
    "B14": "=4 mm", "B15": "=5", "B16": "=7 mm", "B17": "=1.5", "B18": "=2", "B19": "=1 mm^3", "B20": "=sqrt(2)",
    "C1": "=A1 * 2", "C2": "=B1 + B2", "C3": "=sum(A1:A3)", "C4": "=average(B1:B2)",
    "C8": "=min(A1:A3)", "C9": "=max(B1:B2)", "C10": "=count(A1:A6)", "C11": "=stddev(A1:A3)",
    "C12": "=A15 + 1", "C13": "=<<x>>", "C14": "=str(B1)", "C15": "=B1 > 2 mm", "C16": "=A1 / 2",
}
DISPLAY = {"B13": "cm", "B14": "in", "B15": "mm", "B16": "s", "B17": "deg", "B18": "mm"}
ALIASES = {"B1": "thick", "A3": "ratio"}
PREFS = {"decimals": FC["prefs"]["Decimals"], "schema": FC["prefs"]["UserSchema"],
         "alias_bg": FC["prefs"]["AliasedCellBackgroundColor"], "text_fg": FC["prefs"]["TextColor"],
         "positive_fg": FC["prefs"]["PositiveNumberColor"], "negative_fg": FC["prefs"]["NegativeNumberColor"]}
ROLES = ("display", "edit", "tooltip", "fg", "bg", "align", "font")


def ours(sheet, a):
    d = display(sheet, string_to_address(a), PREFS)
    return {k: d[k] for k in ROLES}


def typed_sheet():
    doc = Document("Unnamed")
    s = doc.add_sheet("Spreadsheet")
    for a, t in CELLS.items():
        s.set(a, t)
        doc.recompute()
    for a, u in DISPLAY.items():
        s.setDisplayUnit(a, u)
    for a, al in ALIASES.items():
        s.setAlias(a, al)
    doc.recompute()
    return doc, s


@pytest.mark.parametrize("addr", sorted(FC["cells"]["view"]))
def test_cell_shows_as_in_freecad(addr):
    _, s = typed_sheet()
    want = FC["cells"]["view"][addr]
    got = ours(s, addr)
    assert {k: got[k] for k in ROLES} == {k: (sorted(want[k]) if k == "align" and want[k] else want[k]) for k in ROLES} \
        or _same(got, want), (addr, CELLS.get(addr))


def _same(got, want):
    return all((sorted(got[k] or []) == sorted(want[k] or [])) if k in ("align", "font") else got[k] == want[k]
               for k in ROLES)


def test_pending_then_computed():
    doc = Document("Unnamed")
    s = doc.add_sheet("Spreadsheet")
    for a, t in (("A1", "5"), ("C5", "=C6"), ("C6", "=C5")):    # the cycle the dump had made then
        s.set(a, t)
    doc.recompute()
    s.set("D1", "=A1 + 1")
    s.set("D2", "7")
    for a in ("D1", "D2"):
        assert _same(ours(s, a), FC["pending"][a]), a


@pytest.mark.parametrize("stage,rng", [("first", "A1:B3"), ("fixed", "A1:B3"), ("two_loops", "C1:E3")])
def test_cycles_show_as_in_freecad(stage, rng):
    doc = Document("Unnamed")
    s = doc.add_sheet("Spreadsheet001")
    for a, t in (("A1", "=A2 + 1"), ("A2", "=A1"), ("A3", "=A3"), ("B1", "5"), ("B2", "=B1 * 2")):
        s.set(a, t)
    doc.recompute()
    if stage != "first":
        s.set("A2", "4")
        s.set("A3", "1")
        doc.recompute()
    if stage == "two_loops":
        for a, t in (("C1", "=D1"), ("D1", "=C1"), ("E1", "=E2"), ("E2", "=E3"), ("E3", "=E1")):
            s.set(a, t)
        doc.recompute()
    for a, want in FC["cycles"][stage].items():
        assert _same(ours(s, a), want), (a, ours(s, a), want)

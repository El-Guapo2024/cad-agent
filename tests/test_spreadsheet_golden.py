"""cad_agent's spreadsheets against the real FreeCAD's: each case of tests/golden/spreadsheet/cases.py replayed on
cad_agent.spreadsheet_doc and compared with what freecadcmd recorded in freecad.json (tests/golden/spreadsheet/make.py):
every used cell's content as FreeCAD stores it, its property type and value or "ERR: ..." message, alias, style,
alignment, colours and display unit, the <Cell> attributes a document saves (our file's keywords), column widths and row
heights, the used range, the errors steps raise, a reopened document's recompute, the Pad length a cell drives and the
CSV FreeCAD exports.
"""
import importlib.util
import json
import math
from pathlib import Path

import pytest

from cad_agent import fcexpr as X
from cad_agent import spreadsheet as SS
from cad_agent.spreadsheet_doc import Document, DependencyCycle, PartObject
from cad_agent.spreadsheet_edit import TEMPLATE, model_entries, write_src
from cad_agent.spreadsheet_sheet import Sheet

HERE = Path(__file__).resolve().parent / "golden" / "spreadsheet"
_spec = importlib.util.spec_from_file_location("spreadsheet_golden_cases", HERE / "cases.py")
cases_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cases_mod)
FC = json.loads((HERE / "freecad.json").read_text())

TYPES = {"int": "App::PropertyInteger", "float": "App::PropertyFloat", "quantity": "Spreadsheet::PropertySpreadsheetQuantity",
         "string": "App::PropertyString", "object": "App::PropertyPythonObject"}
SAVED = {"alignment": "alignment", "style": "style", "foreground_color": "foregroundColor",
         "background_color": "backgroundColor", "display_unit": "displayUnit", "alias": "alias", "row_span": "rowSpan",
         "col_span": "colSpan"}


def val(v):
    if v is None or isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, float):
        return v if math.isfinite(v) else repr(v)
    if isinstance(v, X.Quantity):
        return {"q": v.value if math.isfinite(v.value) else repr(v.value), "unit": list(v.dims), "s": X.py_str(v)}
    if isinstance(v, (list, tuple)):
        return {"seq": type(v).__name__, "items": [val(x) for x in v], "s": X.py_str(v)}
    return {"obj": type(v).__name__, "s": X.py_str(v)}


def sheet_state(s: Sheet) -> dict:
    cells = {}
    for a in s.getUsedCells():
        d = {"content": s.get_contents(a)}
        p = s.get_property(a)
        d["type"] = TYPES[p.kind] if p is not None else None
        if p is not None:
            d["value"] = val(p.value)
        else:
            d["get_error"] = f"Invalid cell address or property: {a}"
        for k, f in (("alias", s.getAlias), ("style", s.getStyle), ("alignment", s.getAlignment),
                     ("foreground", s.getForeground), ("background", s.getBackground), ("display_unit", s.getDisplayUnit)):
            r = f(a)
            if r is not None:
                d[k] = sorted(r) if isinstance(r, set) else ([round(x, 6) for x in r] if isinstance(r, tuple) else r)
        cells[a] = d
    widths = {SS.column_name(c): w for c, w in s.column_widths.items() if w != 100 and c < 26}
    heights = {str(r + 1): h for r, h in s.row_heights.items() if h != 30 and r < 79}
    ents = model_entries(s)
    saved = {"cells": [[e.address, {**({"content": e.content} if e.content is not None else {}),
                                    **{SAVED[k]: str(v) for k, v in e.attrs().items()}}] for e in ents[1:]],
             "columnWidths": {k: v for k, v in s.column_widths_named().items()},
             "rowHeights": {str(r + 1): h for r, h in sorted(s.row_heights.items())}}
    return {"label": s.label, "cells": cells, "column_widths": widths, "row_heights": heights,
            "used_range": list(s.getUsedRange()) if s.getUsedRange() else None, "saved": saved,
            "invalid": bool(s.cell_errors)}


def replay(name, steps):
    doc = Document("T")
    out = []
    parts = {}

    def recompute():
        try:
            return doc.recompute()
        except DependencyCycle:
            return "cycle"

    def snapshot(what, ret):
        objs = {}
        for o in doc.objects.values():
            if isinstance(o, Sheet):
                objs[o.name] = sheet_state(o)
        for pn in parts:
            p = doc.objects[pn]
            L = p.bound["length"]
            objs[pn] = {"length": L, "pad_length": L, "volume": round(40 * 20 * L, 6), "expressions": dict(p.expressions)}
        out.append({"step": what, "return": ret, "objects": objs})

    for i, st in enumerate(steps):
        try:
            if st[0] == "@sheet":
                doc.add_sheet(st[1], st[2] if len(st) > 2 else None)
            elif st[0] == "@recompute":
                snapshot("recompute", recompute())
            elif st[0] == "@restore":
                srcs = {o.name: write_src(TEMPLATE.format(name=o.name, slug="T"), model_entries(o))
                        for o in doc.objects.values() if isinstance(o, Sheet)}
                prts = {pn: (doc.objects[pn].bound, doc.objects[pn].expressions) for pn in parts}
                doc = Document(name, srcs, {})
                for pn, (params, ex) in prts.items():
                    doc.objects[pn] = PartObject(pn, params, ex)
                snapshot("restore", recompute())
            elif st[0] == "@part":
                parts[st[1]] = True
                doc.objects[st[1]] = PartObject(st[1], dict(st[2]), dict(st[3]))
            elif st[0] == "@bind":
                part = doc.objects[st[1]]
                err = doc.validate_expression(part, st[2], st[3])
                if err:
                    raise SS.SpreadsheetError(err)
                part.expressions[st[2]] = st[3]
                out.append({"step": "bind", "ok": True})
            elif st[0] == "@export":
                out.append({"step": "export", "text": doc.objects[st[1]].export_text()})
            elif st[0] == "@import":
                doc.objects[st[1]].import_text(st[2])
                out.append({"step": "import", "ok": True})
            else:
                getattr(doc.objects[st[0]], st[1])(*st[2:])
        except (SS.SpreadsheetError, X.ExprError) as e:
            out.append({"step": i, "error": "x", "message": e.message if isinstance(e, X.ExprError) else str(e)})
    return out


def compare(fc_steps, ours):
    diffs = []
    assert len(fc_steps) == len(ours), ([s.get("step") for s in fc_steps], [s.get("step") for s in ours])
    for f, o in zip(fc_steps, ours):
        where = f"step {f.get('step')}"
        if "error" in f or "error" in o:
            if f.get("message") != o.get("message"):
                diffs.append(f"{where}: FreeCAD raised {f.get('message')!r}, ours {o.get('message')!r}")
            continue
        if "text" in f:
            if f["text"] != o["text"]:
                diffs.append(f"{where}: export {f['text']!r} != {o['text']!r}")
            continue
        for name, fo in f.get("objects", {}).items():
            oo = o["objects"].get(name)
            if oo is None:
                diffs.append(f"{where}: no object {name}")
                continue
            if "pad_length" in fo:
                for k in ("length", "pad_length", "volume"):
                    if not math.isclose(fo[k], oo[k], rel_tol=1e-9, abs_tol=1e-9):
                        diffs.append(f"{where} {name}.{k}: {fo[k]} != {oo[k]}")
                continue
            fcells, ocells = fo["cells"], oo["cells"]
            if set(fcells) != set(ocells):
                diffs.append(f"{where} {name}: cells {sorted(set(fcells) ^ set(ocells))} differ")
            for a in sorted(set(fcells) & set(ocells)):
                fc, oc = fcells[a], ocells[a]
                for k in set(fc) | set(oc):
                    fv, ov = fc.get(k), oc.get(k)
                    if k == "style" and fv is not None:
                        fv = sorted(fv)
                    if k in ("foreground", "background") and fv is not None:
                        fv = [round(x, 4) for x in fv]
                        ov = [round(x, 4) for x in ov] if ov else ov
                    if not same(fv, ov):
                        diffs.append(f"{where} {name}.{a}.{k}: FreeCAD {fv!r}, ours {ov!r}")
            for k in ("column_widths", "row_heights", "used_range", "label"):
                if fo[k] != oo[k]:
                    diffs.append(f"{where} {name}.{k}: {fo[k]!r} != {oo[k]!r}")
            fs, os_ = fo.get("saved") or {}, oo["saved"]
            if fs.get("cells", []) != os_["cells"]:
                fd = {a: x for a, x in fs.get("cells", [])}
                od = {a: x for a, x in os_["cells"]}
                for a in sorted(set(fd) | set(od)):
                    if fd.get(a) != od.get(a):
                        diffs.append(f"{where} {name} saved {a}: FreeCAD {fd.get(a)!r}, ours {od.get(a)!r}")
            if fs.get("columnWidths", {}) != os_["columnWidths"] or fs.get("rowHeights", {}) != os_["rowHeights"]:
                diffs.append(f"{where} {name} saved sizes: {fs.get('columnWidths')} {fs.get('rowHeights')} != "
                             f"{os_['columnWidths']} {os_['rowHeights']}")
            if ("Invalid" in fo.get("state", [])) != oo["invalid"]:
                diffs.append(f"{where} {name}: FreeCAD state {fo.get('state')}, ours invalid={oo['invalid']}")
    return diffs


def same(a, b):
    if isinstance(a, float) and isinstance(b, float):
        return math.isclose(a, b, rel_tol=1e-12, abs_tol=0) or a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b


# Known differences (ui/PARITY.md, "Spreadsheet workbench"): the only lines a case may differ in, and why.
KNOWN = {
    # FreeCAD does not recompute an object whose expression reads a cell by its alias when the cell changes (the alias
    # is not the property that changed): the Pad keeps 7.5 mm until something else touches it, even after a reopen.
    # Ours recomputes it, as FreeCAD does for the same binding by address (pad_expression).
    "pad": ("plate.",),
    # Two sheets reading each other: FreeCAD logs "The graph must be a DAG" and recomputes one of them; which one is not
    # something its code decides on purpose. Ours runs both in document order and reports the cycle.
    "sheet_cycle": ("Spreadsheet",),
}


@pytest.mark.parametrize("case", list(cases_mod.CASES))
def test_case_as_freecad(case):
    assert case in FC, "run tests/golden/spreadsheet/make.py in freecadcmd"
    ours = replay(case, cases_mod.CASES[case])
    diffs = compare(FC[case], ours)
    if case in KNOWN:
        diffs = [d for d in diffs if not any(f" {k}" in d for k in KNOWN[case])]
    assert not diffs, "\n".join(diffs[:40])


def test_a_pad_follows_the_cell_through_its_alias():
    """The known difference above: ours gives the Pad the cell's new value at each recompute."""
    ours = replay("pad", cases_mod.CASES["pad"])
    lengths = [s["objects"]["plate"]["length"] for s in ours if "objects" in s]
    assert lengths == [7.5, 4.0, 20.0, 20.0]

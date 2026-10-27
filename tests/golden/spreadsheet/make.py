"""Writes freecad.json: what FreeCAD's Spreadsheet makes of each case of cases.py, for tests/test_spreadsheet_golden.py to
hold cad_agent/spreadsheet_sheet.py and spreadsheet_doc.py to.

    $FREECAD/freecadcmd tests/golden/spreadsheet/make.py [CASE ...]     (FreeCAD 26.3 at 3160daf1e2b6)

Run it from the repository's root. Each case gets a fresh document "T"; its steps are cases.py's (Sheet methods as the GUI's
commands call them, recomputes, a save and reopen). Recorded after each recompute and reopen: every object's State and
the recompute's return, and for each sheet every used cell's content (getContents), its property's TypeId and value
(get, "ERR: ..." for a cell whose evaluation failed), alias, style, alignment, colours, display unit and spans, the
column widths and row heights, the used and non-empty ranges; for a part, the Pad's Length and the solid's volume. A
step that raises records the exception's class and message.
"""
import importlib.util
import json
import math
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(os.getcwd())
HERE = ROOT / "tests" / "golden" / "spreadsheet"
spec = importlib.util.spec_from_file_location("spreadsheet_cases", HERE / "cases.py")
cases_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cases_mod)

import FreeCAD as App  # noqa: E402
import Part  # noqa: E402

V = App.Vector


def val(v):
    if v is None or isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, float):
        return v if math.isfinite(v) else repr(v)
    if hasattr(v, "Value") and hasattr(v, "Unit"):
        return {"q": v.Value if math.isfinite(v.Value) else repr(v.Value), "unit": list(v.Unit.Signature), "s": str(v)}
    if isinstance(v, (list, tuple)):
        return {"seq": type(v).__name__, "items": [val(x) for x in v], "s": str(v)}
    if isinstance(v, set):
        return sorted(v)
    return {"obj": type(v).__name__, "s": str(v)}


def sheet_state(s):
    cells = {}
    for a in s.getUsedCells():
        d = {"content": s.getContents(a)}
        try:
            d["type"] = s.getTypeIdOfProperty(a) if a in s.PropertiesList else None
        except Exception:
            d["type"] = None
        try:
            d["value"] = val(s.get(a))
        except Exception as e:
            d["get_error"] = str(e)
        for k, f in (("alias", s.getAlias), ("style", s.getStyle), ("alignment", s.getAlignment),
                     ("foreground", s.getForeground), ("background", s.getBackground), ("display_unit", s.getDisplayUnit)):
            r = f(a)
            if r is not None:
                d[k] = val(r) if not isinstance(r, tuple) else [round(x, 6) for x in r]
        cells[a] = d
    widths = {}
    heights = {}
    for c in [chr(65 + i) for i in range(26)]:
        w = s.getColumnWidth(c)
        if w != 100:
            widths[c] = w
    for r in range(1, 80):
        h = s.getRowHeight(str(r))
        if h != 30:
            heights[str(r)] = h
    return {"label": s.Label, "cells": cells, "column_widths": widths, "row_heights": heights,
            "used_range": list(s.getUsedRange()) if s.getUsedRange() else None, "state": list(s.State)}


def saved_cells(doc, tmp):
    """Each sheet's <Cells> as the document saves them: [[address, {attribute: value}], ...] and the column widths and
    row heights saved."""
    import xml.etree.ElementTree as ET
    import zipfile
    path = os.path.join(tmp, "_snapshot.FCStd")
    doc.saveCopy(path)
    root = ET.fromstring(zipfile.ZipFile(path).read("Document.xml"))
    out = {}
    for obj in root.iter("Object"):
        name = obj.get("name")
        for prop in obj.iter("Property"):
            if prop.get("name") == "cells":
                cells = prop.find("Cells")
                out.setdefault(name, {})["cells"] = [[c.get("address"), {k: v for k, v in c.attrib.items() if k != "address"}]
                                                     for c in cells.iter("Cell")]
            elif prop.get("name") in ("columnWidths", "rowHeights"):
                el = prop[0]
                out.setdefault(name, {})[prop.get("name")] = {c.get("name"): int(c.get("width") or c.get("height") or 0)
                                                              for c in el}
    return out


def make_part(doc, name, params, expressions):
    """A Body: a 40 x 20 rectangle on XY padded by Length; PARAMS["length"] is the Pad's Length (the part's parameter),
    bound by EXPRESSIONS as the part binds it."""
    holder = doc.addObject("App::FeaturePython", name)
    body = doc.addObject("PartDesign::Body", name + "_Body")
    sk = body.newObject("Sketcher::SketchObject", name + "_Sketch")
    sk.AttachmentSupport = [(body.Origin.OriginFeatures[3], "")]
    sk.MapMode = "FlatFace"
    pts = [V(0, 0, 0), V(40, 0, 0), V(40, 20, 0), V(0, 20, 0)]
    for i in range(4):
        sk.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 4]))
    pad = body.newObject("PartDesign::Pad", name + "_Pad")
    pad.Profile = sk
    holder.addProperty("App::PropertyLength", "length", "Params")
    holder.length = params["length"]
    if "length" in expressions:
        holder.setExpression("length", expressions["length"])
    pad.setExpression("Length", name + ".length")
    return holder


def run_case(name, steps, tmp):
    doc = App.newDocument("T")
    out = []
    parts = {}

    def snapshot(what, ret=None):
        objs = {}
        saved = saved_cells(doc, tmp)
        for o in doc.Objects:
            if o.TypeId == "Spreadsheet::Sheet":
                objs[o.Name] = sheet_state(o)
                objs[o.Name]["saved"] = saved.get(o.Name)
        for pn, body in parts.items():
            pad = doc.getObject(pn + "_Pad")
            objs[pn] = {"length": body.length.Value, "pad_length": pad.Length.Value,
                        "volume": round(pad.Shape.Volume, 6) if not pad.Shape.isNull() else None,
                        "state": list(body.State), "expressions": dict(body.ExpressionEngine)}
        out.append({"step": what, "return": ret, "objects": objs})

    for i, st in enumerate(steps):
        try:
            if st[0] == "@sheet":
                s = doc.addObject("Spreadsheet::Sheet", st[1])
                if len(st) > 2:
                    s.Label = st[2]
            elif st[0] == "@recompute":
                snapshot("recompute", doc.recompute())
            elif st[0] == "@restore":
                path = os.path.join(tmp, f"{name}.FCStd")
                doc.saveAs(path)
                App.closeDocument(doc.Name)
                doc = App.openDocument(path)
                for pn in list(parts):
                    parts[pn] = doc.getObject(pn)
                snapshot("restore", doc.recompute())
            elif st[0] == "@part":
                parts[st[1]] = make_part(doc, st[1], st[2], st[3])
            elif st[0] == "@bind":
                parts[st[1]].setExpression(st[2], st[3])
                out.append({"step": "bind", "ok": True})
            elif st[0] == "@export":
                path = os.path.join(tmp, f"{name}.csv")
                doc.getObject(st[1]).exportFile(path)
                out.append({"step": "export", "text": open(path, encoding="utf-8").read()})
            elif st[0] == "@import":
                path = os.path.join(tmp, f"{name}_in.csv")
                open(path, "w", encoding="utf-8").write(st[2])
                out.append({"step": "import", "ok": doc.getObject(st[1]).importFile(path)})
            else:
                obj = doc.getObject(st[0])
                getattr(obj, st[1])(*st[2:])
        except Exception as e:
            out.append({"step": i, "error": type(e).__name__, "message": str(e)})
    App.closeDocument(doc.Name)
    return out


def main():
    want = sys.argv[1:] if len(sys.argv) > 1 and not sys.argv[-1].endswith(".py") else []
    want = [a for a in want if a in cases_mod.CASES]
    path = HERE / "freecad.json"
    res = json.loads(path.read_text()) if path.exists() and want else {}
    with tempfile.TemporaryDirectory() as tmp:
        for name, steps in cases_mod.CASES.items():
            if want and name not in want:
                continue
            res[name] = run_case(name, steps, tmp)
    res = {k: res[k] for k in cases_mod.CASES if k in res}
    path.write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n")
    print(f"make.py: wrote {path} ({len(res)} cases)")


main()

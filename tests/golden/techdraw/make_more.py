"""Writes more.json: what FreeCAD's App side does with the leader line, symbol, weld, clip and image objects, for
tests/test_techdraw_more.py to hold cad_agent/techdraw_objs.py and techdraw_more.py to.

    $FREECAD/freecadcmd tests/golden/techdraw/make_more.py     (from the repository's root)

Recorded (inputs: more_cases.py): the properties DrawLeaderLine.makeLeader gives a leader line (X, Y, WayPoints, symbols, the
defaults of its other properties); a DrawViewSymbol's EditableTexts for an SVG with editable fields, and its Symbol after
EditableTexts is set; what DrawViewClip.addView does to a view's X and Y; a DrawWeldSymbol's tiles (names, labels, rows, symbol
files and what is embedded); a DrawViewImage's ImageIncluded; every new type's properties in a fresh document (TypeId, group,
default, editor mode) as ui/scripts/fctechdraw_more_types.py reads them.
"""
import importlib.util
import json
import os
import tempfile
from pathlib import Path

import FreeCAD as App
import Part
import TechDraw

HERE = Path(os.getcwd()) / "tests" / "golden" / "techdraw"
V = App.Vector
RES = Path(App.getResourceDir()) / "Mod" / "TechDraw"
spec = importlib.util.spec_from_file_location("techdraw_more_cases", HERE / "more_cases.py")
cases = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cases)


def val(v):
    if isinstance(v, App.Vector):
        return [v.x, v.y, v.z]
    if hasattr(v, "Value") and hasattr(v, "Unit"):
        return v.Value
    if isinstance(v, (list, tuple)):
        return [val(x) for x in v]
    if hasattr(v, "Name"):
        return v.Name
    if isinstance(v, str):   # no machine's paths in the golden: FreeCAD's resources and its document cache by name
        return v.replace(App.getResourceDir().rstrip("/"), "<resources>").replace(App.getUserCachePath().rstrip("/"), "<cache>")
    if isinstance(v, (bool, int, float, type(None))):
        return v
    return repr(v)


def props(o, skip=("Proxy", "ExpressionEngine", "Shape", "Visibility", "Placement", "Label2")):
    out = {}
    for p in o.PropertiesList:
        if p in skip:
            continue
        try:
            out[p] = val(getattr(o, p))
        except Exception as e:
            out[p] = f"<{e}>"
    return out


def new_page(doc):
    page = doc.addObject("TechDraw::DrawPage", "Page")
    t = doc.addObject("TechDraw::DrawSVGTemplate", "Template")
    t.Template = str(RES / "Templates" / "Default_Template_A4_Landscape.svg")
    page.Template = t
    return page


def main():
    out = {"freecad": App.Version()[:4], "leaders": [], "symbol": {}, "clip": [], "welds": {}, "image": {}}
    plate = Part.read(str(HERE / "breps" / "plate.brep"))
    for c in cases.LEADERS:
        doc = App.newDocument("golden")
        f = doc.addObject("Part::Feature", "plate")
        f.Shape = plate
        page = new_page(doc)
        v = doc.addObject("TechDraw::DrawViewPart", "View")
        page.addView(v)
        v.Source = [f]
        v.Direction = V(0, 0, 1)
        v.XDirection = V(1, 0, 0)
        v.X, v.Y = c["view"]["x"], c["view"]["y"]
        doc.recompute()
        ll = TechDraw.makeLeader(v, [V(*p, 0) for p in c["points"]], c["start"], c["end"])
        doc.recompute()
        out["leaders"].append({"case": c["name"], "props": props(ll)})
        App.closeDocument(doc.Name)

    doc = App.newDocument("golden")
    page = new_page(doc)
    s = doc.addObject("TechDraw::DrawViewSymbol", "Symbol")
    page.addView(s)
    s.Symbol = cases.EDITABLE_SVG
    out["symbol"]["editable_after_symbol"] = list(s.EditableTexts)
    s.EditableTexts = cases.EDITED
    out["symbol"]["symbol_after_edit"] = s.Symbol
    out["symbol"]["editable_after_edit"] = list(s.EditableTexts)
    plain = doc.addObject("TechDraw::DrawViewSymbol", "Symbol001")
    page.addView(plain)
    plain.Symbol = (RES / "Symbols" / "misc" / "North.svg").read_text(encoding="utf-8")
    out["symbol"]["north_editable"] = list(plain.EditableTexts)
    # every shipped symbol rewritten by updateFieldsInSymbol (QDomDocument::toString(1)): the serialiser is held to FreeCAD's
    rewritten = {}
    for f in sorted((RES / "Symbols").rglob("*.svg")):
        o = doc.addObject("TechDraw::DrawViewSymbol", "S")
        o.Symbol = f.read_text(encoding="utf-8")
        editable = list(o.EditableTexts)
        o.EditableTexts = ["T%d" % i for i in range(max(len(editable), 1))]
        rewritten[str(f.relative_to(RES / "Symbols"))] = {"editable": editable, "symbol": o.Symbol}
        doc.removeObject(o.Name)
    out["symbol"]["rewritten"] = rewritten
    App.closeDocument(doc.Name)

    for k in cases.CLIP_VIEWS:
        doc = App.newDocument("golden")
        page = new_page(doc)
        clip = doc.addObject("TechDraw::DrawViewClip", "Clip")
        page.addView(clip)
        v = doc.addObject("TechDraw::" + k["kind"], "ClipView")
        page.addView(v)
        v.X, v.Y = k["x"], k["y"]
        if "text" in k:
            v.Text = k["text"]
        doc.recompute()
        clip.addView(v)
        doc.recompute()
        out["clip"].append({"case": k, "clip_x": clip.X.Value, "clip_y": clip.Y.Value, "view_x": v.X.Value, "view_y": v.Y.Value,
                            "views": [x.Name for x in clip.Views]})
        App.closeDocument(doc.Name)

    doc = App.newDocument("golden")
    page = new_page(doc)
    ll = doc.addObject("TechDraw::DrawLeaderLine", "LeaderLine")
    page.addView(ll)
    ws = doc.addObject("TechDraw::DrawWeldSymbol", "WeldSymbol")
    page.addView(ws)
    ws.Leader = ll
    out["welds"]["objects"] = [o.Name for o in doc.Objects]
    out["welds"]["tiles"] = [props(doc.getObject(n)) for n in ("TileWeld", "TileWeld001")]
    out["welds"]["weld"] = props(ws)
    for i, f in enumerate(cases.WELD_SYMBOL_FILES):
        t = doc.getObject("TileWeld")
        t.SymbolFile = str(RES / "Symbols" / f)
        out["welds"].setdefault("symbol_file", []).append({"file": f, "SymbolFile": t.SymbolFile.split("/Mod/TechDraw/")[-1],
                                                           "SymbolIncluded": os.path.basename(t.SymbolIncluded)})
    App.closeDocument(doc.Name)

    doc = App.newDocument("golden")
    page = new_page(doc)
    im = doc.addObject("TechDraw::DrawViewImage", "Image")
    page.addView(im)
    png = Path(tempfile.mkdtemp()) / "pixel.png"
    png.write_bytes(bytes.fromhex("89504e470d0a1a0a0000000d49484452000000020000000108060000009a3e6f5d0000000d49444154789c6360f8cf00"
                                  "000401010000b8f7c16d0000000049454e44ae426082"))
    im.ImageFile = str(png)
    out["image"] = {"before": props(im), "included": os.path.basename(im.ImageIncluded)}
    App.closeDocument(doc.Name)
    (HERE / "more.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print("make_more: ok")


main()

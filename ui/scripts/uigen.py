#!/usr/bin/env python3
"""Generates ui/src/uiforms.ts: the Preferences pages' layouts, as FreeCAD's Qt Designer files define them, plus what the real FreeCAD shows.

    python3 ui/scripts/fcprefs.py OUT_DIR                          # the real FreeCAD, once: OUT_DIR/fcprefs.json
    python3 ui/scripts/uigen.py OUT_DIR/fcprefs.json [ui/src/uiforms.ts]

Each page's .ui at 3160daf1e2b6 (fetched once into ~/.cad-agent/freecad/ui-3160daf1e2b6/, as prefdiff.py does) is read as uic would:
the widgets with their text, tool tips, ranges, suffixes, size policies and minimum and maximum sizes, and the layouts (grids with their
rows, columns and spans, boxes, spacers, margins, spacing, stretch). fcprefs.json adds, per widget, what FreeCAD itself shows in a fresh
profile once the page's code has run (the values a settings page loads, the items its code puts in a combo box, the widgets it hides) and
the widget's size hint (QWidget::sizeHint, which Qt's layouts distribute the space from). src/qtform.tsx lays the result out the way Qt does;
the pages in src/prefs-pages.tsx bind the widgets that do something here, and the rest show these values, greyed out. The generated file is not
edited by hand: run this again after fcprefs.py.
"""
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

COMMIT = "3160daf1e2b6"
COMMIT_FULL = "3160daf1e2b62b0472854da4848255c6b3ad554c"
CACHE = Path.home() / ".cad-agent" / "freecad" / f"ui-{COMMIT}"
HERE = Path(__file__).resolve().parent
# page key (fcprefs_dump.py's) -> the .ui under src/Gui
PAGES = {
    "general": "PreferencePages/DlgSettingsGeneral.ui", "document": "PreferencePages/DlgSettingsDocument.ui",
    "selection": "PreferencePages/DlgSettingsSelection.ui", "keyboard": "Dialogs/DlgKeyboard.ui",
    "cache": "PreferencePages/DlgSettingsCacheDirectory.ui", "notificationarea": "PreferencePages/DlgSettingsNotificationArea.ui",
    "reportview": "PreferencePages/DlgSettingsReportView.ui", "3dview": "PreferencePages/DlgSettings3DView.ui",
    "lightsources": "PreferencePages/DlgSettingsLightSources.ui", "ui": "PreferencePages/DlgSettingsUI.ui",
    "navigation": "PreferencePages/DlgSettingsNavigation.ui", "colors": "PreferencePages/DlgSettingsViewColor.ui",
    "workbenches": "PreferencePages/DlgSettingsWorkbenches.ui", "pdf": "PreferencePages/DlgSettingsPDF.ui",
    "macro": "PreferencePages/DlgSettingsMacro.ui", "pythongeneral": "PreferencePages/DlgSettingsPythonConsole.ui",
    "editor": "PreferencePages/DlgSettingsEditor.ui",
}
# --sketcher: the Sketcher's pages (src/Mod/Sketcher/Gui), written to src/uiforms-sketcher.ts as SKETCHER_FORMS
SKETCHER_PAGES = {
    "sketcher": "src/Mod/Sketcher/Gui/SketcherSettings.ui", "sketchergrid": "src/Mod/Sketcher/Gui/SketcherSettingsGrid.ui",
    "sketcherdisplay": "src/Mod/Sketcher/Gui/SketcherSettingsDisplay.ui", "sketcherappearance": "src/Mod/Sketcher/Gui/SketcherSettingsAppearance.ui",
}
# --techdraw: TechDraw's task panels (src/Mod/TechDraw/Gui), written to src/uiforms-techdraw.ts as TECHDRAW_FORMS (no dump: the
# panels' code fills them, src/techdraw_tasks.tsx)
TECHDRAW_PAGES = {
    "projgroup": "src/Mod/TechDraw/Gui/TaskProjGroup.ui", "section": "src/Mod/TechDraw/Gui/TaskSectionView.ui",
    "dimension": "src/Mod/TechDraw/Gui/TaskDimension.ui", "balloon": "src/Mod/TechDraw/Gui/TaskBalloon.ui",
    "cosvertex": "src/Mod/TechDraw/Gui/TaskCosVertex.ui", "cosline": "src/Mod/TechDraw/Gui/TaskCosmeticLine.ui",
    "coscircle": "src/Mod/TechDraw/Gui/TaskCosmeticCircle.ui", "centerline": "src/Mod/TechDraw/Gui/TaskCenterLine.ui",
    "linedecor": "src/Mod/TechDraw/Gui/TaskLineDecor.ui", "restorelines": "src/Mod/TechDraw/Gui/TaskRestoreLines.ui",
    "hatch": "src/Mod/TechDraw/Gui/TaskHatch.ui", "geomhatch": "src/Mod/TechDraw/Gui/TaskGeomHatch.ui",
    "leader": "src/Mod/TechDraw/Gui/TaskLeaderLine.ui", "richanno": "src/Mod/TechDraw/Gui/TaskRichAnno.ui",
    "weld": "src/Mod/TechDraw/Gui/TaskWeldingSymbol.ui", "symbolchooser": "src/Mod/TechDraw/Gui/SymbolChooser.ui",
    "surface": "src/Mod/TechDraw/Gui/TaskSurfaceFinishSymbols.ui",
}
# the properties the renderer reads; every other property of a .ui (geometry, focus policy, drag and drop modes, ...) has no effect on the layout
KEEP = {"text", "title", "toolTip", "checkable", "checked", "enabled", "flat", "value", "minimum", "maximum", "singleStep", "decimals", "suffix",
        "prefix", "specialValueText", "alignment", "wordWrap", "textFormat", "openExternalLinks", "font", "minimumSize", "maximumSize", "sizePolicy",
        "color", "currentIndex", "editable", "readOnly", "placeholderText", "prefEntry", "prefPath", "unit", "rawValue", "icon", "buddy", "shortcut",
        "frameShape", "orientation", "iconSize", "alternatingRowColors", "rootIsDecorated", "sortingEnabled", "maxLength", "mode", "fileName",
        "visible", "title", "standardButtons", "inputMethodHints", "margin", "indent"}
POLICY = {"Preferred": "P", "Fixed": "F", "Minimum": "m", "Maximum": "M", "Expanding": "E", "MinimumExpanding": "X", "Ignored": "I"}
TEXT_KEYS = {"text", "title", "toolTip", "suffix", "prefix", "specialValueText", "placeholderText"}


def source(path: str) -> str:
    f = CACHE / Path(path).name
    if not f.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        host = "raw.github" + "usercontent.com"
        full = path if path.startswith("src/") else f"src/Gui/{path}"
        f.write_bytes(urllib.request.urlopen(f"https://{host}/FreeCAD/FreeCAD/{COMMIT_FULL}/{full}", timeout=30).read())
    return f.read_text()


def last(s: str) -> str:
    return s.split("::")[-1]


def value(prop: ET.Element):
    for ch in prop:
        t = ch.tag
        if t in ("string", "cstring"):
            return ch.text or ""
        if t == "number":
            return int(ch.text)
        if t == "double":
            return float(ch.text)
        if t == "bool":
            return ch.text == "true"
        if t == "enum":
            return last(ch.text or "")
        if t == "set":
            return [last(x) for x in (ch.text or "").split("|")]
        if t == "size":
            return [int(ch.find("width").text), int(ch.find("height").text)]
        if t == "sizepolicy":
            return [ch.get("hsizetype"), ch.get("vsizetype"), int(ch.findtext("horstretch") or 0), int(ch.findtext("verstretch") or 0)]
        if t == "font":
            f = {}
            if ch.findtext("pointsize"):
                f["pt"] = int(ch.findtext("pointsize"))
            if ch.findtext("bold") == "true":
                f["b"] = 1
            if ch.findtext("italic") == "true":
                f["i"] = 1
            return f
        if t == "color":
            return [int(ch.get("alpha", "255")), int(ch.findtext("red")), int(ch.findtext("green")), int(ch.findtext("blue"))]
        if t == "iconset":
            return ch.get("theme") or (ch.findtext("normaloff") or "")
    return None


def prop_name(p: ET.Element) -> str:
    return p.get("name")


def walk_widget(el: ET.Element) -> dict:
    d: dict = {"c": el.get("class"), "n": el.get("name")}
    props, items, cols = {}, [], []
    for ch in el:
        if ch.tag in ("property", "attribute"):
            name = prop_name(ch)
            if name in KEEP:
                v = value(ch)
                if v is not None:
                    props[name] = v
        elif ch.tag == "layout":
            d["l"] = walk_layout(ch)
        elif ch.tag == "widget":
            d.setdefault("ch", []).append(walk_widget(ch))
        elif ch.tag == "item":
            p = ch.find("property")
            items.append(value(p) if p is not None else "")
        elif ch.tag == "column":
            p = ch.find("property")
            cols.append(value(p) if p is not None else "")
    if props:
        d["p"] = props
    if items:
        d["items"] = items
    if cols:
        d["cols"] = cols
    return d


def ints(s):
    return [int(x) for x in s.split(",")] if s else None


def walk_layout(el: ET.Element) -> dict:
    d: dict = {"t": {"QVBoxLayout": "V", "QHBoxLayout": "H", "QGridLayout": "G"}[el.get("class")], "i": []}
    if el.get("name"):
        d["n"] = el.get("name")
    margins = {}
    for ch in el:
        if ch.tag == "property":
            name = prop_name(ch)
            if name in ("leftMargin", "topMargin", "rightMargin", "bottomMargin"):
                margins[name] = value(ch)
            elif name == "spacing":
                d["sp"] = value(ch)
            elif name == "horizontalSpacing":
                d["hsp"] = value(ch)
            elif name == "verticalSpacing":
                d["vsp"] = value(ch)
        elif ch.tag == "item":
            it: dict = {}
            for k, short in (("row", "r"), ("column", "c"), ("rowspan", "rs"), ("colspan", "cs")):
                if ch.get(k) is not None:
                    it[short] = int(ch.get(k))
            if ch.get("alignment"):
                it["a"] = [last(x) for x in ch.get("alignment").split("|")]
            for sub in ch:
                if sub.tag == "widget":
                    it["w"] = walk_widget(sub)
                elif sub.tag == "layout":
                    it["l"] = walk_layout(sub)
                elif sub.tag == "spacer":
                    sp = {"o": "h" if "Horizontal" in (sub.findtext("property/enum") or "Horizontal") else "v", "t": "Expanding", "w": 0, "h": 0}
                    for pr in sub.findall("property"):
                        if prop_name(pr) == "sizeType":
                            sp["t"] = value(pr).split("::")[-1]
                        elif prop_name(pr) == "sizeHint":
                            sp["w"], sp["h"] = value(pr)
                        elif prop_name(pr) == "orientation":
                            sp["o"] = "h" if value(pr) == "Horizontal" else "v"
                    it["s"] = sp
            d["i"].append(it)
    if margins:
        d["m"] = [margins.get(k) for k in ("leftMargin", "topMargin", "rightMargin", "bottomMargin")]
    for attr, key in (("stretch", "st"), ("rowstretch", "rst"), ("columnstretch", "cst"), ("rowminimumheight", "rmin"), ("columnminimumwidth", "cmin")):
        if el.get(attr):
            d[key] = ints(el.get(attr))
    return d


def fc_state(w: dict) -> dict:
    """What the real FreeCAD shows for a widget, from fcprefs_dump.py's dump: the hint and the state of a fresh profile."""
    out: dict = {"h": w["hint"], "pol": "".join(POLICY[x] for x in w["policy"][:2])}
    if w["policy"][2] or w["policy"][3]:
        out["stretch"] = w["policy"][2:]
    cls = w["cls"]
    if "checked" in w and (w.get("checkable") or "checkable" not in w):
        out["chk"] = bool(w["checked"])
    if w.get("color"):
        out["col"] = w["color"]
    if "currentText" in w:
        out["ct"] = w["currentText"]
        out["ci"] = w["currentIndex"]
        if w["count"] <= 60:
            out["it"] = w["items"]
    if "value" in w and "text" in w:                       # a spin box
        out["v"] = w["value"]
        out["t"] = w["text"]
    elif cls in ("QLabel", "QPushButton", "QCheckBox", "QRadioButton", "QToolButton", "Gui::PrefCheckBox", "Gui::PrefRadioButton") and w.get("text") is not None:
        out["t"] = w["text"]
    elif "text" in w and cls.endswith("LineEdit") or cls == "QLineEdit":
        t = w.get("text", "")
        if not re.search(r"/(Users|private|var|tmp|home)/", t):
            out["t"] = t
    if w.get("placeholder"):                              # what an empty line edit says in grey (the code sets it, or the .ui)
        out["ph"] = w["placeholder"]
    if "headers" in w:
        out["hd"] = w["headers"]
    if "cells" in w and w["cells"]:
        out["rows"] = w["cells"]
    if not w["enabled"]:
        out["dis"] = 1
    if not w["visible"]:
        out["hid"] = 1
    return out


def attach(form: dict, widgets: dict) -> None:
    def go(w: dict):
        st = widgets.get(w["n"])
        if st:
            w["fc"] = fc_state(st)
        if "l" in w:
            lay(w["l"])
        for c in w.get("ch", []):
            go(c)

    def lay(l: dict):
        for it in l["i"]:
            if "w" in it:
                go(it["w"])
            if "l" in it:
                lay(it["l"])

    go(form["root"])


def compact(o, depth=0) -> str:
    """JSON with one widget or layout item per line: readable diffs for a file of a few hundred kB."""
    if isinstance(o, dict):
        inner = ",".join(f"{json.dumps(k)}:{compact(v, depth + 1)}" for k, v in o.items())
        return "{" + inner + "}"
    if isinstance(o, list):
        if o and all(isinstance(x, dict) for x in o) and depth < 12:
            pad = "\n" + " " * (depth + 1)
            return "[" + pad.join([""] + [compact(x, depth + 1) + "," for x in o]).rstrip(",") + "\n" + " " * depth + "]"
        return "[" + ",".join(compact(x, depth + 1) for x in o) + "]"
    return json.dumps(o, ensure_ascii=False)


def main() -> int:
    if "--techdraw" in sys.argv:
        return main_techdraw([a for a in sys.argv[1:] if a != "--techdraw"])
    args = [a for a in sys.argv[1:] if a != "--sketcher"]
    if len(args) < len(sys.argv) - 1:
        return main_sketcher(args)
    dump_path = Path(args[0])
    out_path = Path(args[1]) if len(args) > 1 else HERE.parent / "src" / "uiforms.ts"
    dump = json.loads(dump_path.read_text())
    forms = {}
    for key, rel in PAGES.items():
        root = ET.fromstring(source(rel))
        top = root.find("widget")
        form = {"title": top.findtext("property[@name='windowTitle']/string") or "", "root": walk_widget(top)}
        ld = root.find("layoutdefault")
        if ld is not None:
            form["ld"] = [int(ld.get("spacing", "6")), int(ld.get("margin", "11"))]
        page = dump["pages"].get(key)
        if page:
            attach(form, {w["name"]: w for w in page["widgets"] if w["name"]})
            form["fc"] = {"min": page["minSizeHint"], "hint": page["sizeHint"], "title": page["pageTitle"]}
        forms[key] = form
    files = [f"src/Gui/{rel}" for rel in PAGES.values()]
    names = (",\n//       ").join(", ".join(files[i:i + 2]) for i in range(0, len(files), 2))
    head = f"""// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit {COMMIT}), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   No copyright line in the file: {names}
// GENERATED by ui/scripts/uigen.py: do not edit. The pages of FreeCAD's Preferences dialog that the workbench has, as the Qt Designer
// files above lay them out (widgets with their text, tool tips, ranges and size policies; layouts with their rows, columns, spans,
// margins, spacing and spacers), with, under "fc", what the real FreeCAD 26.3 shows for the widget in a fresh profile (the values the
// page's code loads, the items it puts in a combo box, whether it hides or disables the widget) and its size hint, as
// ui/scripts/fcprefs.py measured them. src/qtform.tsx draws these; src/prefs-pages.tsx binds the widgets that do something here.
"""
    body = "export const FORMS: Record<string, UiForm> = {\n"
    for key, form in forms.items():
        body += f" {json.dumps(key)}: {compact(form, 1)},\n"
    body += "}\n"
    # the Keyboard page's categories, as the real FreeCAD's Category box lists them, and the category each command is in
    cats = (dump["pages"].get("keyboard") or {}).get("extras", {}).get("categories", {})
    if cats:
        order = [c for c in cats if c]
        body += "\n/** The categories of the Keyboard page's Category box in FreeCAD 26.3, in its order, and the category of each command it lists. */\n"
        body += f"export const KEYBOARD_CATEGORIES: string[] = {json.dumps(order, ensure_ascii=False)}\n"
        body += "export const COMMAND_CATEGORY: Record<string, string> = {\n"
        for c in order:
            names = [r["name"] for r in cats[c]["rows"] if r["name"]] if c != "All" else []
            for i in range(0, len(names), 3):
                body += "  " + ", ".join(f"{json.dumps(n)}: {json.dumps(c)}" for n in names[i:i + 3]) + ",\n"
        body += "}\n"
    types = """
/** A widget of a Qt Designer form: class, object name, properties (Qt's names), the layout it holds, child widgets without one, the items
 *  of a combo box, list or menu, the columns of a table, and what the real FreeCAD shows for it (`fc`). */
export interface UiWidget {
  c: string; n: string; p?: Record<string, unknown>; l?: UiLayout; ch?: UiWidget[]; items?: unknown[]; cols?: unknown[]; fc?: UiState
}
/** A box or grid layout: V, H or G; margins (left, top, right, bottom; null where the .ui sets none), spacing, stretch factors and its items. */
export interface UiLayout {
  t: 'V' | 'H' | 'G'; n?: string; m?: (number | null)[]; sp?: number; hsp?: number; vsp?: number; st?: number[]; rst?: number[]; cst?: number[]
  rmin?: number[]; cmin?: number[]; i: UiItem[]
}
/** One cell or slot of a layout: grid position and spans, alignment, and a widget, a nested layout or a spacer. */
export interface UiItem { r?: number; c?: number; rs?: number; cs?: number; a?: string[]; w?: UiWidget; l?: UiLayout; s?: UiSpacer }
export interface UiSpacer { o: 'h' | 'v'; t: string; w: number; h: number }
/** What FreeCAD shows in a fresh profile: h size hint, pol size policy (horizontal, vertical: P Preferred, F Fixed, m Minimum, M Maximum,
 *  E Expanding, X MinimumExpanding, I Ignored), stretch factors, chk checked, v value, t text, ct and ci current text and index, it combo items, ph placeholder text, col colour (ARGB),
 *  hd table headers, rows table cells, dis disabled, hid hidden. */
export interface UiState {
  h: [number, number]; pol: string; stretch?: [number, number]; chk?: boolean; v?: number; t?: string; ct?: string; ci?: number; it?: string[]; ph?: string; col?: string; hd?: string[]; rows?: (string | null)[][]; dis?: 1; hid?: 1
}
export interface UiForm { title: string; root: UiWidget; ld?: [number, number]; fc?: { min: [number, number]; hint: [number, number]; title: string } }
"""
    out_path.write_text(head + types + "\n" + body)
    print(f"uigen: {len(forms)} pages, {out_path.stat().st_size // 1024} kB -> {out_path}")
    return 0


def form_of(key: str, rel: str, dump: dict) -> dict:
    root = ET.fromstring(source(rel))
    top = root.find("widget")
    form = {"title": top.findtext("property[@name='windowTitle']/string") or "", "root": walk_widget(top)}
    ld = root.find("layoutdefault")
    if ld is not None:
        form["ld"] = [int(ld.get("spacing", "6")), int(ld.get("margin", "11"))]
    page = dump["pages"].get(key)
    if page:
        attach(form, {w["name"]: w for w in page["widgets"] if w["name"]})
        form["fc"] = {"min": page["minSizeHint"], "hint": page["sizeHint"], "title": page["pageTitle"]}
    return form


def main_sketcher(args: list) -> int:
    """uigen.py --sketcher OUT_DIR/fcprefs.json [ui/src/uiforms-sketcher.ts]: the Sketcher's pages (fcprefs.py --only sketcher,...)."""
    dump = json.loads(Path(args[0]).read_text())
    out_path = Path(args[1]) if len(args) > 1 else HERE.parent / "src" / "uiforms-sketcher.ts"
    forms = {key: form_of(key, rel, dump) for key, rel in SKETCHER_PAGES.items()}
    names = ", ".join(SKETCHER_PAGES.values())
    head = f"""// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit {COMMIT}), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   No copyright line in the file: {names}
// GENERATED by ui/scripts/uigen.py --sketcher: do not edit. The Sketcher's pages of FreeCAD's Preferences dialog, as uiforms.ts has
// the others: the Qt Designer files above with, under "fc", what the real FreeCAD 26.3 shows in a fresh profile (ui/scripts/fcprefs.py).
// src/prefs-sketcher.tsx binds the widgets that do something here.
import type {{ UiForm }} from './uiforms'
"""
    body = "export const SKETCHER_FORMS: Record<string, UiForm> = {\n"
    for key, form in forms.items():
        body += f" {json.dumps(key)}: {compact(form, 1)},\n"
    body += "}\n"
    out_path.write_text(head + "\n" + body)
    print(f"uigen: {len(forms)} pages, {out_path.stat().st_size // 1024} kB -> {out_path}")
    return 0


def main_techdraw(args: list) -> int:
    """uigen.py --techdraw [ui/src/uiforms-techdraw.ts]: TechDraw's task panels, from their .ui files alone."""
    out_path = Path(args[0]) if args else HERE.parent / "src" / "uiforms-techdraw.ts"
    forms = {key: form_of(key, rel, {"pages": {}}) for key, rel in TECHDRAW_PAGES.items()}
    names = ", ".join(TECHDRAW_PAGES.values())
    head = f"""// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit {COMMIT}), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   No copyright line in the file: {names}
// GENERATED by ui/scripts/uigen.py --techdraw: do not edit. TechDraw's task panels as the Qt Designer files above lay them out;
// src/techdraw_tasks.tsx binds their widgets as the panels' code (TaskProjGroup.cpp, TaskSectionView.cpp, TaskDimension.cpp,
// TaskBalloon.cpp, TaskCosVertex.cpp, TaskCosmeticLine.cpp, TaskCosmeticCircle.cpp, TaskCenterLine.cpp,
// TaskLineDecor.cpp, TaskHatch.cpp, TaskGeomHatch.cpp, TaskLeaderLine.cpp, TaskRichAnno.cpp, TaskWeldingSymbol.cpp, SymbolChooser.cpp,
// TaskSurfaceFinishSymbols.cpp) fills them.
import type {{ UiForm }} from './uiforms'
"""
    body = "export const TECHDRAW_FORMS: Record<string, UiForm> = {\n"
    for key, form in forms.items():
        body += f" {json.dumps(key)}: {compact(form, 1)},\n"
    body += "}\n"
    out_path.write_text(head + "\n" + body)
    print(f"uigen: {len(forms)} panels, {out_path.stat().st_size // 1024} kB -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# SPDX-License-Identifier: LGPL-2.1-or-later
# Runs inside FreeCAD's GUI (fcspreadsheet.py starts it under fclaunch, windows kept off the screen): what the real
# Spreadsheet workbench shows, for the page to be compared with. Writes fcspreadsheet.json into FCGUI_OUT:
#   menus_*, toolbars_*   the Spreadsheet menu and toolbar: no document, a sheet view with one cell, with a range selected
#   create                Spreadsheet_CreateSheet: the objects, the undo step, the MDI window, the tree
#   cells                 each cell of CELLS typed in (SheetModel::setData) and what the model gives for it: display,
#                         edit, tooltip, foreground, background, alignment and font
#   lines                 the Content and Alias line edits for a few current cells
#   commands              each alignment, style, merge and split command on a selection: the undo step and the cells
#   properties            the Properties dialog: its widgets, then changes applied (Set cell properties)
#   set_alias, alias_line, content_line   Spreadsheet_SetAlias's dialog; the Alias and Content line edits
#   copy_paste, cut_paste, delete         SheetTableView's Copy, Cut, Paste and Delete
#   headers               the row and column headers' context menus, and Insert / Remove Rows / Columns run
#   keys                  where Enter, Tab, Shift+Tab, the arrows, Home and End take the current cell
#   context_menu          the cell context menu's actions and which are enabled
#   props, tree, undo     the property view of the sheet, the tree, Std_Undo and Std_Redo
import json
import os
import time
import traceback

import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtCore, QtGui, QtWidgets

OUT = os.environ["FCGUI_OUT"]
mw = Gui.getMainWindow()
app = QtWidgets.QApplication.instance()
res = {"errors": {}}
mw.resize(1280, 800)
Qt = QtCore.Qt


def save():
    json.dump(res, open(os.path.join(OUT, "fcspreadsheet.json"), "w"), indent=1, ensure_ascii=False)


def bail():
    res["errors"]["hung"] = "stopped after 900 s"
    save()
    os._exit(0)


QtCore.QTimer.singleShot(900000, bail)


def pump(sec=0.3):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents(QtCore.QEventLoop.AllEvents, 50)
        time.sleep(0.005)


def safe(name, fn):
    try:
        res[name] = fn()
    except Exception:
        res["errors"][name] = traceback.format_exc()
    save()


def dump_menu(m, depth=0):
    try:
        m.aboutToShow.emit()
    except Exception:
        pass
    out = []
    for a in m.actions():
        if a.isSeparator():
            out.append({"sep": True})
            continue
        if not a.isVisible():
            continue
        d = {"text": a.text(), "name": a.objectName() or a.data(), "shortcut": a.shortcut().toString(),
             "enabled": a.isEnabled(), "tip": a.toolTip()}
        if a.menu() is not None and depth < 4:
            d["menu"] = dump_menu(a.menu(), depth + 1)
        out.append(d)
    return out


def menus():
    pump(0.3)
    out = {"bar": [a.text() for a in mw.menuBar().actions() if a.isVisible()]}
    for a in mw.menuBar().actions():
        if a.text().replace("&", "") in ("Spreadsheet", "Edit"):
            out[a.text()] = dump_menu(a.menu())
    return out


def toolbars():
    pump(0.3)
    out = []
    for tb in mw.findChildren(QtWidgets.QToolBar):
        if tb.windowTitle() != "Spreadsheet":
            continue
        row = {"title": tb.windowTitle(), "name": tb.objectName(), "visible": tb.isVisible(), "buttons": []}
        for a in tb.actions():
            if a.isSeparator():
                row["buttons"].append({"sep": True})
                continue
            if not a.isVisible():
                continue
            w = tb.widgetForAction(a)
            b = {"name": a.objectName() or "", "text": a.text(), "tip": a.toolTip(), "enabled": a.isEnabled(),
                 "widget": w.metaObject().className() if w is not None else None}
            if w is not None and w.metaObject().className() == "QtColorPicker":
                b.update(name=w.objectName(), tip=w.toolTip(), enabled=w.isEnabled())
            row["buttons"].append(b)
        out.append(row)
    return out


def table():
    found = [w for w in app.allWidgets() if w.metaObject().className() == "SpreadsheetGui::SheetTableView"]
    for w in found:
        if w.isVisible():
            return w
    return found[0] if found else None


def line(name):
    for w in mw.findChildren(QtWidgets.QLineEdit, name):
        return w
    return None


def color(c):
    if c is None:
        return None
    if isinstance(c, QtGui.QBrush):
        c = c.color()
    if not isinstance(c, QtGui.QColor):
        return str(c)
    return c.name() if c.alpha() == 255 else c.name() + f"{c.alpha():02x}"


ALIGN = [(Qt.AlignLeft, "left"), (Qt.AlignHCenter, "hcenter"), (Qt.AlignRight, "right"), (Qt.AlignTop, "top"),
         (Qt.AlignVCenter, "vcenter"), (Qt.AlignBottom, "bottom")]


def align(v):
    if v is None:
        return None
    try:
        n = int(v)
    except TypeError:
        n = v.value if hasattr(v, "value") else int(v)
    return [name for flag, name in ALIGN if n & int(flag.value if hasattr(flag, "value") else flag)]


def roles(model, r, c):
    i = model.index(r, c)
    d = {"display": model.data(i, Qt.DisplayRole), "edit": model.data(i, Qt.EditRole),
         "tooltip": model.data(i, Qt.ToolTipRole), "fg": color(model.data(i, Qt.ForegroundRole)),
         "bg": color(model.data(i, Qt.BackgroundRole)), "align": align(model.data(i, Qt.TextAlignmentRole))}
    f = model.data(i, Qt.FontRole)
    d["font"] = [] if f is None else [n for n, on in (("bold", f.bold()), ("italic", f.italic()),
                                                       ("underline", f.underline())) if on]
    for k in list(d):
        if not isinstance(d[k], (str, list, type(None), int, float, bool)):
            d[k] = str(d[k])
    return d


def addr(r, c):
    s = ""
    c0 = c
    if c0 < 26:
        s = chr(65 + c0)
    else:
        s = chr(65 + (c0 - 26) // 26) + chr(65 + (c0 - 26) % 26)
    return f"{s}{r + 1}"


def rc(a):
    col = 0
    i = 0
    while a[i].isalpha():
        col = col * 26 + (ord(a[i]) - 64)
        i += 1
    return int(a[i:]) - 1, col - 1


doc = None
sheet = None


def type_cell(a, text):
    tv = table()
    r, c = rc(a)
    tv.model().setData(tv.model().index(r, c), text, Qt.EditRole)
    pump(0.25)


def select(*ranges, current=None):
    tv = table()
    sm = tv.selectionModel()
    sm.clearSelection()
    first = None
    for rg in ranges:
        a, b = (rg.split(":") + [rg])[:2]
        (r1, c1), (r2, c2) = rc(a), rc(b)
        if first is None:
            first = (r1, c1)
        sel = QtCore.QItemSelection(tv.model().index(r1, c1), tv.model().index(r2, c2))
        sm.select(sel, QtCore.QItemSelectionModel.Select)
    cr = rc(current) if current else first
    sm.setCurrentIndex(tv.model().index(*cr), QtCore.QItemSelectionModel.NoUpdate)
    pump(0.3)


def undo_head(before):
    names = list(doc.UndoNames)
    n = len(names) - len(before)
    return names[:max(n, 0)] if n > 0 else []


def cell_state(a):
    d = {"content": sheet.getContents(a)}
    for k, f in (("alias", sheet.getAlias), ("style", sheet.getStyle), ("alignment", sheet.getAlignment),
                 ("foreground", sheet.getForeground), ("background", sheet.getBackground),
                 ("display_unit", sheet.getDisplayUnit)):
        r = f(a)
        if r is not None:
            d[k] = sorted(r) if isinstance(r, set) else ([round(x, 4) for x in r] if isinstance(r, tuple) else r)
    return d


def used():
    return {a: cell_state(a) for a in sheet.getUsedCells()}


def view_cells(rng):
    tv = table()
    a, b = rng.split(":")
    (r1, c1), (r2, c2) = rc(a), rc(b)
    return {addr(r, c): roles(tv.model(), r, c) for r in range(r1, r2 + 1) for c in range(c1, c2 + 1)}


def spans():
    tv = table()
    out = {}
    for a in sheet.getUsedCells():
        r, c = rc(a)
        if tv.rowSpan(r, c) > 1 or tv.columnSpan(r, c) > 1:
            out[a] = [tv.rowSpan(r, c), tv.columnSpan(r, c)]
    return out


def run(cmd):
    before = list(doc.UndoNames)
    Gui.runCommand(cmd, 0)
    pump(0.6)
    return undo_head(before)


def with_dialog(trigger, inspect):
    """Run trigger(); while the modal dialog it opens is up, inspect(dialog) (which closes it)."""
    got = {}

    def tick():
        for w in app.topLevelWidgets():
            if isinstance(w, QtWidgets.QDialog) and w.isVisible() and not got:
                got["seen"] = True
                try:
                    got.update(inspect(w))
                except Exception:
                    got["error"] = traceback.format_exc()
                    w.reject()
                return
        QtCore.QTimer.singleShot(150, tick)
    QtCore.QTimer.singleShot(300, tick)
    trigger()
    pump(0.6)
    return got


def dialog_widgets(d):
    out = []
    for w in d.findChildren(QtWidgets.QWidget):
        cls = w.metaObject().className()
        e = {"class": cls, "name": w.objectName(), "enabled": w.isEnabled(), "visible": w.isVisible()}
        if w.toolTip():
            e["tip"] = w.toolTip()
        if isinstance(w, QtWidgets.QAbstractButton):
            e["text"] = w.text()
            if w.isCheckable():
                e["checked"] = w.isChecked()
        elif isinstance(w, QtWidgets.QLabel):
            e["text"] = w.text()
        elif isinstance(w, QtWidgets.QLineEdit):
            e["text"] = w.text()
        elif isinstance(w, QtWidgets.QTabWidget):
            e["tabs"] = [w.tabText(i) for i in range(w.count())]
            e["current"] = w.currentIndex()
            e["tab_enabled"] = [w.widget(i).isEnabled() for i in range(w.count())]
        elif cls == "QtColorPicker":
            e["text"] = w.property("text") if w.property("text") is not None else None
        else:
            continue
        out.append(e)
    return {"title": d.windowTitle(), "widgets": out}


def menu_of(trigger, pick=None):
    """The QMenu trigger() pops up (QMenu::exec blocks): its actions, then closed (or the action `pick` triggered)."""
    got = {}
    old = {id(w) for w in app.topLevelWidgets() if isinstance(w, QtWidgets.QMenu) and w.isVisible()}

    def tick():
        for w in app.topLevelWidgets():
            if isinstance(w, QtWidgets.QMenu) and w.isVisible() and id(w) not in old and not got:
                got["actions"] = [{"text": a.text(), "enabled": a.isEnabled()} if not a.isSeparator() else {"sep": True}
                                  for a in w.actions()]
                if pick is not None:
                    a = [x for x in w.actions() if not x.isSeparator()][pick]
                    w.close()
                    a.trigger()
                else:
                    w.close()
                return
        QtCore.QTimer.singleShot(100, tick)
    QtCore.QTimer.singleShot(200, tick)
    trigger()
    pump(0.6)
    return got


CELLS = {
    # values of each kind, as the model shows them with the default preferences
    "A1": "5", "A2": "-3", "A3": "2.5", "A4": "-2.5", "A5": "1/3", "A6": "12345.678", "A7": "1e-7", "A8": "1e20",
    "A9": "12,5", "A10": "0.005", "A11": "-0.004", "A12": "=1/0", "A13": "=nothing", "A14": "=foo(", "A15": "'text",
    "A16": "hello", "A17": "=True", "A18": "=None", "A19": "=list(1;2)", "A20": "=vector(1;2;3)",
    "B1": "3 mm", "B2": "1 m", "B3": "=1 m * 1 m", "B4": "=2 kg", "B5": "=90 deg", "B6": "=1 s", "B7": "-3 mm",
    "B8": "=1 mm / 1 s", "B9": "=12 in", "B10": "=0.5 mm", "B11": "=1e-4 mm", "B12": "=5 N", "B13": "=3 mm",
    "B14": "=4 mm", "B15": "=5", "B16": "=7 mm", "B17": "=1.5", "B18": "=2", "B19": "=1 mm^3", "B20": "=sqrt(2)",
    "C1": "=A1 * 2", "C2": "=B1 + B2", "C3": "=sum(A1:A3)", "C4": "=average(B1:B2)", "C8": "=min(A1:A3)", "C9": "=max(B1:B2)", "C10": "=count(A1:A6)", "C11": "=stddev(A1:A3)",
    "C12": "=A15 + 1", "C13": "=<<x>>", "C14": "=str(B1)", "C15": "=B1 > 2 mm", "C16": "=A1 / 2",
}
DISPLAY = {"B13": "cm", "B14": "in", "B15": "mm", "B16": "s", "B17": "deg", "B18": "mm"}
ALIASES = {"B1": "thick", "A3": "ratio"}


def prefs():
    g = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Spreadsheet")
    u = App.ParamGet("User parameter:BaseApp/Preferences/Units")
    return {k: g.GetString(k) for k in ("AliasedCellBackgroundColor", "TextColor", "PositiveNumberColor",
                                         "NegativeNumberColor", "DisplayAliasFormatString", "ImportExportDelimiter")} | {
        "showAliasName": g.GetBool("showAliasName"), "Decimals": u.GetInt("Decimals", 2), "UserSchema": u.GetInt("UserSchema", 0),
        "locale": QtCore.QLocale().name(), "system_locale": QtCore.QLocale.system().name()}


def focus_table():
    tv = table()
    mw.activateWindow()
    tv.window().activateWindow()
    tv.setFocus(Qt.OtherFocusReason)
    pump(0.2)
    return tv.hasFocus()


def main():
    global doc, sheet
    App.ParamGet("User parameter:BaseApp/Preferences/Document").SetInt("MaxUndoSize", 1000)
    safe("prefs", prefs)
    Gui.activateWorkbench("SpreadsheetWorkbench")
    pump(1.0)
    safe("menus_none", menus)
    safe("toolbars_none", toolbars)

    def create():
        global doc, sheet
        doc = App.newDocument("Unnamed")
        pump(0.5)
        before = list(doc.UndoNames)
        Gui.runCommand("Spreadsheet_CreateSheet", 0)
        pump(1.5)
        if table() is None:
            Gui.getDocument(doc.Name).setEdit("Spreadsheet")
            pump(1.5)
        sheet = doc.getObject("Spreadsheet")
        area = mw.findChild(QtWidgets.QMdiArea)
        act = area.activeSubWindow()
        tv = table()
        return {"objects": [[o.Name, o.TypeId, o.Label] for o in doc.Objects], "undo": undo_head(before),
                "mdi": [w.windowTitle() for w in area.subWindowList()], "active": act.windowTitle() if act else None,
                "table": tv is not None, "rows": tv.model().rowCount(), "cols": tv.model().columnCount(),
                "header_h": [tv.model().headerData(i, Qt.Horizontal, Qt.DisplayRole) for i in (0, 25)],
                "header_v": [tv.model().headerData(i, Qt.Vertical, Qt.DisplayRole) for i in (0, 9)],
                "col_width": tv.columnWidth(0), "row_height": tv.rowHeight(0),
                "labels": [w.text() for w in mw.findChildren(QtWidgets.QLabel) if w.text() in ("&Content", "&Alias")],
                "alias_tip": line("cellAlias").toolTip() if line("cellAlias") else None,
                "content_enabled": line("cellContent").isEnabled() if line("cellContent") else None}
    safe("create", create)
    safe("menus_sheet", menus)
    safe("toolbars_sheet", toolbars)

    def cells():
        before = list(doc.UndoNames)
        for a, t in CELLS.items():
            type_cell(a, t)
        undo_typed = undo_head(before)
        for a, u in DISPLAY.items():
            sheet.setDisplayUnit(a, u)
        for a, al in ALIASES.items():
            sheet.setAlias(a, al)
        doc.recompute()
        pump(1.0)
        return {"undo": undo_typed[:3], "undo_count": len(undo_typed), "cells": used(),
                "view": view_cells("A1:C20"), "empty": roles(table().model(), 30, 5)}
    safe("cells", cells)

    def pending():
        """A typed formula before the recompute that SheetModel::setCellData runs: #PENDING (the dirty state)."""
        sheet.set("D1", "=A1 + 1")
        sheet.set("D2", "7")
        pump(0.5)
        out = {"D1": roles(table().model(), 0, 3), "D2": roles(table().model(), 1, 3)}
        doc.recompute()
        pump(0.5)
        out["after"] = {"D1": roles(table().model(), 0, 3), "D2": roles(table().model(), 1, 3)}
        return out
    safe("pending", pending)

    def lines():
        out = {}
        for a in ("A1", "B1", "C1", "A15", "A14", "E5"):
            select(a)
            pump(0.2)
            out[a] = {"content": line("cellContent").text(), "alias": line("cellAlias").text()}
        return out
    safe("lines", lines)

    def context_menu():
        tv = table()
        out = {}
        for key, sel in (("one", ["E1"]), ("range", ["E1:F2"]), ("merged", None)):
            if sel is None:
                sheet.mergeCells("H1:I2")
                doc.recompute()
                pump(0.3)
                sel = ["H1"]
            select(*sel)
            ev = QtGui.QContextMenuEvent(QtGui.QContextMenuEvent.Mouse, QtCore.QPoint(50, 50), tv.viewport().mapToGlobal(QtCore.QPoint(50, 50)))
            out[key] = menu_of(lambda: app.sendEvent(tv.viewport(), ev))
        sheet.splitCell("H1")
        doc.recompute()
        return out
    safe("context_menu", context_menu)

    def commands():
        out = {}
        for i, cmd in enumerate(["Spreadsheet_AlignLeft", "Spreadsheet_AlignCenter", "Spreadsheet_AlignRight",
                                 "Spreadsheet_AlignTop", "Spreadsheet_AlignVCenter", "Spreadsheet_AlignBottom",
                                 "Spreadsheet_StyleBold", "Spreadsheet_StyleItalic", "Spreadsheet_StyleUnderline"]):
            rg = f"E{i + 3}:F{i + 3}"
            type_cell(f"E{i + 3}", f"'{cmd[12:]}")
            select(rg)
            out[cmd] = {"undo": run(cmd), "cells": {a: cell_state(a) for a in (f"E{i + 3}", f"F{i + 3}")}}
        select("E9:F9")
        out["bold_again"] = {"undo": run("Spreadsheet_StyleBold"), "cell": cell_state("E9")}
        select("E12:F13")
        type_cell("E12", "'m")
        type_cell("F13", "'gone")
        select("E12:F13")
        out["Spreadsheet_MergeCells"] = {"undo": run("Spreadsheet_MergeCells"), "used": used(), "spans": spans()}
        select("E12")
        out["Spreadsheet_SplitCell"] = {"undo": run("Spreadsheet_SplitCell"), "spans": spans()}
        return out
    safe("commands", commands)
    safe("menus_range", lambda: (select("E3:F4"), menus())[1])

    def properties():
        type_cell("G1", "=2 mm")
        select("G1")
        tv = table()
        act = next(a for a in tv.actions() if a.text().replace("…", "").replace("...", "") == "Properties")
        before = list(doc.UndoNames)

        def inspect(d):
            info = dialog_widgets(d)
            tabs = d.findChild(QtWidgets.QTabWidget)
            pages = {}
            for i in range(tabs.count()):
                tabs.setCurrentIndex(i)
                pump(0.1)
                pages[tabs.tabText(i)] = [e for e in dialog_widgets(d)["widgets"] if e["visible"]]
            info["pages"] = pages
            d.findChild(QtWidgets.QRadioButton, "alignRight").click()
            d.findChild(QtWidgets.QRadioButton, "alignTop").click()
            d.findChild(QtWidgets.QCheckBox, "styleBold").click()
            du = d.findChild(QtWidgets.QLineEdit, "displayUnit")
            du.setText("cm")
            du.textEdited.emit("cm")
            al = d.findChild(QtWidgets.QLineEdit, "alias")
            for text in ("1x", "mm", "pi", "thick", "A1", "Label", "g_one"):
                al.setText(text)
                al.textEdited.emit(text)
                pump(0.05)
                st = d.findChild(QtWidgets.QLabel, "aliasStatus")
                ok = d.findChild(QtWidgets.QDialogButtonBox).button(QtWidgets.QDialogButtonBox.Ok)
                info.setdefault("alias_checks", {})[text] = {"status": st.text(), "status_visible": st.isVisible(),
                                                             "tip": al.toolTip(), "ok": ok.isEnabled()}
            du.setText("bogus")
            du.textEdited.emit("bogus")
            info["bad_unit_ok"] = d.findChild(QtWidgets.QDialogButtonBox).button(QtWidgets.QDialogButtonBox.Ok).isEnabled()
            du.setText("cm")
            du.textEdited.emit("cm")
            d.accept()
            return info
        info = with_dialog(act.trigger, inspect)
        pump(0.5)
        info["undo"] = undo_head(before)
        info["cell"] = cell_state("G1")
        info["view"] = roles(tv.model(), 0, 6)
        return info
    safe("properties", properties)

    def properties_range():
        select("G3:G4")
        tv = table()
        act = next(a for a in tv.actions() if a.text().replace("…", "").replace("...", "") == "Properties")

        def inspect(d):
            info = dialog_widgets(d)
            d.reject()
            return info
        return with_dialog(act.trigger, inspect)
    safe("properties_range", properties_range)

    def set_alias():
        type_cell("G6", "4")
        select("G6")
        before = list(doc.UndoNames)

        def inspect(d):
            info = dialog_widgets(d)
            al = d.findChild(QtWidgets.QLineEdit, "alias")
            al.setText("four")
            al.textEdited.emit("four")
            d.accept()
            return info
        info = with_dialog(lambda: Gui.runCommand("Spreadsheet_SetAlias", 0), inspect)
        pump(0.5)
        info["undo"] = undo_head(before)
        info["cell"] = cell_state("G6")
        return info
    safe("set_alias", set_alias)

    def alias_line():
        type_cell("G8", "8")
        select("G8")
        before = list(doc.UndoNames)
        le = line("cellAlias")
        out = {}
        for text in ("bad alias", "eight"):
            le.setText(text)
            le.textEdited.emit(text)
            pump(0.1)
            out[text] = {"tip": le.toolTip(), "style": le.styleSheet()}
        le.editingFinished.emit()
        pump(0.6)
        out["undo"] = undo_head(before)
        out["cell"] = cell_state("G8")
        return out
    safe("alias_line", alias_line)

    def content_line():
        select("G10")
        before = list(doc.UndoNames)
        le = line("cellContent")
        le.setText("=eight * 2")
        le.returnPressed.emit()
        pump(0.8)
        return {"undo": undo_head(before), "cell": cell_state("G10"), "view": roles(table().model(), 9, 6)}
    safe("content_line", content_line)

    def copy_paste():
        type_cell("J1", "1")
        type_cell("J2", "=J1 + 1")
        type_cell("K1", "=$J$1 * 2")
        type_cell("K2", "=sum(J1:J2)")
        sheet.setStyle("J1", "bold")
        doc.recompute()
        pump(0.3)
        tv = table()
        select("J1:K2")
        acts = {a.text(): a for a in tv.findChildren(QtGui.QAction)}
        acts["Copy"].trigger()
        pump(0.3)
        clip = QtWidgets.QApplication.clipboard().mimeData()
        out = {"text": clip.text(), "formats": clip.formats(),
               "xml": bytes(clip.data("application/x-fc-spreadsheet")).decode("utf-8", "replace")}
        select("L5")
        before = list(doc.UndoNames)
        acts["Paste"].trigger()
        pump(0.8)
        out["undo"] = undo_head(before)
        out["used"] = {a: c for a, c in used().items() if a[0] in "JKLM"}
        select("L10:O13")
        acts["Paste"].trigger()
        pump(0.8)
        out["tiled"] = {a: c for a, c in used().items() if a[0] in "LMNO" and int(a[1:]) >= 10}
        select("J1:J2")
        acts["Cut"].trigger()
        pump(0.3)
        select("Q1")
        before = list(doc.UndoNames)
        acts["Paste"].trigger()
        pump(0.8)
        out["cut_undo"] = undo_head(before)
        out["after_cut"] = {a: c for a, c in used().items() if a[0] in "JKQ"}
        select("Q1:Q2")
        before = list(doc.UndoNames)
        acts["Delete"].trigger()
        pump(0.6)
        out["delete_undo"] = undo_head(before)
        out["after_delete"] = {a: c for a, c in used().items() if a[0] in "Q"}
        return out
    safe("copy_paste", copy_paste)

    def headers():
        tv = table()
        out = {}
        for orient, hdr in (("rows", tv.verticalHeader()), ("columns", tv.horizontalHeader())):
            for n in (1, 2):
                tv.clearSelection()
                if orient == "rows":
                    for i in range(n):
                        tv.selectionModel().select(tv.model().index(14 + i, 0),
                                                   QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Rows)
                else:
                    for i in range(n):
                        tv.selectionModel().select(tv.model().index(0, 18 + i),
                                                   QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Columns)
                pump(0.2)
                out[f"{orient}_{n}"] = menu_of(lambda h=hdr: h.customContextMenuRequested.emit(QtCore.QPoint(5, 5)))
        type_cell("A25", "=A26 + 1")
        type_cell("A26", "4")
        tv.clearSelection()
        tv.selectionModel().select(tv.model().index(25, 0), QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Rows)
        pump(0.2)
        before = list(doc.UndoNames)

        menu_of(lambda: tv.verticalHeader().customContextMenuRequested.emit(QtCore.QPoint(5, 5)), pick=0)
        pump(1.0)
        out["insert_undo"] = undo_head(before)
        out["after_insert"] = {a: c for a, c in used().items() if a.startswith("A2")}
        return out
    safe("headers", headers)

    def keys():
        tv = table()
        tv.setFocus()
        out = []
        sheet.mergeCells("T5:U6")
        doc.recompute()
        pump(0.3)
        seq = [("T3", Qt.Key_Return, Qt.NoModifier), ("T3", Qt.Key_Return, Qt.ShiftModifier), ("T3", Qt.Key_Tab, Qt.NoModifier),
               ("T3", Qt.Key_Backtab, Qt.ShiftModifier), ("T3", Qt.Key_Left, Qt.NoModifier), ("T3", Qt.Key_Right, Qt.NoModifier),
               ("T3", Qt.Key_Up, Qt.NoModifier), ("T3", Qt.Key_Down, Qt.NoModifier), ("T3", Qt.Key_Home, Qt.NoModifier),
               ("T3", Qt.Key_Home, Qt.ControlModifier), ("A3", Qt.Key_End, Qt.NoModifier), ("T4", Qt.Key_Down, Qt.NoModifier),
               ("T5", Qt.Key_Down, Qt.NoModifier), ("S5", Qt.Key_Right, Qt.NoModifier), ("A1", Qt.Key_Down, Qt.ControlModifier),
               ("A20", Qt.Key_Down, Qt.ControlModifier)]
        out_focus = focus_table()
        for start, key, mod in seq:
            select(start)
            focus_table()
            for typ in (QtCore.QEvent.KeyPress,):
                app.sendEvent(tv, QtGui.QKeyEvent(typ, key, mod))
            pump(0.2)
            cur = tv.currentIndex()
            out.append({"from": start, "key": QtGui.QKeySequence(int(key.value if hasattr(key, "value") else key)).toString(),
                        "mod": int(mod.value if hasattr(mod, "value") else mod), "to": addr(cur.row(), cur.column()),
                        "focus": tv.hasFocus()})
        return {"focus": out_focus, "moves": out}
    safe("keys", keys)

    def props():
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(sheet)
        pump(0.6)
        out = {}
        tabs = [t for t in mw.findChildren(QtWidgets.QTabWidget)
                if t.parent() is not None and t.parent().metaObject().className() == "Gui::PropertyView"]
        for tw in tabs:
            for i in range(tw.count()):
                tw.setCurrentIndex(i)
                pump(0.3)
                rows = []
                for ed in tw.widget(i).findChildren(QtWidgets.QTreeView):
                    m = ed.model()

                    def walk(parent, depth):
                        for r in range(m.rowCount(parent)):
                            if ed.isRowHidden(r, parent):
                                continue
                            i0, i1 = m.index(r, 0, parent), m.index(r, 1, parent)
                            v = m.data(i1)
                            rows.append({"depth": depth, "name": m.data(i0), "value": v if isinstance(v, (str, int, float, bool, type(None))) else str(v)})
                            if depth < 1:
                                walk(i0, depth + 1)
                    walk(QtCore.QModelIndex(), 0)
                out[tw.tabText(i).replace("&", "").lower()] = rows
        return out
    safe("props", props)

    def tree():
        t = [t for t in mw.findChildren(QtWidgets.QTreeWidget) if t.metaObject().className() == "Gui::TreeWidget"][0]
        t.expandAll()
        pump(0.3)
        rows = []

        def walk(item, depth):
            rows.append({"text": item.text(0), "depth": depth})
            for i in range(item.childCount()):
                walk(item.child(i), depth + 1)
        for i in range(t.topLevelItemCount()):
            walk(t.topLevelItem(i), 0)
        return rows
    safe("tree", tree)

    def undo():
        before = list(doc.UndoNames)
        Gui.runCommand("Std_Undo", 0)
        pump(0.8)
        mid = list(doc.UndoNames)
        Gui.runCommand("Std_Redo", 0)
        pump(0.8)
        return {"before": before[:12], "after_undo": mid[:3], "after_redo": list(doc.UndoNames)[:3]}
    safe("undo", undo)

    def cycles():
        """A second sheet whose cells read each other: what a cycle shows (Sheet::execute's exceptions)."""
        s2 = doc.addObject("Spreadsheet::Sheet", "Spreadsheet001")
        for a, t in (("A1", "=A2 + 1"), ("A2", "=A1"), ("A3", "=A3"), ("B1", "5"), ("B2", "=B1 * 2")):
            s2.set(a, t)
        doc.recompute()
        Gui.getDocument(doc.Name).setEdit("Spreadsheet001")
        pump(1.0)
        out = {"first": view_cells("A1:B3")}
        s2.set("A2", "4")
        s2.set("A3", "1")
        doc.recompute()
        pump(0.6)
        out["fixed"] = view_cells("A1:B3")
        s2.set("C1", "=D1")
        s2.set("D1", "=C1")
        s2.set("E1", "=E2")
        s2.set("E2", "=E3")
        s2.set("E3", "=E1")
        doc.recompute()
        pump(0.6)
        out["two_loops"] = view_cells("C1:E3")
        return out
    safe("cycles", cycles)
    safe("final_cells", used)
    save()
    os._exit(0)


QtCore.QTimer.singleShot(500, main)

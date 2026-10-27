# SPDX-License-Identifier: LGPL-2.1-or-later
# Runs inside FreeCAD's GUI (fctechdraw_more.py starts it under fclaunch, windows kept off the screen): what the real TechDraw
# workbench does with its leader line, rich text, symbol, weld symbol, surface finish, image and clip tools, for the TechDraw page
# to be compared with. Writes fctechdraw_more.json into FCGUI_OUT:
#   start                 the plate's view from above
#   states_*              the TechDraw menu and toolbars (every entry greyed or not) for a selection of nothing, a view, an edge, a
#                         leader line, a weld symbol, a clip group
#   leader_*              TechDraw_LeaderLine: the wrong selections, the panel (TaskLeaderLine), the points clicked on the page,
#                         OK and Cancel; the objects made (properties, view provider properties), the undo steps; the edit panel
#   richanno_*            TechDraw_RichTextAnnotation: the panel, the click that places the text, the text typed, OK, Cancel
#   symbol_*              TechDraw_Symbol with an SVG file chosen in the file dialog
#   weld_*                TechDraw_WeldSymbol on a leader: the panel, the symbol chosen in SymbolChooser, the texts, OK; the edit panel
#   surface_*             TechDraw_SurfaceFinishSymbols: the panel, each icon, ISO and ASME, OK; the symbol's text
#   image_*               TechDraw_Image with a bitmap chosen in the file dialog
#   clip_*                TechDraw_ClipGroup, TechDraw_ClipGroupAdd, TechDraw_ClipGroupRemove
#   tree, props_*         the tree's rows; each new object's property view (Data and View tabs)
#   *_svg, final_dxf      the page exported
#   undo_names            the document's undo steps at the end
import json
import os
import sys
import tempfile
import time
import traceback

import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtCore, QtGui, QtTest, QtWidgets

# the helpers of fctechdraw_hatch_dump.py (everything before its main): the pumps, the task panel's widgets, the property view ...
_src = open(os.environ["FCTECHDRAW_HELPERS"], encoding="utf-8").read().split("\ndef main():")[0]
exec(compile(_src, "fctechdraw_hatch_dump.py", "exec"), globals())
ONLY = [x for x in os.environ.get("FCTECHDRAW_ONLY", "").split(",") if x]


def save():
    json.dump(res, open(os.path.join(OUT, "fctechdraw_more.json"), "w"), indent=1, default=repr)


NEW_TYPES = ("TechDraw::DrawLeaderLine", "TechDraw::DrawRichAnno", "TechDraw::DrawViewSymbol", "TechDraw::DrawWeldSymbol", "TechDraw::DrawTileWeld",
             "TechDraw::DrawViewImage", "TechDraw::DrawViewClip")


def want(section):
    return not ONLY or section in ONLY


# ── clicking on the page (QGVPage's viewport) ────────────────────────────────────────────────────────────────
def page_view():
    for v in mw.findChildren(QtWidgets.QGraphicsView):
        if v.isVisible() and v.scene() is not None and v.metaObject().className() in ("TechDrawGui::QGVPage", "QGVPage"):
            return v
    for v in mw.findChildren(QtWidgets.QGraphicsView):
        if v.isVisible() and v.scene() is not None and v.scene().metaObject().className().endswith("QGSPage"):
            return v
    return None


def page_pixel(x_mm, y_mm):
    """The viewport pixel of the page point (mm from the lower left corner, y up): scene units are 0.1 mm, y down."""
    v = page_view()
    p = v.mapFromScene(QtCore.QPointF(x_mm * 10.0, -y_mm * 10.0))
    return v, p


def page_point(p):
    """The page point (mm, y up) of a viewport pixel: what a click there means to the scene."""
    v = page_view()
    s = v.mapToScene(p)
    return [s.x() / 10.0, -s.y() / 10.0]


def click_page(x_mm, y_mm, button=QtCore.Qt.LeftButton, double=False):
    v, p = page_pixel(x_mm, y_mm)
    vp = v.viewport()
    QtTest.QTest.mouseMove(vp, p)
    pump(0.15)
    if double:
        QtTest.QTest.mouseDClick(vp, button, QtCore.Qt.NoModifier, p)
    else:
        QtTest.QTest.mouseClick(vp, button, QtCore.Qt.NoModifier, p)
    pump(0.3)
    return page_point(p)


def click_points(points, finish="double"):
    """Click each point (left) and finish as a person does: a double click on the last point (QGTracker::onDoubleClick), or a right
    click a little way off it (QGTracker ignores one within 1 mm of the last click)."""
    got = []
    for i, (x, y) in enumerate(points):
        last = i == len(points) - 1
        if last and finish == "double":
            v, p = page_pixel(x, y)
            QtTest.QTest.mouseMove(v.viewport(), p)
            pump(0.15)
            QtTest.QTest.mouseClick(v.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, p)
            pump(0.3)
            QtTest.QTest.mouseDClick(v.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, p)
            got.append(page_point(p))
        else:
            got.append(click_page(x, y))
    if finish == "right":
        v, p = page_pixel(points[-1][0] + 3.0, points[-1][1])
        QtTest.QTest.mouseClick(v.viewport(), QtCore.Qt.RightButton, QtCore.Qt.NoModifier, p)
    pump(0.6)
    return got


def view_page_pos(name):
    o = doc.getObject(name)
    return [o.X.Value, o.Y.Value]


def objects_made(before, kinds=None):
    out = []
    for o in doc.Objects:
        if o.Name in before or (kinds and o.TypeId not in kinds):
            continue
        d = {"Name": o.Name, "Label": o.Label, "TypeId": o.TypeId}
        for p in o.PropertiesList:
            if p in ("Proxy", "ExpressionEngine", "Shape", "Visibility"):
                continue
            try:
                d[p] = val(getattr(o, p))
            except Exception as e:
                d[p] = f"<{e}>"
        try:
            d["ViewProvider"] = vp_props(o.Name)
        except Exception as e:
            d["ViewProvider"] = f"<{e}>"
        out.append(d)
    return out


def object_state(name):
    o = doc.getObject(name)
    d = {"Name": o.Name, "Label": o.Label, "TypeId": o.TypeId}
    for p in o.PropertiesList:
        if p in ("Proxy", "ExpressionEngine", "Shape", "Visibility"):
            continue
        try:
            d[p] = val(getattr(o, p))
        except Exception as e:
            d[p] = f"<{e}>"
    d["ViewProvider"] = vp_props(name)
    return d


def full_states(sels):
    select(sels)
    return {"selection": [[x.ObjectName, list(x.SubElementNames)] for x in Gui.Selection.getSelectionEx()],
            "menu": menus(), "toolbars": toolbars()}


def run_tool_more(cmd, sels, edit=None, ok=True, wait=2.0, before_ok=None):
    """run_tool, and what it made: the objects (with their view provider properties) and the tree."""
    names = {o.Name for o in doc.Objects}
    select(sels)
    undo = list(doc.UndoNames)
    holder = {}
    t = watch_dialogs(holder)
    out = {"selection": [[x.ObjectName, list(x.SubElementNames)] for x in Gui.Selection.getSelectionEx()]}
    Gui.runCommand(cmd, 0)
    pump(wait)
    out["dialog_open"] = bool(Gui.Control.activeDialog())
    out["panel"] = task_widgets()
    out["undo_after_open"] = new_undo(undo)
    out["made_after_open"] = [o.Name for o in doc.Objects if o.Name not in names]
    if edit is not None:
        out["edit"] = edit()
        pump(0.8)
        out["panel_after_edit"] = task_widgets()
    if before_ok is not None:
        out["before_ok"] = before_ok()
    if Gui.Control.activeDialog():
        out["button"] = click_button("OK" if ok else "Cancel")
    settle()
    t.stop()
    out["dialogs"] = holder.get("dialogs", [])
    out["undo"] = new_undo(undo)
    out["made"] = objects_made(names)
    out["tasks_after"] = task_widgets()
    out["dialog_open_after"] = bool(Gui.Control.activeDialog())
    close_task()
    out["tree"] = tree_rows()
    return out


def svg_page():
    import TechDrawGui
    p = os.path.join(tempfile.mkdtemp(prefix="fctechdrawmore"), "page.svg")
    TechDrawGui.exportPageAsSvg(doc.getObject("Page"), p)
    pump(0.5)
    return open(p, encoding="utf-8", errors="replace").read()


def dxf_page():
    import TechDraw
    p = os.path.join(tempfile.mkdtemp(prefix="fctechdrawmore"), "page.dxf")
    TechDraw.writeDXFPage(doc.getObject("Page"), p)
    return open(p, encoding="utf-8", errors="replace").read()


def answer_dialogs(holder, file=None, symbol=None):
    """A timer that answers the file dialog (the file given) and SymbolChooser (the symbol file's base name) a command opens: each
    runs its own event loop under the click that opened it, so the script cannot answer from where it clicked."""
    t = QtCore.QTimer()

    def tick():
        for w in app.topLevelWidgets():
            if not w.isVisible():
                continue
            cls = w.metaObject().className()
            if isinstance(w, QtWidgets.QFileDialog) and file is not None:
                holder.setdefault("file_dialogs", []).append({"title": w.windowTitle(), "dir": w.directory().path(),
                                                              "filters": list(w.nameFilters()), "mode": int(w.fileMode().value)})
                w.selectFile(file)
                w.accept()
            elif cls == "TechDrawGui::SymbolChooser" and symbol is not None:
                lw = w.findChild(QtWidgets.QListWidget, "lwSymbols")
                fc = w.findChild(QtWidgets.QWidget, "fcSymbolDir")
                holder.setdefault("choosers", []).append({"title": w.windowTitle(), "size": [w.width(), w.height()],
                                                          "items": [lw.item(i).text() for i in range(lw.count())],
                                                          "dir": fc.fileName() if hasattr(fc, "fileName") else None,
                                                          "icons": sum(1 for i in range(lw.count()) if not lw.item(i).icon().isNull())})
                for i in range(lw.count()):
                    if lw.item(i).text() == symbol:
                        lw.setCurrentRow(i)
                        lw.itemClicked.emit(lw.item(i))
                        break
                else:
                    w.reject()
            elif isinstance(w, QtWidgets.QMessageBox):
                holder.setdefault("dialogs", []).append({"title": w.windowTitle(), "text": w.text(), "buttons": [b.text() for b in w.buttons()]})
                w.reject()
    t.timeout.connect(tick)
    t.start(300)
    return t


def proxy_widgets():
    """The widgets inside the surface finish panel's graphics view (QGraphicsProxyWidget), by tool tip."""
    out = {}
    for v in mw.findChildren(QtWidgets.QGraphicsView):
        if v.objectName() != "graphicsView" or not v.isVisible():
            continue
        for it in v.scene().items():
            if isinstance(it, QtWidgets.QGraphicsProxyWidget):
                w = it.widget()
                out[w.toolTip()] = {"widget": w, "visible": it.isVisible(), "pos": [it.pos().x(), it.pos().y()],
                                    "size": [w.width(), w.height()], "class": w.metaObject().className()}
    return out


def rich_editors():
    out = []
    for w in app.topLevelWidgets():
        for te in w.findChildren(QtWidgets.QTextEdit):
            out.append({"top": w.metaObject().className(), "visible": te.isVisible(), "edit": te})
    return out


# ── the sections ──────────────────────────────────────────────────────────────────────────────────────────────
def leader_section():
    safe("states_none", lambda: full_states([]))
    safe("states_view", lambda: full_states(["View"]))
    safe("states_edge", lambda: full_states([("View", "Edge2")]))
    safe("leader_wrong_nothing", lambda: run_cmd_plain("TechDraw_LeaderLine", []))
    safe("leader_wrong_page", lambda: run_cmd_plain("TechDraw_LeaderLine", ["Page"]))

    pts = [(120.0, 100.0), (140.0, 125.0), (170.0, 125.0)]
    clicked = {}

    def pick():
        click_button("Pick Points")
        pump(0.5)
        clicked["points"] = click_points(pts)
        clicked["panel_after_pick"] = task_widgets()
        return clicked

    def combo(name, i):
        cb = child(name, QtWidgets.QComboBox)
        if cb is not None:
            cb.setCurrentIndex(i)
            pump(0.4)
        return cb.currentText() if cb is not None else None
    safe("leader_cancel", lambda: run_tool_more("TechDraw_LeaderLine", ["View"], pick, ok=False))

    def edit():
        r = pick()
        r["end"] = combo("cboxEndSym", 0)
        r["start"] = combo("cboxStartSym", 4)
        r["weight"] = set_quantity("dsbWeight", "0.7 mm")
        r["style"] = combo("cboxStyle", 2)
        return r
    safe("leader", lambda: run_tool_more("TechDraw_LeaderLine", ["View"], edit))
    safe("leader_svg", svg_page)
    safe("leader_states", lambda: full_states(["LeaderLine"]))

    # a leader with no points picked: OK straight away
    safe("leader_nopoints", lambda: run_tool_more("TechDraw_LeaderLine", ["View"], None))

    def edit_existing():
        h = doc.getObject("LeaderLine")
        Gui.Selection.clearSelection()
        undo = list(doc.UndoNames)
        Gui.ActiveDocument.setEdit(h, 0)
        pump(1.5)
        out = {"object": h.Name, "dialog_open": bool(Gui.Control.activeDialog()), "panel": task_widgets()}
        out["edit"] = {"start": combo("cboxStartSym", 2), "weight": set_quantity("dsbWeight", "0.35 mm")}
        click_button("OK")
        settle()
        out["undo"] = new_undo(undo)
        out["leader"] = object_state("LeaderLine")
        close_task()
        return out
    safe("leader_edit", edit_existing)


def richanno_section():
    safe("richanno_wrong_page", lambda: run_cmd_plain("TechDraw_RichTextAnnotation", ["Page"]))

    def make(text_fn, base, at, frame=None, width=None):
        names = {o.Name for o in doc.Objects}
        select(base)
        undo = list(doc.UndoNames)
        holder = {}
        out = {"selection": [[x.ObjectName, list(x.SubElementNames)] for x in Gui.Selection.getSelectionEx()]}
        Gui.runCommand("TechDraw_RichTextAnnotation", 0)
        pump(1.5)
        out["panel_open"] = task_widgets()
        out["undo_after_open"] = new_undo(undo)
        out["made_after_open"] = [o.Name for o in doc.Objects if o.Name not in names]
        out["top_levels"] = [w.metaObject().className() for w in app.topLevelWidgets() if w.isVisible()]
        out["clicked"] = click_page(*at)
        pump(1.0)
        out["made_after_click"] = [o.Name for o in doc.Objects if o.Name not in names]
        out["panel_placed"] = task_widgets()
        eds = rich_editors()
        out["editors"] = [[e["top"], e["visible"]] for e in eds]
        if frame is not None:
            gb = child("gbFrame", QtWidgets.QGroupBox)
            if gb is not None:
                gb.setChecked(frame)
                pump(0.5)
        if width is not None:
            out["width"] = set_quantity("dsbMaxWidth", width)
        if text_fn is not None and eds:
            out["text"] = text_fn([e["edit"] for e in eds if e["top"] != "Gui::MainWindow"] or [eds[0]["edit"]])
        pump(0.8)
        out["before_ok"] = [object_state(n.Name) for n in doc.Objects if n.Name not in names and n.TypeId == "TechDraw::DrawRichAnno"]
        out["button"] = click_button("OK")
        settle()
        out["undo"] = new_undo(undo)
        out["made"] = objects_made(names)
        out["dialog_open_after"] = bool(Gui.Control.activeDialog())
        close_task()
        out["tree"] = tree_rows()
        return out

    def plain(edits):
        te = edits[0]
        te.setPlainText("Hello rich text")
        return te.toHtml()

    def formatted(edits):
        te = edits[0]
        te.setPlainText("Bold first\nsecond line")
        c = te.textCursor()
        c.setPosition(0)
        c.setPosition(4, QtGui.QTextCursor.KeepAnchor)
        f = QtGui.QTextCharFormat()
        f.setFontWeight(QtGui.QFont.Bold)
        f.setForeground(QtGui.QColor("#ff0000"))
        c.mergeCharFormat(f)
        c.setPosition(11)
        c.setPosition(17, QtGui.QTextCursor.KeepAnchor)
        f2 = QtGui.QTextCharFormat()
        f2.setFontItalic(True)
        f2.setFontUnderline(True)
        f2.setFontPointSize(14)
        c.mergeCharFormat(f2)
        return te.toHtml()
    safe("richanno_plain", lambda: make(plain, [], (60.0, 40.0)))
    safe("richanno_svg", svg_page)
    safe("richanno_view", lambda: make(formatted, ["View"], (200.0, 60.0), frame=True, width="40 mm"))
    safe("richanno_svg2", svg_page)
    safe("richanno_leader", lambda: make(plain, ["LeaderLine"], (100.0, 150.0)) if doc.getObject("LeaderLine") else None)
    safe("richanno_cancel", lambda: make(plain, [], (30.0, 30.0)) if False else None)

    def edit_existing():
        h = [o for o in doc.Objects if o.TypeId == "TechDraw::DrawRichAnno"][-1]
        Gui.Selection.clearSelection()
        undo = list(doc.UndoNames)
        Gui.ActiveDocument.setEdit(h, 0)
        pump(2.0)
        out = {"object": h.Name, "dialog_open": bool(Gui.Control.activeDialog()), "panel": task_widgets(), "undo_after_open": new_undo(undo)}
        out["edit"] = {"width": set_quantity("dsbMaxWidth", "55 mm")}
        out["button"] = click_button("OK")
        settle()
        out["undo"] = new_undo(undo)
        out["object_after"] = object_state(h.Name)
        close_task()
        return out
    safe("richanno_edit", edit_existing)


def symbol_section():
    north = os.path.join(App.getResourceDir(), "Mod", "TechDraw", "Symbols", "misc", "North.svg")

    def sym(sels, path):
        names = {o.Name for o in doc.Objects}
        select(sels)
        undo = list(doc.UndoNames)
        holder = {}
        t = answer_dialogs(holder, file=path)
        out = {"selection": [[x.ObjectName, list(x.SubElementNames)] for x in Gui.Selection.getSelectionEx()]}
        Gui.runCommand("TechDraw_Symbol", 0)
        pump(2.0)
        t.stop()
        settle()
        out.update(holder)
        out["undo"] = new_undo(undo)
        out["made"] = objects_made(names)
        out["tree"] = tree_rows()
        return out
    safe("symbol_page", lambda: sym([], north))
    safe("symbol_owner", lambda: sym(["View"], os.path.join(App.getResourceDir(), "Mod", "TechDraw", "Symbols", "other", "Diameter.svg")))
    safe("symbol_cancel", lambda: sym([], "") if False else None)
    safe("symbol_svg", svg_page)

    def symbol_props():
        s = [o for o in doc.Objects if o.TypeId == "TechDraw::DrawViewSymbol"]
        return {"count": len(s), "text_matches": [o.Symbol == open(north, encoding="utf-8").read() for o in s]}
    safe("symbol_check", symbol_props)


def weld_section():
    safe("weld_wrong_nothing", lambda: run_cmd_plain("TechDraw_WeldSymbol", []))
    safe("weld_wrong_view", lambda: run_cmd_plain("TechDraw_WeldSymbol", ["View"]))

    def make(symbol, texts, other_symbol=None):
        names = {o.Name for o in doc.Objects}
        select(["LeaderLine"])
        undo = list(doc.UndoNames)
        holder = {}
        t = answer_dialogs(holder, symbol=symbol)
        out = {"selection": [[x.ObjectName, list(x.SubElementNames)] for x in Gui.Selection.getSelectionEx()]}
        Gui.runCommand("TechDraw_WeldSymbol", 0)
        pump(2.0)
        out["dialog_open"] = bool(Gui.Control.activeDialog())
        out["panel"] = task_widgets()
        if symbol:
            b = child("pbArrowSymbol", QtWidgets.QPushButton)
            if b is not None:
                b.click()
                pump(1.5)
            out["panel_after_symbol"] = task_widgets()
        for name, text in texts.items():
            le = child(name, QtWidgets.QLineEdit)
            if le is not None:
                le.setText(text)
                le.textEdited.emit(text)
                pump(0.2)
        if other_symbol:
            t.stop()
            t = answer_dialogs(holder, symbol=other_symbol)
            b = child("pbOtherSymbol", QtWidgets.QPushButton)
            if b is not None:
                b.click()
                pump(1.5)
        for cb in ("cbFieldWeld", "cbAllAround"):
            w = child(cb, QtWidgets.QCheckBox)
            if w is not None:
                w.setChecked(True)
                pump(0.2)
        out["panel_before_ok"] = task_widgets()
        out["button"] = click_button("OK")
        settle()
        t.stop()
        out.update(holder)
        out["undo"] = new_undo(undo)
        out["made"] = objects_made(names)
        close_task()
        out["tree"] = tree_rows()
        return out
    safe("weld", lambda: make("filletDown", {"leArrowTextL": "3", "leArrowTextR": "5", "leArrowTextC": "(2)", "leOtherTextL": "4",
                                              "leTailText": "T1"}, other_symbol="VUp"))
    safe("weld_svg", svg_page)
    safe("weld_states", lambda: full_states(["WeldSymbol"]))

    def edit_existing():
        h = doc.getObject("WeldSymbol")
        Gui.Selection.clearSelection()
        undo = list(doc.UndoNames)
        Gui.ActiveDocument.setEdit(h, 0)
        pump(2.0)
        out = {"object": h.Name, "dialog_open": bool(Gui.Control.activeDialog()), "panel": task_widgets(), "undo_after_open": new_undo(undo)}
        le = child("leTailText", QtWidgets.QLineEdit)
        if le is not None:
            le.setText("T2")
            le.textEdited.emit("T2")
        pump(0.4)
        out["button"] = click_button("OK")
        settle()
        out["undo"] = new_undo(undo)
        out["weld"] = object_state(h.Name)
        close_task()
        return out
    safe("weld_edit", edit_existing)


def surface_section():
    def make(sels, edit):
        names = {o.Name for o in doc.Objects}
        select(sels)
        undo = list(doc.UndoNames)
        holder = {}
        t = watch_dialogs(holder)
        out = {"selection": [[x.ObjectName, list(x.SubElementNames)] for x in Gui.Selection.getSelectionEx()]}
        Gui.runCommand("TechDraw_SurfaceFinishSymbols", 0)
        pump(2.0)
        out["dialog_open"] = bool(Gui.Control.activeDialog())
        out["panel"] = task_widgets()
        px = proxy_widgets()
        out["proxies"] = {k: {kk: vv for kk, vv in v.items() if kk != "widget"} for k, v in px.items()}
        if edit:
            out["edit"] = edit(px)
            pump(0.6)
        out["button"] = click_button("OK")
        settle()
        t.stop()
        out["dialogs"] = holder.get("dialogs", [])
        out["undo"] = new_undo(undo)
        out["made"] = objects_made(names)
        close_task()
        out["tree"] = tree_rows()
        return out

    def iso(px):
        px["Method"]["widget"].setText("milled")
        px["Addition"]["widget"].setText("x")
        px["Average roughness"]["widget"].setCurrentIndex(3)
        px["Lay symbol"]["widget"].setCurrentIndex(2)
        b = child("pbIcon02", QtWidgets.QPushButton)
        b.click()
        pump(0.3)
        le = child("leAngle", QtWidgets.QLineEdit)
        le.setText("30")
        return {"icon": 2, "angle": 30}

    def asme(px):
        child("rbASME", QtWidgets.QRadioButton).click()
        pump(0.4)
        px = proxy_widgets()
        px["Method"]["widget"].setText("ground")
        px["Roughness sampling length"]["widget"].setText("0.8")
        px["Minimum roughness grade number"]["widget"].setCurrentIndex(3)
        px["Maximum roughness grade number"]["widget"].setCurrentIndex(5)
        px["Lay symbol"]["widget"].setCurrentIndex(1)
        child("pbIcon05", QtWidgets.QPushButton).click()
        pump(0.3)
        return {"icon": 5}
    safe("surface_wrong_page", lambda: run_cmd_plain("TechDraw_SurfaceFinishSymbols", ["Page"]))
    safe("surface_vertex", lambda: make([("View", "Vertex1")], iso))
    safe("surface_edge", lambda: make([("View", "Edge2")], asme))
    safe("surface_none", lambda: make([], None))
    safe("surface_face", lambda: make([("View", "Face0")], None))
    safe("surface_leader", lambda: make(["LeaderLine"], None) if doc.getObject("LeaderLine") else None)
    safe("surface_svg", svg_page)


def image_section():
    import struct
    import zlib
    png = os.path.join(tempfile.mkdtemp(prefix="fctechdrawmore"), "pic.png")
    w, h = 40, 30
    raw = b"".join(b"\x00" + bytes(v for x in range(w) for v in ((x * 6) % 256, (y * 8) % 256, 128)) for y in range(h)) \
        if False else b"".join(b"\x00" + bytes(v for x in range(w) for v in ((x * 6) % 256, (y * 8) % 256, 128)) for y in range(h))
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    open(png, "wb").write(data)
    res["image_file"] = {"path_base": os.path.basename(png), "size": [w, h]}

    def img(sels):
        names = {o.Name for o in doc.Objects}
        select(sels)
        undo = list(doc.UndoNames)
        holder = {}
        t = answer_dialogs(holder, file=png)
        out = {"selection": [[x.ObjectName, list(x.SubElementNames)] for x in Gui.Selection.getSelectionEx()]}
        Gui.runCommand("TechDraw_Image", 0)
        pump(2.0)
        t.stop()
        settle()
        out.update(holder)
        out["undo"] = new_undo(undo)
        out["made"] = objects_made(names)
        out["tree"] = tree_rows()
        return out
    safe("image_page", lambda: img([]))
    safe("image_owner", lambda: img(["View"]))
    safe("image_svg", svg_page)
    open_png = png
    res["image_png_b64"] = __import__("base64").b64encode(open(open_png, "rb").read()).decode()


def clip_section():
    safe("clip_wrong_add", lambda: run_cmd_plain("TechDraw_ClipGroupAdd", ["View"]))
    safe("clip_wrong_remove", lambda: run_cmd_plain("TechDraw_ClipGroupRemove", ["View"]))
    safe("clip", lambda: run_tool_more("TechDraw_ClipGroup", [], None))
    safe("clip_states", lambda: full_states(["Clip"]))
    safe("clip_wrong_remove_again", lambda: run_cmd_plain("TechDraw_ClipGroupRemove", ["View"]))

    def move_clip():
        c = doc.getObject("Clip")
        c.X, c.Y = 148.5, 105.0
        c.Width, c.Height = 60.0, 40.0
        c.ShowFrame = True
        doc.recompute()
        pump(0.8)
        return object_state("Clip")
    safe("clip_set", move_clip)
    safe("clip_add", lambda: run_tool_more("TechDraw_ClipGroupAdd", ["Clip", "View"], None))
    safe("clip_after_add", lambda: {"clip": object_state("Clip"), "view": object_state("View")})
    safe("clip_svg", svg_page)
    safe("clip_remove", lambda: run_tool_more("TechDraw_ClipGroupRemove", ["View"], None))
    safe("clip_after_remove", lambda: {"clip": object_state("Clip"), "view": object_state("View")})


def main():
    global doc
    pump(1.5)
    Gui.activateWorkbench("TechDrawWorkbench")
    pump(1.0)
    App.ParamGet("User parameter:BaseApp/Preferences/Document").SetInt("MaxUndoSize", 200)
    doc = App.newDocument("Unnamed")
    pump(0.5)
    import Part
    import TechDraw  # noqa: F401
    import TechDrawGui  # noqa: F401
    for name in ("plate", "bracket"):
        o = doc.addObject("Part::Feature", name)
        o.Shape = Part.read(os.path.join(BREPS, name + ".brep"))
    doc.recompute()
    Gui.SendMsgToActiveView("ViewFit")
    pump(0.5)
    Gui.runCommand("TechDraw_PageDefault", 0)
    settle(1.5)
    select(["plate"])
    Gui.runCommand("TechDraw_View", 0)
    pump(2.0)
    click_button("OK")
    settle(2.0)
    close_task()
    v = doc.getObject("View")
    v.Direction = V(0, 0, 1)
    v.recompute()
    settle(3.0)
    res["start"] = view_state(v)
    res["view_pos"] = view_page_pos("View")
    res["page_view"] = bool(page_view())
    if want("leader"):
        leader_section()
    if want("richanno"):
        richanno_section()
    if want("symbol"):
        symbol_section()
    if want("weld"):
        weld_section()
    if want("surface"):
        surface_section()
    if want("image"):
        image_section()
    if want("clip"):
        clip_section()
    for o in list(doc.Objects):
        if o.TypeId in NEW_TYPES:
            safe("props_" + o.TypeId.split("::")[1] + "_" + o.Name, lambda o=o: property_view(o))
    safe("tree", tree_rows)
    safe("final_svg", svg_page)
    safe("final_dxf", dxf_page)
    safe("undo_names", lambda: list(doc.UndoNames))
    save()
    os._exit(0)


QtCore.QTimer.singleShot(500, main)

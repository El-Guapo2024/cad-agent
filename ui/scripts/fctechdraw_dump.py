# SPDX-License-Identifier: LGPL-2.1-or-later
# Runs inside FreeCAD's GUI (fctechdraw.py starts it under fclaunch, windows kept off the screen): what the real TechDraw
# workbench shows, for the TechDraw page to be compared with. Writes fctechdraw.json into FCGUI_OUT:
#   menus_*, toolbars_*  the TechDraw menu and the workbench's toolbars: no page, a page, an edge of a view selected
#   page_default         TechDraw_PageDefault: the objects made, their properties, the template's editable texts, the
#                        undo step, the MDI windows
#   view_*, projgroup_*  TechDraw_View and TechDraw_ProjectionGroup of the selected part: the panel, the panel with Top
#                        and Right ticked, the objects made after OK
#   section_*            TechDraw_SectionView of View by each arrow (Right, Up, Left, Down): the panel, the section made
#   dim_*                each dimension command from a selection of a view's edges or vertices: the dimension made
#                        (dim_smart_click, after the exports: the smart tool and a click on the page)
#   dimension_panel      a dimension's task panel, opened as a double click opens it
#   annotation_made, balloon_*   TechDraw_Annotation; TechDraw_Balloon and a click on the page
#   tree, props_*        the tree's rows; the property view's Data and View tabs of each kind of object
#   undo                 Std_Undo and Std_Redo of the last step
#   page_svg, page_dxf, page_pdf_bytes, export_state   the page exported, and where each view was then
import json
import os
import tempfile
import time
import traceback

import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtCore, QtGui, QtWidgets

OUT = os.environ["FCGUI_OUT"]
BREPS = os.environ["FCTECHDRAW_BREPS"]     # tests/golden/techdraw/breps, from fctechdraw.py
mw = Gui.getMainWindow()
app = QtWidgets.QApplication.instance()
res = {"errors": {}}
mw.resize(1280, 800)
V = App.Vector


def save():
    json.dump(res, open(os.path.join(OUT, "fctechdraw.json"), "w"), indent=1)


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


def close_dialogs():
    out = []
    for w in app.topLevelWidgets():
        if isinstance(w, QtWidgets.QMessageBox) and w.isVisible():
            out.append({"title": w.windowTitle(), "text": w.text(), "buttons": [b.text() for b in w.buttons()]})
            yes = [b for b in w.buttons() if b.text().replace("&", "") in ("Yes",)]
            (yes[0].click() if yes else w.reject())
    return out


def watch_dialogs(holder):
    t = QtCore.QTimer()

    def tick():
        d = close_dialogs()
        if d:
            holder.setdefault("dialogs", []).extend(d)
    t.timeout.connect(tick)
    t.start(200)
    return t


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
        sub = a.menu()
        if sub is not None and depth < 4:
            d["menu"] = dump_menu(sub, depth + 1)
        out.append(d)
    return out


def menus():
    out = {"bar": [a.text() for a in mw.menuBar().actions() if a.isVisible()]}
    for a in mw.menuBar().actions():
        if a.text().replace("&", "") == "TechDraw":
            out[a.text()] = dump_menu(a.menu())
    return out


TOOLBARS = ["TechDraw Pages", "TechDraw Views", "TechDraw Stacking", "TechDraw Dimensions", "TechDraw Attributes",
            "TechDraw Centerlines", "TechDraw Extend Dimensions", "TechDraw File Access", "TechDraw Decoration",
            "TechDraw Annotation"]


def toolbars():
    out = []
    for tb in mw.findChildren(QtWidgets.QToolBar):
        if not (tb.windowTitle().startswith("TechDraw") or tb.windowTitle() in TOOLBARS):
            continue
        row = {"title": tb.windowTitle(), "name": tb.objectName(), "visible": tb.isVisible(), "buttons": []}
        for a in tb.actions():
            if a.isSeparator():
                row["buttons"].append({"sep": True})
                continue
            if not a.isVisible():
                continue
            w = tb.widgetForAction(a)
            b = {"name": a.objectName() or "", "text": a.text(), "tip": a.toolTip(), "enabled": a.isEnabled()}
            if a.menu() is not None:
                b["menu"] = dump_menu(a.menu())
            if isinstance(w, QtWidgets.QToolButton) and w.menu() is not None and "menu" not in b:
                b["menu"] = dump_menu(w.menu())
            row["buttons"].append(b)
        out.append(row)
    return out


def task_widgets():
    views = [w for w in mw.findChildren(QtWidgets.QWidget) if w.metaObject().className() == "Gui::TaskView::TaskView"]
    out = []
    for tv in views:
        if not tv.isVisible():
            continue
        items = []
        for w in tv.findChildren(QtWidgets.QWidget):
            if not w.isVisible():
                continue
            cls = w.metaObject().className()
            pos = w.mapTo(tv, QtCore.QPoint(0, 0))
            d = {"class": cls, "name": w.objectName(), "y": pos.y(), "x": pos.x(), "enabled": w.isEnabled()}
            if w.toolTip():
                d["tip"] = w.toolTip()
            if isinstance(w, QtWidgets.QLabel) and w.text():
                d["text"] = w.text()
            elif isinstance(w, QtWidgets.QAbstractButton):
                d["text"] = w.text()
                if w.isCheckable():
                    d["checked"] = w.isChecked()
            elif isinstance(w, QtWidgets.QComboBox):
                d["items"] = [w.itemText(i) for i in range(w.count())]
                d["current"] = w.currentText()
            elif isinstance(w, QtWidgets.QAbstractSpinBox):
                d["text"] = w.text()
            elif isinstance(w, QtWidgets.QLineEdit):
                d["text"] = w.text()
            elif isinstance(w, QtWidgets.QListWidget):
                d["items"] = [w.item(i).text() for i in range(w.count())]
            elif isinstance(w, QtWidgets.QTreeWidget):
                d["items"] = [w.topLevelItem(i).text(0) for i in range(w.topLevelItemCount())]
            elif isinstance(w, QtWidgets.QGroupBox):
                d["text"] = w.title()
            elif isinstance(w, (QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit)):
                d["text"] = w.toPlainText()
            elif cls.endswith("TaskHeader") or cls == "QSint::TaskHeader":
                d["text"] = " ".join(lbl.text() for lbl in w.findChildren(QtWidgets.QLabel) if lbl.text())
            else:
                continue
            items.append(d)
        items.sort(key=lambda d: (d["y"], d["x"]))
        out.append(items)
    return out


def click_button(text):
    for b in mw.findChildren(QtWidgets.QAbstractButton):
        if b.isVisible() and b.text().replace("&", "") == text:
            b.click()
            pump(1.0)
            return True
    return False


def task_child(cls, name):
    for w in mw.findChildren(cls, name):
        if w.isVisible():
            return w
    return None


def close_task():
    if Gui.Control.activeDialog():
        Gui.Control.closeDialog()
        pump(0.5)


doc = None


def tree_rows():
    tree = [t for t in mw.findChildren(QtWidgets.QTreeWidget) if t.metaObject().className() == "Gui::TreeWidget"][0]
    tree.expandAll()
    pump(0.4)
    rows = []

    def walk(item, depth):
        rows.append({"text": item.text(0), "depth": depth, "bold": item.font(0).bold(), "children": item.childCount()})
        for i in range(item.childCount()):
            walk(item.child(i), depth + 1)
    for i in range(tree.topLevelItemCount()):
        walk(tree.topLevelItem(i), 0)
    return rows


def editor_rows():
    out = []
    for ed in mw.findChildren(QtWidgets.QTreeView):
        if ed.metaObject().className() != "Gui::PropertyEditor::PropertyEditor" or not ed.isVisible():
            continue
        model = ed.model()
        rows = []

        def walk(parent, depth):
            got = []
            for r in range(model.rowCount(parent)):
                if ed.isRowHidden(r, parent):
                    continue
                i0, i1 = model.index(r, 0, parent), model.index(r, 1, parent)
                v = model.data(i1)
                row = [{"depth": depth, "name": model.data(i0),
                        "value": v if isinstance(v, (str, int, float, bool, type(None))) else str(v)}]
                if depth < 1:
                    kids = walk(i0, depth + 1)
                    if not kids:        # a group none of whose properties is shown: not on the screen
                        continue
                    row += kids
                got += row
            return got
        out.append(walk(QtCore.QModelIndex(), 0))
    return out


def property_view(obj):
    """The property view's rows of obj, each tab (Data, View) of the property view's QTabWidget."""
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(obj)
    pump(0.6)
    out = {}
    tabs = [t for t in mw.findChildren(QtWidgets.QTabWidget)
            if t.parent() is not None and t.parent().metaObject().className() == "Gui::PropertyView"]
    if not tabs:
        out["rows"] = editor_rows()
    for tw in tabs:
        cur = tw.currentIndex()
        for i in range(tw.count()):
            tw.setCurrentIndex(i)
            pump(0.3)
            out[tw.tabText(i).replace("&", "").lower()] = editor_rows()
        tw.setCurrentIndex(cur)
    Gui.Selection.clearSelection()
    return out


def val(v):
    if isinstance(v, (bool, int, float, str, type(None))):
        return v if not isinstance(v, str) or len(v) < 4000 else v[:4000] + "..."
    if isinstance(v, App.Vector):
        return [v.x, v.y, v.z]
    if isinstance(v, App.Units.Quantity):
        return v.Value
    if isinstance(v, App.Placement):
        return {"base": val(v.Base), "rotation": list(v.Rotation.Q)}
    if isinstance(v, App.Rotation):
        return list(v.Q)
    if isinstance(v, App.DocumentObject):
        return v.Name
    if isinstance(v, (list, tuple)):
        return [val(x) for x in v]
    if isinstance(v, dict):
        return {str(k): val(x) for k, x in v.items()}
    if hasattr(v, "getRgb") or type(v).__name__ == "Color":
        return str(v)
    s = str(v)
    return s if len(s) < 2000 else s[:2000] + "..."


SKIP = {"Shape", "Proxy", "PageResult"}


def props(o):
    d = {"Name": o.Name, "TypeId": o.TypeId, "Label": o.Label}
    for p in o.PropertiesList:
        if p in SKIP:
            continue
        try:
            d[p] = val(getattr(o, p))
        except Exception as e:
            d[p] = f"<{e}>"
    return d


def mdi_titles():
    area = mw.findChild(QtWidgets.QMdiArea)
    act = area.activeSubWindow()
    return {"windows": [w.windowTitle() for w in area.subWindowList()],
            "active": None if act is None else act.windowTitle()}


def new_undo(before):
    names = list(doc.UndoNames)
    n = len(names) - len(before)
    return {"head": names[:max(n, 1)], "all": names}


def settle(sec=2.0):
    pump(sec)
    doc.recompute()
    pump(1.0)


def run_cmd(cmd, sels=(), after=None, ok=True, wait=2.5):
    """Select sels ((obj, sub) or obj), run cmd, record the panel (if any), call after(), click OK; the objects made."""
    Gui.Selection.clearSelection()
    for s in sels:
        if isinstance(s, tuple):
            Gui.Selection.addSelection(doc.Name, s[0], s[1])
        else:
            Gui.Selection.addSelection(doc.Name, s)
    pump(0.3)
    undo = list(doc.UndoNames)
    before = {o.Name for o in doc.Objects}
    holder = {}
    t = watch_dialogs(holder)
    out = {"selection": [[x.ObjectName, list(x.SubElementNames)] for x in Gui.Selection.getSelectionEx()]}
    Gui.runCommand(cmd, 0)
    pump(wait)
    out["dialog_open"] = Gui.Control.activeDialog()
    out["panel"] = task_widgets()
    if after is not None:
        out["after"] = after()
    if ok and Gui.Control.activeDialog():
        out["ok"] = click_button("OK")
    settle()
    t.stop()
    out["dialogs"] = holder.get("dialogs", [])
    made = [o for o in doc.Objects if o.Name not in before]
    out["made"] = [props(o) for o in made]
    out["undo"] = new_undo(undo)
    out["tasks_after"] = task_widgets()
    out["mdi"] = mdi_titles()
    close_task()
    return out


def section(arrow, symbol=None):
    def after():
        d = {}
        if symbol is not None:
            le = task_child(QtWidgets.QLineEdit, "leSymbol")
            if le is not None:
                le.setText(symbol)
                le.editingFinished.emit()
            d["symbol_set"] = le is not None
        b = task_child(QtWidgets.QAbstractButton, arrow)
        d["arrow_clicked"] = b is not None
        if b is not None:
            b.click()
        pump(2.0)
        d["panel_after"] = task_widgets()
        d["objects_before_ok"] = [o.Name for o in doc.Objects]
        return d
    r = run_cmd("TechDraw_SectionView", ["View"], after)
    keys = ("Name", "Label", "TypeId", "Caption", "SectionSymbol", "SectionDirection", "SectionNormal", "SectionOrigin",
            "Direction", "XDirection", "Rotation", "Scale", "ScaleType", "X", "Y", "BaseView", "Source")
    r["sections"] = [{k: m.get(k) for k in keys} for m in r["made"]]
    return r


DIM_KEYS = ("Name", "Label", "Type", "MeasureType", "FormatSpec", "X", "Y")


def dimension(cmd, sels):
    r = run_cmd(cmd, sels, ok=False)
    dims = []
    for m in r["made"]:
        o = doc.getObject(m["Name"])
        if not o.isDerivedFrom("TechDraw::DrawViewDimension"):
            continue
        d = {k: m.get(k) for k in DIM_KEYS}
        d["References2D"] = [[ob.Name, list(s) if isinstance(s, (list, tuple)) else s] for ob, s in o.References2D]
        for f in ("getRawValue", "getText"):
            try:
                d[f] = getattr(o, f)()
            except Exception as e:
                d[f] = f"<{e}>"
        dims.append(d)
    r["dimensions"] = dims
    pump(2.0)
    r["undo_later"] = list(doc.UndoNames)[:3]
    return r


def page_view():
    for w in mw.findChildren(QtWidgets.QGraphicsView):
        if w.metaObject().className() == "TechDrawGui::QGVPage" and w.isVisible():
            return w
    for w in mw.findChildren(QtWidgets.QGraphicsView):
        if w.metaObject().className() == "TechDrawGui::QGVPage":
            return w
    return None


def activate_page():
    area = mw.findChild(QtWidgets.QMdiArea)
    for w in area.subWindowList():
        if "Page" in w.windowTitle():
            area.setActiveSubWindow(w)
    pump(0.5)


def click_page(sx, sy):
    """A left click on the page view at scene point (sx, sy)."""
    pv = page_view()
    vp = pv.viewport()
    p = pv.mapFromScene(QtCore.QPointF(sx, sy))
    pf = QtCore.QPointF(p)
    g = QtCore.QPointF(vp.mapToGlobal(p))
    for typ, btns in ((QtCore.QEvent.MouseMove, QtCore.Qt.NoButton), (QtCore.QEvent.MouseButtonPress, QtCore.Qt.LeftButton),
                      (QtCore.QEvent.MouseButtonRelease, QtCore.Qt.NoButton)):
        btn = QtCore.Qt.NoButton if typ == QtCore.QEvent.MouseMove else QtCore.Qt.LeftButton
        ev = QtGui.QMouseEvent(typ, pf, pf, g, btn, btns, QtCore.Qt.NoModifier)
        app.sendEvent(vp, ev)
        pump(0.3)
    return {"viewport_point": [p.x(), p.y()], "scene_point": [sx, sy]}


def key_page(key):
    pv = page_view()
    for typ in (QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease):
        app.sendEvent(pv.viewport(), QtGui.QKeyEvent(typ, key, QtCore.Qt.NoModifier))
        app.sendEvent(pv, QtGui.QKeyEvent(typ, key, QtCore.Qt.NoModifier))
    pump(0.5)


def main():
    global doc
    pump(1.5)
    Gui.activateWorkbench("TechDrawWorkbench")
    pump(1.0)
    # FreeCAD keeps 20 undo steps by default (Preferences, Document, Maximum Undo/Redo steps): more, so that every
    # step this script takes is still in UndoNames at the end
    App.ParamGet("User parameter:BaseApp/Preferences/Document").SetInt("MaxUndoSize", 200)
    doc = App.newDocument("Unnamed")
    pump(0.5)
    import Part
    import TechDraw
    import TechDrawGui
    res["breps"] = BREPS
    for name in ("plate", "bracket"):
        o = doc.addObject("Part::Feature", name)
        o.Shape = Part.read(os.path.join(BREPS, name + ".brep"))
    doc.recompute()
    Gui.SendMsgToActiveView("ViewFit")
    pump(0.5)
    safe("workbench", lambda: Gui.activeWorkbench().name())
    safe("menubar", lambda: [a.text() for a in mw.menuBar().actions() if a.isVisible()])
    safe("menus_nopage", menus)
    safe("toolbars_nopage", toolbars)

    def page_default():
        undo = list(doc.UndoNames)
        before = {o.Name for o in doc.Objects}
        Gui.runCommand("TechDraw_PageDefault", 0)
        settle(1.5)
        made = [o for o in doc.Objects if o.Name not in before]
        out = {"made": [props(o) for o in made], "undo": new_undo(undo), "mdi": mdi_titles()}
        tpl = next((o for o in made if o.isDerivedFrom("TechDraw::DrawTemplate")), None)
        if tpl is not None:
            out["EditableTexts"] = val(tpl.EditableTexts)
        return out
    safe("page_default", page_default)
    Gui.Selection.clearSelection()
    pump(0.5)
    safe("menus_page", menus)
    safe("toolbars_page", toolbars)

    safe("view_made", lambda: run_cmd("TechDraw_View", ["plate"]))
    # the panel recorded while open is "panel"; kept under its own key as asked
    if "view_made" in res:
        res["view_panel"] = res["view_made"].get("panel")

    def projgroup_after():
        boxes = [w for w in mw.findChildren(QtWidgets.QCheckBox) if w.isVisible() and w.objectName().startswith("chk")]
        d = {"checkboxes": [{"name": b.objectName(), "text": b.text(), "tip": b.toolTip(), "checked": b.isChecked(),
                             "enabled": b.isEnabled()} for b in boxes]}
        ticked = []
        for b in boxes:
            t = (b.toolTip() + " " + b.text()).lower()
            if (t.strip().startswith("top") or t.strip().startswith("right")) and not b.isChecked():
                b.click()
                ticked.append(b.objectName())
                pump(1.0)
        d["ticked"] = ticked
        pump(2.0)
        d["panel_checked"] = task_widgets()
        return d
    safe("projgroup_made", lambda: run_cmd("TechDraw_ProjectionGroup", ["plate"], projgroup_after, wait=3.0))
    if "projgroup_made" in res:
        res["projgroup_panel"] = res["projgroup_made"].get("panel")
        res["projgroup_panel_checked"] = res["projgroup_made"].get("after", {}).get("panel_checked")

    safe("section_made", lambda: section("pbRight", "A"))
    if "section_made" in res:
        res["section_panel"] = res["section_made"].get("panel")
        res["section_panel_after"] = res["section_made"].get("after", {}).get("panel_after")
    safe("section_up_made", lambda: section("pbUp"))
    safe("section_left_made", lambda: section("pbLeft"))
    safe("section_down_made", lambda: section("pbDown"))

    def top_view():
        v = doc.getObject("View")
        v.Direction = V(0, 0, 1)
        v.recompute()
        settle(3.0)
        v = doc.getObject("View")
        out = {"Direction": val(v.Direction), "XDirection": val(v.XDirection)}
        try:
            out["edges"] = len(v.getVisibleEdges())
            out["vertices"] = len(v.getVisibleVertexes())
        except Exception as e:
            out["edges"] = f"<{e}>"
        return out
    safe("view_top", top_view)

    def edge_sel(fn):
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, "View", "Edge2")
        pump(0.6)
        out = fn()
        Gui.Selection.clearSelection()
        return out
    safe("menus_edge_selected", lambda: edge_sel(menus))
    safe("toolbars_edge_selected", lambda: edge_sel(toolbars))

    safe("dim_horizontal", lambda: dimension("TechDraw_HorizontalDimension", [("View", "Edge2")]))
    safe("dim_vertical", lambda: dimension("TechDraw_VerticalDimension", [("View", "Edge4")]))
    safe("dim_length", lambda: dimension("TechDraw_LengthDimension", [("View", "Edge0")]))
    safe("dim_radius", lambda: dimension("TechDraw_RadiusDimension", [("View", "Edge1")]))
    safe("dim_diameter", lambda: dimension("TechDraw_DiameterDimension", [("View", "Edge5")]))
    safe("dim_two_vertex", lambda: dimension("TechDraw_LengthDimension", [("View", "Vertex1"), ("View", "Vertex6")]))

    def smart():
        activate_page()
        r = dimension("TechDraw_Dimension", [("View", "Edge2")])
        r["active_dialog_after"] = str(Gui.Control.activeDialog())
        pv = page_view()
        r["page_cursor"] = None if pv is None else int(pv.viewport().cursor().shape().value)
        key_page(QtCore.Qt.Key_Escape)
        key_page(QtCore.Qt.Key_Escape)
        close_task()
        r["after_escape"] = {"objects": [o.Name for o in doc.Objects], "undo": list(doc.UndoNames)[:3]}
        return r
    safe("dim_smart", smart)

    safe("view_bracket", lambda: run_cmd("TechDraw_View", ["bracket"]))
    safe("dim_angle", lambda: dimension("TechDraw_AngleDimension", [("View001", "Edge3"), ("View001", "Edge0")]))

    def dim_panel():
        Gui.Selection.clearSelection()
        d = doc.getObject("Dimension")
        Gui.ActiveDocument.setEdit(d, 0)
        pump(1.5)
        out = {"dialog": str(Gui.Control.activeDialog()), "panel": task_widgets()}
        close_task()
        Gui.ActiveDocument.resetEdit()
        pump(0.5)
        return out
    safe("dimension_panel", dim_panel)

    def annotation():
        activate_page()
        return run_cmd("TechDraw_Annotation", [])
    safe("annotation_made", annotation)

    def balloon():
        activate_page()
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, "View")
        pump(0.3)
        undo = list(doc.UndoNames)
        before = {o.Name for o in doc.Objects}
        holder = {}
        t = watch_dialogs(holder)
        Gui.runCommand("TechDraw_Balloon", 0)
        pump(1.0)
        pv = page_view()
        out = {"page_view": pv is not None, "cursor": None if pv is None else int(pv.viewport().cursor().shape().value)}
        try:
            out["balloonPlacing"] = pv.property("balloonPlacing")
        except Exception:
            pass
        v = doc.getObject("View")
        if pv is not None:
            out["click"] = click_page(v.X.Value * 10 + 150, -v.Y.Value * 10 - 150)
        settle(1.0)
        t.stop()
        out["dialogs"] = holder.get("dialogs", [])
        out["made"] = [props(o) for o in doc.Objects if o.Name not in before]
        out["undo"] = new_undo(undo)
        out["panel"] = task_widgets()
        close_task()
        return out
    safe("balloon_made", balloon)

    safe("tree", tree_rows)
    for key, name in (("Page", "Page"), ("Template", "Template"), ("View", "View"), ("ProjGroup", "ProjGroup"),
                      ("SectionView", "SectionView"), ("Dimension", "Dimension"), ("Annotation", "Annotation")):
        safe("props_" + key, lambda name=name: property_view(doc.getObject(name)))

    def front():
        g = doc.getObject("ProjGroup")
        f = next(o for o in g.Views if getattr(o, "Type", "") == "Front")
        return {"name": f.Name, "rows": property_view(f)}
    safe("props_Front", front)

    def undo():
        before = list(doc.UndoNames)
        objs = [o.Name for o in doc.Objects]
        Gui.runCommand("Std_Undo", 0)
        settle(1.0)
        mid = list(doc.UndoNames)
        objs_mid = [o.Name for o in doc.Objects]
        redo_names = list(doc.RedoNames)
        Gui.runCommand("Std_Redo", 0)
        settle(1.0)
        objs_after = [o.Name for o in doc.Objects]
        return {"before": before, "after_undo": mid, "redo_names": redo_names, "after_redo": list(doc.UndoNames),
                "gone": [n for n in objs if n not in objs_mid], "back": [n for n in objs if n not in objs_mid and n in objs_after],
                "missing_after_redo": [n for n in objs if n not in objs_after]}
    safe("undo", undo)

    page = doc.getObject("Page")
    tmp = tempfile.mkdtemp(prefix="fctechdraw")

    def export_state():
        return [{"Name": o.Name, "TypeId": o.TypeId, "X": val(getattr(o, "X", None)), "Y": val(getattr(o, "Y", None)),
                 "Scale": val(getattr(o, "Scale", None))} for o in page.Views]
    safe("export_state", export_state)

    def svg():
        p = os.path.join(tmp, "page.svg")
        TechDrawGui.exportPageAsSvg(page, p)
        pump(0.5)
        return open(p, encoding="utf-8", errors="replace").read()
    safe("page_svg", svg)

    def dxf():
        p = os.path.join(tmp, "page.dxf")
        TechDraw.writeDXFPage(page, p)
        return open(p, encoding="utf-8", errors="replace").read()
    safe("page_dxf", dxf)

    def pdf():
        p = os.path.join(tmp, "page.pdf")
        TechDrawGui.exportPageAsPdf(page, p)
        pump(0.5)
        b = open(p, "rb").read()
        return {"size": len(b), "head": b[:200].decode("latin-1")}
    safe("page_pdf_bytes", pdf)

    def smart_click():
        """TechDraw_Dimension again with Edge2 selected, and a click on the page above the view: what the click does."""
        activate_page()
        undo = list(doc.UndoNames)
        r = dimension("TechDraw_Dimension", [("View", "Edge2")])
        v = doc.getObject("View")
        r["click"] = click_page(v.X.Value * 10, -(v.Y.Value + 25) * 10)
        pump(1.5)
        r["after_click"] = {"objects": [o.Name for o in doc.Objects], "undo": new_undo(undo)["head"],
                            "panel": task_widgets()}
        key_page(QtCore.Qt.Key_Escape)
        key_page(QtCore.Qt.Key_Escape)
        close_task()
        settle(1.0)
        made = [o for o in doc.Objects if o.Name not in {m["Name"] for m in res["export_state"]} and
                o.isDerivedFrom("TechDraw::DrawViewDimension")]
        r["after_escape"] = {"objects": [o.Name for o in doc.Objects], "undo": new_undo(undo)["head"],
                             "dimensions": [{k: val(getattr(o, k)) for k in DIM_KEYS} for o in made]}
        return r
    safe("dim_smart_click", smart_click)
    safe("undo_names", lambda: list(doc.UndoNames))
    save()
    os._exit(0)


QtCore.QTimer.singleShot(500, main)

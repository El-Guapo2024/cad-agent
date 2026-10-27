# SPDX-License-Identifier: LGPL-2.1-or-later
# Runs inside FreeCAD's GUI (fctechdraw_hatch.py starts it under fclaunch, windows kept off the screen): what the real
# TechDraw workbench does with its hatching tools, for the TechDraw page to be compared with. Writes fctechdraw_hatch.json
# into FCGUI_OUT:
#   states_face, wrong_*   the entries for a face selected; the messages for no selection, a view with no faces, an edge, a page
#   geomhatch, geomhatch_cancel   TechDraw_GeometricHatch on Face0: the panel (TaskGeomHatch), its values changed, OK / Cancel; the
#                                 objects made with their properties and view provider properties, the undo steps, the tree
#   hatch, hatch_again, hatch_edit, geomhatch_edit   TechDraw_Hatch on Face1 (TaskHatch), a second time (Replace hatch?), and the
#                                 edit panels of the hatches made
#   tree, props_*          the tree's rows with the hatches; each hatch's property view (Data and View tabs)
#   *_svg, final_dxf       the page exported with the hatches
import json
import os
import tempfile
import time
import traceback

import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtCore, QtGui, QtWidgets

OUT = os.environ["FCGUI_OUT"]
BREPS = os.environ["FCTECHDRAW_BREPS"]
mw = Gui.getMainWindow()
app = QtWidgets.QApplication.instance()
res = {"errors": {}}
mw.resize(1280, 800)
V = App.Vector
doc = None


def save():
    json.dump(res, open(os.path.join(OUT, "fctechdraw_hatch.json"), "w"), indent=1, default=repr)


def bail():
    res["errors"]["hung"] = "stopped after 1500 s"
    save()
    os._exit(0)


QtCore.QTimer.singleShot(1500000, bail)


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
        d = {"text": a.text(), "name": a.objectName() or a.data(), "enabled": a.isEnabled(), "tip": a.toolTip()}
        sub = a.menu()
        if sub is not None and depth < 4:
            d["menu"] = dump_menu(sub, depth + 1)
        out.append(d)
    return out


def menus():
    for a in mw.menuBar().actions():
        if a.text().replace("&", "") == "TechDraw":
            return dump_menu(a.menu())
    return []


def toolbars():
    out = []
    for tb in mw.findChildren(QtWidgets.QToolBar):
        if not tb.windowTitle().startswith("TechDraw"):
            continue
        row = {"title": tb.windowTitle(), "buttons": []}
        for a in tb.actions():
            if a.isSeparator() or not a.isVisible():
                continue
            w = tb.widgetForAction(a)
            b = {"name": a.objectName() or "", "text": a.text(), "enabled": a.isEnabled()}
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
            elif cls.endswith("TaskHeader") or cls == "QSint::TaskHeader":
                d["text"] = " ".join(lbl.text() for lbl in w.findChildren(QtWidgets.QLabel) if lbl.text())
            elif cls == "Gui::ColorButton":
                d["color"] = w.color().name()
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


def child(name, cls=QtWidgets.QWidget):
    for w in mw.findChildren(cls, name):
        if w.isVisible():
            return w
    return None


def set_quantity(name, text):
    """A Gui::QuantitySpinBox typed into, as a person does."""
    w = child(name)
    if w is None:
        return False
    le = w.lineEdit()
    le.selectAll()
    le.setText(text)
    pump(0.2)
    le.editingFinished.emit()
    pump(0.5)
    return True


def close_task():
    if Gui.Control.activeDialog():
        Gui.Control.closeDialog()
        pump(0.5)


def val(v):
    if isinstance(v, (bool, int, float, str, type(None))):
        return v if not isinstance(v, str) or len(v) < 4000 else v[:4000] + "..."
    if isinstance(v, App.Vector):
        return [v.x, v.y, v.z]
    if isinstance(v, App.Units.Quantity):
        return v.Value
    if isinstance(v, App.Placement):
        return {"base": val(v.Base), "rotation": list(v.Rotation.Q)}
    if isinstance(v, App.DocumentObject):
        return v.Name
    if isinstance(v, (list, tuple)):
        return [val(x) for x in v]
    if isinstance(v, dict):
        return {str(k): val(x) for k, x in v.items()}
    s = str(v)
    return s if len(s) < 2000 else s[:2000] + "..."


def obj_attrs(o):
    out = {}
    for a in dir(o):
        if a.startswith("_") or a in ("clone", "copy"):
            continue
        try:
            x = getattr(o, a)
        except Exception:
            continue
        if callable(x):
            continue
        out[a] = val(x)
    return out


def view_state(v):
    n = 0
    while True:
        try:
            v.getEdgeByIndex(n)
        except Exception:
            break
        n += 1
    nv = 0
    while True:
        try:
            v.getVertexByIndex(nv)
        except Exception:
            break
        nv += 1
    edges = []
    for i in range(n):
        e = v.getEdgeByIndex(i)
        edges.append({"curve": type(e.Curve).__name__, "start": val(e.Vertexes[0].Point), "end": val(e.Vertexes[-1].Point)})
    verts = [val(v.getVertexByIndex(i).Point) for i in range(nv)]
    return {"CosmeticVertexes": [obj_attrs(c) for c in v.CosmeticVertexes],
            "CosmeticEdges": [obj_attrs(c) for c in v.CosmeticEdges],
            "CenterLines": [obj_attrs(c) for c in v.CenterLines],
            "GeomFormats": [obj_attrs(c) if not isinstance(c, (str, int, float)) else c for c in v.GeomFormats],
            "edges": edges, "vertices": verts}


def new_undo(before):
    names = list(doc.UndoNames)
    n = len(names) - len(before)
    return {"head": names[:max(n, 0)], "all": names[:6]}


def settle(sec=1.5):
    pump(sec)
    doc.recompute()
    pump(0.8)


def select(sels):
    Gui.Selection.clearSelection()
    for s in sels:
        if isinstance(s, tuple):
            Gui.Selection.addSelection(doc.Name, s[0], s[1])
        else:
            Gui.Selection.addSelection(doc.Name, s)
    pump(0.4)


def run_tool(cmd, sels, edit=None, ok=True, wait=2.0):
    """Select sels, run cmd, record the panel, call edit() (typing into it), then OK (or Cancel when ok is False)."""
    select(sels)
    undo = list(doc.UndoNames)
    holder = {}
    t = watch_dialogs(holder)
    out = {"selection": [[x.ObjectName, list(x.SubElementNames)] for x in Gui.Selection.getSelectionEx()]}
    Gui.runCommand(cmd, 0)
    pump(wait)
    out["dialog_open"] = bool(Gui.Control.activeDialog())
    out["panel"] = task_widgets()
    out["view_after_open"] = view_state(doc.getObject("View"))
    out["undo_after_open"] = new_undo(undo)
    if edit is not None:
        out["edit"] = edit()
        pump(0.8)
        out["panel_after_edit"] = task_widgets()
        out["view_after_edit"] = view_state(doc.getObject("View"))
    if Gui.Control.activeDialog():
        out["button"] = click_button("OK" if ok else "Cancel")
    settle()
    t.stop()
    out["dialogs"] = holder.get("dialogs", [])
    out["undo"] = new_undo(undo)
    out["view"] = view_state(doc.getObject("View"))
    out["tasks_after"] = task_widgets()
    close_task()
    return out


def run_plain(cmd, sels):
    """A command without a panel (Midpoints, Quadrants, the eraser)."""
    select(sels)
    undo = list(doc.UndoNames)
    holder = {}
    t = watch_dialogs(holder)
    out = {"selection": [[x.ObjectName, list(x.SubElementNames)] for x in Gui.Selection.getSelectionEx()]}
    Gui.runCommand(cmd, 0)
    settle(1.5)
    t.stop()
    out["dialogs"] = holder.get("dialogs", [])
    out["undo"] = new_undo(undo)
    out["view"] = view_state(doc.getObject("View"))
    out["dialog_open"] = bool(Gui.Control.activeDialog())
    close_task()
    return out


KEEP_MENUS = ("Add Lines", "Add Vertices", "Centerlines/Threading", "Remove Cosmetic Object", "Hatching", "Annotations")


def states(sels):
    select(sels)
    m = [e for e in menus() if e.get("text") in KEEP_MENUS or e.get("name") == "TechDraw_CosmeticEraser"]
    tb = [t for t in toolbars() if t["title"] in ("TechDraw Annotation", "TechDraw Centerlines", "TechDraw Decoration")]
    return {"selection": [[x.ObjectName, list(x.SubElementNames)] for x in Gui.Selection.getSelectionEx()],
            "menu": m, "toolbars": tb}


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
                    if not kids:
                        continue
                    row += kids
                got += row
            return got
        out.append(walk(QtCore.QModelIndex(), 0))
    return out


def property_view(obj):
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(obj)
    pump(0.6)
    out = {}
    tabs = [t for t in mw.findChildren(QtWidgets.QTabWidget)
            if t.parent() is not None and t.parent().metaObject().className() == "Gui::PropertyView"]
    for tw in tabs:
        cur = tw.currentIndex()
        for i in range(tw.count()):
            tw.setCurrentIndex(i)
            pump(0.3)
            out[tw.tabText(i).replace("&", "").lower()] = editor_rows()
        tw.setCurrentIndex(cur)
    Gui.Selection.clearSelection()
    return out


def vp_props(name):
    o = Gui.ActiveDocument.getObject(name)
    out = {}
    for p in o.PropertiesList:
        try:
            out[p] = val(getattr(o, p))
        except Exception as e:
            out[p] = f"<{e}>"
    return out


def doc_objects(kinds):
    out = []
    for o in doc.Objects:
        if o.TypeId in kinds:
            d = {"Name": o.Name, "Label": o.Label, "TypeId": o.TypeId}
            for p in o.PropertiesList:
                if p in ("Proxy", "ExpressionEngine", "Shape"):
                    continue
                try:
                    d[p] = val(getattr(o, p))
                except Exception as e:
                    d[p] = f"<{e}>"
            d["ViewProvider"] = vp_props(o.Name)
            out.append(d)
    return out


def tree_rows():
    tree = [t for t in mw.findChildren(QtWidgets.QTreeWidget) if t.metaObject().className() == "Gui::TreeWidget"][0]
    tree.expandAll()
    pump(0.4)
    rows = []

    def walk(item, depth):
        rows.append({"text": item.text(0), "depth": depth, "children": item.childCount()})
        for i in range(item.childCount()):
            walk(item.child(i), depth + 1)
    for i in range(tree.topLevelItemCount()):
        walk(tree.topLevelItem(i), 0)
    return rows


HATCH_TYPES = ("TechDraw::DrawHatch", "TechDraw::DrawGeomHatch")


def hatch_state():
    return {"objects": doc_objects(HATCH_TYPES)}


def run_cmd_plain(cmd, sels):
    """A command that may only show a message (or the Replace question)."""
    select(sels)
    undo = list(doc.UndoNames)
    holder = {}
    t = watch_dialogs(holder)
    out = {"selection": [[x.ObjectName, list(x.SubElementNames)] for x in Gui.Selection.getSelectionEx()]}
    Gui.runCommand(cmd, 0)
    pump(2.0)
    out["dialog_open"] = bool(Gui.Control.activeDialog())
    out["panel"] = task_widgets()
    t.stop()
    out["dialogs"] = holder.get("dialogs", [])
    out["undo_after_open"] = new_undo(undo)
    return out


def hatch_tool(cmd, sels, edit=None, ok=True):
    out = run_tool(cmd, sels, edit, ok)
    out["hatches"] = hatch_state()
    out["tree"] = tree_rows()
    return out


def main():
    global doc
    pump(1.5)
    Gui.activateWorkbench("TechDrawWorkbench")
    pump(1.0)
    App.ParamGet("User parameter:BaseApp/Preferences/Document").SetInt("MaxUndoSize", 200)
    doc = App.newDocument("Unnamed")
    pump(0.5)
    import Part
    import TechDraw
    import TechDrawGui
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

    safe("states_face", lambda: states([("View", "Face0")]))
    safe("wrong_nothing", lambda: run_cmd_plain("TechDraw_Hatch", []))
    safe("wrong_nothing_geom", lambda: run_cmd_plain("TechDraw_GeometricHatch", []))
    safe("wrong_view_only", lambda: run_cmd_plain("TechDraw_Hatch", ["View"]))
    safe("wrong_edge", lambda: run_cmd_plain("TechDraw_GeometricHatch", [("View", "Edge2")]))
    safe("wrong_page", lambda: run_cmd_plain("TechDraw_Hatch", ["Page"]))

    # geometric hatch
    def geom_edit():
        info = {}
        cb = child("cbName", QtWidgets.QComboBox)
        if cb is not None:
            info["names"] = [cb.itemText(i) for i in range(cb.count())]
            cb.setCurrentIndex(3)
            pump(0.5)
            info["name"] = cb.currentText()
        info["scale"] = set_quantity("sbScale", "2")
        info["weight"] = set_quantity("sbWeight", "0.3 mm")
        info["rotation"] = set_quantity("dsbRotation", "15")
        info["ox"] = set_quantity("dsbOffsetX", "1")
        info["oy"] = set_quantity("dsbOffsetY", "2")
        return info
    safe("geomhatch", lambda: hatch_tool("TechDraw_GeometricHatch", [("View", "Face0")], geom_edit))
    safe("geomhatch_svg", lambda: svg_of())
    safe("geomhatch_cancel", lambda: hatch_tool("TechDraw_GeometricHatch", [("View", "Face1")], geom_edit, ok=False))

    # image hatch
    def hatch_edit():
        return {"scale": set_quantity("sbScale", "2"), "rotation": set_quantity("dsbRotation", "10"),
                "ox": set_quantity("dsbOffsetX", "1"), "oy": set_quantity("dsbOffsetY", "2")}
    safe("hatch", lambda: hatch_tool("TechDraw_Hatch", [("View", "Face1")], hatch_edit))
    safe("hatch_svg", lambda: svg_of())
    safe("hatch_again", lambda: hatch_tool("TechDraw_Hatch", [("View", "Face1")], None))

    def edit_existing():
        h = [o for o in doc.Objects if o.TypeId == "TechDraw::DrawHatch"][-1]
        Gui.Selection.clearSelection()
        undo = list(doc.UndoNames)
        Gui.ActiveDocument.setEdit(h, 0)
        pump(1.5)
        out = {"object": h.Name, "dialog_open": bool(Gui.Control.activeDialog()), "panel": task_widgets()}
        out["edit"] = {"scale": set_quantity("sbScale", "3")}
        click_button("OK")
        settle()
        out["undo"] = new_undo(undo)
        out["hatches"] = hatch_state()
        close_task()
        return out
    safe("hatch_edit", edit_existing)

    def geom_edit_existing():
        h = [o for o in doc.Objects if o.TypeId == "TechDraw::DrawGeomHatch"][-1]
        Gui.Selection.clearSelection()
        undo = list(doc.UndoNames)
        Gui.ActiveDocument.setEdit(h, 0)
        pump(1.5)
        out = {"object": h.Name, "dialog_open": bool(Gui.Control.activeDialog()), "panel": task_widgets()}
        out["edit"] = {"scale": set_quantity("sbScale", "1")}
        click_button("OK")
        settle()
        out["undo"] = new_undo(undo)
        out["hatches"] = hatch_state()
        close_task()
        return out
    safe("geomhatch_edit", geom_edit_existing)

    safe("tree", tree_rows)
    for o in doc.Objects:
        if o.TypeId in HATCH_TYPES:
            safe("props_" + o.TypeId.split("::")[1] + "_" + o.Name, lambda o=o: property_view(o))
    safe("final_svg", lambda: svg_of())
    safe("final_dxf", lambda: dxf_of())
    safe("undo_names", lambda: list(doc.UndoNames))
    save()
    os._exit(0)


def svg_of():
    import TechDrawGui
    p = os.path.join(tempfile.mkdtemp(prefix="fctechdrawhatch"), "page.svg")
    TechDrawGui.exportPageAsSvg(doc.getObject("Page"), p)
    pump(0.5)
    return open(p, encoding="utf-8", errors="replace").read()


def dxf_of():
    import TechDraw
    p = os.path.join(tempfile.mkdtemp(prefix="fctechdrawhatch"), "page.dxf")
    TechDraw.writeDXFPage(doc.getObject("Page"), p)
    return open(p, encoding="utf-8", errors="replace").read()


QtCore.QTimer.singleShot(500, main)

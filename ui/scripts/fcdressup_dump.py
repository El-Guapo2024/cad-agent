# Runs inside FreeCAD's GUI (fcdressup.py starts it under fclaunch, windows kept off the screen): what the real PartDesign
# workbench shows for its dress-up features, for dressupcheck.mjs to compare the page with. Writes fcdressup.json:
#   menu        the Part Design menu's Dress-Up Features submenu, and the Dress-Up toolbar (text, command, enabled)
#   <case>      for each case: a Body with a 40 x 20 x 5 Pad, the case's elements selected on the Pad, the command run;
#               then the task panel's widgets (task), the new feature's Base, its properties (names, groups, values,
#               types, enumerations, editor modes), the Select button pressed (task_select: the button's text, what is
#               shown), one more element picked in the 3D view while selecting (Base after it: picked), the property
#               view's rows for the feature after OK, the tree's rows, the transaction's name (Undo's text), and the
#               feature's Base, validity and volume
# Cases: fillet (Edge1 then Edge2 picked), fillet_all (the Pad selected whole: Use all edges), chamfer (Edge4), draft
# (Face1, Face2 picked), thickness (Face6, Face1 picked), none_fillet (nothing selected: Base is the Tip and no element).
import json
import os
import time
import traceback

import FreeCAD as App
import FreeCADGui as Gui
import Part
import Sketcher
from PySide6 import QtCore, QtWidgets

OUT = os.environ["FCGUI_OUT"]
mw = Gui.getMainWindow()
app = QtWidgets.QApplication.instance()
res = {"errors": {}}
mw.resize(1280, 800)
V = App.Vector


def bail():
    res["errors"]["hung"] = "stopped after 600 s"
    json.dump(res, open(os.path.join(OUT, "fcdressup.json"), "w"), indent=1)
    os._exit(0)


QtCore.QTimer.singleShot(600000, bail)


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
        d = {"text": a.text(), "name": a.objectName() or "", "enabled": a.isEnabled()}
        if a.menu() is not None and depth < 3:
            d["menu"] = dump_menu(a.menu(), depth + 1)
        out.append(d)
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
                view = w.view()
                d["items"] = [w.itemText(i) for i in range(w.count()) if not view.isRowHidden(i)]
                d["current"] = w.currentText()
            elif isinstance(w, QtWidgets.QAbstractSpinBox):
                d["text"] = w.text()
            elif isinstance(w, QtWidgets.QLineEdit):
                d["text"] = w.text()
            elif isinstance(w, QtWidgets.QListWidget):
                d["items"] = [w.item(i).text() for i in range(w.count())]
                d["actions"] = [a.text() + ("\t" + a.shortcut().toString() if not a.shortcut().isEmpty() else "") for a in w.actions()]
            elif cls.endswith("TaskBoxHeader") or cls.endswith("TaskHeader") or cls == "QSint::TaskHeader":
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
            pump(0.8)
            return True
    return False


def tree_rows():
    tree = [t for t in mw.findChildren(QtWidgets.QTreeWidget) if t.metaObject().className() == "Gui::TreeWidget"][0]
    tree.expandAll()
    pump(0.3)
    rows = []

    def walk(item, depth):
        rows.append({"text": item.text(0), "depth": depth, "bold": item.font(0).bold(),
                     "fg": item.foreground(0).color().name() if item.foreground(0).style() else None})
        for i in range(item.childCount()):
            walk(item.child(i), depth + 1)

    for i in range(tree.topLevelItemCount()):
        walk(tree.topLevelItem(i), 0)
    return rows


def property_view(obj):
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(obj)
    pump(0.6)
    out = []
    for ed in mw.findChildren(QtWidgets.QTreeView):
        if ed.metaObject().className() != "Gui::PropertyEditor::PropertyEditor" or not ed.isVisible():
            continue
        model = ed.model()
        rows = []

        def walk(parent, depth):
            for r in range(model.rowCount(parent)):
                i0, i1 = model.index(r, 0, parent), model.index(r, 1, parent)
                rows.append({"depth": depth, "name": model.data(i0), "value": model.data(i1),
                             "group": not model.hasIndex(r, 1, parent) or model.flags(i1) == QtCore.Qt.NoItemFlags,
                             "editable": bool(model.flags(i1) & QtCore.Qt.ItemIsEditable)})
                if depth < 1:
                    walk(i0, depth + 1)
        walk(QtCore.QModelIndex(), 0)
        out.append(rows)
    Gui.Selection.clearSelection()
    return out


def props(f):
    return {"values": {p: str(getattr(f, p)) for p in f.PropertiesList},
            "groups": {p: f.getGroupOfProperty(p) for p in f.PropertiesList},
            "types": {p: f.getTypeIdOfProperty(p) for p in f.PropertiesList},
            "modes": {p: f.getEditorMode(p) for p in f.PropertiesList},
            "enums": {p: f.getEnumerationsOfProperty(p) for p in f.PropertiesList
                      if f.getTypeIdOfProperty(p) == "App::PropertyEnumeration"}}


def base_of(f):
    b = f.Base
    return [b[0].Name, list(b[1])] if b else None


def undo_text():
    for a in mw.findChildren(QtGui_Action()):
        pass
    return [doc.getUndoNames()[:3]] if hasattr(doc, "getUndoNames") else None


def QtGui_Action():
    from PySide6 import QtGui
    return QtGui.QAction


pump(1.5)
Gui.activateWorkbench("PartDesignWorkbench")
pump(1.0)


def menu():
    out = {}
    for a in mw.menuBar().actions():
        if a.text() == "&Part Design":
            for s in dump_menu(a.menu()):
                if s.get("text", "").replace("&", "") == "Dress-Up Features":
                    out["menu"] = s["menu"]
    for tb in mw.findChildren(QtWidgets.QToolBar):
        if tb.windowTitle() == "Part Design Dress-Up Features":
            out["toolbar"] = [{"name": a.objectName(), "text": a.text(), "tip": a.toolTip(), "enabled": a.isEnabled()}
                              for a in tb.actions() if not a.isSeparator() and a.isVisible()]
    return out


def make_body(name):
    global doc
    doc = App.newDocument(name)
    pump(0.4)
    Gui.runCommand("PartDesign_Body", 0)
    pump(0.6)
    body = doc.getObject("Body")
    sk = body.newObject("Sketcher::SketchObject", "Sketch")
    sk.AttachmentSupport = [(doc.getObject("XY_Plane"), "")]
    sk.MapMode = "FlatFace"
    pts = [V(0, 0, 0), V(40, 0, 0), V(40, 20, 0), V(0, 20, 0)]
    for i in range(4):
        sk.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 4]), False)
    for i in range(4):
        sk.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % 4, 1))
    pad = body.newObject("PartDesign::Pad", "Pad")
    pad.Profile = sk
    pad.Length = 5
    doc.recompute()
    pump(0.6)
    return body, pad


def case(command, subs, pick=None, whole=False):
    body, pad = make_body("Doc" + command.split("_")[1])
    Gui.Selection.clearSelection()
    if whole:
        Gui.Selection.addSelection(pad)
    for s in subs:
        Gui.Selection.addSelection(doc.Name, pad.Name, s)
    pump(0.4)
    undo_before = doc.UndoCount
    Gui.runCommand(command, 0)
    pump(1.5)
    edit = Gui.ActiveDocument.getInEdit()
    f = edit.Object if edit else None
    out = {"task": task_widgets(), "in_edit": f.Name if f else None, "undo_names": doc.UndoNames[:2] if hasattr(doc, "UndoNames") else None,
           "undo_count_change": doc.UndoCount - undo_before}
    if f is None:
        return out
    out["base"] = base_of(f)
    out["props"] = props(f)
    out["visible_during"] = {o.Name: o.Visibility for o in body.Group if hasattr(o, "Visibility")}
    # Select: the button turns to Confirm Selection and the Pad shows
    sel = [b for b in mw.findChildren(QtWidgets.QToolButton) if b.isVisible() and b.objectName() == "buttonRefSel"]
    if sel and sel[0].isEnabled():
        if not sel[0].isChecked():
            sel[0].click()
            pump(0.8)
        out["task_select"] = task_widgets()
        out["visible_selecting"] = {o.Name: o.Visibility for o in body.Group if hasattr(o, "Visibility")}
        if pick:
            Gui.Selection.addSelection(doc.Name, pad.Name, pick)
            pump(1.0)
            out["picked"] = base_of(f)
            out["task_picked"] = task_widgets()
            # the same element again takes it off
            Gui.Selection.addSelection(doc.Name, pad.Name, pick)
            pump(1.0)
            out["picked_twice"] = base_of(f)
            Gui.Selection.addSelection(doc.Name, pad.Name, pick)
            pump(1.0)
        sel[0].click()
        pump(0.8)
        out["task_confirmed"] = task_widgets()
    out["ok"] = click_button("OK")
    pump(1.2)
    out["after"] = {"base": base_of(f), "valid": f.isValid(), "status": f.getStatusString(),
                    "volume": round(f.Shape.Volume, 6) if not f.Shape.isNull() else None, "tip": body.Tip.Name}
    out["undo_names_after"] = doc.UndoNames[:2] if hasattr(doc, "UndoNames") else None
    out["tree"] = tree_rows()
    out["property_view"] = property_view(f)
    return out


safe("menu", menu)
safe("fillet", lambda: case("PartDesign_Fillet", ["Edge1"], pick="Edge2"))
safe("fillet_all", lambda: case("PartDesign_Fillet", [], whole=True))
safe("chamfer", lambda: case("PartDesign_Chamfer", ["Edge4"], pick="Edge7"))
safe("draft", lambda: case("PartDesign_Draft", ["Face1"], pick="Face2"))
safe("thickness", lambda: case("PartDesign_Thickness", ["Face6"], pick="Face1"))
safe("none_fillet", lambda: case("PartDesign_Fillet", []))

json.dump(res, open(os.path.join(OUT, "fcdressup.json"), "w"), indent=1)
os._exit(0)

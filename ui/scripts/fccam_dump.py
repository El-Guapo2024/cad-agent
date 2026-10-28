# SPDX-License-Identifier: LGPL-2.1-or-later
# Runs inside FreeCAD's GUI (fccam.py starts it under fclaunch, windows kept off the screen): what the real CAM
# workbench shows, for the CAM page to be compared with. Writes fccam.json into FCGUI_OUT:
#   workbench            the CAM workbench's name, menu text and icon
#   menus_*, toolbars_*  the CAM menu and toolbars: no job, the plate selected, a job, an op selected
#   job_dialog           CAM_Job's dialog (DlgJobCreate.ui) with the plate selected
#   job_panel            the Job's task panel after the dialog's OK (PathEdit.ui), every tab
#   op_<command>         each op's task panel (its pages), from the faces selected, then OK
#   dressup_<command>    each dress-up's panel on a selected op, then OK
#   tree, props_*        the tree's rows; the property view of each kind of object
#   undo, undo_after, redo_after   doc.UndoNames, after Std_Undo, after Std_Redo
import json
import os
import time
import traceback

import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtCore, QtWidgets

OUT = os.environ["FCGUI_OUT"]
BREPS = os.environ["FCCAM_BREPS"]
mw = Gui.getMainWindow()
app = QtWidgets.QApplication.instance()
res = {"errors": {}}
mw.resize(1280, 800)


def save():
    json.dump(res, open(os.path.join(OUT, "fccam.json"), "w"), indent=1)


def bail():
    res["errors"]["hung"] = "stopped after 800 s"
    save()
    os._exit(0)


QtCore.QTimer.singleShot(800000, bail)


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


def close_message_boxes():
    out = []
    for w in app.topLevelWidgets():
        if isinstance(w, QtWidgets.QMessageBox) and w.isVisible():
            out.append({"title": w.windowTitle(), "text": w.text(), "buttons": [b.text() for b in w.buttons()]})
            w.reject()
    return out


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
        if a.text().replace("&", "") in ("CAM", "Path"):
            out[a.text()] = dump_menu(a.menu())
    return out


def toolbars():
    out = []
    for tb in mw.findChildren(QtWidgets.QToolBar):
        if not tb.isVisible() and not tb.windowTitle().startswith("CAM"):
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


def widget_rows(root, top=None):
    items = []
    for w in root.findChildren(QtWidgets.QWidget):
        if not w.isVisible():
            continue
        cls = w.metaObject().className()
        pos = w.mapTo(top or root, QtCore.QPoint(0, 0))
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
        elif isinstance(w, QtWidgets.QTableWidget):
            d["rows"] = [[(w.item(r, c).text() if w.item(r, c) else "") for c in range(w.columnCount())]
                         for r in range(w.rowCount())]
            d["header"] = [(w.horizontalHeaderItem(c).text() if w.horizontalHeaderItem(c) else "")
                           for c in range(w.columnCount())]
        elif isinstance(w, QtWidgets.QGroupBox):
            d["text"] = w.title()
            if w.isCheckable():
                d["checked"] = w.isChecked()
        elif isinstance(w, QtWidgets.QTabWidget):
            d["tabs"] = [w.tabText(i) for i in range(w.count())]
            d["current"] = w.tabText(w.currentIndex())
        elif isinstance(w, (QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit)):
            d["text"] = w.toPlainText()
        elif cls.endswith("TaskHeader") or cls == "QSint::TaskHeader":
            d["text"] = " ".join(lbl.text() for lbl in w.findChildren(QtWidgets.QLabel) if lbl.text())
        else:
            continue
        items.append(d)
    items.sort(key=lambda d: (d["y"], d["x"]))
    return items


def task_views():
    return [w for w in mw.findChildren(QtWidgets.QWidget)
            if w.metaObject().className() == "Gui::TaskView::TaskView" and w.isVisible()]


def task_dump():
    out = []
    for tv in task_views():
        page = {"rows": widget_rows(tv)}
        tabs = [t for t in tv.findChildren(QtWidgets.QTabWidget) if t.isVisible()]
        if tabs:
            page["tabs"] = []
            for tw in tabs:
                cur = tw.currentIndex()
                for i in range(tw.count()):
                    tw.setCurrentIndex(i)
                    pump(0.3)
                    page["tabs"].append({"tab": tw.tabText(i), "rows": widget_rows(tw.widget(i), tv)})
                tw.setCurrentIndex(cur)
                pump(0.2)
        out.append(page)
    return out


def click_button(text):
    for b in mw.findChildren(QtWidgets.QAbstractButton):
        if b.isVisible() and b.text().replace("&", "") == text:
            b.click()
            pump(1.5)
            return True
    return False


def accept_task():
    if not click_button("OK"):
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()
    pump(1.0)
    close_message_boxes()


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


def modal_then(fn_record, accept=True):
    """Before a command opens a modal dialog: record it when it is up, then OK it."""
    holder = {}

    def tick():
        w = app.activeModalWidget()
        if w is None:
            QtCore.QTimer.singleShot(200, tick)
            return
        pump(0.5)
        holder["dialog"] = {"title": w.windowTitle(), "rows": widget_rows(w)}
        fn_record(holder)
        if accept and isinstance(w, QtWidgets.QDialog):
            w.accept()
        else:
            w.reject()
    QtCore.QTimer.singleShot(300, tick)
    return holder


doc = App.newDocument("Unnamed")
import Part  # noqa: E402
plate = doc.addObject("Part::Feature", "plate")
plate.Shape = Part.read(os.path.join(BREPS, "plate.brep"))
doc.recompute()
pump(1)
Gui.activateWorkbench("CAMWorkbench")
pump(2)
wb = Gui.activeWorkbench()
res["workbench"] = {"name": wb.name(), "menu_text": getattr(wb, "MenuText", ""), "tip": getattr(wb, "ToolTip", "")}
safe("menus_empty", menus)
safe("toolbars_empty", toolbars)
Gui.Selection.addSelection(plate)
pump(0.5)
safe("menus_selected", menus)
safe("toolbars_selected", toolbars)


def make_job():
    holder = modal_then(lambda h: None)
    Gui.runCommand("CAM_Job")
    pump(3)
    res["job_dialog"] = holder.get("dialog")
    panel = task_dump()
    accept_task()
    return panel


safe("job_panel", make_job)
safe("undo_job", lambda: list(doc.UndoNames))
job = [o for o in doc.Objects if o.Name == "Job"][0]
safe("menus_job", menus)
safe("toolbars_job", toolbars)
clone = job.Model.Group[0]


def op(command, faces):
    def run():
        Gui.Selection.clearSelection()
        if faces:
            Gui.Selection.addSelection(doc.Name, clone.Name, faces[0])
            for f in faces[1:]:
                Gui.Selection.addSelection(doc.Name, clone.Name, f)
        pump(0.5)
        before = {o.Name for o in doc.Objects}
        Gui.runCommand(command)
        pump(3)
        panel = task_dump()
        accept_task()
        doc.recompute()
        pump(1)
        made = [o.Name for o in doc.Objects if o.Name not in before]
        return {"panel": panel, "made": made, "undo": list(doc.UndoNames), "messages": close_message_boxes()}
    return run


safe("op_CAM_Profile", op("CAM_Profile", []))
safe("op_CAM_Pocket_Shape", op("CAM_Pocket_Shape", ["Face17"]))
safe("op_CAM_Drilling", op("CAM_Drilling", ["Face7", "Face8", "Face9", "Face10"]))
safe("op_CAM_MillFace", op("CAM_MillFace", ["Face5"]))
safe("menus_op", lambda: (Gui.Selection.addSelection(doc.getObject("Profile")), pump(0.4), menus())[2])
safe("toolbars_op", toolbars)


def dressup(command, base):
    def run():
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.getObject(base))
        pump(0.5)
        before = {o.Name for o in doc.Objects}
        Gui.runCommand(command)
        pump(3)
        panel = task_dump()
        accept_task()
        doc.recompute()
        pump(1)
        made = [o.Name for o in doc.Objects if o.Name not in before]
        return {"panel": panel, "made": made, "undo": list(doc.UndoNames), "messages": close_message_boxes()}
    return run


safe("dressup_CAM_DressupTag", dressup("CAM_DressupTag", "Profile"))
safe("dressup_CAM_DressupDogbone", dressup("CAM_DressupDogbone", "Pocket_Shape"))
safe("tree", tree_rows)
safe("objects", lambda: [[o.Name, o.TypeId, o.Label] for o in doc.Objects])
for name in ("Job", "Stock", "SetupSheet", "TC__5mm_Endmill", "Endmill", "Profile", "Pocket_Shape", "Drilling",
             "MillFace", "DressupTag", "DressupDogbone", "Operations", "Clone"):
    o = doc.getObject(name)
    if o is not None:
        safe(f"props_{name}", lambda o=o: property_view(o))


def edit_tc():
    """A tool controller's task panel, as a double click opens it."""
    tc = doc.getObject("TC__5mm_Endmill")
    tc.ViewObject.Document.setEdit(tc.ViewObject, 0)
    pump(2)
    panel = task_dump()
    accept_task()
    return panel


safe("tc_panel", edit_tc)
safe("undo", lambda: list(doc.UndoNames))


def undo_redo():
    out = {}
    Gui.runCommand("Std_Undo")
    pump(1.5)
    out["undo_names"] = list(doc.UndoNames)
    out["redo_names"] = list(doc.RedoNames)
    out["tree"] = tree_rows()
    Gui.runCommand("Std_Redo")
    pump(1.5)
    out["after_redo_undo"] = list(doc.UndoNames)
    out["after_redo_tree"] = tree_rows()
    return out


safe("undo_redo", undo_redo)
save()
os._exit(0)

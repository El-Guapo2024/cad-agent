# SPDX-License-Identifier: LGPL-2.1-or-later
# Runs inside FreeCAD's GUI (fcassembly.py starts it under fclaunch, windows kept off the screen): what the real Assembly
# workbench shows, for assemblycheck.mjs to compare the page with. Writes fcassembly.json into FCGUI_OUT:
#   menus_*, toolbars_*  the Assembly menu and the workbench's toolbars, before there is an assembly and with one in edit
#   watchers             the Tasks panel with no task open (InitGui.py's task watchers, the Solver messages panel)
#   panel_<Type>         each Assembly_CreateJoint<Type>'s panel opened with nothing selected: its widgets, top to bottom
#   panel_insert         Assembly_InsertLink's panel
#   joint_*              a joint made from a selection of two elements and OK: the joint's Name and Label, its
#                        References, each component's Placement, the undo step, the Solver messages after it
#   tree                 the tree's rows (text, depth)
#   props_joint          the property view's rows of a joint
import json
import os
import time
import traceback

import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtCore, QtWidgets

OUT = os.environ["FCGUI_OUT"]
mw = Gui.getMainWindow()
app = QtWidgets.QApplication.instance()
res = {"errors": {}}
mw.resize(1280, 800)
V = App.Vector


def save():
    json.dump(res, open(os.path.join(OUT, "fcassembly.json"), "w"), indent=1)


def bail():
    res["errors"]["hung"] = "stopped after 600 s"
    save()
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
        if a.text() == "&Assembly":
            out[a.text()] = dump_menu(a.menu())
    return out


def toolbars():
    out = []
    for tb in mw.findChildren(QtWidgets.QToolBar):
        if tb.windowTitle() not in ("Assembly", "Assembly Joints"):
            continue
        row = {"title": tb.windowTitle(), "visible": tb.isVisible(), "buttons": []}
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


def close_task():
    if Gui.Control.activeDialog():
        Gui.Control.closeDialog()
        pump(0.5)


doc = None
asm = None


def plc(p):
    return [p.Base.x, p.Base.y, p.Base.z, *p.Rotation.Q]


def solver_message():
    """The Solver messages panel's text (TaskAssemblyMessages: a TaskSolverMessages, its labels)."""
    for w in app.allWidgets():
        if w.metaObject().className() == "AssemblyGui::TaskAssemblyMessages":
            return " ".join(lb.text() for lb in w.findChildren(QtWidgets.QLabel) if lb.text())
    return None


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
                rows.append({"depth": depth, "name": model.data(i0), "value": model.data(i1)})
                if depth < 1:
                    walk(i0, depth + 1)
        walk(QtCore.QModelIndex(), 0)
        out.append(rows)
    Gui.Selection.clearSelection()
    return out


def centre(sub):
    """A point on the element sub ("Plate.Face6") as the view would hand it to a click: the element's centre of mass."""
    comp, el = sub.split(".")
    return doc.getObject(comp).Shape.getElement(el).CenterOfMass


def joint(cmd, sub1, sub2, values=None):
    """A joint made as a person makes one: the command, a click on each element (the panel's selection observer gets
    the picked point, TaskAssemblyCreateJoint.addSelection), the panel's values, OK."""
    undo = list(doc.UndoNames)
    Gui.Selection.clearSelection()
    before = {o.Name for o in doc.Objects}
    holder = {}
    t = watch_dialogs(holder)
    Gui.runCommand(cmd, 0)
    pump(1.5)
    for sub in (sub1, sub2):
        c = centre(sub)
        Gui.Selection.addSelection(doc.Name, asm.Name, sub, c.x, c.y, c.z)
        pump(0.8)
    panel = task_widgets()
    import JointObject
    task = JointObject.activeTask
    for k, v in (values or {}).items():
        getattr(task.jForm, k).setProperty("rawValue", v)
        pump(0.6)
    panel_values = task_widgets()
    ok = click_button("OK")
    pump(1.0)
    t.stop()
    made = [o for o in doc.Objects if o.Name not in before]
    j = next((o for o in made if hasattr(o, "JointType")), None)
    return {"panel": panel, "panel_values": panel_values, "ok": ok, "dialogs": holder.get("dialogs", []),
            "joint": None if j is None else {"name": j.Name, "label": j.Label, "type": j.JointType,
                                            "reference1": [j.Reference1[0].Name, list(j.Reference1[1])],
                                            "reference2": [j.Reference2[0].Name, list(j.Reference2[1])]},
            "placements": {o.Name: plc(o.Placement) for o in asm.Group if o.TypeId == "App::Link"},
            "undo": [u for u in doc.UndoNames if u not in undo][:1] or doc.UndoNames[:1],
            "solver": solver_message(), "tasks": task_widgets()}


def main():
    global doc, asm
    pump(1.5)
    Gui.activateWorkbench("AssemblyWorkbench")
    pump(1.0)
    doc = App.newDocument("Unnamed")
    pump(0.5)
    safe("workbench", lambda: Gui.activeWorkbench().name())
    safe("menus_none", menus)
    safe("toolbars_none", toolbars)
    safe("watchers_none", task_widgets)
    plate = doc.addObject("Part::Box", "Box")
    plate.Length, plate.Width, plate.Height = 40, 30, 5
    pin = doc.addObject("Part::Cylinder", "Cylinder")
    pin.Radius, pin.Height = 3, 20
    bar = doc.addObject("Part::Box", "Box001")
    bar.Length, bar.Width, bar.Height = 30, 6, 4
    doc.recompute()
    for o in (plate, pin, bar):
        o.ViewObject.Visibility = False
    Gui.runCommand("Assembly_CreateAssembly", 0)
    pump(1.5)
    asm = doc.getObject("Assembly")
    safe("undo_new", lambda: doc.UndoNames[:1])
    Gui.activateWorkbench("PartWorkbench")         # the Solver messages panel comes with the workbench's activation
    pump(0.8)
    Gui.activateWorkbench("AssemblyWorkbench")
    pump(1.0)
    safe("menus_empty", menus)
    safe("toolbars_empty", toolbars)
    safe("watchers_empty", task_widgets)
    safe("solver_empty", solver_message)

    def insert_panel():
        Gui.runCommand("Assembly_InsertLink", 0)
        pump(1.5)
        out = task_widgets()
        close_task()
        return out
    safe("panel_insert", insert_panel)
    # the components, as CommandInsertLink's accept makes them, the first grounded
    import CommandCreateJoint
    links = {}
    for name, src, p in (("Plate", plate, None), ("Pin", pin, App.Placement(V(30, 5, 2), App.Rotation(10, 20, 30))),
                         ("Bar", bar, App.Placement(V(-20, 40, 15), App.Rotation(-35, 5, 60)))):
        lk = asm.newObject("App::Link", name)
        lk.LinkedObject = src
        lk.Label = name
        if p is not None:
            lk.Placement = p
        links[name] = lk
    CommandCreateJoint.createGroundedJoint(links["Plate"])
    pump(1.0)
    safe("solver_grounded", solver_message)
    safe("menus_parts", menus)
    safe("toolbars_parts", toolbars)
    for t in ("Fixed", "Revolute", "Cylindrical", "Slider", "Ball", "Distance", "Parallel", "Perpendicular", "Angle",
              "RackPinion", "Screw", "Gears", "Belt"):
        def panel(t=t):
            Gui.Selection.clearSelection()
            Gui.runCommand(f"Assembly_CreateJoint{t}", 0)
            pump(1.2)
            out = task_widgets()
            close_task()
            return out
        safe("panel_" + t, panel)
    safe("joint_revolute", lambda: joint("Assembly_CreateJointRevolute", "Plate.Face6", "Pin.Face3"))
    safe("joint_distance", lambda: joint("Assembly_CreateJointDistance", "Plate.Face6", "Bar.Face5",
                                         {"distanceSpinbox": 5.0}))
    safe("joint_redundant", lambda: joint("Assembly_CreateJointFixed", "Plate.Face6", "Pin.Face3"))
    safe("tree", tree_rows)
    safe("props_joint", lambda: property_view(doc.getObject("Joint")))
    safe("undo_names", lambda: list(doc.UndoNames))
    save()
    os._exit(0)


QtCore.QTimer.singleShot(500, main)

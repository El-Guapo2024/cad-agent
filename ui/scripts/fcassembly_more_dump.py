# SPDX-License-Identifier: LGPL-2.1-or-later
# Runs inside FreeCAD's GUI (fcassembly.py --more starts it under fclaunch, windows kept off the screen): what the real
# Assembly workbench does with the commands of the second round, for assemblycheck.mjs's sections rigid, isolate,
# offsets, origin, explode, newpart and subasm. Writes fcassembly_more.json into FCGUI_OUT:
#   menus, toolbars        the Assembly menu and toolbars with three components (Plate grounded, Pin, Bar) in edit
#   rigid                  Assembly_CreateJointRigidGroup on Pin and Bar: the object, its tree rows, property view,
#                          context menu, undo step and what the Report view got
#   isolate                a Revolute panel with Plate.Face6 and Pin.Face3 picked: the other component's Visibility and
#                          Selectable for each Isolate mode
#   offsets                a Fixed panel with Show advanced offsets: its widgets, Offset1's TaskPlacement dialog
#   origin                 a Fixed joint from the Origin's XY_Plane (picked as the tree hands it) to Bar.Face5
#   explode                Assembly_CreateView: its panel, Pin selected, a move made with the dragger, OK, the tree, the
#                          view selected (explodeTemporarily) and unselected
#   newpart                Assembly_InsertNewPart: its panel, a pick, OK
#   subasm                 a second document's Assembly inserted (Insert Component's panel lists it), rigid then turned
#                          flexible: the tree, the AssemblyLink's property view, Go to Linked Assembly
#   sim                    a third document (Plate grounded, Pin on a Revolute): Assembly_CreateSimulation's panel, a
#                          motion added, Generate, the player at its last frame and at frame 50, OK, the tree
import json
import os
import tempfile
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
TMP = tempfile.mkdtemp(prefix="fcasm2")


def save():
    json.dump(res, open(os.path.join(OUT, "fcassembly_more.json"), "w"), indent=1)


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


def close_dialogs(holder=None):
    for w in app.topLevelWidgets():
        if isinstance(w, QtWidgets.QMessageBox) and w.isVisible():
            if holder is not None:
                holder.append({"title": w.windowTitle(), "text": w.text(), "buttons": [b.text() for b in w.buttons()]})
            yes = [b for b in w.buttons() if b.text().replace("&", "") in ("Yes", "Save")]
            (yes[0].click() if yes else w.reject())


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
        if a.menu() is not None and depth < 4:
            d["menu"] = dump_menu(a.menu(), depth + 1)
        out.append(d)
    return out


def menus():
    for a in mw.menuBar().actions():
        if a.text() == "&Assembly":
            return dump_menu(a.menu())
    return None


def toolbars():
    out = []
    for tb in mw.findChildren(QtWidgets.QToolBar):
        if tb.windowTitle() not in ("Assembly", "Assembly Joints"):
            continue
        row = {"title": tb.windowTitle(), "buttons": []}
        for a in tb.actions():
            if a.isSeparator():
                row["buttons"].append({"sep": True})
            elif a.isVisible():
                b = {"name": a.objectName() or "", "text": a.text(), "enabled": a.isEnabled()}
                if a.menu() is not None:
                    b["menu"] = dump_menu(a.menu())
                row["buttons"].append(b)
        out.append(row)
    return out


def widgets_of(root):
    items = []
    for w in root.findChildren(QtWidgets.QWidget):
        if not w.isVisible():
            continue
        cls = w.metaObject().className()
        pos = w.mapTo(root, QtCore.QPoint(0, 0))
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
        elif isinstance(w, (QtWidgets.QAbstractSpinBox, QtWidgets.QLineEdit)):
            d["text"] = w.text()
        elif isinstance(w, QtWidgets.QListWidget):
            d["items"] = [w.item(i).text() for i in range(w.count())]
        elif isinstance(w, QtWidgets.QTreeWidget):
            d["items"] = []

            def walk(it, depth):
                d["items"].append({"text": it.text(0), "depth": depth})
                for k in range(it.childCount()):
                    walk(it.child(k), depth + 1)
            for k in range(w.topLevelItemCount()):
                walk(w.topLevelItem(k), 0)
        elif isinstance(w, QtWidgets.QSlider):
            d["value"], d["max"] = w.value(), w.maximum()
        elif isinstance(w, QtWidgets.QGroupBox):
            d["text"] = w.title()
        elif cls.endswith("TaskHeader"):
            d["text"] = " ".join(lbl.text() for lbl in w.findChildren(QtWidgets.QLabel) if lbl.text())
        else:
            continue
        items.append(d)
    items.sort(key=lambda d: (d["y"], d["x"]))
    return items


def task_widgets():
    views = [w for w in mw.findChildren(QtWidgets.QWidget) if w.metaObject().className() == "Gui::TaskView::TaskView"]
    return [widgets_of(tv) for tv in views if tv.isVisible()]


def close_task():
    """The panel's Cancel (its reject: the joint it made removed, the transaction aborted)."""
    if Gui.Control.activeDialog():
        if not click_button("Cancel"):
            Gui.Control.closeDialog()
        pump(0.5)


def click_button(text):
    for b in mw.findChildren(QtWidgets.QAbstractButton):
        if b.isVisible() and b.text().replace("&", "") == text:
            b.click()
            pump(1.0)
            return True
    return False


def plc(p):
    return [p.Base.x, p.Base.y, p.Base.z, *p.Rotation.Q]


def tree_rows():
    tree = [t for t in mw.findChildren(QtWidgets.QTreeWidget) if t.metaObject().className() == "Gui::TreeWidget"][0]
    tree.expandAll()
    pump(0.4)
    rows = []

    def walk(item, depth):
        rows.append({"text": item.text(0), "depth": depth})
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


def context_menu(vobj):
    """The view provider's own entries (setupContextMenu)."""
    m = QtWidgets.QMenu()
    try:
        vobj.Proxy.setupContextMenu(vobj, m)
    except Exception:
        return None
    return [a.text() for a in m.actions() if not a.isSeparator()]


def report_text():
    for w in mw.findChildren(QtWidgets.QTextEdit):
        if w.metaObject().className() == "Gui::DockWnd::ReportOutput":
            return w.toPlainText()
    return ""


doc = None
asm = None
links = {}


def centre(sub):
    comp, el = sub.split(".")
    return doc.getObject(comp).Shape.getElement(el).CenterOfMass


def pick(sub):
    c = centre(sub)
    Gui.Selection.addSelection(doc.Name, asm.Name, sub, c.x, c.y, c.z)
    pump(0.8)


def setup():
    global doc, asm
    doc = App.newDocument("Unnamed")
    pump(0.5)
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
    import CommandCreateJoint
    for name, src, p in (("Plate", plate, None), ("Pin", pin, App.Placement(V(30, 5, 2), App.Rotation(10, 20, 30))),
                         ("Bar", bar, App.Placement(V(-20, 40, 15), App.Rotation(-35, 5, 60)))):
        lk = asm.newObject("App::Link", name)
        lk.LinkedObject = src
        lk.Label = name
        if p is not None:
            lk.Placement = p
        links[name] = lk
    CommandCreateJoint.createGroundedJoint(links["Plate"])
    doc.saveAs(os.path.join(TMP, "Unnamed.FCStd"))
    pump(1.0)
    return True


def rigid():
    undo = list(doc.UndoNames)
    before = {o.Name for o in doc.Objects}
    report0 = report_text()
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.Name, asm.Name, "Pin.")
    Gui.Selection.addSelection(doc.Name, asm.Name, "Bar.")
    pump(0.5)
    Gui.runCommand("Assembly_CreateJointRigidGroup", 0)
    pump(1.5)
    made = [o for o in doc.Objects if o.Name not in before]
    rg = next((o for o in made if hasattr(o, "ObjectsToRigidGroup")), None)
    out = {"undo": [u for u in doc.UndoNames if u not in undo][:1] or doc.UndoNames[:1],
           "report": report_text()[len(report0):].replace(os.path.normpath(App.getHomePath()) + "/", "<FreeCAD>/")}
    if rg is not None:
        out.update(name=rg.Name, label=rg.Label, members=[o.Name for o in rg.ObjectsToRigidGroup],
                   rigid_placements=[plc(p) for p in rg.RigidPlacements], tree=tree_rows(), props=property_view(rg),
                   menu=context_menu(rg.ViewObject))
    out["placements"] = {n: plc(lk.Placement) for n, lk in links.items()}
    # with the group made, a joint on the Bar takes the Pin along
    return out


def isolate():
    import JointObject
    Gui.Selection.clearSelection()
    Gui.runCommand("Assembly_CreateJointRevolute", 0)
    pump(1.2)
    pick("Plate.Face6")
    pick("Pin.Face3")
    task = JointObject.activeTask
    out = {}
    for i, mode in enumerate(task.isolate_modes):
        task.jForm.isolateType.setCurrentIndex(i)
        pump(0.6)
        out[mode] = {n: {"visibility": lk.Visibility, "selectable": lk.ViewObject.Selectable} for n, lk in links.items()}
    close_task()
    out["after"] = {n: {"visibility": lk.Visibility, "selectable": lk.ViewObject.Selectable} for n, lk in links.items()}
    return out


def offsets():
    import JointObject
    Gui.Selection.clearSelection()
    Gui.runCommand("Assembly_CreateJointFixed", 0)
    pump(1.2)
    task = JointObject.activeTask
    task.jForm.advancedOffsetCheckbox.setChecked(True)
    pump(0.6)
    out = {"panel": task_widgets()}
    seen = {}

    def grab():
        for w in app.topLevelWidgets():
            if w.isVisible() and isinstance(w, QtWidgets.QDialog) and w is not mw:
                seen["title"] = w.windowTitle()
                seen["widgets"] = widgets_of(w)
                w.reject()
                return
        QtCore.QTimer.singleShot(300, grab)
    QtCore.QTimer.singleShot(800, grab)
    task.jForm.offset1Button.click()
    pump(0.5)
    out["dialog"] = seen
    close_task()
    return out


def origin():
    import JointObject
    undo = list(doc.UndoNames)
    before = {o.Name for o in doc.Objects}
    Gui.Selection.clearSelection()
    Gui.runCommand("Assembly_CreateJointFixed", 0)
    pump(1.2)
    Gui.Selection.addSelection(doc.Name, asm.Name, "Origin.XY_Plane.")
    pump(0.8)
    pick("Bar.Face5")
    panel = task_widgets()
    click_button("OK")
    pump(1.0)
    j = next((o for o in doc.Objects if o.Name not in before and hasattr(o, "JointType")), None)
    return {"panel": panel, "undo": [u for u in doc.UndoNames if u not in undo][:1],
            "joint": None if j is None else {"name": j.Name, "label": j.Label, "reference1": [j.Reference1[0].Name, list(j.Reference1[1])],
                                             "reference2": [j.Reference2[0].Name, list(j.Reference2[1])],
                                             "placement1": plc(j.Placement1), "placement2": plc(j.Placement2)},
            "placements": {n: plc(lk.Placement) for n, lk in links.items()}}


def explode():
    undo = list(doc.UndoNames)
    Gui.Selection.clearSelection()
    Gui.runCommand("Assembly_CreateView", 0)
    pump(1.5)
    panel = Gui.doCommandEval("panel")
    out = {"panel": task_widgets()}
    Gui.Selection.addSelection(doc.Name, asm.Name, "Pin.")
    pump(0.8)
    out["selected"] = task_widgets()
    out["dragger_initial"] = plc(panel.initialDraggerPlc) if getattr(panel, "initialDraggerPlc", None) else None
    # the dragger moved 25 mm along Z, as a drag of its blue arrow leaves it, then let go
    target = App.Placement(panel.initialDraggerPlc)
    target.Base = target.Base + V(0, 0, 25)
    panel.blockDraggerMove = True
    asm.ViewObject.DraggerPlacement = target
    panel.blockDraggerMove = False
    panel.draggerMoved(None)
    pump(0.3)
    panel.draggerFinished(None)
    pump(0.6)
    out["moved"] = task_widgets()
    out["exploded"] = {n: plc(lk.Placement) for n, lk in links.items()}
    click_button("OK")
    pump(1.0)
    out["undo"] = [u for u in doc.UndoNames if u not in undo][:1]
    out["after_ok"] = {n: plc(lk.Placement) for n, lk in links.items()}
    out["tree"] = tree_rows()
    view = next((o for o in doc.Objects if o.Name.startswith("Exploded_View") and o.TypeId == "App::FeaturePython"), None)
    if view is not None:
        out["view"] = {"name": view.Name, "label": view.Label, "moves": [{"name": m.Name, "label": m.Label, "type": m.MoveType,
                                                                          "transform": plc(m.MovementTransform),
                                                                          "references": [m.References[0].Name, list(m.References[1])]} for m in view.Group]}
        out["view_props"] = property_view(view.Group[0]) if view.Group else None
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(view)
        pump(0.8)
        out["selected_view"] = {n: plc(lk.Placement) for n, lk in links.items()}
        Gui.Selection.clearSelection()
        pump(0.8)
        out["unselected_view"] = {n: plc(lk.Placement) for n, lk in links.items()}
    return out


def newpart():
    import JointObject
    undo = list(doc.UndoNames)
    before = {o.Name for o in doc.Objects}
    dialogs = []
    t = QtCore.QTimer()
    t.timeout.connect(lambda: close_dialogs(dialogs))
    t.start(200)
    Gui.Selection.clearSelection()
    Gui.runCommand("Assembly_InsertNewPart", 0)
    pump(1.5)
    out = {"panel": task_widgets()}
    pick("Plate.Face6")
    out["picked"] = task_widgets()
    # the new file is saved where FreeCAD asks (a save dialog): put it in the temporary folder instead
    task = JointObject.activeTask
    task.createInNewFileCheck.setChecked(False)
    pump(0.3)
    click_button("OK")
    pump(1.5)
    t.stop()
    made = [o for o in App.ActiveDocument.Objects if o.Name not in before]
    out["made"] = [{"name": o.Name, "label": o.Label, "type": o.TypeId} for o in made]
    out["undo"] = [u for u in doc.UndoNames if u not in undo][:1]
    out["dialogs"] = dialogs
    lk = next((o for o in made if o.TypeId == "App::Link"), None)
    out["link"] = None if lk is None else {"name": lk.Name, "label": lk.Label, "placement": plc(lk.Placement),
                                           "linked": lk.LinkedObject.Name if lk.LinkedObject else None}
    j = next((o for o in made if hasattr(o, "JointType")), None)
    out["joint"] = None if j is None else {"name": j.Name, "label": j.Label, "reference1": [j.Reference1[0].Name, list(j.Reference1[1])],
                                           "reference2": [j.Reference2[0].Name, list(j.Reference2[1])]}
    return out


def subasm():
    global doc
    main = doc
    import CommandCreateJoint
    import JointObject
    import UtilsAssembly
    sub = App.newDocument("Sub")
    box = sub.addObject("Part::Box", "Box")
    cyl = sub.addObject("Part::Cylinder", "Cylinder")
    cyl.Radius, cyl.Height = 3, 20
    sub.recompute()
    box.ViewObject.Visibility = cyl.ViewObject.Visibility = False
    sa = sub.addObject("Assembly::AssemblyObject", "Assembly")
    sa.Type = "Assembly"
    sjg = sa.newObject("Assembly::JointGroup", "Joints")
    l1 = sa.newObject("App::Link", "Plate")
    l1.LinkedObject = box
    l2 = sa.newObject("App::Link", "Pin")
    l2.LinkedObject = cyl
    l2.Placement = App.Placement(V(30, 5, 2), App.Rotation(10, 20, 30))
    g = sjg.newObject("App::FeaturePython", "GroundedJoint")
    JointObject.GroundedJoint(g, l1)
    sub.recompute()
    j = sjg.newObject("App::FeaturePython", "Joint")
    j.Label = "Revolute"
    JointObject.Joint(j, JointObject.JointTypes.index("Revolute"))
    j.Proxy.setJointConnectors(j, [[l1, ["Face6", "Face6"]]])
    j.Proxy.setJointConnectors(j, [[l1, ["Face6", "Face6"]], [l2, ["Face3", "Edge1"]]])
    exec(UtilsAssembly.generatePropertySettings(j), {"App": App})
    sa.recompute(True)
    sub.saveAs(os.path.join(TMP, "Sub.FCStd"))
    App.setActiveDocument(main.Name)
    Gui.activeDocument().activeView()
    Gui.ActiveDocument = Gui.getDocument(main.Name)
    pump(0.8)
    Gui.runCommand("Assembly_InsertLink", 0)
    pump(1.5)
    out = {"insert_panel": task_widgets()}
    close_task()
    undo = list(main.UndoNames)
    main.openTransaction("Insert Component")
    al = asm.newObject("Assembly::AssemblyLink", sa.Label)
    al.LinkedObject = sa
    al.Label = sa.Label
    al.recompute()
    al.Placement.Base = V(50, 0, 0)
    al.Rigid = True
    main.commitTransaction()
    main.recompute()
    pump(1.0)
    out["rigid"] = {"name": al.Name, "label": al.Label, "children": [(c.Name, c.Label, plc(c.Placement)) for c in al.Group if c.TypeId == "App::Link"],
                    "tree": tree_rows(), "props": property_view(al)}
    al.Rigid = False
    main.recompute()
    pump(1.0)
    out["flexible"] = {"children": [(c.Name, c.Label, plc(c.Placement)) for c in al.Group if c.TypeId == "App::Link"],
                       "tree": tree_rows(), "props": property_view(al), "placement": plc(al.Placement)}
    al.Rigid = True
    main.recompute()
    pump(0.6)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(al)
    pump(0.4)
    out["menu_with_link"] = menus()
    Gui.runCommand("Assembly_LinkSelectLinked", 0)
    pump(1.0)
    out["goto"] = {"active": App.ActiveDocument.Name, "selection": [(s.DocumentName, s.ObjectName) for s in Gui.Selection.getSelectionEx("*")]}
    out["undo"] = [u for u in main.UndoNames if u not in undo][:1]
    App.setActiveDocument(main.Name)
    doc = main
    return out


def sim():
    import JointObject
    import CommandCreateSimulation as CS
    sd = App.newDocument("Sim")
    box = sd.addObject("Part::Box", "Box")
    cyl = sd.addObject("Part::Cylinder", "Cylinder")
    cyl.Radius, cyl.Height = 3, 20
    sd.recompute()
    box.ViewObject.Visibility = cyl.ViewObject.Visibility = False
    sa = sd.addObject("Assembly::AssemblyObject", "Assembly")
    sa.Type = "Assembly"
    jg = sa.newObject("Assembly::JointGroup", "Joints")
    l1 = sa.newObject("App::Link", "Plate")
    l1.LinkedObject = box
    l2 = sa.newObject("App::Link", "Pin")
    l2.LinkedObject = cyl
    l2.Placement = App.Placement(V(30, 5, 2), App.Rotation(10, 20, 30))
    g = jg.newObject("App::FeaturePython", "GroundedJoint")
    JointObject.GroundedJoint(g, l1)
    j = jg.newObject("App::FeaturePython", "Joint")
    j.Label = "Revolute"
    JointObject.Joint(j, JointObject.JointTypes.index("Revolute"))
    j.Proxy.setJointConnectors(j, [[l1, ["Face6", "Face6"]], [l2, ["Face3", "Edge1"]]])
    sa.recompute(True)
    sd.recompute()
    sd.saveAs(os.path.join(TMP, "Sim.FCStd"))
    App.setActiveDocument(sd.Name)
    Gui.ActiveDocument = Gui.getDocument(sd.Name)
    Gui.ActiveDocument.setEdit(sa)
    pump(1.0)
    made = []
    init0 = CS.TaskAssemblyCreateSimulation.__init__

    def init(self, *a, **k):
        made.append(self)
        init0(self, *a, **k)
    CS.TaskAssemblyCreateSimulation.__init__ = init
    undo = list(sd.UndoNames)
    out = {"before": {"Pin": plc(l2.Placement)}, "menu": menus()}
    Gui.runCommand("Assembly_CreateSimulation", 0)
    pump(1.5)
    CS.TaskAssemblyCreateSimulation.__init__ = init0
    panel = made[0]
    out["panel"] = task_widgets()
    panel.createMotionObject("Angular", j, "initialValue + 5*time")
    pump(0.5)
    out["motion"] = task_widgets()
    panel.runKinematics()
    pump(1.0)
    out["generated"] = task_widgets()
    out["frames"] = sa.numberOfFrames()
    out["last"] = {"Pin": plc(l2.Placement)}
    panel.setFrameValue(50)
    pump(0.5)
    out["frame50"] = {"Pin": plc(l2.Placement), "widgets": task_widgets()}
    click_button("OK")
    pump(1.0)
    out["undo"] = [u for u in sd.UndoNames if u not in undo][:1]
    out["after_ok"] = {"Pin": plc(l2.Placement)}
    out["tree"] = tree_rows()
    s0 = next((o for o in sd.Objects if o.Name == "Simulation"), None)
    if s0 is not None:
        out["simulation"] = {"name": s0.Name, "label": s0.Label, "group": [m.Name for m in s0.Group],
                             "motions": [{"name": m.Name, "label": m.Label, "type": m.MotionType, "formula": m.Formula,
                                          "joint": m.Joint[0].Name if m.Joint else None} for m in s0.Group],
                             "parent": [o.Name for o in s0.InList],
                             "settings": [s0.aTimeStart.Value, s0.bTimeEnd.Value, s0.cTimeStepOutput.Value,
                                          s0.fGlobalErrorTolerance, s0.jFramesPerSecond]}
    return out


def main():
    pump(1.5)
    Gui.activateWorkbench("AssemblyWorkbench")
    pump(1.0)
    safe("setup", setup)
    safe("menus", menus)
    safe("toolbars", toolbars)
    safe("rigid", rigid)
    safe("isolate", isolate)
    safe("offsets", offsets)
    safe("origin", origin)
    safe("explode", explode)
    safe("newpart", newpart)
    safe("subasm", subasm)
    safe("sim", sim)
    safe("undo_names", lambda: list(doc.UndoNames))
    save()
    os._exit(0)


QtCore.QTimer.singleShot(500, main)

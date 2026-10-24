# Runs inside FreeCAD's GUI (fcedit.py starts it under fclaunch, windows kept off the screen): what the real PartDesign
# workbench shows, for the comparison with the page's (editcheck.mjs). Writes fcedit.json and the tree's icons into
# FCGUI_OUT:
#   menus      the Sketch and Part Design menus, entry by entry (text, command, shortcut, enabled, submenus)
#   toolbars   the workbench's toolbars and their buttons (command, text, tooltip, enabled, a group's menu)
#   pick       the New Sketch task panel FreeCAD shows for a Body with nothing selected (the plane list)
#   pad/pocket each task panel's widgets in order (labels, combo items and the current one, spin boxes, check boxes)
#   tree       the rows of a Body with Sketch, Pad, Sketch001 and Pocket (text, depth, font, colour, icon file),
#              then again with the Tip on Pad
#   menu_*     the tree's context menu on the Pad, the Sketch and the Body
#   delete     the message Std_Delete shows for a sketch a feature uses
import json
import os
import time
import traceback

import FreeCAD as App
import FreeCADGui as Gui
import Part
import Sketcher
from PySide6 import QtCore, QtGui, QtWidgets

OUT = os.environ["FCGUI_OUT"]
mw = Gui.getMainWindow()
app = QtWidgets.QApplication.instance()
res = {"errors": {}}
mw.resize(1280, 800)
V = App.Vector


def bail():
    res["errors"]["hung"] = "stopped after 600 s"
    json.dump(res, open(os.path.join(OUT, "fcedit.json"), "w"), indent=1)
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
        d = {"text": a.text(), "name": a.objectName() or a.data(), "shortcut": a.shortcut().toString(), "enabled": a.isEnabled(),
             "icon": not a.icon().isNull()}
        sub = a.menu()
        if sub is not None and depth < 4:
            d["menu"] = dump_menu(sub, depth + 1)
        out.append(d)
    return out


def cmd_of(a):
    """The command an action runs: Gui's actions carry the command's name as their objectName (Action::Action)."""
    return a.objectName() or ""


pump(1.5)
Gui.activateWorkbench("PartDesignWorkbench")
pump(1.0)
doc = App.newDocument("Unnamed")
pump(0.5)


def menus():
    out = {"bar": [a.text() for a in mw.menuBar().actions() if a.isVisible()]}
    for a in mw.menuBar().actions():
        if a.text() in ("&Sketch", "&Part Design", "&Edit", "&View"):
            out[a.text()] = dump_menu(a.menu())
    return out


def toolbars():
    out = []
    for tb in mw.findChildren(QtWidgets.QToolBar):
        if not tb.isVisible() and not tb.toggleViewAction().isChecked():
            continue
        row = {"title": tb.windowTitle(), "name": tb.objectName(), "visible": tb.isVisible(), "buttons": []}
        for a in tb.actions():
            if a.isSeparator():
                row["buttons"].append({"sep": True})
                continue
            if not a.isVisible():
                continue
            w = tb.widgetForAction(a)
            b = {"name": cmd_of(a), "text": a.text(), "tip": a.toolTip(), "enabled": a.isEnabled()}
            if a.menu() is not None:
                b["menu"] = dump_menu(a.menu())
            if isinstance(w, QtWidgets.QToolButton) and w.menu() is not None and "menu" not in b:
                b["menu"] = dump_menu(w.menu())
            row["buttons"].append(b)
        out.append(row)
    return out


def task_widgets():
    """The open task panel's widgets, top to bottom: what a person reads in it."""
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
            elif cls.endswith("TaskBoxHeader") or cls.endswith("TaskHeader") or cls == "QSint::TaskHeader":
                d["text"] = " ".join(l.text() for l in w.findChildren(QtWidgets.QLabel) if l.text())
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


def tree_widget():
    return [t for t in mw.findChildren(QtWidgets.QTreeWidget) if t.metaObject().className() == "Gui::TreeWidget"][0]


ICONS = {}


def tree_rows():
    tree = tree_widget()
    tree.expandAll()
    pump(0.4)
    rows = []

    def walk(item, depth):
        f = item.font(0)
        key = item.icon(0).cacheKey()
        if key not in ICONS:
            ICONS[key] = f"icon{len(ICONS)}.png"
            item.icon(0).pixmap(32, 32).save(os.path.join(OUT, ICONS[key]))
        rows.append({"text": item.text(0), "depth": depth, "bold": f.bold(), "italic": f.italic(), "underline": f.underline(),
                     "fg": item.foreground(0).color().name() if item.foreground(0).style() else None,
                     "icon": ICONS[key], "expanded": item.isExpanded(), "children": item.childCount(),
                     "tip": item.toolTip(0), "checkable": bool(item.flags() & QtCore.Qt.ItemIsUserCheckable)})
        for i in range(item.childCount()):
            walk(item.child(i), depth + 1)

    for i in range(tree.topLevelItemCount()):
        walk(tree.topLevelItem(i), 0)
    return rows


def objects():
    return [{"name": o.Name, "label": o.Label, "type": o.TypeId, "visible": o.Visibility if hasattr(o, "Visibility") else None}
            for o in doc.Objects]


def find_item(name):
    tree = tree_widget()
    return tree.findItems(name, QtCore.Qt.MatchExactly | QtCore.Qt.MatchRecursive, 0)[0]


def menu_at(name):
    tree = tree_widget()
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.getObject(name))
    pump(0.4)
    target = find_item(name)
    tree.scrollToItem(target)
    pump(0.2)
    pos = tree.visualItemRect(target).center()
    holder = {"polls": 0}

    def grab():
        holder["polls"] += 1
        menus = [w for w in app.topLevelWidgets() if isinstance(w, QtWidgets.QMenu) and w.isVisible() and w.actions()]
        if not menus:
            if holder["polls"] > 40:
                holder["timer"].stop()
            return
        holder["timer"].stop()
        m = max(menus, key=lambda w: len(w.actions()))
        holder["actions"] = dump_menu(m)
        m.close()

    holder["timer"] = QtCore.QTimer()
    holder["timer"].timeout.connect(grab)
    holder["timer"].start(150)
    app.sendEvent(tree.viewport(), QtGui.QContextMenuEvent(QtGui.QContextMenuEvent.Mouse, pos, tree.viewport().mapToGlobal(pos)))
    holder["timer"].stop()
    pump(0.4)
    Gui.Selection.clearSelection()
    return holder.get("actions", "no menu opened")


def rect_sketch(sk, w=40.0, h=20.0):
    pts = [V(0, 0, 0), V(w, 0, 0), V(w, h, 0), V(0, h, 0)]
    for i in range(4):
        sk.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 4]), False)
    for i in range(4):
        sk.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % 4, 1))


safe("menus_empty", menus)
safe("toolbars_empty", toolbars)

# Create body: PartDesign_Body with nothing selected
Gui.runCommand("PartDesign_Body", 0)
pump(1.0)
body = doc.getObject("Body")
res["after_body"] = {"objects": objects()}
safe("tree_body", tree_rows)
safe("menus", menus)
safe("toolbars", toolbars)


def pick():
    Gui.Selection.clearSelection()
    pump(0.3)
    Gui.runCommand("PartDesign_NewSketch", 0)
    pump(1.5)
    out = {"task": task_widgets(), "objects": objects()}
    # pick the XY plane (as a click on it in the 3D view or the tree does), then OK: the sketch opens in the Sketcher
    Gui.Selection.addSelection(doc.getObject("XY_Plane"))
    pump(1.0)
    out["task_picked"] = task_widgets()
    sk = doc.getObject("Sketch")
    out["picked"] = {"support": str(sk.AttachmentSupport), "map_mode": sk.MapMode} if sk else None
    out["ok"] = click_button("OK")
    pump(1.5)
    out["in_edit"] = str(Gui.ActiveDocument.getInEdit().Object.Name) if Gui.ActiveDocument.getInEdit() else None
    out["workbench"] = Gui.activeWorkbench().name()
    sk = doc.getObject("Sketch")
    if sk is not None:
        rect_sketch(sk)
        doc.recompute()
    Gui.ActiveDocument.resetEdit()
    pump(1.0)
    out["workbench_after_close"] = Gui.activeWorkbench().name()
    out["objects_after"] = objects()
    return out


safe("pick", pick)


def feature_panel(command, profile):
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.getObject(profile))
    pump(0.4)
    Gui.runCommand(command, 0)
    pump(1.5)
    out = {"task": task_widgets(), "in_edit": str(Gui.ActiveDocument.getInEdit().Object.Name) if Gui.ActiveDocument.getInEdit() else None}
    f = Gui.ActiveDocument.getInEdit().Object if Gui.ActiveDocument.getInEdit() else None
    if f is not None:
        out["props"] = {p: str(getattr(f, p)) for p in f.PropertiesList}
        out["groups"] = {p: f.getGroupOfProperty(p) for p in f.PropertiesList}
        out["prop_types"] = {p: f.getTypeIdOfProperty(p) for p in f.PropertiesList}
        out["editor_modes"] = {p: f.getEditorMode(p) for p in f.PropertiesList}
        out["enums"] = {p: f.getEnumerationsOfProperty(p) for p in f.PropertiesList if f.getTypeIdOfProperty(p) == "App::PropertyEnumeration"}
    out["ok"] = click_button("OK")
    pump(1.0)
    out["objects_after"] = objects()
    return out


safe("pad", lambda: feature_panel("PartDesign_Pad", "Sketch"))


def second_sketch():
    sk = body.newObject("Sketcher::SketchObject", "Sketch001")
    sk.AttachmentSupport = [(doc.getObject("XY_Plane"), "")]
    sk.MapMode = "FlatFace"
    sk.AttachmentOffset = App.Placement(V(0, 0, 10), App.Rotation())
    sk.addGeometry(Part.Circle(V(20, 10, 0), V(0, 0, 1), 4), False)
    doc.recompute()
    pump(0.5)
    return objects()


safe("sketch001", second_sketch)
safe("pocket", lambda: feature_panel("PartDesign_Pocket", "Sketch001"))
safe("tree", tree_rows)
safe("menu_pad", lambda: menu_at("Pad"))
safe("menu_sketch", lambda: menu_at("Sketch"))
safe("menu_body", lambda: menu_at("Body"))


def tip_on_pad():
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.getObject("Pad"))
    pump(0.3)
    Gui.runCommand("PartDesign_MoveTip", 0)
    pump(1.0)
    out = {"tip": body.Tip.Name if body.Tip else None, "rows": tree_rows(), "objects": objects()}
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.getObject("Pocket"))
    Gui.runCommand("PartDesign_MoveTip", 0)
    pump(1.0)
    return out


safe("tip", tip_on_pad)


def property_view(name):
    """The property view's Data tab for one selected object, as it shows it: group rows and their properties, in order."""
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.getObject(name))
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
                if depth < 2:
                    walk(i0, depth + 1)
        walk(QtCore.QModelIndex(), 0)
        out.append(rows)
    Gui.Selection.clearSelection()
    return out


for _n in ("Pad", "Pocket", "Sketch", "Body"):
    safe("props_" + _n, lambda n=_n: property_view(n))


def delete_used_sketch():
    """Std_Delete on a sketch the Pad uses: the message FreeCAD asks with, answered No."""
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.getObject("Sketch"))
    pump(0.3)
    holder = {}

    def grab():
        for w in app.topLevelWidgets():
            if isinstance(w, QtWidgets.QMessageBox) and w.isVisible():
                holder["title"] = w.windowTitle()
                holder["text"] = w.text()
                holder["informative"] = w.informativeText()
                holder["buttons"] = [b.text() for b in w.buttons()]
                no = w.button(QtWidgets.QMessageBox.No) or w.button(QtWidgets.QMessageBox.Cancel)
                (no or w.buttons()[-1]).click()
                timer.stop()
                return
    timer = QtCore.QTimer()
    timer.timeout.connect(grab)
    timer.start(150)
    Gui.runCommand("Std_Delete", 0)
    pump(1.0)
    timer.stop()
    holder["still_there"] = doc.getObject("Sketch") is not None
    return holder


safe("delete", delete_used_sketch)


def edit_pad():
    """Double-click (setEdit) on the Pad: its task panel again, with the Pad's values."""
    Gui.ActiveDocument.setEdit(doc.getObject("Pad"), 0)
    pump(1.2)
    out = {"task": task_widgets()}
    click_button("Cancel")
    pump(0.6)
    return out


safe("edit_pad", edit_pad)

json.dump(res, open(os.path.join(OUT, "fcedit.json"), "w"), indent=1)
os._exit(0)

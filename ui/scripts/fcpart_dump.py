# SPDX-License-Identifier: LGPL-2.1-or-later
# Runs inside FreeCAD's GUI (fcpart.py starts it under fclaunch, windows kept off the screen): what the real Part workbench
# shows, for partcheck.mjs to compare the page with. Writes fcpart.json and the tree's icons into FCGUI_OUT:
#   menus, toolbars     the Part menu (its submenus) and the workbench's toolbars, their dropdown groups
#   cmd_*               each command run on a selection: the objects it made (Name, Label, TypeId, visibility), the
#                       inputs it hid, its undo step's name, the task panel it opened (its widgets, top to bottom)
#   primitives          the Primitives dialog: its type list, and each type's fields with their defaults
#   tree                the tree's rows after it all (text, depth, icon), with the inputs under what uses them
#   menu_*              the tree's context menu on a Part object
#   props_*             the property view's Data rows of an object of each kind
#   delete_used         Std_Delete's question for an object another uses
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


def save():
    json.dump(res, open(os.path.join(OUT, "fcpart.json"), "w"), indent=1)


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
    """Answer any message box a command opened (its text recorded), so the script goes on."""
    out = []
    for w in app.topLevelWidgets():
        if isinstance(w, QtWidgets.QMessageBox) and w.isVisible():
            out.append({"title": w.windowTitle(), "text": w.text(), "buttons": [b.text() for b in w.buttons()]})
            w.reject()
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
             "enabled": a.isEnabled(), "icon": not a.icon().isNull()}
        sub = a.menu()
        if sub is not None and depth < 4:
            d["menu"] = dump_menu(sub, depth + 1)
        out.append(d)
    return out


def menus():
    out = {"bar": [a.text() for a in mw.menuBar().actions() if a.isVisible()]}
    for a in mw.menuBar().actions():
        if a.text() in ("&Part", "&View", "&Edit"):
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
            b = {"name": a.objectName() or "", "text": a.text(), "tip": a.toolTip(), "enabled": a.isEnabled()}
            if a.menu() is not None:
                b["menu"] = dump_menu(a.menu())
            if isinstance(w, QtWidgets.QToolButton) and w.menu() is not None and "menu" not in b:
                b["menu"] = dump_menu(w.menu())
            row["buttons"].append(b)
        out.append(row)
    return out


def task_widgets():
    """The open task panel's widgets, top to bottom (fcedit_dump.py's task_widgets, with spin box values and list
    widgets)."""
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
                d["items"] = []
                for i in range(w.topLevelItemCount()):
                    it = w.topLevelItem(i)
                    d["items"].append([it.text(c) for c in range(w.columnCount())])
                d["headers"] = [w.headerItem().text(c) for c in range(w.columnCount())]
            elif isinstance(w, QtWidgets.QGroupBox):
                d["text"] = w.title()
            elif cls.endswith("TaskBoxHeader") or cls.endswith("TaskHeader") or cls == "QSint::TaskHeader":
                d["text"] = " ".join(lbl.text() for lbl in w.findChildren(QtWidgets.QLabel) if lbl.text())
            else:
                continue
            items.append(d)
        items.sort(key=lambda d: (d["y"], d["x"]))
        out.append(items)
    return out


def task_buttons():
    """The task dialog's own buttons (OK, Cancel, Close, Create ...)."""
    out = []
    for b in mw.findChildren(QtWidgets.QDialogButtonBox):
        if b.isVisible():
            out += [x.text() for x in b.buttons()]
    return out


def click_button(text):
    for b in mw.findChildren(QtWidgets.QAbstractButton):
        if b.isVisible() and b.text().replace("&", "") == text:
            b.click()
            pump(0.8)
            return True
    return False


def close_task():
    if Gui.Control.activeDialog():
        Gui.Control.closeDialog()
        pump(0.5)


doc = None


def objects():
    return [{"name": o.Name, "label": o.Label, "type": o.TypeId,
             "proxy": type(o.Proxy).__name__ if hasattr(o, "Proxy") and o.Proxy is not None else None,
             "visible": o.ViewObject.Visibility if o.ViewObject else None} for o in doc.Objects]


def select(*names, subs=None):
    Gui.Selection.clearSelection()
    for n in names:
        if subs and n in subs:
            for s in subs[n]:
                Gui.Selection.addSelection(doc.Name, n, s)
        else:
            Gui.Selection.addSelection(doc.getObject(n))
    pump(0.3)


def run(command, *sel, subs=None, ok=None, cancel=False, after=None):
    """Run a command on a selection: the objects it made, what it hid, its undo name, its task panel."""
    before = {o.Name for o in doc.Objects}
    vis = {o.Name: o.ViewObject.Visibility for o in doc.Objects if o.ViewObject}
    undo = list(doc.UndoNames)
    select(*sel, subs=subs)
    holder = {}
    t = watch_dialogs(holder)
    Gui.runCommand(command, 0)
    pump(1.5)
    out = {"task": task_widgets(), "buttons": task_buttons()}
    if after:
        out["after"] = after()
    if ok:
        out["ok"] = click_button(ok)
        pump(1.0)
    elif cancel:
        close_task()
    t.stop()
    doc.recompute()
    pump(0.5)
    out["dialogs"] = holder.get("dialogs", [])
    out["made"] = [o for o in objects() if o["name"] not in before]
    out["hidden"] = sorted(n for n, v in vis.items() if v and doc.getObject(n) and doc.getObject(n).ViewObject
                           and not doc.getObject(n).ViewObject.Visibility)
    out["undo"] = [u for u in doc.UndoNames if u not in undo][:1] or doc.UndoNames[:1]
    out["props"] = {o["name"]: props_of(o["name"]) for o in out["made"]}
    Gui.Selection.clearSelection()
    return out


def props_of(name):
    o = doc.getObject(name)
    out = {}
    for p in o.PropertiesList:
        if p in ("Shape", "Proxy", "ExpressionEngine", "Label2"):
            continue
        try:
            val = "<Material>" if p == "ShapeMaterial" else str(getattr(o, p))     # no memory address in the dump
            out[p] = {"value": val, "group": o.getGroupOfProperty(p), "type": o.getTypeIdOfProperty(p),
                      "mode": o.getEditorMode(p)}
            if o.getTypeIdOfProperty(p) == "App::PropertyEnumeration" and p not in ("MapMode", "AttacherEngine"):
                out[p]["enums"] = o.getEnumerationsOfProperty(p)
        except Exception as e:  # noqa: BLE001
            out[p] = {"error": str(e)}
    return out


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
            ICONS[key] = f"part_icon{len(ICONS)}.png"
            item.icon(0).pixmap(32, 32).save(os.path.join(OUT, ICONS[key]))
        rows.append({"text": item.text(0), "depth": depth, "bold": f.bold(), "italic": f.italic(),
                     "fg": item.foreground(0).color().name() if item.foreground(0).style() else None,
                     "icon": ICONS[key], "children": item.childCount()})
        for i in range(item.childCount()):
            walk(item.child(i), depth + 1)

    for i in range(tree.topLevelItemCount()):
        walk(tree.topLevelItem(i), 0)
    return rows


def find_item(name):
    tree = tree_widget()
    label = doc.getObject(name).Label
    return tree.findItems(label, QtCore.Qt.MatchExactly | QtCore.Qt.MatchRecursive, 0)[0]


def menu_at(name):
    tree = tree_widget()
    select(name)
    target = find_item(name)
    tree.scrollToItem(target)
    pump(0.2)
    pos = tree.visualItemRect(target).center()
    holder = {"polls": 0}

    def grab():
        holder["polls"] += 1
        ms = [w for w in app.topLevelWidgets() if isinstance(w, QtWidgets.QMenu) and w.isVisible() and w.actions()]
        if not ms:
            if holder["polls"] > 40:
                holder["timer"].stop()
            return
        holder["timer"].stop()
        m = max(ms, key=lambda w: len(w.actions()))
        holder["actions"] = dump_menu(m)
        m.close()

    holder["timer"] = QtCore.QTimer()
    holder["timer"].timeout.connect(grab)
    holder["timer"].start(150)
    app.sendEvent(tree.viewport(), QtGui.QContextMenuEvent(QtGui.QContextMenuEvent.Mouse, pos,
                                                           tree.viewport().mapToGlobal(pos)))
    holder["timer"].stop()
    pump(0.4)
    Gui.Selection.clearSelection()
    return holder.get("actions", "no menu opened")


def property_view(name):
    """The property view's Data rows for one selected object, as it shows them (fcedit_dump.py's property_view)."""
    select(name)
    pump(0.4)
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


def sketch(name, geos, placement=None):
    sk = doc.addObject("Sketcher::SketchObject", name)
    if placement is not None:
        sk.Placement = placement
    for g in geos:
        sk.addGeometry(g, False)
    doc.recompute()
    return sk


def rect(x0, y0, x1, y1):
    pts = [V(x0, y0, 0), V(x1, y0, 0), V(x1, y1, 0), V(x0, y1, 0)]
    return [Part.LineSegment(pts[i], pts[(i + 1) % 4]) for i in range(4)]


def primitives():
    """Part_Primitives: the type list and each type's page (its fields and their values), then the Location panel."""
    Gui.runCommand("Part_Primitives", 0)
    pump(1.5)
    out = {"task": task_widgets(), "buttons": task_buttons(), "types": {}}
    combo = [c for c in mw.findChildren(QtWidgets.QComboBox) if c.objectName() == "PrimitiveTypeCB" and c.isVisible()]
    if combo:
        cb = combo[0]
        out["items"] = [cb.itemText(i) for i in range(cb.count())]
        out["made"], out["undo"] = {}, {}
        for i in range(cb.count()):
            cb.setCurrentIndex(i)
            cb.activated.emit(i)                    # DlgPrimitives turns its page on activated
            pump(0.5)
            t = cb.itemText(i)
            out["types"][t] = task_widgets()
            before = {o.Name for o in doc.Objects}
            undo = list(doc.UndoNames)
            click_button("Create")
            pump(0.8)
            out["made"][t] = [dict(o, props=props_of(o["name"])) for o in objects() if o["name"] not in before]
            out["undo"][t] = [u for u in doc.UndoNames if u not in undo][:1]
    close_task()
    return out


def main():
    global doc
    pump(1.5)
    Gui.activateWorkbench("PartWorkbench")
    pump(1.0)
    doc = App.newDocument("Unnamed")
    pump(0.5)
    safe("workbench", lambda: Gui.activeWorkbench().name())
    safe("menus", menus)
    safe("toolbars", toolbars)
    for cmd in ("Part_Box", "Part_Cylinder", "Part_Sphere", "Part_Cone", "Part_Torus"):
        safe("cmd_" + cmd, lambda c=cmd: run(c))
    safe("cmd_Part_Tube", lambda: run("Part_Tube", ok="OK"))
    safe("primitives", primitives)

    # booleans, each on fresh solids that overlap
    def two(a, b):
        x = doc.addObject("Part::Box", a)
        x.Length, x.Width, x.Height = 20, 20, 10
        y = doc.addObject("Part::Cylinder", b)
        y.Radius, y.Height = 6, 20
        y.Placement = App.Placement(V(10, 10, -5), App.Rotation())
        doc.recompute()
    two("BoxA", "CylA")
    safe("cmd_Part_Cut", lambda: run("Part_Cut", "BoxA", "CylA"))
    two("BoxB", "CylB")
    safe("cmd_Part_Fuse", lambda: run("Part_Fuse", "BoxB", "CylB"))
    two("BoxC", "CylC")
    safe("cmd_Part_Common", lambda: run("Part_Common", "BoxC", "CylC"))
    two("BoxD", "CylD")
    safe("cmd_Part_Section", lambda: run("Part_Section", "BoxD", "CylD"))
    safe("cmd_Part_Boolean", lambda: run("Part_Boolean", cancel=True))
    two("BoxE", "CylE")
    safe("cmd_Part_Compound", lambda: run("Part_Compound", "BoxE", "CylE"))
    safe("cmd_Part_RefineShape", lambda: run("Part_RefineShape", "Fusion"))

    # sketches at the document's root, and what is made from them
    sketch("Sketch", rect(0, 0, 30, 20) + [Part.Circle(V(10, 10, 0), V(0, 0, 1), 4)])
    safe("cmd_Part_Extrude", lambda: run("Part_Extrude", "Sketch", ok="OK"))
    sketch("Sketch001", rect(5, 0, 10, 8), App.Placement(V(0, 0, 0), App.Rotation(V(1, 0, 0), 90)))
    safe("cmd_Part_Revolve", lambda: run("Part_Revolve", "Sketch001", ok="OK"))
    m = doc.addObject("Part::Box", "BoxM")
    doc.recompute()
    safe("cmd_Part_Mirror", lambda: run("Part_Mirror", "BoxM", ok="OK"))
    f = doc.addObject("Part::Box", "BoxF")
    doc.recompute()
    safe("cmd_Part_Fillet", lambda: run("Part_Fillet", "BoxF", cancel=True))
    safe("cmd_Part_Chamfer", lambda: run("Part_Chamfer", "BoxF", cancel=True))
    sketch("SketchL1", [Part.Circle(V(0, 0, 0), V(0, 0, 1), 5)])
    sketch("SketchL2", [Part.Circle(V(0, 0, 0), V(0, 0, 1), 3)], App.Placement(V(0, 0, 10), App.Rotation()))
    safe("cmd_Part_Loft", lambda: run("Part_Loft", cancel=True))
    safe("cmd_Part_Sweep", lambda: run("Part_Sweep", cancel=True))
    o = doc.addObject("Part::Box", "BoxO")
    doc.recompute()
    safe("cmd_Part_Offset", lambda: run("Part_Offset", "BoxO", ok="OK"))
    sketch("SketchO", rect(0, 0, 10, 6))
    safe("cmd_Part_Offset2D", lambda: run("Part_Offset2D", "SketchO", ok="OK"))
    t = doc.addObject("Part::Box", "BoxT")
    doc.recompute()
    safe("cmd_Part_Thickness", lambda: run("Part_Thickness", "BoxT", subs={"BoxT": ["Face6"]}, ok="OK"))
    safe("cmd_Part_ProjectionOnSurface", lambda: run("Part_ProjectionOnSurface", cancel=True))

    # Reverse, Scale, Face from wires, Ruled surface: fresh objects, so the commands' names come out as they would on a
    # document of their own
    rv = doc.addObject("Part::Box", "BoxRv")
    doc.recompute()
    safe("cmd_Part_ReverseShape", lambda: run("Part_ReverseShape", "BoxRv"))
    sc = doc.addObject("Part::Box", "BoxSc")
    doc.recompute()
    safe("cmd_Part_Scale", lambda: run("Part_Scale", "BoxSc", ok="OK"))
    safe("cmd_Part_Scale_none", lambda: run("Part_Scale", ok="OK"))
    sketch("SketchFa", rect(0, 0, 10, 6))
    sketch("SketchFb", rect(2, 1, 12, 7), App.Placement(V(0, 0, 5), App.Rotation()))
    safe("cmd_Part_MakeFace", lambda: run("Part_MakeFace", "SketchFa", "SketchFb"))
    for name, a, b in (("LineRa", (0, 0, 0), (10, 0, 0)), ("LineRb", (0, 10, 5), (10, 10, 5))):
        line = doc.addObject("Part::Line", name)
        line.X1, line.Y1, line.Z1, line.X2, line.Y2, line.Z2 = (*a, *b)
        doc.recompute()
    safe("cmd_Part_RuledSurface", lambda: run("Part_RuledSurface", "LineRa", "LineRb"))
    # no selection: CmdPartRuledSurface's warning (its only way there: one or two whole shapes are taken as they are)
    safe("cmd_Part_RuledSurface_none", lambda: run("Part_RuledSurface"))
    two("BoxS", "CylS")
    safe("cmd_Part_BooleanFragments", lambda: run("Part_BooleanFragments", "BoxS", "CylS"))
    two("BoxX", "CylX")
    safe("cmd_Part_XOR", lambda: run("Part_XOR", "BoxX", "CylX"))
    two("BoxJ", "CylJ")
    safe("cmd_Part_JoinConnect", lambda: run("Part_JoinConnect", "BoxJ", "CylJ"))
    two("BoxK", "CylK")
    safe("cmd_Part_Slice", lambda: run("Part_Slice", "BoxK", "CylK"))
    safe("cmd_Part_ExplodeCompound", lambda: run("Part_ExplodeCompound", "Compound"))

    safe("objects", objects)
    safe("tree", tree_rows)
    safe("menu_cut", lambda: menu_at("Cut"))
    safe("menu_box", lambda: menu_at("Box"))
    for n in ("Box", "Cylinder", "Cut", "Fusion", "Extrude", "Revolve", "Section"):
        if doc.getObject(n):
            safe("props_" + n, lambda n=n: property_view(n))

    def delete_used():
        select("BoxA")
        holder = {}
        t = watch_dialogs(holder)
        Gui.runCommand("Std_Delete", 0)
        pump(1.5)
        t.stop()
        return {"dialogs": holder.get("dialogs", []), "still_there": doc.getObject("BoxA") is not None}
    safe("delete_used", delete_used)
    safe("undo_names", lambda: list(doc.UndoNames))

    def types():
        """A fresh object of each type no command above made: its properties, groups, types and editor modes."""
        out = {}
        for tid, name in (("Part::Fillet", "Fillet"), ("Part::Chamfer", "Chamfer"), ("Part::Loft", "Loft"),
                          ("Part::Sweep", "Sweep"), ("Part::Fuse", "Fuse"), ("Part::Common", "CommonBT"),
                          ("Part::Polygon", "Polygon")):
            o = doc.addObject(tid, name)
            out[tid] = props_of(o.Name)
        from BOPTools import JoinFeatures
        for fn, tid in ((JoinFeatures.makeEmbed, "Part::Embed"), (JoinFeatures.makeCutout, "Part::Cutout")):
            o = fn(tid.split("::")[1])
            out[tid] = props_of(o.Name)
        return out
    safe("types", types)
    save()
    os._exit(0)


QtCore.QTimer.singleShot(500, main)

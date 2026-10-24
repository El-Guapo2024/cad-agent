# SPDX-License-Identifier: LGPL-2.1-or-later
# Runs inside FreeCAD's GUI (fctransform.py starts it under fclaunch, windows kept off the screen): what the real PartDesign
# workbench shows for its transformed features and its primitives, for transformcheck.mjs to compare the page with. Writes
# fctransform.json into FCGUI_OUT:
#   setup        a Body: Sketch (40 x 20 rectangle) padded 5 mm, Sketch001 (a circle r 3 at (8, 10), 5 mm up) pocketed 5 mm
#   <command>    for PartDesign_Mirrored, _LinearPattern, _PolarPattern and _MultiTransform run with the Pocket selected:
#                the task panel's widgets (task_widgets), the new feature's properties (values, groups, types, editor modes,
#                enumerations), after OK the objects, the feature's validity and the Body's volume
#   whole_shape  PartDesign_PolarPattern with nothing selected (TransformMode "Whole shape")
#   multi_menu   the Transformations list's context menu in the Multi-Transform panel, and the panel after "Add mirror
#                transformation"
#   edit_*       setEdit on the Mirrored and the LinearPattern: their panels with their values
#   prim_*       each Additive and Subtractive primitive: its panel (TaskPrimitiveParameters with the attachment panel), its
#                properties, after OK the Body's volume
#   tree         the Body's rows at the end (text, depth, icon file; the icons as PNGs)
#   props_*      the property view's rows for the Mirrored, the LinearPattern, the PolarPattern and the Additive Box
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
    res["errors"]["hung"] = "stopped after 900 s"
    json.dump(res, open(os.path.join(OUT, "fctransform.json"), "w"), indent=1)
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
        d = {"text": a.text(), "name": a.objectName() or a.data(), "enabled": a.isEnabled()}
        if a.menu() is not None and depth < 3:
            d["menu"] = dump_menu(a.menu(), depth + 1)
        out.append(d)
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
            elif isinstance(w, QtWidgets.QGroupBox):
                d["text"] = w.title()
                if w.isCheckable():
                    d["checked"] = w.isChecked()
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
            pump(1.0)
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
            ICONS[key] = f"ticon{len(ICONS)}.png"
            item.icon(0).pixmap(32, 32).save(os.path.join(OUT, ICONS[key]))
        rows.append({"text": item.text(0), "depth": depth, "bold": f.bold(),
                     "fg": item.foreground(0).color().name() if item.foreground(0).style() else None,
                     "icon": ICONS[key], "children": item.childCount()})
        for i in range(item.childCount()):
            walk(item.child(i), depth + 1)

    for i in range(tree.topLevelItemCount()):
        walk(tree.topLevelItem(i), 0)
    return rows


def objects():
    return [{"name": o.Name, "label": o.Label, "type": o.TypeId} for o in doc.Objects]


def props(f):
    return {"values": {p: str(getattr(f, p)) for p in f.PropertiesList},
            "groups": {p: f.getGroupOfProperty(p) for p in f.PropertiesList},
            "types": {p: f.getTypeIdOfProperty(p) for p in f.PropertiesList},
            "modes": {p: f.getEditorMode(p) for p in f.PropertiesList},
            "enums": {p: f.getEnumerationsOfProperty(p) for p in f.PropertiesList
                      if f.getTypeIdOfProperty(p) == "App::PropertyEnumeration"}}


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
                if depth < 1:
                    walk(i0, depth + 1)
        walk(QtCore.QModelIndex(), 0)
        out.append(rows)
    Gui.Selection.clearSelection()
    return out


def in_edit():
    e = Gui.ActiveDocument.getInEdit()
    return e.Object if e else None


def shape_of(o):
    s = o.Shape
    return {"volume": round(s.Volume, 6), "area": round(s.Area, 6), "solids": len(s.Solids), "faces": len(s.Faces),
            "valid": o.isValid(), "status": o.getStatusString()}


pump(1.5)
Gui.activateWorkbench("PartDesignWorkbench")
pump(1.0)
doc = App.newDocument("Unnamed")
pump(0.5)


def setup():
    Gui.runCommand("PartDesign_Body", 0)
    pump(1.0)
    global body
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
    sk2 = body.newObject("Sketcher::SketchObject", "Sketch001")
    sk2.AttachmentSupport = [(doc.getObject("XY_Plane"), "")]
    sk2.MapMode = "FlatFace"
    sk2.AttachmentOffset = App.Placement(V(0, 0, 5), App.Rotation())
    sk2.addGeometry(Part.Circle(V(8, 10, 0), V(0, 0, 1), 3), False)
    pocket = body.newObject("PartDesign::Pocket", "Pocket")
    pocket.Profile = sk2
    pocket.Length = 5
    doc.recompute()
    pump(1.0)
    return {"objects": objects(), "volume": round(body.Shape.Volume, 6)}


safe("setup", setup)


def transformed(command, selection=("Pocket",)):
    Gui.Selection.clearSelection()
    for s in selection:
        Gui.Selection.addSelection(doc.getObject(s))
    pump(0.4)
    before = {o.Name for o in doc.Objects}
    Gui.runCommand(command, 0)
    pump(2.0)
    out = {"task": task_widgets()}
    f = in_edit()
    out["in_edit"] = f.Name if f else None
    if f is not None:
        out["props"] = props(f)
        out["undo"] = doc.UndoNames[:3]
    out["ok"] = click_button("OK")
    pump(1.5)
    out["new"] = sorted({o.Name for o in doc.Objects} - before)
    if f is not None:
        out["shape"] = shape_of(f)
        out["tip"] = body.Tip.Name if body.Tip else None
    out["undo_after"] = doc.UndoNames[:3]
    return out


for _c in ("Mirrored", "LinearPattern", "PolarPattern"):
    safe(_c, lambda c=_c: transformed("PartDesign_" + c))


def multi():
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.getObject("Pocket"))
    pump(0.4)
    Gui.runCommand("PartDesign_MultiTransform", 0)
    pump(2.0)
    out = {"task": task_widgets()}
    f = in_edit()
    out["in_edit"] = f.Name if f else None
    if f is not None:
        out["props"] = props(f)
    lists = [w for w in mw.findChildren(QtWidgets.QListWidget) if w.objectName() == "listTransformFeatures"]
    if lists:
        lw = lists[0]
        holder = {}

        def grab():
            menus = [w for w in app.topLevelWidgets() if isinstance(w, QtWidgets.QMenu) and w.isVisible() and w.actions()]
            if menus:
                m = menus[0]
                holder["menu"] = dump_menu(m)
                acts = [a for a in m.actions() if "mirror" in a.text().lower()]
                m.close()
                timer.stop()
                holder["mirror_action"] = acts[0].text() if acts else None
        timer = QtCore.QTimer()
        timer.timeout.connect(grab)
        timer.start(150)
        pos = QtCore.QPoint(10, 10)
        app.sendEvent(lw.viewport(), QtGui.QContextMenuEvent(QtGui.QContextMenuEvent.Mouse, pos, lw.viewport().mapToGlobal(pos)))
        pump(1.0)
        timer.stop()
        out["context_menu"] = holder.get("menu")
        out["actions"] = [{"text": a.text(), "enabled": a.isEnabled()} for a in lw.actions()]
        for a in lw.actions():
            if "mirror" in a.text().lower():
                a.trigger()
                pump(2.0)
                break
        out["task_mirror"] = task_widgets()
        out["objects_mirror"] = objects()
        out["transformations"] = [o.Name for o in f.Transformations] if f is not None else None
        click_button("OK")              # the sub panel's OK
        pump(1.0)
        out["task_after_sub"] = task_widgets()
        for a in lw.actions():
            if "linear" in a.text().lower():
                a.trigger()
                pump(2.0)
                break
        out["task_linear"] = task_widgets()
        click_button("OK")
        pump(1.0)
        out["transformations2"] = [o.Name for o in f.Transformations] if f is not None else None
        if f is not None:
            out["sub_props"] = {o.Name: props(o) for o in f.Transformations}
    out["ok"] = click_button("OK")
    pump(1.5)
    if f is not None:
        out["shape"] = shape_of(f)
    out["objects_after"] = objects()
    out["undo_after"] = doc.UndoNames[:4]
    return out


safe("MultiTransform", multi)
safe("whole_shape", lambda: transformed("PartDesign_PolarPattern", ()))


def edit(name):
    Gui.ActiveDocument.setEdit(doc.getObject(name), 0)
    pump(1.5)
    out = {"task": task_widgets()}
    click_button("Cancel")
    pump(0.8)
    return out


safe("edit_Mirrored", lambda: edit("Mirrored"))
safe("edit_LinearPattern", lambda: edit("LinearPattern"))
safe("edit_PolarPattern", lambda: edit("PolarPattern"))
safe("edit_MultiTransform", lambda: edit("MultiTransform"))

PRIMS = ("Box", "Cylinder", "Sphere", "Cone", "Ellipsoid", "Torus", "Prism", "Wedge")


def primitive(kind, i):
    Gui.Selection.clearSelection()
    pump(0.3)
    before = {o.Name for o in doc.Objects}
    Gui.runCommand(f"PartDesign_CompPrimitive{kind}", i)
    pump(2.0)
    out = {"task": task_widgets(), "undo": doc.UndoNames[:2]}
    f = in_edit()
    out["in_edit"] = f.Name if f else None
    if f is not None:
        out["props"] = props(f)
    out["ok"] = click_button("OK")
    pump(1.5)
    out["new"] = sorted({o.Name for o in doc.Objects} - before)
    if f is not None:
        out["shape"] = shape_of(f)
    return out


for _k in ("Additive", "Subtractive"):
    for _i, _p in enumerate(PRIMS):
        safe(f"prim_{_k}{_p}", lambda k=_k, i=_i: primitive(k, i))

safe("tree", tree_rows)
for _n in ("Mirrored", "LinearPattern", "PolarPattern", "MultiTransform", "Box", "Subtractive_Box", "Box001"):
    if doc.getObject(_n) is not None:
        safe("props_" + _n, lambda n=_n: property_view(n))
res["objects_end"] = objects()

json.dump(res, open(os.path.join(OUT, "fctransform.json"), "w"), indent=1)
os._exit(0)

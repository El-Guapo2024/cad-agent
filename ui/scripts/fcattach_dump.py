# SPDX-License-Identifier: LGPL-2.1-or-later
# Runs inside FreeCAD's GUI (fcattach.py starts it under fclaunch, windows kept off the screen): what the real FreeCAD does
# with attachment, for attachcheck.mjs to hold the page to. On a Body with a 40 x 20 x 5 plate (Sketch on XY, Pad):
#   sketch_on_face  Pad's Face6 selected, PartDesign_NewSketch: the sketch made on it (support, mode, placement, the
#                   transaction's name) and opened
#   datum_*         Edit > Create > Datums' four commands, with a selection and without: the Attachment panel's widgets
#                   as it opens (and after a pick), then OK: the object made (type, name, mode, support, placement) and
#                   the transaction; Cancel makes nothing
#   edit            a datum's double-click: the panel with its values
#   tree            the Body's rows with the datums in it
# Writes FCGUI_OUT/fcattach.json.
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
res = {"errors": {}}
mw.resize(1280, 800)
V = App.Vector
app = QtWidgets.QApplication.instance()


# The same helpers as fcedit_dump.py's (copied: that file is a script)
def pump(sec=0.3):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents(QtCore.QEventLoop.AllEvents, 50)
        time.sleep(0.005)


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



def bail():
    res["errors"]["hung"] = "stopped after 600 s"
    json.dump(res, open(os.path.join(OUT, "fcattach.json"), "w"), indent=1)
    os._exit(0)


QtCore.QTimer.singleShot(600000, bail)


def safe(name, fn):
    try:
        res[name] = fn()
    except Exception:
        res["errors"][name] = traceback.format_exc()


def place(p):
    return [list(p.Base), list(p.Rotation.Q)]


def support(o):
    return [[x[0].Name, list(x[1])] for x in o.AttachmentSupport]


def state(o):
    return {"name": o.Name, "label": o.Label, "type": o.TypeId, "map_mode": o.MapMode, "support": support(o),
            "placement": place(o.Placement), "reversed": o.MapReversed}


doc = App.newDocument("attach")
Gui.runCommand("PartDesign_Body", 0)
pump(1.0)
body = doc.getObject("Body")
planes = {o.Role: o for o in body.Origin.OriginFeatures}
sk = body.newObject("Sketcher::SketchObject", "Sketch")
sk.AttachmentSupport = [(planes["XY_Plane"], "")]
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
Gui.ActiveDocument.ActiveView.viewIsometric()
pump(1.0)
before = set(o.Name for o in doc.Objects)


def new_objects():
    global before
    now = [o for o in doc.Objects if o.Name not in before]
    before = set(o.Name for o in doc.Objects)
    return now


def select(*subs):
    Gui.Selection.clearSelection()
    for obj, sub in subs:
        Gui.Selection.addSelection(doc.Name, obj, sub)
    pump(0.4)


def sketch_on_face():
    select(("Pad", "Face6"))
    Gui.runCommand("PartDesign_NewSketch", 0)
    pump(1.5)
    made = new_objects()
    out = {"made": [state(o) for o in made], "undo": doc.UndoNames[:1],
           "in_edit": str(Gui.ActiveDocument.getInEdit().Object.Name) if Gui.ActiveDocument.getInEdit() else None}
    Gui.ActiveDocument.resetEdit()
    pump(1.0)
    return out


safe("sketch_on_face", sketch_on_face)


def datum(cmd, sel=(), pick=None, flip=False, ok=True):
    select(*sel)
    Gui.runCommand(cmd, 0)
    pump(1.5)
    out = {"task": task_widgets()}
    if pick:
        Gui.Selection.addSelection(doc.Name, *pick)
        pump(1.0)
        out["task_picked"] = task_widgets()
    if flip:
        for b in mw.findChildren(QtWidgets.QCheckBox):
            if b.isVisible() and b.objectName() == "checkBoxFlip":
                b.click()
        pump(0.6)
        out["task_flipped"] = task_widgets()
    out["clicked"] = click_button("OK" if ok else "Cancel")
    pump(1.5)
    doc.recompute()
    out["made"] = [state(o) for o in new_objects() if hasattr(o, "MapMode")]
    out["undo"] = doc.UndoNames[:1]
    return out


safe("datum_plane_face", lambda: datum("Part_DatumPlane", sel=[("Pad", "Face2")]))
safe("datum_plane_pick", lambda: datum("Part_DatumPlane", pick=("XY_Plane", ""), flip=True))
safe("datum_line_vertices", lambda: datum("Part_DatumLine", sel=[("Pad", "Vertex1"), ("Pad", "Vertex6")]))
safe("datum_point_edge", lambda: datum("Part_DatumPoint", sel=[("Pad", "Edge4")]))
safe("lcs_pick", lambda: datum("Part_CoordinateSystem", pick=("Pad", "Vertex6")))
safe("cancel", lambda: datum("Part_DatumPlane", sel=[("Pad", "Face1")], ok=False))


def edit():
    Gui.Selection.clearSelection()
    Gui.ActiveDocument.getObject("DatumPlane").doubleClicked()
    pump(1.5)
    out = {"task": task_widgets()}
    click_button("Cancel")
    pump(1.0)
    return out


safe("edit", edit)
safe("tree", tree_rows)
json.dump(res, open(os.path.join(OUT, "fcattach.json"), "w"), indent=1)
os._exit(0)

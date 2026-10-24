# Runs inside FreeCAD's GUI (fcrevolve.py starts it under fclaunch, windows kept off the screen): what the real
# PartDesign workbench shows for Revolution, Groove and Hole, for revolvecheck.mjs to compare the page with. Writes
# fcrevolve.json into FCGUI_OUT:
#   revolution  PartDesign_Revolution on a sketch on XZ (a rectangle at x 5..15 and a construction line): the task
#               panel's widgets in order, the new feature's properties (value, group, editor mode, enumerations), then
#               the panel after Two sided and after Up to face, and the properties after OK
#   groove      PartDesign_Groove on a notch sketch, the same
#   hole        PartDesign_Hole on a circle on the plate's top: the panel as it opens, then after each of: the thread
#               type ISO metric, the size M6, the cut type ISO 4762, Threaded; and the properties after OK
#   props_*     the property view's Data tab for each feature
import json
import os
import time
import traceback

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide6 import QtCore, QtWidgets

OUT = os.environ["FCGUI_OUT"]
mw = Gui.getMainWindow()
app = QtWidgets.QApplication.instance()
res = {"errors": {}}
mw.resize(1280, 800)
V = App.Vector


def bail():
    res["errors"]["hung"] = "stopped after 600 s"
    json.dump(res, open(os.path.join(OUT, "fcrevolve.json"), "w"), indent=1)
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


def task_view():
    views = [w for w in mw.findChildren(QtWidgets.QWidget) if w.metaObject().className() == "Gui::TaskView::TaskView"]
    return [v for v in views if v.isVisible()]


def task_widgets():
    """The open task panel's widgets, top to bottom: labels, buttons and check boxes with their text, combo boxes with
    their items and current one, spin boxes and line edits with their text, the box headers."""
    out = []
    for tv in task_view():
        items = []
        for w in tv.findChildren(QtWidgets.QWidget):
            if not w.isVisible():
                continue
            cls = w.metaObject().className()
            pos = w.mapTo(tv, QtCore.QPoint(0, 0))
            d = {"class": cls, "name": w.objectName(), "y": pos.y(), "x": pos.x(), "enabled": w.isEnabled()}
            if isinstance(w, QtWidgets.QComboBox):
                d["items"] = [w.itemText(i) for i in range(w.count())]
                d["current"] = w.currentText()
            elif isinstance(w, QtWidgets.QAbstractSpinBox):
                d["text"] = w.text()
            elif isinstance(w, QtWidgets.QLineEdit):
                d["text"] = w.text()
                d["placeholder"] = w.placeholderText()
            elif isinstance(w, QtWidgets.QAbstractButton):
                d["text"] = w.text()
                if w.isCheckable():
                    d["checked"] = w.isChecked()
            elif isinstance(w, QtWidgets.QLabel):
                if not w.text():
                    continue
                d["text"] = w.text()
            elif isinstance(w, QtWidgets.QGroupBox):
                d["text"] = w.title()
            elif cls in ("Gui::ElideLabel", "Gui::ElideCheckBox"):
                t = w.property("text")
                if not t:
                    continue
                d["text"] = t
                if cls == "Gui::ElideCheckBox":
                    d["checked"] = bool(w.property("checked"))
            elif cls.endswith("TaskHeader"):
                d["text"] = " ".join(lab.text() for lab in w.findChildren(QtWidgets.QLabel) if lab.text())
            else:
                continue
            items.append(d)
        items.sort(key=lambda d: (d["y"], d["x"]))
        out.append(items)
    return out


def widget(name):
    for tv in task_view():
        for w in tv.findChildren(QtWidgets.QWidget, name):
            if w.isVisible():
                return w
    return None


def props(f):
    out = {}
    for p in f.PropertiesList:
        v = getattr(f, p)
        v = getattr(v, "Value", v)
        out[p] = {"value": v if isinstance(v, (int, float, str, bool)) else str(v), "group": f.getGroupOfProperty(p),
                  "type": f.getTypeIdOfProperty(p), "mode": f.getEditorMode(p)}
        if f.getTypeIdOfProperty(p) == "App::PropertyEnumeration":
            out[p]["enums"] = f.getEnumerationsOfProperty(p)
    return out


def click_button(text):
    for b in mw.findChildren(QtWidgets.QAbstractButton):
        if b.isVisible() and b.text().replace("&", "") == text:
            b.click()
            pump(0.8)
            return True
    return False


def in_edit():
    e = Gui.ActiveDocument.getInEdit()
    return e.Object if e else None


def rect_sketch(body, name, plane, x0, y0, x1, y1, extra=(), offset=None):
    sk = body.newObject("Sketcher::SketchObject", name)
    sk.AttachmentSupport = [(doc.getObject(plane), "")]
    sk.MapMode = "FlatFace"
    if offset is not None:
        sk.AttachmentOffset = App.Placement(V(*offset), App.Rotation())
    pts = [V(x0, y0, 0), V(x1, y0, 0), V(x1, y1, 0), V(x0, y1, 0)]
    for i in range(4):
        sk.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 4]), False)
    for g, c in extra:
        sk.addGeometry(g, c)
    doc.recompute()
    return sk


def feature_panel(command, profile, steps=()):
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(profile)
    pump(0.4)
    Gui.runCommand(command, 0)
    pump(1.5)
    f = in_edit()
    out = {"task": task_widgets(), "in_edit": f.Name if f else None, "props": props(f) if f else None}
    for label, fn in steps:
        fn()
        pump(1.0)
        out["task_" + label] = task_widgets()
        out["props_" + label] = props(f) if f else None
    out["ok"] = click_button("OK")
    pump(1.0)
    out["props_after"] = props(f) if f else None
    out["valid"] = f.isValid() if f else None
    out["status"] = f.getStatusString() if f else None
    return out


def set_combo(name, text):
    def go():
        w = widget(name)
        i = w.findText(text)
        w.setCurrentIndex(i)
        if hasattr(w, "activated"):
            w.activated.emit(i)
    return go


def set_check(name, on=True):
    def go():
        w = widget(name)
        if w.isChecked() != on:
            w.click()
    return go


pump(1.5)
Gui.activateWorkbench("PartDesignWorkbench")
pump(1.0)
doc = App.newDocument("Unnamed")
pump(0.5)
Gui.runCommand("PartDesign_Body", 0)
pump(1.0)
body = doc.getObject("Body")


def revolution():
    sk = rect_sketch(body, "Sketch", "XZ_Plane", 5, 0, 15, 10,
                     [(Part.LineSegment(V(20, 0, 0), V(20, 10, 0)), True)])
    pump(0.5)
    return feature_panel("PartDesign_Revolution", sk, [
        ("two_sided", set_combo("sidesMode", "Two sided")),
        ("up_to_face", set_combo("changeMode", "Up to face")),
        ("angle_again", set_combo("changeMode", "Angle")),
        ("one_sided", set_combo("sidesMode", "One sided")),
    ])


safe("revolution", revolution)


def groove():
    sk = rect_sketch(body, "Sketch001", "XZ_Plane", 13, 4, 16, 6)
    pump(0.5)
    return feature_panel("PartDesign_Groove", sk, [("symmetric", set_combo("sidesMode", "Symmetric"))])


safe("groove", groove)


def hole():
    d2 = App.newDocument("Holes")
    Gui.runCommand("PartDesign_Body", 0)
    pump(1.0)
    b2 = d2.getObject("Body")
    global doc
    doc = d2
    base = rect_sketch(b2, "Base", "XY_Plane", 0, 0, 40, 20)
    pad = b2.newObject("PartDesign::Pad", "Pad")
    pad.Profile = base
    pad.Length = 10
    d2.recompute()
    sk = b2.newObject("Sketcher::SketchObject", "Holes")
    sk.AttachmentSupport = [(d2.getObject("XY_Plane"), "")]
    sk.MapMode = "FlatFace"
    sk.AttachmentOffset = App.Placement(V(0, 0, 10), App.Rotation())
    sk.addGeometry(Part.Circle(V(10, 10, 0), V(0, 0, 1), 2), False)
    d2.recompute()
    pump(0.5)
    return feature_panel("PartDesign_Hole", sk, [
        ("iso", set_combo("ThreadType", "ISO metric regular")),
        ("m6", set_combo("ThreadSize", "M6x1.0")),
        ("iso4762", set_combo("HoleCutType", "ISO 4762")),
        ("through_all", set_combo("DepthType", "Through all")),
        ("tap_drill", set_combo("HoleType", "Tap drill")),
        ("threaded", set_combo("HoleType", "Threaded")),
        ("model_thread", set_check("ModelThread", True)),
    ])


safe("hole", hole)


def property_view(name, d):
    App.setActiveDocument(d.Name)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(d.getObject(name))
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


unnamed = App.getDocument("Unnamed")
for _n, _d in (("Revolution", unnamed), ("Groove", unnamed), ("Hole", doc)):
    safe("props_" + _n, lambda n=_n, d=_d: property_view(n, d))

json.dump(res, open(os.path.join(OUT, "fcrevolve.json"), "w"), indent=1, default=str)
os._exit(0)

# Runs inside FreeCAD's GUI (fcsweep.py starts it under fclaunch, windows kept off the screen): what the real
# PartDesign workbench shows for Additive/Subtractive Loft, Pipe and Helix, for sweepcheck.mjs to compare the page
# with. Writes fcsweep.json into FCGUI_OUT:
#   loft        PartDesign_AdditiveLoft with a square on XY and a smaller square 20 above it selected (the second is the
#               section, as prepareProfileBased takes it): the panel's widgets in order, the new feature's properties
#               (value, group, editor mode, enumerations), the panel after Ruled and Closed, the properties after OK
#   pipe        PartDesign_AdditivePipe with a circle on XY and an L-shaped path on XZ selected: the three boxes, then
#               after each orientation mode, Multisection, Round corner, and the properties after OK
#   helix       PartDesign_AdditiveHelix on a rectangle at x 5..7 on XZ: the panel (the proposed pitch, the axis items,
#               the status), then after each mode, Left handed, a pitch of 1 mm (the self-intersection warning)
#   subloft, subpipe, subhelix   the subtractive ones in a second Body on a 40 x 40 x 20 block
#   each one's property_view: the property view's Data tab for the feature after OK
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
    json.dump(res, open(os.path.join(OUT, "fcsweep.json"), "w"), indent=1, default=str)
    os._exit(0)


QtCore.QTimer.singleShot(600000, bail)


def pump(sec=0.3):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents(QtCore.QEventLoop.AllEvents, 50)
        time.sleep(0.005)


def safe(name, fn):
    print("fcsweep:", name, flush=True)
    try:
        res[name] = fn()
    except Exception:
        res["errors"][name] = traceback.format_exc()
    json.dump(res, open(os.path.join(OUT, "fcsweep.json"), "w"), indent=1, default=str)


def task_view():
    views = [w for w in mw.findChildren(QtWidgets.QWidget) if w.metaObject().className() == "Gui::TaskView::TaskView"]
    return [v for v in views if v.isVisible()]


def task_widgets():
    """The open task panel's widgets, top to bottom: labels, buttons and check boxes with their text, combo boxes with
    their items and current one, spin boxes and line edits with their text, list widgets with their items, the box
    headers."""
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
            elif isinstance(w, QtWidgets.QListWidget):
                d["items"] = [w.item(i).text() for i in range(w.count())]
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


def sketch(body, name, plane, geometry, offset=None):
    sk = body.newObject("Sketcher::SketchObject", name)
    sk.AttachmentSupport = [(App.ActiveDocument.getObject(plane), "")]
    sk.MapMode = "FlatFace"
    if offset is not None:
        sk.AttachmentOffset = App.Placement(V(*offset), App.Rotation())
    for g in geometry:
        sk.addGeometry(g, False)
    App.ActiveDocument.recompute()
    return sk


def rect(x0, y0, x1, y1):
    pts = [V(x0, y0, 0), V(x1, y0, 0), V(x1, y1, 0), V(x0, y1, 0)]
    return [Part.LineSegment(pts[i], pts[(i + 1) % 4]) for i in range(4)]


def property_view(obj):
    """The property view's rows for obj, a feature of the active document."""
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


def feature_panel(command, selection, steps=()):
    Gui.Selection.clearSelection()
    for o in selection:
        Gui.Selection.addSelection(o)
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
    if in_edit() is not None:            # OK refused (a message box): note it and cancel
        out["ok_refused"] = True
        for w in QtWidgets.QApplication.topLevelWidgets():
            if isinstance(w, QtWidgets.QMessageBox) and w.isVisible():
                out["message"] = w.text()
                w.accept()
        pump(0.5)
        click_button("Cancel")
    out["props_after"] = props(f) if f else None
    out["valid"] = f.isValid() if f else None
    out["status"] = f.getStatusString() if f else None
    out["volume"] = f.Shape.Volume if f and not f.Shape.isNull() else None
    if f is not None:
        out["property_view"] = property_view(f)
    return out


def set_combo(name, text):
    def go():
        w = widget(name)
        i = w.findText(text)
        w.setCurrentIndex(i)
        w.activated.emit(i)
    return go


def set_check(name, on=True):
    def go():
        w = widget(name)
        if w.isChecked() != on:
            w.click()
    return go


def set_spin(name, value):
    def go():
        w = widget(name)
        QtCore.QMetaObject.invokeMethod(w, "setValue", QtCore.Q_ARG(float, value))
    return go


pump(1.5)
Gui.activateWorkbench("PartDesignWorkbench")
pump(1.0)
doc = App.newDocument("Unnamed")
pump(0.5)
Gui.runCommand("PartDesign_Body", 0)
pump(1.0)
body = doc.getObject("Body")


def loft():
    a = sketch(body, "Sketch", "XY_Plane", rect(-10, -10, 10, 10))
    b = sketch(body, "Sketch001", "XY_Plane", rect(-5, -5, 5, 5), offset=(0, 0, 20))
    pump(0.5)
    return feature_panel("PartDesign_AdditiveLoft", [a, b], [
        ("ruled", set_check("checkBoxRuled", True)),
        ("closed", set_check("checkBoxClosed", True)),
        ("unclosed", set_check("checkBoxClosed", False)),
    ])


safe("loft", loft)


def pipe():
    a = sketch(body, "Sketch002", "XY_Plane", [Part.Circle(V(0, 0, 0), V(0, 0, 1), 3)], offset=(30, 0, 0))
    b = sketch(body, "Sketch003", "XZ_Plane", [Part.LineSegment(V(30, 0, 0), V(30, 30, 0)),
                                               Part.ArcOfCircle(Part.Circle(V(50, 30, 0), V(0, 0, 1), 20), 1.5707963267948966, 3.141592653589793)])
    pump(0.5)
    return feature_panel("PartDesign_AdditivePipe", [a, b], [
        ("frenet", set_combo("comboBoxMode", "Frenet")),
        ("auxiliary", set_combo("comboBoxMode", "Auxiliary")),
        ("binormal", set_combo("comboBoxMode", "Binormal")),
        ("standard", set_combo("comboBoxMode", "Standard")),
        ("multisection", set_combo("comboBoxScaling", "Multisection")),
        ("constant", set_combo("comboBoxScaling", "Constant")),
        ("round", set_combo("comboBoxTransition", "Round corner")),
    ])


safe("pipe", pipe)


def helix():
    a = sketch(body, "Sketch004", "XZ_Plane", rect(65, 0, 67, 2))
    pump(0.5)
    return feature_panel("PartDesign_AdditiveHelix", [a], [
        ("pitch_turns", set_combo("inputMode", "Pitch-Turns-Angle")),
        ("height_turns", set_combo("inputMode", "Height-Turns-Angle")),
        ("height_turns_growth", set_combo("inputMode", "Height-Turns-Growth")),
        ("pitch_height", set_combo("inputMode", "Pitch-Height-Angle")),
        ("left_handed", set_check("checkBoxLeftHanded", True)),
        ("pitch_small", set_spin("pitch", 1.0)),
        ("pitch_back", set_spin("pitch", 5.0)),
        ("z_axis", set_combo("axis", "Base Z-axis")),
    ])


safe("helix", helix)


def subtractive():
    d2 = App.newDocument("Block")
    Gui.runCommand("PartDesign_Body", 0)
    pump(1.0)
    b2 = d2.getObject("Body")
    base = sketch(b2, "Base", "XY_Plane", rect(-20, -20, 20, 20))
    pad = b2.newObject("PartDesign::Pad", "Pad")
    pad.Profile = base
    pad.Length = 20
    d2.recompute()
    out = {}
    lo = sketch(b2, "Sketch", "XY_Plane", rect(-8, -8, 8, 8), offset=(0, 0, -5))
    hi = sketch(b2, "Sketch001", "XY_Plane", rect(-3, -3, 3, 3), offset=(0, 0, 25))
    pump(0.5)
    out["subloft"] = feature_panel("PartDesign_SubtractiveLoft", [lo, hi], [
        ("common", set_combo("comboOperation", "Common")), ("subtraction", set_combo("comboOperation", "Subtraction"))])
    prof = sketch(b2, "Sketch002", "YZ_Plane", [Part.Circle(V(0, 20, 0), V(0, 0, 1), 3)], offset=(0, 0, -25))
    path = sketch(b2, "Sketch003", "XY_Plane", [Part.LineSegment(V(-25, 0, 0), V(25, 0, 0))], offset=(0, 0, 20))
    pump(0.5)
    out["subpipe"] = feature_panel("PartDesign_SubtractivePipe", [prof, path])
    hx = sketch(b2, "Sketch004", "XZ_Plane", rect(18, 0, 22, 2))
    pump(0.5)
    out["subhelix"] = feature_panel("PartDesign_SubtractiveHelix", [hx], [
        ("common", set_combo("comboOperation", "Common")), ("subtraction", set_combo("comboOperation", "Subtraction"))])
    return out


safe("subtractive", subtractive)


json.dump(res, open(os.path.join(OUT, "fcsweep.json"), "w"), indent=1, default=str)
os._exit(0)

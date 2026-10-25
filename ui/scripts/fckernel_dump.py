# Runs inside FreeCAD's GUI (fckernel.py starts it under fclaunch, windows kept off the screen): what the real PartDesign
# workbench shows for the kernel behaviour cad_agent adds (feature_taper.py, feature_startref.py, the Common operation,
# feature_scaled.py), for kernelcheck.mjs to compare the page with. Writes fckernel.json into FCGUI_OUT:
#   pocket   PartDesign_Pocket on a circle on a 40 x 20 x 10 plate's top: the task panel's widgets as it opens, then after
#            Start Reference (the Reference row and Pick Reference), a pick of the plate's Face6, a 10 degree taper,
#            Operation Common, Through all, Two sided; the properties after each and after OK
#   multi    PartDesign_MultiTransform on that Pocket: the Transformations list's context menu, then Add Scale
#            Transformation (the new Scale's name and properties, the panel with its fields) and OK
#   props_*  the property view's Data tab for the Pocket and the Scale
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
    res["errors"]["hung"] = "stopped after 400 s"
    json.dump(res, open(os.path.join(OUT, "fckernel.json"), "w"), indent=1, default=str)
    os._exit(0)


QtCore.QTimer.singleShot(400000, bail)


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
    """The open task panel's named widgets that are visible: combo boxes (items, current), spin boxes and line edits
    (text, placeholder), buttons and check boxes (text, checked), with their enabled state."""
    out = {}
    for tv in task_view():
        for w in tv.findChildren(QtWidgets.QWidget):
            if not w.isVisible() or not w.objectName() or w.objectName().startswith("qt_"):
                continue
            d = {"class": w.metaObject().className(), "enabled": w.isEnabled()}
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
            else:
                continue
            out[w.objectName()] = d
    return out


def widget(name):
    for tv in task_view():
        for w in tv.findChildren(QtWidgets.QWidget, name):
            if w.isVisible():
                return w
    return None


def props(f, names):
    out = {}
    for p in names:
        if p not in f.PropertiesList:
            continue
        v = getattr(f, p)
        v = getattr(v, "Value", v)
        if p == "StartReference":
            v = None if v is None else [v[0].Name, list(v[1])]
        out[p] = {"value": v if isinstance(v, (int, float, str, bool, list, type(None))) else str(v), "mode": f.getEditorMode(p)}
        if f.getTypeIdOfProperty(p) == "App::PropertyEnumeration":
            out[p]["enums"] = f.getEnumerationsOfProperty(p)
    return out


POCKET_PROPS = ["StartType", "StartOffset", "StartReference", "TaperAngle", "TaperAngle2", "Operation", "Type", "Type2",
                "SideType"]


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


def set_combo(name, text):
    w = widget(name)
    i = w.findText(text)
    w.setCurrentIndex(i)
    if hasattr(w, "activated"):
        w.activated.emit(i)


pump(1.5)
Gui.activateWorkbench("PartDesignWorkbench")
pump(1.0)
doc = App.newDocument("Unnamed")
pump(0.5)
Gui.runCommand("PartDesign_Body", 0)
pump(1.0)
body = doc.getObject("Body")
base = body.newObject("Sketcher::SketchObject", "Sketch")
base.AttachmentSupport = [(doc.getObject("XY_Plane"), "")]
base.MapMode = "FlatFace"
pts = [V(0, 0, 0), V(40, 0, 0), V(40, 20, 0), V(0, 20, 0)]
for i in range(4):
    base.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 4]), False)
pad = body.newObject("PartDesign::Pad", "Pad")
pad.Profile = base
pad.Length = 10
top = body.newObject("Sketcher::SketchObject", "Sketch001")
top.AttachmentSupport = [(doc.getObject("XY_Plane"), "")]
top.MapMode = "FlatFace"
top.AttachmentOffset = App.Placement(V(0, 0, 10), App.Rotation())
top.addGeometry(Part.Circle(V(20, 10, 0), V(0, 0, 1), 6), False)
doc.recompute()
pump(0.5)


def pocket():
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(top)
    pump(0.4)
    Gui.runCommand("PartDesign_Pocket", 0)
    pump(1.5)
    f = in_edit()
    out = {"task": task_widgets(), "props": props(f, POCKET_PROPS)}

    def step(label, fn):
        fn()
        pump(1.0)
        out["task_" + label] = task_widgets()
        out["props_" + label] = props(f, POCKET_PROPS)

    step("reference", lambda: set_combo("startMode", "Reference"))
    step("pick", lambda: (Gui.Selection.clearSelection(), Gui.Selection.addSelection(doc.Name, "Pad", "Face6")))
    step("taper", lambda: widget("taperEdit").setProperty("rawValue", 10.0))
    step("common", lambda: set_combo("comboOperation", "Common"))
    step("through_all", lambda: set_combo("changeMode", "Through all"))
    step("two_sided", lambda: set_combo("sidesMode", "Two sided"))
    step("dimension2", lambda: set_combo("changeMode2", "Dimension"))
    step("one_sided", lambda: set_combo("sidesMode", "One sided"))
    out["ok"] = click_button("OK")
    pump(1.0)
    out["props_after"] = props(f, POCKET_PROPS)
    out["name"] = f.Name
    return out


safe("pocket", pocket)


def multi():
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.getObject("Pocket"))
    pump(0.4)
    Gui.runCommand("PartDesign_MultiTransform", 0)
    pump(1.5)
    f = in_edit()
    lst = widget("listTransformFeatures")
    actions = [{"text": a.text().replace("&", ""), "enabled": a.isEnabled(), "separator": a.isSeparator()} for a in lst.actions()]
    before = set(o.Name for o in doc.Objects)
    for a in lst.actions():
        if a.text().replace("&", "") == "Add Scale Transformation":
            a.trigger()
            break
    pump(1.5)
    new = [o for o in doc.Objects if o.Name not in before]
    out = {"actions": actions, "new": [(o.Name, o.TypeId) for o in new], "task": task_widgets(),
           "transformations": [o.Name for o in f.Transformations] if f else None}
    if new:
        out["props_scale"] = props(new[0], ["Factor", "Occurrences", "Originals", "TransformMode", "Refine"])
    out["ok"] = click_button("OK")
    pump(1.0)
    out["valid"] = f.isValid() if f else None
    out["name"] = f.Name if f else None
    return out


safe("multi", multi)


def property_view(name):
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


for _n in ("Pocket", "Scale"):
    safe("props_" + _n, lambda n=_n: property_view(n))

json.dump(res, open(os.path.join(OUT, "fckernel.json"), "w"), indent=1, default=str)
os._exit(0)

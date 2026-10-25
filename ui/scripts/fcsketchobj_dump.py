# SPDX-License-Identifier: LGPL-2.1-or-later
# Runs inside FreeCAD's GUI (fcsketchobj.py starts it under fclaunch, windows kept off the screen): what the real FreeCAD
# does with the Sketcher's commands on sketch objects, for sketchobjcheck.mjs to hold the page to. On a Body with a
# 40 x 20 x 5 plate (Sketch on XY, Pad), Sketch001 on the XZ plane (offset 3) and Sketch002 on the Pad's top face with
# external geometry, each case selects in the tree, runs the command and answers its dialogs as a person does:
#   enabled      each command's enabled state with nothing, one sketch, two sketches, a face selected
#   mirror_*     Sketcher_MirrorSketch: SketchMirrorDialog's widgets, the sketch(es) made (name, group, placement,
#                attachment, geometry, constraints), the transaction; Cancel makes nothing
#   merge_*      Sketcher_MergeSketches: the sketch made, the Report view's lines
#   reorient_*   Sketcher_ReorientSketch: the "Sketch Has Support" question, SketchOrientationDialog's widgets, the
#                placement and attachment after OK, whether the sketch opened
#   map_*        Sketcher_MapSketch: its two QInputDialogs (titles, labels, items, current), the attachment after them
#   validate     Sketcher_ValidateSketch: the task panel's widgets, then each button: its dialogs, the transaction and what changed (the notification texts are the source's)
# Every case is undone after it (doc.undo), so each starts from the same document. Writes FCGUI_OUT/fcsketchobj.json.
import json
import math
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
ALIGNMENTS = {1: "EllipseMajorDiameter", 2: "EllipseMinorDiameter", 3: "EllipseFocus1", 4: "EllipseFocus2",
              5: "HyperbolaMajor", 6: "HyperbolaMinor", 7: "HyperbolaFocus", 8: "ParabolaFocus",
              9: "BSplineControlPoint", 10: "BSplineKnotPoint", 11: "ParabolaFocalAxis"}
DIMENSIONAL = ("Distance", "DistanceX", "DistanceY", "Radius", "Diameter", "Angle", "Weight", "SnellsLaw")


def pump(sec=0.3):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents(QtCore.QEventLoop.AllEvents, 50)
        time.sleep(0.005)


def bail():
    res["errors"]["hung"] = "stopped after 600 s"
    json.dump(res, open(os.path.join(OUT, "fcsketchobj.json"), "w"), indent=1)
    os._exit(0)


QtCore.QTimer.singleShot(600000, bail)


def safe(name, fn):
    try:
        res[name] = fn()
    except Exception:
        res["errors"][name] = traceback.format_exc()


def widgets(root):
    """A dialog's or panel's visible widgets, top to bottom (as fcattach_dump.py reads a task panel)."""
    items = []
    for w in root.findChildren(QtWidgets.QWidget):
        if not w.isVisible():
            continue
        cls = w.metaObject().className()
        pos = w.mapTo(root, QtCore.QPoint(0, 0))
        d = {"class": cls, "name": w.objectName(), "y": pos.y(), "x": pos.x(), "enabled": w.isEnabled()}
        if isinstance(w, QtWidgets.QLabel) and (w.text() or w.pixmap() and not w.pixmap().isNull()):
            d["text"] = w.text()
            if w.toolTip():
                d["tip"] = w.toolTip()
        elif isinstance(w, QtWidgets.QAbstractButton):
            d["text"] = w.text()
            if w.isCheckable():
                d["checked"] = w.isChecked()
            if w.toolTip():
                d["tip"] = w.toolTip()
        elif isinstance(w, QtWidgets.QComboBox):
            d["items"] = [w.itemText(i) for i in range(w.count())]
            d["current"] = w.currentText()
            d["editable"] = w.isEditable()
            if w.toolTip():
                d["tip"] = w.toolTip()
        elif isinstance(w, QtWidgets.QAbstractSpinBox):
            d["text"] = w.text()
        elif isinstance(w, QtWidgets.QGroupBox):
            d["title"] = w.title()
            if w.toolTip():
                d["tip"] = w.toolTip()
        elif cls.endswith("TaskHeader") or cls == "QSint::TaskHeader" or cls.endswith("TaskBoxHeader"):
            d["text"] = " ".join(lb.text() for lb in w.findChildren(QtWidgets.QLabel) if lb.text())
        elif isinstance(w, QtWidgets.QLineEdit) and not isinstance(w.parent(), (QtWidgets.QComboBox, QtWidgets.QAbstractSpinBox)):
            d["text"] = w.text()
        else:
            continue
        items.append(d)
    items.sort(key=lambda d: (d["y"], d["x"]))
    return items


def dialog_record(w):
    return {"class": w.metaObject().className(), "title": w.windowTitle(), "widgets": widgets(w),
            **({"text": w.text(), "buttons": [b.text().replace("&", "") for b in w.buttons()]}
               if isinstance(w, QtWidgets.QMessageBox) else {})}


DIALOGS = []


def answer(*actions):
    """Answer the modal dialogs the next command opens, one action each, recording each dialog as it opens."""
    todo = list(actions)

    def poll():
        w = QtWidgets.QApplication.activeModalWidget()
        if w is not None and todo and w.isVisible():
            pump(0.2)
            DIALOGS.append(dialog_record(w))
            act = todo.pop(0)
            try:
                act(w)
            except Exception:
                DIALOGS[-1]["error"] = traceback.format_exc()
                w.reject()
        if todo:
            QtCore.QTimer.singleShot(150, poll)
    QtCore.QTimer.singleShot(150, poll)


def click(text):
    def act(w):
        for b in w.findChildren(QtWidgets.QAbstractButton):
            if b.isVisible() and b.text().replace("&", "") == text:
                b.click()
                return
        raise RuntimeError(f"no button {text!r}")
    return act


def radio(text, then="OK"):
    def act(w):
        for b in w.findChildren(QtWidgets.QRadioButton):
            if b.text().replace("&", "") == text:
                b.click()
        pump(0.2)
        click(then)(w)
    return act


def pick_item(text):
    """QInputDialog::getItem: the item, then OK."""
    def act(w):
        combo = w.findChild(QtWidgets.QComboBox)
        i = combo.findText(text)
        if i < 0:
            raise RuntimeError(f"no item {text!r} in {[combo.itemText(k) for k in range(combo.count())]}")
        combo.setCurrentIndex(i)
        pump(0.1)
        click("OK")(w)
    return act


def orientation(plane, reverse, offset):
    def act(w):
        for b in w.findChildren(QtWidgets.QRadioButton):
            if b.text().replace("&", "") == plane:
                b.click()
        if reverse:
            for b in w.findChildren(QtWidgets.QCheckBox):
                if "Reverse" in b.text():
                    b.click()
        pump(0.2)
        DIALOGS[-1]["preview_after"] = widgets(w)
        spin = [s for s in w.findChildren(QtWidgets.QAbstractSpinBox)][0]
        spin.lineEdit().selectAll()
        spin.lineEdit().setText(f"{offset} mm")
        spin.lineEdit().editingFinished.emit()
        pump(0.2)
        click("OK")(w)
    return act


def report_text():
    for w in mw.findChildren(QtWidgets.QTextEdit):
        if w.metaObject().className() == "Gui::DockWnd::ReportOutput":
            return w.toPlainText()
    return ""


def xy(v):
    return [v.x, v.y]


def geo_out(g):
    t = type(g).__name__
    if t == "LineSegment":
        return {"type": t, "start": xy(g.StartPoint), "end": xy(g.EndPoint)}
    if t == "Circle":
        return {"type": t, "center": xy(g.Center), "radius": g.Radius}
    if t == "ArcOfCircle":
        return {"type": t, "center": xy(g.Center), "radius": g.Radius, "start_angle": g.FirstParameter,
                "end_angle": g.LastParameter}
    if t == "Point":
        return {"type": t, "at": [g.X, g.Y]}
    return {"type": t}


def constraint_out(c):
    import re
    a = dict(re.findall(r'(\w+)="([^"]*)"', c.Content))
    d = {"type": c.Type, "elements": [c.First, c.FirstPos, c.Second, c.SecondPos, c.Third, c.ThirdPos],
         "name": c.Name, "driving": c.Driving}
    if c.Type == "InternalAlignment":
        d["alignment"] = ALIGNMENTS.get(int(a.get("InternalAlignmentType", 0)), "Undef")
    if c.Type in DIMENSIONAL:
        d["value"] = c.Value
    return d


def placement(o):
    return {"position": list(o.Placement.Base), "rotation": list(o.Placement.Rotation.Q)}


def sketch_state(o):
    body = next((b for b in doc.Objects if b.TypeId == "PartDesign::Body" and o in b.Group), None)
    return {"name": o.Name, "label": o.Label, "type": o.TypeId, "body": body.Name if body else None,
            "index": body.Group.index(o) if body else None, "map_mode": o.MapMode,
            "support": [[x[0].Name, list(x[1])] for x in o.AttachmentSupport], "placement": placement(o),
            "offset": {"position": list(o.AttachmentOffset.Base), "rotation": list(o.AttachmentOffset.Rotation.Q)},
            "geometry": [dict(geo_out(g), construction=o.getConstruction(i)) for i, g in enumerate(o.Geometry)],
            "constraints": [constraint_out(c) for c in o.Constraints],
            "external": [[x[0].Name, x[1]] for x in zip([e[0] for e in o.ExternalGeometry], [s for e in o.ExternalGeometry for s in e[1]])]
            if o.ExternalGeometry else []}


# ── the document ─────────────────────────────────────────────────────────────────────────────────────────────
doc = App.newDocument("sketchobj")
Gui.activateWorkbench("PartDesignWorkbench")
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
sk.addConstraint([Sketcher.Constraint("Coincident", i, 2, (i + 1) % 4, 1) for i in range(4)]
                 + [Sketcher.Constraint("Horizontal", 0), Sketcher.Constraint("Horizontal", 2),
                    Sketcher.Constraint("Vertical", 1), Sketcher.Constraint("Vertical", 3),
                    Sketcher.Constraint("DistanceX", 0, 1, 0, 2, 40.0), Sketcher.Constraint("DistanceY", 1, 1, 1, 2, 20.0),
                    Sketcher.Constraint("Coincident", 0, 1, -1, 1)])
pad = body.newObject("PartDesign::Pad", "Pad")
pad.Profile = sk
pad.Length = 5
doc.recompute()
s1 = body.newObject("Sketcher::SketchObject", "Sketch001")
s1.AttachmentSupport = [(planes["XZ_Plane"], "")]
s1.MapMode = "FlatFace"
s1.AttachmentOffset = App.Placement(V(0, 0, 3), App.Rotation())
s1.addGeometry(Part.Circle(V(5, 5, 0), V(0, 0, 1), 2), False)
s1.addGeometry(Part.LineSegment(V(10, 0, 0), V(20, 0, 0)), False)
s1.addGeometry(Part.LineSegment(V(20, 1e-5, 0), V(20, 8, 0)), False)
s1.addGeometry(Part.ArcOfCircle(Part.Circle(V(30, 4, 0), V(0, 0, 1), 3), 0.5, 2.5), False)
s1.addGeometry(Part.LineSegment(V(-5, -5, 0), V(-5, 9, 0)), True)
s1.addConstraint([Sketcher.Constraint("Radius", 0, 2.0), Sketcher.Constraint("Horizontal", 1),
                  Sketcher.Constraint("Vertical", 2), Sketcher.Constraint("Distance", 1, 10.0)])
s1.renameConstraint(3, "len")
doc.recompute()
s2 = body.newObject("Sketcher::SketchObject", "Sketch002")
s2.AttachmentSupport = [(pad, "Face6")]
s2.MapMode = "FlatFace"
doc.recompute()
face6 = pad.Shape.Faces[5]
top_edge = next(f"Edge{i + 1}" for i, e in enumerate(pad.Shape.Edges) if e.isSame(face6.Edges[0]))
res["top_edge"] = top_edge
s2.addExternal("Pad", top_edge)
s2.addGeometry(Part.LineSegment(V(5, 5, 0), V(15, 8, 0)), False)
s2.addGeometry(Part.LineSegment(V(50, 50, 0), V(50 + 1e-9, 50, 0)), False)
s2.addConstraint(Sketcher.Constraint("PointOnObject", 0, 1, -3))
doc.recompute()
Gui.ActiveDocument.ActiveView.viewIsometric()
Gui.activateWorkbench("SketcherWorkbench")
pump(1.0)
res["setup"] = {o.Name: sketch_state(o) for o in (sk, s1, s2)}
COMMANDS = ["Sketcher_NewSketch", "Sketcher_EditSketch", "Sketcher_MapSketch", "Sketcher_ReorientSketch",
            "Sketcher_ValidateSketch", "Sketcher_MergeSketches", "Sketcher_MirrorSketch"]


def select(*names, sub=None):
    Gui.Selection.clearSelection()
    for n in names:
        Gui.Selection.addSelection(doc.Name, n, sub or "")
    pump(0.4)


def enabled():
    out = {}
    for label, sel in (("nothing", ()), ("one sketch", ("Sketch001",)), ("two sketches", ("Sketch", "Sketch001")),
                       ("the pad", ("Pad",))):
        select(*sel)
        out[label] = {c: bool(Gui.Command.get(c).isActive()) for c in COMMANDS}
    select("Pad", sub="Face6")
    out["a face"] = {c: bool(Gui.Command.get(c).isActive()) for c in COMMANDS}
    return out


safe("enabled", enabled)


def run(cmd, sel, *actions, sub=None, keep=False):
    """Select, run the command answering its dialogs, record what it made and changed, then undo it."""
    del DIALOGS[:]
    select(*sel, sub=sub)
    before = {o.Name for o in doc.Objects}
    states = {o.Name: json.dumps(sketch_state(o)) for o in doc.Objects if o.TypeId == "Sketcher::SketchObject"}
    rep0 = len(report_text())
    undo0 = len(doc.UndoNames)
    if actions:
        answer(*actions)
    Gui.runCommand(cmd, 0)
    pump(1.5)
    out = {"dialogs": list(DIALOGS), "undo": doc.UndoNames[:max(0, len(doc.UndoNames) - undo0)],
           "report": report_text()[rep0:].strip().splitlines()}
    out["made"] = [sketch_state(o) for o in doc.Objects if o.Name not in before and o.TypeId == "Sketcher::SketchObject"]
    out["changed"] = {n: sketch_state(doc.getObject(n)) for n, s in states.items()
                      if doc.getObject(n) and json.dumps(sketch_state(doc.getObject(n))) != s}
    ed = Gui.ActiveDocument.getInEdit()
    out["in_edit"] = ed.Object.Name if ed else None
    if ed:
        Gui.ActiveDocument.resetEdit()
        pump(1.0)
    if not keep:
        for _ in range(len(doc.UndoNames) - undo0):
            doc.undo()
        doc.recompute()
        pump(0.5)
    return out


safe("mirror_x", lambda: run("Sketcher_MirrorSketch", ["Sketch001"], radio("X-axis")))
safe("mirror_y_two", lambda: run("Sketcher_MirrorSketch", ["Sketch", "Sketch001"], radio("Y-axis")))
safe("mirror_origin", lambda: run("Sketcher_MirrorSketch", ["Sketch002"], radio("Origin")))
safe("mirror_external", lambda: run("Sketcher_MirrorSketch", ["Sketch002"], radio("Y-axis")))
safe("mirror_cancel", lambda: run("Sketcher_MirrorSketch", ["Sketch001"], click("Cancel")))
safe("merge_two", lambda: run("Sketcher_MergeSketches", ["Sketch001", "Sketch"]))
safe("merge_external", lambda: run("Sketcher_MergeSketches", ["Sketch002", "Sketch001"]))
def reattach():
    """Sketcher_ReorientSketch clears AttachmentSupport before its transaction opens, so undo leaves the sketch
    detached: put the supports back by hand, for the cases after."""
    s1.AttachmentSupport = [(planes["XZ_Plane"], "")]
    s1.MapMode = "FlatFace"
    s2.AttachmentSupport = [(pad, "Face6")]
    s2.MapMode = "FlatFace"
    doc.recompute()
    pump(0.5)
    return {o.Name: sketch_state(o) for o in (s1, s2)}


safe("reorient_no", lambda: run("Sketcher_ReorientSketch", ["Sketch001"], click("No")))
safe("reorient_yes", lambda: run("Sketcher_ReorientSketch", ["Sketch001"], click("Yes"),
                                 orientation("YZ-plane", True, 12.5)))
reattach()
safe("reorient_xz", lambda: run("Sketcher_ReorientSketch", ["Sketch002"], click("Yes"),
                                orientation("XZ-plane", False, -4)))
reattach()
safe("reorient_cancel", lambda: run("Sketcher_ReorientSketch", ["Sketch002"], click("Yes"), click("Cancel")))
safe("reattached", reattach)
safe("map_face", lambda: run("Sketcher_MapSketch", ["Pad"], pick_item("Sketch001"), click("OK"), sub="Face6"))
safe("map_detach", lambda: run("Sketcher_MapSketch", ["Pad"], pick_item("Sketch002"), pick_item("Do not attach"),
                               sub="Face2"))
safe("map_circular", lambda: run("Sketcher_MapSketch", ["Pad"], pick_item("Sketch"), sub="Face6"))
safe("map_self", lambda: run("Sketcher_MapSketch", ["Sketch001"], pick_item("Sketch002"), click("Cancel")))


def task_root():
    views = [w for w in mw.findChildren(QtWidgets.QWidget) if w.metaObject().className() == "Gui::TaskView::TaskView"]
    return next((v for v in views if v.isVisible()), None)


def press(name, *actions):
    del DIALOGS[:]
    rep0 = len(report_text())
    undo0 = list(doc.UndoNames)
    if actions:
        answer(*actions)
    btn = [b for b in task_root().findChildren(QtWidgets.QPushButton) if b.objectName() == name][0]
    btn.click()
    pump(1.5)
    s = doc.getObject("Sketch001") if VALIDATING[0] == "Sketch001" else doc.getObject(VALIDATING[0])
    return {"button": name, "dialogs": list(DIALOGS), "report": report_text()[rep0:].strip().splitlines(),
            "undo": doc.UndoNames[:len(doc.UndoNames) - len(undo0)],
            "panel": widgets(task_root()), "sketch": sketch_state(s)}


VALIDATING = ["Sketch001"]


def validate(name):
    VALIDATING[0] = name
    select(name)
    undo0 = len(doc.UndoNames)
    Gui.runCommand("Sketcher_ValidateSketch", 0)
    pump(1.5)
    out = {"panel": widgets(task_root()), "steps": []}
    for b in ("highlightButton", "findButton", "fixButton", "findConstraint", "findDegenerated", "fixDegenerated",
              "findReversed", "orientLockEnable", "orientLockDisable"):
        try:
            out["steps"].append(press(b))
        except Exception:
            out["steps"].append({"button": b, "error": traceback.format_exc()})
    try:
        out["steps"].append(press("delConstrExtr", click("Yes")))
    except Exception:
        out["steps"].append({"button": "delConstrExtr", "error": traceback.format_exc()})
    out["buttons"] = [b.text() for b in task_root().findChildren(QtWidgets.QPushButton) if b.isVisible()]
    for b in task_root().findChildren(QtWidgets.QAbstractButton):
        if b.isVisible() and b.text().replace("&", "") in ("Close", "OK", "Cancel"):
            out["closed_with"] = b.text()
            b.click()
            break
    pump(1.0)
    for _ in range(len(doc.UndoNames) - undo0):
        doc.undo()
    doc.recompute()
    pump(0.5)
    return out


safe("validate_sketch001", lambda: validate("Sketch001"))
safe("validate_sketch002", lambda: validate("Sketch002"))
json.dump(res, open(os.path.join(OUT, "fcsketchobj.json"), "w"), indent=1)
os._exit(0)

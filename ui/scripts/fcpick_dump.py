# Runs inside FreeCAD's GUI (fcpick.py starts it under fclaunch, windows kept off the screen): what the real PartDesign
# workbench does with a pick in the 3D view while a task panel asks for a reference, for pickcheck.mjs to compare the page
# with. A pick is Gui.Selection.addSelection(doc, object, sub-element), which goes through the selection gate a panel
# installs (ReferenceSelection, ...) as a click in the 3D view does; what the gate refuses is not selected and the panel
# does not change. Writes fcpick.json, one entry per case, each a list of steps:
#   {"step": what was done, "task": the panel's widgets (fcdressup_dump's task_widgets), "props": the feature's
#    properties that the step can change, "visible": which of the Body's objects are shown, "selected": the selection}
# Cases, each in a new document with a Body: a 40 x 20 x 5 Pad, Part datums (DatumPlane at z 12, DatumLine turned 30
# degrees about Y), an LCS at z 9, PartDesign's own datums (DatumPlane001 at z 11, DatumLine001), a circle sketch on the
# Pad's top (Sketch001), and the case's feature:
#   pad_face      Pad of Sketch001, Type Up to face: Select Face picks (an edge, Face6, the datum plane, XY_Plane, the
#                 LCS's plane, the datum line, PartDesign's plane), then OK
#   pad_shape     Type Up to shape: Select Shape (a face, the Pad whole), All faces off, Select Faces (Face6, Face1)
#   pad_direction Direction/edge: Select reference... (a face, an edge, the datum line, the LCS's Z axis), OK
#   revolution    a sketch on XZ, Revolution: Axis Select reference... (the datum plane, a face, the datum line, the
#                 LCS's Z axis, PartDesign's line), Type Up to face and Select Face (Face2)
#   mirrored      Mirrored of a Pocket: Plane Select reference... (an edge, the datum line, the datum plane, the LCS's
#                 YZ plane, a face of the Pocket), OK
#   linear        LinearPattern of the Pocket, a second Pocket after it: Direction Select reference... (a circle, the
#                 datum line, an edge, a face, the datum plane, PartDesign's plane); Add Feature and a pick on the base
#                 shown; Mode Spacing; the context menu on the pattern in the tree
#   linear_exp    with Mod/Part's ExperimentalFeatures on: Mode Spacing and the add-spacing button
#   polar         PolarPattern of the Pocket: Axis Select reference... (a face, the Pocket's circle, the datum line)
#   draft         Draft of Face1: Neutral Plane (XY_Plane, the datum plane, the LCS's plane), Pull Direction (the datum
#                 plane, Z_Axis, the datum line), OK
#   primitive     the Additive Primitive toolbar button: its action before and after the cylinder is made
#   datums        PartDesign_Plane, _Line, _Point, _CoordinateSystem: the command's texts, its panel, OK
#   delete        Std_Delete of the datum plane a sketch is attached to, of the sketch a Pad uses, of the Pad a Fillet
#                 uses: FreeCAD's question, answered Yes, and what is left
import json
import os
import time
import traceback

import FreeCAD as App
import FreeCADGui as Gui
import Part
import Sketcher
import pivy.coin as coin  # noqa: F401  (getSceneGraph hands out Coin nodes only once pivy is loaded)
from PySide6 import QtCore, QtGui, QtWidgets

OUT = os.environ["FCGUI_OUT"]
mw = Gui.getMainWindow()
app = QtWidgets.QApplication.instance()
res = {"errors": {}}
mw.resize(1280, 800)
V = App.Vector


def bail():
    res["errors"]["hung"] = "stopped after 900 s"
    json.dump(res, open(os.path.join(OUT, "fcpick.json"), "w"), indent=1)
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
    try:
        Gui.Control.closeDialog()
    except Exception:
        pass
    pump(0.5)


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
        d = {"text": a.text(), "name": a.objectName() or "", "enabled": a.isEnabled()}
        if a.menu() is not None and depth < 2:
            d["menu"] = dump_menu(a.menu(), depth + 1)
        out.append(d)
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
            if w.toolTip():
                d["tip"] = w.toolTip()
            if isinstance(w, QtWidgets.QLabel) and w.text():
                d["text"] = w.text()
            elif isinstance(w, QtWidgets.QAbstractButton):
                d["text"] = w.text()
                if w.isCheckable():
                    d["checked"] = w.isChecked()
            elif isinstance(w, QtWidgets.QComboBox):
                view = w.view()
                d["items"] = [w.itemText(i) for i in range(w.count()) if not view.isRowHidden(i)]
                d["current"] = w.currentText()
            elif isinstance(w, QtWidgets.QAbstractSpinBox):
                d["text"] = w.text()
            elif isinstance(w, QtWidgets.QLineEdit):
                d["text"] = w.text()
                d["placeholder"] = w.placeholderText()
            elif isinstance(w, QtWidgets.QListWidget):
                d["items"] = [w.item(i).text() for i in range(w.count())]
            elif cls.endswith("TaskBoxHeader") or cls.endswith("TaskHeader") or cls == "QSint::TaskHeader":
                d["text"] = " ".join(lbl.text() for lbl in w.findChildren(QtWidgets.QLabel) if lbl.text())
            else:
                continue
            items.append(d)
        items.sort(key=lambda d: (d["y"], d["x"]))
        for d in items:                     # the order is what the check reads; positions and tooltips are not
            for k in ("x", "y", "tip"):
                d.pop(k, None)
        out.append(items)
    return out


def widget(name):
    """The visible widget of the task view with this object name."""
    for w in mw.findChildren(QtWidgets.QWidget, name):
        if w.isVisible():
            return w
    for w in mw.findChildren(QtWidgets.QWidget, name):
        return w
    return None


def toggle(name):
    b = widget(name)
    b.click()
    pump(0.6)


def choose(name, text):
    """A combo's item by its text, as a user picks it (activated and currentIndexChanged both fire)."""
    cb = widget(name)
    i = cb.findText(text)
    if i < 0:
        raise ValueError(f"{name} has no {text!r}: {[cb.itemText(k) for k in range(cb.count())]}")
    cb.setCurrentIndex(i)
    cb.activated.emit(i)
    pump(0.8)


def click_button(text):
    for b in mw.findChildren(QtWidgets.QAbstractButton):
        if b.isVisible() and b.text().replace("&", "") == text:
            b.click()
            pump(0.8)
            return True
    return False


def link(v):
    """A PropertyLinkSub / LinkSubList value as names."""
    if v is None:
        return None
    if isinstance(v, tuple) and len(v) == 2 and hasattr(v[0], "Name"):
        return [v[0].Name, list(v[1])]
    if isinstance(v, list):
        return [link(x) for x in v]
    if hasattr(v, "Name"):
        return v.Name
    return str(v)


def body_visible():
    return {o.Name: bool(o.Visibility) for o in body.Group if hasattr(o, "Visibility")}


def selected():
    return [[s.ObjectName, list(s.SubElementNames)] for s in Gui.Selection.getSelectionEx()]


# ── the on-view spacing labels (PartGui::PatternParametersWidget's EditableDatumLabels) ────────────────────────────────
IDENTITY = [[1.0 if r == c else 0.0 for c in range(4)] for r in range(4)]


def mat_mul(a, b):
    return [[sum(a[r][k] * b[k][c] for k in range(4)) for c in range(4)] for r in range(4)]


def node_transform(n, m):
    """m times the node's own transform (Coin names them Transform, Translation, Rotation and Scale; FreeCAD's labels are
    placed by a Transform holding a Base::Placement)."""
    cls = str(n.getTypeId().getName())
    if cls not in ("Transform", "SoTransform", "Translation", "SoTranslation", "Rotation", "SoRotation", "Scale", "SoScale"):
        return m
    tr, q, sc = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0], [1.0, 1.0, 1.0]
    try:
        if cls in ("Transform", "SoTransform", "Translation", "SoTranslation"):
            tr = [float(x) for x in n.getField("translation").getValue()]
        if cls in ("Transform", "SoTransform", "Rotation", "SoRotation"):
            rot = n.getField("rotation").getValue()
            try:            # SbRotation is a 4-tuple to index (its getValue() returns None in this pivy)
                q = [float(rot[i]) for i in range(4)]
            except Exception:
                q = [float(x) for x in rot.getValue()]
        if cls in ("Transform", "SoTransform", "Scale", "SoScale"):
            sc = [float(x) for x in n.getField("scaleFactor").getValue()]
    except Exception:
        return m
    x, y, z, w = q
    r = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
         [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
         [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    t = [[r[i][0] * sc[0], r[i][1] * sc[1], r[i][2] * sc[2], tr[i]] for i in range(3)] + [[0.0, 0.0, 0.0, 1.0]]
    return mat_mul(m, t)


def datum_labels():
    """The spacing labels drawn now: each SoDatumLabel of the 3D view's scene graph that is switched on (EditableDatumLabel
    deactivate only sets its root SoSwitch to SO_SWITCH_NONE), with its text, its points in world coordinates, its angle
    params and its colour."""
    view = Gui.ActiveDocument.ActiveView if Gui.ActiveDocument else None
    if not view:
        return []
    out = []

    def walk(n, m):
        cls = str(n.getTypeId().getName())
        if cls in ("Switch", "SoSwitch"):
            try:
                if int(n.whichChild.getValue()) < 0:
                    return node_transform(n, m)      # off: none of its children, its own transform still applies
            except Exception:
                pass
        m2 = node_transform(n, m)
        if cls == "SoDatumLabel":
            try:
                pnts = [[float(x) for x in p] for p in n.pnts.getValues()]
                col = [float(x) for x in n.textColor.getValue()]
                d = {"text": [str(s) for s in n.string.getValues()],
                     "points": [[round(sum(m2[r][c] * p[c] for c in range(3)) + m2[r][3], 6) for r in range(3)] for p in pnts],
                     "color": [round(x, 4) for x in col], "type": int(n.datumtype.getValue()), "size": int(n.size.getValue())}
                for k in (1, 2, 3):
                    try:
                        d[f"param{k}"] = round(float(n.getField(f"param{k}").getValue()), 6)
                    except Exception:
                        pass
                out.append(d)
            except Exception:
                pass
        try:
            children = n.getChildren() or []
        except Exception:
            children = []
        run = m2                         # a Transform applies to the siblings after it, not to the next group
        for c in children:
            run = walk(c, run)
        return m2

    walk(view.getSceneGraph(), IDENTITY)
    return out


def snap(step, f, props=(), labels=False):
    pump(0.3)
    d = {"step": step, "task": task_widgets(), "props": {p: link(getattr(f, p)) for p in props if hasattr(f, p)},
         "visible": body_visible(), "selected": selected()}
    if labels:
        d["labels"] = datum_labels()
    return d


def pick(obj, sub=""):
    Gui.Selection.addSelection(doc.Name, obj, sub)
    pump(0.8)


def setup(extra=None):
    global doc, body
    doc = App.newDocument("Unnamed")
    pump(0.5)
    Gui.runCommand("PartDesign_Body", 0)
    pump(1.0)
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
    dp = body.newObject("Part::DatumPlane", "DatumPlane")
    dp.MapMode = "Deactivated"
    dp.Placement = App.Placement(V(0, 0, 12), App.Rotation())
    dl = body.newObject("Part::DatumLine", "DatumLine")
    dl.MapMode = "Deactivated"
    dl.Placement = App.Placement(V(0, 0, 0), App.Rotation(0, 30, 0))
    lcs = body.newObject("Part::LocalCoordinateSystem", "LCS")
    lcs.MapMode = "Deactivated"
    lcs.Placement = App.Placement(V(0, 0, 9), App.Rotation())
    pdp = body.newObject("PartDesign::Plane", "DatumPlane001")
    pdp.MapMode = "Deactivated"
    pdp.Placement = App.Placement(V(0, 0, 11), App.Rotation())
    pdl = body.newObject("PartDesign::Line", "DatumLine001")
    pdl.MapMode = "Deactivated"
    pdl.Placement = App.Placement(V(0, 0, 0), App.Rotation(0, 20, 0))
    if extra:
        extra()
    doc.recompute()
    pump(1.0)
    return {o.Name: o.TypeId for o in body.Group}


def lcs_feature(role):
    return next(o.Name for o in doc.getObject("LCS").OriginFeatures if o.Role == role)


def top_sketch(name="Sketch001", x=10.0, y=10.0, r=3.0):
    sk = body.newObject("Sketcher::SketchObject", name)
    sk.AttachmentSupport = [(doc.getObject("XY_Plane"), "")]
    sk.MapMode = "FlatFace"
    sk.AttachmentOffset = App.Placement(V(0, 0, 5), App.Rotation())
    sk.addGeometry(Part.Circle(V(x, y, 0), V(0, 0, 1), r), False)
    return sk


def run(command, *select):
    Gui.Selection.clearSelection()
    for s in select:
        if isinstance(s, tuple):
            Gui.Selection.addSelection(doc.Name, *s)
        else:
            Gui.Selection.addSelection(doc.getObject(s))
    pump(0.4)
    Gui.runCommand(command, 0)
    pump(2.0)
    e = Gui.ActiveDocument.getInEdit()
    return e.Object if e else None


def finish(f, props):
    out = {"ok": click_button("OK")}
    pump(1.5)
    out["props"] = {p: link(getattr(f, p)) for p in props if hasattr(f, p)}
    out["valid"] = f.isValid()
    out["status"] = f.getStatusString()
    out["volume"] = round(body.Shape.Volume, 6)
    out["undo"] = doc.UndoNames[:2]
    App.closeDocument(doc.Name)
    pump(0.5)
    return out


pump(1.5)
Gui.activateWorkbench("PartDesignWorkbench")
pump(1.0)


def pad_face():
    out = {"setup": setup(lambda: top_sketch())}
    f = run("PartDesign_Pad", "Sketch001")
    P = ("Type", "UpToFace", "Offset")
    out["open"] = snap("open", f, P)
    choose("changeMode", "Up to face")
    out["steps"] = [snap("type up to face", f, P)]
    for obj, sub in (("Pad", "Edge1"), ("Pad", "Face6"), ("DatumPlane", ""), ("XY_Plane", ""), (lcs_feature("XY_Plane"), ""),
                     ("DatumLine", ""), ("DatumPlane001", "")):
        if not widget("buttonFace").isChecked():
            toggle("buttonFace")
            out["steps"].append(snap("Select Face", f, P))
        pick(obj, sub)
        out["steps"].append(snap(f"pick {obj} {sub}".strip(), f, P))
        Gui.Selection.clearSelection()
    out["finish"] = finish(f, P)
    return out


def pad_shape():
    out = {"setup": setup(lambda: top_sketch())}
    f = run("PartDesign_Pad", "Sketch001")
    P = ("Type", "UpToShape")
    choose("changeMode", "Up to shape")
    out["steps"] = [snap("type up to shape", f, P)]
    toggle("buttonShape")
    out["steps"].append(snap("Select Shape", f, P))
    pick("Pad", "Face6")
    out["steps"].append(snap("pick Pad Face6", f, P))
    Gui.Selection.clearSelection()
    if not widget("buttonShape").isChecked():
        toggle("buttonShape")
    pick("Pad")
    out["steps"].append(snap("pick Pad", f, P))
    Gui.Selection.clearSelection()
    widget("checkBoxAllFaces").click()
    pump(0.6)
    out["steps"].append(snap("All faces off", f, P))
    if not widget("buttonShapeFace").isChecked():
        toggle("buttonShapeFace")
        out["steps"].append(snap("Select Faces", f, P))
    for sub in ("Face6", "Face1"):
        pick("Pad", sub)
        out["steps"].append(snap(f"pick Pad {sub}", f, P))
        Gui.Selection.clearSelection()
    out["finish"] = finish(f, P)
    return out


def pad_direction():
    out = {"setup": setup(lambda: top_sketch())}
    f = run("PartDesign_Pad", "Sketch001")
    P = ("ReferenceAxis", "UseCustomVector", "Direction", "AlongSketchNormal")
    out["steps"] = [snap("open", f, P)]
    for obj, sub in (("Pad", "Face1"), ("Pad", "Edge9"), ("DatumLine", ""), (lcs_feature("Z_Axis"), ""), ("DatumLine001", "")):
        if widget("directionCB").currentText() != "Select reference…":
            choose("directionCB", "Select reference…")
            out["steps"].append(snap("Select reference…", f, P))
        pick(obj, sub)
        out["steps"].append(snap(f"pick {obj} {sub}".strip(), f, P))
        Gui.Selection.clearSelection()
    out["finish"] = finish(f, P)
    return out


def revolution():
    def extra():
        sk = body.newObject("Sketcher::SketchObject", "Sketch001")
        sk.AttachmentSupport = [(doc.getObject("XZ_Plane"), "")]
        sk.MapMode = "FlatFace"
        pts = [V(45, 0, 0), V(50, 0, 0), V(50, 8, 0), V(45, 8, 0)]
        for i in range(4):
            sk.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 4]), False)
        dl2 = body.newObject("Part::DatumLine", "DatumLine002")
        dl2.MapMode = "Deactivated"
        dl2.Placement = App.Placement(V(42, 0, 0), App.Rotation())
    out = {"setup": setup(extra)}
    f = run("PartDesign_Revolution", "Sketch001")
    P = ("ReferenceAxis", "Type", "UpToFace")
    out["steps"] = [snap("open", f, P)]
    for obj, sub in (("DatumPlane", ""), ("Pad", "Face1"), ("DatumLine002", ""), (lcs_feature("Z_Axis"), ""), ("DatumLine001", ""),
                     ("Pad", "Edge9")):
        if widget("axis").currentText() != "Select reference…":
            choose("axis", "Select reference…")
            out["steps"].append(snap("Select reference…", f, P))
        pick(obj, sub)
        out["steps"].append(snap(f"pick {obj} {sub}".strip(), f, P))
        Gui.Selection.clearSelection()
    choose("changeMode", "Up to face")
    out["steps"].append(snap("type up to face", f, P))
    if not widget("buttonFace").isChecked():
        toggle("buttonFace")
        out["steps"].append(snap("Select Face", f, P))
    pick("Pad", "Face2")
    out["steps"].append(snap("pick Pad Face2", f, P))
    App.closeDocument(doc.Name)
    return out


def with_pocket(second=False):
    def extra():
        top_sketch("Sketch001", 8, 10, 3)
        pocket = body.newObject("PartDesign::Pocket", "Pocket")
        pocket.Profile = doc.getObject("Sketch001")
        pocket.Length = 5
        if second:
            top_sketch("Sketch002", 30, 10, 2)
            p2 = body.newObject("PartDesign::Pocket", "Pocket001")
            p2.Profile = doc.getObject("Sketch002")
            p2.Length = 5
    return setup(extra)


def mirrored():
    out = {"setup": with_pocket()}
    f = run("PartDesign_Mirrored", "Pocket")
    P = ("MirrorPlane",)
    out["steps"] = [snap("open", f, P)]
    for obj, sub in (("Pocket", "Edge1"), ("DatumLine", ""), ("DatumPlane", ""), (lcs_feature("YZ_Plane"), ""), ("Pocket", "Face4"),
                     ("DatumPlane001", "")):
        if widget("comboPlane").currentText() != "Select reference…":
            choose("comboPlane", "Select reference…")
            out["steps"].append(snap("Select reference…", f, P))
        pick(obj, sub)
        out["steps"].append(snap(f"pick {obj} {sub}".strip(), f, P))
        Gui.Selection.clearSelection()
    out["finish"] = finish(f, P)
    return out


def tree_context_menu(name):
    tree = [t for t in mw.findChildren(QtWidgets.QTreeWidget) if t.metaObject().className() == "Gui::TreeWidget"][0]
    tree.expandAll()
    pump(0.3)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.getObject(name))
    pump(0.5)
    item = next((it for it in tree.selectedItems()), None)
    holder = {}

    def grab():
        menus = [w for w in app.topLevelWidgets() if isinstance(w, QtWidgets.QMenu) and w.isVisible() and w.actions()]
        if menus:
            holder["menu"] = dump_menu(menus[0])
            menus[0].close()
            timer.stop()
    timer = QtCore.QTimer()
    timer.timeout.connect(grab)
    timer.start(150)
    rect = tree.visualItemRect(item) if item is not None else QtCore.QRect(10, 10, 10, 10)
    pos = rect.center()
    app.sendEvent(tree.viewport(), QtGui.QContextMenuEvent(QtGui.QContextMenuEvent.Mouse, pos, tree.viewport().mapToGlobal(pos)))
    pump(1.0)
    timer.stop()
    return holder.get("menu")


def linear():
    out = {"setup": with_pocket(second=True)}
    f = run("PartDesign_LinearPattern", "Pocket")
    P = ("Direction", "Originals", "Mode", "Spacings", "SpacingPattern")
    out["steps"] = [snap("open", f, P)]
    for obj, sub in (("Pocket001", "Edge7"), ("DatumLine", ""), ("Pocket001", "Edge1"), ("Pocket001", "Face1"), ("DatumPlane", ""),
                     ("DatumPlane001", ""), ("DatumLine001", "")):
        if widget("comboDirection").currentText() != "Select reference…":
            choose("comboDirection", "Select reference…")
            out["steps"].append(snap("Select reference…", f, P))
        pick(obj, sub)
        out["steps"].append(snap(f"pick {obj} {sub}".strip(), f, P))
        Gui.Selection.clearSelection()
    toggle("buttonAddFeature")
    out["steps"].append(snap("Add Feature", f, P))
    pick("Pocket001", "Face3")
    out["steps"].append(snap("pick Pocket001 Face3", f, P))
    Gui.Selection.clearSelection()
    if widget("buttonAddFeature").isChecked():
        toggle("buttonAddFeature")
    toggle("buttonRemoveFeature")
    out["steps"].append(snap("Remove Feature", f, P))
    pick("Pocket001", "Face3")
    out["steps"].append(snap("pick Pocket001 Face3 (remove)", f, P))
    Gui.Selection.clearSelection()
    if widget("buttonRemoveFeature").isChecked():
        toggle("buttonRemoveFeature")
    choose("comboMode", "Spacing")
    out["steps"].append(snap("Mode Spacing", f, P))
    out["finish"] = {"ok": click_button("OK")}
    pump(1.5)
    out["finish"]["props"] = {p: link(getattr(f, p)) for p in P}
    out["context_menu"] = tree_context_menu(f.Name)
    out["context_menu_pad"] = tree_context_menu("Pad")
    App.closeDocument(doc.Name)
    return out


def linear_exp():
    hp = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Part")
    was = hp.GetBool("ExperimentalFeatures", False)
    hp.SetBool("ExperimentalFeatures", True)
    try:
        out = {"setup": with_pocket()}
        f = run("PartDesign_LinearPattern", "Pocket")
        P = ("Mode", "Offset", "Occurrences", "Spacings", "SpacingPattern")
        out["steps"] = [snap("open", f, P)]
        choose("comboMode", "Spacing")
        out["steps"].append(snap("Mode Spacing", f, P))
        f.Occurrences = 4                   # (the UIntSpinBox's setValue from Python lands at its maximum)
        doc.recompute()
        pump(0.6)
        out["steps"].append(snap("Occurrences 4", f, P))
        toggle("addSpacingButton")
        out["steps"].append(snap("add spacing", f, P))
        toggle("addSpacingButton")
        out["steps"].append(snap("add spacing again", f, P))
        out["finish"] = finish(f, P)
        return out
    finally:
        hp.SetBool("ExperimentalFeatures", was)


def polar():
    out = {"setup": with_pocket()}
    f = run("PartDesign_PolarPattern", "Pocket")
    P = ("Axis",)
    out["steps"] = [snap("open", f, P)]
    for obj, sub in (("Pocket", "Face1"), ("Pocket", "Edge7"), ("DatumLine", ""), ("DatumPlane", ""), ("DatumLine001", "")):
        if widget("comboDirection").currentText() != "Select reference…":
            choose("comboDirection", "Select reference…")
            out["steps"].append(snap("Select reference…", f, P))
        pick(obj, sub)
        out["steps"].append(snap(f"pick {obj} {sub}".strip(), f, P))
        Gui.Selection.clearSelection()
    out["finish"] = finish(f, P)
    return out


def polar_spacing_labels():
    out = {"setup": with_pocket()}
    f = run("PartDesign_PolarPattern", "Pocket")
    P = ("Axis", "Mode", "Angle", "Offset", "Occurrences", "Spacings")
    out["open"] = snap("open", f, P, labels=True)
    out["steps"] = []
    f.Occurrences = 4                       # (the UIntSpinBox's setValue from Python lands at its maximum)
    doc.recompute()
    pump(0.6)
    out["steps"].append(snap("Occurrences 4", f, P, labels=True))
    choose("comboMode", "Angular Spacing")
    out["steps"].append(snap("Angular Spacing", f, P, labels=True))
    f.Spacings = [30.0, -1.0, -1.0]
    doc.recompute()
    pump(0.5)
    # the label refresh a widget change makes (updatePatternSpacingLabels), with the override now in the property
    choose("comboMode", "Total Angle")
    choose("comboMode", "Angular Spacing")
    out["steps"].append(snap("Spacings 30", f, P, labels=True))
    out["finish"] = finish(f, P)
    return out


def spacing():
    """PatternParametersWidget's on-view spacing labels: Extent one, Spacing occurrences - 1, the deactivated colour for
    -1 (the global offset), an override's own colour, and the linear and polar geometries."""
    out = {}
    out["setup"] = with_pocket(second=True)
    f = run("PartDesign_LinearPattern", "Pocket001")
    P = ("Originals", "Direction", "Mode", "Length", "Offset", "Occurrences", "Spacings")
    out["open"] = snap("open", f, P, labels=True)
    out["steps"] = []
    f.Occurrences = 4
    doc.recompute()
    pump(0.6)
    out["steps"].append(snap("Occurrences 4", f, P, labels=True))
    choose("comboMode", "Spacing")
    out["steps"].append(snap("Mode Spacing", f, P, labels=True))
    f.Spacings = [20.0, -1.0, -1.0]
    doc.recompute()
    pump(0.5)
    choose("comboMode", "Extent")
    choose("comboMode", "Spacing")
    out["steps"].append(snap("Spacings 20", f, P, labels=True))
    out["linear_finish"] = finish(f, P)
    out["polar"] = polar_spacing_labels()
    return out


def draft():
    out = {"setup": setup()}
    f = run("PartDesign_Draft", ("Pad", "Face1"))
    P = ("NeutralPlane", "PullDirection", "Base")
    out["steps"] = [snap("open", f, P)]
    if widget("buttonRefSel") is not None and widget("buttonRefSel").isChecked():
        toggle("buttonRefSel")
        out["steps"].append(snap("Preview", f, P))
    for button, obj, sub in (("buttonPlane", "XY_Plane", ""), ("buttonPlane", "DatumLine", ""), ("buttonPlane", "DatumPlane", ""),
                             ("buttonPlane", lcs_feature("XY_Plane"), ""), ("buttonPlane", "DatumPlane001", ""),
                             ("buttonLine", "DatumPlane", ""), ("buttonLine", "Z_Axis", ""), ("buttonLine", "DatumLine", ""),
                             ("buttonLine", "DatumLine001", ""), ("buttonLine", "Pad", "Edge9")):
        if not widget(button).isChecked():
            toggle(button)
            out["steps"].append(snap(button, f, P))
        pick(obj, sub)
        out["steps"].append(snap(f"{button} pick {obj} {sub}".strip(), f, P))
        Gui.Selection.clearSelection()
    out["finish"] = finish(f, P)
    return out


def primitive():
    setup()
    bars = [t for t in mw.findChildren(QtWidgets.QToolBar) if t.isVisible()]
    out = {}

    def buttons():
        got = {}
        for t in bars:
            for b in t.findChildren(QtWidgets.QToolButton):
                a = b.defaultAction()
                if a is not None and a.objectName() in ("PartDesign_CompPrimitiveAdditive", "PartDesign_CompPrimitiveSubtractive"):
                    m = b.menu() or a.menu()
                    got[a.objectName()] = {"text": a.text(), "tooltip": a.toolTip(), "popup": str(b.popupMode()).split(".")[-1],
                                           "menu": [x.text() for x in m.actions()] if m else None,
                                           "icon": a.icon().cacheKey(),
                                           "icons": [x.icon().cacheKey() for x in m.actions()] if m else None}
        return got
    out["before"] = buttons()
    Gui.runCommand("PartDesign_CompPrimitiveAdditive", 1)
    pump(2.0)
    out["task"] = task_widgets()
    click_button("OK")
    pump(1.5)
    out["after"] = buttons()
    Gui.runCommand("PartDesign_CompPrimitiveSubtractive", 3)
    pump(2.0)
    click_button("Cancel")
    pump(1.0)
    out["after_sub_cancel"] = buttons()
    App.closeDocument(doc.Name)
    return out


def datums():
    out = {}
    for c in ("PartDesign_Plane", "PartDesign_Line", "PartDesign_Point", "PartDesign_CoordinateSystem"):
        cmd = Gui.Command.get(c)
        out[c] = {"info": cmd.getInfo() if cmd else None}
    for c, sel in (("PartDesign_Plane", None), ("PartDesign_Line", ("Pad", "Edge9")), ("PartDesign_Point", ("Pad", "Vertex1")),
                   ("PartDesign_CoordinateSystem", None), ("PartDesign_Plane", ("Pad", "Face6"))):
        setup()
        before = {o.Name for o in doc.Objects}
        f = run(c, *([sel] if sel else []))
        d = {"in_edit": f.Name if f else None, "type": f.TypeId if f else None, "task": task_widgets(),
             "new": sorted({o.Name for o in doc.Objects} - before)}
        if f is not None:
            d["props"] = {p: link(getattr(f, p)) for p in ("AttachmentSupport", "MapMode", "Label") if hasattr(f, p)}
        d["ok"] = click_button("OK")
        pump(1.2)
        d["undo"] = doc.UndoNames[:2]
        if f is not None:
            d["after"] = {p: link(getattr(f, p)) for p in ("AttachmentSupport", "MapMode") if hasattr(f, p)}
            d["placement"] = str(f.Placement)
        out[f"{c}{'_' + sel[1] if sel else ''}"] = d
        App.closeDocument(doc.Name)
        pump(0.5)
    return out


def ask_yes():
    holder = {}

    def grab():
        for w in app.topLevelWidgets():
            if isinstance(w, QtWidgets.QMessageBox) and w.isVisible():
                holder.setdefault("boxes", []).append({"title": w.windowTitle(), "text": w.text(), "informative": w.informativeText(),
                                                       "buttons": [b.text() for b in w.buttons()]})
                yes = w.button(QtWidgets.QMessageBox.Yes) or w.button(QtWidgets.QMessageBox.Ok)
                (yes or w.buttons()[0]).click()
                return
    timer = QtCore.QTimer()
    timer.timeout.connect(grab)
    timer.start(150)
    return holder, timer


def delete():
    out = {}

    def extra():
        sk = body.newObject("Sketcher::SketchObject", "Sketch001")
        sk.AttachmentSupport = [(doc.getObject("DatumPlane"), "")]
        sk.MapMode = "FlatFace"
        sk.addGeometry(Part.Circle(V(10, 10, 0), V(0, 0, 1), 3), False)
        p = body.newObject("PartDesign::Pad", "Pad001")
        p.Profile = sk
        p.Length = 2
        fil = body.newObject("PartDesign::Fillet", "Fillet")
        fil.Base = (doc.getObject("Pad001"), ["Edge1"])
        fil.Radius = 0.5
    for victim in ("DatumPlane", "Sketch001", "Pad001", "Pad"):
        setup(extra)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.getObject(victim))
        pump(0.3)
        holder, timer = ask_yes()
        Gui.runCommand("Std_Delete", 0)
        pump(1.5)
        timer.stop()
        doc.recompute()
        pump(0.8)
        holder["left"] = [o.Name for o in body.Group]
        holder["tip"] = body.Tip.Name if body.Tip else None
        holder["objects"] = {o.Name: {"valid": o.isValid(), "status": o.getStatusString(),
                                      **{p: link(getattr(o, p)) for p in ("AttachmentSupport", "MapMode", "Profile", "Base", "BaseFeature")
                                         if hasattr(o, p)}} for o in body.Group}
        sk = doc.getObject("Sketch001")
        holder["sketch_placement"] = str(sk.Placement) if sk else None
        holder["undo"] = doc.UndoNames[:2]
        out[victim] = holder
        App.closeDocument(doc.Name)
        pump(0.5)
    return out


# A message box a command or OK opens (UnifiedDatumCommand's "Invalid Selection", TaskDlgDatumParameters' "Incompatible
# Reference Set", Std_Delete's question) is modal: a timer records it and answers Yes, so the script goes on.
BOXES = []


def answer_boxes():
    for w in app.topLevelWidgets():
        if isinstance(w, QtWidgets.QMessageBox) and w.isVisible() and not w.property("fcpick_seen"):
            w.setProperty("fcpick_seen", True)
            BOXES.append({"title": w.windowTitle(), "text": w.text(), "buttons": [b.text().replace("&", "") for b in w.buttons()]})
            yes = w.button(QtWidgets.QMessageBox.Yes) or w.button(QtWidgets.QMessageBox.Ok)
            (yes or w.buttons()[0]).click()


_boxes = QtCore.QTimer()
_boxes.timeout.connect(answer_boxes)
_boxes.start(200)
ONLY = [c for c in os.environ.get("FCPICK_ONLY", "").split(",") if c]
for _n, _f in (("pad_face", pad_face), ("pad_shape", pad_shape), ("pad_direction", pad_direction), ("revolution", revolution),
               ("mirrored", mirrored), ("linear", linear), ("linear_exp", linear_exp), ("polar", polar), ("spacing", spacing),
               ("draft", draft),
               ("primitive", primitive), ("datums", datums), ("delete", delete)):
    if ONLY and _n not in ONLY:
        continue
    BOXES.clear()
    safe(_n, _f)
    if _n in res and isinstance(res[_n], dict):
        res[_n]["message_boxes"] = list(BOXES)
    for d in list(App.listDocuments().values()):
        App.closeDocument(d.Name)
    pump(0.5)

json.dump(res, open(os.path.join(OUT, "fcpick.json"), "w"), indent=1)
os._exit(0)

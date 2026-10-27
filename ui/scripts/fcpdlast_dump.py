# Runs inside FreeCAD's GUI (fcpdlast.py starts it under fclaunch, windows kept off the screen): what the real PartDesign
# workbench shows for its last commands, for the comparison with the page's (pdlastcheck.mjs). Writes fcpdlast.json and the
# tree's icons into FCGUI_OUT. Each scenario starts from a Body holding a 40 x 20 x 5 Pad on a rectangle (made in code, as
# fcedit_dump.py's flow leaves it), then runs the command as a click on its button does:
#   gear       PartDesign_InvoluteGear: the task panel (its widgets and values), a change of the number of teeth, OK; the
#              undo step, the tree, the property view, the tree's context menu; setEdit again and OK; a Pad on it
#   sprocket   PartDesign_Sprocket: the panel, a change of Sprocket reference (the pitch, roller and width it sets), OK;
#              setEdit then Cancel (what is left)
#   defeat     PartDesign_Defeaturing on a hole's face: the panel, OK, the undo step, the property view; with an edge
#              selected (its warning); with nothing selected
#   binder     PartDesign_SubShapeBinder on the Pad's top face: the object, its Support, the undo step, the tree, the
#              property view, the tree's context menu, a double-click (Sync binder)
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
    json.dump(res, open(os.path.join(OUT, "fcpdlast.json"), "w"), indent=1, default=str)
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
        d = {"text": a.text(), "name": a.objectName() or a.data(), "shortcut": a.shortcut().toString(), "enabled": a.isEnabled()}
        sub = a.menu()
        if sub is not None and depth < 4:
            d["menu"] = dump_menu(sub, depth + 1)
        out.append(d)
    return out


def task_widgets():
    """The open task panel's widgets, top to bottom (fcedit_dump.py's)."""
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
                d["text"] = " ".join(lb.text() for lb in w.findChildren(QtWidgets.QLabel) if lb.text())
            else:
                continue
            items.append(d)
        items.sort(key=lambda d: (d["y"], d["x"]))
        out.append(items)
    return out


def widget(name):
    for w in mw.findChildren(QtWidgets.QWidget, name):
        if w.isVisible():
            return w
    return None


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
            ICONS[key] = f"pdlast-icon{len(ICONS)}.png"
            item.icon(0).pixmap(32, 32).save(os.path.join(OUT, ICONS[key]))
        rows.append({"text": item.text(0), "depth": depth, "bold": f.bold(), "icon": ICONS[key], "children": item.childCount(),
                     "fg": item.foreground(0).color().name() if item.foreground(0).style() else None})
        for i in range(item.childCount()):
            walk(item.child(i), depth + 1)

    for i in range(tree.topLevelItemCount()):
        walk(tree.topLevelItem(i), 0)
    return rows


def objects():
    return [{"name": o.Name, "label": o.Label, "type": o.TypeId, "visible": o.Visibility if hasattr(o, "Visibility") else None,
             "in_body": body is not None and o in body.Group} for o in doc.Objects]


def find_item(name):
    tree = tree_widget()
    return tree.findItems(doc.getObject(name).Label, QtCore.Qt.MatchExactly | QtCore.Qt.MatchRecursive, 0)[0]


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


def property_view(name):
    """The property view's Data tab for one selected object (fcedit_dump.py's)."""
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


def props(o):
    return {p: str(getattr(o, p)) for p in o.PropertiesList if p not in ("Shape", "Proxy", "ExpressionEngine")}


def shape(o):
    s = o.Shape
    if s.isNull():
        return None
    return {"type": s.ShapeType, "faces": len(s.Faces), "edges": len(s.Edges), "area": round(s.Area, 6),
            "length": round(s.Length, 6), "volume": round(s.Volume, 6) if s.Solids else 0}


def message_box(run):
    """Run something that may show a QMessageBox; its title, text and buttons, answered with its last button."""
    holder = {}

    def grab():
        for w in app.topLevelWidgets():
            if isinstance(w, QtWidgets.QMessageBox) and w.isVisible():
                holder.update(title=w.windowTitle(), text=w.text(), buttons=[b.text() for b in w.buttons()])
                w.buttons()[-1].click()
                timer.stop()
                return
    timer = QtCore.QTimer()
    timer.timeout.connect(grab)
    timer.start(150)
    run()
    pump(1.0)
    timer.stop()
    return holder or None


# ── the Body every scenario starts from ──────────────────────────────────────────────────────────────────────────────
pump(1.5)
Gui.activateWorkbench("PartDesignWorkbench")
pump(1.0)
doc = None
body = None


def fresh(name):
    """A new document with Body (active), Sketch (40 x 20 on XY) and Pad (5 mm)."""
    global doc, body
    for d in list(App.listDocuments()):
        App.closeDocument(d)
    pump(0.3)
    doc = App.newDocument(name)
    pump(0.3)
    Gui.runCommand("PartDesign_Body", 0)
    pump(0.6)
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
    sk.Visibility = False
    doc.recompute()
    doc.UndoMode = 1
    doc.clearUndos()
    pump(0.5)


def in_edit():
    e = Gui.ActiveDocument.getInEdit()
    return e.Object.Name if e else None


# ── Involute Gear ────────────────────────────────────────────────────────────────────────────────────────────────────
def gear():
    fresh("GearDoc")
    out = {}
    Gui.Selection.clearSelection()
    Gui.runCommand("PartDesign_InvoluteGear", 0)
    pump(1.5)
    out["in_edit"] = in_edit()
    out["task"] = task_widgets()
    g = doc.getObject("InvoluteGear")
    out["props_new"] = props(g)
    out["groups"] = {p: g.getGroupOfProperty(p) for p in g.PropertiesList}
    out["shape_new"] = shape(g)
    sp = widget("spinBox_NumberOfTeeth")
    sp.setValue(13)
    pump(0.5)
    out["teeth_live"] = g.NumberOfTeeth
    out["shape_13"] = shape(g)
    out["ok"] = click_button("OK")
    pump(1.0)
    out["after_ok"] = {"in_edit": in_edit(), "undo": doc.UndoNames, "tip": body.Tip.Name, "objects": objects(),
                       "props": props(g)}
    out["tree"] = tree_rows()
    out["props_view"] = property_view("InvoluteGear")
    out["menu"] = menu_at("InvoluteGear")
    Gui.ActiveDocument.setEdit(g, 0)
    pump(1.2)
    out["edit_task"] = task_widgets()
    widget("doubleSpinBox_Addendum").setValue(0.9)
    pump(0.4)
    out["edit_ok"] = click_button("OK")
    pump(1.0)
    out["after_edit"] = {"undo": doc.UndoNames, "addendum": g.AddendumCoefficient}
    Gui.ActiveDocument.setEdit(g, 0)
    pump(1.0)
    widget("doubleSpinBox_Dedendum").setValue(1.4)
    pump(0.4)
    click_button("Cancel")
    pump(1.0)
    out["after_cancel"] = {"undo": doc.UndoNames, "dedendum": g.DedendumCoefficient, "exists": doc.getObject("InvoluteGear") is not None}
    # Pad on the gear: selected, then PartDesign_Pad (the panel, OK)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(g)
    pump(0.3)
    Gui.runCommand("PartDesign_Pad", 0)
    pump(1.5)
    out["pad_in_edit"] = in_edit()
    out["pad_ok"] = click_button("OK")
    pump(1.0)
    out["after_pad"] = {"undo": doc.UndoNames, "tip": body.Tip.Name, "objects": objects(),
                        "pad001": shape(doc.getObject("Pad001")) if doc.getObject("Pad001") else None}
    out["tree_pad"] = tree_rows()
    return out


safe("gear", gear)


# ── Sprocket ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def sprocket():
    fresh("SprocketDoc")
    out = {}
    Gui.Selection.clearSelection()
    Gui.runCommand("PartDesign_Sprocket", 0)
    pump(1.5)
    out["in_edit"] = in_edit()
    out["task"] = task_widgets()
    s = doc.getObject("Sprocket")
    out["props_new"] = props(s)
    out["groups"] = {p: s.getGroupOfProperty(p) for p in s.PropertiesList}
    out["enum"] = s.getEnumerationsOfProperty("SprocketReference")
    combo = widget("comboBox_SprocketReference")
    combo.setCurrentIndex(3)
    pump(0.5)
    out["task_ansi40"] = task_widgets()
    out["props_ansi40"] = props(s)
    out["ok"] = click_button("OK")
    pump(1.0)
    out["after_ok"] = {"undo": doc.UndoNames, "tip": body.Tip.Name, "objects": objects(), "props": props(s), "shape": shape(s)}
    out["props_view"] = property_view("Sprocket")
    out["menu"] = menu_at("Sprocket")
    Gui.ActiveDocument.setEdit(s, 0)
    pump(1.2)
    out["edit_task"] = task_widgets()
    click_button("Cancel")
    pump(1.0)
    out["after_cancel"] = {"undo": doc.UndoNames, "exists": doc.getObject("Sprocket") is not None, "objects": objects()}
    return out


safe("sprocket", sprocket)


# ── Defeaturing ──────────────────────────────────────────────────────────────────────────────────────────────────────
def defeat():
    fresh("DefeatDoc")
    out = {}
    sk = body.newObject("Sketcher::SketchObject", "Sketch001")
    sk.AttachmentSupport = [(doc.getObject("XY_Plane"), "")]
    sk.MapMode = "FlatFace"
    sk.addGeometry(Part.Circle(V(20, 10, 0), V(0, 0, 1), 3), False)
    pocket = body.newObject("PartDesign::Pocket", "Pocket")
    pocket.Profile = sk
    pocket.Type = "ThroughAll"
    pocket.Reversed = True
    doc.recompute()
    doc.clearUndos()
    pump(0.5)
    out["pocket_faces"] = len(pocket.Shape.Faces)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.Name, "Pocket", "Face7")
    pump(0.3)
    Gui.runCommand("PartDesign_Defeaturing", 0)
    pump(1.5)
    out["in_edit"] = in_edit()
    out["task"] = task_widgets()
    d = doc.getObject("Defeaturing")
    out["props_new"] = props(d) if d else None
    out["groups"] = {p: d.getGroupOfProperty(p) for p in d.PropertiesList} if d else None
    out["ok"] = click_button("OK")
    pump(1.0)
    out["after_ok"] = {"undo": doc.UndoNames, "tip": body.Tip.Name, "objects": objects(), "shape": shape(d) if d else None,
                       "base": str(d.Base) if d else None}
    out["tree"] = tree_rows()
    out["props_view"] = property_view("Defeaturing")
    out["menu"] = menu_at("Defeaturing")
    # an edge selected: the command's warning
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.Name, "Defeaturing", "Edge1")
    pump(0.3)
    out["edge_selected"] = message_box(lambda: Gui.runCommand("PartDesign_Defeaturing", 0))
    out["after_edge"] = [o["name"] for o in objects()]
    # nothing selected: a Defeaturing on the Tip with no face, its panel, OK
    Gui.Selection.clearSelection()
    pump(0.3)
    Gui.runCommand("PartDesign_Defeaturing", 0)
    pump(1.5)
    out["empty_in_edit"] = in_edit()
    out["empty_task"] = task_widgets()
    click_button("OK")
    pump(1.0)
    d1 = doc.getObject("Defeaturing001")
    out["after_empty"] = {"undo": doc.UndoNames, "base": str(d1.Base) if d1 else None, "tip": body.Tip.Name,
                          "valid": d1.isValid() if d1 else None}
    return out


safe("defeat", defeat)


# ── Sub-Shape Binder ─────────────────────────────────────────────────────────────────────────────────────────────────
def binder():
    fresh("BinderDoc")
    out = {}
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.Name, "Body", "Pad.Face6")
    pump(0.3)
    Gui.runCommand("PartDesign_SubShapeBinder", 0)
    pump(1.5)
    b = doc.getObject("Binder")
    out["in_edit"] = in_edit()
    out["task"] = task_widgets()
    out["after"] = {"undo": doc.UndoNames, "tip": body.Tip.Name, "objects": objects(), "props": props(b), "shape": shape(b),
                    "support": [[lk[0].Name, list(lk[1])] for lk in b.Support]}
    out["groups"] = {p: b.getGroupOfProperty(p) for p in b.PropertiesList}
    out["modes"] = {p: b.getEditorMode(p) for p in b.PropertiesList}
    out["tree"] = tree_rows()
    out["props_view"] = property_view("Binder")
    out["menu"] = menu_at("Binder")
    item = find_item("Binder")
    tree = tree_widget()
    tree.scrollToItem(item)
    pump(0.2)
    rect = tree.visualItemRect(item)
    QtTest = __import__("PySide6.QtTest", fromlist=["QTest"])
    QtTest.QTest.mouseDClick(tree.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, rect.center())
    pump(1.0)
    out["after_double"] = {"undo": doc.UndoNames, "in_edit": in_edit()}
    # with nothing selected: an empty binder
    Gui.Selection.clearSelection()
    pump(0.3)
    Gui.runCommand("PartDesign_SubShapeBinder", 0)
    pump(1.0)
    b1 = doc.getObject("Binder001")
    out["empty"] = {"exists": b1 is not None, "support": str(b1.Support) if b1 else None, "null": b1.Shape.isNull() if b1 else None,
                    "undo": doc.UndoNames}
    # the Pad selected in the tree: the whole Pad
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.Name, "Body", "Pad.")
    pump(0.3)
    Gui.runCommand("PartDesign_SubShapeBinder", 0)
    pump(1.0)
    b2 = doc.getObject("Binder002")
    out["whole"] = {"support": [[lk[0].Name, list(lk[1])] for lk in b2.Support] if b2 else None, "shape": shape(b2) if b2 else None}
    return out


safe("binder", binder)


# ── Clone and Boolean: a second Body ─────────────────────────────────────────────────────────────────────────────────
def second_body(name="Body001", sketch="Sketch001", pad="Pad001"):
    """Another Body beside the first: a rod (a circle of 4 at (20, 10), 12 long from z = -3) through the plate."""
    b = doc.addObject("PartDesign::Body", name)
    sk = b.newObject("Sketcher::SketchObject", sketch)
    sk.AttachmentSupport = [(b.Origin.OriginFeatures[3], "")]       # its XY_Plane
    sk.MapMode = "FlatFace"
    sk.AttachmentOffset = App.Placement(V(0, 0, -3), App.Rotation())
    sk.addGeometry(Part.Circle(V(20, 10, 0), V(0, 0, 1), 4), False)
    p = b.newObject("PartDesign::Pad", pad)
    p.Profile = sk
    p.Length = 12
    sk.Visibility = False
    doc.recompute()
    return b


def visible():
    return {o.Name: o.Visibility for o in doc.Objects if o.TypeId in ("PartDesign::Body", "PartDesign::Boolean", "PartDesign::FeatureBase")}


def clone():
    fresh("CloneDoc")
    out = {}
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(body)
    pump(0.3)
    out["enabled"] = Gui.Command.get("PartDesign_Clone").isActive()
    Gui.runCommand("PartDesign_Clone", 0)
    pump(1.5)
    c = doc.getObject("Clone")
    b1 = doc.getObject("Body001")
    out["after"] = {"undo": doc.UndoNames, "in_edit": in_edit(), "objects": objects(), "visible": visible(),
                    "body001_group": [o.Name for o in b1.Group] if b1 else None, "tip": b1.Tip.Name if b1 and b1.Tip else None,
                    "base": c.BaseFeature.Name if c and c.BaseFeature else None, "shape": shape(c) if c else None,
                    "body001": shape(b1) if b1 else None,
                    "active": str(Gui.ActiveDocument.ActiveView.getActiveObject("pdbody"))}
    out["props"] = props(c) if c else None
    out["groups"] = {p: c.getGroupOfProperty(p) for p in c.PropertiesList} if c else None
    out["modes"] = {p: c.getEditorMode(p) for p in c.PropertiesList} if c else None
    out["tree"] = tree_rows()
    out["props_view"] = property_view("Clone")
    out["menu"] = menu_at("Clone")
    Gui.Selection.clearSelection()
    pump(0.3)
    out["enabled_nothing"] = Gui.Command.get("PartDesign_Clone").isActive()
    return out


safe("clone", clone)


def boolean():
    fresh("BooleanDoc")
    out = {}
    rod = second_body()
    doc.clearUndos()
    Gui.ActiveDocument.ActiveView.setActiveObject("pdbody", body)
    pump(0.3)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(rod)
    pump(0.3)
    Gui.runCommand("PartDesign_Boolean", 0)
    pump(1.5)
    bo = doc.getObject("Boolean")
    out["in_edit"] = in_edit()
    out["task"] = task_widgets()
    out["created"] = {"group": [o.Name for o in bo.Group] if bo else None, "type": bo.Type if bo else None,
                      "visible": visible(), "props": props(bo) if bo else None}
    out["groups"] = {p: bo.getGroupOfProperty(p) for p in bo.PropertiesList} if bo else None
    combo = widget("comboType")
    combo.setCurrentIndex(1)
    pump(1.0)
    out["cut_live"] = {"type": bo.Type, "shape": shape(bo)}
    out["ok"] = click_button("OK")
    pump(1.2)
    out["after_ok"] = {"undo": doc.UndoNames, "in_edit": in_edit(), "tip": body.Tip.Name, "visible": visible(),
                       "objects": objects(), "shape": shape(bo), "body": shape(body), "group": [o.Name for o in bo.Group]}
    out["tree"] = tree_rows()
    out["props_view"] = property_view("Boolean")
    out["menu"] = menu_at("Boolean")
    Gui.ActiveDocument.setEdit(bo, 0)
    pump(1.2)
    out["edit_task"] = task_widgets()
    click_button("Cancel")
    pump(1.0)
    out["after_cancel"] = {"undo": doc.UndoNames, "visible": visible()}
    # nothing selected: an empty Boolean, its panel; OK asks for a body
    Gui.Selection.clearSelection()
    pump(0.3)
    Gui.runCommand("PartDesign_Boolean", 0)
    pump(1.5)
    out["empty_in_edit"] = in_edit()
    out["empty_task"] = task_widgets()
    out["empty_ok"] = message_box(lambda: click_button("OK"))
    out["empty_still_in_edit"] = in_edit()
    click_button("Cancel")
    pump(1.0)
    out["after_empty_cancel"] = {"undo": doc.UndoNames, "objects": [o.Name for o in doc.Objects]}
    return out


safe("boolean", boolean)

json.dump(res, open(os.path.join(OUT, "fcpdlast.json"), "w"), indent=1, default=str)
os._exit(0)

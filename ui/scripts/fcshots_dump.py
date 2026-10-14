# Runs inside FreeCAD's GUI (fcshots.py starts it on the cocoa platform, windows kept off the screen): the
# screenshots our UI is compared with, all of the main window at 1280 x 800 as a real Mac shows it. Writes
# freecad-<thing>.png into FCGUI_OUT, and fcshots.json (what was measured). FCSHOTS_ONLY=a,b limits the shots.
#
# The stand-in document is the arduino_car sample's ten bodies as plain Part boxes, cylinders and a sphere, by
# name and bounding box (scene.json's, passed in FCSHOTS_BODIES): the chrome is what is compared, not the geometry.
import json
import os
import time
import traceback

import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtCore, QtGui, QtOpenGLWidgets, QtWidgets

OUT = os.environ["FCGUI_OUT"]
ONLY = set(filter(None, os.environ.get("FCSHOTS_ONLY", "").split(",")))
W, H = 1280, 800
mw = Gui.getMainWindow()
app = QtWidgets.QApplication.instance()
res = {"errors": {}}
DPR = mw.devicePixelRatioF()


LAST = [time.time(), "start"]
LOG = open(os.path.join(OUT, "fcshots.log"), "w")


def progress(what):
    LAST[0], LAST[1] = time.time(), what
    LOG.write("%.1f %s\n" % (time.time() - T0, what))
    LOG.flush()


T0 = time.time()


def watchdog():
    """A step that blocks (a modal dialog or a menu that never closes) ends the run with what was done so far."""
    if time.time() - LAST[0] > float(os.environ.get("FCSHOTS_STEP_TIMEOUT", "40")):
        res["errors"]["hung"] = "no progress for 40 s in step %r; windows: %s" % (
            LAST[1], [[w.metaObject().className(), w.isVisible()] for w in app.topLevelWidgets() if w.isVisible()])
        json.dump(res, open(os.path.join(OUT, "fcshots.json"), "w"), indent=1)
        os._exit(0)


_wd = QtCore.QTimer()
_wd.timeout.connect(watchdog)
_wd.start(1000)


def pump(sec=0.3):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents(QtCore.QEventLoop.AllEvents, 50)
        time.sleep(0.005)


def want(name):
    return not ONLY or name in ONLY


def save(img, name):
    path = os.path.join(OUT, "freecad-%s.png" % name)
    img.save(path)
    return path


def shot(name, widget=None):
    """Grab the main window (or a widget) after letting it settle."""
    pump(0.4)
    return save((widget or mw).grab(), name)


def step(name):
    """Run one shot's function; a failure is written down and the next shot goes on."""
    def deco(fn):
        if want(name):
            progress(name)
            try:
                fn()
            except Exception:
                res["errors"][name] = traceback.format_exc()
        return fn
    return deco


def find(cls, name=None, root=None):
    for w in (root or mw).findChildren(cls):
        if name is None or w.metaObject().className() == name or w.objectName() == name:
            return w
    return None


def widget3d():
    for w in mw.findChildren(QtOpenGLWidgets.QOpenGLWidget):
        if w.width() > 300:
            return w
    return None


# ── the window ──────────────────────────────────────────────────────────────────
mw.resize(W, H)
pump(1.0)
res["dpr"] = DPR
res["window"] = [mw.width(), mw.height()]


# ── 1. Start page, as a new user sees it, then with the first-start setup done ──
@step("start")
def _():
    pump(2.5)
    shot("start")
    for b in mw.findChildren(QtWidgets.QPushButton):
        res.setdefault("start_buttons", []).append([b.text(), b.isVisible()])
    done = [b for b in mw.findChildren(QtWidgets.QPushButton) if b.text().replace("&", "") in ("Done", "Finish", "OK")]
    if done:
        done[0].click()
        pump(1.5)
        shot("start-cards")


# ── 2. a document with the sample's bodies ──────────────────────────────────────
bodies = json.load(open(os.environ["FCSHOTS_BODIES"])) if os.environ.get("FCSHOTS_BODIES") else []
doc = App.newDocument("arduino_car")
for b in bodies:
    (x0, y0, z0), (x1, y1, z1) = b["bbox"]
    n = b["name"]
    if n.startswith("wheel"):
        o = doc.addObject("Part::Cylinder", n)
        o.Radius, o.Height = (x1 - x0) / 2, y1 - y0
        o.Placement = App.Placement(App.Vector((x0 + x1) / 2, y0, (z0 + z1) / 2), App.Rotation(App.Vector(1, 0, 0), -90))
    elif n == "caster_ball":
        o = doc.addObject("Part::Sphere", n)
        o.Radius = (x1 - x0) / 2
        o.Placement = App.Placement(App.Vector((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), App.Rotation())
    else:
        o = doc.addObject("Part::Box", n)
        o.Length, o.Width, o.Height = x1 - x0, y1 - y0, z1 - z0
        o.Placement = App.Placement(App.Vector(x0, y0, z0), App.Rotation())
if not bodies:
    doc.addObject("Part::Box", "chassis")
doc.recompute()
pump(1.0)
view = Gui.ActiveDocument.ActiveView
view.viewDefaultOrientation()
view.fitAll()
pump(1.0)


Gui.Selection.clearSelection()
Gui.Selection.addSelection(doc.Name, "chassis")
pump(1.2)
res["selection"] = [s.Name for s in Gui.Selection.getSelection()]


@step("part")
def _():
    shot("part")


@step("navicube")
def _():
    # the cube and its buttons, cropped from the same grab (a second run at devicePixelRatio 3 for a close-up)
    img = mw.grab()
    w3 = widget3d()
    p = w3.mapTo(mw, QtCore.QPoint(0, 0))
    res["view3d"] = [p.x(), p.y(), w3.width(), w3.height()]
    s = int(150 * DPR)
    x = int((p.x() + w3.width()) * DPR) - s
    y = int(p.y() * DPR)
    save(img.copy(x, y, s, s), "navicube")


# ── 3. the tree's context menu on a part ─────────────────────────────────────────
@step("treemenu")
def _():
    tree = [t for t in mw.findChildren(QtWidgets.QTreeWidget) if t.metaObject().className() == "Gui::TreeWidget"][0]
    doc_item = tree.topLevelItem(0)
    item = None
    for i in range(doc_item.childCount()):
        if doc_item.child(i).text(0) == "chassis":
            item = doc_item.child(i)
    rect = tree.visualItemRect(item)
    pos = rect.center()
    holder = {"polls": 0}

    def grab_menu():
        # Gui::TreeWidget::contextMenuEvent runs a top-level QMenu with exec(): this runs inside its event loop
        holder["polls"] += 1
        menus = [w for w in app.topLevelWidgets() if isinstance(w, QtWidgets.QMenu) and w.isVisible() and w.actions()]
        if not menus:
            if holder["polls"] > 40:        # 6 s: nothing opened, let the event go
                holder["tops"] = [[w.metaObject().className(), w.isVisible()] for w in app.topLevelWidgets()][:30]
                holder["timer"].stop()
                QtWidgets.QApplication.sendEvent(tree, QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_Escape, QtCore.Qt.NoModifier))
            return
        holder["timer"].stop()
        holder["menus"] = [[w.metaObject().className(), w.objectName(), len(w.actions()), w.width(), w.height(), w.x(), w.y()] for w in menus]
        m = max(menus, key=lambda w: len(w.actions()))
        # Qt put it at QCursor::pos(), the real pointer, which nothing here moves: near the bottom of the screen a tall menu
        # scrolls to fit. Pop it up again at a corner of the (large) virtual screen, where it has all its height.
        m.popup(QtCore.QPoint(100, 100))
        pump(0.3)
        holder["img"] = m.grab()
        holder["size"] = [m.width(), m.height()]
        holder["actions"] = [[a.text(), a.shortcut().toString(), a.isEnabled(), a.isSeparator()] for a in m.actions()]
        m.close()

    holder["timer"] = QtCore.QTimer()
    holder["timer"].timeout.connect(grab_menu)
    holder["timer"].start(150)
    ev = QtGui.QContextMenuEvent(QtGui.QContextMenuEvent.Mouse, pos, tree.viewport().mapToGlobal(pos))
    app.sendEvent(tree.viewport(), ev)
    holder["timer"].stop()
    pump(0.5)
    res["treemenu"] = {k: v for k, v in holder.items() if k not in ("img", "timer")}
    if "img" in holder:
        # as Qt places a popup: its corner at the click, moved up and left to stay inside what is shown
        save(holder["img"], "treemenu-popup")
        base = mw.grab()
        top = tree.viewport().mapTo(mw, pos)
        x = min(int(top.x() * DPR), base.width() - holder["img"].width())
        y = min(int(top.y() * DPR), base.height() - holder["img"].height())
        pnt = QtGui.QPainter(base)
        pnt.drawPixmap(x, max(0, y), holder["img"])
        pnt.end()
        save(base, "treemenu")


# ── 4. the Preferences dialog's main pages (a modal dialog: the pages are chosen from a timer in its event loop) ──
PAGES = [("General", "General", "general"), ("Display", "3D View", "3dview"), ("Display", "Navigation", "navigation"),
         ("Display", "Colors", "colors"), ("General", "Report View", "reportview")]


@step("prefs")
def _():
    res["prefs"] = {}
    holder = {"polls": 0}

    def drive():
        dlg = app.activeModalWidget()
        holder["polls"] += 1
        if dlg is None:
            if holder["polls"] > 60:
                holder["timer"].stop()
            return
        holder["timer"].stop()
        tv = [t for t in dlg.findChildren(QtWidgets.QTreeView) if t.objectName() == "groupsTreeView"][0]
        m = tv.model()
        for group, page, key in PAGES:
            for r in range(m.rowCount()):
                gi = m.index(r, 0)
                if m.data(gi) != group:
                    continue
                tv.expand(gi)
                for c in range(m.rowCount(gi)):
                    pi = m.index(c, 0, gi)
                    if m.data(pi) == page:
                        tv.setCurrentIndex(pi)
                        tv.clicked.emit(pi)
                        pump(0.8)
                        save(dlg.grab(), "prefs-" + key)
                        res["prefs"][key] = {"page": group + " / " + page, "size": [dlg.width(), dlg.height()]}
                        progress("prefs " + key)
        dlg.close()

    holder["timer"] = QtCore.QTimer()
    holder["timer"].timeout.connect(drive)
    holder["timer"].start(300)
    Gui.showPreferences()
    holder["timer"].stop()
    pump(0.3)


# ── 5. the report view with one message of each kind ────────────────────────────
@step("report")
def _():
    dw = find(QtWidgets.QDockWidget, "Report view")
    dw.show()
    pump(0.8)
    App.Console.PrintMessage("Opened arduino_car\n")
    App.Console.PrintMessage("Scene: 10 bodies, 10155 triangles (3.4 s)\n")
    App.Console.PrintLog("log: the activity log line of an agent command\n")
    App.Console.PrintWarning("2 unchecked\n")
    App.Console.PrintError("wheel_left was placed, but a fit check fails: overlap 469.841 mm^3\n")
    pump(1.0)
    shot("report")


res["done"] = True
json.dump(res, open(os.path.join(OUT, "fcshots.json"), "w"), indent=1)
os._exit(0)

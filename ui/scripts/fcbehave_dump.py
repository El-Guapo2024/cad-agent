# Runs inside FreeCAD's GUI (fcbehave.py starts it on the cocoa platform, windows kept off the screen): measures what the
# real 3D view does, for the comparison with cadui.getView() (oursbehave.mjs measures ours the same way). Writes fcbehave.json
# into FCGUI_OUT: the camera orientation after each standard view, the default orientation and Home, the zoom a wheel notch and
# the zoom commands make, the navigation style and the settings the Navigation page shows (what its widgets hold, which the
# parameters' defaults fill in).
import json
import math
import os
import re
import time
import traceback

import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtCore, QtGui, QtOpenGLWidgets, QtWidgets

OUT = os.environ["FCGUI_OUT"]
mw = Gui.getMainWindow()
app = QtWidgets.QApplication.instance()
res = {"errors": {}}
mw.resize(1280, 800)


def bail():
    """A step that blocks (a dialog that never shows) ends the run with what was measured so far."""
    res["errors"]["hung"] = "stopped after 150 s"
    json.dump(res, open(os.path.join(OUT, "fcbehave.json"), "w"), indent=1)
    os._exit(0)


QtCore.QTimer.singleShot(150000, bail)


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


pump(1.5)
doc = App.newDocument("behave")
box = doc.addObject("Part::Box", "Box")
box.Length, box.Width, box.Height = 170, 82, 40
doc.recompute()
pump(1.0)
view = Gui.ActiveDocument.ActiveView


def cam():
    """The Coin camera node's fields, from the text getCamera() prints."""
    t = view.getCamera()
    out = {"type": re.search(r"(\w+Camera) \{", t).group(1)}
    for k in ("height", "heightAngle", "focalDistance", "nearDistance", "farDistance", "aspectRatio"):
        m = re.search(r"\b%s ([-\d.e+]+)" % k, t)
        if m:
            out[k] = float(m.group(1))
    for k in ("position", "orientation"):
        m = re.search(r"\b%s ([-\d.e+]+) ([-\d.e+]+) ([-\d.e+]+)\s*([-\d.e+]+)?" % k, t)
        if m:
            out[k] = [float(g) for g in m.groups() if g is not None]
    return out


def state():
    q = view.getCameraOrientation().Q
    c = cam()
    return {"q": [q[0], q[1], q[2], q[3]], "dir": list(view.getViewDirection()), "up": list(view.getUpDirection()),
            "height": c.get("height"), "position": c.get("position"), "focal": c.get("focalDistance"), "camera": c.get("type")}


res["dpr"] = mw.devicePixelRatioF()
res["animation_default"] = view.isAnimationEnabled()
res["camera_type"] = view.getCameraType()
res["camera_types"] = view.listCameraTypes()
res["nav_type"] = view.getNavigationType()
res["nav_types"] = view.listNavigationTypes()
res["initial"] = state()
view.setAnimationEnabled(False)
view.fitAll()
pump(0.5)
res["initial_fit"] = state()


def views():
    out = {}
    for name in ("viewFront", "viewTop", "viewRight", "viewRear", "viewBottom", "viewLeft", "viewIsometric", "viewDimetric",
                 "viewTrimetric", "viewAxonometric", "viewDefaultOrientation"):
        view.viewFront()
        pump(0.15)
        before = state()
        getattr(view, name)()
        pump(0.3)
        s = state()
        s["height_before"] = before["height"]
        out[name] = s
    return out


safe("views", views)


def rotates():
    out = {}
    for name in ("viewRotateLeft", "viewRotateRight"):
        view.viewFront()
        pump(0.15)
        getattr(view, name)()
        pump(0.3)
        out[name] = state()
    return out


safe("rotates", rotates)


def home():
    view.viewFront()
    pump(0.2)
    Gui.runCommand("Std_ViewHome", 0)
    pump(0.5)
    return state()


safe("home", home)


def widget3d():
    """The viewer (a QGraphicsView): wheel events sent to its viewport or to the MDI view are not what Quarter listens to."""
    for w in mw.findChildren(QtWidgets.QWidget):
        if w.metaObject().className() == "Gui::View3DInventorViewer":
            return w


def wheel(w, delta, pos=None, phase=QtCore.Qt.NoScrollPhase, mods=QtCore.Qt.NoModifier):
    p = pos or QtCore.QPointF(w.width() / 2, w.height() / 2)
    ev = QtGui.QWheelEvent(p, w.mapToGlobal(p), QtCore.QPoint(0, 0), QtCore.QPoint(0, delta), QtCore.Qt.NoButton, mods, phase, False)
    app.sendEvent(w, ev)
    pump(0.15)


def zoom():
    out = {}
    w = widget3d()
    view.viewIsometric()
    view.fitAll()
    pump(0.4)
    h0 = state()["height"]
    center = QtCore.QPointF(w.width() / 2, w.height() / 2)
    wheel(w, 120, center)
    h1 = state()["height"]
    out["wheel_up_1"] = {"h0": h0, "h1": h1, "ratio": h1 / h0}
    wheel(w, -120, center)
    h2 = state()["height"]
    out["wheel_down_1_after_up_1"] = {"h2": h2, "ratio_vs_h1": h2 / h1}
    for i in range(5):
        wheel(w, 120, center)
    h3 = state()["height"]
    out["wheel_up_5_more"] = {"h3": h3, "ratio_vs_h2": h3 / h2}
    view.fitAll()
    pump(0.3)
    h4 = state()["height"]
    view.zoomIn()
    pump(0.3)
    h5 = state()["height"]
    view.zoomOut()
    pump(0.3)
    h6 = state()["height"]
    out["zoomIn"] = {"ratio": h5 / h4}
    out["zoomOut_after_zoomIn"] = {"ratio_vs_zoomIn": h6 / h5}
    # a Mac trackpad scroll (a pixel delta, a scroll phase): the Navigation page says touchpad scroll pans
    view.fitAll()
    pump(0.3)
    s0 = state()
    ev = QtGui.QWheelEvent(center, w.mapToGlobal(center), QtCore.QPoint(0, 30), QtCore.QPoint(0, 60), QtCore.Qt.NoButton,
                           QtCore.Qt.NoModifier, QtCore.Qt.ScrollUpdate, False)
    app.sendEvent(w, ev)
    pump(0.2)
    s1 = state()
    out["trackpad_scroll_60"] = {"height_ratio": s1["height"] / s0["height"], "position_moved": [b - a for a, b in zip(s0["position"], s1["position"])]}
    return out


safe("zoom", zoom)


def settings():
    """What the Navigation page's widgets hold: dialog values, which the parameters' defaults fill in."""
    out = {}
    holder = {"polls": 0}

    def grab():
        dlg = app.activeModalWidget()
        holder["polls"] += 1
        if dlg is None:
            if holder["polls"] > 60:
                holder["timer"].stop()
            return
        holder["timer"].stop()
        try:
            tv = [t for t in dlg.findChildren(QtWidgets.QTreeView) if t.objectName() == "groupsTreeView"][0]
            m = tv.model()
            for r in range(m.rowCount()):
                gi = m.index(r, 0)
                if m.data(gi) == "Display":
                    tv.expand(gi)
                    for c in range(m.rowCount(gi)):
                        pi = m.index(c, 0, gi)
                        if m.data(pi) == "Navigation":
                            tv.setCurrentIndex(pi)
                            tv.clicked.emit(pi)
            pump(0.6)
            nav = [w for w in dlg.findChildren(QtWidgets.QWidget) if w.metaObject().className() == "Gui::Dialog::DlgSettingsNavigation"][0]
            for w in nav.findChildren(QtWidgets.QWidget):
                cn = w.metaObject().className()
                if not cn.startswith("Gui::Pref"):
                    continue
                entry = w.property("prefEntry")
                if entry is None:
                    continue
                name = bytes(entry).decode() if not isinstance(entry, str) else entry
                val = None
                if cn in ("Gui::PrefCheckBox", "Gui::PrefRadioButton", "Gui::PrefCheckableGroupBox"):
                    val = w.isChecked()
                elif cn == "Gui::PrefComboBox":
                    val = w.currentText()
                elif cn == "Gui::PrefColorButton":
                    c = w.property("color")
                    val = c.name(QtGui.QColor.HexArgb) if c is not None else None
                elif cn in ("Gui::PrefSpinBox", "Gui::PrefDoubleSpinBox"):
                    val = w.value()
                elif cn == "Gui::PrefQuantitySpinBox":
                    val = w.text()
                out[name] = val
        except Exception:
            out["_error"] = traceback.format_exc()
        finally:
            dlg.close()

    holder["timer"] = QtCore.QTimer()
    holder["timer"].timeout.connect(grab)
    holder["timer"].start(300)
    Gui.showPreferences()
    holder["timer"].stop()
    return out


safe("nav_page", settings)
json.dump(res, open(os.path.join(OUT, "fcbehave.json"), "w"), indent=1)
os._exit(0)

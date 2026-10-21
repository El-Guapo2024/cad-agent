# Runs inside FreeCAD's GUI (fcbehave.py starts it on the cocoa platform, windows kept off the screen): measures what the
# real 3D view does, for the comparison with cadui.getView() (oursbehave.mjs measures ours the same way). Writes fcbehave.json
# into FCGUI_OUT: the camera orientation after each standard view, the default orientation and Home, the zoom a wheel notch and
# the zoom commands make, the navigation style and the settings the Navigation page shows (what its widgets hold, which the
# parameters' defaults fill in), the double-click interval, Fit All and Fit Selection and Align to Selection for faces, edges and
# vertices, the tree's context menu and QuickMeasure's messages. FCBEHAVE_ONLY=a,b (fcbehave.py --only) runs just those sections.
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
    res["errors"]["hung"] = "stopped after 900 s"
    json.dump(res, open(os.path.join(OUT, "fcbehave.json"), "w"), indent=1)
    os._exit(0)


QtCore.QTimer.singleShot(900000, bail)


def pump(sec=0.3):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents(QtCore.QEventLoop.AllEvents, 50)
        time.sleep(0.005)


ONLY = set(filter(None, os.environ.get("FCBEHAVE_ONLY", "").split(",")))   # fcbehave.py --only a,b: just those sections


def safe(name, fn):
    if ONLY and name not in ONLY:
        return
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


def drags():
    """CAD style's mouse: middle drag pans, middle+left (or middle+right) rotates. Qt mouse events sent to the viewer (the pointer
    of the Mac does not move). The numbers depend on the viewer's size, which is recorded: oursbehave.mjs sizes its canvas to it."""
    out = {"viewer": [widget3d().width(), widget3d().height()]}
    w = widget3d()
    M, Lb, R = QtCore.Qt.MiddleButton, QtCore.Qt.LeftButton, QtCore.Qt.RightButton

    def ev(kind, p, button, held):
        pos = QtCore.QPointF(p[0], p[1])
        app.sendEvent(w, QtGui.QMouseEvent(kind, pos, w.mapToGlobal(pos), button, held, QtCore.Qt.NoModifier))

    def drag(presses, a, b, steps=20):
        held = QtCore.Qt.NoButton
        ev(QtCore.QEvent.MouseMove, a, QtCore.Qt.NoButton, held)
        pump(0.05)
        for btn in presses:
            held = held | btn
            ev(QtCore.QEvent.MouseButtonPress, a, btn, held)
            pump(0.05)
        for i in range(1, steps + 1):
            ev(QtCore.QEvent.MouseMove, (a[0] + (b[0] - a[0]) * i / steps, a[1] + (b[1] - a[1]) * i / steps), QtCore.Qt.NoButton, held)
            pump(0.02)
        for btn in reversed(presses):
            held = held & ~btn
            ev(QtCore.QEvent.MouseButtonRelease, b, btn, held)
            pump(0.05)
        pump(0.3)

    def angle(a, b):
        d = abs(sum(x * y for x, y in zip(a, b)))
        return math.degrees(2 * math.acos(min(1.0, d)))

    cx, cy = w.width() / 2, w.height() / 2
    for name, presses, dx, dy in [("MMB drag right 100 (pan)", [M], 100, 0), ("MMB+LMB drag right 100 (rotate)", [M, Lb], 100, 0),
                                  ("MMB+LMB drag down 100 (rotate)", [M, Lb], 0, 100), ("MMB+RMB drag right 100 (rotate)", [M, R], 100, 0)]:
        view.viewIsometric()
        view.fitAll()
        pump(0.4)
        s0 = state()
        drag(presses, (cx, cy), (cx + dx, cy + dy))
        s1 = state()
        moved = [b - a for a, b in zip(s0["position"], s1["position"])]
        out[name] = {"angle_deg": angle(s0["q"], s1["q"]), "moved_in_view_heights": math.sqrt(sum(m * m for m in moved)) / s0["height"]}
    return out


safe("drags", drags)


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
            # the lists the page's combo boxes offer (the names the navigation styles and the default orientations go by)
            out["_combos"] = {w.objectName(): [w.itemText(i) for i in range(w.count())]
                              for w in nav.findChildren(QtWidgets.QComboBox) if w.objectName() and not w.property("doNotSearch")}
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


# ── Qt's double-click interval: what NavigationStyle, the NaviCube and every style ask QApplication for ──
def dblclick():
    return {"doubleClickInterval_ms": QtWidgets.QApplication.doubleClickInterval(),
            "startDragDistance_px": QtWidgets.QApplication.startDragDistance()}


safe("dblclick", dblclick)


# ── the shapes the element probes select: the same three as the scratch project "probe" that oursbehave.mjs opens ──
OBJS = {}


def probe_objects():
    post = doc.addObject("Part::Cylinder", "post")
    post.Radius, post.Height = 20, 60
    post.Placement = App.Placement(App.Vector(300, 200, 10), App.Rotation())
    tilted = doc.addObject("Part::Box", "tilted")
    tilted.Length, tilted.Width, tilted.Height = 120, 70, 30
    tilted.Placement = App.Placement(App.Vector(400, 0, 0), App.Rotation(App.Vector(1, 2, 3), 37))
    doc.recompute()
    pump(0.6)
    return {"block": box, "post": post, "tilted": tilted}


OBJS.update(probe_objects())


def local(p):
    """A point of the tilted box, given in its own frame, in the world."""
    return list(OBJS["tilted"].Placement.multVec(App.Vector(*p)))


def pick(body, kind, near):
    """The Face, Edge or Vertex of the body whose middle is nearest `near`: (its name, its middle)."""
    sh = OBJS[body].Shape
    items = {"Face": sh.Faces, "Edge": sh.Edges, "Vertex": sh.Vertexes}[kind]
    pt = App.Vector(*near)
    mid = (lambda e: e.Point) if kind == "Vertex" else (lambda e: e.CenterOfMass)
    best = min(range(len(items)), key=lambda i: (mid(items[i]) - pt).Length)
    return "%s%d" % (kind, best + 1), items[best]


def select(picks):
    """Gui.Selection holds exactly these elements (a pick is (body, kind, near); kind None is the whole body)."""
    Gui.Selection.clearSelection()
    names = []
    for body, kind, near in picks:
        o = OBJS[body]
        if kind is None:
            Gui.Selection.addSelection(o)
            names.append(o.Name)
        else:
            sub, _ = pick(body, kind, near)
            Gui.Selection.addSelection(o, sub)
            names.append("%s.%s" % (o.Name, sub))
    pump(0.15)
    return {"asked": names, "held": [[s.ObjectName] + list(s.SubElementNames) for s in Gui.Selection.getSelectionEx()]}


def state2():
    """state() plus the focal point (position + focal distance along the view) and the perspective angle."""
    s = state()
    c = cam()
    s["target"] = [p + s["focal"] * d for p, d in zip(s["position"], s["dir"])]
    s["heightAngle"] = c.get("heightAngle")
    s["aspect"] = c.get("aspectRatio")
    return s


def bbox_of(picks):
    """The box of the picked elements from FreeCAD's own shapes: a check on what the camera does with it."""
    box3 = None
    for body, kind, near in picks:
        if kind is None:
            sh = OBJS[body].Shape
        else:
            items = {"Face": OBJS[body].Shape.Faces, "Edge": OBJS[body].Shape.Edges, "Vertex": OBJS[body].Shape.Vertexes}[kind]
            sh = items[int(pick(body, kind, near)[0][len(kind):]) - 1]
        if box3 is None:
            box3 = App.BoundBox(sh.BoundBox)
        else:
            box3.add(sh.BoundBox)
    c = box3.Center
    return {"min": [box3.XMin, box3.YMin, box3.ZMin], "max": [box3.XMax, box3.YMax, box3.ZMax], "center": [c.x, c.y, c.z],
            "radius": 0.5 * math.sqrt(box3.XLength ** 2 + box3.YLength ** 2 + box3.ZLength ** 2)}


def set_view(name, roll=0.0):
    """A standard view, then turned about the viewing direction by `roll` degrees."""
    getattr(view, name)()
    pump(0.15)
    if roll:
        d = App.Vector(*view.getViewDirection())
        view.setCameraOrientation(App.Rotation(d, roll).multiply(view.getCameraOrientation()))
        pump(0.15)


def resize_viewer(w, h):
    """Resize the main window until the 3D viewer is about w x h; returns its size."""
    mw.resize(1280 + (w - 1014), 800 + (h - 661))
    pump(0.6)
    for _ in range(3):
        v = widget3d()
        mw.resize(mw.width() + (w - v.width()), mw.height() + (h - v.height()))
        pump(0.6)
    v = widget3d()
    return [v.width(), v.height()]


FIT_CASES = [
    ("fit all (no selection)", None),
    ("block whole", [("block", None, None)]),
    ("block +z face", [("block", "Face", (85, 41, 40))]),
    ("block -x face", [("block", "Face", (0, 41, 20))]),
    ("block vertical edge", [("block", "Edge", (0, 0, 20))]),
    ("block corner vertex", [("block", "Vertex", (0, 0, 0))]),
    ("block two faces +z +x", [("block", "Face", (85, 41, 40)), ("block", "Face", (170, 41, 20))]),
    ("block opposite corners", [("block", "Vertex", (0, 0, 0)), ("block", "Vertex", (170, 82, 40))]),
    ("post side face", [("post", "Face", (300, 200, 40))]),
    ("post top circle", [("post", "Edge", (300, 200, 70))]),
    ("block +z face and post whole", [("block", "Face", (85, 41, 40)), ("post", None, None)]),
    ("block +z face and post top face", [("block", "Face", (85, 41, 40)), ("post", "Face", (300, 200, 70))]),
    ("block whole and post vertex", [("block", None, None), ("post", "Vertex", (320, 200, 70))]),
    ("tilted -w face", [("tilted", "Face", local((60, 35, 0)))]),
]


def fit_probe():
    """Fit All and Fit Selection on a perspective and an orthographic camera, in a wide and a tall viewer."""
    out = {}
    for vsz in ((1014, 661), (420, 760)):
        got = resize_viewer(*vsz)
        k = "%dx%d" % tuple(got)
        out[k] = {}
        for ctype in ("Perspective", "Orthographic"):
            view.setCameraType(ctype)
            pump(0.3)
            r = {}
            for name, picks in FIT_CASES:
                set_view("viewIsometric")
                view.fitAll()
                pump(0.3)
                if picks is None:
                    Gui.Selection.clearSelection()
                    view.fitAll()
                    pump(0.5)
                    r[name] = {"state": state2()}
                    continue
                sel = select(picks)
                before = state2()
                Gui.runCommand("Std_ViewFitSelection", 0)
                pump(0.4)
                r[name] = {"selection": sel, "box": bbox_of(picks), "before": before, "state": state2()}
            out[k][ctype] = r
    view.setCameraType("Orthographic")
    resize_viewer(1014, 661)
    Gui.Selection.clearSelection()
    return out


safe("fit", fit_probe)


def vp_bbox():
    """What ViewProvider::getBoundingBox (the call View3DInventorViewer::viewObjects makes for each selected element) gives, beside
    the element's own box from the shape: the call is the Python ViewObject.getBoundingBox(subname, transform)."""
    out = {}
    for name, picks in FIT_CASES:
        if picks is None:
            continue
        r = []
        for body, kind, near in picks:
            vo = OBJS[body].ViewObject
            sub = "" if kind is None else pick(body, kind, near)[0]
            sh = OBJS[body].Shape if kind is None else {"Face": OBJS[body].Shape.Faces, "Edge": OBJS[body].Shape.Edges,
                                                      "Vertex": OBJS[body].Shape.Vertexes}[kind][int(sub[len(kind):]) - 1]
            box_of = lambda b: [round(v, 3) for v in (b.XMin, b.YMin, b.ZMin, b.XMax, b.YMax, b.ZMax)] if b.isValid() else None
            args = [sub] if sub else []
            r.append({"sub": sub or "(whole)", "viewprovider": box_of(vo.getBoundingBox(*args)),
                      "viewprovider_untransformed": box_of(vo.getBoundingBox(*args, transform=False)), "shape": box_of(sh.BoundBox)})
        out[name] = r
    return out


safe("vp_bbox", vp_bbox)


# ── Align to Selection: the camera after Std_AlignToSelection, from many starting orientations ──
ALIGN_CASES = [
    ("block +z", [("block", "Face", (85, 41, 40))]),
    ("block -z", [("block", "Face", (85, 41, 0))]),
    ("block +x", [("block", "Face", (170, 41, 20))]),
    ("block -x", [("block", "Face", (0, 41, 20))]),
    ("block +y", [("block", "Face", (85, 82, 20))]),
    ("block -y", [("block", "Face", (85, 0, 20))]),
    ("tilted +u", [("tilted", "Face", local((120, 35, 15)))]),
    ("tilted -u", [("tilted", "Face", local((0, 35, 15)))]),
    ("tilted +v", [("tilted", "Face", local((60, 70, 15)))]),
    ("tilted -v", [("tilted", "Face", local((60, 0, 15)))]),
    ("tilted +w", [("tilted", "Face", local((60, 35, 30)))]),
    ("tilted -w", [("tilted", "Face", local((60, 35, 0)))]),
    ("post top disc", [("post", "Face", (300, 200, 70))]),
    ("post bottom disc", [("post", "Face", (300, 200, 10))]),
    ("post side", [("post", "Face", (300, 200, 40))]),
    ("block vertical edge", [("block", "Edge", (0, 0, 20))]),
    ("block top edge along x", [("block", "Edge", (85, 0, 40))]),
    ("post top circle", [("post", "Edge", (300, 200, 70))]),
    ("block +z and +x faces", [("block", "Face", (85, 41, 40)), ("block", "Face", (170, 41, 20))]),
    ("block +z and post top", [("block", "Face", (85, 41, 40)), ("post", "Face", (300, 200, 70))]),
    ("block corner vertex", [("block", "Vertex", (0, 0, 0))]),
    ("block whole", [("block", None, None)]),
]
ALIGN_STARTS = [("front", "viewFront", 0), ("rear", "viewRear", 0), ("top", "viewTop", 0), ("bottom", "viewBottom", 0),
                ("left", "viewLeft", 0), ("right", "viewRight", 0), ("iso", "viewIsometric", 0), ("iso roll 30", "viewIsometric", 30),
                ("front roll 60", "viewFront", 60), ("top roll 100", "viewTop", 100), ("top roll -170", "viewTop", -170),
                ("rear roll 20", "viewRear", 20)]


def align_probe():
    out = {}
    view.setCameraType("Orthographic")
    for name, picks in ALIGN_CASES:
        out[name] = {}
        for sname, v, roll in ALIGN_STARTS:
            set_view(v, roll)
            Gui.Selection.clearSelection()
            view.fitAll()
            pump(0.15)
            sel = select(picks)
            before = state2()
            Gui.runCommand("Std_AlignToSelection", 0)
            pump(0.15)
            after = state2()
            keep = ("q", "target", "focal", "height")
            out[name][sname] = {"before": {k: before[k] for k in keep}, "after": {k: after[k] for k in keep}}
            if sname == "front":
                out[name]["selection"] = sel
    Gui.Selection.clearSelection()
    return out


safe("align", align_probe)


# ── the tree's context menu: what Gui::TreeWidget::contextMenuEvent puts up on a part, on two parts and on the document ──
def dump_menu(m, depth=0):
    out = []
    for a in m.actions():
        if a.isSeparator():
            out.append({"sep": True})
            continue
        d = {"text": a.text(), "name": a.objectName(), "shortcut": a.shortcut().toString(), "enabled": a.isEnabled(),
             "checkable": a.isCheckable(), "checked": a.isChecked(), "visible": a.isVisible(), "icon": not a.icon().isNull()}
        sub = a.menu()
        if sub is not None and depth < 4:
            try:
                sub.aboutToShow.emit()
            except Exception:
                pass
            d["menu"] = dump_menu(sub, depth + 1)
        out.append(d)
    return out


def tree_menu():
    tree = [t for t in mw.findChildren(QtWidgets.QTreeWidget) if t.metaObject().className() == "Gui::TreeWidget"][0]
    doc_item = tree.topLevelItem(0)
    out = {"workbench": Gui.activeWorkbench().name()}

    def at(item, selection):
        Gui.Selection.clearSelection()
        for n in selection:
            Gui.Selection.addSelection(OBJS[n])
        pump(0.5)
        pos = tree.visualItemRect(item).center()
        holder = {"polls": 0}

        def grab():
            holder["polls"] += 1
            menus = [w for w in app.topLevelWidgets() if isinstance(w, QtWidgets.QMenu) and w.isVisible() and w.actions()]
            if not menus:
                if holder["polls"] > 40:
                    holder["timer"].stop()
                    QtWidgets.QApplication.sendEvent(tree, QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_Escape, QtCore.Qt.NoModifier))
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
        return holder.get("actions", "no menu opened")

    children = {doc_item.child(i).text(0): doc_item.child(i) for i in range(doc_item.childCount())}
    out["part"] = at(children["Box"], ["block"])
    out["two parts"] = at(children["Box"], ["block", "post"])
    out["document"] = at(doc_item, [])
    Gui.Selection.clearSelection()
    return out


safe("tree_menu", tree_menu)


# ── QuickMeasure: the words in the status bar's right side for a selection (Measurement::findType and QuickMeasure::printResult) ──
QM_CASES = [
    ("circle", [("post", "Edge", (300, 200, 70))]),
    ("disc face", [("post", "Face", (300, 200, 70))]),
    ("cylinder face", [("post", "Face", (300, 200, 40))]),
    ("two parallel edges", [("block", "Edge", (0, 0, 20)), ("block", "Edge", (170, 0, 20))]),
    ("two circles, parallel axes", [("post", "Edge", (300, 200, 70)), ("post", "Edge", (300, 200, 10))]),
    ("two circles, axes 30 degrees apart", [("post", "Edge", (300, 200, 70)), ("post2", "Edge", (500, 185, 35.98))]),
    ("circle and a line", [("post", "Edge", (300, 200, 70)), ("block", "Edge", (0, 0, 20))]),
    ("circle and a plane", [("post", "Edge", (300, 200, 70)), ("block", "Face", (85, 41, 40))]),
    ("circle and its own cylinder", [("post", "Edge", (300, 200, 70)), ("post", "Face", (300, 200, 40))]),
    ("circle and a cylinder 30 degrees off", [("post", "Edge", (300, 200, 70)), ("post2", "Face", (500, 192.5, 22.99))]),
    ("point and a circle", [("block", "Vertex", (0, 0, 0)), ("post", "Edge", (300, 200, 70))]),
    ("point and a cylinder", [("block", "Vertex", (0, 0, 0)), ("post", "Face", (300, 200, 40))]),
    ("point and a plane", [("block", "Vertex", (170, 82, 40)), ("post", "Face", (300, 200, 70))]),
]


def quickmeasure():
    post2 = doc.addObject("Part::Cylinder", "post2")
    post2.Radius, post2.Height = 10, 30
    post2.Placement = App.Placement(App.Vector(500, 200, 10), App.Rotation(App.Vector(1, 0, 0), 30))
    doc.recompute()
    pump(0.5)
    OBJS["post2"] = post2
    out = {}

    def labels():
        return {w.objectName() or ("#%d" % i): w.text() for i, w in enumerate(mw.statusBar().findChildren(QtWidgets.QLabel)) if w.text()}

    Gui.Selection.clearSelection()
    pump(0.6)
    base = labels()
    for name, picks in QM_CASES:
        sel = select(picks)
        pump(0.6)
        now = labels()
        out[name] = {"selection": sel["held"], "message": [t for k, t in now.items() if base.get(k) != t]}
        Gui.Selection.clearSelection()
        pump(0.4)
    return out


safe("quickmeasure", quickmeasure)
json.dump(res, open(os.path.join(OUT, "fcbehave.json"), "w"), indent=1)
os._exit(0)

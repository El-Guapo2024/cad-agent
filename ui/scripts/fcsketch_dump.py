# Runs inside FreeCAD's GUI (fcsketch.py starts it on the X11 or Mac platform, windows kept off the screen): what the
# Sketcher shows and does in edit mode, as the reference ui/scripts/sketchcheck.mjs compares the workbench's Sketcher with.
#
# Writes FCGUI_OUT/fcsketch.json:
#   chrome:  the toolbars that show while a sketch is edited (each command, its menu text and shortcut, and for a group
#            command the commands of its drop-down), the menu bar's Sketch menu, and the task panel's boxes and buttons;
#   params:  what a fresh profile's (FreeCAD Light) Sketcher and View parameters hold that the edit mode draws with;
#   cases:   for each case of sketchcases.json, the sketch after its steps (the geometry, the constraints, the solver's
#            message) when the same clicks, keys and selections are sent to the real 3D view.
#
# Clicks are synthetic Qt mouse events sent to the 3D view's viewport at the pixel where FreeCAD itself projects the
# case's sketch coordinates (View3DInventorPy::getPointOnViewport), with the camera the case file names.
import os, json, math, traceback
import FreeCAD as App, FreeCADGui as Gui
from PySide6 import QtWidgets, QtCore, QtGui

OUT = os.environ["FCGUI_OUT"]
CASES = json.load(open(os.environ["FCSKETCH_CASES"]))
ONLY = [x for x in os.environ.get("FCSKETCH_ONLY", "").split(",") if x]
mw = Gui.getMainWindow()
app = QtWidgets.QApplication.instance()
res = {"errors": {}, "cases": {}, "dialogs": []}
current = {"case": None}


def accept_modal():
    """The datum dialog (EditDatumDialog's exec) and any message box a step opens: what it shows, then OK."""
    w = app.activeModalWidget()
    if w is None:
        return
    d = {"case": current["case"], "title": w.windowTitle(), "widgets": widgets(w)}
    res["dialogs"].append(d)
    if isinstance(w, QtWidgets.QDialog):
        w.accept()
    else:
        w.close()


modal_timer = QtCore.QTimer()
modal_timer.timeout.connect(accept_modal)
modal_timer.start(150)


def pump(n=8):
    for _ in range(n):
        app.processEvents()


def wait(ms):
    """Let FreeCAD's timers and sensors run (SketcherTests' GuiTestCase.pump): a synthetic event handled at once sees the
    scene of the last redraw, and the preselection the next click reads comes from it."""
    loop = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(ms, loop.quit)
    loop.exec()


def act(a, depth=0):
    if a.isSeparator():
        return "---"
    d = {"name": a.objectName(), "text": a.text(), "shortcut": a.shortcut().toString(), "enabled": a.isEnabled(),
         "checkable": a.isCheckable(), "checked": a.isChecked(), "icon": not a.icon().isNull()}
    m = a.menu()
    if m is not None and depth < 6:
        try:
            m.aboutToShow.emit()
        except Exception:
            pass
        d["menu"] = [act(x, depth + 1) for x in m.actions()]
    if a.objectName().startswith("Sketcher_Comp"):
        # A group command (Gui::ActionGroup): its drop-down's commands, from the command itself.
        try:
            subs = Gui.Command.get(a.objectName()).getAction()
            d["group"] = [act(x, depth + 1) for x in subs]
        except Exception as e:
            d["group_error"] = str(e)
    return d


def widgets(w, depth=0):
    out = []
    for c in w.children():
        if not isinstance(c, QtWidgets.QWidget):
            continue
        d = {"cls": c.metaObject().className(), "name": c.objectName()}
        for attr in ("text", "title"):
            f = getattr(c, attr, None)
            if callable(f):
                try:
                    v = f()
                    if v:
                        d[attr] = v
                except Exception:
                    pass
        kids = widgets(c, depth + 1) if depth < 14 else []
        if kids:
            d["kids"] = kids
        out.append(d)
    return out


def safe(name, fn):
    try:
        fn()
    except Exception:
        res["errors"][name] = traceback.format_exc()


def new_sketch(doc, name):
    body = doc.getObject("Body") or doc.addObject("PartDesign::Body", "Body")
    sk = body.newObject("Sketcher::SketchObject", name)
    sk.AttachmentSupport = (body.Origin.OriginFeatures[3], [""])  # XY_Plane
    sk.MapMode = "FlatFace"
    doc.recompute()
    return sk


# ── the sketch, as the workbench's solver contract writes it (ui/src/planegcs-fake.ts) ──
GEO_UNDEF = -2000


def geo_out(sk):
    out = []
    for i, g in enumerate(sk.Geometry):
        c = bool(sk.getConstruction(i))
        t = type(g).__name__
        if t == "Point":
            d = {"type": "Point", "at": [g.X, g.Y]}
        elif t == "LineSegment":
            d = {"type": "LineSegment", "start": [g.StartPoint.x, g.StartPoint.y], "end": [g.EndPoint.x, g.EndPoint.y]}
        elif t == "Circle":
            d = {"type": "Circle", "center": [g.Center.x, g.Center.y], "radius": g.Radius}
        elif t == "ArcOfCircle":
            x0 = math.atan2(g.XAxis.y, g.XAxis.x)
            d = {"type": "ArcOfCircle", "center": [g.Center.x, g.Center.y], "radius": g.Radius,
                 "start_angle": g.FirstParameter + x0, "end_angle": g.LastParameter + x0}
        elif t in ("Ellipse", "ArcOfEllipse", "ArcOfHyperbola", "ArcOfParabola"):
            d = {"type": t, "center": [g.Location.x, g.Location.y]}
            if t == "ArcOfParabola":
                d["focal"] = g.Focal
            else:
                d["major_radius"], d["minor_radius"] = g.MajorRadius, g.MinorRadius
            d["x_axis"] = [g.XAxis.x, g.XAxis.y]
            if t != "Ellipse":
                d["start_angle"], d["end_angle"] = g.FirstParameter, g.LastParameter
        elif t == "BSplineCurve":
            d = {"type": t, "poles": [[q.x, q.y] for q in g.getPoles()], "weights": list(g.getWeights()),
                 "knots": list(g.getKnots()), "mults": list(g.getMultiplicities()), "degree": g.Degree,
                 "periodic": g.isPeriodic()}
        else:
            d = {"type": t}
        if c:
            d["construction"] = True
        out.append(d)
    return out


def cons_args(c):
    """Sketcher.Constraint(type, *args, value): the arguments FreeCAD's Python constructor takes, value left out."""
    t, f, fp, s, sp, th, tp = c.Type, c.First, c.FirstPos, c.Second, c.SecondPos, c.Third, c.ThirdPos
    if t == "Coincident":
        return [f, fp, s, sp]
    if t in ("Horizontal", "Vertical"):
        return [f] if s == GEO_UNDEF else [f, fp, s, sp]
    if t in ("Parallel", "Equal"):
        return [f, s]
    if t in ("Perpendicular", "Tangent"):
        if th != GEO_UNDEF:
            return [f, s, th, tp]
        if fp == 0 and sp == 0:
            return [f, s]
        if sp == 0:
            return [f, fp, s]
        return [f, fp, s, sp]
    if t == "PointOnObject":
        return [f, fp, s]
    if t in ("Distance", "DistanceX", "DistanceY"):
        if s == GEO_UNDEF:
            return [f] if fp == 0 else [f, fp]
        if fp == 0 and sp == 0:     # between two edges: Constraint('Distance', GeoId1, GeoId2, value)
            return [f, s]
        if sp == 0:
            return [f, fp, s]
        return [f, fp, s, sp]
    if t in ("Radius", "Diameter", "Block", "Weight"):
        return [f]
    if t == "Angle":
        if s == GEO_UNDEF:
            return [f]
        if fp == 0 and sp == 0:
            return [f, s]
        return [f, fp, s, sp]
    if t == "Symmetric":
        return [f, fp, s, sp, th] if tp == 0 else [f, fp, s, sp, th, tp]
    return [f, fp, s, sp, th, tp]


ALIGNMENTS = {1: "EllipseMajorDiameter", 2: "EllipseMinorDiameter", 3: "EllipseFocus1", 4: "EllipseFocus2",
              5: "HyperbolaMajor", 6: "HyperbolaMinor", 7: "HyperbolaFocus", 8: "ParabolaFocus",
              9: "BSplineControlPoint", 10: "BSplineKnotPoint", 11: "ParabolaFocalAxis"}


def cons_out(sk):
    import re
    out = []
    for c in sk.Constraints:
        if c.Type == "InternalAlignment":
            a = dict(re.findall(r'(\w+)="([^"]*)"', c.Content))
            kind = int(a.get("InternalAlignmentType", 0))
            args = [c.First, c.Second] if kind in (1, 2, 5, 6, 11) else [c.First, c.FirstPos, c.Second] if kind in (3, 4, 7, 8) \
                else [c.First, c.FirstPos, c.Second, int(a.get("InternalAlignmentIndex", -1))]
            out.append({"type": "InternalAlignment:" + ALIGNMENTS.get(kind, "Undef"), "args": args})
            continue
        d = {"type": c.Type, "args": cons_args(c)}
        if c.Type in ("Distance", "DistanceX", "DistanceY", "Radius", "Diameter", "Angle", "Weight"):
            d["value"] = c.Value
            if not c.Driving:
                d["driving"] = False
        if c.Name:
            d["name"] = c.Name
        out.append(d)
    return out


def report_text():
    for w in mw.findChildren(QtWidgets.QTextEdit):
        if w.metaObject().className() == "Gui::DockWnd::ReportOutput":
            return w.toPlainText()
    return ""


def task_message():
    for w in mw.findChildren(QtWidgets.QWidget):
        if w.objectName() == "labelStatus" and w.metaObject().className() == "Gui::StatefulLabel":
            link = [x for x in w.parent().children() if getattr(x, "objectName", lambda: "")() == "labelStatusLink"]
            return {"status": w.text(), "link": link[0].text() if link else ""}
    return None


KEYS = {"Escape": QtCore.Qt.Key_Escape, "Delete": QtCore.Qt.Key_Delete, "Return": QtCore.Qt.Key_Return, "Tab": QtCore.Qt.Key_Tab}


def plate_sketch(name):
    """A case with "plate": a document of its own holding a Body with the 40 x 20 x 5 plate (a rectangle on XY padded
    5 mm), and the case's sketch on the plate's top face (Pad.Face6, FlatFace), after the Pad."""
    import Part
    doc = App.newDocument("P_" + name.replace("-", "_"))
    body = doc.addObject("PartDesign::Body", "Body")
    base = body.newObject("Sketcher::SketchObject", "Sketch")
    base.AttachmentSupport = (body.Origin.OriginFeatures[3], [""])
    base.MapMode = "FlatFace"
    pts = [App.Vector(0, 0, 0), App.Vector(40, 0, 0), App.Vector(40, 20, 0), App.Vector(0, 20, 0)]
    for i in range(4):
        base.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 4]))
    pad = body.newObject("PartDesign::Pad", "Pad")
    pad.Profile = base
    pad.Length = 5
    doc.recompute()
    base.Visibility = False
    sk = body.newObject("Sketcher::SketchObject", "S")
    sk.AttachmentSupport = (pad, ["Face6"])
    sk.MapMode = "FlatFace"
    doc.recompute()
    return doc, sk


def ext_out(sk):
    """The external geometry after the two axes (ExternalGeo[2:]), in the solver's form, and the references."""
    out = []
    for g in sk.ExternalGeo[2:]:
        t = type(g).__name__
        if t == "Point":
            out.append({"type": "Point", "at": [g.X, g.Y]})
        elif t == "LineSegment":
            out.append({"type": "LineSegment", "start": [g.StartPoint.x, g.StartPoint.y], "end": [g.EndPoint.x, g.EndPoint.y]})
        elif t == "Circle":
            out.append({"type": "Circle", "center": [g.Center.x, g.Center.y], "radius": g.Radius})
        else:
            out.append({"type": t})
    refs = [[o.Name, s] for o, subs in sk.ExternalGeometry for s in (subs if isinstance(subs, (list, tuple)) else [subs])]
    return out, refs


def run_case(doc, case, k):
    current["case"] = case["name"]
    report_at = len(report_text())
    if case.get("plate"):
        doc, sk = plate_sketch(case["name"])
    else:
        sk = new_sketch(doc, "S%d" % k)
    setup = case.get("setup") or {}
    import Part, Sketcher
    for g in setup.get("geometry", []):
        V = lambda p: App.Vector(p[0], p[1], 0)
        t = g["type"]
        if t == "Point":
            geo = Part.Point(V(g["at"]))
        elif t == "LineSegment":
            geo = Part.LineSegment(V(g["start"]), V(g["end"]))
        elif t == "Circle":
            geo = Part.Circle(V(g["center"]), App.Vector(0, 0, 1), g["radius"])
        elif t == "BSplineCurve":
            geo = Part.BSplineCurve([V(q) for q in g["poles"]], g["mults"], g["knots"], g.get("periodic", False), g["degree"],
                                    g.get("weights"))
        else:
            geo = Part.ArcOfCircle(Part.Circle(V(g["center"]), App.Vector(0, 0, 1), g["radius"]), g["start_angle"], g["end_angle"])
        sk.addGeometry(geo, bool(g.get("construction")))
    for c in setup.get("constraints", []):
        args = list(c["args"]) + ([c["value"]] if "value" in c else [])
        sk.addConstraint(Sketcher.Constraint(c["type"], *args))
    doc.recompute()
    Gui.ActiveDocument.setEdit(sk)
    pump(20)
    view = Gui.ActiveDocument.ActiveView
    cam = CASES["camera"]
    cx, cy = cam["center"]
    view.setCamera("#Inventor V2.1 ascii\nOrthographicCamera {\n viewportMapping ADJUST_CAMERA\n position %g %g 100\n"
                   " orientation 0 0 1 0\n nearDistance 0\n farDistance 200\n aspectRatio 1\n focalDistance 100\n height %g\n}\n"
                   % (cx, cy, cam["height"]))
    pump(10)
    vp = view.graphicsView().viewport()

    def scr(p):
        px = view.getPointOnViewport(App.Vector(p[0], p[1], 0))
        return QtCore.QPoint(int(px[0]), vp.height() - 1 - int(px[1]))

    held = {"buttons": QtCore.Qt.NoButton}

    def send(kind, q, button):
        # QApplication::sendEvent straight to the viewport, as FreeCAD's own SketcherTests (GuiTestCase.send_mouse) do:
        # QTest's events reach the Sketcher's preselection differently, and auto-constraints on a preselected point or
        # edge never came out of them.
        if kind == "press":
            held["buttons"] = held["buttons"] | button
        elif kind == "release":
            held["buttons"] = held["buttons"] & ~button
        t = {"move": QtCore.QEvent.MouseMove, "press": QtCore.QEvent.MouseButtonPress, "release": QtCore.QEvent.MouseButtonRelease}[kind]
        ev = QtGui.QMouseEvent(t, QtCore.QPointF(q), QtCore.QPointF(vp.mapToGlobal(q)), QtCore.Qt.NoButton if kind == "move" else button,
                               held["buttons"], QtCore.Qt.NoModifier)
        QtWidgets.QApplication.sendEvent(vp, ev)

    def mouse(kind, p, button=QtCore.Qt.LeftButton):
        send(kind, scr(p), button)
        wait(80 if kind == "move" else 60)

    for st in case["steps"]:
        if "cmd" in st:
            Gui.runCommand(st["cmd"], 0)
            pump(6)
        elif "move" in st:
            mouse("move", st["move"])
        elif "click" in st:
            p = st["click"]
            # A move on the way there, as a real pointer makes, then the move onto the point, the press and the release.
            mouse("move", [p[0] + 0.7, p[1] + 0.4])
            mouse("move", p)
            mouse("press", p)
            mouse("release", p)
        elif "rclick" in st:
            p = st["rclick"]
            mouse("move", p)
            mouse("press", p, QtCore.Qt.RightButton)
            mouse("release", p, QtCore.Qt.RightButton)
            # the context menu FreeCAD may pop up in STATUS_NONE
            for m in app.topLevelWidgets():
                if isinstance(m, QtWidgets.QMenu) and m.isVisible():
                    m.close()
        elif "drag" in st:
            a, b = st["drag"]
            mouse("move", a)
            mouse("press", a)
            n = 6
            for i in range(1, n + 1):
                mouse("move", [a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n])
            mouse("release", b)
        elif "key" in st:
            key = st["key"]
            qk = KEYS.get(key) or getattr(QtCore.Qt, "Key_" + key.upper())
            for t in (QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease):
                QtWidgets.QApplication.sendEvent(vp, QtGui.QKeyEvent(t, qk, QtCore.Qt.NoModifier, key if len(key) == 1 else ""))
            wait(60)
        elif "select" in st:
            for sub in st["select"]:
                Gui.Selection.addSelection(doc.Name, "Body", sk.Name + "." + sub)
            pump(3)
        elif "pick" in st:
            # an element of the model selected, as a click on it in the 3D view selects it (the External tool takes
            # it from the selection: DrawSketchHandlerExternal::onSelectionChanged)
            obj, sub = st["pick"].split(".", 1)
            Gui.Selection.addSelection(doc.Name, obj, sub)
            pump(6)
            wait(100)
        elif "clear" in st:
            Gui.Selection.clearSelection()
    pump(6)
    res["cases"][case["name"]] = {"geometry": geo_out(sk), "constraints": cons_out(sk), "message": task_message(),
                                  "report": report_text()[report_at:]}
    if case.get("plate"):
        ext, refs = ext_out(sk)
        res["cases"][case["name"]].update({"external": ext, "external_geometry": refs})
    Gui.ActiveDocument.resetEdit()
    pump(6)


def chrome_and_cases():
    mw.resize(1280, 800)
    mw.show()
    pump(10)
    Gui.activateWorkbench("PartDesignWorkbench")
    doc = App.newDocument("T")
    sk = new_sketch(doc, "Sketch")
    Gui.ActiveDocument.setEdit(sk)
    pump(30)
    vp = Gui.ActiveDocument.ActiveView.graphicsView().viewport()
    res["viewport"] = [vp.width(), vp.height()]
    res["workbench"] = Gui.activeWorkbench().name()
    tbs = []
    for tb in mw.findChildren(QtWidgets.QToolBar):
        if tb.isVisible():
            tbs.append({"name": tb.objectName(), "title": tb.windowTitle(), "row": tb.y(), "x": tb.x(),
                        "actions": [act(a) for a in tb.actions()]})
    tbs.sort(key=lambda t: (t["row"], t["x"]))
    menus = [act(a) for a in mw.menuBar().actions()]
    tv = [w for w in mw.findChildren(QtWidgets.QWidget) if w.metaObject().className() == "Gui::TaskView::TaskView"]
    res["chrome"] = {"toolbars": tbs, "menubar": menus, "taskview": [widgets(t) for t in tv]}
    res["message_empty"] = task_message()
    Gui.ActiveDocument.resetEdit()
    pump(10)
    for k, case in enumerate(CASES["cases"]):
        if ONLY and case["name"] not in ONLY:
            continue
        try:
            run_case(doc, case, k)
        except Exception:
            res["errors"][case["name"]] = traceback.format_exc()
            try:
                Gui.ActiveDocument.resetEdit()
            except Exception:
                pass


def params():
    p = {}
    for path, names in {
        "User parameter:BaseApp/Preferences/View": ["EditedEdgeColor", "EditedVertexColor", "ConstructionColor", "InternalAlignedGeoColor",
            "FullyConstraintElementColor", "FullyConstraintConstructionElementColor", "FullyConstraintInternalAlignmentColor",
            "FullyConstrainedColor", "InvalidSketchColor", "ConstrainedDimColor", "ConstrainedIcoColor", "NonDrivingConstrDimColor",
            "ExprBasedConstrDimColor", "DeactivatedConstrDimColor", "ExternalColor", "ExternalDefiningColor", "HighlightColor",
            "SelectionColor", "CursorTextColor", "CursorCrosshairColor", "CreateLineColor", "AxisXColor", "AxisYColor",
            "MarkerSize", "EditSketcherFontSize", "ConstraintSymbolSize", "DefaultShapePointSize", "InformationColor"],
        "User parameter:BaseApp/Preferences/Mod/Sketcher/General": ["GridLineColor", "GridDivLineColor", "ShowGrid", "GridSize",
            "AxisTransparency"],
        "User parameter:BaseApp/Preferences/Mod/Sketcher/View": ["EdgeWidth", "ConstructionWidth", "ExternalWidth", "AxisLineWidth"],
    }.items():
        g = App.ParamGet(path)
        for n in names:
            v = None
            for get in (g.GetUnsigned, g.GetInt, g.GetBool, g.GetString):
                try:
                    if n in [x[1] for x in g.GetContents() or []]:
                        v = [x for x in g.GetContents() if x[1] == n][0][2]
                        break
                except Exception:
                    pass
            p[n] = v
    res["params"] = p


safe("params", params)
safe("chrome_and_cases", chrome_and_cases)
json.dump(res, open(os.path.join(OUT, "fcsketch.json"), "w"), indent=1)
os._exit(0)

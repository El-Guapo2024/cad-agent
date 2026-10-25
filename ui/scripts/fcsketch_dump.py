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
    if isinstance(w, QtWidgets.QMessageBox) and current.get("msgbox"):
        # a case's "msgbox": the button of that text is pressed (QMessageBox::question's Yes, Cancel ...)
        for b in w.buttons():
            if b.text().replace("&", "") == current["msgbox"]:
                b.click()
                return
    # a "cmd" step's "dialog": the named fields set first (a spin box's value, a check box's state)
    for name, v in (current.get("dialog") or {}).items():
        c = w.findChild(QtWidgets.QWidget, name)
        if isinstance(c, QtWidgets.QAbstractButton):
            c.setChecked(bool(v))
        elif c is not None:
            c.setValue(v)
    current["dialog"] = None
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
        if not c.IsActive:
            d["active"] = False
        if c.InVirtualSpace:
            d["virtual_space"] = True
        out.append(d)
    # SketchObject's ExpressionEngine: ".Constraints[3]" or ".Constraints.name" bound to an expression
    import re as _re
    for path, e in sk.ExpressionEngine:
        m = _re.match(r"^\.?Constraints(?:\[(\d+)\]|\.(\w+))$", path)
        if not m:
            continue
        i = int(m.group(1)) if m.group(1) else next((k for k, c in enumerate(sk.Constraints) if c.Name == m.group(2)), -1)
        if 0 <= i < len(out):
            out[i]["expr"] = e
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


KEYS = {"Escape": QtCore.Qt.Key_Escape, "Delete": QtCore.Qt.Key_Delete, "Return": QtCore.Qt.Key_Return, "Tab": QtCore.Qt.Key_Tab,
        "Backspace": QtCore.Qt.Key_Backspace}


def char_key(ch):
    """The Qt key of a typed character."""
    named = {".": QtCore.Qt.Key_Period, "-": QtCore.Qt.Key_Minus, ",": QtCore.Qt.Key_Comma, " ": QtCore.Qt.Key_Space,
             "+": QtCore.Qt.Key_Plus, "*": QtCore.Qt.Key_Asterisk, "/": QtCore.Qt.Key_Slash, "(": QtCore.Qt.Key_ParenLeft,
             ")": QtCore.Qt.Key_ParenRight, "=": QtCore.Qt.Key_Equal}
    if ch in named:
        return named[ch]
    if ch.isdigit():
        return getattr(QtCore.Qt, "Key_" + ch)
    return getattr(QtCore.Qt, "Key_" + ch.upper())


def tool_widget():
    for w in mw.findChildren(QtWidgets.QWidget):
        if w.metaObject().className() == "SketcherGui::SketcherToolDefaultWidget" and w.isVisible():
            return w
    return None


def set_tool_widget(spec):
    """{"name": "checkBoxTS1", "checked": true} | {"name": "comboBox1", "index": 2} | {"name": "parameterOne", "value": 4}."""
    tw = tool_widget()
    if tw is None:
        raise RuntimeError("no tool widget for %r" % (spec,))
    c = tw.findChild(QtWidgets.QWidget, spec["name"])
    if c is None:
        raise RuntimeError("no %s in the tool widget" % spec["name"])
    if "checked" in spec:
        if c.isChecked() != bool(spec["checked"]):
            c.click()
    elif "index" in spec:
        c.setCurrentIndex(int(spec["index"]))
    elif "value" in spec:
        c.setFocus()
        le = c.findChild(QtWidgets.QLineEdit)
        le.selectAll()
        for ch in str(spec["value"]):
            for t in (QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease):
                QtWidgets.QApplication.sendEvent(c, QtGui.QKeyEvent(t, char_key(ch), QtCore.Qt.NoModifier, ch))
        for t in (QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease):
            QtWidgets.QApplication.sendEvent(c, QtGui.QKeyEvent(t, QtCore.Qt.Key_Return, QtCore.Qt.NoModifier, "\r"))


def tool_widget_out():
    """What the Tool Parameters box shows: its title and each visible control (label, state)."""
    tw = tool_widget()
    if tw is None:
        return None
    out = []
    for c in tw.findChildren(QtWidgets.QWidget):
        if not c.isVisibleTo(tw):
            continue
        n = c.objectName()
        if n.startswith("checkBoxTS"):
            out.append({"name": n, "text": c.text(), "checked": c.isChecked()})
        elif n.startswith("comboBox"):
            out.append({"name": n, "items": [c.itemText(i) for i in range(c.count())], "index": c.currentIndex()})
        elif n.startswith("parameter") and c.metaObject().className() == "Gui::PrefQuantitySpinBox":
            # PySide may hand the box back as a QAbstractSpinBox (no rawValue method): the Q_PROPERTY then
            out.append({"name": n, "value": c.rawValue() if hasattr(c, "rawValue") else c.property("rawValue")})
    box = tw.parentWidget()
    while box is not None and not box.inherits("Gui::TaskView::TaskBox"):
        box = box.parentWidget()
    title = ""
    if box is not None:  # the TaskBox's header (QSint::TaskHeader) holds the title on a button
        for h in box.findChildren(QtWidgets.QWidget):
            if "TaskHeader" in h.metaObject().className():
                for b in h.findChildren(QtWidgets.QAbstractButton):
                    if b.text():
                        title = b.text()
                        break
                if not title:
                    for b in h.findChildren(QtWidgets.QLabel):
                        if b.text():
                            title = b.text()
                            break
                break
    return {"title": title, "controls": out}


def cpp(w):
    import shiboken6
    return shiboken6.getCppPointer(w)[0]


def ovp_boxes():
    """The on-view parameters' spin boxes over the 3D views (EditableDatumLabel::startEdit parents them to the MDI view)."""
    def in_mdi(w):
        while w is not None:
            if w.metaObject().className() == "QMdiArea":
                return True
            w = w.parentWidget()
        return False
    return [w for w in mw.findChildren(QtWidgets.QAbstractSpinBox)
            if w.metaObject().className() == "Gui::QuantitySpinBox" and in_mdi(w)]


def ovp_out(before=()):
    """The on-view parameters shown at the end of the steps: each spin box over the 3D view and its text."""
    out = []
    for w in ovp_boxes():
        if w.isVisible() and cpp(w) not in before:
            le = w.findChild(QtWidgets.QLineEdit)
            out.append({"text": le.text() if le else "", "focus": w.hasFocus()})
    return out


def set_params(params, restore=None):
    """A case's "params": {"Mod/Sketcher/Tools/OnViewParameterVisibility": 2, ...} (ints, bools, floats)."""
    old = {}
    for k, v in params.items():
        path, name = k.rsplit("/", 1)
        g = App.ParamGet("User parameter:BaseApp/Preferences/" + path)
        if isinstance(v, bool):
            old[k] = g.GetBool(name, False) if name in [x[1] for x in g.GetContents() or []] else None
            g.SetBool(name, v)
        elif isinstance(v, int):
            old[k] = g.GetInt(name) if name in [x[1] for x in g.GetContents() or []] else None
            g.SetInt(name, v)
        else:
            old[k] = g.GetFloat(name) if name in [x[1] for x in g.GetContents() or []] else None
            g.SetFloat(name, float(v))
    return old


def unset_params(old):
    for k, v in old.items():
        path, name = k.rsplit("/", 1)
        g = App.ParamGet("User parameter:BaseApp/Preferences/" + path)
        for rm in (g.RemBool, g.RemInt, g.RemFloat):
            try:
                rm(name)
            except Exception:
                pass
        if v is not None:
            (g.SetBool if isinstance(v, bool) else g.SetInt if isinstance(v, int) else g.SetFloat)(name, v)


# ── the task panel's Constraints and Elements boxes (TaskSketcherConstraints, TaskSketcherElements) ──
PANEL_PARAMS = {"Mod/Sketcher/General": ["ConstraintFilterEnabled", "SelectedConstraintFilters", "ElementFilterEnabled", "ElementFilterState"],
                "Mod/Sketcher": ["VisualisationTrackingFilter", "ExtendedConstraintInformation", "HideInternalAlignment", "AutoRemoveRedundants"],
                "Mod/Sketcher/Elements": ["ExtendedNaming"]}


def reset_panel_params():
    """The panel's parameters back to their defaults (a step may have changed them; the next case starts afresh)."""
    for path, names in PANEL_PARAMS.items():
        g = App.ParamGet("User parameter:BaseApp/Preferences/" + path)
        for n in names:
            for rm in (g.RemBool, g.RemInt):
                try:
                    rm(n)
                except Exception:
                    pass


def panel_list(which):
    name = {"constraints": "listWidgetConstraints", "elements": "listWidgetElements"}[which]
    import gc, shiboken6
    gc.collect()   # wrappers of an earlier edit's widgets, which a new one may reuse the address of
    for w in mw.findChildren(QtWidgets.QListWidget):
        if shiboken6.isValid(w) and w.objectName() == name and w.isVisible():
            return w
    raise RuntimeError("no %s list in the task panel" % which)


def panel_child(which, name):
    lw = panel_list(which)
    # (findChild may hand back the wrapper of a deleted widget of an earlier edit at the same address)
    import shiboken6
    w = next((x for x in mw.findChildren(QtWidgets.QWidget) if shiboken6.isValid(x) and x.objectName() == name
              and lw.parentWidget().isAncestorOf(x)), None)
    if w is None:
        raise RuntimeError("no %s beside the %s list" % (name, which))
    return w


def filter_list(which):
    """The filter button's check list (ConstraintFilterList / ElementFilterList, the QWidgetAction's default widget)."""
    import gc, shiboken6
    gc.collect()
    cls = {"constraints": "SketcherGui::ConstraintFilterList", "elements": "SketcherGui::ElementFilterList"}[which]
    found = [w for w in app.allWidgets() if shiboken6.isValid(w) and w.metaObject().className() == cls]
    if os.environ.get("FCSKETCH_TRACE"):
        with open(os.path.join(OUT, "trace.log"), "a") as f:
            f.write("  %d %s\n" % (len(found), cls))
    if not found:
        raise RuntimeError("no %s" % cls)
    return found[-1]


class _Probe(QtWidgets.QStyledItemDelegate):
    """TaskSketcherElements' ElementItemDelegate::subControlRect, measured with the list's own style and options."""
    def rect(self, lw, row, sub):
        item = lw.item(row)
        opt = QtWidgets.QStyleOptionViewItem()
        opt.initFrom(lw)
        opt.rect = lw.visualItemRect(item)
        opt.decorationSize = lw.iconSize()
        opt.showDecorationSelected = True
        self.initStyleOption(opt, lw.model().index(row, 0))
        st = lw.style()
        cb = st.subElementRect(QtWidgets.QStyle.SE_CheckBoxIndicator, opt, lw)
        cb.moveTo(4, opt.rect.top() + (opt.rect.height() - cb.height()) // 2)
        if sub == "check":
            return cb
        dec = st.subElementRect(QtWidgets.QStyle.SE_ItemViewItemDecoration, opt, lw).translated(cb.right() + 4, 0)
        k = ["edge", "start", "end", "mid", "label"].index(sub)
        r = dec.translated((dec.width() + 4) * k, 0)
        if sub == "label":
            r.setRight(opt.rect.right())
        return r


_probe = _Probe()
MODS = {"ctrl": QtCore.Qt.ControlModifier, "shift": QtCore.Qt.ShiftModifier, None: QtCore.Qt.NoModifier}


def menu_entries(m):
    out = []
    for a in m.actions():
        if a.isSeparator():
            out.append("sep")
        else:
            out.append({"text": a.text(), "enabled": a.isEnabled(), "bold": m.defaultAction() is a, "shortcut": a.shortcut().toString(),
                        **({"sub": menu_entries(a.menu())} if a.menu() else {})})
    return out


def run_menu(pick, record):
    """The context menu the list pops up (QMenu::exec): what it holds, then the entry named `pick` (or none)."""
    state = {"done": False}

    def handle():
        m = app.activePopupWidget()
        if not isinstance(m, QtWidgets.QMenu):
            m = next((w for w in app.topLevelWidgets() if isinstance(w, QtWidgets.QMenu) and w.isVisible()), None)
        if m is None:
            state["tries"] = state.get("tries", 0) + 1
            if state["tries"] < 100:
                QtCore.QTimer.singleShot(50, handle)
            return
        state["done"] = True
        if record is not None:
            record.append(menu_entries(m))
        act = next((a for a in m.actions() if not a.isSeparator() and a.text() == pick), None) if pick else None
        m.hide()
        if act is not None and act.isEnabled():
            act.trigger()
    QtCore.QTimer.singleShot(50, handle)
    return state


def panel_step(st, panel_record):
    which = st["panel"]
    lw = panel_list(which) if "row" in st or "menu" in st or "empty" in st else None
    mod = MODS[st.get("mod")]
    if "row" in st:
        row = st["row"]
        item = lw.item(row)
        lw.scrollToItem(item)
        pump(2)
        vp = lw.viewport()
        if which == "elements":
            pos = _probe.rect(lw, row, st.get("sub", "label")).center()
        else:
            pos = lw.visualItemRect(item).center()
        if "check" in st:                     # the row's check box (a constraint's virtual space)
            item.setCheckState(QtCore.Qt.Checked if st["check"] else QtCore.Qt.Unchecked)
        elif "menu" in st:                    # a right click on the row, and an entry of its context menu
            from PySide6.QtTest import QTest
            # the menu is handled from a timer: QMenu::exec runs its own event loop
            state = run_menu(st["menu"], panel_record.setdefault("menus", []) if st.get("record") else None)
            QTest.mousePress(vp, QtCore.Qt.RightButton, mod, pos)
            QTest.mouseRelease(vp, QtCore.Qt.RightButton, mod, pos)
            wait(150)
            if not state["done"]:
                ev = QtGui.QContextMenuEvent(QtGui.QContextMenuEvent.Mouse, pos, vp.mapToGlobal(pos))
                QtWidgets.QApplication.sendEvent(vp, ev)
            wait(250)
        elif st.get("dblclick"):
            from PySide6.QtTest import QTest
            QTest.mouseDClick(vp, QtCore.Qt.LeftButton, mod, pos)
            wait(250)
        else:
            from PySide6.QtTest import QTest
            # the pointer moves onto the row first, as a real one does (TaskSketcherElements' itemEntered: focusItemIndex)
            QTest.mouseMove(vp, pos)
            wait(60)
            QTest.mouseClick(vp, QtCore.Qt.LeftButton, mod, pos)
            wait(120)
        if "rename" in st:                    # F2 (or the editor a double click opened), the text, Return
            if not any(isinstance(w, QtWidgets.QLineEdit) and w.isVisible() for w in lw.viewport().findChildren(QtWidgets.QLineEdit)):
                lw.setCurrentItem(item)
                for t in (QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease):
                    QtWidgets.QApplication.sendEvent(lw, QtGui.QKeyEvent(t, QtCore.Qt.Key_F2, QtCore.Qt.NoModifier, ""))
                wait(120)
            ed = next((w for w in lw.viewport().findChildren(QtWidgets.QLineEdit) if w.isVisible()), None)
            if ed is None:
                raise RuntimeError("no editor for row %d" % row)
            ed.selectAll()
            ed.insert(st["rename"])
            for t in (QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease):
                QtWidgets.QApplication.sendEvent(ed, QtGui.QKeyEvent(t, QtCore.Qt.Key_Return, QtCore.Qt.NoModifier, "\r"))
            wait(150)
    elif "empty" in st:                       # a click on the list's empty part
        from PySide6.QtTest import QTest
        vp = lw.viewport()
        QTest.mouseClick(vp, QtCore.Qt.LeftButton, mod, QtCore.QPoint(vp.width() // 2, vp.height() - 3))
        wait(120)
    elif "filter" in st:                      # an item of the filter's check list
        fl = filter_list(which)
        for i in range(fl.count()):
            if fl.item(i).text().strip().lstrip("- ") == st["filter"]:
                it = fl.item(i)
                # a user's click: Checked becomes Unchecked, anything else Checked
                want = st.get("checked")
                if want is None:
                    want = it.checkState() != QtCore.Qt.Checked
                it.setCheckState(QtCore.Qt.Checked if want else QtCore.Qt.Unchecked)
                break
        else:
            raise RuntimeError("no filter %r" % st["filter"])
        wait(120)
    elif "filterBox" in st:
        b = panel_child(which, "filterBox")
        if b.isChecked() != bool(st["filterBox"]):
            b.click()
        wait(120)
    elif "setting" in st:                     # an action of the Settings button's menu
        acts = panel_child(which, "settingsButton").actions()
        a = next(a for a in acts if a.text() == st["setting"])
        if st.get("checked") is None or a.isChecked() != bool(st["checked"]):
            a.trigger()
        wait(120)
    elif "button" in st:                      # showHideButton
        panel_child(which, st["button"]).click()
        wait(150)


def panel_out(doc):
    out = {}
    try:
        lc = panel_list("constraints")
        out["constraints"] = [{"text": lc.item(i).text(), "hidden": lc.item(i).isHidden(), "checked": lc.item(i).checkState() == QtCore.Qt.Checked,
                               "selected": lc.item(i).isSelected(), "tip": lc.item(i).toolTip() or ""} for i in range(lc.count())]
    except RuntimeError:
        pass
    try:
        le = panel_list("elements")
        out["elements"] = [{"id": le.item(i).data(QtCore.Qt.UserRole), "hidden": le.item(i).isHidden(), "selected": le.item(i).isSelected()}
                           for i in range(le.count())]
    except RuntimeError:
        pass
    sel = []
    for o in Gui.Selection.getSelectionEx(doc.Name, 0):
        for n in o.SubElementNames:
            sel.append(n.split(".")[-1])
    out["selection"] = sorted(sel)
    return out


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
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)  # the last case's spin boxes
    ovp_before = {cpp(w) for w in ovp_boxes()}
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
        else:
            geo = Part.ArcOfCircle(Part.Circle(V(g["center"]), App.Vector(0, 0, 1), g["radius"]), g["start_angle"], g["end_angle"])
        sk.addGeometry(geo, bool(g.get("construction")))
    for c in setup.get("constraints", []):
        args = list(c["args"]) + ([c["value"]] if "value" in c else [])
        i = sk.addConstraint(Sketcher.Constraint(c["type"], *args))
        # a setup constraint's states, as the part file writes them (name=, driving=False, active=False,
        # virtual_space=True, a value bound to an expression)
        if c.get("name"):
            sk.renameConstraint(i, c["name"])
        if c.get("driving") is False:
            sk.setDriving(i, False)
        if c.get("active") is False:
            sk.setActive(i, False)
        if c.get("virtual_space"):
            sk.setVirtualSpace(i, True)
        if c.get("expr"):
            sk.setExpression("Constraints[%d]" % i, c["expr"])
    doc.recompute()
    old_params = set_params(case.get("params") or {})
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

    panel_record = {}
    current["msgbox"] = case.get("msgbox")
    for st in case["steps"]:
        if os.environ.get("FCSKETCH_TRACE"):
            with open(os.path.join(OUT, "trace.log"), "a") as f:
                f.write("%s %s\n" % (case["name"], json.dumps(st)))
        if "cmd" in st:
            current["dialog"] = st.get("dialog")
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
        elif "type" in st:
            # text typed where the keyboard focus is: an on-view parameter's spin box takes digits, '-', '.' and ','
            # (DrawSketchKeyboardManager), and passes other keys on to the 3D view
            for ch in st["type"]:
                w = app.focusWidget() or vp
                for t in (QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease):
                    QtWidgets.QApplication.sendEvent(w, QtGui.QKeyEvent(t, char_key(ch), QtCore.Qt.NoModifier, ch))
                wait(40)
            wait(80)
        elif "fkey" in st:
            # a key to the focus widget (Return, Tab, Escape, Backspace in an on-view parameter), with "ctrl": true
            # for Ctrl+Return (finishEditingOnAllOVPs)
            key = st["fkey"]
            qk = KEYS.get(key) or getattr(QtCore.Qt, "Key_" + key.upper())
            mod = QtCore.Qt.ControlModifier if st.get("ctrl") else QtCore.Qt.NoModifier
            text = {"Return": "\r", "Tab": "\t", "Escape": "\x1b", "Backspace": "\b"}.get(key, key if len(key) == 1 else "")
            w = app.focusWidget() or vp
            for t in (QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease):
                QtWidgets.QApplication.sendEvent(w, QtGui.QKeyEvent(t, qk, mod, text))
            wait(100)
        elif "widget" in st:
            # a control of the tool's widget (SketcherToolDefaultWidget, in the Tool Parameters box): checkBoxTS1..4,
            # comboBox1..3, parameterOne..Ten, set as a click or an entry there sets it
            set_tool_widget(st["widget"])
            wait(120)
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
        elif "panel" in st:
            # the task panel's lists, filters and settings (sketchcases-panels.json)
            panel_step(st, panel_record)
    pump(6)
    res["cases"][case["name"]] = {"geometry": geo_out(sk), "constraints": cons_out(sk), "message": task_message(),
                                  "report": report_text()[report_at:]}
    if case.get("plate"):
        ext, refs = ext_out(sk)
        res["cases"][case["name"]].update({"external": ext, "external_geometry": refs})
    tw = tool_widget_out()
    if tw is not None:
        res["cases"][case["name"]]["tool_widget"] = tw
    res["cases"][case["name"]]["ovp"] = ovp_out(ovp_before)
    if os.environ.get("FCSKETCH_DEBUG"):
        res["cases"][case["name"]]["debug"] = {
            "focus": [app.focusWidget().metaObject().className() if app.focusWidget() else None,
                      app.focusWidget().parentWidget().metaObject().className() if app.focusWidget() and app.focusWidget().parentWidget() else None],
            "spinboxes": [[w.metaObject().className(), w.parentWidget().metaObject().className() if w.parentWidget() else None,
                           w.isVisible(), w.hasFocus(), (w.findChild(QtWidgets.QLineEdit).text() if w.findChild(QtWidgets.QLineEdit) else "")]
                          for w in mw.findChildren(QtWidgets.QAbstractSpinBox) if w.isVisible()]}
    if any("panel" in st for st in case["steps"]) or "panel" in (case.get("check") or []):
        res["cases"][case["name"]]["panel"] = {**panel_out(doc), **panel_record}
    Gui.ActiveDocument.resetEdit()
    pump(6)
    unset_params(old_params)
    reset_panel_params()


def chrome_and_cases():
    mw.resize(1280, 800)
    mw.show()
    # the window active, so that widgets take the keyboard focus (fcsketch.py maps it on the xvfb screen)
    mw.activateWindow()
    mw.raise_()
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
            "MarkerSize", "EditSketcherFontSize", "ConstraintSymbolSize", "DefaultShapePointSize"],
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

# SPDX-License-Identifier: LGPL-2.1-or-later
# Runs inside FreeCAD's GUI (fctechdraw_annot.py starts it under fclaunch, windows kept off the screen): what the real
# TechDraw workbench does with its annotation tools, for the TechDraw page to be compared with. Writes
# fctechdraw_annot.json into FCGUI_OUT:
#   states_*          the Add Lines, Add Vertices, Centerlines and Remove Cosmetic Object entries (greyed or not) and the
#                     Annotation, Centerlines and Decoration toolbars' buttons, for a selection of nothing, a view, an edge,
#                     two edges, two vertices, a face, a cosmetic edge
#   cosvertex_*       TechDraw_CosmeticVertex: the panel, the X and Y typed, OK; the view's CosmeticVertexes, the undo step
#   midpoints_*, quadrants_*   TechDraw_Midpoints, TechDraw_Quadrants on an edge and on a circle
#   cosline_*         TechDraw_2PointCosmeticLine on two vertices: the panel, a coordinate changed, OK; then its edit panel
#   coscircle_*       TechDraw_CosmeticCircle on two vertices: the panel (circle, arc), OK; then its edit panel
#   clines_*          TechDraw_2LineCenterLine, TechDraw_2PointCenterLine, TechDraw_FaceCenterLine: the panel, its values
#                     changed (shifts, rotation, extension, orientation, weight, style), OK, Cancel (which undoes the creation)
#   decorate_*        TechDraw_DecorateLine on an HLR edge, a cosmetic edge and a centre line: the panel (and the
#                     Restore Invisible Lines box), the values changed, OK, Cancel; the view's GeomFormats
#   eraser_*          TechDraw_CosmeticEraser on a cosmetic edge, a centre line and a cosmetic vertex
#   props_View        the property view of the view once it holds cosmetic geometry
#   page_svg, page_dxf   the page exported with the cosmetic geometry on the view
#   undo_names        the document's undo steps at the end
import json
import os
import tempfile
import time
import traceback

import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtCore, QtGui, QtWidgets

OUT = os.environ["FCGUI_OUT"]
BREPS = os.environ["FCTECHDRAW_BREPS"]
mw = Gui.getMainWindow()
app = QtWidgets.QApplication.instance()
res = {"errors": {}}
mw.resize(1280, 800)
V = App.Vector
doc = None


def save():
    json.dump(res, open(os.path.join(OUT, "fctechdraw_annot.json"), "w"), indent=1, default=repr)


def bail():
    res["errors"]["hung"] = "stopped after 1500 s"
    save()
    os._exit(0)


QtCore.QTimer.singleShot(1500000, bail)


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
    save()


def close_dialogs():
    out = []
    for w in app.topLevelWidgets():
        if isinstance(w, QtWidgets.QMessageBox) and w.isVisible():
            out.append({"title": w.windowTitle(), "text": w.text(), "buttons": [b.text() for b in w.buttons()]})
            yes = [b for b in w.buttons() if b.text().replace("&", "") in ("Yes",)]
            (yes[0].click() if yes else w.reject())
    return out


def watch_dialogs(holder):
    t = QtCore.QTimer()

    def tick():
        d = close_dialogs()
        if d:
            holder.setdefault("dialogs", []).extend(d)
    t.timeout.connect(tick)
    t.start(200)
    return t


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
        d = {"text": a.text(), "name": a.objectName() or a.data(), "enabled": a.isEnabled(), "tip": a.toolTip()}
        sub = a.menu()
        if sub is not None and depth < 4:
            d["menu"] = dump_menu(sub, depth + 1)
        out.append(d)
    return out


def menus():
    for a in mw.menuBar().actions():
        if a.text().replace("&", "") == "TechDraw":
            return dump_menu(a.menu())
    return []


def toolbars():
    out = []
    for tb in mw.findChildren(QtWidgets.QToolBar):
        if not tb.windowTitle().startswith("TechDraw"):
            continue
        row = {"title": tb.windowTitle(), "buttons": []}
        for a in tb.actions():
            if a.isSeparator() or not a.isVisible():
                continue
            w = tb.widgetForAction(a)
            b = {"name": a.objectName() or "", "text": a.text(), "enabled": a.isEnabled()}
            if a.menu() is not None:
                b["menu"] = dump_menu(a.menu())
            if isinstance(w, QtWidgets.QToolButton) and w.menu() is not None and "menu" not in b:
                b["menu"] = dump_menu(w.menu())
            row["buttons"].append(b)
        out.append(row)
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
                d["items"] = [w.itemText(i) for i in range(w.count())]
                d["current"] = w.currentText()
            elif isinstance(w, QtWidgets.QAbstractSpinBox):
                d["text"] = w.text()
            elif isinstance(w, QtWidgets.QLineEdit):
                d["text"] = w.text()
            elif isinstance(w, QtWidgets.QListWidget):
                d["items"] = [w.item(i).text() for i in range(w.count())]
            elif isinstance(w, QtWidgets.QTreeWidget):
                d["items"] = [w.topLevelItem(i).text(0) for i in range(w.topLevelItemCount())]
            elif isinstance(w, QtWidgets.QGroupBox):
                d["text"] = w.title()
            elif cls.endswith("TaskHeader") or cls == "QSint::TaskHeader":
                d["text"] = " ".join(lbl.text() for lbl in w.findChildren(QtWidgets.QLabel) if lbl.text())
            elif cls == "Gui::ColorButton":
                d["color"] = w.color().name()
            else:
                continue
            items.append(d)
        items.sort(key=lambda d: (d["y"], d["x"]))
        out.append(items)
    return out


def click_button(text):
    for b in mw.findChildren(QtWidgets.QAbstractButton):
        if b.isVisible() and b.text().replace("&", "") == text:
            b.click()
            pump(1.0)
            return True
    return False


def child(name, cls=QtWidgets.QWidget):
    for w in mw.findChildren(cls, name):
        if w.isVisible():
            return w
    return None


def set_quantity(name, text):
    """A Gui::QuantitySpinBox typed into, as a person does."""
    w = child(name)
    if w is None:
        return False
    le = w.lineEdit()
    le.selectAll()
    le.setText(text)
    pump(0.2)
    le.editingFinished.emit()
    pump(0.5)
    return True


def close_task():
    if Gui.Control.activeDialog():
        Gui.Control.closeDialog()
        pump(0.5)


def val(v):
    if isinstance(v, (bool, int, float, str, type(None))):
        return v if not isinstance(v, str) or len(v) < 4000 else v[:4000] + "..."
    if isinstance(v, App.Vector):
        return [v.x, v.y, v.z]
    if isinstance(v, App.Units.Quantity):
        return v.Value
    if isinstance(v, App.Placement):
        return {"base": val(v.Base), "rotation": list(v.Rotation.Q)}
    if isinstance(v, App.DocumentObject):
        return v.Name
    if isinstance(v, (list, tuple)):
        return [val(x) for x in v]
    if isinstance(v, dict):
        return {str(k): val(x) for k, x in v.items()}
    s = str(v)
    return s if len(s) < 2000 else s[:2000] + "..."


def obj_attrs(o):
    out = {}
    for a in dir(o):
        if a.startswith("_") or a in ("clone", "copy"):
            continue
        try:
            x = getattr(o, a)
        except Exception:
            continue
        if callable(x):
            continue
        out[a] = val(x)
    return out


def view_state(v):
    n = 0
    while True:
        try:
            v.getEdgeByIndex(n)
        except Exception:
            break
        n += 1
    nv = 0
    while True:
        try:
            v.getVertexByIndex(nv)
        except Exception:
            break
        nv += 1
    edges = []
    for i in range(n):
        e = v.getEdgeByIndex(i)
        edges.append({"curve": type(e.Curve).__name__, "start": val(e.Vertexes[0].Point), "end": val(e.Vertexes[-1].Point)})
    verts = [val(v.getVertexByIndex(i).Point) for i in range(nv)]
    return {"CosmeticVertexes": [obj_attrs(c) for c in v.CosmeticVertexes],
            "CosmeticEdges": [obj_attrs(c) for c in v.CosmeticEdges],
            "CenterLines": [obj_attrs(c) for c in v.CenterLines],
            "GeomFormats": [obj_attrs(c) if not isinstance(c, (str, int, float)) else c for c in v.GeomFormats],
            "edges": edges, "vertices": verts}


def new_undo(before):
    names = list(doc.UndoNames)
    n = len(names) - len(before)
    return {"head": names[:max(n, 0)], "all": names[:6]}


def settle(sec=1.5):
    pump(sec)
    doc.recompute()
    pump(0.8)


def select(sels):
    Gui.Selection.clearSelection()
    for s in sels:
        if isinstance(s, tuple):
            Gui.Selection.addSelection(doc.Name, s[0], s[1])
        else:
            Gui.Selection.addSelection(doc.Name, s)
    pump(0.4)


def run_tool(cmd, sels, edit=None, ok=True, wait=2.0):
    """Select sels, run cmd, record the panel, call edit() (typing into it), then OK (or Cancel when ok is False)."""
    select(sels)
    undo = list(doc.UndoNames)
    holder = {}
    t = watch_dialogs(holder)
    out = {"selection": [[x.ObjectName, list(x.SubElementNames)] for x in Gui.Selection.getSelectionEx()]}
    Gui.runCommand(cmd, 0)
    pump(wait)
    out["dialog_open"] = bool(Gui.Control.activeDialog())
    out["panel"] = task_widgets()
    out["view_after_open"] = view_state(doc.getObject("View"))
    out["undo_after_open"] = new_undo(undo)
    if edit is not None:
        out["edit"] = edit()
        pump(0.8)
        out["panel_after_edit"] = task_widgets()
        out["view_after_edit"] = view_state(doc.getObject("View"))
    if Gui.Control.activeDialog():
        out["button"] = click_button("OK" if ok else "Cancel")
    settle()
    t.stop()
    out["dialogs"] = holder.get("dialogs", [])
    out["undo"] = new_undo(undo)
    out["view"] = view_state(doc.getObject("View"))
    out["tasks_after"] = task_widgets()
    close_task()
    return out


def run_plain(cmd, sels):
    """A command without a panel (Midpoints, Quadrants, the eraser)."""
    select(sels)
    undo = list(doc.UndoNames)
    holder = {}
    t = watch_dialogs(holder)
    out = {"selection": [[x.ObjectName, list(x.SubElementNames)] for x in Gui.Selection.getSelectionEx()]}
    Gui.runCommand(cmd, 0)
    settle(1.5)
    t.stop()
    out["dialogs"] = holder.get("dialogs", [])
    out["undo"] = new_undo(undo)
    out["view"] = view_state(doc.getObject("View"))
    out["dialog_open"] = bool(Gui.Control.activeDialog())
    close_task()
    return out


KEEP_MENUS = ("Add Lines", "Add Vertices", "Centerlines/Threading", "Remove Cosmetic Object", "Hatching", "Annotations")


def states(sels):
    select(sels)
    m = [e for e in menus() if e.get("text") in KEEP_MENUS or e.get("name") == "TechDraw_CosmeticEraser"]
    tb = [t for t in toolbars() if t["title"] in ("TechDraw Annotation", "TechDraw Centerlines", "TechDraw Decoration")]
    return {"selection": [[x.ObjectName, list(x.SubElementNames)] for x in Gui.Selection.getSelectionEx()],
            "menu": m, "toolbars": tb}


def editor_rows():
    out = []
    for ed in mw.findChildren(QtWidgets.QTreeView):
        if ed.metaObject().className() != "Gui::PropertyEditor::PropertyEditor" or not ed.isVisible():
            continue
        model = ed.model()
        rows = []

        def walk(parent, depth):
            got = []
            for r in range(model.rowCount(parent)):
                if ed.isRowHidden(r, parent):
                    continue
                i0, i1 = model.index(r, 0, parent), model.index(r, 1, parent)
                v = model.data(i1)
                row = [{"depth": depth, "name": model.data(i0),
                        "value": v if isinstance(v, (str, int, float, bool, type(None))) else str(v)}]
                if depth < 1:
                    kids = walk(i0, depth + 1)
                    if not kids:
                        continue
                    row += kids
                got += row
            return got
        out.append(walk(QtCore.QModelIndex(), 0))
    return out


def property_view(obj):
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(obj)
    pump(0.6)
    out = {}
    tabs = [t for t in mw.findChildren(QtWidgets.QTabWidget)
            if t.parent() is not None and t.parent().metaObject().className() == "Gui::PropertyView"]
    for tw in tabs:
        cur = tw.currentIndex()
        for i in range(tw.count()):
            tw.setCurrentIndex(i)
            pump(0.3)
            out[tw.tabText(i).replace("&", "").lower()] = editor_rows()
        tw.setCurrentIndex(cur)
    Gui.Selection.clearSelection()
    return out


def find_edge(v, curve, near, tol=0.01):
    """The index of the view's edge of this curve type whose start point is near (x, y)."""
    i = 0
    while True:
        try:
            e = v.getEdgeByIndex(i)
        except Exception:
            return None
        p = e.Vertexes[0].Point
        if type(e.Curve).__name__ == curve and abs(p.x - near[0]) < tol and abs(p.y - near[1]) < tol:
            return i
        i += 1


def main():
    global doc
    pump(1.5)
    Gui.activateWorkbench("TechDrawWorkbench")
    pump(1.0)
    App.ParamGet("User parameter:BaseApp/Preferences/Document").SetInt("MaxUndoSize", 200)
    doc = App.newDocument("Unnamed")
    pump(0.5)
    import Part
    import TechDraw
    import TechDrawGui
    for name in ("plate", "bracket"):
        o = doc.addObject("Part::Feature", name)
        o.Shape = Part.read(os.path.join(BREPS, name + ".brep"))
    doc.recompute()
    Gui.SendMsgToActiveView("ViewFit")
    pump(0.5)
    Gui.runCommand("TechDraw_PageDefault", 0)
    settle(1.5)
    select(["plate"])
    Gui.runCommand("TechDraw_View", 0)
    pump(2.0)
    click_button("OK")
    settle(2.0)
    close_task()
    v = doc.getObject("View")
    v.Direction = V(0, 0, 1)
    v.recompute()
    settle(3.0)
    res["start"] = view_state(v)

    safe("states_none", lambda: states([]))
    safe("states_view", lambda: states(["View"]))
    safe("states_edge", lambda: states([("View", "Edge2")]))
    safe("states_two_edges", lambda: states([("View", "Edge0"), ("View", "Edge4")]))
    safe("states_two_vertices", lambda: states([("View", "Vertex1"), ("View", "Vertex6")]))
    safe("states_face", lambda: states([("View", "Face0")]))

    # cosmetic vertex
    def cosvertex():
        def edit():
            return {"x": set_quantity("dsbX", "5 mm"), "y": set_quantity("dsbY", "6 mm")}
        return run_tool("TechDraw_CosmeticVertex", ["View"], edit)
    safe("cosvertex", cosvertex)
    safe("cosvertex_cancel", lambda: run_tool("TechDraw_CosmeticVertex", ["View"], None, ok=False))
    # midpoints and quadrants
    safe("midpoints", lambda: run_plain("TechDraw_Midpoints", [("View", "Edge2")]))
    safe("quadrants", lambda: run_plain("TechDraw_Quadrants", [("View", "Edge5")]))
    safe("midpoints_nothing", lambda: run_plain("TechDraw_Midpoints", ["View"]))

    # cosmetic line through two vertices
    def cosline():
        def edit():
            return {"x2": set_quantity("qsbx2", "12 mm"), "y2": set_quantity("qsby2", "9 mm")}
        return run_tool("TechDraw_2PointCosmeticLine", [("View", "Vertex1"), ("View", "Vertex6")], edit)
    safe("cosline", cosline)
    safe("cosline_wrong", lambda: run_tool("TechDraw_2PointCosmeticLine", [("View", "Vertex1")], None))

    def cosline_edit():
        v = doc.getObject("View")
        i = find_edge(v, "Line", (-20.0, 15.0)) if False else None
        # the cosmetic line is the last cosmetic edge: its Edge index is the HLR edges' count + its place
        n = 0
        while True:
            try:
                v.getEdgeByIndex(n)
            except Exception:
                break
            n += 1
        idx = n - 1
        res["cosline_edge_index"] = idx

        def edit():
            return {"y1": set_quantity("qsby1", "-3 mm")}
        return run_tool("TechDraw_2PointCosmeticLine", [("View", "Edge%d" % idx)], edit)
    safe("cosline_edit", cosline_edit)

    # cosmetic circle: centre and a point on it
    def coscircle():
        def edit():
            return {"radius": set_quantity("qsbRadius", "3 mm")}
        return run_tool("TechDraw_CosmeticCircle", [("View", "Vertex6"), ("View", "Vertex8")], edit)
    safe("coscircle", coscircle)

    def coscircle_arc():
        def edit():
            b = child("rbArc", QtWidgets.QAbstractButton)
            if b is not None:
                b.click()
                pump(0.5)
            return {"arc": b is not None, "start": set_quantity("qsbStartAngle", "10 °"), "end": set_quantity("qsbEndAngle", "100 °")}
        return run_tool("TechDraw_CosmeticCircle", [("View", "Vertex1"), ("View", "Vertex4")], edit)
    safe("coscircle_arc", coscircle_arc)

    def coscircle_edit():
        v = doc.getObject("View")
        n = 0
        while True:
            try:
                v.getEdgeByIndex(n)
            except Exception:
                break
            n += 1
        res["coscircle_edge_index"] = n - 1

        def edit():
            return {"radius": set_quantity("qsbRadius", "6 mm")}
        return run_tool("TechDraw_CosmeticCircle", [("View", "Edge%d" % (n - 1))], edit)
    safe("coscircle_edit", coscircle_edit)

    # centre lines
    def cl_edit():
        return {"vshift": set_quantity("qsbVertShift", "1.5 mm"), "hshift": set_quantity("qsbHorizShift", "-2 mm"),
                "rotate": set_quantity("qsbRotate", "10 °"), "extend": set_quantity("qsbExtend", "2 mm"),
                "weight": set_quantity("dsbWeight", "0.7 mm")}
    safe("cl2lines", lambda: run_tool("TechDraw_2LineCenterLine", [("View", "Edge0"), ("View", "Edge4")], cl_edit))
    safe("cl2points", lambda: run_tool("TechDraw_2PointCenterLine", [("View", "Vertex3"), ("View", "Vertex8")], None))
    safe("cl2lines_cancel", lambda: run_tool("TechDraw_2LineCenterLine", [("View", "Edge2"), ("View", "Edge3")], cl_edit, ok=False))
    safe("cl2lines_wrong", lambda: run_tool("TechDraw_2LineCenterLine", [("View", "Edge2")], None))

    def clface():
        return run_tool("TechDraw_FaceCenterLine", [("View", "Face0")], None)
    safe("clface", clface)
    safe("clface_hole", lambda: run_tool("TechDraw_FaceCenterLine", [("View", "Face1")], None))

    def cl_edit_existing():
        v = doc.getObject("View")
        n = 0
        while True:
            try:
                v.getEdgeByIndex(n)
            except Exception:
                break
            n += 1
        # the centre lines are the last edges
        idx = n - len(v.CenterLines)
        res["cl_first_edge_index"] = idx
        return run_tool("TechDraw_2LineCenterLine", [("View", "Edge%d" % idx)], None)
    safe("cl_edit_existing", cl_edit_existing)

    # the property view with cosmetic geometry
    safe("props_View", lambda: property_view(doc.getObject("View")))

    # the page, exported
    page = doc.getObject("Page")
    tmp = tempfile.mkdtemp(prefix="fctechdrawannot")

    def svg():
        p = os.path.join(tmp, "page.svg")
        TechDrawGui.exportPageAsSvg(page, p)
        pump(0.5)
        return open(p, encoding="utf-8", errors="replace").read()
    safe("page_svg", svg)

    def dxf():
        p = os.path.join(tmp, "page.dxf")
        TechDraw.writeDXFPage(page, p)
        return open(p, encoding="utf-8", errors="replace").read()
    safe("page_dxf", dxf)

    # line decoration: Line Decoration on a cosmetic edge and a centre line, then on HLR edges
    def deco_edit():
        st = child("cb_Style", QtWidgets.QComboBox)
        info = {}
        if st is not None:
            st.setCurrentIndex(3)
            pump(0.5)
            info["style"] = st.currentText()
        info["weight"] = set_quantity("dsb_Weight", "0.9 mm")
        cb = child("cb_Visible", QtWidgets.QCheckBox)
        if cb is not None:
            cb.setChecked(False)
            pump(0.4)
            info["visible"] = False
        return info

    def deco_cosmetic():
        v = doc.getObject("View")
        st = view_state(v)
        first_ce = len(st["edges"]) - len(st["CosmeticEdges"]) - len(st["CenterLines"])
        first_cl = len(st["edges"]) - len(st["CenterLines"])
        return run_tool("TechDraw_DecorateLine", [("View", "Edge%d" % first_ce), ("View", "Edge%d" % first_cl)], deco_edit)
    safe("decorate_cosmetic", deco_cosmetic)
    safe("page_svg_formatted", svg)
    safe("page_dxf_formatted", dxf)
    safe("decorate_hlr", lambda: run_tool("TechDraw_DecorateLine", [("View", "Edge0"), ("View", "Edge1")], deco_edit))
    safe("decorate_view_only", lambda: run_tool("TechDraw_DecorateLine", ["View"], None))
    safe("page_svg_hlr_formatted", svg)

    # the eraser: the cosmetic line, a centre line and a cosmetic vertex
    def eraser():
        v = doc.getObject("View")
        st = view_state(v)
        n_edges, n_cl = len(st["edges"]), len(st["CenterLines"])
        first_ce = len(st["edges"]) - len(st["CosmeticEdges"]) - len(st["CenterLines"])
        first_cv = len(st["vertices"]) - len(st["CosmeticVertexes"])
        res["eraser_indexes"] = {"first_cosmetic_edge": first_ce, "first_centerline": n_edges - n_cl, "first_cosmetic_vertex": first_cv}
        return {"edge": run_plain("TechDraw_CosmeticEraser", [("View", "Edge%d" % first_ce)]),
                "centerline": run_plain("TechDraw_CosmeticEraser", [("View", "Edge%d" % (len(view_state(v)["edges"]) - len(v.CenterLines)))]),
                "vertex": run_plain("TechDraw_CosmeticEraser", [("View", "Vertex%d" % first_cv)]),
                "hlr_edge": run_plain("TechDraw_CosmeticEraser", [("View", "Edge0")])}
    safe("eraser", eraser)
    safe("undo_names", lambda: list(doc.UndoNames))
    # last: Cancel of an HLR edge's Line Decoration panel may take FreeCAD down
    safe("decorate_cancel", lambda: run_tool("TechDraw_DecorateLine", [("View", "Edge3")], deco_edit, ok=False))
    save()
    os._exit(0)


QtCore.QTimer.singleShot(500, main)

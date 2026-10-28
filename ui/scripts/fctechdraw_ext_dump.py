# SPDX-License-Identifier: LGPL-2.1-or-later
# Runs inside FreeCAD's GUI (fctechdraw_ext.py starts it under fclaunch): what the real TechDraw workbench's extension
# commands (CommandExtensionPack.cpp, CommandExtensionDims.cpp, TechDrawTools/CommandPositionSectionView.py, TechDraw_ShowAll)
# do, for the TechDraw page to be compared with. It uses the helpers of fctechdraw_annot_dump.py (run before main()), and
# writes fctechdraw_ext.json into FCGUI_OUT:
#   states_*       the extension menus' entries (greyed or not) for a few selections
#   pack_*         each Centerlines/Threading and Attributes command on a selection of vertices, edges or views: the view's
#                  edges and vertices (FreeCAD's numbering), what its cosmetic objects hold, the undo step, the dialogs
#   attrs_*        TechDraw_ExtensionSelectLineAttributes (its panel, the values typed, OK) and what the later commands made
#   dims_*         the dimension commands: the dimensions made (Type, References2D, X, Y, FormatSpec, Arbitrary), the cosmetic
#                  vertices and edges the oblique ones added, the undo step; the position, cascade, prefix and decimal commands
#   notes_*        TechDraw_ExtensionAreaAnnotation and TechDraw_ExtensionArcLengthAnnotation: the balloon and its view provider
#   section_*      TechDraw_ExtensionPositionSectionView on a section view and on an edge and a vertex
#   showall        TechDraw_ShowAll (Toggle Edge Visibility)
#   verts_*        TechDraw_ExtensionVertexAtIntersection
#   offset_vertex* TechDraw_CommandAddOffsetVertex (TechDrawTools/TaskAddOffsetVertex.py): the panel, OK and Cancel
#   customize_*    TechDraw_ExtensionCustomizeFormat (TaskCustomizeFormat) on a dimension and a balloon
import os

SRC = os.environ["FCTECHDRAW_ANNOT_DUMP"]
_src = open(SRC, encoding="utf-8").read().split("\ndef main():")[0]
exec(compile(_src, SRC, "exec"), globals())

EXT_MENUS = ("Attributes/Modifications", "Centerlines/Threading", "Format/Organize Dimensions", "Annotations", "Add Lines")


def add_view(name, part, direction, xdir=(1, 0, 0), x=100.0, y=100.0, scale=1.0):
    page = doc.getObject("Page")
    v = doc.addObject("TechDraw::DrawViewPart", name)
    page.addView(v)
    v.Source = [doc.getObject(part)]
    v.Direction = V(*direction)
    v.XDirection = V(*xdir)
    v.X, v.Y = x, y
    v.Scale = scale
    doc.recompute()
    settle(1.0)
    return v


def edge_list(v):
    out = []
    i = 0
    while True:
        try:
            e = v.getEdgeByIndex(i)
        except Exception:
            break
        out.append(e)
        i += 1
    return out


def objs_of(prefix):
    return [o.Name for o in doc.Objects if o.Name.startswith(prefix)]


DIM_KEYS = ("Name", "Type", "MeasureType", "References2D", "X", "Y", "FormatSpec", "Arbitrary", "ArbitraryTolerances", "EqualTolerance",
            "OverTolerance", "UnderTolerance", "FormatSpecOverTolerance", "FormatSpecUnderTolerance", "Label", "Rotation", "LockPosition")
BALLOON_KEYS = ("Name", "Text", "X", "Y", "OriginX", "OriginY", "BubbleShape", "EndType", "EndTypeScale", "ShapeScale", "KinkLength",
                "TextWrapLen", "ScaleType", "SourceView", "Rotation", "LockPosition", "Label")


def dim_state(d):
    out = {k: v for k, v in obj_attrs(d).items() if k in DIM_KEYS}
    for k in ("getRawValue",):
        try:
            out[k] = val(getattr(d, k)())
        except Exception as e:
            out[k] = "<%s>" % e
    return out


def snapshot(vname):
    v = doc.getObject(vname)
    st = view_state(v)
    st["dims"] = {o.Name: dim_state(o) for o in doc.Objects if o.TypeId == "TechDraw::DrawViewDimension"}
    st["balloons"] = {}
    for o in doc.Objects:
        if o.TypeId == "TechDraw::DrawViewBalloon":
            d = {k: v for k, v in obj_attrs(o).items() if k in BALLOON_KEYS}
            try:
                vo = o.ViewObject
                d["vp"] = {p: val(getattr(vo, p)) for p in ("Fontsize", "LineWidth", "LineVisible", "Color") if hasattr(vo, p)}
            except Exception as e:
                d["vp"] = "<%s>" % e
            st["balloons"][o.Name] = d
    st["sections"] = {o.Name: {"X": o.X.Value, "Y": o.Y.Value} for o in doc.Objects if o.TypeId == "TechDraw::DrawViewSection"}
    st["lock"] = {o.Name: o.LockPosition for o in doc.Objects if o.isDerivedFrom("TechDraw::DrawViewPart")}
    try:
        st["showall"] = {o.Name: o.ViewObject.ShowAllEdges for o in doc.Objects if o.isDerivedFrom("TechDraw::DrawViewPart")}
    except Exception as e:
        st["showall"] = "<%s>" % e
    return st


def prefix_dialog_handler(holder, text):
    """The 'Prefix Text' QDialog of TechDraw_ExtensionInsertRepetition: type the text, accept."""
    t = QtCore.QTimer()

    def tick():
        for w in app.topLevelWidgets():
            if isinstance(w, QtWidgets.QDialog) and w.isVisible() and w.windowTitle() == "Prefix Text":
                holder.setdefault("dialogs", []).append({"title": w.windowTitle(), "widgets": [
                    (type(c).__name__, c.text() if hasattr(c, "text") else "") for c in w.findChildren(QtWidgets.QWidget)
                    if isinstance(c, (QtWidgets.QLabel, QtWidgets.QLineEdit, QtWidgets.QAbstractButton))]})
                for e in w.findChildren(QtWidgets.QLineEdit):
                    e.setText(text)
                w.accept()
    t.timeout.connect(tick)
    t.start(150)
    return t


def run_ext(cmd, sels, vname="View", prefix_text=None, wait=1.5):
    select(sels)
    undo = list(doc.UndoNames)
    holder = {}
    t = watch_dialogs(holder)
    t2 = prefix_dialog_handler(holder, prefix_text) if prefix_text is not None else None
    out = {"selection": [[x.ObjectName, list(x.SubElementNames)] for x in Gui.Selection.getSelectionEx()],
           "objects_before": [o.Name for o in doc.Objects]}
    Gui.runCommand(cmd, 0)
    settle(wait)
    t.stop()
    if t2:
        t2.stop()
    out["dialogs"] = holder.get("dialogs", [])
    out["undo"] = new_undo(undo)
    out["state"] = snapshot(vname)
    out["new_objects"] = [o.Name for o in doc.Objects if o.Name not in out["objects_before"]]
    out["dialog_open"] = bool(Gui.Control.activeDialog())
    close_task()
    return out


def menus_state(sels):
    select(sels)
    m = [e for e in menus() if e.get("text") in EXT_MENUS]
    tb = [t for t in toolbars() if t["title"] in ("TechDraw Attributes", "TechDraw Centerlines", "TechDraw Extend Dimensions")]
    return {"selection": [[x.ObjectName, list(x.SubElementNames)] for x in Gui.Selection.getSelectionEx()], "menu": m, "toolbars": tb}


def vertex_at(v, p, tol=0.01):
    i = 0
    while True:
        try:
            q = v.getVertexByIndex(i).Point
        except Exception:
            return None
        if abs(q.x - p[0]) < tol and abs(q.y - p[1]) < tol:
            return i
        i += 1


def main():
    global doc
    pump(1.5)
    Gui.activateWorkbench("TechDrawWorkbench")
    pump(1.0)
    App.ParamGet("User parameter:BaseApp/Preferences/Document").SetInt("MaxUndoSize", 300)
    doc = App.newDocument("Unnamed")
    pump(0.5)
    import Part
    import TechDraw
    import TechDrawGui
    for name in ("plate", "flange", "shaft"):
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
    res["start"] = snapshot("View")
    fl = add_view("Flange", "flange", (0, 0, 1), x=200, y=60)
    res["start_flange"] = snapshot("Flange")
    sf = add_view("ShaftF", "shaft", (0, -1, 0), x=60, y=150)
    res["start_shaftf"] = snapshot("ShaftF")
    st = add_view("ShaftT", "shaft", (0, 0, 1), x=200, y=150)
    res["start_shaftt"] = snapshot("ShaftT")

    safe("states_none", lambda: menus_state([]))
    safe("states_view", lambda: menus_state(["View"]))
    safe("states_vertices", lambda: menus_state([("View", "Vertex1"), ("View", "Vertex6")]))

    # ── CommandExtensionPack: circles, arcs, parallel and perpendicular lines ──
    safe("pack_circle2", lambda: run_ext("TechDraw_ExtensionDrawCosmCircle", [("View", "Vertex6"), ("View", "Vertex8")]))
    safe("pack_circle3", lambda: run_ext("TechDraw_ExtensionDrawCosmCircle3Points", [("View", "Vertex1"), ("View", "Vertex4"), ("View", "Vertex5")]))
    safe("pack_arc", lambda: run_ext("TechDraw_ExtensionDrawCosmArc", [("View", "Vertex6"), ("View", "Vertex8"), ("View", "Vertex4")]))
    safe("pack_parallel", lambda: run_ext("TechDraw_ExtensionLineParallel", [("View", "Edge2"), ("View", "Vertex8")]))
    safe("pack_perpendicular", lambda: run_ext("TechDraw_ExtensionLinePerpendicular", [("View", "Edge0"), ("View", "Vertex4")]))
    safe("pack_perpendicular_vertex_first", lambda: run_ext("TechDraw_ExtensionLinePerpendicular", [("View", "Vertex3"), ("View", "Edge3")]))
    safe("pack_parallel_bad", lambda: run_ext("TechDraw_ExtensionLineParallel", [("View", "Edge2"), ("View", "Edge3")]))
    safe("pack_circle_cl", lambda: run_ext("TechDraw_ExtensionCircleCenterLines", [("View", "Edge5"), ("View", "Edge1")]))
    safe("pack_circle_cl_line", lambda: run_ext("TechDraw_ExtensionCircleCenterLines", [("View", "Edge2")]))

    def cosmetic_edge_index(k):
        s = view_state(doc.getObject("View"))
        first = len(s["edges"]) - len(s["CosmeticEdges"]) - len(s["CenterLines"])
        return first + k

    ce = lambda k: ("View", "Edge%d" % cosmetic_edge_index(k))
    safe("pack_extend", lambda: run_ext("TechDraw_ExtensionExtendLine", [ce(3)]))
    safe("pack_shorten", lambda: run_ext("TechDraw_ExtensionShortenLine", [ce(4)]))
    safe("pack_extend_hlr", lambda: run_ext("TechDraw_ExtensionExtendLine", [("View", "Edge2")]))
    safe("pack_extend_circle", lambda: run_ext("TechDraw_ExtensionExtendLine", [ce(0)]))

    # a centre line to extend and to change
    safe("pack_cl_make", lambda: run_tool("TechDraw_2LineCenterLine", [("View", "Edge0"), ("View", "Edge4")], None))

    def cl_edge():
        s = view_state(doc.getObject("View"))
        return ("View", "Edge%d" % (len(s["edges"]) - len(s["CenterLines"])))
    safe("pack_extend_cl", lambda: run_ext("TechDraw_ExtensionExtendLine", [cl_edge()]))
    safe("pack_shorten_cl", lambda: run_ext("TechDraw_ExtensionShortenLine", [cl_edge()]))

    # toggle edge visibility, lock
    safe("showall", lambda: run_ext("TechDraw_ShowAll", ["View"]))
    safe("showall_back", lambda: run_ext("TechDraw_ShowAll", ["View"]))
    safe("lock", lambda: run_ext("TechDraw_ExtensionLockUnlockView", ["View"]))
    safe("lock_back", lambda: run_ext("TechDraw_ExtensionLockUnlockView", ["View", "Flange"]))

    # select line attributes: the panel, then the commands that use them
    def attrs_edit():
        info = {}
        st = child("cbLineStyle", QtWidgets.QComboBox)
        info["styles"] = [st.itemText(i) for i in range(st.count())] if st else None
        if st is not None:
            st.setCurrentIndex(4)
            pump(0.4)
            info["style"] = st.currentText()
        rb = child("rbThick", QtWidgets.QRadioButton)
        if rb is not None:
            rb.setChecked(True)
            pump(0.3)
            info["thick"] = rb.text()
        for n in ("sbSpacing", "sbStretch"):
            sb = child(n, QtWidgets.QDoubleSpinBox)
            if sb is not None:
                sb.setValue(12.0 if n == "sbSpacing" else 4.0)
                pump(0.3)
                info[n] = sb.value()
        return info
    safe("attrs_select", lambda: run_tool("TechDraw_ExtensionSelectLineAttributes", ["View"], attrs_edit))
    safe("attrs_change", lambda: run_ext("TechDraw_ExtensionChangeLineAttributes", [ce(3), cl_edge(), ("View", "Edge2")]))
    safe("attrs_extend", lambda: run_ext("TechDraw_ExtensionExtendLine", [ce(4)]))
    safe("attrs_circle", lambda: run_ext("TechDraw_ExtensionDrawCosmCircle", [("View", "Vertex2"), ("View", "Vertex3")]))
    safe("attrs_perpendicular", lambda: run_ext("TechDraw_ExtensionLinePerpendicular", [("View", "Edge3"), ("View", "Vertex0")]))

    # ── hole circle and the threads ──
    def flange_circles():
        out = []
        for i, e in enumerate(edge_list(doc.getObject("Flange"))):
            if type(e.Curve).__name__ == "Circle":
                out.append((i, round(e.Curve.Radius, 3)))
        return out
    res["flange_circles"] = flange_circles()
    holes = [("Flange", "Edge%d" % i) for i, r in res["flange_circles"] if abs(r - 3.0) < 0.01]
    safe("pack_holecircle", lambda: run_ext("TechDraw_ExtensionHoleCircle", holes, "Flange"))
    safe("pack_holecircle_three", lambda: run_ext("TechDraw_ExtensionHoleCircle", holes[:3], "Flange"))
    safe("pack_holecircle_two", lambda: run_ext("TechDraw_ExtensionHoleCircle", holes[:2], "Flange"))
    safe("pack_holecircle_cl", lambda: run_ext("TechDraw_ExtensionCircleCenterLines", holes[:1], "Flange"))

    def shaft_lines():
        out = []
        for i, e in enumerate(edge_list(doc.getObject("ShaftF"))):
            if type(e.Curve).__name__ == "Line":
                a, b = e.Vertexes[0].Point, e.Vertexes[-1].Point
                out.append((i, [round(a.x, 3), round(a.y, 3)], [round(b.x, 3), round(b.y, 3)]))
        return out
    res["shaft_lines"] = shaft_lines()
    vert = [(i, a, b) for i, a, b in res["shaft_lines"] if abs(a[0] - b[0]) < 0.001]
    res["shaft_vertical"] = vert
    left = [v for v in vert if v[1][0] < -9.0][0]
    right = [v for v in vert if v[1][0] > 9.0][0]
    thin_l = [v for v in vert if -7.0 < v[1][0] < 0.0][0]
    thin_r = [v for v in vert if 0.0 < v[1][0] < 7.0][0]
    pair = [("ShaftF", "Edge%d" % right[0]), ("ShaftF", "Edge%d" % left[0])]
    safe("pack_thread_hole_side", lambda: run_ext("TechDraw_ExtensionThreadHoleSide", pair, "ShaftF"))
    pair2 = [("ShaftF", "Edge%d" % thin_r[0]), ("ShaftF", "Edge%d" % thin_l[0])]
    safe("pack_thread_bolt_side", lambda: run_ext("TechDraw_ExtensionThreadBoltSide", pair2, "ShaftF"))
    safe("pack_thread_side_one", lambda: run_ext("TechDraw_ExtensionThreadBoltSide", pair[:1], "ShaftF"))
    circles = [("ShaftT", "Edge%d" % i) for i, e in enumerate(edge_list(doc.getObject("ShaftT"))) if type(e.Curve).__name__ == "Circle"]
    res["shaft_top_circles"] = circles
    safe("pack_thread_hole_bottom", lambda: run_ext("TechDraw_ExtensionThreadHoleBottom", circles[:1], "ShaftT"))
    safe("pack_thread_bolt_bottom", lambda: run_ext("TechDraw_ExtensionThreadBoltBottom", circles[1:2] or circles[:1], "ShaftT"))
    safe("pack_thread_bottom_line", lambda: run_ext("TechDraw_ExtensionThreadBoltBottom", [("View", "Edge2")]))

    # ── CommandExtensionDims ──
    def new_dims(before):
        return [o.Name for o in doc.Objects if o.TypeId == "TechDraw::DrawViewDimension" and o.Name not in before]

    def dim_names():
        return [o.Name for o in doc.Objects if o.TypeId == "TechDraw::DrawViewDimension"]

    made = {}

    def dimcmd(key, cmd, sels, **kw):
        before = dim_names()
        r = run_ext(cmd, sels, **kw)
        made[key] = new_dims(before)
        return r
    res["made"] = made
    safe("dims_chain_h", lambda: dimcmd("chain_h", "TechDraw_ExtensionCreateHorizChainDimension",
                                       [("View", "Vertex%d" % i) for i in (1, 3, 8, 4)]))
    safe("dims_chain_v", lambda: dimcmd("chain_v", "TechDraw_ExtensionCreateVertChainDimension",
                                       [("View", "Vertex%d" % i) for i in (5, 3, 6, 4)]))
    safe("dims_chain_o", lambda: dimcmd("chain_o", "TechDraw_ExtensionCreateObliqueChainDimension",
                                       [("View", "Vertex%d" % i) for i in (0, 8, 4)]))
    safe("dims_coord_h", lambda: dimcmd("coord_h", "TechDraw_ExtensionCreateHorizCoordDimension",
                                       [("View", "Vertex%d" % i) for i in (1, 3, 8, 4)]))
    safe("dims_coord_h_rev", lambda: dimcmd("coord_h_rev", "TechDraw_ExtensionCreateHorizCoordDimension",
                                           [("View", "Vertex%d" % i) for i in (4, 8, 3)]))
    safe("dims_coord_v", lambda: dimcmd("coord_v", "TechDraw_ExtensionCreateVertCoordDimension",
                                       [("View", "Vertex%d" % i) for i in (3, 5, 6, 4)]))
    safe("dims_coord_o", lambda: dimcmd("coord_o", "TechDraw_ExtensionCreateObliqueCoordDimension",
                                       [("View", "Vertex%d" % i) for i in (0, 8, 4)]))
    safe("dims_chamfer_h", lambda: dimcmd("chamfer_h", "TechDraw_ExtensionCreateHorizChamferDimension",
                                         [("View", "Vertex2"), ("View", "Vertex0")]))
    safe("dims_chamfer_v", lambda: dimcmd("chamfer_v", "TechDraw_ExtensionCreateVertChamferDimension",
                                         [("View", "Vertex0"), ("View", "Vertex2")]))
    safe("dims_chamfer_h_neg", lambda: dimcmd("chamfer_h_neg", "TechDraw_ExtensionCreateHorizChamferDimension",
                                             [("View", "Vertex5"), ("View", "Vertex2")]))
    safe("dims_arc", lambda: dimcmd("arc", "TechDraw_ExtensionCreateLengthArc", [("View", "Edge1")]))
    safe("dims_arc_line", lambda: dimcmd("arc_line", "TechDraw_ExtensionCreateLengthArc", [("View", "Edge2")]))
    safe("dims_chain_h_one", lambda: dimcmd("chain_h_one", "TechDraw_ExtensionCreateHorizChainDimension", [("View", "Vertex1")]))

    # position and cascade: move the dimensions about first, as a person does
    def scatter(names, which):
        for k, n in enumerate(names):
            d = doc.getObject(n)
            if which in ("x", "xy"):
                d.X = d.X.Value + 3.0 * (k + 1) * (-1 if k % 2 else 1)
            if which in ("y", "xy"):
                d.Y = d.Y.Value + 4.0 * (k + 1) * (-1 if k % 2 else 1)
        settle(0.8)
        return {n: [doc.getObject(n).X.Value, doc.getObject(n).Y.Value] for n in names}
    res["scatter"] = {}
    res["scatter"]["chain_h"] = scatter(made["chain_h"], "y")
    safe("dims_pos_h", lambda: run_ext("TechDraw_ExtensionPosHorizChainDimension", made["chain_h"]))
    res["scatter"]["chain_v"] = scatter(made["chain_v"], "x")
    safe("dims_pos_v", lambda: run_ext("TechDraw_ExtensionPosVertChainDimension", made["chain_v"]))
    res["scatter"]["chain_o"] = scatter(made["chain_o"], "xy")
    safe("dims_pos_o", lambda: run_ext("TechDraw_ExtensionPosObliqueChainDimension", made["chain_o"]))
    safe("dims_pos_none", lambda: run_ext("TechDraw_ExtensionPosHorizChainDimension", made["chain_v"][:1]))
    res["scatter"]["coord_h"] = scatter(made["coord_h"], "y")
    safe("dims_cascade_h", lambda: run_ext("TechDraw_ExtensionCascadeHorizDimension", made["coord_h"]))
    res["scatter"]["coord_v"] = scatter(made["coord_v"], "x")
    safe("dims_cascade_v", lambda: run_ext("TechDraw_ExtensionCascadeVertDimension", made["coord_v"]))
    res["scatter"]["coord_o"] = scatter(made["coord_o"], "xy")
    safe("dims_cascade_o", lambda: run_ext("TechDraw_ExtensionCascadeObliqueDimension", made["coord_o"]))

    # prefixes and decimals
    one = made["chain_h"][:1]
    two = made["chain_h"][1:3]
    safe("dims_prefix_diameter", lambda: run_ext("TechDraw_ExtensionInsertDiameter", one))
    safe("dims_prefix_square", lambda: run_ext("TechDraw_ExtensionInsertSquare", two))
    safe("dims_prefix_repeat", lambda: run_ext("TechDraw_ExtensionInsertRepetition", one, prefix_text="4"))
    safe("dims_prefix_remove", lambda: run_ext("TechDraw_ExtensionRemovePrefixChar", one + two))
    safe("dims_prefix_remove_again", lambda: run_ext("TechDraw_ExtensionRemovePrefixChar", one))
    safe("dims_decimal_up", lambda: run_ext("TechDraw_ExtensionIncreaseDecimal", one + two))
    safe("dims_decimal_down", lambda: run_ext("TechDraw_ExtensionDecreaseDecimal", one))

    def decimals_to_limit():
        out = []
        for _ in range(3):
            out.append(run_ext("TechDraw_ExtensionDecreaseDecimal", two[:1])["state"]["dims"][two[0]]["FormatSpec"])
        for _ in range(11):
            r = run_ext("TechDraw_ExtensionIncreaseDecimal", two[:1], wait=0.4)
        out.append(r["state"]["dims"][two[0]]["FormatSpec"])
        return out
    safe("dims_decimal_limits", decimals_to_limit)
    safe("dims_prefix_on_view", lambda: run_ext("TechDraw_ExtensionInsertDiameter", ["View"]))

    # annotations: area and arc length
    safe("notes_area", lambda: run_ext("TechDraw_ExtensionAreaAnnotation", [("View", "Face0")]))
    safe("notes_area_none", lambda: run_ext("TechDraw_ExtensionAreaAnnotation", [("View", "Edge0")]))
    safe("notes_arclength", lambda: run_ext("TechDraw_ExtensionArcLengthAnnotation", [("View", "Edge1"), ("View", "Edge3")]))
    safe("notes_arclength_circle", lambda: run_ext("TechDraw_ExtensionArcLengthAnnotation", [("View", "Edge5")]))

    # cosmetic intersection vertices, Offset Vertex (TechDrawTools) and Customize Format Label
    safe("verts_intersection_lines", lambda: run_ext("TechDraw_ExtensionVertexAtIntersection", [("View", "Edge2"), ("View", "Edge4")]))
    safe("verts_intersection_circle", lambda: run_ext("TechDraw_ExtensionVertexAtIntersection", [("View", "Edge2"), ("View", "Edge7")]))
    safe("verts_intersection_one", lambda: run_ext("TechDraw_ExtensionVertexAtIntersection", [("View", "Edge2")]))
    safe("verts_intersection_vertex", lambda: run_ext("TechDraw_ExtensionVertexAtIntersection", [("View", "Edge2"), ("View", "Vertex1")]))

    def offset_edit():
        info = {}
        for n, v in (("dSpinBoxX", 3.0), ("dSpinBoxY", -2.0)):
            w = child(n, QtWidgets.QDoubleSpinBox)
            if w is not None:
                w.setValue(v)
                pump(0.4)
                info[n] = w.value()
        le = child("le_SourceVertex", QtWidgets.QLineEdit)
        info["source"] = le.text() if le else None
        return info
    safe("offset_vertex", lambda: run_tool("TechDraw_CommandAddOffsetVertex", [("View", "Vertex8")], offset_edit))
    safe("offset_vertex_cancel", lambda: run_tool("TechDraw_CommandAddOffsetVertex", [("View", "Vertex3")], offset_edit, ok=False))

    def customize_edit():
        info = {}
        le = child("leFormat", QtWidgets.QLineEdit)
        lb = child("lbShowPreview", QtWidgets.QLabel)
        info["before"] = [le.text(), lb.text()]
        le.setText("%.1f mm")
        pump(0.4)
        info["typed"] = [le.text(), lb.text()]
        buttons = {}
        for b in mw.findChildren(QtWidgets.QPushButton):
            if b.isVisible() and b.objectName()[:2] == "pb" and len(b.objectName()) == 5 and b.objectName()[2] in "ABCDEF":
                buttons[b.objectName()] = [b.text(), b.toolTip()]
        info["buttons"] = buttons
        for n in ("pbA01", "pbC01"):
            b = child(n, QtWidgets.QPushButton)
            if b is not None:
                b.click()
                pump(0.3)
        info["clicked"] = [le.text(), lb.text()]
        return info

    def customize(name):
        r = run_tool("TechDraw_ExtensionCustomizeFormat", [name], customize_edit)
        r["after"] = {k: val(getattr(doc.getObject(name), k)) for k in ("FormatSpec", "Text") if hasattr(doc.getObject(name), k)}
        return r
    safe("customize_dim", lambda: customize("Dimension001"))
    safe("customize_balloon", lambda: customize("Balloon001"))

    # position section view: a section of a projection group's item (the command takes the group as the base), of a
    # single view (a DrawProjGroupItem outside a group: the Python command fails), and the edge and vertex form
    def make_group():
        page = doc.getObject("Page")
        g = doc.addObject("TechDraw::DrawProjGroup", "ProjGroup")
        page.addView(g)
        g.Source = [doc.getObject("plate")]
        front = g.addProjection("Front")
        front.Direction = V(0, -1, 0)
        front.XDirection = V(1, 0, 0)
        front.recompute()
        g.X, g.Y = 100.0, 150.0
        doc.recompute()
        settle(2.0)
        return {"group": [g.X.Value, g.Y.Value], "item": front.Name, "item_xy": [front.X.Value, front.Y.Value]}
    safe("section_group", make_group)

    def make_section(name, base, x, y):
        sec = doc.addObject("TechDraw::DrawViewSection", name)
        doc.getObject("Page").addView(sec)
        sec.BaseView = doc.getObject(base)
        sec.Source = doc.getObject(base).Source
        sec.SectionDirection = "Down"
        sec.SectionNormal = V(0, 1, 0)
        sec.SectionOrigin = V(0, 0, 0)
        sec.Direction = V(0, -1, 0)
        sec.XDirection = V(1, 0, 0)
        sec.Scale = 1.0
        doc.recompute()
        settle(2.0)
        sec.X, sec.Y = x, y
        settle(1.0)
        return {"name": name, "X": sec.X.Value, "Y": sec.Y.Value, "base": base,
                "base_xy": [doc.getObject(base).X.Value, doc.getObject(base).Y.Value]}
    safe("section_make", lambda: make_section("Section", "ProjItem", 160.0, 40.0))
    safe("section_pos", lambda: run_ext("TechDraw_ExtensionPositionSectionView", ["Section"]))

    def section_pair():
        sec = doc.getObject("Section")
        sec.X, sec.Y = 140.0, 52.0
        settle(1.5)
        n = 0
        es = []
        while True:
            try:
                es.append(sec.getEdgeByIndex(n))
                n += 1
            except Exception:
                break
        res["section_edges"] = [[i, type(e.Curve).__name__, val(e.Vertexes[0].Point), val(e.Vertexes[-1].Point)] for i, e in enumerate(es)]
        n = 0
        bv = []
        item = doc.getObject("ProjItem")
        while True:
            try:
                bv.append(item.getVertexByIndex(n).Point)
                n += 1
            except Exception:
                break
        res["item_vertices"] = [val(p) for p in bv]
        i = next(i for i, e in enumerate(es) if type(e.Curve).__name__ == "Line" and abs(e.Vertexes[0].Point.x - e.Vertexes[-1].Point.x) < 1e-6)
        res["section_edge_used"] = i
        return run_ext("TechDraw_ExtensionPositionSectionView", [("Section", "Edge%d" % i), ("ProjItem", "Vertex1")])
    safe("section_edge_vertex", section_pair)

    def section_oblique():
        sec = doc.getObject("Section")
        sec.X, sec.Y = 140.0, 52.0
        settle(1.0)
        i = next(i for i in range(20) if True)
        n = 0
        es = []
        while True:
            try:
                es.append(sec.getEdgeByIndex(n))
                n += 1
            except Exception:
                break
        j = next(j for j, e in enumerate(es) if type(e.Curve).__name__ == "Line" and abs(e.Vertexes[0].Point.y - e.Vertexes[-1].Point.y) < 1e-6)
        res["section_edge_used_h"] = j
        return run_ext("TechDraw_ExtensionPositionSectionView", [("Section", "Edge%d" % j), ("ProjItem", "Vertex2")])
    safe("section_edge_vertex_h", section_oblique)
    safe("section_make_single", lambda: make_section("SectionB", "View", 120.0, 40.0))
    safe("section_pos_single", lambda: run_ext("TechDraw_ExtensionPositionSectionView", ["SectionB"]))
    safe("section_pos_view", lambda: run_ext("TechDraw_ExtensionPositionSectionView", ["View"]))
    safe("undo_names", lambda: list(doc.UndoNames))
    save()
    os._exit(0)


QtCore.QTimer.singleShot(500, main)

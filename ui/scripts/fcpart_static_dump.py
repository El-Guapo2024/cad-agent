# SPDX-License-Identifier: LGPL-2.1-or-later
# Runs inside FreeCAD's GUI (fcpart_static.py starts it under fclaunch): what the real Part workbench shows for the commands
# that make a Part::Feature holding a shape (cad_agent/feature_part_static.py), for partcheck.mjs to compare the page with.
# Writes fcpart_static.json into FCGUI_OUT:
#   menus_selected      the Part menu with a Box selected (which entries are enabled)
#   cmd_*               each command run on a selection: the objects it made (Name, Label, TypeId), the inputs it hid, its
#                       undo step's name, the task panel it opened, its properties
#   crosssections_*     the Cross-sections panel: its widgets, the values after each plane and the Sections box
#   builder_*           the Shape builder panel in each mode (labels, enabled boxes), and what Create makes from a selection
#   check_*             the Check geometry panel: Settings page, Results page (message, tree rows), Shape Content
#   tree, props_*       the tree's rows and the property view of what the commands made
# The helpers are fcpart_dump.py's (its source up to main()), run here with the same names.
import os
from pathlib import Path

_src = (Path(os.environ.get("FCGUI_SCRIPTS", "")) / "fcpart_dump.py") if os.environ.get("FCGUI_SCRIPTS") else None
if _src is None or not _src.exists():
    _src = Path(globals().get("__file__", "")).with_name("fcpart_dump.py")
exec(compile(_src.read_text().split("\ndef main():")[0].replace('"fcpart.json"', '"fcpart_static.json"'), str(_src), "exec"))


def widget_values():
    """The open task panel's widgets with their values (task_widgets plus every spin box and check)."""
    return task_widgets()


def box(name, l=10, w=20, h=5, placement=None):
    o = doc.addObject("Part::Box", name)
    o.Length, o.Width, o.Height = l, w, h
    if placement is not None:
        o.Placement = placement
    doc.recompute()
    return o


def panel_texts():
    out = []
    for items in task_widgets():
        for d in items:
            if d.get("class") in ("QLabel", "QCheckBox", "QRadioButton", "QGroupBox", "QPushButton") and d.get("text"):
                out.append(d)
    return out


def set_radio(text):
    for b in mw.findChildren(QtWidgets.QRadioButton):
        if b.isVisible() and b.text().replace("&", "") == text:
            b.click()
            pump(0.4)
            return True
    return False


def set_check(text, on):
    for b in mw.findChildren(QtWidgets.QCheckBox):
        if b.isVisible() and b.text().replace("&", "").strip() == text:
            if b.isChecked() != on:
                b.click()
                pump(0.3)
            return True
    return False


def spin(name):
    for w in mw.findChildren(QtWidgets.QWidget):
        if w.objectName() == name and w.isVisible():
            return w
    return None


def cross_sections():
    box("BoxCs", 10, 20, 5)
    select("BoxCs")
    Gui.runCommand("Part_CrossSections", 0)
    pump(1.5)
    out = {"task": task_widgets(), "buttons": task_buttons()}
    values = {}
    for plane in ("XY", "XZ", "YZ"):
        set_radio(plane)
        values[plane] = {n: (spin(n).text() if spin(n) is not None else None) for n in ("position", "distance", "countSections")}
        values[plane]["sections"] = [b.isChecked() for b in mw.findChildren(QtWidgets.QGroupBox)
                                     if b.objectName() == "sectionsBox"]
    out["values"] = values
    # the sections box on (it is checked at the start), count and distance as the dialog derives them
    cb = [b for b in mw.findChildren(QtWidgets.QGroupBox) if b.objectName() == "sectionsBox"][0]
    out["sections_start"] = cb.isChecked()
    cb.setChecked(False)
    pump(0.3)
    out["sections_off"] = {n: (spin(n).text() if spin(n) is not None else None) for n in ("position", "distance", "countSections")}
    cb.setChecked(True)
    pump(0.3)
    set_radio("XZ")
    for n, v in (("countSections", 3),):
        s = spin(n)
        s.setValue(v)
        pump(0.3)
    out["xz_count3"] = {n: (spin(n).text() if spin(n) is not None else None) for n in ("position", "distance", "countSections")}
    set_check("On both sides", True)
    out["both"] = {n: (spin(n).text() if spin(n) is not None else None) for n in ("position", "distance", "countSections")}
    before = {o.Name for o in doc.Objects}
    undo = list(doc.UndoNames)
    click_button("OK")
    pump(1.5)
    doc.recompute()
    out["made"] = [dict(o, props=props_of(o["name"])) for o in objects() if o["name"] not in before]
    out["undo"] = [u for u in doc.UndoNames if u not in undo][:1] or doc.UndoNames[:1]
    out["shape"] = {o["name"]: {"edges": len(doc.getObject(o["name"]).Shape.Edges), "wires": len(doc.getObject(o["name"]).Shape.Wires),
                                "type": doc.getObject(o["name"]).Shape.ShapeType} for o in out["made"]}
    close_task()
    return out


def builder():
    b = box("BoxSb", 10, 20, 5)
    out = {"modes": {}, "made": {}}
    Gui.Selection.clearSelection()
    Gui.runCommand("Part_Builder", 0)
    pump(1.5)
    out["task"] = task_widgets()
    out["buttons"] = task_buttons()
    modes = ["Edge from vertices", "Wire from edges", "Face from vertices", "Face from edges", "Shell from faces", "Solid from shell"]
    picks = {"Edge from vertices": ["Vertex1", "Vertex8"], "Wire from edges": ["Edge2", "Edge10", "Edge6", "Edge12"],
             "Face from vertices": ["Vertex2", "Vertex4", "Vertex8", "Vertex6"], "Face from edges": ["Edge2", "Edge10", "Edge6", "Edge12"],
             "Shell from faces": ["Face1", "Face3", "Face5"]}
    for m in modes:
        set_radio(m)
        texts = {}
        for w in mw.findChildren(QtWidgets.QCheckBox):
            if w.isVisible() and w.text().replace("&", "") in ("Planar", "Refine shape", "All faces"):
                texts[w.text().replace("&", "")] = {"enabled": w.isEnabled(), "checked": w.isChecked()}
        label = [d.get("text") for items in task_widgets() for d in items if d.get("class") == "QLabel" and d.get("text")
                 and d["text"] != "Create Shape"]
        out["modes"][m] = {"boxes": texts, "labels": label, "checked_radios": [r.text() for r in mw.findChildren(QtWidgets.QRadioButton) if r.isChecked()]}
    # Create, from a selection of sub-elements: the object, its name and undo step
    for m in modes[:5]:
        set_radio(m)
        Gui.Selection.clearSelection()
        for s in picks[m]:
            Gui.Selection.addSelection(doc.Name, "BoxSb", s)
        pump(0.3)
        before = {o.Name for o in doc.Objects}
        undo = list(doc.UndoNames)
        holder = {}
        t = watch_dialogs(holder)
        click_button("Create")
        pump(1.0)
        doc.recompute()
        t.stop()
        out["made"][m] = {"objs": [dict(o, shape=doc.getObject(o["name"]).Shape.ShapeType, area=round(doc.getObject(o["name"]).Shape.Area, 6),
                                        placement=str(doc.getObject(o["name"]).Placement)) for o in objects() if o["name"] not in before],
                          "undo": [u for u in doc.UndoNames if u not in undo][:1], "dialogs": holder.get("dialogs", []),
                          "selection_after": [str(x) for x in Gui.Selection.getSelectionEx()]}
    # wrong selections: their messages
    out["wrong"] = {}
    for m, picks_ in (("Edge from vertices", ["Vertex1"]), ("Wire from edges", []), ("Face from vertices", ["Vertex1", "Vertex2"]),
                      ("Shell from faces", ["Face1"]), ("Solid from shell", [])):
        set_radio(m)
        Gui.Selection.clearSelection()
        for s in picks_:
            Gui.Selection.addSelection(doc.Name, "BoxSb", s)
        pump(0.3)
        holder = {}
        t = watch_dialogs(holder)
        click_button("Create")
        pump(1.0)
        t.stop()
        out["wrong"][m] = holder.get("dialogs", [])
    # Solid from shell: the shell object, whole
    set_radio("Solid from shell")
    shell = [o for o in doc.Objects if o.Name.startswith("Shell")][0]
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(shell)
    pump(0.3)
    before = {o.Name for o in doc.Objects}
    undo = list(doc.UndoNames)
    holder = {}
    t = watch_dialogs(holder)
    click_button("Create")
    pump(1.0)
    doc.recompute()
    t.stop()
    out["made"]["Solid from shell"] = {"objs": [dict(o, shape=doc.getObject(o["name"]).Shape.ShapeType, area=round(doc.getObject(o["name"]).Shape.Area, 6))
                                                for o in objects() if o["name"] not in before],
                                       "undo": [u for u in doc.UndoNames if u not in undo][:1], "dialogs": holder.get("dialogs", [])}
    close_task()
    return out


def check_geometry():
    out = {}
    b = box("BoxCg", 10, 20, 5)
    select("BoxCg")
    Gui.runCommand("Part_CheckGeometry", 0)
    pump(1.5)
    out["settings"] = {"task": task_widgets(), "buttons": task_buttons()}
    set_check("Run boolean operation check", True)
    click_button("Run Check")
    pump(2.0)
    out["results"] = {"task": task_widgets(), "buttons": task_buttons()}
    out["tree"] = check_tree()
    close_task()
    # an invalid shape: a self-intersecting wire made face, and a shell not closed
    import Part
    bad = doc.addObject("Part::Feature", "Bowtie")
    bad.Shape = Part.Face(Part.makePolygon([V(0, 0, 0), V(10, 10, 0), V(10, 0, 0), V(0, 10, 0), V(0, 0, 0)]))
    shell = doc.addObject("Part::Feature", "OpenShell")
    shell.Shape = Part.Shell(Part.makeBox(10, 10, 10).Faces[:5])
    doc.recompute()
    select("Bowtie", "OpenShell", "BoxCg")
    Gui.runCommand("Part_CheckGeometry", 0)
    pump(1.5)
    click_button("Run Check")
    pump(2.0)
    out["bad"] = {"task": task_widgets(), "tree": check_tree()}
    close_task()
    return out


def check_tree():
    rows = []
    for tv in mw.findChildren(QtWidgets.QTreeView):
        if tv.metaObject().className() == "QTreeView" and tv.isVisible() and tv.model() is not None and tv.model().columnCount() == 3:
            m = tv.model()

            def walk(parent, depth):
                for r in range(m.rowCount(parent)):
                    rows.append({"depth": depth, "cols": [m.data(m.index(r, c, parent)) for c in range(3)]})
                    walk(m.index(r, 0, parent), depth + 1)
            walk(QtCore.QModelIndex(), 0)
            rows.append({"header": [m.headerData(c, QtCore.Qt.Horizontal) for c in range(3)]})
    return rows


def main():
    global doc
    pump(1.5)
    Gui.activateWorkbench("PartWorkbench")
    pump(1.0)
    doc = App.newDocument("Unnamed")
    pump(0.5)
    safe("workbench", lambda: Gui.activeWorkbench().name())
    P = App.Placement(V(5, -3, 2), App.Rotation(30, 15, -10))
    box("Box", 10, 20, 5, P)
    select("Box")
    safe("menus_selected", menus)
    safe("toolbars_selected", toolbars)
    Gui.Selection.clearSelection()
    safe("menus_none", menus)
    safe("cmd_Part_SimpleCopy", lambda: run("Part_SimpleCopy", "Box"))
    safe("cmd_Part_TransformedCopy", lambda: run("Part_TransformedCopy", "Box"))
    safe("cmd_Part_ElementCopy", lambda: run("Part_ElementCopy", "Box"))
    safe("cmd_Part_ElementCopy_face", lambda: run("Part_ElementCopy", "Box", subs={"Box": ["Face3"]}))
    safe("cmd_Part_SimpleCopy_two", lambda: run("Part_SimpleCopy", "Box", "Box001"))
    # Convert to solid: a compound, a shell, a solid (ignored) and a face (ignored)
    c1, c2 = box("BoxA", 10, 10, 10), box("BoxB", 10, 10, 10, App.Placement(V(10, 0, 0), App.Rotation()))
    comp = doc.addObject("Part::Compound", "Comp")
    comp.Links = [c1, c2]
    doc.recompute()
    safe("cmd_Part_MakeSolid_compound", lambda: run("Part_MakeSolid", "Comp"))
    sh = doc.addObject("Part::Feature", "Sh")
    sh.Shape = Part.makeBox(10, 10, 10).Shells[0]
    doc.recompute()
    safe("cmd_Part_MakeSolid_shell", lambda: run("Part_MakeSolid", "Sh"))
    safe("cmd_Part_MakeSolid_solid", lambda: run("Part_MakeSolid", "BoxA"))
    safe("cmd_Part_MakeSolid_none", lambda: run("Part_MakeSolid"))
    # Set tolerance
    safe("cmd_Part_ToleranceSet", lambda: run("Part_ToleranceSet", "BoxA"))
    safe("cmd_Part_ToleranceSet_two", lambda: run("Part_ToleranceSet", "BoxA", "BoxB"))
    safe("cmd_Part_ToleranceSet_none", lambda: run("Part_ToleranceSet"))
    safe("crosssections", cross_sections)
    safe("builder", builder)
    safe("check_geometry", check_geometry)
    safe("objects", objects)
    safe("tree", tree_rows)
    for n in ("Box001", "Comp_solid", "Tolerance", "Box_cs", "Edge", "Face"):
        if doc.getObject(n):
            safe("props_" + n, lambda n=n: property_view(n))

    def types():
        out = {}
        from BOPTools import ToleranceFeatures
        o = ToleranceFeatures.makeToleranceSet("ToleranceT")
        out["Part::ToleranceSet"] = props_of(o.Name)
        o = doc.addObject("Part::Feature", "FeatureT")
        out["Part::Feature"] = props_of(o.Name)
        return out
    safe("types", types)
    safe("undo_names", lambda: list(doc.UndoNames))
    save()
    os._exit(0)


QtCore.QTimer.singleShot(500, main)

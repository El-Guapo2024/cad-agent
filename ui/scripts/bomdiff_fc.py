# SPDX-License-Identifier: LGPL-2.1-or-later
# bomdiff.py's FreeCAD half: runs inside freecadcmd, builds each case as an Assembly of App::Link components and
# answers with the rows of FreeCAD's own BOM (Assembly::BomObject, as CommandCreateBom.py:316-331 creates it).
import json, os
import FreeCAD as App
import Part
import UtilsAssembly

COLUMNS = ["Index", "Name", "Description", "File Name", "Quantity"]    # CommandCreateBom.py:53-59, the default columns
cases = json.load(open(os.environ["BOMDIFF_IN"]))
out = {}
for title, bodies in cases.items():
    doc = App.newDocument(title)
    things = {}
    for body in bodies:
        if body["part"] not in things:                  # one object for each part; its label is the BOM's Name
            o = doc.addObject("Part::Feature", body["part"])
            o.Label = body["part"]
            o.Shape = Part.makeBox(20, 10, 4)
            things[body["part"]] = o
    asm = doc.addObject("Assembly::AssemblyObject", "Assembly")
    for body in bodies:
        # A mirror is a link with a negative Scale (BomObject::isObjMirrored, BomObject.cpp:253-270 reads Scale); a
        # mirror of a mirror is a mirrored link to a mirrored link.
        target = things[body["part"]]
        for k in range(max(body["mirrors"], 0)):
            if k < body["mirrors"] - 1:
                inner = doc.addObject("App::Link", body["name"] + "_inner")
                inner.LinkedObject, inner.Scale = target, -1
                target = inner
        lk = asm.newObject("App::Link", body["name"])
        lk.LinkedObject = target
        if body["mirrors"] == -1:
            lk.ScaleVector = App.Vector(-1, 1, 1)
        elif body["mirrors"]:
            lk.Scale = -1
    doc.recompute()
    bom = UtilsAssembly.getBomGroup(asm).newObject("Assembly::BomObject", "Bill of Materials")
    bom.columnsNames = COLUMNS
    doc.recompute()
    bom.recompute()
    rows, r = [], 2
    while bom.getContents(f"A{r}"):
        cell = lambda c: bom.getContents(f"{c}{r}").removeprefix("'")
        rows.append([cell("A"), cell("B"), int(cell("E"))])
        r += 1
    out[title] = {"rows": rows, "scales": {o.Name: [o.Scale, tuple(o.ScaleVector)] for o in asm.OutList if o.TypeId == "App::Link"}}
json.dump(out, open(os.environ["BOMDIFF_OUT"], "w"))

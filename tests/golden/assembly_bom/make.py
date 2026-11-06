"""Writes freecad.json: FreeCAD's Bill of Materials of each case of cases.py, the cells after each recompute.

    $FREECAD/freecadcmd tests/golden/assembly_bom/make.py [CASE]     (FREECAD: FreeCAD's bin folder, 26.3 at 3160daf1e2b6)

Run it from the repository's root. Each case gets a fresh document: a Part::Feature per part (Label as PARTS says), its
sub-assemblies (an Assembly each, as Assembly_CreateAssembly makes one, with an App::Link per component), the Assembly
with its components (App::Link, or an Assembly::AssemblyLink to a sub-assembly), and the BOM as Assembly_CreateBom
makes it (UtilsAssembly.getBomGroup, then newObject("Assembly::BomObject", "Bill of Materials") and its columns); then
the document recomputed, and again after each step. The File Name column is the document's file, "" here (never saved).
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.getcwd())
sys.path.insert(0, str(ROOT / "tests" / "golden" / "assembly_bom"))

import FreeCAD as App  # noqa: E402
import Part  # noqa: E402
import UtilsAssembly  # noqa: E402

from cases import CASES, PARTS  # noqa: E402

COLS = "ABCDEFGH"


def assembly(doc, name):
    a = doc.addObject("Assembly::AssemblyObject", name)
    a.Type = "Assembly"
    a.newObject("Assembly::JointGroup", "Joints")
    return a


def add(doc, asm, comps, parts, subs):
    for name, target in comps:
        if target.startswith("@"):
            lk = asm.newObject("Assembly::AssemblyLink", name)
            lk.LinkedObject = subs[target[1:]]
        else:
            lk = asm.newObject("App::Link", name)
            lk.LinkedObject = parts[target]


def cells(bom):
    out = {}
    for row in range(0, 30):
        for c in COLS:
            t = bom.getContents(f"{c}{row + 1}")
            if t:
                out[f"{c}{row + 1}"] = t
    return out


def run(case):
    doc = App.newDocument("Unnamed")
    parts = {}
    for i, (n, label) in enumerate(PARTS.items()):
        o = doc.addObject("Part::Feature", n)
        o.Shape = Part.makeBox(10 + i, 5, 2)
        o.Label = label
        parts[n] = o
    subs = {}
    for sname, comps in case.get("subs", {}).items():
        s = assembly(doc, sname)
        add(doc, s, comps, parts, subs)
        subs[sname] = s
    asm = assembly(doc, "Assembly")
    add(doc, asm, case["components"], parts, subs)
    bg = UtilsAssembly.getBomGroup(asm)
    bom = bg.newObject("Assembly::BomObject", "Bill of Materials")
    bom.columnsNames = case.get("columns", ["Index", "Name", "Description", "File Name", "Quantity"])
    doc.recompute()
    out = [cells(bom)]
    for st in case.get("steps", []):
        add(doc, asm, st.get("add", []), parts, subs)
        for a, v in st.get("set", {}).items():
            bom.set(a, v)
        for k, v in st.get("props", {}).items():
            setattr(bom, k, v)
        bom.touch()
        doc.recompute()
        out.append(cells(bom))
    App.closeDocument(doc.Name)
    return out


path = ROOT / "tests" / "golden" / "assembly_bom" / "freecad.json"
data = json.loads(path.read_text()) if path.exists() else {}
names = [a for a in sys.argv[1:] if not a.endswith(".py")] or list(CASES)
for n in names:
    data[n] = run(CASES[n])
    print(n, [len(c) for c in data[n]])
path.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")

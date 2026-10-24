#!/usr/bin/env python3
"""Write ui/src/sketchcmdinfo.ts: every Sketcher command's menu text, tooltip, pixmap and shortcut, read from FreeCAD's
sources (the sMenuText, sToolTipText, sPixmap and sAccel each command's constructor sets in src/Mod/Sketcher/Gui/*.cpp).

    python3 ui/scripts/sketchcmdgen.py FREECAD_SRC

FREECAD_SRC is a checkout of FreeCAD at 3160daf1e2b6 (src/Mod/Sketcher/Gui is enough). A group command
(Sketcher_Comp*) shows the pixmap of the command its drop-down starts with, as Gui::GroupCommand does.
"""
import json
import re
import sys
from pathlib import Path

src = Path(sys.argv[1]) / "src" / "Mod" / "Sketcher" / "Gui"
out = {}
for f in sorted(src.glob("*.cpp")):
    s = f.read_text(encoding="utf-8")
    for m in re.finditer(r'\("(Sketcher_\w+)"\)\s*\{(.*?)\n\}', s, re.S):
        name, body = m.group(1), m.group(2)
        if "sMenuText" not in body:
            continue
        d = {}
        for k in ("sMenuText", "sToolTipText", "sPixmap", "sAccel"):
            mm = re.search(k + r'\s*=\s*(?:QT_TR_NOOP\()?\s*((?:"(?:[^"\\]|\\.)*"\s*)+)', body)
            if mm:
                d[k] = "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', mm.group(1)))
        out[name] = d
# The unified coincident command's constructor takes its name as an argument (CommandConstraints.cpp).
out["Sketcher_ConstrainCoincidentUnified"] = {"sMenuText": "Coincident Constraint", "sToolTipText": "Constrains the selected elements to be coincident",
                                              "sPixmap": "Constraint_Coincident", "sAccel": "C"}
lines = []
for name in sorted(out):
    d = out[name]
    row = [d.get("sMenuText", ""), d.get("sToolTipText", ""), d.get("sPixmap", ""), d.get("sAccel", "")]
    lines.append(f"  {name}: {json.dumps(row, ensure_ascii=False)},")
head = """// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Sketcher/Gui/CommandCreateGeo.cpp: 2010 Jürgen Riegel
//   src/Mod/Sketcher/Gui/CommandConstraints.cpp: 2010 Jürgen Riegel
//   src/Mod/Sketcher/Gui/Command.cpp: 2008 Jürgen Riegel
//   src/Mod/Sketcher/Gui/CommandSketcherTools.cpp: 2014 Abdullah Tahiri
// Written by ui/scripts/sketchcmdgen.py from FreeCAD's sources: each Sketcher command's menu text, tooltip, pixmap and
// shortcut (sMenuText, sToolTipText, sPixmap, sAccel). Do not edit; run the script again.
export const SKETCH_CMD_INFO: Record<string, [string, string, string, string]> = {
"""
# The geometry tools' icons for construction mode (Sketcher_ToggleConstruction swaps them in, as CommandCreateGeo.cpp's
# updateAction does), the ones Resources/icons/geometry has.
constr = sorted(f.stem[: -len("_Constr")] for f in (src / "Resources" / "icons" / "geometry").glob("*_Constr.svg"))
tail = "/** The icons that have a construction-mode variant (NAME_Constr.svg). */\nexport const CONSTR_ICONS = new Set(" + json.dumps(constr) + ")\n"
Path(__file__).resolve().parent.parent.joinpath("src", "sketchcmdinfo.ts").write_text(head + "\n".join(lines) + "\n}\n" + tail, encoding="utf-8")
print(f"sketchcmdgen: {len(out)} commands")

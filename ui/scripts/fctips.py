#!/usr/bin/env python3
"""Write ui/src/fctips.ts: FreeCAD's menu text and tooltip for every FreeCAD command id that ui/src names.

    python3 scripts/fctips.py [--dump fctips.json]

Without --dump it runs FreeCAD's GUI with fctips_dump.py first (a temporary profile): FREECAD_APP is either an
unpacked Linux AppImage (its usr/bin/freecad, run under xvfb-run) or FreeCAD.app on a Mac (fclaunch.py).
The texts are FreeCAD's own source strings (sMenuText, sToolTipText), the same on every platform; the tooltips
are drawn from them as Action::createToolTip does (tooltip.ts). Run it again after a FreeCAD update or when ui/src
starts naming a new command.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "src"


def run_dump(out: Path) -> Path:
    app = Path(os.environ.get("FREECAD_APP", "~/.cad-agent/freecad/FreeCAD.app")).expanduser()
    with tempfile.TemporaryDirectory(prefix="fctips") as home:
        if (app / "usr" / "bin" / "freecad").exists():
            env = {**os.environ, "FCGUI_OUT": str(out), "FREECAD_USER_HOME": home,
                   "FREECAD_USER_DATA": f"{home}/data", "FREECAD_USER_TEMP": f"{home}/tmp"}
            subprocess.run(["xvfb-run", "-a", "-s", "-screen 0 1600x1000x24", str(app / "usr" / "bin" / "freecad"),
                            str(HERE / "fctips_dump.py")], env=env, stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)
        else:
            sys.path.insert(0, str(HERE))
            from fclaunch import run_freecad
            run_freecad(HERE / "fctips_dump.py", out, Path(home))
    return out / "fctips.json"


# The commands the header's files define: every Std_ one but those a Python module adds (the Addon Manager's, Material's),
# and Part's selection filters (CommandFilter.cpp). Std_Measure and Std_MassProperties come from Mod/Measure/Gui/Command.cpp.
NOT_HERE = {"Std_AddonMgr", "Std_AddonMgrPip", "Std_SetAppearance", "Std_SetMaterial"}
PART = {"Part_SelectFilter", "Part_VertexSelection", "Part_EdgeSelection", "Part_FaceSelection", "Part_RemoveSelectionGate"}


# PartDesign's and the Sketcher's C++ commands (Mod/PartDesign/Gui/Command*.cpp, Mod/Sketcher/Gui/Command.cpp), and Part's Check
# Geometry (Mod/Part/Gui/Command.cpp); the gears and the shaft wizard are Python modules of their own.
PY_COMMANDS = {"PartDesign_InvoluteGear", "PartDesign_Sprocket", "PartDesign_WizardShaft"}


def wanted(name: str) -> bool:
    return ((name.startswith("Std_") and name not in NOT_HERE) or name in PART or name == "Part_CheckGeometry"
            or (name.startswith(("PartDesign_", "Sketcher_")) and name not in PY_COMMANDS))


def clean(title: str) -> str:
    """Action::cleanTitle: the mnemonic's & dropped."""
    return re.sub(r"&(.)", r"\1", title)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", help="a fctips.json written by fctips_dump.py")
    a = ap.parse_args()
    if a.dump:
        dump = json.loads(Path(a.dump).read_text())
    else:
        with tempfile.TemporaryDirectory(prefix="fctips-out") as out:
            p = run_dump(Path(out))
            if not p.exists():
                sys.exit("fctips: FreeCAD wrote nothing")
            dump = json.loads(p.read_text())
    cmds = dump["commands"]
    used = set()
    for f in sorted(SRC.glob("*.ts*")):
        if f.name != "fctips.ts":
            used |= set(re.findall(r"\b(?:Std|Part|PartDesign|Sketcher)_[A-Za-z0-9]+\b", f.read_text()))
    rows = []
    for name in sorted(used):
        c = cmds.get(name)
        if not wanted(name) or not c or "error" in c or not c.get("menu"):
            continue
        rows.append(f"  {name}: {json.dumps([clean(c['menu']), c.get('tip') or ''], ensure_ascii=False)},")
    head = """// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Gui/CommandStd.cpp: 2002 Jürgen Riegel; 2023 FreeCAD Project Association
//   src/Gui/CommandDoc.cpp: 2002 Jürgen Riegel
//   src/Gui/CommandView.cpp: 2002 Jürgen Riegel
//   src/Gui/CommandWindow.cpp: 2002 Jürgen Riegel
//   src/Gui/CommandMacro.cpp: 2010 Werner Mayer
//   src/Gui/CommandStructure.cpp: 2017 Stefan Tröger
//   src/Gui/CommandLink.cpp: 2017 Zheng Lei (realthunder)
//   src/Gui/CommandFeat.cpp: 2002 Jürgen Riegel
//   src/Gui/CommandTest.cpp: 2002 Jürgen Riegel
//   src/Mod/Part/Gui/CommandFilter.cpp: 2002 Jürgen Riegel
//   src/Mod/Measure/Gui/Command.cpp: 2023 David Friedli
// Written by ui/scripts/fctips.py from the running FreeCAD: each command's menu text (sMenuText, its & dropped as
// Action::cleanTitle does) and tooltip (sToolTipText), for every FreeCAD command id ui/src names. tooltip.ts draws a
// command's tooltip from these as Action::createToolTip does. Do not edit by hand.
export const FC_TIPS: Record<string, [menuText: string, toolTip: string]> = {
"""
    (SRC / "fctips.ts").write_text(head + "\n".join(rows) + "\n}\n")
    print(f"fctips: {len(rows)} commands -> {SRC / 'fctips.ts'}")


if __name__ == "__main__":
    main()

# SPDX-License-Identifier: LGPL-2.1-or-later
"""Writes ui/src/attachmodes.ts from cad_agent/attacher.py (FreeCAD's Attacher.cpp, held to freecadcmd by
tests/test_attacher.py): each engine's modes in eMapMode order (EnableAllSupportedModes: those with reference
lists), and the reference combinations each mode takes (modeRefTypes), as the Attachment panel lists them when
nothing is referenced and in its tooltips (AttacherGui::getRefListForMode).

    .venv/bin/python ui/scripts/attachmodes.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from cad_agent import attacher as A  # noqa: E402

OUT = ROOT / "ui" / "src" / "attachmodes.ts"


def main():
    modes = {e: A.modes(e) for e in A.ENGINES}
    refs = {e: {m: [[A.ref_type_name(t) for t in combo] for combo in A.MODE_REFS[e][A.M[m]]]
                for m in modes[e][1:]} for e in A.ENGINES}
    head = ("// SPDX-License-Identifier: LGPL-2.1-or-later\n"
            "// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is\n"
            "// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):\n"
            "//   src/Mod/Part/App/Attacher.cpp: 2015 Victor Titov (DeepSOIC)\n"
            "// Written by ui/scripts/attachmodes.py from cad_agent/attacher.py, the port of FreeCAD's\n"
            "// src/Mod/Part/App/Attacher.cpp (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6; 2015 Victor Titov\n"
            "// (DeepSOIC); LGPL-2.0-or-later). Do not edit: run the script again. Each attacher engine's modes in eMapMode\n"
            "// order (Deactivated first), and each mode's reference combinations (modeRefTypes), by eRefType name (|Placement: a whole object).\n")
    OUT.write_text(head + "export const ENGINE_MODES: Record<string, string[]> = " + json.dumps(modes) + "\n"
                   + "export const MODE_REFS: Record<string, Record<string, string[][]>> = " + json.dumps(refs) + "\n"
                   + "export const REF_TYPES: string[] = " + json.dumps(list(A.REF_TYPES)) + "\n")
    print(OUT, {e: len(m) for e, m in modes.items()})


if __name__ == "__main__":
    main()

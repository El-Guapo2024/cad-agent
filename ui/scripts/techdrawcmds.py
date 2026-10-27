#!/usr/bin/env python3
"""Generates ui/src/techdraw_cmds.ts: every TechDraw command's menu text, tool tip and icon, from its source.

    python3 ui/scripts/techdrawcmds.py [FREECAD_SRC] [ui/src/techdraw_cmds.ts]

FREECAD_SRC is a folder holding src/Mod/TechDraw at 3160daf1e2b6 (fetched from GitHub into
~/.cad-agent/freecad/techdraw-3160daf1e2b6/ when not given). Each C++ command's constructor (Command("TechDraw_X") in
src/Mod/TechDraw/Gui/Command*.cpp) gives sMenuText, sToolTipText and sPixmap; a group command (Gui::GroupCommand)
gives its sMenuText and the commands it lists; the Python ones (TechDrawTools/Command*.py) give MenuText, ToolTip
and Pixmap from GetResources. The icon is the pixmap's file name in public/freecad-icons/techdraw (td-<name>), or null
when there is none. The generated file is not edited by hand.
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

COMMIT = "3160daf1e2b6"
HERE = Path(__file__).resolve().parent
ICONS = HERE.parent / "public" / "freecad-icons" / "techdraw"
FILES = ["Command.cpp", "CommandCreateDims.cpp", "CommandAnnotate.cpp", "CommandDecorate.cpp", "CommandStack.cpp",
         "CommandExtensionDims.cpp", "CommandExtensionPack.cpp", "CommandHelpers.cpp", "CommandAlign.cpp"]
PY = ["CommandAxoLengthDimension.py", "CommandHoleShaftFit.py", "CommandFillTemplateFields.py", "CommandShareView.py",
      "CommandMoveView.py", "CommandPositionSectionView.py", "CommandVertexCreations.py", "CommandFillTemplateFields.py"]


def fetch(root: Path, rel: str) -> str:
    f = root / rel
    if not f.exists():
        f.parent.mkdir(parents=True, exist_ok=True)
        host = "raw.github" + "usercontent.com"
        try:
            f.write_bytes(urllib.request.urlopen(f"https://{host}/FreeCAD/FreeCAD/{COMMIT}/{rel}", timeout=30).read())
        except Exception:
            return ""
    return f.read_text(errors="replace")


def cstr(text: str) -> str:
    """The concatenated C++ string literals inside QT_TR_NOOP(...) or "...", unescaped."""
    parts = re.findall(r'"((?:[^"\\]|\\.)*)"', text)
    s = "".join(parts)
    return s.encode("utf-8").decode("unicode_escape").encode("latin-1").decode("utf-8")


def icon(pix: str):
    if not pix:
        return None
    stem = pix.split("/")[-1].removesuffix(".svg")
    return f"td-{stem}" if (ICONS / f"{stem}.svg").exists() else None


def parse_cpp(src: str, out: dict):
    for m in re.finditer(r'Command\("(TechDraw_\w+)"\)', src):
        name = m.group(1)
        body = src[m.end():m.end() + 2500]
        end = body.find("\n}")
        body = body[:end] if end > 0 else body
        d = out.setdefault(name, {})
        for key, field in (("text", "sMenuText"), ("tip", "sToolTipText"), ("pix", "sPixmap")):
            mm = re.search(field + r"\s*=\s*(.*?);", body, re.S)
            if mm:
                v = mm.group(1)
                d[key] = cstr(v) if '"' in v else ""
        sub = re.findall(r'addCommand\("(TechDraw_\w+)"\)|addCommand\(\)', body)
        if "addCommand" in body:
            d["group"] = [s or "sep" for s in re.findall(r'addCommand\(\s*(?:"(TechDraw_\w+)")?\s*\)', body)]


LIT = r"""(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')"""


def parse_py(src: str, out: dict):
    for m in re.finditer(r"""Gui\.addCommand\(\s*['"](TechDraw_\w+)['"]\s*,\s*(\w+)\(\)\s*\)""", src):
        name, cls = m.group(1), m.group(2)
        c = re.search(rf"class {cls}\b.*?def GetResources\(self\):(.*?)\n    def ", src, re.S)
        if not c:
            continue
        res = c.group(1)
        d = out.setdefault(name, {})
        for key, field in (("text", "MenuText"), ("tip", "ToolTip"), ("pix", "Pixmap")):
            mm = re.search(rf"""['"]{field}['"]\s*:\s*(.*?)(?=,\s*['"][A-Za-z]+['"]\s*:|\}})""", res, re.S)
            if not mm:
                continue
            strs = ["".join(g) for g in re.findall(LIT, mm.group(1))]
            if "QT_TRANSLATE_NOOP" in mm.group(1):
                strs = strs[1:]                 # the context
            d[key] = "".join(strs).encode("utf-8").decode("unicode_escape").encode("latin-1").decode("utf-8")


def main():
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / ".cad-agent" / "freecad" / f"techdraw-{COMMIT}"
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE.parent / "src" / "techdraw_cmds.ts"
    out: dict = {}
    for f in FILES:
        parse_cpp(fetch(root, f"src/Mod/TechDraw/Gui/{f}"), out)
    for f in sorted(set(PY)):
        parse_py(fetch(root, f"src/Mod/TechDraw/TechDrawTools/{f}"), out)
    # the group commands whose constructor lists no addCommand (they make their actions in code): their lists as the
    # real FreeCAD's toolbars show them (ui/scripts/fctechdraw.json), and the Python group's GetCommands
    rec = HERE / "fctechdraw.json"
    if rec.exists():
        for tb in json.loads(rec.read_text()).get("toolbars_page", []):
            for b in tb["buttons"]:
                if b.get("menu") and b.get("name") and not out.get(b["name"], {}).get("group"):
                    out.setdefault(b["name"], {})["group"] = [m.get("name") or "" if not m.get("sep") else "sep" for m in b["menu"]]
    if "TechDraw_CommandVertexCreationGroup" in out:
        out["TechDraw_CommandVertexCreationGroup"]["group"] = ["TechDraw_ExtensionVertexAtIntersection", "TechDraw_CommandAddOffsetVertex"]
    rows = []
    for name in sorted(out):
        d = out[name]
        e = {"text": d.get("text", ""), "tip": d.get("tip", ""), "icon": icon(d.get("pix", ""))}
        if d.get("group"):
            e["group"] = d["group"]
        rows.append(f"  {json.dumps(name)}: {json.dumps(e, ensure_ascii=False)},")
    head = f"""// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit {COMMIT}), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/TechDraw/Gui/Command.cpp: 2002 Jürgen Riegel; 2014 Luke Parry
//   src/Mod/TechDraw/Gui/CommandCreateDims.cpp: 2014 Luke Parry; 2022 WandererFan
//   src/Mod/TechDraw/Gui/CommandAnnotate.cpp: 2019 WandererFan
//   src/Mod/TechDraw/Gui/CommandDecorate.cpp: 2014 Luke Parry
//   src/Mod/TechDraw/Gui/CommandStack.cpp: 2022 WandererFan
//   src/Mod/TechDraw/Gui/CommandExtensionDims.cpp: 2021 edi
//   src/Mod/TechDraw/Gui/CommandExtensionPack.cpp: 2021 edi
//   src/Mod/TechDraw/Gui/CommandHelpers.cpp: 2024 WandererFan
//   src/Mod/TechDraw/Gui/CommandAlign.cpp: 2024 Benjamin Bræstrup Sayoc
//   src/Mod/TechDraw/TechDrawTools/CommandAxoLengthDimension.py: 2023 edi
//   src/Mod/TechDraw/TechDrawTools/CommandHoleShaftFit.py: 2023 edi
//   src/Mod/TechDraw/TechDrawTools/CommandFillTemplateFields.py: 2023 Syres
//   src/Mod/TechDraw/TechDrawTools/CommandShareView.py: 2022 WandererFan
//   src/Mod/TechDraw/TechDrawTools/CommandMoveView.py: 2022 WandererFan
//   src/Mod/TechDraw/TechDrawTools/CommandPositionSectionView.py: 2023 edi
//   src/Mod/TechDraw/TechDrawTools/CommandVertexCreations.py: 2023 edi
// GENERATED by ui/scripts/techdrawcmds.py: do not edit. Each TechDraw command's menu text, tool tip and icon
// (public/freecad-icons/techdraw, td-<file>) as its constructor sets them, and a group command's commands (the ones
// that make theirs in code: as the real FreeCAD's toolbars list them, ui/scripts/fctechdraw.json).
export type TdCmd = {{ text: string; tip: string; icon: string | null; group?: string[] }}
export const TD_CMDS: Record<string, TdCmd> = {{
"""
    dst.write_text(head + "\n".join(rows) + "\n}\n")
    print(f"techdrawcmds: {len(rows)} commands -> {dst}")


if __name__ == "__main__":
    main()

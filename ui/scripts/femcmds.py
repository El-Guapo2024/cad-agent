"""Writes ui/src/fem_cmds.ts: the FEM workbench's menus and toolbars (src/Mod/Fem/Gui/Workbench.cpp's setupMenuBar
and setupToolBars) and each command's MenuText, ToolTip, Pixmap and Accel: the C++ ones from Gui/Command.cpp
(sMenuText, sToolTipText, sPixmap, sAccel; a group's members from its getCommandByName calls), the Python ones from
femcommands/commands.py (CommandManager: command "FEM" + the class name, pixmap the command, unless set; a group's
self.commands).

    python3 ui/scripts/femcmds.py WORKBENCH_CPP COMMAND_CPP COMMANDS_PY     (FreeCAD 26.3, 3160daf1e2b6)
"""
import ast
import json
import re
import sys
from pathlib import Path

wb_src, cmd_src, py_src = (Path(a).read_text() for a in sys.argv[1:4])


def structure(fn):
    """setupMenuBar / setupToolBars: {var: (title, [items])} and the top-level order."""
    body = re.search(rf"{fn}\(\) const\s*\{{(.*?)\n\}}", wb_src, re.S).group(1)
    body = re.sub(r"//[^\n]*", "", body)
    titles, items, order = {}, {}, []
    for var, title in re.findall(r"(\w+)->setCommand\(\"([^\"]+)\"\)", body):
        titles[var] = title
        items[var] = []
    for var, chain in re.findall(r"\*(\w+)((?:\s*<<\s*(?:\"[^\"]*\"|\w+))+)\s*;", body):
        items.setdefault(var, [])
        for tok in re.findall(r"<<\s*(\"[^\"]*\"|\w+)", chain):
            items[var].append(tok.strip('"') if tok.startswith('"') else {"sub": tok})
    for var in re.findall(r"root->insertItem\(item,\s*(\w+)\)", body):
        order.append(var)
    if not order:
        order = [v for v in titles if re.search(rf"new Gui::ToolBarItem\(root\)", body) and v in titles]

    def expand(var):
        out = []
        for it in items.get(var, []):
            out.append({"menu": titles[it["sub"]], "items": expand(it["sub"])} if isinstance(it, dict) else it)
        return out
    tops = order if fn == "setupMenuBar" else [v for v in titles]
    return [{"title": titles[v], "items": expand(v)} for v in tops if v in titles]


cmds = {}
# C++ commands: Command("FEM_X") then sMenuText / sToolTipText / sPixmap / sAccel in the constructor
for m in re.finditer(r'::\w+\(\)\s*:\s*Command\("(\w+)"\)\s*\{(.*?)\n\}', cmd_src, re.S):
    name, body = m.group(1), m.group(2)

    def field(f, body=body):
        x = re.search(rf'{f}\s*=\s*(?:QT_TR_NOOP\()?"((?:[^"\\]|\\.)*)"', body)
        return x.group(1) if x else None
    cmds[name] = {"menu": field("sMenuText"), "tip": field("sToolTipText"), "pixmap": field("sPixmap"),
                  "accel": field("sAccel")}
for gm in re.finditer(r'class Cmd(\w+)\b.*?Command\("(FEM_\w+)"\)', cmd_src, re.S):
    pass
for name in list(cmds):
    cls = re.search(rf'Cmd(\w+)::Cmd\w+\(\)\s*:\s*Command\("{name}"\)', cmd_src)
    if cls:
        create = re.search(rf'Gui::Action\* Cmd{cls.group(1)}::createAction\(\)\s*\{{(.*?)\n\}}', cmd_src, re.S)
        lang = re.search(rf'void Cmd{cls.group(1)}::languageChange\(\)\s*\{{(.*?)\n\}}', cmd_src, re.S)
        src = (lang or create).group(1) if (lang or create) else ""
        group = re.findall(r'getCommandByName\(\s*"(\w+)"', src)
        if group:
            cmds[name]["group"] = group
# Python commands
tree = ast.parse(py_src)
classes = {c.name: c for c in tree.body if isinstance(c, ast.ClassDef)}
for n in ast.walk(tree):
    if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "addCommand" and len(n.args) == 2:
        name, cls = n.args[0].value, n.args[1].func.id
        c = classes.get(cls)
        r = {"menu": cls.lstrip("_"), "tip": None, "pixmap": "FEM" + cls, "accel": None}
        r["tip"] = f"Creates a {r['menu']}"
        for f in [x for x in (c.body if c else []) if isinstance(x, ast.FunctionDef) and x.name == "__init__"]:
            for a in ast.walk(f):
                if isinstance(a, ast.Assign) and isinstance(a.targets[0], ast.Attribute):
                    k = a.targets[0].attr
                    v = a.value
                    if isinstance(v, ast.Call) and getattr(v.func, "attr", getattr(v.func, "id", "")) == "QT_TRANSLATE_NOOP":
                        v = v.args[-1]
                    try:
                        val = ast.literal_eval(v)
                    except ValueError:
                        continue
                    if k in ("menutext", "tooltip", "pixmap", "accel"):
                        r[{"menutext": "menu", "tooltip": "tip"}.get(k, k)] = val
                    if k == "commands":
                        r["group"] = val
        cmds[name] = r
out = Path(__file__).resolve().parents[1] / "src" / "fem_cmds.ts"
out.write_text("// SPDX-License-Identifier: LGPL-2.1-or-later\n"
               "// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is\n"
               "// LGPL-2.1-or-later as it states; ui/NOTICE has them all):\n"
               "//   src/Mod/Fem/Gui/Workbench.cpp: 2008 Werner Mayer, 2023 Peter McB\n"
               "//   src/Mod/Fem/Gui/Command.cpp: 2008 Jürgen Riegel, 2022 Peter McB\n"
               "//   src/Mod/Fem/femcommands/commands.py: 2016 Bernd Hahnebach\n"
               "// GENERATED by ui/scripts/femcmds.py from those files (the menus and toolbars, each command's resources): do\n"
               "// not edit.\n"
               "export type FemCmd = { menu: string | null; tip: string | null; pixmap: string | null; accel: string | null; group?: string[] }\n"
               "export type FemItem = string | { menu: string; items: FemItem[] }\n"
               f"export const FEM_CMDS: Record<string, FemCmd> = {json.dumps(cmds, indent=1, ensure_ascii=False)}\n"
               f"export const FEM_MENUS: {{ title: string; items: FemItem[] }}[] = {json.dumps(structure('setupMenuBar'), indent=1)}\n"
               f"export const FEM_TOOLBARS: {{ title: string; items: FemItem[] }}[] = {json.dumps(structure('setupToolBars'), indent=1)}\n")
print(len(cmds), "commands")

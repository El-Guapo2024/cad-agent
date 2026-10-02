#!/usr/bin/env python3
"""Turn fcgui.py's dump into menudiff.js's reference: PartWorkbench's menu bar as
{"menus": {title: [{label, kbd, cmd, sub?} | {sep: true}]}}, written to PROJECT/out/fc-ref.png
(a .png name so the workbench's /api/file serves it to the page).

    python3 scripts/fcref.py PROJECT_DIR [freecad-gui.json]

Hidden actions (FreeCAD's empty recent-file and saved-view slots) are left out. The key text is
the native one FreeCAD put in the tooltip ("⌘N"), else the portable shortcut. The dump runs Qt's
offscreen platform, whose key scheme isn't the Mac's: Close, Redo, Delete, Exit and Next/Previous
Window differ from ours on purpose (see PARITY.md's Menus note).
"""
import json
import re
import sys
from pathlib import Path

amp = lambda s: s.replace("&&", "\0").replace("&", "").replace("\0", "&")


def conv(items):
    out = []
    for a in items:
        if a.get("sep"):
            out.append({"sep": True})
            continue
        if a.get("visible") is False or not a.get("text"):
            continue
        kbd = ""
        if a.get("shortcut"):
            m = re.search(r"</b> \(([^)]*)\)</p>", a.get("tip", ""))
            kbd = m.group(1) if m else a["shortcut"]
        e = {"label": amp(a["text"]), "kbd": kbd, "cmd": a.get("name", "")}
        if a.get("menu") is not None:
            e["sub"] = conv(a["menu"])
        out.append(e)
    return out


project = Path(sys.argv[1])
src = Path(sys.argv[2] if len(sys.argv) > 2 else "~/.cad-agent/freecad/reference/freecad-gui.json").expanduser()
bar = json.loads(src.read_text())["workbenches"]["PartWorkbench"]["menubar"]
(project / "out").mkdir(exist_ok=True)
(project / "out" / "fc-ref.png").write_text(json.dumps({"menus": {amp(m["text"]): conv(m.get("menu", [])) for m in bar if not m.get("sep")}}))
print(f"fcref: wrote {project / 'out' / 'fc-ref.png'}")

#!/usr/bin/env python3
"""Run the real FreeCAD GUI headless (Qt's offscreen platform) and dump its interface.

    python3 scripts/fcgui.py [OUT_DIR] [--platform cocoa]     # OUT_DIR default ~/.cad-agent/freecad/reference

Writes freecad-gui.json (every command's menu text, tooltip, status tip and shortcut; the
menu bar and toolbars of NoneWorkbench, PartWorkbench and PartDesignWorkbench; docks; status
bar widgets) and screenshots (start page at 800 and 1280 wide, a Part Box selected, each dock).
FREECAD_APP overrides where FreeCAD.app is; FreeCAD's user files go to a temporary folder.
Give a scratch OUT_DIR when ~/.cad-agent must stay untouched.

--platform cocoa runs it on the Mac's own Qt platform instead, windows kept off the screen (fclaunch.py
says how): the Mac's key bindings (Close is Cmd+W, not offscreen's Ctrl+F4) and its font, and the 3D view
renders. The default stays offscreen, so older dumps remain comparable.
"""
import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fclaunch import run_freecad  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("out", nargs="?", default="~/.cad-agent/freecad/reference")
ap.add_argument("--platform", choices=["offscreen", "cocoa"], default="offscreen")
a = ap.parse_args()
out = Path(a.out).expanduser()
with tempfile.TemporaryDirectory(prefix="fcgui") as home:
    r = run_freecad(Path(__file__).with_name("fcgui_dump.py"), out, Path(home), platform=a.platform)
if not (out / "freecad-gui.json").exists():
    sys.exit(f"fcgui: FreeCAD wrote nothing (exit {r.returncode})\n{r.stdout[-4000:]}")
print(f"fcgui: wrote {out}")

#!/usr/bin/env python3
"""Run the real FreeCAD GUI headless (Qt's offscreen platform) and dump its interface.

    python3 scripts/fcgui.py [OUT_DIR]     # default ~/.cad-agent/freecad/reference

Writes freecad-gui.json (every command's menu text, tooltip, status tip and shortcut; the
menu bar and toolbars of NoneWorkbench, PartWorkbench and PartDesignWorkbench; docks; status
bar widgets) and screenshots (start page at 800 and 1280 wide, a Part Box selected, each dock).
FREECAD_APP overrides where FreeCAD.app is; FreeCAD's user files go to a temporary folder.
"""
import os, subprocess, sys, tempfile
from pathlib import Path

APP = Path(os.environ.get("FREECAD_APP", "~/.cad-agent/freecad/FreeCAD.app")).expanduser()
out = Path(sys.argv[1] if len(sys.argv) > 1 else "~/.cad-agent/freecad/reference").expanduser()
out.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix="fcgui") as home:
    env = {**os.environ, "FCGUI_OUT": str(out), "QT_QPA_PLATFORM": "offscreen", "FREECAD_USER_HOME": home}
    r = subprocess.run([str(APP / "Contents" / "MacOS" / "FreeCAD"), str(Path(__file__).with_name("fcgui_dump.py"))],
                       env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300)
if not (out / "freecad-gui.json").exists():
    sys.exit(f"fcgui: FreeCAD wrote nothing (exit {r.returncode})\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
print(f"fcgui: wrote {out}")

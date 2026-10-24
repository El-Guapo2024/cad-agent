#!/usr/bin/env python3
"""The real FreeCAD's Sketcher in edit mode, as the reference for the workbench's (ui/scripts/sketchcheck.mjs compares).

    FREECAD_APP=<unpacked AppImage> xvfb-run -a -s "-screen 0 1600x1000x24" python3 ui/scripts/fcsketch.py OUT_DIR [--only CASE,...]

Starts FreeCAD's GUI (fclaunch.py: a temporary profile holding the FreeCAD Light preference pack, every window kept off
the screen; on Linux the X11 platform, so run it under xvfb-run as above) and writes OUT_DIR/fcsketch.json: the toolbars,
menus and task panel of a sketch in edit mode, the drawing parameters a fresh profile has, and, for each case of
ui/scripts/sketchcases.json, the sketch FreeCAD makes from the case's clicks, keys and selections (fcsketch_dump.py).
--only runs only the named cases.
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fclaunch import run_freecad  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--only", default="")
ap.add_argument("--cases", default=str(Path(__file__).with_name("sketchcases.json")))
a = ap.parse_args()
out = Path(a.out).expanduser()
with tempfile.TemporaryDirectory(prefix="fcsketch") as tmp:
    (Path(tmp) / "home").mkdir()
    r = run_freecad(Path(__file__).with_name("fcsketch_dump.py"), out, Path(tmp) / "home", platform="cocoa", scale=0.5, timeout=1200,
                    env={"FCSKETCH_ONLY": a.only, "FCSKETCH_CASES": str(Path(a.cases).resolve())})
if not (out / "fcsketch.json").exists():
    sys.exit(f"fcsketch: FreeCAD wrote nothing (exit {r.returncode})\n{r.stdout[-4000:]}")
res = json.loads((out / "fcsketch.json").read_text())
for name, err in res["errors"].items():
    print(f"fcsketch: {name} failed:\n{err}")
print(f"fcsketch: wrote {out / 'fcsketch.json'} ({len(res['cases'])} cases)")

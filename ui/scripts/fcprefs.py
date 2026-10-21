#!/usr/bin/env python3
"""Every Preferences page the workbench has, as the real FreeCAD lays it out and fills it in a fresh profile.

    python3 scripts/fcprefs.py OUT_DIR [--only general,navigation,...] [--scale 0.5] [--tall 1900] [--timeout 300]

Starts the real FreeCAD GUI (the weekly build at ~/.cad-agent/freecad/FreeCAD.app; FREECAD_APP overrides) on the Mac's Qt
platform with every window kept off the screen (fclaunch.py), opens Preferences and walks its tree. Writes OUT_DIR/fcprefs.json
(the dialog's metrics; per page every widget's rectangle in the page, text, state and tool tip, the value it shows, its size policy
and hints, and every layout's margins, spacing and items: fcprefs_dump.py has the list) and OUT_DIR/freecad-prefs-<page>.png (the
dialog at 900 px high, as it opens) and freecad-prefs-<page>-tall.png (tall enough for the page not to scroll). FreeCAD's user
files are a temporary folder; its profile starts as FreeCAD's own "FreeCAD Light" preference pack, which is what a new user gets.
oursprefs.mjs reads the same things off the workbench; fcprefsdiff.py compares the two.
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
ap.add_argument("--scale", type=float, default=0.5)
ap.add_argument("--tall", type=int, default=1900)
ap.add_argument("--timeout", type=int, default=300)
a = ap.parse_args()
out = Path(a.out).expanduser()
with tempfile.TemporaryDirectory(prefix="fcprefs") as tmp:
    (Path(tmp) / "home").mkdir()
    r = run_freecad(Path(__file__).with_name("fcprefs_dump.py"), out, Path(tmp) / "home", platform="cocoa", scale=a.scale,
                    timeout=a.timeout, env={"FCPREFS_ONLY": a.only, "FCPREFS_TALL": str(a.tall)})
if not (out / "fcprefs.json").exists():
    sys.exit(f"fcprefs: FreeCAD wrote nothing (exit {r.returncode})\n{r.stdout[-4000:]}")
res = json.loads((out / "fcprefs.json").read_text())
for name, err in res["errors"].items():
    print(f"fcprefs: {name} failed:\n{err}")
print(f"fcprefs: {len(res['pages'])} pages -> {out / 'fcprefs.json'}")

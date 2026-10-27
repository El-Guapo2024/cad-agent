#!/usr/bin/env python3
"""Dump what the real FreeCAD's Spreadsheet workbench shows, for the Spreadsheet page to be compared with.

    FREECAD_APP=<unpacked AppImage> xvfb-run -a -s "-screen 0 1600x1000x24" python3 scripts/fcspreadsheet.py OUT_DIR

Starts FreeCAD's GUI (fclaunch.py: user files in a temporary folder, windows kept off the screen) with
fcspreadsheet_dump.py, which uses the workbench as a person would (New Spreadsheet, cells typed into the sheet view,
the alignment and style commands on a selection, merge and split, the Properties dialog, Set Alias, the Content and
Alias line edits, Copy, Cut, Paste and Delete, the headers' Insert Rows, the keys that move the current cell) and
writes OUT_DIR/fcspreadsheet.json: the Spreadsheet menu and toolbar, what the sheet's model gives for each cell
(display string, tooltip, colours, alignment, font), the dialogs, the undo steps, the tree and the property view.
ui/scripts/spreadsheetcheck.mjs holds the page to it.
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
a = ap.parse_args()
out = Path(a.out).expanduser()
with tempfile.TemporaryDirectory(prefix="fcspreadsheet") as tmp:
    (Path(tmp) / "home").mkdir()
    r = run_freecad(Path(__file__).with_name("fcspreadsheet_dump.py"), out, Path(tmp) / "home", platform="cocoa",
                    scale=0.5, timeout=1000, show=True)
if not (out / "fcspreadsheet.json").exists():
    sys.exit(f"fcspreadsheet: FreeCAD wrote nothing (exit {r.returncode})\n{r.stdout[-4000:]}")
res = json.loads((out / "fcspreadsheet.json").read_text())
for name, err in res["errors"].items():
    print(f"fcspreadsheet: {name} failed:\n{err}")
print(f"fcspreadsheet: wrote {out / 'fcspreadsheet.json'}")

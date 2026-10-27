#!/usr/bin/env python3
"""Dump what the real FreeCAD's TechDraw annotation tools do, for the TechDraw page to be compared with.

    FREECAD_APP=<unpacked AppImage> xvfb-run -a -s "-screen 0 1600x1000x24" python3 scripts/fctechdraw_annot.py OUT_DIR

Starts FreeCAD's GUI (fclaunch.py: user files in a temporary folder, windows kept off the screen) with
fctechdraw_annot_dump.py, which draws a part (a page, a view of the plate from above) and then uses the tools of the
Add Lines, Add Vertices and Centerlines menus and the eraser the way a person does, and writes
OUT_DIR/fctechdraw_annot.json: the menu entries' state for each selection, each task panel, what it made (the view's
cosmetic vertices, cosmetic edges, centre lines and line formats, the geometry's numbering), the undo steps, the
property view and the page exported. techdrawcheck.mjs holds the workbench to it (ui/scripts/fctechdraw_annot.json).
"""
import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fclaunch import run_freecad  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("out")
a = ap.parse_args()
out = Path(a.out).expanduser()
with tempfile.TemporaryDirectory(prefix="fctechdrawannot") as tmp:
    (Path(tmp) / "home").mkdir()
    r = run_freecad(Path(__file__).with_name("fctechdraw_annot_dump.py"), out, Path(tmp) / "home", platform="cocoa", scale=0.5,
                    timeout=1700,
                    env={"FCTECHDRAW_BREPS": str(Path(__file__).resolve().parents[2] / "tests/golden/techdraw/breps")})
if not (out / "fctechdraw_annot.json").exists():
    sys.exit(f"fctechdraw_annot: FreeCAD wrote nothing (exit {r.returncode})\n{r.stdout[-4000:]}")
text = (out / "fctechdraw_annot.json").read_text()
text = re.sub(r'"(?:[^"\\]|\\.)*?/(?:usr/share|share)/Mod/TechDraw/', '"<FreeCAD>/Mod/TechDraw/', text)
text = text.replace(str(Path(__file__).resolve().parents[2]), "<repo>")
text = re.sub(r'"(?:[^"\\]|\\.)*?/FreeCAD_Doc_[0-9a-f_-]+/', '"<document>/', text)
(out / "fctechdraw_annot.json").write_text(text)
res = json.loads(text)
for name, err in res["errors"].items():
    print(f"fctechdraw_annot: {name} failed:\n{err}")
print(f"fctechdraw_annot: wrote {out / 'fctechdraw_annot.json'}")

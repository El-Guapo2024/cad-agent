#!/usr/bin/env python3
"""Dump what the real FreeCAD's TechDraw workbench shows, for the TechDraw page to be compared with.

    FREECAD_APP=<unpacked AppImage> xvfb-run -a -s "-screen 0 1600x1000x24" python3 scripts/fctechdraw.py OUT_DIR

Starts FreeCAD's GUI (fclaunch.py: user files in a temporary folder, windows kept off the screen) with
fctechdraw_dump.py, which draws a part as a person would (Insert Default Page, a view and a projection group of the
selected part, section views by each arrow, dimensions from a selection of edges and vertices, an annotation, a
balloon) and writes OUT_DIR/fctechdraw.json: the TechDraw menu and toolbars, each task panel, the objects made with
their properties and undo steps, the tree, the property views and the page exported as SVG, DXF and PDF.
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
with tempfile.TemporaryDirectory(prefix="fctechdraw") as tmp:
    (Path(tmp) / "home").mkdir()
    r = run_freecad(Path(__file__).with_name("fctechdraw_dump.py"), out, Path(tmp) / "home", platform="cocoa", scale=0.5,
                    timeout=1000,
                    env={"FCTECHDRAW_BREPS": str(Path(__file__).resolve().parents[2] / "tests/golden/techdraw/breps")})
if not (out / "fctechdraw.json").exists():
    sys.exit(f"fctechdraw: FreeCAD wrote nothing (exit {r.returncode})\n{r.stdout[-4000:]}")
# the machine's own paths (FreeCAD's resources, this checkout, FreeCAD's document cache) as placeholders, so the file
# names no local folder
text = (out / "fctechdraw.json").read_text()
text = re.sub(r'"(?:[^"\\]|\\.)*?/(?:usr/share|share)/Mod/TechDraw/', '"<FreeCAD>/Mod/TechDraw/', text)
text = text.replace(str(Path(__file__).resolve().parents[2]), "<repo>")
text = re.sub(r'"(?:[^"\\]|\\.)*?/FreeCAD_Doc_[0-9a-f_-]+/', '"<document>/', text)
(out / "fctechdraw.json").write_text(text)
res = json.loads(text)
for name, err in res["errors"].items():
    print(f"fctechdraw: {name} failed:\n{err}")
print(f"fctechdraw: wrote {out / 'fctechdraw.json'}")

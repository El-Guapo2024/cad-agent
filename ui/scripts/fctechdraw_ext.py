#!/usr/bin/env python3
"""Dump what the real FreeCAD's TechDraw extension commands do (CommandExtensionPack/Dims), for the TechDraw page to be compared with.

    FREECAD_APP=<unpacked AppImage> xvfb-run -a -s "-screen 0 1600x1000x24" python3 scripts/fctechdraw_annot.py OUT_DIR

Starts FreeCAD's GUI (fclaunch.py: user files in a temporary folder, windows kept off the screen) with
fctechdraw_ext_dump.py, which draws a part (a page, a view of the plate from above) and then uses the tools of the
extension commands (Attributes, Centerlines/Threading, Format/Organize Dimensions) the way a person does, and writes
OUT_DIR/fctechdraw_ext.json: the menu entries' state for each selection, each task panel, what it made (the view's
cosmetic vertices, cosmetic edges, centre lines and line formats, the geometry's numbering), the undo steps, the
property view and the page exported. techdrawcheck.mjs holds the workbench to it (ui/scripts/fctechdraw_ext.json).
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
with tempfile.TemporaryDirectory(prefix="fctechdrawext") as tmp:
    (Path(tmp) / "home").mkdir()
    r = run_freecad(Path(__file__).with_name("fctechdraw_ext_dump.py"), out, Path(tmp) / "home", platform="cocoa", scale=0.5,
                    timeout=1700,
                    env={"FCTECHDRAW_JSON": "fctechdraw_ext.json", "FCTECHDRAW_ANNOT_DUMP": str(Path(__file__).with_name("fctechdraw_annot_dump.py")), "FCTECHDRAW_BREPS": str(Path(__file__).resolve().parents[2] / "tests/golden/techdraw/breps")})
if not (out / "fctechdraw_ext.json").exists():
    sys.exit(f"fctechdraw_ext: FreeCAD wrote nothing (exit {r.returncode})\n{r.stdout[-4000:]}")
text = (out / "fctechdraw_ext.json").read_text()
text = re.sub(r'"(?:[^"\\]|\\.)*?/(?:usr/share|share)/Mod/TechDraw/', '"<FreeCAD>/Mod/TechDraw/', text)
text = text.replace(str(Path(__file__).resolve().parents[2]), "<repo>")
text = re.sub(r'"(?:[^"\\]|\\.)*?/FreeCAD_Doc_[0-9a-f_-]+/', '"<document>/', text)
(out / "fctechdraw_ext.json").write_text(text)
res = json.loads(text)


def strip(x):
    """The menus' tool tips are the HTML of the command's text, which fctechdraw_ext.json does not need."""
    if isinstance(x, dict):
        return {k: strip(v) for k, v in x.items() if k != "tip"}
    if isinstance(x, list):
        return [strip(v) for v in x]
    return x


res = strip(res)
(out / "fctechdraw_ext.json").write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n")
for name, err in res["errors"].items():
    print(f"fctechdraw_ext: {name} failed:\n{err}")
print(f"fctechdraw_ext: wrote {out / 'fctechdraw_ext.json'}")

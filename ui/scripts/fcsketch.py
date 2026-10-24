#!/usr/bin/env python3
"""The real FreeCAD's Sketcher in edit mode, as the reference for the workbench's (ui/scripts/sketchcheck.mjs compares).

    FREECAD_APP=<unpacked AppImage> xvfb-run -a -s "-screen 0 1600x1000x24" python3 ui/scripts/fcsketch.py OUT_DIR [--only CASE,...]

Starts FreeCAD's GUI (fclaunch.py: a temporary profile holding the FreeCAD Light preference pack, every window kept off
the screen; on Linux the X11 platform, so run it under xvfb-run as above) and writes OUT_DIR/fcsketch.json: the toolbars,
menus and task panel of a sketch in edit mode, the drawing parameters a fresh profile has, and, for each case of
ui/scripts/sketchcases.json, the sketch FreeCAD makes from the case's clicks, keys and selections (fcsketch_dump.py).
--only runs only the named cases. --ref also writes the part sketchcheck.mjs compares with, ui/scripts/sketchref.json:
the toolbars' and the Sketch menu's commands in order, the colour parameters, each case's geometry, constraints and
solver message, and the datum dialogs' titles (--ref without OUT_DIR's run: `--ref --from OUT_DIR/fcsketch.json`).
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
ap.add_argument("--ref", action="store_true", help="also write ui/scripts/sketchref.json")
ap.add_argument("--from", dest="src", default="", help="with --ref: an fcsketch.json already written, instead of running FreeCAD")
ap.add_argument("--cases", default=str(Path(__file__).with_name("sketchcases.json")))
a = ap.parse_args()
out = Path(a.out).expanduser()


def write_ref(res: dict) -> Path:
    def acts(items):
        out = []
        for x in items:
            if x == "---":
                out.append("sep")
            elif x.get("group"):
                out.append({"group": x["name"], "items": acts(x["group"])})
            else:
                out.append(x["name"])
        return out

    def menu(items):
        out = []
        for x in items:
            if x == "---":
                out.append("sep")
            elif x.get("menu"):
                out.append({"menu": x["text"], "items": menu(x["menu"])})
            else:
                out.append(x["name"])
        return out
    sketch = next(m for m in res["chrome"]["menubar"] if m != "---" and m["text"] == "S&ketch")
    ref = {"about": "What FreeCAD 26.3 (3160daf1e2b6) does for ui/scripts/sketchcases.json, written by fcsketch.py --ref; "
                    "ui/scripts/sketchcheck.mjs compares the workbench with it.",
           "viewport": res["viewport"],
           "toolbars": [{"title": t["title"], "items": acts(t["actions"])} for t in res["chrome"]["toolbars"]],
           "sketch_menu": menu(sketch["menu"]), "params": res["params"], "message_empty": res["message_empty"],
           "dialogs": [{"case": d["case"], "title": d["title"]} for d in res["dialogs"]],
           "cases": {k: {"geometry": v["geometry"], "constraints": v["constraints"], "message": v["message"],
                         **({"external": v["external"], "external_geometry": v["external_geometry"]} if "external" in v else {})}
                     for k, v in res["cases"].items()}}
    path = Path(__file__).with_name("sketchref.json")
    path.write_text(json.dumps(ref, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


if a.ref and a.src:
    print(f"fcsketch: wrote {write_ref(json.loads(Path(a.src).expanduser().read_text()))}")
    sys.exit(0)
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
if a.ref:
    print(f"fcsketch: wrote {write_ref(res)}")

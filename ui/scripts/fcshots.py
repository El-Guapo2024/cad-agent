#!/usr/bin/env python3
"""FreeCAD's own screenshots, for the side-by-side with the workbench (oursshots.mjs makes ours).

    python3 scripts/fcshots.py OUT_DIR [--scene PROJECT/out/scene.json] [--scale 0.5] [--only start,part,...]

Starts the real FreeCAD GUI (the weekly build at ~/.cad-agent/freecad/FreeCAD.app; FREECAD_APP overrides) on
the Mac's Qt platform with every window kept off the screen (fclaunch.py), lays out a document of the project's
bodies (the bodies of a scene.json the workbench wrote: name and bounding box, as plain Part shapes) and writes
OUT_DIR/freecad-<thing>.png at 1280 x 800, plus fcshots.json (what was measured). The shots: start,
start-cards, part (a part selected: the tree, the property view, the 3D view), navicube (the cube cropped
from that grab), treemenu (the tree's context menu on a part), report (the Report view with a message of each
kind). --scale is Qt's QT_SCALE_FACTOR: 0.5 on a Retina screen gives a devicePixelRatio of 1 and 1280 x 800
pixels; 1.5 gives 3, for a close-up of the cube (3840 x 2400). FreeCAD's user files are a temporary folder.
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
ap.add_argument("--scene", help="a project's out/scene.json: its bodies become the document")
ap.add_argument("--scale", type=float, default=0.5)
ap.add_argument("--only", default="")
ap.add_argument("--timeout", type=int, default=300)
a = ap.parse_args()
out = Path(a.out).expanduser()
env = {"FCSHOTS_ONLY": a.only}
with tempfile.TemporaryDirectory(prefix="fcshots") as tmp:
    if a.scene:
        bodies = [{"name": b["name"], "bbox": b["bbox"]} for b in json.loads(Path(a.scene).read_text())["bodies"]]
        (Path(tmp) / "bodies.json").write_text(json.dumps(bodies))
        env["FCSHOTS_BODIES"] = str(Path(tmp) / "bodies.json")
    (Path(tmp) / "home").mkdir()
    r = run_freecad(Path(__file__).with_name("fcshots_dump.py"), out, Path(tmp) / "home", platform="cocoa",
                    scale=a.scale, timeout=a.timeout, env=env)
if not (out / "fcshots.json").exists():
    sys.exit(f"fcshots: FreeCAD wrote nothing (exit {r.returncode})\n{r.stdout[-4000:]}")
res = json.loads((out / "fcshots.json").read_text())
for name, err in res["errors"].items():
    print(f"fcshots: {name} failed:\n{err}")
print(f"fcshots: wrote {out} (devicePixelRatio {res['dpr']}, window {res['window']})")

#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""The NaviCube side by side with FreeCAD's, on Linux: shots of both at the same orientations and pointer positions, and
how far they differ.

    FREECAD_APP=<unpacked AppImage> NODE_PATH=<folder with playwright> \\
        .venv/bin/python ui/scripts/navishots.py OUT_DIR --url http://127.0.0.1:<port>/next/ [--project mini_machine]
        [--skip-fc] [--skip-ours]

FreeCAD: the weekly build FreeCAD_weekly-2026.09.30 (main 3160daf1e2b6) unpacked with --appimage-extract (FREECAD_APP is
the squashfs-root folder), started under `xvfb-run` with its user files in a temporary folder that starts as its own
"FreeCAD Light" preference pack; navishots_dump.py takes the shots inside it. Ours: navishots_ours.mjs, against a workbench
that serves scratch copies only (`serve.run([scratch])` with the CAD_* folders in scratch, as ui/HANDOFF.md says; never the
owner's ports). Each shot is the 180 px square at the top right of the 3D view, where the cube is: OUT_DIR/fc-<shot>.png and
ours-<shot>.png; side-<shot>.png has the two side by side, three times the size, FreeCAD's on the left. Printed per shot: the
share of pixels that differ by more than 48 in a channel, the mean difference, and the box of the dark (outline) pixels.
Needs Pillow and numpy (the repo's .venv has them). The labels differ where the box has no Arial for FreeCAD's Qt (it
falls back to a serif face there); the shapes, places and colours are what is compared.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ISO = [0.424708, 0.17592, 0.339851, 0.820473]
R2 = 0.7071067811865476
SHOTS = {
    # Camera.cpp's views, two arbitrary turns, and the isometric view in perspective
    "orient": {"iso": ISO, "front": [R2, 0, 0, R2], "top": [0, 0, 0, 1], "right": [0.5, 0.5, 0.5, 0.5], "rear": [0, R2, R2, 0],
               "corner": [0.6, 0.2, -0.3, 0.71], "odd": [0.2, 0.3, 0.1, 0.92], "persp": "persp"},
    # the pointer, from the cube's centre (px), in the isometric view: a corner, a face, and each kind of button
    "hover": {"hover-center": [0, 0], "hover-front": [-14, 14], "hover-north": [0, -58], "hover-east": [58, 0],
              "hover-rollL": [-44, -44], "hover-home": [-54, -54], "hover-back": [53, -56], "hover-menu": [53, 52]},
}
S = 180


def run_freecad(out: Path):
    app = Path(os.environ.get("FREECAD_APP", "")).expanduser()
    exe = app / "usr" / "bin" / "freecad"
    if not exe.exists():
        sys.exit(f"navishots: no FreeCAD at {exe} (set FREECAD_APP to the unpacked AppImage)")
    pack = app / "usr" / "share" / "Gui" / "PreferencePacks" / "FreeCAD Light" / "FreeCAD Light.cfg"
    with tempfile.TemporaryDirectory() as home:
        shutil.copy(pack, Path(home) / "user.cfg")
        env = {**os.environ, "FREECAD_USER_HOME": home, "FCGUI_OUT": str(out), "NAVI_SHOTS": json.dumps(SHOTS)}
        if Path("/etc/fonts/fonts.conf").exists():
            env.setdefault("FONTCONFIG_FILE", "/etc/fonts/fonts.conf")
        r = subprocess.run(["xvfb-run", "-a", "-s", "-screen 0 1600x1000x24", str(exe), str(HERE / "navishots_dump.py")],
                           env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=600)
    res = json.loads((out / "fc.json").read_text()) if (out / "fc.json").exists() else {"error": r.stdout[-2000:]}
    if "error" in res:
        sys.exit("navishots: FreeCAD failed:\n" + res["error"])


def run_ours(out: Path, url: str, project: str):
    subprocess.run(["node", str(HERE / "navishots_ours.mjs"), url, project, str(out), json.dumps(SHOTS)], check=True, timeout=600)


def compare(out: Path):
    import numpy as np
    from PIL import Image

    def load(p):
        im = Image.open(p).convert("RGB")
        w, _ = im.size
        return im.crop((w - S, 0, w, S))

    names = [n + s for n in SHOTS["orient"] for s in ("-away", "-near")] + list(SHOTS["hover"])
    print(f"{'shot':16s} {'differ':>7s} {'mean':>6s}  dark box (x0, y0, x1, y1) FreeCAD / ours")
    for n in names:
        a, b = load(out / f"fc-{n}.png"), load(out / f"ours-{n}.png")
        side = Image.new("RGB", (2 * S * 3 + 6, S * 3), "white")
        side.paste(a.resize((S * 3, S * 3), Image.NEAREST), (0, 0))
        side.paste(b.resize((S * 3, S * 3), Image.NEAREST), (S * 3 + 6, 0))
        side.save(out / f"side-{n}.png")
        x, y = np.asarray(a).astype(int), np.asarray(b).astype(int)
        d = np.abs(x - y).max(axis=2)

        def dark(m):
            ys, xs = np.nonzero(m.mean(axis=2) < 96)
            return (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())) if len(xs) else None
        print(f"{n:16s} {np.mean(d > 48) * 100:6.2f}% {d.mean():6.2f}  {dark(x)} / {dark(y)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out", type=Path)
    ap.add_argument("--url")
    ap.add_argument("--project", default="mini_machine")
    ap.add_argument("--skip-fc", action="store_true")
    ap.add_argument("--skip-ours", action="store_true")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    if not a.skip_fc:
        run_freecad(a.out)
    if not a.skip_ours:
        if not a.url:
            sys.exit("navishots: --url is needed for our shots")
        run_ours(a.out, a.url, a.project)
    compare(a.out)


if __name__ == "__main__":
    main()

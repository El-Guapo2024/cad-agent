"""Export a project's assembly to viewer/model.glb for the live viewer.

The viewer polls model.json and reloads the model whenever the stamp changes,
so re-running this after an edit is all it takes to see the new geometry in
the app's Browser pane. Prototype of `cad serve`; see PLAN_V2.md.

    .venv/bin/python viewer/export_glb.py assembly_cell
"""
import json
import sys
import time
import zlib
from pathlib import Path

from build123d import Color, Compound, export_gltf

from cad_agent.state import load_assembly

HERE = Path(__file__).resolve().parent

# Stable, distinguishable colours: bought stock grey, everything we make warm.
STOCK = {"bed": (0.35, 0.37, 0.40), "rail": (0.72, 0.74, 0.78), "beam": (0.72, 0.74, 0.78)}
MADE = [(0.85, 0.45, 0.20), (0.20, 0.55, 0.85), (0.30, 0.70, 0.45), (0.80, 0.70, 0.25)]


def colour(name: str) -> Color:
    for key, rgb in STOCK.items():
        if key in name:
            return Color(*rgb)
    return Color(*MADE[zlib.crc32(name.split("_left")[0].split("_right")[0].encode()) % len(MADE)])


def main(slug: str) -> None:
    solids, *_ = load_assembly(slug)
    if not solids:
        sys.exit(f"{slug}: no assembly.py")
    children = []
    for name, solid in solids.items():
        solid.label, solid.color = name, colour(name)
        children.append(solid)
    export_gltf(Compound(children=children), HERE / "model.glb", binary=True,
                linear_deflection=0.05, angular_deflection=0.2)
    meta = {"title": slug, "parts": len(children), "stamp": time.time()}
    (HERE / "model.json").write_text(json.dumps(meta))
    print(f"{slug}: {len(children)} parts -> {HERE / 'model.glb'}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "assembly_cell")

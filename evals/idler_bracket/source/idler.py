"""Generator for the given parts of the idler_bracket task.

Run once from the repo root to write the STEP files and their source notes:

    python evals/idler_bracket/source/idler.py

Every body is modelled centred on its own bounding box and already in the
assembly's orientation (idler and shaft axes along z, extrusion along x), so a
design only has to translate it. Each one is registered the way
`cad bought add-step` does it, so the files land in given/bought/ with a .json
sidecar recording where the numbers came from. This script is not laid into the
agent's project; it is the record of how the given geometry was made.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from build123d import (Axis, BuildLine, BuildPart, BuildSketch, Box, Cylinder, Plane, Polyline,
                       Pos, export_step, make_face, revolve)

from cad_agent import bought, state
from cad_agent.parts import EXTRUSION

OUT = Path(__file__).resolve().parent.parent / "given" / "bought"


def idler():
    """GT2 20T toothless idler: a smooth wheel between two flanges, bore 5.

    The listings give 18 mm across the flanges, 8.5 mm overall and a 5 mm bore,
    for a 6 mm belt. The belt-running diameter is the 12.2 mm tip circle of a
    20-tooth GT2 pulley (they say the smooth wheel matches it). The flange is
    taken as 1.0 mm thick, which leaves 6.5 mm between flanges for a 6 mm belt.
    """
    bore, flange_od, belt_od, width, flange_t = 5.0, 18.0, 12.2, 8.5, 1.0
    r0, r1, r2, h = bore / 2.0, belt_od / 2.0, flange_od / 2.0, width / 2.0
    half = [(r0, -h), (r2, -h), (r2, -h + flange_t), (r1, -h + flange_t),
            (r1, h - flange_t), (r2, h - flange_t), (r2, h), (r0, h), (r0, -h)]
    with BuildPart() as part:
        with BuildSketch(Plane.XZ):
            with BuildLine():
                Polyline(*half)
            make_face()
        revolve(axis=Axis.Z)
    return part.part


def shaft():
    """M5 rod, 20 long, as a plain 5.0 mm cylinder along z (ISO 262 nominal).

    20 is the extrusion's own height, so the stub and the shaft end on the same
    planes: the stance rule takes the lowest plane as the ground and wants 5 mm
    of footprint on it, which a 5.0 mm rod alone would meet only by equality.
    """
    return Cylinder(2.5, 20.0)


def extrusion():
    """A 60 mm stub of 2040 profile: 20 x 40 with a 4.2 mm bore in each end.

    The bores are the M5 tap drill, 10 mm either side of the centre on the long
    side (one per 20 x 20 half). T-slots are left out, as in cad_agent.parts: an
    end mount never touches them.
    """
    e = EXTRUSION["2040"]
    length = 60.0
    body = Box(length, e["h"], e["w"])
    for sy in (-1, 1):
        body -= Pos(0, sy * e["h"] / 4.0, 0) * Cylinder(e["bore"] / 2.0, length + 2.0).rotate(Axis.Y, 90)
    return body


PARTS = {
    "gt2_idler": (idler, "GT2 20T toothless (smooth) idler for a 6 mm belt: bore 5, across flanges 18, overall width 8.5. "
                         "Two retailer listings agree (no maker datasheet found): botland.store product 18929 'smooth "
                         "pulley 20T GT2 6mm, 5 mm hole', and tinytronics.nl 'GT2-20 pulley toothless 5mm axis'. "
                         "Belt-running 12.2 is the 20-tooth GT2 tip circle (the listings say it matches one); flange 1.0 "
                         "thick is assumed, not published. A flanged wheel: no bearing, no hub.", None),
    "m5_shaft": (shaft, "M5 x 20 threaded rod as a plain 5.0 x 20 mm cylinder (ISO 262 nominal major diameter). "
                        "Made by evals/idler_bracket/source/idler.py.", None),
    "extrusion_2040": (extrusion, "2040 aluminium profile stub, 20 x 40 x 60: envelope and 4.2 mm end bores (M5 tap drill) "
                                  "from cad_agent.parts EXTRUSION['2040'] (`cad tables`). T-slots omitted.", None),
}


def register(name: str, solid, source: str, vendor: str | None) -> Path:
    """Export one STEP and register it into given/bought/ like `cad bought add-step`."""
    with tempfile.TemporaryDirectory() as tmp:
        state.ROOT = Path(tmp)
        state.project_dir("gen", create=True)
        step = Path(tmp) / f"{name}.step"
        export_step(solid, str(step))
        dest = bought.register_step("gen", name, str(step), source, vendor)
        OUT.mkdir(parents=True, exist_ok=True)
        for f in (dest, dest.with_suffix(".json")):
            shutil.copy2(f, OUT / f.name)
    return OUT / f"{name}.step"


if __name__ == "__main__":
    for name, (fn, source, vendor) in PARTS.items():
        path = register(name, fn(), source, vendor)
        print(f"{name}: {path}")
    sys.exit(0)

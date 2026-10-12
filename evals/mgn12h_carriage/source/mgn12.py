"""Generator for the given parts of the mgn12h_carriage task.

Run once from the repo root to write the STEP files and their source notes:

    python evals/mgn12h_carriage/source/mgn12.py

Every body is modelled centred on its own bounding box and already in the
assembly's orientation (rail along x, block face up), so a design only has to
translate it. Each one is registered the way `cad bought add-step` does it, so
the files land in given/bought/ with a .json sidecar recording where the
numbers came from. The STEPs are written with cad_agent.export.write_step, so
every run writes the same bytes. This script is not laid into the agent's
project; it is the record of how the given geometry was made.

The block and rail are envelopes for clearance checking, not models of the
part: no balls, end caps, seals or grease nipple, and the rail has no ball
grooves. What the gates need is the space they take and where they bolt down.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from build123d import Box, Cylinder, Pos

from cad_agent import bought, state
from cad_agent.export import write_step
from cad_agent.library.gen import mgn
from cad_agent.parts import CLEARANCE_HOLE, TAP_DRILL

OUT = Path(__file__).resolve().parent.parent / "given" / "bought"

HIWIN = "HIWIN MG series catalog GW-11-5-EN-2207-K"


def rail(length: float = 150.0):
    """MGNR12R: 12 wide, 8 high, 25 mm hole pitch, M3 x 10 screws.

    HIWIN table 3.81 gives D 6.0, h 4.5, d 3.5, and F 3.16 gives the end
    distance: L = (n - 1) x P + E1 + E2. Six holes on a 150 mm rail leave
    E = 12.5, inside the catalog's 5 to 20 and not over P / 2.
    """
    return mgn.rail(width=12.0, height=8.0, pitch=25.0, counterbore_dia=6.0, counterbore_depth=4.5, hole_dia=3.5,
                    end_min=5.0, length=length, holes=6)


def block():
    """MGN12H: 45.4 x 27 x 10, standing 3.0 above the rail's base (H1).

    Table 3.79 gives H 13, H1 3.0, W 27, B 20, C 20, L 45.4 and M3 x 3.5. The
    block is centred on its own box, so the rail's top face is the block-frame
    plane z = 0 and the rail's base is 8 mm below it. The channel clears the
    rail by 0.2 mm a side and above, which a real block's preload does not
    show but keeps the two from touching in every fit query.
    """
    return mgn.carriage(length=45.4, width=27.0, height=13.0, base_gap=3.0, rail_width=12.0, hole_pitch_along=20.0,
                        hole_pitch_across=20.0, tap_dia=TAP_DRILL["M3"], tap_depth=3.5, rail_gap=0.2)


def end_stop():
    """A block standing at each rail end, tall enough to stop a plate on the block."""
    return Box(8.0, 24.0, 20.0)


def tool():
    """The thing the carriage carries: a flange with four M3 clearance holes on 30 x 30.

    The underside is relieved 26 x 26 x 3 for the heads of the plate's own
    M3 cap screws (head 5.5 across, 3 high, at 20 x 20), so the flange can sit
    flat on the plate. The relief is clear of the bolt circle: the hole edges
    start 13.3 mm from the centre and the relief ends at 13.
    """
    body = Box(36.0, 36.0, 6.0)
    for sx in (-1, 1):
        for sy in (-1, 1):
            body -= Pos(sx * 15.0, sy * 15.0, 0) * Cylinder(CLEARANCE_HOLE["M3"] / 2.0, 8.0)
    body -= Pos(0, 0, -3.0 + 1.0) * Box(26.0, 26.0, 4.0)       # z -4 to 0: 3 mm into the part
    return body


PARTS = {
    "mgn12_rail": (rail, f"{HIWIN}, table 3.81: MGNR12R, 12 x 8 mm, P 25, counterbore D 6.0 x h 4.5, d 3.5. "
                         "150 mm cut length, six holes, E 12.5 (F 3.16). Envelope: no ball grooves.",
                   "HIWIN"),
    "mgn12h_block": (block, f"{HIWIN}, table 3.79: MGN12H, H 13, H1 3.0, W 27, B 20, C 20, L 45.4, M3 x 3.5. "
                            "Envelope with the rail channel: no balls, end caps, seals or grease nipple.",
                     "HIWIN"),
    "end_stop": (end_stop, "eval fixture, not a vendor part: 8 x 24 x 20 mm end stop butted against a rail end. "
                           "Made by evals/mgn12h_carriage/source/mgn12.py.", None),
    "tool_flange": (tool, "eval fixture, not a vendor part: 36 x 36 x 6 mm tool flange, four M3 clearance holes "
                          "(3.4) on 30 x 30, 26 x 26 x 3 relief underneath. Made by evals/mgn12h_carriage/source/mgn12.py.",
                    None),
}


def register(name: str, solid, source: str, vendor: str | None) -> Path:
    """Export one STEP and register it into given/bought/ like `cad bought add-step`."""
    with tempfile.TemporaryDirectory() as tmp:
        state.ROOT = Path(tmp)
        state.project_dir("gen", create=True)
        step = Path(tmp) / f"{name}.step"
        write_step(solid, step)
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

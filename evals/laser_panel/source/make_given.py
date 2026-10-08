"""Makes the given files for the laser_panel eval: the frame, the push button and the OLED module.

Run from the repo root with the cad-agent Python:

    python evals/laser_panel/source/make_given.py

Each body is built by its own module here (frame.py, push_button.py, oled.py), and each module says where
its numbers come from. This writes a STEP file and a source note for every body into
evals/laser_panel/given/bought/, the same pair `cad bought add-step` leaves in a project (it calls the
same function). The STEPs are written with cad_agent.export.write_step, so every run writes the same bytes,
whatever order the bodies come in; the committed ones are the artefacts and this script says how they were
made.

The push button and the OLED are envelopes of the real parts, not models of them: see their docstrings
for what is left out. The hole sizes the frame is drilled to come from cad_agent.parts.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from cad_agent import state
from cad_agent.bought import register_step
from cad_agent.export import write_step

import frame
import oled
import push_button

OUT = Path(__file__).resolve().parent.parent / "given" / "bought"
BODIES = (("frame", frame), ("push_button", push_button), ("oled", oled))


def main() -> int:
    slug = "make_given"
    with tempfile.TemporaryDirectory() as tmp:
        state.ROOT = Path(tmp)
        state.project_dir(slug, create=True)
        for name, module in BODIES:
            step = Path(tmp) / f"{name}.step"
            write_step(module.build(), step)
            register_step(slug, name, str(step), module.SOURCE, module.VENDOR)
        OUT.mkdir(parents=True, exist_ok=True)
        for p in sorted((Path(tmp) / slug / "bought").iterdir()):
            shutil.copy(p, OUT / p.name)
            print(f"wrote {OUT / p.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

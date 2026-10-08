"""Writes the given bought parts of the eval tasks: STEP files modelled in build123d.

    python evals/make_given.py          # from the repo root

The STEPs are checked in, so nothing needs this at scoring time. It exists so the
numbers behind every file are written down in one place, and a changed dimension
is a change to a script a reviewer can read, not to a binary. Each STEP gets the
sidecar bought.py asks for, with its source. They are written with
cad_agent.export.write_step, so every run writes the same bytes.

These are task fixtures, not vendor files: the outlines follow the figures named
in each source line, and anything the figures do not give (a hole pattern the
task needs, a mounting face) is the task's own choice and says so.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from build123d import Axis, Box, Cone, Cylinder, Pos, Rot

from cad_agent.export import write_step

HERE = Path(__file__).resolve().parent


def write(task: str, name: str, solid, source: str) -> None:
    out = HERE / task / "given" / "bought"
    out.mkdir(parents=True, exist_ok=True)
    write_step(solid, out / f"{name}.step")
    (out / f"{name}.json").write_text(json.dumps(
        {"source": source, "vendor": None, "verified": True, "original": f"{name}.step"}, indent=1))
    lo, hi = solid.bounding_box().min, solid.bounding_box().max
    print(f"{task}/{name}: {hi.X - lo.X:.2f} x {hi.Y - lo.Y:.2f} x {hi.Z - lo.Z:.2f} mm")


def nema17_motor():
    """Origin at the middle of the mounting face, shaft toward +z, body behind it."""
    body = Pos(0, 0, -20) * Box(42.3, 42.3, 40.0)
    body = body.chamfer(5.0, None, body.edges().filter_by(Axis.Z))      # the cut corners
    motor = body + Pos(0, 0, 1) * Cylinder(11.0, 2.0)                   # 22 mm pilot, 2 mm high
    motor += Pos(0, 0, 12) * Cylinder(2.5, 24.0)                        # 5 mm shaft, 24 mm out of the face
    for sx in (-1, 1):
        for sy in (-1, 1):                                              # M3 tapped, 4.5 mm deep
            motor -= Pos(sx * 15.5, sy * 15.5, -1.75) * Cylinder(1.25, 5.5)
    return motor


def syringe():
    """A 10 mL luer-lock syringe, plunger part way out, solid: only its outside matters.

    Origin on the barrel axis at the underside of the finger flange, +z toward the
    plunger. Barrel 16.0 mm across and 75 mm long below the flange.
    """
    flange = Pos(0, 0, 1.5) * (Box(19.0, 14.0, 3.0)
                               + Pos(-9.5, 0, 0) * Cylinder(7.0, 3.0)
                               + Pos(9.5, 0, 0) * Cylinder(7.0, 3.0))   # 33 x 14 mm, 3 mm thick
    s = Pos(0, 0, -37.5) * Cylinder(8.0, 75.0) + flange
    s += Pos(0, 0, -78.5) * Cone(3.5, 8.0, 7.0)                         # the shoulder to the tip
    s += Pos(0, 0, -86.0) * Cylinder(3.0, 8.0)                          # luer nozzle
    s += Pos(0, 0, -85.5) * Cylinder(5.5, 7.0)                          # luer-lock collar
    s += Pos(0, 0, 5.0) * Cylinder(3.5, 130.0)                          # plunger rod, z -60..70
    s += Pos(0, 0, 71.5) * Cylinder(11.0, 3.0)                          # thumb pad
    return s


def carriage_plate():
    """6 mm plate, 100 x 80 mm. Origin at the middle of the front face, thickness toward +y."""
    plate = Pos(0, 3, 0) * Box(100.0, 6.0, 80.0)
    for sx in (-1, 1):
        for sz in (-1, 1):                                              # M3 clearance, 24 x 30 mm
            plate -= Pos(sx * 12.0, 3, sz * 15.0) * Rot(90, 0, 0) * Cylinder(1.7, 8.0)
    return plate


def galvo_head():
    """Scan head with its F-theta lens barrel. Origin where the beam leaves the lens, +z up.

    Lens barrel 56 mm across and 15 mm long under a 100 x 70 x 70 mm body. Four M4 tapped
    holes, 40 mm square, in the +x face.
    """
    head = Pos(0, 0, 7.5) * Cylinder(28.0, 15.0) + Pos(0, 0, 50.0) * Box(100.0, 70.0, 70.0)
    for sy in (-1, 1):
        for z in (30.0, 70.0):
            head -= Pos(47.0, sy * 20.0, z) * Rot(0, 90, 0) * Cylinder(1.65, 10.0)
    return head


def main() -> int:
    write("nema17_mount", "nema17_motor", nema17_motor(),
          "NEMA ICS 16 frame 17 (31.0 mm square pattern, 22.0 mm pilot, 5 mm shaft) with the "
          "common 17HS4401 outline (42.3 mm square, 40 mm body, 24 mm shaft); modelled in "
          "build123d by evals/make_given.py, not a vendor file")
    write("syringe_clamp", "syringe", syringe(),
          "typical 10 mL luer-lock syringe: 16.0 mm barrel, 33 mm finger flange; makers differ "
          "by about 0.5 mm; modelled in build123d by evals/make_given.py, not a vendor file")
    write("syringe_clamp", "carriage_plate", carriage_plate(),
          "task drawing: 6 mm aluminium plate 100 x 80 mm with four M3 clearance holes on a "
          "24 x 30 mm pattern; modelled in build123d by evals/make_given.py")
    write("galvo_mount", "galvo_head", galvo_head(),
          "10 mm aperture galvo head class (about 100 x 70 mm body) with an F-theta lens barrel; "
          "the outline and the 40 mm M4 pattern are the task's own; modelled in build123d by "
          "evals/make_given.py, not a vendor file")
    return 0


if __name__ == "__main__":
    sys.exit(main())

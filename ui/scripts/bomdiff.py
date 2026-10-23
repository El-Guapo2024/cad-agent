#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Differential test: cad_agent/bom.py against the real FreeCAD's Assembly BOM, for mirrored bodies.

Each case is a list of bodies: the part it is, and how many times it was mirrored. FreeCAD builds it as an
Assembly of App::Link components, a mirror being a link with a negative Scale (BomObject::isObjMirrored,
src/Mod/Assembly/App/BomObject.cpp:253-270 at 3160daf1e2b6), and makes its BOM with Assembly::BomObject;
bom.py builds the same bodies as a scratch project (part modules, a bought STEP, an assembly.py that calls
build123d's mirror()) and makes its own. The rows (Index, Name, Quantity) are compared; exit status 1 if any
differ.

    python ui/scripts/bomdiff.py      # with the Python that runs cad_agent (build123d), from the repo

FREECAD_APP overrides where FreeCAD is: a FreeCAD.app (default ~/.cad-agent/freecad/FreeCAD.app) or an
extracted AppImage (the folder holding usr/bin/freecadcmd). FreeCAD runs with its user files in a temporary
folder.

What it found at 3160daf1e2b6 (FreeCAD 26.3, weekly 2026.09.30): FreeCAD never splits a mirrored link off.
isObjMirrored takes `static_cast<App::LinkElement*>(obj)`, which is never null, so an App::Link's Scale is read
through a LinkElement's layout (BomObject.cpp:259-260) and the App::Link branch (266-267) is never reached; a
link with Scale -1 folds into the line of the part as before, and so does one with ScaleVector (-1, 1, 1). A
LinkElement, the one type that branch is right for, is not an App::Link and is not listed at all (203-213), nor
is a link array (both seen by hand, not cases here). bom.py does the same: a mirrored body is on its part's line
(its docstring, "mirrors"), and every case agrees.
"""
import json, os, subprocess, sys, tempfile, textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
APP = Path(os.environ.get("FREECAD_APP", "~/.cad-agent/freecad/FreeCAD.app")).expanduser()

# name, part, mirrors. motor is bought; the rest are part modules. -1 is one mirror that FreeCAD is given as a
# ScaleVector (-1, 1, 1), a plane mirror, where the others are a Scale of -1 (which sets ScaleVector (-1, -1, -1)).
CASES = {
    "workshop": [("panel", "panel", 0), ("clip_left", "clip", 0), ("clip_right", "clip", 1), ("block", "block", 0),
                 ("motor", "motor", 0)],
    "mirror_of_a_mirror": [("clip_left", "clip", 0), ("clip_right", "clip", 1), ("clip_back", "clip", 2),
                           ("clip_front", "clip", 1)],
    "two_sides": [("motor_left", "motor", 0), ("wheel_left", "wheel", 0), ("bracket_left", "bracket", 0),
                  ("motor_right", "motor", 1), ("wheel_right", "wheel", 1), ("bracket_right", "bracket", 1)],
    "only_mirrored": [("clip_right", "clip", 1)],
    "scale_vector": [("clip_left", "clip", 0), ("clip_right", "clip", -1)],
    "none_mirrored": [("clip_left", "clip", 0), ("clip_right", "clip", 0), ("block", "block", 0)],
}

PART = textwrap.dedent('''\
    """{name}: a test part."""
    from build123d import Box, Cylinder, Pos

    MATERIAL = "petg"
    PROCESS = "fdm"
    PARAMS = {{}}


    def build():
        return Box({x}, 10, 4) - Pos({x} / 4, 0, 0) * Cylinder(1.6, 10)
''')


def freecadcmd():
    for p in (APP / "Contents" / "Resources" / "bin" / "freecadcmd", APP / "Contents" / "Resources" / "bin" / "FreeCADCmd",
              APP / "usr" / "bin" / "freecadcmd", APP / "bin" / "freecadcmd"):
        if p.exists():
            return p
    sys.exit(f"bomdiff: no freecadcmd in {APP} (set FREECAD_APP)")


def run_freecad(tmp):
    inp, out, home = Path(tmp) / "in.json", Path(tmp) / "fc.json", Path(tmp) / "fchome"
    home.mkdir()
    inp.write_text(json.dumps({t: [{"name": n, "part": p, "mirrors": m} for n, p, m in bodies] for t, bodies in CASES.items()}))
    env = {**os.environ, "BOMDIFF_IN": str(inp), "BOMDIFF_OUT": str(out), "FREECAD_USER_HOME": str(home),
           "FREECAD_USER_DATA": str(home / "data"), "FREECAD_USER_TEMP": str(home / "tmp")}
    r = subprocess.run([str(freecadcmd()), str(HERE / "bomdiff_fc.py")], env=env, stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, timeout=600)
    if not out.exists():
        sys.exit(f"bomdiff: FreeCAD wrote nothing (exit {r.returncode})\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    return json.loads(out.read_text())


def run_ours(tmp):
    sys.path.insert(0, str(REPO))
    from build123d import Box, Pos
    from cad_agent import bom, state as st
    from cad_agent import export as ex
    st.ROOT = Path(tmp) / "projects"
    out = {}
    for title, bodies in CASES.items():
        d = st.ROOT / title
        for sub in ("parts", "bought", "out"):
            (d / sub).mkdir(parents=True, exist_ok=True)
        for k, part in enumerate(sorted({p for _, p, _ in bodies if p != "motor"})):
            (d / "parts" / f"{part}.py").write_text(PART.format(name=part, x=20 + 4 * k))
        ex.write_step(Box(30, 20, 20), d / "bought" / "motor.step")
        (d / "bought" / "motor.json").write_text(json.dumps({"source": "bomdiff", "verified": True}))
        lines = []
        for k, (name, part, mirrors) in enumerate(bodies):
            solid = 'bought_solid(SLUG, "motor")' if part == "motor" else f'build_part(SLUG, "{part}")[0]'
            solid = f"Pos({40 * k}, 0, 0) * {solid}"
            for plane in ("Plane.YZ", "Plane.XZ")[:abs(mirrors)]:
                solid = f"mirror({solid}, {plane})"
            lines.append(f'        "{name}": {solid},')
        (d / "assembly.py").write_text(
            "from build123d import Plane, Pos, mirror\nfrom cad_agent.state import build_part, bought_solid\n\n"
            f'SLUG = "{title}"\nALLOW_CONTACT = set()\n\n\ndef parts():\n    return {{\n' + "\n".join(lines) + "\n    }\n")
        with st.reusing_builds():
            b = bom.build(title)
        out[title] = {"rows": [[ln.index, ln.name, ln.quantity] for ln in b.lines]}
    return out


def main():
    with tempfile.TemporaryDirectory() as tmp:
        fc, ours = run_freecad(tmp), run_ours(tmp)
    bad = 0
    for title in CASES:
        f, o = fc[title]["rows"], ours[title]["rows"]
        same = f == o
        bad += not same
        print(f"{title}: {'same' if same else 'DIFFERENT'} ({len(f)} lines in FreeCAD, {len(o)} in bom.py)")
        if not same:
            print(f"  link Scales: {fc[title]['scales']}")
            for k in range(max(len(f), len(o))):
                a = " ".join(map(str, f[k])) if k < len(f) else "-"
                b = " ".join(map(str, o[k])) if k < len(o) else "-"
                print(f"  {a:<32} | {b}")
    print(f"{len(CASES) - bad} of {len(CASES)} cases the same")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Differential test of the drawings' visible smooth edges: cad_agent/drawing/hlr.py against the real FreeCAD's TechDraw.

    python scripts/hlrdiff.py                   # (needs FreeCAD: FREECAD_APP, as exprdiff.py) exit 1 if a view differs
    python scripts/hlrdiff.py --tol 1e-4 --show # a tighter tolerance, and every edge of each view

Run it with the repo's Python (it imports cad_agent and build123d) from the repo root. The shapes: the panel of
tests/test_drawing.py (R5 corners, a rounded window and a slot), the plates of the mini_machine fixture (back_wall and base,
built from a copy of the fixture in a temporary folder), and two solids with curved smooth edges (a cylinder with a filleted
rim, a box with every edge filleted). Each plate is seen as `cad drawing` sees it (onesheet.views_of: the face, the view
from the left in first angle and from the right in third), each solid along +z, +y and +x. Each shape goes to a STEP file
by build123d and through both:

  ours     hlr.hlr_edges, the Rg1LineVCompound edges as OCCT gives them (before hlr.py joins and covers them)
  FreeCAD  hlrdiff_fc.py in freecadcmd: a TechDraw DrawViewPart with the same Direction and XDirection, SmoothVisible
           off and on (GeometryObject.cpp:264-266, FreeCAD 3160daf1e2b6), the smooth edges being what the second has more

Edges are matched by their two end points (either way round) and their length, within --tol mm (1e-3 by default) in
the view's x and y. A view agrees when every edge of one side has its match on the other.
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
REPO = HERE.parent.parent
sys.path[:0] = [str(REPO), str(REPO / "tests")]
APP = Path(os.environ.get("FREECAD_APP", "~/.cad-agent/freecad/FreeCAD.app")).expanduser()


def freecadcmd():
    for name in ("freecadcmd", "FreeCADCmd"):
        for bin_dir in (APP / "Contents" / "Resources" / "bin", APP / "usr" / "bin", APP / "bin"):   # the Mac's app, an unpacked AppImage
            p = bin_dir / name
            if p.exists():
                return p
    sys.exit(f"hlrdiff: no freecadcmd in {APP} (set FREECAD_APP)")


def shapes(tmp: Path):
    """[(name, solid, [(view, z_dir, x_dir), ...])]"""
    import importlib.util

    from build123d import Axis, Box, Cylinder, fillet

    import test_drawing as T
    from cad_agent.drawing import platefit

    def plate_views(solid):                               # the directions of onesheet.views_of, first and third angle
        pl = platefit.analyse(solid)
        u, n = pl.frame.u, pl.frame.n
        neg = lambda t: tuple(-x for x in t)                # noqa: E731
        return [("face", n, u), ("left", neg(u), n), ("right", u, neg(n))]

    fixture = tmp / "mini_machine"
    shutil.copytree(REPO / "tests" / "fixtures" / "mini_machine", fixture)
    out = [("panel", T.panel())]
    for part in ("back_wall", "base"):
        spec = importlib.util.spec_from_file_location(f"hlrdiff_{part}", fixture / "parts" / f"{part}.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        out.append((part, mod.build(**mod.PARAMS)))
    got = [(name, solid, plate_views(solid)) for name, solid in out]
    axes = [("z", (0, 0, 1), (1, 0, 0)), ("y", (0, 1, 0), (0, 0, 1)), ("x", (1, 0, 0), (0, 1, 0))]
    knob = Cylinder(10, 20)
    knob = fillet(knob.edges().sort_by(Axis.Z)[-1:], 3.0)
    block = fillet(Box(30, 20, 10).edges(), 2.0)
    got += [("knob", knob, axes), ("block", block, axes)]
    return got


def ours(solid, z, x) -> list:
    from cad_agent.drawing import hlr
    _, _, smooth = hlr.hlr_edges(solid, z, x)
    out = []
    for e in smooth:
        a, b = e.position_at(0), e.position_at(1)
        out.append({"a": [a.X, a.Y], "b": [b.X, b.Y], "length": e.length})
    return out


def close(p, q, tol):
    return abs(p[0] - q[0]) <= tol and abs(p[1] - q[1]) <= tol


def same(e, f, tol):
    ends = (close(e["a"], f["a"], tol) and close(e["b"], f["b"], tol)) or (close(e["a"], f["b"], tol) and close(e["b"], f["a"], tol))
    return ends and abs(e["length"] - f["length"]) <= tol


def err(e, f):
    d = lambda p, q: max(abs(p[0] - q[0]), abs(p[1] - q[1]))     # noqa: E731
    return max(min(max(d(e["a"], f["a"]), d(e["b"], f["b"])), max(d(e["a"], f["b"]), d(e["b"], f["a"]))), abs(e["length"] - f["length"]))


def match(a, b, tol):
    """(pairs, a left over, b left over)"""
    left = list(b)
    pairs, alone = [], []
    for e in a:
        k = next((i for i, f in enumerate(left) if same(e, f, tol)), None)
        if k is None:
            alone.append(e)
        else:
            pairs.append((e, left.pop(k)))
    return pairs, alone, left


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tol", type=float, default=1e-3)
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--timeout", type=int, default=600)
    a = ap.parse_args()
    from build123d import export_step
    with tempfile.TemporaryDirectory(prefix="hlrdiff") as tmp:
        tmp = Path(tmp)
        views, mine = [], {}
        for name, solid, dirs in shapes(tmp):
            step = tmp / f"{name}.step"
            export_step(solid, str(step))
            for view, z, x in dirs:
                key = f"{name}/{view}"
                views.append({"step": str(step), "name": key, "direction": list(z), "xdirection": list(x)})
                mine[key] = ours(solid, z, x)
        inp, outp, home = tmp / "in.json", tmp / "out.json", tmp / "fchome"
        home.mkdir()
        inp.write_text(json.dumps({"views": views}), encoding="utf-8")
        env = {**os.environ, "HLRDIFF_IN": str(inp), "HLRDIFF_OUT": str(outp), "FREECAD_USER_HOME": str(home),
               "FREECAD_USER_DATA": str(home / "data"), "FREECAD_USER_TEMP": str(home / "tmp")}
        r = subprocess.run([str(freecadcmd()), str(HERE / "hlrdiff_fc.py")], env=env, stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=a.timeout)
        if not outp.exists():
            sys.exit(f"hlrdiff: FreeCAD wrote nothing (exit {r.returncode}): {(r.stdout + r.stderr)[-2000:]}")
        fc = json.loads(outp.read_text(encoding="utf-8"))
    print(f"hlrdiff: FreeCAD {fc['freecad']}, tolerance {a.tol:g} mm")
    bad = 0
    total = [0, 0, 0]
    for v in fc["views"]:
        name = v["name"]
        if "error" in v:
            print(f"  {name:18s} FreeCAD failed: {v['error'].strip().splitlines()[-1]}")
            bad += 1
            continue
        pairs, only_ours, only_fc = match(mine[name], v["smooth"], a.tol)
        worst = max((err(e, f) for e, f in pairs), default=0.0)
        ok = not only_ours and not only_fc
        bad += not ok
        total[0] += len(mine[name])
        total[1] += len(v["smooth"])
        total[2] += len(pairs)
        len_o = sum(e["length"] for e in mine[name])
        len_f = sum(e["length"] for e in v["smooth"])
        print(f"  {name:18s} {'same' if ok else 'DIFFERS'}: ours {len(mine[name])} edges {len_o:.4f} mm, FreeCAD {len(v['smooth'])} "
              f"{len_f:.4f} mm, {len(pairs)} matched, worst {worst:.1e} mm")
        for label, es in (("only ours", only_ours), ("only FreeCAD", only_fc)) + ((("both", [e for e, _ in pairs]),) if a.show else ()):
            for e in es:
                print(f"      {label}: ({e['a'][0]:.4f}, {e['a'][1]:.4f}) - ({e['b'][0]:.4f}, {e['b'][1]:.4f}), {e['length']:.4f} mm")
    print(f"hlrdiff: {len(fc['views']) - bad} of {len(fc['views'])} views agree; {total[2]} of {total[0]} edges of ours and "
          f"{total[1]} of FreeCAD's matched")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

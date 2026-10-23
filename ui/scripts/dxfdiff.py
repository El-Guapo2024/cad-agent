#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""The laser DXF (cad_agent/dxf.py) against the real FreeCAD's: the same part through both writers, compared.

A plate with rounded corners, a round hole and an elliptical hole is made with build123d and written by cad_agent.dxf;
the same solid, as a STEP, is read by FreeCAD and the edges of its top face (the face dxf.py writes from) are written
by Import.writeDXFShape
(dxfdiff_fc.py, inside freecadcmd). Then:

  * every section around the entities (HEADER, CLASSES, TABLES, BLOCKS, OBJECTS) is compared line for line, values
    and their padding included, and must differ only where cad_agent/dxf.py says it does on purpose (EXPECTED below);
  * the entities are compared by kind and geometry, in any order: LINE ends, CIRCLE and ARC centre, radius and
    angles, ELLIPSE centre, axis, ratio and parameters, to 1e-6 mm;
  * the file ends as FreeCAD's does ("EOF", no newline);
  * FreeCAD reads ours back (Import.readDXF): as many edges as entities, the cut length and the box of the part.

    python3 ui/scripts/dxfdiff.py            # needs FreeCAD: FREECAD_APP, as for exprdiff.py (the Mac's app or an
                                             # unpacked AppImage), and the repository's .venv
                                             # (CAD_PYTHON names another Python with build123d)
Exit 0 when nothing differs but EXPECTED.
"""
import json
import math
import os
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))
from exprdiff import freecadcmd  # noqa: E402

# (section, the line of FreeCAD's file or None, the line of ours or None): the deliberate differences of dxf.py,
# by content. The comment line and the handles of the layer table, which follow the number of entities, are left out.
EXPECTED = Counter({
    ("HEADER", None, "$MEASUREMENT"): 1, ("HEADER", None, "$EXTMIN"): 1, ("HEADER", None, "$EXTMAX"): 1,
    ("TABLES", "     1", "     3"): 1,                 # the LTYPE table's count
    ("TABLES", "21", "22"): 3,                         # the LTYPE records' owner
    ("TABLES", "     2", "     1"): 1,                 # the DIMSTYLE table's count
    ("TABLES", "5", "2"): 1,                           # the BLOCK_RECORD table's count
})
TOL = 1e-6


def ours(step: Path) -> bytes:
    code = ("import sys\nfrom build123d import *\nfrom cad_agent import dxf\n"
            "with BuildPart() as p:\n    with BuildSketch():\n        RectangleRounded(60, 30, 5)\n"
            "        with Locations((-15, 0)):\n            Circle(3, mode=Mode.SUBTRACT)\n"
            "        with Locations((12, 2)):\n            Ellipse(6, 2.5, mode=Mode.SUBTRACT)\n    extrude(amount=3)\n"
            "export_step(p.part, sys.argv[1])\nsys.stdout.buffer.write(dxf.dxf_of(p.part, 'dxfdiff'))\n")
    py = Path(os.environ.get("CAD_PYTHON", REPO / ".venv" / "bin" / "python"))
    r = subprocess.run([str(py if py.exists() else sys.executable), "-c", code, str(step)], capture_output=True,
                       env={**os.environ, "PYTHONPATH": str(REPO)}, timeout=600)
    if r.returncode:
        sys.exit(f"dxfdiff: our writer failed: {r.stderr.decode()[-800:]}")
    return r.stdout


def sections(lines: list[str]) -> dict:
    """{section name: its lines}, from a file's lines (the 999 comment dropped)."""
    out, name, i = {}, None, 2
    while i < len(lines) - 1:
        code, value = lines[i].strip(), lines[i + 1]
        if code == "0" and value == "SECTION":
            name = lines[i + 3]
            out[name] = []
            i += 4
            continue
        if name:
            out[name] += [lines[i], value]
        i += 2
    return out


def entities(lines: list[str]) -> list:
    """The ENTITIES as (kind, {code: [values]}) with the handles dropped."""
    out, cur = [], None
    for i in range(0, len(lines) - 1, 2):
        code, value = lines[i].strip(), lines[i + 1].strip()
        if code == "0":
            cur = (value, {})
            out.append(cur)
        elif cur and code not in ("5", "330"):
            cur[1].setdefault(code, []).append(value)
    return out


def geometry(kind: str, g: dict) -> tuple:
    nums = {c: [float(v) for v in vs] for c, vs in g.items() if c in ("10", "20", "11", "21", "40", "41", "42", "50", "51")}
    if kind == "LINE":   # either way round
        a, b = (nums["10"][0], nums["20"][0]), (nums["11"][0], nums["21"][0])
        return tuple(sorted((a, b)))
    return tuple((c, tuple(v)) for c, v in sorted(nums.items()))


def close(a, b) -> bool:
    if isinstance(a, tuple) and len(a) == 2 and a[0] in ("50", "51") and isinstance(b, tuple) and b[0] == a[0]:
        # an arc's angle: the half turn is atan2's 180 or -180 by the sign of a rounding error in FreeCAD, 180 in ours
        return len(a[1]) == len(b[1]) and all(abs(x - y) <= TOL or (abs(abs(x) - 180) <= TOL and abs(abs(y) - 180) <= TOL)
                                              for x, y in zip(a[1], b[1]))
    if isinstance(a, (tuple, list)):
        return len(a) == len(b) and all(close(x, y) for x, y in zip(a, b))
    if isinstance(a, str):
        return a == b
    return abs(a - b) <= TOL


def main():
    with tempfile.TemporaryDirectory(prefix="dxfdiff") as tmp:
        tmp = Path(tmp)
        step, mine, theirs = tmp / "plate.step", tmp / "ours.dxf", tmp / "freecad.dxf"
        mine.write_bytes(ours(step))
        job = {"step": str(step), "z": 3.0, "out": str(theirs), "read": str(mine)}
        (tmp / "in.json").write_text(json.dumps(job))
        env = {**os.environ, "DXFDIFF_IN": str(tmp / "in.json"), "DXFDIFF_OUT": str(tmp / "out.json"),
               "FREECAD_USER_HOME": str(tmp / "home")}
        r = subprocess.run([str(freecadcmd()), str(HERE / "dxfdiff_fc.py")], env=env, capture_output=True, text=True, timeout=600)
        if not (tmp / "out.json").exists():
            sys.exit(f"dxfdiff: FreeCAD failed: {(r.stdout + r.stderr)[-800:]}")
        fc = json.loads((tmp / "out.json").read_text())
        a_text, b_text = theirs.read_text(), mine.read_text()

    problems = []
    a, b = a_text.split("\n"), b_text.split("\n")
    print(f"dxfdiff: FreeCAD {fc['freecad']}")
    if (a[-1], b[-1]) != ("EOF", "EOF"):
        problems.append(f"last line: FreeCAD {a[-1]!r}, ours {b[-1]!r}")
    sa, sb = sections(a), sections(b)
    seen = Counter()
    import difflib
    for name in sa:
        if name == "ENTITIES":
            continue
        x, y = sa[name], sb.get(name, [])
        if name == "TABLES":   # the layer table's handles follow the number of entities
            layer = lambda L: [v for i, v in enumerate(L) if not (i % 2 and L[i - 1].strip() in ("5", "330") and v.startswith("A") and len(v) == 3)]
            x, y = layer(x), layer(y)
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, x, y, autojunk=False).get_opcodes():
            if op == "equal":
                continue
            old, new = x[i1:i2], y[j1:j2]
            if op == "insert" and name == "HEADER":
                for v in new:
                    if v.startswith("$"):
                        seen[(name, None, v)] += 1
                continue
            if op == "replace" and len(old) == len(new):
                for u, v in zip(old, new):
                    seen[(name, u, v)] += 1
                continue
            problems.append(f"{name}: FreeCAD {old[:8]} ours {new[:8]}")
    for key, n in seen.items():
        if EXPECTED.get(key, 0) != n:
            problems.append(f"{key[0]}: FreeCAD {key[1]!r} where ours has {key[2]!r} ({n} times)")
    for key, n in EXPECTED.items():
        if seen.get(key, 0) != n:
            problems.append(f"expected difference not found: {key} (wanted {n}, saw {seen.get(key, 0)})")

    ea = [(k, geometry(k, g)) for k, g in entities(sa.get("ENTITIES", [])) if k != "ENDSEC"]
    eb = [(k, geometry(k, g)) for k, g in entities(sb.get("ENTITIES", [])) if k != "ENDSEC"]
    left = list(eb)
    for k, g in ea:
        hit = next((i for i, (k2, g2) in enumerate(left) if k2 == k and close(g, g2)), None)
        if hit is None:
            problems.append(f"FreeCAD's {k} {g} has no match in ours")
        else:
            left.pop(hit)
    problems += [f"ours has a {k} {g} FreeCAD has not" for k, g in left]
    print(f"dxfdiff: entities {Counter(k for k, _ in ea)} (FreeCAD), {len(ea) - len(left) if len(left) <= len(ea) else 0} matched")

    rd = fc["read"]
    length = 2 * 50 + 2 * 20 + 2 * math.pi * 5 + 2 * math.pi * 3
    print(f"dxfdiff: FreeCAD reads ours: {rd['edges']} edges, {rd['length']:.6f} mm, box {rd['box']}")
    if rd["edges"] != len(eb) or rd["box"] is None or not close(tuple(rd["box"]), (-30.0, -15.0, 30.0, 15.0)):
        problems.append(f"FreeCAD read {rd['edges']} edges of {len(eb)}, box {rd['box']}")
    if abs(rd["length"] - (length + ellipse_perimeter(6, 2.5))) > 1e-4:
        problems.append(f"FreeCAD reads a cut length of {rd['length']:.6f} mm, not {length + ellipse_perimeter(6, 2.5):.6f}")
    for p in problems:
        print("  DIFF", p)
    print(f"dxfdiff: {'nothing differs but what dxf.py says' if not problems else f'{len(problems)} differences'}")
    return 1 if problems else 0


def ellipse_perimeter(a: float, b: float, n: int = 200000) -> float:
    return sum(math.hypot(a * math.sin(t), b * math.cos(t)) for t in (2 * math.pi * (i + 0.5) / n for i in range(n))) * 2 * math.pi / n


if __name__ == "__main__":
    sys.exit(main())

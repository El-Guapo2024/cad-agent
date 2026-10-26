"""Writes freecad.json: what FreeCAD 26.3 makes for the Sketcher's text (Sketcher_CreateText), for
tests/test_sketch_text.py to hold cad_agent/sketch_text.py and the solver's Text groups to.

    python3 tests/golden/sketchtext/make.py <freecadcmd>           # writes freecad.json
    python3 tests/golden/sketchtext/make.py <freecadcmd> --check   # and compares with ours

<freecadcmd> may also come from $FREECADCMD (FreeCAD 26.3, weekly-2026.09.30 at 3160daf1e2b6). Each case is a handle
line (p1 to p2), a text, a font file and Width or Height, done as DrawSketchHandlerText::executeCommands does it
(freecad_side.py), then edits: setTextAndFont again (EditTextDialog's change of text, font or method), geometry drawn
after the text, and constraints on the handle, which the solve answers by moving the glyphs with it
(Sketch::applyGroupTransformations). Recorded after each step: every geometry and every constraint (a Text's elements,
text, font and isTextHeight). The fonts are the one cad-agent ships (osifont-lgpl3fe, FreeCAD's default) and the
fonts of this machine that fontconfig lists; each case records its font's SHA-256, and the test skips a case whose
font is not on the machine that runs it.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

STRINGS = ["Text", "Hi", "FreeCAD 26.3", "Ag?!", "jumpy QWERTY", "o", "%&@#", "Ünïcödé àéü", "fi ff -_= 0123456789",
           "  spaced  out  "]
# (file name, the strings it is asked for): the shipped font with every string, the machine's with some
FONTS = [("osifont-lgpl3fe.ttf", STRINGS), ("DejaVuSans.ttf", STRINGS[:6]), ("DejaVuSerif-Bold.ttf", STRINGS[1:4]),
         ("FreeSansOblique.ttf", STRINGS[2:5]), ("Loma-Bold.otf", STRINGS[:3]), ("wqy-zenhei.ttc", ["Text", "中文字体"])]


def font_file(name: str) -> str | None:
    sys.path.insert(0, str(ROOT))
    from cad_agent import sketch_text as T
    for p in T.fonts().values():
        if os.path.basename(p) == name:
            return p
    return None


def sha(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def generate() -> list[dict]:
    r = random.Random(26)
    cases = []
    for name, strings in FONTS:
        path = font_file(name)
        if path is None:
            print(f"make.py: {name} is not on this machine, left out")
            continue
        for k, text in enumerate(strings):
            for height in (False, True):
                x1, y1 = round(r.uniform(-30, 30), 3), round(r.uniform(-30, 30), 3)
                ang = r.choice([0.0, 90.0, r.uniform(-180, 180)])
                ln = r.choice([10.0, 3.5, r.uniform(1, 80)])
                p2 = [x1 + ln * math.cos(math.radians(ang)), y1 + ln * math.sin(math.radians(ang))]
                cases.append({"name": f"{name} {text!r} {'height' if height else 'width'} {ln:.3g} at {ang:.3g}",
                              "font_name": name, "font_sha256": sha(path), "font": path, "text": text,
                              "height": height, "construction": k % 3 == 2, "p1": [x1, y1], "p2": p2})
    osi = font_file("osifont-lgpl3fe.ttf")
    dejavu = font_file("DejaVuSans.ttf")
    other = dejavu or osi
    L = lambda a, b: {"type": "LineSegment", "start": list(a), "end": list(b)}  # noqa: E731
    base = {"font_name": "osifont-lgpl3fe.ttf", "font_sha256": sha(osi), "font": osi, "construction": False}
    # EditTextDialog's changes: text, font, method, construction kept from the glyphs
    cases.append({**base, "name": "edit the text", "text": "Hi", "height": True, "p1": [0, 0], "p2": [0, 10],
                  "edits": [{"op": "set", "index": 0, "text": "Hello", "font": osi, "height": True,
                             "construction": False}]})
    cases.append({**base, "name": "edit the font and the method", "text": "Ab", "height": False, "p1": [5, 5],
                  "p2": [25, 9], "edits": [{"op": "set", "index": 0, "text": "Ab", "font": other, "height": True,
                                           "construction": False}],
                  "edit_font_name": os.path.basename(other), "edit_font_sha256": sha(other)})
    cases.append({**base, "name": "a construction text edited", "text": "Ab", "height": True, "construction": True,
                  "p1": [1, 1], "p2": [1, 6], "edits": [{"op": "set", "index": 0, "text": "Abc", "font": osi,
                                                         "height": True, "construction": False}]})
    # geometry before the text and after it (the handle is not last when the text is edited)
    cases.append({**base, "name": "geometry before and after, then an edit", "text": "xy", "height": True,
                  "before": [L((0, 0), (10, 0)), L((10, 0), (10, 10))], "p1": [20, 0], "p2": [20, 5],
                  "edits": [{"op": "geometry", "geo": L((-5, -5), (-5, 5))},
                            {"op": "set", "index": 0, "text": "xyz", "font": osi, "height": False,
                             "construction": False},
                            {"op": "set", "index": 0, "text": "w", "font": osi, "height": True,
                             "construction": False}]})
    # constraints on the handle: the glyphs follow it (moved, turned, scaled)
    for k in range(8):
        x1, y1 = round(r.uniform(-20, 20), 3), round(r.uniform(-20, 20), 3)
        ang = r.uniform(-180, 180)
        ln = r.uniform(2, 30)
        p2 = [x1 + ln * math.cos(math.radians(ang)), y1 + ln * math.sin(math.radians(ang))]
        edits = []
        if k % 4 == 0:
            edits = [{"op": "constraint", "type": "Horizontal", "args": [0]},
                     {"op": "constraint", "type": "DistanceX", "args": [0, 1, 0, 2], "value": 20.0}]
        elif k % 4 == 1:
            edits = [{"op": "constraint", "type": "Coincident", "args": [0, 1, -1, 1]},
                     {"op": "constraint", "type": "Angle", "args": [0], "value": math.radians(30.0)},
                     {"op": "constraint", "type": "Distance", "args": [0], "value": 12.5}]
        elif k % 4 == 2:
            edits = [{"op": "constraint", "type": "Vertical", "args": [0]},
                     {"op": "constraint", "type": "DistanceY", "args": [-1, 1, 0, 1], "value": 4.0},
                     {"op": "constraint", "type": "DistanceX", "args": [-1, 1, 0, 1], "value": -3.0},
                     {"op": "constraint", "type": "Distance", "args": [0], "value": 7.0}]
        else:
            edits = [{"op": "constraint", "type": "DistanceX", "args": [-1, 1, 0, 1], "value": 2.0},
                     {"op": "constraint", "type": "DistanceY", "args": [-1, 1, 0, 1], "value": 1.0},
                     {"op": "constraint", "type": "DistanceX", "args": [-1, 1, 0, 2], "value": 15.0},
                     {"op": "constraint", "type": "DistanceY", "args": [-1, 1, 0, 2], "value": -6.0},
                     {"op": "set", "index": 0, "text": "moved", "font": osi, "height": False,
                      "construction": False}]
        cases.append({**base, "name": f"constraints on the handle {k}", "text": ["Go", "R2", "text", "K"][k % 4],
                      "height": k % 2 == 0, "p1": [x1, y1], "p2": p2, "edits": edits})
    return cases


def run_freecad(freecadcmd: str, cases: list[dict]) -> list[dict]:
    with tempfile.TemporaryDirectory() as tmp:
        cin, cout = Path(tmp) / "cases.json", Path(tmp) / "answers.json"
        cin.write_text(json.dumps(cases))
        env = {**os.environ, "SKETCHTEXT_CASES": str(cin), "SKETCHTEXT_ANSWERS": str(cout)}
        # tests/golden/sketcher/bump_malloc.c: the solver's parameters ordered as they are made, as in the port, so
        # that an under-constrained step is FreeCAD's one answer (see that file)
        so = Path(tmp) / "bump_malloc.so"
        subprocess.run([os.environ.get("CC", "cc"), "-O2", "-shared", "-fPIC", "-o", str(so),
                        str(HERE.parent / "sketcher" / "bump_malloc.c")], check=True)
        env["LD_PRELOAD"] = str(so)
        subprocess.run([freecadcmd, str(HERE / "freecad_side.py")], env=env, check=True, stdout=subprocess.DEVNULL)
        return json.loads(cout.read_text())


def portable(case: dict) -> dict:
    """The case as stored: font files by name (and hash), not by this machine's paths."""
    out = {k: v for k, v in case.items() if k != "font"}
    for e in out.get("edits", []):
        if "font" in e:
            e["font"] = os.path.basename(e["font"])
    return out


def main(argv):
    fc = argv[1] if len(argv) > 1 and not argv[1].startswith("--") else os.environ.get("FREECADCMD")
    if not fc:
        sys.exit("usage: make.py <freecadcmd> [--check]")
    cases = generate()
    answers = run_freecad(fc, cases)
    out = {"about": "FreeCAD 26.3 (3160daf1e2b6) on Sketcher_CreateText (setTextAndFont, the Text groups' solve), "
                    "written by tests/golden/sketchtext/make.py; tests/test_sketch_text.py compares.",
           "cases": [{**portable(c), "freecad": a} for c, a in zip(cases, answers)]}
    (HERE / "freecad.json").write_text(json.dumps(out, indent=0, ensure_ascii=False) + "\n")
    errors = [c["name"] for c, a in zip(cases, answers) if "error" in a]
    print(f"wrote {HERE / 'freecad.json'}: {len(cases)} cases, {len(errors)} FreeCAD errors")
    for e in errors[:10]:
        print("  error:", e)
    if "--check" in argv:
        sys.path.insert(0, str(ROOT))
        sys.path.insert(0, str(ROOT / "tests"))
        from test_sketch_text import compare_all
        bad, skipped = compare_all(out["cases"])
        for name, why in bad[:40]:
            print(f"DIFF {name}: {why}")
        print(f"{len(out['cases']) - len(bad) - skipped} of {len(out['cases'])} cases equal, {skipped} skipped")


if __name__ == "__main__":
    main(sys.argv)

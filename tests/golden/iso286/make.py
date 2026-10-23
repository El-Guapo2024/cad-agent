"""Writes freecad.json: FreeCAD TechDraw's ISO 286 answers, for tests/test_holes_fit.py to hold cad_agent/iso286.py to.

    python3 tests/golden/iso286/make.py <FreeCAD>/Mod/TechDraw/TechDrawTools/TaskHoleShaftFit.py

It runs that file's class ISO286 (the Hole/Shaft Fit tool's tables, pure Python) for every class the tool
offers at 27 sizes, and records (lower, upper) in micrometres, or null where the tool raises.
"""
import ast
import json
import sys
from pathlib import Path

src = Path(sys.argv[1]).read_text()
cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "ISO286")
ns = {}
exec(compile(ast.Module([cls], []), "TaskHoleShaftFit.py", "exec"), ns)

CLASSES = "c11 f7 h6 h7 h9 k6 n6 r6 s6 D10 E9 F8 G7 H7 H8 H11 K7 N7 R7 S7".split()
SIZES = [1, 2.5, 4, 8, 12, 16, 20, 27, 35, 45, 55, 70, 90, 110, 130, 150, 170, 190, 210, 240, 260, 300,
         330, 380, 420, 470, 499]
out = {}
for c in CLASSES:
    for s in SIZES:
        iso = ns["ISO286"]()
        try:
            iso.calculate(s, c[0], int(c[1:]))
            v = sorted(round(x * 1000, 3) for x in iso.getValues())
        except IndexError:
            v = None
        out[f"{c} {s:g}"] = v
Path(__file__).with_name("freecad.json").write_text(json.dumps(out, indent=0) + "\n")
print(len(out), "answers")

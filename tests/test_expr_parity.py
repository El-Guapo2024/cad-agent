"""The workbench's formula engine against the real FreeCAD's: a sample of ui/scripts/exprdiff.py's cases with the answers FreeCAD gave.

ui/scripts/exprdiff.py puts some 75,000 expressions through FreeCAD (DocumentObject.evalExpression) and through ui/src/expr.ts and
lists every difference; that needs the UI's node_modules (and FreeCAD, to record new answers), so it is a script. This is the part CI can run:

  * tests/golden/expr/cases.json  a few hundred of those cases, every kind of answer and every category among them, with the
    answers FreeCAD 26.3.0 (main 3160daf1e2b6) gave, and a hash of the sources the engine is made of;
  * tests/golden/expr/engine.mjs  expr.ts and what it uses, bundled for Node (`python3 ui/scripts/exprdiff.py
    --emit-engine tests/golden/expr/engine.mjs --emit-fixture tests/golden/expr/cases.json` makes both from the stored answers).

The sample goes through the engine under Node and every answer is held to FreeCAD's by the same comparison the script uses (type,
value to a few units in the last place, dimensions, exception class and message). The engine is checked to be current: if a source
changed since it was bundled, this says so, and the fix is to run the command above.
"""
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
GOLDEN = REPO / "tests" / "golden" / "expr"
SCRIPTS = REPO / "ui" / "scripts"


def load_exprdiff():
    spec = importlib.util.spec_from_file_location("exprdiff", SCRIPTS / "exprdiff.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["exprdiff"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def exprdiff():
    return load_exprdiff()


@pytest.fixture(scope="module")
def sample():
    return json.loads((GOLDEN / "cases.json").read_text(encoding="utf-8"))


def test_the_sample_is_broad(sample):
    cases = sample["cases"]
    assert len(cases) >= 300
    categories = Counter(c["c"] for c in cases)
    for name in ("num", "unit", "unit2", "upow", "building", "op", "cond", "fn", "const", "str", "var", "py", "geom", "fctest", "lex", "uconv",
                 "lex2", "fmt", "rand", "fuzz", "mutate", "numfuzz", "idfuzz", "wsfuzz"):
        assert categories[name] >= 2, f"no cases of the {name} family"
    values = {c["r"]["t"] for c in cases if "t" in c["r"]}
    assert {"int", "float", "bool", "str", "quantity", "list", "tuple", "none", "vector"} <= values
    errors = {c["r"]["etype"] for c in cases if "error" in c["r"]}
    assert {"ParserError", "TypeError", "ZeroDivisionError", "ArithmeticError", "OverflowError", "ExpressionError", "RuntimeError",
            "ValueError", "IndexError", "AttributeError", "FreeCADError"} <= errors
    # the answers carry the reasons the evaluator is modelled on Python: a Quantity is not a float, a bool is a number, 1/2 is not 0
    answers = {c["e"]: c["r"] for c in cases}
    assert answers["1 + 2"]["t"] == "int" and answers["7 / 2"]["t"] == "float" and answers["sin(30)"]["t"] == "quantity"
    assert answers["2+3==4"]["t"] == "bool" and answers["<<a>> + <<b>>"]["v"] == "ab"


def test_the_engine_is_the_one_the_sources_make(sample, exprdiff):
    assert (GOLDEN / "engine.mjs").is_file()
    assert sample["sources"] == exprdiff.source_hash(), (
        "ui/src/expr*.ts, quantity.ts, units-data.ts, units-schemas.ts or ui/scripts/exprdiff-entry.ts changed since tests/golden/expr/engine.mjs "
        "was bundled: run `python3 ui/scripts/exprdiff.py --emit-engine tests/golden/expr/engine.mjs --emit-fixture tests/golden/expr/cases.json` "
        "(it needs the UI's node_modules) and commit both files")


def test_the_engine_answers_as_freecad_did(sample, exprdiff, tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    cases = sample["cases"]
    texts = tmp_path / "texts.json"
    answers = tmp_path / "answers.json"
    texts.write_text(json.dumps([c["e"] for c in cases]), encoding="utf-8")
    run = subprocess.run([node, str(SCRIPTS / "exprdiff_ours.mjs"), (GOLDEN / "engine.mjs").resolve().as_uri(), str(texts), str(answers)],
                         capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr
    ours = json.loads(answers.read_text(encoding="utf-8"))
    assert len(ours) == len(cases)
    differ = []
    for case, o in zip(cases, ours):
        d = exprdiff.differs(o, case["r"])
        if d and not exprdiff.excused(o, case["r"]):
            differ.append(f"{case['c']} {case['e']!r}: {d[0]}\n    ours    {exprdiff.show(o)}\n    FreeCAD {exprdiff.show(case['r'])}")
    assert not differ, f"{len(differ)} of {len(cases)} answers differ from FreeCAD's:\n" + "\n".join(differ[:12])


def test_the_comparison_catches_what_it_is_for(exprdiff):
    one = {"t": "int", "v": "1"}
    assert exprdiff.differs(one, one) is None
    assert exprdiff.differs({"t": "float", "v": 1.0}, one)[0] == "type"
    assert exprdiff.differs({"t": "int", "v": "2"}, one)[0] == "value"
    q = {"t": "quantity", "v": 1.0, "dims": [1, 0, 0, 0, 0, 0, 0, 0]}
    assert exprdiff.differs({**q, "dims": [2, 0, 0, 0, 0, 0, 0, 0]}, q)[0] == "dims"
    assert exprdiff.differs({"t": "quantity", "v": 1.0 + 4e-16, "dims": q["dims"]}, q) is None
    assert exprdiff.differs({"t": "quantity", "v": 1.001, "dims": q["dims"]}, q)[0] == "value"
    err = {"error": "division by zero\nin expression: 1 / 0", "etype": "ZeroDivisionError"}
    assert exprdiff.differs(err, err) is None
    assert exprdiff.differs({**err, "etype": "ArithmeticError"}, err)[0] == "etype"
    assert exprdiff.differs({**err, "error": "division by zero"}, err)[0] == "message"
    assert exprdiff.differs(err, one)[0] == "missing" and exprdiff.differs(one, err)[0] == "accepted"
    nan = {"t": "float", "v": "nan"}
    assert exprdiff.differs(nan, nan) is None and exprdiff.differs({"t": "float", "v": "-0.0"}, {"t": "float", "v": 0.0})[0] == "value"


def test_the_cases_are_deterministic_and_wide(exprdiff):
    import exprdiff_cases
    first = exprdiff_cases.cases()
    again = exprdiff_cases.cases()
    assert first == again and len(first) >= 60000
    assert len({t for _, t in first}) == len(first)                      # no case twice
    assert all(isinstance(t, str) and "\0" not in t for _, t in first)   # FreeCAD's evalExpression takes a C string
    assert len(exprdiff_cases.UNITS) == 132                              # every UNIT and USUNIT token of Expression.l
    digest = hashlib.sha256("\n".join(t for _, t in first).encode("utf-8")).hexdigest()
    assert len(digest) == 64

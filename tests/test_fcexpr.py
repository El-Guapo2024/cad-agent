"""The server's formula engine (cad_agent/fcexpr.py: ui/src/expr.ts bundled into cad_agent/fcexpr_engine.js, run in V8)
against the real FreeCAD's answers.

tests/golden/expr/cases.json holds a sample of ui/scripts/exprdiff.py's cases with the answers FreeCAD 26.3.0 (main 3160daf1e2b6)
gave; every one goes through cad_agent.fcexpr (the bundle and the Python glue: values, trees and hooks) and is held to
FreeCAD's by exprdiff's own comparison. (All 75,558 stored answers: `python3 ui/scripts/exprdiff_py.py`.) The bundle must be
of the current TS sources (ui/scripts/fcexprjs.py).
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from cad_agent import fcexpr as F

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "ui" / "scripts"
L = (1, 0, 0, 0, 0, 0, 0, 0)


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def exprdiff():
    return _load("exprdiff", "exprdiff.py")


@pytest.fixture(scope="module")
def runner():
    return _load("exprdiff_py", "exprdiff_py.py")


@pytest.fixture(scope="module")
def sample():
    return json.loads((REPO / "tests" / "golden" / "expr" / "cases.json").read_text(encoding="utf-8"))


def test_the_engine_answers_as_freecad_did(sample, exprdiff, runner):
    cases = sample["cases"]
    assert len(cases) >= 1500
    ours = runner.run_all([c["e"] for c in cases])
    differ = []
    for case, o in zip(cases, ours):
        d = exprdiff.differs(o, case["r"])
        if d and not exprdiff.excused(o, case["r"]):
            differ.append(f"{case['c']} {case['e']!r}: {d[0]}\n    ours    {exprdiff.show(o)}\n    FreeCAD {exprdiff.show(case['r'])}")
    assert not differ, f"{len(differ)} of {len(cases)} answers differ from FreeCAD's:\n" + "\n".join(differ[:12])
    assert F.QUIRKS.int32_cast is False   # run_all puts it back


def test_the_engine_bundle_is_current():
    gen = _load("fcexprjs", "fcexprjs.py")
    assert gen.bundled_hash() == gen.source_hash(), "ui/src/expr.ts or what it uses changed: run python3 ui/scripts/fcexprjs.py"


def test_to_text_round_trips(sample):
    """Expression::toString reads back as the same text, except where FreeCAD's own does not: a power of a number with a unit
    ("(1 mm) ^ 2" prints as "1 mm ^ 2", which reads as 1 (mm ^ 2)) and an object named by a <<string>>."""
    names = frozenset(sample["names"])
    n = 0
    for case in sample["cases"]:
        try:
            tree = F.parse(case["e"], names, "Obj")
        except F.ExprError:
            continue
        text = F.to_text(tree)
        try:
            again = F.to_text(F.parse(text, names, "Obj"))
        except F.ExprError:
            again = None
        if again != text:
            assert "^" in case["e"] or "<<" in case["e"], (case["e"], text, again)
            continue
        n += 1
    assert n > 1500


def test_user_string_and_units():
    assert F.user_string(F.Quantity(12.5, L), 0, 2, 8) == ("12.50 mm", 1.0, "mm")
    assert F.user_string(F.Quantity(12500, L), 0, 2, 8)[0] == "12.50 m"
    assert F.user_string(F.Quantity(25.4 * 13.5, L), 5, 2, 8)[0] == "1' 1\" + 1/2\""
    assert F.to_number(0.1, "Fixed", 20) == "0.10000000000000000555"
    assert F.parse_unit("cm") == (L, 10.0) and F.parse_unit("1/mm") == ((-1, 0, 0, 0, 0, 0, 0, 0), 1.0)
    with pytest.raises(F.ExprError) as e:
        F.parse_unit("2 mm")
    assert (e.value.etype, e.value.message) == ("ExpressionError", "Expression is not a unit.")
    assert F.is_token_a_unit("mm") and not F.is_token_a_unit('"') and not F.is_token_a_unit("mmx")
    assert F.is_token_a_constant("pi") and not F.is_token_a_constant("pi2")


def test_values_and_errors():
    env = F.Env({"pLen": F.Quantity(10, L), "pCnt": 3}, owner="Obj")
    assert F.evaluate_value("pLen * pCnt + 1 cm", env).value == 40.0
    assert F.evaluate_value("7 / 2", env) == 3.5 and F.evaluate_value("2 ^ 70", env) == 2 ** 70
    assert F.py_str(F.evaluate_value("pLen", env)) == "10.0 mm"
    assert F.evaluate_value("str(pCnt) + <<x>>", env) == "3x" and F.evaluate_value("vector(1; 2; 3)", env) == F.Vector(1, 2, 3)
    with pytest.raises(F.ExprError) as e:
        F.evaluate_value("1 / 0", env)
    assert e.value.etype == "ZeroDivisionError" and e.value.message == "division by zero\nin expression: 1 / 0"
    with pytest.raises(F.ExprError) as e:
        F.evaluate_value("nope + 1", env)
    assert e.value.etype == "RuntimeError"
    with pytest.raises(F.ExprError) as e:
        F.evaluate_value("-" * 5000 + "1", env)
    assert (e.value.etype, e.value.message) == ("RecursionError", "maximum recursion depth exceeded")


def test_identifiers_and_cells():
    tree = F.parse("sum(A1:B2) + x")
    assert [p.names for p in F.identifiers(tree)] == [["A1"], ["B1"], ["A2"], ["B2"], ["x"]]
    assert F.evaluate(tree, F.Env({"A1": 1, "B2": F.Quantity(2, (0,) * 8), "x": 5})) == 8
    hook = F.Env({"x": 5}, range_cells=lambda r: [("A1", 1, "int"), ("A2", True, "bool")])
    with pytest.raises(F.ExprError) as e:
        F.evaluate(tree, hook)
    assert e.value.message == "Invalid property type for aggregate.\nin expression: sum(A1:B2)"
    assert F.evaluate(F.parse("list(A1:B2)"), hook) == [1, True]


def test_hooks():
    def resolve(path):
        assert path.names[0] == "Box"
        return F.Quantity(7, L), path.names[2:]
    env = F.Env({}, owner="Obj", resolve=resolve)
    assert F.evaluate_value("Box.Length * 2", env).value == 14.0
    assert F.evaluate_value("Box.Length.Value", env) == 7.0
    assert F.evaluate_value("Obj.x", F.Env({"x": 3}, owner="Obj")) == 3
    tree = F.parse("Box.Length.Value", resolve_ambiguity=lambda obj, prop, owner: F.VarPath(obj=obj, names=[prop], forced=True))
    assert tree.path.obj.name == "Box" and tree.path.names == ["Length", "Value"] and F.to_text(tree) == "Box.Length.Value"
    env = F.Env({}, owner="Obj", resolve=lambda path: (F.Quantity(7, L), path.names[1:]))
    assert F.evaluate(tree, env) == 7.0
    failing = F.Env({}, owner="Obj", resolve=lambda path: (_ for _ in ()).throw(F.ExprError("Property 'Length' not found in 'Box'", "RuntimeError")))
    with pytest.raises(F.ExprError) as e:
        F.evaluate(tree, failing)
    assert e.value.message == "Property 'Length' not found in 'Box'"
    assert F.evaluate(F.parse("1 ? 2 : Box.Length"), failing) == 2   # a name the evaluation never reaches is never an error

"""cad_agent/assembly_wb.py and ui/ondsel against FreeCAD's Assembly workbench: every case of
tests/golden/assembly/cases.py replayed through our commands, each step's component placements, joint references
and JCS held to what freecadcmd recorded (tests/golden/assembly/freecad.json, make.py), and the ASMT system each
case ends with (exportAsASMT) compared number by number."""
import json
import math
import re
import shutil
import sys
from pathlib import Path

import pytest

from cad_agent import ondsel

HERE = Path(__file__).resolve().parent / "golden" / "assembly"
sys.path.insert(0, str(HERE))
from cases import CASES  # noqa: E402

GOLD = json.loads((HERE / "freecad.json").read_text())["cases"]
pytestmark = pytest.mark.skipif(not ondsel.available(), reason="ui/ondsel is not built (ui/ondsel/build.sh native)")

POS_TOL = 1e-6           # mm
ROT_TOL = 1e-8           # quaternion components (q and -q are the same rotation)


def replay(c):
    from cad_agent import assembly_wb as W
    from cad_agent import feature_part as Part
    shapes = {}
    for pname, objs in c["parts"].items():
        shapes[pname] = Part.evaluate(objs, {})[objs[-1].name]
    objects = [W.Link(n, p, placement=pl) for n, p, pl in c["components"]]
    objects += [W.GroundedJoint("GroundedJoint" if i == 0 else f"GroundedJoint{i:03d}", g)
                for i, g in enumerate(c["ground"])]
    doc = W.AssemblyDocument(objects, shapes)
    doc.recompute()
    steps = []
    for step in c["steps"]:
        op = step["op"]
        if op == "joint":
            W.create_joint(doc, step["type"], step["ref1"], step["ref2"], step["props"])
        elif op == "set":
            doc.set(doc.get(step["joint"]), step["prop"], step["value"])
            doc.recompute()
        elif op == "reverse":
            j = doc.get(step["joint"])
            doc.flip_one_part(j)
            doc.accept(j)
        elif op == "move":
            doc.plc[step["link"]] = W.to_placement(step["placement"])
            doc.recompute()
        elif op == "suppress":
            doc.get(step["joint"]).suppressed = step["value"]
            doc.recompute()
        steps.append(state(doc))
    final = doc.solve()
    return doc, steps, final


def plc_list(p):
    return [*p.pos, *p.rot.q]


def state(doc):
    joints = {}
    for j in doc.joints():
        p1, p2 = doc.jcs[j.name]
        joints[j.name] = {"label": j.label, "type": j.joint_type,
                          "reference1": None if j.reference1 is None else [j.reference1[0], list(j.reference1[1])],
                          "reference2": None if j.reference2 is None else [j.reference2[0], list(j.reference2[1])],
                          "placement1": plc_list(p1), "placement2": plc_list(p2)}
    return {"placements": {n: plc_list(p) for n, p in doc.plc.items()}, "joints": joints}


def same_plc(a, b):
    if max(abs(x - y) for x, y in zip(a[:3], b[:3])) > POS_TOL:
        return False
    qa, qb = a[3:], b[3:]
    return (max(abs(x - y) for x, y in zip(qa, qb)) <= ROT_TOL
            or max(abs(x + y) for x, y in zip(qa, qb)) <= ROT_TOL)


def diff_state(ours, theirs, where):
    out = []
    for n, p in theirs["placements"].items():
        if not same_plc(ours["placements"][n], p):
            out.append(f"{where} {n}.Placement {fmt(ours['placements'][n])} != FreeCAD {fmt(p)}")
    for n, j in theirs["joints"].items():
        mine = ours["joints"].get(n)
        if mine is None:
            out.append(f"{where} no joint {n}")
            continue
        for k in ("label", "type", "reference1", "reference2"):
            if mine[k] != j[k]:
                out.append(f"{where} {n}.{k} {mine[k]!r} != FreeCAD {j[k]!r}")
        for k in ("placement1", "placement2"):
            if not same_plc(mine[k], j[k]):
                out.append(f"{where} {n}.{k} {fmt(mine[k])} != FreeCAD {fmt(j[k])}")
    return out


def fmt(p):
    return "(" + ", ".join(f"{x:.9g}" for x in p) + ")"


NUM = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def same_asmt(a: str, b: str, tol=1e-6):
    """The two ASMT files line by line, numbers to tol (relative to 1), words exactly."""
    la, lb = a.strip().splitlines(), b.strip().splitlines()
    if len(la) != len(lb):
        return f"{len(la)} lines != FreeCAD's {len(lb)}"
    for i, (x, y) in enumerate(zip(la, lb)):
        if NUM.sub("#", x) != NUM.sub("#", y):
            return f"line {i + 1}: {x.strip()!r} != FreeCAD {y.strip()!r}"
        for u, v in zip(NUM.findall(x), NUM.findall(y)):
            if abs(float(u) - float(v)) > tol * max(1.0, abs(float(v))):
                return f"line {i + 1}: {x.strip()!r} != FreeCAD {y.strip()!r}"
    return None


@pytest.fixture(scope="module", params=["native", "wasm"])
def build(request):
    """The native library (cad_agent/ondsel.py's ctypes) and the WebAssembly build the browser runs (ui/ondsel/dist,
    through Node), each held to the same answers."""
    if request.param == "wasm":
        if not shutil.which("node"):
            pytest.skip("node is not installed: the WebAssembly build is not checked")
        ondsel.use_wasm()
    yield request.param
    ondsel.use_native()


@pytest.mark.parametrize("name", list(CASES))
def test_assembly_case_matches_freecad(build, name):
    gold = GOLD[name]
    assert "error" not in gold, gold.get("error")
    doc, steps, final = replay(CASES[name])
    problems = []
    for i, (mine, theirs) in enumerate(zip(steps, gold["steps"])):
        problems += diff_state(mine, theirs, f"step {i + 1}")
    assert final["status"] == gold["solve"]
    problems += diff_state(state(doc), gold["after_solve"], "after solve()")
    bad = same_asmt(doc.export_asmt(), gold["asmt"])
    if bad:
        problems.append(f"exportAsASMT: {bad}")
    assert not problems, "\n".join(problems)


def test_every_case_has_freecads_answer():
    assert set(GOLD) == set(CASES)


def test_angles_are_degrees_and_placements_quaternions():
    from cad_agent import assembly_wb as W
    p = W.to_placement(((1, 2, 3), (90, 0, 0)))
    assert math.isclose(p.rot.q[2], math.sqrt(0.5)) and math.isclose(p.rot.q[3], math.sqrt(0.5))
    assert W.to_placement(W.placement_literal(p)).rot.q == p.rot.q

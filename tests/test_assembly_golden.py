"""cad_agent/assembly_wb.py and ui/ondsel against FreeCAD's Assembly workbench: every case of
tests/golden/assembly/cases.py replayed through our commands, each step's component placements, joint references
and JCS held to what freecadcmd recorded (tests/golden/assembly/freecad.json, make.py), and the ASMT system each
case ends with (exportAsASMT) compared number by number."""
import importlib.util
import json
import math
import re
import shutil
from pathlib import Path

import pytest

from cad_agent import ondsel

HERE = Path(__file__).resolve().parent / "golden" / "assembly"
_spec = importlib.util.spec_from_file_location("assembly_cases", HERE / "cases.py")  # not "cases": each golden has one
_cases = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cases)
CASES = _cases.CASES

GOLD = json.loads((HERE / "freecad.json").read_text())["cases"]
pytestmark = pytest.mark.skipif(not ondsel.available(), reason="ui/ondsel is not built (ui/ondsel/build.sh native)")

POS_TOL = 1e-6           # mm
ROT_TOL = 1e-8           # quaternion components (q and -q are the same rotation)


def replay(c, document="Unnamed"):
    from cad_agent import assembly_link as AL
    from cad_agent import assembly_wb as W
    from cad_agent import feature_part as Part
    subs = {}
    for sname, sc in c.get("subs", {}).items():
        # the sub-assembly's own document, made and solved as a case is: what the AssemblyLink links
        sdoc, _, _ = replay(sc, document=sname)
        sdoc.write_back()
        subs[sname] = AL.SubSource(sname, sdoc.objects, sdoc.shapes)
    shapes = {}
    for pname, objs in c["parts"].items():
        shapes[pname] = Part.evaluate(objs, {})[objs[-1].name]
    objects = [W.Link(n, p, placement=pl) for n, p, pl in c["components"]]
    objects += [W.GroundedJoint("GroundedJoint" if i == 0 else f"GroundedJoint{i:03d}", g)
                for i, g in enumerate(c["ground"])]
    doc = W.AssemblyDocument(objects, shapes, document=document, subs=subs)
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
            o = doc.get(step["joint"])
            if isinstance(o, W.RigidGroupJoint):
                W.set_rigid(doc, o, "suppressed", step["value"])
            else:
                o.suppressed = step["value"]
            doc.recompute()
        elif op == "rigid":
            W.create_rigid_group(doc, step["parts"])
        elif op == "update_rigid":
            W.update_stored_positions(doc, doc.get(step["joint"]))
            doc.recompute()
        elif op == "insert_assembly":
            AL.insert_assembly_link(doc, step["sub"], subs[step["sub"]], rigid=step.get("rigid", True),
                                    placement=(step.get("placement") or (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
                                    ground_first=False)
            doc.recompute()
        elif op == "set_rigid":
            AL.set_rigid(doc, doc.get(step["link"]), step["value"])
            doc.recompute()
        elif op == "exploded_view":
            from cad_agent import assembly_view as AV
            AV.set_view(doc, step["moves"])
            doc.recompute()
        steps.append(state(doc))
    final = doc.solve()
    return doc, steps, final


def plc_list(p):
    return [*p.pos, *p.rot.q]


def state(doc):
    from cad_agent import assembly_wb as W
    joints = {}
    for j in doc.joints():
        p1, p2 = doc.jcs[j.name]
        joints[j.name] = {"label": j.label, "type": j.joint_type,
                          "reference1": None if j.reference1 is None else [j.reference1[0], list(j.reference1[1])],
                          "reference2": None if j.reference2 is None else [j.reference2[0], list(j.reference2[1])],
                          "placement1": plc_list(p1), "placement2": plc_list(p2)}
    rigid = {g.name: {"label": g.label or g.name, "members": list(g.objects_to_rigid_group),
                      "rigid_placements": [plc_list(W.to_placement(p)) for p in g.rigid_placements],
                      "suppressed": g.suppressed} for g in doc.rigid_groups()}
    placements = {n: plc_list(p) for n, p in doc.plc.items()}
    for o in doc.asm_links():                  # a flexible link's Placement is the identity, a rigid one's children
        if not o.rigid:                        # the sources' placements
            placements[o.name] = plc_list(W.Placement())
        placements.update({c: plc_list(p) for c, p in doc.child_plc.items() if doc.child_of[c][0] == o.name})
    out = {"placements": placements, "joints": joints}
    if rigid:
        out["rigid_groups"] = rigid
    links = {o.name: {"rigid": o.rigid, "children": o.children(), "labels": [doc.child_labels[c] for c in o.children()]}
             for o in doc.asm_links()}
    if links:
        out["assembly_links"] = links
    from cad_agent import assembly_view as AV
    exploded = {}
    for v in AV.views(doc):
        final, lines = AV.exploded_placements(doc, v, headless=True, applied=False)
        exploded[v.name] = {"label": v.label or v.name, "moves": list(v.group),
                            "placements": {n: plc_list(p) for n, p in final.items()},
                            "lines": [[list(a), list(b)] for a, b in lines]}
    if exploded:
        out["exploded"] = exploded
    return out


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
    for n, a in theirs.get("assembly_links", {}).items():
        mine = ours.get("assembly_links", {}).get(n)
        if mine != a:
            out.append(f"{where} {n} {mine!r} != FreeCAD {a!r}")
    for n, e in theirs.get("exploded", {}).items():
        mine = ours.get("exploded", {}).get(n)
        if mine is None:
            out.append(f"{where} no exploded view {n}")
            continue
        for k in ("label", "moves"):
            if mine[k] != e[k]:
                out.append(f"{where} {n}.{k} {mine[k]!r} != FreeCAD {e[k]!r}")
        for c, p in e["placements"].items():
            if c not in mine["placements"] or not same_plc(mine["placements"][c], p):
                out.append(f"{where} {n} exploded {c} {mine['placements'].get(c)} != FreeCAD {p}")
        if len(mine["lines"]) != len(e["lines"]) or any(
                max(abs(x - y) for x, y in zip(a + b, c + d)) > POS_TOL
                for (a, b), (c, d) in zip(mine["lines"], e["lines"])):
            out.append(f"{where} {n} lines {mine['lines']} != FreeCAD {e['lines']}")
    for n, g in theirs.get("rigid_groups", {}).items():
        mine = ours.get("rigid_groups", {}).get(n)
        if mine is None:
            out.append(f"{where} no rigid group {n}")
            continue
        for k in ("label", "members", "suppressed"):
            if mine[k] != g[k]:
                out.append(f"{where} {n}.{k} {mine[k]!r} != FreeCAD {g[k]!r}")
        if len(mine["rigid_placements"]) != len(g["rigid_placements"]) or not all(
                same_plc(a, b) for a, b in zip(mine["rigid_placements"], g["rigid_placements"])):
            out.append(f"{where} {n}.RigidPlacements {mine['rigid_placements']} != FreeCAD {g['rigid_placements']}")
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

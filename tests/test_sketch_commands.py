"""cad_agent/sketch_commands.py against FreeCAD 26.3: the Sketcher's commands on sketch objects (Mirror, Merge, Validate,
Reorient, Map) on the sketches of tests/golden/sketchobj/freecad.json (make.py), every geometry and constraint to
1e-9, and `cad feature mirror | merge | reorient | map | validate` on a part file."""
from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import pytest

from cad_agent import sketch_commands as SC
from test_workbench import demo  # noqa: F401 (a scratch project)

GOLDEN = Path(__file__).parent / "golden" / "sketchobj" / "freecad.json"
TOL = 1e-9
NUMS = {"LineSegment": ("start", "end"), "Circle": ("center", "radius"), "Point": ("at",),
        "ArcOfCircle": ("center", "radius", "start_angle", "end_angle"),
        "Ellipse": ("center", "major_radius", "minor_radius", "x_axis"),
        "ArcOfEllipse": ("center", "major_radius", "minor_radius", "x_axis", "start_angle", "end_angle"),
        "ArcOfHyperbola": ("center", "major_radius", "minor_radius", "x_axis", "start_angle", "end_angle"),
        "ArcOfParabola": ("center", "focal", "x_axis", "start_angle", "end_angle"),
        "BSplineCurve": ("poles", "knots", "mults", "degree")}


def _flat(v):
    if isinstance(v, (list, tuple)):
        return [x for e in v for x in _flat(e)]
    return [float(v)]


def geometry_diff(ours: list, theirs: list, tol=TOL) -> str:
    if len(ours) != len(theirs):
        return f"{len(ours)} geometries, FreeCAD {len(theirs)}"
    for i, (a, b) in enumerate(zip(ours, theirs)):
        if a["type"] != b["type"]:
            return f"geometry {i}: {a['type']}, FreeCAD {b['type']}"
        if bool(a.get("construction")) != bool(b.get("construction")):
            return f"geometry {i}: construction {a.get('construction')}, FreeCAD {b.get('construction')}"
        for k in NUMS[a["type"]]:
            x, y = _flat(a.get(k, a.get("point") if k == "at" else None)), _flat(b[k])
            if len(x) != len(y) or any(abs(p - q) > tol for p, q in zip(x, y)):
                return f"geometry {i} {k}: {a.get(k)}, FreeCAD {b[k]}"
    return ""


def constraint_view(c: dict, values=None) -> dict:
    """Our constraint dict as FreeCAD's fields."""
    f = SC.fields(c, values)
    d = {"type": f["type"], "elements": [f["first"], f["first_pos"], f["second"], f["second_pos"], f["third"],
                                         f["third_pos"]], "name": f["name"], "driving": f["driving"]}
    if f["type"] == "InternalAlignment":
        d["alignment"], d["index"] = f["alignment"], f["index"]
    if f["type"] in SC.DIMENSIONAL:
        d["value"] = f["value"]
    return d


def constraints_diff(ours: list, theirs: list, tol=TOL) -> str:
    if len(ours) != len(theirs):
        return f"{len(ours)} constraints, FreeCAD {len(theirs)}: {[c['type'] for c in ours]} / {[c['type'] for c in theirs]}"
    for i, (c, t) in enumerate(zip(ours, theirs)):
        a = constraint_view(c)
        for k in ("type", "elements", "alignment", "index", "name", "driving"):
            if k in t and a.get(k) != t[k]:
                return f"constraint {i} {k}: {a.get(k)}, FreeCAD {t[k]}"
        if "value" in t and abs(a["value"] - t["value"]) > tol:
            return f"constraint {i} value: {a['value']}, FreeCAD {t['value']}"
    return ""


def _planegcs() -> bool:
    try:
        from cad_agent import planegcs
        planegcs.solve({"name": "probe", "geometry": [], "constraints": []})
        return True
    except Exception:
        return False


def _solved(geometry, constraints):
    """Our side of FreeCAD's recompute: (the geometry PlaneGCS solves to, the degrees of freedom left). An
    under-constrained sketch is not repeatable in FreeCAD itself (its solver orders unknowns by memory address), so
    only a fully constrained one is held to FreeCAD's answer."""
    from cad_agent import planegcs
    from cad_agent.feature import Constraint, Sketch, geometry_from_dict
    sk = Sketch("Sketch", geometry=[geometry_from_dict(g) for g in geometry],
                constraints=[Constraint(c["type"], *c["args"], *([c["value"]] if "value" in c else []),
                                        driving=c.get("driving", True)) for c in constraints])
    out = planegcs.solve(sk.as_dict({}))
    return out["geometry"], out.get("dof", -1)


SOLVED = {"compared": 0, "under": 0}


def _satisfied(geometry, constraints) -> bool:
    from cad_agent.feature import Constraint, Sketch, geometry_from_dict
    sk = Sketch("Sketch", geometry=[geometry_from_dict(g) for g in geometry],
                constraints=[Constraint(c["type"], *c["args"], *([c["value"]] if "value" in c else []),
                                        driving=c.get("driving", True)) for c in constraints])
    return not sk.unsatisfied({}, unchecked=False)


def _solved_diff(geometry, constraints, theirs):
    g, dof = _solved(geometry, constraints)
    # FreeCAD's solve leaves a sketch that satisfies its constraints where it is, as ours does; not one with degenerate
    # geometry, which its solver nudges
    if dof != 0 and _satisfied(geometry, constraints) and not SC.degenerated(geometry):
        SOLVED["kept"] = SOLVED.get("kept", 0) + 1
        why = geometry_diff(geometry, theirs, 1e-7)
        return why and "kept " + why
    if dof != 0:
        SOLVED["under"] += 1
        return ""
    SOLVED["compared"] += 1
    why = geometry_diff(g, theirs)
    return why and "solved " + why


def _src(fc_state):
    return [{k: v for k, v in g.items() if k not in ("start_point", "end_point")} for g in fc_state["geometry"]]


def compare(case: dict, solve: bool) -> str:
    fc = case["freecad"]
    if "error" in fc:
        return "FreeCAD: " + fc["error"].strip().splitlines()[-1]
    kind = case["kind"]
    if kind == "mirror":
        m = SC.mirror({"geometry": _src(fc["source"]), "constraints": case["constraints"]}, case["ref"])
        why = geometry_diff(m["geometry"], fc["mirrored"]["geometry"]) or \
            constraints_diff(m["constraints"], fc["mirrored"]["constraints"])
        if why or not solve:
            return why
        return _solved_diff(m["geometry"], m["constraints"], fc["solved"]["geometry"])
    if kind == "merge":
        srcs = [{"name": f"Sketch{i}", "geometry": _src(st), "constraints": s["constraints"]}
                for i, (s, st) in enumerate(zip(case["sketches"], fc["sources"]))]
        m = SC.merge(srcs)
        why = geometry_diff(m["geometry"], fc["merged"]["geometry"]) or \
            constraints_diff(m["constraints"], fc["merged"]["constraints"])
        return why or (_solved_diff(m["geometry"], m["constraints"], fc["solved"]["geometry"]) if solve else "")
    if kind == "validate":
        geo = _src(fc["source"])
        cons = [SC.fields(c) for c in case["constraints"]]
        for key, want in fc["missing"].items():
            tol, incl = key.split()
            got = SC.missing_coincidences(geo, cons, float(tol), incl == "True")
            got = [[m["first"], m["first_pos"], m["second"], m["second_pos"]] for m in got]
            if got != [w[:4] for w in want["list"]]:
                return f"missing coincidences at {key}: {got}, FreeCAD {[w[:4] for w in want['list']]}"
        ov = sorted((round(x, 6), round(y, 6)) for x, y in SC.open_vertices(geo))
        if ov != sorted((round(x, 6), round(y, 6)) for x, y in fc["open"]):
            return f"open vertices {ov}, FreeCAD {sorted(map(tuple, fc['open']))}"
        if (not SC.invalid_constraints(geo, cons)) != fc["valid"]:
            return f"evaluateConstraints {not SC.invalid_constraints(geo, cons)}, FreeCAD {fc['valid']}"
        if len(SC.degenerated(geo)) != fc["degenerated"]:
            return f"{len(SC.degenerated(geo))} degenerated, FreeCAD {fc['degenerated']}"
        for k, lock in (("lock", True), ("unlock", False)):
            if SC.orientation_locking(geo, cons, lock) != fc[k]:
                return f"changeConstraintsLocking({lock}) {SC.orientation_locking(geo, cons, lock)}, FreeCAD {fc[k]}"
        miss = SC.missing_coincidences(geo, cons, 1e-4, False)
        fixed = list(case["constraints"]) + SC.coincidence_constraints(miss)
        why = constraints_diff(fixed, fc["fixed"]["constraints"])
        if why:
            return "Fix: " + why
        g2, c2 = SC.remove_degenerated([dict(g) for g in geo], [dict(c, _i=i) for i, c in enumerate(cons)])
        why = geometry_diff(g2, _src(fc["source"]) if not fc["degenerated"] else
                            [g for i, g in enumerate(_src(fc["source"])) if i not in SC.degenerated(geo)]) or \
            constraints_diff([SC.args_of(c) for c in c2], fc["removed"]["constraints"])
        if why:
            return "removeDegeneratedGeometries: " + why
        if solve:
            why = _solved_diff(geo, fixed, fc["fixed"]["geometry"])
            if why:
                return "Fix: " + why
        return ""
    return f"unknown kind {kind}"


def compare_all(cases, solve=None) -> list:
    solve = _planegcs() if solve is None else solve
    return [(c["name"], why) for c in cases if (why := compare(c, solve))]


@pytest.fixture(scope="module")
def golden():
    return json.loads(GOLDEN.read_text())["cases"]


@pytest.mark.parametrize("kind", ["mirror", "merge", "validate"])
def test_against_freecad(golden, kind):
    cases = [c for c in golden if c["kind"] == kind]
    assert cases
    bad = compare_all(cases)
    assert not bad, f"{len(bad)} of {len(cases)} differ: " + "; ".join(f"{n}: {w}" for n, w in bad[:5])


def test_constraint_fields_round_trip(golden):
    for c in golden:
        for cons in [c.get("constraints", [])] + [s["constraints"] for s in c.get("sketches", [])]:
            for k in cons:
                back = SC.args_of(SC.fields(k))
                assert back["type"] == k["type"] and back["args"] == k["args"], (k, back)


@pytest.mark.parametrize("plane,reverse,q", [
    ("XY", False, (0, 0, 0, 1)), ("XY", True, (1, 0, 0, 0)), ("XZ", False, (math.sqrt(.5), 0, 0, math.sqrt(.5))),
    ("XZ", True, (0, math.sqrt(.5), math.sqrt(.5), 0)), ("YZ", False, (.5, .5, .5, .5)), ("YZ", True, (-.5, .5, .5, -.5))])
def test_reorient_placement(plane, reverse, q):
    pos, rot = SC.reorient(plane, reverse, 12.3456789)
    assert all(abs(a - b) < 1e-6 for a, b in zip(rot, q))
    assert pos == {"XY": (0, 0, 12.345679), "XZ": (0, 12.345679, 0), "YZ": (12.345679, 0, 0)}[plane]


def test_cpp_sort_matches_a_strict_order():
    import random
    r = random.Random(3)
    for n in (0, 1, 5, 16, 17, 40, 200):
        a = [r.random() for _ in range(n)]
        b = list(a)
        SC._cpp_sort(b, lambda x, y: x < y)
        assert b == sorted(a)


# ── the commands on a part file ────────────────────────────────────────────────────────────────────────────────

PART = '''from cad_agent.feature import (ArcOfCircle, Body, Circle, Constraint, LineSegment, Pad, Point, Sketch)

PARAMS = {"w": 30.0}

FEATURES = [
    Sketch("Sketch", support="XY",
           geometry=[LineSegment((0.0, 0.0), (30.0, 0.0)), LineSegment((30.0, 0.0), (30.0, 20.0)),
                     LineSegment((30.0, 20.0), (0.0, 20.0)), LineSegment((0.0, 20.0), (0.0, 0.0))],
           constraints=[Constraint("Coincident", 0, 2, 1, 1), Constraint("Coincident", 1, 2, 2, 1),
                        Constraint("Coincident", 2, 2, 3, 1), Constraint("Coincident", 3, 2, 0, 1),
                        Constraint("Horizontal", 0), Constraint("Horizontal", 2), Constraint("Vertical", 1),
                        Constraint("Vertical", 3), Constraint("DistanceX", 0, 1, 0, 2, "w"),
                        Constraint("Coincident", 0, 1, -1, 1)]),
    Pad("Pad", "Sketch", length=5.0),
    Sketch("Sketch001", support="XZ", attachment_offset=(0.0, 0.0, 3.0),
           geometry=[Circle((5.0, 5.0), 2.0), LineSegment((10.0, 0.0), (20.0, 0.0)),
                     LineSegment((20.0, 1e-05), (20.0, 8.0))],
           constraints=[Constraint("Radius", 0, 2.0)]),
    Sketch("Sketch002", geometry=[LineSegment((40.0, 40.0), (40.0, 40.00000001))]),
]


def build(**p):
    return Body(FEATURES, p)
'''


@pytest.fixture()
def part_file(tmp_path):
    p = tmp_path / "Plate.py"
    p.write_text(PART)
    return p


def test_mirror_ops(part_file):
    out = SC.mirror_ops(part_file, ["Sketch001"], "Y")
    (op,) = out["ops"]
    f = op["feature"]
    assert out["step"] == "Create a mirrored sketch for each selected sketch"
    assert f["name"] == "MirroredSketch" and f["map_mode"] == "Deactivated" and op["after"] == "Sketch002"
    assert f["geometry"][0]["center"] == [-5.0, 5.0]
    pos, ypr = f["placement"]
    assert pos == pytest.approx([0.0, -3.0, 0.0], abs=1e-9)        # XZ's normal is -Y: the offset 3 along it
    assert [c["type"] for c in f["constraints"]] == ["Radius"]


def test_merge_ops(part_file):
    out = SC.merge_ops(part_file, ["Sketch", "Sketch001"])
    f = out["ops"][0]["feature"]
    assert f["name"] == "Sketch003" and out["step"] == "Merge sketches"
    assert len(f["geometry"]) == 7 and len(f["constraints"]) == 11
    assert f["constraints"][-1] == {"type": "Radius", "args": [4], "value": 2.0, "driving": True, "name": ""}
    dx = f["constraints"][8]
    assert dx["type"] == "DistanceX" and dx["value"] == 30.0            # addCopyOfConstraints leaves the expression


def test_validate(part_file):
    out = SC.validate(part_file, "Sketch001", "coincidences", 1e-4, True)
    assert [(m["first"], m["first_pos"], m["second"], m["second_pos"]) for m in out["missing"]] == [(1, 2, 2, 1)]
    assert out["notification"]["text"] == "1 missing coincidences found"
    out = SC.validate(part_file, "Sketch002", "degenerated")
    assert out["degenerated"] == [0] and out["notification"]["text"] == "1 degenerated geometry found"
    if _planegcs():
        fix = SC.validate(part_file, "Sketch001", "coincidences", 1e-4, True, fix=True)
        props = fix["ops"][0]["props"]
        assert props["constraints"][-1]["type"] == "Coincident" and fix["step"] == "Add coincident constraint"
        assert props["geometry"][1]["end"] == pytest.approx(props["geometry"][2]["start"], abs=1e-9)


def test_reorient_and_map_ops(part_file):
    out = SC.reorient_ops(part_file, "Sketch001", "YZ", True, 4.0)
    props = out["ops"][0]["props"]
    assert props["map_mode"] == "Deactivated" and props["attachment_support"] == []
    assert props["placement"][0] == [4.0, 0.0, 0.0]
    assert SC.map_check(part_file, "Sketch", [("Pad", "Face6")]).startswith("Some of the selected objects depend")
    assert SC.map_check(part_file, "Sketch001", [("Pad", "Face6")]) is None
    out = SC.map_ops(part_file, "Sketch001", [("Pad", "Face6")], "FlatFace")
    assert out["step"] == "Attach sketch"
    assert out["ops"][0]["props"] == {"support": None, "attachment_support": [["Pad", "Face6"]], "map_mode": "FlatFace"}


def test_the_commands_through_cad_feature(demo, capsys):
    """`cad feature mirror | merge | reorient | validate | map` write the part file in one undo step each, named as
    FreeCAD names the transaction; --dry answers with the ops and writes nothing."""
    from cad_agent import cli
    from cad_agent import undo as un
    from test_cli import run
    (demo / "parts" / "Plate.py").write_text(PART)
    before = (demo / "parts" / "Plate.py").read_text()
    code, data = run(capsys, "feature", "mirror", "demo", "Plate", "Sketch001", "--ref", "origin", "--dry")
    assert code == cli.OK and data["ops"][0]["feature"]["name"] == "MirroredSketch"
    assert (demo / "parts" / "Plate.py").read_text() == before
    code, data = run(capsys, "feature", "mirror", "demo", "Plate", "Sketch001", "--ref", "origin")
    assert code in (cli.OK, cli.FAIL, cli.UNCHECKED) and data.get("built"), data
    assert [f["name"] for f in data["doc"]["features"]][-1] == "MirroredSketch"
    assert un.load(demo)["undo"][-1]["name"] == "Create a mirrored sketch for each selected sketch"
    code, data = run(capsys, "feature", "merge", "demo", "Plate", "Sketch", "Sketch001")
    assert un.load(demo)["undo"][-1]["name"] == "Merge sketches"
    merged = next(f for f in data["doc"]["features"] if f["name"] == "Sketch003")
    assert len(merged["geometry"]) == 7 and merged["map_mode"] == "Deactivated"
    code, data = run(capsys, "feature", "reorient", "demo", "Plate", "Sketch001", "--plane", "XZ", "--offset", "2")
    sk = next(f for f in data["doc"]["features"] if f["name"] == "Sketch001")
    assert sk["map_mode"] == "Deactivated" and sk["placement"][0] == [0.0, 2.0, 0.0]
    assert un.load(demo)["undo"][-1]["name"] == "Reorient sketch"
    code, data = run(capsys, "feature", "map", "demo", "Plate", "Sketch001", "--support", "Pad.Face6", "--mode", "FlatFace")
    sk = next(f for f in data["doc"]["features"] if f["name"] == "Sketch001")
    assert sk["attachment_support"] == [["Pad", "Face6"]] and un.load(demo)["undo"][-1]["name"] == "Attach sketch"
    code, data = run(capsys, "feature", "map", "demo", "Plate", "Sketch", "--support", "Pad.Face6", "--mode", "FlatFace")
    assert code == cli.USAGE
    code, data = run(capsys, "feature", "validate", "demo", "Plate", "Sketch002", "--check", "degenerated", "--fix")
    sk = next(f for f in data["doc"]["features"] if f["name"] == "Sketch002")
    assert sk["geometry"] == [] and un.load(demo)["undo"][-1]["name"] == "Remove degenerated geometry"
    code, data = run(capsys, "feature", "validate", "demo", "Plate", "Sketch", "--check", "coincidences")
    assert data["notification"]["title"] == "No missing coincidences" and "ops" not in data

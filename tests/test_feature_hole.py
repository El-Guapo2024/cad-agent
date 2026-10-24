"""cad_agent.feature_hole gives what FreeCAD's PartDesign::Hole gives: the same properties for the same choices (its
tables and its onChanged cascade), the same solid, the same refusals; and the part-file layer and `cad feature` take it.

tests/golden/hole/cases.py holds the cases; make.py ran each in FreeCAD 26.3 (3160daf1e2b6) and wrote freecad.json.
"""
import json
import math
from pathlib import Path

import pytest

from cad_agent import feature_edit, feature_hole, feature_hole_tables as T
from cad_agent.feature import Body, FeatureError, Hole

from test_feature_revolve import _measure, load_cases

GOLDEN = Path(__file__).parent / "golden" / "hole"
_c = load_cases(GOLDEN / "cases.py", "hole_cases")
STATES, CASES, ERRORS = _c.STATES, _c.CASES, _c.ERRORS
FC = json.loads((GOLDEN / "freecad.json").read_text())


def test_every_case_has_freecads_answer():
    assert set(STATES) == set(FC["states"]) and set(CASES) == set(FC["cases"]) and set(ERRORS) == set(FC["errors"]), \
        "run tests/golden/hole/make.py in freecadcmd"
    assert not [n for n, s in FC["states"].items() if "error" in s]
    assert not [n for n, g in FC["cases"].items() if "error" in g or not g["valid"]]
    assert len(STATES) >= 60 and len(CASES) >= 25


# The plate's through-all length, as FreeCAD's getThroughAllLength gives it when the properties are set (base: the
# 40 x 20 x 10 plate; the profile's face: the circle of radius 2 at (10, 10, 10)).
PLATE_THROUGH_ALL = 2.02 * math.sqrt(40 ** 2 + 20 ** 2 + 10 ** 2)


@pytest.mark.parametrize("name", sorted(STATES))
def test_same_properties_as_freecad(name):
    want = FC["states"][name]
    st = feature_hole.resolve(STATES[name], PLATE_THROUGH_ALL)
    for prop, fc in want.items():
        if prop.startswith("_"):
            continue
        got = st[feature_hole.CAMEL[prop]]
        if isinstance(fc["value"], float):
            assert got == pytest.approx(fc["value"], abs=1e-9), prop
        else:
            assert got == fc["value"], prop
        assert (feature_hole.CAMEL[prop] in st.ro) == fc["read_only"], f"{prop} read-only"
        if "enums" in fc:
            assert st.e[feature_hole.CAMEL[prop]].items == fc["enums"], f"{prop} enums"


def test_the_tables_are_freecads():
    # a few rows straight from FeatureHole.cpp and Resources/Hole, as the generator copied them
    assert ("M6x1.0", 6.0, 1.0, 5.0) in T.THREADS["ISOMetricProfile"]
    assert len(T.THREADS["ISOMetricFineProfile"]) == 172 and T.THREADS["None"] == [("---", 6.0, 0.0, 0.0)]
    assert (6.0, 6.4, 6.6, 7.0) in T.METRIC_HOLE_DIAMETERS and ("1/4", 6.8, 7.1, 7.5) in T.UTS_HOLE_DIAMETERS
    assert feature_hole.CUTS[("ISOMetricProfile", "ISO 4762")]["data"][7] == ("M6x1.0", 11.0, 6.4)
    assert T.ENUMS["DepthTypeEnums"] == ["Dimension", "ThroughAll"]
    assert FC["states"]["iso"]["hole_cut_type"]["enums"] == feature_hole._ISO_CUT_TYPES


@pytest.mark.parametrize("name", sorted(CASES))
def test_same_solid_as_freecad(name):
    case, want = CASES[name], FC["cases"][name]
    got = _measure(Body(case["features"], case.get("params")))
    assert got["volume"] == pytest.approx(want["volume"], rel=1e-6)
    assert got["area"] == pytest.approx(want["area"], rel=1e-6)
    size = math.dist(want["bbox"][:3], want["bbox"][3:])
    assert got["bbox"] == pytest.approx(want["bbox"], abs=1e-6 * size)
    assert got["center_of_mass"] == pytest.approx(want["center_of_mass"], abs=1e-6 * size)
    assert (got["solids"], got["faces"]) == (want["solids"], want["faces"])
    key = lambda f: tuple(round(x, 4) for x in f)       # noqa: E731
    assert sorted(map(key, got["face_list"])) == sorted(map(key, want["face_list"]))


ORDER_DIFFERS: set = set()


@pytest.mark.parametrize("name", sorted(set(CASES) - ORDER_DIFFERS))
def test_face_names_are_freecads(name):
    case, want = CASES[name], FC["cases"][name]
    got = _measure(Body(case["features"], case.get("params")))
    assert [[round(x, 4) for x in f] for f in got["face_list"]] == \
        [[round(x, 4) for x in f] for f in want["face_list"]]


@pytest.mark.parametrize("name", sorted(ERRORS))
def test_refused_in_freecads_words(name):
    words = FC["errors"][name].split(": ", 1)[1]
    with pytest.raises(FeatureError) as e:
        Body(ERRORS[name])
    assert str(e.value) == words


# ── the part file ─────────────────────────────────────────────────────────────────────────────────────────

def test_minimal_keeps_only_what_was_chosen():
    st = feature_hole.resolve({"thread_type": "ISOMetricProfile", "thread_size": "M6x1.0", "hole_cut_type": "ISO 4762"})
    full = st.values()
    assert (full["diameter"], full["hole_cut_diameter"], full["hole_cut_depth"]) == (6.6, 11.0, 6.4)
    assert Hole.minimal(full) == {"thread_type": "ISOMetricProfile", "thread_size": "M6x1.0",
                                  "hole_cut_type": "ISO 4762"}
    # an explicit default is still a choice when setting it moves another property, as in FreeCAD: Diameter sets
    # ThreadDiameter (6 here, 0 on a new Hole) and Depth sets ThreadDepth (25, not 23.5); DrillPoint and Tapered move none
    assert Hole.minimal({"diameter": 6.0, "depth": 25.0}) == {"diameter": 6.0, "depth": 25.0}
    assert Hole.minimal({"drill_point": "Angled", "tapered": False}) == {}


TEMPLATE = '''from cad_agent.feature import (ArcOfCircle, Body, Circle, Constraint, LineSegment, Pad, Pocket, Point,
                               Sketch)

PARAMS = {"deep": 6.0}

FEATURES = [
    Sketch("Base", support="XY",
           geometry=[LineSegment((0.0, 0.0), (40.0, 0.0)), LineSegment((40.0, 0.0), (40.0, 20.0)),
                     LineSegment((40.0, 20.0), (0.0, 20.0)), LineSegment((0.0, 20.0), (0.0, 0.0))],
           constraints=[]),
    Pad("Pad", "Base", length=10.0),
    Sketch("Holes", support="XY", attachment_offset=(0.0, 0.0, 10.0),
           geometry=[Circle((10.0, 10.0), 2.0), Circle((30.0, 10.0), 2.0)], constraints=[]),
]


def build(**p):
    return Body(FEATURES, p)
'''


def _run(path):
    ns = {}
    exec(compile(path.read_text(), str(path), "exec"), ns)
    return ns["build"](**ns["PARAMS"])


def test_add_set_round_trip(tmp_path):
    p = tmp_path / "Plate.py"
    p.write_text(TEMPLATE)
    full = feature_hole.resolve({"thread_type": "ISOMetricProfile", "thread_size": "M5x0.8",
                                 "hole_cut_type": "ISO 4762", "depth_type": "ThroughAll"}).values()
    doc = feature_edit.apply(p, [{"op": "add", "feature": {"name": "Hole", "type": "PartDesign::Hole", "profile": "Holes",
                                                           **full}}])
    src = p.read_text()
    assert 'Hole("Hole", "Holes", thread_type="ISOMetricProfile", thread_size="M5x0.8", depth_type="ThroughAll", ' \
           'hole_cut_type="ISO 4762")' in src
    assert "Hole, LineSegment" in src
    h = doc["features"][-1]
    assert (h["diameter"], h["hole_cut_diameter"], h["hole_cut_depth"]) == (5.5, 10.0, 5.4)
    assert "diameter" in h["read_only"] and h["enums"]["thread_size"][13] == "M5x0.8"
    v0 = _run(p).volume
    # a new size: the diameter and the counterbore follow, and nothing else is written
    doc = feature_edit.apply(p, [{"op": "set", "name": "Hole", "props": {"thread_size": "M6x1.0"}}])
    h = doc["features"][-1]
    assert (h["diameter"], h["hole_cut_diameter"], h["hole_cut_depth"]) == (6.6, 11.0, 6.4)
    assert _run(p).volume < v0
    # a value the others give is dropped, not written
    feature_edit.apply(p, [{"op": "set", "name": "Hole", "props": {"diameter": 6.6}}])
    assert "diameter=" not in p.read_text()
    # a depth from PARAMS
    doc = feature_edit.apply(p, [{"op": "set", "name": "Hole", "props": {"depth_type": "Dimension", "depth": "deep"}}])
    assert doc["features"][-1]["depth"] == "deep" and 'depth="deep"' in p.read_text()
    assert feature_edit.read(p) == doc
    with pytest.raises(feature_edit.FeatureEditError, match="read-only in FreeCAD"):
        feature_edit.apply(p, [{"op": "set", "name": "Hole", "props": {"thread_diameter": 3.0}}])
    with pytest.raises(feature_edit.FeatureEditError, match="is not one of"):
        feature_edit.apply(p, [{"op": "set", "name": "Hole", "props": {"thread_size": "M99"}}])


def test_resolve_feature_is_what_the_panel_shows(tmp_path):
    p = tmp_path / "Plate.py"
    p.write_text(TEMPLATE)
    r = feature_edit.resolve_feature(p, {"name": "Hole", "type": "PartDesign::Hole", "profile": "Holes",
                                         "thread_type": "ISOMetricProfile", "thread_size": "M6x1.0",
                                         "depth_type": "ThroughAll"}, through_all=92.57)
    assert (r["diameter"], r["depth"], r["thread_diameter"]) == (6.6, 92.57, 6.0)
    assert "diameter" in r["read_only"] and "depth" in r["read_only"] and r["enums"]["thread_fit"] == ["Medium", "Fine", "Coarse"]
    assert r["minimal"] == {"thread_type": "ISOMetricProfile", "thread_size": "M6x1.0", "depth_type": "ThroughAll"}
    assert p.read_text() == TEMPLATE                      # nothing written
    # a new Revolution: what CmdPartDesignRevolution sets
    rv = feature_edit.resolve_feature(p, {"name": "Revolution", "type": "PartDesign::Revolution", "profile": "Holes"})
    assert rv["reference_axis"] == ["Holes", "V_Axis"] and rv["angle"] == 360.0


def test_hole_is_a_type_of_the_cli():
    from cad_agent import featurecmd
    assert featurecmd.TYPES["Hole"] == "PartDesign::Hole"
    assert featurecmd.name_of([{"op": "add", "feature": {"type": "PartDesign::Hole"}}], {}) == "Make Hole"

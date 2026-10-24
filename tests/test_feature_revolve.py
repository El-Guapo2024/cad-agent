"""cad_agent.feature_revolve builds what FreeCAD's PartDesign Revolution and Groove build, from the same FEATURES lines,
and the part-file layer and `cad feature` take them.

tests/golden/revolve/cases.py holds the bodies; make.py built each in FreeCAD 26.3 (3160daf1e2b6) through
feature.to_freecad and wrote freecad.json. Here the same lines go through feature.Body: the same volume and area (1e-6
relative), bounding box and centre of mass (1e-6 of the box's size), solids and faces, and the same faces (area and
centre); the lists FreeCAD refuses are refused in its words.
"""
import importlib.util
import json
import math
from pathlib import Path

import pytest
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

from cad_agent import feature, feature_edit
from cad_agent.feature import Body, FeatureError, Revolution, Sketch
from cad_agent.feature_revolve import suggest_reversed

GOLDEN = Path(__file__).parent / "golden" / "revolve"


def load_cases(path, name):
    """A golden folder's cases.py under its own module name (each folder has one called cases.py)."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_cases = load_cases(GOLDEN / "cases.py", "revolve_cases")
CASES, ERRORS, rect, ring = _cases.CASES, _cases.ERRORS, _cases.rect, _cases.ring


def _measure(part):
    """As tests/test_feature.py measures (and make.py measures FreeCAD's): volume, area, optimal box, centre of mass
    over the solids, and each face's area and centre in Face1, Face2, ... order."""
    shape = part.wrapped
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    lo, hi = box.CornerMin(), box.CornerMax()
    com, vol = [0.0, 0.0, 0.0], 0.0
    for s in part.solids():
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(s.wrapped, props)
        c = props.CentreOfMass()
        vol += props.Mass()
        com = [com[0] + c.X() * props.Mass(), com[1] + c.Y() * props.Mass(), com[2] + c.Z() * props.Mass()]
    faces = []
    for f in feature._faces(shape):
        fp = GProp_GProps()
        BRepGProp.SurfaceProperties_s(f, fp)
        fc = fp.CentreOfMass()
        faces.append([fp.Mass(), fc.X(), fc.Y(), fc.Z()])
    return {"volume": part.volume, "area": part.area, "bbox": [lo.X(), lo.Y(), lo.Z(), hi.X(), hi.Y(), hi.Z()],
            "center_of_mass": [x / vol for x in com] if abs(vol) > 1e-9 else None, "solids": len(part.solids()),
            "faces": len(faces),
            "face_list": faces}


FC = json.loads((GOLDEN / "freecad.json").read_text())
FREECAD, FREECAD_ERRORS = FC["cases"], FC["errors"]


def test_every_case_has_freecads_answer():
    assert set(CASES) == set(FREECAD) and set(ERRORS) == set(FREECAD_ERRORS), \
        "run tests/golden/revolve/make.py in freecadcmd"
    assert len(CASES) >= 40
    assert not [n for n, g in FREECAD.items() if "error" in g or not g["valid"]]


# Where the refine differs (FreeCAD's BRepBuilderAPI_RefineModel against OCCT's UnifySameDomain; feature.py's _refine):
# the same solid, the faces counted otherwise.
# rev_n_axis: a revolution about the sketch's normal is flat (no volume); UnifySameDomain merges its coplanar faces
# into 2, FreeCAD's refine leaves 6.
REFINE_DIFFERS = {"rev_n_axis": 2}


@pytest.mark.parametrize("name", sorted(CASES))
def test_same_solid_as_freecad(name):
    case, want = CASES[name], FREECAD[name]
    got = _measure(Body(case["features"], case.get("params")))
    assert got["volume"] == pytest.approx(want["volume"], rel=1e-6)
    assert got["area"] == pytest.approx(want["area"], rel=1e-6)
    size = math.dist(want["bbox"][:3], want["bbox"][3:])
    assert got["bbox"] == pytest.approx(want["bbox"], abs=1e-6 * size)
    if abs(want["volume"]) > 1e-9:            # rev_n_axis turns the face in its own plane: no volume, no centre
        assert got["center_of_mass"] == pytest.approx(want["center_of_mass"], abs=1e-6 * size)
    if name in REFINE_DIFFERS:
        assert (got["solids"], got["faces"]) == (want["solids"], REFINE_DIFFERS[name])
        return
    assert (got["solids"], got["faces"]) == (want["solids"], want["faces"])
    key = lambda f: tuple(round(x, 4) for x in f)       # noqa: E731
    assert sorted(map(key, got["face_list"])) == sorted(map(key, want["face_list"]))


# Mostly the faces come in FreeCAD's order too, so an up_to_face written ("Revolution", "Face3") names the face
# FreeCAD's Face3 is. These have the same faces in another order.
ORDER_DIFFERS = {"rev_on_plate", "rev_symmetric_up_to_first", "groove_up_to_first"} | set(REFINE_DIFFERS)


def test_face_names_differ_only_where_known():
    assert len(set(CASES) - ORDER_DIFFERS) >= 40


@pytest.mark.parametrize("name", sorted(set(CASES) - ORDER_DIFFERS))
def test_face_names_are_freecads(name):
    case, want = CASES[name], FREECAD[name]
    got = _measure(Body(case["features"], case.get("params")))
    assert [[round(x, 4) for x in f] for f in got["face_list"]] == \
        [[round(x, 4) for x in f] for f in want["face_list"]]


@pytest.mark.parametrize("name", sorted(ERRORS))
def test_refused_in_freecads_words(name):
    words = FREECAD_ERRORS[name].split(": ", 1)[1]
    with pytest.raises(FeatureError) as e:
        Body(ERRORS[name])
    assert str(e.value) == words


# ── the command's defaults (CmdPartDesignRevolution, CmdPartDesignGroove) ─────────────────────────────────

def test_the_command_sets_the_v_axis_and_360_degrees():
    f = Revolution("Revolution", "Sketch")
    assert f.reference_axis == ("Sketch", "V_Axis") and f.angle == 360.0 and f.angle2 == 0.0
    assert (f.side_type, f.type, f.type2, f.refine, f.reversed) == ("One side", "Angle", "Angle", True, False)


def test_suggest_reversed_is_freecads_sign():
    # XZ: the normal is -Y, the V axis global Z, the profile at +X: normal . (Z x X) = -1, so a Revolution is
    # reversed (angle < 0) and a Groove is not.
    sk = ring()
    assert suggest_reversed(Revolution("R", "Sketch"), sk) is True
    assert suggest_reversed(feature.Groove("G", "Sketch"), sk) is False
    # XY: the normal +Z, the V axis global Y, the profile at +X: Z . (Y x X) = -1 again
    xy = Sketch("Sketch", "XY", rect(5, 0, 15, 10))
    assert suggest_reversed(Revolution("R", "Sketch"), xy) is True
    # at -X the sign turns: the Revolution is not reversed, the Groove is
    left = Sketch("Sketch", "XY", rect(-15, 0, -5, 10))
    assert suggest_reversed(Revolution("R", "Sketch"), left) is False
    assert suggest_reversed(feature.Groove("G", "Sketch"), left) is True


def test_deprecated_forms_are_their_side_types():
    assert Revolution("R", "S", midplane=True).side_type == "Symmetric"
    r = Revolution("R", "S", type="TwoAngles")
    assert (r.side_type, r.type, r.type2) == ("Two sides", "Angle", "Angle")
    with pytest.raises(FeatureError, match="not one of Angle, UpToLast"):
        Revolution("R", "S", type="ThroughAll")
    with pytest.raises(FeatureError, match="not one of Angle, ThroughAll"):
        feature.Groove("G", "S", type="UpToLast")


# ── the part file: feature_edit read/apply and `cad feature add` ──────────────────────────────────────────

TEMPLATE = '''from cad_agent.feature import (ArcOfCircle, Body, Circle, Constraint, LineSegment, Pad, Pocket, Point,
                               Sketch)

PARAMS = {"turn": 90.0}

FEATURES = [
    Sketch("Sketch", support="XZ",
           geometry=[LineSegment((5.0, 0.0), (15.0, 0.0)), LineSegment((15.0, 0.0), (15.0, 10.0)),
                     LineSegment((15.0, 10.0), (5.0, 10.0)), LineSegment((5.0, 10.0), (5.0, 0.0)),
                     LineSegment((20.0, 0.0), (20.0, 10.0), construction=True)],
           constraints=[]),
]


def build(**p):
    return Body(FEATURES, p)
'''


def _run(path):
    ns = {}
    exec(compile(path.read_text(), str(path), "exec"), ns)
    return ns["build"](**ns["PARAMS"])


def test_add_revolution_writes_the_import_and_the_commands_defaults(tmp_path):
    p = tmp_path / "Body.py"
    p.write_text(TEMPLATE)
    doc = feature_edit.apply(p, [{"op": "add", "feature": {"name": "Revolution", "type": "PartDesign::Revolution",
                                                           "profile": "Sketch"}}])
    src = p.read_text()
    imports = src.split("from cad_agent.feature import (", 1)[1].split(")", 1)[0]
    assert "Revolution" in [x.strip() for x in imports.split(",")]
    rev = doc["features"][1]
    assert rev["reference_axis"] == ["Sketch", "V_Axis"] and rev["angle"] == 360.0 and rev["reversed"] is True
    # the axis is always written (FreeCAD's ReferenceAxis has no default the feature builds with); 360 is the default
    assert 'Revolution("Revolution", "Sketch", reference_axis=("Sketch", "V_Axis"), reversed=True)' in src
    assert _run(p).volume == pytest.approx(math.pi * (15 ** 2 - 5 ** 2) * 10)


def test_set_rename_delete_round_trip(tmp_path):
    p = tmp_path / "Body.py"
    p.write_text(TEMPLATE)
    feature_edit.apply(p, [{"op": "add", "feature": {"name": "Groove", "type": "PartDesign::Revolution",
                                                     "profile": "Sketch", "reversed": False}}])
    doc = feature_edit.apply(p, [{"op": "set", "name": "Groove", "props": {
        "reference_axis": ["Sketch", "Axis0"], "angle": "turn", "side_type": "Symmetric"}}])
    f = doc["features"][1]
    assert (f["reference_axis"], f["angle"], f["side_type"]) == (["Sketch", "Axis0"], "turn", "Symmetric")
    v = _run(p).volume                    # a quarter turn of the rectangle about x = 20: centroid at r = 10
    assert v == pytest.approx(100 * 10 * math.pi / 2)
    with pytest.raises(feature_edit.FeatureEditError, match="Groove uses it"):
        feature_edit.apply(p, [{"op": "delete", "name": "Sketch"}])
    doc = feature_edit.apply(p, [{"op": "rename", "name": "Sketch", "to": "Profile"}])
    assert doc["features"][1]["profile"] == "Profile" and doc["features"][1]["reference_axis"] == ["Profile", "Axis0"]
    assert feature_edit.read(p) == doc
    with pytest.raises(feature_edit.FeatureEditError, match="type1 'ThroughAll' is not one of|is not one of"):
        feature_edit.apply(p, [{"op": "set", "name": "Groove", "props": {"type1": "ThroughAll"}}])


def test_groove_is_a_type_of_the_cli():
    from cad_agent import featurecmd
    assert featurecmd._kw_types()[0]["Revolution"] == "PartDesign::Revolution"
    assert featurecmd._kw_types()[0]["Groove"] == "PartDesign::Groove"
    assert featurecmd.name_of([{"op": "add", "feature": {"type": "PartDesign::Groove"}}], {}) == "Make Groove"
    assert featurecmd.name_of([{"op": "set", "name": "Revolution", "props": {"angle": 5}}], {}) == \
        "Edit Revolution.Angle"

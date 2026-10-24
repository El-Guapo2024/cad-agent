"""cad_agent.feature_sweep builds what FreeCAD's PartDesign Additive/Subtractive Loft, Pipe and Helix build, from the
same FEATURES lines, and the part-file layer and `cad feature` take them.

tests/golden/sweep/cases.py holds the bodies; make.py built each in FreeCAD 26.3 (3160daf1e2b6) through
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

from cad_agent import feature, feature_edit, feature_sweep
from cad_agent.feature import AdditiveHelix, AdditiveLoft, AdditivePipe, Body, FeatureError, Sketch

GOLDEN = Path(__file__).parent / "golden" / "sweep"


def load_cases(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_cases = load_cases(GOLDEN / "cases.py", "sweep_cases")
CASES, ERRORS, rect, ring_profile = _cases.CASES, _cases.ERRORS, _cases.rect, _cases.ring_profile


def _measure(part):
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
            "faces": len(faces), "face_list": faces}


FC = json.loads((GOLDEN / "freecad.json").read_text())
FREECAD, FREECAD_ERRORS = FC["cases"], FC["errors"]


def test_every_case_has_freecads_answer():
    assert set(CASES) == set(FREECAD) and set(ERRORS) == set(FREECAD_ERRORS), \
        "run tests/golden/sweep/make.py in freecadcmd"
    assert len(CASES) >= 60
    assert not [n for n, g in FREECAD.items() if "error" in g or not g["valid"]]


# Where the refine differs (FreeCAD's BRepBuilderAPI_RefineModel against OCCT's UnifySameDomain; feature_sweep.refine):
# the same solid, the faces counted otherwise. {case: our face count}
# subhelix_common, subhelix_outside_deprecated: RefineModel's cylinder uniter merges the four strips the helix leaves of
# the cylinder's face into one; UnifySameDomain keeps them (and FreeCAD's merged face moves the volume by 5e-7).
REFINE_DIFFERS = {"subhelix_common": 18, "subhelix_outside_deprecated": 18}
# Where the solid is the same but FreeCAD's numbers differ past 1e-6 of the size: {case: relative tolerance}
LOOSER = {"subhelix_common": 2e-5, "subhelix_outside_deprecated": 2e-5}


def _same_faces(got, want, size, ordered):
    """Each face's area and centre within 1e-6 relative (5e-4 mm2 absolute for the helical B-spline faces, which the
    two builds approximate apart by that much) and 1e-5 of the box's size: in order, or matched one to one."""
    def close(a, b):
        return abs(a[0] - b[0]) <= max(5e-4, 1e-6 * abs(b[0])) and \
            all(abs(x - y) <= 1e-5 * size + 1e-6 for x, y in zip(a[1:], b[1:]))
    if len(got) != len(want):
        return False
    if ordered:
        return all(close(a, b) for a, b in zip(got, want))
    left = list(want)
    for a in got:
        hit = next((i for i, b in enumerate(left) if close(a, b)), None)
        if hit is None:
            return False
        left.pop(hit)
    return True


@pytest.mark.parametrize("name", sorted(CASES))
def test_same_solid_as_freecad(name):
    case, want = CASES[name], FREECAD[name]
    got = _measure(Body(case["features"], case.get("params")))
    rel = LOOSER.get(name, 1e-6)
    assert got["volume"] == pytest.approx(want["volume"], rel=1e-6)
    assert got["area"] == pytest.approx(want["area"], rel=1e-6)
    size = math.dist(want["bbox"][:3], want["bbox"][3:])
    assert got["bbox"] == pytest.approx(want["bbox"], abs=1e-6 * size)
    assert got["center_of_mass"] == pytest.approx(want["center_of_mass"], abs=rel * size)
    if name in REFINE_DIFFERS:
        assert (got["solids"], got["faces"]) == (want["solids"], REFINE_DIFFERS[name])
        return
    assert (got["solids"], got["faces"]) == (want["solids"], want["faces"])
    assert _same_faces(got["face_list"], want["face_list"], size, ordered=False)


# Mostly the faces come in FreeCAD's order too, so a later reference ("AdditiveLoft", "Face3") names the face FreeCAD's
# Face3 is. These have the same faces in another order:
# loft_section_face_of_pad: the section is a face of the solid the loft is fused with; FreeCAD's fuse orders the faces
# otherwise (before the refine, which changes nothing here).
ORDER_DIFFERS = {"loft_section_face_of_pad"} | set(REFINE_DIFFERS)


def test_face_names_differ_only_where_known():
    assert len(set(CASES) - ORDER_DIFFERS) >= 60


@pytest.mark.parametrize("name", sorted(set(CASES) - ORDER_DIFFERS))
def test_face_names_are_freecads(name):
    case, want = CASES[name], FREECAD[name]
    got = _measure(Body(case["features"], case.get("params")))
    size = math.dist(want["bbox"][:3], want["bbox"][3:])
    assert _same_faces(got["face_list"], want["face_list"], size, ordered=True)


@pytest.mark.parametrize("name", sorted(ERRORS))
def test_refused_in_freecads_words(name):
    words = FREECAD_ERRORS[name].split(": ", 1)[1]
    with pytest.raises(FeatureError) as e:
        Body(ERRORS[name])
    assert str(e.value) == words


# ── the properties: FreeCAD's defaults, the deprecated Outside, the modes ────────────────────────────────────────

def test_defaults_are_freecads():
    h = AdditiveHelix("AdditiveHelix", "Sketch")
    assert h.reference_axis == ("Sketch", "V_Axis")          # CmdPartDesignAdditiveHelix's ReferenceAxis
    assert (h.mode, h.pitch, h.height, h.turns, h.angle, h.growth, h.tolerance) == \
        ("pitch-height-angle", 10.0, 30.0, 3.0, 0.0, 0.0, 0.1)
    assert (h.left_handed, h.reversed, h.refine) == (False, False, True)
    p = AdditivePipe("AdditivePipe", "Profile", spine="Path")
    assert (p.mode, p.transition, p.transformation, p.binormal, p.auxiliary_curvilinear) == \
        ("Standard", "Transformed", "Constant", (0.0, 0.0, 0.0), True)
    s = feature.SubtractiveLoft("SubtractiveLoft", "Sketch", sections=["Sketch001"])
    assert (s.ruled, s.closed, s.operation, s.sections) == (False, False, "Subtraction", ("Sketch001",))
    assert feature.SubtractiveHelix("H", "S", outside=True).operation == "Common"   # Helix::onDocumentRestored
    with pytest.raises(FeatureError, match="not one of Standard, Fixed, Frenet, Auxiliary, Binormal"):
        AdditivePipe("P", "S", mode="Corrected Frenet")
    with pytest.raises(FeatureError, match="not one of Subtraction, Common"):
        feature.SubtractivePipe("P", "S", operation="Union")


def test_links_keep_every_sub_element():
    p = AdditivePipe("P", "S", spine=["Pad", ["Edge1", "Edge5"]], sections=[["Top", [""]], ["Apex", ["Vertex1"]]])
    assert p.spine == ("Pad", ("Edge1", "Edge5")) and p.sections == ("Top", ("Apex", "Vertex1"))
    assert p.as_dict()["spine"] == ["Pad", ["Edge1", "Edge5"]]
    assert AdditivePipe.from_dict(p.as_dict()).spine == p.spine
    assert AdditivePipe("P", "S", spine=("Path", ["Edge2"])).spine == ("Path", "Edge2")


def test_helix_modes_follow_freecads_execute():
    v = AdditiveHelix("H", "S", pitch=4.0, height=10.0, angle=5.0).values({})
    assert v["turns"] == pytest.approx(2.5) and v["growth"] == pytest.approx(4.0 * math.tan(math.radians(5.0)))
    v = AdditiveHelix("H", "S", mode="pitch-turns-angle", pitch=4.0, turns=2.0).values({})
    assert v["height"] == pytest.approx(8.0)
    v = AdditiveHelix("H", "S", mode="height-turns-angle", height=12.0, turns=4.0).values({})
    assert v["pitch"] == pytest.approx(3.0)
    v = AdditiveHelix("H", "S", mode="height-turns-growth", height=12.0, turns=3.0, growth=1.5).values({})
    assert v["pitch"] == pytest.approx(4.0) and v["angle"] == pytest.approx(math.degrees(math.atan(3 * 1.5 / 12)))
    assert AdditiveHelix("H", "S", angle=120.0).values({})["angle"] == 89.0     # Helix::floatAngle {-89, 89}
    assert AdditiveHelix("H", "S", tolerance=0.0).values({})["tolerance"] == 0.1


def test_helix_proposes_freecads_pitch_and_warns_of_self_intersection():
    sk = ring_profile()
    pitch, height = feature_sweep.propose(sk)                # 1.1 x the diagonal of the 2 x 2 profile's box
    assert pitch == pytest.approx(1.1 * math.sqrt(8)) and height == pytest.approx(3 * pitch)
    f = {"type": "PartDesign::AdditiveHelix", "profile": "Sketch"}
    assert feature_sweep.status({**f, "pitch": 1.0}, sk) == "Warning: helix might be self intersecting"
    assert feature_sweep.status({**f, "pitch": 5.0}, sk) == ""
    assert feature_sweep.status({**f, "pitch": 0.0}, sk) == "Error: Pitch too small!"


# ── the part file: feature_edit read/apply and `cad feature add` ──────────────────────────────────────────

TEMPLATE = '''from cad_agent.feature import (ArcOfCircle, Body, Circle, Constraint, LineSegment, Pad, Pocket, Point,
                               Sketch)

PARAMS = {"lead": 4.0}

FEATURES = [
    Sketch("Sketch", support="XZ",
           geometry=[LineSegment((5.0, 0.0), (7.0, 0.0)), LineSegment((7.0, 0.0), (7.0, 2.0)),
                     LineSegment((7.0, 2.0), (5.0, 2.0)), LineSegment((5.0, 2.0), (5.0, 0.0))],
           constraints=[]),
    Sketch("Top", support="XZ", attachment_offset=(0.0, 0.0, -10.0),
           geometry=[Circle((6.0, 1.0), 1.0)], constraints=[]),
    Sketch("Path", support="XY",
           geometry=[LineSegment((6.0, 0.0), (6.0, 20.0))], constraints=[]),
]


def build(**p):
    return Body(FEATURES, p)
'''


def _run(path):
    ns = {}
    exec(compile(path.read_text(), str(path), "exec"), ns)
    return ns["build"](**ns["PARAMS"])


def test_add_helix_writes_what_the_command_and_panel_set(tmp_path):
    p = tmp_path / "Body.py"
    p.write_text(TEMPLATE)
    doc = feature_edit.apply(p, [{"op": "add", "feature": {"name": "AdditiveHelix", "type": "PartDesign::AdditiveHelix",
                                                           "profile": "Sketch"}}])
    h = doc["features"][-1]
    assert h["reference_axis"] == ["Sketch", "V_Axis"]
    assert h["pitch"] == pytest.approx(1.1 * math.sqrt(8), abs=1e-9) and h["height"] == pytest.approx(3 * h["pitch"])
    src = p.read_text()
    assert "AdditiveHelix" in src.split("from cad_agent.feature import (", 1)[1].split(")", 1)[0]
    assert 'AdditiveHelix("AdditiveHelix", "Sketch", reference_axis=("Sketch", "V_Axis"), pitch=3.111269837, ' \
           'height=9.333809512)' in src
    assert _run(p).volume == pytest.approx(4 * 2 * math.pi * 6 * 3, rel=1e-6)
    doc = feature_edit.apply(p, [{"op": "set", "name": "AdditiveHelix", "props": {
        "mode": "pitch-turns-angle", "pitch": "lead", "turns": 2.0, "left_handed": True}}])
    h = doc["features"][-1]
    assert (h["mode"], h["pitch"], h["turns"], h["left_handed"]) == ("pitch-turns-angle", "lead", 2.0, True)
    assert _run(p).volume == pytest.approx(4 * 2 * math.pi * 6 * 2, rel=1e-6)
    assert feature_edit.read(p) == doc


def test_loft_and_pipe_round_trip_their_links(tmp_path):
    p = tmp_path / "Body.py"
    p.write_text(TEMPLATE)
    feature_edit.apply(p, [{"op": "add", "feature": {"name": "AdditiveLoft", "type": "PartDesign::AdditiveLoft",
                                                     "profile": "Sketch", "sections": [["Top", [""]]]}}])
    assert 'AdditiveLoft("AdditiveLoft", "Sketch", sections=["Top"])' in p.read_text()
    doc = feature_edit.apply(p, [{"op": "set", "name": "AdditiveLoft", "props": {"ruled": True}}])
    assert doc["features"][-1]["sections"] == ["Top"] and doc["features"][-1]["ruled"] is True
    with pytest.raises(feature_edit.FeatureEditError, match="AdditiveLoft uses it"):
        feature_edit.apply(p, [{"op": "delete", "name": "Top"}])
    doc = feature_edit.apply(p, [{"op": "rename", "name": "Top", "to": "Section"}])
    assert doc["features"][-1]["sections"] == ["Section"]
    feature_edit.apply(p, [{"op": "delete", "name": "AdditiveLoft"}])
    feature_edit.apply(p, [{"op": "add", "feature": {"name": "Sweep", "type": "PartDesign::AdditivePipe",
                                                     "profile": "Section", "spine": ["Path", ["Edge1"]],
                                                     "mode": "Frenet", "transition": "Round corner"}}])
    assert 'AdditivePipe("Sweep", "Section", spine=("Path", "Edge1"), mode="Frenet", ' \
           'transition="Round corner")' in p.read_text()
    doc = feature_edit.apply(p, [{"op": "rename", "name": "Path", "to": "Spine"}])
    assert doc["features"][-1]["spine"] == ["Spine", "Edge1"]
    assert feature_edit.read(p) == doc


def test_the_six_are_types_of_the_cli():
    from cad_agent import featurecmd
    types, _ = featurecmd._kw_types()
    for kind in ("AdditiveLoft", "SubtractiveLoft", "AdditivePipe", "SubtractivePipe", "AdditiveHelix",
                 "SubtractiveHelix"):
        assert types[kind] == f"PartDesign::{kind}" and featurecmd._type(kind) == f"PartDesign::{kind}"
        # Command.cpp's prepareProfileBased: openCommand("Make " + which)
        assert featurecmd.name_of([{"op": "add", "feature": {"type": f"PartDesign::{kind}"}}], {}) == f"Make {kind}"
    assert featurecmd.name_of([{"op": "set", "name": "AdditiveHelix", "props": {"pitch": 5}}], {}) == \
        "Edit AdditiveHelix.Pitch"

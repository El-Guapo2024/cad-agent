"""Tool envelopes and the bought-part import path.

The theme of both: numbers come from the person holding the part, never from
a catalogue this code pretends to have.
"""
import math
import pytest

from cad_agent import tooling
from cad_agent.bought import (MissingProvenance, bought_info, list_bought,
                              register_measured, verify)
from cad_agent.geom import bbox, intersection_volume


# ─── tool envelopes ─────────────────────────────────────────────────────────

def test_drill_stands_tip_down_at_the_origin():
    """Every tool shares one pose, or placing them means reading each source."""
    lo, hi = bbox(tooling.drill(3.0, 33.0, shank=20.0))
    assert lo[2] == pytest.approx(0.0, abs=1e-6)
    assert hi[2] == pytest.approx(53.0, abs=1e-3)
    assert hi[0] - lo[0] == pytest.approx(3.0, abs=1e-3)


def test_drill_point_is_included_in_the_flute_length():
    """Flute length is measured from the tip, as it is on the tool."""
    a = bbox(tooling.drill(6.0, 40.0, shank=10.0))
    assert a[1][2] - a[0][2] == pytest.approx(50.0, abs=1e-3)


def test_end_mill_is_flat_where_a_drill_is_pointed():
    """The difference that matters: an end mill's clearance is constant."""
    mill = tooling.end_mill(6.0, 20.0, 30.0)
    drill = tooling.drill(6.0, 20.0, shank=30.0)
    # Just above the tip the mill is full diameter and the drill is not.
    from build123d import Box, Pos
    probe = Pos(0, 0, 0.5) * Box(6.0, 6.0, 0.2)
    assert intersection_volume(mill, probe) > intersection_volume(drill, probe)


def test_collet_nose_sits_above_the_tool_not_at_the_tip():
    """The fat part is 40 mm up, which is the collision people forget."""
    lo, _ = bbox(tooling.collet_nose(32.0, 40.0, standoff=25.0))
    assert lo[2] == pytest.approx(25.0, abs=1e-6)


def test_laser_cone_opens_toward_the_work_not_away():
    """Reads backwards, so it is asserted: the swept union is wide at the work.

    A single beam converges to a point, but the galvos put that point anywhere
    in the field, so over a job the union opens downward. Getting this upside
    down would clear every fixture wall that actually shadows a corner.
    """
    from build123d import Box, Pos
    cone = tooling.laser_cone(focal_length=160.0, field=110.0, lens_dia=30.0)
    r = 110.0 * math.sqrt(2.0) / 2.0
    near_work = Pos(r - 2.0, 0, 2.0) * Box(2.0, 2.0, 2.0)
    near_lens = Pos(r - 2.0, 0, 155.0) * Box(2.0, 2.0, 2.0)
    assert intersection_volume(cone, near_work) > 0.0
    assert intersection_volume(cone, near_lens) == pytest.approx(0.0, abs=1e-6)


def test_field_corner_tilt_is_reported_and_is_large():
    """26 degrees at the corner of a typical field is the number that bites."""
    assert tooling.tilt_at_corner(160.0, 110.0) == pytest.approx(25.93, abs=0.05)
    # A longer lens tilts less, which is the whole reason to buy one.
    assert tooling.tilt_at_corner(254.0, 110.0) < tooling.tilt_at_corner(160.0, 110.0)


def test_needle_envelope_includes_the_barrel():
    """A 0.5 mm tip clears everything; the 23 mm barrel above it does not."""
    n = tooling.needle(0.51, 12.0, 23.5, 60.0, taper=4.0)
    lo, hi = bbox(n)
    assert hi[0] - lo[0] == pytest.approx(23.5, abs=1e-3)
    assert hi[2] - lo[2] == pytest.approx(76.0, abs=1e-3)


@pytest.mark.parametrize("call", [
    lambda: tooling.drill(0.0, 10.0),
    lambda: tooling.end_mill(6.0, 20.0, 0.0),
    lambda: tooling.laser_cone(160.0, 0.0, 30.0),
    lambda: tooling.laser_cone(20.0, 110.0, 30.0, offset=25.0),
])
def test_impossible_tools_are_refused(call):
    with pytest.raises(ValueError):
        call()


# ─── measured import ────────────────────────────────────────────────────────

@pytest.fixture
def proj(tmp_path, monkeypatch):
    from cad_agent import state
    monkeypatch.setattr(state, "ROOT", tmp_path)
    (tmp_path / "t" / "bought").mkdir(parents=True)
    (tmp_path / "t" / "parts").mkdir()
    return "t"


def test_measured_part_starts_unverified(proj):
    """The default is the point: a drawing figure is a claim until measured."""
    register_measured(proj, "laser_head", 60.0, 60.0, 90.0,
                      source="vendor drawing sheet 2")
    row = [r for r in list_bought(proj) if r["name"] == "laser_head"][0]
    assert row["verified"] is False
    assert bought_info(proj, "laser_head")["bbox_mm"] == [60.0, 60.0, 90.0]


def test_measured_part_without_a_source_is_refused(proj):
    with pytest.raises(MissingProvenance):
        register_measured(proj, "x", 1.0, 1.0, 1.0, source="   ")


def test_bolt_pattern_is_cut_into_the_envelope(proj):
    register_measured(proj, "mod", 40.0, 40.0, 10.0, source="drawing",
                      holes=[(-15.0, -15.0), (15.0, 15.0)], hole_dia=3.2)
    info = bought_info(proj, "mod")
    assert info["volume_cm3"] < 40.0 * 40.0 * 10.0 / 1000.0


def test_verify_requires_saying_what_was_measured(proj):
    register_measured(proj, "m", 10.0, 10.0, 10.0, source="drawing")
    with pytest.raises(MissingProvenance):
        verify(proj, "m", "  ")


def test_verify_records_the_measurement_in_the_source(proj):
    register_measured(proj, "m", 10.0, 10.0, 10.0, source="drawing p4")
    info = verify(proj, "m", "callipers 2026-09-18: 10.05 x 9.98 x 10.01")
    assert info["verified"] is True
    assert "drawing p4" in info["source"]          # the original claim survives
    assert "callipers" in info["source"]


def test_overwriting_a_bought_part_is_refused(proj):
    """Provenance and calliper corrections must not be silently replaced."""
    register_measured(proj, "m", 10.0, 10.0, 10.0, source="drawing")
    with pytest.raises(FileExistsError):
        register_measured(proj, "m", 11.0, 10.0, 10.0, source="drawing")

"""The gates that measure rather than believe.

Both rules here were added after a fault reached a published page: a 0.8 mm
web between two slots, and a cutout that swallowed two mounting holes. Each
test below reproduces one of those faults in miniature and asserts the gate
now catches it.
"""
import pytest
from build123d import Box, Cylinder, Pos

from cad_agent.checks import check_dfm
from cad_agent.checks.web import section_wires, web_report
from cad_agent.thickness import measure_min_wall


# ─── measured thickness ──────────────────────────────────────────────────────

def test_thickness_matches_known_solids():
    assert measure_min_wall(Box(10, 10, 10), 1500)["median_mm"] == pytest.approx(10, abs=0.02)
    tube = Cylinder(10, 40) - Cylinder(8, 42)
    assert measure_min_wall(tube, 2500)["median_mm"] == pytest.approx(2.0, abs=0.05)
    assert measure_min_wall(Box(50, 50, 0.8), 1500)["median_mm"] == pytest.approx(0.8, abs=0.02)


def test_thin_sheet_fails_the_wall_rule():
    rows = check_dfm("foil", Box(60, 60, 0.4), "fdm", samples=1200)
    wall = next(r for r in rows if r["rule"] == "min wall")
    assert wall["state"] == "FAIL"
    assert "measured" not in wall["measured"] or "declared" not in wall["measured"]


def test_wall_rule_reports_the_percentile_it_gated_on():
    rows = check_dfm("block", Box(20, 20, 20), "cnc", samples=1200)
    wall = next(r for r in rows if r["rule"] == "min wall")
    assert wall["state"] == "PASS"
    assert "percentile" in wall["measured"] and "rays" in wall["measured"]


# ─── in-plane web ────────────────────────────────────────────────────────────

def _plate_with_hole_near_edge(edge_gap):
    """50 mm plate, 3 mm hole whose edge sits `edge_gap` from the outer edge."""
    x = 25.0 - edge_gap - 1.5
    return Box(50, 50, 3) - Pos(x, 0, 0) * Cylinder(1.5, 5)


def test_web_measures_the_gap_to_the_edge():
    r = web_report(_plate_with_hole_near_edge(0.5))
    assert r["min_web_mm"] == pytest.approx(0.5, abs=0.01)
    assert "outer edge" in r["between"]


def test_web_reports_where_the_narrow_point_is():
    r = web_report(_plate_with_hole_near_edge(0.5))
    assert r["at_xy"][0] == pytest.approx(24.75, abs=0.1)


def test_narrow_web_fails_a_laser_cut_part():
    rows = check_dfm("plate", _plate_with_hole_near_edge(0.5), "laser_cut",
                     measure=False, min_feature_mm=3.0)
    web = next(r for r in rows if r["rule"] == "web")
    assert web["state"] == "FAIL"
    assert "0.5" in web["measured"]


def test_generous_web_passes():
    rows = check_dfm("plate", _plate_with_hole_near_edge(6.0), "laser_cut",
                     measure=False, min_feature_mm=3.0)
    assert next(r for r in rows if r["rule"] == "web")["state"] == "PASS"


def test_two_slots_that_nearly_touch_are_caught():
    """The exact fault that reached the first published car."""
    plate = Box(80, 40, 3)
    plate -= Pos(0, 6.0, 0) * Box(20, 4, 5)      # spans y 4.0 to 8.0
    plate -= Pos(0, 2.2, 0) * Box(20, 2, 5)      # spans y 1.2 to 3.2, so 0.8 between
    r = web_report(plate)
    assert r["min_web_mm"] == pytest.approx(0.8, abs=0.02)
    rows = check_dfm("plate", plate, "laser_cut", measure=False, min_feature_mm=3.0)
    assert next(x for x in rows if x["rule"] == "web")["state"] == "FAIL"


# ─── feature count ───────────────────────────────────────────────────────────

def test_feature_count_catches_a_swallowed_hole():
    """A cutout that grows over a hole leaves fewer boundaries than declared."""
    holes = [Pos(sx * 12, sy * 8, 0) * Cylinder(1.7, 5)
             for sx in (-1, 1) for sy in (-1, 1)]
    good = Box(80, 40, 3)
    for h in holes:
        good -= h
    assert web_report(good)["features"] == 4

    swallowed = good - Pos(-12, 0, 0) * Box(16, 26, 5)   # eats the left pair
    assert web_report(swallowed)["features"] == 3        # bay plus the right two

    rows = check_dfm("plate", swallowed, "laser_cut", measure=False,
                     min_feature_mm=3.0, expect_features=4)
    count = next(r for r in rows if r["rule"] == "feature count")
    assert count["state"] == "FAIL"
    assert "3 cutouts" in count["measured"]


def test_missing_expectation_is_unchecked_not_passed():
    plate = Box(80, 40, 3) - Pos(0, 0, 0) * Cylinder(3, 5)
    rows = check_dfm("plate", plate, "laser_cut", measure=False, min_feature_mm=3.0)
    assert next(r for r in rows if r["rule"] == "feature count")["state"] == "UNCHECKED"


def test_a_part_cut_into_pieces_fails():
    plate = Box(60, 20, 3) - Pos(0, 0, 0) * Box(4, 30, 5)   # severed in two
    rows = check_dfm("plate", plate, "laser_cut", measure=False, min_feature_mm=3.0)
    regions = [r for r in rows if r["rule"] == "regions"]
    assert regions and regions[0]["state"] == "FAIL"


# ─── scope ───────────────────────────────────────────────────────────────────

def test_web_rule_does_not_apply_to_chunky_parts():
    rows = check_dfm("block", Box(20, 20, 18), "cnc", samples=800)
    assert next(r for r in rows if r["rule"] == "web")["state"] == "N/A"


def test_section_wires_separates_edge_from_cutouts():
    plate = Box(50, 50, 3) - Pos(10, 0, 0) * Cylinder(3, 5) - Pos(-10, 0, 0) * Cylinder(3, 5)
    outers, inners, faces = section_wires(plate)
    assert len(outers) == 1 and len(inners) == 2 and faces == 1

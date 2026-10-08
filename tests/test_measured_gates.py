"""The gates that measure rather than believe.

Both rules here were added after a fault reached a published page: a 0.8 mm
web between two slots, and a cutout that swallowed two mounting holes. Each
test below reproduces one of those faults in miniature and asserts the gate
now catches it.
"""
import pytest
from build123d import Box, Compound, Cylinder, Pos, Rot

from cad_agent.checks import check_dfm
from cad_agent.checks.dfm import PROCESS
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


# ─── a plain plate ───────────────────────────────────────────────────────────

def test_a_plain_plate_has_no_web_to_measure():
    """A lid with no cutout has nothing between a cutout and the edge: N/A, so it can pass."""
    assert web_report(Box(80, 40, 3))["state"] == "TRIVIAL"
    rows = check_dfm("lid", Box(80, 40, 3), "laser_cut", measure=False, min_feature_mm=3.0,
                     expect_features=0)
    web = next(r for r in rows if r["rule"] == "web")
    assert web["state"] == "N/A" and "no cutout reaches the mid-plane" in web["measured"]
    assert web["limit"] == "1.5 mm" and "no web" in web["source"]
    assert next(r for r in rows if r["rule"] == "feature count")["state"] == "PASS"
    assert not [r for r in rows if r["state"] in ("FAIL", "UNCHECKED")]


def test_a_plain_plate_still_answers_for_its_cutout_count():
    """N/A for the web must not let a plate whose holes all went missing through."""
    plain = Box(80, 40, 3)
    undeclared = check_dfm("lid", plain, "laser_cut", measure=False, min_feature_mm=3.0)
    count = next(r for r in undeclared if r["rule"] == "feature count")
    assert count["state"] == "UNCHECKED" and "0 cutouts found" in count["measured"]
    assert "0 for a plain part" in count["source"]
    gone = check_dfm("lid", plain, "laser_cut", measure=False, min_feature_mm=3.0, expect_features=4)
    count = next(r for r in gone if r["rule"] == "feature count")
    assert count["state"] == "FAIL" and "0 cutouts" in count["measured"]


def test_a_slice_that_cuts_no_material_is_still_unchecked():
    """Not a plain plate: the outline could not be read, which is not the same as nothing to find."""
    pair = Compound([Pos(0, 0, -2.5) * Box(50, 50, 1), Pos(0, 0, 2.5) * Box(50, 50, 1)])
    assert web_report(pair)["state"] == "EMPTY"
    rows = check_dfm("pair", pair, "laser_cut", measure=False, min_feature_mm=3.0, expect_features=0)
    web = next(r for r in rows if r["rule"] == "web")
    assert web["state"] == "UNCHECKED" and "no material" in web["source"]
    assert not [r for r in rows if r["rule"] == "feature count"]


# ─── scope ───────────────────────────────────────────────────────────────────

def test_web_rule_does_not_apply_to_chunky_parts():
    rows = check_dfm("block", Box(20, 20, 18), "cnc", samples=800)
    assert next(r for r in rows if r["rule"] == "web")["state"] == "N/A"


def test_section_wires_separates_edge_from_cutouts():
    plate = Box(50, 50, 3) - Pos(10, 0, 0) * Cylinder(3, 5) - Pos(-10, 0, 0) * Cylinder(3, 5)
    outers, inners, faces = section_wires(plate)
    assert len(outers) == 1 and len(inners) == 2 and faces == 1


# ─── holes and slots, as the process cuts them ───────────────────────────────

def stadium(length, width, t, turn=0.0):
    """What cuts a slot: round ends `length` apart, centre to centre, and the box between."""
    r = width / 2
    tool = (Pos(-length / 2, 0, 0) * Cylinder(r, t + 2) + Pos(length / 2, 0, 0) * Cylinder(r, t + 2)
            + Box(length, width, t + 2))
    return Rot(0, 0, turn) * tool


def cuts(solid, process, features):
    """The part rules of a plate, keyed by rule name."""
    rows = check_dfm("plate", solid, process, measure=False, min_feature_mm=3.0,
                     expect_features=features)
    return {r["rule"]: r for r in rows}


@pytest.mark.parametrize("dia, state", [(0.5, "FAIL"), (0.99, "FAIL"), (1.0, "PASS"), (3.4, "PASS")])
def test_a_laser_cut_hole_under_the_minimum_fails(dia, state):
    plate = Box(60, 30, 3) - Pos(10, 0, 0) * Cylinder(dia / 2, 5) - Pos(-10, 0, 0) * Cylinder(2.5, 5)
    r = cuts(plate, "laser_cut", 2)["min hole"]
    assert r["state"] == state and r["limit"] == "1.0 mm"
    assert r["measured"].startswith(f"{min(dia, 5.0):g} mm at (")            # the smallest of the two
    assert "the smallest of 2 round holes" in r["measured"]
    assert state == "PASS" or "(10, 0, 0)" in r["measured"]                  # a failure says where


@pytest.mark.parametrize("make", [
    lambda w: Pos(10, 0, 0) * stadium(10, w, 3),                            # round ends
    lambda w: Pos(10, 0, 0) * Box(10, w, 5),                                 # a window's short side
    lambda w: Pos(35, 0, 0) * Box(10, w, 5),                                 # a notch open to the edge
    lambda w: Pos(10, 0, 0) * Rot(0, 0, 30) * Box(10, w, 5),                 # a slit that is turned
], ids=["stadium slot", "slit", "notch at the edge", "turned slit"])
def test_a_laser_cut_slot_or_gap_narrower_than_the_kerf_fails(make):
    bad = cuts(Box(80, 40, 3) - make(0.1), "laser_cut", 1)["kerf"]
    assert bad["state"] == "FAIL" and bad["limit"] == "0.15 mm"
    assert bad["measured"].startswith("0.1 mm at (")
    good = cuts(Box(80, 40, 3) - make(0.2), "laser_cut", 1)["kerf"]
    assert good["state"] == "PASS" and good["measured"].startswith("0.2 mm at (")


def test_the_kerf_reads_the_air_between_flat_walls_not_the_material_between_them():
    # A 0.5 mm web between two slots is the web rule's business; the slots themselves are wide.
    plate = Box(80, 40, 3) - Pos(0, 4, 0) * Box(20, 4, 5) - Pos(0, -0.5, 0) * Box(20, 4, 5)
    rows = cuts(plate, "laser_cut", 2)
    assert rows["kerf"]["state"] == "PASS" and rows["kerf"]["measured"].startswith("4 mm at (")
    assert rows["web"]["state"] == "FAIL"


def test_a_gap_beside_a_tab_counts_and_a_plain_plate_has_nothing_to_judge():
    # A notch 12 mm wide open to the right edge, with a tab in it 11.9 mm wide: 0.05 mm each side.
    comb = (Box(40, 40, 3) - Pos(10, 0, 0) * Box(20, 12, 5)) + Pos(7, 0, 0) * Box(16, 11.9, 3)
    assert cuts(comb, "laser_cut", 0)["kerf"]["state"] == "FAIL"
    plain = cuts(Box(80, 40, 3), "laser_cut", 0)
    assert plain["kerf"]["state"] == "N/A" and plain["min hole"]["state"] == "N/A"


def test_slots_are_not_holes_for_the_laser_and_are_for_the_mill():
    plate = Box(80, 40, 6) - Pos(10, 0, 0) * stadium(10, 0.8, 6)
    laser = cuts(plate, "laser_cut", 1)
    assert laser["min hole"]["state"] == "N/A" and "no round hole" in laser["min hole"]["measured"]
    assert laser["kerf"]["state"] == "PASS"                                  # 0.8 is far over 0.15
    mill = cuts(plate, "cnc", 1)
    assert mill["min hole"]["state"] == "FAIL" and "the smallest of 1 hole or slot" in mill["min hole"]["measured"]
    assert "kerf" not in mill                                                # a mill has none


def test_a_printed_part_has_no_hole_floor():
    plate = Box(80, 40, 6) - Pos(10, 0, 0) * Cylinder(0.5, 8)               # drilled out after printing
    rows = cuts(plate, "fdm", 1)
    assert "min hole" not in rows and "kerf" not in rows
    assert not [r for r in rows.values() if r["state"] == "FAIL"]


def test_a_search_that_fails_leaves_the_hole_and_kerf_rows_unchecked(monkeypatch):
    from cad_agent.checks import cuts as reader

    def boom(solid):
        raise RuntimeError("no cylinders today")
    monkeypatch.setattr(reader, "hole_report", boom)
    rows = cuts(Box(60, 30, 3) - Pos(10, 0, 0) * Cylinder(1.7, 5), "laser_cut", 1)
    for rule in ("min hole", "kerf"):
        assert rows[rule]["state"] == "UNCHECKED"
        assert "RuntimeError: no cylinders today" in rows[rule]["measured"]


@pytest.mark.parametrize("process", sorted(PROCESS))
def test_every_number_in_a_process_table_is_read_by_a_rule(monkeypatch, process):
    """A limit nothing reads is a promise nobody keeps: laser_cut's kerf and every process's
    minimum hole sat in the table for weeks, judged by no one."""
    class Reads(dict):
        asked: set

        def __getitem__(self, key):
            self.asked.add(key)
            return super().__getitem__(key)

        def __contains__(self, key):
            self.asked.add(key)
            return super().__contains__(key)

    table = Reads(PROCESS[process])
    table.asked = set()
    monkeypatch.setitem(PROCESS, process, table)
    plate = Box(80, 40, 3) - Pos(10, 0, 0) * Cylinder(1.7, 5) - Pos(-10, 0, 0) * stadium(10, 3.4, 3)
    check_dfm("plate", plate, process, measure=False, min_feature_mm=3.0, expect_features=2)
    assert set(PROCESS[process]) <= table.asked, set(PROCESS[process]) - table.asked

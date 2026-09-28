"""The sweep and reach rules: a gate that only judges home is not a gate.

Each test here encodes a fault that the static fit check passes and the sweep
check must not. That distinction is the whole reason the module exists, so
every test asserts both halves: clean at home, caught in travel.
"""
import pytest
from build123d import Box, Pos

from cad_agent.checks.fit import check_fit
from cad_agent.motion import (Axis, load_axes, pose, sample_travel, sweep_axis,
                              tool_span, _bbox_gap)


class FakeMod:
    pass


def _machine(gap=40.0):
    """A slider between two posts. At home it is clear of both."""
    return {
        "slider": Pos(0, 0, 0) * Box(20, 20, 20),
        "post_left": Pos(-gap, 0, 0) * Box(20, 20, 20),
        "post_right": Pos(gap, 0, 0) * Box(20, 20, 20),
    }


def _axis(travel=(-60.0, 60.0), **kw):
    kw.setdefault("work", None)
    return Axis(name="x", moves=("slider",), direction=(1, 0, 0),
                travel=travel, **kw)


def test_static_fit_passes_what_sweep_catches():
    """The fault this whole module was written for."""
    parts = _machine()
    assert all(r["state"] == "PASS" for r in check_fit(parts))

    hits = sweep_axis(parts, _axis(travel=(-60.0, 60.0)), {}, set())
    crashed = {k for k, h in hits.items() if h.overlap > 0.0}
    assert crashed == {("post_left", "slider"), ("post_right", "slider")}


def test_short_travel_stays_clear():
    """The same machine with travel inside the posts is genuinely fine."""
    hits = sweep_axis(_machine(), _axis(travel=(-15.0, 15.0)), {}, set())
    assert all(h.overlap == 0.0 for h in hits.values())
    # Closest approach is the post gap less half of each body, less travel.
    worst = min(h.distance for h in hits.values())
    assert worst == pytest.approx(5.0, abs=1e-6)


def test_sweep_names_the_pose_that_failed():
    """A failure that does not say where is not actionable."""
    hits = sweep_axis(_machine(), _axis(travel=(0.0, 60.0)), {}, set())
    hit = hits[("post_right", "slider")]
    assert hit.overlap > 0.0
    assert hit.at > 0.0          # it crashed going positive, not at home


def test_static_pairs_are_not_swept():
    """Two bodies that both stay put cannot change, so they are not re-judged."""
    hits = sweep_axis(_machine(), _axis(travel=(-10.0, 10.0)), {}, set())
    assert ("post_left", "post_right") not in hits
    assert len(hits) == 2


def test_clearance_requirement_is_honoured_in_travel():
    parts = _machine()
    req = {("post_right", "slider"): 30.0}
    hits = sweep_axis(parts, _axis(travel=(0.0, 10.0)), req, set())
    # At t=10 the gap is 40 - 20 - 10 = 10 mm, under the 30 mm required.
    assert hits[("post_right", "slider")].distance == pytest.approx(10.0, abs=1e-6)


def test_bbox_gap_is_a_lower_bound():
    """The prefilter must never claim more distance than really exists.

    This is the load-bearing property: sweep skips the exact call whenever the
    bound already settles the verdict, so a bound that overstates would hide a
    crash rather than merely cost time.
    """
    from cad_agent.geom import min_distance
    a = Box(10, 10, 10)
    for d in (5.0, 12.0, 30.0):
        b = Pos(d, d / 2.0, 0) * Box(10, 10, 10)
        assert _bbox_gap(a, b) <= min_distance(a, b) + 1e-9


def test_pose_moves_only_declared_bodies():
    parts = _machine()
    moved = pose(parts, _axis(), 25.0)
    assert moved["post_left"] is parts["post_left"]
    assert moved["slider"] is not parts["slider"]
    lo, _ = moved["slider"].bounding_box().min, None
    assert lo.X == pytest.approx(15.0, abs=1e-6)


def test_pose_rejects_a_body_that_does_not_exist():
    """A typo in `moves` must fail loudly, not silently sweep nothing."""
    axis = Axis(name="x", moves=("slidr",), direction=(1, 0, 0), travel=(0.0, 1.0))
    with pytest.raises(KeyError, match="slidr"):
        pose(_machine(), axis, 0.5)


def test_travel_samples_include_both_ends():
    """The ends are where a limit is respected or not, so they are never missed."""
    ts = sample_travel(_axis(travel=(-30.0, 70.0)), samples=5)
    assert ts[0] == pytest.approx(-30.0) and ts[-1] == pytest.approx(70.0)
    assert len(ts) == 5


def test_reach_accounts_for_the_tool_offset():
    """A tool mounted off-centre reaches an off-centre span, and reach says so."""
    axis = _axis(travel=(-100.0, 100.0), tool_point=(-35.0, 0.0, 0.0))
    lo, hi = tool_span(axis)
    assert (lo, hi) == pytest.approx((-135.0, 65.0))


def test_load_axes_rejects_backwards_travel():
    mod = FakeMod()
    mod.AXES = {"x": {"moves": ("a",), "direction": (1, 0, 0), "travel": (10.0, -10.0)}}
    with pytest.raises(ValueError, match="does not increase"):
        load_axes(mod)


def test_no_axes_means_a_static_assembly():
    assert load_axes(FakeMod()) == {}


def test_zero_direction_is_rejected():
    with pytest.raises(ValueError, match="zero direction"):
        _ = Axis(name="x", moves=("a",), direction=(0, 0, 0), travel=(0.0, 1.0)).unit


# ─── the web plane ──────────────────────────────────────────────────────────

def test_web_sections_a_plate_whatever_axis_it_stands_on():
    """A plate on edge must give the same answer as one lying flat.

    The original rule always sliced on XY. A plate standing in YZ was then cut
    along its thin direction, which returns a ragged strip: the rule reported
    a split part with no cutouts and failed a part that was fine. A wrong
    answer stated confidently is worse than declining to judge, so this is the
    regression that keeps the plane derived from the part.
    """
    from cad_agent.checks.web import thin_axis, web_report
    from build123d import Cylinder, Rot

    def plate(rot):
        s = Box(100.0, 100.0, 6.0)
        for x in (-30.0, 30.0):
            s -= Pos(x, 0, 0) * Cylinder(4.0, 20.0)
        return rot * s if rot else s

    flat = web_report(plate(None))
    on_edge = web_report(plate(Rot(90, 0, 0)))     # thin axis becomes y
    upright = web_report(plate(0 * 1 or Rot(0, 90, 0)))   # thin axis becomes x

    assert thin_axis(plate(None)) == 2
    assert thin_axis(plate(Rot(90, 0, 0))) == 1
    assert thin_axis(plate(Rot(0, 90, 0))) == 0

    for r in (flat, on_edge, upright):
        assert r["state"] == "MEASURED"
        assert r["features"] == 2, r
        assert r["regions"] == 1, r
        assert r["min_web_mm"] == pytest.approx(flat["min_web_mm"], abs=1e-6)

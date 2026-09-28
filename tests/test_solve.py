"""The search loop: margins from gate rows, and what may steer them.

The bug these tests exist for is subtle and looked like a working optimiser.
On a 6 mm plate `min wall` reads 5.9998 whatever a bolt row does, because the
thinnest wall *is* the plate. Its relative margin then becomes the worst one
for every candidate that clears it, the objective saturates, every feasible
candidate ties, and `max` returns whichever grid point it saw first. A coin
toss, reported as an optimum, with a plausible number on it.
"""
import pytest

from cad_agent.solve import (Eval, Margin, evaluate, feasible_span,
                             responsive_rules, solve, sweep)

SLUG, PART = "assembly_cell", "x_carriage"


def _m(rule, measured, limit=1.5):
    return Margin(rule=rule, state="PASS", measured=measured, limit=limit,
                  slack=measured - limit, relative=(measured - limit) / limit)


def _ev(**rules):
    return Eval(overrides={}, ok=True,
                margins=[_m(r, v) for r, v in rules.items()])


def test_a_constant_rule_is_not_responsive():
    """The whole bug in one assertion."""
    results = [_ev(min_wall=6.0, web=2.0), _ev(min_wall=6.0, web=9.0)]
    assert responsive_rules(results) == {"web"}


def test_a_single_sample_cannot_be_called_responsive():
    """One observation is not a trend; it must not enter the objective."""
    assert responsive_rules([_ev(web=2.0)]) == set()


def test_min_wall_really_is_inert_on_this_plate():
    """Not a synthetic case: the real part behaves this way."""
    rs = sweep(SLUG, PART, "rail_bolt_z", [12.0, 20.0, 28.0])
    live = responsive_rules(rs)
    assert "web" in live
    assert "min wall" not in live, (
        "min wall moved; if the part changed thickness this test's premise "
        "is gone and the inert-rule guard needs a different example")


def test_solve_reports_which_rules_could_steer_it():
    """A reader must be able to see what the optimum was actually argued from."""
    r = solve(SLUG, PART, "rail_bolt_z", 8.0, 36.0, steps=9, refine=1)
    assert r["found"]
    assert r["responsive_rules"] == ["web"]
    assert "min wall" in r["inert_rules"]
    assert r["tightest_rule"] == "web"
    assert all("responds" in m for m in r["margins"])


def test_the_optimum_sits_inside_the_feasible_span():
    r = solve(SLUG, PART, "rail_bolt_z", 8.0, 36.0, steps=9, refine=1)
    span = r["feasible_span"]
    assert span["low"] <= r["value"] <= span["high"]


def test_the_span_is_bounded_by_a_named_rule_on_each_side():
    """A boundary that does not say why is not actionable."""
    r = solve(SLUG, PART, "rail_bolt_z", 8.0, 36.0, steps=9, refine=1)
    span = r["feasible_span"]
    for side in ("bounded_below_by", "bounded_above_by"):
        assert span[side] is not None, side
        assert span[side]["rule"]


def test_visual_rules_are_excluded_from_search():
    """Drifting from the approved render is what exploring *is*."""
    ev = evaluate(SLUG, PART, {"rail_bolt_z": 20.0})
    assert not any(m.rule.startswith(("drift", "extent", "silhouette"))
                   for m in ev.margins)


def test_an_impossible_range_reports_not_found_rather_than_guessing():
    r = solve(SLUG, PART, "rail_bolt_z", 60.0, 80.0, steps=4, refine=0)
    assert r["found"] is False
    assert "no feasible value" in r["note"]


def test_backwards_bounds_are_refused():
    with pytest.raises(ValueError, match="hi must exceed lo"):
        solve(SLUG, PART, "rail_bolt_z", 30.0, 10.0)


def test_feasible_span_is_none_when_nothing_passes():
    bad = [Eval(overrides={"p": 1.0}, ok=False, hard_fails=[{"rule": "x"}])]
    assert feasible_span(bad, "p") is None


# ─── the fast path ──────────────────────────────────────────────────────────

def test_skipping_ignored_checks_does_not_change_the_verdict():
    """The whole safety argument for the speedup, asserted.

    Search drops the visual family (always ignored) and the ray-cast wall
    measurement (only once a pass has shown it cannot move). If either
    changed a verdict, the speedup would be buying wrong answers cheaply.
    """
    from cad_agent.runner import part_check
    for z in (16.0, 22.0, 28.0):
        full = part_check(SLUG, PART, {"rail_bolt_z": z}, render=False)
        fast = part_check(SLUG, PART, {"rail_bolt_z": z}, render=False,
                          only={"geometry"}, opts={"measure": False})
        full_geom = {r["rule"]: r["state"] for r in full["rows"]
                     if r["check"] == "geometry" and r["rule"] != "min wall"}
        fast_geom = {r["rule"]: r["state"] for r in fast["rows"]
                     if r["rule"] != "min wall"}
        assert full_geom == fast_geom, f"verdicts diverged at rail_bolt_z={z}"


def test_part_check_reports_what_it_skipped():
    """A cheaper run must say it was cheaper, or a reader over-reads it."""
    from cad_agent.runner import part_check
    r = part_check(SLUG, PART, render=False, only={"geometry"},
                   opts={"measure": False})
    assert r["skipped_checks"] == ["visual"]
    assert r["opts"] == {"measure": False}


def test_solve_confirms_its_winner_at_full_fidelity():
    r = solve(SLUG, PART, "rail_bolt_z", 8.0, 36.0, steps=9, refine=1)
    assert r["found"]
    assert r["confirmed_at_full_fidelity"] is True
    assert r["savings"]["visual_skipped"] is True
    assert r["savings"]["raycast_skipped"] is True


def test_the_fast_search_finds_what_the_slow_one_found():
    """Same optimum, less money. Asserted rather than assumed."""
    fast = solve(SLUG, PART, "rail_bolt_z", 8.0, 36.0, steps=9, refine=1)
    slow = solve(SLUG, PART, "rail_bolt_z", 8.0, 36.0, steps=9, refine=1,
                 ignore=("drift", "extent", "silhouette"))
    assert fast["value"] == pytest.approx(slow["value"], abs=1e-6)
    assert fast["feasible_span"]["low"] == slow["feasible_span"]["low"]
    assert fast["feasible_span"]["high"] == slow["feasible_span"]["high"]

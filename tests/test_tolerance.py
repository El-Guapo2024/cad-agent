"""A length that sits on its limit meets it, in every rule that compares one.

OCCT's distances carry about 1e-7 of noise, and a design that is asked for exactly 5 mm or
exactly 3 mm lands a hair either side of it. Each test puts a length 5e-7 mm short of its
limit, inside the registry's TOL_MM, and then a real shortfall that must still fail.
"""
import pytest
from build123d import Box, Pos

from cad_agent import rules
from cad_agent.checks.dfm import check_dfm
from cad_agent.checks.fit import check_fit
from cad_agent.motion import Axis
from cad_agent.registry import TOL_MM, AssemblyCtx
from test_spec import IFACE, bodies, by_rule, check, rig  # noqa: F401 (the rig fixture)

HAIR = 5e-7         # inside the tolerance


def ctx(parts, clearance=None, axes=None):
    return AssemblyCtx(slug="t", parts=parts, clearance=clearance or {}, allow_contact=set(),
                       out_dir=None, axes=axes or {})


def states(rows):
    return [(r.rule, r.state) for r in rows]


def test_the_tolerance_is_a_hair_above_occt_noise():
    assert 1e-7 < TOL_MM <= 1e-5


# ─── stance ──────────────────────────────────────────────────────────────────

def footprint(width):
    rows = list(rules.stance(ctx({"foot": Box(width, width, 5)})))
    return next(r for r in rows if r.rule == "footprint")


def test_a_contact_patch_of_exactly_5_mm_stands():
    assert footprint(5.0).state == "PASS"
    assert footprint(5.0 - HAIR).state == "PASS"
    assert footprint(5.0 - 1e-3).state == "FAIL"


def test_a_body_0_05_mm_off_the_ground_is_on_it_or_above_it_never_neither():
    ground = Box(40, 40, 5)
    for lift, on, above in ((0.0, 2, 0), (0.05, 2, 0), (0.05 + HAIR, 2, 0), (0.06, 1, 1)):
        parts = {"ground": ground, "lifted": Pos(0, 0, lift) * Box(10, 10, 5)}
        rows = list(rules.stance(ctx(parts)))
        row = next(r for r in rows if r.rule == "ground plane")
        assert row.measured.startswith(f"{on} bodies on the plane, {above} above it"), (lift, row.measured)


# ─── fit, sweep and reach ────────────────────────────────────────────────────

def test_a_gap_of_exactly_the_required_clearance_passes():
    def gap_row(gap):
        parts = {"a": Box(10, 10, 10), "b": Pos(10 + gap, 0, 0) * Box(10, 10, 10)}
        return check_fit(parts, required_clearance={"a|b": 3.0})[0]
    assert gap_row(3.0 - HAIR)["state"] == "PASS"
    assert gap_row(3.0 + HAIR)["state"] == "PASS"
    assert gap_row(3.0 - 1e-3)["state"] == "FAIL"


def slider_ctx(travel_to, need):
    """A slider 20 mm from a post, moving `travel_to` toward it, asked to keep `need` away."""
    parts = {"slider": Box(20, 20, 20), "post": Pos(40, 0, 0) * Box(20, 20, 20)}
    axis = Axis(name="x", moves=("slider",), direction=(1, 0, 0), travel=(0.0, travel_to))
    return ctx(parts, clearance={("post", "slider"): need}, axes={"x": axis})


def test_a_sweep_that_comes_within_a_hair_of_the_clearance_keeps_it():
    rows = list(rules.sweep(slider_ctx(HAIR, need=20.0)))
    assert states(rows) == [("sweep/x", "PASS")]
    rows = list(rules.sweep(slider_ctx(1e-3, need=20.0)))
    assert states(rows) == [("sweep/x", "FAIL")]


def test_a_work_area_that_ends_a_hair_past_the_travel_is_reached():
    def reach(work):
        axis = Axis(name="x", moves=("slider",), direction=(1, 0, 0), travel=(-60.0, 60.0), work=work)
        return list(rules.reach(ctx({"slider": Box(1, 1, 1)}, axes={"x": axis})))[0]
    assert reach((-60.0 - HAIR, 60.0 + HAIR)).state == "PASS"
    assert reach((-60.0 - 1e-3, 60.0)).state == "FAIL"


# ─── dfm ─────────────────────────────────────────────────────────────────────

def test_a_declared_wall_a_hair_under_the_process_limit_passes():
    def wall(declared):
        rows = check_dfm("block", Box(20, 20, 18), "fdm", measure=False, min_feature_mm=declared)
        return next(r for r in rows if r["rule"] == "min wall")["state"]
    assert wall(0.8 - HAIR) == "PASS"
    assert wall(0.8 - 1e-3) == "FAIL"


# ─── spec ────────────────────────────────────────────────────────────────────

def test_a_position_a_hair_past_its_tolerance_passes(rig):  # noqa: F811
    def position(dx):
        text = f'[[position]]\nbody = "far"\ncenter_mm = [{200 + dx!r}, 0, 10]\n'
        return by_rule(check(rig, text), "position")[0].state
    assert position(0.1 + HAIR) == "PASS"
    assert position(0.1 + 1e-3) == "FAIL"


def test_an_axis_offset_a_hair_past_its_tolerance_passes(rig):  # noqa: F811
    rows = by_rule(check(rig, IFACE, bodies(shift=0.1 + HAIR)), "interface")
    assert len(rows) == 2 and all(r.state == "PASS" for r in rows)
    rows = by_rule(check(rig, IFACE, bodies(shift=0.1 + 1e-3)), "interface")
    assert len(rows) == 2 and all(r.state == "FAIL" for r in rows)


def test_a_mass_a_hair_over_its_budget_passes(rig):  # noqa: F811
    # 60 x 40 x 4 mm less two 3.4 mm holes in PETG: 12.10 g, so a 12.1 g budget is on the edge.
    from cad_agent import state as st
    from cad_agent.geom import mass_g
    solid, meta = st.build_part("rig", "top_plate")
    exact = mass_g(solid, meta["material"])
    assert by_rule(check(rig, f'[[mass]]\nparts = {{ top_plate = 1 }}\nmax_g = {exact - HAIR!r}\n'),
                   "mass")[0].state == "PASS"
    assert by_rule(check(rig, f'[[mass]]\nparts = {{ top_plate = 1 }}\nmax_g = {exact - 1e-3!r}\n'),
                   "mass")[0].state == "FAIL"

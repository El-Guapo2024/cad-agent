"""The extension points: registering a check, and visual regression.

These matter more than they look. The registry is what makes a new verifier
cheap, so it has to refuse the shapes that would quietly weaken a gate. The
visual rules are what catch a change nobody wrote a rule for, so they have to
notice a real change and ignore a re-render of the same thing.
"""
import numpy as np
import pytest
from build123d import Box, Cylinder, Pos

from cad_agent import registry as reg
from cad_agent.checks import visual as vis
from cad_agent.render import draw, read_png, tessellate


# ─── registry ────────────────────────────────────────────────────────────────

def test_row_rejects_a_state_outside_the_four():
    with pytest.raises(ValueError) as e:
        reg.Row(subject="s", rule="r", state="PROBABLY")
    assert "UNCHECKED" in str(e.value)


def test_all_four_states_are_accepted():
    for st in ("PASS", "FAIL", "UNCHECKED", "N/A"):
        assert reg.Row(subject="s", rule="r", state=st).state == st


def test_unchecked_counts_as_failing_but_na_does_not():
    assert "UNCHECKED" in reg.FAILING
    assert "FAIL" in reg.FAILING
    assert "N/A" not in reg.FAILING
    assert "PASS" not in reg.FAILING


def test_every_shipped_check_is_registered_with_a_scope():
    names = {c.name for c in reg.checks()}
    assert {"geometry", "visual", "fit", "stance", "provenance"} <= names
    for c in reg.checks():
        assert c.scope in ("part", "assembly", "project")
        assert c.doc, f"{c.name} has no docstring, so the report cannot say what it does"


def test_checks_can_be_filtered_by_scope():
    assert all(c.scope == "part" for c in reg.checks("part"))
    assert {c.name for c in reg.checks("assembly")} >= {"fit", "stance"}


def test_duplicate_registration_is_refused():
    with pytest.raises(ValueError):
        reg.register(scope="part", name="geometry")(lambda ctx: [])


def test_a_check_that_raises_becomes_unchecked_not_a_crash():
    """One broken rule must not hide every other result."""
    def boom(ctx):
        raise RuntimeError("bad maths")
    spec = reg.CheckSpec(name="boom", scope="part", fn=boom, doc="", order=99)
    ctx = reg.PartCtx(slug="s", name="p", solid=None, meta={}, out_dir=None)
    (row,) = reg.run(spec, ctx)
    assert row.state == "UNCHECKED"
    assert "RuntimeError" in row.measured
    assert "fix the check" in row.source


def test_runner_stamps_the_check_name_on_every_row():
    def two(ctx):
        yield reg.Row(subject="a", rule="x", state="PASS")
        yield reg.Row(subject="b", rule="y", state="PASS")
    spec = reg.CheckSpec(name="two", scope="part", fn=two, doc="", order=1)
    rows = reg.run(spec, reg.PartCtx("s", "p", None, {}, None))
    assert [r.check for r in rows] == ["two", "two"]


# ─── visual ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def visual_project(tmp_path):
    (tmp_path / "out").mkdir()
    return tmp_path, tmp_path / "out"


def test_coverage_is_near_zero_for_an_empty_frame(tmp_path):
    from cad_agent.render import _write_png
    blank = np.full((60, 80, 3), 247, dtype=np.uint8)
    _write_png(blank, tmp_path / "blank.png")
    assert vis._coverage(read_png(tmp_path / "blank.png")) == 0.0


def test_coverage_sees_a_drawn_part(tmp_path):
    p = draw(tessellate(Box(10, 10, 10)), tmp_path / "b.png", "iso", size=(200, 160))
    assert vis._coverage(read_png(p)) > 0.1


def test_first_run_is_unchecked_not_passed(visual_project):
    root, out = visual_project
    rows = list(vis.visual_rows("cube", Box(10, 10, 10), out, root))
    drift = next(r for r in rows if r.rule.startswith("drift"))
    assert drift.state == "UNCHECKED"
    assert "approve" in drift.source


def test_an_unchanged_part_passes_after_approval(visual_project):
    root, out = visual_project
    list(vis.visual_rows("cube", Box(10, 10, 10), out, root))
    vis.approve(root, out, "cube", "iso")
    rows = list(vis.visual_rows("cube", Box(10, 10, 10), out, root))
    drift = next(r for r in rows if r.rule.startswith("drift"))
    assert drift.state == "PASS"
    assert "0.000%" in drift.measured


def test_a_changed_part_fails_and_says_where(visual_project):
    root, out = visual_project
    plain = Box(30, 30, 30)
    list(vis.visual_rows("blk", plain, out, root))
    vis.approve(root, out, "blk", "iso")

    drilled = plain - Pos(0, 0, 0) * Cylinder(6, 40)
    rows = list(vis.visual_rows("blk", drilled, out, root))
    drift = next(r for r in rows if r.rule.startswith("drift"))
    assert drift.state == "FAIL"
    assert "changed region" in drift.measured
    assert any("_diff_" in a for a in drift.artifacts), "a diff image must be written"


def test_the_diff_image_marks_only_what_changed(visual_project):
    root, out = visual_project
    plain = Box(30, 30, 30)
    list(vis.visual_rows("blk", plain, out, root))
    vis.approve(root, out, "blk", "iso")
    list(vis.visual_rows("blk", plain - Pos(0, 0, 0) * Cylinder(6, 40), out, root))

    diff = read_png(out / "_diff_blk_iso.png")
    red = (diff[:, :, 0].astype(int) - diff[:, :, 2] > 100)
    frac = red.mean()
    assert 0.0 < frac < 0.5, f"{frac:.3%} of the diff is marked, which is implausible"


def test_approving_without_a_render_is_refused(visual_project):
    root, out = visual_project
    with pytest.raises(FileNotFoundError) as e:
        vis.approve(root, out, "never_rendered", "iso")
    assert "run the checks first" in str(e.value)


def test_extent_separates_a_move_from_a_reshape(visual_project):
    root, out = visual_project
    box = Box(20, 20, 20)
    list(vis.visual_rows("b", box, out, root))
    vis.approve(root, out, "b", "iso")
    # The view frames on the bounding box, so a pure translation is invisible.
    rows = list(vis.visual_rows("b", Pos(50, 0, 0) * box, out, root))
    assert next(r for r in rows if r.rule.startswith("drift")).state == "PASS"
    assert next(r for r in rows if r.rule.startswith("extent")).state == "PASS"


def test_an_unknown_view_is_unchecked(visual_project):
    root, out = visual_project
    rows = list(vis.visual_rows("b", Box(5, 5, 5), out, root, views=("corner",)))
    assert rows[0].state == "UNCHECKED"
    assert "unknown view" in rows[0].measured

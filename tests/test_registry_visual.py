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
from cad_agent import rules  # noqa: F401  (importing it registers every shipped check)
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


def test_the_image_numbers_are_those_of_plain_integer_arithmetic(tmp_path):
    """Coverage, drift and drawn extent are held to the int64 sums they were first written as."""
    from cad_agent.render import _write_png
    rng = np.random.default_rng(7)
    cur = rng.integers(0, 256, (48, 64, 3), dtype=np.uint8)
    base = np.where(rng.random((48, 64, 1)) < 0.9, cur, rng.integers(0, 256, (48, 64, 3), dtype=np.uint8))
    cur[0, 0] = base[0, 0] = (247, 246, 244)
    cur[:6], base[:6, :20] = (247, 246, 244), (247, 246, 244)                   # background to be found
    _write_png(cur, tmp_path / "cur.png")
    _write_png(base, tmp_path / "base.png")

    def ink(img):
        return np.abs(img.astype(int) - img[0, 0].astype(int)).max(axis=2) > vis.CHANNEL_TOL

    def extent(img):
        ys, xs = np.nonzero(ink(img))
        return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())

    assert vis._coverage(cur) == float(ink(cur).mean()) > 0
    assert vis._drawn_bbox(cur) == extent(cur)
    shown = vis.compare(tmp_path / "cur.png", tmp_path / "base.png", tmp_path / "diff.png")
    moved = np.abs(cur.astype(int) - base.astype(int)).max(axis=2) > vis.CHANNEL_TOL
    assert shown["drift"] == float(moved.mean()) > 0
    assert (shown["coverage"], shown["baseline_coverage"]) == (float(ink(cur).mean()), float(ink(base).mean()))
    assert (shown["bbox"], shown["baseline_bbox"]) == (extent(cur), extent(base))
    ys, xs = np.nonzero(moved)
    assert shown["changed_region"] == [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
    assert vis.compare(tmp_path / "cur.png", tmp_path / "base.png", tmp_path / "diff2.png", current=cur) == \
        {**shown, "diff_png": str(tmp_path / "diff2.png")}                       # an image already read gives the same


def test_first_run_is_unchecked_not_passed(visual_project):
    root, out = visual_project
    rows = list(vis.visual_rows("cube", Box(10, 10, 10), out, root))
    drift = next(r for r in rows if r.rule.startswith("drift"))
    assert drift.state == "UNCHECKED"
    assert "`cad approve`" in drift.source and "baseline_approve" not in drift.source   # the CLI, not the retired tool


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

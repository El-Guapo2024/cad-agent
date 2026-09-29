"""Tests over the desk_fab_line project: the state layer, runner and gate.

The project is a fixture: a snapshot of the Desk Fab Line's hot plate dock,
the harness's first real design, kept in tests/fixtures so cad-agent is tested
without depending on the repo that owns the live design. Each run works on a
temporary copy, because check_all writes checks.json and out/.
"""
import json
import shutil
from pathlib import Path

import pytest

from cad_agent import state as st
from cad_agent.cutlist import cutlist
from cad_agent.runner import check_all, done_check

SLUG = "desk_fab_line"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="module", autouse=True)
def project(tmp_path_factory):
    """A copy of the design, with state.ROOT pointed at it for the whole module.

    checks.json and out/ are not copied: they are what check_all writes.
    """
    src = FIXTURES / SLUG
    root = tmp_path_factory.mktemp("projects")
    dst = root / SLUG
    for sub in ("parts", "bought", "baseline", "research"):
        shutil.copytree(src / sub, dst / sub,
                        ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("assembly.py", "spec.toml"):
        shutil.copy2(src / name, dst / name)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(st, "ROOT", root)
        yield dst


@pytest.fixture(scope="module")
def checked(project):
    """One check_all over the copy, shared by every test that reads checks.json.

    A run takes seconds, which is why this and the copy are module-scoped
    rather than per test like the throwaway projects in test_cli.py.
    """
    return check_all(SLUG, render_views=("iso",))


def test_project_is_discoverable():
    assert SLUG in st.list_projects()


def test_missing_project_raises():
    with pytest.raises(FileNotFoundError):
        st.project_dir("no_such_project")


def test_parts_are_listed():
    names = st.part_names(SLUG)
    assert "hot_plate" in names and "plate_standoff" in names


def test_hot_plate_declares_what_the_gates_need():
    _, meta = st.build_part(SLUG, "hot_plate")
    assert meta["material"] == "aluminium"
    assert meta["process"] == "cnc"
    assert meta["min_feature_mm"] is not None


def test_overrides_change_the_geometry():
    thin, _ = st.build_part(SLUG, "hot_plate", {"thickness": 6.0})
    from cad_agent.geom import bbox
    lo, hi = bbox(thin)
    assert hi[2] - lo[2] == pytest.approx(6.0)


def test_missing_part_raises():
    with pytest.raises(FileNotFoundError):
        st.build_part(SLUG, "flux_capacitor")


def _rows(payload, check=None, rule=None, subject=None):
    out = payload["rows"]
    if check:
        out = [r for r in out if r["check"] == check]
    if rule:
        out = [r for r in out if r["rule"] == rule]
    if subject:
        out = [r for r in out if r["subject"] == subject]
    return out


def test_check_all_writes_checks_json(checked):
    payload = checked
    assert payload["summary"]["parts_failed"] == 0
    assert payload["rows"], "a run with parts must produce rows"
    on_disk = json.loads((st.project_dir(SLUG) / "checks.json").read_text())
    assert on_disk["summary"] == payload["summary"]
    assert on_disk["written_utc"]


def test_every_row_is_attributed_to_a_check(checked):
    payload = st.read_checks(SLUG)
    for r in payload["rows"]:
        assert r["check"], r
        assert r["state"] in ("PASS", "FAIL", "UNCHECKED", "N/A"), r
        assert r["source"] or r["state"] == "PASS", r


def test_all_four_check_families_ran(checked):
    payload = st.read_checks(SLUG)
    ran = {r["check"] for r in payload["rows"]}
    assert {"geometry", "fit", "stance", "provenance", "visual"} <= ran


def test_thermal_gap_is_gated_not_assumed(checked):
    payload = st.read_checks(SLUG)
    rows = _rows(payload, check="fit",
                 subject="floor_rail_front vs hot_plate")
    assert rows and rows[0]["state"] == "PASS"
    assert "20.00 mm" in rows[0]["limit"]


def test_geometry_and_fit_are_green(checked):
    payload = st.read_checks(SLUG)
    for check in ("geometry", "fit", "stance"):
        bad = [r for r in _rows(payload, check=check) if r["state"] == "FAIL"]
        assert not bad, bad


def test_done_check_holds_the_project_open_on_unverified_geometry(checked):
    """The mica heater's dimensions came from no published drawing.

    Asserts both halves: the gate fails, and it fails for that reason alone.
    Confirming the part and setting VERIFIED turns this green.
    """
    result = done_check(SLUG)
    assert not result["ok"]
    assert all("provenance" in f or "drift" in f for f in result["failures"]), \
        result["failures"]
    assert any("mica_heater" in f for f in result["failures"])


def test_bought_parts_are_checked_for_provenance(checked):
    payload = st.read_checks(SLUG)
    rows = _rows(payload, check="provenance")
    assert any(r["subject"] == "mica_heater" and r["state"] == "UNCHECKED"
               for r in rows)


def test_done_check_fails_on_unchecked(checked, monkeypatch):
    """Silence must not read as a pass."""
    payload = dict(st.read_checks(SLUG))
    payload["rows"] = [{
        "subject": "assembly", "rule": "fit", "state": "UNCHECKED",
        "measured": "nothing was judged", "limit": "n/a", "source": "",
        "check": "fit", "artifacts": [],
    }]
    monkeypatch.setattr(st, "read_checks", lambda slug: payload)
    import cad_agent.runner as runner
    result = runner.done_check(SLUG)
    assert not result["ok"]
    assert any("unchecked" in f for f in result["failures"])


def test_cutlist_is_derived_from_parts():
    cl = cutlist(SLUG)
    kinds = {r["kind"] for r in cl["rows"]}
    assert any("G10" in k for k in kinds)
    assert cl["rows"][0]["qty"] == 4

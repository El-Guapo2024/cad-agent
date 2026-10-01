"""The CLI is what agents drive, so these tests go through it: argument
parsing, the exit code that is the verdict, --json, and the activity log.

Most run in-process through cli.main(argv) against a throwaway project, which
keeps the kernel import to one per test session. Two run bin/cad in a
subprocess, so the wrapper and the exit codes a shell sees are covered too;
both are chosen to fail or finish before the slow build123d import.
"""
import json
import os
import subprocess
from pathlib import Path

import pytest

from cad_agent import cli
from cad_agent import state as st

REPO = Path(__file__).resolve().parent.parent

PLATE = '''"""Test plate: a flat bracket with two clearance holes."""
from build123d import Box, Cylinder, Pos
from cad_agent.parts import CLEARANCE_HOLE

MATERIAL = "petg"
PROCESS = "fdm"
MIN_FEATURE_MM = 1.2
EXPECT_FEATURES = 2

PARAMS = {"width": 40.0, "depth": 20.0, "thickness": 4.0, "screw": "M3"}


def build(width, depth, thickness, screw):
    part = Box(width, depth, thickness)
    for x in (-width / 4, width / 4):
        part -= Pos(x, 0, 0) * Cylinder(CLEARANCE_HOLE[screw] / 2, thickness + 2)
    return part
'''

BLOCK = '''"""Test block: a 10 mm cube."""
from build123d import Box

MATERIAL = "aluminium"
PROCESS = "cnc"
MIN_FEATURE_MM = 2.0

PARAMS = {"size": 10.0}


def build(size):
    return Box(size, size, size)
'''

BROKEN = '''"""A part whose build raises, standing in for a design mistake."""
MATERIAL = "petg"
PROCESS = "fdm"
MIN_FEATURE_MM = 1.0
PARAMS = {}


def build():
    raise ValueError("wall thickness came out negative")
'''

# The block sits 20 mm up: its bottom face at z = 15, the plate's top at z = 2.
ASSEMBLY = '''from build123d import Pos
from cad_agent.state import build_part

SLUG = "demo"
CLEARANCE = {}
ALLOW_CONTACT = set()


def parts():
    plate, _ = build_part(SLUG, "plate")
    block, _ = build_part(SLUG, "block")
    return {"plate": plate, "block": Pos(0, 0, 20) * block}
'''


@pytest.fixture()
def demo(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(st, "ROOT", tmp_path)
    monkeypatch.delenv("CAD_PROJECTS", raising=False)
    assert cli.main(["init", "demo", "--brief", "test project"]) == cli.OK
    capsys.readouterr()
    d = tmp_path / "demo"
    (d / "parts" / "plate.py").write_text(PLATE)
    (d / "parts" / "block.py").write_text(BLOCK)
    (d / "assembly.py").write_text(ASSEMBLY)
    return d


def run(capsys, *argv):
    """Run with --json; return (exit code, the parsed JSON object)."""
    code = cli.main(["--json", *argv])
    out = capsys.readouterr().out.strip().splitlines()
    assert out, f"no JSON on stdout for {argv}"
    payload = json.loads(out[-1])
    assert payload["exit"] == code
    return code, payload["data"]


def log_lines(path: Path) -> list[dict]:
    return [json.loads(x) for x in (path / ".cad" / "log.jsonl").read_text().splitlines()]


# ─── Projects ────────────────────────────────────────────────────────────────

def test_init_writes_the_profile_and_ls_finds_the_parts(demo, capsys):
    assert (demo / "mech_profile.md").read_text().count("test project") == 1
    code, data = run(capsys, "ls")
    assert code == cli.OK and data["projects"] == ["demo"]   # .cad is not a project
    code, data = run(capsys, "ls", "demo")
    assert data["parts"] == ["block", "plate"] and data["assembly"] is True
    code, data = run(capsys, "status", "demo")
    assert code == cli.OK and data["last_check"] is None


def test_init_refuses_a_path_as_a_name(demo, capsys):
    code, data = run(capsys, "init", "../escape")
    assert code == cli.USAGE and "letters, digits" in data["error"]


def test_init_refuses_an_already_existing_project(demo, capsys):
    code, data = run(capsys, "init", "demo")
    assert code == cli.USAGE and "already exists" in data["error"]


# ─── Parts ───────────────────────────────────────────────────────────────────

def test_build_measures_and_takes_overrides(demo, capsys):
    code, data = run(capsys, "build", "demo", "plate", "--set", "thickness=6")
    assert code == cli.OK
    assert data["bbox_mm"] == [40.0, 20.0, 6.0]
    assert data["overrides"] == {"thickness": 6}
    assert data["mass_g"] > 0 and data["process"] == "fdm"


def test_a_misspelt_parameter_is_a_usage_error_naming_the_real_ones(demo, capsys):
    code, data = run(capsys, "build", "demo", "plate", "--set", "thikness=6")
    assert code == cli.USAGE
    assert "thikness" in data["error"] and "thickness" in data["error"]


def test_unknown_project_or_part_is_a_usage_error(demo, capsys):
    code, data = run(capsys, "build", "nope", "plate")
    assert code == cli.USAGE and "demo" in data["error"]      # lists what exists
    code, data = run(capsys, "build", "demo", "nope")
    assert code == cli.USAGE and "plate" in data["error"]


def test_a_part_that_raises_is_a_fail_not_a_crash(demo, capsys):
    (demo / "parts" / "broken.py").write_text(BROKEN)
    code, data = run(capsys, "build", "demo", "broken")
    assert code == cli.FAIL
    assert "did not build" in data["error"] and "negative" in data["error"]


def test_render_writes_part_and_assembly_pngs(demo, capsys):
    code, data = run(capsys, "render", "demo", "plate", "--view", "top")
    assert code == cli.OK and Path(data["png"]).exists()
    code, data = run(capsys, "render", "demo")
    assert code == cli.OK and data["subject"] == "assembly" and Path(data["png"]).exists()
    code, data = run(capsys, "render", "demo", "plate", "--view", "sideways")
    assert code == cli.USAGE
    code, data = run(capsys, "render", "demo", "--set", "size=5")
    assert code == cli.USAGE                                  # --set needs a part


# ─── Measurement and reference ───────────────────────────────────────────────

def test_measure_exit_code_says_whether_parts_interfere(demo, capsys):
    code, data = run(capsys, "measure", "demo", "plate", "block")
    assert code == cli.FAIL and data["interferes"] is True    # both at the origin
    code, data = run(capsys, "measure", "demo", "plate", "block", "--posed")
    assert code == cli.OK and data["min_distance_mm"] == pytest.approx(13.0, abs=1e-3)


def test_mass_gives_freecads_mass_properties_as_placed(demo, capsys):
    code, data = run(capsys, "mass", "demo", "plate", "block")
    assert code == cli.OK
    assert [b["body"] for b in data["bodies"]] == ["plate", "block"]
    assert data["mass_kg"] == pytest.approx(sum(b["mass_kg"] for b in data["bodies"]))
    assert len(data["inertia_kg_mm2"]) == 3 and len(data["principal_moments"]) == 3
    code, data = run(capsys, "mass", "demo", "nope")
    assert code == cli.USAGE


def test_tables_rules_and_tool_envelopes(demo, capsys):
    code, data = run(capsys, "tables", "holes")
    assert code == cli.OK and "M3" in data["clearance_hole_mm"]
    code, data = run(capsys, "tables", "nope")
    assert code == cli.USAGE
    code, data = run(capsys, "rules")
    names = {r["name"] for r in data["rules"]}
    assert {"geometry", "fit", "visual", "provenance"} <= names
    code, data = run(capsys, "tool", "laser_cone", "focal_length=210", "field=150", "lens_dia=30")
    assert code == cli.OK and data["corner_tilt_deg"] == pytest.approx(26.8, abs=0.05)
    code, data = run(capsys, "tool", "laser_cone", "focal_length=210")
    assert code == cli.USAGE and "field" in data["error"]


# ─── Gates ───────────────────────────────────────────────────────────────────

def test_check_exit_code_is_the_verdict_and_approval_settles_drift(demo, capsys):
    code, data = run(capsys, "check", "demo", "--part", "plate", "--all")
    assert code == cli._verdict(r["state"] for r in data["rows"])

    code, data = run(capsys, "check", "demo", "--all")
    assert (demo / "checks.json").exists()
    assert code == cli._verdict(r["state"] for r in data["rows"])
    drift = [r for r in data["rows"] if r["rule"].startswith("drift/")]
    assert drift and all(r["state"] == "UNCHECKED" for r in drift)   # no baseline yet
    assert code != cli.OK

    code, data = run(capsys, "approve", "demo")
    assert code == cli.OK and data["approved"]

    code, data = run(capsys, "check", "demo", "--all")
    drift = [r for r in data["rows"] if r["rule"].startswith("drift/")]
    assert drift and all(r["state"] == "PASS" for r in drift)
    assert code == cli._verdict(r["state"] for r in data["rows"])

    # This process already ran commands, so its verify cannot count as fresh.
    code, data = run(capsys, "verify", "demo")
    assert code == cli.UNCHECKED and data["process"] == {"fresh": False, "mode": "reused"}
    code, data = run(capsys, "done", "demo")
    assert code == cli.UNCHECKED and data["done"] is False
    assert "the verdict came from a process that was not fresh" in data["reasons"]


def test_done_before_any_verify_is_unchecked(demo, capsys):
    code, data = run(capsys, "done", "demo")
    assert code == cli.UNCHECKED and data["done"] is False
    assert data["reasons"] == ["never verified: run `cad verify`"]


# ─── Bought parts ────────────────────────────────────────────────────────────

def test_bought_measured_part_flow(demo, capsys):
    code, data = run(capsys, "bought", "add-measured", "demo", "motor",
                     "--size", "42", "42", "40", "--source", "datasheet p3",
                     "--hole", "15.5,15.5", "--hole=-15.5,-15.5")
    assert code == cli.OK and data["bbox_mm"]
    code, data = run(capsys, "bought", "ls", "demo")
    assert [r["name"] for r in data["bought"]] == ["motor"]
    code, data = run(capsys, "bought", "verify", "demo", "motor", "--note", "calipers 42.1 x 42.0")
    assert code == cli.OK and "calipers" in data["source"]
    code, data = run(capsys, "bought", "info", "demo", "nope")
    assert code == cli.USAGE
    code, data = run(capsys, "bought", "add-measured", "demo", "rail", "--size", "1", "2", "3",
                     "--source", "p1", "--hole", "not-a-point")
    assert code == cli.USAGE


# ─── Usage, output, log ──────────────────────────────────────────────────────

def test_argument_errors_exit_3_not_argparse_2(demo, capsys):
    assert cli.main([]) == cli.USAGE
    assert cli.main(["check"]) == cli.USAGE                 # missing slug
    assert cli.main(["bought"]) == cli.USAGE                # missing action
    assert cli.main(["tool", "wrench"]) == cli.USAGE        # not a tool kind
    assert cli.main(["bought", "add-measured", "demo", "m", "--size", "1", "2", "3"]) == cli.USAGE
    assert cli.main(["--help"]) == cli.OK


def test_json_flag_works_before_or_after_the_command(demo, capsys):
    for argv in (["--json", "ls"], ["ls", "--json"]):
        assert cli.main(argv) == cli.OK
        assert json.loads(capsys.readouterr().out)["data"]["projects"] == ["demo"]


def test_every_command_lands_in_the_activity_log(demo, capsys):
    run(capsys, "build", "demo", "plate")
    run(capsys, "render", "demo", "plate")
    run(capsys, "build", "demo", "plate", "--set", "bogus=1")
    lines = log_lines(demo)
    assert [x["cmd"] for x in lines] == ["init", "build", "render", "build"]
    assert [x["exit"] for x in lines] == [0, 0, 0, 3]
    assert lines[2]["files"] and lines[2]["files"][0].endswith("plate_iso.png")
    assert all(x["t"] and "ms" in x for x in lines)
    run(capsys, "rules")                                    # no project: the root log
    assert log_lines(st.ROOT)[-1]["cmd"] == "rules"


# ─── The real entry point ────────────────────────────────────────────────────

def _bin(tmp_path, *argv):
    # Cold on purpose: these cover the wrapper and the exit code, and must not
    # leave a warm worker running (test_warm.py covers that path).
    env = dict(os.environ, CAD_PROJECTS=str(tmp_path), CAD_WARM="0")
    return subprocess.run([str(REPO / "bin" / "cad"), *argv], capture_output=True,
                          text=True, env=env, timeout=120)


def test_bin_cad_runs_and_honours_cad_projects(tmp_path):
    (tmp_path / "alpha").mkdir()
    p = _bin(tmp_path, "--json", "ls")
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["data"]["projects"] == ["alpha"]


def test_bin_cad_exit_code_reaches_the_shell(tmp_path):
    p = _bin(tmp_path, "build", "nope", "plate")
    assert p.returncode == 3 and "no project" in p.stderr

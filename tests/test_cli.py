"""The CLI is what agents drive, so these tests go through it: argument
parsing, the exit code that is the verdict, --json, and the activity log.

Most run in-process through cli.main(argv) against a throwaway project, which
keeps the kernel import to one per test session. Two run bin/cad in a
subprocess, so the wrapper and the exit codes a shell sees are covered too;
both are chosen to fail or finish before the slow build123d import.
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from cad_agent import cli
from cad_agent import state as st
from conftest import cad_env

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
    env = cad_env(CAD_PROJECTS=str(tmp_path), CAD_WARM="0")
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


def test_bin_cad_in_a_test_runs_the_tests_own_python(tmp_path, monkeypatch):
    # A plugin session exports CAD_PYTHON for its own install and CAD_PROJECTS for its own designs.
    monkeypatch.setenv("CAD_PYTHON", str(tmp_path / "no-such-python"))
    monkeypatch.setenv("CAD_PROJECTS", str(tmp_path / "someone-elses-projects"))
    env = cad_env()
    assert env["CAD_PYTHON"] == sys.executable and "CAD_PROJECTS" not in env
    assert cad_env(CAD_PROJECTS="/here")["CAD_PROJECTS"] == "/here"
    (tmp_path / "alpha").mkdir()
    p = _bin(tmp_path, "--json", "ls")
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["data"]["projects"] == ["alpha"]


# ─── Which Python bin/cad runs ───────────────────────────────────────────────

def _stub(path: Path, code: int = 0) -> Path:
    """A "python" that says which one it is and what PYTHONPATH it was given."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'#!/bin/sh\necho "ran:$0"\necho "pythonpath:$PYTHONPATH"\nexit {code}\n')
    path.chmod(0o755)
    return path


def _checkouts(tmp_path):
    """(main, worktree): a minimal cad-agent checkout and a git worktree of it."""
    main = tmp_path / "main"
    (main / "bin").mkdir(parents=True)
    shutil.copy(REPO / "bin" / "cad", main / "bin" / "cad")
    (main / "cad_agent").mkdir()
    (main / "cad_agent" / "warm.py").write_text("")
    shutil.copytree(REPO / ".claude" / "hooks", main / ".claude" / "hooks",
                    ignore=shutil.ignore_patterns("__pycache__"))
    for args in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", "x"],
                 ["worktree", "add", "-q", "-b", "wt", str(tmp_path / "wt")]):
        subprocess.run(["git", "-C", str(main), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                       check=True, capture_output=True)
    return main.resolve(), (tmp_path / "wt").resolve()


def _python_of(checkout, tmp_path, **env):
    """(the python bin/cad ran, its PYTHONPATH) in a shell with no CAD_PYTHON and an empty home."""
    e = {"PATH": os.environ["PATH"], "HOME": str(tmp_path / "home"), **env}
    p = subprocess.run([str(checkout / "bin" / "cad"), "x"], capture_output=True, text=True,
                       env=e, cwd=tmp_path, timeout=60)
    assert p.returncode == 0, p.stderr
    return (re.search(r"ran:(.*)", p.stdout).group(1), re.search(r"pythonpath:(.*)", p.stdout).group(1))


def test_a_worktree_runs_the_main_checkouts_python_on_its_own_code(tmp_path):
    # A worktree has no .venv, and falling through to the plugin's means another build123d and
    # OCCT; the main checkout's venv has an editable install of the main checkout, so the
    # worktree's cad_agent has to be put first.
    main, wt = _checkouts(tmp_path)
    _stub(main / ".venv" / "bin" / "python")
    _stub(tmp_path / "home" / ".claude" / "plugins" / "data" / "cad-agent-x" / "venv" / "bin" / "python")
    assert _python_of(wt, tmp_path) == (str(main / ".venv" / "bin" / "python"), str(wt))
    assert _python_of(main, tmp_path) == (str(main / ".venv" / "bin" / "python"), str(main))


def test_the_python_bin_cad_picks_goes_by_order(tmp_path):
    main, wt = _checkouts(tmp_path)
    plugin = _stub(tmp_path / "home" / ".claude" / "plugins" / "data" / "cad-agent-x" / "venv" / "bin" / "python")
    assert _python_of(wt, tmp_path)[0] == str(plugin)        # a worktree of a checkout with no venv
    own = _stub(wt / ".venv" / "bin" / "python")
    _stub(main / ".venv" / "bin" / "python")
    assert _python_of(wt, tmp_path)[0] == str(own)           # its own venv beats the main one
    chosen = _stub(tmp_path / "chosen" / "python")
    assert _python_of(wt, tmp_path, CAD_PYTHON=str(chosen))[0] == str(chosen)
    data = _stub(tmp_path / "data" / "venv" / "bin" / "python")
    own.unlink()
    shutil.rmtree(main / ".venv")
    assert _python_of(wt, tmp_path, CLAUDE_PLUGIN_DATA=str(tmp_path / "data"))[0] == str(data)


def test_a_checkout_that_is_not_a_worktree_does_not_borrow_a_venv(tmp_path):
    # A plugin's copy of the repo, or a clone nobody installed: no venv of its own, no git parent.
    alone = tmp_path / "alone"
    (alone / "bin").mkdir(parents=True)
    shutil.copy(REPO / "bin" / "cad", alone / "bin" / "cad")
    plugin = _stub(tmp_path / "home" / ".claude" / "plugins" / "data" / "cad-agent-x" / "venv" / "bin" / "python")
    assert _python_of(alone, tmp_path) == (str(plugin), str(alone.resolve()))


# ─── A mistake in the arguments is a usage error, never a crash ───────────────────────────────

def test_a_project_name_is_one_folder_not_a_path(demo, capsys):
    # `status ..` took the folder above the projects for a project, `check ""` the root itself
    # and `check /etc` any folder on the machine, and a gate writes checks.json into its project.
    for name in ("..", "", "/etc", "a/b", ".cad"):
        code, data = run(capsys, "status", name)
        assert code == cli.USAGE and "no project" in data["error"], name
    code, data = run(capsys, "check", "..")
    assert code == cli.USAGE
    assert not (demo.parent / "checks.json").exists() and not (demo.parent.parent / "checks.json").exists()


def test_values_that_make_no_tool_are_usage_errors(demo, capsys):
    for argv in (["drill", "diameter=-3", "flute=20"], ["drill", "diameter=0", "flute=0"],
                 ["laser_cone", "focal_length=0", "field=110", "lens_dia=30"]):
        code, data = run(capsys, "tool", *argv)
        assert code == cli.USAGE and "positive" in data["error"], argv
    code, data = run(capsys, "tool", "drill", "diameter=abc", "flute=20")
    assert code == cli.USAGE and "diameter must be a number" in data["error"]
    code, data = run(capsys, "tool", "drill", "diameter=3", "flute=20", "colour=red")
    assert code == cli.USAGE and "no parameter colour" in data["error"] and "shank_dia" in data["error"]


def test_a_tolerance_the_mesher_cannot_use_is_a_usage_error(demo, capsys):
    for bad in ("0", "-1", "nan", "inf"):
        code, data = run(capsys, "render", "demo", "plate", "--tolerance", bad)
        assert code == cli.USAGE and "above 0" in data["error"], bad
    code, data = run(capsys, "scene", "demo", "--tolerance", "0")
    assert code == cli.USAGE


def test_an_unknown_view_is_a_usage_error_for_check_verify_and_approve(demo, capsys):
    for argv in (["check", "demo", "--views", "iso,nope"], ["verify", "demo", "--views", "nope"],
                 ["approve", "demo", "--view", "nope"]):
        code, data = run(capsys, *argv)
        assert code == cli.USAGE and "unknown view 'nope'" in data["error"] and "iso2" in data["error"], argv


def test_approve_before_anything_was_rendered_says_to_run_the_checks(demo, capsys):
    code, data = run(capsys, "approve", "demo")
    assert code == cli.USAGE and "run the checks first" in data["error"]


def test_a_set_of_the_wrong_type_is_a_usage_error_like_cad_set(demo, capsys):
    code, data = run(capsys, "build", "demo", "plate", "--set", "thickness=abc")
    assert code == cli.USAGE and "thickness is a number" in data["error"]
    code, data = run(capsys, "build", "demo", "plate", "--set", "thickness=5")
    assert code == cli.OK and data["overrides"] == {"thickness": 5.0}


# ─── Messages that say what to do ────────────────────────────────────────────────────────────

def test_measure_names_the_flag_that_reaches_bought_parts_and_placed_bodies(demo, capsys):
    code, data = run(capsys, "measure", "demo", "plate", "motor")
    assert code == cli.USAGE and "no part 'motor'" in data["error"] and "--posed" in data["error"]


def test_a_build_failure_with_no_message_says_where_to_look(demo, capsys):
    (demo / "parts" / "broken.py").write_text(BROKEN.replace('ValueError("wall thickness came out negative")',
                                                             "RuntimeError()"))
    code, data = run(capsys, "build", "demo", "broken")
    assert code == cli.FAIL and "RuntimeError" in data["error"] and "dimension" in data["error"]


def test_projects_may_follow_the_subcommand_like_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(st, "ROOT", st.ROOT)              # cli.main moves it to the folder named
    monkeypatch.delenv("CAD_PROJECTS", raising=False)
    (tmp_path / "alpha").mkdir()
    assert cli.main(["ls", "--projects", str(tmp_path), "--json"]) == cli.OK
    assert json.loads(capsys.readouterr().out)["data"]["projects"] == ["alpha"]


def test_ls_says_so_when_the_projects_folder_does_not_exist(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(st, "ROOT", tmp_path / "nope")
    assert cli.main(["ls"]) == cli.OK
    out = capsys.readouterr().out
    assert "no projects yet" in out and "does not exist" in out and "cad init" in out


def test_a_preference_asked_out_of_range_says_what_was_kept(capsys):
    assert cli.main(["pref", "MaxUndoSize", "500"]) == cli.OK
    out = capsys.readouterr().out
    assert "MaxUndoSize = 99" in out and "asked for 500" in out and "0 to 99" in out


def test_nothing_to_undo_says_so_when_undo_is_switched_off(demo, capsys):
    assert cli.main(["pref", "MaxUndoSize", "0"]) == cli.OK       # what `pref MaxUndoSize -4` leaves
    capsys.readouterr()
    for cmd in ("undo", "redo"):
        code, data = run(capsys, cmd, "demo")
        assert code == cli.USAGE and "nothing to" in data["error"] and "MaxUndoSize" in data["error"], cmd


def test_a_centre_of_gravity_and_a_tool_envelope_are_not_printed_as_minus_zero(demo, capsys):
    assert cli.main(["mass", "demo"]) == cli.OK
    assert "-0.000" not in capsys.readouterr().out
    assert cli.main(["tool", "drill", "diameter=3", "flute=20"]) == cli.OK
    assert "-0.0" not in capsys.readouterr().out


# ─── A design that fails to build fails the gates; it does not crash them ────────────────────

def test_an_assembly_that_raises_fails_the_gates_instead_of_crashing(demo, capsys):
    (demo / "assembly.py").write_text('def parts():\n    raise RuntimeError("no such body")\n')
    code, data = run(capsys, "check", "demo")
    assert code == cli.FAIL
    row = next(r for r in data["rows"] if r["check"] == "assembly" and r["rule"] == "build")
    assert row["state"] == "FAIL" and "no such body" in row["measured"]
    for cmd in ("verify", "mass"):
        code, data = run(capsys, cmd, "demo")
        assert code == cli.FAIL, cmd


def test_a_cutlist_reads_the_part_as_it_is_now_and_leaves_no_bytecode_behind(demo, monkeypatch, capsys):
    monkeypatch.setattr(sys, "dont_write_bytecode", False)
    part = demo / "parts" / "plate.py"
    part.write_text(PLATE + "\nCUTLIST = [{'kind': '2020', 'length_mm': 100, 'qty': 1}]\n")
    stamp = part.stat().st_mtime
    code, data = run(capsys, "cutlist", "demo")
    assert code == cli.OK and data["rows"][0]["length_mm"] == 100
    part.write_text(PLATE + "\nCUTLIST = [{'kind': '2020', 'length_mm': 200, 'qty': 1}]\n")
    os.utime(part, (stamp, stamp))                               # the same second, the same size
    code, data = run(capsys, "cutlist", "demo")
    assert data["rows"][0]["length_mm"] == 200
    assert not (demo / "parts" / "__pycache__").exists()


def test_the_top_level_help_names_the_warm_worker(capsys):
    # Messages tell people to `cad warm stop`; it is not a subcommand argparse lists.
    assert cli.main(["--help"]) == cli.OK
    assert "cad warm status|start|stop" in capsys.readouterr().out


def test_listing_a_read_only_project_does_not_write_into_it(tmp_path, monkeypatch, capsys):
    # `cad ls` and `bought ls` made the project's bought/ folder, so a project nobody could write to
    # (a read-only checkout) crashed on them.
    monkeypatch.setattr(st, "ROOT", tmp_path)
    (tmp_path / "ro" / "parts").mkdir(parents=True)
    (tmp_path / "ro" / "parts" / "plate.py").write_text(PLATE)
    for argv in (["ls", "ro"], ["bought", "ls", "ro"], ["status", "ro"]):
        code, data = run(capsys, *argv)
        assert code == cli.OK, argv
    assert not (tmp_path / "ro" / "bought").exists()


def test_a_folder_that_refuses_the_write_is_a_usage_error_naming_it(demo, monkeypatch, capsys):
    real = Path.mkdir

    def refuse(self, *a, **kw):
        if self.name == "out":
            raise PermissionError(13, "Permission denied", str(self))
        return real(self, *a, **kw)
    monkeypatch.setattr(Path, "mkdir", refuse)
    for argv in (["render", "demo", "plate"], ["check", "demo", "--part", "plate"]):
        code, data = run(capsys, *argv)
        assert code == cli.USAGE and "cannot write" in data["error"] and "out" in data["error"], argv


def test_a_projects_path_that_is_a_file_is_a_usage_error_not_a_crash(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(st, "ROOT", st.ROOT)
    monkeypatch.delenv("CAD_PROJECTS", raising=False)
    not_a_folder = tmp_path / "part.py"
    not_a_folder.write_text("")
    for argv in (["ls"], ["status", "demo"], ["init", "demo"]):
        assert cli.main(["--json", "--projects", str(not_a_folder), *argv]) == cli.USAGE, argv
        out = capsys.readouterr()
        assert "is not a folder" in json.loads(out.out)["data"]["error"] and "Traceback" not in out.err


def test_a_part_that_cannot_be_built_fails_export_approve_and_cutlist_instead_of_crashing(demo, capsys):
    (demo / "parts" / "plate.py").write_text("def build(:\n")                  # a syntax error
    (demo / "parts" / "block.py").write_text('PARAMS = {}\n')                  # no build()
    for argv in (["export", "demo", "plate"], ["export", "demo", "block"], ["approve", "demo"],
                 ["cutlist", "demo"]):
        code, data = run(capsys, *argv)
        assert code == cli.FAIL and "did not build" in data["error"], argv


def test_a_build_that_returns_no_solid_fails_the_part_not_the_tool(demo, capsys):
    (demo / "parts" / "plate.py").write_text(PLATE.replace("    return part\n", "    return None\n"))
    code, data = run(capsys, "build", "demo", "plate")
    assert code == cli.FAIL and "returned NoneType, not a solid" in data["error"]
    for cmd in ("check", "verify"):
        code, data = run(capsys, cmd, "demo")
        assert code == cli.FAIL, cmd


def test_an_assembly_that_returns_the_wrong_thing_fails_with_what_it_returned(demo, capsys):
    # parts() gave back a list, a number where a solid goes, or a key that is not a name: each
    # crashed another command with exit 4 and an AttributeError from deep in the renderer.
    for text, shown in (("def parts():\n    return [1, 2]\n", "got list"),
                        ("def parts():\n    return {'a': 5}\n", "'a': int"),
                        ("def parts():\n    return {1: None}\n", "1: NoneType")):
        (demo / "assembly.py").write_text(text)
        for argv in (["mass", "demo"], ["render", "demo"], ["place", "demo", "a", "--by=1,0,0"],
                     ["measure", "demo", "a", "b", "--posed"]):
            code, data = run(capsys, *argv)
            assert code == cli.FAIL and shown in data["error"], (text, argv)
        code, data = run(capsys, "check", "demo")
        row = next(r for r in data["rows"] if r["check"] == "assembly" and r["rule"] == "build")
        assert code == cli.FAIL and shown in row["measured"], text


def test_status_says_what_to_do_about_a_checks_json_it_cannot_read(demo, capsys):
    (demo / "checks.json").write_text("{not json")
    assert cli.main(["status", "demo"]) == cli.OK
    assert "cannot be read" in capsys.readouterr().out


def test_set_on_a_part_file_that_is_not_text_fails_the_part_not_the_tool(demo, capsys):
    (demo / "parts" / "plate.py").write_bytes(b"# \xff\xfe not UTF-8\nPARAMS = {}\n")
    code, data = run(capsys, "set", "demo", "plate", "thickness=5")
    assert code == cli.FAIL and "plate does not parse" in data["error"]

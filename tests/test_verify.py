"""The verifier's rules: a verdict counts only while it still describes the files.

These call verify.run with fresh=True, standing in for a fresh process, so each
rule is tested without paying a kernel import per case. test_warm.py covers the
real fresh path, a verify through bin/cad and the warm worker.
"""
import subprocess

import pytest

from cad_agent import cli, verify
from cad_agent import state as st
from test_cli import ASSEMBLY, BLOCK, PLATE, run

# The plate spans z -2..2 and the block z 15..25: a 13 mm gap, 40 x 20 x 27 overall.
SPEC = '''[envelope]
max_mm = [50, 30, 30]

[[clearance]]
a = "plate"
b = "block"
min_mm = 10
'''


@pytest.fixture()
def demo(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "ROOT", tmp_path)
    monkeypatch.delenv("CAD_PROJECTS", raising=False)
    d = st.project_dir("demo", create=True)
    (d / "parts" / "plate.py").write_text(PLATE)
    (d / "parts" / "block.py").write_text(BLOCK)
    (d / "assembly.py").write_text(ASSEMBLY)
    (d / "spec.toml").write_text(SPEC)            # without one, nothing can PASS
    from cad_agent.runner import approve_views, check_all
    check_all("demo")
    approve_views("demo")          # baselines exist, so the visual gate can pass
    return d


def git(d, *args):
    return subprocess.run(["git", "-C", str(d), "-c", "user.name=t", "-c", "user.email=t@t",
                           *args], check=True, capture_output=True, text=True).stdout.strip()


def test_a_clean_design_passes_and_is_done(demo, capsys):
    rec = verify.run("demo", fresh=True, mode="test")
    assert rec["verdict"] == "PASS", [r for r in rec["rows"] if r["state"] != "PASS"]
    assert (demo / "verify.json").exists()
    assert rec["design_files"] >= 5               # 2 parts, assembly, 2+ baselines
    assert verify.status("demo")["done"] is True
    code, data = run(capsys, "done", "demo")
    assert code == cli.OK and data["done"] is True


def test_a_process_that_already_ran_commands_cannot_pass(demo):
    rec = verify.run("demo", fresh=False, mode="reused")
    assert rec["verdict"] == "UNCHECKED"
    assert "not a fresh process" in " ".join(rec["notes"])
    assert verify.status("demo")["done"] is False


def test_editing_the_design_makes_the_verdict_stale(demo, capsys):
    verify.run("demo", fresh=True, mode="test")
    part = demo / "parts" / "plate.py"
    part.write_text(part.read_text().replace('"thickness": 4.0', '"thickness": 5.0'))
    s = verify.status("demo")
    assert s["done"] is False and "the design changed since it was verified" in s["reasons"]
    code, _ = run(capsys, "done", "demo")
    assert code == cli.UNCHECKED


def test_approving_a_new_render_is_a_design_change(demo):
    verify.run("demo", fresh=True, mode="test")
    baseline = sorted((demo / "baseline").glob("*.png"))[0]
    baseline.write_bytes(baseline.read_bytes() + b"\0")
    assert "the design changed since it was verified" in verify.status("demo")["reasons"]


def test_run_outputs_are_not_design(demo):
    verify.run("demo", fresh=True, mode="test")
    (demo / "checks.json").write_text("{}")        # outputs change on every run
    (demo / "out" / "extra.png").write_bytes(b"x")
    assert verify.status("demo")["done"] is True


def test_a_rule_change_makes_the_verdict_stale(demo, monkeypatch):
    verify.run("demo", fresh=True, mode="test")
    monkeypatch.setattr(verify, "engine_hash", lambda: "different")
    assert "cad-agent's rules changed since it was verified" in verify.status("demo")["reasons"]


def test_a_rule_change_during_the_run_leaves_the_verdict_unchecked(demo, monkeypatch):
    # A `git pull` while `cad verify` runs: the process imported some rules before it and some
    # after, and the hash it would write describes only the files on disk at the end.
    seen = iter(["rules as the run began", "rules as the run ended"])
    monkeypatch.setattr(verify, "engine_hash", lambda: next(seen))
    rec = verify.run("demo", fresh=True, mode="test")
    assert rec["verdict"] == "UNCHECKED"
    assert "cad-agent's own code changed while it was being verified" in " ".join(rec["notes"])
    assert rec["engine_hash"] == "rules as the run began"


def test_a_failing_design_fails_the_gate(demo, capsys):
    # The block moves down into the plate: the fit gate must fail.
    (demo / "assembly.py").write_text(ASSEMBLY.replace("Pos(0, 0, 20)", "Pos(0, 0, 0)"))
    rec = verify.run("demo", fresh=True, mode="test")
    assert rec["verdict"] == "FAIL"
    code, data = run(capsys, "done", "demo")
    assert code == cli.FAIL and data["verdict"] == "FAIL"


def test_in_a_repo_only_committed_work_counts(demo):
    git(demo, "init", "-q", "-b", "main")
    git(demo, "add", "-A")
    git(demo, "commit", "-q", "-m", "design")
    rec = verify.run("demo", fresh=True, mode="test")
    assert rec["git"]["commit"] == git(demo, "rev-parse", "HEAD")
    assert rec["git"]["dirty"] is False           # rewriting checks.json and out/ is not a change
    assert verify.status("demo")["done"] is True

    part = demo / "parts" / "block.py"
    part.write_text(part.read_text().replace('"size": 10.0', '"size": 9.0'))
    rec = verify.run("demo", fresh=True, mode="test")
    assert rec["verdict"] == "PASS" and rec["git"]["dirty"] is True
    s = verify.status("demo")
    assert s["done"] is False and any("uncommitted" in r for r in s["reasons"])

    git(demo, "commit", "-q", "-am", "smaller block")
    verify.run("demo", fresh=True, mode="test")
    assert verify.status("demo")["done"] is True

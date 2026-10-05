"""The Claude Code hooks in .claude/hooks, driven the way Claude Code drives them:
JSON on stdin, JSON (or nothing) on stdout.

The edit hook runs `bin/cad check` through a warm worker kept in a temporary
CAD_WARM_DIR, so only the first check pays the kernel import. The stop hook
only calls `cad done`, which never imports the kernel.
"""
import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from test_cli import PLATE

REPO = Path(__file__).resolve().parent.parent
EDIT = REPO / ".claude" / "hooks" / "cad_on_edit.py"
STOP = REPO / ".claude" / "hooks" / "cad_on_stop.py"


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    e = dict(os.environ, CAD_WARM_DIR=str(tmp_path_factory.mktemp("warm")))
    e.pop("CAD_WARM", None)
    e.pop("CAD_PROJECTS", None)
    yield e
    subprocess.run([str(REPO / "bin" / "cad"), "warm", "stop"], env=e, capture_output=True)


@pytest.fixture()
def project(tmp_path):
    d = tmp_path / "rig" / "parts"
    d.mkdir(parents=True)
    (d / "plate.py").write_text(PLATE)
    return tmp_path, tmp_path / "rig"


def hook(script, event, env, **extra):
    p = subprocess.run(["python3", str(script)], input=json.dumps(event), capture_output=True,
                       text=True, env=dict(env, **extra), timeout=300)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout) if p.stdout.strip() else None


def edit(path):
    return {"tool_name": "Edit", "tool_input": {"file_path": str(path)}}


def test_edit_hook_ignores_files_that_are_not_design(env, project):
    root, rig = project
    (rig / "notes.md").write_text("hello")
    assert hook(EDIT, edit(rig / "notes.md"), env) is None


def test_edit_hook_is_silent_on_a_passing_part_and_reports_a_failing_one(env, project):
    root, rig = project
    part = rig / "parts" / "plate.py"
    assert hook(EDIT, edit(part), env) is None      # drift waits on approval: not reported
    part.write_text(PLATE.replace('"thickness": 4.0', '"thickness": 0.5'))
    out = hook(EDIT, edit(part), env)
    assert out["decision"] == "block"
    assert "cad check rig/plate" in out["reason"] and "FAIL" in out["reason"]
    assert "min wall" in out["reason"]


def test_stop_hook_lets_a_second_stop_through(env):
    assert hook(STOP, {"stop_hook_active": True}, env) is None


# ─── The eval tasks are fixtures, not projects ───────────────────────────────

FAILING = PLATE.replace('"thickness": 4.0', '"thickness": 0.5')       # fails its wall gate


def listing(root):
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))


@pytest.fixture()
def checkout(tmp_path):
    """The layout of a cad-agent checkout's evals/: a README, and a task whose reference design
    has parts/ and assembly.py like a project. Returns (the checkout, the task's folder)."""
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "README.md").write_text("# evals\n")
    ref = tmp_path / "evals" / "task" / "reference"
    (ref / "parts").mkdir(parents=True)
    (ref / "parts" / "plate.py").write_text(FAILING)
    (ref / "assembly.py").write_text("def parts():\n    return {}\n")
    return tmp_path, tmp_path / "evals" / "task"


def test_the_hooks_leave_the_eval_tasks_alone(env, checkout):
    """Checking, logging or listing an eval task's reference piles .cad/, out/ and checks.json up
    in the repo, and a stop blocked over a design nobody is verifying."""
    root, task = checkout
    before = listing(root)
    for path in (task / "reference" / "parts" / "plate.py", task / "reference" / "assembly.py"):
        assert hook(EDIT, dict(edit(path), session_id="sess-evals"), env) is None
    assert hook(STOP, {"session_id": "sess-evals"}, env) is None       # and no touched record
    # What an older edit hook would have recorded for this session, and a projects folder
    # pointed at the task: the stop hook does not list them either.
    (Path(env["CAD_WARM_DIR"]) / "touched-sess-old.tsv").write_text(f"{task}\treference\n")
    assert hook(STOP, {"session_id": "sess-old"}, env) is None
    assert hook(STOP, {}, env, CAD_PROJECTS=str(task)) is None
    assert listing(root) == before


def test_without_the_evals_readme_it_is_an_ordinary_folder(env, checkout):
    """The marker is what makes a folder a checkout's evals/; the same files elsewhere are a project."""
    root, task = checkout
    (root / "evals" / "README.md").unlink()
    part = task / "reference" / "parts" / "plate.py"
    out = hook(EDIT, dict(edit(part), session_id="sess-plain"), env)
    assert out["decision"] == "block" and "cad check reference/plate" in out["reason"]
    out = hook(STOP, {"session_id": "sess-plain"}, env)
    assert out["decision"] == "block" and "reference" in out["reason"]


def test_a_project_that_is_called_evals_is_still_checked(env, tmp_path):
    rig = tmp_path / "evals"
    (rig / "parts").mkdir(parents=True)
    (rig / "parts" / "plate.py").write_text(FAILING)
    (rig / "README.md").write_text("notes on this design\n")
    out = hook(EDIT, edit(rig / "parts" / "plate.py"), env)
    assert out["decision"] == "block" and "cad check evals/plate" in out["reason"]


def git(d, *args):
    subprocess.run(["git", "-C", str(d), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   check=True, capture_output=True)


def test_stop_hook_blocks_on_a_project_this_session_edited(env, project):
    root, rig = project
    part = rig / "parts" / "plate.py"
    hook(EDIT, dict(edit(part), session_id="sess-1"), env)       # the edit hook records it
    out = hook(STOP, {"session_id": "sess-1"}, env)               # no CAD_PROJECTS needed
    assert out["decision"] == "block"
    assert "rig" in out["reason"] and "never verified" in out["reason"]
    assert hook(STOP, {"session_id": "another-session"}, env) is None


def test_stop_hook_blocks_on_uncommitted_design_changes(env, project):
    root, rig = project
    git(rig, "init", "-q")
    git(rig, "add", "-A")
    git(rig, "commit", "-q", "-m", "design")
    part = rig / "parts" / "plate.py"
    part.write_text(part.read_text().replace('"thickness": 4.0', '"thickness": 5.0'))
    out = hook(STOP, {}, env, CAD_PROJECTS=str(root))
    assert out["decision"] == "block" and "uncommitted" in out["reason"]


def test_stop_hook_leaves_untouched_projects_alone(env, project):
    """Never verified, but committed and not edited this session: not this session's business.
    A fresh clone makes every file look new, so file times must not decide this."""
    root, rig = project
    git(rig, "init", "-q")
    git(rig, "add", "-A")
    git(rig, "commit", "-q", "-m", "design")
    now = time.time()
    for p in rig.rglob("*"):
        os.utime(p, (now, now))                                   # brand-new file times
    assert hook(STOP, {}, env, CAD_PROJECTS=str(root)) is None

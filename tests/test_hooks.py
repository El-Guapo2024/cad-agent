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

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
from types import SimpleNamespace

import pytest

from conftest import cad_env
from test_cli import ASSEMBLY, BLOCK, PLATE, _checkouts, _stub

REPO = Path(__file__).resolve().parent.parent
EDIT =REPO / ".claude" / "hooks" / "cad_on_edit.py"
STOP = REPO / ".claude" / "hooks" / "cad_on_stop.py"


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    e = cad_env(CAD_WARM_DIR=str(tmp_path_factory.mktemp("warm")))
    e.pop("CAD_WARM", None)
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


def test_edit_hook_reports_a_part_that_has_grown_into_its_neighbour(env, project):
    """A part edit is judged against the other bodies of the assembly too, which the build cache
    supplies, so the interference shows up at the edit and not at the next full check."""
    root, rig = project
    (rig / "parts" / "block.py").write_text(BLOCK)
    (rig / "assembly.py").write_text(ASSEMBLY.replace('SLUG = "demo"', 'SLUG = "rig"'))
    part = rig / "parts" / "plate.py"
    assert hook(EDIT, edit(part), env) is None             # the block sits 13 mm above the plate
    part.write_text(PLATE.replace('"thickness": 4.0', '"thickness": 40.0'))
    out = hook(EDIT, edit(part), env)
    assert out["decision"] == "block" and "cad check rig/plate" in out["reason"]
    assert "FAIL" in out["reason"] and "interference" in out["reason"] and "block vs plate" in out["reason"]
    part.write_text(PLATE)
    assert hook(EDIT, edit(part), env) is None


def test_the_install_script_asks_uv_to_look_at_the_interpreter_again():
    """uv keeps what an interpreter reported and a record made without SYSTEM_VERSION_COMPAT=0 turns
    down embreex's wheel; every uv install in the script says to refresh (see the comment in it)."""
    script = REPO / "plugin" / "install.sh"
    assert subprocess.run(["sh", "-n", str(script)], capture_output=True).returncode == 0
    installs = [ln for ln in script.read_text().splitlines() if ln.strip().startswith("uv pip install")]
    assert len(installs) == 2 and all("--refresh-package" in ln for ln in installs)


# ─── The install script, run offline with tools that only log what they are asked ───

# What a venv's python finds when the script asks it to load the kernel, so that a test can say the
# session was already usable by then: `cad` linked into the plugin's bin, and the env file written.
_PY_STUB = """#!/bin/sh
usable=no
[ -L "$FAKE_DATA/bin/cad" ] && grep -q CAD_PYTHON "$FAKE_ENV" && usable=yes
echo "python $* [warm=${CAD_WARM:-unset} bytecode=<${PYTHONDONTWRITEBYTECODE-unset}> usable=$usable]" >> "$FAKE_LOG"
[ -z "${FAKE_KERNEL_FAILS:-}" ]
"""
_PIP_STUB = """#!/bin/sh
echo "pip $* [compat=${SYSTEM_VERSION_COMPAT:-unset}]" >> "$FAKE_LOG"
case "$*" in *"[embree]"*) [ -z "${FAKE_EMBREE_FAILS:-}" ] ;; esac
"""
_UV_STUB = """#!/bin/sh
echo "uv $* [compat=${SYSTEM_VERSION_COMPAT:-unset}]" >> "$FAKE_LOG"
case "$1" in
  venv) for last; do :; done; mkdir -p "$last/bin"; cp "$FAKE_PYTHON" "$last/bin/python"; chmod +x "$last/bin/python" ;;
  pip) case "$*" in *"[embree]"*) [ -z "${FAKE_EMBREE_FAILS:-}" ] ;; esac ;;
esac
"""
_PYTHON313_STUB = """#!/bin/sh
case "$1" in
  -c) echo "probe $2" >> "$FAKE_LOG"; exit 0 ;;
  -m) mkdir -p "$3/bin"; cp "$FAKE_PYTHON" "$3/bin/python"; cp "$FAKE_PIP" "$3/bin/pip"
      chmod +x "$3/bin/python" "$3/bin/pip" ;;
esac
"""


def _install(tmp_path, uv=True, **flags):
    """Run plugin/install.sh as a SessionStart hook does, with a uv (or, without one, a python3.13) and a
    venv python that log their calls in tmp_path/calls.log. Returns an object with run() for another start."""
    s = SimpleNamespace()
    s.root, s.data, s.project = tmp_path / "root", tmp_path / "data", tmp_path / "proj"
    s.env_file, s.log = tmp_path / "session-env.sh", tmp_path / "calls.log"
    (s.root / "bin").mkdir(parents=True)
    (s.root / "pyproject.toml").write_text('[project]\nname = "cad-agent"\nversion = "9.9.9"\n')
    (s.root / "bin" / "cad").write_text("#!/bin/sh\n")
    s.project.mkdir()
    s.env_file.write_text("")
    fake = tmp_path / "fakebin"
    fake.mkdir()
    for name, text in (("python_stub", _PY_STUB), ("pip_stub", _PIP_STUB)):
        (tmp_path / name).write_text(text)
    for name, text in (("uv", _UV_STUB),) if uv else (("python3.13", _PYTHON313_STUB),):
        (fake / name).write_text(text)
        (fake / name).chmod(0o755)
    env = {"PATH": f"{fake}:/usr/bin:/bin", "HOME": str(tmp_path / "home"),
           "CLAUDE_PLUGIN_ROOT": str(s.root), "CLAUDE_PLUGIN_DATA": str(s.data),
           "CLAUDE_PROJECT_DIR": str(s.project), "CLAUDE_ENV_FILE": str(s.env_file),
           "FAKE_LOG": str(s.log), "FAKE_DATA": str(s.data), "FAKE_ENV": str(s.env_file),
           "FAKE_PYTHON": str(tmp_path / "python_stub"), "FAKE_PIP": str(tmp_path / "pip_stub"), **flags}
    s.run = lambda: subprocess.run(["sh", str(REPO / "plugin" / "install.sh")], env=env, cwd=s.project,
                                   capture_output=True, text=True, timeout=60)
    s.calls = lambda: s.log.read_text().splitlines() if s.log.exists() else []
    s.pkg = f"{s.root}[metal]" if os.uname().sysname == "Darwin" else str(s.root)
    s.first = s.run()
    return s


def test_the_install_script_installs_once_and_loads_the_kernel_once_cad_is_in_place(tmp_path):
    s = _install(tmp_path)
    assert s.first.returncode == 0, s.first.stderr
    assert s.first.stdout == ""                       # a hook's stdout reaches the model: all talk is stderr
    calls = s.calls()
    uv = [c for c in calls if c.startswith("uv ")]
    # The kernel's wheels stop at Python 3.14 (OCP has no cp315, build123d says <3.15): a uv that knows
    # 3.15 would otherwise pick it on a machine with no other 3.12+, and the install would not resolve.
    assert uv[0] == f"uv venv -q --python >=3.12,<3.15 {s.data / 'venv'} [compat=0]"
    assert f"-e {s.pkg} [compat=0]" in uv[1] and f"-e {s.root}[embree] [compat=0]" in uv[2]
    assert (s.data / "installed").read_text().strip() == f"9.9.9 {s.root}"
    assert (s.data / "bin" / "cad").resolve() == (s.root / "bin" / "cad").resolve()
    env_lines = s.env_file.read_text().splitlines()
    assert env_lines[0] == f'export CAD_PYTHON="{s.data / "venv" / "bin" / "python"}"'
    assert env_lines[2] == f'export CAD_PROJECTS="{s.project}/cad-projects"'
    # The first import of the new venv takes minutes on a Mac (every native library is checked the first
    # time it loads), so it happens here and not in the first `cad` call: with bytecode caching forced on, no
    # worker, and only once `cad` is on PATH and the session env is written, so a hook cut short there loses nothing.
    py = [c for c in calls if c.startswith("python ")]
    assert py[0] == "python -P -m cad_agent.warm --version [warm=0 bytecode=<> usable=yes]"
    assert py[1].startswith("python -P -c import trimesh, embreex")
    assert calls.index(uv[-1]) < calls.index(py[0])
    # Started again with the install in place, it only sets up the session.
    before = s.calls()
    again = s.run()
    assert again.returncode == 0 and again.stdout == ""
    assert s.calls() == before
    assert len(s.env_file.read_text().splitlines()) == 2 * len(env_lines)


def test_a_kernel_that_will_not_start_after_the_install_is_said_and_does_not_undo_it(tmp_path):
    s = _install(tmp_path, FAKE_KERNEL_FAILS="1")
    assert s.first.returncode == 0 and "the CAD kernel did not start" in s.first.stderr
    assert (s.data / "installed").exists() and (s.data / "bin" / "cad").is_symlink()
    assert "CAD_PYTHON" in s.env_file.read_text()


def test_a_platform_without_embree_still_installs(tmp_path):
    s = _install(tmp_path, FAKE_EMBREE_FAILS="1")
    assert s.first.returncode == 0 and "Embree not installed" in s.first.stderr
    assert (s.data / "installed").exists()


def test_without_uv_the_script_makes_its_venv_with_python_and_pip(tmp_path):
    s = _install(tmp_path, uv=False)
    assert s.first.returncode == 0, s.first.stderr
    pip = [c for c in s.calls() if c.startswith("pip ")]
    assert pip == [f"pip install -q -e {s.pkg} [compat=0]", f"pip install -q -e {s.root}[embree] [compat=0]"]
    probe = next(c for c in s.calls() if c.startswith("probe "))     # the python it accepts: 3.12 to 3.14
    assert "(3, 12) <= sys.version_info[:2] < (3, 15)" in probe
    assert any(c.startswith("python -P -m cad_agent.warm --version") for c in s.calls())
    assert (s.data / "installed").exists()


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


def test_the_hooks_run_the_python_bin_cad_picks_in_a_worktree(tmp_path):
    """The hooks call bin/cad, so a worktree's hooks get the main checkout's venv, not the plugin's."""
    main, wt = _checkouts(tmp_path)
    _stub(main / ".venv" / "bin" / "python", code=1)           # exit 1, so the hook reports its output
    _stub(tmp_path / "home" / ".claude" / "plugins" / "data" / "cad-agent-x" / "venv" / "bin" / "python", code=1)
    part = tmp_path / "projects" / "rig" / "parts" / "plate.py"
    part.parent.mkdir(parents=True)
    part.write_text(PLATE)
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path / "home")}
    out = hook(wt / ".claude" / "hooks" / "cad_on_edit.py", edit(part), env)
    assert f"ran:{main / '.venv' / 'bin' / 'python'}" in out["reason"]
    assert f"pythonpath:{wt}" in out["reason"]

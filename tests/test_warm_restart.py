"""A running worker never serves a command on code older than the disk's.

`cad verify` hashes every cad_agent file into its verdict, so a worker that went on running a
file it had loaded before a `git pull` would record a verdict under rules it never ran. A command's
fork imports cad_agent fresh, so most edits need nothing; what the worker itself holds (warm.py,
the sidecar's files, the preloaded kernel) is what it must notice, and then restart.

The worker here runs from a copy of cad_agent in a temporary folder, so the tests can edit its
files without touching the repo's. It is started once for the module (a kernel import, 5 to 35 s
on this machine), and each restart costs another.
"""
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from conftest import cad_env
from cad_agent import warm as w

REPO = Path(__file__).resolve().parent.parent

SLOW = '''"""A part whose build takes a few seconds, standing in for a long command."""
import time
from pathlib import Path
from build123d import Box

MATERIAL = "petg"
PROCESS = "fdm"
MIN_FEATURE_MM = 1.2
PARAMS = {}


def build():
    (Path(__file__).parent / "started").write_text("1")
    time.sleep(5)
    return Box(10, 10, 10)
'''


def edit(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    assert old in text, f"{old!r} is not in {path.name}"
    path.write_text(text.replace(old, new, 1))


def modules_of(statement: str) -> set[str]:
    """The cad_agent files a fresh interpreter has loaded after `statement`."""
    code = (f"{statement}; import sys, json; "
            "print(json.dumps(sorted(m for m in sys.modules if m.split('.')[0] == 'cad_agent')))")
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
                       cwd=REPO)
    assert p.returncode == 0, p.stderr
    return {"__init__.py" if m == "cad_agent" else m.split(".", 1)[1] + ".py"
            for m in json.loads(p.stdout)}


# ─── What is watched, and a restart that cannot happen ───────────────────────

def test_the_watched_files_are_the_ones_the_processes_load():
    # A file a process loads but the list misses is a file whose edit it would never notice.
    assert modules_of("import cad_agent.warm") == set(w.OWN_CODE)
    assert modules_of("import cad_agent.metal_render") == set(w.SIDECAR_CODE)
    assert all((REPO / "cad_agent" / n).is_file() for n in (*w.OWN_CODE, *w.SIDECAR_CODE))


def test_a_watch_sees_other_bytes_and_ignores_a_rewrite(tmp_path):
    f, absent = tmp_path / "a.py", tmp_path / "absent.py"
    f.write_text("x = 1\n")
    watch = w._Watch([f, absent])
    assert watch.changed() == []
    f.write_text("x = 1\n")                         # what `git checkout` and `touch` do
    os.utime(f, ns=(1, 1))
    assert watch.changed() == []
    f.write_text("x = 2\n")
    assert watch.changed() == [f]
    f.unlink()                                      # gone is changed too
    absent.write_text("")                           # and so is a file that appears
    assert set(watch.changed()) == {f, absent}


def test_the_check_costs_microseconds_when_nothing_changed():
    watch = w._Watch([w.PKG / n for n in (*w.OWN_CODE, *w.SIDECAR_CODE)] + w._kernel_files())
    t0 = time.perf_counter()
    for _ in range(500):
        assert watch.changed() == []
    assert (time.perf_counter() - t0) / 500 < 0.002      # about 25 us here; 2 ms is a regression


def test_the_kernel_the_worker_preloads_is_watched():
    names = {p.parent.name for p in w._kernel_files()}
    assert names == set(w.PRELOAD)


def test_a_worker_that_cannot_exec_itself_hands_control_back_to_stop(tmp_path, monkeypatch, capsys):
    # The interpreter can be gone (a venv rebuilt under it); serving on the old code is the one
    # thing a restart exists to prevent, so the caller must be told to stop.
    class Sidecar:
        stopped = False

        def stop(self):
            self.stopped = True

    srv, sidecar = socket.socket(socket.AF_UNIX), Sidecar()
    lock = open(tmp_path / "w.lock", "w")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "no-such-python"))
    w._restart(tmp_path / "w.sock", srv, lock, sidecar, 0, [tmp_path / "warm.py"])
    assert sidecar.stopped and w.INHERIT_ENV not in os.environ
    assert "cannot restart" in capsys.readouterr().out
    srv.close()
    lock.close()


# ─── A running worker ────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def farm(tmp_path_factory):
    """(cad, copy, projects): a worker started from a copy of cad_agent, and a client for it.

    cad(*argv) is what bin/cad runs, from the copy, so the worker and its forks import the copy.
    """
    copy = tmp_path_factory.mktemp("copy")
    shutil.copytree(REPO / "cad_agent", copy / "cad_agent",
                    ignore=shutil.ignore_patterns("workbench", "__pycache__"))
    projects = tmp_path_factory.mktemp("projects")
    (projects / "demo" / "parts").mkdir(parents=True)
    (projects / "demo" / "parts" / "slow.py").write_text(SLOW)
    env = cad_env(CAD_PROJECTS=str(projects), CAD_WARM_DIR=str(tmp_path_factory.mktemp("warm")),
                  PYTHONPATH=str(copy))
    env.pop("CAD_WARM", None)

    def cad(*argv, wait=True):
        cmd = [sys.executable, "-m", "cad_agent.warm", *argv]
        if not wait:
            return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                    env=env, cwd=copy)
        return subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=copy, timeout=300)
    cad.env = env

    started = cad("warm", "start")
    assert started.returncode == 0, started.stderr
    try:
        yield cad, copy, projects
    finally:
        cad("warm", "stop")


def status(cad) -> dict:
    p = cad("warm", "status")
    assert p.returncode == 0, p.stderr
    found = {"pid": re.search(r"worker (\d+)", p.stdout), "socket": re.search(r"socket (\S+)", p.stdout),
             "restarts": re.search(r"restarted (\d+) time", p.stdout),
             "sidecar": re.search(r"metal sidecar (\d+)", p.stdout)}
    return {k: (v.group(1) if v else None) for k, v in found.items()}


def restarts(st: dict) -> int:
    return int(st["restarts"] or 0)


def test_an_edit_to_a_rule_runs_on_the_next_command_and_needs_no_restart(farm):
    cad, copy, _ = farm
    before = status(cad)
    edit(copy / "cad_agent" / "cli.py", 'print(f"cad-agent ', 'print(f"MARK-a cad-agent ')
    p = cad("--version")
    assert p.returncode == 0 and "MARK-a cad-agent" in p.stdout, p.stderr
    assert status(cad) == before                    # the same worker, never restarted


def test_an_edit_to_the_workers_own_code_restarts_it_without_a_command(farm):
    cad, copy, _ = farm
    before = status(cad)
    edit(copy / "cad_agent" / "warm.py", "        from cad_agent import cli ",
         '        print("MARK-b", file=sys.stderr)\n        from cad_agent import cli ')
    log = Path(before["socket"]).with_suffix(".log")
    deadline = time.monotonic() + 30
    while "changed on disk, restarting" not in log.read_text() and time.monotonic() < deadline:
        time.sleep(0.2)                             # it notices by itself, between commands
    assert "warm.py changed on disk, restarting" in log.read_text()
    p = cad("--version")                            # waits in the queue for the new worker
    assert p.returncode == 0 and "MARK-b" in p.stderr, p.stderr
    after = status(cad)
    assert restarts(after) == restarts(before) + 1 and after["pid"] == before["pid"]


def test_a_restart_lets_the_command_in_flight_finish_and_serves_the_next_on_new_code(farm):
    cad, copy, projects = farm
    before = status(cad)
    started = projects / "demo" / "parts" / "started"
    started.unlink(missing_ok=True)
    slow = cad("build", "demo", "slow", wait=False)
    deadline = time.monotonic() + 60
    while not started.exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    assert started.exists(), "the slow build never began"
    edit(copy / "cad_agent" / "warm.py", "MARK-b", "MARK-c")
    p = cad("--version")                            # arrives while the build runs
    assert p.returncode == 0 and "MARK-c" in p.stderr, p.stderr
    out, err = slow.communicate(timeout=60)
    assert slow.returncode == 0, err                # not cut short by the restart
    assert "10.0" in out
    assert restarts(status(cad)) == restarts(before) + 1


@pytest.mark.skipif(sys.platform != "darwin" or importlib.util.find_spec("Metal") is None,
                    reason="the Metal sidecar exists only on a Mac with PyObjC's Metal")
def test_an_edit_to_the_sidecars_code_restarts_the_worker_and_its_sidecar(farm):
    cad, copy, _ = farm
    before = status(cad)
    assert before["sidecar"]
    path = copy / "cad_agent" / "metal_render.py"
    path.write_text(path.read_text() + "\n# edited under a running sidecar\n")
    p = cad("--version")
    assert p.returncode == 0, p.stderr
    after = status(cad)
    assert restarts(after) == restarts(before) + 1
    assert after["sidecar"] not in (None, before["sidecar"])

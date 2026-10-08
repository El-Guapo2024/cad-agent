"""The warm worker: bin/cad through a background process that imported the
kernel once. What must hold is that it changes speed and nothing else: same
output, same exit codes, and an edit to a part is seen on the very next call.

One worker is started for the module, in a temporary CAD_WARM_DIR so it never
touches ~/.cache, and stopped at the end even if a test fails. Starting it
costs one kernel import (20-35 s on this machine).
"""
import json
import re
import subprocess
import time
from pathlib import Path

import pytest

from cad_agent import warm as warm_module
from conftest import cad_env
from test_cli import BLOCK, PLATE

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def warm(tmp_path_factory):
    root = tmp_path_factory.mktemp("projects")
    d = root / "demo" / "parts"
    d.mkdir(parents=True)
    (d / "plate.py").write_text(PLATE)
    (d / "block.py").write_text(BLOCK)
    env = cad_env(CAD_PROJECTS=str(root), CAD_WARM_DIR=str(tmp_path_factory.mktemp("warm")),
                  CAD_MACRO_DIR=str(tmp_path_factory.mktemp("macros")))
    env.pop("CAD_WARM", None)

    def cad(*argv):
        return subprocess.run([str(REPO / "bin" / "cad"), *argv], capture_output=True,
                              text=True, env=env, timeout=300)
    cad.env = env

    started = cad("warm", "start")
    assert started.returncode == 0, started.stderr
    try:
        yield cad, root
    finally:
        cad("warm", "stop")


def test_output_and_exit_codes_match_the_cold_path(warm):
    cad, _ = warm
    p = cad("--json", "ls", "demo")
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["data"]["parts"] == ["block", "plate"]
    assert cad("build", "nope", "plate").returncode == 3
    p = cad("--json", "measure", "demo", "plate", "block")
    assert p.returncode == 1 and json.loads(p.stdout)["data"]["interferes"] is True


def test_a_warm_call_skips_the_kernel_import(warm):
    cad, _ = warm
    t0 = time.monotonic()
    p = cad("build", "demo", "block")
    assert p.returncode == 0, p.stderr
    assert time.monotonic() - t0 < 15          # cold is 20-35 s of import alone


def test_an_edited_part_is_seen_on_the_next_call(warm):
    cad, root = warm
    part = root / "demo" / "parts" / "plate.py"
    p = cad("--json", "build", "demo", "plate")
    assert json.loads(p.stdout)["data"]["bbox_mm"][2] == 4.0
    part.write_text(PLATE.replace('"thickness": 4.0', '"thickness": 7.0'))
    p = cad("--json", "build", "demo", "plate")
    assert json.loads(p.stdout)["data"]["bbox_mm"][2] == 7.0


def test_verify_through_the_worker_runs_fresh(warm):
    cad, _ = warm
    p = cad("--json", "verify", "demo")
    assert p.returncode in (0, 1, 2), p.stderr
    assert json.loads(p.stdout)["data"]["process"] == {"fresh": True, "mode": "warm-fork"}
    d = cad("--json", "done", "demo")
    assert (d.returncode == 0) == json.loads(d.stdout)["data"]["done"]


def test_status_counts_what_it_served(warm):
    cad, _ = warm
    p = cad("warm", "status")
    assert p.returncode == 0 and "commands served" in p.stdout


def test_a_long_lived_caller_runs_commands_without_launching_a_client(warm, monkeypatch):
    # The workbench server talks to the socket itself: same output and exit
    # codes as bin/cad, with no Python process started per command.
    from cad_agent import warm as w
    cad, root = warm
    monkeypatch.setenv("CAD_WARM_DIR", cad.env["CAD_WARM_DIR"])
    code, out, err = w.run_captured(["--projects", str(root), "--json", "ls", "demo"])
    assert code == 0, err
    assert json.loads(out)["data"]["parts"] == ["block", "plate"]
    code, out, _ = w.run_captured(["--projects", str(root), "--json", "measure", "demo",
                                   "plate", "block"])
    assert code == 1 and json.loads(out)["data"]["interferes"] is True
    reply = w.ping()                            # the keep-alive the login service sends
    assert reply and reply["exit"] == 0 and reply["pid"]


def test_a_step_through_the_worker_is_the_step_a_busy_process_makes(warm, monkeypatch):
    # A fork starts from a parent that has exported nothing; this process has exported plenty.
    # Neither the clock nor OCCT's occurrence counter may tell them apart (see test_export.py).
    from cad_agent import export as ex
    from cad_agent import state as st
    from test_export import PLACED
    cad, root = warm
    part = root / "demo" / "parts" / "placed.py"
    step = root / "demo" / "out" / "placed.step"
    part.write_text(PLACED)
    try:
        assert cad("export", "demo", "placed").returncode == 0
        first = step.read_bytes()
        assert cad("export", "demo", "placed").returncode == 0
        assert step.read_bytes() == first
        monkeypatch.setattr(st, "ROOT", root)
        for _ in range(3):
            ex.export_part("demo", "placed")
        assert step.read_bytes() == first
    finally:
        part.unlink()


def test_a_render_through_the_worker_is_the_render_a_cold_run_makes(warm, monkeypatch):
    # The worker changes speed and nothing else, pictures included. On a Mac this
    # also holds the worker to Metal: a fork cannot compile shaders (nor, on a fresh
    # install, find them cached), so its sidecar must be the one that drew.
    from cad_agent import cli
    from cad_agent import state as st
    from cad_agent.render import backend_status
    cad, root = warm
    monkeypatch.setattr(st, "ROOT", st.ROOT)          # cli.main moves it to the scratch root
    png = root / "demo" / "out" / "plate_iso.png"
    assert cli.main(["--projects", str(root), "render", "demo", "plate"]) == 0
    cold = png.read_bytes()
    png.unlink()
    p = cad("render", "demo", "plate")
    assert p.returncode == 0, p.stderr
    assert png.read_bytes() == cold
    if backend_status().startswith("metal"):
        status = cad("warm", "status").stdout
        drawn = re.search(r"metal sidecar \d+ on .+, (\d+) draws served", status)
        assert drawn and int(drawn.group(1)) >= 1, status


# ─── The environment a fork sees ─────────────────────────────────────────────

# Read by the client, or set by the worker, so a fork never takes them from its client.
NOT_FORWARDED = {"CAD_WARM", "CAD_WARM_DIR", "CAD_WARM_CHILD", "CAD_EVALS"}


def test_every_variable_a_command_reads_reaches_its_fork():
    # A variable missing from ENV_PASS is read from the environment of whoever started the worker:
    # `CAD_MACRO_DIR=x cad macro save` wrote to the folder of the first client.
    read = set()
    for f in (REPO / "cad_agent").glob("*.py"):
        read |= set(re.findall(r'environ(?:\.get|\.pop|\.setdefault)?[(\[]\s*"(CAD_[A-Z_]+)"', f.read_text()))
    assert read - NOT_FORWARDED <= set(warm_module.ENV_PASS), read - NOT_FORWARDED - set(warm_module.ENV_PASS)


def test_a_forks_macro_folder_is_its_clients_not_the_workers(warm, tmp_path):
    cad, _ = warm
    mine = tmp_path / "mine"
    p = subprocess.run([str(REPO / "bin" / "cad"), "macro", "save", "m1", "-"], input="ls\n",
                       capture_output=True, text=True, env=dict(cad.env, CAD_MACRO_DIR=str(mine)), timeout=120)
    assert p.returncode == 0, p.stderr
    assert (mine / "m1.cad").exists()
    assert not (Path(cad.env["CAD_MACRO_DIR"]) / "m1.cad").exists()


# ─── The lock and the log ────────────────────────────────────────────────────

def test_a_second_worker_cannot_take_the_lock_and_a_removed_one_can_be_retaken(tmp_path):
    path = tmp_path / "warm-x.lock"
    first = warm_module._take_lock(path)
    assert first is not None and warm_module._take_lock(path) is None
    assert warm_module._lock_is_free(tmp_path / "warm-x.sock") is False
    path.unlink()                                   # what a worker on its way out does
    first.close()
    assert warm_module._lock_is_free(tmp_path / "warm-x.sock") is True
    again = warm_module._take_lock(path)
    assert again is not None
    again.close()


def test_a_clean_exit_removes_the_lock_and_a_log_with_nothing_to_say(tmp_path):
    sock = tmp_path / "warm-x.sock"
    lock = warm_module._take_lock(sock.with_suffix(".lock"))
    sock.with_suffix(".log").write_text("warm worker 1 ready in 5.0 s at x\n"
                                        "warm worker 1: warm.py changed on disk, restarting\n")
    warm_module._retire(sock, lock)
    assert list(tmp_path.iterdir()) == []


def test_a_clean_exit_keeps_a_log_that_has_a_complaint(tmp_path):
    sock = tmp_path / "warm-x.sock"
    lock = warm_module._take_lock(sock.with_suffix(".lock"))
    sock.with_suffix(".log").write_text("warm worker 1 ready in 5.0 s at x\n"
                                        "metal sidecar: shader would not compile\n")
    warm_module._retire(sock, lock)
    assert [p.name for p in tmp_path.iterdir()] == ["warm-x.log"]


def test_a_stopped_worker_leaves_no_lock_and_no_log_behind(warm):
    # Last in the module: it stops the worker the others share. Every test run, and every day
    # of use, starts a worker per scratch folder or checkout; their files piled up in /tmp.
    cad, _ = warm
    sock = Path(re.search(r"socket (\S+)", cad("warm", "status").stdout).group(1))
    assert cad("warm", "stop").returncode == 0
    deadline = time.monotonic() + 15
    while list(sock.parent.glob(f"{sock.stem}.*")) and time.monotonic() < deadline:
        time.sleep(0.2)                             # the sidecar is given a moment to leave
    assert list(sock.parent.glob(f"{sock.stem}.*")) == []


def test_warm_help_is_help_not_an_error(tmp_path):
    env = cad_env(CAD_WARM_DIR=str(tmp_path / "none"))
    p = subprocess.run([str(REPO / "bin" / "cad"), "warm", "--help"], capture_output=True, text=True,
                       env=env, timeout=60)
    assert p.returncode == 0 and "stop" in p.stdout and not p.stderr


def test_a_closed_stdout_or_stderr_is_not_a_crash(warm):
    # `cad ls >&-` left Python without a sys.stdout, and the worker was handed a descriptor that
    # was not open: the client died in its own flush. A cold run writes to nowhere and succeeds.
    cad, _ = warm
    for redirect in (">&-", "2>&-", "<&-"):
        p = subprocess.run(["bash", "-c", f"'{REPO / 'bin' / 'cad'}' --json ls demo {redirect}"],
                           capture_output=True, text=True, env=cad.env, timeout=120)
        assert p.returncode == 0 and "Traceback" not in p.stderr, (redirect, p.stderr)


def test_a_worker_folder_that_cannot_be_made_runs_cold_and_says_so(tmp_path):
    blocker = tmp_path / "a-file"
    blocker.write_text("")
    env = cad_env(CAD_WARM_DIR=str(blocker / "sub"), CAD_PROJECTS=str(tmp_path))
    env.pop("CAD_WARM", None)
    p = subprocess.run([str(REPO / "bin" / "cad"), "--json", "ls"], capture_output=True, text=True,
                       env=env, timeout=120)
    assert p.returncode == 0 and json.loads(p.stdout)["data"]["projects"] == []
    assert "running cold" in p.stderr and "Traceback" not in p.stderr
    q = subprocess.run([str(REPO / "bin" / "cad"), "warm", "status"], capture_output=True, text=True,
                       env=env, timeout=60)
    assert q.returncode == 4 and "CAD_WARM_DIR" in q.stderr

"""The warm worker: bin/cad through a background process that imported the
kernel once. What must hold is that it changes speed and nothing else: same
output, same exit codes, and an edit to a part is seen on the very next call.

One worker is started for the module, in a temporary CAD_WARM_DIR so it never
touches ~/.cache, and stopped at the end even if a test fails. Starting it
costs one kernel import (20-35 s on this machine).
"""
import json
import os
import re
import subprocess
import time
from pathlib import Path

import pytest

from test_cli import BLOCK, PLATE

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def warm(tmp_path_factory):
    root = tmp_path_factory.mktemp("projects")
    d = root / "demo" / "parts"
    d.mkdir(parents=True)
    (d / "plate.py").write_text(PLATE)
    (d / "block.py").write_text(BLOCK)
    env = dict(os.environ, CAD_PROJECTS=str(root),
               CAD_WARM_DIR=str(tmp_path_factory.mktemp("warm")))
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

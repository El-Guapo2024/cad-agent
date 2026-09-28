"""The warm worker: bin/cad through a background process that imported the
kernel once. What must hold is that it changes speed and nothing else: same
output, same exit codes, and an edit to a part is seen on the very next call.

One worker is started for the module, in a temporary CAD_WARM_DIR so it never
touches ~/.cache, and stopped at the end even if a test fails. Starting it
costs one kernel import (20-35 s on this machine).
"""
import json
import os
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

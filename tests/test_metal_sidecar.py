"""The Metal sidecar: how a warm-worker fork gets its renders drawn on the GPU.

A fork cannot compile Metal shaders (metal_render.py says why), so the worker
execs a sidecar and the forks send it their triangles. The protocol and the
fallbacks are tested everywhere, against a stand-in for the GPU; the real
sidecar is tested on a Mac, where it must draw exactly what this process would.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from pathlib import Path

import numpy as np
import pytest
from build123d import Box, Cylinder

from cad_agent import metal_render as mr
from cad_agent.render import read_png, tessellate

REPO = Path(__file__).resolve().parent.parent
FLAT = (10, 20, 30)


@pytest.fixture
def sock_dir():
    # A socket path is capped near 100 bytes, which pytest's own temp folders exceed on a Mac.
    d = tempfile.mkdtemp(prefix="cad-", dir="/tmp")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


def flat(positions, colors, mvp, size, bg):
    return np.full((size[1], size[0], 3), FLAT, np.uint8)


@pytest.fixture
def stand_in(sock_dir, monkeypatch):
    """stand_in(draw): a sidecar loop in a thread whose "GPU" is `draw`; the env points at it."""
    live = []

    def start(draw):
        path = sock_dir / "s.metal"
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(path))
        srv.listen(4)
        srv.settimeout(0.1)
        stop = threading.Event()

        def loop():
            while not stop.is_set():
                try:
                    conn, _ = srv.accept()
                except socket.timeout:
                    continue
                except OSError:
                    return
                with conn:
                    mr.handle(conn, draw, lambda: "stand-in gpu")

        t = threading.Thread(target=loop, daemon=True)
        t.start()
        live.append((srv, stop, t))
        monkeypatch.setenv(mr.SIDECAR_ENV, str(path))
        return path

    yield start
    for srv, stop, t in live:
        stop.set()
        t.join(2)
        srv.close()


def _raw(path, header: bytes) -> dict:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(10)
    try:
        s.connect(str(path))
        s.sendall(header)
        try:
            s.shutdown(socket.SHUT_WR)       # "that is all I have", for a request promising more
        except OSError:
            pass                             # the server has answered and hung up already
        return json.loads(s.makefile("rb").readline())
    finally:
        s.close()


# ─── the protocol, against a stand-in GPU (runs on every platform) ───────────

def test_a_draw_goes_to_the_sidecar_and_its_pixels_come_back(stand_in, tmp_path):
    calls = []

    def draw(positions, colors, mvp, size, bg):
        calls.append((positions.copy(), colors.copy(), mvp.copy(), size, list(bg)))
        return flat(positions, colors, mvp, size, bg)

    stand_in(draw)
    mesh = tessellate(Box(10, 20, 30))
    png = mr.render_metal(mesh, tmp_path / "r.png", view="iso", size=(32, 24))

    (positions, colors, mvp, size, bg), = calls
    want = mr._geometry(mesh, "iso", (32, 24), (196, 122, 62), None, (70, 150, 110), 1.08)
    assert size == (32, 24) and bg == [247, 246, 244]
    for got, expected in zip((positions, colors, mvp), want):
        assert got.dtype == np.float32 and np.array_equal(got, expected)
    assert (read_png(png) == FLAT).all()
    assert mr.device_name() == "stand-in gpu"


def test_a_sidecar_that_does_not_answer_leaves_the_draw_to_this_process(
        sock_dir, tmp_path, monkeypatch):
    here = []
    monkeypatch.setattr(mr, "_draw_local", lambda *a: here.append(a[3]) or flat(*a))
    monkeypatch.setenv(mr.SIDECAR_ENV, str(sock_dir / "nobody-home.metal"))
    png = mr.render_metal(tessellate(Cylinder(5, 10)), tmp_path / "r.png", size=(16, 12))
    assert here == [(16, 12)] and (read_png(png) == FLAT).all()


def test_a_gpu_failure_in_the_sidecar_leaves_the_draw_to_this_process(
        stand_in, tmp_path, monkeypatch):
    def failing(*_):
        raise RuntimeError("Metal render failed")

    here = []
    stand_in(failing)
    monkeypatch.setattr(mr, "_draw_local", lambda *a: here.append(a[3]) or flat(*a))
    png = mr.render_metal(tessellate(Box(4, 4, 4)), tmp_path / "r.png", size=(16, 12))
    assert here == [(16, 12)] and (read_png(png) == FLAT).all()


def test_a_bad_request_gets_an_error_and_the_next_one_is_served(stand_in):
    drawn = []
    path = stand_in(lambda *a: drawn.append(a) or flat(*a))
    assert _raw(path, b"not json\n")["ok"] is False
    assert _raw(path, b'{"op": "nope"}\n')["ok"] is False
    # promises 3 vertices and sends none
    short = _raw(path, b'{"op": "draw", "size": [8, 8], "bg": [0, 0, 0], "n": 3}\n')
    assert short["ok"] is False and "cut short" in short["error"]
    huge = _raw(path, b'{"op": "draw", "size": [8, 8], "bg": [0, 0, 0], "n": 999999999}\n')
    assert huge["ok"] is False
    assert not drawn
    assert mr._ask({"op": "ping"})[0]["name"] == "stand-in gpu"


# ─── the real sidecar (a Mac with Metal) ─────────────────────────────────────

def _metal_or_skip():
    try:
        return mr.device_name()
    except Exception as e:
        pytest.skip(f"no Metal on this host: {e}")


def _start_sidecar(path):
    return subprocess.Popen([sys.executable, "-m", "cad_agent.metal_render", "_serve",
                             str(path), str(os.getpid())], cwd=REPO)


def _wait_for(path, proc):
    deadline = time.time() + 120
    while not path.exists():
        assert proc.poll() is None, "the sidecar exited before it was ready"
        assert time.time() < deadline, "the sidecar was not ready in 120 s"
        time.sleep(0.1)


def test_the_real_sidecar_draws_exactly_what_this_process_would(sock_dir, tmp_path, monkeypatch):
    _metal_or_skip()
    path = sock_dir / "s.metal"
    side = _start_sidecar(path)
    try:
        _wait_for(path, side)
        meshes = {"box": tessellate(Box(10, 20, 30)), "cylinder": tessellate(Cylinder(12, 30))}
        for name, mesh in meshes.items():
            for view in ("iso", "top", "front"):
                monkeypatch.delenv(mr.SIDECAR_ENV, raising=False)
                here = mr.render_metal(mesh, tmp_path / f"{name}-{view}-here.png", view=view,
                                       size=(120, 90)).read_bytes()
                monkeypatch.setenv(mr.SIDECAR_ENV, str(path))
                there = mr.render_metal(mesh, tmp_path / f"{name}-{view}-there.png", view=view,
                                        size=(120, 90)).read_bytes()
                assert here == there, f"{name} {view}: the sidecar drew something else"
        ping = mr._ask({"op": "ping"})[0]
        assert ping["pid"] == side.pid and ping["served"] >= 6
        assert mr.device_name() == ping["name"]
    finally:
        side.terminate()
        side.wait(10)
    assert not path.exists(), "the sidecar leaves its socket behind"


PARENT = textwrap.dedent("""
    import os, subprocess, sys, time
    sock = sys.argv[1]
    side = subprocess.Popen([sys.executable, "-m", "cad_agent.metal_render", "_serve", sock,
                             str(os.getpid())])
    print(side.pid, flush=True)
    for _ in range(1200):                   # leave only once the sidecar is serving
        if os.path.exists(sock):
            break
        time.sleep(0.1)
""")


def test_the_sidecar_goes_when_its_parent_does(sock_dir):
    _metal_or_skip()
    path = sock_dir / "s.metal"
    parent = subprocess.Popen([sys.executable, "-c", PARENT, str(path)], cwd=REPO,
                              stdout=subprocess.PIPE, text=True)
    side = int(parent.stdout.readline())
    parent.wait(120)
    deadline = time.time() + 15
    try:
        while time.time() < deadline:
            os.kill(side, 0)                # raises once it has gone
            time.sleep(0.2)
        pytest.fail("the sidecar outlived its parent")
    except ProcessLookupError:
        pass
    finally:
        try:
            os.kill(side, 15)
        except ProcessLookupError:
            pass
    assert not path.exists()

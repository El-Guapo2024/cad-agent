"""The workbench: placements.toml, `cad place`, `cad scene` and `cad serve`.

A part moved by hand is a design input like any other: every gate sees it,
the verifier hashes it, and a bad file fails closed. The server is a client
of the CLI, so it is tested through the same commands, run in process.
"""
import contextlib
import io
import json
import math
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import numpy as np
import pytest

from cad_agent import cli, placements, serve
from cad_agent import state as st
from cad_agent.verify import source_hash
from test_cli import ASSEMBLY, BLOCK, PLATE, run


@pytest.fixture()
def demo(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(st, "ROOT", tmp_path)
    monkeypatch.delenv("CAD_PROJECTS", raising=False)
    monkeypatch.setenv("CAD_WARM_DIR", str(tmp_path / ".warm"))
    assert cli.main(["init", "demo", "--brief", "workbench test"]) == cli.OK
    capsys.readouterr()
    d = tmp_path / "demo"
    (d / "parts" / "plate.py").write_text(PLATE)
    (d / "parts" / "block.py").write_text(BLOCK)
    (d / "assembly.py").write_text(ASSEMBLY)
    return d


# ─── placements.toml ─────────────────────────────────────────────────────────

def _rx(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def _ry(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def _rz(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def test_a_placement_is_rx_ry_rz_about_the_pivot_then_the_move():
    p = {"move": (5.0, -2.0, 7.0), "turn": (30.0, 45.0, 60.0), "about": (10.0, 20.0, 30.0)}
    r = _rx(math.radians(30)) @ _ry(math.radians(45)) @ _rz(math.radians(60))
    x = np.array([13.0, -4.0, 2.5])
    want = r @ (x - p["about"]) + p["about"] + p["move"]
    m = np.array(placements.matrix(p))
    assert np.allclose(m[:, :3] @ x + m[:, 3], want)
    # and the kernel applies the same matrix (a Vertex caches its coordinates,
    # so follow the centre of a small box instead)
    from build123d import Box, Pos
    c = placements.apply({"b": Pos(*x) * Box(1, 1, 1)}, {"b": p})["b"].center()
    assert np.allclose([c.X, c.Y, c.Z], want, atol=1e-7)


def test_bad_placements_fail_closed(demo):
    (demo / "placements.toml").write_text("[block]\nmove = [0, 0]\n")
    with pytest.raises(placements.PlacementError, match="three numbers"):
        placements.load(demo)
    (demo / "placements.toml").write_text("[block]\nshift = [0, 0, 1]\n")
    with pytest.raises(placements.PlacementError, match="unknown key shift"):
        placements.load(demo)
    (demo / "placements.toml").write_text("[block\n")
    with pytest.raises(placements.PlacementError, match="does not parse"):
        placements.load(demo)


def test_a_broken_placements_file_fails_the_check_instead_of_crashing(demo, capsys):
    (demo / "placements.toml").write_text("[block]\nshift = [0, 0, 1]\n")
    code, data = run(capsys, "check", "demo")
    assert code == cli.FAIL and "unknown key shift" in data["error"]


# ─── cad place ───────────────────────────────────────────────────────────────

def test_place_moves_a_body_and_every_gate_sees_it(demo, capsys):
    # The block's bottom sits at z = 15 and the plate's top at z = 2: down 18 buries it.
    code, data = run(capsys, "place", "demo", "block", "--move=0,0,-18")
    assert code == cli.FAIL and data["fails"] == 1
    assert data["rows"][0]["check"] == "interference"
    saved = placements.load(demo)["block"]
    assert saved["move"] == (0.0, 0.0, -18.0) and saved["about"] == (0.0, 0.0, 20.0)

    code, data = run(capsys, "measure", "demo", "block", "plate", "--posed")
    assert code == cli.FAIL and data["interferes"]
    code, data = run(capsys, "check", "demo", "--all")
    moved = [r for r in data["rows"] if r["check"] == "placements" and r["subject"] == "block"]
    assert moved and moved[0]["state"] == "PASS" and "-18.0" in moved[0]["measured"]
    assert any(r["check"] == "fit" and r["state"] == "FAIL" for r in data["rows"])

    # --by nudges from where it is; back above the plate it is clear again
    code, data = run(capsys, "place", "demo", "block", "--by=0,0,10")
    assert code == cli.OK and placements.load(demo)["block"]["move"] == (0.0, 0.0, -8.0)
    code, data = run(capsys, "measure", "demo", "block", "plate", "--posed")
    assert code == cli.OK and data["min_distance_mm"] == pytest.approx(5.0)
    assert len(data["points"]) == 2

    code, data = run(capsys, "place", "demo", "block", "--reset")
    assert code == cli.OK and data["placement"] is None
    assert not (demo / "placements.toml").exists()


def test_place_rejects_what_it_cannot_do(demo, capsys):
    assert run(capsys, "place", "demo", "nope", "--by=1,0,0")[0] == cli.USAGE
    assert run(capsys, "place", "demo", "block")[0] == cli.USAGE             # no move given
    assert run(capsys, "place", "demo", "block", "--move=1,2")[0] == cli.USAGE
    assert run(capsys, "place", "demo", "block", "--reset", "--by=1,0,0")[0] == cli.USAGE


def test_moving_back_to_zero_removes_the_entry(demo, capsys):
    run(capsys, "place", "demo", "block", "--move=3,0,0")
    run(capsys, "place", "demo", "block", "--move=0,0,0")
    assert "block" not in placements.load(demo)


def test_placements_are_hashed_and_unknown_bodies_are_unchecked(demo, capsys):
    before, n = source_hash(demo)
    run(capsys, "place", "demo", "block", "--move=0,0,5")
    after, m = source_hash(demo)
    assert after != before and m == n + 1
    text = (demo / "placements.toml").read_text()
    (demo / "placements.toml").write_text(text + "\n[ghost]\nmove = [1.0, 0.0, 0.0]\n")
    code, data = run(capsys, "check", "demo")
    ghost = [r for r in data["rows"] if r["subject"] == "ghost"]
    assert ghost and ghost[0]["state"] == "UNCHECKED"


# ─── cad scene ───────────────────────────────────────────────────────────────

def test_scene_is_three_cad_viewer_data_plus_what_the_panels_need(demo, capsys):
    import base64
    code, data = run(capsys, "scene", "demo")
    assert code == cli.OK and sorted(data["bodies"]) == ["block", "plate"] and data["triangles"] > 0
    scene = json.loads((demo / "out" / "scene.json").read_text())
    assert scene["format"] == "cad-scene/3" and scene["assembly"] is True
    shapes = scene["viewer"]["shapes"]
    assert sorted(p["id"] for p in shapes["parts"]) == ["/Group/block", "/Group/plate"]
    inst = scene["viewer"]["instances"][0]
    assert inst["vertices"]["codec"] == "b64" and inst["vertices"]["dtype"] == "float32"
    assert len(base64.b64decode(inst["triangles"]["buffer"])) == 4 * inst["triangles"]["shape"][0]
    plate = next(b for b in scene["bodies"] if b["name"] == "plate")
    assert plate["path"] == "/Group/plate" and plate["kind"] == "made" and plate["material"] == "petg"
    assert plate["placement"] is None and plate["about"] == plate["center"]

    # a hand move is drawn where the gates see it, and carried so a drag can build on it
    run(capsys, "place", "demo", "block", "--move=10,0,0")
    run(capsys, "scene", "demo")
    scene = json.loads((demo / "out" / "scene.json").read_text())
    block = next(b for b in scene["bodies"] if b["name"] == "block")
    assert block["placement"]["move"] == [10.0, 0.0, 0.0] and block["about"] == [0.0, 0.0, 20.0]
    assert scene["bbox"][1][0] == pytest.approx(20.0)     # plate 40 wide; block shifted to 15
    assert block["bbox"][1][0] == pytest.approx(15.0)


def test_scene_tessellates_each_body_with_its_own_deviation_and_angular_deflection(demo, capsys):
    """FreeCAD's own defaults (ViewProviderPartExt::loadParameter: 0.2 / 28.65 deg) apply until a
    body's out/gui.json view_props says otherwise, and then only that body is affected: plate has
    two cylindrical clearance holes (curved faces), so its mesh gets coarser/finer; block is a
    plain cube, so neither Deviation nor AngularDeflection can change its triangle count."""
    from cad_agent import gui

    def tri_count(sc, name):
        part = next(p for p in sc["viewer"]["shapes"]["parts"] if p["id"] == f"/Group/{name}")
        return sc["viewer"]["instances"][part["shape"]["ref"]]["triangles"]["shape"][0] // 3

    run(capsys, "scene", "demo")
    base = json.loads((demo / "out" / "scene.json").read_text())
    plate_default, block_default = tri_count(base, "plate"), tri_count(base, "block")
    assert plate_default > 0 and block_default > 0

    gui.save_persisted(demo, [], {"plate": {"angularDeflection": 180.0}}, [])   # coarsest allowed
    run(capsys, "scene", "demo")
    coarse = json.loads((demo / "out" / "scene.json").read_text())
    assert tri_count(coarse, "plate") < plate_default
    assert tri_count(coarse, "block") == block_default    # untouched: no view_props, no curves either

    gui.save_persisted(demo, [], {"plate": {"angularDeflection": 1.0}}, [])     # finest allowed
    run(capsys, "scene", "demo")
    fine = json.loads((demo / "out" / "scene.json").read_text())
    assert tri_count(fine, "plate") > plate_default

    # a forced global --tolerance overrides every body's own Deviation alike (AngularDeflection
    # is back to unset here, so this isolates the Deviation axis against the first run above)
    gui.save_persisted(demo, [], {}, [])
    code, data = run(capsys, "scene", "demo", "--tolerance", "50")
    assert code == cli.OK
    forced = json.loads((demo / "out" / "scene.json").read_text())
    assert tri_count(forced, "plate") < plate_default     # 50 is far coarser than the 0.2 default


# ─── cad serve ───────────────────────────────────────────────────────────────

def inproc(root, args):
    """The server's runner, in this process: the same argv and the same JSON."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = cli.main(["--projects", str(root), "--json", *args])
    lines = [ln for ln in buf.getvalue().splitlines() if ln.startswith("{")]
    return {"exit": code, "data": json.loads(lines[-1])["data"] if lines else {}, "stderr": ""}


def serving(bench, monkeypatch):
    """A bench behind a real server on a free port: (call, scheduled, stop). `call(path, body)` is a GET, or a
    JSON POST with the X-CAD header (header=False leaves it off); `raw=` posts those bytes instead (an upload);
    full=True also returns the response headers."""
    scheduled = []
    monkeypatch.setattr(bench, "schedule", lambda slug, kind="check": scheduled.append((slug, kind)))
    srv = serve.make_server(bench, "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def call(path, body=None, header=True, raw=None, full=False):
        req = urllib.request.Request(base + path)
        if raw is not None or body is not None:
            req.data = raw if raw is not None else json.dumps(body).encode()
            req.add_header("Content-Type", "application/octet-stream" if raw is not None else "application/json")
            if header:
                req.add_header("X-CAD", "1")
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return (r.status, r.read(), r.headers) if full else (r.status, r.read())
        except urllib.error.HTTPError as e:
            return (e.code, e.read(), e.headers) if full else (e.code, e.read())

    def stop():
        srv.shutdown()
        srv.server_close()
        bench.clear_uploads()
    call.base = base
    return call, scheduled, stop


@pytest.fixture()
def server(demo, monkeypatch):
    bench = serve.Bench([demo.parent], runner=inproc)
    call, scheduled, stop = serving(bench, monkeypatch)
    yield call, bench, scheduled
    stop()


def test_the_server_lists_builds_and_places_through_the_cli(server, demo):
    call, bench, scheduled = server
    code, body = call("/")
    assert code == 200 and b"workbench" in body
    code, body = call("/api/projects")
    assert code == 200 and [p["slug"] for p in json.loads(body)["projects"]] == ["demo"]
    code, body = call("/api/scene?slug=demo")
    assert code == 200 and {b["name"] for b in json.loads(body)["bodies"]} == {"block", "plate"}

    code, body = call("/api/place", {"slug": "demo", "body": "block", "move": [0, 0, -18],
                                     "turn": [0, 0, 0], "about": [0, 0, 20]})
    r = json.loads(body)
    assert code == 200 and r["exit"] == cli.FAIL and r["data"]["fails"] == 1
    assert placements.load(demo)["block"]["move"] == (0.0, 0.0, -18.0)
    assert scheduled == [("demo", "check")]            # a full check follows every move
    log = (demo / ".cad" / "log.jsonl").read_text()
    assert '"cmd": "place"' in log                     # the page's moves are in the activity log

    # the scene is rebuilt because placements.toml is a design input
    code, body = call("/api/scene?slug=demo")
    block = next(b for b in json.loads(body)["bodies"] if b["name"] == "block")
    assert block["placement"]["move"] == [0.0, 0.0, -18.0]


def test_the_server_refuses_what_a_foreign_page_could_ask(server, demo):
    call, _, _ = server
    code, _ = call("/api/place", {"slug": "demo", "body": "block", "reset": True}, header=False)
    assert code == 403
    code, _ = call("/api/file?slug=demo&path=assembly.py")
    assert code == 404
    code, _ = call("/api/file?slug=demo&path=../../etc/passwd")
    assert code == 404
    code, _ = call("/api/scene?slug=nope")
    assert code == 404
    code, _ = call("/../cad_agent/serve.py")
    assert code == 404


def test_the_server_says_which_project_is_unknown_or_missing(server):
    # /api/status answered 200 for a project that does not exist, a request without a slug said
    # "no project None", and a POST named the project as "missing or unknown 'nope'".
    call, _, _ = server
    for path, body in (("/api/status?slug=nope", None), ("/api/check", {"slug": "nope"})):
        code, raw = call(path, body)
        assert code == 404 and json.loads(raw)["error"] == "no project 'nope'", path
    for path, body in (("/api/status", None), ("/api/scene", None), ("/api/check", {})):
        code, raw = call(path, body)
        assert code == 400 and "slug" in json.loads(raw)["error"], path


def test_a_verdict_is_not_an_error_but_a_usage_mistake_or_a_crash_says_why():
    # `cad place` of a part into another exits 1 and `cad verify` of an unfinished design exits 2: both are
    # answers, with their rows. The server used to add error="cad failed" to them, and the page showed that
    # as the whole message ("wheel_left was placed, but a fit check fails: cad failed").
    hit = '{"cmd": "place", "exit": 1, "data": {"fails": 1, "rows": [{"pair": "a vs b", "state": "FAIL"}]}}'
    r = serve._result(cli.FAIL, hit, "")
    assert r["exit"] == cli.FAIL and "error" not in r["data"] and r["data"]["rows"][0]["pair"] == "a vs b"
    r = serve._result(cli.UNCHECKED, '{"cmd": "verify", "exit": 2, "data": {"verdict": "UNCHECKED"}, "text": "demo  UNCHECKED"}', "")
    assert "error" not in r["data"] and r["text"] == "demo  UNCHECKED"
    # what went wrong, when nothing was verdict: the command's own message, else its stderr, else a stand-in
    r = serve._result(cli.FAIL, '{"cmd": "scene", "exit": 1, "data": {"error": "demo did not build"}}', "")
    assert r["data"]["error"] == "demo did not build"
    r = serve._result(cli.USAGE, '{"cmd": "place", "exit": 3, "data": {}}', "cad place: no body 'x'\n")
    assert r["data"]["error"] == "cad place: no body 'x'"
    r = serve._result(cli.CRASH, "", "")
    assert r["exit"] == cli.CRASH and r["data"]["error"] == "cad failed"
    r = serve._result(-9, "", "")                        # a process killed from outside
    assert r["data"]["error"] == "cad failed"
    assert "error" not in serve._result(cli.OK, '{"cmd": "status", "exit": 0, "data": {}}', "")["data"]


def test_the_watcher_announces_design_changes_and_new_log_lines(demo):
    bench = serve.Bench([demo.parent], runner=inproc)
    got = []
    bench.broadcast = got.append
    bench.scan(announce=False)
    (demo / "parts" / "block.py").write_text(BLOCK.replace("10.0", "12.0"))
    (demo / ".cad").mkdir(exist_ok=True)
    with (demo / ".cad" / "log.jsonl").open("a") as f:
        f.write(json.dumps({"cmd": "check", "exit": 0}) + "\n")
    bench.scan()
    kinds = {e["type"] for e in got}
    assert "design" in kinds and "log" in kinds
    assert next(e for e in got if e["type"] == "log")["entries"][-1]["cmd"] == "check"


def test_the_watcher_announces_a_project_made_outside_the_workbench(tmp_path):
    # The first design usually comes from the agent's `cad init`, not File > New: a page
    # showing "No projects yet" has to hear about it, once, and about one removed too.
    bench = serve.Bench([tmp_path], runner=inproc)
    got = []
    bench.broadcast = got.append
    bench.scan(announce=False)
    bench.scan()
    assert got == []
    (tmp_path / "first" / "parts").mkdir(parents=True)
    bench.scan()
    bench.scan()
    assert got == [{"type": "projects"}]
    (tmp_path / "first" / "parts").rmdir()
    bench.scan()
    assert got == [{"type": "projects"}] * 2


def test_rescene_debounced_coalesces_rapid_calls_into_one_scene_and_one_broadcast(demo):
    """A slider drag fires many Deviation/AngularDeflection changes a second; `rescene_debounced`
    should fold them into a single `cad scene` run (and a single broadcast) after a quiet period,
    the same way `schedule()` folds overlapping check/verify runs."""
    bench = serve.Bench([demo.parent], runner=inproc)
    calls, broadcasts = [], []
    bench.cad = lambda slug, what, args: calls.append((what, args)) or {"exit": 0, "data": {}, "stderr": ""}
    bench.broadcast = broadcasts.append

    for _ in range(5):                       # five rapid-fire changes, as a drag would send
        bench.rescene_debounced("demo", delay=0.05)
    time.sleep(0.2)

    assert calls == [("scene", ["scene", "demo"])]
    assert broadcasts == [{"type": "scene", "slug": "demo"}]

    # a later change starts a fresh debounce window
    bench.rescene_debounced("demo", delay=0.05)
    time.sleep(0.2)
    assert calls == [("scene", ["scene", "demo"])] * 2
    assert broadcasts == [{"type": "scene", "slug": "demo"}] * 2


def test_rescene_debounced_does_not_broadcast_when_the_rebuild_fails(demo):
    bench = serve.Bench([demo.parent], runner=inproc)
    broadcasts = []
    bench.cad = lambda slug, what, args: {"exit": 1, "data": {"error": "nope"}, "stderr": ""}
    bench.broadcast = broadcasts.append
    bench.rescene_debounced("demo", delay=0.02)
    time.sleep(0.15)
    assert broadcasts == []


def test_serve_takes_the_port_the_app_assigns(demo, monkeypatch, capsys):
    monkeypatch.setenv("CAD_RUNTIME_DIR", str(demo.parent / "runtime"))   # not the machine's registry
    got = {}
    monkeypatch.setattr(serve, "run", lambda roots, host, port, **kw: got.update(port=port, **kw))
    monkeypatch.setenv("PORT", "9123")
    assert cli.main(["serve"]) == cli.OK and got["port"] == 9123
    assert cli.main(["serve", "--port", "8800"]) == cli.OK and got["port"] == 8800
    monkeypatch.setenv("PORT", "eighty")
    assert cli.main(["serve"]) == cli.USAGE
    monkeypatch.delenv("PORT")
    assert cli.main(["serve"]) == cli.OK and got["port"] == 8733


def test_serve_reuses_a_workbench_on_these_folders_else_takes_a_free_port(demo, monkeypatch):
    from cad_agent import gui_client
    monkeypatch.setenv("CAD_RUNTIME_DIR", str(demo.parent / "runtime"))
    monkeypatch.delenv("PORT", raising=False)
    tried = []

    def run(roots, host, port, **kw):
        tried.append(port)
        if port < 8735:
            raise RuntimeError(f"port {port} is busy")
    monkeypatch.setattr(serve, "run", run)
    # 8733 and 8734 serve other folders (a login service on the real projects, say): next free port
    other = [{"url": "http://127.0.0.1:8733", "roots": [str(demo.parent / "elsewhere")]}]
    monkeypatch.setattr(gui_client, "_candidates", lambda: other)
    assert cli.main(["serve"]) == cli.OK and tried == [8733, 8734, 8735]
    # a port asked for doesn't move
    tried.clear()
    assert cli.main(["serve", "--port", "8733"]) == cli.USAGE and tried == [8733]
    # one already serving these folders is the answer, and nothing new starts
    tried.clear()
    mine = [{"url": "http://127.0.0.1:8740", "roots": [str(st.ROOT)]}]
    monkeypatch.setattr(gui_client, "_candidates", lambda: mine)
    assert cli.main(["--json", "serve"]) == cli.OK and tried == []


def test_serve_watches_the_projects_folder_before_there_are_designs(tmp_path, monkeypatch):
    # The plugin points CAD_PROJECTS at <project>/cad-projects, which doesn't exist until the
    # first design: the workbench still has to watch it, so that design shows up live.
    monkeypatch.setattr(st, "ROOT", tmp_path / "cad-projects")
    monkeypatch.delenv("CAD_PROJECTS", raising=False)    # a plugin session sets it; it would win over ROOT
    got = {}
    monkeypatch.setattr(serve, "run", lambda roots, host, port, **kw: got.update(roots=roots))
    assert cli.main(["serve", "--port", "8800"]) == cli.OK
    assert (tmp_path / "cad-projects").is_dir() and got["roots"][0] == tmp_path / "cad-projects"


def test_the_login_service_keeps_the_kernel_warm_and_restarts_after_a_crash(tmp_path):
    from cad_agent import service
    job = service.definition([tmp_path], port=8799)
    args = job["ProgramArguments"]
    assert args[1:5] == ["-m", "cad_agent.warm", "serve", "--keep-warm"]
    assert args[5:] == ["--port", "8799", str(tmp_path)]
    assert job["RunAtLoad"] is True and job["KeepAlive"] == {"SuccessfulExit": False}
    assert job["Label"] == service.LABEL and job["StandardErrorPath"].endswith("workbench.log")


def test_page_writes_a_snapshot_that_needs_no_server(demo, capsys):
    run(capsys, "check", "demo")
    code, data = run(capsys, "page", "demo")
    assert code == cli.OK and data["title"] == "Demo"
    out = demo / "out" / "page"
    for name in ("index.html", "page.js", "three-cad-viewer.css", "three-cad-viewer.esm.min.js",
                 "scene.json", "data.json"):
        assert (out / name).is_file(), name
    page = json.loads((out / "data.json").read_text())
    assert page["rows"] and all("artifacts" not in r for r in page["rows"])
    assert page["status"]["verdict"] is None and page["status"]["done"] is False
    assert any(r["current"] for r in page["renders"])
    html = (out / "index.html").read_text()
    assert "<title>Demo</title>" in html and "<html" not in html     # the host adds the shell
    assert 'src="page.js"' in html
    js = (out / "page.js").read_text()
    assert "fetch('data.json')" in js and "fetch('scene.json')" in js


def test_bodies_are_matched_to_their_part_without_guessing():
    from cad_agent.scene import _part_for
    cell, plate = ["gantry_end", "syringe_clamp", "x_carriage"], ["hot_plate", "plate_standoff"]
    assert _part_for("gantry_end_left", cell) == "gantry_end"
    assert _part_for("gantry_beam", cell) is None             # an extrusion, not a gantry_end
    assert _part_for("rail_left", cell) is None
    assert _part_for("standoff_fl", plate) == "plate_standoff"
    assert _part_for("floor_rail_front", plate) is None
    assert _part_for("bracket_2", ["bracket"]) == "bracket"


def test_effective_tessellation_falls_back_to_freecads_own_defaults():
    import math
    from cad_agent.scene import _effective_tessellation
    # unset: FreeCAD's ViewProviderPartExt::loadParameter() defaults (0.2%, 28.65 deg ~ 0.5 rad)
    dev, ang = _effective_tessellation({}, "block", None, None)
    assert dev == pytest.approx(0.2) and ang == pytest.approx(math.radians(28.65))
    # a body's own view_props wins over the default, one axis at a time
    dev, ang = _effective_tessellation({"block": {"deviation": 0.5}}, "block", None, None)
    assert dev == pytest.approx(0.5) and ang == pytest.approx(math.radians(28.65))
    dev, ang = _effective_tessellation({"block": {"angularDeflection": 90.0}}, "block", None, None)
    assert dev == pytest.approx(0.2) and ang == pytest.approx(math.radians(90.0))
    # another body's view_props never leaks in
    dev, ang = _effective_tessellation({"plate": {"deviation": 50.0}}, "block", None, None)
    assert dev == pytest.approx(0.2)
    # an explicit override forces every body alike, regardless of its own view_props
    dev, ang = _effective_tessellation({"block": {"deviation": 0.5}}, "block", 0.3, 0.1)
    assert dev == pytest.approx(0.3) and ang == pytest.approx(0.1)


# ─── cad set: dimensions edited from the page ────────────────────────────────

PART_WITH_NOTES = '''"""A part whose PARAMS carry comments and a computed value."""
PARAMS = {
    "width": 40.0,        # across the flats — keep ≥ 30 mm
    "depth": -5.0,
    "count": 2,
    "screw": "M3",        # ISO 273 medium
    "rounded": True,
    "half": 40.0 / 2,     # computed: not editable
}
'''


def test_params_are_read_and_rewritten_in_place(tmp_path):
    from cad_agent import params as pm
    f = tmp_path / "p.py"
    f.write_text(PART_WITH_NOTES)
    got = pm.read(f)
    assert [got[k]["value"] for k in ("width", "depth", "count", "screw", "rounded")] == [40.0, -5.0, 2, "M3", True]
    assert got["half"]["editable"] is False and got["width"]["editable"] is True
    pm.write(f, {"width": 55.5, "depth": -7.0, "screw": "M4", "rounded": False})
    text = f.read_text()
    # only the literals changed: comments (with non-ASCII in them) and layout stay
    assert '"width": 55.5,        # across the flats — keep ≥ 30 mm' in text
    assert '"depth": -7.0,' in text and '"screw": "M4",        # ISO 273 medium' in text
    assert '"rounded": False,' in text and '"half": 40.0 / 2,' in text
    assert text.count("\n") == PART_WITH_NOTES.count("\n")
    assert pm.coerce("count", 2, 3.0) == 3 and pm.coerce("width", 1.0, 8) == 8.0
    with pytest.raises(pm.ParamError):
        pm.coerce("count", 2, 2.5)
    with pytest.raises(pm.ParamError):
        pm.write(f, {"nope": 1.0})


def test_set_writes_the_value_only_when_the_part_still_builds(demo, capsys):
    plate = demo / "parts" / "plate.py"
    code, data = run(capsys, "set", "demo", "plate", "thickness=6")
    assert code in (cli.OK, cli.UNCHECKED) and data["changed"] == {"thickness": [4.0, 6.0]}
    assert '"thickness": 6.0' in plate.read_text() and data["bbox_mm"][2] == 6.0
    assert data["mass_g"] > 0
    before = plate.read_text()
    code, data = run(capsys, "set", "demo", "plate", "screw=M99")      # no such hole size
    assert code == cli.FAIL and plate.read_text() == before              # not written
    assert run(capsys, "set", "demo", "plate", "nope=1")[0] == cli.USAGE
    assert run(capsys, "set", "demo", "plate", "thickness=thick")[0] == cli.USAGE


def test_the_page_edits_a_parameter_through_cad_set(server, demo):
    call, _, scheduled = server
    code, body = call("/api/set", {"slug": "demo", "part": "block", "values": {"size": 12}})
    r = json.loads(body)
    assert code == 200 and r["data"]["changed"] == {"size": [10.0, 12.0]}
    assert '"size": 12.0' in (demo / "parts" / "block.py").read_text()
    assert ("demo", "check") in scheduled
    code, body = call("/api/scene?slug=demo")
    block = next(b for b in json.loads(body)["bodies"] if b["name"] == "block")
    assert block["params"]["size"] == {"value": 12.0, "type": "float", "editable": True}


def test_the_server_hosts_the_react_ui_at_next(server, tmp_path, monkeypatch):
    call, _, _ = server
    (tmp_path / "next").mkdir()
    (tmp_path / "next" / "index.html").write_text("<p>react ui</p>")
    monkeypatch.setattr(serve, "STATIC", tmp_path.resolve())
    assert call("/next/") == (200, b"<p>react ui</p>")
    # /next redirects to /next/, which the build's relative asset paths need
    assert call("/next") == (200, b"<p>react ui</p>")


def test_export_downloads_a_step_file(server):
    call, _, _ = server
    code, body = call("/api/export", {"slug": "demo", "part": "block", "format": "step"})
    data = json.loads(body)["data"]
    assert code == 200 and data["path"].endswith(".step")
    code, body = call("/api/file?" + urllib.parse.urlencode({"slug": "demo", "path": data["path"]}))
    assert code == 200 and body.startswith(b"ISO-10303-21")
    code, _ = call("/api/export", {"slug": "demo", "part": "block", "format": "obj"})
    assert code == 400


def test_export_offers_every_format_the_cli_writes(server):
    """File > Export lists 3MF and DXF too, so the server takes every format `cad export` writes."""
    call, _, _ = server
    code, body = call("/api/export", {"slug": "demo", "part": "block", "format": "3mf"})
    data = json.loads(body)["data"]
    assert code == 200 and data["path"].endswith(".3mf")
    code, body = call("/api/file?" + urllib.parse.urlencode({"slug": "demo", "path": data["path"]}))
    assert code == 200 and body.startswith(b"PK")                  # a 3MF is a zip
    code, body = call("/api/export", {"slug": "demo", "part": "block", "format": "dxf"})
    assert code == 200 and "exit" in json.loads(body)              # what `cad export` says of a block, not a 400
    code, body = call("/api/export", {"slug": "demo", "part": "block", "format": "obj"})
    assert code == 400 and "3mf" in json.loads(body)["error"]


def test_open_file_location_reveals_a_part_file_or_the_project(server, monkeypatch):
    call, _, _ = server
    launched = []
    monkeypatch.setattr(serve.subprocess, "Popen", lambda cmd, **kw: launched.append(cmd))
    code, body = call("/api/reveal", {"slug": "demo", "part": "block"})
    assert code == 200 and json.loads(body)["revealed"].endswith("parts/block.py")
    code, body = call("/api/reveal", {"slug": "demo", "part": "../assembly"})   # no escaping the parts folder
    assert code == 200 and json.loads(body)["revealed"].endswith("demo")
    # xdg-open can't select a file, so on Linux it opens the folder that holds it
    assert len(launched) == 2 and all(str(c[-1]).endswith(("block.py", "parts", "demo")) for c in launched)


def test_mass_route_gives_mass_properties(server):
    call, _, _ = server
    code, body = call("/api/mass", {"slug": "demo", "bodies": ["block"]})
    data = json.loads(body)["data"]
    assert code == 200 and data["mass_kg"] > 0 and len(data["cog"]) == 3


# ─── POST /api/init (File > New) ─────────────────────────────────────────────

def test_init_route_creates_a_project_in_the_first_root_and_registers_it(server, demo):
    call, bench, _ = server
    code, body = call("/api/init", {"name": "newproj"})
    r = json.loads(body)
    assert code == 200 and r["exit"] == cli.OK
    assert r["data"]["slug"] == "newproj" and r["data"]["root"] == str(demo.parent)
    assert (demo.parent / "newproj" / "parts").is_dir()

    code, body = call("/api/projects")
    slugs = {p["slug"] for p in json.loads(body)["projects"]}
    assert {"demo", "newproj"} <= slugs


def test_init_route_rejects_a_bad_name(server):
    call, _, _ = server
    code, body = call("/api/init", {"name": "../escape"})
    r = json.loads(body)
    assert code == 200 and r["exit"] == cli.USAGE and "letters, digits" in r["data"]["error"]


def test_init_route_rejects_an_existing_project(server, demo):
    call, _, _ = server
    code, body = call("/api/init", {"name": "demo"})
    r = json.loads(body)
    assert code == 200 and r["exit"] == cli.USAGE and "already exists" in r["data"]["error"]


def test_init_route_with_an_explicit_new_root_registers_that_root_too(server, demo, tmp_path):
    call, bench, _ = server
    other = tmp_path / "other-root"
    code, body = call("/api/init", {"name": "proj2", "root": str(other)})
    r = json.loads(body)
    assert code == 200 and r["exit"] == cli.OK and r["data"]["root"] == str(other)
    assert (other / "proj2" / "parts").is_dir()
    assert other in bench.roots

    code, body = call("/api/projects")
    slugs = {p["slug"] for p in json.loads(body)["projects"]}
    assert {"demo", "proj2"} <= slugs


def test_init_route_broadcasts_a_projects_event(server, demo):
    call, bench, _ = server
    got = []
    bench.broadcast = got.append
    call("/api/init", {"name": "broadcasttest"})
    assert any(e.get("type") == "projects" for e in got)


def test_init_route_with_no_root_configured_is_a_clean_usage_error(server):
    call, bench, _ = server
    bench.roots = []          # simulate a workbench started with nothing to serve
    code, body = call("/api/init", {"name": "x"})
    r = json.loads(body)
    assert code == 200 and r["exit"] == cli.USAGE and "no projects root" in r["data"]["error"]


def test_projects_carry_a_file_card(server, demo):
    call, _, _ = server
    (demo / "out").mkdir(exist_ok=True)
    (demo / "out" / "_check_x.png").write_bytes(b"x")
    (demo / "out" / "part_front.png").write_bytes(b"x")
    (demo / "out" / "part_iso.png").write_bytes(b"x")
    item = next(p for p in json.loads(call("/api/projects")[1])["projects"] if p["slug"] == "demo")
    assert item["thumb"] == "out/part_iso.png"
    assert item["size"] > 0


def test_init_route_takes_the_brief(server, demo):
    call, _, _ = server
    code, body = call("/api/init", {"name": "briefed", "brief": "A mount for the laser head."})
    assert code == 200 and json.loads(body)["exit"] == cli.OK
    assert "A mount for the laser head." in (demo.parent / "briefed" / "mech_profile.md").read_text()
    code, body = call("/api/init", {"name": "unbriefed"})
    assert json.loads(body)["exit"] == cli.OK and "TODO" in (demo.parent / "unbriefed" / "mech_profile.md").read_text()


# ─── What a person can do from the page that the agent does from the CLI ─────────────────────────────

@pytest.fixture()
def works(tmp_path, monkeypatch):
    """test_bom.py's workshop (a laser-cut panel, two printed clips, a machined block, a bought motor), behind a
    server, with a library store of its own."""
    from test_bom import make_workshop
    monkeypatch.setattr(st, "ROOT", tmp_path)
    monkeypatch.delenv("CAD_PROJECTS", raising=False)
    monkeypatch.setenv("CAD_WARM_DIR", str(tmp_path / ".warm"))
    monkeypatch.setenv("CAD_LIBRARY", str(tmp_path / "store"))
    project = make_workshop(tmp_path)
    bench = serve.Bench([tmp_path], runner=inproc)
    call, _, stop = serving(bench, monkeypatch)
    yield call, bench, project
    stop()


def cad(call, slug, *argv):
    """POST /api/cad, the console's door: any `cad` subcommand, run for the page."""
    code, body = call("/api/cad", {"slug": slug, "argv": list(argv)})
    assert code == 200, body
    return json.loads(body)


def out(call, path, slug="works", **query):
    """GET /api/file for a path in the project: (status, bytes, headers)."""
    return call("/api/file?" + urllib.parse.urlencode({"slug": slug, "path": path, **query}), full=True)


def test_a_bom_is_a_table_for_the_page_and_its_files_download(works):
    call, _, _ = works
    r = cad(call, "works", "bom", "works")
    assert r["exit"] == cli.OK and [ln["name"] for ln in r["data"]["lines"]] == ["panel", "clip", "block", "motor"]
    assert r["data"]["totals"]["lines"] == 4 and r["data"]["files"][0].endswith("out/bom.csv")
    code, body, head = out(call, "out/bom.csv")
    assert code == 200 and head["Content-Type"] == "text/csv" and body.startswith(b"Index,Name,")
    assert head["Content-Disposition"] == 'attachment; filename="bom.csv"'
    code, body, head = out(call, "out/bom.json")
    assert code == 200 and head["Content-Type"] == "application/json" and json.loads(body)["project"] == "works"
    # the two options the page offers are the CLI's
    r = cad(call, "works", "bom", "works", "--only-parts")
    assert [ln["name"] for ln in r["data"]["lines"]] == ["panel", "clip", "block"] and r["data"]["options"]["only_parts"]


def test_a_drawing_shows_in_the_page_and_downloads_as_a_file(works):
    call, _, project = works
    r = cad(call, "works", "drawing", "works", "panel")
    # the design is not verified: the sheet is written, stamped, and the exit says UNCHECKED
    assert r["exit"] == cli.UNCHECKED and r["data"]["stamp"] == "NOT VERIFIED"
    assert [f["path"] for f in r["data"]["files"]] == ["panel.dxf", "panel.pdf", "panel.svg"]
    assert (project / "out" / "drawings" / "panel.svg").is_file()
    code, body, head = out(call, "out/drawings/panel.svg")
    assert code == 200 and head["Content-Type"] == "image/svg+xml" and b"<svg" in body[:600]
    assert head["Content-Disposition"] == 'attachment; filename="panel.svg"'
    # the page's own tab asks to see it: no download header, and nothing in it can run
    code, body, head = out(call, "out/drawings/panel.svg", inline="1")
    assert code == 200 and head["Content-Disposition"] is None
    assert "default-src 'none'" in head["Content-Security-Policy"] and head["X-Content-Type-Options"] == "nosniff"
    code, body, head = out(call, "out/drawings/panel.pdf", inline="1")
    assert code == 200 and body.startswith(b"%PDF") and head["Content-Type"] == "application/pdf" and head["Content-Disposition"] is None
    code, body, head = out(call, "out/drawings/panel.pdf")
    assert head["Content-Disposition"] == 'attachment; filename="panel.pdf"'
    code, body, head = out(call, "out/drawings/panel.dxf", inline="1")
    assert code == 200 and head["Content-Disposition"] == 'attachment; filename="panel.dxf"'      # a DXF is only ever saved
    # a part that is not a plate is the CLI's answer, not the server's
    r = cad(call, "works", "drawing", "works", "clip")
    assert r["exit"] == cli.USAGE and "fdm" in r["data"]["error"]


def test_the_file_server_gives_back_what_commands_write_and_nothing_else(works):
    call, _, project = works
    (project / "out").mkdir(exist_ok=True)
    for name in ("page.html", "run.py", "notes.txt", "keys.toml", "payload.svgz"):
        (project / "out" / name).write_text("x")
    (project / "checks.json").write_text("{}")
    for path in ("out/page.html", "out/run.py", "out/notes.txt", "out/keys.toml", "out/payload.svgz", "out/missing.csv",
                 "checks.json", "assembly.py", "parts/panel.py", "bought/motor.json", "out/../assembly.py", "../works/assembly.py"):
        assert out(call, path)[0] == 404, path
    (project / "out" / "table.csv").write_text("a,b\n")
    assert out(call, "out/table.csv")[0] == 200


def test_shop_writes_a_stamped_draft_the_page_can_list_and_download(works):
    call, _, project = works
    r = cad(call, "works", "shop", "works")                 # nothing is verified: nothing is written
    assert r["exit"] == cli.UNCHECKED and r["data"]["done"] is False and not (project / "out" / "shop").exists()
    r = cad(call, "works", "shop", "works", "--draft")
    assert r["exit"] == cli.UNCHECKED and r["data"]["draft"] is True and r["data"]["rows_total"] > 0
    paths = {f["path"] for f in r["data"]["files"]}
    assert {"panel.dxf", "panel.step", "clip.3mf", "clip.stl", "bom.csv", "bom.json", "drawings/panel.svg"} <= paths
    code, body, head = out(call, "out/shop/manifest.json")        # what the page shows of a shop folder it did not just write
    manifest = json.loads(body)
    assert code == 200 and manifest["draft"] is True and manifest["verdict"] == "NOT VERIFIED"
    assert {f["path"] for f in manifest["files"]} == paths
    for path in ("out/shop/panel.dxf", "out/shop/clip.3mf", "out/shop/drawings/panel.pdf"):
        code, body, head = out(call, path)
        assert code == 200 and body and "attachment" in head["Content-Disposition"], path
    r = cad(call, "works", "shop", "works", "--check")            # a design nobody verified has nothing to certify
    assert r["exit"] == cli.UNCHECKED and r["data"]["done"] is False and "cad verify" in r["data"]["reasons"][0]


def test_the_library_answers_without_a_project_and_a_part_goes_into_one_with_undo(works):
    call, bench, project = works
    code, body = call("/api/cad", {"argv": ["lib", "ls", "nema"]})                   # no slug: the catalog needs no project
    r = json.loads(body)
    assert code == 200 and r["exit"] == cli.OK and {"nema8", "nema17", "fcl-nema17"} <= {e["name"] for e in r["data"]["entries"]}
    code, body = call("/api/cad", {"argv": ["lib", "info", "nema8"]})
    r = json.loads(body)
    assert r["exit"] == cli.OK and r["data"]["entry"]["vendor"] == "Nanotec" and r["data"]["status"] == "ready"
    assert json.loads(call("/api/cad", {"argv": ["rules"]})[1])["data"]["rules"]
    r = json.loads(call("/api/cad", {"argv": ["eval", "brief", "nema17_mount"]})[1])       # the task set is read, not run
    assert r["exit"] == cli.OK and r["data"]["task"] == "nema17_mount" and "NEMA 17" in r["data"]["brief"]
    assert json.loads(call("/api/cad", {"argv": ["eval", "ls"]})[1])["data"]["tasks"]
    # what reads a project still names one, and so does a command that is not on the list: `eval run` starts a real agent
    for argv in (["check", "works"], ["bom", "works"], ["approve", "works"], ["eval", "run", "--agent", "true"], ["eval"]):
        code, body = call("/api/cad", {"argv": argv})
        assert code == 400 and "missing slug" in json.loads(body)["error"], argv

    r = cad(call, "works", "lib", "use", "works", "extrusion-2020", "length=150", "--as", "rail_2020")
    assert r["exit"] == cli.OK and r["data"]["journaled"] is True and r["data"]["params"]["length"] == 150
    assert (project / "bought" / "rail_2020.json").is_file()
    history = json.loads(call("/api/history?slug=works")[1])
    assert history["undo"][0]["name"] == "Add Library Part" and history["undo"][0]["by"] == "ui"
    r = cad(call, "works", "lib", "check", "works")
    assert r["exit"] == cli.OK and r["data"]["rows"]
    code, body = call("/api/undo", {"slug": "works"})
    assert json.loads(body)["exit"] == cli.OK and not (project / "bought" / "rail_2020.json").exists()


def test_a_picked_file_is_kept_for_the_command_that_wants_a_path(works, tmp_path):
    import hashlib
    from pathlib import Path
    from build123d import Box
    from cad_agent import export as ex
    call, bench, project = works
    step = tmp_path / "made.step"
    ex.write_step(Box(10, 20, 30), step)
    data = step.read_bytes()
    code, body = call("/api/upload?name=" + urllib.parse.quote("my part (1).step"), raw=data)
    up = json.loads(body)
    assert code == 200 and up["name"] == "my_part_1_.step" and up["bytes"] == len(data)
    assert up["sha256"] == hashlib.sha256(data).hexdigest()
    assert bench.uploads in Path(up["path"]).parents and Path(up["path"]).read_bytes() == data
    # a name is a name: no folders, no dots in front
    code, body = call("/api/upload?name=" + urllib.parse.quote("../../etc/.passwd"), raw=b"x")
    assert code == 200 and json.loads(body)["name"] == "passwd" and bench.uploads in Path(json.loads(body)["path"]).parents

    # and `cad lib add` takes it, as the file the person picked: a new entry in the store, then into the project
    r = cad(call, "works", "lib", "add", "test-box", up["path"], "--source", "https://example.com/box", "--title", "Test box")
    assert r["exit"] == cli.OK and r["data"]["created"] is True and str(tmp_path / "store") in r["data"]["path"]
    r = cad(call, "works", "lib", "info", "test-box")
    assert r["exit"] == cli.OK and r["data"]["status"] == "in your store" and r["data"]["in_store"] is True
    r = cad(call, "works", "lib", "use", "works", "test-box")
    assert r["exit"] == cli.OK and (project / "bought" / "test_box.step").is_file()
    # a file that is not a STEP is the CLI's refusal
    code, body = call("/api/upload?name=notes.txt", raw=b"not a step file")
    r = cad(call, "works", "lib", "add", "test-notes", json.loads(body)["path"], "--source", "https://example.com/n")
    assert r["exit"] == cli.USAGE and "STEP" in r["data"]["error"]


def test_an_upload_needs_the_header_a_name_and_a_body_that_arrives(works, monkeypatch):
    import socket
    call, bench, _ = works
    assert call("/api/upload?name=a.step", raw=b"x", header=False)[0] == 403
    assert call("/api/upload", raw=b"x")[0] == 400                    # no name
    assert call("/api/upload?name=a.step", raw=b"")[0] == 400         # nothing in it
    assert bench.uploads is None                                      # none of those made a folder
    host, port = call.base[len("http://"):].split(":")

    def raw(request: bytes, shutdown=False) -> bytes:                 # raw sockets: urllib sends exactly what it says
        with socket.create_connection((host, int(port)), timeout=10) as s:
            s.sendall(request)
            if shutdown:
                s.shutdown(socket.SHUT_WR)
            return s.recv(65536)
    head = b"POST /api/upload?name=a.step HTTP/1.0\r\nHost: 127.0.0.1\r\nX-CAD: 1\r\nContent-Length: 100\r\n\r\n"
    assert b" 400 " in raw(head + b"0123456789", shutdown=True).split(b"\r\n")[0]       # ten bytes of a hundred
    assert bench.uploads is not None and not list(bench.uploads.iterdir())              # and no file left behind
    monkeypatch.setattr(serve, "UPLOAD_MAX", 50)
    assert b" 413 " in raw(head).split(b"\r\n")[0]


def test_an_upload_folder_a_stopped_server_left_behind_goes_after_twelve_hours(works, monkeypatch, tmp_path):
    import os
    import tempfile
    call, bench, _ = works
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp"))
    (tmp_path / "tmp").mkdir()
    old, recent, other = (tmp_path / "tmp" / n for n in ("cad-upload-old", "cad-upload-recent", "somebody-elses"))
    for d in (old, recent, other):
        d.mkdir()
        (d / "x.step").write_text("x")
    os.utime(old, (time.time() - 13 * 3600,) * 2)
    os.utime(other, (time.time() - 99 * 3600,) * 2)
    assert call("/api/upload?name=a.step", raw=b"ISO-10303-21;")[0] == 200
    assert not old.exists() and recent.exists() and other.exists()      # only an old cad-upload-* folder, and not this server's own
    assert bench.uploads is not None and bench.uploads.parent == tmp_path / "tmp"


def test_a_machines_poses_are_in_the_scene_and_the_pages_arithmetic_is_the_kernels(tmp_path, monkeypatch, capsys):
    """The page shows a pose by moving the bodies each axis carries, so the scene carries AXES and POSES, and the
    sum the page does (motion.pose: the axis's unit direction times its position, added up) must equal what
    subassembly.apply_pose makes of the solids."""
    from test_mini_machine import lay
    from cad_agent.geom import bbox
    from cad_agent.subassembly import apply_pose
    monkeypatch.setattr(st, "ROOT", tmp_path)
    monkeypatch.delenv("CAD_PROJECTS", raising=False)
    monkeypatch.setenv("CAD_WARM_DIR", str(tmp_path / ".warm"))
    monkeypatch.setenv("CAD_LIBRARY", str(tmp_path / "store"))
    lay(tmp_path)
    assert run(capsys, "scene", "mini_machine")[0] == cli.OK
    scene = json.loads((tmp_path / "mini_machine" / "out" / "scene.json").read_text())
    assert scene["format"] == "cad-scene/3"
    assert scene["poses"] == {"park": {"slide": 60.0, "gantry/x": -45.0}, "work": {"slide": 0.0, "gantry/x": 30.0},
                              "gantry/park": {"gantry/x": -45.0}}
    axes = {a["name"]: a for a in scene["axes"]}

    def offset(pose, body):      # what the page's poseOffsets does, line for line
        total = np.zeros(3)
        for axis, at in scene["poses"][pose].items():
            a = axes[axis]
            if body in a["moves"]:
                d = np.array(a["direction"], dtype=float)
                total += d / np.linalg.norm(d) * at
        return total

    machine = st.load_machine("mini_machine", placed=True)
    for pose in scene["poses"]:
        posed = apply_pose(machine, pose)
        for name, solid in machine.parts.items():
            (lo, _), (plo, _) = bbox(solid), bbox(posed[name])
            assert np.allclose(np.array(plo) - np.array(lo), offset(pose, name), atol=1e-6), (pose, name)
    assert any(offset("park", b).any() for b in machine.parts) and not offset("work", "base").any()


def test_a_project_without_poses_has_an_empty_set(demo, capsys):
    run(capsys, "scene", "demo")
    scene = json.loads((demo / "out" / "scene.json").read_text())
    assert scene["poses"] == {} and scene["axes"] == []


def test_a_body_made_with_bought_solid_is_bought_in_the_scene_whatever_it_is_called(tmp_path, monkeypatch, capsys):
    """The tree and the colours decided by names alone, so `drive = bought_solid(SLUG, "motor")` showed as stock."""
    from test_bom import ASSEMBLY, make_workshop
    monkeypatch.setattr(st, "ROOT", tmp_path)
    monkeypatch.delenv("CAD_PROJECTS", raising=False)
    monkeypatch.setenv("CAD_WARM_DIR", str(tmp_path / ".warm"))
    make_workshop(tmp_path, assembly=ASSEMBLY.replace('"motor":', '"drive":'))
    assert run(capsys, "scene", "works")[0] == cli.OK
    scene = json.loads((tmp_path / "works" / "out" / "scene.json").read_text())
    kinds = {b["name"]: b["kind"] for b in scene["bodies"]}
    assert kinds["drive"] == "bought" and kinds["panel"] == "made" and kinds["block"] == "made"
    drive = next(b for b in scene["bodies"] if b["name"] == "drive")
    assert drive["part"] is None and drive["color"] == "#6f8fb0" and "project" not in drive and drive["params"] == {}

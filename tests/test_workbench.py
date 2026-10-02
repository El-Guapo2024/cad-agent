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
    assert scene["format"] == "cad-scene/2" and scene["assembly"] is True
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


@pytest.fixture()
def server(demo, monkeypatch):
    bench = serve.Bench([demo.parent], runner=inproc)
    scheduled = []
    monkeypatch.setattr(bench, "schedule", lambda slug, kind="check": scheduled.append((slug, kind)))
    srv = serve.make_server(bench, "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def call(path, body=None, header=True):
        req = urllib.request.Request(base + path)
        if body is not None:
            req.data = json.dumps(body).encode()
            req.add_header("Content-Type", "application/json")
            if header:
                req.add_header("X-CAD", "1")
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    yield call, bench, scheduled
    srv.shutdown()
    srv.server_close()


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

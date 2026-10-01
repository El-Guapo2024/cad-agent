"""The workbench's shared GUI state: FreeCADGui's job (Gui.Selection,
Visibility, SendMsgToActiveView, ViewObject properties) as HTTP endpoints
(serve.py / gui.py), a generic command runner (/api/cad), and the CLI that
drives them from a shell (cli.py gui_* / gui_client.py), including finding
the right workbench when more than one is running on the machine.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from cad_agent import cli, gui, gui_client, serve
from cad_agent import state as st
from cad_agent.verify import source_hash
from test_cli import ASSEMBLY, BLOCK, PLATE, run
from test_workbench import demo, inproc, server  # noqa: F401  (reused fixtures)


# ─── discovery plumbing ──────────────────────────────────────────────────────

@pytest.fixture()
def runtime(tmp_path, monkeypatch):
    """Point the server registry at a throwaway dir, like a fresh machine, and
    make sure CAD_SERVE_URL from the real environment never leaks into a test."""
    monkeypatch.setenv("CAD_RUNTIME_DIR", str(tmp_path / "runtime-home"))
    monkeypatch.delenv("CAD_SERVE_URL", raising=False)
    return tmp_path / "runtime-home"


def _http(base, path, body=None, header=True, method=None):
    req = urllib.request.Request(base + path, method=method)
    if body is not None:
        req.data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
        if header:
            req.add_header("X-CAD", "1")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


class _Live:
    """A real Bench + HTTP server for one projects root, with host/port set the
    way serve.run() sets them, so it can be registered like `cad serve` does."""

    def __init__(self, root: Path):
        self.bench = serve.Bench([root], runner=inproc)
        self.srv = serve.make_server(self.bench, "127.0.0.1", 0)
        self.bench.host, self.bench.port = "127.0.0.1", self.srv.server_address[1]
        self.url = f"http://127.0.0.1:{self.bench.port}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def call(self, path, body=None, header=True):
        return _http(self.url, path, body, header)

    def register(self):
        serve.write_registry(self.bench)

    def close(self):
        # a Deviation/AngularDeflection `set` schedules a real debounced rescene
        # (serve.Bench.rescene_debounced); nothing else ever tears that down, and an
        # orphaned timer firing after this fixture is gone would run `cad scene` through
        # `inproc`'s process-global redirect_stdout in a thread the next test does not
        # expect, stealing its captured stdout. Cancel whatever is still pending.
        for timer in self.bench.rescene_timers.values():
            timer.cancel()
        self.srv.shutdown()
        self.srv.server_close()


@pytest.fixture()
def bench_server(demo, runtime):
    live = _Live(demo.parent)
    yield live
    live.close()


def _make_project(root: Path, slug: str = "demo") -> Path:
    d = root / slug
    (d / "parts").mkdir(parents=True)
    (d / "bought").mkdir()
    (d / "out").mkdir()
    (d / "parts" / "plate.py").write_text(PLATE)
    (d / "parts" / "block.py").write_text(BLOCK)
    (d / "assembly.py").write_text(ASSEMBLY)
    return d


# ─── GET/POST /api/gui ───────────────────────────────────────────────────────

def test_default_gui_state_is_empty_and_disconnected(server, demo):
    call, bench, scheduled = server
    code, body = call("/api/gui?slug=demo")
    data = json.loads(body)
    assert code == 200
    assert data == {"slug": "demo", "connected": False, "selected": [], "preselected": None,
                    "hidden": [], "task": None, "view": {"camera": None, "projection": None},
                    "view_props": {}, "unselectable": [], "commands": [], "camera_node": None, "updated": None}


def test_get_gui_404s_for_an_unknown_project(server):
    call, _, _ = server
    code, _ = call("/api/gui?slug=nope")
    assert code == 404


def test_post_gui_merges_partial_state_and_marks_connected(server, demo):
    call, bench, _ = server
    code, body = call("/api/gui", {"slug": "demo", "state": {
        "selected": ["block"], "preselected": "plate.Face1", "task": "Sketch edit",
        "view": {"camera": "iso"}}})
    assert code == 200
    data = json.loads(body)
    assert data["connected"] is True and data["selected"] == ["block"]
    assert data["preselected"] == "plate.Face1" and data["task"] == "Sketch edit"
    assert data["view"] == {"camera": "iso", "projection": None}

    # a second, disjoint partial update leaves the rest alone
    code, body = call("/api/gui", {"slug": "demo", "state": {"view": {"projection": "ortho"}}})
    data = json.loads(body)
    assert data["view"] == {"camera": "iso", "projection": "ortho"}
    assert data["selected"] == ["block"] and data["task"] == "Sketch edit"


def test_post_gui_rejects_a_non_object_state(server, demo):
    call, _, _ = server
    code, body = call("/api/gui", {"slug": "demo", "state": "nope"})
    assert code == 400 and "state must be an object" in json.loads(body)["error"]


def test_post_gui_view_props_merge_per_body_without_clobbering(server, demo):
    call, bench, _ = server
    call("/api/gui", {"slug": "demo", "state": {"view_props": {"block": {"shapeColor": "#ff0000"}}}})
    code, body = call("/api/gui", {"slug": "demo",
                                   "state": {"view_props": {"block": {"transparency": 50}}}})
    data = json.loads(body)
    assert data["view_props"] == {"block": {"shapeColor": 0xFF0000, "transparency": 50}}

    code, body = call("/api/gui", {"slug": "demo", "state": {"unselectable": ["plate"]}})
    assert json.loads(body)["unselectable"] == ["plate"]
    # out/gui.json gets both, alongside hidden
    saved = json.loads((demo / "out" / "gui.json").read_text())
    assert saved["view_props"] == {"block": {"shapeColor": 0xFF0000, "transparency": 50}}
    assert saved["unselectable"] == ["plate"]


def test_post_gui_view_props_rejects_pseudo_props_and_bad_values(server, demo):
    call, _, _ = server
    code, body = call("/api/gui", {"slug": "demo", "state": {"view_props": {"block": {"visibility": True}}}})
    assert code == 400 and "not a view property" in json.loads(body)["error"]
    code, body = call("/api/gui", {"slug": "demo", "state": {"view_props": {"block": {"transparency": 200}}}})
    assert code == 400


# ─── Deviation/AngularDeflection: the two that re-tessellate ────────────────

def test_post_gui_view_props_retessellates_only_for_deviation_and_angular(server, demo, monkeypatch):
    call, bench, _ = server
    rescened = []
    monkeypatch.setattr(bench, "rescene_debounced", lambda slug: rescened.append(slug))

    # a plain look change needs no new geometry
    call("/api/gui", {"slug": "demo", "state": {"view_props": {"block": {"shapeColor": "#ff0000"}}}})
    assert rescened == []

    call("/api/gui", {"slug": "demo", "state": {"view_props": {"block": {"deviation": 0.5}}}})
    assert rescened == ["demo"]
    call("/api/gui", {"slug": "demo", "state": {"view_props": {"plate": {"angularDeflection": 15.0}}}})
    assert rescened == ["demo", "demo"]


def test_gui_do_set_retessellates_only_for_deviation_and_angular(server, demo, monkeypatch):
    call, bench, _ = server
    rescened = []
    monkeypatch.setattr(bench, "rescene_debounced", lambda slug: rescened.append(slug))

    call("/api/gui/do", {"slug": "demo", "cmd": "set", "args": ["block"],
                         "props": {"shapeColor": "255,0,0"}})
    assert rescened == []
    call("/api/gui/do", {"slug": "demo", "cmd": "hide", "args": ["block"]})   # a non-"set" cmd
    assert rescened == []

    call("/api/gui/do", {"slug": "demo", "cmd": "set", "args": ["block"],
                         "props": {"deviation": 0.5, "shapeColor": "255,0,0"}})
    assert rescened == ["demo"]
    call("/api/gui/do", {"slug": "demo", "cmd": "set", "args": ["plate"],
                         "props": {"angularDeflection": 90.0}})
    assert rescened == ["demo", "demo"]


# ─── the UI's published `cad gui run` vocabulary ────────────────────────────

def test_post_gui_commands_round_trips_and_is_not_persisted(server, demo):
    call, bench, _ = server
    published = [{"name": "Std_ViewFitAll", "label": "Fit All", "enabled": True},
                {"name": "CADAgent_Frobnicate", "label": "Frobnicate", "enabled": False}]
    code, body = call("/api/gui", {"slug": "demo", "state": {"commands": published}})
    assert code == 200 and json.loads(body)["commands"] == published
    assert json.loads(call("/api/gui?slug=demo")[1])["commands"] == published

    # session-only: never written to out/gui.json, and gone on a fresh bench
    assert not (demo / "out" / "gui.json").exists()
    fresh = serve.Bench([demo.parent], runner=inproc)
    assert fresh.gui_get("demo")["commands"] == []

    # a later post replaces the whole list, same as `selected`
    code, body = call("/api/gui", {"slug": "demo", "state": {"commands": []}})
    assert json.loads(body)["commands"] == []


@pytest.mark.parametrize("commands", [
    "nope",
    [{"name": "X"}],
    [{"name": "X", "label": "Y", "enabled": "true"}],
    [{"name": 1, "label": "Y", "enabled": True}],
    [{"name": "X", "label": 2, "enabled": True}],
])
def test_post_gui_commands_rejects_bad_shapes(server, demo, commands):
    call, _, _ = server
    code, body = call("/api/gui", {"slug": "demo", "state": {"commands": commands}})
    assert code == 400


# ─── POST /api/gui/do ────────────────────────────────────────────────────────

def test_gui_do_select_and_clear_round_trip_and_log(server, demo):
    call, bench, _ = server
    code, body = call("/api/gui/do", {"slug": "demo", "cmd": "select", "args": ["block", "plate"]})
    assert code == 200 and json.loads(body) == {"ok": True, "clients": 0}
    assert json.loads(call("/api/gui?slug=demo")[1])["selected"] == ["block", "plate"]

    code, body = call("/api/gui/do", {"slug": "demo", "cmd": "clear", "args": []})
    assert code == 200
    assert json.loads(call("/api/gui?slug=demo")[1])["selected"] == []

    log = (demo / ".cad" / "log.jsonl").read_text()
    assert '"cmd": "gui.select"' in log and '"cmd": "gui.clear"' in log
    assert '"block", "plate"' in log or '"block"' in log   # argv was logged


def test_gui_do_show_and_hide_persist_to_gui_json_immediately(server, demo):
    call, _, _ = server
    before, n = source_hash(demo)
    code, body = call("/api/gui/do", {"slug": "demo", "cmd": "hide", "args": ["block"]})
    assert code == 200
    data = json.loads(call("/api/gui?slug=demo")[1])
    assert data["hidden"] == ["block"]
    saved = json.loads((demo / "out" / "gui.json").read_text())
    assert saved["hidden"] == ["block"]
    # out/ is never part of what `cad verify` hashes
    after, m = source_hash(demo)
    assert after == before and m == n

    call("/api/gui/do", {"slug": "demo", "cmd": "show", "args": ["block"]})
    assert json.loads(call("/api/gui?slug=demo")[1])["hidden"] == []


def test_gui_do_view_and_fit_and_say(server, demo):
    call, _, _ = server
    call("/api/gui/do", {"slug": "demo", "cmd": "view", "args": ["iso"]})
    assert json.loads(call("/api/gui?slug=demo")[1])["view"]["camera"] == "iso"
    call("/api/gui/do", {"slug": "demo", "cmd": "view", "args": ["ortho"]})
    data = json.loads(call("/api/gui?slug=demo")[1])
    assert data["view"] == {"camera": "iso", "projection": "ortho"}

    code, body = call("/api/gui/do", {"slug": "demo", "cmd": "fit", "args": ["selection"]})
    assert code == 200 and json.loads(body)["ok"] is True
    code, body = call("/api/gui/do", {"slug": "demo", "cmd": "say", "args": ["hello there"]})
    assert code == 200
    log = (demo / ".cad" / "log.jsonl").read_text()
    assert '"cmd": "gui.say"' in log and '"cmd": "gui.fit"' in log


def test_gui_do_view_takes_an_inventor_camera(server, demo):
    call, _, _ = server
    cam = ("OrthographicCamera {   viewportMapping ADJUST_CAMERA   position 0 0 87.5   orientation 0 0 1  0"
           "   nearDistance 37.5   farDistance 137.5   aspectRatio 1   focalDistance 87.5   height 100  }")
    code, _ = call("/api/gui/do", {"slug": "demo", "cmd": "view", "args": [cam]})
    assert code == 200
    assert json.loads(call("/api/gui?slug=demo")[1])["view"] == {"camera": cam, "projection": "ortho"}
    persp = "#Inventor V2.1 ascii\n\n\nPerspectiveCamera {\n  position 1 2 3\n  heightAngle 0.78539819\n\n}\n"
    call("/api/gui/do", {"slug": "demo", "cmd": "view", "args": [persp]})
    assert json.loads(call("/api/gui?slug=demo")[1])["view"]["projection"] == "persp"
    code, _ = call("/api/gui/do", {"slug": "demo", "cmd": "view", "args": ["Camera { position 0 0 1 }"]})
    assert code == 400


def test_post_gui_camera_node_round_trips_and_is_validated(server, demo):
    call, _, _ = server
    cam = "#Inventor V2.1 ascii\n\n\nOrthographicCamera {\n  position 1 2 3\n  height 50\n\n}\n"
    code, _ = call("/api/gui", {"slug": "demo", "state": {"camera_node": cam}})
    assert code == 200
    assert json.loads(call("/api/gui?slug=demo")[1])["camera_node"] == cam
    code, _ = call("/api/gui", {"slug": "demo", "state": {"camera_node": "not a camera"}})
    assert code == 400


def test_gui_do_run_broadcasts_and_passes_through_extra_args(server, demo):
    call, _, _ = server
    code, body = call("/api/gui/do", {"slug": "demo", "cmd": "run", "args": ["Std_ViewFitAll"]})
    assert code == 200 and json.loads(body) == {"ok": True, "clients": 0}

    code, body = call("/api/gui/do", {"slug": "demo", "cmd": "run",
                                      "args": ["CADAgent_Frobnicate", "arg1", "arg2"]})
    assert code == 200
    log = (demo / ".cad" / "log.jsonl").read_text()
    assert '"cmd": "gui.run"' in log and '"CADAgent_Frobnicate", "arg1", "arg2"' in log


def test_gui_do_set_handles_view_props_and_visibility_and_selectable(server, demo):
    call, _, _ = server
    code, body = call("/api/gui/do", {"slug": "demo", "cmd": "set", "args": ["block"],
                                      "props": {"shapeColor": "255,0,0", "transparency": 40,
                                                "visibility": False, "selectable": False}})
    assert code == 200
    data = json.loads(call("/api/gui?slug=demo")[1])
    assert data["view_props"]["block"] == {"shapeColor": 0xFF0000, "transparency": 40}
    assert data["hidden"] == ["block"] and data["unselectable"] == ["block"]
    saved = json.loads((demo / "out" / "gui.json").read_text())
    assert saved["view_props"]["block"] == {"shapeColor": 0xFF0000, "transparency": 40}
    assert saved["hidden"] == ["block"] and saved["unselectable"] == ["block"]

    call("/api/gui/do", {"slug": "demo", "cmd": "set", "args": ["block"],
                         "props": {"visibility": True, "selectable": True}})
    data = json.loads(call("/api/gui?slug=demo")[1])
    assert data["hidden"] == [] and data["unselectable"] == []
    assert data["view_props"]["block"] == {"shapeColor": 0xFF0000, "transparency": 40}


@pytest.mark.parametrize("payload, needle", [
    ({"cmd": "nope", "args": []}, "unknown gui command"),
    ({"cmd": "hide", "args": []}, "needs at least one name"),
    ({"cmd": "clear", "args": ["x"]}, "takes no arguments"),
    ({"cmd": "view", "args": ["sideways"]}, "unknown view"),
    ({"cmd": "fit", "args": ["x", "y"]}, "fit takes"),
    ({"cmd": "say", "args": []}, "say needs text"),
    ({"cmd": "set", "args": ["block"], "props": {"transparency": 500}}, "must be a number between"),
    ({"cmd": "set", "args": ["block"], "props": {"deviation": 500}}, "must be a number between"),
    ({"cmd": "set", "args": ["block"], "props": {"angularDeflection": 0}}, "must be a number between"),
    ({"cmd": "set", "args": ["block"], "props": {"nope": 1}}, "unknown view property"),
    ({"cmd": "set", "args": ["block", "plate"], "props": {"transparency": 1}}, "exactly one body"),
    ({"cmd": "run", "args": []}, "needs a command name"),
    ({"cmd": "run", "args": ["not a command"]}, "command name"),
    ({"cmd": "run", "args": ["bad-name"]}, "command name"),
    ({"cmd": "run", "args": ["3dStart"]}, "command name"),
])
def test_gui_do_rejects_bad_commands_and_arguments(server, demo, payload, needle):
    call, _, _ = server
    code, body = call("/api/gui/do", {"slug": "demo", **payload})
    assert code == 400 and needle in json.loads(body)["error"]


def test_gui_do_requires_the_x_cad_header(server, demo):
    call, _, _ = server
    code, _ = call("/api/gui/do", {"slug": "demo", "cmd": "clear", "args": []}, header=False)
    assert code == 403


# ─── gui.json persistence across a restart ──────────────────────────────────

def test_hidden_and_view_props_survive_a_fresh_bench(server, demo):
    call, _, _ = server
    call("/api/gui/do", {"slug": "demo", "cmd": "hide", "args": ["plate"]})
    call("/api/gui/do", {"slug": "demo", "cmd": "set", "args": ["block"],
                         "props": {"displayMode": "Wireframe"}})
    call("/api/gui/do", {"slug": "demo", "cmd": "select", "args": ["block"]})  # session-only

    fresh = serve.Bench([demo.parent], runner=inproc)   # a new process would start here
    data = fresh.gui_get("demo")
    assert data["hidden"] == ["plate"]
    assert data["view_props"] == {"block": {"displayMode": "Wireframe"}}
    assert data["selected"] == [] and data["task"] is None   # session state did not persist


# ─── POST /api/cad ───────────────────────────────────────────────────────────

def test_api_cad_runs_a_subcommand_like_the_cli_would(server, demo):
    call, _, _ = server
    code, body = call("/api/cad", {"slug": "demo", "argv": ["status", "demo"]})
    data = json.loads(body)
    assert code == 200 and data["exit"] == cli.OK and data["data"]["project"] == "demo"


@pytest.mark.parametrize("argv", [["serve"], ["service", "status"]])
def test_api_cad_refuses_serve_and_service(server, demo, argv):
    call, _, _ = server
    code, body = call("/api/cad", {"slug": "demo", "argv": argv})
    data = json.loads(body)
    assert code == 200 and data["exit"] == cli.USAGE and "cannot run through the workbench" in data["data"]["error"]


def test_api_cad_rejects_a_bad_argv(server, demo):
    call, _, _ = server
    code, body = call("/api/cad", {"slug": "demo", "argv": []})
    assert code == 400
    code, body = call("/api/cad", {"slug": "demo", "argv": "status"})
    assert code == 400


# ─── registry: several workbenches at once ──────────────────────────────────

def test_write_list_and_remove_registry_round_trip(bench_server, runtime):
    bench_server.register()
    recs = serve.list_registry()
    assert len(recs) == 1 and recs[0]["port"] == bench_server.bench.port
    assert recs[0]["roots"] == [str(bench_server.bench.roots[0])]
    serve.remove_registry(bench_server.bench.port)
    assert serve.list_registry() == []


def test_find_server_prefers_cad_serve_url_override(monkeypatch, tmp_path):
    monkeypatch.setenv("CAD_SERVE_URL", "http://example.invalid:9")
    assert gui_client.find_server(tmp_path, "whatever") == "http://example.invalid:9"


def test_find_server_fails_clearly_when_nothing_is_running(runtime, tmp_path):
    with pytest.raises(gui_client.NoWorkbench, match="no workbench running"):
        gui_client.find_server(tmp_path, "demo")


def test_find_server_matches_by_root(bench_server, demo):
    bench_server.register()
    assert gui_client.find_server(demo.parent, "demo") == bench_server.url


def test_find_server_falls_back_to_the_live_project_list(bench_server, demo, tmp_path):
    bench_server.register()
    # a root that does not match anything recorded, but the slug is live
    other_root = tmp_path / "elsewhere"
    other_root.mkdir()
    assert gui_client.find_server(other_root, "demo") == bench_server.url


def test_find_server_drops_a_dead_registration(runtime, tmp_path):
    # bind a real socket to get a free port, then close it: guaranteed to answer nothing
    probe = serve.make_server(serve.Bench([]), "127.0.0.1", 0)
    dead_port = probe.server_address[1]
    probe.server_close()
    serve._registry_dir().mkdir(parents=True, exist_ok=True)
    (serve._registry_dir() / f"{dead_port}.json").write_text(json.dumps(
        {"host": "127.0.0.1", "port": dead_port, "pid": 999999, "roots": [str(tmp_path)]}))
    with pytest.raises(gui_client.NoWorkbench):
        gui_client.find_server(tmp_path, "demo")
    assert serve.list_registry() == []        # the stale file was cleaned up


def test_find_server_is_ambiguous_with_two_equally_good_matches(runtime, tmp_path):
    rootA, rootB = tmp_path / "a", tmp_path / "b"
    _make_project(rootA), _make_project(rootB)
    liveA, liveB = _Live(rootA), _Live(rootB)
    try:
        liveA.register()
        liveB.register()
        other_root = tmp_path / "unrelated"
        other_root.mkdir()
        with pytest.raises(gui_client.NoWorkbench, match="2 workbenches could serve"):
            gui_client.find_server(other_root, "demo")
    finally:
        liveA.close()
        liveB.close()


# ─── cad gui ... from the CLI ────────────────────────────────────────────────

def test_cli_gui_state_select_show_hide_view_fit_say_clear(bench_server, demo, capsys):
    bench_server.register()
    code, data = run(capsys, "gui", "select", "demo", "block")
    assert code == cli.OK and data["clients"] == 0

    code, data = run(capsys, "gui", "state", "demo")
    assert code == cli.OK and data["selected"] == ["block"] and data["connected"] is True

    code, data = run(capsys, "gui", "show", "demo", "block")
    assert code == cli.OK
    code, data = run(capsys, "gui", "hide", "demo", "block", "plate")
    assert code == cli.OK
    code, data = run(capsys, "gui", "state", "demo")
    assert sorted(data["hidden"]) == ["block", "plate"]

    assert run(capsys, "gui", "view", "demo", "top")[0] == cli.OK
    assert run(capsys, "gui", "fit", "demo", "--selection")[0] == cli.OK
    assert run(capsys, "gui", "say", "demo", "hello", "there")[0] == cli.OK
    code, data = run(capsys, "gui", "clear", "demo")
    assert code == cli.OK
    code, data = run(capsys, "gui", "state", "demo")
    assert data["selected"] == [] and data["view"]["camera"] == "top"


def test_cli_gui_set_maps_freecad_property_names(bench_server, demo, capsys):
    bench_server.register()
    code, data = run(capsys, "gui", "set", "demo", "block", "ShapeColor=#00ff00",
                     "Transparency=25", "Visibility=false")
    assert code == cli.OK
    code, data = run(capsys, "gui", "state", "demo")
    assert data["view_props"]["block"] == {"shapeColor": 0x00FF00, "transparency": 25}
    assert data["hidden"] == ["block"]


def test_cli_gui_set_accepts_deviation_and_angular_deflection(bench_server, demo, capsys, monkeypatch):
    # this test is about validation, not about the real debounced rescene (which has its own
    # tests): a real one would run `cad scene` on a background thread via `inproc`'s process-
    # global redirect_stdout, racing this same test's later run()/capsys calls.
    monkeypatch.setattr(bench_server.bench, "rescene_debounced", lambda slug: None)
    bench_server.register()
    code, data = run(capsys, "gui", "set", "demo", "block", "Deviation=0.5", "AngularDeflection=15")
    assert code == cli.OK
    code, data = run(capsys, "gui", "state", "demo")
    assert data["view_props"]["block"] == {"deviation": 0.5, "angularDeflection": 15.0}

    # FreeCAD's own ranges (tessRange / angDeflectionRange): 0.01-100 and 1-180
    code, data = run(capsys, "gui", "set", "demo", "block", "Deviation=0.001")
    assert code == cli.USAGE and "must be between" in data["error"]
    code, data = run(capsys, "gui", "set", "demo", "block", "AngularDeflection=181")
    assert code == cli.USAGE and "must be between" in data["error"]


def test_cli_gui_rejects_an_unknown_body_name(bench_server, demo, capsys):
    bench_server.register()
    code, data = run(capsys, "gui", "select", "demo", "not_a_body")
    assert code == cli.USAGE and "not_a_body" in data["error"] and "block" in data["error"]
    code, data = run(capsys, "gui", "hide", "demo", "not_a_body")
    assert code == cli.USAGE


def test_cli_gui_set_rejects_an_unknown_or_bad_property(bench_server, demo, capsys):
    bench_server.register()
    code, data = run(capsys, "gui", "set", "demo", "block", "Nope=1")
    assert code == cli.USAGE and "unknown view property" in data["error"]
    code, data = run(capsys, "gui", "set", "demo", "block", "Transparency=notanumber")
    assert code == cli.USAGE


def test_cli_gui_select_allows_subelement_names_but_show_does_not(bench_server, demo, capsys):
    bench_server.register()
    assert run(capsys, "gui", "select", "demo", "block.Face3")[0] == cli.OK
    code, data = run(capsys, "gui", "select", "demo", "block.NotAThing7")
    assert code == cli.USAGE
    code, data = run(capsys, "gui", "show", "demo", "block.Face3")
    assert code == cli.USAGE          # show/hide: whole bodies only


def test_cli_gui_exits_unchecked_when_no_workbench_is_running(runtime, demo, capsys):
    code, data = run(capsys, "gui", "state", "demo")
    assert code == cli.UNCHECKED
    assert "no workbench running (start it with: cad serve)" in data["error"]


def test_cli_gui_honors_cad_serve_url_override(bench_server, demo, monkeypatch, capsys):
    monkeypatch.setenv("CAD_SERVE_URL", bench_server.url)
    # no registry entry at all; the override must skip discovery entirely
    code, data = run(capsys, "gui", "state", "demo")
    assert code == cli.OK


# ─── cad gui run / cad gui commands ──────────────────────────────────────────

def test_cli_gui_run_sends_the_command_and_any_extra_args(bench_server, demo, capsys):
    bench_server.register()
    code, data = run(capsys, "gui", "run", "demo", "Std_ViewFitAll")
    assert code == cli.OK and data["clients"] == 0

    code, data = run(capsys, "gui", "run", "demo", "CADAgent_Frobnicate", "1", "two")
    assert code == cli.OK
    log = (demo / ".cad" / "log.jsonl").read_text()
    assert '"cmd": "gui.run"' in log and '"CADAgent_Frobnicate", "1", "two"' in log


def test_cli_gui_run_rejects_a_bad_command_name(bench_server, demo, capsys):
    bench_server.register()
    code, data = run(capsys, "gui", "run", "demo", "not a command")
    assert code == cli.USAGE and "command name" in data["error"]
    code, data = run(capsys, "gui", "run", "demo", "3Start")
    assert code == cli.USAGE and "command name" in data["error"]


def test_cli_gui_run_checks_the_published_list_once_the_ui_has_one(bench_server, demo, capsys):
    bench_server.register()
    # nothing published yet: an agent's guess is sent through regardless
    assert run(capsys, "gui", "run", "demo", "Std_Whatever")[0] == cli.OK

    bench_server.bench.gui_post("demo", {"commands": [
        {"name": "Std_ViewFitAll", "label": "Fit All", "enabled": True}]})
    code, data = run(capsys, "gui", "run", "demo", "Std_ViewFitAl")        # typo
    assert code == cli.USAGE and "Std_ViewFitAll" in data["error"]        # close match named
    code, data = run(capsys, "gui", "run", "demo", "Totally_Unknown")
    assert code == cli.USAGE and "Std_ViewFitAll" in data["error"]        # falls back to the list

    assert run(capsys, "gui", "run", "demo", "Std_ViewFitAll")[0] == cli.OK


def test_cli_gui_commands_lists_name_label_enabled(bench_server, demo, capsys):
    bench_server.register()
    code, data = run(capsys, "gui", "commands", "demo")
    assert code == cli.OK and data["commands"] == []

    bench_server.bench.gui_post("demo", {"commands": [
        {"name": "Std_ViewFitAll", "label": "Fit All", "enabled": True},
        {"name": "CADAgent_Frobnicate", "label": "Frobnicate", "enabled": False}]})
    code, data = run(capsys, "gui", "commands", "demo")
    assert code == cli.OK
    assert data["commands"] == [
        {"name": "Std_ViewFitAll", "label": "Fit All", "enabled": True},
        {"name": "CADAgent_Frobnicate", "label": "Frobnicate", "enabled": False}]


def test_cli_gui_run_and_commands_exit_unchecked_when_no_workbench_is_running(runtime, demo, capsys):
    code, data = run(capsys, "gui", "run", "demo", "Std_ViewFitAll")
    assert code == cli.UNCHECKED and "no workbench running" in data["error"]
    code, data = run(capsys, "gui", "commands", "demo")
    assert code == cli.UNCHECKED and "no workbench running" in data["error"]

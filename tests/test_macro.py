"""Macros: a text file of `cad` commands, saved/listed/replayed by `cad macro
...` and by the workbench's `/api/macro*` endpoints (serve.py / macro.py).

CLI-level tests go through `cli.main` in process (the `run()` helper from
test_cli, same as everywhere else). Server-level tests spin up a real HTTP
server over a `Bench` whose runner is an in-process `cli.main` call (like
test_workbench's `inproc`), except this one also keeps the JSON payload's
`"text"` field, since a macro run's report leans on it. `CAD_MACRO_DIR` is
set to a temp dir by the `macro_home` fixture in every test here, so nothing
touches the real `~/.cad-agent/macros`.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from cad_agent import cli, macro, serve
from test_cli import run
from test_gui import bench_server, runtime  # noqa: F401 (reused fixtures)
from test_workbench import demo, inproc  # noqa: F401 (reused fixtures)


@pytest.fixture()
def macro_home(tmp_path, monkeypatch):
    d = tmp_path / "macros"
    monkeypatch.setenv("CAD_MACRO_DIR", str(d))
    return d


# ─── macro.py: file management ───────────────────────────────────────────────

def test_macro_dir_honors_the_env_var(macro_home):
    assert macro.macro_dir() == macro_home


@pytest.mark.parametrize("bad", ["", " ", " Foo", "Foo ", "a/b", "../x", "a.b", "a\\b", "a:b"])
def test_validate_name_rejects_bad_names(macro_home, bad):
    with pytest.raises(ValueError):
        macro.validate_name(bad)


@pytest.mark.parametrize("good", ["Foo", "my macro 1", "a-b_c", "123"])
def test_validate_name_accepts_good_names(macro_home, good):
    assert macro.validate_name(good) == good


def test_save_list_read_round_trip(macro_home):
    assert macro.list_macros() == []
    p = macro.save_macro("Demo Macro", "# cad macro: Demo Macro\ncad status demo\n")
    assert p == macro_home / "Demo Macro.cad"
    rows = macro.list_macros()
    assert len(rows) == 1 and rows[0]["name"] == "Demo Macro" and rows[0]["lines"] == 2
    assert macro.read_macro("Demo Macro") == "# cad macro: Demo Macro\ncad status demo\n"
    # overwrite: save is create-or-overwrite
    macro.save_macro("Demo Macro", "cad status demo\n")
    assert macro.read_macro("Demo Macro") == "cad status demo\n"


def test_list_macros_is_sorted_and_empty_before_the_dir_exists(macro_home):
    assert not macro_home.exists()
    assert macro.list_macros() == []
    macro.save_macro("Zeta", "x\n")
    macro.save_macro("Alpha", "x\n")
    assert [r["name"] for r in macro.list_macros()] == ["Alpha", "Zeta"]


def test_read_missing_macro_names_the_real_ones(macro_home):
    macro.save_macro("One", "cad status demo\n")
    with pytest.raises(FileNotFoundError, match="One"):
        macro.read_macro("Nope")


def test_delete_rename_duplicate_round_trip(macro_home):
    macro.save_macro("A", "cad status demo\n")
    macro.duplicate_macro("A", "B")
    assert [r["name"] for r in macro.list_macros()] == ["A", "B"]
    assert macro.read_macro("B") == macro.read_macro("A")

    with pytest.raises(FileExistsError):
        macro.duplicate_macro("A", "B")

    macro.rename_macro("A", "C")
    assert [r["name"] for r in macro.list_macros()] == ["B", "C"]
    with pytest.raises(FileNotFoundError):
        macro.rename_macro("A", "Z")

    macro.delete_macro("B")
    assert [r["name"] for r in macro.list_macros()] == ["C"]
    with pytest.raises(FileNotFoundError):
        macro.delete_macro("B")


def test_rename_to_an_existing_name_fails_rename_to_itself_is_a_noop(macro_home):
    macro.save_macro("A", "x\n")
    macro.save_macro("B", "y\n")
    with pytest.raises(FileExistsError):
        macro.rename_macro("A", "B")
    assert macro.rename_macro("A", "A") == macro_home / "A.cad"
    with pytest.raises(FileExistsError):
        macro.duplicate_macro("A", "A")


# ─── macro.py: tokens() / run_lines() ────────────────────────────────────────

@pytest.mark.parametrize("line, want", [
    ("", None), ("   ", None), ("# a comment", None), ("   # also a comment", None),
    ("cad build demo plate", ["build", "demo", "plate"]),
    ("build demo plate", ["build", "demo", "plate"]),
    ("cad", None),
])
def test_tokens(line, want):
    assert macro.tokens(line) == want


def test_tokens_keeps_a_quoted_argument_together():
    assert macro.tokens('cad gui say demo "hello there"') == ["gui", "say", "demo", "hello there"]


def test_tokens_raises_on_unbalanced_quotes():
    with pytest.raises(ValueError):
        macro.tokens('cad gui say demo "unterminated')


def test_run_lines_skips_blanks_and_comments_and_stops_at_usage_or_crash():
    calls = []

    def exec_line(argv):
        calls.append(argv)
        return {"exit": {"a": 0, "b": 3, "c": 0}[argv[0]], "text": argv[0]}

    result = macro.run_lines(["a", "# comment", "", "b", "c"], exec_line)
    assert calls == [["a"], ["b"]]                      # c never runs
    assert result["exit"] == 3
    assert [r["line"] for r in result["ran"]] == ["a", "b"]
    assert [r["exit"] for r in result["ran"]] == [0, 3]


def test_run_lines_continues_past_fail_and_unchecked_and_fail_outranks_unchecked():
    def exec_line(argv):
        return {"exit": int(argv[0]), "text": ""}

    result = macro.run_lines(["0", "2", "1", "0"], exec_line)
    assert result["exit"] == cli.FAIL
    assert [r["exit"] for r in result["ran"]] == [0, 2, 1, 0]

    result = macro.run_lines(["0", "2", "0"], exec_line)
    assert result["exit"] == cli.UNCHECKED

    result = macro.run_lines(["0", "0"], exec_line)
    assert result["exit"] == cli.OK


def test_run_lines_a_bad_macro_line_stops_the_replay_as_usage():
    result = macro.run_lines(['cad gui say demo "unterminated', "cad status demo"],
                             lambda argv: pytest.fail("should never run"))
    assert result["exit"] == cli.USAGE and len(result["ran"]) == 1


# ─── CLI: cad macro ls/show/save/rm ──────────────────────────────────────────

def test_cli_macro_ls_save_show_rm(demo, macro_home, capsys, tmp_path):
    code, data = run(capsys, "macro", "ls")
    assert code == cli.OK and data["macros"] == []

    text = "# cad macro: Greet\ncad status demo\n"
    src = tmp_path / "Greet.src"
    src.write_text(text)
    code, data = run(capsys, "macro", "save", "Greet", str(src))
    assert code == cli.OK and data["path"] == str(macro_home / "Greet.cad")

    code, data = run(capsys, "macro", "ls")
    assert code == cli.OK and [m["name"] for m in data["macros"]] == ["Greet"]

    code, data = run(capsys, "macro", "show", "Greet")
    assert code == cli.OK and data["text"] == text

    code, data = run(capsys, "macro", "show", "Nope")
    assert code == cli.USAGE and "Nope" in data["error"]

    code, data = run(capsys, "macro", "rm", "Greet")
    assert code == cli.OK
    code, data = run(capsys, "macro", "ls")
    assert data["macros"] == []
    code, data = run(capsys, "macro", "rm", "Greet")
    assert code == cli.USAGE


def test_cli_macro_save_from_stdin(demo, macro_home, capsys, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("cad status demo\n"))
    code, data = run(capsys, "macro", "save", "FromStdin", "-")
    assert code == cli.OK
    assert macro.read_macro("FromStdin") == "cad status demo\n"


def test_cli_macro_save_rejects_a_bad_name_or_missing_file(demo, macro_home, capsys, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("cad status demo\n"))
    code, data = run(capsys, "macro", "save", "bad/name", "-")
    assert code == cli.USAGE and "bad/name" in data["error"]

    code, data = run(capsys, "macro", "save", "Ok", "/no/such/file.cad")
    assert code == cli.USAGE


# ─── CLI: cad macro run ──────────────────────────────────────────────────────

def test_cli_macro_run_executes_lines_in_order(demo, macro_home, capsys):
    macro.save_macro("Build", "# a header\n\ncad build demo plate\ncad status demo\n")
    code, data = run(capsys, "macro", "run", "Build")
    assert code == cli.OK and data["exit"] == cli.OK
    assert len(data["ran"]) == 2
    assert data["ran"][0]["line"] == "cad build demo plate" and data["ran"][0]["exit"] == cli.OK
    assert data["ran"][1]["line"] == "cad status demo" and data["ran"][1]["exit"] == cli.OK


def test_cli_macro_run_skips_blanks_and_comments(demo, macro_home, capsys):
    macro.save_macro("C", "# header\n\n   \ncad status demo\n# trailing\n")
    code, data = run(capsys, "macro", "run", "C")
    assert code == cli.OK and len(data["ran"]) == 1


def test_cli_macro_run_stops_at_a_usage_error_line(demo, macro_home, capsys):
    macro.save_macro("Bad", "cad build demo plate\ncad build demo nope\ncad status demo\n")
    code, data = run(capsys, "macro", "run", "Bad")
    assert code == cli.USAGE and data["exit"] == cli.USAGE
    assert len(data["ran"]) == 2                 # the third line never ran
    assert data["ran"][1]["exit"] == cli.USAGE


def test_cli_macro_run_continues_past_fail_and_unchecked(demo, macro_home, capsys, runtime):
    # plate and block overlap at their own origins (no --posed): FAIL.
    # a `cad gui` line with no workbench running: UNCHECKED, but the macro carries on.
    macro.save_macro("Mixed", "cad measure demo plate block\n"
                     "cad gui select demo plate\n"
                     "cad status demo\n")
    code, data = run(capsys, "macro", "run", "Mixed")
    assert code == cli.FAIL                      # FAIL outranks UNCHECKED
    assert [r["exit"] for r in data["ran"]] == [cli.FAIL, cli.UNCHECKED, cli.OK]
    assert "no workbench running" in data["ran"][1]["text"]


def test_cli_macro_run_unknown_name(demo, macro_home, capsys):
    code, data = run(capsys, "macro", "run", "Ghost")
    assert code == cli.USAGE and "Ghost" in data["error"]


def test_cli_macro_run_logs_itself_at_the_root_and_each_line_at_its_project(demo, macro_home, capsys):
    macro.save_macro("L", "cad status demo\n")
    run(capsys, "macro", "run", "L")
    root_log = (demo.parent / ".cad" / "log.jsonl").read_text()
    assert '"cmd": "macro run"' in root_log
    line_log = (demo / ".cad" / "log.jsonl").read_text()
    assert '"cmd": "status"' in line_log


def test_cli_macro_run_gui_line_reaches_a_running_workbench(demo, macro_home, capsys, bench_server):
    bench_server.register()
    macro.save_macro("WithGui", "cad gui select demo plate\ncad gui hide demo block\n")
    code, data = run(capsys, "macro", "run", "WithGui")
    assert code == cli.OK
    assert [r["exit"] for r in data["ran"]] == [cli.OK, cli.OK]
    state = bench_server.bench.gui_get("demo")
    assert state["selected"] == ["plate"] and state["hidden"] == ["block"]


def test_cli_macro_run_gui_run_line_reaches_a_running_workbench(demo, macro_home, capsys, bench_server):
    bench_server.register()
    macro.save_macro("RunIt", "cad gui run demo Std_ViewFitAll\n")
    code, data = run(capsys, "macro", "run", "RunIt")
    assert code == cli.OK and data["ran"][0]["exit"] == cli.OK
    log = (demo / ".cad" / "log.jsonl").read_text()
    assert '"cmd": "gui.run"' in log and '"Std_ViewFitAll"' in log


def test_cli_macro_run_gui_run_line_is_unchecked_without_a_workbench(demo, macro_home, capsys, runtime):
    # same as any other `cad gui` macro line (see test_cli_macro_run_continues_past_fail_and_unchecked):
    # no workbench to reach is UNCHECKED, not a usage error, so the next line still runs.
    macro.save_macro("RunIt", "cad gui run demo Std_ViewFitAll\ncad status demo\n")
    code, data = run(capsys, "macro", "run", "RunIt")
    assert code == cli.UNCHECKED
    assert [r["exit"] for r in data["ran"]] == [cli.UNCHECKED, cli.OK]
    assert "no workbench running" in data["ran"][0]["text"]


# ─── server: GET/POST /api/macro* ────────────────────────────────────────────

def _inproc_text(root, args):
    """Like test_workbench.inproc, but keeps the --with-text payload's "text"
    field too, since a macro run's report leans on each line's own text."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = cli.main(["--projects", str(root), "--json", *args])
    lines_ = [ln for ln in buf.getvalue().splitlines() if ln.startswith("{")]
    payload = json.loads(lines_[-1]) if lines_ else {}
    return {"exit": code, "data": payload.get("data", {}), "text": payload.get("text", ""), "stderr": ""}


@pytest.fixture()
def mserver(demo, macro_home):
    bench = serve.Bench([demo.parent], runner=_inproc_text)
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
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    yield call, bench
    srv.shutdown()
    srv.server_close()


def test_get_macros_empty_then_lists_after_a_save(mserver, macro_home):
    call, bench = mserver
    code, body = call("/api/macros")
    assert code == 200 and json.loads(body) == {"dir": str(macro_home), "macros": []}

    code, body = call("/api/macro", {"name": "Hello", "text": "cad status demo\n"})
    assert code == 200
    data = json.loads(body)
    assert data == {"name": "Hello", "path": str(macro_home / "Hello.cad")}

    code, body = call("/api/macros")
    macros = json.loads(body)["macros"]
    assert len(macros) == 1 and macros[0]["name"] == "Hello" and macros[0]["lines"] == 1

    code, body = call("/api/macro?name=Hello")
    assert code == 200 and json.loads(body)["text"] == "cad status demo\n"

    code, body = call("/api/macro?name=Nope")
    assert code == 404


def test_post_macro_requires_the_x_cad_header(mserver, macro_home):
    call, _ = mserver
    code, _ = call("/api/macro", {"name": "X", "text": "cad status demo\n"}, header=False)
    assert code == 403


def test_macro_rename_and_duplicate_endpoints(mserver, macro_home):
    call, _ = mserver
    call("/api/macro", {"name": "Hello", "text": "cad status demo\n"})
    code, body = call("/api/macro/duplicate", {"name": "Hello", "to": "Hello2"})
    assert code == 200 and json.loads(body)["name"] == "Hello2"
    code, body = call("/api/macro/rename", {"name": "Hello2", "to": "Hello3"})
    assert code == 200 and json.loads(body)["name"] == "Hello3"
    names = sorted(m["name"] for m in json.loads(call("/api/macros")[1])["macros"])
    assert names == ["Hello", "Hello3"]

    code, body = call("/api/macro/rename", {"name": "Hello", "to": "Hello3"})
    assert code == 400 and "Hello3" in json.loads(body)["error"]
    code, body = call("/api/macro/rename", {"name": "Hello", "to": "bad/name"})
    assert code == 400

    code, body = call("/api/macro/delete", {"name": "Hello3"})
    assert code == 200 and json.loads(body) == {"deleted": True}
    names = sorted(m["name"] for m in json.loads(call("/api/macros")[1])["macros"])
    assert names == ["Hello"]
    code, body = call("/api/macro/delete", {"name": "Nope"})
    assert code == 404


def test_macro_save_errors(mserver, macro_home):
    call, _ = mserver
    code, body = call("/api/macro", {"name": "bad/name", "text": "x\n"})
    assert code == 400
    code, body = call("/api/macro", {"name": "NoText"})
    assert code == 400 and "text must be a string" in json.loads(body)["error"]


def test_macro_run_http_runs_cad_and_gui_lines_against_the_bench(mserver, macro_home, demo):
    call, bench = mserver
    call("/api/macro", {"name": "Mix", "text": "cad build demo plate\n"
                        "cad gui select demo plate\n"
                        "cad gui hide demo block\n"
                        "cad status demo\n"})
    code, body = call("/api/macro/run", {"name": "Mix", "slug": "demo"})
    assert code == 200
    data = json.loads(body)
    assert data["exit"] == cli.OK
    assert [r["exit"] for r in data["ran"]] == [cli.OK] * 4
    state = bench.gui_get("demo")
    assert state["selected"] == ["plate"] and state["hidden"] == ["block"]
    log = (demo / ".cad" / "log.jsonl").read_text()
    assert '"cmd": "macro.run"' in log and '"Mix"' in log


def test_macro_run_http_runs_a_gui_run_line_against_the_bench(mserver, macro_home, demo):
    call, bench = mserver
    call("/api/macro", {"name": "RunCmd", "text": "cad gui run demo Std_ViewFitAll\n"
                        "cad gui run demo CADAgent_Frobnicate arg1\n"})
    code, body = call("/api/macro/run", {"name": "RunCmd", "slug": "demo"})
    data = json.loads(body)
    assert code == 200 and data["exit"] == cli.OK
    assert [r["exit"] for r in data["ran"]] == [cli.OK, cli.OK]
    log = (demo / ".cad" / "log.jsonl").read_text()
    assert '"cmd": "gui.run"' in log and '"CADAgent_Frobnicate", "arg1"' in log


def test_macro_run_http_without_slug_falls_back_to_the_first_root(mserver, macro_home):
    call, _ = mserver
    call("/api/macro", {"name": "NoSlug", "text": "cad status demo\n"})
    code, body = call("/api/macro/run", {"name": "NoSlug"})
    assert code == 200 and json.loads(body)["exit"] == cli.OK


def test_macro_run_http_unknown_slug_400s(mserver, macro_home):
    call, _ = mserver
    call("/api/macro", {"name": "M", "text": "cad status demo\n"})
    code, body = call("/api/macro/run", {"name": "M", "slug": "ghost"})
    assert code == 400


def test_macro_run_http_unknown_macro_404s(mserver, macro_home):
    call, _ = mserver
    code, body = call("/api/macro/run", {"name": "Ghost", "slug": "demo"})
    assert code == 404


def test_macro_run_http_stops_at_a_usage_line(mserver, macro_home):
    call, _ = mserver
    call("/api/macro", {"name": "Stop", "text": "cad status demo\n"
                        "cad build demo nope\ncad status demo\n"})
    code, body = call("/api/macro/run", {"name": "Stop", "slug": "demo"})
    data = json.loads(body)
    assert data["exit"] == cli.USAGE and len(data["ran"]) == 2

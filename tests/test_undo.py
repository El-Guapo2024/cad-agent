"""The undo/redo journal (undo.py) and the `cad set` / `cad place` / `cad
bought add-*` commands that write to it, plus `cad undo` / `cad redo` /
`cad history` and the matching workbench endpoints.

Unit tests drive undo.py directly against a bare tmp_path (no project, no
CAD kernel). CLI-level tests reuse test_workbench's `demo` fixture (plate +
block + assembly) through cli.main, the same way test_cli.py does. Server
tests reuse test_workbench's in-process `server` fixture (its runner,
`inproc`, calls cli.main directly in this process — good enough for most of
this file, but it cannot catch a bug in how the *real* server marks a command
"ui", since that has to cross a process boundary). The "real warm worker"
tests near the end reuse test_warm.py's `warm` fixture (an actual
`cad warm start` daemon) and go through `serve.Bench`'s default runner
(`cad_direct`) or `warm.run_captured` directly, the same code path
`cad serve` uses in production.
"""
from __future__ import annotations

import json

import pytest

from cad_agent import cli, undo as un
from cad_agent.verify import source_hash
from test_cli import run
from test_warm import warm  # noqa: F401 (reused fixture)
from test_workbench import demo, inproc, server  # noqa: F401 (reused fixtures)


@pytest.fixture(autouse=True)
def _no_actor_leak(monkeypatch):
    """Nothing in these tests should inherit CAD_ACTOR from a previous test
    or the real shell; each test sets it explicitly if it wants "ui"."""
    monkeypatch.delenv("CAD_ACTOR", raising=False)


# ─── undo.py: record / load / perform, no project involved ──────────────────

def test_actor_is_agent_unless_cad_actor_is_ui(monkeypatch):
    assert un.actor() == "agent"
    monkeypatch.setenv("CAD_ACTOR", "ui")
    assert un.actor() == "ui"
    monkeypatch.setenv("CAD_ACTOR", "something-else")
    assert un.actor() == "agent"


def test_load_is_empty_lists_when_nothing_was_ever_journaled(tmp_path):
    assert un.load(tmp_path) == {"undo": [], "redo": []}
    (tmp_path / ".cad").mkdir()
    (tmp_path / ".cad" / "undo.json").write_text("not json")
    assert un.load(tmp_path) == {"undo": [], "redo": []}


def test_record_writes_an_entry_and_clears_redo(tmp_path):
    files = [{"path": "a.txt", "before": "1", "after": "2"}]
    e = un.record(tmp_path, "Edit Parameters", "cad set demo a x=2", files)
    assert e["name"] == "Edit Parameters" and e["by"] == "agent" and e["files"] == files
    assert e["id"] and e["t"]
    data = un.load(tmp_path)
    assert data["undo"] == [e] and data["redo"] == []

    # fake a redo stack, then record a new change: it is cleared, like FreeCAD
    data["redo"] = [dict(e, id="stale")]
    (tmp_path / ".cad" / "undo.json").write_text(json.dumps(data))
    un.record(tmp_path, "Edit Parameters", "cad set demo a x=3",
              [{"path": "a.txt", "before": "2", "after": "3"}])
    assert un.load(tmp_path)["redo"] == []


def test_record_skips_a_true_noop(tmp_path):
    files = [{"path": "a.txt", "before": "same", "after": "same"}]
    assert un.record(tmp_path, "Placement", "cad place demo body --move=0,0,0", files) is None
    assert un.load(tmp_path) == {"undo": [], "redo": []}


def test_record_caps_the_undo_stack_at_max_steps(tmp_path):
    for i in range(un.MAX_STEPS + 5):
        un.record(tmp_path, "Edit Parameters", f"cad set demo a x={i}",
                  [{"path": "a.txt", "before": str(i), "after": str(i + 1)}])
    data = un.load(tmp_path)
    assert len(data["undo"]) == un.MAX_STEPS
    # the oldest were dropped: the stack holds the most recent MAX_STEPS
    assert data["undo"][0]["cmd"].endswith(f"x={5}")
    assert data["undo"][-1]["cmd"].endswith(f"x={un.MAX_STEPS + 4}")


def test_perform_undo_then_redo_round_trip(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("before")
    un.record(tmp_path, "Edit Parameters", "cad set demo a x=2",
              [{"path": "a.txt", "before": "before", "after": "before"}])  # no-op, skipped
    f.write_text("after")
    un.record(tmp_path, "Edit Parameters", "cad set demo a x=2",
              [{"path": "a.txt", "before": "before", "after": "after"}])

    r = un.perform(tmp_path, "undo")
    assert [e["cmd"] for e in r["applied"]] == ["cad set demo a x=2"] and r["blocked"] is None
    assert f.read_text() == "before"
    assert un.load(tmp_path) == {"undo": [], "redo": r["applied"]}

    r = un.perform(tmp_path, "redo")
    assert f.read_text() == "after" and r["blocked"] is None
    assert un.load(tmp_path)["redo"] == []


def test_perform_undo_of_a_file_that_did_not_exist_before_deletes_it(tmp_path):
    f = tmp_path / "bought" / "widget.py"
    f.parent.mkdir(parents=True)
    f.write_text("content")
    un.record(tmp_path, "Add Bought Part", "cad bought add-measured demo widget ...",
              [{"path": "bought/widget.py", "before": None, "after": "content"}])
    r = un.perform(tmp_path, "undo")
    assert not f.exists() and r["applied"]
    r = un.perform(tmp_path, "redo")
    assert f.read_text() == "content"


def test_perform_refuses_when_the_file_was_edited_since(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("after")
    un.record(tmp_path, "Edit Parameters", "cad set demo a x=2",
              [{"path": "a.txt", "before": "before", "after": "after"}])

    f.write_text("hand-edited")                       # break the undo check
    r = un.perform(tmp_path, "undo")
    assert r["applied"] == [] and "a.txt" in r["blocked"]["reason"]
    assert f.read_text() == "hand-edited"              # never clobbered
    assert len(un.load(tmp_path)["undo"]) == 1         # the entry is still there to inspect

    f.write_text("after")                              # put it back as the command left it
    r = un.perform(tmp_path, "undo")
    assert r["applied"] and r["blocked"] is None and f.read_text() == "before"

    f.write_text("hand-edited-again")                  # break the redo check
    r = un.perform(tmp_path, "redo")
    assert r["applied"] == [] and "a.txt" in r["blocked"]["reason"]
    assert f.read_text() == "hand-edited-again"


def test_perform_multistep_applies_what_it_can_then_stops_blocked(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("v0")
    for v in ("v0->v1", "v1->v2", "v2->v3"):
        before, after = v.split("->")
        f.write_text(after)
        un.record(tmp_path, "Edit Parameters", f"cad set demo a x={after}",
                  [{"path": "a.txt", "before": before, "after": after}])
    assert f.read_text() == "v3"
    r = un.perform(tmp_path, "undo", steps=10)       # only 3 entries exist
    assert len(r["applied"]) == 3 and r["blocked"] is None
    assert f.read_text() == "v0"


def test_perform_on_an_empty_stack_does_nothing(tmp_path):
    r = un.perform(tmp_path, "undo")
    assert r == {"applied": [], "blocked": None}


# ─── cad set / cad place / cad bought add-*: they journal, cad doesn't otherwise ──

def test_set_journals_edit_parameters_and_undo_redo_round_trip(demo, capsys):
    plate = demo / "parts" / "plate.py"
    code, data = run(capsys, "set", "demo", "plate", "thickness=6")
    assert code in (cli.OK, cli.UNCHECKED)
    j = un.load(demo)
    assert len(j["undo"]) == 1 and j["redo"] == []
    e = j["undo"][0]
    assert e["name"] == "Edit Parameters" and e["by"] == "agent"
    assert e["cmd"] == "cad set demo plate thickness=6"
    assert e["files"] == [{"path": "parts/plate.py", "before": e["files"][0]["before"],
                           "after": plate.read_text()}]
    assert '"thickness": 4.0' in e["files"][0]["before"]

    code, data = run(capsys, "undo", "demo")
    assert code == cli.OK and data["direction"] == "undo"
    assert '"thickness": 4.0' in plate.read_text()
    assert data["remaining"] == {"undo": 0, "redo": 1}
    assert data["follow_up"] and "part gates for plate" in data["follow_up"]

    code, data = run(capsys, "redo", "demo")
    assert code == cli.OK and '"thickness": 6.0' in plate.read_text()
    assert data["remaining"] == {"undo": 1, "redo": 0}


def test_set_with_no_real_change_is_not_journaled(demo, capsys):
    run(capsys, "set", "demo", "plate", "thickness=4")      # already 4.0
    assert un.load(demo) == {"undo": [], "redo": []}


def test_a_new_set_after_undo_clears_the_redo_stack(demo, capsys):
    run(capsys, "set", "demo", "plate", "thickness=6")
    run(capsys, "undo", "demo")
    assert len(un.load(demo)["redo"]) == 1
    run(capsys, "set", "demo", "plate", "depth=25")
    j = un.load(demo)
    assert j["redo"] == [] and len(j["undo"]) == 1 and j["undo"][0]["name"] == "Edit Parameters"


def test_place_journals_placement_and_undo_removes_the_entry(demo, capsys):
    code, data = run(capsys, "place", "demo", "block", "--move=5,0,0")
    assert code == cli.OK
    j = un.load(demo)
    assert len(j["undo"]) == 1
    e = j["undo"][0]
    assert e["name"] == "Placement" and e["cmd"] == "cad place demo block --move=5,0,0"
    assert e["files"] == [{"path": "placements.toml", "before": None,
                           "after": (demo / "placements.toml").read_text()}]

    code, data = run(capsys, "undo", "demo")
    assert code == cli.OK and not (demo / "placements.toml").exists()
    assert "fit check for block" in data["follow_up"]

    code, data = run(capsys, "redo", "demo")
    assert code == cli.OK and (demo / "placements.toml").exists()


def test_place_reset_is_journaled_too(demo, capsys):
    run(capsys, "place", "demo", "block", "--move=5,0,0")
    code, data = run(capsys, "place", "demo", "block", "--reset")
    assert code == cli.OK
    j = un.load(demo)
    assert len(j["undo"]) == 2
    e = j["undo"][-1]
    assert e["cmd"] == "cad place demo block --reset"
    assert e["files"][0]["after"] is None and not (demo / "placements.toml").exists()
    run(capsys, "undo", "demo")
    assert (demo / "placements.toml").exists()        # back to the --move state


def test_bought_add_measured_is_journaled_and_undo_deletes_the_file(demo, capsys):
    code, data = run(capsys, "bought", "add-measured", "demo", "motor",
                     "--size", "10", "10", "10", "--source", "datasheet")
    assert code == cli.OK
    j = un.load(demo)
    assert len(j["undo"]) == 1 and j["undo"][0]["name"] == "Add Bought Part"
    motor = demo / "bought" / "motor.py"
    assert j["undo"][0]["files"] == [{"path": "bought/motor.py", "before": None,
                                      "after": motor.read_text()}]
    run(capsys, "undo", "demo")
    assert not motor.exists()
    run(capsys, "redo", "demo")
    assert motor.exists()


def test_bought_add_step_journals_both_the_step_and_its_sidecar(demo, capsys, tmp_path):
    from build123d import Box, export_step
    src = tmp_path / "vendor.step"
    export_step(Box(5, 5, 5), str(src))
    code, data = run(capsys, "bought", "add-step", "demo", "widget", str(src),
                     "--source", "https://vendor.example")
    assert code == cli.OK
    j = un.load(demo)
    paths = {f["path"] for f in j["undo"][0]["files"]}
    assert paths == {"bought/widget.step", "bought/widget.json"}
    run(capsys, "undo", "demo")
    assert not (demo / "bought" / "widget.step").exists()
    assert not (demo / "bought" / "widget.json").exists()


def test_undo_refuses_a_hand_edited_file_and_does_not_clobber_it(demo, capsys):
    plate = demo / "parts" / "plate.py"
    run(capsys, "set", "demo", "plate", "thickness=6")
    hand_edit = plate.read_text().replace('"thickness": 6.0', '"thickness": 9.0')
    plate.write_text(hand_edit)
    code, data = run(capsys, "undo", "demo")
    assert code == cli.FAIL and "parts/plate.py" in data["error"]
    assert plate.read_text() == hand_edit                   # never clobbered
    assert len(un.load(demo)["undo"]) == 1                   # entry is not consumed


def test_redo_refuses_a_hand_edited_file(demo, capsys):
    plate = demo / "parts" / "plate.py"
    run(capsys, "set", "demo", "plate", "thickness=6")
    run(capsys, "undo", "demo")
    hand_edit = plate.read_text().replace('"thickness": 4.0', '"thickness": 5.5')
    plate.write_text(hand_edit)
    code, data = run(capsys, "redo", "demo")
    assert code == cli.FAIL and "parts/plate.py" in data["error"]
    assert plate.read_text() == hand_edit


def test_nothing_to_undo_or_redo_is_a_usage_error(demo, capsys):
    assert run(capsys, "undo", "demo")[0] == cli.USAGE
    assert run(capsys, "redo", "demo")[0] == cli.USAGE
    run(capsys, "set", "demo", "plate", "thickness=6")
    assert run(capsys, "redo", "demo")[0] == cli.USAGE       # nothing undone yet


def test_steps_flag_moves_several_at_once(demo, capsys):
    run(capsys, "set", "demo", "plate", "thickness=6")
    run(capsys, "set", "demo", "plate", "depth=25")
    code, data = run(capsys, "undo", "demo", "--steps", "2")
    assert code == cli.OK and len(data["applied"]) == 2
    plate = (demo / "parts" / "plate.py").read_text()
    assert '"thickness": 4.0' in plate and '"depth": 20.0' in plate
    assert run(capsys, "undo", "demo", "--steps", "0")[0] == cli.USAGE


def test_cad_history_lists_both_stacks_newest_first(demo, capsys):
    run(capsys, "set", "demo", "plate", "thickness=6")
    run(capsys, "place", "demo", "block", "--move=5,0,0")
    run(capsys, "undo", "demo")
    code, data = run(capsys, "history", "demo")
    assert code == cli.OK
    assert [r["name"] for r in data["undo"]] == ["Edit Parameters"]
    assert [r["name"] for r in data["redo"]] == ["Placement"]
    assert all({"id", "name", "by", "t"} == set(r) for r in data["undo"] + data["redo"])


def test_undo_json_is_outside_source_hash(demo, capsys):
    # verify.DESIGN (what `cad verify`/`cad done` hash) lists parts, assembly,
    # spec, placements, bought and approved renders only — .cad/ is not in it,
    # so the journal can never flip a verdict.
    before, n_before = source_hash(demo)
    (demo / ".cad").mkdir(exist_ok=True)
    (demo / ".cad" / "undo.json").write_text(json.dumps({"undo": [{"fake": True}], "redo": []}))
    after, n_after = source_hash(demo)
    assert before == after and n_before == n_after

    run(capsys, "set", "demo", "plate", "thickness=6")   # writes parts/plate.py *and* .cad/undo.json
    assert (demo / ".cad" / "undo.json").exists()
    h1, _ = source_hash(demo)
    (demo / ".cad" / "undo.json").write_text("{}")        # touch the journal again
    h2, _ = source_hash(demo)
    assert h1 == h2                                       # the journal never moves the hash


def test_macro_run_journals_one_entry_per_line(demo, capsys):
    from cad_agent import macro
    macro.save_macro("Bump", "cad set demo plate thickness=6\n"
                             "cad place demo block --move=5,0,0\n")
    code, data = run(capsys, "macro", "run", "Bump")
    assert code in (cli.OK, cli.UNCHECKED)       # `set`'s own verdict may be UNCHECKED (no baseline)
    j = un.load(demo)
    assert [e["name"] for e in j["undo"]] == ["Edit Parameters", "Placement"]
    # undoing once only reverts the macro's last line, same as if it had been typed by hand
    run(capsys, "undo", "demo")
    assert not (demo / "placements.toml").exists()
    assert '"thickness": 6.0' in (demo / "parts" / "plate.py").read_text()


# ─── the workbench: CAD_ACTOR=ui, GET /api/history, POST /api/undo /api/redo ──

def test_server_set_is_journaled_as_ui(server, demo):
    call, bench, _ = server
    assert un.load(demo) == {"undo": [], "redo": []}
    call("/api/set", {"slug": "demo", "part": "block", "values": {"size": 12}})
    j = un.load(demo)
    assert len(j["undo"]) == 1 and j["undo"][0]["by"] == "ui"


def test_cli_set_outside_the_server_is_journaled_as_agent(demo, capsys):
    run(capsys, "set", "demo", "plate", "thickness=6")
    assert un.load(demo)["undo"][0]["by"] == "agent"


def test_get_api_history(server, demo, capsys):
    call, bench, _ = server
    run(capsys, "set", "demo", "plate", "thickness=6")       # agent, straight through the CLI
    call("/api/place", {"slug": "demo", "body": "block", "move": [5, 0, 0],
                        "turn": [0, 0, 0], "about": [0, 0, 20]})
    code, body = call("/api/history?slug=demo")
    data = json.loads(body)
    assert code == 200
    assert [r["name"] for r in data["undo"]] == ["Placement", "Edit Parameters"]
    assert data["undo"][0]["by"] == "ui" and data["undo"][1]["by"] == "agent"
    assert data["redo"] == []


def test_post_api_undo_and_redo(server, demo):
    call, bench, _ = server
    call("/api/set", {"slug": "demo", "part": "block", "values": {"size": 12}})
    code, body = call("/api/undo", {"slug": "demo"})
    r = json.loads(body)
    assert code == 200 and r["exit"] == cli.OK
    assert '"size": 10.0' in (demo / "parts" / "block.py").read_text()

    code, body = call("/api/redo", {"slug": "demo", "steps": 1})
    r = json.loads(body)
    assert code == 200 and r["exit"] == cli.OK
    assert '"size": 12.0' in (demo / "parts" / "block.py").read_text()


def test_post_api_undo_with_nothing_to_undo_reports_usage_exit(server, demo):
    call, bench, _ = server
    code, body = call("/api/undo", {"slug": "demo"})
    r = json.loads(body)
    assert code == 200 and r["exit"] == cli.USAGE            # the HTTP call still succeeds


def test_watcher_broadcasts_history_on_journal_changes(demo, capsys):
    from cad_agent import serve
    bench = serve.Bench([demo.parent], runner=inproc)
    got = []
    bench.broadcast = got.append
    bench.scan(announce=False)
    run(capsys, "set", "demo", "plate", "thickness=6")
    bench.scan()
    kinds = [e["type"] for e in got]
    assert "history" in kinds and "design" in kinds


# ─── the real warm worker: a live bug caught here (by="agent" through the ────
# server's actual cad_direct -> warm.run_captured -> socket -> fork path,
# because CAD_ACTOR set in *this* process's environment never reaches a fork
# of the long-lived daemon — it inherits the daemon's own environment from
# whenever that process started, not a client's). cli.py's --actor flag rides
# in `argv` instead, which the socket protocol already carries end to end,
# and which a forked child always re-parses fresh (it re-imports cli.py from
# disk every time; only warm.py's own module-level state, like a stale
# ENV_PASS, would be frozen at the daemon's start). The tests above, through
# `inproc`, cannot see this class of bug: they never cross a process boundary.

def test_bench_cad_marks_entries_ui_through_the_real_warm_worker(warm, monkeypatch):
    """The exact path a live workbench uses: Bench.cad() with its default
    runner (serve.cad_direct) against a real `cad warm start` daemon."""
    from cad_agent import serve
    cad, root = warm
    monkeypatch.setenv("CAD_WARM_DIR", cad.env["CAD_WARM_DIR"])
    monkeypatch.delenv("CAD_PROJECTS", raising=False)
    bench = serve.Bench([root])          # default runner: serve.cad_direct, the real thing
    r = bench.cad("demo", "set", ["set", "demo", "plate", "thickness=11"])
    assert r["exit"] in (cli.OK, cli.UNCHECKED), r
    j = un.load(root / "demo")
    assert j["undo"] and j["undo"][-1]["by"] == "ui"
    assert '"thickness": 11.0' in (root / "demo" / "parts" / "plate.py").read_text()


def test_plain_warm_call_without_actor_flag_is_still_agent(warm, monkeypatch):
    """Same real socket, no --actor flag: an agent's `cad set` from a
    terminal, which must not come out marked "ui"."""
    from cad_agent import warm as w
    cad, root = warm
    monkeypatch.setenv("CAD_WARM_DIR", cad.env["CAD_WARM_DIR"])
    code, out, err = w.run_captured(
        ["--projects", str(root), "--json", "set", "demo", "plate", "thickness=12"])
    assert code in (cli.OK, cli.UNCHECKED), err
    j = un.load(root / "demo")
    assert j["undo"][-1]["by"] == "agent"


def test_max_undo_size_preference_caps_the_journal(tmp_path, capsys):
    # Preferences > Document "Maximum undo/redo steps" (MaxUndoSize), via `cad pref`.
    code, data = run(capsys, "pref", "MaxUndoSize", "3")
    assert code == 0 and data["prefs"] == {"MaxUndoSize": 3}
    for i in range(6):
        un.record(tmp_path, "Edit Parameters", f"cad set demo a x={i}",
                  [{"path": "a.txt", "before": str(i), "after": str(i + 1)}])
    assert [e["cmd"][-3:] for e in un.load(tmp_path)["undo"]] == ["x=3", "x=4", "x=5"]
    # 0 keeps nothing, as FreeCAD's 0 turns undo off
    run(capsys, "pref", "MaxUndoSize", "0")
    un.record(tmp_path, "Edit Parameters", "cad set demo a x=9", [{"path": "a.txt", "before": "9", "after": "10"}])
    assert un.load(tmp_path)["undo"] == []


def test_pref_rejects_unknown_keys_and_clamps_to_the_spin_box(capsys):
    code, _ = run(capsys, "pref", "Bogus", "1")
    assert code != 0
    _, data = run(capsys, "pref", "MaxUndoSize", "500")
    assert data["prefs"]["MaxUndoSize"] == 99
    _, data = run(capsys, "pref")
    assert data["prefs"]["MaxUndoSize"] == 99


def test_the_page_reads_and_writes_the_same_preferences(server, capsys):
    call, _, _ = server
    code, body = call("/api/pref", {"key": "MaxUndoSize", "value": 7})
    assert code == 200 and json.loads(body)["prefs"]["MaxUndoSize"] == 7
    assert json.loads(call("/api/prefs")[1])["prefs"]["MaxUndoSize"] == 7
    _, data = run(capsys, "pref", "MaxUndoSize")
    assert data["prefs"] == {"MaxUndoSize": 7}
    assert call("/api/pref", {"key": "Nope", "value": 1})[0] == 400

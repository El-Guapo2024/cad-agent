"""cad eval: the tasks in evals/ and the scoring around them.

The grading rules are tested on hand-made verify records, which needs no kernel. The tasks are
tested for real: every reference design must score 100% through the same code `cad eval score`
runs, and a small edit to each must fail on the rule it should. That verifies a scratch copy in a
fresh process, through a warm worker kept in a temporary CAD_WARM_DIR and stopped at the end, so
the first score pays one kernel import and each later one a few seconds.
"""
import json
import shlex
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from cad_agent import cli, evals
from cad_agent import state as st
from test_cli import run

REPO = Path(__file__).resolve().parent.parent
EVALS = REPO / "evals"
TASKS = ("nema17_mount", "syringe_clamp", "galvo_mount")

# What each hidden spec adds to the usual rows, as the rules a score has to contain.
SPEC_RULES = {
    "nema17_mount": {"spec/envelope", "spec/size", "spec/position", "spec/clearance",
                     "spec/interface", "spec/mass"},
    "syringe_clamp": {"spec/envelope", "spec/size", "spec/position", "spec/clearance",
                      "spec/interface", "spec/mass"},
    "galvo_mount": {"spec/envelope", "spec/size", "spec/position", "spec/clearance",
                    "spec/interface", "spec/mass", "spec/keepout"},
}

# One small edit to each reference, and the rule it has to break.
BROKEN = {
    "nema17_mount": ("parts/bracket.py", '"motor_pitch": 31.0', '"motor_pitch": 30.0', "spec/interface"),
    "syringe_clamp": ("parts/syringe_clamp.py", '"fit": 0.4', '"fit": 1.0', "spec/clearance"),
    "galvo_mount": ("parts/galvo_mount.py", '"column_x": 112.0', '"column_x": 80.0', "spec/keepout"),
}


@pytest.fixture(scope="module")
def worker(tmp_path_factory):
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("CAD_WARM_DIR", str(tmp_path_factory.mktemp("warm")))
        for var in ("CAD_WARM", "CAD_PROJECTS", "CAD_EVALS"):
            mp.delenv(var, raising=False)
        yield
        subprocess.run([sys.executable, "-m", "cad_agent.warm", "warm", "stop"],
                       capture_output=True, timeout=60)


@pytest.fixture(autouse=True)
def _scratch_root(tmp_path, monkeypatch):
    """The CLI logs every command under the projects root: keep that off the repo's projects/."""
    monkeypatch.setattr(st, "ROOT", tmp_path / "projects")


@pytest.fixture(scope="module")
def reference(worker):
    """Each task's reference, scored once and shared by the tests that read the result."""
    cache = {}

    def score(task):
        if task not in cache:
            cache[task] = evals.score(evals.get_task(EVALS, task), EVALS / task / "reference",
                                      show_all=True)
        return cache[task]
    return score


def copy_reference(task, dest):
    shutil.copytree(EVALS / task / "reference", dest)
    return dest


# ─── The tasks ───────────────────────────────────────────────────────────────

def test_ls_and_brief_describe_every_task(capsys):
    code, data = run(capsys, "eval", "ls", "--evals", str(EVALS))
    assert code == cli.OK
    assert run(capsys, "eval", "--evals", str(EVALS), "ls")[1] == data      # before the action works too
    rows = {r["task"]: r for r in data["tasks"]}
    assert set(TASKS) <= set(rows)
    for task in TASKS:
        assert rows[task]["title"].startswith(task) and rows[task]["given"] and rows[task]["reference"]
    code, data = run(capsys, "eval", "brief", "nema17_mount", "--evals", str(EVALS))
    assert code == cli.OK and data["given"] == rows["nema17_mount"]["given"]
    assert data["brief"] == (EVALS / "nema17_mount" / "brief.md").read_text()
    cli.main(["eval", "brief", "nema17_mount", "--evals", str(EVALS)])
    out = capsys.readouterr().out
    assert out.startswith("# nema17_mount:")
    assert out.endswith("given files, laid into projects/nema17_mount/:\n"
                        "  bought/nema17_motor.json\n  bought/nema17_motor.step\n")


@pytest.mark.parametrize("task", TASKS)
def test_the_brief_states_everything_the_hidden_spec_checks(task):
    """No gotchas: every body and part module the spec names, every given file, and every
    number the spec holds a design to, are in the brief the agent gets."""
    brief = (EVALS / task / "brief.md").read_text()
    spec = tomllib.loads((EVALS / task / "spec.toml").read_text())

    def triple(values):
        return " x ".join(f"{v:g}" for v in values)

    names = set()
    for kind in ("size", "position"):
        names |= {e["body"] for e in spec.get(kind, [])}
    for kind in ("clearance", "interface"):
        for e in spec.get(kind, []):
            names |= {e["a"], e["b"]}
    for e in spec.get("keepout", []):
        names |= set(e["clear"])
    for e in spec.get("mass", []):
        names |= set(e["parts"])
    for name in sorted(names):
        assert f"`{name}`" in brief, f"{task}: the brief never names `{name}`"
    for path in (EVALS / task / "given").rglob("*"):
        if path.is_file() and path.suffix != ".json":
            assert path.relative_to(EVALS / task / "given").as_posix() in brief
    assert "laid again" in brief and "own `spec.toml`" in brief

    assert triple(spec["envelope"]["max_mm"]) in brief
    for e in spec.get("size", []):          # a pin states its nominal size, a floor its floor
        lo, hi = e.get("min_mm"), e.get("max_mm")
        assert triple([(a + b) / 2 for a, b in zip(lo, hi)] if lo and hi else lo or hi) in brief, e
    for e in spec.get("position", []):
        assert "(" + ", ".join(f"{v:g}" for v in e["center_mm"]) + ")" in brief, e
    for e in spec.get("clearance", []):
        for key in ("min_mm", "max_mm"):
            assert key not in e or f"{e[key]:g}" in brief, e
    for e in spec.get("keepout", []):
        assert all(f"{v:g}" in brief for v in e["params"].values()), e
    for e in spec.get("mass", []):
        assert f"{e['max_g']:g} g" in brief, e


@pytest.mark.parametrize("task", TASKS)
def test_a_task_is_complete(task):
    root = EVALS / task
    assert (root / "brief.md").is_file() and (root / "spec.toml").is_file()
    assert (root / "reference" / "assembly.py").is_file()
    assert list((root / "reference" / "parts").glob("*.py"))
    for sidecar in (root / "given" / "bought").glob("*.step"):       # a bought part says where it came from
        assert json.loads(sidecar.with_suffix(".json").read_text())["source"].strip()


def test_unknown_tasks_and_a_missing_agent_are_usage_errors(capsys, tmp_path):
    for argv in (["eval", "brief", "nope"], ["eval", "score", "nope", str(tmp_path)],
                 ["eval", "run", "--agent", "true", "nope"], ["eval", "run"],
                 ["eval", "score", "nema17_mount", str(tmp_path / "absent")],
                 ["eval", "ls", "--evals", str(tmp_path / "absent")]):
        code, data = run(capsys, *argv)
        assert code == cli.USAGE and data["error"], argv
    code, data = run(capsys, "eval", "run")
    assert "--agent" in data["error"]


def test_the_tasks_folder_comes_from_the_flag_then_the_environment_then_the_repo(monkeypatch, tmp_path):
    monkeypatch.delenv("CAD_EVALS", raising=False)
    assert evals.tasks_dir() == EVALS
    monkeypatch.setenv("CAD_EVALS", str(tmp_path / "env"))
    assert evals.tasks_dir() == (tmp_path / "env").resolve()
    assert evals.tasks_dir(str(tmp_path / "flag")) == (tmp_path / "flag").resolve()


def test_results_stay_out_of_git():
    assert "evals/results/" in (REPO / ".gitignore").read_text().splitlines()


# ─── Laying the project that gets graded ─────────────────────────────────────

def test_the_graded_project_has_the_given_files_and_the_hidden_spec(tmp_path):
    task = evals.get_task(EVALS, "nema17_mount")
    design = copy_reference("nema17_mount", tmp_path / "design")
    (design / "bought").mkdir()
    (design / "bought" / "nema17_motor.step").write_text("a smaller motor")           # tampered
    (design / "bought" / "nema17_motor.json").write_text('{"source": "my own"}')
    (design / "spec.toml").write_text("[envelope]\nmax_mm = [1000, 1000, 1000]\n")     # the agent's own
    (design / "placements.toml").write_text("")
    for dropped in ("out", ".cad", "baseline", "parts/__pycache__"):
        (design / dropped).mkdir(exist_ok=True)
        (design / dropped / "x").write_text("x")
    for dropped in ("checks.json", "verify.json"):
        (design / dropped).write_text("{}")
    project = tmp_path / "graded"
    evals.lay(task, design, project)
    given = task.path / "given" / "bought"
    for name in ("nema17_motor.step", "nema17_motor.json"):
        assert (project / "bought" / name).read_bytes() == (given / name).read_bytes()
    assert (project / "spec.toml").read_bytes() == (task.path / "spec.toml").read_bytes()
    assert (project / "assembly.py").is_file() and (project / "parts" / "bracket.py").is_file()
    assert (project / "placements.toml").is_file()                 # a design input, so it is kept
    for dropped in ("out", ".cad", "baseline", "checks.json", "verify.json", "parts/__pycache__"):
        assert not (project / dropped).exists(), dropped


def test_a_given_file_the_agent_deleted_comes_back(tmp_path):
    task = evals.get_task(EVALS, "galvo_mount")
    project = tmp_path / "graded"
    evals.lay(task, copy_reference("galvo_mount", tmp_path / "design"), project)
    assert sorted(p.name for p in (project / "bought").iterdir()) == ["galvo_head.json", "galvo_head.step"]


# ─── Grading: what a verify record is worth ──────────────────────────────────

def row(rule, state, subject="x", check="spec"):
    return {"subject": subject, "check": check, "rule": rule, "state": state,
            "measured": "m", "limit": "l", "source": "s", "artifacts": []}


def record(rows, fresh=True, notes=(), parts_failed=0):
    return {"rows": rows, "process": {"fresh": fresh, "mode": "warm-fork"}, "notes": list(notes),
            "summary": {"parts_failed": parts_failed}}


def test_render_rows_and_n_a_do_not_count():
    g = evals.grade(record([row("spec/size", "PASS"), row("fit", "PASS"),
                            row("drift/iso", "UNCHECKED"), row("extent/iso", "FAIL"),
                            row("visual/iso", "UNCHECKED"), row("moved", "N/A"),
                            row("silhouette/iso", "PASS")]))
    assert (g["verdict"], g["score"], g["graded"], g["passed"]) == ("PASS", 1.0, 3, 3)
    assert (g["skipped"], g["na"]) == (3, 1)


def test_the_score_is_passed_over_graded_and_a_fail_or_unchecked_row_blocks_a_pass():
    one_fail = evals.grade(record([row("a", "PASS")] * 3 + [row("b", "FAIL")]))
    assert (one_fail["verdict"], one_fail["score"], one_fail["passed"], one_fail["graded"]) == \
        ("FAIL", 0.75, 3, 4)
    unchecked = evals.grade(record([row("a", "PASS"), row("b", "UNCHECKED")]))
    assert (unchecked["verdict"], unchecked["score"]) == ("UNCHECKED", 0.5)
    both = evals.grade(record([row("a", "UNCHECKED"), row("b", "FAIL")]))
    assert both["verdict"] == "FAIL"                         # FAIL outranks UNCHECKED, as in cad verify


def test_a_record_that_cannot_be_trusted_is_never_a_pass():
    green = [row("a", "PASS")]
    stale = evals.grade(record(green, fresh=False))
    assert stale["verdict"] == "UNCHECKED" and stale["score"] == 1.0 and "fresh" in stale["notes"][0]
    moved = evals.grade(record(green, notes=["the design changed while it was being verified; run again"]))
    assert moved["verdict"] == "UNCHECKED" and "changed while" in moved["notes"][0]
    assert evals.grade(record([]))["verdict"] == "UNCHECKED"             # nothing was judged


def test_a_part_that_did_not_build_is_a_failed_row():
    g = evals.grade(record([row("a", "PASS")], parts_failed=1), {"bracket": "ValueError: no wall"})
    assert g["verdict"] == "FAIL" and (g["passed"], g["graded"]) == (1, 2)
    assert g["rows"][-1]["subject"] == "bracket" and "no wall" in g["rows"][-1]["measured"]
    unnamed = evals.grade(record([row("a", "PASS")], parts_failed=2))
    assert unnamed["verdict"] == "FAIL" and "2 part(s)" in unnamed["rows"][-1]["measured"]


def test_a_verify_that_did_not_finish_scores_zero():
    g = evals.grade({"error": "cad verify did not finish (exit 4): KeyError: 'x'"})
    assert (g["verdict"], g["score"], g["passed"]) == ("FAIL", 0.0, 0) and "KeyError" in g["rows"][0]["measured"]


def test_placeholders_are_quoted_and_other_braces_left_alone():
    cmd = evals.fill('claude -p "$(cat {brief})" --add-dir {dir} # {task} ${HOME} {root}',
                     brief=Path("/a b/BRIEF.md"), dir=Path("/a b/p"), task="t", root=Path("/a b"))
    assert cmd == "claude -p \"$(cat '/a b/BRIEF.md')\" --add-dir '/a b/p' # t ${HOME} '/a b'"


# ─── Scoring for real ────────────────────────────────────────────────────────

@pytest.mark.parametrize("task", TASKS)
def test_the_reference_scores_full_marks(reference, task):
    r = reference(task)
    assert r["verdict"] == "PASS" and r["score"] == 1.0, [x for x in r["rows"] if x["state"] != "PASS"]
    assert r["graded"] == r["passed"] >= 20 and r["skipped"] >= 1
    assert SPEC_RULES[task] <= {x["rule"] for x in r["rows"]}
    assert not r["notes"] and r["verify_seconds"] is not None


@pytest.mark.parametrize("task", TASKS)
def test_a_small_edit_to_the_reference_fails_on_the_rule_it_should(worker, tmp_path, capsys, task):
    rel, old, new, rule = BROKEN[task]
    design = copy_reference(task, tmp_path / "design")
    text = (design / rel).read_text()
    assert old in text
    (design / rel).write_text(text.replace(old, new))
    code, r = run(capsys, "eval", "score", task, str(design), "--evals", str(EVALS))
    assert code == cli.FAIL and r["verdict"] == "FAIL" and 0.5 < r["score"] < 1.0
    assert {x["rule"] for x in r["rows"]} == {rule}              # nothing else broke, only that rule
    assert all(x["state"] == "FAIL" for x in r["rows"])


def test_tampering_with_a_given_file_or_the_spec_gains_nothing(worker, tmp_path, capsys):
    task = evals.get_task(EVALS, "nema17_mount")
    design = copy_reference("nema17_mount", tmp_path / "design")
    (design / "bought").mkdir()
    (design / "bought" / "nema17_motor.step").write_text("not a step file")
    (design / "bought" / "nema17_motor.json").write_text("{}")
    (design / "spec.toml").write_text("[envelope]\nmax_mm = [1, 1, 1]\n")      # fails if it is ever read
    code, r = run(capsys, "eval", "score", task.name, str(design), "--keep", "--evals", str(EVALS))
    kept = Path(r["kept"])
    try:
        assert code == cli.OK and r["verdict"] == "PASS" and r["score"] == 1.0
        project = kept / "projects" / task.name
        assert (project / "spec.toml").read_bytes() == (task.path / "spec.toml").read_bytes()
        assert (project / "bought" / "nema17_motor.step").read_bytes() == \
            (task.path / "given" / "bought" / "nema17_motor.step").read_bytes()
        assert (design / "bought" / "nema17_motor.step").read_text() == "not a step file"   # theirs untouched
    finally:
        shutil.rmtree(kept, ignore_errors=True)


# ─── Running an agent ────────────────────────────────────────────────────────

@pytest.fixture()
def mini(tmp_path):
    """A task with nothing to design, so a run through it costs one near-empty verify."""
    root = tmp_path / "evals"
    (root / "mini" / "given" / "bought").mkdir(parents=True)
    (root / "mini" / "brief.md").write_text("# mini: nothing to do\n\nBe brief.\n")
    (root / "mini" / "spec.toml").write_text("[envelope]\nmax_mm = [10, 10, 10]\n")
    (root / "mini" / "given" / "bought" / "thing.txt").write_text("given\n")
    return root


def test_the_agent_runs_in_a_git_repo_with_the_brief_and_the_given_files(worker, mini, capsys):
    probe = ("test -f {brief} && test -f {dir}/bought/thing.txt && test {task} = mini && "
             'test "$CAD_PROJECTS" = {root}/projects && test "$PWD" = {root} && '
             'test -z "$(git -C {root} status --porcelain)" && '
             'test "$(git -C {root} rev-list --count HEAD)" = 1 && '
             "cmp {brief} " + shlex.quote(str(mini / "mini" / "brief.md")))
    out = mini / "out" / "results.json"
    code, r = run(capsys, "eval", "run", "--agent", probe, "--evals", str(mini), "--keep",
                  "--out", str(out), "--timeout", "120")
    (t,) = r["tasks"]
    agent_dir, scratch = Path(t["agent_dir"]), Path(t["kept"])        # --keep keeps both
    try:
        assert t["agent_exit"] == 0 and not t["timed_out"], t["agent_tail"]
        assert t["task"] == "mini" and code == cli.UNCHECKED and t["verdict"] == "UNCHECKED"
        assert r["file"] == str(out) and json.loads(out.read_text())["tasks"][0]["task"] == "mini"
        assert (agent_dir / "repo" / ".gitignore").is_file()
        assert (scratch / "projects" / "mini" / "spec.toml").is_file()
    finally:
        shutil.rmtree(agent_dir, ignore_errors=True)
        shutil.rmtree(scratch, ignore_errors=True)


def test_results_go_to_a_dated_file_next_to_the_tasks_by_default(worker, mini, capsys):
    code, r = run(capsys, "eval", "run", "--agent", "true", "--evals", str(mini))
    path = Path(r["file"])
    assert path.parent == mini / "results" and path.suffix == ".json" and path.is_file()
    assert json.loads(path.read_text())["summary"] == r["summary"]
    assert r["summary"]["tasks"] == 1 and r["summary"]["pass"] == 0


def test_an_agent_that_runs_out_of_time_is_killed_and_what_it_left_is_scored(worker, mini, capsys):
    code, r = run(capsys, "eval", "run", "--agent", "sleep 60", "--timeout", "1", "--evals", str(mini))
    (t,) = r["tasks"]
    assert t["timed_out"] and t["agent_seconds"] < 30 and t["verdict"] != "PASS"


def test_an_agent_that_copies_the_reference_scores_pass_and_one_that_does_nothing_does_not(
        worker, tmp_path, capsys):
    ref = EVALS / "nema17_mount" / "reference"
    copy = f"cp -R {shlex.quote(str(ref))}/. {{dir}}/"
    code, r = run(capsys, "eval", "run", "--agent", copy, "--evals", str(EVALS),
                  "--out", str(tmp_path / "copy.json"), "nema17_mount")
    (t,) = r["tasks"]
    assert code == cli.OK and t["verdict"] == "PASS" and t["score"] == 1.0 and t["agent_exit"] == 0
    assert r["summary"] == {"tasks": 1, "pass": 1, "mean_score": 1.0}

    nothing = tmp_path / "nothing.json"                 # no --json this time: the table a person reads
    code = cli.main(["eval", "run", "--agent", "true", "--evals", str(EVALS), "--out", str(nothing),
                     "nema17_mount"])
    table = capsys.readouterr().out
    saved = json.loads(nothing.read_text())
    (t,) = saved["tasks"]
    assert code == cli.UNCHECKED and t["verdict"] == "UNCHECKED" and t["score"] < 0.2
    assert saved["summary"]["pass"] == 0
    assert "nema17_mount" in table and "UNCHECKED" in table and "mean score" in table

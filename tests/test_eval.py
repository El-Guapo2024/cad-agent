"""cad eval: the tasks in evals/ and the scoring around them.

The grading rules are tested on hand-made verify records, which needs no kernel. The tasks are
tested for real: every reference design must score 100% through the same code `cad eval score`
runs, and a small edit to each must fail on the rule it should. That verifies a scratch copy in a
fresh process, through a warm worker kept in a temporary CAD_WARM_DIR and stopped at the end, so
the first score pays one kernel import and each later one a few seconds.
"""
import json
import re
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
TASKS = ("nema17_mount", "syringe_clamp", "galvo_mount", "mgn12h_carriage", "hotplate_standoffs",
         "pinned_carrier", "laser_panel", "pcb_enclosure", "idler_bracket", "endstop_bracket",
         "dock_material", "beam_deflection")

# What each hidden spec adds to the usual rows, as the rules a score has to contain.
SPEC_RULES = {
    "nema17_mount": {"spec/envelope", "spec/size", "spec/position", "spec/clearance",
                     "spec/interface", "spec/mass"},
    "syringe_clamp": {"spec/envelope", "spec/size", "spec/position", "spec/clearance",
                      "spec/interface", "spec/mass", "spec/shaft_fit"},
    "galvo_mount": {"spec/envelope", "spec/size", "spec/position", "spec/clearance",
                    "spec/interface", "spec/mass", "spec/keepout"},
    "mgn12h_carriage": {"spec/size", "spec/position", "spec/clearance", "spec/interface", "spec/mass",
                        "spec/axis", "spec/bodies"},
    "hotplate_standoffs": {"spec/envelope", "spec/size", "spec/position", "spec/clearance",
                           "spec/interface", "spec/bodies", "spec/heat", "spec/holes"},
    "pinned_carrier": {"spec/size", "spec/position", "spec/clearance", "spec/interface", "spec/bodies",
                       "spec/holes"},
    "laser_panel": {"spec/envelope", "spec/size", "spec/position", "spec/clearance", "spec/interface"},
    "pcb_enclosure": {"spec/envelope", "spec/size", "spec/position", "spec/clearance", "spec/interface"},
    "idler_bracket": {"spec/envelope", "spec/size", "spec/position", "spec/clearance", "spec/interface",
                      "spec/bodies"},
    "endstop_bracket": {"spec/envelope", "spec/size", "spec/position", "spec/clearance",
                        "spec/interface"},
    "dock_material": {"spec/envelope", "spec/size", "spec/position", "spec/clearance", "spec/interface",
                      "spec/heat", "spec/bodies"},
    "beam_deflection": {"spec/envelope", "spec/size", "spec/position", "spec/clearance", "spec/mass",
                        "spec/deflection", "spec/bodies"},
}

# One small edit to each reference, and the rule it has to break: (file, old, new, rule). A rule
# can be a tuple when the edit breaks what follows from it too (a pin that no longer fits its
# hole also overlaps the block), and a fifth item names the row's subject where one rule has
# several entries.
BROKEN = {
    "nema17_mount": ("parts/bracket.py", '"motor_pitch": 31.0', '"motor_pitch": 30.0', "spec/interface"),
    "syringe_clamp": ("parts/syringe_clamp.py", '"fit": 0.4', '"fit": 1.0', ("spec/clearance", "spec/shaft_fit")),
    "galvo_mount": ("parts/galvo_mount.py", '"column_x": 112.0', '"column_x": 80.0', "spec/keepout"),
    "mgn12h_carriage": ("parts/carriage_plate.py", '"bolt_pitch_y": 20.0', '"bolt_pitch_y": 15.0',
                        "spec/interface"),
    "hotplate_standoffs": ("parts/standoff.py", "CLEARANCE_HOLE[screw] / 2.0", "3.8 / 2.0",
                           ("spec/interface", "spec/holes")),       # a 3.8 mm bore is past M3's coarse 3.6
    "pinned_carrier": ("parts/carrier.py", '"pin_pitch": 50.0', '"pin_pitch": 50.2',
                       ("spec/interface", "spec/clearance", "interference")),
    "laser_panel": ("parts/panel.py", '"button_hole": 16.0', '"button_hole": 17.0', "spec/clearance",
                    "push_button|panel"),                           # the max_mm: a button that gapes
    "pcb_enclosure": ("parts/base.py", 'round(h["point"].X, 3)', 'round(h["point"].X + 0.5, 3)',
                      "spec/interface"),
    "idler_bracket": ("parts/bracket.py", '"gap": 0.75', '"gap": 0.25',
                      ("spec/clearance", "clearance"), "idler|bracket"),
    "endstop_bracket": ("parts/bracket.py", '"pitch": 9.5', '"pitch": 10.0', "spec/interface"),
    "dock_material": ("parts/dock.py", 'MATERIAL = "stainless"', 'MATERIAL = "aluminium"',      # 170 C, in a 250 C zone
                      "spec/heat", "dock"),
    "beam_deflection": ("assembly.py", "Rot(90, 0, 0) * bought_solid", "bought_solid",           # the 2040 lies flat
                        "spec/deflection", "beam"),
}

# A design the brief rules out but every other rule passes, and the one rule that catches it:
# [[holes]] `through` and [[shaft_fit]], which the specs did not have. (task, file, old, new, rule)
GAPS = [
    # the pin holes drilled blind from the underside, 11 of the block's 12 mm: the pins still fit
    ("pinned_carrier", "parts/carrier.py",
     "Pos(sx * pin_pitch / 2.0, 0, height / 2.0) * Cylinder(pin_hole / 2.0, height + 2.0)",
     "Pos(sx * pin_pitch / 2.0, 0, 5.25) * Cylinder(pin_hole / 2.0, 11.5)", "spec/holes"),
    # the bore drilled blind from the top, 3 mm of floor left: it still meets the plate's hole
    ("hotplate_standoffs", "parts/standoff.py", "body -= Cylinder(CLEARANCE_HOLE[screw] / 2.0, height + 2.0)",
     "body -= Cylinder(CLEARANCE_HOLE[screw] / 2.0, height - 2.0).translate((0, 0, 2.0))", "spec/holes"),
    # a bore 1 mm over the barrel, pushed 0.3 mm toward the plate: 0.2 mm at its closest, in range
    ("syringe_clamp", "parts/syringe_clamp.py", "body -= Pos(bore_x, bore_y, 0) * Cylinder(bore_r, height + 2.0)",
     "bore_r = (barrel_dia + 1.0) / 2.0\n    body -= Pos(bore_x, bore_y + 0.3, 0) * Cylinder(bore_r, height + 2.0)",
     "spec/shaft_fit"),
]

# One edit to a reference that its brief says is fine, and that must still score 100%: what the
# briefs allow and what the grader accepts have to agree. (file, old, new)
PERMITTED = {
    "hotplate_standoffs": ("parts/standoff.py", "CLEARANCE_HOLE[screw] / 2.0", "3.2 / 2.0"),   # M3 close fit
    "dock_material": ("parts/dock.py", 'MATERIAL = "stainless"', 'MATERIAL = "polyimide"'),        # 360 C: the table clears it
    "mgn12h_carriage": ("parts/carriage_plate.py", "* Cylinder(d / 2.0, thickness + 2.0)",   # counterbored bolts
                        "* (Cylinder(d / 2.0, thickness + 2.0) + Pos(0, 0, 2.5) * Cylinder(3.0, 3.0))"),
    # A 3 mm LED hole over the frame's opening, 3 mm in from its rim: the brief says only a hole
    # whose axis lands on the frame is a mounting hole, so this is none and needs no mate. (The
    # grader once read it as one, being within 6 mm of the frame.)
    "laser_panel": ("parts/panel.py", "CUTLIST = ",
                    "EXPECT_FEATURES = 7\n_build = build\n\n\n"
                    "def build(**params):\n    return _build(**params) - Pos(0, 17, 0) * Cylinder(1.5, 5)\n\n\n"
                    "CUTLIST = "),
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
    for task in TASKS:                       # "name: what it is", which is what `ls` shows
        assert rows[task]["title"].startswith(f"{task}: ")
        assert rows[task]["given"] and rows[task]["reference"]
    cli.main(["eval", "ls", "--evals", str(EVALS)])
    lines = capsys.readouterr().out.splitlines()
    assert len({line.index(f"{t}: ") for t in TASKS for line in lines if line.startswith(f"  {t}")}) == 1
    code, data = run(capsys, "eval", "brief", "nema17_mount", "--evals", str(EVALS))
    assert code == cli.OK and data["given"] == rows["nema17_mount"]["given"]
    assert data["brief"] == (EVALS / "nema17_mount" / "brief.md").read_text()
    cli.main(["eval", "brief", "nema17_mount", "--evals", str(EVALS)])
    out = capsys.readouterr().out
    assert out.startswith("# nema17_mount:")
    assert out.endswith("given files, laid into projects/nema17_mount/:\n"
                        "  bought/nema17_motor.json\n  bought/nema17_motor.step\n")


NUM = r"-?\d+(?:\.\d+)?"
SIZES = re.compile(rf"({NUM})\s*x\s*({NUM})\s*x\s*({NUM})")                  # 100 x 60 x 3
POINTS = re.compile(rf"\(\s*({NUM})\s*,\s*({NUM})\s*,\s*({NUM})\s*\)")       # (-22.5, 0, -6.7)


def numbers(text):
    """Every number in a text, as floats, so 13 and 13.0 are the same one."""
    found = [round(float(m), 4) for m in re.findall(NUM, text)]
    return set(found) | {abs(v) for v in found}


def triples(pattern, text):
    return {tuple(round(float(v), 4) for v in m) for m in pattern.findall(text)}


@pytest.mark.parametrize("task", TASKS)
def test_the_brief_states_everything_the_hidden_spec_checks(task):
    """No gotchas: every body and part module the spec names, every given file, and every
    number the spec holds a design to, are in the brief the agent gets. Numbers are read, not
    matched as text, since each brief has its own way to write 13.0 and 6 x 12 x 14."""
    brief = (EVALS / task / "brief.md").read_text()
    spec = tomllib.loads((EVALS / task / "spec.toml").read_text())
    nums, sizes, points = numbers(brief), triples(SIZES, brief), triples(POINTS, brief)

    names = set()
    for kind in ("size", "position"):
        names |= {e["body"] for e in spec.get(kind, [])}
    for kind in ("clearance", "interface"):
        for e in spec.get(kind, []):
            names |= {e["a"], e["b"]}
    for e in spec.get("keepout", []):
        names |= set(e["clear"])
    for e in spec.get("mass", []):
        names |= set(e.get("parts", {})) | set(e.get("bodies", []))        # parts = {name = n}, or bodies = [...]
    for e in spec.get("heat", []):
        names |= {e["source"]} | (set(e["clear"]) if isinstance(e.get("clear"), list) else set())
    for e in spec.get("deflection", []):
        names.add(e["body"])
    names |= set(spec.get("bodies", {}).get("names", []))
    for name in sorted(names):
        assert f"`{name}`" in brief, f"{task}: the brief never names `{name}`"
    for given in evals.get_task(EVALS, task).given:       # by file name: they all say they are in bought/
        assert given.endswith(".json") or Path(given).name in brief, \
            f"{task}: the brief never names {given}"
    assert re.search(r"\blaid\b[^.]*\bagain\b", brief), \
        f"{task}: the brief never says the given files are laid again"
    assert "spec.toml" in brief and re.search(r"replace|not read", brief), \
        f"{task}: the brief never says the agent's own spec.toml is not the grader's"

    for key in ("min_mm", "max_mm"):
        if key in spec.get("envelope", {}):
            assert tuple(round(v, 4) for v in spec["envelope"][key]) in sizes, spec["envelope"]
    for e in spec.get("size", []):
        lo, hi = e.get("min_mm"), e.get("max_mm")
        if lo and hi and all(b - a <= 1 for a, b in zip(lo, hi)):     # a pin states its nominal size
            assert tuple(round((a + b) / 2, 4) for a, b in zip(lo, hi)) in sizes, e
        elif (lo or hi) and not (lo and hi) and all(lo or hi):         # a floor, or a ceiling, its limit
            assert tuple(lo or hi) in sizes, e
        for a, b in zip(lo or [0] * 3, hi or [0] * 3):                 # per axis: both ends, or the middle
            ends = [v for v in (a, b) if v]                            # (0 leaves that side open)
            assert all(round(v, 4) in nums for v in ends) or \
                (len(ends) == 2 and round((a + b) / 2, 4) in nums), (e, a, b)
    for e in spec.get("position", []):
        assert tuple(round(v, 4) for v in e["center_mm"]) in points, e
        assert "tol_mm" not in e or e["tol_mm"] in nums, e
    for e in spec.get("clearance", []):
        for key in ("min_mm", "max_mm"):
            assert key not in e or e[key] in nums, e
    for e in spec.get("interface", []):                                # its default tolerance is 0.1
        assert e.get("tol_mm", 0.1) in nums and ("near_mm" not in e or e["near_mm"] in nums), e
        assert "fastener" not in e or e["fastener"] in brief, e
    for e in spec.get("keepout", []):
        assert all(v in nums for v in e["params"].values()), e
    for e in spec.get("mass", []):
        assert f"{e['max_g']:g} g" in brief, e
    for e in spec.get("heat", []):                                     # the zone: how hot, how far, with what headroom
        for key in ("temp_c", "radius_mm", "margin_c"):
            assert key not in e or round(e[key], 4) in nums, (key, e)
    for e in spec.get("deflection", []):                               # the beam: its span, its load and its limit
        for key in ("span_mm", "load_n", "load_g", "max_um"):
            assert key not in e or round(e[key], 4) in nums, (key, e)
        assert e["support"] in brief and ("self_weight" not in e or "own weight" in brief), e
    for e in spec.get("holes", []):                                    # how many, how big, and through or how deep
        assert f"`{e['body']}`" in brief and e.get("count", 0) in nums | {0}, e
        assert all(round(e[k], 4) in nums for k in ("min_dia_mm", "max_dia_mm", "depth_mm") if k in e), e
        assert "through" not in e or re.search(r"\bthrough\b" if e["through"] else r"\bblind\b", brief), e
    for e in spec.get("shaft_fit", []):                                # a diametral fit, in its own numbers
        assert f"`{e['shaft']}`" in brief and f"`{e['bore']}`" in brief, e
        assert all(round(e[k], 4) in nums for k in ("min_mm", "max_mm", "tol_mm") if k in e), e
        assert "diameter" in brief, e
    if "count" in spec.get("bodies", {}):
        assert spec["bodies"]["count"] in nums, spec["bodies"]
    for e in spec.get("axis", []):                                     # an axis the design must declare
        assert e["name"] in brief and all(round(e[k], 4) in nums for k in e if k.endswith("_mm")), e


@pytest.mark.parametrize("task", TASKS)
def test_a_task_is_complete(task):
    root = EVALS / task
    assert (root / "brief.md").is_file() and (root / "spec.toml").is_file()
    assert (root / "reference" / "assembly.py").is_file()
    # its own parts, or a library part it copied in (a design of stock, such as a beam, has no part module)
    assert list((root / "reference" / "parts").glob("*.py")) or list((root / "reference" / "bought").glob("*.py"))
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


def test_what_a_tool_left_among_the_given_files_is_not_given(tmp_path):
    root = tmp_path / "evals"
    given = root / "t" / "given"
    (given / "bought").mkdir(parents=True)
    (root / "t" / "brief.md").write_text("# t: a task\n")
    (root / "t" / "spec.toml").write_text("[envelope]\nmax_mm = [1, 1, 1]\n")
    (given / "bought" / "thing.step").write_text("step")
    for junk in (".cad/log.jsonl", "__pycache__/x.pyc", "bought/.DS_Store"):
        (given / junk).parent.mkdir(exist_ok=True)
        (given / junk).write_text("x")
    task = evals.get_task(root, "t")
    assert task.given == ["bought/thing.step"]
    task.lay_given(tmp_path / "project")
    laid = sorted(p.relative_to(tmp_path / "project").as_posix()
                  for p in (tmp_path / "project").rglob("*") if p.is_file())
    assert laid == ["bought/thing.step"]


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
    cmd = evals.fill('claude -p "$(cat {brief})" --add-dir {dir} --plugin-dir {plugin} '
                     '# {task} ${HOME} {root}',
                     brief=Path("/a b/BRIEF.md"), dir=Path("/a b/p"), task="t", root=Path("/a b"),
                     plugin=Path("/a b/plugin"))
    assert cmd == ("claude -p \"$(cat '/a b/BRIEF.md')\" --add-dir '/a b/p' --plugin-dir '/a b/plugin' "
                   "# t ${HOME} '/a b'")


# ─── The plugin an agent is given: no graders in it ──────────────────────────

def test_the_plugin_copy_leaves_out_what_grades_and_what_is_not_a_plugin(tmp_path):
    """A repo with one of everything: what an agent under test must not read (the hidden specs
    in evals/, a tasks folder elsewhere in the repo, the history, other agents' worktrees) and
    what is only weight (the environment, caches). Everything else comes across."""
    src = tmp_path / "repo"
    kept = ["bin/cad", ".claude-plugin/plugin.json", ".claude/skills/cad/SKILL.md",
            "cad_agent/__init__.py", "docs/evals.md", "pyproject.toml", "ui/src/main.ts",
            ".github/ci.yml"]
    left_out = ["evals/t/spec.toml", "specs/t/spec.toml", ".git/HEAD", "vendor/lib/.git",
                ".venv/bin/python", ".claude/worktrees/w/evals/t/spec.toml",
                "ui/node_modules/x/index.js", "cad_agent/__pycache__/x.pyc",
                "cad_agent.egg-info/PKG-INFO", ".pytest_cache/v", "bin/.DS_Store"]
    for rel in kept + left_out:
        (src / rel).parent.mkdir(parents=True, exist_ok=True)
        (src / rel).write_text("x")
    copy = evals.plugin_copy(tmp_path / "copy", tasks=src / "specs", src=src)
    assert copy == tmp_path / "copy"
    got = sorted(p.relative_to(copy).as_posix() for p in copy.rglob("*") if p.is_file())
    assert got == sorted(kept)


def test_the_real_plugin_copy_is_a_working_plugin_without_evals(tmp_path):
    copy = evals.plugin_copy(tmp_path / "plugin", EVALS)
    for rel in (".claude-plugin/plugin.json", "plugin/hooks.json", ".claude/hooks/cad_on_edit.py",
                ".claude/hooks/cad_on_stop.py", ".claude/skills/cad/SKILL.md", "bin/cad",
                "pyproject.toml", "cad_agent/evals.py"):
        assert (copy / rel).is_file(), rel
    names = {p.name for p in copy.rglob("*")}
    assert not {"evals", ".git", ".venv", "worktrees", "node_modules"} & names
    assert not set(TASKS) & names                                       # no task folder, wherever


def test_a_folder_that_is_not_a_plugin_is_not_copied(tmp_path):
    """A plain install has no checkout to copy: the repo root is then site-packages."""
    (tmp_path / "site-packages").mkdir()
    with pytest.raises(evals.EvalError, match="not a plugin folder"):
        evals.plugin_copy(tmp_path / "copy", src=tmp_path / "site-packages")
    assert not (tmp_path / "copy").exists()


def test_a_plugin_placeholder_without_a_plugin_copy_is_refused():
    with pytest.raises(evals.EvalError, match="plugin"):
        evals.run_task(evals.get_task(EVALS, "nema17_mount"), "echo {plugin}", 5)


# ─── Scoring for real ────────────────────────────────────────────────────────

@pytest.mark.parametrize("task", TASKS)
def test_the_reference_scores_full_marks(reference, task):
    r = reference(task)
    assert r["verdict"] == "PASS" and r["score"] == 1.0, [x for x in r["rows"] if x["state"] != "PASS"]
    own_parts = list((EVALS / task / "reference" / "parts").glob("*.py"))
    assert r["graded"] == r["passed"] >= 20 and r["skipped"] >= (1 if own_parts else 0)   # a part's render waits for approval
    assert SPEC_RULES[task] <= {x["rule"] for x in r["rows"]}
    assert not r["notes"] and r["verify_seconds"] is not None


@pytest.mark.parametrize("task", TASKS)
def test_a_small_edit_to_the_reference_fails_on_the_rule_it_should(worker, tmp_path, capsys, task):
    rel, old, new, rules, *subject = BROKEN[task]
    rules = (rules,) if isinstance(rules, str) else rules
    design = copy_reference(task, tmp_path / "design")
    text = (design / rel).read_text()
    assert old in text
    (design / rel).write_text(text.replace(old, new))
    code, r = run(capsys, "eval", "score", task, str(design), "--evals", str(EVALS))
    assert code == cli.FAIL and r["verdict"] == "FAIL" and 0.5 < r["score"] < 1.0
    assert {x["rule"] for x in r["rows"]} == set(rules)          # nothing else broke, only that rule
    assert all(x["state"] == "FAIL" for x in r["rows"])
    if subject:                                                  # and it is the entry that was meant
        assert subject[0] in {x["subject"] for x in r["rows"] if x["rule"] == rules[0]}


@pytest.mark.parametrize("task, rel, old, new, rule", GAPS, ids=[g[0] for g in GAPS])
def test_what_only_the_hole_and_fit_rules_catch_fails_on_them(worker, tmp_path, capsys, task, rel, old, new, rule):
    design = copy_reference(task, tmp_path / "design")
    text = (design / rel).read_text()
    assert old in text
    (design / rel).write_text(text.replace(old, new))
    code, r = run(capsys, "eval", "score", task, str(design), "--evals", str(EVALS))
    assert code == cli.FAIL and r["verdict"] == "FAIL"
    assert {x["rule"] for x in r["rows"]} == {rule}, r["rows"]      # every other rule still passes it


@pytest.mark.parametrize("task", PERMITTED)
def test_an_edit_the_brief_allows_still_scores_full_marks(worker, tmp_path, capsys, task):
    rel, old, new = PERMITTED[task]
    design = copy_reference(task, tmp_path / "design")
    text = (design / rel).read_text()
    assert old in text
    (design / rel).write_text(text.replace(old, new))
    code, r = run(capsys, "eval", "score", task, str(design), "--evals", str(EVALS))
    assert code == cli.OK and r["verdict"] == "PASS" and r["score"] == 1.0, r["rows"]


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


# ─── dock_material: what a 250 C zone does to the dock's material ────────────

def edited(task, tmp_path, rel, old, new):
    """A copy of the task's reference with `old` in `rel` replaced by `new`."""
    design = copy_reference(task, tmp_path / "design")
    text = (design / rel).read_text()
    assert old in text
    (design / rel).write_text(text.replace(old, new))
    return design


def dock_rows(result):
    return {x["subject"]: x for x in result["rows"] if x["rule"] == "spec/heat"}


@pytest.mark.parametrize("material,rated,basis", [("pla", 55, "HDT ISO 75-2 B"), ("aluminium", 170, "stated service limit")])
def test_a_pla_or_aluminium_dock_fails_the_heat_row_and_nothing_else(worker, tmp_path, capsys, material, rated, basis):
    """The dock stands 3 mm from a 250 C plate, inside the 15 mm zone: a body there is held to the plate's
    temperature as if it touched it, and these two are rated for 55 and 170 C."""
    design = edited("dock_material", tmp_path, "parts/dock.py", 'MATERIAL = "stainless"', f'MATERIAL = "{material}"')
    code, r = run(capsys, "eval", "score", "dock_material", str(design), "--evals", str(EVALS), "--all")
    assert code == cli.FAIL and r["verdict"] == "FAIL" and r["passed"] == r["graded"] - 1
    heat = dock_rows(r)
    assert set(heat) == {"dock", "base_plate"}                              # the plate is the source: exempt, no row
    assert heat["dock"]["state"] == "FAIL"
    assert heat["dock"]["measured"] == f"{material} ({basis}) rated {rated} C, 3.00 mm from hot_plate"
    assert heat["dock"]["limit"] == ">= 250 C, a zone, not a thermal model"
    assert heat["base_plate"]["state"] == "PASS"                            # the given plate passes on its declared 400 C
    assert [x["rule"] for x in r["rows"] if x["state"] != "PASS"] == ["spec/heat"]


def test_an_aluminium_standoff_fails_the_heat_row_hotplate_standoffs_has_now(worker, tmp_path, capsys):
    """Its brief used to call aluminium, brass and copper fine at 250 C and its grader had no heat rule; the table gives them
    170, 120 and 200 C, and the grader has the zone now: each of the four standoffs, touching the plate, is one failing row."""
    design = edited("hotplate_standoffs", tmp_path, "parts/standoff.py", 'MATERIAL = "polyimide"', 'MATERIAL = "aluminium"')
    code, r = run(capsys, "eval", "score", "hotplate_standoffs", str(design), "--evals", str(EVALS), "--all")
    heat = dock_rows(r)
    assert code == cli.FAIL and sorted(heat) == [f"standoff_{i}" for i in range(1, 5)]      # the base is 20 mm off: no row
    assert {x["state"] for x in heat.values()} == {"FAIL"} and heat["standoff_1"]["measured"].startswith(
        "aluminium (stated service limit) rated 170 C, 0.00 mm from hot_plate")
    assert [x["rule"] for x in r["rows"] if x["state"] != "PASS"] == ["spec/heat"] * 4


def test_a_carriage_with_no_AXES_fails_the_axis_row_the_brief_asks_for_and_no_longer_costs_nothing(worker, tmp_path, capsys):
    """The first of the known gaps in evals/README.md: `[[axis]]` can require what the brief asks for."""
    design = edited("mgn12h_carriage", tmp_path, "assembly.py", "AXES = {", "UNUSED_AXES = {")
    code, r = run(capsys, "eval", "score", "mgn12h_carriage", str(design), "--evals", str(EVALS), "--all")
    failing = [(x["rule"], x["subject"]) for x in r["rows"] if x["state"] == "FAIL"]
    assert code == cli.FAIL and failing == [("spec/axis", "axis x")]
    (row,) = [x for x in r["rows"] if x["rule"] == "spec/axis"]
    assert "no axis 'x' in AXES" in row["measured"] and "assembly.py declares no AXES" in row["measured"]


def test_the_grader_rates_the_dock_by_the_table_for_every_material_the_brief_lists(worker, tmp_path):
    """Steel, stainless and polyimide clear 250 C and the other nine do not: one row each, whatever the material."""
    from cad_agent import materials
    task = evals.get_task(EVALS, "dock_material")
    brief = task.brief
    listed = re.search(r"one of the twelve materials `cad tables materials` knows: (.*?)\. Anything else", brief, re.S)[1]
    names = {w.strip().lower() for w in re.split(r",| and ", listed.replace("\n", " ")) if w.strip()}
    assert names == set(materials.names())                                  # the brief lists the table, all of it
    cleared = {}
    for material in sorted(names):
        design = edited("dock_material", tmp_path / material, "parts/dock.py", 'MATERIAL = "stainless"',
                        f'MATERIAL = "{material}"')
        r = evals.score(task, design, show_all=True)
        row = dock_rows(r)["dock"]
        cleared[material] = row["state"]
        assert r["verdict"] == ("PASS" if row["state"] == "PASS" else "FAIL"), (material, r["rows"])
        assert (row["state"] == "PASS") == (materials.prop(material, "max_service_temp_c").value >= 250), row
    assert {m for m, s in cleared.items() if s == "PASS"} == {"steel", "stainless", "polyimide"}


@pytest.mark.parametrize("old,new,why", [
    ('MATERIAL = "stainless"\n', "", "its part module 'dock' declares no MATERIAL"),
    ('MATERIAL = "stainless"', 'MATERIAL = "peek"', "material 'peek' is not in materials.py"),
])
def test_a_dock_with_no_rating_is_unchecked_not_a_pass(worker, tmp_path, capsys, old, new, why):
    """The brief says a material the table does not know, or none, leaves the heat row unable to pass."""
    design = edited("dock_material", tmp_path, "parts/dock.py", old, new)
    code, r = run(capsys, "eval", "score", "dock_material", str(design), "--evals", str(EVALS), "--all")
    row = dock_rows(r)["dock"]
    assert row["state"] == "UNCHECKED" and why in row["measured"] and r["verdict"] != "PASS"


def test_the_base_plate_is_in_the_zone_and_passes_on_the_rating_its_note_declares(worker, tmp_path, capsys):
    """It lies under the hot plate, so it is judged. Its sidecar says 400 C and quotes the page; without a rating the
    row is UNCHECKED, which no design could fix, and that is what a zone wider than 15 mm would have done to the
    hotplate_standoffs plate."""
    from cad_agent import materials
    note = json.loads((EVALS / "dock_material" / "given" / "bought" / "base_plate.json").read_text())
    assert note["material"] == "steel" and note["max_temp_c"] == materials.prop("steel", "max_service_temp_c").value
    assert note["max_temp_source"].startswith("https://www.makeitfrom.com/") and "Mechanical 400" in note["max_temp_source"]
    root = tmp_path / "evals"                                              # a copy of the task whose base plate says nothing
    shutil.copytree(EVALS / "dock_material", root / "dock_material", ignore=shutil.ignore_patterns("reference"))
    side = root / "dock_material" / "given" / "bought" / "base_plate.json"
    side.write_text(json.dumps({k: v for k, v in note.items() if k not in ("material", "max_temp_c", "max_temp_source")}))
    r = evals.score(evals.get_task(root, "dock_material"), EVALS / "dock_material" / "reference", show_all=True)
    base = dock_rows(r)["base_plate"]
    assert base["state"] == "UNCHECKED" and "declares neither max_temp_c" in base["measured"] and r["verdict"] == "UNCHECKED"
    assert dock_rows(r)["dock"]["state"] == "PASS"                         # the dock itself is as rated as it was


# ─── beam_deflection: which stock clears 50 um, and what else it must be ─────

@pytest.mark.parametrize("entry,rule,state,says", [
    ("extrusion-2020", "spec/deflection", "FAIL", "242."),                 # a 2020 is far too limber: 242 um
    ("extrusion-4040", "spec/mass", "FAIL", "1120.6 g"),                   # a 4040 is stiff enough and weighs too much
    ("extrusion-2040-envelope", "spec/deflection", "UNCHECKED", "not declared `geometry = \"exact\"`"),   # a solid box
])
def test_the_other_library_extrusions_miss_the_beam_task_on_their_own_rule(worker, tmp_path, monkeypatch, capsys,
                                                                           entry, rule, state, says):
    monkeypatch.setenv("CAD_LIBRARY", str(tmp_path / "store"))
    design = copy_reference("beam_deflection", tmp_path / "projects" / "beam_deflection")
    code, out = run(capsys, "lib", "use", "beam_deflection", entry, "length=640", "--as", "extrusion_2040", "--replace")
    assert code == cli.OK and out["entry"] == entry
    code, r = run(capsys, "eval", "score", "beam_deflection", str(design), "--evals", str(EVALS), "--all")
    rows = [x for x in r["rows"] if x["state"] != "PASS"]
    assert [(x["rule"], x["state"]) for x in rows] == [(rule, state)], rows            # one row, and it is that one
    assert says in rows[0]["measured"] and r["verdict"] == state


def test_the_beam_brief_quotes_the_working_volumes_the_part_rules_use():
    """It says no part module can be a bar 640 mm long, and why: the `envelope` row's limit for each process."""
    from cad_agent.checks.dfm import PROCESS
    brief = (EVALS / "beam_deflection" / "brief.md").read_text()
    for name, volume in {n: p["max_bbox_mm"] for n, p in PROCESS.items()}.items():
        assert " x ".join(f"{v:g}" for v in volume) in brief and f"`{name}`" in brief, name
    assert max(max(p["max_bbox_mm"]) for p in PROCESS.values()) < 640           # so the claim is true


def test_the_reference_beam_is_the_2040_on_its_edge_with_room_to_spare_on_both_limits(reference):
    r = {x["rule"]: x for x in reference("beam_deflection")["rows"]}
    deflection = r["spec/deflection"]["measured"]
    assert float(re.match(r"([\d.]+) um at midspan", deflection)[1]) == pytest.approx(37.67, abs=0.02)      # of 50
    assert r["spec/mass"]["measured"].startswith("499.3 g")                                               # of 600
    assert float(re.search(r"I ([\d.]+) mm\^4", deflection)[1]) == pytest.approx(46740, abs=20)         # 12145 lying flat
    note = json.loads((EVALS / "beam_deflection" / "reference" / "bought" / "extrusion_2040.json").read_text())
    assert note["library"] == "extrusion-2040" and note["geometry"] == "exact" and note["sha256"]    # `cad lib use` wrote it


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


def plugin_probe(seen):
    """An agent command that writes what it sees of {plugin} into a file, and fails if the
    environment still points it at the tasks."""
    out = shlex.quote(str(seen))
    return f'ls -A {{plugin}} > {out} && echo {{plugin}} >> {out} && test -z "${{CAD_EVALS:-}}"'


def test_the_agent_gets_a_plugin_copy_without_evals_that_goes_away(worker, mini, capsys, tmp_path,
                                                                   monkeypatch):
    monkeypatch.setenv("CAD_EVALS", str(mini))          # run finds the tasks here; the agent must not
    seen = tmp_path / "seen.txt"
    code, r = run(capsys, "eval", "run", "--agent", plugin_probe(seen), "--timeout", "120")
    (t,) = r["tasks"]
    assert t["agent_exit"] == 0, t["agent_tail"]
    *top, where = seen.read_text().splitlines()
    assert {".claude-plugin", "cad_agent", "bin"} <= set(top)
    assert not {"evals", ".git", ".venv"} & set(top)
    assert not Path(where).exists() and "plugin_dir" not in r            # one copy per run, removed after it


def test_keep_keeps_the_plugin_copy_and_says_where(worker, mini, capsys, tmp_path):
    seen = tmp_path / "seen.txt"
    code, r = run(capsys, "eval", "run", "--agent", plugin_probe(seen), "--evals", str(mini), "--keep",
                  "--timeout", "120")
    (t,) = r["tasks"]
    kept = Path(r["plugin_dir"])
    try:
        assert t["agent_exit"] == 0, t["agent_tail"]
        assert seen.read_text().splitlines()[-1] == str(kept)             # the agent was given this copy
        assert (kept / "cad_agent" / "evals.py").is_file() and not (kept / "evals").exists()
    finally:
        for folder in (kept.parent, t["agent_dir"], t["kept"]):
            shutil.rmtree(folder, ignore_errors=True)


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

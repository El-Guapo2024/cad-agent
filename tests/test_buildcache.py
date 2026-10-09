"""The build cache (buildcache.py): what keys an entry, what it never serves, and that the edit
loop's commands use it while `cad verify` never does.

The projects are the throwaway demo of test_cli.py (a plate and a block), so a build takes a few
milliseconds and most of what is measured is the cache. Two tests run a fixture design through
cached and uncached `check` and hold their rows equal.
"""
import json
import shutil
from pathlib import Path

import pytest

from cad_agent import buildcache, cli, runner, verify
from cad_agent import state as st
from test_cli import ASSEMBLY, PLATE, log_lines, run
from test_cli import BLOCK as CUBE

FIXTURES = Path(__file__).resolve().parent / "fixtures"
# test_cli's block returns a Box, a primitive that carries its own arguments and is built each time
# (the cache keeps plain Parts); this one returns the Part a boolean would.
BLOCK = CUBE.replace("from build123d import Box", "from build123d import Box, Part").replace(
    "return Box(size, size, size)", "return Part(Box(size, size, size).wrapped)")
THICK = PLATE.replace('"thickness": 4.0', '"thickness": 40.0')       # its top reaches the block above it


@pytest.fixture()
def demo(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(st, "ROOT", tmp_path)
    monkeypatch.delenv("CAD_PROJECTS", raising=False)
    buildcache.forget()
    assert cli.main(["init", "demo", "--brief", "test project"]) == cli.OK
    capsys.readouterr()
    d = tmp_path / "demo"
    (d / "parts" / "plate.py").write_text(PLATE)
    (d / "parts" / "block.py").write_text(BLOCK)
    (d / "assembly.py").write_text(ASSEMBLY)
    return d


def how(data) -> dict:
    """{"built": [...], "cache": [...]} from a command's log of builds."""
    out = {"built": [], "cache": []}
    for b in data["builds"]:
        out[b["how"]].append(b["part"])
    return {k: sorted(v) for k, v in out.items()}


def judged(rows) -> list:
    """The rows a person approving a render is not holding open (the edit hook skips the same)."""
    return [r for r in rows if not r["rule"].startswith(("drift/", "extent/", "visual/"))]


def entries(project: Path) -> list[Path]:
    d = buildcache.cache_dir(project)
    return sorted(d.glob(f"*{buildcache.SUFFIX}")) if d.is_dir() else []


def checks_json(project: Path) -> str:
    """checks.json as a run leaves it, less the time it was written and how long each part took."""
    d = json.loads((project / "checks.json").read_text())
    d.pop("written_utc")
    for p in d["parts"].values():
        p.pop("build_s")
    return json.dumps(d, sort_keys=True, indent=1)


# ─── The loop: what is built, what is read back ──────────────────────────────

def test_a_second_check_builds_nothing_and_leaves_the_same_checks_json(demo, capsys):
    code, first = run(capsys, "check", "demo", "--all")
    assert how(first) == {"built": ["block", "plate"], "cache": []}
    assert len(entries(demo)) == 2
    cold = checks_json(demo)
    code2, second = run(capsys, "check", "demo", "--all")
    assert how(second) == {"built": [], "cache": ["block", "plate"]} and code2 == code
    assert checks_json(demo) == cold
    code3, third = run(capsys, "check", "demo", "--all", "--no-cache")
    assert how(third) == {"built": ["block", "plate"], "cache": []} and code3 == code
    assert checks_json(demo) == cold                   # the file does not say how its parts were got
    assert second["rows"] == third["rows"]
    text = lambda *argv: (cli.main(["--json", "--with-text", *argv]), json.loads(
        capsys.readouterr().out.strip().splitlines()[-1])["text"])[1]
    assert "build cache: 2 of 2 parts reused" in text("check", "demo")       # the line a human reads
    assert "build cache" not in text("check", "demo", "--no-cache")


def test_an_edit_rebuilds_only_the_part_edited(demo, capsys):
    run(capsys, "check", "demo")
    (demo / "parts" / "plate.py").write_text(PLATE.replace('"depth": 20.0', '"depth": 22.0'))
    code, data = run(capsys, "check", "demo", "--part", "plate")
    assert how(data) == {"built": ["plate"], "cache": ["block"]}
    code, data = run(capsys, "check", "demo")
    assert how(data) == {"built": [], "cache": ["block", "plate"]}     # the edit was kept too
    (demo / "assembly.py").write_text(ASSEMBLY + "\n# a note\n")
    code, data = run(capsys, "check", "demo")
    assert how(data) == {"built": [], "cache": ["block", "plate"]}     # assembly.py is no part's input


def test_scene_reads_the_parts_it_can_and_builds_the_one_edited(demo, capsys):
    code, first = run(capsys, "scene", "demo")
    assert how(first)["built"] == ["block", "plate"]
    (demo / "parts" / "block.py").write_text(BLOCK.replace('"size": 10.0', '"size": 12.0'))
    code, data = run(capsys, "scene", "demo")
    assert how(data) == {"built": ["block"], "cache": ["plate"]}
    block = [b for b in json.loads((demo / "out" / "scene.json").read_text())["bodies"] if b["name"] == "block"][0]
    assert block["bbox"] == [[-6.0, -6.0, 14.0], [6.0, 6.0, 26.0]]      # the new block, not the cached one


def scene_numbers(project: Path) -> str:
    """out/scene.json with every buffer read as numbers: a -0.0 and a 0.0 in a normal are one."""
    import base64
    import hashlib
    import numpy as np
    d = json.loads((project / "out" / "scene.json").read_text())
    d.pop("written_utc")
    for inst in d["viewer"]["instances"]:
        for key, buf in list(inst.items()):
            if isinstance(buf, dict) and "buffer" in buf:
                arr = np.frombuffer(base64.b64decode(buf["buffer"]), dtype="<f4" if buf["dtype"] == "float32" else "<u4")
                inst[key] = hashlib.sha1((arr + arr.dtype.type(0)).tobytes()).hexdigest()
    return json.dumps(d, sort_keys=True)


def test_the_scene_is_the_same_numbers_with_and_without_the_cache(demo, capsys):
    run(capsys, "scene", "demo", "--no-cache")
    plain = scene_numbers(demo)
    code, cold = run(capsys, "scene", "demo")
    code, warm = run(capsys, "scene", "demo")
    assert how(warm) == {"built": [], "cache": ["block", "plate"]}
    assert scene_numbers(demo) == plain


def test_measure_and_place_read_the_cache_too(demo, capsys):
    run(capsys, "check", "demo")
    code, data = run(capsys, "measure", "demo", "plate", "block", "--posed")
    assert how(data) == {"built": [], "cache": ["block", "plate"]} and data["min_distance_mm"] == 13.0
    code, data = run(capsys, "place", "demo", "block", "--by=0,0,-1")
    assert how(data) == {"built": [], "cache": ["block", "plate"]} and code == cli.OK
    code, data = run(capsys, "measure", "demo", "plate", "block", "--posed", "--no-cache")
    assert how(data) == {"built": ["block", "plate"], "cache": []}


def test_set_leaves_the_new_part_in_the_cache_for_the_next_scene(demo, capsys):
    run(capsys, "check", "demo")
    code, data = run(capsys, "set", "demo", "plate", "thickness=6")
    assert how(data) == {"built": ["plate"], "cache": []}
    code, data = run(capsys, "scene", "demo")
    assert how(data) == {"built": [], "cache": ["block", "plate"]}
    plate = [b for b in json.loads((demo / "out" / "scene.json").read_text())["bodies"] if b["name"] == "plate"][0]
    assert plate["bbox"][1][2] == 3.0                        # 6 mm thick, centred on z = 0


def test_the_activity_log_says_which_parts_were_built(demo, capsys):
    run(capsys, "check", "demo")
    run(capsys, "check", "demo")
    last = log_lines(demo)[-1]
    assert last["cmd"] == "check" and last["builds"] == {"built": [], "cache": ["block", "plate"]}


# ─── Fit at the edit ─────────────────────────────────────────────────────────

def test_a_part_check_judges_the_pairs_of_its_bodies_in_the_assembly(demo, capsys):
    run(capsys, "check", "demo")
    code, data = run(capsys, "check", "demo", "--part", "plate", "--all")
    fit = [r for r in data["rows"] if r["check"] == "fit"]
    assert [r["subject"] for r in fit] == ["block vs plate"] and fit[0]["state"] == "PASS"
    assert fit[0]["rule"] == "clearance" and "gap 13.000 mm" in fit[0]["measured"]
    assert "the fit of plate in assembly.py" in data["scope"] and not judged(data["failing"])

    (demo / "parts" / "plate.py").write_text(THICK)
    code, data = run(capsys, "check", "demo", "--part", "plate")
    assert code == cli.FAIL and how(data) == {"built": ["plate"], "cache": ["block"]}
    failing = judged(data["failing"])
    assert [(r["check"], r["rule"], r["subject"], r["state"]) for r in failing] == \
        [("fit", "interference", "block vs plate", "FAIL")]
    assert set(failing[0]) >= {"state", "rule", "subject", "measured", "limit"}      # what the edit hook prints
    assert "overlap" in failing[0]["measured"]
    # the block's own edit is judged against the plate that is there now
    code, data = run(capsys, "check", "demo", "--part", "block")
    assert any(r["rule"] == "interference" for r in judged(data["failing"]))


def test_the_fit_rule_can_judge_only_the_pairs_of_some_bodies():
    from build123d import Box, Pos
    from cad_agent.checks.fit import check_fit
    parts = {"a": Box(10, 10, 10), "b": Pos(30, 0, 0) * Box(10, 10, 10), "c": Pos(60, 0, 0) * Box(10, 10, 10)}
    pairs = lambda **kw: [r["pair"] for r in check_fit(parts, **kw)]
    assert pairs() == ["a vs b", "a vs c", "b vs c"]
    assert pairs(involving={"a"}) == ["a vs b", "a vs c"]
    assert pairs(involving={"c"}) == ["a vs c", "b vs c"]
    assert pairs(involving={"b", "c"}) == ["a vs b", "a vs c", "b vs c"]
    assert pairs(involving=set()) == []


def test_a_set_variant_and_a_project_without_an_assembly_have_no_fit_to_judge(demo, capsys):
    code, data = run(capsys, "check", "demo", "--part", "plate", "--set", "thickness=40")
    assert not [r for r in data["rows"] if r["check"] == "fit"]
    assert data["scope"].startswith("part rules only; fit, sweep")
    (demo / "assembly.py").unlink()
    code, data = run(capsys, "check", "demo", "--part", "plate")
    assert not [r for r in data["rows"] if r["check"] == "fit"]
    assert data["scope"].startswith("part rules only; fit, sweep")


def test_a_part_the_assembly_has_no_body_for_is_said_so(demo, capsys):
    (demo / "parts" / "spare.py").write_text(BLOCK)
    code, data = run(capsys, "check", "demo", "--part", "spare")
    assert not [r for r in data["rows"] if r["check"] == "fit"]
    assert "no body of assembly.py comes from this part" in data["scope"]


def test_a_broken_assembly_is_a_failing_row_of_the_part_check(demo, capsys):
    (demo / "assembly.py").write_text("def parts():\n    raise ValueError('no layout yet')\n")
    code, data = run(capsys, "check", "demo", "--part", "plate")
    assert code == cli.FAIL
    failing = judged(data["failing"])
    assert [(r["rule"], r["state"]) for r in failing] == [("build", "FAIL")]
    assert "no layout yet" in failing[0]["measured"] and "assembly.py did not build" in data["scope"]


# ─── What a key is made of ───────────────────────────────────────────────────

def test_the_key_follows_everything_a_build_can_depend_on(demo):
    key = lambda name="plate", ov=None: buildcache.key(demo, name, ov)
    base = key()
    assert base and len(base) == 64
    assert key() == base and key("block") != base
    assert key(ov={"thickness": 5.0}) != base and key(ov={"thickness": 5.0}) == key(ov={"thickness": 5.0})

    (demo / "parts" / "block.py").write_text(BLOCK + "# edit\n")
    (demo / "assembly.py").write_text(ASSEMBLY + "# edit\n")
    (demo / "spec.toml").write_text("[envelope]\nmax_mm = [1, 1, 1]\n")
    assert key() == base                                    # not what the plate is built from

    (demo / "parts" / "plate.py").write_text(PLATE + "# edit\n")
    changed = key()
    assert changed != base
    (demo / "helpers.py").write_text("X = 1\n")             # a module a part could import
    with_helper = key()
    assert with_helper != changed
    (demo / "helpers.py").write_text("X = 2\n")
    assert key() != with_helper and key("block") != key("plate")
    (demo / "bought").mkdir(exist_ok=True)
    before = key()
    (demo / "bought" / "motor.step").write_text("ISO-10303-21;")
    assert key() != before                                   # any file in bought/
    (demo / "bought" / ".DS_Store").write_text("x")
    after = key()
    (demo / "bought" / ".DS_Store").write_text("y")
    assert key() == after                                    # a Finder note is no input


def test_a_part_depends_on_the_parts_and_assembly_it_imports_and_on_all_when_it_cannot_tell(demo):
    head = "from build123d import Box, Part"
    (demo / "parts" / "dependent.py").write_text(BLOCK.replace(head, head + "\nimport plate", 1))
    (demo / "parts" / "dynamic.py").write_text(BLOCK + "\nimport importlib\nimportlib.import_module('anything')\n")
    (demo / "parts" / "reads_layout.py").write_text(BLOCK.replace(head, head + "\nfrom assembly import SLUG", 1))
    keys = lambda: {n: buildcache.key(demo, n) for n in ("dependent", "dynamic", "reads_layout", "block", "plate")}
    before = keys()
    (demo / "parts" / "plate.py").write_text(PLATE + "# edit\n")
    after = keys()
    assert after["dependent"] != before["dependent"] and after["dynamic"] != before["dynamic"]
    assert after["reads_layout"] != before["reads_layout"]      # assembly.py builds the plate
    assert after["block"] == before["block"]
    (demo / "assembly.py").write_text(ASSEMBLY + "# edit\n")
    last = keys()
    assert last["reads_layout"] != after["reads_layout"] and last["dynamic"] != after["dynamic"]
    assert last["dependent"] == after["dependent"] and last["block"] == after["block"]


def test_a_part_that_opens_a_file_depends_on_every_file_of_the_project(demo):
    head = "from build123d import Box, Part"
    (demo / "parts" / "reads.py").write_text(BLOCK.replace(head, head + "\nfrom pathlib import Path", 1)
                                             + "\nDATA = Path(__file__).with_name('data.csv').read_text()\n")
    keys = lambda: {n: buildcache.key(demo, n) for n in ("reads", "block")}
    before = keys()
    (demo / "mech_profile.md").write_text("another brief\n")
    (demo / "checks.json").write_text("{}")                  # an output, never an input
    (demo / "out" / "notes.txt").write_text("render notes")
    after = keys()
    assert after["reads"] != before["reads"] and after["block"] == before["block"]
    again = keys()
    (demo / "checks.json").write_text('{"changed": true}')
    assert keys() == again


def test_a_part_that_builds_another_part_depends_on_it(demo):
    (demo / "parts" / "derived.py").write_text(
        BLOCK + "\nfrom cad_agent.state import build_part\n\nBASE = build_part('demo', 'plate')\n")
    before = {n: buildcache.key(demo, n) for n in ("derived", "block")}
    (demo / "parts" / "plate.py").write_text(PLATE + "# edit\n")
    after = {n: buildcache.key(demo, n) for n in ("derived", "block")}
    assert after["derived"] != before["derived"] and after["block"] == before["block"]


def test_a_helper_in_a_linked_folder_counts(demo, tmp_path):
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "dims.py").write_text("W = 1\n")
    (demo / "lib").symlink_to(shared, target_is_directory=True)
    before = buildcache.key(demo, "plate")
    (shared / "dims.py").write_text("W = 2\n")
    assert buildcache.key(demo, "plate") != before
    (shared / "loop").symlink_to(shared, target_is_directory=True)           # a link back up must not hang the walk
    assert buildcache.key(demo, "plate")


def test_a_change_of_the_code_or_the_libraries_is_a_miss(demo, capsys, monkeypatch):
    run(capsys, "check", "demo")
    base = buildcache.key(demo, "plate")
    with monkeypatch.context() as m:
        m.setattr(verify, "engine_hash", lambda: "another engine")
        buildcache.forget()
        assert buildcache.key(demo, "plate") != base
        code, data = run(capsys, "check", "demo")
        assert how(data) == {"built": ["block", "plate"], "cache": []}
    buildcache.forget()
    assert buildcache.key(demo, "plate") == base
    import build123d
    with monkeypatch.context() as m:
        m.setattr(build123d, "__version__", "0.0.0")
        buildcache.forget()
        assert buildcache.key(demo, "plate") != base
    buildcache.forget()


# ─── Fail safe ───────────────────────────────────────────────────────────────

def entry_of(demo, name="plate") -> Path:
    return buildcache.cache_dir(demo) / f"{buildcache.key(demo, name)}{buildcache.SUFFIX}"


@pytest.mark.parametrize("damage", ["truncate", "flip a byte of the shape", "another key", "empty", "text"])
def test_an_entry_that_is_damaged_or_not_the_keys_is_a_miss_and_is_dropped(demo, capsys, damage):
    run(capsys, "check", "demo")
    path = entry_of(demo)
    blob = path.read_bytes()
    if damage == "truncate":
        path.write_bytes(blob[: len(blob) // 2])
    elif damage == "flip a byte of the shape":
        path.write_bytes(blob[:-40] + bytes([blob[-40] ^ 0xFF]) + blob[-39:])
    elif damage == "another key":
        path.write_bytes(entry_of(demo, "block").read_bytes())          # a valid entry, for the block
    elif damage == "empty":
        path.write_bytes(b"")
    else:
        path.write_bytes(b"not an entry at all")
    code, data = run(capsys, "check", "demo")
    assert how(data) == {"built": ["plate"], "cache": ["block"]}
    code, data = run(capsys, "check", "demo")
    assert how(data) == {"built": [], "cache": ["block", "plate"]}     # rebuilt, then stored again


def test_a_part_with_anything_set_on_it_is_built_every_time(demo, capsys):
    (demo / "parts" / "block.py").write_text(BLOCK.replace("return Part(Box(size, size, size).wrapped)",
                                                           "part = Part(Box(size, size, size).wrapped)\n"
                                                           "    part.label = 'block'\n    return part"))
    run(capsys, "check", "demo")
    code, data = run(capsys, "check", "demo")
    assert how(data) == {"built": ["block"], "cache": ["plate"]}


def test_a_meta_that_does_not_survive_json_is_not_stored(demo, capsys):
    (demo / "parts" / "block.py").write_text(BLOCK.replace('PARAMS = {"size": 10.0}', 'PARAMS = {"size": 10.0, "pair": (1, 2)}')
                                             .replace("def build(size):", "def build(size, pair):"))
    run(capsys, "check", "demo")
    code, data = run(capsys, "check", "demo")
    assert how(data) == {"built": ["block"], "cache": ["plate"]}       # a tuple would come back a list


def test_a_project_that_cannot_be_written_into_still_checks(demo, capsys):
    shutil.rmtree(demo / ".cad")
    (demo / ".cad").write_text("a file where the folder should be")
    code, data = run(capsys, "check", "demo")
    assert how(data) == {"built": ["block", "plate"], "cache": []} and judged(data["rows"])
    assert entries(demo) == []


def test_the_cache_stays_under_its_cap_and_drops_the_oldest(demo, capsys, monkeypatch):
    run(capsys, "check", "demo")
    one = max(p.stat().st_size for p in entries(demo))
    monkeypatch.setattr(buildcache, "CAP_BYTES", int(one * 2.5))
    for thick in (5, 6, 7, 8):
        (demo / "parts" / "plate.py").write_text(PLATE.replace('"thickness": 4.0', f'"thickness": {thick}.0'))
        run(capsys, "check", "demo", "--part", "plate")
    kept = entries(demo)
    assert 1 <= len(kept) < 6 and sum(p.stat().st_size for p in kept) <= one * 2.5
    assert entry_of(demo).exists()                           # the newest is the last to go
    assert (buildcache.cache_dir(demo).parent / ".gitignore").read_text() == "*\n"


# ─── The verifier never uses it ──────────────────────────────────────────────

def poison(demo, name="plate"):
    """Replace a part's entry with a valid one for a different shape."""
    from build123d import Box, Part
    meta = {"params": {}, "material": "petg", "process": "fdm", "min_feature_mm": 1.0,
            "expect_features": None, "doc": "", "build_s": 0.0}
    assert buildcache.store(demo, name, None, buildcache.key(demo, name), Part(Box(5, 5, 5).wrapped), meta)


def envelope(rows, subject="plate") -> str:
    return [r["measured"] for r in rows if r["subject"] == subject and r["rule"] == "envelope"][0]


def test_verify_ignores_a_poisoned_entry_and_leaves_the_cache_alone(demo, capsys):
    run(capsys, "check", "demo")
    poison(demo)
    code, data = run(capsys, "check", "demo", "--all")
    assert how(data)["cache"] == ["block", "plate"] and envelope(data["rows"]).startswith("5.0 x 5.0 x 5.0")
    before = {p.name: (p.stat().st_mtime_ns, p.read_bytes()) for p in entries(demo)}

    rec = verify.run("demo", fresh=True, mode="cold")
    assert envelope(rec["rows"]).startswith("40.0 x 20.0 x 4.0")           # rebuilt from source
    code, said = run(capsys, "verify", "demo", "--all")                    # and so is the command's
    assert envelope(said["rows"]).startswith("40.0 x 20.0 x 4.0") and "builds" not in said
    assert {p.name: (p.stat().st_mtime_ns, p.read_bytes()) for p in entries(demo)} == before
    code, plain = run(capsys, "check", "demo", "--all", "--no-cache")
    assert [r for r in rec["rows"] if r["check"] != "visual"] == [r for r in plain["rows"] if r["check"] != "visual"]

    shutil.rmtree(demo / ".cad" / "cache")
    verify.run("demo", fresh=True, mode="cold")
    assert not (demo / ".cad" / "cache").exists()                            # and it writes none


def test_check_all_is_uncached_even_inside_a_block_that_asked_for_the_cache(demo, capsys):
    run(capsys, "check", "demo")
    poison(demo)
    with st.caching_builds():
        payload = runner.check_all("demo")
    assert [b["how"] for b in payload["builds"]] == ["built", "built"]
    assert envelope(payload["rows"]).startswith("40.0 x 20.0 x 4.0")
    with st.caching_builds():
        cached = runner.check_all("demo", cached=True)
    assert envelope(cached["rows"]).startswith("5.0 x 5.0 x 5.0")            # the poison is live where it is asked for


def test_the_cache_is_off_unless_a_command_asks_for_it(demo):
    runner.check_all("demo")
    assert entries(demo) == []
    st.build_part("demo", "plate")
    assert entries(demo) == []


# ─── Cached and uncached agree on real designs ───────────────────────────────

def lay(tmp_path, monkeypatch, slug):
    root = tmp_path / "projects"
    shutil.copytree(FIXTURES / slug, root / slug,
                    ignore=shutil.ignore_patterns("out", "checks.json", "verify.json", ".cad"))
    monkeypatch.setattr(st, "ROOT", root)
    buildcache.forget()
    return root / slug


def test_cached_and_uncached_checks_leave_the_same_rows_on_a_fixture(tmp_path, monkeypatch):
    slug = "desk_fab_line"
    project = lay(tmp_path, monkeypatch, slug)
    plain = runner.check_all(slug, cached=False)
    plain_file = checks_json(project)
    cold = runner.check_all(slug, cached=True)
    assert checks_json(project) == plain_file
    warm = runner.check_all(slug, cached=True)
    assert checks_json(project) == plain_file and warm["rows"] == plain["rows"] == cold["rows"]
    assert sorted(b["part"] for b in warm["builds"] if b["how"] == "cache") == st.part_names(slug)
    assert not [b for b in warm["builds"] if b["how"] == "built"]

    part = st.part_names(slug)[0]
    edited = project / "parts" / f"{part}.py"
    edited.write_text(edited.read_text() + "\n# an edit\n")
    after = runner.check_all(slug, cached=True)
    assert [b["part"] for b in after["builds"] if b["how"] == "built"] == [part]
    after_file = checks_json(project)
    again = runner.check_all(slug, cached=False)
    assert after["rows"] == again["rows"] and checks_json(project) == after_file


def test_the_edit_hooks_part_check_agrees_with_and_without_the_cache_on_a_machine(tmp_path, monkeypatch):
    """The gantry cell: three parts, eight bodies, axes. The part check does not run its sweep."""
    slug = "assembly_cell"
    lay(tmp_path, monkeypatch, slug)
    for part in st.part_names(slug):
        fast = runner.part_check(slug, part, fit=True, cached=True, render=False)
        fast_again = runner.part_check(slug, part, fit=True, cached=True, render=False)
        slow = runner.part_check(slug, part, fit=True, cached=False, render=False)
        assert fast["rows"] == slow["rows"] == fast_again["rows"], part
        assert fast["scope"] == slow["scope"] and [r for r in fast["rows"] if r["check"] == "fit"], part
        assert [b["how"] for b in fast_again["builds"]] == ["cache"] * 3, part

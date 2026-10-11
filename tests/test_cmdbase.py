"""The command contract (cmdbase.py) and the commands of step 6 that are not built yet.

A command another piece of step 6 builds has a parser entry now. It is listed in `cad --help`,
parsed, and answers exit 3 "not built yet" until the module LAZY names for it exists; then the
module's handler runs and its ARGUMENTS shape the parser. None of that may cost the CLI the CAD
kernel, so the first test holds the import and the parse to a process that never loads it.
"""
import dataclasses
import json
import subprocess
import sys
import textwrap
import types
from pathlib import Path

import pytest

from cad_agent import cli, cmdbase, warm
from cad_agent import state as st
from cad_agent.cmdbase import LAZY, OK, Result
from conftest import cad_env

REPO = Path(__file__).resolve().parent.parent
BASE_COMMANDS = ("bom", "shop", "drawing", "lib ls", "lib info", "lib add", "lib use", "lib check", "lib fetch")


def not_built(command):
    """Whether no module has filled this command in: the ones whose behaviour is 'not built yet'."""
    return cmdbase.resolve(LAZY[command].target) is None


def run(capsys, *argv):
    """Run with --json; return (exit code, parsed stdout object or None, stderr)."""
    code = cli.main(["--json", *argv])
    out, err = capsys.readouterr()
    lines = [ln for ln in out.splitlines() if ln.startswith("{")]
    return code, (json.loads(lines[-1]) if lines else None), err


# ─── The table ───────────────────────────────────────────────────────────────

def test_the_table_lists_every_command_step_6_adds():
    assert set(BASE_COMMANDS) <= set(LAZY)
    for command, lazy in LAZY.items():
        assert lazy.command == command
        module, _, function = lazy.target.partition(":")
        assert module.startswith("cad_agent.") and function.startswith("cmd_"), lazy.target
        assert lazy.piece in {"A", "B", "C1", "C2", "D", "E"}
        assert lazy.help and not lazy.help.endswith("."), command


@pytest.mark.parametrize("command", sorted(LAZY))
def test_every_new_command_has_a_parser_entry(command, capsys):
    assert cli.main([*command.split(), "--help"]) == OK
    out, _ = capsys.readouterr()
    assert command.split()[-1] in out


def test_the_help_lists_the_new_commands(capsys):
    assert cli.main(["--help"]) == OK
    out, _ = capsys.readouterr()
    for word in ("bom", "shop", "drawing", "lib"):
        assert f"\n    {word} " in out, word
    assert cli.main(["lib", "--help"]) == OK
    out, _ = capsys.readouterr()
    assert all(f"\n    {c.split()[1]} " in out for c in LAZY if c.startswith("lib "))


def test_the_cli_and_its_parse_never_import_the_cad_kernel():
    # `cad --help`, `cad ls` and the first word of every command must not wait for build123d: the
    # handlers of the new commands are imported when they run, not when the parser is built.
    code = ("import sys\n"
            "from cad_agent import cli\n"
            "cli.main(['lib', '--help'])\n"
            "cli.main(['shop', '--help'])\n"
            "print(sorted(m for m in ('build123d', 'OCP', 'numpy', 'ezdxf', 'lib3mf') if m in sys.modules))\n")
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
                       env=cad_env(PYTHONPATH=str(REPO)), cwd=str(REPO))
    assert p.returncode == 0, p.stderr
    assert p.stdout.strip().splitlines()[-1] == "[]"


# ─── Not built yet ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("command", [c for c in sorted(LAZY) if not_built(c)] or [pytest.param(
    "bom", marks=pytest.mark.skip(reason="every command has been built"))])
def test_a_command_that_is_not_built_answers_exit_3_and_says_so(command, capsys):
    code, out, err = run(capsys, *command.split(), "demo")
    assert code == cmdbase.USAGE == 3
    assert out["exit"] == 3 and out["data"]["not_built"] is True
    assert "not built yet" in out["data"]["error"] and LAZY[command].target in out["data"]["error"]
    assert f"cad {command}: not built yet" in err


def test_a_command_that_is_not_built_takes_any_arguments(capsys):
    # Not "unrecognized arguments": the command is what is missing, not the way it was called.
    for command in ("shop", "lib use"):
        if not not_built(command):
            continue
        code, out, err = run(capsys, *command.split(), "demo", "part", "--draft", "--as", "x", "-q")
        assert code == 3 and out["data"]["not_built"] is True, err
        assert "unrecognized" not in err


def test_not_built_is_not_a_crash_or_a_verdict(capsys):
    # exit 3 is "usage", so a script that gates on 0/1/2 never mistakes a missing command for a design result
    for command in ("bom", "drawing"):
        if not_built(command):
            code, out, _ = run(capsys, command, "demo")
            assert code == 3 and "traceback" not in json.dumps(out).lower()


# ─── A module that exists ────────────────────────────────────────────────────

@pytest.fixture()
def fake_shop(monkeypatch):
    """A cad_agent-free module standing in for the piece that builds `cad shop`."""
    mod = types.ModuleType("fake_shop_module")
    seen = []

    def cmd_shop(a):
        seen.append(a)
        return Result(OK, {"slug": a.slug, "draft": a.draft, "check": a.check}, f"shop {a.slug}", "wrote it")

    def add_shop_arguments(parser):
        parser.add_argument("slug")
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--draft", action="store_true")
        mode.add_argument("--check", action="store_true")

    mod.cmd_shop, mod.ARGUMENTS, mod.seen = cmd_shop, {"shop": add_shop_arguments}, seen
    monkeypatch.setitem(sys.modules, "fake_shop_module", mod)
    monkeypatch.setitem(LAZY, "shop", dataclasses.replace(LAZY["shop"], target="fake_shop_module:cmd_shop"))
    return mod


def test_a_built_command_is_handled_by_its_module_with_its_own_arguments(fake_shop, capsys):
    code, out, _ = run(capsys, "shop", "demo", "--draft")
    assert code == OK
    assert out["cmd"] == "shop" and out["data"] == {"slug": "demo", "draft": True, "check": False}
    assert fake_shop.seen[0].cmd_name == "shop"


def test_the_arguments_a_module_declares_are_enforced(fake_shop, capsys):
    code, out, err = run(capsys, "shop", "demo", "--draft", "--check")
    assert code == 3 and out is None and "not allowed with" in err        # argparse's own mutual exclusion
    code, out, err = run(capsys, "shop")
    assert code == 3 and "slug" in err
    assert not fake_shop.seen


def test_the_help_of_a_built_command_shows_the_module_arguments(fake_shop, capsys):
    assert cli.main(["shop", "--help"]) == OK
    out, _ = capsys.readouterr()
    assert "--draft" in out and "--check" in out


def test_a_module_without_the_function_is_still_not_built(monkeypatch, capsys):
    mod = types.ModuleType("half_built_module")                 # the file is there, the handler is not
    monkeypatch.setitem(sys.modules, "half_built_module", mod)
    monkeypatch.setitem(LAZY, "bom", dataclasses.replace(LAZY["bom"], target="half_built_module:cmd_bom"))
    code, out, _ = run(capsys, "bom", "demo")
    assert code == 3 and out["data"]["not_built"] is True


def test_a_nested_command_goes_to_its_own_handler(monkeypatch, capsys):
    mod = types.ModuleType("fake_lib_module")
    mod.cmd_lib_info = lambda a: Result(OK, {"name": a.name}, a.name, "info")
    mod.ARGUMENTS = {"lib info": lambda p: p.add_argument("name")}
    monkeypatch.setitem(sys.modules, "fake_lib_module", mod)
    monkeypatch.setitem(LAZY, "lib info", dataclasses.replace(LAZY["lib info"], target="fake_lib_module:cmd_lib_info"))
    code, out, _ = run(capsys, "lib", "info", "mgn12")
    assert code == OK and out["cmd"] == "lib info" and out["data"] == {"name": "mgn12"}


# ─── Resolving a target ──────────────────────────────────────────────────────

def test_resolve_finds_an_object_and_says_none_for_a_module_not_there_yet():
    assert cmdbase.resolve("cad_agent.cmdbase:Result") is Result
    assert cmdbase.resolve("cad_agent.cmdbase:no_such_function") is None
    assert cmdbase.resolve("cad_agent.no_such_module:cmd_x") is None
    assert cmdbase.resolve("cad_agent.no_such_package.cli:cmd_x") is None          # a parent that is absent too


def test_a_module_that_cannot_import_something_else_is_a_crash_not_not_built(tmp_path, monkeypatch):
    # The difference matters: a half-built piece must fail loudly, not hide behind "not built yet".
    (tmp_path / "broken_piece.py").write_text("import a_dependency_nobody_has\n\n\ndef cmd_x(a):\n    pass\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    with pytest.raises(ModuleNotFoundError) as e:
        cmdbase.resolve("broken_piece:cmd_x")
    assert e.value.name == "a_dependency_nobody_has"


# ─── What cli.py keeps ───────────────────────────────────────────────────────

def test_cli_keeps_the_names_the_contract_moved_out():
    for name in ("OK", "FAIL", "UNCHECKED", "USAGE", "CRASH", "EXIT_CODES", "Result", "UsageError",
                 "BuildFailed", "WorkbenchDown", "NotBuilt"):
        assert getattr(cli, name) is getattr(cmdbase, name), name
    for old, new in (("_project", "project"), ("_part", "part"), ("_pairs", "pairs"), ("_value", "value"),
                     ("_views", "views"), ("_verdict", "verdict"), ("_rows_text", "rows_text"),
                     ("_builds", "builds"), ("_build", "build"), ("_assembly", "assembly"),
                     ("_overrides", "overrides"), ("_actor", "actor"), ("_from_cache", "from_cache"),
                     ("_tolerance", "tolerance"), ("_Parser", "Parser")):
        assert getattr(cli, old) is getattr(cmdbase, new), old
    assert issubclass(cmdbase.NotBuilt, cmdbase.UsageError)


def test_verdict_ranks_fail_over_unchecked_over_ok():
    assert cmdbase.verdict(["PASS", "N/A"]) == cmdbase.OK
    assert cmdbase.verdict(["PASS", "UNCHECKED"]) == cmdbase.UNCHECKED
    assert cmdbase.verdict(["UNCHECKED", "FAIL"]) == cmdbase.FAIL
    assert cmdbase.verdict([]) == cmdbase.OK


def test_pairs_and_value_read_what_a_person_means():
    assert cmdbase.pairs(["a=5", "b=true", "c=[1, 2]", "d=hello"], "t") == {"a": 5, "b": True, "c": [1, 2], "d": "hello"}
    with pytest.raises(cmdbase.UsageError):
        cmdbase.pairs(["no_equals"], "tool")


def test_a_project_that_is_not_there_is_a_usage_error_naming_the_ones_that_are(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "ROOT", tmp_path)
    (tmp_path / "alpha").mkdir()
    with pytest.raises(cmdbase.UsageError) as e:
        cmdbase.project("beta")
    assert "alpha" in str(e.value)


# ─── export, and the worker ──────────────────────────────────────────────────

PART = textwrap.dedent('''\
    """A plate."""
    from build123d import Box

    MATERIAL = "petg"
    PROCESS = "fdm"
    MIN_FEATURE_MM = 1.2
    PARAMS = {}


    def build():
        return Box(30, 20, 4)
''')


@pytest.fixture()
def plate_project(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "ROOT", tmp_path)
    monkeypatch.delenv("CAD_PROJECTS", raising=False)
    d = st.project_dir("demo", create=True)
    (d / "parts" / "plate.py").write_text(PART)
    return d


def test_export_accepts_every_format_and_says_not_built_for_the_ones_that_are_not(plate_project, capsys):
    from cad_agent import export
    assert set(export.FORMATS) <= set(cli.EXPORT_FORMATS) == {"step", "stl", "3mf", "dxf"}
    assert {"step", "stl"} <= set(export.FORMATS)
    for fmt in cli.EXPORT_FORMATS:
        code, out, err = run(capsys, "export", "demo", "plate", "--format", fmt)
        if fmt in ("step", "stl"):
            assert code == OK and out["data"]["format"] == fmt, err
            assert (plate_project / "out" / f"plate.{fmt}").exists()
        elif fmt not in export.FORMATS:
            assert code == 3 and out["data"]["not_built"] is True
            assert f"--format {fmt} is not built yet" in err and not (plate_project / "out" / f"plate.{fmt}").exists()


def test_export_checks_the_part_before_the_format(plate_project, capsys):
    code, out, err = run(capsys, "export", "demo", "nope", "--format", "dxf")
    assert code == 3 and "no part 'nope'" in err and "not_built" not in out["data"]


def test_the_warm_worker_passes_the_library_variable_and_serves_lib_without_the_kernel():
    assert "CAD_LIBRARY" in warm.ENV_PASS
    assert warm._command(["--json", "lib", "ls"]) in warm.KERNEL_FREE
    assert warm._command(["shop", "x"]) not in warm.KERNEL_FREE

"""The command contract: what a `cad` command is, how it ends, and how one that is not built yet answers.

cli.py held all of this next to the commands, so a module that wanted to add a command had to import
cli.py, which imports every other command. Everything a handler needs lives here now, and cli.py
imports it back under the names it always had.

A handler is a function `handler(a) -> Result`, where `a` is the argparse namespace. It does the work
and returns a Result; it never prints and never calls sys.exit. How it ends is the exit code, which is
the verdict (see EXIT_CODES): raise UsageError for a bad argument or an unknown project, part or
name, BuildFailed when the design failed (not the tool), and let anything unexpected escape, which
`cli.main` turns into 4. `Result.data` is what `--json` prints, `text` is what a terminal shows,
`summary` is one line for the activity log, and `files` lists what the command wrote.

New commands (step 6)
---------------------
The commands of step 6 are declared in LAZY, one row each, with the module and function that will
handle them. cli.py has a parser entry for every row, so `cad --help` lists them and `cad shop x`
parses, but the handler is only imported when the command is run, and a handler that is not there
yet answers exit 3 "not built yet". To build one:

  1. write `cmd_x(a) -> Result` in the module LAZY names. Import from here (project, part, verdict,
     rows_text, builds, ...), not from cli.py;
  2. give it its arguments by adding the command to the module's ARGUMENTS dict:

         ARGUMENTS = {"shop": add_shop_arguments}      # command as typed -> fn(parser)

     The parser the function gets already has `--json` and `--projects`. It is called only when that
     command is run or its --help is shown, so a module that imports the CAD kernel costs nothing
     for `cad ls`. Until the module exists, the command takes any arguments and answers "not built
     yet";
  3. nothing else: no edit to cli.py, and the file that holds the handler is the piece's own.

A command with a sub-command (`cad lib use`) is two words in LAZY: "lib use". A module with the file
but not the function yet is still "not built"; one that fails to import anything else raises, so a half
built piece is a crash with a traceback and not a quiet exit 3. Do not add `--json` or `--projects`: the
parser has them. A command that changes a project's files journals the change (`undo.record(...,
by=actor(a))`, as `cad bought add-step` does), and one that reads no geometry should not import the CAD
kernel at module level (`lib` is in warm.KERNEL_FREE and answers without a worker). Name the tests
`tests/test_<piece>.py` so `tests/affected.py` finds them from the module's name.
"""
from __future__ import annotations

import argparse
import contextlib
import importlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import state as st

OK, FAIL, UNCHECKED, USAGE, CRASH = 0, 1, 2, 3, 4

EXIT_CODES = """exit codes:
  0  ok        every row PASS or N/A, or the query succeeded
  1  FAIL      a gate failed, parts interfere, or a part did not build
  2  UNCHECKED something could not be settled (not a pass)
  3  usage     bad arguments, unknown project, part or tool
  4  crash     unexpected exception in cad-agent"""


class UsageError(Exception):
    """Bad arguments, or a project, part or tool that does not exist."""


class NotBuilt(UsageError):
    """A command, or an option of one, that a later piece of step 6 builds (LAZY, below)."""


class BuildFailed(Exception):
    """A part module raised: the design failed, not the tool."""


class WorkbenchDown(Exception):
    """`cad gui` found no running workbench to answer for a project: UNCHECKED,
    not a usage error — the command was fine, the workbench just is not up."""


@dataclass
class Result:
    code: int
    data: dict
    text: str
    summary: str = ""
    files: list = field(default_factory=list)


# ─── Argument and lookup helpers ─────────────────────────────────────────────

def value(text: str):
    """Read a value the way a person means it: 5 is a number, true a bool,
    [1, 2] a list, anything else a string."""
    try:
        return json.loads(text)
    except ValueError:
        return text


def pairs(items, what: str) -> dict:
    out = {}
    for item in items or []:
        key, sep, raw = item.partition("=")
        if not sep or not key:
            raise UsageError(f"{what} takes key=value, got {item!r}")
        out[key] = value(raw)
    return out


def project(slug: str) -> Path:
    try:
        return st.project_dir(slug)
    except FileNotFoundError:
        have = ", ".join(st.list_projects()) or "none"
        raise UsageError(f"no project {slug!r} (projects: {have})") from None


def part(slug: str, name: str) -> Path:
    path = project(slug) / "parts" / f"{name}.py"
    if not path.exists():
        have = ", ".join(st.part_names(slug)) or "none"
        raise UsageError(f"no part {name!r} in {slug} (parts: {have})")
    return path


def views(text: str) -> tuple[str, ...]:
    """A comma list of views for check, verify and approve, each one the renderer draws."""
    from .render import VIEWS
    names = tuple(v.strip() for v in text.split(",") if v.strip()) or ("iso",)
    bad = [v for v in names if v not in VIEWS]
    if bad:
        raise UsageError(f"unknown view {', '.join(repr(v) for v in bad)} "
                         f"(views: {', '.join(sorted(VIEWS))})")
    return names


def tolerance(number: float | None) -> None:
    """--tolerance is the tessellation tolerance in mm: the mesher fails on zero or less."""
    if number is not None and not 0 < number < float("inf"):
        raise UsageError(f"--tolerance is the tessellation tolerance in mm and must be above 0, "
                         f"got {number:g}")


def actor(a) -> str:
    """Who to journal a change under: `--actor` when the caller passed it
    (the workbench server adds it to every command it runs; see undo.record's
    docstring), else undo.actor()'s own CAD_ACTOR-env fallback (default
    "agent")."""
    from . import undo as un
    return a.actor or un.actor()


def overrides(a) -> dict:
    """--set values, checked against the part's PARAMS so a typo is a usage
    error naming the real parameters rather than a TypeError from build()."""
    ov = pairs(getattr(a, "set", None), "--set")
    if not ov:
        return {}
    if not getattr(a, "part", None):
        raise UsageError("--set changes one part's PARAMS; name the part")
    path = part(a.slug, a.part)
    try:
        defaults = dict(getattr(st._load_module(path), "PARAMS", {}))
    except Exception as e:
        raise BuildFailed(f"{a.part} did not load: {st.why(e)}") from e
    unknown = sorted(set(ov) - set(defaults))
    if unknown:
        raise UsageError(f"{a.part} has no parameter {', '.join(unknown)} "
                         f"(params: {', '.join(sorted(defaults))})")
    from .params import ParamError, coerce
    for key, v in list(ov.items()):              # a number where the part has a number, as `cad set`
        if isinstance(defaults[key], (bool, int, float)):
            try:
                ov[key] = coerce(key, defaults[key], v)
            except ParamError as e:
                raise UsageError(str(e)) from None
    return ov


def build(slug: str, name: str, ov: dict | None = None):
    """(solid, meta) of one part; a part that raises is BuildFailed."""
    part(slug, name)
    try:
        return st.build_part(slug, name, ov)
    except Exception as e:
        raise BuildFailed(f"{name} did not build: {st.why(e)}") from e


def assembly(slug: str) -> dict:
    """The bodies assembly.py places, with placements.toml applied; UsageError if it has none."""
    project(slug)
    try:
        asm, *_ = st.load_assembly(slug)
    except Exception as e:
        raise BuildFailed(f"{slug} assembly did not build: {st.why(e)}") from e
    if asm is None:
        raise UsageError(f"{slug} has no assembly.py")
    return asm


@contextlib.contextmanager
def builds(a):
    """The scope the edit loop's commands build parts in: a part got once is copied, and unless
    --no-cache it comes from the project's build cache and goes back into it. Yields the log of
    builds. `verify` does not use this; see buildcache.py."""
    with st.reusing_builds() as log, st.caching_builds(not getattr(a, "no_cache", False)):
        yield log


def from_cache(log) -> str:
    """A line on where a run's parts came from, when some came from the build cache."""
    cached = [b["part"] for b in log if b["how"] == "cache"]
    if not cached:
        return ""
    built = [b["part"] for b in log if b["how"] == "built"]
    return (f"build cache: {len(cached)} of {len(cached) + len(built)} parts reused"
            + (f", built {', '.join(built)}" if built else ""))


def verdict(states) -> int:
    """The exit code a set of row states adds up to: FAIL outranks UNCHECKED outranks OK."""
    states = set(states)
    if "FAIL" in states:
        return FAIL
    if "UNCHECKED" in states:
        return UNCHECKED
    return OK


def rows_text(rows, show_all: bool) -> list[str]:
    shown = rows if show_all else [r for r in rows if r["state"] != "PASS"]
    lines = []
    for r in shown:
        rule = f"{r['check']}/{r['rule']}" if r.get("check") else r["rule"]
        limit = r.get("limit")
        tail = f"   [limit {limit}]" if limit not in (None, "n/a") else ""
        lines.append(f"  {r['state']:9} {rule:24} {r['subject']:20} {r['measured']}{tail}")
    if len(shown) < len(rows):
        lines.append(f"  ({len(rows) - len(shown)} passing rows hidden; --all shows them)")
    return lines


# ─── Commands another module builds ──────────────────────────────────────────

@dataclass(frozen=True)
class Lazy:
    command: str     # as typed after `cad`: "shop", "lib use"
    target: str      # "package.module:function", the handler; imported when the command runs
    piece: str       # the step 6 piece that builds it, for the "not built yet" message
    help: str        # the one line `cad --help` shows


# What the plan (docs/STEP6_PLAN.md) calls the pieces: A library, D shop outputs, E drawings.
LAZY: dict[str, Lazy] = {c.command: c for c in (
    Lazy("lib ls", "cad_agent.library.cli:cmd_lib_ls", "A",
         "the library: what it holds, what is shipped and what is in your own store"),
    Lazy("lib info", "cad_agent.library.cli:cmd_lib_info", "A",
         "one library part: vendor, part number, licence, datum, mass, hash and where it came from"),
    Lazy("lib add", "cad_agent.library.cli:cmd_lib_add", "A",
         "put a vendor STEP you downloaded by hand in your own store, checked against the catalog"),
    Lazy("lib use", "cad_agent.library.cli:cmd_lib_use", "A",
         "copy a library part into a project's bought/ with its sidecar (source, hash, datum, mass)"),
    Lazy("lib check", "cad_agent.library.cli:cmd_lib_check", "A",
         "check the store's files against the catalog's hashes, and a project's bought parts against the library"),
    Lazy("lib fetch", "cad_agent.library.cli:cmd_lib_fetch", "A",
         "download a library part where its licence allows it"),
    Lazy("bom", "cad_agent.bom:cmd_bom", "D",
         "the bill of materials of a project's assembly: kind, material, process, vendor, part number, mass"),
    Lazy("shop", "cad_agent.shop:cmd_shop", "D",
         "write out/shop/ for a verified design: DXF, 3MF, STL, STEP, drawings and the BOM"),
    Lazy("drawing", "cad_agent.drawing:cmd_drawing", "E",
         "a dimensioned drawing of one machined part"),
)}


def resolve(target: str):
    """The function or object at "package.module:name", or None when it is not there yet.

    Only the target's own module (or a package above it) being absent counts as "not there": a module
    that exists but fails to import something else raises, so a half-built piece is a crash with a
    traceback and not a command that quietly says it is not built.
    """
    module, _, attr = target.partition(":")
    try:
        mod = importlib.import_module(module)
    except ModuleNotFoundError as e:
        if e.name and (module == e.name or module.startswith(e.name + ".")):
            return None
        raise
    return getattr(mod, attr, None)


def handler(command: str) -> Callable:
    """The handler cli.py registers for a LAZY command: it finds the real one when the command runs."""
    lazy = LAZY[command]

    def run(a) -> Result:
        fn = resolve(lazy.target)
        if fn is None:
            raise NotBuilt(f"not built yet (step 6, piece {lazy.piece}; its handler is {lazy.target})")
        return fn(a)
    run.__name__ = "lazy_" + command.replace(" ", "_")
    run.__doc__ = lazy.help
    return run


def extend_arguments(parser, command: str) -> bool:
    """Give a LAZY command's parser the arguments its module declares. False: the module has none yet."""
    module = LAZY[command].target.partition(":")[0]
    table = resolve(f"{module}:ARGUMENTS")
    add_arguments = table.get(command) if isinstance(table, dict) else None
    if add_arguments is None:
        return False
    add_arguments(parser)
    return True


class Parser(argparse.ArgumentParser):
    """argparse exits 2 on bad arguments; 2 means UNCHECKED here, so use 3.

    A parser with `lazy_command` set is a LAZY command's. Its arguments come from the module that
    builds the command, when the command is parsed or its help shown and not before; while there is
    no such module it takes any arguments, so that `cad shop x --draft` says "not built yet" and not
    "unrecognized arguments".
    """
    lazy_command: str | None = None
    _lazy_filled = False
    _lazy_built = False

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(USAGE, f"{self.prog}: error: {message}\n")

    def _fill_lazy(self) -> None:
        if self.lazy_command and not self._lazy_filled:
            self._lazy_filled = True
            self._lazy_built = extend_arguments(self, self.lazy_command)

    def parse_known_args(self, args=None, namespace=None):
        self._fill_lazy()
        ns, extra = super().parse_known_args(args, namespace)
        if self.lazy_command and not self._lazy_built:
            return ns, []
        return ns, extra

    def format_help(self):
        self._fill_lazy()
        return super().format_help()

    def format_usage(self):
        self._fill_lazy()
        return super().format_usage()

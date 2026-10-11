"""The two places step 6 adds to without editing a shared file: spec kinds and rules.

A section of spec.toml is a kind registered with `@spec_kind` in its own module of
cad_agent/speckinds/, and a rule is a module of cad_agent/ruleset/. Both packages are imported whole
(`registry.autoload`), so a piece of step 6 adds a file and nothing else. These tests hold what the
pieces rely on: the seven kinds that moved keep their rows in the order they had, a new kind is
run, guarded and ordered like those, and a module that cannot load is a crash and not a rule that
quietly went missing.
"""
import sys
import textwrap
from pathlib import Path

import pytest

from cad_agent import registry as reg
from cad_agent import spec as sp
from cad_agent import speckinds
from cad_agent.registry import Row, SpecCtx, spec_kind
from cad_agent.speckinds.kit import Unusable, require, row
from test_spec import bodies, check, rig  # noqa: F401 (the rig fixture)

LEGACY = ("envelope", "size", "position", "clearance", "keepout", "mass", "interface")


@pytest.fixture()
def kinds(monkeypatch):
    """The spec kind registry, to add kinds to and find unchanged afterwards."""
    monkeypatch.setattr(reg, "_SPEC_KINDS", dict(reg._SPEC_KINDS))
    return reg._SPEC_KINDS


# ─── The seven kinds that moved ──────────────────────────────────────────────

def test_the_seven_kinds_are_registered_in_the_order_a_message_lists_them():
    assert reg.spec_kind_names()[:7] == LEGACY
    assert sp.KINDS[:7] == LEGACY
    assert all(k.doc for k in reg.spec_kinds()), "a kind with no docstring cannot say what it judges"


def test_their_rows_come_in_the_order_they_always_did():
    # envelope, then every [[size]], [[position]], [[clearance]], [[keepout]], [[interface]], and [[mass]] last
    order = [k.name for k in reg.spec_kinds() if k.name in LEGACY]
    assert order == ["envelope", "size", "position", "clearance", "keepout", "interface", "mass"]
    assert [k.name for k in reg.spec_kinds() if k.table] == ["envelope"]


def test_a_spec_with_every_section_reports_them_in_that_order(rig):
    text = textwrap.dedent('''\
        [[mass]]
        parts = { top_plate = 1 }
        max_g = 100

        [[interface]]
        a = "top"
        b = "base"

        [[keepout]]
        tool = "drill"
        params = { diameter = 3, flute = 20 }
        clear = ["far"]

        [[clearance]]
        a = "top"
        b = "far"
        min_mm = 1

        [[position]]
        body = "far"
        center_mm = [200, 0, 10]

        [[size]]
        body = "far"
        max_mm = [11, 11, 21]

        [envelope]
        max_mm = [400, 400, 400]
    ''')
    rows = check(rig, text)
    seen = []
    for r in rows:
        if not seen or seen[-1] != r.rule:
            seen.append(r.rule)
    assert seen == ["spec/envelope", "spec/size", "spec/position", "spec/clearance", "spec/keepout",
                    "spec/interface", "spec/mass"]
    assert [r.source for r in rows if r.rule == "spec/envelope"] == ["spec.toml"]
    assert [r.source for r in rows if r.rule == "spec/size"] == ["spec.toml [[size]] #1"]


def test_the_unknown_section_message_lists_the_kinds_as_it_always_did(rig):
    rows = check(rig, "[nonsense]\nx = 1\n")
    assert rows[0].limit == "one of envelope, size, position, clearance, keepout, mass, interface"
    assert rows[0].measured == "unknown section [nonsense]" and rows[-1].limit.startswith("at least one of envelope")


def test_what_spec_used_to_define_can_still_be_imported_from_it():
    from cad_agent.speckinds import interface, keepout
    assert sp.holes is interface.holes
    assert sp.TOOLS is keepout.TOOLS and "laser_cone" in sp.TOOLS
    # checks/cuts.py and evals/pcb_enclosure/reference/parts/base.py do exactly this
    from cad_agent.spec import holes
    assert holes is interface.holes


# ─── A kind of its own ───────────────────────────────────────────────────────

def test_a_new_kind_is_run_on_every_entry_with_the_context(rig, kinds):
    seen = []

    @spec_kind("probe", order=15)
    def probe(entry, ctx):
        """A kind the test adds."""
        seen.append((entry, ctx))
        yield row(entry["name"], "probe", "PASS", f"{len(ctx.parts)} bodies", "n/a")

    assert reg.spec_kind_names()[-1] == "probe" and sp.KINDS[-1] == "probe"
    rows = check(rig, '[[probe]]\nname = "a"\n[[probe]]\nname = "b"\n')
    assert [(r.subject, r.rule, r.state, r.source) for r in rows] == [
        ("a", "spec/probe", "PASS", "spec.toml [[probe]] #1"), ("b", "spec/probe", "PASS", "spec.toml [[probe]] #2")]
    ctx = seen[0][1]
    assert isinstance(ctx, SpecCtx) and ctx.slug == "rig" and set(ctx.parts) == {"top", "base", "far"}
    assert ctx.machine is None


def test_a_new_kind_slots_in_by_order_and_a_table_kind_is_judged_once(rig, kinds):
    @spec_kind("early", order=1, table=True)
    def early(entry, ctx):
        yield row("assembly", "early", "PASS", entry["note"])

    @spec_kind("late", order=99)
    def late(entry, ctx):
        yield row("assembly", "late", "PASS", "late")

    rows = check(rig, '[[late]]\nx = 1\n[early]\nnote = "hi"\n[[size]]\nbody = "far"\nmax_mm = [11, 11, 21]\n')
    assert [r.rule for r in rows] == ["spec/early", "spec/size", "spec/late"]
    assert rows[0].measured == "hi" and rows[0].source == "spec.toml"


def test_the_machine_reaches_the_kind(rig, kinds):
    got = []

    @spec_kind("probe")
    def probe(entry, ctx):
        got.append(ctx.machine)
        return []

    machine = object()
    (rig / "spec.toml").write_text("[[probe]]\nx = 1\n")
    list(sp.check_spec("rig", bodies(), machine=machine))
    assert got == [machine]


def test_an_entry_a_kind_cannot_use_is_one_unchecked_row_and_the_rest_still_run(rig, kinds):
    @spec_kind("picky", order=5)
    def picky(entry, ctx):
        if entry.get("boom"):
            raise RuntimeError("went wrong")
        yield row("x", "picky", "PASS", str(require(entry, "need", "[[picky]]")))

    rows = check(rig, '[[picky]]\nneed = 1\n[[picky]]\nx = 2\n[[picky]]\nboom = true\n'
                      '[[size]]\nbody = "far"\nmax_mm = [11, 11, 21]\n')
    assert [(r.state, r.subject) for r in rows] == [
        ("PASS", "x"), ("UNCHECKED", "[[picky]] #2"), ("UNCHECKED", "[[picky]] #3"), ("PASS", "far")]
    assert rows[1].measured == "[[picky]] is missing `need`"
    assert rows[2].measured == "RuntimeError: went wrong"
    assert Unusable.__mro__[1] is Exception


def test_a_kind_registered_twice_or_badly_named_is_refused(kinds):
    with pytest.raises(ValueError, match="already registered"):
        spec_kind("size")(lambda entry, ctx: [])
    for bad in ("Heat", "two words", "heat-load", ""):
        with pytest.raises(ValueError, match="lower-case TOML key"):
            spec_kind(bad)


def test_a_kind_nobody_registered_is_unchecked_not_ignored(rig):
    rows = check(rig, '[[heat]]\nsource = "x"\n[[size]]\nbody = "far"\nmax_mm = [11, 11, 21]\n')
    assert (rows[0].rule, rows[0].state, rows[0].measured) == ("spec/heat", "UNCHECKED", "unknown section [heat]")


# ─── Finding the modules ─────────────────────────────────────────────────────

@pytest.fixture()
def pkg(tmp_path, monkeypatch):
    """A package on disk to autoload: a, first, z and a _helper that is left alone."""
    root = tmp_path / "scratch_pkg"
    root.mkdir()
    (root / "__init__.py").write_text("")
    for name in ("a", "first", "z", "_helper"):
        (root / f"{name}.py").write_text(f"LOADED = '{name}'\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    yield root
    for name in [m for m in sys.modules if m == "scratch_pkg" or m.startswith("scratch_pkg.")]:
        del sys.modules[name]


def test_autoload_imports_the_first_modules_in_order_then_the_rest_by_name(pkg):
    assert reg.autoload("scratch_pkg", first=("z",)) == ["z", "a", "first"]
    assert sys.modules["scratch_pkg.z"].LOADED == "z"
    assert "scratch_pkg._helper" not in sys.modules                  # a leading underscore is a helper


def test_autoload_lets_a_module_that_cannot_load_raise(pkg):
    (pkg / "broken.py").write_text("raise RuntimeError('this module is a bug')\n")
    with pytest.raises(RuntimeError, match="this module is a bug"):
        reg.autoload("scratch_pkg")


# ─── Rules ───────────────────────────────────────────────────────────────────

def test_the_rules_written_before_step_6_are_all_still_registered():
    from cad_agent import rules  # noqa: F401
    names = {c.name for c in reg.checks()}
    assert {"geometry", "visual", "fit", "stance", "provenance", "sweep", "reach", "spec", "placements"} <= names


def test_rules_imports_every_module_of_the_ruleset_folder():
    from cad_agent import rules, ruleset
    folder = Path(ruleset.__file__).parent
    on_disk = sorted(p.stem for p in folder.glob("*.py") if not p.stem.startswith("_"))
    assert ruleset.MODULES == on_disk
    assert all(f"cad_agent.ruleset.{name}" in sys.modules for name in on_disk)
    assert rules.ruleset is ruleset


def test_a_module_dropped_into_a_ruleset_folder_registers_its_rule(tmp_path, monkeypatch):
    # The same thing cad_agent/ruleset does, on a folder of this test's own: a file is a rule.
    monkeypatch.setattr(reg, "_CHECKS", list(reg._CHECKS))
    root = tmp_path / "scratch_rules"
    root.mkdir()
    (root / "__init__.py").write_text("")
    (root / "heat.py").write_text(textwrap.dedent('''\
        from cad_agent.registry import Row, register

        @register(scope="project", name="scratch_heat", order=90)
        def scratch_heat(ctx):
            """A rule that lives in its own file."""
            yield Row(subject=ctx.slug, rule="scratch", state="PASS")
    '''))
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        assert reg.autoload("scratch_rules") == ["heat"]
        spec = next(c for c in reg.checks("project") if c.name == "scratch_heat")
        assert spec.doc == "A rule that lives in its own file." and spec.order == 90
        rows = reg.run(spec, reg.ProjectCtx(slug="demo", dir=tmp_path, parts={}, out_dir=tmp_path))
        assert [(r.check, r.rule, r.state) for r in rows] == [("scratch_heat", "scratch", "PASS")]
    finally:
        for name in [m for m in sys.modules if m.startswith("scratch_rules")]:
            del sys.modules[name]


def test_the_assembly_context_carries_the_machine_and_defaults_to_none():
    ctx = reg.AssemblyCtx(slug="s", parts={}, clearance={}, allow_contact=set(), out_dir=Path("."))
    assert ctx.machine is None
    assert reg.AssemblyCtx(slug="s", parts={}, clearance={}, allow_contact=set(), out_dir=Path("."),
                           machine="m").machine == "m"
    assert isinstance(Row(subject="s", rule="r", state="PASS"), Row) and speckinds.MODULES[:7] == list(LEGACY)

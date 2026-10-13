"""The check registry: adding a verifier is one decorated function.

Before this, the runner called fit, then manufacturability, then provenance,
each wired in by hand and each reporting a different row shape. Adding a rule
meant editing the runner, the gate, and the report generator. That is the
opposite of a loop you can extend while you work.

Now a check declares its scope and returns rows in one shape:

    @register(scope="part", name="web")
    def web_rule(ctx):
        yield Row(subject=ctx.name, rule="web", state="PASS", ...)

Scopes decide what the runner hands you:

    part       once per part, with the built solid and its declarations
    assembly   once, with every positioned solid and the clearance table
    project    once, with the whole project directory

A check is a function in a module of cad_agent/ruleset/, which rules.py imports with the rest: a new
rule is one new file there, and no other file changes (`autoload`, below, finds it).

The same holds for the sections of a project's spec.toml. A kind judges one entry of one section and
registers itself with `spec_kind`:

    @spec_kind("heat", order=80)
    def heat(entry, ctx):
        yield Row(...)

and lives in its own module of cad_agent/speckinds/ (see speckinds/kit.py for what a kind uses).

Three rules the shape enforces, because they are what make a gate worth
having:

  A state is PASS, FAIL, UNCHECKED or N/A. There is no fifth, and UNCHECKED
  is not a pass: it means a rule could not be settled, which fails the gate
  exactly as a failure does.

  N/A means the rule does not apply to this subject, which is different from
  not knowing. A flat-part rule on a solid block is N/A; the same rule with
  no baseline to compare against is UNCHECKED.

  Every row names its limit and where that limit came from, so a reader can
  disagree with the threshold rather than with the number.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Iterable, Literal

State = Literal["PASS", "FAIL", "UNCHECKED", "N/A"]
Scope = Literal["part", "assembly", "project"]

STATES = ("PASS", "FAIL", "UNCHECKED", "N/A")
FAILING = ("FAIL", "UNCHECKED")   # what holds a project open

# A measured length meets its limit when it misses by no more than this. OCCT's distances carry
# about 1e-7 of noise, so a part placed exactly on a limit would otherwise pass or fail by the
# last digit. Every rule that compares a length to a limit allows it.
TOL_MM = 1e-6


@dataclass
class Row:
    """One verdict. `measured` and `limit` are strings so a row can carry
    a coordinate or a count as readily as a number."""
    subject: str
    rule: str
    state: State
    measured: str = ""
    limit: str = "n/a"
    source: str = ""
    check: str = ""            # filled in by the runner
    artifacts: list = field(default_factory=list)   # paths a reader can open, from the project folder (checks.json is committed)

    def __post_init__(self):
        if self.state not in STATES:
            raise ValueError(
                f"state must be one of {STATES}, not {self.state!r}; "
                "a rule that could not be settled is UNCHECKED, and one that "
                "does not apply is N/A")

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class PartCtx:
    slug: str
    name: str
    solid: Any
    meta: dict
    out_dir: Any
    # Per-run knobs a caller can turn down, e.g. skipping the ray-cast wall
    # measurement during a parameter search. Empty means full fidelity, which
    # is what every gate run uses.
    opts: dict = field(default_factory=dict)


@dataclass
class AssemblyCtx:
    slug: str
    parts: dict
    clearance: dict
    allow_contact: set
    out_dir: Any
    axes: dict = field(default_factory=dict)
    # The bodies.Assembly that parts, clearance, allow_contact and axes came from, with what else
    # assembly.py declares: poses, the BodyInfo of every body, sub-assemblies. None when the project
    # has no assembly.py or a caller built this context by hand.
    machine: Any = None


@dataclass
class ProjectCtx:
    slug: str
    dir: Any
    parts: dict
    out_dir: Any


@dataclass
class CheckSpec:
    name: str
    scope: Scope
    fn: Callable
    doc: str
    order: int


_CHECKS: list[CheckSpec] = []


def register(scope: Scope, name: str | None = None, order: int = 50):
    """Register a check. `order` sorts the report; cheap rules go first."""
    def deco(fn: Callable) -> Callable:
        key = name or fn.__name__
        if any(c.name == key for c in _CHECKS):
            raise ValueError(f"a check named {key!r} is already registered")
        _CHECKS.append(CheckSpec(
            name=key, scope=scope, fn=fn,
            doc=(fn.__doc__ or "").strip().splitlines()[0] if fn.__doc__ else "",
            order=order))
        return fn
    return deco


def checks(scope: Scope | None = None) -> list[CheckSpec]:
    sel = [c for c in _CHECKS if scope is None or c.scope == scope]
    return sorted(sel, key=lambda c: (c.order, c.name))


def run(spec: CheckSpec, ctx) -> list[Row]:
    """Run one check. A check that raises becomes an UNCHECKED row rather
    than killing the run: one broken rule must not hide every other result."""
    try:
        rows = list(spec.fn(ctx) or [])
    except Exception as e:
        subject = getattr(ctx, "name", getattr(ctx, "slug", "?"))
        rows = [Row(subject=subject, rule=spec.name, state="UNCHECKED",
                    measured=f"{type(e).__name__}: {e}",
                    source="the check itself raised; fix the check, not the part")]
    for r in rows:
        r.check = spec.name
    return rows


# ─── The sections of spec.toml ───────────────────────────────────────────────

@dataclass
class SpecCtx:
    """What a spec kind is handed with each entry.

    `parts` is the positioned solids, as the fit rule sees them. `machine` is the bodies.Assembly
    they came from (its poses, axes, children and the BodyInfo of every body), or None when the
    caller only had the solids, as the tests of a kind do; `bodies` is its BodyInfo either way.
    `slug` names the project, for a kind that builds part modules itself.
    """
    slug: str
    parts: dict
    machine: Any = None

    @property
    def bodies(self) -> dict:
        """A BodyInfo for every body: the machine's, or described from the project's files when the
        caller had only the solids (see bodies.py for what each holds)."""
        if self.machine is not None and getattr(self.machine, "bodies", None):
            return self.machine.bodies
        from .bodies import describe
        return describe(self.slug, self.parts)


@dataclass
class SpecKind:
    name: str
    fn: Callable
    order: int
    table: bool
    doc: str


_SPEC_KINDS: dict[str, SpecKind] = {}


def spec_kind(name: str, order: int = 50, table: bool = False):
    """Register a section of spec.toml. The function judges one entry and yields Rows:

        fn(entry: dict, ctx: SpecCtx) -> Iterable[Row]

    `[[name]]` is a list of entries, each judged on its own and reported as `[[name]] #i`; with
    `table=True` the section is one `[name]` table, judged once. `order` is where its rows come among
    the other sections' (ascending, ties by name), and the order sections are *listed* in a message
    is the order they registered in. A name that is registered twice is refused, and so is one that
    would not be a TOML key.
    """
    if not name.isidentifier() or name != name.lower():
        raise ValueError(f"a spec kind is a lower-case TOML key, not {name!r}")

    def deco(fn: Callable) -> Callable:
        if name in _SPEC_KINDS:
            raise ValueError(f"a spec kind named {name!r} is already registered")
        _SPEC_KINDS[name] = SpecKind(
            name=name, fn=fn, order=order, table=table,
            doc=(fn.__doc__ or "").strip().splitlines()[0] if fn.__doc__ else "")
        return fn
    return deco


def spec_kinds() -> list[SpecKind]:
    """Every registered kind, in the order their rows are reported."""
    return sorted(_SPEC_KINDS.values(), key=lambda k: (k.order, k.name))


def spec_kind_names() -> tuple[str, ...]:
    """Every registered kind's name, in the order they registered in: the order a message lists them."""
    return tuple(_SPEC_KINDS)


# ─── Finding the modules ─────────────────────────────────────────────────────

def autoload(package: str, first: tuple = ()) -> list[str]:
    """Import every module of a package, so that what each registers is registered.

    The modules named in `first` come first, in that order, and then the rest by name. A module
    whose name starts with an underscore is a helper and is left alone. Returns the names, in the
    order imported. An import that fails raises: a rule or a spec kind that cannot load is a bug to
    see, and a gate that quietly lost one is worse than a crash.
    """
    import importlib
    import pkgutil
    pkg = importlib.import_module(package)
    names = list(first)
    names += sorted(m.name for m in pkgutil.iter_modules(pkg.__path__)
                    if not m.name.startswith("_") and m.name not in names)
    for name in names:
        importlib.import_module(f"{package}.{name}")
    return names

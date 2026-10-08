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
    artifacts: list = field(default_factory=list)   # paths a reader can open

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

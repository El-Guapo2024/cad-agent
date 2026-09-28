"""Search over a part's parameters, driven by what the gates actually said.

A gate answers pass or fail, which is what you want before cutting metal and
almost useless for steering. But nearly every row carries two numbers — what
was measured and the limit it was measured against — and the gap between them
is a **margin**. Margins turn a wall of verdicts into something a search can
climb.

Two things fall out of that, and the second is the reason this module exists.

**A failing run says which way you went wrong.** Sweeping one bolt row down a
plate, the part fails below by colliding with its neighbour (`web`, between two
cutouts) and fails above by escaping through the rim (`feature count` drops as
a hole breaks out). Those are opposite directions wearing different rule names.
Reading the *kind* of failure is a gradient you get for free.

**Passing is not one thing.** A design that clears every limit by a hair and
one that clears them comfortably both report PASS, and they are not equally
good: the first is a design where a tolerance stack eats the margin and the
part comes back wrong. So the objective here is not "does it pass" but **how
much room the tightest rule has left** — maximise the worst margin, and
robustness falls out instead of being hoped for.

Margins are compared **relative to their own limit**, because the rules speak
different units. 0.5 mm of wall and 0.5% of pixel drift are not comparable
quantities, and averaging them would be arithmetic on nonsense.

What this deliberately does not do: replace the gate. `solve` reports the best
parameter it found and the margins it found there. Committing that value is
still an edit to the part file, and `check_all` still has the last word —
because a part-scope search cannot see fit, sweep or reach.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .registry import FAILING
from .runner import part_check

# Which way a rule wants to go. +1: measured should exceed the limit.
# -1: measured should stay under it. Rules absent from this table are still
# honoured as pass/fail; they simply contribute no gradient, which is the
# honest treatment of a count or a multi-axis envelope.
SENSE = {
    "min wall": +1,
    "web": +1,
    "silhouette": +1,
    "drift": -1,
    "extent": -1,
}

# Drift from the approved render is excluded from search by default, because
# drifting from the approved design is the definition of exploring. Leaving it
# in fails every candidate except the one already approved, which would make
# the search agree with wherever it started.
# The whole visual family is excluded, not just drift. Every one of these
# compares the candidate against the *approved* render, which is a picture of
# a different design the moment a parameter moves. `extent` is the trap: it
# reports 0 px of movement against a 1 px limit, which reduces to a fat
# relative margin and then wins "tightest rule" over the geometry that
# actually constrains the part.
IGNORE_BY_DEFAULT = ("drift", "extent", "silhouette")

_NUM = re.compile(r"-?\d+(?:\.\d+)?")


def _sense_for(rule: str) -> int | None:
    for key, s in SENSE.items():
        if rule == key or rule.startswith(key + "/"):
            return s
    return None


def _first_number(text: str) -> float | None:
    m = _NUM.search(text or "")
    return float(m.group()) if m else None


def _ignored(rule: str, ignore) -> bool:
    return any(rule == k or rule.startswith(k + "/") for k in ignore)


@dataclass
class Margin:
    rule: str
    state: str
    measured: float
    limit: float
    slack: float          # in the rule's own units; negative means failing
    relative: float       # slack / limit, so rules in different units compare


@dataclass
class Eval:
    """One candidate: what the gates said, reduced to something comparable."""
    overrides: dict
    ok: bool
    margins: list = field(default_factory=list)
    hard_fails: list = field(default_factory=list)   # failures with no gradient
    worst: float = float("-inf")
    worst_rule: str = ""
    build_s: float = 0.0

    @property
    def feasible(self) -> bool:
        return self.ok and not self.hard_fails


# Checks whose every row is ignored during search. Running them costs about
# half of each candidate and produces nothing the objective can read.
SEARCH_CHECKS = {"geometry"}


def evaluate(slug: str, part: str, overrides: dict,
             ignore=IGNORE_BY_DEFAULT, only=None, opts=None) -> Eval:
    """Run the part rules and reduce them to margins.

    `only` and `opts` exist to make a search affordable, not to weaken a gate:
    see `solve`, which spends a full-fidelity pass learning what it is allowed
    to skip and a second one confirming the winner.
    """
    r = part_check(slug, part, overrides, render=False, only=only, opts=opts)
    ev = Eval(overrides=dict(overrides), ok=True, build_s=r["build_s"])

    for row in r["rows"]:
        rule, state = row["rule"], row["state"]
        if _ignored(rule, ignore):
            continue
        failing = state in FAILING
        sense = _sense_for(rule)
        lim = _first_number(row["limit"]) if row["limit"] != "n/a" else None
        meas = _first_number(row["measured"])

        if sense is None or lim is None or meas is None or lim == 0:
            # No usable gradient. It still counts, it just cannot steer.
            if failing:
                ev.hard_fails.append(
                    {"rule": rule, "state": state, "measured": row["measured"],
                     "limit": row["limit"]})
                ev.ok = False
            continue

        slack = (meas - lim) if sense > 0 else (lim - meas)
        ev.margins.append(Margin(rule=rule, state=state, measured=meas,
                                 limit=lim, slack=round(slack, 4),
                                 relative=round(slack / abs(lim), 4)))
        if failing:
            ev.ok = False

    if ev.margins:
        tight = min(ev.margins, key=lambda m: m.relative)
        ev.worst, ev.worst_rule = tight.relative, tight.rule
    return ev


def sweep(slug: str, part: str, param: str, values, ignore=IGNORE_BY_DEFAULT,
          base: dict | None = None, only=None, opts=None) -> list:
    """Evaluate one parameter across a list of values."""
    out = []
    for v in values:
        o = dict(base or {})
        o[param] = v
        out.append(evaluate(slug, part, o, ignore, only=only, opts=opts))
    return out


def feasible_span(results: list, param: str):
    """The contiguous run of feasible values, and what bounds it on each side.

    The bounding failures are the useful part. They name *why* the design
    cannot go further in each direction, which is the thing a person actually
    wants to know before choosing a value inside the span.
    """
    vals = [(r.overrides[param], r) for r in results]
    vals.sort(key=lambda t: t[0])
    ok = [(v, r) for v, r in vals if r.feasible]
    if not ok:
        return None
    lo, hi = ok[0][0], ok[-1][0]

    def bound(side):
        cand = [(v, r) for v, r in vals
                if (v < lo if side == "below" else v > hi) and not r.feasible]
        if not cand:
            return None
        v, r = (max(cand, key=lambda t: t[0]) if side == "below"
                else min(cand, key=lambda t: t[0]))
        why = (r.hard_fails[0]["rule"] if r.hard_fails
               else (r.worst_rule or "unknown"))
        return {"at": v, "rule": why}

    return {"param": param, "low": lo, "high": hi,
            "bounded_below_by": bound("below"),
            "bounded_above_by": bound("above"),
            "count": len(ok)}


# A rule whose measured value moves by less than this across a whole sweep is
# treated as constant for that search.
RESPONSE_EPS = 1e-6


def responsive_rules(results: list) -> set:
    """Rules whose measurement actually moves when the parameter does.

    Without this the objective is wrong in a way that looks fine. On a 6 mm
    plate `min wall` reads 5.9998 for every value of every parameter that
    moves a hole, because the thinnest wall *is* the plate. Its relative
    margin sits at 3.0 and becomes the worst margin for every candidate that
    clears it, so "maximise the worst margin" saturates: the real constraint
    stops being compared, every feasible candidate ties, and whichever grid
    point `max` reaches first wins. That is a coin toss reported as an
    optimum.

    A rule that cannot respond to the parameter carries no information about
    it. It is still honoured as pass/fail — a constant that fails, fails —
    but it is kept out of the objective.
    """
    seen: dict = {}
    for r in results:
        for m in r.margins:
            seen.setdefault(m.rule, []).append(m.measured)
    return {rule for rule, vals in seen.items()
            if len(vals) > 1 and (max(vals) - min(vals)) > RESPONSE_EPS}


def _objective(ev, responsive: set):
    """Worst relative margin among rules that respond. None when none do."""
    live = [m for m in ev.margins if m.rule in responsive]
    if not live:
        return None, ""
    tight = min(live, key=lambda m: m.relative)
    return tight.relative, tight.rule


def solve(slug: str, part: str, param: str, lo: float, hi: float,
          steps: int = 9, refine: int = 2, ignore=IGNORE_BY_DEFAULT,
          base: dict | None = None) -> dict:
    """Find the value of one parameter with the most room to spare.

    A coarse pass, then `refine` rounds narrowing around the best point. This
    is a grid, not an optimiser, and deliberately so: the objective is not
    smooth — it steps whenever a hole breaks out or two cutouts merge — so
    gradient methods will happily walk off a cliff and report the far side.
    A grid at least sees the cliff.
    """
    if hi <= lo:
        raise ValueError(f"hi must exceed lo, got {lo}..{hi}")
    history, best, span = [], None, None
    best_live: set = set()
    best_why = ""
    a, b = float(lo), float(hi)

    # Fidelity is earned, not assumed. Round 0 runs every part rule at full
    # cost; what it learns there decides what later rounds may skip, and the
    # winner is re-checked at full fidelity before being returned. Skipping
    # work the first pass proved inert is an optimisation; skipping work you
    # merely hope is inert is how a search talks itself into a bad part.
    # Visual needs no probe round: every search ignores all of its rows by
    # construction, so it is dropped from the first pass. The ray cast is
    # different — whether it can move is a fact about this part that round 0
    # has to establish.
    only, opts = set(SEARCH_CHECKS), None
    savings = {"visual_skipped": True, "raycast_skipped": False}

    for rnd in range(refine + 1):
        vals = [a + (b - a) * i / (steps - 1) for i in range(steps)]
        results = sweep(slug, part, param, vals, ignore, base,
                        only=only, opts=opts)
        history.append({"round": rnd, "low": round(a, 4), "high": round(b, 4),
                        "tried": [round(v, 4) for v in vals],
                        "feasible": [round(r.overrides[param], 4)
                                     for r in results if r.feasible]})
        # The span is taken from the first, widest pass only. Later rounds
        # search a narrowed window where everything is feasible by
        # construction, so reporting their span would claim the part is
        # bounded at the edges of the zoom rather than at its real limits.
        if rnd == 0:
            span = feasible_span(results, param)
        good = [r for r in results if r.feasible]
        if not good:
            break

        live = responsive_rules(results)
        if rnd == 0:
            # Visual rules are ignored by every search, so running them is
            # pure cost. The ray-cast wall measurement is dropped only when
            # the first pass showed it cannot move — on a flat plate the
            # thinnest wall is the stock and no hole position changes it.
            if "min wall" not in live:
                opts = {"measure": False}
                savings["raycast_skipped"] = True
        scored = [(r, _objective(r, live)[0]) for r in good]
        if any(v is not None for _, v in scored):
            top = max((r for r, v in scored if v is not None),
                      key=lambda r: _objective(r, live)[0])
            tie_break = "worst responsive margin"
        else:
            # No rule discriminates. The defensible pick is then the middle of
            # the feasible run: furthest from whatever bounds it on each side.
            mid = (good[0].overrides[param] + good[-1].overrides[param]) / 2.0
            top = min(good, key=lambda r: abs(r.overrides[param] - mid))
            tie_break = ("centre of the feasible span; no responsive rule "
                         "discriminated between these candidates")
        best_v = _objective(best, live)[0] if best else None
        top_v = _objective(top, live)[0]
        if best is None or (top_v is not None and best_v is not None
                            and top_v > best_v) or best_v is None:
            best, best_live, best_why = top, live, tie_break
        # Narrow to one grid step either side of the winner.
        step = (b - a) / (steps - 1)
        centre = top.overrides[param]
        a, b = centre - step, centre + step

    if best is None:
        return {"param": param, "found": False, "history": history,
                "note": f"no feasible value of {param} in {lo}..{hi}; widen the "
                        "range, or the constraint is elsewhere in the part"}
    # Confirm the winner with everything switched back on. A disagreement here
    # means the cheap pass was not a faithful stand-in, which is a fact about
    # the harness and must be reported, never quietly resolved in its favour.
    confirm = evaluate(slug, part, best.overrides, ignore)
    if not confirm.feasible:
        return {
            "param": param, "found": False, "history": history,
            "value_rejected_on_recheck": round(best.overrides[param], 4),
            "recheck_failures": confirm.hard_fails
                                or [{"rule": m.rule, "measured": m.measured,
                                     "limit": m.limit} for m in confirm.margins
                                    if m.relative < 0],
            "note": "the fast pass proposed a value that fails a full-fidelity "
                    "check. Do not use it. The skipped rules were not inert "
                    "after all, which is a harness bug worth chasing.",
        }

    obj, obj_rule = _objective(best, best_live)
    return {
        "param": param,
        "found": True,
        "value": round(best.overrides[param], 4),
        "chosen_by": best_why,
        "worst_margin_relative": obj,
        "tightest_rule": obj_rule,
        "responsive_rules": sorted(best_live),
        "inert_rules": sorted({m.rule for m in best.margins} - best_live),
        "margins": [{"rule": m.rule, "measured": m.measured, "limit": m.limit,
                     "slack": m.slack, "relative": m.relative,
                     "responds": m.rule in best_live}
                    for m in sorted(best.margins, key=lambda m: m.relative)],
        "feasible_span": span,
        "confirmed_at_full_fidelity": True,
        "savings": savings,
        "history": history,
        "note": "part rules only. Fit, sweep and reach are assembly facts; "
                "run check_all before committing this value.",
    }


def design_loop(slug: str, part: str, plan: list, ignore=IGNORE_BY_DEFAULT,
                rounds: int = 2) -> dict:
    """Tune several parameters against the gates, one at a time, repeatedly.

    `plan` is a list of (param, lo, hi). Each parameter is solved with the
    others held at their current best, then the whole list is walked again —
    coordinate descent, because the parameters interact: widening a plate
    moves where a bolt row can sit, and a value chosen before that widening
    was chosen under a constraint that no longer applies.

    A second pass is usually enough. If round two moves nothing, the
    parameters were independent and one pass would have done; if it moves a
    lot, they are coupled and that coupling is worth knowing about — it is
    reported rather than silently iterated away.

    The loop reports. It does not edit the part file, and it cannot see the
    assembly. Committing a value is a deliberate edit, and `check_all` still
    decides, because fit, sweep and reach are facts about a machine and this
    only ever looked at one part.
    """
    current: dict = {}
    steps: list = []
    for rnd in range(rounds):
        moved = 0.0
        for param, lo, hi in plan:
            base = {k: v for k, v in current.items() if k != param}
            r = solve(slug, part, param, lo, hi, ignore=ignore, base=base)
            if not r["found"]:
                steps.append({"round": rnd, "param": param, "found": False,
                              "note": r["note"]})
                continue
            was = current.get(param)
            current[param] = r["value"]
            if was is not None:
                moved += abs(r["value"] - was)
            steps.append({
                "round": rnd, "param": param, "found": True,
                "from": was, "to": r["value"],
                "worst_margin_relative": r["worst_margin_relative"],
                "tightest_rule": r["tightest_rule"],
                "feasible_span": r["feasible_span"],
            })
        if rnd > 0 and moved == 0.0:
            break

    final = evaluate(slug, part, current, ignore)
    later = [s for s in steps if s.get("round", 0) > 0 and s.get("found")]
    coupled = [s["param"] for s in later
               if s.get("from") is not None and s["from"] != s["to"]]
    return {
        "part": part,
        "params": current,
        "feasible": final.feasible,
        "worst_margin_relative": final.worst,
        "tightest_rule": final.worst_rule,
        "hard_fails": final.hard_fails,
        "steps": steps,
        "coupled": coupled,
        "coupling_note": (
            f"{', '.join(coupled)} moved on a later pass, so these parameters "
            "constrain each other and the order they were tuned in mattered"
            if coupled else
            "nothing moved after the first pass, so these parameters are "
            "independent of one another"),
        "note": "part rules only; run check_all before committing these values.",
    }

"""mechanism: whether the machine's moving parts are held, driven and tensioned, not only clear of each other.

The fit, sweep and clearance rules say nothing overlaps and nothing crashes. A design can pass all of them with a
lead screw floating in mid-air, a shaft through a clearance hole with no bearing, a belt with no way to tension it
and an axis with guides but nothing to push it. pcb_conveyor's first draft did exactly that and passed. This rule
asks the questions an engineer asks first, from what assembly.py declares, and measures what it can:

  rotating   every body that turns names what holds it (bearings, bushes, the shaft it rides on). Each support
             must be within FIT_MM of the body, and the supports' contact spots must be spread along the turning
             axis by at least the body's diameter (one support, or two at one spot, lets it wobble), unless the
             entry says `cantilever: True`: then its supports must hold it over the lesser of its own length and
             its diameter (a thin pulley on an axle passes; a long shaft held at one end does not).
  belts      every belt names its pulleys and what tensions it. Each pulley must be within FIT_MM of the belt and
             be a declared rotating body; the tensioner must be a body in the assembly.
  axes       every axis in AXES names its guides (pairs of a moving and a fixed body, within FIT_MM) and its drive
             (a body within FIT_MM of something the axis moves), and the actuator that turns the drive.

And it looks for what was not declared: a body whose name says it turns or loops (shaft, screw, pulley, idler,
roller, gear, wheel, sprocket, belt, chain), and not like what holds one (block, bracket, mount, support,
bearing...), and that MECHANISM does not mention is a FAIL, because an undeclared
rotating part is exactly how the floating screw got through. A body that only looks like one is listed in
MECHANISM["static"] with a reason.

The declaration, in assembly.py:

    MECHANISM = {
        "rotating": {"lead_screw_1": {"axis": (0, 1, 0), "supports": ["screw_bearing_1a", "screw_bearing_1b"]}},
        "belts": {"front_belt": {"pulleys": ["front_idler_in", ...], "tension": "front_idler_in"}},
        "axes": {"width": {"guides": [["guide_block_1", "guide_rail_1"]], "drive": "lead_screw_1",
                           "actuator": "width_motor"}},
        "static": {"hex_bar_stock": "a spacer, it does not turn"},
    }

When it applies: once assembly.py declares MECHANISM (until then N/A, as `com` does with masses).

What it does not judge: loads, bearing ratings, belt tension values, whether a fit is a press or a slide, or
anything dynamic. Those are FEM's and the physics sim's. It judges that the parts that must exist do, and are where
they must be.
"""
from __future__ import annotations

import re

from ..registry import Row, register

FIT_MM = 0.5                 # a support, guide or pulley this close counts as touching (a slide fit's gap is less)
SOURCE = (f"assembly.py MECHANISM; distances by BRep (within {FIT_MM} mm counts as held); supports spread along the "
          "axis by at least the body's diameter (rule of thumb: one bearing spot lets a shaft wobble)")
TURNS = re.compile(r"(shaft|screw|pulley|idler|roller|gear|wheel|sprocket|belt|chain|spindle|axle)", re.I)
HOLDS = re.compile(r"(block|bracket|mount|support|bearing|housing|cover|guard|clamp|plate)", re.I)  # holds one
RULE = "mechanism"


@register(scope="assembly", name="mechanism", order=40)
def mechanism(ctx):
    """Whether every turning part is supported, every belt is on its pulleys and tensioned, every axis guided and
    driven, as assembly.py's MECHANISM declares and the geometry shows."""
    if not ctx.parts:
        yield Row(subject="assembly", rule=RULE, state="N/A", measured="no assembly", limit="n/a",
                  source="nothing positioned")
        return
    mech = _declared(ctx.slug)
    if mech is None:
        # Like `com`: judged once a design declares it, so the designs made before this rule are not all put on
        # hold for a claim they never made. Declaring MECHANISM is how a design starts to claim it works.
        looks = sorted(n for n in ctx.parts if TURNS.search(n) and not HOLDS.search(n))
        yield Row(subject="assembly", rule=RULE, state="N/A",
                  measured=(f"no MECHANISM declared ({len(ctx.axes)} axes, {len(looks)} bodies named like turning "
                            "parts); declare one to have them judged"), limit="n/a", source=SOURCE)
        return

    rotating = dict(mech.get("rotating", {}))
    belts = dict(mech.get("belts", {}))
    axes = dict(mech.get("axes", {}))
    static = dict(mech.get("static", {}))

    # what was not declared
    known = set(rotating) | set(belts) | set(static)
    for n in sorted(ctx.parts):
        if TURNS.search(n) and not HOLDS.search(n) and n not in known:
            yield Row(subject=n, rule=f"{RULE}/declared", state="FAIL",
                      measured=f"{n} is named like a part that turns or loops, and MECHANISM does not say what holds "
                               "it (rotating), what it runs on (belts), or that it does not move (static)",
                      limit="declared", source=SOURCE)
    for n in sorted(set(rotating) | set(belts) | set(static)):
        if n not in ctx.parts:
            yield Row(subject=n, rule=f"{RULE}/declared", state="FAIL",
                      measured=f"MECHANISM names {n}, which the assembly does not return", limit="a body",
                      source=SOURCE)

    for n, d in sorted(rotating.items()):
        if n in ctx.parts:
            yield _rotating(n, d, ctx.parts)
    for n, d in sorted(belts.items()):
        if n in ctx.parts:
            yield from _belt(n, d, ctx.parts, rotating)
    for name in sorted(ctx.axes):
        yield from _axis(name, axes.get(name), ctx.parts, set(ctx.axes[name].moves))
    for name in sorted(set(axes) - set(ctx.axes)):
        yield Row(subject=f"axis {name}", rule=f"{RULE}/axis", state="FAIL",
                  measured=f"MECHANISM describes axis {name}, which AXES does not declare", limit="an axis",
                  source=SOURCE)


def _declared(slug):
    from ..state import _load_module, project_dir
    path = project_dir(slug) / "assembly.py"
    if not path.exists():
        return None
    m = getattr(_load_module(path), "MECHANISM", None)
    return m if isinstance(m, dict) else None


def _dist(a, b) -> float:
    from ..geom import min_distance
    return float(min_distance(a, b))


def _bb(s):
    from ..geom import bbox
    return bbox(s)


def _rotating(n, d, parts) -> Row:
    rule = f"{RULE}/supported"
    axis = tuple(float(v) for v in d.get("axis", ()))
    sup = list(d.get("supports", ()))
    if len(axis) != 3 or not any(axis):
        return Row(subject=n, rule=rule, state="FAIL", measured=f"{n} declares no turning axis",
                   limit="an axis (x, y, z)", source=SOURCE)
    if not sup:
        return Row(subject=n, rule=rule, state="FAIL", measured=f"{n} turns, and nothing is named as holding it",
                   limit="supports named", source=SOURCE)
    missing = [s for s in sup if s not in parts]
    if missing:
        return Row(subject=n, rule=rule, state="FAIL",
                   measured=f"{n}'s supports {', '.join(missing)} are not in the assembly", limit="each support a body",
                   source=SOURCE)
    far = [(s, _dist(parts[n], parts[s])) for s in sup]
    loose = [f"{s} ({g:.2f} mm away)" for s, g in far if g > FIT_MM]
    if loose:
        return Row(subject=n, rule=rule, state="FAIL",
                   measured=f"{n} is not held by {', '.join(loose)}", limit=f"each support within {FIT_MM} mm",
                   source=SOURCE)
    k = max(range(3), key=lambda i: abs(axis[i]))          # the axis, as the nearest coordinate direction
    lo, hi = _bb(parts[n])
    dia = max(hi[i] - lo[i] for i in range(3) if i != k)
    own = hi[k] - lo[k]                                     # its length along the axis
    spots = []
    for s in sup:
        slo, shi = _bb(parts[s])
        a, b = max(lo[k] - FIT_MM, slo[k]), min(hi[k] + FIT_MM, shi[k])
        spots.append((a, b))
    span = max(b for _, b in spots) - min(a for a, _ in spots)
    if d.get("cantilever"):
        need = min(dia, own)                                # a thin pulley on an axle is held over its width
        state = "PASS" if span >= need - 1e-6 else "FAIL"
        return Row(subject=n, rule=rule, state=state,
                   measured=f"cantilevered on {', '.join(sup)}, held over {span:.1f} mm (its length {own:.1f}, "
                            f"diameter {dia:.1f})", limit="held over the lesser of its length and diameter",
                   source=SOURCE)
    if len(sup) < 2:
        return Row(subject=n, rule=rule, state="FAIL",
                   measured=f"{n} is held by {sup[0]} alone, so it can wobble about that spot",
                   limit="two supports, or cantilever declared", source=SOURCE)
    centres = sorted((a + b) / 2.0 for a, b in spots)
    spread = centres[-1] - centres[0]
    return Row(subject=n, rule=rule, state="PASS" if spread >= dia else "FAIL",
               measured=f"held by {', '.join(sup)}, their spots {spread:.1f} mm apart along the axis (diameter "
                        f"{dia:.1f})", limit="spots apart by at least the diameter", source=SOURCE)


def _belt(n, d, parts, rotating):
    rule = f"{RULE}/belt"
    pulleys = list(d.get("pulleys", ()))
    if len(pulleys) < 2:
        yield Row(subject=n, rule=rule, state="FAIL", measured=f"{n} names {len(pulleys)} pulleys",
                  limit="at least two", source=SOURCE)
        return
    bad = []
    for p in pulleys:
        if p not in parts:
            bad.append(f"{p} (not in the assembly)")
        elif p not in rotating:
            bad.append(f"{p} (not declared as turning, so nothing says what holds it)")
        else:
            g = _dist(parts[n], parts[p])
            if g > FIT_MM:
                bad.append(f"{p} ({g:.2f} mm off the belt)")
    yield Row(subject=n, rule=rule, state="FAIL" if bad else "PASS",
              measured=("runs on " + ", ".join(pulleys)) if not bad else "; ".join(bad),
              limit=f"each pulley declared turning and within {FIT_MM} mm", source=SOURCE)
    t = d.get("tension")
    yield Row(subject=n, rule=f"{RULE}/tension", state="PASS" if t and t in parts else "FAIL",
              measured=(f"tensioned by {t}" if t and t in parts else
                        f"tensioner {t} is not in the assembly" if t else f"nothing tensions {n}"),
              limit="a tensioner (an adjustable pulley or idler) named", source=SOURCE)


def _axis(name, d, parts, moves):
    subj = f"axis {name}"
    if not d:
        yield Row(subject=subj, rule=f"{RULE}/axis", state="FAIL",
                  measured=f"axis {name} moves {len(moves)} bodies, and MECHANISM does not say what guides or "
                           "drives it", limit="guides, drive and actuator declared", source=SOURCE)
        return
    guides = [tuple(g) for g in d.get("guides", ())]
    bad = []
    for g in guides:
        if len(g) != 2 or any(x not in parts for x in g):
            bad.append(f"{g} (not two bodies of the assembly)")
            continue
        a, b = g
        if (a in moves) == (b in moves):
            bad.append(f"{a}/{b} (a guide pairs a body the axis moves with one it does not)")
            continue
        gap = _dist(parts[a], parts[b])
        if gap > FIT_MM:
            bad.append(f"{a}/{b} ({gap:.2f} mm apart)")
    yield Row(subject=subj, rule=f"{RULE}/guided",
              state="FAIL" if bad or not guides else "PASS",
              measured=("; ".join(bad) if bad else f"guided by {len(guides)} pairs" if guides else "no guides named"),
              limit=f"guide pairs within {FIT_MM} mm", source=SOURCE)
    drive, act = d.get("drive"), d.get("actuator")
    if not drive or drive not in parts:
        yield Row(subject=subj, rule=f"{RULE}/driven", state="FAIL",
                  measured=f"drive {drive} is not in the assembly" if drive else "nothing drives it",
                  limit="a drive body", source=SOURCE)
    else:
        gap = min(_dist(parts[drive], parts[m]) for m in moves if m in parts)
        yield Row(subject=subj, rule=f"{RULE}/driven", state="PASS" if gap <= FIT_MM else "FAIL",
                  measured=(f"{drive} reaches what the axis moves" if gap <= FIT_MM else
                            f"{drive} is {gap:.2f} mm from everything the axis moves, so it pushes nothing"),
                  limit=f"within {FIT_MM} mm of a moved body", source=SOURCE)
    yield Row(subject=subj, rule=f"{RULE}/actuated", state="PASS" if act and act in parts else "FAIL",
              measured=f"actuated by {act}" if act and act in parts else (
                  f"actuator {act} is not in the assembly" if act else "no actuator named"),
              limit="an actuator body (motor, crank, cylinder)", source=SOURCE)

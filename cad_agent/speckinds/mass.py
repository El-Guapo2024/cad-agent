"""[[mass]]: a weight budget, over part modules, placed bodies, or everything one axis moves.

The `parts` form is in cad_agent/spec.py and is unchanged. Two forms came with step 6 (an entry takes
exactly one of the three):

    [[mass]]                     # part modules, by count: volume x density of the part as it builds
    parts = { x_carriage = 1, syringe_clamp = 2 }
    max_g = 400

    [[mass]]                     # the bodies assembly.py places, each once
    bodies = ["x_carriage", "motor_x", "rail_x"]
    max_g = 900

    [[mass]]                     # every body AXES["x"]["moves"] lists: what the motor has to throw
    moving = "x"
    max_g = 800

`parts` counts a part module as built, which is blind to anything assembly.py does to it and to what it
did not build itself. `bodies` and `moving` weigh the solids the assembly really holds, so a part cut
in assembly.py weighs what is left, and a bought body weighs what its sidecar declares.

What a body weighs is its BodyInfo.mass_g (bodies.py): a made body, volume x density of its MATERIAL;
a bought body, the `mass_g` it declares together with a `mass_source` (bought.py has the contract: a
mass with no source is not used); a stock body, nothing. The same rule as every rule of step 6: a mass
nobody states is unknown, never a default. An entry with a body of unknown mass is UNCHECKED, and the
row names each such body and why. One exception, because it is a proof and not a guess: if the bodies
whose mass is known already weigh more than `max_g`, the budget is blown whatever the rest weigh, so
that row is FAIL.
"""
from __future__ import annotations

from ..registry import TOL_MM, spec_kind
from .kit import (Unusable as _Unusable, get_body as _body, require as _need, row as _row)

FORMS = ("parts", "bodies", "moving")


@spec_kind("mass", order=70)
def mass(entry: dict, ctx):
    """A weight budget: part modules by count, placed bodies, or everything one axis moves."""
    forms = [k for k in FORMS if k in entry]
    if len(forms) > 1:
        raise _Unusable("[[mass]] takes one of `parts`, `bodies` or `moving`, "
                        f"and this one has {' and '.join(forms)}")
    if "bodies" in entry:
        yield from _bodies(entry, ctx)
    elif "moving" in entry:
        yield from _moving(entry, ctx)
    else:
        yield from _parts(entry, ctx)


def _parts(entry: dict, ctx):
    """The mass of counted part modules against max_g."""
    from .. import state as st
    slug = ctx.slug
    from ..geom import mass_g
    if "parts" not in entry:
        raise _Unusable("[[mass]] is missing `parts`, `bodies` or `moving`")
    counts = _need(entry, "parts", "[[mass]]")
    limit = float(_need(entry, "max_g", "[[mass]]"))
    if not isinstance(counts, dict) or not counts:
        raise _Unusable("`parts` must map part names to counts, e.g. { x_carriage = 1 }")
    total, lines = 0.0, []
    for name, n in counts.items():
        if name not in st.part_names(slug):
            raise _Unusable(f"no part module {name!r} (parts: {', '.join(st.part_names(slug))})")
        solid, meta = st.build_part(slug, name)
        if not meta["material"]:
            raise _Unusable(f"{name} declares no MATERIAL, so its mass is unknown")
        g = mass_g(solid, meta["material"]) * float(n)
        total += g
        lines.append(f"{name} x{n} {g:.1f} g")
    yield _row(", ".join(counts), "mass", "PASS" if total <= limit + TOL_MM else "FAIL",
               f"{total:.1f} g ({'; '.join(lines)})", f"<= {limit:g} g")


def _bodies(entry: dict, ctx):
    """The placed bodies named in `bodies`, weighed as assembly.py holds them."""
    names = entry["bodies"]
    if not (isinstance(names, list) and names and all(isinstance(n, str) for n in names)):
        raise _Unusable('`bodies` must list body names, e.g. ["x_carriage", "motor_x"]')
    twice = sorted({n for n in names if names.count(n) > 1})
    if twice:
        raise _Unusable(f"`bodies` lists {', '.join(twice)} more than once, which would weigh it twice")
    limit = _limit(entry)
    for name in names:
        _body(ctx.parts, name)
    yield _budget(", ".join(names), names, limit, ctx)


def _moving(entry: dict, ctx):
    """Every body the named axis moves, weighed as assembly.py holds them."""
    axis = entry["moving"]
    if not (isinstance(axis, str) and axis):
        raise _Unusable('`moving` must name one axis, e.g. moving = "x"')
    limit = _limit(entry)
    if ctx.machine is None:
        raise _Unusable("`moving` reads AXES from assembly.py, and no assembly was loaded")
    axes = ctx.machine.axes
    if not axes:
        raise _Unusable(f"assembly.py declares no AXES, so there is no axis {axis!r} to move anything")
    if axis not in axes:
        raise _Unusable(f"no axis {axis!r} in AXES (axes: {', '.join(sorted(axes))})")
    names = list(dict.fromkeys(axes[axis].moves))
    if not names:
        raise _Unusable(f"axis {axis!r} moves no body")
    missing = [n for n in names if n not in ctx.parts]
    if missing:
        raise _Unusable(f"axis {axis!r} moves {', '.join(missing)}, which the assembly does not return "
                        f"(bodies: {', '.join(sorted(ctx.parts))})")
    yield _budget(f"axis {axis}", names, limit, ctx)


def _limit(entry: dict) -> float:
    return float(_need(entry, "max_g", "[[mass]]"))


def _budget(subject: str, names: list, limit: float, ctx):
    """One row: what the bodies weigh against max_g, or why that cannot be said."""
    infos = ctx.bodies
    known, lines, unknown = 0.0, [], []
    for name in names:
        info = infos.get(name)
        if info is None or info.mass_g is None:
            unknown.append(f"{name} ({_why_unknown(info)})")
            continue
        known += info.mass_g
        lines.append(f"{name} {info.mass_g:.1f} g" + ("" if info.kind == "made" else f" ({info.mass_source})"))
    limit_text = f"<= {limit:g} g"
    if not unknown:
        return _row(subject, "mass", "PASS" if known <= limit + TOL_MM else "FAIL",
                    f"{known:.1f} g ({'; '.join(lines)})", limit_text)
    gone = f"no mass for {'; '.join(unknown)}"
    if known > limit + TOL_MM:
        return _row(subject, "mass", "FAIL",
                    f"{known:.1f} g already, before the bodies of unknown mass ({'; '.join(lines)}); {gone}",
                    limit_text)
    return _row(subject, "mass", "UNCHECKED",
                f"{gone}; the others weigh {known:.1f} g ({'; '.join(lines) or 'none'})", limit_text)


def _why_unknown(info) -> str:
    """Why a body has no mass, in the words BodyInfo.notes already has, else by what kind of body it is."""
    if info is not None and info.notes:
        return "; ".join(info.notes)
    if info is not None and info.kind == "bought":
        return f"bought part {info.part!r} declares no mass_g with a mass_source"
    return ("assembly.py builds it itself, so it has no material or declared mass; make it a part module with a "
            "MATERIAL, or a bought part with mass_g and mass_source")

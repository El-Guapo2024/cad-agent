"""What a spec kind needs to write itself: the row it returns, the entry it cannot use, the lookups.

A kind is a function `fn(entry, ctx)` that yields rows, registered with `@spec_kind` (registry.py).
These are the pieces every kind shares, so that a new one is its measurement and nothing else:

    from ..registry import spec_kind
    from .kit import Unusable, get_body, require, row, vec3

    @spec_kind("heat", order=80)
    def heat(entry, ctx):
        \"\"\"One line saying what it judges (cad rules prints it).\"\"\"
        at = vec3(require(entry, "at", "[[heat]]"), "at")
        body = get_body(ctx.parts, entry["body"])
        yield row(entry["body"], "heat", "PASS", "...", "...")

An entry that names something missing or lacks a field raises Unusable, and check_spec turns it into
one UNCHECKED row naming the entry (`[[heat]] #2`) and carrying the message, so a typo fails the gate
and hides no other result. Any other exception does the same with its type in front. A row says
where its limit came from; `source` defaults to the spec entry and check_spec fills in which one.
"""
from __future__ import annotations

from ..registry import TOL_MM, Row


class Unusable(Exception):
    """An entry that names something missing, or lacks a field."""


def row(subject, rule, state, measured, limit="n/a", source="spec.toml"):
    """One verdict of a spec entry; its rule is reported as `spec/<rule>`."""
    return Row(subject=subject, rule=f"spec/{rule}", state=state,
               measured=measured, limit=limit, source=source)


def require(entry: dict, key: str, where: str):
    """entry[key], or an Unusable entry that says which section lacks it."""
    if key not in entry:
        raise Unusable(f"{where} is missing `{key}`")
    return entry[key]


def get_body(parts: dict, name: str):
    """The positioned solid called `name`, or an Unusable entry listing the bodies there are."""
    if name not in parts:
        raise Unusable(f"no body {name!r} in the assembly (bodies: {', '.join(sorted(parts))})")
    return parts[name]


def vec3(value, what: str) -> list[float]:
    if not (isinstance(value, list) and len(value) == 3):
        raise Unusable(f"{what} must be [x, y, z]")
    return [float(v) for v in value]


def bounds(dims, top, low):
    """The state, the reason and the limit text for a box held to x, y, z bounds."""
    over = [a for a, d, m in zip("xyz", dims, top) if d > m + TOL_MM] if top else []
    under = [a for a, d, m in zip("xyz", dims, low) if d < m - TOL_MM] if low else []
    why = (f", too big in {''.join(over)}" if over else "") + \
          (f", too small in {''.join(under)}" if under else "")
    limit = ", ".join(f"{sign} {b[0]:g} x {b[1]:g} x {b[2]:g} mm"
                      for sign, b in (("<=", top), (">=", low)) if b)
    return ("FAIL" if over or under else "PASS"), why, limit

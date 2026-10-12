"""[bodies]: how many bodies assembly.py returns, and which.

"Exactly six bodies, called rail, block, ..." is in the brief of an eval task and nothing held a design to it, so
a design could carry a spare body, or leave out one that no other entry looks at:

    [bodies]
    count = 6                                           # exactly this many
    names = ["rail", "block", "stop_left", "stop_right", "tool", "carriage_plate"]     # exactly these

Either or both. A sub-assembly's bodies are counted by their full names (`gantry/x_carriage`), since that is what
the assembly holds. FAIL when the assembly has another number of bodies or other names, and the row says which
are missing and which are not asked for; PASS otherwise. UNCHECKED when the section cannot be read: a key it does
not have, a `count` that is not a whole number, `names` that is not a list of different names, a `count` that
disagrees with the number of `names`, or no assembly.py to count the bodies of.
"""
from __future__ import annotations

from ..registry import spec_kind
from .kit import Unusable as _Unusable, row as _row

KEYS = ("count", "names")


@spec_kind("bodies", order=86, table=True)
def bodies(entry: dict, ctx):
    """How many bodies the assembly has, and whether they are exactly the names asked for."""
    unknown = sorted(set(entry) - set(KEYS))
    if unknown:
        raise _Unusable(f"[bodies] does not take {', '.join(unknown)} (keys: {', '.join(KEYS)})")
    if not entry:
        raise _Unusable("[bodies] needs `count` and/or `names`")
    count = entry.get("count")
    if count is not None and (isinstance(count, bool) or not isinstance(count, int) or count < 0):
        raise _Unusable(f"[bodies] `count` must be a whole number of bodies, got {count!r}")
    names = entry.get("names")
    if names is not None:
        if not (isinstance(names, list) and all(isinstance(n, str) and n for n in names)):
            raise _Unusable("[bodies] `names` must be a list of body names")
        if len(set(names)) != len(names):
            twice = sorted({n for n in names if names.count(n) > 1})
            raise _Unusable(f"[bodies] `names` lists {', '.join(twice)} more than once")
        if count is not None and count != len(names):
            raise _Unusable(f"[bodies] `count` is {count} and `names` lists {len(names)}")
    if getattr(ctx, "machine", None) is None and not ctx.parts:
        raise _Unusable("no assembly.py, so there are no bodies to count")
    have = sorted(ctx.parts)
    asked = []
    if count is not None:
        asked.append(f"exactly {count} bodies")
    if names is not None:
        asked.append("exactly the bodies " + ", ".join(names))
    short = []
    if count is not None and len(have) != count:
        diff = len(have) - count
        short.append(f"{len(have)} bodies, {abs(diff)} {'more' if diff > 0 else 'fewer'} than {count}")
    if names is not None:
        missing = [n for n in names if n not in ctx.parts]
        extra = [n for n in have if n not in names]
        if missing:
            short.append(f"missing {', '.join(missing)}")
        if extra:
            short.append(f"not asked for: {', '.join(extra)}")
    shown = ", ".join(have[:8]) + (f" and {len(have) - 8} more" if len(have) > 8 else "")
    yield _row("assembly", "bodies", "FAIL" if short else "PASS",
               "; ".join(short) if short else f"{len(have)} bodies: {shown}", "; ".join(asked))

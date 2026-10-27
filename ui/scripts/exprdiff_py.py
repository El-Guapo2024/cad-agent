#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Differential test of the server's formula engine (cad_agent/fcexpr.py running src/expr.ts in V8) against the real FreeCAD's answers.

The same stored answers ui/scripts/exprdiff.py holds ui/src/expr.ts to (scripts/exprdiff/fc_answers.json.gz, some 75,000
expressions evaluated by FreeCAD 26.3 on an object with the properties of exprdiff-entry.ts), the same comparison
(exprdiff.differs and exprdiff.excused), here through the server's path: the bundle, the Python values and trees, no Node needed.

    PYTHONPATH=. python3 ui/scripts/exprdiff_py.py                  # every case; exit 1 if anything differs
    PYTHONPATH=. python3 ui/scripts/exprdiff_py.py --show 5 --kind value --category fn --limit 2000
    PYTHONPATH=. python3 ui/scripts/exprdiff_py.py --against-ts ours.json   # also compare with expr.ts's answers (a JSON list,
                                                                          # as scripts/exprdiff_ours.mjs writes them)
"""
import argparse
import importlib.util
import json
import math
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from cad_agent import fcexpr  # noqa: E402
from cad_agent.fcexpr import Env, ExprError, Other, Quantity, QuantityError, Vector  # noqa: E402


def load_exprdiff():
    spec = importlib.util.spec_from_file_location("exprdiff", HERE / "exprdiff.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["exprdiff"] = module
    spec.loader.exec_module(module)
    return module


L = (1, 0, 0, 0, 0, 0, 0, 0)
#: The owner's properties, as exprdiff-entry.ts has them.
PROPERTIES = {
    "pLen": Quantity(10.0, L), "pWid": Quantity(20.0, L), "pAng": Quantity(30.0, (0, 0, 0, 0, 0, 0, 0, 1)),
    "pMass": Quantity(2.0, (0, 1, 0, 0, 0, 0, 0, 0)), "pCnt": 3, "pRat": 0.5, "pStr": "abc", "pOn": True, "pLong": "abcdefghij",
    "pList": ["a", "b", "c", "d", "e", "f"],
}


def env():
    return Env(dict(PROPERTIES), owner="Obj", doc="T")


def enc(x):
    if math.isnan(x):
        return "nan"
    if math.isinf(x):
        return "inf" if x > 0 else "-inf"
    if x == 0 and math.copysign(1.0, x) < 0:
        return "-0.0"
    return x


def describe(r):
    """The answer in exprdiff's form (exprdiff-entry.ts's describe)."""
    t = type(r)
    if r is None:
        return {"t": "none"}
    if t is bool:
        return {"t": "bool", "v": r}
    if t is int:
        return {"t": "int", "v": fcexpr._int_text(r)}
    if t is float:
        return {"t": "float", "v": enc(r)}
    if t is complex:
        return {"t": "complex", "re": enc(r.real), "im": enc(r.imag)}
    if t is str:
        return {"t": "str", "v": r}
    if isinstance(r, Quantity):
        return {"t": "quantity", "v": enc(r.value), "dims": list(r.dims)}
    if t in (list, tuple):
        return {"t": t.__name__, "v": [describe(x) for x in r]}
    if isinstance(r, Other):
        return {"t": "other", "type": r.type, "str": r.str}
    if isinstance(r, Vector):
        return {"t": "vector", "v": [enc(x) for x in r.v]}
    return {"error": f"not a value: {r!r}", "etype": "Crash"}


def run(text, e=None):
    try:
        return describe(fcexpr.evaluate_value(text, e or env()))
    except ExprError as ex:
        return {"error": ex.message, "etype": ex.etype}
    except QuantityError as ex:
        return {"error": ex.message, "etype": "QuantityError"}
    except Exception as ex:   # noqa: BLE001 - a bug in the port: counted as a difference of its own
        return {"error": f"{type(ex).__name__}: {ex}", "etype": "Crash"}


def run_all(texts):
    old = fcexpr.QUIRKS.int32_cast
    fcexpr.QUIRKS.int32_cast = True   # as exprdiff-entry.ts: FreeCAD's integral numbers above 2^31 are -2147483648
    try:
        e = env()
        return [run(t, e) for t in texts]
    finally:
        fcexpr.QUIRKS.int32_cast = old


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--show", type=int, default=6, help="examples printed per kind")
    ap.add_argument("--kind", help="print only this kind")
    ap.add_argument("--category", help="only the cases of this category")
    ap.add_argument("--limit", type=int, help="only the first N cases of the selection")
    ap.add_argument("--list", help="write every difference to this JSON file")
    ap.add_argument("--against-ts", help="a JSON list of expr.ts's answers to every case (scripts/exprdiff_ours.mjs): compare too")
    args = ap.parse_args()
    exprdiff = load_exprdiff()
    header, cases, fc = exprdiff.read_answers()
    if exprdiff.digest_of([t for _, t in cases]) != header.get("digest"):
        sys.exit("exprdiff_py: the answers file does not match its own digest: it was edited")
    ts = json.loads(Path(args.against_ts).read_text(encoding="utf-8")) if args.against_ts else None
    keep = list(range(len(cases)))
    if args.category:
        keep = [i for i in keep if cases[i][0] == args.category]
    if args.limit:
        keep = keep[:args.limit]
    cases, fc = [cases[i] for i in keep], [fc[i] for i in keep]
    ts = [ts[i] for i in keep] if ts else None
    f = header.get("freecad") or {}
    print(f"exprdiff_py: {len(cases)} cases, FreeCAD {f.get('version')} ({str(f.get('commit'))[:12]}), through cad_agent.fcexpr ...", flush=True)
    t0 = time.time()
    ours = run_all([t for _, t in cases])
    print(f"exprdiff_py: {time.time() - t0:.1f} s")

    diffs, set_aside = [], Counter()
    for (cat, text), o, a in zip(cases, ours, fc):
        d = exprdiff.differs(o, a)
        if d:
            why = exprdiff.excused(o, a)
            if why:
                set_aside[why] += 1
            else:
                diffs.append((d[0], cat, text, o, a, d[1]))
    kinds = Counter(d[0] for d in diffs)
    print(f"\n{len(cases)} cases, {len(diffs)} differ" + ("" if not diffs else "  (" + ", ".join(f"{k} {n}" for k, n in kinds.most_common()) + ")"))
    for why, n in set_aside.items():
        print(f"set aside: {n} cases, {why}")
    if diffs:
        by_cat = Counter(d[1] for d in diffs)
        totals = Counter(c for c, _ in cases)
        print("by category: " + ", ".join(f"{c} {by_cat[c]}/{totals[c]}" for c in totals if by_cat[c]))
    shown = defaultdict(int)
    for kind, cat, text, o, a, why in diffs:
        if (args.kind and kind != args.kind) or shown[kind] >= args.show:
            continue
        shown[kind] += 1
        print(f"  [{kind}] ({cat}) {text!r}{'  ' + why if why else ''}\n      ours    {exprdiff.show(o)}\n      FreeCAD {exprdiff.show(a)}")
    if ts is not None:
        apart = [(c, t, o, x) for (c, t), o, x in zip(cases, ours, ts) if exprdiff.differs(o, x)]
        print(f"\nagainst expr.ts: {len(apart)} of {len(cases)} answers differ")
        for c, t, o, x in apart[:args.show]:
            print(f"  ({c}) {t!r}\n      python  {exprdiff.show(o)}\n      expr.ts {exprdiff.show(x)}")
    if args.list:
        Path(args.list).write_text(json.dumps([{"kind": k, "cat": c, "e": t, "ours": o, "fc": a} for k, c, t, o, a, _ in diffs], indent=0), encoding="utf-8")
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main())

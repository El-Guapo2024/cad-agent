#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Differential test of the formula engine: ui/src/expr.ts against the real FreeCAD's expression language.

The cases (scripts/exprdiff_cases.py: some 75,000 expressions, from numbers and units, unit arithmetic and conversion,
precedence, functions, constants, strings, conditionals and names to syntax errors and fuzzing, derived from the lexer, the
grammar and the tests of FreeCAD main 3160daf1e2b6, the commit PARITY.md ports) were run through the real FreeCAD 26.3 once,
on a machine that has it (freecadcmd, DocumentObject.evalExpression on an object that owns the properties
exprdiff_cases.PROPERTIES lists). Its answers are stored in scripts/exprdiff/fc_answers.json.gz, so this compares our
TypeScript evaluator (bundled for Node by vite) with them and needs no FreeCAD. Every disagreement is listed by kind.

    python3 scripts/exprdiff.py                         # against the stored answers; exit 1 if anything differs
    python3 scripts/exprdiff.py --loose                 # numbers and units only (for an evaluator that has no Python types)
    python3 scripts/exprdiff.py --show 5 --kind value   # five examples of each kind (or only that kind)
    python3 scripts/exprdiff.py --category fn --limit 2000
    python3 scripts/exprdiff.py --list diffs.json       # every difference, in a file
    python3 scripts/exprdiff.py --record                # (needs FreeCAD) run every case through it, store the answers, compare
    python3 scripts/exprdiff.py --fc --category str     # (needs FreeCAD) compare with a live run of the selection, store nothing
    python3 scripts/exprdiff.py --emit-engine E.mjs --emit-fixture F.json   # what tests/test_expr_parity.py runs (see below)

The answers file: gzip JSON, {"freecad": the build the answers come from, "object": the properties, "digest": a hash of the
case texts, "cases": [[category, expression, answer], ...]}. An answer is what exprdiff_fc.py writes: {"t": "quantity", "v":
10.0, "dims": [1, 0, 0, 0, 0, 0, 0, 0]}, {"t": "int", "v": "3"}, {"t": "str", "v": "abc"}, {"t": "list", "v": [...]},
{"t": "vector", "v": [x, y, z]} ..., or {"error": the exception's text, "etype": its Python class}. nan, inf and -0.0 are the
strings "nan", "inf", "-inf" and "-0.0". `--record` rewrites the file from exprdiff_cases.cases(); EXPRDIFF_SEED=N adds other random
cases (a file of its own: `--record --answers other.json.gz`).

Kinds: type (the Python type of the answer: int, float, bool, str, a Quantity ...), value, dims, missing (ours raises where
FreeCAD answers), accepted (ours answers where FreeCAD raises), etype (the exception class), message (its text, "in
expression:" tail included), shape (a list differs in length). --loose compares only numbers and units, errors against values.
EXPRDIFF_RTOL sets how close two floats must be (default 1e-13; 0 is bit for bit).

Our side is the TypeScript entry (--entry, default scripts/exprdiff-entry.ts): an ES module that exports run(text), the answer in
the form above. It is bundled by vite, so the UI's node_modules must be there (`npm ci` in ui/). --emit-engine bundles it
minified into one file, and --emit-fixture writes a few hundred of the cases with FreeCAD's answers: tests/test_expr_parity.py
runs the one through the other without vite or FreeCAD (ENGINE_SOURCES below lists what the bundle is made of, so the test can
tell that it is stale).

--record and --fc need FreeCAD.app (FREECAD_APP overrides ~/.cad-agent/freecad/FreeCAD.app); it runs headless with its user
files in a temporary folder, one process at a time.
"""
import argparse
import gzip
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
UI = HERE.parent
sys.path.insert(0, str(HERE))
import exprdiff_cases  # noqa: E402

ANSWERS = HERE / "exprdiff" / "fc_answers.json.gz"
APP = Path(os.environ.get("FREECAD_APP", "~/.cad-agent/freecad/FreeCAD.app")).expanduser()
RTOL = float(os.environ.get("EXPRDIFF_RTOL", "1e-13"))   # how close two floats must be: a few units in the last place by default; 0 for bit for bit
SOURCE = "https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b62b0472854da4848255c6b3ad554c"
LOCAL_PATH = re.compile(r"/(?:Users|home|private|var/folders)/[\w.-]")   # the start of a folder of the machine that ran FreeCAD


def freecadcmd():
    for name in ("freecadcmd", "FreeCADCmd"):
        p = APP / "Contents" / "Resources" / "bin" / name
        if p.exists():
            return p
    sys.exit(f"exprdiff: no freecadcmd in {APP} (set FREECAD_APP): --record and --fc need FreeCAD")


def run_freecad(texts, tmp, chunk=4000, timeout=180):
    """FreeCAD's answers, one per text, and which FreeCAD it is. A crash or a hang ends one process: the case it stopped on is
    recorded as an answer of its own and the next process starts after it."""
    home = Path(tmp) / "fchome"
    home.mkdir(exist_ok=True)
    inp, out, meta_file = Path(tmp) / "fc_in.json", Path(tmp) / "fc_out.jsonl", Path(tmp) / "fc_meta.json"
    env = {**os.environ, "FCDIFF_IN": str(inp), "FCDIFF_OUT": str(out), "FCDIFF_META": str(meta_file), "FREECAD_USER_HOME": str(home),
           "FREECAD_USER_DATA": str(home / "data"), "FREECAD_USER_TEMP": str(home / "tmp")}
    done, idle = [], 0
    while len(done) < len(texts):
        start = len(done)
        stop = min(len(texts), start + chunk)
        job = {"doc": exprdiff_cases.DOC, "owner": exprdiff_cases.OWNER, "props": exprdiff_cases.PROPERTIES, "cases": texts[start:stop]}
        inp.write_text(json.dumps(job), encoding="utf-8")
        out.write_text("")
        tail = ""
        try:
            r = subprocess.run([str(freecadcmd()), str(HERE / "exprdiff_fc.py")], env=env, stdin=subprocess.DEVNULL,
                               capture_output=True, text=True, timeout=timeout)
            how, tail = f"exit {r.returncode}", (r.stdout + r.stderr)[-600:]
        except subprocess.TimeoutExpired:
            how = "timeout"
        lines = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines() if x.strip()]
        done += lines
        idle = 0 if lines else idle + 1
        if idle >= 3:
            sys.exit(f"exprdiff: FreeCAD does not answer ({how}): {tail}")
        if len(done) < stop:   # the process stopped before the end of its chunk: the case after the last answer is the culprit
            culprit = len(done)
            done.append({"error": f"FreeCAD stopped here ({how})", "etype": "Crash"})
            print(f"exprdiff: FreeCAD stopped ({how}) on case {culprit}: {texts[culprit]!r}", file=sys.stderr)
    meta = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.exists() else {}
    return done[:len(texts)], meta


def digest_of(texts):
    return hashlib.sha256("\n".join(texts).encode("utf-8", "surrogatepass")).hexdigest()


def read_answers(path=ANSWERS):
    """(the file's header, [(category, text)], [answer]) from a file write_answers made (gzip or plain JSON)."""
    raw = Path(path).read_bytes()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    data = json.loads(raw.decode("utf-8"))
    rows = data.pop("cases")
    return data, [(c, t) for c, t, _ in rows], [a for _, _, a in rows]


def write_answers(path, freecad, cases, answers):
    """Store FreeCAD's answers with the cases, the properties of the object they were asked on, and the FreeCAD they came from."""
    header = {"freecad": freecad, "source": SOURCE, "how": "DocumentObject.evalExpression on an App::FeaturePython object",
              "object": {"doc": exprdiff_cases.DOC, "owner": exprdiff_cases.OWNER, "properties": exprdiff_cases.PROPERTIES},
              "digest": digest_of([t for _, t in cases]), "count": len(cases)}
    body = json.dumps({**header, "cases": [[c, t, a] for (c, t), a in zip(cases, answers)]}, separators=(",", ":")).encode("ascii")
    text = body.decode("ascii")
    local = LOCAL_PATH.search(text) or (re.search(re.escape(str(Path.home())), text) if str(Path.home()) != "/" else None)
    if local:   # a message FreeCAD wrote that names a folder of this machine does not belong in the repository
        sys.exit(f"exprdiff: refusing to store a local path, found near {text[max(0, local.start() - 80):local.end() + 80]!r}")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(body, 9, mtime=0) if path.suffix == ".gz" else body)
    return len(body), path.stat().st_size


# What the engine in tests/golden/expr is built from; tests/test_expr_parity.py recomputes this to see that it is current.
# (A file named here that does not exist is left out: list the files of the evaluator you have.)
ENGINE_SOURCES = ["src/expr.ts", "src/expr-py.ts", "src/expr-grammar.ts", "src/quantity.ts", "src/units-data.ts", "src/units-schemas.ts",
                  "scripts/exprdiff-entry.ts"]


def source_hash():
    """A hash of the sources the engine bundle is made of (line ends as in git, so a checkout on any system gives the same)."""
    h = hashlib.sha256()
    for name in ENGINE_SOURCES:
        if (UI / name).exists():
            h.update(name.encode() + b"\0" + (UI / name).read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()


BANNER = ("/* SPDX-License-Identifier: LGPL-2.1-or-later\n * ui/src/expr.ts and what it uses, bundled for Node by ui/scripts/exprdiff.py --emit-engine.\n"
          " * It follows FreeCAD main 3160daf1e2b6 (LGPL-2.0-or-later and LGPL-2.1-or-later); ui/NOTICE names the files and their authors. */")


def build_engine(entry, out_file, minify=False, banner=""):
    """Bundle `entry` (an ES module exporting run(text)) with vite for Node; out_file is the one file it makes."""
    out_file = Path(out_file)
    if not (UI / "node_modules" / "vite").exists():
        sys.exit("exprdiff: no ui/node_modules/vite: run `npm ci` in ui/ first")
    with tempfile.TemporaryDirectory(prefix="exprengine") as work:     # vite empties the folder it writes to: never the target's
        build = ("import('vite').then((v) => v.build({ configFile: false, root: %r, publicDir: false, logLevel: 'error',"
                 " build: { ssr: %r, outDir: %r, emptyOutDir: true, minify: %s, rollupOptions: { output: { entryFileNames: %r, banner: %r } } } }))"
                 % (str(UI), str(entry), work, "true" if minify else "false", "engine.mjs", banner))
        subprocess.run(["node", "-e", build], cwd=UI, check=True)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_bytes((Path(work) / "engine.mjs").read_bytes())


def run_engine(engine, texts, tmp):
    """Every text through a bundle made by build_engine; the answers, as scripts/exprdiff_ours.mjs writes them."""
    inp, out = Path(tmp) / "ours_in.json", Path(tmp) / "ours_out.json"
    inp.write_text(json.dumps(texts), encoding="utf-8")
    subprocess.run(["node", str(HERE / "exprdiff_ours.mjs"), Path(engine).resolve().as_uri(), str(inp), str(out)], cwd=UI, check=True)
    return json.loads(out.read_text(encoding="utf-8"))


def run_ours(texts, entry, tmp):
    outdir = Path(tmp) / "bundle"
    build_engine(entry, outdir / "entry.mjs")
    return run_engine(outdir / "entry.mjs", texts, tmp)


def num(x):
    """A JSON number or one of the strings 'nan', 'inf', '-inf', '-0.0' as a float."""
    return float(x)


def close(a, b):
    a, b = num(a), num(b)
    if math.isnan(a) or math.isnan(b):
        return math.isnan(a) and math.isnan(b)
    if a == b:
        return math.copysign(1, a) == math.copysign(1, b) or a != 0
    if math.isinf(a) or math.isinf(b) or a == 0 or b == 0:
        return False
    return abs(a - b) <= RTOL * max(abs(a), abs(b))


def differs(o, f, loose=False):
    """None if the two answers agree, else (kind, what)."""
    if "error" in o or "error" in f:
        if "error" in o and "error" in f:
            if loose:
                return None
            if o.get("etype") != f.get("etype"):
                return "etype", f"{o.get('etype')} vs {f.get('etype')}"
            # a Python SystemError names the object it came from by address
            return None if re.sub(r"0x[0-9a-f]+", "0x0", o["error"]) == re.sub(r"0x[0-9a-f]+", "0x0", f["error"]) else ("message", "")
        return ("missing", "") if "error" in o else ("accepted", "")
    if loose:
        def flat(x):
            if x["t"] in ("int", "float", "bool", "quantity"):
                v = x["v"]
                v = {True: 1.0, False: 0.0}.get(v, v) if isinstance(v, bool) else num(v)
                return {"t": "n", "v": v, "dims": x.get("dims", [0] * 8)}
            return x
        o, f = flat(o), flat(f)
    if o["t"] != f["t"]:
        return "type", f"{o['t']} vs {f['t']}"
    t = f["t"]
    if t in ("n", "quantity"):
        if o["dims"] != f["dims"]:
            return "dims", f"{o['dims']} vs {f['dims']}"
        return None if close(o["v"], f["v"]) else ("value", "")
    if t == "float":
        return None if close(o["v"], f["v"]) else ("value", "")
    if t == "complex":
        return None if close(o["re"], f["re"]) and close(o["im"], f["im"]) else ("value", "")
    if t in ("vector", "matrix", "rotation"):
        return None if len(o["v"]) == len(f["v"]) and all(close(a, b) for a, b in zip(o["v"], f["v"])) else ("value", "")
    if t == "placement":
        same = all(close(a, b) for a, b in zip(o["base"] + o["q"], f["base"] + f["q"]))
        return None if same else ("value", "")
    if t in ("list", "tuple"):
        if len(o["v"]) != len(f["v"]):
            return "shape", "length"
        for a, b in zip(o["v"], f["v"]):
            d = differs(a, b, loose)
            if d:
                return d
        return None
    if t == "other":
        return None if (o.get("type"), o.get("str")) == (f.get("type"), f.get("str")) else ("value", "")
    return None if o.get("v") == f.get("v") else ("value", "")


def excused(o, f):
    """Why a difference is not counted, or None. An evaluator that does not build a Matrix, a Placement or a Rotation (a quantity
    field cannot hold one) may say so with a NotImplementedError where FreeCAD makes one, or fails trying and Python reports it
    as a SystemError: the case is set aside (and counted, in the line below the totals)."""
    if o.get("etype") == "NotImplementedError" and (f.get("t") in ("matrix", "rotation", "placement") or f.get("etype") == "SystemError"):
        return "Matrix, Placement or Rotation not built"
    if o.get("etype") == f.get("etype") == "UnicodeDecodeError":   # the text of a string that is not UTF-8: FreeCAD's position is stray memory
        return "UTF-8 position in an error message"
    return None


def show(r):
    s = json.dumps(r, ensure_ascii=False)
    return s if len(s) < 230 else s[:227] + "..."


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--entry", default=str(HERE / "exprdiff-entry.ts"), help="the TypeScript entry that exports run(text)")
    ap.add_argument("--answers", default=str(ANSWERS), help="the file of FreeCAD's answers: read, or written by --record")
    ap.add_argument("--record", action="store_true", help="run every case of exprdiff_cases through FreeCAD (needs it) and store the answers")
    ap.add_argument("--fc", action="store_true", help="compare with a live FreeCAD run of the selected cases (needs it), storing nothing")
    ap.add_argument("--loose", action="store_true", help="compare numbers and units only")
    ap.add_argument("--show", type=int, default=6, help="examples printed per kind")
    ap.add_argument("--kind", help="print only this kind")
    ap.add_argument("--category", help="only the cases of this category (as the 'by category' line names them)")
    ap.add_argument("--limit", type=int, help="only the first N cases of the selection")
    ap.add_argument("--emit-fixture", help="write a sample of the cases with FreeCAD's answers here")
    ap.add_argument("--sample", type=int, default=400, help="size of that sample")
    ap.add_argument("--emit-engine", help="write the evaluator, bundled for Node, here (what tests/test_expr_parity.py runs the sample through)")
    ap.add_argument("--list", help="write every difference to this JSON file")
    args = ap.parse_args()
    if args.record and (args.category or args.limit or args.fc):
        ap.error("--record runs every case: leave out --category, --limit and --fc")

    freecad = None
    if args.record or args.fc:
        cases = exprdiff_cases.cases()
        if args.category:
            cases = [c for c in cases if c[0] == args.category]
        if args.limit:
            cases = cases[:args.limit]
        print(f"exprdiff: {len(cases)} cases through FreeCAD ...", flush=True)
        with tempfile.TemporaryDirectory(prefix="exprdiff") as tmp:
            fc, freecad = run_freecad([t for _, t in cases], tmp)
        if args.record:
            raw, packed = write_answers(args.answers, freecad, cases, fc)
            print(f"exprdiff: {len(cases)} answers stored ({raw:,} bytes, {packed:,} packed) in {args.answers}")
    else:
        header, cases, fc = read_answers(args.answers)
        freecad = header.get("freecad")
        if digest_of([t for _, t in cases]) != header.get("digest"):
            sys.exit(f"exprdiff: {args.answers} does not match its own digest: it was edited")
        if args.category:
            keep = [i for i, (c, _) in enumerate(cases) if c == args.category]
            cases, fc = [cases[i] for i in keep], [fc[i] for i in keep]
        if args.limit:
            cases, fc = cases[:args.limit], fc[:args.limit]
    texts = [t for _, t in cases]
    if freecad:
        print(f"exprdiff: {len(cases)} cases, FreeCAD {freecad.get('version')} ({freecad.get('revision')}, {str(freecad.get('commit'))[:12]})", flush=True)
    with tempfile.TemporaryDirectory(prefix="exprdiff") as tmp:
        print("exprdiff: through ours ...", flush=True)
        ours = run_ours(texts, args.entry, tmp)

    diffs, set_aside = [], Counter()
    for (cat, text), o, f in zip(cases, ours, fc):
        d = differs(o, f, args.loose)
        if d:
            why = excused(o, f)
            if why:
                set_aside[why] += 1
            else:
                diffs.append((d[0], cat, text, o, f, d[1]))
    kinds = Counter(d[0] for d in diffs)
    print(f"\n{len(cases)} cases, {len(diffs)} differ" + ("" if not diffs else "  (" + ", ".join(f"{k} {n}" for k, n in sorted(kinds.items(), key=lambda kv: -kv[1])) + ")"))
    for why, n in set_aside.items():
        print(f"set aside: {n} cases, {why}")
    if diffs:
        by_cat = Counter(d[1] for d in diffs)
        totals = Counter(c for c, _ in cases)
        print("by category: " + ", ".join(f"{c} {by_cat[c]}/{totals[c]}" for c in totals if by_cat[c]))
    shown = defaultdict(int)
    for kind, cat, text, o, f, why in diffs:
        if args.kind and kind != args.kind:
            continue
        if shown[kind] >= args.show:
            continue
        shown[kind] += 1
        print(f"  [{kind}] ({cat}) {text!r}{'  ' + why if why else ''}\n      ours    {show(o)}\n      FreeCAD {show(f)}")
    if args.list:
        Path(args.list).write_text(json.dumps([{"kind": k, "cat": c, "e": t, "ours": o, "fc": f} for k, c, t, o, f, _ in diffs], indent=0), encoding="utf-8")
    if args.emit_fixture:
        emit_fixture(Path(args.emit_fixture), cases, fc, args.sample, source_hash(), freecad)
    if args.emit_engine:
        build_engine(args.entry, args.emit_engine, minify=True, banner=BANNER)
        print(f"exprdiff: the evaluator, bundled, in {args.emit_engine}")
    return 1 if diffs else 0


def answer_shape(f):
    """What kind of answer FreeCAD gave: its type, or its exception class and the words of its message."""
    if "error" in f:
        msg = re.sub(r"\nin expression: .*", "", f["error"], flags=re.S)
        msg = re.sub(r"'[^']*'|\"[^\"]*\"|0x[0-9a-f]+|[0-9]+", "#", msg)
        return ("E", f["etype"], msg)
    return ("V", f["t"], tuple(f["dims"]) if f["t"] == "quantity" else None)


def emit_fixture(path, cases, fc, n, sources, freecad=None):
    """A sample of the cases, with FreeCAD's answers: one or two of every kind of answer in each category, then cases spread
    evenly through each category up to `n` in all."""
    by_cat = defaultdict(list)
    for (cat, text), f in zip(cases, fc):
        by_cat[cat].append((cat, text, f))
    total = sum(len(v) for v in by_cat.values())
    picked, taken = [], set()
    for cat, items in by_cat.items():
        seen = defaultdict(int)
        for c, t, f in items:
            key = answer_shape(f)
            if seen[key] < (2 if key[0] == "E" else 1):
                seen[key] += 1
                picked.append((c, t, f))
                taken.add(t)
    room = max(0, n - len(picked))
    for cat, items in by_cat.items():
        rest = [x for x in items if x[1] not in taken]
        quota = round(room * len(items) / total)
        if quota and rest:
            step = max(1, len(rest) // quota)
            for x in rest[::step][:quota]:
                picked.append(x)
                taken.add(x[1])
    picked.sort(key=lambda x: (x[0], x[1]))
    build = f"FreeCAD {freecad['version']} ({freecad['revision']}, {freecad['commit'][:12]})" if freecad else "FreeCAD 26.3.0 (git 3160daf1e2b6)"
    fixture = {"freecad": f"{build}, DocumentObject.evalExpression",
               "names": exprdiff_cases.NAMES, "sources": sources,
               "cases": [{"c": c, "e": t, "r": f} for c, t, f in picked]}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fixture, ensure_ascii=True, indent=0) + "\n", encoding="utf-8")
    print(f"exprdiff: {len(picked)} cases written to {path}")


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Write cad_agent/fcexpr_engine.js: the page's formula engine (ui/src/expr.ts and what it uses) with
ui/scripts/expr-server-entry.ts, bundled by vite as one classic script that cad_agent/fcexpr.py runs in V8 (mini-racer).
The server has no formula engine of its own: this is the one the browser runs. The bundle's banner carries a hash of its
sources, so tests/test_fcexpr.py can tell that it is stale.

    python3 ui/scripts/fcexprjs.py            # write the bundle (needs `npm ci` in ui/)
    python3 ui/scripts/fcexprjs.py --check    # exit 1 if the bundle is not of the current sources
"""
import argparse
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
UI = HERE.parent
REPO = UI.parent
OUT = REPO / "cad_agent" / "fcexpr_engine.js"
SOURCES = ["src/expr.ts", "src/expr-py.ts", "src/expr-grammar.ts", "src/quantity.ts", "src/units-data.ts", "src/units-schemas.ts",
           "scripts/expr-server-entry.ts"]
MARK = "// sources: "


def source_hash():
    """A hash of the sources the bundle is made of (line ends as in git, so a checkout on any system gives the same)."""
    h = hashlib.sha256()
    for name in SOURCES:
        h.update(name.encode() + b"\0" + (UI / name).read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()


def banner():
    return ("/* SPDX-License-Identifier: LGPL-2.1-or-later\n * ui/src/expr.ts and what it uses, with ui/scripts/expr-server-entry.ts, bundled "
            "by ui/scripts/fcexprjs.py for cad_agent/fcexpr.py.\n * It follows FreeCAD main 3160daf1e2b6 (LGPL-2.0-or-later and "
            "LGPL-2.1-or-later); ui/NOTICE names the files and their authors. */\n" + MARK + source_hash())


def bundled_hash(path=OUT):
    for line in path.read_text(encoding="utf-8").splitlines()[:8]:
        if line.startswith(MARK):
            return line[len(MARK):].strip()
    return None


def build(out=OUT):
    if not (UI / "node_modules" / "vite").exists():
        sys.exit("fcexprjs: no ui/node_modules/vite: run `npm ci` in ui/ first")
    with tempfile.TemporaryDirectory(prefix="fcexprjs") as work:   # vite empties the folder it writes to: never the target's
        js = ("import('vite').then((v) => v.build({ configFile: false, root: %r, publicDir: false, logLevel: 'error', build: {"
              " outDir: %r, emptyOutDir: true, minify: false, lib: { entry: %r, formats: ['iife'], name: 'FCExprBundle',"
              " fileName: () => 'engine.js' }, rollupOptions: { output: { banner: %r } } } }))"
              % (str(UI), work, str(HERE / "expr-server-entry.ts"), banner()))
        subprocess.run(["node", "-e", js], cwd=UI, check=True)
        text = (Path(work) / "engine.js").read_text(encoding="utf-8")
    out.write_text(text, encoding="utf-8")
    return text


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if the bundle is stale")
    args = ap.parse_args()
    if args.check:
        current = OUT.exists() and bundled_hash() == source_hash()
        print(f"fcexprjs: {OUT} is {'current' if current else 'STALE: run python3 ui/scripts/fcexprjs.py'}")
        sys.exit(0 if current else 1)
    text = build()
    print(f"fcexprjs: wrote {OUT} ({len(text):,} bytes)")


if __name__ == "__main__":
    main()

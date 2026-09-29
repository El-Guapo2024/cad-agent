#!/usr/bin/env python3
"""Stop hook: a session can't end quietly over a changed cad project that isn't verified.

When Claude is about to stop, this asks `cad done` about every cad project it
can see: the repo's projects/ and CAD_PROJECTS. A project counts as touched if
its design has uncommitted changes, its last verdict no longer matches the
files, or it has never been verified but its design files changed in the last
12 hours. If a touched project is not done, this prints
{"decision": "block", "reason": ...}. Claude then either verifies it (commit,
`cad verify`, `cad done`) or tells the user plainly that it isn't verified.

It blocks once. When Claude stops again right after, stop_hook_active is true
and the stop goes through: the point is that "not done" gets said, not a loop.
`cad done` never imports the CAD kernel, so this takes about half a second per
project. Standard library only; the CLI does the work.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CAD = REPO / "bin" / "cad"
RECENT_S = 12 * 3600
TOUCHED = ("the design changed since it was verified", "the design has uncommitted changes",
           "it verified uncommitted changes")
DESIGN = ("parts", "bought", "baseline")


def cad(*argv):
    env = dict(os.environ, CAD_WARM="0")         # done and ls never need the kernel
    p = subprocess.run([str(CAD), "--json", *argv], capture_output=True, text=True,
                       timeout=60, env=env)
    try:
        return json.loads(p.stdout.strip().splitlines()[-1]).get("data") or {}
    except (ValueError, IndexError):
        return {}


def recently_edited(project: Path) -> bool:
    files = [project / "assembly.py", project / "spec.toml"]
    for d in DESIGN:
        files += [p for p in (project / d).glob("*") if p.is_file()]
    newest = max((p.stat().st_mtime for p in files if p.exists()), default=0)
    return time.time() - newest < RECENT_S


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except ValueError:
        event = {}
    if event.get("stop_hook_active"):
        return 0
    roots = [REPO / "projects"]
    if os.environ.get("CAD_PROJECTS"):
        roots.append(Path(os.environ["CAD_PROJECTS"]).expanduser())
    open_items = []
    for root in (r.resolve() for r in roots if r.is_dir()):
        for slug in cad("--projects", str(root), "ls").get("projects", []):
            s = cad("--projects", str(root), "done", slug)
            if not s or s.get("done"):
                continue
            reasons = s.get("reasons", [])
            touched = any(r.startswith(TOUCHED) for r in reasons) or (
                s.get("verdict") is None and recently_edited(root / slug))
            if touched:
                open_items.append(f"  {slug} ({root}): " + "; ".join(reasons))
    if not open_items:
        return 0
    reason = ("cad: these projects changed but `cad done` rejects them:\n" + "\n".join(open_items)
              + "\nCommit the design, run `bin/cad verify <slug>` and `bin/cad done <slug>`, "
                "or tell the user plainly that the design is not verified and why.")
    print(json.dumps({"decision": "block", "reason": reason}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

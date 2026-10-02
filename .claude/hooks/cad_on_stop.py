#!/usr/bin/env python3
"""Stop hook: a session can't end quietly over a changed cad project that isn't verified.

When Claude is about to stop, this asks `cad done` about the projects this
session could have changed. A project counts as touched if any of these holds:

- the edit hook recorded it for this session (by session_id)
- its design has uncommitted changes
- its last verdict no longer matches its files

If a touched project is not done, this prints {"decision": "block", "reason": ...}.
Claude then either verifies it (commit, `cad verify`, `cad done`) or tells the
user plainly that it isn't verified. Old projects nobody touched are left
alone, even if they were never verified; file times are never used to guess,
because a fresh clone makes every file look new.

It blocks once. When Claude stops again right after, stop_hook_active is true
and the stop goes through: the point is that "not done" gets said, not a loop.
`cad done` never imports the CAD kernel, so this takes about half a second per
project. Standard library only; the CLI does the work.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CAD = REPO / "bin" / "cad"
CHANGED = ("the design changed since it was verified", "the design has uncommitted changes",
           "it verified uncommitted changes")


def cad(*argv):
    env = dict(os.environ, CAD_WARM="0")         # done and ls never need the kernel
    p = subprocess.run([str(CAD), "--json", *argv], capture_output=True, text=True,
                       timeout=60, env=env)
    try:
        return json.loads(p.stdout.strip().splitlines()[-1]).get("data") or {}
    except (ValueError, IndexError):
        return {}


def touched_this_session(session_id: str) -> set[tuple[str, str]]:
    if not session_id:
        return set()
    d = Path(os.environ.get("CAD_WARM_DIR") or Path.home() / ".cache" / "cad-agent")
    f = d / f"touched-{re.sub(r'[^A-Za-z0-9_-]', '_', session_id)}.tsv"
    try:
        return {tuple(line.split("\t", 1)) for line in f.read_text().splitlines() if "\t" in line}
    except OSError:
        return set()


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except ValueError:
        event = {}
    if event.get("stop_hook_active"):
        return 0
    touched = touched_this_session(event.get("session_id", ""))
    # The projects the CLI works on: CAD_PROJECTS (the plugin points it at the project's
    # cad-projects), else this checkout's own projects/. Run as a plugin without it, only what
    # this session touched: the plugin's bundled examples are nobody's work.
    env = os.environ.get("CAD_PROJECTS")
    roots = {str(Path(env).expanduser().resolve())} if env else set()
    if not env and not os.environ.get("CLAUDE_PLUGIN_ROOT"):
        roots.add(str((REPO / "projects").resolve()))
    roots |= {root for root, _ in touched}

    open_items = []
    for root in sorted(r for r in roots if Path(r).is_dir()):
        for slug in cad("--projects", root, "ls").get("projects", []):
            s = cad("--projects", root, "done", slug)
            if not s or s.get("done"):
                continue
            reasons = s.get("reasons", [])
            if (root, slug) in touched or any(r.startswith(CHANGED) for r in reasons):
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

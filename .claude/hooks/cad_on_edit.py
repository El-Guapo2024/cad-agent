#!/usr/bin/env python3
"""PostToolUse hook: after an edit to a cad project, run its gates and hand back what fails.

Claude Code sends the tool call as JSON on stdin. If the edited file is a part
module (<root>/<slug>/parts/<name>.py), an assembly.py or a spec.toml, this runs
`bin/cad check` on it (the part alone for a part, every gate otherwise) and,
when rows fail, prints {"decision": "block", "reason": ...} so the failures go
back to Claude. The edit has already happened; "block" means "read this before
going on".

Drift, extent and visual rows are left out: they wait on a human approving a
render, which is nothing to fix mid-edit. `cad verify` still gates them.
Standard library only; the CLI does the work.
"""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CAD = REPO / "bin" / "cad"
SKIP = ("drift/", "extent/", "visual/")
MAX_LINES = 12


def target(path: Path):
    """(projects root, slug, part or None) for a cad design file, else None."""
    if path.name in ("assembly.py", "spec.toml"):
        project, part = path.parent, None
    elif path.suffix == ".py" and path.parent.name == "parts" and not path.stem.startswith("_"):
        project, part = path.parent.parent, path.stem
    else:
        return None
    if not (project / "parts").is_dir():
        return None
    return project.parent, project.name, part


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    raw = (event.get("tool_input") or {}).get("file_path") or \
        (event.get("tool_response") or {}).get("filePath")
    hit = target(Path(raw).resolve()) if raw else None
    if hit is None:
        return 0
    root, slug, part = hit
    argv = [str(CAD), "--json", "--projects", str(root), "check", slug]
    if part:
        argv += ["--part", part]
    what = f"{slug}/{part}" if part else slug
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=280)
    except subprocess.TimeoutExpired:
        print(json.dumps({"systemMessage": f"cad check {what} timed out"}))
        return 0
    try:
        out = json.loads(p.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        out = {"exit": p.returncode, "data": {"error": (p.stderr or p.stdout)[-800:]}}
    code, data = out.get("exit", p.returncode), out.get("data") or {}
    if code == 0:
        return 0                                   # silence is a pass
    if "error" in data:
        reason = f"cad check {what} could not run (exit {code}): {data['error']}"
    else:
        rows = [r for r in data.get("rows", [])
                if r.get("state") in ("FAIL", "UNCHECKED")
                and not str(r.get("rule", "")).startswith(SKIP)]
        if not rows:
            return 0                               # only approval-dependent rows are open
        lines = [f"  {r['state']:9} {r.get('rule')} · {r.get('subject')}: {r.get('measured')}"
                 + (f" (limit {r['limit']})" if r.get("limit") not in (None, "n/a") else "")
                 for r in rows[:MAX_LINES]]
        if len(rows) > MAX_LINES:
            lines.append(f"  ...and {len(rows) - MAX_LINES} more (bin/cad check {slug} --all)")
        reason = f"cad check {what} after your edit:\n" + "\n".join(lines)
    print(json.dumps({"decision": "block", "reason": reason}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

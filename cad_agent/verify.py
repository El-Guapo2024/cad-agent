"""The verifier: rebuilds a project from source and decides whether it passes.

The agent that edits a design never grades it. `cad verify` rebuilds every
part and the assembly from what is on disk (never from the build cache that
`check` and `scene` keep for the edit loop), runs every gate, and writes
verify.json with the verdict and exactly what was verified:

    source_hash  sha256 over every file that defines the design: parts,
                 assembly, spec, bought geometry and the approved renders
    engine_hash  sha256 over cad-agent's own source, because a change to a
                 rule changes what "passes" means; read before the run and
                 again after it, so a verdict is never written for rules that
                 changed in between (a `git pull` mid-verify)
    git          the commit, the project's tree at that commit, and whether
                 the design had uncommitted changes
    process      whether it ran in a fresh process: a warm-worker fork or a
                 new interpreter, never a process that already ran commands

`cad done` accepts a verdict only while its hashes still match the disk,
only from a fresh process, and, inside a repo, only on committed work.
Anything else is UNCHECKED: a verdict about files that have since changed is
a verdict about a different design.

Why a separate command and not one more tool: build123d-mcp found that a
verifier the agent calls in-process made results worse, because the agent
read "conforms" as a stop signal. Here the verdict is a file with hashes the
agent cannot argue with, and `done` is the only gate.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path

from . import state as st

PKG = Path(__file__).resolve().parent
DESIGN = ("parts/*.py", "assembly.py", "spec.toml", "placements.toml", "bought/*",
          "baseline/*.png")
OUTPUTS = ("checks.json", "verify.json")      # written by runs, never inputs


def design_files(pdir: Path) -> list[Path]:
    files = set()
    for pattern in DESIGN:
        files.update(p for p in pdir.glob(pattern) if p.is_file())
    return sorted(files)


def source_hash(pdir: Path) -> tuple[str, int]:
    """Hash of the design as it is on disk: path and content of every input."""
    h = hashlib.sha256()
    files = design_files(pdir)
    for p in files:
        h.update(p.relative_to(pdir).as_posix().encode() + b"\0")
        h.update(hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest(), len(files)


def engine_hash() -> str:
    """Hash of cad-agent's own code: the rules are part of every verdict."""
    h = hashlib.sha256()
    for p in sorted(PKG.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        h.update(p.relative_to(PKG).as_posix().encode() + b"\0")
        h.update(hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()


def _git(real: Path, *args: str, raw: bool = False) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(real), *args], capture_output=True,
                           text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    return r.stdout if raw else r.stdout.strip()


def _changed_paths(real: Path) -> list[str]:
    """Paths `git status` reports, parsed from -z output (no quoting, and no
    stripping: the first status column is often a space)."""
    out = _git(real, "status", "--porcelain", "-z", "--untracked-files=all", "--", ".",
               raw=True) or ""
    tokens, paths, i = out.split("\0"), [], 0
    while i < len(tokens):
        entry = tokens[i]
        if len(entry) > 3:
            paths.append(entry[3:])
            if entry[0] in "RC":               # a rename or copy carries its old path next
                i += 1
        i += 1
    return paths


def git_info(pdir: Path) -> dict | None:
    """Commit, project tree at that commit, and uncommitted design changes.

    Projects are often symlinked in from elsewhere, so this works on the real
    path. Run outputs (checks.json, verify.json, out/, .cad/) are not design,
    so they never make the tree dirty.
    """
    real = pdir.resolve()
    top = _git(real, "rev-parse", "--show-toplevel")
    if top is None:
        return None
    rel = real.relative_to(Path(top).resolve()).as_posix() or "."
    head = _git(real, "rev-parse", "HEAD")
    changed = []
    for path in _changed_paths(real):
        name = path.rsplit("/", 1)[-1]
        if name in OUTPUTS or "/out/" in f"/{path}" or "/.cad/" in f"/{path}" \
                or "/__pycache__/" in f"/{path}":
            continue
        changed.append(path)
    tree = None
    if head:
        tree = _git(real, "rev-parse", "HEAD^{tree}" if rel == "." else f"HEAD:{rel}")
    return {"repo": top, "path": rel, "commit": head, "tree": tree,
            "dirty": bool(changed), "uncommitted": changed[:20]}


def _verdict(rows, parts_failed: int) -> str:
    states = {r["state"] for r in rows}
    if parts_failed or "FAIL" in states:
        return "FAIL"
    if "UNCHECKED" in states:
        return "UNCHECKED"
    return "PASS"


def run(slug: str, fresh: bool, mode: str, views=("iso",)) -> dict:
    """Rebuild everything, run every gate, write verify.json. Returns the record."""
    from .runner import check_all
    pdir = st.project_dir(slug)
    before, n_files = source_hash(pdir)
    engine = engine_hash()
    t0 = time.perf_counter()
    payload = check_all(slug, render_views=tuple(views), cached=False)   # never the build cache: see buildcache.py
    after, _ = source_hash(pdir)
    rows, summary = payload["rows"], payload["summary"]

    verdict = _verdict(rows, summary.get("parts_failed", 0))
    notes = []
    if before != after:
        verdict = "UNCHECKED"
        notes.append("the design changed while it was being verified; run again")
    if engine_hash() != engine:
        verdict = "UNCHECKED"
        notes.append("cad-agent's own code changed while it was being verified; run again")
    if not fresh:
        if verdict == "PASS":
            verdict = "UNCHECKED"
        notes.append("not a fresh process: this process had already run commands, "
                     "so run `cad verify` from a shell")
    git = git_info(pdir)
    if git and git["dirty"]:
        notes.append("verified uncommitted changes: commit, then verify again for it to count")

    record = {
        "project": slug,
        "verdict": verdict,
        "written_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "seconds": round(time.perf_counter() - t0, 1),
        "source_hash": before,
        "design_files": n_files,
        "engine_hash": engine,
        "git": git,
        "process": {"fresh": fresh, "mode": mode},
        "views": list(views),
        "summary": summary,
        "notes": notes,
        "rows": rows,
    }
    st.write_atomic(pdir / "verify.json", json.dumps(record, indent=2))
    return record


def status(slug: str) -> dict:
    """Whether the last verdict still stands, and every reason it does not."""
    pdir = st.project_dir(slug)
    path = pdir / "verify.json"
    if not path.exists():
        reasons = ["never verified: run `cad verify`"]
        git = git_info(pdir)
        if git and git.get("dirty"):
            reasons.append("the design has uncommitted changes")
        return {"project": slug, "done": False, "verdict": None, "reasons": reasons}
    try:
        rec = json.loads(path.read_text())
        if not (isinstance(rec, dict) and isinstance(rec.get("process", {}), dict)
                and isinstance(rec.get("git"), (dict, type(None)))):
            raise ValueError("not a verify record")
    except (OSError, ValueError) as e:
        return {"project": slug, "done": False, "verdict": None,
                "reasons": [f"verify.json cannot be read ({e}): run `cad verify` to write it again"]}
    reasons = []
    current, _ = source_hash(pdir)
    if current != rec.get("source_hash"):
        reasons.append("the design changed since it was verified")
    if engine_hash() != rec.get("engine_hash"):
        reasons.append("cad-agent's rules changed since it was verified")
    if not rec.get("process", {}).get("fresh"):
        reasons.append("the verdict came from a process that was not fresh")
    git = rec.get("git")
    if git and git.get("dirty"):
        reasons.append("it verified uncommitted changes: commit, then verify again")
    now = git_info(pdir) if git else None
    if now and now.get("dirty") and "the design changed since it was verified" not in reasons:
        reasons.append("the design has uncommitted changes")
    if rec.get("verdict") != "PASS":
        reasons.append(f"the verdict was {rec.get('verdict')}")
    return {"project": slug, "done": not reasons, "verdict": rec.get("verdict"),
            "reasons": reasons, "verified_utc": rec.get("written_utc"),
            "commit": (git or {}).get("commit"), "process": rec.get("process"),
            "failing": [r for r in rec.get("rows", []) if r["state"] in ("FAIL", "UNCHECKED")]}

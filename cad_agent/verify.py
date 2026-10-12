"""The verifier: rebuilds a project from source and decides whether it passes.

The agent that edits a design never grades it. `cad verify` rebuilds every
part and the assembly from what is on disk (never from the build cache that
`check` and `scene` keep for the edit loop), runs every gate, and writes
verify.json with the verdict and exactly what was verified:

    source_hash  sha256 over every file that defines the design: parts,
                 assembly, spec, bought geometry and the approved renders,
                 and the same files of every project it links as a
                 sub-assembly (subassembly.py), down the tree
    engine_hash  sha256 over cad-agent's own source, because a change to a
                 rule changes what "passes" means; read before the run and
                 again after it, so a verdict is never written for rules that
                 changed in between (a `git pull` mid-verify)
    git          the commit, the project's tree at that commit, and whether
                 the design had uncommitted changes; for each linked project
                 too, under `children`
    process      whether it ran in a fresh process: a warm-worker fork or a
                 new interpreter, never a process that already ran commands
    tree         only with sub-assemblies: each one linked, and the hash of
                 every project below this one

A project with sub-assemblies is verified as the whole: every part of every project in the tree is rebuilt from
source in this one process and every gate of every project is run (their rows are named <project>:<check>), so
PASS stands for each project passing `cad verify` on these files. A child's own verify.json and checks.json are
never read; they are claims, and this is the evidence. The projects are found by reading assembly.py (nothing
is run to hash them), and the run checks that it loaded no project that reading missed: if it did, the verdict
cannot be PASS, because the hashes would not cover what was judged.

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
from .subassembly import tree_dirs, tree_projects

PKG = Path(__file__).resolve().parent
DESIGN = ("parts/*.py", "assembly.py", "spec.toml", "placements.toml", "bought/*",
          "baseline/*.png")
OUTPUTS = ("checks.json", "verify.json")      # written by runs, never inputs


def design_files(pdir: Path) -> list[Path]:
    files = set()
    for pattern in DESIGN:
        files.update(p for p in pdir.glob(pattern) if p.is_file())
    return sorted(files)


def _feed(h, files: list[Path], base: Path, label: str = "") -> None:
    for p in files:
        h.update((label + p.relative_to(base).as_posix()).encode() + b"\0")
        h.update(hashlib.sha256(p.read_bytes()).digest())


def _own_hash(pdir: Path) -> tuple[str, int]:
    """The hash of one project's own inputs, without the projects it links."""
    h = hashlib.sha256()
    files = design_files(pdir) if pdir.is_dir() else []
    _feed(h, files, pdir)
    return h.hexdigest(), len(files)


def source_hash(pdir: Path) -> tuple[str, int]:
    """Hash of the design as it is on disk: path and content of every input.

    A project that links sub-assemblies (subassembly.py) is made of their files too, and of their own, down the
    tree: each project's inputs are hashed after this one's, under its name, so an edit to a child changes the
    parent's hash and a verdict about the parent stops standing. The projects are found by reading assembly.py's
    source (subassembly.tree_projects), and `run` below checks that the run loaded no project this missed. A
    project that links nothing hashes as it always did.
    """
    h = hashlib.sha256()
    files = design_files(pdir)
    _feed(h, files, pdir)
    count = len(files)
    for name, cdir in tree_dirs(pdir):
        kept = design_files(cdir) if cdir.is_dir() else []
        h.update(b"project\0" + name.encode() + b"\0")
        _feed(h, kept, cdir, label=f"{name}/")
        count += len(kept)
    return h.hexdigest(), count


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

    A project that links sub-assemblies answers for them as well: `children` holds the same record for each
    project below it, and the design is dirty if any of them is. A child that is in no git repository while this
    one is cannot be said to be committed, so it counts as uncommitted and the entry says so. Without children
    the record is what it always was.
    """
    info = _git_info(pdir)
    kids = tree_dirs(pdir) if info is not None else []
    if kids:
        info["children"] = {}
        for name, cdir in kids:
            sub = _git_info(cdir) if cdir.is_dir() else None
            info["children"][name] = sub
            if sub is None:
                why = f"{name}: " + ("not in a git repository" if cdir.is_dir() else "no such project")
                info["uncommitted"] = (info["uncommitted"] + [why])[:20]
                info["dirty"] = True
            elif sub["dirty"]:
                info["uncommitted"] = (info["uncommitted"] + [f"{name}/{p}" for p in sub["uncommitted"]])[:20]
                info["dirty"] = True
    return info


def _git_info(pdir: Path) -> dict | None:
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
    tree = payload.get("tree")
    loaded = set(tree["projects"]) if tree else set()
    unhashed = sorted(loaded - set(tree_projects(pdir)[0]))
    if unhashed:
        if verdict == "PASS":
            verdict = "UNCHECKED"
        notes.append(f"the run loaded {', '.join(unhashed)}, which assembly.py's source does not name as a plain "
                     "string, so the hashes do not cover it: write each SUBASSEMBLIES project as a literal")
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
    if tree:
        record["tree"] = {"subassemblies": tree["subassemblies"],
                          "projects": {name: dict(zip(("source_hash", "design_files"), _own_hash(cdir)))
                                       for name, cdir in tree_dirs(pdir)}}
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

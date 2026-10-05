"""The eval set: design tasks the verifier scores, so "better" is a number.

A task is a folder under evals/ (or $CAD_EVALS, or --evals DIR):

    brief.md     what the agent is given: every requirement the spec checks, in words and numbers
    spec.toml    the hidden spec, the grader. The agent writes its own and never sees this one
    given/       files laid into the agent's project at the start and again before grading, in
                 the project's own layout (given/bought/x.step -> projects/<task>/bought/x.step)
    reference/   a complete design that scores 100%, which is the proof the task can be solved

Scoring is `cad verify` and nothing else. `score` copies a design into a scratch project, drops
its outputs and approved renders, lays the given files and the hidden spec over it, and verifies
the copy in a fresh process. Whatever the agent did to its own spec.toml, to a given file or to
its own verdict gains nothing, because none of it survives the copy. Every row counts except the
three kinds that wait on a person approving a render (the edit hook skips the same ones), and
N/A is not held against a design. A score is passed rows over graded rows; PASS needs all of them.

This module imports no CAD kernel. The one place geometry happens is the verify subprocess, which
runs this package's own code, so a change to a rule moves the score it is meant to move.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

SKIP = ("drift/", "extent/", "visual/")                          # rows that wait on an approved render
DROP = ("checks.json", "verify.json", "out", ".cad", "baseline")  # outputs and approvals, never design
NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_-]{0,63}$")
SCORE_TIMEOUT_S = 900                                            # one verify, including a cold kernel


class EvalError(Exception):
    """A task, folder or command that cannot be used: bad arguments, not a bad design."""


@dataclass
class Task:
    name: str
    path: Path

    @property
    def brief(self) -> str:
        return (self.path / "brief.md").read_text()

    @property
    def title(self) -> str:
        for line in self.brief.splitlines():
            if line.strip():
                return line.strip().lstrip("#").strip()
        return ""

    @property
    def given(self) -> list[str]:
        base = self.path / "given"
        files = base.rglob("*") if base.is_dir() else []
        return sorted(p.relative_to(base).as_posix() for p in files if p.is_file())


def tasks_dir(arg: str | None = None) -> Path:
    """--evals DIR, else $CAD_EVALS, else evals/ next to the package."""
    raw = arg or os.environ.get("CAD_EVALS")
    return Path(raw).expanduser().resolve() if raw else Path(__file__).resolve().parent.parent / "evals"


def list_tasks(root: Path) -> list[Task]:
    if not root.is_dir():
        raise EvalError(f"no evals folder at {root} (--evals DIR, or CAD_EVALS)")
    return [Task(p.name, p) for p in sorted(root.iterdir()) if (p / "brief.md").is_file()]


def get_task(root: Path, name: str) -> Task:
    have = ", ".join(t.name for t in list_tasks(root)) or "none"
    if not NAME.fullmatch(name) or not (root / name / "brief.md").is_file():
        raise EvalError(f"no task {name!r} in {root} (tasks: {have})")
    if not (root / name / "spec.toml").is_file():
        raise EvalError(f"task {name!r} has no spec.toml, so there is nothing to grade with")
    return Task(name, root / name)


# ─── Scoring ─────────────────────────────────────────────────────────────────

def lay(task: Task, design: Path, project: Path) -> None:
    """Make the project that gets graded: the design, then the given files, then the hidden spec."""
    def ignore(src, names):
        drop = {"__pycache__", ".git"} & set(names)
        return drop | (set(DROP) & set(names) if Path(src) == design else set())
    shutil.copytree(design, project, ignore=ignore, ignore_dangling_symlinks=True)
    given = task.path / "given"
    if given.is_dir():
        shutil.copytree(given, project, dirs_exist_ok=True)
    shutil.copyfile(task.path / "spec.toml", project / "spec.toml")


def _last_json(text: str) -> dict | None:
    for line in reversed(text.splitlines()):
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                return None
    return None


def run_verify(projects: Path, name: str, timeout: float = SCORE_TIMEOUT_S) -> dict:
    """`cad verify` in a fresh process: its record with every row, or {"error": ...}.

    It goes through the warm worker like any other call, with PYTHONPATH pointing at this
    package so the grader and the caller are the same code.
    """
    env = {k: v for k, v in os.environ.items() if k != "CAD_PROJECTS"}
    here = str(Path(__file__).resolve().parent.parent)
    env["PYTHONPATH"] = os.pathsep.join([here, env["PYTHONPATH"]] if env.get("PYTHONPATH") else [here])
    cmd = [sys.executable, "-m", "cad_agent.warm", "--projects", str(projects), "--json",
           "verify", name, "--all"]
    try:
        p = subprocess.run(cmd, cwd=projects, env=env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"error": f"cad verify did not finish in {timeout:g} s"}
    out = _last_json(p.stdout)
    if out is None or out.get("exit") not in (0, 1, 2):
        why = ((out or {}).get("data") or {}).get("error") or p.stderr.strip()[-400:] or "no output"
        return {"error": f"cad verify did not finish (exit {p.returncode}): {why}"}
    return out["data"]


def _failed_parts(project: Path) -> dict:
    try:
        parts = json.loads((project / "checks.json").read_text()).get("parts", {})
    except (OSError, ValueError):
        return {}
    return {n: p.get("error", "did not build") for n, p in parts.items() if p.get("state") == "FAIL"}


def grade(rec: dict, failed: dict | None = None) -> dict:
    """What a verify record is worth: the rows that count, and the verdict they add up to.

    A part that did not build is a graded failure of its own, since it leaves no rows to fail.
    A record from a process that was not fresh, or about a design that changed while it was
    verified, cannot be a PASS however green its rows are.
    """
    if "error" in rec:
        row = {"subject": "verify", "check": "verify", "rule": "verify", "state": "FAIL",
               "measured": rec["error"], "limit": "a finished verdict"}
        return {"verdict": "FAIL", "score": 0.0, "graded": 1, "passed": 0, "skipped": 0, "na": 0,
                "notes": [], "rows": [row]}
    graded, skipped, na = [], 0, 0
    for r in rec.get("rows", []):
        if r["rule"].startswith(SKIP):
            skipped += 1
        elif r["state"] == "N/A":
            na += 1
        else:
            graded.append({k: r.get(k, "") for k in ("subject", "check", "rule", "state", "measured", "limit")})
    n_failed = rec.get("summary", {}).get("parts_failed", 0)
    failed = dict(failed or {})
    if n_failed and not failed:
        failed = {"parts": f"{n_failed} part(s) did not build"}
    for name, error in failed.items():
        graded.append({"subject": name, "check": "build", "rule": "build", "state": "FAIL",
                       "measured": error, "limit": "builds"})
    notes = []
    if not rec.get("process", {}).get("fresh"):
        notes.append("verify did not run in a fresh process")
    if any("changed while" in n for n in rec.get("notes", [])):
        notes.append("the design changed while it was being verified")
    states = {r["state"] for r in graded}
    verdict = ("FAIL" if "FAIL" in states else
               "UNCHECKED" if "UNCHECKED" in states or notes or not graded else "PASS")
    passed = sum(r["state"] == "PASS" for r in graded)
    return {"verdict": verdict, "score": round(passed / len(graded), 4) if graded else 0.0,
            "graded": len(graded), "passed": passed, "skipped": skipped, "na": na,
            "notes": notes, "rows": graded}


def score(task: Task, design: Path, keep: bool = False, show_all: bool = False,
          timeout: float = SCORE_TIMEOUT_S) -> dict:
    """Grade one design against one task. `rows` are the graded rows that did not pass,
    or all of them with show_all."""
    design = Path(design).expanduser().resolve()
    if not design.is_dir():
        raise EvalError(f"no design folder at {design}")
    t0 = time.monotonic()
    work = Path(tempfile.mkdtemp(prefix=f"cad-eval-{task.name}-")).resolve()
    try:
        project = work / "projects" / task.name
        try:
            lay(task, design, project)
        except (OSError, shutil.Error) as e:
            raise EvalError(f"cannot copy the design from {design}: {e}") from None
        rec = run_verify(project.parent, task.name, timeout)
        g = grade(rec, _failed_parts(project))
    finally:
        if not keep:
            shutil.rmtree(work, ignore_errors=True)
    rows = g["rows"] if show_all else [r for r in g["rows"] if r["state"] != "PASS"]
    result = {"task": task.name, "verdict": g["verdict"], "score": g["score"], "graded": g["graded"],
              "passed": g["passed"], "skipped": g["skipped"], "na": g["na"], "rows": rows,
              "notes": g["notes"], "seconds": round(time.monotonic() - t0, 1),
              "verify_seconds": rec.get("seconds")}
    if keep:
        result["kept"] = str(work)
    return result


# ─── Running an agent ────────────────────────────────────────────────────────

def fill(command: str, **values) -> str:
    """Put {brief} {dir} {task} {root} into an agent command, each quoted for the shell."""
    for key, value in values.items():
        command = command.replace("{" + key + "}", shlex.quote(str(value)))
    return command


def _git(root: Path, *args: str) -> None:
    try:
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as e:
        raise EvalError(f"git {' '.join(args)} failed in {root}: {getattr(e, 'stderr', e)}") from None


def start(task: Task, work: Path) -> tuple[Path, Path]:
    """The agent's world: a git repo whose projects/<task> holds the given files and whose
    root holds BRIEF.md. Returns (repo root, project folder)."""
    root = work / "repo"
    project = root / "projects" / task.name
    given = task.path / "given"
    project.mkdir(parents=True)
    if given.is_dir():
        shutil.copytree(given, project, dirs_exist_ok=True)
    (root / "BRIEF.md").write_text(task.brief)
    (root / ".gitignore").write_text("projects/*/out/\nprojects/*/.cad/\nprojects/.cad/\n__pycache__/\n")
    _git(root, "init", "-q", "-b", "main")
    for key, value in (("user.name", "eval agent"), ("user.email", "eval@localhost"),
                       ("commit.gpgsign", "false")):
        _git(root, "config", key, value)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", f"eval {task.name}: the given files and the brief")
    return root, project


def run_task(task: Task, agent: str, timeout: float, keep: bool = False) -> dict:
    """One task, start to score: set up the repo, run the agent command in it, grade what it left."""
    work = Path(tempfile.mkdtemp(prefix=f"cad-eval-run-{task.name}-")).resolve()   # macOS /var is /private/var
    log = work / "agent.log"
    try:
        root, project = start(task, work)
        command = fill(agent, brief=root / "BRIEF.md", dir=project, task=task.name, root=root)
        env = dict(os.environ, CAD_PROJECTS=str(root / "projects"))
        print(f"{task.name}: running the agent (up to {timeout:g} s), output in {log}", file=sys.stderr)
        t0 = time.monotonic()
        timed_out = False
        with log.open("w") as out:
            proc = subprocess.Popen(command, shell=True, cwd=root, env=env, stdin=subprocess.DEVNULL,
                                    stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                proc.wait(timeout=timeout)
            except BaseException as e:               # out of time, or Ctrl-C: the agent does not outlive us
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait()
                if not isinstance(e, subprocess.TimeoutExpired):
                    raise
                timed_out = True
        agent_s = round(time.monotonic() - t0, 1)
        result = score(task, project, keep=keep)
        print(f"{task.name}: {result['verdict']} {result['score']:.1%}", file=sys.stderr)
        result.update(agent_exit=proc.returncode, agent_seconds=agent_s, timed_out=timed_out,
                      agent_tail=log.read_text(errors="replace")[-1500:])
        if keep:
            result["agent_dir"] = str(work)
        return result
    finally:
        if not keep:
            shutil.rmtree(work, ignore_errors=True)


def run(root: Path, agent: str, names: list[str], timeout: float, keep: bool = False,
        out: Path | None = None) -> dict:
    """Every named task (default: all), one after another, and a results file."""
    if not agent.strip():
        raise EvalError("--agent needs a command, e.g. --agent 'claude -p \"$(cat {brief})\" ...'")
    tasks = [get_task(root, n) for n in names] or list_tasks(root)
    if not tasks:
        raise EvalError(f"no tasks in {root}")
    started = datetime.now(timezone.utc)
    results = [run_task(t, agent, timeout, keep) for t in tasks]
    scores = [r["score"] for r in results]
    data = {"started_utc": started.strftime("%Y-%m-%dT%H:%M:%SZ"), "agent": agent,
            "timeout_s": timeout, "evals": str(root), "tasks": results,
            "summary": {"tasks": len(results), "pass": sum(r["verdict"] == "PASS" for r in results),
                        "mean_score": round(sum(scores) / len(scores), 4)}}
    path = out or root / "results" / f"{started.strftime('%Y%m%dT%H%M%SZ')}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
    data["file"] = str(path)
    return data

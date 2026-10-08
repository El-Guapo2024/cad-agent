"""Run only the tests that can see what changed: the quick check between full runs.

The full suite takes 7 to 20 minutes on a laptop, and GitHub CI runs all of it on every push.
So while fixing, run the test files that can notice the change, and leave the rest to CI:

    .venv/bin/python tests/affected.py            # run them (extra args go to pytest)
    .venv/bin/python tests/affected.py --list     # only say which
    .venv/bin/python tests/affected.py origin/main

It compares the work tree with BASE (default main) and picks every changed test file, plus every
test file that names a changed module. Including too much is the safe side; CI catches the rest.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TESTS = REPO / "tests"
# Changed paths that no module name points at, and the tests that cover them.
COVERS = {
    "evals/": ["test_eval.py"],
    ".claude/hooks/": ["test_hooks.py"],
    "plugin/": ["test_hooks.py"],
    "bin/": ["test_cli.py", "test_warm.py"],
    "cad_agent/workbench/": ["test_workbench.py"],
}
EVERYTHING = ("tests/conftest.py", "pyproject.toml")    # these reach every test


def changed(base: str) -> list[str]:
    """Paths that differ from `base`: committed since, uncommitted, and new."""
    def git(*args):
        r = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True)
        return r.stdout.splitlines()
    return sorted(set(git("diff", "--name-only", f"{base}...HEAD") + git("diff", "--name-only", "HEAD")
                      + git("ls-files", "--others", "--exclude-standard")))


def affected(paths: list[str]) -> list[str] | None:
    """Test files to run for `paths`, or None when every test is affected."""
    if any(p in EVERYTHING for p in paths):
        return None
    tests = {t.name: t.read_text() for t in sorted(TESTS.glob("test_*.py"))}
    out = set()
    for path in paths:
        p = Path(path)
        if path.startswith("tests/") and p.name in tests:
            out.add(p.name)
        for prefix, names in COVERS.items():
            if path.startswith(prefix):
                out.update(names)
        if path.startswith("cad_agent/") and p.suffix == ".py":
            mod = p.parent.name if p.stem == "__init__" else p.stem
            word = re.compile(rf"\b{re.escape(mod)}\b")
            out.update(name for name, text in tests.items() if word.search(text))
    return sorted(n for n in out if n in tests)


def main(argv: list[str]) -> int:
    args = argv[1:]
    listing = "--list" in args
    args = [a for a in args if a != "--list"]
    base = args.pop(0) if args and not args[0].startswith("-") else "main"
    names = affected(changed(base))
    files = ["tests"] if names is None else [f"tests/{n}" for n in names]
    if listing:
        print(" ".join(files))
        return 0
    if not files:
        print(f"no test file sees the changes since {base}", file=sys.stderr)
        return 0
    return subprocess.run([sys.executable, "-m", "pytest", "-q", *files, *args], cwd=REPO).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv))

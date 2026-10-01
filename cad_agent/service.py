"""cad service: the workbench as a login service (macOS launchd).

`cad service install [DIR ...]` writes ~/Library/LaunchAgents/com.cad-agent.workbench.plist
and loads it. From then on `cad serve --keep-warm` starts at login and restarts if
it crashes. It keeps the CAD kernel loaded, so opening the workbench launches
nothing and never waits on the kernel import. The cost is the memory of a
loaded kernel, about 400 MB, held all the time. `cad service uninstall` removes
it, and `cad service status` says whether it is up and answering.

It is a login item, so installing it is the user's decision; nothing installs
it on its own.
"""
from __future__ import annotations

import os
import plistlib
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

LABEL = "com.cad-agent.workbench"
PKG = Path(__file__).resolve().parent


def plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def log_path() -> Path:
    d = Path(os.environ.get("CAD_WARM_DIR") or Path.home() / ".cache" / "cad-agent")
    return d / "workbench.log"


def definition(roots: list[Path], port: int = 8733) -> dict:
    """The launchd job. The server and the agent's `cad` calls must find the
    same warm worker, so CAD_WARM_DIR is carried over when it is set."""
    env = {k: os.environ[k] for k in ("CAD_WARM_DIR",) if k in os.environ}
    job = {
        "Label": LABEL,
        "ProgramArguments": [sys.executable, "-m", "cad_agent.warm", "serve", "--keep-warm",
                             "--port", str(port), *[str(r) for r in roots]],
        "WorkingDirectory": str(PKG.parent),
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},     # restart after a crash, not after a stop
        "ThrottleInterval": 30,
        # You click and wait on it, and the warm worker it starts inherits this:
        # "Background" throttled every command about eightfold.
        "ProcessType": "Interactive",
        "StandardOutPath": str(log_path()),
        "StandardErrorPath": str(log_path()),
    }
    if env:
        job["EnvironmentVariables"] = env
    return job


def _launchctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


def _domain() -> str:
    return f"gui/{os.getuid()}"


def _need_mac() -> None:
    if sys.platform != "darwin":
        raise RuntimeError("cad service uses macOS launchd; elsewhere, run `cad serve` "
                           "under your own service manager")


def _port_of_installed(default: int = 8733) -> int:
    try:
        args = plistlib.loads(plist_path().read_bytes())["ProgramArguments"]
        return int(args[args.index("--port") + 1])
    except (OSError, KeyError, ValueError, IndexError, plistlib.InvalidFileException):
        return default


def _answering(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3) as r:
            return r.status == 200
    except OSError:
        return False


def status(port: int | None = None) -> dict:
    _need_mac()
    port = port or _port_of_installed()
    r = _launchctl("print", f"{_domain()}/{LABEL}")
    pid = re.search(r"^\s*pid = (\d+)", r.stdout, re.M)
    state = re.search(r"^\s*state = (\S+)", r.stdout, re.M)
    return {"installed": plist_path().exists(), "loaded": r.returncode == 0,
            "state": state.group(1) if state else None,
            "pid": int(pid.group(1)) if pid else None,
            "url": f"http://127.0.0.1:{port}", "answering": _answering(port),
            "plist": str(plist_path()), "log": str(log_path())}


def _unload() -> None:
    _launchctl("bootout", f"{_domain()}/{LABEL}")
    for _ in range(50):                            # bootout finishes asynchronously
        if _launchctl("print", f"{_domain()}/{LABEL}").returncode != 0:
            return
        time.sleep(0.1)


def install(roots: list[Path], port: int = 8733, wait_s: float = 15) -> dict:
    _need_mac()
    path = plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    log_path().parent.mkdir(parents=True, exist_ok=True)
    _unload()                                      # replacing one is an update
    with path.open("wb") as f:
        plistlib.dump(definition(roots, port), f)
    r = _launchctl("bootstrap", _domain(), str(path))
    if r.returncode != 0:
        raise RuntimeError(f"launchctl bootstrap failed: {(r.stderr or r.stdout).strip()}")
    deadline = time.time() + wait_s
    while time.time() < deadline and not _answering(port):
        time.sleep(0.25)
    return status(port)


def uninstall() -> dict:
    _need_mac()
    existed = plist_path().exists()
    _unload()
    plist_path().unlink(missing_ok=True)
    return {"removed": existed, "plist": str(plist_path())}

"""Warm worker: keeps the CAD kernel imported so `cad` answers in about a second.

Importing build123d costs about 35 s on this machine: 10 s for OCP, the OCCT
bindings, and 20 s for scikit-learn, scipy and fonts that build123d imports
eagerly. A CLI that pays that on every call is unusable in an agent loop; the
MCP server hid it by staying alive.

So the first `cad` call starts one background process that imports the
third-party stack once and waits on a Unix socket. Each later call sends its
argv plus its own stdin, stdout and stderr file descriptors. The worker forks;
the child adopts those descriptors, moves to the caller's directory and runs
the command, writing straight to the caller's terminal. The parent sends the
child's exit status back, and the client exits with it.

What this keeps:
- Every command runs in a fresh child forked from a parent that has never run
  project code, so nothing leaks from one command into the next.
- cad_agent is imported fresh in every child, so an edit to a rule or a part
  takes effect on the next call. Only third-party modules are preloaded;
  after upgrading one of those, run `cad warm stop`.
- The parent is single-threaded (one-thread BLAS) and never touches
  Objective-C, which is what makes fork safe on macOS. The Metal renderer
  loads in the child.
- It exits by itself after 30 idle minutes. CAD_WARM=0 skips it entirely.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import select
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

IDLE_S = 30 * 60
START_TIMEOUT_S = 240
PKG = Path(__file__).resolve().parent
PRELOAD = ("numpy", "build123d")
ENV_PASS = ("CAD_PROJECTS", "CAD_RENDER_BACKEND", "CAD_PREFS", "COLUMNS", "NO_COLOR", "TERM",
            "CAD_ACTOR")  # undo.actor()'s fallback for CAD_WARM=0; the
                          # workbench server passes cli.py's --actor flag
                          # instead (a warm-worker fork inherits the
                          # long-lived daemon's own environment, not a
                          # client's, so an env var set here would only take
                          # effect after the next time the daemon restarts)
COLD = {(), ("-h",), ("--help",)}           # nothing to import: answer without a worker
NO_KERNEL = {"serve", "service"}   # kernel-free: never hold a worker fork


def _command(argv: list[str]) -> str | None:
    """The subcommand, skipping the global flags that may come before it."""
    i = 0
    while i < len(argv):
        if argv[i] == "--projects":
            i += 2
        elif argv[i] == "--json" or argv[i].startswith("--projects="):
            i += 1
        else:
            return argv[i]
    return None


def _dir() -> Path:
    d = Path(os.environ.get("CAD_WARM_DIR") or Path.home() / ".cache" / "cad-agent")
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    return d


def sock_path() -> Path:
    """One worker per checkout and worker directory.

    macOS caps a Unix socket path at 104 bytes, and a long home or temp
    directory blows through that, so a long path moves to a short private
    directory under /tmp. The lock and log sit next to the socket.
    """
    d = _dir()
    key = hashlib.sha1(f"{PKG}|{d}".encode()).hexdigest()[:10]
    p = d / f"warm-{key}.sock"
    if len(str(p)) > 100:
        short = Path("/tmp") / f"cad-agent-{os.getuid()}"
        short.mkdir(mode=0o700, exist_ok=True)
        p = short / f"warm-{key}.sock"
    return p


# ─── Worker ──────────────────────────────────────────────────────────────────

def _reply(conn: socket.socket, payload: dict) -> None:
    try:
        conn.sendall((json.dumps(payload) + "\n").encode())
    except OSError:
        pass
    finally:
        conn.close()


def _child(req: dict, fds: list[int]) -> None:
    """Runs in the forked child. Never returns."""
    code = 4
    try:
        for i, fd in enumerate(fds[:3]):
            os.dup2(fd, i)
        for fd in fds:
            os.close(fd)
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        os.chdir(req.get("cwd") or "/")
        env = req.get("env") or {}
        for k in ENV_PASS:
            if k in env:
                os.environ[k] = env[k]
            else:
                os.environ.pop(k, None)
        sys.stdin = os.fdopen(0, "r", closefd=False)
        sys.stdout = os.fdopen(1, "w", closefd=False)
        sys.stderr = os.fdopen(2, "w", closefd=False)
        sys.argv = ["cad", *req["argv"]]
        os.environ["CAD_WARM_CHILD"] = "1"     # lets `cad verify` record how it ran
        from cad_agent import cli              # fresh from disk in every child
        code = cli.main(list(req["argv"]))
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
    except BaseException:
        import traceback
        traceback.print_exc()
        code = 4
    finally:
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.flush()
            except Exception:
                pass
    os._exit(code if isinstance(code, int) else 4)


def serve(path: Path) -> None:
    lock = open(path.with_suffix(".lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return                                 # another worker owns this checkout
    for var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
                "VECLIB_MAXIMUM_THREADS"):
        os.environ.setdefault(var, "1")        # keep the parent single-threaded for fork
    import warnings
    warnings.filterwarnings("ignore", message=".*fork.*", category=DeprecationWarning)

    t0 = time.time()
    for mod in PRELOAD:
        __import__(mod)
    preload_s = round(time.time() - t0, 1)

    path.unlink(missing_ok=True)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    old = os.umask(0o177)                      # socket readable by this user only
    try:
        srv.bind(str(path))
    finally:
        os.umask(old)
    srv.listen(16)
    print(f"warm worker {os.getpid()} ready in {preload_s} s at {path}", flush=True)

    running: dict[int, socket.socket] = {}     # child pid -> its client connection
    served, last, started = 0, time.time(), time.time()
    stop = False

    def _terminate(*_):
        raise KeyboardInterrupt                # SIGTERM: stop children, remove the socket

    signal.signal(signal.SIGTERM, _terminate)
    try:
        while not stop:
            while running:                     # reap finished children, report their codes
                try:
                    pid, status = os.waitpid(-1, os.WNOHANG)
                except ChildProcessError:
                    break
                if pid == 0:
                    break
                conn = running.pop(pid, None)
                if conn is not None:
                    _reply(conn, {"exit": os.waitstatus_to_exitcode(status)})
                last = time.time()
            if not running and time.time() - last > IDLE_S:
                break
            ready, _, _ = select.select([srv, *running.values()], [], [], 0.2)
            for s in ready:
                if s is not srv:               # a client hung up mid-command (Ctrl-C)
                    try:
                        gone = s.recv(1, socket.MSG_PEEK) == b""
                    except OSError:
                        gone = True
                    if gone:
                        for pid, c in list(running.items()):
                            if c is s:
                                try:
                                    os.kill(pid, signal.SIGTERM)
                                except ProcessLookupError:
                                    pass
                    continue
                conn, _ = srv.accept()
                try:
                    msg, fds, _, _ = socket.recv_fds(conn, 65536, 3)
                    req = json.loads(msg.decode() or "{}")
                except (OSError, ValueError):
                    conn.close()
                    continue
                if req.get("control") in ("status", "ping"):
                    if req["control"] == "ping":       # keep-alive from a long-lived client
                        last = time.time()
                    _reply(conn, {"exit": 0, "pid": os.getpid(), "up_s": int(time.time() - started),
                                  "served": served, "running": len(running),
                                  "preload_s": preload_s, "socket": str(path)})
                    continue
                if req.get("control") == "stop":
                    _reply(conn, {"exit": 0, "stopped": os.getpid()})
                    stop = True
                    break
                if len(fds) != 3 or "argv" not in req:
                    for fd in fds:
                        os.close(fd)
                    _reply(conn, {"exit": 3, "error": "bad request"})
                    continue
                pid = os.fork()
                if pid == 0:
                    srv.close()
                    conn.close()               # the parent reports the exit code, not the child
                    for c in running.values():
                        c.close()
                    _child(req, fds)
                for fd in fds:
                    os.close(fd)
                running[pid] = conn
                served += 1
                last = time.time()
    except KeyboardInterrupt:
        pass
    finally:
        for pid in running:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        srv.close()
        path.unlink(missing_ok=True)


# ─── Client ──────────────────────────────────────────────────────────────────

def _connect(path: Path) -> socket.socket | None:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.connect(str(path))
        return s
    except OSError:
        s.close()
        return None


def _start(path: Path) -> subprocess.Popen:
    log = path.with_suffix(".log")
    with open(log, "ab") as lf:
        return subprocess.Popen([sys.executable, "-m", "cad_agent.warm", "_serve", str(path)],
                                stdin=subprocess.DEVNULL, stdout=lf, stderr=lf,
                                cwd=str(PKG.parent), start_new_session=True)


def _log_tail(path: Path, n: int = 6) -> str:
    try:
        return "\n".join(path.with_suffix(".log").read_text().splitlines()[-n:])
    except OSError:
        return ""


def _connect_or_start(path: Path, quiet: bool = False) -> socket.socket | None:
    conn = _connect(path)
    if conn is not None:
        return conn
    if not quiet:
        print("cad: starting the warm worker; the first call imports the CAD kernel "
              "(about 35 s here), later calls take about a second", file=sys.stderr)
    proc = _start(path)
    deadline = time.time() + START_TIMEOUT_S
    while time.time() < deadline:
        time.sleep(0.25)
        conn = _connect(path)
        if conn is not None:
            return conn
        # Exit 0 means another worker holds the lock and may still be importing:
        # keep waiting for it. Anything else is a crash: say why and give up.
        if proc.poll() not in (None, 0):
            print(f"cad: the warm worker exited:\n{_log_tail(path)}", file=sys.stderr)
            return _connect(path)
    return None


def _read_reply(conn: socket.socket) -> dict:
    data = b""
    while True:
        chunk = conn.recv(4096)
        if not chunk:
            break
        data += chunk
    conn.close()
    try:
        return json.loads(data.decode().strip() or "{}")
    except ValueError:
        return {}


def _cold(argv: list[str]) -> int:
    from cad_agent import cli
    return cli.main(argv)


# ─── For long-lived callers ──────────────────────────────────────────────────
# The workbench server runs many commands. Starting a Python client for each
# one costs a process launch per click, so it talks to the socket itself.

def run_captured(argv: list[str], cwd: str | None = None,
                 timeout: float = 900) -> tuple[int, str, str] | None:
    """One command in a worker fork, output captured: (exit, stdout, stderr).
    None when no worker can be started (the caller runs it cold instead)."""
    conn = _connect_or_start(sock_path(), quiet=True)
    if conn is None:
        return None
    out_r, out_w = os.pipe()
    err_r, err_w = os.pipe()
    null = os.open(os.devnull, os.O_RDONLY)
    header = {"argv": list(argv), "cwd": cwd or os.getcwd(),
              "env": {k: os.environ[k] for k in ENV_PASS if k in os.environ}}
    try:
        socket.send_fds(conn, [json.dumps(header).encode()], [null, out_w, err_w])
    except OSError:
        for fd in (out_r, err_r):
            os.close(fd)
        conn.close()
        return None
    finally:
        for fd in (null, out_w, err_w):
            os.close(fd)
    chunks: dict[int, list[bytes]] = {out_r: [], err_r: []}
    pending = [out_r, err_r]
    deadline = time.time() + timeout
    while pending and time.time() < deadline:   # drain both, or a full pipe stalls the child
        ready, _, _ = select.select(pending, [], [], min(1.0, max(0.0, deadline - time.time())))
        for fd in ready:
            data = os.read(fd, 65536)
            if data:
                chunks[fd].append(data)
            else:
                pending.remove(fd)
                os.close(fd)
    out = b"".join(chunks[out_r]).decode(errors="replace")
    err = b"".join(chunks[err_r]).decode(errors="replace")
    if pending:                                 # timed out: hanging up stops the child
        for fd in pending:
            os.close(fd)
        conn.close()
        return 4, out, err + f"\ncad: timed out after {timeout:.0f} s"
    conn.settimeout(30)
    try:
        reply = _read_reply(conn)
    except OSError:
        reply = {}
    return int(reply.get("exit", 4)), out, err


def ping() -> dict | None:
    """Start the worker if it is not running, and reset its idle clock."""
    conn = _connect_or_start(sock_path(), quiet=True)
    if conn is None:
        return None
    try:
        conn.sendall(json.dumps({"control": "ping"}).encode())
        return _read_reply(conn)
    except OSError:
        return None


def _control(args: list[str]) -> int:
    action = args[0] if args else "status"
    path = sock_path()
    if action == "start":
        conn = _connect_or_start(path)
        if conn is None:
            print(f"cad warm: worker did not start; see {path.with_suffix('.log')}", file=sys.stderr)
            return 4
        conn.close()
        action = "status"
    if action not in ("status", "stop"):
        print("usage: cad warm [status|start|stop]", file=sys.stderr)
        return 3
    conn = _connect(path)
    if conn is None:
        print("cad warm: not running")
        return 0 if action == "stop" else 2
    conn.sendall(json.dumps({"control": action}).encode())
    reply = _read_reply(conn)
    if action == "stop":
        print(f"cad warm: stopped worker {reply.get('stopped')}")
    else:
        print(f"cad warm: worker {reply.get('pid')} up {reply.get('up_s')} s, "
              f"{reply.get('served')} commands served, kernel import took "
              f"{reply.get('preload_s')} s\n  socket {reply.get('socket')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["_serve"]:
        serve(Path(argv[1]))
        sys.stdout.flush()
        os._exit(0)                            # skip tearing down the kernel: seconds, for nothing
    if argv[:1] == ["warm"]:
        return _control(argv[1:])
    if (os.environ.get("CAD_WARM", "1") == "0" or tuple(argv) in COLD
            or _command(argv) in NO_KERNEL):
        return _cold(argv)
    conn = _connect_or_start(sock_path())
    if conn is None:
        print("cad: the warm worker did not start; running cold", file=sys.stderr)
        return _cold(argv)
    for stream in (sys.stdout, sys.stderr):
        stream.flush()
    header = {"argv": argv, "cwd": os.getcwd(),
              "env": {k: os.environ[k] for k in ENV_PASS if k in os.environ}}
    try:
        socket.send_fds(conn, [json.dumps(header).encode()], [0, 1, 2])
        reply = _read_reply(conn)
    except KeyboardInterrupt:
        conn.close()                           # the worker sees the hang-up and stops the child
        return 130
    if "exit" not in reply:
        print("cad: the warm worker dropped the command; `cad warm stop` and retry, "
              "or CAD_WARM=0 to run cold", file=sys.stderr)
        return 4
    return int(reply["exit"])


if __name__ == "__main__":
    sys.exit(main())

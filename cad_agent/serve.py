"""cad serve: the workbench, a local page with the live 3D view.

The page is a client of the CLI. It never builds geometry itself: every scene,
move, check and approval runs as a `cad` command through the warm worker, so
it lands in the activity log like anything the agent does, and the verdicts
are the gates' own. This process only serves files, runs those commands and
watches the project folders:

- a design file changes (the agent edited a part, or you moved one): the
  page hears it within half a second and fetches a fresh scene
- checks.json, verify.json or the activity log change: the page hears that too
- you drag a part: `cad place` writes placements.toml and reports what the
  part now hits, then a full `cad check` runs in the background

It binds to localhost, and every POST needs the X-CAD header, which a page
from another origin cannot send without a preflight this server never answers.
Nothing here imports the CAD kernel, so it starts instantly and stays small.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import macro
from . import state as st
from . import undo
from .gui import GuiBoard, GuiError, RETESSELLATE_PROPS, parse_prop_args
from .verify import DESIGN

PKG = Path(__file__).resolve().parent
STATIC = PKG / "workbench"
SCENE_FORMAT = "cad-scene/2"        # scene.FORMAT; an older scene.json is rebuilt
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".png": "image/png", ".svg": "image/svg+xml",
         ".json": "application/json"}


def _config_path() -> Path:
    d = Path(os.environ.get("CAD_WARM_DIR") or Path.home() / ".cache" / "cad-agent")
    return d / "workbench.json"


def saved_roots() -> list[Path]:
    try:
        return [Path(r) for r in json.loads(_config_path().read_text()).get("roots", [])]
    except (OSError, ValueError):
        return []


# ─── server discovery: several workbenches can run at once ─────────────────
#
# A login service on the real projects (port 8733) and a scratch one on a
# temp folder (tests, or another checkout) both answer at the same time, so
# `cad gui` cannot assume a fixed port. Each `cad serve` records itself here,
# one file per port; `cad gui` (gui_client.find_server) reads every file,
# drops the ones nothing answers for any more, and matches the rest by root
# or by asking /api/projects. CAD_RUNTIME_DIR moves this for tests, so they
# never touch the real machine's registry.

def runtime_dir() -> Path:
    return Path(os.environ.get("CAD_RUNTIME_DIR") or Path.home() / ".cad-agent")


def _registry_dir() -> Path:
    return runtime_dir() / "serve"


def _registry_path(port) -> Path:
    return _registry_dir() / f"{port}.json"


def write_registry(bench: "Bench") -> Path:
    """Record this running server: host, port, pid and the roots it serves,
    so `cad gui` elsewhere on the machine can find it."""
    rec = {"host": bench.host, "port": bench.port, "pid": os.getpid(),
           "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "roots": [str(r) for r in bench.roots]}
    path = _registry_path(bench.port)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rec, indent=2))
    tmp.replace(path)
    return path


def remove_registry(port) -> None:
    try:
        _registry_path(port).unlink(missing_ok=True)
    except OSError:
        pass


def list_registry() -> list[dict]:
    """Every server this machine has recorded, alive or not; callers check."""
    d = _registry_dir()
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob("*.json")):
        try:
            out.append(json.loads(p.read_text()))
        except (OSError, ValueError):
            continue
    return out


def _result(code: int, stdout: str, stderr: str) -> dict:
    lines = [ln for ln in stdout.strip().splitlines() if ln.startswith("{")]
    try:
        payload = json.loads(lines[-1]) if lines else {}
    except ValueError:
        payload = {}
    data = payload.get("data", {})
    if code and not data.get("error"):
        data = {**data, "error": (stderr.strip().splitlines() or ["cad failed"])[-1]}
    res = {"exit": code, "data": data, "stderr": stderr[-4000:]}
    if "text" in payload:
        res["text"] = payload["text"]
    return res


def cad_direct(root: Path, args: list[str], timeout: float = 900) -> dict:
    """Run one cad command in a fork of the warm worker, talking to its socket
    from this process: no Python client is launched per command."""
    from . import warm
    argv = ["--projects", str(root), "--json", *args]
    if os.environ.get("CAD_WARM", "1") != "0":
        r = warm.run_captured(argv, cwd=str(PKG.parent), timeout=timeout)
        if r is not None:
            return _result(*r)
    return cad_subprocess(root, args, timeout)


def cad_subprocess(root: Path, args: list[str], timeout: float = 900) -> dict:
    """The fallback: one cad process per command (CAD_WARM=0, or no worker)."""
    cmd = [sys.executable, "-m", "cad_agent.warm", "--projects", str(root), "--json", *args]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           cwd=str(PKG.parent))
    except subprocess.TimeoutExpired:
        return {"exit": 4, "data": {"error": f"cad {' '.join(args)} timed out"}, "stderr": ""}
    return _result(p.returncode, p.stdout, p.stderr)


class Bench:
    def __init__(self, roots, runner=None):
        self.roots: list[Path] = []
        for r in roots:
            self.add_root(Path(r), save=False)
        self.run = runner or cad_direct
        self.clients: list[queue.Queue] = []
        self.lock = threading.Lock()
        self.root_lock = threading.Lock()
        self.slug_locks: dict[str, threading.Lock] = {}
        self.busy: dict[str, set] = {}
        self.checking: set[str] = set()
        self.recheck: set[str] = set()
        self.sigs: dict = {}
        self.log_pos: dict = {}
        self.gui = GuiBoard()
        self.rescene_timers: dict[str, threading.Timer] = {}
        self.host: str | None = None    # set by run(), for write_registry()
        self.port: int | None = None

    # ── projects ─────────────────────────────────────────────────────────────
    def add_root(self, root: Path, save: bool = True) -> bool:
        root = root.expanduser().resolve()
        if not root.is_dir() or root in self.roots:
            return False
        self.roots.append(root)
        if save:
            path = _config_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            known = [str(r) for r in saved_roots()]
            if str(root) not in known:
                path.write_text(json.dumps({"roots": known + [str(root)]}, indent=2))
        return True

    def projects(self) -> dict[str, Path]:
        out: dict[str, Path] = {}
        for root in self.roots:
            try:
                kids = sorted(root.iterdir())
            except OSError:
                continue
            for p in kids:
                if p.is_dir() and not p.name.startswith(".") and (p / "parts").is_dir():
                    out.setdefault(p.name, root)
        return out

    def root_of(self, slug: str) -> Path:
        root = self.projects().get(slug or "")
        if root is None:
            raise KeyError(slug)
        return root

    def with_root(self, root: Path, fn):
        with self.root_lock:
            old, st.ROOT = st.ROOT, root
            try:
                return fn()
            finally:
                st.ROOT = old

    def status(self, slug: str) -> dict:
        from .verify import status
        try:
            return self.with_root(self.root_of(slug), lambda: status(slug))
        except Exception as e:
            return {"project": slug, "done": False, "verdict": None,
                    "reasons": [f"{type(e).__name__}: {e}"]}

    # ── events ───────────────────────────────────────────────────────────────
    def broadcast(self, event: dict) -> int:
        """Send to every open /api/events connection; returns how many got it."""
        msg = json.dumps(event, default=str)
        with self.lock:
            clients = list(self.clients)
            for q in clients:
                q.put(msg)
        return len(clients)

    def set_busy(self, slug: str, what: str, on: bool) -> None:
        with self.lock:
            s = self.busy.setdefault(slug, set())
            (s.add if on else s.discard)(what)
        self.broadcast({"type": "busy", "slug": slug, "what": what, "on": on,
                        "busy": sorted(self.busy.get(slug, ()))})

    def cad(self, slug: str, what: str, args: list[str]) -> dict:
        """Run one cad command for the page: always `--actor ui` (cli.py's
        hidden flag), since everything this bench runs is on a page's
        behalf. An env var here would not do it — a command may run in a
        warm-worker fork, which inherits the *daemon's* environment from
        whenever it started, not this process's (see undo.record's
        docstring); an argv flag is parsed fresh by cli.py on every call."""
        root = self.root_of(slug)
        self.set_busy(slug, what, True)
        try:
            return self.run(root, ["--actor", "ui", *args])
        finally:
            self.set_busy(slug, what, False)

    # ── gui: the shared selection, visibility and view (FreeCADGui's job) ──────
    def gui_get(self, slug: str) -> dict:
        root = self.root_of(slug)
        return self.gui.get(slug, root / slug, len(self.clients))

    def gui_post(self, slug: str, patch: dict) -> dict:
        root = self.root_of(slug)
        self.gui.post(slug, root / slug, patch)
        vp = patch.get("view_props")
        if isinstance(vp, dict) and any(isinstance(p, dict) and RETESSELLATE_PROPS & p.keys()
                                        for p in vp.values()):
            self.rescene_debounced(slug)
        return self.gui_get(slug)

    def gui_do(self, slug: str, cmd: str, args: list[str], props: dict | None = None) -> dict:
        root = self.root_of(slug)
        pdir = root / slug
        summary, files = self.gui.do(slug, pdir, cmd, args, props)
        if cmd == "set" and props and RETESSELLATE_PROPS & props.keys():
            self.rescene_debounced(slug)   # `cad gui set`, POST /api/gui/do, and a macro `set` line
        event = {"type": "gui", "slug": slug, "cmd": cmd, "args": args}
        if props is not None:
            event["props"] = props
        n = self.broadcast(event)
        from .cli import log_activity         # lazy: cli imports serve lazily too
        log_activity(pdir, f"gui.{cmd}", args, 0, summary, files)
        return {"ok": True, "clients": n}

    # ── macros: replay a saved sequence of cad/gui lines ────────────────────────
    def _macro_gui_line(self, argv: list[str]) -> dict:
        """One `cad gui ...` macro line, dispatched straight to this bench's
        GuiBoard — the same path POST /api/gui/do uses — instead of through a
        cad subprocess: that state only lives in this process's memory, and a
        subprocess has nothing to mutate. Every gui line spells out its own
        project slug (`gui <action> <slug> ...`), same as any other cad line."""
        if len(argv) < 3:
            return {"exit": 3, "text": f"cad {' '.join(argv)}: gui needs an action and a project"}
        action, slug, rest = argv[1], argv[2], argv[3:]
        try:
            if action == "state":
                self.gui_get(slug)
                return {"exit": 0, "text": f"{slug}: gui state read"}
            if action == "say":
                args, props = ([" ".join(rest)] if rest else []), None
            elif action == "set":
                if not rest:
                    raise GuiError("set needs a body name")
                args, props = [rest[0]], (parse_prop_args(rest[1:]) or None)
            else:
                args, props = rest, None     # select/clear/show/hide/view/fit validate themselves
            r = self.gui_do(slug, action, args, props)
            return {"exit": 0, "text": f"{slug}: gui {action} ({r['clients']} client(s) watching)"}
        except KeyError:
            return {"exit": 3, "text": f"no project {slug!r}"}
        except GuiError as e:
            return {"exit": 3, "text": str(e)}

    def macro_run(self, slug: str, name: str, lines: list[str]) -> dict:
        """Replay a macro's lines: `gui` ones through `_macro_gui_line`, the
        rest through the same runner /api/cad uses. `slug`, if given, picks
        both the project root to run under and the activity log to write to;
        with none given, the bench's first root stands in for `--projects`."""
        if slug:
            root = self.root_of(slug)        # KeyError -> caller maps to 400
        elif self.roots:
            root = self.roots[0]
        else:
            raise KeyError(slug)

        def exec_line(argv):
            if argv and argv[0] == "gui":
                return self._macro_gui_line(argv)
            what = argv[0] if argv else "macro-line"
            # self.cad() already adds --actor ui; the no-slug fallback below
            # bypasses it (no project to call bench.cad()'s set_busy for), so
            # it says so itself — every line here is a `cad` command run for
            # the UI either way.
            r = (self.cad(slug, what, ["--with-text", *argv]) if slug
                 else self.run(root, ["--actor", "ui", "--with-text", *argv]))
            text = r.get("text") or (r.get("data") or {}).get("error") or ""
            return {"exit": r["exit"], "text": text}

        result = macro.run_lines(lines, exec_line)
        from .cli import log_activity         # lazy: cli imports serve lazily too
        log_activity(root / slug if slug else root, "macro.run", [name], result["exit"],
                     f"{name}: ran {len(result['ran'])} line(s)")
        return result

    # ── background work ──────────────────────────────────────────────────────
    def schedule(self, slug: str, kind: str = "check") -> None:
        """Run `cad check` (or verify) in the background; a request that arrives
        while one runs is folded into a single re-run afterwards."""
        key = f"{kind}:{slug}"
        with self.lock:
            if key in self.checking:
                self.recheck.add(key)
                return
            self.checking.add(key)

        def work():
            while True:
                r = self.cad(slug, kind, [kind, slug])
                self.broadcast({"type": kind + "ed", "slug": slug, "exit": r["exit"],
                                "error": r["data"].get("error")})
                with self.lock:
                    if key in self.recheck:
                        self.recheck.discard(key)
                        continue
                    self.checking.discard(key)
                    return
        threading.Thread(target=work, daemon=True).start()

    def rescene_debounced(self, slug: str, delay: float = 0.4) -> None:
        """A body's Deviation or AngularDeflection changed. FreeCAD would
        re-tessellate it right away (ViewProviderPartExt::onChanged ->
        updateVisual()), but a slider drag fires many of these a second, so wait
        out a quiet period, then rebuild the whole scene once and tell the page
        with the same event `scan()` sends when scene.json changes on its own —
        the hash-based staleness check in `scene()` would otherwise never
        notice, since out/gui.json (view_props) is never part of the design
        hash (see gui.py's module docstring)."""
        def fire():
            with self.lock:
                # only clear our own slot: a new call may have already raced in
                # and replaced it with a fresh (still pending) timer of its own
                if self.rescene_timers.get(slug) is timer:
                    del self.rescene_timers[slug]
            r = self.cad(slug, "scene", ["scene", slug])
            if r["exit"] == 0:
                self.broadcast({"type": "scene", "slug": slug})
        with self.lock:
            old = self.rescene_timers.get(slug)
            if old is not None:
                old.cancel()
            timer = threading.Timer(delay, fire)
            timer.daemon = True
            self.rescene_timers[slug] = timer
            timer.start()

    def warm_up(self) -> None:
        """Start the warm worker now, so the first scene takes seconds, not half a minute."""
        roots = self.roots or [st.ROOT]
        try:
            self.run(roots[0], ["--version"])
        except Exception:
            pass

    def keep_warm(self, every_s: float = 300) -> None:
        """For the login service: keep the kernel loaded while the workbench is
        up, restarting it if something stopped it. One ping per interval."""
        from . import warm
        while True:
            try:
                warm.ping()
            except Exception:
                pass
            time.sleep(every_s)

    def scene(self, slug: str) -> tuple[int, bytes]:
        from .verify import source_hash
        root = self.root_of(slug)
        pdir = root / slug
        path = pdir / "out" / "scene.json"
        lock = self.slug_locks.setdefault(slug, threading.Lock())
        with lock:
            fresh = False
            if path.exists():
                try:
                    rec = json.loads(path.read_text())
                    fresh = (rec.get("format") == SCENE_FORMAT
                             and rec.get("source_hash") == source_hash(pdir)[0])
                except ValueError:
                    fresh = False
            if not fresh:
                r = self.cad(slug, "scene", ["scene", slug])
                if r["exit"] != 0:
                    return 422, json.dumps({"error": r["data"].get("error") or r["stderr"]
                                            or "scene failed"}).encode()
            return 200, path.read_bytes()

    # ── watching ─────────────────────────────────────────────────────────────
    def _design_sig(self, pdir: Path):
        sig = []
        for pattern in DESIGN:
            for p in sorted(pdir.glob(pattern)):
                try:
                    s = p.stat()
                    sig.append((p.name, s.st_mtime_ns, s.st_size))
                except OSError:
                    pass
        return tuple(sig)

    @staticmethod
    def _mtime(p: Path):
        try:
            return p.stat().st_mtime_ns
        except OSError:
            return None

    def scan(self, announce: bool = True) -> None:
        for slug, root in self.projects().items():
            pdir = root / slug
            now = {"design": self._design_sig(pdir),
                   "checks": self._mtime(pdir / "checks.json"),
                   "verify": self._mtime(pdir / "verify.json"),
                   "scene": self._mtime(pdir / "out" / "scene.json"),
                   "history": self._mtime(pdir / ".cad" / "undo.json")}
            for what, sig in now.items():
                key = (slug, what)
                if key in self.sigs and self.sigs[key] != sig and announce:
                    self.broadcast({"type": what, "slug": slug})
                self.sigs[key] = sig
            log = pdir / ".cad" / "log.jsonl"
            try:
                size = log.stat().st_size
            except OSError:
                continue
            pos = self.log_pos.get(slug)
            if pos is None or size < pos:
                self.log_pos[slug] = size
                continue
            if size > pos:
                with log.open("rb") as f:
                    f.seek(pos)
                    chunk = f.read(size - pos)
                end = chunk.rfind(b"\n") + 1
                self.log_pos[slug] = pos + end
                entries = []
                for line in chunk[:end].splitlines():
                    try:
                        entries.append(json.loads(line))
                    except ValueError:
                        pass
                if entries and announce:
                    self.broadcast({"type": "log", "slug": slug, "entries": entries})

    def watch(self) -> None:
        self.scan(announce=False)
        while True:
            time.sleep(0.5)
            try:
                self.scan()
            except Exception:
                pass

    def log_tail(self, slug: str, limit: int = 200) -> list[dict]:
        log = self.root_of(slug) / slug / ".cad" / "log.jsonl"
        if not log.exists():
            return []
        out = []
        for line in log.read_text().splitlines()[-limit:]:
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
        return out


def make_handler(bench: Bench):
    class Handler(BaseHTTPRequestHandler):
        server_version = "cad-workbench"

        def log_message(self, *args):
            pass

        # ── plumbing ─────────────────────────────────────────────────────────
        def _send(self, code: int, body: bytes, ctype: str = "application/json", headers: dict | None = None) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code: int = 200) -> None:
            self._send(code, json.dumps(obj, default=str).encode())

        def _query(self) -> dict:
            return {k: v[-1] for k, v in parse_qs(urlparse(self.path).query).items()}

        def _local(self) -> bool:
            host = (self.headers.get("Host") or "").split(":")[0]
            return host in ("127.0.0.1", "localhost", "[::1]", "::1")

        # ── GET ──────────────────────────────────────────────────────────────
        def do_GET(self):
            if not self._local():
                return self._json({"error": "localhost only"}, 403)
            path = urlparse(self.path).path
            q = self._query()
            try:
                if path == "/api/events":
                    return self._events()
                if path == "/api/projects":
                    items = []
                    for slug, root in bench.projects().items():
                        s = bench.status(slug)
                        items.append({"slug": slug, "root": str(root),
                                      "assembly": (root / slug / "assembly.py").exists(),
                                      "verdict": s.get("verdict"), "done": s.get("done"),
                                      **_file_card(root / slug)})
                    return self._json({"projects": items, "roots": [str(r) for r in bench.roots]})
                if path == "/api/scene":
                    code, body = bench.scene(q.get("slug", ""))
                    return self._send(code, body)
                if path == "/api/checks":
                    p = bench.root_of(q.get("slug", "")) / q["slug"] / "checks.json"
                    return self._send(200, p.read_bytes() if p.exists() else b"{}")
                if path == "/api/status":
                    return self._json(bench.status(q.get("slug", "")))
                if path == "/api/log":
                    return self._json({"entries": bench.log_tail(q.get("slug", ""),
                                                                 int(q.get("limit", 200)))})
                if path == "/api/cache":
                    from . import appcache
                    total = appcache.size()
                    # ?startup=1: the page's start-up check (ApplicationCache::periodicCheckOfSize).
                    due = appcache.periodic_check_due() if q.get("startup") else False
                    return self._json({"dir": str(appcache.directory()), "bytes": total, "due": due,
                                       "text": appcache.to_string(total), "limit": appcache.limit_bytes(),
                                       "limitText": appcache.to_string(appcache.limit_bytes())})
                if path == "/api/prefs":
                    from . import userprefs
                    return self._json({"prefs": userprefs.load()})
                if path == "/api/history":
                    slug = q.get("slug", "")
                    pdir = bench.root_of(slug) / slug
                    data = undo.load(pdir)

                    def rows(stack):
                        return [{"id": e["id"], "name": e["name"], "by": e["by"], "t": e["t"]}
                                for e in reversed(stack)]
                    return self._json({"undo": rows(data["undo"]), "redo": rows(data["redo"])})
                if path == "/api/gui":
                    return self._json(bench.gui_get(q.get("slug", "")))
                if path == "/api/file":
                    return self._file(q.get("slug", ""), q.get("path", ""))
                if path == "/api/macros":
                    return self._json({"dir": str(macro.macro_dir()), "macros": macro.list_macros()})
                if path == "/api/macro":
                    name = q.get("name", "")
                    return self._json({"name": name, "text": macro.read_macro(name)})
                return self._static(path)
            except FileNotFoundError as e:
                return self._json({"error": str(e)}, 404)
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
            except KeyError:
                return self._json({"error": f"no project {q.get('slug')!r}"}, 404)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _static(self, path: str):
            name = "index.html" if path in ("/", "") else path.lstrip("/")
            target = (STATIC / name).resolve()
            if STATIC in target.parents and target.is_dir():   # the React UI at /next/
                if not path.endswith("/"):                     # its asset paths are relative
                    self.send_response(301)
                    self.send_header("Location", path + "/")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                target = target / "index.html"
            if STATIC not in target.parents or not target.is_file():
                return self._json({"error": "not found"}, 404)
            self._send(200, target.read_bytes(), TYPES.get(target.suffix, "application/octet-stream"))

        def _file(self, slug: str, rel: str):
            pdir = (bench.root_of(slug) / slug).resolve()
            target = (pdir / rel).resolve()
            inside = lambda t: any(pdir / d in t.parents for d in ("out", "baseline"))
            if not inside(target):
                # a log or checks.json written where the project used to live
                # (a clone, a copy): the same file under this project
                for d in ("/out/", "/baseline/"):
                    if d in rel:
                        target = (pdir / (d.strip("/") + "/" + rel.rsplit(d, 1)[1])).resolve()
                        break
            kinds = {".png": "image/png", ".step": "application/step", ".stl": "model/stl"}
            ok = target.suffix in kinds and target.is_file() and inside(target)
            if not ok:
                return self._json({"error": "only renders and exports under out/ or baseline/"}, 404)
            # An export is a download; a render shows in the page.
            extra = {} if target.suffix == ".png" else {"Content-Disposition": f'attachment; filename="{target.name}"'}
            self._send(200, target.read_bytes(), kinds[target.suffix], extra)

        def _events(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            q: queue.Queue = queue.Queue()
            with bench.lock:
                bench.clients.append(q)
            try:
                self.wfile.write(b"retry: 1500\n\n")
                self.wfile.flush()
                while True:
                    try:
                        msg = q.get(timeout=15)
                        self.wfile.write(f"data: {msg}\n\n".encode())
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                with bench.lock:
                    if q in bench.clients:
                        bench.clients.remove(q)

        # ── POST ─────────────────────────────────────────────────────────────
        def do_POST(self):
            if not self._local() or self.headers.get("X-CAD") != "1":
                return self._json({"error": "localhost pages only"}, 403)
            path = urlparse(self.path).path
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._json({"error": "body must be JSON"}, 400)
            slug = body.get("slug", "")
            try:
                if path == "/api/roots":
                    added = bench.add_root(Path(str(body.get("path", ""))))
                    if added and bench.port is not None:
                        write_registry(bench)       # keep `cad gui`'s discovery current
                    bench.broadcast({"type": "projects"})
                    return self._json({"added": added, "roots": [str(r) for r in bench.roots]})
                if path == "/api/init":
                    # File > New: there is no project yet, so this runs ahead of
                    # bench.root_of(slug) below, same as /api/roots.
                    name = str(body.get("name", ""))
                    root_in = body.get("root")
                    if root_in:
                        root = Path(str(root_in)).expanduser().resolve()
                    elif bench.roots:
                        root = bench.roots[0]
                    else:
                        return self._json({"exit": 3, "stderr": "", "data": {    # cli.USAGE
                            "error": "no projects root configured; pass \"root\""}})
                    r = bench.run(root, ["--with-text", "init", name])
                    if r["exit"] == 0:
                        r["data"] = {**r["data"], "slug": name, "root": str(root)}
                        added = bench.add_root(root)
                        if added and bench.port is not None:
                            write_registry(bench)
                        bench.broadcast({"type": "projects"})
                    return self._json(r)
                # macros: not tied to any one project, so these skip bench.root_of(slug) below
                if path == "/api/macro":
                    text = body.get("text")
                    if not isinstance(text, str):
                        return self._json({"error": "text must be a string"}, 400)
                    name = str(body.get("name", ""))
                    return self._json({"name": name, "path": str(macro.save_macro(name, text))})
                if path == "/api/macro/delete":
                    macro.delete_macro(str(body.get("name", "")))
                    return self._json({"deleted": True})
                if path == "/api/macro/rename":
                    p = macro.rename_macro(str(body.get("name", "")), str(body.get("to", "")))
                    return self._json({"name": p.stem, "path": str(p)})
                if path == "/api/macro/duplicate":
                    p = macro.duplicate_macro(str(body.get("name", "")), str(body.get("to", "")))
                    return self._json({"name": p.stem, "path": str(p)})
                if path == "/api/cache/clear":
                    from . import appcache
                    freed = appcache.clear()
                    total = appcache.size()
                    return self._json({"freed": freed, "bytes": total, "text": appcache.to_string(total)})
                if path == "/api/pref":
                    # `cad pref KEY VALUE`'s store, written here directly (no project involved).
                    from . import userprefs
                    try:
                        userprefs.set_value(str(body.get("key", "")), body.get("value"))
                    except (KeyError, TypeError, ValueError) as e:
                        return self._json({"error": f"bad preference: {e}"}, 400)
                    return self._json({"prefs": userprefs.load()})
                if path == "/api/macro/run":
                    name = str(body.get("name", ""))
                    text = macro.read_macro(name)
                    run_slug = str(body.get("slug") or "")
                    return self._json(bench.macro_run(run_slug, name, text.splitlines()))
                bench.root_of(slug)
                if path in ("/api/undo", "/api/redo"):
                    action = path.rsplit("/", 1)[-1]
                    steps = int(body.get("steps") or 1)
                    r = bench.cad(slug, action,
                                 ["--with-text", action, slug, "--steps", str(steps)])
                    return self._json(r)
                if path == "/api/place":
                    args = ["place", slug, str(body["body"])]
                    if body.get("reset"):
                        args.append("--reset")
                    else:
                        for key in ("move", "turn", "about"):
                            v = [float(x) for x in body[key]]
                            args.append(f"--{key}={v[0]:.6g},{v[1]:.6g},{v[2]:.6g}")
                    r = bench.cad(slug, "place", args)
                    if r["exit"] in (0, 1):
                        bench.schedule(slug, "check")
                    return self._json(r)
                if path == "/api/set":
                    # A person changed a dimension in the Inspect panel: `cad set` writes it
                    # into the part's PARAMS (after checking the part still builds).
                    values = body["values"]
                    if not isinstance(values, dict) or not values:
                        return self._json({"error": "values must be {name: value}"}, 400)
                    args = ["set", slug, str(body["part"])]
                    for k, v in values.items():
                        args.append(f"{k}={v if isinstance(v, str) else json.dumps(v)}")
                    r = bench.cad(slug, "set", args)
                    if r["exit"] in (0, 1, 2):
                        bench.schedule(slug, "check")
                    return self._json(r)
                if path == "/api/export":
                    fmt = str(body.get("format", "step"))
                    if fmt not in ("step", "stl"):
                        return self._json({"error": "format is step or stl"}, 400)
                    return self._json(bench.cad(slug, "export", ["export", slug, str(body["part"]), "--format", fmt]))
                if path == "/api/measure":
                    return self._json(bench.cad(slug, "measure", ["measure", slug, str(body["a"]),
                                                                  str(body["b"]), "--posed"]))
                if path == "/api/reveal":
                    # The tree's Open file location: the project folder, or a part's file,
                    # in the desktop's file manager (this server runs on the user's machine).
                    target = bench.root_of(slug) / slug
                    part = str(body.get("part") or "")
                    parts = (target / "parts").resolve()
                    if part and (parts / f"{part}.py").is_file() and (parts / f"{part}.py").resolve().parent == parts:
                        target = parts / f"{part}.py"
                    if sys.platform == "darwin":
                        cmd = ["open", "-R", str(target)] if target.is_file() else ["open", str(target)]
                    elif sys.platform.startswith("win"):
                        cmd = ["explorer", f"/select,{target}"] if target.is_file() else ["explorer", str(target)]
                    else:
                        cmd = ["xdg-open", str(target if target.is_dir() else target.parent)]
                    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return self._json({"revealed": str(target)})
                if path == "/api/mass":
                    names = [str(n) for n in body.get("bodies") or []]
                    return self._json(bench.cad(slug, "mass", ["mass", slug, *names]))
                if path == "/api/check":
                    bench.schedule(slug, "check")
                    return self._json({"started": True})
                if path == "/api/verify":
                    bench.schedule(slug, "verify")
                    return self._json({"started": True})
                if path == "/api/approve":
                    # A person clicked Approve on the page; the agent never calls this.
                    args = ["approve", slug]
                    if body.get("part"):
                        args += ["--part", str(body["part"])]
                    if body.get("view"):
                        args += ["--view", str(body["view"])]
                    r = bench.cad(slug, "approve", args)
                    bench.schedule(slug, "check")
                    return self._json(r)
                if path == "/api/gui":
                    # The UI pushing its own live state: selection, hover, task, camera.
                    state = body.get("state")
                    if not isinstance(state, dict):
                        return self._json({"error": "state must be an object"}, 400)
                    return self._json(bench.gui_post(slug, state))
                if path == "/api/gui/do":
                    # An agent (or the UI) pointing at things for whoever is looking: the
                    # same FreeCADGui.Selection / Visibility / SendMsgToActiveView job.
                    cmd = str(body.get("cmd", ""))
                    args = body.get("args")
                    if not isinstance(args, list):
                        return self._json({"error": "args must be a list"}, 400)
                    return self._json(bench.gui_do(slug, cmd, args, body.get("props")))
                if path == "/api/cad":
                    # The UI's console: any cad subcommand, run exactly as the CLI would.
                    argv = body.get("argv")
                    if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
                        return self._json({"error": "argv must be a non-empty list of strings"}, 400)
                    if argv[0] in ("serve", "service"):
                        return self._json({"exit": 3, "stderr": "", "data": {    # cli.USAGE
                            "error": f"cad {argv[0]} cannot run through the workbench console; "
                                     "use a shell"}})
                    return self._json(bench.cad(slug, argv[0], ["--with-text", *argv]))
                return self._json({"error": "unknown endpoint"}, 404)
            except KeyError as e:
                return self._json({"error": f"missing or unknown {e}"}, 400)
            except FileNotFoundError as e:
                return self._json({"error": str(e)}, 404)
            except (TypeError, ValueError, IndexError, FileExistsError) as e:
                return self._json({"error": f"bad request: {e}"}, 400)

    return Handler


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


_NOT_SOURCE = {"out", ".cad", "__pycache__", ".git", ".venv", "node_modules"}


def _file_card(pdir: Path) -> dict:
    """What the Start page's file card shows for a project (FileCardDelegate: a thumbnail and
    a size): its newest render, the iso views first (out/*.png, not the checks' _-prefixed
    images), and the bytes of its own files."""
    out = pdir / "out"
    renders = [p for p in out.glob("*.png") if not p.name.startswith("_")] if out.is_dir() else []
    renders.sort(key=lambda p: (p.stem != "assembly_iso", "iso" not in p.stem, -p.stat().st_mtime))
    size = 0
    for f in pdir.rglob("*"):
        if f.is_file() and not (_NOT_SOURCE & set(f.relative_to(pdir).parts)):
            size += f.stat().st_size
    return {"thumb": f"out/{renders[0].name}" if renders else None, "size": size}


def make_server(bench: Bench, host: str = "127.0.0.1", port: int = 8733) -> Server:
    return Server((host, port), make_handler(bench))


def run(roots, host: str = "127.0.0.1", port: int = 8733, runner=None,
        keep_warm: bool = False) -> None:
    bench = Bench([*roots, *saved_roots()], runner)
    try:
        httpd = make_server(bench, host, port)
    except OSError as e:
        raise RuntimeError(f"port {port} is busy ({e.strerror}); another workbench may be "
                           f"running, or pass --port") from e
    bench.host, bench.port = host, httpd.server_address[1]
    write_registry(bench)      # so `cad gui` elsewhere on the machine can find this one
    threading.Thread(target=bench.watch, daemon=True).start()
    threading.Thread(target=bench.keep_warm if keep_warm else bench.warm_up, daemon=True).start()
    n = len(bench.projects())
    print(f"workbench: http://{host}:{bench.port}  ({n} projects in {len(bench.roots)} folders; "
          "Ctrl-C stops it)", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        remove_registry(bench.port)
        httpd.server_close()

"""cad gui: the CLI's side of the workbench's shared GUI state — HTTP calls to
a running `cad serve`, the same endpoints the UI itself calls.

Several workbenches can be up on one machine at once (a login service on the
real projects, a scratch one on a temp folder for a test or another
checkout), so a project has to be matched to the one server that actually
serves it rather than assumed to be on a fixed port. CAD_SERVE_URL overrides
this outright; otherwise every server this machine has recorded (serve.
list_registry) is asked whether it is still up, and the one whose roots
include the project's root, or whose own /api/projects lists the slug, wins.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


class NoWorkbench(Exception):
    """No running workbench answers for this project (the CLI exits 2, UNCHECKED)."""


class GuiRequestError(Exception):
    """A workbench answered but rejected the request (the CLI exits 3, usage)."""


def _call(req: urllib.request.Request, timeout: float) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}
    except (urllib.error.URLError, OSError, TimeoutError, ValueError) as e:
        raise NoWorkbench(str(e)) from None


def _get(url: str, timeout: float = 5) -> tuple[int, dict]:
    return _call(urllib.request.Request(url), timeout)


def _post(url: str, body: dict, timeout: float = 15) -> tuple[int, dict]:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-CAD": "1"}, method="POST")
    return _call(req, timeout)


def _candidates() -> list[dict]:
    """Every registered workbench that still answers, with the projects it
    currently serves. A registry entry nothing answers for is removed: the
    process behind it is gone."""
    from . import serve
    out = []
    for rec in serve.list_registry():
        url = f"http://{rec.get('host', '127.0.0.1')}:{rec.get('port')}"
        try:
            code, body = _get(url + "/api/projects")
        except NoWorkbench:
            serve.remove_registry(rec.get("port"))
            continue
        if code != 200:
            continue
        out.append({**rec, "url": url, "projects": [p["slug"] for p in body.get("projects", [])]})
    return out


def find_server(root: Path, slug: str) -> str:
    """The base URL (http://host:port) of the workbench serving `slug`, a
    project under `root`. Raises NoWorkbench when none, or more than one
    without a clear winner, answers for it."""
    override = os.environ.get("CAD_SERVE_URL")
    if override:
        return override.rstrip("/")
    live = _candidates()
    if not live:
        raise NoWorkbench("no workbench running (start it with: cad serve)")
    root = Path(root).expanduser().resolve()
    by_root = {r["url"] for r in live
              if root in {Path(x).expanduser().resolve() for x in r.get("roots", [])}}
    by_slug = {r["url"] for r in live if slug in r.get("projects", [])}
    chosen = (by_root & by_slug) or by_root or by_slug
    if len(chosen) == 1:
        return next(iter(chosen))
    if not chosen:
        found = "; ".join(f"{r['url']} (projects: {', '.join(r['projects']) or 'none'})" for r in live)
        raise NoWorkbench(f"no running workbench serves project {slug!r}; found {found}")
    raise NoWorkbench(f"{len(chosen)} workbenches could serve {slug!r} "
                      f"({', '.join(sorted(chosen))}); set CAD_SERVE_URL to pick one")


def _unwrap(code: int, body: dict, url: str) -> dict:
    if code != 200:
        raise GuiRequestError(body.get("error") or f"workbench at {url} returned HTTP {code}")
    return body


def get_state(url: str, slug: str) -> dict:
    code, body = _get(f"{url}/api/gui?{urllib.parse.urlencode({'slug': slug})}")
    return _unwrap(code, body, url)


def post_state(url: str, slug: str, patch: dict) -> dict:
    code, body = _post(f"{url}/api/gui", {"slug": slug, "state": patch})
    return _unwrap(code, body, url)


def do(url: str, slug: str, cmd: str, args: list[str], props: dict | None = None) -> dict:
    payload = {"slug": slug, "cmd": cmd, "args": args}
    if props is not None:
        payload["props"] = props
    code, body = _post(f"{url}/api/gui/do", payload)
    return _unwrap(code, body, url)

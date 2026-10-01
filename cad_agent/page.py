"""cad page: a review page for one project at one commit, to share.

`cad page <slug>` writes a folder, out/page/ by default:

    index.html   the page (a fragment: the artifact host adds the document shell)
    page.js      the page logic; three-cad-viewer draws the model
    three-cad-viewer.esm.min.js, .css   the viewer itself, published with the page
    scene.json   the model, the same data the workbench draws
    data.json    verdict, git commit, every gate row, parts, renders
    renders/     current renders, and the approved baselines

Publish the folder as a private artifact (index.html, with the other files next
to it) and send the link. The reader can turn, cut, explode and measure the
model and read every gate, on any device, without installing anything. It is a
snapshot: moves are not written back, and the verdict is the one `cad verify`
recorded. Publish again after the next verify.
"""
from __future__ import annotations

import html
import json
import shutil
import time
from pathlib import Path

from . import state as st

STATIC = Path(__file__).resolve().parent / "workbench"
FILES = ("page.js",)


def _title(slug: str) -> str:
    return " ".join(w.capitalize() for w in slug.replace("-", "_").split("_") if w)


def build_page(slug: str, out: Path | None = None) -> tuple[Path, dict]:
    from .scene import build_scene, plain
    from .verify import git_info, status
    pdir = st.project_dir(slug)
    out = Path(out) if out else pdir / "out" / "page"
    out.mkdir(parents=True, exist_ok=True)
    scene = build_scene(slug)
    (out / "scene.json").write_text(json.dumps(scene, separators=(",", ":"), default=plain))
    try:
        checks = st.read_checks(slug)
    except (FileNotFoundError, ValueError):
        checks = {}

    shutil.rmtree(out / "renders", ignore_errors=True)          # only ever our own copies
    (out / "renders").mkdir()
    renders, seen = [], set()
    for r in checks.get("renders", []):
        key = (r["part"], r["view"])
        if key in seen:
            continue
        seen.add(key)
        cur = pdir / r["path"]
        base = pdir / "baseline" / f"{r['part']}_{r['view']}.png"
        item = {"subject": r["part"], "view": r["view"], "current": None, "approved": None}
        if cur.is_file():
            item["current"] = f"renders/{r['part']}_{r['view']}.png"
            shutil.copyfile(cur, out / item["current"])
        if base.is_file():
            item["approved"] = f"renders/approved_{r['part']}_{r['view']}.png"
            shutil.copyfile(base, out / item["approved"])
        if item["current"] or item["approved"]:
            renders.append(item)

    rows = [{k: v for k, v in row.items() if k != "artifacts"} for row in checks.get("rows", [])]
    stat = status(slug)
    data = {
        "format": "cad-page/1", "project": slug, "title": _title(slug),
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git": git_info(pdir),
        "status": {k: stat.get(k) for k in ("done", "verdict", "reasons", "verified_utc", "commit")},
        "checks_written_utc": checks.get("written_utc"),
        "summary": checks.get("summary", {}).get("by_state", {}),
        "rows": rows, "renders": renders,
    }
    (out / "data.json").write_text(json.dumps(data, indent=1, default=str))
    for name in FILES:
        shutil.copyfile(STATIC / name, out / name)
    for name in ("three-cad-viewer.css", "three-cad-viewer.esm.min.js"):   # the viewer, self-hosted
        shutil.copyfile(STATIC / "vendor" / name, out / name)
    for stale in ("view.js", "measure.js"):                   # written by older versions
        (out / stale).unlink(missing_ok=True)
    page = (STATIC / "page.html").read_text().replace("{{TITLE}}", html.escape(data["title"]))
    (out / "index.html").write_text(page)
    return out, data

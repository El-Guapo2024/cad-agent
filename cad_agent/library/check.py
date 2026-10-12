"""`check`: hash what is on disk against what says it should be, in the store and in a project.

Two things are checked, and each answers a different question.

The store. Every file in it is named for its hash, so re-hashing it says whether it is still the file it was
(a disk error, an edit), and the catalog's pins say whether the file is the one an entry stands for. A shipped
entry that was never fetched is N/A, since it is not a fault that a file was not downloaded; a file that
the user's own entry pins and the store lacks is a FAIL, since the user put it there.

A project's bought/. For each part the file that defines its geometry is hashed against the sidecar's sha256 (the
same test the provenance rule makes at verify time), and a part that names a library entry is then compared with
the catalog: a STEP against the catalog's pin, and a generated part against what `use` would write today for the
parameters it was made with. A catalog that has moved on since is not a failure of the project, which is
verified against its own tree, so it is UNCHECKED: the user decides whether to take the change (`use --replace`)
and the row says what differs. A part that never came from the library has no catalog row, and a hand-made
part that pins nothing is N/A.

The rows are the shape of every other command's (state, rule, subject, measured, limit, source), and the exit code
is the verdict of cmdbase.verdict: FAIL outranks UNCHECKED outranks 0.
"""
from __future__ import annotations

import json
from pathlib import Path

from .. import bought
from . import store
from .catalog import Catalog, LibraryError, arguments, resolve_params, sidecar
from .use import render_module

CONTRACT = ("source", "vendor", "pn", "licence", "geometry", "mass_g", "mass_source", "material", "max_temp_c",
            "max_temp_source", "attribution", "datum")


def row(state: str, rule: str, subject: str, measured: str, limit: str = "n/a", source: str = "") -> dict:
    return {"check": "library", "rule": rule, "subject": subject, "state": state, "measured": measured,
            "limit": limit, "source": source}


def check_store(catalog: Catalog) -> list[dict]:
    rows = [row("FAIL", "catalog", "catalog", problem, "a catalog every entry of which is well formed",
                "catalog.toml and the store's library.json") for problem in catalog.problems]
    whole = {}
    for path in store.files(catalog.store):
        sha = path.stem
        actual = store.sha256_of(path)
        whole[sha] = actual == sha
        names = ", ".join(e.name for e in catalog.entries.values() if e.sha256 == sha) or "no entry"
        rows.append(row("PASS" if actual == sha else "FAIL", "store file", f"{sha[:12]} ({names})",
                        "hashes to its own name" if actual == sha else f"hashes to {actual}, not its name",
                        "a file that is what its name says", "sha256 of the bytes"))
    for entry in catalog.entries.values():
        if entry.kind != "step" or not entry.sha256 or entry.problems:
            continue
        if whole.get(entry.sha256):
            rows.append(row("PASS", "pin", entry.name, f"in the store, and it is the file pinned ({entry.sha256[:12]})",
                            "the file the entry pins", f"the {entry.origin} entry's sha256"))
        elif entry.sha256 not in whole and entry.origin == "shipped":
            rows.append(row("N/A", "pin", entry.name, "not in your store (it is not a fault that it was not downloaded)",
                            "n/a", f"`cad lib fetch {entry.name}` or `cad lib add`"))
        elif entry.sha256 not in whole:
            rows.append(row("FAIL", "pin", entry.name, f"your entry pins {entry.sha256[:12]} and the store lacks it",
                            "the file the entry pins", "the store's library.json"))
    if not rows:
        rows.append(row("N/A", "store", str(catalog.store), "the store holds nothing yet", "n/a", "`cad lib fetch`"))
    return rows


def _side(path: Path) -> dict:
    try:
        data = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _catalog_rows(slug: str, name: str, spec, actual: str, side: dict, catalog: Catalog) -> dict:
    """The comparison with the catalog for one part that names a library entry."""
    entry = catalog.entries.get(spec.library)
    if entry is None:
        return row("UNCHECKED", "catalog", name, f"{spec.library} is not in this catalog (an older or newer cad-agent, "
                   "or a store that is not yours)", "an entry the catalog holds", "catalog.toml and the store's library.json")
    if entry.kind == "step":
        if entry.sha256 is None:
            return row("UNCHECKED", "catalog", name, f"{entry.name} pins no sha256", "the file the entry pins", "the entry")
        ok = actual == entry.sha256
        return row("PASS" if ok else "FAIL", "catalog", name,
                   f"{spec.file} is the file {entry.name} pins" if ok else
                   f"{spec.file} hashes to {actual[:16]}..., and {entry.name} pins {entry.sha256[:16]}...",
                   "the file the entry pins", f"the {entry.origin} entry's sha256")
    if not entry.verified:
        return row("UNCHECKED", "catalog", name, f"{entry.name} is declared unconfirmed, and its module is meant to be edited "
                   "when it is confirmed, so it is not compared", "the module the entry writes", "the entry")
    given = side.get("library_params")
    if not isinstance(given, dict):
        return row("UNCHECKED", "catalog", name, "its sidecar does not record the parameters it was made with, so "
                   "the copy cannot be made again to compare", "the module the entry writes", "the sidecar's library_params")
    try:
        params = resolve_params(entry, given)
    except LibraryError as e:
        return row("UNCHECKED", "catalog", name, f"the parameters it was made with no longer hold: {e}",
                   "the module the entry writes", "the catalog")
    want, differs = sidecar(entry, params), []
    for key in CONTRACT:
        if want.get(key) != side.get(key):
            differs.append(key)
    text = render_module(entry, name, arguments(entry, params), params)
    if text != Path(bought.bought_dir(slug) / spec.file).read_text(encoding="utf-8"):
        differs.append("the module")
    if differs:
        return row("UNCHECKED", "catalog", name, f"the catalog says something else now: {', '.join(differs)}; "
                   f"`cad lib use ... --as {name} --replace` takes the change", "what the entry writes today", "the catalog")
    return row("PASS", "catalog", name, f"the same as {entry.name} writes today", "what the entry writes today", "the catalog")


def check_project(slug: str, catalog: Catalog) -> list[dict]:
    rows = []
    parts = bought.list_bought(slug)
    if not parts:
        return [row("N/A", "bought parts", slug, "none in this project", "n/a", "nothing bought, so nothing to compare")]
    for part in parts:
        name = part["name"]
        spec = bought.bought_spec(slug, name)
        path = bought.bought_dir(slug) / spec.file
        side = _side(path)
        actual = bought.file_sha256(path)
        if spec.sha256 is not None:
            ok = actual == spec.sha256
            rows.append(row("PASS" if ok else "FAIL", "sha256", name,
                            f"{spec.file} hashes to {actual[:16]}..., the pin" if ok else
                            f"{spec.file} hashes to {actual[:16]}..., the sidecar pins {spec.sha256[:16]}...",
                            "the sha256 the sidecar pins", "the sidecar"))
        elif spec.library and spec.verified:
            rows.append(row("UNCHECKED", "sha256", name, f"copied from {spec.library} and pins no sha256, so nothing says "
                            f"{spec.file} is the file that was copied", "a sha256 pin", "the sidecar"))
        elif spec.library:
            rows.append(row("UNCHECKED", "sha256", name, f"unpinned: {spec.library} is declared unconfirmed, and `cad bought "
                            "verify` rewrites its module", "a sha256 pin", "the sidecar"))
        else:
            rows.append(row("N/A", "sha256", name, "not from the library, and it pins nothing", "n/a", "the sidecar"))
        if spec.library:
            rows.append(_catalog_rows(slug, name, spec, actual, side, catalog))
        else:
            rows.append(row("N/A", "catalog", name, "not copied from the library", "n/a", "the sidecar"))
    return rows

"""`use`: copy one entry into a project's bought/, with the sidecar that says where it came from.

After this the project is on its own. What it needs is in bought/: the STEP, or a small module that calls a
generator with every number written out, and `<name>.json` with the contract keys of bought.py (source, vendor, part
number, licence, mass and its source, geometry, the datum, the sha256). `cad verify`, the build cache, CI and the
eval scorer read the project's own tree, never the store and never the catalog, so a verdict about a design does
not move when the library does. The generator itself is code in cad_agent/library/gen/, which is part of the
engine (verify.engine_hash covers it), so a change to a generator changes every verdict, as a change to a rule does.

A module, not a copy of the generator, because a generator is code and the project should hold its parameters. The
module imports the generator inside build(), so that listing the project's bought parts (`cad ls`, `cad bought ls`)
runs it without waiting for the CAD kernel. It is pinned: the sidecar's sha256 is the hash of the module, so an
edit by hand is a FAIL row (`cad lib check` and the provenance rule) and not a quiet change of geometry. The one
exception is a part that declares something unconfirmed, such as a dimension no maker publishes: its module carries
the flag `cad bought verify` looks for to take a calliper reading, and that command rewrites the module, so the
part is left unpinned until it is confirmed.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from dataclasses import dataclass, field
from pathlib import Path

from .. import bought
from . import store
from .catalog import (PART_NAME, Catalog, Entry, IntegrityError, LibraryError, arguments, fetch_ruling, resolve_params,
                      sidecar)

SUFFIXES = (".step", ".stp", ".py", ".json")        # what bought/ may hold under one name
JOURNAL_MAX = 4 << 20                               # bytes of files the undo journal is given for one copy


@dataclass
class Copy:
    name: str
    entry: Entry
    params: dict
    files: list                                     # paths written
    side: dict                                      # the sidecar as written
    notes: list = field(default_factory=list)
    changes: list | None = None                     # [{"path", "before", "after"}] for the undo journal; None if it was too big


def default_name(entry: Entry) -> str:
    return entry.name.replace("-", "_")


def command(entry: Entry, name: str, params: dict) -> str:
    """The `cad lib use` that makes this copy again, as the module's docstring and the journal say it."""
    given = " ".join(f"{k}={v:g}" if isinstance(v, float) else f"{k}={v}" for k, v in params.items())
    return f"cad lib use <project> {entry.name}{' ' + given if given else ''} --as {name} --replace"


def _doc(text: str) -> str:
    """Text for the inside of a triple-quoted docstring: a backslash or a run of quotes must not end or break it."""
    return text.replace("\\", "/").replace('"""', "'''")


def render_module(entry: Entry, name: str, args: dict, params: dict) -> str:
    """The module a generator entry becomes: its docstring says what it is, ARGS holds every number, build() calls the generator."""
    module, _, function = entry.generator.partition(":")
    made = ", ".join(f"{k} {v:g}" + (f" {entry.params[k]['unit']}" if entry.params[k]["unit"] else "")
                     if isinstance(v, float) else f"{k} {v}" for k, v in params.items())
    head = [f'"""{name}: {_doc(entry.title)}' + (f", {made}" if made else "") + ".", "",
            f"Copied from the library entry {entry.name} by `cad lib use`; where each number came from is in {name}.json",
            f"and in `cad lib info {entry.name}`."]
    if entry.verified:
        head += [f"It is meant to be left alone: `{command(entry, name, params)}`", "writes it again, and `cad lib check <project>` "
                 "fails when this file no longer hashes to the pin in the sidecar."]
    else:
        head += ["", "Not confirmed: " + _doc(", ".join(entry.unconfirmed)) + ". Measure the real part, put what you measured in ARGS,",
                 f"and run `cad bought verify <project> {name} --note \"what you measured\"`. It pins no hash, because that",
                 "command rewrites this file."]
    lines = head + ['"""']
    if not entry.verified:
        lines += [f"SOURCE = {entry.source + ' Unconfirmed: ' + ', '.join(entry.unconfirmed) + '.'!r}", "VERIFIED = False"]
    lines += ["", "PARAMS = {}                      # fixed: the sidecar's mass is the mass of exactly this part", "", "ARGS = {"]
    lines += [f"    {k!r}: {v!r}," for k, v in args.items()]
    lines += ["}", "", "", "def build():", f"    from {module} import {function}", f"    return {function}(**ARGS)", ""]
    return "\n".join(lines)


def _taken(bdir: Path, name: str) -> list[Path]:
    return [bdir / f"{name}{s}" for s in SUFFIXES if (bdir / f"{name}{s}").exists()]


def _library_part(bdir: Path, name: str) -> bool:
    """Whether the part now under this name was written by the library (its sidecar names an entry)."""
    try:
        return isinstance(json.loads((bdir / f"{name}.json").read_text(encoding="utf-8")).get("library"), str)
    except (OSError, ValueError, AttributeError):
        return False


def _text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _came_from(row: dict | None) -> str | None:
    """A sentence on how the store came to hold this file, from the record `fetch` and `add` keep."""
    if not row:
        return None
    when = row.get("when", "")
    if row.get("how") == "fetch" and row.get("url"):
        return f"In the store: fetched from {row['url']} on {when}."
    if row.get("how") == "add":
        return f"In the store: downloaded by hand from {row.get('source', 'a page the user recorded')} on {when}."
    return None


def use(slug: str, catalog: Catalog, entry_name: str, given: dict, name: str | None = None, replace: bool = False) -> Copy:
    """Copy an entry into project `slug`. Raises LibraryError for a request that cannot be done as asked (an unknown
    entry or parameter, a name taken, a STEP not in the store) and IntegrityError for a store file that is not the one
    the catalog pins. Writes nothing in either case."""
    entry = catalog.get(entry_name)
    if entry.problems:
        raise LibraryError(f"{entry.name} is not usable as it stands: " + "; ".join(entry.problems))
    name = name or default_name(entry)
    if not PART_NAME.match(name):
        raise LibraryError(f"a bought part is named with letters, digits and _ (starting with a letter), not {name!r}")
    if entry.kind == "step" and given:
        raise LibraryError(f"{entry.name} is a file, which takes no parameters (got {', '.join(sorted(given))})")
    params = resolve_params(entry, given)
    if entry.kind == "bd_warehouse" and importlib.util.find_spec(entry.requires) is None:
        raise LibraryError(f"{entry.name} is drawn by {entry.requires}, which is not installed: "
                           "`pip install 'cad-agent[fasteners]'`")
    bdir = bought.bought_dir(slug)
    if (bdir.parent / "parts" / f"{name}.py").exists():
        raise LibraryError(f"{slug} already has a part module called {name}: `--as` picks another name for the bought part")
    taken = _taken(bdir, name)
    if taken and not replace:
        raise LibraryError(f"bought/ already has {', '.join(p.name for p in taken)}; `--as` picks another name, "
                           "`--replace` writes this one again")
    if taken and not _library_part(bdir, name):
        raise LibraryError(f"bought/{name} was not copied from the library, so `--replace` will not overwrite it: "
                           "remove it by hand if you mean to")

    src, payload, note = None, None, None
    if entry.kind == "step":
        src = store.path_of(entry.sha256, catalog.store)
        if not src.exists():
            ok, _ = fetch_ruling(entry)
            how = (f"`cad lib fetch {entry.name}`, or download it by hand and " if ok else "download it by hand and ")
            raise LibraryError(f"{entry.name} is not in your store ({catalog.store}): {how}"
                               f"`cad lib add {entry.name} FILE --source URL`")
        if store.sha256_of(src) != entry.sha256:
            raise IntegrityError(f"the store's file for {entry.name} no longer hashes to the catalog's pin "
                                 f"{entry.sha256}: it is damaged. Delete {src} and fetch it again")
        note = _came_from(catalog.files.get(entry.sha256))
        geometry_file = bdir / f"{name}.step"
    else:
        payload = render_module(entry, name, arguments(entry, params), params)
        compile(payload, f"{name}.py", "exec")           # a title with a stray quote must not become a module that will not load
        geometry_file = bdir / f"{name}.py"

    side = sidecar(entry, params, note)
    if entry.kind == "step":
        side["sha256"], side["original"] = entry.sha256, f"{entry.sha256}.step"
    elif entry.verified:
        side["sha256"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    else:
        side.pop("verified", None)                       # the module's flag says it, and `cad bought verify` edits that
    side_path = bdir / f"{name}.json"

    data = src.read_bytes() if src is not None else None          # read before anything is removed
    before = {p: _text(p) for p in taken}
    for p in taken:
        p.unlink()
    bought.bought_dir(slug, create=True)
    if data is not None:
        geometry_file.write_bytes(data)
    else:
        geometry_file.write_text(payload, encoding="utf-8")
    side_path.write_text(json.dumps(side, indent=1) + "\n", encoding="utf-8")
    written = [geometry_file, side_path]

    notes = []
    if "mass_g" not in side:
        notes.append("declares no mass_g: [[mass]] bodies and the centre-of-mass rule take its mass as unknown")
    if "max_temp_c" not in side and "material" not in side:
        notes.append("declares neither max_temp_c nor a material (its sources give none): [[heat]] cannot rate it, so a hot "
                     "zone near it is UNCHECKED")
    if not entry.verified:
        notes.append("unconfirmed (" + ", ".join(entry.unconfirmed or ["its dimensions"]) +
                     "): the provenance rule says UNCHECKED until it is measured")
    notes += list(entry.notes)

    changes = None                                       # the undo journal keeps whole files, so a big STEP is not kept in it
    small = sum(p.stat().st_size for p in written) + sum(len(v) for v in before.values() if v) <= JOURNAL_MAX
    after = {p: _text(p) for p in written} if small else {}
    if small and None not in after.values() and None not in before.values():
        changes = [{"path": p.relative_to(bdir.parent).as_posix(), "before": before.get(p), "after": after.get(p)}
                   for p in sorted(set(before) | set(after))]
    return Copy(name=name, entry=entry, params=params, files=written, side=side, notes=notes, changes=changes)

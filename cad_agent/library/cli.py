"""`cad lib ls|info|add|use|check|fetch`: the part library's commands.

cmdbase.LAZY already knows these six and routes each here; the options are the ARGUMENTS at the end, given to a
command's parser only when that command is run or its --help is shown. Every handler returns a Result and ends with
the exit codes of every other command:

    0  the request was done, or the query answered
    1  FAIL         a file is not the one a pin names: a download or a file given to `add` that does not hash to the
                    catalog's pin, a store file that no longer hashes to its name, a library.json that cannot be read;
                    for `check`, any row that is FAIL
    2  UNCHECKED    nothing could be settled: the network did not answer a `fetch`; for `check`, a row that is
                    UNCHECKED (a part that pins no hash, a catalog that has moved on since the copy was made)
    3  usage        an unknown project, entry or parameter, a name already taken, a licence that does not allow a
                    fetch, a file that is not a STEP. Nothing was written
    4  crash        a bug here (cad.main turns any other exception into this)

A command that changes a project (`use`) writes its files into bought/ and journals the change like `cad bought
add-step` does, so `cad undo` takes it back. Every command is kernel-free (warm.KERNEL_FREE has `lib`): the catalog,
the store, the hashes and the copies need nothing from the CAD kernel, and `cad lib ls` answers at once. The
geometry a generator draws is built when a project builds the part it copied in.
"""
from __future__ import annotations

import importlib.util
import shlex
from pathlib import Path

from .. import bought
from .. import cmdbase
from ..cmdbase import FAIL, OK, Result, UsageError
from . import check, store, use
from .catalog import (KINDS, NAME, IntegrityError, LibraryError, Unreachable, fetch_ruling, load, mass_of,
                      resolve_params)

NEW_ENTRY_FLAGS = ("title", "vendor", "pn", "licence", "attribution", "material", "mass_g", "mass_source",
                   "max_temp_c", "max_temp_source", "datum_move", "datum_turn", "geometry", "unverified")


# ─── Reading the library ─────────────────────────────────────────────────────

def _status(entry, catalog) -> str:
    """Where an entry stands for this user: usable now, or what it would take."""
    if entry.kind == "step":
        if store.path_of(entry.sha256, catalog.store).exists():
            return "in your store"
        ok, _ = fetch_ruling(entry)
        return "fetch it" if ok else "add it by hand"
    if entry.kind == "bd_warehouse" and importlib.util.find_spec(entry.requires) is None:
        return f"needs {entry.requires} (cad-agent[fasteners])"
    return "ready"


def _summary(entry, catalog) -> dict:
    return {"name": entry.name, "kind": entry.kind, "title": entry.title, "vendor": entry.vendor, "pn": entry.pn,
            "licence": entry.licence, "geometry": entry.geometry, "verified": entry.verified, "origin": entry.origin,
            "status": _status(entry, catalog), "problems": list(entry.problems)}


def _columns(rows: list[list[str]]) -> list[str]:
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]) - 1)]
    return ["  " + "  ".join(c.ljust(w) for c, w in zip(r, widths)) + "  " + r[-1] for r in rows]


def cmd_lib_ls(a) -> Result:
    catalog = load()
    word = (a.query or "").lower()
    chosen = [e for e in catalog.entries.values()
              if (not a.kind or e.kind == a.kind)
              and (not word or word in " ".join(filter(None, (e.name, e.title, e.vendor, e.pn))).lower())]
    chosen.sort(key=lambda e: (KINDS.index(e.kind), e.name))
    rows = [_summary(e, catalog) for e in chosen]
    table = [["name", "kind", "vendor / part number", "licence", "status"]]
    table += [[r["name"], r["kind"], " ".join(filter(None, (r["vendor"], r["pn"]))) or "-", r["licence"], r["status"]]
              for r in rows]
    lines = [f"{len(rows)} of {len(catalog.entries)} entries (store: {catalog.store})"]
    lines += _columns(table) if rows else ["  nothing matches"]
    if catalog.problems:
        lines.append(f"{len(catalog.problems)} fault(s) in the catalog: `cad lib check` lists them")
    return Result(OK, {"store": str(catalog.store), "entries": rows, "problems": catalog.problems}, "\n".join(lines),
                  f"{len(rows)} entries")


def _span(p: dict) -> str:
    """What a parameter may be, in words."""
    if p["choices"]:
        return "one of " + ", ".join(map(str, p["choices"]))
    lo, hi = p["min"], p["max"]
    if lo is not None and hi is not None:
        return f"{lo:g} to {hi:g}"
    if lo is not None:
        return f"at least {lo:g}"
    return f"at most {hi:g}" if hi is not None else "any number"


def _describe(entry, catalog) -> list[str]:
    ok, why = fetch_ruling(entry)
    lines = [f"{entry.name}   {entry.title}",
             f"  kind     {entry.kind}" + (f" ({entry.generator})" if entry.generator else "") + f", {entry.origin}",
             f"  from     {entry.vendor or 'no vendor recorded'}" + (f", part number {entry.pn}" if entry.pn else "")
             + f", licence {entry.licence}",
             f"  geometry {entry.geometry}, " + ("verified" if entry.verified else
                                                  "UNCONFIRMED (" + ", ".join(entry.unconfirmed or ["see source"]) + ")"),
             f"  source   {entry.source}"]
    lines += [f"  read     {u}" for u in entry.docs]
    if entry.attribution:
        lines.append(f"  credit   {entry.attribution}")
    if entry.kind == "step":
        lines.append(f"  pinned   {entry.sha256}" + (f" ({entry.size} bytes)" if entry.size else ""))
        lines.append(f"  url      {entry.url or 'none: a file you add by hand'}")
        path = store.path_of(entry.sha256, catalog.store)
        row = catalog.files.get(entry.sha256, {})
        lines.append(f"  store    {path} " + (f"(in your store{', ' + row['how'] if row.get('how') else ''})"
                                              if path.exists() else "(not in your store)"))
        lines.append("  fetch    " + ("allowed: `cad lib fetch " + entry.name + "`" if ok else why))
        if entry.datum:
            lines.append(f"  datum    move {entry.datum['move']}, turn {entry.datum['turn']} (the file's frame to the part's)")
    for key, p in entry.params.items():
        lines.append(f"  param    {key} = {p['default']}" + (f" {p['unit']}" if p["unit"] else "") + f"  ({_span(p)})"
                     + (f"  [{p['source']}]" if p["source"] else ""))
    if entry.mass:
        grams, why_mass = mass_of(entry, resolve_params(entry, {}))
        lines.append(f"  mass     {grams:g} g at the defaults: {why_mass}")
    else:
        lines.append("  mass     none declared (no source gives one)")
    lines.append("  rating   " + (f"{entry.max_temp_c:g} C: {entry.max_temp_source}" if entry.max_temp_c is not None else
                                  "no max_temp_c declared" + (f"; its material {entry.material} is rated by materials.py"
                                                              if entry.material else "")))
    if entry.dims:
        lines.append("  dims (each with where it came from):")
        width = max(len(k) for k in entry.dims)
        lines += [f"    {k.ljust(width)}  {d['value']!s:<22} {d['source']}" for k, d in entry.dims.items()]
    if entry.model:
        lines.append("  model    " + ", ".join(f"{k} = {v}" for k, v in entry.model.items())
                     + "   (choices the model makes, not dimensions)")
    lines += [f"  note     {n}" for n in entry.notes]
    lines += [f"  fault    {p}" for p in entry.problems]
    return lines


def cmd_lib_info(a) -> Result:
    catalog = load()
    try:
        entry = catalog.get(a.entry)
    except LibraryError as e:
        raise UsageError(str(e)) from None
    ok, why = fetch_ruling(entry)
    data = {"entry": entry.as_dict(), "status": _status(entry, catalog), "fetch": {"allowed": ok, "why_not": why},
            "store": str(catalog.store)}
    if entry.kind == "step":
        data["in_store"] = store.path_of(entry.sha256, catalog.store).exists()
    return Result(OK, data, "\n".join(_describe(entry, catalog)), entry.name)


# ─── Copying in ──────────────────────────────────────────────────────────────

def _failed(error: Exception, code: int, what: str) -> Result:
    return Result(code, {"error": str(error)}, str(error), what)


def cmd_lib_use(a) -> Result:
    from .. import undo as un
    pdir = cmdbase.project(a.slug)
    given = cmdbase.pairs(a.params, "parameters")
    catalog = load()
    try:
        copy = use.use(a.slug, catalog, a.entry, given, name=a.name, replace=a.replace)
    except IntegrityError as e:
        return _failed(e, FAIL, "refused: a file is not the one pinned")
    except LibraryError as e:
        raise UsageError(str(e)) from None
    if copy.changes:
        cmd = shlex.join(["cad", "lib", "use", a.slug, a.entry, *a.params] + (["--as", a.name] if a.name else [])
                         + (["--replace"] if a.replace else []))
        un.record(pdir, "Add Library Part", cmd, copy.changes, by=cmdbase.actor(a))
    side = copy.side
    lines = [f"{copy.name}: {copy.entry.name} copied into {a.slug}/bought/ ({', '.join(p.name for p in copy.files)})",
             f"  from     {side.get('vendor') or 'no vendor recorded'}" + (f", part number {side['pn']}" if side.get("pn") else "")
             + f", licence {side['licence']}",
             f"  geometry {side['geometry']}" + (f", datum {side['datum']}" if side.get("datum") else ""),
             "  mass     " + (f"{side['mass_g']:g} g ({side['mass_source']})" if "mass_g" in side else "not declared"),
             "  pinned   " + (side["sha256"] if "sha256" in side else "no: see the notes")]
    lines += [f"  note     {n}" for n in copy.notes]
    if copy.changes is None:
        lines.append("  undo     not journaled (the files are large): delete the files above by hand to take it back")
    lines.append(f"  next     bought_solid({a.slug!r}, {copy.name!r}) in assembly.py; `cad lib check {a.slug}` re-hashes it")
    data = {"project": a.slug, "name": copy.name, "entry": copy.entry.name, "kind": copy.entry.kind,
            "params": copy.params, "sidecar": side, "notes": copy.notes, "journaled": copy.changes is not None,
            "files": [str(p) for p in copy.files]}
    return Result(OK, data, "\n".join(lines), f"{copy.entry.name} as {copy.name}", [str(p) for p in copy.files])


# ─── The store: add and fetch ────────────────────────────────────────────────

def _vector(text: str | None, what: str) -> list[float] | None:
    if text is None:
        return None
    try:
        v = [float(x) for x in text.split(",")]
    except ValueError:
        v = []
    if len(v) != 3:
        raise UsageError(f"{what} takes X,Y,Z, got {text!r} (write --datum-move=-1,0,2 when the first is negative)")
    return v


def _new_entry(a, sha: str, size: int) -> dict:
    """What `add` writes into library.json for a file the catalog does not know: only what the flags say, plus the pin."""
    if (a.mass_g is None) != (a.mass_source is None):
        raise UsageError("--mass-g and --mass-source go together: a mass with no source is not used")
    if (a.max_temp_c is None) != (a.max_temp_source is None):
        raise UsageError("--max-temp-c and --max-temp-source go together: a rating with no source is not used")
    datum = None
    if a.datum_move or a.datum_turn:
        datum = {"move": _vector(a.datum_move, "--datum-move") or [0, 0, 0],
                 "turn": _vector(a.datum_turn, "--datum-turn") or [0, 0, 0]}
    raw = {"title": a.title or a.entry, "kind": "step", "licence": a.licence or "unknown", "geometry": a.geometry or "envelope",
           "verified": not a.unverified, "source": a.source, "vendor": a.vendor, "pn": a.pn,
           "attribution": a.attribution, "material": a.material,
           "mass": {"g": a.mass_g, "source": a.mass_source} if a.mass_g is not None else None,
           "max_temp_c": a.max_temp_c, "max_temp_source": a.max_temp_source, "datum": datum, "sha256": sha, "size": size}
    return {k: v for k, v in raw.items() if v is not None}


def cmd_lib_add(a) -> Result:
    path = Path(a.file).expanduser()
    if not path.is_file():
        raise UsageError(f"no file at {path}")
    if not store.looks_like_step(path):
        raise UsageError(f"{path} does not begin the way a STEP file does (ISO-10303-21;): it is not what `add` takes")
    if not a.source.strip():
        raise UsageError("--source is required: the page the file came from")
    catalog = load()
    known = catalog.entries.get(a.entry)
    flags = [f for f in NEW_ENTRY_FLAGS if getattr(a, f) not in (None, False)]
    try:
        if known is not None and known.kind != "step":
            raise UsageError(f"{known.name} is drawn by the library, so there is no file to add")
        if known is not None and known.origin == "shipped":
            if flags:
                raise UsageError(f"the catalog already says what {known.name} is; {', '.join('--' + f.replace('_', '-') for f in flags)} "
                                 "are for a file it does not know")
            sha, dest, created = store.put(path, expect=known.sha256, store=catalog.store)
            action = f"{known.name}: the file is the one the catalog pins"
        elif known is not None:                                      # one of the user's own
            sha = store.sha256_of(path)
            if sha == known.sha256:
                sha, dest, created = store.put(path, store=catalog.store)
                action = f"{known.name}: the file is the one your entry pins"
            elif not a.replace:
                raise IntegrityError(f"{path} hashes to {sha}, and your entry {known.name} pins {known.sha256}: it is not "
                                     "that file. `--replace` pins this one instead")
            else:
                sha, dest, created = store.put(path, store=catalog.store)
                raw = store.read_raw(catalog.store)["parts"][known.name]
                raw.update(sha256=sha, size=path.stat().st_size, source=a.source)
                store.add_entry(known.name, raw, catalog.store, replace=True)
                action = f"{known.name}: your entry now pins this file"
        else:
            if not NAME.match(a.entry):
                raise UsageError(f"an entry is named in lower case words joined by hyphens, not {a.entry!r}")
            sha, dest, created = store.put(path, store=catalog.store)
            store.add_entry(a.entry, _new_entry(a, sha, path.stat().st_size), catalog.store)
            action = f"{a.entry}: a new entry in your store"
        store.record_file(sha, a.entry, "add", a.source, catalog.store)
    except IntegrityError as e:
        return _failed(e, FAIL, "refused: not the file that is pinned")
    except LibraryError as e:
        raise UsageError(str(e)) from None
    text = f"{action}\n  {'stored' if created else 'already stored'} as {dest}\n  sha256 {sha}"
    return Result(OK, {"entry": a.entry, "sha256": sha, "path": str(dest), "created": created, "store": str(catalog.store)},
                  text, f"added {a.entry}", [str(dest)])


def cmd_lib_fetch(a) -> Result:
    catalog = load()
    entries = []
    for name in dict.fromkeys(a.entries):
        try:
            entry = catalog.get(name)
        except LibraryError as e:
            raise UsageError(str(e)) from None
        ok, why = fetch_ruling(entry)
        if not ok:
            raise UsageError(why)
        entries.append(entry)
    results, lines, states = [], [], []
    for entry in entries:                       # every entry is checked before the first byte is downloaded
        try:
            sha, dest, created = store.download(entry.url, entry.sha256, catalog.store)
        except IntegrityError as e:
            results.append({"entry": entry.name, "state": "FAIL", "error": str(e)})
            lines.append(f"  FAIL      {entry.name}: {e}")
            states.append("FAIL")
            continue
        except Unreachable as e:
            results.append({"entry": entry.name, "state": "UNCHECKED", "error": str(e)})
            lines.append(f"  UNCHECKED {entry.name}: {e}")
            states.append("UNCHECKED")
            continue
        if created:
            store.record_file(sha, entry.name, "fetch", entry.source, catalog.store, url=entry.url)
        results.append({"entry": entry.name, "state": "PASS", "sha256": sha, "path": str(dest), "downloaded": created})
        lines.append(f"  PASS      {entry.name}: " + (f"downloaded to {dest}" if created else f"already in your store ({dest})"))
        states.append("PASS")
    code = cmdbase.verdict(states)
    credit = sorted({e.attribution for e in entries if e.attribution})
    head = f"fetch: {states.count('PASS')} of {len(entries)} in your store ({catalog.store})"
    text = "\n".join([head] + lines + [f"  credit    {c}" for c in credit])
    return Result(code, {"fetched": results, "store": str(catalog.store)}, text,
                  f"{states.count('PASS')} of {len(entries)} fetched",
                  [r["path"] for r in results if r.get("downloaded")])


# ─── check ───────────────────────────────────────────────────────────────────

def cmd_lib_check(a) -> Result:
    catalog = load()
    if a.slug:
        cmdbase.project(a.slug)
        rows = check.check_project(a.slug, catalog)
        what = f"{a.slug}/bought/ against its sidecars and the catalog"
    else:
        rows = check.check_store(catalog)
        what = f"the store {catalog.store} against the catalog's pins"
    counts = {s: sum(r["state"] == s for r in rows) for s in ("PASS", "FAIL", "UNCHECKED", "N/A")}
    code = cmdbase.verdict(r["state"] for r in rows)
    tally = ", ".join(f"{n} {s}" for s, n in counts.items() if n)
    text = "\n".join([f"{what}: {tally}"] + cmdbase.rows_text(rows, a.all))
    return Result(code, {"project": a.slug, "rows": rows, "summary": counts, "store": str(catalog.store)}, text,
                  f"{tally}")


# ─── The options ─────────────────────────────────────────────────────────────

def _ls_arguments(p) -> None:
    p.add_argument("query", nargs="?", help="only the entries whose name, title, vendor or part number holds this text")
    p.add_argument("--kind", choices=KINDS, help="only generators, STEP files or bd_warehouse parts")


def _info_arguments(p) -> None:
    p.add_argument("entry")


def _add_arguments(p) -> None:
    p.add_argument("entry", help="a catalog entry (its file is checked against the pin), or a new name for a file of your own")
    p.add_argument("file", metavar="FILE", help="the STEP you downloaded")
    p.add_argument("--source", required=True, help="the page the file came from")
    p.add_argument("--replace", action="store_true", help="pin this file for one of your own entries that pins another")
    new = p.add_argument_group("for a file the catalog does not know (a new entry in your store)")
    new.add_argument("--title")
    new.add_argument("--vendor")
    new.add_argument("--pn", help="the vendor's part number")
    new.add_argument("--licence", help="its licence (default unknown, which `fetch` never downloads)")
    new.add_argument("--attribution", help="the credit its licence asks for")
    new.add_argument("--material", help="a key of `cad tables materials`")
    new.add_argument("--mass-g", type=float, help="grams, with --mass-source")
    new.add_argument("--mass-source")
    new.add_argument("--max-temp-c", type=float, help="degrees C, with --max-temp-source")
    new.add_argument("--max-temp-source")
    new.add_argument("--geometry", choices=bought.GEOMETRIES,
                     help="exact only when the solid is the real shape and a stiffness rule may stand on it "
                          "(default envelope)")
    new.add_argument("--datum-move", metavar="X,Y,Z", help="mm that take the file's origin to the part's frame")
    new.add_argument("--datum-turn", metavar="RX,RY,RZ", help="degrees, applied before the move")
    new.add_argument("--unverified", action="store_true", help="its dimensions are not confirmed: the provenance rule says UNCHECKED")


def _use_arguments(p) -> None:
    p.add_argument("slug")
    p.add_argument("entry")
    p.add_argument("params", nargs="*", metavar="KEY=VALUE", help="what the entry lets you choose (`cad lib info ENTRY`)")
    p.add_argument("--as", dest="name", metavar="NAME", help="the name in bought/ (default: the entry's, with _ for -)")
    p.add_argument("--replace", action="store_true", help="write a part the library copied in before again")


def _check_arguments(p) -> None:
    p.add_argument("slug", nargs="?", help="a project to check its bought/ against; without it, the store")
    p.add_argument("--all", action="store_true", help="show passing rows too")


def _fetch_arguments(p) -> None:
    p.add_argument("entries", nargs="+", metavar="ENTRY")


ARGUMENTS = {"lib ls": _ls_arguments, "lib info": _info_arguments, "lib add": _add_arguments,
             "lib use": _use_arguments, "lib check": _check_arguments, "lib fetch": _fetch_arguments}

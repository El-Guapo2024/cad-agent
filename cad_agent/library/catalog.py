"""The catalog: what the library holds, read and checked, with where every number came from.

Two files make the catalog, and a part may be in either:

    cad_agent/library/catalog.toml    what the repo ships. Written by hand, one `[parts.<name>]` table for each
                                      part, so that every number can sit beside the page it was read from.
    <store>/library.json              the user's own entries, which `cad lib add` writes, and the record of
                                      what the store holds and where each file came from. Machine written.

The store is `bought.library_dir()`: $CAD_LIBRARY, else ~/.cad-agent/library. Reading either file does not import
the CAD kernel, and neither does anything else in this module, which is why `cad lib ls` answers at once.

An entry is one of three kinds:

    generator     geometry the repo draws itself, in cad_agent/library/gen/. `use` writes a small module into the
                  project that calls the generator with the numbers written out, so the project holds every number
                  its part was built from. Free to copy: the model is the repo's own and the numbers are facts.
    step          a file somebody else made. It is never in the repo. The catalog pins where it can be had (`url`)
                  and what it must hash to (`sha256`); `fetch` downloads it into the store where its licence lets
                  the repo do that, and `add` takes one the user downloaded by hand and checks it against the pin.
    bd_warehouse  geometry another open-source package draws (Apache-2.0), when the optional `fasteners` extra is
                  installed. The project gets a module that calls it.

What an entry says, and why each field is a field
-------------------------------------------------
    title, vendor, pn, licence, attribution    what it is and under what terms (a CC-BY file must be credited, so
                                               `attribution` goes into the sidecar `use` writes, for the BOM)
    source, docs                               where the numbers came from, in words, and the https URLs read
    geometry                                   "exact" or "envelope": whether a stiffness rule may stand on the solid
    verified                                   false for a part whose dimensions nobody has checked against the
                                               maker's own drawing: the provenance rule then says UNCHECKED
    material, max_temp_c + max_temp_source     what the rules of step 6 read; each is left out unless a source says it
    mass                                       one of four forms, below, always with its source
    datum                                      where the vendor put the origin, as {move, turn} (step entries)
    [dims]                                     every number the generator draws from, each with its source:
                                               `width = { value = 12.0, source = "table 3.81: WR 12" }`
    [model]                                    what the generator does that no source says (a clearance gap): plain
                                               values, because they are choices and not dimensions
    [params]                                   what the user may change when copying it (a length), with its limits

A mass is one of
    { g = 50.0, source }                            a part that weighs one thing
    { per_m_g = 650.0, param = "length", source }   per metre of a parameter (a rail, an extrusion)
    { section_mm2 = 167.8, material = "aluminium", param = "length", source }
                                                    a section's area times materials.py's density, per metre
    { by = "length", table = { "40" = 230.0 }, source }
                                                    a table, keyed by the value of a parameter

and `use` turns it into the sidecar's `mass_g` and `mass_source` for the length it was asked for, because a bought
body's mass is what its sidecar declares (bought.py): the mass of a 300 mm rail is not the mass of a 150 mm one.

A value no source gives is not in the entry. What needs it is then UNCHECKED, by design, and says so.
"""
from __future__ import annotations

import difflib
import json
import math
import re
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .. import bought, materials

CATALOG = Path(__file__).with_name("catalog.toml")
STORE_FILE = "library.json"
FORMAT = 1
KINDS = ("generator", "step", "bd_warehouse")
GEN_PACKAGE = "cad_agent.library.gen."          # a generator entry draws with one of ours
NAME = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")           # an entry: mgn12-rail
PART_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")          # a bought part in a project: rail_x
HEX64 = re.compile(r"^[0-9a-f]{64}$")
TARGET = re.compile(r"^[A-Za-z_][\w.]*:[A-Za-z_]\w*$")           # module:function
MASS_FORMS = ("g", "per_m_g", "section_mm2", "by")

# The licences under which the repo downloads a file for the user and keeps it in their store. Each lets a copy be
# made, and the ones that ask for credit are met by `attribution`, which `use` copies into the sidecar. Any other
# licence (a vendor's terms, "unknown", a non-commercial one) is a file the user gets by hand, from the vendor.
OPEN_LICENCES = frozenset({
    "CC0-1.0", "CC-BY-3.0", "CC-BY-4.0", "CC-BY-SA-3.0", "CC-BY-SA-4.0", "MIT", "Apache-2.0", "BSD-2-Clause",
    "BSD-3-Clause", "LGPL-2.1-or-later", "LGPL-3.0-or-later", "GPL-3.0-or-later", "Unlicense"})


class LibraryError(ValueError):
    """A request the library cannot do as asked: an unknown entry or parameter, a name already taken. Exit 3."""


class IntegrityError(LibraryError):
    """A file that is not the one a pin names, or a store that no longer holds what it should. Exit 1."""


class Unreachable(LibraryError):
    """A download that did not happen, so nothing could be settled. Exit 2."""


@dataclass(frozen=True)
class Entry:
    name: str
    origin: str                      # "shipped" (catalog.toml) | "store" (the user's library.json)
    kind: str
    title: str
    licence: str
    geometry: str                    # "exact" | "envelope"
    verified: bool
    source: str
    docs: tuple
    vendor: str | None = None
    pn: str | None = None
    attribution: str | None = None
    material: str | None = None
    max_temp_c: float | None = None
    max_temp_source: str | None = None
    mass: dict | None = None
    datum: dict | None = None
    url: str | None = None
    sha256: str | None = None
    size: int | None = None
    generator: str | None = None
    requires: str | None = None
    dims: dict = field(default_factory=dict)       # {name: {"value", "source"}}
    model: dict = field(default_factory=dict)      # {name: value}
    params: dict = field(default_factory=dict)     # {name: {"default", "min", "max", "choices", "unit", "source"}}
    unconfirmed: tuple = ()          # what a maker's drawing does not give and the geometry still needs
    notes: tuple = ()
    problems: tuple = ()

    def as_dict(self) -> dict:
        d = asdict(self)
        for key in ("docs", "unconfirmed", "notes", "problems"):
            d[key] = list(d[key])
        return d


@dataclass
class Catalog:
    entries: dict                    # {name: Entry}
    problems: list                   # what is wrong in either file, one line each
    store: Path
    files: dict                      # {sha256: {"entry", "how", "source", ...}}: what the store records of its files

    def get(self, name: str) -> Entry:
        if name in self.entries:
            return self.entries[name]
        near = difflib.get_close_matches(name, self.entries, n=3)
        hint = f"; did you mean {', '.join(near)}?" if near else ""
        raise LibraryError(f"no library entry {name!r}{hint} (`cad lib ls` lists them)")


# ─── Reading ─────────────────────────────────────────────────────────────────

def _text(v) -> str | None:
    return v.strip() if isinstance(v, str) and v.strip() else None


def _number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _url(v) -> bool:
    return isinstance(v, str) and v.startswith("https://") and " " not in v


def _vector(v, what: str, faults: list) -> tuple | None:
    if isinstance(v, (list, tuple)) and len(v) == 3 and all(_number(x) for x in v):
        return tuple(float(x) for x in v)
    faults.append(f"{what} must be three numbers, got {v!r}")
    return None


def _datum(raw, faults: list) -> dict | None:
    if raw is None:
        return None
    if not isinstance(raw, dict) or set(raw) - {"move", "turn"}:
        faults.append(f"datum must be {{move, turn}}, got {raw!r}")
        return None
    out = {k: _vector(raw.get(k, [0, 0, 0]), f"datum {k}", faults) for k in ("move", "turn")}
    return None if None in out.values() else {k: list(v) for k, v in out.items()}


def _dims(raw, faults: list) -> dict:
    out = {}
    for key, d in (raw or {}).items():
        if not isinstance(d, dict) or set(d) - {"value", "source"} or "value" not in d:
            faults.append(f"dims.{key} must be {{value, source}}, got {d!r}")
        elif _text(d.get("source")) is None:
            faults.append(f"dims.{key} has no source: a number nothing cites is left out of the entry")
        else:
            v = d["value"]
            flat = [x for r in v for x in (r if isinstance(r, list) else [r])] if isinstance(v, list) else [v]
            if not flat or not all(_number(x) for x in flat):
                faults.append(f"dims.{key} must be a number or lists of numbers, got {v!r}")
            else:
                out[key] = {"value": v, "source": d["source"].strip()}
    return out


def _params(raw, faults: list) -> dict:
    out = {}
    for key, p in (raw or {}).items():
        if not isinstance(p, dict) or set(p) - {"default", "min", "max", "choices", "unit", "source"} or "default" not in p:
            faults.append(f"params.{key} must have a default (and may have min, max, choices, unit, source), got {p!r}")
            continue
        choices = p.get("choices")
        if choices is not None and not (isinstance(choices, list) and choices and p["default"] in choices):
            faults.append(f"params.{key}: choices must be a list that holds the default")
            continue
        if choices is None and not _number(p["default"]):
            faults.append(f"params.{key}: the default must be a number (or give choices)")
            continue
        lo, hi = p.get("min"), p.get("max")
        if any(x is not None and not _number(x) for x in (lo, hi)) or (
                lo is not None and hi is not None and lo > hi) or (
                choices is None and ((lo is not None and p["default"] < lo) or (hi is not None and p["default"] > hi))):
            faults.append(f"params.{key}: min and max must be numbers around the default")
            continue
        out[key] = {"default": p["default"], "min": lo, "max": hi, "choices": choices,
                    "unit": _text(p.get("unit")), "source": _text(p.get("source"))}
    return out


def _mass(raw, params: dict, faults: list) -> dict | None:
    if raw is None:
        return None
    if not isinstance(raw, dict) or _text(raw.get("source")) is None:
        faults.append("mass needs a source: a mass nothing cites is left out of the entry")
        return None
    forms = [f for f in MASS_FORMS if f in raw]
    if len(forms) != 1:
        faults.append(f"mass takes exactly one of {', '.join(MASS_FORMS)}, got {', '.join(forms) or 'none'}")
        return None
    form, need = forms[0], {"g": (), "per_m_g": ("param",), "section_mm2": ("param", "material"), "by": ("table",)}[forms[0]]
    extra = set(raw) - {form, "source", "param", "material", "table"}
    if extra or any(k not in raw for k in need):
        faults.append(f"mass form {form} takes {', '.join(need) or 'nothing more'} (and a source), got {sorted(raw)}")
        return None
    if form == "by":
        table = raw["table"]
        if raw["by"] not in params or not isinstance(table, dict) or not table or not all(_number(v) and v > 0 for v in table.values()):
            faults.append("mass.by must name a parameter and give a table of positive masses")
            return None
        choices = params[raw["by"]]["choices"]
        if choices is None:
            faults.append(f"mass.by names {raw['by']!r}, which has no choices to tabulate")
            return None
        missing = [str(c) for c in choices if str(c) not in table]
        if missing:
            faults.append(f"mass.table has no mass for {', '.join(missing)}, which the parameter allows")
            return None
    elif not _number(raw[form]) or raw[form] <= 0:
        faults.append(f"mass.{form} must be a positive number")
        return None
    if "param" in raw and raw["param"] not in params:
        faults.append(f"mass.param {raw['param']!r} is not a parameter of the entry")
        return None
    if "material" in raw and materials.prop(raw["material"], "density_g_cm3") is None:
        faults.append(f"mass.material {raw['material']!r} is not in materials.py")
        return None
    return dict(raw)


def parse_entry(name: str, raw: dict, origin: str) -> Entry:
    """One entry, checked. A fault is in `problems` (the entry stays listed, flagged) and never an exception, so that
    a mistake in the user's own file costs one entry and not the whole listing."""
    faults: list = []
    if not NAME.match(name):
        faults.append(f"the name {name!r} must be lower case words joined by hyphens")
    known = {"title", "kind", "licence", "geometry", "verified", "source", "docs", "vendor", "pn", "attribution",
             "material", "max_temp_c", "max_temp_source", "mass", "datum", "url", "sha256", "size", "generator",
             "requires", "dims", "model", "params", "unconfirmed", "notes"}
    unknown = sorted(set(raw) - known)
    if unknown:
        faults.append(f"unknown key {', '.join(unknown)}")
    kind = raw.get("kind")
    if kind not in KINDS:
        faults.append(f"kind must be one of {', '.join(KINDS)}, got {kind!r}")
    geometry = raw.get("geometry", "envelope")
    if geometry not in bought.GEOMETRIES:
        faults.append(f"geometry must be one of {', '.join(bought.GEOMETRIES)}, got {geometry!r}")
        geometry = "envelope"
    title, source = _text(raw.get("title")), _text(raw.get("source"))
    licence = _text(raw.get("licence")) or "unknown"
    if title is None:
        faults.append("title is missing")
    if source is None:
        faults.append("source is missing: say where the numbers or the file came from")
    docs = raw.get("docs", [])
    if not (isinstance(docs, list) and all(_url(u) for u in docs)):
        faults.append("docs must be a list of https URLs")
        docs = []
    if origin == "shipped" and not docs:
        faults.append("a shipped entry cites at least one page it was read from (docs)")
    sha, url = raw.get("sha256"), raw.get("url")
    if sha is not None and not (isinstance(sha, str) and HEX64.match(sha)):
        faults.append(f"sha256 must be 64 lower-case hexadecimal characters, got {sha!r}")
        sha = None
    if url is not None and not _url(url):
        faults.append(f"url must be an https URL, got {url!r}")
        url = None
    size = raw.get("size")
    if size is not None and not (isinstance(size, int) and not isinstance(size, bool) and size > 0):
        faults.append("size must be a whole number of bytes")
        size = None
    generator, requires = raw.get("generator"), _text(raw.get("requires"))
    if kind in ("generator", "bd_warehouse"):
        prefix = GEN_PACKAGE if kind == "generator" else "bd_warehouse."
        if not (isinstance(generator, str) and TARGET.match(generator) and generator.startswith(prefix)):
            faults.append(f"generator must be `{prefix}module:function`, got {generator!r}")
            generator = None
        if kind == "bd_warehouse" and requires != "bd_warehouse":
            faults.append("a bd_warehouse entry requires `bd_warehouse`")
    elif generator is not None:
        faults.append("only a generator or bd_warehouse entry has a generator")
        generator = None
    if kind == "step" and sha is None:
        faults.append("a step entry pins the sha256 of the file it stands for")
    temp, temp_source = raw.get("max_temp_c"), _text(raw.get("max_temp_source"))
    if temp is not None and (not _number(temp) or temp_source is None):
        faults.append("max_temp_c is a number of degrees C and needs a max_temp_source")
        temp = temp_source = None
    elif temp is None and temp_source is not None:
        faults.append("max_temp_source without a max_temp_c")
    material = _text(raw.get("material"))
    if material is not None and materials.key(material) is None:
        faults.append(f"material {material!r} is not in materials.py")
        material = None
    attribution = _text(raw.get("attribution"))
    if licence.startswith("CC-BY") and attribution is None:
        faults.append(f"a {licence} entry needs an attribution: the licence asks for the credit")
    params = _params(raw.get("params"), faults)
    model = raw.get("model") or {}
    if not isinstance(model, dict):
        faults.append("model must be a table of values")
        model = {}
    unconfirmed = raw.get("unconfirmed", [])
    verified = raw.get("verified", True)
    if not isinstance(verified, bool) or not (isinstance(unconfirmed, list) and all(_text(u) for u in unconfirmed)):
        faults.append("verified is true or false, and unconfirmed a list of what is not confirmed")
        unconfirmed, verified = [], True
    if unconfirmed and verified:
        faults.append("an entry with something unconfirmed is verified = false")
    notes = raw.get("notes", [])
    if not (isinstance(notes, list) and all(_text(n) for n in notes)):
        faults.append("notes must be a list of text")
        notes = []
    return Entry(
        name=name, origin=origin, kind=kind if kind in KINDS else "step", title=title or name, licence=licence,
        geometry=geometry, verified=verified, source=source or "", docs=tuple(docs), vendor=_text(raw.get("vendor")),
        pn=_text(raw.get("pn")), attribution=attribution, material=material, max_temp_c=temp,
        max_temp_source=temp_source, mass=_mass(raw.get("mass"), params, faults),
        datum=_datum(raw.get("datum"), faults), url=url, sha256=sha, size=size, generator=generator,
        requires=requires, dims=_dims(raw.get("dims"), faults), model=dict(model), params=params,
        unconfirmed=tuple(unconfirmed), notes=tuple(notes), problems=tuple(faults))


def shipped() -> dict:
    """The entries catalog.toml holds. A catalog the repo ships that does not parse is a bug, so it raises."""
    data = tomllib.loads(CATALOG.read_text(encoding="utf-8"))
    return {name: parse_entry(name, raw, "shipped") for name, raw in data.get("parts", {}).items()}


def read_store(store: Path) -> tuple[dict, dict, list]:
    """(the user's entries, the files record, problems) from <store>/library.json. A file that cannot be read is a
    problem and not an exception: the shipped entries still list, and `cad lib check` says what is wrong."""
    path = store / STORE_FILE
    if not path.exists():
        return {}, {}, []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("format") != FORMAT:
            raise ValueError(f"format must be {FORMAT}")
        parts, files = data.get("parts", {}), data.get("files", {})
        if not (isinstance(parts, dict) and isinstance(files, dict)):
            raise ValueError("parts and files must be objects")
    except (OSError, ValueError) as e:
        return {}, {}, [f"{path} cannot be read: {e}"]
    return {name: parse_entry(name, raw, "store") for name, raw in parts.items() if isinstance(raw, dict)}, files, []


def load(store: Path | None = None) -> Catalog:
    """The shipped entries and the user's, with the faults of both. A user entry never takes the place of a shipped one
    (the shipped pin is the catalog's), so a name in both is a fault of the user's file and the shipped one stands."""
    store = Path(store) if store is not None else bought.library_dir()
    entries, problems = dict(shipped()), []
    mine, files, faults = read_store(store)
    problems += faults
    for name, entry in mine.items():
        if name in entries:
            problems.append(f"{store / STORE_FILE}: {name} is also a shipped entry, and the shipped one stands")
        else:
            entries[name] = entry
    for name, entry in entries.items():
        problems += [f"{name}: {p}" for p in entry.problems]
    return Catalog(entries=entries, problems=problems, store=store, files=files)


# ─── What an entry becomes in a project ──────────────────────────────────────

def resolve_params(entry: Entry, given: dict) -> dict:
    """The parameters a copy is made with: the user's over the defaults, each held to its type and limits."""
    unknown = sorted(set(given) - set(entry.params))
    if unknown:
        have = ", ".join(entry.params) or "none"
        raise LibraryError(f"{entry.name} has no parameter {', '.join(unknown)} (parameters: {have})")
    out = {}
    for key, spec in entry.params.items():
        v = given.get(key, spec["default"])
        unit = f" {spec['unit']}" if spec["unit"] else ""
        if spec["choices"] is not None:
            if isinstance(v, bool) or v not in spec["choices"]:
                raise LibraryError(f"{key} must be one of {', '.join(str(c) for c in spec['choices'])}, got {v!r}")
            v = spec["choices"][spec["choices"].index(v)]           # 40.0 is the choice 40: a table is keyed by it
        else:
            if not _number(v):
                raise LibraryError(f"{key} must be a number" + (f" of {spec['unit']}" if spec["unit"] else "") + f", got {v!r}")
            v = float(v)
            if (spec["min"] is not None and v < spec["min"]) or (spec["max"] is not None and v > spec["max"]):
                lo = "" if spec["min"] is None else f"{spec['min']:g}"
                hi = "" if spec["max"] is None else f"{spec['max']:g}"
                why = f" ({spec['source']})" if spec["source"] else ""
                raise LibraryError(f"{key} must be from {lo} to {hi}{unit}, got {v:g}{why}")
        out[key] = v
    return out


def arguments(entry: Entry, params: dict) -> dict:
    """What the generator is called with: the dimensions (each with a source), the model's own choices, the params."""
    out = {key: d["value"] for key, d in entry.dims.items()}
    out.update(entry.model)
    out.update(params)
    return out


def mass_of(entry: Entry, params: dict) -> tuple[float | None, str | None]:
    """(grams, where that came from) for the copy `params` describes, or (None, None) when the entry declares none."""
    m = entry.mass
    if not m:
        return None, None
    src = m["source"]
    if "g" in m:
        return m["g"], src
    if "by" in m:
        key = params[m["by"]]
        return m["table"][str(key)], f"{src} (for {m['by']} {key})"
    length = params[m["param"]]
    metres = length / 1000.0
    if "per_m_g" in m:
        grams = m["per_m_g"] * metres
        return round(grams, 3), f"{src}; {m['per_m_g']:g} g/m x {metres:g} m = {grams:.1f} g"
    rho = materials.prop(m["material"], "density_g_cm3")
    per_m = m["section_mm2"] * rho.value               # mm^2 x g/cm^3 is grams per metre
    grams = per_m * metres
    return round(grams, 3), (f"{src}; {m['section_mm2']:g} mm2 x {rho.value:g} g/cm3 ({materials.key(m['material'])}, "
                             f"materials.py) = {per_m:.1f} g/m, x {metres:g} m = {grams:.1f} g")


def sidecar(entry: Entry, params: dict, store_note: str | None = None) -> dict:
    """The bought contract's keys (bought.py) for a copy of this entry, as the JSON the sidecar holds.

    `sha256` is added by the caller, who has the file; `library_params` is ours (not a contract key), so that
    `lib check` can make the same copy again and say what the catalog has changed since.
    """
    side = {"source": entry.source + (f" {store_note}" if store_note else ""), "vendor": entry.vendor,
            "verified": entry.verified, "library": entry.name, "licence": entry.licence, "geometry": entry.geometry}
    if entry.pn:
        side["pn"] = entry.pn
    if entry.attribution:
        side["attribution"] = entry.attribution
    if entry.material:
        side["material"] = entry.material
    grams, why = mass_of(entry, params)
    if grams is not None:
        side["mass_g"], side["mass_source"] = grams, why
    if entry.max_temp_c is not None:
        side["max_temp_c"], side["max_temp_source"] = entry.max_temp_c, entry.max_temp_source
    if entry.datum and any(entry.datum["move"] + entry.datum["turn"]):
        side["datum"] = entry.datum
    if entry.kind != "step":
        side["library_params"] = params
    return side


def fetch_ruling(entry: Entry) -> tuple[bool, str]:
    """Whether `fetch` may download this entry, and if not, what to do instead. Nothing is fetched that cannot be
    checked, and nothing whose licence does not let the repo hand it over."""
    if entry.kind != "step":
        return False, f"{entry.name} is drawn here, so there is nothing to download"
    if not entry.url:
        return False, f"{entry.name} has no download URL: it is a file you add by hand (`cad lib add`)"
    if not entry.sha256:
        return False, f"the catalog pins no sha256 for {entry.name}, and nothing is downloaded that cannot be checked"
    if entry.licence not in OPEN_LICENCES:
        page = entry.docs[0] if entry.docs else entry.url
        return False, (f"{entry.name} is under {entry.licence}, which does not let the repo fetch it for you: "
                       f"download it by hand from {page} and run `cad lib add {entry.name} FILE --source URL`")
    return True, ""

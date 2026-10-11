"""Bought parts: geometry that came from a vendor, never from memory.

A bought part enters a project one of two ways, and both record where the
geometry came from:

  STEP      the vendor's own file, dropped in projects/<slug>/bought/.
            Authoritative. Nothing to transcribe, so nothing to get wrong.

  MEASURED  a small Python module in the same directory declaring dimensions
            with a SOURCE naming the drawing, datasheet page, or calliper
            reading they came from. Used when no STEP exists.

Either kind may also declare VERIFIED = False, meaning the numbers came from a
listing that did not publish them and must be confirmed with callipers when
the part arrives. Unverified geometry is reported by every tool that touches
it and fails `done_check`, because a dimension nobody checked is not a
dimension the gates can stand on.

The rule this enforces: a remembered bolt circle is how an assembly passes
every check and still does not fit. A bought part with no provenance is
rejected rather than trusted.

The contract (step 6)
---------------------
What else a bought part may declare, for the rules that read mass, temperature and stiffness. The
keys go in the sidecar `<name>.json` beside the STEP, or beside a module; a module may also set them
as UPPER_CASE constants (`MASS_G = 12.0`), which win over the sidecar's. A key that is not there is
unknown, and a rule that needs it is UNCHECKED: nothing is defaulted to look like a measurement.

    source, vendor, verified    as before (a sidecar may now give a module's too)
    mass_g, mass_source         grams, and where the mass came from; a mass with no source is not used
    material                    a key of materials.py ("petg", "aluminium"), for density and stiffness
    max_temp_c, max_temp_source the highest temperature it may sit at, in degrees C, and its datasheet
    geometry                    "exact" or "envelope" (the default). Only exact geometry may give
                                stiffness: a motor's STEP or a box standing for a part is an envelope
    datum                       {"move": [x, y, z], "turn": [rx, ry, rz]}: the rigid move, in mm and
                                degrees (Rx . Ry . Rz, as placements.toml turns a body, about the
                                origin), that takes the file's own coordinates to the part's frame.
                                bought_solid applies it, so an assembly does not need to know where
                                the vendor put the origin
    sha256                      the hash of the file in bought/ that defines the geometry (the STEP's
                                bytes, or the module's); the provenance rule FAILs when the file no
                                longer hashes to it
    pn, licence, library        part number, licence, and the library entry it was copied from

`bought_spec` reads and checks them (a fault is in `problems`, never an exception), and the provenance
rule turns every fault and the hash into rows. `bought_solid(slug, name, **params)` loads the
geometry: a generator module takes `params` over its PARAMS, a STEP takes none, and the solid it
returns carries a tag (`tag_of`) naming the bought part it is, which survives the moves an assembly
makes and tells bodies.describe what a body is whatever it is called.

The vendor STEPs that may not go in the public repo live in a store of the user's, `library_dir()`:
$CAD_LIBRARY, else ~/.cad-agent/library. A project copies in what it uses, so verify, the build cache
and CI read only the project.

Reading a STEP's declaration (`bought_spec`, `library_dir`, `register_step`) does not import the CAD
kernel, which is why `cad lib` can answer without waiting for it; loading geometry (`load_bought`,
`bought_info`) imports it when it is called, and so does running a measured module.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from .state import _load_module, project_dir, why


class MissingProvenance(ValueError):
    """A measured part that does not say where its dimensions came from."""


LIBRARY_ENV = "CAD_LIBRARY"
GEOMETRIES = ("exact", "envelope")      # envelope first in meaning: it is what an undeclared part is
TAG = "_cad_bought"                     # the attribute bought_solid sets on the solid it returns
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
CONTRACT_KEYS = ("source", "vendor", "verified", "mass_g", "mass_source", "material", "max_temp_c",
                 "max_temp_source", "geometry", "datum", "sha256", "pn", "licence", "library")


def library_dir() -> Path:
    """The user's store of vendor STEP files: $CAD_LIBRARY, else ~/.cad-agent/library. It is read
    where it is and never made here; the library (step 6, piece A) fills it."""
    raw = os.environ.get("CAD_LIBRARY")          # spelt out so test_warm sees it and holds warm.ENV_PASS to it
    return Path(raw).expanduser() if raw else Path.home() / ".cad-agent" / "library"


def bought_dir(slug: str, create: bool = False) -> Path:
    """The folder of bought parts; made only for a write, so that listing them in a project
    nobody can write to (a read-only checkout) is a listing and not a PermissionError."""
    d = project_dir(slug) / "bought"
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def list_bought(slug: str) -> list[dict]:
    """Every bought part, with its kind and provenance."""
    out = []
    d = bought_dir(slug)
    for p in sorted(d.iterdir()) if d.is_dir() else []:
        if p.name.startswith("."):
            continue                   # .DS_Store, and ._x.step: a Mac's resource fork beside a file copied off a stick
        if p.suffix.lower() in (".step", ".stp"):
            meta = _sidecar(p)
            out.append({"name": p.stem, "kind": "STEP", "file": p.name,
                        "source": meta.get("source", "UNRECORDED"),
                        "vendor": meta.get("vendor"),
                        "verified": meta.get("verified", True)})
        elif p.suffix == ".py" and not p.stem.startswith("_"):
            try:
                mod = _load(p)
            except Exception as e:     # still listed, as unconfirmed, so `ls` shows it and the gates say why
                out.append({"name": p.stem, "kind": "MEASURED", "file": p.name,
                            "source": f"cannot load: {why(e)}", "vendor": None, "verified": False})
                continue
            side = _sidecar(p)             # a generated module keeps its record there (see the contract)
            out.append({"name": p.stem, "kind": "MEASURED", "file": p.name,
                        "source": getattr(mod, "SOURCE", side.get("source", "UNRECORDED")),
                        "vendor": getattr(mod, "VENDOR", side.get("vendor")),
                        "verified": bool(getattr(mod, "VERIFIED", side.get("verified", True)))})
    return out


def _sidecar(step_path: Path) -> dict:
    j = step_path.with_suffix(".json")
    try:
        data = json.loads(j.read_text()) if j.exists() else {}
    except ValueError:
        return {}                      # unreadable: no source on record, which load_bought refuses
    return data if isinstance(data, dict) else {}


def _load(path: Path):
    return _load_module(path)             # from source: see state._load_module for why


def register_step(slug: str, name: str, step_path: str, source: str,
                  vendor: str | None = None, verified: bool = True) -> Path:
    """Copy a vendor STEP into the project and record where it came from."""
    src = Path(step_path).expanduser()
    if not src.exists():
        raise FileNotFoundError(f"no STEP at {src}")
    if not source.strip():
        raise MissingProvenance("source is required: the page the file came from")
    dest = bought_dir(slug, create=True) / f"{name}{src.suffix.lower()}"
    dest.write_bytes(src.read_bytes())
    dest.with_suffix(".json").write_text(json.dumps(
        {"source": source, "vendor": vendor, "verified": verified,
         "original": src.name}, indent=1))
    return dest


def load_bought(slug: str, name: str, **params):
    """Return the solid for a bought part, by either route.

    A module's `params` replace its PARAMS for this call (a generator takes a length, say); a STEP is a
    fixed file and takes none. The datum, if the part declares one, is applied, and the solid carries a
    tag naming the part (see the contract in the module docstring).
    """
    from build123d import import_step
    d = bought_dir(slug)
    for ext in (".step", ".stp"):
        p = d / f"{name}{ext}"
        if p.exists():
            meta = _sidecar(p)
            if not meta.get("source"):
                raise MissingProvenance(
                    f"{name}{ext} has no sidecar recording its source; "
                    "re-add it with register_step so the provenance is kept")
            if params:
                raise ValueError(f"{name}{ext} is a STEP file, which takes no parameters "
                                 f"(got {', '.join(sorted(params))})")
            return _finish(import_step(str(p)), slug, name, _make_spec(name, "STEP", p, meta))
    p = d / f"{name}.py"
    if p.exists():
        mod = _load(p)
        declared = _declared(p, mod)
        source = str(declared.get("source") or "").strip()
        if not source:
            raise MissingProvenance(
                f"{name}.py declares no SOURCE; a measured part must name the "
                "drawing, datasheet page or calliper reading it came from")
        defaults = dict(getattr(mod, "PARAMS", {}))
        unknown = sorted(set(params) - set(defaults))
        if unknown:
            raise ValueError(f"{name}.py has no parameter {', '.join(unknown)} "
                             f"(params: {', '.join(sorted(defaults)) or 'none'})")
        return _finish(mod.build(**{**defaults, **params}), slug, name, _make_spec(name, "MEASURED", p, declared))
    raise FileNotFoundError(
        f"no bought part {name!r} in {d}; add a vendor STEP with register_step "
        "or write a measured module with a SOURCE")


# ─── The contract ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class BoughtSpec:
    """What a bought part declares, checked. A value that did not hold is None (or the default), and
    why is in `problems`; the provenance rule reports each as a FAIL."""
    name: str
    kind: str                       # "STEP" | "MEASURED"
    file: str                       # the file in bought/ that defines the geometry
    source: str                     # "UNRECORDED" when it has none
    vendor: str | None
    verified: bool
    mass_g: float | None            # only when mass_source says where it came from
    mass_source: str | None
    material: str | None
    max_temp_c: float | None        # likewise with max_temp_source
    max_temp_source: str | None
    geometry: str                   # "exact" | "envelope"
    datum: dict | None              # {"move": (x, y, z), "turn": (rx, ry, rz)}; None: the identity
    sha256: str | None              # as declared, lower case
    pn: str | None
    licence: str | None
    library: str | None
    problems: tuple = ()

    def as_dict(self) -> dict:
        d = asdict(self)
        d["problems"] = list(self.problems)
        return d


def _declared(p: Path, mod=None) -> dict:
    """Everything a bought file declares, under the lower-case keys of the contract: the sidecar's,
    then a module's UPPER_CASE constants over them."""
    decl = dict(_sidecar(p))
    if mod is not None:
        for key in CONTRACT_KEYS:
            if hasattr(mod, key.upper()):
                decl[key] = getattr(mod, key.upper())
    return decl


def _number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _text(v) -> str | None:
    return v.strip() if isinstance(v, str) and v.strip() else None


def _datum(raw) -> tuple[dict | None, str | None]:
    """(the datum as {"move", "turn"} tuples or None for the identity, or a fault)."""
    if raw is None:
        return None, None
    if not isinstance(raw, dict):
        return None, f"datum must be {{move, turn}}, got {raw!r}"
    unknown = sorted(set(raw) - {"move", "turn"})
    if unknown:
        return None, f"datum has unknown key {', '.join(unknown)} (keys: move, turn)"
    out = {}
    for key in ("move", "turn"):
        v = raw.get(key, [0, 0, 0])
        if not (isinstance(v, (list, tuple)) and len(v) == 3 and all(_number(x) for x in v)):
            return None, f"datum {key} must be three numbers, got {v!r}"
        out[key] = tuple(float(x) for x in v)
    return (None if not any(out["move"] + out["turn"]) else out), None


def _make_spec(name: str, kind: str, p: Path, decl: dict) -> BoughtSpec:
    faults = []
    mass = mass_source = temp = temp_source = sha = None

    if decl.get("mass_g") is not None:
        if not _number(decl["mass_g"]) or decl["mass_g"] <= 0:
            faults.append(f"mass_g must be a positive number of grams, got {decl['mass_g']!r}")
        elif _text(decl.get("mass_source")) is None:
            faults.append("mass_g is declared without a mass_source: say where the mass came from "
                          "(it is not used until you do)")
        else:
            mass, mass_source = float(decl["mass_g"]), _text(decl["mass_source"])
    if decl.get("max_temp_c") is not None:
        if not _number(decl["max_temp_c"]) or not -273.15 < decl["max_temp_c"] < 10000:
            faults.append(f"max_temp_c must be a temperature in degrees C, got {decl['max_temp_c']!r}")
        elif _text(decl.get("max_temp_source")) is None:
            faults.append("max_temp_c is declared without a max_temp_source: name the datasheet "
                          "(it is not used until you do)")
        else:
            temp, temp_source = float(decl["max_temp_c"]), _text(decl["max_temp_source"])

    geometry = decl.get("geometry")
    if geometry is None:
        geometry = "envelope"
    elif geometry not in GEOMETRIES:
        faults.append(f"geometry must be one of {', '.join(GEOMETRIES)}, got {geometry!r}")
        geometry = "envelope"

    datum, fault = _datum(decl.get("datum"))
    if fault:
        faults.append(fault)

    if decl.get("sha256") is not None:
        pinned = decl["sha256"].strip().lower() if isinstance(decl["sha256"], str) else ""
        if _HEX64.fullmatch(pinned):
            sha = pinned
        else:
            faults.append(f"sha256 must be 64 hexadecimal characters, got {decl['sha256']!r}")

    text = {}
    for key in ("material", "pn", "licence", "library"):
        text[key] = _text(decl.get(key))
        if decl.get(key) is not None and text[key] is None:
            faults.append(f"{key} must be text, got {decl[key]!r}")

    return BoughtSpec(
        name=name, kind=kind, file=p.name, source=decl.get("source", "UNRECORDED"),
        vendor=decl.get("vendor"), verified=bool(decl.get("verified", True)),
        mass_g=mass, mass_source=mass_source, material=text["material"], max_temp_c=temp,
        max_temp_source=temp_source, geometry=geometry, datum=datum, sha256=sha, pn=text["pn"],
        licence=text["licence"], library=text["library"], problems=tuple(faults))


def bought_spec(slug: str, name: str) -> BoughtSpec:
    """What a bought part declares, read and checked; FileNotFoundError when there is no such part.

    It never raises for a bad declaration or a module that will not load: the fault is in `problems`,
    so that a listing and a rule can say what is wrong with the part and carry on with the rest.
    """
    d = bought_dir(slug)
    for ext in (".step", ".stp"):
        p = d / f"{name}{ext}"
        if p.exists():
            return _make_spec(name, "STEP", p, _declared(p))
    p = d / f"{name}.py"
    if p.exists():
        try:
            decl = _declared(p, _load(p))
        except Exception as e:             # listed as list_bought lists it: unconfirmed, with the reason as its source
            return _make_spec(name, "MEASURED", p, {"source": f"cannot load: {why(e)}", "verified": False})
        return _make_spec(name, "MEASURED", p, decl)
    raise FileNotFoundError(
        f"no bought part {name!r} in {d}; add a vendor STEP with register_step "
        "or write a measured module with a SOURCE")


def _finish(solid, slug: str, name: str, spec: BoughtSpec):
    """The solid in the part's own frame (its datum applied), tagged with what it is."""
    fault = next((f for f in spec.problems if f.startswith("datum")), None)
    if fault:                           # a datum we cannot read would leave the part where the vendor put it
        raise ValueError(f"bought part {name!r}: {fault}")
    if spec.datum:
        from .placements import location
        solid = solid.moved(location({**spec.datum, "about": (0.0, 0.0, 0.0)}))
    setattr(solid, TAG, {"project": slug, "name": name})
    return solid


def tag_of(solid) -> dict | None:
    """{"project", "name"} if `solid` is a bought part (or a move or copy of one), else None."""
    tag = getattr(solid, TAG, None)
    return tag if isinstance(tag, dict) and isinstance(tag.get("name"), str) else None


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pin_status(slug: str, name: str) -> tuple[str, str] | None:
    """(pinned, actual) sha256 of the file that defines a bought part, or None when it pins none."""
    spec = bought_spec(slug, name)
    if spec.sha256 is None:
        return None
    return spec.sha256, file_sha256(bought_dir(slug) / spec.file)


def bought_info(slug: str, name: str) -> dict:
    from .geom import bbox, volume
    solid = load_bought(slug, name)
    lo, hi = bbox(solid)
    rows = {r["name"]: r for r in list_bought(slug)}
    return {
        "name": name,
        "kind": rows.get(name, {}).get("kind"),
        "source": rows.get(name, {}).get("source"),
        "vendor": rows.get(name, {}).get("vendor"),
        "verified": rows.get(name, {}).get("verified", True),
        "bbox_mm": [round(hi[i] - lo[i], 3) for i in range(3)],
        "origin_mm": [round(v, 3) for v in lo],
        "volume_cm3": round(volume(solid) / 1000.0, 3),
    }


MEASURED_TEMPLATE = '''"""{name}: {vendor_line}

Bought part. The geometry below is an envelope for clearance checking, not a
model of the part: what the gates need to know is the space it occupies and
where it bolts down, and inventing detail beyond that only creates numbers
nobody checked.
"""
from build123d import Box, Cylinder, Pos

SOURCE = {source!r}
VENDOR = {vendor!r}
VERIFIED = {verified!r}

PARAMS = {params!r}


def build({args}):
    body = Box(length, width, height)
{holes}
    return body
'''


def register_measured(slug: str, name: str, length: float, width: float,
                      height: float, source: str, vendor: str | None = None,
                      verified: bool = False, holes: list | None = None,
                      hole_dia: float = 3.2) -> Path:
    """Create a measured bought part from an envelope and a provenance line.

    The fast path for a part you have a datasheet for but no STEP: three
    dimensions, an optional bolt pattern, and where the numbers came from.

    `verified` defaults to **False**, and that default is the point. A figure
    read off a drawing is a claim until someone puts callipers on the part, so
    the honest starting state is unconfirmed, and confirming it is a deliberate
    edit rather than something that happens by omission. An unverified part
    reports UNCHECKED and holds the project's gate open until it is either
    measured or replaced by a vendor STEP.
    """
    if not source.strip():
        raise MissingProvenance(
            "source is required: name the drawing, datasheet page or calliper "
            "reading these dimensions came from")
    for label, v in (("length", length), ("width", width), ("height", height)):
        if v <= 0:
            raise ValueError(f"{label} must be positive, not {v}")

    params = {"length": float(length), "width": float(width),
              "height": float(height)}
    body = ""
    if holes:
        params["hole_dia"] = float(hole_dia)
        params["holes"] = [[float(x), float(y)] for x, y in holes]
        body = ("    for hx, hy in holes:\n"
                "        body -= Pos(hx, hy, 0) * Cylinder(hole_dia / 2.0, height + 2)\n")

    path = bought_dir(slug, create=True) / f"{name}.py"
    if path.exists():
        raise FileExistsError(
            f"{path} already exists; edit it rather than overwriting, so its "
            "provenance and any calliper corrections survive")
    path.write_text(MEASURED_TEMPLATE.format(
        name=name, vendor_line=(vendor or "vendor not recorded"),
        source=source, vendor=vendor, verified=bool(verified),
        params=params, args=", ".join(params), holes=body))
    return path


def verify(slug: str, name: str, note: str) -> dict:
    """Mark a measured part confirmed against the real thing.

    `note` is required and is appended to SOURCE, because "verified" with no
    record of what was measured is the same unchecked claim wearing a better
    label.
    """
    if not note.strip():
        raise MissingProvenance(
            "say what was measured and how, e.g. 'callipers on the part, "
            "2026-09-18: 42.1 x 22.0 x 19.3'")
    path = bought_dir(slug) / f"{name}.py"
    if not path.exists():
        raise FileNotFoundError(
            f"{name} is not a measured part in {slug}; a vendor STEP is "
            "verified by re-registering it, not by this call")
    text = path.read_text()
    if "VERIFIED = False" not in text:
        raise ValueError(f"{name} is not marked unverified; nothing to confirm")
    text = text.replace("VERIFIED = False", "VERIFIED = True", 1)
    old = [ln for ln in text.splitlines() if ln.startswith("SOURCE = ")][0]
    src = eval(old.split("=", 1)[1].strip())            # a literal we wrote
    text = text.replace(old, f"SOURCE = {src + ' | confirmed: ' + note.strip()!r}", 1)
    path.write_text(text)
    return bought_info(slug, name)

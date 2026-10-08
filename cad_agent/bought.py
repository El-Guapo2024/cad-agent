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
"""
from __future__ import annotations

import json
from pathlib import Path

from build123d import import_step

from .geom import bbox, volume
from .state import _load_module, project_dir


class MissingProvenance(ValueError):
    """A measured part that does not say where its dimensions came from."""


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
        if p.suffix.lower() in (".step", ".stp"):
            meta = _sidecar(p)
            out.append({"name": p.stem, "kind": "STEP", "file": p.name,
                        "source": meta.get("source", "UNRECORDED"),
                        "vendor": meta.get("vendor"),
                        "verified": meta.get("verified", True)})
        elif p.suffix == ".py" and not p.stem.startswith("_"):
            mod = _load(p)
            out.append({"name": p.stem, "kind": "MEASURED", "file": p.name,
                        "source": getattr(mod, "SOURCE", "UNRECORDED"),
                        "vendor": getattr(mod, "VENDOR", None),
                        "verified": bool(getattr(mod, "VERIFIED", True))})
    return out


def _sidecar(step_path: Path) -> dict:
    j = step_path.with_suffix(".json")
    return json.loads(j.read_text()) if j.exists() else {}


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


def load_bought(slug: str, name: str):
    """Return the solid for a bought part, by either route."""
    d = bought_dir(slug)
    for ext in (".step", ".stp"):
        p = d / f"{name}{ext}"
        if p.exists():
            meta = _sidecar(p)
            if not meta.get("source"):
                raise MissingProvenance(
                    f"{name}{ext} has no sidecar recording its source; "
                    "re-add it with register_step so the provenance is kept")
            return import_step(str(p))
    p = d / f"{name}.py"
    if p.exists():
        mod = _load(p)
        source = getattr(mod, "SOURCE", "").strip()
        if not source:
            raise MissingProvenance(
                f"{name}.py declares no SOURCE; a measured part must name the "
                "drawing, datasheet page or calliper reading it came from")
        return mod.build(**getattr(mod, "PARAMS", {}))
    raise FileNotFoundError(
        f"no bought part {name!r} in {d}; add a vendor STEP with register_step "
        "or write a measured module with a SOURCE")


def bought_info(slug: str, name: str) -> dict:
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

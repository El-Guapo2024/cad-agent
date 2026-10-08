"""Project state. A project is a directory of parametric part modules.

projects/<slug>/
  mech_profile.md      the spec, written by the agent, edited by the human
  parts/<name>.py      each exposes PARAMS, MATERIAL, PROCESS, MIN_FEATURE_MM, build(**params)
  assembly.py          optional: parts() -> {name: solid}, CLEARANCE, ALLOW_CONTACT
  bought/*.step        vendor geometry, never modelled from memory
  out/                 renders, exports
  checks.json          the only source of numbers for the report
"""
from __future__ import annotations
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "projects"


def _is_name(slug: str) -> bool:
    """A project is one folder directly under the projects root. An empty name, `..` or a path
    would otherwise name the root itself, the folder above it, or any folder on the machine, and
    `cad check` would write checks.json there."""
    return bool(slug) and slug == Path(slug).name and not slug.startswith(".")


def why(e: BaseException) -> str:
    """A failure as a line to show: the kernel's own errors (Standard_Failure) carry no message,
    and the bare name leaves the reader nothing to change."""
    text = str(e).strip()
    if text:
        return f"{type(e).__name__}: {text}"
    return (f"{type(e).__name__} (it gave no message; a zero, negative or oversized "
            "dimension is the usual cause)")


def project_dir(slug: str, create: bool = False) -> Path:
    if not _is_name(slug):
        raise FileNotFoundError(f"no project {slug!r}")
    d = ROOT / slug
    if create:
        for sub in ("parts", "bought", "out"):
            (d / sub).mkdir(parents=True, exist_ok=True)
    elif not d.exists():
        raise FileNotFoundError(f"no project {slug!r} at {d}")
    return d


def list_projects() -> list[str]:
    """Project directories. Hidden ones (the CLI's .cad activity log) are not projects."""
    if not ROOT.exists():
        return []
    return sorted(p.name for p in ROOT.iterdir()
                  if p.is_dir() and not p.name.startswith("."))


def _load_module(path: Path):
    """Run a design file from its source, every time. Never from __pycache__:
    bytecode is reused when the file's mtime (whole seconds) and size match,
    so a rewrite within the same second that keeps the length (thickness
    6.0 -> 8.0, from `cad set` or an agent's edit and an immediate check)
    would run the old numbers."""
    import types
    mod = types.ModuleType(f"_cad_{path.stem}")
    mod.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), "exec"), mod.__dict__)
    return mod


def part_names(slug: str) -> list[str]:
    d = project_dir(slug) / "parts"
    return sorted(p.stem for p in d.glob("*.py") if not p.stem.startswith("_"))


def build_part(slug: str, name: str, overrides: dict | None = None):
    """Returns (solid, meta). meta carries the resolved params and process info."""
    path = project_dir(slug) / "parts" / f"{name}.py"
    if not path.exists():
        raise FileNotFoundError(f"no part {name!r} in {slug}")
    mod = _load_module(path)
    params = dict(getattr(mod, "PARAMS", {}))
    params.update(overrides or {})
    t0 = time.perf_counter()
    solid = mod.build(**params)
    meta = {
        "params": params,
        "material": getattr(mod, "MATERIAL", None),
        "process": getattr(mod, "PROCESS", None),
        "min_feature_mm": getattr(mod, "MIN_FEATURE_MM", None),
        "expect_features": getattr(mod, "EXPECT_FEATURES", None),
        "doc": (mod.__doc__ or "").strip().splitlines()[0] if mod.__doc__ else "",
        "build_s": round(time.perf_counter() - t0, 3),
    }
    return solid, meta


def bought_solid(slug: str, name: str):
    """Bought geometry for an assembly to place. Imported here to avoid a cycle."""
    from .bought import load_bought
    return load_bought(slug, name)


def load_assembly(slug: str, placed: bool = True):
    """Returns (parts, clearance, allow_contact, axes) or (None, {}, set(), {}).

    `axes` is the declared motion of the machine, empty for a static assembly.
    Parts moved by hand (placements.toml) are applied unless `placed` is False,
    which the workbench uses to show the move separately from the code's pose.
    """
    from .motion import load_axes
    from . import placements
    pdir = project_dir(slug)
    path = pdir / "assembly.py"
    if not path.exists():
        return None, {}, set(), {}
    mod = _load_module(path)
    parts = mod.parts()
    if placed:
        parts = placements.apply(parts, placements.load(pdir))
    return (parts, dict(getattr(mod, "CLEARANCE", {})),
            set(getattr(mod, "ALLOW_CONTACT", set())), load_axes(mod))


def write_checks(slug: str, payload: dict) -> Path:
    p = project_dir(slug) / "checks.json"
    payload = dict(payload)
    payload["written_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    p.write_text(json.dumps(payload, indent=2))
    return p


def read_checks(slug: str) -> dict:
    p = project_dir(slug) / "checks.json"
    if not p.exists():
        raise FileNotFoundError(f"{slug} has no checks.json; run check_all first")
    return json.loads(p.read_text())

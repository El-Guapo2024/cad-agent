"""Project state. A project is a directory of parametric part modules.

projects/<slug>/
  mech_profile.md      the spec, written by the agent, edited by the human
  parts/<name>.py      each exposes PARAMS, MATERIAL, PROCESS, MIN_FEATURE_MM, build(**params)
  assembly.py          optional: parts() -> {name: solid}, CLEARANCE, ALLOW_CONTACT, AXES, POSES,
                       SUBASSEMBLIES (load_machine reads them; bodies.py says what each holds)
  bought/*.step        vendor geometry, never modelled from memory
  out/                 renders, exports
  checks.json          the only source of numbers for the report
"""
from __future__ import annotations
import copy
import importlib.util
import json
import shlex
import sys
import time
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "projects"

# The packages cad-agent can use and does not require: the module a part imports, and what to install for it. Each
# is an extra of pyproject.toml (a test holds the two to each other), and the plugin's installer adds them all.
OPTIONAL = {"bd_warehouse": "bd_warehouse>=0.3"}       # `fasteners`: the library's ISO screw, nut and washer


def install_command(requirement: str) -> str:
    """The command that adds `requirement` to the Python that is running cad. That interpreter's own pip when it has
    one, else uv: the plugin's venv is made by uv, which leaves no pip in it and none on PATH, and a bare
    `pip install 'cad-agent[...]'` names a package that nobody publishes, so that advice cannot work there."""
    py, req = shlex.quote(sys.executable), shlex.quote(requirement)
    try:
        has_pip = importlib.util.find_spec("pip") is not None
    except (ImportError, ValueError):               # a pip with no spec: this runs inside why(), which must not fail
        has_pip = False
    return f"{py} -m pip install {req}" if has_pip else f"uv pip install -p {py} {req}"


def _is_name(slug: str) -> bool:
    """A project is one folder directly under the projects root. An empty name, `..` or a path
    would otherwise name the root itself, the folder above it, or any folder on the machine, and
    `cad check` would write checks.json there."""
    return bool(slug) and slug == Path(slug).name and not slug.startswith(".")


def why(e: BaseException) -> str:
    """A failure as a line to show: the kernel's own errors (Standard_Failure) carry no message,
    and the bare name leaves the reader nothing to change. A module of an optional package that is
    not installed says how to install it (a project copied from a machine that has it)."""
    text = str(e).strip()
    if text:
        need = OPTIONAL.get((getattr(e, "name", None) or "").partition(".")[0]) if isinstance(e, ModuleNotFoundError) else None
        if need:
            text += f" (an optional package of cad-agent: `{install_command(need)}`)"
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
    if not ROOT.is_dir():
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
    return sorted(p.stem for p in d.glob("*.py") if not p.stem.startswith(("_", ".")))   # ._x.py: a Mac's resource fork


_BUILT: ContextVar = ContextVar("built_parts", default=None)
_EVENTS: ContextVar = ContextVar("build_events", default=None)
_CACHE: ContextVar = ContextVar("cached_builds", default=False)


@contextmanager
def reusing_builds():
    """Inside the block, a part that was built once is copied rather than built again.

    One run builds the same part several times: for its own checks, again when assembly.py asks
    for it, again for a mass budget. Each is the same code with the same numbers, and a build
    takes a few tenths of a second to a second where a copy takes a few milliseconds. A pristine
    copy is kept the moment the part is built, before a rule meshes or measures the solid (both
    change a shape in place), and every later call is handed its own deep copy of that, so no two
    callers share a shape and none gets a mesh it did not make. A part asked for with overrides,
    or one that cannot be copied, is built as before.

    It yields the block's log of builds: one {"part", "how", "s"} for each part got any other way
    than by copy, how being "built" (its build() ran) or "cache" (see caching_builds).
    """
    token, log = _BUILT.set({}), _EVENTS.set([])
    try:
        yield _EVENTS.get()
    finally:
        _BUILT.reset(token)
        _EVENTS.reset(log)


@contextmanager
def caching_builds(on: bool = True):
    """Inside the block, build_part takes a part from the project's build cache when it and
    everything it depends on are as they were, and keeps what it builds there (buildcache.py).

    The edit loop uses it and a command asks for it by name. `cad verify` runs the checks inside
    caching_builds(False), so a verdict never rests on a part remembered from an earlier run;
    False holds inside an outer block that turned it on.
    """
    token = _CACHE.set(bool(on))
    try:
        yield
    finally:
        _CACHE.reset(token)


def build_part(slug: str, name: str, overrides: dict | None = None):
    """Returns (solid, meta). meta carries the resolved params and process info."""
    pdir = project_dir(slug)
    path = pdir / "parts" / f"{name}.py"
    if not path.exists():
        raise FileNotFoundError(f"no part {name!r} in {slug}")
    built = _BUILT.get()
    if built is not None and not overrides and str(path) in built:
        solid, meta = built[str(path)]
        return copy.deepcopy(solid), copy.deepcopy(meta)
    k = None
    if _CACHE.get():
        k, hit = _cache_lookup(pdir, name, overrides)
        if hit is not None:
            return _kept(built, path, overrides, name, "cache", *hit)
    mod = _load_module(path)
    params = dict(getattr(mod, "PARAMS", {}))
    params.update(overrides or {})
    t0 = time.perf_counter()
    solid = mod.build(**params)
    if not hasattr(solid, "bounding_box"):         # geom.bbox's own test for "a shape"
        raise TypeError(f"{name}.build() returned {type(solid).__name__}, not a solid: "
                        "return the Part (or Compound) it makes")
    meta = {
        "params": params,
        "material": getattr(mod, "MATERIAL", None),
        "process": getattr(mod, "PROCESS", None),
        "min_feature_mm": getattr(mod, "MIN_FEATURE_MM", None),
        "expect_features": getattr(mod, "EXPECT_FEATURES", None),
        "doc": (mod.__doc__ or "").strip().splitlines()[0] if mod.__doc__ else "",
        "build_s": round(time.perf_counter() - t0, 3),
    }
    if k:
        from . import buildcache
        buildcache.store(pdir, name, overrides, k, solid, meta)
    return _kept(built, path, overrides, name, "built", solid, meta)


def built_meta(slug: str, name: str) -> dict | None:
    """The meta of a part already built in this reusing_builds() block, or None. Nothing is built or
    loaded to answer, so a caller that only wants a part's MATERIAL or PROCESS costs the run nothing."""
    built = _BUILT.get()
    hit = built.get(str(project_dir(slug) / "parts" / f"{name}.py")) if built is not None else None
    return copy.deepcopy(hit[1]) if hit else None


def _cache_lookup(pdir: Path, name: str, overrides: dict | None):
    """(key, (solid, meta) or None). Trouble with the cache is a miss, never a failed build."""
    try:
        from . import buildcache
        k = buildcache.key(pdir, name, overrides)
        return k, (buildcache.load(pdir, k) if k else None)
    except Exception:
        return None, None


def _kept(built, path: Path, overrides, name: str, how: str, solid, meta):
    """Log how a part was got, and keep a pristine copy of it for the rest of the run."""
    events = _EVENTS.get()
    if events is not None:
        events.append({"part": name, "how": how, "s": meta["build_s"]})
    if built is not None and not overrides:
        try:
            built[str(path)] = (copy.deepcopy(solid), copy.deepcopy(meta))
        except Exception:                          # a shape that will not copy is built each time, as before
            pass
    return solid, meta


def bought_solid(slug: str, name: str, **params):
    """Bought geometry for an assembly to place, in the part's own frame (its datum applied).

    A generated part takes `params` over its PARAMS (`bought_solid(SLUG, "mgn12_rail", length=300)`),
    a STEP takes none. The solid is tagged with the part it is, which is how bodies.describe knows a
    body is bought and what it declares (mass, material, temperature, geometry); see bought.py.
    Imported here to avoid a cycle.
    """
    from .bought import load_bought
    return load_bought(slug, name, **params)


def load_machine(slug: str, placed: bool = True, describe: bool = True):
    """The assembly assembly.py describes, as a bodies.Assembly, or None when the project has none.

    parts is what parts() returns, with the hand-made moves of placements.toml applied unless `placed`
    is False (the workbench shows a move apart from the code's pose). clearance, allow_contact and
    axes are CLEARANCE, ALLOW_CONTACT and AXES; poses is POSES, held as declared ({name: {...}});
    bodies is a BodyInfo for each body (skipped with `describe=False`, for a caller that only wants
    solids). SUBASSEMBLIES, if declared, is expanded by subassembly.expand (the children's bodies come in
    as `child/body`, and they are described there). placements.toml is applied after that, so the file
    may move a child's body by its full name, quoted; subassembly.py has the rest. See bodies.py for what
    each field holds.
    """
    from . import bodies, placements
    from .motion import load_axes
    pdir = project_dir(slug)
    path = pdir / "assembly.py"
    if not path.exists():
        return None
    mod = _load_module(path)
    parts = mod.parts()
    bad = [f"{k!r}: {type(v).__name__}" for k, v in parts.items()
           if not (isinstance(k, str) and hasattr(v, "bounding_box"))] if isinstance(parts, dict) else None
    if bad is None or bad:
        got = type(parts).__name__ if bad is None else f"{bad[0]} among its entries"
        raise TypeError(f"assembly.py parts() must return {{name: solid}}, got {got}")
    poses = getattr(mod, "POSES", None) or {}
    if not (isinstance(poses, dict) and all(isinstance(k, str) and isinstance(v, dict) for k, v in poses.items())):
        raise TypeError("assembly.py POSES must be {name: {...}}, one dict for each named pose")
    machine = bodies.Assembly(
        slug=slug, parts=parts, clearance=dict(getattr(mod, "CLEARANCE", {})),
        allow_contact=set(getattr(mod, "ALLOW_CONTACT", set())), axes=load_axes(mod), poses=dict(poses),
        bodies=dict(getattr(parts, "bodies", None) or {}))   # an Assembly's sub-assembly bodies (assembly_wb.Parts)
    declared = getattr(mod, "SUBASSEMBLIES", None)
    if declared:
        from .cmdbase import NotBuilt, resolve
        expand = resolve("cad_agent.subassembly:expand")
        if expand is None:
            raise NotBuilt("assembly.py declares SUBASSEMBLIES, which step 6 piece B builds "
                           "(cad_agent/subassembly.py: expand(machine, declared) -> Assembly)")
        machine = expand(machine, declared)
    if placed:
        machine.parts = placements.apply(machine.parts, placements.load(pdir))
    if describe:
        left = {n: s for n, s in machine.parts.items() if n not in machine.bodies}
        machine.bodies.update(bodies.describe(slug, left))
    return machine


def load_assembly(slug: str, placed: bool = True):
    """Returns (parts, clearance, allow_contact, axes) or (None, {}, set(), {}).

    `axes` is the declared motion of the machine, empty for a static assembly.
    Parts moved by hand (placements.toml) are applied unless `placed` is False,
    which the workbench uses to show the move separately from the code's pose.
    The same call as load_machine, for a caller that wants the four and not the bodies.
    """
    machine = load_machine(slug, placed, describe=False)
    if machine is None:
        return None, {}, set(), {}
    return machine.as_tuple()


def write_atomic(path: Path, text: str) -> None:
    """Write beside the file and rename over it, so a run killed half way leaves the old file
    and not a truncated one that every later `cad status` or `cad done` has to choke on."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def write_checks(slug: str, payload: dict) -> Path:
    p = project_dir(slug) / "checks.json"
    payload = dict(payload)
    payload["written_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    write_atomic(p, json.dumps(payload, indent=2))
    return p


def read_checks(slug: str) -> dict:
    p = project_dir(slug) / "checks.json"
    if not p.exists():
        raise FileNotFoundError(f"{slug} has no checks.json; run check_all first")
    return json.loads(p.read_text())

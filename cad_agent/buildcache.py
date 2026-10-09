"""The build cache: a part, built once, kept for the next command.

An edit to one part used to cost a rebuild of all of them, the untouched ones too, and a build takes
from a fraction of a second to several. This keeps each built solid in the project, under
.cad/cache/builds/ beside the activity log, and a command that needs it again reads it back in a
few milliseconds.

It is for the edit loop (`check`, `scene`, `measure`, `place`), never for judging a design.
`cad verify` rebuilds from source in a fresh process because a verdict is only worth something if
nothing it relies on was remembered, so it never reads or writes the cache: a command asks for the
cache with state.caching_builds(), and nothing else gets it.

An entry is found by a sha256 over everything its build could depend on, so a change to any of them
is a miss and never a stale hit:

  the part's source, and the --set overrides it is built with;
  every .py file of the project that is not a part or assembly.py (helpers a part could import);
  another part, or assembly.py, only when the imports in what the part runs name it;
  everything in bought/ (a part can import a bought module, as arduino_car's chassis does);
  every file of the project, if what the part runs opens a file, builds another part or imports by
    a name it computes (open, read_text, build_part, importlib, exec and the like), since then
    nothing says what it reads;
  cad-agent's own source (verify.engine_hash), build123d, OCP, Python and the machine.

An entry is one file: a line of JSON (the key, the class, the part's meta and a fingerprint of the
shape), the shape in OCCT's binary BRep format, and a sha256 of all that. Nothing is trusted on the
way in or out. A part is stored only if what comes back from the file has the fingerprint (the
counts of solids, faces, edges and vertices, volume, area and box) of the shape that went in, is a
plain build123d Part, Compound or Solid with nothing set on it, and has a meta that survives JSON
unchanged. An entry that is missing, truncated, from another key, or whose shape no longer gives
the fingerprint it was stored with is a miss, and so is every error: the cache can only make a
command faster.

What comes back is the shape that went in, not the same bits. OCCT rebuilds each surface frame and
location from the numbers it reads (renormalising them), so a frame that was a hair off square, as
Rot(0, 90, 0) leaves one (6e-17 where a 0 belongs), returns a few ulps away, and a zero may change
its sign. That is some eight orders below the 1e-6 mm every gate allows and below what any row prints;
FINGERPRINT_TOL holds it to that when a part is stored, and tests/test_buildcache.py holds the rows
of cached and uncached `check` equal on the fixture designs.
"""
from __future__ import annotations

import ast
import hashlib
import io
import json
import os
import platform
import sys
import threading
import time
from pathlib import Path

FORMAT = 1
MAGIC = b"cad-agent build cache 1\n"
CAP_BYTES = 64 * 1024 * 1024        # per project; the entries used longest ago go first
FINGERPRINT_TOL = 1e-9              # relative, or mm for a box edge: how far a stored shape may be from the built one
SUFFIX = ".part"
SKIP_DIRS = {"out", "baseline", "research", "__pycache__", "node_modules"}    # outputs, renders, notes
OUTPUTS = {"checks.json", "verify.json"}
# A part that calls one of these may reach a module or a file by a name the scan of its imports cannot
# see: build_part and load_assembly run other design files, the rest import or read by a computed name.
REACHES_CALLS = {"__import__", "exec", "eval", "compile", "open", "build_part", "load_assembly"}
REACHES_METHODS = {"import_module", "run_path", "run_module", "spec_from_file_location", "load_module",
                   "exec_module", "open", "read_text", "read_bytes", "load", "loadtxt", "import_step",
                   "import_stl", "import_svg", "import_brep", "import_dxf", "build_part", "load_assembly"}

_ENV: str | None = None


def cache_dir(pdir: Path) -> Path:
    return Path(pdir) / ".cad" / "cache" / "builds"


def forget() -> None:
    """Drop what is remembered about this process's environment (a test changes it)."""
    global _ENV
    _ENV = None


def _environment_now() -> str:
    """What every entry depends on besides the project: the code that builds and judges it."""
    import build123d
    import OCP
    from .verify import engine_hash
    return "|".join([str(FORMAT), engine_hash(), build123d.__version__,
                     str(getattr(OCP, "__version__", "?")), sys.version.split()[0],
                     sys.platform, platform.machine()])


def _environment() -> str:
    """The environment as this process first saw it, which is the code it is running."""
    global _ENV
    if _ENV is None:
        _ENV = _environment_now()
    return _ENV


def _files(root: Path) -> list[Path]:
    """Every file under the project that could be design: no outputs, renders, dot files or folders.
    A link to a folder is followed, once."""
    found, seen = [], set()
    for base, dirs, names in os.walk(root, followlinks=True):
        real = os.path.realpath(base)
        if real in seen:
            dirs[:] = []
            continue
        seen.add(real)
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
        found += [Path(base) / n for n in sorted(names)
                  if not n.startswith(".") and not n.endswith(".pyc") and n not in OUTPUTS]
    return found


def _imports(src: bytes) -> tuple[set[str], bool]:
    """The names a source imports, and whether it can reach a module or file by a name it computes."""
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError):
        return set(), True
    names, reaches = set(), False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.update(a.name for a in node.names)
            if node.module:
                names.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            f = node.func
            reaches |= (isinstance(f, ast.Name) and f.id in REACHES_CALLS) or \
                       (isinstance(f, ast.Attribute) and f.attr in REACHES_METHODS)
    return names, reaches


def key(pdir: Path, name: str, overrides: dict | None = None, env: str | None = None) -> str | None:
    """The cache key of one part as the project is on disk now, or None when it cannot be made."""
    pdir = Path(pdir)
    try:
        part = pdir / "parts" / f"{name}.py"
        src = part.read_bytes()
        extra = json.dumps(overrides or {}, sort_keys=True)
        files = _files(pdir)
        bought = [p for p in files if p.relative_to(pdir).parts[0] == "bought"]
        modules: dict[str, list[Path]] = {}                  # what a part imports only by name: parts, assembly.py
        for p in files:
            if p == pdir / "assembly.py" or (p.parent == pdir / "parts" and p.suffix == ".py"
                                             and not p.stem.startswith("_")):
                modules.setdefault(p.stem, []).append(p)
        named = {p for ps in modules.values() for p in ps}
        helpers = [p for p in files if p.suffix == ".py" and p not in named and p not in bought]
        need = {*helpers, *bought}
        scan, reaches = [src] + [p.read_bytes() for p in helpers + [b for b in bought if b.suffix == ".py"]], False
        for source in scan:                                  # grows as imported modules are added
            names, wide = _imports(source)
            reaches |= wide
            for p in (q for stem in names & modules.keys() for q in modules[stem]):
                if p not in need and p != part:
                    need.add(p)
                    scan.append(p.read_bytes())
        h = hashlib.sha256()
        for field in (env or _environment(), name, extra):
            h.update(field.encode() + b"\0")
        h.update(src)
        for p in sorted(set(files) - {part} if reaches else need):
            h.update(p.relative_to(pdir).as_posix().encode() + b"\0" + hashlib.sha256(p.read_bytes()).digest())
        return h.hexdigest()
    except (OSError, TypeError, ValueError):
        return None


def _plain(solid) -> str | None:
    """The class to restore a built solid as, if a bare shape of that class is the same object.

    Whatever else a part sets (a label, a colour, joints, assembly children) lives only in Python
    and would be lost in the file, so such a part is built each time.
    """
    from build123d import Compound, Part, Solid
    cls = type(solid)
    if cls not in (Part, Compound, Solid):
        return None
    try:
        twin = cls(solid.wrapped)
        a, b = dict(vars(solid)), dict(vars(twin))
        if a.keys() != b.keys() or any(a[k] != b[k] for k in a if k != "_wrapped"):
            return None
    except Exception:
        return None
    return cls.__name__


def _fingerprint(shape) -> list:
    """Numbers a shape must give back after a round trip through the file."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SOLID, TopAbs_VERTEX
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape
    counts = []
    for kind in (TopAbs_SOLID, TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX):
        found = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(shape, kind, found)
        counts.append(found.Extent())
    vol, area, box = GProp_GProps(), GProp_GProps(), Bnd_Box()
    BRepGProp.VolumeProperties_s(shape, vol)
    BRepGProp.SurfaceProperties_s(shape, area)
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    return json.loads(json.dumps([counts, vol.Mass(), area.Mass(), list(box.Get())]))


def _same_shape(a: list, b: list) -> bool:
    """Whether two fingerprints are one shape: the same counts, the same numbers to FINGERPRINT_TOL."""
    def near(x, y):
        return abs(x - y) <= FINGERPRINT_TOL * max(1.0, abs(x), abs(y))
    return a[0] == b[0] and all(near(x, y) for x, y in zip([a[1], a[2], *a[3]], [b[1], b[2], *b[3]]))


def _write(shape) -> bytes:
    from OCP.BinTools import BinTools, BinTools_FormatVersion_CURRENT
    buf = io.BytesIO()
    BinTools.Write_s(shape, buf, False, False, BinTools_FormatVersion_CURRENT)   # no mesh: a part is stored as built
    return buf.getvalue()


def _read(data: bytes):
    from OCP.BinTools import BinTools
    from OCP.TopoDS import TopoDS_Shape
    shape = TopoDS_Shape()
    BinTools.Read_s(shape, io.BytesIO(data))
    if shape.IsNull():
        raise ValueError("empty shape")
    return shape


META_KEYS = ("params", "material", "process", "min_feature_mm", "expect_features", "doc", "build_s")


def _restore(cls_name: str, shape):
    """The bare build123d object for a shape, of the class that was stored (an allowed one, never a name from the file)."""
    import build123d
    return {c.__name__: c for c in (build123d.Part, build123d.Compound, build123d.Solid)}[cls_name](shape)


def load(pdir: Path, k: str):
    """(solid, meta) from the entry for key `k`, or None: missing, damaged or not this key's."""
    path = cache_dir(pdir) / f"{k}{SUFFIX}"
    t0 = time.perf_counter()
    try:
        data = path.read_bytes()
        body = data[:-32]
        if not body.startswith(MAGIC) or hashlib.sha256(body).digest() != data[-32:]:
            raise ValueError("damaged")
        head, _, brep = body[len(MAGIC):].partition(b"\n")
        head = json.loads(head)
        if head["key"] != k or head["format"] != FORMAT:
            raise ValueError("not this key's")
        shape = _read(brep)
        if _fingerprint(shape) != head["fingerprint"]:
            raise ValueError("does not round-trip")
        meta = head["meta"]
        if not isinstance(meta, dict) or not set(META_KEYS) <= meta.keys():
            raise ValueError("no meta")
        solid = _restore(head["cls"], shape)
    except FileNotFoundError:
        return None
    except Exception:
        _drop(path)
        return None
    meta["build_s"] = round(time.perf_counter() - t0, 3)     # what this run spent, not what the build took
    try:
        os.utime(path)                                       # recently used: evicted last
    except OSError:
        pass
    return solid, meta


def _drop(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def store(pdir: Path, name: str, overrides: dict | None, k: str, solid, meta: dict) -> bool:
    """Keep a part that was just built, if it comes back as it went in. Never raises.

    The fingerprint kept is the one the shape has after the round trip, which the reader gives
    again to the last bit; only the first trip is held to FINGERPRINT_TOL of the built shape.
    """
    try:
        cls = _plain(solid)
        if cls is None or json.loads(json.dumps(meta)) != meta or not set(META_KEYS) <= meta.keys():
            return False
        brep = _write(solid.wrapped)
        built, want = _fingerprint(solid.wrapped), _fingerprint(_read(brep))
        if not _same_shape(built, want):
            return False
        if key(pdir, name, overrides, env=_environment_now()) != k:   # the design or the code moved during the build
            return False
        head = json.dumps({"format": FORMAT, "key": k, "cls": cls, "meta": meta, "fingerprint": want},
                          separators=(",", ":"))
        blob = MAGIC + head.encode() + b"\n" + brep
        d = cache_dir(pdir)
        d.mkdir(parents=True, exist_ok=True)
        ignore = d.parent / ".gitignore"
        if not ignore.exists():
            ignore.write_text("*\n")                         # a project inside someone's repo: never commit these
        tmp = d / f"{k}{SUFFIX}.{os.getpid()}.{threading.get_ident()}.tmp"
        try:
            tmp.write_bytes(blob + hashlib.sha256(blob).digest())    # the checksum of everything before it
            tmp.replace(d / f"{k}{SUFFIX}")
        finally:
            tmp.unlink(missing_ok=True)
        _evict(d)
        return True
    except Exception:
        return False


def _evict(d: Path) -> None:
    """Keep the folder under CAP_BYTES by deleting the entries used longest ago."""
    entries, now = [], time.time()
    for p in d.iterdir():
        try:
            st = p.stat()
        except OSError:
            continue
        if p.name.endswith(".tmp"):
            if now - st.st_mtime > 600:                      # a writer that died
                _drop(p)
        elif p.name.endswith(SUFFIX):
            entries.append((st.st_mtime, st.st_size, p))
    total = sum(size for _, size, _ in entries)
    for _, size, p in sorted(entries):
        if total <= CAP_BYTES:
            break
        _drop(p)
        total -= size

"""Exports: STEP for a machine shop, STL and 3MF for a printer, DXF for a laser. `cad export --format` writes them
to the project's out/ folder, and `cad shop` (shop.py) writes the same files, from `render`, to out/shop/.

A file that goes to a shop, or is a design file (a bought part is a STEP, and `cad verify` hashes bought/*),
has to be the same bytes whenever and wherever it is written: in a fresh process or a worker that has
exported a hundred parts, today or next week, on OCCT 7.9 or 8.0. A hash in a manifest and `cad shop --check`
both rest on it. Each format gets there its own way (the DXF, 3MF and STL are the same bytes on both kernels,
the STEP all but one line):

  STEP   OCCT puts the process into it in two places, and `canonical_step` fixes each: the header's time
         stamp is the wall clock (pinned to STEP_STAMP); an assembly occurrence is numbered from a counter that
         lives as long as the process, and a part returned as `Pos(...) * body` is an assembly of one (the
         first export of a process writes NEXT_ASSEMBLY_USAGE_OCCURRENCE('1', ...), the twentieth writes
         '20'; the numbers are counted again from 1, which is what a fresh process writes). The header also
         names the version of the kernel that wrote it ("Open CASCADE STEP processor 7.9" or "8.0"), and that is
         left as it is: it is true, the committed STEP files say it, and tests/test_library.py tells another
         kernel by it. It is the only thing a part's STEP says that differs between OCCT 7.9 and 8.0 (checked on a
         plate, a filleted block, a sphere with a cone, a torus, a bracket and a turned plate), so `kernel_free`
         gives the bytes without it, which is what `cad shop --check` compares and the tests pin
  3MF    threemf.py: a mesh of sorted integers, in a zip written by hand (the module says why)
  STL    the same mesh, so a printed part's STL and 3MF are one shape. This replaced OCCT's own STL writer,
         whose triangles come in the kernel's order and move with its version
  DXF    dxf.py: the part's outline, as FreeCAD's ImpExpDxf writes one, to a nanometre

`render(solid, name, fmt, stamp)` gives the bytes of any of them. A `stamp` ("NOT VERIFIED", for `cad shop
--draft`) is written into the file where the format has room for it: the STEP's description, the 3MF's title
and name, the STL's header, a text on the DXF's own layer.
"""
from __future__ import annotations
import re
import tempfile
from pathlib import Path
from build123d import export_step
from .state import project_dir, build_part

STEP_STAMP = "1970-01-01T00:00:00"      # FILE_NAME's time_stamp; the epoch says "no date", on purpose
FORMATS = ("step", "stl", "3mf", "dxf")               # what export_part writes

_STAMP = re.compile(rb"(FILE_NAME\(\s*'(?:[^']|'')*'\s*,\s*')[^']*(')")
_PROCESSOR = re.compile(rb"Open CASCADE STEP processor [0-9][0-9.]*")
_OCCURRENCE = re.compile(rb"(#\d+\s*=\s*NEXT_ASSEMBLY_USAGE_OCCURRENCE\(\s*')(\d+)(')")
_DESCRIPTION = re.compile(rb"(FILE_DESCRIPTION\(\()")


def canonical_step(data: bytes) -> bytes:
    """What a fresh process would have written, however the STEP in `data` was made.

    Only the time stamp and the occurrence numbers change. The numbers keep their order, so each occurrence
    keeps its place: `'7', '5', '6'` becomes `'3', '1', '2'`.
    """
    data = _STAMP.sub(lambda m: m[1] + STEP_STAMP.encode() + m[2], data, count=1)
    seen = sorted({int(m[2]) for m in _OCCURRENCE.finditer(data)})
    number = {old: b"%d" % new for new, old in enumerate(seen, 1)}
    return _OCCURRENCE.sub(lambda m: m[1] + number[int(m[2])] + m[3], data)


def kernel_free(data: bytes) -> bytes:
    """A STEP without the one thing in it that is the kernel's: the version it names as its processor."""
    return _PROCESSOR.sub(b"Open CASCADE STEP processor", data, count=1)


def stamp_step(data: bytes, stamp: str) -> bytes:
    """A STEP with `stamp` as the first line of its description, which is where a reader looks for a note."""
    text = stamp.encode("ascii", "replace").replace(b"'", b"''")
    return _DESCRIPTION.sub(lambda m: m[1] + b"'" + text + b"',", data, count=1)


def step_bytes(shape) -> bytes:
    """The STEP of `shape`: the same shape, the same bytes, in any process at any time (and on either kernel, but for
    the processor line, see `kernel_free`)."""
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "shape.step"
        export_step(shape, str(raw))
        data = raw.read_bytes()
    return canonical_step(data)


def write_step(shape, path: str | Path) -> Path:
    """Write `shape` as STEP to `path` (see step_bytes)."""
    path = Path(path)
    path.write_bytes(step_bytes(shape))
    return path


def render(solid, name: str, fmt: str, stamp: str | None = None) -> bytes:
    """The bytes of `solid` as `fmt` (one of FORMATS), named `name` inside the file, with `stamp` written into it."""
    fmt = fmt.lower()
    if fmt == "step":
        data = step_bytes(solid)
        return stamp_step(data, stamp) if stamp else data
    if fmt in ("stl", "3mf"):
        from . import threemf
        mesh = threemf.mesh_of(solid)
        return (threemf.write_stl if fmt == "stl" else threemf.write_3mf)(mesh, name, stamp)
    if fmt == "dxf":
        from . import dxf
        return dxf.dxf_of(solid, name, stamp)
    raise ValueError(f"unsupported format {fmt!r}; use {' or '.join(FORMATS)}")


def export_part(slug: str, name: str, fmt: str = "step") -> Path:
    solid, _ = build_part(slug, name)
    fmt = fmt.lower()
    if fmt not in FORMATS:
        raise ValueError(f"unsupported format {fmt!r}; use {' or '.join(FORMATS)}")
    data = render(solid, name, fmt)
    out = project_dir(slug) / "out"
    out.mkdir(parents=True, exist_ok=True)
    p = out / f"{name}.{fmt}"
    p.write_bytes(data)
    return p

"""Exports. STEP for a machine shop, STL for printing, DXF for laser cutting.

A STEP is also a design file: a bought part is one, and `cad verify` hashes bought/*. So one part
has to write one file, in a fresh process or a worker that has exported a hundred, today or next
week. OCCT breaks that in two places, and `write_step` fixes both:

  - the header's time stamp is the wall clock; it is pinned to STEP_STAMP;
  - an assembly occurrence is numbered from a counter that lives as long as the process, and a part
    returned as `Pos(...) * body` is an assembly of one. The first export of a process writes
    NEXT_ASSEMBLY_USAGE_OCCURRENCE('1', ...), the twentieth writes '20'. The numbers are counted
    again from 1, which is what a fresh process writes.

Everything else a part's STEP says comes from the part, and does not change between runs.
"""
from __future__ import annotations
import re
import tempfile
from pathlib import Path
from build123d import export_step, export_stl
from .state import project_dir, build_part

STEP_STAMP = "1970-01-01T00:00:00"      # FILE_NAME's time_stamp; the epoch says "no date", on purpose

_STAMP = re.compile(rb"(FILE_NAME\(\s*'(?:[^']|'')*'\s*,\s*')[^']*(')")
_OCCURRENCE = re.compile(rb"(#\d+\s*=\s*NEXT_ASSEMBLY_USAGE_OCCURRENCE\(\s*')(\d+)(')")


def canonical_step(data: bytes) -> bytes:
    """What a fresh process would have written, however the STEP in `data` was made.

    Only the time stamp and the occurrence numbers change. The numbers keep their order, so each
    occurrence keeps its place: `'7', '5', '6'` becomes `'3', '1', '2'`.
    """
    data = _STAMP.sub(lambda m: m[1] + STEP_STAMP.encode() + m[2], data, count=1)
    seen = sorted({int(m[2]) for m in _OCCURRENCE.finditer(data)})
    number = {old: b"%d" % new for new, old in enumerate(seen, 1)}
    return _OCCURRENCE.sub(lambda m: m[1] + number[int(m[2])] + m[3], data)


def write_step(shape, path: str | Path) -> Path:
    """Write `shape` as STEP to `path`: the same shape, the same bytes, in any process at any time."""
    path = Path(path)
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "shape.step"
        export_step(shape, str(raw))
        data = raw.read_bytes()
    path.write_bytes(canonical_step(data))
    return path


def export_part(slug: str, name: str, fmt: str = "step") -> Path:
    solid, _ = build_part(slug, name)
    out = project_dir(slug) / "out"
    out.mkdir(parents=True, exist_ok=True)
    fmt = fmt.lower()
    if fmt == "step":
        p = write_step(solid, out / f"{name}.step")
    elif fmt == "stl":
        p = out / f"{name}.stl"
        export_stl(solid, str(p))
    else:
        raise ValueError(f"unsupported format {fmt!r}; use step or stl")
    return p

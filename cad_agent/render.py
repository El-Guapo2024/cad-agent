"""Headless render: OCCT solid -> triangle mesh -> numpy z-buffer -> PNG.

No GPU, no display, no EGL. Deterministic output so a rebuild that changes
nothing produces a byte-identical image.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from pathlib import Path
import numpy as np

# Named views: (azimuth_deg, elevation_deg). Camera looks at the bbox centre.
VIEWS = {
    "iso":   (45.0, 30.0),
    "iso2":  (-135.0, 30.0),
    "top":   (0.0, 89.9),
    "bottom":(0.0, -89.9),
    "front": (0.0, 0.0),
    "back":  (180.0, 0.0),
    "left":  (90.0, 0.0),
    "right": (-90.0, 0.0),
}


@dataclass
class Mesh:
    verts: np.ndarray  # (n,3) float
    tris: np.ndarray   # (m,3) int

    @property
    def bbox(self):
        return self.verts.min(axis=0), self.verts.max(axis=0)


def tessellate(shape, tolerance: float = 0.1, angular: float = 0.3) -> Mesh:
    """build123d/OCCT shape -> Mesh. Uses the shape's own tessellate()."""
    inner = getattr(shape, "wrapped", None)
    obj = shape if inner is None else shape
    verts, tris = obj.tessellate(tolerance, angular)
    v = np.array([[p.X, p.Y, p.Z] for p in verts], dtype=float)
    t = np.array(tris, dtype=int).reshape(-1, 3)
    return Mesh(v, t)


def _basis(az_deg: float, el_deg: float):
    az, el = math.radians(az_deg), math.radians(el_deg)
    # camera direction (from camera toward target)
    fwd = np.array([
        -math.cos(el) * math.cos(az),
        -math.cos(el) * math.sin(az),
        -math.sin(el),
    ])
    fwd /= np.linalg.norm(fwd)
    world_up = np.array([0.0, 0.0, 1.0])
    if abs(np.dot(fwd, world_up)) > 0.999:
        world_up = np.array([0.0, 1.0, 0.0])
    right = np.cross(world_up, -fwd); right /= np.linalg.norm(right)
    up = np.cross(-fwd, right); up /= np.linalg.norm(up)
    return right, up, fwd


def merge(meshes: list[Mesh]) -> Mesh:
    """Concatenate meshes into one, reindexing triangles. For assembly views."""
    verts, tris, off = [], [], 0
    for m in meshes:
        verts.append(m.verts)
        tris.append(m.tris + off)
        off += len(m.verts)
    return Mesh(np.vstack(verts), np.vstack(tris))


def render(
    mesh: Mesh,
    out_path: str | Path,
    view: str = "iso",
    size: tuple[int, int] = (900, 700),
    bg=(247, 246, 244),
    face=(196, 122, 62),
    edge_boost: float = 0.0,
    margin: float = 1.08,
    highlight: np.ndarray | None = None,
    highlight_face=(70, 150, 110),
) -> Path:
    """Orthographic flat-shaded render with a z-buffer. Returns the PNG path."""
    if view not in VIEWS:
        raise ValueError(f"unknown view {view!r}; choose from {sorted(VIEWS)}")
    az, el = VIEWS[view]
    right, up, fwd = _basis(az, el)

    lo, hi = mesh.bbox
    centre = (lo + hi) / 2.0
    v = mesh.verts - centre

    # project to camera space
    x = v @ right
    y = v @ up
    z = v @ fwd  # larger = further away

    W, H = size
    span_x = max(x.max() - x.min(), 1e-9)
    span_y = max(y.max() - y.min(), 1e-9)
    scale = min(W / (span_x * margin), H / (span_y * margin))
    px = x * scale + W / 2.0
    py = H / 2.0 - y * scale  # image y grows downward

    tris = mesh.tris
    # flat shading from the geometric normal, lit from over the camera's shoulder
    p0, p1, p2 = mesh.verts[tris[:, 0]], mesh.verts[tris[:, 1]], mesh.verts[tris[:, 2]]
    n = np.cross(p1 - p0, p2 - p0)
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    ln[ln == 0] = 1.0
    n = n / ln
    light = -(fwd * 0.65) + up * 0.55 + right * 0.35
    light /= np.linalg.norm(light)
    lam = np.abs(n @ light)
    shade = 0.35 + 0.65 * lam  # ambient + diffuse

    img = np.zeros((H, W, 3), dtype=np.float64)
    img[:, :] = np.array(bg, dtype=float)
    zbuf = np.full((H, W), np.inf)

    base = np.array(face, dtype=float)
    hl = np.array(highlight_face, dtype=float)
    hl_set = set(highlight.tolist()) if highlight is not None else set()

    # depth-sorted rasterisation with a per-pixel z-buffer
    tz = (z[tris[:, 0]] + z[tris[:, 1]] + z[tris[:, 2]]) / 3.0
    order = np.argsort(-tz)  # far to near

    for ti in order:
        a, b, c = tris[ti]
        xs = np.array([px[a], px[b], px[c]])
        ys = np.array([py[a], py[b], py[c]])
        zs = np.array([z[a], z[b], z[c]])

        x0 = max(int(np.floor(xs.min())), 0)
        x1 = min(int(np.ceil(xs.max())) + 1, W)
        y0 = max(int(np.floor(ys.min())), 0)
        y1 = min(int(np.ceil(ys.max())) + 1, H)
        if x0 >= x1 or y0 >= y1:
            continue

        # barycentric over the bbox
        d = ((ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2]))
        if abs(d) < 1e-12:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
        l0 = ((ys[1] - ys[2]) * (gx - xs[2]) + (xs[2] - xs[1]) * (gy - ys[2])) / d
        l1 = ((ys[2] - ys[0]) * (gx - xs[2]) + (xs[0] - xs[2]) * (gy - ys[2])) / d
        l2 = 1.0 - l0 - l1
        inside = (l0 >= -1e-9) & (l1 >= -1e-9) & (l2 >= -1e-9)
        if not inside.any():
            continue
        depth = l0 * zs[0] + l1 * zs[1] + l2 * zs[2]

        sub_z = zbuf[y0:y1, x0:x1]
        win = inside & (depth < sub_z)
        if not win.any():
            continue
        col = (hl if ti in hl_set else base) * shade[ti]
        if edge_boost:
            # darken near the triangle border to hint at edges
            rim = np.minimum(np.minimum(l0, l1), l2) < 0.02
            col_arr = np.repeat(col[None, :], win.sum(), axis=0)
            col_arr[rim[win]] *= (1.0 - edge_boost)
        else:
            col_arr = col
        sub_img = img[y0:y1, x0:x1]
        sub_img[win] = col_arr
        sub_z[win] = depth[win]

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    _write_png(np.clip(img, 0, 255).astype(np.uint8), out)
    return out


# ─── Backend dispatch ────────────────────────────────────────────────────────

_BACKEND_NOTE: list[str] = []


def backend_status() -> str:
    """Which renderer will run, and why. Named so a report can quote it."""
    import os
    forced = os.environ.get("CAD_RENDER_BACKEND", "auto").lower()
    if forced == "numpy":
        return "numpy z-buffer (forced by CAD_RENDER_BACKEND)"
    try:
        from .metal_render import device_name
        return f"metal ({device_name()})"
    except Exception as e:  # pragma: no cover - depends on the host
        return f"numpy z-buffer (metal unavailable: {type(e).__name__}: {e})"


def draw(mesh: Mesh, out_path, view: str = "iso", backend: str = "auto", **kw):
    """Render through the fastest available backend.

    Metal is roughly two orders of magnitude faster than the numpy path and
    produces the same image, so it is the default wherever it is reachable.
    The numpy rasteriser stays as the fallback: it needs nothing but numpy,
    so a machine without Metal still renders rather than failing.
    """
    import os
    choice = (backend or "auto").lower()
    if choice == "auto":
        choice = os.environ.get("CAD_RENDER_BACKEND", "auto").lower()
    if choice in ("auto", "metal"):
        try:
            from .metal_render import render_metal
            return render_metal(mesh, out_path, view=view, **kw)
        except Exception as e:
            if choice == "metal":
                raise
            if not _BACKEND_NOTE:
                _BACKEND_NOTE.append(f"metal unavailable ({type(e).__name__}), using numpy")
    elif choice != "numpy":
        raise ValueError(f"unknown backend {choice!r}; use auto, metal or numpy")
    return render(mesh, out_path, view=view, **kw)


def read_png(path) -> np.ndarray:
    """Read back a PNG this module wrote. Enough of the format for our own
    output: 8-bit truecolour, no interlacing, filter type 0."""
    import struct
    import zlib
    raw = Path(path).read_bytes()
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} is not a PNG")
    pos, idat, w, h = 8, b"", 0, 0
    while pos < len(raw):
        ln = int.from_bytes(raw[pos:pos + 4], "big")
        tag = raw[pos + 4:pos + 8]
        data = raw[pos + 8:pos + 8 + ln]
        if tag == b"IHDR":
            w, h, depth, colour = struct.unpack(">IIBB", data[:10])
            if (depth, colour) != (8, 2):
                raise ValueError(f"{path}: expected 8-bit truecolour, got "
                                 f"depth {depth} colour type {colour}")
        elif tag == b"IDAT":
            idat += data
        pos += 12 + ln
    flat = zlib.decompress(idat)
    stride = w * 3 + 1
    rows = [flat[i * stride + 1:(i + 1) * stride] for i in range(h)]
    return np.frombuffer(b"".join(rows), dtype=np.uint8).reshape(h, w, 3)


def _write_png(rgb: np.ndarray, path: Path) -> None:
    """Minimal PNG writer (zlib + struct). Avoids an image-library dependency."""
    import struct, zlib
    H, W, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[y].tobytes() for y in range(H))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 6))
           + chunk(b"IEND", b""))
    path.write_bytes(png)

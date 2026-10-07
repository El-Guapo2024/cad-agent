"""Metal rasteriser: the same flat-shaded z-buffered image, drawn on the GPU.

macOS has no EGL, so the usual headless OpenGL path does not exist here. Metal
is Apple's supported route and PyObjC exposes it, so this backend talks to it
directly: an offscreen colour texture plus a depth texture, one render pass,
no window and no window-server session. It works over ssh and in a subprocess.

The image is meant to match `render.render` pixel for pixel in intent: flat
shading from the geometric normal, one light over the camera's shoulder, a
depth test resolving overlaps. Shading is computed on the CPU in numpy, which
is vectorised and cheap, and the triangles are sent unindexed so each one
carries its own constant colour. That avoids needing per-primitive data in the
shader at all.

One limit shapes the rest of the file. Metal compiles shaders in an XPC
service, and a process made by fork() without exec cannot open that
connection: the bootstrap look-up fails with "No such process" and the compile
with XPC_ERROR_CONNECTION_INVALID. The warm worker (warm.py) runs every command
in such a fork. The compile still succeeds there when Metal's on-disk shader
cache already holds this source for this python (a cold run fills it; another
venv's python does not share it), which is why a venv that had once rendered
cold looked fine while a fresh install rendered with numpy. So the worker
starts a sidecar, a process it execs, that owns the device, the compiled
pipeline and every draw; a fork sends it the triangles over a Unix socket
(named by CAD_METAL_SIDECAR) and gets the pixels back. With no such variable,
or no answer, the draw happens in the calling process.
"""
from __future__ import annotations

import json
import os
import select
import signal
import socket
import sys
from pathlib import Path

import numpy as np

from .render import VIEWS, Mesh, _basis, _write_png

SIDECAR_ENV = "CAD_METAL_SIDECAR"   # warm.py sets it in the worker, so its forks inherit it
SIDECAR_TIMEOUT_S = 60

_SHADER = """
#include <metal_stdlib>
using namespace metal;

struct VOut {
    float4 pos [[position]];
    float4 col;
};

vertex VOut v_main(uint vid [[vertex_id]],
                   const device packed_float3 *positions [[buffer(0)]],
                   const device float4 *colors [[buffer(1)]],
                   constant float4x4 &mvp [[buffer(2)]]) {
    VOut o;
    o.pos = mvp * float4(positions[vid], 1.0);
    o.col = colors[vid];
    return o;
}

fragment float4 f_main(VOut in [[stage_in]]) {
    return in.col;
}
"""


class MetalUnavailable(RuntimeError):
    """Raised when no Metal device can be reached, so callers can fall back."""


_STATE: dict = {}


def _metal():
    """Device, queue, pipeline and depth state, built once and reused.

    Shader compilation dominates a first call, so it must not happen per
    render. Everything cached here is immutable and thread-confined to the
    caller in practice: a render loop draws one image at a time.
    """
    if _STATE:
        return _STATE
    try:
        import Metal
    except ImportError as e:  # pragma: no cover - depends on the host
        raise MetalUnavailable(
            "pyobjc-framework-Metal is not installed; pip install it or use "
            "the numpy backend"
        ) from e

    device = Metal.MTLCreateSystemDefaultDevice()
    if device is None:
        raise MetalUnavailable("no Metal device on this machine")

    library, err = device.newLibraryWithSource_options_error_(_SHADER, None, None)
    if library is None:
        raise MetalUnavailable(f"shader would not compile: {err}")

    desc = Metal.MTLRenderPipelineDescriptor.alloc().init()
    desc.setVertexFunction_(library.newFunctionWithName_("v_main"))
    desc.setFragmentFunction_(library.newFunctionWithName_("f_main"))
    desc.colorAttachments().objectAtIndexedSubscript_(0).setPixelFormat_(
        Metal.MTLPixelFormatRGBA8Unorm)
    desc.setDepthAttachmentPixelFormat_(Metal.MTLPixelFormatDepth32Float)
    pipeline, err = device.newRenderPipelineStateWithDescriptor_error_(desc, None)
    if pipeline is None:
        raise MetalUnavailable(f"pipeline would not build: {err}")

    dsd = Metal.MTLDepthStencilDescriptor.alloc().init()
    dsd.setDepthCompareFunction_(Metal.MTLCompareFunctionLess)
    dsd.setDepthWriteEnabled_(True)

    _STATE.update(
        Metal=Metal,
        device=device,
        queue=device.newCommandQueue(),
        pipeline=pipeline,
        depth_state=device.newDepthStencilStateWithDescriptor_(dsd),
        # A discrete GPU has its own memory, so a texture we intend to read
        # back must be managed and explicitly synchronised after the pass.
        unified=bool(device.hasUnifiedMemory()),
        name=str(device.name()),
    )
    return _STATE


def _local_name() -> str:
    return _metal()["name"]


def device_name() -> str:
    """The GPU's name, asked of the sidecar when this process has one."""
    if os.environ.get(SIDECAR_ENV):
        try:
            return _ask({"op": "name"})[0]["name"]
        except _SIDECAR_DOWN:
            pass
    return _local_name()


def _geometry(mesh: Mesh, view: str, size, face, highlight, highlight_face, margin):
    """CPU side: project, shade, and expand to unindexed triangles.

    Returns the vertex positions in world space, a colour per vertex, and the
    orthographic matrix that maps world space to Metal's clip space.
    """
    if view not in VIEWS:
        raise ValueError(f"unknown view {view!r}; choose from {sorted(VIEWS)}")
    right, up, fwd = _basis(*VIEWS[view])

    lo, hi = mesh.bbox
    centre = (lo + hi) / 2.0
    v = mesh.verts - centre
    x, y, z = v @ right, v @ up, v @ fwd

    W, H = size
    span_x = max(x.max() - x.min(), 1e-9)
    span_y = max(y.max() - y.min(), 1e-9)
    scale = min(W / (span_x * margin), H / (span_y * margin))

    tris = mesh.tris
    p0, p1, p2 = mesh.verts[tris[:, 0]], mesh.verts[tris[:, 1]], mesh.verts[tris[:, 2]]
    n = np.cross(p1 - p0, p2 - p0)
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    ln[ln == 0] = 1.0
    n /= ln
    light = -(fwd * 0.65) + up * 0.55 + right * 0.35
    light /= np.linalg.norm(light)
    shade = 0.35 + 0.65 * np.abs(n @ light)          # ambient + diffuse

    base = np.tile(np.asarray(face, dtype=np.float32) / 255.0, (len(tris), 1))
    if highlight is not None and len(highlight):
        base[np.asarray(highlight, dtype=int)] = (
            np.asarray(highlight_face, dtype=np.float32) / 255.0)
    rgb = base * shade[:, None]
    rgba = np.concatenate([rgb, np.ones((len(tris), 1), dtype=np.float32)], axis=1)

    # Unindexed: three vertices per triangle, each carrying the flat colour.
    positions = mesh.verts[tris.reshape(-1)].astype(np.float32)
    colors = np.repeat(rgba, 3, axis=0).astype(np.float32)

    # Orthographic: world -> camera basis -> NDC. Metal clip space is x,y in
    # [-1,1] with y up, and z in [0,1] with 0 nearest.
    zmin, zmax = float(z.min()), float(z.max())
    zspan = max(zmax - zmin, 1e-9)
    basis = np.stack([right, up, fwd])                       # rows
    s = np.diag([2.0 * scale / W, 2.0 * scale / H, 1.0 / zspan])
    m3 = s @ basis
    mvp = np.eye(4, dtype=np.float32)
    mvp[:3, :3] = m3
    mvp[:3, 3] = -(m3 @ centre)
    mvp[2, 3] -= zmin / zspan
    # Metal expects column-major float4x4, so transpose on the way out.
    return positions, colors, np.ascontiguousarray(mvp.T, dtype=np.float32)


def _leaks_new() -> bool:
    """Does this pyobjc leave one retain too many on what Metal's new* methods return?

    pyobjc 12.2.2 does: a buffer or texture that is dropped is never freed, so a process
    that draws for hours (the sidecar) grows by every pass's vertex buffers and textures,
    well over a megabyte a draw. The device counts what it has allocated, so this measures
    the leak, and that one release cures it, rather than trusting a version number.
    """
    dev, Metal = _STATE["device"], _STATE["Metal"]
    size = 1 << 20

    def grown_by_a_dropped_buffer(release: bool) -> int:
        before = dev.currentAllocatedSize()
        buf = dev.newBufferWithLength_options_(size, Metal.MTLResourceStorageModeShared)
        if release:
            buf.release()
        del buf
        return dev.currentAllocatedSize() - before

    try:
        return grown_by_a_dropped_buffer(False) >= size and grown_by_a_dropped_buffer(True) <= 0
    except Exception:  # noqa: BLE001 - cannot tell, so leave the objects alone
        return False


def _own(obj):
    """Balance the retain _leaks_new() found, so that dropping `obj` frees it."""
    if _STATE.get("release_new"):
        obj.release()
    return obj


def _draw_local(positions, colors, mvp, size, bg) -> np.ndarray:
    """The GPU pass in this process: unindexed triangles in, (H, W, 3) pixels out."""
    _metal()                      # first, so a machine without Metal is told what is missing
    import objc
    # Metal hands back autoreleased objects, and nothing drains a pool in a plain Python
    # process, so a long-lived one (the sidecar) would keep every pass's textures.
    with objc.autorelease_pool():
        return _gpu_pass(positions, colors, mvp, size, bg)


def _gpu_pass(positions, colors, mvp, size, bg) -> np.ndarray:
    st = _metal()
    Metal = st["Metal"]
    W, H = size

    opts = Metal.MTLResourceStorageModeManaged
    pos_buf = _own(st["device"].newBufferWithBytes_length_options_(
        positions.tobytes(), positions.nbytes, opts))
    col_buf = _own(st["device"].newBufferWithBytes_length_options_(
        colors.tobytes(), colors.nbytes, opts))

    ctd = Metal.MTLTextureDescriptor.texture2DDescriptorWithPixelFormat_width_height_mipmapped_(
        Metal.MTLPixelFormatRGBA8Unorm, W, H, False)
    ctd.setUsage_(Metal.MTLTextureUsageRenderTarget | Metal.MTLTextureUsageShaderRead)
    ctd.setStorageMode_(Metal.MTLStorageModeManaged)
    colour_tex = _own(st["device"].newTextureWithDescriptor_(ctd))

    dtd = Metal.MTLTextureDescriptor.texture2DDescriptorWithPixelFormat_width_height_mipmapped_(
        Metal.MTLPixelFormatDepth32Float, W, H, False)
    dtd.setUsage_(Metal.MTLTextureUsageRenderTarget)
    dtd.setStorageMode_(Metal.MTLStorageModePrivate)
    depth_tex = _own(st["device"].newTextureWithDescriptor_(dtd))

    rp = Metal.MTLRenderPassDescriptor.renderPassDescriptor()
    ca = rp.colorAttachments().objectAtIndexedSubscript_(0)
    ca.setTexture_(colour_tex)
    ca.setLoadAction_(Metal.MTLLoadActionClear)
    ca.setStoreAction_(Metal.MTLStoreActionStore)
    ca.setClearColor_(Metal.MTLClearColorMake(
        bg[0] / 255.0, bg[1] / 255.0, bg[2] / 255.0, 1.0))
    da = rp.depthAttachment()
    da.setTexture_(depth_tex)
    da.setLoadAction_(Metal.MTLLoadActionClear)
    da.setStoreAction_(Metal.MTLStoreActionDontCare)
    da.setClearDepth_(1.0)

    cmd = st["queue"].commandBuffer()
    enc = cmd.renderCommandEncoderWithDescriptor_(rp)
    enc.setRenderPipelineState_(st["pipeline"])
    enc.setDepthStencilState_(st["depth_state"])
    enc.setVertexBuffer_offset_atIndex_(pos_buf, 0, 0)
    enc.setVertexBuffer_offset_atIndex_(col_buf, 0, 1)
    enc.setVertexBytes_length_atIndex_(mvp.tobytes(), mvp.nbytes, 2)
    enc.drawPrimitives_vertexStart_vertexCount_(
        Metal.MTLPrimitiveTypeTriangle, 0, len(positions))
    enc.endEncoding()

    if not st["unified"]:
        # Discrete GPU: pull the texture back into CPU-visible memory.
        blit = cmd.blitCommandEncoder()
        blit.synchronizeResource_(colour_tex)
        blit.endEncoding()

    cmd.commit()
    cmd.waitUntilCompleted()
    if cmd.error() is not None:
        raise RuntimeError(f"Metal render failed: {cmd.error()}")

    buf = bytearray(W * H * 4)
    colour_tex.getBytes_bytesPerRow_fromRegion_mipmapLevel_(
        buf, W * 4, Metal.MTLRegionMake2D(0, 0, W, H), 0)
    rgba = np.frombuffer(bytes(buf), dtype=np.uint8).reshape(H, W, 4)
    return np.ascontiguousarray(rgba[:, :, :3])


def render_metal(
    mesh: Mesh,
    out_path: str | Path,
    view: str = "iso",
    size: tuple[int, int] = (900, 700),
    bg=(247, 246, 244),
    face=(196, 122, 62),
    margin: float = 1.08,
    highlight: np.ndarray | None = None,
    highlight_face=(70, 150, 110),
) -> Path:
    """Draw the mesh on the GPU and write a PNG. Same signature as render()."""
    positions, colors, mvp = _geometry(
        mesh, view, size, face, highlight, highlight_face, margin)
    rgb = _draw(positions, colors, mvp, size, bg)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    _write_png(rgb, out)
    return out


# ─── The sidecar ─────────────────────────────────────────────────────────────
# One request per connection: a JSON header line, then the raw bytes it names.
#   {"op": "draw", "size": [W, H], "bg": [r, g, b], "n": vertices}
#       + n*3 float32 positions, n*4 float32 colours, 16 float32 matrix
#       -> {"ok": true, "bytes": W*H*3} + the RGB pixels
#   {"op": "name"} -> {"ok": true, "name": device}
#   {"op": "ping"} -> {"ok": true, "pid", "name", "served": draws so far}
# A failure comes back as {"ok": false, "error": text}.

_SIDECAR_DOWN = (OSError, ValueError, EOFError, KeyError, MetalUnavailable)
_SERVED = [0]


def _ask(header: dict, *payload) -> tuple[dict, bytes]:
    """One round trip to the sidecar named by CAD_METAL_SIDECAR."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(SIDECAR_TIMEOUT_S)
    try:
        s.connect(os.environ[SIDECAR_ENV])
        s.sendall(json.dumps(header).encode() + b"\n")
        for part in payload:
            s.sendall(part)
        f = s.makefile("rb")
        reply = json.loads(f.readline() or b"{}")
        if not reply.get("ok"):
            raise MetalUnavailable(f"sidecar: {reply.get('error', 'no reply')}")
        body = f.read(reply.get("bytes", 0))
        if len(body) != reply.get("bytes", 0):
            raise EOFError("sidecar reply cut short")
        return reply, body
    finally:
        s.close()


def _draw_remote(positions, colors, mvp, size, bg) -> np.ndarray:
    W, H = size
    _, body = _ask({"op": "draw", "size": [int(W), int(H)], "bg": [float(c) for c in bg],
                    "n": len(positions)}, positions, colors, mvp)
    return np.frombuffer(body, dtype=np.uint8).reshape(H, W, 3)


def _draw(positions, colors, mvp, size, bg) -> np.ndarray:
    """The GPU pass, in the sidecar when this process has one, else here."""
    if os.environ.get(SIDECAR_ENV):
        try:
            return _draw_remote(positions, colors, mvp, size, bg)
        except _SIDECAR_DOWN:
            pass          # nobody answering: this process may still manage (a cached shader)
    return _draw_local(positions, colors, mvp, size, bg)


def handle(conn: socket.socket, draw=_draw_local, name=_local_name) -> None:
    """Answer one request on `conn`. A bad one gets an error reply, never an exception."""
    body = b""
    try:
        conn.settimeout(30)
        f = conn.makefile("rb")
        head = json.loads(f.readline(1 << 16) or b"{}")
        op = head.get("op")
        if op == "draw":
            W, H = (int(v) for v in head["size"])
            n = int(head["n"])
            if not (0 < W <= 16384 and 0 < H <= 16384 and 0 < n <= 1 << 25 and n % 3 == 0):
                raise ValueError("size or vertex count out of range")
            raw = f.read(n * 28 + 64)
            if len(raw) != n * 28 + 64:
                raise EOFError("request cut short")
            positions = np.frombuffer(raw, np.float32, n * 3).reshape(n, 3)
            colors = np.frombuffer(raw, np.float32, n * 4, offset=n * 12).reshape(n, 4)
            mvp = np.frombuffer(raw, np.float32, 16, offset=n * 28).reshape(4, 4)
            body = np.ascontiguousarray(draw(positions, colors, mvp, (W, H), head["bg"])).tobytes()
            _SERVED[0] += 1
            reply = {"ok": True, "bytes": len(body)}
        elif op == "name":
            reply = {"ok": True, "name": name()}
        elif op == "ping":
            reply = {"ok": True, "pid": os.getpid(), "name": name(), "served": _SERVED[0]}
        else:
            raise ValueError(f"unknown op {op!r}")
    except Exception as e:  # noqa: BLE001 - whatever went wrong goes back to the caller
        reply, body = {"ok": False, "error": f"{type(e).__name__}: {e}"}, b""
    try:
        conn.sendall(json.dumps(reply).encode() + b"\n" + body)
    except OSError:
        pass              # the caller gave up


def serve(path: Path, parent: int | None = None, draw=_draw_local, name=_local_name) -> None:
    """Answer draws one at a time until `parent`, the worker that started us, is gone."""
    path = Path(path)
    path.unlink(missing_ok=True)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    old = os.umask(0o177)                      # the socket is this user's alone
    try:
        srv.bind(str(path))
    finally:
        os.umask(old)
    srv.listen(64)                             # a burst of forks queues here, it is not turned away
    try:
        while parent is None or os.getppid() == parent:
            if select.select([srv], [], [], 1.0)[0]:
                try:
                    conn, _ = srv.accept()
                except OSError:
                    continue
                with conn:
                    handle(conn, draw, name)
    finally:
        srv.close()
        path.unlink(missing_ok=True)


def main(argv: list[str]) -> int:
    """`python -m cad_agent.metal_render _serve SOCKET PARENT_PID`, as the warm worker runs it."""
    if len(argv) != 3 or argv[0] != "_serve":
        print("usage: python -m cad_agent.metal_render _serve SOCKET PARENT_PID", file=sys.stderr)
        return 2
    try:
        _metal()      # compile now rather than on the first draw, and bind no socket if we cannot
        _STATE["release_new"] = _leaks_new()     # only here: a one-shot cold run need not bother
        # The first pass wakes a discrete GPU, close to a second: spend it before anyone waits.
        _draw_local(np.array([[-.5, -.5, .5], [.5, -.5, .5], [0, .5, .5]], np.float32),
                    np.ones((3, 4), np.float32), np.eye(4, dtype=np.float32), (16, 16), (0, 0, 0))
    except MetalUnavailable as e:
        print(f"metal sidecar: {e}", file=sys.stderr)
        return 1
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))      # leave through serve()'s cleanup
    serve(Path(argv[1]), int(argv[2]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

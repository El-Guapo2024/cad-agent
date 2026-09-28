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
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .render import VIEWS, Mesh, _basis, _write_png

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


def device_name() -> str:
    return _metal()["name"]


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
    st = _metal()
    Metal = st["Metal"]
    W, H = size

    positions, colors, mvp = _geometry(
        mesh, view, size, face, highlight, highlight_face, margin)

    opts = Metal.MTLResourceStorageModeManaged
    pos_buf = st["device"].newBufferWithBytes_length_options_(
        positions.tobytes(), positions.nbytes, opts)
    col_buf = st["device"].newBufferWithBytes_length_options_(
        colors.tobytes(), colors.nbytes, opts)

    ctd = Metal.MTLTextureDescriptor.texture2DDescriptorWithPixelFormat_width_height_mipmapped_(
        Metal.MTLPixelFormatRGBA8Unorm, W, H, False)
    ctd.setUsage_(Metal.MTLTextureUsageRenderTarget | Metal.MTLTextureUsageShaderRead)
    ctd.setStorageMode_(Metal.MTLStorageModeManaged)
    colour_tex = st["device"].newTextureWithDescriptor_(ctd)

    dtd = Metal.MTLTextureDescriptor.texture2DDescriptorWithPixelFormat_width_height_mipmapped_(
        Metal.MTLPixelFormatDepth32Float, W, H, False)
    dtd.setUsage_(Metal.MTLTextureUsageRenderTarget)
    dtd.setStorageMode_(Metal.MTLStorageModePrivate)
    depth_tex = st["device"].newTextureWithDescriptor_(dtd)

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

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    _write_png(np.ascontiguousarray(rgba[:, :, :3]), out)
    return out

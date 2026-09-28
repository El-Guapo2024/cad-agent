"""Tests for the gates and the render loop. These are the reason the numbers
on a report can be trusted, so they check the failure paths, not just happy ones.
"""
import numpy as np
import pytest
from build123d import Box, Cylinder, Pos

from cad_agent.checks import check_dfm, check_fit
from cad_agent.geom import bbox, intersection_volume, mass_g, min_distance, volume
from cad_agent.parts import EXTRUSION, extrusion_blank
from cad_agent.render import VIEWS, merge, render, tessellate


# ─── geometry queries ────────────────────────────────────────────────────────

def test_volume_and_mass():
    b = Box(10, 10, 10)                     # 1000 mm^3 = 1 cm^3
    assert volume(b) == pytest.approx(1000.0, rel=1e-6)
    assert mass_g(b, "aluminium") == pytest.approx(2.70, rel=1e-6)


def test_mass_rejects_unknown_material():
    with pytest.raises(KeyError):
        mass_g(Box(1, 1, 1), "unobtainium")


def test_min_distance_and_overlap():
    a = Box(10, 10, 10)
    far = Pos(0, 0, 20) * Box(10, 10, 10)   # 10 mm gap
    touch = Pos(0, 0, 10) * Box(10, 10, 10)  # face to face
    over = Pos(0, 0, 5) * Box(10, 10, 10)    # half overlapping
    assert min_distance(a, far) == pytest.approx(10.0, abs=1e-6)
    assert min_distance(a, touch) == pytest.approx(0.0, abs=1e-6)
    assert intersection_volume(a, far) == pytest.approx(0.0, abs=1e-6)
    assert intersection_volume(a, over) == pytest.approx(500.0, rel=1e-4)


# ─── fit gate ────────────────────────────────────────────────────────────────

def test_fit_flags_interference():
    parts = {"a": Box(10, 10, 10), "b": Pos(0, 0, 5) * Box(10, 10, 10)}
    (row,) = check_fit(parts)
    assert row["state"] == "FAIL"
    assert row["check"] == "interference"
    assert "mm^3" in row["detail"]


def test_fit_enforces_required_clearance():
    parts = {"a": Box(10, 10, 10), "b": Pos(0, 0, 15) * Box(10, 10, 10)}  # 5 mm
    (ok,) = check_fit(parts, required_clearance={"a|b": 4.0})
    (bad,) = check_fit(parts, required_clearance={"a|b": 6.0})
    assert ok["state"] == "PASS" and ok["measured_mm"] == pytest.approx(5.0)
    assert bad["state"] == "FAIL" and "required" in bad["detail"]


def test_fit_contact_needs_explicit_permission():
    parts = {"a": Box(10, 10, 10), "b": Pos(0, 0, 10) * Box(10, 10, 10)}
    (unlisted,) = check_fit(parts, required_clearance={"a|b": 2.0})
    assert unlisted["state"] == "FAIL"
    (allowed,) = check_fit(parts, required_clearance={"a|b": 2.0},
                           allow_contact={"a|b"})
    assert allowed["state"] == "PASS" and "allowed" in allowed["detail"]


def test_fit_judges_every_pair():
    parts = {n: Pos(0, 0, 30 * i) * Box(5, 5, 5) for i, n in enumerate("abcd")}
    assert len(check_fit(parts)) == 6          # 4 choose 2


# ─── dfm gate ────────────────────────────────────────────────────────────────

def test_dfm_fails_oversized_envelope():
    rows = check_dfm("slab", Box(400, 400, 400), "cnc", min_feature_mm=5)
    env = next(r for r in rows if r["rule"] == "envelope")
    assert env["state"] == "FAIL"


def test_dfm_wall_is_unchecked_when_nothing_measures_or_declares_it():
    rows = check_dfm("p", Box(10, 10, 10), "fdm", measure=False)
    wall = next(r for r in rows if r["rule"] == "min wall")
    assert wall["state"] == "UNCHECKED"


def test_dfm_fails_a_thin_declared_wall_when_measurement_is_off():
    rows = check_dfm("p", Box(10, 10, 10), "fdm", min_feature_mm=0.3, measure=False)
    wall = next(r for r in rows if r["rule"] == "min wall")
    assert wall["state"] == "FAIL"
    assert "declared" in wall["measured"]


def test_measurement_overrides_a_wrong_declaration():
    """A part that understates its own thickness is corrected, not believed."""
    rows = check_dfm("p", Box(10, 10, 10), "fdm", min_feature_mm=0.3, samples=1000)
    wall = next(r for r in rows if r["rule"] == "min wall")
    assert wall["state"] == "PASS"
    assert "rays" in wall["measured"]


def test_dfm_rejects_unknown_process():
    with pytest.raises(ValueError):
        check_dfm("p", Box(1, 1, 1), "sintering")


# ─── helpers ─────────────────────────────────────────────────────────────────

def test_extrusion_axis_orients_the_length():
    for axis, idx in (("x", 0), ("y", 1), ("z", 2)):
        lo, hi = bbox(extrusion_blank("2040", 300.0, axis=axis))
        dims = [hi[i] - lo[i] for i in range(3)]
        assert dims[idx] == pytest.approx(300.0)


def test_extrusion_rejects_bad_axis_and_profile():
    with pytest.raises(ValueError):
        extrusion_blank("2040", 100.0, axis="w")
    with pytest.raises(ValueError):
        extrusion_blank("9090", 100.0)


def test_extrusion_profiles_have_the_fields_parts_use():
    for kind, e in EXTRUSION.items():
        assert {"w", "h", "slot", "bore"} <= set(e), kind


# ─── render ──────────────────────────────────────────────────────────────────

def test_tessellate_produces_triangles():
    m = tessellate(Box(10, 10, 10))
    assert m.tris.shape[1] == 3
    assert len(m.tris) >= 12


def test_render_writes_a_png_of_the_right_size(tmp_path):
    m = tessellate(Box(10, 20, 30))
    p = render(m, tmp_path / "a.png", view="iso", size=(120, 90))
    head = p.read_bytes()[:8]
    assert head == b"\x89PNG\r\n\x1a\n"
    width = int.from_bytes(p.read_bytes()[16:20], "big")
    height = int.from_bytes(p.read_bytes()[20:24], "big")
    assert (width, height) == (120, 90)


def test_render_is_deterministic(tmp_path):
    m = tessellate(Cylinder(5, 20))
    a = render(m, tmp_path / "a.png", view="front", size=(80, 80)).read_bytes()
    b = render(m, tmp_path / "b.png", view="front", size=(80, 80)).read_bytes()
    assert a == b


def test_render_actually_draws_the_part(tmp_path):
    """A view of a solid must differ from the background, or the loop is blind."""
    m = tessellate(Box(10, 10, 10))
    p = render(m, tmp_path / "a.png", view="iso", size=(100, 100))
    assert p.stat().st_size > 200


def test_views_differ_from_each_other(tmp_path):
    m = tessellate(Box(30, 10, 5))
    top = render(m, tmp_path / "t.png", view="top", size=(80, 80)).read_bytes()
    front = render(m, tmp_path / "f.png", view="front", size=(80, 80)).read_bytes()
    assert top != front


def test_render_rejects_unknown_view(tmp_path):
    with pytest.raises(ValueError):
        render(tessellate(Box(1, 1, 1)), tmp_path / "x.png", view="corner")


def test_named_views_all_render(tmp_path):
    m = tessellate(Box(10, 20, 5))
    for v in VIEWS:
        assert render(m, tmp_path / f"{v}.png", view=v, size=(60, 60)).exists()


def test_merge_reindexes_triangles():
    a, b = tessellate(Box(5, 5, 5)), tessellate(Pos(0, 0, 10) * Box(5, 5, 5))
    big = merge([a, b])
    assert len(big.tris) == len(a.tris) + len(b.tris)
    assert big.tris.max() == len(big.verts) - 1


# ─── metal backend ───────────────────────────────────────────────────────────

def _metal_or_skip():
    try:
        from cad_agent.metal_render import device_name
        return device_name()
    except Exception as e:
        pytest.skip(f"no Metal on this host: {e}")


def test_metal_device_is_reachable():
    assert _metal_or_skip()


def test_metal_writes_a_valid_png(tmp_path):
    _metal_or_skip()
    from cad_agent.metal_render import render_metal
    m = tessellate(Box(10, 20, 30))
    p = render_metal(m, tmp_path / "m.png", view="iso", size=(160, 120))
    raw = p.read_bytes()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    assert int.from_bytes(raw[16:20], "big") == 160
    assert int.from_bytes(raw[20:24], "big") == 120


def _decode(path):
    """Read our own PNG back to pixels, so the two backends can be compared."""
    import struct, zlib
    raw = path.read_bytes()
    pos, idat, w, h = 8, b"", 0, 0
    while pos < len(raw):
        ln = int.from_bytes(raw[pos:pos + 4], "big")
        tag = raw[pos + 4:pos + 8]
        data = raw[pos + 8:pos + 8 + ln]
        if tag == b"IHDR":
            w, h = struct.unpack(">II", data[:8])
        elif tag == b"IDAT":
            idat += data
        pos += 12 + ln
    flat = zlib.decompress(idat)
    stride = w * 3 + 1
    rows = [flat[i * stride + 1:(i + 1) * stride] for i in range(h)]
    return np.frombuffer(b"".join(rows), dtype=np.uint8).reshape(h, w, 3)


def test_metal_and_numpy_agree(tmp_path):
    """The GPU path must draw the same picture, or a render stops being evidence."""
    _metal_or_skip()
    from cad_agent.metal_render import render_metal
    m = tessellate(Cylinder(12, 30))
    a = _decode(render(m, tmp_path / "cpu.png", view="iso", size=(240, 180)))
    b = _decode(render_metal(m, tmp_path / "gpu.png", view="iso", size=(240, 180)))
    assert a.shape == b.shape
    # Edge pixels differ by a fraction where the two rasterisers disagree on
    # coverage; the silhouette and the shading must still match.
    diff = np.abs(a.astype(int) - b.astype(int)).max(axis=2)
    assert (diff > 24).mean() < 0.02, f"{(diff > 24).mean():.3%} of pixels differ"


def test_metal_is_deterministic(tmp_path):
    _metal_or_skip()
    from cad_agent.metal_render import render_metal
    m = tessellate(Box(10, 10, 20))
    a = render_metal(m, tmp_path / "a.png", view="front", size=(100, 100)).read_bytes()
    b = render_metal(m, tmp_path / "b.png", view="front", size=(100, 100)).read_bytes()
    assert a == b


def test_metal_rejects_unknown_view(tmp_path):
    _metal_or_skip()
    from cad_agent.metal_render import render_metal
    with pytest.raises(ValueError):
        render_metal(tessellate(Box(1, 1, 1)), tmp_path / "x.png", view="corner")


# ─── backend dispatch ────────────────────────────────────────────────────────

def test_draw_falls_back_to_numpy_when_forced(tmp_path, monkeypatch):
    from cad_agent.render import draw
    monkeypatch.setenv("CAD_RENDER_BACKEND", "numpy")
    p = draw(tessellate(Box(5, 5, 5)), tmp_path / "n.png", view="top", size=(60, 60))
    assert p.exists()


def test_draw_rejects_unknown_backend(tmp_path):
    from cad_agent.render import draw
    with pytest.raises(ValueError):
        draw(tessellate(Box(1, 1, 1)), tmp_path / "x.png", backend="vulkan")


def test_backend_status_names_the_renderer():
    from cad_agent.render import backend_status
    s = backend_status()
    assert "metal" in s or "numpy" in s

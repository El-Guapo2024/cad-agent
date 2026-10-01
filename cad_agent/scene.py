"""scene.json: what the workbench and the review page draw.

The geometry is tessellated by ocp-tessellate into three-cad-viewer's format
(the viewer inside OCP CAD Viewer), so the tree, section caps, explode,
measuring and camera all come from that library. What this adds is what the
panels need and the viewer does not know:

- per body: the part module it comes from, material, colour, mass, size
- the hand-made move (placements.toml) with its pivot, so a drag in the
  workbench can be written back as a new placement
- AXES, the spec envelope, and the design hash the scene was built from

Bodies are drawn where every gate sees them: placements applied.
"""
from __future__ import annotations

import base64
import math
import time
import zlib
from pathlib import Path

import numpy as np

from . import gui, placements, state as st
from .params import read as params_of

FORMAT = "cad-scene/2"

# Colours by material: what a part is made of should read at a glance.
MATERIAL_COLOR = {
    "petg": "#e8833a", "pla": "#e3a83c", "abs": "#d9d4c7", "nylon": "#ece6d6",
    "aluminium": "#b9c0c8", "aluminum": "#b9c0c8", "steel": "#8a9199",
    "stainless": "#a3aab1", "brass": "#c9a64b", "copper": "#c77b4e",
    "acrylic": "#9fd3e6", "fr4": "#3f7d3a", "polyimide": "#c98a2b",
}
STOCK_COLOR = "#aab1b9"      # extrusions and other stock: plain aluminium grey
BOUGHT_COLOR = "#6f8fb0"     # vendor parts: blue-grey, so they read as not ours
PALETTE = ["#e8833a", "#3f8fd2", "#4fae6e", "#d4b13c", "#b26ad1", "#e0607e"]
FLOAT_KEYS = {"vertices", "normals", "edges", "obj_vertices", "uvs"}


POSITION = {"left", "right", "front", "back", "top", "bottom", "upper", "lower", "inner",
            "outer", "l", "r", "fl", "fr", "bl", "br", "tl", "tr"}


def _part_for(body: str, parts: list[str]) -> str | None:
    """The part module a body comes from: the same name, or the name without
    a position or index suffix (end_plate_left -> end_plate), or the one part
    that name ends (standoff_fl -> plate_standoff). Anything else is stock:
    gantry_beam is not a gantry_end."""
    if body in parts:
        return body
    words = body.split("_")
    while len(words) > 1 and (words[-1] in POSITION or words[-1].isdigit()):
        words.pop()
    stem = "_".join(words)
    if stem in parts:
        return stem
    hits = [p for p in parts if p.endswith("_" + stem)]
    return hits[0] if len(hits) == 1 else None


def _bought_names(pdir: Path) -> set[str]:
    d = pdir / "bought"
    return {p.stem for p in d.glob("*") if p.suffix in (".py", ".step", ".stp")} if d.is_dir() else set()


def _encode(instance: dict) -> dict:
    """One tessellated instance as three-cad-viewer's base64 buffers."""
    out = {}
    for key, value in instance.items():
        if value is None:
            continue
        floats = key in FLOAT_KEYS
        a = np.ascontiguousarray(np.asarray(value).ravel(), dtype="<f4" if floats else "<u4")
        out[key] = {"buffer": base64.b64encode(a.tobytes()).decode(),
                    "dtype": "float32" if floats else "uint32", "codec": "b64", "shape": [a.size]}
    return out


def plain(o):
    """json.dumps default for what ocp-tessellate returns."""
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, tuple):
        return list(o)
    raise TypeError(f"not JSON: {type(o).__name__}")


def placed_solids(slug: str) -> tuple[dict, dict]:
    """Every body as the scene shows it (placements applied; parts laid out along x
    when there is no assembly.py), and each made part's material."""
    from .geom import bbox
    part_names = st.part_names(slug)
    base, _, _, _ = st.load_assembly(slug, placed=False)
    metas: dict = {}
    if base is None:
        from build123d import Pos
        base, x = {}, 0.0
        for name in part_names:
            solid, metas[name] = st.build_part(slug, name)
            lo, hi = bbox(solid)
            base[name] = Pos(x - lo[0], 0, 0) * solid
            x += (hi[0] - lo[0]) + 20.0
    shown = placements.apply(base, placements.load(st.project_dir(slug)))
    materials = {}
    for name in shown:
        part = _part_for(name, part_names)
        if part:
            if part not in metas:
                _, metas[part] = st.build_part(slug, part)
            materials[name] = metas[part].get("material")
    return shown, materials


def _effective_tessellation(view_props: dict, name: str,
                            deviation: float | None, angular: float | None) -> tuple[float, float]:
    """One body's Deviation (percent of its bounding-box size) and AngularDeflection
    (degrees, converted to radians): its own view_props entry, falling back to
    FreeCAD's ViewProviderPartExt::loadParameter() defaults when it has neither set
    (see gui.DEVIATION_DEFAULT / gui.ANGULAR_DEFLECTION_DEFAULT). An explicit
    `deviation`/`angular` (already radians) forces that value on every body alike —
    `cad scene --tolerance` and the old no-args callers (page.py) use this."""
    props = view_props.get(name, {})
    dev = deviation if deviation is not None else props.get("deviation", gui.DEVIATION_DEFAULT)
    deg = props.get("angularDeflection", gui.ANGULAR_DEFLECTION_DEFAULT)
    ang = angular if angular is not None else math.radians(deg)
    return dev, ang


def _tessellate_bodies(shown: dict, colors: dict, view_props: dict,
                       deviation: float | None, angular: float | None) -> tuple[list, dict]:
    """Tessellate every body in `shown` with its own Deviation/AngularDeflection.
    ocp-tessellate's tessellate_group only takes one (deviation, angular_tolerance)
    pair for a whole call, so bodies are bucketed by their distinct effective pair
    (almost always just one bucket) and each bucket gets its own to_ocpgroup +
    tessellate_group call; the results are merged back into a single three-cad-
    viewer instances list and shapes tree, same shape as one call would have made.
    FreeCAD itself retessellates one object at a time the same way (onChanged on
    Deviation/AngularDeflection calls that object's own updateVisual())."""
    from ocp_tessellate.convert import tessellate_group, to_ocpgroup
    buckets: dict[tuple[float, float], list[str]] = {}
    for name in shown:
        buckets.setdefault(_effective_tessellation(view_props, name, deviation, angular), []).append(name)
    if not buckets:    # no bodies: still make one (empty) call, for a well-formed shapes tree
        buckets[(gui.DEVIATION_DEFAULT, math.radians(gui.ANGULAR_DEFLECTION_DEFAULT))] = []

    combined_inst: list = []
    combined_parts: list = []
    combined_bb: dict | None = None
    template: dict | None = None
    for (dev, ang), names in buckets.items():
        group, instances = to_ocpgroup(*[shown[n] for n in names], names=names,
                                       colors=[colors[n] for n in names])
        inst, shapes, _ = tessellate_group(group, instances,
                                           {"deviation": dev, "angular_tolerance": ang})
        offset = len(combined_inst)
        for part in shapes["parts"]:
            ref = part.get("shape")
            if isinstance(ref, dict) and "ref" in ref:
                ref["ref"] += offset
        combined_parts.extend(shapes["parts"])
        combined_inst.extend(inst)
        if template is None:
            template = shapes
        bb = shapes.get("bb")
        if bb:
            combined_bb = bb if combined_bb is None else {
                k: (min if k.endswith("min") else max)(combined_bb[k], bb[k]) for k in combined_bb}
    shapes = {**(template or {}), "parts": combined_parts, "bb": combined_bb}
    return combined_inst, shapes


def build_scene(slug: str, deviation: float | None = None, angular: float | None = None) -> dict:
    from .geom import bbox, mass_g
    from .verify import source_hash
    pdir = st.project_dir(slug)
    part_names = st.part_names(slug)
    base, _, _, axes = st.load_assembly(slug, placed=False)
    metas: dict = {}
    assembly = base is not None
    if not assembly:
        # No assembly.py: every part at its own origin, laid out along x.
        from build123d import Pos
        base, x = {}, 0.0
        for name in part_names:
            solid, metas[name] = st.build_part(slug, name)
            lo, hi = bbox(solid)
            base[name] = Pos(x - lo[0], 0, 0) * solid
            x += (hi[0] - lo[0]) + 20.0
    placed = placements.load(pdir)
    shown = placements.apply(base, placed)
    try:
        parts_meta = st.read_checks(slug).get("parts", {})
    except (FileNotFoundError, ValueError):
        parts_meta = {}
    bought = _bought_names(pdir)
    view_props = gui.load_view_props(pdir)

    bodies, lo_all, hi_all = [], [np.inf] * 3, [-np.inf] * 3
    for name, solid in base.items():
        part = _part_for(name, part_names)
        material = None
        if part:
            meta = metas.get(part) or parts_meta.get(part)
            if not meta or "material" not in meta:
                _, meta = st.build_part(slug, part)
            metas[part] = meta
            material = meta.get("material")
        kind = "made" if part else ("bought" if name in bought else "stock")
        color = (MATERIAL_COLOR.get((material or "").lower())
                 or (BOUGHT_COLOR if kind == "bought" else STOCK_COLOR if kind == "stock"
                     else PALETTE[zlib.crc32(name.encode()) % len(PALETTE)]))
        try:
            mass = round(mass_g(solid, material), 2) if material else None
        except KeyError:
            mass = None
        blo, bhi = bbox(solid)
        slo, shi = bbox(shown[name])
        lo_all = [min(lo_all[i], slo[i]) for i in range(3)]
        hi_all = [max(hi_all[i], shi[i]) for i in range(3)]
        center = [round((blo[i] + bhi[i]) / 2, 4) for i in range(3)]
        move = placed.get(name)
        bodies.append({
            "name": name, "path": f"/Group/{name}", "part": part, "kind": kind,
            # read from the file, not from checks.json, so the fields show what is there now
            "params": params_of(pdir / "parts" / f"{part}.py") if part else {},
            "material": material, "color": color, "mass_g": mass,
            "bbox": [[round(v, 4) for v in slo], [round(v, 4) for v in shi]],
            "center": center,
            "placement": {k: list(v) for k, v in move.items()} if move else None,
            "about": list(move["about"]) if move else center,
        })

    for b in bodies:                   # one part module can make several bodies
        b["used_by"] = [x["name"] for x in bodies if b["part"] and x["part"] == b["part"]]
    colors = {b["name"]: b["color"] for b in bodies}
    inst, shapes = _tessellate_bodies(shown, colors, view_props, deviation, angular)
    triangles = sum(int(np.asarray(i["triangles"]).size // 3) for i in inst)
    envelope = None
    spec_path = pdir / "spec.toml"
    if spec_path.exists():
        import tomllib
        try:
            envelope = tomllib.loads(spec_path.read_text()).get("envelope")
        except tomllib.TOMLDecodeError:
            envelope = None
    return {
        "format": FORMAT, "project": slug, "root": str(st.ROOT), "units": "mm",
        "written_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_hash": source_hash(pdir)[0],
        "assembly": assembly, "triangles": triangles,
        "bbox": [[round(v, 4) for v in lo_all], [round(v, 4) for v in hi_all]] if bodies else None,
        "bodies": bodies,
        "axes": [{"name": a.name, "moves": list(a.moves), "direction": list(a.direction),
                  "travel": list(a.travel), "work": list(a.work) if a.work else None}
                 for a in axes.values()],
        "envelope": envelope,
        "unknown_placements": sorted(set(placed) - set(base)),
        "viewer": {"instances": [_encode(i) for i in inst], "shapes": shapes},
    }


def write_scene(slug: str, deviation: float | None = None, angular: float | None = None) -> tuple[Path, dict]:
    import json
    scene = build_scene(slug, deviation, angular)
    out = st.project_dir(slug) / "out"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "scene.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(scene, separators=(",", ":"), default=plain))
    tmp.replace(path)
    return path, scene

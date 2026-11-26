"""CAD assembly -> MuJoCo: meshes, convex collision pieces, an MJCF and a JSON scene description.

    python -m cad_agent.sim_export pcb_conveyor --pose carrier --belt front_belt --belt rear_belt \
        --exclude test_board --out sim/out/pcb_conveyor_carrier

This runs in the CAD venv (build123d); it does not need MuJoCo. It writes, under `out`:

    <slug>.xml     an MJCF: one body named <slug>, welded to the world, holding every exported body's geoms
                   (a visual mesh in group 1, convex collision pieces in group 3); load it on its own to look at
                   the assembly, or attach it into a bigger scene (MjSpec.attach / frame.attach_body).
    scene.json     what a simulation needs beyond the MJCF: each body's role, its axis, its collision pieces,
                   bounding box (mm), the pose applied, and the path of every belt (see `belt_path`).
    meshes/*.stl   in mm, in the assembly's frame (the MJCF scales them by 0.001 to metres).

Collision. MuJoCo collides the convex hull of a mesh, so a non-convex body (a rail with a ledge, an L bracket)
collides as a lump unless it is split. `decompose` splits a solid into convex-ish pieces without any external
library: it cuts the solid's bounding box on every axis-aligned planar face it has, marks the cells the solid
fills, merges fully filled cells greedily into boxes (a partly filled cell, cut by a chamfer or a round, stays
its own piece), and intersects the solid with each box (an exact OCC boolean). Each
piece's hull is then what MuJoCo collides. This is exact for solids whose concave features are axis-aligned planes
(ledges, steps, slots, pockets: most machined and extruded parts); concavities that are not (holes, bores, V
grooves) are filled in by the hull, which is the usual approximation. A body that would need more than
`max_pieces` pieces, or more than `max_cells` cells, falls back to its whole hull and says so in scene.json.

Per-body modes (`collision={name: mode}`, default "auto"): "auto" (decompose, hull on fallback), "hull",
"boxes" (the merged boxes as primitive box geoms: fastest, loses chamfers), "none" (visual only).

Roles: "static" (default: fixed geoms), "belt" (visual only in the MJCF; its top run is described in scene.json so
the simulator can model it as a moving surface), "free" (a body with a free joint, from `free={name: density}`),
and excluded bodies (left out). Bodies an axis moves are grouped in a child body `axis_<name>`; with
`axes="joint"` that body gets a slide joint (range = the axis travel, measured from the exported pose) and a
position actuator holding it, otherwise it is fixed at the pose.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from xml.sax.saxutils import quoteattr

MM = 0.001
EPS = 1e-6


# ─── Geometry (build123d) ──────────────────────────────────────────────────────

def _planes(solid, k: int, min_gap: float) -> list[float]:
    """The solid's bounding planes on axis k: its bbox ends and every planar face whose normal is along k."""
    from build123d import GeomType
    bb = solid.bounding_box()
    lo, hi = (bb.min.X, bb.min.Y, bb.min.Z)[k], (bb.max.X, bb.max.Y, bb.max.Z)[k]
    cs = [lo, hi]
    for f in solid.faces():
        if f.geom_type != GeomType.PLANE:
            continue
        n = f.normal_at()
        if abs(abs((n.X, n.Y, n.Z)[k]) - 1.0) < 1e-6:
            c = f.center()
            cs.append((c.X, c.Y, c.Z)[k])
    cs = sorted(c for c in cs if lo - EPS <= c <= hi + EPS)
    out = [cs[0]]
    for c in cs[1:]:
        if c - out[-1] > min_gap:
            out.append(c)
    out[-1] = hi
    return out


def _box(x0, x1, y0, y1, z0, z1):
    from build123d import Box, Pos
    return Pos((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2) * Box(x1 - x0, y1 - y0, z1 - z0)


def _volume(shape) -> float:
    try:
        return float(shape.volume)
    except Exception:
        return 0.0


def decompose(solid, max_cells: int = 1500, max_pieces: int = 32, min_gap: float = 0.05, fill: float = 0.02):
    """Split `solid` into convex-ish pieces: [(build123d shape, (x0, x1, y0, y1, z0, z1)), ...], or None when it
    would take more than max_cells cells or max_pieces pieces (the caller falls back to the hull)."""
    g = [_planes(solid, k, min_gap) for k in range(3)]
    n = [len(c) - 1 for c in g]
    if n[0] * n[1] * n[2] > max_cells:
        return None
    filled = {}
    for i in range(n[0]):
        for j in range(n[1]):
            for k in range(n[2]):
                b = (g[0][i], g[0][i + 1], g[1][j], g[1][j + 1], g[2][k], g[2][k + 1])
                cell = (b[1] - b[0]) * (b[3] - b[2]) * (b[5] - b[4])
                if cell <= 0:
                    continue
                v = _volume(solid & _box(*b))
                if v > fill * cell:
                    filled[(i, j, k)] = "full" if v > 0.98 * cell else "part"
    # greedy merge: grow each unvisited filled cell along x, then y, then z
    seen, boxes = set(), []
    full = lambda i, j, k: filled.get((i, j, k)) == "full" and (i, j, k) not in seen
    for (i, j, k) in sorted(filled):
        if (i, j, k) in seen:
            continue
        if filled[(i, j, k)] == "part":      # a partly filled cell (a chamfer, a round) stays its own piece
            seen.add((i, j, k))
            boxes.append((g[0][i], g[0][i + 1], g[1][j], g[1][j + 1], g[2][k], g[2][k + 1]))
            if len(boxes) > max_pieces:
                return None
            continue
        i1 = i
        while full(i1 + 1, j, k):
            i1 += 1
        j1 = j
        while all(full(a, j1 + 1, k) for a in range(i, i1 + 1)):
            j1 += 1
        k1 = k
        while all(full(a, b, k1 + 1) for a in range(i, i1 + 1) for b in range(j, j1 + 1)):
            k1 += 1
        for a in range(i, i1 + 1):
            for b in range(j, j1 + 1):
                for c in range(k, k1 + 1):
                    seen.add((a, b, c))
        boxes.append((g[0][i], g[0][i1 + 1], g[1][j], g[1][j1 + 1], g[2][k], g[2][k1 + 1]))
        if len(boxes) > max_pieces:
            return None
    pieces = []
    for b in boxes:
        p = solid & _box(*b)
        if _volume(p) > EPS:
            pieces.append((p, b))
    return pieces


def belt_path(solid, travel_axis: int = 0) -> dict:
    """A flat belt drawn as its loop -> its top run, in mm: the end pulleys are the belt's cylindrical faces with
    the highest centres; the top run is tangent to their outer faces. Travel along x (axis 0) only, for now.

    Returns {"top_z", "y": [y0, y1], "run": [x_a, x_b] (the end pulleys' centres), "center_z", "r_out", "r_in",
    "thick", "width"}.
    """
    from build123d import GeomType
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    if travel_axis != 0:
        raise NotImplementedError("belt_path: belts travelling along x only")
    cyl = []
    for f in solid.faces():
        if f.geom_type == GeomType.CYLINDER:
            c = BRepAdaptor_Surface(f.wrapped).Cylinder()
            loc = c.Location()
            cyl.append((c.Radius(), loc.X(), loc.Z()))
    if not cyl:
        raise ValueError("belt_path: the belt has no cylindrical faces (wraps)")
    ztop = max(z for _, _, z in cyl)
    ends = [(r, x) for r, x, z in cyl if abs(z - ztop) < 1e-3]
    r_out, r_in = max(r for r, _ in ends), min(r for r, _ in ends)
    xs = sorted({round(x, 6) for _, x in ends})
    bb = solid.bounding_box()
    return {"top_z": ztop + r_out, "y": [bb.min.Y, bb.max.Y], "run": [xs[0], xs[-1]], "center_z": ztop,
            "r_out": r_out, "r_in": r_in, "thick": r_out - r_in, "width": bb.max.Y - bb.min.Y}


def _bbox(solid) -> list[float]:
    bb = solid.bounding_box()
    return [bb.min.X, bb.min.Y, bb.min.Z, bb.max.X, bb.max.Y, bb.max.Z]


# ─── MJCF writing (pure Python) ────────────────────────────────────────────────

def _attrs(**kw) -> str:
    return " ".join(f"{k}={quoteattr(str(v))}" for k, v in kw.items() if v is not None)


def write_mjcf(scene: dict, path: Path, axes_mode: str = "static") -> None:
    """The MJCF for a scene dict (as `export` builds it). Meshes are referenced relative to the MJCF's folder."""
    assets, geoms_by_group = [], {}
    s = f"{MM:g} {MM:g} {MM:g}"
    for b in scene["bodies"]:
        if b["role"] == "excluded":
            continue
        name = b["name"]
        key = "free:" + name if b["role"] == "free" else (b.get("axis") or "")
        out = geoms_by_group.setdefault(key, [])
        dens = b.get("density")
        assets.append(f'    <mesh {_attrs(name=name, file=b["mesh"], scale=s)}/>')
        rgba = {"belt": "0.15 0.15 0.15 1", "free": "0.1 0.5 0.2 1"}.get(b["role"], "0.7 0.72 0.75 1")
        out.append(f'      <geom {_attrs(name=name + "__vis", type="mesh", mesh=name, group=1, contype=0, conaffinity=0, rgba=rgba, mass=0)}/>')
        c = b["collision"]
        if b["role"] in ("belt",) or c["mode"] == "none":
            continue
        for i, p in enumerate(c.get("pieces", [])):
            gname = f"{name}__c{i}"
            if c["mode"] == "boxes":
                x0, x1, y0, y1, z0, z1 = p
                out.append(f'      <geom {_attrs(name=gname, type="box", group=3, rgba="1 0.4 0.2 0.3", pos=f"{(x0+x1)/2*MM:g} {(y0+y1)/2*MM:g} {(z0+z1)/2*MM:g}", size=f"{(x1-x0)/2*MM:g} {(y1-y0)/2*MM:g} {(z1-z0)/2*MM:g}", density=dens)}/>')
            else:
                assets.append(f'    <mesh {_attrs(name=gname, file=p, scale=s)}/>')
                out.append(f'      <geom {_attrs(name=gname, type="mesh", mesh=gname, group=3, rgba="1 0.4 0.2 0.3", density=dens)}/>')
    slug = scene["slug"]
    lines = [f'<mujoco model={quoteattr(slug)}>',
             '  <compiler angle="radian" autolimits="true"/>',
             '  <asset>', *assets, '  </asset>',
             '  <worldbody>',
             f'    <body name={quoteattr(slug)}>',
             *geoms_by_group.get("", [])]
    acts = []
    for ax, d in scene["axes"].items():
        g = geoms_by_group.get(ax)
        if not g:
            continue
        lines.append(f'      <body name={quoteattr("axis_" + ax)}>')
        if axes_mode == "joint":
            lo, hi = (t - d["position"] for t in d["travel"])
            lines.append(f'        <joint {_attrs(name="axis_" + ax, type="slide", axis=" ".join(f"{v:g}" for v in d["direction"]), range=f"{lo*MM:g} {hi*MM:g}", damping=100)}/>')
            acts.append(f'    <position {_attrs(name="axis_" + ax, joint="axis_" + ax, kp=1e5)}/>')
        lines += ["  " + x for x in g]
        lines.append('      </body>')
    lines.append('    </body>')
    for b in scene["bodies"]:
        if b["role"] != "free":
            continue
        g = geoms_by_group.pop("free:" + b["name"], [])
        lines += [f'    <body name={quoteattr(b["name"])}>', '      <freejoint/>', *g, '    </body>']
    lines.append('  </worldbody>')
    if acts:
        lines += ['  <actuator>', *acts, '  </actuator>']
    lines.append('</mujoco>')
    path.write_text("\n".join(lines) + "\n")


# ─── The exporter ──────────────────────────────────────────────────────────────

def export(slug: str, out: str | Path, pose: str | None = None, belts=(), exclude=(), free: dict | None = None,
           collision: dict | None = None, axes_mode: str = "static", tolerance: float = 0.05,
           max_pieces: int = 32, log=print) -> dict:
    """Export assembly `slug` (at POSES[pose], if given) to `out`. Returns the scene dict also written to
    scene.json. `belts`: names of flat-belt bodies to describe as moving surfaces; `exclude`: names to leave out;
    `free`: {name: density kg/m^3} for bodies to simulate as free; `collision`: {name: mode}."""
    from build123d import export_stl
    from .state import load_machine
    from .subassembly import apply_pose
    out = Path(out)
    (out / "meshes").mkdir(parents=True, exist_ok=True)
    m = load_machine(slug, describe=False)
    if m is None:
        raise SystemExit(f"{slug}: no assembly.py")
    parts = apply_pose(m, pose) if pose else dict(m.parts)
    positions = dict(m.poses.get(pose, {})) if pose else {}
    free, collision = dict(free or {}), dict(collision or {})
    unknown = [n for n in (*belts, *exclude, *free, *collision) if n not in parts]
    if unknown:
        raise SystemExit(f"not bodies of {slug}: {unknown}")
    axis_of = {b: a for a, ax in m.axes.items() for b in ax.moves}
    scene = {"slug": slug, "pose": pose, "units": "mm", "mjcf_scale": MM,
             "axes": {a: {"moves": list(ax.moves), "direction": list(ax.direction), "travel": list(ax.travel),
                          "position": float(positions.get(a, 0.0))} for a, ax in m.axes.items()},
             "bodies": [], "belts": {}}
    for name, solid in parts.items():
        role = ("excluded" if name in exclude else "belt" if name in belts else "free" if name in free
                else "static")
        body = {"name": name, "role": role, "axis": axis_of.get(name), "bbox": _bbox(solid)}
        scene["bodies"].append(body)
        if role == "excluded":
            continue
        body["mesh"] = f"meshes/{name}.stl"
        export_stl(solid, str(out / body["mesh"]), tolerance=tolerance, angular_tolerance=0.2)
        if role == "belt":
            scene["belts"][name] = belt_path(solid)
            body["collision"] = {"mode": "none"}
            continue
        if role == "free":
            body["density"] = free[name]
        mode = collision.get(name, "auto")
        c = {"mode": mode}
        if mode in ("auto", "boxes"):
            pieces = decompose(solid, max_pieces=max_pieces)
            if pieces is None:
                c = {"mode": "hull", "note": "decomposition too fine; collides as its hull"}
                log(f"  {name}: decomposition over the limits, using its hull")
            elif mode == "boxes":
                c["pieces"] = [list(b) for _, b in pieces]
            else:
                c = {"mode": "pieces", "pieces": []}
                for i, (p, _) in enumerate(pieces):
                    f = f"meshes/{name}__c{i}.stl"
                    export_stl(p, str(out / f), tolerance=tolerance, angular_tolerance=0.2)
                    c["pieces"].append(f)
        if c["mode"] == "hull":
            c["pieces"] = [body["mesh"]]
        body["collision"] = c
        log(f"  {name}: {role}, collision {c['mode']} ({len(c.get('pieces', []))} piece(s))")
    write_mjcf(scene, out / f"{slug}.xml", axes_mode)
    (out / "scene.json").write_text(json.dumps(scene, indent=1))
    log(f"wrote {out / (slug + '.xml')} and scene.json")
    return scene


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m cad_agent.sim_export", description=__doc__.split("\n")[0])
    ap.add_argument("slug")
    ap.add_argument("--out", required=True)
    ap.add_argument("--pose")
    ap.add_argument("--belt", action="append", default=[], help="a flat-belt body to model as a moving surface")
    ap.add_argument("--exclude", action="append", default=[])
    ap.add_argument("--free", action="append", default=[], help="NAME=DENSITY (kg/m^3): simulate as a free body")
    ap.add_argument("--collision", action="append", default=[], help="NAME=MODE (auto|hull|boxes|none)")
    ap.add_argument("--axes", choices=("static", "joint"), default="static")
    ap.add_argument("--tolerance", type=float, default=0.05, help="mesh tolerance, mm")
    a = ap.parse_args(argv)
    kv = lambda xs, f: {k: f(v) for k, v in (x.split("=", 1) for x in xs)}
    export(a.slug, a.out, pose=a.pose, belts=a.belt, exclude=a.exclude, free=kv(a.free, float),
           collision=kv(a.collision, str), axes_mode=a.axes, tolerance=a.tolerance)


if __name__ == "__main__":
    sys.exit(main())

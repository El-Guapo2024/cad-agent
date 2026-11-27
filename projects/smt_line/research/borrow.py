"""Bring the two borrowed designs into projects/smt_line/bought/ as STEP files, from the open sources themselves.

    .venv/bin/python -I projects/smt_line/research/borrow.py <lumenpnp clone> <lumenpnp-archive conveyor-branch clone>

  pnp_v4.step       the LumenPnP v4 (Opulo, CERN-OHL-W v2), src/assembly.FCStd at github.com/opulo-inc/lumenpnp,
                    in its own frame (x across, y front to back, z up; the lower side extrusions' tops at z 40).
                    Kept: frame, legs, plates, gantry, head, cameras, nozzle rack, control box. Left out: fasteners,
                    belts, cable clips and tubes (no bearing on the fit, and 400 MB with them); the strip feeders
                    and the board holder (the conveyor takes their place); the two rear staging plates (the
                    conveyor's rollers and rails pass where they were).
  pnp_conveyor.step the conveyor prototype from the `conveyor` branch of github.com/opulo-inc/lumenpnp-archive
                    (Opulo, 2021, GPL-3.0), drawn for the Index (LumenPnP's predecessor, y up), every body of it:
                    aluminium-angle rails (McMaster 8982K546), 608ZZ end rollers, the four frame mounts, SG90 clamp
                    servos with their cams, clamps and guides, the width knobs. Moved, not changed: turned from the
                    Index's y-up frame into the LumenPnP's z-up one (rails along x), its mounts on the same 20x20
                    lower side extrusions they were drawn for, and slid 90 mm back along them so the front mounts
                    clear the LumenPnP's control box (the Index had none there).

Opulo's notice, which the licence asks every derivative to carry: "LumenPnP is (c) by Opulo. This notice must be
included in any distributions of this project or derivative works." The names LumenPnP and Opulo are Opulo's marks,
so the parts are called pnp_* here and the credit is in the sidecars.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from fcstd_read import Doc, bbox, resolve, world          # noqa: E402

from OCP.gp import gp_Trsf, gp_Vec                          # noqa: E402
from OCP.TopLoc import TopLoc_Location              # noqa: E402
from build123d import Compound, Shape, export_step  # noqa: E402

BOUGHT = HERE.parent / "bought"

DROP = re.compile(r"screw|nut|washer|bhcs|shcs|clip|belt|tube|tee|union|cable|strip-feeder|board-support|t-nut|"
                  r"^Body0(0[89]|1\d|20)$|^Body001$|mobo", re.I)
# Body008/009: the rear staging plates. Body001, Body010..020: the board holder's clamps and slats.

# The Index's frame into the LumenPnP's: x' = -z + 20.5, y' = -x + 90, z' = y + 20.1. A proper turn (det +1).
# 20.5 and 20.1 put the Index's lower side extrusion (x 0..20 along its z, top at y 19.9) on the LumenPnP's
# (x 0..20, top at z 40); 90 is the slide back along it.
CONV_SHIFT = (20.5, 90.0, 20.1)
# Then each corner onto the LumenPnP's own extrusions. Opulo's two CADs of the same frame differ by tenths (the
# Index's lower side extrusions map to x 0..20 and 580.5..600.5; the LumenPnP's sit at x -0.0637..19.9363 and
# 580.0685..600.0685, their tops at z 40.0674 and 40.0043), while each mount's channel is exactly the extrusion's
# 20.000. So `fit_corners` measures the faces and moves each corner (its mount, rollers, washers, knob) to centre the
# mount's channel on its extrusion with the channel's ceiling on the extrusion's top (0.02 to 0.52 mm), and each rail,
# with the clamp and servo on it, up until it rests on the higher (left) extrusion's top, which brings both ledges to
# one height; along x a rail moves as its left mounts do, which it slides in.
MOUNT = re.compile(r"FDM-00(2[89]|3[01])")


def bodies(path):
    d = Doc.get(path)
    for n, t in d.types.items():
        if t == "App::Link" or (t in ("Part::Feature", "Part::FeaturePython", "PartDesign::Body") and d.shape(n) is not None):
            if not d.visible(n):
                continue
            s = resolve(d, n)
            if s is None or s.IsNull():
                continue
            yield d.label(n), world(d, n, s)


def corner(s):
    """Which end of the conveyor a body is at ("middle": the rails, and the clamps at mid-span), and which side."""
    x0, y0, _, x1, y1, _ = bbox(s)
    end = "middle" if x1 - x0 > 300 or 100 < (x0 + x1) / 2 < 500 else ("left" if x1 < 300 else "right")
    return end, ("front" if (y0 + y1) / 2 < 342.5 else "back")


def planes(s, axis):
    """(position, area, facing +1/-1) of each flat face of a body square to x, y or z."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepGProp import BRepGProp
    from OCP.GeomAbs import GeomAbs_Plane
    from OCP.GProp import GProp_GProps
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    e = TopExp_Explorer(s, TopAbs_FACE)
    while e.More():
        f = TopoDS.Face(e.Current()); a = BRepAdaptor_Surface(f)
        if a.GetType() == GeomAbs_Plane:
            n = getattr(a.Plane().Axis().Direction(), axis)()
            if abs(abs(n) - 1) < 1e-9:
                g = GProp_GProps(); BRepGProp.SurfaceProperties_s(f, g)
                out = 1 if (n > 0) != (f.Orientation() == TopAbs_REVERSED) else -1
                yield getattr(a.Plane().Location(), axis)(), g.Mass(), out
        e.Next()


def move(s, d):
    f = gp_Trsf(); f.SetTranslation(gp_Vec(*d)); return s.Moved(TopLoc_Location(f))


def fit_corners(conv, ext):
    """The move for each corner and each rail that seats it on the extrusions, from their faces."""
    side = {k: (min(x for x, a, _ in planes(e, "X") if a > 2000), max(z for z, a, _ in planes(e, "Z") if a > 2000))
            for k, e in ext.items()}                       # each extrusion's low x face and its top
    fix = {}
    for lab, s in conv:
        if MOUNT.match(lab):
            end, _ = c = corner(s)
            x_lo, top = side[end]
            chan = min((x for x, a, o in planes(s, "X") if o > 0), key=lambda x: abs(x - x_lo))  # faces +x: the channel's low wall
            ceil = min((z for z, a, o in planes(s, "Z") if o < 0), key=lambda z: abs(z - top))   # faces down: on the top
            assert abs(chan - x_lo) < 1 and abs(ceil - top) < 1, (lab, chan, ceil)
            fix[c] = (x_lo - chan, 0.0, top - ceil)
    for lab, s in conv:
        if "8982K546" in lab:
            _, sd = c = corner(s)
            bottom = min(z for z, a, o in planes(s, "Z") if o < 0)
            fix[c] = (fix[("left", sd)][0], 0.0, max(t for _, t in side.values()) - bottom)
    return fix


def flat_tops(s):
    """The heights of the upward-facing flat faces of a body: the conveyor's ledges, for the board's height."""
    return [z for z, _, o in planes(s, "Z") if o > 0]


def write(name, shapes, sidecar):
    p = BOUGHT / f"{name}.step"
    export_step(Compound([Shape(s) for s in shapes]), str(p))
    sidecar["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
    p.with_suffix(".json").write_text(json.dumps(sidecar, indent=1) + "\n")
    print(f"wrote {p.name}: {len(shapes)} bodies, {p.stat().st_size / 1e6:.1f} MB")


def main(lumen, archive):
    pnp = [(lab, s) for lab, s in bodies(Path(lumen) / "src" / "assembly.FCStd") if not DROP.search(lab)]
    keep = [s for _, s in pnp]
    frame = dict(pnp)
    write("pnp_v4", keep, {
        "source": "https://github.com/opulo-inc/lumenpnp src/assembly.FCStd (LumenPnP v4), read by tools/fcstd_read.py",
        "vendor": "Opulo (open hardware)", "licence": "CERN-OHL-W-2.0",
        "notice": "LumenPnP is (c) by Opulo. This notice must be included in any distributions of this project or derivative works.",
        "verified": True, "geometry": "exact",
        "changes": "fasteners, belts, cables, strip feeders, board holder, the motherboard (inside the control box) and the two rear staging plates left out"})

    t = gp_Trsf()
    tx, ty, tz = CONV_SHIFT
    t.SetValues(0, 0, -1, tx,  -1, 0, 0, ty,  0, 1, 0, tz)
    conv = []
    for lab, s in bodies(Path(archive) / "pnp" / "cad" / "assembly.FCStd"):
        if not re.match(r"(FDM-00(2[89]|3[0-6])|OTS-000[4-8])", lab):
            continue
        s = s.Moved(TopLoc_Location(t))
        conv.append((lab, s))
    ext = {"left": frame["vslot-extrusion-20mmx20mmx600mm003"], "right": frame["vslot-extrusion-20mmx20mmx600mm001"]}
    fix = fit_corners(conv, ext)
    conv = [move(s, fix[corner(s)]) for lab, s in conv]
    ledges = sorted({round(z, 9) for c in conv for z in flat_tops(c) if 41 < z < 43})
    print("ledge tops (z, pick-and-place frame):", ledges)
    write("pnp_conveyor", conv, {
        "source": "https://github.com/opulo-inc/lumenpnp-archive/tree/conveyor pnp/cad/assembly.FCStd (Index conveyor prototype, 2021)",
        "vendor": "Opulo (open hardware)", "licence": "GPL-3.0",
        "notice": "LumenPnP is (c) by Opulo. This notice must be included in any distributions of this project or derivative works.",
        "verified": False, "geometry": "exact",
        "changes": f"turned from the Index's y-up frame to z-up and moved by {CONV_SHIFT}, then each corner by {({k if isinstance(k, str) else '-'.join(k): tuple(round(v, 4) for v in d) for k, d in fix.items()})} to sit on the LumenPnP's own extrusions; no body changed. Unverified: "
                   "a prototype Opulo never released; its parts list has a NEMA14 (not placed in the CAD) and no belt, so how it drove the board is not drawn"})


if __name__ == "__main__":
    main(*sys.argv[1:3])

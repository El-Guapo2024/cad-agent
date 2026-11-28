"""Bring the two borrowed designs into projects/smt_line/bought/ as STEP files, from the open sources themselves.

    .venv/bin/python -I projects/smt_line/research/borrow.py <lumenpnp clone> <Rapid-Star clone>

  pnp_v4.step       the LumenPnP v4 (Opulo, CERN-OHL-W v2), src/assembly.FCStd at github.com/opulo-inc/lumenpnp,
                    in its own frame (x across, y front to back, z up; the lower side extrusions' tops at z 40).
                    Kept: frame, legs, plates, gantry, head, cameras, nozzle rack, control box. Left out: fasteners,
                    belts, cable clips and tubes (no bearing on the fit, and 400 MB with them); the strip feeders
                    and the board holder (the conveyor takes their place); the two rear staging plates (the
                    conveyor's rollers and rails pass where they were).
  pnp_conveyor.step the PCB conveyor of Deltaprintr's Rapid Star (github.com/Deltaprintr/Rapid-Star, Mechanics/
                    Machine Assembly v27.step; CC BY-NC-SA 4.0, used with Deltaprintr's permission, which Juan got
                    on 2026-11-27): its two `Conveyer` sub-assemblies, every body but the fasteners and the corner
                    brackets (those bolt to Rapid Star's own frame). Each is a 2020 rail, 640 long, carrying a 4 mm
                    flat belt on five 13 mm pulleys, driven by an N20 gear motor at one end; a guide plate, two
                    hoods, a servo-lifted gripper bar that clamps the board up against the hoods, a limit-switch
                    board, and on one rail the board-stop solenoid. Moved, not changed: turned from Rapid Star's
                    y-up frame to z-up with the rails along x, the rails standing on 23 mm blocks across the tops
                    of the LumenPnP's lower side extrusions (see RS_LIFT), the front rail's guide on the line Opulo's
                    own conveyor prototype ran its front wall (y 270.6), the back rail 143.9 behind it for a
                    140-wide board (Rapid Star fixes its rails at one spacing, set here for our board), and along x so the
                    guides end 1.05 mm short of the oven's end roller.

Opulo's notice, which the licence asks every derivative to carry: "LumenPnP is (c) by Opulo. This notice must be
included in any distributions of this project or derivative works." Rapid Star's licence asks for credit to
Deltaprintr and the same licence on adaptations. LumenPnP, Opulo, Deltaprintr and Rapid Star are their owners' marks,
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

RS_DROP = re.compile(r"screw|nut|washer|standoff|corner_bracket", re.I)
# Rapid Star is drawn y-up: x' = x, y' = -z, z' = y.
RS_UP = (1, 0, 0, 0,  0, 0, -1, 0,  0, 1, 0, 0)
RS_FRONT_GUIDE_Y = 270.6     # where Opulo's prototype had its front wall: clear of the LumenPnP's control box
RS_LANE = 143.9              # guide to guide: a 140-wide board with 3.9 to spare, as Opulo's prototype had it
# Rapid Star's frame is 640 wide and the LumenPnP's 600. Each guide plate hangs 21.6 below its rail at x 220..280 from
# the rail's middle, to carry the lower pulleys, which on Rapid Star is inside its side extrusions; on the LumenPnP the
# +x one lands on the right side extrusion. So each rail end stands on a bought 23 mm block (assembly.py `rail_blocks`),
# which lifts the guides 1.4 clear of the extrusions' tops, and no part of Rapid Star's is changed.
# The lift can't be more than 23.3: the front guide's -x end then meets a LumenPnP part outside its left side
# extrusion (x -60.7..-20.7, its bottom at z 84.4). At 23.0 the guide clears both by 1.4.
RS_LIFT = 23.0
# The guides run 9.1 past the belts at each end. Along x, the guides end 1.05 short of the IN6's end roller (its front
# at x 657.00 as the check measures it), which puts the belts' end 10.2 from it.
RS_GUIDE_END_X = 655.95
# Lifted, the front rail's limit-switch board (it stands 8 above the rail, at the rail's -x end) reaches into the
# LumenPnP's upper left side extrusion (x 0..20). It bolts to the rail's T-slot, so it slides along the rail to 1 mm
# inside the extrusion's inner face. The back rail's switch is at the +x end, outside the frame, 3.9 clear.
UPPER_EXTRUSION_X = 20.0     # the upper left side extrusion's inner face (pnp_v4)


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


def trsf(v):
    t = gp_Trsf(); t.SetValues(*v); return t


def rapid_star(path):
    """Each Rapid Star conveyor's bodies, in z-up Rapid Star coordinates, and which side it is ('front'/'back')."""
    from build123d import import_step
    a = import_step(str(path))
    convs = [c for c in a.children if re.match(r"Conveyer_v\d+", c.label)]
    assert len(convs) == 2, [c.label for c in a.children]
    up = trsf(RS_UP)
    out = {}
    for c in convs:
        m = up.Multiplied(c.location.wrapped.Transformation())
        bodies_ = [(k.label, k.wrapped.Moved(TopLoc_Location(m))) for k in c.children if not RS_DROP.search(k.label)]
        rail = next(s for lab, s in bodies_ if lab.startswith("2020-640"))
        out["front" if (bbox(rail)[1] + bbox(rail)[4]) / 2 < 0 else "back"] = bodies_
    return out


def guide_face(bodies_, side):
    """The guide plate's face the board's edge runs against: the inner (lane) side of the guide."""
    g = next(s for lab, s in bodies_ if lab.startswith("Conveyer_Guide"))
    ys = [(y, a) for y, a, o in planes(g, "Y") if a > 5000 and (o > 0) == (side == "front")]
    return max(ys, key=lambda t: t[1])[0]


def flat_tops(s):
    """The heights of the upward-facing flat faces of a body: the conveyor's ledges, for the board's height."""
    return [z for z, _, o in planes(s, "Z") if o > 0]


def write(name, shapes, sidecar):
    p = BOUGHT / f"{name}.step"
    export_step(Compound([Shape(s) for s in shapes]), str(p))
    sidecar["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
    p.with_suffix(".json").write_text(json.dumps(sidecar, indent=1) + "\n")
    print(f"wrote {p.name}: {len(shapes)} bodies, {p.stat().st_size / 1e6:.1f} MB")


def main(lumen, rs):
    pnp = [(lab, s) for lab, s in bodies(Path(lumen) / "src" / "assembly.FCStd") if not DROP.search(lab)]
    keep = [s for _, s in pnp]
    frame = dict(pnp)
    write("pnp_v4", keep, {
        "source": "https://github.com/opulo-inc/lumenpnp src/assembly.FCStd (LumenPnP v4), read by tools/fcstd_read.py",
        "vendor": "Opulo (open hardware)", "licence": "CERN-OHL-W-2.0",
        "notice": "LumenPnP is (c) by Opulo. This notice must be included in any distributions of this project or derivative works.",
        "verified": True, "geometry": "exact",
        "changes": "fasteners, belts, cables, strip feeders, board holder, the motherboard (inside the control box) and the two rear staging plates left out"})

    convs = rapid_star(Path(rs) / "Mechanics" / "Machine Assembly v27.step")
    top = max(max(z for z, a, _ in planes(frame[k], "Z") if a > 2000)
              for k in ("vslot-extrusion-20mmx20mmx600mm003", "vslot-extrusion-20mmx20mmx600mm001"))
    rail_bottom = min(bbox(s)[2] for side in convs.values() for lab, s in side if lab.startswith("2020-640"))
    guide_end = max(bbox(s)[3] for side in convs.values() for lab, s in side if lab.startswith("Conveyer_Guide"))
    dx, dz = RS_GUIDE_END_X - guide_end, top + RS_LIFT - rail_bottom
    move_by = {}
    for side, want in (("front", RS_FRONT_GUIDE_Y), ("back", RS_FRONT_GUIDE_Y + RS_LANE)):
        move_by[side] = (dx, want - guide_face(convs[side], side), dz)
    conv = []
    for side, bs in convs.items():
        for lab, s in bs:
            s = move(s, move_by[side])
            if lab.startswith("Conveyor_Limit_Switch") and bbox(s)[0] < UPPER_EXTRUSION_X + 1.0:
                slide = UPPER_EXTRUSION_X + 1.0 - bbox(s)[0]
                print(f"slid {lab} {slide:.3f} along its rail")
                s = move(s, (slide, 0.0, 0.0))
            conv.append(s)
    belts = sorted({round(z, 6) for side, bs in convs.items() for lab, s in bs if lab.startswith("Belt")
                    for z in flat_tops(move(s, move_by[side]))})
    print("belt tops (z, pick-and-place frame):", belts)
    print("rails span x", [tuple(round(v, 3) for v in (bbox(move(s, move_by[sd]))[0], bbox(move(s, move_by[sd]))[3]))
                           for sd, bs in convs.items() for lab, s in bs if lab.startswith("2020-640")])
    print("conveyor reaches x", round(max(bbox(c)[3] for c in conv), 3))
    print("belts end at x", round(max(bbox(move(s, move_by[sd]))[3] for sd, bs in convs.items() for lab, s in bs if lab.startswith("Belt")), 3))
    write("pnp_conveyor", conv, {
        "source": "https://github.com/Deltaprintr/Rapid-Star Mechanics/Machine Assembly v27.step, the two Conveyer sub-assemblies",
        "vendor": "Deltaprintr (open hardware)", "licence": "CC BY-NC-SA 4.0; used with Deltaprintr's permission (Juan, 2026-11-27)",
        "notice": "Rapid Star conveyor by Deltaprintr (deltaprintr.com), CC BY-NC-SA 4.0. Deltaprintr and Rapid Star are trademarks of Deltaprinter Inc.",
        "verified": False, "geometry": "exact",
        "changes": f"fasteners and the corner brackets (for Rapid Star's own frame) left out; turned from y-up to z-up; moved, front conveyor by {tuple(round(v, 4) for v in move_by['front'])}, back by {tuple(round(v, 4) for v in move_by['back'])}, so the rails stand on {RS_LIFT} mm blocks on the LumenPnP's lower side extrusions, the lane is {RS_LANE} guide to guide, and the guides end at x {RS_GUIDE_END_X}; the front rail's limit-switch board slid along its rail's T-slot to 1 mm inside the LumenPnP's upper left side extrusion; no body's shape changed. Unverified: how the rails fasten to the blocks and extrusions is not drawn"})


if __name__ == "__main__":
    main(*sys.argv[1:3])

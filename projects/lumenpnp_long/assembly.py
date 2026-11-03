"""LumenPnP v4.2.0 with its Y axis 300 mm longer: the base of the one-machine PCB fab.

The `lumenpnp` project's own STEPs (Opulo's assembly, CERN-OHL-W v2; see lumenpnp/assembly.py), changed only by a
stretch at y = YS: a part that runs the whole length (the side frames' two 2020 extrusions, the MGN rail, the belt
runs) is cut there and its own section extruded DY to fill the gap, so it keeps its real profile; a part behind YS
(the rear legs and brackets, the rear feeder rail, what the user fits there) moves DY back; the Y cable chain's lower
run is repeated over the gap. What rides on the gantry stays where it is. Opulo's staging plate and strip feeders are left out (FAB_CLEAR). To buy: the 2020s 900 instead of 600, the
MGN12 rail 850 instead of 550, the Y belts 600 mm longer each, and a longer Y cable chain.

A stretched group is a modified copy of Opulo's, so it is stock here (no declared mass).
"""
from build123d import Box, Compound, Keep, Plane, Pos, Solid, Vector
from cad_agent.state import bought_solid

BASE = "lumenpnp"
YS, DY = 400.0, 300.0                  # the cut, in front of the rear feeder rail (y 410) and behind the Y carriage
LONG_MM = 300.0                        # a part longer than this along y that crosses YS is stretched
GROUPS = ("y_gantry_left", "y_gantry_right", "x_gantry", "front_feeder_rail", "rear_feeder_rail",
          "y_limit_striker", "x_drag_chain_asm", "y_drag_chain_asm", "components_installed_by_user")
# Opulo's staging plate and optional strip feeders are left out: the fab's fixture (fab_stage) holds the board, and
# it travels where they stood. So does what the user installs inside FAB_CLEAR (the strip feeders' parts and a parts
# tray in the middle of the bed): the fixture's swept box, x and y in this frame, z from below the bed up.
FAB_CLEAR = ((80.0, 55.0, -150.0), (454.0, 675.0, 60.0))      # from x 80: the nozzle rack (x 51 to 75) stays
MOVED = {"rear_feeder_rail"}           # wholly behind the cut
KEPT = {"x_gantry", "x_drag_chain_asm", "front_feeder_rail", "y_limit_striker"}

CLEARANCE = {}
ALLOW_CONTACT = {"frame|gantry"}          # the Y carriages on their rails
GANTRY_Y = (-100.0, 240.0)                # pcbfab's Y travel, which pcbfab declares (with what it adds to the gantry)


def _pieces(shape):
    return shape if isinstance(shape, list) else [shape]


def _stretch(so):
    cut = Plane(origin=(0, YS, 0), z_dir=(0, 1, 0))
    front = _pieces(so.split(cut, keep=Keep.BOTTOM))
    back = _pieces(so.split(cut, keep=Keep.TOP))
    out = list(front) + [Pos(0, DY, 0) * b for b in back]
    for f in front:
        for face in f.faces():
            if abs(face.center().Y - YS) < 1e-3 and abs(abs(face.normal_at().Y) - 1.0) < 1e-6:
                out.append(Solid.extrude(face, Vector(0, DY, 0)))
    return out


def _clear(b, dy):
    (x0, y0, z0), (x1, y1, z1) = FAB_CLEAR
    return not (b.min.X > x1 or b.max.X < x0 or b.min.Y + dy > y1 or b.max.Y + dy < y0 or b.min.Z > z1
                or b.max.Z < z0)


def _longer(g):
    solids = bought_solid(BASE, g).solids()
    out = []
    for so in solids:
        b = so.bounding_box()
        if g == "components_installed_by_user" and _clear(b, DY if (b.min.Y + b.max.Y) / 2.0 > YS else 0.0):
            continue
        cy = (b.min.Y + b.max.Y) / 2.0
        if b.max.Y - b.min.Y > LONG_MM and b.min.Y < YS < b.max.Y:
            out += _stretch(so)
        elif cy > YS:
            out.append(Pos(0, DY, 0) * so)
        else:
            out.append(so)
            if g == "y_drag_chain_asm" and cy > YS - DY and b.max.Z < 100.0:    # the chain's lower run
                out.append(Pos(0, DY, 0) * so)
    return Compound(out)


def _groups():
    out = {}
    for g in GROUPS:
        if g in KEPT:
            out[g] = bought_solid(BASE, g)
        elif g in MOVED:
            out[g] = Pos(0, DY, 0) * bought_solid(BASE, g)
        else:
            out[g] = _longer(g)
    return out


def _inside(b, c, pad=0.5):
    return (c.min.X - pad <= b.min.X and b.max.X <= c.max.X + pad and c.min.Y - pad <= b.min.Y
            and b.max.Y <= c.max.Y + pad and c.min.Z - pad <= b.min.Z and b.max.Z <= c.max.Z + pad)


def _near(b, c, pad=0.5):
    return not (b.min.X > c.max.X + pad or c.min.X > b.max.X + pad or b.min.Y > c.max.Y + pad
                or c.min.Y > b.max.Y + pad or b.min.Z > c.max.Z + pad or c.min.Z > b.max.Z + pad)


def _repeats(so, b, others, plate):
    """Whether a solid of the same size sits at the same x and z along y outside the carriage plate: a rail's
    screw, not the carriage's."""
    size = (b.max.X - b.min.X, b.max.Y - b.min.Y, b.max.Z - b.min.Z)
    for o, ob in others:
        if o is so or (ob.max.Y > plate.min.Y - 10.0 and ob.min.Y < plate.max.Y + 10.0):
            continue
        if (abs(ob.min.X - b.min.X) < 0.1 and abs(ob.min.Z - b.min.Z) < 0.1
                and all(abs(u - v) < 0.1 for u, v in zip(size, (ob.max.X - ob.min.X, ob.max.Y - ob.min.Y,
                                                                 ob.max.Z - ob.min.Z)))):
            return True
    return False


def parts():
    """Two bodies, by what moves: the gantry (what LumenPnP's Y carries) and the frame (the rest).

    Opulo's groups are its assembly's, not its motion's: the Y carriages, their screws and the user's screws in the
    gantry sit in the side frames' groups and the user's group, so a gantry moved on its own drives through its own
    carriages, and every screw that Opulo's model draws in an undrilled part overlaps a neighbouring group. Taken by
    motion, a screw is inside the body it holds together, and the fit and sweep rules judge the gantry against the
    frame. The gantry: x_gantry and x_drag_chain_asm whole; from the side frames' groups, what lies inside the Y
    carriage plates' boxes (y 174 to 286 at home) except the rail's own screws, which repeat along it; from the
    user's group, what touches any of those. The Y cable chain is flexible: its bend rolls between its runs at half
    the gantry's speed, so no rigid split of it moves right. Where a rail or a belt run passes through a moving part,
    the part gets the channel its real one has (_channels). Its lower run (on the frame) is kept; its bend and upper
    run are left out of this model (Opulo's chain, used as designed; nothing of the fab's comes within 24 mm of it).
    """
    g = _groups()
    gantry = list(g["x_gantry"].solids()) + list(g["x_drag_chain_asm"].solids())
    frame = []
    for side in ("y_gantry_left", "y_gantry_right"):
        sol = [(so, so.bounding_box()) for so in g[side].solids()]
        plate = max((b for so, b in sol if b.max.Y - b.min.Y < 200 and b.min.Z > 60),
                    key=lambda b: (b.max.X - b.min.X) * (b.max.Y - b.min.Y) * (b.max.Z - b.min.Z))
        for so, b in sol:
            moving = _inside(b, plate, pad=10.0) and not _repeats(so, b, sol, plate)
            (gantry if moving else frame).append(so)
    for so in g["y_drag_chain_asm"].solids():
        b = so.bounding_box()
        if (b.min.Z + b.max.Z) / 2.0 < 65.0:                       # the lower run, on the frame
            frame.append(so)
    for n in ("front_feeder_rail", "rear_feeder_rail", "y_limit_striker"):
        frame += list(g[n].solids())
    gb = [so.bounding_box() for so in gantry]
    for so in g["components_installed_by_user"].solids():
        b = so.bounding_box()
        (gantry if any(_near(b, c) for c in gb) else frame).append(so)
    return {"frame": Compound(frame), "gantry": Compound(_channels(gantry, frame))}


def _channels(gantry, frame):
    """The moving solids with a channel where a rail or a belt run of the frame passes through them.

    Opulo draws an MGN carriage block, and the carriage plate the Y belt runs through, as solids with no channel,
    so at home the block sits in its rail. A run is a frame solid more than LONG_MM along y; its box, run out
    over the whole travel, is cut from every moving solid it reaches: the channel the real part has.
    """
    runs = [so.bounding_box() for so in frame]
    runs = [b for b in runs if b.max.Y - b.min.Y > LONG_MM]
    lo, hi = GANTRY_Y
    out = []
    for so in gantry:
        b = so.bounding_box()
        for r in runs:
            if r.min.Y + lo > b.max.Y or r.max.Y + hi < b.min.Y or not _near(b, r, pad=0.0):
                continue
            if b.min.X > r.max.X or r.min.X > b.max.X or b.min.Z > r.max.Z or r.min.Z > b.max.Z:
                continue
            cut = Pos((r.min.X + r.max.X) / 2.0, (b.min.Y + b.max.Y) / 2.0, (r.min.Z + r.max.Z) / 2.0) * Box(
                r.max.X - r.min.X, b.max.Y - b.min.Y + 2.0, r.max.Z - r.min.Z)
            so = so - cut
            so = so.solids()[0] if hasattr(so, "solids") and len(so.solids()) == 1 else so
        out += list(so.solids()) if hasattr(so, "solids") else [so]
    return out

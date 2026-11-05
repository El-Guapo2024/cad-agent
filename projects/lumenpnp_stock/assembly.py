"""LumenPnP v4.2.0 as Opulo sells it: the pick-and-place of the PCB line, with the fab's process tools on its head.

The `lumenpnp` project's own STEPs (Opulo's assembly, CERN-OHL-W v2; see lumenpnp/assembly.py), unchanged, taken as
two bodies by what moves (parts() below), as lumenpnp_long does for its longer frame. Its optional strip feeders
are left out, and what the user installs inside FIXTURE_CLEAR: the board's fixture (pnp_tools) lies across the
feeder rails where they stood; parts come from the feeders on the rails.

Opulo's own groups are stock here (a modified copy of no catalog part: no declared mass).
"""
from build123d import Box, Compound, Pos
from cad_agent.state import bought_solid

BASE = "lumenpnp"
GROUPS = ("y_gantry_left", "y_gantry_right", "x_gantry", "front_feeder_rail", "rear_feeder_rail",
          "y_limit_striker", "x_drag_chain_asm", "y_drag_chain_asm", "primary_staging_plate",
          "components_installed_by_user")
FIXTURE_CLEAR = ((140.0, 20.0, 20.0), (410.0, 420.0, 60.0))    # the fixture and the board over the bed
LONG_MM = 300.0                        # a frame solid longer than this along y is a rail or a belt run (_channels)

CLEARANCE = {}
ALLOW_CONTACT = {"frame|gantry"}          # the Y carriages on their rails
GANTRY_Y = (-170.0, 230.0)                # the channels' reach; the gantry's own travel is pnp_tools's AXES


def _groups():
    out = {g: bought_solid(BASE, g) for g in GROUPS}
    (x0, y0, z0), (x1, y1, z1) = FIXTURE_CLEAR
    keep = []
    for so in out["components_installed_by_user"].solids():
        b = so.bounding_box()
        if b.min.X > x1 or b.max.X < x0 or b.min.Y > y1 or b.max.Y < y0 or b.min.Z > z1 or b.max.Z < z0:
            keep.append(so)
    out["components_installed_by_user"] = Compound(keep)
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
    for n in ("front_feeder_rail", "rear_feeder_rail", "y_limit_striker", "primary_staging_plate"):
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

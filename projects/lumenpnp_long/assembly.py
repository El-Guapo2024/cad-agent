"""LumenPnP v4.2.0 with its Y axis 300 mm longer: the base of the one-machine PCB fab.

The `lumenpnp` project's own STEPs (Opulo's assembly, CERN-OHL-W v2; see lumenpnp/assembly.py), changed only by a
stretch at y = YS: a part that runs the whole length (the side frames' two 2020 extrusions, the MGN rail, the belt
runs) is cut there and its own section extruded DY to fill the gap, so it keeps its real profile; a part behind YS
(the rear legs and brackets, the rear feeder rail, what the user fits there) moves DY back; the Y cable chain's lower
run is repeated over the gap. What rides on the gantry stays where it is. The optional strip feeders sit 40 mm further back, clear of
the fab's hot plate. To buy: the 2020s 900 instead of 600, the
MGN12 rail 850 instead of 550, the Y belts 600 mm longer each, and a longer Y cable chain.

A stretched group is a modified copy of Opulo's, so it is stock here (no declared mass).
"""
from build123d import Compound, Keep, Plane, Pos, Solid, Vector
from cad_agent.state import bought_solid

BASE = "lumenpnp"
YS, DY = 400.0, 300.0                  # the cut, in front of the rear feeder rail (y 410) and behind the Y carriage
LONG_MM = 300.0                        # a part longer than this along y that crosses YS is stretched
GROUPS = ("y_gantry_left", "y_gantry_right", "x_gantry", "front_feeder_rail", "rear_feeder_rail",
          "y_limit_striker", "x_drag_chain_asm", "y_drag_chain_asm", "primary_staging_plate",
          "optional_strip_feeders", "components_installed_by_user")
MOVED = {"rear_feeder_rail"}           # wholly behind the cut
FEEDERS_BACK = 40.0                    # the optional strip feeders (printed) moved back, 50 mm clear of the 250 C hot plate
KEPT = {"x_gantry", "x_drag_chain_asm", "front_feeder_rail", "y_limit_striker", "primary_staging_plate"}

CLEARANCE = {}
ALLOW_CONTACT = {
    "components_installed_by_user|front_feeder_rail", "components_installed_by_user|rear_feeder_rail",
    "components_installed_by_user|x_drag_chain_asm", "components_installed_by_user|x_gantry",
    "components_installed_by_user|y_drag_chain_asm", "components_installed_by_user|y_gantry_left",
    "components_installed_by_user|y_gantry_right", "x_drag_chain_asm|x_gantry", "x_drag_chain_asm|y_drag_chain_asm",
}


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


def _longer(g):
    solids = bought_solid(BASE, g).solids()
    out = []
    for so in solids:
        b = so.bounding_box()
        cy = (b.min.Y + b.max.Y) / 2.0
        if b.max.Y - b.min.Y > LONG_MM and b.min.Y < YS < b.max.Y:
            out += _stretch(so)
        elif cy > YS:
            out.append(Pos(0, DY, 0) * so)
        elif g == "components_installed_by_user" and 170 < (b.min.X + b.max.X) / 2.0 < 420 and 190 < cy < 320:
            out.append(Pos(0, FEEDERS_BACK, 0) * so)        # the strip feeders' own parts go back with them
        else:
            out.append(so)
            if g == "y_drag_chain_asm" and cy > YS - DY and b.max.Z < 100.0:    # the chain's lower run
                out.append(Pos(0, DY, 0) * so)
    return Compound(out)


def parts():
    out = {}
    for g in GROUPS:
        if g in KEPT:
            out[g] = bought_solid(BASE, g)
        elif g == "optional_strip_feeders":
            out[g] = Pos(0, FEEDERS_BACK, 0) * bought_solid(BASE, g)
        elif g in MOVED:
            out[g] = Pos(0, DY, 0) * bought_solid(BASE, g)
        else:
            out[g] = _longer(g)
    return out

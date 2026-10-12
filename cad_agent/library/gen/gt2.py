"""A smooth GT2 idler pulley: a wheel between two flanges, bore through, drawn as an envelope.

The belt runs on the `belt_od` diameter, between flanges `flange_od` across and `flange_t` thick, and the whole is
`width` long. It is revolved from its half section about z, centred on the origin. There is no bearing, hub or set
screw: the listings this is drawn from do not give them, and what a bracket meets is the flange and the bore.
"""
from __future__ import annotations

from build123d import Axis, BuildLine, BuildPart, BuildSketch, Plane, Polyline, make_face, revolve


def idler(bore, flange_od, belt_od, width, flange_t):
    r0, r1, r2, h = bore / 2.0, belt_od / 2.0, flange_od / 2.0, width / 2.0
    half = [(r0, -h), (r2, -h), (r2, -h + flange_t), (r1, -h + flange_t),
            (r1, h - flange_t), (r2, h - flange_t), (r2, h), (r0, h), (r0, -h)]
    with BuildPart() as part:
        with BuildSketch(Plane.XZ):
            with BuildLine():
                Polyline(*half)
            make_face()
        revolve(axis=Axis.Z)
    return part.part

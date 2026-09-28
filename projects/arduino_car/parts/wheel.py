"""Drive wheel pressed onto the TT motor's D-shaft.

Printed as one piece: hub, spokes and rim. The tyre is a separate O-ring or a
rubber band seated in the rim groove, which is why the rim has a channel
rather than a flat face.

The bore is a D to match the motor shaft, so torque goes through the flat
rather than through a friction fit that will round out.
"""
import math

from build123d import Box, Cylinder, Pos, Rot

MATERIAL = "petg"
PROCESS = "fdm"
MIN_FEATURE_MM = 3.0

PARAMS = {
    "dia": 65.0,
    "width": 24.0,
    "rim_wall": 3.5,
    "groove_depth": 2.5,
    "groove_width": 6.0,
    "hub_dia": 16.0,
    "hub_len": 14.0,
    "bore_dia": 5.6,      # motor axle 5.5 plus a press allowance
    "bore_flat": 0.5,
    "spokes": 6,
    "spoke_w": 5.0,
    "web": 3.0,
}


def build(dia, width, rim_wall, groove_depth, groove_width, hub_dia, hub_len,
          bore_dia, bore_flat, spokes, spoke_w, web):
    r = dia / 2.0
    # Rim: a tube, with a tyre groove turned into its outer face.
    wheel = Rot(0, 90, 0) * Cylinder(r, width)
    wheel -= Rot(0, 90, 0) * Cylinder(r - rim_wall, width + 2)
    wheel -= Rot(0, 90, 0) * (
        Cylinder(r + 1, groove_width) - Cylinder(r - groove_depth, groove_width + 2))

    # Hub with a D bore.
    hub = Rot(0, 90, 0) * Cylinder(hub_dia / 2.0, hub_len)
    bore = Rot(0, 90, 0) * Cylinder(bore_dia / 2.0, hub_len + 2)
    bore -= Pos(0, bore_dia / 2.0 - bore_flat / 2.0, 0) * Box(
        hub_len + 4, bore_flat, bore_dia + 1)
    wheel += hub - bore

    # Spokes joining hub to rim, in the web plane.
    for i in range(spokes):
        a = 2 * math.pi * i / spokes
        length = r - rim_wall / 2.0 - hub_dia / 2.0 + 2
        mid = (hub_dia / 2.0 + r - rim_wall / 2.0) / 2.0
        spoke = Box(web, spoke_w, length)
        wheel += Pos(0, mid * math.sin(a), mid * math.cos(a)) * Rot(
            math.degrees(a), 0, 0) * spoke
    return wheel

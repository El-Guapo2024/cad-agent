"""TT gearmotor, the yellow plastic hobby gearbox sold with most robot kits.

Envelope only: gearbox body, motor can, and the output axle that the wheel
presses onto. Modelled centred on the axle, because the axle is what locates
the wheel and therefore what the chassis has to position.

Single output shaft by default. The dual-shaft variant exists, but two of them
mounted facing each other across a narrow chassis put their inner stubs on the
same axis and clash on the centreline, which the fit gate caught the first
time this car was assembled.

DIMENSIONS ARE UNVERIFIED. These parts are sold with a wattage and a gear
ratio and almost never a drawing, and the 2026-09-13 survey found vendor
pages blocked. Every number here is class-typical and must be confirmed with
callipers before anything is cut.
"""
from build123d import Box, Cylinder, Pos, Rot

SOURCE = ("class-typical TT gearmotor envelope; no vendor drawing found, "
          "vendor pages blocked during the 2026-09-13 survey")
VENDOR = None
VERIFIED = False

PARAMS = {
    "body_l": 37.0,      # gearbox, along the axle
    "body_w": 22.5,
    "body_h": 18.8,
    "can_dia": 24.0,     # motor can sticking out the back
    "can_len": 33.0,
    "axle_dia": 5.5,
    "axle_len": 12.0,    # output side only
    "axle_flat": 0.5,    # D-shaft flat depth
    "dual_shaft": False, # a dual-shaft pair mounted facing each other collide
}


def build(body_l, body_w, body_h, can_dia, can_len, axle_dia, axle_len, axle_flat,
          dual_shaft):
    # Axle runs along x, origin at the axle centre.
    body = Pos(0, -body_w / 2.0 + 5.0, 0) * Box(body_l, body_w, body_h)
    body += Pos(0, -body_w - can_len / 2.0 + 5.0, 0) * Rot(90, 0, 0) * Cylinder(
        can_dia / 2.0, can_len)
    for sx in ((-1, 1) if dual_shaft else (1,)):
        shaft = Rot(0, 90, 0) * Cylinder(axle_dia / 2.0, axle_len)
        # D-flat, the feature a wheel keys onto.
        shaft -= Pos(0, axle_dia / 2.0 - axle_flat / 2.0, 0) * Box(
            axle_len + 1, axle_flat, axle_dia + 1)
        body += Pos(sx * (body_l / 2.0 + axle_len / 2.0), 0, 0) * shaft
    return body

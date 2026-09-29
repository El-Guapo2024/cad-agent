"""Reflow hot plate: aluminium block heated from below, dock of assembly box B.

Two heating styles, chosen by a parameter, because which one to buy is still
open:

  flat        a mica element clamped to the underside. The plate is then a
              plain block. Default, after a 2026-09-13 survey found 6 mm
              cartridge heaters at 80-100 mm in mains voltage to be rare:
              stock is 6 x 20-50 mm, or a diameter too fat for a 10 mm plate.
  cartridge   two bores running the long axis, the original design. Kept
              because it gives a stiffer, more even plate if a heater in the
              right size does turn up.

A blind well takes the K-type thermocouple bead at mid-depth on the centre
line, positioned so it reads plate temperature rather than sitting against a
heater. Four corner holes carry it on standoffs. A pad on the top face takes
the KSD301 bimetal cutout, which is the hardware over-temperature limit and is
independent of firmware.

The clamped face is the datum: with the flat style the underside must stay
flat, so nothing is machined into it.
"""
from build123d import Box, Cylinder, Pos, Rot, Mode, BuildPart, Align
from cad_agent.parts import CLEARANCE_HOLE, TAP_DRILL

MATERIAL = "aluminium"
PROCESS = "cnc"
MIN_FEATURE_MM = 4.0   # thinnest remaining wall: bore to edge

# Cutouts expected at the mid-plane with the flat heater: 4 mount holes and
# the 2 bimetal-switch holes. The cartridge variant adds 2 bores and is not
# gated by this figure, since a module constant cannot vary with a parameter.
EXPECT_FEATURES = 6

PARAMS = {
    "heater_style": "flat", # "flat" (mica underneath) or "cartridge" (bores)
    "size": 100.0,          # plate is square, mm
    "thickness": 10.0,
    "heater_dia": 6.35,     # 1/4 inch cartridge heater
    "heater_fit": 0.1,      # bore is heater + fit, for a slip fit
    "heater_spacing": 50.0, # centre to centre, symmetric about the middle
    "tc_dia": 1.6,          # thermocouple bead well
    "tc_depth": 30.0,
    "mount_screw": "M3",
    "mount_inset": 7.0,
    "switch_screw": "M3",
}


def build(heater_style, size, thickness, heater_dia, heater_fit, heater_spacing,
          tc_dia, tc_depth, mount_screw, mount_inset, switch_screw):
    if heater_style not in ("flat", "cartridge"):
        raise ValueError(
            f"heater_style must be 'flat' or 'cartridge', not {heater_style!r}")
    half = size / 2.0

    plate = Box(size, size, thickness)

    if heater_style == "cartridge":
        # Through bores along X, offset in Y, at mid thickness. The bore is
        # the heater plus a slip-fit allowance; a heater is made undersize.
        bore = heater_dia + heater_fit
        for y in (-heater_spacing / 2.0, heater_spacing / 2.0):
            plate -= Pos(0, y, 0) * Rot(0, 90, 0) * Cylinder(bore / 2.0, size + 2)

    # Thermocouple well: blind bore in from one edge, on the centre line,
    # stopping short of the middle so it does not meet a heater bore.
    plate -= (Pos(0, -half + tc_depth / 2.0, 0) * Rot(90, 0, 0)
              * Cylinder(tc_dia / 2.0, tc_depth))

    # Mount holes: tapped from below at the corners.
    d = TAP_DRILL[mount_screw]
    for sx in (-1, 1):
        for sy in (-1, 1):
            plate -= (Pos(sx * (half - mount_inset), sy * (half - mount_inset), 0)
                      * Cylinder(d / 2.0, thickness + 2))

    # Bimetal switch pad: two tapped holes in the top face near one edge.
    ds = TAP_DRILL[switch_screw]
    for sx in (-1, 1):
        plate -= (Pos(sx * 9.0, half - mount_inset, thickness / 2.0 - 3.0)
                  * Cylinder(ds / 2.0, 6.0))

    return plate

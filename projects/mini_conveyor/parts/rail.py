"""Mini conveyor rail: the aluminium bar each belt runs along (two per module, both fixed: the line has one carrier
size). Machined.

Frame as the big conveyor's rail: x along the travel, the inner face at y 0 with the bar in -y, z 0 at the belt's
top (the carrier's bottom). A 4.5 ledge carries the belt's top run; the face above it guides the carrier's edge; the
return run passes under, hidden between the end idlers and the drive pulley below the middle (NeoDen's layout,
without its snub idlers: the triangle wraps the drive pulley enough). The entry idler's axle sits in a slot: sliding
it toward the end tensions the belt. The guide face's ends are chamfered 3 deep over 11 (about 15 degrees) as a lead-in.
"""
from build123d import Box, Cylinder, Polygon, Pos, Rot, extrude

MATERIAL = "aluminium"
PROCESS = "cnc"
MIN_FEATURE_MM = 2.0

PARAMS = {"length": 250.0, "thick": 10.0, "top": 6.0, "bottom": -45.0, "ledge": 4.5, "ledge_t": 5.0,
          "belt_t": 1.5, "ledge_end": 24.0, "lead_in": 3.0, "lead_len": 11.0, "idler_x": 112.0, "idler_z": -11.5, "axle": 6.0,
          "slot": 6.0, "drive_z": -28.0, "bore": 22.0, "mount_x": 105.0, "mount_hole": 5.5}


def build(length, thick, top, bottom, ledge, ledge_t, belt_t, ledge_end, lead_in, lead_len, idler_x, idler_z, axle, slot,
          drive_z, bore, mount_x, mount_hole):
    h = top - bottom
    rail = Pos(0, -thick / 2.0, bottom + h / 2.0) * Box(length, thick, h)
    rail += Pos(0, ledge / 2.0, -belt_t - ledge_t / 2.0) * Box(length - 2 * ledge_end, ledge, ledge_t)
    for sx in (-1, 1):            # lead-in wedges, shallow (about 15 deg): the physics sim found 45 deg steep
        tri = Polygon((sx * length / 2.0, 0.01), (sx * length / 2.0, -lead_in), (sx * (length / 2.0 - lead_len), 0.01),
                      align=None)
        rail -= Pos(0, 0, (top + bottom) / 2.0) * extrude(tri, h / 2.0 + 1, both=True)
    y = -thick / 2.0
    rail -= Pos(0, y, drive_z) * Rot(90, 0, 0) * Cylinder(bore / 2.0, thick + 2)            # the 608's bore
    rail -= Pos(idler_x, y, idler_z) * Rot(90, 0, 0) * Cylinder(axle / 2.0, thick + 2)      # exit idler's axle
    rail -= Pos(-idler_x - slot / 2.0, y, idler_z) * Box(slot, thick + 2, axle)            # entry idler: a slot
    for x in (-idler_x, -idler_x - slot):
        rail -= Pos(x, y, idler_z) * Rot(90, 0, 0) * Cylinder(axle / 2.0, thick + 2)
    for x in (-mount_x, mount_x):                                                           # to the cross beams
        rail -= Pos(x, y, bottom + 6.0) * Cylinder(mount_hole / 2.0, 14.0)
    return rail

"""Transport rail: the machined aluminium bar each belt runs along (one fixed at the front, one moving at the rear).

Its frame: x along the board's travel, the inner face (the board's guide) at y 0 with the bar behind it in -y, z 0 at
the belt's top, which is the board's bottom. A ledge on the inner face carries the belt's top run; the board's edge
rides on the belt and is guided by the face above it. The ledge sticks out 4.5 mm, under SMEMA 1.2's 0.187 in
(4.75 mm) edge clearance. The top inner edge is chamfered at both ends as the lead-in (SMEMA: at least 0.125 in, 3.2 mm).
The hex drive shaft passes through a bearing bore near the exit end (+x); shoulder-bolt axles carry the end idlers,
and the return idler's axle sits in a slot so pulling it toward the entry end tensions the belt.
"""
from build123d import Box, Cylinder, Pos, Rot, chamfer, Axis

MATERIAL = "aluminium"
PROCESS = "cnc_long"
MIN_FEATURE_MM = 2.0

PARAMS = {"length": 600.0, "thick": 12.0, "top": 8.0, "bottom": -70.0, "ledge": 4.5, "ledge_t": 6.0, "belt_t": 1.5,
          "ledge_end": 25.0, "lead_in": 4.0, "drive_x": 260.0, "drive_z": -50.0, "bore": 22.0,
          "idler_x": 290.0, "idler_z": -11.5, "axle": 6.0, "return_x": 260.0, "mount_holes": 6.6, "slot": 8.0}


def build(length, thick, top, bottom, ledge, ledge_t, belt_t, ledge_end, lead_in, drive_x, drive_z, bore,
          idler_x, idler_z, axle, return_x, mount_holes, slot):
    h = top - bottom
    rail = Pos(0, -thick / 2.0, bottom + h / 2.0) * Box(length, thick, h)
    run = length - 2.0 * ledge_end
    rail += Pos(0, ledge / 2.0, -belt_t - ledge_t / 2.0) * Box(run, ledge, ledge_t)
    rail -= Pos(drive_x, -thick / 2.0, drive_z) * Rot(90, 0, 0) * Cylinder(bore / 2.0, thick + 2)  # drive bearing
    for x, z in ((idler_x, idler_z), (-idler_x, idler_z)):                                          # idler axles
        rail -= Pos(x, -thick / 2.0, z) * Rot(90, 0, 0) * Cylinder(axle / 2.0, thick + 2)
    # the return idler's axle in a slot along x: sliding it out tensions the belt
    rail -= Pos(-return_x - slot / 2.0, -thick / 2.0, drive_z) * Box(slot, thick + 2, axle)
    for x in (-return_x, -return_x - slot):
        rail -= Pos(x, -thick / 2.0, drive_z) * Rot(90, 0, 0) * Cylinder(axle / 2.0, thick + 2)
    for sx in (-1, 1):                                                                               # lead-in
        e = rail.edges().filter_by(Axis.Z).group_by(Axis.X)[0 if sx < 0 else -1]
        e = e.filter_by(lambda ed: ed.center().Y > -0.01)
        if e:
            rail = chamfer(e, lead_in)
    for x in (-length / 2.0 + 60.0, length / 2.0 - 60.0):                                            # to its mounts
        rail -= Pos(x, -thick / 2.0, bottom + 6.0) * Cylinder(mount_holes / 2.0, 14.0)
    return rail

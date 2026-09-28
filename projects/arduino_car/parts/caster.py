"""Ball caster at the nose: a printed socket holding a loose steel ball.

The third contact point. A ball rather than a swivel wheel because a swivel
has to castor round when the car reverses, and on a light chassis it jams
instead. A ball has no preferred direction at all.

The socket captures the ball from above with a lip smaller than the ball, so
it drops in from below during assembly and cannot fall out. The bore is a
clearance fit plus a working gap: printed sockets shrink slightly and a ball
that binds is worse than one that rattles.
"""
from build123d import Box, Cylinder, Sphere, Pos

MATERIAL = "petg"
PROCESS = "fdm"
MIN_FEATURE_MM = 3.0

PARAMS = {
    "ball_dia": 16.0,
    "ball_gap": 0.6,       # printed sockets shrink; binding is worse than slop
    "body_dia": 28.0,
    "drop": 42.3,          # set by the wheel radius: the ball must touch the
                           # same ground plane the wheels do, or the car rocks
    "flange_t": 4.0,
    "pcd": 26.0,           # matches the chassis caster circle
    "hole_dia": 3.4,
    "lip": 2.0,            # how far the socket closes over the ball equator
}


def build(ball_dia, ball_gap, body_dia, drop, flange_t, pcd, hole_dia, lip):
    import math
    socket_r = (ball_dia + ball_gap) / 2.0

    body = Pos(0, 0, -drop / 2.0) * Cylinder(body_dia / 2.0, drop)
    flange = Pos(0, 0, flange_t / 2.0) * Cylinder(pcd / 2.0 + 7.0, flange_t)
    part = body + flange

    # Spherical seat, opening downward, closed over the equator by `lip`.
    centre_z = -drop + socket_r - lip
    part -= Pos(0, 0, centre_z) * Sphere(socket_r)
    part -= Pos(0, 0, centre_z - socket_r) * Cylinder(
        socket_r - lip, ball_dia)           # the opening the ball sits proud of

    for i in range(4):
        a = math.radians(45 + 90 * i)
        part -= Pos(pcd / 2.0 * math.cos(a), pcd / 2.0 * math.sin(a),
                    flange_t / 2.0) * Cylinder(hole_dia / 2.0, flange_t + 2)
    return part

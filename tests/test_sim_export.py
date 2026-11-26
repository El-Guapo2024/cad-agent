"""cad_agent.sim_export: convex decomposition and belt paths (no MuJoCo needed)."""
import math

from build123d import Box, Cylinder, Pos, Rot

from cad_agent.sim_export import belt_path, decompose


def test_decompose_splits_an_l_into_two_convex_boxes():
    ell = Pos(0, 0, 5) * Box(100, 10, 10) + Pos(0, 10, 2) * Box(100, 10, 4)   # a bar with a ledge
    pieces = decompose(ell)
    assert len(pieces) == 2
    assert math.isclose(sum(p.volume for p, _ in pieces), ell.volume, rel_tol=1e-6)


def test_decompose_keeps_a_convex_solid_whole():
    pieces = decompose(Box(10, 20, 30))
    assert len(pieces) == 1


def test_decompose_gives_up_past_the_limit():
    comb = Box(200, 10, 2)
    for i in range(40):
        comb += Pos(-97.5 + 5 * i, 0, 3) * Box(2, 10, 4)
    assert decompose(comb, max_pieces=8) is None


def test_belt_path_reads_the_wraps():
    ring = Rot(90, 0, 0) * (Cylinder(11.5, 4) - Cylinder(10, 4))
    loop = Pos(-50, 0, 0) * ring + Pos(50, 0, 0) * ring + Pos(0, 0, 10.75) * Box(100, 4, 1.5)
    p = belt_path(loop)
    assert p["run"] == [-50.0, 50.0]
    assert math.isclose(p["top_z"], 11.5) and math.isclose(p["thick"], 1.5)

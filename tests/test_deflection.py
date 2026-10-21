"""[[deflection]]: a body held as a beam, judged by Euler-Bernoulli bending from Roark's Table 8.1.

cad_agent/beam.py is the engineering and speckinds/deflection.py the judge. These tests hold:

  * the closed forms, to the last digits, on a rectangular and a tube section for every support and place of
    load, and against a cubic-Hermite beam element that shares no coefficient with them;
  * the sections OCCT gives: a rectangle, a tube, an I built up by the parallel axis theorem, a turned one with
    its product of inertia, a notch and a hole that fall between the uniform stations, and a T-slot extrusion
    against its datasheet;
  * every way a body is not a beam, and every PASS, FAIL and UNCHECKED the rule gives, with the numbers it gives;
  * that the section is one more kind after the seven there were, its rows after theirs.

No project uses [[deflection]] yet, so no verdict that held before changes. The sample designs' checks.json and
verify.json rows were compared by hand with the code without this piece (they are identical), and the last
tests here hold what a unit test can: the other sections' rows are the same with or without it, in the same
order.
"""
import functools
import json
import math
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import numpy as np
import pytest
from build123d import Box, Compound, Cylinder, Face, Location, Pos, Rot, Solid, Vector, Wire, export_step

from cad_agent import beam, geom, materials, registry
from cad_agent import spec as sp
from cad_agent import state as st
from cad_agent.bodies import Assembly, BodyInfo
from cad_agent.motion import Axis
from cad_agent.parts import blank_of, extrusion_blank
from cad_agent.registry import SpecCtx
from cad_agent.speckinds.deflection import deflection as kind
from cad_agent.speckinds.kit import Unusable
from conftest import cad_env

REPO = Path(__file__).resolve().parent.parent
E_AL = materials.prop("aluminium", "youngs_modulus_mpa").value          # 70000 MPa
LEGACY = ("envelope", "size", "position", "clearance", "keepout", "mass", "interface")

L, B, H = 400.0, 30.0, 12.0                      # a bar along x: 400 long, 30 wide (y), 12 deep (z)
I_Z = B * H ** 3 / 12.0                          # 4320 mm^4: its stiffness against a load along z
I_Y = H * B ** 3 / 12.0                          # 27000 mm^4: against a load along y
DO, DI = 40.0, 34.0
I_TUBE = math.pi * (DO ** 4 - DI ** 4) / 64.0


@functools.lru_cache(maxsize=None)
def shape(name: str):
    return {"rect": lambda: Box(L, B, H),
            "tube": lambda: Rot(0, 90, 0) * (Cylinder(DO / 2, L) - Cylinder(DI / 2, L + 2))}[name]()


@functools.lru_cache(maxsize=None)
def profile_of(name: str):
    return beam.profile(shape(name))


def approx(v):
    return pytest.approx(v, rel=1e-9)


# ─── The closed forms ────────────────────────────────────────────────────────

def closed(support, at, point, udl, span, e, i):
    """The textbook forms, written out again here (Roark's Table 8.1 cases 1a, 1d, 1e and 2a, 2d, 2e)."""
    ei = e * i
    if support == "simple":
        return point * span ** 3 / (48 * ei) + 5 * udl * span ** 3 / (384 * ei)
    if support == "fixed":
        return point * span ** 3 / (192 * ei) + udl * span ** 3 / (384 * ei)
    a = 0.0 if at in ("end", "worst") else span / 2          # Roark's a: from the free end to the load
    return point * (2 * span ** 3 - 3 * span ** 2 * a + a ** 3) / (6 * ei) + udl * span ** 3 / (8 * ei)


PLACES = [("simple", "center"), ("simple", "worst"), ("fixed", "center"), ("fixed", "worst"),
          ("cantilever", "center"), ("cantilever", "end"), ("cantilever", "worst")]
LOADS = [(10.0, 0.0), (0.0, 4.0), (10.0, 4.0)]                      # newtons at a point, newtons spread over the span


@pytest.mark.parametrize("section, i_true", [("rect", I_Z), ("tube", I_TUBE)])
@pytest.mark.parametrize("support, at", PLACES)
def test_the_closed_forms_hold_on_sections_read_from_the_solid(section, i_true, support, at):
    i_min, i_max = profile_of(section).second_moment(2)
    assert i_min == approx(i_true) and i_max == approx(i_true)
    for point, udl in LOADS:
        for span in (L, 350.0):
            got = beam.deflection(support, span, E_AL, i_min, point, udl, at)
            assert got.mm == approx(closed(support, at, point, udl, span, E_AL, i_true))
            assert got.mm == got.point_mm + got.udl_mm
            assert (got.point_mm == 0) == (point == 0) and (got.udl_mm == 0) == (udl == 0)


def test_where_the_deflection_is_and_which_roark_cases_gave_it():
    assert beam.deflection("simple", L, E_AL, I_Z, 1.0, 1.0).where == "midspan"
    assert beam.deflection("fixed", L, E_AL, I_Z, 1.0, 1.0).where == "midspan"
    assert beam.deflection("cantilever", L, E_AL, I_Z, 1.0, 1.0).where == "the free end"
    cases = {(s, a): beam.deflection(s, L, E_AL, I_Z, 1.0, 1.0, a).cases for s, a in PLACES}
    assert cases[("simple", "worst")] == ("1e", "2e") and cases[("fixed", "center")] == ("1d", "2d")
    assert cases[("cantilever", "worst")] == ("1a (a = 0)", "2a") == cases[("cantilever", "end")]
    assert cases[("cantilever", "center")] == ("1a (a = L/2)", "2a")


def test_worst_is_midspan_for_a_simple_or_fixed_beam_and_the_free_end_for_a_cantilever():
    for support in ("simple", "fixed"):
        assert beam.place_of(support, "worst") == beam.place_of(support, "center") == "center"
        with pytest.raises(ValueError, match="free end"):
            beam.place_of(support, "end")
    assert beam.place_of("cantilever", "worst") == beam.place_of("cantilever", "end") == "end"
    assert beam.place_of("cantilever", "center") == "center"
    with pytest.raises(ValueError, match="support must be one of"):
        beam.place_of("pinned", "worst")
    with pytest.raises(ValueError, match="at must be one of"):
        beam.place_of("simple", "middle")


def test_beam_and_the_kind_import_without_the_cad_kernel():
    # cad_agent.spec imports every kind, so a kind that imported the kernel at module level would make `cad ls`
    # and `cad lib` wait for it: geometry is read where a body is cut, not where the module is imported
    code = ("import sys\n"
            "import cad_agent.beam, cad_agent.speckinds.deflection, cad_agent.spec\n"
            "print(sorted(m for m in ('build123d', 'OCP') if m in sys.modules))\n")
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
                       env=cad_env(PYTHONPATH=str(REPO)), cwd=str(REPO))
    assert p.returncode == 0, p.stderr
    assert p.stdout.strip().splitlines()[-1] == "[]"


def test_the_closed_forms_refuse_what_is_not_a_beam_or_not_a_load():
    for bad in (dict(span_mm=0.0), dict(e_mpa=-1.0), dict(i_mm4=float("nan")), dict(i_mm4=float("inf"))):
        with pytest.raises(ValueError, match="must be a positive number"):
            beam.deflection("simple", **{"span_mm": L, "e_mpa": E_AL, "i_mm4": I_Z, **bad})
    with pytest.raises(ValueError, match="magnitudes"):
        beam.deflection("simple", L, E_AL, I_Z, point_n=-1.0)
    assert beam.weight_n(1000.0) == pytest.approx(9.80665)


def hermite_nodes(support, span, ei, point_n, udl_n, point_node, n=8):
    """The deflection at each node of a beam of n cubic Hermite elements, `ei` a number or one for each element.
    It is exact at the nodes for loads at nodes and for a uniform load, so for a prismatic beam it is the closed
    form by another road. Nothing here is shared with beam.py."""
    h = span / n
    ei = np.broadcast_to(np.asarray(ei, dtype=float), (n,))
    fe = udl_n / span * np.array([h / 2, h * h / 12, h / 2, -h * h / 12])
    k, f = np.zeros((2 * (n + 1),) * 2), np.zeros(2 * (n + 1))
    for e in range(n):
        s = slice(2 * e, 2 * e + 4)
        k[s, s] += ei[e] / h ** 3 * np.array([[12, 6 * h, -12, 6 * h], [6 * h, 4 * h * h, -6 * h, 2 * h * h],
                                              [-12, -6 * h, 12, -6 * h], [6 * h, 2 * h * h, -6 * h, 4 * h * h]])
        f[s] += fe
    f[2 * point_node] += point_n
    held = {"simple": [0, 2 * n], "fixed": [0, 1, 2 * n, 2 * n + 1], "cantilever": [0, 1]}[support]
    free = [i for i in range(2 * (n + 1)) if i not in held]
    u = np.zeros(2 * (n + 1))
    u[free] = np.linalg.solve(k[np.ix_(free, free)], f[free])
    return np.abs(u[0::2])


def hermite(support, span, ei, point_n, udl_n, point_node, n=8):
    """The largest nodal deflection (see hermite_nodes)."""
    return float(hermite_nodes(support, span, ei, point_n, udl_n, point_node, n).max())


@pytest.mark.parametrize("support, at", PLACES)
def test_the_closed_forms_agree_with_a_finite_element_beam(support, at):
    node = 8 if support == "cantilever" and at != "center" else 4        # the load's node, of 8 elements
    for point, udl in LOADS:
        got = beam.deflection(support, L, E_AL, I_Z, point, udl, at).mm
        assert got == approx(hermite(support, L, E_AL * I_Z, point, udl, node))


@pytest.mark.parametrize("support", ["simple", "fixed", "cantilever"])
def test_no_place_for_the_load_does_more_harm_than_the_one_worst_names(support):
    nodes = range(1, 9 if support == "cantilever" else 8)
    by_place = [hermite(support, L, E_AL * I_Z, 10.0, 0.0, node) for node in nodes]
    assert max(by_place) == approx(beam.deflection(support, L, E_AL, I_Z, 10.0, 0.0, "worst").mm)
    assert by_place.index(max(by_place)) + 1 == (8 if support == "cantilever" else 4)


@pytest.mark.parametrize("support", ["simple", "fixed", "cantilever"])
@pytest.mark.parametrize("point, udl", LOADS)
def test_the_weakest_and_the_stiffest_section_bound_a_beam_whose_stiffness_varies(support, point, udl):
    """The rule passes on the deflection of the weakest section the whole way and fails on that of the stiffest,
    which is only right if a beam whose every section lies between them deflects between the two: held here
    with finite elements, for stiffnesses that change from element to element at random."""
    n, node = 20, 20 if support == "cantilever" else 10
    rng = np.random.default_rng(7)
    for trial in range(60):
        ei = E_AL * I_Z * (rng.uniform(1.0, 6.0, n) if trial % 2 else np.where(rng.random(n) < 0.3, 6.0, 1.0))
        real = hermite_nodes(support, L, ei, point, udl, node, n).max()
        weakest = hermite_nodes(support, L, ei.min(), point, udl, node, n).max()
        stiffest = hermite_nodes(support, L, ei.max(), point, udl, node, n).max()
        assert stiffest * (1 - 1e-9) <= real <= weakest * (1 + 1e-9), (trial, stiffest, real, weakest)


# ─── The sections ────────────────────────────────────────────────────────────

def test_a_rectangle_gives_the_second_moment_for_each_load_axis():
    prof = profile_of("rect")
    assert (prof.axis, prof.across, prof.length) == (0, (1, 2), pytest.approx(L))
    assert prof.second_moment(2) == (approx(I_Z), approx(I_Z))
    assert prof.second_moment(1) == (approx(I_Y), approx(I_Y))
    assert (prof.depth(2), prof.depth(1)) == (approx(H), approx(B))
    with pytest.raises(ValueError, match="does not bend"):
        prof.second_moment(0)


def test_the_beam_may_run_along_any_axis_and_sit_anywhere():
    along_y = beam.profile(Pos(5, 100, -7) * Box(B, L, H))
    assert along_y.axis == 1 and along_y.across == (0, 2)
    assert along_y.second_moment(2)[0] == approx(I_Z) and along_y.second_moment(0)[0] == approx(I_Y)
    along_z = beam.profile(Box(B, H, L))
    assert along_z.axis == 2 and along_z.across == (0, 1)
    assert along_z.second_moment(0)[0] == approx(I_Y) and along_z.second_moment(1)[0] == approx(I_Z)
    assert beam.profile(Pos(100, -50, 30) * shape("tube")).second_moment(1)[0] == approx(I_TUBE)


def test_a_tube_is_what_its_closed_form_says_for_either_load_axis():
    prof = profile_of("tube")
    assert prof.second_moment(1)[0] == approx(I_TUBE) and prof.second_moment(2)[0] == approx(I_TUBE)
    assert prof.depth(2) == approx(DO)


def test_a_built_up_section_has_the_parallel_axis_theorem_in_it():
    # an I: flanges 40 wide and 6 thick, a web 6 wide between them, 40 deep overall
    i_beam = Box(L, 40, 6).moved(Location((0, 0, 17))) + Box(L, 40, 6).moved(Location((0, 0, -17))) + Box(L, 6, 28)
    strong = 2 * (40 * 6 ** 3 / 12 + 40 * 6 * 17 ** 2) + 6 * 28 ** 3 / 12
    weak = 2 * (6 * 40 ** 3 / 12) + 28 * 6 ** 3 / 12
    prof = beam.profile(i_beam)
    assert prof.second_moment(2)[0] == approx(strong) and prof.second_moment(1)[0] == approx(weak)
    assert prof.depth(2) == approx(40)


def test_a_section_turned_about_the_beam_has_its_product_of_inertia_taken_out():
    t = math.radians(30)
    c, s = math.cos(t), math.sin(t)
    iy_, iz_ = B ** 3 * H / 12, H ** 3 * B / 12                 # the bar's own, about its centre
    tyy, tzz, tyz = iy_ * c * c + iz_ * s * s, iy_ * s * s + iz_ * c * c, (iy_ - iz_) * s * c
    prof = beam.profile(Rot(30, 0, 0) * Box(L, B, H))
    assert prof.second_moment(2)[0] == approx(tzz - tyz ** 2 / tyy)        # the stiffness against a load along z
    assert prof.second_moment(1)[0] == approx(tyy - tyz ** 2 / tzz)
    assert prof.second_moment(2)[0] < tzz                                    # the sideways give costs stiffness
    quarter = beam.profile(Rot(90, 0, 0) * Box(L, B, H))
    assert quarter.second_moment(2)[0] == approx(I_Y) and quarter.second_moment(1)[0] == approx(I_Z)


def test_the_footprint_is_the_rectangle_with_the_sections_area_and_moments_however_it_is_turned():
    plain = beam.profile(Box(L, 20, 40)).footprint
    assert plain == (pytest.approx(20, abs=1e-9), pytest.approx(40, abs=1e-9))
    for turn in (30, 45, 90):
        turned = beam.profile(Rot(turn, 0, 0) * Box(L, 20, 40)).footprint
        assert turned == (pytest.approx(20, abs=1e-9), pytest.approx(40, abs=1e-9)), turn
    holed = beam.profile(Box(L, 40, 20) - Pos(-100.7, 0, 0) * Cylinder(2.75, 30)).footprint
    assert holed == (pytest.approx(20, abs=1e-9), pytest.approx(40, abs=1e-9))     # the median, not the section at a hole
    w, h = beam.profile(t_slot_2040()).footprint
    assert (w, h) != (pytest.approx(20, abs=0.1), pytest.approx(40, abs=0.1)) and w > 20 and h > 40


def uniform_stations(prof):
    return [prof.lo + (i + 0.5) * prof.length / beam.STATIONS for i in range(beam.STATIONS)]


def test_a_notch_between_the_uniform_stations_is_still_a_station():
    notch = Pos(30.3, 0, 8) * Box(2.0, 30.0, 8.0)                # 2 mm wide, cuts 6 mm off the top of a 20 mm bar
    prof = beam.profile(Box(L, 20, 20) - notch)
    assert all(abs(x - 30.3) > 1.0 for x in uniform_stations(prof))      # 21 equal cells would have missed it
    assert prof.second_moment(2) == (approx(20 * 14 ** 3 / 12), approx(20 * 20 ** 3 / 12))
    assert any(abs(s.x - 30.3) < 1e-6 for s in prof.sections)


def test_a_hole_is_a_station_at_its_diameter_and_does_not_make_the_plate_two_beams():
    prof = beam.profile(Box(L, 40, 6) - Pos(-100.7, 0, 0) * Cylinder(3.0, 10))
    assert prof.second_moment(2) == (approx((40 - 6) * 6 ** 3 / 12), approx(40 * 6 ** 3 / 12))
    assert any(s.pieces == 2 for s in prof.sections)                   # at the diameter the section is two strips
    assert prof.second_moment(1)[0] < 6 * 40 ** 3 / 12                 # the strong axis feels it a little


def test_the_ends_are_sections_but_a_chamfer_is_not_a_weak_end():
    thin_ends = Box(L, 30, 6) + Box(L - 10, 30, 12)                   # 5 mm of the thin plate shows at each end
    prof = beam.profile(thin_ends)
    assert prof.second_moment(2)[0] == approx(30 * 6 ** 3 / 12)
    assert prof.sections[0].x < prof.lo + 5.0 and prof.sections[-1].x > prof.hi - 5.0
    chamfered = Box(L, 30, 12)                                        # 2 mm chamfers round both ends, inside the skirt
    chamfered = chamfered.chamfer(2.0, None, chamfered.edges().filter_by(lambda e: abs(e.center().X) > L / 2 - 1))
    both = beam.profile(chamfered).second_moment(2)
    assert both == (approx(I_Z), approx(I_Z))


# ─── 2040: a T-slot extrusion against its datasheet ──────────────────────────

def t_slot_2040(length=L):
    """A 20 x 40 T-slot section, six slots and a central chamber, from the dimensions of the datasheet below: a
    20 x 40 outline, 6.2 mm slot opening, 6.1 mm from the face to the bottom of the slot, 5 mm bores, 1.5 mm
    diagonal webs. Two dimensions its drawing does not give were taken as typical and not fitted: a 1.8 mm lip
    over the slot and a cavity 12.4 mm wide under it, narrowing to 7.4 mm at the bottom."""
    def prism(points):
        wire = Wire.make_polygon([Vector(-(length + 2) / 2, y, z) for y, z in points], close=True)
        return Solid.extrude(Face(wire), Vector(length + 2, 0, 0))

    def cavity(cz, turn):
        c, s = math.cos(math.radians(turn)), math.sin(math.radians(turn))
        cav = [(-6.2, 8.2), (6.2, 8.2), (3.7, 3.9), (-3.7, 3.9)]
        opening = [(-3.1, 8.19), (3.1, 8.19), (3.1, 10.5), (-3.1, 10.5)]
        return [[(c * y - s * z, cz + s * y + c * z) for y, z in pts] for pts in (cav, opening)]

    section = Box(length, 20, 40)
    cuts = []
    for cz, turns in ((10.0, (0, -90, 90)), (-10.0, (180, -90, 90))):       # the slots of each 20 mm module
        for turn in turns:
            cuts += cavity(cz, turn)
    cuts.append([(-6.2, -1.8), (6.2, -1.8), (6.2, 1.8), (-6.2, 1.8)])        # the lips between the two modules
    cuts += [cavity(10.0, 180)[0], cavity(-10.0, 0)[0]]                      # and the cavities that face each other
    for points in cuts:
        section -= prism(points)
    for cz in (10.0, -10.0):
        section -= Pos(0, 0, cz) * Rot(0, 90, 0) * Cylinder(2.5, length + 2)
    return section


def test_a_2040_extrusion_has_the_second_moments_its_datasheet_publishes():
    """haluminium.com, "20 Series T-Slot Aluminium Extrusion Profile" (2018-08-29; a copy is at
    https://fabacademy.org/2021/labs/agrilab/students/antonio-anaya/files/week10/profile_alum_2020_datasheet.pdf),
    20*40 profile S6-20x40: slot width 6.2 mm, T-slot height 6.1 mm, hole 5 mm, diagonal bar 1.5 mm,
    0.90 kg/m, Ix 4.64 cm^4 (about the axis across the 20 mm side, for a load along the 40 mm side) and Iy 1.42 cm^4."""
    prof = beam.profile(t_slot_2040())
    strong, weak = prof.second_moment(2)[0], prof.second_moment(1)[0]
    assert strong == pytest.approx(4.64e4, rel=0.05) and weak == pytest.approx(1.42e4, rel=0.05)
    assert prof.sections[0].area == pytest.approx(0.90 / 2.70e-3, rel=0.10)          # 0.90 kg/m of aluminium, mm^2
    assert prof.depth(2) == approx(40) and prof.second_moment(2) == (approx(strong), approx(strong))   # a prism
    assert strong < 20 * 40 ** 3 / 12 / 2        # under half what the solid bar around it has: why a box would lie


# ─── A body that is not a beam ───────────────────────────────────────────────

def test_a_body_in_two_solids_is_not_a_beam():
    with pytest.raises(beam.NotABeam, match="2 solids"):
        beam.profile(Compound([Box(100, 10, 10), Pos(200, 0, 0) * Box(100, 10, 10)]))


def test_which_way_a_body_runs_must_be_clear_or_said():
    with pytest.raises(beam.NotABeam, match="which way it runs") as e:
        beam.profile(Box(100, 98, 10))
    assert 'axis = "x"' in str(e.value) and 'axis = "y"' in str(e.value)
    assert beam.profile(Box(100, 98, 10), axis=1).axis == 1                     # said: it runs along y
    assert beam.profile(Box(100, 80, 10)).axis == 0


def test_a_tilted_body_is_not_a_straight_beam_but_one_degree_is_within_what_is_allowed():
    with pytest.raises(beam.NotABeam, match="strays .* across"):
        beam.profile(Rot(0, 0, 5) * Box(L, 20, 20))
    prof = beam.profile(Rot(0, 0, 1) * Box(L, 20, 20))
    assert prof.second_moment(2)[0] == pytest.approx(20 ** 4 / 12, rel=2e-4)
    assert beam.TILT_DEG == 2.0


def test_a_body_with_no_long_edge_cannot_be_told_straight():
    ribbed = Box(L, 30, 10)
    for x in range(-175, 176, 70):                               # a groove across the whole width, top and bottom
        ribbed -= Pos(x, 0, 5) * Box(2, 40, 2) + Pos(x, 0, -5) * Box(2, 40, 2)
    with pytest.raises(beam.NotABeam, match="straightness cannot be told"):
        beam.profile(ribbed)


def test_a_ladder_is_two_beams_where_a_plate_with_a_hole_is_one():
    with pytest.raises(beam.NotABeam, match=r"for 300\.0 mm the section is in separate pieces"):
        beam.profile(Box(L, 40, 6) - Box(300, 30, 10))                 # two rails tied only at the ends
    with pytest.raises(beam.NotABeam, match=r"for 30\.0 mm the section is in separate pieces"):
        beam.profile(Box(L, 40, 6) - Cylinder(15.0, 10))               # a 30 mm hole in a 40 mm plate
    assert beam.profile(Box(L, 40, 6) - Cylinder(3.0, 10)).second_moment(2)[0] > 0    # a small one is fine


def test_too_many_cuts_across_a_body_is_not_a_beam_this_samples():
    holes = Compound([Pos(-193.5 + 3.0 * i, 0, 0) * Cylinder(1.0, 10) for i in range(130)])
    with pytest.raises(beam.NotABeam, match=f"more than {beam.MAX_STATIONS}"):
        beam.profile(Box(L, 40, 6) - holes)


def test_a_cut_that_finds_nothing_or_fails_is_not_a_section(monkeypatch):
    body = shape("rect").wrapped
    with pytest.raises(beam.NotABeam, match="no section at x = 900.00 mm"):
        beam._section(body, 0, 900.0, [0.0, 0.0, 0.0], 100.0, 1, 2)

    class Failed:
        def __init__(self, *args):
            pass

        def IsDone(self):
            return False

        def Build(self):
            pass

    import OCP.BRepAlgoAPI as algo
    monkeypatch.setattr(algo, "BRepAlgoAPI_Common", Failed)
    with pytest.raises(beam.NotABeam, match="could not be cut"):
        beam._section(body, 0, 0.0, [0.0, 0.0, 0.0], 100.0, 1, 2)


# ─── The rule on bodies it is handed ─────────────────────────────────────────

def info(name="b", material="aluminium", mass=None, geometry="exact", kind_="made", **extra):
    return BodyInfo(name=name, kind=kind_, project="t", material=material, mass_g=mass,
                    mass_source="test" if mass is not None else None, geometry=geometry, **extra)


def run(entry, solid=None, infos=None, parts=None, axes=None, **body):
    """The rows [[deflection]] gives for `entry` on a body "b" (an aluminium, exact bar unless told otherwise)."""
    parts = {"b": solid if solid is not None else shape("rect"), **(parts or {})}
    infos = {"b": info(**body), **(infos or {})}
    entry = {"body": "b", "support": "simple", "max_um": 1000.0, **entry}
    if not {"load_n", "load_g", "load_moving", "self_weight"} & set(entry):
        entry["load_n"] = 5.0                                  # a load of 5 N unless the entry brings its own
    ctx = SpecCtx(slug="t", parts=parts, machine=Assembly(slug="t", parts=parts, bodies=infos, axes=axes or {}))
    return list(kind(entry, ctx))


def one(entry, **kw):
    (row,) = run(entry, **kw)
    return row


def um(row):
    """The deflection a row reports, in micrometres: the number before its first "um" (the larger, of two)."""
    return float(re.match(r"(?:between [\d.]+ and )?([\d.]+) um", row.measured)[1])


def expected_um(support="simple", at="worst", point=5.0, udl=0.0, span=L, i=I_Z, e=E_AL):
    return closed(support, at, point, udl, span, e, i) * 1000.0


@pytest.mark.parametrize("support, at", PLACES)
def test_the_row_carries_the_closed_form_and_flips_at_the_limit(support, at):
    want = expected_um(support, at, point=5.0, udl=0.0)
    row = one({"support": support, "at": at, "load_n": 5.0, "max_um": want * 1.001})
    assert (row.state, row.rule, row.subject, row.limit) == ("PASS", "spec/deflection", "b", f"<= {want * 1.001:g} um")
    assert um(row) == pytest.approx(want, abs=5e-4)
    assert one({"support": support, "at": at, "load_n": 5.0, "max_um": want * 0.999}).state == "FAIL"


def test_the_row_says_what_the_number_rests_on():
    row = one({"load_g": 500, "self_weight": True}, mass=388.8)
    assert row.state == "PASS"
    m = row.measured
    assert m.startswith("32.127 um at midspan; simple span 400 mm, load 500 g = 4.903 N + 3.813 N own weight; I 4320 mm^4; ")
    assert "E 70000 MPa (FreeCAD 3160daf1e2b6 src/Mod/Material/Resources/Materials/Standard/Metal/Aluminum/" in m
    assert m.endswith("YoungsModulus = 70000 MPa); span/depth 33.3; Roark Table 8.1 cases 1e, 2e")
    assert one({"load_n": 5.0}).measured.endswith("Roark Table 8.1 case 1e")
    want = closed("simple", "worst", beam.weight_n(500), beam.weight_n(388.8), L, E_AL, I_Z) * 1000
    assert um(row) == pytest.approx(want, abs=5e-4)


def test_a_cc_by_card_is_credited_beside_the_modulus_it_gives_and_an_lgpl_card_is_not():
    steel = one({"load_n": 5.0}, material="steel").measured
    assert ('Steel-Generic.FCMat: YoungsModulus = 200000 MPa) ["Steel-Generic" by Juergen Riegel, CC-BY-3.0 '
            "https://creativecommons.org/licenses/by/3.0/]; span/depth") in steel
    aluminium = one({"load_n": 5.0}).measured                      # an LGPL card: the row is what it was
    assert "Stöhr" not in aluminium and "CC-BY" not in aluminium


def test_each_load_a_row_can_carry_adds_up():
    w = beam.weight_n(388.8)
    for entry, point, udl in (({"load_n": 5.0}, 5.0, 0.0), ({"load_g": 250}, beam.weight_n(250), 0.0),
                              ({"load_n": 5.0, "self_weight": True}, 5.0, w),
                              ({"load_g": 100, "self_weight": True}, beam.weight_n(100), w),
                              ({"self_weight": True}, 0.0, w)):
        row = one(entry, mass=388.8)
        assert um(row) == pytest.approx(expected_um(point=point, udl=udl), abs=5e-4), entry
    assert "own weight" in row.measured and "load 3.813 N own weight" in row.measured


def test_a_body_is_cut_once_however_many_entries_name_it(monkeypatch):
    calls, real = [], beam.profile
    monkeypatch.setattr(beam, "profile", lambda solid, axis=None: calls.append(axis) or real(solid, axis))
    parts = {"b": shape("rect")}
    ctx = SpecCtx(slug="t", parts=parts, machine=Assembly(slug="t", parts=parts, bodies={"b": info()}))
    entry = {"body": "b", "support": "simple", "load_n": 5.0, "max_um": 1000.0}
    rows = [row for e in (entry, {**entry, "support": "fixed"}, {**entry, "support": "cantilever", "at": "center"},
                          {**entry, "axis": "x"}) for row in kind(e, ctx)]
    assert calls == [None, 0]                                  # one cut for the three that leave the axis to the body
    assert [r.state for r in rows] == ["PASS"] * 4
    assert rows[0].measured.split(";")[0] != rows[1].measured.split(";")[0]        # and each still has its own answer


def test_a_span_shorter_than_the_body_shortens_the_formula_and_the_weight_on_it():
    w = beam.weight_n(388.8) * 350 / 400
    row = one({"span_mm": 350, "load_n": 5.0, "self_weight": True}, mass=388.8)
    assert um(row) == pytest.approx(expected_um(point=5.0, udl=w, span=350), abs=5e-4)
    assert "simple span 350 mm" in row.measured


def test_a_cantilever_is_loaded_at_its_free_end_unless_the_load_is_said_to_be_at_the_middle():
    end = one({"support": "cantilever", "load_n": 2.0})
    mid = one({"support": "cantilever", "load_n": 2.0, "at": "center"})
    assert end.measured.startswith(f"{expected_um('cantilever', 'end', 2.0):.3f} um at the free end")
    assert mid.measured.startswith(f"{expected_um('cantilever', 'center', 2.0):.3f} um at the free end")
    assert "case 1a (a = 0)" in end.measured and "case 1a (a = L/2)" in mid.measured


def test_a_load_across_gravity_and_the_weight_are_two_planes_that_combine_as_vectors():
    w = beam.weight_n(388.8)
    row = one({"load_n": 5.0, "direction": "-y", "self_weight": True}, mass=388.8)
    sideways, down = expected_um(point=5.0, i=I_Y), expected_um(point=0.0, udl=w, i=I_Z)
    assert um(row) == pytest.approx(math.hypot(sideways, down), abs=5e-4)
    assert "I 27000 mm^4 for a load along y, 4320 mm^4 for a load along z" in row.measured
    along_y = one({"load_n": 5.0, "direction": "y"})
    assert um(along_y) == pytest.approx(sideways, abs=5e-4) and "I 27000 mm^4;" in along_y.measured


def test_a_vertical_beam_is_loaded_across_and_its_weight_does_not_bend_it():
    post = Box(B, H, L)                                                # along z
    unchecked({"load_n": 5.0}, "the beam's own axis", solid=post)       # gravity, the default, is along it
    across = one({"load_n": 5.0, "direction": "x", "self_weight": True}, solid=post, mass=388.8)
    assert across.state == "PASS" and "own weight" not in across.measured
    assert um(across) == pytest.approx(expected_um(point=5.0, i=I_Y), abs=5e-4)
    unchecked({"self_weight": True, "direction": "x"}, "nothing bends this beam", solid=post, mass=388.8)


# ─── Every way the rule cannot judge ─────────────────────────────────────────

def unchecked(entry, expect, **kw):
    row = one(entry, **kw)
    assert (row.state, row.subject, row.rule) == ("UNCHECKED", "b", "spec/deflection"), row
    assert re.search(expect, row.measured), row.measured
    assert row.limit == f"<= {entry.get('max_um', 1000.0):g} um"
    return row


def test_an_envelope_has_no_section_whatever_it_is_called():
    unchecked({}, "stock that assembly.py builds", kind_="stock", geometry="envelope", material=None)
    unchecked({}, "bought part that is not declared `geometry = \"exact\"`", kind_="bought", geometry="envelope")
    unchecked({}, "not exact geometry", kind_="made", geometry="envelope")
    assert one({}, kind_="bought", geometry="exact").state == "PASS"      # a bought part that models its section may


def test_unverified_geometry_is_a_claim():
    unchecked({}, r"unverified \(VERIFIED = False\)", kind_="bought", verified=False)


def test_no_modulus_with_a_source_no_verdict():
    unchecked({}, "has no material", material=None)
    unchecked({}, "material 'unobtainium' is not in materials.py", material="unobtainium")
    unchecked({}, "no Young's modulus for fr4", material="fr4")


def test_a_modulus_whose_source_is_missing_is_not_used(monkeypatch):
    real = materials.prop
    monkeypatch.setattr(materials, "prop", lambda name, which: materials.Prop(70000.0, "  ")
                        if which == "youngs_modulus_mpa" else real(name, which))
    unchecked({}, "a Young's modulus with no source")
    monkeypatch.setattr(materials, "prop", lambda name, which: None)
    unchecked({}, "has no Young's modulus")


def test_a_modulus_comes_from_the_material_the_body_says_it_is_made_of():
    for material in ("steel", "pla", "petg", "aluminium"):
        e = materials.prop(material, "youngs_modulus_mpa")
        row = one({"max_um": 1e6}, material=material)
        assert row.state == "PASS" and f"E {e.value:g} MPa ({e.source})" in row.measured
        assert um(row) == pytest.approx(expected_um(e=e.value), abs=5e-4)


def moving_axes(**moves):
    return {name: Axis(name=name, moves=tuple(m), direction=(0, 1, 0), travel=(-10.0, 10.0)) for name, m in moves.items()}


def test_the_mass_an_axis_moves_is_the_load_and_the_beam_itself_is_left_out():
    infos = {"carriage": info("carriage", "steel", 251.2),
             "head": info("head", None, 150.0, kind_="bought", geometry="envelope")}
    parts = {"carriage": Box(1, 1, 1), "head": Box(1, 1, 1)}
    axes = moving_axes(y=("carriage", "head"), x=("b", "carriage"))
    row = one({"load_moving": "y", "max_um": 5000}, infos=infos, axes=axes, parts=parts)
    assert row.state == "PASS" and "401.2 g moved by axis y: carriage 251.2 g, head 150 g" in row.measured
    assert um(row) == pytest.approx(expected_um(point=beam.weight_n(401.2)), abs=5e-4)
    own = one({"load_moving": "x", "max_um": 5000}, infos=infos, axes=axes, parts=parts)
    assert "251.2 g moved by axis x: carriage 251.2 g" in own.measured       # "b" is on axis x, and not in its own load


def test_a_moving_load_needs_every_mass_it_adds_up():
    infos = {"carriage": info("carriage", "steel", 251.2),
             "blank": info("blank", None, None, kind_="stock", geometry="envelope", notes=("a note",)),
             "sensor": info("sensor", None, None, kind_="bought", geometry="envelope"),
             "bare": info("bare", None, None, kind_="stock", geometry="envelope")}
    parts = {k: Box(1, 1, 1) for k in infos}
    axes = moving_axes(y=("carriage", "blank"), z=("sensor",), w=("bare",))
    unchecked({"load_moving": "y"}, r"the mass axis y moves is not known: blank \(a note\)", infos=infos, axes=axes, parts=parts)
    unchecked({"load_moving": "z"}, r"sensor \(a bought part with no declared mass and mass_source\)",
              infos=infos, axes=axes, parts=parts)
    unchecked({"load_moving": "w"}, r"bare \(stock built in assembly.py has no material, so no mass\)",
              infos=infos, axes=axes, parts=parts)


def test_a_moving_load_needs_the_axes_of_an_assembly():
    unchecked({"load_moving": "y"}, "needs the AXES of the project's assembly.py", axes={})
    with pytest.raises(Unusable, match=r"no axis 'q' to take the load from \(axes: x, y\)"):
        run({"load_moving": "q"}, axes=moving_axes(x=("b", "c"), y=("c",)))
    with pytest.raises(Unusable, match="moves nothing but b"):
        run({"load_moving": "y"}, axes=moving_axes(y=("b",)))
    with pytest.raises(Unusable, match="moves 'ghost', which is not a body"):
        run({"load_moving": "y"}, axes=moving_axes(y=("ghost",)))


def test_the_own_weight_needs_a_mass():
    unchecked({"self_weight": True}, "needs the mass of b, and it is not known", mass=None)
    assert one({"self_weight": True}, mass=100.0).state == "PASS"


def test_shear_is_left_out_so_a_short_deep_beam_is_not_judged():
    unchecked({}, r"span/depth is 8\.3 \(100 mm over 12\.0 mm deep along z\), under 10: shear", solid=Box(100, 30, 12))
    assert one({}, solid=Box(120, 30, 12)).state == "PASS"                 # span/depth 10.0 is the least that is judged
    deep_sideways = one({"direction": "y"}, solid=Box(L, 45, 12))          # 400 over 45 mm deep along y: 8.9
    assert deep_sideways.state == "UNCHECKED" and "along y" in deep_sideways.measured


def test_fixed_ends_need_twice_the_slenderness_since_their_shear_is_four_times_as_great():
    near = Box(180, 30, 12)                                                # span/depth 15
    assert one({"support": "simple"}, solid=near).state == "PASS"
    assert one({"support": "cantilever"}, solid=near).state == "PASS"
    unchecked({"support": "fixed"}, r"span/depth is 15\.0 .* under 20", solid=near)
    assert one({"support": "fixed"}, solid=Box(240, 30, 12)).state == "PASS"
    assert beam.SLENDER == {"simple": 10.0, "cantilever": 10.0, "fixed": 20.0}


# ─── A solid box that stands for an extrusion ────────────────────────────────

def bracket_blank(kind="2040", length=400.0):
    """A blank as a part module makes a bracket of it: cross holes, a tapped end and a notch cut in it."""
    rail = extrusion_blank(kind, length, axis="x")                        # 400 long in x, 40 in y, 20 in z (2040)
    for x in (-150, -50, 50, 150):
        rail -= Pos(x, 0, 0) * Cylinder(2.75, 50)                         # M5 clearance holes right through
    rail -= Pos(-length / 2 + 5, 0, 0) * Rot(0, 90, 0) * Cylinder(2.1, 10)    # a tapped end
    return rail - Pos(100, 0, 8) * Box(20, 60, 4)                         # and a notch


def blank(body):
    """What parts.blank_of says of a body, from its sections and its volume as the rule reads them."""
    prof = beam.profile(body)
    return blank_of(prof.footprint, prof.length, geom.volume(body))


@pytest.mark.parametrize("kind", ["2020", "2040", "4040"])
@pytest.mark.parametrize("axis", ["x", "y", "z"])
def test_a_box_of_an_extrusions_size_is_unchecked_whoever_made_it_and_which_way_it_runs(kind, axis):
    row = unchecked({}, rf"solid box of a {kind}'s outer size \(.* filled\): that is what extrusion_blank makes",
                    solid=extrusion_blank(kind, 400.0, axis=axis))
    assert 'geometry = "exact"' in row.measured and "solid = true" in row.measured
    unchecked({}, "solid box of a", solid=extrusion_blank(kind, 400.0, axis=axis), kind_="bought", geometry="exact")


def test_a_blank_that_has_been_drilled_cut_moved_and_turned_is_still_one():
    body = bracket_blank()                                                # every boolean has dropped any tag
    found = blank(body)
    assert found.kind == "2040" and 0.97 < found.fill < 1.0
    assert found.footprint_mm == (pytest.approx(20, abs=1e-3), pytest.approx(40, abs=1e-3))
    for placed in (body, Pos(10, 20, 30) * body, Rot(0, 0, 90) * Pos(10, 20, 30) * body,
                   Rot(30, 0, 0) * body,                                  # turned about its own length
                   Rot(0, 0, 1.5) * body):                                # and a degree and a half off its axis
        unchecked({}, r"solid box of a 2040's outer size \(20 x 40(\.\d+)? mm, 9\d% of its box filled\)", solid=placed)


def test_what_is_not_a_blank_is_judged_as_the_body_it_is():
    real = t_slot_2040()                                                  # a real profile fills 39 % of its box
    pocketed = extrusion_blank("2040", L, axis="x") - Pos(0, 0, 4) * Box(300, 30, 12)     # 34 % milled out
    for body in (real, pocketed, Box(L, 25, 30), Box(L, 20, 41)):         # and a solid bar of another size
        assert blank(body) is None
    row = one({"load_n": 5.0}, solid=real)
    assert row.state == "PASS" and "a solid bar" not in row.measured
    assert one({"load_n": 5.0}, solid=pocketed).state == "PASS"
    assert um(row) > expected_um(point=5.0, i=20 * 40 ** 3 / 12) * 2           # a real 2040 is 2 times too soft for its box


def test_a_stub_a_cube_and_a_size_that_is_nearly_one_are_not_blanks():
    assert blank_of((20, 40), 60.0, 20 * 40 * 60) is None                 # under twice as long as wide
    assert blank_of((40, 40), 40.0, 40 ** 3) is None
    assert blank_of((20.05, 40), L, 20.05 * 40 * L) is not None and blank_of((20.3, 40), L, 20.3 * 40 * L) is None
    assert blank_of((40, 20), L, 20 * 40 * L).kind == "2040"              # either way round
    assert blank_of((20, 40), L, 0.89 * 20 * 40 * L) is None and blank_of((20, 40), L, 0.91 * 20 * 40 * L)
    stub = unchecked({}, r"span/depth is 3\.0", solid=extrusion_blank("2040", 60.0, axis="x"))
    assert "extrusion_blank" not in stub.measured


def test_a_solid_bar_of_such_a_size_that_really_is_one_says_so():
    bar = Box(L, 20, 40)                                                  # a 20 x 40 flat bar, not an extrusion
    unchecked({}, "say `solid = true`", solid=bar)
    row = one({"load_n": 50.0, "solid": True}, solid=bar)
    assert row.state == "PASS" and um(row) == pytest.approx(expected_um(point=50.0, i=20 * 40 ** 3 / 12), abs=5e-4)
    assert row.measured.endswith("a solid bar because the entry says `solid = true`, though a box of a 2040's outer size")
    other = one({"solid": True})                                          # nothing to take on its word: no note
    assert "solid = true" not in other.measured
    bad({"solid": "yes"}, "`solid` must be true or false")
    bad({"solid": 1}, "`solid` must be true or false")


STEPPED = Box(L, 30, 8) + Box(240, 30, 12)                             # 80 mm of 8 thick at each end, 240 of 12 between
I_THIN, I_THICK = 30 * 8 ** 3 / 12, 30 * 12 ** 3 / 12


def test_a_section_that_varies_passes_on_its_weakest_fails_on_its_stiffest_and_is_unchecked_between():
    upper, lower = expected_um(point=20.0, i=I_THIN), expected_um(point=20.0, i=I_THICK)
    real = hermite_nodes("simple", L, E_AL * np.array([I_THIN] * 2 + [I_THICK] * 6 + [I_THIN] * 2), 20.0, 0.0, 5, 10).max()
    assert lower < real * 1000 < upper                      # the beam as it is, by finite elements, is between the two
    weak = one({"load_n": 20.0, "max_um": upper * 1.01}, solid=STEPPED)
    assert weak.state == "PASS" and weak.measured.startswith(f"{upper:.3f} um or less at midspan (the weakest section)")
    assert f"I {I_THIN:.5g} (largest {I_THICK:.5g}) mm^4" in weak.measured
    strong = one({"load_n": 20.0, "max_um": lower * 0.99}, solid=STEPPED)
    assert strong.state == "FAIL" and strong.measured.startswith(f"{lower:.3f} um or more at midspan (the stiffest section)")
    between = one({"load_n": 20.0, "max_um": (upper + lower) / 2}, solid=STEPPED)
    assert between.state == "UNCHECKED"
    assert between.measured.startswith(f"between {lower:.3f} and {upper:.3f} um at midspan: the section varies along the body")
    assert um(between) == pytest.approx(upper, abs=5e-4)                 # the larger of the two numbers


def test_a_uniform_section_has_no_such_gray_zone():
    want = expected_um()
    for scale, state in ((1.0000001, "PASS"), (0.999, "FAIL")):
        assert one({"max_um": want * scale}).state == state


def test_a_body_that_is_not_a_beam_is_unchecked_with_the_reason_beam_py_gives():
    unchecked({}, "2 solids", solid=Compound([Box(100, 10, 10), Pos(200, 0, 0) * Box(100, 10, 10)]))
    unchecked({}, "which way it runs", solid=Box(100, 98, 10))
    unchecked({}, "strays", solid=Rot(0, 0, 5) * Box(L, 20, 20))
    unchecked({}, "separate pieces", solid=Box(L, 40, 6) - Box(300, 30, 10))


def test_the_axis_may_be_said_and_a_load_along_it_is_not_bending():
    said = one({"axis": "y", "load_n": 5.0}, solid=Box(200, 198, 12))        # nearly square: it runs along y as it is told
    assert said.state == "PASS" and "simple span 198 mm" in said.measured
    unchecked({"direction": "x"}, "compression and not bending")
    unchecked({"direction": "-x"}, "the beam's own axis")


def test_a_span_longer_than_the_body_is_a_mistake_in_the_entry():
    with pytest.raises(Unusable, match=r"`span_mm` 500 is longer than the body \(400.00 mm\)"):
        run({"span_mm": 500})


# ─── An entry that does not say what to judge ────────────────────────────────

def bad(entry, expect, **kw):
    with pytest.raises(Unusable, match=expect):
        run(entry, **kw)


def test_a_malformed_entry_is_not_a_guess():
    bad({"body": None}, "`body` must be the name of a body")
    bad({"support": "pinned"}, "support must be one of simple, fixed, cantilever")
    bad({"at": "middle"}, "at must be one of center, end, worst")
    bad({"support": "simple", "at": "end"}, "free end")
    bad({"max_um": 0}, "`max_um` must be a positive number")
    bad({"max_um": True}, "`max_um` must be a positive number")
    bad({"max_um": "50"}, "`max_um` must be a positive number")
    bad({"load_n": -1.0}, "`load_n` must be a positive number")
    bad({"span_mm": 0}, "`span_mm` must be a positive number")
    bad({"load_n": 1.0, "load_g": 5.0}, "takes one load, not load_n and load_g")
    bad({"load_g": 1.0, "load_moving": "y"}, "takes one load, not load_g and load_moving")
    bad({"self_weight": "yes"}, "`self_weight` must be true or false")
    bad({"load_moving": ""}, "`load_moving` must be the name of an axis")
    bad({"direction": "up"}, "`direction` must be x, y or z")
    bad({"axis": 3}, "`axis` must be x, y or z")


def test_a_key_that_is_misspelt_is_refused_so_that_a_weight_is_never_quietly_dropped():
    bad({"selfweight": True}, r"no key `selfweight` \(keys: body, support, span_mm, load_n, load_g, load_moving, at, "
                              r"self_weight, max_um, direction, axis, solid\)")
    bad({"load_kg": 2}, "no key `load_kg`")


def test_an_entry_with_nothing_to_carry_or_nothing_to_hold_it_to_is_incomplete():
    parts = {"b": shape("rect")}
    ctx = SpecCtx(slug="t", parts=parts, machine=Assembly(slug="t", parts=parts, bodies={"b": info()}))
    entry = {"body": "b", "support": "simple", "max_um": 50.0}
    with pytest.raises(Unusable, match="has no load: give load_n, load_g or load_moving, or self_weight = true"):
        list(kind(entry, ctx))
    for key in ("body", "support", "max_um"):
        with pytest.raises(Unusable, match=f"is missing `{key}`"):
            list(kind({k: v for k, v in {**entry, "load_n": 1.0}.items() if k != key}, ctx))
    with pytest.raises(Unusable, match="no body 'ghost' in the assembly"):
        list(kind({**entry, "load_n": 1.0, "body": "ghost"}, ctx))


# ─── Through a project: made, bought and stock bodies, and the real run ──────

SLUG = "beams"

PARTS = {"bar": ("aluminium", "Box(400, 30, 12)"), "carriage": ("steel", "Box(40, 40, 20)"), "plain": (None, "Box(100, 20, 10)")}

ASSEMBLY = textwrap.dedent('''\
    from build123d import Box, Pos
    from cad_agent.state import build_part, bought_solid

    SLUG = "beams"
    AXES = {
        "y": {"moves": ("carriage", "head"), "direction": (0, 1, 0), "travel": (-10.0, 10.0)},
        "z": {"moves": ("blank", "carriage"), "direction": (0, 0, 1), "travel": (-10.0, 10.0)},
    }


    def parts():
        bar, _ = build_part(SLUG, "bar")
        carriage, _ = build_part(SLUG, "carriage")
        plain, _ = build_part(SLUG, "plain")
        return {
            "bar": bar,
            "carriage": Pos(0, 0, 40) * carriage,
            "plain": Pos(0, 60, 0) * plain,
            "head": Pos(0, 0, 80) * bought_solid(SLUG, "head"),
            "rail": Pos(0, 100, 0) * bought_solid(SLUG, "rail"),
            "bare": Pos(0, 140, 0) * bought_solid(SLUG, "bare"),
            "unweighed": Pos(0, 180, 0) * bought_solid(SLUG, "unweighed"),
            "blank": Pos(0, -100, 0) * Box(300, 20, 40),
        }
''')


class Rig:
    def __init__(self, folder, machine):
        self.folder, self.machine = folder, machine

    def check(self, toml, machine=True):
        (self.folder / "spec.toml").write_text(textwrap.dedent(toml))
        return list(sp.check_spec(SLUG, self.machine.parts, machine=self.machine if machine else None))

    def rows(self, toml, **kw):
        return [r for r in self.check(toml, **kw) if r.rule == "spec/deflection"]


@pytest.fixture(scope="module")
def mach(tmp_path_factory):
    root = tmp_path_factory.mktemp("projects")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(st, "ROOT", root)
        d = st.project_dir(SLUG, create=True)
        for name, (material, build) in PARTS.items():
            (d / "parts" / f"{name}.py").write_text(
                f'"""{name}."""\nfrom build123d import Box\n\n' + (f'MATERIAL = "{material}"\n' if material else "")
                + f'PROCESS = "cnc"\nMIN_FEATURE_MM = 2.0\nPARAMS = {{}}\n\n\ndef build():\n    return {build}\n')
        for name, side in (("rail", {"material": "steel", "mass_g": 480, "mass_source": "datasheet 1, weight"}),
                           ("head", {"mass_g": 150, "mass_source": "datasheet 2, weight"}),
                           ("bare", {"geometry": "exact"}),
                           ("unweighed", {"geometry": "exact", "material": "steel"})):
            export_step(Box(30, 30, 30) if name == "head" else Box(300, 20, 10), str(d / "bought" / f"{name}.step"))
            side = {"geometry": "exact", **side} if name != "head" else side
            (d / "bought" / f"{name}.json").write_text(json.dumps({"source": f"datasheet {name}", "vendor": "V",
                                                                    "verified": True, **side}))
        (d / "assembly.py").write_text(ASSEMBLY)
        yield Rig(d, st.load_machine(SLUG))


def test_the_bodies_of_a_project_are_judged_by_what_they_are(mach):
    kinds = {n: (b.kind, b.geometry, b.material) for n, b in mach.machine.bodies.items()}
    assert kinds["bar"] == ("made", "exact", "aluminium") and kinds["rail"] == ("bought", "exact", "steel")
    assert kinds["blank"][:2] == ("stock", "envelope") and kinds["head"][:2] == ("bought", "envelope")
    rows = mach.rows('''
        [[deflection]]
        body = "bar"
        support = "simple"
        load_g = 500
        self_weight = true
        max_um = 100

        [[deflection]]
        body = "rail"
        support = "fixed"
        load_n = 5
        self_weight = true
        max_um = 100

        [[deflection]]
        body = "blank"
        support = "simple"
        load_n = 5
        max_um = 100

        [[deflection]]
        body = "head"
        support = "simple"
        load_n = 5
        max_um = 100
    ''')
    assert [(r.subject, r.state) for r in rows] == [("bar", "PASS"), ("rail", "PASS"), ("blank", "UNCHECKED"),
                                                   ("head", "UNCHECKED")]
    assert [r.source for r in rows] == [f"spec.toml [[deflection]] #{i}" for i in (1, 2, 3, 4)]
    bar_mass = L * B * H / 1000 * 2.70
    assert um(rows[0]) == pytest.approx(expected_um(point=beam.weight_n(500), udl=beam.weight_n(bar_mass)), abs=5e-4)
    steel = materials.prop("steel", "youngs_modulus_mpa").value
    rail = expected_um("fixed", point=5.0, udl=beam.weight_n(480.0), span=300, i=20 * 10 ** 3 / 12, e=steel)
    assert um(rows[1]) == pytest.approx(rail, abs=5e-4)                      # the declared mass, not volume x density
    assert "stock that assembly.py builds" in rows[2].measured and 'geometry = "exact"' in rows[3].measured


def test_a_bought_part_that_is_exact_still_needs_a_material_and_a_mass_for_what_it_uses(mach):
    rows = mach.rows('''
        [[deflection]]
        body = "bare"
        support = "simple"
        load_n = 5
        max_um = 100

        [[deflection]]
        body = "unweighed"
        support = "simple"
        self_weight = true
        max_um = 100

        [[deflection]]
        body = "unweighed"
        support = "simple"
        load_n = 5
        max_um = 100
    ''')
    assert [r.state for r in rows] == ["UNCHECKED", "UNCHECKED", "PASS"]
    assert "bare has no material" in rows[0].measured
    assert "needs the mass of unweighed" in rows[1].measured and "no declared mass and mass_source" in rows[1].measured


def test_the_axes_of_the_project_carry_the_load_and_an_unknown_mass_fails_closed(mach):
    rows = mach.rows('''
        [[deflection]]
        body = "bar"
        support = "cantilever"
        load_moving = "y"
        max_um = 1000

        [[deflection]]
        body = "bar"
        support = "cantilever"
        load_moving = "z"
        max_um = 1000
    ''')
    carriage = 40 * 40 * 20 / 1000 * 7.85
    assert rows[0].state == "PASS" and f"{carriage + 150:.4g} g moved by axis y" in rows[0].measured
    assert um(rows[0]) == pytest.approx(expected_um("cantilever", "end", beam.weight_n(carriage + 150)), abs=5e-4)
    assert rows[1].state == "UNCHECKED" and "blank (stock built in assembly.py" in rows[1].measured
    none = mach.rows('[[deflection]]\nbody = "bar"\nsupport = "simple"\nload_moving = "y"\nmax_um = 1000\n', machine=False)
    assert none[0].state == "UNCHECKED" and "needs the AXES" in none[0].measured


def test_an_entry_the_rule_cannot_use_is_one_unchecked_row_that_hides_nothing(mach):
    rows = mach.check('''
        [envelope]
        max_mm = [500, 500, 500]

        [[deflection]]
        body = "bar"
        support = "pinned"
        load_n = 1
        max_um = 50

        [[deflection]]
        body = "bar"
        support = "simple"
        load_n = 1
        max_um = 5000
    ''')
    assert [(r.rule, r.state) for r in rows] == [("spec/envelope", "PASS"), ("spec/deflection", "UNCHECKED"),
                                                 ("spec/deflection", "PASS")]
    assert rows[1].subject == "[[deflection]] #1" and "support must be one of" in rows[1].measured


def test_deflection_is_one_more_kind_after_the_seven_and_its_rows_come_after_theirs(mach):
    kinds = {k.name: k for k in registry.spec_kinds()}
    assert kinds["deflection"].order == 80 and not kinds["deflection"].table and kinds["deflection"].doc
    assert registry.spec_kind_names()[:7] == LEGACY and "deflection" in sp.KINDS
    assert max(kinds[n].order for n in LEGACY) < kinds["deflection"].order
    legacy = '''
        [envelope]
        max_mm = [500, 500, 500]

        [[size]]
        body = "bar"
        max_mm = [401, 31, 13]

        [[mass]]
        parts = { bar = 1 }
        max_g = 500
    '''
    more = '''
        [[deflection]]
        body = "bar"
        support = "simple"
        load_n = 1
        max_um = 5000
    '''
    def key(r):
        return (r.rule, r.state, r.subject, r.measured, r.limit, r.source)

    before = [key(r) for r in mach.check(legacy)]
    after = mach.check(legacy + more)
    assert [key(r) for r in after[:len(before)]] == before
    assert [r.rule for r in after[len(before):]] == ["spec/deflection"]


def test_the_real_run_hands_the_machine_to_the_rule(mach):
    from cad_agent.runner import check_all
    (mach.folder / "spec.toml").write_text(textwrap.dedent('''
        [[deflection]]
        body = "bar"
        support = "cantilever"
        load_moving = "y"
        self_weight = true
        max_um = 1000
    '''))
    payload = check_all(SLUG, render_views=("iso",))
    (row,) = [r for r in payload["rows"] if r["rule"] == "spec/deflection"]
    assert (row["state"], row["check"], row["subject"]) == ("PASS", "spec", "bar")
    assert "moved by axis y" in row["measured"] and "own weight" in row["measured"]

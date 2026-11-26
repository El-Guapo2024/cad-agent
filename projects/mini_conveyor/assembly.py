"""One bench-top module of the v1 mini PCB line (UV laser -> LumenPnP -> oven), positioned (2026-11-26).

The line moves one standard carrier (carrier.py: 170 x 170, a 150 x 150 board flush in its pocket), so the rails
are fixed: no width screws, guides or width motor. What is kept from the references (../pcb_conveyor/research/
REFERENCES.md): NeoDen J08's hidden belt return to a drive pulley below the middle and its shaft across to both
belts; SuperHouse PCBCONVEYOR's flat belts on flanged pulleys and stepper drive; SMEMA 1.2's tooling-hole size and
edge distance and its 3.2 mm minimum lead-in (the rails' 3 mm chamfers plus the belt's wrap give it).

Height: the carrier's top (the board's top) is at 137 mm over the bench, the LumenPnP's board height in
pnp_tools (its board top 37 over the frame's datum, whose feet are 100 below), so a module can pass through it.

Frame: x along the travel (+x out), y from the front rail's inner face, z up from the bench.
"""
from build123d import Plane, Pos, Rot, mirror

from cad_agent.state import build_part, bought_solid

SLUG = "mini_conveyor"

CARRIER = 170.0
GAP = CARRIER + 1.0           # 0.5 a side
CARRIER_T = 6.0
Z0 = 137.0 - CARRIER_T        # the belts' top: the carrier's bottom
L = 250.0
IDLER = (112.0, -11.5)
DRIVE_Z = -28.0
BEAM_X = 105.0
RAIL_T, RAIL_BOT = 10.0, -45.0
EXT = 20.0
SHAFT_Y = (-24.0, GAP + RAIL_T + 1.0)
MOTOR_FACE_Y = -44.5

CLEARANCE = {}
ALLOW_CONTACT = {f"{s}_rail|cross_beam_{i}" for s in ("front", "rear") for i in (1, 2)} | {
    f"cross_beam_{i}|leg_{i}{e}" for i in (1, 2) for e in "fr"} | {
    f"{s}_{a}|{s}_{q}" for s in ("front", "rear") for a, q in (("axle_in", "idler_in"), ("axle_out", "idler_out"))} | {
    f"{s}_{a}|{s}_rail" for s in ("front", "rear") for a in ("axle_in", "axle_out", "bearing")} | {
    f"{s}_bearing|shaft" for s in ("front", "rear")} | {f"{s}_drive|shaft" for s in ("front", "rear")} | {
    f"{s}_belt|{s}_{p}" for s in ("front", "rear") for p in ("idler_in", "idler_out", "drive")} | {
    f"{s}_belt|{s}_rail" for s in ("front", "rear")} | {f"carrier|{s}_belt" for s in ("front", "rear")} | {
    "coupler|shaft", "coupler|stepper", "stepper|motor_mount", "motor_mount|front_rail"}

MECHANISM = {
    "rotating": {
        **{f"{s}_{p}": {"axis": (0, 1, 0), "supports": [f"{s}_{a}"], "cantilever": True}
           for s in ("front", "rear") for p, a in (("idler_in", "axle_in"), ("idler_out", "axle_out"))},
        **{f"{s}_drive": {"axis": (0, 1, 0), "supports": ["shaft"], "cantilever": True} for s in ("front", "rear")},
        "shaft": {"axis": (0, 1, 0), "supports": ["front_bearing", "rear_bearing"]},
    },
    "belts": {f"{s}_belt": {"pulleys": [f"{s}_idler_in", f"{s}_idler_out", f"{s}_drive"],
                            "tension": f"{s}_idler_in"} for s in ("front", "rear")},   # its axle slides in a slot
    "static": {f"{s}_{a}": "a shoulder bolt fixed in the rail; the idler turns on it" for s in ("front", "rear")
               for a in ("axle_in", "axle_out")},
}


def _side(p, b):
    """A rail with its belt, idlers, axles, drive pulley and bearing, in the front rail's frame."""
    s = {"rail": p("rail", length=L, thick=RAIL_T, bottom=RAIL_BOT, idler_x=IDLER[0], idler_z=IDLER[1],
                   drive_z=DRIVE_Z, mount_x=BEAM_X)}
    s["belt"] = Pos(0, 0.5, 0) * b("flat_belt", pts=((-IDLER[0], IDLER[1]), (IDLER[0], IDLER[1]), (0.0, DRIVE_Z)))
    y = 0.3
    s["idler_in"] = Pos(-IDLER[0], y, IDLER[1]) * p("pulley")
    s["idler_out"] = Pos(IDLER[0], y, IDLER[1]) * p("pulley")
    s["drive"] = Pos(0, y, DRIVE_Z) * p("pulley", bore=8.0)
    head = y + 4.2 + 1.0
    for k, x in (("axle_in", -IDLER[0]), ("axle_out", IDLER[0])):
        s[k] = Pos(x, head, IDLER[1]) * b("axle", length=head + RAIL_T + 0.5)
    s["bearing"] = Pos(0, -RAIL_T / 2.0, DRIVE_Z) * b("bearing_608")
    return s


def parts():
    p = lambda n, **o: build_part(SLUG, n, o or None)[0]
    b = lambda n, **o: bought_solid(SLUG, n, **o)
    out = {}
    for k, v in _side(p, b).items():
        out[f"front_{k}"] = Pos(0, 0, Z0) * v
        out[f"rear_{k}"] = Pos(0, GAP, Z0) * mirror(v, Plane.XZ)
    beam_len = GAP + 2 * RAIL_T
    for i, x in enumerate((-BEAM_X, BEAM_X), 1):
        out[f"cross_beam_{i}"] = Pos(x, GAP / 2.0, Z0 + RAIL_BOT - EXT / 2.0) * Rot(90, 0, 0) * b(
            "extrusion_2020", length=beam_len)
        leg = Z0 + RAIL_BOT - EXT
        for e, y in (("f", 0.0), ("r", GAP)):
            out[f"leg_{i}{e}"] = Pos(x, y, leg / 2.0) * b("extrusion_2020", length=leg)
    out["shaft"] = Pos(0, sum(SHAFT_Y) / 2.0, Z0 + DRIVE_Z) * b("shaft", length=SHAFT_Y[1] - SHAFT_Y[0])
    out["coupler"] = Pos(0, -13.0, Z0 + DRIVE_Z) * Rot(0, 0, 180) * b("coupler")
    out["motor_mount"] = Pos(0, -RAIL_T, Z0 + DRIVE_Z) * p("motor_mount", depth=-MOTOR_FACE_Y - RAIL_T)
    out["stepper"] = Pos(0, MOTOR_FACE_Y, Z0 + DRIVE_Z) * b("stepper")
    out["carrier"] = Pos(0, 0.5, Z0) * p("carrier", size_x=CARRIER, size_y=CARRIER, thick=CARRIER_T)
    return out

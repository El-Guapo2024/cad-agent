"""Does a PCB ride the pcb_conveyor module correctly? A MuJoCo check of the CAD assembly.

Run in the sim venv (MuJoCo, numpy, matplotlib; no build123d), after exporting the assembly with the CAD venv:

    .venv/bin/python -m cad_agent.sim_export pcb_conveyor --pose carrier --belt front_belt --belt rear_belt \
        --exclude test_board --out sim/out/pcb_conveyor_carrier
    .venv/bin/python -m cad_agent.sim_export pcb_conveyor --belt front_belt --belt rear_belt \
        --exclude test_board --out sim/out/pcb_conveyor_home
    MUJOCO_GL=egl ~/work/sim-venv/bin/python sim/mujoco_conveyor.py --all --video nominal_2 --video small_49x40_home

Scene: two copies of the exported module (MJCF attached twice), the second `gap` mm after the first's track end
(SMEMA's maximum, 9.5 mm), every belt's top run replaced by a moving tread (see Tread), and a free box for the board.

Belts. MuJoCo has no moving-surface contact, and a body that is teleported (mocap) has no velocity in the contact
solver, so its friction would brake the board instead of driving it. Each belt is instead a chain of short
segments (the "tread") that run around the belt's actual visible path: up the entry pulley's arc, along the flat
top run, and down the exit pulley's arc, at the belt speed. Each segment is a capsule across the belt (radius = half the belt's thickness, so the
chain's envelope is exactly the belt's outer face, flat and wrapped) on a body with three joints (slide x,
slide z, hinge y) whose position AND velocity are prescribed every step from the belt's travel; their armature is
huge, so the contact forces cannot move them within a step (they are kinematic, effectively infinite mass). The
board therefore sees a surface whose contact velocity is the belt's, and is driven only by friction (Coulomb,
elliptic cone), as on the real belt. A segment that leaves the exit arc (vertical, 11.5 mm below the pass line, out
of the board's reach) re-enters at the bottom of the entry arc; the belt's hidden return run is not modelled.
Segments collide with the board only (not with each other, the pulleys or the rails).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np

os.environ.setdefault("MUJOCO_GL", "egl")
import mujoco  # noqa: E402

HERE = Path(__file__).resolve().parent
MM = 0.001
G = 9.81

# ─── Assumptions (see README / report for what is sourced and what is assumed) ────────────────────────────────
MU_BELT = 0.6          # ASSUMED: antistatic PU/rubber flat belt on FR4 / solder mask
MU_GUIDE = 0.3         # ASSUMED: aluminium rail face on an FR4 edge
FR4_DENSITY = 1850.0   # given: 1.85 g/cm^3
SMEMA_GAP = 9.5        # SMEMA 1.2: track ends at most 0.375 in apart
# belt speeds: vendor SMT edge conveyors list 0.5 to 20 m/min adjustable (Groves IS-500mm SMT conveyor datasheet,
# SMT MAX AE-400G); SMEMA sets no speed. The scenarios run 0.5, 2 and 10 m/min.
GUIDES = ("front_rail", "rear_rail")
SOLREF, SOLIMP = [0.002, 1.0], [0.95, 0.99, 0.0005, 0.5, 2]   # stiff contacts: ~0.05 mm sink under a 500 g board
SQ = math.sqrt(0.5)     # bodies whose faces guide the board's edges


@dataclass
class Scenario:
    name: str
    pose_dir: str = "pcb_conveyor_carrier"
    speed: float = 2.0                  # m/min
    board: tuple = (150.0, 169.0, 1.6)  # length (x), width (y), thickness, mm
    mass: float | None = None           # kg; None -> FR4 density
    mu_belt: float = MU_BELT
    mu_guide: float = MU_GUIDE
    gap: float = SMEMA_GAP
    m2_offset: tuple = (0.0, 0.0)       # module 2's (y, z) misalignment, mm
    speed_ratio: dict = field(default_factory=dict)   # belt name -> speed factor (belt mismatch)
    ramp: float = 0.2                   # s, belt 0 -> speed
    stop_at: float | None = None        # board centre x (mm, world) at which the belts stop (slip test)
    stop_ramp: float = 0.2              # s, speed -> 0
    start_offset: tuple = (0.0, 0.0)    # board's initial (dy mm, yaw deg)
    note: str = ""


SCENARIOS = {s.name: s for s in [
    Scenario("nominal_0.5", speed=0.5, note="FR4 169x150x1.6 (75 g), 0.5 m/min"),
    Scenario("nominal_2", speed=2.0, note="FR4 169x150x1.6 (75 g), 2 m/min"),
    Scenario("fast_10", speed=10.0, note="FR4 board, 10 m/min (mid vendor range)"),
    Scenario("skewed_start", speed=2.0, start_offset=(0.3, 0.3), note="dropped 0.3 mm off centre, 0.3 deg yawed"),
    Scenario("slip_75g", speed=2.0, ramp=0.0, stop_at=150.0, stop_ramp=0.0,
             note="75 g board; belts start and stop instantly (step)"),
    Scenario("slip_500g", speed=2.0, mass=0.5, ramp=0.0, stop_at=150.0, stop_ramp=0.0,
             note="500 g carrier, same footprint; step start and stop"),
    Scenario("slip_500g_mu0.3", speed=2.0, mass=0.5, mu_belt=0.3, ramp=0.0, stop_at=150.0, stop_ramp=0.0,
             note="500 g carrier, worn belt mu 0.3; step start and stop"),
    Scenario("slip_500g_10mpm", speed=10.0, mass=0.5, ramp=0.0, stop_at=150.0, stop_ramp=0.0,
             note="500 g carrier at 10 m/min; step start and stop"),
    Scenario("belt_mismatch_2pct", speed=2.0, speed_ratio={"rear_belt": 0.98},
             note="rear belt 2% slow (pulley/belt-thickness tolerance)"),
    Scenario("m2_lateral_1.0", speed=2.0, m2_offset=(1.0, 0.0), note="module 2 1.0 mm to the rear"),
    Scenario("m2_lateral_1.5", speed=2.0, m2_offset=(1.5, 0.0), note="module 2 1.5 mm to the rear"),
    Scenario("m2_high_1.0", speed=2.0, m2_offset=(0.0, 1.0), note="module 2 1.0 mm high"),
    Scenario("m2_low_1.0", speed=2.0, m2_offset=(0.0, -1.0), note="module 2 1.0 mm low"),
    Scenario("small_49x50_home", pose_dir="pcb_conveyor_home", board=(50.0, 49.0, 1.6),
             note="pose home (W 50): a 49 x 50 board"),
    Scenario("small_49x40_home", pose_dir="pcb_conveyor_home", board=(40.0, 49.0, 1.6),
             note="pose home (W 50): a 49 x 40 board"),
    Scenario("small_49x70_home", pose_dir="pcb_conveyor_home", board=(70.0, 49.0, 1.6),
             note="pose home (W 50): a 49 x 70 board"),
]}


# ─── The belt tread ──────────────────────────────────────────────────────────────────────────────────────────

class Tread:
    """One belt's visible path (entry arc, top run, exit arc) tiled with N segments; positions in mm, module frame."""

    def __init__(self, belt: dict, pitch: float):
        self.t, self.w = belt["thick"], belt["width"]
        self.xa, self.xb = belt["run"]
        self.cz = belt["center_z"]
        self.rc = belt["r_out"] - self.t / 2.0          # the segments' centre line
        self.lq = math.pi / 2.0 * self.rc
        self.run = self.xb - self.xa
        self.P = 2 * self.lq + self.run
        self.n = int(round(self.P / pitch))
        self.pitch = self.P / self.n
        self.yc = (belt["y"][0] + belt["y"][1]) / 2.0
        self.s0 = np.arange(self.n) * self.pitch

    def state(self, travel_mm: float, v_mm: float):
        """(x, z, alpha), (dx, dz, dalpha) for every segment, in m / rad."""
        s = (self.s0 + travel_mm) % self.P
        x, z, a = np.empty(self.n), np.empty(self.n), np.zeros(self.n)
        dx, dz, da = np.full(self.n, v_mm), np.zeros(self.n), np.zeros(self.n)
        e = s < self.lq
        top = (s >= self.lq) & (s < self.lq + self.run)
        q = ~e & ~top
        phi = np.where(e, math.pi - s / self.rc, math.pi / 2.0 - (s - self.lq - self.run) / self.rc)
        arc = e | q
        xc = np.where(e, self.xa, self.xb)
        x[arc] = xc[arc] + self.rc * np.cos(phi[arc])
        z[arc] = self.cz + self.rc * np.sin(phi[arc])
        a[arc] = math.pi / 2.0 - phi[arc]
        dx[arc] = v_mm * np.sin(phi[arc])
        dz[arc] = -v_mm * np.cos(phi[arc])
        da[arc] = v_mm / self.rc
        x[top] = self.xa + (s[top] - self.lq)
        z[top] = self.cz + self.rc
        return (np.stack([x * MM, z * MM, a], 1), np.stack([dx * MM, dz * MM, da], 1))


# ─── Building the model ──────────────────────────────────────────────────────────────────────────────────────

def build(sc: Scenario, pitch: float = 2.0, timestep: float = 0.0005):
    d = HERE / "out" / sc.pose_dir
    scene = json.loads((d / "scene.json").read_text())
    slug = scene["slug"]
    bodies = {b["name"]: b for b in scene["bodies"]}
    rails = [bodies[g]["bbox"] for g in GUIDES]
    x0, x1 = min(b[0] for b in rails), max(b[3] for b in rails)
    track = x1 - x0
    mod_dx = track + sc.gap
    spec = mujoco.MjSpec()
    spec.modelname = f"{slug}_{sc.name}"
    spec.option.timestep = timestep
    spec.option.cone = mujoco.mjtCone.mjCONE_ELLIPTIC
    spec.option.impratio = 10.0
    spec.visual.global_.offwidth, spec.visual.global_.offheight = 960, 540
    spec.worldbody.add_light(pos=[0.3, 0.1, 2.5], dir=[0, 0, -1], diffuse=[0.8, 0.8, 0.8])
    spec.worldbody.add_light(pos=[-1, -1, 2], dir=[0.4, 0.4, -1], diffuse=[0.4, 0.4, 0.4])
    spec.worldbody.add_geom(name="floor", type=mujoco.mjtGeom.mjGEOM_PLANE, size=[3, 3, 0.1],
                            rgba=[0.35, 0.37, 0.4, 1], pos=[0.3, 0.1, 0])
    offsets = [(0.0, 0.0, 0.0), (mod_dx, sc.m2_offset[0], sc.m2_offset[1])]
    for i, (dx, dy, dz) in enumerate(offsets):
        child = mujoco.MjSpec.from_file(str(d / f"{slug}.xml"))
        f = spec.worldbody.add_frame(pos=[dx * MM, dy * MM, dz * MM])
        f.attach_body(child.body(slug), f"m{i}/", "")
    for g in spec.geoms:
        if g.name.endswith("__vis") and "_belt" in g.name:
            g.group = 4                                   # the CAD belt loop: hidden, the tread stands in
        elif g.group == 3:
            g.friction = [sc.mu_guide, 0.005, 0.0001]
            g.contype, g.conaffinity = 1, 1
            g.solref, g.solimp = SOLREF, SOLIMP
    treads = []
    for i, (dx, dy, dz) in enumerate(offsets):
        for bname, belt in scene["belts"].items():
            tr = Tread(belt, pitch)
            ratio = sc.speed_ratio.get(bname, 1.0)
            for k in range(tr.n):
                b = spec.worldbody.add_body(name=f"m{i}/{bname}/s{k}", pos=[dx * MM, (dy + tr.yc) * MM, dz * MM])
                for jn, jt, ax in (("x", mujoco.mjtJoint.mjJNT_SLIDE, [1, 0, 0]),
                                   ("z", mujoco.mjtJoint.mjJNT_SLIDE, [0, 0, 1]),
                                   ("a", mujoco.mjtJoint.mjJNT_HINGE, [0, 1, 0])):
                    b.add_joint(name=f"m{i}/{bname}/s{k}/{jn}", type=jt, axis=ax,
                                armature=1e4 if jt == mujoco.mjtJoint.mjJNT_SLIDE else 1e2)
                # a capsule across the belt, radius half the belt's thickness: its outer surface is exactly the
                # belt's outer face on the flat run and on the pulley arcs (no polygon bump at the wraps)
                b.add_geom(name=f"m{i}/{bname}/s{k}", type=mujoco.mjtGeom.mjGEOM_CAPSULE,
                           size=[tr.t / 2 * MM, (tr.w - tr.t) / 2 * MM, 0], quat=[SQ, -SQ, 0, 0],
                           rgba=[0.12, 0.12, 0.12, 1] if k % 2 else [0.3, 0.3, 0.33, 1],
                           friction=[sc.mu_belt, 0.005, 0.0001], contype=2, conaffinity=0, mass=0.001,
                           solref=SOLREF, solimp=SOLIMP)
            treads.append((i, bname, tr, ratio))
    # the board
    L, Wb, T = sc.board
    belts = list(scene["belts"].values())
    top_z = belts[0]["top_z"]
    yc = np.mean([(b["y"][0] + b["y"][1]) / 2 for b in belts]) + sc.start_offset[0]
    xa = belts[0]["run"][0]
    bx = xa + 5.0 + L / 2.0                              # trailing edge 5 mm onto the flat top run
    yaw0 = math.radians(sc.start_offset[1])
    board = spec.worldbody.add_body(name="board", pos=[bx * MM, yc * MM, (top_z + T / 2 + 0.2) * MM],
                                    quat=[math.cos(yaw0 / 2), 0, 0, math.sin(yaw0 / 2)])
    board.add_freejoint(name="board")
    mass = sc.mass if sc.mass else FR4_DENSITY * L * Wb * T * 1e-9
    board.add_geom(name="board", type=mujoco.mjtGeom.mjGEOM_BOX, size=[L / 2 * MM, Wb / 2 * MM, T / 2 * MM],
                   mass=mass, rgba=[0.1, 0.55, 0.2, 1], friction=[0.01, 0.005, 0.0001], contype=1, conaffinity=3,
                   solref=SOLREF, solimp=SOLIMP)
    model = spec.compile()
    geo = {"top_z": top_z, "track": track, "mod_dx": mod_dx, "x0": x0, "x1": x1, "mass": mass,
           "belt_run": belts[0]["run"], "yc": yc, "yaw0": yaw0, "board": sc.board, "m2_offset": offsets[1]}
    return model, treads, geo


# ─── Running ─────────────────────────────────────────────────────────────────────────────────────────────────

def _rpy(R):
    return (math.atan2(R[2, 1], R[2, 2]), math.asin(max(-1, min(1, -R[2, 0]))), math.atan2(R[1, 0], R[0, 0]))


def run(sc: Scenario, pitch=2.0, timestep=0.0005, frames_every=None, render_size=(640, 360), log=print):
    model, treads, geo = build(sc, pitch, timestep)
    data = mujoco.MjData(model)
    # tread joint addresses
    tidx = []
    for i, bname, tr, ratio in treads:
        qa = np.array([[model.jnt_qposadr[model.joint(f"m{i}/{bname}/s{k}/{j}").id] for j in "xza"]
                       for k in range(tr.n)])
        va = np.array([[model.jnt_dofadr[model.joint(f"m{i}/{bname}/s{k}/{j}").id] for j in "xza"]
                       for k in range(tr.n)])
        tidx.append((tr, ratio, qa, va))
    bid = model.body("board").id
    gboard = model.geom("board").id
    names = [mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, g) or "" for g in range(model.ngeom)]

    def category(n):
        if "_belt/s" in n:
            return n.split("/")[0] + " belt"
        base = n.split("/", 1)[-1].split("__")[0]
        return n.split("/")[0] + " guide rail" if base in GUIDES else base

    cats = [category(n) for n in names]
    L, Wb, T = sc.board
    corners = np.array([[sx * L / 2, sy * Wb / 2, -T / 2] for sx in (-1, 1) for sy in (-1, 1)]) * MM
    v_set = sc.speed / 60.0 * 1000.0                  # mm/s
    top_z = geo["top_z"]
    m2_belt_x0 = geo["mod_dx"] + geo["belt_run"][0]
    x_goal = m2_belt_x0 + L / 2.0 + 20.0              # fully on module 2's flat run
    dist = x_goal - (geo["belt_run"][0] + 5 + L / 2)
    t_max = 1.0 + sc.ramp + 2.0 * dist / v_set + 3.0
    travel = 0.0
    t_stop = None
    rec = []
    contacts_seen = {}
    frames = []
    renderer = None
    cam = None
    if frames_every:
        renderer = mujoco.Renderer(model, render_size[1], render_size[0])
        for g in range(model.ngeom):          # see-through guide rails, so the board's edge shows from the side
            if names[g].split("/")[-1].removesuffix("__vis") in GUIDES and names[g].endswith("__vis"):
                model.geom_rgba[g, 3] = 0.25
        cam = mujoco.MjvCamera()
        cam.type = mujoco.mjtCamera.mjCAMERA_FREE
        small = sc.board[0] < 100
        cam.distance, cam.elevation, cam.azimuth = (0.22, -8.0, -90.0) if small else (0.75, -28.0, -125.0)
        opt = mujoco.MjvOption()
    mujoco.mj_forward(model, data)
    nstep = int(t_max / timestep)
    rec_every = max(1, int(0.005 / timestep))
    done_at = None
    stalled, stalled_for = False, 0.0
    t0 = time.time()
    t_belt0 = 0.2                                    # the board is dropped, the belts start at 0.2 s
    for step in range(nstep):
        t = data.time
        bx_mm = data.xpos[bid][0] / MM
        if sc.stop_at is not None and t_stop is None and bx_mm >= sc.stop_at:
            t_stop = t
        if t < t_belt0:
            v = 0.0
        else:
            v = v_set * min(1.0, (t - t_belt0) / sc.ramp) if sc.ramp > 0 else v_set
        if t_stop is not None:
            v *= max(0.0, 1.0 - (t - t_stop) / sc.stop_ramp) if sc.stop_ramp > 0 else 0.0
        travel += v * timestep
        for tr, ratio, qa, va in tidx:
            q, qd = tr.state(travel * ratio, v * ratio)
            data.qpos[qa] = q
            data.qvel[va] = qd
        mujoco.mj_step(model, data)
        if step % rec_every == 0:
            R = data.xmat[bid].reshape(3, 3)
            p = data.xpos[bid]
            cz = (p + corners @ R.T)[:, 2] / MM - top_z
            roll, pitch_, yaw = _rpy(R)
            touch = {}
            f6 = np.zeros(6)
            rail_fn = 0.0
            g1, g2 = data.contact.geom1[:data.ncon], data.contact.geom2[:data.ncon]
            for ci in np.nonzero((g1 == gboard) | (g2 == gboard))[0]:
                k = cats[g2[ci] if g1[ci] == gboard else g1[ci]]
                touch[k] = touch.get(k, 0) + 1
                contacts_seen[k] = contacts_seen.get(k, 0) + 1
                if k.endswith("guide rail"):
                    mujoco.mj_contactForce(model, data, int(ci), f6)
                    rail_fn += abs(f6[0])
            rec.append((t, p[0] / MM, p[1] / MM, p[2] / MM - top_z - T / 2, math.degrees(roll), math.degrees(pitch_),
                        math.degrees(yaw - geo["yaw0"]), data.qvel[model.jnt_dofadr[model.joint("board").id]] / MM,
                        v, travel, cz.min(), cz.max(), touch.get("m0 belt", 0), touch.get("m1 belt", 0),
                        touch.get("m0 guide rail", 0) + touch.get("m1 guide rail", 0), rail_fn))
        if frames_every and step % int(frames_every / timestep) == 0:
            cam.lookat[:] = [data.xpos[bid][0], geo["yc"] * MM, top_z * MM]
            renderer.update_scene(data, cam)
            frames.append((data.time, renderer.render().copy()))
        z_c = data.xpos[bid][2] / MM - top_z
        if z_c < -60:
            log(f"  {sc.name}: board fell (z {z_c:.0f} mm) at t {t:.2f}")
            break
        if v > 0 and data.qvel[model.jnt_dofadr[model.joint("board").id]] / MM < 0.05 * v:
            stalled_for += timestep
            if stalled_for > 3.0:
                log(f"  {sc.name}: board stalled at x {bx_mm:.1f} mm, t {t:.2f} s")
                stalled = True
                break
        else:
            stalled_for = 0.0
        if done_at is None and (bx_mm >= x_goal or (t_stop is not None and v == 0.0)):
            done_at = t
        if done_at is not None and t > done_at + 0.5:
            break
    wall = time.time() - t0
    cols = ["t", "x", "y", "z", "roll", "pitch", "yaw", "vx", "v_belt", "travel", "zmin", "zmax", "n_m1", "n_m2",
            "n_rail", "rail_fn"]
    arr = np.array(rec)
    res = {c: arr[:, i] for i, c in enumerate(cols)}
    res["contacts_seen"] = contacts_seen
    res["t_stop"] = t_stop
    res["wall"] = wall
    res["stalled"] = stalled
    res["steps"] = step + 1
    return res, geo, frames


# ─── Checks ──────────────────────────────────────────────────────────────────────────────────────────────────

def checks(sc: Scenario, r: dict, geo: dict) -> dict:
    L = sc.board[0]
    t = r["t"]
    settled = t > 0.15
    xa, xb = geo["belt_run"]
    m2a = geo["mod_dx"] + xa
    lead, trail = r["x"] + L / 2, r["x"] - L / 2
    transfer = settled & (lead > xb) & (trail < m2a)
    # heights are measured from the pass line of the module the board's centre is over (module 2 may be offset)
    dz2 = geo["m2_offset"][2]
    zref = np.where(r["x"] > (xb + m2a) / 2.0, dz2, 0.0)
    r = dict(r, zmin=r["zmin"] - zref, zmax=r["zmax"] - zref, z=r["z"] - zref)
    out = {}
    final_x = r["x"][-1]
    on_m2 = (r["n_m2"][-1] > 0) and (r["n_m1"][-1] == 0)
    if sc.stop_at is None:
        goal = m2a + L / 2
        out["reaches module 2"] = (final_x >= goal and on_m2,
                                   f"final centre x {final_x:.0f} mm (needs >= {goal:.0f}, on m2 belts only: {on_m2})")
    else:
        out["reaches stop point"] = (final_x >= sc.stop_at - 5, f"stopped at x {final_x:.1f} mm")
    yaw = np.abs(r["yaw"][settled]).max()
    out["yaw < 1 deg"] = (yaw < 1.0, f"max |yaw| {yaw:.3f} deg")
    carry = settled & ~transfer                     # (a pitching board lifts its tail over the gap: not a climb)
    climb = r["zmax"][carry].max()
    roll = np.abs(r["roll"][carry]).max()
    out["no rail climb"] = (climb < 0.5 and roll < 0.5,
                            f"highest corner {climb:+.2f} mm over pass line, max |roll| {roll:.3f} deg")
    lowc = r["zmin"][settled].min()
    out["never falls through"] = (lowc > -2.0 and r["z"][-1] > -1.0,
                                  f"lowest corner {lowc:+.2f} mm, final centre z {r['z'][-1]:+.2f} mm")
    if transfer.any():
        pit = np.abs(r["pitch"][transfer]).max()
        dip = r["zmin"][transfer].min()
        out["transfer pitch < 1 deg"] = (pit < 1.0, f"max |pitch| {pit:.3f} deg over the gap, lowest corner {dip:+.2f} mm")
    elif sc.stop_at is None:
        out["transfer pitch < 1 deg"] = (False, "board never crossed the gap")
    # slip: board displacement vs belt travel while carried on module 1's flat run
    carried = settled & (trail > xa) & (lead < xb)
    if carried.any():
        i0, i1 = np.argmax(carried), len(carried) - 1 - np.argmax(carried[::-1])
        k = np.mean(list(sc.speed_ratio.values()) + [1.0] * (2 - len(sc.speed_ratio)))   # the belts' mean speed
        slip = k * (r["travel"][i1] - r["travel"][i0]) - (r["x"][i1] - r["x"][i0])
        vrel = k * r["v_belt"][carried] - r["vx"][carried]
        out["no belt slip"] = (abs(slip) < 1.0, f"slip {slip:+.2f} mm over {r['travel'][i1]-r['travel'][i0]:.0f} mm "
                                                f"of belt travel; max |v_belt - v_board| {np.abs(vrel).max():.2f} mm/s")
    # a step start: how far the belt runs ahead of the board before the board is up to speed
    i = np.searchsorted(t, 0.2 + max(sc.ramp, 0.0) + 0.3)
    if i < len(t):
        k0 = np.searchsorted(t, 0.19)
        s0 = (r["travel"][i] - r["travel"][k0]) - (r["x"][i] - r["x"][k0])
        out["start slip < 1 mm"] = (abs(s0) < 1.0, f"{s0:+.3f} mm (belt 0 -> {sc.speed:g} m/min in {sc.ramp*1000:.0f} ms)")
    if r["t_stop"] is not None:
        k0 = np.searchsorted(t, r["t_stop"])
        over = (r["x"][-1] - r["x"][k0]) - (r["travel"][-1] - r["travel"][k0])
        out["stop slip < 1 mm"] = (abs(over) < 1.0, f"board overran the belt by {over:+.3f} mm (stop in "
                                                    f"{sc.stop_ramp*1000:.0f} ms)")
    fn = r["rail_fn"][settled]
    out["rail drag"] = (True, f"max guide-rail normal force {fn.max():.3f} N, mean {fn.mean():.3f} N "
                              f"(board weight {geo['mass']*G:.2f} N)")
    others = {k: v for k, v in r["contacts_seen"].items() if k not in ("m0 belt", "m1 belt", "m0 guide rail", "m1 guide rail")}
    out["touches only belts and rail faces"] = (not others, ", ".join(f"{k} ({v} samples)" for k, v in others.items())
                                                or "yes")
    return out


# ─── Output ──────────────────────────────────────────────────────────────────────────────────────────────────

def plot(sc, r, geo, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(4, 1, figsize=(8, 9), sharex=True)
    t = r["t"]
    ax[0].plot(t, r["x"], color="#2a6fdb", label="board centre x")
    ax[0].plot(t, r["travel"] + r["x"][0], color="#999", ls="--", lw=1, label="belt travel (from start)")
    for xv, lab in ((geo["belt_run"][1], "m1 belt end"), (geo["mod_dx"] + geo["belt_run"][0], "m2 belt start")):
        ax[0].axhline(xv, color="#c44", lw=0.8, ls=":")
        ax[0].text(t[0], xv, lab, fontsize=7, color="#c44", va="bottom")
    ax[0].set_ylabel("x, mm")
    ax[0].legend(fontsize=7, loc="lower right")
    ax[1].plot(t, r["yaw"], label="yaw", color="#2a6fdb")
    ax[1].plot(t, r["pitch"], label="pitch", color="#d9822b")
    ax[1].plot(t, r["roll"], label="roll", color="#3a9a5b")
    ax[1].set_ylabel("deg")
    ax[1].legend(fontsize=7)
    ax[2].plot(t, r["zmax"], label="highest corner", color="#d9822b")
    ax[2].plot(t, r["zmin"], label="lowest corner", color="#2a6fdb")
    ax[2].set_ylabel("over pass line, mm")
    ax[2].legend(fontsize=7)
    ax[3].plot(t, r["vx"], label="board vx", color="#2a6fdb")
    ax[3].plot(t, r["v_belt"], label="belt", color="#999", ls="--")
    ax[3].set_ylabel("mm/s")
    ax[3].set_xlabel("t, s")
    ax[3].legend(fontsize=7)
    fig.suptitle(f"{sc.name}: {sc.note}", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def save_frames(frames, gif_path, strip_path, window=None, n_strip=6):
    """An animated GIF of every other frame, and a strip of n_strip frames (over `window`, (t0, t1), if given)."""
    from PIL import Image
    ims = [Image.fromarray(f) for _, f in frames]
    ts = np.array([t for t, _ in frames])
    if not ims:
        return
    small = [im.resize((im.width // 2, im.height // 2)) for im in ims[::2]]
    small[0].save(gif_path, save_all=True, append_images=small[1:], duration=120, loop=0, optimize=True)
    sel = np.arange(len(ims))
    if window is not None and ((ts >= window[0]) & (ts <= window[1])).sum() >= n_strip:
        sel = np.nonzero((ts >= window[0]) & (ts <= window[1]))[0]
    pick = [ims[sel[int(i)]] for i in np.linspace(0, len(sel) - 1, n_strip)]
    w, h = pick[0].size
    strip = Image.new("RGB", (w * 3, h * ((len(pick) + 2) // 3)))
    for i, im in enumerate(pick):
        strip.paste(im, ((i % 3) * w, (i // 3) * h))
    strip.save(strip_path)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("scenarios", nargs="*", help=f"any of {', '.join(SCENARIOS)}")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--speed", type=float, help="override belt speed, m/min")
    ap.add_argument("--pitch", type=float, default=2.0, help="tread segment pitch, mm")
    ap.add_argument("--timestep", type=float, default=0.0005)
    ap.add_argument("--video", action="append", default=[], metavar="SCENARIO",
                    help="render a GIF + frame strip of this scenario (EGL/OSMesa offscreen)")
    ap.add_argument("--out", default=str(HERE / "results"))
    a = ap.parse_args(argv)
    names = list(SCENARIOS) if a.all or not a.scenarios else a.scenarios
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    summary = {}
    for n in names:
        sc = SCENARIOS[n]
        if a.speed:
            sc = replace(sc, speed=a.speed)
        vid = n in a.video
        r, geo, frames = run(sc, a.pitch, a.timestep, frames_every=0.1 if vid else None)
        ck = checks(sc, r, geo)
        ok = all(v[0] for v in ck.values())
        print(f"{n}: {'PASS' if ok else 'FAIL'}  ({sc.note}; mass {geo['mass']*1000:.0f} g; "
              f"{r['t'][-1]:.1f} s simulated in {r['wall']:.0f} s)")
        for k, (p, msg) in ck.items():
            print(f"    {'PASS' if p else 'FAIL'}  {k}: {msg}")
        plot(sc, r, geo, out / f"{n}.png")
        if vid:
            L = sc.board[0]
            over = (r["x"] + L / 2 > geo["belt_run"][1]) & (r["x"] - L / 2 < geo["mod_dx"] + geo["belt_run"][0])
            win = (r["t"][over][0] - 0.5, r["t"][over][-1] + 0.5) if over.any() else None
            save_frames(frames, out / f"{n}.gif", out / f"{n}_frames.png", win)
        summary[n] = {"note": sc.note, "speed_m_min": sc.speed, "mass_g": geo["mass"] * 1000, "mu_belt": sc.mu_belt,
                      "mu_guide": sc.mu_guide, "pass": ok, "sim_s": float(r["t"][-1]),
                      "checks": {k: {"pass": bool(p), "detail": m} for k, (p, m) in ck.items()},
                      "contacts_seen": r["contacts_seen"]}
        (out / f"{n}.json").write_text(json.dumps(summary[n], indent=1))
    return 0 if all(s["pass"] for s in summary.values()) else 1


if __name__ == "__main__":
    sys.exit(main())

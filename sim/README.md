# sim: MuJoCo checks of CAD assemblies

Two halves, two interpreters:

| step | code | interpreter |
|---|---|---|
| CAD assembly -> meshes, convex collision pieces, MJCF, `scene.json` | `cad_agent/sim_export.py` | `.venv/bin/python` (build123d) |
| scenario, physics, checks, plots, frames | `sim/mujoco_conveyor.py` | `~/work/sim-venv/bin/python` (MuJoCo 4.0.1, numpy, matplotlib) |

## Export any assembly

```sh
.venv/bin/python -m cad_agent.sim_export <slug> --out sim/out/<slug>_<pose> [--pose NAME] \
    [--belt BODY ...] [--exclude BODY ...] [--free BODY=DENSITY ...] [--collision BODY=MODE ...] [--axes static|joint]
```

Writes `<slug>.xml` (MJCF; one body `<slug>` welded to the world; visual meshes in geom group 1, collision pieces
in group 3; mm meshes scaled to metres), `scene.json` (roles, axes, pose, bounding boxes, belt paths) and
`meshes/*.stl`. The MJCF loads on its own (`python -m mujoco.viewer --mjcf sim/out/.../<slug>.xml`) or can be
attached into a larger scene with `MjSpec` (`frame.attach_body(child.body(slug), prefix, "")`), which is how the
conveyor runner places two modules.

- **Poses and axes.** `--pose` applies `POSES[name]` (via `subassembly.apply_pose`). Bodies an axis moves go into a
  child body `axis_<name>`; `--axes joint` gives it a slide joint (travel as range) and a position actuator.
- **Collision.** MuJoCo collides only the convex hull of a mesh. `auto` (default) splits each body into convex
  pieces: it cuts the bounding box on every axis-aligned planar face of the solid, keeps the cells the solid fills,
  merges fully filled cells greedily into boxes (partly filled cells, e.g. a chamfer, stay separate) and intersects
  the solid with each box (exact OCC boolean). Exact for concave features made of axis-aligned planes (ledges, steps,
  slots); round holes and slanted grooves get filled by the hull. Falls back to the whole hull past 32 pieces.
  Other modes: `hull`, `boxes` (primitive boxes; fastest, loses chamfers), `none`.
  The pcb_conveyor rail comes out as 10-11 pieces: the bar, the belt ledge, and the end blocks with the lead-in
  chamfers; its hull alone would have filled the space above the ledge where the board rides.
- **Belts.** `--belt` bodies are exported visual-only; `scene.json` gets their path (top-run height, y span, end
  pulley centres, outer/inner wrap radius) read from the belt solid's cylindrical faces, for the simulator to model
  as a moving surface. Belts travelling along x only, for now.

## The conveyor check

```sh
.venv/bin/python -m cad_agent.sim_export pcb_conveyor --pose carrier --belt front_belt --belt rear_belt \
    --exclude test_board --out sim/out/pcb_conveyor_carrier
.venv/bin/python -m cad_agent.sim_export pcb_conveyor --belt front_belt --belt rear_belt \
    --exclude test_board --out sim/out/pcb_conveyor_home
MUJOCO_GL=egl ~/work/sim-venv/bin/python sim/mujoco_conveyor.py --all --video nominal_2 --video small_49x40_home      # or: ... nominal_2 slip_500g
~/work/sim-venv/bin/python sim/report.py                                             # results/*.json -> results/RESULTS.md
```

Each scenario prints PASS/FAIL per check and writes `sim/results/<scenario>.png` (x, yaw/pitch/roll, corner
heights, board vs belt speed over time) and `<scenario>.json`; `--video` adds `nominal_2.gif` and
`nominal_2_frames.png` (EGL offscreen rendering). `sim/out/` is generated and not committed.

How the belts are modelled is in the docstring of `mujoco_conveyor.py`; per-scenario numbers are in
[results/RESULTS.md](results/RESULTS.md).

# cad-agent v2: CLI-first, with a verifier

*2026-09-28. Plan, not started. v1 (PLAN.md, README.md) is built and green: 22 MCP tools, 129 tests, Metal renders, gates for geometry, fit, motion, tooling, visual, provenance.*

## Goal

A 3D design harness any agent drives from the shell. The agent doesn't decide when a design is done. An independent verifier decides, by rebuilding everything from source and checking it against a written spec.

## What the research changed (2026-09-28)

Full map: [research/reports/CLI CAD agent landscape 2026.md](<research/reports/CLI CAD agent landscape 2026.md>).

- **Nobody has the whole thing.** v1 already matches or leads the field on interference, wall thickness, motion sweeps, keep-outs, visual regression and provenance. The open gap is the out-of-process verifier with source hashing, the spec, and the eval set: steps 2, 3 and 6 below.
- **Borrow:**
  - agentcad: JSON on stdout, progress on stderr (step 1).
  - CADCLAW: its gate names (interference, adjacency, dimensional, orientation, tolerance, BOM) and its `checked` / `not_checked` / `assumptions` report, for `spec.toml` and `verify.json` (steps 2–3).
  - MARB: "one grader, open method" for the eval set (step 6).
- **Evidence for the design.** build123d-mcp's own sweeps found that a verifier the agent calls in-process scores *worse*, because the agent reads "conforms" as a stop signal. So `cad verify` stays a separate process whose verdict the agent can't overrule.
- **Evaluate:** cad-khana's bisected motion-sweep onset and crease-aware wall thickness against ours (step 5).
- **Adopt:** bd_warehouse for fasteners, bearings and NEMA17/23 motors. Build our own MGN12/15 rail and 2020/2040 T-slot profiles, because nobody has them (step 5).

## Why CLI instead of MCP

This was your call on 2026-09-28. The reasons:

- **Context.** No tool schemas sit in the context. The agent reads `cad --help` when it needs to.
- **Scriptable.** Sweeps, loops and pipes are plain bash, and the same commands work in subagents, CI, or any model (the fab-gym idea).
- **No server lifecycle.** Edit the code and the next command uses it. MCP needs a reconnect.
- **One path for everyone.** A human and an agent run the same commands and see the same output.

## The CLI

It's a thin wrapper over the functions the MCP tools already call. Nothing new underneath.

```
cad init <slug>
cad ls [<slug>]                              projects, or one project's parts and bought parts
cad status <slug>
cad build <slug> <part> [--set k=v ...]      bbox, volume, mass, measured wall
cad render <slug> [<part>] [--view iso|top|front|section|exploded]   prints the PNG path
cad check <slug> [--part <p>]                every gate; writes checks.json and prints the table
cad rules                                    what a run checks
cad measure <slug> <a> <b>                   min distance or overlap volume
cad solve <slug> <part> --param k=lo:hi      margin-driven search (solve.py)
cad tool <kind> [dims...]                    tool envelope: drill, laser cone, syringe
cad bought add-step|add-measured|ls|info|verify ...
cad tables [holes|inserts|extrusions]
cad approve <slug> <subject> <view>          human step: accept a render as the new baseline
cad cutlist <slug>
cad export <slug> [<part>] --step|--stl|--dxf
cad verify <slug>                            the verifier (below)
```

Conventions:
- Every command prints a short human-readable table by default, or JSON with `--json`.
- Exit codes: 0 pass, 1 fail, 2 unchecked, 3 usage error, 4 crash (a cad-agent bug, never a verdict).
- **Warm worker** (`cad_agent/warm.py`). Importing build123d costs 20–35 s here, so the first call starts a background worker that imports it once. Every command then runs in a fresh fork of that worker, in about 1 s. `CAD_WARM=0` runs cold; `cad warm status|stop`.
- Renders are files; the agent opens them with Read.
- The tests drive the CLI through a subprocess, so the CLI itself is what's tested.

## The verifier: `cad verify <slug>`

1. It runs in a **fresh process with a clean cache** and rebuilds every part and the assembly from source. It trusts nothing the agent ran earlier, including the agent's own `checks.json`.
2. It runs every gate, then the project's **spec** (below), then the render baselines and the provenance check.
3. It **hashes every source file** (parts, assembly, spec, bought). A result produced from older sources counts as stale, and a stale result fails.
4. It writes `verify.json` and a one-line verdict. The exit code is the verdict: pass only with zero FAIL and zero UNCHECKED rows.
5. It's the only way a project becomes done. `done_check` folds into it.

It also reports every baseline that changed since the last human `approve`, so the agent can't quietly bless its own renders.

## The spec: `spec.toml`, the brief as acceptance tests

```toml
[envelope]
max_mm = [550, 450, 450]
work_area_mm = [200, 200]

[[keepout]]              # laser beam cone must stay clear while the gantry is parked
tool = "laser_cone"; focal_mm = 210; field_mm = 150
clear = ["gantry_beam", "carriage"]; at = "park"

[[interface]]            # bolt holes that must line up
a = "x_carriage"; b = "mgn12h_block"; fastener = "M3"; tol_mm = 0.1

[[heat]]
zone = "dock"; temp_c = 250; radius_mm = 60   # material service temp must be at least the zone temp

[budget]
head_mass_g = 400
beam_deflection_um = { max = 50, load_n = 10 }
```

Each requirement becomes a PASS / FAIL / UNCHECKED row with the measured value, the limit and the source, exactly like the gates.

## What designing a whole machine needs next

- **Models from outside.** Two different jobs:
  - **Real geometry of what we buy**, where accuracy matters: vendor STEP files.
    - Manual download, or an API where one exists (TraceParts with a partner key; McMaster-Carr's needs approval).
    - Registered with `cad bought add-step --source <url>`, which already refuses geometry without a source.
    - bd_warehouse gives parametric NEMA motors, OpenBuilds extrusion and fasteners with no download.
    - AliExpress parts rarely have models: measure them (`add-measured`, then `verify`).
  - **Inspiration**: `cad find "<query>"` searches Thingiverse (official API, needs a free app token you create) and Printables (unofficial API, best effort). It lists title, license, link and thumbnail, and shows them in the workbench.
    - Downloads land in `inspiration/`, never in a design.
    - Most are non-commercial licences, so ideas only, per the earlier rule (clean-room our own parts).
  - The MCP registry has no connector for any of these (checked 2026-09-28), so this is CLI.
- **Parts library** shared across projects: vendor STEPs with sources for MGN12, NEMA17/NEMA8, 2020/2040, GT2, fasteners, inserts, 858D, galvo head, cameras, pump. Today each project imports its own.
- **Sub-assemblies**: frame, gantry, head, dock, laser and enclosure, each placed into one machine assembly.
- **New rules**:
  - interface (holes coaxial, clearance on one side and tap/insert on the other)
  - heat zone (material vs local temperature)
  - moving mass
  - beam deflection (formulas, not FEA)
- **Shop outputs**: DXF for laser-cut panels, dimensioned PDF drawings for machined plates, print-ready STL/3MF, one BOM and order list.
- **Eval set**: about 10 small design tasks, each a brief plus a hidden `spec.toml`. The agent designs through the CLI only, and `cad verify` scores the result. Run it before and after every harness change, so "better" is a number. Examples: NEMA17 mount on 2040, MGN12H carriage plate, syringe clamp, hot-plate standoff, pinned carrier with relief pocket, galvo head mount with beam keep-out, laser-cut panel.
- **Optional second opinion**: a reviewer subagent reads `verify.json` and the renders, and lists what no rule covers (assembly order, tool access, cables). Its findings become new spec lines or rules, never verdicts.

## Native in the Claude Code app

The CLI is the engine and the app drives it. No MCP.

| Piece | What it does |
|---|---|
| **Skill `/cad`** (replaces `skills/mech-design.md` and the MCP) | Loads the design contract and the loop only when invoked: brief → `spec.toml` → parts → `cad check` → `cad verify` → report. Every command runs through Bash. |
| **PostToolUse hook** on edits to `parts/*.py` or `assembly.py` | Runs `cad check <slug> --part <p> --json` and hands Claude only the failing rows, so gate feedback arrives on every save without being asked for. |
| **Stop hook** | Runs `cad verify` on any project whose sources changed since the last verify (the hash check keeps this fast). A FAIL or UNCHECKED blocks the stop and feeds back the verdict, so the agent can't declare done over a red verifier. A counter caps the retries: after that, the session may end, but only with the failure stated. |
| **Reviewer subagent** (`.claude/agents/cad-reviewer.md`) | Read-only: Read, `cad render`, `cad verify`. Looks at renders and `verify.json` and lists what no rule covers. It can't edit and can't pass anything. |
| **Live 3D view in the app** | `cad serve <slug>` runs a small local three.js page that loads the GLB export and reloads on every rebuild. A `.claude/launch.json` entry lets the app's Browser pane open it, so you watch the part change while Claude works. **Prototype working (2026-09-28):** `viewer/export_glb.py <slug>` plus `viewer/index.html`, served by the `cad-viewer` entry in `~/ws/.claude/launch.json`. It shows assembly_cell and desk_fab_line in the pane and reloads within ~1.5 s of a re-export. Claude screenshots the same pane. |
| **Workbench** (grows out of the live view) | One local page in the Browser pane with four panels:<br>• **Parts:** every project and part with its gate status.<br>• **3D view:** live.<br>• **Verifier:** `verify.json` rows, measured value vs limit.<br>• **Activity:** a live feed of every `cad` command the agent ran, with its result and the renders it looked at, fed by the log below.<br>It's read-only, except the "approve render" button, which is your step. Wrapped tools (slicer, FEA) log to the same feed. |
| **Activity log** | Every `cad` command appends one JSON line to `projects/<slug>/.cad/log.jsonl`: time, command, arguments, exit code, short summary, files written. |
| **Review page** | `cad page <slug>` writes one HTML page (renders, gate table, BOM, unverified items) that can be published as an artifact for approval. |
| **Permissions** | Allowlist `cad *` in the project's `.claude/settings.json` so the loop doesn't prompt on every command (ask first). |
| **Plugin (later)** | Bundle the skill, hooks, agent and launch config as a Claude Code plugin, so any project gets all of it with one install. |

## Packaging as a Claude app (idea, 2026-09-28)

Which package fits depends on who uses it. The engine stays a CLI with a verifier either way, so each option below only wraps it:

| For | Package | What it adds | Cost |
|---|---|---|---|
| Us, developers | **Claude Code plugin** | One install from a GitHub marketplace: the CLI, the `/cad` skill, the hooks, the reviewer agent, and the workbench launch config. Mostly step 4 plus packaging. | Low. Setup must build the ~860 MB environment (uv) |
| People who don't code, in normal Claude chat | **MCP App or desktop extension** | The 3D view, check table and approve button render inside the conversation. The UI protocol is MCP, so a thin MCP layer calls the same CLI. | Medium. The engine must run locally (desktop extension) or on a hosted server |
| Customers, as a product | **Standalone app on the Agent SDK** | Its own window, its own agent loop, the same engine | High |

Recommended order: plugin first, then the others only if a real audience asks for them.

**Decided 2026-09-28: the standalone app (option 3), built around git, but the harnesses come first.** The app is a shell: a window, an agent loop and a git panel. The real work, and the hard part, is one harness per domain, all the same shape: a CLI with `--json` and exit codes, an independent verifier, a spec, and an eval set. Order: 3D (`cad`, this plan), then boards (hw-agent gets the same treatment), then the machines (station drivers plus a job verifier). The app comes after the harnesses hold up.

What "built around git" means:
- A project is a repo. `desk-fab-line` was initialized locally on 2026-09-28.
- The agent works on a branch, and every change is a commit.
- Design variants are branches, compared by renders and verifier results.
- `cad verify` ties its verdict to the git tree hash, so "passed" means "passed at this commit", and a dirty tree is stale by definition.
- Approving a render is a commit with a name on it. CI runs the verifier on every pull request.

**Collaborating inside it** (you, Seb, whoever joins):
- **Git is the source of truth.** A design is Python parts, `spec.toml`, `checks.json` and the approved renders, all diffable. Every change is a pull request.
- **The verifier runs in CI.** `cad verify` runs on every pull request (Linux, numpy renderer), so neither the author nor their agent decides a design passes.
- **Shared review page.** `cad page` is published as an artifact the others can open. They comment on it, and "approve render" records who approved and when. Approval stays a human step, and now it has a name on it.
- **claude-share for sessions,** already set up with Seb, so each person sees how the other's agent got to a design.
- Everyone runs the same plugin locally, and the workbench stays per person.

## Build order

Each step ends with the tests green.

1. `cad` CLI at parity with the 22 MCP tools, with `--json`, exit codes and the activity log; tests go through the CLI. **Done 2026-09-28:**
   - `cad_agent/cli.py`, `bin/cad`, and the warm worker.
   - Extras beyond the MCP tools: `measure --posed`, `--projects` / `CAD_PROJECTS`, and fast failure on typos before the kernel loads.
   - 21 new tests; 150 passing.
2. `cad verify`: fresh process, clean rebuild, verdict tied to the git tree hash (source hashing when there is no repo). **Done 2026-09-28** (`cad_agent/verify.py`):
   - `verify.json` records the verdict plus the design-file hash, a hash of cad-agent's own code, the git commit and tree, uncommitted design changes, and whether the process was fresh.
   - `cad done` accepts only a PASS whose hashes still match the disk, from a fresh process, and on committed work. It reads files only, so it answers in half a second.
   - 9 new tests; 159 passing. First real run: assembly_cell PASS at commit 8055012.
3. `spec.toml`, starting with envelope, keep-out, clearance and interface.
4. Claude Code wiring: the `/cad` skill, the check and verify hooks, the reviewer agent, the `cad` allowlist. Then retire MCP: delete the project-scoped `cad` entry in `~/.claude.json` (ask first), then `mcp_app.py`.
5. The workbench (`cad serve` + launch config: parts, live 3D, verifier, activity feed, approve button) and the review page (`cad page`).
6. Machine scale: parts library, sub-assemblies, the heat, mass and deflection rules, shop outputs.
7. The eval set and its scores.
8. First real job: the one-machine layout (frame, gantry, dock, laser keep-out).

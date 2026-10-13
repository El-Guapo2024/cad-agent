# Step 6 plan: machine scale (proposed 2026-10-10, approved as written, built 2026-10-10 to 2026-10-12)

**Done.** "As built", at the end, lists where the build differs from this plan. The plan below is kept as it was
approved.

From main 4e23a54. Every new command keeps `--json`, the 0/1/2/3/4 exit codes and the activity log. Anything a
rule cannot measure is UNCHECKED. `cad verify` never trusts a cache. Free and open-source tools only.

**What the code forces.**
- Three files are bottlenecks every piece would edit: `spec.KINDS`, `cli.build_parser` and `rules.py`.
- `verify.engine_hash` hashes only `cad_agent/**/*.py`, and `verify.DESIGN` only the project's own files. A TOML
  table of rule data, or a sibling project, would not be hashed.
- `export.py` claims DXF and writes none.
- The extrusion blanks and the eval givens are solid boxes, so a stiffness rule would read them and pass falsely.
- FreeCAD's material cards hold Density, YoungsModulus, PoissonRatio, YieldStrength and thermal values, but no
  service temperature.

So a contract step goes first.

## Pieces

### P0: the contract
One agent, merged before anything else. Nothing a user sees changes except `cad tables materials`.
- **Registries.** Spec kinds register with `@spec_kind`, and the seven existing kinds move to
  `cad_agent/speckinds/` with their row order kept. Rules auto-import from `cad_agent/ruleset/`.
- **CLI.** `cmdbase.py` holds Result, the exit codes and the errors. Parser entries exist for every new command;
  their handlers are imported lazily from each piece's module and answer exit 3 "not built yet" until filled.
- **`materials.py`.** A Python literal, so engine_hash and the build-cache key cover it. It holds FreeCAD card names
  and values (Density, YoungsModulus, PoissonRatio, YieldStrength), each cited to the FreeCAD `.FCMat` files (LGPL),
  with a MaxServiceTemperature slot for C1. `geom.DENSITY` is derived from it.
- **`bodies.py`.** `BodyInfo` records kind (made, bought or stock), project, part, material, mass, maximum
  temperature, geometry and source. `state.load_machine()` returns an Assembly of parts, clearance, allow_contact,
  axes, poses, bodies and children. `load_assembly` stays as a wrapper.
- **Bought contract.**
  - `mass_g` with its source, `material`, `max_temp_c` with its source.
  - `geometry = exact|envelope`, default envelope: only `exact` may give stiffness.
  - `datum {move, turn}`.
  - A `sha256` checked by provenance (FAIL on mismatch).
  - `bought_solid(slug, name, **params)`.
- **Also:** `CAD_LIBRARY` passes through the warm worker; `tests/affected.py` gets COVERS entries; pyproject declares
  ezdxf (MIT) and lib3mf (BSD), plus extras `drawings=[matplotlib]` and `fasteners=[bd_warehouse]`.
- **Verified by:** all tests, checks.json and verify.json rows byte-identical on every sample design, and all 10 eval
  references at 100%.

### A: library (`cad lib ls|info|add|use|check|fetch`)
- **A project copies in what it uses.** `use` copies the STEP, or writes a bought module that calls a generator,
  into `bought/`, with a sidecar of `{library, sha256, source, vendor, pn, licence, datum, mass}`. Verify, the build
  cache, CI and eval scoring still read only the project tree.
- **Shipped in `cad_agent/library/`.** `catalog.toml` plus `gen/*.py`, for parts that may be redistributed: MGN12/15,
  2020/2040/4040 with real slot profiles (`exact`), NEMA 8/17 and a GT2 idler. These are promoted from the eval
  generators, which must still regenerate byte-identical. Also STEPs from FreeCAD-library (CC-BY 3.0, with
  attribution) and fasteners from bd_warehouse (Apache-2.0).
- **Vendor STEPs never go in the public repo.** They live in a user store, `~/.cad-agent/library` or `CAD_LIBRARY`
  (for example a private repo), stored by sha256 with each URL and hash pinned in the catalog. `fetch` works only
  where the licence allows it; otherwise download by hand and run `add --source`.

### B: sub-assemblies, poses and axes
- **A sub-assembly is a sibling project, placed by declaration:**
  `SUBASSEMBLIES={"gantry":{"project":"gantry","at":[..],"turn":[..]}}`.
  This is FreeCAD's link to another document. Each child stays a full project with its own check and verify.
- **Flattening.** Body names become `gantry/x_carriage`. Child CLEARANCE, ALLOW_CONTACT and AXES are lifted with the
  prefix, and axes turn with the instance.
- **Poses.** `POSES={"park":{...}}`.
- **Failures.** A cycle, depth over 8, or "/" in a part name is a FAIL row.
- **The parent's verify rebuilds the whole tree fresh** and never reads a child's verify.json. `source_hash` and
  `git_info` cover every child.
- **Spec.** `pose="park"` on clearance, keepout and position. New `[[axis]]` and `[bodies] count/names` kinds close
  two step-7 gaps.

### C1: mass and heat
- **`[[mass]]`** gains `bodies=[..]` and `moving="<axis>"`. A bought part needs a declared `mass_g` with its source,
  otherwise UNCHECKED.
- **New `ruleset/com.py`:** the centre of mass must fall inside the stance footprint.
- **`[[heat]]`** takes `source` (or `at`), `temp_c`, `radius_mm` and `margin_c`. Every body within the radius needs
  MaxServiceTemperature of at least temp_c plus the margin, using the exact B-rep distance. Rows say it is "a zone,
  not a thermal model".
- **C1 fills MaxServiceTemperature in materials.py,** each with a value, its basis (HDT per ISO 75-2 B, UL 746B RTI,
  or Tg) and the datasheet URL.

### C2: deflection
- **`[[deflection]]`** takes `body`, `support=simple|fixed|cantilever`, `span_mm`, a load
  (`load_n|load_g|load_moving`), `at`, `self_weight` and `max_um`.
- **Method:** Euler-Bernoulli superposition, from Roark's Table 8.1. I comes from OCCT section faces (the minimum over
  21 stations), E from materials.py.
- **UNCHECKED** for envelope bodies, a missing E or source, or span/depth under 10.
- **FEA** (CalculiX + Gmsh) comes later as an optional cross-check, never the only judge.

### D: shop outputs
Commands: `cad export --format step|stl|3mf|dxf`, `cad bom` and `cad shop <slug> [--draft|--check]`.
- **`cad shop` writes `out/shop/`:** DXF for laser parts, 3MF and STL for printed ones, STEP for all, drawings,
  `bom.csv` and `bom.json`, and `manifest.json` with hashes, commit and verdict.
- **How it is fenced.** It rebuilds without the cache and exits 2 unless `cad done` holds; `--draft` stamps
  NOT VERIFIED on everything.
- **Part rule:** a laser part must be a through-cut, and its DXF must read back to the mid-plane section. A printed
  part's 3MF must be watertight with volume within 0.5%.
- **DXF** follows FreeCAD's ImpExpDxf settings. DXF, 3MF and SVG bytes are pinned so they repeat.
- **BOM** ports FreeCAD's `Assembly/CommandCreateBom.py` and adds kind, material, process, vendor, PN, source, mass
  and shop file. An opt-in `[shop]` spec kind gates it.

### E: drawings (a TechDraw port)
`cad drawing <slug> <part>`
- **Views** use HLR projection, the way TechDraw's `GeometryObject::projectShape` does: visible lines solid, hidden
  ones dashed.
- **Layout:** first or third angle, with ISO 128 line types and an ISO 5457 frame.
- **Dimensions** come from the B-rep: extents, hole positions and hole callouts, plus an ISO 2768-m note.
- **Formats:** the DXF is the master; SVG and PDF are drawn from it.
- **Title block** carries the commit and NOT VERIFIED unless `cad done` holds.
- **Scope:** machined plates only, no sections and no GD&T.

### Integration (last)
- Update the docs and the skill.
- Add two eval tasks (a 250 C dock material, a beam for 50 um).
- `mini_machine`: a fixture that uses every piece and is verified by CI.

## Schedule
- **P0 merges first,** alone. It owns `cli.py`, `cmdbase.py`, `registry.py`, `spec.py`, `rules.py`, `geom.py`,
  `bodies.py`, `warm.py`, `pyproject.toml`, `tests/affected.py` and `conftest.py`.
- **Then A, B, C1, C2, D and E** run on disjoint files, each adding only its own tests. Rough sizes: A 2 days,
  B 3 to 4 (the riskiest), C1 1 to 2, C2 2, D 3, E 4 to 5.
- **Merge order:** C1, C2, A, D, B, E, integration.
- **Every merge must** pass the affected tests, keep the eval references at 100%, and leave fixture verdicts
  unchanged unless the change is intended.

## Risks, cuts, step 8
- **Risks:**
  - Verify time on about 80 bodies (measure mini_machine early).
  - "/" names in the UI.
  - Sourcing material values (missing means UNCHECKED, by design).
  - Repeatable bytes.
  - Slow OCCT HLR.
- **Cut in this order if time is short:** PDF, automatic hole dimensions, drawings, `lib fetch` and bd_warehouse,
  3MF, the centre-of-mass rule, the moving-load options on deflection.
- **Never cut:** P0, hashing every child project, or the UNCHECKED guards.
- **Left for step 8:**
  - The machine itself.
  - Combined multi-axis sweeps.
  - Sheet-metal unfolding and FEA.
  - UI tree nesting.
  - Vendor APIs.
  - Multi-project eval tasks.
  - The remaining step-7 grader gaps.

## As built (2026-10-12)

The pieces merged through the `batch` branch in the planned order (P0, then C1, C2, A, D, B, E), and the integration
came last. Every command and spec kind named above exists. Nothing on the cut list was cut, and nothing was added
outside the plan except what is listed here. Only the harness was built: no machine was designed.

**Where the build differs from the plan**
- **Contract.** The `drawings` extra (matplotlib) was never used, since the SVG and PDF are written by hand, and it went
  in the integration. Every material has a service temperature, but FreeCAD's cards have none, so the numbers are ours,
  each with a basis (HDT, Tg or a stated limit). PC and ASA are not in the table, because adding them would move pinned
  densities; a bought part declares its own rating.
- **Library (A).** 22 entries, with four FreeCAD-library STEPs and three bd_warehouse fasteners beyond the plan. The GT2
  idler and those STEPs are marked unverified (no maker drawing), so a design that uses one stays UNCHECKED until
  `cad bought verify`. The two motors declare the makers' ambient limits (40 C and 50 C) as their rating. "Exact"
  extrusions are within 1 % of the maker's STEP in section area and second moment. `engine_hash` covers the generators
  and not `catalog.toml`, so a generator edit moves the verdicts of every project that uses it. A live `lib fetch` was
  never run, because the tests fake the download.
- **Sub-assemblies (B).** Added: `"gantry/*"` in an axis's `moves`; failure rows `subassembly/<kind>` listed all at once;
  child rows named `<project>:<check>/<rule>`. A parent is not done until each child has a spec.toml and approved
  renders, and project names in `SUBASSEMBLIES` must be string literals, because verify reads the tree without running
  it. A parent's check costs about twice a flat project's (80 bodies: 11 to 13 s against 6 to 7 s).
- **Mass and heat (C1).** `[[heat]]` gained `clear`. `com` judges the support polygon (the convex hull of the contact
  patches), not the stance patch's box, at home and at both ends of each axis; it is N/A until a bought part declares a
  mass, because every design before step 6 holds a body of unknown mass. `[[mass]]` is FAIL, not UNCHECKED, when the
  bodies of known mass already exceed `max_g`. Only steel, stainless and polyimide are rated for 250 C.
- **Deflection (C2).** More UNCHECKED paths than planned: fixed ends need span/depth 20 (simple and cantilever 10), a
  solid box of a 2020, 2040 or 4040's size is UNCHECKED (that is what `extrusion_blank` and the eval givens are;
  `solid = true` says it is a bar), a section that varies is judged by its weakest and stiffest section, and a body
  with more than 120 stations is not a beam. Torsion is not modelled. The sections are the middle of 21 cells plus
  the middle of every cut across the beam. The finite-element cross-check was not built.
- **Shop (D).** The DXF, 3MF, STL and BOM files are the same bytes on OCCT 7.9 and 8.0; a STEP is too but for the header
  line that names the processor, so `cad shop --check` compares it without that line. The 3MF is written by hand and lib3mf
  reads it back (it has no Linux aarch64 wheel). The STL is the same mesh, not OCCT's writer. The shop part rules run
  only with a `[shop]` section. `files = ["drawings/..."]` in `[shop]` is UNCHECKED, because the BOM cannot say which
  plates will be drawn. `cad export --format dxf` writes any part's mid-plane section without judging it.
- **Drawings (E).** Laser-cut plates are drawn as well as machined ones. The frame has no ISO 5457 zone grid, and a size
  ISO 2768-m has no tolerance for (under 0.5 mm, over 4000 mm) is drawn with a note. Anything that is not a prism along
  its thinnest axis with through features is refused with the reason (exit 2), a printed part or one with no PROCESS
  with exit 3. Of the eval references two plates are drawn (`laser_panel/panel`, `nema17_mount/bracket`). Hidden-line
  removal cost 75 to 180 ms a plate, so it was not the risk the plan feared.
- **Integration.** The skill, README, DETAILS, PLAN_V2 and HANDOFF; nylon's rating from a PA6 sheet (its card was PA6
  but its numbers cited a PA66 sheet); two eval tasks, `dock_material` (a `[[heat]]` task at 250 C) and
  `beam_deflection` (a `[[deflection]]` task, 50 um); and the `mini_machine` fixture, which uses every piece and which
  CI verifies like every folder of `tests/fixtures`.

**Risks, as they turned out.** Verify time on 80 bodies was measured and is above (not a blocker). "/" names in the
UI are still open: the workbench shows a flat name and does not colour the pair rows of a child's bodies. Sourcing
material values worked as designed: a missing value is UNCHECKED, and there are none missing for the 12 materials.
Repeatable bytes were solved (D). Slow hidden-line removal was not a problem.

**Left before the release** (ui/HANDOFF.md, "Next"): a UI check, three UI gaps (the "/" row colouring, 3mf and dxf in the
workbench's export, no buttons for drawing, bom, shop or lib), a fresh-install check of the plugin (it gains the core
dependencies ezdxf and lib3mf), and the version bump. **Left for later**, as the plan said: the machine itself (step 8),
combined multi-axis sweeps, sheet-metal unfolding, FEA, UI tree nesting, vendor APIs, multi-project eval tasks, and the
step 7 grader gaps that remain (a hole count, a shaft fit, a clearance to a sub-feature).

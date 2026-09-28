# CAD-Agent v2: Closest Existing Equivalents (September 2026)

## LLM Agents + Code-CAD Projects

### Takeaway
Six mature open-source projects now combine LLM agents with Python code-CAD frameworks (build123d, CadQuery, OpenSCAD), with three offering CI-like verification loops. Build123d has become the dominant kernel for agent-driven CAD, with two dedicated tooling projects (cad-khana, build123d-mcp) and AgentCAD as the most-starred standalone harness.

### Cited Findings

#### Build123d-Based Tools
- **build123d-mcp** (MCP server for Claude, Cursor, VS Code, Cline, Codex CLI) improved CADGenBench scores from 0.360 → 0.457 and validity from 88% → 100% in June 2026 — [GitHub](https://github.com/pzfreo/build123d-mcp); **96 stars**, Apache 2.0 license; actively maintained with 560+ commits. Capabilities: execute code, render PNG/SVG/DXF, measure geometry (volume, area, topology, CoM), detect holes/bosses/countersinks, fit/alignment comparison, printability validation, export STEP/STL/DXF/SVG. No fresh-rebuild verification or visual regression. — [PyPI](https://pypi.org/project/build123d-mcp/)
- **cad-khana** (Claude Code skill + diagnostics-first Build123d wrapper) provides structured checks via `mechanism.json`: interferences, clearances, assertion results, motion validation across sampled joint poses, FDM wall-thickness & overhang inspection, orthographic/isometric engineering drawing PNG export for multimodal agents — [GitHub](https://github.com/cyberchitta/cad-khana); **16 stars**, Apache 2.0, early API. CLI commands: `khana check`, `khana draw`, `khana export` (STL/STEP), `khana view`, `khana diff`. Uses JSON diagnostics rather than rebuild verification.
- **AgentCAD** (standalone harness, defaults to build123d, CadQuery optional) is the highest-starred CAD+LLM entry point at **140 stars**, Apache 2.0, 197 commits. Offers A/B comparison viewer, STL/GLB/OBJ export, "compare measured cylindrical features against explicit checklist," topology analysis with validity extraction. No independent verifier or visual regression. — [GitHub](https://github.com/jdilla1277/agentcad); last commit date not visible in fetch, 32 open issues, 16 forks active.

#### OpenSCAD-Based Tools
- **openscad-agent** (Claude Code-powered, generates versioned .scad files) includes three CLI skills: `/openscad` for design iteration, `/preview-scad` PNG rendering, `/export-stl` with non-manifold geometry validation. **129 stars**, MIT license, 18 forks — [GitHub](https://github.com/iancanderson/openscad-agent). Geometry validation on export checks printability but does not offer DFM, interference, or fresh-rebuild gates.
- **ScadLM** ("open source agentic AI CAD generation built on OpenSCAD") — [GitHub](https://github.com/KrishKrosh/ScadLM); no star count, license, or feature details retrieved; presumed early-stage.
- **OpenSCAD Studio** (chat UX, streams Claude/GPT/local responses, MCP support) — no GitHub repository with code; web app focus, not CLI.

#### Multi-Agent & Conversational Systems
- **Multi-Agent CAD (MAC)** (decoupled multi-agent framework for text-to-CAD via constrained test-time compute, updated Sept 16, 2026) — [GitHub](https://github.com/Pan-Chera/Multi-Agent-CAD); no stars or commit-date metadata retrieved.
- **Zookeeper** (Zoo.dev conversational agent, integrated with KCL language engine, Jan 2026 release v1.1). Differentiator: tools for connecting to Zoo CAD engine, writing/executing/debugging KCL, analyzing 3D models via visual snapshots and computational tools — [Docs](https://docs.zoo.dev/research/zookeeper). Not open-source; web-based, not CLI. KCL is textual and version-controlable; agent loops are proprietary.
- **Text-to-CAD library** (earthtojake fork, "agent skills for CAD, robotics and hardware design") — [GitHub](https://github.com/earthtojake/text-to-cad); creates/edits CAD from plain-language or image requests, STEP as main output, STL/3MF/GLB export. No star count or verification details; appears to be skill collection rather than verifier-first harness.
- **Anvilate** ("open-source, local-first design agent for mechanical engineers," plain-English input → physics-validated parametric STEP/DXF). Not verified as having public GitHub repo; no details on checks or CLI structure.

### Inferences
- **Agent-first projects are mature enough for production**: cad-khana and build123d-mcp already ship diagnostic JSON/validation UIs for agents to understand failures. AgentCAD's A/B viewer is a usable replacement for "visual regression" (human spot-check rather than automated diff).
- **No project has fresh-rebuild verifier or spec-driven acceptance gates** as standalone CLI tools. Zookeeper's computational tools and cad-khana's motion validation are closest, but neither published as verifiable harness layer separate from the agent loop.
- **OpenSCAD has fewer stars than build123d/CadQuery tooling**, despite ScadLM's promise, suggesting build123d is winning momentum for LLM+CAD work.
- **KCL (Zoo.dev) is proprietary**: text-based parametric CAD with agentic tools exist, but the harness and eval set are not open-source or available as CLI.

### Gaps
- **No data on whether any project has passed CADGenBench / RealCADBench / BenchCAD independently**. The build123d-mcp improvement claim (0.360 → 0.457) is from June 2026, but which model/prompt, which benchmark version, and whether cad-khana or AgentCAD achieve similar gains is not documented.
- **Last commit dates for cad-khana and AgentCAD not retrieved**; cannot confirm active maintenance status beyond star count.
- **No information on whether any project integrates buyer-supplied STEP parts with provenance tracking**. All projects assume geometry-generation-only workflows.
- **Visual regression tooling for CAD renders not found in any of the six projects**. VRT is mature for UI (Percy, Applitools, Chromatic, Argos, Playwright) but CAD-specific visual diff tools were not mentioned in any project documentation.

---

## Parts Libraries and Vendor STEP Access

### Takeaway
Build123d and CadQuery ecosystems have parametric parts libraries (bd_warehouse, cq_warehouse) covering fasteners, gears, and sprockets, but neither provides linear rails (MGN12/MGN15), stepper motors (NEMA8/NEMA17), or extrusion profiles (2020/2040) parametrically. Vendor STEP file APIs (McMaster-Carr, Misumi, HIWIN, TraceParts) do not have documented headless/programmatic access; all downloads are manual web UI.

### Cited Findings

#### bd_warehouse (build123d parametric library)
- Categories: bearings, bushings, fasteners, flanges, gears (spur/helical/rack/worm), OpenBuilds parts, O-rings, pipes, retaining rings, shaft keys, sprockets, threads (ISO/Whitworth/BSPP/Acme/metric-trapezoidal/plastic-bottle). — [ReadTheDocs](https://bd-warehouse.readthedocs.io/); [GitHub](https://github.com/gumyr/bd_warehouse)
- **No MGN linear rails, NEMA motors, or extrusion profiles found** in published docs.
- Actively maintained; comprehensive documentation; on-demand parametric generation for STEP/STL export.

#### cq_warehouse (CadQuery parametric library)
- Categories: sprockets, chains, threads, holes, fasteners, fastener BOM, drafting (MBD support). Extensions sub-package adds tuple operations to Vertex. — [ReadTheDocs](https://cq-warehouse.readthedocs.io/); [GitHub](https://github.com/gumyr/cq_warehouse)
- **No MGN linear rails, NEMA motors, or extrusion profiles**.
- v0.8.0 released; related ecosystem includes cq-kit, cqMore, cq_gears (spur/helical/planetary).

#### FreeCAD Fasteners Workbench
- Provides parametric fasteners (nuts, screws, washers) with customizable properties; v0.5.67 updated 2026-09-10 — [GitHub](https://github.com/shaise/FreeCAD_FastenersWB); [FreeCAD Addons](https://www.freecad.org/addons.php?lang=en)
- Added BSP Thread Support (Taps & Dies) as of Feb 5, 2026.
- **Does not include motion-part families** (rails, motors, pulleys).
- FreeCAD community library exists (FCStd, STEP, STL, BREP formats) but is several gigabytes, manually curated, and lacks programmatic part generation.

#### Vendor STEP File Access
- **McMaster-Carr**: Free 3D models for most parts; manual download via web dropdown; no documented REST API or headless mechanism. — [Forum discussions](https://forums.autodesk.com/t5/fusion-design-validate-document/downloading-from-mcmaster-carr/td-p/6755969)
- **Misumi**: No API documentation found; web-based catalog access only.
- **TraceParts**: Offers 3D models for download; no documented API; web UI only. — [Website](https://www.traceparts.com/en)
- **3DContentCentral** (Dassault systems): Web interface; no public API.
- **GrabCAD**: Community uploads; no vendor APIs; manual model sourcing.
- **HIWIN**: No headless API located; traditional sales/distributor channels for CAD access.

### Inferences
- **Parts libraries are generation-only**: bd_warehouse and cq_warehouse excel at on-demand parametric creation, not cataloging pre-made vendor parts. This is by design (version control, repeatability), but means agents cannot reference a vendor STEP file as immutable provenance.
- **Mechanical motion subsystems (linear rails, stepper motors, timing pulleys) are not yet commodified as parametric parts** in open CAD libraries. Agents would need to either generate approximate geometry or rely on purchased STEP files.
- **Vendor STEP download automation would require web scraping or proprietary data agreements**, not open APIs. For agents, this means either: (a) hardcoded URLs per vendor/part, (b) human-maintained STEP cache, or (c) parametric approximations.

### Gaps
- **No comprehensive parametric model for common motion systems** (linear rail assemblies, motor mounts, timing-pulley trains) in either bd_warehouse or cq_warehouse.
- **License status of vendor STEP files** when downloaded for programmatic use is unclear; terms of service may prohibit headless/batch access or commercial redistribution.
- **No data on whether bd_warehouse MGN-rail or motor parts exist as pull requests or experimental branches** (search included only released documentation).
- **Cannot verify whether FreeCAD Fasteners Workbench includes motor-mount or rail-guide parametric families** beyond fasteners.

---

## Deterministic Verification, DFM, and Acceptance Gates

### Takeaway
Two projects (cad-khana, build123d-mcp) include deterministic checks at the geometry level (wall thickness, clearances, hole patterns), but neither implements a verifier-first harness with source hashing, spec.toml acceptance tests, or fresh-process rebuild validation. Visual regression testing is mature for UI but absent from CAD tooling. Kinematic/motion-sweep verification exists in cad-khana but is not standardized across projects.

### Cited Findings

#### Existing Verification in CAD Agents
- **cad-khana** checks: interferences, clearances (named assertions), motion validation (across sampled joint poses), FDM wall-thickness & overhang inspection, drawing export for human inspection. — [GitHub](https://github.com/cyberchitta/cad-khana); CLI: `khana check`, `khana diff`.
- **build123d-mcp** checks: `validate()` function for part integrity, shape comparison via `compare()`, hole/outer-envelope export gates, printability assessment. Improved CADGenBench scores (June 2026).
- **openscad-agent** checks: non-manifold geometry validation on STL export; printability inspection (implicit in export).
- **AgentCAD**: "compare measured cylindrical features against explicit checklist," topology validity extraction. No mention of motion validation or DFM gates beyond topology.

#### Deterministic Verification Architecture (Academic / Research)
- **Agentic Verification of Software Systems** (arxiv 2511.17330): four-layer check loop (machine-checked proofs → weaker checks → known-answer tests → code review). Not CAD-specific; mentions GNATprove, CVC5, Z3 for formal proof but not geometry verification. — [arXiv](https://arxiv.org/pdf/2511.17330)
- **Automated Testing and Repair for Verified Compilers** (arxiv 2607.28928): verifier-first loop treats agent as unreliable producer; not applied to CAD.
- **Self-Improving CAD Generation Agents with Finite Element Analysis as Feedback** (arxiv 2605.17448): FEA as a feedback loop, but implementation details and public code not in search results.

#### Visual Regression Tools (Mature for UI, Absent for CAD)
- UI VRT tools (Percy, Applitools, Chromatic, Argos, Playwright, BackstopJS): per-pixel or AI-driven diffing against baseline. Mature field with 2026 benchmarks. — [BrowserStack](https://www.browserstack.com/percy/visual-regression-testing); [SauceLabs](https://saucelabs.com/resources/blog/comparing-the-20-best-visual-testing-tools-of-2026)
- **No equivalent for CAD 3D render regression found** across build123d-mcp, cad-khana, AgentCAD, or openscad-agent. Engineering drawings (PNG HLR) in cad-khana are human-reviewed, not automatically diffed.

#### Kinematic and Motion Validation
- **cad-khana** motion validation: "checks geometric constraints across sampled poses of declared joints." Mechanism.json output. — [GitHub](https://github.com/cyberchitta/cad-khana)
- **No other project mentions motion sweeps or kinematic constraints** in available documentation.

### Inferences
- **Verifier-first architecture is understood but not implemented in CAD agents yet**: academic papers describe the pattern; no CAD project has published a standalone verifier that rebuilds from source and runs acceptance tests independently.
- **Specification-driven acceptance tests (spec.toml style) do not exist** in any CAD agent harness. AgentCAD's "explicit checklist" is likely hardcoded per assembly, not declarative.
- **Visual regression for CAD renders is a gap**: CAD geometry changes are harder to automatically diff than UI pixels (occlusion, lighting, camera sensitivity), but no project has attempted even a basic baseline-comparison tool.
- **Motion validation is a cad-khana differentiator** but requires joint declaration in code, limiting adoption to assemblies that explicitly model degrees of freedom.

### Gaps
- **No data on whether cad-khana motion validation can be extended to arbitrary geometric constraints** (e.g., ray-cast wall thickness, tool keep-out envelopes, axis-aligned travel bounds).
- **"Fresh-process rebuild" verification not mentioned in any project.** It's unclear whether build123d code can be rebuilt deterministically and whether geometry hashing is stable (OCCT kernel versioning?).
- **Spec-driven acceptance gates (YAML or TOML test declarations)** are absent from all projects; cannot verify feasibility without implementation attempt.
- **No project has published CAD-specific visual regression benchmarks or datasets** (e.g., expected vs. actual render diffs, evaluation metrics).

---

## Evaluation Benchmarks and Datasets

### Takeaway
Four major CAD generation benchmarks exist as of September 2026 (CADGenBench, RealCADBench, BenchCAD, Parametric CAD Bench), with RealCADBench being the largest (12,632 tasks across 19 factory-automation categories). Build123d-mcp achieved notable improvements on an unspecified model in June 2026 (0.360 → 0.457 score, 88% → 100% validity), but no other project has published benchmark-specific results.

### Cited Findings

#### CAD Generation Benchmarks (2026)
- **CADGenBench**: Focuses on drawing-to-CAD translation; targets executable or editable outputs. — [Hodgesj substack](https://hodgesj.substack.com/p/benchmarks-for-ai-models-and-agents)
- **RealCADBench**: 12,632 tasks from 19 factory-automation categories, spanning text descriptions, 2D engineering drawings, real product pictures, and rendered images for Part and Assembly modeling. Kernel-level rebuildability tests without topological errors. — [arXiv 2609.03773](https://arxiv.org/pdf/2609.03773)
- **BenchCAD**: Domain-expert-verified benchmark of 17,900 executable CadQuery programs across 106 industrial part families. — [arXiv 2605.10865](https://arxiv.org/pdf/2605.10865)
- **Parametric CAD Bench**: V3 contains 100 complex FreeCAD tasks: 30 creation from text, 30 create-and-edit from text, 40 creation from engineering drawings. Evaluates authoring editable FreeCAD models from natural language. — [CADBench.ai](https://cadbench.ai/)
- **CADBench**: Multimodal benchmark for AI-assisted CAD program generation. — [arXiv 2605.10873](https://arxiv.org/pdf/2605.10873)
- **CADEngBench**: "It Looks Like CAD, but Does It Work?" — Evaluates parametric design, assembly reasoning, and physics simulation. — [arXiv 2608.09296](https://arxiv.org/html/2608.09296v1)

#### Published Performance Data
- **build123d-mcp** (June 2026): Improved one model from score 0.360 → 0.457 and CAD validity from 88% → 100% on an unspecified benchmark (presumed CADGenBench). No other model results or benchmark sources published. — [PyPI](https://pypi.org/project/build123d-mcp/)
- **AgentCAD, cad-khana, openscad-agent**: No public benchmark results retrieved.

### Inferences
- **RealCADBench is the most comprehensive** (12,632 tasks, 19 categories, industrial grounding), while BenchCAD has the largest code corpus (17,900 CadQuery programs).
- **No project has publicly benchmarked against multiple datasets**, making cross-project comparison impossible from available sources.
- **Assembly reasoning and physics simulation (CADEngBench) are under-represented** in agent harnesses; most tools focus on individual part generation.

### Gaps
- **Unknown which model and benchmark cad-khana and AgentCAD target**, if any. No published results beyond build123d-mcp's June 2026 claim.
- **Evaluation of verifier-first or acceptance-gate behavior** is not part of any benchmark; they measure generation speed/correctness, not safety or determinism.
- **No dataset for motion-validated assemblies or DFM-gated designs** (e.g., wall-thickness compliance, clearance validation) exists in published benchmarks.

---

## Features Absent from All Existing Projects

### By Category

#### Verifier Architecture
- [ ] Fresh-process rebuild from source with deterministic geometry hashing
- [ ] Spec-driven acceptance tests (YAML/TOML declarations, CI-like test runners)
- [ ] Source-file provenance hashing (Git integration, immutable audit trail)
- [ ] Independent verifier (separate from agent loop, can be run in isolation)

#### CAD Checks & Gates
- [ ] Ray-cast wall-thickness validation (DFM per manufacturing process)
- [ ] Tool/laser keep-out envelope enforcement
- [ ] Axis-aligned travel bounds for kinematic joints (swept volumes)
- [ ] Interference detection with quantified gap/clearance reporting (cad-khana has assertion only)
- [ ] Visual regression testing for 3D renders (baseline comparison, diff markup)

#### Vendor Parts & Provenance
- [ ] Headless STEP file fetching from vendor APIs (McMaster, Misumi, HIWIN, TraceParts)
- [ ] Immutable STEP library with MD5/SHA2 hashing per part
- [ ] Buyable parts integrated with BOM and cost rollup
- [ ] Parametric models for common motion subsystems (linear rails, stepper motors, timing pulleys)

#### Interface & Ecosystem
- [ ] CLI-first harness designed for agent iteration (not GUI, not MCP)
- [ ] Evaluation dataset with golden designs and acceptance criteria
- [ ] Plugin system for custom DFM rules per manufacturer
- [ ] Deterministic performance benchmarking (e.g., iterations-to-valid, cost-per-design)

#### KCL Ecosystem
- [ ] Open-source tooling for text-to-KCL agent loops (Zookeeper is proprietary Zoo.dev SaaS)
- [ ] Public eval set for KCL-based CAD generation

### Notes
- **CLI-first design**: Only openscad-agent and cad-khana include CLI workflows; AgentCAD is primarily library; build123d-mcp is MCP-server; Zookeeper is web-app-only.
- **Eval set**: No project publishes a labeled dataset of "correct" designs with acceptance criteria for agent evaluation.
- **Parametric motion parts**: Linear rails (MGN12/15), NEMA motors (8/17), extrusion profiles (2020/2040), GT2 pulleys not in bd_warehouse, cq_warehouse, or FreeCAD Fasteners.
- **Vendor STEP APIs**: All vendor sites require manual download; no public, headless-safe APIs found.

---

## Recommendations for cad-agent v2 Design

### Adopt & Extend
1. Use **build123d** as the primary geometry kernel (clear winner; 140+ projects, 4+ agent harnesses).
2. Integrate **build123d-mcp** as the agent interface (proven CADGenBench gains, 96 stars, Apache 2.0).
3. Reference **cad-khana** diagnostics JSON pattern for structured error reporting (motion validation example).
4. Use **bd_warehouse** for commodified parts; populate custom parametric library for motion subsystems.

### Build New (Not in Landscape)
1. **Verifier harness**: Fresh-process rebuild with geometry hashing; source-file audit trail; spec.toml acceptance tests.
2. **Visual regression framework**: Baseline PNG/SVG render comparison with diff markup (adapt UI VRT tooling for CAD).
3. **Vendor STEP cache**: Manual curation (CSV: MPN, vendor URL, SHA2, provenance); headless download wrapper (scraping or data agreements).
4. **Parametric motion library**: Linear rails, stepper motors, timing pulleys in build123d; reusable assembly templates.
5. **DFM rule engine**: Wall-thickness, tool keep-out, axis sweeps; pluggable per process (FDM, CNC, sheet metal).
6. **CLI harness**: Agent loop with spec files, acceptance gates, and render regression as first-class features.

### Evaluation
1. **Target benchmarks**: RealCADBench (12.6k tasks, industrial scale), BenchCAD (17.9k CadQuery programs for comparison).
2. **Extend eval set**: Add motion validation, DFM compliance, and acceptance-gate strictness as metrics beyond generation correctness.
3. **Publish results**: Compare cad-agent v2 against build123d-mcp baseline on same benchmark & model.

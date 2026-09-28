# CAD Agent Landscape 2026: Quick Comparison Table

| Project | Kernel | Interface | Stars | Last Update | License | Checks Offered | Verifier? | Visual Regression? | Eval Set? |
|---------|--------|-----------|-------|-------------|---------|---|---|---|---|
| **build123d-mcp** | build123d | MCP Server | 96 | Active (June 2026) | Apache 2.0 | Printability, geometry measurement, hole detection, fit comparison | No | No | No (external: CADGenBench claimed +97 score) |
| **cad-khana** | build123d | CLI (Claude Code skill) | 16 | Active | Apache 2.0 | Interferences, clearances, motion validation, wall thickness, DFM overhang, drawings | No | No | No |
| **AgentCAD** | build123d (default), CadQuery (optional) | Library + A/B viewer | 140 | Active (197 commits) | Apache 2.0 | Topology validity, cylindrical feature checklist | No | No (A/B viewer is manual) | No |
| **openscad-agent** | OpenSCAD | CLI (Claude Code skills) | 129 | Active | MIT | Non-manifold geometry, printability | No | No | No |
| **Multi-Agent CAD (MAC)** | build123d + others | Framework | ? | Sept 16, 2026 | ? | ? | No | No | No |
| **Zookeeper** | KCL (Zoo.dev) | Web app + chat | Proprietary | Jan 2026 | Proprietary | Visual snapshots, computational analysis | No | No | No (Zoo training data) |
| **ScadLM** | OpenSCAD | ? | ? | ? | ? | ? | No | No | No |
| **Anvilate** | ? | Local-first (claims parametric STEP output) | Unknown/proprietary | ? | Unknown | Physics validation (claimed) | No | No | No |

## Parts Libraries Comparison

| Library | Framework | Bearings | Fasteners | Gears | Linear Rails | NEMA Motors | Extrusion | License |
|---------|-----------|----------|-----------|-------|---|---|---|---|
| **bd_warehouse** | build123d | ✓ | ✓ | ✓ (spur/helical/rack/worm) | ✗ | ✗ | ✗ (OpenBuilds parts only) | ? |
| **cq_warehouse** | CadQuery | ? | ✓ | ✓ | ✗ | ✗ | ✗ | ? |
| **FreeCAD Fasteners WB** | FreeCAD | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | ? |
| **FreeCAD Part Library** | FreeCAD | Various | Various | Various | ✗ (manual curation) | ✗ (manual curation) | ✗ | Various |

## Vendor STEP File Access

| Vendor | API? | Headless? | Format | Notes |
|--------|------|-----------|--------|-------|
| **McMaster-Carr** | No | No | STEP | Manual web dropdown; feature requests exist but unfulfilled |
| **Misumi** | No | No | STEP | Web catalog only |
| **TraceParts** | No | No | STEP | Web UI; no public API |
| **3DContentCentral** | No | No | STEP | Dassault-hosted; web interface |
| **GrabCAD** | No | No | STEP | Community uploads; no vendor APIs |
| **HIWIN** (linear rails) | No | No | STEP | Traditional sales channels only |

---

## Benchmark Performance (Published)

| Benchmark | Size | Best Known Result | Project | Notes |
|-----------|------|---|---|---|
| **CADGenBench** | ? | 0.457 (validity: 100%) | build123d-mcp (June 2026) | Improvement from baseline 0.360; model/version unspecified |
| **RealCADBench** | 12,632 tasks (19 categories) | Not published | — | Industrial assembly & part modeling; no agent results public |
| **BenchCAD** | 17,900 CadQuery programs (106 families) | Not published | — | Largest code corpus; no agent results public |
| **Parametric CAD Bench v3** | 100 FreeCAD tasks | Not published | — | Create/create-edit/drawing-based; no agent results public |

---

## Features Nobody Has (Gaps Matrix)

| Feature | cad-khana | build123d-mcp | AgentCAD | openscad-agent | Zookeeper | Any Project? |
|---------|---|---|---|---|---|---|
| **Fresh-rebuild verifier** | ✗ | ✗ | ✗ | ✗ | ✗ | **NO** |
| **Spec.toml acceptance tests** | ✗ | ✗ | ✗ | ✗ | ✗ | **NO** |
| **Visual regression (renders)** | ✗ | ✗ | ✗ | ✗ | ✗ | **NO** |
| **DFM wall-thickness (ray-cast)** | ✗ (overhang only) | ✗ | ✗ | ✗ | ✗ | **NO** |
| **Motion sweep validation** | ✓ | ✗ | ✗ | ✗ | ? | 1 of 6 |
| **Tool keep-out envelope** | ✗ | ✗ | ✗ | ✗ | ✗ | **NO** |
| **Vendor STEP headless fetch** | ✗ | ✗ | ✗ | ✗ | ✗ | **NO** |
| **Parametric motion library** (rails/motors/pulleys) | ✗ | ✗ | ✗ | ✗ | ✗ | **NO** |
| **CLI-first design** | ✓ | ✗ (MCP) | ✗ (library) | ✓ | ✗ (web) | 2 of 6 |
| **Published eval set** | ✗ | ✗ | ✗ | ✗ | ✗ | **NO** |

---

## Recommendation: cad-agent v2 Should Target

### Core Stack
- **Kernel**: build123d (4+ mature agent integrations, clear winner)
- **Agent interface**: build123d-mcp (proven CADGenBench boost) + CLI wrapper for spec files / acceptance gates
- **Parts**: bd_warehouse (existing) + custom parametric motion library (new)

### Differentiators (Nobody Has These)
1. **Verifier harness** with fresh-process rebuild, source hashing, spec-driven acceptance gates
2. **Visual regression** for render baselines (adapt UI VRT tools)
3. **DFM rule engine** (wall thickness, tool keep-out, axis sweeps)
4. **Vendor STEP cache** with provenance hashing
5. **Motion-specific validation** (extend cad-khana pattern to arbitrary constraints)
6. **Eval set** with labeled designs and acceptance criteria (benchmark cross-validation)

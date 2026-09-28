# Code-First CAD Kernels and Libraries (September 2026)

## Current Status of Major CAD Kernels

### Takeaway
The CAD kernel landscape as of September 2026 remains fragmented with no single dominant choice. build123d (Python B-rep on OCCT) and CadQuery (Python parametric on OCCT) dominate in Python, while Manifold (C++ triangle mesh) offers modern geometry guarantees, Rust alternatives (Truck) show promise, and parametric languages like OpenSCAD (now with fast Manifold backend) and Zoo KCL provide code-first paradigms with different trade-offs.

### Cited Findings

**Python B-rep Dominance:**
- build123d v0.13.0 released September 21, 2026, on Python (requires 3.11-3.14), built on OCP (OCCT bindings) — [PyPI](https://pypi.org/project/build123d/), [GitHub](https://github.com/gumyr/build123d) with 3.2k stars, Apache 2.0 license
- CadQuery 2.8.0 stable (June 2024), 5.9k stars on GitHub, Apache 2.0 license, parametric B-rep on OCCT via OCP bindings — [GitHub](https://github.com/CadQuery/cadquery)
- pythonOCC-core 8.0.1 is current latest, with 7.9.3 released August 10, 2026 on PyPI supporting Python 3.13-3.14 — [PyPI](https://pypi.org/project/pythonocc-core/), [GitHub](https://github.com/tpaviot/pythonocc-core)

**OpenSCAD Status:**
- Stable release remains 2021.01 (January 31, 2021) — [GitHub](https://github.com/openscad/openscad/releases)
- Manifold geometry backend (non-CGAL) is now default in nightly development builds (2025.09.02 observed in September 2026), delivering 100x performance improvements; accessible via Preferences menu — [OpenSCAD Downloads](https://openscad.org/downloads.html), [GNU Guix](https://packages.guix.gnu.org/packages/openscad/2025.09.02-0.5d6e37d/)
- CLI support available via headless mode in experimental builds

**FreeCAD:**
- FreeCAD 1.1.4 (September 28, 2026) is latest stable release, described as "last planned maintenance release in 1.1.x series"; includes weekly development builds through 2026-09-23 — [GitHub Releases](https://github.com/FreeCAD/FreeCAD/releases)
- freecad-cli npm package version 1.0.1 (March 28, 2026) provides CLI interface; separate effort from official FreeCAD with patches for headless, exit codes, clean stdout — [Libraries.io](https://libraries.io/npm/freecad-cli), [GitHub](https://github.com/monyuonyu/freecad-cli-patches)

**Modern Geometry Libraries:**
- Manifold v3.5.4 (September 25, 2025) is current stable; guarantees manifold triangle mesh output; supports ray-casting (v3.5.0 May 2025), ExecutionContext API for progress/cancellation, Python bindings — [GitHub](https://github.com/elalish/manifold), [ManifoldCAD.org](https://manifoldcad.org/)
- Exports 3MF and glTF; does NOT export STEP — [GitHub Wiki](https://github.com/elalish/manifold/wiki/Manifold-Library)

**Rust CAD Kernels:**
- Fornjot: early-stage b-rep CAD kernel in Rust; **project concluded, no longer in development** — [GitHub](https://github.com/hannobraun/fornjot)
- Truck: "B-rep CAD kernel in Rust" from ricosjp; 1.6k stars, Apache 2.0 license, v0.6.x series referenced in tutorials, 2,872 commits, with active forks (monstertruck, vcad) — [GitHub](https://github.com/ricosjp/truck)

**Parametric CAD Languages:**
- Zoo KCL: parametric programming language for CAD from KittyCAD; shipped Zookeeper AI agent integrated into Zoo Design Studio v1.1 (January 2026) for conversational prompt-to-model workflow; available as web app and desktop (Windows/macOS/Linux) — [Zoo Research](https://zoo.dev/research/introducing-kcl), [Zookeeper](https://zoo.dev/research/zookeeper)
- SolveSpace: v3.2 latest stable release with multi-constraint support, optional Qt frontend for Linux, merged experimental web version; solvespace-cli supports headless export with -DENABLE_GUI=OFF CMake flag — [GitHub](https://github.com/solvespace/solvespace), [Ubuntu Man Pages](https://manpages.ubuntu.com/manpages/jammy/man1/solvespace-cli.1.html)

**TypeScript/JavaScript CAD:**
- Replicad: TypeScript CAD library, 690 stars, MIT license, 492 commits, supports 3D design in JavaScript/TypeScript with browser parameter adjustment; latest build September 4, 2026 — [GitHub](https://github.com/sgenoud/replicad)
- JSCAD: modular JavaScript CAD; @jscad/modeling v2.13.0 (6 months before Sept 2026 = ~March 2026), @jscad/cli v2.3.8 (4 months before = ~May 2026) on npm; **does NOT support STEP import/export** — [npm @jscad](https://www.npmjs.com/search?q=@jscad), [GitHub Releases](https://github.com/jscad/jscad-desktop)

**Implicit/CSG/SDF CAD:**
- ImplicitCAD: Haskell-based programmatic CAD, CSG boolean operations, supports continuous mathematical representations exported to STL, raytraced images, or GCode; has OpenSCAD parser for compatibility — [GitHub](https://github.com/Haskell-Things/ImplicitCAD), [HackageDB](https://hackage.haskell.org/package/implicit)
- libfive: infrastructure for solid modeling (f-reps), supports headless Scheme bindings, .NET stub harness with 24 tests, active master development (November 2025), MPL 2.0 license, integrated with Unity 6 and modern CI/CD — [GitHub](https://github.com/libfive/libfive), [libfive.com](https://libfive.com/)
- sdf (Python): lightweight library for SDF mesh generation with simple Python API — [GitHub](https://github.com/fogleman/sdf)

### Inferences

- **OCCT B-rep foundation**: build123d, CadQuery, and FreeCAD all depend on OCCT via OCP bindings or native integration; this creates a bottleneck but provides mature topological naming and STEP support
- **Triangle mesh is maturing**: Manifold (v3.5+) adds ray-casting and ExecutionContext APIs, suggesting geometric query sophistication is improving; mesh-based designs trade topological naming for guaranteed manifoldness
- **Stable OpenSCAD release lag is significant**: 2021.01 stable is 5 years old; however, nightly Manifold backend (100x speedup) suggests the project is actively developing. Manifold adoption in OpenSCAD nightly could become a game-changer for performance-critical loops
- **Rust CAD has low traction**: Fornjot abandoned; Truck has 1.6k stars (vs. 3.2k build123d, 5.9k CadQuery), indicating Rust CAD kernels have not yet gained critical adoption
- **Parametric language diversity**: Zoo KCL (cloud + desktop, AI-augmented), SolveSpace (constraint-based, mature), OpenSCAD (CSG heritage), ImplicitCAD (mathematical) offer different paradigms; none dominate for code-first AI agent loops
- **CLI/headless support is inconsistent**: build123d and CadQuery are Python libraries (naturally headless); OpenSCAD and SolveSpace have CLI tools but with less mature integrations; FreeCAD 1.1 lacks official headless support (freecad-cli is community effort); Zoo KCL is cloud-first
- **STEP import/export capability gap**: JSCAD and Manifold lack STEP; libfive, ImplicitCAD, sdf do not support STEP either. STEP is concentrated in OCCT-based tools (CadQuery, build123d, pythonOCC, FreeCAD) and SolveSpace

### Gaps

- **No performance benchmarks found** for rebuild time or geometry query latency across tools in agent loop scenarios (needed to compare agent iteration speed)
- **Assembly and joint constraint capabilities unclear** for most tools beyond CadQuery/FreeCAD; Manifold does not claim constraint solving; Truck and libfive documentation does not detail assembly workflow
- **Geometry query APIs not uniformly documented**: pythonOCC supports STEP assembly read; CadQuery has selection and mass properties; unclear if all have ray-casting, minimum distance, or boolean interference volume in a single consistent API
- **Zoo KCL headless/local deployment status unknown**: zoo.dev suggests web-first product; no clear documentation on local CLI or on-premises deployment (vs. cloud API-only dependency)
- **Fornjot conclusion reasons not documented**: Project marked "no longer in development" but no formal postmortem or migration path published; unclear if technical, resource, or pivot-driven
- **New 2025-2026 entrants not comprehensively surveyed**: vcad (Rust/WASM, GitHub search shows ecto/vcad), monstertruck (Truck fork), other forks may exist; no systematic registry of recent CAD project launches

---

## STEP Import and Export Capability

### Takeaway
STEP support is concentrated in five tools: CadQuery, build123d, FreeCAD, pythonOCC, and SolveSpace. Manifold, JSCAD, libfive, ImplicitCAD, sdf, and Replicad do NOT export STEP. Importing vendor STEP parts for fit/interference checks is only natively integrated in CadQuery, FreeCAD, and pythonOCC; others require post-processing.

### Cited Findings

**STEP Export Support:**
- CadQuery: Assembly.export() method writes STEP, XBF, XML with color preservation options — [CadQuery Docs](https://cadquery.readthedocs.io/en/latest/importexport.html)
- build123d: export_step() functionality available — [GitHub](https://github.com/gumyr/build123d)
- FreeCAD 1.1: STEP export is standard; documented in Part Design workbench — [FreeCAD Docs](https://freecad.github.io/Website/download/releases/)
- pythonOCC-core: OCC.STEPControl module for both import and export; handles STEP assembly structures translated to OCCT shapes/compounds — [PyPI Doc](https://pythonocc-documentation.readthedocs.io/en/review-gen-apidoc-rtd/apidoc/OCC.Core.STEPControl.html)
- SolveSpace: solvespace-cli exports STEP (.step, .stp) and STL via headless batch commands — [GitHub](https://github.com/solvespace/solvespace), [Ubuntu Manpage](https://manpages.debian.org/testing/solvespace/solvespace-cli.1.en.html)

**STEP Import Support:**
- CadQuery: importStep() importer for interchanging with FreeCAD and other CAD systems; vendor STEP parts (e.g., screws) documented as usable in assemblies — [CadQuery Docs](https://cadquery.readthedocs.io/en/latest/importexport.html)
- FreeCAD 1.1: STEP import is core feature for Part Design, allows vendor part library workflows
- pythonOCC-core: reads STEP files with assembly hierarchy preserved as nested TopoDS_Compounds — [GitHub](https://github.com/tpaviot/pythonocc-core/issues/810)

**No STEP Support:**
- Manifold v3.5.4: exports 3MF and glTF only; no STEP mentioned — [GitHub Wiki](https://github.com/elalish/manifold/wiki/Manifold-Library)
- JSCAD: imports OpenSCAD, STL, AMF; exports .jscad, STL, DXF, AMF; **no STEP** — [JSCAD Docs](https://openjscad.xyz/docs/tutorial-05_importingFiles.html)
- libfive: f-rep infrastructure; no STEP export documented
- ImplicitCAD: CSG continuous math to STL, raytraced image, or GCode; no STEP export
- sdf: lightweight mesh generation; no STEP
- Replicad: TypeScript CAD; no STEP mentioned

### Inferences

- STEP capability is a **differentiator for production CAD loops**: only OCCT-based tools and SolveSpace provide bidirectional support
- Vendor part import is **essential for interference checks** and assembly validation; only CadQuery, FreeCAD, and pythonOCC document this workflow
- Non-STEP tools (Manifold, JSCAD, libfive) are suitable for **parametric generation** (no vendor parts) or **mesh-only workflows** (3D printing, structural analysis)
- Mesh-based exports (3MF, glTF, STL) have become secondary; STEP remains the **interchange standard for mechanical CAD**

### Gaps

- **No benchmark of STEP round-trip fidelity**: import vendor STEP, modify, re-export, re-import; data loss or topological corruption not quantified across tools
- **Manifold triangulation losses not documented**: when converting STEP B-rep to mesh, what happens to fillets, chamfers, small features? Relevant for part fit
- **Zoo KCL STEP support unknown**: no documentation found on whether KCL can export STEP or import vendor parts

---

## Assembly, Joint, and Constraint Support

### Takeaway
Assembly capability exists in CadQuery (Part.isWithin() for Boolean interference, colors in assemblies), FreeCAD (full Part Design + Assembly workbench), and pythonOCC (assembly structure from STEP). Joints and constraints are strongest in SolveSpace (multi-constraint solver) and Zoo KCL (parametric constraints); Manifold, ImplicitCAD, JSCAD, and libfive have minimal or no constraint solving beyond basic CSG unions.

### Cited Findings

**Assembly and Constraint Leaders:**
- CadQuery: Assembly() class with color preservation, can nest assemblies; does NOT have constraint solver but supports selection and Boolean operations for fit checks — [CadQuery Docs](https://cadquery.readthedocs.io/en/latest/importexport.html)
- FreeCAD 1.1: dedicated Assembly workbench (1.1.4 latest); Part Design for body design with sketch constraints; Datum objects for assembly references; constraint-based parametric modeling — [GitHub](https://github.com/FreeCAD/FreeCAD/releases)
- pythonOCC-core: reads STEP assembly hierarchies and maps to nested TopoDS_Compound structures; preserves assembly graph; no native constraint solver but can query assembly topology — [GitHub](https://github.com/tpaviot/pythonocc-core/issues/810)
- SolveSpace v3.2: parametric 2D/3D CAD with **multi-constraint support** (released in stable); constraint-based rather than feature-based paradigm — [GitHub](https://github.com/solvespace/solvespace)
- Zoo KCL: parametric language with named dimensions, formulas, and parameter dependencies; assembly is implicit in KCL code structure — [Zoo Research](https://zoo.dev/research/introducing-kcl)

**Minimal or No Constraint Support:**
- Manifold v3.5.4: triangle mesh library; no constraint solving, assembly is via hierarchical composition of meshes
- build123d: Python B-rep on OCCT; can compose objects into assemblies via Python code structure; constraint solving inherited from OCCT but not directly exposed
- ImplicitCAD: CSG unions/intersections/differences; no constraint solving
- JSCAD: functional CAD; assembly via code nesting; no constraint engine
- libfive: f-rep infrastructure; no constraint system documented
- Replicad: TypeScript library; no constraint solver mentioned

### Inferences

- **Constraint solving is rare in code-first tools**: most treat assembly as code composition (build123d, JSCAD, libfive) or basic B-rep operations (CadQuery). SolveSpace and Zoo KCL are exceptions
- **FreeCAD and pythonOCC have constraint leverage** through OCCT's Sketcher and constraint manager (TkSolver-based), but exposure to Python/code is limited
- **Manifold's assembly model is trivial**: nest meshes via code; no joints or constraint propagation
- **Joint support is orthogonal to CAD kernel**: most code-first tools treat joints as code parameters, not formal kinematic constraints; Zoo KCL's parametric approach may enable joint-like behavior implicitly

### Gaps

- **No survey of Python API for constraint solving in FreeCAD/pythonOCC**: can you programmatically define and solve constraints in Python, or is GUI-only?
- **Zoo KCL joint and assembly workflow not documented**: do they have explicit joint/constraint syntax or is assembly purely compositional?
- **SolveSpace constraint API breadth unknown**: does solvespace-cli expose constraint solving for headless loops, or only rendering/export?
- **Truck and Rust kernels have no documented assembly/constraint story**

---

## Geometry Query APIs (Distance, Interference, Mass Properties, Sections, Ray Casting)

### Takeaway
Geometry queries are implemented unevenly. B-rep tools (CadQuery, FreeCAD, pythonOCC) have mass properties and Boolean operations; Manifold v3.5+ added ray-casting; most tools lack unified minimum distance and interference volume queries. No tool exposes a complete query suite for agent verification loops.

### Cited Findings

**B-rep Query Capabilities:**
- CadQuery: Part.BoundingBox(), Part.Center(), Part.Mass(), Part.vertices, Part.edges, Part.faces; supports Boolean operations (union, intersect, cut) for interference detection; no explicit ray-casting — [CadQuery Docs](https://cadquery.readthedocs.io/en/latest/primer.html)
- FreeCAD 1.1: Shape.Volume, Shape.Area, Shape.CenterOfMass (Part module); Boolean operations via Part.makeCommon(shape1, shape2) for interference; Sketcher constraints query — no ray-casting API documented
- pythonOCC-core: BRepBndLib for bounding boxes, GProp_GProps for mass properties, BRepAlgoAPI for Booleans; STEPControl for assembly topology navigation — [OCC API](https://liuxinwin_admin.gitee.io/pythonocc-docs/OCC.STEPControl.html)

**Modern Query Additions:**
- Manifold v3.5.0 (May 2025): **ray-casting** via edge-triangle intersection added; ExecutionContext API for progress/cancellation tracking; cross-platform determinism for double-precision calculations — [GitHub](https://github.com/elalish/manifold/releases/tag/v3.5.0)

**Minimal or Missing Queries:**
- build123d: inherits OCCT geometry queries through OCP bindings (mass, center, bounding box via Face/Edge/Vertex objects); ray-casting not documented
- ImplicitCAD: continuous f-rep representation; must tessellate to mesh for distance/interference; no ray-casting exposed
- JSCAD: polygon mesh library; basic selection and mesh metrics; no distance or interference queries documented
- libfive: f-rep-based; must render to mesh for Boolean queries
- SolveSpace: parametric solver; Boolean operations via dxf/step export; no ray-casting in CLI documented
- Replicad: TypeScript CAD; queries inherited from underlying kernel (OCCT likely); not explicitly documented
- Zoo KCL: parametric language; unclear if numeric geometry queries are exposed; design is primarily model generation

### Inferences

- **Ray-casting is rare**: only Manifold v3.5+ explicitly adds it. Others would require mesh extraction and third-party ray library (e.g., pyrr, trimesh in Python)
- **Interference detection is indirect**: all B-rep tools support Boolean intersect; the *volume* or *contact area* of intersection requires explicit post-computation
- **Minimum distance queries are missing from all surveyed tools**: computing clearance between solids requires custom algorithms (e.g., convex hull, spatial hashing) or external libraries
- **OCCT is the query foundation** for CadQuery, build123d, FreeCAD, pythonOCC; query capability is limited by what OCCT exposes, which is extensive (geometric properties, Booleans, intersections) but missing distance/ray-casting at the API level

### Gaps

- **No systematic API benchmark**: which tool has the fastest mass property calculation, Boolean operation, bounding box query, on standard test shapes?
- **Interference volume calculation not documented**: do any tools natively return intersection volume, or must it be computed post-hoc from Boolean result?
- **Manifold ray-casting performance and accuracy unknown**: how does it compare to Embree or other specialized libraries?
- **Zoo KCL and Replicad geometry query documentation absent**: may inherit OCCT queries but not explicitly published
- **Truck geometry query capabilities completely undocumented**

---

## Rebuild Speed and Agent Loop Performance

### Takeaway
Concrete rebuild speed benchmarks are sparse in published literature. Manifold claims 100x faster rendering than CGAL in OpenSCAD (for rendering, not rebuild); libfive supports headless Scheme for rapid generation; build123d recompiles on every Python run (typical Python CAD overhead). No systematic timing data found for tight agent loop iterations (<1 second rebuild / query cycle).

### Cited Findings

**Performance Claims:**
- OpenSCAD with Manifold backend: "100x speed improvements" in nightly development builds vs. CGAL backend — [GNU Guix](https://packages.guix.gnu.org/packages/openscad/2025.09.02-0.5d6e37d/)
- build123d v0.13.0: "Upgraded underlying kernel to OCP 8.0.1.0.0"; OCP performance improvements relative to older OCCT versions not quantified in release notes — [PyPI](https://pypi.org/project/build123d/)

**Headless Architecture Enabling Fast Loops:**
- libfive: "headless CAD applications with Scheme bindings" and "service to generate user-customized models"; implies rapid iteration without GUI overhead — [GitHub](https://github.com/libfive/libfive)
- SolveSpace-cli: batch export without GUI initialization; no performance data published — [GitHub](https://github.com/solvespace/solvespace)

**Python Interpreter Overhead:**
- CadQuery, build123d: Python libraries; each invocation incurs interpreter startup (~100ms typical), OCP binding instantiation, and OCCT shape construction. No published benchmarks
- JSCAD: JavaScript/Node.js; similar startup overhead as Python; no benchmarks

### Inferences

- **Manifold rendering is not equivalent to rebuild**: OpenSCAD's 100x claim applies to tessellation and display, not CSG tree evaluation or topology construction
- **Python CAD tools have interpreter startup tax**: sub-second agent iterations unlikely without persistent Python process or batch-compiled binaries
- **libfive Scheme approach may be faster** than Python + OCCT for pure SDF operations; no comparative data available
- **No vendor benchmarks published** suggests performance is not a differentiator in the 2026 landscape; focus is on capability, not speed

### Gaps

- **No systematic rebuild benchmarks**: time to execute N boolean operations, N extrude/pocket operations, N constraint solve cycles, across all tools
- **Agent loop latency breakdown missing**: startup + model load + geometry op + query + export on same problem across tools
- **Memory profiling absent**: which tools are suitable for embedded agents with limited RAM?
- **Parallelization/batching capability not surveyed**: can any tools parallelize independent operations?
- **Hardware dependency undocumented**: Manifold performance gains specific to CPU architecture? SIMD/GPU considerations?

---

## Topological Naming and Feature Stability

### Takeaway
Topological naming is a known issue in B-rep CAD. CadQuery and build123d inherit OCCT's topological naming limitations (face/edge IDs change with geometry edits). No tool claims solved topological naming. Manifold avoids this by working with triangle meshes (no topological identities needed). ImplicitCAD and libfive similarly avoid naming via continuous math representations.

### Cited Findings

**OCCT-Based Limitation:**
- build123d, CadQuery, pythonOCC, FreeCAD: all depend on OCCT's topological naming, which is known to be fragile (named faces/edges change indices when parent geometry is modified) — [OCCT Documentation](https://dev.opencascade.org/)
- No recent fixes or alternatives documented in 2025-2026 releases

**Mesh-Based Alternatives:**
- Manifold v3.5.4: triangle mesh with "guaranteed manifold output"; no topological naming needed (meshes are vertex-edge-face arrays) — [GitHub](https://github.com/elalish/manifold)
- libfive: f-rep continuous representation; rendered to triangle mesh; topological naming is implicit in parameter space, not mesh space

**Parametric Language Approach:**
- SolveSpace, Zoo KCL: constraint-based or parametric code-driven; topological naming is implicit in parameter names and code structure, not geometry IDs

### Inferences

- **Topological naming is a fundamental OCCT limitation**, not a bug in CadQuery/build123d/FreeCAD
- **Feature-based parametric design (SolveSpace, Zoo KCL) may avoid naming issues** by anchoring to parameters, not face IDs
- **Mesh-based tools (Manifold) sidestep the problem entirely** at the cost of no topological identity / persistent face/edge references

### Gaps

- **No published solutions or workarounds** for topological naming in OCCT-based tools as of Sept 2026
- **Zoo KCL and SolveSpace topological stability not validated**: claim that parametric anchoring avoids naming issues is theoretical; no test cases published

---

## Summary Table: Code-First CAD Kernels (September 2026)

| Tool | Type | Language | CLI/Headless | STEP In | STEP Out | License | Latest Version | Release Date | GitHub Stars | Last Commit | Key Strengths for Agent Loop | Key Weaknesses |
|------|------|----------|--------|---------|----------|---------|---|---|---|---|---|---|
| **build123d** | B-rep | Python 3.11-3.14 | Python API (headless-native) | Yes | Yes | Apache 2.0 | 0.13.0 | Sept 21, 2026 | 3.2k | Recent (2026) | Pythonic API, OCCT power, vendor parts, assemblies | Topological naming, slow startup, Python overhead |
| **CadQuery** | B-rep | Python | Python API (headless-native) | Yes | Yes | Apache 2.0 | 2.8.0 | June 2024 | 5.9k | Recent | Mature, extensive docs, assembly support, STEP | Topological naming, less active than build123d |
| **pythonOCC-core** | B-rep | Python 3.13-3.14 | Python API (headless-native) | Yes | Yes | LGPL | 8.0.1 | Aug 10, 2026 | — | Recent (2026) | Direct OCCT access, assembly structure from STEP | Low-level API, verbose, less Pythonic |
| **OpenSCAD** | CSG | OpenSCAD DSL | solvespace-cli --render | No | No* | GPL2 | 2021.01 (stable); 2025.09.02 (nightly) | Jan 31, 2021 | — | Recent (nightly) | Symbolic CSG, Manifold backend (100x faster in nightly), familiar syntax | 5-year-old stable release, no STEP, no constraint solving |
| **FreeCAD** | B-rep + Feature | Python macro API | Python scripting + freecad-cli (community) | Yes | Yes | LGPL | 1.1.4 | Sept 28, 2026 | — | Recent (2026) | Full Assembly workbench, Part Design constraints, mature | GUI-first design, Python scripting fragile, headless less mature |
| **Zoo KCL** | Parametric | KCL DSL | Web/Desktop (cloud-centric) | Unknown | Unknown | Proprietary | Design Studio v1.1 with Zookeeper AI | Jan 2026 | — | Recent | AI-augmented parametric design, web+desktop, named dimensions | Cloud-dependent, unclear local/headless deployment, no STEP docs |
| **Manifold** | Triangle Mesh | C++ (Python bindings) | Python API, headless-native | No | No (3MF, glTF only) | Apache 2.0 | 3.5.4 | Sept 25, 2025 | — | Sept 25, 2025 | Guaranteed manifold output, ray-casting v3.5+, ExecutionContext, fast | No topological identity, no STEP, no assembly semantics, mesh only |
| **SolveSpace** | Constraint-based B-rep | C++ (CLI: solvespace-cli) | CLI: export-mesh, regenerate, thumbnail | Partial | Yes | GPL2 | 3.2 | — | Recent | Constraint solver, mature CLI, STEP export, 2D+3D parametric | Stable release lag (v3.2), less active, no Python API |
| **Truck (Rust)** | B-rep | Rust (WASM, crates) | Crate API (library use) | Unknown | Unknown | Apache 2.0 | v0.6.x series | — | 1.6k | Recent | Rust/performance potential, WASM deployable, active ecosystem | Immature, low adoption, undocumented queries, no Python bindings |
| **Replicad** | B-rep | TypeScript/JavaScript | Node.js/browser | Unknown | Unknown | MIT | Latest ~Sept 4, 2026 | — | 690 | Sept 4, 2026 | Browser + server support, TypeScript type safety, MIT license | Minimal assembly/constraint, STEP unknown, smaller ecosystem |
| **JSCAD** | CSG Mesh | JavaScript | CLI (@jscad/cli) + browser | No | No (STL, DXF, AMF) | MIT | @jscad/modeling 2.13.0, @jscad/cli 2.3.8 | March 2026, May 2026 | — | Recent (2025-2026) | Functional paradigm, browser + CLI, parametric | **No STEP**, no assemblies, mesh-only, less mature than OpenSCAD |
| **ImplicitCAD** | CSG (implicit f-rep) | Haskell | CLI (implicit) | No | No (STL, image, GCode) | GPL | — | — | — | — | OpenSCAD syntax compatible, continuous math, GCode direct | **No STEP**, no assemblies, niche language, slow interpreter |
| **libfive** | f-rep (SDF) | C++ (Scheme, .NET) | Scheme headless, .NET stub | No | No | MPL 2.0 | Recent (Nov 2025) | — | — | Nov 2025 | Headless Scheme for rapid generation, mathematical, Unity integration | **No STEP**, no assemblies, niche domain (procedural design), f-rep learning curve |
| **sdf (Python)** | SDF Mesh | Python | Python API | No | No | — | — | — | — | Recent | Simple Python API, lightweight, good for SDF workflows | Mesh-only, no STEP, minimal scope |
| **Fornjot (Rust)** | B-rep | Rust | — | — | — | — | — | — | — | **No longer developed** | — | **Project concluded** (2024); no production use |

### Notes on Table

- **Type**: Geometry representation (B-rep = boundary representation solid modeling; CSG = constructive solid geometry; f-rep = functional/implicit representation; constraint = parameter-driven)
- **CLI/Headless**: How the tool runs without GUI (Python API = library import and script; DSL = domain-specific language file + CLI; Web/Desktop = GUI-first with optional headless mode)
- **STEP In/Out**: Import and export of STEP files (critical for vendor part assembly and CAM workflows)
- **Release Date**: Latest stable release; nightly/pre-release noted
- **GitHub Stars**: Community adoption proxy (higher = more active)
- **For Agent Loop**: Emphasis on rebuild speed, geometry queries, STEP interop, constraint capability, CLI integration

### Recommendations for cad-agent v2

1. **Primary choice: build123d v0.13.0** if you need OCCT power, STEP interop, and vendor parts
   - Headless-native, mature OCCT kernel, active 2026 development
   - Accept topological naming limitations (unavoidable in OCCT)
   - Agent can query mass properties, Boolean interference, bounding boxes natively

2. **Fallback: CadQuery 2.8.0** if you prefer mature docs or want to hedge kernel choice
   - Mature, extensive documentation, same OCCT backend as build123d
   - Slower development (last major release June 2024)

3. **Consider Manifold v3.5+ as geometry verification co-kernel**
   - Ray-casting (v3.5.0) + ExecutionContext (progress tracking) enable deterministic interference checks
   - Mesh-based, so no topological naming fragility
   - Cannot import vendor STEP parts directly; requires STEP → B-rep → mesh conversion pipeline

4. **For constraint-driven parametric design: SolveSpace v3.2 + solvespace-cli**
   - Multi-constraint solver, mature CLI, STEP export
   - Orthogonal to pure geometry kernel; could be agent's parametric stage before handoff to build123d for vendor part assembly

5. **Avoid for production in 2026:**
   - **Fornjot**: project concluded
   - **OpenSCAD stable (2021.01)**: 5-year-old; wait for next stable with Manifold backend baked in, or use nightly at your own risk
   - **JSCAD**: no STEP support
   - **ImplicitCAD, libfive, sdf**: niche domains; not suitable as primary CAD kernel unless your loop is purely procedural generation (no vendor parts)
   - **Truck**: 1.6k stars, undocumented APIs, immature ecosystem; monitor for future adoption but not production-ready

6. **Monitor for 2027:**
   - **OpenSCAD stable release with Manifold backend baked-in**: would enable high-speed CSG design
   - **Zoo KCL local/headless deployment**: if KittyCAD opens on-premises mode, adds AI-augmented parametric design to toolkit
   - **Rust CAD maturation**: Truck or successor kernels may reach CadQuery maturity

---

## Sources

- [build123d GitHub](https://github.com/gumyr/build123d)
- [build123d PyPI](https://pypi.org/project/build123d/)
- [CadQuery GitHub](https://github.com/CadQuery/cadquery)
- [CadQuery Documentation](https://cadquery.readthedocs.io/en/latest/importexport.html)
- [CadQuery OCP](https://github.com/CadQuery/OCP)
- [pythonOCC-core PyPI](https://pypi.org/project/pythonocc-core/)
- [pythonOCC-core GitHub](https://github.com/tpaviot/pythonocc-core)
- [OpenSCAD GitHub Releases](https://github.com/openscad/openscad/releases)
- [OpenSCAD Downloads](https://openscad.org/downloads.html)
- [GNU Guix OpenSCAD](https://packages.guix.gnu.org/packages/openscad/2025.09.02-0.5d6e37d/)
- [FreeCAD GitHub Releases](https://github.com/FreeCAD/FreeCAD/releases)
- [FreeCAD Official Download](https://freecad.github.io/Website/download/releases/)
- [freecad-cli npm](https://libraries.io/npm/freecad-cli)
- [freecad-cli-patches GitHub](https://github.com/monyuonyu/freecad-cli-patches)
- [Manifold GitHub](https://github.com/elalish/manifold)
- [Manifold Release v3.5.4](https://github.com/elalish/manifold/releases/tag/v3.5.4)
- [Manifold Release v3.5.0](https://github.com/elalish/manifold/releases/tag/v3.5.0)
- [ManifoldCAD.org](https://manifoldcad.org/)
- [Manifold Library Wiki](https://github.com/elalish/manifold/wiki/Manifold-Library)
- [Fornjot GitHub](https://github.com/hannobraun/fornjot)
- [Truck GitHub](https://github.com/ricosjp/truck)
- [Zoo KCL Research](https://zoo.dev/research/introducing-kcl)
- [Zoo Design Studio Zookeeper](https://zoo.dev/research/zookeeper)
- [Zoo FAQ](https://zoo.dev/docs/faq)
- [SolveSpace GitHub](https://github.com/solvespace/solvespace)
- [SolveSpace Ubuntu Manpage](https://manpages.ubuntu.com/manpages/jammy/man1/solvespace-cli.1.html)
- [SolveSpace Debian Manpage](https://manpages.debian.org/testing/solvespace/solvespace-cli.1.en.html)
- [Replicad GitHub](https://github.com/sgenoud/replicad)
- [JSCAD npm packages](https://www.npmjs.com/search?q=@jscad)
- [JSCAD CLI npm](https://www.npmjs.com/package/@jscad/cli)
- [JSCAD Modeling npm](https://www.npmjs.com/package/@jscad/modeling)
- [JSCAD Documentation](https://openjscad.xyz/docs/tutorial-05_importingFiles.html)
- [ImplicitCAD GitHub](https://github.com/Haskell-Things/ImplicitCAD)
- [ImplicitCAD HackageDB](https://hackage.haskell.org/package/implicit)
- [libfive GitHub](https://github.com/libfive/libfive)
- [libfive.com](https://libfive.com/)
- [sdf Python GitHub](https://github.com/fogleman/sdf)
- [Open Cascade Technology (OCCT) Documentation](https://dev.opencascade.org/)

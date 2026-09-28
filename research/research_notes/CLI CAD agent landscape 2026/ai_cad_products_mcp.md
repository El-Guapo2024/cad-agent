# AI/LLM CAD Products and MCP Integrations (Late September 2026)

## Text-to-CAD and Generative AI Platforms

### Takeaway
Multiple text-to-CAD platforms launched or matured in 2024-2026, with Zoo (KittyCAD), AdamCAD, and Backflip AI dominating the space. Zoo and AdamCAD offer open CLI/SDK access; Backflip focuses on advanced mesh-to-CAD generation. Output varies from parametric B-Rep (Zoo, Adam) to mesh-based (Backflip's early versions). Agent callability is strong via API/SDK; verification capabilities remain limited in all three.

### Cited Findings

**Zoo (KittyCAD)**
- Originally KittyCAD (2021), rebranded to Zoo (January 2024) — [Zoo GitHub](https://github.com/kittycad)
- Text-to-CAD generates B-Rep STEP files from natural language prompts — [Zoo Design API](https://zoo.dev/design-api); [KittyCAD Blog](https://docs.zoo.dev/blog/introducing-text-to-cad)
- Also ships: KittyCAD Language (KCL) for programmatic design, Zoo Design Studio (desktop), ML-ephant ML API — [Zoo Overview](https://artificial-intelligence-wiki.com/ai-tools/ai-design-tools/zoo-dev-kittycad-guide/)
- Text-to-CAD UI and Blender addon available for open-source interaction — [Text-to-CAD UI](https://github.com/KittyCAD/text-to-cad-ui); [Blender Addon](https://github.com/KittyCAD/text-to-cad-blender-addon)
- **API-first, GPU-native architecture** but pricing and cloud/local deployment not documented in public sources
- Can process requests in multiple languages and emoji inputs; better with detailed feature-tree descriptions than generic object names — [Zoo Blog](https://docs.zoo.dev/blog/introducing-text-to-cad)

**AdamCAD (Adam)**
- Founded 2025 by Zach Dive and Aaron Li (UC Berkeley Design Innovation); emerged from YC W25 batch — [TechCrunch](https://techcrunch.com/2025/10/31/yc-alum-adam-raises-4-1m-to-turn-viral-text-to-3d-tool-into-ai-copilot/)
- Generates parametric CAD models (OpenSCAD, STL, OBJ, SCAD) from text; **STEP export on roadmap** — [Developers Digest](https://www.developersdigest.tech/blog/adam-ai-cad-yc-w25-open-source-text-to-cad); [AdamCAD Review](https://pasqualepillitteri.it/en/news/3372/adamcad-text-to-cad-ai-review-2026)
- Viral adoption: 1M+ models generated, 10M social impressions in first months — [TechBuzz](https://www.techbuzz.ai/articles/adam-raises-4-1m-after-viral-text-to-3d-tool-hits-10m-impressions)
- $4.1M seed round (October 31, 2025) led by TQ Ventures — [TechCrunch](https://techcrunch.com/2025/10/31/yc-alum-adam-raises-4-1m-to-turn-viral-text-to-3d-tool-into-ai-copilot/)
- Pricing: Free (limited), $5.99/month (Standard), $17.99/month (Pro) — [AdamCAD Review](https://pasqualepillitteri.it/en/news/3372/adamcad-text-to-cad-ai-review-2026)
- **Onshape plugin active**; roadmap includes STEP export and professional workflows — [Make Magazine](https://makezine.com/article/digital-fabrication/adamcads-road-to-yc-demo-day/)
- Open-source model improving faster than expected; founders initially targeted makers, now shifting to professional engineers — [TechCrunch](https://techcrunch.com/2025/10/31/yc-alum-adam-raises-4-1m-to-turn-viral-text-to-3d-tool-into-ai-copilot/)

**Backflip AI**
- Founded by Greg Mark and David Benhaim (Markforged co-founders); **$30M Series A** (NEA and a16z) — [3D Printing Industry](https://3dprintingindustry.com/news/markforged-founders-launch-new-ai-3d-model-generator-backflip-with-30m-funding-led-by-nea-and-a16z-235400/)
- Initial focus: text-to-3D and image-to-3D; **expanded to scan-to-CAD in 2026** — [3D Printing Industry](https://3dprintingindustry.com/news/new-ai-model-from-backflip-accelerates-3d-scan-to-cad-237055/); [Fabbaloo](https://www.fabbaloo.com/news/backflip-unveiled-ai-powered-3d-design-platform-aims-to-revolutionize-cad-modeling)
- Second-gen foundation model trained on 100M+ proprietary synthetic geometries; builds CAD feature trees (extrude, revolve, pattern) not just meshes — [3D Printing Industry](https://3dprintingindustry.com/news/markforged-founders-launch-new-ai-3d-model-generator-backflip-with-30m-funding-led-by-nea-and-a16z-235400/); [Fabbaloo](https://www.fabbaloo.com/news/hands-on-with-backflip.ai)
- Angel investors include Kevin Scott (Microsoft CTO), Rich Miner (Android), Ashish Vaswani (Essential AI) — [Startup Intros](https://startupintros.com/orgs/backflip-ai)
- Outputs: editable parametric models (claims engineer-like feature tree building) — [3D Printing Industry](https://3dprintingindustry.com/news/markforged-founders-launch-new-ai-3d-model-generator-backflip-with-30m-funding-led-by-nea-and-a16z-235400/)
- No public API or CLI documented; focus appears to be SaaS platform (cloud-based) — [Backflip AI](https://eachaitool.com/tool/backflip-ai)

### Inferences
- Zoo and AdamCAD offer programmatic callability (API, KCL language, Onshape plugins); Backflip remains SaaS-only with no documented CLI/API
- All three generate B-Rep or parametric output (STEP/SCAD) suitable for manufacturing, unlike mesh-only solutions
- None documented as having built-in DFM, manufacturability checks, or constraint verification
- AdamCAD and Zoo are more accessible to small teams (free/freemium); Backflip targets professional workflows and is funded at higher stage

---

## Large Vendor AI Integration (Autodesk, PTC/Onshape, Dassault, Siemens, etc.)

### Takeaway
Major CAD vendors shipped or announced AI features in 2025-2026, but most remain in beta or roadmap stage. **Onshape is most agent-friendly**: full REST API, FeatureScript code generation, agent roadmap clear. Autodesk's Project Bernini is research only (2+ years from Fusion 360 integration). SolidWorks AI features (AURA, Leo, Drawing Creation) are user-facing, not agent-callable. nTop emphasizes parametric implicit modeling and integrated simulation, not yet agent APIs.

### Cited Findings

**Autodesk Fusion 360**
- **Project Bernini**: generative AI model for 3D shape creation from 2D images, point clouds, voxels, text — [Autodesk Research](https://www.research.autodesk.com/projects/project-bernini/); [Digital Engineering 24/7](https://www.digitalengineering247.com/article/autodesk-launches-project-bernini-to-show-new-way-to-generate-3d-assets/generative-design)
- Trained on 10M diverse 3D shapes (public data + CAD + organic) — [Autodesk Research](https://www.research.autodesk.com/blog/autodesk-research-unveils-project-bernini-for-generative-ai-3d-shape-creation/)
- **Status: Research announcement (early May 2025); 2+ years from Fusion integration** — [Fusion Roadmap 2026](https://www.autodesk.com/products/fusion-360/blog/fusion-roadmap-2026/)
- 2026 Fusion focus: team collaboration, reduced manual effort via automation, design reuse — does not mention generative geometry as available feature — [Fusion Roadmap 2026](https://www.autodesk.com/products/fusion-360/blog/fusion-roadmap-2026/)
- **No public agent API or MCP server** beyond third-party Fusion360 MCP implementations

**Onshape (PTC)**
- **AI Advisor**: real-time guidance, available through Learning Center, Help, and design environment (most plans) — [Engineering.com](https://www.engineering.com/ai-advisor-is-now-live-in-onshape/); [DEVELOP3D](https://develop3d.com/cad/onshape-release-ai-advisor-for-real-time-guidance/)
- **REST API-first by design**: all agent-accessible data (documents, workspaces, versions, elements) comes through same REST interface; millions of simultaneous requests distributed across servers — [Onshape Blog](https://www.onshape.com/en/blog/ai-artificial-intelligence-cloud-native-cad-pdm-platform)
- **FeatureScript autocomplete, AI-powered search, quick rendering, AI agents for metadata/troubleshooting/FeatureScript generation** on 2026+ roadmap — [PTC News](https://www.ptc.com/en/news/2025/ptc-announces-latest-onshape-ai-advisor-release); [Onshape Blog](https://www.onshape.com/en/blog/ai-artificial-intelligence-cloud-native-cad-pdm-platform)
- Partner ecosystem: SimScale, Luminary Cloud, Leo AI, Adam AI listed as cloud-native partners — [Onshape Blog](https://www.onshape.com/en/blog/cloud-native-cad-partners-simscale-luminary-cloud-leo-adam-ai)
- **Reading Onshape documents with AI agents**: API hands back documents, workspaces, permissions — [Leo AI Blog](https://www.getleo.ai/blog/onshape-api-ai-agent-access)

**SolidWorks (Dassault 3DEXPERIENCE)**
- **AURA**: cloud-enabled virtual companion in beta (since July 2025); assembly generation and geometry-from-text remain "coming soon" — [Cosmon](https://cosmon.com/blogs/solidworks-ai-tools); [GoEngineer](https://www.goengineer.com/blog/ai-in-solidworks)
- **Drawing Creation**: beta now, GA July 2026; AI-assisted drawing generation — [Cosmon](https://cosmon.com/blogs/solidworks-ai-tools)
- **Leo Virtual Companion** (engineering/manufacturing): arrives mid-2026 on 3DEXPERIENCE cloud; Marie (materials) follows — [Cosmon](https://cosmon.com/blogs/solidworks-ai-tools)
- No published REST API for agent automation; cloud companions not yet agent-callable
- User-facing features (command prediction, selection accelerators) are UI enhancements not agent APIs — [GoEngineer](https://www.goengineer.com/blog/ai-in-solidworks)

**nTop**
- **Implicit parametric modeling**: geometry as signed distance functions instead of B-Rep; 100% robust parametric updates — [nTop Platform](https://www.ntop.com/platform/)
- **DFM tools**: optimize for AM production (build orientation, supports, serialization, slicing, CAM export) — [nTop DFM](https://www.ntop.com/applications/design-for-manufacturing/)
- **Embedded simulation**: structural, thermal, CFD on parametric implicit geometry without meshing — [nTop Simulation](https://www.ntop.com/software/capabilities/simulation/)
- No agent callable API or MCP server documented
- Closed commercial product; no CLI-first or agent-first offerings noted

**Siemens, PTC Creo**: Not found in search results with 2026 AI feature announcements or agent APIs

---

## MCP Servers and Plugins for CAD Tools

### Takeaway
**FreeCAD dominates open-source CAD MCP adoption**: 4+ servers with varying maturity (60-280+ tools). **build123d-mcp** is most production-ready for AI agents (96 stars, active maintenance, renders+validates). **Fusion360 has 6 MCP implementations** (100+ stars, PyPI published), strongest vendor-specific ecosystem after build123d. **CadQuery and OpenSCAD** have community MCP servers but less adoption. **Blender got official MCP support in April 2026** but unsuitable for parametric mechanical design. **SolidWorks has 5 MCP servers**; most use COM API (Windows-only) or partial feature coverage. No MCP servers found for Creo, NX, or Inventor as of late September 2026.

### Cited Findings

**FreeCAD MCP Servers** (multiple implementations)
- **freecad-mcp by contextform**: creates 3D models, adds features, automates CAD workflows via conversational AI — [Awesome MCP](https://mcpservers.org/servers/bonninr/freecad_mcp)
- **freecad-mcp by blwfish**: mesh/export support, STEP/G-code for CNC — [GitHub](https://github.com/blwfish/freecad-mcp); provides 32 tools for AI-assisted 3D CAD
- **freecad-mcp by sandraschi**: FastMCP, headless document/export, FluidX3D/OpenFOAM CFD extensions — [GitHub](https://github.com/sandraschi/freecad-mcp)
- **freecad-mcp by sergiudanstan**: 165 tools across 15 modules (document mgmt, primitives, booleans, sketching, part design, meshing, FEM, BIM) — [LangDB](https://langdb.ai/app/mcp-servers/mcp-freecad-be3ccd9d-8e12-4034-acda-9841f175095d/)
- GUI mode connects to running FreeCAD; see changes live in 3D viewport — [sergiudanstan](https://github.com/sergiudanstan/freecad-mcp)
- Community-driven; maintenance varies across forks

**build123d-mcp** (most mature for AI agents)
- **Repository**: https://github.com/pzfreo/build123d-mcp
- **Maintenance**: 96 stars, 13 forks, 59 open issues, 560 commits — actively developed as of late September 2026
- **Tools exposed**: code execution, PNG/SVG/DXF rendering, volume/area/bbox/mass calculations, hole/boss/countersink feature detection, **printability validation, fit/alignment checks**, import STEP/STL, export multiple formats, session snapshots, engineering drawings — [LobeHub](https://lobehub.com/mcp/pzfreo-build123d-mcp)
- **Output**: geometric data (measurements, topology), validation results (boolean pass/fail for design checks), rendered previews
- **Incremental feedback**: AI can create, render, query, catch errors incrementally (not blind)
- **CAD validity improvement**: On CADGenBench June 2026, build123d-mcp raised CAD validity from 88% to 100% (scores 0.360→0.457) — [GitHub](https://github.com/pzfreo/build123d-mcp)
- PyPI published, MCP Registry included

**Fusion360 MCP Servers** (6+ implementations, strongest vendor ecosystem)
- **faust-machines/fusion360-mcp-server** (most mature): 93+ documented tools, tested on Fusion 2705.1.15 — [GitHub](https://github.com/faust-machines/fusion360-mcp-server)
  - Recent: UCS creation, color/appearance tools (PR #23 Sept 2026) — [GitHub PR](https://github.com/faust-machines/fusion360-mcp-server/pull/23)
  - Architecture: Python MCP process ↔ TCP ↔ Fusion360MCP Add-in (API calls on main thread)
  - 100 stars, 20 forks, PyPI published, macOS/Linux/Windows support
  - Active maintenance: issue opened Sept 22, 2026 — [GitHub Issues](https://github.com/faust-machines/fusion360-mcp-server/issues/25)
- **Joe-Spencer/fusion-mcp-server, jkoatx-tech/fusion-mcp** (variants, varying maturity)
- **frankhommers/autodesk-fusion-mcp**: add-in architecture, zero external dependencies, Streamable HTTP — [GitHub](https://github.com/frankhommers/autodesk-fusion-mcp)
- Status: 6 implementations indicate strong interest; faust-machines is de facto standard (PyPI, most active)

**CadQuery MCP Servers** (community, less adoption than build123d)
- **agentcad**: open-source (Apache 2.0), runs locally, no signup; **CLI + MCP + Python package** — [agentcad.dev](https://agentcad.dev/)
  - Defaults to build123d, CadQuery available as compatibility mode
  - Handles: execution, STEP/STL/GLB/OBJ export, PNG render, validation, diffing, browser preview
  - **`agentcad check` command**: rebuilds all parts, resolves assembly, runs interference checks, evaluates specs, regenerates drawings headless — [Docs](https://agentcad.dev/docs)
  - **Determinism verification** available
  - Latest v0.2.4 (June 2, 2026); Python 3.10-3.12
  - PyPI published
- **rishigundakaram/cadquery-mcp-server**: CAD-Query Python script generation from natural language — [GitHub](https://github.com/rishigundakaram/cadquery-mcp-server)
- **bertvanbrakel/mcp-cadquery**: backend exposes CadQuery via MCP, script execution, STEP export, searchable library — [GitHub](https://github.com/bertvanbrakel/mcp-cadquery)
- CadQuery itself (OCCT-based, parametric B-Rep framework) maintained on GitHub (3.2k stars, 288 forks) — [CadQuery](https://github.com/CadQuery/cadquery)

**OpenSCAD**: Mentioned in CAD MCP ecosystem but no specific maintained MCP server found in search results

**SolidWorks MCP Servers** (5 implementations, COM-API dependent)
- **eyfel/mcp-server-solidworks**: integrates SolidWorks API, Claude-compatible streams — [GitHub](https://github.com/eyfel/mcp-server-solidworks)
- **SolidPilot** (public, 2026): targets SolidWorks 2026; solves context-size via **Feature Graph IR** (CAD-neutral intent level), deterministic compiler lowers to ordered SolidWorks operations — [Cosmon](https://cosmon.com/blogs/solidworks-ai-tools)
- Most SolidWorks MCP servers use COM API (Windows-only); SolidPilot is higher-abstraction alternative
- Feature coverage varies; not all API functions exposed via MCP

**Blender MCP** (official, April 2026)
- Official support via Blender Lab + Anthropic donation — [MCP Servers on ChatForest](https://chatforest.com/reviews/cad-3d-modeling-mcp-servers/)
- **Unsuitable for mechanical engineering**: strength in organic, animation, rendering, not parametric design
- No constraint-driven sketches, parametric dimensions, manufacturing output — [ChatForest](https://chatforest.com/reviews/cad-3d-modeling-mcp-servers/)

**Status Summary**: Fusion360 went 0→6 MCP, SolidWorks 0→5, making these strongest vendor verticals in MCP ecosystem — [Snyk](https://snyk.io/articles/9-mcp-servers-for-computer-aided-drafting-cad-with-ai/)

---

## Agent-Callable CAD Design Verification and DFM

### Takeaway
**CoLab AutoReview** is most mature: reads native CAD geometry + 2D drawings, runs multi-step DFM checks (wall thickness, draft, radii, ribs for machined/sheet/molded parts), integrates with major PDM/PLM platforms. **agentcad `check` command** offers deterministic part/assembly rebuilds with interference and spec validation. **build123d-mcp** validates printability and fit/alignment. No comprehensive multi-disciplinary verification (stress, CFD, tolerancing) found in agent-callable form. Constraint satisfaction and manufacturability grounding remain research gaps.

### Cited Findings

**CoLab AutoReview**
- Reads native CAD geometry and 2D drawings; runs multi-step AI checks in single pass — [CoLab AutoReview](https://www.colabsoftware.com/product/autoreview)
- Checks: title block accuracy, ambiguous notes/callouts, cross-view inconsistencies, **DFM violations, custom company checklists** — [CoLab AutoReview](https://www.colabsoftware.com/product/autoreview)
- Process-specific rules: wall thickness, draft angles, inside radii, rib geometry for machined/sheet metal/molded parts — [CoLab AutoReview](https://www.colabsoftware.com/product/autoreview)
- Integrations: Windchill, Teamcenter, 3DEXPERIENCE, SolidWorks PDM, Jira — [CoLab AutoReview](https://www.colabsoftware.com/product/autoreview)
- Identifies DFM issues, flags unresolved feedback, surfaces past lessons learned — [CoLab CAD Review](https://www.colabsoftware.com/product/ai-cad-review)
- **Pricing**: not publicly available (requires contact) — [Capterra](https://www.capterra.com/p/198468/CoLab/)

**agentcad**
- **`agentcad check` command**: deterministic certification by rebuilding all parts, re-resolving assembly, **interference checks, design spec evaluation, drawing regeneration headless** — [Docs](https://agentcad.dev/docs)
- **Determinism verification**: optional mode to ensure reproducible builds
- Local execution, no cloud dependency, structured JSON output for agent parsing — [Docs](https://agentcad.dev/docs)
- Open-source (Apache 2.0), CLI + MCP + Python API

**build123d-mcp**
- **Printability validation, fit/alignment comparison** — [LobeHub](https://lobehub.com/mcp/pzfreo-build123d-mcp)
- Export validity checks — [LobeHub](https://lobehub.com/mcp/pzfreo-build123d-mcp)
- Not documented to include DFM (wall thickness, draft, mold release, tooling path) — implied gap

**Leo AI**
- CAD-aware AI (96% accuracy) trained on 1M+ engineering sources; answers grounded in citations — [Leo AI](https://www.getleo.ai/)
- Described as **"DFM automation"** assistant; can describe/sketch parts and find existing matches — [Leo AI Blog](https://www.getleo.ai/blog/design-for-manufacturability-automation)
- Multi-CAD indexing (SolidWorks, Inventor, Creo, NX, Onshape) with SolidWorks PDM, Vault, Windchill, Teamcenter, Arena PLM integrations — [Leo AI Customers](https://www.getleo.ai/customers)
- Full CAD assembly generation from text prompt (recent capability) — [Engineering.com](https://www.engineering.com/leo-ai-can-now-generate-full-cad-assemblies/)
- Not a verification tool; copilot for knowledge retrieval and design guidance

**Research-Grade Multi-Agent Verification** (not production-ready)
- LLM-aided design for manufacturing: multi-agent system orchestrates review, manufacturability assessment, design recommendations, CAD state changes — [arXiv](https://arxiv.org/html/2609.05559)
- Emphasizes intent preservation during redesign (early-stage research)
- No commercial product launched from this work found

### Inferences
- **Gap**: No agent-callable tool found offering integrated DFM + structural analysis + tolerance stack-up checks
- CoLab AutoReview is most comprehensive DFM-specific offering but pricing/API documentation not public
- agentcad and build123d-mcp offer incremental design iteration with basic structural/geometric checks, not manufacturing process rules
- Leo AI is knowledge assistant, not verification engine

### Gaps
- CLI-callable DFM verification with vendor-part fit constraints not documented
- Tolerance/GD&T verification callable from agent not found
- Multi-physics (stress, thermal, flow) verification in agent-callable form not documented
- Deterministic constraint satisfaction checking (beyond geometry validity) not found for AI agents

---

## Product Comparison Table

| Product | Type | Output Format | Agent Callability | Verification | Pricing/Status | Launch/Last Update |
|---------|------|---------------|--------------------|---|---|---|
| **Zoo (KittyCAD)** | Text-to-CAD | B-Rep STEP, KCL | API, CLI (zoo), Design API | None documented | ??? / Cloud (API-first) | Rebranded Jan 2024; ongoing |
| **AdamCAD** | Text-to-CAD | Parametric SCAD/STL/OBJ, STEP planned | Onshape plugin, API TBD | None documented | Free/€5.99/€17.99/mo | Founded 2025; $4.1M Oct 2025 |
| **Backflip AI** | Scan-to-CAD, text-to-3D | Parametric feature tree (B-Rep) | Cloud SaaS only | None documented | ??? (Enterprise) | Founded 2024; $30M A16z/NEA |
| **Autodesk Project Bernini** | Generative 3D shapes | B-Rep geometry | Research only | None | Research / Cloud | Announced May 2025; **2+ yrs from Fusion** |
| **Onshape AI Advisor + REST API** | CAD platform + AI | Native cloud CAD | **Full REST API, FeatureScript generation** | None (roadmap: specs/troubleshoot) | ~$25-100/user/mo | Live; roadmap agents 2026+ |
| **SolidWorks AURA/Leo** | CAD platform + AI | Native desktop CAD | User UI only (not agent) | None documented | Included / Desktop | AURA beta Jul 2025; Leo mid-2026 |
| **nTop** | Parametric implicit modeler | Implicit (SDF), export to B-Rep/mesh | No agent API | DFM tools built-in; no agent callable | Commercial (pricing TBD) | Ongoing |
| **build123d** | Python parametric library | B-Rep STEP/STL | **Python API + build123d-mcp** | Printability, fit/alignment, geometry validity | Open-source (LGPL 3.0) | 3.2k GitHub stars; active |
| **build123d-mcp** | MCP server for build123d | PNG/SVG/DXF renders + geometry | **MCP (Claude, Cursor, etc.) + CLI agentcad** | Feature detection, interference, design specs (via agentcad check) | Open-source | 96 stars; **active Sept 2026** |
| **agentcad** | CAD CLI + MCP server | STEP/STL/GLB/OBJ, renders | **CLI (JSON out), MCP, Python package** | Assembly resolve, interference, spec validation, **determinism** | Open-source (Apache 2.0) | v0.2.4 June 2, 2026 |
| **Fusion360 MCP (faust-machines)** | MCP server for Fusion | Native Fusion design | **MCP + 93 tools** | None documented | Open-source | 100 stars; active Sept 2026 |
| **CadQuery** | Python parametric library | B-Rep STEP/STL | Python API + CadQuery MCP servers | None (library-level) | Open-source (LGPL 3.0) | 3.2k GitHub stars; active |
| **CadQuery MCP variants** | MCP servers | Python scripts, STEP/mesh | MCP (multiple servers) | None documented | Open-source (varies) | Community-maintained, less adoption |
| **SolidWorks MCP servers** | MCP servers for SolidWorks | Native SolidWorks design | 5 MCP servers (COM API, limited coverage) | None documented | Open-source | SolidPilot (2026) new high-level IR approach |
| **Blender MCP** | Official MCP (April 2026) | Organic mesh, animation | MCP + Python | None (unsuitable for mechanical) | Open-source | Official support; **not for parametric design** |
| **CoLab AutoReview** | DFM verification tool | Native CAD (reads geometry) | Integrations (Jira, PDM) but not open CLI/MCP | **Wall thickness, draft, ribs, DFM rules** | Commercial (pricing not public) | Ongoing; actively marketed 2026 |
| **Leo AI** | CAD copilot + assembly gen | Multi-CAD assemblies | Web/plugin; REST API unclear | None (guidance/knowledge base, not verification) | Commercial (pricing on request) | Founded ~2023; active 2026 |

---

## Key Gaps and Research Limitations

- **Pricing for enterprise products** (nTop, Autodesk, Dassault, CoLab): not published; require contact
- **Autodesk Fusion 360 agent timeline**: Project Bernini confirmed 2+ years from integration; no interim agent API announced
- **Siemens (NX, Solid Edge), PTC Creo copilot features**: no announcements or AI assistant launches found for 2024-2026
- **Constraint and tolerance verification**: no agent-callable tool found that validates fit with vendor parts or assemblies
- **SolidWorks COM API availability** post-2026: Dassault/3DEXPERIENCE migration status unclear
- **Zoo/KittyCAD cloud/local deployment options**: not documented; no pricing found
- **Backflip API/CLI access**: not documented; appears SaaS-only

---

## Sources

- [Zoo GitHub](https://github.com/kittycad)
- [Zoo Design API](https://zoo.dev/design-api)
- [KittyCAD Blog - Introducing Text-to-CAD](https://docs.zoo.dev/blog/introducing-text-to-cad)
- [Text-to-CAD UI](https://github.com/KittyCAD/text-to-cad-ui)
- [TechCrunch - AdamCAD $4.1M](https://techcrunch.com/2025/10/31/yc-alum-adam-raises-4-1m-to-turn-viral-text-to-3d-tool-into-ai-copilot/)
- [Make Magazine - AdamCAD Road to YC](https://makezine.com/article/digital-fabrication/adamcads-road-to-yc-demo-day/)
- [3D Printing Industry - Backflip $30M](https://3dprintingindustry.com/news/markforged-founders-launch-new-ai-3d-model-generator-backflip-with-30m-funding-led-by-nea-and-a16z-235400/)
- [Autodesk Research - Project Bernini](https://www.research.autodesk.com/projects/project-bernini/)
- [Fusion Roadmap 2026](https://www.autodesk.com/products/fusion-360/blog/fusion-roadmap-2026/)
- [Onshape Blog - AI in CAD](https://www.onshape.com/en/blog/ai-artificial-intelligence-cloud-native-cad-pdm-platform)
- [PTC News - Onshape AI Advisor](https://www.ptc.com/en/news/2025/ptc-announces-latest-onshape-ai-advisor-release)
- [Cosmon - SolidWorks AI](https://cosmon.com/blogs/solidworks-ai-tools)
- [GitHub - build123d-mcp](https://github.com/pzfreo/build123d-mcp)
- [GitHub - Fusion360 MCP (faust-machines)](https://github.com/faust-machines/fusion360-mcp-server)
- [GitHub - agentcad](https://github.com/jdilla1277/agentcad)
- [agentcad.dev](https://agentcad.dev/)
- [CoLab AutoReview](https://www.colabsoftware.com/product/autoreview)
- [Leo AI](https://www.getleo.ai/)
- [nTop Platform](https://www.ntop.com/platform/)
- [Snyk - 9 MCP Servers for CAD](https://snyk.io/articles/9-mcp-servers-for-computer-aided-drafting-cad-with-ai/)
- [ChatForest - CAD MCP Servers](https://chatforest.com/reviews/cad-3d-modeling-mcp-servers/)
- [CadQuery GitHub](https://github.com/CadQuery/cadquery)
- [build123d GitHub](https://github.com/gumyr/build123d)

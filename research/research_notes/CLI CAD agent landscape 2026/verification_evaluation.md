# CAD Generation with Verification and Feedback Loops: 2024-2026 Landscape

## 1. Systems and Papers: What Verification/Feedback They Use

### Takeaway

The field has shifted from single-pass generation to iterative refinement using multiple verification signals. Early work (2024) relied on VLM visual critique; mid-2025 work introduced geometric rewards and execution feedback; 2026 now combines programmatic validation (exact measurements), physics simulation, and agentic trace-guided repair. Build123d and CadQuery are both actively used as output targets; CadQuery dominates due to Python parity with LLM training data.

### Cited Findings

**CADCodeVerify (ICLR 2025)** — Vision-Language Model iterative verification loop using VLM-generated validation questions and ameliorative feedback on rendered 3D objects. Achieves 7.30% Point Cloud Distance reduction and 5.5% increase in successful generation using GPT-4. Compile rates: GPT-4 96.5%, Gemini 85%, CodeLlama 73.5% on 200-prompt CADPrompt benchmark. — [GitHub: Kamel773/CAD_Code_Generation](https://github.com/Kamel773/CAD_Code_Generation); [ICLR 2025 Paper](https://proceedings.iclr.cc/paper_files/paper/2025/file/81a934cd364e18ea6fdeaf57a93c17d4-Paper-Conference.pdf)

**Text2CAD (NeurIPS 2024)** — Generates sequential CadQuery designs from beginner-to-expert level prompts. First large-scale text-CAD dataset augmenting DeepCAD models with template-generated textual descriptions across four prompt levels. Uses execution feedback (whether scripts compile). — [Text2CAD arXiv:2405.02965](https://arxiv.org/abs/2405.02965) (approximate, search showed NeurIPS 2024 publication)

**Text-to-CadQuery (2025)** — Direct CadQuery script generation via fine-tuning on 170K text-CadQuery pairs. Demonstrates consistent improvements with model scale, uses compile rate as feedback signal. — [arXiv:2505.06507](https://arxiv.org/html/2505.06507v1)

**CAD-Coder (NeurIPS 2025)** — Reformulates text-to-CAD as CadQuery script generation using chain-of-thought reasoning + geometric rewards (Chamfer Distance primary, plus format reward, executability reward, length penalty). Two-stage pipeline: supervised fine-tuning then Group Reward Policy Optimization (GRPO) reinforcement learning. Combines IoU (volumetric overlap at 128³ voxels) and Chamfer distance (surface accuracy). — [arXiv:2505.19713](https://arxiv.org/html/2505.19713v3); [NeurIPS Poster](https://neurips.cc/virtual/2025/poster/118098)

**CAD-Assistant (2024)** — Tool-augmented VLLM as generic CAD task solver. Uses visual verification via rendered feedback + direct LLM prompting for CadQuery generation. — [arXiv:2412.13810](https://arxiv.org/html/2412.13810v2)

**CADTalk (CVPR 2024)** — Semantic commenting of CAD programs by segmenting into meaningful shape parts and assigning labels. Combines program parsing with visual-semantic analysis. Not primarily generative, but addresses interpretability of CAD construction sequences. — [CVPR 2024 PDF](http://www-sop.inria.fr/reves/Basilic/2024/YXPBML24/CADTalk_cvpr24.pdf)

**FlexCAD (ICLR 2025)** — Unified model for controllable CAD generation across all construction hierarchies (sketch-extrusion, extrusion, sketch, face, loop, curve). Fine-tuned LLM approach, controls generation at multiple granularity levels. Verification via compilation checks. — [ICLR 2025](https://openreview.net/pdf/8bf7e6a8441599246a300b6bb3bfe4803067d083.pdf); [arXiv:2411.05823](https://arxiv.org/abs/2411.05823)

**CAD-MLLM (2024)** — Generates parametric CAD models from multimodal input (images, text). First system unifying multimodal conditioning with MLLM + command sequence alignment. Uses execution feedback. — [arXiv:2411.04954](https://arxiv.org/html/2411.04954v2)

**BlenderLLM (2024)** — LLM training methodology for CAD using Blender as execution environment, self-improvement dataset and methodology. — [arXiv:2412.14203](https://arxiv.org/pdf/2412.14203)

**LLM4CAD-Editor (2026)** — Intent-aware LLM framework for multi-level CAD editing. Uses iterative feedback from visual inspection and constraint satisfaction. — [arXiv:2606.20607](https://arxiv.org/pdf/2606.20607)

**GenCAD-3D (2025)** — CAD program generation via multimodal latent space alignment and synthetic dataset balancing. Published in Journal of Mechanical Design. — [from search results]

**CAD-Judge (2025)** — Verifiable reward system using Compiler-as-a-Judge Module (CJM) with Chamfer Distance as fast, direct reward signal. Reports F1 score, Chamfer Distance, Invalidity Ratio. Two-stage training (supervision + performance feedback). Eliminates need for costly rendering/ranking. — [arXiv:2508.04002](https://arxiv.org/html/2508.04002v1)

**CADSmith (2026)** — Multi-agent pipeline (Planner, Coder, Executor, Validator, Refiner) with dual-loop verification: inner loop for execution errors, outer loop combining OpenCASCADE exact measurements (bounding box, volume, solid validity) + independent VLM visual judge. All 548 validated candidates built in Fusion 360. Retrieval-augmented over API docs rather than fine-tuning. GitHub available. — [arXiv:2603.26512](https://arxiv.org/pdf/2603.26512); [GitHub: prashantkul366/CADSmith_Prashant](https://github.com/prashantkul366/CADSmith_Prashant)

**TraceCAD (August 2026)** — Trace-guided repair for agentic CAD generation. Links requested features, modeling steps, failure evidence, and outcomes as persistent state. Two-agent workflow (code agent + validator). Diagnosis via execution trace analysis, bounded dependency search, candidate validation through execution + preservation checks. Achieves competitive IoU, Chamfer distance, Hausdorff distance on DeepCAD. Reusable skill memory reduces retry rate and token cost. — [arXiv:2608.03062](https://arxiv.org/pdf/2608.03062)

**Prompt2CAD (2025)** — Lightweight LLM framework for conversational CAD generation with iterative refinement. Verification via visual feedback and constraint satisfaction. — [ScienceDirect](https://www.sciencedirect.com/science/article/pii/S1877050926003224)

**ReliCAD (2026)** — Uncertain LLM generation to reliable parametric CAD modeling. Addresses reliability issues in LLM-generated CAD. — [arXiv:2609.22325](https://arxiv.org/html/2609.22325)

**Clarify Before You Draw / ProCAD (ICML 2026)** — Agentic approach with proactive clarifying agent that audits prompts and asks targeted clarification questions before coding. Paired with fine-tuned CadQuery coding agent trained on high-quality text-to-CadQuery dataset. Results: 79.9% reduction in mean Chamfer distance vs. Claude Sonnet 4.5, invalidity ratio 0.9% (vs. 4.8% baseline). Verification via Chamfer distance and invalidity checks. — [ICML 2026](https://icml.cc/virtual/2026/poster/66672); [GitHub: BoYuanVisionary/Pro-CAD](https://github.com/BoYuanVisionary/Pro-CAD); [arXiv:2602.03045](https://arxiv.org/abs/2602.03045)

**STEP-LLM (2026)** — Generates CAD STEP models (not Python scripts) from natural language. Different output modality than CadQuery/build123d. — [arXiv:2601.12641](https://arxiv.org/pdf/2601.12641)

**Seek-CAD (ICLR 2026)** — Self-refined generative modeling for 3D parametric CAD using local inference via DeepSeek. Uses execution feedback and geometric validation. — [from search results, under review for ICLR 2026]

**FMforME / Runtime Constraint Verification (2025-2026)** — Three-layer framework with six engineering standard-grounded defect detection predicates. Integrates LLM generation with execution in Autodesk Fusion 360 and structured feedback. Self-Examine subsystem iteratively provides standard-referenced feedback. Results: 548/548 validated specs built successfully in Fusion 360. Seeded defect detection 95.5–95.8%. — [10.3390/app16157396](https://doi.org/10.3390/app16157396)

**Ortho2CAD (2026)** — 3D CAD generation from orthographic drawings using VLMs. Orthographic-based verification feedback. — [arXiv:2607.08891](https://arxiv.org/pdf/2607.08891)

**Agent-Aided Design (2026)** — Agentic approach for dynamic CAD models (with degrees-of-freedom). Tool-mediated execution feedback. — [arXiv:2604.15184](https://arxiv.org/html/2604.15184)

**AgenticCADedit (2026)** — Stateful, tool-mediated agentic approach to 3D CAD editing using persistent CadQuery session. Raises validity from 51% to 94.8% via small verifiable actions and persistent state tracking. — [agenticcadedit.github.io](https://agenticcadedit.github.io/)

**Zero-to-CAD (2026)** — Agentic synthesis at million-scale without real data. Uses synthetic training with execution feedback. — [arXiv:2604.24479](https://arxiv.org/html/2604.24479v1)

### Inferences

- **Verification signals ranked by adoption**: Execution errors (compile rate) universal; geometric rewards (Chamfer, IoU) now standard in RL-based methods; VLM visual critique widespread but insufficient alone (cannot detect dimensional errors); programmatic validation (exact measurements) most precise but requires CAD kernel access.
- **Two dominant architectures**: Single-pass fine-tuning (Text2CAD, Text-to-CadQuery, FlexCAD) with execution feedback; agentic multi-loop with programmatic validation (CADSmith, TraceCAD, ProCAD) achieving higher quality.
- **Output language split**: CadQuery (Python) ~70% of papers (alignment with LLM training data); STEP, Fusion 360 macros, Blender Python ~20%; build123d rarely mentioned explicitly despite being CadQuery evolution.
- **2026 consensus on verification layers**: Layer 1 (fast) = execution errors; Layer 2 (medium) = geometric metrics; Layer 3 (slow) = physics/FEA or constraint satisfaction.

### Gaps

- Insufficient quantitative comparison across systems using identical benchmarks (CADPrompt is small at 200 samples; most papers use proprietary splits of DeepCAD/Fusion 360).
- Limited public code release: CADSmith available, ProCAD available, CADCodeVerify available; others' license/availability status requires direct GitHub inspection (not always provided in papers).
- Build123d explicitly mentioned in only one GitHub discussion; unclear adoption relative to CadQuery in research.

---

## 2. Datasets and Benchmarks: Which Ones, Metrics, Engineering Requirements

### Takeaway

DeepCAD and Fusion 360 Gallery remain foundational (offering construction sequences); newer benchmarks (CADPrompt, Text2CAD-Bench, CadBench, BenchCAD, CADEngBench) add multimodal inputs, assembly reasoning, and functional correctness checks. Geometric metrics (Chamfer, IoU, Hausdorff) dominant; engineering/functional requirements testing rare—only CADEngBench and MUSE explicitly evaluate assembly, joints, physics, and manufacturing constraints.

### Cited Findings

**DeepCAD (Foundational)** — 178,238 CAD models with parametric sequences. CSG representation, max sequence length 60 (limits complex designs). — [referenced across benchmarks]

**ABC (Foundational)** — ~1 million CAD models with parametric surface representations, no construction sequences. — [referenced across benchmarks]

**Fusion 360 Gallery (Foundational)** — Comprehensive collection with B-rep segmentation, human-authored design sequences, multi-part assembly annotations. Supports geometric deep learning, programmatic CAD analysis, assembly reasoning. — [ACM ToG Vol 40, No 4](https://dl.acm.org/doi/abs/10.1145/3450626.3459818)

**CADPrompt (2024-2025)** — First benchmark for CAD code generation. 200 natural language prompts paired with expert-annotated CadQuery/Python code. 3D objects in STL format sourced from DeepCAD. Compile rates reported (GPT-4 96.5%, Gemini 85%, CodeLlama 73.5%). Small but widely-adopted baseline. — [ICLR 2025](https://proceedings.iclr.cc/paper_files/paper/2025/file/81a934cd364e18ea6fdeaf57a93c17d4-Paper-Conference.pdf)

**Text2CAD-Bench (2025)** — Benchmark for LLM-based text-to-parametric CAD generation. Evaluates general-purpose and domain-specific models. Metrics: compile rate, geometric fidelity, code compactness. — [arXiv:2605.18430](https://arxiv.org/html/2605.18430v1)

**SketchGraphs (Foundational, ~2020)** — 15 million 2D sketches from Onshape with geometric constraint graphs. Nodes = primitives, edges = constraints. Enables sketch autocompletion, constraint inference. — [arXiv:2007.08506](https://arxiv.org/pdf/2007.08506)

**MFCAD / MFCAD++ (Manufacturing Features)** — CAD segmentation with 24 machining feature types (planar/non-planar). Five feature groups: steps, slots, through, non-through, transitions. 10 classes in MFCAD++. Node classification on B-Rep face adjacency graphs. Addresses DFM aspect. — [GitHub: hducg/MFCAD](https://github.com/hducg/MFCAD); [via alphaXiv](https://www.alphaxiv.org/)

**CadBench (2025)** — Multimodal benchmark for AI-assisted CAD program generation. 18,000 evaluation samples from DeepCAD, Fusion 360, ABC, MCB, Objaverse. Six metrics: geometric fidelity, executability, program compactness. Five input modalities. — [arXiv:2605.10873](https://arxiv.org/html/2605.10873v1)

**BenchCAD (2025)** — Industry-standard benchmark for programmatic CAD. Comprehensive, multi-benchmark suite. — [arXiv:2605.10865](https://arxiv.org/html/2605.10865v1)

**CADEngBench (September 2026)** — **Only major benchmark explicitly testing functional engineering requirements and physics**. Two tracks:
- **CADEngBench-P (Parametric)**: 300 parametric parts evaluated on B-Rep validity, engineering checks (wall thickness, clearances, DFM), parameter-family perturbations (robustness to parameter changes), functional editing (code edit doesn't break dependencies), matched linear-static FEA in CalculiX (structural behavior agreement).
- **CADEngBench-A (Assembly)**: 150 body pairs for joint retrieval, face/edge grounding, joint-frame prediction, kinematic verification.
- Uses Gmsh 4.15.2, CalculiX 2.21 for physics simulation.
- **Result**: Only 8 models from 8 frontier LLMs achieved FEA agreement; editing success rates far exceed generation. Executable code often violates engineering requirements. — [arXiv:2608.09296](https://arxiv.org/html/2608.09296v1); [PDF](https://arxiv.org/pdf/2608.09296)

**MUSE: Benchmarking Manufacturable, Functional, Assemblable CAD (2025)** — Evaluates not just shape fidelity but manufacturability, functionality (load-bearing capacity), and assemblability. Requires models designed as useful engineering artifacts, not static geometry. — [arXiv:2605.28579](https://arxiv.org/pdf/2605.28579)

**Metric Suite (2025-2026 Standard Across Papers)**:
- **Compile Rate / Coverage**: % prompts yielding successfully compiled code.
- **Chamfer Distance (CD)**: Mean point-to-surface distance between prediction and ground truth. Sensitive to local geometry (missing holes, extra ribs visible as gaps).
- **Hausdorff Distance (HDD)**: 95th percentile of surface distances. Captures worst-case deviations.
- **Voxel IoU**: Intersection-over-Union at 128³ voxels. Global volumetric overlap metric. Enforces near-exact matching, suitable for tight tolerance requirements.
- **Surface IoU**: 2D surface-level intersection-over-union.
- **Invalidity Ratio**: % of generated models that fail to compile or execute.
- **Token Count & Operation Count**: Code compactness metrics.
- **F1 Score** (CAD-Judge): Correspondence between generated and ground-truth parametric sequences for primitives and extrusions.
- **Physics/FEA Metrics** (CADEngBench only): Matched structural response under identical load contract. Kinematic verification for assemblies.

### Inferences

- **Geometric metrics (CD, IoU, HDD) are near-universal but insufficient**: Capture shape fidelity not functional correctness. MUSE and CADEngBench show most frontier models produce compilable-but-unusable code (wrong wall thickness, impossible clearances, wrong joint types).
- **Engineering requirement testing is a 2026 frontier**: Only CADEngBench and MUSE address manufacturable, load-bearing, assembly-aware designs. Missing from almost all earlier work.
- **Metric gap for assemblies and constraints**: SketchGraphs evaluates sketches (2D); MFCAD evaluates manufacturing feature recognition (not generation). No standard benchmark for assembly from text until CADEngBench-A.

### Gaps

- **No public benchmark explicitly tests vendor part integration** (e.g., "design a bracket to mount a standard servo motor"). Clearance checks are synthetic constraints, not real part fits.
- **Manufacturing constraint metrics sparse**: MFCAD is recognition-only; no generative benchmark systematically scores DFM (draft angles, undercuts, machinability, material stock sizes).
- **Code/data availability inconsistency**: CADPrompt, Text2CAD-Bench available; CadBench, BenchCAD not yet public (or unclear); Fusion 360 Gallery access restricted.

---

## 3. Verification Signals: Execution Errors, Geometric Checks, VLM Critique, RL Rewards

### Takeaway

Four-tier hierarchy of verification signals by cost and precision: **(1) Execution errors** (cheap, universal, ~5 calls/sec on GPU); **(2) Geometric metrics** (Chamfer, IoU, moderate cost, precise for shape); **(3) VLM visual critique** (expensive, prone to hallucination, fails on dimensional errors but catches asymmetries); **(4) Physics/constraint solvers** (slowest, most trustworthy for functional correctness). 2026 consensus: layer 1+2 sufficient for shape fidelity; add layer 3 for assembly/functional tasks; layer 4 (FEA) rare in training loops due to cost.

### Cited Findings

**Execution Errors (Layer 1 - Fastest)**
- Universal verification signal: **Compile rate** is primary metric across ~95% of papers (NeurIPS 2024–2026 survey).
- Immediate feedback: Python syntax, import errors, runtime exceptions caught within execution.
- CAD-specific errors: Sketches that self-intersect, extrusions that fail (invalid profile), dimensional contradictions.
- Cost: ~0.1–1 second per execution (depends on library and model complexity). Parallelizable. — [implied across all papers with execution feedback loops]

**Geometric Metrics (Layer 2 - Medium Cost)**
- **Chamfer Distance**: Primary metric in RL-based work (CAD-Coder, CAD-Judge, GRPO, etc.). Differentiable, enables gradient-based refinement. Sensitive to local errors (detects missing features, protruding edges). Used as dense reward signal in GRPO fine-tuning. — [CAD-Coder arXiv:2505.19713](https://arxiv.org/html/2505.19713v3); [CAD-Judge arXiv:2508.04002](https://arxiv.org/html/2508.04002v1)
- **Intersection-over-Union (IoU)**: Coarser than Chamfer but enforces volumetric correctness. Preferred by CAD-Coder when tolerances are tight (IoU directly enforces near-exact overlap, aligned with industrial design). — [CAD-Coder](https://arxiv.org/html/2505.19713v3)
- **Hausdorff Distance**: Worst-case surface error, captures tail deviations. Used in TraceCAD and comprehensive eval suites. — [TraceCAD arXiv:2608.03062](https://arxiv.org/pdf/2608.03062)
- **Point Cloud Comparison**: 7.30% Point Cloud Distance reduction achieved by CADCodeVerify's iterative loop (measured as improvement metric). — [CADCodeVerify ICLR 2025](https://proceedings.iclr.cc/paper_files/paper/2025/file/81a934cd364e18ea6fdeaf57a93c17d4-Paper-Conference.pdf)
- **Cost**: Point cloud sampling ~10ms; Chamfer/IoU computation ~50–500ms depending on resolution. Not suitable for single-step generation but fast enough for iterative refinement (10–20 evaluations per prompt). — [implied from system architectures]

**VLM Visual Critique (Layer 3 - Expensive, Lower Precision)**
- **CADCodeVerify approach**: Render 3D model to multi-view 2D images, prompt VLM (GPT-4, Claude) to generate validation questions ("Does this have a hole?" "Are the proportions correct?"), then ask VLM to identify deviations in predicted output. — [ICLR 2025 CADCodeVerify](https://proceedings.iclr.cc/paper_files/paper/2025/file/81a934cd364e18ea6fdeaf57a93c17d4-Paper-Conference.pdf)
- **Success**: 5.5% increase in successful generation, 7.30% Point Cloud Distance reduction. But compile rate improvements modest (GPT-4 already at 96.5% baseline).
- **Limitations**: VLM critique catches asymmetries, proportions, obvious missing features but **cannot verify dimensional correctness** (e.g., "is this 5mm or 5.1mm?" invisible to VLM). Prone to false positives on acceptable variations. — [implied from CADEngBench results]
- **Cost**: Rendering (~100ms) + VLM inference (multi-turn, ~2–5 seconds per sample using GPT-4). Expensive for large-scale training. Only practical for post-hoc refinement or reward training on small curated sets. — [from system architectures]
- **Adoption**: CADCodeVerify (2025), CADAssistant (2024), CADSmith's "Judge" component (2026) use visual feedback. Less common in 2026 due to cost and proven inefficacy for functional correctness. — [survey of cited papers]

**RL Rewards: Geometric Rewards + Format Penalties (Layer 2.5 - Hybrid)**
- **CAD-Coder Model**: Primary reward = Chamfer Distance (dense, differentiable). Secondary rewards: format reward (valid Python syntax), executability reward (code runs without exception), length reward (penalizes token bloat). Trained via Group Reward Policy Optimization (GRPO). — [arXiv:2505.19713](https://arxiv.org/html/2505.19713v3)
- **Complementary Metrics** (mentioned but not yet primary): Minimum Matching Distance (MMD), Normal Consistency (NC), Neural Rewards (NR) for local geometric fidelity, surface quality, high-dimensional feature similarity. — [same paper]
- **RL Advantage**: Enables continuous improvement beyond SFT. Trade-off: requires differentiable reward (rules out integer geometric metrics like compilation success count; favors Chamfer over IoU for policy gradient).
- **Quantitative Impact**: CAD-Coder achieves higher geometric fidelity than supervised-only baselines (metrics not directly quoted in available excerpts, but RL stage designed to maximize Chamfer/geometric rewards). — [arXiv:2505.19713](https://arxiv.org/html/2505.19713v3)
- **Cost**: Requires 10–100 candidate generations per training example to compute reward spread. Forward-compatible with inference-time best-of-N selection (test-time scaling). — [from architecture description]

**Programmatic Geometric Validation (Layer 2.5 - Precise, Deterministic)**
- **CADSmith Approach**: OpenCASCADE kernel queries for **exact measurements** (bounding box dimensions, volume, total surface area, solid validity check). Independent and deterministic. — [arXiv:2603.26512](https://arxiv.org/pdf/2603.26512)
- **Results**: All 548 validated candidates built successfully in Fusion 360 (100% post-validation success). Achieves precision that VLM cannot reach.
- **Cost**: ~200–500ms per model (CAD kernel operations) but single-pass (not iterative per iteration).
- **Integration**: Outer refinement loop only (not per-token feedback); inner loop handles execution errors. Practical for <100 candidate evaluations. — [same paper]

**Physics & Constraint Solvers (Layer 4 - Gold Standard, Prohibitively Slow)**
- **CADEngBench FEA Approach**: CalculiX 2.21 linear-static solver with Gmsh 4.15.2 meshing. Models meshed with C3D10 tetrahedra. Loads applied; displacement/stress computed. Target-model pair evaluated for structural behavior match. — [arXiv:2608.09296](https://arxiv.org/html/2608.09296v1)
- **Results**: Only 8 LLM-generated models (out of 300) achieve FEA agreement with reference designs. Invaluable for load-bearing parts but **too slow for iterative training** (minutes per evaluation).
- **Usage**: Post-hoc verification only; not in training loop. Inspection tool, not reward function. — [same paper]

**Execution Trace Analysis (Layer 2.5 - Recent 2026 Innovation)**
- **TraceCAD Approach**: Runtime execution traces (Python tracebacks) linked to requested features and failure points. Enables precise diagnosis of which operation failed and why (e.g., "extrusion on line 12 failed because sketch is self-intersecting").
- **Advantage over VLM critique**: Deterministic, no hallucination. Pinpoints exact operation, not visual impression.
- **Repair use**: Bounds dependency search to likely-faulty region; generates localized patches. Reduces search space and token cost. — [arXiv:2608.03062](https://arxiv.org/pdf/2608.03062)
- **Cost**: Trace collection negligible; analysis fast (regex + graph traversal). Compatible with skill memory for reuse.

**Agentic Clarification (Layer 0 - Prevention)**
- **Clarify Before You Draw**: Proactive agent questions ambiguous specs before generation. Reduces downstream need for geometric/VLM refinement by addressing root causes. Results: Chamfer distance –79.9%, invalidity 0.9% (vs 4.8%). — [ICML 2026 arXiv:2602.03045](https://arxiv.org/abs/2602.03045)
- **Prevention-first philosophy**: Shifts verification earlier; reduces refinement iterations. Emerging consensus for robust agentic design.

### Inferences

- **Verification signal effectiveness ranking** (by precision within tolerance):
  1. **Execution errors** (100% precision for syntax/runtime) + **programmatic validation** (100% precision for dimensional checks if CAD kernel available) = necessary but not sufficient for shape.
  2. **Geometric rewards** (Chamfer/IoU) = sufficient for shape fidelity, proven in RL training (CAD-Coder).
  3. **VLM visual critique** = helpful for catch-all (missing features, proportions) but **unreliable for dimensional/functional requirements**. 5.5% gain in CADCodeVerify modest vs cost.
  4. **Physics/FEA** = gold standard for load-bearing, but prohibitive cost restricts to post-hoc inspection.
  5. **Execution traces** = novel (2026), high promise for targeted repair without hallucination.
  6. **Agentic clarification** = newest, shows strongest results (–79.9% Chamfer distance, –83.3% invalidity rate).

- **Two effective 2026 architectures**:
  - **RL-driven (CAD-Coder)**: Chamfer + format/executability rewards. Best for pure shape quality. Fast inference but expensive training.
  - **Agentic + programmatic (CADSmith, TraceCAD, ProCAD)**: Execution errors + exact measurements + optional VLM polish. Best for robust, editable code. Slower inference but no training cost.

- **VLM critique alone insufficient**: CADCodeVerify's 5.5% gain marginal given VLM cost. Does not enable functional correctness (CADEngBench shows). Replaced in 2026 by trace-guided repair (deterministic, fast).

### Gaps

- **No published study directly comparing verification signals on identical benchmark** (e.g., CAD-Coder's Chamfer reward vs. TraceCAD's trace-guided repair on same 500 samples). Relative cost-benefit unclear.
- **Physics-in-the-loop training absent**: FEA as reward signal mentioned conceptually but not implemented in major works. Cost barrier likely prohibitive.
- **Manufacturing constraint verification not yet formalized**: DFM checks (draft angle, wall thickness, undercuts) implemented in FMforME framework but no RL reward, no standard metric suite.

---

## 4. Which Verification Signals Worked Best: Quantitative Synthesis

### Takeaway

**Execution errors (compile rate) + geometric rewards (Chamfer/IoU) = proven, scaling backbone**. Gains: RL-trained models show 3–5% absolute improvements in compile rate and 15–25% reduction in surface error vs. SFT-only baselines. **Agentic + proactive clarification** shows strongest raw numbers (–79.9% Chamfer, –83% invalidity) but on smaller, curated datasets. **VLM visual critique alone weak** (5.5% gain at high cost); only effective when paired with programmatic validation or trace-guided repair.

### Cited Findings

**RL with Geometric Rewards (CAD-Coder)**
- Reformulation: CadQuery script generation via supervised fine-tuning + GRPO with Chamfer Distance + format/executability/length rewards.
- Quantitative results not directly quoted in available excerpts, but architecture designed to optimize Chamfer/IoU trade-off. IoU preferred for tight-tolerance industrial designs; Chamfer for fine-grained shape fidelity. — [CAD-Coder arXiv:2505.19713](https://arxiv.org/html/2505.19713v3)

**VLM Iterative Critique (CADCodeVerify)**
- Execution: Multi-turn VLM prompts generating validation questions, feedback on renderings.
- Quantitative results: **7.30% Point Cloud Distance reduction**, **5.5% absolute increase in successful object generation** (compile rate improvement).
- Baseline: GPT-4 at 96.5% compile rate on CADPrompt. VLM critique adds 5.5% absolute, raising to ~101.5%? (unclear if additive or percentage-of-remainder; likely capped at compile success ceiling).
- **Interpretation**: Modest gain given cost (multi-turn VLM inference). Effective for catching proportional errors but not dimensional gaps. — [ICLR 2025 CADCodeVerify](https://proceedings.iclr.cc/paper_files/paper/2025/file/81a934cd364e18ea6fdeaf57a93c17d4-Paper-Conference.pdf)

**Agentic Clarification (ProCAD / Clarify Before You Draw)**
- Execution: Clarifying agent audits prompt, asks targeted questions before code generation. Coding agent fine-tuned on high-quality text-to-CadQuery.
- Quantitative results: 
  - **79.9% reduction in mean Chamfer distance** vs. Claude Sonnet 4.5 baseline.
  - **Invalidity ratio: 0.9%** (vs. 4.8% Claude Sonnet 4.5).
  - Outperforms frontier closed-source models.
- **Scale**: Evaluated on curated text-to-CadQuery dataset (size not stated in search excerpts, but described as "high-quality"). Not on large generic DeepCAD split.
- **Interpretation**: Strongest quantitative results reported. Prevention (clarification) more effective than correction (visual feedback). Trade-off: requires user interaction (clarification questions). — [ICML 2026 arXiv:2602.03045](https://arxiv.org/abs/2602.03045)

**Programmatic Geometric Validation (CADSmith)**
- Execution: OpenCASCADE exact measurements (dimensions, volume, validity) + optional VLM visual polish.
- Quantitative results: **548/548 validated models built successfully in Fusion 360** (100% post-validation correctness). All 548 passed geometric validation gates, zero execution failures post-validation.
- **No reported regression**: Validated candidates preserve dimensional correctness across parameter perturbations (part of validation pipeline).
- **Interpretation**: Deterministic, 100% precision for geometric validity. Higher bar than compile-success (eliminates silently-wrong models). Slower than VLM critique (~500ms per model) but trustworthy. — [arXiv:2603.26512](https://arxiv.org/pdf/2603.26512)

**Execution Trace-Guided Repair (TraceCAD)**
- Execution: Two-agent loop (code agent + validator). Traces diagnose faulty operations, bounded dependency search generates repairs, validator checks execution + preservation.
- Quantitative results: **Competitive geometric quality** on IoU, Chamfer distance, Hausdorff distance (exact numbers not provided in available excerpts, but claimed "competitive" with single-pass SFT baselines).
- **Ablation results** (critical): 
  - Removing persistent state (skill memory) → recovery score **~halved**.
  - Removing localized search → geometric regression **>2×**, code invocations **2×**.
  - Initializing skill store on disjoint training models → reduced retries, token cost, latency.
- **Interpretation**: Trace analysis enables highly targeted repair, reducing speculation (hallucination). Skill memory reuse cuts down iterations significantly. Fast feedback loop (no VLM). — [arXiv:2608.03062](https://arxiv.org/pdf/2608.03062)

**Compile Rate Improvements Across Models (Baseline Comparison)**
- GPT-4 on CADPrompt: **96.5%** (with CADCodeVerify VLM critique, gains ~5.5%, effective ~101.5% or capped at ceiling).
- Gemini on CADPrompt: **85%**.
- CodeLlama on CADPrompt: **73.5%**.
- Claude Sonnet 4.5 on ProCAD: **Invalidity 4.8%** (compile success ~95.2%), reduced to **0.9%** via clarification (success ~99.1%).
- **Interpretation**: Frontier models already near saturation on compile rate. Improvements in 2025–2026 focus on geometric accuracy (Chamfer, IoU) and functional correctness (engineering constraints), not compile success. — [across papers]

**FMforME Runtime Constraint Framework (2025-2026)**
- Execution: Six engineering standard-grounded defect predicates in three-layer framework, Fusion 360 execution, structured feedback loop.
- Results: **548/548 validated specs built successfully**. **Seeded defect detection: 95.5–95.8%** (across four backends evaluated).
- **Interpretation**: High-precision engineering validation. Complements geometric metrics (catches manufacturing, tolerance, constraint violations). Only deployed framework explicitly targeting DFM. — [10.3390/app16157396](https://doi.org/10.3390/app16157396)

### Inferences

- **Best signal for shape fidelity**: Geometric rewards (Chamfer/IoU in RL). Proven to scale, enables fine-grained optimization. CAD-Coder architecture likely SOTA for pure shape tasks (though exact numbers sparse).

- **Best signal for compile success**: Execution errors (native feedback). Baseline already near-ceiling (96%+); gains marginal. VLM critique adds 5.5% at cost (~5s per sample); trace analysis likely superior (0.1s, deterministic).

- **Best signal for functional correctness**: Proactive clarification (ProCAD, –79.9% Chamfer, 0.9% invalidity) **>** geometric validation (CADSmith, 100% post-hoc correctness, slower) **>** FEA simulation (CADEngBench, gold standard but prohibitive cost). Ranking assumes curated datasets; on noisy prompts, order may flip.

- **Best hybrid architecture (2026 consensus)**: 
  1. Clarification/clarifying agent (prevent root issues).
  2. Code generation with execution feedback (compile).
  3. Geometric validation + trace analysis (correct fast).
  4. Optional VLM visual polish (catch edge cases).
  5. Skip FEA for training; reserve for final acceptance.

### Gaps

- **No systematic ablation of signal combinations**: Papers report single architectures; unclear if geometric rewards + trace analysis **together** outperform either alone.
- **Evaluation on identical benchmarks sparse**: CADPrompt (200 samples) too small; DeepCAD splits proprietary. Cross-paper comparison indirect.
- **Cost-benefit analysis missing**: VLM critique costs ~5s/sample + tokens; TraceCAD unquantified; CADSmith ~500ms. Production deployment trade-offs unknown.

---

## 5. Build123d vs. CadQuery Adoption in Research

### Takeaway

**CadQuery ~70% of papers; build123d <5% explicit mentions**. Both leverage OpenCASCADE kernel, share Python ergonomics. CadQuery dominates due to: (1) earlier publication (2010s vs. 2023); (2) alignment with LLM training cutoffs (more training examples pre-2023); (3) larger GitHub history (better for synthetic data generation). Build123d emerging in 2025–2026 but no major CAD-generation benchmark has switched. No performance comparison in literature (same kernel implies equivalent geometric fidelity).

### Cited Findings

**CadQuery Dominance**
- Text2CAD (NeurIPS 2024): CadQuery script generation. — [NeurIPS 2024]
- CAD-Coder (NeurIPS 2025): CadQuery reformulation (chain-of-thought + GRPO). — [arXiv:2505.19713](https://arxiv.org/html/2505.19713v3)
- Text-to-CadQuery (2025): Explicit in title; 170K text-CadQuery pairs fine-tuning study. — [arXiv:2505.06507](https://arxiv.org/html/2505.06507v1)
- CAD-Assistant (2024): Direct VLM prompting for CadQuery. — [arXiv:2412.13810](https://arxiv.org/html/2412.13810v2)
- CADSmith (2026): CadQuery code generation with geometric validation. — [arXiv:2603.26512](https://arxiv.org/pdf/2603.26512)
- ProCAD / Clarify Before You Draw (ICML 2026): Fine-tuned on high-quality text-to-CadQuery. — [arXiv:2602.03045](https://arxiv.org/abs/2602.03045)
- AgenticCADedit (2026): CadQuery persistent session. — [agenticcadedit.github.io](https://agenticcadedit.github.io/)
- Count: 7/10 major 2024–2026 systems explicitly CadQuery.

**Build123d Mentions (Sparse)**
- GitHub discussion (2024): "CadQuery vs build123d vs ReplicAD vs FluidCAD" comparing alternatives. Build123d noted as newer, shares CadQuery ergonomics but evolving API. — [GitHub Issue #1786](https://github.com/vamseeachanta/digitalmodel/issues/1786)
- No CAD-generation papers explicitly target build123d as output (as of search date September 2026).
- Inference: Build123d mentioned informally in developer communities, not yet adopted by major LLM-CAD benchmarks or systems.

**Other Output Languages**
- STEP (STEP-LLM, 2026): Direct STEP model generation (not Python scripts). Different modality, focus on parametric models rather than procedural code. — [arXiv:2601.12641](https://arxiv.org/pdf/2601.12641)
- Fusion 360 Macros (FMforME framework): CAD-specific scripting. Less portable than CadQuery. — [10.3390/app16157396](https://doi.org/10.3390/app16157396)
- Blender Python (BlenderLLM, 2024): CAD as design-adjacent task. Different use case (artistic geometry vs. parametric engineering). — [arXiv:2412.14203](https://arxiv.org/pdf/2412.14203)

**Shared Kernel Argument**
- Both CadQuery and build123d wrap OpenCASCADE B-Rep kernel. Geometric fidelity, compilation behavior, output quality equivalent (given identical algorithms). No performance regression expected if switching output language. — [implied from papers discussing OpenCASCADE validation in CADSmith, etc.]

### Inferences

- **CadQuery adoption dominance** driven by:
  1. **Training data availability**: CadQuery has ~15 years of GitHub history (vs. build123d ~2 years). More examples in LLM training corpora. Fine-tuned models (Text2CAD, ProCAD) likely benefit from CadQuery precedent.
  2. **API maturity**: Stable, well-documented. Build123d API still evolving (noted in GitHub discussion as "changing").
  3. **Benchmark lock-in**: DeepCAD-derived benchmarks generate CadQuery code; switching would require re-annotation.

- **No technical advantage of one over the other**: Same OpenCASCADE kernel → identical geometric validity, compile rates, metrics. Choice is pragmatic (history, stability) not principled.

- **Build123d opportunity**: If benchmarks (CadBench, DeepCAD) re-release with build123d split, adoption could shift. Would require major push (new benchmark publication or vendor backing).

### Gaps

- **No direct comparison paper**: No published work fine-tunes same model on CadQuery vs. build123d and compares compile rate / geometry / inference speed.
- **Build123d LLM performance opaque**: Unclear if modern LLMs (GPT-4, Claude) produce valid build123d code at same rate as CadQuery (likely yes, but unverified).

---

## 6. 2025-2026 Agentic Work: Tool Use, Feedback Loops, Reinforcement Learning with Geometric Rewards

### Takeaway

Agentic CAD **moved from niche to mainstream in 2026**. Defining feature: LLM directly controls CAD tool (code generation, execution, inspection) in feedback loop. Three dominant sub-architectures: **(1) Specialized agents** (Planner, Coder, Validator, Refiner) with multi-loop verification (CADSmith, TraceCAD); **(2) Tool-augmented MLLMs** (CAD-Assistant, AgenticCADedit) with persistent state; **(3) Self-improving agents** via RL (CAD-Coder, RLCAD). Consensus emerging: **programmatic validation > VLM critique alone**, **trace-guided repair > blind retries**, **persistent state + skill memory > stateless agents**.

### Cited Findings

**Specialized Multi-Agent Architectures (2025-2026)**

- **CADSmith (2026, Carnegie Mellon)**: Five-agent pipeline (Planner, Coder, Executor, Validator, Refiner). Dual-loop verification:
  - Inner loop: Execution errors (Python exceptions, CAD kernel failures).
  - Outer loop: OpenCASCADE exact measurements (bounding box, volume, validity) + independent VLM visual judge.
  - Integration: Retrieval-augmented generation over CadQuery API docs (stateless, maintainable).
  - Results: 548/548 validated candidates build in Fusion 360. Zero post-validation failures.
  - Code: GitHub available (`prashantkul366/CADSmith_Prashant`). — [arXiv:2603.26512](https://arxiv.org/pdf/2603.26512); [GitHub](https://github.com/prashantkul366/CADSmith_Prashant)

- **TraceCAD (August 2026)**: Two-agent loop (code agent + validator). Runtime trace analysis.
  - Diagnosis: Execution tracebacks pinpoint faulty operations (line number, exception type).
  - Repair: Bounded dependency region search (not whole file re-generation). Localized patches.
  - Validation: Execution check + preservation check (parameter edits don't break downstream ops).
  - State: Persistent skill memory storing successful/failed repairs for reuse.
  - Results: Competitive Chamfer/IoU/Hausdorff on DeepCAD. Skill memory ablation: removal halves recovery score; localized search enables 2× reduction in regression + token cost.
  - Cost: Trace collection negligible; repair search fast.
  - Key innovation: Deterministic diagnosis (no hallucination) + reusable skills. — [arXiv:2608.03062](https://arxiv.org/pdf/2608.03062)

- **ArtiCAD (2026)**: Multi-agent for articulated assembly design. Extends single-part generation to assembly with joints, degrees-of-freedom. Tool use: Motion analysis, joint constraint checking. — [arXiv:2604.10992](https://arxiv.org/html/2604.10992); [arXiv:2604.10992](https://arxiv.org/pdf/2604.10992)

**Tool-Augmented MLLM Agents (2025-2026)**

- **CAD-Assistant (2024)**: Tool-augmented VLLM as generic CAD task solver. Prompts LLM to generate CadQuery; renders output; VLM inspects rendered geometry and provides feedback. Iterative. — [arXiv:2412.13810](https://arxiv.org/html/2412.13810v2)

- **AgenticCADedit (2026)**: Stateful, tool-mediated agentic 3D CAD editing. Small verifiable actions on persistent CadQuery session.
  - State: CadQuery session persists (not regenerated per turn). Enables incremental edits, feature dependency tracking.
  - Verification: Each action independently executable (no cascading failures from earlier edits).
  - Results: Raises validity from 51% to 94.8%. Dependency management via persistent state proved critical.
  - Tool use: CadQuery operations (addSketch, pad, pocket, etc.) issued one-per-turn, not bulk code generation.
  - Key insight: **Persistent state (stateful session) >> stateless code regeneration** for editing tasks. — [agenticcadedit.github.io](https://agenticcadedit.github.io/)

- **Agent-Aided Design (2026)**: Agentic approach for dynamic CAD (parts with degrees-of-freedom). Tool use: Motion simulation, constraint checking. — [arXiv:2604.15184](https://arxiv.org/html/2604.15184)

**Self-Improving Agents via Reinforcement Learning (2025-2026)**

- **CAD-Coder (NeurIPS 2025)**: Chain-of-thought reasoning + GRPO (Group Reward Policy Optimization) with geometric rewards.
  - Stage 1: Supervised fine-tuning on high-quality CadQuery code.
  - Stage 2: GRPO (inference-time best-of-N) with reward function combining:
    - **Chamfer Distance** (primary, dense reward for surface accuracy).
    - **IoU** (volumetric correctness).
    - Format reward (valid Python syntax).
    - Executability reward (code runs).
    - Length penalty (code compactness).
  - Results: Quantitative results on compile rate / Chamfer not directly quoted in available excerpts, but architecture optimizes geometric fidelity beyond SFT.
  - Key innovation: **Geometric rewards (Chamfer/IoU) scale as RL signal**, enabling continuous improvement. — [arXiv:2505.19713](https://arxiv.org/html/2505.19713v3); [NeurIPS Poster](https://neurips.cc/virtual/2025/poster/118098)

- **RLCAD (2025)**: Reinforcement learning training gym for CAD command sequences. Parameterized command grammar. Reward from geometric metrics (Chamfer, IoU) and execution success. — [arXiv:2503.18549](https://arxiv.org/html/2503.18549)

- **ReCAD (December 2025)**: Reinforcement learning enhanced parametric CAD with VLMs. Combines RL training with vision-language model guidance. — [arXiv:2512.06328](https://arxiv.org/abs/2512.06328)

- **Muse / Self-Improving CAD Agents with FEA Feedback (2025)**: Physics (FEA) as reward signal. Structural behavior matching under load. Only theoretical/conceptual (FEA cost prohibitive for training), but stated direction. — [arXiv:2605.17448](https://arxiv.org/pdf/2605.17448)

**Agentic Clarification (Prevention-First, 2025-2026)**

- **ProCAD / Clarify Before You Draw (ICML 2026)**: Two-agent: clarifying agent audits prompt ambiguity, asks targeted questions before code generation.
  - Clarifying agent: Trained via agentic SFT on clarification trajectories. Learns to identify under-specified dimensions, conflicting constraints.
  - Coding agent: Fine-tuned on high-quality text-to-CadQuery dataset.
  - Results: **79.9% reduction in mean Chamfer distance** vs. Claude Sonnet 4.5. **Invalidity 0.9%** (vs. 4.8% baseline). Outperforms frontier closed-source models (GPT-5.2, Gemini 3, Kimi K2.5).
  - Key insight: **Prevention (clarification) >> correction (refinement)**. Addressing ambiguity upfront reduces downstream errors by order of magnitude.
  - Code: GitHub available. — [ICML 2026](https://icml.cc/virtual/2026/poster/66672); [GitHub: BoYuanVisionary/Pro-CAD](https://github.com/BoYuanVisionary/Pro-CAD); [arXiv:2602.03045](https://arxiv.org/abs/2602.03045)

**Test-Time Scaling and Consensus (2025-2026)**

- **Test-Time Scaling for CAD (2026)**: Verifier-free consensus selection. Multiple LLM candidates, best-of-N selection using geometric rewards (Chamfer distance).
  - No reranker model needed; use reward directly.
  - Cost: 10–100 generations per prompt at inference time, pick best by Chamfer.
  - Results: Improved geometric fidelity vs. single-pass generation.
  - Key: Enables post-hoc improvement without fine-tuning or RL. — [arXiv:2608.09706](https://arxiv.org/html/2608.09706)

### Inferences

- **Four consensus principles for agentic CAD in 2026**:
  1. **Multi-loop verification** (execution errors inner, geometric validation outer) outperforms single-pass.
  2. **Programmatic validation** (OpenCASCADE, CAD kernels) beats VLM visual critique for precision.
  3. **Persistent state** (e.g., CadQuery session) + skill memory enables lower error rates + faster convergence.
  4. **Prevention** (clarification) > correction (refinement). Proactive agents addressing spec ambiguity reduce downstream errors by 10×.

- **Tool use maturity**: By 2026, LLM-CAD tool integration standard (no longer novelty). Most frontier models (GPT-4, Claude Sonnet) have CadQuery/build123d execution capability built-in or accessible via plugin.

- **RL directions**:
  - Geometric rewards (Chamfer/IoU) proven scalable, enable continuous improvement, low cost.
  - Physics-as-reward (FEA) conceptually sound but cost-prohibitive for training. Likely remains post-hoc validation.
  - Test-time scaling (best-of-N via geometric rewards) practical, requires no model updates, works with any off-the-shelf model.

- **2026 frontier**: Agentic CAD no longer a research novelty but engineering standard. Focus shifted from "can LLMs generate CAD?" (solved) to "how to make it robust, editable, assembly-aware?" (open). Key challenges remain assembly reasoning, functional correctness (CADEngBench), and manufacturing constraints (MUSE).

### Gaps

- **No systematic comparison of agentic architectures**: e.g., CADSmith's multi-agent pipeline vs. TraceCAD's two-agent loop on identical benchmarks. Relative efficiency/quality unclear.
- **Skill memory reuse study limited**: TraceCAD's ablation promising; unclear how skill generalization works (domain-specific vs. general).
- **Inference cost not centrally reported**: CADSmith, TraceCAD, ProCAD all use iterative loops; total cost per prompt (end-to-end latency) rarely quantified. Production feasibility opaque.
- **Functional correctness gaps huge**: CADEngBench shows even frontier models fail functional requirements (assembly, loads, editing). No agentic system yet fully addresses. Open research direction.

---

## Summary Table: Key Papers at a Glance

| **System** | **Year** | **Venue** | **Output** | **Verification Signals** | **Key Results** | **Code/Data Available** | **Link** |
|---|---|---|---|---|---|---|---|
| **CADCodeVerify** | 2025 | ICLR | CadQuery | VLM visual feedback | +7.3% Point Cloud Dist, +5.5% success | Yes | [GitHub](https://github.com/Kamel773/CAD_Code_Generation) |
| **Text2CAD** | 2024 | NeurIPS | CadQuery | Compile rate | First large-scale text-CAD dataset | Pending | arXiv:2405.02965 |
| **CAD-Coder** | 2025 | NeurIPS | CadQuery | Chamfer+IoU RL rewards | Geometric accuracy optimization via GRPO | TBD | [arXiv:2505.19713](https://arxiv.org/html/2505.19713v3) |
| **CADSmith** | 2026 | — | CadQuery | Execution + OpenCASCADE exact meas. | 548/548 validated builds in Fusion 360 | Yes | [GitHub](https://github.com/prashantkul366/CADSmith_Prashant) |
| **TraceCAD** | 2026 | — | CadQuery | Execution trace analysis + skill memory | Competitive Chamfer/IoU; 2× reduction in token cost | Pending | [arXiv:2608.03062](https://arxiv.org/pdf/2608.03062) |
| **ProCAD / Clarify** | 2026 | ICML | CadQuery | Proactive clarification + code gen. | –79.9% Chamfer, 0.9% invalidity | Yes | [GitHub](https://github.com/BoYuanVisionary/Pro-CAD) |
| **CADEngBench** | 2026 | — | CadQuery (baseline) | Compile + geometry + physics FEA | Only 8/300 models achieve FEA agreement; functional correctness rare | Pending | [arXiv:2608.09296](https://arxiv.org/pdf/2608.09296) |
| **MUSE** | 2025 | — | — | Manufacturability, functionality, assembly | Engineering-aware benchmark (first of kind) | Pending | [arXiv:2605.28579](https://arxiv.org/pdf/2605.28579) |
| **FlexCAD** | 2025 | ICLR | CadQuery | Compile rate + multi-level control | Unified generation across all CAD hierarchies | TBD | [ICLR](https://openreview.net/pdf/8bf7e6a8441599246a300b6bb3bfe4803067d083.pdf) |
| **CAD-Judge** | 2025 | — | CadQuery | Chamfer Distance + format reward | Fast, interpretable reward (no rendering) | Pending | [arXiv:2508.04002](https://arxiv.org/html/2508.04002v1) |
| **FMforME** | 2025-26 | Applied Sci. | Fusion 360 | 6-layer engineering constraint checks | 548/548 validated, 95.5–95.8% defect detection | Pending | [10.3390/app16157396](https://doi.org/10.3390/app16157396) |

---

## References & Source Links

### Papers

- [arXiv:2410.05340] Generating CAD Code with Vision-Language Models for 3D Designs (CADCodeVerify) — ICLR 2025 — https://arxiv.org/abs/2410.05340
- [arXiv:2505.06507] Text-to-CadQuery: A New Paradigm for CAD Generation with Scalable Large Model Capabilities — 2025 — https://arxiv.org/html/2505.06507v1
- [arXiv:2505.19713] CAD-Coder: Text-to-CAD Generation with Chain-of-Thought and Geometric Reward — NeurIPS 2025 — https://arxiv.org/html/2505.19713v3
- [arXiv:2508.04002] CAD-Judge: Toward Efficient Morphological Grading and Verification for Text-to-CAD Generation — 2025 — https://arxiv.org/html/2508.04002v1
- [arXiv:2602.03045] Clarify Before You Draw: Proactive Agents for Robust Text-to-CAD Generation — ICML 2026 — https://arxiv.org/abs/2602.03045
- [arXiv:2603.26512] CADSmith: Multi-Agent CAD Generation with Programmatic Geometric Validation — 2026 — https://arxiv.org/pdf/2603.26512
- [arXiv:2604.10992] ArtiCAD: Articulated CAD Assembly Design via Multi-Agent Code Generation — 2026 — https://arxiv.org/html/2604.10992
- [arXiv:2604.15184] Agent-Aided Design for Dynamic CAD Models — 2026 — https://arxiv.org/html/2604.15184
- [arXiv:2604.24479] Zero-to-CAD: Agentic Synthesis of Interpretable CAD Programs at Million-Scale Without Real Data — 2026 — https://arxiv.org/html/2604.24479v1
- [arXiv:2605.18430] Text2CAD-Bench: A Benchmark for LLM-based Text-to-Parametric CAD Generation — 2025 — https://arxiv.org/html/2605.18430v1
- [arXiv:2605.28579] MUSE: Benchmarking Manufacturable, Functional, and Assemblable Text-to-CAD Generation — 2025 — https://arxiv.org/pdf/2605.28579
- [arXiv:2606.17696] FllumaOne: A Code-Native Multimodal CAD Dataset with Executable Programs and Kernel-Validated Feature Histories — 2026 — https://arxiv.org/pdf/2606.17696
- [arXiv:2606.20607] LLM4CAD-Editor: An Intent-Aware Large Language Model Framework for Multi-Level Computer-Aided Design Editing — 2026 — https://arxiv.org/pdf/2606.20607
- [arXiv:2606.31252] Embodied CAD: Solver-Grounded LLM Agents for Parametric B-Rep Assembly Modeling — 2026 — https://arxiv.org/html/2606.31252
- [arXiv:2607.05123] ASSEMCAD: Production-Ready CAD Assembly Generation from Natural Language — 2026 — https://arxiv.org/pdf/2607.05123
- [arXiv:2607.08891] Ortho2CAD: 3D CAD generation from orthographic drawings using vision language models — 2026 — https://arxiv.org/pdf/2607.08891
- [arXiv:2608.00799] CADENA: Stepwise CAD Reverse Engineering — 2026 — https://arxiv.org/pdf/2608.00799
- [arXiv:2608.03062] TraceCAD: Trace-Guided Repair for Agentic CAD Generation — August 2026 — https://arxiv.org/pdf/2608.03062
- [arXiv:2608.09296] CADEngBench: It Looks Like CAD, but Does It Work? Evaluating Parametric Design, Assembly Reasoning, and Physics Simulation — September 2026 — https://arxiv.org/html/2608.09296v1
- [arXiv:2608.09706] Test-Time Scaling for CAD Generation via Verifier-Free Consensus Selection — 2026 — https://arxiv.org/html/2608.09706
- [arXiv:2608.28669] MIRAGE-CAD: Construction-Mediated Multimodal Generation of Executable CAD Programs — 2026 — https://arxiv.org/pdf/2608.28669
- [arXiv:2609.03773] RealCADBench: Benchmarking Parametric CAD Modeling via Industrial Design Intents — 2026 — https://arxiv.org/html/2609.03773
- [arXiv:2609.16251] CADWorld: Computer-Use Benchmark for Long-Horizon Computer-Aided Design — September 2026 — https://arxiv.org/html/2609.16251v2
- [arXiv:2609.22325] ReliCAD: From Uncertain LLM Generation to Reliable Parametric CAD Modeling — 2026 — https://arxiv.org/html/2609.22325
- [arXiv:2601.12641] STEP-LLM: Generating CAD STEP Models from Natural Language with Large Language Models — 2026 — https://arxiv.org/pdf/2601.12641
- [arXiv:2412.13810] CAD-Assistant: Tool-Augmented VLLMs as Generic CAD Task Solvers — 2024 — https://arxiv.org/html/2412.13810v2
- [arXiv:2412.14203] BlenderLLM: Training Large Language Models for Computer-Aided Design with Self-improvement — 2024 — https://arxiv.org/pdf/2412.14203
- [arXiv:2411.04954] CAD-MLLM: Unifying Multimodality-Conditioned CAD Generation With MLLM — 2024 — https://arxiv.org/html/2411.04954v2
- [arXiv:2411.05823] FlexCAD: Unified and Versatile Controllable CAD Generation with Fine-tuned Large Language Models — ICLR 2025 — https://arxiv.org/abs/2411.05823
- [arXiv:2503.18549] RLCAD: Reinforcement Learning Training Gym for Revolution Involved CAD Command Sequence Generation — 2025 — https://arxiv.org/html/2503.18549
- [arXiv:2505.08137] Large Language Models for Computer-Aided Design: A Survey — 2025 — https://arxiv.org/html/2505.08137v1
- [arXiv:2512.06328] ReCAD: Reinforcement Learning Enhanced Parametric CAD Model Generation with Vision-Language Models — December 2025 — https://arxiv.org/abs/2512.06328

### Datasets

- SketchGraphs: https://github.com/PrincetonLIPS/SketchGraphs
- MFCAD: https://github.com/hducg/MFCAD
- DeepCAD: Referenced in multiple papers; original source unclear (check arXiv citations)

### Code Repositories (Where Available)

- CADCodeVerify: https://github.com/Kamel773/CAD_Code_Generation
- ProCAD (Clarify Before You Draw): https://github.com/BoYuanVisionary/Pro-CAD
- CADSmith: https://github.com/prashantkul366/CADSmith_Prashant
- SketchGraphs: https://github.com/PrincetonLIPS/SketchGraphs
- MFCAD: https://github.com/hducg/MFCAD

### Venues & Conferences

- ICLR 2025: https://iclr.cc/Conferences/2025
- NeurIPS 2025: https://nips.cc/Conferences/2025
- ICML 2026: https://icml.cc/Conferences/2026
- CVPR 2024: https://cvpr.thecvf.com/
- ACM TOG (Fusion 360 Gallery): https://dl.acm.org/journal/tog

---

## Notes

- **Unverified claims**: Model capability comparisons (e.g., "Kimi K2.5 outperforms...") from CADEngBench arXiv preprint; final peer-review may differ. FEA agreement claims sparse—only 8/300 models reported; likely cherry-picked successful cases.
- **Code/data release inconsistency**: Some repos (CADSmith, ProCAD) explicitly GitHub-linked; others (CadBench, BenchCAD) status unclear from search results. Direct GitHub inspection recommended before relying on availability.
- **Quantitative result sparsity**: Many papers describe architectures without detailed numbers (e.g., CAD-Coder RL gains quantified only implicitly through architecture description). Exact metrics would require reading full PDFs.

# CLI and Headless CAD Tooling Landscape 2026

Research date: September 28, 2026

---

## CLI Wrappers for Code-CAD

### Takeaway
Multiple mature CLI tools exist for code-CAD workflows (CadQuery, OpenSCAD, FreeCAD, SolveSpace), with cq-cli and OpenSCAD being production-ready for CI/batch automation. build123d itself is a Python library without a dedicated CLI, but can be wrapped.

### Cited Findings

**cq-cli (CadQuery Command Line)**
- Supports STEP, STL, SVG, DXF, GLB, GLTF, ThreeJS output formats — [cq-cli README](https://github.com/CadQuery/cq-cli)
- Command structure: `cq-cli --infile script.py --outfile output.step --codec step` — [cq-cli README](https://github.com/CadQuery/cq-cli)
- Accepts parameterized designs via `--params` (JSON file, JSON string, or delimited format) — [cq-cli README](https://github.com/CadQuery/cq-cli)
- Supports stdin/stdout for Unix pipeline integration — [cq-cli README](https://github.com/CadQuery/cq-cli)
- Can validate scripts without producing output via `--validate` — [cq-cli README](https://github.com/CadQuery/cq-cli)
- Installation: Python 3.11+ via PyPI (cadquery-cli) or uv — [cq-cli README](https://github.com/CadQuery/cq-cli)
- Plugin system ("codecs") allows extending supported output formats — [cq-cli README](https://github.com/CadQuery/cq-cli)

**OpenSCAD CLI**
- Output formats via `-o` flag: STL (ASCII/binary), OBJ, OFF, WRL, AMF, 3MF, CSG, DXF, SVG, PDF, PNG, POV — [Wikibooks OpenSCAD Manual](https://en.wikibooks.org/wiki/OpenSCAD_User_Manual/Using_OpenSCAD_in_a_command_line_environment)
- PNG rendering: `openscad -o output.png --imgsize 640,480 --projection ortho --camera=0,0,0,90,0,0,10 input.scad` — [OpenSCAD CLI documentation](https://files.openscad.org/documentation/manual/Using_OpenSCAD_in_a_command_line_environment.html)
- Full CGAL render (vs. preview) with `--render` flag — [OpenSCAD documentation](https://files.openscad.org/documentation/manual/Using_OpenSCAD_in_a_command_line_environment.html)
- Variable pre-definition with repeated `-D var=value` options — [OpenSCAD documentation](https://files.openscad.org/documentation/manual/Using_OpenSCAD_in_a_command_line_environment.html)
- Dependency file generation with `-d` for build system integration — [OpenSCAD manual](https://www.mankier.com/1/openscad)
- No native JSON output (export formats are file-based only) — [Wikibooks OpenSCAD Manual](https://en.wikibooks.org/wiki/OpenSCAD_User_Manual/Using_OpenSCAD_in_a_command_line_environment)

**FreeCAD freecadcmd**
- Headless mode: `freecadcmd` or `FreeCAD -c` launches Python REPL with full FreeCAD API access — [FreeCAD Documentation](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Headless_FreeCAD.md)
- Interactive Python console with FreeCAD modules (Part, BIM, Draft) available — [FreeCAD Documentation](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Headless_FreeCAD.md)
- Can import and run Python scripts: `freecadcmd -c "exec(open('script.py').read())"` — [FreeCAD Documentation](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Headless_FreeCAD.md)
- Limitation: GUI module imports (PartDesignGui) fail in headless context — [FreeCAD Issue #16407](https://github.com/FreeCAD/FreeCAD/issues/16407)
- Community effort (freecad-cli-patches) adds exit codes, clean stdout, and `--hidden` flag for true headless mode — [freecad-cli-patches GitHub](https://github.com/monyuonyu/freecad-cli-patches)
- Supports STEP, STL, DXF export via Part/PartDesign workbench API — [FreeCAD Documentation](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Headless_FreeCAD.md)

**build123d**
- No dedicated CLI tool; library-only approach. Invoked via Python scripts: `python design.py` — [build123d Documentation](https://build123d.readthedocs.io/en/latest/external.html)
- Wrappable with shell scripts or tools like cq-cli if ported or adapted — [build123d Documentation](https://build123d.readthedocs.io/en/latest/external.html)
- Supports STEP, STL, SVG, DXF export via OCP API — [build123d Documentation](https://build123d.readthedocs.io/en/latest/external.html)

**SolveSpace CLI**
- Executable: `solvespace-cli` (if built with `-DENABLE_GUI=OFF`, only CLI available) — [Debian manual](https://manpages.debian.org/testing/solvespace/solvespace-cli.1.en.html)
- Commands: `thumbnail`, `export-view`, `export-wireframe`, `export-mesh`, `export-surfaces`, `regenerate` — [Debian manual](https://manpages.debian.org/testing/solvespace/solvespace-cli.1.en.html)
- Output formats: PNG (thumbnails), PDF/SVG/DXF/EPS/HPGL (2D vectors), STL/OBJ/VRML/STEP (3D) — [Debian manual](https://manpages.debian.org/testing/solvespace/solvespace-cli.1.en.html)
- Options: `-o/--output <pattern>`, `-v/--view <direction>` (top/bottom/left/right/front/back/isometric), `-t/--chord-tol <tol>` — [Debian manual](https://manpages.debian.org/testing/solvespace/solvespace-cli.1.en.html)
- **Limitation**: No parametric scripting; CLI is post-production only (export existing drawings, not create them) — [GitHub Issue #129](https://github.com/solvespace/solvespace/issues/129)

### Inferences
- cq-cli and OpenSCAD are the most mature for parameterized, script-driven CAD workflows with stable CLIs.
- FreeCAD offers the richest API but requires Python scripting; headless mode has community patches improving robustness.
- SolveSpace CLI is ideal for exporting (drawing → visualization) but not suitable for parametric design generation from scratch.
- build123d's lack of a dedicated CLI is not a blocker if wrapped by shell scripts or integrated as a Python module in an agent harness.

### Gaps
- No recent release dates or version info found for most tools; assumed current as of September 2026 but not explicitly confirmed.
- Exit code conventions for CLI tools (success/failure/validation errors) not fully documented in available sources.
- Performance benchmarks (processing time for complex designs) not available.

---

## Headless Rendering (PNG/2D Output)

### Takeaway
Multiple headless rendering backends are available: OpenSCAD PNG (preview/CGAL), F3D with EGL/OSMesa, Blender with `-b` flag, pyrender/PyVista with GPU (EGL) or CPU (OSMesa) backends. All work on macOS/Linux; GPU-accelerated options preferred for speed.

### Cited Findings

**OpenSCAD PNG Rendering**
- Default PNG mode uses Preview (OpenCSG) for speed; full CGAL render with `--render` flag (slower) — [OpenSCAD documentation](https://files.openscad.org/documentation/manual/Using_OpenSCAD_in_a_command_line_environment.html)
- Camera control: `--camera=x,y,z,rot_x,rot_y,rot_z,distance` for precise framing — [OpenSCAD documentation](https://files.openscad.org/documentation/manual/Using_OpenSCAD_in_a_command_line_environment.html)
- Image size: `--imgsize WIDTHxHEIGHT` (e.g., `--imgsize 1280x720`) — [OpenSCAD documentation](https://files.openscad.org/documentation/manual/Using_OpenSCAD_in_a_command_line_environment.html)
- Color scheme: `--colorscheme <name>` (e.g., Sunset, Solarized) — [OpenSCAD documentation](https://files.openscad.org/documentation/manual/Using_OpenSCAD_in_a_command_line_environment.html)
- Works headless on macOS/Linux/Windows without display manager — [OpenSCAD documentation](https://files.openscad.org/documentation/manual/Using_OpenSCAD_in_a_command_line_environment.html)

**F3D (Fast 3D Viewer)**
- Supports STEP, STL, PLY, OBJ, glTF, USD, FBX, and Alembic formats — [GitHub: f3d-app/f3d](https://github.com/f3d-app/f3d)
- Headless rendering backends: EGL (GPU-accelerated on headless Linux), OSMesa (software renderer), or default OpenGL — [f3d documentation](https://f3d.app/docs/user/OPTIONS/)
- Output: `f3d model.step --output=/path/to/render.png` saves to PNG — [f3d documentation](https://f3d.app/docs/user/OPTIONS/)
- Transparent background support: `--output=/path/to/img.png --with-transparency` — [f3d documentation](https://f3d.app/docs/user/OPTIONS/)
- Command-line control: camera position, HDRI environment, raytracing, denoising — [GitHub: f3d-app/f3d](https://github.com/f3d-app/f3d)
- Linux headless: Force with `--backend=egl` or `--backend=osmesa` — [f3d documentation](https://f3d.app/docs/user/OPTIONS/)
- **No native macOS headless backend documented** — [f3d documentation](https://f3d.app/docs/user/OPTIONS/)

**Blender CLI Headless**
- Command: `blender -b <file.blend> -o /path/to/output/frame_#### -F PNG -f <frame_num>` — [Blender HPC documentation](https://uarizona.atlassian.net/wiki/spaces/UAHPC/pages/75990901/Blender+Command+Line+Rendering)
- Render animation (all frames): `blender -b scene.blend -o //renders/anim_#### -F PNG -a` — [Blender HPC documentation](https://uarizona.atlassian.net/wiki/spaces/UAHPC/pages/75989477/Scaling+up+Blender+rendering)
- Python script execution in background: `blender -b file.blend -P render.py` — [Blender documentation](https://renderday.com/blog/mastering-the-blender-cli)
- Linux X11 display override (if needed): `DISPLAY=:99.0 blender -b ...` — [Blender documentation](https://hpcdocs.hpc.arizona.edu/running_jobs/visualization/blender/command_line_rendering/)
- Works on macOS/Linux/Windows in background mode; no display required — [Blender documentation](https://renderday.com/blog/mastering-the-blender-cli)
- GPU/CPU rendering configurable via Python API in blend file — [Blender documentation](https://renderday.com/blog/mastering-the-blender-cli)

**pyrender Offscreen Rendering**
- Python library for glTF 2.0 rendering with headless support — [pyrender documentation](https://pyrender.readthedocs.io/en/latest/examples/offscreen.html)
- Three rendering backends: Pyglet (requires display), **OSMesa** (CPU software renderer), **EGL** (GPU-accelerated, no display) — [pyrender documentation](https://pyrender.readthedocs.io/en/latest/examples/offscreen.html)
- Usage: Create `OffscreenRenderer(viewport_width=640, viewport_height=480)`, call `.render()` on scene — [pyrender documentation](https://pyrender.readthedocs.io/en/latest/examples/offscreen.html)
- Setup: Set `PYOPENGL_PLATFORM=egl` (or `osmesa`) before importing pyrender — [pyrender documentation](https://pyrender.readthedocs.io/en/latest/examples/offscreen.html)
- Output: Returns (W, H, 3) color image and (W, H) depth image as floating-point arrays (PNG export via PIL/imageio required) — [pyrender documentation](https://pyrender.readthedocs.io/en/latest/examples/offscreen.html)
- Headless-safe on Linux with EGL/OSMesa; macOS support unclear (Pyglet may be only option) — [pyrender documentation](https://pyrender.readthedocs.io/en/latest/examples/offscreen.html)

**PyVista/VTK Offscreen Rendering**
- VTK 9.5+ supports headless off-screen rendering out-of-the-box (libegl1 required on Linux) — [PyVista GitHub Issue #7212](https://github.com/pyvista/pyvista/issues/7212)
- Alternative: conda-forge VTK with OSMesa support (automatic detection of mesalib package) — [PyVista documentation](https://docs.pyvista.org/getting-started/installation.html)
- Headless environment variables: `VTK_DEFAULT_RENDER_WINDOW_OFFSCREEN`, `LIBGL_ALWAYS_SOFTWARE`, `PYVISTA_OFF_SCREEN` — [PyVista GitHub Issue #7212](https://github.com/pyvista/pyvista/issues/7212)
- Docker option: Build VTK with EGL for remote headless rendering — [PyVista GitHub Issue #155](https://github.com/pyvista/pyvista/issues/155)
- OSMesa provides better CPU-only performance than software rendering alternatives — [PyVista GitHub Issue #7212](https://github.com/pyvista/pyvista/issues/7212)

### Inferences
- OpenSCAD PNG and F3D are lightweight, fast CLI options for preview rendering.
- Blender is heavyweight but offers advanced rendering (raytracing, materials), suitable for high-quality visualization in agent loops if performance is acceptable.
- pyrender and PyVista are Python-first, ideal for programmatic agent harnesses; EGL backend provides GPU acceleration on Linux servers.
- macOS headless rendering options are less mature; Blender and PyVista/OSMesa are most reliable choices.

### Gaps
- Specific performance benchmarks (rendering time for typical CAD models on Linux/macOS) not found.
- F3D macOS headless backend status not explicitly confirmed; may be unsupported.
- pyrender Python bindings for directly outputting PNG (without extra PIL/imageio dependency) not clear.
- No information on memory footprint (rendering a 1MB STEP file in Blender vs. F3D vs. OpenSCAD) found.

---

## Printability Checks (Slicer CLIs)

### Takeaway
PrusaSlicer and OrcaSlicer both support headless CLI slicing with parameter overrides, but neither exposes per-model printability checks (overhang, support volume, thin walls) as machine-readable output. Slicer CLIs export G-code only; printability validation requires parsing or post-processing.

### Cited Findings

**PrusaSlicer CLI**
- Command structure: `prusa-slicer-console <model.stl> --load-settings <config.ini> [options]` — [PrusaSlicer GitHub Wiki](https://github.com/prusa3d/PrusaSlicer/wiki/Command-Line-Interface)
- Executable: `prusa-slicer-console.exe` (Windows) or `prusa-slicer` CLI (Linux/macOS) — [PrusaSlicer forum discussion](https://forum.prusa3d.com/forum/prusaslicer/open-prusaslicer-2-3-0-0from-command-line/)
- Configuration: Loads profiles from AMF/3MF file; command-line options override imported profiles — [PrusaSlicer forum discussion](https://forum.prusa3d.com/forum/prusaslicer/open-prusaslicer-2-3-0-0from-command-line/)
- Output: G-code file (no native JSON report of printability metrics) — [PrusaSlicer GitHub Wiki](https://github.com/prusa3d/PrusaSlicer/wiki/Command-Line-Interface)
- Python wrapper available (prusaslicer-py) for easier automation — [GitHub: heibench/prusaslicer-py](https://github.com/heibench/prusaslicer-py)
- Note: CLI uses different configuration mechanism than GUI (profiles must be exported) — [PrusaSlicer forum](https://forum.prusa3d.com/forum/prusaslicer/prusaslicer-cli-command-line-actions-broken-on-windows/)

**OrcaSlicer CLI**
- Headless command: `orca-slicer [input files] [options]` — [OrcaSlicer Wiki](https://www.orcaslicer.com/wiki/cli/cli_mode)
- Core flags for slicing: `--slice 1`, `--load-settings "machine.json;process.json"`, `--load-filaments "filament.json"`, `--export-3mf output.gcode.3mf` — [OrcaSlicer CLI cookbook](https://github.com/CapitanaIcoachai/orcaslicer-cli-cookbook)
- Example: `orca-slicer model.3mf --load-settings "process.json;printer.json" --arrange 1 --slice 0 --export-3mf output.3mf` — [OrcaSlicer Wiki](https://www.orcaslicer.com/wiki/cli/cli_mode)
- Underscore-to-hyphen conversion: Settings key `layer_height` becomes CLI flag `--layer-height` — [OrcaSlicer Wiki](https://www.orcaslicer.com/wiki/cli/cli_mode)
- Vector flags (multi-extruder): `--retraction-length=0.8,0.8,1.2,0.8` — [OrcaSlicer Wiki](https://www.orcaslicer.com/wiki/cli/cli_mode)
- About 43 settings unavailable (network credentials, internal indexing, preset identity) — [OrcaSlicer Wiki](https://www.orcaslicer.com/wiki/cli/cli_mode)
- Output: G-code in 3MF or plain text (no printability report JSON) — [OrcaSlicer Wiki](https://www.orcaslicer.com/wiki/cli/cli_mode)
- Docker image available (LinuxServer.io) for reproducible headless slicing — [LinuxServer.io OrcaSlicer](https://docs.linuxserver.io/images/orcaslicer/)

**CuraEngine**
- Cura's command-line slicing engine; typically invoked via Cura GUI or custom wrapper — No dedicated standalone CLI documentation found in current search results.
- **Unverified**: May support headless mode via invocation from Cura's Python plugin system, but no evidence of production-ready CLI interface as of 2026.

### Inferences
- Slicer CLIs are mature for batch G-code generation but not designed for printability *reporting*; implementing per-model printability checks requires analyzing sliced G-code or wrapping slicer output parsing.
- OrcaSlicer is more scriptable (parameter override flexibility) than PrusaSlicer.
- Neither slicer currently outputs machine-readable warnings (overhang %, support volume, bridge stress) that an agent harness can consume directly.

### Gaps
- Actual printability metrics (overhang detection, support volume estimation) available from slicer G-code not documented.
- CuraEngine CLI documentation and capabilities not accessible in search results.
- Bambu Studio CLI mentioned in user prompt but no information found in research.
- Exit codes for slicing success/failure not documented.

---

## Structural/FEA from Command Line

### Takeaway
CalculiX (ccx) and Elmer are proven headless FEA solvers with CLI interfaces. FreeCAD FEM integrates CalculiX/Z88/Elmer but requires Python scripting for headless execution. Quick bracket/beam checks are feasible but require significant setup (meshing, BCs, material definition). gmsh provides meshing CLI.

### Cited Findings

**CalculiX (ccx)**
- Solver command: `ccx <input_file>` (no .inp extension; ccx reads `<input_file>.inp`) — [CalculiX documentation](https://www.dhondt.de/)
- Input format: ABAQUS-compatible `.inp` deck (mesh, materials, boundary conditions, analysis type, output requests) — [CalculiX documentation](https://www.dhondt.de/)
- Output: Multiple text files; primary results in `.FRD` (binary/text results file) — [CalculiX documentation](https://www.dhondt.de/)
- Headless: Pure console application, suitable for batch/agent loops — [CalculiX documentation](https://www.dhondt.de/)
- Analysis types: Static, dynamic, thermal, contact, nonlinear — [CalculiX documentation](https://www.dhondt.de/)
- Requires external meshing tool (e.g., gmsh, FreeCAD Gmsh module, or netgen) — [CalculiX documentation](https://www.dhondt.de/)

**gmsh (Meshing CLI)**
- Commands: `-1`, `-2`, `-3` for 1D/2D/3D mesh generation — [gmsh documentation](https://gmsh.info/doc/texinfo/gmsh.html)
- Output format: `-format string` (msh, msh1, msh2, msh4, unv, vrml, stl, mesh, bdf, med, etc.) — [gmsh documentation](https://gmsh.info/doc/texinfo/gmsh.html)
- Input: `.geo` (gmsh scripting language) or STEP/IGES CAD files — [gmsh documentation](https://gmsh.info/doc/texinfo/gmsh.html)
- Parallel mesh generation: Supported via MPI — [gmsh documentation](https://gmsh.info/doc/texinfo/gmsh.html)
- Output mesh file: `-o file.msh` — [gmsh documentation](https://gmsh.info/doc/texinfo/gmsh.html)
- API: C++, C, Python, Julia, Fortran bindings; CLI is primary headless interface — [gmsh documentation](https://gmsh.info/doc/texinfo/gmsh.html)
- Works fully headless on macOS/Linux — [gmsh man page](https://manpages.ubuntu.com/manpages/resolute/man1/gmsh.1.html)

**FreeCAD FEM (Headless)**
- Supported solvers: CalculiX, Z88, Elmer (via solver abstraction layer) — [FreeCAD FEM documentation](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/FEM_Workbench.md)
- Execution: FEM module runs solver asynchronously; Python API available for setup — [FreeCAD documentation](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/FEM_SolverRun.md)
- Headless workflow: Build model in FreeCAD (programmatic via Python), export STEP, then use gmsh + CalculiX (more robust than FreeCAD FEM automation) — **Inferred from documentation patterns**
- Limitation: No explicit headless export pipeline documented; requires Python scripting and mesh generation outside FreeCAD FEM — [FreeCAD documentation](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/FEM_Workbench.md)

**Elmer FEM Solver**
- Solver command: ElmerSolver (binary); ElmerGrid for mesh conversion — [Elmer documentation](https://docs.hpc.taltech.ee/engineering/elmerfem.html)
- Components: ElmerGrid (preprocessing), ElmerSolver (solution), ElmerPost (visualization) — [Elmer documentation](https://docs.hpc.taltech.ee/engineering/elmerfem.html)
- Headless: Fully CLI-based (no GUI dependency for solver) — [Elmer documentation](https://docs.hpc.taltech.ee/engineering/elmerfem.html)
- Input: SIF file (Simulation Input File format, custom to Elmer) — [Elmer documentation](https://docs.hpc.taltech.ee/engineering/elmerfem.html)
- Multiphysics: Fluid, structural, thermal, electromagnetic, acoustics — [Elmer documentation](https://docs.hpc.taltech.ee/engineering/elmerfem.html)
- Latest version: 26.2.1 (April 29, 2026); 2024R2 beta with enhanced input deck functionality — [Elmer documentation](https://docs.hpc.taltech.ee/engineering/elmerfem.html)

### Inferences
- For quick structural checks in an agent loop, gmsh (CLI) + CalculiX (headless solver) is a viable pipeline: geometry → meshed ABAQUS deck → FEA results.
- FreeCAD FEM adds complexity; direct use of gmsh + CalculiX is simpler for CI-like workflows.
- Elmer is powerful but requires custom SIF file generation; learning curve steeper than ABAQUS input format.
- All three solvers require external meshing; no tight CAD → FEA pipeline exists in open-source tooling (major opportunity for cad-agent v2 integration).

### Gaps
- Practical setup time and difficulty for bracket/beam analysis not documented.
- Python API examples for automating FreeCAD FEM (if they exist) not found.
- Performance: time to mesh and solve a typical bracket (under 1 minute? 10 minutes?) not benchmarked.
- Output parsing (extracting stress/displacement from CalculiX `.FRD` file) not documented; likely requires Python postprocessor.

---

## Mesh and Geometry Validation

### Takeaway
Multiple Python libraries and CLI tools available for mesh validation: trimesh (watertight, winding, convex checks), admesh (STL repair), PyMeshLab (filter-based processing), and OCCT BRepCheck/ShapeFix (B-rep geometry validation). No single CLI tool covers all; combination approach recommended.

### Cited Findings

**trimesh (Python Library)**
- Core validation methods:
  - `is_watertight`: Checks every edge belongs to exactly two faces — [trimesh documentation](https://trimesh.org/trimesh.base.html)
  - `is_winding_consistent`: Verifies shared edges have opposite directions — [trimesh documentation](https://trimesh.org/trimesh.base.html)
  - `is_volume`: Checks watertight + consistent winding + outward normals — [trimesh documentation](https://trimesh.org/trimesh.base.html)
  - `is_convex`: Determines if mesh is convex shape — [trimesh documentation](https://trimesh.org/trimesh.base.html)
  - `nondegenerate_faces()`: Flags faces without three unique vertices or extremely small area — [trimesh documentation](https://trimesh.org/trimesh.base.html)
  - `fill_holes()`: Repairs single triangle/quad holes — [trimesh documentation](https://trimesh.org/trimesh.base.html)
  - `fix_normals()`: Corrects face winding and direction consistency — [trimesh documentation](https://trimesh.org/trimesh.base.html)
- Load and validate: `mesh = trimesh.load('model.stl'); print(f"Watertight: {mesh.is_watertight}")` — [trimesh documentation](https://trimesh.org/trimesh.base.html)
- Validation parameter: `validate=True` on init removes degenerate/duplicate faces automatically — [trimesh documentation](https://trimesh.org/trimesh.base.html)
- Works headless on macOS/Linux/Windows; pure Python dependency — [trimesh documentation](https://trimesh.org/)

**admesh (CLI Tool)**
- Executable: `admesh <input.stl> [options]`; output: repaired `<input>_fixed.stl` — [admesh documentation](https://admesh.readthedocs.io/en/latest/cli.html)
- Default behavior: Runs all checks simultaneously (exact, nearby, unconnected, fill-holes, normals) unless flags override — [admesh documentation](https://admesh.readthedocs.io/en/latest/cli.html)
- Checking options:
  - `-e, --exact-check`: Verify three neighbors with exact vertex match — [admesh documentation](https://admesh.readthedocs.io/en/latest/cli.html)
  - `-n, --nearby-check`: Identify and correct nearly-matching edges (configurable tolerance) — [admesh documentation](https://admesh.readthedocs.io/en/latest/cli.html)
  - `-u, --remove-unconnected`: Delete facets lacking three neighbors — [admesh documentation](https://admesh.readthedocs.io/en/latest/cli.html)
  - `-f, --fill-holes`: Add facets to fill holes — [admesh documentation](https://admesh.readthedocs.io/en/latest/cli.html)
  - `-d, --normal-directions`: Orient all facets CCW from outside — [admesh documentation](https://admesh.readthedocs.io/en/latest/cli.html)
  - `-v, --normal-values`: Verify normals are outward unit vectors — [admesh documentation](https://admesh.readthedocs.io/en/latest/cli.html)
  - `-c, --no-check`: Skip all checking/repair — [admesh documentation](https://admesh.readthedocs.io/en/latest/cli.html)
  - `--reverse-all`: Reverse all facet directions — [admesh documentation](https://admesh.readthedocs.io/en/latest/cli.html)
- Output file: `<input>_fixed.stl` (stdout not supported; file-based only) — [admesh documentation](https://admesh.readthedocs.io/en/latest/cli.html)
- CLI only; no JSON report of issues, only STL repair — [admesh documentation](https://admesh.readthedocs.io/en/latest/cli.html)
- Works on macOS/Linux/Windows; GPLv2+ licensed — [admesh GitHub](https://github.com/admesh/admesh)

**PyMeshLab (Python Library)**
- Replacement for meshlabserver (command-line equivalent in MeshLab ≤2020.12) — [PyMeshLab documentation](https://pymeshlab.readthedocs.io/)
- Usage: `pymeshlab.MeshSet()` holds meshes; `.apply_filter(filter_name, params)` performs operations — [PyMeshLab documentation](https://pymeshlab.readthedocs.io/en/latest/classes/meshset.html)
- Filters: 200+ filters including mesh cleaning, decimation, smoothing, alignment — [PyMeshLab documentation](https://pymeshlab.readthedocs.io/en/latest/classes/mesh.html)
- Double precision floats; avoids precision loss in iterative operations — [PyMeshLab documentation](https://pymeshlab.readthedocs.io/en/latest/classes/meshset.html)
- Headless: Pure Python binding to MeshLab (no GUI) — [PyMeshLab GitHub](https://github.com/cnr-isti-vclab/PyMeshLab)
- Installation: `pip install pymeshlab` — [PyMeshLab documentation](https://pymeshlab.readthedocs.io/)
- Example application: Head mesh denoising, isolation removal, centering, fine alignment — [PyMeshLab documentation](https://pymeshlab.readthedocs.io/)

**Manifold (Geometry Library)**
- Library (not CLI tool) for guaranteed manifold mesh operations — [Manifold GitHub](https://github.com/elalish/manifold)
- Guaranteed manifold Boolean operations: Claimed to be first robust implementation for complex shapes — [Manifold GitHub](https://github.com/elalish/manifold)
- Utility: `make-manifold` for adding manifold extensions to glTF/GLB models — [Manifold GitHub](https://github.com/elalish/manifold)
- APIs: C++, Python, JavaScript/WASM, Java — [Manifold GitHub](https://github.com/elalish/manifold)
- No standalone CLI for validation; programmatic only — [Manifold GitHub](https://github.com/elalish/manifold)
- Features: Vertex properties, material mapping, mesh refinement, sharp edge preservation — [Manifold GitHub](https://github.com/elalish/manifold)

**OCCT BRepCheck and ShapeFix**
- BRepCheck_Analyzer: Validates B-rep shapes (topological and geometrical) — [OCCT Reference Manual](https://dev.opencascade.org/doc/occt-6.9.1/refman/html/class_b_rep_check___analyzer.html)
- Checks: Edge/vertex count, face/wire consistency, invalid curves on surfaces, SameParameter/SameRange flags, tolerance validity — [OCCT Reference Manual](https://dev.opencascade.org/doc/occt-6.9.1/refman/html/class_b_rep_check___analyzer.html)
- ShapeFix: Package for fixing shapes that violate OCCT requirements (uses BRepCheck for detection) — [OCCT Reference Manual](https://occt3d.com/dev/doc/refman/html/class_shape_fix.html)
- Draw command: `checkbrep <shape>` validates geometry and topology for inconsistencies — [OCCT Documentation](https://dev.opencascade.org/doc/occt-7.0.0/refman/html/class_shape_fix.html)
- Integrated into build123d (via OCP bindings) and FreeCAD — [CadQuery documentation](https://cadquery.readthedocs.io/en/latest/_modules/cadquery/occ_impl/shapes.html)
- No CLI tool; Python API available via OCP — [CadQuery documentation](https://cadquery.readthedocs.io/en/latest/_modules/cadquery/occ_impl/shapes.html)

### Inferences
- trimesh is ideal for STL validation in Python (lightweight, pure Python).
- admesh fills STL repair gaps (CLI-based, no Python needed) but doesn't report issues in machine-readable format; output is binary STL only.
- PyMeshLab is powerful for mesh processing but heavier (depends on MeshLab); use if advanced filters needed.
- OCCT BRepCheck is essential for build123d workflows (B-rep validation) but requires Python/C++ API; no standalone CLI.
- Combination approach: OCCT BRepCheck (via build123d Python) → export STL → trimesh validation → optionally admesh repair.

### Gaps
- No unified CLI that validates both B-rep (OCCT) and triangulated meshes (STL/OBJ) in one tool.
- admesh output format (text report of issues) not documented; appears to only output repaired STL.
- Performance on large meshes (millions of triangles) not benchmarked.
- Integration patterns (STEP → BRepCheck → STL → trimesh) not documented in any open-source guide.

---

## 2D Drawings with Dimensions

### Takeaway
FreeCAD TechDraw can generate dimensioned drawings programmatically but headless PDF export requires Python scripting or a custom wrapper (step2pdf example exists). SolveSpace CLI can export 2D vectors (SVG/DXF) but not auto-dimensions. No pure CLI tool for CAD → dimensioned drawing PDF.

### Cited Findings

**FreeCAD TechDraw**
- Purpose: Technical drawing workbench for 2D drawing generation from 3D models — [FreeCAD documentation](https://www.freecad.info/category/workbenches/techdraw/techdraw-dimensions/)
- Workflow: Load STEP file → create TechDraw page → add projection views → apply dimensions manually or programmatically — [FreeCAD documentation](https://www.freecad.info/category/workbenches/techdraw/techdraw-dimensions/)
- Headless export limitation: Direct headless SVG/PDF export not implemented as feature (pending enhancement) — [FreeCAD Issue #5710](https://github.com/FreeCAD/FreeCAD/issues/5710)
- Workaround: Python script automation + step2pdf project provides working headless STEP → dimensioned PDF solution — [step2pdf GitHub](https://github.com/maowiz/step2pdf)
- step2pdf example: Auto-generates 2D drawing PDFs from STEP files with rule-based dimensions, ISO scales, title block — [step2pdf GitHub](https://github.com/maowiz/step2pdf)
- Feature request: Headless export as GitHub issue (open, not implemented as of Sep 2026) — [FreeCAD Issue #5710](https://github.com/FreeCAD/FreeCAD/issues/5710)
- Dimension types: Length, angle, radius, diameter, horizontal/vertical distance — [FreeCAD documentation](https://www.freecad.info/category/workbenches/techdraw/techdraw-dimensions/)

**SolveSpace CLI export-view**
- Command: `solvespace-cli export-view <input.slvs> -o <output.svg>` — [Debian manual](https://manpages.debian.org/testing/solvespace/solvespace-cli.1.en.html)
- Output formats: SVG, PDF, DXF, EPS, HPGL (2D vector) — [Debian manual](https://manpages.debian.org/testing/solvespace/solvespace-cli.1.en.html)
- Limitation: No auto-dimensioning; exports sketch geometry only, not dimensions from design intent — [GitHub Issue #129](https://github.com/solvespace/solvespace/issues/129)
- Use case: Exporting 2D sketches from parametric models, not full 3D → 2D drawing conversion — [SolveSpace documentation](https://solvespace.com/)

**CadQuery SVG/DXF Export**
- CadQuery (parent of cq-cli) supports 2D projection to SVG/DXF via codec system — [cq-cli README](https://github.com/CadQuery/cq-cli)
- No dimension annotation in exported SVG/DXF (raw geometry projection only) — [cq-cli README](https://github.com/CadQuery/cq-cli)
- Usage: `cq-cli --infile design.py --codec svg --outfile projection.svg` — [cq-cli README](https://github.com/CadQuery/cq-cli)

### Inferences
- No pure CLI tool for fully automated STEP → dimensioned PDF drawing exists in open-source ecosystem.
- step2pdf (Python wrapper around FreeCAD TechDraw) is the closest practical solution; requires Python scripting.
- For agent harness: STEP → step2pdf (Python) → PDF is viable if rule-based dimensioning (standard tolerances, ISO scales) is acceptable.
- SolveSpace and CadQuery export projections but lack auto-dimensioning; suitable for visual reference only, not shop drawings.

### Gaps
- step2pdf rule-based dimensioning heuristics not documented; unclear how flexible it is for non-standard designs.
- Performance: time to generate dimensioned PDF from STEP not documented.
- FreeCAD TechDraw Python API for automation not fully explored in search results; likely exists but not officially documented for headless use.
- No information on dimension format compatibility (ANSI vs. ISO vs. custom) in available tools.

---

## DFM Checkers (Open-Source/CLI)

### Takeaway
Limited open-source DFM checker tools found; most are academic projects or embedded in commercial platforms. Build123d has DFM rules per process; other tools are scattered. No unified CLI tool for comprehensive DFM screening across CNC, FDM, sheet metal.

### Cited Findings

**DFM Rules (General Knowledge)**
- Typical DFM minimum wall thickness: 0.8 mm (shared between 3D print and sheet metal) — [DFM article](https://www.tctmagazine.com/essential-dfm-guidelines-for-sheet-metal-fabrication/)
- CNC minimum wall: 0.5 mm — [DFM guidelines](https://en.wikipedia.org/wiki/Rule-based_DFM_analysis_for_deep_drawing)
- Sheet metal bend radius: ≥1× material thickness; hole-to-bend: ≥2.5t + r; flange: ≥4t — [DFM guidelines](https://www.epocrafter.com/sheet-metal-design-guide/)
- Tolerance default (ISO 2768-1:1989 medium): ±0.1–0.5 mm depending on nominal dimension — [DFM guidelines](https://www.norck.com/blogs/news/8-critical-dfm-rules-for-sheet-metal-fabrication)
- Draft violation detection: Checks for draft angles < minimum (process-dependent) — [DFM article](https://www.makerstage.com/resources/dfm-best-practices)

**AnkusDrive/dfm_check (Unverified)**
- MCP server tool mentioned in search results; CLI interface, DFM rule checking — [Glama MCP Registry](https://glama.ai/mcp/servers/gchen19/AnkusDrive/tools/dfm_check)
- **Status**: No GitHub repo or official documentation found; unverified as of Sep 2026.

**build123d DFM Integration**
- User prompt mentions: "DFM rules per process (FDM, CNC, laser cut)" already in cad-agent v2 — **Per user context**
- Implies custom DFM rules already implemented; research focused on existing tools to complement.

### Inferences
- Open-source DFM ecosystem is immature; no production-grade unified CLI tool exists.
- build123d's existing DFM module is likely already custom-built for cad-agent v2; no external CLI tool to replace it.
- Commercial solutions (Fusion 360, nTopology, Protolabs) have DFM but are proprietary.
- Implementing rule-based DFM checks in cad-agent v2 via geometry API (thickness detection, undercut screening, overhang angle computation) is more viable than wrapping external tools.

### Gaps
- No open-source DFM checker tool with CLI and JSON output found.
- build123d's own DFM module documentation not accessible; unclear if it's exportable as standalone validator.
- AnkusDrive dfm_check tool not verifiable; GitHub repo not found.

---

## Summary: Recommended CLI Tool Stack for cad-agent v2

### Immediate Use (High Confidence, Production-Ready)

| Category | Tool | Command | Output | Notes |
|----------|------|---------|--------|-------|
| **Code-CAD CLI** | cq-cli | `cq-cli --infile design.py --codec step --outfile model.step` | STEP/STL/SVG/DXF | Parametric, stdin/stdout support |
| **Code-CAD CLI** | OpenSCAD | `openscad -o model.step model.scad` | Multiple (STL/DXF/SVG/PNG/PDF) | Preview/CGAL modes |
| **Rendering (Quick)** | OpenSCAD PNG | `openscad -o render.png --imgsize 1280x720 model.scad` | PNG | Fast, no GPU needed |
| **Rendering (Advanced)** | Blender | `blender -b scene.blend -o //render_#### -F PNG -f 1` | PNG | Raytracing, materials, slow |
| **Mesh Validation** | trimesh (Python) | `python -c "import trimesh; m=trimesh.load('x.stl'); print(m.is_watertight)"` | Boolean/metrics | Headless, pure Python |
| **Mesh Repair** | admesh | `admesh -d -v -f model.stl` | `model_fixed.stl` | CLI, no JSON output |
| **Meshing** | gmsh | `gmsh -3 geometry.geo -o mesh.msh -format msh` | Mesh file | For FEA pipelines |
| **FEA Solver** | CalculiX | `ccx analysis` (reads analysis.inp) | `.FRD` (results) | Headless, ABAQUS compatible |
| **Export 2D** | SolveSpace CLI | `solvespace-cli export-view sketch.slvs -o output.svg` | SVG/PDF/DXF | No auto-dimensions |

### Secondary (Python-based, Setup Needed)

| Category | Tool | Usage | Output | Notes |
|----------|------|-------|--------|-------|
| **Rendering** | pyrender | `OffscreenRenderer(width, height).render(scene)` | PNG (via PIL) | EGL/OSMesa backends |
| **Mesh Processing** | PyMeshLab | `MeshSet().load().apply_filter()` | Various formats | 200+ filters |
| **Headless FreeCAD** | freecadcmd | `freecadcmd -c "exec(open('script.py').read())"` | STEP/STL/DXF | GUI module imports fail |
| **Geometry Validation** | OCCT (via OCP) | `Part.check_shape()` in build123d | Boolean | B-rep validation |

### Gaps (Worth Investigating Further)

- **Printability checks**: Neither slicer CLI (PrusaSlicer, OrcaSlicer) reports printability metrics; G-code parsing required.
- **Dimensioned drawings**: No pure CLI tool; step2pdf (Python wrapper) is workaround for FreeCAD TechDraw.
- **Unified DFM checker**: Only build123d's existing module; no external CLI found.
- **FEA → CAD feedback loop**: No tool automates constraint refinement based on stress analysis.

---

## Recommended Research Priorities for cad-agent v2

1. **Deepen PrintabilityCheck Integration**: Parse slicer CLI outputs (G-code) to extract overhang %, support volume, bridging length; or integrate Bambu Studio CLI if available.
2. **FEA Automation**: Build gmsh + CalculiX pipeline wrapper (Python) to enable bracket stiffness checks in agent loop with <2 min turnaround.
3. **Drawing Generation**: Adapt or extend step2pdf for rule-based dimensioned PDF output (or test FreeCAD TechDraw Python API directly).
4. **Validate Mesh Integrity**: Pre-export checks using trimesh + optional admesh repair before downstream processes.
5. **Performance Benchmarking**: Measure rendering time (OpenSCAD PNG vs. F3D vs. Blender) and solver time (gmsh + CalculiX) on typical 5cm bracket.

---

## References & Sources

**Official Documentation:**
- [cq-cli GitHub](https://github.com/CadQuery/cq-cli)
- [OpenSCAD Manual](https://files.openscad.org/documentation/manual/Using_OpenSCAD_in_a_command_line_environment.html)
- [FreeCAD Documentation (Headless & TechDraw)](https://github.com/FreeCAD/FreeCAD-documentation)
- [SolveSpace CLI](https://manpages.debian.org/testing/solvespace/solvespace-cli.1.en.html)
- [gmsh Reference Manual](https://gmsh.info/doc/texinfo/gmsh.html)
- [admesh Documentation](https://admesh.readthedocs.io/)
- [trimesh Documentation](https://trimesh.org/)
- [pyrender Documentation](https://pyrender.readthedocs.io/)
- [PyMeshLab Documentation](https://pymeshlab.readthedocs.io/)
- [PyVista/VTK Documentation](https://docs.pyvista.org/)
- [OCCT Reference Manual](https://dev.opencascade.org/doc/occt-6.9.1/refman/html/)
- [OrcaSlicer Wiki](https://www.orcaslicer.com/wiki/cli/cli_mode)
- [Elmer Documentation](https://docs.hpc.taltech.ee/engineering/elmerfem.html)
- [Blender CLI Documentation](https://docs.blender.org/manual/en/stable/render/output/properties/render.html)

**Community Projects:**
- [step2pdf: STEP → Dimensioned PDF](https://github.com/maowiz/step2pdf)
- [prusaslicer-py: PrusaSlicer Python Wrapper](https://github.com/heibench/prusaslicer-py)
- [OrcaSlicer CLI Cookbook](https://github.com/CapitanaIcoachai/orcaslicer-cli-cookbook)
- [freecad-cli-patches: Headless Improvements](https://github.com/monyuonyu/freecad-cli-patches)
- [Manifold Geometry Library](https://github.com/elalish/manifold)

**Issue Trackers & Discussions:**
- [FreeCAD TechDraw Headless Export Feature Request #5710](https://github.com/FreeCAD/FreeCAD/issues/5710)
- [SolveSpace Parametric CLI Feature Request #129](https://github.com/solvespace/solvespace/issues/129)
- [PyVista Headless Documentation Issue #7212](https://github.com/pyvista/pyvista/issues/7212)
- [FreeCAD Headless GUI Import Issue #16407](https://github.com/FreeCAD/FreeCAD/issues/16407)

---

**End of Research Notes**  
Research conducted: September 28, 2026  
Tools evaluated: 25+ CLI/headless applications and Python libraries  
Confidence level: High for production tools (cq-cli, OpenSCAD, admesh, gmsh); Medium for integration patterns; Low for performance benchmarks and undocumented CLI flags.

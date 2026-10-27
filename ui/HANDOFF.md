# Handoff: the cad-agent workbench and the FreeCAD fix list (2026-10-23)

Goal: the workbench UI in `ui/` looks and behaves like FreeCAD main 3160daf1e2b6, over the `cad` CLI that the agent shares. FreeCAD's code and icons may be copied (LGPL, with the notices in NOTICE and ui/NOTICE). `ui/PARITY.md` records what is done and every deliberate difference; `docs/FREECAD_AUDIT.md` is the comparison with FreeCAD's code that the fix list below comes from.

## State (main, 2026-10-22; CI 1732 passed)
- Release 0.2.0 (step 6, machine scale) and everything after it is on main:
  - the UI round: NaviCube placement, face clicks always upright, cube and camera in step, the view keys 0 to 6;
  - the wiring check: `ui/scripts/wirecheck.mjs` clicks all 920 controls; 802 work, 114 are greyed with a reason, 4 are human-only, 0 broken;
  - the approved renders of `tests/fixtures/mini_machine` and `mini_gantry`, so both fixtures verify PASS on CI.
- The FreeCAD fix list: items 1 to 4 below; 5 to 9 under "Done 2026-10-23":
  1. Licence notices: NOTICE, THIRD_PARTY_LICENSES and ui/NOTICE; an SPDX line on every ui/src file; notices for the ports outside ui/ (geom.py mass_properties, dxf.py, appcache.py); the bundle's own notices, written by `ui/scripts/licenses.mjs`; the CC-BY material credits. Guarded by tests/test_licenses.py.
  2. Look:
     - how a selected face is drawn (diffuse plus emissive, as FreeCAD does);
     - tree and property view shading, from QColor::darker/lighter;
     - dock widths, toolbar height, the tab close buttons;
     - the Report view's font and colours;
     - Start page cards and tooltip style;
     - Home: Top until the Navigation page is saved, as FreeCAD does.
  3. Behaviour:
     - perspective Fit All (R/tan, as measured in FreeCAD);
     - Align to Selection, a port of alignToSelection;
     - the OS double-click interval;
     - the Mac keys (Delete, Recompute, Previous Window);
     - the µA unit, the tree's full context menu, and appcache's calendar days.
     
     Fit Selection already matched: FreeCAD fits the whole part, not the element.
  4. Preferences: every page is drawn from FreeCAD's own .ui files (`ui/src/qtform.tsx`; `ui/scripts/uigen.py` writes `ui/src/uiforms.ts`). Greyed settings show FreeCAD's defaults, and Reset All restores a fresh profile.

## The formula engine (item 5): done, 2026-10-23
- `ui/src/expr.ts`, `expr-grammar.ts` (Expression.y's LALR tables, written by `ui/scripts/exprgen.py`) and `expr-py.ts` (Python's values and operators) port FreeCAD's expression language; results are Python values and errors FreeCAD's exception classes and messages.
- `cd ui && python3 scripts/exprdiff.py` (strict): 0 of 75,558 differ from FreeCAD 26.3; 251 Matrix/Placement/Rotation cases are set aside. Three new random seeds recorded on the Linux build differ only in C library message texts.
- `tests/test_expr_parity.py` runs 1,974 stored answers on CI through `tests/golden/expr/engine.mjs`. After any change to the engine's sources, rebuild both with `python3 ui/scripts/exprdiff.py --emit-engine tests/golden/expr/engine.mjs --emit-fixture tests/golden/expr/cases.json` (needs only ui/node_modules).
- Deliberate differences are in PARITY.md, "The formula engine": no Matrix/Placement/Rotation, no int32 cast (`QUIRKS.int32Cast`, on only in the comparison), size limits instead of a frozen tab.
- The rewrite came from the branch `fc-formulas-rewrite-wip`. It was reviewed and fixed (the owner's name was passed through, int parameters became ints, size and depth guards were added, dead code removed) and merged as `fc-formulas-engine`. The old branch can be deleted.

## Done 2026-10-23, and what is left
Items 5 to 9 of the fix list are done, each checked against the real FreeCAD (the Linux build of 3160daf1e2b6, headless or under xvfb):
- 5. Formulas: above.
- 6. Shop outputs. The DXF around the entities is FreeCAD's (`ui/scripts/dxfdiff.py`). Drawings draw the visible smooth edges as TechDraw does (`ui/scripts/hlrdiff.py`: 65 of 65 edges in 15 views). The BOM's "mirrored line" finding was wrong for the build: FreeCAD's isObjMirrored never reads a link's Scale, and bom.py already matched (`ui/scripts/bomdiff.py`, 6 of 6).
- 7. The NaviCube is drawn as SoNaviCube draws it (`ui/src/navicube3d.ts`; `ui/scripts/navishots.py`: the same pixels in 24 shots but the label font).
- 8. Leftovers:
  - Tooltip content (`ui/scripts/fctips.py` writes `ui/src/fctips.ts` from the running FreeCAD).
  - Start page Examples, the tabs' icons and "*", the lit selected face, and tree-hover preselection on top. HeadlightColor needed nothing.
  - The Custom default camera orientation (`ui/scripts/ourscamera.mjs`, 20 of 20). Align to a curved face (264 of 264).
  - Qt's spare-room rules in Preferences.
- 9. Grader gaps: `[[holes]]` and `[[shaft_fit]]`, and what a `[[clearance]]` `max_mm` bounds is now documented.

Also done later on 2026-10-23 (main cd8fa2c, CI green):
- 5.9 Arrow-key panning: FreeCAD's int-truncated aspect, measured in the real FreeCAD at seven sizes (`ui/scripts/arrowpan_fc.py`; navcheck 92).
- keycheck: 62 of 62 on Linux (it needs projects/arduino_car served, and presses F5 for Std_Refresh off a Mac).
- Grader: `[[holes]]` `through`, `depth_mm`, `depth_tol_mm` (depth to the drill point's shoulder, as FreeCAD's Hole Depth);
  `[[shaft_fit]]` `fit = "H7/g6"` and `nominal_mm` (cad_agent/iso286.py, IT5-IT11 up to 500 mm). A fit stays the diameter
  difference, as ISO 286 and every CAD tool count it.
- Browser checks on the merged code: cubecheck 378/378, navcheck 92/92, keycheck 62/62; wirecheck's customize, start, prefs
  and Placement sections clean locally. On Linux, wirecheck's "Cmd+click adds a part" fails by platform (Meta vs Ctrl), on old main too.

## Now (2026-10-24): editing in the app, as FreeCAD does
Juan's call: the app should edit like FreeCAD, edits written back as Python, Sketcher and Pad/Pocket first.
The plan and its order are docs/EDITING_PLAN.md. Steps 1 to 4 are in main (4e73c0c, CI green, 1954 passed):
- Solver: FreeCAD's PlaneGCS vendored unchanged in ui/planegcs/, Sketch.cpp's mapping ported (sketch.cpp, api.cpp),
  native for Python (cad_agent/planegcs.py; `ui/planegcs/build.sh native`, PLANEGCS_TOOLCHAIN with Eigen 5.0.0,
  which is what FreeCAD 26.3 is built with) and wasm for the page (ui/planegcs/dist). Native equals freecadcmd bit
  for bit on 971 sketches (tests/golden/sketcher); wasm differs only where FreeCAD's own answer is rounding-sensitive.
  FreeCAD orders unknowns by memory address, so under-constrained sketches are not repeatable in FreeCAD itself.
- Part files: cad_agent/feature.py (FEATURES = [Sketch, Pad, Pocket], Body), feature_edit.py (read/apply in place);
  57 bodies equal FreeCAD's volume/area/box/centre (tests/golden/feature). Differences: refine (UnifySameDomain),
  face order after fuses in 11 cases, crossing wires refused.
- Tree and editing: `cad feature ...`, /api/<slug>/features, Body tree, Pad/Pocket panels, tip, move, rename,
  delete, undo (editcheck 59 ok vs ui/scripts/fcedit.json).
- Sketcher UI: edit mode, geometry and constraint tools, drag, solver messages (sketchcheck 56/57 vs
  ui/scripts/sketchref.json; c-parallel is FreeCAD's GUI not repeating itself).
Each check's known differences are in ui/PARITY.md (PartDesign, Sketcher).
Step 5, round 2 (five parallel branches) is all in main (95ad35c, CI green, 5026 passed), on one seam,
cad_agent/feature_kw.py's KwFeature:
- pd-transform: Mirrored, Linear/PolarPattern, MultiTransform, 16 primitives (transformcheck 174 ok, 3 known).
- pd-dressup: Fillet, Chamfer, Draft, Thickness, edge/face picking, renumbering follow-up (dressupcheck 115 ok, 4 known).
- pd-revolve: Revolution, Groove, Hole with FreeCAD's tables (revolvecheck 258 ok, 1 known).
- pd-attach: Attacher (cad_agent/attacher.py, 1818 placements = FreeCAD), sketches on faces/datums, Part datums,
  external geometry, attached primitives (attachcheck 89 ok).
- sketcher-geom: ellipses, conic arcs, B-splines in PlaneGCS/feature.py/Sketcher; Trim, Split, Extend, sketch
  Fillet/Chamfer (522 conic and 362 sketchops goldens; sketchcheck 74/75, c-parallel known). editcheck 59 ok, 19 known.
- CI builds ui/planegcs native before the tests (feature tests solve sketches before test_planegcs did).
  Locally, rebuild it (`ui/planegcs/build.sh native`) after a merge that changes api.cpp/sketch.cpp.
Step 5, round 3 (six branches) is all in main (7526c0c, CI green, 6977 passed, 2026-10-25):
- pd-sweep: Additive/Subtractive Loft, Pipe, Helix (71 goldens; sweepcheck 302 ok).
- pd-kernel: FreeCAD's RefineModel (cad_agent/refine.py) and booleans (topo_boolean.py) for every feature, closing
  the face-count/order differences; taper, Common, Scaled, Start Reference (kernelcheck 38 ok). Left: Mirrored puts
  the copy's faces first in 5 transform goldens; refine.py merged 2 edges more than FreeCAD in 2 Part cuts (fixed 2026-10-27:
  FreeCAD keeps conic edges from BRepLib_FuseEdges on OCCT 8 too, collectConicEdges).
- sketcher-curves: B-spline by knots and its tools, trim/split on B-splines, fillet between curves, Offset, Carbon
  Copy, projected conics/B-splines; OCCT's numbers via `cad feature sketchkernel` (408 goldens). Left: solver fails to
  converge on wide B-splines by knots; Carbon Copy copies values, not expressions.
- sketcher-ovp: on-view parameters and the Tool Parameters box, Symmetry/Translate/Rotate/Scale/Array/Clone/Copy,
  Constraints/Elements panels, Preferences > Sketcher; sketchcheck in 9 suites, 313/317 (4 known). The unfinished
  out-of-edit commands (Validate/Map/Reorient/Mirror/Merge sketches) are on origin/sketcher-outofedit-wip, not merged.
- Next: Assembly joints (Assembly workbench, its solver), then the leftovers in PARITY.md (ShapeBinder, Part's 3D
  picking and attachment, Part Scale/Face/Ruled/Reverse, pattern spacing labels, Sketcher text and visual layers).
- DeepSeek's handoff (ShapeBinder, Part attachment and 3D picking, Part Scale/Face/Ruled/Reverse, pattern spacing
  labels, Sketcher visual layers), reviewed and fixed, is in main as a2fffac (2026-10-26). DeepSeek works in its own
  worktree on ds/handoff-1025 and commits there only; the lead reviews and squashes its work into main.
- Step 5, round 4 (2026-10-26): Assembly (below) is in main; Sketcher text and the out-of-edit sketch commands are on
  branch sketcher-text. Each golden folder has a cases.py: load it under its own name (importlib, as the tests do),
  never `sys.path.insert` + `from cases import`, or it shadows another folder's in the full run.
- pd-last (2026-10-27): PartDesign's last commands, each a KwFeature: Involute Gear and Sprocket (cad_agent/feature_gear.py,
  a profile as a sketch is), Defeaturing (feature_defeaturing.py), Sub-Shape Binder (feature_subbinder.py), Boolean and Clone
  (feature_boolean.py, `cad feature clone`): a Body is a part module, so a Boolean's tool or a Clone's source is another part's
  name (docs/EDITING_PLAN.md, "Several Bodies"). 52 freecadcmd documents in tests/golden/pdlast (`make.py [CASE ...]`); the page
  (src/pd_last.tsx, src/pd_boolean.tsx, Defeaturing in pd_dressup.tsx) held by scripts/pdlastcheck.mjs to scripts/fcpdlast.json
  (scripts/fcpdlast.py): 171 ok, 4 known. The Shaft Design Wizard is cut. refine.py now keeps conic edges from FuseEdges.
- pd-pick (2026-10-25): every panel's reference picks in the 3D view through FreeCAD's gates (src/pd_pick.tsx), datums
  as references everywhere (cad_agent/feature_refs.py, tests/golden/pick), Pad ReferenceAxis, Std_Delete that breaks
  links as FreeCAD (feature_delete.py), PartDesign_Plane/Line/Point/CoordinateSystem, the split primitive buttons,
  Multi-Transform in the tree menu; scripts/pickcheck.mjs vs scripts/fcpick.json. PARITY.md "Picking in the 3D view".
- Browser checks must use scratch projects only (a check once wrote a Plate part into projects/arduino_car).
- Part workbench (branch part-wb, 2026-10-25): Part objects are OBJECTS beside FEATURES (docs/EDITING_PLAN.md, "Part
  workbench objects in a part file"); cad_agent/feature_part*.py (primitives, booleans, split/join/compound tools,
  Extrude incl. taper and every face maker, Revolve, Mirror, Fillet, Chamfer, Loft, Sweep, Offset, Offset2D, Thickness,
  Projection on surface), feature_edit_part.py, `cad feature new --document`; 211 freecadcmd documents in
  tests/golden/part (`make.py [split|sweep]`), 1,368 checks. UI: src/part_wb.tsx, part_tasks.tsx, part_props.ts
  (scripts/partprops.py), checked by scripts/partcheck.mjs against scripts/fcpart.json (scripts/fcpart.py): 392 ok,
  22 known (2026-10-25; after the merge of editing-plan b855cc3 + 71cd370 the touched sections: booleans 44 ok / 2 known,
  panels, props and undo all ok). Cut: Shape
  builder and Cross-sections (static Part::Feature copies), Scale, Face from wires, Ruled surface, Reverse; see PARITY.md.
  partcheck's output reaches a log only at its end (run it as `node scripts/partcheck.mjs > log`; it takes ~40 minutes on
  a loaded box).
- Assembly workbench (branch assembly, 2026-10-26): FreeCAD's OndselSolver vendored unchanged in ui/ondsel/upstream (the
  submodule revision of 3160daf1e2b6, 4be80eef02a3), AssemblyObject.cpp's solve ported in front of it (ui/ondsel/assembly.cpp,
  a C API taking JSON), native (`ui/ondsel/build.sh native`, cad_agent/ondsel.py; CI builds it) and wasm (ui/ondsel/dist,
  src/ondsel.ts). The Assembly is assembly.py's ASSEMBLY list (docs/EDITING_PLAN.md, "Assembly in a part file"):
  cad_agent/assembly_wb.py (Link, GroundedJoint, Joint; JointObject.py's presolve and accept), assembly_jcs.py
  (findPlacement), assembly_edit.py, `cad assembly ...`, /api/<slug>/assembly; parts() is the solved assembly, so every gate
  reads it. 48 freecadcmd cases equal on both builds (tests/golden/assembly, `freecadcmd tests/golden/assembly/make.py`);
  the page (src/assembly_wb.tsx) checked by scripts/assemblycheck.mjs against scripts/fcassembly.json (scripts/fcassembly.py):
  124 ok, 0 FAIL. Cut: rigid groups, sub-assemblies, link arrays, exploded views, snapshots, simulation, the BOM object
  (PARITY.md "Assembly workbench"). Run assemblycheck with CAD_PYTHON set in a worktree without its own .venv.

TechDraw (branch techdraw, 2026-10-27): pages as techdraw/<Page>.py, `cad techdraw`, the workbench in the page (views,
projection groups, sections, dimensions, balloons, annotations, SVG/DXF/PDF). HLR numbering equals FreeCAD's; checks are
tests/test_techdraw_{golden,svg,edit}.py and ui/scripts/techdrawcheck.mjs; differences in ui/PARITY.md ("TechDraw workbench").

## Next (paused 2026-10-23)
1. ~~Hidden specs~~ (done 2026-10-23): `pinned_carrier` and `hotplate_standoffs` count their holes `through`, and
   `syringe_clamp` grades its bore with `[[shaft_fit]]`; tests/test_eval.py GAPS has the design each one catches.
   No brief gives a blind depth or an ISO fit class to grade (pinned_carrier quotes H7/F7 for reference only).
2. Grader choices left to Juan:
   - ~~`through` as a count filter~~ (decided 2026-10-23): it holds every hole of the size and axis, as FreeCAD's Hole Depth Type does,
     so "4 through" fails on a fifth blind hole too.
   - ~~ISO 286 c and s unchecked~~: every class FreeCAD's TechDraw Hole/Shaft Fit tool offers is checked against it (tests/golden/iso286;
     FreeCAD's own n6 is wrong over 160 mm, audit 5.14). JS/js are exactly ±IT/2.
3. Status bar height and toolbar widths: they come from the Mac's Qt style, so measure them on a Mac.
4. 5.1 Home (FREECAD_AUDIT.md): under way in another lane.
- Stays a deliberate difference: the spline re-fit in DXF export.
- VM checks: a full wirecheck on a spot n2-standard-4 runs past its 150 minutes with click timeouts (slowness, not code), and a
  timed-out job uploads nothing. Run wirecheck by `--only=` sections, one job each, or locally; the VM is fine for cubecheck and navcheck.

## The FreeCAD oracle on a Linux box
- Every comparison uses FreeCAD main 3160daf1e2b6, which is the weekly build `weekly-2026.09.30`.
- To install it on Linux:
  1. Download `FreeCAD_weekly-2026.09.30-Linux-x86_64.AppImage` from the FreeCAD/FreeCAD GitHub release of that tag, and check it against the release's `-SHA256.txt`.
  2. Unpack it with `--appimage-extract`.
  3. Run it headless with `squashfs-root/usr/bin/freecadcmd`; run the GUI tools under `xvfb-run -a -s "-screen 0 1600x1000x24"` with
     FREECAD_APP set to the unpacked folder: `fclaunch.py` (fcbehave.py, fcprefs.py, ...) then starts its `usr/bin/freecad` on X11.
- The look tools (`fcgui.py --platform cocoa`, `fcshots.py`, `fcmeasure.py`) read widget sizes from the Mac's Qt style. Qt's Linux style is not the same, so compare look on a Mac, or say which platform a number comes from.
- The browser checks need Node 20.19 with `npm ci` in ui/, and Playwright 1.59.1 with Chromium (`npx playwright install --with-deps chromium`). Point NODE_PATH at the folder that holds `playwright`.

## Pitfalls
- Never push a branch whose diff or commit messages hold a local path (/Users/..., /private/tmp/..., /home/...). Squash it clean first.
- Every branch rebuilds the bundle, so two UI branches merged together conflict in `cad_agent/workbench/next/`. Rebuild after the merge.
- cubecheck can lose one case under heavy load (a 0.001 mm focal point, a camera-up check). Rerun it before judging; the merged builds passed 378/378.
- agentcheck's "check options" step times out on the CPU renderer.
- keycheck rewrites the project's checks.json and out/gui.json, so run it on a copy.
- A comment edit in cad_agent/*.py changes `engine_hash`, so earlier verdicts go stale until they are verified again.
- Line numbers in older notes are off by the SPDX headers. FREECAD_AUDIT.md section 0.1 has the shift for each file.

## Testing without touching real projects
`cad serve` always includes the repo's own `projects/`. For UI tests, start the workbench with `serve.run([scratch_root])` from Python and set CAD_PREFS, CAD_WARM_DIR, CAD_RUNTIME_DIR and CAD_MACRO_DIR to scratch paths.

## How to check
- `cd ui && npx tsc -b --noEmit && npm run build` (the build goes to `cad_agent/workbench/next/`; commit it). Use Node 20.19 or newer (Vite 8, TypeScript 7): `/usr/local/bin/node` here is 20.6.1, where `tsc` will not load and `npm ci` quietly leaves out rolldown's native binding (navcheck then dies with "Cannot find native binding"); nvm has v20.19.0, so `PATH=~/.nvm/versions/node/v20.19.0/bin:$PATH`. A fresh worktree has no `ui/node_modules`: `npm ci` there.
- `node ui/scripts/navcheck.mjs`: 85 navigation checks (the double-click interval among them), needs only Node.
- While fixing: `.venv/bin/python tests/affected.py` runs only the test files that can see what changed since main (`--list` to see them). The full suite (`.venv/bin/python -m pytest -q`, 1732 tests; CI runs it in about 8 minutes) runs on GitHub CI for every push, which also runs `cad verify` on every folder of `tests/fixtures`: fixes collect on a `batch` branch, which is pushed every couple of hours and fast-forwards main once CI is green.
- keycheck on the Mac: Playwright comes with the miniconda Python install. Make a folder holding a symlink `playwright -> ~/miniconda3/lib/python3.13/site-packages/playwright/driver/package` and run `NODE_PATH=<folder> node ui/scripts/keycheck.mjs http://127.0.0.1:<port>/next/` against a scratch workbench (serve.run with the CAD_* variables above; a `cad-keycheck` entry in ~/ws/.claude/launch.json does this on port 8792). It presses undo and redo, so redo replays an edit another run undid, and Space and V, T leave the first part hidden and transparent in `out/gui.json`: give each run a fresh copy of the project. It launches Chromium on SwiftShader on purpose (see the flags in the script).
- The NaviCube: `NODE_PATH=<folder> node ui/scripts/cubecheck.mjs http://127.0.0.1:<port>/next/ [PROJECT]` (the same Playwright set-up as keycheck, against a scratch workbench on a copy of tests/fixtures; it only changes the view, and takes about seven minutes on SwiftShader). It runs every cube action from nine starting orientations (a face, edge and corner click, the arrows, both rolls, backside, home, double click, a drag, keys 0 to 6 and Rotate left and right), then the same on frames 170 ms apart, with no wait between actions, across a scene reload, a resize and a change of projection, in perspective, and for NaviRotateToNearest. The page reports itself through `CadView.probe()` (`cadui.getView().probe()`; it records draws only after `probe(true)`), and the expected orientations are written out from FreeCAD's NaviCube.cpp and Camera.cpp. Run it after any change to the cube, `nav.ts`'s animation or the draw hook.
- The NaviCube's look against the real FreeCAD, on Linux: `FREECAD_APP=<unpacked AppImage> NODE_PATH=<folder> .venv/bin/python ui/scripts/navishots.py OUT --url http://127.0.0.1:<port>/next/` (a scratch workbench; FreeCAD runs under xvfb-run, its NaviCube is OpenGL and so platform independent). It writes both sets of shots, side-by-side images and per-shot numbers (the docstring says which).
- The 3D view against the real FreeCAD (2026-10-21): `python3 ui/scripts/fcbehave.py OUT [--only fit,align,tree_menu,quickmeasure,...]` measures it (the camera after Fit All, Fit Selection and Align to Selection, the tree's context menu, QuickMeasure's messages, the double-click interval; `fcbehave_dump.py` is what runs inside it), then `NODE_PATH=<folder> node ui/scripts/oursselect.mjs URL PROJECTS_ROOT ours.json OUT/fcbehave.json` measures ours the same way on a scratch workbench (it adds the projects `probe` and `probeqm` to PROJECTS_ROOT) and prints where they differ; `--compare-only` compares files already written. Merge several `fcbehave.json` files into one for the comparison.
- Every control: `NODE_PATH=<folder> node ui/scripts/wirecheck.mjs [URL] [--only=SECTION,...]` lists every menu entry, button and panel control and clicks each enabled one (it starts its own scratch workbench when given no URL, and sets CAD_RENDER_BACKEND=numpy); a full pass takes about 90 minutes.
- Formulas: `cd ui && python3 scripts/exprdiff.py` compares `src/expr.ts` with FreeCAD 26.3's stored answers to 75,558 expressions (the script's docstring has every option; `--record`/`--fc` with FREECAD_APP set to an unpacked AppImage run the Linux FreeCAD).
- The laser DXF against FreeCAD: `FREECAD_APP=<FreeCAD> CAD_PYTHON=.venv/bin/python python3 ui/scripts/dxfdiff.py` (one part through both writers, every line compared, and FreeCAD reads ours back).
- Preferences against FreeCAD: `node ui/scripts/prefdump.mjs URL dump.json`, then `python3 ui/scripts/prefdiff.py dump.json` (fetches the .ui files once).
- Menus against FreeCAD: `python3 ui/scripts/fcgui.py` (FreeCAD's dump), `python3 ui/scripts/fcref.py <scratch project>`, then `node ui/scripts/menurun.mjs 'URL#<project>'`. 43 expected differences as of 2026-10-02 (PARITY.md's Menus note).
- Toolbar tooltips: `python3 ui/scripts/fctips.py` runs FreeCAD (FREECAD_APP: an unpacked AppImage under xvfb-run, or FreeCAD.app) and rewrites `ui/src/fctips.ts`, every command's menu text and tooltip; run it when ui/src names a new FreeCAD command.
- Side by side with the real FreeCAD (all of them start its GUI on the Mac's Qt platform with every window kept off the screen, and a temporary profile; one FreeCAD and one headless browser at a time): `fcshots.py OUT --scene <project>/out/scene.json` and `oursshots.mjs URL PROJECT OUT` take the same shots of both (the Start page, a part selected, the tree menu, the Report view, a tooltip, the Preferences pages); `fcbehave.py` and `oursbehave.mjs` compare the camera (standard views, Home, zoom, mouse drags); `fcmeasure.py` reads FreeCAD's own widget geometry (docks, toolbars, tabs, tree and property view, fonts, a fresh profile's parameters) and the colours of a selected, a preselected and a face-selected Part. The quick look pass of 2026-10-20 took its numbers from these and from FreeCAD's source at 3160daf1e2b6 (PARITY.md says which).
- `python3 ui/scripts/fcdiff.py` and `fcgui.py` need FreeCAD's weekly build at `~/.cad-agent/freecad/FreeCAD.app`. That's only on the owner's Mac, not in the cloud.
- To fetch FreeCAD sources: `https://raw.githubusercontent.com/FreeCAD/FreeCAD/3160daf1e2b6/<path>`.

## Rules
- Port line by line from FreeCAD and cite the source file in comments; note any deliberate difference in PARITY.md.
- Use free tools only, and build CLI-first, so the agent and the UI can do the same things.
- Use scratch copies of projects for tests, never real projects.
- Commit on a branch, then fast-forward main and push.

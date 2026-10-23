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

Left:
- Status bar height and toolbar widths: these come from the Mac's Qt style, so measure them on a Mac.
- 5.1 Home and 5.9 arrow-key panning (FREECAD_AUDIT.md).
- The spline re-fit in DXF export stays a deliberate difference.
- Open questions on the grader:
  - Should a fit be the gap per side or the diameter difference (now the diameter)?
  - Should there be ISO 286 fit classes?
  - Should `[[holes]]` tell through holes from blind ones?
  - No hidden spec uses the new kinds yet.

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

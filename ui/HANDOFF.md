# Handoff: FreeCAD-parity UI, and what comes next (2026-10-02)

Goal: the workbench UI in `ui/` looks and behaves like FreeCAD main 3160daf1e2b6, over the `cad` CLI that the agent shares. FreeCAD's code and icons may be copied (LGPL). `ui/PARITY.md` is the record of what's done.

## State (main, 2026-10-02)
- All menus, toolbars, keys, panels and navigation styles that apply here are done, and every Preferences page FreeCAD's resource.cpp registers is present (see PARITY.md), plus Tools > Customize (Toolbars, Macros), user shortcuts (Preferences > General > Keyboard), Expression Editor name completion, the pick radius, tree selection check boxes, and every command echoed to the console (ScriptToPyConsole).
- New CLI: `cad pref [KEY [VALUE]]` (MaxUndoSize, CacheLimit, CachePeriod; userprefs.py) and `cad cache [--clear]` (appcache.py). The page edits the same store over /api/prefs and /api/cache.
- `node ui/scripts/keycheck.mjs [URL]` presses all 62 default shortcuts in a running workbench and checks each ran (needs Playwright; point it at a scratch workbench only).

## Next (plan of 2026-10-02, after pulling b804ece on the Mac)
Checked on the Mac (2026-10-02): tsc clean, navcheck 72/72, pytest 374 passed (after fixing one Mac-only test: macOS caps a socket path at 104 bytes), keycheck 62/62 fired. Not yet run: the FreeCAD diffs.

On the Mac (these need FreeCAD or a real Claude Code install):
1. ~~Full health check~~ done 2026-10-02 (see above).
2. Compare the new Preferences pages with FreeCAD, label by label against each page's .ui at 3160daf1e2b6 (the Preferences dialog crashes offscreen, so compare the .ui files, as before): Light Sources, UI, Document, Keyboard, Cache, Advanced, Workbenches, PDF, Python General and Editor. Fix the differences and note any deliberate ones in PARITY.md. Re-run `fcgui.py` for menus, toolbars and shortcuts, since Customize and Keyboard changed them.
3. Try the plugin for real in a scratch folder: `/plugin marketplace add El-Guapo2024/cad-agent`, install it, and check that the SessionStart install puts `cad` on PATH, the cad skill and hooks fire on a small part, and `/cad-agent:workbench` opens. Juan runs the `/plugin` commands; Claude checks the result.

Then the product (PLAN_V2.md build order, steps 6–8). Recommended order:
4. Step 7 first, the eval set: about 10 small briefs, each with a hidden `spec.toml`, and a runner (`cad eval`) that scores them through `cad verify`. That way every later harness change is measured.
5. Step 6, machine scale: a parts library with vendor STEPs and sources, sub-assemblies, the heat, mass and deflection rules, and shop outputs (DXF, drawings, STL/3MF, BOM).
6. Step 8, the first real job: the one-machine layout (frame, gantry, dock, laser keep-out).

UI parity itself is done apart from step 2. Anything left is n/a by design (listed in PARITY.md).

## Testing without touching real projects
`cad serve` always includes the repo's own `projects/`. For UI tests, start the workbench with `serve.run([scratch_root])` from Python and set CAD_PREFS, CAD_WARM_DIR, CAD_RUNTIME_DIR and CAD_MACRO_DIR to scratch paths.

## How to check
- `cd ui && npx tsc -b --noEmit && npm run build` (the build goes to `cad_agent/workbench/next/`; commit it).
- `node ui/scripts/navcheck.mjs`: 72 navigation checks, needs only Node.
- `.venv/bin/python -m pytest -q`: 374 tests.
- keycheck on the Mac: Playwright comes with the miniconda Python install. Make a folder holding a symlink `playwright -> ~/miniconda3/lib/python3.13/site-packages/playwright/driver/package` and run `NODE_PATH=<folder> node ui/scripts/keycheck.mjs http://127.0.0.1:<port>/next/` against a scratch workbench (serve.run with the CAD_* variables above; a `cad-keycheck` entry in ~/ws/.claude/launch.json does this on port 8792).
- `python3 ui/scripts/fcdiff.py` and `fcgui.py` need FreeCAD's weekly build at `~/.cad-agent/freecad/FreeCAD.app`. That's only on Juan's Mac, not in the cloud.
- To fetch FreeCAD sources: `https://raw.githubusercontent.com/FreeCAD/FreeCAD/3160daf1e2b6/<path>`.

## Rules
- Port line by line from FreeCAD and cite the source file in comments; note any deliberate difference in PARITY.md.
- Use free tools only, and build CLI-first, so the agent and the UI can do the same things.
- Use scratch copies of projects for tests, never real projects.
- Commit on a branch, then fast-forward main and push.

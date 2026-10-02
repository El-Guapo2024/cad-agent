# Handoff: FreeCAD-parity UI (2026-10-01)

Goal: the workbench UI in `ui/` looks and behaves like FreeCAD main 3160daf1e2b6, over the `cad` CLI that the agent shares. FreeCAD's code and icons may be copied (LGPL). `ui/PARITY.md` is the record of what's done.

## State (main, 2026-10-02)
- All menus, toolbars, keys, panels and navigation styles that apply here are done, and every Preferences page FreeCAD's resource.cpp registers is present (see PARITY.md), plus Tools > Customize (Toolbars, Macros), user shortcuts (Preferences > General > Keyboard), Expression Editor name completion, the pick radius, tree selection check boxes, and every command echoed to the console (ScriptToPyConsole).
- New CLI: `cad pref [KEY [VALUE]]` (MaxUndoSize, CacheLimit, CachePeriod; userprefs.py) and `cad cache [--clear]` (appcache.py). The page edits the same store over /api/prefs and /api/cache.
- `node ui/scripts/keycheck.mjs [URL]` presses all 62 default shortcuts in a running workbench and checks each ran (needs Playwright; point it at a scratch workbench only).

## Next
1. Run fcdiff.py / fcgui.py on the Mac against the new pages (Light Sources, UI, Document, Keyboard, Cache, Advanced, Workbenches, PDF, Python General/Editor) and fix any label differences.
2. Rotation rings of the Transform dragger: check their drag updates the Rotation fields as the arrows do (the arrows were checked with a real mouse drag).
3. Anything left is n/a by design (listed in PARITY.md).

## Testing without touching real projects
`cad serve` always includes the repo's own `projects/`. For UI tests, start the workbench with `serve.run([scratch_root])` from Python and set CAD_PREFS, CAD_WARM_DIR, CAD_RUNTIME_DIR and CAD_MACRO_DIR to scratch paths.

## How to check
- `cd ui && npx tsc -b --noEmit && npm run build` (the build goes to `cad_agent/workbench/next/`; commit it).
- `node ui/scripts/navcheck.mjs`: 72 navigation checks, needs only Node.
- `.venv/bin/python -m pytest -q`: 367 tests.
- `python3 ui/scripts/fcdiff.py` and `fcgui.py` need FreeCAD's weekly build at `~/.cad-agent/freecad/FreeCAD.app`. That's only on Juan's Mac, not in the cloud.
- To fetch FreeCAD sources: `https://raw.githubusercontent.com/FreeCAD/FreeCAD/3160daf1e2b6/<path>`.

## Rules
- Port line by line from FreeCAD and cite the source file in comments; note any deliberate difference in PARITY.md.
- Use free tools only, and build CLI-first, so the agent and the UI can do the same things.
- Use scratch copies of projects for tests, never real projects.
- Commit on a branch, then fast-forward main and push.

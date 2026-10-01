# Handoff: FreeCAD-parity UI (2026-10-01)

Goal: the workbench UI in `ui/` looks and behaves like FreeCAD main 3160daf1e2b6, over the `cad` CLI that the agent shares. FreeCAD's code and icons may be copied (LGPL). `ui/PARITY.md` is the record of what's done.

## State (main @ 5102c39)
- All menus, toolbars, keys, panels and navigation styles that apply here are done (see PARITY.md).
- Latest work: 3D view gestures (touch pinch/pan/twist, Safari twist, Option+scroll roll, double-click deferral), and Preferences > Display > Colors (background gradients, tree edit colour).

## Next, in order
1. Preferences > Display > Light Sources (`src/Gui/PreferencePages/DlgSettingsLightSources.ui/.cpp` at 3160daf1e2b6), wired to the viewer's lights.
2. Make the selection and preselection colours editable (Selection page; today they're fixed in `ui/src/theme.ts` VIEW).
3. Preferences > Display > UI: the tree options that apply.

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

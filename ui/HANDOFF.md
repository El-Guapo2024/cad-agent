# Handoff: FreeCAD-parity UI (2026-10-01)

Goal: the workbench UI in `ui/` looks and behaves like FreeCAD main 3160daf1e2b6, over the `cad` CLI that the agent shares. FreeCAD's code and icons may be copied (LGPL). `ui/PARITY.md` is the record of what's done.

## State (main, 2026-10-01)
- All menus, toolbars, keys, panels and navigation styles that apply here are done (see PARITY.md).
- Latest work: Preferences > Display > Light Sources (lights.ts: FreeCAD's camera-following three-point rig), editable selection/preselection colours on the Selection page, and Preferences > Display > UI (tree view and overlay options). Fixed a load-time "Viewer.render() must be called" error (resize handlers before the first render).

## Next, in order
1. The remaining Preferences pages registered in resource.cpp that apply: General > Document (DlgSettingsDocumentImp), Display > Advanced (DlgSettingsAdvanced), Python > Python console / Editor (DlgSettingsPythonConsole, DlgSettingsEditor) for the console here. Port what applies, show the rest disabled with an n/a tooltip.
2. Expression Editor name completion (parameter names while typing).
3. Pick radius on the Selection page (needs a screen-space pick tolerance over three-cad-viewer's ray cast).

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

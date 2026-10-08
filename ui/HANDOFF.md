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
2. ~~Compare the new Preferences pages with FreeCAD~~ done 2026-10-02: all 18 pages match their .ui files (`prefdump.mjs` + `prefdiff.py`), and the menus were re-checked against a fresh `fcgui.py` dump (`fcref.py` + `menurun.mjs`). PARITY.md has the details and what's expected to differ.
3. Try the plugin for real in a scratch folder: `/plugin marketplace add El-Guapo2024/cad-agent`, install it, and check that the SessionStart install puts `cad` on PATH, the cad skill and hooks fire on a small part, and `/cad-agent:workbench` opens. Juan runs the `/plugin` commands; Claude checks the result.
   - First try, 2026-10-02 (0.1.0), found three bugs, fixed in 0.1.1. The first-run install failed on a Python that reports macOS 10.16 (miniconda's), because uv then turns down the kernel's macosx_11_0 wheels; it now sets SYSTEM_VERSION_COMPAT=0, and Macs get the `metal` extra. `/cad-agent:workbench` handed out the URL of a workbench serving other folders when 8733 was taken; `cad serve` now reuses one that serves the same folders, else takes the next free port. The stop hook checked the plugin's bundled examples at every stop in every project.
   - Next: Juan runs `claude plugin marketplace update cad-agent` and `claude plugin update cad-agent@cad-agent`, opens a fresh session in ~/ws/cad-trial (a git repo), and repeats the trial.
   - Fixed 2026-10-07: renders in the warm worker fell back to numpy on a fresh install. It was not OCP 8.0 and not the worker's start (a parent that imports nothing fails the same way). A fork without exec cannot reach Metal's shader compiler, an XPC service (the look-up fails with "No such process", so the compile fails with XPC_ERROR_CONNECTION_INVALID). In a fork the compile only works if Metal's shader cache already holds the same source for the same python (another venv does not share it), and any cold run fills it. That is why the import-then-fork tests passed and the dev .venv looked fine (on main, 2 of 6 warm renders there still fell back to numpy, once the entry was missing). Now the worker execs a sidecar (`metal_render.py`; `cad warm status` shows it) that owns the device and does every draw: the forks send it their triangles (`CAD_METAL_SIDECAR`) and get the same pixels a cold render makes, byte for byte. To repeat a fresh install without reinstalling, run the plugin's python through a new venv-like folder with a short, new name (a symlink to its python, a copy of pyvenv.cfg, a symlink to lib): Metal has not cached that one.
   - CI had been red since f43b3e2 from one Linux-only test (reveal opens the folder on Linux); fixed.

Then the product (PLAN_V2.md build order, steps 6–8). Recommended order:
4. Step 7 first, the eval set: about 10 small briefs, each with a hidden `spec.toml`, and a runner (`cad eval`) that scores them through `cad verify`. That way every later harness change is measured.
   - Phases 1 and 2 done 2026-10-04: 10 tasks in `evals/` (`nema17_mount`, `syringe_clamp`, `galvo_mount`, `mgn12h_carriage`, `hotplate_standoffs`, `pinned_carrier`, `laser_panel`, `pcb_enclosure`, `idler_bracket`, `endstop_bracket`), `cad eval ls|brief|score|run`, `spec.toml` gained `[[size]]`, `[[position]]` and `max_mm` on `[[clearance]]`. See `evals/README.md`.
   - Never run with a real agent yet: it spends plan usage, so it needs Juan's OK. The command is in `evals/README.md`; it passes `--plugin-dir {plugin}`, a copy of the plugin without `evals/`, so the agent can't read the hidden specs. The edit and stop hooks skip everything under `evals/`.
   - Three checks that wrongly failed good designs, fixed 2026-10-07 (the briefs dropped their workarounds): `[[interface]]` judges holes, not every round face (a counterbore is part of its hole and sized by its narrowest bore, a slot is judged by its centre line, fillets and notches are not holes); a clearance hole is anything in ISO 273's fine to coarse range (M3: 3.2 to 3.6 mm); `geometry/web` is N/A for a flat part with no cutout, whose cutout count is still held to `EXPECT_FEATURES`.
   - Known gaps, what the grader can't say yet (each task works round them; `evals/README.md` has the detail):
     - no `[[axis]]` kind, so `AXES` can't be required (`mgn12h_carriage` asks for it; without it only the home pose is graded);
     - no hole-count option and no shaft-fit option;
     - a clearance `max_mm` bounds only the closest approach, and there is no clearance to a sub-feature;
     - there is no DXF export for laser parts;
     - no heat rule and no body count.
5. Step 6, machine scale: a parts library with vendor STEPs and sources, sub-assemblies, the heat, mass and deflection rules, and shop outputs (DXF, drawings, STL/3MF, BOM).
6. Step 8, the first real job: the one-machine layout (frame, gantry, dock, laser keep-out).

UI parity itself is done. Anything left is n/a by design (listed in PARITY.md).

## Testing without touching real projects
`cad serve` always includes the repo's own `projects/`. For UI tests, start the workbench with `serve.run([scratch_root])` from Python and set CAD_PREFS, CAD_WARM_DIR, CAD_RUNTIME_DIR and CAD_MACRO_DIR to scratch paths.

## How to check
- `cd ui && npx tsc -b --noEmit && npm run build` (the build goes to `cad_agent/workbench/next/`; commit it).
- `node ui/scripts/navcheck.mjs`: 72 navigation checks, needs only Node.
- `.venv/bin/python -m pytest -q`: 374 tests.
- keycheck on the Mac: Playwright comes with the miniconda Python install. Make a folder holding a symlink `playwright -> ~/miniconda3/lib/python3.13/site-packages/playwright/driver/package` and run `NODE_PATH=<folder> node ui/scripts/keycheck.mjs http://127.0.0.1:<port>/next/` against a scratch workbench (serve.run with the CAD_* variables above; a `cad-keycheck` entry in ~/ws/.claude/launch.json does this on port 8792).
- Preferences against FreeCAD: `node ui/scripts/prefdump.mjs URL dump.json`, then `python3 ui/scripts/prefdiff.py dump.json` (fetches the .ui files once).
- Menus against FreeCAD: `python3 ui/scripts/fcgui.py` (FreeCAD's dump), `python3 ui/scripts/fcref.py <scratch project>`, then `node ui/scripts/menurun.mjs 'URL#<project>'`. 43 expected differences as of 2026-10-02 (PARITY.md's Menus note).
- `python3 ui/scripts/fcdiff.py` and `fcgui.py` need FreeCAD's weekly build at `~/.cad-agent/freecad/FreeCAD.app`. That's only on Juan's Mac, not in the cloud.
- To fetch FreeCAD sources: `https://raw.githubusercontent.com/FreeCAD/FreeCAD/3160daf1e2b6/<path>`.

## Rules
- Port line by line from FreeCAD and cite the source file in comments; note any deliberate difference in PARITY.md.
- Use free tools only, and build CLI-first, so the agent and the UI can do the same things.
- Use scratch copies of projects for tests, never real projects.
- Commit on a branch, then fast-forward main and push.

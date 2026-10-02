---
description: Open the cad-agent workbench (FreeCAD-style 3D UI) on this project's designs
argument-hint: "[folder with cad projects]"
---
Start the cad-agent workbench in the background with `cad serve $ARGUMENTS` (with no argument it
serves `$CAD_PROJECTS`) and give the user the address it prints, with `/next/` on the end. It
answers "workbench already running: URL" when one already serves these folders (give that URL),
and otherwise takes the first free port from 8733: a workbench on port 8733 may be serving other
folders, so never hand out a URL `cad serve` didn't print. Don't stop it at the end of the turn.
If `cad` isn't found, the plugin's setup failed at session start: say so, and don't fall back to
another checkout's `bin/cad`.

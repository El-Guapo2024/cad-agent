---
description: Open the cad-agent workbench (FreeCAD-style 3D UI) on this project's designs
argument-hint: "[folder with cad projects]"
---
Start the cad-agent workbench in the background with `cad serve $ARGUMENTS` (with no argument it
serves `$CAD_PROJECTS`), wait until it prints its address, and give the user the URL
(http://127.0.0.1:8733/next/ unless it reports another port). Don't stop it at the end of the turn.

# Editing in the app, as FreeCAD does (plan, 2026-10-24)

Until now the app shows and checks parts the agent writes in Python; it does not make or change shapes
(ui/PARITY.md: "no FreeCAD document, no save, no feature tree and no sketcher"). Juan's call, 2026-10-24:
the app should edit as FreeCAD does, edits are written back as Python, and the Sketcher with Pad/Pocket
comes first. The reference is FreeCAD at 3160daf1e2b6 (weekly-2026.09.30), as for the rest of the port.

## Where an edit lives

A part made in the app is still a part module, `parts/<name>.py`, with PARAMS and `build()`, so every gate,
check, drawing and export keeps working and the agent can read and change it. Its shape is a feature list
the app reads and writes, in plain Python the agent can edit too:

```python
PARAMS = {"width": 40.0, "thick": 5.0}

SKETCHES = {
    "Sketch": sketch(plane="XY",
        geometry=[line((0, 0), (40, 0)), line((40, 0), (40, 20)), ...],
        constraints=[horizontal(0), distance_x(0, "width"), coincident((0, 2), (1, 1)), ...]),
}
FEATURES = [
    pad("Pad", sketch="Sketch", length="thick"),
    pocket("Pocket", sketch="Sketch001", type="through_all"),
]

def build(**p):
    return body(SKETCHES, FEATURES, p)
```

- Names, order and options follow FreeCAD's objects (SketchObject, PartDesign::Pad, ...), so a FreeCAD user
  reads it as their tree. A length may be a number or the name of a PARAMS entry (FreeCAD's expressions).
- The app edits these literals in place, as params.py does for PARAMS today: comments and layout stay.
- A part written by hand (free-form build123d, as all parts are now) stays editable as code. It can take
  features on top: the hand-written solid is the body's BaseFeature, as FreeCAD's PartDesign Body allows.

## The Sketcher's solver

FreeCAD solves sketches with PlaneGCS (Mod/Sketcher/App/planegcs, LGPL-2.1-or-later, like ui/). Dragging a
point re-solves on every mouse move, so it must run in the browser. Plan: compile PlaneGCS itself to
WebAssembly (Emscripten; it needs Eigen and Boost's graph headers), so its results are FreeCAD's by
construction, with the Python side running the same build (or the real FreeCAD) for `cad` and the gates.
A hand port to TypeScript is the fallback if the build fights back.

## Order of work, each step checked against the real FreeCAD

1. PlaneGCS to WebAssembly; a check that solves FreeCAD's own sketcher test sketches and compares with
   freecadcmd's results.
2. The feature-list module (`cad_agent/feature.py`): sketch to wire to face, Pad and Pocket with their types
   (Dimension, Through all, To first, Up to face, Two dimensions, Symmetric, Reversed), written and read
   back without loss. Checked by building the same sketch and pad in freecadcmd and comparing volume,
   area and bounding box.
3. Sketcher UI: edit mode (the view turns to the sketch plane), lines, polylines, arcs, circles,
   rectangles, slots, points, construction mode, the constraint tools and their icons, dragging with
   re-solve, the DoF count, conflicting and redundant constraints in the task panel, Close.
4. Object editing: create Body/Sketch/Pad/Pocket from the menus and toolbars, the tree with the feature
   history, double-click to edit, delete, rename, reorder, undo across all of it, save (the .py file).
5. Then, in this order: Revolution, Groove, Hole, Fillet, Chamfer, Draft, Thickness, Patterns, Mirror,
   datums, Additive/Subtractive primitives; Part workbench booleans and primitives; Assembly joints.

Each step goes on its own branch and into main when its checks and CI are green, as before.

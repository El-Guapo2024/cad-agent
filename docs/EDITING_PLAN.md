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

## Part workbench objects in a part file (decided 2026-10-24, branch part-wb)

A Body is one ordered history; Part objects are a graph: a Part::Cut is made from its Base and Tool, a Part::MultiFuse
from its Shapes, a Part::Extrusion from its Base, each of which may be any other object, a sketch or a Body. In the
part file they are a second list beside FEATURES, OBJECTS, in FreeCAD's document order (each object after what it
links), written in FreeCAD's Python vocabulary under the name `Part`:

```python
from cad_agent import feature_part as Part
from cad_agent.feature import Circle, Sketch

OBJECTS = [
    Part.Box("Box", length=40, width=20, height=5, label="Cube"),
    Part.Cylinder("Cylinder", radius="r", height=5, placement=((8, 10, 0), (0, 0, 0))),
    Part.Cut("Cut", "Box", "Cylinder"),
    Sketch("Sketch", support="XY", geometry=[Circle((0, 0), 5)], constraints=[]),
    Part.Extrusion("Extrude", "Sketch", length_fwd=10, solid=True),
]

def build(**p):
    return Part.Document(OBJECTS, p)                       # with a Body: Part.Document(OBJECTS, p, FEATURES, tip=TIP)
```

- Each object is a feature_kw.KwFeature call: its Name first, links by position where FreeCAD's Python takes them
  (Base, Tool; Shapes), the rest FreeCAD's properties in snake_case with FreeCAD's defaults left out, so feature_edit
  reads and edits OBJECTS with the code it has for FEATURES. A link is a name, (name, "Edge3") or (name, ["Edge1",
  ...]); label= is FreeCAD's Label when the command gives one (Part_Box labels its Box "Cube").
- The Body, when the file has FEATURES, is the object "Body"; an object may link it or one of its features (a sketch).
  A sketch made outside a Body is a Sketch(...) in OBJECTS, placed on an origin plane.
- What build() returns is what FreeCAD shows: every object nothing links (the commands hide their inputs), and the
  Body when nothing links it, as one compound. So every gate, drawing and export keeps reading one shape.
- `Part.` and not bare names because hand-written parts import build123d's Box, Cylinder, Sphere, Plane: the first Part
  object turns a Body file into a document (Body(FEATURES, p, ...) becomes Part.Document(OBJECTS, p, FEATURES, ...)),
  a hand-written part first gets its Body with its solid as BaseFeature, and nothing it imports is shadowed.
- Smallest extension of the seams: feature.py and feature_kw.py are unchanged but for feature_kw's import moving to its
  end (an import cycle main had too); feature_edit.py's list helpers take which list (FEATURES or OBJECTS) and
  its read() gives "objects" and "body"; the rest is in new files: cad_agent/feature_part*.py (the objects and
  Part.Document), feature_part_face.py (FreeCAD's face makers), feature_edit_part.py (OBJECTS' own edits).
- Checked like the Body: tests/golden/part (freecadcmd builds every case through feature_part.to_freecad; each object's
  volume, area, length, box, centre and topology counts) and each type's FreeCAD defaults.

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

## Static objects in a part file (decided 2026-10-27, branch part-wb-2)

FreeCAD's Simple, Transformed and Element copy, Convert to solid, Cross-sections and the Shape builder run Python that sets
the Shape of a new Part::Feature, which then holds that shape alone. A part file holds the recipe instead, as an object of
OBJECTS (cad_agent/feature_part_static.py): `Part.Feature("Box001", "Box")` (a copy of the source's placed shape; a
`("Box", "Face3")` source is the element copy; the copy's Placement is the source's, a vertex's identity),
`Part.MakeSolid("Comp_solid", "Comp")`, `Part.CrossSections("Box_cs", "Box", plane="XZ", positions=[...])`,
`Part.ShapeBuilder("Face", "Face from vertices", elements=[("Box", "Vertex2"), ...], planar=...)`. They have no children in the
tree and hide nothing. The cost is that they follow their source when it changes. Set tolerance is a parametric
FeaturePython in FreeCAD (`Part.ToleranceSet("Tolerance", ["Box"], min_tolerance=1e-07)`), its result at the origin
(Feature::onChanged puts a recompute's shape at the object's Placement). A recipe's own properties are not FreeCAD properties
of Part::Feature (`STATIC = True`), so the property view shows Placement and Label only, as FreeCAD's.

## Assembly in a part file (decided 2026-10-26, branch assembly)

FreeCAD's Assembly is an object of a document whose components are App::Links to objects of other documents. Here a
part file is one document (a Body, or Part objects) and its build() returns one shape, so an Assembly does not go in
a part file: it goes in the project's assembly.py, which already is "the project's assembly document" for every gate
(state.load_machine calls its parts()). Its ASSEMBLY list holds, in FreeCAD's Python vocabulary under the name
`Assembly` and in the document's order, the components and the JointGroup's joints:

```python
from cad_agent import assembly_wb as Assembly

SLUG = "arm_demo"

ASSEMBLY = [
    Assembly.Link("plate", "plate"),                                   # App::Link to parts/plate.py
    Assembly.Link("pin", "pin", placement=((20.0, 15.0, -15.0), (0.0, 0.0, 0.0, 1.0))),
    Assembly.GroundedJoint("GroundedJoint", "plate"),
    Assembly.Joint("Joint", "Revolute", ("plate", ["Face6", "Face6"]), ("pin", ["Face3", "Edge1"]),
                   label="Revolute"),
]

def parts():
    return Assembly.parts(SLUG, ASSEMBLY)                               # {component: its part, placed}
```

- Each entry is a feature_kw.KwFeature (cad_agent/assembly_wb.py): Link is App::Link (LinkedObject: a part of the
  project; Placement), GroundedJoint is JointObject.GroundedJoint (ObjectToGround), Joint is JointObject.Joint with
  its properties in snake_case and FreeCAD's defaults left out: joint_type (Fixed, Revolute, Cylindrical, Slider,
  Ball, Distance, Parallel, Perpendicular, Angle, RackPinion, Screw, Gears, Belt), reference1/2, offset1/2, angle,
  distance, distance2, the limits, detach1/2, suppressed, label. The Assembly and its JointGroup ("Joints") are the
  list itself: the tree shows them as FreeCAD does.
- A reference is FreeCAD 26.3's (moving part, [element, vertex]): ("pin", ["Face3", "Edge1"]) is the JCS on the
  pin's Face3 at the centre of that face's own Edge1. Placement1/2 are recomputed from the references
  (updateJCSPlacements) and written only when detached.
- A component's placement is its Placement as the last solve left it, every digit kept, so a recompute starts where
  FreeCAD's document would; hand-written ones may give yaw, pitch, roll in degrees. parts() recomputes the
  Assembly as FreeCAD does on opening a document (SolveOnRecompute) and returns each component's part placed there,
  so the fit, sweep, BOM, mass and render gates see the solved assembly. A component's name is the part's (the
  document's root object's Label, as a FreeCAD user labels a Body after the part), made unique as FreeCAD does.
- The solver is FreeCAD's: OndselSolver at the submodule revision of 3160daf1e2b6 (4be80eef02a3), vendored unchanged
  in ui/ondsel/upstream, with the solving half of AssemblyObject.cpp ported in front (ui/ondsel/assembly.cpp, a C
  API taking JSON), native for Python (cad_agent/ondsel.py, `ui/ondsel/build.sh native`) and WebAssembly for the
  page (ui/ondsel/dist, ui/src/ondsel.ts), as PlaneGCS is. JointObject.py and UtilsAssembly.py's Python (presolve,
  findPlacement, the panel's create and accept) are ported in assembly_wb.py and assembly_jcs.py.
- An assembly.py written by hand stays as it is; the first `cad assembly insert` (Assembly_InsertLink) adds the
  list, and a hand-written parts() becomes placed_parts(), whose bodies the new parts() returns beside the
  Assembly's. AXES, POSES, CLEARANCE and ALLOW_CONTACT keep their meaning; a sub-project is still SUBASSEMBLIES.
- Edits: cad_agent/assembly_edit.py (read/apply, all or nothing, the entries an edit did not change keep their text)
  behind `cad assembly ...` (cad_agent/assemblycmd.py), each change one undo step named as FreeCAD's transaction
  ("Insert Component", "Create Revolute Joint", "Toggle grounded", "Move part").
- Checked like the Body: tests/golden/assembly (freecadcmd builds each case through the GUI's command sequence;
  every step's placements, references, JCS and the exportAsASMT file), the native and the wasm build both.
- The later commands (2026-10-27, branch assembly-2) are more entries of the same list, FreeCAD's objects again:
  `Assembly.RigidGroupJoint("RigidGroupJoint", ["bar", "pin"], rigid_placements=...)` (Create Rigid Group; the
  members' placements relative to the first, kept for a suppressed group's Update Stored Positions);
  `Assembly.AssemblyLink("Assembly", "other_project", rigid=True, components=[...], joints=[...])` (a sub-assembly:
  another project's assembly.py ASSEMBLY, its components named uniquely here, a flexible one's joints copied in as
  synchronizeJoints does; a reference into a rigid one is `("Assembly", ["Plate.Face6", ...])`); the Assembly's
  Origin as a reference (`("Origin", ["XY_Plane.", "XY_Plane."])`); `Assembly.ViewGroup`, `ExplodedView` and its
  `ExplodedViewStep` moves (Exploded View); `Assembly.SimulationGroup`, `Simulation` (aTimeStart ... jFramesPerSecond
  in snake_case, `group=` its motions) and `Motion` (joint, motion_type, formula). New Part writes parts/<Part>.py (a Body
  with a sketch) and links it in with a Fixed joint at the element picked. Their code: assembly_link.py,
  assembly_view.py, assembly_sim.py, assembly_newpart.py, each registering its classes into assembly_wb; the solver
  side (rigid clusters, generateSimulation) is in ui/ondsel/assembly.cpp.

## Several Bodies (decided 2026-10-27, branch pd-last)

FreeCAD's PartDesign_Boolean fuses, cuts or commons other Bodies of the document into the active one, and PartDesign_Clone
starts a new Body whose base is a copy of another. Both need a link from one Body to another. The app already makes each Body
its own part module (New Body writes parts/Body001.py, and the tree lists every part's Body as FreeCAD lists the Bodies of a
document), and a part file stays one Body with its Part objects. So a link to another Body is that part's name, and a link to
one of its features "Part.Feature":

```python
# parts/Body.py
FEATURES = [
    Sketch("Sketch", ...), Pad("Pad", "Sketch", length=5),
    Boolean("Boolean", ["Body001"], type="Cut"),             # PartDesign::Boolean, its Group the tool Bodies
]

# parts/Body001.py, written by PartDesign_Clone (`cad feature clone SLUG Body`): "Create Clone"
FEATURES = [
    Clone("Clone", "Body"),                                  # PartDesign::FeatureBase, BaseFeature the Body
]
TIP = "Clone"
```

- The other part is built from its own source as its build() builds it (its FEATURES with its PARAMS, BaseFeature and TIP; a
  part with no FEATURES is its build()'s shape, a Part::Feature as FreeCAD takes one), in its own frame: both Bodies sit at the
  document's origin, as two Bodies FreeCAD makes do until one is moved (Boolean's getTopoShapeInLocalCoordinates). Where
  assembly.py places a part does not move it for the Boolean.
- A Body that reaches itself through these links is refused ("Link cycle: Body001 -> Body -> Body001"), as FreeCAD refuses a
  dependency loop; a missing part is "no Body 'Body009' (parts/Body009.py)".
- cad_agent/feature_boolean.py has the features; it finds the other part next to the part file whose FEATURES name it, and a
  caller that has the Bodies at hand gives them by name instead (feature_boolean.OTHERS: tests/golden/pdlast). The build cache
  keys a part that calls Boolean or Clone on every file of the project (buildcache.REACHES_CALLS), as it keys a part that calls
  build_part, so an edit to the tool rebuilds the Body that uses it.
- Checked like the Body: tests/golden/pdlast builds each case's other Bodies first in the same FreeCAD document, under their part
  names, then the case's Body; the shapes are FreeCAD's (tests/test_feature_pdlast.py).
- A ShapeBinder and a Sub-Shape Binder still bind their own Body only.

## TechDraw pages in a project (decided 2026-10-27, branch techdraw)

FreeCAD's TechDraw page is a document object (TechDraw::DrawPage) whose views link the 3D objects they draw; a view's
lines are not stored but recomputed from the shape (DrawViewPart::execute, hidden line removal). Here a page is one
file of the project, `techdraw/<Page>.py`, holding the page's objects in FreeCAD's document order under the name
`TechDraw`, as ASSEMBLY holds the Assembly's:

```python
"""Page: a TechDraw page of the project; the app and `cad techdraw ...` edit it (cad_agent/techdraw_edit.py)."""
from cad_agent import techdraw as TechDraw

PAGE = [
    TechDraw.DrawPage("Page", "Template"),
    TechDraw.DrawSVGTemplate("Template", template="ISO/A4_Landscape_TD.svg", editable_texts={"FC-Title": "Plate"}),
    TechDraw.DrawProjGroup("ProjGroup", source=["plate"], views=["ProjItem", "ProjItem001"], anchor="ProjItem",
                           x=120.0, y=110.0, scale_type="Custom", scale=0.5),
    TechDraw.DrawProjGroupItem("ProjItem", type="Front", label="Front"),
    TechDraw.DrawProjGroupItem("ProjItem001", type="Top", direction=(0.0, 0.0, 1.0), label="Top"),
    TechDraw.DrawProjGroupItem("View", source=["plate"], direction=(0.0, 0.0, 1.0), x=230.0, y=60.0),
    TechDraw.DrawViewSection("Section", base_view="View", section_symbol="A", section_normal=(-1.0, 0.0, 0.0),
                             section_origin=(20.0, 15.0, 2.5), direction=(-1.0, 0.0, 0.0), x_direction=(0.0, 1.0, 0.0),
                             x=230.0, y=150.0),
    TechDraw.DrawViewDimension("Dimension", type="DistanceX", references_2d=[("View", "Edge3")], x=12.0, y=-25.0),
    TechDraw.DrawViewDimension("Dimension001", type="Diameter", references_2d=[("View", "Edge5")],
                               format_spec="⌀%.2w", over_tolerance=0.1, under_tolerance=-0.1, equal_tolerance=False),
    TechDraw.DrawViewBalloon("Balloon", source_view="View", origin_x=5.0, origin_y=3.0, text="1", x=30.0, y=30.0),
    TechDraw.DrawViewAnnotation("Annotation", text=["Default Text"], x=40.0, y=20.0),
]
```

- Each entry is a feature_kw.KwFeature (cad_agent/techdraw.py): its Name, the links FreeCAD's Python takes by
  position (DrawPage's Template), the rest the type's properties in snake_case with FreeCAD's defaults (a fresh
  profile's Preferences > TechDraw) left out. Property names are FreeCAD's: Source, Direction, XDirection, Scale,
  ScaleType, X, Y, Rotation, HardHidden, SmoothVisible...; BaseView, SectionNormal, SectionOrigin, SectionDirection,
  SectionSymbol, CutSurfaceDisplay; Type, References2D, MeasureType, FormatSpec, OverTolerance, UnderTolerance,
  EqualTolerance, Arbitrary, ArbitraryTolerances, Inverted, TheoreticalExact; SourceView, OriginX/Y, BubbleShape,
  EndType, Text; Text, TextSize, Font, TextStyle, MaxWidth, LineSpace.
- One file is one page: every view in PAGE belongs to its DrawPage (the page's Views are the list's views, in order,
  that no DrawProjGroup holds); a DrawProjGroup's Views and Anchor are written, and its items take their Source,
  Scale and ScaleType from it as DrawProjGroup::updateChildren* gives them. Names are unique over all of a project's
  pages, as in FreeCAD's one document ("Page001" has "Template001").
- A Source is a part of the project, by its module's name (parts/plate.py's build(), FreeCAD's Body or Part feature),
  in the part's own frame. A 2D reference is (view, "EdgeN" | "VertexN"), FreeCAD's References2D, numbered as
  DrawViewPart numbers its geometry after HLR (GeometryObject::addGeomFromCompound: visible hard, outline, smooth,
  then hidden ones, each after ScrubCount passes of DrawProjectSplit::removeOverlapEdges), so the numbers are FreeCAD's.
- Nothing computed is stored: lines, vertices, section faces, dimension values and text are a recompute
  (cad_agent/techdraw_view.py: ShapeUtils, GeometryObject, DrawProjGroup's placement, DrawViewSection's cut;
  techdraw_dim.py: DrawViewDimension's measures and DimensionFormatter), done with OCCT through OCP inside the
  commands, as cad_agent/drawing/hlr.py does. A view's X and Y are written when they are the page's (a move, or
  AutoDistribute off), as FreeCAD saves them.
- Templates are FreeCAD's own SVGs, shipped in cad_agent/techdraw_templates/ (Default_Template_A4_Landscape.svg,
  ISO/A4_Landscape_TD.svg, ISO/A3_Landscape_TD.svg and the ISO 5457 minimal A4/A3 sheets: LGPL-2.1-or-later as part
  of FreeCAD, the ISO 5457 ones CC0 1.0 as their metadata says; NOTICE), named by their path under FreeCAD's
  Mod/TechDraw/Templates. EditableTexts are the template's freecad:editable fields, as DrawSVGTemplate reads them.
- Edits: cad_agent/techdraw_edit.py (read/apply, all or nothing, untouched entries keep their text) behind
  `cad techdraw ...` (cad_agent/techdrawcmd.py) and /api/<slug>/techdraw; each change one undo step named as
  FreeCAD's transaction ("Drawing create page", "Create view", "Create projection group", "Create SectionView",
  "Create dimension", "Create Balloon", "Create Annotation", and for the annotation tools of cad_agent/techdraw_annot.py
  "Add Cosmetic Vertex", "Create Cosmetic Line", "Create Cosmetic Circle", "Create Centerline", "Edit Line Appearance",
  "Remove Cosmetic Object", "Create Hatch", "Create GeomHatch"). A view's cosmetic vertices, cosmetic edges, centre lines and
  geom formats are lists on the view (`cosmetic_vertexes=`, `cosmetic_edges=`, `center_lines=`, `geom_formats=`); a hatch is
  its own entry (`DrawHatch`/`DrawGeomHatch`, `source=` the view, `faces=["Face0"]`).
- Exports (`cad techdraw export`): SVG and PDF of the page as TechDraw's MDIViewPage prints it, and DXF as
  TechDraw.writeDXFPage writes it, to out/techdraw/<Page>.svg|dxf|pdf.
- Coexisting with `cad drawing`: its plate drawings (cad_agent/drawing/, out/drawings/) are unchanged, and so are its
  gates and tests; techdraw/ is not a design input (verify.DESIGN), so a page never makes a verdict stale.
- Checked like the Body: tests/golden/techdraw (freecadcmd builds each page from the same BREP: every view's visible
  and hidden edges in FreeCAD's order, each dimension's value and text, section faces, the projection group's
  positions, the DXF page), and ui/scripts/techdrawcheck.mjs against ui/scripts/fctechdraw.json (the real GUI's
  TechDraw menu and toolbars, task panels, tree, property view and undo).

## Spreadsheets in a project (decided 2026-10-27, branch spreadsheet)

FreeCAD's Spreadsheet::Sheet is a document object whose cells are its properties (A1, B2 and each alias, Sheet.cpp's
dynamic properties) and whose ExpressionEngine-like PropertySheet holds each cell's content and look. Here a sheet is one
file of the project, `spreadsheet/<Name>.py`, holding the Sheet and its used cells in FreeCAD's order (PropertySheet::Save:
row by row, left to right) under the name `Spreadsheet`, as PAGE holds a TechDraw page:

```python
"""Spreadsheet: a Spreadsheet::Sheet of the project; the app and `cad sheet ...` edit it (cad_agent/spreadsheet_edit.py)."""
from cad_agent import spreadsheet as Spreadsheet

SHEET = [
    Spreadsheet.Sheet("Spreadsheet", label="Params", column_widths={"A": 140}, row_heights={"1": 40}),
    Spreadsheet.Cell("A1", "'Thickness", style="bold"),
    Spreadsheet.Cell("B1", "=5 mm", alias="thick", alignment="center|vcenter|vimplied"),
    Spreadsheet.Cell("B2", "=thick * 2 + 1 mm", display_unit="cm", foreground_color="#ff0000ff"),
    Spreadsheet.Cell("A3", "12.5", background_color="#ffff00ff", row_span=1, col_span=2),
]
```

- A cell's content is what FreeCAD stores (Cell::getStringContent(persistent)): a formula as `=` and the expression as
  Expression::toString prints it (`=A1*2` is kept as `=A1 * 2`, `=Params.A1` on the sheet Params as `=A1`), a string as
  `'text`, a number as its NumberExpression (`12,5` is kept as `12.5`, `1e3` as `1000`), a quantity or fraction typed
  without `=` as a formula (`3 mm` is `=3 mm`, `1/2` is `=1 / 2`), text FreeCAD cannot parse after `=` as the string it
  keeps (`'=foo(`). What is typed goes through Cell::setContent's rules, so the file holds FreeCAD's text.
- The look is the `<Cell>` element's attributes of a FreeCAD document, in snake_case and in FreeCAD's encoding: alignment
  (Cell::encodeAlignment, "left|vcenter|vimplied"), style ("bold|italic|underline", sorted), foreground_color and
  background_color ("#rrggbbaa", encodeColor), display_unit (the unit's text, "cm"), alias, row_span and col_span (a merged
  cell's anchor). Column widths and row heights are PropertyColumnWidths/PropertyRowHeights: {"A": 140}, {"3": 40}; the
  defaults (100 and 30) are left out. Nothing computed is stored: values, units and errors are a recompute.
- Names: a sheet's Name is unique among the project's sheets and parts (FreeCAD's one document: getUniqueObjectName gives
  Spreadsheet, Spreadsheet001 ...); its Label defaults to its Name. An alias follows Sheet::setAlias (PropertySheet::
  isValidAlias: a letter, then letters, digits and `_`; not a cell address, a unit or a constant; unique in the sheet) with
  FreeCAD's messages ("Invalid alias", "Alias already defined", "... reserved unit token").

### What binds to a cell

A part's PARAMS are the properties of its Body (the document object the part is). An expression bound to one is FreeCAD's
ExpressionEngine of that object, kept beside PARAMS in the part module:

```python
PARAMS = {"thick": 5.0, "width": 40.0}
EXPRESSIONS = {"thick": "Spreadsheet.thick", "width": "<<Params>>.B2 * 4"}   # FreeCAD's ExpressionEngine
```

One formula engine (decided 2026-10-27, Juan's "minimize our own code"): ui/src/expr.ts (with expr-py.ts, quantity.ts and
the grammar and unit tables) is the only implementation of FreeCAD's expression language. The server shares it: it is
bundled, as it is, into cad_agent/fcexpr_engine.js (ui/scripts/fcexprjs.py, with ui/scripts/expr-server-entry.ts for the
JSON in and out; tests/test_fcexpr.py fails when the bundle is older than its sources) and run in V8 through the
mini-racer package. cad_agent/fcexpr.py is glue only: the tree as dataclasses of expr.ts's Node (a sheet's insert, remove,
paste and rename visitors rewrite it), values as Python's, and the document's hooks (ObjectIdentifier::resolveAmbiguity,
another object's property, a range's cells), which Python answers before the call and expr.ts's Env.resolve,
Env.rangeCells and parseExpr's resolveAmbiguity consult. A sheet's cell views (SheetModel::data) and its CSV are made once,
on the server, and the page shows them; CSV import reads with the standard library's csv module.

- An EXPRESSIONS entry is a FreeCAD expression evaluated by the page's own engine (see "One formula engine" below) with
  the part as its owner, as ObjectIdentifier resolves names: a bare name is one of the
  part's own PARAMS; `Obj.prop` names the object Obj by its Name, else by its Label, `<<Label>>.prop` by Label only, and
  `Spreadsheet.A1` / `Spreadsheet.thick` is the cell's computed property (by address or alias, absolute `$A$1` too). The
  result is written to the PARAMS entry in that entry's type, as setting a PropertyFloat from a Quantity takes its value
  in internal units (mm, degrees): 7.5 mm makes thick 7.5.
- The literal in PARAMS stays what FreeCAD saves as the property's value (the last recompute's), and `cad set` /
  params.write refuse a bound entry ("thick is bound to Spreadsheet.thick ..."), as FreeCAD's property editor makes a
  bound property read only. A FEATURES value keeps naming a PARAMS entry ("thick"), so a Pad's Length follows a cell
  through the parameter: Pad.Length = thick = Spreadsheet.thick.
- A cell may read a part's PARAMS the same way (`=plate.thick`, `=<<plate>>.width`): the part's parameters as its
  EXPRESSIONS leave them, read from its source without running it.
- The binding is applied wherever a part module is run (state._load_module and feature_edit's loader): the module's PARAMS
  are the bound values, so every build, gate and drawing sees them. The build cache keys every part on the project's
  spreadsheet files (they are helper sources to buildcache.key), so an edited cell rebuilds the parts that read it.

### Recompute and dependency errors

- Inside a sheet, Sheet::execute is ported as it is: the dirty cells and those depending on them in a graph built in
  CellAddress order, boost::topological_sort's order (depth first over the vertices as added, finishing order reversed),
  each cell's value set as FreeCAD sets its property (PropertyInteger for a whole number, PropertyFloat, a
  PropertySpreadsheetQuantity for a quantity with a unit, PropertyString, PropertyPythonObject for True, None, a list or a
  Vector), an evaluation error as the cell's exception and the property "ERR: <message>". A cycle fails the whole sheet
  ("Pending computation due to cyclic dependency", then each loop's cells "Cyclic dependency\nA1, A2"), and the sheet's
  recompute says "One or more cells failed contains errors.". Dependencies are PropertySheet::addDependencies' (an alias
  counts only if it existed when the cell was set, as in FreeCAD).
- Between objects (sheets and parts) the document's order is the dependency order. A cycle between objects is FreeCAD's
  "The graph must be a DAG": nothing is recomputed and the binding reports it. Setting an expression that would close a
  cycle is refused as PropertyExpressionEngine::validateExpression refuses it ("cyclic reference to <slug>#Spreadsheet.A2").

### Edits, the CLI and the page

- cad_agent/spreadsheet.py has the Sheet, Cell and PropertySheet ports (Sheet.cpp, Cell.cpp, PropertySheet.cpp, Range.cpp's
  CellAddress and Range) and SheetPy's methods by their names (set, setAlias, setStyle(range, value, 'add'), setAlignment
  (range, value, 'keep'), setForeground, setBackground, clearForeground, setDisplayUnit, mergeCells, splitCell,
  insertRows, removeColumns ..., setColumnWidth, setRowHeight, clear, importFile, exportFile). An edit is a list of those
  calls, as FreeCAD's GUI commands send them (Gui::Command::doCommand lines), applied all or nothing by
  cad_agent/spreadsheet_edit.py; an entry the edit did not change keeps its text.
- `cad sheet ...` (cad_agent/spreadsheetcmd.py) and /api/<slug>/spreadsheet[/<Sheet>]; each change one undo step named as
  FreeCAD's transaction ("Create Spreadsheet", "Edit cell", "Set cell properties", "Merge cells", "Set bold text",
  "Insert Rows", "Clear Cells", "Paste Cell" ...).
- CSV: Spreadsheet_Import / Spreadsheet_Export as Sheet::importFromFile / exportToFile with the preferences' delimiter,
  quote and escape characters (tab, `"`, `\`).
- The page (ui/src/spreadsheet*.tsx): the Spreadsheet workbench, the sheet as an MDI tab (SheetView: the Content and Alias
  line edits above SheetTableView), its menu and toolbar, the tree, the property view and undo. Charts, Bind, the
  Configuration Table and xlsx import are cut.
- Checked like the rest: tests/golden/spreadsheet (freecadcmd: each case's contents, values and property types, the
  errors, recompute through to a Pad whose Length a cell drives), and ui/scripts/spreadsheetcheck.mjs against
  ui/scripts/fcspreadsheet.json (the real GUI's menus, toolbars, context menu, Properties dialog, the sheet's display
  strings, colours and alignment, the tree, the property view and undo).

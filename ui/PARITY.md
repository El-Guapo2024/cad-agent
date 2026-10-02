# FreeCAD parity, command by command

Compared against FreeCAD main at 3160daf1e2b6 (2026-09-29). The command lists come
straight from `src/Gui/Workbench.cpp`: `StdWorkbench::setupMenuBar`, `setupToolBars`
and `setupContextMenu`. The shortcuts come from each command's `sAccel` in
`src/Gui/Command*.cpp`, and the behaviour from the files named per section.

Every row marked done was checked in the page, by the tests run on 2026-09-29 and 2026-09-30.

Legend: **done**, **partial** (says what differs), **missing**, **n/a** (and why).

Why most n/a rows are n/a: the UI shows parts built from Python. There is no FreeCAD document,
no save, no feature tree and no sketcher. Edits are `cad set` (a part's PARAMS) and
`cad place` (a rigid move in placements.toml). Creating or deleting objects is the agent's
job, in the code.

## Edit menu

| FreeCAD | Key | Ours |
|---|---|---|
| Undo / Redo | ⌘Z / ⇧⌘Z | done (our edits: parameters and placements) |
| Cut, Copy, Paste, Duplicate, Delete | | n/a (objects come from code) |
| Recompute (Std_Refresh) | Ctrl+R | done: re-runs the checks. Not bound to ⌘R, which reloads the page |
| Box selection | ⇧B | done: left to right, parts inside or centred in the box; right to left, parts crossing it (`applyBoxSelection`); Esc cancels |
| Box element selection | ⇧E | done: vertices inside; faces and edges by the same two rules; a part wholly inside is taken whole |
| Select all | ⌘A | done |
| Transform | | done (FreeCAD main's `TaskTransform`): arrows and rings together, as SoTransformDragger; the Placement box shows the dragger in the Local (U/V/W), Global (X/Y/Z) or a picked coordinate system, with Align dragger rotation, and its fields move the part; Utilities: Move to other object (match and align chosen axes to a picked element) and Flip; the Dragger box: snapping, and the origin (object origin, centre of mass, or a picked face, edge or vertex); OK/Apply/Cancel; its fields follow `TaskTransform`'s references: Local shows the move from where the drag started along the dragger's own U/V/W and the turn as intrinsic X-Y′-Z″ from the reference rotation (a drag about another axis starts a new reference; typing a second angle zeroes the first and turns about the new axis); Global and custom show extrinsic X, Y, Z |
| Placement | | done (`Placement.cpp`): Translation with Axial (Shift for the opposite way), Center with Use center of mass and Selected points (one vertex: the centre; two: the axis between them; three: the normal of their plane), Rotation as axis and angle or Euler angles Z–Y′–X″, Apply incremental changes, Reset, a live preview, OK/Apply/Cancel |
| Align to… (Std_Alignment) | | done: select the fixed object then the movable one; only the two show while you click point pairs on each (coloured as FreeCAD's markers); Align computes `ManualAlignment`'s transform (one pair moves, two turn line onto line, three turn plane onto plane) and writes the placement, undoable. One view instead of FreeCAD's split view |
| Send to Python console | ⇧⌘P | done: the names go into the console line |
| Properties | ⌥↩ | done: brings up the property view |
| Toggle edit mode | | done: parameters, or Transform for a plain shape |
| Preferences | ⌘, | done for what applies, laid out as FreeCAD's pages: General > Units (unit system, decimals 1–12, minimum fractional inch); Navigation (`DlgSettingsNavigation.ui`): checkable Navigation Cube (steps by turn, corner, rotate to nearest, font, size, opacity when inactive, colour), checkable Rotation Center Indicator (sphere size, colour and transparency), Navigation (3D navigation + Mouse Configuration, orbit style, rotation mode, default camera orientation, zoom at cursor, zoom step, invert zoom, touchscreen tilt, touchpad scroll pans), Space Mouse (n/a in a browser), checkable Animations (duration, spinning), Clarify Selection; 3D View: corner coordinate system and size, camera type; Colors (`DlgSettingsViewColor.ui`): the background as a simple colour or a linear or radial gradient, with Top/Middle/Bottom (Central/Midway/End) colours, Switch and Middle color, and the tree's colour for the object being edited (active container and colour bar shown disabled, n/a); plus Transform snap |
| Edit mode submenu (Std_UserEditMode) | | done: Default, Transform, Cutting, Color, with FreeCAD's icons and tips; double-click and Toggle edit mode follow it (Cutting and Color have no editor here) |
| Part, Group, VarSet, Annotation, Datums, Links, Text document | | n/a |

## View menu

| FreeCAD | Key | Ours |
|---|---|---|
| Orthographic / Perspective view | V,O / V,P | done |
| Fullscreen | ⌥F11 | done (the browser may keep F11 for itself) |
| Freeze display | ⇧F, ⌘1–9 | done: Freeze View, Restore View 1–9, Clear Views, Save Views… and Load Views… as FreeCAD's .cam XML |
| Draw style | V,1–V,7 | done: all seven |
| Bounding box (Std_SelBoundingBox) | | done |
| Toggle axis cross | A,C | done |
| Clipping view | | done (`Clipping.cpp`/`.ui`): checkable Clipping X/Y/Z group boxes (all off at first, offsets at the middle of the scene, steps of a power of ten near a hundredth of its size) each with Offset and Flip; Custom Clipping Direction with Offset, View (the plane faces along the view), Adjust to view direction (it keeps facing along the view) and Direction X/Y/Z; an axis plane turns the custom one off and back. Coin keeps the side the plane's normal points to: Clipping X at c keeps x ≥ c, Flip keeps x ≤ c. Closing removes them |
| Random color, Toggle transparency | V,T | done |
| Workbench, Panels | | done; Panels includes the Selection view |
| Toolbars (Std_ToolBarMenu) | | done: each toolbar can be hidden and stays hidden |
| Toggle bottom panels (Std_ToggleBottomPanels) | ⌘0 | done |
| Tree view actions (Std_TreeViewActions) | T,1 T,2 T,4 | done: Sync view, Sync selection (a 3D selection scrolls the tree to it), Preselection (hovering a tree item preselects it), Record selection with Selection back and forward, Collapse/Expand, Go to selection. Sync placement and the document modes don't apply (one document) |
| Status bar (Std_ViewStatusBar) | | done |
| Overlay panels (Std_DockOverlay) | ⌘←→↑↓, T,T | done: Toggle overlay for all panels (the combo view and the report area float over the 3D view, which takes the whole area; toggling again docks them back at their sizes), Toggle overlay for the active panel, Toggle transparent panels and Toggle transparent mode (transparent until the mouse is over them), Bypass mouse events, Toggle left/right/top/bottom |
| New 3D view, Document window, Texture mapping, Issue camera position, Toggle navigation/edit | | n/a |

**Standard views**: all done, including Align to selection (looks straight at a selected planar face).
- Axonometric: Isometric (0), Dimetric, Trimetric
- Fit all (V,F) and Fit selection (V,S)
- Home (Home key)
- Front, Top, Right, Rear, Bottom, Left (1–6)
- Rotate left / right (⇧← / ⇧→)
- Store / recall working view (⇧End / End)

**Zoom**: done: in and out (⌘+ / ⌘−), Box zoom (⌘B).

**Visibility**: all done.
- Toggle visibility (Space)
- Show selection, Hide selection
- Select visible objects
- Toggle all, Show all, Hide all objects
- Toggle selectability

## Tools, File, Macro, Windows, Help

| FreeCAD | Ours |
|---|---|
| Measure (Std_Measure) | done (`TaskMeasure`, FreeCAD main's unified measurement): the result follows the selection while the task is open; Mode is Auto or one of Distance, Distance Free (between the clicked points), Angle, Length, Position, Area, Diameter, Radius, Geometric Center, with Auto taking a prioritized type (Angle for non-parallel lines and planes, Diameter for a circle, Radius for an arc) or the first valid one; the Result in a chosen unit; a label in the 3D view; Save (Enter) keeps it, Auto save, Esc clears the selection or closes. Elements are measured from the displayed geometry; two whole parts exactly by `cad measure`, a part's centre by `cad mass` |
| QuickMeasure | done (`QuickMeasure.cpp`): with no task open, the status bar's right side measures the selected elements in FreeCAD's words: Area, Total area, Nominal distance, Length, Total length, Radius, Diameter, Angle, Distance, Minimum distance, Center distance |
| Mass properties | done (`TaskMassProperties`): volume, mass, density, surface area, centres of gravity and volume, the inertia matrix and principal moments, about the centre of gravity or a custom point, in FreeCAD's four unit systems; inertia around the axis of a selected edge. Computed exactly by OpenCASCADE through `cad mass`, as `MassPropertiesResult.cpp` does (1000 kg/m³ when a part has no density) |
| Save image (Std_ViewScreenShot) | done (`DlgSettingsImageImp`): PNG, JPG or WEBP; the view's size or a standard size, aspect kept; background Current, White, Black or Transparent; the comment written into the PNG; a watermark |
| Clarify selection (G,G) | done |
| Units converter (Std_UnitsCalculator) | done: FreeCAD's quantity grammar (`Quantity.y`) and its 131 units, generated from `Quantity.l`; the converter, its history and Copy; the Quantity box in all ten unit schemas (`UnitsSchemasData.h`, generated), with decimals and the 46 unit categories |
| View turntable (Std_DemoMode) | done: angle, speed, fullscreen, timer and timeout, Play/Stop (`DemoMode.cpp`) |
| Load image (Std_ViewLoadImage) | done, reinterpreted: FreeCAD opens the file in its own 2D `ImageView`; here it becomes a textured plane in the one 3D view instead (`CadView.setImagePlane`, `viewer.ts`), laid flat under the model and sized to it. Session-only: never written to the project or to localStorage |
| Scene inspector (Std_SceneInspector) | done, reinterpreted for three.js: `SceneInspector.cpp`'s dialog over Coin's scene graph, here over `this.viewer.scene` (`CadView.sceneTree`, `viewer.ts`) — node type and name per row, Refresh |
| Dependency graph (Std_DependencyGraph) / Export Dependency Graph | done, reinterpreted: FreeCAD lays out the document's real object graph with Graphviz (shells out to `dot`/`unflatten`) and shows the SVG in its own MDI view (`GraphvizView`); no Graphviz binary and no Python-level object graph here, so the graph is each body's `part`/`used_by` (`api.ts`'s `Body`), laid out by a small hand-rolled layering (`tools.tsx`'s `buildDependencyGraph`) and shown in the Tasks panel, not a separate view/tab. Export writes both a Graphviz `.gv` (FreeCAD's own format) and an `.svg` (ours already is one) |
| Edit Parameters (Std_DlgParameter) | done, reinterpreted: FreeCAD's dialog edits the real `ParameterGrp` tree (`User parameter:BaseApp/Preferences/…`); ours reads and writes what this UI actually has instead — the `saved` helper's localStorage keys, grouped into FreeCAD's real preference names (View, NaviCube, Units, TreeView, Macro, RecentFiles, StatusBar, MainWindow, PropertyView; anything else under General), built live off whatever's actually in `localStorage` rather than a fixed list. Boolean/Integer/Unsigned/Float/Text editing, and New/Delete/Rename via a right-click menu (`tools.tsx`), as FreeCAD's — Remove/Rename Key disabled for a real setting (this UI's own code reads it by that exact name) but open for anything user-created via New. Changes apply live to the store. Dropped: Find, Save to disk (nothing here is ever unsaved — every edit already writes straight to localStorage) |
| Document Utility (Std_ProjectUtil) | disabled: n/a, no FCStd files here for it to check or recover |
| Customize (Std_DlgCustomize) | disabled: n/a, no customizable workbench toolbars, commands, macros or keyboard shortcuts stored here |
| Addon Manager | n/a at this commit's standard build too: not shown without `BUILD_ADDONMGR` |
| "Verify (fresh rebuild)" | moved out of Tools — it was never a FreeCAD command (`Std_*`), just parked here before this pass; the CAD Agent workbench menu/toolbar already has Verify |
| File (`CommandDoc.cpp` + `CommandWindow.cpp`'s Close/CloseAll) | done, Workbench.cpp's exact order (`StdWorkbench::setupMenuBar`): **New Document** asks a name first (no Save As here), then `cad init` (POST /api/init, the lead's contract) opens the result; **Open…** is a dialog over our own project list, standing in for FreeCAD's native file-open dialog; **Open Recent** uses FreeCAD's numbered format ("1 name"…) and its 4-entry default (`DlgSettingsGeneral`'s `RecentFiles`); **Close / Close All** moved here from Windows — at this commit `Workbench.cpp`'s own Windows menu has no Close entries, unlike older FreeCAD; **Save / Save As / Save a Copy / Save All / Revert** show FreeCAD's labels and shortcuts but stay disabled — every edit here (`cad set`/`place`/…) writes straight to its file, so there's never an unsaved document to save or a saved one to revert to; **Import… / Export…** are ours (bought parts; STEP/STL/Review page) under FreeCAD's labels; **Merge Document** disabled (n/a: only ever one document); **Document Information** is the existing `documentInfo` task, disabled with no project open (`Std_ProjectInfo::isActive`); **Print / Print Preview / Export PDF** all open the current 3D view's image on a new tab and the browser's own print dialog, which previews before printing and whose "Save as PDF" destination covers Export PDF too (disabled with no project or window open, as `sendHasMsgToActiveView` would be); **Exit** disabled (a browser tab can't quit the app) |
| Macro (`CommandMacro.cpp`, `DlgMacroRecordImp`, `DlgMacroExecuteImp`) | done: Macro recording…/Stop macro recording (toggles like FreeCAD's), Macros… (list, Execute, Close, Create, Edit — one textarea, no separate script editor —, Rename, Duplicate, Delete), Recent macros (12, Std_RecentMacros' default), Execute macro (disabled unless a macro is open in Edit, since FreeCAD's runs the active editor view), Attach to Remote Debugger shown disabled (n/a: no debugger). A macro is a text file of `cad` commands, not Python; System macros/Find in files/Toolbar/Download/Open Folder are n/a (no second macro root, no Addon Manager, no filesystem access from a browser; `Workbench.cpp`'s Macro menu doesn't list Open Folder at this commit either). Recording appends each model-changing edit's line (`setParams`/`place`, slug made explicit) and GUI-only actions (selection, show/hide, view props, standard views/fit) as `cad gui …`, commented out unless Preferences > Macro's new Record GUI commands is on (default on, `DlgSettingsMacro.ui`'s `PrefCheckBox_RecordGui`, collapsed from its two real checkboxes to one) |
| Windows (`CommandWindow.cpp`) | done for one document window, Workbench.cpp's exact order (no Close here — see File, above): Next/Previous/Tile/Cascade stay disabled (FreeCAD needs two or more); Std_WindowsMenu shows the one open window's title as a checked entry (clicking it just re-activates it, being always the only/active one); Choose Open Window (`Std_Windows`, renamed from our old "Windows…") lists it (`DlgActivateWindowImp`) |
| Help (`CommandStd.cpp`'s `StdCmdHelpGroup`) | done, Workbench.cpp's exact order: **What's This?** (Shift+F1) enters a pick mode (`chrome.tsx`'s `whatsThis`) — FreeCAD looks up each widget's own What's This text; lacking that, the next click shows the picked element's tooltip instead, near the pointer; **User Documentation / FreeCAD Forum / Report an Issue / Developers Handbook / FreeCAD Website / Donate to FreeCAD** open FreeCAD's own URLs in a new tab; **Restart in Safe Mode** disabled (n/a: a browser tab can't restart the app's own process); **Python Help** (Std_PythonHelp) — registered in `CommandStd.cpp`'s `CreateStdCommands` but its class isn't defined anywhere in that file (nor `CommandView.cpp`/`CommandDoc.cpp`) at this commit, so its real label/URL couldn't be confirmed from source there; a reasonable best effort (label, and FreeCAD's user-hub-style URL) stands in; **About cad-agent** (Std_About, renamed from "About this UI") keeps the existing About content. FreeCAD's own per-user URL override (`User parameter:BaseApp/Preferences/Websites`) isn't modeled: always FreeCAD's default URL |

## Toolbars

| FreeCAD toolbar | Ours |
|---|---|
| Edit: Undo, Redo, Recompute | done |
| Workbench | done: Part Design, Assembly, Inspection |
| View: Fit all, Fit selection, Standard views ▾, Draw style ▾, Measure | done |
| View: Align to selection | done |
| View: Mass properties | done |
| Individual views: Isometric … Left | done |
| File, Clipboard, Macro, Structure | n/a |

We add our own workbench toolbar: Toggle visibility, Edit parameters, Transform, Placement (Verify in Inspection).

## Context menus

**3D view** (`setupContextMenu`, "View"):
- Done:
  - Standard views: Isometric, Home, the six views, Rotate left and right
  - Fit all, Fit selection, Draw style
- Done: Align to selection.
- Done: Clarify selection at the top when anything is under the pointer. Main dropped the Navigation styles submenu; the status bar has the switcher.
- With a selection:
  - Done: Toggle visibility, Toggle selectability, Go to selection (T,G), Random color, Toggle transparency, and the part's own Transform and Placement. We add Edit parameters, Reset to the code's position, Measure and Mass properties.
  - Done: Send to console.
  - n/a: Delete, Suppress, Freeze.
- A right-click picks the part under the pointer; a right-drag pans and opens nothing.

**Tree** (`setupContextMenu`, "Tree", plus `TreeWidget::contextMenuEvent`):
- On an object, as FreeCAD orders it:
  - The object's own action first, in bold (Edit, or Transform for a plain shape).
  - The selection's commands: Toggle visibility, Show and Hide selection, Toggle selectability, Select all instances, Random color, Toggle transparency, Send to console, Transform and Placement (one object), Properties.
  - Then Show items hidden in tree view, Toggle visibility in tree view (Show In Tree), Mark to recompute and Recompute object (both re-run the checks), and Open file location.
- On the document: Show items hidden in tree view, Open file location (the project folder), Search objects, Mark to recompute.
- n/a: Rename (names come from assembly.py), Cut/Copy/Paste/Delete, Suppress/Freeze, Create group, Select dependents, Close/Reload document, Skip recomputes, expressions and links.

## Keyboard (sAccel)

Done:
- Space, 0–6, Home, ⇧←/⇧→, End / ⇧End
- V,F; V,S; V,O; V,P; V,T; V,1; V,3; V,6; V,7
- A,C; T,G
- ⇧B, ⌘A, ⌘+ / ⌘−, ⌥↩, Esc (cancels a task, closes search, clears the selection), ⌘Z / ⇧⌘Z

Also done: V,2; V,4; V,5; ⇧E; ⌘B; ⇧⌘P; ⌘,.

Also bound: ⌘N (File > New Document), ⌘O (File > Open…), ⌘P (File > Print) and ⌘F6 (Execute macro, when a macro is open in Edit).

Left to the browser: Ctrl+R (page reload) and ⌘W (close tab; browsers don't hand it to pages anyway), so File > Close only shows ⌘W. ⌘S / ⇧⌘S / ⇧⌥⌘S / ⌘Q show on Save / Save As / Save a Copy / Exit for parity only. Those commands are disabled (see the File row above), so their keys do nothing; ⌘S is still caught so the browser's Save Page doesn't open.

## Mouse and navigation cube

- **Corner coordinate system** (View3DInventorViewer::drawAxisCross): done. FreeCAD's arrows (`createAxisArrowGeometry`), AxisX/Y/ZColor (#CC3333, #33CC33, #3333CC), its X, Y, Z letter bitmaps (`CornerCrossLetters.h`), a 45° perspective mini view at the bottom right, 10 % of the shorter side (CornerCoordSystemSize, 2–100), sorted by depth. three-cad-viewer's own axes marker (bottom left) isn't drawn.

- **Navigation**: done. `src/nav.ts` ports `src/Gui/Navigation/`:
  - `NavigationStyle`: pan on the focal plane, zoom as e^step, zoom at the cursor, roll, `lookAtPoint` (a quick middle click centres the view on the point under it), and the rotation-centre marker.
  - The orbit, through `FCSphereSheetProjector` over Coin's `SbSphereSheetProjector`: Rounded Arcball (the default), Trackball, Trackball Classic, Free Turntable and Turntable. Rotation about the window centre, the cursor, or the object centre.
  - All twelve styles, event by event: Blender, CAD (the default), Gesture, Maya-Gesture, OpenCascade, OpenInventor, OpenSCAD, Revit, Siemens NX, SolidWorks, TinkerCAD and Touchpad.
  - The wheel: 120 a notch, ZoomStep 0.2, InvertZoom. A touchpad pans (Shift orbits), as `wheelAction` does on a Mac. PageUp and PageDown zoom at the cursor.
  - Gestures (`processPinchEvent`, `pinchAction`, `SoTouchEvents.cpp`). A trackpad pinch (Chrome and Firefox send it as Ctrl+wheel) and Safari's pinch and twist work as Qt's native gestures: they zoom and turn at the cursor, and DisableTouchTilt never blocks the turn. On a touchscreen the first finger is the left button. Two fingers make a QPinchGesture: their centre pans, their spread zooms, and their turn rolls the view when DisableTouchTilt is off (it's on by default). The Gesture style enters GestureState (panning), except on a Mac, where FreeCAD hands gestures straight to NavigationStyle. Maya-Gesture drags with its own pinch, which ignores the tilt setting. OpenInventor drops gestures outside selection, as FreeCAD does. A pinch never ends in a click.
  - `processClickEvent`: a left press within the double-click time of the last one waits for its release (issue #0002433). A drag box clears that state.
  - Not FreeCAD's: Alt+scroll rolls the view at the cursor, 1° per 4 px of touchpad scroll or 15° per wheel notch, because Chrome and Firefox report no trackpad twist. FreeCAD's wheel ignores Alt, so nothing of FreeCAD's is lost.
  - A left drag from empty space box-selects: left to right takes what is inside or centred in the box, right to left what crosses it (`applyBoxSelection`). Ctrl adds.
  - A left click selects on release; Ctrl toggles (Ctrl is Cmd on a Mac, as Qt maps it). A click on nothing clears.
  - Long press (1 s) opens Clarify Selection; OpenInventor, Gesture and OpenSCAD need Ctrl for it.
  - View changes animate as `NavigationAnimation`: 500 ms, InOutCubic. Fit all animates as `animatedViewAll` and frames the bounding sphere exactly. Spinning animation is optional.
  - Cursors are FreeCAD's rotate, pan and zoom icons.
- **Preferences**: the Navigation page's settings: style, orbit style, rotation mode, default camera orientation (Trimetric; used for a new view and for Home), zoom step, zoom at cursor, invert zoom, touchpad panning, touchscreen tilt, rotation centre, animations and duration, spinning, long-press clarify and its timeout.
- **NaviCube** (`NaviCube.cpp`):
  - A click turns to the face, edge or corner by FreeCAD's `getFaceRotation`, with `NaviRotateToNearest`: the roll nearest the camera's, in 90° steps (60° on corners). Clicking it again within the double-click time also centres the model.
  - A drag orbits the model's bounding sphere, at sensitivity 0.45 (`beginOrbitDrag`).
  - Arrows turn 45° (NaviStepByTurn 8), plus roll and backside; clicks made during the animation add up. Home, and the menu: Orthographic, Perspective, Isometric, Fit all.
- **Home** (`viewHome`): turns to the default orientation while moving to the model's centre, then fits all.
- **Standard views** use FreeCAD's exact rotations (`Camera.cpp`) and keep zoom and target, as `View3DPy::viewFront` does.
- **3D right-click menu** (`NavigationStyle::openPopupMenu`, FreeCAD main): the object under the pointer (or the one selected) gives its own actions first, then Clarify Selection, then the View menu in main's order (fit, align, draw style, standard views, document window, then the selection's commands, then Transform and Placement for one object). It doesn't change the selection. Main no longer has a Navigation styles submenu.
- **Clarify Selection** (Std_ClarifySelection, G, G): everything under the cursor within the pick radius × 5, sorted into Object, Face, Edge and Vertex. Hovering an entry preselects it; choosing one adds it (`SelectionMenu`).

## Selection, property view, task panel, output

| Area | Ours |
|---|---|
| Preselection and selection colours, tree ↔ 3D sync, ⌘-click, click on empty space | done |
| Status bar "Preselected: doc.obj (x, y, z)" | done (`getPreselectionInfo`): each coordinate in the unit system's unit for its size, min(6, decimals) places; plus the face or edge under the mouse |
| Face / edge / vertex selection | done: hover lights just the element, a click selects it, ⌘-click adds; named Face n / Edge n / Vertex n, numbered from 1 per type |
| Property view: Data/View tabs, groups, editors per type | done |
| Property view: Placement | done, as Angle, Axis, Position |
| Property view: expressions | done, one-shot: `=` in a field opens the Expression Editor (`DlgExpressionInput`) on it: the result or the fault as you type (FreeCAD's messages: unit mismatch between result and required unit, unit discarded), OK or Return takes it, Reset or Esc leaves the value. Units, + - * / % ^, FreeCAD's functions and the part's other parameters (`ExpressionParser`). PARAMS holds plain numbers, so the value is written, not the expression |
| Property view: units | done: lengths and angles show as FreeCAD quantities (`170.00 mm`, `90.00°`) and take any unit (`17 cm`, `1/2 in`, `2 ft 3 in`). A PARAMS float is a length (parts are in mm), or an angle when its name says so |
| Quantity fields (`Gui::QuantitySpinBox`) | done, in Placement, Transform, the property view's lengths and angles, and the snap settings: the value in the user's unit system; typing commits each valid value (keyboard tracking); a bare number takes the unit shown; `1 in`, `2 m 3 cm`, `1/2"` read as quantities, sums as expressions whose bare terms take the field's unit (`App/QuantityInput.cpp`); Return and leaving the field check it and say why it's wrong under it (Incomplete number, Invalid expression, Incompatible unit, Value is outside the allowed range…) with the fault selected; Esc puts it back; Up/Down, Page Up/Down, the wheel and the arrow buttons step by one of the unit shown (⌘: ten); Tab selects the number |
| Property view: View tab | done: FreeCAD's Part view properties in its three groups. Display Options: Bounding Box, Display Mode (Flat Lines, Shaded, Wireframe, Points; used when the draw style is As is), Show In Tree (with the tree's Show hidden items), Visibility. Object Style: Draw Style (dash patterns), Lighting, Line Color, Line Width, Point Color, Point Size, Shape Appearance, Transparency, with Angular Deflection and Deviation read only. Selection: On Top When Selected, Selectable, Selection Style (BoundBox draws a box in DefaultBBoxSelectionColor). Defaults from ViewParams and FreeCAD Light. Edits apply to the whole selection |
| Task panel: OK, Apply, Cancel, Esc, collapsible boxes | done; as `TaskView::keyPressEvent`, Return in a field presses the default button and Esc the Cancel or Close button |
| Message boxes (`QMessageBox`) | done: title, icon (critical, warning, information, question), text and buttons; Return presses the default, Esc the Cancel/No/only button; focus goes back after. Placement's "Incorrect Quantity" uses it |
| Report view: colours, and its menu (`ReportOutput::contextMenuEvent`) | done: Options (Display message types, Show report view on, Go to end; Redirect Python output/errors don't apply), Copy, Select all, Clear, Save as; time stamps as `checkShowReportTimecode` |
| Python console | done, for `cad`: echoes every command and runs typed ones (check, verify, set, place, measure, select, view, fit), with history; ⌘L clears; the menu (`PythonConsole.cpp`): Copy, Copy command, Copy history, Save history as, Save history (across sessions), Paste, Select all, Clear console, Insert file name, Word wrap |
| Status bar | done: messages, the element under the mouse, checks, verdict, the navigation style switcher, and MainWindow's DimensionWidget: what the view spans in the user's unit system (`dimensionText`), its menu picks the unit system |
| Unit system (UnitsApi) | done: one setting (Preferences > General > Units, or the status bar) for everything that shows a quantity: parameters, placement, bounding box, measurements, QuickMeasure, preselection, the view's size. Schemas are numbered as FreeCAD numbers them (`UnitsSchemas::getVec` sorts by number) |
| Selection view (`SelectionView.cpp`) | done: the selection as `doc#object.element (label)`, the count, search by label (Enter selects the matches), double-click toggles, hover preselects, the item menu (Select only, Deselect, Zoom fit, Go to selection, Mark to recompute, To Python console), and the picked object list |

## Audit, 2026-09-30

Ten audits compared FreeCAD main 3160daf1e2b6 line by line with this UI, one area each (navigation styles, NaviCube and axis cross, Placement, Transform, quantities and expressions, menus and keys, tree/property/output panels, Measure/Mass/Units, task panel layouts, 3D view and selection). Their reports, and what each fix pass did with every item, are in the session's `scratchpad/parity/audit/` (`<area>.md`, `fixes-<area>.md`). Fixed in that pass, among the rest:

- Navigation: arrow keys move the camera a tenth of the view (SoQTQuarterAdaptor), before any style sees them; Page Up/Down as FreeCAD fires them; touchpad horizontal scroll rejection; Maya-Gesture and Siemens NX details.
- NaviCube: its menu (Orthographic, Perspective, Isometric, Fit all, Fit selection, Align to selection, Movable Navigation Cube), the fade to InactiveOpacity away from it, Arial labels, its own hover colour #AAE2FF, FreeCAD Light's base colour #F2F2F2, rotate to nearest, steps by turn (360°/n for arrows and rolls), size, corner and font from Preferences; moving it snaps to the nine places the cube library has (FreeCAD's is continuous).
- Placement: the stored pivot folded into the position (Center starts at zero), the rotation input remembered, incremental on/off composing as FreeCAD does, Selected Points on faces and edges too with its messages, the full message box, every field reset, "=" opens the Expression Editor; the layout as Placement.ui (Translation | Center side by side when there's room, Axis stacked, buttons at the bottom).
- Transform: one "Transform" box in TaskTransform.ui's order, OK and Cancel only, Local/Global/Custom with U/V/W, X/Y/Z, X′/Y′/Z′, the references and their Pick Reference / Cancel, the options frame behind Std_DlgParameter, the dragger's own axis labels and colours, the dragger unpickable while picking, FreeCAD's reference rules for the fields.
- Quantities and expressions: ^ right-associative in quantities and left in expressions, comparisons and a?b:c, FreeCAD's functions with their unit rules, comma decimals, 5' 3", the input diagnostics, stepping and keyboard of QuantitySpinBox.
- Menus and keys: Align to… in Edit, S,B / S,F / T,5 / ⌘⇧R / ⌘E, ⌘F in the tree, the status bar's order, the toolbars' order and defaults.
- Panels: booleans as check boxes; the property view's context menu (Copy, Expand/Collapse Properties, Show Hidden) and keys (arrows, F2/Return, Tab to the next field); the tree's search as itemSearch (the exact name, preselected and scrolled to, Return selects; nothing is hidden); the report view's Critical messages and labels; the console's menu rules, Esc and its 100-line history; Preferences as FreeCAD's pages; Clipping as Clipping.ui (and the side it keeps); Save image's aspect-ratio buttons.
- Measure: Show Delta, Additive Selection with FreeCAD's Ctrl/Shift rule, Radius winning the tie with Diameter, the unit list in the unit system's unit (mm²) and remembered, Reset; faces classified as discs, cylinders (full or a section) and spheres from the mesh, so QuickMeasure and Measure give diameters, radii and axis distances; the angle drawn as an arc; FreeCAD's measurement colours (60, 240, 0).
- 3D view: SelectionStyle BoundBox in the selection colours, preselected objects boxed too, no points in Hidden Line, the 0.2 mm vertex/edge preference, perspective Fit All at 45°.

Left at the time: pinch rotation and pan, and processClickEvent's double-click deferral. Both are done now (2026-10-01; see Navigation above).

## Audit, 2026-09-30 (second round)

Four fix passes closed what the first round left. Three re-checks (quantities and expressions, navigation styles, Placement and Transform) found no regressions in the first round's fixes. Notes are in `scratchpad/parity/audit/fixes2-*.md` and `regress-*.md`.

- Overlay panels: FreeCAD's auto modes (None, Auto hide, Show on edit, Hide on edit, Auto task), the edge hint and hover reveal, the 200 ms InOutCubic slide, and the overlay title bar (Transparent, auto mode, Overlay, toggle) with FreeCAD's overlay icons.
- Tree: preselection after PreSelectionDelay (700 ms) with the PreSelectionTimeout debounce; no header and only the label column by default (HideColumn, HideInternalNames), with Tree Settings > Show Description / Show Internal Name.
- Property view: no header (setHeaderHidden); the Property/Value boundary drags from any row within 5 px; FirstColumnSize is remembered.
- Mass properties: TaskMassProperties' five boxes; a custom reference with an orientation (a picked planar face stands in for an LCS); centres shown relative to it; Reset keeps the mode; "(Average)" density; every value written as setText does (Fixed, the unit system's decimals, the schema of the Units box; anything under 1e-7 shows as 0).
- 3D view: the rotation centre indicator follows its preferences (size, colour, alpha); distance measurements have extension lines, an offset dimension line and cross markers; angle arcs have arrowheads; the NaviCube goes anywhere (continuous position, dragged 1:1) and shows its ShowCS axes.

## Audit, 2026-10-01 (third round)

Every change since was compared with FreeCAD's source again (`regress2-*`, `regress3-*` notes), and what they found was fixed after checking each finding against the source:

- Measurements: FreeCAD's base look for Length, Position, Diameter, Radius, Area and Geometric Center (a leader line and a cross, the label at its end), 2 px and 1 px line weights, angle arcs with spokes at FreeCAD's radius, saved measurements keep their drawing; the NaviCube's ShowCS axes are 2.2 px solid lines with caps and depth-tested, and its drag is FreeCAD's absolute drag from the press point.
- Widgets as FreeCAD.qss paints them under FreeCAD Light (checked rule by rule, tokens resolved from `FreeCAD Light.yaml`): check boxes and radio buttons with the images_classic marks, scroll bars (framed track, gradient handle, arrow buttons), sliders, buttons (white on hover, black border pressed), tool buttons (inset when pressed, the checked colours), spin boxes (one accent ring, white button hover), combo boxes, header sections, task boxes, group boxes (#c5c5c5, 5 px), the menu bar's MenuBackgroundColor, menu separators, no status bar dividers, tree indentation 12; tooltips are QToolTips (bold on PrimaryColor, 1.5 px border, 5 px radius; 700 ms wake-up, 2 s fall-asleep, cursor + (2, 16)).
- Part shapes' Deviation and Angular Deflection are editable and re-tessellate (ViewProviderPartExt; FreeCAD's out-of-the-box 0.2 % and 28.65°), from the View tab, `cad gui set` or a macro; Transparency steps by 1; the report view's time stamps are hh:mm:ss.
- Status bar as MainWindow.cpp's registry: the preselection text exactly as getPreselectionInfo writes it, the Bottom Panel Toggle button (order 700, checkable, approximate state like FreeCAD's), and the right-click menu listing every item by title in bar order, each checkable and remembered (buildStatusBarContextMenu / setStatusBarItemEnabled).
- Combo boxes are QComboBoxes now, not native selects: FreeCAD.qss's popup (opens below or above, at least the box's width, the current item marked, 10 visible then scrolling), its keys (Up/Down step a closed box without opening, Alt+Down/F4/Space/Enter open, Home/End/PageUp/PageDown, type-ahead, Esc), and the wheel on a focused box.
- Status bar extras from FreeCAD main: Input Hints (InputHintWidget; TaskMeasure's "⇧ auto-save" and "⌘ add to measurement", keycaps as generateKeyIcon draws them) and the SequencerBar busy indicator while the scene rebuilds or a command runs.
- Notification Area (NotificationArea.cpp, order 800): warnings, errors and critical messages become notifications (unread badge, the tray icons), the list with its Delete / Delete User Notifications / Delete All menu, non-intrusive balloons with FreeCAD's timing, and its Preferences page.
- Preferences: Show FPS (SoQTQuarterAdaptor's readout), axis colours (corner cross, dragger, ShowCS, Std_AxisCross), the new-document camera height, Show axis cross; image size and turntable timeout minimums.
- Menus: every label is FreeCAD main's sMenuText (Title Case, "…" only where FreeCAD has it), across the menus, the toolbars' tips, context menus, the NaviCube menu (its commands' own labels) and task titles; File, Macro and Windows menus as Workbench.cpp lists them; workbench menus sit between Macro and Windows.

## Working together (the CLI behind the UI)

FreeCAD has one person and a Python console. Here a person in the UI and an agent in a terminal share one project through the same `cad` commands:

| FreeCAD | Ours |
|---|---|
| Python console | runs any `cad` command and prints what a terminal prints; echoes each UI edit as its `cad` line |
| Report view | also lists every command the agent runs (the activity log) and its `cad gui say` messages |
| Gui.Selection, Visibility, ViewObject properties, SendMsgToActiveView | `cad gui state / select / clear / show / hide / set / view / fit`: the agent reads and drives what the person sees; visibility, colours and selectability persist in `out/gui.json` (GuiDocument.xml's job) |
| Document undo (Std_Undo / Std_Redo, the toolbar dropdown) | one journal for both: UI edits and the agent's `cad set` / `cad place` / bought parts, 20 steps, `cad undo` / `cad redo` / `cad history` |
| Macros (Std_DlgMacroRecord, Macros, Recent Macros, Execute Macro) | macros are `cad` command files in `~/.cad-agent/macros/`; recorded from the UI (GUI lines as comments by default, as FreeCAD's RecordGui / GuiAsComment), read and run by the agent with `cad macro show / run` |
| File > New, Open, Recent Files | `cad init` and the projects the workbench serves |
| Addon workbench | the CAD Agent workbench: check, verify, done, cut list, tables, tool envelopes, bought parts, renders, approvals, rules |

## Checked against the real FreeCAD, 2026-10-01

FreeCAD's weekly build of main at exactly 3160daf1e2b6 (`weekly-2026.09.30`, reports 26.3.0dev) lives in `~/.cad-agent/freecad/FreeCAD.app`. Two scripts run it with its user files in a temporary folder:

- `python3 scripts/fcdiff.py [suite…]` puts the same cases through `freecadcmd` and through our TypeScript (bundled for Node) and prints every disagreement; exit 1 if any. Suites: `schemas`, `parse` (Quantity.l / Quantity.y), `user` (UnitsSchema::translate: 39 units × 47 values × 10 schemas × 0/2/4 decimals, plus fractional inches), `number` (Quantity::toNumber), `rotation` (getYawPitchRoll, getRawValue, getEulerAngles in all 26 sequences), `ypr` (setYawPitchRoll), `euler` (setEulerAngles). All pass; the only accepted differences are FreeCAD's undefined behaviour (toDMS casting angles past INT_MAX to int).
- `node scripts/navcheck.mjs` needs no FreeCAD. It runs FreeCAD's own `NavigationStylePinchTest.cpp` cases against our `pinchAction`. It also drives the double-click deferral, touchscreen pinches, pans and twists, Ctrl+wheel and Safari gestures, and Alt+scroll through fake DOM events, once as a Mac and once as another system. 72 checks, all pass.
- `python3 scripts/fcgui.py` runs FreeCAD's GUI on Qt's offscreen platform and dumps every command's menu text, tooltip, status tip and shortcut, the menus and toolbars of three workbenches, the docks and the status bar widgets, with screenshots, to `~/.cad-agent/freecad/reference/`.

What the first runs found and fixed:

- **Rotation readouts** (Placement and Transform panels) used three.js's Euler maths, which locks gimbal at a different threshold and puts the angle in yaw instead of roll. `rotation.ts` is now Base::Rotation line by line (its OCCT Shoemake code for all sequences). 3,350 cases match.
- **Number formatting**: FreeCAD main formats quantities with ICU, which rounds the double's shortest decimal digits half to even (9.995 → 10.00, 0.5 → 0 at 0 decimals); we used `toFixed`. `formatFixed` ports it; 55,407 of 55,413 unit cases match, the rest being the undefined behaviour above.
- **Parser**: "5." and "1.e3" are numbers (Quantity.l); `unit^num` raises the unit to the exponent truncated to `signed char` (so "1 m^0.5" is a plain number), as Quantity::pow does; a stray non-ASCII character ends the input (a negative token is bison's end of input); every syntax failure says "syntax error"; empty input is DBL_MIN, not JS's MIN_VALUE.
- **Measurement labels** in a chosen unit: MeasureBase::formatQuantity writes Quantity::toNumber at the user's decimals, `%g` between -1 and 1 (0.5 m shows "0.5 m", not "0.50 m"); we printed `toFixed(2)`.
- **Shared GUI state**: opening a project could publish its empty defaults before loadGui returned, overwriting a saved `out/gui.json`, and a reconnect republished stale visibility over the agent's newer change. Both fixed; the server's copy of hidden / unselectable / view properties now wins until it has been read.

Then, against the GUI dump (`freecad-gui.json` from `scripts/fcgui.py`; `scripts/menudiff.js` reads every menu off the page and diffs it against FreeCAD's):

- **Menus**: 99 differences down to the expected ones: FreeCAD's Part-only entries (Edit > Create, Appearance per Face), its installed workbenches, our Checks panel and CAD Agent toolbar, About cad-agent, and the console kept as "Console" / "Send to Console" (it runs `cad`, not Python). Shortcuts are the macOS ones (qplatformtheme.cpp's bindings: Close ⌘W, Redo ⇧⌘Z, Delete ⌦, Next/Previous Window ⌘} / ⌘{), modifiers in macOS order (⌥⇧⌘S). Fixed: command ids (Std_Properties, Std_TreeCollapseDocument, Std_MainFullscreen vs Std_ViewFullscreen, Std_DockOverlayToggle), title case (As Is, Hidden Line, No Shading, Flat Lines, Part Tools, Report View, Selection View), Edit's clipboard group (Copy puts the selection's names on the clipboard; the rest are n/a), Recompute F5, View's New 3D View, Freeze Display (Freeze View ⇧F, Restore View N ⌘N, Save/Load Views as FreeCAD's .cam XML), Document Window (Docked V,D, Fullscreen F11), Issue Camera Position, Texture Mapping, Toggle Navigation/Edit Mode, Material, Appearance, Link Navigation, Overlay Docked Panel, Initiate Dragging, the workbench list in internal-name order with W,1…, Tools' Addon Manager / Python Package Manager, Help's Start Page and Python Modules Documentation, Windows' numbered entries, Open Recent's Clear Recent Files, an empty Recent Macros, File > Export… (⌘E) as FreeCAD's save dialog with its filters (STEP with colors, STL Mesh, WebGL for the review page) and its "No Selection" warning.
- **Cameras**: "GetCamera" / "SetCamera" ported (Coin's camera node text). `cad gui view PROJECT '<camera>'` takes what Issue Camera Position prints, and the UI publishes its camera node as it settles (`cad gui state` shows it), so either side can save and restore the other's exact viewpoint.
- **Toolbars**: StdWorkbench's set and order (File, Edit, Clipboard, Workbench, Macro, View, Individual Views, Structure, Help) on the first row and the workbench's own on a second (ToolBarManager's toolbar break), Clipboard/Macro/Individual Views hidden by default, the 8px handle each toolbar starts with (hidden by Lock Toolbars), ToolbarIconSize 24 (ToolBarManager's default) in 32x31 buttons, 39px rows, as measured in the real FreeCAD.
- **Start page**: StartView ported (New File cards, Recent Files with each project's newest render and size, First Start Setup, "Do not show this Start page again"); a "Start" tab before the 3D view at startup, Help > Start Page (Start_Start).
- **Status bar**: 34px; the bottom-panel toggle, the notification button with its unread count, Tux's navigation indicator (style icon, Settings > Orbit style / Compact / Tooltip, every style), the Dimension button with its unit-system menu, the size grip.
- **Tree**: 18px rows, children 22px in, the eye (TreeItemVisible/Invisible) before the icon, the selection bar as wide as the widest item (column 0 sized to contents with HideColumn), the active document bold.
- **Property view**: 20px rows, group rows without an arrow (drawBranches), Placement as one row under Base in PropertyPlacementItem's format with Angle / Axis / Position under it, vectors as PropertyVectorItem / PropertyVectorDistanceItem write them; View > Display Options' Show Placement (SoFCPlacementIndicatorKit's axis cross), settable from `cad gui set … ShowPlacement=true`.
- **Appearance** (⌘D, Std_SetAppearance): TaskDisplayProperties ported — Viewing Mode, Material (Default only; Custom appearance edits the shape colour), Display (point size and line width 1–64, transparency), Close only; live on the selection, runnable by the agent.
- **Selection filter** (Part_SelectFilter in the View toolbar: Vertex / Edge / Face Selection, No Selection Filters): a gate on preselection and selection, refusals shown as SelectionSingleton's "Not allowed: doc.obj.sub " with the forbidden cursor; `cad gui run … Part_EdgeSelection` sets it.
- **Context menus**: the 3D view's (object actions, Clarify Selection, Link Actions, Fit/Align/Draw Style/Standard Views, Document Window with Docked/Undocked/Fullscreen, the selection commands, Delete, Send to Console, Transform/Placement) and the tree's (Toggle Freeze, the visibility group, colours, Cut/Copy/Paste/Delete, Send to Console, Transform/Placement, then Tree.cpp's own) in StdWorkbench::setupContextMenu's order.
- **Layout**: the document tabs (Start, "name : 1") under the views, as the tabbed MDI area has them, with FreeCAD.qss's close icons; a dock group with one panel drawn as that QDockWidget's title bar (Model on its own, title centred); the Tasks dock only while a task is open, tabbed with Model.
- **Preferences** (Std_DlgPreferences, ⌘,): the modal dialog of DlgPreferences.ui — groups and pages in a tree with their 24px icons (General: General, Document, Selection, Keyboard, Cache, Notification Area, Report View; Display: 3D View, Light Sources, UI, Navigation, Colors, Advanced, Transform snap; Workbenches: Available Workbenches; Import-Export: PDF; Python: Macro, General, Editor — the pages that apply here, in resource.cpp's order), the page header and "Search preferences…" (every label, shown as page over text), Reset with its menu (Reset Page '…', Reset Group '…', Reset All after "Clear User Settings"), OK / Apply / Cancel; settings show as they change, Cancel puts back what Apply last kept. DlgSettingsSelection's page is new (its tree options, colours and enables; the pick radius shown as fixed). Each page was diffed label by label against its .ui (General, Notification Area, Report View, 3D View, Navigation, Macro: nothing missing but combo items that only exist while a list is open); General now has FreeCAD's three groups (unit system, decimals, fractional inch, toolbar icon size 16/24/32/48 and recent file list size work; language, number format, theme, splash, recompute options and preference packs show disabled), 3D View its Rendering group (fixed by WebGL, shown disabled), Macro its four groups (macro path, GUI recording and the recent list size work), and Report View is new (record and show-on per level, timecode, colours; the Python redirects n/a). Deliberately different: log messages are recorded by default, since the agent's activity is logged at that level. Display > Colors is new: DlgSettingsViewColor.ui's three groups, with its behaviour (the radios swap the simple colour for the gradient's, the labels read Central/Midway/End for a radial gradient, Switch swaps the first and last colours, Middle color enables the middle one). The background is SoFCBackgroundGradient ported: the same triangles in clip space (one quad, or two with a middle colour; a 32-segment fan to a circle of radius √2, or to the 0.3√2 × √0.5 inner ellipse and a ring with a middle colour), drawn two-sided as UNKNOWN_SHAPE_TYPE makes Coin do, with its dithering shader. Read back from the canvas, the colours land where the geometry puts them (within the ±2/255 dither). Save picture keeps the gradient with "Current". Fixed with it: radio buttons on the pages had a shared group name with their copies in the search index, so the 3D View page's Perspective/Orthographic pair could show neither checked.
- **Colours checked against the running FreeCAD Light**: SelectionColor 0x00abff, HighlightColor 0x0ac8ff, BackgroundColor #f7f7f7, DefaultShapeColor #adb5bd, line black, vertex #191919 — all as ours.
- Deliberately different: stock bodies keep cad-agent's aluminium grey (#aab1b9) instead of DefaultShapeColor (#adb5bd); bodies are coloured by kind.

Still to compare: the 3D view's own rendering (no GL offscreen to take a reference from). The Report View stays shown by default (FreeCAD's fresh profile hides the bottom docks) since it is where the agent's messages land.

## Light Sources, 2026-10-01

- **Preferences > Display > Light Sources** (`DlgSettingsLightSources.ui/.cpp`, `View3DSettings.cpp`, `View3DInventorViewer.cpp` at 3160daf1e2b6), between 3D View and Navigation as resource.cpp orders it. Main light, Backlight and Fill light each have enable, horizontal and vertical angle (azimuth/elevation, converted to and from the stored direction as `azimuthElevationToDirection`/`directionToAzimuthElevation` do), colour and intensity; Ambient light has colour and intensity. Defaults are View3DSettings' (90/60/40/20 %, #FFFFFF/#F5F5EE/#E6FAFF/#FFFFFF, its three default directions). Preview is configureViewer's sphere (radius 3, createMaterial's #D2D2FF diffuse, #CCCCCC specular, shininess 0.9) through an orthographic camera along (0, 1, 0.3) at twice viewAll's height, with Pushes in / Pulls out stepping a 14th of it, over the view's background. `lights.ts` replaces three-cad-viewer's two lights with this rig in the 3D view.
- Deliberately different: all three lights follow the camera (their directions are in the camera's frame), as the headlight does in Coin; intensities are π × FreeCAD's fraction, which gives Coin's Lambert shading under three's physically based lights; ambient light lights the diffuse colour, since three's materials have no separate ambient colour (FreeCAD's 0x333333). The 3D view's materials stay three-cad-viewer's MeshStandardMaterial (the preview sphere is Phong, like Coin's). Directions are stored as soon as they change, like every page here, not on OK.
- **Preferences > General > Selection** colours: SelectionColor and HighlightColor are colour buttons beside Enable selection / Enable preselection (DlgSettingsSelection.ui's grid), defaulting to #00ABFF / #0AC8FF. They drive every highlight in the 3D view (whole objects, sub-elements, bounding boxes) and change it live; unticking an enable stops that highlight, as SoFCEnableSelectionAction / SoFCEnablePreselectionAction do. Radius stays disabled (n/a: picking is three-cad-viewer's ray cast).
- **Preferences > Display > UI** (`DlgSettingsUI.ui`, TreeParams.py/.cpp, Tree.cpp at 3160daf1e2b6), after Light Sources as resource.cpp orders it. Tree View works live: Font size (onFontSizeChanged: 0 keeps the default, else at least 8 pt), Icon size (getIconSize: 0 is 16, else at least 10), Show visibility icon, Resizable columns (header grips; widths kept like ColumnSize1-3, the last column stretches), Hide description / Hide internal names (the same settings as the tree's Tree Settings menu), Hide scroll bar and Hide header (both only while the tree is a dock overlay, as TreeParams documents). Overlay: Hide property view scroll bar works; the tab bar and pass-through options are shown fixed, auto-hide in non-3D views n/a. Theme Customization (FreeCAD Light's accent colours and style sheets) and Suggested Actions are shown disabled (n/a: one theme, no task watcher).
- **Preferences > General > Document** (`DlgSettingsDocument.ui`), after General as resource.cpp orders it. Maximum undo/redo steps works and is CLI-first: `cad pref MaxUndoSize N` (userprefs.py, `~/.cad-agent/preferences.json`) caps the shared undo journal (undo.py), and the page reads and writes the same store over `/api/prefs`, so the agent's `cad undo` and the page's Edit > Undo see one limit; 0 keeps nothing, as FreeCAD's 0 turns undo off. Cancel and Reset Page put it back too. Everything else on the page (recompute, FCStd storage, backups, thumbnails, labels, authoring and licence) is shown disabled with why it's n/a.
- **Preferences > Python > General** (`DlgSettingsPythonConsole.ui`, shown as "General" as FreeCAD titles it) and **Editor** (`DlgSettingsEditor.ui`), after Macro as resource.cpp orders them. The console follows Enable word wrap (now on by default, PythonWordWrap's default; it was off), Enable block cursor and Save history, the same settings as its own menu's Word Wrap and Save History. The console and the macro editor follow the Editor group: font family and size (10 pt), the Text, Python output and Python error colours (FreeCAD Light.cfg's #212529, #D9480F, #A61E4D; the console's output was grey before), Tab size, and Tab inserting Indent size spaces or a tab (Insert spaces / Keep tabs, TextEdit's keyPressEvent); the editor's block cursor too. Display Items lists every item with FreeCAD Light's colours, with a preview. Different: a browser can't list installed fonts, so Family offers the system fixed font and common monospace families; line numbers, folding and the syntax colours are n/a (the editor here is plain text), as are the profiler interval and the Python executable (no Python here).
- **Preferences > Display > Advanced** (`DlgSettingsAdvanced.cpp`, generated from OverlayParams.py), after Colors as resource.cpp orders it: its Overlay grid with OverlayParams' ranges, steps and suffixes. The overlay now reads them instead of hardcoded defaults: hint trigger size and width, the left and bottom panels' hint offset and length (the hint strip is now FreeCAD's default 100 px long, not the whole edge; 0 fills it), hint delay, Activate on hover (off: a click on the hint reveals the panel) and the auto-hide animation's duration and curve (all 41 QEasingCurve names; Linear, the Quad/Cubic/Quart/Quint/Sine/Expo/Circ/Back In/Out/InOut curves as their standard cubic-béziers, OutIn, Elastic and Bounce as their nearest InOut/Back fit, since CSS has no cubic-bézier for them). Right/top panel hints are n/a (only left and bottom panels overlay here); the wheel and click pass-through, navigation-cube spacing, splitter and layout timings are shown fixed.
- **Preferences > General > Keyboard** (`Dialogs/DlgKeyboard.ui`, `DlgKeyboardImp.cpp`, `ShortcutManager.cpp`), after Selection as resource.cpp orders it: Multi-key sequence delay, the search box, Category, the command list (Command, Shortcut, Default), Current and New shortcut (AccelLineEdit: up to four chords, Backspace clears), Assign / Clear / Reset / Reset All and the Priority List. Any registry command can get a shortcut (`keymap.ts`): a user shortcut runs before App.tsx's own bindings, a changed command's default keys stop doing anything, a key that is both a shortcut and the start of a longer one waits ShortcutTimeout (300 ms) as ShortcutManager does, and menus show the new keys. Shortcuts are stored as portable text ("Ctrl" is ⌘ on a Mac) and shown as native text. Different: no categories (All only), and Move Up/Down are disabled because a shared shortcut runs the first command that has it.
- **Preferences > General > Cache** (`DlgSettingsCacheDirectory.ui/.cpp`, ApplicationCache), after Keyboard as resource.cpp orders it, CLI-first: `cad cache [--clear]` (appcache.py) reports the user cache (the warm worker's `~/.cache/cad-agent`) and its size against CacheLimit, and clears what no running worker uses (as clearDirectory keeps lock files and open documents). The page shows the location, Check periodically at program start (CachePeriod, Weekly) and Cache size limit (CacheLimit, 500 MB, the same items), the current size in ApplicationCache::toString's format and Check Now, which offers to clear an over-limit cache with FreeCAD's message; the page runs the same check at start-up when the period has passed. Browse cache directory is n/a in a browser.
- **Preferences > Workbenches > Available Workbenches** (`DlgSettingsWorkbenches.ui`, `DlgSettingsWorkbenchesImp.cpp`), its own group between Display and Python as resource.cpp orders it: a row per workbench (enable, icon, name, its W, n key, Auto-load, Loaded), reordered by drag and drop or Sort Alphabetically, disabled ones listed after; the order and the disabled list drive the toolbar selector, View > Workbench and W, 1-9. Selectors: item style (Icon and text / Icon / Text) and selector type (ComboBox or TabBar, which here switches at once rather than after a restart). Startup: Default workbench (the one shown at start, which must stay enabled). Auto-load and Remember active workbench by tab are n/a (every workbench is part of the page; one 3D view).
- **Preferences > Import-Export > PDF** (`DlgSettingsPDF.ui/.cpp`), its own group as resource.cpp orders it: PDF version with its four versions and the note under it, shown disabled (n/a: Export PDF is the browser's Save as PDF, which picks the version). With it every preference page FreeCAD's resource.cpp registers is here.

## Still missing

- Nothing from FreeCAD's standard menus, toolbars, context menus, keys or panels that applies to these projects. What is left is n/a (no FreeCAD document, sketcher or feature tree) or listed as n/a above.

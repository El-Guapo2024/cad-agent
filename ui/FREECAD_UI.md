# FreeCAD Desktop UI Port Spec for React

**Target: FreeCAD main (nightly) at 3160daf1e2b6, 2026-09-29** (the code behind the weekly builds; nearest installable build: weekly-2026.09.23). This spec was first written against tag 1.1.4. Between the two, the only changes that matter to the port are the colours below, taken from main; the icons we use are identical.

| Setting | 1.1.4 | main |
|---|---|---|
| Preselection (View/HighlightColor) | #007A00 | #0AC8FF |
| Selection (View/SelectionColor) | #3B5BDB | #00ABFF |
| Accent (Themes/ThemeAccentColor1) | #4AA5FF | #00ABFF |
| Edge colour (View/DefaultShapeLineColor) | #191919 | #000000 |
| NaviCube | size 132, BaseColor #E2E8EF at 75% | same |

**Target Release:** FreeCAD 1.1.4 (Sept 28, 2026)  
**Default Theme:** Light  
**Source:** github.com/FreeCAD/FreeCAD/releases/1.1

---

## 1. Licences

| Component | Licence | Source | Reuse Policy |
|-----------|---------|--------|--------------|
| **FreeCAD Core Code** | LGPL-2.1-or-later | [LICENSE](https://github.com/FreeCAD/FreeCAD/blob/releases/1.1/LICENSE) | Reciprocal copyleft; modifications require source disclosure. |
| **SVG Icons (src/Gui/Icons)** | LGPL-2.0-or-later | Each SVG's metadata: `FreeCAD LGPL2+` (checked edit-undo.svg, PartDesign_Body.svg @1.1.4) | Keep each file's metadata. |
| **Workbench Icons (src/Mod/*/Gui/Resources/icons)** | LGPL-2.0-or-later | Same per-file metadata | Same. |
| **Qt Stylesheets (.qss files)** | LGPL-2.1 | [Stylesheets dir](https://github.com/FreeCAD/FreeCAD/tree/releases/1.1/src/Gui/Stylesheets) | LGPL-2.1; theme parameters in YAML are derivative works. |

**Reuse verdict (checked):** icons, stylesheets and ported code can all ship in cad-agent. Copied files keep their metadata and sit with the LGPL text and a credit line. Code translated from FreeCAD (C++ to TypeScript, .qss to CSS) is a derivative work: each such file gets `SPDX-License-Identifier: LGPL-2.1-or-later` and names its FreeCAD source file. The repo will be public, which covers the source requirement; it needs a licence first (LGPL-2.1-or-later for ui/ at least).

---

## 2. Default Layout at First Start

| Panel | Initial State | Dock Position | Tabs | Default Width/Height |
|-------|---------------|---------------|----|-----|
| **Combo View** | Visible | Left | Model tree (active), Tasks, Selection | 300–350px |
| **Model Tree** | Visible | In Combo View (tab 0) | N/A | Inherits |
| **Property Editor (Data/View)** | Visible | In Combo View (below tree, splitter) | Data, View | Inherits |
| **Tasks Panel** | Hidden, shown on task | In Combo View (tab) | Task-specific | Inherits |
| **Report View** | Hidden or bottom | Bottom | Messages, Python | 150–200px height |
| **Python Console** | Hidden | Bottom (tab) | Code, Output | Inherits |
| **Selection View** | Hidden | Combo View (tab) or dedicated panel | Selected objects | Inherits |
| **3D View** | Central | Center (MDI) | Document tab (e.g., "Document") | Remainder |

**Source:**
- ComboView layout: [src/Gui/ComboView.cpp](https://github.com/FreeCAD/FreeCAD/blob/releases/1.1/src/Gui/ComboView.cpp) lines 30–60 (QSplitter, Tree, PropertyView)
- Tree visibility: [src/Gui/Tree.cpp](https://github.com/FreeCAD/FreeCAD/blob/releases/1.1/src/Gui/Tree.cpp)
- StatusBar and MainWindow: [src/Gui/MainWindow.cpp](https://github.com/FreeCAD/FreeCAD/blob/releases/1.1/src/Gui/MainWindow.cpp)

**UNVERIFIED:** Start page appearance, exact default dock order per platform.

---

## 3. Theme: Colours, Fonts, Spacing

### Light Theme (Default)

**Base Palette** (`src/Gui/Stylesheets/parameters/FreeCAD Light.yaml`):

| Token | Hex | Usage |
|-------|-----|-------|
| PrimaryColor | `#F0F0F0` | Window, panel backgrounds |
| TextForegroundColor | `#000000` | All text |
| GeneralBorderColor | Darken PrimaryColor 20% | Borders, dividers |
| AccentColor | @ThemeAccentColor1 (UNVERIFIED: ~`#0078D4`?) | Active selection, highlights, focused buttons |
| TextEditFieldBackgroundColor | Lighten PrimaryColor 4% | Input fields, editable cells |
| GeneralDisabledBackgroundColor | Darken PrimaryColor 10% | Disabled controls |
| GeneralHeaderBackgroundColor | Darken PrimaryColor 8% | Tree headers, section titles |
| MenuBackgroundColor | Lighten PrimaryColor 2% | Menu and dropdown backgrounds |
| TabbarBackgroundColor | Darken PrimaryColor 20% | Tab bar background, inactive tabs |
| ScrollbarBackgroundColor | Darken PrimaryColor 10% | Scrollbar thumb |
| TextSelectBackgroundColor | Blend with AccentColor | Text selection highlight |

**Fonts & Spacing** (Qt defaults; UNVERIFIED):
- **Font:** System default (Windows: Segoe UI; Linux: Noto Sans; macOS: San Francisco)
- **Size:** 10–11pt body, 9pt tooltips
- **Line height:** 1.4em
- **Margins:** 2–4px container padding, 0–2px inter-element spacing
- **Border radius:** 3px (InputFieldBorderRadius)

[FreeCAD Light YAML](https://github.com/FreeCAD/FreeCAD/blob/releases/1.1/src/Gui/Stylesheets/parameters/FreeCAD%20Light.yaml) | [Main QSS](https://github.com/FreeCAD/FreeCAD/blob/releases/1.1/src/Gui/Stylesheets/FreeCAD.qss)

### Dark Theme (for reference)

| Token | Hex | Usage |
|-------|-----|-------|
| PrimaryColor | `#323232` | Window background |
| TextForegroundColor | `#FFFFFF` | Text |
| GeneralBorderColor | Darken PrimaryColor 200% | Borders |
| TabbarBackgroundColor | Darken PrimaryColor 200% | Tab bar |

[FreeCAD Dark YAML](https://github.com/FreeCAD/FreeCAD/blob/releases/1.1/src/Gui/Stylesheets/parameters/FreeCAD%20Dark.yaml)

---

## 4. 3D View Defaults

Colours below are decoded from FreeCAD 1.1.4's preference packs (Light, Dark, Classic). Which pack a first start applies is UNVERIFIED.

| Property | Value | Source |
|----------|-------|--------|
| **Background** | Light: solid #F7F7F7. Dark: solid #1F1F1F. Classic: gradient #333365 to #9797AA. No pack: gradient #333365 to #ABABC1 | PreferencePacks/<pack>/<pack>.cfg @1.1.4; View3DSettings.cpp:399,519-524 |
| **Preselection Highlight** | Light #007A00, Dark #246EAB, Classic #E1E114 (yellow) | PreferencePacks/<pack>/<pack>.cfg @1.1.4 (packed RRGGBBAA) |
| **Selection Colour** | Light #3B5BDB, Dark #35A047, Classic #1CAD1C (green) | PreferencePacks/<pack>/<pack>.cfg @1.1.4 |
| **Default Shape Colour** | Light #ADB5BD, Dark #727980, Classic #CCCCE6; line colour #191919 | PreferencePacks/<pack>/<pack>.cfg @1.1.4 |
| **Line Width** | UNVERIFIED | |
| **Navigation Cube (NaviCube)** | | |
| — Position | Top-right corner, inset 10–20px | [NaviCube.cpp](https://github.com/FreeCAD/FreeCAD/blob/releases/1.1/src/Gui/NaviCube.cpp): viewport coordinates |
| — Size | 132px (cubeWidgetSize) | NaviCube.cpp: `static int cubeWidgetSize = 132;` |
| — Face/Edge/Corner Colors | X=Red(1,0,0), Y=Green(0,1,0), Z=Blue(0,0,1) | NaviCube.cpp: hardcoded RGB |
| — Base/Highlight/Emphasis | Theme-dependent (UNVERIFIED colors) | NaviCube.cpp: `baseColor`, `emphaseColor`, `hiliteColor` |
| — Click Behaviour | Face click: view along axis; Edge/Corner: rotate to iso/dimetric | [NaviCube.cpp](https://github.com/FreeCAD/FreeCAD/blob/releases/1.1/src/Gui/NaviCube.cpp) (UNVERIFIED exact logic) |
| **Axis Cross** | Origin; X=Red, Y=Green, Z=Blue | [AxisOrigin.cpp](https://github.com/FreeCAD/FreeCAD/blob/releases/1.1/src/Gui/AxisOrigin.cpp) |
| **Default Navigation Style** | CAD (`CADNavigationStyle`), not Inventor | View3DSettings.cpp:292 @1.1.4 |

---

## 5. Behaviour

### Tree Panel

| Feature | Behaviour | Source |
|---------|-----------|--------|
| **Visibility Toggle** | **Space** key toggles; eye icon double-click toggles | [Tree.cpp](https://github.com/FreeCAD/FreeCAD/blob/releases/1.1/src/Gui/Tree.cpp): `toggleVisibilityInTreeAction`, `visibilityIconDoubleClickTimer` |
| **Eye Icon** | Visible when Visibility parameter enabled; hides element tree-wide if unchecked | Tree.cpp: `isVisibilityIconEnabled()` |
| **F2** | Rename/relabel object inline | Tree.cpp: `relabelObjectAction->setShortcut(Qt::Key_F2)` |
| **Double-Click** | Opens object's edit task (e.g., Pad dialog in Part Design) | UNVERIFIED |
| **Context Menu** | Rename, Delete, Mark to Recompute, Toggle Visibility, Show/Hide, Copy, Paste | [Tree.cpp](https://github.com/FreeCAD/FreeCAD/blob/releases/1.1/src/Gui/Tree.cpp): `contextMenu.addAction(...)` |
| **Overlay Icons** | Error/warning badges, "recompute needed" badge, hidden status | Tree.cpp: `overlay_*` icons |
| **Tree ↔ 3D Sync** | Click tree item → select in 3D; click 3D → highlight tree; Ctrl+Click multi-select | [Selection.cpp](https://github.com/FreeCAD/FreeCAD/blob/releases/1.1/src/Gui/Selection/Selection.cpp) |
| **Empty Space Click** | Deselects all | Standard GUI behaviour |

### Property Editor (Data/View Tabs)

| Property Type | Editor | Behaviour |
|----------------|--------|-----------|
| **Float (unit)** | Spin input + unit dropdown | Shows value with unit suffix (e.g., "10 mm"); right-click → expression editor |
| **Integer** | Spin input | No units; ±/scroll wheel |
| **Boolean** | Checkbox | Checked ↔ True/False |
| **Enumeration** | Dropdown | List of predefined values |
| **String** | Text field | Plain text input |
| **Placement** | Grouped/expandable row | Expands to: Angle, Axis (X/Y/Z), Position (X/Y/Z) as sub-fields |
| **Read-Only** | Disabled (greyed) text or button only | No text edit; often "..." button to open editor |

**Tabs:**
- **Data:** Object properties (Placement, Label, Material, etc.)
- **View:** Display properties (Color, Transparency, Line Width, etc.)

[PropertyEditor.cpp](https://github.com/FreeCAD/FreeCAD/blob/releases/1.1/src/Gui/propertyeditor/PropertyEditor.cpp)

### Task Panel

| Element | Behaviour |
|---------|-----------|
| **OK** | Accept and close task |
| **Cancel** | Reject and close task (undo changes) |
| **Apply** | Accept but keep panel open |
| **Layout** | Vertical stack; OK/Cancel/Apply at bottom |

[TaskDialog.pyi](https://github.com/FreeCAD/FreeCAD/blob/releases/1.1/src/Gui/FreeCADGui._TaskDialog.pyi)

### Report View

| Message Type | Colour | Context Menu |
|--------------|--------|--------------|
| **LogText** | Blue | Copy, Clear, Context-dependent |
| **Warning** | Orange (`#FFAA00`) | Same |
| **Error** | Red (`#FF0000`) | Same |
| **Critical** | Dark red | Same |

[ReportView.cpp](https://github.com/FreeCAD/FreeCAD/blob/releases/1.1/src/Gui/ReportView.cpp): `logCol = Qt::blue; warnCol = QColor(255, 170, 0);`

### Python Console

**Echo Behaviour:** GUI actions (e.g., rotate view, select object) are echoed as equivalent Python commands in the console. Example: `Gui.Selection.addSelection('Document', 'Body', 'Pad')`.

### Undo/Redo Naming

**Naming scheme:** Action name + context. Example:
- "Undo Pad" (after creating a Pad feature)
- "Undo Rotate View" (after rotating)
- "Redo Property Change" (after editing a property)

[CommandBase.cpp](https://github.com/FreeCAD/FreeCAD/blob/releases/1.1/src/Gui/CommandBase.cpp) (UNVERIFIED exact format)

### Preselection Status Bar Text

**Format:** `"<ObjectName>:<SubElement> (on <FeatureType>)"`  
Example: `"Pad:Face3 (on Pad)"` when hovering over a face.

[StatusBarLabel.cpp](https://github.com/FreeCAD/FreeCAD/blob/releases/1.1/src/Gui/StatusBarLabel.cpp) (UNVERIFIED exact text)

---

## 6. Keyboard Shortcuts

### Standard Views

| Action | Shortcut | Source |
|--------|----------|--------|
| **View Home (reset)** | `Home` | [CommandView.cpp](https://github.com/FreeCAD/FreeCAD/blob/releases/1.1/src/Gui/CommandView.cpp): StdCmdViewHome::sAccel |
| **Standard Views 1–7** | `V, 1` through `V, 7` | CommandView.cpp: Multi-keystroke sequences |
| **Perspective** | `V, P` | CommandView.cpp: StdPerspectiveCamera::sAccel |
| **Orthographic** | `V, O` | UNVERIFIED |
| **Isometric (View 0)** | `0` or `KP_0` | UNVERIFIED |

### Navigation & Drawing

| Action | Shortcut |
|--------|----------|
| **Fit All** | `V, F` or `Home` (contextual) |
| **Fit Selection** | `V, S` |
| **Draw Style 1 (AsIs)** | `V, 1` |
| **Draw Style 2–7** | `V, 2` through `V, 7` |
| **Undo** | `Ctrl+Z` |
| **Redo** | `Ctrl+Y` |
| **Toggle Visibility** | `Space` |

[CommandView.cpp](https://github.com/FreeCAD/FreeCAD/blob/releases/1.1/src/Gui/CommandView.cpp)

### Other Common Shortcuts

| Action | Shortcut |
|--------|----------|
| **Rename (in Tree)** | `F2` |
| **Select All** | `Ctrl+A` |
| **Copy** | `Ctrl+C` |
| **Paste** | `Ctrl+V` |

---

## 7. Icon Map (Latest Stable Release 1.1.4)

### Core UI Icons

| Concept | SVG Path | Release 1.1.4 |
|---------|----------|--------------|
| **Document** | `src/Gui/Icons/Document.svg` | ✓ |
| **Part/Body** | `src/Mod/PartDesign/Gui/Resources/icons/PartDesign_Body.svg` | ✓ |
| **Generic Solid Feature** | `src/Mod/Part/Gui/Resources/icons/Part_Feature.svg` | ✓ |
| **Imported STEP Part** | `src/Mod/Part/Gui/Resources/icons/Part_FeatureImport.svg` | ✓ |
| **Assembly** | `src/Mod/Assembly/Gui/Resources/icons/AssemblyWorkbench.svg` | ✓ |
| **Assembly Joint** | `src/Mod/Assembly/Gui/Resources/icons/Assembly_CreateJointFixed.svg` | ✓ |
| **Group/Folder** | `src/Gui/Icons/Group.svg` | ✓ |

### Standard Views

| View | Icon Path |
|------|-----------|
| **Isometric** | `src/Gui/Icons/Std_ViewHome.svg` (or view-isometric.svg) |
| **Front** | `src/Gui/Icons/view-front.svg` (UNVERIFIED exact name) |
| **Top** | `src/Gui/Icons/view-top.svg` (UNVERIFIED) |
| **Right** | `src/Gui/Icons/view-right.svg` (UNVERIFIED) |
| **Rear** | `src/Gui/Icons/view-rear.svg` (UNVERIFIED) |
| **Bottom** | `src/Gui/Icons/view-bottom.svg` (UNVERIFIED) |
| **Left** | `src/Gui/Icons/view-left.svg` (UNVERIFIED) |

### View & Navigation

| Action | Icon Path |
|--------|-----------|
| **Fit All** | `src/Gui/Icons/view-fit-all.svg` (UNVERIFIED) |
| **Fit Selection** | `src/Gui/Icons/view-fit-selection.svg` (UNVERIFIED) |
| **Draw Styles 1–7** | `src/Gui/Icons/DrawStyleAsIs.svg`, `DrawStyleWireframe.svg`, `DrawStyleFlatLines.svg`, etc. |
| **Perspective** | `src/Gui/Icons/view-perspective.svg` |
| **Orthographic** | `src/Gui/Icons/view-orthogonal.svg` (UNVERIFIED) |
| **Undo** | `src/Gui/Icons/edit-undo.svg` |
| **Redo** | `src/Gui/Icons/edit-redo.svg` |
| **Recompute/Refresh** | `src/Gui/Icons/view-refresh.svg` or `Std_MarkToRecompute.svg` |

### Object & Editing

| Action | Icon Path |
|--------|-----------|
| **Placement** | `src/Gui/Icons/Std_Placement.svg` |
| **Transform Dragger** | `src/Gui/Icons/Std_TransformManip.svg` |
| **Measure** | `src/Gui/Icons/view-measurement.svg` |
| **Toggle Visibility** | `src/Gui/Icons/Std_ToggleVisibility.svg` |
| **Eye (Visible)** | `src/Gui/Icons/view-eye.svg` (UNVERIFIED; may be embedded in Tree) |
| **Eye (Hidden)** | `src/Gui/Icons/Invisible.svg` (UNVERIFIED) |
| **Overlay: Error** | `src/Gui/Icons/overlay_error.svg` (UNVERIFIED) |
| **Overlay: Warning** | `src/Gui/Icons/overlay_warning.svg` (UNVERIFIED) |
| **Overlay: Recompute** | `src/Gui/Icons/overlay_recompute.svg` |

### Workbenches

| Workbench | Icon Path |
|-----------|-----------|
| **Part Design** | `src/Mod/PartDesign/Gui/Resources/icons/PartDesignWorkbench.svg` |
| **Assembly** | `src/Mod/Assembly/Gui/Resources/icons/AssemblyWorkbench.svg` |
| **Inspection** | `src/Mod/Inspection/Gui/Resources/icons/InspectionWorkbench.svg` |
| **TechDraw** | `src/Mod/TechDraw/Gui/Resources/icons/TechDrawWorkbench.svg` (UNVERIFIED) |

### Other

| Item | Icon Path |
|------|-----------|
| **Report View** | `src/Gui/Icons/report-view.svg` (UNVERIFIED) |
| **Python Console** | `src/Gui/Icons/python-console.svg` (UNVERIFIED) |
| **Preferences** | `src/Gui/Icons/preferences.svg` (UNVERIFIED) |
| **Screenshot** | `src/Gui/Icons/Std_ViewScreenShot.svg` |
| **Clipping Plane** | `src/Gui/Icons/Std_ToggleClipPlane.svg` |
| **Material** | `src/Gui/Icons/material.svg` (UNVERIFIED) |
| **Spreadsheet** | `src/Gui/Icons/spreadsheet.svg` (UNVERIFIED) |

[Icons Directory](https://github.com/FreeCAD/FreeCAD/tree/releases/1.1/src/Gui/Icons) | [PartDesign Icons](https://github.com/FreeCAD/FreeCAD/tree/releases/1.1/src/Mod/PartDesign/Gui/Resources/icons)

---

## 8. UI Differences: FreeCAD 1.0 vs. 1.1.4

| Feature | 1.0 | 1.1.4 | Change |
|---------|-----|-------|--------|
| **Theme System** | Single QSS + hardcoded colours | YAML parameter-driven theming | New system for easier customization |
| **NaviCube** | Present | Present, improved | Minor refinements (UNVERIFIED exact diff) |
| **Property Editor** | Single Data tab | Data + View tabs | Split for clearer organization |
| **Sketcher** | Traditional (Sketcher workbench) | Same | No major UI change (outside scope) |
| **Assembly Workbench** | Draft Assembly | New Assembly2 (beta in 1.0, stable in 1.1) | Major overhaul for Assembly 2 UI |
| **Python Console** | Available | Available | Same interface |
| **Tree Icons** | Minimal overlay | Enhanced overlay icons (error/recompute badges) | More visual feedback |

[1.0 Release Notes](https://github.com/FreeCAD/FreeCAD/releases/tag/1.0.0) vs. [1.1.4 Release Notes](https://github.com/FreeCAD/FreeCAD/releases/tag/1.1.4)

**UNVERIFIED:** Exact visual/behavioural changes between 1.0 and 1.1.4 UI; assume minimal changes in core UI panels.

---

## Open Questions

1. **What are the exact hex colours for NaviCube base, emphasis, and highlight states?** They are theme-dependent and computed in NaviCube.cpp; defaults not found in stylesheets.

2. **What is the exact preselection status-bar format and message construction?** Logic likely in StatusBarLabel or MouseSelection; precise format unconfirmed.

3. **Which FreeCAD/Tango/FreeDesktop icons in src/Gui/Icons are licensed separately (CC-BY-SA vs. LGPL)?** Icon headers show LGPL, but attribution/source tracking incomplete.

4. **How does the tree overlay (error/warning/recompute badges) rendering work?** Expected to be icon compositing; no compositing code found in Tree.cpp.

5. **What is the exact behaviour of Ctrl+Click in the tree and 3D view for multi-select?** Selection logic in Selection.cpp is extensive; precise modifiers unconfirmed for all cases.

6. **What are the default 3D view background gradient and lighting settings for gradient backgrounds?** Current code shows solid white; gradient support UNVERIFIED.

7. **How are undo/redo command names derived from the action that triggered them?** Command naming logic in CommandBase.cpp not fully inspected.

8. **What is the Python console's exact mechanism for echoing GUI actions as Python commands?** Likely documented in DocumentObserverPython or GuiConsole; logic not fully traced.

---

## Notes

- All hex colours inferred from computed YAML (darken/lighten operations not fully expanded).
- Many icons listed as UNVERIFIED: repo naming convention suggests `view-*.svg`, `edit-*.svg`, `overlay-*.svg`, but not all confirmed in directory listing.
- Start page not researched (outside main UI scope).
- Sketcher, Part Design, Assembly modelling tools intentionally excluded (spec covers **display** and **tree**, not **creation**).
- This spec targets the **display-only port**: expect to adapt keyboard shortcuts, theme colours, and icon references as React/web constraints emerge.

# FreeCAD audit, 2026-10-14: cad-agent against FreeCAD at 3160daf1e2b6

Read-only audit of what cad-agent says it ports from FreeCAD (commit `3160daf1e2b62b0472854da4848255c6b3ad554c`, 2026-09-29, the weekly
build 26.3.0dev). No product code was changed; this file is the only thing the audit adds.

## 0. Result in brief

- Citations are in good shape. Every FreeCAD path cited in `cad_agent/` and its tests exists at the commit; the line ranges I sampled
  in ui/src (about 60) are right except one; 8 of 8 material cards match name, author, licence and all 22 cited values.
- The ports are better than their audit trail: Camera.cpp's nine views, NaviCube's 26 orientations, the corner axis cross (letter masks
  byte for byte), the Rounded Arcball and the other projectors, the CAD style, the DXF arc, circle and ellipse conventions (real FreeCAD, 820 entities: 0 differ)
  and Quantity, Units and Rotation (real FreeCAD, over 130,000 cases: all agree but one missing unit, micro-ampere, and one case FreeCAD leaves undefined)
  are exact.
- What is not true: section 4 (stale or wrong citations), section 5 (behaviour mismatches; the ones a person meets first are Home, Fit
  Selection, Align to Selection, perspective Fit All and the look of the NaviCube), section 6 (one function, geom.mass_properties, is a close translation of
  LGPL code; dxf.py and appcache.py are borderline; the shipped UI bundle carries no licence notice at all).

## 0.1 Status, 2026-10-20: the licence findings and the stale citations are fixed

Sections 4 and 6 below describe the repository as it was on 2026-10-14 (29d4e9b); they are kept as the record. Section 5, the
behaviour mismatches, is untouched. What changed:

- **Section 6.1, outside ui/.** `NOTICE` and `THIRD_PARTY_LICENSES` exist. `geom.mass_properties` keeps its code and carries the notice
  of `MassPropertiesResult.cpp` (LGPL-2.1-or-later, 2026 Morten Vajhøj); `dxf.py` carries the notice of `dxf.cpp` (BSD-3-Clause, 2009 Dan
  Heeks, modified 2018 wandererfan) and names the `DxfPlate` templates as FreeCAD's LGPL-2.0-or-later; `appcache.py` carries the notice
  of `DlgSettingsCacheDirectory.cpp` (2021 Werner Mayer; the file says Library General Public License "version 2 or later", so
  LGPL-2.0-or-later, not 2.1). None needed a rewrite. `materials.py` has each licence's URL and `credit()`, which prints the author, the
  title, the licence URL and where the card is, in `cad tables`, `cad tables density`, `cad tables materials` and after the E of a
  `[[deflection]]` row, for the five CC-BY-3.0 cards.
- **Section 6.2, ui/.** Every `ui/src` file starts with `// SPDX-License-Identifier: LGPL-2.1-or-later` (`tests/test_licenses.py`); the 40
  that follow FreeCAD files name them, with their copyright holders, in the header; `ui/NOTICE` lists the 130 FreeCAD files and their
  authors. `npm run build` now writes `THIRD_PARTY_LICENSES.txt` (the 47 npm packages in the bundle, each with the licence text it ships:
  `ui/scripts/licenses.mjs`), `LICENSE` and `NOTICE` into `cad_agent/workbench/next/`; `pyproject.toml` has the SPDX expression, the
  `license-files` and the package data, and a wheel built from it carries all of them. `ui/package.json` has its `license`.
- **Section 4, citations.** Fixed: viewer.ts:222 (`getTextPosition` is ViewProviderMeasureBase.cpp:769-788 with the offset at 784; the
  audit's 768-786 and 782 were two lines early), viewer.ts:65 (`syncNodeState`), macro.tsx:100 and 130, tooltip.ts:4, the `GetCamera` and
  `SetCamera` names (store.ts, viewer.ts, commands.ts, gui.py, PARITY.md), "131 units" (PARITY.md says 131 of 132 and why), PARITY.md's
  Home note, dxf.py (:11 the licence of dxf.cpp, :17 and :23-24 the splines, :46 the comment line, and the other differences of 5.10),
  undo.py:41, bom.py:19 and 447 with DETAILS.md, subassembly.py:89-95, hlr.py:50 and drawing/__init__.py:26, gui.py:69 and 96 (all
  checked against the same commit), and DETAILS.md:205. Already right when checked: prefs.tsx:229 (the option reads "Freecad Overlay.qss").
  Left as they are: drawing/writers.py:40 (its 999 line is output, and `tests/golden/drawings` pin it) and the same "Only parts" claim in the
  tooltip of ui/src/shopwb.tsx:85 (UI text, to change with the next bundle build).
- **Line numbers.** The line numbers of our own `ui/src` files in sections 4 and 5 are those of 29d4e9b. The licence headers moved every
  file's lines down by: App.tsx 6, actions.ts 13, agentwb.tsx 1, api.ts 4, axiscross.ts 4, background.ts 5, chrome.tsx 19, cmdicons.ts 8,
  cmdreg.ts 11, combo.tsx 4, commands.ts 7, customize.tsx 6, env.d.ts 1, expr.ts 7, exprdialog.tsx 5, filemenu.tsx 6, freecad.css 17,
  icons.tsx 11, keymap.ts 9, librarywb.tsx 1, lights.ts 7, macro.tsx 7, main.tsx 1, measure.tsx 9, msgbox.tsx 1, nav.ts 22, navicube.tsx 4,
  notifications.tsx 5, panels.tsx 17, placement.ts 1, poses.ts 1, prefs.tsx 17, qsb.tsx 4, qslider.ts 4, quantity-input.ts 5, quantity.ts 7,
  rotation.ts 7, shopwb.tsx 4, start.tsx 7, store.ts 12, superscript.ts 4, theme.ts 5, tools.tsx 10, tooltip.ts 4, units-data.ts 6,
  units-schemas.ts 4, viewer.ts 17. (The FreeCAD line numbers are unchanged.)

## 0.2 Status, 2026-10-21: the behaviour mismatches of section 5

Section 5 below is the record of 2026-10-14. Measured again in the real FreeCAD (`ui/scripts/fcbehave.py`, sections `fit`, `align`,
`tree_menu`, `quickmeasure`, `dblclick` and the combo lists of `nav_page`; ours by `ui/scripts/oursselect.mjs`; the Mac's key bindings by
`fcgui.py --platform cocoa`):

- **5.2 Fit Selection: the audit was wrong for this build.** `viewObjects` does call `vp->getBoundingBox(subName)`, but the box it gets
  back is the whole part's: `SoBrepFaceSet::getBoundingBox` has no partial box, and measured, an Edge and a Vertex give the whole box too
  (`ViewObject.getBoundingBox("Face6")` equals the part's box). For a part with a Placement the box comes back without it, so the camera
  lands away from the part. Fitting the whole part, as ours did, is what FreeCAD does; nothing was changed but the perspective distance.
- **5.4 Perspective Fit All: fixed.** R / tan(heightAngle / 2) (232.893 for R 96.468 at 45°, 1 / min(1, aspect) times that in a tall
  view), not R / sin; Fit Selection keeps the heightAngle, Fit All sets 45°. 36 of 36 cases agree.
- **5.3 Align to Selection: fixed**, from `View3DInventorViewer::alignToSelection`, `Part::Feature::getCameraAlignmentDirection` and
  `GeoFeature`: the camera turns about the focal point and is not moved; it stays on its side, takes the quarter-turn roll nearest its own
  from the face's longest straight edge; straight and planar edges and several elements work. 254 of 264 cases agreed on 2026-10-21; the
  10 left were a curved face. Since 2026-10-23 a face that is not planar gives the surface normal at the middle of its (u, v) bounds and
  its longest straight edge, as getCameraAlignmentDirection does (`scene.py` works them out from the shape, which the mesh cannot):
  264 of 264 agree (measured on Linux). Whether a camera exactly across the face flips is decided by Coin's float32 rounding; the same
  float32 arithmetic is used, and the normal is not rounded (a cylinder's side seen from the Front view turns on its 1.2e-16).
- **5.7 `µA`: fixed**; `fcdiff.py parse` has four cases for it (210 cases, none differ).
- **5.8 Double-click time: fixed**, as far as a page can: 500 ms by default on a Mac and Windows, 400 on X11, lengthened by the browser's
  own click count (`dblclick.ts`).
- **5.13 small ones**: `MayaGesture` and the appcache's calendar days and hidden files are fixed; QuickMeasure's circle types are
  there (the audit listed two, `Measurement::findType` has four, and a point and an arc); the Custom default camera orientation is
  done since 2026-10-23 (the Camera Settings dialog, Home and a new view: 20 of 20 measured cases agree, `fcbehave.py --only
  custom_camera` against `ui/scripts/ourscamera.mjs`, on Linux).
- **Also**: the Mac's Delete (⌫), Recompute (⌘R) and Previous Window (⇧⌘}); the tree menu's entries (Material, Appearance, Expression and
  Link Actions, Rename, Close Document, ... as in the real menu, greyed out where they mean nothing here).
- **Open**: 5.1 Home (under way elsewhere), 5.5 the NaviCube's look, 5.6 expressions, 5.9 arrow-key panning, 5.10 DXF, 5.11 BOM, 5.12
  drawings.

## 1. How it was checked

- Every cited FreeCAD file was fetched at the commit (raw.githubusercontent.com) and read; cited lines and functions compared with our comments.
- Numbers by script: the NaviCube tables, 48 navigation hint strings, 61 unit types, 132 unit tokens, 201 icons, the corner-cross letter masks,
  the preference pages' defaults (dumped from 18 .ui files), the material cards.
- The real FreeCAD (`~/.cad-agent/freecad/FreeCAD.app`, the weekly build of exactly this commit) was asked wherever it can answer, run
  read-only (user files in a temp folder; writes under `~/.cad-agent` denied by `sandbox-exec`):
  `ui/scripts/fcdiff.py` re-run (schemas 10, parse 206, user 55,413, number 600, rotation 326, ypr 112, euler 2,912: 0 differ, 6 known);
  extended with every `Quantity.l` unit token x 8 shapes and the user-format suite over all 61 quantity types x 10 schemas x 3 decimals
  (72,333 cases); a new expression differential (7,801 expressions against `DocumentObject.evalExpression`); the GUI on Qt's offscreen
  platform for Home and Fit All; `Import.writeDXFShape` on 838 edges.
- The Python half (`cad_agent/`) was read first by a second reader (a sonnet subagent), whose headline findings I re-checked against the fetched
  sources (marked [re-checked] below; the rest is marked [second reader] and not confirmed by me): the BSD header of dxf.cpp, the spline code, geom.py against MassPropertiesResult.cpp, appcache.py, the
  60 % template overlap (re-run), the cards (re-run), TechDraw's projection default, the stale `SetCamera` and `setUndoMode` names.
- `node ui/scripts/navcheck.mjs` (copy of ui/ in scratch): 72 of 72.

Not checked: anything drawn by GL (the offscreen FreeCAD has no GL context); the event logic of the other eleven navigation styles (only the CAD style was
compared line by line; the nine button-combination styles are one function in nav.ts, Gesture, Maya-Gesture and Siemens NX have their own); Placement, Transform
and Measure logic beyond their line citations; BOM and TechDraw outputs against a real FreeCAD run; TechDraw's hidden-line style default; docs/ and plugin/.

## 2. Inventory

63 files of ours name FreeCAD files (`freecad-src/inventory.md`). The big ones:

| ours | FreeCAD files it ports from |
|---|---|
| ui/src/viewer.ts | NaviCube.cpp (12 cites), SoNaviCube.cpp, Camera.cpp, View3DInventorViewer.cpp, View3DSettings.cpp, ViewProviderMeasure{Base,Angle,Distance}.cpp, SceneInspector.cpp, ImageView.cpp |
| ui/src/nav.ts | NavigationStyle.cpp, NavigationAnimation.cpp, the twelve *NavigationStyle.cpp, SoTouchEvents.cpp, View3DInventorViewer.cpp (long press) |
| ui/src/commands.ts, navicube.tsx, store.ts | NaviCube.cpp (buttons, menu, defaults), Camera.cpp, View3DPy.cpp |
| ui/src/quantity.ts, units-data.ts, units-schemas.ts, superscript.ts | Quantity.l/.y, Quantity.cpp, Unit.cpp, UnitsConvData.h, UnitsSchemasData.h, NumericFormatting.cpp, UnitsApi.cpp |
| ui/src/rotation.ts | Base/Rotation.cpp (all 26 Euler sequences) |
| ui/src/expr.ts, exprdialog.tsx, quantity-input.ts, qsb.tsx | Expression.y/.l/.cpp, QuantityInput.cpp, QuantitySpinBox.cpp, ExpressionCompleter.cpp |
| ui/src/panels.tsx, prefs.tsx, store.ts | PropertyEditor.cpp, Tree.cpp, TreeParams.py, DlgPreferences.ui, 18 DlgSettings*.ui, Placement.cpp, TaskTransform.cpp |
| ui/src/axiscross.ts, background.ts, lights.ts, theme.ts | View3DInventorViewer.cpp drawAxisCross, CornerCrossLetters.h, SoFCBackgroundGradient.cpp, View3DSettings.cpp, FreeCAD Light.cfg |
| ui/src/measure.tsx | TaskMeasure/TaskMassProperties.cpp, MassPropertiesResult.cpp, ViewProviderMeasure*.cpp |
| ui/src/chrome.tsx, actions.ts, filemenu.tsx, macro.tsx, tools.tsx, start.tsx, icons.tsx, cmdreg.ts, freecad.css | Workbench.cpp, Command*.cpp, Overlay*.cpp, FreeCAD.qss, StartView.cpp, DlgMacro*, DlgParameterImp.cpp |
| cad_agent/dxf.py | Import: ImpExpDxf.cpp (`exportShape`), dxf.cpp (`CDxfWrite`), AppImportPy.cpp, DxfPlate/*.rub |
| cad_agent/drawing/ | TechDraw GeometryObject.cpp (`projectShape`, `makeTDGeometry`), DrawViewPart.cpp, DrawProjGroup.cpp, Preferences.cpp |
| cad_agent/bom.py, speckinds/shop.py, shop.py | Assembly CommandCreateBom.py, BomObject.cpp |
| cad_agent/subassembly.py | Assembly AssemblyLink.cpp |
| cad_agent/materials.py | Material/Resources/Materials/**.FCMat (8 cards) |
| cad_agent/geom.py, beam.py, gui.py, scene.py, serve.py, undo.py, appcache.py, userprefs.py, macro.py, cli.py | MassPropertiesResult.cpp, TopoShapeFacePyImp.cpp, ViewProviderExt.cpp, Document.cpp, ApplicationCache (DlgSettingsCacheDirectory.cpp), DlgSettingsDocument.ui, Macro.cpp |

Looks ported, cites nothing:
- ui: `cmdicons.ts` (command to icon names, from the commands' `sPixmap`), `keymap.ts` default accelerators (each command's `sAccel`), the menu texts and
  tooltips of `cmdreg.ts`/`chrome.tsx` and the labels and tooltips of `prefs.tsx` (`sMenuText`/`sToolTipText`/.ui strings, verbatim); `msgbox.tsx` and
  `tooltip.ts` follow Qt (QMessageBox, QToolTip), not FreeCAD.
- cad_agent: dxf.py:616-676 (CLASSES, TABLES, BLOCK_RECORD, BLOCKS) and :733-759 (TEXT, SOLID) follow classes14.rub, tables114/214.rub and
  dxf.cpp:299-350, 384-489, 1031-1156 (only header14 and objects14 are named); drawing/onesheet.py:53-56 view vectors are DrawViewPart.cpp:1523-1532;
  hlr.py `canonical`/`cover` do the job of GeometryObject.cpp:521-533 by another algorithm; dxf.py:410-416 knot expansion is ImpExpDxf.cpp:2091-2106
  (FreeCAD's own comment credits DrawingExport.cpp); geom.py:153-167 is MassPropertiesResult.cpp:227-263 (cited at function level only);
  scene.py's deviation to deflection formula is Part/App/Tools.cpp:895-902 (it lives in ocp-tessellate).

## 3. Verified true (no finding)

- Line citations: NaviCube.cpp 148, 149, 461-466, 887-898, 937, 1170-1178, 1246-1262, 1331-1337; SoNaviCube.cpp 765-812 and its coordinates;
  View3DInventorViewer.cpp 607-609, 2073, 2257-2318; View3DSettings.cpp 367-368; PropertyEditor.cpp 106/113/1509 and .h:185; the Overlay, Tree,
  TreeParams, StartView, MassProperties and Measure ranges I sampled.
- Camera.cpp: all nine standard-view quaternions equal. NaviCube `getFaceRotation`: the 26 face, edge and corner orientations equal (both tables
  parsed, Coin's reversed quaternion product applied). Flat buttons (arrows, rolls, backside), 360/NaviStepByTurn clamped 4..36, the nearest-roll steps.
- Navigation: 47 of 48 hint strings equal (the 48th has "\n" where ours has a space), CAD style, the arcball/sheet/turntable/classic projectors,
  spinInternal's sphere shift, orbit-drag scaling, wheelAction, pinchAction, the animation (500 ms, InOutCubic), zoom e^step, the arrow-key step,
  the registration order of the twelve styles, DemoMode's defaults, box zoom (a perspective view changes the angle).
- Defaults of the pages I dumped (Navigation, 3D View, Selection, UI, Notification Area, Report View, Macro, Document, Python, Editor, Light
  Sources, Keyboard) and the three default light directions (View3DSettings.h:35-37).
- Corner axis cross: arrow geometry, 1.15 letter distance, 7 % height clamped 8..18, and the three 21x27 letter masks.
- Real FreeCAD: `Quantity.l` parse (all tokens but one), user formatting of every quantity type, number formatting, Rotation (26 sequences).
  `Unit::unitSpecs` (61 types, in order) equals UNIT_TYPES. 201 of 201 icons are byte-identical to FreeCAD's.
- Real FreeCAD, Fit All: orthographic height = 2R (113.578 for a 100x50x20 box) and 2R/aspect in a portrait view, zoom steps e^-0.2 and e^0.2: as ours.
- Real FreeCAD, `Import.writeDXFShape` on 838 edges: 400 arcs (normal +Z and -Z), 12 circles, 408 ellipses and ellipse arcs: centre, radius, angles
  and parameters equal ours mod 360 / 2 pi (0 differ). Lines differ only in endpoint order (ours sorts them).
- [re-checked] Cards: path, name, author, licence and 22 values. TechDraw `Preferences::projectionAngle` default FirstAngle (Preferences.cpp:154-159).
  Assembly `Assembly_CreateBom` columns, order and option defaults (CommandCreateBom.py:53-59, 136-138; BomObject.cpp:69-91).

## 4. Wrong or stale citations

ui, mine:
- ui/src/viewer.ts:222 `ViewProviderMeasureBase.cpp ~752-766` (getTextPosition): it is 768-786 (the `SbVec2s(30, 30)` at 782).
- ui/src/viewer.ts:65 names `mousePressed/populateRenderParams` for NaviCube.cpp:461-466; those lines are `syncNodeState` (the lines are right).
- ui/src/macro.tsx:100, 130 `DlgMacroRecordImp.ui`, `DlgMacroExecuteImp.ui`: the files are `DlgMacroRecord.ui`, `DlgMacroExecute.ui`.
- ui/src/prefs.tsx:229 `Overlay.qss`: the file is `Stylesheets/overlay/Freecad Overlay.qss`. ui/src/tooltip.ts:4 points at `scratchpad/collab/tooltip.css`, not in the repo.
- [re-checked] "GetCamera" / "SetCamera" as view messages (ui/PARITY.md:275; ui/src/commands.ts:41, 46, 48; store.ts:296, 302; viewer.ts:1171, 1200;
  cad_agent/gui.py:40, 387): neither exists in `src/Gui` at the commit. It is `View3DInventor::getCamera()/setCamera()` (View3DInventor.cpp:558-570) and
  Std_ViewIvIssueCamPos records `Gui.activeView().setCamera("...")` (CommandView.cpp:2551-2582). The text format is the same.
- ui/PARITY.md "its 131 units": `Quantity.l` has 132 UNIT tokens, ours 131 (the missing one is a finding, 5.7).
- ui/PARITY.md "default camera orientation (Trimetric; used for a new view and for Home)": FreeCAD's Home does not use it on a fresh profile (5.1).
- docs/DETAILS.md:205 "LGPL-2.1-or-later; those files say so": 15 of 47 ui/src files carry a notice (6.2).

cad_agent:
- [re-checked] dxf.py:17, 23-24 "ELLIPSE and SPLINE as they are", "a rational or periodic spline has no entity": WRONG for splines. `exportBSpline` (ImpExpDxf.cpp:2035-2116)
  re-fits every B-spline edge with `Approx_Curve3d` (tolerance 0.001, C0, 200 segments, degree 3) and writes flag closed + 2 periodic + 4 rational + 8;
  rational and periodic ones are written too. Only a Bezier (2121) and unknown types (warning, 1883) are dropped. Real FreeCAD: a cubic through 5 points is 17
  knots and 13 poles; ours writes the exact 11 and 7.
- [re-checked] dxf.py:11 "(LGPL-2.1-or-later)" beside dxf.cpp: `dxf.cpp` and `dxf.h` are BSD-3-Clause, (c) 2009 Dan Heeks, modified 2018 wandererfan; ImpExpDxf.cpp is LGPL (c) 2015 Yorik van Havre.
- [re-checked] dxf.py:46 comment line "FreeCAD v1.0 ...": the real one is `FreeCAD v26.3 20260929 (Git shallow)`.
- [re-checked] undo.py:41 `App::Document::setUndoMode`: there is none; Gui/Document.cpp:572 reads MaxUndoSize and calls `setMaxUndoStackSize` (App/Document.cpp:843).
- [second reader] subassembly.py:89-95 AssemblyLink: true but incomplete. Going flexible resets the link's Placement to identity and bakes it into the children
  (AssemblyLink.cpp:192-237); rigid copies the components' placements (536-541). There is no LinkTransform and no mirror in FreeCAD's file or in ours.
- [second reader] hlr.py:50, drawing/__init__.py:26: "hidden dashed" credited to GeometryObject.cpp; that file only classes visible and hidden, the dash is
  TechDraw/Gui/QGIViewPart.cpp:461-465. drawing/writers.py:40 (the 999 line of every drawing DXF) "views as FreeCAD projectShape": visible smooth edges
  are dropped (hlr.py:22), no centring, scaling or inversion.
- [re-checked in BomObject.cpp] bom.py:19, 447 "FreeCAD's 'Only parts'": FreeCAD's keeps part containers and drops solids such as bodies (BomObject.cpp:84-91, TaskAssemblyCreateBom.ui:56-61);
  ours keeps the parts made here and drops bought and stock ones, a different cut under the same name.
- [second reader] gui.py:69, 96 GuiDocument.xml names: ShapeColor is not stored, ShapeAppearance is (ViewProviderGeometryObject.cpp:434-437).

## 5. Behaviour mismatches, most noticeable first (S/M/L = effort to fix)

1. **Home goes to Trimetric; FreeCAD's goes to Top** until the Navigation page has been saved once. `View3DInventorViewer.cpp:4516` `viewHome` uses
   `Camera::defaultOrientation("Top")`; a new document uses `View3DPy.cpp:704` `defaultOrientation("Trimetric")`; the page shows Trimetric when
   the key is unset (`DlgSettingsNavigation.cpp:239`). Real FreeCAD offscreen: key unset, `viewDefaultOrientation()` gives
   (0.446015, 0.119509, 0.229575, 0.856787); after `viewFront`, Home gives (0, 0, 0, 1) = Top; with the key set to Trimetric, Home gives Trimetric.
   Ours: one `homeView` default 'Trimetric' (store.ts:348, commands.ts:21, prefs.tsx:636). S.
2. **Fit Selection ignores a sub-element selection.** FreeCAD fits the selected faces', edges' and vertices' bounding boxes
   (`View3DInventorViewer.cpp:4623-4716` viewObjects, `vp->getBoundingBox(subName)` at 4660; `ViewSelectionExtend` default false, ViewParams.cpp:412); ours fits the
   whole body (`fitAll(selected)`: commands.ts:399, cmdreg.ts:63, chrome.tsx:142, App.tsx:136). M.
3. **Align to Selection** (viewer.ts:1858) always looks from the face's outward normal with world Z up (Y for a normal along Z), and moves the focal point to the face's
   centre. FreeCAD keeps the camera on its current side (flips the direction if the camera's z is closer to the opposite one, `View3DInventorViewer.cpp:4844`), takes the
   roll nearest the current one in 90 degree steps (4874-4904), and only turns the camera (`setCameraOrientation(orientation)` at 4918, no move to centre). S-M.
4. **Perspective Fit All sits 8.2 % too far.** FreeCAD puts the camera at R / tan(heightAngle/2) (`View3DInventorViewer.cpp:4466-4469`; real FreeCAD: a 100x50x20 box gives
   focalDistance 137.10097 = 56.789 / tan 22.5 deg, and 294.42 in a 434x932 view); ours R / sin(fov/2) (viewer.ts:930) = 148.4. `View3DPy.cpp:759` setDefaultCameraHeight
   does use sin, which our defaultCameraHeight copies, so FreeCAD uses both. S.
5. **The NaviCube looks different.** Ours is three-viewport-gizmo's rounded cube; FreeCAD's SoNaviCube is flat chamfered pieces all in BaseColor (`SoNaviCube.cpp:1042-1051`) with black
   BorderWidth outlines (`:1087-1096`), labels in EmphaseColor (black, white when BaseColor is dark, `View3DSettings.cpp:640-644`) and drawn arrow, roll, home and menu shapes (`:814-948`).
   Ours draws edges #d3dae2 and corners #c9d1da (viewer.ts:2013-2014), no outlines, labels always black, HTML glyph buttons (navicube.tsx). The cube's travel area uses a fixed
   10 px offset where FreeCAD's OffsetX/Y default is 0 (viewer.ts:54; View3DSettings.cpp:608) and 12 px more at the bottom. PARITY.md does not say the look differs. L.
6. **The expression evaluator (expr.ts) is not FreeCAD's.** 1,597 of 7,801 generated expressions disagree with `DocumentObject.evalExpression` (non-finite results counted equal). FreeCAD
   evaluates through Python objects (`Expression.cpp:1379-1485` calc()). Real families: (a) function unit rules are not enforced (sin/cos/tan of a non-angle, exp/log/sinh/cosh/tanh/asin/acos/atan
   of a unit, atan2 and mod with unequal units, `abs(1; 2)`, `count()`; `Expression.cpp:2483-2535`); (b) `%` is Python's floor modulo (`-1.5 % 2` is 0.5, `2 % -1.5` is -1; ours -1.5 and 0.5) and `2 % 3 mm`
   is an error (`:1474-1485`); (c) a plain number against a quantity compares the internal values (`2 < 3 cm` and `2 == 2 mm` are true; RICH_COMPARE `:1418-1430`); ours raises "quantities need to have
   same unit"; (d) `round(-2.5)` is -3 (boost round, `:2646`), ours -2; (e) `1 mm/s^2` is acceleration, ours applies `^` to the whole `mm/s` chain, so `2 * 1 mm/s^2` is mm^2/s^2 and `1 m/s ^ 2` is 1e6
   (expr.ts unitExp; a typed quantity reaches this only through sums and the like, the Quantity grammar goes first); (f) `1 s + 1 min` fails ("min" is a function name in ours); (g) `2 / 0` and `0 ^ -1.5` are errors,
   `2 mm ^ 10` is "Unit exponent overflow". M.
7. **`µA` is not a unit.** `Quantity.l:99` has `"\xC2\xB5""A"` (two adjacent literals, which the generator missed); units-data.ts has 131 of 132, so `1 µA` reads as 1 and `µA` alone as DBL_MIN, FreeCAD 1e-6 A
   (real FreeCAD, parse suite). S.
8. **Double-click time is 400 ms** (nav.ts:132, viewer.ts:2237); FreeCAD asks `QApplication::doubleClickInterval()` (`NaviCube.cpp:1089-1090`, `NavigationStyle.cpp:2543`, each style): the OS value, 500 ms on macOS and
   Windows by default; 400 ms is only Qt's X11 default. S.
9. **Arrow-key panning**: FreeCAD builds the view volume with an integer-truncated aspect (`SoQTQuarterAdaptor.cpp:661`, `width() / height()` on ints), so left and right step 0.1 of the view's height in a view wider than
   tall; ours 0.1 of the true width. S, low.
10. [re-checked against a real FreeCAD file] **DXF files** (real FreeCAD file at hand): splines are re-fitted (4); angles are raw atan2 in (-180, 180] there and [0, 360) here (dxf.cpp:764-765); HEADER has $DIMSTYLE, $DIMTXSTY, $PEXTMAX, $PEXTMIN where ours has
    $MEASUREMENT, $EXTMIN, $EXTMAX; TABLES have 2 STYLE (txt and arial.ttf), 2 APPID, a DIMSTYLE where ours has 1, 1 and none; CLASSES has 3, ours 1; handles start at 0xA01, ours at 1; the file ends "EOF" with no newline.
    Only DIMSTYLE is in the docstring (dxf.py:48). Same geometry, readable by the same readers. S to document.
11. [second reader] **BOM**: a mirrored body is one line with quantity 2 where FreeCAD gives a second line "... (mirrored)" (BomObject.cpp:219-226, 283-290; documented, tests/test_bom.py:140, 188). M.
12. [second reader] **Drawings** leave out the visible smooth edges that TechDraw draws by default (GeometryObject.cpp:264; documented hlr.py:22-24).
13. Small: Preferences > Navigation shows "Maya-Gesture" (FreeCAD "MayaGesture", NavigationStyle.cpp:2846; the status bar is right); the Default camera orientation list lacks "Custom"
    (DlgSettingsNavigation.cpp:223-233); QuickMeasure lacks "Center surface distance" and "Center axis distance" (QuickMeasure.cpp:326-337); [second reader] appcache.py counts 24 h where FreeCAD counts calendar days
    (DlgSettingsCacheDirectory.cpp:216-220) and counts dotfiles QDir skips.

## 6. Licence

Repo MIT (LICENSE); `ui/` and its build `cad_agent/workbench/next/` LGPL-2.1-or-later by ui/LICENSE and README.md:77. There is no NOTICE file. Not legal advice; the test used is "close translation of
FreeCAD's authored code (same decomposition, order, constants, text) versus independent reimplementation of its behaviour".

### 6.1 Outside ui/ (MIT)

| file | verdict | evidence | recommendation |
|---|---|---|---|
| cad_agent/geom.py:121-176 `mass_properties` | close translation, small | MassPropertiesResult.cpp:94-276 (LGPL-2.1+, (c) 2026 Morten Vajhøj): same three accumulators and `Add(vol, density)` (:107-111, 186-198); the principal-axes block is the same branches in the same order, the 0.9 threshold, UnitZ/UnitY reference, `ref x axis3`, `axis3 x axis1` (:227-263); `moment()` is `axisMoment` (:265-269) | add a notice (SPDX LGPL-2.1-or-later and the attribution on that function) or rewrite (eigh of the inertia tensor; results change only in degenerate cases) |
| cad_agent/dxf.py `DxfWriter` static sections (599-676, 733-771) and the golden DXFs | borderline | 60 % (156 of 261) of FreeCAD's five R14 DxfPlate templates' (code, value) pairs appear in order, handles masked: objects14 13 of 13, header 20 of 29, tables 113 of 195, classes 10 of 24 (script re-run); BLOCKS equals dxf.cpp:384-489 group for group, TEXT/SOLID equal :1031-1156. Much of it is forced by the R14 format; ours drops DIMSTYLE, fixes counts, has its own handles. dxf.cpp is BSD-3-Clause (c) Dan Heeks with no notice here; the .rub files carry no header, so they follow the repository's LGPL-2.1 | add a NOTICE with the BSD-3 text and dxf.cpp's copyright line (Dan Heeks 2009, "modified 2018 wandererfan"), and name the .rub files as LGPL-2.1-or-later; or rebuild the static sections from Autodesk's DXF reference |
| cad_agent/dxf.py entity code (356-421, 705-731) | restructured, behaviour equal | same constants and predicate (CLOSED_SPAN 1.0, CLOSED_GAP_SQ 0.001 = ImpExpDxf.cpp:1785); 838 edges against the real FreeCAD equal | covered by the notice above |
| cad_agent/appcache.py | function-by-function re-expression | ApplicationCache (DlgSettingsCacheDirectory.cpp:165-187, 204-226, 277-364, (c) 2021 Werner Mayer, LGPL): the Period table (-1, 1, 7, 31, 365), `toString`, `toBytes`, `periodicCheckOfSize`, `clearDirectory`'s keep-list | add a notice, or rename and restructure |
| cad_agent/materials.py | data under licences | the 8 cards: 5 CC-BY-3.0 (Riegel, Stoehr, Firszt), 2 LGPL-2.1-or-later (Stoehr), 1 LGPL-2.0-or-later (Muench), all as each card says; CARDS has name, author and licence but no URI or licence text (CC BY 3.0 section 4 wants them) and is never printed (`materials.table()` omits it) | add the CC URL and print author and licence in `cad tables materials`, or a NOTICE (catalog.toml:591 is the model) |
| hlr.py, bom.py, speckinds/shop.py, shop.py, subassembly.py, undo.py, userprefs.py, macro.py, scene.py, serve.py, gui.py, cli.py, beam.py, export.py, drawing/{__init__,paper,onesheet,writers,platefit,arrange,readback}.py | independent | facts only (column and option names, 20/500/0.2/28.65/1e-6, property names), OCCT's documented HLR call order, own algorithms, no FreeCAD text | none |

The docstring credits ("FreeCAD ... commit 3160daf1e2b6, LGPL-2.1-or-later", dxf.py:11, bom.py:9, drawing/__init__.py:24) are a courtesy for the independent files and not a notice for the three above: they name the
project and the commit but no copyright holder and no terms, and dxf.py:11 mislabels dxf.cpp. Minimum fix: a `NOTICE` (or THIRD_PARTY.md) with FreeCAD's copyright holders for the files above and the BSD-3 text, SPDX headers on dxf.py,
geom.py (that function) and appcache.py, and the CC URL for the cards.

### 6.2 ui/ and its build

- ui/LICENSE (LGPL-2.1 text, "ported from FreeCAD ... or any later version") and README.md:77 cover the folder as a whole. Per file, 15 of 47 ui/src files carry a notice in their header (14 .ts/.tsx: axiscross,
  background, exprdialog, measure, nav, navicube, qsb, quantity-input, quantity, rotation, superscript, theme, units-data, units-schemas; and freecad.css); background.ts, theme.ts and freecad.css use an SPDX line, the others
  name the FreeCAD file, the commit and "LGPL-2.1-or-later" in a comment. The 32 without include every large port: viewer.ts (44 FreeCAD mentions), panels.tsx, prefs.tsx, tools.tsx, commands.ts, store.ts, actions.ts,
  filemenu.tsx, macro.tsx, start.tsx, lights.ts, expr.ts, placement.ts, cmdreg.ts, App.tsx, chrome.tsx (its only "LGPL" is the About-box sentence, line 549). docs/DETAILS.md:205 says "those files say so".
  Recommendation: `// SPDX-License-Identifier: LGPL-2.1-or-later` on every ui/src file that ports FreeCAD, and a `ui/NOTICE` naming the FreeCAD files' copyright holders it was derived from (Kustaa Nyholm and Joao Matos for
  NaviCube.cpp, Werner Mayer for Camera.cpp, Juergen Riegel for Quantity.l, ...), since LGPL asks for them to be kept.
- **The shipped bundle has no notice at all.** `cad_agent/workbench/next/assets/index-*.js` (3.3 MB, what the wheel serves) contains no LGPL notice and no MIT notice for React, three, three-cad-viewer, three-viewport-gizmo, dockview or
  radix (0 hits for "copyright", "@license", "MIT License"); `workbench/next/` has a LICENSE only inside freecad-icons/; pyproject's package-data does not ship ui/LICENSE and there is no `license` field. Fix: put the LGPL text in
  `ui/public/LICENSE` (vite copies public/ into the build) and list `workbench/next/LICENSE` in package-data; keep legal comments or emit a THIRD_PARTY_LICENSES file with the build; add `"license"` to ui/package.json and pyproject. S.
- Icons: 201 of 201 SVGs are byte-identical to FreeCAD's at the commit, and ui/public/freecad-icons/README.md states the exceptions (12 Tango CC-BY-SA 2.0, 4 CC-BY-SA 4.0 alongside LGPL, 3 public domain). No finding.
- cad_agent/workbench/vendor/ keeps its libraries' own headers (three, three-cad-viewer: MIT). No finding.

## 7. Where things are

The audit read FreeCAD's sources at the commit from GitHub (FreeCAD/FreeCAD, 13,354 files). Its working files stayed in a scratch
folder outside the repo: the new differential scripts (`fcdiff_extra.py`, `fcdiff_user_all.py`, `exprdiff.py` with `exprdiff_fc.py`,
`exprdiff_ours.mjs`, `exprdiff-entry.ts`, `home_probe_gui.py`, `fit_probe_gui.py`), the 7,801 expression answers and the 838-edge DXF
comparison. The first three scripts are worth adding to ui/scripts as they are.

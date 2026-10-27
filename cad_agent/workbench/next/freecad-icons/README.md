# FreeCAD icons

These icons are copied unmodified from FreeCAD
(https://github.com/FreeCAD/FreeCAD, `src/Gui/Icons` and
`src/Mod/*/Gui/Resources/icons`). They were taken at tag `1.1.4` and are
byte-identical on `main` at 3160daf1e2b6 (2026-09-29), the version the UI follows;
the later additions were taken from that commit. They are placeholders, to be replaced with
our own set later.

The `overlay-*.svg` files (the dock overlay panel's title bar buttons) come from a third
location, `src/Gui/Stylesheets/overlay/icons/*.svg` (light-theme variants, i.e. the files
with no `_light`/`_lightgray` suffix); renamed with an `overlay-` prefix here to avoid
clashing with unrelated icons of the same short name.

The CAD Agent workbench's commands for the shop (bill of materials, drawing, library, poses) use six
more, taken from `src/Mod/Assembly/Gui/Resources/icons` and `src/Mod/TechDraw/Gui/Resources/icons/actions`
at 3160daf1e2b6: `Assembly_BillOfMaterials.svg` (Assembly_CreateBom's own pixmap), `Assembly_InsertLink.svg`
(Insert Component, for the library), `Assembly_ExplodedView.svg` (poses), `TechDraw_PageDefault.svg`
(a drawing), `TechDraw_ExportPageDXF.svg` and `TechDraw_ExportPageSVG.svg`. The first and fourth carry no
licence metadata, so FreeCAD's LGPL-2.1 applies; the other four say `FreeCAD LGPL2+`. A drawing's tab
shows `TechDraw_TreePage.svg` (`src/Mod/TechDraw/Gui/Resources/icons`, the icon ViewProviderPage gives its page's
window; `FreeCAD LGPL2+`).

The PartDesign datums' own icons, `PartDesign_Plane.svg`, `PartDesign_Line.svg`, `PartDesign_Point.svg` and
`PartDesign_CoordinateSystem.svg` (src/Mod/PartDesign/Gui/Resources/icons at 3160daf1e2b6, for PartDesign::Plane and its
neighbours in the tree), were added with attachment; they say `FreeCAD LGPL2+`.

Licences, as each file's metadata states:

- Most are LGPL-2.0-or-later (`FreeCAD LGPL2+`). Files with no licence in their
  metadata come under FreeCAD's licence, LGPL-2.1 (see `LICENSE`, copied from
  the FreeCAD repository).
- CC-BY-SA 2.0 (Tango Desktop Project and derivatives): `Std_ViewScreenShot.svg`,
  `help-browser.svg`, `utilities-terminal.svg`, `zoom-selection.svg`, `view-fullscreen.svg`,
  `zoom-border.svg`, `zoom-in.svg`, `zoom-out.svg`, `accessories-text-editor.svg`,
  `media-playback-start.svg`, `media-playback-stop.svg`, `applications-accessories.svg`, and
  `button_sort.svg` (the Switch button of Preferences > Display > Colors; its metadata names the licence, no creator).
- CC-BY-SA 4.0 as well as `FreeCAD LGPL2+` (both in the metadata): `Std_UserEditModeDefault.svg`,
  `Std_UserEditModeTransform.svg`, `Std_UserEditModeCutting.svg`, `Std_UserEditModeColor.svg`.
- Public domain: `process-stop.svg`, `accessories-calculator.svg` (CC0 1.0, Jakub Steiner),
  and `internet-web-browser.svg`.
- `cursor-pan.svg`, `cursor-rotate.svg`, `cursor-zoom.svg`, `MassPropertiesIcon.svg`, `media-record.svg`,
  `Std_WindowTileVer.svg`, `Std_WindowCascade.svg`, `Std_WindowNext.svg` and `Std_WindowPrev.svg`
  carry no licence metadata, so FreeCAD's LGPL-2.1 applies.

Credit: the FreeCAD project and the icon authors named in each file's metadata.

qss-*.svg: FreeCAD's stylesheet indicator and scroll-bar arrow images, src/Gui/Stylesheets/images_classic/ at 3160daf1e2b6 (LGPL-2.1-or-later).

The Sketcher's icons are in `sketcher/`: every SVG of `src/Mod/Sketcher/Gui/Resources/icons` (its `constraints/`,
`elements/`, `general/`, `geometry/`, `overlay/`, `pointers/`, `splines/`, `tools/` and `dialogs/` folders, flattened) at
3160daf1e2b6, unmodified. They are FreeCAD LGPL2+ as their metadata states, or carry no licence and come under FreeCAD's
LGPL-2.1, but for `Sketcher_ValidateSketch.svg` and `Sketcher_ReorientSketch.svg`, whose metadata names CC-BY-SA 4.0, [vocx] as the creator and [agryson] Alexander Gryson as a contributor (the
NOTICE at the top of the repository credits them, and THIRD_PARTY_LICENSES has the licence).
The PartDesign workbench's tree and commands (ui/src/partdesign.tsx) use 50 more, taken at 3160daf1e2b6 from
`src/Mod/PartDesign/Gui/Resources/icons` (`PartDesign_*.svg`, the Tip's overlay `PartDesign_Overlay_Tip.svg`),
`src/Mod/Sketcher/Gui/Resources/icons` (`Sketcher_Sketch.svg`, `Sketcher_NotFullyConstrained.svg`, and from its `general/`
folder `Sketcher_NewSketch`, `Sketcher_EditSketch`, `Sketcher_MapSketch`, `Sketcher_ReorientSketch`, `Sketcher_ValidateSketch`,
`Sketcher_MergeSketch`, `Sketcher_MirrorSketch`), `src/Mod/Part/Gui/Resources/icons` (`Part_Detached.svg`,
`booleans/Part_CheckGeometry.svg`, `tools/Part_ColorFace.svg`), `src/Gui/Icons` (the Origin's `Std_CoordinateSystem.svg`,
`Std_Axis.svg`, `Std_Plane.svg`, `Std_Point.svg`, and `Std_ToggleFreeze.svg`) and `src/Mod/PartDesign/WizardShaft/WizardShaft.svg`,
renamed `PartDesign_WizardShaft.svg` here. Their metadata says `FreeCAD LGPL2+`, except: `Sketcher_ReorientSketch.svg`
(CC-BY-SA 4.0, Alexander Gryson) and `Sketcher_ValidateSketch.svg` (`FreeCAD CC-BY-SA 4.0`); `PartDesign_Clone.svg` (an empty
licence link, `FreeCAD LGPL2+` in its rights), `Std_CoordinateSystem.svg` and `Std_ToggleFreeze.svg` (no licence metadata), which
come under FreeCAD's LGPL-2.1.
The dress-up features' panels (ui/src/pd_dressup.tsx) add `PartDesign_Flip_Direction.svg` (`src/Mod/PartDesign/Gui/Resources/icons`
at 3160daf1e2b6, the Chamfer panel's Flip direction button): its work's licence link is empty, and its metadata carries a
CC-BY-SA 2.0 licence block with no creator (THIRD_PARTY_LICENSES has the licence).
The additive and subtractive primitives (ui/src/pd_transform.tsx) use 14 more from `src/Mod/PartDesign/Gui/Resources/icons` at
3160daf1e2b6, `PartDesign_Additive{Cylinder,Sphere,Cone,Ellipsoid,Torus,Prism,Wedge}.svg` and their `Subtractive` twins
(Box's two were there already); their metadata says `FreeCAD LGPL2+`.
The Sketcher's Constraints list and datum dialog (ui/src/sketchpanels.tsx, sketchui.tsx) add `bound-expression.svg`
(`src/Gui/Icons` at 3160daf1e2b6, the icon ExpressionDelegate paints beside a datum bound to an expression; Alfredo Monclus,
`FreeCAD LGPL2+`).

The Part workbench's icons (ui/src/part_icons.ts) are in `part/`: every SVG of `src/Mod/Part/Gui/Resources/icons` and its
`booleans/`, `create/`, `parametric/` and `tools/` folders (flattened) at 3160daf1e2b6, unmodified, 80 files. Their metadata
says `FreeCAD LGPL2+`; `Part_Compound.svg`, `Part_CompoundFilter.svg`, `Part_ExplodeCompound.svg` and
`Part_ProjectionOnSurface.svg` carry no LGPL tag and come under FreeCAD's LGPL-2.1, and `Part_CompoundFilter.svg`,
`Part_ProjectionOnSurface.svg`, `Part_Thickness.svg` and `Part_ColorFace.svg` also name CC-BY-SA 4.0 (creators [vocx],
Bernd Hahnebach, [agryson] Alexander Gryson and Stefan Tröger as their metadata lists them; THIRD_PARTY_LICENSES has the
licence).
The Assembly workbench's icons (ui/src/assembly_wb.tsx) are in `assembly/`: every SVG of
`src/Mod/Assembly/Gui/Resources/icons` at 3160daf1e2b6, unmodified, 34 files, and `Geoassembly.svg` (`src/Gui/Icons`, the
Assembly object's tree icon). Their metadata says `FreeCAD LGPL2+`, but for `Assembly_BillOfMaterials.svg` and
`Assembly_CreateJointRigidGroup.svg`, which carry no licence and come under FreeCAD's LGPL-2.1.
The Multi-Transform panel's Scale transformation (ui/src/pd_transform.tsx, PartDesign::Scaled) adds `PartDesign_Scaled.svg`
(`src/Mod/PartDesign/Gui/Resources/icons` at 3160daf1e2b6, ViewProviderScaled's icon); its metadata says `FreeCAD LGPL2+`.

The TechDraw workbench's icons (ui/src/techdraw.tsx, techdraw_tasks.tsx) are in `techdraw/`: every SVG of
`src/Mod/TechDraw/Gui/Resources/icons` and its `actions/` folder at 3160daf1e2b6, flattened and unmodified, 169 files;
the rich text editor's `MRTE/` folder and `actions/TechDraw_MoveView.svg` (CC-BY-SA 2.0) are left out. Their metadata
says `FreeCAD LGPL2+` (some link the LGPL 3.0 text from their `cc:license` while their rights say FreeCAD LGPL2+), or
carries no licence and they come under FreeCAD's LGPL-2.1.

The Spreadsheet workbench's icons (ui/src/spreadsheet.tsx) are in `spreadsheet/`: every SVG of
`src/Mod/Spreadsheet/Gui/Resources/icons` at 3160daf1e2b6, unmodified, 18 files. Their metadata says `FreeCAD LGPL2+`
(drawn by Eivind Kvedalen), but for SpreadsheetStyleBold.svg, SpreadsheetStyleItalic.svg and SpreadsheetStyleUnderline.svg
(Tango's format-text icons, by Lapo Calamandrei and Andreas Nilsson), which are in the public domain as their
`cc:license` says.

// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Gui/Selection/SelectionColors.h: 2026 FreeCAD contributors
//   src/Gui/View3DSettings.cpp: 2023 Werner Mayer
//   No copyright line in the file: src/Gui/PreferencePacks/FreeCAD Light/FreeCAD Light.cfg
// 3D view colours of the "FreeCAD Light" theme in FreeCAD main (nightly) at 3160daf1e2b6, 2026-09-29,
// from src/Gui/PreferencePacks/FreeCAD Light/FreeCAD Light.cfg ([View] and [NaviCube] groups,
// packed RRGGBBAA) and src/Gui/Selection/SelectionColors.h. The UI colours are in freecad.css.
export const VIEW = {
  background: 0xf7f7f7, // BackgroundColor (Gradient off)
  preselect: 0x0ac8ff, // HighlightColor (= highlightFallbackColor)
  select: 0x00abff, // SelectionColor (= selectionFallbackColor)
  shape: 0xadb5bd, // DefaultShapeColor
  line: 0x000000, // DefaultShapeLineColor
  cube: 0xf2f2f2, // NaviCube BaseColor: light.cfg's own override (opaque), not View3DSettings.cpp's code fallback (0xE2E8EFC0)
  cubeHover: 0xaae2ff, // NaviCube HiliteColor (its own hover colour, not the 3D view's HighlightColor)
}

// The report view's default colours (Preferences > General > Output window).
export const REPORT = { msg: '#000000', log: '#0000ff', warn: '#ffaa00', err: '#ff0000' }

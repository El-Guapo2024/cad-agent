// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Sketcher/App/Sketch.cpp: 2010 Jürgen Riegel
// The one place the Sketcher's UI takes its solver from: FreeCAD's PlaneGCS behind Sketch.cpp's mapping, compiled to
// WebAssembly (planegcs.ts). A stand-in for tests would be swapped in on this line.
export * from './planegcs'

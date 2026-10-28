// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6): the CAM workbench's icons, copied unmodified
// into public/freecad-icons/cam from src/Mod/CAM/Gui/Resources/icons; their licences are in public/freecad-icons/README.md
// and ui/NOTICE. The icon names cam.tsx draws, merged into icons.tsx's FILES: 'cam-' and the file's name.
const NAMES = ['CAMWorkbench', 'CAM_3DPocket', 'CAM_Adaptive', 'CAM_Area_Workplane', 'CAM_Array', 'CAM_BaseGeometry', 'CAM_Comment', 'CAM_Custom',
  'CAM_Datums', 'CAM_Deburr', 'CAM_Depths', 'CAM_Dressup', 'CAM_Drilling', 'CAM_Engrave', 'CAM_ExportTemplate', 'CAM_Face', 'CAM_Heights',
  'CAM_HeightsDiagram', 'CAM_HeightsDiagram_NoFinish', 'CAM_Helix', 'CAM_InactiveOp', 'CAM_Inspect', 'CAM_Job', 'CAM_OpActive', 'CAM_OpCopy',
  'CAM_Pocket', 'CAM_Post', 'CAM_PostSelected', 'CAM_Probe', 'CAM_Profile', 'CAM_Sanity', 'CAM_SelectLoop', 'CAM_SetupSheet', 'CAM_Shape',
  'CAM_SimpleCopy', 'CAM_Simulator', 'CAM_SimulatorGL', 'CAM_Slot', 'CAM_StartPoint', 'CAM_Stop', 'CAM_Tags', 'CAM_ThreadMilling', 'CAM_ToolBit',
  'CAM_ToolController', 'CAM_ToolTable', 'CAM_Toolpath'] as const
export type CamIcon = `cam-${(typeof NAMES)[number]}`
export const CAM_FILES = Object.fromEntries(NAMES.map((n) => [`cam-${n}`, `cam/${n}`])) as { [K in (typeof NAMES)[number] as `cam-${K}`]: string }

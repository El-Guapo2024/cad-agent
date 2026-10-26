// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6): the Assembly workbench's icons, copied
// unmodified into public/freecad-icons/assembly from src/Mod/Assembly/Gui/Resources/icons (and src/Gui/Icons'
// Geoassembly); their licences are in public/freecad-icons/README.md and ui/NOTICE.
// The icon names assembly_wb.tsx draws, merged into icons.tsx's FILES.
export const ASSEMBLY_FILES = {
  'as-assembly': 'assembly/Geoassembly', 'as-activate': 'assembly/Assembly_ActivateAssembly',
  'as-link': 'assembly/Assembly_AssemblyLink', 'as-link-rigid': 'assembly/Assembly_AssemblyLinkRigid',
  'as-bom': 'assembly/Assembly_BillOfMaterials', 'as-insert': 'assembly/Assembly_InsertLink',
  'as-joints': 'assembly/Assembly_JointGroup', 'as-ground': 'assembly/Assembly_ToggleGrounded',
  'as-rigid': 'assembly/Assembly_CreateJointRigidGroup', 'as-solve': 'assembly/Assembly_SolveAssembly',
  'as-exploded': 'assembly/Assembly_ExplodedView', 'as-simulation': 'assembly/Assembly_CreateSimulation',
  'as-asmt': 'assembly/Assembly_ExportASMT', 'as-select-joints': 'assembly/Assembly_SelectJointsOfComponent',
  'as-Fixed': 'assembly/Assembly_CreateJointFixed', 'as-Revolute': 'assembly/Assembly_CreateJointRevolute',
  'as-Cylindrical': 'assembly/Assembly_CreateJointCylindrical', 'as-Slider': 'assembly/Assembly_CreateJointSlider',
  'as-Ball': 'assembly/Assembly_CreateJointBall', 'as-Distance': 'assembly/Assembly_CreateJointDistance',
  'as-Parallel': 'assembly/Assembly_CreateJointParallel', 'as-Perpendicular': 'assembly/Assembly_CreateJointPerpendicular',
  'as-Angle': 'assembly/Assembly_CreateJointAngle', 'as-RackPinion': 'assembly/Assembly_CreateJointRackPinion',
  'as-Screw': 'assembly/Assembly_CreateJointScrew', 'as-Gears': 'assembly/Assembly_CreateJointGears',
  'as-Belt': 'assembly/Assembly_CreateJointPulleys', 'wb-assembly-own': 'assembly/AssemblyWorkbench',
} as const

// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Sketcher/Gui/Workbench.cpp: 2008 Jürgen Riegel
//   src/Mod/Sketcher/Gui/Command.cpp: 2008 Jürgen Riegel
//   src/Mod/Sketcher/Gui/CommandCreateGeo.cpp: 2010 Jürgen Riegel
//   src/Mod/Sketcher/Gui/CommandConstraints.cpp: 2010 Jürgen Riegel
//   src/Mod/Sketcher/Gui/CommandSketcherTools.cpp: 2014 Abdullah Tahiri
//   src/Gui/ShortcutManager.cpp: 2022 Zheng Lei (realthunder)
// The Sketcher workbench's commands: its toolbars and Sketch menu as Workbench.cpp lays them out (the edit mode's
// toolbars ForceAvailable while a sketch is in edit), each command's text, tooltip, icon and shortcut
// (sketchcmdinfo.ts, from FreeCAD's sources), what each does here, and the two- and three-key shortcuts (G, L; G, 3, A)
// while the sketch is in edit (ShortcutManager's sequences, with its timeout for a prefix of a longer one).
import { SKETCH_CMD_INFO } from './sketchcmdinfo'
import * as S from './sketcher'
import { ArcHandler, CircleHandler, LineHandler, PointHandler, PolygonHandler, PolylineHandler, RectangleHandler, SlotHandler, toggleConstruction } from './sketchtools'
import { runConstraint, isConstraintCommand, toggleDriving, toggleActive, idOf } from './sketchcons'
import * as SK from './sketch'
import { getState, report } from './store'
import { recordAndRun } from './actions'

export type ToolItem = string | 'sep' | { group: string; items: string[] }
/** Workbench::setupToolBars' edit-mode toolbars (UnifiedLineCommands, SingleDimensioningTool, AutoHorVer and
 *  UnifiedCoincident at their defaults), as the real FreeCAD 26.3 shows them (ui/scripts/fcsketch.py). */
export const EDIT_TOOLBARS: { title: string; items: ToolItem[] }[] = [
  { title: 'Edit Mode', items: ['Sketcher_LeaveSketch', 'Sketcher_ViewSketch', 'Sketcher_ViewSection'] },
  { title: 'Geometries', items: ['Sketcher_CreatePoint',
    { group: 'Sketcher_CompLine', items: ['Sketcher_CreatePolyline', 'Sketcher_CreateLine'] },
    { group: 'Sketcher_CompCreateArc', items: ['Sketcher_CreateArc', 'Sketcher_Create3PointArc', 'Sketcher_CreateArcOfEllipse', 'Sketcher_CreateArcOfHyperbola', 'Sketcher_CreateArcOfParabola'] },
    { group: 'Sketcher_CompCreateConic', items: ['Sketcher_CreateCircle', 'Sketcher_Create3PointCircle', 'Sketcher_CreateEllipseByCenter', 'Sketcher_CreateEllipseBy3Points'] },
    { group: 'Sketcher_CompCreateRectangles', items: ['Sketcher_CreateRectangle', 'Sketcher_CreateRectangle_Center', 'Sketcher_CreateOblong'] },
    { group: 'Sketcher_CompCreateRegularPolygon', items: ['Sketcher_CreateTriangle', 'Sketcher_CreateSquare', 'Sketcher_CreatePentagon', 'Sketcher_CreateHexagon', 'Sketcher_CreateHeptagon', 'Sketcher_CreateOctagon', 'Sketcher_CreateRegularPolygon'] },
    { group: 'Sketcher_CompSlot', items: ['Sketcher_CreateSlot', 'Sketcher_CreateArcSlot'] },
    { group: 'Sketcher_CompCreateBSpline', items: ['Sketcher_CreateBSpline', 'Sketcher_CreatePeriodicBSpline', 'Sketcher_CreateBSplineByInterpolation', 'Sketcher_CreatePeriodicBSplineByInterpolation'] },
    'Sketcher_CreateText', 'sep', 'Sketcher_ToggleConstruction'] },
  { title: 'Constraints', items: [
    { group: 'Sketcher_CompDimensionTools', items: ['Sketcher_Dimension', 'sep', 'Sketcher_ConstrainDistanceX', 'Sketcher_ConstrainDistanceY', 'Sketcher_ConstrainDistance', 'Sketcher_ConstrainRadiam', 'Sketcher_ConstrainRadius', 'Sketcher_ConstrainDiameter', 'Sketcher_ConstrainAngle', 'Sketcher_ConstrainLock'] },
    'sep', 'Sketcher_ConstrainCoincidentUnified',
    { group: 'Sketcher_CompHorVer', items: ['Sketcher_ConstrainHorVer', 'Sketcher_ConstrainHorizontal', 'Sketcher_ConstrainVertical'] },
    'Sketcher_ConstrainParallel', 'Sketcher_ConstrainPerpendicular', 'Sketcher_ConstrainTangent', 'Sketcher_ConstrainEqual', 'Sketcher_ConstrainSymmetric', 'Sketcher_ConstrainBlock',
    'sep', { group: 'Sketcher_CompToggleConstraints', items: ['Sketcher_ToggleDrivingConstraint', 'Sketcher_ToggleActiveConstraint'] }] },
  { title: 'Sketcher Tools', items: [
    { group: 'Sketcher_CompCreateFillets', items: ['Sketcher_CreateFillet', 'Sketcher_CreateChamfer'] },
    { group: 'Sketcher_CompCurveEdition', items: ['Sketcher_Trimming', 'Sketcher_Split', 'Sketcher_Extend'] },
    { group: 'Sketcher_CompExternal', items: ['Sketcher_Projection', 'Sketcher_Intersection'] },
    'Sketcher_CarbonCopy', 'sep', 'Sketcher_Translate', 'Sketcher_Rotate', 'Sketcher_Scale', 'Sketcher_Offset', 'Sketcher_Symmetry', 'Sketcher_RemoveAxesAlignment'] },
  { title: 'B-Spline Tools', items: ['Sketcher_BSplineConvertToNURBS', 'Sketcher_BSplineIncreaseDegree', 'Sketcher_BSplineDecreaseDegree',
    { group: 'Sketcher_CompModifyKnotMultiplicity', items: ['Sketcher_BSplineIncreaseKnotMultiplicity', 'Sketcher_BSplineDecreaseKnotMultiplicity'] },
    'Sketcher_BSplineInsertKnot', 'Sketcher_JoinCurves'] },
  { title: 'Visual Helpers', items: ['Sketcher_SelectConstraints', 'Sketcher_SelectElementsAssociatedWithConstraints', 'sep', 'Sketcher_ArcOverlay',
    { group: 'Sketcher_CompBSplineShowHideGeometryInformation', items: ['Sketcher_BSplineDegree', 'Sketcher_BSplinePolygon', 'Sketcher_BSplineComb', 'Sketcher_BSplineKnotMultiplicity', 'Sketcher_BSplinePoleWeight'] },
    'Sketcher_RestoreInternalAlignmentGeometry', 'Sketcher_SwitchVirtualSpace'] },
]
/** The Sketcher workbench's own toolbar, out of edit mode. */
export const SKETCHER_TOOLBAR: ToolItem[] = ['Sketcher_NewSketch', 'Sketcher_EditSketch', 'Sketcher_MapSketch', 'Sketcher_ReorientSketch', 'Sketcher_ValidateSketch', 'Sketcher_MergeSketches', 'Sketcher_MirrorSketch']
/** Workbench::setupMenuBar's "S&ketch" menu. */
export type MenuItem = string | 'sep' | { menu: string; items: MenuItem[] }
export const SKETCH_MENU: MenuItem[] = [
  'Sketcher_NewSketch', 'Sketcher_EditSketch', 'Sketcher_MapSketch', 'Sketcher_ReorientSketch', 'Sketcher_ValidateSketch', 'Sketcher_MergeSketches', 'Sketcher_MirrorSketch',
  'Sketcher_LeaveSketch', 'Sketcher_CancelSketch', 'Sketcher_ViewSketch', 'Sketcher_ViewSection', 'Sketcher_StopOperation',
  { menu: 'Geometries', items: ['Sketcher_CreatePoint', 'Sketcher_CreatePolyline', 'Sketcher_CreateLine', 'Sketcher_CreateArc', 'Sketcher_Create3PointArc', 'Sketcher_CreateArcOfEllipse',
    'Sketcher_CreateArcOfHyperbola', 'Sketcher_CreateArcOfParabola', 'Sketcher_CreateCircle', 'Sketcher_Create3PointCircle', 'Sketcher_CreateEllipseByCenter',
    'Sketcher_CreateEllipseBy3Points', 'Sketcher_CreateRectangle', 'Sketcher_CreateRectangle_Center', 'Sketcher_CreateOblong', 'Sketcher_CreateTriangle', 'Sketcher_CreateSquare',
    'Sketcher_CreatePentagon', 'Sketcher_CreateHexagon', 'Sketcher_CreateHeptagon', 'Sketcher_CreateOctagon', 'Sketcher_CreateRegularPolygon', 'Sketcher_CreateSlot',
    'Sketcher_CreateArcSlot', 'Sketcher_CreateBSpline', 'Sketcher_CreatePeriodicBSpline', 'Sketcher_CreateBSplineByInterpolation', 'Sketcher_CreatePeriodicBSplineByInterpolation',
    'Sketcher_CreateText', 'sep', 'Sketcher_ToggleConstruction'] },
  { menu: 'Constraints', items: ['Sketcher_ConstrainCoincidentUnified', 'Sketcher_ConstrainHorVer', 'Sketcher_ConstrainHorizontal', 'Sketcher_ConstrainVertical', 'Sketcher_ConstrainParallel',
    'Sketcher_ConstrainPerpendicular', 'Sketcher_ConstrainTangent', 'Sketcher_ConstrainEqual', 'Sketcher_ConstrainSymmetric', 'Sketcher_ConstrainBlock', 'sep', 'Sketcher_Dimension',
    'Sketcher_ConstrainDistanceX', 'Sketcher_ConstrainDistanceY', 'Sketcher_ConstrainDistance', 'Sketcher_ConstrainRadiam', 'Sketcher_ConstrainRadius', 'Sketcher_ConstrainDiameter',
    'Sketcher_ConstrainAngle', 'Sketcher_ConstrainLock', 'Sketcher_ConstrainSnellsLaw', 'sep', 'Sketcher_ToggleDrivingConstraint', 'Sketcher_ToggleActiveConstraint'] },
  { menu: 'Sketcher Tools', items: ['Sketcher_CreateFillet', 'Sketcher_CreateChamfer', 'Sketcher_Trimming', 'Sketcher_Extend', 'Sketcher_Split', 'Sketcher_Projection', 'Sketcher_Intersection',
    'Sketcher_CarbonCopy', 'sep', 'Sketcher_SelectOrigin', 'Sketcher_SelectHorizontalAxis', 'Sketcher_SelectVerticalAxis', 'sep', 'Sketcher_Translate', 'Sketcher_Rotate', 'Sketcher_Scale',
    'Sketcher_Offset', 'Sketcher_Symmetry', 'Sketcher_RemoveAxesAlignment', 'sep', 'Sketcher_DeleteAllGeometry', 'Sketcher_DeleteAllConstraints', 'sep', 'Sketcher_CopyClipboard',
    'Sketcher_Cut', 'Sketcher_Paste'] },
  { menu: 'B-Spline Tools', items: ['Sketcher_BSplineConvertToNURBS', 'Sketcher_BSplineIncreaseDegree', 'Sketcher_BSplineDecreaseDegree', 'Sketcher_BSplineIncreaseKnotMultiplicity',
    'Sketcher_BSplineDecreaseKnotMultiplicity', 'Sketcher_BSplineInsertKnot', 'Sketcher_JoinCurves'] },
  { menu: 'Visual Helpers', items: ['Sketcher_SelectElementsWithDoFs', 'Sketcher_SelectConstraints', 'Sketcher_SelectElementsAssociatedWithConstraints', 'Sketcher_SelectRedundantConstraints',
    'Sketcher_SelectConflictingConstraints', 'sep', 'Sketcher_ArcOverlay', 'Sketcher_RestoreInternalAlignmentGeometry', 'Sketcher_SwitchVirtualSpace',
    { menu: 'Toggle B-Spline Information Layer', items: ['Sketcher_BSplineDegree', 'Sketcher_BSplinePolygon', 'Sketcher_BSplineComb', 'Sketcher_BSplineKnotMultiplicity', 'Sketcher_BSplinePoleWeight'] }] },
]

/** A command's menu text, tooltip, icon file and shortcut. */
export function cmdInfo(name: string) {
  const [menu, tip, pixmap, accel] = SKETCH_CMD_INFO[name] ?? [name, '', '', '']
  return { menu, tip, pixmap, accel }
}
/** The group button's icon: its last chosen command's (GroupCommand::setup, rememberLast). */
const lastOfGroup = new Map<string, string>()
export const groupDefault = (group: string, items: string[]) => lastOfGroup.get(group) ?? items.find((i) => i !== 'sep')!
export function iconOf(name: string) {
  const own = cmdInfo(name).pixmap
  if (own) return own
  for (const tb of EDIT_TOOLBARS) for (const it of tb.items) if (typeof it === 'object' && it.group === name) return cmdInfo(groupDefault(it.group, it.items)).pixmap
  return ''
}

const tool = (make: () => S.Handler) => () => S.activateHandler(make())
/** What each command does here. */
const RUN: Record<string, () => void> = {
  Sketcher_CreatePoint: tool(() => new PointHandler()),
  Sketcher_CreateLine: tool(() => new LineHandler()),
  Sketcher_CreatePolyline: tool(() => new PolylineHandler()),
  Sketcher_CreateArc: tool(() => new ArcHandler(0)),
  Sketcher_Create3PointArc: tool(() => new ArcHandler(1)),
  Sketcher_CreateCircle: tool(() => new CircleHandler(0)),
  Sketcher_Create3PointCircle: tool(() => new CircleHandler(1)),
  Sketcher_CreateRectangle: tool(() => new RectangleHandler(0)),
  Sketcher_CreateRectangle_Center: tool(() => new RectangleHandler(1)),
  Sketcher_CreateOblong: tool(() => new RectangleHandler(0, true)),
  Sketcher_CreateSlot: tool(() => new SlotHandler()),
  Sketcher_CreateTriangle: tool(() => new PolygonHandler(3)),
  Sketcher_CreateSquare: tool(() => new PolygonHandler(4)),
  Sketcher_CreatePentagon: tool(() => new PolygonHandler(5)),
  Sketcher_CreateHexagon: tool(() => new PolygonHandler(6)),
  Sketcher_CreateHeptagon: tool(() => new PolygonHandler(7)),
  Sketcher_CreateOctagon: tool(() => new PolygonHandler(8)),
  Sketcher_CreateRegularPolygon: tool(() => new PolygonHandler(6)),
  Sketcher_ToggleConstruction: toggleConstruction,
  Sketcher_LeaveSketch: () => void S.closeEdit(true),
  Sketcher_CancelSketch: () => void S.closeEdit(false),
  Sketcher_ViewSketch: S.viewSketch,
  Sketcher_StopOperation: () => S.purgeHandler(),
  Sketcher_ToggleDrivingConstraint: toggleDriving,
  Sketcher_ToggleActiveConstraint: toggleActive,
  Sketcher_SelectOrigin: () => S.setSelection([...S.getSelection(), 'RootPoint']),
  Sketcher_SelectHorizontalAxis: () => S.setSelection([...S.getSelection(), 'H_Axis']),
  Sketcher_SelectVerticalAxis: () => S.setSelection([...S.getSelection(), 'V_Axis']),
  Sketcher_SelectConflictingConstraints: () => selectConstraintList(S.getResult()?.conflicting ?? []),
  Sketcher_SelectRedundantConstraints: () => selectConstraintList(S.getResult()?.redundant ?? []),
  Sketcher_SelectElementsWithDoFs: selectElementsWithDoFs,
  Sketcher_SelectConstraints: selectAssociatedConstraints,
  Sketcher_SelectElementsAssociatedWithConstraints: selectAssociatedGeometry,
  Sketcher_DeleteAllGeometry: () => { if (!confirm('Are you really sure you want to delete all geometry and constraints?')) return; S.openCommand('Delete all geometry'); S.setGeometry([]); S.setConstraints([]); S.commitCommand(); S.clearSelection(); S.solve() },
  Sketcher_DeleteAllConstraints: () => { if (!confirm('Are you really sure you want to delete all the constraints?')) return; S.openCommand('Delete All Constraints'); S.setConstraints([]); S.commitCommand(); S.clearSelection(); S.solve() },
}
/** Commands that work only while a sketch is in edit (eType ForEdit, isSketchInEdit). */
const OUT_OF_EDIT = new Set(['Sketcher_NewSketch', 'Sketcher_MapSketch', 'Sketcher_ReorientSketch', 'Sketcher_ValidateSketch', 'Sketcher_MergeSketches', 'Sketcher_MirrorSketch'])
let newSketchHook: (() => void) | null = null
/** Sketcher_NewSketch's dialog (SketchOrientationDialog, sketchui.tsx) registers here. */
export function onNewSketch(f: () => void) { newSketchHook = f }
export function isImplemented(name: string) { return name in RUN || isConstraintCommand(name) || name === 'Sketcher_NewSketch' || name === 'Sketcher_EditSketch' }
/** Command::isActive. */
export function isEnabled(name: string): boolean {
  const editing = S.isEditing()
  if (name === 'Sketcher_NewSketch') return !editing && !!getState().slug
  // CmdSketcherEditSketch: a sketch selected in the tree; until the tree has sketches, the one last in edit
  if (name === 'Sketcher_EditSketch') return !editing && !!getState().slug && !!S.lastSketch()
  if (OUT_OF_EDIT.has(name)) return false
  if (!editing || !isImplemented(name)) return false
  const sel = S.getSelection()
  switch (name) {
    case 'Sketcher_SelectConstraints': case 'Sketcher_SelectElementsAssociatedWithConstraints': case 'Sketcher_ToggleActiveConstraint':
      return sel.length > 0
    case 'Sketcher_StopOperation': return true
    default: return true
  }
}
export function why(name: string) {
  if (!isImplemented(name)) return 'Not in this workbench yet'
  if (OUT_OF_EDIT.has(name)) return 'Works on sketch objects, which the tree shows (not yet)'
  return ''
}
/** Sketcher_EditSketch: the sketch named, with the geometry and constraints given as JSON (`cad gui run PROJECT
 *  Sketcher_EditSketch NAME '{"geometry": [...], "constraints": [...]}' [PART]`, the form feature_edit.py saves), or
 *  without arguments the one last in edit. */
export function editSketchCommand(args: string[]) {
  if (S.isEditing()) return
  if (!args.length) { const last = S.lastSketch(); if (last) void S.editSketch(last); return }
  const [name, json, part] = args
  let sketch: { geometry: SK.Geo[]; constraints: import('./solver').Cons[] } = { geometry: [], constraints: [] }
  if (json) {
    try {
      const j = JSON.parse(json)
      sketch = { geometry: j.geometry ?? [], constraints: j.constraints ?? [] }
    } catch (e) { report('err', `Sketcher_EditSketch: ${e instanceof Error ? e.message : String(e)}`); return }
  }
  void S.editSketch({ part: part ?? null, name, sketch: S.unsavedSketch(name) && !json ? S.unsavedSketch(name)! : sketch })
}
/** Runs a Sketcher command by id, as Gui.runCommand does. */
export function runSketchCommand(name: string, args: string[] = []) {
  for (const tb of EDIT_TOOLBARS) for (const it of tb.items) if (typeof it === 'object' && it.items.includes(name)) lastOfGroup.set(it.group, name)
  if (name === 'Sketcher_NewSketch') { newSketchHook?.(); return }
  if (name === 'Sketcher_EditSketch') { recordAndRun(name, () => editSketchCommand(args), args); return }
  if (!isEnabled(name)) { report('warn', `${cmdInfo(name).menu || name}: not available now`); return }
  recordAndRun(name, () => {
    if (isConstraintCommand(name)) { S.purgeHandler(); runConstraint(name); return }
    RUN[name]?.()
  })
}
function selectConstraintList(ids: number[]) { S.setSelection(ids.map((i) => SK.constraintName(S.getConstraints()[i], i))) }
/** Sketcher_SelectElementsWithDoFs: the geometry still free to move (the solver's dependent parameters). */
function selectElementsWithDoFs() {
  const r = S.getResult()
  if (!r?.dependent) return
  const names = new Set<string>()
  for (const [g, pos] of r.dependent) {
    if (pos === 0) names.add(SK.edgeName(g))
    else { const v = S.vertexIndexOf(g, pos as SK.PointPos); if (v >= 0) names.add(SK.vertexName(v)) }
  }
  S.setSelection([...names])
}
/** Sketcher_SelectConstraints: the constraints on the selected geometry. */
function selectAssociatedConstraints() {
  const cs = S.getConstraints(), ids = S.getSelection().map(idOf).filter((x): x is { geoId: number; pos: SK.PointPos } => !!x)
  const out: string[] = []
  cs.forEach((c, i) => {
    if (ids.some((s) => (s.pos === 0 ? [c.first, c.second, c.third].includes(s.geoId) : (c.first === s.geoId && c.firstPos === s.pos) || (c.second === s.geoId && c.secondPos === s.pos) || (c.third === s.geoId && c.thirdPos === s.pos)))) out.push(SK.constraintName(c, i))
  })
  S.setSelection(out)
}
/** Sketcher_SelectElementsAssociatedWithConstraints. */
function selectAssociatedGeometry() {
  const cs = S.getConstraints(), out: string[] = []
  for (const i of S.selectedConstraints()) {
    const c = cs[i]
    for (const [g, p] of [[c.first, c.firstPos], [c.second, c.secondPos], [c.third, c.thirdPos]] as [number, SK.PointPos][]) {
      if (g === SK.GEO_UNDEF) continue
      if (p === 0) out.push(SK.edgeName(g))
      else if (g === -1 && p === 1) out.push('RootPoint')
      else if (g >= 0) out.push(SK.vertexName(S.vertexIndexOf(g, p)))
    }
  }
  S.setSelection(out)
}

// ── shortcuts while editing (ShortcutManager's sequences) ────────────────────────────────────────────────────────
const SHORTCUT_TIMEOUT = () => getState().shortcutTimeout || 300
let pending: { keys: string[]; timer: number } | null = null
const accelTable = () => Object.entries(SKETCH_CMD_INFO).filter(([, v]) => v[3]).map(([k, v]) => [k, v[3].split(', ').map((x) => x.trim().toUpperCase())] as const)
/** A key while the sketch is in edit: true when it is part of a Sketcher shortcut. */
export function sketchShortcut(e: KeyboardEvent): boolean {
  if (!S.isEditing() || e.metaKey || e.ctrlKey || e.altKey) return false
  const k = e.key.length === 1 ? e.key.toUpperCase() : ''
  if (!k) return false
  const keys = [...(pending?.keys ?? []), k]
  if (pending) clearTimeout(pending.timer)
  const table = accelTable().filter(([n]) => isImplemented(n))
  const exact = table.find(([, a]) => a.length === keys.length && a.every((x, i) => x === keys[i]))
  const longer = table.some(([, a]) => a.length > keys.length && keys.every((x, i) => a[i] === x))
  if (!exact && !longer) { pending = null; return false }
  e.preventDefault()
  if (exact && !longer) { pending = null; runSketchCommand(exact[0]); return true }
  pending = { keys, timer: window.setTimeout(() => { pending = null; if (exact) runSketchCommand(exact[0]) }, SHORTCUT_TIMEOUT()) }
  return true
}

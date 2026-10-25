// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Sketcher/Gui/ViewProviderSketch.cpp: 2009 Juergen Riegel
//   src/Mod/Sketcher/Gui/EditModeCoinManager.cpp: 2021 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/SnapManager.cpp: 2023 Pierre-Louis Boyer
//   src/Mod/Sketcher/Gui/TaskDlgEditSketch.cpp: 2009 Jürgen Riegel
//   src/Mod/Sketcher/Gui/TaskSketcherMessages.cpp: 2011 Jürgen Riegel
//   src/Mod/Sketcher/Gui/Workbench.cpp: 2008 Jürgen Riegel
//   src/Mod/Sketcher/Gui/Utils.cpp: 2021 Abdullah Tahiri
//   src/Mod/Sketcher/App/SketchObject.cpp: 2008 Jürgen Riegel
//   src/Gui/TaskView/TaskSolverMessages.cpp: 2011 Jürgen Riegel
// The Sketcher's edit mode (ViewProviderSketch in edit, with TaskDlgEditSketch open): entering it turns the view to
// the sketch, hides what depends on it and shows the grid; the 3D view's mouse and keys come here first, as Coin hands
// them to the view provider's event callbacks (mouseButtonPressed, mouseMove, keyPressed); preselection and
// selection of points, edges, the axes and constraints; dragging with a re-solve on every move (Sketch::movePoint);
// box selection; Delete; the solver's messages (UpdateSolverInformation); undo within the edit; OK and Cancel.
// The drawing is sketchdraw.ts, the geometry tools sketchtools.ts, the constraint commands sketchcons.ts.
import * as THREE from 'three'
import { loadSolver, type Solver, type SolveResult, type Sketch, type Geo, type XY, type Drag } from './solver'
import * as SK from './sketch'
import { type Constraint, type PointPos, NONE, START, END, MID, H_AXIS, V_AXIS, GEO_UNDEF } from './sketch'
import { drawSketch, type DrawState, type HitRegions, type Screen, SIZES, iconsLoaded, gridSpacing, scaleFactor } from './sketchdraw'
import { getState, setState, report, saved, type Workbench } from './store'
import { getView, showPanel, closeTask, setEditHistory } from './actions'
import { api } from './api'
import { applyOps } from './partdesign'
import { userString } from './quantity'
import type { NavEvent, V2 } from './nav'
import { isMac } from './nav'

// ── the session ──────────────────────────────────────────────────────────────────────────────────────────────────
/** Where the sketch lies in the world: SketchObject's Placement (its attachment) in the part's frame. */
export type Placement = { base: [number, number, number]; rotation: [number, number, number, number] }
/** A sketch to edit: the part module it is saved into (null for one not yet in a part), its name in that module's
 *  SKETCHES, where it lies, and its geometry and constraints in the solver's form. */
export type SketchRef = { part: string | null; name: string; placement?: Placement; sketch?: Sketch; external?: External }
/** The sketch's external geometry (SketchObject's ExternalGeometry and ExternalGeo after the axes): the references as
 *  the part file names them ([object, element]), the geometry they project to (GeoId -3, -4, …), and for each
 *  geometry the reference it comes from (a face gives several). */
export type External = { refs: [string, string][]; geometry: Geo[]; owner: number[] }
type Snapshot = { geometry: Geo[]; constraints: Constraint[]; external: External }
const noExternal = (): External => ({ refs: [], geometry: [], owner: [] })
const copyExternal = (e: External): External => ({ refs: e.refs.map((r) => [...r] as [string, string]), geometry: e.geometry.map((g) => ({ ...g })), owner: [...e.owner] })
/** ViewProviderSketch::Mode (SketchMode). */
export type Mode = 'none' | 'selectPoint' | 'selectEdge' | 'selectCross' | 'selectConstraint' | 'selectWire' | 'drag' | 'dragConstraint'
  | 'useHandler' | 'startRubber' | 'rubber'
/** ViewProviderSketch::Preselection: a vertex (or -1), a curve (GeoId, or null), the cross (0 root, 1 H axis, 2 V axis),
 *  constraints. */
export type Pre = { point: number; curve: number | null; cross: number | null; constraints: number[] }
/** TaskSolverMessages: the state, the status label's text, and the link after it. */
export type SolverMessage = { state: 'empty' | 'under_constrained' | 'fully_constrained' | 'conflicting_constraints' | 'redundant_constraints'
  | 'partially_redundant_constraints' | 'malformed_constraints' | 'solver_failed'; text: string; link: string; linkText: string }

/** What a geometry tool (DrawSketchHandler, sketchtools.ts) gets from the edit mode and gives it. */
export interface Handler {
  readonly toolName: string
  activated(): void
  deactivated(): void
  mouseMove(pos: XY): void
  pressButton(pos: XY): boolean
  releaseButton(pos: XY): boolean
  pressRightButton(pos: XY): void
  /** A key, pressed or released; true when the tool used it. */
  registerPressedKey(pressed: boolean, key: string): boolean
  /** The crosshair cursor's SVG (Sketcher_Pointer_*) and the auto-constraint icons it carries. */
  cursor(): { svg: string; tail: string[] } | null
  /** MainWindow::showHints. */
  hints(): { message: string; keys: string[] }[]
}

type DragState = { geo: [number, PointPos][]; drag: Drag | null; xInit: number; yInit: number; relative: boolean; start: Snapshot; moved: boolean }
export type EditView = { curves: XY[][]; construction: boolean; markers: XY[]; extensionHint: XY[] | null; directionHints: { lines: XY[][]; active: number }
  positionText: { at: XY; text: string } | null; ovps: DrawState['ovps'] }
const emptyEdit = (): EditView => ({ curves: [], construction: false, markers: [], extensionHint: null, directionHints: { lines: [], active: -1 }, positionText: null, ovps: [] })

type Session = {
  ref: SketchRef
  placement: Placement
  geometry: Geo[]
  constraints: Constraint[]
  external: External
  result: SolveResult | null
  message: SolverMessage
  backup: Snapshot
  undo: (Snapshot & { name: string })[]
  redo: (Snapshot & { name: string })[]
  /** Gui::Selection for this sketch, in the order things were picked ("Edge1", "Vertex3", "RootPoint", "H_Axis",
   *  "Constraint2"): the constraint commands read it in order, as FreeCAD's getSelectionEx does. */
  selection: string[]
  pre: Pre
  mode: Mode
  handler: Handler | null
  /** GeometryCreationMode: new geometry is construction geometry. */
  construction: boolean
  edit: EditView
  rubber: { a: [number, number]; b: [number, number] } | null
  drag: DragState | null
  dragConstraints: { ids: number[]; xInit: number; yInit: number; start: Constraint[] } | null
  /** Constraint::isVisible off (TaskSketcherConstraints' Display only filtered constraints): constraints the view leaves out. */
  hiddenConstraints: Set<number>
  /** ViewProviderSketch::isShownVirtualSpace: the view shows the constraints in the other virtual space (Sketcher_SwitchVirtualSpace). */
  shownVirtualSpace: boolean
  before: { hidden: string[]; camera: string | null; workbench: Workbench }
  /** An open command (Gui::Document::openCommand): its name and the sketch before it. */
  command: { name: string; before: Snapshot } | null
  hits: HitRegions
  /** The last press (DoubleClick::prvClickPos / prvClickTime) and the cursor (prvCursorPos / newCursorPos). */
  click: { pos: [number, number]; t: number; cursor: [number, number] }
  showGrid: boolean
  angleSnap: { on: boolean; ref: XY; last: number }
  saving: boolean
  /** TaskSketcherElements' list: slotElementsChanged rebuilds it (leaving every row unselected) when the geometry or
   *  a constraint changes as a property change, and onSelectionChanged re-selects its rows when the selection
   *  changes. A counter and which of the two it counts last, so that the Elements box can wait for the last signal. */
  listVersion: number
  lastListChange: 'elements' | 'selection'
}

let solver: Solver | null = null
let session: Session | null = null
const subs = new Set<() => void>()
let version = 0
function changed() {
  version++
  subs.forEach((f) => f())
  getView()?.redraw()
}
export function subscribeSketch(f: () => void) { subs.add(f); return () => { subs.delete(f) } }
export const sketchVersion = () => version
export const getSession = () => session
export const isEditing = () => !!session
/** What the Elements box reads: see Session.listVersion. */
export const elementsListEvent = (): { version: number; last: 'elements' | 'selection' } =>
  ({ version: session?.listVersion ?? 0, last: session?.lastListChange ?? 'elements' })
function elementsChanged() { if (session) { session.listVersion++; session.lastListChange = 'elements' } }
function selectionChanged() { if (session) { session.listVersion++; session.lastListChange = 'selection' } }

// ── geometry helpers on the session ──────────────────────────────────────────────────────────────────────────────
const sel = () => session?.selection ?? []
export const selectedPoints = () => new Set(sel().filter((n) => n.startsWith('Vertex') || n === 'RootPoint').map((n) => (n === 'RootPoint' ? -1 : Number(n.slice(6)) - 1)))
export const selectedCurves = () => new Set(sel().map(SK.edgeId).filter((g): g is number => g !== null))
/** getCompleteGeometry: the geometry, with the external geometry at its negative GeoIds (SK.withExternal). */
const geoAll = (): Geo[] => (session ? SK.withExternal(session.geometry, session.external.geometry) : [])
export const selectedConstraints = () => new Set(sel().filter((n) => n.startsWith('Constraint')).map((n) => Number(n.slice(10)) - 1))

/** ViewProviderSketch::getEditingPlacement as a matrix (sketch to world). */
function sketchMatrix(p: Placement) {
  return new THREE.Matrix4().compose(new THREE.Vector3(...p.base), new THREE.Quaternion(...p.rotation), new THREE.Vector3(1, 1, 1))
}

// ── the view ─────────────────────────────────────────────────────────────────────────────────────────────────────
/** The camera and canvas the 3D view draws with (CadView.sketchViewport). */
export type Viewport = { cam: THREE.Camera; w: number; h: number; hole: Screen['hole']; target: THREE.Vector3 }
function screenOf(vp: Viewport, p: Placement): Screen & { toSketch(x: number, y: number): XY | null; center: XY } {
  const m = sketchMatrix(p), inv = m.clone().invert()
  const cam = vp.cam as THREE.OrthographicCamera & THREE.PerspectiveCamera
  cam.updateMatrixWorld()
  const v = new THREE.Vector3()
  const toScreen = (q: XY): [number, number] => {
    v.set(q[0], q[1], 0).applyMatrix4(m).project(cam)
    return [((v.x + 1) / 2) * vp.w, ((1 - v.y) / 2) * vp.h]
  }
  const ray = new THREE.Raycaster()
  const normal = new THREE.Vector3(0, 0, 1).applyQuaternion(new THREE.Quaternion(...p.rotation))
  const plane = new THREE.Plane().setFromNormalAndCoplanarPoint(normal, new THREE.Vector3(...p.base))
  /** getProjectingLine + getCoordsOnSketchPlane: the pixel's ray through the sketch's plane, in sketch coordinates. */
  const toSketch = (x: number, y: number): XY | null => {
    ray.setFromCamera(new THREE.Vector2((x / vp.w) * 2 - 1, 1 - (y / vp.h) * 2), cam)
    const hit = ray.ray.intersectPlane(plane, new THREE.Vector3())
    if (!hit) return null
    hit.applyMatrix4(inv)
    return [hit.x, hit.y]
  }
  let worldPerPx: number, visibleHeight: number
  if (cam.isOrthographicCamera) { visibleHeight = (cam.top - cam.bottom) / cam.zoom; worldPerPx = visibleHeight / vp.h }
  else { const d = cam.position.distanceTo(vp.target); visibleHeight = 2 * d * Math.tan(THREE.MathUtils.degToRad(cam.fov) / 2); worldPerPx = visibleHeight / vp.h }
  const c = vp.target.clone().applyMatrix4(inv)
  return { w: vp.w, h: vp.h, toScreen, toSketch, worldPerPx, visibleHeight, hole: vp.hole, center: [c.x, c.y] }
}
let lastScreen: ReturnType<typeof screenOf> | null = null
const screen = () => {
  const vp = getView()?.sketchViewport()
  if (!vp || !session) return lastScreen
  lastScreen = screenOf(vp, session.placement)
  return lastScreen
}
/** ViewProviderSketch::getScaleFactor. */
export const getScaleFactor = () => { const s = screen(); return s ? scaleFactor(s) : 1 }
export const worldPerPx = () => screen()?.worldPerPx ?? 0.1
export const toScreen = (p: XY) => screen()?.toScreen(p) ?? [0, 0]
export const gridSize = () => { const s = screen(); return s ? gridSpacing(s, 10) : 10 }

function drawState(): DrawState {
  const s = session!
  const r = s.result
  return {
    geometry: geoAll(), external: s.external.geometry, constraints: s.constraints, fully: !!r && (r.fully_constrained ?? (r.dof === 0 && r.status === 'solved')) && s.geometry.length > 0,
    // SolverGeometryExtension::FullyConstraint: a geometry none of whose parameters is still free
    fullyElements: new Set(r?.dependent ? s.geometry.map((_, i) => i).filter((i) => !r.dependent!.some(([g]) => g === i)) : []),
    invalid: false, preselect: s.pre,
    selection: { points: selectedPoints(), curves: selectedCurves(), constraints: selectedConstraints() },
    editCurves: s.edit.curves, editConstruction: s.edit.construction, editMarkers: s.edit.markers, extensionHint: s.edit.extensionHint,
    directionHints: s.edit.directionHints, positionText: s.edit.positionText, ovps: s.edit.ovps, rubber: s.rubber, showGrid: s.showGrid,
    // a constraint shows when it is visible and in the virtual space the view shows (EditModeConstraintCoinManager)
    gridSize: 10, hiddenConstraints: new Set([...s.hiddenConstraints, ...s.constraints.flatMap((c, i) => (c.virtual !== s.shownVirtualSpace ? [i] : []))]),
  }
}

// ── solving and the solver's messages ────────────────────────────────────────────────────────────────────────────
/** The solver's sketch: geometry, constraints, and the external geometry as fixed geometry (Sketch::setUpSketch). */
export const toSketch = (s: Snapshot): Sketch => ({ geometry: s.geometry, constraints: s.constraints.map(SK.toCons),
  ...(s.external.geometry.length ? { external: s.external.geometry } : {}) })
/** intListHelper, of the constraints' numbers as FreeCAD's messages give them: from 1 (the solver's are 0-based). */
const intList = (zero: number[]) => { const ints = zero.map((i) => i + 1); return ints.length < 8 ? ints.join(', ') : `${ints.slice(0, 3).join(', ')}, and ${ints.length - 3} more` }
/** ViewProviderSketch::UpdateSolverInformation. */
function messageOf(s: Session): SolverMessage {
  const r = s.result
  // (ViewProviderSketch::UpdateSolverInformation: empty is no geometry and nothing beyond the axes in ExternalGeo)
  if (!s.geometry.length && !s.external.geometry.length) return { state: 'empty', text: 'Empty sketch', link: '', linkText: '' }
  if (!r) return { state: 'solver_failed', text: 'Solver failed to converge', link: '', linkText: '' }
  if (r.dof < 0 || r.conflicting.length) return { state: 'conflicting_constraints', text: 'Over-constrained: ', link: '#conflicting', linkText: `(${intList(r.conflicting)})` }
  if (r.malformed.length) return { state: 'malformed_constraints', text: 'Malformed constraints: ', link: '#malformed', linkText: `(${intList(r.malformed)})` }
  if (r.redundant.length) return { state: 'redundant_constraints', text: 'Redundant constraints: ', link: '#redundant', linkText: `(${intList(r.redundant)})` }
  if (r.partially_redundant.length) return { state: 'partially_redundant_constraints', text: 'Partially redundant: ', link: '#partiallyredundant', linkText: `(${intList(r.partially_redundant)})` }
  if (r.status === 'failed') return { state: 'solver_failed', text: 'Solver failed to converge', link: '', linkText: '' }
  if (r.dof > 0) return { state: 'under_constrained', text: 'Under-constrained: ', link: '#dofs', linkText: `${r.dof} Degrees of Freedom` /* tr("%n Degrees of Freedom", "", dofs): with no English plural forms loaded, FreeCAD 26.3 says "1 Degrees" too */ }
  return { state: 'fully_constrained', text: 'Fully constrained', link: '', linkText: '' }
}
/** SketchObject::solve: geometry moves to the solution; a reference dimension takes the value it measures. */
export function solve() {
  const s = session
  if (!s || !solver) return null
  const r = solver.solve(toSketch(s))
  s.result = r
  // SketchObject keeps the solved geometry only when the solve succeeds (stored_geometry)
  s.geometry = r.stored_geometry ?? (r.status === 'solved' || r.status === 'redundant' ? r.geometry : s.geometry)
  // SketchObject::updateNonDrivingConstraints
  s.constraints = s.constraints.map((c) => (!c.driving && SK.isDimensional(c) ? { ...c, value: SK.measure(geoAll(), c) } : c))
  s.message = messageOf(s)
  changed()
  publishSketch()
  return r
}
/** The sketch in edit, for `cad gui` (GET /api/gui's "sketch"): what an agent, or ui/scripts/sketchcheck.mjs, reads back. */
let publishTimer = 0
function publishSketch() {
  clearTimeout(publishTimer)
  publishTimer = window.setTimeout(() => {
    const slug = getState().slug, s = session
    if (!slug) return
    const sketch = s ? {
      name: s.ref.name, part: s.ref.part, geometry: s.geometry,
      ...(s.external.refs.length ? { external: s.external.geometry, external_geometry: s.external.refs } : {}),
      constraints: s.constraints.map(SK.toCons),
      message: { state: s.message.state, status: s.message.text, link: s.message.linkText },
    } : null
    api.setGui(slug, { sketch }).catch(() => { /* best effort, as publishGui */ })
  }, 30)
}
/** The solver on a sketch other than the session's (with planegcs' extras: "solve": false, "drags"), for the editing
 *  operations' moves (sketchops.ts's Mover); null before the solver is loaded. */
export function solveRaw(s: Sketch & { solve?: boolean; drags?: { geo: number; pos: number; to: XY; update_geometry?: boolean }[] }) {
  return solver ? solver.solve(s) : null
}
/** SketchObject::diagnoseAdditionalConstraints: the solver's verdict with extra constraints, the sketch unchanged. */
export function diagnoseWith(extra: Constraint[]) {
  const s = session
  if (!s || !solver) return null
  return solver.solve(toSketch({ geometry: s.geometry, constraints: [...s.constraints, ...extra], external: s.external }))
}

// ── commands and undo (Gui::Document's transactions while the sketch is in edit) ────────────────────────────────
const snap = (): Snapshot => ({ geometry: session!.geometry.map((g) => ({ ...g })), constraints: session!.constraints.map((c) => ({ ...c })),
  external: copyExternal(session!.external) })
const same = (a: Snapshot, b: Snapshot) => JSON.stringify(a) === JSON.stringify(b)
export function openCommand(name: string) { if (session) session.command = { name, before: snap() } }
export function commitCommand() {
  const s = session
  if (!s?.command) return
  if (!same(s.command.before, snap())) { s.undo.unshift({ ...s.command.before, name: s.command.name }); s.redo = [] ; s.undo.splice(20) }
  s.command = null
  publishHistory()
}
export function abortCommand() {
  const s = session
  if (!s?.command) return
  s.geometry = s.command.before.geometry; s.constraints = s.command.before.constraints; s.external = s.command.before.external
  s.command = null
  elementsChanged()
  solve()
}
function publishHistory() {
  const s = session
  setEditHistory(s ? { undo: s.undo.map((u, i) => ({ id: `sk${i}`, name: u.name, by: 'ui' as const, t: 0 })), redo: s.redo.map((u, i) => ({ id: `skr${i}`, name: u.name, by: 'ui' as const, t: 0 })) } : null,
    { undo, redo })
}
/** Std_Undo while the sketch is in edit: the last sketch command (slotUndoDocument redraws). */
export function undo(steps = 1) {
  const s = session
  if (!s) return
  for (let i = 0; i < steps && s.undo.length; i++) {
    const u = s.undo.shift()!
    s.redo.unshift({ ...snap(), name: u.name })
    s.geometry = u.geometry; s.constraints = u.constraints; s.external = u.external
  }
  elementsChanged()
  clearSelection(); solve(); publishHistory()
}
export function redo(steps = 1) {
  const s = session
  if (!s) return
  for (let i = 0; i < steps && s.redo.length; i++) {
    const r = s.redo.shift()!
    s.undo.unshift({ ...snap(), name: r.name })
    s.geometry = r.geometry; s.constraints = r.constraints; s.external = r.external
  }
  elementsChanged()
  clearSelection(); solve(); publishHistory()
}

// ── geometry and constraints (SketchObject's addGeometry, addConstraint, delGeometries, delConstraints) ─────────
/** The geometry, with the external geometry reachable at its GeoIds (-3, -4, …) as getCompleteGeometry has it. */
export function getGeometry() { return geoAll() }
export const getExternal = (): External => session?.external ?? noExternal()
export function getConstraints() { return session?.constraints ?? [] }
/** The highest GeoId (SketchObject::getHighestCurveIndex). */
export const highestCurveIndex = () => (session ? session.geometry.length - 1 : -1)
/** Geometry without its construction flag, or with it set. */
export function withConstruction(g: Geo, on: boolean): Geo {
  const { construction: _c, ...rest } = g as Geo & { construction?: boolean }
  void _c
  return (on ? { ...rest, construction: true } : rest) as Geo
}
/** Geometry on a visual layer: 0 (Normal) is left out, as the part file writes it. */
export function withLayer(g: Geo, layer: number): Geo {
  const { layer: _l, ...rest } = g as Geo & { layer?: number }
  void _l
  return (layer ? { ...rest, layer } : rest) as Geo
}
export function addGeometry(g: Geo | Geo[], construction?: boolean): number {
  const s = session!
  for (const e of Array.isArray(g) ? g : [g]) s.geometry = [...s.geometry, construction === undefined ? e : withConstruction(e, construction)]
  elementsChanged()
  return s.geometry.length - 1
}
export function addConstraint(c: Constraint | Constraint[]): number {
  const s = session!
  for (const k of Array.isArray(c) ? c : [c]) s.constraints.push(k)
  elementsChanged()
  return s.constraints.length - 1
}
export function setConstraints(list: Constraint[]) { session!.constraints = list; elementsChanged() }
export function setGeometry(list: Geo[]) { session!.geometry = list; elementsChanged() }
export function setConstraint(i: number, c: Constraint) { const s = session!; s.constraints = s.constraints.map((x, k) => (k === i ? c : x)); elementsChanged() }
/** SketchObject::delGeometries: the geometry, the constraints on it, the GeoIds after it renumbered. */
export function delGeometries(ids: number[]) {
  const s = session!
  const gone = new Set(ids.filter((g) => g >= 0))
  // a geometry with internal geometry takes it along (SketchObject::delGeometries)
  for (const c of s.constraints) if (c.type === 'InternalAlignment' && gone.has(c.second)) gone.add(c.first)
  const map = (g: number) => (g < 0 || g === GEO_UNDEF ? g : g - [...gone].filter((x) => x < g).length)
  s.constraints = s.constraints.filter((c) => !gone.has(c.first) && !gone.has(c.second) && !gone.has(c.third))
    .map((c) => ({ ...c, first: map(c.first), second: map(c.second), third: map(c.third) }))
  s.geometry = s.geometry.filter((_, i) => !gone.has(i))
  elementsChanged()
}
export function delConstraints(ids: number[]) {
  const s = session!
  const gone = new Set(ids)
  s.constraints = s.constraints.filter((_, i) => !gone.has(i))
  s.hiddenConstraints = new Set([...s.hiddenConstraints].filter((i) => !gone.has(i)).map((i) => i - ids.filter((x) => x < i).length))
  elementsChanged()
}
/** SketchObject::delConstraintOnPoint: the constraints on one point (a coincidence, a point on an object, a
 *  dimension to it); with onlyCoincident, only those that tie it to another point. */
export function delConstraintOnPoint(g: number, pos: PointPos, onlyCoincident = false) {
  const s = session!
  const ids: number[] = []
  s.constraints.forEach((c, i) => {
    const on = (c.first === g && c.firstPos === pos) || (c.second === g && c.secondPos === pos) || (c.third === g && c.thirdPos === pos)
    if (!on) return
    if (onlyCoincident && c.type !== 'Coincident' && !(c.type === 'Tangent' && c.firstPos !== NONE && c.secondPos !== NONE)) return
    ids.push(i)
  })
  delConstraints(ids)
}
/** SketchObject::toggleConstruction. */
export function toggleConstruction(g: number) {
  const s = session!
  s.geometry = s.geometry.map((e, i) => (i === g ? withConstruction(e, !e.construction) : e))
  elementsChanged()
}
/** SketchObject::addExternal: a reference and the geometry it projects to (rebuildExternalGeometry's), after the
 *  others. Refused as FreeCAD refuses a reference the sketch has already ("Duplicated external reference"). */
export function addExternal(ref: [string, string], geometry: Geo[]): boolean {
  const s = session!
  if (s.external.refs.some((r) => r[0] === ref[0] && r[1] === ref[1])) return false
  const i = s.external.refs.length
  s.external = { refs: [...s.external.refs, ref], geometry: [...s.external.geometry, ...geometry], owner: [...s.external.owner, ...geometry.map(() => i)] }
  elementsChanged()
  return true
}
/** SketchObject::delExternal (delExternalPrivate with removeRef): the external geometries' references go, with every
 *  geometry those references made and the constraints on any of them; the GeoIds after them move up. */
export function delExternal(geoIds: number[]) {
  const s = session!, e = s.external
  const refs = new Set(geoIds.filter(SK.isExternalId).map((g) => e.owner[SK.REF_EXT - g]).filter((r) => r !== undefined))
  if (!refs.size) return
  const gone = new Set(e.owner.map((r, k) => (refs.has(r) ? SK.REF_EXT - k : null)).filter((g): g is number => g !== null))
  const map = (g: number) => (SK.isExternalId(g) ? g + [...gone].filter((x) => x > g).length : g) // changeConstraintAfterDeletingGeo
  s.constraints = s.constraints.filter((c) => !gone.has(c.first) && !gone.has(c.second) && !gone.has(c.third))
    .map((c) => ({ ...c, first: map(c.first), second: map(c.second), third: map(c.third) }))
  const keep = e.owner.map((r) => !refs.has(r))
  const renumber = new Map([...new Set(e.owner.filter((r) => !refs.has(r)))].map((r, k) => [r, k]))
  s.external = { refs: e.refs.filter((_, r) => !refs.has(r)), geometry: e.geometry.filter((_, k) => keep[k]),
    owner: e.owner.filter((_, k) => keep[k]).map((r) => renumber.get(r)!) }
  elementsChanged()
}

// ── selection (Gui::Selection, as ViewProviderSketch::onSelectionChanged reads it) ───────────────────────────────
export function addSelection(name: string) { const s = session; if (s && !s.selection.includes(name)) { s.selection = [...s.selection, name]; selectionChanged(); changed() } }
export function rmvSelection(name: string) { const s = session; if (s) { const had = s.selection.includes(name); s.selection = s.selection.filter((n) => n !== name); if (had) selectionChanged(); changed() } }
export function isSelected(name: string) { return !!session?.selection.includes(name) }
export function clearSelection() { const s = session; if (s && s.selection.length) { s.selection = []; selectionChanged(); changed() } }
export function setSelection(names: string[]) { const s = session; if (s) { s.selection = [...new Set(names)]; selectionChanged(); changed() } }
export function getSelection() { return [...sel()] }

// ── the solver's view of points (SketchObject::getPoint, getGeoVertexIndex) ──────────────────────────────────────
export const getPoint = (g: number, pos: PointPos) => SK.getPoint(geoAll(), g, pos)
export const geoVertexIndex = (v: number): [number, PointPos] => SK.vertices(geoAll())[v] ?? [GEO_UNDEF, NONE]
export const vertexIndexOf = (g: number, pos: PointPos) => SK.vertexOf(geoAll(), g, pos)

// ── preselection (EditModeCoinManager::detectPreselection, its screen-space policy) ──────────────────────────────
type Hit = { kind: 'point' | 'edge' | 'axis' | 'constraint'; point?: number; geo?: number; cross?: number; constraints?: number[]; cKind?: 'icon' | 'presentation' | 'annotation' }
const PRIORITY = { none: 0, presentation: 100, axis: 300, fallback: 350, edge: 400, annotation: 425, icon: 450, point: 500 }
const prio = (h: Hit | null) => (!h ? 0 : h.kind === 'point' ? PRIORITY.point : h.kind === 'edge' ? PRIORITY.edge : h.kind === 'axis' ? PRIORITY.axis
  : h.cKind === 'icon' ? PRIORITY.icon : h.cKind === 'annotation' ? PRIORITY.annotation : h.cKind === 'presentation' ? PRIORITY.presentation : PRIORITY.fallback)
/** View/PickRadius (5 px): SoRayPickAction's radius. */
const pickRadius = () => getState().selPrefs.pickRadius ?? 5
function segDist2(p: [number, number], a: [number, number], b: [number, number]) {
  const dx = b[0] - a[0], dy = b[1] - a[1], l2 = dx * dx + dy * dy
  let t = l2 > 1e-9 ? ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2 : 0
  t = Math.max(0, Math.min(1, t))
  const x = a[0] + t * dx - p[0], y = a[1] + t * dy - p[1]
  return x * x + y * y
}
function detect(x: number, y: number, hovered: number): Hit | null {
  const s = session!, sc = screen()
  if (!sc) return null
  const cur: [number, number] = [x, y]
  const cands: Hit[] = []
  // constraints: icons, then datum text and lines (detectPreselectionConstr), unless Shift makes them unselectable
  if (s.mode !== 'useHandler' && constraintsSelectable) {
    const pad = 3 // ConstraintIconHitPadding
    const icon = s.hits.icons.find((b) => x >= b.x - pad && x <= b.x + b.w + pad && y >= b.y - pad && y <= b.y + b.h + pad)
    if (icon) cands.push({ kind: 'constraint', constraints: icon.ids, cKind: 'icon' })
    else {
      const lab = s.hits.labels.find((l) => {
        const dx = x - l.x, dy = y - l.y, c = Math.cos(-l.angle), sn = Math.sin(-l.angle)
        const u = dx * c - dy * sn, v = dx * sn + dy * c
        return Math.abs(u) <= l.w / 2 + 2 && Math.abs(v) <= l.h / 2 + 2
      })
      if (lab) cands.push({ kind: 'constraint', constraints: [lab.id], cKind: 'presentation' })
      else {
        const line = s.hits.datumLines.find((l) => l.pts.some((p, i) => i > 0 && segDist2(cur, l.pts[i - 1], p) <= 9))
        if (line) cands.push({ kind: 'constraint', constraints: [line.id], cKind: 'annotation' })
      }
    }
  }
  // geometry: a point near enough (hit radius: marker extent / 2 + 5 px, +2 px at an end of a curve, +2 px hysteresis
  // for the point already under the cursor), else an edge within its hit radius or the pick radius
  const all = geoAll()
  const verts = SK.vertices(all)
  let best: Hit | null = null, bestD = Infinity
  verts.forEach(([g, pos], v) => {
    if ((all[g]?.layer ?? 0) === 2) return           // a hidden visual layer is not drawn, so not pickable
    const p = SK.getPoint(all, g, pos)
    if (!p) return
    const [px, py] = sc.toScreen(p)
    const d2 = (px - x) ** 2 + (py - y) ** 2
    const end = all[g].type !== 'Point' && (pos === START || pos === END)
    const r = Math.max(SIZES.marker, SIZES.pointSize) * 0.5 + 5 + (end ? 2 : 0) + (v === hovered ? 2 : 0)
    if (d2 <= r * r && d2 <= bestD) { bestD = d2; best = { kind: 'point', point: v } }
  })
  if (!best) {
    let bestE = Infinity
    const edge = (g: Geo, i: number) => {
      if (g.type === 'Point' || (g.layer ?? 0) === 2) return
      const pts = SK.polyline(g).map((p) => sc.toScreen(p))
      const lw = SK.isExternalId(i) ? SIZES.external : g.construction ? SIZES.construction : SIZES.curve
      const r = Math.max(3, lw * 0.5 + 2, pickRadius())
      for (let k = 1; k < pts.length; k++) {
        const d2 = segDist2(cur, pts[k - 1], pts[k])
        if (d2 <= r * r && d2 < bestE) { bestE = d2; best = { kind: 'edge', geo: i } }
      }
    }
    s.geometry.forEach(edge)
    s.external.geometry.forEach((g, k) => edge(g, SK.REF_EXT - k)) // the external curves (curvesExternal)
  }
  if (best) cands.push(best)
  // the axes and the root point
  const o = sc.toScreen([0, 0]), pr = pickRadius()
  if ((o[0] - x) ** 2 + (o[1] - y) ** 2 <= (pr + SIZES.pointSize / 2) ** 2) cands.push({ kind: 'axis', cross: 0 })
  else {
    const h1 = sc.toScreen([-1e6, 0]), h2 = sc.toScreen([1e6, 0]), v1 = sc.toScreen([0, -1e6]), v2 = sc.toScreen([0, 1e6])
    const dh = segDist2(cur, h1, h2), dv = segDist2(cur, v1, v2)
    if (Math.min(dh, dv) <= pr * pr) cands.push({ kind: 'axis', cross: dh <= dv ? 1 : 2 })
  }
  return cands.reduce<Hit | null>((a, b) => (prio(b) > prio(a) ? b : a), null)
}
let constraintsSelectable = true
let lastHit: { pos: [number, number]; hit: Hit | null } | null = null
/** ViewProviderSketch::detectAndShowPreselection: true when the preselection changed. */
function showPreselection(hit: Hit | null): boolean {
  const s = session!
  const before = JSON.stringify(s.pre)
  if (!hit) s.pre = { point: -1, curve: null, cross: null, constraints: [] }
  else if (hit.kind === 'point') s.pre = { point: hit.point!, curve: null, cross: null, constraints: [] }
  else if (hit.kind === 'edge') s.pre = { point: -1, curve: hit.geo!, cross: null, constraints: [] }
  else if (hit.kind === 'axis') s.pre = { point: -1, curve: null, cross: hit.cross!, constraints: [] }
  else s.pre = { point: -1, curve: null, cross: null, constraints: hit.constraints! }
  return JSON.stringify(s.pre) !== before
}
/** ViewProviderSketch::preselectAtPoint: preselect what lies at a sketch point, as if the cursor were there. */
export function preselectAtPoint(p: XY) {
  const s = session, sc = screen()
  if (!s || !sc || ['selectPoint', 'selectEdge', 'selectConstraint', 'drag', 'dragConstraint', 'rubber'].includes(s.mode)) return
  const [x, y] = sc.toScreen(p)
  const hit = detect(x, y, lastHit?.hit?.kind === 'point' ? lastHit.hit.point! : -1)
  lastHit = { pos: [x, y], hit }
  showPreselection(hit)
}
export const getPreselection = () => session?.pre ?? { point: -1, curve: null, cross: null, constraints: [] }

// ── snapping (SnapManager) ───────────────────────────────────────────────────────────────────────────────────────
/** Sketcher/Snap: Snap and SnapToObjects on, SnapToGrid off, SnapAngle 5°. */
export const SNAP = { snap: true, objects: true, grid: false, angle: (5 * Math.PI) / 180 }
let ctrlHeld = false
export function setAngleSnapping(on: boolean, ref: XY = [0, 0]) { if (session) session.angleSnap = { on, ref, last: 0 } }
/** SnapManager::snap: at an angle (Ctrl, when the tool asks), to the preselected point or curve, to the grid. */
export function snapPosition(p: XY): XY {
  const s = session
  if (!s || !SNAP.snap) return p
  if (s.angleSnap.on && ctrlHeld) {
    const r = s.angleSnap.ref, d: XY = [p[0] - r[0], p[1] - r[1]], length = Math.hypot(d[0], d[1])
    const a1 = Math.atan2(d[1], d[0]), a2 = a1 + (a1 < 0 ? 2 : -2) * Math.PI
    s.angleSnap.last = Math.abs(a1 - s.angleSnap.last) < Math.abs(a2 - s.angleSnap.last) ? a1 : a2
    const a = Math.round(s.angleSnap.last / SNAP.angle) * SNAP.angle
    return [r[0] + length * Math.cos(a), r[1] + length * Math.sin(a)]
  }
  if (s.angleSnap.on) s.angleSnap.last = 0
  let out: XY = [...p] as XY
  if (SNAP.objects) {
    const pre = s.pre
    if (pre.cross === 0) return [0, 0]
    const all = geoAll()
    if (pre.point >= 0) { const [g, pos] = geoVertexIndex(pre.point); const q = SK.getPoint(all, g, pos); if (q) return q }
    if (pre.cross === 1) out = [out[0], 0]
    else if (pre.cross === 2) out = [0, out[1]]
    else if (pre.curve !== null && !SK.isAxisId(pre.curve) && all[pre.curve]) {
      const g = all[pre.curve]
      let q = SK.closestOnCurve(g, p)
      if (SK.isLine(g)) { // snapToLineMiddle
        const mid: XY = [(g.start[0] + g.end[0]) / 2, (g.start[1] + g.end[1]) / 2], l = Math.hypot(g.end[0] - g.start[0], g.end[1] - g.start[1])
        if (Math.hypot(q[0] - mid[0], q[1] - mid[1]) < l * 0.05) q = mid
      } else if (SK.isArc(g)) { // snapToArcMiddle
        const sp = SK.getPoint(all, pre.curve, START)!, ep = SK.getPoint(all, pre.curve, END)!
        const sv: XY = [sp[0] - g.center[0], sp[1] - g.center[1]]
        let mv: XY = [sv[0] + ep[0] - g.center[0], sv[1] + ep[1] - g.center[1]]
        const ml = Math.hypot(mv[0], mv[1])
        mv = ml < 1e-7 ? [sv[1], -sv[0]] : [(mv[0] / ml) * g.radius, (mv[1] / ml) * g.radius]
        const angle = g.end_angle - g.start_angle, revert = angle < Math.PI ? 1 : -1
        const pa = Math.atan2(q[1] - g.center[1], q[0] - g.center[0]), ma = Math.atan2(revert * mv[1], revert * mv[0])
        if (Math.abs(pa - ma) < 0.1 * angle) q = [g.center[0] + mv[0] * revert, g.center[1] + mv[1] * revert]
      }
      return q
    }
  }
  if (SNAP.grid) {
    const gs = gridSize(), tol = gs / 5
    const cx = Math.round(out[0] / gs) * gs, cy = Math.round(out[1] / gs) * gs
    if (Math.abs(out[0] - cx) < tol) out = [cx, out[1]]
    if (Math.abs(out[1] - cy) < tol) out = [out[0], cy]
  }
  return out
}

// ── tools ────────────────────────────────────────────────────────────────────────────────────────────────────────
/** ViewProviderSketch::activateHandler: the tool takes the mouse; any selection is cleared. */
export function activateHandler(h: Handler) {
  const s = session
  if (!s) return
  if (s.handler) deactivateHandler()
  s.handler = h
  s.mode = 'useHandler'
  s.edit = emptyEdit()
  clearSelection()
  h.activated()
  applyCursor()
  setState({ hints: h.hints() })
  changed()
}
/** ViewProviderSketch::purgeHandler / deactivateHandler: back to selecting. */
export function deactivateHandler() {
  const s = session
  if (!s?.handler) return
  const h = s.handler
  s.handler = null
  h.deactivated()
  s.mode = 'none'
  s.edit = emptyEdit()
  setState({ hints: [] })
  applyCursor()
  changed()
}
export const purgeHandler = deactivateHandler
export const getHandler = () => session?.handler ?? null
export function setEdit(patch: Partial<EditView>) { const s = session; if (s) { s.edit = { ...s.edit, ...patch }; changed() } }
export function updateHints() { const h = session?.handler; if (h) setState({ hints: h.hints() }) }
export const isConstructionMode = () => !!session?.construction
export function setConstructionMode(on: boolean) { const s = session; if (s) { s.construction = on; changed() } }

/** DrawSketchHandler's cursors: the tool's crosshair SVG, its white drawn in CursorCrosshairColor, 32 px with the hot spot at
 *  (8, 8), and the auto-constraints' 16 px icons after it (ToolHandler::setCrosshairCursor, addCursorTail). */
const cursorCache = new Map<string, string>()
const svgText = new Map<string, string>()
async function cursorUrl(svg: string, tail: string[]): Promise<string | null> {
  const key = svg + '|' + tail.join(',')
  if (cursorCache.has(key)) return cursorCache.get(key)!
  const load = async (name: string, recolor: boolean) => {
    let t = svgText.get(name)
    if (t === undefined) { try { t = await (await fetch(`./freecad-icons/sketcher/${name}.svg`)).text() } catch { t = '' } ; svgText.set(name, t) }
    if (!t) return null
    if (recolor) t = t.replace(/#(?:ffffff|fff)\b/gi, '#212529')
    const img = new Image()
    img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(t)
    await img.decode().catch(() => {})
    return img
  }
  const base = await load(svg, true)
  if (!base) return null
  const icons = await Promise.all(tail.map((n) => load(n, false)))
  const c = document.createElement('canvas')
  c.width = 32 + 16 * icons.length; c.height = 32
  const g = c.getContext('2d')!
  g.drawImage(base, 0, 0, 32, 32)
  icons.forEach((im, i) => { if (im) g.drawImage(im, 32 + 16 * i, 16, 16, 16) })
  const url = `url(${c.toDataURL()}) 8 8, crosshair`
  cursorCache.set(key, url)
  return url
}
let cursorSeq = 0
export function applyCursor() {
  const s = session, v = getView()
  const want = s?.handler?.cursor() ?? null
  const seq = ++cursorSeq
  if (!want) { v?.setSketchCursor(''); return }
  void cursorUrl(want.svg, want.tail).then((u) => { if (seq === cursorSeq) v?.setSketchCursor(u ?? 'crosshair') })
}

// ── the mouse (ViewProviderSketch::mouseButtonPressed / mouseMove) ───────────────────────────────────────────────
const toTopLeft = (pos: V2, h: number): [number, number] => [pos[0], h - 1 - pos[1]]
function sketchPos(x: number, y: number): XY | null { return screen()?.toSketch(x, y) ?? null }

function hitNow(x: number, y: number) {
  const hovered = lastHit?.hit?.kind === 'point' ? lastHit.hit.point! : -1
  return detect(x, y, hovered)
}
/** resolveClickPreselectionResult: the hover's result if the press is within the pick radius of it. */
function clickHit(x: number, y: number) {
  const now = hitNow(x, y)
  if (lastHit && (lastHit.pos[0] - x) ** 2 + (lastHit.pos[1] - y) ** 2 <= pickRadius() ** 2) return lastHit.hit
  return now
}
let blockContextMenu = false

/** The 3D view's events in edit mode (CadView.sketch.event): true when the Sketcher used it. */
export function handleEvent(ev: NavEvent): boolean {
  const s = session, sc = screen()
  if (!s || !sc) return false
  ctrlHeld = ev.ctrl
  if (ev.type === 'move') return mouseMove(ev, sc.h)
  if ((ev.type === 'press' || ev.type === 'release') && ev.button === 1) return leftButton(ev, sc.h)
  if ((ev.type === 'press' || ev.type === 'release') && ev.button === 2) return rightButton(ev, sc.h)
  return false
}

function leftButton(ev: NavEvent, h: number): boolean {
  const s = session!
  const [x, y] = toTopLeft(ev.pos, h)
  const raw = sketchPos(x, y)
  if (!raw) return false
  if (ev.type === 'press') {
    if (s.mode === 'useHandler' && s.handler) { const p = snapPosition(raw); s.handler.pressButton(p); changed(); return true }
    if (s.mode !== 'none') return false
    const hit = clickHit(x, y)
    showPreselection(hit)
    let done = true
    if (hit?.kind === 'point') s.mode = 'selectPoint'
    else if (hit?.kind === 'edge') s.mode = 'selectEdge'
    else if (hit?.kind === 'axis') s.mode = 'selectCross'
    else if (hit?.kind === 'constraint') s.mode = 'selectConstraint'
    else done = false
    const dci = doubleClickMs() / 1000
    if (done && Math.hypot(x - s.click.pos[0], y - s.click.pos[1]) < 5 && ev.t - s.click.t < dci) {
      editDoubleClicked()
      s.click = { pos: [-16000, -16000], t: 0, cursor: [x, y] }
      if ((s.mode as Mode) !== 'selectWire') s.mode = 'none'
    } else {
      s.click = { pos: [x, y], t: ev.t, cursor: [x, y] }
      if (!done) s.mode = 'startRubber'
    }
    changed()
    // FreeCAD hands an empty press on to the navigation; here the Sketcher keeps it, so that the drag becomes its own
    // rubber band and not the 3D view's box selection.
    return true
  }
  // release
  const p = snapPosition(raw)
  switch (s.mode) {
    case 'useHandler': if (s.handler) { applyCursor(); s.handler.releaseButton(p) } changed(); return true
    case 'selectPoint': if (s.pre.point >= 0) preselectToSelection(SK.vertexName(s.pre.point), ev.ctrl); s.mode = 'none'; changed(); return true
    case 'selectEdge': if (s.pre.curve !== null) preselectToSelection(SK.edgeName(s.pre.curve), ev.ctrl); s.mode = 'none'; changed(); return true
    case 'selectCross': if (s.pre.cross !== null) preselectToSelection(['RootPoint', 'H_Axis', 'V_Axis'][s.pre.cross], ev.ctrl); s.mode = 'none'; changed(); return true
    case 'selectWire': toggleWireSelection(s.pre.curve); s.mode = 'none'; changed(); return true
    case 'selectConstraint': for (const id of s.pre.constraints) preselectToSelection(SK.constraintSelName(id), ev.ctrl, true); s.mode = 'none'; changed(); return true
    case 'drag': commitDragMove(p); s.mode = 'none'; changed(); return true
    case 'dragConstraint': commitConstraintDrag(p); s.mode = 'none'; changed(); return true
    case 'startRubber': if (!ev.ctrl) clearSelection(); s.mode = 'none'; changed(); return true
    case 'rubber': doBoxSelection(s.click.cursor, [x, y], ev.ctrl); s.rubber = null; blockContextMenu = true; s.mode = 'none'; changed(); return true
    default: return false
  }
}
/** ViewProviderSketch::preselectToSelection: a click toggles the element's selection (Ctrl keeps the rest; FreeCAD's
 *  SoFCUnifiedSelection adds without Ctrl too in edit mode, which is what selecting several elements for a constraint
 *  needs). */
function preselectToSelection(name: string, _ctrl: boolean, isConstraint = false) {
  void isConstraint
  if (isSelected(name)) rmvSelection(name)
  else addSelection(name)
}
function rightButton(ev: NavEvent, h: number): boolean {
  const s = session!
  const [x, y] = toTopLeft(ev.pos, h)
  if (ev.type === 'press') {
    blockContextMenu = false
    if (s.mode === 'rubber') { s.rubber = null; blockContextMenu = true; s.mode = 'none'; changed(); return true }
    return s.mode === 'useHandler'
  }
  if (s.mode === 'useHandler' && s.handler) {
    const raw = sketchPos(x, y)
    s.handler.pressRightButton(raw ?? [0, 0])
    changed()
    return true
  }
  return false
}
/** NavigationStyle::openPopupMenu while editing: the Sketcher's own menu (generateContextMenu), or nothing while a tool
 *  runs (its right click finished it above). */
export function wantsPopup(): 'sketch' | 'none' {
  const s = session
  if (!s) return 'none'
  if (s.mode === 'useHandler' || blockContextMenu) { blockContextMenu = false; return 'none' }
  return 'sketch'
}

function mouseMove(ev: NavEvent, h: number): boolean {
  const s = session!
  const [x, y] = toTopLeft(ev.pos, h)
  cursorPx = [x, y]
  // Shift makes constraints unselectable while nothing else goes on (setConstraintSelectability)
  if (['none', 'selectPoint', 'selectEdge', 'selectCross', 'selectConstraint', 'selectWire'].includes(s.mode)) constraintsSelectable = !ev.shift
  if (['selectPoint', 'selectEdge', 'selectConstraint', 'startRubber'].includes(s.mode)) {
    const dx = x - s.click.cursor[0], dy = y - s.click.cursor[1]
    if (Math.abs(dx) < 3 && Math.abs(dy) < 3) return true
  }
  const raw = sketchPos(x, y)
  if (!raw) return false
  let preChanged = false
  if (!['selectPoint', 'selectEdge', 'selectConstraint', 'drag', 'dragConstraint', 'rubber'].includes(s.mode)) {
    const hit = hitNow(x, y)
    lastHit = { pos: [x, y], hit }
    preChanged = showPreselection(hit)
  }
  switch (s.mode) {
    case 'none': if (preChanged) changed(); return false
    case 'selectPoint':
      if (!s.result?.conflicting.length && s.pre.point >= 0) { const [g, pos] = geoVertexIndex(s.pre.point); initDragging(g, pos, snapPosition(raw)) }
      else s.mode = 'none'
      s.pre = { ...s.pre, point: -1 }
      changed(); return true
    case 'selectEdge':
      if (!s.result?.conflicting.length && s.pre.curve !== null && s.pre.curve >= 0) initDragging(s.pre.curve, NONE, snapPosition(raw))
      else s.mode = 'none'
      s.pre = { ...s.pre, curve: null }
      changed(); return true
    case 'selectConstraint': {
      const ids = s.pre.constraints
      const start = sketchPos(...s.click.cursor) ?? raw
      s.mode = 'dragConstraint'
      s.dragConstraints = { ids, xInit: start[0], yInit: start[1], start: s.constraints.map((c) => ({ ...c })) }
      s.pre = { ...s.pre, constraints: [] }
      changed(); return true
    }
    case 'drag': doDragStep(snapPosition(raw)); return true
    case 'dragConstraint': if (s.dragConstraints) { const p = snapPosition(raw); for (const id of s.dragConstraints.ids) moveConstraint(id, p) } changed(); return true
    case 'useHandler': if (s.handler) { s.handler.mouseMove(snapPosition(raw)); if (preChanged) applyCursor() } changed(); return true
    case 'startRubber': s.mode = 'rubber'; s.rubber = { a: s.click.cursor, b: [x, y] }; changed(); return true
    case 'rubber': s.rubber = { a: s.click.cursor, b: [x, y] }; changed(); return true
    default: return false
  }
}
const doubleClickMs = () => saved.get('doubleClickInterval', 0) || 400

/** ViewProviderSketch::editDoubleClicked: a datum's dialog; an edge selects its wire. */
function editDoubleClicked() {
  const s = session!
  if (s.pre.curve !== null && s.pre.curve >= 0) { s.mode = 'selectWire'; return }
  for (const id of s.pre.constraints) {
    const c = s.constraints[id]
    if (c && SK.isDimensional(c)) { onDatumDoubleClick?.(id); return }
  }
}
let onDatumDoubleClick: ((id: number) => void) | null = null
/** The datum dialog (EditDatumDialog, sketchpanel.tsx) registers here. */
export function onEditDatum(f: (id: number) => void) { onDatumDoubleClick = f }

/** ViewProviderSketch::toggleWireSelection: the edges joined end to end with the one clicked. */
function toggleWireSelection(g: number | null) {
  const s = session!
  if (g === null || g < 0) return
  const wire = new Set<number>([g]), stack = [g]
  while (stack.length) {
    const cur = stack.pop()!
    for (const pos of [START, END] as PointPos[]) {
      for (const [og] of SK.coincidentPoints(s.constraints, cur, pos)) if (og >= 0 && !wire.has(og) && s.geometry[og].type !== 'Point') { wire.add(og); stack.push(og) }
    }
  }
  const names = [...wire].map(SK.edgeName)
  if (names.every((n) => isSelected(n))) setSelection(sel().filter((n) => !names.includes(n)))
  else setSelection([...sel(), ...names])
}

// ── dragging (initDragging, doDragStep, commitDragMove) ──────────────────────────────────────────────────────────
function initDragging(geoId: number, pos: PointPos, at: XY) {
  const s = session!
  if (geoId < 0 || !solver) { s.mode = 'none'; return }
  const dragged: [number, PointPos][] = [[geoId, pos]]
  // selected curves and points go with it (they all move by the cursor's displacement then)
  for (const g of selectedCurves()) {
    if (g < 0) continue
    if (g === geoId) { if (!(pos === MID && SK.isArc(s.geometry[g]))) dragged[0][1] = NONE }
    else dragged.push([g, NONE])
  }
  for (const v of selectedPoints()) {
    if (v < 0) continue
    const [g, p] = geoVertexIndex(v)
    if (!dragged.some(([dg, dp]) => dg === g && (dp === p || dp === NONE))) dragged.push([g, p])
  }
  const start = snap()
  let relative = false, xInit = 0, yInit = 0
  const g0 = s.geometry[dragged[0][0]]
  if ((dragged.length === 1 && dragged[0][1] === NONE && SK.isLine(g0)) || dragged.length > 1) {
    relative = true
    const p0 = sketchPos(...s.click.cursor) ?? at
    const sp = snapPosition(p0); xInit = sp[0]; yInit = sp[1]
  }
  s.drag = { geo: dragged, drag: dragged.length === 1 ? solver.drag(toSketch(start), dragged[0][0], dragged[0][1]) : null, xInit, yInit, relative, start, moved: false }
  s.mode = 'drag'
}
/** moveGeometriesTemporary: the solver pulls the dragged element to the cursor, everything else as the constraints let it. */
function doDragStep(p: XY) {
  const s = session!, d = s.drag
  if (!d || !solver) return
  const vec: XY = [p[0] - d.xInit, p[1] - d.yInit]
  let r: SolveResult
  if (d.drag) r = d.drag.move(d.relative ? vec : p, d.relative)
  else {
    // several elements: each point moves by the displacement, then the solver settles the constraints around them
    const moved = d.start.geometry.map((g, i) => {
      const ds = d.geo.filter(([gi]) => gi === i)
      if (!ds.length) return g
      return translateGeo(g, vec, ds.some(([, ps]) => ps === NONE) ? NONE : ds[0][1])
    })
    r = solver.solve(toSketch({ geometry: moved, constraints: d.start.constraints, external: d.start.external }))
  }
  if (r.status === 'solved' || r.status === 'redundant') {
    s.geometry = r.geometry
    d.moved = true
    s.edit = { ...s.edit, positionText: { at: p, text: positionString(p) } }
  }
  s.result = { ...r, geometry: s.geometry }
  changed()
}
function translateGeo(g: Geo, v: XY, pos: PointPos): Geo {
  const t = (q: XY): XY => [q[0] + v[0], q[1] + v[1]]
  if (g.type === 'Point') return { ...g, at: t(g.at) }
  if (g.type === 'LineSegment') return pos === START ? { ...g, start: t(g.start) } : pos === END ? { ...g, end: t(g.end) } : { ...g, start: t(g.start), end: t(g.end) }
  if (g.type === 'BSplineCurve') return { ...g, poles: g.poles.map(t) }
  return { ...g, center: t(g.center) }
}
function commitDragMove(p: XY) {
  const s = session!, d = s.drag
  if (!d) return
  doDragStep(p)
  d.drag?.end()
  const name = d.geo.length === 1 ? (d.geo[0][1] === NONE ? 'Drag Curve' : 'Drag Point') : 'Drag geometries'
  if (d.moved) { s.command = { name, before: d.start }; commitCommand() }
  s.drag = null
  s.edit = { ...s.edit, positionText: null }
  solve()
}
/** ViewProviderSketch::moveConstraint: a datum's label where the cursor put it (LabelDistance, LabelPosition). */
export function moveConstraint(id: number, to: XY) {
  const s = session!
  const c = { ...s.constraints[id] }
  const geo = geoAll(), P = (g: number, pos: PointPos) => SK.getPoint(geo, g, pos)!
  const n2 = (v: XY): XY => { const l = Math.hypot(v[0], v[1]) || 1; return [v[0] / l, v[1] / l] }
  if (c.type === 'Distance' || c.type === 'DistanceX' || c.type === 'DistanceY' || c.type === 'Radius' || c.type === 'Diameter') {
    let p1: XY = [0, 0], p2: XY = [0, 0]
    if (c.secondPos !== NONE) { p1 = P(c.first, c.firstPos); p2 = P(c.second, c.secondPos) }
    else if (c.second !== GEO_UNDEF) {
      p1 = SK.getPoint(geo, c.first, c.firstPos) ?? [0, 0]
      let g1 = geo[c.first], g2 = geo[c.second]
      if (SK.isLine(g2) && SK.isCircular(g1) && c.firstPos === NONE) [g1, g2] = [g2, g1]
      else if (SK.isLine(g2)) { const d: XY = [g2.end[0] - g2.start[0], g2.end[1] - g2.start[1]], t = ((p1[0] - g2.start[0]) * d[0] + (p1[1] - g2.start[1]) * d[1]) / (d[0] * d[0] + d[1] * d[1]); p2 = [g2.start[0] + t * d[0], g2.start[1] + t * d[1]] }
      if (SK.isCircular(g2)) {
        const cc = g2 as { center: XY; radius: number }
        if (c.firstPos !== NONE) { const v = n2([p1[0] - cc.center[0], p1[1] - cc.center[1]]); p2 = [cc.center[0] + cc.radius * v[0], cc.center[1] + cc.radius * v[1]] }
        else if (SK.isCircular(g1)) { const a = g1 as { center: XY; radius: number }, v = n2([cc.center[0] - a.center[0], cc.center[1] - a.center[1]]); p1 = [a.center[0] + v[0] * a.radius, a.center[1] + v[1] * a.radius]; p2 = [cc.center[0] - v[0] * cc.radius, cc.center[1] - v[1] * cc.radius] }
        else if (SK.isLine(g1)) { const d: XY = [g1.end[0] - g1.start[0], g1.end[1] - g1.start[1]], t = ((cc.center[0] - g1.start[0]) * d[0] + (cc.center[1] - g1.start[1]) * d[1]) / (d[0] * d[0] + d[1] * d[1]); p1 = [g1.start[0] + t * d[0], g1.start[1] + t * d[1]]; const v = n2([p1[0] - cc.center[0], p1[1] - cc.center[1]]); p2 = [cc.center[0] + v[0] * cc.radius, cc.center[1] + v[1] * cc.radius] }
      }
    } else if (c.firstPos !== NONE) p2 = P(c.first, c.firstPos)
    else {
      const g = geo[c.first]
      if (SK.isLine(g)) { p1 = g.start; p2 = g.end }
      else if (SK.isArc(g) || SK.isCircle(g)) {
        const center = (g as { center: XY }).center, radius = (g as { radius: number }).radius
        p1 = center
        let angle = c.labelPosition
        if (SK.isArc(g) && angle === 10) angle = (g.start_angle + g.end_angle) / 2
        else angle = Math.atan2(to[1] - center[1], to[0] - center[0])
        const u: XY = [Math.cos(angle), Math.sin(angle)]
        if (c.type === 'Diameter') p1 = [center[0] - radius * u[0], center[1] - radius * u[1]]
        p2 = [center[0] + radius * u[0], center[1] + radius * u[1]]
      } else return
    }
    const vec: XY = [to[0] - p2[0], to[1] - p2[1]]
    const dir: XY = c.type === 'DistanceX' ? [p2[0] - p1[0] >= 1.19e-7 ? 1 : -1, 0] : c.type === 'DistanceY' ? [0, p2[1] - p1[1] >= 1.19e-7 ? 1 : -1] : n2([p2[0] - p1[0], p2[1] - p1[1]])
    if (c.type === 'Radius' || c.type === 'Diameter') { c.labelDistance = vec[0] * dir[0] + vec[1] * dir[1]; c.labelPosition = Math.atan2(dir[1], dir[0]) }
    else {
      const normal: XY = [-dir[1], dir[0]]
      c.labelDistance = vec[0] * normal[0] + vec[1] * normal[1]
      const v2: XY = [to[0] - (p1[0] + p2[0]) / 2, to[1] - (p1[1] + p2[1]) / 2]
      c.labelPosition = v2[0] * dir[0] + v2[1] * dir[1]
    }
  } else if (c.type === 'Angle') {
    let p0: XY = [0, 0], factor = 0.5
    if (c.second !== GEO_UNDEF) {
      const L = (g: number) => (g === H_AXIS ? { start: [0, 0] as XY, end: [1, 0] as XY } : g === V_AXIS ? { start: [0, 0] as XY, end: [0, 1] as XY } : geo[g] as { start: XY; end: XY })
      const l1 = L(c.first), l2 = L(c.second)
      if (!l1?.start || !l2?.start) return
      const f1 = c.firstPos === END, f2 = c.secondPos === END
      const p11 = f1 ? l1.end : l1.start, p12 = f1 ? l1.start : l1.end, p21 = f2 ? l2.end : l2.start, p22 = f2 ? l2.start : l2.end
      const d1: XY = [p12[0] - p11[0], p12[1] - p11[1]], d2: XY = [p22[0] - p21[0], p22[1] - p21[1]]
      const det = d1[0] * d2[1] - d1[1] * d2[0]
      if (Math.abs(det) < 1e-12) return
      const t = ((p21[0] - p11[0]) * d2[1] - (p21[1] - p11[1]) * d2[0]) / det
      const inter: XY = [p11[0] + t * d1[0], p11[1] + t * d1[1]]
      const left = (a: XY, b: XY, q: XY) => (b[0] - a[0]) * (q[1] - a[1]) - (b[1] - a[1]) * (q[0] - a[0]) > 0
      let ap3: XY = [inter[0] + d1[0] + d2[0], inter[1] + d1[1] + d2[1]]
      let sign1 = left(p11, p12, ap3), sign2 = left(p21, p22, ap3)
      const sign3 = left(p11, p12, to), sign4 = left(p21, p22, to)
      const reverse = !(sign1 === sign3 && sign2 === sign4) && !(sign1 !== sign3 && sign2 !== sign4)
      if (reverse) { // SketchObject::reverseAngleConstraintToSupplementary
        c.secondPos = (c.secondPos === END ? START : c.secondPos === START ? END : c.secondPos) as PointPos
        if (c.secondPos === NONE) c.secondPos = END
        c.value = Math.PI - c.value
        ap3 = [inter[0] + d1[0] - d2[0], inter[1] + d1[1] - d2[1]]
        sign1 = left(p11, p12, ap3); sign2 = left(p21, p22, ap3)
      }
      if (!(sign1 === sign3 && sign2 === sign4)) { // SketchObject::inverseAngleConstraint
        c.firstPos = (c.firstPos === END ? START : END) as PointPos
        c.secondPos = (c.secondPos === END ? START : END) as PointPos
      }
      p0 = inter
    } else {
      const g = geo[c.first]
      if (SK.isLine(g)) p0 = [(g.start[0] + g.end[0]) / 2, (g.start[1] + g.end[1]) / 2]
      else if (SK.isArc(g)) { const a = (g.start_angle + g.end_angle) / 2; c.labelDistance = factor * ((to[0] - g.center[0]) * Math.cos(a) + (to[1] - g.center[1]) * Math.sin(a)); setConstraint(id, c); return }
      else return
    }
    c.labelDistance = factor * Math.hypot(to[0] - p0[0], to[1] - p0[1])
    void factor
  } else return
  setConstraint(id, c)
}
function commitConstraintDrag(p: XY) {
  const s = session!, d = s.dragConstraints
  if (!d) return
  for (const id of d.ids) moveConstraint(id, p)
  s.command = { name: 'Drag Constraint', before: { geometry: s.geometry, constraints: d.start, external: s.external } }
  commitCommand()
  s.pre = { ...s.pre, constraints: d.ids }
  s.dragConstraints = null
}

// ── box selection (ViewProviderSketch::doBoxSelection) ──────────────────────────────────────────────────────────
function doBoxSelection(a: [number, number], b: [number, number], additive: boolean) {
  const s = session!, sc = screen()
  if (!sc) return
  const x0 = Math.min(a[0], b[0]), x1 = Math.max(a[0], b[0]), y0 = Math.min(a[1], b[1]), y1 = Math.max(a[1], b[1])
  const touch = a[0] > b[0] // right to left: anything the box touches
  const inside = (p: XY) => { const [x, y] = sc.toScreen(p); return x >= x0 && x <= x1 && y >= y0 && y <= y1 }
  const segCross = (p: [number, number], q: [number, number]) => {
    const inBox = (r: [number, number]) => r[0] >= x0 && r[0] <= x1 && r[1] >= y0 && r[1] <= y1
    if (inBox(p) || inBox(q)) return true
    const edges: [[number, number], [number, number]][] = [[[x0, y0], [x1, y0]], [[x1, y0], [x1, y1]], [[x1, y1], [x0, y1]], [[x0, y1], [x0, y0]]]
    const cr = (o: [number, number], u: [number, number], v: [number, number]) => (u[0] - o[0]) * (v[1] - o[1]) - (u[1] - o[1]) * (v[0] - o[0])
    return edges.some(([e1, e2]) => cr(p, q, e1) * cr(p, q, e2) <= 0 && cr(e1, e2, p) * cr(e1, e2, q) <= 0)
  }
  const out: string[] = additive ? [...sel()] : [...sel()]
  let v = -1
  const all = geoAll()
  // getCompleteGeometry's order, as the vertex index has it: the sketch's geometry, then the external geometry
  // from the last one to the first
  const items: [Geo, number][] = [...s.geometry.map((g, i) => [g, i] as [Geo, number]),
    ...s.external.geometry.map((g, k) => [g, SK.REF_EXT - k] as [Geo, number]).reverse()]
  items.forEach(([g, i]) => {
    const vert = (p: XY) => { v++; if (inside(p)) { out.push(SK.vertexName(v)); return true } return false }
    if (g.type === 'Point') { vert(g.at); return }
    if (g.type === 'LineSegment') {
      const in1 = vert(g.start), in2 = vert(g.end)
      if (in1 && in2 && !touch) out.push(SK.edgeName(i))
      else if (touch && segCross(sc.toScreen(g.start), sc.toScreen(g.end))) out.push(SK.edgeName(i))
      return
    }
    const pts = SK.polyline(g, 50)
    const curveIn = () => { if (touch) return pts.some((p) => inside(p)); return pts.every((p) => inside(p)) }
    if (g.type === 'Circle' || g.type === 'Ellipse') { const c = vert(g.center); if ((c || touch) && curveIn()) out.push(SK.edgeName(i)); return }
    const s0 = SK.getPoint(all, i, START)!, e0 = SK.getPoint(all, i, END)!
    const ins = vert(s0), ine = vert(e0)
    if (g.type !== 'BSplineCurve') vert(g.center)
    if ((ins && ine) || touch) { if (curveIn()) out.push(SK.edgeName(i)) }
  })
  if (inside([0, 0])) out.push('RootPoint')
  setSelection(out)
}

// ── keys (ViewProviderSketch::keyPressed, ShortcutListener's Delete) ────────────────────────────────────────────
/** Sketcher's LeaveSketchWithEscape (on; the General page sets it): Esc with nothing going on closes the edit (TaskDlgEditSketch's
 *  escape button). Read as sketchovp.ts's sketcherParam reads it (that module imports this one). */
export const leaveWithEscape = () => saved.get<Record<string, unknown>>('sketcherParams', {})['Mod/Sketcher/LeaveSketchWithEscape'] !== false
export function handleKey(e: KeyboardEvent, down: boolean): boolean {
  const s = session
  if (!s) return false
  const key = e.key
  ctrlHeld = isMac ? e.metaKey : e.ctrlKey
  if (key === 'Escape') {
    if (s.handler) { if (down) s.handler.registerPressedKey(true, 'Escape'); else s.handler.registerPressedKey(false, 'Escape'); changed(); return true }
    if (s.dragConstraints) { if (!down) { s.constraints = s.dragConstraints.start; s.dragConstraints = null; s.mode = 'none'; changed() } return true }
    if (s.drag) { if (!down) { s.drag.drag?.end(); s.geometry = s.drag.start.geometry; s.drag = null; s.mode = 'none'; solve() } return true }
    if (!down) return true
    if (s.selection.length) { clearSelection(); return true }
    if (leaveWithEscape()) { void closeEdit(true); return true }
    return true
  }
  if (s.handler) {
    const used = s.handler.registerPressedKey(down, key.length === 1 ? key.toUpperCase() : key)
    if (used) changed()
    return used
  }
  if (down && (key === 'Delete' || (isMac && key === 'Backspace'))) { deleteSelected(); return true }
  return false
}

/** ViewProviderSketch::onDelete: the selected constraints first, then the points' constraints, then the geometry. */
export function deleteSelected() {
  const s = session
  if (!s || !s.selection.length) return
  openCommand('Delete')
  const cons = [...selectedConstraints()].sort((a, b) => b - a)
  const curves = [...selectedCurves()].filter((g) => g >= 0)
  const externals = [...selectedCurves()].filter(SK.isExternalId)
  const points = [...selectedPoints()].filter((v) => v >= 0).map(geoVertexIndex)
  delConstraints(cons)
  // a point of a curve that goes too: nothing to do; a point on its own (Part::GeomPoint) is geometry; an external
  // point (a projected vertex) is its external geometry
  for (const [g, pos] of points) {
    if (curves.includes(g) || externals.includes(g)) continue
    if (SK.isExternalId(g)) { if (geoAll()[g]?.type === 'Point') externals.push(g); else delConstraintOnPoint(g, pos); continue }
    if (s.geometry[g]?.type === 'Point') curves.push(g)
    else delConstraintOnPoint(g, pos)
  }
  if (curves.length) delGeometries([...new Set(curves)])
  if (externals.length) delExternal(externals) // ViewProviderSketch::onDelete: delExternal on the ExternalEdges
  clearSelection()
  commitCommand()
  solve()
}

// ── entering and leaving edit mode ──────────────────────────────────────────────────────────────────────────────
/** ViewProviderSketch::setEdit + setEditViewer: back up the sketch, show the grid, hide what depends on the sketch
 *  (the part's body: HideDependent), turn the view to the sketch (RestoreCamera keeps the camera for later), switch to
 *  the Sketcher workbench (EditingWorkbench), open the task panel, solve. */
export async function editSketch(ref: SketchRef) {
  if (session) await closeEdit(true)
  solver ??= await loadSolver()
  const placement = ref.placement ?? { base: [0, 0, 0], rotation: [0, 0, 0, 1] }
  const sk = ref.sketch ?? { geometry: [], constraints: [] }
  const geometry = sk.geometry.map((g) => ({ ...g })), constraints = sk.constraints.map(SK.fromCons)
  const external = copyExternal(ref.external ?? noExternal())
  const st = getState(), view = getView()
  const dependents = (st.scene?.bodies ?? []).filter((b) => ref.part && b.part === ref.part && dependsOnSketch(ref.part, ref.name)).map((b) => b.name)
  session = {
    ref, placement, geometry, constraints, external, result: null, message: { state: 'empty', text: 'Empty sketch', link: '', linkText: '' },
    backup: { geometry: geometry.map((g) => ({ ...g })), constraints: constraints.map((c) => ({ ...c })), external: copyExternal(external) }, undo: [], redo: [], selection: [],
    pre: { point: -1, curve: null, cross: null, constraints: [] }, mode: 'none', handler: null, construction: false, edit: emptyEdit(),
    rubber: null, drag: null, dragConstraints: null, hiddenConstraints: new Set(), shownVirtualSpace: false,
    before: { hidden: st.hidden, camera: view?.getCamera() ?? null, workbench: st.workbench }, command: null,
    hits: { icons: [], labels: [], datumLines: [] }, click: { pos: [-16000, -16000], t: 0, cursor: [0, 0] },
    showGrid: saved.get('sketcher.showGrid', true), angleSnap: { on: false, ref: [0, 0], last: 0 }, saving: false,
    listVersion: 0, lastListChange: 'elements',
  }
  setState({ hidden: [...new Set([...st.hidden, ...dependents])], workbench: 'sketcher', selected: [], subSel: [], sketchEditing: { part: ref.part, name: ref.name },
    task: { kind: 'sketch', body: ref.name } })
  showPanel('view3d') // the sketch's 3D view in front (setEditViewer)
  showPanel('tasks')
  iconsLoaded(() => getView()?.redraw())
  view?.setSketchHook({ event: handleEvent, key: handleKey, draw: drawOverlay, popup: wantsPopup })
  const q = placement.rotation, base = new THREE.Vector3(...placement.base)
  const box = sketchBox()
  view?.lookAtSketch(q, base, box)
  publishHistory()
  solve()
}
/** HideDependent (TaskSketcherGeneral, on): ViewProviderSketch::setEdit hides the objects that depend on the sketch
 *  (getInListRecursive). The 3D view draws a Body as its Tip's solid, so the Body hides when its Tip depends on the
 *  sketch: the Tip takes it as its profile, or comes after a feature that does or that is attached to, or projects,
 *  something that does. A sketch after the Tip (a new sketch on a face) leaves the Body shown, to be picked from. */
export function dependsOnSketch(part: string, sketch: string, target?: string): boolean {
  const doc = getState().features[part]
  if (!doc) return true
  target ??= shownSolid(part) ?? undefined
  if (!target) return false
  const names = new Set([sketch])
  const refsOf = (f: Record<string, unknown>): string[] => {
    const out: string[] = []
    if (typeof f.profile === 'string') out.push(f.profile)
    for (const k of ['attachment_support', 'external_geometry', 'up_to_shape', 'up_to_shape2']) for (const r of (Array.isArray(f[k]) ? f[k] as unknown[] : [])) out.push(String(Array.isArray(r) ? r[0] : r))
    for (const k of ['up_to_face', 'up_to_face2']) { const r = f[k]; if (Array.isArray(r)) out.push(String(r[0])); else if (typeof r === 'string') out.push(r) }
    return out
  }
  let solidDepends = false
  for (const f of doc.features) {
    const solid = typeof f.profile === 'string' // a Pad or Pocket: its base is the solid before it (getBaseObject)
    if (refsOf(f).some((r) => names.has(r)) || (solid && solidDepends)) { names.add(f.name); if (solid) solidDepends = true }
    if (f.name === (target ?? doc.tip)) break
  }
  const t = target ?? doc.tip
  return !!t && names.has(t)
}
/** The feature whose solid the 3D view draws for a Body: its Tip, or (a sketch as the Tip leaves the solid before it)
 *  the last solid feature before it, else the BaseFeature. */
export function shownSolid(part: string): string | null {
  const doc = getState().features[part]
  if (!doc) return null
  const upto = doc.tip ? doc.features.findIndex((f) => f.name === doc.tip) : doc.features.length - 1
  for (let i = upto; i >= 0; i--) if (typeof doc.features[i].profile === 'string') return doc.features[i].name
  return doc.base ? 'BaseFeature' : null
}
/** The sketch's bounding box in the world, to fit the view to (viewObjects). */
function sketchBox(): THREE.Box3 | null {
  const s = session
  if (!s || !s.geometry.length) return null
  const m = sketchMatrix(s.placement), box = new THREE.Box3()
  for (const g of s.geometry) for (const p of SK.polyline(g, 16)) box.expandByPoint(new THREE.Vector3(p[0], p[1], 0).applyMatrix4(m))
  return box
}
function drawOverlay(ctx: CanvasRenderingContext2D, vp: Viewport) {
  const s = session
  if (!s) return
  lastScreen = screenOf(vp, s.placement)
  s.hits = drawSketch(ctx, lastScreen, drawState(), lastScreen.center)
  for (const f of overlayDrawn) f()
}
const overlayDrawn = new Set<() => void>()
/** After each drawing of the overlay (the camera may have moved): the on-view parameters' boxes follow their labels. */
export function onOverlayDrawn(f: () => void) { overlayDrawn.add(f); return () => { overlayDrawn.delete(f) } }
/** The 3D view's canvas in the page (client pixels) and its size, for the boxes over it. */
export function viewSize(): { w: number; h: number; left: number; top: number } | null {
  const vp = getView()?.sketchViewport(), c = document.querySelector('canvas.sketch-overlay') as HTMLElement | null
  if (!vp || !c) return null
  const r = c.getBoundingClientRect()
  return { w: vp.w, h: vp.h, left: r.left, top: r.top }
}
/** The cursor over the 3D view (pixels from its top left), where it was last moved. */
export const cursorScreen = () => cursorPx
let cursorPx: [number, number] | null = null
/** View3DInventorViewer::getDimensions: the view's width and height in sketch units. */
export function viewDimensions(): [number, number] | null { const s = screen(); return s ? [(s.visibleHeight * s.w) / s.h, s.visibleHeight] : null }

/** TaskDlgEditSketch::accept (OK, Sketcher_LeaveSketch) and reject (Cancel, Sketcher_CancelSketch): leave the edit,
 *  saving the sketch into its part, or putting it back as it was. */
export async function closeEdit(accept: boolean) {
  const s = session
  if (!s) return
  if (s.handler) deactivateHandler()
  const result = accept ? toSketch(s) : toSketch(s.backup)
  const changedSketch = !same(s.backup, snap())
  const view = getView()
  view?.setSketchHook(null)
  view?.setSketchCursor('')
  session = null
  lastHit = null
  setState({ hidden: s.before.hidden, workbench: s.before.workbench, sketchEditing: null, hints: [] })
  if (getState().task?.kind === 'sketch') closeTask()
  if (s.before.camera) view?.setCamera(s.before.camera) // TempoVis.restore: RestoreCamera
  setEditHistory(null)
  changed()
  publishSketch()
  const ext = accept ? s.external : s.backup.external
  lastClosed = { ...s.ref, placement: s.placement, sketch: result, external: ext }
  const refsChanged = JSON.stringify(s.backup.external.refs) !== JSON.stringify(s.external.refs)
  if (accept && changedSketch) await saveSketch(s.ref.part, s.ref.name, result, refsChanged ? s.external.refs : undefined)
  closed.forEach((f) => f({ ref: s.ref, sketch: result, accepted: accept }))
}
const closed = new Set<(e: { ref: SketchRef; sketch: Sketch; accepted: boolean }) => void>()
/** The tree (step 4) hears when a sketch closes, to show it again. */
export function onSketchClosed(f: (e: { ref: SketchRef; sketch: Sketch; accepted: boolean }) => void) { closed.add(f); return () => { closed.delete(f) } }

/** Saves a sketch into its part module (cad_agent/feature_edit.py `apply`, op "set" on the sketch's geometry and
 *  constraints): POST /api/<slug>/features/<part> {ops}. Without a part, or without the endpoint, the sketch stays as
 *  it is in memory and the Report view says why, as FreeCAD's report does when a recompute fails. */
export async function saveSketch(part: string | null, name: string, sketch: Sketch, externalRefs?: [string, string][]): Promise<boolean> {
  const slug = getState().slug
  pending.set(name, sketch)
  if (!slug || !part) { report('err', `${name}: the sketch is in no part yet, so it was not saved. It is kept in memory until this page closes.`); return false }
  // partdesign.tsx applyOps: one undo step ("Edit Sketch"), the part rebuilt before the edit is kept; it says in the
  // Report view what went wrong, and then the edit stays in memory. ExternalGeometry goes with it when it changed.
  const props: Record<string, unknown> = { geometry: sketch.geometry, constraints: sketch.constraints }
  if (externalRefs) props.external_geometry = externalRefs
  const doc = await applyOps(part, [{ op: 'set', name, props }], { name: 'Edit Sketch' })
  if (!doc) { report('err', `${name}: the sketch was not saved into parts/${part}.py; the edit is kept in memory.`); return false }
  pending.delete(name)
  return true
}
/** The sketch that was last in edit, as it was left: what Sketcher_EditSketch opens again while the tree has no sketches. */
let lastClosed: SketchRef | null = null
export const lastSketch = () => lastClosed
/** Sketches edited here and not saved (no part, no endpoint): what a re-edit starts from. */
const pending = new Map<string, Sketch>()
export const unsavedSketch = (name: string) => pending.get(name) ?? null

// ── for the panel and the commands ───────────────────────────────────────────────────────────────────────────────
export const getMessage = () => session?.message ?? null
export const getResult = () => session?.result ?? null
export const getMode = () => session?.mode ?? 'none'
export function setShowGrid(on: boolean) { const s = session; saved.set('sketcher.showGrid', on); if (s) { s.showGrid = on; changed() } }
export const showGrid = () => session?.showGrid ?? saved.get('sketcher.showGrid', true)
export function setConstraintHidden(i: number, hidden: boolean) { const s = session; if (!s) return; const h = new Set(s.hiddenConstraints); if (hidden) h.add(i); else h.delete(i); s.hiddenConstraints = h; changed() }
export const hiddenConstraints = () => session?.hiddenConstraints ?? new Set<number>()
/** Where the last draw put the constraints' icons and labels (screen pixels), and a pixel in sketch coordinates. */
export const hitRegions = () => session?.hits ?? null
/** The panel and the toolbars redraw (a mode that is no sketch data changed: the constraint creation mode). */
export const notifyChanged = () => changed()
export const screenToSketch = (x: number, y: number) => screen()?.toSketch(x, y) ?? null
/** ViewProviderSketch::getIsShownVirtualSpace / setIsShownVirtualSpace. */
export const isShownVirtualSpace = () => !!session?.shownVirtualSpace
export function setShownVirtualSpace(on: boolean) { const s = session; if (s && s.shownVirtualSpace !== on) { s.shownVirtualSpace = on; changed() } }
/** Sketcher_ViewSketch: look at the sketch again. */
export function viewSketch() {
  const s = session
  if (!s) return
  getView()?.lookAtSketch(s.placement.rotation, new THREE.Vector3(...s.placement.base), sketchBox())
}
/** Preselect from the task panel's lists (TaskSketcherElements/Constraints hovering). */
export function setPreselection(pre: Partial<Pre> | null) {
  const s = session
  if (!s) return
  s.pre = { point: -1, curve: null, cross: null, constraints: [], ...(pre ?? {}) }
  changed()
}
/** The cursor's text: " (x, y)" in the user's units (lengthToDisplayFormat with the system decimals). */
export function positionString(p: XY) { return ` (${lengthString(p[0])}, ${lengthString(p[1])})` }
/** SketcherGui::lengthToDisplayFormat with UseSystemDecimals: the length as the unit system writes it. */
export const lengthString = (v: number) => userString({ value: v, dims: [1, 0, 0, 0, 0, 0, 0, 0] }).text
/** angleToDisplayFormat with UseSystemDecimals: the number in the system's decimals and a degree sign. */
export const angleString = (deg: number) => userString({ value: deg, dims: [0, 0, 0, 0, 0, 0, 0, 1] }).text.replace(/\s*°$/, '') + '°'

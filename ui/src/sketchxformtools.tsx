// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Sketcher/Gui/CommandSketcherTools.cpp: 2014 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/SketchRectangularArrayDialog.cpp: 2015 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/Utils.cpp: 2021 Abdullah Tahiri
//   No copyright line in the file: src/Mod/Sketcher/Gui/SketchRectangularArrayDialog.ui
// The Sketcher's transform commands in edit mode: Sketcher_Copy, Sketcher_Clone and Sketcher_Move (SketcherCopy: the
// selected edges and points, the last selected point or the last edge's start or centre as the reference; then
// DrawSketchHandlerCopy: a rubber line from the reference to the cursor with its length and angle, the click runs
// sketch.addCopy / addMove), Sketcher_RectangularArray (its dialog, SketchRectangularArrayDialog, then the same
// handler with auto-constraints at the end, running sketch.addRectangularArray) and Sketcher_RemoveAxesAlignment.
// The SketchObject operations they run are sketchxform.ts.
import { useState, useSyncExternalStore } from 'react'
import { createPortal } from 'react-dom'
import type { XY } from './solver'
import * as SK from './sketch'
import { type PointPos, NONE, START, MID, GEO_UNDEF, H_AXIS, V_AXIS, RT_PNT, REF_EXT } from './sketch'
import * as S from './sketcher'
import * as XF from './sketchxform'
import { DrawSketchHandler, type AutoConstraint } from './sketchtools'
import { report, saved } from './store'
import { QSpin } from './qtform'

/** "%f": a number as the commands write it into their Python call (six decimals). */
const f6 = (v: number) => Number(v.toFixed(6))
const warn = (title: string, text: string) => report('warn', `${title}: ${text}`)
const doc = (): XF.Doc => ({ geometry: S.getGeometry().map((g) => ({ ...g })), constraints: S.getConstraints().map((c) => ({ ...c })) })
function apply(d: XF.Doc) { S.setGeometry(d.geometry); S.setConstraints(d.constraints) }
const geometryAt = (g: number) => S.getGeometry()[g]
const isVertexName = (n: string) => n.length > 6 && n.startsWith('Vertex')
const isEdgeName = (n: string) => n.length > 4 && n.startsWith('Edge')
const edgeIdOf = (n: string) => Number(n.slice(4)) - 1
const vertexIdOf = (n: string) => Number(n.slice(6)) - 1

/** SketcherGui::getIdsFromName. */
function idsFromName(name: string): [number, PointPos] {
  if (isEdgeName(name)) return [edgeIdOf(name), NONE]
  if (name === 'RootPoint') return [RT_PNT, START]
  if (name === 'H_Axis') return [H_AXIS, NONE]
  if (name === 'V_Axis') return [V_AXIS, NONE]
  if (name.length > 12 && name.startsWith('ExternalEdge')) return [REF_EXT + 1 - Number(name.slice(12)), NONE]
  if (isVertexName(name)) return S.geoVertexIndex(vertexIdOf(name))
  return [GEO_UNDEF, NONE]
}
/** SketcherGui::isCommandActive: in edit with no tool or a tool running. */
export function isCommandActive(): boolean {
  if (!S.isEditing()) return false
  const mode = S.getMode()
  return mode === 'none' || mode === 'useHandler'
}
/** SketcherGui::isCommandNeedingGeometryActive: isCommandActive, and some geometry selected. */
export function isCommandNeedingGeometryActive(): boolean {
  return isCommandActive() && S.getSelection().some((n) => idsFromName(n)[0] !== GEO_UNDEF)
}

type CopySelection = { list: number[]; lastGeoId: number; lastPos: PointPos }
/** The selection as SketcherCopy::activate and CmdSketcherRectangularArray::activated read it: the edges and the points
 *  to copy, in the order they were selected, and the reference point (the last selected vertex if it is not a point
 *  of its own, else the last edge's start, or its centre for a circle or an ellipse). The selection is cleared. */
function copySelection(): CopySelection | null {
  const names = S.getSelection()
  if (!names.length) { warn('Wrong selection', 'Select elements from a single sketch.'); return null }
  S.clearSelection()
  let lastGeoId = 0, lastPos: PointPos = NONE, lastGeo: SK.Geo | undefined
  const list: number[] = []
  for (const n of names) {
    if (isEdgeName(n)) {
      lastGeoId = edgeIdOf(n); lastPos = NONE; lastGeo = geometryAt(lastGeoId)
      if (lastGeoId >= 0) list.push(lastGeoId)
    } else if (isVertexName(n)) {
      const [g] = S.geoVertexIndex(vertexIdOf(n))
      if (geometryAt(g)?.type === 'Point') { lastGeoId = g; lastPos = START; if (g >= 0) list.push(g) }
    }
  }
  const last = names[names.length - 1]
  if (isVertexName(last)) {
    const [g, pos] = S.geoVertexIndex(vertexIdOf(last))
    if (geometryAt(g)?.type !== 'Point') { lastGeoId = g; lastPos = pos }
  }
  if (!list.length) { warn('Wrong selection', 'A copy requires at least one selected non-external geometric element'); return null }
  if (lastPos === NONE) lastPos = lastGeo?.type === 'Circle' || lastGeo?.type === 'Ellipse' ? MID : START
  return { list, lastGeoId, lastPos }
}

export type CopyOp = 'copy' | 'clone' | 'move'
type ArrayParams = { clone: boolean; rows: number; cols: number; constraintSeparation: boolean; equalVerticalHorizontalSpacing: boolean }

/** DrawSketchHandlerCopy and DrawSketchHandlerRectangularArray: a line from the reference point to the cursor, its
 *  length and angle at the cursor (Ctrl: 5° steps); the click makes the copies at that displacement. */
export class CopyHandler extends DrawSketchHandler {
  readonly toolName = 'DSH_Copy'
  private mode: 'first' | 'end' = 'first'
  private editCurve: XY[] = [[0, 0], [0, 0]]
  private sugConstr1: AutoConstraint[] = []
  constructor(private readonly sel: CopySelection, private readonly op: CopyOp | 'array', private readonly array?: ArrayParams) { super() }
  crosshair() { return this.op === 'array' ? 'Sketcher_Pointer_Create_RectangularArray' : 'Sketcher_Pointer_Create_Copy' }
  activated() {
    const o = S.getPoint(this.sel.lastGeoId, this.sel.lastPos) ?? [0, 0]
    this.editCurve = [o, o]
    // SnapMode::Snap5Degree with Ctrl: the angle in 5° steps about the reference, the length kept (SnapManager's
    // angle snapping does the same)
    S.setAngleSnapping(true, o)
  }
  deactivated() { super.deactivated(); S.setAngleSnapping(false) }
  mouseMove(p: XY) {
    if (this.mode !== 'first') return
    const d: XY = [p[0] - this.editCurve[0][0], p[1] - this.editCurve[0][1]]
    const length = Math.fround(Math.hypot(d[0], d[1])), angle = Math.fround(Math.atan2(d[1], d[0]))
    this.editCurve = [this.editCurve[0], p]
    S.setEdit({ positionText: { at: p, text: ` (${S.lengthString(length)}, ${S.angleString((angle * 180) / Math.PI)})` }, curves: [this.editCurve] })
    if (this.op === 'array') { this.seekAndRender(this.sugConstr1, p, [0, 0]); return }
    S.applyCursor()
  }
  pressButton(_p: XY) {
    if (this.mode === 'first') { S.setEdit({ curves: [this.editCurve] }); this.mode = 'end' }
    return true
  }
  releaseButton(_p: XY) {
    if (this.mode !== 'end') return true
    const v: XY = [f6(this.editCurve[1][0] - this.editCurve[0][0]), f6(this.editCurve[1][1] - this.editCurve[0][1])]
    S.setEdit({ positionText: null })
    const { list } = this.sel
    if (this.op === 'array') {
      const a = this.array!
      S.openCommand('Create copy of geometry')
      try {
        // addRectangularArray(geoIds, vector, clone, Cols, Rows, constraintSeparation, 1.0 or 0.5)
        const d = doc()
        XF.addRectangularArray(d, list, v, a.clone, a.cols, a.rows, a.constraintSeparation, a.equalVerticalHorizontalSpacing ? 1.0 : 0.5)
        apply(d)
        S.commitCommand()
      } catch (e) { report('err', `Error: ${e instanceof Error ? e.message : String(e)}`); S.abortCommand() }
      // the auto-constraints for the destination copy
      if (this.sugConstr1.length) { this.createAutoConstraintsDirect(this.sugConstr1, this.sel.lastGeoId + list.length, this.sel.lastPos); this.sugConstr1 = [] }
    } else {
      S.openCommand('Copy/clone/move geometry')
      try {
        const d = doc()
        if (this.op === 'move') XF.addMove(d, list, v)
        else XF.addCopy(d, list, v, false, this.op === 'clone')
        apply(d)
        S.commitCommand()
      } catch (e) { report('err', `Error: ${e instanceof Error ? e.message : String(e)}`); S.abortCommand() }
    }
    // tryAutoRecomputeIfNotSolve
    S.solve()
    S.setEdit({ curves: [] })
    S.purgeHandler()
    return true
  }
}

/** SketcherCopy::activate(op): Sketcher_Copy, Sketcher_Clone, Sketcher_Move. */
export function copyCommand(op: CopyOp) {
  const sel = copySelection()
  if (sel) S.activateHandler(new CopyHandler(sel, op))
}

// ── Sketcher_RectangularArray (SketchRectangularArrayDialog) ─────────────────────────────────────────────────────
const PREF = 'Mod/Sketcher/'
type ArrayDlg = { id: number; done: (p: ArrayParams | null) => void } | null
let arrayDlg: ArrayDlg = null, arrayDlgs = 0
const arraySubs = new Set<() => void>()
const setArrayDlg = (d: ArrayDlg) => { arrayDlg = d; arraySubs.forEach((f) => f()) }
/** SketchRectangularArrayDialog::exec: the values (each kept in its preference, onRestore / onSave), or null. */
const askArray = () => new Promise<ArrayParams | null>((done) => setArrayDlg({ id: ++arrayDlgs, done }))
/** CmdSketcherRectangularArray::activated. */
export async function rectangularArrayCommand() {
  const sel = copySelection()
  if (!sel) return
  const p = await askArray()
  if (p && S.isEditing()) S.activateHandler(new CopyHandler(sel, 'array', p))
}
/** SketchRectangularArrayDialog.ui: Columns and Rows, Equal vertical/horizontal spacing, Constrain inter-element
 *  separation, Clone; OK and Cancel. */
export function ArrayDialog() {
  const d = useSyncExternalStore((f) => { arraySubs.add(f); return () => { arraySubs.delete(f) } }, () => arrayDlg)
  return d ? <ArrayDialogBody key={d.id} d={d} /> : null
}
function ArrayDialogBody({ d }: { d: NonNullable<ArrayDlg> }) {
  const [cols, setCols] = useState(() => Math.max(2, saved.get(PREF + 'DefaultArrayColumnNumber', 2)))
  const [rows, setRows] = useState(() => Math.max(1, saved.get(PREF + 'DefaultArrayRowNumber', 1)))
  const [equal, setEqual] = useState(() => saved.get(PREF + 'DefaultEqualVerticalHorizontalSpacing', false))
  const [separation, setSeparation] = useState(() => saved.get(PREF + 'DefaultConstraintArrayElements', true))
  const [clone, setClone] = useState(() => saved.get(PREF + 'CloneOnCopy', false))
  const finish = (ok: boolean) => {
    setArrayDlg(null)
    if (!ok) { d.done(null); return }
    saved.set(PREF + 'DefaultArrayRowNumber', rows); saved.set(PREF + 'DefaultArrayColumnNumber', cols)
    saved.set(PREF + 'DefaultConstraintArrayElements', separation); saved.set(PREF + 'DefaultEqualVerticalHorizontalSpacing', equal); saved.set(PREF + 'CloneOnCopy', clone)
    d.done({ clone, rows, cols, constraintSeparation: separation, equalVerticalHorizontalSpacing: equal })
  }
  const spin = (name: string, label: string, tip: string, value: number, min: number, set: (v: number) => void) => (
    <div className="hbox fill"><span>{label}</span>
      <QSpin data-qf={name} title={tip} value={value} min={min} max={99} step={1} dec={0} suffix="" prefix="" special="" left={false} off={false} onSet={set} /></div>)
  const check = (name: string, label: string, tip: string, value: boolean, set: (v: boolean) => void) => (
    <label className="tcheck" title={tip}><input type="checkbox" data-qf={name} checked={value} onChange={(e) => set(e.target.checked)} /> {label}</label>)
  return createPortal(
    <div className="msgbox-back" onKeyDown={(e) => { e.stopPropagation(); if (e.key === 'Escape') finish(false); if (e.key === 'Enter') finish(true) }}>
      <div className="msgbox datum-dlg" role="dialog" aria-label="Create Array">
        <div className="msgbox-title">Create Array</div>
        <div className="datum-body">
          {spin('ColsQuantitySpinBox', 'Columns', 'Number of columns of the linear array', cols, 2, setCols)}
          {spin('RowsQuantitySpinBox', 'Rows', 'Number of rows of the linear array', rows, 1, setRows)}
          {check('EqualVerticalHorizontalSpacingCheckBox', 'Equal vertical/horizontal spacing', 'Makes the inter-row and inter-col spacing the same if clicked', equal, setEqual)}
          {check('ConstraintSeparationCheckBox', 'Constrain inter-element separation', 'Constrains each element in the array with respect to the others using construction lines', separation, setSeparation)}
          {check('CloneCheckBox', 'Clone', 'Substitutes dimensional constraints by geometric constraints\nin the copies, so that a change in the original element is reflected on copies', clone, setClone)}
        </div>
        <div className="msgbox-buttons" style={{ justifyContent: 'center' }}>
          <button className="qbtn default" onClick={() => finish(true)}>OK</button>
          <button className="qbtn" onClick={() => finish(false)}>Cancel</button>
        </div>
      </div>
    </div>, document.body)
}

// ── Sketcher_CopyClipboard, Sketcher_Cut, Sketcher_Paste ─────────────────────────────────────────────────────────
/** SketcherGui::getListOfSelectedGeoIds(forceInternalSelection): the selected edges (external ones too) and points of
 *  their own, then the internal geometry of a selected conic or B-spline. */
function selectedGeoIds(): number[] {
  const out: number[] = []
  for (const n of S.getSelection()) {
    if (isEdgeName(n)) out.push(edgeIdOf(n))
    else if (n.length > 12 && n.startsWith('ExternalEdge')) out.push(REF_EXT + 1 - Number(n.slice(12)))
    else if (isVertexName(n)) { const [g] = S.geoVertexIndex(vertexIdOf(n)); if (geometryAt(g)?.type === 'Point' && g >= 0) out.push(g) }
  }
  const cs = S.getConstraints()
  for (const g of [...out]) {
    const t = geometryAt(g)?.type
    if (t === 'Ellipse' || t === 'ArcOfEllipse' || t === 'ArcOfHyperbola' || t === 'ArcOfParabola' || t === 'BSplineCurve')
      for (const c of cs) if (c.type === 'InternalAlignment' && c.second === g && !out.includes(c.first)) out.push(c.first)
  }
  if (!out.length) report('err', 'Invalid selection: Selection has no valid geometries.')
  return out
}
const e8 = (v: number) => v.toFixed(8)
const v3 = (p: XY) => `App.Vector(${e8(p[0])}, ${e8(p[1])}, ${e8(0)})`
/** PythonConverter::process(geometry): the Part constructor FreeCAD writes for it ("%.8f"). */
function geometryPython(g: SK.Geo): string {
  switch (g.type) {
    case 'LineSegment': return `Part.LineSegment(${v3(g.start)},${v3(g.end)})`
    case 'ArcOfCircle': return `Part.ArcOfCircle(Part.Circle(${v3(g.center)}, App.Vector(${e8(0)}, ${e8(0)}, ${e8(1)}), ${e8(g.radius)}), ${e8(g.start_angle)}, ${e8(g.end_angle)})`
    case 'Point': return `Part.Point(${v3(g.at)})`
    case 'Circle': return `Part.Circle(${v3(g.center)}, App.Vector(${e8(0)}, ${e8(0)}, ${e8(1)}), ${e8(g.radius)})`
    case 'Ellipse': case 'ArcOfEllipse': case 'ArcOfHyperbola': {
      const ax = g.x_axis, l = Math.hypot(ax[0], ax[1]) || 1, X: XY = [ax[0] / l, ax[1] / l], Y: XY = [-X[1], X[0]]
      const maj: XY = [g.center[0] + X[0] * g.major_radius, g.center[1] + X[1] * g.major_radius]
      const min: XY = [g.center[0] + Y[0] * g.minor_radius, g.center[1] + Y[1] * g.minor_radius]
      if (g.type === 'Ellipse') return `Part.Ellipse(${v3(maj)}, ${v3(min)}, ${v3(g.center)})`
      if (g.type === 'ArcOfEllipse') return `Part.ArcOfEllipse(Part.Ellipse(${v3(maj)}, ${v3(min)}, ${v3(g.center)}), ${e8(g.start_angle)}, ${e8(g.end_angle)})`
      return `Part.ArcOfHyperbola(Part.Hyperbola(${v3(maj)}, ${v3(min)}, ${v3(g.center)}), ${e8(g.start_angle)}, ${e8(g.end_angle)})`
    }
    case 'ArcOfParabola': {
      const ax = g.x_axis, l = Math.hypot(ax[0], ax[1]) || 1
      const focus: XY = [g.center[0] + (ax[0] / l) * g.focal, g.center[1] + (ax[1] / l) * g.focal]
      return `Part.ArcOfParabola(Part.Parabola(${v3(focus)}, ${v3(g.center)}, App.Vector(0, 0, 1)), ${e8(g.start_angle)}, ${e8(g.end_angle)})`
    }
    case 'BSplineCurve': {
      const list = (a: string[]) => `[${a.join(', ')}]`
      const weights = g.weights ?? g.poles.map(() => 1)
      return `Part.BSplineCurve(${list(g.poles.map((p) => `App.Vector(${e8(p[0])}, ${e8(p[1])})`))}, ${list(g.mults.map(e8))}, ${list(g.knots.map(e8))}, ${g.periodic ? 'True' : 'False'}, ${g.degree}, ${list(weights.map(e8))}, False)`
    }
  }
}
/** PythonConverter::process(constraint, AddLastGeoIdToGeoIds): Sketcher.Constraint(...) with "lastGeoId + n" for the
 *  copied geometry, the value as std::to_string writes it ("%f"). */
function constraintPython(c: SK.Constraint): string {
  const id = (g: number) => (g >= 0 ? `lastGeoId + ${g}` : String(g))
  const i1 = id(c.first), i2 = id(c.second), i3 = id(c.third), ip1 = `${i1}, ${c.firstPos}`, ip2 = `${i2}, ${c.secondPos}`
  const val = c.value.toFixed(6)
  const secondUndef = c.second === GEO_UNDEF, thirdUndef = c.third === GEO_UNDEF, e1 = c.firstPos === NONE, e2 = c.secondPos === NONE, e3 = c.thirdPos === NONE
  let r: string
  switch (c.type) {
    case 'Coincident': r = `Coincident', ${ip1}, ${ip2}`; break
    case 'Horizontal': case 'Vertical': r = secondUndef ? `${c.type}', ${i1}` : `${c.type}', ${ip1}, ${ip2}`; break
    case 'Block': r = `Block', ${i1}`; break
    case 'Tangent': case 'Perpendicular': r = e1 ? `${c.type}', ${i1}, ${i2}` : e2 ? `${c.type}', ${ip1}, ${i2}` : `${c.type}', ${ip1}, ${ip2}`; break
    case 'Parallel': case 'Equal': r = `${c.type}', ${i1}, ${i2}`; break
    case 'Distance': r = secondUndef ? `Distance', ${i1}, ${val}` : e1 ? `Distance', ${i1}, ${i2}, ${val}` : e2 ? `Distance', ${ip1}, ${i2}, ${val}` : `Distance', ${ip1}, ${ip2}, ${val}`; break
    case 'Angle': r = secondUndef ? `Angle', ${i1}, ${val}` : thirdUndef ? (e2 ? `Angle', ${i1}, ${i2}, ${val}` : `Angle', ${ip1}, ${ip2}, ${val}`) : `AngleViaPoint', ${i1}, ${i2}, ${i3}, ${c.thirdPos}, ${val}`; break
    case 'DistanceX': case 'DistanceY': r = e1 && secondUndef ? `${c.type}', ${i1}, ${val}` : e2 ? `${c.type}', ${ip1}, ${val}` : `${c.type}', ${ip1}, ${ip2}, ${val}`; break
    case 'Radius': case 'Diameter': case 'Weight': r = `${c.type}', ${i1}, ${val}`; break
    case 'PointOnObject': r = `PointOnObject', ${ip1}, ${i2}`; break
    case 'Symmetric': r = e3 ? `Symmetric', ${ip1}, ${ip2}, ${i3}` : `Symmetric', ${ip1}, ${ip2}, ${i3}, ${c.thirdPos}`; break
    case 'SnellsLaw': r = `SnellsLaw', ${ip1}, ${ip2}, ${i3}, ${val}`; break
    case 'InternalAlignment': {
      const a = c.alignment!
      if (['EllipseMajorDiameter', 'EllipseMinorDiameter', 'HyperbolaMajor', 'HyperbolaMinor', 'ParabolaFocalAxis'].includes(a)) r = `InternalAlignment:${a}', ${i1}, ${i2}`
      else if (a === 'BSplineControlPoint') r = `InternalAlignment:${a}', ${ip1}, ${i2}, ${c.alignmentIndex ?? -1}`
      else if (a === 'BSplineKnotPoint') r = `InternalAlignment:${a}', ${i1}, 1, ${i2}, ${c.alignmentIndex ?? -1}`
      else r = `InternalAlignment:${a}', ${ip1}, ${i2}`
      break
    }
    default: throw new Error('PythonConverter: Constraint Type not supported')
  }
  if (!c.active || !c.driving) r += (c.active ? ', True' : ', False') + (SK.isDimensional(c) ? (c.driving ? ', True' : ', False') : '')
  return `Sketcher.Constraint('${r})`
}
/** PythonConverter::convert(doc, geometries, OmitInternalGeometry): runs of construction and normal geometry. */
function geometriesPython(doc: string, geos: SK.Geo[]): string {
  if (!geos.length) return ''
  let command = 'lastGeoId = len(ActiveSketch.Geometry)\n', list = '', n = 0, construction = !!geos[0].construction
  const flush = () => {
    if (!n) return
    command += '\n' + (construction ? `constrGeoList = []\n${list}${doc}.addGeometry(constrGeoList,True)\ndel constrGeoList\n` : `geoList = []\n${list}${doc}.addGeometry(geoList,False)\ndel geoList\n`)
  }
  for (const g of geos) {
    if (!!g.construction !== construction) { flush(); list = ''; n = 0; construction = !!g.construction }
    list += `${construction ? 'constrGeoList' : 'geoList'}.append(${geometryPython(g)})\n`
    n++
  }
  flush()
  return command
}
function constraintsPython(doc: string, cs: SK.Constraint[]): string {
  if (cs.length === 1) return `${doc}.addConstraint(${constraintPython(cs[0])})\n\n`
  let list = 'constraintList = []'
  for (const c of cs) list += `\nconstraintList.append(${constraintPython(c)})`
  return cs.length ? `${list}\n${doc}.addConstraint(constraintList)\ndel constraintList\n` : list
}
let clipboardText = ''
/** copySelectionToClipboard: the selected geometry (sorted, without repeats) and the constraints among it (or with the
 *  axes and the root) as FreeCAD's Python, on the clipboard. */
function copySelectionToClipboard(): boolean {
  const ids = [...new Set(selectedGeoIds())].sort((a, b) => a - b)
  if (!ids.length) return false
  const geos = ids.map((g) => geometryAt(g)!)
  const index = new Map(ids.map((g, j) => [g, j]))
  const ok = (g: number) => ids.includes(g) || g === GEO_UNDEF || g === RT_PNT || g === V_AXIS || g === H_AXIS
  const cons = S.getConstraints().filter((c) => ok(c.first) && ok(c.second) && ok(c.third))
    .map((c) => ({ ...c, first: index.get(c.first) ?? c.first, second: index.get(c.second) ?? c.second, third: index.get(c.third) ?? c.third }))
  const ref = S.getSession()?.ref
  const objectCmd = `App.getDocument('${ref?.part ?? 'Unnamed'}').getObject('${ref?.name ?? 'Sketch'}')`
  let text = `# Copied from sketcher. From:\n#objectStr = ${objectCmd}\n${geometriesPython('objectStr', geos)}\n`
  try { text += constraintsPython('objectStr', cons) } catch (e) { report('err', String(e instanceof Error ? e.message : e)); return false }
  clipboardText = text
  void navigator.clipboard?.writeText(text).catch(() => {})
  return true
}
export function copyClipboardCommand() { copySelectionToClipboard() }
export function cutCommand() {
  if (!copySelectionToClipboard()) return
  // "Cut in Sketcher": ViewProviderSketch::deleteSelected
  S.deleteSelected()
}
// ── pasting: the Python copySelectionToClipboard writes, read back ──
const NUM = String.raw`-?\d+(?:\.\d+)?(?:e[-+]?\d+)?`
const vec = (s: string): XY => { const m = s.match(new RegExp(`App\\.Vector\\((${NUM}), (${NUM})`)); return [Number(m![1]), Number(m![2])] }
const nums = (s: string) => [...s.matchAll(new RegExp(NUM, 'g'))].map((m) => Number(m[0]))
function parseGeometry(src: string, construction: boolean): SK.Geo | null {
  const c = construction ? { construction: true } : {}
  const vs = [...src.matchAll(/App\.Vector\(([^)]*)\)/g)].map((m) => nums(m[1]) as number[])
  const tail = nums(src.replace(/App\.Vector\([^)]*\)/g, ''))
  if (src.startsWith('Part.LineSegment(')) return { type: 'LineSegment', start: [vs[0][0], vs[0][1]], end: [vs[1][0], vs[1][1]], ...c }
  if (src.startsWith('Part.Point(')) return { type: 'Point', at: [vs[0][0], vs[0][1]], ...c }
  if (src.startsWith('Part.Circle(')) return { type: 'Circle', center: [vs[0][0], vs[0][1]], radius: tail[0], ...c }
  if (src.startsWith('Part.ArcOfCircle(')) return { type: 'ArcOfCircle', center: [vs[0][0], vs[0][1]], radius: tail[0], start_angle: tail[1], end_angle: tail[2], ...c }
  const conic = (): { center: XY; major_radius: number; minor_radius: number; x_axis: XY } => {
    const [maj, min, ctr] = vs, center: XY = [ctr[0], ctr[1]]
    const A = Math.hypot(maj[0] - ctr[0], maj[1] - ctr[1]), B = Math.hypot(min[0] - ctr[0], min[1] - ctr[1])
    return { center, major_radius: A, minor_radius: B, x_axis: [(maj[0] - ctr[0]) / A, (maj[1] - ctr[1]) / A] }
  }
  if (src.startsWith('Part.Ellipse(')) return { type: 'Ellipse', ...conic(), ...c }
  if (src.startsWith('Part.ArcOfEllipse(')) return { type: 'ArcOfEllipse', ...conic(), start_angle: tail[0], end_angle: tail[1], ...c }
  if (src.startsWith('Part.ArcOfHyperbola(')) return { type: 'ArcOfHyperbola', ...conic(), start_angle: tail[0], end_angle: tail[1], ...c }
  if (src.startsWith('Part.ArcOfParabola(')) {
    const [f, v] = vs, focal = Math.hypot(f[0] - v[0], f[1] - v[1])
    return { type: 'ArcOfParabola', center: [v[0], v[1]], focal, x_axis: [(f[0] - v[0]) / focal, (f[1] - v[1]) / focal], start_angle: tail[0], end_angle: tail[1], ...c }
  }
  if (src.startsWith('Part.BSplineCurve(')) {
    const lists = [...src.matchAll(/\[([^\]]*)\]/g)].map((m) => m[1])
    const poles = [...lists[0].matchAll(/App\.Vector\(([^)]*)\)/g)].map((m) => nums(m[1]) as number[]).map((p): XY => [p[0], p[1]])
    const after = src.slice(src.indexOf(lists[2]) + lists[2].length + 1)
    const m = after.match(/^,\s*(True|False),\s*(\d+)/)
    return { type: 'BSplineCurve', poles, mults: nums(lists[1]).map(Math.round), knots: nums(lists[2]), periodic: m?.[1] === 'True', degree: Number(m?.[2] ?? 3), weights: nums(lists[3]), ...c }
  }
  return null
}
/** Sketcher.Constraint(...) as ConstraintPy::PyInit reads the forms PythonConverter writes. */
function parseConstraint(src: string, lastGeoId: number): SK.Constraint | null {
  const m = src.match(/^Sketcher\.Constraint\('([^']+)',\s*(.*)\)$/)
  if (!m) return null
  let type = m[1]
  const args = m[2].split(',').map((a) => a.trim())
  const flags: boolean[] = []
  while (args.length && (args[args.length - 1] === 'True' || args[args.length - 1] === 'False')) flags.unshift(args.pop() === 'True')
  const vals = args.map((a) => { const k = a.match(/^lastGeoId \+ (\d+)$/); return k ? lastGeoId + Number(k[1]) : Number(a) })
  let c: SK.Constraint
  if (type.startsWith('InternalAlignment:')) c = SK.fromCons({ type, args: vals })
  else {
    if (type === 'AngleViaPoint') type = 'Angle'
    const dims = ['Distance', 'DistanceX', 'DistanceY', 'Radius', 'Diameter', 'Angle', 'Weight', 'SnellsLaw']
    const dim = dims.includes(type)
    if (m[1] === 'AngleViaPoint') c = SK.constraint('Angle', vals[0], NONE, vals[1], NONE, vals[2], vals[3] as PointPos, vals[4])
    else c = SK.fromCons(dim ? { type, args: vals.slice(0, -1), value: vals[vals.length - 1] } : { type, args: vals })
  }
  if (flags.length) { c.active = flags[0]; if (flags.length > 1) c.driving = flags[1] }
  return c
}
/** CmdSketcherPaste: the clipboard's Python run on the sketch (when it is a Sketcher copy), then a solve. */
export async function pasteCommand() {
  let data = ''
  try { data = (await navigator.clipboard?.readText()) ?? '' } catch { data = '' }
  if (!data.includes('# Copied from sketcher.')) data = clipboardText
  if (!data.includes('# Copied from sketcher.') || !S.isEditing()) return
  const lastGeoId = S.getGeometry().length
  const geos: SK.Geo[] = [], cons: SK.Constraint[] = []
  for (const line of data.split('\n')) {
    const g = line.match(/^(constrGeoList|geoList)\.append\((.*)\)$/)
    if (g) { const x = parseGeometry(g[2], g[1] === 'constrGeoList'); if (x) geos.push(x); continue }
    const c = line.match(/^constraintList\.append\((.*)\)$/) ?? line.match(/^objectStr\.addConstraint\((Sketcher\.Constraint\(.*\))\)$/)
    if (c) { const x = parseConstraint(c[1], lastGeoId); if (x) cons.push(x) }
  }
  S.openCommand('Paste in Sketcher')
  if (geos.length) S.addGeometry(geos)
  if (cons.length) S.addConstraint(cons)
  S.solve()
  S.commitCommand()
}

// ── Sketcher_RemoveAxesAlignment ─────────────────────────────────────────────────────────────────────────────────
/** CmdSketcherRemoveAxesAlignment::activated. */
export function removeAxesAlignmentCommand() {
  const names = S.getSelection()
  if (!names.length) { warn('Wrong selection', 'Select elements from a single sketch.'); return }
  S.clearSelection()
  const list: number[] = []
  for (const n of names) {
    if (isEdgeName(n)) { const g = edgeIdOf(n); if (g >= 0) list.push(g) }
    else if (isVertexName(n)) { const [g] = S.geoVertexIndex(vertexIdOf(n)); if (geometryAt(g)?.type === 'Point' && g >= 0) list.push(g) }
  }
  if (!list.length) { warn('Wrong selection', 'Removal of axes alignment requires at least one selected non-external geometric element'); return }
  S.openCommand('Remove Axes Alignment')
  try {
    const d = doc()
    XF.removeAxesAlignment(d, list)
    apply(d)
    S.commitCommand()
  } catch (e) { report('err', `Error: ${e instanceof Error ? e.message : String(e)}`); S.abortCommand() }
  S.solve()
}

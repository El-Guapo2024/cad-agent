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
/** SketcherGui::isCommandNeedingGeometryActive: in edit with no tool or a tool running, and some geometry selected. */
export function isCommandNeedingGeometryActive(): boolean {
  if (!S.isEditing()) return false
  const mode = S.getMode()
  if (mode !== 'none' && mode !== 'useHandler') return false
  return S.getSelection().some((n) => idsFromName(n)[0] !== GEO_UNDEF)
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

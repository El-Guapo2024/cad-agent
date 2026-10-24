// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Sketcher/Gui/CommandSketcherBSpline.cpp: 2017 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/CommandSketcherOverlay.cpp: 2017 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/DrawSketchHandlerBSpline.h: 2022 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/Utils.cpp: 2021 Abdullah Tahiri
// The Sketcher's curve commands: the B-Spline Tools toolbar (Geometry to B-Spline, Increase/Decrease B-Spline Degree,
// Increase/Decrease Knot Multiplicity, Insert Knot, Join Curves), the B-spline information layer's toggles, and
// B-spline by knots (Sketcher_CreateBSplineByInterpolation and its periodic one). Each does what FreeCAD's command
// does, through the SketchObject operations of sketchbspline.ts; the numbers of the new curves are OCCT's, from the
// sketch kernel (sketchkernel.ts), so a command may finish a moment after the click.
import type { Geo, XY } from './solver'
import * as SK from './sketch'
import { type PointPos, NONE, START, END, MID, GEO_UNDEF } from './sketch'
import * as S from './sketcher'
import * as BS from './sketchbspline'
import * as OPS from './sketchops'
import * as CV from './sketchcurves'
import { idOf } from './sketchcons'
import { DefaultHandler, DrawSketchHandler, type AutoConstraint } from './sketchtools'
import { BSplineHandler, setKnotsSwitch } from './sketchgeo'
import { runOp, withKernel, tryKernel, KernelError, type Kernel } from './sketchkernel'
import './sketchkernelapi'
import { LAYERS, toggleLayer, onLayerToggled, type LayerCommand } from './sketchbsplineinfo'
import { report } from './store'

const LMB = 'LMB', RMB = 'RMB'
const CONFUSION = 1e-7
const warn = (title: string, text: string) => report('warn', `${title}: ${text}`)
const error = (title: string, text: string) => report('err', `${title}: ${text}`)
const msg = (e: unknown) => (e instanceof Error ? e.message : String(e))
/** The sketch in edit as a SketchObject's lists (its own geometry; the external at its GeoIds through ext). */
const snapshot = (): BS.Doc => ({ geometry: S.getGeometry().map((g) => ({ ...g })), constraints: S.getConstraints().map((c) => ({ ...c })) })
const copy = (d: BS.Doc): BS.Doc => ({ geometry: d.geometry.map((g) => ({ ...g })), constraints: d.constraints.map((c) => ({ ...c })) })
const ext = (g: number): Geo | undefined => S.getGeometry()[g]
function apply(d: BS.Doc) { S.setGeometry(d.geometry); S.setConstraints(d.constraints) }
const isBSpline = (g: Geo | undefined) => g?.type === 'BSplineCurve'

// ── isActive (Utils.cpp) ─────────────────────────────────────────────────────────────────────────────────────────
/** isCommandNeedingGeometryActive: something of the sketch's geometry selected. */
const geometrySelected = () => S.getSelection().some((n) => { const i = idOf(n); return !!i && i.geoId !== GEO_UNDEF })
/** isCommandNeedingBSplineActive: a B-spline among the selected (an edge of it, or its start or end). */
const bsplineSelected = () => S.getSelection().some((n) => { const i = idOf(n); return !!i && i.geoId !== GEO_UNDEF && isBSpline(S.getGeometry()[i.geoId]) })
/** isCommandNeedingBSplineKnotActive: one knot selected (a knot point, or a B-spline's start or end). */
function knotSelected(): boolean {
  const sel = S.getSelection()
  if (sel.length !== 1) return false
  const i = idOf(sel[0])
  if (!i || i.geoId === GEO_UNDEF) return false
  const d = snapshot()
  return BS.isBsplineKnotOrEndPoint(d, i.geoId, i.pos) && !!BS.findBSplineAndKnotIndex(d, i.geoId, i.pos)
}

// ── Geometry to B-Spline (CmdSketcherConvertToNURBS) ─────────────────────────────────────────────────────────────
function convertToNURBS() {
  const ids: number[] = []
  for (const n of S.getSelection()) {
    if (n.length > 4 && n.startsWith('Edge')) ids.push(Number(n.slice(4)) - 1)
    else if (n.length > 12 && n.startsWith('ExternalEdge')) ids.push(-(Number(n.slice(12)) + 2))
  }
  if (!ids.length) { warn('Wrong selection', 'None of the selected elements is an edge.'); S.solve(); return }
  const base = snapshot()
  runOp((k) => {
    const d = copy(base)
    for (const g of ids) if (!BS.convertToNURBS(d, g, k, ext)) throw new Error(`Object does not support NURBS conversion: ${g}`)
    for (const g of ids) BS.exposeInternalGeometry(d, g)
    return d
  }, (d) => { S.openCommand('Convert to NURBS'); apply(d); S.commitCommand(); S.solve() },
  (e) => { error('Error', msg(e)); S.solve() })
}

// ── Increase / Decrease B-Spline Degree ──────────────────────────────────────────────────────────────────────────
const ignoredWarning = () => warn('Wrong selection', 'At least one of the selected objects was not a B-spline and was ignored.')
function increaseDegree() {
  const geo = S.getGeometry()
  const ids: number[] = []
  let ignored = false
  for (const n of S.getSelection()) {
    if (!(n.length > 4 && n.startsWith('Edge'))) continue
    const g = Number(n.slice(4)) - 1
    if (isBSpline(geo[g])) ids.push(g); else ignored = true
  }
  const base = snapshot()
  runOp((k) => {
    const d = copy(base)
    for (const g of ids) {
      if (!BS.increaseBSplineDegree(d, g, k)) throw new Error(`Degree increase failed for: ${g}`)
      BS.exposeInternalGeometry(d, g)
    }
    return d
  }, (d) => {
    if (ignored) ignoredWarning()
    S.openCommand('Increase B-spline degree'); apply(d); S.commitCommand(); S.solve(); S.clearSelection()
  }, (e) => { error('Error', msg(e)); S.solve(); S.clearSelection() })
}
function decreaseDegree() {
  const geo = S.getGeometry()
  const sel = S.getSelection()
  S.clearSelection()
  let target = -1, ignored = false
  for (const n of sel) {
    if (!(n.length > 4 && n.startsWith('Edge'))) continue
    const g = Number(n.slice(4)) - 1
    // only one: the GeoIds change after the first (the old B-spline goes, the new one comes at the end)
    if (isBSpline(geo[g])) { target = g; break }
    ignored = true
  }
  const base = snapshot()
  runOp((k) => { const d = copy(base); if (target >= 0) BS.decreaseBSplineDegree(d, target, k); return d }, (d) => {
    if (ignored) ignoredWarning()
    S.openCommand('Decrease B-spline degree'); apply(d); S.commitCommand(); S.solve(); S.clearSelection()
  }, (e) => { error('Error', msg(e)); S.solve() })
}

// ── Increase / Decrease Knot Multiplicity ────────────────────────────────────────────────────────────────────────
function modifyKnot(incr: 1 | -1) {
  const sel = S.getSelection()
  if (sel.length > 1) { warn('Wrong selection', 'The selection comprises more than one item. Select just one knot.'); return }
  const id = sel.length ? idOf(sel[0]) : null
  const base = snapshot()
  const found = id && BS.isBsplineKnotOrEndPoint(base, id.geoId, id.pos) ? BS.findBSplineAndKnotIndex(base, id.geoId, id.pos) : null
  if (!found) {
    warn('Wrong selection', 'None of the selected elements is a knot of a B-spline')
    S.solve(); S.clearSelection()
    return
  }
  runOp((k) => {
    const d = copy(base)
    let ng: number
    try { ng = BS.modifyBSplineKnotMultiplicity(d, found.spline, found.knot, incr, k) } catch (e) {
      // OCCT's refusal comes back as SketchObjectPy's ValueError
      if (e instanceof KernelError) throw new BS.SketchError(`Multiplicity modification failed for: ${found.spline}`)
      throw e
    }
    BS.exposeInternalGeometry(d, ng)
    return d
  }, (d) => {
    S.openCommand(incr > 0 ? 'Increase knot multiplicity' : 'Decrease knot multiplicity'); apply(d); S.commitCommand(); S.solve(); S.clearSelection()
  }, (e) => {
    // CmdSketcherIncreaseKnotMultiplicity: "Input Error" (a Base::Exception); the decrease: "Error"
    error(incr > 0 ? 'Input Error' : 'Error', msg(e))
    S.clearSelection(); S.solve()
  })
}

// ── Insert Knot (DrawSketchHandlerBSplineInsertKnot) ─────────────────────────────────────────────────────────────
/** The cursor's nearest point on the B-spline is marked and its parameter written next to it (the one of the move
 *  before, as FreeCAD's text lags a move behind); a click inserts a knot there (multiplicity 1), then the B-spline's
 *  internal geometry is exposed again. Continuous mode keeps the tool on, on the same B-spline. */
export class InsertKnotHandler extends DrawSketchHandler {
  readonly toolName = 'DSH_BSplineInsertKnot'
  private guessParam: number
  private last: XY = [0, 0]
  private busy = false
  constructor(private geoId: number) {
    super()
    this.guessParam = CV.bsplineRange(S.getGeometry()[geoId] as CV.BSpline)[0]
  }
  crosshair() { return 'Sketcher_Pointer_InsertKnot' }
  mouseMove(p: XY) {
    const b = S.getGeometry()[this.geoId] as CV.BSpline | undefined
    if (!isBSpline(b)) return
    this.last = p
    const text = ` ${this.guessParam.toFixed(3)}`
    // GeomCurve::closestParameter (OCCT's, from the kernel; the port's own while the answer is on its way)
    const geo = BS.plain(b!)
    this.guessParam = tryKernel((k) => k({ op: 'closest', geo, p }).u!, () => {}) ?? CV.closestParameter(b!, p)!
    const on = CV.bsplineValue(b!, this.guessParam)
    S.setEdit({ positionText: { at: on, text }, markers: [on] })
  }
  pressButton() { return true }
  releaseButton(): boolean {
    if (this.busy) return true
    const b = S.getGeometry()[this.geoId]
    if (!isBSpline(b)) return true
    const g = this.geoId, p = this.last, geo = BS.plain(b)
    const base = snapshot()
    this.busy = true
    runOp((k) => {
      const u = k({ op: 'closest', geo, p }).u!
      const d = copy(base)
      // insertBSplineKnot(%d, %lf, %d): the parameter as "%lf" writes it, six decimals
      const ng = BS.insertBSplineKnot(d, g, Number(u.toFixed(6)), 1, k)
      BS.exposeInternalGeometry(d, ng)
      return { d, ng }
    }, ({ d, ng }) => {
      this.busy = false
      S.openCommand('Insert knot'); apply(d); S.commitCommand(); S.solve()
      // ContinuousCreationMode: on, the B-spline's GeoId as it is now
      this.geoId = ng
      S.applyCursor()
    }, (e) => {
      this.busy = false
      error(e instanceof BS.SketchError ? 'Input Error' : 'CAD Kernel Error', e instanceof KernelError ? `Knot insertion failed for: ${g}` : msg(e))
      S.solve()
      S.purgeHandler()
    })
    return true
  }
  deactivated() { super.deactivated(); S.setEdit({ positionText: null, markers: [] }) }
}
function insertKnot() {
  const sel = S.getSelection()
  if (!sel.length) { warn('Selection is empty', 'Nothing is selected. Select a B-spline.'); return }
  // the first selected element, read as an edge (SubNames[0].substr(4))
  const g = Number(sel[0].slice(4)) - 1
  if (isBSpline(S.getGeometry()[g])) S.activateHandler(new InsertKnotHandler(g))
  else warn('Wrong selection', 'Select a B-spline to insert a knot (not a knot on it). If the curve is not a B-spline, convert it into one first.')
  S.clearSelection()
}

// ── Join Curves (CmdSketcherJoinCurves) ──────────────────────────────────────────────────────────────────────────
function joinCurves() {
  const sel = S.getSelection()
  const d0 = snapshot()
  let ids: [number, PointPos][]
  if (!sel.length) { warn('Selection is empty', 'Nothing is selected. Select end points of curves.'); return }
  if (sel.length === 1) {
    const i = idOf(sel[0])
    if (!i) return
    ids = []
    for (const [g, p] of OPS.directlyCoincident(d0, i.geoId, i.pos)) {
      if (p !== START && p !== END) continue
      if (ids.length < 2) ids.push([g, p])
      else { warn('Too many curves on point', 'Exactly two curves should end at the selected point to be able to join them.'); return }
    }
    if (ids.length < 2) { warn('Too few curves on point', 'Exactly two curves should end at the selected point to be able to join them.'); return }
  } else if (sel.length === 2) {
    const a = idOf(sel[0]), b = idOf(sel[1])
    if (!a || !b) return
    ids = [[a.geoId, a.pos], [b.geoId, b.pos]]
  } else { warn('Wrong selection', 'Two end points, or coincident point should be selected.'); return }
  const [[g1, p1], [g2, p2]] = ids
  const tangent = d0.constraints.some((c) => c.type === 'Tangent' && ((c.first === g1 && c.firstPos === p1 && c.second === g2 && c.secondPos === p2)
    || (c.first === g2 && c.firstPos === p2 && c.second === g1 && c.secondPos === p1)))
  runOp((k) => { const d = copy(d0); BS.join(d, g1, p1, g2, p2, tangent ? 1 : 0, k); return d }, (d) => {
    S.openCommand('Join Curves'); apply(d); S.commitCommand(); S.solve(); S.clearSelection()
  }, (e) => { error('Error', msg(e)); S.clearSelection(); S.solve() })
}

// ── B-spline by knots (DrawSketchHandlerBSpline, ConstructionMethod::Knots) ──────────────────────────────────────
/** Each click a knot point (Part.Point, construction), auto-constraints on it; the right button (or Esc) or a click back
 *  on the first knot ends it: the B-spline through the points (OCCT's GeomAPI_Interpolate, raised to degree 3), the
 *  points made its knots (InternalAlignment), its ends tied to what the first and last point were, then its internal
 *  geometry exposed. R takes back the last point, F toggles periodic, M switches to control points. */
export class BSplineKnotsHandler extends DefaultHandler {
  readonly toolName = 'DSH_BSpline'
  protected readonly states = 2
  protected readonly methods = 1
  private prevCursor: XY = [0, 0]
  points: XY[] = []
  private geoIds: number[] = []
  private multiplicities: number[] = []
  private sugBackup: AutoConstraint[][] = []
  private pendingAutos: SK.Constraint[] = []
  private busy = false
  constructor(public periodic = false, private carried: XY[] = []) { super() }
  crosshair() { return this.periodic ? 'Sketcher_Pointer_Create_Periodic_BSplineByInterpolation' : 'Sketcher_Pointer_Create_BSplineByInterpolation' }
  hints() {
    const sw = this.hint('%1 switch to control points', ['M']), per = this.hint('%1 toggle periodic', ['F'])
    if (this.state === 0) return [this.hint('%1 pick first knot', [LMB]), sw, per]
    return [this.hint('%1 pick next point', [LMB]), this.hint('%1 finish', [RMB]), sw, per, this.hint('%1 undo last point', ['R'])]
  }
  activated() {
    super.activated()
    S.openCommand('Add Sketch B-Spline')
    // changeConstructionMethode: the points of the other method's tool, as knots now
    if (this.carried.length) {
      for (const p of this.carried) { this.prevCursor = p; this.addPos() }
      this.carried = []
      this.state = 1
      S.solve()
      S.updateHints()
    }
  }
  deactivated() { super.deactivated(); S.abortCommand() }
  private lastPoint(): XY { return this.points.length ? this.points[this.points.length - 1] : [0, 0] }
  protected update(p: XY) {
    this.prevCursor = p
    if (this.state === 0) { this.drawPositionAtCursor(p); this.seekAndRender(this.sug[0], p, [0, 0]) }
    else if (this.state === 1) { this.clearCursorText(); this.drawShape(); this.seekAndRender(this.sug[1], p, [0, 0]) }
  }
  /** addGeometry(Part.Point(App.Vector(%f,%f,0)),True). */
  private addPos(): boolean {
    this.points.push(this.prevCursor)
    this.multiplicities.push(1)
    this.geoIds.push(S.highestCurveIndex() + 1)
    S.addGeometry(BS.knotPoint(this.prevCursor))
    return true
  }
  protected canGoToNextMode() {
    if (this.busy) return false
    if (this.state === 0) {
      this.addPos()
      this.onElement(this.sug[0], this.geoIds[this.geoIds.length - 1], START)
      this.commitAutos()
      S.solve()
      return true
    }
    if (this.points.length && Math.hypot(this.prevCursor[0] - this.lastPoint()[0], this.prevCursor[1] - this.lastPoint()[1]) < CONFUSION) return false
    let closed = false
    for (const ac of this.sug[1]) {
      if (ac.type !== 'Coincident') continue
      if (ac.geoId === this.geoIds[0]) closed = true
      else if (SK.coincidentPoints(S.getConstraints(), ac.geoId, ac.posId).has(this.geoIds[0])) closed = true
    }
    if (closed) { if (this.periodic) return true }
    else S.setAngleSnapping(true, this.lastPoint())
    this.addPos()
    this.onElement(this.sug[1], this.geoIds[this.geoIds.length - 1], START)
    this.sugBackup.push([...this.sug[1]])
    this.sug[1].length = 0
    this.commitAutos()
    S.solve()
    return closed
  }
  private commitAutos() { this.pendingAutos.push(...this.autos); this.autos = [] }
  quit() {
    if (this.state === 1) {
      if (this.geoIds.length > 1) this.setState(2)
      else this.handleContinuousMode()
      return
    }
    S.abortCommand()
    super.quit()
  }
  rightButtonOrEsc() { this.quit() }
  registerPressedKey(pressed: boolean, key: string): boolean {
    if (key === 'U' || key === 'J') return true // the degree widget: the knots method makes degree 3 whatever it says
    if (!pressed && key === 'R' && this.state === 1) { this.undoLastPoint(); return true }
    if (!pressed && key === 'F') { this.periodic = !this.periodic; S.applyCursor(); if (this.state === 1) this.drawShape(); return true }
    if (key === 'M') {
      if (!pressed) { const pts = [...this.points]; S.activateHandler(new BSplineHandler(this.periodic, pts)) }
      return true
    }
    return super.registerPressedKey(pressed, key)
  }
  private undoLastPoint() {
    if (this.geoIds.length === 1) { this.quit(); return }
    const del = this.geoIds[this.geoIds.length - 1]
    const ids = S.getConstraints().map((c, i) => ([c.first, c.second, c.third].includes(del) ? i : -1)).filter((i) => i >= 0)
    S.delConstraints(ids)
    S.delGeometries([del])
    this.pendingAutos = this.pendingAutos.filter((c) => ![c.first, c.second, c.third].includes(del))
    S.solve()
    this.geoIds.pop(); this.points.pop(); this.multiplicities.pop(); this.sugBackup.pop()
    this.update(this.prevCursor)
  }
  /** The preview: Part::GeomBSplineCurve::interpolate of the points and the cursor (OCCT's, from the kernel; drawn when
   *  the answer comes, the last one meanwhile). */
  private preview: Geo | null = null
  protected createShape(onlyOutline: boolean) {
    this.shapeGeometry = []
    const pts = [...this.points]
    const l = Math.hypot(this.prevCursor[0] - this.lastPoint()[0], this.prevCursor[1] - this.lastPoint()[1])
    if (onlyOutline && (!pts.length || l >= CONFUSION)) pts.push(this.prevCursor)
    if (pts.length < 2) return
    const periodic = this.periodic
    const g = tryKernel((k) => k({ op: 'interpolate', points: pts, periodic, degree: null }).geo!, () => { if (this.state === 1) this.drawShape() })
    if (g) this.preview = g
    if (this.preview) this.shapeGeometry.push(this.isConstructionMode() ? { ...this.preview, construction: true } : this.preview)
  }
  /** The B-spline, with the kernel's answers (fetched in finish, before this runs). */
  private build(k: Kernel, d: BS.Doc) {
    return BS.bsplineByKnots(d, this.geoIds[0], this.points, this.multiplicities, this.periodic, this.isConstructionMode(), k)
  }
  protected finish(): boolean {
    if (!this.isLast || this.geoIds.length <= 1) return super.finish()
    if (this.busy) return true
    // the interpolation is OCCT's: fetch it, then make the B-spline as the other tools do, all at once
    this.busy = true
    const base = snapshot()
    withKernel((k) => this.build(k, copy(base))).then(() => { this.busy = false; super.finish() },
      (e) => { this.busy = false; report('err', `Error: Error creating B-spline (${msg(e)})`); S.abortCommand(); S.solve(); this.handleContinuousMode() })
    return true
  }
  protected executeCommands() {
    if (this.geoIds.length === 1) { S.abortCommand(); return }
    try {
      const d = snapshot()
      runOp((k) => this.build(k, d), () => { apply(d); S.commitCommand() }, (e) => { throw e })
    } catch (e) {
      report('err', 'Error: Error creating B-spline')
      void e
      S.abortCommand()
      S.solve()
    }
  }
  protected generateAutoConstraints() {
    this.autos = this.pendingAutos; this.pendingAutos = []
    this.removeRedundantAutoConstraints()
  }
  protected createAutoConstraints() { this.createGeneratedAutoConstraints(true); this.sug[0].length = 0; this.sug[1].length = 0 }
  protected handleContinuousMode(): boolean {
    if (this.continuousMode) { this.reset(); return false }
    S.purgeHandler()
    return true
  }
  protected onReset() {
    S.abortCommand()
    S.openCommand('Add Sketch B-Spline')
    this.geoIds = []; this.points = []; this.multiplicities = []; this.sugBackup = []; this.pendingAutos = []; this.preview = null
  }
}
// M in the control points tool: the knots tool, with the points so far
setKnotsSwitch((periodic, points) => S.activateHandler(new BSplineKnotsHandler(periodic, points)))

// ── the commands ─────────────────────────────────────────────────────────────────────────────────────────────────
const tool = (make: () => S.Handler) => () => S.activateHandler(make())
/** What each curve command does (sketchcmds.ts's RUN takes these). */
export const CURVE_RUN: Record<string, () => void> = {
  Sketcher_BSplineConvertToNURBS: convertToNURBS,
  Sketcher_BSplineIncreaseDegree: increaseDegree,
  Sketcher_BSplineDecreaseDegree: decreaseDegree,
  Sketcher_BSplineIncreaseKnotMultiplicity: () => modifyKnot(1),
  Sketcher_BSplineDecreaseKnotMultiplicity: () => modifyKnot(-1),
  Sketcher_BSplineInsertKnot: insertKnot,
  Sketcher_JoinCurves: joinCurves,
  Sketcher_CreateBSplineByInterpolation: tool(() => new BSplineKnotsHandler(false)),
  Sketcher_CreatePeriodicBSplineByInterpolation: tool(() => new BSplineKnotsHandler(true)),
  ...Object.fromEntries((Object.keys(LAYERS) as LayerCommand[]).map((c) => [c, () => toggleLayer(c)])),
}
/** Command::isActive for the curve commands; undefined for the others. */
export function curveEnabled(name: string): boolean | undefined {
  switch (name) {
    case 'Sketcher_BSplineConvertToNURBS': return geometrySelected()
    case 'Sketcher_BSplineIncreaseDegree': case 'Sketcher_BSplineDecreaseDegree': case 'Sketcher_BSplineInsertKnot': case 'Sketcher_JoinCurves':
      return bsplineSelected()
    case 'Sketcher_BSplineIncreaseKnotMultiplicity': case 'Sketcher_BSplineDecreaseKnotMultiplicity': return knotSelected()
    default: return undefined
  }
}
onLayerToggled(() => S.setEdit({}))
void MID; void NONE

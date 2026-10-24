// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Sketcher/Gui/DrawSketchHandlerTrimming.h: 2022 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/DrawSketchHandlerSplitting.h: 2022 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/DrawSketchHandlerExtend.h: 2022 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/DrawSketchHandlerFillet.h: 2022 Abdullah Tahiri
// The Sketcher's editing tools: Trim (Sketcher_Trimming: the piece under the cursor between its cuts goes, hold the
// button and drag to trim several, U for the axes as cuts), Split (Sketcher_Split), Extend (Sketcher_Extend: pick a
// line or an arc, then where its end goes) and Fillet / Chamfer (Sketcher_CreateFillet, Sketcher_CreateChamfer: two
// edges, or the corner point of two lines; U keeps the corner as construction, M switches fillet and chamfer). Each
// calls the SketchObject operation FreeCAD's tool calls, ported in sketchops.ts.
import type { Geo, XY } from './solver'
import * as SK from './sketch'
import { type PointPos, NONE, START, END, GEO_UNDEF } from './sketch'
import * as S from './sketcher'
import * as OPS from './sketchops'
import { DefaultHandler, DrawSketchHandler, type AutoConstraint } from './sketchtools'
import { report } from './store'
import { runOp, KernelError } from './sketchkernel'
import './sketchkernelapi'

const LMB = 'LMB'
/** The coordinates as the tool's Python command writes them ("%f": six decimals). */
const f6 = (v: number) => Number(v.toFixed(6))
const at6 = (p: XY): XY => [f6(p[0]), f6(p[1])]
const doc = (): OPS.Doc => ({ geometry: S.getGeometry().map((g) => ({ ...g })), constraints: S.getConstraints().map((c) => ({ ...c })) })
/** A copy of a snapshot, for an operation that may run again once the sketch kernel has answered (runOp). */
const copy = (d: OPS.Doc): OPS.Doc => ({ geometry: d.geometry.map((g) => ({ ...g })), constraints: d.constraints.map((c) => ({ ...c })) })
function apply(d: OPS.Doc) { S.setGeometry(d.geometry); S.setConstraints(d.constraints) }
/** SketchObject::moveGeometry(..., updateGeoBeforeMoving=true), through the solver. */
const mover: OPS.Mover = (d, geo, pos, to) => {
  const r = S.solveRaw({ geometry: d.geometry, constraints: d.constraints.map(SK.toCons), solve: false, drags: [{ geo, pos, to, update_geometry: true }] })
  return r && r.status_code === 0 && r.stored_geometry ? r.stored_geometry : null
}
const isInternal = (g: number) => S.getConstraints().some((c) => c.type === 'InternalAlignment' && c.first === g)
/** The edge under the cursor, if the tool's selection gate lets it through. */
function preselectedCurve(allowed: (g: Geo, id: number) => boolean): number {
  const pre = S.getPreselection(), id = pre.curve
  if (id === null || id < 0) return GEO_UNDEF
  const g = S.getGeometry()[id]
  return g && allowed(g, id) ? id : GEO_UNDEF
}

// ── Trim (DrawSketchHandlerTrimming.h) ───────────────────────────────────────────────────────────────────────────
/** TrimmingSelection: a trimmed curve, a circle, an ellipse or a B-spline that is not internal geometry. */
const trimmable = (g: Geo, id: number) => g.type !== 'Point' && !isInternal(id)
export class TrimmingHandler extends DefaultHandler {
  readonly toolName = 'DSH_Trimming'
  protected readonly states = 1
  private mousePressed = false
  private trimPos: XY = [0, 0]
  private geoIdToTrim = GEO_UNDEF
  private includeAxes = false
  crosshair() { return 'Sketcher_Pointer_Trimming' }
  hints() { return [this.hint('%1 pick edge to trim', [LMB]), this.hint('%1 toggle include axes as trim boundaries', ['U'])] }
  pressButton(p: XY) { this.mousePressed = true; return super.pressButton(p) }
  releaseButton(_p: XY) { this.mousePressed = false; return true }
  registerPressedKey(pressed: boolean, key: string): boolean {
    if (key === 'U' && !pressed) { this.includeAxes = !this.includeAxes; return true }
    return super.registerPressedKey(pressed, key)
  }
  protected update(p: XY) {
    this.trimPos = p
    this.geoIdToTrim = preselectedCurve(trimmable)
    if (this.mousePressed) { this.executeCommands(); return } // hold-and-drag trim
    if (this.geoIdToTrim < 0) { S.setEdit({ markers: [] }); return }
    const seek = OPS.seekTrimPoints(doc(), this.geoIdToTrim, p, this.includeAxes)
    if (!seek) return
    const g = this.geoIdToTrim
    S.setEdit({ markers: [seek.ids[0] !== GEO_UNDEF ? seek.points[0] : S.getPoint(g, START)!, seek.ids[1] !== GEO_UNDEF ? seek.points[1] : S.getPoint(g, END)!].filter((x) => !!x) })
  }
  protected canGoToNextMode() { return this.geoIdToTrim >= 0 }
  protected executeCommands() {
    if (this.geoIdToTrim < 0) return
    const g = this.geoIdToTrim
    this.geoIdToTrim = GEO_UNDEF
    S.setPreselection(null)
    const base = doc(), at = at6(this.trimPos), axes = this.includeAxes
    // a B-spline's cuts are OCCT's (the sketch kernel): the trim waits for them
    runOp((k) => { const d = copy(base); OPS.trim(d, g, at, axes, k); return d }, (d) => {
      S.openCommand('Trim edge')
      apply(d)
      S.commitCommand()
      S.clearSelection()
      S.solve()
    }, (e) => { report('err', `Failed to trim edge: ${e instanceof Error ? e.message : String(e)}`); S.clearSelection(); S.solve() })
  }
}

// ── Split (DrawSketchHandlerSplitting.h) ─────────────────────────────────────────────────────────────────────────
export class SplittingHandler extends DrawSketchHandler {
  readonly toolName = 'DSH_Splitting'
  crosshair() { return 'Sketcher_Pointer_Splitting' }
  hints() { return [{ message: '%1 pick location on edge to split', keys: [LMB] }] }
  activated() { S.clearSelection() }
  mouseMove(_p: XY) {}
  pressButton(_p: XY) { return true }
  releaseButton(p: XY) {
    const id = preselectedCurve((g) => g.type !== 'Point' && g.type !== 'ArcOfCircle' ? true : g.type === 'ArcOfCircle')
    if (id < 0) { this.quit(); return true }
    const base = doc(), at = at6(p)
    runOp((k) => { const d = copy(base); OPS.split(d, id, at, k); return d }, (d) => {
      S.openCommand('Split edge')
      apply(d)
      S.commitCommand()
      S.solve()
    }, (e) => { report('err', `Failed to add edge: ${e instanceof Error ? e.message : String(e)}`); S.solve() })
    return true
  }
}

// ── Extend (DrawSketchHandlerExtend.h) ───────────────────────────────────────────────────────────────────────────
const getAngle = (a: XY, b: XY) => { const l = Math.hypot(...a) * Math.hypot(...b); return l ? Math.acos(Math.max(-1, Math.min(1, (a[0] * b[0] + a[1] * b[1]) / l))) : NaN }
/** DrawSketchHandlerExtend::crossProduct, which returns an int. */
const crossInt = (a: XY, b: XY) => Math.trunc(a[0] * b[1] - a[1] * b[0])
export class ExtendHandler extends DrawSketchHandler {
  readonly toolName = 'DSH_Extend'
  private mode: 'first' | 'second' = 'first'
  private baseGeoId = -1
  private extendFromStart = false
  private savedExtendFromStart = false
  private increment = 0
  private sugConstr: AutoConstraint[] = []
  crosshair() { return 'Sketcher_Pointer_Extension' }
  hints() { return [{ message: this.mode === 'first' ? '%1 pick edge to extend' : '%1 set extension length', keys: [LMB] }] }
  activated() { S.clearSelection() }
  mouseMove(p: XY) {
    if (this.mode !== 'second') return
    const g = S.getGeometry()[this.baseGeoId]
    if (g?.type === 'LineSegment') {
      const sp = g.start, ep = g.end, line: XY = [ep[0] - sp[0], ep[1] - sp[1]], rp: XY = [p[0] - sp[0], p[1] - sp[1]]
      const t = (rp[0] * line[0] + rp[1] * line[1]) / (line[0] ** 2 + line[1] ** 2)
      const proj: XY = [line[0] * t, line[1] * t]
      // Base::Vector2d::Distance(recenteredLine): from the point to the line's end, as vectors from the origin
      const curve: XY[] = Math.hypot(...rp) < Math.hypot(rp[0] - line[0], rp[1] - line[1]) ? [[sp[0] + proj[0], sp[1] + proj[1]], ep] : [sp, [sp[0] + proj[0], sp[1] + proj[1]]]
      const inCurve = Math.hypot(...proj) < Math.hypot(...line) && getAngle(proj, line) < 0.1
      if (inCurve) {
        this.increment = this.savedExtendFromStart ? -1 * Math.hypot(...proj) : Math.hypot(...proj) - Math.hypot(...line)
        this.extendFromStart = this.savedExtendFromStart
      } else {
        this.extendFromStart = Math.hypot(p[0] - sp[0], p[1] - sp[1]) < Math.hypot(p[0] - ep[0], p[1] - ep[1])
        this.increment = this.extendFromStart ? Math.hypot(...proj) : Math.hypot(...proj) - Math.hypot(...line)
      }
      S.setEdit({ curves: [curve] })
    } else if (g?.type === 'ArcOfCircle') {
      const c = g.center, r = g.radius, start = g.start_angle, end = g.end_angle, arcAngle = end - start
      const angle: XY = [p[0] - c[0], p[1] - c[1]], sa: XY = [Math.cos(start), Math.sin(start)], ea: XY = [Math.cos(end), Math.sin(end)]
      const half: XY = [Math.cos(start + arcAngle / 2), Math.sin(start + arcAngle / 2)]
      const toEnd = getAngle(angle, ea), toStart = getAngle(angle, sa)
      let modStart = start, modArc = end - start
      const outOfArc = getAngle(half, angle) * 2 > arcAngle
      if (this.extendFromStart) {
        const ccw = crossInt(angle, sa) < 0
        if (outOfArc) { if (ccw) { modStart -= 2 * Math.PI - toStart; modArc += 2 * Math.PI - toStart } else { modStart -= toStart; modArc += toStart } }
        else if (ccw) { modStart += toStart; modArc -= toStart } else { modStart += 2 * Math.PI - toStart; modArc -= 2 * Math.PI - toStart }
      } else {
        const cw = crossInt(angle, ea) >= 0
        if (outOfArc) modArc += cw ? 2 * Math.PI - toEnd : toEnd
        else modArc -= cw ? toEnd : 2 * Math.PI - toEnd
      }
      this.increment = modArc - (end - start)
      S.setEdit({ curves: [Array.from({ length: 31 }, (_, i): XY => { const a = modStart + (i * modArc) / 30; return [c[0] + r * Math.cos(a), c[1] + r * Math.sin(a)] })] })
    }
    const pre = S.getPreselection().curve
    if (this.baseGeoId !== pre) this.seekAndRender(this.sugConstr, p, [0, 0])
  }
  pressButton(_p: XY) { return true }
  releaseButton(p: XY) {
    if (this.mode === 'first') {
      this.baseGeoId = preselectedCurve((g) => g.type === 'LineSegment' || g.type === 'ArcOfCircle')
      if (this.baseGeoId > -1) {
        const g = S.getGeometry()[this.baseGeoId]
        if (g.type === 'LineSegment') {
          this.savedExtendFromStart = Math.hypot(p[0] - g.start[0], p[1] - g.start[1]) < Math.hypot(p[0] - g.end[0], p[1] - g.end[1])
          this.extendFromStart = this.savedExtendFromStart
          this.mode = 'second'
        } else if (g.type === 'ArcOfCircle') {
          const a: XY = [p[0] - g.center[0], p[1] - g.center[1]]
          this.extendFromStart = getAngle(a, [Math.cos(g.start_angle), Math.sin(g.start_angle)]) < getAngle(a, [Math.cos(g.end_angle), Math.sin(g.end_angle)])
          this.mode = 'second'
        }
      } else { this.quit(); return true }
    } else {
      const pos: PointPos = this.extendFromStart ? START : END
      S.openCommand('Extend edge')
      try {
        const d = doc()
        OPS.extend(d, this.baseGeoId, f6(this.increment), pos, mover)
        apply(d)
        S.commitCommand()
        if (this.sugConstr.length) { this.createAutoConstraintsDirect(this.sugConstr, this.baseGeoId, pos); this.sugConstr = [] }
      } catch (e) { report('err', `Failed to extend edge: ${e instanceof Error ? e.message : String(e)}`); S.abortCommand() }
      S.solve()
      // ContinuousCreationMode (on)
      this.mode = 'first'
      S.setEdit({ curves: [] })
      S.applyCursor()
    }
    S.updateHints()
    return true
  }
}

// ── Fillet / Chamfer (DrawSketchHandlerFillet.h) ─────────────────────────────────────────────────────────────────
export class FilletHandler extends DefaultHandler {
  readonly toolName = 'DSH_Fillet'
  protected readonly states = 2
  protected readonly methods = 2
  private preserveCorner = true
  private vtId = -1
  private geoId1 = GEO_UNDEF; private geoId2 = GEO_UNDEF
  private firstPos: XY = [0, 0]; private secondPos: XY = [0, 0]
  constructor(method = 0) { super(); this.method = method }
  crosshair() {
    if (this.method === 0) return this.preserveCorner ? 'Sketcher_Pointer_Create_PointFillet' : 'Sketcher_Pointer_Create_Fillet'
    return this.preserveCorner ? 'Sketcher_Pointer_Create_PointChamfer' : 'Sketcher_Pointer_Create_Chamfer'
  }
  hints() {
    const sw = this.hint('%1 switch mode', ['M']), pc = this.hint('%1 toggle preserve corner', ['U'])
    return [this.hint(this.state === 0 ? '%1 pick first edge or point' : '%1 pick second edge', [LMB]), sw, pc]
  }
  registerPressedKey(pressed: boolean, key: string): boolean {
    if (key === 'U' && !pressed) { this.preserveCorner = !this.preserveCorner; S.applyCursor(); return true }
    return super.registerPressedKey(pressed, key)
  }
  protected resetOnMethodChange() { return false }
  protected update(p: XY) {
    const pre = S.getPreselection()
    if (this.state === 0) {
      this.vtId = pre.point >= 0 ? pre.point : -1
      this.geoId1 = pre.curve !== null && pre.curve >= 0 ? pre.curve : GEO_UNDEF
      this.firstPos = p
    } else if (this.state === 1) {
      this.geoId2 = pre.curve !== null && pre.curve >= 0 ? pre.curve : GEO_UNDEF
      this.secondPos = p
    }
  }
  private bounded(id: number) { const g = S.getGeometry()[id]; return !!g && g.type !== 'Point' && g.type !== 'Circle' && g.type !== 'Ellipse' }
  protected canGoToNextMode() {
    if (this.state === 0) return this.vtId !== -1 || (this.geoId1 >= 0 && this.bounded(this.geoId1))
    if (this.state === 1) return this.geoId2 >= 0 && this.bounded(this.geoId2)
    return false
  }
  protected onButtonPressed(p: XY) {
    this.update(p)
    if (this.canGoToNextMode()) {
      if (this.state === 0) {
        if (this.vtId !== -1) this.setState(2)
        else { S.addSelection(SK.edgeName(this.geoId1)); this.setState(1) }
      } else this.setState(2)
    }
    S.updateHints()
  }
  protected executeCommands() {
    const chamfer = this.method === 1
    const d = doc()
    const geo = S.getGeometry()
    if (this.vtId !== -1) {
      const [g, pos] = S.geoVertexIndex(this.vtId)
      if (pos !== START && pos !== END) return
      const radius = OPS.cornerFilletRadius(d, g, pos)
      if (radius < 0) return
      const list = OPS.directlyCoincident(d, g, pos)
      const construction = list.length >= 2 && !!geo[list[0][0]]?.construction && !!geo[list[1][0]]?.construction
      const filletGeoId = S.highestCurveIndex() + (chamfer ? 2 : 1)
      S.openCommand('Create fillet')
      try {
        OPS.filletAtPoint(d, g, pos, f6(radius), true, this.preserveCorner, chamfer, mover)
        if (construction && d.geometry[filletGeoId]) d.geometry[filletGeoId] = { ...d.geometry[filletGeoId], construction: !d.geometry[filletGeoId].construction }
        apply(d)
        S.commitCommand()
      } catch (e) { report('err', `Failed to create fillet: ${e instanceof Error ? e.message : String(e)}`); S.abortCommand() }
    } else {
      const g1 = geo[this.geoId1], g2 = geo[this.geoId2]
      if (!g1 || !g2) return
      const construction = !!g1.construction && !!g2.construction
      let radius = 0
      if (g1.type === 'LineSegment' && g2.type === 'LineSegment') {
        radius = OPS.suggestFilletRadius(g1, g2, this.firstPos, this.secondPos)
        if (radius < 0) return
      }
      const filletGeoId = S.highestCurveIndex() + (chamfer ? 2 : 1)
      const g1id = this.geoId1, g2id = this.geoId2, r1 = at6(this.firstPos), r2 = at6(this.secondPos), corner = this.preserveCorner
      // between curves other than two lines the fillet is OCCT's (the sketch kernel's offset curves): it waits for it
      runOp((k) => {
        const e = copy(d)
        if (!OPS.fillet(e, g1id, g2id, r1, r2, f6(radius), true, corner, chamfer, mover, k)) {
          // SketchObjectPy::fillet's ValueError (the points as C++ streams them, six significant digits)
          const v = (p: XY) => `(${p.map((x) => Number(x.toPrecision(6))).join(', ')}, 0)`
          throw new Error(`Not able to fillet curves with ids : (${g1id}, ${g2id}) and points ${v(r1)} & ${v(r2)}`)
        }
        return e
      }, (e) => {
        if (construction && e.geometry[filletGeoId]) e.geometry[filletGeoId] = { ...e.geometry[filletGeoId], construction: !e.geometry[filletGeoId].construction }
        S.openCommand('Create fillet')
        apply(e)
        S.commitCommand()
        S.solve()
      }, (e) => { report('err', `${e instanceof KernelError ? 'CAD Kernel Error' : 'Value Error'}: ${e instanceof Error ? e.message : String(e)}`); S.clearSelection(); S.solve() })
      S.clearSelection()
    }
  }
  protected generateAutoConstraints() {}
  protected createAutoConstraints() {}
  protected onReset() { this.vtId = -1; this.geoId1 = GEO_UNDEF; this.geoId2 = GEO_UNDEF }
}
void NONE

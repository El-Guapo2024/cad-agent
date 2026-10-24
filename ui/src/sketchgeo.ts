// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Sketcher/Gui/DrawSketchHandlerEllipse.h: 2022 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/DrawSketchHandlerArcOfEllipse.h: 2022 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/DrawSketchHandlerArcOfHyperbola.h: 2022 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/DrawSketchHandlerArcOfParabola.h: 2022 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/DrawSketchHandlerBSpline.h: 2022 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/DrawSketchDefaultHandler.h: 2022 Abdullah Tahiri
//   src/Mod/Sketcher/App/SketchObjectGeometry.cpp: 2008 Jürgen Riegel
// The Sketcher's conic and B-spline tools: the ellipse by its centre or by its axis ends (Sketcher_CreateEllipseByCenter,
// Sketcher_CreateEllipseBy3Points), the arcs of ellipse, hyperbola and parabola, and the B-spline by its control points,
// open or periodic (Sketcher_CreateBSpline, Sketcher_CreatePeriodicBSpline), each making the geometry, the internal
// geometry (exposeInternalGeometry) and the auto-constraints FreeCAD's tool makes for the same clicks.
import type { Geo, XY } from './solver'
import * as SK from './sketch'
import { type Constraint, type PointPos, NONE, START, END, MID, constraint, alignmentConstraint } from './sketch'
import * as S from './sketcher'
import * as CV from './sketchcurves'
import { DefaultHandler, type AutoConstraint } from './sketchtools'

const CONFUSION = 1e-7, PCONFUSION = CONFUSION * 0.01
const sub = (a: XY, b: XY): XY => [a[0] - b[0], a[1] - b[1]], add = (a: XY, b: XY): XY => [a[0] + b[0], a[1] + b[1]]
const mul = (a: XY, k: number): XY => [a[0] * k, a[1] * k], len = (a: XY) => Math.hypot(a[0], a[1])
const dot = (a: XY, b: XY) => a[0] * b[0] + a[1] * b[1]
const normalize = (a: XY): XY => { const l = len(a); return l ? [a[0] / l, a[1] / l] : [0, 0] }
/** Base::Vector2d::Rotate(π/2). */
const perp = (a: XY): XY => [-a[1], a[0]]
const LMB = 'LMB', RMB = 'RMB'

/** ElCLib::AdjustPeriodic, as Geom_TrimmedCurve::SetTrim puts an ellipse's trim in [0, 2π). */
export function adjustPeriodic(u1: number, u2: number): [number, number] {
  const first = 0, last = 2 * Math.PI, period = last - first, preci = Math.min(Math.abs(u2 - u1) / 2, PCONFUSION)
  u1 -= Math.floor((u1 - first) / period) * period
  if (last - u1 < preci) u1 -= period
  u2 -= Math.floor((u2 - u1) / period) * period
  if (u2 - u1 < preci) u2 += period
  return [u1, u2]
}
const cons = (construction: boolean) => (construction ? { construction: true } : {})
/** addEllipseToShapeGeometry: centre, major axis direction, radii. */
export function makeEllipse(c: XY, majorAxis: XY, a: number, b: number, construction: boolean): Geo {
  return { type: 'Ellipse', center: c, major_radius: a, minor_radius: b, x_axis: normalize(majorAxis), ...cons(construction) }
}
/** addArcOfEllipseToShapeGeometry: setRange(start, end, emulateCCW) normalises the trim. */
export function makeArcOfEllipse(c: XY, majorAxis: XY, a: number, b: number, start: number, end: number, construction: boolean): Geo {
  const [u1, u2] = adjustPeriodic(start, end)
  return { type: 'ArcOfEllipse', center: c, major_radius: a, minor_radius: b, x_axis: normalize(majorAxis), start_angle: u1, end_angle: u2, ...cons(construction) }
}
export function makeArcOfHyperbola(c: XY, majorAxis: XY, a: number, b: number, start: number, end: number, construction: boolean): Geo {
  return { type: 'ArcOfHyperbola', center: c, major_radius: a, minor_radius: b, x_axis: normalize(majorAxis), start_angle: Math.min(start, end), end_angle: Math.max(start, end), ...cons(construction) }
}
export function makeArcOfParabola(axis: XY, vertex: XY, focal: number, start: number, end: number, construction: boolean): Geo {
  return { type: 'ArcOfParabola', center: vertex, focal, x_axis: normalize(axis), start_angle: Math.min(start, end), end_angle: Math.max(start, end), ...cons(construction) }
}

/** The sketch's InternalAlignment constraints, as exposeInternalGeometry reads them. */
function alignments(): CV.AlignmentRef[] {
  return S.getConstraints().filter((c) => c.type === 'InternalAlignment' && c.alignment)
    .map((c) => ({ first: c.first, second: c.second, alignment: c.alignment!, index: c.alignmentIndex ?? -1 }))
}
/** SketchObject::exposeInternalGeometry(geoId) on the sketch in edit: the internal geometry its constraints do not
 *  already give it, as construction geometry, then its InternalAlignment (and a B-spline's Weight and Equal)
 *  constraints (addAndCleanup). The number of elements added, or -1 for a type that has none. */
export function exposeInternalGeometry(geoId: number): number {
  const cs = S.getConstraints()
  const weighted = (circle: number) => cs.some((c) => c.type === 'Weight' && c.first === circle)
  const ex = CV.exposeInternalGeometry(S.getGeometry(), alignments(), geoId, weighted)
  if (!ex) return -1
  if (ex.geometry.length) S.addGeometry(ex.geometry)
  const list: Constraint[] = ex.order.map((k) => {
    if (k >= 0) { const a = ex.alignments[k]; return alignmentConstraint(a.alignment, a.first, a.firstPos, a.second, a.index) }
    const o = ex.others[-1 - k]
    return o.type === 'Weight' ? constraint('Weight', o.first, NONE, SK.GEO_UNDEF, NONE, SK.GEO_UNDEF, NONE, o.value ?? 1) : constraint('Equal', o.first, NONE, o.second!)
  })
  if (list.length) S.addConstraint(list)
  return ex.geometry.length
}

// ── Ellipse (DrawSketchHandlerEllipse.h): Center, then ThreeRim ("Axis endpoints") ──────────────────────────────
export class EllipseHandler extends DefaultHandler {
  readonly toolName = 'DSH_Ellipse'
  protected readonly states = 3
  protected readonly methods = 2
  private centerPoint: XY = [0, 0]; private periapsis: XY = [0, 0]; private apoapsis: XY = [0, 0]
  private firstAxis: XY = [0, 0]; private secondAxis: XY = [0, 0]
  private firstRadius = 0; private secondRadius = 0; private majorRadius = 0; private minorRadius = 0
  private ellipseGeoId = SK.GEO_UNDEF
  constructor(method = 0) { super(); this.method = method }
  crosshair() { return this.method === 0 ? 'Sketcher_Pointer_Create_EllipseByCenter' : 'Sketcher_Pointer_Create_Ellipse_3points' }
  hints() {
    const c = ['%1 pick ellipse center', '%1 pick axis endpoint', '%1 pick minor axis endpoint'], r = ['%1 pick first rim point', '%1 pick second rim point', '%1 pick third rim point']
    return [this.hint((this.method === 0 ? c : r)[Math.min(this.state, 2)], [LMB]), this.hint('%1 switch mode', ['M'])]
  }
  protected update(p: XY) {
    if (this.state === 0) {
      this.drawPositionAtCursor(p)
      if (this.method === 0) { this.centerPoint = p; this.seekAndRender(this.sug[0], p, [0, 0]) }
      else { this.apoapsis = p; this.seekAndRender(this.sug[0], p, [0, 0], 'curve') }
    } else if (this.state === 1) {
      this.periapsis = p
      this.calculateMajorAxisParameters()
      this.drawShape()
      if (this.method === 0) this.clearCursorText(); else this.drawPositionAtCursor(p)
      this.seekAndRender(this.sug[1], p, [0, 0], 'curve')
    } else if (this.state === 2) {
      this.calculateThroughPointMinorAxisParameters(p)
      this.drawShape()
      if (this.method === 0) this.clearCursorText(); else this.drawPositionAtCursor(p)
      this.seekAndRender(this.sug[2], p, [0, 0], 'curve')
    }
  }
  private calculateMajorAxisParameters() {
    if (this.method === 1) this.centerPoint = add(mul(sub(this.apoapsis, this.periapsis), 0.5), this.periapsis)
    this.firstAxis = sub(this.periapsis, this.centerPoint)
    this.firstRadius = len(this.firstAxis)
  }
  /** de la Hire: the ellipse through the cursor. */
  private calculateThroughPointMinorAxisParameters(p: XY) {
    const d = sub(p, this.centerPoint), fa = this.firstAxis
    const projx = mul(fa, dot(d, fa) / dot(fa, fa)) // Base::Vector2d::ProjectToLine
    const projy = sub(d, projx)
    const lx = len(projx), ly = len(projy)
    if (lx > this.firstRadius) this.secondRadius = ly
    else {
      const t = Math.acos(lx / this.firstRadius)
      this.secondRadius = t === 0 ? 0 : ly / Math.sin(t)
    }
    this.secondAxis = mul(normalize(projy), this.secondRadius)
  }
  protected createShape() {
    this.shapeGeometry = []
    let majorAxis = this.firstAxis
    this.majorRadius = this.firstRadius
    if (this.state === 1) this.minorRadius = this.majorRadius * 0.5
    else {
      this.minorRadius = this.secondRadius
      if (this.secondRadius > this.firstRadius) { majorAxis = this.secondAxis; this.majorRadius = this.secondRadius; this.minorRadius = this.firstRadius }
    }
    if (this.majorRadius < CONFUSION || this.minorRadius < CONFUSION) return
    if (Math.abs(this.firstRadius - this.secondRadius) < CONFUSION) this.shapeGeometry.push(this.circle(this.centerPoint, this.firstRadius))
    else this.shapeGeometry.push(makeEllipse(this.centerPoint, majorAxis, this.majorRadius, this.minorRadius, this.isConstructionMode()))
  }
  protected canGoToNextMode() {
    if (this.state === 1 && this.firstRadius < CONFUSION) return false
    if (this.state === 2 && (this.firstRadius < CONFUSION || this.secondRadius < CONFUSION)) return false
    return true
  }
  protected angleSnappingControl() { if (this.state === 1 || this.state === 2) S.setAngleSnapping(true, this.centerPoint); else S.setAngleSnapping(false) }
  protected executeCommands() {
    S.openCommand('Add sketch ellipse')
    this.ellipseGeoId = S.highestCurveIndex() + 1
    this.createShape()
    this.addShape()
    // in the exceptional event that this may lead to a circle, do not exposeInternalGeometry
    if (this.shapeGeometry[0]?.type === 'Ellipse') exposeInternalGeometry(this.ellipseGeoId)
    S.commitCommand()
  }
  protected generateAutoConstraints() {
    const id = this.ellipseGeoId, [ac1, ac2, ac3] = this.sug
    if (this.method === 0) { this.onElement(ac1, id, MID); this.onElement(ac2, id, NONE); this.onElement(ac3, id, NONE) }
    else { this.onElement(ac1, id, NONE); this.onElement(ac2, id, NONE); this.onElement(ac3, id, NONE) }
    this.removeRedundantAutoConstraints()
  }
  protected createAutoConstraints() { this.createGeneratedAutoConstraints(true); for (const s of this.sug.slice(0, 3)) s.length = 0 }
}

// ── Arc of ellipse (DrawSketchHandlerArcOfEllipse.h) ─────────────────────────────────────────────────────────────
export class ArcOfEllipseHandler extends DefaultHandler {
  readonly toolName = 'DSH_ArcOfEllipse'
  protected readonly states = 4
  private centerPoint: XY = [0, 0]; private axisPoint: XY = [0, 0]
  private secondRadius = 0; private startAngle = 0; private arcAngle = 0; private valid = true
  private ellipseGeoId = SK.GEO_UNDEF
  crosshair() { return 'Sketcher_Pointer_Create_ArcOfEllipse' }
  hints() { return [this.hint(['%1 pick ellipse center point', '%1 pick axis point', '%1 pick arc start point', '%1 pick arc end point'][Math.min(this.state, 3)], [LMB])] }
  private firstRadius() { return len(sub(this.centerPoint, this.axisPoint)) }
  private firstAxis() { return normalize(sub(this.axisPoint, this.centerPoint)) }
  private secondAxis() { return perp(this.firstAxis()) }
  protected update(p: XY) {
    this.valid = true
    if (this.state === 0) { this.centerPoint = p; this.drawPositionAtCursor(p); this.seekAndRender(this.sug[0], p, [0, 0]) }
    else if (this.state === 1) {
      this.axisPoint = p
      if (len(sub(this.axisPoint, this.centerPoint)) < CONFUSION) { this.valid = false; this.drawShape(); return }
      this.clearCursorText()
      this.seekAndRender(this.sug[1], p, sub(p, this.centerPoint), 'curve')
    } else if (this.state === 2) {
      const a = this.firstRadius(), ad = this.firstAxis(), bd = this.secondAxis(), d = sub(p, this.centerPoint)
      const dp: XY = [dot(d, ad), dot(d, bd)]
      const cosT = Math.max(-1, Math.min(1, dp[0] / a)), sinT = Math.sqrt(Math.max(0, 1 - cosT * cosT))
      if (sinT < CONFUSION) { this.valid = false; this.drawShape(); return }
      this.secondRadius = Math.abs(dp[1]) / sinT
      if (Math.abs(dp[1]) < CONFUSION) { this.valid = false; this.drawShape(); return }
      this.startAngle = Math.atan2(dp[1] / this.secondRadius, dp[0] / a)
      this.clearCursorText()
      this.seekAndRender(this.sug[2], p, [0, 0])
    } else if (this.state === 3) {
      const ad = this.firstAxis(), bd = this.secondAxis(), d = sub(p, this.centerPoint)
      const dp: XY = [dot(d, ad), dot(d, bd)]
      const angle1 = Math.atan2(dp[1] / this.secondRadius, dp[0] / this.firstRadius()) - this.startAngle
      const angle2 = angle1 + (angle1 < 0 ? 2 : -2) * Math.PI
      this.arcAngle = Math.abs(angle1 - this.arcAngle) < Math.abs(angle2 - this.arcAngle) ? angle1 : angle2
      if (Math.abs(this.arcAngle) < CONFUSION) { this.valid = false; this.drawShape(); return }
      this.clearCursorText()
      this.seekAndRender(this.sug[3], p, [0, 0])
    }
    this.drawShape()
  }
  private ellipse() {
    const r1 = this.firstRadius(), r2 = this.secondRadius, big = r1 >= r2
    const est = big ? this.startAngle : this.startAngle - Math.PI / 2
    return { majorRadius: Math.max(r1, r2), minorRadius: Math.min(r1, r2), majorAxis: big ? this.firstAxis() : this.secondAxis(),
      startAngle: this.arcAngle > 0 ? est : this.arcAngle + est, endAngle: this.arcAngle > 0 ? this.arcAngle + est : est }
  }
  protected createShape() {
    this.shapeGeometry = []
    if (!this.valid) return
    const cm = this.isConstructionMode()
    if (this.state === 1) { this.shapeGeometry.push(makeEllipse(this.centerPoint, this.firstAxis(), this.firstRadius(), this.firstRadius() / 2, cm)); return }
    const e = this.ellipse()
    if (this.state === 2) this.shapeGeometry.push(makeEllipse(this.centerPoint, e.majorAxis, e.majorRadius, e.minorRadius, cm))
    else this.shapeGeometry.push(makeArcOfEllipse(this.centerPoint, e.majorAxis, e.majorRadius, e.minorRadius, e.startAngle, e.endAngle, cm))
  }
  protected canGoToNextMode() { return this.valid }
  protected executeCommands() {
    S.openCommand('Add sketch arc of ellipse')
    this.ellipseGeoId = S.highestCurveIndex() + 1
    this.createShape()
    this.addShape()
    exposeInternalGeometry(this.ellipseGeoId)
    S.commitCommand()
  }
  protected generateAutoConstraints() {
    const id = this.ellipseGeoId, [ac1, ac2, ac3, ac4] = this.sug, ccw = this.arcAngle > 0
    this.onElement(ac1, id, MID); this.onElement(ac2, id, NONE)
    this.onElement(ac3, id, ccw ? START : END); this.onElement(ac4, id, ccw ? END : START)
    this.removeRedundantAutoConstraints()
  }
  protected createAutoConstraints() { this.createGeneratedAutoConstraints(true); for (const s of this.sug.slice(0, 4)) s.length = 0 }
}

// ── Arc of hyperbola (DrawSketchHandlerArcOfHyperbola.h) ─────────────────────────────────────────────────────────
export class ArcOfHyperbolaHandler extends DefaultHandler {
  readonly toolName = 'DSH_ArcOfHyperbola'
  protected readonly states = 4
  private centerPoint: XY = [0, 0]; private axisPoint: XY = [0, 0]
  private minorRadius = 0; private startAngle = 0; private endAngle = 0; private valid = true
  private hyperbolaGeoId = SK.GEO_UNDEF
  crosshair() { return 'Sketcher_Pointer_Create_ArcOfHyperbola' }
  hints() { return [this.hint(['%1 pick center point', '%1 pick axis point', '%1 pick arc start point', '%1 pick arc end point'][Math.min(this.state, 3)], [LMB])] }
  private majorRadius() { return len(sub(this.centerPoint, this.axisPoint)) }
  private majorAxis() { return normalize(sub(this.axisPoint, this.centerPoint)) }
  private minorAxis() { return perp(this.majorAxis()) }
  private arcAngle() { return this.endAngle - this.startAngle }
  protected update(p: XY) {
    this.valid = true
    if (this.state === 0) { this.centerPoint = p; this.drawPositionAtCursor(p); this.seekAndRender(this.sug[0], p, [0, 0]) }
    else if (this.state === 1) {
      this.axisPoint = p
      if (len(sub(this.axisPoint, this.centerPoint)) < CONFUSION) { this.valid = false; this.drawShape(); return }
      this.clearCursorText()
      this.seekAndRender(this.sug[1], p, [0, 0], 'curve')
    } else if (this.state === 2) {
      const a = this.majorRadius(), d = sub(p, this.centerPoint), dp: XY = [dot(d, this.majorAxis()), dot(d, this.minorAxis())]
      if (Math.abs(dp[1]) < CONFUSION) { this.valid = false; this.drawShape(); return }
      const denom = (dp[0] * dp[0]) / (a * a) - 1
      if (denom < CONFUSION) { this.valid = false; this.drawShape(); return }
      this.minorRadius = Math.sqrt((dp[1] * dp[1]) / denom)
      this.startAngle = Math.atanh((dp[1] * a) / (dp[0] * this.minorRadius))
      this.drawPositionAtCursor(p)
      this.seekAndRender(this.sug[2], p, [0, 0])
    } else if (this.state === 3) {
      const d = sub(p, this.centerPoint), dp: XY = [dot(d, this.majorAxis()), dot(d, this.minorAxis())]
      if (Math.abs((dp[1] * this.majorRadius()) / (dp[0] * this.minorRadius)) > 1) { this.valid = false; this.drawShape(); return }
      this.endAngle = Math.atanh((dp[1] * this.majorRadius()) / (dp[0] * this.minorRadius))
      if (Math.abs(this.arcAngle()) < CONFUSION) { this.valid = false; this.drawShape(); return }
      this.drawPositionAtCursor(p)
      this.seekAndRender(this.sug[3], p, [0, 0])
    }
    this.drawShape()
  }
  protected createShape() {
    this.shapeGeometry = []
    if (!this.valid) return
    const cm = this.isConstructionMode()
    if (this.state === 1) this.shapeGeometry.push(this.line(this.centerPoint, this.axisPoint))
    else if (this.state === 2 && Math.abs(this.startAngle) > CONFUSION)
      this.shapeGeometry.push(makeArcOfHyperbola(this.centerPoint, this.majorAxis(), this.majorRadius(), this.minorRadius, this.startAngle, -this.startAngle, cm))
    else if (this.state >= 3)
      this.shapeGeometry.push(makeArcOfHyperbola(this.centerPoint, this.majorAxis(), this.majorRadius(), this.minorRadius, this.startAngle, this.endAngle, cm))
  }
  protected canGoToNextMode() { return this.valid }
  protected executeCommands() {
    S.openCommand('Add sketch arc of hyperbola')
    this.hyperbolaGeoId = S.highestCurveIndex() + 1
    this.createShape()
    this.addShape()
    exposeInternalGeometry(this.hyperbolaGeoId)
    S.commitCommand()
  }
  protected generateAutoConstraints() {
    const id = this.hyperbolaGeoId, [ac1, ac2, ac3, ac4] = this.sug, up = this.arcAngle() > 0
    this.onElement(ac1, id, MID); this.onElement(ac2, id, NONE)
    this.onElement(ac3, id, up ? START : END); this.onElement(ac4, id, up ? END : START)
    this.removeRedundantAutoConstraints()
  }
  protected createAutoConstraints() { this.createGeneratedAutoConstraints(true); for (const s of this.sug.slice(0, 4)) s.length = 0 }
}

// ── Arc of parabola (DrawSketchHandlerArcOfParabola.h): focus, vertex, then the two ends ─────────────────────────
export class ArcOfParabolaHandler extends DefaultHandler {
  readonly toolName = 'DSH_ArcOfParabola'
  protected readonly states = 4
  private centerPoint: XY = [0, 0]; private focusPoint: XY = [0, 0]
  private startPoint = 0; private endPoint = 0; private valid = true
  private parabolaGeoId = SK.GEO_UNDEF
  crosshair() { return 'Sketcher_Pointer_Create_ArcOfParabola' }
  hints() { return [this.hint(['%1 pick focus point', '%1 pick axis point', '%1 pick starting point', '%1 pick end point'][Math.min(this.state, 3)], [LMB])] }
  private axis() { return normalize(sub(this.focusPoint, this.centerPoint)) }
  private focal() { return len(sub(this.focusPoint, this.centerPoint)) }
  protected update(p: XY) {
    this.valid = true
    if (this.state === 0) { this.focusPoint = p; this.drawPositionAtCursor(p); this.seekAndRender(this.sug[0], p, [0, 0]) }
    else if (this.state === 1) {
      this.centerPoint = p
      if (len(sub(this.centerPoint, this.focusPoint)) < CONFUSION) { this.valid = false; this.drawShape(); return }
      this.clearCursorText()
      this.seekAndRender(this.sug[1], p, [0, 0])
    } else if (this.state === 2) {
      this.startPoint = dot(sub(p, this.centerPoint), perp(this.axis()))
      this.drawPositionAtCursor(p)
      this.seekAndRender(this.sug[2], p, [0, 0])
    } else if (this.state === 3) {
      this.endPoint = dot(sub(p, this.centerPoint), perp(this.axis()))
      if (Math.abs(this.endPoint - this.startPoint) < CONFUSION) { this.valid = false; this.drawShape(); return }
      this.drawPositionAtCursor(p)
      this.seekAndRender(this.sug[3], p, [0, 0])
    }
    this.drawShape()
  }
  protected createShape() {
    this.shapeGeometry = []
    if (!this.valid) return
    const cm = this.isConstructionMode()
    if (this.state === 1) this.shapeGeometry.push(this.line(this.focusPoint, this.centerPoint))
    else if (this.state === 2 && Math.abs(this.startPoint) > CONFUSION)
      this.shapeGeometry.push(makeArcOfParabola(this.axis(), this.centerPoint, this.focal(), this.startPoint, -this.startPoint, cm))
    else if (this.state >= 3)
      this.shapeGeometry.push(makeArcOfParabola(this.axis(), this.centerPoint, this.focal(), this.startPoint, this.endPoint, cm))
  }
  protected canGoToNextMode() { return this.valid }
  protected executeCommands() {
    S.openCommand('Add sketch arc of parabola')
    this.parabolaGeoId = S.highestCurveIndex() + 1
    this.createShape()
    this.addShape()
    exposeInternalGeometry(this.parabolaGeoId)
    S.commitCommand()
  }
  protected generateAutoConstraints() {
    const id = this.parabolaGeoId, [ac1, ac2, ac3, ac4] = this.sug, up = this.startPoint < this.endPoint
    this.onElement(ac1, id + 1, START) // the focus point exposeInternalGeometry added
    this.onElement(ac2, id, MID)
    this.onElement(ac3, id, up ? START : END); this.onElement(ac4, id, up ? END : START)
    this.removeRedundantAutoConstraints()
  }
  protected createAutoConstraints() { this.createGeneratedAutoConstraints(true); for (const s of this.sug.slice(0, 4)) s.length = 0 }
}

// ── B-spline by control points (DrawSketchHandlerBSpline.h, ControlPoints) ───────────────────────────────────────
/** Each click a construction circle at the pole (the first weighted 1, the others equal to it), auto-constraints on its
 *  centre; the right button (or Esc) or a click back on the first pole ends it: the B-spline, its poles aligned to the
 *  circles (its ends to what the first and last circle were tied to), the knot points (exposeInternalGeometry).
 *  U and J raise and lower the degree (3), R takes back the last pole, F toggles periodic. */
export class BSplineHandler extends DefaultHandler {
  readonly toolName = 'DSH_BSpline'
  protected readonly states = 2
  protected readonly methods = 1
  private splineDegree = 3
  private prevCursor: XY = [0, 0]
  private points: XY[] = []
  private geoIds: number[] = []
  private sugBackup: AutoConstraint[][] = []
  constructor(private periodic = false) { super() }
  crosshair() { return this.periodic ? 'Sketcher_Pointer_Create_Periodic_BSpline' : 'Sketcher_Pointer_Create_BSpline' }
  hints() {
    const sw = this.hint('%1 switch to knots', ['M']), per = this.hint('%1 toggle periodic', ['F']), deg = this.hint('%1/%2 increase/decrease degree', ['U', 'J'])
    if (this.state === 0) return [this.hint('%1 pick first control point', [LMB]), sw, per, deg]
    return [this.hint('%1 pick next point', [LMB]), this.hint('%1 finish', [RMB]), sw, per, this.hint('%1 undo last point', ['R']), deg]
  }
  activated() { super.activated(); S.openCommand('Add Sketch B-Spline') }
  deactivated() { super.deactivated(); S.abortCommand() }
  private lastPoint(): XY { return this.points.length ? this.points[this.points.length - 1] : [0, 0] }
  getStartPointOfCurrentSegment() { return null }
  protected update(p: XY) {
    this.prevCursor = p
    if (this.state === 0) { this.drawPositionAtCursor(p); this.seekAndRender(this.sug[0], p, [0, 0]) }
    else if (this.state === 1) { this.clearCursorText(); this.drawShape(); this.seekAndRender(this.sug[1], p, [0, 0]) }
  }
  /** addGeometry: the pole's circle (radius 10, construction), Weight 1 on the first, Equal to the first after. */
  private addPos(): boolean {
    this.points.push(this.prevCursor)
    const geoId = S.highestCurveIndex() + 1
    this.geoIds.push(geoId)
    S.addGeometry({ type: 'Circle', center: this.prevCursor, radius: 10, construction: true })
    if (this.points.length === 1) S.addConstraint(constraint('Weight', geoId, NONE, SK.GEO_UNDEF, NONE, SK.GEO_UNDEF, NONE, 1.0))
    else S.addConstraint(constraint('Equal', this.geoIds[0], NONE, geoId))
    return true
  }
  protected canGoToNextMode() {
    if (this.state === 0) {
      this.addPos()
      this.onElement(this.sug[0], this.geoIds[this.geoIds.length - 1], MID)
      this.commitAutos()
      S.solve()
      return true
    }
    if (this.points.length && len(sub(this.prevCursor, this.lastPoint())) < CONFUSION) return false
    let closed = false
    for (const ac of this.sug[1]) {
      if (ac.type !== 'Coincident') continue
      if (ac.geoId === this.geoIds[0]) closed = true
      else if (SK.coincidentPoints(S.getConstraints(), ac.geoId, ac.posId).has(this.geoIds[0])) closed = true
    }
    if (closed) { if (this.periodic) return true }
    else S.setAngleSnapping(true, this.lastPoint())
    this.addPos()
    this.onElement(this.sug[1], this.geoIds[this.geoIds.length - 1], MID)
    this.sugBackup.push([...this.sug[1]])
    this.sug[1].length = 0
    this.commitAutos()
    S.solve()
    return closed
  }
  /** The auto-constraints generated as each pole is placed: FreeCAD keeps them (AutoConstraints) until the B-spline is
   *  made and adds them then. */
  private pendingAutos: Constraint[] = []
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
    if (!pressed && (key === 'U' || key === 'J')) {
      this.splineDegree = key === 'U' ? this.splineDegree + 1 : Math.max(1, this.splineDegree - 1)
      if (this.state === 1) this.drawShape()
      return true
    }
    if (!pressed && key === 'R' && this.state === 1) { this.undoLastPoint(); return true }
    if (!pressed && key === 'F') { this.periodic = !this.periodic; S.applyCursor(); if (this.state === 1) this.drawShape(); return true }
    if (key === 'M') return true
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
    this.geoIds.pop(); this.points.pop(); this.sugBackup.pop()
    this.update(this.prevCursor)
  }
  protected createShape(onlyOutline: boolean) {
    this.shapeGeometry = []
    const pts = [...this.points]
    const l = len(sub(this.prevCursor, this.lastPoint()))
    if (onlyOutline && (!pts.length || l >= CONFUSION)) pts.push(this.prevCursor)
    if (pts.length < 2) return
    const n = pts.length, maxDegree = n - (this.periodic ? 0 : 1), degree = Math.min(maxDegree, this.splineDegree)
    let knots: number[], mults: number[]
    if (!this.periodic) {
      knots = Array.from({ length: n - degree + 1 }, (_, i) => i)
      mults = knots.map(() => 1); mults[0] = degree + 1; mults[mults.length - 1] = degree + 1
    } else {
      knots = Array.from({ length: n + 1 }, (_, i) => i)
      mults = knots.map(() => 1)
    }
    const g: Geo = { type: 'BSplineCurve', poles: pts, weights: pts.map(() => 1), knots, mults, degree, periodic: this.periodic }
    this.shapeGeometry.push(this.isConstructionMode() ? { ...g, construction: true } : g)
  }
  protected executeCommands() {
    if (this.geoIds.length === 1) { S.abortCommand(); return }
    this.createShape(false)
    this.addShape()
    const bsp = S.highestCurveIndex()
    if (!this.periodic) {
      // what the first and last pole were tied to now ties the B-spline's ends
      const list = S.getConstraints().map((c) => {
        if (c.first === this.geoIds[0] && c.firstPos === MID) return { ...c, first: bsp, firstPos: START as PointPos }
        if (c.first === this.geoIds[this.geoIds.length - 1] && c.firstPos === MID) return { ...c, first: bsp, firstPos: END as PointPos }
        return c
      })
      S.setConstraints(list)
    }
    S.addConstraint(this.geoIds.map((g, i) => alignmentConstraint('BSplineControlPoint', this.geoIds[0] + i, MID, bsp, i)))
    exposeInternalGeometry(bsp)
    S.commitCommand()
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
    this.splineDegree = 3
    this.geoIds = []; this.points = []; this.sugBackup = []; this.pendingAutos = []
  }
}

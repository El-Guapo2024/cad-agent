// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Sketcher/Gui/DrawSketchHandlerEllipse.h: 2022 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/DrawSketchHandlerArcOfEllipse.h: 2022 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/DrawSketchHandlerArcOfHyperbola.h: 2022 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/DrawSketchHandlerArcOfParabola.h: 2022 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/DrawSketchHandlerBSpline.h: 2022 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/DrawSketchDefaultHandler.h: 2022 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/DrawSketchController.h: 2023 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/DrawSketchDefaultWidgetController.h: 2023 Abdullah Tahiri
//   src/Mod/Sketcher/App/SketchObjectGeometry.cpp: 2008 Jürgen Riegel
// The Sketcher's conic and B-spline tools: the ellipse by its centre or by its axis ends (Sketcher_CreateEllipseByCenter,
// Sketcher_CreateEllipseBy3Points), the arcs of ellipse, hyperbola and parabola, and the B-spline by its control points,
// open or periodic (Sketcher_CreateBSpline, Sketcher_CreatePeriodicBSpline), each making the geometry, the internal
// geometry (exposeInternalGeometry) and the auto-constraints FreeCAD's tool makes for the same clicks; the conics' on-view
// parameters (DSHEllipseController, with its Tool Parameters box, and the arcs' DrawSketchControllers) and the
// constraints the values set make.
import type { Geo, XY } from './solver'
import * as SK from './sketch'
import { type Constraint, type PointPos, NONE, START, END, MID, constraint, alignmentConstraint } from './sketch'
import * as S from './sketcher'
import * as CV from './sketchcurves'
import { DefaultHandler, type AutoConstraint } from './sketchtools'
import { type Controller, type OvpSpec, OVP, f6, constraintToAttachment, RT_PNT_ID, V_AXIS_ID, H_AXIS_ID } from './sketchovp'

const CONFUSION = 1e-7, PCONFUSION = CONFUSION * 0.01
const sub = (a: XY, b: XY): XY => [a[0] - b[0], a[1] - b[1]], add = (a: XY, b: XY): XY => [a[0] + b[0], a[1] + b[1]]
const mul = (a: XY, k: number): XY => [a[0] * k, a[1] * k], len = (a: XY) => Math.hypot(a[0], a[1])
const dot = (a: XY, b: XY) => a[0] * b[0] + a[1] * b[1]
/** Base::Vector2d::Angle. */
const angleOf = (a: XY) => Math.atan2(a[1], a[0])
/** SketcherGui::areCollinear. */
const areCollinear = (a: XY, b: XY, c: XY) => Math.abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) < CONFUSION
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

/** Each constraint a controller's addConstraints adds is a Python addConstraint, which solves the sketch at once
 *  (SketchObjectPy::addConstraint): the next one is added to the geometry as that solve left it. */
const addSolved = (c: Constraint) => { S.addConstraint(c); S.solve() }
const attachSolved = (...a: Parameters<typeof constraintToAttachment>) => { constraintToAttachment(...a); S.solve() }

// ── Ellipse (DrawSketchHandlerEllipse.h): Center, then ThreeRim ("Axis endpoints") ──────────────────────────────
/** DSHEllipseController: a DrawSketchDefaultWidgetController with the construction method's combo box; the centre's X
 *  and Y, the first radius and its angle, then the second radius (Center); or the three rim points' X and Y (ThreeRim). */
export class EllipseHandler extends DefaultHandler {
  readonly toolName = 'DSH_Ellipse'
  protected readonly states = 3
  protected readonly methods = 2
  protected readonly autoConstraintSize = 3
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
      this.ctl.drawPositionAtCursor(p)
      if (this.method === 0) { this.centerPoint = p; this.seekAndRender(this.sug[0], p, [0, 0]) }
      else { this.apoapsis = p; this.seekAndRender(this.sug[0], p, [0, 0], 'curve') }
    } else if (this.state === 1) {
      this.periapsis = p
      this.calculateMajorAxisParameters()
      this.drawShape()
      if (this.method === 0) this.ctl.drawDoubleAtCursor(p, this.firstRadius); else this.ctl.drawPositionAtCursor(p)
      this.seekAndRender(this.sug[1], p, [0, 0], 'curve')
    } else if (this.state === 2) {
      this.calculateThroughPointMinorAxisParameters(p)
      this.drawShape()
      if (this.method === 0) this.ctl.drawWidthHeightAtCursor(p, this.firstRadius, this.secondRadius); else this.ctl.drawPositionAtCursor(p)
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
  // the controller's specialisations
  isWidgetVisible() { return true }
  toolWidgetText() { return 'Ellipse Parameters' }
  toolIcon() { return 'Sketcher_CreateEllipseByCenter' }
  ovpSpec(): OvpSpec { return { ovps: this.method === 0 ? 5 : 6, widget: { parameters: 0, checkboxes: 0, comboboxes: 1, lineEdits: 0 }, firstComboIsMethod: true } }
  ovpState(i: number) { return i < 2 ? 0 : i < 4 ? 1 : 2 }
  configureToolWidget(c: Controller) {
    if (!c.init) {
      c.setComboboxElements(0, ['Center', 'Axis endpoints'])
      const k = this.isConstructionMode() ? '_Constr' : ''
      c.setComboboxItemIcon(0, 0, `Sketcher_CreateEllipseByCenter${k}`); c.setComboboxItemIcon(0, 1, `Sketcher_CreateEllipse_3points${k}`)
    }
    const o = c.onViewParameters
    o[OVP.First].setLabelType('DISTANCEX'); o[OVP.Second].setLabelType('DISTANCEY')
    if (this.method === 1) {
      o[OVP.Third].setLabelType('DISTANCEX'); o[OVP.Fourth].setLabelType('DISTANCEY')
      o[OVP.Fifth].setLabelType('DISTANCEX'); o[OVP.Sixth].setLabelType('DISTANCEY')
    } else {
      o[OVP.Third].setLabelType('RADIUS', 'Dimensioning'); o[OVP.Fourth].setLabelType('ANGLE', 'Dimensioning'); o[OVP.Fifth].setLabelType('RADIUS', 'Dimensioning')
    }
  }
  doEnforceControlParameters(c: Controller, p: XY): XY {
    const o = c.onViewParameters
    let [x, y] = p
    if (this.state === 0) {
      if (o[OVP.First].isSet) x = o[OVP.First].getValue()
      if (o[OVP.Second].isSet) y = o[OVP.Second].getValue()
    } else if (this.state === 1) {
      const third = o[OVP.Third], fourth = o[OVP.Fourth]
      if (this.method === 0) {
        let dir = sub([x, y], this.centerPoint)
        if (len(dir) < CONFUSION) dir = [1, dir[1]] // if direction null, default to (1, 0)
        let length = len(dir)
        if (third.isSet) {
          length = third.getValue()
          if (length < CONFUSION && third.hasFinishedEditing) { c.unsetOnViewParameter(third); return [x, y] }
          ;[x, y] = add(this.centerPoint, mul(normalize(dir), length))
        }
        if (fourth.isSet) { const a = (fourth.getValue() * Math.PI) / 180; x = this.centerPoint[0] + Math.cos(a) * length; y = this.centerPoint[1] + Math.sin(a) * length }
      } else {
        if (third.isSet) x = third.getValue()
        if (fourth.isSet) y = fourth.getValue()
        if (third.hasFinishedEditing && fourth.hasFinishedEditing && len(sub([x, y], this.apoapsis)) < CONFUSION) { c.unsetOnViewParameter(third); c.unsetOnViewParameter(fourth) }
      }
    } else if (this.state === 2) {
      const fifth = o[OVP.Fifth]
      if (this.method === 0) {
        if (fifth.isSet) {
          // (periapsis - centerPoint).Perpendicular(true): clockwise
          const d = sub(this.periapsis, this.centerPoint)
          ;[x, y] = add(this.centerPoint, mul(normalize([d[1], -d[0]]), fifth.getValue()))
        }
      } else {
        const sixth = o[OVP.Sixth]
        if (fifth.isSet) x = fifth.getValue()
        if (sixth.isSet) y = sixth.getValue()
        if (fifth.hasFinishedEditing && sixth.hasFinishedEditing && areCollinear(this.apoapsis, this.periapsis, [x, y])) { c.unsetOnViewParameter(fifth); c.unsetOnViewParameter(sixth) }
      }
    }
    return [x, y]
  }
  adaptParameters(c: Controller, p: XY) {
    const o = c.onViewParameters
    const xy = (a: number, b: number) => {
      if (!o[a].isSet) c.setOnViewParameterValue(a, p[0])
      if (!o[b].isSet) c.setOnViewParameterValue(b, p[1])
      const sameSign = p[0] * p[1] > 0
      o[a].setLabelAutoDistanceReverse(!sameSign); o[b].setLabelAutoDistanceReverse(sameSign)
      o[a].setPoints([0, 0], p); o[b].setPoints([0, 0], p)
    }
    if (this.state === 0) xy(OVP.First, OVP.Second)
    else if (this.state === 1) {
      if (this.method === 0) {
        const vec = sub(p, this.centerPoint)
        if (!o[OVP.Third].isSet) c.setOnViewParameterValue(OVP.Third, len(vec))
        if (!o[OVP.Fourth].isSet) c.setOnViewParameterValue(OVP.Fourth, len(vec) > 0 ? (angleOf(vec) * 180) / Math.PI : 0, 'Angle')
        o[OVP.Third].setPoints(this.centerPoint, p)
        o[OVP.Fourth].setPoints(this.centerPoint, [0, 0])
        o[OVP.Fourth].setLabelRange(angleOf(vec))
      } else xy(OVP.Third, OVP.Fourth)
    } else if (this.state === 2) {
      if (this.method === 0) {
        if (!o[OVP.Fifth].isSet) c.setOnViewParameterValue(OVP.Fifth, len(this.secondAxis))
        o[OVP.Fifth].setPoints(this.centerPoint, add(this.centerPoint, this.secondAxis))
      } else xy(OVP.Fifth, OVP.Sixth)
    }
  }
  computeNextDrawSketchHandlerMode(c: Controller) {
    const o = c.onViewParameters
    if (this.state === 0) { if (o[OVP.First].hasFinishedEditing && o[OVP.Second].hasFinishedEditing) this.setNextState(1) }
    else if (this.state === 1) { if (o[OVP.Third].hasFinishedEditing && o[OVP.Fourth].hasFinishedEditing) this.setNextState(2) }
    else if (this.state === 2) {
      if (this.method === 0) { if (o[OVP.Fifth].hasFinishedEditing) this.setNextState(this.states) }
      else if (o[OVP.Fifth].hasFinishedEditing && o[OVP.Sixth].hasFinishedEditing) this.setNextState(this.states)
    }
  }
  /** DSHEllipseController::addConstraints, before the auto-constraints are diagnosed (AutoConstraints is empty, so each
   *  parameter set goes in): the centre's position, the first radius and its angle on the axis line it gave (the
   *  internal major or minor axis), the second radius. No constraint for an ellipse by its axis ends. */
  addConstraints(c: Controller) {
    if (this.method !== 0) return
    const o = c.onViewParameters
    const x0set = o[OVP.First].isSet, y0set = o[OVP.Second].isSet
    if (this.shapeGeometry[0]?.type === 'Ellipse') {
      const firstCurve = this.ellipseGeoId
      const x0 = o[OVP.First].getValue(), y0 = o[OVP.Second].getValue(), angle = (o[OVP.Fourth].getValue() * Math.PI) / 180
      let firstLine = firstCurve + 1, secondLine = firstCurve + 2 // the major axis, then the minor
      if (this.firstRadius < this.secondRadius) [firstLine, secondLine] = [secondLine, firstLine]
      if (x0set) attachSolved([firstCurve, MID], V_AXIS_ID, x0)
      if (y0set) attachSolved([firstCurve, MID], H_AXIS_ID, y0)
      if (o[OVP.Third].isSet) addSolved(constraint('Distance', firstCurve, MID, firstLine, START, SK.GEO_UNDEF, NONE, f6(this.firstRadius)))
      if (o[OVP.Fourth].isSet) addSolved(constraint('Angle', firstLine, NONE, SK.GEO_UNDEF, NONE, SK.GEO_UNDEF, NONE, f6(angle)))
      if (o[OVP.Fifth].isSet) addSolved(constraint('Distance', firstCurve, MID, secondLine, START, SK.GEO_UNDEF, NONE, f6(this.secondRadius)))
    } else { // it is a circle: its position from the widget's (unused) parameters, as FreeCAD's reads them
      const firstCurve = S.highestCurveIndex()
      if (x0set) attachSolved([firstCurve, MID], V_AXIS_ID, c.getParameter(OVP.First))
      if (y0set) attachSolved([firstCurve, MID], H_AXIS_ID, c.getParameter(OVP.Second))
      if (o[OVP.Third].isSet) addSolved(constraint('Radius', firstCurve, NONE, SK.GEO_UNDEF, NONE, SK.GEO_UNDEF, NONE, f6(this.firstRadius)))
    }
  }
}

// ── Arc of ellipse (DrawSketchHandlerArcOfEllipse.h) ─────────────────────────────────────────────────────────────
/** DSHArcOfEllipseController: a DrawSketchController (no widget) with seven on-view parameters: the centre's X and Y,
 *  the first radius and its angle, the second radius and the start angle, the arc's angle. */
export class ArcOfEllipseHandler extends DefaultHandler {
  readonly toolName = 'DSH_ArcOfEllipse'
  protected readonly states = 4
  protected readonly autoConstraintSize = 4
  private centerPoint: XY = [0, 0]; private axisPoint: XY = [0, 0]
  private secondRadius = 0; private startAngle = 0; private arcAngle = 0; private valid = true; private secondRadiusSet = false
  private ellipseGeoId = SK.GEO_UNDEF
  crosshair() { return 'Sketcher_Pointer_Create_ArcOfEllipse' }
  hints() { return [this.hint(['%1 pick ellipse center point', '%1 pick axis point', '%1 pick arc start point', '%1 pick arc end point'][Math.min(this.state, 3)], [LMB])] }
  private firstRadius() { return len(sub(this.centerPoint, this.axisPoint)) }
  private firstAxis() { return normalize(sub(this.axisPoint, this.centerPoint)) }
  private secondAxis() { return perp(this.firstAxis()) }
  protected update(p: XY) {
    this.valid = true
    if (this.state === 0) { this.centerPoint = p; this.ctl.drawPositionAtCursor(p); this.seekAndRender(this.sug[0], p, [0, 0]) }
    else if (this.state === 1) {
      this.axisPoint = p
      if (len(sub(this.axisPoint, this.centerPoint)) < CONFUSION) { this.valid = false; this.drawShape(); return }
      this.ctl.drawDirectionAtCursor(p, this.centerPoint)
      this.seekAndRender(this.sug[1], p, sub(p, this.centerPoint), 'curve')
    } else if (this.state === 2) {
      const a = this.firstRadius(), ad = this.firstAxis(), bd = this.secondAxis(), d = sub(p, this.centerPoint)
      const dp: XY = [dot(d, ad), dot(d, bd)]
      if (!this.secondRadiusSet) {
        const cosT = Math.max(-1, Math.min(1, dp[0] / a)), sinT = Math.sqrt(Math.max(0, 1 - cosT * cosT))
        if (sinT < CONFUSION) { this.valid = false; this.drawShape(); return }
        this.secondRadius = Math.abs(dp[1]) / sinT
        if (Math.abs(dp[1]) < CONFUSION) { this.valid = false; this.drawShape(); return }
      }
      this.startAngle = Math.atan2(dp[1] / this.secondRadius, dp[0] / a)
      this.ctl.drawWidthHeightAtCursor(p, this.firstRadius(), this.secondRadius)
      this.seekAndRender(this.sug[2], p, [0, 0])
    } else if (this.state === 3) {
      const ad = this.firstAxis(), bd = this.secondAxis(), d = sub(p, this.centerPoint)
      const dp: XY = [dot(d, ad), dot(d, bd)]
      const angle1 = Math.atan2(dp[1] / this.secondRadius, dp[0] / this.firstRadius()) - this.startAngle
      const angle2 = angle1 + (angle1 < 0 ? 2 : -2) * Math.PI
      this.arcAngle = Math.abs(angle1 - this.arcAngle) < Math.abs(angle2 - this.arcAngle) ? angle1 : angle2
      if (Math.abs(this.arcAngle) < CONFUSION) { this.valid = false; this.drawShape(); return }
      this.ctl.drawDoubleAtCursor(p, this.arcAngle, 'Angle')
      this.seekAndRender(this.sug[3], p, [0, 0])
    } else return
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
    else if (this.state >= 3) this.shapeGeometry.push(makeArcOfEllipse(this.centerPoint, e.majorAxis, e.majorRadius, e.minorRadius, e.startAngle, e.endAngle, cm))
  }
  protected canGoToNextMode() { return this.valid }
  protected angleSnappingControl() { S.setAngleSnapping(false) }
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
  // the controller's specialisations
  toolIcon() { return 'Sketcher_CreateElliptical_Arc' }
  ovpSpec(): OvpSpec { return { ovps: 7, widget: null, firstComboIsMethod: false } }
  ovpState(i: number) { return i < 6 ? Math.trunc(i / 2) : 3 }
  configureOnViewParameters(c: Controller) {
    const o = c.onViewParameters
    o[OVP.First].setLabelType('DISTANCEX'); o[OVP.Second].setLabelType('DISTANCEY')
    o[OVP.Third].setLabelType('RADIUS', 'Dimensioning'); o[OVP.Fourth].setLabelType('ANGLE', 'Dimensioning')
    o[OVP.Fifth].setLabelType('RADIUS', 'Dimensioning'); o[OVP.Sixth].setLabelType('ANGLE', 'Dimensioning')
    o[OVP.Seventh].setLabelType('ANGLE', 'Dimensioning')
  }
  doEnforceControlParameters(c: Controller, p: XY): XY {
    this.update(p) // the member variables up to date before the parameters are enforced
    const o = c.onViewParameters
    let [x, y] = p
    if (this.state === 0) {
      if (o[OVP.First].isSet) x = o[OVP.First].getValue()
      if (o[OVP.Second].isSet) y = o[OVP.Second].getValue()
    } else if (this.state === 1) {
      const radiusP = o[OVP.Third], angleP = o[OVP.Fourth]
      if (!radiusP.isSet && !angleP.isSet) return p
      let r = this.firstRadius(), axis = this.firstAxis()
      if (radiusP.isSet) {
        r = radiusP.getValue()
        if (r < CONFUSION && radiusP.hasFinishedEditing) { c.unsetOnViewParameter(radiusP); return p }
      }
      if (angleP.isSet) { const a = (angleP.getValue() * Math.PI) / 180; axis = [Math.cos(a), Math.sin(a)] }
      ;[x, y] = add(this.centerPoint, mul(axis, r))
    } else if (this.state === 2) {
      const radiusP = o[OVP.Fifth], startP = o[OVP.Sixth]
      if (!radiusP.isSet && !startP.isSet) return p
      let r2 = this.secondRadius, start = this.startAngle
      if (radiusP.isSet) {
        r2 = radiusP.getValue()
        this.secondRadius = r2
        this.secondRadiusSet = true
        if (r2 < CONFUSION && radiusP.hasFinishedEditing) { this.secondRadiusSet = false; c.unsetOnViewParameter(radiusP); return p }
      }
      if (startP.isSet) start = (startP.getValue() * Math.PI) / 180
      ;[x, y] = add(add(this.centerPoint, mul(this.firstAxis(), this.firstRadius() * Math.cos(start))), mul(this.secondAxis(), r2 * Math.sin(start)))
    } else if (this.state === 3) {
      const arcP = o[OVP.Seventh]
      if (!arcP.isSet) return p
      const arcAngle = (arcP.getValue() * Math.PI) / 180
      if (Math.abs(arcAngle) % (2 * Math.PI) < CONFUSION && arcP.hasFinishedEditing) { c.unsetOnViewParameter(arcP); return p }
      this.arcAngle = arcAngle // so that it does not flip past π, where the other way round is shorter
      const end = this.startAngle + arcAngle
      ;[x, y] = add(add(this.centerPoint, mul(this.firstAxis(), this.firstRadius() * Math.cos(end))), mul(this.secondAxis(), this.secondRadius * Math.sin(end)))
    }
    return [x, y]
  }
  adaptParameters(c: Controller, p: XY) {
    const o = c.onViewParameters
    if (this.state === 0) {
      if (!o[OVP.First].isSet) c.setOnViewParameterValue(OVP.First, p[0])
      if (!o[OVP.Second].isSet) c.setOnViewParameterValue(OVP.Second, p[1])
      const sameSign = p[0] * p[1] > 0
      o[OVP.First].setLabelAutoDistanceReverse(!sameSign); o[OVP.Second].setLabelAutoDistanceReverse(sameSign)
      o[OVP.First].setPoints([0, 0], p); o[OVP.Second].setPoints([0, 0], p)
    } else if (this.state === 1) {
      if (!o[OVP.Third].isSet) c.setOnViewParameterValue(OVP.Third, this.firstRadius())
      if (!o[OVP.Fourth].isSet) c.setOnViewParameterValue(OVP.Fourth, (angleOf(this.firstAxis()) * 180) / Math.PI, 'Angle')
      o[OVP.Third].setPoints(this.centerPoint, p)
      o[OVP.Fourth].setPoints(this.centerPoint, [0, 0])
      o[OVP.Fourth].setLabelRange(angleOf(this.firstAxis()))
    } else if (this.state === 2) {
      const radiusP = o[OVP.Fifth], startP = o[OVP.Sixth]
      if (!radiusP.isSet) c.setOnViewParameterValue(OVP.Fifth, this.valid ? this.secondRadius : 0)
      if (!startP.isSet) c.setOnViewParameterValue(OVP.Sixth, (this.startAngle * 180) / Math.PI, 'Angle')
      startP.setPoints(this.centerPoint, [0, 0])
      startP.setLabelStartAngle(angleOf(this.firstAxis()))
      startP.setLabelRange(this.startAngle)
      radiusP.setPoints(this.centerPoint, add(this.centerPoint, mul(this.secondAxis(), this.secondRadius)))
      if (!this.valid) radiusP.setPoints(this.centerPoint, this.centerPoint)
    } else if (this.state === 3) {
      const arcP = o[OVP.Seventh]
      if (!arcP.isSet) c.setOnViewParameterValue(OVP.Seventh, (this.arcAngle * 180) / Math.PI, 'Angle')
      arcP.setPoints(this.centerPoint, [0, 0])
      arcP.setLabelStartAngle(angleOf(this.firstAxis()) + this.startAngle)
      arcP.setLabelRange(this.arcAngle)
    }
  }
  computeNextDrawSketchHandlerMode(c: Controller) {
    const o = c.onViewParameters
    if (this.state === 0) { if (o[OVP.First].hasFinishedEditing && o[OVP.Second].hasFinishedEditing) this.setNextState(1) }
    else if (this.state === 1) { if (o[OVP.Third].hasFinishedEditing && o[OVP.Fourth].hasFinishedEditing) this.setNextState(2) }
    else if (this.state === 2) { if (o[OVP.Fifth].hasFinishedEditing && o[OVP.Sixth].hasFinishedEditing) this.setNextState(3) }
    else if (this.state === 3) { if (o[OVP.Seventh].hasFinishedEditing) this.setNextState(this.states) }
  }
  /** DSHArcOfEllipseController::addConstraints, with no diagnosis yet: the centre's position (on the origin when both
   *  are 0), the major and minor radii on the internal axis lines, the first axis's angle; not the arc's angles. */
  addConstraints(c: Controller) {
    const o = c.onViewParameters
    const firstCurve = this.ellipseGeoId, majorLine = firstCurve + 1, minorLine = firstCurve + 2
    const r1 = this.firstRadius(), isFirstMajor = r1 > this.secondRadius
    const majorRadius = Math.max(r1, this.secondRadius), minorRadius = Math.min(r1, this.secondRadius)
    const x0set = o[OVP.First].isSet, y0set = o[OVP.Second].isSet, firstAxisSet = o[OVP.Fourth].isSet
    const majorRadiusSet = isFirstMajor ? o[OVP.Third].isSet : o[OVP.Fifth].isSet
    const minorRadiusSet = isFirstMajor ? o[OVP.Fifth].isSet : o[OVP.Third].isSet
    if (x0set && y0set && len(this.centerPoint) <= CONFUSION) attachSolved([firstCurve, MID], RT_PNT_ID, 0)
    else {
      if (x0set) attachSolved([firstCurve, MID], V_AXIS_ID, this.centerPoint[0])
      if (y0set) attachSolved([firstCurve, MID], H_AXIS_ID, this.centerPoint[1])
    }
    if (majorRadiusSet) addSolved(constraint('Distance', majorLine, START, firstCurve, MID, SK.GEO_UNDEF, NONE, f6(majorRadius)))
    // the first line is constrained, not the major one: it is what the user gave
    if (firstAxisSet) addSolved(constraint('Angle', majorRadius === r1 ? majorLine : minorLine, NONE, SK.GEO_UNDEF, NONE, SK.GEO_UNDEF, NONE, f6(angleOf(this.firstAxis()))))
    if (minorRadiusSet) addSolved(constraint('Distance', minorLine, START, firstCurve, MID, SK.GEO_UNDEF, NONE, f6(minorRadius)))
  }
}

// ── Arc of hyperbola (DrawSketchHandlerArcOfHyperbola.h) ─────────────────────────────────────────────────────────
/** DSHArcOfHyperbolaController: seven on-view parameters: the centre's X and Y, the major radius and its angle, the
 *  minor radius and the (hyperbolic, unitless) start parameter, the arc's parameter span. */
export class ArcOfHyperbolaHandler extends DefaultHandler {
  readonly toolName = 'DSH_ArcOfHyperbola'
  protected readonly states = 4
  protected readonly autoConstraintSize = 4
  private centerPoint: XY = [0, 0]; private axisPoint: XY = [0, 0]
  private minorRadius = 0; private startAngle = 0; private endAngle = 0; private valid = true; private minorRadiusSet = false
  private hyperbolaGeoId = SK.GEO_UNDEF
  crosshair() { return 'Sketcher_Pointer_Create_ArcOfHyperbola' }
  hints() { return [this.hint(['%1 pick center point', '%1 pick axis point', '%1 pick arc start point', '%1 pick arc end point'][Math.min(this.state, 3)], [LMB])] }
  private majorRadius() { return len(sub(this.centerPoint, this.axisPoint)) }
  private majorAxis() { return normalize(sub(this.axisPoint, this.centerPoint)) }
  private minorAxis() { return perp(this.majorAxis()) }
  private arcAngle() { return this.endAngle - this.startAngle }
  protected update(p: XY) {
    this.valid = true
    if (this.state === 0) { this.centerPoint = p; this.ctl.drawPositionAtCursor(p); this.seekAndRender(this.sug[0], p, [0, 0]) }
    else if (this.state === 1) {
      this.axisPoint = p
      if (len(sub(this.axisPoint, this.centerPoint)) < CONFUSION) { this.valid = false; this.drawShape(); return }
      this.ctl.drawDirectionAtCursor(p, this.centerPoint)
      this.seekAndRender(this.sug[1], p, [0, 0], 'curve')
    } else if (this.state === 2) {
      const a = this.majorRadius(), d = sub(p, this.centerPoint), dp: XY = [dot(d, this.majorAxis()), dot(d, this.minorAxis())]
      if (!this.minorRadiusSet) {
        if (Math.abs(dp[1]) < CONFUSION) { this.valid = false; this.drawShape(); return }
        const denom = (dp[0] * dp[0]) / (a * a) - 1
        if (denom < CONFUSION) { this.valid = false; this.drawShape(); return }
        this.minorRadius = Math.sqrt((dp[1] * dp[1]) / denom)
      }
      this.startAngle = Math.atanh((dp[1] * a) / (dp[0] * this.minorRadius))
      this.ctl.drawPositionAtCursor(p)
      this.seekAndRender(this.sug[2], p, [0, 0])
    } else if (this.state === 3) {
      const d = sub(p, this.centerPoint), dp: XY = [dot(d, this.majorAxis()), dot(d, this.minorAxis())]
      if (Math.abs((dp[1] * this.majorRadius()) / (dp[0] * this.minorRadius)) > 1) { this.valid = false; this.drawShape(); return }
      this.endAngle = Math.atanh((dp[1] * this.majorRadius()) / (dp[0] * this.minorRadius))
      if (Math.abs(this.arcAngle()) < CONFUSION) { this.valid = false; this.drawShape(); return }
      this.ctl.drawPositionAtCursor(p)
      this.seekAndRender(this.sug[3], p, [0, 0])
    } else return
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
  protected angleSnappingControl() { S.setAngleSnapping(false) }
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
  // the controller's specialisations
  toolIcon() { return 'Sketcher_CreateHyperbolic_Arc' }
  ovpSpec(): OvpSpec { return { ovps: 7, widget: null, firstComboIsMethod: false } }
  ovpState(i: number) { return i < 6 ? Math.trunc(i / 2) : 3 }
  configureOnViewParameters(c: Controller) {
    const o = c.onViewParameters
    o[OVP.First].setLabelType('DISTANCEX'); o[OVP.Second].setLabelType('DISTANCEY')
    o[OVP.Third].setLabelType('RADIUS', 'Dimensioning'); o[OVP.Fourth].setLabelType('ANGLE', 'Dimensioning')
    o[OVP.Fifth].setLabelType('DISTANCE', 'Dimensioning')
    o[OVP.Sixth].setLabelType('ANGLE', 'Dimensioning') // not a real angle: the hyperbolic one
    o[OVP.Seventh].setLabelType('ANGLE', 'Dimensioning')
  }
  doEnforceControlParameters(c: Controller, p: XY): XY {
    this.update(p) // the member variables up to date before the parameters are enforced
    const o = c.onViewParameters
    let [x, y] = p
    if (this.state === 0) {
      if (o[OVP.First].isSet) x = o[OVP.First].getValue()
      if (o[OVP.Second].isSet) y = o[OVP.Second].getValue()
    } else if (this.state === 1) {
      const radiusP = o[OVP.Third], angleP = o[OVP.Fourth]
      if (!radiusP.isSet && !angleP.isSet) return p
      let r = this.majorRadius(), axis = this.majorAxis()
      if (radiusP.isSet) {
        r = radiusP.getValue()
        if (r < CONFUSION && radiusP.hasFinishedEditing) { c.unsetOnViewParameter(radiusP); return p }
      }
      if (angleP.isSet) { const a = (angleP.getValue() * Math.PI) / 180; axis = [Math.cos(a), Math.sin(a)] }
      ;[x, y] = add(this.centerPoint, mul(axis, r))
    } else if (this.state === 2) {
      const radiusP = o[OVP.Fifth], startP = o[OVP.Sixth]
      if (!radiusP.isSet && !startP.isSet) return p
      let b = this.minorRadius, start = this.startAngle
      if (radiusP.isSet) {
        b = radiusP.getValue()
        this.minorRadius = b
        this.minorRadiusSet = true
        if (b < CONFUSION && radiusP.hasFinishedEditing) { this.minorRadiusSet = false; c.unsetOnViewParameter(radiusP); return p }
      }
      if (startP.isSet) start = startP.getValue()
      ;[x, y] = add(add(this.centerPoint, mul(this.majorAxis(), this.majorRadius() * Math.cosh(start))), mul(this.minorAxis(), b * Math.sinh(start)))
    } else if (this.state === 3) {
      const arcP = o[OVP.Seventh]
      if (!arcP.isSet) return p
      const arcAngle = -arcP.getValue(), end = this.startAngle - arcAngle
      ;[x, y] = add(add(this.centerPoint, mul(this.majorAxis(), this.majorRadius() * Math.cosh(end))), mul(this.minorAxis(), this.minorRadius * Math.sinh(end)))
    }
    return [x, y]
  }
  adaptParameters(c: Controller, p: XY) {
    const o = c.onViewParameters
    if (this.state === 0) {
      if (!o[OVP.First].isSet) c.setOnViewParameterValue(OVP.First, p[0])
      if (!o[OVP.Second].isSet) c.setOnViewParameterValue(OVP.Second, p[1])
      const sameSign = p[0] * p[1] > 0
      o[OVP.First].setLabelAutoDistanceReverse(!sameSign); o[OVP.Second].setLabelAutoDistanceReverse(sameSign)
      o[OVP.First].setPoints([0, 0], p); o[OVP.Second].setPoints([0, 0], p)
    } else if (this.state === 1) {
      if (!o[OVP.Third].isSet) c.setOnViewParameterValue(OVP.Third, this.majorRadius())
      if (!o[OVP.Fourth].isSet) c.setOnViewParameterValue(OVP.Fourth, (angleOf(this.majorAxis()) * 180) / Math.PI, 'Angle')
      o[OVP.Third].setPoints(this.centerPoint, p)
      o[OVP.Fourth].setPoints(this.centerPoint, [0, 0])
      o[OVP.Fourth].setLabelRange(angleOf(this.majorAxis()))
    } else if (this.state === 2) {
      const radiusP = o[OVP.Fifth], startP = o[OVP.Sixth]
      if (!radiusP.isSet) c.setOnViewParameterValue(OVP.Fifth, this.valid ? this.minorRadius : 0)
      if (!startP.isSet) c.setOnViewParameterValue(OVP.Sixth, this.valid ? this.startAngle : 0, 'One')
      const start = this.axisPoint
      startP.setPoints(start, [0, 0])
      startP.setLabelStartAngle(angleOf(this.majorAxis()))
      startP.setLabelRange(0)
      radiusP.setPoints(start, add(start, mul(this.minorAxis(), this.minorRadius * Math.sign(this.startAngle))))
      if (!this.valid) radiusP.setPoints(start, start)
    } else if (this.state === 3) {
      const arcP = o[OVP.Seventh]
      if (!arcP.isSet) c.setOnViewParameterValue(OVP.Seventh, this.arcAngle(), 'One')
      arcP.setPoints(this.axisPoint, [0, 0])
      arcP.setLabelStartAngle(angleOf(this.majorAxis()))
      arcP.setLabelRange(0)
    }
  }
  computeNextDrawSketchHandlerMode(c: Controller) {
    const o = c.onViewParameters
    if (this.state === 0) { if (o[OVP.First].hasFinishedEditing && o[OVP.Second].hasFinishedEditing) this.setNextState(1) }
    else if (this.state === 1) { if (o[OVP.Third].hasFinishedEditing && o[OVP.Fourth].hasFinishedEditing) this.setNextState(2) }
    else if (this.state === 2) { if (o[OVP.Fifth].hasFinishedEditing && o[OVP.Sixth].hasFinishedEditing) this.setNextState(3) }
    else if (this.state === 3) { if (o[OVP.Seventh].hasFinishedEditing) this.setNextState(this.states) }
  }
  /** DSHArcOfHyperbolaController::addConstraints, with no diagnosis yet: the centre's position, the major radius and
   *  the major axis's angle (the internal major line runs the other way), the minor radius; not the hyperbolic angles. */
  addConstraints(c: Controller) {
    const o = c.onViewParameters
    const firstCurve = this.hyperbolaGeoId, majorLine = firstCurve + 1, minorLine = firstCurve + 2
    const x0set = o[OVP.First].isSet, y0set = o[OVP.Second].isSet
    if (x0set && y0set && len(this.centerPoint) <= CONFUSION) attachSolved([firstCurve, MID], RT_PNT_ID, 0)
    else {
      if (x0set) attachSolved([firstCurve, MID], V_AXIS_ID, this.centerPoint[0])
      if (y0set) attachSolved([firstCurve, MID], H_AXIS_ID, this.centerPoint[1])
    }
    if (o[OVP.Third].isSet) addSolved(constraint('Distance', firstCurve, MID, majorLine, START, SK.GEO_UNDEF, NONE, f6(this.majorRadius())))
    if (o[OVP.Fourth].isSet) addSolved(constraint('Angle', majorLine, NONE, SK.GEO_UNDEF, NONE, SK.GEO_UNDEF, NONE, f6(angleOf(this.majorAxis()) - Math.PI)))
    if (o[OVP.Fifth].isSet) addSolved(constraint('Distance', majorLine, START, minorLine, START, SK.GEO_UNDEF, NONE, f6(this.minorRadius)))
  }
}

// ── Arc of parabola (DrawSketchHandlerArcOfParabola.h): focus, vertex, then the two ends ─────────────────────────
/** DSHArcOfParabolaController: six on-view parameters: the focus's X and Y, the focal length and the axis's angle,
 *  the start and the end's parameters (unitless). */
export class ArcOfParabolaHandler extends DefaultHandler {
  readonly toolName = 'DSH_ArcOfParabola'
  protected readonly states = 4
  protected readonly autoConstraintSize = 4
  private centerPoint: XY = [0, 0]; private focusPoint: XY = [0, 0]
  private startPoint = 0; private endPoint = 0; private valid = true
  private parabolaGeoId = SK.GEO_UNDEF
  crosshair() { return 'Sketcher_Pointer_Create_ArcOfParabola' }
  hints() { return [this.hint(['%1 pick focus point', '%1 pick axis point', '%1 pick starting point', '%1 pick end point'][Math.min(this.state, 3)], [LMB])] }
  private axis() { return normalize(sub(this.focusPoint, this.centerPoint)) }
  private focal() { return len(sub(this.focusPoint, this.centerPoint)) }
  protected update(p: XY) {
    this.valid = true
    if (this.state === 0) { this.focusPoint = p; this.ctl.drawPositionAtCursor(p); this.seekAndRender(this.sug[0], p, [0, 0]) }
    else if (this.state === 1) {
      this.centerPoint = p
      if (len(sub(this.centerPoint, this.focusPoint)) < CONFUSION) { this.valid = false; this.drawShape(); return }
      this.ctl.drawDirectionAtCursor(p, this.focusPoint)
      this.seekAndRender(this.sug[1], p, [0, 0])
    } else if (this.state === 2) {
      this.startPoint = dot(sub(p, this.centerPoint), perp(this.axis()))
      this.ctl.drawPositionAtCursor(p)
      this.seekAndRender(this.sug[2], p, [0, 0])
    } else if (this.state === 3) {
      this.endPoint = dot(sub(p, this.centerPoint), perp(this.axis()))
      if (Math.abs(this.endPoint - this.startPoint) < CONFUSION) { this.valid = false; this.drawShape(); return }
      this.ctl.drawPositionAtCursor(p)
      this.seekAndRender(this.sug[3], p, [0, 0])
    } else return
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
  protected angleSnappingControl() { S.setAngleSnapping(false) }
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
  // the controller's specialisations
  toolIcon() { return 'Sketcher_CreateParabolic_Arc' }
  ovpSpec(): OvpSpec { return { ovps: 6, widget: null, firstComboIsMethod: false } }
  ovpState(i: number) { return i < 4 ? Math.trunc(i / 2) : i - 2 }
  configureOnViewParameters(c: Controller) {
    const o = c.onViewParameters
    o[OVP.First].setLabelType('DISTANCEX'); o[OVP.Second].setLabelType('DISTANCEY')
    o[OVP.Third].setLabelType('RADIUS', 'Dimensioning'); o[OVP.Fourth].setLabelType('ANGLE', 'Dimensioning')
    o[OVP.Fifth].setLabelType('ANGLE', 'Dimensioning'); o[OVP.Sixth].setLabelType('ANGLE', 'Dimensioning')
  }
  doEnforceControlParameters(c: Controller, p: XY): XY {
    this.update(p) // the member variables up to date before the parameters are enforced
    const o = c.onViewParameters
    let [x, y] = p
    if (this.state === 0) {
      if (o[OVP.First].isSet) x = o[OVP.First].getValue()
      if (o[OVP.Second].isSet) y = o[OVP.Second].getValue()
    } else if (this.state === 1) {
      const focalP = o[OVP.Third], angleP = o[OVP.Fourth]
      if (!focalP.isSet && !angleP.isSet) return p
      let focal = this.focal(), axis = this.axis()
      if (focalP.isSet) {
        focal = focalP.getValue()
        if (focal < CONFUSION && focalP.hasFinishedEditing) { c.unsetOnViewParameter(focalP); return p }
      }
      if (angleP.isSet) { const a = (angleP.getValue() * Math.PI) / 180; axis = [Math.cos(a), Math.sin(a)] }
      ;[x, y] = add(this.focusPoint, mul(axis, -focal))
    } else if (this.state === 2) {
      const startP = o[OVP.Fifth]
      if (!startP.isSet) return p
      ;[x, y] = add(this.centerPoint, mul(perp(this.axis()), startP.getValue()))
    } else if (this.state === 3) {
      const arcP = o[OVP.Sixth]
      if (!arcP.isSet) return p
      const arc = -arcP.getValue()
      if (Math.abs(arc) < CONFUSION && arcP.hasFinishedEditing) { c.unsetOnViewParameter(arcP); return p }
      // FreeCAD's puts the cursor where the end already is (endPoint, from the cursor), not where the span says
      ;[x, y] = add(this.centerPoint, mul(perp(this.axis()), this.endPoint))
    }
    return [x, y]
  }
  adaptParameters(c: Controller, p: XY) {
    const o = c.onViewParameters
    if (this.state === 0) {
      if (!o[OVP.First].isSet) c.setOnViewParameterValue(OVP.First, p[0])
      if (!o[OVP.Second].isSet) c.setOnViewParameterValue(OVP.Second, p[1])
      const sameSign = p[0] * p[1] > 0
      o[OVP.First].setLabelAutoDistanceReverse(!sameSign); o[OVP.Second].setLabelAutoDistanceReverse(sameSign)
      o[OVP.First].setPoints([0, 0], p); o[OVP.Second].setPoints([0, 0], p)
    } else if (this.state === 1) {
      if (!o[OVP.Third].isSet) c.setOnViewParameterValue(OVP.Third, this.focal())
      if (!o[OVP.Fourth].isSet) c.setOnViewParameterValue(OVP.Fourth, (angleOf(this.axis()) * 180) / Math.PI, 'Angle')
      o[OVP.Third].setPoints(this.focusPoint, p)
      o[OVP.Fourth].setPoints(this.focusPoint, [0, 0])
      o[OVP.Fourth].setLabelRange(angleOf(this.axis()))
    } else if (this.state === 2) {
      const startP = o[OVP.Fifth]
      if (!startP.isSet) c.setOnViewParameterValue(OVP.Fifth, this.startPoint, 'One')
      startP.setPoints(this.centerPoint, [0, 0])
      startP.setLabelStartAngle(angleOf(this.axis()))
      startP.setLabelRange(0)
    } else if (this.state === 3) {
      const arcP = o[OVP.Sixth]
      if (!arcP.isSet) c.setOnViewParameterValue(OVP.Sixth, this.endPoint - this.startPoint, 'One')
      arcP.setPoints(this.centerPoint, [0, 0])
      arcP.setLabelStartAngle(angleOf(this.axis()))
      arcP.setLabelRange(0)
    }
  }
  computeNextDrawSketchHandlerMode(c: Controller) {
    const o = c.onViewParameters
    if (this.state === 0) { if (o[OVP.First].hasFinishedEditing && o[OVP.Second].hasFinishedEditing) this.setNextState(1) }
    else if (this.state === 1) { if (o[OVP.Third].hasFinishedEditing && o[OVP.Fourth].hasFinishedEditing) this.setNextState(2) }
    else if (this.state === 2) { if (o[OVP.Fifth].hasFinishedEditing) this.setNextState(3) }
    else if (this.state === 3) { if (o[OVP.Sixth].hasFinishedEditing) this.setNextState(this.states) }
  }
  /** DSHArcOfParabolaController::addConstraints, with no diagnosis yet: the focus's position (its point, at its "mid"),
   *  the focal length and the axis's angle on the internal focal line; not the ends' parameters. */
  addConstraints(c: Controller) {
    const o = c.onViewParameters
    const focusPoint = this.parabolaGeoId + 1, line = this.parabolaGeoId + 2
    const x0set = o[OVP.First].isSet, y0set = o[OVP.Second].isSet
    if (x0set && y0set && len(this.focusPoint) <= CONFUSION) attachSolved([focusPoint, MID], RT_PNT_ID, 0)
    else {
      if (x0set) attachSolved([focusPoint, MID], V_AXIS_ID, this.focusPoint[0])
      if (y0set) attachSolved([focusPoint, MID], H_AXIS_ID, this.focusPoint[1])
    }
    if (o[OVP.Third].isSet) addSolved(constraint('Distance', line, START, line, END, SK.GEO_UNDEF, NONE, f6(this.focal())))
    if (o[OVP.Fourth].isSet) addSolved(constraint('Angle', line, NONE, SK.GEO_UNDEF, NONE, SK.GEO_UNDEF, NONE, f6(angleOf(this.axis()))))
  }
}

// ── B-spline by control points (DrawSketchHandlerBSpline.h, ControlPoints) ───────────────────────────────────────
let knotsSwitch: ((periodic: boolean, points: XY[]) => void) | null = null
/** M: the knots method's tool (sketchcurvecmds.ts registers it). */
export function setKnotsSwitch(f: (periodic: boolean, points: XY[]) => void) { knotsSwitch = f }
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
  /** carried: the knots tool's points so far, as poles now (M, changeConstructionMethode). */
  constructor(private periodic = false, private carried: XY[] = []) { super() }
  crosshair() { return this.periodic ? 'Sketcher_Pointer_Create_Periodic_BSpline' : 'Sketcher_Pointer_Create_BSpline' }
  hints() {
    const sw = this.hint('%1 switch to knots', ['M']), per = this.hint('%1 toggle periodic', ['F']), deg = this.hint('%1/%2 increase/decrease degree', ['U', 'J'])
    if (this.state === 0) return [this.hint('%1 pick first control point', [LMB]), sw, per, deg]
    return [this.hint('%1 pick next point', [LMB]), this.hint('%1 finish', [RMB]), sw, per, this.hint('%1 undo last point', ['R']), deg]
  }
  activated() {
    super.activated(); S.openCommand('Add Sketch B-Spline')
    if (this.carried.length) { for (const p of this.carried) { this.prevCursor = p; this.addPos() } this.carried = []; this.state = 1; S.solve(); S.updateHints() }
  }
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
    if (key === 'M') { if (!pressed) knotsSwitch?.(this.periodic, [...this.points]); return true } // to B-spline by knots
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

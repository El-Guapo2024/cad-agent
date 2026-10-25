// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Sketcher/Gui/DrawSketchHandlerSymmetry.h: 2022 Boyer Pierre-Louis
//   src/Mod/Sketcher/Gui/DrawSketchHandlerTranslate.h: 2022 Boyer Pierre-Louis
//   src/Mod/Sketcher/Gui/DrawSketchHandlerRotate.h: 2022 Boyer Pierre-Louis
//   src/Mod/Sketcher/Gui/DrawSketchHandlerScale.h: 2022 Boyer Pierre-Louis
//   src/Mod/Sketcher/Gui/CommandSketcherTools.cpp: 2014 Abdullah Tahiri
// The Sketcher's controllable transform tools, on the on-view parameters and the Tool Parameters box (sketchovp.ts):
// Sketcher_Symmetry (pick an axis, an edge or a point; delete the originals, or tie the copies with symmetry
// constraints), Sketcher_Translate (a reference point, a vector, a second one for rows; elements and rows, equal
// constraints, symmetric), Sketcher_Rotate (a centre, a start angle, the rotation; elements, equal constraints,
// symmetric) and Sketcher_Scale (a reference point, a reference length, the scaled length or the factor; keep the
// originals). Their shapes are sketchxform.ts's translateShape, rotateShape and scaleShape and SketchObject's
// addSymmetric; they go into the sketch as the Python FreeCAD's tools write (commandAddShapeGeometryAndConstraints).
import type { Geo, XY } from './solver'
import * as SK from './sketch'
import { START, NONE, GEO_UNDEF, H_AXIS, V_AXIS, RT_PNT, REF_EXT, type PointPos } from './sketch'
import * as S from './sketcher'
import * as XF from './sketchxform'
import * as OPS from './sketchops'
import { DefaultHandler } from './sketchtools'
import { Controller, OVP, type OvpSpec } from './sketchovp'
import { addShapeThroughPython, selectedGeoIds } from './sketchxformtools'
import { report } from './store'

const LMB = 'LMB'
const CONFUSION = 1e-7
const sub = (a: XY, b: XY): XY => [a[0] - b[0], a[1] - b[1]], add = (a: XY, b: XY): XY => [a[0] + b[0], a[1] + b[1]]
const mul = (a: XY, k: number): XY => [a[0] * k, a[1] * k], len = (a: XY) => Math.hypot(a[0], a[1])
const angleOf = (a: XY) => Math.atan2(a[1], a[0])
const unitOf = (a: XY): XY => { const l = len(a); return l ? [a[0] / l, a[1] / l] : a }
const rad = (d: number) => (d * Math.PI) / 180, deg = (r: number) => (r * 180) / Math.PI
const doc = (): XF.Doc => ({ geometry: S.getGeometry().map((g) => ({ ...g })), constraints: S.getConstraints().map((c) => ({ ...c })) })
const constructionLine = (a: XY, b: XY): Geo => ({ type: 'LineSegment', start: a, end: b, construction: true })
/** delGeometries([...]) as the tools run it: SketchObject::delGeometries (constraints on coincident points moved on). */
function deleteOriginalGeos(list: number[]) {
  if (!list.length) return
  const d: OPS.Doc = { geometry: S.getGeometry().map((g) => ({ ...g })), constraints: S.getConstraints().map((c) => ({ ...c })) }
  OPS.delGeometries(d, list)
  S.setGeometry(d.geometry); S.setConstraints(d.constraints)
}
/** A tool's executeCommands failing: FreeCAD's notification, the command aborted, the tool told to stop. */
function failed(e: unknown, what: string): never {
  console.error(e)
  report('err', `Error: ${what}`)
  S.abortCommand()
  throw new Error('Tool execution aborted')
}

// ── Sketcher_Symmetry (DrawSketchHandlerSymmetry.h) ──────────────────────────────────────────────────────────────
/** DSHSymmetryController: no on-view parameter; "Delete original geometries (U)" and "Create symmetry constraints (J)". */
export class SymmetryHandler extends DefaultHandler {
  readonly toolName = 'DSH_Symmetry'
  protected readonly states = 1
  protected readonly autoConstraintSize = 0
  private refGeoId = GEO_UNDEF
  private refPosId: PointPos = NONE
  private deleteOriginal = false
  private createSymConstraints = true
  constructor(private readonly list: number[]) { super() }
  crosshair() { return 'Sketcher_Pointer_Create_Symmetry' }
  hints() { return [this.hint('%1 pick axis, edge, or point', [LMB])] }
  activated() { super.activated(); this.continuousMode = false }
  protected update(_p: XY) {
    if (this.state !== 0) return
    const pre = S.getPreselection(), geo = S.getGeometry()
    if (pre.point >= 0) [this.refGeoId, this.refPosId] = S.geoVertexIndex(pre.point)
    else if (pre.cross === 0) { this.refGeoId = RT_PNT; this.refPosId = START }
    else if (pre.cross === 1) { this.refGeoId = H_AXIS; this.refPosId = NONE }
    else if (pre.cross === 2) { this.refGeoId = V_AXIS; this.refPosId = NONE }
    else if (pre.curve !== null && (pre.curve >= 0 || pre.curve <= REF_EXT) && geo[pre.curve]?.type === 'LineSegment') { this.refGeoId = pre.curve; this.refPosId = NONE }
    else { this.refGeoId = GEO_UNDEF; this.refPosId = NONE }
    this.drawShape()
  }
  protected createShape(onlyOutline: boolean) {
    this.shapeGeometry = []
    if (this.refGeoId === GEO_UNDEF) return
    if (onlyOutline) this.shapeGeometry = XF.getSymmetric(doc(), this.list, this.refGeoId, this.refPosId).geometry
  }
  protected canGoToNextMode() { return !(this.state === 0 && this.refGeoId === GEO_UNDEF) }
  protected executeCommands() {
    try {
      S.openCommand('Symmetry geometries')
      this.createSymConstraints = !this.deleteOriginal && this.createSymConstraints
      const d = doc()
      XF.addSymmetric(d, this.list, this.refGeoId, this.refPosId, this.createSymConstraints)
      S.setGeometry(d.geometry); S.setConstraints(d.constraints)
      if (this.deleteOriginal) deleteOriginalGeos(this.list)
      S.solve()
      S.commitCommand()
    } catch (e) { failed(e, 'Failed to create symmetry') }
  }
  isWidgetVisible() { return true }
  toolWidgetText() { return 'Symmetry Parameters' }
  toolIcon() { return 'Sketcher_Symmetry' }
  ovpSpec(): OvpSpec { return { ovps: 0, widget: { parameters: 0, checkboxes: 2, comboboxes: 0, lineEdits: 0 }, firstComboIsMethod: false } }
  configureToolWidget(c: Controller) {
    if (!c.init) {
      c.setCheckboxLabel(0, 'Delete original geometries (U)')
      c.setCheckboxToolTip(0, 'Removes the original geometry and keeps only the mirrored result.')
      c.setCheckboxLabel(1, 'Create symmetry constraints (J)')
      c.setCheckboxToolTip(1, 'Create symmetry constraints between the original and mirrored geometries')
    }
    c.syncCheckboxToHandler(1, this.createSymConstraints)
  }
  adaptDrawingToCheckboxChange(c: Controller, i: number, v: boolean) {
    if (i === 0) { this.deleteOriginal = v; if (v && c.getCheckboxChecked(1)) c.setCheckboxChecked(1, false) }
    else if (i === 1) { this.createSymConstraints = v; if (v && c.getCheckboxChecked(0)) c.setCheckboxChecked(0, false) }
  }
}

// ── Sketcher_Translate (DrawSketchHandlerTranslate.h) ────────────────────────────────────────────────────────────
/** DSHTranslateController: the reference point's X and Y, the vector's length and angle, the second vector's; the
 *  widget's Elements and Rows, "Apply equal constraints" and "Symmetric". */
export class TranslateHandler extends DefaultHandler {
  readonly toolName = 'DSH_Translate'
  protected readonly states = 3
  protected readonly autoConstraintSize = 0
  private referencePoint: XY = [0, 0]; private firstTranslationPoint: XY = [0, 0]; private secondTranslationPoint: XY = [0, 0]
  private firstTranslationVector: XY = [0, 0]; private secondTranslationVector: XY = [0, 0]
  private deleteOriginal = false; private cloneConstraints = false; private firstDirectionSymmetric = false; private secondDirectionSymmetric = false
  private numberOfCopies = 1; private secondNumberOfCopies = 1
  constructor(private readonly list: number[]) { super() }
  crosshair() { return 'Sketcher_Pointer_Create_Translate' }
  hints() {
    const elements = this.hint('%1/%2 increase/decrease number of elements', ['U', 'J']), rows = this.hint('%1/%2 increase/decrease number of rows', ['R', 'F'])
    if (this.state === 0) return [this.hint('%1 pick reference point', [LMB])]
    if (this.state === 1) return [this.hint('%1 set translation vector', [LMB]), elements, rows]
    if (this.state === 2) return [this.hint('%1 set second translation vector', [LMB]), elements, rows]
    return []
  }
  activated() { super.activated(); this.continuousMode = false }
  protected update(p: XY) {
    if (this.state === 0) this.referencePoint = p
    else if (this.state === 1) { this.firstTranslationPoint = p; this.firstTranslationVector = sub(p, this.referencePoint); this.drawShape() }
    else if (this.state === 2) { this.secondTranslationPoint = p; this.secondTranslationVector = sub(p, this.referencePoint); this.drawShape() }
  }
  protected onButtonPressed(p: XY) {
    this.update(p)
    if (this.state === 1 && this.secondNumberOfCopies === 1) this.setState(this.states)
    else {
      if (this.state === 1) this.secondDirectionSymmetric = this.firstDirectionSymmetric
      this.setState(this.state + 1)
    }
  }
  protected canGoToNextMode() {
    if (this.state === 1 && len(this.firstTranslationVector) < CONFUSION) return false
    if (this.state === 2 && len(this.secondTranslationVector) < CONFUSION && this.secondNumberOfCopies > 1) return false
    return true
  }
  protected angleSnappingControl() { if (this.state === 1 || this.state === 2) S.setAngleSnapping(true, this.referencePoint); else S.setAngleSnapping(false) }
  private shape() {
    const s = XF.translateShape(doc(), this.list, this.firstTranslationVector, this.secondTranslationVector, this.numberOfCopies, this.secondNumberOfCopies,
      this.firstDirectionSymmetric, this.secondDirectionSymmetric, this.cloneConstraints)
    this.deleteOriginal = s.deleteOriginal
    return s
  }
  protected createShape(onlyOutline: boolean) {
    this.shapeGeometry = this.shape().geometry
    if (onlyOutline) {
      if (len(this.firstTranslationVector) > CONFUSION) this.shapeGeometry.push(constructionLine(this.referencePoint, this.firstTranslationPoint))
      if (len(this.secondTranslationVector) > CONFUSION) this.shapeGeometry.push(constructionLine(this.referencePoint, this.secondTranslationPoint))
    }
  }
  protected executeCommands() {
    try {
      S.openCommand('Translate geometries')
      const s = this.shape()
      addShapeThroughPython(s.geometry, s.constraints)
      if (this.deleteOriginal) deleteOriginalGeos(this.list)
      S.commitCommand()
    } catch (e) { failed(e, 'Failed to translate') }
  }
  isWidgetVisible() { return true }
  toolWidgetText() { return 'Translate Parameters' }
  toolIcon() { return 'Sketcher_Translate' }
  ovpSpec(): OvpSpec { return { ovps: 6, widget: { parameters: 2, checkboxes: 2, comboboxes: 0, lineEdits: 0 }, firstComboIsMethod: false } }
  ovpState(i: number) { return Math.trunc(i / 2) }
  firstKeyShortcut(c: Controller) { c.setParameterWithoutPassingFocus(0, c.getParameter(0) + 1); return true }
  secondKeyShortcut(c: Controller) { const v = c.getParameter(0); if (v > 1) c.setParameterWithoutPassingFocus(0, v - 1); return true }
  thirdKeyShortcut(c: Controller) { c.setParameterWithoutPassingFocus(1, c.getParameter(1) + 1); return true }
  fourthKeyShortcut(c: Controller) { const v = c.getParameter(1); if (v > 1) c.setParameterWithoutPassingFocus(1, v - 1); return true }
  configureToolWidget(c: Controller) {
    if (!c.init) {
      c.setCheckboxLabel(0, 'Apply equal constraints')
      c.setCheckboxToolTip(0, 'If this option is selected dimensional constraints are excluded from the operation.\nInstead equal constraints are applied between the original objects and their copies.')
      c.setCheckboxLabel(1, 'Symmetric')
      c.setCheckboxToolTip(1, 'Distribute the elements symmetrically around the original position.')
    }
    const o = c.onViewParameters
    o[OVP.First].setLabelType('DISTANCEX'); o[OVP.Second].setLabelType('DISTANCEY')
    o[OVP.Third].setLabelType('DISTANCE', 'Dimensioning'); o[OVP.Fourth].setLabelType('ANGLE', 'Dimensioning')
    o[OVP.Fifth].setLabelType('DISTANCE', 'Dimensioning'); o[OVP.Sixth].setLabelType('ANGLE', 'Dimensioning')
    c.setParameterLabel(0, 'Elements'); c.setParameterLabel(1, 'Rows')
    c.setParameter(0, 1); c.setParameter(1, 1)
    for (const i of [0, 1]) { c.configureParameterUnit(i, 'None'); c.configureParameterMin(i, 1); c.configureParameterMax(i, 9999); c.configureParameterDecimals(i, 0) }
  }
  adaptDrawingToParameterChange(_c: Controller, i: number, v: number) {
    if (i === 0) this.numberOfCopies = Math.max(1, Math.floor(Math.abs(v)))
    else if (i === 1) this.secondNumberOfCopies = Math.max(1, Math.floor(Math.abs(v)))
  }
  adaptDrawingToCheckboxChange(_c: Controller, i: number, v: boolean) {
    if (i === 0) this.cloneConstraints = v
    else if (i === 1) { if (this.state === 2) this.secondDirectionSymmetric = v; else this.firstDirectionSymmetric = v }
  }
  doEnforceControlParameters(c: Controller, p: XY): XY {
    const o = c.onViewParameters
    let q: XY = [p[0], p[1]]
    if (this.state === 0) {
      if (o[OVP.First].isSet) q = [o[OVP.First].getValue(), q[1]]
      if (o[OVP.Second].isSet) q = [q[0], o[OVP.Second].getValue()]
    } else if (this.state === 1 || this.state === 2) {
      const lp = o[this.state === 1 ? OVP.Third : OVP.Fifth], ap = o[this.state === 1 ? OVP.Fourth : OVP.Sixth]
      let dir = sub(q, this.referencePoint)
      if (len(dir) < CONFUSION) dir = [1, dir[1]]
      let length = len(dir)
      if (lp.isSet) {
        length = lp.getValue()
        if (length < CONFUSION && lp.hasFinishedEditing) { c.unsetOnViewParameter(lp); return q }
        q = add(this.referencePoint, mul(unitOf(dir), length))
      }
      if (ap.isSet) { const a = rad(ap.getValue()); q = [this.referencePoint[0] + Math.cos(a) * length, this.referencePoint[1] + Math.sin(a) * length] }
    }
    return q
  }
  adaptParameters(c: Controller, p: XY) {
    const o = c.onViewParameters
    if (this.state === 0) {
      if (!o[OVP.First].isSet) c.setOnViewParameterValue(OVP.First, p[0])
      if (!o[OVP.Second].isSet) c.setOnViewParameterValue(OVP.Second, p[1])
      const sameSign = p[0] * p[1] > 0
      o[OVP.First].setLabelAutoDistanceReverse(!sameSign); o[OVP.Second].setLabelAutoDistanceReverse(sameSign)
      o[OVP.First].setPoints([0, 0], p); o[OVP.Second].setPoints([0, 0], p)
    } else if (this.state === 1 || this.state === 2) {
      const [li, ai] = this.state === 1 ? [OVP.Third, OVP.Fourth] : [OVP.Fifth, OVP.Sixth]
      if (!o[li].isSet) c.setOnViewParameterValue(li, len(sub(p, this.referencePoint)))
      const angle = angleOf(this.state === 1 ? this.firstTranslationVector : this.secondTranslationVector)
      if (!o[ai].isSet) c.setOnViewParameterValue(ai, deg(angle), 'Angle')
      o[li].setPoints(this.referencePoint, p)
      o[ai].setPoints(this.referencePoint, [0, 0])
      o[ai].setLabelRange(angle)
    }
  }
  computeNextDrawSketchHandlerMode(c: Controller) {
    const o = c.onViewParameters
    if (this.state === 0) { if (o[OVP.First].hasFinishedEditing && o[OVP.Second].hasFinishedEditing) this.setNextState(1) }
    else if (this.state === 1) {
      if (o[OVP.Third].hasFinishedEditing && o[OVP.Fourth].hasFinishedEditing) {
        if (this.secondNumberOfCopies === 1) this.setNextState(this.states)
        else { this.secondDirectionSymmetric = this.firstDirectionSymmetric; this.setNextState(2) }
      }
    } else if (this.state === 2) { if (o[OVP.Fifth].hasFinishedEditing && o[OVP.Sixth].hasFinishedEditing) this.setNextState(this.states) }
  }
}

// ── Sketcher_Rotate (DrawSketchHandlerRotate.h) ──────────────────────────────────────────────────────────────────
/** DSHRotateController: the centre's X and Y, the start angle, the rotation; the widget's Elements, "Apply equal
 *  constraints" and "Symmetric". */
export class RotateHandler extends DefaultHandler {
  readonly toolName = 'DSH_Rotate'
  protected readonly states = 3
  protected readonly autoConstraintSize = 0
  private centerPoint: XY = [0, 0]; private startPoint: XY = [0, 0]; private endpoint: XY = [0, 0]
  private deleteOriginal = false; private cloneConstraints = false; private symmetric = false
  private length = 0; private startAngle = 0; private endAngle = 0; private totalAngle = 0
  private numberOfCopies = 1
  constructor(private readonly list: number[]) { super() }
  crosshair() { return 'Sketcher_Pointer_Create_Rotate' }
  hints() {
    const elements = this.hint('%1/%2 increase/decrease number of elements', ['U', 'J'])
    const first = ['%1 pick center point', '%1 set start angle', '%1 set rotation angle'][this.state]
    return first ? [this.hint(first, [LMB]), elements] : []
  }
  activated() { super.activated(); this.continuousMode = false }
  protected update(p: XY) {
    if (this.state === 0) this.centerPoint = p
    else if (this.state === 1) {
      this.length = len(sub(p, this.centerPoint)); this.startAngle = angleOf(sub(p, this.centerPoint)); this.startPoint = p
      this.drawShape()
    } else if (this.state === 2) {
      this.endAngle = angleOf(sub(p, this.centerPoint))
      this.endpoint = add(this.centerPoint, mul([Math.cos(this.endAngle), Math.sin(this.endAngle)], this.length))
      this.totalAngle = XF.closestContinuousAngle(this.endAngle - this.startAngle, this.totalAngle)
      this.drawShape()
    }
  }
  protected angleSnappingControl() { if (this.state === 1 || this.state === 2) S.setAngleSnapping(true, this.centerPoint); else S.setAngleSnapping(false) }
  private shape() {
    const s = XF.rotateShape(doc(), this.list, this.centerPoint, this.totalAngle, this.numberOfCopies, this.symmetric, this.cloneConstraints)
    this.deleteOriginal = s.deleteOriginal
    return s
  }
  protected createShape(onlyOutline: boolean) {
    this.shapeGeometry = []
    if (this.state === 1) {
      if (this.length > CONFUSION) this.shapeGeometry.push({ type: 'LineSegment', start: this.centerPoint, end: this.startPoint, ...(this.isConstructionMode() ? { construction: true } : {}) })
      return
    }
    this.shapeGeometry = this.shape().geometry
    if (onlyOutline) this.shapeGeometry.push(constructionLine(this.centerPoint, this.startPoint), constructionLine(this.centerPoint, this.endpoint))
  }
  protected executeCommands() {
    try {
      S.openCommand('Rotate geometries')
      const s = this.shape()
      addShapeThroughPython(s.geometry, s.constraints)
      if (this.deleteOriginal) deleteOriginalGeos(this.list)
      S.commitCommand()
    } catch (e) { failed(e, 'Failed to rotate') }
  }
  isWidgetVisible() { return true }
  toolWidgetText() { return 'Rotate Parameters' }
  toolIcon() { return 'Sketcher_Rotate' }
  ovpSpec(): OvpSpec { return { ovps: 4, widget: { parameters: 1, checkboxes: 2, comboboxes: 0, lineEdits: 0 }, firstComboIsMethod: false } }
  ovpState(i: number) { return i < 2 ? 0 : i === 2 ? 1 : 2 }
  firstKeyShortcut(c: Controller) { c.setParameterWithoutPassingFocus(0, c.getParameter(0) + 1); return true }
  secondKeyShortcut(c: Controller) { const v = c.getParameter(0); if (v > 1) c.setParameterWithoutPassingFocus(0, v - 1); return true }
  configureToolWidget(c: Controller) {
    if (!c.init) {
      c.setCheckboxLabel(0, 'Apply equal constraints')
      c.setCheckboxToolTip(0, '<p>If this option is selected dimensional constraints are excluded from the operation.\nInstead equal constraints are applied between the original objects and their copies.</p>')
      c.setCheckboxLabel(1, 'Symmetric')
      c.setCheckboxToolTip(1, 'Distribute the elements symmetrically around the original position.')
    }
    const o = c.onViewParameters
    o[OVP.First].setLabelType('DISTANCEX'); o[OVP.Second].setLabelType('DISTANCEY')
    o[OVP.Third].setLabelType('ANGLE', 'Dimensioning'); o[OVP.Fourth].setLabelType('ANGLE', 'Dimensioning')
    c.setParameterLabel(0, 'Elements')
    c.setParameter(0, 1)
    c.configureParameterUnit(0, 'None'); c.configureParameterMin(0, 1); c.configureParameterMax(0, 9999); c.configureParameterDecimals(0, 0)
  }
  adaptDrawingToParameterChange(_c: Controller, i: number, v: number) { if (i === 0) this.numberOfCopies = Math.max(1, Math.floor(Math.abs(v))) }
  adaptDrawingToCheckboxChange(_c: Controller, i: number, v: boolean) { if (i === 0) this.cloneConstraints = v; else if (i === 1) this.symmetric = v }
  doEnforceControlParameters(c: Controller, p: XY): XY {
    const o = c.onViewParameters
    let q: XY = [p[0], p[1]]
    if (this.state === 0) {
      if (o[OVP.First].isSet) q = [o[OVP.First].getValue(), q[1]]
      if (o[OVP.Second].isSet) q = [q[0], o[OVP.Second].getValue()]
    } else if (this.state === 1) {
      const t = o[OVP.Third]
      if (t.isSet) {
        const a = rad(t.getValue()), cl = XF.clampToFullTurn(a)
        if (cl !== a) c.setOnViewParameterValue(OVP.Third, deg(cl), 'Angle')
        q = [this.centerPoint[0] + 1, this.centerPoint[1]]
      }
    } else if (this.state === 2) {
      const f = o[OVP.Fourth]
      if (f.isSet) {
        let a = rad(f.getValue())
        const cl = XF.clampToFullTurn(a)
        if (cl !== a) { c.setOnViewParameterValue(OVP.Fourth, deg(cl), 'Angle'); a = cl }
        this.totalAngle = a
        q = [this.centerPoint[0] + Math.cos(this.startAngle + a), this.centerPoint[1] + Math.sin(this.startAngle + a)]
      }
    }
    return q
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
      if (!o[OVP.Third].isSet) c.setOnViewParameterValue(OVP.Third, deg(this.startAngle), 'Angle')
      o[OVP.Third].setPoints(this.centerPoint, [0, 0])
      o[OVP.Third].setLabelRange(this.startAngle)
    } else if (this.state === 2) {
      if (!o[OVP.Fourth].isSet) c.setOnViewParameterValue(OVP.Fourth, deg(this.totalAngle), 'Angle')
      o[OVP.Fourth].setPoints(this.centerPoint, [0, 0])
      o[OVP.Fourth].setLabelStartAngle(this.startAngle)
      o[OVP.Fourth].setLabelRange(this.totalAngle)
    }
  }
  computeNextDrawSketchHandlerMode(c: Controller) {
    const o = c.onViewParameters
    if (this.state === 0) { if (o[OVP.First].hasFinishedEditing && o[OVP.Second].hasFinishedEditing) this.setNextState(1) }
    else if (this.state === 1) {
      if (o[OVP.Third].hasFinishedEditing) { this.totalAngle = XF.clampToFullTurn(rad(o[OVP.Third].getValue())); this.setNextState(this.states) }
    } else if (this.state === 2) { if (o[OVP.Fourth].hasFinishedEditing) this.setNextState(this.states) }
  }
}

// ── Sketcher_Scale (DrawSketchHandlerScale.h) ────────────────────────────────────────────────────────────────────
/** DSHScaleController: the reference point's X and Y, the scale factor (always shown); "Keep original geometries (U)". */
export class ScaleHandler extends DefaultHandler {
  readonly toolName = 'DSH_Scale'
  protected readonly states = 3
  protected readonly autoConstraintSize = 0
  private referencePoint: XY = [0, 0]; private startPoint: XY = [0, 0]; private endPoint: XY = [0, 0]
  private deleteOriginal = true
  private refLength = 0; private length = 0; private scaleFactor = 0
  constructor(private readonly list: number[]) { super() }
  crosshair() { return 'Sketcher_Pointer_Create_Scale' }
  hints() {
    if (this.state === 0) return [this.hint('%1 pick reference point', [LMB])]
    if (this.state === 1) return [this.hint('%1 set scale factor', [LMB])]
    return []
  }
  activated() { super.activated(); this.continuousMode = false }
  protected update(p: XY) {
    if (this.state === 0) this.referencePoint = p
    else if (this.state === 1) { this.refLength = len(sub(p, this.referencePoint)); this.startPoint = p; this.drawShape() }
    else if (this.state === 2) { this.length = len(sub(p, this.referencePoint)); this.endPoint = p; this.scaleFactor = this.length / this.refLength; this.drawShape() }
  }
  protected canGoToNextMode() { return !(this.state === 2 && this.scaleFactor < CONFUSION) }
  protected angleSnappingControl() { if (this.state === 1 || this.state === 2) S.setAngleSnapping(true, this.referencePoint); else S.setAngleSnapping(false) }
  protected createShape(onlyOutline: boolean) {
    this.shapeGeometry = []
    if (this.state === 1) { if (this.refLength > CONFUSION) this.shapeGeometry.push(constructionLine(this.referencePoint, this.startPoint)); return }
    if (Math.abs(this.scaleFactor) < CONFUSION) return
    this.shapeGeometry = XF.scaleShape(doc(), this.list, this.referencePoint, this.scaleFactor, this.deleteOriginal).geometry
    if (onlyOutline) this.shapeGeometry.push(constructionLine(this.referencePoint, this.startPoint), constructionLine(this.referencePoint, this.endPoint))
  }
  protected executeCommands() {
    if (this.scaleFactor <= CONFUSION || !Number.isFinite(this.scaleFactor)) throw new Error('Invalid scale factor. Scale factor must be a positive number.')
    try {
      S.openCommand('Scale geometries')
      const s = XF.scaleShape(doc(), this.list, this.referencePoint, this.scaleFactor, this.deleteOriginal)
      if (this.deleteOriginal) deleteOriginalGeos(this.list)
      const initial = S.getConstraints().length
      addShapeThroughPython(s.geometry, s.constraints)
      const cs = [...S.getConstraints()]
      // reassignConstraintNames: the originals are gone, so the copies take their names
      if (this.deleteOriginal) s.constraints.forEach((c, i) => { if (c.name && cs[initial + i]) cs[initial + i] = { ...cs[initial + i], name: c.name } })
      // scaleLabels: the datum labels scaled with the shape (a radius's or diameter's position is an angle)
      const k = Math.fround(this.scaleFactor)
      for (const l of s.labels) {
        const id = l.constrId + initial, c = cs[id]
        if (!c) continue
        cs[id] = { ...c, labelDistance: Math.fround(l.distance * k), labelPosition: c.type === 'Radius' || c.type === 'Diameter' ? l.position : Math.fround(l.position * k) }
      }
      S.setConstraints(cs)
      S.commitCommand()
    } catch (e) { failed(e, 'Failed to scale') }
  }
  isWidgetVisible() { return true }
  toolWidgetText() { return 'Scale Parameters' }
  toolIcon() { return 'Sketcher_Scale' }
  ovpSpec(): OvpSpec { return { ovps: 3, widget: { parameters: 0, checkboxes: 1, comboboxes: 0, lineEdits: 0 }, firstComboIsMethod: false } }
  ovpState(i: number) { return i < 2 ? 0 : 2 }
  configureToolWidget(c: Controller) {
    if (!c.init) c.setCheckboxLabel(0, 'Keep original geometries (U)')
    const o = c.onViewParameters
    o[OVP.First].setLabelType('DISTANCEX'); o[OVP.Second].setLabelType('DISTANCEY')
    o[OVP.Third].setLabelType('DISTANCE', 'Forced')
  }
  adaptDrawingToCheckboxChange(_c: Controller, i: number, v: boolean) { if (i === 0) this.deleteOriginal = !v }
  doEnforceControlParameters(c: Controller, p: XY): XY {
    const o = c.onViewParameters
    let q: XY = [p[0], p[1]]
    if (this.state === 0) {
      if (o[OVP.First].isSet) q = [o[OVP.First].getValue(), q[1]]
      if (o[OVP.Second].isSet) q = [q[0], o[OVP.Second].getValue()]
    } else if (this.state === 2 && o[OVP.Third].isSet) {
      const k = o[OVP.Third].getValue()
      this.refLength = 1
      this.startPoint = add(this.referencePoint, [1, 0])
      this.endPoint = add(this.referencePoint, [k, 0])
      q = this.endPoint
    }
    return q
  }
  adaptParameters(c: Controller, p: XY) {
    const o = c.onViewParameters
    if (this.state === 0) {
      if (!o[OVP.First].isSet) c.setOnViewParameterValue(OVP.First, p[0])
      if (!o[OVP.Second].isSet) c.setOnViewParameterValue(OVP.Second, p[1])
      const sameSign = p[0] * p[1] > 0
      o[OVP.First].setLabelAutoDistanceReverse(!sameSign); o[OVP.Second].setLabelAutoDistanceReverse(sameSign)
      o[OVP.First].setPoints([0, 0], p); o[OVP.Second].setPoints([0, 0], p)
    } else if (this.state === 2) {
      if (!o[OVP.Third].isSet) c.setOnViewParameterValue(OVP.Third, this.scaleFactor, 'None')
      o[OVP.Third].setPoints(this.referencePoint, this.endPoint)
    }
  }
  computeNextDrawSketchHandlerMode(c: Controller) {
    const o = c.onViewParameters
    if (this.state === 0) { if (o[OVP.First].isSet && o[OVP.Second].isSet) this.setNextState(1) }
    else if (this.state === 2) { if (o[OVP.Third].hasFinishedEditing) this.setNextState(this.states) }
  }
}

/** CmdSketcherSymmetry / Translate / Rotate / Scale::activated: the selected geometry (with a conic's or a
 *  B-spline's internal geometry), then the tool; the selection is cleared. */
export function transformCommand(kind: 'symmetry' | 'translate' | 'rotate' | 'scale') {
  const list = selectedGeoIds()
  if (list.length) {
    const H = { symmetry: SymmetryHandler, translate: TranslateHandler, rotate: RotateHandler, scale: ScaleHandler }[kind]
    S.activateHandler(new H(list))
  }
  S.clearSelection()
}
void SK

// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Sketcher/Gui/DrawSketchController.h: 2023 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/DrawSketchDefaultWidgetController.h: 2023 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/DrawSketchControllableHandler.h: 2023 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/DrawSketchKeyboardManager.cpp: 2023 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/SketcherToolDefaultWidget.cpp: 2022 Pierre-Louis Boyer
//   src/Mod/Sketcher/Gui/Utils.cpp: 2021 Abdullah Tahiri
//   src/Gui/EditableDatumLabel.cpp: 2023 Ondsel
//   src/Gui/SoDatumLabel.cpp: 2011 Luke Parry
//   src/Gui/QuantitySpinBox.cpp: 2014 Werner Mayer
// The on-view parameters and the Tool Parameters box of the Sketcher's tools. An on-view parameter is a
// Gui::EditableDatumLabel: a dimension drawn in the view (SoDatumLabel) with a spin box over its text while its state
// of the tool is current; typing in it sets the value (keyboard tracking), Enter or Tab finishes it and passes the focus
// on, a value set is enforced on the cursor (doEnforceControlParameters) and becomes a constraint when the shape is made
// (addConstraints). The keys a box does not take go on to the 3D view (DrawSketchKeyboardManager). The controller
// (DrawSketchController with DrawSketchDefaultWidgetController's widget part) runs the parameters of one tool; each
// tool's handler (sketchtools.ts) supplies the specialisations as methods (OvpTool).
import type { XY } from './solver'
import * as S from './sketcher'
import { saved } from './store'
import { interpretInput, numberLength, shownText, type DisplayUnit } from './quantity-input'
import type { Dims } from './units-data'
import { sketcherIcon } from './sketchdraw'
import * as SK from './sketch'

// ── preferences (User parameter:BaseApp/Preferences/…) ───────────────────────────────────────────────────────────
/** The Sketcher's parameters the tools read, by FreeCAD's path under Preferences ("Mod/Sketcher/Tools/OnViewParameterVisibility"). */
const PARAM_DEFAULTS: Record<string, number | boolean> = {
  'Mod/Sketcher/Tools/OnViewParameterVisibility': 1,
  'Mod/Sketcher/ContinuousCreationMode': true,
  'Mod/Sketcher/ShowCursorCoords': true,
}
export function sketcherParam<T extends number | boolean>(path: string, d?: T): T {
  const all = saved.get<Record<string, number | boolean>>('sketcherParams', {})
  return (path in all ? all[path] : d ?? PARAM_DEFAULTS[path]) as T
}
/** Sets parameters (null removes one); returns what they were, for setting back. */
export function setSketcherParams(ps: Record<string, number | boolean | null>): Record<string, number | boolean | null> {
  const all = { ...saved.get<Record<string, number | boolean>>('sketcherParams', {}) }, old: Record<string, number | boolean | null> = {}
  for (const [k, v] of Object.entries(ps)) {
    old[k] = k in all ? all[k] : null
    if (v === null) delete all[k]; else all[k] = v
  }
  saved.set('sketcherParams', all)
  return old
}
/** OnViewParameterVisibility: 0 None, 1 Dimensions only (the default), 2 Position and dimensions. */
export const ovpVisibilityPref = () => sketcherParam<number>('Mod/Sketcher/Tools/OnViewParameterVisibility')

// ── Gui::EditableDatumLabel ──────────────────────────────────────────────────────────────────────────────────────
export type LabelType = 'DISTANCE' | 'DISTANCEX' | 'DISTANCEY' | 'RADIUS' | 'DIAMETER' | 'ANGLE'
/** EditableDatumLabel::Function: a coordinate (Positioning), a dimension (Dimensioning), always shown (Forced). */
export type LabelFunction = 'Positioning' | 'Dimensioning' | 'Forced'
/** Base::Unit: Length, Angle, or One (a number without a unit, as a hyperbola's or parabola's parameter). */
export type Unit = 'Length' | 'Angle' | 'One'
/** A value's unit: a length, an angle, or None (Base::Unit(): a plain number, a count or a scale factor). */
export type ValueUnit = Unit | 'None'
const DIMS: Record<ValueUnit, Dims> = { Length: [1, 0, 0, 0, 0, 0, 0, 0], Angle: [0, 0, 0, 0, 0, 0, 0, 1], One: [0, 0, 0, 0, 0, 0, 0, 0], None: [0, 0, 0, 0, 0, 0, 0, 0] }
const CONFUSION = 1e-7

/** The labels shown now (an active label is drawn; one in edit has its box), for the drawing and the checks. */
const shown = new Set<EditableDatumLabel>()
let drawScheduled = false
function publishLabels() {
  if (drawScheduled) return
  drawScheduled = true
  queueMicrotask(() => {
    drawScheduled = false
    S.setEdit({ ovps: [...shown].filter((l) => l.isActive()).map((l) => l.drawn()) })
  })
}

/** DrawSketchKeyboardManager: where a key typed in an on-view parameter goes, the box (DSHControl) or the 3D view
 *  (ViewProvider). Digits, '-', '.', ',', Backspace, Delete and a paste start editing; Enter and Tab end it. */
export class DrawSketchKeyboardManager {
  mode: 'ViewProvider' | 'DSHControl' = 'ViewProvider'
  /** eventFilter for a key event on a box: true when it went to the 3D view (the box does not take it). */
  filter(e: KeyboardEvent, down: boolean): boolean {
    if (this.mode === 'DSHControl' && e.altKey) { forwardToView(e, down); return true } // Alt+key: to the view, mode kept
    if (e.key === 'Enter' || e.key === 'Tab') { this.mode = 'ViewProvider'; return false }
    this.mode = this.detect(e)
    if (this.mode === 'ViewProvider') { forwardToView(e, down); return true }
    return false
  }
  private detect(e: KeyboardEvent): 'ViewProvider' | 'DSHControl' {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'v') return 'DSHControl'
    if (e.key === 'Backspace' || e.key === 'Delete') return 'DSHControl'
    if (e.key.length === 1) { const ch = e.key; if (/\d/.test(ch) || ch === '-' || ch === '.' || ch === ',') return 'DSHControl' }
    return this.mode
  }
}
/** QApplication::sendEvent(vpViewer, keyEvent): the key as the 3D view gets it (ViewProviderSketch::keyPressed). */
function forwardToView(e: KeyboardEvent, down: boolean) {
  e.preventDefault()
  e.stopPropagation()
  S.handleKey(e, down)
}

export class EditableDatumLabel {
  isSet = false
  hasFinishedEditing = false
  private value = 0
  private editStartValue = 0
  private type: LabelType = 'DISTANCE'
  private fn: LabelFunction = 'Positioning'
  private pts: [XY, XY] = [[0, 0], [0, 0]]
  private param1 = 0
  private param2 = 0
  private param3 = 0
  private autoDistanceReverse = false
  private activatedColor = false
  private active = false
  /** label->string: the text drawn when no box is on it (" " while editing). */
  private text = ' '
  private unit: ValueUnit = 'Length'
  private locked = false
  box: HTMLInputElement | null = null
  private display: DisplayUnit | null = null
  private keymanager: DrawSketchKeyboardManager | null = null
  // the signals the controller connects (initNOnViewParameters)
  onValueChanged: (v: number) => void = () => {}
  onEditingFinished: (v: number) => void = () => {}
  onEditingCanceled: (v: number) => void = () => {}
  onFocusGained: () => void = () => {}
  onParameterUnset: () => void = () => {}
  onFinishEditingOnAllOVPs: () => void = () => {}

  constructor(private autoDistance = true, private avoidMouseCursor = true) {
    this.setDeactivatedColor()
    if (autoDistance) this.setLabelRecommendedDistance()
  }
  destroy() { this.deactivate(); shown.delete(this) }

  activate() {
    if (this.active) return
    this.active = true
    shown.add(this)
    publishLabels()
  }
  deactivate() {
    this.stopEdit()
    if (!this.active) return
    this.active = false
    shown.delete(this)
    publishLabels()
  }
  isActive() { return this.active }
  isInEdit() { return !!this.box }
  getValue() { return this.value }
  getFunction() { return this.fn }

  /** startEdit: visibleToMouse false (the default) makes the box transparent to the mouse
   *  (setSpinboxVisibleToMouse: WA_TransparentForMouseEvents), so the clicks and moves over it reach the 3D view. */
  startEdit(val: number, keymanager: DrawSketchKeyboardManager, visibleToMouse = false) {
    if (this.box) return
    this.resetLockedState()
    this.text = ' '
    this.keymanager = keymanager
    const box = document.createElement('input')
    box.className = 'ovp-box'
    box.spellcheck = false
    box.setAttribute('data-ovp', '')
    this.box = box
    this.unit = 'Length'
    this.value = val
    this.editStartValue = val
    this.setBoxText(val)
    box.addEventListener('keydown', (e) => this.key(e, true))
    box.addEventListener('keyup', (e) => this.key(e, false))
    box.addEventListener('input', () => this.edited())
    box.addEventListener('focus', () => this.onFocusGained())
    box.addEventListener('pointerdown', (e) => e.stopPropagation())
    if (!visibleToMouse) box.style.pointerEvents = 'none'
    overlayHost()?.appendChild(box)
    this.updateGeometry()
    this.positionSpinbox()
    this.setFocusToSpinbox()
    publishLabels()
  }
  stopEdit(writeChanges = true) {
    const box = this.box
    if (!box) return
    const v = writeChanges ? this.boxQuantity() ?? this.editStartValue : this.editStartValue
    this.text = shownText({ value: v, dims: DIMS[this.unit] }).text
    const hadFocus = document.activeElement === box
    box.remove()
    this.box = null
    if (hadFocus) ensureViewFocus()
    publishLabels()
  }
  /** The box's value, when its text is valid (QuantitySpinBox::rawValue after hasValidInput). */
  private boxQuantity(): number | null {
    const box = this.box
    if (!box) return null
    const r = interpretInput(box.value, { dims: DIMS[this.unit], display: this.display ?? shownText({ value: 0, dims: DIMS[this.unit] }).display, phase: 'editing' })
    return r.status === 'ok' ? r.q.value : null
  }
  private hasValidInput() { return this.boxQuantity() !== null }
  private setBoxText(v: number) {
    const s = shownText({ value: v, dims: DIMS[this.unit] })
    this.display = s.display
    if (this.box) this.box.value = s.text
  }
  /** syncValueFromSpinBox. */
  private syncValueFromSpinBox(emitParameterUnset = false): boolean {
    const q = this.boxQuantity()
    if (q === null) {
      if (emitParameterUnset) { this.resetLockedState(); this.onParameterUnset() }
      return false
    }
    this.value = q
    this.isSet = true
    if (this.hasFinishedEditing) this.setLockedAppearance(true)
    return true
  }
  /** QuantitySpinBox::userInput with keyboard tracking: each valid edit is a new value (handleSpinBoxValueChanged);
   *  an emptied box clears the parameter (inputCleared, handleSpinBoxInputCleared). */
  private edited() {
    const box = this.box
    if (!box) return
    if (box.value.trim() === '') {
      if (!this.isSet && !this.hasFinishedEditing) return
      this.isSet = false
      this.resetLockedState()
      this.onParameterUnset()
      return
    }
    if (this.syncValueFromSpinBox()) { this.activatedColor = true; this.onValueChanged(this.value) }
    this.updateGeometry()
  }
  /** EditableDatumLabel::eventFilter, after the keyboard manager's (installed last, so it runs first). */
  private key(e: KeyboardEvent, down: boolean) {
    if (this.keymanager?.filter(e, down)) return
    if (!down) return
    if (e.key === 'Escape') {
      e.preventDefault(); e.stopPropagation()
      this.value = this.editStartValue
      this.isSet = false
      this.hasFinishedEditing = false
      this.setLockedAppearance(false)
      this.setSpinboxValue(this.editStartValue, this.unit)
      this.stopEdit()
      this.onEditingCanceled(this.value)
      return
    }
    if (e.key === 'Enter' || e.key === 'Tab') {
      e.preventDefault(); e.stopPropagation()
      // Tab with nothing typed only cycles (the box keeps the event: QAbstractSpinBox does nothing with it)
      if (e.key === 'Tab' && !this.isSet) { if (!this.hasValidInput()) this.syncValueFromSpinBox(); return }
      if (e.ctrlKey || e.metaKey) { this.onFinishEditingOnAllOVPs(); return }
      this.hasFinishedEditing = true
      if (!this.syncValueFromSpinBox()) return
      this.activatedColor = true
      this.onEditingFinished(this.value)
      return
    }
    if (this.hasFinishedEditing) this.resetLockedState()
    e.stopPropagation() // the box's own keys (the global shortcuts never see them: QLineEdit's ShortcutOverride)
  }
  setSpinboxValue(val: number, unit: ValueUnit = 'Length') {
    this.value = val
    this.unit = unit
    if (!this.box) { this.text = shownText({ value: val, dims: DIMS[unit] }).text; publishLabels(); return }
    this.setBoxText(val)
    this.updateGeometry()
    this.positionSpinbox()
    if (document.activeElement === this.box) this.selectNumber()
  }
  private selectNumber() { const b = this.box; if (b) { const n = numberLength(b.value); if (n > 0) b.setSelectionRange(0, n) } }
  setFocusToSpinbox() {
    const b = this.box
    if (!b) return
    if (document.activeElement !== b) { b.focus({ preventScroll: true }); this.selectNumber() }
  }
  /** spinBox->adjustSize(): as wide as its text. */
  private updateGeometry() {
    const b = this.box
    if (!b) return
    b.style.width = `${Math.max(3, b.value.length + (this.locked ? 2 : 0)) + 1}ch`
  }
  /** positionSpinbox: centred on the label's text, kept in the view, moved off the cursor. */
  positionSpinbox() {
    const b = this.box
    if (!b) return
    const vp = S.viewSize()
    if (!vp) return
    const [px, py] = S.toScreen(this.textCenter())
    const w = b.offsetWidth || 60, h = b.offsetHeight || 20
    let x = Math.min(Math.max(px - w / 2, 0), vp.w - w), y = Math.min(Math.max(py - h / 2, 0), vp.h - h)
    if (this.avoidMouseCursor) {
      const c = S.cursorScreen()
      const margin = Math.trunc(h * 0.7)
      if (c && c[0] > x - margin && c[0] < x + w + margin && c[1] > y - margin && c[1] < y + h + margin) y = c[1] + (c[1] > py ? -h - margin : margin)
    }
    b.style.left = `${vp.left + x}px`
    b.style.top = `${vp.top + y}px`
  }
  /** SoDatumLabel::getLabelTextCenter. */
  textCenter(): XY {
    const [p1, p2] = this.pts
    if (this.type === 'DISTANCE' || this.type === 'DISTANCEX' || this.type === 'DISTANCEY') {
      const eps = 1.1920929e-7
      let dir: XY = this.type === 'DISTANCE' ? [p2[0] - p1[0], p2[1] - p1[1]] : this.type === 'DISTANCEX' ? [p2[0] - p1[0] >= eps ? 1 : -1, 0] : [0, p2[1] - p1[1] >= eps ? 1 : -1]
      const l = Math.hypot(dir[0], dir[1]); dir = l ? [dir[0] / l, dir[1] / l] : [0, 0]
      const normal: XY = [-dir[1], dir[0]]
      const np = (p2[0] - p1[0]) * normal[0] + (p2[1] - p1[1]) * normal[1]
      const p1_: XY = [p1[0] + np * normal[0], p1[1] + np * normal[1]]
      const mid: XY = [(p1_[0] + p2[0]) / 2, (p1_[1] + p2[1]) / 2]
      return [mid[0] + normal[0] * this.param1 + dir[0] * this.param2, mid[1] + normal[1] * this.param1 + dir[1] * this.param2]
    }
    if (this.type === 'RADIUS' || this.type === 'DIAMETER') {
      let dir: XY = [p2[0] - p1[0], p2[1] - p1[1]]
      const l = Math.hypot(dir[0], dir[1]); dir = l ? [dir[0] / l, dir[1] / l] : [0, 0]
      return [p2[0] + this.param1 * dir[0], p2[1] + this.param1 * dir[1]]
    }
    // ANGLE: getAngleTextCenter(p0, start, range, 2 × length), the middle of the arc
    const r = 2 * this.param1, mid = this.param2 + 0.5 * this.param3
    return [p1[0] + r * Math.cos(mid), p1[1] + r * Math.sin(mid)]
  }
  setPoints(p1: XY, p2: XY) {
    this.pts = [[p1[0], p1[1]], [p2[0], p2[1]]]
    this.positionSpinbox()
    if (this.autoDistance) this.setLabelRecommendedDistance()
    publishLabels()
  }
  setLabelType(type: LabelType, fn: LabelFunction = 'Positioning') { this.type = type; this.fn = fn }
  setLabelDistance(v: number) { this.param1 = v; publishLabels() }
  setLabelStartAngle(v: number) { this.param2 = v; publishLabels() }
  setLabelRange(v: number) { this.param3 = v; publishLabels() }
  /** setLabelRecommendedDistance: 3% of the view's width plus height (getDimensions), whatever the zoom. */
  setLabelRecommendedDistance() {
    const d = S.viewDimensions()
    if (!d) return
    this.param1 = (this.autoDistanceReverse ? -1 : 1) * (d[0] + d[1]) * 0.03
  }
  setLabelAutoDistanceReverse(v: boolean) { this.autoDistanceReverse = v }
  setActivatedColor() { this.activatedColor = true; publishLabels() }
  setDeactivatedColor() { this.activatedColor = false; publishLabels() }
  setLockedAppearance(locked: boolean) {
    this.locked = locked
    if (this.box) { this.box.classList.toggle('locked', locked); this.box.style.backgroundImage = locked ? `url(${sketcherIcon('Constraint_Lock')})` : ''; this.updateGeometry() }
    publishLabels()
  }
  resetLockedState() { this.hasFinishedEditing = false; this.setLockedAppearance(false) }
  /** What the overlay draws for it (SoDatumLabel: lineWidth 2, size 17, ConstrainedDimColor or DeactivatedConstrDimColor). */
  drawn() {
    if (this.autoDistance) this.setLabelRecommendedDistance()
    return { kind: this.type, pts: this.pts as XY[], text: this.box ? ' ' : this.text, param1: this.param1, param2: this.param2, param3: this.param3, focus: this.activatedColor, locked: this.locked }
  }
  /** For the checks: the box's text and whether it has the focus (fcsketch_dump.py's ovp_out). */
  state() { return this.box ? { text: this.box.value, focus: document.activeElement === this.box } : null }
}

// ── the view the boxes sit over ──────────────────────────────────────────────────────────────────────────────────
function overlayHost(): HTMLElement | null { return document.body }
/** ViewProviderSketch::ensureFocus: the keys go to the 3D view again. */
export function ensureViewFocus() {
  const a = document.activeElement as HTMLElement | null
  if (a?.hasAttribute?.('data-ovp')) a.blur()
}
/** The camera moved or the view was drawn again: the boxes follow their labels (the camera sensor). */
export function repositionBoxes() { for (const l of shown) l.positionSpinbox() }
S.onOverlayDrawn(repositionBoxes)
/** For the checks (sketchcheck.mjs): the boxes over the view. */
export function ovpStates() { return [...shown].map((l) => l.state()).filter((x): x is { text: string; focus: boolean } => !!x) }

// ── the tool's widget (SketcherToolDefaultWidget) ───────────────────────────────────────────────────────────────
/** A widget parameter's unit: a length, an angle, or none (Base::Unit(): a count, as the polygon's sides). */
export type WidgetUnit = ValueUnit
export type WidgetParameter = { label: string; value: number; unit: ValueUnit; visible: boolean; enabled: boolean; isSet: boolean; min?: number; max?: number; decimals?: number }
export type WidgetCheckbox = { label: string; checked: boolean; visible: boolean; toolTip: string; icon?: string; prefEntry: string }
export type WidgetCombobox = { label: string; items: { text: string; icon?: string }[]; index: number; visible: boolean; prefEntry: string }
export type ToolWidget = {
  title: string; icon: string
  parameters: WidgetParameter[]; checkboxes: WidgetCheckbox[]; comboboxes: WidgetCombobox[]
  notice: string; noticeVisible: boolean
  /** What the box's controls report back (the controller's slots). */
  onParameter(i: number, v: number): void; onCheckbox(i: number, v: boolean): void; onCombobox(i: number, v: number): void
  onParameterTab(i: number): void
  /** A box of the widget to focus (setParameterFocus): its index, and a counter so that the same one can be asked again. */
  focus: { parameter: number; seq: number }
}
const N_PARAMETERS = 10, N_CHECKBOXES = 4, N_COMBOBOXES = 3
let widget: ToolWidget | null = null
let widgetVisible = false
const widgetSubs = new Set<() => void>()
let widgetVersion = 0
function widgetChanged() { widgetVersion++; widgetSubs.forEach((f) => f()) }
export const subscribeToolWidget = (f: () => void) => { widgetSubs.add(f); return () => { widgetSubs.delete(f) } }
export const toolWidgetVersion = () => widgetVersion
/** TaskSketcherTool: the widget shown in the Tool Parameters box (TaskDlgEditSketch::slotToolChanged), or null. */
export const getToolWidget = () => (widgetVisible ? widget : null)
/** For the checks: the box's title and its visible controls, as fcsketch_dump.py's tool_widget_out lists them. */
export function toolWidgetState() {
  const w = getToolWidget()
  if (!w) return null
  const controls: Record<string, unknown>[] = []
  const names = ['One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten']
  w.comboboxes.forEach((c, i) => { if (c.visible) controls.push({ name: `comboBox${i + 1}`, items: c.items.map((x) => x.text), index: c.index }) })
  w.parameters.forEach((p, i) => { if (p.visible) controls.push({ name: `parameter${names[i]}`, value: p.value }) })
  w.checkboxes.forEach((c, i) => { if (c.visible) controls.push({ name: `checkBoxTS${i + 1}`, text: c.label, checked: c.checked }) })
  // the order Qt's findChildren gives: the .ui's order (combos, line edits, parameters, check boxes)
  return { title: w.title, controls }
}
function newWidget(): ToolWidget {
  return {
    title: 'Tool Parameters', icon: 'document-new', notice: '', noticeVisible: false, focus: { parameter: -1, seq: 0 },
    parameters: Array.from({ length: N_PARAMETERS }, (_, i) => ({ label: `Parameter ${i + 1}`, value: 0, unit: 'Length' as Unit, visible: false, enabled: true, isSet: false })),
    checkboxes: Array.from({ length: N_CHECKBOXES }, (_, i) => ({ label: `Checkbox ${i + 1}`, checked: false, visible: false, toolTip: `Checkbox ${i + 1} toolTip`, prefEntry: '' })),
    comboboxes: Array.from({ length: N_COMBOBOXES }, (_, i) => ({ label: i === 0 ? 'Mode (M)' : 'Mode', items: [], index: 0, visible: false, prefEntry: '' })),
    onParameter() {}, onCheckbox() {}, onCombobox() {}, onParameterTab() {},
  }
}

// ── the controller ───────────────────────────────────────────────────────────────────────────────────────────────
/** What a tool's handler gives its controller: the counts per construction method (OnViewParameters<…>,
 *  WidgetParameters<…>, …) and the specialisations (DSH…Controller::…). */
export interface OvpTool {
  currentState(): number
  readonly endState: number
  isLastState(): boolean
  constructionMethod(): number
  setConstructionMethod(m: number): void
  readonly constructionMethodsCount: number
  readonly continuousMode: boolean
  mouseMove(p: XY): void
  reset(): void
  resetControls(): void
  updateCursor(): void
  setNextState(s: number | null): void
  getNextState(): number | null
  applyNextState(): void
  cancelCurrentAction(): void
  preselectAtPoint(p: XY): void
  updateDataAndDrawToPosition(p: XY): void
  drawPositionAtCursor(p: XY): void
  drawDirectionAtCursor(p: XY, origin: XY): void
  drawWidthHeightAtCursor(p: XY, a: number, b: number): void
  drawDoubleAtCursor(p: XY, v: number, unit: Unit): void
  isWidgetVisible(): boolean
  toolWidgetText(): string
  toolIcon(): string
  // the specialisations, per tool
  ovpSpec(): OvpSpec
  ovpState(i: number): number
  configureOnViewParameters(c: Controller): void
  configureToolWidget(c: Controller): void
  doEnforceControlParameters(c: Controller, p: XY): XY
  adaptParameters(c: Controller, p: XY): void
  computeNextDrawSketchHandlerMode(c: Controller): void
  addConstraints(c: Controller): void
  addStepConstraints(c: Controller): void
  adaptDrawingToOnViewParameterChange(c: Controller, i: number, v: number): void
  adaptDrawingToParameterChange(c: Controller, i: number, v: number): void
  adaptDrawingToCheckboxChange(c: Controller, i: number, v: boolean): void
  adaptDrawingToComboboxChange(c: Controller, i: number, v: number): boolean
  doConstructionMethodChanged(c: Controller): void
  resetOnConstructionMethodChanged(): boolean
  firstKeyShortcut?(c: Controller): boolean
  secondKeyShortcut?(c: Controller): boolean
  thirdKeyShortcut?(c: Controller): boolean
  fourthKeyShortcut?(c: Controller): boolean
}
/** The amounts for the current construction method; widget null for a DrawSketchController without a default widget. */
export type OvpSpec = { ovps: number; widget: { parameters: number; checkboxes: number; comboboxes: number; lineEdits: number } | null; firstComboIsMethod: boolean }

export class Controller {
  onViewParameters: EditableDatumLabel[] = []
  init = false
  parameterWithFocus = 0
  prevCursorPosition: XY = [0, 0]
  private lastControlEnforcedPosition: XY = [0, 0]
  private firstMoveInit = false
  focusAutoPassing = true
  private dynamicOverride = false
  private keymanager = new DrawSketchKeyboardManager()
  toolWidget: ToolWidget | null = null
  private nParameter = 0; private nCheckbox = 0; private nCombobox = 0; private nLineEdit = 0
  private blockWidget = false

  constructor(readonly handler: OvpTool) {}

  // ── NVI ──
  /** initControls: the widget (TaskSketcherTool made it on activation), then the controls reset. */
  initControls() {
    const spec = this.handler.ovpSpec()
    widget = spec.widget || this.handler.isWidgetVisible() ? newWidget() : null
    widgetVisible = !!widget && this.handler.isWidgetVisible()
    this.toolWidget = widget
    if (widget) {
      widget.title = this.handler.toolWidgetText() || 'Tool Parameters'
      widget.icon = this.handler.toolIcon() || 'document-new'
      widget.onParameter = (i, v) => { if (!this.blockWidget) this.parameterValueChanged(i, v) }
      widget.onCheckbox = (i, v) => { widgetChanged(); if (!this.blockWidget) this.checkboxCheckedChanged(i, v) }
      widget.onCombobox = (i, v) => { widgetChanged(); if (!this.blockWidget) this.comboboxSelectionChanged(i, v) }
      widget.onParameterTab = () => this.passFocusToNextParameter()
    }
    this.resetControls()
    this.init = true
    widgetChanged()
  }
  /** The tool goes (DrawSketchHandler::deactivate): its labels and widget with it. */
  dispose() {
    for (const l of this.onViewParameters) l.destroy()
    this.onViewParameters = []
    if (this.toolWidget === widget) { widget = null; widgetVisible = false; widgetChanged() }
  }
  resetControls() {
    ensureViewFocus()
    this.resetOnViewParameters()
    if (this.toolWidget) this.resetDefaultWidget()
    this.firstMoveInit = false
  }
  mouseMoved(_p: XY) {
    if (!this.firstMoveInit) this.setModeOnViewParameters()
    this.firstMoveInit = true
  }
  /** enforceControlParameters: the position the parameters set make of the cursor's; null when not finite. */
  enforceControlParameters(p: XY): XY | null {
    const q = this.handler.doEnforceControlParameters(this, [p[0], p[1]])
    if (!Number.isFinite(q[0]) || !Number.isFinite(q[1])) return null
    this.prevCursorPosition = q
    this.lastControlEnforcedPosition = q
    // the focus back on the current parameter, in case the user worked outside the 3D view
    if (this.focusAutoPassing && this.parameterWithFocus >= 0) this.setFocusToOnViewParameter(this.parameterWithFocus)
    return q
  }
  onConstructionMethodChanged() {
    this.handler.doConstructionMethodChanged(this)
    this.handler.updateCursor()
    if (this.handler.resetOnConstructionMethodChanged()) this.handler.reset()
    this.handler.mouseMove(this.prevCursorPosition)
  }
  onViewValueChanged(i: number, value: number) {
    try { this.tryViewValueChanged(i, value) } catch (e) { console.error('C++ exception in onViewValueChanged:', e) }
  }
  finishEditingOnAllOVPs() {
    const initialState = this.handler.currentState()
    this.onViewParameters.forEach((p, i) => {
      if (this.isOnViewParameterOfCurrentMode(i) && this.isOnViewParameterVisible(i) && initialState === this.handler.ovpState(i)) {
        p.isSet = true
        p.hasFinishedEditing = true
        this.onViewValueChanged(i, p.getValue())
      }
    })
  }
  private tryViewValueChanged(i: number, value: number) {
    // on Enter the focus goes on to the next parameter of the state not yet finished, round to the first
    if (this.onViewParameters[i].hasFinishedEditing) {
      const next = (start: number) => { for (let k = start; k < this.onViewParameters.length; k++) if (this.isOnViewParameterOfCurrentMode(k) && !this.onViewParameters[k].hasFinishedEditing) return k; return -1 }
      const first = next(0), after = next(i + 1)
      if (after !== -1) this.setFocusToOnViewParameter(after)
      else if (first !== -1) this.setFocusToOnViewParameter(first)
    }
    this.handler.adaptDrawingToOnViewParameterChange(this, i, value)
    this.finishControlsChanged()
  }
  adaptParameters(p?: XY) { this.handler.adaptParameters(this, p ?? this.lastControlEnforcedPosition) }
  onHandlerModeChanged() { this.setModeOnViewParameters() }
  afterHandlerModeChanged() {
    if (this.handler.currentState() !== this.handler.endState || this.handler.continuousMode) this.handler.mouseMove(this.prevCursorPosition)
  }
  tabShortcut() { this.passFocusToNextParameter() }
  firstKeyShortcut() { if (this.handler.firstKeyShortcut?.(this)) return; if (this.nCheckbox >= 1) this.setCheckboxChecked(0, !this.getCheckboxChecked(0)) }
  secondKeyShortcut() { if (this.handler.secondKeyShortcut?.(this)) return; if (this.nCheckbox >= 2) this.setCheckboxChecked(1, !this.getCheckboxChecked(1)) }
  thirdKeyShortcut() { if (this.handler.thirdKeyShortcut?.(this)) return; if (this.nCheckbox >= 3) this.setCheckboxChecked(2, !this.getCheckboxChecked(2)) }
  fourthKeyShortcut() { if (this.handler.fourthKeyShortcut?.(this)) return; if (this.nCheckbox >= 4) this.setCheckboxChecked(3, !this.getCheckboxChecked(3)) }
  drawPositionAtCursor(p: XY) { if (this.visibility() !== 2) this.handler.drawPositionAtCursor(p) }
  drawDirectionAtCursor(p: XY, origin: XY) { if (this.visibility() === 0) this.handler.drawDirectionAtCursor(p, origin) }
  drawWidthHeightAtCursor(p: XY, a: number, b: number) { if (this.visibility() === 0) this.handler.drawWidthHeightAtCursor(p, a, b) }
  drawDoubleAtCursor(p: XY, v: number, unit: Unit = 'Length') { if (this.visibility() === 0) this.handler.drawDoubleAtCursor(p, v, unit) }

  // ── helpers ──
  /** setMode: a mode enum of the handler set from a control, the cursor and the controls redone. */
  setMode(set: () => void) { set(); this.handler.updateCursor(); this.handler.resetControls() }
  /** finishControlsChanged: redraw where the cursor was, preselect what lies there (so the auto-constraints come), and
   *  go to the next state if the parameters completed this one. */
  finishControlsChanged() {
    this.handler.mouseMove(this.prevCursorPosition)
    const currentState = this.handler.currentState()
    this.handler.preselectAtPoint(this.lastControlEnforcedPosition)
    this.handler.updateDataAndDrawToPosition(this.lastControlEnforcedPosition)
    this.handler.computeNextDrawSketchHandlerMode(this)
    const nextState = this.handler.getNextState()
    const reprocess = nextState !== null && nextState !== this.handler.endState && nextState !== currentState && this.firstMoveInit
    this.handler.applyNextState()
    if (reprocess) this.handler.mouseMove(this.prevCursorPosition)
  }
  private initNOnViewParameters(n: number) {
    for (const l of this.onViewParameters) l.destroy()
    this.onViewParameters = []
    for (let i = 0; i < n; i++) {
      const p = new EditableDatumLabel(true, true)
      const changed = (v: number) => { p.setActivatedColor(); this.onViewValueChanged(i, v) }
      p.onValueChanged = changed
      p.onEditingFinished = changed
      p.onEditingCanceled = () => this.handler.cancelCurrentAction()
      p.onFocusGained = () => { this.parameterWithFocus = i }
      p.onParameterUnset = () => { this.unsetOnViewParameter(p); this.finishControlsChanged() }
      p.onFinishEditingOnAllOVPs = () => this.finishEditingOnAllOVPs()
      this.onViewParameters.push(p)
    }
  }
  /** unsetOnViewParameter: the parameter takes the cursor's value again. */
  unsetOnViewParameter(p: EditableDatumLabel) {
    p.isSet = false
    p.hasFinishedEditing = false
    p.setDeactivatedColor()
    p.setLockedAppearance(false)
  }
  setOnViewParameterValue(i: number, val: number, unit: ValueUnit = 'Length') {
    if (this.isOnViewParameterVisible(i)) this.onViewParameters[i].setSpinboxValue(val, unit)
  }
  /** setModeOnViewParameters: the current state's parameters in edit (the first last, so that it keeps the focus). */
  setModeOnViewParameters() {
    this.dynamicOverride = false
    const end = this.handler.currentState() === this.handler.endState
    this.onViewParameters.forEach((p, i) => {
      if (this.isOnViewParameterOfCurrentMode(i)) return
      p.stopEdit()
      if (!p.isSet || end) p.deactivate()
    })
    for (let i = this.onViewParameters.length - 1; i >= 0; i--) {
      if (this.isOnViewParameterOfCurrentMode(i) && this.isOnViewParameterVisible(i)) this.activateOnViewParameter(i)
    }
  }
  activateOnViewParameter(i: number) {
    const p = this.onViewParameters[i]
    if (!p) return
    if (!p.isActive()) { p.setPoints(this.prevCursorPosition, this.prevCursorPosition); p.activate() }
    p.startEdit(0, this.keymanager)
  }
  deactivateOnViewParameter(i: number) { const p = this.onViewParameters[i]; if (p) { p.stopEdit(); p.deactivate() } }
  setFocusToOnViewParameter(i: number): boolean {
    if (i < this.onViewParameters.length && this.isOnViewParameterVisible(i)) {
      this.onViewParameters[i].setFocusToSpinbox()
      this.parameterWithFocus = i
      return true
    }
    return false
  }
  /** passFocusToNextParameter (DrawSketchDefaultWidgetController's, which DrawSketchController's is with no widget):
   *  the next parameter of this state, then the widget's boxes, round to the first. */
  passFocusToNextParameter() {
    const nOvp = this.onViewParameters.length, total = nOvp + this.nParameter + this.nLineEdit
    let index = this.parameterWithFocus + 1
    if (index >= total) index = 0
    const trySet = (idx: number): boolean => {
      while (idx < nOvp) { if (this.isOnViewParameterOfCurrentMode(idx) && this.isOnViewParameterVisible(idx)) { this.setFocusToParameter(idx); return true } idx++ }
      if (idx < nOvp + this.nParameter) { if (this.nParameter > 0) { this.setFocusToParameter(idx); return true } idx = nOvp + this.nParameter }
      if (idx < total && this.nLineEdit > 0) { this.setFocusToParameter(idx); return true }
      return false
    }
    if (!trySet(index)) trySet(0)
  }
  private setFocusToParameter(i: number) {
    if (this.setFocusToOnViewParameter(i)) return
    const w = i - this.onViewParameters.length
    if (w < this.nParameter && this.toolWidget) { this.toolWidget.focus = { parameter: w, seq: this.toolWidget.focus.seq + 1 }; this.parameterWithFocus = i; widgetChanged() }
  }
  isOnViewParameterOfCurrentMode(i: number) { return i < this.onViewParameters.length && this.handler.ovpState(i) === this.handler.currentState() }
  isOnViewParameterOfPreviousMode(i: number) { return i < this.onViewParameters.length && this.handler.ovpState(i) < this.handler.currentState() }
  /** OnViewParameterVisibilityManager::isVisible. */
  isOnViewParameterVisible(i: number) {
    const p = this.onViewParameters[i]
    if (!p) return false
    if (p.getFunction() === 'Forced') return true
    switch (this.visibility()) {
      case 0: return this.dynamicOverride
      case 1: return (p.getFunction() === 'Dimensioning') !== this.dynamicOverride
      case 2: return !this.dynamicOverride
    }
    return false
  }
  toggleDynamicOverride() { this.dynamicOverride = !this.dynamicOverride }
  private visibility() { return ovpVisibilityPref() }
  resetOnViewParameters() {
    this.initNOnViewParameters(this.handler.ovpSpec().ovps)
    this.parameterWithFocus = 0
    this.handler.configureOnViewParameters(this)
  }
  // ── the widget (DrawSketchDefaultWidgetController) ──
  private parameterValueChanged(i: number, v: number) {
    this.handler.adaptDrawingToParameterChange(this, i, v)
    this.focusAutoPassing = false
    this.finishControlsChanged()
    this.focusAutoPassing = true
  }
  private checkboxCheckedChanged(i: number, v: boolean) {
    const cb = this.toolWidget?.checkboxes[i]
    if (cb?.prefEntry) setSketcherParams({ [`Mod/Sketcher/Tools/${cb.prefEntry}`]: v })
    this.handler.adaptDrawingToCheckboxChange(this, i, v)
    this.finishControlsChanged()
  }
  private comboboxSelectionChanged(i: number, v: number) {
    const cb = this.toolWidget?.comboboxes[i]
    if (cb?.prefEntry) setSketcherParams({ [`Mod/Sketcher/Tools/${cb.prefEntry}`]: v })
    if (!this.handler.adaptDrawingToComboboxChange(this, i, v)) {
      // the default: the first combo box is the construction method
      if (this.handler.ovpSpec().firstComboIsMethod && i === 0 && this.handler.constructionMethodsCount > 1) this.handler.setConstructionMethod(v)
    }
    this.finishControlsChanged()
  }
  private resetDefaultWidget() {
    const w = this.toolWidget!
    const spec = this.handler.ovpSpec().widget ?? { parameters: 0, checkboxes: 0, comboboxes: 0, lineEdits: 0 }
    this.blockWidget = true
    try {
      this.nParameter = spec.parameters; this.nCheckbox = spec.checkboxes; this.nCombobox = spec.comboboxes; this.nLineEdit = spec.lineEdits
      w.parameters.forEach((p, i) => { p.visible = i < this.nParameter; p.value = 0; p.isSet = false })
      w.checkboxes.forEach((c, i) => { c.visible = i < this.nCheckbox; c.checked = false })
      w.comboboxes.forEach((c, i) => { c.visible = i < this.nCombobox })
      this.handler.configureToolWidget(this)
      if (this.handler.ovpSpec().firstComboIsMethod && w.comboboxes[0].index !== this.handler.constructionMethod()) w.comboboxes[0].index = this.handler.constructionMethod()
    } finally { this.blockWidget = false }
    widgetChanged()
  }
  // SketcherToolDefaultWidget's setters, for the specialisations
  setParameterLabel(i: number, s: string) { const p = this.toolWidget?.parameters[i]; if (p) { p.label = s; widgetChanged() } }
  setParameter(i: number, v: number) { const p = this.toolWidget?.parameters[i]; if (p) { p.value = v; p.isSet = true; widgetChanged(); this.toolWidget!.onParameter(i, v) } }
  setParameterWithoutPassingFocus(i: number, v: number) { this.setParameter(i, v) }
  configureParameterInitialValue(i: number, v: number) { const p = this.toolWidget?.parameters[i]; if (p) { p.value = v; widgetChanged() } }
  configureParameterUnit(i: number, u: ValueUnit) { const p = this.toolWidget?.parameters[i]; if (p) { p.unit = u; widgetChanged() } }
  configureParameterMin(i: number, v: number) { const p = this.toolWidget?.parameters[i]; if (p) p.min = v }
  configureParameterMax(i: number, v: number) { const p = this.toolWidget?.parameters[i]; if (p) p.max = v }
  configureParameterDecimals(i: number, v: number) { const p = this.toolWidget?.parameters[i]; if (p) p.decimals = v }
  setParameterEnabled(i: number, on: boolean) { const p = this.toolWidget?.parameters[i]; if (p) { p.enabled = on; widgetChanged() } }
  getParameter(i: number) { return this.toolWidget?.parameters[i]?.value ?? 0 }
  isParameterSet(i: number) { return !!this.toolWidget?.parameters[i]?.isSet }
  updateVisualValue(i: number, v: number, u: ValueUnit = 'Length') { const p = this.toolWidget?.parameters[i]; if (p) { p.value = v; p.unit = u; widgetChanged() } }
  setCheckboxLabel(i: number, s: string) { const c = this.toolWidget?.checkboxes[i]; if (c) { c.label = s; widgetChanged() } }
  setCheckboxToolTip(i: number, s: string) { const c = this.toolWidget?.checkboxes[i]; if (c) c.toolTip = s }
  setCheckboxIcon(i: number, icon: string) { const c = this.toolWidget?.checkboxes[i]; if (c) c.icon = icon }
  /** setCheckboxPrefEntry + restoreCheckBoxPref: the box remembers its state (Gui::PrefCheckBox, under Mod/Sketcher/Tools). */
  setCheckboxPrefEntry(i: number, entry: string) {
    const c = this.toolWidget?.checkboxes[i]
    if (!c) return
    c.prefEntry = entry
    if (entry) c.checked = sketcherParam<boolean>(`Mod/Sketcher/Tools/${entry}`, c.checked)
  }
  getCheckboxChecked(i: number) { return !!this.toolWidget?.checkboxes[i]?.checked }
  /** setCheckboxChecked: as a click does (toggled, which the controller hears unless the widget is being reset). */
  setCheckboxChecked(i: number, v: boolean) {
    const c = this.toolWidget?.checkboxes[i]
    if (!c || c.checked === v) return
    c.checked = v
    widgetChanged()
    this.toolWidget!.onCheckbox(i, v)
  }
  setComboboxLabel(i: number, s: string) { const c = this.toolWidget?.comboboxes[i]; if (c) { c.label = s; widgetChanged() } }
  setComboboxElements(i: number, names: string[]) { const c = this.toolWidget?.comboboxes[i]; if (c) { c.items = names.map((text) => ({ text })); widgetChanged() } }
  setComboboxItemIcon(i: number, k: number, icon: string) { const c = this.toolWidget?.comboboxes[i]; if (c?.items[k]) c.items[k].icon = icon }
  setComboboxPrefEntry(i: number, entry: string) {
    const c = this.toolWidget?.comboboxes[i]
    if (!c) return
    c.prefEntry = entry
    if (entry) c.index = sketcherParam<number>(`Mod/Sketcher/Tools/${entry}`, c.index)
  }
  getComboboxIndex(i: number) { return this.toolWidget?.comboboxes[i]?.index ?? 0 }
  setComboboxIndex(i: number, v: number) {
    const c = this.toolWidget?.comboboxes[i]
    if (!c || c.index === v) return
    c.index = v
    widgetChanged()
    this.toolWidget!.onCombobox(i, v)
  }
  setNoticeText(s: string) { if (this.toolWidget) { this.toolWidget.notice = s; widgetChanged() } }
  setNoticeVisible(on: boolean) { if (this.toolWidget) { this.toolWidget.noticeVisible = on; widgetChanged() } }
  /** syncCheckboxToHandler: the box shows the handler's state (no signal: the widget is being configured). */
  syncCheckboxToHandler(i: number, v: boolean) {
    const c = this.toolWidget?.checkboxes[i]
    if (!c || c.checked === v) return
    const b = this.blockWidget
    this.blockWidget = true
    try { this.setCheckboxChecked(i, v) } finally { this.blockWidget = b }
  }
  /** syncConstructionMethodComboboxToHandler: the first combo box shows the handler's construction method. */
  syncConstructionMethodComboboxToHandler() {
    const c = this.toolWidget?.comboboxes[0]
    if (!c || !this.handler.ovpSpec().firstComboIsMethod || c.index === this.handler.constructionMethod()) return
    c.index = this.handler.constructionMethod()
    widgetChanged()
  }
  get keyManager() { return this.keymanager }
}

/** A controllable handler's parameter, by state: OnViewParameter::First, Second, … */
export const OVP = { First: 0, Second: 1, Third: 2, Fourth: 3, Fifth: 4, Sixth: 5, Seventh: 6, Eighth: 7, Ninth: 8, Tenth: 9 } as const
/** Precision::Confusion. */
export const PRECISION = CONFUSION

// ── SketcherGui's Utils.cpp: the constraints a parameter set makes ──────────────────────────────────────────────
/** printf's %f, as Gui::cmdAppObjectArgs writes a value into the Python command: six decimals. */
export const f6 = (v: number) => Number(v.toFixed(6))
/** ConstraintToAttachment: a point at a distance from the V axis (DistanceX), the H axis (DistanceY), or on an axis or
 *  the root point (distance 0: PointOnObject on a curve, Coincident on a point). */
export function constraintToAttachment(el: [number, SK.PointPos], att: [number, SK.PointPos], distance: number) {
  if (distance === 0) {
    if (att[1] === SK.NONE) S.addConstraint(SK.constraint('PointOnObject', el[0], el[1], att[0]))
    else S.addConstraint(SK.constraint('Coincident', el[0], el[1], att[0], att[1]))
  } else if (att[0] === SK.V_AXIS && att[1] === SK.NONE) S.addConstraint(SK.constraint('DistanceX', el[0], el[1], SK.GEO_UNDEF, SK.NONE, SK.GEO_UNDEF, SK.NONE, f6(distance)))
  else if (att[0] === SK.H_AXIS && att[1] === SK.NONE) S.addConstraint(SK.constraint('DistanceY', el[0], el[1], SK.GEO_UNDEF, SK.NONE, SK.GEO_UNDEF, SK.NONE, f6(distance)))
}
/** GeoElementId::RtPnt, VAxis, HAxis. */
export const RT_PNT_ID: [number, SK.PointPos] = [SK.RT_PNT, SK.START], V_AXIS_ID: [number, SK.PointPos] = [SK.V_AXIS, SK.NONE], H_AXIS_ID: [number, SK.PointPos] = [SK.H_AXIS, SK.NONE]
/** std::remainder. */
const remainder = (x: number, y: number) => x - Math.round(x / y) * y
/** ConstraintLineByAngle: a line at an angle to the H axis (Horizontal, Vertical, or Angle). */
export function constraintLineByAngle(geoId: number, angle: number) {
  if (Math.abs(remainder(angle, Math.PI)) < CONFUSION) S.addConstraint(SK.constraint('Horizontal', geoId))
  else if (Math.abs(remainder(angle, Math.PI / 2)) < CONFUSION) S.addConstraint(SK.constraint('Vertical', geoId))
  else S.addConstraint(SK.constraint('Angle', SK.H_AXIS, SK.NONE, geoId, SK.NONE, SK.GEO_UNDEF, SK.NONE, f6(angle)))
}
/** Constraint2LinesByAngle: Parallel, Perpendicular or the Angle between two lines. */
export function constraint2LinesByAngle(geoId1: number, geoId2: number, angle: number) {
  const modPi = angle % Math.PI, modHalfPi = angle % (Math.PI / 2)
  if (Math.abs(modPi) < CONFUSION) S.addConstraint(SK.constraint('Parallel', geoId1, SK.NONE, geoId2))
  else if (Math.abs(modHalfPi) < CONFUSION) S.addConstraint(SK.constraint('Perpendicular', geoId1, SK.NONE, geoId2))
  else S.addConstraint(SK.constraint('Angle', geoId1, SK.END, geoId2, SK.START, SK.GEO_UNDEF, SK.NONE, f6(angle)))
}

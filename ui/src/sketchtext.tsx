// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Sketcher/Gui/DrawSketchHandlerText.h: 2025 Pierre-Louis Boyer
//   src/Mod/Sketcher/Gui/EditTextDialog.cpp: 2025 Pierre-Louis Boyer
//   src/Mod/Sketcher/Gui/FontProvider.cpp: 2026 FreeCAD Project Association
//   src/Mod/Sketcher/App/SketchObject.cpp: 2008 Jürgen Riegel (setTextAndFont)
//   No copyright line in the file: src/Mod/Sketcher/Gui/EditTextDialog.ui
// Sketcher_CreateText: the handle line (a construction line from the first click to the second, the text's height or
// width), the Text constraint naming it and the glyphs, and EditTextDialog (a double click on the handle). The glyphs
// are FreeCAD's: `cad feature text` builds them on the server with FreeType and HarfBuzz as Part::makeTextWires does
// (cad_agent/sketch_text.py, held to FreeCAD 26.3 by tests/golden/sketchtext). The page asks it for the font list
// (FontProvider), for the text's outlines once per text and font (the tool's cachedBaseShapes, which the preview
// places itself), and for the exact glyphs of a handle when the text is made or edited; setTextAndFont's bookkeeping
// of geometry and constraints is done here, as the sketch's other operations are. The solver (ui/planegcs) leaves the
// glyphs out and moves them with the handle (Sketch::applyGroupTransformations).
import { useEffect, useState, useSyncExternalStore } from 'react'
import { createPortal } from 'react-dom'
import { api, resultText } from './api'
import type { Geo, XY } from './solver'
import { type Constraint, type PointPos, NONE, START, END, GEO_UNDEF, constraint, textConstraint } from './sketch'
import * as S from './sketcher'
import { Controller, OVP, f6, constraintToAttachment, constraintLineByAngle, RT_PNT_ID, V_AXIS_ID, H_AXIS_ID, type OvpSpec } from './sketchovp'
import { DefaultHandler, removeRedundantHorizontalVertical } from './sketchtools'
import { kernelBusy } from './sketchkernel'
import { messageBox } from './msgbox'
import { getState, report } from './store'
import './sketchtext.css'

const CONFUSION = 1e-7

// ── the server: `cad feature text` ──────────────────────────────────────────────────────────────────────────────
type Fonts = { fonts: string[]; paths: Record<string, string>; default: string | null }
type Shapes = { geometry: Geo[]; box: number[] | null }
type Req = { op: 'fonts' } | { op: 'shapes'; text: string; font: string }
  | { op: 'geometry'; text: string; font: string; p1: XY; p2: XY; height: boolean; construction: boolean }
const cache = new Map<string, Record<string, unknown>>()
const pending = new Map<string, Promise<Record<string, unknown>>>()
let inFlight = 0
const keyOf = (r: Req) => JSON.stringify(r)
async function fetchAnswer(r: Req): Promise<Record<string, unknown>> {
  const k = keyOf(r)
  const have = cache.get(k)
  if (have) return have
  let p = pending.get(k)
  if (!p) {
    p = (async () => {
      const slug = getState().slug
      if (!slug) throw new Error('no project for the sketch text')
      inFlight++
      try {
        const res = await api.cad(slug, ['feature', 'text', slug, '--req', JSON.stringify([r])])
        if (res.exit !== 0 || !res.data) throw new Error(`sketch text: ${resultText(res)}`)
        const a = ((res.data.answers ?? []) as Record<string, unknown>[])[0] ?? { error: 'no answer' }
        cache.set(k, a)
        return a
      } finally { inFlight--; pending.delete(k) }
    })()
    pending.set(k, p)
  }
  return p
}
/** The answer when it is in; else null, and then() runs once it is. */
function answerNow(r: Req, then?: () => void): Record<string, unknown> | null {
  const a = cache.get(keyOf(r))
  if (a) return a
  fetchAnswer(r).then(() => then?.(), (e) => report('err', e instanceof Error ? e.message : String(e)))
  return null
}
// the checks wait for the server's answers (sketchcheck.mjs reads cadKernelBusy)
;(globalThis as { cadKernelBusy?: () => number }).cadKernelBusy = () => kernelBusy() + inFlight

/** FontProvider's findAvailableFontFiles: the names (sorted case-insensitively), the file of each, the default. */
const fontsNow = (then?: () => void) => answerNow({ op: 'fonts' }, then) as Fonts | null
/** Base::FileInfo::fileNamePure: what Constraint::setFont keeps of a path. */
export function fileNamePure(path: string) {
  const name = path.replace(/\\/g, '/').split('/').pop() ?? path
  const dot = name.lastIndexOf('.')
  return dot >= 0 ? name.slice(0, dot) : name
}

// ── Part::transformAndConvertToGeometry, for the preview ────────────────────────────────────────────────────────
/** The base shapes (at 1 unit per em) fitted to the handle p1 -> p2: their box's corner to p1, scaled to the box's
 *  height (or width), turned to the handle (minus a quarter turn for the height). */
function placeShapes(sh: Shapes, p1: XY, p2: XY, height: boolean, construction: boolean): Geo[] {
  const d: XY = [p2[0] - p1[0], p2[1] - p1[1]], length = Math.hypot(d[0], d[1])
  if (!sh.box || !sh.geometry.length || length < CONFUSION) return []
  const [xmin, ymin, , xmax, ymax] = sh.box
  let scale: number, angle: number
  if (height) { if (ymax - ymin < CONFUSION) return []; scale = length / (ymax - ymin); angle = Math.atan2(d[1], d[0]) - Math.PI / 2 }
  else { if (xmax - xmin < CONFUSION) return []; scale = length / (xmax - xmin); angle = Math.atan2(d[1], d[0]) }
  const c = Math.cos(angle), s = Math.sin(angle)
  const at = (p: XY): XY => { const x = (p[0] - xmin) * scale, y = (p[1] - ymin) * scale; return [p1[0] + c * x - s * y, p1[1] + s * x + c * y] }
  return sh.geometry.map((g) => {
    const k = g.type === 'LineSegment' ? { ...g, start: at(g.start), end: at(g.end) }
      : g.type === 'BSplineCurve' ? { ...g, poles: g.poles.map(at) } : g
    return construction ? { ...k, construction: true } : k
  })
}

// ── SketchObject::setTextAndFont, with the glyphs the server made for the handle ────────────────────────────────
/** The request for the glyphs of the Text constraint at index, its handle as the sketch has it now. */
function glyphRequest(index: number, text: string, fontPath: string, height: boolean, construction: boolean): Req | null {
  const c = S.getConstraints()[index], geo = S.getGeometry()
  const handle = c?.elements?.[0]?.[0]
  const line = handle === undefined ? undefined : geo[handle]
  if (!line || line.type !== 'LineSegment') return null
  // construction: the glyphs' own once there are glyphs (setTextAndFont keeps them as they were)
  const first = c.elements?.[1]?.[0]
  const cons = first !== undefined && first !== GEO_UNDEF ? !!geo[first]?.construction : construction
  return { op: 'geometry', text, font: fontPath, p1: line.start, p2: line.end, height, construction: cons }
}
/** setTextAndFont(ConstrId, text, font, isHeight, isConstruction): the old glyphs deleted (which takes the old
 *  constraint along: a new one is added at the end), the new ones added after the sketch's geometry, the constraint
 *  naming the handle and them. glyphs: the server's answer for glyphRequest. */
function setTextAndFont(index: number, text: string, fontPath: string, height: boolean, glyphs: Geo[]): boolean {
  const c = S.getConstraints()[index]
  if (!c || c.type !== 'Text' || !c.elements?.length) return false
  let handle = c.elements[0][0]
  const firstText = c.elements[1]?.[0] ?? GEO_UNDEF
  const existing = firstText !== GEO_UNDEF, handleLast = handle > firstText
  if (existing) {
    const dele: number[] = []
    for (const [g] of c.elements.slice(1)) {
      if (g === GEO_UNDEF) continue
      dele.push(g)
      if (handleLast) handle-- // the handle line comes after every glyph
    }
    S.delGeometries(dele)
  }
  if (S.getGeometry()[handle]?.type !== 'LineSegment') return false
  const last = S.highestCurveIndex()
  if (glyphs.length) S.addGeometry(glyphs)
  const added: [number, PointPos][] = []
  for (let g = last + 1; g <= S.highestCurveIndex(); g++) added.push([g, NONE])
  const font = fileNamePure(fontPath)
  if (existing) S.addConstraint(textConstraint([[handle, NONE], ...added], text, font, height))
  else S.setConstraint(index, { ...textConstraint([...c.elements, ...added], text, font, height), name: c.name })
  return true
}

// ── DrawSketchHandlerText ───────────────────────────────────────────────────────────────────────────────────────
/** TextConstructionMethod: Width (the default), Height. DSHTextController: TwoSeekEnd, four on-view parameters (the
 *  first point's X and Y, then the handle's length and angle), the widget's method combo box, the Text line edit and
 *  the Font combo box. */
export class TextHandler extends DefaultHandler {
  readonly toolName = 'DSH_Text'
  protected readonly states = 2
  protected readonly methods = 2
  protected readonly autoConstraintSize = 2
  private startPoint: XY = [0, 0]
  private endPoint: XY = [0, 0]
  private length = 0
  private handleId = 0
  /** QObject::tr("Text"), the font's file, the Font combo box's names. */
  text = 'Text'
  font = ''
  private fontNames: string[] = []
  private busy = false
  constructor(method = 0) { super(); this.method = method }
  crosshair() { return 'Sketcher_Pointer_Text' }
  hints() {
    const h = this.method === 1 ? (this.state === 0 ? '%1 pick bottom-left point' : '%1 pick top-left point')
      : (this.state === 0 ? '%1 pick bottom-left point' : '%1 pick bottom-right point')
    return [this.hint(h, ['LMB']), this.hint('%1 switch mode', ['M'])]
  }
  protected update(p: XY) {
    if (this.state === 0) {
      this.ctl.drawPositionAtCursor(p)
      this.startPoint = p
      this.seekAndRender(this.sug[0], p, [0, 0])
    } else if (this.state === 1) {
      this.ctl.drawDirectionAtCursor(p, this.startPoint)
      this.endPoint = p
      this.drawShape()
      this.seekAndRender(this.sug[1], p, [p[0] - this.startPoint[0], p[1] - this.startPoint[1]])
    }
  }
  /** createShape: the cached base shapes (Part::makeTextWires of the text and font, from the server once per pair)
   *  placed on the handle; nothing until they are in. */
  protected createShape(onlyOutline = false) {
    this.shapeGeometry = []
    const v: XY = [this.endPoint[0] - this.startPoint[0], this.endPoint[1] - this.startPoint[1]]
    this.length = Math.hypot(v[0], v[1])
    if (this.length < CONFUSION || !this.font) return
    const sh = answerNow({ op: 'shapes', text: this.text, font: this.font }, () => { if (this.state === 1) this.update(this.endPoint) }) as Shapes | null
    if (!sh || sh.box === undefined) return
    this.shapeGeometry = placeShapes(sh, this.startPoint, this.endPoint, this.method === 1, this.isConstructionMode() && !onlyOutline)
  }
  protected canGoToNextMode() { return !(this.state === 1 && this.length < CONFUSION) }
  protected angleSnappingControl() { if (this.state === 1) S.setAngleSnapping(true, this.startPoint); else S.setAngleSnapping(false) }
  /** The handle as executeCommands' Python command writes it ("%f"), and the glyphs' request for it. */
  private handle(): [XY, XY] { return [[f6(this.startPoint[0]), f6(this.startPoint[1])], [f6(this.endPoint[0]), f6(this.endPoint[1])]] }
  private request(): Req {
    const [p1, p2] = this.handle()
    return { op: 'geometry', text: this.text, font: this.font, p1, p2, height: this.method === 1, construction: this.isConstructionMode() }
  }
  /** The glyphs are the server's: fetched, then FreeCAD's finish (executeCommands and the constraints). */
  protected finish(): boolean {
    if (!this.isLast) return false
    if (this.busy) return true
    this.busy = true
    const go = () => { this.busy = false; super.finish() }
    if (!this.font || !this.text) { go(); return true }
    fetchAnswer(this.request()).then(go, (e) => { this.busy = false; report('err', e instanceof Error ? e.message : String(e)); S.purgeHandler() })
    return true
  }
  /** executeCommands: the handle line (construction), the Text constraint holding it, then setTextAndFont. */
  protected executeCommands() {
    S.openCommand('Add sketch Text')
    try {
      const [p1, p2] = this.handle()
      S.addGeometry({ type: 'LineSegment', start: p1, end: p2 }, true)
      this.handleId = S.highestCurveIndex()
      const height = this.method === 1
      S.addConstraint(textConstraint([[this.handleId, NONE]], this.text, fileNamePure(this.font), height))
      const index = S.getConstraints().length - 1
      const req = glyphRequest(index, this.text, this.font, height, this.isConstructionMode())
      const a = req ? cache.get(keyOf(req)) : undefined
      if (a?.error) throw new Error(String(a.error))
      // setTextAndFont reads the handle the Python command wrote: the line finish() fetched the glyphs for
      const glyphs = (a?.geometry as Geo[] | undefined) ?? []
      if (!setTextAndFont(index, this.text, this.font, height, glyphs)) throw new Error('Failed to add text')
      S.commitCommand()
    } catch (e) {
      S.abortCommand()
      report('err', `Error: Failed to add text${e instanceof Error && e.message !== 'Failed to add text' ? ` (${e.message})` : ''}`)
    }
  }
  protected generateAutoConstraints() {
    if (this.avoidRedundants) removeRedundantHorizontalVertical(this.sug[0], this.sug[1])
    this.onElement(this.sug[0], this.handleId, START)
    this.onElement(this.sug[1], this.handleId, END)
    this.removeRedundantAutoConstraints()
  }
  protected createAutoConstraints() { this.createGeneratedAutoConstraints(true); this.sug[0].length = 0; this.sug[1].length = 0 }
  // the controller's specialisations (DSHTextController)
  isWidgetVisible() { return true }
  toolWidgetText() { return 'Text parameters' }
  toolIcon() { return 'Sketcher_CreateText' }
  ovpSpec(): OvpSpec { return { ovps: 4, widget: { parameters: 0, checkboxes: 0, comboboxes: 2, lineEdits: 1 }, firstComboIsMethod: true } }
  ovpState(i: number) { return i < 2 ? 0 : 1 }
  configureToolWidget(c: Controller) {
    if (!c.init) {
      c.setComboboxElements(0, ['Width', 'Height'])
      c.setLineEditLabel(0, 'Text')
      c.setLineEditText(0, this.text)
      c.setComboboxLabel(1, 'Font')
      this.fillFonts(c)
    }
    const o = c.onViewParameters
    o[OVP.First].setLabelType('DISTANCEX'); o[OVP.Second].setLabelType('DISTANCEY')
    o[OVP.Third].setLabelType('DISTANCE', 'Dimensioning'); o[OVP.Fourth].setLabelType('ANGLE', 'Dimensioning')
    c.setLineEditText(0, this.text)
    if (this.fontNames.length) {
      const k = this.fontNames.findIndex((n) => fontsNow()?.paths[n] === this.font)
      if (k >= 0) c.setComboboxIndex(1, k)
    }
  }
  /** findAvailableFontFiles, the names sorted, then the default: osifont-lgpl3fe, else DejaVu Sans, else Arial,
   *  else the first. The list comes from the server: filled when it is in. */
  private fillFonts(c: Controller) {
    const f = fontsNow(() => { if (this.ctl === c) this.fillFonts(c) })
    if (!f) return
    this.fontNames = f.fonts
    c.setComboboxElements(1, f.fonts)
    if (!this.font) {
      const want = ['osifont-lgpl3fe', 'DejaVu Sans', 'Arial'].map((w) => f.fonts.find((n) => n.toLowerCase() === w.toLowerCase())).find((n) => n)
        ?? f.fonts[0]
      if (want) this.font = f.paths[want]
    }
    const k = this.fontNames.findIndex((n) => f.paths[n] === this.font)
    if (k >= 0) { const old = c.getComboboxIndex(1); c.setComboboxIndex(1, k); if (old === k) this.update(this.state === 1 ? this.endPoint : this.startPoint) }
  }
  adaptDrawingToLineEditTextChange(_c: Controller, i: number, text: string) { if (i === 0) this.text = text }
  adaptDrawingToComboboxChange(_c: Controller, i: number, v: number) {
    if (i === 0) return false // the construction method
    if (i === 1) { const n = this.fontNames[v], p = n ? fontsNow()?.paths[n] : undefined; if (p) this.font = p }
    return true
  }
  doEnforceControlParameters(c: Controller, p: XY): XY {
    const o = c.onViewParameters
    let [x, y] = p
    if (this.state === 0) {
      if (o[OVP.First].isSet) x = o[OVP.First].getValue()
      if (o[OVP.Second].isSet) y = o[OVP.Second].getValue()
      return [x, y]
    }
    if (this.state !== 1) return p
    const third = o[OVP.Third], fourth = o[OVP.Fourth]
    let dir: XY = [x - this.startPoint[0], y - this.startPoint[1]]
    if (Math.hypot(dir[0], dir[1]) < CONFUSION) dir = [1, dir[1]] // if direction null, default to (1, 0)
    if (third.isSet) {
      const length = third.getValue()
      if (length < CONFUSION) { c.unsetOnViewParameter(third); return [x, y] }
      const n = Math.hypot(dir[0], dir[1])
      ;[x, y] = [this.startPoint[0] + (length * dir[0]) / n, this.startPoint[1] + (length * dir[1]) / n]
    }
    if (fourth.isSet) {
      let angle = (fourth.getValue() * Math.PI) / 180
      if (this.method === 1) angle += Math.PI * 0.5
      const d: XY = [Math.cos(angle), Math.sin(angle)]
      // onSketchPos.ProjectToLine(onSketchPos - startPoint, dir) (Vector2d's: the foot on the line), += startPoint
      const v: XY = [x - this.startPoint[0], y - this.startPoint[1]], t = (v[0] * d[0] + v[1] * d[1]) / Math.hypot(d[0], d[1])
      const n = Math.hypot(d[0], d[1])
      ;[x, y] = [(d[0] / n) * t + this.startPoint[0], (d[1] / n) * t + this.startPoint[1]]
    }
    if (third.isSet && fourth.isSet && Math.hypot(x - this.startPoint[0], y - this.startPoint[1]) < CONFUSION) {
      c.unsetOnViewParameter(third); c.unsetOnViewParameter(fourth)
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
      return
    }
    if (this.state !== 1) return
    const third = o[OVP.Third], fourth = o[OVP.Fourth]
    const vec: XY = [this.endPoint[0] - this.startPoint[0], this.endPoint[1] - this.startPoint[1]], l = Math.hypot(vec[0], vec[1])
    if (!third.isSet) c.setOnViewParameterValue(OVP.Third, l)
    let range: number
    if (this.method === 1) {
      // the angle of the text's baseline: the handle turned a quarter turn clockwise (Vector2d::Angle)
      range = Math.atan2(-vec[0], vec[1])
    } else range = Math.atan2(vec[1], vec[0])
    if (!fourth.isSet) c.setOnViewParameterValue(OVP.Fourth, (range * 180) / Math.PI, 'Angle')
    else if (fourth.hasFinishedEditing && l > CONFUSION) {
      const ovpRange = (fourth.getValue() * Math.PI) / 180
      if (Math.abs(range - ovpRange) > CONFUSION) c.setOnViewParameterValue(OVP.Fourth, (range * 180) / Math.PI, 'Angle')
    }
    third.setPoints(this.startPoint, this.endPoint)
    fourth.setPoints(this.startPoint, [0, 0])
    fourth.setLabelRange(range)
  }
  computeNextDrawSketchHandlerMode(c: Controller) {
    const o = c.onViewParameters
    if (this.state === 0 && o[OVP.First].hasFinishedEditing && o[OVP.Second].hasFinishedEditing) this.setNextState(1)
    else if (this.state === 1 && o[OVP.Third].hasFinishedEditing && o[OVP.Fourth].hasFinishedEditing) this.setNextState(this.states)
  }
  /** DSHTextController::addConstraints with no auto-constraints diagnosed yet (they come after): each parameter set,
   *  on the handle line. */
  addConstraints(c: Controller) {
    const firstCurve = this.handleId, o = c.onViewParameters
    const x0 = o[OVP.First].getValue(), y0 = o[OVP.Second].getValue(), p3 = o[OVP.Third].getValue(), p4 = o[OVP.Fourth].getValue()
    const x0set = o[OVP.First].isSet, y0set = o[OVP.Second].isSet, p3set = o[OVP.Third].isSet, p4set = o[OVP.Fourth].isSet
    if (x0set && y0set && x0 === 0 && y0 === 0) constraintToAttachment([firstCurve, START], RT_PNT_ID, x0)
    else {
      if (x0set) constraintToAttachment([firstCurve, START], V_AXIS_ID, x0)
      if (y0set) constraintToAttachment([firstCurve, START], H_AXIS_ID, y0)
    }
    if (p3set) S.addConstraint(constraint('Distance', firstCurve, NONE, GEO_UNDEF, NONE, GEO_UNDEF, NONE, f6(Math.abs(p3))))
    if (p4set) {
      let angle = (p4 * Math.PI) / 180
      if (this.method === 1) angle += Math.PI * 0.5
      constraintLineByAngle(firstCurve, angle)
    }
  }
}

// ── EditTextDialog (ViewProviderSketch::editDoubleClicked on a text's handle) ───────────────────────────────────
type Dlg = { index: number; text: string; font: string; height: boolean }
let dlg: Dlg | null = null
const dlgSubs = new Set<() => void>()
const dlgChanged = () => dlgSubs.forEach((f) => f())
/** The dialog for the Text constraint at index (it needs the font list first). */
export async function editText(index: number) {
  const c = S.getConstraints()[index]
  if (!c || c.type !== 'Text') return
  try { await fetchAnswer({ op: 'fonts' }) } catch (e) { report('err', e instanceof Error ? e.message : String(e)); return }
  dlg = { index, text: c.text ?? '', font: c.font ?? '', height: c.textHeight !== false }
  dlgChanged()
}
S.onEditText((id) => { void editText(id) })

export function EditTextDialog() {
  const d = useSyncExternalStore((f) => { dlgSubs.add(f); return () => { dlgSubs.delete(f) } }, () => dlg)
  const [text, setText] = useState('')
  const [font, setFont] = useState(0)
  const [height, setHeight] = useState(true)
  const fonts = d ? fontsNow() : null
  useEffect(() => {
    if (!d || !fonts) return
    setText(d.text); setHeight(d.height)
    // findText(currentFontName, Qt::MatchFixedString): the stored font, case-insensitively; a warning when it is gone
    const k = d.font ? fonts.fonts.findIndex((n) => n.toLowerCase() === d.font.toLowerCase()) : -1
    setFont(k >= 0 ? k : 0)
    if (d.font && k < 0) void messageBox('warning', 'Font not found', `The original font '${d.font}' is not found on your system. A default font has been selected.`)
  }, [d]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!d || !fonts) return null
  const close = () => { dlg = null; dlgChanged() }
  const accept = async () => {
    close()
    const name = fonts.fonts[font] ?? '', path = fonts.paths[name] ?? ''
    // nothing changed: nothing to do
    if (text === d.text && name === d.font && height === d.height) return
    const c = S.getConstraints()[d.index]
    if (!c) return
    const req = glyphRequest(d.index, text, path, height, false)
    if (!req) return
    let a: Record<string, unknown>
    try { a = await fetchAnswer(req) } catch (e) { report('err', `Failed to modify text constraint: ${e instanceof Error ? e.message : String(e)}`); return }
    if (a.error) { report('err', `Failed to modify text constraint: ${a.error}`); return }
    S.openCommand('Modify sketch text constraint')
    if (!setTextAndFont(d.index, text, path, height, (a.geometry as Geo[]) ?? [])) { S.abortCommand(); report('err', 'Failed to modify text constraint'); return }
    S.commitCommand()
    S.solve()
  }
  return createPortal(
    <div className="msgbox-back" onKeyDown={(e) => {
      e.stopPropagation()
      if (e.key === 'Escape') { e.preventDefault(); close() }
      if (e.key === 'Enter') { e.preventDefault(); void accept() }
    }}>
      <div className="msgbox datum-dlg sk-edit-text" role="dialog" aria-label="Edit Text" data-dialog="Edit Text">
        <div className="msgbox-title">Edit Text</div>
        <div className="datum-body form">
          <span>Text</span><input className="qline" data-name="lineEdit_text" data-qf="lineEdit_text" autoFocus value={text} onChange={(e) => setText(e.target.value)} />
          <span>Font</span>
          <select className="qcombo" data-name="comboBox_font" data-qf="comboBox_font" value={font} size={1} onChange={(e) => setFont(Number(e.target.value))}>
            {fonts.fonts.map((n, i) => <option key={n} value={i}>{n}</option>)}
          </select>
          <span className="radios">
            <label className="tcheck"><input type="radio" data-name="radioButton_height" data-qf="radioButton_height" checked={height} onChange={() => setHeight(true)} /> Height</label>
            <label className="tcheck"><input type="radio" data-name="radioButton_width" data-qf="radioButton_width" checked={!height} onChange={() => setHeight(false)} /> Width</label>
          </span>
        </div>
        <div className="msgbox-buttons">
          <button className="qbtn default" onClick={() => void accept()}>OK</button>
          <button className="qbtn" onClick={close}>Cancel</button>
        </div>
      </div>
    </div>, document.body)
}

/** For the checks and the Python console: a sketch's text constraints as {index, text, font, height, glyphs}. */
export function textConstraints(cons: Constraint[] = S.getConstraints()) {
  return cons.map((c, i) => (c.type === 'Text' ? { index: i, text: c.text, font: c.font, height: c.textHeight !== false, glyphs: (c.elements?.length ?? 1) - 1 } : null))
    .filter((x) => x)
}

// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Sketcher/Gui/Command.cpp: 2008 Jürgen Riegel (Sketcher_MapSketch, _ReorientSketch, _ValidateSketch,
//                                     _MirrorSketch, _MergeSketches)
//   src/Mod/Sketcher/Gui/SketchMirrorDialog.cpp: 2015 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/SketchOrientationDialog.cpp: 2011 Jürgen Riegel
//   src/Mod/Sketcher/Gui/TaskSketcherValidation.cpp: 2013 Werner Mayer
//   No copyright line in the file: src/Mod/Sketcher/Gui/SketchMirrorDialog.ui, SketchOrientationDialog.ui,
//   TaskSketcherValidation.ui
// The Sketcher's commands on sketch objects, out of edit mode, on the sketches the tree selects: Attach Sketch
// (Sketcher_MapSketch's two QInputDialogs), Reorient Sketch (the "Sketch Has Support" question and
// SketchOrientationDialog), Validate Sketch (TaskSketcherValidation, with its points drawn in the 3D view), Merge
// Sketches and Mirror Sketch (SketchMirrorDialog). The work is the server's (`cad feature mirror | merge | reorient |
// map | validate`, cad_agent/sketch_commands.py, held to FreeCAD 26.3 by tests/golden/sketchobj): the page asks it for
// the ops (--dry) and sends them as one undo step named as FreeCAD names the transaction (applyOps).
import { useEffect, useState, useSyncExternalStore } from 'react'
import { createPortal } from 'react-dom'
import * as THREE from 'three'
import { api, resultText, type CadResult, type FeatureOp } from './api'
import { getState, report, subscribe, useStore } from './store'
import { closeTask, editSketch, getView, openTask } from './actions'
import { messageBox } from './msgbox'
import { QuantityBox } from './qsb'
import { MODE_TEXTS } from './attachertexts'
import { applyOps, bodyOfPart, sketchMatrix, SKETCH, splitRef } from './partdesign'
import { refsOfSelection } from './pd_attach'
import { onSketchObjectCommands } from './sketchcmds'
import * as S from './sketcher'
import './sketchobjcmds.css'

type Sel = { part: string; name: string }
const OBJ = ['Sketcher_MapSketch', 'Sketcher_ReorientSketch', 'Sketcher_ValidateSketch', 'Sketcher_MergeSketches', 'Sketcher_MirrorSketch']
/** The task panels that are FreeCAD task dialogs (Gui::Control().activeDialog()). */
const DIALOG_TASKS = new Set(['sketchAttach', 'pad', 'pocket', 'attach', 'revolution', 'groove', 'hole', 'fillet', 'chamfer', 'draft', 'thickness',
  'pdTransform', 'pdPrimitive', 'sketch', 'sketchValidate'])

/** Gui::Selection().getObjectsOfType<Sketcher::SketchObject>(): the sketches selected in the tree, in selection order. */
export function selectedSketches(): Sel[] {
  const s = getState(), out: Sel[] = []
  for (const r of s.featSel) {
    const [part, name] = splitRef(r)
    if (s.features[part]?.features.find((f) => f.name === name)?.type === SKETCH && !out.some((x) => x.part === part && x.name === name)) out.push({ part, name })
  }
  return out
}
const docHasSketches = () => Object.values(getState().features).some((d) => d.features.some((f) => f.type === SKETCH))
const hasSelection = () => { const s = getState(); return s.featSel.length > 0 || s.subSel.length > 0 || s.selected.length > 0 }
const msg = (e: unknown) => (e instanceof Error ? e.message : String(e))

/** Command::isActive of each (Command.cpp). */
function enabled(name: string): boolean {
  const s = getState()
  if (!s.slug || S.isEditing()) return false
  const n = selectedSketches().length
  switch (name) {
    case 'Sketcher_MapSketch': return docHasSketches() && hasSelection()
    case 'Sketcher_ReorientSketch': return n === 1
    case 'Sketcher_ValidateSketch': return !(s.task && DIALOG_TASKS.has(s.task.kind)) && n === 1
    case 'Sketcher_MergeSketches': return n > 1
    case 'Sketcher_MirrorSketch': return n > 0
  }
  return false
}
function run(name: string) {
  if (name === 'Sketcher_MapSketch') void mapSketch()
  else if (name === 'Sketcher_ReorientSketch') void reorientSketch()
  else if (name === 'Sketcher_ValidateSketch') validateSketch()
  else if (name === 'Sketcher_MergeSketches') void mergeSketches()
  else if (name === 'Sketcher_MirrorSketch') void mirrorSketch()
}
onSketchObjectCommands({ names: OBJ, enabled, run })

// ── the server ───────────────────────────────────────────────────────────────────────────────────────────────────
async function cad(argv: string[]): Promise<CadResult | null> {
  const slug = getState().slug
  if (!slug) return null
  try { return await api.cad(slug, argv) } catch (e) { report('err', msg(e)); return null }
}
/** `cad feature ... --dry`: the ops the command amounts to, sent as one step (POST /api/<slug>/features/<part>). */
async function applyCommand(part: string, argv: string[], what: string) {
  const r = await cad([...argv, '--dry'])
  if (!r) return null
  if (r.exit > 2 || r.data?.error) { report('err', `${what}: ${resultText(r)}`); return null }
  const ops = (r.data?.ops ?? []) as FeatureOp[]
  if (!ops.length) return r.data ?? null
  const done = await applyOps(part, ops, { name: r.data?.step as string, line: r.data?.line as string })
  return done ? r.data ?? null : null
}

// ── the dialogs (QDialog::exec) ──────────────────────────────────────────────────────────────────────────────────
type Dlg = { kind: 'mirror' } | { kind: 'orient' } | { kind: 'item'; title: string; label: string; items: string[]; current: number }
let dlg: { d: Dlg; resolve(v: unknown): void } | null = null
const dlgSubs = new Set<() => void>()
function ask<T>(d: Dlg): Promise<T | null> { return new Promise((resolve) => { dlg = { d, resolve: resolve as (v: unknown) => void }; dlgSubs.forEach((f) => f()) }) }
function close(v: unknown) { const x = dlg; dlg = null; dlgSubs.forEach((f) => f()); x?.resolve(v) }

function Buttons({ ok }: { ok(): void }) {
  return <div className="msgbox-buttons"><button className="qbtn default" onClick={ok}>OK</button><button className="qbtn" onClick={() => close(null)}>Cancel</button></div>
}
function Modal({ title, children, ok }: { title: string; children: React.ReactNode; ok(): void }) {
  return createPortal(
    <div className="msgbox-back" onKeyDown={(e) => { e.stopPropagation(); if (e.key === 'Escape') close(null); if (e.key === 'Enter') ok() }}>
      <div className="msgbox datum-dlg" role="dialog" aria-label={title} data-dialog={title}>
        <div className="msgbox-title">{title}</div>
        {children}
        <Buttons ok={ok} />
      </div>
    </div>, document.body)
}
/** SketchMirrorDialog: X-axis (checked), Y-axis, Origin. */
function MirrorDialog() {
  const [ref, setRef] = useState<'X' | 'Y' | 'origin'>('X')
  const ok = () => close(ref)
  return (
    <Modal title="Select Mirror Axis or Point" ok={ok}>
      <fieldset className="tgroup datum-body"><legend>Select Mirror Axis or Point</legend>
        {([['X', 'X-axis'], ['Y', 'Y-axis'], ['origin', 'Origin']] as const).map(([k, t]) =>
          <label key={k} className="tcheck"><input type="radio" name="mirror-ref" checked={ref === k} onChange={() => setRef(k)} /> {t}</label>)}
      </fieldset>
    </Modal>)
}
/** SketchOrientationDialog: the plane, Reverse direction, Offset, and the preview of the view (onPreview's icons). */
const PREVIEW: Record<string, [string, string]> = { XY: ['view-top', 'view-bottom'], XZ: ['view-front', 'view-rear'], YZ: ['view-right', 'view-left'] }
function OrientDialog() {
  const [plane, setPlane] = useState<'XY' | 'XZ' | 'YZ'>('XY')
  const [reverse, setReverse] = useState(false)
  const [offset, setOffset] = useState(0)
  const ok = () => close({ plane, reverse, offset })
  return (
    <Modal title="Choose Orientation" ok={ok}>
      <div className="hbox">
        <fieldset className="tgroup datum-body"><legend>Sketch Orientation</legend>
          {(['XY', 'XZ', 'YZ'] as const).map((p) => <label key={p} className="tcheck"><input type="radio" name="orient-plane" checked={plane === p} onChange={() => setPlane(p)} /> {p}-plane</label>)}
        </fieldset>
        <img className="orient-preview" data-preview={PREVIEW[plane][reverse ? 1 : 0]} src={`./freecad-icons/${PREVIEW[plane][reverse ? 1 : 0]}.svg`} width={48} height={48} alt="Preview" />
      </div>
      <label className="tcheck"><input type="checkbox" checked={reverse} onChange={(e) => setReverse(e.target.checked)} /> Reverse direction</label>
      <div className="hbox fill"><span>Offset</span><QuantityBox value={offset} dims={[1, 0, 0, 0, 0, 0, 0, 0]} step={10} onChange={setOffset} /></div>
    </Modal>)
}
/** QInputDialog::getItem (not editable). */
function ItemDialog({ d }: { d: Extract<Dlg, { kind: 'item' }> }) {
  const [cur, setCur] = useState(d.current)
  return (
    <Modal title={d.title} ok={() => close(d.items[cur])}>
      <div className="datum-body"><div className="qlabel" style={{ whiteSpace: 'pre-wrap' }}>{d.label}</div>
        <select className="qcombo" value={cur} onChange={(e) => setCur(Number(e.target.value))}>{d.items.map((t, i) => <option key={i} value={i}>{t}</option>)}</select></div>
    </Modal>)
}
export function SketchObjHost() {
  const d = useSyncExternalStore((f) => { dlgSubs.add(f); return () => { dlgSubs.delete(f) } }, () => dlg)
  if (!d) return null
  if (d.d.kind === 'mirror') return <MirrorDialog />
  if (d.d.kind === 'orient') return <OrientDialog />
  return <ItemDialog key={d.d.title} d={d.d} />
}

// ── the commands ─────────────────────────────────────────────────────────────────────────────────────────────────
/** CmdSketcherMirrorSketch: SketchMirrorDialog, then a MirroredSketch for each selected sketch. */
async function mirrorSketch() {
  const sel = selectedSketches(), slug = getState().slug
  if (!sel.length || !slug) { report('warn', 'Wrong selection: Select at least 1 sketch'); return }
  const ref = await ask<string>({ kind: 'mirror' })
  if (!ref) return
  for (const part of [...new Set(sel.map((x) => x.part))]) {
    await applyCommand(part, ['feature', 'mirror', slug, part, ...sel.filter((x) => x.part === part).map((x) => x.name), '--ref', ref], 'Mirror Sketch')
  }
}
/** CmdSketcherMergeSketches: a new sketch in the first sketch's Body; what FreeCAD prints goes to the Report view. */
async function mergeSketches() {
  const sel = selectedSketches(), slug = getState().slug
  if (sel.length < 2 || !slug) { report('warn', 'Wrong selection: Select at least 2 sketches'); return }
  const part = sel[0].part
  const names = sel.map((x) => (x.part === part ? x.name : `${x.part}/${x.name}`))
  const out = await applyCommand(part, ['feature', 'merge', slug, part, ...names], 'Merge Sketches')
  for (const m of (out?.messages ?? []) as string[]) report('msg', m.replace(/\n$/, ''))
}
/** CmdSketcherReorientSketch: a sketch with a support is detached first (asked), then placed on the plane the dialog
 *  says, and opened (setEdit). */
async function reorientSketch() {
  const sk = selectedSketches()[0], slug = getState().slug
  if (!sk || !slug) return
  const f = getState().features[sk.part]?.features.find((x) => x.name === sk.name)
  let detached = false
  if (((f?.attachment_support as unknown[]) ?? []).length) {
    const b = await messageBox('question', 'Sketch Has Support', 'Sketch with a support face cannot be reoriented.\nDetach it from the support?', ['Yes', 'No'])
    if (b !== 'Yes') return
    detached = true
  }
  const r = await ask<{ plane: string; reverse: boolean; offset: number }>({ kind: 'orient' })
  if (!r) {
    // FreeCAD has cleared AttachmentSupport already (outside any transaction): the sketch stays where it is, detached
    if (detached) await applyCommand(sk.part, ['feature', 'map', slug, sk.part, sk.name], 'Reorient Sketch')
    return
  }
  const scene = getState().scene
  const done = await applyCommand(sk.part, ['feature', 'reorient', slug, sk.part, sk.name, '--plane', r.plane, ...(r.reverse ? ['--reverse'] : []),
    '--offset', String(r.offset)], 'Reorient Sketch')
  if (!done) return
  await nextScene(scene)       // setEdit on the sketch where the rebuilt scene puts it
  editSketch(sk.part, sk.name)
}
/** Until the scene the file watcher reloads after an edit is in (or a few seconds have gone). */
function nextScene(before: unknown): Promise<void> {
  return new Promise((resolve) => {
    let un = () => {}
    const t = setTimeout(() => { un(); resolve() }, 8000)
    un = subscribe(() => { if (getState().scene !== before) { clearTimeout(t); un(); setTimeout(resolve, 300) } })
  })
}
/** The part whose objects the selection holds: the tree's rows, else the 3D view's body. */
function selectionPart(): string | null {
  const s = getState()
  for (const r of s.featSel) { const [p] = splitRef(r); if (s.features[p]) return p }
  for (const sub of s.subSel) { const b = s.scene?.bodies.find((x) => x.name === sub.slice(0, sub.indexOf('.'))); if (b?.part && s.features[b.part]) return b.part }
  for (const n of s.selected) { const b = s.scene?.bodies.find((x) => x.name === n); if (b?.part && s.features[b.part]) return b.part }
  return null
}
const refArg = (r: [string, string]) => (r[1] ? `${r[0]}.${r[1]}` : r[0])
/** CmdSketcherMapSketch: which sketch (the selected ones left out), the circular dependency check, then the method:
 *  "Do not attach", the modes that fit the selection (SuggestAutoMapMode on AttachEngine3D, captions of
 *  AttachEnginePlane), the current one marked; then "Attach sketch" or "Detach sketch". */
async function mapSketch() {
  const s = getState(), slug = s.slug
  const part = selectionPart()
  if (!slug || !part) return
  const doc = s.features[part]
  const selected = new Set(selectedSketches().filter((x) => x.part === part).map((x) => x.name))
  const all = doc.features.filter((f) => f.type === SKETCH)
  const sketches = all.filter((f) => !selected.has(f.name)).map((f) => f.name).sort((a, b) => (a < b ? -1 : a > b ? 1 : 0))
  const inSel = all.length > sketches.length
  if (!sketches.length) { report('warn', `No sketch found: ${inSel ? 'Cannot attach sketch to itself!' : 'The document does not contain a sketch'}`); return }
  const name = await ask<string>({ kind: 'item', title: 'Select Sketch', label: inSel ? 'Select a sketch (some sketches not shown to prevent a circular dependency)'
    : 'Select a sketch from the list', items: sketches, current: 0 })
  if (!name) return
  const refs = refsOfSelection(part)
  const supports = refs.flatMap((r) => ['--support', refArg(r)])
  const chk = await cad(['feature', 'map', slug, part, name, ...supports, '--check'])
  if (!chk) return
  const refusal = chk.data?.refusal ?? (chk.exit > 2 ? resultText(chk) : null)
  if (refusal) { report('warn', `Map sketch: Can't map a sketch to support:\n${refusal}`); return }
  const sug = await cad(['feature', 'attach', slug, part, '--engine', '3D', ...supports])
  const fit = ((sug?.data?.suggestion?.all ?? []) as string[]).slice()
  const best = (sug?.data?.suggestion?.best ?? 'Deactivated') as string
  const cur = (doc.features.find((f) => f.name === name)?.map_mode as string | undefined) ?? 'Deactivated'
  const incompatible = !fit.includes(cur)
  const valid = ['Deactivated', ...fit, ...(incompatible ? [cur] : [])]
  const items = ['Do not attach']
  let iSugg = 0, iCurr = 0
  for (const m of valid) {
    items.push(MODE_TEXTS.Plane[m]?.[0] ?? m)
    if (m === cur) { iCurr = items.length - 1; items[items.length - 1] += incompatible ? ' (incompatible with selection)' : ' (current)' }
    if (m === best) {
      iSugg = items.length - 1
      if (iSugg === 1) iSugg = 0 // redirect deactivate to detach
      else items[items.length - 1] += ' (suggested)'
    }
  }
  const text = await ask<string>({ kind: 'item', title: 'Sketch Attachment', label: incompatible
    ? 'Current attachment mode is incompatible with the new selection.\nSelect the method to attach this sketch to selected objects.'
    : 'Select the method to attach this sketch to selected objects.', items, current: incompatible ? iSugg : iCurr })
  if (text === null) return
  const index = items.indexOf(text)
  const mode = index === 0 ? 'Deactivated' : valid[index - 1]
  await applyCommand(part, ['feature', 'map', slug, part, name, ...(index === 0 ? [] : [...supports, '--mode', mode])], 'Attach Sketch')
}
/** CmdSketcherValidateSketch: one sketch selected, then its Sketch Validation panel. */
function validateSketch() {
  const sel = selectedSketches()
  if (sel.length !== 1) { report('warn', 'Wrong selection: Select only 1 sketch.'); return }
  openTask('sketchValidate', sel[0].part, sel[0].name)
}

// ── the Sketch Validation panel (TaskSketcherValidation) ─────────────────────────────────────────────────────────
/** Precision::Confusion() / 100 ... * 100000, as QLocale::toString writes them; 0.0001 is the current one. */
const TOLERANCES: [string, number][] = [['1e-09', 1e-9], ['1e-08', 1e-8], ['1e-07', 1e-7], ['1e-06', 1e-6], ['1e-05', 1e-5], ['0.0001', 1e-4], ['0.001', 1e-3], ['0.01', 1e-2]]
type Note = { kind: 'warning' | 'notification' | 'error'; title: string; text: string }
function notify(n: Note | undefined) {
  if (!n) return
  // Gui::TranslatedUserWarning / TranslatedUserError go to the notification area, TranslatedNotification to the Report view
  report(n.kind === 'warning' ? 'warn' : n.kind === 'error' ? 'err' : 'msg', `${n.title}: ${n.text}`)
}
/** showPoints: orange points with a yellow PLUS marker (MarkerSize 9) at each, in the sketch's frame. */
function pointsObject(part: string, name: string, pts: number[][]): THREE.Object3D | null {
  const st = getState(), f = st.features[part]?.features.find((x) => x.name === name)
  if (!f || !pts.length) return null
  const g = new THREE.Group()
  const m = new THREE.Matrix4(), b = bodyOfPart(st, part)
  if (b?.matrix?.length === 16) m.fromArray(b.matrix).transpose()
  m.multiply(sketchMatrix(f))
  g.matrixAutoUpdate = false
  g.matrix.copy(m)
  const geom = new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute(pts.flatMap((p) => [p[0], p[1], 0]), 3))
  const plus = document.createElement('canvas')
  plus.width = plus.height = 9
  const c = plus.getContext('2d')
  if (c) { c.fillStyle = '#ffff00'; c.fillRect(4, 0, 1, 9); c.fillRect(0, 4, 9, 1) }
  const dot = new THREE.Points(geom, new THREE.PointsMaterial({ color: 0xff8000, size: 6, sizeAttenuation: false, depthTest: false }))
  const mark = new THREE.Points(geom, new THREE.PointsMaterial({ map: new THREE.CanvasTexture(plus), size: 9, sizeAttenuation: false, transparent: true, depthTest: false }))
  dot.renderOrder = mark.renderOrder = 10
  g.add(dot, mark)
  g.userData.validationPoints = pts
  return g
}
const showPoints = (part: string, name: string, pts: number[][]) => getView()?.setHelper('sketch-validation', pointsObject(part, name, pts))
const hidePoints = () => getView()?.setHelper('sketch-validation', null)

export function ValidateTask({ part, name }: { part: string; name: string }) {
  const slug = useStore((s) => s.slug)
  const [tol, setTol] = useState('0.0001')
  const [ignore, setIgnore] = useState(true)
  const [fix, setFix] = useState({ coincidences: false, constraints: false, degenerated: false, reversed: false })
  const [busy, setBusy] = useState(false)
  useEffect(() => () => hidePoints(), [])
  if (!slug) return null
  const tolerance = () => {
    const v = Number(tol.trim())
    if (tol.trim() && Number.isFinite(v)) return v
    return TOLERANCES.find(([t]) => t === tol)?.[1] ?? 1e-7
  }
  const call = async (check: string, opts: { fix?: boolean; tol?: boolean } = {}) => {
    setBusy(true)
    try {
      const argv = ['feature', 'validate', slug, part, name, '--check', check, ...(opts.fix ? ['--fix'] : []),
        ...(opts.tol ? ['--tolerance', String(tolerance()), ...(ignore ? [] : ['--include-construction'])] : [])]
      if (opts.fix || check === 'external') return await applyCommand(part, argv, 'Sketch Validation')
      const r = await cad(argv)
      if (!r || r.exit > 2) { if (r) report('err', `Sketch Validation: ${resultText(r)}`); return null }
      return r.data ?? null
    } finally { setBusy(false) }
  }
  const find = async () => {
    const d = await call('coincidences', { tol: true })
    if (!d) return
    hidePoints()
    const miss = (d.missing ?? []) as { at: number[] }[]
    if (miss.length) showPoints(part, name, miss.map((m) => m.at))
    notify(d.notification as Note)
    setFix((x) => ({ ...x, coincidences: miss.length > 0 }))
  }
  const fixCoincidences = async () => { await call('coincidences', { tol: true, fix: true }); setFix((x) => ({ ...x, coincidences: false })); hidePoints() }
  const highlight = async () => {
    const d = await call('open')
    hidePoints()
    if (d && (d.points as number[][]).length) showPoints(part, name, d.points as number[][])
  }
  const findConstraint = async () => { const d = await call('constraints'); if (!d) return; notify(d.notification as Note); setFix((x) => ({ ...x, constraints: (d.invalid as number[]).length > 0 })) }
  const fixConstraint = async () => { await call('constraints', { fix: true }); setFix((x) => ({ ...x, constraints: false })) }
  const findDegenerated = async () => { const d = await call('degenerated'); if (!d) return; notify(d.notification as Note); setFix((x) => ({ ...x, degenerated: (d.degenerated as number[]).length > 0 })) }
  // onFixDegeneratedClicked turns fixButton (the coincidences' Fix) off, as FreeCAD's does
  const fixDegenerated = async () => { await call('degenerated', { fix: true }); setFix((x) => ({ ...x, coincidences: false })); hidePoints() }
  const findReversed = async () => {
    const d = await call('reversed')
    if (!d) return
    hidePoints()
    if ((d.points as number[][]).length) showPoints(part, name, d.points as number[][])
    notify(d.notification as Note)
    setFix((x) => ({ ...x, reversed: (d.points as number[][]).length > 0 && (d.constraints as number) > 0 }))
  }
  const lock = async (on: boolean) => { const d = await call(on ? 'lock' : 'unlock'); if (d) notify(d.notification as Note) }
  const delExternal = async () => {
    const b = await messageBox('question', 'Delete Constraints to External Geometry', 'This will delete all constraints that deal with external geometry. This is '
      + 'useful to rescue a sketch with broken or changed links to external geometry. Delete the constraints?', ['Yes', 'No'])
    if (b !== 'Yes') return
    const d = await call('external')
    if (d) notify(d.notification as Note)
  }
  const B = ({ id, text, tip, on, onClick }: { id: string; text: string; tip?: string; on?: boolean; onClick(): void }) =>
    <button className="qbtn" data-name={id} title={tip} disabled={on === false} onClick={() => { if (!busy) void onClick() }}>{text}</button>
  return (
    <div className="tasks" data-task="sketchValidate" data-busy={busy ? 'true' : 'false'}>
      <div className="tbuttons"><button className="qbtn" onClick={() => { hidePoints(); closeTask() }}>Close</button></div>
      <div className="tbox" data-box="validation">
        <div className="tbox-head"><span>Sketch Validation</span></div>
        <div className="tbox-body sk-validate">
          <fieldset className="tgroup" data-group="groupBox_0"><legend>Open and Non-Manifold Vertices</legend>
            <B id="highlightButton" text="Highlight Troublesome Vertices" tip="Highlights open and non-manifold vertices that could lead to errors if the sketch is used to generate solids. This is purely based on the topological shape of the sketch and not on its geometry/constraint set." onClick={highlight} />
          </fieldset>
          <fieldset className="tgroup" data-group="groupBox_1" title="Fixes missing coincidences by adding extra coincident constraints"><legend>Missing Coincidences</legend>
            <div className="grid2">
              <span>Tolerance</span>
              <input className="qcombo" data-name="comboBoxTolerance" list="sk-validate-tol" value={tol} title="Defines the X/Y tolerance within which missing coincidences are detected"
                onChange={(e) => { if (/^[0-9.eE+-]*$/.test(e.target.value)) setTol(e.target.value) }} />
              <datalist id="sk-validate-tol">{TOLERANCES.map(([t]) => <option key={t} value={t} />)}</datalist>
              <label className="tcheck span2" title="Ignores construction geometry in the search"><input type="checkbox" data-name="checkBoxIgnoreConstruction" checked={ignore} onChange={(e) => setIgnore(e.target.checked)} /> Ignore construction geometry</label>
              <B id="findButton" text="Find" tip={'Finds and displays missing coincidences in the sketch.\nThis is done by analyzing the sketch geometries and constraints.'} onClick={find} />
              <B id="fixButton" text="Fix" on={fix.coincidences} onClick={fixCoincidences} />
            </div>
          </fieldset>
          <fieldset className="tgroup" data-group="groupBox_2"><legend>Invalid Constraints</legend>
            <div className="grid2">
              <B id="findConstraint" text="Find" tip="Finds invalid/malformed constrains in the sketch" onClick={findConstraint} />
              <B id="fixConstraint" text="Fix" tip="Tries to fix found invalid constraints" on={fix.constraints} onClick={fixConstraint} />
              <span className="span2"><B id="delConstrExtr" text="Delete Constraints Linked to External Geometry" tip="Deletes constraints referring to external geometry" onClick={delExternal} /></span>
            </div>
          </fieldset>
          <fieldset className="tgroup" data-group="groupBox_6"><legend>Degenerate Geometry</legend>
            <div className="grid2">
              <B id="findDegenerated" text="Find" tip="Finds degenerated geometries in the sketch" onClick={findDegenerated} />
              <B id="fixDegenerated" text="Fix" tip="Tries to fix found degenerated geometries" on={fix.degenerated} onClick={fixDegenerated} />
            </div>
          </fieldset>
          <fieldset className="tgroup" data-group="groupBox_3"><legend>Reversed External Geometry</legend>
            <B id="findReversed" text="Find" tip="Finds reversed external geometries" onClick={findReversed} />
            <B id="swapReversed" text="Swap Endpoints in Constraints" tip="Fixes found reversed external geometries by swapping their endpoints" on={fix.reversed} onClick={() => {}} />
          </fieldset>
          <fieldset className="tgroup" data-group="groupBox_4"><legend>Constraint Orientation Locking</legend>
            <B id="orientLockEnable" text="Enable/Update" tip="Enables/updates constraint orientation locking" onClick={() => lock(true)} />
            <B id="orientLockDisable" text="Disable" tip="Disables constraint orientation locking" onClick={() => lock(false)} />
          </fieldset>
        </div>
      </div>
    </div>
  )
}

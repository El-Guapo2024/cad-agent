// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/PartDesign/Gui/Workbench.cpp: 2008 Werner Mayer
//   src/Mod/PartDesign/Gui/CommandBody.cpp: 2015 Alexander Golubev (Fat-Zer)
//   src/Mod/PartDesign/Gui/Command.cpp: 2008 Jürgen Riegel
//   src/Mod/PartDesign/Gui/SketchWorkflow.cpp: 2022 Werner Mayer
//   src/Mod/PartDesign/Gui/TaskExtrudeParameters.cpp: 2021 Werner Mayer
//   src/Mod/PartDesign/Gui/TaskPadParameters.cpp: 2011 Juergen Riegel
//   src/Mod/PartDesign/Gui/TaskPocketParameters.cpp: 2011 Juergen Riegel
//   src/Mod/PartDesign/Gui/ViewProvider.cpp: 2011 Juergen Riegel
//   src/Mod/PartDesign/Gui/ViewProviderSketchBased.cpp: 2015 Alexander Golubev (Fat-Zer)
//   src/Mod/PartDesign/Gui/StyleParameters.h: 2025 Kacper Donat
//   src/Mod/Part/Gui/TaskAttacher.cpp: 2013 Jan Rheinländer
//   src/Mod/Part/Gui/ViewProviderAttachExtension.cpp: 2016 Stefan Tröger
//   src/Mod/Sketcher/Gui/ViewProviderSketch.cpp: 2009 Juergen Riegel
//   src/Gui/Tree.cpp: 2004 Jürgen Riegel
//   src/Gui/CommandDoc.cpp: 2002 Jürgen Riegel
//   src/Gui/ViewProviderPlane.cpp: 2012 Jürgen Riegel; 2015 Alexander Golubev (Fat-Zer)
//   src/Gui/propertyeditor/PropertyEditor.cpp: 2004 Werner Mayer
//   No copyright line in the file: src/Mod/PartDesign/Gui/TaskPadPocketParameters.ui, src/Mod/Part/Gui/TaskAttacher.ui
// PartDesign for parts whose shape is a FEATURES list (cad_agent/feature.py): the tree's Body with its Origin, BaseFeature
// and features, their properties, the Sketch and Part Design menus and toolbars, New Body, New Sketch (the attachment panel),
// Pad and Pocket (their task panels, with the preview overlay), Set Tip, Move Feature After…, Delete, Rename and visibility.
// Every edit is `cad feature` on the server (POST /api/<slug>/features/<part>), one undo step of the shared journal; the part
// rebuilds there and the scene reloads as after `cad set`. Nothing here builds a shape: the preview is the profile extruded
// in the browser, as FreeCAD's "Show preview overlay" draws the feature's tool, and what OK writes is built by the server.
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import * as THREE from 'three'
import { api, resultText, type Body, type FeatureOp } from './api'
import { consoleLog, getState, report, setState, subscribe, useStore, type Feature, type FeatureDoc, type State } from './store'
import { closeTask, editSketch, featureOf, getView, loadFeatures, loadHistory, ORIGIN_NAMES, openTask, select, showPanel, toggleVisibility } from './actions'
import { Icon, type IconName } from './icons'
import { cls, EditRow, Group, Row, TaskBox, Twisty, propPad } from './panels'
import { QuantityBox, LENGTH, ANGLE } from './qsb'
import { QComboBox } from './combo'
import { messageBox } from './msgbox'
import { evaluate } from './expr'
import * as quantity from './quantity'
import type { Entry } from './chrome'
import { editRevolveFeature, RevolveProps, revolveEntries, REVOLVE_ICONS, REVOLVE_KINDS } from './pd_revolve'
import { DressUpProps, dressUpEntries, dressUpUses, editDressUp, isDressUp } from './pd_dressup'
import { editPdx, findFeature, isPdx, pdxChildren, pdxDeleteOps, pdxIcon, pdxKind, PdxProps, pdxUses, primitiveMenu, transformMenu } from './pd_transform'
import './partdesign.css'
import { attachedOf, DATUM_TYPES, isDatum, placementMatrix, withAttached } from './attached'
import { attachmentRows, editAttachment, sketchOnSelection } from './pd_attach'
import { deleteObjects, isObjectRef, partKey } from './part_wb'

export const SKETCH = 'Sketcher::SketchObject', PAD = 'PartDesign::Pad', POCKET = 'PartDesign::Pocket'
const ICON_OF: Record<string, IconName> = { [SKETCH]: 'pd-sketch', [PAD]: 'pd-pad', [POCKET]: 'pd-pocket',
  'PartDesign::Fillet': 'pd-fillet', 'PartDesign::Chamfer': 'pd-chamfer', 'PartDesign::Draft': 'pd-draft', 'PartDesign::Thickness': 'pd-thickness', ...REVOLVE_ICONS }
const KIND: Record<string, string> = { [SKETCH]: 'Sketch', [PAD]: 'Pad', [POCKET]: 'Pocket',
  'PartDesign::Fillet': 'Fillet', 'PartDesign::Chamfer': 'Chamfer', 'PartDesign::Draft': 'Draft', 'PartDesign::Thickness': 'Thickness', ...REVOLVE_KINDS }
for (const [t, d] of Object.entries(DATUM_TYPES)) { ICON_OF[t] = d.icon as IconName; KIND[t] = t } // the datums (pd_attach.tsx)
/** App::Origin's features, as FreeCAD names (Name) and labels (Label) them, with their ViewProviders' icons. */
export const ORIGIN: [string, string, IconName][] = [
  ['X_Axis', 'X-axis', 'std-axis'], ['Y_Axis', 'Y-axis', 'std-axis'], ['Z_Axis', 'Z-axis', 'std-axis'],
  ['XY_Plane', 'XY-plane', 'std-plane'], ['XZ_Plane', 'XZ-plane', 'std-plane'], ['YZ_Plane', 'YZ-plane', 'std-plane'], ['Origin001', 'Origin-Point', 'std-point'],
]
const PLANE_OF: Record<string, 'XY' | 'XZ' | 'YZ'> = { XY_Plane: 'XY', XZ_Plane: 'XZ', YZ_Plane: 'YZ' }

// ── the model ────────────────────────────────────────────────────────────────
/** A part shows as a PartDesign Body when it has a feature list (a Body made in the app, or a hand-written part with
 *  features on top of its solid, the BaseFeature). A hand-written part with none is a plain Part::Feature, as before. */
export const isBodyDoc = (d: FeatureDoc | undefined | null): d is FeatureDoc => !!d && d.body !== false && (d.features.length > 0 || !d.base)
export const refOf = (part: string, name: string) => `${part}/${name}`
export const splitRef = (ref: string) => { const i = ref.indexOf('/'); return [ref.slice(0, i), ref.slice(i + 1)] as const }
/** The scene's body made from this part module, if the scene draws it. */
export const bodyOfPart = (s: State, part: string): Body | undefined => s.scene?.bodies.find((b) => b.part === part)
/** ViewProviderSketchBased::claimChildren: a feature claims its profile sketch, which the tree shows under it. */
function consumers(doc: FeatureDoc): Record<string, string[]> {
  const out: Record<string, string[]> = {}
  for (const f of doc.features) if (f.type !== SKETCH && typeof f.profile === 'string') (out[f.profile] ??= []).push(f.name)
  return out
}
/** The Body's own Group in order, minus the sketches a feature claims (they show under it). */
const topLevel = (doc: FeatureDoc) => { const c = consumers(doc); return doc.features.filter((f) => f.type !== SKETCH || !c[f.name]?.length) }
const solidNames = (doc: FeatureDoc) => doc.features.filter((f) => f.type !== SKETCH && !isDatum(f.type)).map((f) => f.name)

/** A value as FEATURES keeps it: a number, or the name of a PARAMS entry or an expression over them (feature.py's value()). */
export function numberOf(v: unknown, params: Record<string, unknown>): number | null {
  if (typeof v === 'number') return v
  if (typeof v !== 'string' || !v.trim()) return null
  const vars: Record<string, quantity.Quantity> = {}
  for (const [k, x] of Object.entries(params)) if (typeof x === 'number') vars[k] = { value: x, dims: [0, 0, 0, 0, 0, 0, 0, 0] }
  try { return evaluate(v, vars).value } catch { return null }
}
/** Whether a feature is shown: a Body shows its Tip (ViewProvider::onChanged hides every other feature when one is shown);
 *  a sketch is shown until a feature takes it as its profile, which hides it, and Space flips that. */
export function featureVisible(s: State, part: string, f: Feature | string): boolean {
  const doc = s.features[part]
  if (!doc) return false
  const name = typeof f === 'string' ? f : f.name
  const feat = doc.features.find((x) => x.name === name)
  const body = bodyOfPart(s, part)
  const bodyShown = !body || !s.hidden.includes(body.name)
  if (!feat) return name === 'BaseFeature' ? bodyShown && !doc.tip : false
  if (feat.type === SKETCH) return !consumers(doc)[name]?.length !== s.sketchShown.includes(refOf(part, name))
  if (isDatum(feat.type)) return bodyShown && !s.sketchShown.includes(refOf(part, name)) // shown, as a new datum is
  return bodyShown && doc.tip === name
}

// ── edits: each POST is one undo step (`cad feature apply`) ──────────────────
const msg = (e: unknown) => (e instanceof Error ? e.message : String(e))
/** POST /api/<slug>/features/<part>: the ops as one step, built on the server before it stays. The console shows the
 *  `cad feature` line it is (PythonConsole echoing a GUI action). Returns the list after, or null when it was refused. */
export async function applyOps(part: string, ops: FeatureOp[], opts: { name?: string; line?: string } = {}): Promise<FeatureDoc | null> {
  const slug = getState().slug
  if (!slug) return null
  const line = opts.line ?? `cad feature apply ${slug} ${part} --ops '${JSON.stringify(ops)}'${opts.name ? ` --name '${opts.name}'` : ''}`
  if (getState().scriptToPyConsole) consoleLog('in', line)
  try {
    const r = await api.applyFeatures(slug, part, ops, opts.name)
    const d = r.data ?? {}
    if (r.exit > 2 || d.error || !d.doc) { report('err', `${opts.name ?? 'Edit'}: ${resultText(r)}`); return null }
    const doc = withAttached(d.doc as FeatureDoc)
    setState((s) => ({ features: { ...s.features, [part]: doc } }))
    const fails = Number(d.failing ?? 0)
    report(fails ? 'warn' : 'msg', `${part}: ${d.step}${d.built ? (fails ? `, ${fails} part gate${fails > 1 ? 's' : ''} not passing` : ', part gates pass') : ''}`)
    loadHistory()
    return doc
  } catch (e) {
    report('err', `${opts.name ?? 'Edit'}: ${msg(e)}`)
    return null
  }
}

/** PartDesignGui::getBody: the active Body, else the Body of what is selected in the tree, else the only one there is. */
export function targetBody(): string | null {
  const s = getState()
  if (s.activeBody && isBodyDoc(s.features[s.activeBody])) return s.activeBody
  const sel = s.featSel[0]
  if (sel) return splitRef(sel)[0]
  const fromScene = s.selected.map((n) => s.scene?.bodies.find((b) => b.name === n)?.part).find((p) => p && s.features[p])
  if (fromScene) return fromScene
  const bodies = Object.keys(s.features).filter((p) => isBodyDoc(s.features[p]))
  return bodies.length === 1 ? bodies[0] : null
}
const NO_BODY = 'In order to use PartDesign you need an active Body object in the document. Please make one active (double click) '
  + 'or create one.\n\nIf you have a legacy document with PartDesign objects without Body, use the migrate function in PartDesign '
  + 'to put them into a Body.'

/** PartDesign_Body: a new part module with an empty Body (`cad feature new`), made active. FreeCAD names it Body, Body001, …;
 *  so does this, as the part module's name. With a hand-written part selected, that part becomes the Body, its solid the
 *  BaseFeature (CmdPartDesignBody's baseFeature): its file changes when the first feature is added. */
export async function createBody() {
  const s = getState()
  if (!s.slug) { report('warn', 'New Body: make or open a document first (File > New Document)'); openTask('newDocument', ''); return }
  const sel = s.selected.length === 1 ? s.scene?.bodies.find((b) => b.name === s.selected[0]) : undefined
  if (sel?.part && s.features[sel.part]) {
    if (isBodyDoc(s.features[sel.part])) {
      await messageBox('warning', 'Bad base feature', `${sel.part} already belongs to a body and cannot be used as a base feature for another body.`)
      return
    }
    setState({ activeBody: sel.part })
    report('msg', `${sel.part} is the active Body; its solid is the BaseFeature its first feature adds to or cuts from`)
    return
  }
  const taken = new Set([...Object.keys(s.features), ...(s.scene?.bodies.map((b) => b.part ?? '') ?? [])])
  let name = 'Body', n = 0
  while (taken.has(name)) name = `Body${String(++n).padStart(3, '0')}`
  if (s.scriptToPyConsole) consoleLog('in', `cad feature new ${s.slug} ${name}`)
  try {
    const r = await api.cad(s.slug, ['feature', 'new', s.slug, name])
    if (r.exit !== 0) { report('err', `New Body: ${resultText(r)}`); return }
    const doc = (r.data?.doc ?? { part: name, params: {}, base: false, features: [], tip: null }) as FeatureDoc
    setState((x) => ({ features: { ...x.features, [name]: doc }, activeBody: name, featSel: [refOf(name, '')].slice(0, 0), selected: [] }))
    report('msg', `Add a Body: parts/${name}.py`)
    loadHistory()
    loadFeatures()
  } catch (e) { report('err', `New Body: ${msg(e)}`) }
}

/** PartDesign_NewSketch (SketchWorkflow::createSketch): with an Origin plane selected, the sketch goes straight onto it and
 *  opens; otherwise the attachment panel (TaskAttacher) asks for one, with the Origin's planes shown to pick from. A face of
 *  a solid cannot be a support here yet (feature.py attaches sketches to the Body's planes), so it gets the panel too. */
export async function newSketch() {
  const s = getState()
  if (!s.slug) { report('warn', 'New Sketch: make or open a document first'); return }
  let part = targetBody()
  if (!part) {
    const bodies = Object.keys(s.features).filter((p) => isBodyDoc(s.features[p]))
    if (bodies.length) { await messageBox('warning', 'No active body', NO_BODY); return }
    await createBody() // shouldCreateBody: no Body in the document, so make one
    part = getState().activeBody
    if (!part) return
  }
  const plane = s.featSel.map(splitRef).find(([p, n]) => p === part && PLANE_OF[n])
  if (plane) return addSketch(part, PLANE_OF[plane[1]], [0, 0, 0, 0, 0, 0])
  if (await sketchOnSelection(part)) return       // a face, a datum plane or a sketch selected (pd_attach.tsx)
  openTask('attach', part, `new:${SKETCH}`)
}
const nextName = (doc: FeatureDoc, base: string) => {
  const names = new Set(doc.features.map((f) => f.name))
  if (!names.has(base)) return base
  for (let i = 1; ; i++) { const n = `${base}${String(i).padStart(3, '0')}`; if (!names.has(n)) return n }
}
/** The sketch, made on its plane (SketchRequestSelection::createSketch: "New Sketch", FlatFace), then opened in the Sketcher. */
async function addSketch(part: string, support: 'XY' | 'XZ' | 'YZ', off: number[]) {
  const doc = getState().features[part]
  if (!doc) return false
  const name = nextName(doc, 'Sketch')
  const offset = off.some((x) => x !== 0) ? { attachment_offset: [[off[0], off[1], off[2]], [off[5], off[4], off[3]]] } : {}
  const feature = { name, type: SKETCH, support, ...offset, geometry: [], constraints: [] }
  const after = doc.tip ?? doc.features[doc.features.length - 1]?.name ?? null
  const done = await applyOps(part, [{ op: 'add', feature, after }], { name: 'New Sketch' })
  if (!done) return false
  setState({ featSel: [refOf(part, name)], selected: [] })
  editSketch(part, name)
  return true
}

/** PartDesign_Pad / PartDesign_Pocket (prepareProfileBased): a sketch selected, or the Body's last sketch no feature uses, is
 *  the profile; the task panel opens on a new feature, which OK makes ("Make Pad") and Cancel never writes. */
export async function padOrPocket(kind: 'pad' | 'pocket') {
  const s = getState()
  const part = targetBody()
  if (!part) { await messageBox('warning', 'No active body', NO_BODY); return }
  const doc = s.features[part]
  const selected = s.featSel.map(splitRef).find(([p, n]) => p === part && doc.features.find((f) => f.name === n)?.type === SKETCH)
  const used = consumers(doc)
  const free = doc.features.filter((f) => f.type === SKETCH && !used[f.name]?.length)
  const profile = selected?.[1] ?? (free.length === 1 ? free[0].name : null)
  if (!profile) {
    await messageBox('warning', 'No sketch to use',
      free.length ? 'Please select a sketch or a face, and then the command.' : 'Please create a sketch or 2D object first.')
    return
  }
  openTask(kind, part, profile)
}

/** Std_Edit / a double-click on a tree row: a sketch opens in the Sketcher, a Pad or Pocket its task panel ("Edit Pad"),
 *  the Body becomes the active one (ViewProviderBody::doubleClicked). */
export function editFeature(ref: string) {
  const [part, name] = splitRef(ref)
  const doc = getState().features[part]
  const f = findFeature(doc, name)
  if (!f) return
  if (isPdx(f.type)) return editPdx(part, name)
  if (f.type === SKETCH) return editSketch(part, name)
  if (f.type === PAD || f.type === POCKET) { setState({ task: { kind: f.type === PAD ? 'pad' : 'pocket', body: part, other: name, edit: true } }); showPanel('tasks'); return }
  if (isDatum(f.type)) return editAttachment(part, name)   // ViewProviderDatum::doubleClicked: the attachment editor
  if (editRevolveFeature(part, f)) return
  if (isDressUp(f.type)) return editDressUp(part, f)
  report('warn', `${name}: a ${f.type} has no task panel here yet`)
}
export function toggleActiveBody(part: string) {
  const on = getState().activeBody === part
  setState({ activeBody: on ? null : part })
}

/** PartDesign_MoveTip ("Set Tip"): the Body is built up to this feature; what comes after is kept and not built. */
export async function setTip() {
  const refs = getState().featSel
  if (refs.length !== 1) { await messageBox('warning', 'Selection error', 'Select exactly one Part Design feature or a body.'); return }
  const [part, name] = splitRef(refs[0])
  const doc = getState().features[part]
  const f = doc?.features.find((x) => x.name === name)
  if (!f || f.type === SKETCH) { await messageBox('warning', 'Selection error', 'Only a solid feature can be the tip of a body.'); return }
  if (doc.tip === name) { report('msg', `${name} is already the tip of the body`); return }
  await applyOps(part, [{ op: 'tip', name }], { name: 'Move tip to selected feature', line: `cad feature tip ${getState().slug} ${part} ${name}` })
}

/** PartDesign_MoveFeatureInTree ("Move Feature After…"): QInputDialog::getItem over the Body's features, then the move, and
 *  FreeCAD's question when the moved feature lands after the Tip. */
export function moveFeatureAfter() {
  const refs = getState().featSel.filter((r) => splitRef(r)[1] && !ORIGIN_NAMES.includes(splitRef(r)[1]))
  const parts = new Set(refs.map((r) => splitRef(r)[0]))
  if (!refs.length || parts.size !== 1) { void messageBox('warning', 'Selection error', 'Select one or more features from the same body.'); return }
  setPickItem({ part: [...parts][0], names: refs.map((r) => splitRef(r)[1]) })
}
let pickItem: { part: string; names: string[] } | null = null
const pickSubs = new Set<() => void>()
const setPickItem = (p: typeof pickItem) => { pickItem = p; pickSubs.forEach((f) => f()) }
async function moveAfter(part: string, names: string[], target: string | null) {
  const doc = getState().features[part]
  const ops: FeatureOp[] = []
  let last = target
  for (const n of doc.features.map((f) => f.name).filter((n) => names.includes(n))) {
    if (n === target) continue
    ops.push({ op: 'move', name: n, after: last })
    last = n
  }
  if (!ops.length) return
  const lastFeat = doc.features.find((f) => f.name === last)
  if (last !== target && doc.tip === target && lastFeat && lastFeat.type !== SKETCH) {
    const yes = await messageBox('question', 'Move Tip', 'The moved feature appears after the currently set tip.\n\nSet tip to last feature?', ['No', 'Yes'])
    if (yes === 'Yes') ops.push({ op: 'tip', name: last! })
  }
  await applyOps(part, ops, { name: 'Move a feature inside body' })
}
/** QInputDialog::getItem, as Move Feature After… asks: "Select a feature from the list". */
export function PickItemHost() {
  const [, redraw] = useState(0)
  useEffect(() => { const f = () => redraw((n) => n + 1); pickSubs.add(f); return () => { pickSubs.delete(f) } }, [])
  const p = pickItem
  const doc = p ? getState().features[p.part] : null
  const items = doc ? [doc.base ? 'BaseFeature' : 'Beginning of the body', ...doc.features.map((f) => f.name)] : []
  const [choice, setChoice] = useState(0)
  useEffect(() => setChoice(0), [p])
  if (!p || !doc) return null
  const ok = () => { setPickItem(null); void moveAfter(p.part, p.names, choice === 0 ? null : items[choice]) }
  return (
    <div className="msgbox-back" onKeyDown={(e) => { e.stopPropagation(); if (e.key === 'Escape') setPickItem(null); if (e.key === 'Enter') ok() }}>
      <div className="msgbox pd-getitem" role="dialog" aria-label="Move Feature After…">
        <div className="msgbox-title">Move Feature After…</div>
        <div className="msgbox-body pd-getitem-body">
          <label>Select a feature from the list</label>
          <QComboBox autoFocus value={String(choice)} onChange={(e) => setChoice(Number(e.target.value))}>
            {items.map((t, i) => <option key={i} value={String(i)}>{t}</option>)}
          </QComboBox>
        </div>
        <div className="msgbox-buttons">
          <button className="qbtn default" onClick={ok}>OK</button>
          <button className="qbtn" onClick={() => setPickItem(null)}>Cancel</button>
        </div>
      </div>
    </div>
  )
}

/** Std_Delete on a Body's rows (StdCmdDelete::activated): FreeCAD asks before deleting what others use ("Object
 *  Dependencies"), then deletes them in one transaction. The Origin and the BaseFeature are not deletable. */
export async function deleteFeatures(refs = getState().featSel) {
  if (refs.length && refs.every((r) => isObjectRef(getState(), r))) return deleteObjects(refs)   // Part objects (part_wb.tsx)
  const byPart = new Map<string, string[]>()
  for (const r of refs) {
    const [part, name] = splitRef(r)
    if (!name || ORIGIN_NAMES.includes(name)) continue
    byPart.set(part, [...(byPart.get(part) ?? []), name])
  }
  if (!byPart.size) {
    if (refs.some((r) => !splitRef(r)[1])) report('warn', 'Delete: a Body is its part module; delete parts/<name>.py to remove it (the agent\'s job, in the code)')
    return
  }
  for (const [part, names] of byPart) {
    const doc = getState().features[part]
    const { top, ops } = pdxDeleteOps(doc, names)
    const users = doc.features.filter((f) => !top.includes(f.name) && ((typeof f.profile === 'string' && top.includes(f.profile)) || pdxUses(f, top) || dressUpUses(f, top))).map((f) => f.name)
    if (users.length) {
      const answer = await messageBox('warning', 'Object Dependencies', `The following referencing objects might break.\n\nContinue?\n\n${users.join('\n')}`, ['Yes', 'No'])
      if (answer !== 'Yes') return
    }
    const done = await applyOps(part, ops, { name: 'Delete', line: `cad feature delete ${getState().slug} ${part} ${names.join(' ')}` })
    if (done) setState((s) => ({ featSel: s.featSel.filter((r) => !names.includes(splitRef(r)[1])) }))
  }
}

/** Space on a Body's rows (Std_ToggleVisibility): the Body and its Tip show and hide the body; a sketch shows over the model.
 *  An earlier solid feature has no shape of its own here (the scene has the Body's Tip): Set Tip shows it. */
export function toggleFeatureVisibility(refs = getState().featSel) {
  const s = getState()
  const flip: string[] = []
  for (const r of refs) {
    const [part, name] = splitRef(r)
    const doc = s.features[part]
    const f = doc?.features.find((x) => x.name === name)
    const body = bodyOfPart(s, part)
    if (!name || (f && f.name === doc.tip) || (name === 'BaseFeature' && !doc.tip)) { if (body) toggleVisibility([body.name]); continue }
    if (f?.type === SKETCH || isDatum(f?.type)) { flip.push(r); continue }
    if (f) report('warn', `${name} is not the Tip: the 3D view shows the Body at its Tip. Set Tip on ${name} shows the Body up to it.`)
  }
  if (flip.length) setState((x) => ({ sketchShown: [...x.sketchShown.filter((r) => !flip.includes(r)), ...flip.filter((r) => !x.sketchShown.includes(r))] }))
}

/** Tree.cpp's Rename (F2): the row's label is edited in place; Return renames the feature, Escape leaves it. FreeCAD renames
 *  the Label and keeps the internal Name; FEATURES names a feature once, so the name itself changes, and every reference. */
let renaming: string | null = null
const renameSubs = new Set<() => void>()
export function startRename(ref = getState().featSel[0]) {
  if (!ref || getState().featSel.length !== 1) return false
  const [, name] = splitRef(ref)
  if (!name || ORIGIN_NAMES.includes(name)) { report('warn', 'Rename: the Body is named by its part module, the Origin by FreeCAD'); return true }
  renaming = ref
  renameSubs.forEach((f) => f())
  return true
}
async function finishRename(ref: string, to: string | null) {
  renaming = null
  renameSubs.forEach((f) => f())
  const [part, name] = splitRef(ref)
  if (!to || to === name) return
  if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(to)) { report('err', `Rename: ${to} is not a name FEATURES can take (letters, digits and _)`); return }
  const done = await applyOps(part, [{ op: 'rename', name, to }], { name: `Rename ${name}.Label`, line: `cad feature rename ${getState().slug} ${part} ${name} ${to}` })
  if (done) setState({ featSel: [refOf(part, to)] })
}

// ── the tree (Tree.cpp's DocumentObjectItem, ViewProviderBody's claimChildren) ─────────────
export type TreeCtx = {
  iconSize: number; showDesc: boolean; showInternal: boolean; eyes: boolean; checkBoxes: boolean; editColor: string
  enter(name: string | null): void; cancelPreselect(): void
  /** The context menu over a row: the selection is that row's already. */
  menu(at: { x: number; y: number }): void
}
const open = new Map<string, boolean>() // DocumentObjectItem's expanded state, by row (the Origin starts folded, as FreeCAD's)
const openSubs = new Set<() => void>()
const isOpen = (ref: string, dflt: boolean) => open.get(ref) ?? dflt
const setOpen = (ref: string, v: boolean) => { open.set(ref, v); openSubs.forEach((f) => f()) }
/** The Body's Origin unfolded in the tree (TaskAttacher's visibilityAutomation shows it to pick from). */
export const openOrigin = (part: string) => setOpen(refOf(part, 'Origin'), true)

/** Picking a row: it alone, or added with Cmd/Ctrl; the 3D selection gives way (actions.ts select() clears this one back). */
function pickRow(ref: string, additive: boolean) {
  const s = getState()
  const featSel = additive ? (s.featSel.includes(ref) ? s.featSel.filter((r) => r !== ref) : [...s.featSel, ref]) : [ref]
  setState({ featSel, selected: [], subSel: [] })
  attachPicker?.(ref)
}

/** One row: the indentation and branch, the eye, the icon with its overlays, the label and the columns. */
function PdRow({ ctx, depth, refKey, icon, label, internal, desc, hidden, kids, dflt, overlays, bold, onDouble, title }:
  { ctx: TreeCtx; depth: number; refKey: string; icon: IconName; label: string; internal: string; desc?: string; hidden: boolean; kids: boolean; dflt: boolean
    overlays?: ReactNode; bold?: boolean; onDouble?(): void; title?: string }) {
  const sel = useStore((s) => s.featSel.includes(refKey))
  const [, redraw] = useState(0)
  useEffect(() => { const f = () => redraw((n) => n + 1); renameSubs.add(f); openSubs.add(f); return () => { renameSubs.delete(f); openSubs.delete(f) } }, [])
  const isRenaming = renaming === refKey
  const opened = isOpen(refKey, dflt)
  return (
    <div className={cls('trow', 'pdrow', sel && 'sel', hidden && 'hid')} data-ref={refKey} title={title}
      onClick={(e) => { ctx.cancelPreselect(); pickRow(refKey, e.metaKey || e.ctrlKey) }}
      onDoubleClick={() => onDouble?.()}
      onMouseEnter={() => ctx.enter(null)}
      onContextMenu={(e) => { e.preventDefault(); e.stopPropagation(); if (!getState().featSel.includes(refKey)) pickRow(refKey, false); ctx.menu({ x: e.clientX, y: e.clientY }) }}>
      <span className="tlab">
        <span className="pdindent" style={{ width: 6 + 12 * (depth - 1) }} />
        {kids ? <Twisty open={opened} onClick={() => setOpen(refKey, !opened)} /> : <span className="twisty-none" />}
        {ctx.checkBoxes && <input type="checkbox" className="tcheckbox" checked={sel} onClick={(e) => e.stopPropagation()} onChange={() => pickRow(refKey, true)} />}
        {ctx.eyes && <span className="teye" title="Toggle visibility (Space)" onClick={(e) => { e.stopPropagation(); toggleFeatureVisibility([refKey]) }}
          onDoubleClick={(e) => e.stopPropagation()}><Icon name={hidden ? 'eye-off' : 'eye'} size={ctx.iconSize} /></span>}
        <span className="ticon"><Icon name={icon} size={ctx.iconSize} />{overlays}</span>
        {isRenaming
          ? <input className="trename" autoFocus defaultValue={label} onClick={(e) => e.stopPropagation()} onBlur={(e) => void finishRename(refKey, e.currentTarget.value.trim())}
            onKeyDown={(e) => { e.stopPropagation(); if (e.key === 'Enter') e.currentTarget.blur(); if (e.key === 'Escape') void finishRename(refKey, null) }} />
          : <span className="tname" style={bold ? { fontWeight: 700 } : undefined}>{label}</span>}
      </span>
      {ctx.showDesc && <span className="tdesc">{desc ?? ''}</span>}
      {ctx.showInternal && <span className="tdesc">{internal}</span>}
    </div>
  )
}

/** A part module's Body in the tree: the Body row (the scene's body, when it draws one), then its Origin, BaseFeature and
 *  features in order, the Tip marked with PartDesign_Overlay_Tip, a sketch under the feature that uses it, what is hidden
 *  (everything but the Tip, and the sketches in use) greyed as Tree.cpp greys an invisible object. */
export function PdBodyRows({ ctx, part, body, bodyRow }: { ctx: TreeCtx; part: string; body: Body | undefined; bodyRow(children: ReactNode): ReactNode }) {
  const s = useStore((x) => x)
  const doc = s.features[part]
  const [, redraw] = useState(0)
  useEffect(() => { const f = () => redraw((n) => n + 1); openSubs.add(f); return () => { openSubs.delete(f) } }, [])
  if (!doc) return null
  const used = consumers(doc)
  const bodyRef = refOf(part, '')
  const opened = isOpen(bodyRef, true)
  const twisty = <Twisty open={opened} onClick={() => setOpen(bodyRef, !opened)} />
  const tipOverlay = <img className="tov tov-br" src="./freecad-icons/PartDesign_Overlay_Tip.svg" width={10} height={10} alt="" draggable={false} />
  const featureRow = (f: Feature, depth: number): ReactNode => {
    const r = refOf(part, f.name)
    const kids = f.type !== SKETCH && typeof f.profile === 'string' ? doc.features.filter((x) => x.name === f.profile && x.type === SKETCH) : pdxChildren(f)
    const after = solidNames(doc).indexOf(f.name) > solidNames(doc).indexOf(doc.tip ?? '') && f.type !== SKETCH
    const lcs = f.type === 'Part::LocalCoordinateSystem'
    const lcsIndex = (name: string) => doc.features.filter((x) => x.type === 'Part::LocalCoordinateSystem').findIndex((x) => x.name === name)
    const overlays = <>
      {f.name === doc.tip && f.type !== SKETCH && tipOverlay}
      {f.type === SKETCH && f.fully_constrained === false && <img className="tov tov-br" src="./freecad-icons/Sketcher_NotFullyConstrained.svg" width={10} height={10} alt="" draggable={false} />}
      {f.type === SKETCH && !f.support && !(f.attachment_support as unknown[] | undefined)?.length && <img className="tov tov-bl" src="./freecad-icons/Part_Detached.svg" width={10} height={10} alt="" draggable={false} />}
    </>
    const desc = [KIND[f.type] ?? pdxKind(f.type) ?? f.type, f.type !== SKETCH && f.profile ? `profile ${f.profile}` : null, after ? 'after the Tip: not built' : null].filter(Boolean).join(' · ')
    return (
      <div key={r} className="pdgroup">
        <PdRow ctx={ctx} depth={depth} refKey={r} icon={ICON_OF[f.type] ?? pdxIcon(f.type) ?? 'part'} label={f.name} internal={f.name} desc={desc}
          hidden={!featureVisible(s, part, f)} kids={kids.length > 0 || lcs} dflt={false} overlays={overlays} onDouble={() => editFeature(r)}
          title={after ? `${f.name} comes after the Tip (${doc.tip}): it is kept, not built` : undefined} />
        {kids.length > 0 && isOpen(r, false) && kids.map((k) => featureRow(k, depth + 1))}
        {lcs && isOpen(r, false) && ORIGIN.map(([n, label, icon]) => {
          // ViewProviderCoordinateSystem::claimChildren: its origin's features, labelled as FreeCAD's unique labels them
          const role = n === 'Origin001' ? 'Origin' : n, k = lcsIndex(f.name) + 1
          return <PdRow key={n} ctx={ctx} depth={depth + 1} refKey={`${r}/${role}`} icon={icon} label={`${label}${String(k).padStart(3, '0')}`}
            internal={`${role}${String(k + (role === 'Origin' ? 1 : 0)).padStart(3, '0')}`} hidden={!featureVisible(s, part, f)} kids={false} dflt={false} />
        })}
      </div>
    )
  }
  const originRef = refOf(part, 'Origin')
  const children = opened ? <>
    <PdRow ctx={ctx} depth={2} refKey={originRef} icon="std-origin" label="Origin" internal="Origin" hidden kids dflt={false} />
    {isOpen(originRef, false) && ORIGIN.map(([n, label, icon]) =>
      <PdRow key={n} ctx={ctx} depth={3} refKey={refOf(part, n)} icon={icon} label={label} internal={n} hidden={false} kids={false} dflt={false} />)}
    {doc.base && <PdRow ctx={ctx} depth={2} refKey={refOf(part, 'BaseFeature')} icon="part" label="BaseFeature" internal="BaseFeature"
      desc={`the solid parts/${part}.py builds`} hidden={!featureVisible(s, part, 'BaseFeature')} kids={false} dflt={false}
      overlays={!doc.tip ? tipOverlay : undefined} />}
    {topLevel(doc).map((f) => featureRow(f, 2))}
  </> : null
  void used
  return <>{bodyRow(twisty)}{children}</>
}

/** The tree's context menu on a Body's rows (TreeWidget::contextMenuEvent with PartDesignGui::Workbench::setupContextMenu,
 *  as the real FreeCAD 26.3 shows it on a Pad, a Sketch and a Body: ui/scripts/fcedit.json). */
export function featureTreeEntries(common: { expressionActions: Entry; linkActions: Entry; showHidden: Entry; properties(): void }): Entry[] {
  const s = getState(), refs = s.featSel, one = refs.length === 1 ? refs[0] : null
  const [part, name] = one ? splitRef(one) : ['', '']
  const doc = s.features[part]
  const f = doc?.features.find((x) => x.name === name)
  const isBody = !!one && !name
  const na = (label: string, why: string, extra: Partial<Exclude<Entry, 'sep'>> = {}): Entry => ({ label, disabled: true, title: `n/a: ${why}`, ...extra })
  const own: Entry[] = []
  if (f && f.type !== SKETCH && !isDatum(f.type)) own.push({ label: `Edit ${f.name}`, bold: true, onSelect: () => editFeature(one!) }, na('Set Face Colors', 'face colours are the material\'s here', { icon: 'pd-color-face' }), 'sep',
    { label: 'Set Tip', icon: 'pd-move-tip', cmd: 'PartDesign_MoveTip', onSelect: () => void setTip() })
  if (f?.type === SKETCH) own.push({ label: 'Edit Sketch', bold: true, onSelect: () => editFeature(one!) },
    { label: 'Edit Attachment', onSelect: () => editAttachment(part, name) }, 'sep')
  if (f && isDatum(f.type)) own.push({ label: 'Edit Attachment', onSelect: () => editAttachment(part, name) }, 'sep')
  if (isBody) own.push({ label: 'Active Body', checked: s.activeBody === part, onSelect: () => toggleActiveBody(part) }, 'sep')
  if (f) own.push(na('Move Object To…', 'a feature belongs to its part module', { icon: 'pd-move-feature' }),
    { label: 'Move Feature After…', icon: 'pd-move-in-tree', cmd: 'PartDesign_MoveFeatureInTree', onSelect: moveFeatureAfter }, 'sep')
  if (f && f.type !== SKETCH) own.push(na('Toggle Suppressed', 'FEATURES has no suppressed state'))
  own.push(na('Toggle Freeze', 'parts rebuild from source; there is no recompute to freeze', { icon: 'freeze' }), 'sep')
  const appearance = 'the Body shows its Tip with the part\'s colours; set them on the part\'s row of a hand-written part'
  return [...own,
    { label: 'Toggle Visibility', kbd: 'Space', icon: 'visibility', onSelect: () => toggleFeatureVisibility() },
    { label: 'Show Selection', icon: 'show-sel', onSelect: () => setFeatureVisible(true) },
    { label: 'Hide Selection', icon: 'hide', onSelect: () => setFeatureVisible(false) },
    na('Toggle Selectability', 'the 3D view picks the Body\'s shape', { icon: 'unselectable' }),
    na('Select All Instances', 'a feature has one instance'),
    'sep',
    na('Material', 'materials are set in the part\'s source', { icon: 'material' }),
    na('Appearance', appearance, { icon: 'appearance', kbd: '⌘D' }),
    na('Random Color', appearance, { icon: 'random-color' }),
    na('Toggle Transparency', appearance, { icon: 'transparency', kbd: 'V, T' }),
    'sep',
    { label: 'Cut', kbd: '⌘X', icon: 'edit-cut', disabled: true },
    { label: 'Copy', kbd: '⌘C', icon: 'edit-copy', onSelect: () => { void navigator.clipboard?.writeText(refs.map((r) => splitRef(r)[1] || splitRef(r)[0]).join('\n')) } },
    { label: 'Paste', kbd: '⌘V', icon: 'edit-paste', disabled: true },
    { label: 'Delete', kbd: '⌫', icon: 'edit-delete', cmd: 'Std_Delete', disabled: !refs.some((r) => { const [, n] = splitRef(r); return !!n && !ORIGIN_NAMES.includes(n) }), onSelect: () => void deleteFeatures() },
    { label: 'Send to Console', kbd: '⇧⌘P', icon: 'console', onSelect: () => consoleLog('in', refs.map((r) => splitRef(r).join('.')).join(' ')) },
    ...(f?.type === SKETCH || isBody ? [na('Transform', 'a Body\'s placement comes from assembly.py; select the part to move it', { icon: 'transform' }),
      na('Placement', 'a sketch is placed by its support and attachment offset', { icon: 'placement' })] : []),
    { label: 'Properties', kbd: '⌥↵', onSelect: common.properties },
    'sep',
    common.expressionActions, common.linkActions, common.showHidden,
    na('Toggle Visibility in Tree View', 'a Body\'s rows always show'),
    na('Add Dependent Objects to Selection', 'the features that use one show under it'),
    'sep',
    { label: 'Mark to Recompute', icon: 'recompute', onSelect: () => void loadFeatures() },
    { label: 'Recompute Object', kbd: '⇧⌘R', icon: 'recompute', onSelect: () => void loadFeatures() },
    'sep',
    { label: 'Rename', kbd: 'F2', disabled: !f, onSelect: () => startRename() },
  ]
}
function setFeatureVisible(on: boolean) {
  const s = getState()
  toggleFeatureVisibility(s.featSel.filter((r) => { const [p, n] = splitRef(r); return featureVisible(s, p, n || (s.features[p]?.tip ?? '')) !== on }))
}

// ── the property view (PropertyEditor: groups in name order, FreeCAD's display names) ─────────
const human = (camel: string) => camel.replace(/([a-z0-9])([A-Z])/g, '$1 $2').replace(/([A-Z])([A-Z][a-z])/g, '$1 $2')
type PropDef = { key: string; name: string; kind: 'length' | 'angle' | 'bool' | 'enum' | 'link' | 'vector' | 'text'; items?: string[]; ro?: (f: Feature) => string | null }
const TYPES_PAD = ['Length', 'UpToLast', 'UpToFirst', 'UpToFace', 'UpToShape'], TYPES_POCKET = ['Length', 'ThroughAll', 'UpToFirst', 'UpToFace', 'UpToShape']
const SIDES = ['One side', 'Two sides', 'Symmetric'], STARTS = ['Profile plane', 'Offset', 'Reference']
/** A Pad's or Pocket's Type property (Length, UpToLast, ThroughAll, …): feature_edit.py's dicts carry it as `type1`,
 *  since `type` is the TypeId ("PartDesign::Pad"); the file says `type=` as FreeCAD's Python does. */
export function extrudeType(f: Feature): string {
  return typeof f.type1 === 'string' ? f.type1 : 'Length'
}
const sideType = (f: Feature) => (f.side_type as string) ?? (f.midplane ? 'Symmetric' : extrudeType(f) === 'TwoLengths' ? 'Two sides' : 'One side')
/** FeatureExtrude's properties by group, as the property view lists them for a Pad and a Pocket; `ro` says why one is
 *  read-only (FreeCAD's ReadOnly status, set by its mode) or not editable here. */
function extrudeGroups(kind: 'Pad' | 'Pocket'): [string, PropDef[]][] {
  const two = (f: Feature) => (sideType(f) === 'Two sides' ? null : 'Side Type is not Two sides')
  const upto = (k: string) => (f: Feature) => (/^UpTo/.test(k === 'type1' ? extrudeType(f) : String(f[k] ?? 'Length')) ? null : 'only for an Up to … type')
  const noSel = () => 'a face or shape is picked in the task panel in FreeCAD; FEATURES names it in the code'
  const noTaper = () => 'feature.py does not taper yet'
  const groups: [string, PropDef[]][] = [
    ['Base', [{ key: 'name', name: 'Label', kind: 'text' }, { key: 'suppressed', name: 'Suppressed', kind: 'bool', ro: () => 'FEATURES has no suppressed state' }]],
    [kind, [{ key: 'side_type', name: 'Side Type', kind: 'enum', items: SIDES }, { key: 'use_custom_vector', name: 'Use Custom Vector', kind: 'bool' },
      { key: 'direction', name: 'Direction', kind: 'vector', ro: (f) => (f.use_custom_vector ? null : 'Use Custom Vector is off') },
      { key: 'reference_axis', name: 'Reference Axis', kind: 'text', ro: () => 'the sketch\'s normal; an edge is picked in FreeCAD' },
      { key: 'along_sketch_normal', name: 'Along Sketch Normal', kind: 'bool' }]],
    ['Part Design', [...(kind === 'Pocket' ? [{ key: 'operation', name: 'Operation', kind: 'enum' as const, items: ['Subtraction', 'Common'], ro: () => 'feature.py cuts; Common is not there yet' }] : []),
      { key: 'refine', name: 'Refine', kind: 'bool' }, { key: 'fuzzy_tolerance', name: 'Fuzzy Tolerance', kind: 'text', ro: () => 'the booleans run at OCCT\'s own tolerance' }]],
    ['Side1', [{ key: 'type1', name: 'Type', kind: 'enum', items: kind === 'Pad' ? TYPES_PAD : TYPES_POCKET }, { key: 'length', name: 'Length', kind: 'length', ro: (f) => (extrudeType(f) === 'Length' ? null : 'Type is not Length') },
      { key: 'up_to_face', name: 'Up To Face', kind: 'text', ro: noSel }, { key: 'up_to_shape', name: 'Up To Shape', kind: 'text', ro: noSel },
      { key: 'offset', name: 'Offset', kind: 'length', ro: upto('type1') }, { key: 'taper_angle', name: 'Taper Angle', kind: 'angle', ro: noTaper }]],
    ['Side2', [{ key: 'type2', name: 'Type2', kind: 'enum', items: kind === 'Pad' ? TYPES_PAD : TYPES_POCKET, ro: two }, { key: 'length2', name: 'Length2', kind: 'length', ro: two },
      { key: 'up_to_face2', name: 'Up To Face2', kind: 'text', ro: noSel }, { key: 'up_to_shape2', name: 'Up To Shape2', kind: 'text', ro: noSel },
      { key: 'offset2', name: 'Offset2', kind: 'length', ro: (f) => two(f) ?? upto('type2')(f) }, { key: 'taper_angle2', name: 'Taper Angle2', kind: 'angle', ro: noTaper }]],
    ['Sketch Based', [{ key: 'profile', name: 'Profile', kind: 'link' }, { key: 'midplane', name: 'Midplane', kind: 'bool', ro: () => 'replaced by Side Type (Symmetric), as in FreeCAD at this commit' }, { key: 'reversed', name: 'Reversed', kind: 'bool' },
      { key: 'allow_multi_face', name: 'Allow Multi Face', kind: 'bool', ro: () => 'a Body\'s features always allow several faces' }]],
    ['Start', [{ key: 'start_type', name: 'Start Type', kind: 'enum', items: STARTS }, { key: 'start_offset', name: 'Start Offset', kind: 'length', ro: (f) => (f.start_type === 'Offset' ? null : 'Start Type is not Offset') },
      { key: 'start_reference', name: 'Start Reference', kind: 'text', ro: () => 'a face is picked in FreeCAD; FEATURES names it in the code' }]],
  ]
  return groups
}
/** FeatureExtrude's defaults (FeatureExtrude.cpp, FeaturePad.cpp, FeaturePocket.cpp): what a property shows that FEATURES leaves out. */
const DEFAULTS: Record<string, unknown> = { side_type: 'One side', use_custom_vector: false, direction: [0, 0, 1], reference_axis: '', along_sketch_normal: true,
  operation: 'Subtraction', refine: true, fuzzy_tolerance: 0, type1: 'Length', length2: 10, up_to_face: '', up_to_shape: '', offset: 0, taper_angle: 0,
  type2: 'Length', up_to_face2: '', up_to_shape2: '', offset2: 0, taper_angle2: 0, midplane: false, reversed: false, allow_multi_face: true,
  start_type: 'Profile plane', start_offset: 0, start_reference: '', suppressed: false }
const LENGTH_DEFAULT: Record<string, number> = { [PAD]: 10, [POCKET]: 5 }

/** The Data tab for a Body's row: a feature's properties (editable ones write through `cad feature set`), a sketch's, the
 *  Body's, or the Origin's. */
export function FeatureProps({ refKey }: { refKey: string }) {
  useStore((s) => s.units)
  const s = useStore((x) => x)
  const [part, name] = splitRef(refKey)
  const doc = s.features[part]
  if (!doc) return null
  const f = findFeature(doc, name)
  const vars = Object.fromEntries(Object.entries(doc.params).filter(([, v]) => typeof v === 'number').map(([k, v]) => [k, { value: v as number, dims: [0, 0, 0, 0, 0, 0, 0, 0] as quantity.Quantity['dims'] }]))
  const set = (props: Record<string, unknown>) => {
    const k = Object.keys(props)[0]
    const label = k === 'name' ? `Rename ${name}.Label` : `Edit ${name}.${k.split('_').map((w) => w[0].toUpperCase() + w.slice(1)).join('')}`
    if (k === 'name') return void finishRename(refKey, String(props.name))
    void applyOps(part, [{ op: 'set', name, props }], { name: label, line: `cad feature set ${s.slug} ${part} ${name} ${Object.entries(props).map(([a, b]) => `${a}=${typeof b === 'string' ? b : JSON.stringify(b)}`).join(' ')}` })
  }
  if (!name) {
    const body = bodyOfPart(s, part)
    return <>
      <Group title="Base">
        <Row k="Allow Compound" v="true" />
        <Row k="Tip" v={doc.tip ?? ''} />
        <Row k="Base Feature" v={doc.base ? `parts/${part}.py's solid` : ''} />
        <Row k="Label" v={part} />
        <Row k="Group" v={`[${doc.features.map((x) => x.name).join(', ')}]`} />
        {body && <Row k="Placement" v={body.placement ? 'moved by hand (placements.toml)' : 'from assembly.py'} />}
      </Group>
    </>
  }
  if (!f) {
    const o = ORIGIN.find(([n]) => n === name)
    return <Group title="Base"><Row k="Label" v={o?.[1] ?? name} /><Row k="Placement" v={name === 'XZ_Plane' ? '[(1.00 0.00 0.00); 90.00°; (0.00 mm  0.00 mm  0.00 mm)]' : name === 'YZ_Plane' ? '[(0.58 0.58 0.58); 120.00°; (0.00 mm  0.00 mm  0.00 mm)]' : '[(0.00 0.00 1.00); 0.00°; (0.00 mm  0.00 mm  0.00 mm)]'} /></Group>
  }
  if (f.type === SKETCH) {
    return <>
      <Group title="Attachment">{attachmentRows(f).map(([k, x]) => <Row key={k} k={k} v={x} />)}</Group>
      <Group title="Base"><EditRow k="Label" value={f.name} type="str" onCommit={(v) => set({ name: v })} /></Group>
      <Group title="Sketch">
        <Row k="Constraints" v={`[${(f.constraints ?? []).length} constraints]`} />
        <Row k="Geometry" v={`[${(f.geometry ?? []).length} elements]`} />
      </Group>
    </>
  }
  if (isDatum(f.type)) {
    // a datum: AttachExtension's properties, then its Base (Label, Placement), and PartDesign::Plane's Size
    const pl = attachedOf(f)?.placement
    const sz = ['resize_mode', 'length', 'width'].filter((k) => k in f)
    return <>
      <Group title="Attachment">{attachmentRows(f).map(([k, x]) => <Row key={k} k={k} v={x} />)}</Group>
      <Group title="Base"><EditRow k="Label" value={f.name} type="str" onCommit={(x) => set({ name: x })} />
        <Row k="Placement" v={pl ? `[Pos=(${pl.position.map((x) => x.toFixed(2)).join(', ')}), Yaw-Pitch-Roll=(${pl.ypr.map((x) => x.toFixed(2)).join(', ')})]` : ''} /></Group>
      {sz.length > 0 && <Group title="Size">{sz.map((k) => <Row key={k} k={human(k.split('_').map((w) => w[0].toUpperCase() + w.slice(1)).join(''))} v={String(f[k])} />)}</Group>}
    </>
  }
  if (REVOLVE_KINDS[f.type]) return <RevolveProps part={part} f={f} set={set} finishRename={(v) => void finishRename(refKey, v)} />
  if (isDressUp(f.type)) return <DressUpProps part={part} f={f} set={set} onRename={(n) => void finishRename(refKey, n)} />
  if (isPdx(f.type)) return <PdxProps part={part} name={name} />
  if (f.type !== PAD && f.type !== POCKET) return <Group title="Base"><Row k="Label" v={f.name} /><Row k="Type" v={f.type} /></Group>
  const sketches = doc.features.filter((x) => x.type === SKETCH).map((x) => x.name)
  const value = (d: PropDef) => (d.key === 'name' ? f.name : d.key === 'type1' ? extrudeType(f) : d.key === 'side_type' ? sideType(f) : d.key === 'length' ? (f.length ?? LENGTH_DEFAULT[f.type]) : d.key === 'length2' ? (f.length2 ?? LENGTH_DEFAULT[f.type]) : f[d.key] ?? DEFAULTS[d.key])
  const row = (d: PropDef): ReactNode => {
    let v = value(d)
    const why = d.ro?.(f) ?? null
    if (d.key === 'direction' && !f.use_custom_vector) {
      // FeatureExtrude::computeDirection: without a custom vector, Direction is the sketch's normal, away from the material
      // for a Pocket, flipped by Reversed (FreeCAD shows [0 0 1] for a Pad on XY, [0 0 -1] for a Pocket)
      const sk = doc.features.find((x) => x.name === f.profile)
      const n = sk ? new THREE.Vector3(0, 0, 1).transformDirection(sketchMatrix(sk)) : new THREE.Vector3(0, 0, 1)
      n.multiplyScalar((f.type === POCKET ? -1 : 1) * (f.reversed ? -1 : 1))
      v = n.toArray().map((x) => Math.round(x * 1e9) / 1e9 + 0)
    }
    const shown = (x: unknown) => (d.kind === 'length' ? qtext(numberOf(x, doc.params), LENGTH) + (typeof x === 'string' ? `  (= ${x})` : '')
      : d.kind === 'angle' ? qtext(numberOf(x, doc.params), ANGLE) : d.kind === 'vector' ? `[${(Array.isArray(x) ? x : [0, 0, 1]).map((n) => Number(n).toFixed(2)).join(' ')}]` : String(x ?? ''))
    if (why) return <Row key={d.key} k={<span title={`Read-only: ${why}`}>{d.name}</span>} v={shown(v)} />
    if (d.kind === 'bool') return <EditRow key={d.key} k={d.name} value={v === true} type="bool" onCommit={(x) => set({ [d.key]: x })} />
    if (d.kind === 'enum' || d.kind === 'link') {
      const items = d.kind === 'link' ? sketches : d.items!
      return <div key={d.key} className="prow" tabIndex={0}><span className="pk" style={propPad(0)}>{d.name}</span>
        <span className="pv"><QComboBox className="qselect-pv" value={String(v)} onChange={(e) => set({ [d.key]: e.target.value })}>{items.map((o) => <option key={o}>{o}</option>)}</QComboBox></span></div>
    }
    if (d.kind === 'length' || d.kind === 'angle') {
      const n = numberOf(v, doc.params) ?? 0
      return <EditRow key={d.key} k={d.name} value={n} type="float" kind={d.kind === 'length' ? 'Length' : 'Angle'} vars={vars} owner={f.name}
        onCommit={(x) => set({ [d.key]: x })} onExpr={(text) => set({ [d.key]: text })} note={typeof v === 'string' ? `= ${v}` : undefined} />
    }
    return <EditRow key={d.key} k={d.name} value={String(v)} type="str" onCommit={(x) => set({ [d.key]: x })} />
  }
  return <>{extrudeGroups(f.type === PAD ? 'Pad' : 'Pocket').map(([g, defs]) => <Group key={g} title={g}>{defs.map(row)}</Group>)}</>
}
const qtext = (n: number | null, dims: quantity.Quantity['dims']) => (n === null ? '?' : quantity.userString({ value: n, dims }).text)
function planeOf(support: unknown): 'XY' | 'XZ' | 'YZ' | null {
  const t = JSON.stringify(support ?? '')
  return t.includes('XZ') ? 'XZ' : t.includes('YZ') ? 'YZ' : t.includes('XY') ? 'XY' : null
}

// ── geometry: a sketch's curves in its plane, and its profile extruded (the preview) ─────────────
type Curve = { kind: 'line'; a: [number, number]; b: [number, number]; cons: boolean } | { kind: 'circle'; c: [number, number]; r: number; cons: boolean }
  | { kind: 'arc'; c: [number, number]; r: number; a0: number; a1: number; cons: boolean } | { kind: 'point'; p: [number, number]; cons: boolean }
const pt = (v: unknown): [number, number] | null => (Array.isArray(v) && v.length >= 2 && v.every((x) => typeof x === 'number') ? [v[0] as number, v[1] as number]
  : v && typeof v === 'object' && typeof (v as any).x === 'number' ? [(v as any).x, (v as any).y] : null)
/** One entry of a sketch's geometry as the part-file layer hands it: feature.py's LineSegment/Circle/ArcOfCircle/Point, as an
 *  object ({"type": "LineSegment", "start", "end"}, {"type": "Circle", "center", "radius"}, …) or a call's argument list. */
export function curveOf(g: unknown): Curve | null {
  if (!g || typeof g !== 'object') return null
  const o = g as Record<string, unknown>
  const args = Array.isArray(g) ? (g as unknown[]).slice(1) : (Array.isArray(o.args) ? o.args as unknown[] : [])
  const type = String(Array.isArray(g) ? g[0] : o.type ?? o.kind ?? o.geometry ?? '')
  const cons = o.construction === true
  const n = (...ks: string[]) => { for (const k of ks) if (typeof o[k] === 'number') return o[k] as number; return null }
  const p = (...ks: string[]) => { for (const k of ks) { const v = pt(o[k]); if (v) return v } return null }
  if (/Line/i.test(type)) { const a = p('start', 'p1', 'a', 'start_point') ?? pt(args[0]), b = p('end', 'p2', 'b', 'end_point') ?? pt(args[1]); return a && b ? { kind: 'line', a, b, cons } : null }
  if (/Arc/i.test(type)) {
    const c = p('center', 'c') ?? pt(args[0]), r = n('radius', 'r') ?? (args[1] as number), a0 = n('start_angle', 'a0', 'startAngle') ?? (args[2] as number), a1 = n('end_angle', 'a1', 'endAngle') ?? (args[3] as number)
    return c && [r, a0, a1].every((x) => typeof x === 'number') ? { kind: 'arc', c, r, a0, a1, cons } : null
  }
  if (/Circle/i.test(type)) { const c = p('center', 'c') ?? pt(args[0]), r = n('radius', 'r') ?? (args[1] as number); return c && typeof r === 'number' ? { kind: 'circle', c, r, cons } : null }
  if (/Point/i.test(type)) { const q = p('point', 'p', 'at', 'position') ?? pt(args[0]); return q ? { kind: 'point', p: q, cons } : null }
  return null
}
/** The sketch's placement in the part (feature.py's planes: XZ has x along X, y along Z and the normal -Y; YZ has x along Y,
 *  y along Z, the normal +X), times its AttachmentOffset: (x, y, z) or ((x, y, z), (yaw, pitch, roll)) in degrees. */
export function sketchMatrix(f: Feature): THREE.Matrix4 {
  const att = attachedOf(f)
  if (att?.placement) return placementMatrix(att.placement) // attached by the Body (a face, a datum, …): the server's
  const plane = planeOf(f.support) ?? 'XY'
  const m = new THREE.Matrix4()
  if (plane === 'XZ') m.makeBasis(new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, 0, 1), new THREE.Vector3(0, -1, 0))
  else if (plane === 'YZ') m.makeBasis(new THREE.Vector3(0, 1, 0), new THREE.Vector3(0, 0, 1), new THREE.Vector3(1, 0, 0))
  const off = f.attachment_offset as unknown
  if (Array.isArray(off)) {
    const pos = (Array.isArray(off[0]) ? off[0] : off) as number[]
    const ypr = (Array.isArray(off[0]) ? off[1] : null) as number[] | null
    const o = new THREE.Matrix4()
    if (ypr) o.makeRotationFromEuler(new THREE.Euler(THREE.MathUtils.degToRad(ypr[2] ?? 0), THREE.MathUtils.degToRad(ypr[1] ?? 0), THREE.MathUtils.degToRad(ypr[0] ?? 0), 'ZYX'))
    o.setPosition(pos[0] ?? 0, pos[1] ?? 0, pos[2] ?? 0)
    m.multiply(o)
  }
  return m
}
const partMatrix = (b: Body | undefined) => { const m = new THREE.Matrix4(); if (b?.matrix?.length === 16) m.fromArray(b.matrix).transpose(); return m }
function polyline(c: Curve): THREE.Vector2[] {
  if (c.kind === 'line') return [new THREE.Vector2(...c.a), new THREE.Vector2(...c.b)]
  if (c.kind === 'point') return [new THREE.Vector2(...c.p)]
  const [a0, a1] = c.kind === 'circle' ? [0, 2 * Math.PI] : [c.a0, c.a1 < c.a0 ? c.a1 + 2 * Math.PI : c.a1]
  const n = Math.max(8, Math.ceil(((a1 - a0) / (2 * Math.PI)) * 64))
  return Array.from({ length: n + 1 }, (_, i) => { const t = a0 + ((a1 - a0) * i) / n; return new THREE.Vector2(c.c[0] + c.r * Math.cos(t), c.c[1] + c.r * Math.sin(t)) })
}
/** The sketch's closed wires (TopoShape::makeElementWires joins edges end to end), each a polygon, outer ones before holes. */
export function profileLoops(curves: Curve[]): THREE.Vector2[][] {
  const loops: THREE.Vector2[][] = []
  const open = curves.filter((c) => !c.cons && (c.kind === 'line' || c.kind === 'arc')).map(polyline)
  for (const c of curves) if (!c.cons && c.kind === 'circle') loops.push(polyline(c).slice(0, -1))
  const tol = 1e-6 * Math.max(1, ...open.flat().map((v) => Math.abs(v.x) + Math.abs(v.y)))
  while (open.length) {
    const chain = open.shift()!.slice()
    for (let grew = true; grew;) {
      grew = false
      for (let i = 0; i < open.length; i++) {
        const seg = open[i], end = chain[chain.length - 1]
        if (seg[0].distanceTo(end) < tol) chain.push(...seg.slice(1))
        else if (seg[seg.length - 1].distanceTo(end) < tol) chain.push(...seg.slice(0, -1).reverse())
        else continue
        open.splice(i, 1); grew = true; break
      }
    }
    if (chain.length > 2 && chain[0].distanceTo(chain[chain.length - 1]) < tol) loops.push(chain.slice(0, -1))
  }
  return loops
}
function shapesOf(loops: THREE.Vector2[][]): THREE.Shape[] {
  const area = (l: THREE.Vector2[]) => Math.abs(THREE.ShapeUtils.area(l))
  const sorted = [...loops].sort((a, b) => area(b) - area(a))
  const inside = (p: THREE.Vector2, poly: THREE.Vector2[]) => {
    let c = false
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      if ((poly[i].y > p.y) !== (poly[j].y > p.y) && p.x < ((poly[j].x - poly[i].x) * (p.y - poly[i].y)) / (poly[j].y - poly[i].y) + poly[i].x) c = !c
    }
    return c
  }
  const shapes: { loop: THREE.Vector2[]; shape: THREE.Shape; depth: number }[] = []
  for (const loop of sorted) {
    const parents = shapes.filter((s) => inside(loop[0], s.loop))
    const depth = parents.length
    if (depth % 2 === 0) shapes.push({ loop, shape: new THREE.Shape(loop), depth })
    else { const host = parents[parents.length - 1]; host.shape.holes.push(new THREE.Path(loop)); shapes.push({ loop, shape: host.shape, depth }) }
  }
  return [...new Set(shapes.filter((s) => s.depth % 2 === 0).map((s) => s.shape))]
}
/** A sketch drawn over the model, in SketchEdgeColor (FreeCAD Light: #212529) and 2 px (DefaultShapeLineWidth). */
export function sketchObject(f: Feature, body: Body | undefined): THREE.Object3D | null {
  const curves = (f.geometry ?? []).map(curveOf).filter((c): c is Curve => !!c)
  if (!curves.length) return null
  const g = new THREE.Group()
  const mat = new THREE.LineBasicMaterial({ color: 0x212529, linewidth: 2 }), cmat = new THREE.LineDashedMaterial({ color: 0x212529, dashSize: 1, gapSize: 1 })
  for (const c of curves) {
    const pts = polyline(c).map((v) => new THREE.Vector3(v.x, v.y, 0))
    if (c.kind === 'point') { g.add(new THREE.Points(new THREE.BufferGeometry().setFromPoints(pts), new THREE.PointsMaterial({ color: 0x212529, size: 4, sizeAttenuation: false }))); continue }
    const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), c.cons ? cmat : mat)
    if (c.cons) line.computeLineDistances()
    g.add(line)
  }
  g.applyMatrix4(partMatrix(body).multiply(sketchMatrix(f)))
  return g
}

/** The preview overlay of a Pad or Pocket being edited (ViewProvider::attachPreview, SoPreviewShape): the tool, the profile
 *  extruded along the sketch's normal, in PreviewAdditiveColor (0, 1, 0.6) or PreviewSubtractiveColor (1, 0, 0) at
 *  SoPreviewShape's transparency 0.8, with its edges. Up to … and Through all run to the far side of the model's box. */
export type ExtrudeSpec = { kind: 'pad' | 'pocket'; side_type: string; type: string; length: number; type2: string; length2: number; reversed: boolean; offset: number; start_type: string; start_offset: number }
export function previewObject(spec: ExtrudeSpec, sketch: Feature, body: Body | undefined): THREE.Object3D | null {
  const shapes = shapesOf(profileLoops((sketch.geometry ?? []).map(curveOf).filter((c): c is Curve => !!c)))
  if (!shapes.length) return null
  const toPart = partMatrix(body).multiply(sketchMatrix(sketch))
  // the sketch's normal in the part, and the model's extent along it from the sketch plane (Through all, Up to …)
  const origin = new THREE.Vector3().applyMatrix4(toPart), normal = new THREE.Vector3(0, 0, 1).transformDirection(toPart)
  const box = getView()?.modelBox()
  const reach = (sign: number) => {
    if (!box || box.isEmpty()) return 100
    let far = 0
    for (const x of [box.min.x, box.max.x]) for (const y of [box.min.y, box.max.y]) for (const z of [box.min.z, box.max.z]) far = Math.max(far, sign * new THREE.Vector3(x, y, z).sub(origin).dot(normal))
    return Math.max(far, 1) + 1
  }
  const dir = (spec.kind === 'pad' ? 1 : -1) * (spec.reversed ? -1 : 1)
  const amount = (type: string, len: number, sign: number) => (type === 'Length' ? len : reach(sign))
  let z0: number, z1: number
  if (spec.side_type === 'Symmetric') { const l = amount(spec.type, spec.length, dir); z0 = -l / 2; z1 = l / 2 }
  else if (spec.side_type === 'Two sides') { z1 = dir * amount(spec.type, spec.length, dir); z0 = -dir * amount(spec.type2, spec.length2, -dir) }
  else { z0 = 0; z1 = dir * amount(spec.type, spec.length, dir) }
  const start = spec.start_type === 'Offset' ? dir * spec.start_offset : 0
  const lo = Math.min(z0, z1) + start, depth = Math.abs(z1 - z0)
  if (!(depth > 1e-9)) return null
  const geo = new THREE.ExtrudeGeometry(shapes, { depth, bevelEnabled: false, curveSegments: 32 })
  geo.translate(0, 0, lo)
  const color = spec.kind === 'pad' ? new THREE.Color(0, 1, 0.6) : new THREE.Color(1, 0, 0)
  const g = new THREE.Group()
  g.add(new THREE.Mesh(geo, new THREE.MeshPhongMaterial({ color, transparent: true, opacity: 0.2, depthWrite: false, side: THREE.DoubleSide })))
  g.add(new THREE.LineSegments(new THREE.EdgesGeometry(geo, 20), new THREE.LineBasicMaterial({ color, linewidth: 2 })))
  g.applyMatrix4(toPart)
  return g
}

/** The Origin's planes while New Sketch asks for one (setOriginTemporaryVisibility, ViewProviderPlane): a quad from 8 to
 *  DatumPlaneSize (62) in its first quadrant, coloured by the axis it is normal to (AxisZColor for XY, …), 0.85 transparent,
 *  with its label; each can be clicked. */
export function originPlanes(body: Body | undefined, temporary = false): THREE.Object3D {
  const g = new THREE.Group(), size = 62, off = 8
  const colors = getState().axisColors
  for (const [name, label, color] of [['XY_Plane', 'XY-plane', colors.z], ['XZ_Plane', 'XZ-plane', colors.y], ['YZ_Plane', 'YZ-plane', colors.x]] as const) {
    const quad = new THREE.Group()
    quad.userData.pickName = name
    const shape = new THREE.Shape([new THREE.Vector2(size, size), new THREE.Vector2(size, off), new THREE.Vector2(off, off), new THREE.Vector2(off, size)])
    const face = new THREE.Mesh(new THREE.ShapeGeometry(shape), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.15, side: THREE.DoubleSide, depthWrite: false }))
    face.userData.pickName = name
    quad.add(face)
    quad.add(new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(shape.getPoints().map((p) => new THREE.Vector3(p.x, p.y, 0))), new THREE.LineBasicMaterial({ color })))
    const canvas = document.createElement('canvas'); canvas.width = 128; canvas.height = 32
    const ctx = canvas.getContext('2d')!
    ctx.font = 'bold 20px sans-serif'; ctx.fillStyle = color; ctx.textAlign = 'right'; ctx.fillText(label, 124, 24)
    const sprite = new THREE.Mesh(new THREE.PlaneGeometry(24, 6), new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(canvas), transparent: true, side: THREE.DoubleSide, depthWrite: false }))
    sprite.position.set(size / 2 - 2 - 12, size / 2 - 6, 0.01)
    quad.add(sprite)
    quad.applyMatrix4(sketchMatrix({ name, type: SKETCH, support: PLANE_OF[name] }))
    quad.userData.shapeScale = temporary ? 2 : 1   // DatumPlaneSize in pixels; DatumTemporaryScaleFactor while picking
    g.add(quad)
  }
  g.applyMatrix4(partMatrix(body))
  return g
}

// What the 3D view draws for the Bodies: the sketches shown, kept in step with the store.
let shownKey = ''
subscribe(() => {
  const s = getState(), v = getView()
  if (!v) return
  const items: [string, Feature, Body | undefined][] = []
  for (const [part, doc] of Object.entries(s.features)) for (const f of doc.features) if (f.type === SKETCH && featureVisible(s, part, f)) items.push([refOf(part, f.name), f, bodyOfPart(s, part)])
  const key = JSON.stringify(items.map(([r, f, b]) => [r, f.geometry, f.support, f.attachment_offset, b?.matrix])) + (s.scene?.source_hash ?? '')
  if (key === shownKey) return
  shownKey = key
  const g = new THREE.Group()
  for (const [, f, b] of items) { const o = sketchObject(f, b); if (o) g.add(o) }
  v.setHelper('pd-sketches', g.children.length ? g : null)
})

// ── task panels ──────────────────────────────────────────────────────────────
/** While New Sketch's panel is open, a click on an Origin plane (in the 3D view or the tree) is its reference. */
let attachPicker: ((ref: string) => void) | null = null
/** pd_attach.tsx's Attachment panel takes the tree's clicks as references while it is open. */
export function setAttachPicker(f: ((ref: string) => void) | null) { attachPicker = f }
function TaskHead({ title, icon, children }: { title: string; icon: IconName; children: ReactNode }) {
  return <TaskBox title={title} icon={icon}>{children}</TaskBox>
}
function OkCancel({ onOk, onCancel, okDisabled }: { onOk(): void; onCancel(): void; okDisabled?: boolean }) {
  return <div className="tbuttons pd-buttons"><button className="qbtn default" disabled={okDisabled} onClick={onOk}>OK</button><button className="qbtn" onClick={onCancel}>Cancel</button></div>
}
/** Pad and Pocket's task panel (TaskPadPocketParameters.ui, laid out by TaskExtrudeParameters::updateWholeUI/updateSideUI):
 *  Start, Direction, Type, Length or Offset to face, Taper angle, the second side's, Reversed, the Direction group,
 *  Operation (a Pocket's), Recompute on change, then Preview. A new feature has FreeCAD's defaults (Pad 10 mm, Pocket 5 mm).
 *  The preview overlay follows every change; OK writes the feature ("Make Pad", or "Edit Pad" for one double-clicked) and
 *  the server builds it, Cancel writes nothing. */
export function ExtrudeTask({ kind, part, name, edit }: { kind: 'pad' | 'pocket'; part: string; name: string; edit: boolean }) {
  const s = useStore((x) => x)
  const doc = s.features[part]
  const existing = edit ? doc?.features.find((f) => f.name === name) : undefined
  const profileName = existing ? String(existing.profile ?? '') : name
  const sketch = doc?.features.find((f) => f.name === profileName)
  const num = (v: unknown, d: number) => numberOf(v, doc?.params ?? {}) ?? d
  const initial = useMemo(() => ({
    start_type: String(existing?.start_type ?? 'Profile plane'), start_offset: num(existing?.start_offset, 0),
    side_type: existing ? sideType(existing) : 'One side', type: existing ? extrudeType(existing) : 'Length',
    length: num(existing?.length, kind === 'pad' ? 10 : 5), offset: num(existing?.offset, 0),
    type2: String(existing?.type2 ?? 'Length'), length2: num(existing?.length2, kind === 'pad' ? 10 : 5), offset2: num(existing?.offset2, 0),
    reversed: existing?.reversed === true, along_sketch_normal: existing?.along_sketch_normal !== false,
  }), [part, name, edit])
  const [v, setV] = useState(initial)
  const [update, setUpdate] = useState(true)
  const [overlay, setOverlay] = useState(true)
  const set = (patch: Partial<typeof v>) => setV((x) => ({ ...x, ...patch }))
  const types = kind === 'pad' ? [['Length', 'Dimension'], ['UpToLast', 'To last'], ['UpToFirst', 'To first'], ['UpToFace', 'Up to face'], ['UpToShape', 'Up to shape']]
    : [['Length', 'Dimension'], ['ThroughAll', 'Through all'], ['UpToFirst', 'To first'], ['UpToFace', 'Up to face'], ['UpToShape', 'Up to shape']]
  const sides: [string, string][] = [['One side', 'One sided'], ['Two sides', 'Two sided'], ['Symmetric', 'Symmetric']]
  const body = bodyOfPart(s, part)
  const drawn = useRef(false)
  useEffect(() => {
    // Recompute on change off: the preview stays as it was until it is checked again (TaskFeatureParameters::recomputeFeature)
    if (!update && drawn.current) return
    drawn.current = true
    getView()?.setHelper('pd-preview', overlay && sketch ? previewObject({ kind, ...v }, sketch, body) : null)
  }, [v, overlay, update, sketch, body])
  useEffect(() => () => { getView()?.setHelper('pd-preview', null) }, [])
  if (!doc || !sketch) return <div className="tasks"><p className="hint">{part}: no sketch {profileName}</p></div>
  const label = kind === 'pad' ? 'Pad' : 'Pocket'
  /** What the panel sets, in FreeCAD's property names (snake_case; the Type property is `type1`, `type` being the TypeId). */
  const props = (): Record<string, unknown> => {
    const out: Record<string, unknown> = { profile: sketch.name, side_type: v.side_type, type1: v.type, length: v.length, reversed: v.reversed }
    if (v.type !== 'Length') out.offset = v.offset
    if (v.side_type === 'Two sides') { out.type2 = v.type2; out.length2 = v.length2; if (v.type2 !== 'Length') out.offset2 = v.offset2 }
    if (v.start_type !== 'Profile plane') { out.start_type = v.start_type; out.start_offset = v.start_offset }
    return out
  }
  const ok = async () => {
    const p = props()
    if (existing) {
      const was = (k: string) => (k === 'type1' ? extrudeType(existing) : k === 'side_type' ? sideType(existing)
        : k === 'length' || k === 'length2' ? num(existing[k], kind === 'pad' ? 10 : 5) : k.endsWith('offset') || k === 'offset2' ? num(existing[k], 0) : existing[k] ?? DEFAULTS[k])
      const changed = Object.fromEntries(Object.entries(p).filter(([k, x]) => JSON.stringify(x) !== JSON.stringify(was(k))))
      closeTask()
      if (Object.keys(changed).length) await applyOps(part, [{ op: 'set', name, props: changed }], { name: `Edit ${name}` })
      return
    }
    const newName = nextName(doc, label)
    const ops: FeatureOp[] = [{ op: 'add', feature: { name: newName, type: kind === 'pad' ? PAD : POCKET, ...p }, after: sketch.name }]
    closeTask()
    const done = await applyOps(part, ops, { name: `Make ${label}` })
    if (done) setState({ featSel: [refOf(part, newName)], selected: [] })
  }
  const lengthBox = (key: 'length' | 'length2' | 'offset' | 'offset2' | 'start_offset', lbl: string) => (
    <label className="tfield"><span>{lbl}</span><QuantityBox value={v[key]} dims={LENGTH} min={key.startsWith('length') ? 0 : undefined} onChange={(x) => set({ [key]: x })} /></label>)
  const side = (t: string, which: 1 | 2) => (
    <>
      {t === 'Length' && lengthBox(which === 1 ? 'length' : 'length2', 'Length')}
      {((t === 'UpToLast' && kind === 'pad') || t === 'UpToFirst' || t === 'UpToFace') && lengthBox(which === 1 ? 'offset' : 'offset2', 'Offset to face')}
      {(t === 'Length' || (t === 'ThroughAll' && kind === 'pocket')) && <label className="tfield" title="n/a: feature.py does not taper yet"><span>Taper angle</span><QuantityBox value={0} dims={ANGLE} disabled onChange={() => {}} /></label>}
      {t === 'UpToFace' && <div className="tfield"><input readOnly placeholder="No face selected" title="Name the face in the code: up_to_face=(&quot;Pad&quot;, &quot;Face6&quot;)" /><button className="qbtn" disabled>Select Face</button></div>}
      {t === 'UpToShape' && <div className="tfield"><input readOnly placeholder="No shape selected" /><button className="qbtn" disabled>Select Shape</button></div>}
    </>
  )
  return (
    <div className="tasks">
      <OkCancel onOk={() => void ok()} onCancel={closeTask} />
      <TaskHead title={`${label} Parameters`} icon={kind === 'pad' ? 'pd-pad' : 'pd-pocket'}>
        <div className="pd-form">
          <label className="tfield"><span>Start</span><QComboBox value={v.start_type} onChange={(e) => set({ start_type: e.target.value })}>
            {STARTS.map((x) => <option key={x} value={x} disabled={x === 'Reference'}>{x}</option>)}</QComboBox></label>
          {v.start_type !== 'Profile plane' && lengthBox('start_offset', 'Offset')}
          <label className="tfield"><span>Direction</span><QComboBox value={v.side_type} onChange={(e) => set({ side_type: e.target.value })}>
            {sides.map(([k, t]) => <option key={k} value={k}>{t}</option>)}</QComboBox></label>
          {v.side_type === 'Two sides' && <div className="pd-side">Side 1</div>}
          <label className="tfield"><span>Type</span><QComboBox value={v.type} onChange={(e) => {
            const t = e.target.value
            // onModeChanged: back to Dimension with no length at all takes 5 mm
            set({ type: t, ...(t === 'Length' && v.length + (v.side_type === 'Two sides' ? v.length2 : 0) < 1e-7 ? { length: 5 } : {}) })
          }}>{types.map(([k, t]) => <option key={k} value={k}>{t}</option>)}</QComboBox></label>
          {side(v.type, 1)}
          {v.side_type === 'Two sides' && <>
            <div className="pd-side">Side 2</div>
            <label className="tfield"><span>Type</span><QComboBox value={v.type2} onChange={(e) => set({ type2: e.target.value })}>
              {types.map(([k, t]) => <option key={k} value={k}>{t}</option>)}</QComboBox></label>
            {side(v.type2, 2)}
          </>}
          <hr className="pd-line" />
          <label className="tcheck"><input type="checkbox" checked={v.reversed} disabled={v.side_type === 'Symmetric' && v.type === 'Length'} onChange={(e) => set({ reversed: e.target.checked })} /> Reversed</label>
          <fieldset className="tgroup"><legend>Direction</legend>
            <label className="tfield"><span>Direction/edge</span><QComboBox value="normal" onChange={() => {}}>
              <option value="normal">Sketch normal</option><option value="select" disabled>Select reference…</option><option value="custom" disabled>Custom direction</option></QComboBox></label>
            <label className="tcheck" title="If unchecked, the length will be measured along the specified direction"><input type="checkbox" checked={v.along_sketch_normal} disabled onChange={(e) => set({ along_sketch_normal: e.target.checked })} /> Length along sketch normal</label>
          </fieldset>
          {kind === 'pocket' && <label className="tfield"><span>Operation</span><QComboBox value="Subtraction" onChange={() => {}}>
            <option>Subtraction</option><option disabled>Common</option></QComboBox></label>}
          <label className="tcheck"><input type="checkbox" checked={update} onChange={(e) => setUpdate(e.target.checked)} /> Recompute on change</label>
        </div>
      </TaskHead>
      <TaskHead title="Preview" icon={kind === 'pad' ? 'pd-pad' : 'pd-pocket'}>
        <label className="tcheck" title="n/a: the result is built when OK writes it; the preview shows the tool"><input type="checkbox" disabled /> Show final result</label>
        <label className="tcheck"><input type="checkbox" checked={overlay} onChange={(e) => setOverlay(e.target.checked)} /> Show preview overlay</label>
      </TaskHead>
    </div>
  )
}

// ── menus and toolbars (PartDesignGui::Workbench::setupMenuBar / setupToolBars) ─────────────
const later = 'not yet: the PartDesign features after Pad and Pocket come later (docs/EDITING_PLAN.md, step 5)'
const soon = (label: string, icon: IconName, cmd: string): Entry => ({ label, icon, cmd, disabled: true, title: later })
const hasDoc = () => !!getState().slug
/** The "&Sketch" menu, entry by entry as the real FreeCAD 26.3 has it. */
export function sketchMenu(): Entry[] {
  const s = getState(), one = s.featSel.length === 1 ? s.features[splitRef(s.featSel[0])[0]]?.features.find((f) => f.name === splitRef(s.featSel[0])[1]) : undefined
  return [
    { label: 'New Sketch', icon: 'pd-new-sketch', cmd: 'PartDesign_NewSketch', disabled: !hasDoc(), onSelect: () => void newSketch() },
    { label: 'Edit Sketch', icon: 'pd-edit-sketch', cmd: 'Sketcher_EditSketch', disabled: one?.type !== SKETCH, onSelect: () => editFeature(s.featSel[0]) },
    { label: 'Attach Sketch', icon: 'pd-map-sketch', cmd: 'Sketcher_MapSketch', disabled: true, title: 'not yet: a sketch\'s support is set when it is made, or with `cad feature set`' },
    { label: 'Reorient Sketch', icon: 'pd-reorient-sketch', cmd: 'Sketcher_ReorientSketch', disabled: true, title: 'not yet: comes with the Sketcher' },
    { label: 'Validate Sketch', icon: 'pd-validate-sketch', cmd: 'Sketcher_ValidateSketch', disabled: true, title: 'not yet: comes with the Sketcher' },
    { label: 'Merge Sketches', icon: 'pd-merge-sketch', cmd: 'Sketcher_MergeSketches', disabled: true, title: 'not yet: comes with the Sketcher' },
    { label: 'Mirror Sketch', icon: 'pd-mirror-sketch', cmd: 'Sketcher_MirrorSketch', disabled: true, title: 'not yet: comes with the Sketcher' },
  ]
}
/** The "&Part Design" menu, entry by entry as the real FreeCAD 26.3 has it (the WizardShaft entry is there when its Python
 *  module is, as it is in the Linux build). */
export function partDesignMenu(): Entry[] {
  const doc = hasDoc()
  const rv = revolveEntries(doc)
  return [
    { label: 'New Body', icon: 'body', cmd: 'PartDesign_Body', onSelect: () => void createBody() },
    'sep',
    soon('Shape Binder', 'pd-shape-binder', 'PartDesign_ShapeBinder'), soon('Sub-Shape Binder', 'pd-subshape-binder', 'PartDesign_SubShapeBinder'), soon('Clone', 'pd-clone', 'PartDesign_Clone'),
    'sep',
    { label: 'Additive Features', sub: [
      { label: 'Pad', icon: 'pd-pad', cmd: 'PartDesign_Pad', disabled: !doc, onSelect: () => void padOrPocket('pad') },
      rv.revolve, soon('Additive Loft', 'pd-add-loft', 'PartDesign_AdditiveLoft'),
      soon('Additive Pipe', 'pd-add-pipe', 'PartDesign_AdditivePipe'), soon('Additive Helix', 'pd-add-helix', 'PartDesign_AdditiveHelix')] },
    { label: 'Additive Primitive', icon: 'pd-add-box', sub: primitiveMenu('Additive') },
    'sep',
    { label: 'Subtractive Features', sub: [
      { label: 'Pocket', icon: 'pd-pocket', cmd: 'PartDesign_Pocket', disabled: !doc, onSelect: () => void padOrPocket('pocket') },
      rv.hole, rv.groove, soon('Subtractive Loft', 'pd-sub-loft', 'PartDesign_SubtractiveLoft'),
      soon('Subtractive Pipe', 'pd-sub-pipe', 'PartDesign_SubtractivePipe'), soon('Subtractive Helix', 'pd-sub-helix', 'PartDesign_SubtractiveHelix')] },
    { label: 'Subtractive Primitive', icon: 'pd-sub-box', sub: primitiveMenu('Subtractive') },
    'sep',
    { label: 'Dress-Up Features', sub: [...dressUpEntries(doc), soon('Defeaturing', 'pd-defeaturing', 'PartDesign_Defeaturing')] },
    'sep',
    { label: 'Transformation Features', sub: transformMenu() },
    'sep',
    soon('Boolean Operation', 'pd-boolean', 'PartDesign_Boolean'),
    'sep',
    { label: 'Inspect Appearance', icon: 'material', cmd: 'Materials_InspectAppearance', disabled: true, title: 'n/a: materials are set in the part\'s source' },
    { label: 'Inspect Material', icon: 'material', cmd: 'Materials_InspectMaterial', disabled: true, title: 'n/a: materials are set in the part\'s source' },
    'sep',
    { label: 'Check Geometry', icon: 'pd-check-geometry', cmd: 'Part_CheckGeometry', disabled: true, title: 'n/a: the checks (Recompute) judge the geometry here' },
    'sep',
    soon('Involute Gear', 'pd-gear', 'PartDesign_InvoluteGear'), soon('Sprocket', 'pd-sprocket', 'PartDesign_Sprocket'),
    'sep',
    soon('Shaft Design Wizard', 'pd-wizard-shaft', 'PartDesign_WizardShaft'),
  ]
}
/** The workbench's four toolbars, button by button (setupToolBars). Groups (Create Datum's sketch commands, the primitives)
 *  show their default command, as a GroupCommand's tool button does. */
const byLabel = (list: Entry[], label: string): Exclude<Entry, 'sep'> => list.find((e): e is Exclude<Entry, 'sep'> => e !== 'sep' && e.label === label)!
export function pdToolbars(): [string, Entry[]][] {
  const doc = hasDoc()
  const m = partDesignMenu(), sk = sketchMenu()
  const sub = (label: string) => (m.find((e) => e !== 'sep' && e.label === label) as Exclude<Entry, 'sep'>).sub!
  const pad = sub('Additive Features'), pocket = sub('Subtractive Features')
  return [
    ['Part Design Helper Features', [byLabel(m, 'New Body'), { ...byLabel(sk, 'New Sketch'), cmd: 'PartDesign_CompSketches' }, byLabel(sk, 'Validate Sketch'),
      byLabel(m, 'Check Geometry'), byLabel(m, 'Sub-Shape Binder'), byLabel(m, 'Clone')]],
    ['Part Design Modeling Features', [...pad, { label: 'Additive Primitive', icon: 'pd-add-box', cmd: 'PartDesign_CompPrimitiveAdditive', disabled: !doc, sub: primitiveMenu('Additive') }, 'sep',
      ...pocket, { label: 'Subtractive Primitive', icon: 'pd-sub-box', cmd: 'PartDesign_CompPrimitiveSubtractive', disabled: !doc, sub: primitiveMenu('Subtractive') }, 'sep',
      soon('Boolean Operation', 'pd-boolean', 'PartDesign_Boolean')]],
    ['Part Design Dress-Up Features', sub('Dress-Up Features')],
    ['Part Design Transformation Features', sub('Transformation Features')],
  ].map(([t, e]) => [t as string, (e as Entry[]).map((x) => (x !== 'sep' && x.cmd === 'PartDesign_Pad' ? { ...x, disabled: !doc } : x))])
}

// ── keys on a Body's rows (Tree.cpp: F2 renames; Std_Delete; Space) ─────────────────────────
/** App.tsx's key handler asks here first: true when a Body's rows were selected and the key was theirs. */
export function featureKey(e: KeyboardEvent): boolean {
  if (partKey(e)) return true   // a Part object's rows (part_wb.tsx)
  const s = getState()
  if (!s.featSel.length) return false
  const t = e.target as HTMLElement | null
  if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return false
  if (e.key === 'F2') return startRename()
  if (e.key === 'Delete' || e.key === 'Backspace') { void deleteFeatures(); return true }
  if (e.key === ' ') { toggleFeatureVisibility(); return true }
  if (e.key === 'Enter' && s.featSel.length === 1) { editFeature(s.featSel[0]); return true }
  return false
}

/** The Sketch and Part Design menus and the workbench's toolbars as plain data (labels, commands, greyed or not, submenus):
 *  what ui/scripts/editcheck.mjs holds to FreeCAD's (cadui.pd() in the page). */
export function pdMenus() {
  const plain = (es: Entry[]): unknown[] => es.map((e) => (e === 'sep' ? { sep: true } : { text: e.label, cmd: e.cmd ?? null, enabled: !e.disabled, ...(e.sub ? { menu: plain(e.sub) } : {}) }))
  return { sketch: plain(sketchMenu()), partDesign: plain(partDesignMenu()), toolbars: pdToolbars().map(([title, es]) => ({ title, buttons: plain(es) })) }
}

void select

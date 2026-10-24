// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Part/Gui/TaskAttacher.cpp: 2013 Jan Rheinländer
//   src/Mod/Part/Gui/AttacherTexts.cpp: 2016 Victor Titov (DeepSOIC) (through attachertexts.ts)
//   src/Mod/Part/Gui/ViewProviderAttachExtension.cpp: 2016 Stefan Tröger
//   src/Mod/Part/Gui/Command.cpp: 2002 Jürgen Riegel (Part_DatumPlane, Part_DatumLine, Part_DatumPoint, Part_CoordinateSystem)
//   src/Mod/PartDesign/Gui/SketchWorkflow.cpp: 2022 Werner Mayer
//   src/Gui/ViewProviderDatum.cpp: 2015 Alexander Golubev (Fat-Zer)
//   src/Gui/ViewProviderPlane.cpp: 2012 Jürgen Riegel; 2015 Alexander Golubev (Fat-Zer)
//   src/Gui/ViewProviderLine.cpp: 2012 Jürgen Riegel; 2015 Alexander Golubev (Fat-Zer); 2026 Joao Matos
//   src/Gui/ViewProviderPoint.cpp: 2024 Ondsel (PL Boyer)
//   src/Gui/ViewProviderCoordinateSystem.cpp: 2015 Stefan Tröger; 2015 Alexander Golubev (Fat-Zer)
//   src/Gui/ViewParams.cpp: 2018 Zheng Lei (realthunder)
//   No copyright line in the file: src/Mod/Part/Gui/TaskAttacher.ui
// Attachment in the app, as FreeCAD does it: the Attachment panel (TaskAttacher) for a sketch and for a datum, with its
// reference buttons, the mode list of the attacher engine (the modes that fit in bold, the ones more references would
// reach greyed with "(add …)"), the offset and Flip sides; the datums Edit > Create > Datums makes (Part's DatumPlane,
// DatumLine, DatumPoint and LCS, PartDesign's own too), drawn as Gui's ViewProviderDatum draws them; and New Sketch on
// a selected face, datum plane or sketch (SketchWorkflow). What the panel shows for the references (their types, the
// suggestion, the placement) is the server's attacher, `cad feature attach` (cad_agent/attacher.py, FreeCAD's
// Attacher.cpp held to freecadcmd); OK writes the attachment through `cad feature apply`, one undo step.
import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { api } from './api'
import { getState, report, setState, subscribe, useStore, type Feature, type FeatureDoc } from './store'
import { closeTask, editSketch, getView, openTask, showPanel } from './actions'
import { cls, TaskBox } from './panels'
import { QuantityBox, LENGTH, ANGLE } from './qsb'
import { messageBox } from './msgbox'
import type { Entry } from './chrome'
import { MODE_TEXTS, REF_TYPE_TEXTS } from './attachertexts'
import { ENGINE_MODES, MODE_REFS, REF_TYPES } from './attachmodes'
import { suggest } from './attachsuggest'
import { attachedOf, DATUM_TYPES, isDatum, placementMatrix, ROLES, type PlacementData } from './attached'
import { applyOps, bodyOfPart, featureVisible, openOrigin, refOf, SKETCH, splitRef, targetBody, setAttachPicker, originPlanes } from './partdesign'

export type Ref = [string, string]                  // AttachmentSupport's (object, sub-element)
type Engine = '3D' | 'Plane' | 'Line' | 'Point'
type Suggestion = { message: string; best: string; all: string[]; reachable: Record<string, string[][]>; hints: string[]; types: string[] }
type Answer = { types?: string[]; suggestion?: Suggestion; mode?: string; placement?: PlacementData | null; error?: string; message?: string
  key?: string; refsKey?: string }

/** readLinks' types for references the page can type itself (the origin's features, a datum, an LCS's features), as the
 *  server's attacher types them; null when one needs the Body's shapes (a face, an edge, a vertex, a whole solid). */
function localTypes(doc: FeatureDoc, refs: Ref[]): string[] | null {
  const ofRole = (role: string) => (role.endsWith('_Plane') ? 'Plane' : role.endsWith('_Axis') ? 'Line' : 'Vertex')
  const out: string[] = []
  for (const [o, s] of refs) {
    if (ROLES.includes(o) && !s) { out.push(ofRole(o) + '|Placement'); continue }
    const f = doc.features.find((x) => x.name === o)
    const d = f && isDatum(f.type) ? DATUM_TYPES[f.type] : null
    if (!d) return null
    if (!s) { out.push({ plane: 'Plane', cs: 'Plane', line: 'Line', point: 'Vertex', lcs: 'Object' }[d.shape] + '|Placement'); continue }
    const role = ROLES.find((r) => s.startsWith(r))
    if (d.shape === 'lcs' && role) { out.push(ofRole(role) + (s.endsWith('.') ? '|Placement' : '')); continue }
    if (d.shape === 'cs' && ['X', 'Y', 'Z'].includes(s)) { out.push('Plane'); continue }
    return null
  }
  return out
}

const msg = (e: unknown) => (e instanceof Error ? e.message : String(e))
const refArg = ([o, s]: Ref) => (s ? `${o}.${s}` : o)
/** makeRefString: "Pad:Face6"; a datum or an origin feature by its name alone. */
export const refText = ([o, s]: Ref) => (ROLES.includes(o) && !s ? `Origin:${o === 'Origin' ? 'Origin001' : o}.` : s ? `${o}:${s}` : o)
const typeText = (t: string) => { const i = REF_TYPES.indexOf(t.split('|')[0]); return i >= 0 ? REF_TYPE_TEXTS[i] : t }
const modeCaption = (engine: Engine, m: string) => MODE_TEXTS[engine]?.[m]?.[0] ?? m
const modeTip = (engine: Engine, m: string) => {
  const t = MODE_TEXTS[engine]?.[m]?.[1] ?? ''
  if (m === 'Deactivated') return t
  return `${t}\n\nReference combinations:\n${(MODE_REFS[engine]?.[m] ?? []).map((c) => c.map(typeText).join(', ')).join('\n')}`
}
const ENGINE_OF_SKETCH: Engine = 'Plane'
/** The engine of a feature: a sketch's Plane, a datum's own. */
export const engineOf = (type: string): Engine => (type === SKETCH ? ENGINE_OF_SKETCH : DATUM_TYPES[type]?.engine ?? 'Plane')

/** The Body's object a click names, as a reference: a tree row ("part/Name"), or the 3D selection of the Body's shape
 *  ("body.Face6", the Tip feature's element). TaskAttacher::addToReference drops the sub-element of a datum or an
 *  origin feature. */
function refOfRow(part: string, row: string): Ref | null {
  const [p, n] = splitRef(row)
  if (p !== part || !n) return null
  if (n === 'Origin001') return ['Origin', '']
  if (n === 'Origin') return null
  const lcs = n.match(/^(.*)\/(X_Axis|Y_Axis|Z_Axis|XY_Plane|XZ_Plane|YZ_Plane|Origin)$/)
  if (lcs) return [lcs[1], lcs[2] + '.']               // an LCS's feature: FreeCAD's "LCS", "XY_Plane001."
  return [n, '']
}
/** The solid the 3D view shows for the Body: the last solid feature up to its Tip (a sketch or a datum as the Tip leaves the
 *  one before it), whose elements a click in the 3D view names. */
function tipFeature(doc: FeatureDoc): string | null {
  const upto = doc.tip ? doc.features.findIndex((f) => f.name === doc.tip) : doc.features.length - 1
  const solids = doc.features.slice(0, upto + 1).filter((f) => f.type !== SKETCH && !isDatum(f.type))
  return solids.length ? solids[solids.length - 1].name : doc.base ? 'BaseFeature' : null
}
/** The 3D selection's sub-elements of this part's Body, as references to its Tip feature. */
function refsOfSelection(part: string): Ref[] {
  const s = getState(), body = bodyOfPart(s, part), doc = s.features[part]
  if (!doc) return []
  const out: Ref[] = []
  const tip = tipFeature(doc)
  for (const r of s.subSel) {
    const i = r.indexOf('.')
    if (body && r.slice(0, i) === body.name && tip) out.push([tip, r.slice(i + 1)])
  }
  if (!s.subSel.length && body && s.selected.includes(body.name) && tip) out.push([tip, ''])
  for (const row of s.featSel) { const ref = refOfRow(part, row); if (ref) out.push(ref) }
  return out
}

// ── the attachment of one object, asked of the server ─────────────────────────────────────────────
async function ask(part: string, refs: Ref[], engine: Engine, opts: { mode?: string | null; prefer?: string | null; offset: number[]; flip: boolean;
  parameter: number; before?: string | null }): Promise<Answer> {
  const slug = getState().slug
  if (!slug) return {}
  const argv = ['feature', 'attach', slug, part, '--engine', engine, ...refs.flatMap((r) => ['--support', refArg(r)])]
  if (opts.mode) argv.push('--mode', opts.mode)
  if (opts.prefer) argv.push('--prefer', opts.prefer)
  argv.push('--offset', JSON.stringify([[opts.offset[0], opts.offset[1], opts.offset[2]], [opts.offset[5], opts.offset[4], opts.offset[3]]]))
  if (opts.flip) argv.push('--reversed')
  if (opts.parameter) argv.push('--parameter', String(opts.parameter))
  if (opts.before) argv.push('--before', opts.before)
  try {
    const r = await api.cad(slug, argv)
    if (r.exit > 2) return { error: String(r.data?.error ?? r.stderr ?? 'the attacher did not answer') }
    return r.data as Answer
  } catch (e) { return { error: msg(e) } }
}

/** What a task for an attachment edits: an existing feature, or one OK will make (a datum; a sketch, which opens). */
export type AttachTarget = { part: string; name: string | null; type: string }
const PANEL_TITLE = 'Attachment'

/** The Attachment panel (TaskAttacher + TaskDlgAttacher): as FreeCAD fills it from the object's properties, keeps the
 *  references, the mode and the offset as the user changes them, previews the result, and on OK writes
 *  AttachmentSupport, MapMode, AttachmentOffset and MapReversed (TaskDlgAttacher::accept). */
export function AttachTask({ target }: { target: AttachTarget }) {
  const s = useStore((x) => x)
  const doc = s.features[target.part]
  const existing = target.name ? doc?.features.find((f) => f.name === target.name) : undefined
  const engine = engineOf(target.type)
  const init = () => {
    let refs = ((existing?.attachment_support as Ref[] | undefined) ?? []).map((r) => [r[0], r[1]] as Ref)
    let first: string | null = null
    if (!existing && doc) {
      // TaskAttacher::handleInitialSelection: what is selected when the panel opens is its first references
      refs = refsOfSelection(target.part).filter(([o]) => o !== target.name).slice(0, 4)
      const lt = localTypes(doc, refs)
      if (lt && refs.length) { const sg = suggest(engine, lt); first = sg.message === 'OK' ? sg.best : null }
    }
    const off = existing?.attachment_offset as unknown
    const o = [0, 0, 0, 0, 0, 0]
    if (Array.isArray(off)) {
      const pos = (Array.isArray(off[0]) ? off[0] : off) as number[], ypr = (Array.isArray(off[0]) ? off[1] : [0, 0, 0]) as number[]
      o[0] = pos[0] ?? 0; o[1] = pos[1] ?? 0; o[2] = pos[2] ?? 0; o[5] = ypr[0] ?? 0; o[4] = ypr[1] ?? 0; o[3] = ypr[2] ?? 0
    }
    const mode = (existing ? (attachedOf(existing)?.map_mode ?? existing.map_mode) : null) as string | null
    return { refs, mode: mode ?? first ?? 'Deactivated', offset: o, flip: existing?.map_reversed === true }
  }
  const [v, setV] = useState(init)
  const [ans, setAns] = useState<Answer>({})
  // only a new object starts with a reference button active; it moves on after the selection's references (autoNext)
  const [active, setActive] = useState<number>(existing ? -1 : Math.min(v.refs.length, 3))
  const autoNext = useRef(!existing)
  const userSelected = useRef(false)
  const seq = useRef(0)
  const before = existing?.name ?? null
  // the server's answer for what the panel holds now (TaskAttacher::updateListOfModes, updatePreview)
  useEffect(() => {
    const n = ++seq.current
    const t = window.setTimeout(async () => {
      const a = await ask(target.part, v.refs, engine, { mode: userSelected.current ? v.mode : null,
        prefer: !userSelected.current && v.mode !== 'Deactivated' ? v.mode : null, offset: v.offset, flip: v.flip, parameter: Number(existing?.map_path_parameter ?? 0), before })
      if (n !== seq.current) return
      setAns({ ...a, key: JSON.stringify(v), refsKey: JSON.stringify(v.refs) })
      if (!userSelected.current && a.mode && a.mode !== v.mode) setV((x) => ({ ...x, mode: a.mode! }))
    }, 60)
    return () => window.clearTimeout(t)
  }, [JSON.stringify(v), target.part])
  // the references come from clicks in the tree and the 3D view (TaskAttacher::onSelectionChanged)
  const add = (refs: Ref[]) => setV((x) => {
    if (active < 0 || !refs.length) return x
    let list = [...x.refs], i = active
    const fresh = refs.filter((r) => !(target.name && r[0] === target.name) && !list.some((q) => q[0] === r[0] && q[1] === r[1]))
    if (!fresh.length) return x                                               // itself, or a duplicate selection
    for (const r of fresh) {
      if (autoNext.current && i > 0 && i === list.length && list[i - 1][0] === r[0] && list[i - 1][1] && !r[1]) i--
      if (i < list.length) list[i] = r; else list.push(r)
      if (autoNext.current) i = i >= 3 ? -1 : i + 1
    }
    list = list.slice(0, 4)
    userSelected.current = false
    window.setTimeout(() => setActive(i), 0)
    // updateListOfModes then getActiveMapMode: the mode chosen before while it still fits, else the best fit
    const lt = doc ? localTypes(doc, list) : null
    if (!lt) return { ...x, refs: list }
    const sg = suggest(engine, lt)
    return { ...x, refs: list, mode: x.mode !== 'Deactivated' && sg.all.includes(x.mode) ? x.mode : sg.message === 'OK' ? sg.best : 'Deactivated' }
  })
  useEffect(() => {
    let last = JSON.stringify([getState().subSel, getState().featSel, getState().selected])
    const unsub = subscribe(() => {
      const st = getState(), key = JSON.stringify([st.subSel, st.featSel, st.selected])
      if (key === last) return
      last = key
      const refs = refsOfSelection(target.part)
      if (refs.length) add([refs[refs.length - 1]])
    })
    setAttachPicker((row) => { const r = refOfRow(target.part, row); if (r) add([r]) })
    const view = getView()
    if (view) {
      // the Origin's planes, larger and labelled while the panel is open (setTemporaryScale, setLabelVisibility)
      view.setHelper('pd-origin', originPlanes(bodyOfPart(getState(), target.part), true))
      view.helperPicker = (name) => {
        if (ROLES.includes(name)) add([[name, '']])
        else { const r = refOfRow(target.part, name); if (r) add([r]) }
      }
      view.rescaleHelpers()
    }
    datumLabels = true; redrawDatums()
    openOrigin(target.part)
    return () => {
      unsub(); setAttachPicker(null); datumLabels = false; redrawDatums()
      const w = getView(); if (w) { w.setHelper('pd-origin', null); w.setHelper('pd-attach-preview', null); w.helperPicker = null }
    }
  }, [target.part, active])
  // the object where the attachment puts it (the panel's updatePreview moves the object itself)
  useEffect(() => {
    const view = getView()
    if (!view) return
    const pl = ans.placement
    view.setHelper('pd-attach-preview', pl ? previewOf(target.type, pl, bodyOfPart(getState(), target.part)) : null)
    view.rescaleHelpers()
  }, [ans.placement, target.type])
  if (!doc) return <div className="tasks"><p className="hint">{target.part}: no Body</p></div>
  // the server's answer when it is for these references, else what the page can tell from the references alone
  const refsKey = JSON.stringify(v.refs), fresh = ans.key === JSON.stringify(v)
  const lt = localTypes(doc, v.refs)
  const sug = (ans.refsKey === refsKey ? ans.suggestion : undefined) ?? (lt && v.refs.length ? suggest(engine, lt) : undefined)
  const types = sug?.types ?? []
  const attached = v.mode !== 'Deactivated' && v.refs.length > 0 && (fresh ? !!ans.placement : !!sug?.all.includes(v.mode))
  const failed = fresh && ans.error && v.refs.length && v.mode !== 'Deactivated'
  // TaskAttacher::updateListOfModes: with references, Deactivated, the modes that fit, then those more references reach
  let modes: { m: string; text: string; on: boolean }[]
  if (v.refs.length && sug) {
    const reach = ENGINE_MODES[engine].filter((m) => sug.reachable[m])
    modes = [{ m: 'Deactivated', text: modeCaption(engine, 'Deactivated'), on: true }, ...sug.all.map((m) => ({ m, text: modeCaption(engine, m), on: true })),
      ...reach.map((m) => { const extra = sug.reachable[m]; return { m, on: false,
        text: extra.length === 1 ? `${modeCaption(engine, m)} (add ${extra[0].map(typeText).join('+')})` : `${modeCaption(engine, m)} (add more references)` } })]
  } else modes = ENGINE_MODES[engine].map((m) => ({ m, text: modeCaption(engine, m), on: true }))
  const bold = userSelected.current || v.mode !== 'Deactivated' ? v.mode : sug?.best
  const nextHint = (sug?.hints?.length ?? 0) > 0
  const button = (i: number) => {
    const enable = !(i > v.refs.length) && !(i === v.refs.length && v.refs.length > 0 && !nextHint)
    const text = active === i ? 'Selecting…' : i < types.length ? typeText(types[i]) : `Reference${i + 1}`
    return <button className={cls('qbtn', active === i && 'on')} disabled={!enable} aria-pressed={active === i}
      onClick={() => { autoNext.current = false; setActive(active === i ? -1 : i); if (active !== i) setState({ selected: [], subSel: [], featSel: [] }) }}>{text}</button>
  }
  const lineOf = (i: number) => (i < v.refs.length ? refText(v.refs[i]) : 'No reference selected')
  const setLine = (i: number, text: string) => {
    if (text.trim()) return
    setV((x) => ({ ...x, refs: x.refs.filter((_, k) => k !== i) }))         // onRefName: an empty line removes it
    userSelected.current = false
  }
  const field = (i: number, label: string, dims: typeof LENGTH) => (
    <label className="tfield" key={label}><span>{label}</span>
      <QuantityBox value={v.offset[i]} dims={dims} disabled={!attached} onChange={(x) => setV((y) => ({ ...y, offset: y.offset.map((o, j) => (j === i ? x : o)) }))} /></label>)
  const cancel = () => closeTask()
  const ok = async () => {
    const props = attachmentProps(v)
    if (target.name) {
      closeTask()
      await applyOps(target.part, [{ op: 'set', name: target.name, props }], { name: 'Edit attachment' })
      return
    }
    if (target.type === SKETCH) {
      if (!v.refs.length || v.mode === 'Deactivated') {
        await messageBox('warning', 'New Sketch', 'Pick a face or a plane in the 3D view or the tree to attach the sketch to.')
        return
      }
      closeTask()
      await newSketchWith(target.part, props, 'New Sketch')
      return
    }
    const t = DATUM_TYPES[target.type]
    const name = nextName(doc, t.base)
    closeTask()
    const done = await applyOps(target.part, [{ op: 'add', feature: { name, type: target.type, ...props } }]   /* appended, as Body::addObject puts a datum */, { name: t.txn })
    if (done) setState({ featSel: [refOf(target.part, name)], selected: [] })
  }
  return (
    <div className="tasks">
      <div className="tbuttons pd-buttons"><button className="qbtn default" onClick={() => void ok()}>OK</button><button className="qbtn" onClick={cancel}>Cancel</button></div>
      <TaskBox title={PANEL_TITLE} icon="pd-attach">
        <p className="pd-attach-msg" style={{ color: failed ? 'red' : attached ? 'green' : undefined }}>
          {failed ? `Attachment mode failed: ${ans.error}` : attached ? `Attached with mode ${modeCaption(engine, v.mode)}` : 'Not attached'}</p>
        {[0, 1, 2, 3].map((i) => (
          <div className="tfield" key={i}>{button(i)}
            <input value={lineOf(i)} onChange={(e) => setLine(i, e.target.value)} readOnly={i >= v.refs.length} /></div>))}
        <div className="tlabel">Attachment Mode</div>
        <div className="pd-modes" role="listbox">
          {modes.map(({ m, text, on }) => (
            <div key={m + text} role="option" aria-selected={v.mode === m && on} title={modeTip(engine, m)}
              className={cls('pd-mode', v.mode === m && on && 'sel', !on && 'off', on && bold === m && 'best')}
              onClick={() => { if (!on) return; userSelected.current = true; setV((x) => ({ ...x, mode: m })) }}>{text}</div>))}
        </div>
        <fieldset className="tgroup" disabled={!attached}><legend>{attached ? 'Attachment Offset (in its local coordinate system):' : 'Attachment Offset (inactive - not attached):'}</legend>
          {field(0, 'In X-direction', LENGTH)}{field(1, 'In Y-direction', LENGTH)}{field(2, 'In Z-direction', LENGTH)}
          {field(3, 'Around X-axis', ANGLE)}{field(4, 'Around Y-axis', ANGLE)}{field(5, 'Around Z-axis', ANGLE)}
        </fieldset>
        <label className="tcheck"><input type="checkbox" checked={v.flip} onChange={(e) => setV((x) => ({ ...x, flip: e.target.checked }))} /> Flip sides</label>
      </TaskBox>
    </div>
  )
}

/** The part file's attachment keywords for what the panel holds. */
function attachmentProps(v: { refs: Ref[]; mode: string; offset: number[]; flip: boolean }) {
  const off = v.offset.some((x) => x !== 0) ? [[v.offset[0], v.offset[1], v.offset[2]], [v.offset[5], v.offset[4], v.offset[3]]] : null
  return { attachment_support: v.refs.map((r) => [r[0], r[1]]), map_mode: v.mode, attachment_offset: off, map_reversed: v.flip }
}
const nextName = (doc: FeatureDoc, base: string) => {
  const names = new Set(doc.features.map((f) => f.name))
  if (!names.has(base)) return base
  for (let i = 1; ; i++) { const n = `${base}${String(i).padStart(3, '0')}`; if (!names.has(n)) return n }
}
const afterTip = (doc: FeatureDoc) => doc.tip ?? doc.features[doc.features.length - 1]?.name ?? null

/** A sketch made with an attachment, then opened in the Sketcher (SketchPreselection::createSketchOnSupport). */
async function newSketchWith(part: string, props: Record<string, unknown>, txn: string) {
  const doc = getState().features[part]
  if (!doc) return
  const name = nextName(doc, 'Sketch')
  const done = await applyOps(part, [{ op: 'add', feature: { name, type: SKETCH, ...props, geometry: [], constraints: [] }, after: afterTip(doc) }], { name: txn })
  if (!done) return
  setState({ featSel: [refOf(part, name)], selected: [], subSel: [] })
  editSketch(part, name)
}

/** PartDesign_NewSketch's fast path (SketchWorkflow: SketchPreselection): a single planar face of the Body, a datum plane
 *  or a plane of the origin selected makes the sketch on it with FlatFace ("Sketch on Face"), a sketch with ObjectXY;
 *  several sub-elements or a face that is not flat say so as FreeCAD does. Returns false when the selection is not one
 *  of those (the attachment panel opens then, with the selection as its first references). */
export async function sketchOnSelection(part: string): Promise<boolean> {
  const s = getState(), doc = s.features[part]
  if (!doc) return false
  const subs = refsOfSelection(part).filter(([, sub]) => sub)
  const faces = subs.filter(([, sub]) => sub.startsWith('Face'))
  if (subs.length > 1 && faces.length) { await messageBox('warning', 'Several sub-elements selected', 'Select a single face as support for a sketch!'); return true }
  if (faces.length === 1) {
    const a = await ask(part, faces, 'Plane', { offset: [0, 0, 0, 0, 0, 0], flip: false, parameter: 0 })
    if (a.message === 'LinkBroken' || a.error && !a.types) { await messageBox('warning', 'No support face selected', 'Select a face as support for a sketch!'); return true }
    if (a.types?.[0] !== 'Plane') { await messageBox('warning', 'No planar support', 'Need a planar face as support for a sketch!'); return true }
    await newSketchWith(part, { attachment_support: [[faces[0][0], faces[0][1]]], map_mode: 'FlatFace' }, 'Sketch on Face')
    return true
  }
  const rows = s.featSel.map((r) => refOfRow(part, r)).filter((r): r is Ref => !!r)
  if (rows.length === 1 && !subs.length) {
    const f = doc.features.find((x) => x.name === rows[0][0])
    const isPlane = (f && (f.type === 'Part::DatumPlane' || f.type === 'PartDesign::Plane')) || rows[0][1].endsWith('_Plane.')
    if (isPlane) { await newSketchWith(part, { attachment_support: [rows[0]], map_mode: 'FlatFace' }, 'Sketch on Face'); return true }
    if (f?.type === SKETCH) { await newSketchWith(part, { attachment_support: [rows[0]], map_mode: 'ObjectXY' }, 'Sketch on Face'); return true }
  }
  return false
}

// ── Edit > Create > Datums (Part_Datums), and the Structure toolbar's ──────────────────────────────────────
/** Part_DatumPlane … Part_CoordinateSystem: a new datum in the active Body, its Attachment panel open with the
 *  selection as its first references (TaskAttacher::handleInitialSelection); OK makes it, in FreeCAD's transaction
 *  ("Add datum plane"), Cancel makes nothing. */
export async function createDatum(type: string) {
  const s = getState()
  if (!s.slug) return
  const part = targetBody()
  if (!part) { await messageBox('warning', 'No active body', 'Activate a Body (double click) or create one first: a datum here belongs to a Body.'); return }
  openTask('attach', part, `new:${type}`)
  showPanel('tasks')
}
/** The Datums group command (Part_Datums) as Edit > Create shows it. */
export function datumsMenu(): Entry {
  const has = !!getState().slug
  return { label: 'Datums', cmd: 'Part_Datums', sub: ['Part::LocalCoordinateSystem', 'Part::DatumPlane', 'Part::DatumLine', 'Part::DatumPoint'].map((t): Entry => {
    const d = DATUM_TYPES[t]
    return { label: d.menu, icon: d.icon as never, cmd: d.cmd, disabled: !has, onSelect: () => void createDatum(t) }
  }) }
}
/** ViewProviderAttachExtension's "Edit Attachment" (and a datum's double-click): the panel on the object. */
export function editAttachment(part: string, name: string) {
  const f = getState().features[part]?.features.find((x) => x.name === name)
  if (!f) return
  openTask('attach', part, name)
  showPanel('tasks')
}
/** The task's target, from State.task (kind 'attach'; other: the feature, or "new:<TypeId>"). */
export function attachTarget(part: string, other: string): AttachTarget {
  if (other.startsWith('new:')) return { part, name: null, type: other.slice(4) }
  const f = getState().features[part]?.features.find((x) => x.name === other)
  return { part, name: other, type: f?.type ?? SKETCH }
}

// ── the datums in the 3D view (Gui::ViewProviderDatum and its planes, lines, points; ViewProviderCoordinateSystem) ──
// Sizes are FreeCAD's View parameters (ViewParams.cpp): DatumPlaneSize 62, DatumLineSize 70, DatumPointSize 2.5, at
// DatumScale 100 %, in an SoShapeScale of LocalCoordinateSystemSize 1 (pixels, whatever the zoom); while the Attachment
// panel is open they are DatumTemporaryScaleFactor (2) larger and the planes show their labels.
const PLANE_SIZE = 62, LINE_SIZE = 70, POINT_SIZE = 2.5, TEMP_SCALE = 2
const DATUM_COLOR = '#3296fa'                     // ViewProviderCoordinateSystem::defaultColor (0x3296faff)
let datumLabels = false
function label(text: string, color: string) {
  const canvas = document.createElement('canvas'); canvas.width = 256; canvas.height = 32
  const ctx = canvas.getContext('2d')!
  ctx.font = 'bold 20px sans-serif'; ctx.fillStyle = color; ctx.textAlign = 'right'; ctx.fillText(text, 252, 24)
  return new THREE.Mesh(new THREE.PlaneGeometry(40, 5), new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(canvas), transparent: true, side: THREE.DoubleSide, depthWrite: false }))
}
/** ViewProviderPlane: a quad (±size for a plane with no role, 8 … size in the first quadrant for an origin's), its edge
 *  and its face 0.85 transparent, the label at the corner's half. */
function planeObject(color: string, role: boolean, text: string | null, pick: string | null) {
  const g = new THREE.Group()
  const lo = role ? 8 : -PLANE_SIZE, hi = PLANE_SIZE
  const pts = [new THREE.Vector2(hi, hi), new THREE.Vector2(hi, role ? 8 : -hi), new THREE.Vector2(lo, lo), new THREE.Vector2(role ? 8 : -hi, hi)]
  const shape = new THREE.Shape(pts)
  const face = new THREE.Mesh(new THREE.ShapeGeometry(shape), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.15, side: THREE.DoubleSide, depthWrite: false }))
  const edge = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(pts.map((p) => new THREE.Vector3(p.x, p.y, 0))), new THREE.LineBasicMaterial({ color }))
  if (pick) { face.userData.pickName = pick; edge.userData.pickName = pick }
  g.add(face, edge)
  if (text) { const l = label(text, color); l.position.set(hi / 2 - 2 - 20, hi / 2 - 6, 0.01); g.add(l) }
  return g
}
/** ViewProviderLine: 0 … 2·size along its base direction (Z for a datum line), 0.2 … size for an origin's axis. */
function lineObject(color: string, dir: THREE.Vector3, role: boolean, pick: string | null) {
  const a = dir.clone().multiplyScalar(role ? 0.2 * LINE_SIZE : 0), b = dir.clone().multiplyScalar(role ? LINE_SIZE : 2 * LINE_SIZE)
  const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints([a, b]), new THREE.LineBasicMaterial({ color, linewidth: 2 }))
  if (pick) line.userData.pickName = pick
  return line
}
function pointObject(color: string, pick: string | null) {
  const m = new THREE.Mesh(new THREE.SphereGeometry(POINT_SIZE, 12, 8), new THREE.MeshBasicMaterial({ color }))
  if (pick) m.userData.pickName = pick
  return m
}
/** One datum, in its own frame, in an SoShapeScale. */
function datumObject(type: string, name: string, pick: string | null, labels: boolean): THREE.Object3D {
  const d = DATUM_TYPES[type]
  const scaled = new THREE.Group()
  scaled.userData.shapeScale = labels ? TEMP_SCALE : 1
  const ac = getState().axisColors
  if (d.shape === 'plane' || d.shape === 'cs') scaled.add(planeObject(DATUM_COLOR, false, labels ? name : null, pick))
  else if (d.shape === 'line') scaled.add(lineObject(DATUM_COLOR, new THREE.Vector3(0, 0, 1), false, pick))
  else if (d.shape === 'point') scaled.add(pointObject(DATUM_COLOR, pick))
  else {
    // an LCS: its origin's features (LocalCoordinateSystem::getSetupData), each pickable as the LCS's feature
    const sub = (role: string) => (pick ? `${pick}/${role}` : null)
    const axes: [string, THREE.Vector3, string][] = [['X_Axis', new THREE.Vector3(1, 0, 0), ac.x], ['Y_Axis', new THREE.Vector3(0, 1, 0), ac.y], ['Z_Axis', new THREE.Vector3(0, 0, 1), ac.z]]
    for (const [role, dir, color] of axes) scaled.add(lineObject(color, dir, true, sub(role)))
    const planes: [string, THREE.Matrix4, string, string][] = [
      ['XY_Plane', new THREE.Matrix4(), ac.z, 'XY'],
      ['XZ_Plane', new THREE.Matrix4().makeRotationX(Math.PI / 2), ac.y, 'XZ'],
      ['YZ_Plane', new THREE.Matrix4().makeBasis(new THREE.Vector3(0, 1, 0), new THREE.Vector3(0, 0, 1), new THREE.Vector3(1, 0, 0)), ac.x, 'YZ']]
    for (const [role, m, color, text] of planes) { const p = planeObject(color, true, labels ? text : null, sub(role)); p.applyMatrix4(m); scaled.add(p) }
    scaled.add(pointObject(DATUM_COLOR, sub('Origin')))
  }
  return scaled
}
function partMatrix(body: ReturnType<typeof bodyOfPart>) { const m = new THREE.Matrix4(); if (body?.matrix?.length === 16) m.fromArray(body.matrix).transpose(); return m }
function placed(obj: THREE.Object3D, pl: PlacementData, body: ReturnType<typeof bodyOfPart>) {
  const g = new THREE.Group()
  g.add(obj)
  g.applyMatrix4(partMatrix(body).multiply(placementMatrix(pl)))
  return g
}
/** What the panel previews: the datum where it would go, or the sketch's plane (ViewProvider2DObject's ShowPlane). */
function previewOf(type: string, pl: PlacementData, body: ReturnType<typeof bodyOfPart>) {
  if (isDatum(type)) return placed(datumObject(type, '', null, true), pl, body)
  const g = new THREE.Group()
  g.userData.shapeScale = TEMP_SCALE
  g.add(planeObject('#ffaa00', false, null, null))
  return placed(g, pl, body)
}

let drawnKey = ''
function redrawDatums() { drawnKey = ''; drawDatums() }
/** Every Body's datums that are shown, where the Body attached them. */
function drawDatums() {
  const s = getState(), v = getView()
  if (!v) return
  const items: [string, string, Feature, PlacementData][] = []
  for (const [part, doc] of Object.entries(s.features)) for (const f of doc.features) {
    const pl = attachedOf(f)?.placement
    if (isDatum(f.type) && pl && featureVisible(s, part, f)) items.push([part, f.name, f, pl])
  }
  const key = JSON.stringify([items.map(([p, n, f, pl]) => [p, n, f.type, pl, bodyOfPart(s, p)?.matrix]), datumLabels, s.axisColors])
  if (key === drawnKey) return
  drawnKey = key
  const g = new THREE.Group()
  for (const [part, name, f, pl] of items) g.add(placed(datumObject(f.type, name, refOf(part, name), datumLabels), pl, bodyOfPart(s, part)))
  v.setHelper('pd-datums', g.children.length ? g : null)
  v.rescaleHelpers()
}
subscribe(drawDatums)

/** The property view's Attachment group, for a sketch and a datum (AttachExtension's properties, FreeCAD's names). */
export function attachmentRows(f: Feature): [string, string][] {
  const sup = (f.attachment_support as Ref[] | undefined) ?? []
  const pl = attachedOf(f)
  const engine = engineOf(f.type)
  const off = f.attachment_offset as unknown
  let offText = '[(0.00 0.00 1.00); 0.00°; (0.00 mm  0.00 mm  0.00 mm)]'
  if (Array.isArray(off)) {
    const pos = (Array.isArray(off[0]) ? off[0] : off) as number[], ypr = (Array.isArray(off[0]) ? off[1] : [0, 0, 0]) as number[]
    const q = new THREE.Quaternion().setFromEuler(new THREE.Euler(THREE.MathUtils.degToRad(ypr[2] ?? 0), THREE.MathUtils.degToRad(ypr[1] ?? 0), THREE.MathUtils.degToRad(ypr[0] ?? 0), 'ZYX'))
    const ang = 2 * Math.acos(Math.min(1, Math.abs(q.w))), sn = Math.sqrt(1 - q.w * q.w) || 1, sgn = q.w < 0 ? -1 : 1
    const axis = ang < 1e-12 ? [0, 0, 1] : [sgn * q.x / sn, sgn * q.y / sn, sgn * q.z / sn]
    offText = `[(${axis.map((x) => x.toFixed(2)).join(' ')}); ${THREE.MathUtils.radToDeg(ang).toFixed(2)}°; (${pos.map((x) => `${Number(x ?? 0).toFixed(2)} mm`).join('  ')})]`
  }
  const supText = sup.map(([o, s]) => (ROLES.includes(o) ? `Origin [${o}.]` : s ? `${o} [${s}]` : o)).join(', ')
  return [['Attacher Engine', `Engine ${engine}`], ['Attachment Offset', offText], ['Attachment Support', supText],
    ['Map Mode', String(pl?.map_mode ?? f.map_mode ?? (sup.length ? 'FlatFace' : 'Deactivated'))],
    ['Map Path Parameter', Number(f.map_path_parameter ?? 0).toFixed(2)], ['Map Reversed', f.map_reversed ? 'true' : 'false']]
}

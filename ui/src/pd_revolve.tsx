// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/PartDesign/Gui/Command.cpp: 2008 Jürgen Riegel
//   src/Mod/PartDesign/Gui/TaskRevolutionParameters.cpp: 2011 Juergen Riegel
//   src/Mod/PartDesign/Gui/TaskHoleParameters.cpp: 2011 Juergen Riegel
//   src/Mod/PartDesign/App/FeatureHole.cpp: 2011 Juergen Riegel
//   No copyright line in the file: src/Mod/PartDesign/Gui/TaskRevolutionParameters.ui, src/Mod/PartDesign/Gui/TaskHoleParameters.ui
// PartDesign Revolution, Groove and Hole for parts whose shape is a FEATURES list (cad_agent/feature_revolve.py and
// feature_hole.py): PartDesign_Revolution, PartDesign_Groove and PartDesign_Hole as Command.cpp runs them, their task
// panels (TaskRevolutionParameters.ui, TaskHoleParameters.ui, as their .cpp lay them out), the preview overlay, and their
// properties in the property view. Every edit is `cad feature` on the server, one undo step, as Pad's and Pocket's are.
// What follows from what in a Hole (its diameter from the thread, the counterbore from the screw norm) is FreeCAD's
// Hole::onChanged ported in feature_hole.py: the panel asks the server (`cad feature resolve`), so there is one port.
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import * as THREE from 'three'
import { api, type FeatureOp } from './api'
import { getState, setState, useStore, type Feature, type FeatureDoc } from './store'
import { closeTask, getView, showPanel } from './actions'
import { cls, EditRow, Group, Row, TaskBox, propPad } from './panels'
import { QuantityBox, LENGTH, ANGLE } from './qsb'
import { QComboBox } from './combo'
import { messageBox } from './msgbox'
import * as quantity from './quantity'
import type { Entry } from './chrome'
import { OperationRow, StartReferenceRow, startRefProp, type StartRef } from './pd_kernel'
import { applyOps, bodyOfPart, curveOf, isSolid, numberOf, profileLoops, refOf, sketchMatrix, splitRef, targetBody, SKETCH } from './partdesign'
import { axisRefText, refText as pickText, useOriginShown, useRefPick, type Ref } from './pd_pick'

export const REVOLUTION = 'PartDesign::Revolution', GROOVE = 'PartDesign::Groove', HOLE = 'PartDesign::Hole'
export const REVOLVE_KINDS: Record<string, string> = { [REVOLUTION]: 'Revolution', [GROOVE]: 'Groove', [HOLE]: 'Hole' }
export const REVOLVE_ICONS = { [REVOLUTION]: 'pd-revolution', [GROOVE]: 'pd-groove', [HOLE]: 'pd-hole' } as const
type Kind = 'revolution' | 'groove' | 'hole'
const TYPE_OF: Record<Kind, string> = { revolution: REVOLUTION, groove: GROOVE, hole: HOLE }
const LABEL: Record<Kind, string> = { revolution: 'Revolution', groove: 'Groove', hole: 'Hole' }
const NO_BODY = 'In order to use PartDesign you need an active Body object in the document. Please make one active (double click) '
  + 'or create one.\n\nIf you have a legacy document with PartDesign objects without Body, use the migrate function in PartDesign '
  + 'to put them into a Body.'
const msg = (e: unknown) => (e instanceof Error ? e.message : String(e))
const usedBy = (doc: FeatureDoc) => new Set(doc.features.filter((f) => f.type !== SKETCH && typeof f.profile === 'string').map((f) => f.profile as string))
const nextName = (doc: FeatureDoc, base: string) => {
  const names = new Set(doc.features.map((f) => f.name))
  if (!names.has(base)) return base
  for (let i = 1; ; i++) { const n = `${base}${String(i).padStart(3, '0')}`; if (!names.has(n)) return n }
}

// ── the commands (Command.cpp: prepareProfileBased, then the worker) ─────────────────────────────────────
/** PartDesign_Revolution, PartDesign_Groove, PartDesign_Hole: a sketch selected, or the Body's one sketch no feature uses,
 *  is the profile; the task panel opens on a new feature (CmdPartDesignRevolution's worker sets its ReferenceAxis to the
 *  sketch's V_Axis, Angle 360 and Reversed as suggestReversed says), which OK makes ("Make Revolution") and Cancel never
 *  writes. A Groove needs a solid to cut, as FreeCAD's check before it says. */
export async function profileCommand(kind: Kind) {
  const s = getState()
  const part = targetBody()
  if (!part) { await messageBox('warning', 'No active body', NO_BODY); return }
  const doc = s.features[part]
  if (kind === 'groove' && !doc.base && !doc.features.some((f) => isSolid(f.type))) {
    await messageBox('warning', 'Cannot use this command as there is no solid to subtract from.',
      'Ensure that the body contains a feature before attempting a subtractive command.')
    return
  }
  const selected = s.featSel.map(splitRef).find(([p, n]) => p === part && doc.features.find((f) => f.name === n)?.type === SKETCH)
  const used = usedBy(doc)
  const free = doc.features.filter((f) => f.type === SKETCH && !used.has(f.name))
  const profile = selected?.[1] ?? (free.length === 1 ? free[0].name : null)
  if (!profile) {
    await messageBox('warning', 'No sketch to use', free.length ? 'Please select a sketch or a face, and then the command.' : 'Please create a sketch or 2D object first.')
    return
  }
  setState({ task: { kind, body: part, other: profile } })
  showPanel('tasks')
}

/** The Part Design menu's and toolbar's entries for the three (labels, icons and commands as FreeCAD's). */
export function revolveEntries(doc: boolean): Record<'revolve' | 'groove' | 'hole', Entry> {
  return {
    revolve: { label: 'Revolve', icon: 'pd-revolution', cmd: 'PartDesign_Revolution', disabled: !doc, onSelect: () => void profileCommand('revolution') },
    groove: { label: 'Groove', icon: 'pd-groove', cmd: 'PartDesign_Groove', disabled: !doc, onSelect: () => void profileCommand('groove') },
    hole: { label: 'Hole', icon: 'pd-hole', cmd: 'PartDesign_Hole', disabled: !doc, onSelect: () => void profileCommand('hole') },
  }
}

/** Std_Edit / a double-click: the feature's panel ("Edit Revolution"). True when it is one of the three. */
export function editRevolveFeature(part: string, f: Feature): boolean {
  const kind = f.type === REVOLUTION ? 'revolution' : f.type === GROOVE ? 'groove' : f.type === HOLE ? 'hole' : null
  if (!kind) return false
  setState({ task: { kind, body: part, other: f.name, edit: true } })
  showPanel('tasks')
  return true
}

/** `cad feature resolve`: the feature's every property as FreeCAD's would hold it, from the ones chosen. */
async function resolve(part: string, feature: Record<string, unknown>, throughAll?: number | null): Promise<Feature | null> {
  const slug = getState().slug
  if (!slug) return null
  const argv = ['feature', 'resolve', slug, part, '--feature', JSON.stringify(feature), ...(throughAll ? ['--through-all', String(throughAll)] : [])]
  try {
    const r = await api.cad(slug, argv)
    return r.exit === 0 && r.data?.feature ? (r.data.feature as Feature) : null
  } catch (e) { void msg(e); return null }
}

/** ProfileBased::getThroughAllLength from what the view draws: 2.02 x the diagonal of the Body's box. */
function throughAllOf(): number | null {
  const box = getView()?.modelBox()
  if (!box || box.isEmpty()) return null
  return 2.02 * box.min.distanceTo(box.max)
}

// ── shared bits of the panels ───────────────────────────────────────────────────────────────────────────
function OkCancel({ onOk, onCancel }: { onOk(): void; onCancel(): void }) {
  return <div className="tbuttons pd-buttons"><button className="qbtn default" onClick={onOk}>OK</button><button className="qbtn" onClick={onCancel}>Cancel</button></div>
}
function Field({ label, children, hidden, title }: { label: string; children: ReactNode; hidden?: boolean; title?: string }) {
  if (hidden) return null
  return <label className="tfield" title={title}><span>{label}</span>{children}</label>
}
function Check({ label, checked, onChange, disabled, title, hidden }: { label: string; checked: boolean; onChange(v: boolean): void; disabled?: boolean; title?: string; hidden?: boolean }) {
  if (hidden) return null
  return <label className="tcheck" title={title}><input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} /> {label}</label>
}
function Combo({ value, items, onChange, disabled, qf }: { value: string; items: [string, string][]; onChange(v: string): void; disabled?: boolean | ((v: string) => boolean); qf?: string }) {
  return <QComboBox data-qf={qf} value={value} disabled={disabled === true} onChange={(e) => onChange(e.target.value)}>
    {items.map(([k, t]) => <option key={k} value={k} disabled={typeof disabled === 'function' && disabled(k)}>{t}</option>)}</QComboBox>
}
const STARTS: [string, string][] = [['Profile plane', 'Profile plane'], ['Offset', 'Offset'], ['Reference', 'Reference']]
const SIDES: [string, string][] = [['One side', 'One sided'], ['Two sides', 'Two sided'], ['Symmetric', 'Symmetric']]

// ── Revolution and Groove ───────────────────────────────────────────────────────────────────────────────
/** The axis combo (TaskRevolutionParameters::fillAxisCombo): the sketch's V and H axes, its construction lines, the Body's
 *  X, Y and Z axes, "Select reference…" (greyed: an edge is named in the code), and the current link when it is none of
 *  those. Each item's value is the reference_axis it stands for. */
function axisItems(sketch: Feature | undefined, current: unknown, doc?: FeatureDoc, picked: unknown[] = []): [string, string][] {
  const items: [string, string][] = []
  if (sketch) {
    items.push([JSON.stringify([sketch.name, 'V_Axis']), 'Vertical sketch axis'], [JSON.stringify([sketch.name, 'H_Axis']), 'Horizontal sketch axis'])
    let n = 0
    for (const g of sketch.geometry ?? []) {
      const c = curveOf(g)
      if (c?.kind === 'line' && c.cons) { items.push([JSON.stringify([sketch.name, `Axis${n}`]), `Construction line ${n + 1}`]); n++ }
    }
  }
  items.push([JSON.stringify('X_Axis'), 'Base X-axis'], [JSON.stringify('Y_Axis'), 'Base Y-axis'], [JSON.stringify('Z_Axis'), 'Base Z-axis'])
  // "Select reference…", then each link picked or set (addAxisToCombo appends them after it, as FreeCAD's list grows)
  items.push(['select', 'Select reference…'])
  for (const r of [...picked, current]) {
    const k = JSON.stringify(r)
    if (r != null && !items.some(([x]) => x === k)) items.push([k, axisRefText(doc, r as Ref)])
  }
  return items
}

/** An axis in the sketch's own plane coordinates (for the preview), or null when it is not a line there. */
function axisInSketch(axis: unknown, sketch: Feature, docFeatures: Feature[]): { p: THREE.Vector3; d: THREE.Vector3 } | null {
  const m = sketchMatrix(sketch), inv = m.clone().invert()
  if (typeof axis === 'string') {
    const d = { X_Axis: [1, 0, 0], Y_Axis: [0, 1, 0], Z_Axis: [0, 0, 1] }[axis]
    if (!d) return null
    return { p: new THREE.Vector3().applyMatrix4(inv), d: new THREE.Vector3(...d).transformDirection(inv) }
  }
  if (!Array.isArray(axis)) return null
  const [obj, sub] = axis as [string, string]
  const sk = docFeatures.find((f) => f.name === obj && f.type === SKETCH)
  if (obj === sketch.name) {
    if (sub === 'V_Axis') return { p: new THREE.Vector3(), d: new THREE.Vector3(0, 1, 0) }
    if (sub === 'H_Axis') return { p: new THREE.Vector3(), d: new THREE.Vector3(1, 0, 0) }
    if (sub === 'N_Axis') return { p: new THREE.Vector3(), d: new THREE.Vector3(0, 0, 1) }
    const m2 = /^Axis(\d+)$/.exec(sub)
    if (m2) {
      const lines = (sketch.geometry ?? []).map(curveOf).filter((c) => c?.kind === 'line' && c.cons)
      const c = lines[Number(m2[1])]
      if (c?.kind === 'line') return { p: new THREE.Vector3(c.a[0], c.a[1], 0), d: new THREE.Vector3(c.b[0] - c.a[0], c.b[1] - c.a[1], 0).normalize() }
    }
  }
  const e = /^Edge(\d+)$/.exec(sub ?? '')
  if (sk && e) {
    const lines = (sk.geometry ?? []).map(curveOf).filter((c) => c && !c.cons && c.kind !== 'point')
    const c = lines[Number(e[1]) - 1]
    if (c?.kind === 'line') {
      const toThis = inv.clone().multiply(sketchMatrix(sk))
      const a = new THREE.Vector3(c.a[0], c.a[1], 0).applyMatrix4(toThis), b = new THREE.Vector3(c.b[0], c.b[1], 0).applyMatrix4(toThis)
      return { p: a, d: b.sub(a).normalize() }
    }
  }
  return null
}

export type RevolveSpec = { kind: 'revolution' | 'groove'; side_type: string; type: string; angle: number; type2: string; angle2: number; reversed: boolean; start_type: string; start_offset: number }
/** The preview overlay (SoPreviewShape's colours, as Pad's): the profile turned about the axis over the angles; an up-to or
 *  through-all type turns a full turn, the model being in the way. */
export function revolvePreview(spec: RevolveSpec, axis: unknown, sketch: Feature, features: Feature[], body: ReturnType<typeof bodyOfPart>): THREE.Object3D | null {
  const loops = profileLoops((sketch.geometry ?? []).map(curveOf).filter((c): c is NonNullable<ReturnType<typeof curveOf>> => !!c))
  const ax = axisInSketch(axis, sketch, features)
  if (!loops.length || !ax) return null
  const turn = (t: string, a: number) => (t === 'Angle' ? THREE.MathUtils.degToRad(a) : 2 * Math.PI)
  let a0: number, a1: number
  if (spec.side_type === 'Symmetric') { const a = turn(spec.type, spec.angle); a0 = -a / 2; a1 = a / 2 }
  else if (spec.side_type === 'Two sides') { a0 = -turn(spec.type2, spec.angle2); a1 = turn(spec.type, spec.angle) }
  else { a0 = 0; a1 = turn(spec.type, spec.angle) }
  const start = spec.start_type === 'Offset' ? THREE.MathUtils.degToRad(spec.start_offset) : 0
  const sign = spec.reversed ? -1 : 1
  if (Math.abs(a1 - a0) < 1e-9) return null
  const steps = Math.max(8, Math.ceil((Math.abs(a1 - a0) / (2 * Math.PI)) * 64))
  const pos: number[] = [], idx: number[] = []
  const rot = (v: THREE.Vector2, a: number) => new THREE.Vector3(v.x, v.y, 0).sub(ax.p).applyAxisAngle(ax.d, sign * (a + start)).add(ax.p)
  for (const loop of loops) {
    const base = pos.length / 3, n = loop.length
    for (let i = 0; i <= steps; i++) for (const v of loop) { const p = rot(v, a0 + ((a1 - a0) * i) / steps); pos.push(p.x, p.y, p.z) }
    for (let i = 0; i < steps; i++) for (let j = 0; j < n; j++) {
      const a = base + i * n + j, b = base + i * n + ((j + 1) % n), c = a + n, d = b + n
      idx.push(a, b, d, a, d, c)
    }
  }
  const geo = new THREE.BufferGeometry()
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3))
  geo.setIndex(idx)
  geo.computeVertexNormals()
  const color = spec.kind === 'revolution' ? new THREE.Color(0, 1, 0.6) : new THREE.Color(1, 0, 0)
  const g = new THREE.Group()
  g.add(new THREE.Mesh(geo, new THREE.MeshPhongMaterial({ color, transparent: true, opacity: 0.2, depthWrite: false, side: THREE.DoubleSide })))
  for (const a of [a0, a1]) for (const loop of loops) {
    g.add(new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(loop.map((v) => rot(v, a))), new THREE.LineBasicMaterial({ color })))
  }
  const toPart = new THREE.Matrix4()
  if (body?.matrix?.length === 16) toPart.fromArray(body.matrix).transpose()
  g.applyMatrix4(toPart.multiply(sketchMatrix(sketch)))
  return g
}

/** TaskRevolutionParameters (TaskRevolutionParameters.ui as setupDialog, updateWholeUI and updateSideUI lay it out):
 *  Start and its Offset, Direction (One sided, Two sided, Symmetric), Axis, then per side Type and Angle (or Select Face and
 *  the face's name), Project selected axis to profile plane, Reversed (greyed for a symmetric angle), a Groove's Operation,
 *  Recompute on change; then Preview. OK writes "Make Revolution" or, for one double-clicked, "Edit Revolution". */
export function RevolveTask({ kind, part, name, edit }: { kind: 'revolution' | 'groove'; part: string; name: string; edit: boolean }) {
  const s = useStore((x) => x)
  const doc = s.features[part]
  const existing = edit ? doc?.features.find((f) => f.name === name) : undefined
  const profileName = existing ? String(existing.profile ?? '') : name
  const sketch = doc?.features.find((f) => f.name === profileName)
  const num = (v: unknown, d: number) => numberOf(v, doc?.params ?? {}) ?? d
  const initial = useMemo(() => ({
    reference_axis: (existing?.reference_axis ?? [profileName, 'V_Axis']) as unknown,
    start_type: String(existing?.start_type ?? 'Profile plane'), start_offset: num(existing?.start_offset, 0),
    side_type: String(existing?.side_type ?? 'One side'), type: String(existing?.type1 ?? 'Angle'), angle: num(existing?.angle, 360),
    type2: String(existing?.type2 ?? 'Angle'), angle2: num(existing?.angle2, 0), reversed: existing?.reversed === true,
    project_axis: existing?.project_axis === true,
    up_to_face: (existing?.up_to_face ?? null) as unknown, up_to_face2: (existing?.up_to_face2 ?? null) as unknown,
    operation: String(existing?.operation ?? 'Subtraction'), start_reference: (existing?.start_reference ?? null) as StartRef,
  }), [part, name, edit])
  const [v, setV] = useState(initial)
  // TaskRevolutionParameters::setSelectionMode: the axis (EDGE | PLANAR | CIRCLE) or a side's face (FACE), picked in the 3D
  // view or the tree through pd_pick.tsx's gate; the Origin's axes shown while the panel is open
  const [sel, setSel] = useState<{ mode: 'axis' } | { mode: 'face'; side: 1 | 2 } | null>(null)
  const [picked, setPicked] = useState<unknown[]>([])            // the axes picked this session (the combo keeps them)
  useRefPick(sel !== null, { part, feature: existing?.name ?? null, allow: sel?.mode === 'axis' ? { edge: true, planar: true, circle: true } : { face: true },
    onPick: (p) => {
      if (sel?.mode === 'axis') { set({ reference_axis: p.ref }); setPicked((x) => (x.some((r) => JSON.stringify(r) === JSON.stringify(p.ref)) ? x : [...x, p.ref])) }
      else if (sel?.mode === 'face') set(sel.side === 1 ? { up_to_face: p.ref } : { up_to_face2: p.ref })
      setSel(null)
    } })
  useOriginShown(part, 'axes')
  const set = (patch: Partial<typeof v>) => setV((x) => {
    // setSelectionMode(Face) when a side turns to Up to face with no face yet (updateUI's focus), None when it turns away
    for (const [k, side] of [['type', 1], ['type2', 2]] as const) {
      if (!(k in patch) || patch[k] === x[k]) continue
      if (patch[k] === 'UpToFace' && !(side === 1 ? x.up_to_face : x.up_to_face2)) setSel({ mode: 'face', side })
      else if (sel?.mode === 'face' && sel.side === side) setSel(null)
    }
    return { ...x, ...patch }
  })
  const [update, setUpdate] = useState(true)
  const [overlay, setOverlay] = useState(true)
  // a new one: what CmdPartDesignRevolution / CmdPartDesignGroove set (the V axis, 360°, suggestReversed)
  useEffect(() => {
    if (edit || !sketch) return
    void resolve(part, { name: nextName(doc, LABEL[kind]), type: TYPE_OF[kind], profile: sketch.name }).then((r) => {
      if (r) set({ reference_axis: r.reference_axis, angle: Number(r.angle ?? 360), reversed: r.reversed === true })
    })
  }, [part, name, edit])
  const body = bodyOfPart(s, part)
  const drawn = useRef(false)
  useEffect(() => {
    if (!update && drawn.current) return
    drawn.current = true
    getView()?.setHelper('pd-preview', overlay && sketch ? revolvePreview({ kind, ...v }, v.reference_axis, sketch, doc?.features ?? [], body) : null)
  }, [v, overlay, update, sketch, body])
  useEffect(() => () => { getView()?.setHelper('pd-preview', null) }, [])
  if (!doc || !sketch) return <div className="tasks"><p className="hint">{part}: no sketch {profileName}</p></div>
  const label = LABEL[kind]
  const types: [string, string][] = [['Angle', 'Angle'], kind === 'revolution' ? ['UpToLast', 'To last'] : ['ThroughAll', 'Through all'], ['UpToFirst', 'To first'], ['UpToFace', 'Up to face']]
  const props = (): Record<string, unknown> => {
    const out: Record<string, unknown> = { profile: sketch.name, reference_axis: v.reference_axis, side_type: v.side_type, type1: v.type, angle: v.angle, reversed: v.reversed, project_axis: v.project_axis }
    if (v.type === 'UpToFace') out.up_to_face = v.up_to_face
    if (v.side_type === 'Two sides') { out.type2 = v.type2; out.angle2 = v.angle2; if (v.type2 === 'UpToFace') out.up_to_face2 = v.up_to_face2 }
    if (v.start_type !== 'Profile plane') { out.start_type = v.start_type; out.start_offset = v.start_offset }
    if (v.start_type === 'Reference') out.start_reference = v.start_reference
    if (kind === 'groove') out.operation = v.operation
    return out
  }
  const ok = async () => {
    const p = props()
    if (existing) {
      const was = (k: string) => (k === 'angle' || k === 'angle2' || k === 'start_offset' ? num(existing[k], k === 'angle' ? 360 : 0)
        : k === 'operation' ? existing[k] ?? 'Subtraction' : k === 'start_reference' ? existing[k] ?? null : existing[k])
      const changed = Object.fromEntries(Object.entries(p).filter(([k, x]) => JSON.stringify(x) !== JSON.stringify(was(k))))
      closeTask()
      if (Object.keys(changed).length) await applyOps(part, [{ op: 'set', name, props: changed }], { name: `Edit ${name}` })
      return
    }
    const newName = nextName(doc, label)
    const ops: FeatureOp[] = [{ op: 'add', feature: { name: newName, type: TYPE_OF[kind], ...p }, after: sketch.name }]
    closeTask()
    const done = await applyOps(part, ops, { name: `Make ${label}` })
    if (done) setState({ featSel: [refOf(part, newName)], selected: [] })
  }
  const faceText = (r: unknown) => (Array.isArray(r) ? `${r[0]}:${r[1]}` : typeof r === 'string' ? r : '')
  const parseFace = (t: string): unknown => { const m = /^\s*([A-Za-z_][\w]*)\s*:\s*(Face\d+)\s*$/.exec(t); return m ? [m[1], m[2]] : /_Plane$/.test(t.trim()) ? t.trim() : null }
  const side = (which: 1 | 2) => {
    const t = which === 1 ? v.type : v.type2
    return <>
      {v.side_type === 'Two sides' && <div className="pd-side">{`Side ${which}`}</div>}
      <Field label="Type"><Combo qf={which === 1 ? "changeMode" : "changeMode2"} value={t} items={types} onChange={(x) => set(which === 1 ? { type: x } : { type2: x })} /></Field>
      <Field label="Angle" hidden={t !== 'Angle'}><QuantityBox value={which === 1 ? v.angle : v.angle2} dims={ANGLE} min={-360} max={360} onChange={(x) => set(which === 1 ? { angle: x } : { angle2: x })} /></Field>
      {t === 'UpToFace' && (() => {
        const on = sel?.mode === 'face' && sel.side === which
        return <div className="tfield pd-pickrow">
          <button className={cls('qbtn', on && 'on')} aria-pressed={on} data-qf={which === 1 ? 'buttonFace' : 'buttonFace2'} onClick={() => setSel(on ? null : { mode: 'face', side: which })}>Select Face</button>
          <input readOnly data-qf={which === 1 ? 'lineFaceName' : 'lineFaceName2'} placeholder={on ? 'Face selection active' : 'No face selected'}
            value={pickText(doc, (which === 1 ? v.up_to_face : v.up_to_face2) as Ref | null)} /></div>
      })()}
    </>
  }
  const symmetricAngleLike = v.side_type === 'Symmetric' && (v.type === 'Angle' || (kind === 'groove' && v.type === 'ThroughAll'))
  return (
    <div className="tasks">
      <OkCancel onOk={() => void ok()} onCancel={closeTask} />
      <TaskBox title={`${label} Parameters`} icon={kind === 'revolution' ? 'pd-revolution' : 'pd-groove'}>
        <div className="pd-form">
          <Field label="Start"><Combo value={v.start_type} items={STARTS} onChange={(x) => set({ start_type: x })} /></Field>
          {v.start_type === 'Reference' && <StartReferenceRow part={part} value={v.start_reference} self={existing?.name} onChange={(r) => set({ start_reference: r })} />}
          <Field label="Offset" hidden={v.start_type === 'Profile plane'}><QuantityBox value={v.start_offset} dims={ANGLE} min={-360} max={360} onChange={(x) => set({ start_offset: x })} /></Field>
          <Field label="Direction"><Combo value={v.side_type} items={SIDES} onChange={(x) => set({ side_type: x })} /></Field>
          <Field label="Axis"><Combo qf="axis" value={sel?.mode === 'axis' ? 'select' : JSON.stringify(v.reference_axis)} items={axisItems(sketch, v.reference_axis, doc, picked)}
            onChange={(x) => { if (x === 'select') setSel({ mode: 'axis' }); else { setSel(null); set({ reference_axis: JSON.parse(x) }) } }} /></Field>
          {side(1)}
          {v.side_type === 'Two sides' && side(2)}
          <Check label="Project selected axis to profile plane" checked={v.project_axis} onChange={(x) => set({ project_axis: x })} />
          <Check label="Reversed" checked={v.reversed} disabled={symmetricAngleLike} onChange={(x) => set({ reversed: x })} />
          {kind === 'groove' && <OperationRow value={v.operation} onChange={(x) => set({ operation: x })} />}
          <Check label="Recompute on change" checked={update} onChange={setUpdate} />
        </div>
      </TaskBox>
      <TaskBox title="Preview" icon={kind === 'revolution' ? 'pd-revolution' : 'pd-groove'}>
        <Check label="Show final result" checked={false} disabled onChange={() => {}} title="n/a: the result is built when OK writes it; the preview shows the tool" />
        <Check label="Show preview overlay" checked={overlay} onChange={setOverlay} />
      </TaskBox>
    </div>
  )
}

// ── Hole ────────────────────────────────────────────────────────────────────────────────────────────────
/** TaskHoleParameters' ThreadType items: the shown name of each of Hole::ThreadTypeEnums, and its fit class. */
const THREAD_TYPES: [string, string, 'None' | 'ISO' | 'UTS' | 'Other'][] = [
  ['None', 'None', 'None'], ['ISOMetricProfile', 'ISO metric regular', 'ISO'], ['ISOMetricFineProfile', 'ISO metric fine', 'ISO'],
  ['UNC', 'UTS coarse', 'UTS'], ['UNF', 'UTS fine', 'UTS'], ['UNEF', 'UTS extra fine', 'UTS'], ['NPT', 'ANSI pipes', 'UTS'],
  ['BSP', 'ISO/BSP pipes', 'ISO'], ['BSW', 'BSW whitworth', 'Other'], ['BSF', 'BSF whitworth fine', 'Other'], ['ISOTyre', 'ISO tyre valves', 'Other']]
/** threadTypeChanged's ThreadFit texts by the type's class (the property's own names stay Medium/Fine/Coarse, ...). */
const FIT_TEXT = { None: ['-', '-', '-'], ISO: ['Medium', 'Fine', 'Coarse'], UTS: ['Normal', 'Close', 'Loose'], Other: ['Normal', 'Close', 'Wide'] }
const PROFILE_TYPES: [number, string][] = [[6, 'Circles and arcs'], [7, 'Points, circles and arcs'], [1, 'Points']]
const HOLE_TYPES = ['Clearance / Passthrough', 'Tap drill', 'Threaded']
const BASE_CUTS = ['None', 'Counterbore', 'Countersink', 'Counterdrill']
type HoleRes = Feature & { read_only?: string[]; enums?: Record<string, string[]>; minimal?: Record<string, unknown> }

/** The hole's tool for the preview: the profile Hole::execute revolves (drill, cut, drill point), at each circle's and
 *  arc's centre and each point, as BaseProfileType picks them. */
export function holePreview(r: HoleRes, sketch: Feature, body: ReturnType<typeof bodyOfPart>, throughAll: number | null): THREE.Object3D | null {
  const f = (k: string, d = 0) => (typeof r[k] === 'number' ? (r[k] as number) : d)
  const length = r.depth_type === 'ThroughAll' ? (throughAll ?? f('depth', 25)) : f('depth', 25)
  if (!(length > 0)) return null
  const tapered = r.tapered ? THREE.MathUtils.degToRad(f('tapered_angle', 90)) : Math.PI / 2
  const radius = f('diameter', 6) / 2, bottom = radius - length / Math.tan(tapered)
  const cut = String(r.hole_cut_type ?? 'None')
  const pts: THREE.Vector2[] = [new THREE.Vector2(0, 0)]
  let zc = 0
  if (cut !== 'None') {
    const sink = /sink|10642|2009|7046/.test(cut) || (cut === 'Counterdrill')
    const bore = !sink
    const cr = f('hole_cut_diameter') / 2, depth = sink && cut !== 'Counterdrill' ? 0 : f('hole_cut_depth')
    const half = bore ? Math.PI / 2 : THREE.MathUtils.degToRad(f('hole_cut_countersink_angle', 90) / 2)
    pts.push(new THREE.Vector2(cr, 0))
    if (depth > 0) pts.push(new THREE.Vector2(cr, -depth))
    zc = -depth - (cr - radius) / Math.tan(half)
    pts.push(new THREE.Vector2(radius + (zc + 0) * (radius - bottom) / length, zc))
  } else pts.push(new THREE.Vector2(radius, 0))
  pts.push(new THREE.Vector2(bottom, -length))
  if (r.drill_point === 'Angled') pts.push(new THREE.Vector2(0, -length - radius * Math.tan(THREE.MathUtils.degToRad((180 - f('drill_point_angle', 118)) / 2))))
  else pts.push(new THREE.Vector2(0, -length))
  const lathe = new THREE.LatheGeometry(pts.map((p) => new THREE.Vector2(Math.max(p.x, 0), p.y)), 48)
  lathe.rotateX(Math.PI / 2)                     // LatheGeometry turns about y; the hole's axis is the sketch's normal
  const mask = Number(r.base_profile_type ?? 7)
  const centres: THREE.Vector3[] = []
  for (const g of sketch.geometry ?? []) {
    const c = curveOf(g)
    if (!c || c.cons) continue
    if ((c.kind === 'circle' && mask & 2) || (c.kind === 'arc' && mask & 4)) centres.push(new THREE.Vector3(c.c[0], c.c[1], 0))
    if (c.kind === 'point' && mask & 1) centres.push(new THREE.Vector3(c.p[0], c.p[1], 0))
  }
  if (!centres.length) return null
  const g = new THREE.Group(), color = new THREE.Color(1, 0, 0)
  const start = r.start_type === 'Offset' ? f('start_offset') : 0
  for (const c of centres) {
    const m = new THREE.Mesh(lathe, new THREE.MeshPhongMaterial({ color, transparent: true, opacity: 0.2, depthWrite: false, side: THREE.DoubleSide }))
    m.position.set(c.x, c.y, -start)
    if (r.reversed) m.scale.z = -1
    g.add(m)
    const e = new THREE.LineSegments(new THREE.EdgesGeometry(lathe, 20), new THREE.LineBasicMaterial({ color }))
    e.position.copy(m.position); e.scale.copy(m.scale)
    g.add(e)
  }
  const toPart = new THREE.Matrix4()
  if (body?.matrix?.length === 16) toPart.fromArray(body.matrix).transpose()
  g.applyMatrix4(toPart.multiply(sketchMatrix(sketch)))
  return g
}

/** TaskHoleParameters (TaskHoleParameters.ui, as its constructor and slots show and hide its widgets): Profile and
 *  Placement (Base profile types, Start), then Hole: Standard, Size, Head type, Depth type, Custom head values, Head
 *  diameter and depth, Countersink angle, Depth, Diameter, Drill angle, Include in depth, Tapered, Switch direction,
 *  Hole type, Clearance, the Thread group (Model thread, Class, Direction, Thread depth, Custom clearance), Operation.
 *  The panel keeps what was chosen; every other value comes from the server's port of Hole::onChanged, as the property
 *  would hold it after the choice. OK writes the choices ("Make Hole", "Edit Hole"). */
export function HoleTask({ part, name, edit }: { part: string; name: string; edit: boolean }) {
  const s = useStore((x) => x)
  const doc = s.features[part]
  const existing = edit ? doc?.features.find((f) => f.name === name) : undefined
  const profileName = existing ? String(existing.profile ?? '') : name
  const sketch = doc?.features.find((f) => f.name === profileName)
  const throughAll = useMemo(() => throughAllOf(), [part])
  const [chosen, setChosen] = useState<Record<string, unknown> | null>(edit ? null : {})
  const [startRef, setStartRef] = useState<StartRef>((existing?.start_reference ?? null) as StartRef)
  const [res, setRes] = useState<HoleRes | null>(null)
  const [overlay, setOverlay] = useState(true)
  const [modelThread, setModelThread] = useState(existing?.model_thread === true)
  const seq = useRef(0)
  // an edited hole starts from what its file chose (Hole.minimal of its values)
  useEffect(() => {
    if (!edit || !existing) return
    void resolve(part, { ...existing }, throughAll).then((r) => setChosen((r?.minimal as Record<string, unknown>) ?? {}))
  }, [part, name, edit])
  useEffect(() => {
    if (!chosen || !sketch) return
    const n = ++seq.current
    const t = setTimeout(() => {
      void resolve(part, { name: existing?.name ?? nextName(doc, 'Hole'), type: HOLE, profile: sketch.name, ...chosen }, throughAll).then((r) => { if (r && n === seq.current) setRes(r) })
    }, 120)
    return () => clearTimeout(t)
  }, [chosen])
  const body = bodyOfPart(s, part)
  useEffect(() => { getView()?.setHelper('pd-preview', overlay && res && sketch ? holePreview(res, sketch, body, throughAll) : null) }, [res, overlay, body])
  useEffect(() => () => { getView()?.setHelper('pd-preview', null) }, [])
  if (!doc || !sketch) return <div className="tasks"><p className="hint">{part}: no sketch {profileName}</p></div>
  if (!res || !chosen) return <div className="tasks"><OkCancel onOk={() => {}} onCancel={closeTask} /><TaskBox title="Hole Parameters" icon="pd-hole"><p className="hint">…</p></TaskBox></div>
  const ro = new Set(res.read_only ?? [])
  const choose = (patch: Record<string, unknown>, drop: string[] = []) => setChosen((c) => {
    const out = { ...(c ?? {}), ...patch }
    for (const k of drop) delete out[k]
    return out
  })
  const val = (k: string) => res[k]
  const numv = (k: string) => (typeof res[k] === 'number' ? (res[k] as number) : 0)
  const isNone = val('thread_type') === 'None'
  const threaded = val('threaded') === true
  const holeType = !threaded ? 0 : (val('model_thread') === true || val('cosmetic_thread') === true) ? 2 : 1
  const cutTypes = res.enums?.hole_cut_type ?? BASE_CUTS
  const cut = String(val('hole_cut_type'))
  const cutIndex = cutTypes.indexOf(cut)
  const dynamicSink = cutIndex >= 4 && /ISO (2009|10642|7046)/.test(cut)
  const isSink = cut === 'Countersink' || dynamicSink, isDrill = cut === 'Counterdrill'
  const custom = val('hole_cut_custom_values') === true
  const dimension = val('depth_type') === 'Dimension'
  const angled = val('drill_point') === 'Angled'
  const fitClass = THREAD_TYPES.find(([k]) => k === val('thread_type'))?.[2] ?? 'None'
  const fits = (res.enums?.thread_fit ?? ['Medium', 'Fine', 'Coarse']).map((k, i): [string, string] => [k, FIT_TEXT[fitClass][i] ?? k])
  const q = (k: string, dims: quantity.Quantity['dims'], opts: { disabled?: boolean; min?: number; max?: number } = {}) =>
    <QuantityBox key={`${k}:${numv(k)}`} value={numv(k)} dims={dims} disabled={opts.disabled} min={opts.min} max={opts.max} onChange={(x) => choose({ [k]: x })} />
  const setHoleType = (i: number) => {
    // holeTypeChanged / apply: Threaded, ModelThread and CosmeticThread from the combo and the Model thread box
    if (i === 0) choose({ threaded: false }, ['model_thread', 'cosmetic_thread'])
    else if (i === 1) choose({ threaded: true, model_thread: false, cosmetic_thread: false })
    else choose({ threaded: true, model_thread: modelThread, cosmetic_thread: !modelThread })
  }
  const ok = async () => {
    const minimal = (await resolve(part, { name: existing?.name ?? 'Hole', type: HOLE, profile: sketch.name, ...chosen }, throughAll))?.minimal ?? chosen
    // StartReference is a link, outside Hole::onChanged's state: written when the start is a Reference
    const keep: Record<string, unknown> = { ...(minimal as Record<string, unknown>),
      ...(val('start_type') === 'Reference' ? { start_reference: startRef } : existing?.start_reference != null ? { start_reference: null } : {}) }
    if (existing) {
      const was = (existing as Record<string, unknown>)
      const changed: Record<string, unknown> = {}
      for (const [k, x] of Object.entries(keep)) if (JSON.stringify(x) !== JSON.stringify(was[k])) changed[k] = x
      closeTask()
      if (Object.keys(changed).length) await applyOps(part, [{ op: 'set', name, props: changed }], { name: `Edit ${name}` })
      return
    }
    const newName = nextName(doc, 'Hole')
    closeTask()
    const done = await applyOps(part, [{ op: 'add', feature: { name: newName, type: HOLE, profile: sketch.name, ...keep }, after: sketch.name }], { name: 'Make Hole' })
    if (done) setState({ featSel: [refOf(part, newName)], selected: [] })
  }
  return (
    <div className="tasks">
      <OkCancel onOk={() => void ok()} onCancel={closeTask} />
      <TaskBox title="Hole Parameters" icon="pd-hole">
        <div className="pd-form">
          <fieldset className="tgroup"><legend>Profile and Placement</legend>
            <Field label="Base profile types"><Combo value={String(val('base_profile_type'))} items={PROFILE_TYPES.map(([b, t]) => [String(b), t])} onChange={(x) => choose({ base_profile_type: Number(x) })} /></Field>
            <Field label="Start"><Combo value={String(val('start_type'))} items={STARTS} onChange={(x) => choose({ start_type: x })} /></Field>
            {val('start_type') === 'Reference' && <StartReferenceRow part={part} value={startRef} self={existing?.name} onChange={setStartRef} />}
            <Field label="Offset" hidden={val('start_type') === 'Profile plane'}>{q('start_offset', LENGTH)}</Field>
          </fieldset>
          <fieldset className="tgroup"><legend>Hole</legend>
            <Field label="Standard"><Combo value={String(val('thread_type'))} items={THREAD_TYPES.map(([k, t]): [string, string] => [k, t])}
              onChange={(x) => choose({ thread_type: x }, ['thread_size', 'thread_class', 'thread_fit', ...(BASE_CUTS.includes(cut) ? [] : ['hole_cut_type']), 'hole_cut_depth', 'hole_cut_custom_values'])} /></Field>
            <Field label="Size" hidden={isNone}><Combo value={String(val('thread_size'))} items={(res.enums?.thread_size ?? []).map((t): [string, string] => [t, t])} onChange={(x) => choose({ thread_size: x })} /></Field>
            <Field label="Head type"><Combo value={cut} items={cutTypes.map((t): [string, string] => [t, t])} onChange={(x) => choose({ hole_cut_type: x }, ['hole_cut_depth', 'hole_cut_custom_values', 'hole_cut_diameter', 'hole_cut_countersink_angle'])} /></Field>
            <Field label="Depth type"><Combo value={String(val('depth_type'))} items={[['Dimension', 'Dimension'], ['ThroughAll', 'Through all']]} onChange={(x) => choose({ depth_type: x }, ['depth'])} /></Field>
            <Check label="Custom head values" hidden={cutIndex < 4} checked={custom} disabled={ro.has('hole_cut_custom_values')} onChange={(x) => choose({ hole_cut_custom_values: x })} />
            <Field label="Head diameter" hidden={cut === 'None'}>{q('hole_cut_diameter', LENGTH, { disabled: cutIndex >= 4 ? !custom : ro.has('hole_cut_diameter') })}</Field>
            <Field label="Head depth" hidden={cut === 'None'}>{q('hole_cut_depth', LENGTH, { disabled: cutIndex >= 4 ? !custom : ro.has('hole_cut_depth') })}</Field>
            <Field label="Countersink angle" hidden={!(isSink || isDrill)}>{q('hole_cut_countersink_angle', ANGLE, { disabled: cutIndex >= 4 ? !custom || ro.has('hole_cut_countersink_angle') : ro.has('hole_cut_countersink_angle') })}</Field>
            <Field label="Depth">{q('depth', LENGTH, { disabled: !dimension })}</Field>
            <Field label="Diameter">{q('diameter', LENGTH, { disabled: !isNone })}</Field>
            <Check label="Drill angle" checked={angled && dimension} disabled={!dimension} onChange={(x) => choose({ drill_point: x ? 'Angled' : 'Flat' })} />
            <Field label="">{q('drill_point_angle', ANGLE, { disabled: !(angled && dimension) })}</Field>
            <Check label="Include in depth" checked={val('drill_for_depth') === true} disabled={!(angled && dimension)} onChange={(x) => choose({ drill_for_depth: x })} />
            <Check label="Tapered" checked={val('tapered') === true} onChange={(x) => choose({ tapered: x }, ['tapered_angle'])} />
            <Field label="">{q('tapered_angle', ANGLE, { disabled: val('tapered') !== true })}</Field>
            <Check label="Switch direction" checked={val('reversed') === true} onChange={(x) => choose({ reversed: x })} />
            <Field label="Hole type" hidden={isNone}><Combo value={String(holeType)} items={HOLE_TYPES.map((t, i): [string, string] => [String(i), t])} onChange={(x) => setHoleType(Number(x))} /></Field>
            <Field label="Clearance" hidden={isNone || threaded}><Combo value={String(val('thread_fit'))} items={fits} onChange={(x) => choose({ thread_fit: x })} /></Field>
          </fieldset>
          {threaded && holeType === 2 && <fieldset className="tgroup"><legend>Thread</legend>
            <Check label="Model Thread" checked={modelThread} onChange={(x) => { setModelThread(x); choose({ model_thread: x, cosmetic_thread: !x }) }} />
            <Check label="Update thread view" hidden={!modelThread} checked={false} disabled onChange={() => {}} title="n/a: the thread is built when OK writes it; the preview shows the drill" />
            <Field label="Class"><Combo value={String(val('thread_class'))} items={(res.enums?.thread_class ?? []).map((t): [string, string] => [t, t])} disabled={val('use_custom_thread_clearance') === true} onChange={(x) => choose({ thread_class: x })} /></Field>
            <div className="tfield"><span>Direction</span>
              <label className="tcheck"><input type="radio" checked={val('thread_direction') === 'Right'} onChange={() => choose({ thread_direction: 'Right' })} /> Right hand</label>
              <label className="tcheck"><input type="radio" checked={val('thread_direction') === 'Left'} onChange={() => choose({ thread_direction: 'Left' })} /> Left hand</label></div>
            <Field label="Thread Depth Type"><Combo value={String(val('thread_depth_type'))} items={[['Hole Depth', 'Hole depth'], ['Dimension', 'Dimension'], ['Tapped (DIN76)', 'Tapped (DIN76)']]} onChange={(x) => choose({ thread_depth_type: x }, ['thread_depth'])} /></Field>
            <Field label="Thread depth" hidden={val('thread_depth_type') !== 'Dimension'}>{q('thread_depth', LENGTH)}</Field>
            {modelThread && <>
              <Check label="Custom Clearance" checked={val('use_custom_thread_clearance') === true} onChange={(x) => choose({ use_custom_thread_clearance: x })} />
              <Field label="">{q('custom_thread_clearance', LENGTH, { disabled: val('use_custom_thread_clearance') !== true })}</Field>
            </>}
          </fieldset>}
          <OperationRow value={String(val('operation') ?? 'Subtraction')} onChange={(x) => choose({ operation: x })} />
        </div>
      </TaskBox>
      <TaskBox title="Preview" icon="pd-hole">
        <Check label="Show final result" checked={false} disabled onChange={() => {}} title="n/a: the result is built when OK writes it; the preview shows the tool" />
        <Check label="Show preview overlay" checked={overlay} onChange={setOverlay} />
      </TaskBox>
    </div>
  )
}

// ── the property view ───────────────────────────────────────────────────────────────────────────────────
type PropDef = { key: string; name: string; kind: 'length' | 'angle' | 'bool' | 'enum' | 'link' | 'text' | 'int'; items?: string[]; ro?: (f: Feature) => string | null }
const human = (snake: string) => snake.split('_').map((w) => w[0].toUpperCase() + w.slice(1)).join(' ')
/** FreeCAD's groups for a Revolution, a Groove and a Hole, in the order its property view lists them
 *  (ui/scripts/fcrevolve.json), and why a property is read-only (Revolved::updateProperties, Hole::onChanged). */
function groupsOf(f: Feature): [string, PropDef[]][] {
  const noSel = () => 'a face is picked in the task panel in FreeCAD; FEATURES names it in the code'
  const base: [string, PropDef[]] = ['Base', [{ key: 'name', name: 'Label', kind: 'text' }, { key: 'suppressed', name: 'Suppressed', kind: 'bool', ro: () => 'FEATURES has no suppressed state' }]]
  const start = (unit: 'length' | 'angle'): [string, PropDef[]] => ['Start', [{ key: 'start_type', name: 'Start Type', kind: 'enum', items: ['Profile plane', 'Offset', 'Reference'] },
    { key: 'start_offset', name: 'Start Offset', kind: unit, ro: (x) => (x.start_type === 'Offset' ? null : 'Start Type is Profile plane') },
    { key: 'start_reference', name: 'Start Reference', kind: 'text', ro: (x) => (x.start_type === 'Reference' ? 'picked in the task panel (Pick Reference)' : 'Start Type is not Reference') }]]
  const partDesign = (sub: boolean): [string, PropDef[]] => ['Part Design', [...(sub ? [{ key: 'operation', name: 'Operation', kind: 'enum' as const, items: ['Subtraction', 'Common'] }] : []),
    { key: 'refine', name: 'Refine', kind: 'bool' }, { key: 'fuzzy_tolerance', name: 'Fuzzy Tolerance', kind: 'text', ro: () => 'the booleans run at OCCT\'s own tolerance' }]]
  if (f.type === HOLE) {
    const r = new Set((f.read_only as string[] | undefined) ?? [])
    const why = (k: string) => (x: Feature) => (new Set((x.read_only as string[] | undefined) ?? []).has(k) ? 'read-only in FreeCAD as the other properties are set (Hole::onChanged)' : null)
    const e = (f.enums as Record<string, string[]> | undefined) ?? {}
    const keys: [string, PropDef['kind']][] = [['threaded', 'bool'], ['model_thread', 'bool'], ['cosmetic_thread', 'bool'], ['thread_type', 'enum'], ['thread_size', 'enum'], ['thread_class', 'enum'],
      ['thread_fit', 'enum'], ['diameter', 'length'], ['thread_diameter', 'length'], ['thread_direction', 'enum'], ['hole_cut_type', 'enum'], ['hole_cut_custom_values', 'bool'],
      ['hole_cut_diameter', 'length'], ['hole_cut_depth', 'length'], ['hole_cut_countersink_angle', 'angle'], ['depth_type', 'enum'], ['depth', 'length'], ['drill_point', 'enum'],
      ['drill_point_angle', 'angle'], ['drill_for_depth', 'bool'], ['tapered', 'bool'], ['tapered_angle', 'angle'], ['thread_depth_type', 'enum'], ['thread_depth', 'length'],
      ['use_custom_thread_clearance', 'bool'], ['custom_thread_clearance', 'length'], ['base_profile_type', 'int']]
    void r
    return [base, ['Hole', keys.map(([k, kind]) => ({ key: k, name: human(k), kind, items: e[k], ro: k === 'thread_diameter' ? () => 'ThreadDiameter is set by the thread (read-only in FreeCAD)' : why(k) }))],
      partDesign(true), ['Sketch Based', [{ key: 'profile', name: 'Profile', kind: 'link' }, { key: 'midplane', name: 'Midplane', kind: 'bool', ro: () => 'a Hole has no midplane' },
        { key: 'reversed', name: 'Reversed', kind: 'bool' }, { key: 'allow_multi_face', name: 'Allow Multi Face', kind: 'bool', ro: () => 'a Body\'s features always allow several faces' }]], start('length')]
  }
  const groove = f.type === GROOVE
  const types = groove ? ['Angle', 'ThroughAll', 'UpToFirst', 'UpToFace'] : ['Angle', 'UpToLast', 'UpToFirst', 'UpToFace']
  const two = (x: Feature) => (x.side_type === 'Two sides' ? null : 'Side Type is not Two sides')
  const sym = (x: Feature) => (x.side_type === 'Symmetric' && (x.type1 === 'Angle' || x.type1 === 'ThroughAll') ? 'a symmetric angle has no direction (Revolved::updateProperties)' : null)
  const own: [string, PropDef[]] = [groove ? 'Groove' : 'Revolution', [{ key: 'side_type', name: 'Side Type', kind: 'enum', items: ['One side', 'Two sides', 'Symmetric'] },
    { key: 'project_axis', name: 'Project Axis', kind: 'bool' }, { key: 'reference_axis', name: 'Reference Axis', kind: 'text', ro: () => 'picked in the task panel (Axis)' }]]
  const groups: [string, PropDef[]][] = [base]
  if (groove) groups.push(own, partDesign(true))
  else groups.push(partDesign(false), own)
  groups.push(['Side1', [{ key: 'type1', name: 'Type', kind: 'enum', items: types }, { key: 'angle', name: 'Angle', kind: 'angle', ro: (x) => (x.type1 === 'Angle' ? null : 'Type is not Angle') },
    { key: 'up_to_face', name: 'Up To Face', kind: 'text', ro: noSel }]],
  ['Side2', [{ key: 'type2', name: 'Type2', kind: 'enum', items: types, ro: two }, { key: 'angle2', name: 'Angle2', kind: 'angle', ro: (x) => two(x) ?? (x.type2 === 'Angle' ? null : 'Type2 is not Angle') },
    { key: 'up_to_face2', name: 'Up To Face2', kind: 'text', ro: noSel }]],
  ['Sketch Based', [{ key: 'profile', name: 'Profile', kind: 'link' }, { key: 'midplane', name: 'Midplane', kind: 'bool', ro: () => 'replaced by Side Type (Symmetric), as in FreeCAD at this commit' },
    { key: 'reversed', name: 'Reversed', kind: 'bool', ro: sym }, { key: 'allow_multi_face', name: 'Allow Multi Face', kind: 'bool', ro: () => 'a Body\'s features always allow several faces' }]], start('angle'))
  return groups
}
const DEFAULTS: Record<string, unknown> = { suppressed: false, operation: 'Subtraction', fuzzy_tolerance: 0, midplane: false, allow_multi_face: true, start_reference: null }
const refText = (r: unknown) => (Array.isArray(r) ? `${r[0]} [${r[1]}]` : typeof r === 'string' ? r : '')

/** The Data tab for a Revolution, a Groove or a Hole (editable ones write through `cad feature set`). True when it drew. */
export function RevolveProps({ part, f, set, finishRename }: { part: string; f: Feature; set(props: Record<string, unknown>): void; finishRename(v: string): void }) {
  const s = useStore((x) => x)
  const doc = s.features[part]
  const sketches = doc?.features.filter((x) => x.type === SKETCH).map((x) => x.name) ?? []
  const vars = Object.fromEntries(Object.entries(doc?.params ?? {}).filter(([, v]) => typeof v === 'number').map(([k, v]) => [k, { value: v as number, dims: [0, 0, 0, 0, 0, 0, 0, 0] as quantity.Quantity['dims'] }]))
  const row = (d: PropDef): ReactNode => {
    const v = d.key === 'name' ? f.name : f[d.key] ?? DEFAULTS[d.key]
    const why = d.ro?.(f) ?? null
    const shown = (x: unknown) => (d.kind === 'length' ? quantity.userString({ value: numberOf(x, doc?.params ?? {}) ?? 0, dims: LENGTH }).text + (typeof x === 'string' ? `  (= ${x})` : '')
      : d.kind === 'angle' ? quantity.userString({ value: numberOf(x, doc?.params ?? {}) ?? 0, dims: ANGLE }).text + (typeof x === 'string' ? `  (= ${x})` : '')
        : d.key.startsWith('up_to_face') || d.key === 'reference_axis' ? refText(x) : d.key === 'start_reference' ? startRefProp(x as StartRef) : String(x ?? ''))
    if (why) return <Row key={d.key} k={<span title={`Read-only: ${why}`}>{d.name}</span>} v={shown(v)} />
    if (d.key === 'name') return <EditRow key={d.key} k={d.name} value={f.name} type="str" onCommit={(x) => finishRename(String(x))} />
    if (d.kind === 'bool') return <EditRow key={d.key} k={d.name} value={v === true} type="bool" onCommit={(x) => set({ [d.key]: x })} />
    if (d.kind === 'enum' || d.kind === 'link') {
      const items = d.kind === 'link' ? sketches : d.items ?? [String(v)]
      return <div key={d.key} className="prow" tabIndex={0}><span className="pk" style={propPad(0)}>{d.name}</span>
        <span className="pv"><QComboBox className="qselect-pv" value={String(v)} onChange={(e) => set({ [d.key]: e.target.value })}>{items.map((o) => <option key={o}>{o}</option>)}</QComboBox></span></div>
    }
    if (d.kind === 'length' || d.kind === 'angle') {
      const n = numberOf(v, doc?.params ?? {}) ?? 0
      return <EditRow key={d.key} k={d.name} value={n} type="float" kind={d.kind === 'length' ? 'Length' : 'Angle'} vars={vars} owner={f.name}
        onCommit={(x) => set({ [d.key]: x })} onExpr={(text) => set({ [d.key]: text })} note={typeof v === 'string' ? `= ${v}` : undefined} />
    }
    if (d.kind === 'int') return <EditRow key={d.key} k={d.name} value={Number(v)} type="int" onCommit={(x) => set({ [d.key]: Number(x) })} />
    return <EditRow key={d.key} k={d.name} value={String(v)} type="str" onCommit={(x) => set({ [d.key]: x })} />
  }
  return <>{groupsOf(f).map(([g, defs]) => <Group key={g} title={g}>{defs.map(row)}</Group>)}</>
}

/** For editcheck-like checks in the page: the open Revolution/Groove/Hole panel's fields, as plain data. */
export function panelFields(): unknown[] {
  return [...document.querySelectorAll('.taskview .tbox-body .tfield, .taskview .tbox-body .tcheck, .taskview .tbox-body legend')].map((el) => {
    const label = el.tagName === 'LEGEND' ? el.textContent ?? '' : el.querySelector(':scope > span')?.textContent ?? el.textContent?.trim() ?? ''
    const combo = el.querySelector('.combo-label')?.textContent ?? null
    const input = el.querySelector('input:not([type=checkbox]):not([type=radio])') as HTMLInputElement | null
    const box = el.querySelector('input[type=checkbox]') as HTMLInputElement | null
    return { label: label.trim(), combo, value: input?.value ?? null, checked: box ? box.checked : null, enabled: !(input?.disabled ?? box?.disabled ?? false), legend: el.tagName === 'LEGEND' }
  })
}

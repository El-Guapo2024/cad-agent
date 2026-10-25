// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/PartDesign/Gui/Command.cpp: 2008 Jürgen Riegel
//   src/Mod/PartDesign/Gui/TaskLoftParameters.cpp: 2015 Stefan Tröger
//   src/Mod/PartDesign/Gui/TaskPipeParameters.cpp: 2015 Stefan Tröger
//   src/Mod/PartDesign/Gui/TaskHelixParameters.cpp: 2011 Juergen Riegel
//   src/Mod/PartDesign/App/FeatureHelix.cpp: 2010 Juergen Riegel
//   src/Mod/PartDesign/Gui/ViewProviderLoft.cpp: 2015 Stefan Tröger
//   src/Mod/PartDesign/Gui/ViewProviderPipe.cpp: 2015 Stefan Tröger
//   src/Mod/PartDesign/Gui/ViewProviderHelix.cpp: 2011 Juergen Riegel
//   No copyright line in the file: src/Mod/PartDesign/Gui/TaskLoftParameters.ui,
//       src/Mod/PartDesign/Gui/TaskPipeParameters.ui, src/Mod/PartDesign/Gui/TaskPipeOrientation.ui,
//       src/Mod/PartDesign/Gui/TaskPipeScaling.ui, src/Mod/PartDesign/Gui/TaskHelixParameters.ui
// PartDesign's Additive/Subtractive Loft, Pipe and Helix for parts whose shape is a FEATURES list
// (cad_agent/feature_sweep.py): the six commands as Command.cpp's prepareProfileBased runs them (the first selected sketch is
// the profile; a Loft takes the others as sections, a Pipe the second as its spine), their task panels laid out as FreeCAD's
// .ui files, a preview overlay, and their properties in the property view. Every edit is `cad feature` on the server, one
// undo step, as Pad's and Pocket's are.
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import * as THREE from 'three'
import { api, type FeatureOp } from './api'
import { getState, setState, subscribe, useStore, type Feature, type FeatureDoc } from './store'
import { closeTask, getView, showPanel } from './actions'
import { EditRow, Group, Row, TaskBox, propPad } from './panels'
import { QuantityBox, LENGTH, ANGLE, NUMBER } from './qsb'
import { QComboBox } from './combo'
import { messageBox } from './msgbox'
import * as quantity from './quantity'
import type { Entry } from './chrome'
import type { IconName } from './icons'
import { applyOps, bodyOfPart, curveOf, isSolid, numberOf, profileLoops, refOf, setAttachPicker, sketchMatrix, splitRef, targetBody, SKETCH } from './partdesign'
import { useRefPick } from './pd_pick'
import './pd_sweep.css'

type Kind = 'loft' | 'pipe' | 'helix'
type Info = { kind: Kind; additive: boolean; name: string; label: string; icon: IconName }
const mk = (kind: Kind, additive: boolean, icon: IconName): Info => {
  const word = { loft: 'Loft', pipe: 'Pipe', helix: 'Helix' }[kind]
  return { kind, additive, name: `${additive ? 'Additive' : 'Subtractive'}${word}`, label: `${additive ? 'Additive' : 'Subtractive'} ${word}`, icon }
}
/** The six, by TypeId: the call name in the part file (FreeCAD's short type), the menu text, the icon. */
export const SWEEP: Record<string, Info> = {
  'PartDesign::AdditiveLoft': mk('loft', true, 'pd-add-loft'), 'PartDesign::SubtractiveLoft': mk('loft', false, 'pd-sub-loft'),
  'PartDesign::AdditivePipe': mk('pipe', true, 'pd-add-pipe'), 'PartDesign::SubtractivePipe': mk('pipe', false, 'pd-sub-pipe'),
  'PartDesign::AdditiveHelix': mk('helix', true, 'pd-add-helix'), 'PartDesign::SubtractiveHelix': mk('helix', false, 'pd-sub-helix'),
}
export const isSweep = (type: string) => type in SWEEP
export const SWEEP_KINDS: Record<string, string> = Object.fromEntries(Object.entries(SWEEP).map(([t, i]) => [t, i.name]))
export const SWEEP_ICONS: Record<string, IconName> = Object.fromEntries(Object.entries(SWEEP).map(([t, i]) => [t, i.icon]))
const typeOf = (name: string) => `PartDesign::${name}`
const NO_BODY = 'In order to use PartDesign you need an active Body object in the document. Please make one active (double click) '
  + 'or create one.\n\nIf you have a legacy document with PartDesign objects without Body, use the migrate function in PartDesign '
  + 'to put them into a Body.'
const nextName = (doc: FeatureDoc, base: string) => {
  const names = new Set(doc.features.map((f) => f.name))
  if (!names.has(base)) return base
  for (let i = 1; ; i++) { const n = `${base}${String(i).padStart(3, '0')}`; if (!names.has(n)) return n }
}

// ── links: "Sketch", ["Sketch", "Vertex1"], ["Pad", ["Edge1", "Edge2"]] (feature_sweep.link) ──────────────────────
type Link = string | [string, string | string[]] | null
const linkName = (l: unknown): string | null => (typeof l === 'string' ? l : Array.isArray(l) && typeof l[0] === 'string' ? l[0] : null)
const linkSubs = (l: unknown): string[] => (Array.isArray(l) ? (Array.isArray(l[1]) ? (l[1] as string[]) : typeof l[1] === 'string' && l[1] ? [l[1]] : []) : [])
const makeLink = (name: string | null, subs: string[]): Link => (!name ? null : !subs.length ? name : subs.length === 1 ? [name, subs[0]] : [name, subs])
/** PartDesignGui's make2DLabel: the object's label, with ":Vertex1" for a sub-element. */
const linkText = (l: unknown) => { const n = linkName(l); const s = linkSubs(l); return n ? (s.length ? `${n}:${s.join(',')}` : n) : '' }

/** The features a sweep links to (deleting one of those is refused while it does). */
export function sweepUses(f: Feature, names: string[]): boolean {
  if (!isSweep(f.type)) return false
  const links = [f.profile, f.spine, f.auxiliary_spine, ...((f.sections as unknown[] | undefined) ?? [])]
  if (SWEEP[f.type].kind === 'helix') links.push(f.reference_axis)
  return links.some((l) => { const n = linkName(l); return !!n && names.includes(n) })
}
/** ViewProviderLoft/Pipe/Helix::claimChildren: the profile, the sections, the spine and the auxiliary spine that are sketches. */
export function sweepChildren(doc: FeatureDoc, f: Feature): Feature[] {
  const names = [linkName(f.profile)]
  if (SWEEP[f.type]?.kind !== 'helix') names.push(...((f.sections as unknown[] | undefined) ?? []).map(linkName))
  if (SWEEP[f.type]?.kind === 'pipe') names.push(linkName(f.spine), linkName(f.auxiliary_spine))
  const out: Feature[] = []
  for (const n of names) {
    const s = n ? doc.features.find((x) => x.name === n && x.type === SKETCH) : undefined
    if (s && !out.includes(s)) out.push(s)
  }
  return out
}

// ── the commands (Command.cpp: prepareProfileBased, then the worker) ─────────────────────────────────────
let pendingNew: { profile: string; sections: string[]; spine: string | null } | null = null

/** PartDesign_AdditiveLoft ... PartDesign_SubtractiveHelix: the first selected sketch (or the Body's one sketch no feature
 *  uses) is the profile; a Loft takes the other selected sketches as its sections, a Pipe a second one as its spine
 *  (prepareProfileBased). A subtractive one needs a solid to cut, as FreeCAD's check says. The panel opens on a new feature,
 *  which OK makes ("Make AdditiveLoft") and Cancel never writes. */
export async function sweepCommand(type: string) {
  const info = SWEEP[type]
  const s = getState()
  const part = targetBody()
  if (!part) { await messageBox('warning', 'No active body', NO_BODY); return }
  const doc = s.features[part]
  if (!info.additive && !doc.base && !doc.features.some((f) => isSolid(f.type))) {
    await messageBox('warning', 'Cannot use this command as there is no solid to subtract from.',
      'Ensure that the body contains a feature before attempting a subtractive command.')
    return
  }
  const selected = s.featSel.map(splitRef).filter(([p, n]) => p === part && doc.features.find((f) => f.name === n)?.type === SKETCH).map(([, n]) => n)
  const used = new Set(doc.features.filter((f) => f.type !== SKETCH).flatMap((f) => [linkName(f.profile)]).filter(Boolean) as string[])
  const free = doc.features.filter((f) => f.type === SKETCH && !used.has(f.name))
  const profile = selected[0] ?? (free.length === 1 ? free[0].name : null)
  if (!profile) {
    await messageBox('warning', 'No sketch to use', free.length ? 'Please select a sketch or a face, and then the command.' : 'Please create a sketch or 2D object first.')
    return
  }
  pendingNew = { profile, sections: info.kind === 'loft' ? selected.slice(1) : [], spine: info.kind === 'pipe' && selected.length === 2 ? selected[1] : null }
  setState({ task: { kind: 'pdSweep', body: part, other: `new:${type}` } })
  showPanel('tasks')
}

/** The Part Design menu's and toolbar's six entries (Workbench.cpp's order: Additive ... then Subtractive ...). */
export function sweepEntries(doc: boolean): Record<'addLoft' | 'addPipe' | 'addHelix' | 'subLoft' | 'subPipe' | 'subHelix', Entry> {
  const e = (t: string): Entry => ({ label: SWEEP[t].label, icon: SWEEP[t].icon, cmd: `PartDesign_${SWEEP[t].name}`, disabled: !doc, onSelect: () => void sweepCommand(t) })
  return { addLoft: e('PartDesign::AdditiveLoft'), addPipe: e('PartDesign::AdditivePipe'), addHelix: e('PartDesign::AdditiveHelix'),
    subLoft: e('PartDesign::SubtractiveLoft'), subPipe: e('PartDesign::SubtractivePipe'), subHelix: e('PartDesign::SubtractiveHelix') }
}
/** For cmdreg.ts: [command, menu text, run]. */
export function sweepCommands(): [string, string, () => void][] {
  return Object.entries(SWEEP).map(([t, i]) => [`PartDesign_${i.name}`, i.label, () => void sweepCommand(t)])
}

/** Std_Edit / a double-click: the feature's panel. True when it is one of the six. */
export function editSweep(part: string, f: Feature): boolean {
  if (!isSweep(f.type)) return false
  setState({ task: { kind: 'pdSweep', body: part, other: f.name, edit: true } })
  showPanel('tasks')
  return true
}

async function resolve(part: string, feature: Record<string, unknown>): Promise<Feature | null> {
  const slug = getState().slug
  if (!slug) return null
  try {
    const r = await api.cad(slug, ['feature', 'resolve', slug, part, '--feature', JSON.stringify(feature)])
    return r.exit === 0 && r.data?.feature ? (r.data.feature as Feature) : null
  } catch { return null }
}

// ── shared bits of the panels ───────────────────────────────────────────────────────────────────────────
function OkCancel({ onOk, onCancel }: { onOk(): void; onCancel(): void }) {
  return <div className="tbuttons pd-buttons"><button className="qbtn default" onClick={onOk}>OK</button><button className="qbtn" onClick={onCancel}>Cancel</button></div>
}
function Field({ label, children, hidden, title }: { label: string; children: ReactNode; hidden?: boolean; title?: string }) {
  if (hidden) return null
  return <label className="tfield" title={title}><span>{label}</span>{children}</label>
}
function Check({ label, checked, onChange, disabled, title }: { label: string; checked: boolean; onChange(v: boolean): void; disabled?: boolean; title?: string }) {
  return <label className="tcheck" title={title}><input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} /> {label}</label>
}
function Combo({ value, items, onChange, disabled }: { value: string; items: [string, string][]; onChange(v: string): void; disabled?: (v: string) => boolean }) {
  return <QComboBox value={value} onChange={(e) => onChange(e.target.value)}>
    {items.map(([k, t]) => <option key={k} value={k} disabled={disabled?.(k)}>{t}</option>)}</QComboBox>
}
/** A QToolButton that toggles a selection mode: while it is down, a click on a tree row (or an edge in the 3D view, for
 *  the edge lists) is taken as the reference, as the panels' onSelectionChanged takes FreeCAD's selection. */
function Toggle({ label, on, onToggle, title }: { label: string; on: boolean; onToggle(on: boolean): void; title?: string }) {
  return <button className={`qbtn ptool${on ? ' on' : ''}`} aria-pressed={on} title={title} onClick={() => onToggle(!on)}>{label}</button>
}
/** A QListWidget: one row per item, the current one highlighted, rows reordered by dragging when `reorder`, Delete (the
 *  context menu's Remove) takes the current one out. */
function ListBox({ items, onChange, reorder, title, name }: { items: string[]; onChange(next: string[]): void; reorder?: boolean; title?: string; name: string }) {
  const [cur, setCur] = useState<number | null>(null)
  const drag = useRef<number | null>(null)
  return <div className="pd-list" data-name={name} title={title} tabIndex={0}
    onKeyDown={(e) => { if ((e.key === 'Delete' || e.key === 'Backspace') && cur !== null) { onChange(items.filter((_, i) => i !== cur)); setCur(null) } }}>
    {items.map((t, i) => <div key={`${t}:${i}`} className={`pd-list-row${cur === i ? ' cur' : ''}`} draggable={!!reorder} onClick={() => setCur(i)}
      onDragStart={() => { drag.current = i }} onDragOver={(e) => e.preventDefault()}
      onDrop={() => { const from = drag.current; drag.current = null; if (from === null || from === i) return; const next = [...items]; const [x] = next.splice(from, 1); next.splice(i, 0, x); onChange(next); setCur(i) }}>{t}</div>)}
  </div>
}
type Mode = string | null
/** While one of a panel's selection buttons is down: tree-row clicks (setAttachPicker) and 3D edge picks (subSel) go to it. */
function useSelectionMode(mode: Mode, part: string, onRow: (name: string) => void, onEdge: (feature: string, edge: string) => void, feature: string | null = null) {
  // pd_pick.tsx: the base shown in the Body's place and its edges clicked in the 3D view (an edge mode takes edges, the
  // others whole objects: a sketch's row, a datum), the tree's rows through the same gate
  const edgeMode = !!mode && /Edge$/.test(mode)
  useRefPick(!!mode, { part, feature, allow: (p) => (edgeMode ? p.kind === 'element' && p.sub.startsWith('Edge') : !p.sub || p.kind !== 'element'),
    onPick: (p) => { if (edgeMode) onEdge(p.obj, p.sub); else onRow(p.obj) } })
}

// ── geometry for the previews ────────────────────────────────────────────────────────────────────────────
type Curve = NonNullable<ReturnType<typeof curveOf>>
const curvesOf = (sk: Feature): Curve[] => (sk.geometry ?? []).map(curveOf).filter((c): c is Curve => !!c)
/** A sketch's non-construction curves as polylines in the Body's frame (the spine of a preview). */
function sketchPolylines(sk: Feature): THREE.Vector3[][] {
  const m = sketchMatrix(sk), out: THREE.Vector3[][] = []
  const p = (x: number, y: number) => new THREE.Vector3(x, y, 0).applyMatrix4(m)
  for (const c of curvesOf(sk)) {
    if (c.cons) continue
    if (c.kind === 'line') out.push([p(...c.a), p(...c.b)])
    else if (c.kind === 'circle' || c.kind === 'arc') {
      const a0 = c.kind === 'arc' ? c.a0 : 0
      let a1 = c.kind === 'arc' ? c.a1 : 2 * Math.PI
      while (a1 < a0) a1 += 2 * Math.PI
      const n = Math.max(8, Math.ceil(((a1 - a0) / (2 * Math.PI)) * 48))
      out.push(Array.from({ length: n + 1 }, (_, i) => p(c.c[0] + c.r * Math.cos(a0 + ((a1 - a0) * i) / n), c.c[1] + c.r * Math.sin(a0 + ((a1 - a0) * i) / n))))
    }
  }
  return out
}
/** A sketch's closed loops in the Body's frame, each resampled to n points (for a loft's preview). */
function loops3d(sk: Feature, n = 0): THREE.Vector3[][] {
  const m = sketchMatrix(sk)
  return profileLoops(curvesOf(sk)).map((loop) => {
    const pts = loop.map((v) => new THREE.Vector3(v.x, v.y, 0).applyMatrix4(m))
    return n ? resample(pts, n) : pts
  })
}
function resample(pts: THREE.Vector3[], n: number): THREE.Vector3[] {
  const ring = [...pts, pts[0]], len: number[] = [0]
  for (let i = 1; i < ring.length; i++) len.push(len[i - 1] + ring[i].distanceTo(ring[i - 1]))
  const total = len[len.length - 1] || 1, out: THREE.Vector3[] = []
  for (let k = 0, j = 1; k < n; k++) {
    const t = (total * k) / n
    while (j < len.length - 1 && len[j] < t) j++
    const f = (t - len[j - 1]) / ((len[j] - len[j - 1]) || 1)
    out.push(ring[j - 1].clone().lerp(ring[j], f))
  }
  return out
}
const pointOf = (sk: Feature): THREE.Vector3 | null => {
  const c = curvesOf(sk).find((x) => x.kind === 'point' && !x.cons)
  return c && c.kind === 'point' ? new THREE.Vector3(c.p[0], c.p[1], 0).applyMatrix4(sketchMatrix(sk)) : null
}
/** SoPreviewShape's colours, as Pad's preview: green for additive, red for subtractive. */
function previewGroup(additive: boolean, strips: THREE.Vector3[][][], lines: THREE.Vector3[][]): THREE.Object3D {
  const color = additive ? new THREE.Color(0, 1, 0.6) : new THREE.Color(1, 0, 0)
  const g = new THREE.Group()
  for (const rows of strips) {
    if (rows.length < 2) continue
    const n = rows[0].length, pos: number[] = [], idx: number[] = []
    for (const r of rows) for (const v of r) pos.push(v.x, v.y, v.z)
    for (let i = 0; i < rows.length - 1; i++) for (let j = 0; j < n; j++) {
      const a = i * n + j, b = i * n + ((j + 1) % n), c = a + n, d = b + n
      idx.push(a, b, d, a, d, c)
    }
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3))
    geo.setIndex(idx)
    geo.computeVertexNormals()
    g.add(new THREE.Mesh(geo, new THREE.MeshPhongMaterial({ color, transparent: true, opacity: 0.2, depthWrite: false, side: THREE.DoubleSide })))
  }
  for (const l of lines) g.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(l), new THREE.LineBasicMaterial({ color })))
  return g
}
function inPart(g: THREE.Object3D, body: ReturnType<typeof bodyOfPart>): THREE.Object3D {
  const toPart = new THREE.Matrix4()
  if (body?.matrix?.length === 16) toPart.fromArray(body.matrix).transpose()
  g.applyMatrix4(toPart)
  return g
}

// ── the panels ──────────────────────────────────────────────────────────────────────────────────────────
type Values = Record<string, unknown>
const DEFAULTS: Record<Kind, Values> = {
  loft: { profile: null, sections: [], ruled: false, closed: false, operation: 'Subtraction' },
  pipe: { profile: null, spine: null, mode: 'Standard', transition: 'Transformed', transformation: 'Constant', sections: [], auxiliary_spine: null,
    auxiliary_curvilinear: true, binormal: [0, 0, 0], operation: 'Subtraction' },
  helix: { profile: null, reference_axis: null, mode: 'pitch-height-angle', pitch: 10, height: 30, turns: 3, angle: 0, growth: 0, left_handed: false, reversed: false,
    operation: 'Subtraction' },
}
const NUMERIC = new Set(['pitch', 'height', 'turns', 'angle', 'growth'])

/** The open Loft, Pipe or Helix panel: `other` is the feature edited, or "new:<TypeId>" for one OK makes. */
export function SweepTask({ part, other, edit }: { part: string; other: string; edit: boolean }) {
  const s = useStore((x) => x)
  const doc = s.features[part]
  const existing = edit ? doc?.features.find((f) => f.name === other) : undefined
  const type = existing?.type ?? other.replace(/^new:/, '')
  const info = SWEEP[type]
  const initial = useMemo((): Values => {
    const d = { ...DEFAULTS[info.kind] }
    if (existing) {
      for (const k of Object.keys(d)) if (k in existing) d[k] = NUMERIC.has(k) ? numberOf(existing[k], doc?.params ?? {}) ?? d[k] : existing[k]
      return d
    }
    const p = pendingNew
    d.profile = p?.profile ?? null
    if (info.kind === 'loft') d.sections = p?.sections ?? []
    if (info.kind === 'pipe') d.spine = p?.spine ?? null
    if (info.kind === 'helix') d.reference_axis = [p?.profile, 'V_Axis']
    return d
  }, [part, other, edit])
  const [v, setV] = useState(initial)
  const set = (patch: Values) => setV((x) => ({ ...x, ...patch }))
  const [update, setUpdate] = useState(true)
  const [overlay, setOverlay] = useState(true)
  const [mode, setMode] = useState<Mode>(null)
  const name = existing?.name ?? (doc ? nextName(doc, info.name) : info.name)
  // a new Helix: what its command and panel set (ReferenceAxis, then proposeParameters' Pitch and Height)
  useEffect(() => {
    if (edit || info.kind !== 'helix' || !v.profile) return
    void resolve(part, { name, type, profile: v.profile }).then((r) => { if (r) set({ reference_axis: r.reference_axis, pitch: Number(r.pitch), height: Number(r.height) }) })
  }, [part, other, edit])
  const sketchOf = (n: string | null) => (n ? doc?.features.find((f) => f.name === n && f.type === SKETCH) : undefined)
  const profile = sketchOf(linkName(v.profile))
  const body = bodyOfPart(s, part)
  const drawn = useRef(false)
  useEffect(() => {
    if (!update && drawn.current) return
    drawn.current = true
    let g: THREE.Object3D | null = null
    try { g = overlay && profile && doc ? preview(info, v, doc) : null } catch { g = null }
    getView()?.setHelper('pd-preview', g ? inPart(g, body) : null)
  }, [v, overlay, update, body])
  useEffect(() => () => { getView()?.setHelper('pd-preview', null) }, [])
  // the selection buttons: what a tree row or an edge picked while one is down does
  const pick = (n: string) => {
    if (mode === 'profile') set({ profile: n })
    else if (mode === 'spine') set({ spine: n })
    else if (mode === 'aux') set({ auxiliary_spine: n })
    else if (mode === 'addSection' && n !== linkName(v.profile) && !(v.sections as unknown[]).some((x) => linkName(x) === n)) set({ sections: [...(v.sections as unknown[]), n] })
    else if (mode === 'removeSection') set({ sections: (v.sections as unknown[]).filter((x) => linkName(x) !== n) })
    else return
    setMode(null)
  }
  const pickEdge = (feat: string, e: string) => {
    const key = mode === 'addEdge' || mode === 'removeEdge' ? 'spine' : mode === 'addAuxEdge' || mode === 'removeAuxEdge' ? 'auxiliary_spine' : null
    if (!key) return
    const cur = v[key], subs = linkName(cur) === feat ? linkSubs(cur) : []
    const next = mode!.startsWith('add') ? (subs.includes(e) ? subs : [...subs, e]) : subs.filter((x) => x !== e)
    set({ [key]: makeLink(feat, next) })
  }
  useSelectionMode(mode, part, pick, pickEdge, existing?.name ?? null)
  if (!doc || !profile) return <div className="tasks"><p className="hint">{part}: no sketch {linkName(v.profile) ?? linkName(existing?.profile) ?? ''}</p></div>
  const props = (): Values => {
    const keep = Object.keys(DEFAULTS[info.kind]).filter((k) => k !== 'operation' || !info.additive)
    const out: Values = {}
    for (const k of keep) out[k] = v[k]
    if (info.kind === 'helix') for (const k of NUMERIC) if (!MODE_INPUTS[String(v.mode)].includes(k) && !edit) delete out[k]
    return out
  }
  const ok = async () => {
    const p = props()
    if (existing) {
      const was = (k: string) => (NUMERIC.has(k) ? numberOf(existing[k], doc.params) ?? DEFAULTS[info.kind][k] : existing[k] ?? DEFAULTS[info.kind][k])
      const changed = Object.fromEntries(Object.entries(p).filter(([k, x]) => JSON.stringify(x) !== JSON.stringify(was(k))
        && !(NUMERIC.has(k) && typeof existing[k] === 'string' && numberOf(existing[k], doc.params) === x)))
      closeTask()
      if (Object.keys(changed).length) await applyOps(part, [{ op: 'set', name, props: changed }], { name: `Edit ${name}` })
      return
    }
    const ops: FeatureOp[] = [{ op: 'add', feature: { name, type, ...p }, after: lastUsed(doc, p) }]
    closeTask()
    const done = await applyOps(part, ops, { name: `Make ${info.name}` })
    if (done) setState({ featSel: [refOf(part, name)], selected: [] })
  }
  const title = `${info.label} Parameters`
  const operation = !info.additive && <Field label="Operation"><Combo value={String(v.operation)} items={[['Subtraction', 'Subtraction'], ['Common', 'Common']]} onChange={(x) => set({ operation: x })} /></Field>
  const previewBox = <TaskBox title="Preview" icon={info.icon}>
    <Check label="Show final result" checked={false} disabled onChange={() => {}} title="n/a: the result is built when OK writes it; the preview shows the tool" />
    <Check label="Show preview overlay" checked={overlay} onChange={setOverlay} />
  </TaskBox>
  const toggle = (m: string) => (on: boolean) => setMode(on ? m : null)
  const objectRow = (key: string, m: string) => <div className="tfield pd-object">
    <Toggle label="Object" on={mode === m} onToggle={toggle(m)} title="Click a sketch in the tree to take it" />
    <input value={linkName(v[key]) ?? ''} onChange={(e) => set({ [key]: e.target.value ? makeLink(e.target.value, linkSubs(v[key])) : null })} />
  </div>
  if (info.kind === 'loft') {
    const secs = (v.sections as unknown[]).map(linkText)
    return <div className="tasks">
      <OkCancel onOk={() => void ok()} onCancel={closeTask} />
      <TaskBox title={title} icon={info.icon}>
        <div className="pd-form">
          <Check label="Ruled surface" checked={v.ruled === true} onChange={(x) => set({ ruled: x })} />
          <Check label="Closed" checked={v.closed === true} onChange={(x) => set({ closed: x })} />
          <fieldset className="tgroup"><legend>Profile</legend>{objectRow('profile', 'profile')}</fieldset>
          <div className="hbox">
            <Toggle label="Add Section" on={mode === 'addSection'} onToggle={toggle('addSection')} title="Click a sketch in the tree to add it" />
            <Toggle label="Remove Section" on={mode === 'removeSection'} onToggle={toggle('removeSection')} title="Click a section's sketch in the tree to remove it" />
          </div>
          <ListBox name="sections" items={secs} reorder title="List can be reordered by dragging"
            onChange={(next) => set({ sections: next.map((t) => (v.sections as unknown[])[secs.indexOf(t)]) })} />
          {operation}
          <Check label="Recompute on change" checked={update} onChange={setUpdate} />
        </div>
      </TaskBox>
      {previewBox}
    </div>
  }
  if (info.kind === 'pipe') {
    const edges = linkSubs(v.spine), aux = linkSubs(v.auxiliary_spine)
    const bin = (v.binormal as number[]) ?? [0, 0, 0]
    const secs = (v.sections as unknown[]).map(linkText)
    return <div className="tasks">
      <OkCancel onOk={() => void ok()} onCancel={closeTask} />
      <TaskBox title={title} icon={info.icon}>
        <div className="pd-form">
          <fieldset className="tgroup"><legend>Profile</legend>{objectRow('profile', 'profile')}</fieldset>
          <Field label="Corner transition"><Combo value={String(v.transition)} items={[['Transformed', 'Transformed'], ['Right corner', 'Right corner'], ['Round corner', 'Round corner']]} onChange={(x) => set({ transition: x })} /></Field>
          <fieldset className="tgroup"><legend>Path to Sweep Along</legend>
            {objectRow('spine', 'spine')}
            <div className="hbox">
              <Toggle label="Add edge" on={mode === 'addEdge'} onToggle={toggle('addEdge')} title="Click an edge of the Body in the 3D view to add it" />
              <Toggle label="Remove edge" on={mode === 'removeEdge'} onToggle={toggle('removeEdge')} title="Click an edge of the Body in the 3D view to remove it" />
            </div>
            <ListBox name="spine-edges" items={edges} onChange={(next) => set({ spine: makeLink(linkName(v.spine), next) })} />
          </fieldset>
          {operation}
        </div>
      </TaskBox>
      <TaskBox title={`${info.label} Section Orientation`} icon={info.icon}>
        <div className="pd-form">
          <Field label="Orientation mode"><Combo value={String(v.mode)} items={['Standard', 'Fixed', 'Frenet', 'Auxiliary', 'Binormal'].map((x) => [x, x])} onChange={(x) => set({ mode: x })} /></Field>
          {v.mode === 'Auxiliary' && <>
            <Check label="Curvilinear equivalence" checked={v.auxiliary_curvilinear === true} onChange={(x) => set({ auxiliary_curvilinear: x })} />
            <fieldset className="tgroup"><legend>Profile</legend>
              <div className="tfield pd-object">
                <Toggle label="Object" on={mode === 'aux'} onToggle={toggle('aux')} title="Click a sketch in the tree to take it" />
                <input value={linkName(v.auxiliary_spine) ?? ''} onChange={(e) => set({ auxiliary_spine: e.target.value || null })} />
                <button className="qbtn ptool" title="Clear" onClick={() => set({ auxiliary_spine: null })}>✕</button>
              </div>
              <div className="hbox">
                <Toggle label="Add Edge" on={mode === 'addAuxEdge'} onToggle={toggle('addAuxEdge')} />
                <Toggle label="Remove Edge" on={mode === 'removeAuxEdge'} onToggle={toggle('removeAuxEdge')} />
              </div>
              <ListBox name="aux-edges" items={aux} onChange={(next) => set({ auxiliary_spine: makeLink(linkName(v.auxiliary_spine), next) })} />
            </fieldset>
          </>}
          {v.mode === 'Binormal' && <>
            <div className="tfield pd-label"><span>Set the constant binormal vector used to calculate the profiles orientation</span></div>
            {(['X', 'Y', 'Z'] as const).map((a, i) => <Field key={a} label={a}><QuantityBox value={Number(bin[i] ?? 0)} dims={NUMBER} decimals={2} step={0.1}
              onChange={(x) => set({ binormal: bin.map((b, j) => (j === i ? x : Number(b ?? 0))) })} /></Field>)}
          </>}
        </div>
      </TaskBox>
      <TaskBox title={`${info.label} Section Transformation`} icon={info.icon}>
        <div className="pd-form">
          <Field label="Transform mode"><Combo value={v.transformation === 'Multisection' ? 'Multisection' : 'Constant'} items={[['Constant', 'Constant'], ['Multisection', 'Multisection']]} onChange={(x) => set({ transformation: x })} /></Field>
          {v.transformation === 'Multisection' && <>
            <div className="hbox">
              <Toggle label="Add Section" on={mode === 'addSection'} onToggle={toggle('addSection')} title="Click a sketch in the tree to add it" />
              <Toggle label="Remove Section" on={mode === 'removeSection'} onToggle={toggle('removeSection')} />
            </div>
            <ListBox name="sections" items={secs} reorder title="List can be reordered by dragging"
              onChange={(next) => set({ sections: next.map((t) => (v.sections as unknown[])[secs.indexOf(t)]) })} />
          </>}
        </div>
      </TaskBox>
      {previewBox}
    </div>
  }
  // the Helix
  const m = String(v.mode)
  const shows = (k: string) => MODE_INPUTS[m].includes(k)
  const status = helixStatus(v, profile)
  const onMode = (x: string) => {
    // onModeChanged: the fields take the properties as the last recompute left them (the derived ones too)
    const d = derived(v)
    set({ mode: x, ...(d ? { pitch: d.pitch, height: d.height, turns: d.turns, angle: d.angle, growth: d.growth } : {}) })
  }
  return <div className="tasks">
    <OkCancel onOk={() => void ok()} onCancel={closeTask} />
    <TaskBox title={title} icon={info.icon}>
      <div className="pd-form">
        <div className="tfield pd-status"><span>Status</span><span className="pd-message">{status}</span></div>
        <Field label="Axis"><Combo value={JSON.stringify(v.reference_axis)} items={helixAxisItems(profile, v.reference_axis)} disabled={(x) => x === 'select'}
          onChange={(x) => { if (x !== 'select') set({ reference_axis: JSON.parse(x) }) }} /></Field>
        <Field label="Mode"><Combo value={m} items={HELIX_MODES} onChange={onMode} /></Field>
        <Field label="Pitch" hidden={!shows('pitch')}><QuantityBox value={Number(v.pitch)} dims={LENGTH} min={0} onChange={(x) => set({ pitch: x })} /></Field>
        <Field label="Height" hidden={!shows('height')}><QuantityBox value={Number(v.height)} dims={LENGTH} min={0} onChange={(x) => set({ height: x })} /></Field>
        <Field label="Turns" hidden={!shows('turns')}><QuantityBox value={Number(v.turns)} dims={NUMBER} min={0} decimals={2} onChange={(x) => set({ turns: x })} /></Field>
        <Field label="Cone angle" hidden={!shows('angle')}><QuantityBox value={Number(v.angle)} dims={ANGLE} min={-89} max={89} onChange={(x) => set({ angle: x })} /></Field>
        <Field label="Radial growth" hidden={!shows('growth')}><QuantityBox value={Number(v.growth)} dims={LENGTH} onChange={(x) => set({ growth: x })} /></Field>
        <Check label="Left handed" checked={v.left_handed === true} onChange={(x) => set({ left_handed: x })} />
        <Check label="Reversed" checked={v.reversed === true} onChange={(x) => set({ reversed: x })} />
        {operation}
        <Check label="Recompute on change" checked={update} onChange={setUpdate} />
      </div>
    </TaskBox>
    {previewBox}
  </div>
}

/** The feature a new one goes after: the last of the sketches it links (FreeCAD inserts after the Tip, which the sketch is
 *  right after making it). */
function lastUsed(doc: FeatureDoc, p: Values): string | undefined {
  const names = new Set([p.profile, p.spine, p.auxiliary_spine, ...((p.sections as unknown[]) ?? [])].map(linkName).filter(Boolean) as string[])
  const idx = doc.features.map((f, i) => (names.has(f.name) ? i : -1)).filter((i) => i >= 0)
  return idx.length ? doc.features[Math.max(...idx)].name : undefined
}

// ── the Helix's modes and status (FeatureHelix.cpp) ──────────────────────────────────────────────────────
const HELIX_MODES: [string, string][] = [['pitch-height-angle', 'Pitch-Height-Angle'], ['pitch-turns-angle', 'Pitch-Turns-Angle'],
  ['height-turns-angle', 'Height-Turns-Angle'], ['height-turns-growth', 'Height-Turns-Growth']]
/** Helix::setReadWriteStatusForMode: the properties a mode reads; the others follow from them and are read-only. */
export const MODE_INPUTS: Record<string, string[]> = { 'pitch-height-angle': ['pitch', 'height', 'angle'], 'pitch-turns-angle': ['pitch', 'turns', 'angle'],
  'height-turns-angle': ['height', 'turns', 'angle'], 'height-turns-growth': ['height', 'turns', 'growth'] }
const CONFUSION = 1e-7
/** Helix::execute's first part: the mode's three checked (FreeCAD's messages) and the others computed. */
function derived(v: Values): { pitch: number; height: number; turns: number; angle: number; growth: number; error?: string } | null {
  let pitch = Number(v.pitch), height = Number(v.height), turns = Math.max(CONFUSION, Number(v.turns)), angle = Math.min(89, Math.max(-89, Number(v.angle))), growth = Number(v.growth)
  const tan = (a: number) => Math.tan(THREE.MathUtils.degToRad(a))
  const err = (e: string) => ({ pitch, height, turns, angle, growth, error: e })
  switch (v.mode) {
    case 'pitch-height-angle':
      if (pitch < CONFUSION) return err('Error: Pitch too small!')
      if (height < CONFUSION) return err('Error: height too small!')
      turns = height / pitch; growth = pitch * tan(angle); break
    case 'pitch-turns-angle':
      if (pitch < CONFUSION) return err('Error: pitch too small!')
      if (turns < CONFUSION) return err('Error: turns too small!')
      height = turns * pitch; growth = pitch * tan(angle); break
    case 'height-turns-angle':
      if (height < CONFUSION) return err('Error: height too small!')
      if (turns < CONFUSION) return err('Error: turns too small!')
      pitch = height / turns; growth = pitch * tan(angle); break
    case 'height-turns-growth':
      if (turns < CONFUSION) return err('Error: turns too small!')
      if (height < CONFUSION && Math.abs(growth) < CONFUSION && turns > 1) return err('Error: either height or growth must not be zero!')
      pitch = height / turns
      if (height > 0) angle = THREE.MathUtils.radToDeg(Math.atan((turns * growth) / height))
      break
    default: return null
  }
  return { pitch, height, turns, angle, growth }
}
/** The axis as the Helix takes it (Base, Axis: Helix::updateAxis), in the Body's frame. */
function helixAxis(axis: unknown, sketch: Feature): { base: THREE.Vector3; dir: THREE.Vector3 } | null {
  const m = sketchMatrix(sketch)
  if (typeof axis === 'string') {
    const d = ({ X_Axis: [1, 0, 0], Y_Axis: [0, 1, 0], Z_Axis: [0, 0, 1] } as Record<string, number[]>)[axis]
    return d ? { base: new THREE.Vector3(), dir: new THREE.Vector3(...d) } : null
  }
  if (!Array.isArray(axis) || axis[0] !== sketch.name) return null
  const sub = String(axis[1]), o = new THREE.Vector3().applyMatrix4(m)
  const local = sub === 'V_Axis' ? [0, 1, 0] : sub === 'H_Axis' ? [1, 0, 0] : sub === 'N_Axis' ? [0, 0, 1] : null
  if (local) return { base: o, dir: new THREE.Vector3(...local).transformDirection(m) }
  const k = /^Axis(\d+)$/.exec(sub)
  if (k) {
    const c = curvesOf(sketch).filter((x) => x.kind === 'line' && x.cons)[Number(k[1])]
    if (c?.kind === 'line') {
      const a = new THREE.Vector3(c.a[0], c.a[1], 0).applyMatrix4(m), b = new THREE.Vector3(c.b[0], c.b[1], 0).applyMatrix4(m)
      return { base: a, dir: b.sub(a) }            // Base::Axis: not normalised
    }
  }
  return null
}
function profileBox(sketch: Feature): THREE.Box3 {
  const box = new THREE.Box3()
  for (const loop of loops3d(sketch)) for (const p of loop) box.expandByPoint(p)
  return box
}
/** TaskHelixParameters::updateStatus for a helix that builds: the self-intersection warning when Pitch is below
 *  Helix::safePitch; the mode's error when its values are refused. */
function helixStatus(v: Values, sketch: Feature): string {
  const d = derived(v)
  if (!d) return 'Error: unsupported mode'
  if (d.error) return d.error
  const ax = helixAxis(v.reference_axis, sketch)
  if (!ax) return ''
  const n = new THREE.Vector3(0, 0, 1).transformDirection(sketchMatrix(sketch))
  const start = ax.dir.clone().cross(n)
  let safe: number
  const box = profileBox(sketch), size = box.getSize(new THREE.Vector3())
  if (start.length() < CONFUSION && v.mode !== 'height-turns-growth') safe = CONFUSION
  else if (start.length() < CONFUSION && Math.abs(d.turns) >= 1 && Math.abs(d.growth) > 0) safe = Infinity
  else {
    const pitch0 = size.dot(ax.dir.clone().normalize()), across = Math.abs(size.dot(start.clone().normalize()))
    if (v.mode === 'height-turns-growth') safe = Math.abs(d.growth) > across ? 0 : d.turns < 1 ? 0 : pitch0
    else {
      const a = Math.abs(THREE.MathUtils.degToRad(d.angle))
      safe = Math.tan(a) * pitch0 > across ? across / Math.tan(a) : pitch0
    }
  }
  return safe > d.pitch ? 'Warning: helix might be self intersecting' : ''
}
/** TaskHelixParameters::fillAxisCombo: the sketch's normal, vertical and horizontal axes, its construction lines, the Body's
 *  X, Y and Z axes, "Select reference…", and the current link when it is none of those. */
function helixAxisItems(sketch: Feature, current: unknown): [string, string][] {
  const items: [string, string][] = [[JSON.stringify([sketch.name, 'N_Axis']), 'Normal sketch axis'], [JSON.stringify([sketch.name, 'V_Axis']), 'Vertical sketch axis'],
    [JSON.stringify([sketch.name, 'H_Axis']), 'Horizontal sketch axis']]
  curvesOf(sketch).filter((c) => c.kind === 'line' && c.cons).forEach((_, i) => items.push([JSON.stringify([sketch.name, `Axis${i}`]), `Construction line ${i + 1}`]))
  items.push([JSON.stringify('X_Axis'), 'Base X-axis'], [JSON.stringify('Y_Axis'), 'Base Y-axis'], [JSON.stringify('Z_Axis'), 'Base Z-axis'], ['select', 'Select reference…'])
  const cur = JSON.stringify(current)
  if (current != null && !items.some(([k]) => k === cur)) items.splice(items.length - 1, 0, [cur, linkText(current)])
  return items
}

// ── the previews ─────────────────────────────────────────────────────────────────────────────────────────
function preview(info: Info, v: Values, doc: FeatureDoc): THREE.Object3D | null {
  const sk = (n: string | null) => (n ? doc.features.find((f) => f.name === n && f.type === SKETCH) : undefined)
  const prof = sk(linkName(v.profile))
  if (!prof) return null
  if (info.kind === 'loft') {
    // the loft's sections joined straight (a ruled preview), each loop resampled to the same count
    const chain = [v.profile, ...(v.sections as unknown[])].map((l) => ({ s: sk(linkName(l)), vertex: /^Vertex/.test(linkSubs(l)[0] ?? '') }))
      .filter((x) => x.s) as { s: Feature; vertex: boolean }[]
    const N = 64
    const rings = chain.map(({ s, vertex }) => { const pt = pointOf(s); return vertex || (!profileLoops(curvesOf(s)).length && pt) ? [Array(N).fill(pt)] : loops3d(s, N) })
    const count = rings[0]?.length ?? 0
    const strips: THREE.Vector3[][][] = []
    for (let w = 0; w < count; w++) {
      const rows = rings.map((r) => r[Math.min(w, r.length - 1)]).filter(Boolean) as THREE.Vector3[][]
      if (v.closed && rows.length > 2) rows.push(rows[0])
      strips.push(rows)
    }
    return previewGroup(info.additive, strips, rings.flat().map((l) => [...l, l[0]]))
  }
  if (info.kind === 'pipe') {
    // the path and the profile (FreeCAD previews the swept tool; this draws what it sweeps along)
    const spine = sk(linkName(v.spine))
    const lines = loops3d(prof).map((l) => [...l, l[0]])
    if (spine) lines.push(...sketchPolylines(spine))
    return previewGroup(info.additive, [], lines)
  }
  const d = derived(v), ax = helixAxis(v.reference_axis, prof)
  if (!d || d.error || !ax) return null
  // the profile turned about the axis and moved along it, turn by turn (makeSpiralHelix's path, the profile at its start)
  const dir = ax.dir.clone().normalize(), sign = (v.left_handed ? -1 : 1) * (v.reversed ? -1 : 1), along = v.reversed ? -1 : 1
  const loops = loops3d(prof, 32), steps = Math.max(8, Math.ceil(Math.min(d.turns, 50) * 48))
  const growth = v.mode === 'height-turns-growth' ? d.growth : d.pitch * Math.tan(THREE.MathUtils.degToRad(d.angle))
  const strips = loops.map((loop) => Array.from({ length: steps + 1 }, (_, i) => {
    const t = i / steps, ang = sign * 2 * Math.PI * d.turns * t
    return loop.map((p) => {
      const rel = p.clone().sub(ax.base), h = rel.dot(dir), radial = rel.clone().sub(dir.clone().multiplyScalar(h))
      const r = radial.length(), grown = r > 1e-9 ? radial.multiplyScalar((r + growth * d.turns * t) / r) : radial
      return ax.base.clone().add(grown.applyAxisAngle(dir, ang)).add(dir.clone().multiplyScalar(h + along * d.height * t))
    })
  }))
  return previewGroup(info.additive, strips, loops.map((l) => [...l, l[0]]))
}

// ── the property view (FreeCAD's groups in their order; ProfileBased's unused ones read-only) ───────────────────
type PropDef = { key: string; name: string; kind: 'length' | 'angle' | 'bool' | 'enum' | 'link' | 'text' | 'number'; items?: string[]; ro?: (f: Feature) => string | null }
const human = (k: string) => k.split('_').map((w) => w[0].toUpperCase() + w.slice(1)).join(' ')
const unused = (what: string) => () => `ProfileBased's, which a ${what} does not use`
function groupsOf(f: Feature): [string, PropDef[]][] {
  const info = SWEEP[f.type]
  const word = { loft: 'Loft', pipe: 'Pipe', helix: 'Helix' }[info.kind]
  const base: [string, PropDef[]] = ['Base', [{ key: 'name', name: 'Label', kind: 'text' }, { key: 'suppressed', name: 'Suppressed', kind: 'bool', ro: () => 'FEATURES has no suppressed state' }]]
  const pd: [string, PropDef[]] = ['Part Design', [...(info.additive ? [] : [{ key: 'operation', name: 'Operation', kind: 'enum' as const, items: ['Subtraction', 'Common'] }]),
    { key: 'refine', name: 'Refine', kind: 'bool' }, { key: 'fuzzy_tolerance', name: 'Fuzzy Tolerance', kind: 'text', ro: () => 'the booleans run at OCCT\'s own tolerance' }]]
  const sides: [string, PropDef[]][] = [['Side1', [{ key: 'up_to_face', name: 'Up To Face', kind: 'text', ro: unused(word) }, { key: 'up_to_shape', name: 'Up To Shape', kind: 'text', ro: unused(word) }]],
    ['Side2', [{ key: 'up_to_face2', name: 'Up To Face2', kind: 'text', ro: unused(word) }, { key: 'up_to_shape2', name: 'Up To Shape2', kind: 'text', ro: unused(word) }]]]
  const sb: [string, PropDef[]] = ['Sketch Based', [{ key: 'profile', name: 'Profile', kind: 'link' }, { key: 'midplane', name: 'Midplane', kind: 'bool', ro: unused(word) },
    ...(info.kind === 'helix' ? [] : [{ key: 'reversed', name: 'Reversed', kind: 'bool' as const, ro: unused(word) }]),
    { key: 'allow_multi_face', name: 'Allow Multi Face', kind: 'bool', ro: () => 'a Body\'s features always allow several faces' }]]
  if (info.kind === 'loft') {
    return [base, ['Loft', [{ key: 'sections', name: 'Sections', kind: 'text', ro: () => 'picked in the task panel (Add Section)' },
      { key: 'ruled', name: 'Ruled', kind: 'bool' }, { key: 'closed', name: 'Closed', kind: 'bool' }]], pd, ...sides, sb]
  }
  if (info.kind === 'pipe') {
    return [base, pd, ...sides, sb, ['Sweep', [{ key: 'sections', name: 'Sections', kind: 'text', ro: () => 'picked in the task panel (Multisection)' },
      { key: 'spine', name: 'Spine', kind: 'text', ro: () => 'picked in the task panel (Path to Sweep Along)' }, { key: 'spine_tangent', name: 'Spine Tangent', kind: 'bool' },
      { key: 'auxiliary_spine', name: 'Auxiliary Spine', kind: 'text', ro: () => 'picked in the task panel (Auxiliary)' },
      { key: 'auxiliary_spine_tangent', name: 'Auxiliary Spine Tangent', kind: 'bool' }, { key: 'auxiliary_curvilinear', name: 'Auxiliary Curvilinear', kind: 'bool' },
      { key: 'mode', name: 'Mode', kind: 'enum', items: ['Standard', 'Fixed', 'Frenet', 'Auxiliary', 'Binormal'] }, { key: 'binormal', name: 'Binormal', kind: 'text', ro: () => 'set in the task panel (Binormal)' },
      { key: 'transition', name: 'Transition', kind: 'enum', items: ['Transformed', 'Right corner', 'Round corner'] },
      { key: 'transformation', name: 'Transformation', kind: 'enum', items: ['Constant', 'Multisection', 'Linear', 'S-shape', 'Interpolation'] }]]]
  }
  const ro = (k: string) => (x: Feature) => (MODE_INPUTS[String(x.mode ?? 'pitch-height-angle')].includes(k) ? null : `follows from the mode's other values (Helix::setReadWriteStatusForMode)`)
  return [base, ['Helix', [{ key: '_base', name: 'Base', kind: 'text', ro: () => 'derived from the reference axis' }, { key: '_axis', name: 'Axis', kind: 'text', ro: () => 'derived from the reference axis' },
    { key: 'reference_axis', name: 'Reference Axis', kind: 'text', ro: () => 'picked in the task panel (Axis)' },
    { key: 'mode', name: 'Mode', kind: 'enum', items: HELIX_MODES.map(([k]) => k) }, { key: 'pitch', name: 'Pitch', kind: 'length', ro: ro('pitch') },
    { key: 'height', name: 'Height', kind: 'length', ro: ro('height') }, { key: 'turns', name: 'Turns', kind: 'number', ro: ro('turns') },
    { key: 'angle', name: 'Angle', kind: 'angle', ro: ro('angle') }, { key: 'growth', name: 'Growth', kind: 'length', ro: ro('growth') },
    { key: 'left_handed', name: 'Left Handed', kind: 'bool' }, { key: 'reversed', name: 'Reversed', kind: 'bool' }, { key: 'tolerance', name: 'Tolerance', kind: 'number' }]], pd, ...sides, sb]
}
const PROP_DEFAULTS: Record<string, unknown> = { suppressed: false, fuzzy_tolerance: 0, midplane: false, allow_multi_face: true, reversed: false, up_to_face: '', up_to_shape: '',
  up_to_face2: '', up_to_shape2: '', spine_tangent: false, auxiliary_spine_tangent: false, refine: true }
const fcFloat = (x: number) => String(Number(x.toPrecision(6)))
const vec = (v: THREE.Vector3 | number[]) => `[${(Array.isArray(v) ? v : v.toArray()).map((n) => (Math.abs(n) < 5e-10 ? 0 : n).toFixed(2)).join(' ')}]`
/** The Reference Axis as FreeCAD's property view shows it: "Sketch [V_Axis]", "Z-axis (Z_Axis)". */
const axisText = (r: unknown) => (typeof r === 'string' ? `${r[0]}-axis (${r})` : Array.isArray(r) ? `${r[0]} [${r[1]}]` : '')

export function SweepProps({ part, f, set, finishRename }: { part: string; f: Feature; set(props: Record<string, unknown>): void; finishRename(v: string): void }) {
  const s = useStore((x) => x)
  const doc = s.features[part]
  const params = doc?.params ?? {}
  const sketches = doc?.features.filter((x) => x.type === SKETCH).map((x) => x.name) ?? []
  const vars = Object.fromEntries(Object.entries(params).filter(([, x]) => typeof x === 'number').map(([k, x]) => [k, { value: x as number, dims: [0, 0, 0, 0, 0, 0, 0, 0] as quantity.Quantity['dims'] }]))
  const info = SWEEP[f.type]
  // the Helix's derived properties, as execute() leaves them
  const hv: Values = info.kind === 'helix' ? Object.fromEntries(['pitch', 'height', 'turns', 'angle', 'growth'].map((k) => [k, numberOf(f[k], params) ?? 0])) : {}
  const d = info.kind === 'helix' ? derived({ ...hv, mode: f.mode }) : null
  const prof = doc?.features.find((x) => x.name === linkName(f.profile) && x.type === SKETCH)
  const ax = info.kind === 'helix' && prof ? helixAxis(f.reference_axis, prof) : null
  const value = (k: string): unknown => {
    if (k === 'name') return f.name
    if (k === '_base') return ax ? vec(ax.base) : '[0.00 0.00 0.00]'
    if (k === '_axis') return ax ? vec(ax.dir.clone().normalize()) : '[0.00 1.00 0.00]'
    if (info.kind === 'helix' && d && !d.error && k in d && !MODE_INPUTS[String(f.mode ?? 'pitch-height-angle')].includes(k)) return (d as Record<string, unknown>)[k]
    return f[k] ?? PROP_DEFAULTS[k] ?? ''
  }
  const row = (p: PropDef): ReactNode => {
    const v = value(p.key)
    const why = p.ro?.(f) ?? null
    const shown = (x: unknown) => (p.kind === 'length' ? quantity.userString({ value: numberOf(x, params) ?? 0, dims: LENGTH }).text + (typeof x === 'string' ? `  (= ${x})` : '')
      : p.kind === 'angle' ? quantity.userString({ value: numberOf(x, params) ?? 0, dims: ANGLE }).text + (typeof x === 'string' ? `  (= ${x})` : '')
        : p.kind === 'number' ? (typeof x === 'number' ? fcFloat(x) : String(x)) : p.key === 'reference_axis' ? axisText(x)
          : p.key === 'binormal' ? vec((x as number[]) ?? [0, 0, 0]) : Array.isArray(x) && (p.key === 'sections') ? x.map(linkText).join(', ')
            : p.key === 'spine' || p.key === 'auxiliary_spine' || p.key === 'profile' ? linkText(x) : String(x ?? ''))
    if (why) return <Row key={p.key} k={<span title={`Read-only: ${why}`}>{p.name}</span>} v={shown(v)} />
    if (p.key === 'name') return <EditRow key={p.key} k={p.name} value={f.name} type="str" onCommit={(x) => finishRename(String(x))} />
    if (p.kind === 'bool') return <EditRow key={p.key} k={p.name} value={v === true} type="bool" onCommit={(x) => set({ [p.key]: x })} />
    if (p.kind === 'enum' || p.kind === 'link') {
      const items = p.kind === 'link' ? sketches : p.items ?? [String(v)]
      return <div key={p.key} className="prow" tabIndex={0}><span className="pk" style={propPad(0)}>{p.name}</span>
        <span className="pv"><QComboBox className="qselect-pv" value={String(linkName(v) ?? v)} onChange={(e) => set({ [p.key]: e.target.value })}>{items.map((o) => <option key={o}>{o}</option>)}</QComboBox></span></div>
    }
    if (p.kind === 'length' || p.kind === 'angle') {
      const n = numberOf(v, params) ?? 0
      return <EditRow key={p.key} k={p.name} value={n} type="float" kind={p.kind === 'length' ? 'Length' : 'Angle'} vars={vars} owner={f.name}
        onCommit={(x) => set({ [p.key]: x })} onExpr={(text) => set({ [p.key]: text })} note={typeof v === 'string' ? `= ${v}` : undefined} />
    }
    if (p.kind === 'number') return <EditRow key={p.key} k={p.name} value={numberOf(v, params) ?? 0} type="float" vars={vars} owner={f.name}
      onCommit={(x) => set({ [p.key]: Number(x) })} onExpr={(text) => set({ [p.key]: text })} note={typeof v === 'string' ? `= ${v}` : undefined} />
    return <EditRow key={p.key} k={p.name} value={String(v)} type="str" onCommit={(x) => set({ [p.key]: x })} />
  }
  void human
  return <>{groupsOf(f).map(([g, defs]) => <Group key={g} title={g}>{defs.map(row)}</Group>)}</>
}

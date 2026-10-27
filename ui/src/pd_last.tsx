// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/PartDesign/InvoluteGearFeature.py: 2014 Juergen Riegel (CommandInvoluteGear, makeInvoluteGear, the task
//     panel: assignValue, transferTo, transferFrom, accept, reject)
//   src/Mod/PartDesign/SprocketFeature.py: 2020 Adam Spontarelli (CommandSprocket, makeSprocket, SprocketTaskPanel,
//     sprocketReferenceChanged, SprocketReferenceRollerTable, reject)
//   src/Mod/PartDesign/Gui/Command.cpp: 2008 Jürgen Riegel (CmdPartDesignSubShapeBinder)
//   src/Mod/PartDesign/Gui/ViewProviderShapeBinder.cpp: 2015 Stefan Tröger (ViewProviderSubShapeBinder: UseBinderStyle,
//     doubleClicked)
//   No copyright line in the file: src/Mod/PartDesign/InvoluteGearFeature.ui, src/Mod/PartDesign/SprocketFeature.ui
// PartDesign's Involute Gear and Sprocket (cad_agent/feature_gear.py: a closed wire a Pad or a Pocket takes as its
// profile) and Sub-Shape Binder (cad_agent/feature_subbinder.py): their commands, the gears' task panels (the .ui forms,
// each value applied to the preview as it changes, as assignValue does), the wires and binders drawn in the 3D view from
// the server's shapes (`cad feature shape`), the tree's rows and context menus, and the property view. Each edit is one
// step of the shared undo journal ("Create involute gear", "Create Sprocket", "Create Sub-Shape Binder").
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import * as THREE from 'three'
import { api, type Body, type FeatureOp } from './api'
import { getState, report, setState, subscribe, useStore, type Feature, type FeatureDoc } from './store'
import { closeTask, getView, loadFeatures, showPanel } from './actions'
import type { IconName } from './icons'
import { EditRow, Group, Row, TaskBox, propPad } from './panels'
import { QuantityBox, LENGTH, ANGLE } from './qsb'
import { QComboBox } from './combo'
import { messageBox } from './msgbox'
import type { Entry } from './chrome'
import { applyOps, bodyOfPart, featureVisible, isSolid, numberOf, refOf, splitRef, targetBody } from './partdesign'
import { refsOfSelection, attachmentRows, type Ref } from './pd_attach'
import * as quantity from './quantity'
import './partdesign.css'

export const GEAR = 'Part::InvoluteGear', SPROCKET = 'Part::Sprocket', SUB_BINDER = 'PartDesign::SubShapeBinder'
/** A Part2DObject of PartDesign's: a profile a Pad or Pocket takes, as a sketch is. */
export const isProfile2d = (t: unknown): boolean => t === GEAR || t === SPROCKET
export const isSubBinder = (t: unknown): boolean => t === SUB_BINDER
/** What this module draws, edits and lists: not a solid feature of the Body. */
export const isLast = (t: unknown): boolean => isProfile2d(t) || isSubBinder(t)
export const LAST_ICONS: Record<string, IconName> = { [GEAR]: 'pd-gear', [SPROCKET]: 'pd-sprocket', [SUB_BINDER]: 'pd-subshape-binder' }
export const LAST_KINDS: Record<string, string> = { [GEAR]: 'InvoluteGear', [SPROCKET]: 'Sprocket', [SUB_BINDER]: 'SubShapeBinder' }

const NO_BODY = 'In order to use PartDesign you need an active Body object in the document. Please make one active (double click) '
  + 'or create one.\n\nIf you have a legacy document with PartDesign objects without Body, use the migrate function in PartDesign '
  + 'to put them into a Body.'
const nextName = (doc: FeatureDoc, base: string) => {
  const names = new Set(doc.features.map((f) => f.name))
  if (!names.has(base)) return base
  for (let i = 1; ; i++) { const n = `${base}${String(i).padStart(3, '0')}`; if (!names.has(n)) return n }
}
const INCH = 25.4

// ── the gears' properties (InvoluteGearFeature.py's and SprocketFeature.py's _ensure_properties) ──────────────
type Kind = 'gear' | 'sprocket'
const TYPE: Record<Kind, string> = { gear: GEAR, sprocket: SPROCKET }
const kindOf = (t: string): Kind | null => (t === GEAR ? 'gear' : t === SPROCKET ? 'sprocket' : null)
export const GEAR_DEFAULTS: Record<string, number | boolean | string> = { number_of_teeth: 26, modules: 2.5, pressure_angle: 20, high_precision: true,
  external_gear: true, addendum_coefficient: 1, dedendum_coefficient: 1.25, root_fillet_coefficient: 0.38, profile_shift_coefficient: 0 }
export const SPROCKET_DEFAULTS: Record<string, number | boolean | string> = { number_of_teeth: 50, pitch: 0.375 * INCH, roller_diameter: 0.2 * INCH,
  thickness: 0.11 * INCH, sprocket_reference: 'ANSI 25' }
const DEFAULTS: Record<Kind, Record<string, number | boolean | string>> = { gear: GEAR_DEFAULTS, sprocket: SPROCKET_DEFAULTS }
/** SprocketFeature.py's SprocketReferenceRollerTable: [the task panel's name, pitch, roller diameter, thickness] in inches. */
export const SPROCKET_REFERENCES: [string, number, number, number][] = [
  ['ANSI 25', 0.250, 0.130, 0.110], ['ANSI 35', 0.375, 0.200, 0.168], ['ANSI 41', 0.500, 0.306, 0.227], ['ANSI 40', 0.500, 0.312, 0.284],
  ['ANSI 50', 0.625, 0.400, 0.343], ['ANSI 60', 0.750, 0.469, 0.459], ['ANSI 80', 1.000, 0.625, 0.575], ['ANSI 100', 1.250, 0.750, 0.692],
  ['ANSI 120', 1.500, 0.875, 0.924], ['ANSI 140', 1.750, 1.000, 0.924], ['ANSI 160', 2.000, 1.125, 1.156], ['ANSI 180', 2.250, 1.460, 1.301],
  ['ANSI 200', 2.500, 1.562, 1.389], ['ANSI 240', 3.000, 1.875, 1.738], ['Bicycle with derailleur', 0.500, 0.3125, 0.11],
  ['Bicycle without derailleur', 0.500, 0.3125, 0.084], ['ISO 606 06B', 0.375, 6.35 / 25.4, 5.2 / 25.4], ['ISO 606 08B', 0.500, 8.51 / 25.4, 7.0 / 25.4],
  ['ISO 606 10B', 0.625, 10.16 / 25.4, 9.1 / 25.4], ['ISO 606 12B', 0.750, 12.07 / 25.4, 11.1 / 25.4], ['ISO 606 16B', 1.000, 15.88 / 25.4, 16.2 / 25.4],
  ['ISO 606 20B', 1.250, 19.05 / 25.4, 18.5 / 25.4], ['ISO 606 24B', 1.500, 25.4 / 25.4, 24.1 / 25.4], ['Motorcycle 420', 0.500, 0.3125, 0.227],
  ['Motorcycle 425', 0.500, 0.3125, 0.284], ['Motorcycle 428', 0.500, 0.335, 0.284], ['Motorcycle 520', 0.625, 0.400, 0.227],
  ['Motorcycle 525', 0.625, 0.400, 0.284], ['Motorcycle 530', 0.625, 0.400, 0.343], ['Motorcycle 630', 0.750, 0.400, 0.343],
]
const TRANSACTION: Record<Kind, string> = { gear: 'Create involute gear', sprocket: 'Create Sprocket' }

// ── the shapes the server builds (`cad feature shape`), kept per feature list ────────────────────────────────
type Mesh = { faces: { name: string; points: number[]; index: number[] }[]; edges: { name: string; points: number[] }[] }
const meshes = new WeakMap<FeatureDoc, Map<string, Mesh | null>>()
const meshSubs = new Set<() => void>()
let meshTick = 0
/** The shape of one of the Body's objects as the server builds it (its wire, a binder's compound), in the part's frame;
 *  undefined while it is asked for, null when it has none. */
function meshOf(part: string, doc: FeatureDoc, f: Feature): Mesh | null | undefined {
  const cache = meshes.get(doc) ?? new Map<string, Mesh | null>()
  meshes.set(doc, cache)
  if (cache.has(f.name)) return cache.get(f.name)
  const slug = getState().slug
  if (!slug) return null
  cache.set(f.name, null)
  void api.featureShape(slug, part, [], f.name).then((r) => {
    const d = r.data ?? {}
    cache.set(f.name, r.exit > 2 || d.error ? null : ((d.shape as Mesh) ?? null))
    meshTick++
    for (const s of meshSubs) s()
  }).catch(() => undefined)
  return undefined
}
function useMeshTick() {
  const [, redraw] = useState(0)
  useEffect(() => { const f = () => redraw((n) => n + 1); meshSubs.add(f); return () => { meshSubs.delete(f) } }, [])
  return meshTick
}
const partMatrix = (b: Body | undefined) => { const m = new THREE.Matrix4(); if (b?.matrix?.length === 16) m.fromArray(b.matrix).transpose(); return m }
const SKETCH_EDGE = 0x212529                       // SketchEdgeColor, FreeCAD Light
const GOLD = 0xffd700, GOLD_LINE = 0xfa9600       // DefaultDatumColor 0xFFD70099 (60 % transparent), DefaultDatumLineColor
const SHAPE = 0xcccccc, LINE = 0x1a1a1a           // DefaultShapeColor, DefaultShapeLineColor
function wireObject(m: Mesh, color: number): THREE.Object3D {
  const g = new THREE.Group()
  for (const e of m.edges) {
    if (e.points.length < 6) continue
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(e.points, 3))
    g.add(new THREE.Line(geo, new THREE.LineBasicMaterial({ color, linewidth: 2 })))
  }
  return g
}
/** ViewProviderSubShapeBinder: a binder named "Binder…" (UseBinderStyle) in the datum's golden yellow, 60 % transparent,
 *  its lines orange; any other in the default shape colours. */
function binderObject(m: Mesh, name: string, selected: string | null): THREE.Object3D {
  const style = /^binder/i.test(name)
  const g = new THREE.Group()
  for (const f of m.faces) {
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(f.points, 3))
    geo.setIndex(f.index)
    geo.computeVertexNormals()
    g.add(new THREE.Mesh(geo, new THREE.MeshPhongMaterial({ color: selected ?? (style ? GOLD : SHAPE), transparent: style, opacity: style ? 0.4 : 1,
      depthWrite: !style, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 })))
  }
  for (const e of m.edges) {
    if (e.points.length < 6) continue
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(e.points, 3))
    g.add(new THREE.Line(geo, new THREE.LineBasicMaterial({ color: selected ?? (style ? GOLD_LINE : LINE), linewidth: 2 })))
  }
  return g
}

// ── the 3D view: every shown gear (as a sketch is shown, until a feature takes it) and every shown binder ─────────
let drawnKey = ''
function drawLast() {
  const s = getState(), view = getView()
  if (!view) return
  const rows: { part: string; doc: FeatureDoc; f: Feature }[] = []
  for (const [part, doc] of Object.entries(s.features)) for (const f of doc.features) {
    if (!isLast(f.type) || !featureVisible(s, part, f)) continue
    if (s.task?.kind === 'pdGear' && s.task.body === part && s.task.other === f.name) continue   // the panel draws it
    rows.push({ part, doc, f })
  }
  const got = rows.map((r) => meshOf(r.part, r.doc, r.f))
  const sel = rows.map((r) => s.featSel.includes(refOf(r.part, r.f.name)))
  const key = JSON.stringify([rows.map((r, i) => [r.part, r.f.name, !!got[i], bodyOfPart(s, r.part)?.matrix]), sel, s.selPrefs.color, meshTick])
  if (key === drawnKey) return
  drawnKey = key
  const g = new THREE.Group()
  rows.forEach((r, i) => {
    const m = got[i]
    if (!m) return
    const color = sel[i] ? s.selPrefs.color : null
    const o = isSubBinder(r.f.type) ? binderObject(m, r.f.name, color) : wireObject(m, color ? new THREE.Color(color).getHex() : SKETCH_EDGE)
    o.applyMatrix4(partMatrix(bodyOfPart(s, r.part)))
    g.add(o)
  })
  view.setHelper('pd-last', g.children.length ? g : null)
}
subscribe(drawLast)
meshSubs.add(drawLast)

/** A gear's wire as sketch geometry (straight segments along the server's polylines, in the profile's own plane), so the
 *  Pad and Pocket panels draw their preview from it as they do from a sketch's; the feature itself before it arrives. */
export function useProfile(part: string, doc: FeatureDoc | undefined, name: string, toLocal: (f: Feature) => THREE.Matrix4): Feature | undefined {
  const tick = useMeshTick()
  return useMemo(() => {
    const f = doc?.features.find((x) => x.name === name)
    if (!f || !doc || !isProfile2d(f.type)) return f
    const m = meshOf(part, doc, f)
    if (!m) return f
    const inv = toLocal(f).clone().invert()
    const geometry: unknown[] = []
    for (const e of m.edges) {
      const p = e.points
      for (let i = 0; i + 5 < p.length; i += 3) {
        const a = new THREE.Vector3(p[i], p[i + 1], p[i + 2]).applyMatrix4(inv), b = new THREE.Vector3(p[i + 3], p[i + 4], p[i + 5]).applyMatrix4(inv)
        geometry.push({ type: 'LineSegment', start: [a.x, a.y], end: [b.x, b.y] })
      }
    }
    return { ...f, geometry }
  }, [doc, name, tick])
}

// ── the commands ───────────────────────────────────────────────────────────────────────────────────────────────
type Pending = { part: string; name: string; kind: Kind }
let pending: Pending | null = null
/** CommandInvoluteGear / CommandSprocket: openTransaction, makeInvoluteGear('InvoluteGear') (a Part2DObjectPython put at
 *  the end of the active Body's Group, body.Group + [obj]), then setEdit: its panel on the new gear. OK writes it, Cancel
 *  writes nothing (reject's abortTransaction). With no active Body FreeCAD puts it in the document; here it needs one. */
export async function makeGear(kind: Kind) {
  const s = getState()
  if (!s.slug) { report('warn', `${kind === 'gear' ? 'Involute Gear' : 'Sprocket'}: make or open a document first`); return }
  const part = targetBody()
  if (!part || !s.features[part]) { await messageBox('warning', 'No active body', NO_BODY); return }
  pending = { part, name: nextName(s.features[part], kind === 'gear' ? 'InvoluteGear' : 'Sprocket'), kind }
  setState({ task: { kind: 'pdGear', body: part, other: pending.name }, selected: [], subSel: [] })
  showPanel('tasks')
}
/** setEdit on a gear (a double-click on its row): its panel with its values. */
export function editLast(part: string, f: Feature) {
  if (isProfile2d(f.type)) { setState({ task: { kind: 'pdGear', body: part, other: f.name, edit: true } }); showPanel('tasks'); return }
  if (isSubBinder(f.type)) { syncBinder(part, f); return }
}
/** ViewProviderSubShapeBinder::doubleClicked: updatePlacement(true), "Sync binder" around update(UpdateForced). The binder
 *  here is rebuilt from its Support on every build (only BindMode Synchronized is taken), so the sync rebuilds the Body and
 *  leaves no undo step, as FreeCAD's leaves none when nothing changed. */
function syncBinder(part: string, f: Feature) {
  report('msg', `${part}/${f.name}: synchronized with its support`)
  void loadFeatures()
}
/** setEdit(SelectObject): the objects its Support binds selected (their rows; an element by its object's row). */
function selectBound(part: string, f: Feature) {
  const objs = new Set<string>()
  for (const r of (Array.isArray(f.support) ? f.support : []) as unknown[]) {
    const o = typeof r === 'string' ? r.split('.')[0] : Array.isArray(r) ? String(r[0]) : ''
    if (o) objs.add(o)
  }
  setState({ featSel: [...objs].map((o) => refOf(part, o)), selected: [], subSel: [] })
}

/** CmdPartDesignSubShapeBinder: a new SubShapeBinder ("Binder", "Binder001", …) in the active Body (Body::addObject's
 *  place: after the Tip), its Support the selection (an element of the Body's shape as (feature, element), a feature's row
 *  whole; the active Body itself dropped, as links[link] skips pcActiveBody), and no panel: "Create Sub-Shape Binder". */
export async function subShapeBinder() {
  const s = getState()
  if (!s.slug) return
  const part = targetBody()
  if (!part || !s.features[part]) { await messageBox('warning', 'No active body', NO_BODY); return }
  const doc = s.features[part]
  const support: Ref[] = refsOfSelection(part, false)
  const name = nextName(doc, 'Binder')
  const after = insertAfter(doc)
  const done = await applyOps(part, [{ op: 'add', feature: { name, type: SUB_BINDER, ...(support.length ? { support } : {}) }, ...(after ? { after } : {}) }],
    { name: 'Create Sub-Shape Binder' })
  if (done) setState({ featSel: [refOf(part, name)], selected: [], subSel: [] })
}
/** Body::insertObject(feature, getNextSolidFeature(), after=false): before the first solid after the Tip (the end when
 *  none is), so a feature that is not a solid goes after the Tip and leaves it where it was. */
function insertAfter(doc: FeatureDoc): string | null {
  const names = doc.features.map((f) => f.name)
  const tip = doc.tip ? names.indexOf(doc.tip) : -1
  if (tip < 0) return names[names.length - 1] ?? null
  for (let i = tip + 1; i < doc.features.length; i++) if (isSolid(doc.features[i].type)) return doc.features[i - 1].name
  return names[names.length - 1] ?? null
}

// ── the gears' task panel (InvoluteGearFeature.ui, SprocketFeature.ui) ─────────────────────────────────────────
const PANEL_TITLE: Record<Kind, string> = { gear: 'Involute Parameter', sprocket: 'Sprocket Parameters' }
const PANEL_ICON: Record<Kind, IconName> = { gear: 'pd-gear', sprocket: 'pd-sprocket' }
export function GearTask({ part, name, edit }: { part: string; name: string; edit: boolean }) {
  const s = useStore((x) => x)
  const doc = s.features[part]
  const existing = edit ? doc?.features.find((f) => f.name === name) : undefined
  const fresh = useMemo(() => (!edit && pending?.part === part && pending.name === name ? pending : null), [part, name, edit])
  const kind: Kind = (existing ? kindOf(existing.type) : fresh?.kind) ?? 'gear'
  const defaults = DEFAULTS[kind]
  // transferFrom: the object's values (an expression's value as its number; kept as written while that field is untouched)
  const initial = useMemo(() => {
    const out: Record<string, unknown> = {}
    for (const [k, d] of Object.entries(defaults)) {
      const v = existing?.[k]
      out[k] = typeof d === 'number' ? (numberOf(v ?? d, doc?.params ?? {}) ?? d) : (v ?? d)
    }
    return out
  }, [part, name, edit])
  const [v, setV] = useState<Record<string, unknown>>(initial)
  const touched = useRef(new Set<string>())
  const set = (patch: Record<string, unknown>) => { for (const k of Object.keys(patch)) touched.current.add(k); setV((x) => ({ ...x, ...patch })) }
  // the properties the part file gets: a new gear what is not FreeCAD's default, an edit what was changed
  const props = (): Record<string, unknown> => {
    const out: Record<string, unknown> = {}
    for (const [k, d] of Object.entries(defaults)) {
      if (existing ? touched.current.has(k) && JSON.stringify(v[k]) !== JSON.stringify(initial[k]) : JSON.stringify(v[k]) !== JSON.stringify(d)) out[k] = v[k]
    }
    return out
  }
  const ops = (): FeatureOp[] => (existing ? [{ op: 'set', name, props: props() }] : [{ op: 'add', feature: { name, type: TYPE[kind], ...props() } }])
  // the wire as each value changes (assignValue: setattr, then Proxy.execute), drawn as the gear's own while the panel is open
  const [built, setBuilt] = useState<{ mesh: Mesh | null; error: string | null } | null>(null)
  const seq = useRef(0)
  useEffect(() => {
    const slug = getState().slug
    if (!slug || !doc) return
    const n = ++seq.current
    const t = setTimeout(async () => {
      try {
        const r = await api.featureShape(slug, part, ops(), name)
        if (n !== seq.current) return
        const d = r.data ?? {}
        setBuilt({ mesh: (d.shape as Mesh) ?? null, error: (d.error as string) ?? (r.exit > 2 ? String(d.message ?? r.text ?? 'failed') : null) })
      } catch (e) { if (n === seq.current) setBuilt({ mesh: null, error: String(e) }) }
    }, 120)
    return () => clearTimeout(t)
  }, [JSON.stringify(v)])
  const body = bodyOfPart(s, part)
  useEffect(() => {
    const view = getView()
    if (!view) return
    const g = built?.mesh ? wireObject(built.mesh, SKETCH_EDGE) : null
    if (g) g.applyMatrix4(partMatrix(body))
    view.setHelper('pd-gear-preview', g)
  }, [built, body?.matrix])
  useEffect(() => () => { getView()?.setHelper('pd-gear-preview', null) }, [])

  if (!doc) return <div className="tasks"><p className="hint">{part}: no feature list</p></div>
  const ok = async () => {
    // accept: transferTo, recompute, resetEdit; the transaction CommandInvoluteGear opened is the undo step
    closeTask()
    if (existing) {
      const p = props()
      if (Object.keys(p).length) await applyOps(part, [{ op: 'set', name, props: p }], { name: `Edit ${name}` })
      return
    }
    const done = await applyOps(part, ops(), { name: TRANSACTION[kind] })
    if (done) setState({ featSel: [refOf(part, name)], selected: [] })
  }
  const cancel = async () => {
    closeTask()
    // SprocketTaskPanel.reject removes the object, also one that was only being edited (removeObject, then abortTransaction
    // with no transaction open): FreeCAD 26.3 deletes an existing sprocket on Cancel ("Delete", undoable); the gear's reject
    // only resets the edit
    if (existing && kind === 'sprocket') await applyOps(part, [{ op: 'delete', name }], { name: 'Delete' })
  }
  const num = (k: string) => Number(v[k])
  const spin = (k: string, qf: string, min: number, max: number, step: number, dec: number) => (
    <input className="pdx-int" data-qf={qf} type="number" min={min} max={max} step={step} value={dec ? num(k).toFixed(dec) : num(k)}
      onChange={(e) => { const x = Number(e.target.value); if (Number.isFinite(x)) set({ [k]: dec ? x : Math.round(x) }) }} />)
  const field = (label: string, qf: string, control: ReactNode) => <label key={qf} className="tfield"><span data-qf={`label:${qf}`}>{label}</span>{control}</label>
  const yesNo = (k: string, qf: string) => (
    <QComboBox data-qf={qf} value={v[k] === true ? 'True' : 'False'} onChange={(e) => set({ [k]: e.target.value === 'True' })}>
      <option value="True">True</option><option value="False">False</option></QComboBox>)
  return (
    <div className="tasks">
      <div className="tbuttons pd-buttons">
        <button className="qbtn default" onClick={() => void ok()}>OK</button>
        <button className="qbtn" onClick={() => void cancel()}>Cancel</button>
        <button className="qbtn" onClick={() => setV((x) => ({ ...x }))}>Apply</button>
      </div>
      <TaskBox title={PANEL_TITLE[kind]} icon={PANEL_ICON[kind]}>
        <div className="pd-form" data-panel={kind}>
          {kind === 'gear' ? <>
            {field('Number of teeth', 'spinBox_NumberOfTeeth', spin('number_of_teeth', 'spinBox_NumberOfTeeth', 3, 9999, 1, 0))}
            {field('Module', 'Quantity_Modules', <QuantityBox value={num('modules')} dims={LENGTH} min={0} max={2000} step={2} decimals={undefined} onChange={(x) => set({ modules: x })} />)}
            {field('Pressure angle', 'Quantity_PressureAngle', <QuantityBox value={num('pressure_angle')} dims={ANGLE} min={0} max={90} step={2} onChange={(x) => set({ pressure_angle: x })} />)}
            {field('High precision', 'comboBox_HighPrecision', yesNo('high_precision', 'comboBox_HighPrecision'))}
            {field('External gear', 'comboBox_ExternalGear', yesNo('external_gear', 'comboBox_ExternalGear'))}
            {field('Addendum coefficient', 'doubleSpinBox_Addendum', spin('addendum_coefficient', 'doubleSpinBox_Addendum', 0, 5, 0.05, 2))}
            {field('Dedendum coefficient', 'doubleSpinBox_Dedendum', spin('dedendum_coefficient', 'doubleSpinBox_Dedendum', 0, 5, 0.05, 2))}
            {field('Root fillet coefficient', 'doubleSpinBox_RootFillet', spin('root_fillet_coefficient', 'doubleSpinBox_RootFillet', 0, 2, 0.02, 2))}
            {field('Profile shift coefficient', 'doubleSpinBox_ProfileShift', spin('profile_shift_coefficient', 'doubleSpinBox_ProfileShift', -3, 3, 0.1, 2))}
          </> : <>
            {field('Number of teeth', 'spinBox_NumberOfTeeth', spin('number_of_teeth', 'spinBox_NumberOfTeeth', 3, 9999, 1, 0))}
            {field('Sprocket reference', 'comboBox_SprocketReference', <QComboBox data-qf="comboBox_SprocketReference" value={String(v.sprocket_reference)} onChange={(e) => {
              // sprocketReferenceChanged: Pitch, RollerDiameter and Thickness from the table, in inches
              const r = SPROCKET_REFERENCES.find(([n]) => n === e.target.value)
              if (r) set({ sprocket_reference: r[0], pitch: r[1] * INCH, roller_diameter: r[2] * INCH, thickness: r[3] * INCH })
            }}>{SPROCKET_REFERENCES.map(([n]) => <option key={n} value={n}>{n}</option>)}</QComboBox>)}
            {field('Chain pitch', 'Quantity_Pitch', <QuantityBox key={`p${v.sprocket_reference}`} value={num('pitch')} dims={LENGTH} min={0.01 * INCH} max={2000 * INCH} step={0.001 * INCH} onChange={(x) => set({ pitch: x })} />)}
            {field('Chain roller diameter', 'Quantity_RollerDiameter', <QuantityBox key={`r${v.sprocket_reference}`} value={num('roller_diameter')} dims={LENGTH} min={0.01 * INCH} max={50 * INCH} step={0.01 * INCH} onChange={(x) => set({ roller_diameter: x })} />)}
            {field('Tooth width', 'Quantity_Thickness', <QuantityBox key={`t${v.sprocket_reference}`} value={num('thickness')} dims={LENGTH} min={0.01 * INCH} max={50 * INCH} step={0.01 * INCH} onChange={(x) => set({ thickness: x })} />)}
          </>}
          {built?.error && <p className="pd-error">{built.error}</p>}
        </div>
      </TaskBox>
    </div>
  )
}

// ── the menus ──────────────────────────────────────────────────────────────────────────────────────────────────
/** Part Design > Involute Gear and Sprocket (CommandInvoluteGear, CommandSprocket: IsActive with a document). */
export function gearEntries(hasDoc: boolean): { gear: Entry; sprocket: Entry } {
  return {
    gear: { label: 'Involute Gear', icon: 'pd-gear', cmd: 'PartDesign_InvoluteGear', disabled: !hasDoc, title: 'Creates or edits the involute gear definition', onSelect: () => void makeGear('gear') },
    sprocket: { label: 'Sprocket', icon: 'pd-sprocket', cmd: 'PartDesign_Sprocket', disabled: !hasDoc, title: 'Creates or edits the sprocket definition.', onSelect: () => void makeGear('sprocket') },
  }
}
export function subShapeBinderEntry(hasDoc: boolean): Entry {
  return { label: 'Sub-Shape Binder', icon: 'pd-subshape-binder', cmd: 'PartDesign_SubShapeBinder', disabled: !hasDoc, onSelect: () => void subShapeBinder(),
    title: 'Creates a reference to geometry from one or more objects, allowing it to be used inside or outside a body. It tracks relative placements, supports multiple geometry types (solids, faces, edges, vertices), and can work with objects in the same or external documents.' }
}
/** The tree's context menu of a gear or a binder, before the entries every object has (the real FreeCAD 26.3's:
 *  ui/scripts/fcpdlast.json): a Python feature has no Edit entry, a Part::Feature that is not a PartDesign feature no Set
 *  Tip, Toggle Suppressed or Set Face Colors. */
export function lastTreeEntries(part: string, f: Feature, na: (label: string, why: string, extra?: Partial<Exclude<Entry, 'sep'>>) => Entry, moveAfter: () => void): Entry[] {
  const own: Entry[] = []
  if (isSubBinder(f.type)) own.push(   // ViewProviderSubShapeBinder::setupContextMenu
    { label: 'Synchronize', onSelect: () => syncBinder(part, f) },
    { label: 'Select Bound Object', onSelect: () => selectBound(part, f) })
  own.push(na('Appearance per Face', 'face colours are the material\'s here'), 'sep')
  own.push(na('Move Object To…', 'a feature belongs to its part module', { icon: 'pd-move-feature' }),
    { label: 'Move Feature After…', icon: 'pd-move-in-tree', cmd: 'PartDesign_MoveFeatureInTree', onSelect: moveAfter }, 'sep',
    na('Toggle Freeze', 'parts rebuild from source; there is no recompute to freeze', { icon: 'freeze' }), 'sep')
  return own
}

// ── the property view (as the real FreeCAD 26.3 lists it: ui/scripts/fcpdlast.json) ──────────────────────────────
type P = { key: string; name: string; kind: 'length' | 'angle' | 'bool' | 'enum' | 'int' | 'float' | 'text'; items?: string[]; ro?: string }
const GEAR_ROWS: P[] = [
  { key: 'addendum_coefficient', name: 'Addendum Coefficient', kind: 'float' }, { key: 'dedendum_coefficient', name: 'Dedendum Coefficient', kind: 'float' },
  { key: 'external_gear', name: 'External Gear', kind: 'bool' }, { key: 'high_precision', name: 'High Precision', kind: 'bool' },
  { key: 'modules', name: 'Modules', kind: 'length' }, { key: 'number_of_teeth', name: 'Number Of Teeth', kind: 'int' },
  { key: 'pressure_angle', name: 'Pressure Angle', kind: 'angle' }, { key: 'profile_shift_coefficient', name: 'Profile Shift Coefficient', kind: 'float' },
  { key: 'root_fillet_coefficient', name: 'Root Fillet Coefficient', kind: 'float' },
]
const SPROCKET_ROWS: P[] = [
  { key: 'number_of_teeth', name: 'Number Of Teeth', kind: 'int' }, { key: 'pitch', name: 'Pitch', kind: 'length' },
  { key: 'roller_diameter', name: 'Roller Diameter', kind: 'length' }, { key: 'sprocket_reference', name: 'Sprocket Reference', kind: 'enum', items: SPROCKET_REFERENCES.map(([n]) => n) },
  { key: 'thickness', name: 'Thickness', kind: 'length' },
]
const BINDER_ROWS: P[] = [
  { key: 'support', name: 'Support', kind: 'text', ro: 'Support is read-only (SubShapeBinder sets it from the selection)' },
  { key: 'fuse', name: 'Fuse', kind: 'bool' }, { key: 'make_face', name: 'Make Face', kind: 'bool' }, { key: 'claim_children', name: 'Claim Children', kind: 'bool' },
  { key: 'relative', name: 'Relative', kind: 'bool' },
  { key: 'bind_mode', name: 'Bind Mode', kind: 'enum', items: ['Synchronized'], ro: 'Frozen and Detached keep a shape the part file cannot hold' },
  { key: 'partial_load', name: 'Partial Load', kind: 'bool' },
  { key: 'bind_copy_on_change', name: 'Bind Copy On Change', kind: 'enum', items: ['Disabled'], ro: 'copy on change needs a hidden document the part file does not have' },
  { key: 'refine', name: 'Refine', kind: 'bool' },
]
const OFFSET_ROWS: P[] = [
  { key: 'offset', name: 'Offset', kind: 'float' }, { key: 'offset_join_type', name: 'Offset Join Type', kind: 'enum', items: ['Arcs', 'Tangent', 'Intersection'] },
  { key: 'offset_fill', name: 'Offset Fill', kind: 'bool' }, { key: 'offset_open_result', name: 'Offset Open Result', kind: 'bool' },
  { key: 'offset_intersection', name: 'Offset Intersection', kind: 'bool' },
]
const BINDER_DEFAULTS: Record<string, unknown> = { fuse: false, make_face: true, offset: 0, offset_join_type: 'Arcs', offset_fill: false, offset_open_result: false,
  offset_intersection: false, claim_children: false, relative: true, bind_mode: 'Synchronized', partial_load: false, bind_copy_on_change: 'Disabled', refine: true }
/** DlgPropertyLink::formatLinks of a PropertyXLinkSubList: "Pad [Face6]", objects one after another. */
export function supportText(v: unknown): string {
  if (!Array.isArray(v)) return ''
  const groups = new Map<string, string[]>()
  const add = (o: string, sub: string) => { const g = groups.get(o) ?? []; if (sub) g.push(sub); groups.set(o, g) }
  for (const r of v) {
    if (typeof r === 'string') { const i = r.indexOf('.'); add(i > 0 ? r.slice(0, i) : r, i > 0 ? r.slice(i + 1) : '') }
    else if (Array.isArray(r) && typeof r[0] === 'string') for (const s of (Array.isArray(r[1]) ? r[1] : [r[1] ?? ''])) add(r[0], String(s))
  }
  return [...groups].map(([o, subs]) => (subs.length ? `${o} [${subs.join(' ')}]` : o)).join(' ')
}
const placementText = (f: Feature) => {
  const pl = (f.attached as { placement?: { position: number[]; rotation: number[] } } | undefined)?.placement
  if (!pl) return '[(0.00 0.00 1.00); 0.00°; (0.00 mm  0.00 mm  0.00 mm)]'
  const [x, y, z, w] = pl.rotation, ang = 2 * Math.acos(Math.max(-1, Math.min(1, w))), sn = Math.sqrt(Math.max(0, 1 - w * w))
  const axis = sn < 1e-9 ? [0, 0, 1] : [x / sn, y / sn, z / sn]
  return `[(${axis.map((c) => c.toFixed(2)).join(' ')}); ${(ang * 180 / Math.PI).toFixed(2)}°; (${pl.position.map((c) => `${c.toFixed(2)} mm`).join('  ')})]`
}
/** The Data tab of a gear, a sprocket or a Sub-Shape Binder: editable rows write through `cad feature set`. */
export function LastProps({ part, f, set, onRename }: { part: string; f: Feature; set(props: Record<string, unknown>): void; onRename(name: string): void }) {
  const s = useStore((x) => x)
  const doc = s.features[part]
  const vars = Object.fromEntries(Object.entries(doc.params).filter(([, x]) => typeof x === 'number').map(([k, x]) => [k, { value: x as number, dims: [0, 0, 0, 0, 0, 0, 0, 0] as quantity.Quantity['dims'] }]))
  const kind = kindOf(f.type)
  const dflt = kind ? DEFAULTS[kind] : BINDER_DEFAULTS
  const row = (p: P): ReactNode => {
    const x = p.key === 'support' ? supportText(f.support) : f[p.key] ?? dflt[p.key]
    if (p.ro) return <Row key={p.key} k={<span title={`Read-only: ${p.ro}`}>{p.name}</span>} v={String(x ?? '')} />
    if (p.kind === 'bool') return <EditRow key={p.key} k={p.name} value={x === true} type="bool" onCommit={(n) => set({ [p.key]: n })} />
    if (p.kind === 'enum') return <div key={p.key} className="prow" tabIndex={0}><span className="pk" style={propPad(0)}>{p.name}</span>
      <span className="pv"><QComboBox className="qselect-pv" value={String(x)} onChange={(e) => set({ [p.key]: e.target.value })}>{p.items!.map((o) => <option key={o}>{o}</option>)}</QComboBox></span></div>
    const n = numberOf(x, doc.params) ?? 0
    if (p.kind === 'int') return <EditRow key={p.key} k={p.name} value={n} type="int" onCommit={(y) => set({ [p.key]: Math.round(Number(y)) })} note={typeof x === 'string' ? `= ${x}` : undefined} />
    return <EditRow key={p.key} k={p.name} value={n} type="float" kind={p.kind === 'length' ? 'Length' : p.kind === 'angle' ? 'Angle' : null} vars={vars} owner={f.name}
      onCommit={(y) => set({ [p.key]: y })} onExpr={(text) => set({ [p.key]: text })} note={typeof x === 'string' ? `= ${x}` : undefined} />
  }
  const label = <EditRow key="label" k="Label" value={f.name} type="str" onCommit={(n) => onRename(String(n))} />
  if (isSubBinder(f.type)) return <>
    <Group title="Base">{BINDER_ROWS.map(row)}<Row k="Placement" v={placementText(f)} />{label}</Group>
    <Group title="Offsetting">{OFFSET_ROWS.map(row)}</Group>
  </>
  // AttachExtension's rows as an unattached Part2DObject shows them (Attacher Engine, Attachment Support, Map Mode), then
  // Base, then the object's own group, its rows in name order as the property view sorts a Python feature's
  // (a Part2DObject's AttacherType is AttachEnginePlane; the offset and path rows show once it is attached)
  const attached = !!(f.attachment_support as unknown[] | undefined)?.length
  const att = attachmentRows(f).map(([k, x]): [string, string] => [k, k === 'Attacher Engine' ? 'Engine Plane' : x])
    .filter(([k]) => attached || ['Attacher Engine', 'Attachment Support', 'Map Mode'].includes(k))
  return <>
    <Group title="Attachment">{att.map(([k, x]) => <Row key={k} k={k} v={x} />)}</Group>
    <Group title="Base"><Row k="Placement" v={placementText(f)} />{label}</Group>
    <Group title={kind === 'gear' ? 'Gear' : 'Sprocket'}>{(kind === 'gear' ? GEAR_ROWS : SPROCKET_ROWS).map(row)}</Group>
  </>
}

/** The tree: a gear is a profile, so the feature that takes it shows it under itself, as a sketch (claimChildren). */
export const profileTypes = (t: unknown) => isProfile2d(t)
void splitRef

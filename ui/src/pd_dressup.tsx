// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/PartDesign/Gui/Command.cpp: 2008 Jürgen Riegel (dressupGetSelected, finishDressupFeature, makeChamferOrFillet,
//     CmdPartDesignDraft, CmdPartDesignThickness)
//   src/Mod/PartDesign/Gui/TaskDressUpParameters.cpp: 2012 Jan Rheinländer (referenceSelected, setSelectionMode, deleteRef,
//     addAllEdges, the Remove and Add All Edges actions)
//   src/Mod/PartDesign/Gui/TaskFilletParameters.cpp: 2011 Juergen Riegel
//   src/Mod/PartDesign/Gui/TaskChamferParameters.cpp: 2011 Juergen Riegel
//   src/Mod/PartDesign/Gui/TaskDraftParameters.cpp: 2012 Jan Rheinländer
//   src/Mod/PartDesign/Gui/TaskThicknessParameters.cpp: 2015 Stefan Tröger
//   src/Mod/PartDesign/Gui/ViewProviderDressUp.cpp: 2012 Jan Rheinländer (highlightReferences, setErrorState)
//   src/Mod/PartDesign/Gui/StyleParameters.h: 2025 Kacper Donat (PreviewDressUpColor, PreviewShapeOpacity, PreviewErrorColor)
//   src/Mod/Part/Gui/ReferenceHighlighter.cpp: 2021 Werner Mayer (the magenta of a referenced element)
//   No copyright line in the file: src/Mod/PartDesign/Gui/TaskFilletParameters.ui, src/Mod/PartDesign/Gui/TaskChamferParameters.ui,
//     src/Mod/PartDesign/Gui/TaskDraftParameters.ui, src/Mod/PartDesign/Gui/TaskThicknessParameters.ui
// PartDesign's dress-up features, Fillet, Chamfer, Draft and Thickness (cad_agent/feature_dressup.py): the commands, their
// task panels and the property view. The page cannot build a fillet, so the panel asks the server for the feature built
// after its edits (`cad feature shape`, POST /api/<slug>/features/<part>/shape, nothing written) and draws what comes back:
// the base feature (the solid before it, FreeCAD's BaseFeature), whose faces and edges are picked by FreeCAD's names while
// Select is down, and the faces the feature makes as the preview overlay. OK writes it ("Make Fillet", one undo step).
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import * as THREE from 'three'
import { api, type Body, type FeatureOp } from './api'
import { getState, report, setState, useStore, type Feature, type FeatureDoc } from './store'
import { closeTask, getView, showPanel } from './actions'
import { type IconName } from './icons'
import { EditRow, Group, Row, TaskBox, cls, propPad } from './panels'
import { QuantityBox, LENGTH, ANGLE } from './qsb'
import { QComboBox } from './combo'
import { messageBox } from './msgbox'
import { applyOps, bodyOfPart, numberOf, refOf, setAttachPicker, SKETCH, targetBody, tempHidden } from './partdesign'
import * as quantity from './quantity'
import type { Entry } from './chrome'
import { allows, axisRefText, datumHover, parsePick, parseRow, type Allow, type Picked, type Ref } from './pd_pick'
import './partdesign.css'

export type DressKind = 'fillet' | 'chamfer' | 'draft' | 'thickness'
type Info = { type: string; label: string; icon: IconName; edges: boolean; faces: boolean; cmd: string; tip: string }
/** Each dress-up: FreeCAD's TypeId, the command, and what its panel picks (TaskDressUpParameters' selectEdges, selectFaces). */
export const DRESS: Record<DressKind, Info> = {
  fillet: { type: 'PartDesign::Fillet', label: 'Fillet', icon: 'pd-fillet', edges: true, faces: true, cmd: 'PartDesign_Fillet', tip: 'Applies a fillet to the selected edges or faces' },
  chamfer: { type: 'PartDesign::Chamfer', label: 'Chamfer', icon: 'pd-chamfer', edges: true, faces: true, cmd: 'PartDesign_Chamfer', tip: 'Applies a chamfer to the selected edges or faces' },
  draft: { type: 'PartDesign::Draft', label: 'Draft', icon: 'pd-draft', edges: false, faces: true, cmd: 'PartDesign_Draft', tip: 'Applies a draft to the selected faces' },
  thickness: { type: 'PartDesign::Thickness', label: 'Thickness', icon: 'pd-thickness', edges: false, faces: true, cmd: 'PartDesign_Thickness', tip: 'Applies thickness and removes the selected faces' },
}
export const kindOfType = (t: string): DressKind | null => (Object.keys(DRESS) as DressKind[]).find((k) => DRESS[k].type === t) ?? null
export const isDressUp = (t: string) => kindOfType(t) !== null
/** Whether a dress-up references one of names: its Base, a Draft's Neutral Plane or Pull Direction (Std_Delete's warning). */
export function dressUpUses(f: Feature, names: string[]): boolean {
  if (!isDressUp(f.type)) return false
  return ['base', 'neutral_plane', 'pull_direction'].some((k) => { const r = f[k]; const n = Array.isArray(r) ? r[0] : r; return typeof n === 'string' && names.includes(n) })
}
const CHAMFER_TYPES: [string, string][] = [['Equal distance', 'Equal distance'], ['Two distances', 'Two distances'], ['Distance and Angle', 'Distance and angle']]
/** Each kind's own properties and FreeCAD's defaults (FeatureFillet.cpp, FeatureChamfer.cpp, FeatureDraft.cpp, FeatureThickness.cpp). */
const DEFAULTS: Record<DressKind, Record<string, unknown>> = {
  fillet: { radius: 1, use_all_edges: false, refine: true },
  chamfer: { chamfer_type: 'Equal distance', size: 1, size2: 1, angle: 45, flip_direction: false, use_all_edges: false, refine: true },
  draft: { angle: 1.5, neutral_plane: null, pull_direction: null, reversed: false, refine: true },
  thickness: { value: 1, reversed: true, mode: 'Skin', join: 'Arc', intersection: false, refine: true },
}
const NO_BODY = 'In order to use PartDesign you need an active Body object in the document. Please make one active (double click) '
  + 'or create one.\n\nIf you have a legacy document with PartDesign objects without Body, use the migrate function in PartDesign '
  + 'to put them into a Body.'
const nextName = (doc: FeatureDoc, base: string) => {
  const names = new Set(doc.features.map((f) => f.name))
  if (!names.has(base)) return base
  for (let i = 1; ; i++) { const n = `${base}${String(i).padStart(3, '0')}`; if (!names.has(n)) return n }
}
/** The solid a new feature goes on: the Tip, or the solid before it when the Tip is a sketch, else the BaseFeature. */
function solidAtTip(doc: FeatureDoc): string | null {
  const names = doc.features.map((f) => f.name)
  const upto = doc.tip ? names.indexOf(doc.tip) : names.length - 1
  for (let i = upto; i >= 0; i--) if (doc.features[i].type !== SKETCH) return doc.features[i].name
  return doc.base ? 'BaseFeature' : null
}

// ── the commands (Command.cpp's makeChamferOrFillet, CmdPartDesignDraft, CmdPartDesignThickness) ────
type Pending = { part: string; name: string; base: string; refs: string[]; useAll: boolean }
let pending: Pending | null = null
/** dressupGetSelected + finishDressupFeature: the edges and faces selected on the Body's shape (its Tip) are the new
 *  feature's Base; the Body selected whole gives a Fillet or Chamfer every edge (UseAllEdges); nothing selected, the Tip with
 *  no element. Draft keeps the faces (FreeCAD also drops a face that is not a plane, cylinder or cone; here the feature says
 *  so when it is built), Thickness the faces. The panel opens on it; OK writes "Make Fillet", Cancel writes nothing. */
export async function dressUp(kind: DressKind) {
  const s = getState()
  const part = targetBody()
  if (!part || !s.features[part]) { await messageBox('warning', 'No active body', NO_BODY); return }
  const doc = s.features[part]
  const body = bodyOfPart(s, part)
  const own = body ? `${body.name}.` : '\u0000'
  const refs = s.subSel
  const bodies = new Set(refs.map((r) => r.slice(0, r.lastIndexOf('.'))))
  if (bodies.size > 1) { await messageBox('warning', 'Wrong selection', 'Select an edge, face, or body from a single body.'); return }
  if (refs.length && !refs[0].startsWith(own)) { await messageBox('warning', 'Selection is not in the active body', 'Select an edge, face, or body from an active body.'); return }
  const base = solidAtTip(doc)
  if (!base) { await messageBox('warning', 'Wrong selection', 'Shape of the selected part is empty'); return }
  let subs = refs.map((r) => r.slice(own.length))
  if (kind === 'draft' || kind === 'thickness') subs = subs.filter((n) => n.startsWith('Face')) // "filter out the edges"
  const whole = !refs.length && !!body && s.selected.includes(body.name)
  const useAll = whole && (kind === 'fillet' || kind === 'chamfer')
  pending = { part, name: nextName(doc, DRESS[kind].label), base, refs: subs, useAll }
  setState({ subSel: [], selected: [], task: { kind, body: part, other: pending.name } }) // Gui.Selection().clearSelection()
  showPanel('tasks')
}
/** Std_Edit / a double-click on a dress-up's row: its panel on the feature ("Edit Fillet"). */
export function editDressUp(part: string, f: Feature) {
  const kind = kindOfType(f.type)
  if (!kind) return
  setState({ task: { kind, body: part, other: f.name, edit: true } })
  showPanel('tasks')
}

// ── the shapes the server builds, drawn and picked here ──────────────────────
type Mesh = { faces: { name: string; points: number[]; index: number[]; kind?: string }[]; edges: { name: string; points: number[]; kind?: string | null }[] }
type Built = { shape: Mesh | null; base: Mesh | null; base_name: string | null; error: string | null }
const partMatrix = (b: Body | undefined) => { const m = new THREE.Matrix4(); if (b?.matrix?.length === 16) m.fromArray(b.matrix).transpose(); return m }
const MAGENTA = new THREE.Color(1, 0, 1) // ReferenceHighlighter's elementColor and PreviewDressUpColor
const SELECTED = new THREE.Color(0x1cad1c) // the selection colour (View > Selection colour, FreeCAD Light)
const SHAPE = new THREE.Color(0xcccccc), LINE = new THREE.Color(0x1a1a1a)
/** The solid as faces and edges; with pick, each named for helperPicker, an edge over its face (pickPriority). */
function meshObject(m: Mesh, opts: { pick: boolean; marked: Set<string>; current: Set<string>; only?: Set<string>; color?: THREE.Color; opacity?: number; edgeColor?: THREE.Color }) {
  const g = new THREE.Group()
  for (const f of m.faces) {
    if (opts.only && !opts.only.has(f.name)) continue
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(f.points, 3))
    geo.setIndex(f.index)
    geo.computeVertexNormals()
    const color = opts.current.has(f.name) ? SELECTED : opts.marked.has(f.name) ? MAGENTA : opts.color ?? SHAPE
    const op = opts.opacity ?? 1
    const mesh = new THREE.Mesh(geo, new THREE.MeshPhongMaterial({ color, transparent: op < 1, opacity: op, depthWrite: op >= 1, side: THREE.DoubleSide,
      polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 }))
    if (opts.pick) mesh.userData.pickName = f.name
    g.add(mesh)
  }
  for (const e of m.edges) {
    if (e.points.length < 6) continue
    if (opts.only && !opts.marked.has(e.name) && opts.edgeColor === undefined) continue
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(e.points, 3))
    const color = opts.current.has(e.name) ? SELECTED : opts.marked.has(e.name) ? MAGENTA : opts.edgeColor ?? LINE
    const line = new THREE.Line(geo, new THREE.LineBasicMaterial({ color, linewidth: 2 }))
    if (opts.pick) { line.userData.pickName = e.name; line.userData.pickPriority = 1 }
    g.add(line)
  }
  return g
}
/** The faces of the feature that the base does not have: DressUp::updatePreviewShape's generated faces, matched by area and
 *  centre (the page has no shape history). */
function generated(shape: Mesh, base: Mesh): Set<string> {
  const key = (f: { points: number[]; index: number[] }) => {
    let a = 0; const c = [0, 0, 0]
    for (let i = 0; i < f.index.length; i += 3) {
      const p = [0, 1, 2].map((k) => new THREE.Vector3().fromArray(f.points, f.index[i + k] * 3))
      const ar = p[1].clone().sub(p[0]).cross(p[2].clone().sub(p[0])).length() / 2
      a += ar
      for (const q of p) { c[0] += (q.x * ar) / 3; c[1] += (q.y * ar) / 3; c[2] += (q.z * ar) / 3 }
    }
    return a > 0 ? [a, c[0] / a, c[1] / a, c[2] / a].map((x) => Math.round(x * 100) / 100).join(',') : ''
  }
  const had = new Set(base.faces.map(key))
  return new Set(shape.faces.filter((f) => !had.has(key(f))).map((f) => f.name))
}

// ── the task panel (TaskDlgDressUpParameters with TaskFilletParameters, …) ─────────────────────
type Mode = 'none' | 'refSel' | 'plane' | 'line'
const refText = (r: unknown) => (r == null ? '' : typeof r === 'string' ? r : Array.isArray(r) ? `${r[0]}:${Array.isArray(r[1]) ? r[1].join(',') : r[1]}` : '')

export function DressUpTask({ kind, part, name, edit }: { kind: DressKind; part: string; name: string; edit: boolean }) {
  const s = useStore((x) => x)
  const info = DRESS[kind]
  const doc = s.features[part]
  const existing = edit ? doc?.features.find((f) => f.name === name) : undefined
  const fresh = useMemo(() => (!edit && pending?.part === part && pending.name === name ? pending : null), [part, name, edit])
  const baseName = existing ? (Array.isArray(existing.base) ? String(existing.base[0]) : solidAtTip(doc!) ?? '') : fresh?.base ?? (doc ? solidAtTip(doc) ?? '' : '')
  const num = (v: unknown, d: number) => numberOf(v, doc?.params ?? {}) ?? d
  const initial = useMemo(() => {
    const d = DEFAULTS[kind], src: Record<string, unknown> = existing ?? {}
    const out: Record<string, unknown> = {}
    for (const [k, dv] of Object.entries(d)) out[k] = typeof dv === 'number' ? num(src[k], dv) : (src[k] ?? dv)
    if (fresh?.useAll) out.use_all_edges = true
    return out
  }, [part, name, edit])
  const [v, setV] = useState<Record<string, unknown>>(initial)
  const [refs, setRefs] = useState<string[]>(() => (existing && Array.isArray(existing.base) ? (existing.base[1] as string[]) ?? [] : fresh?.refs ?? []))
  // setSelectionMode(refSel) when the list starts empty; Draft also does when it has no pull direction (TaskDraftParameters)
  const [mode, setMode] = useState<Mode>(() => (initial.use_all_edges === true ? 'none' : !refs.length || (kind === 'draft' && !(existing?.pull_direction)) ? 'refSel' : 'none'))
  const [current, setCurrent] = useState<string[]>([])  // the list's selected rows, highlighted in the 3D view
  const [showFinal, setShowFinal] = useState(false)
  const [overlay, setOverlay] = useState(true)
  const [built, setBuilt] = useState<Built | null>(null)
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null)
  const set = (patch: Record<string, unknown>) => setV((x) => ({ ...x, ...patch }))
  const body = bodyOfPart(s, part)
  const useAll = v.use_all_edges === true

  // the feature as the panel has it, as ops `cad feature shape` and OK take
  const props = (): Record<string, unknown> => {
    const out: Record<string, unknown> = { base: [baseName, refs] }
    for (const [k, dv] of Object.entries(DEFAULTS[kind])) if (JSON.stringify(v[k]) !== JSON.stringify(dv) || (existing && k in existing)) out[k] = v[k]
    return out
  }
  const ops = (): FeatureOp[] => {
    if (existing) return [{ op: 'set', name, props: props() }]
    const after = doc?.tip ?? doc?.features[doc.features.length - 1]?.name ?? null
    return [{ op: 'add', feature: { name, type: info.type, ...props() }, after }, { op: 'tip', name }]
  }
  // Recompute: the server builds it after every change (TaskDressUpParameters::updateFeature's recomputeFeature)
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
        // a build that fails before its base keeps the base shown (and pickable) as it was
        setBuilt((old) => ({ shape: (d.shape as Mesh) ?? null, base: (d.base as Mesh) ?? old?.base ?? null, base_name: (d.base_name as string) ?? old?.base_name ?? null,
          error: (d.error as string) ?? (r.exit > 2 ? String(d.message ?? r.text ?? "failed") : null) }))
      } catch (e) { if (n === seq.current) setBuilt({ shape: null, base: null, base_name: null, error: String(e) }) }
    }, 150)
    return () => clearTimeout(t)
  }, [JSON.stringify(v), JSON.stringify(refs)])
  // UseAllEdges from a whole-Body selection: every edge in the list (dressupGetSelected adds Edge1 … EdgeN)
  useEffect(() => { if (fresh?.useAll && built?.base && !refs.length) setRefs(built.base.edges.map((e) => e.name)) }, [built?.base])

  // the 3D view: the Body hidden while the panel is open; the base shown (showPreviousFeature) with the references in magenta,
  // pickable while selecting; the faces the feature makes as the overlay, or the result with Show final result
  useEffect(() => {
    const b = body?.name
    if (!b) return
    const was = getState().hidden.includes(b)
    if (!was) { tempHidden.add(b); setState((x) => ({ hidden: [...x.hidden, b] })) }     // its datums stay shown
    return () => { if (!was) { setState((x) => ({ hidden: x.hidden.filter((n) => n !== b) })); tempHidden.delete(b) } }
  }, [body?.name])
  useEffect(() => {
    const view = getView()
    if (!view) return
    const g = new THREE.Group()
    const marked = new Set(mode === 'refSel' || current.length ? refs : [])
    const cur = new Set(current)
    const picking = mode !== 'none'
    const final = showFinal && !picking && built?.shape && !built.error
    if (final) g.add(meshObject(built!.shape!, { pick: false, marked: new Set(), current: new Set() }))
    else if (built?.base) g.add(meshObject(built.base, { pick: picking, marked, current: cur }))
    if (overlay && !picking && !final && built?.shape && built.base && !built.error) {
      const gen = generated(built.shape, built.base)
      if (gen.size) g.add(meshObject(built.shape, { pick: false, marked: new Set(), current: new Set(), only: gen, color: MAGENTA, opacity: 0.2, edgeColor: MAGENTA }))
    }
    if (built?.error && built.base && overlay) {   // setErrorState: PreviewErrorColor at PreviewErrorOpacity
      g.add(meshObject(built.base, { pick: false, marked: new Set(), current: new Set(), color: new THREE.Color(1, 0, 0), opacity: 0.05, edgeColor: new THREE.Color(1, 0, 0) }))
    }
    g.applyMatrix4(partMatrix(body))
    view.setHelper('pd-dressup', g.children.length ? g : null)
  }, [built, mode, refs, current, showFinal, overlay, body?.matrix])
  useEffect(() => () => { const w = getView(); if (w) { w.setHelper('pd-dressup', null); w.helperPicker = null } }, [])

  // picking: TaskDressUpParameters::referenceSelected toggles the element; Draft's Neutral Plane and Pull Direction take one,
  // a datum or an LCS's feature too. The gate is setSelectionMode's ReferenceSelection (pd_pick.tsx): refSel the kind's edges
  // and faces; Neutral Plane EDGE | FACE | PLANAR, Pull Direction EDGE | PLANAR (TaskDraftParameters)
  useEffect(() => {
    const view = getView()
    if (!view) return
    const kinds: Record<string, string | null | undefined> = {}
    for (const f of built?.base?.faces ?? []) kinds[f.name] = f.kind
    for (const e of built?.base?.edges ?? []) kinds[e.name] = e.kind
    const allow: Allow = mode === 'refSel' ? { edge: info.edges, face: info.faces } : mode === 'plane' ? { edge: true, face: true, planar: true } : { edge: true, planar: true }
    const parse = (name: string): Picked | null => (/^(Face|Edge|Vertex)\d+$/.test(name) ? { obj: baseName, sub: name, kind: 'element', type: kinds[name] ?? '', ref: [baseName, name] }
      : parsePick(part, name))
    const slug = getState().slug ?? 'Unnamed'
    view.helperGate = mode === 'none' ? null : (name) => {
      const p = parse(name)
      if (p && (mode !== 'refSel' || p.kind === 'element') && allows(p, allow)) return true
      return `Not allowed: ${slug}.${part}.${p ? (p.sub ? `${p.obj}.${p.sub}` : p.obj) : name} `
    }
    view.helperPicker = mode === 'none' ? null : (name: string) => {
      const p = parse(name)
      if (!p) return
      if (mode === 'refSel') {
        const sub = p.sub
        setRefs((r) => (r.includes(sub) ? r.filter((x) => x !== sub) : [...r, sub]))
        setCurrent([])
      } else if (mode === 'plane') {
        set({ neutral_plane: p.ref })
        // TaskDraftParameters::onSelectionChanged: the button stays down, a later pick replaces it
      } else if (mode === 'line') {
        set({ pull_direction: p.ref })
      }
    }
    // the tree's rows through the same gate (an Origin plane or axis, a datum: the panel does not show the Origin)
    setAttachPicker(mode === 'plane' || mode === 'line' ? (row) => {
      const p = parseRow(part, row)
      if (!p || !allows(p, allow)) { setState({ gateMsg: 'Selection not allowed by filter' }); return }
      set(mode === 'plane' ? { neutral_plane: p.ref } : { pull_direction: p.ref })
    } : null)
    view.helperHover = mode === 'none' ? datumHover : (name, refused) => {
      const p = name ? parse(name) : null
      setState({ gateMsg: refused, preselected: p ? part : null, preSub: p ? `${part}.${p.sub ? `${p.obj}.${p.sub}` : p.obj}` : null, prePoint: null })
    }
    return () => { const w = getView(); if (w) { w.helperPicker = null; w.helperGate = null; w.helperHover = datumHover } setAttachPicker(null); setState({ gateMsg: null }) }
  }, [mode, baseName, built?.base])

  if (!doc) return <div className="tasks"><p className="hint">{part}: no feature list</p></div>
  const removeSelected = () => { setRefs((r) => r.filter((x) => !current.includes(x))); setCurrent([]) }
  const addAllEdges = () => { if (built?.base) setRefs((r) => [...r, ...built.base!.edges.map((e) => e.name).filter((n) => !r.includes(n))]) }
  const keys = (e: React.KeyboardEvent) => {
    if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); removeSelected() }
    if (e.key.toLowerCase() === 'a' && e.ctrlKey && e.shiftKey && info.edges) { e.preventDefault(); addAllEdges() }
  }
  const ok = async () => {
    if (!refs.length) report('warn', `Empty ${info.label.toLowerCase()} created!`)
    // FreeCAD keeps a feature that does not build (an empty Fillet: "Fillet not possible on selected shapes") and marks it
    // in error; a part file here only takes a Body that builds, so the panel says why and stays open (PARITY.md)
    if (built?.error) { await messageBox('warning', 'Input error', built.error); return }
    closeTask()
    if (existing) {
      const p = props()
      const was = (k: string) => (k === 'base' ? existing.base : existing[k] ?? DEFAULTS[kind][k])
      const changed = Object.fromEntries(Object.entries(p).filter(([k, x]) => JSON.stringify(x) !== JSON.stringify(was(k))))
      if (Object.keys(changed).length) await applyOps(part, [{ op: 'set', name, props: changed }], { name: `Edit ${name}` })
      return
    }
    const done = await applyOps(part, ops(), { name: `Make ${info.label}` })
    if (done) setState({ featSel: [refOf(part, name)], selected: [] })
  }
  const lengthBox = (key: string, label: string, min = 0) => (
    <label className="tfield"><span>{label}</span><QuantityBox value={Number(v[key])} dims={LENGTH} min={min} onChange={(x) => set({ [key]: x })} /></label>)
  const angleBox = (key: string, label: string, min: number, max: number) => (
    <label className="tfield"><span>{label}</span><QuantityBox value={Number(v[key])} dims={ANGLE} min={min} max={max} onChange={(x) => set({ [key]: x })} /></label>)
  const select = mode === 'refSel'
  return (
    <div className="tasks" onKeyDown={keys}>
      <div className="tbuttons pd-buttons"><button className="qbtn default" onClick={() => void ok()}>OK</button><button className="qbtn" onClick={closeTask}>Cancel</button></div>
      <TaskBox title={`${info.label} Parameters`} icon={info.icon}>
        <div className="pd-form">
          <button className={cls('qbtn', 'pd-refsel', select && 'on')} aria-pressed={select} disabled={useAll} title="Toggles between selection and preview mode"
            onClick={() => setMode(select ? 'none' : 'refSel')}>{select ? 'Confirm Selection' : 'Select'}</button>
          <div className={cls('pd-reflist', useAll && 'off')} role="listbox" tabIndex={0} aria-disabled={useAll}
            title={'- select an item to highlight it\n- double-click on an item to see the ' + (kind === 'fillet' ? 'fillets' : kind === 'chamfer' ? 'chamfers' : kind === 'draft' ? 'drafts' : 'features')}
            onContextMenu={(e) => { e.preventDefault(); if (!useAll) setMenu({ x: e.clientX, y: e.clientY }) }}>
            {refs.map((r) => <div key={r} role="option" aria-selected={current.includes(r)} className={cls('pd-mode', current.includes(r) && 'sel')}
              onClick={(e) => { if (useAll) return; setCurrent((c) => (e.ctrlKey || e.metaKey ? (c.includes(r) ? c.filter((x) => x !== r) : [...c, r]) : [r])); if (mode === 'none') setMode('refSel') }}
              onDoubleClick={() => { setMode('none'); setCurrent([]) }}>{r}</div>)}
          </div>
          {menu && <div className="pd-ctx" style={{ left: menu.x, top: menu.y }} onMouseLeave={() => setMenu(null)}>
            <div className="pd-ctx-item" onClick={() => { removeSelected(); setMenu(null) }}><span>Remove</span><span className="kbd">Del</span></div>
            {info.edges && <div className="pd-ctx-item" onClick={() => { addAllEdges(); setMenu(null) }}><span>Add All Edges</span><span className="kbd">Ctrl+Shift+A</span></div>}
          </div>}
          {kind === 'fillet' && <>
            {lengthBox('radius', 'Radius')}
            <label className="tcheck"><input type="checkbox" checked={useAll} onChange={(e) => { set({ use_all_edges: e.target.checked }); if (e.target.checked) setMode('none') }} /> Use all edges</label>
          </>}
          {kind === 'chamfer' && <>
            <div className="tfield"><span>Type</span><QComboBox value={String(v.chamfer_type)} onChange={(e) => set({ chamfer_type: e.target.value })}>
              {CHAMFER_TYPES.map(([k, t]) => <option key={k} value={k}>{t}</option>)}</QComboBox>
              <button className={cls('qbtn', 'pd-flip', v.flip_direction === true && 'on')} aria-pressed={v.flip_direction === true} disabled={v.chamfer_type === 'Equal distance'}
                title="Flips the direction" onClick={() => set({ flip_direction: !v.flip_direction })}><img src="freecad-icons/PartDesign_Flip_Direction.svg" alt="" width={16} height={16} /></button></div>
            {lengthBox('size', 'Size')}
            <label className="tcheck"><input type="checkbox" checked={useAll} onChange={(e) => { set({ use_all_edges: e.target.checked }); if (e.target.checked) setMode('none') }} /> Use all edges</label>
            {v.chamfer_type === 'Two distances' && lengthBox('size2', 'Size 2')}
            {v.chamfer_type === 'Distance and Angle' && angleBox('angle', 'Angle', 0, 180)}
          </>}
          {kind === 'draft' && <>
            {angleBox('angle', 'Draft angle', -90, 90)}
            <div className="tfield"><button className={cls('qbtn', mode === 'plane' && 'on')} aria-pressed={mode === 'plane'} onClick={() => setMode(mode === 'plane' ? 'none' : 'plane')}
              title="A planar face, or an edge normal to the pull direction, of the base">Neutral Plane</button><input readOnly data-qf="linePlane" value={axisRefText(doc, v.neutral_plane as Ref)} /></div>
            <div className="tfield"><button className={cls('qbtn', mode === 'line' && 'on')} aria-pressed={mode === 'line'} onClick={() => setMode(mode === 'line' ? 'none' : 'line')}
              title="A straight edge of the base">Pull Direction</button><input readOnly data-qf="lineLine" value={axisRefText(doc, v.pull_direction as Ref)} /></div>
            <label className="tcheck"><input type="checkbox" checked={v.reversed === true} onChange={(e) => set({ reversed: e.target.checked })} /> Reverse pull direction</label>
          </>}
          {kind === 'thickness' && <>
            {lengthBox('value', 'Thickness')}
            <label className="tfield"><span>Mode</span><QComboBox value={String(v.mode)} onChange={(e) => set({ mode: e.target.value })}>
              <option value="Skin">Skin</option><option value="RectoVerso">Recto verso</option></QComboBox></label>
            <label className="tfield"><span>Join type</span><QComboBox value={String(v.join)} onChange={(e) => set({ join: e.target.value })}>
              <option value="Arc">Arc</option><option value="Intersection">Intersection</option></QComboBox></label>
            <label className="tcheck"><input type="checkbox" checked={v.intersection === true} onChange={(e) => set({ intersection: e.target.checked })} /> Intersection</label>
            <label className="tcheck" title={v.mode === 'RectoVerso' ? 'Recto verso applies the thickness equally to both sides' : undefined}>
              <input type="checkbox" checked={v.reversed === true} disabled={v.mode === 'RectoVerso'} onChange={(e) => set({ reversed: e.target.checked })} /> Make thickness inwards</label>
          </>}
          {built?.error && <p className="pd-error">{built.error}</p>}
        </div>
      </TaskBox>
      <TaskBox title="Preview" icon={info.icon}>
        <label className="tcheck"><input type="checkbox" checked={showFinal} onChange={(e) => setShowFinal(e.target.checked)} /> Show final result</label>
        <label className="tcheck"><input type="checkbox" checked={overlay} onChange={(e) => setOverlay(e.target.checked)} /> Show preview overlay</label>
      </TaskBox>
    </div>
  )
}

// ── the property view: FreeCAD's groups and rows for each, as its PropertyEditor lists them ───────────
type P = { key: string; name: string; kind: 'length' | 'angle' | 'bool' | 'enum' | 'text'; items?: string[]; ro?: (f: Feature) => string | null }
const label: P = { key: 'name', name: 'Label', kind: 'text' }
const baseRow: P = { key: 'base', name: 'Base', kind: 'text', ro: () => 'picked in the task panel (double-click the feature)' }
const supportT: P = { key: 'support_transform', name: 'Support Transform', kind: 'bool', ro: () => 'for the patterns, which are not here yet' }
const suppressed: P = { key: 'suppressed', name: 'Suppressed', kind: 'bool', ro: () => 'FEATURES has no suppressed state' }
const partDesign: [string, P[]] = ['Part Design', [{ key: 'refine', name: 'Refine', kind: 'bool' }, { key: 'fuzzy_tolerance', name: 'Fuzzy Tolerance', kind: 'text', ro: () => 'the operations run at OCCT\'s own tolerance' }]]
function groupsOf(kind: DressKind): [string, P[]][] {
  if (kind === 'fillet') return [['Base', [baseRow, supportT, label, suppressed]], ['Fillet', [{ key: 'radius', name: 'Radius', kind: 'length' }, { key: 'use_all_edges', name: 'Use All Edges', kind: 'bool' }]], partDesign]
  if (kind === 'chamfer') {
    const ct = (f: Feature) => String(f.chamfer_type ?? 'Equal distance')
    return [['Base', [baseRow, supportT, label, suppressed]], ['Chamfer', [{ key: 'chamfer_type', name: 'Chamfer Type', kind: 'enum', items: CHAMFER_TYPES.map(([k]) => k) },
      { key: 'size', name: 'Size', kind: 'length' }, { key: 'size2', name: 'Size2', kind: 'length', ro: (f) => (ct(f) === 'Two distances' ? null : 'Chamfer Type is not Two distances') },
      { key: 'angle', name: 'Angle', kind: 'angle', ro: (f) => (ct(f) === 'Distance and Angle' ? null : 'Chamfer Type is not Distance and Angle') },
      { key: 'flip_direction', name: 'Flip Direction', kind: 'bool' }, { key: 'use_all_edges', name: 'Use All Edges', kind: 'bool' }]], partDesign]
  }
  if (kind === 'draft') return [['Base', [{ key: 'angle', name: 'Angle', kind: 'angle' }, { key: 'reversed', name: 'Reversed', kind: 'bool' }, baseRow, supportT, label, suppressed]],
    ['Draft', [{ key: 'neutral_plane', name: 'Neutral Plane', kind: 'text', ro: () => 'picked in the task panel' }, { key: 'pull_direction', name: 'Pull Direction', kind: 'text', ro: () => 'picked in the task panel' }]], partDesign]
  return [['Base', [baseRow, supportT, label, suppressed]], partDesign, ['Thickness', [{ key: 'value', name: 'Value', kind: 'length' }, { key: 'mode', name: 'Mode', kind: 'enum', items: ['Skin', 'Pipe', 'RectoVerso'] },
    { key: 'join', name: 'Join', kind: 'enum', items: ['Arc', 'Intersection'] }, { key: 'reversed', name: 'Reversed', kind: 'bool' }, { key: 'intersection', name: 'Intersection', kind: 'bool' }]]]
}
/** The Data tab for a dress-up: editable rows write through `cad feature set` ("Edit Fillet.Radius"). */
export function DressUpProps({ part, f, set, onRename }: { part: string; f: Feature; set(props: Record<string, unknown>): void; onRename(name: string): void }) {
  const s = useStore((x) => x)
  const kind = kindOfType(f.type)!
  const doc = s.features[part]
  const vars = Object.fromEntries(Object.entries(doc.params).filter(([, x]) => typeof x === 'number').map(([k, x]) => [k, { value: x as number, dims: [0, 0, 0, 0, 0, 0, 0, 0] as quantity.Quantity['dims'] }]))
  const qtext = (n: number | null, dims: quantity.Quantity['dims']) => (n === null ? '?' : quantity.userString({ value: n, dims }).text)
  const value = (p: P): unknown => (p.key === 'name' ? f.name : p.key === 'base' ? (Array.isArray(f.base) ? `${f.base[0]} [${(f.base[1] as string[]).join(', ')}]` : '')
    : p.key === 'neutral_plane' || p.key === 'pull_direction' ? refText(f[p.key]) : f[p.key] ?? DEFAULTS[kind][p.key] ?? (p.kind === 'bool' ? false : p.key === 'fuzzy_tolerance' ? 0 : ''))
  const row = (p: P): ReactNode => {
    const x = value(p)
    const why = p.ro?.(f) ?? null
    const shown = p.kind === 'length' ? qtext(numberOf(x, doc.params), LENGTH) + (typeof x === 'string' ? `  (= ${x})` : '')
      : p.kind === 'angle' ? qtext(numberOf(x, doc.params), ANGLE) : p.kind === 'bool' ? String(x === true) : String(x ?? '')
    if (why) return <Row key={p.key} k={<span title={`Read-only: ${why}`}>{p.name}</span>} v={shown} />
    if (p.key === 'name') return <EditRow key={p.key} k={p.name} value={f.name} type="str" onCommit={(n) => onRename(String(n))} />
    if (p.kind === 'bool') return <EditRow key={p.key} k={p.name} value={x === true} type="bool" onCommit={(n) => set({ [p.key]: n })} />
    if (p.kind === 'enum') return <div key={p.key} className="prow" tabIndex={0}><span className="pk" style={propPad(0)}>{p.name}</span>
      <span className="pv"><QComboBox className="qselect-pv" value={String(x)} onChange={(e) => set({ [p.key]: e.target.value })}>{p.items!.map((o) => <option key={o}>{o}</option>)}</QComboBox></span></div>
    const n = numberOf(x, doc.params) ?? 0
    return <EditRow key={p.key} k={p.name} value={n} type="float" kind={p.kind === 'length' ? 'Length' : 'Angle'} vars={vars} owner={f.name}
      onCommit={(y) => set({ [p.key]: y })} onExpr={(text) => set({ [p.key]: text })} note={typeof x === 'string' ? `= ${x}` : undefined} />
  }
  return <>{groupsOf(kind).map(([g, defs]) => <Group key={g} title={g}>{defs.map(row)}</Group>)}</>
}

// ── menus and toolbar: Workbench.cpp's "Dress-Up Features" (Defeaturing is not here yet) ─────────────
export function dressUpEntries(hasDoc: boolean): Entry[] {
  return (Object.keys(DRESS) as DressKind[]).map((k) => ({ label: DRESS[k].label, icon: DRESS[k].icon, cmd: DRESS[k].cmd, disabled: !hasDoc, title: DRESS[k].tip, onSelect: () => void dressUp(k) }))
}


// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/PartDesign/Gui/Command.cpp: 2008 Jürgen Riegel (CmdPartDesignShapeBinder)
//   src/Mod/PartDesign/Gui/TaskShapeBinder.cpp: 2015 Stefan Tröger (updateUI, setupButtonGroup, supportChanged,
//     onButtonToggled, onSelectionChanged, referenceSelected, deleteItem, accept)
//   src/Mod/PartDesign/Gui/ViewProviderShapeBinder.cpp: 2015 Stefan Tröger (the golden datum look, highlightReferences,
//     setEdit, "Edit Shape Binder")
//   src/Mod/PartDesign/App/ShapeBinder.cpp: 2015 Stefan Tröger (getFilteredReferences, buildShapeFromReferences)
//   No copyright line in the file: src/Mod/PartDesign/Gui/TaskShapeBinder.ui
// PartDesign's ShapeBinder (cad_agent/feature_binder.py): a Body feature that copies geometry another object has — a Pad
// or a Pocket whole or by its faces and edges, a sketch, another binder, a PartDesign datum, or one of the Origin's
// planes, lines and points. The command (PartDesign_ShapeBinder), its task panel (Object, Add Geometry, Remove Geometry
// and the reference list, in FreeCAD's "Shape Binder Parameters" box), the binder drawn as ViewProviderShapeBinder draws
// it (golden yellow, 60 % transparent, its lines orange) and the property view. The panel observes the selection as the
// C++ panel's SelectionObserver does: a click in the 3D view or the tree while a button is down is handed to
// referenceSelected and ends the mode; the support object shows as FreeCAD shows it (setVisible), its references in
// magenta while Add or Remove is down, and the binder itself is previewed from the server (`cad feature shape`, nothing
// written) as it is edited. OK writes it ("Create Shape Binder", one undo step).
import { useEffect, useMemo, useRef, useState, type KeyboardEvent as RKeyboardEvent } from 'react'
import * as THREE from 'three'
import { api, type Body, type FeatureOp } from './api'
import { getState, setState, subscribe, useStore, type Feature, type FeatureDoc } from './store'
import { closeTask, getView, showPanel } from './actions'
import { EditRow, Group, Row, TaskBox, cls } from './panels'
import { messageBox } from './msgbox'
import { applyOps, bodyOfPart, featureVisible, isSolid, refOf, SKETCH, splitRef, targetBody } from './partdesign'
import { baseMesh, baseOf, datumHover, parsePick } from './pd_pick'
import { refOfRow, refsOfSelection, type Ref } from './pd_attach'
import { DATUM_TYPES, isBinder, ROLES, SHAPE_BINDER } from './attached'
import './partdesign.css'

type Mesh = { faces: { name: string; points: number[]; index: number[]; kind?: string }[]; edges: { name: string; points: number[]; kind?: string | null }[] }
type Mode = 'none' | 'obj' | 'add' | 'remove'
const NO_BODY = 'In order to use PartDesign you need an active Body object in the document. Please make one active (double click) '
  + 'or create one.\n\nIf you have a legacy document with PartDesign objects without Body, use the migrate function in PartDesign '
  + 'to put them into a Body.'
const GOLD = 0xffd700, GOLD_LINE = 0xfa9600       // DefaultDatumColor 0xFFD70099 (60 % transparent), DefaultDatumLineColor
const MAGENTA = new THREE.Color(1, 0, 1)          // ViewProviderShapeBinder::highlightReferences
const SHAPE = new THREE.Color(0xcccccc), LINE = new THREE.Color(0x1a1a1a)
const partMatrix = (b: Body | undefined) => { const m = new THREE.Matrix4(); if (b?.matrix?.length === 16) m.fromArray(b.matrix).transpose(); return m }
const nextName = (doc: FeatureDoc, base: string) => {
  const names = new Set(doc.features.map((f) => f.name))
  if (!names.has(base)) return base
  for (let i = 1; ; i++) { const n = `${base}${String(i).padStart(3, '0')}`; if (!names.has(n)) return n }
}

/** Support as the part file writes it (feature_attach.support_list), normalised to (object, element) pairs: "Pad",
 *  "Pad.Face6", ("Pad", "Face6") and ("Pad", ["Face6", "Edge3"]) all read here, the whole object with "". */
function pairs(v: unknown): Ref[] {
  const one = (r: unknown): Ref[] => {
    if (typeof r === 'string') { const i = r.indexOf('.'); return i > 0 ? [[r.slice(0, i), r.slice(i + 1)]] : [[r, '']] }
    if (!Array.isArray(r) || typeof r[0] !== 'string') return []
    const sub = r[1]
    if (typeof sub === 'string') return [[r[0], sub]]
    if (Array.isArray(sub)) return sub.length ? sub.map((s) => [r[0], String(s)] as Ref) : [[r[0], '']]
    return [[r[0], '']]
  }
  if (v == null) return []
  if (typeof v === 'string') return one(v)
  if (!Array.isArray(v)) return []
  if (v.length === 2 && typeof v[0] === 'string' && (typeof v[1] === 'string' || Array.isArray(v[1]))) return one(v)
  return v.flatMap(one)
}

/** Whether the binder may copy an object (ShapeBinder.cpp's getFilteredReferences, feature_binder._part_feature): a Body
 *  feature that is a Part::Feature — a Pad or a Pocket, a sketch, another binder, PartDesign's Plane, Line or Point. Not
 *  the Origin's own features (they fall back to a shape of their own) and not a Part::DatumPlane. */
function isPartFeature(doc: FeatureDoc | undefined, o: string): boolean {
  if (!doc) return false
  if (o === 'BaseFeature') return doc.base
  const f = doc.features.find((x) => x.name === o)
  if (!f) return false
  return (f.type.startsWith('PartDesign::') && f.type in DATUM_TYPES) || f.type === SKETCH || isSolid(f.type) || isBinder(f.type)
}
/** Whether the panel can show that object as a mesh of its own (`cad feature shape`): a solid, a sketch or a binder (a
 *  datum's plane is infinite, an Origin feature is drawn by the Origin). */
function meshable(doc: FeatureDoc | undefined, o: string): boolean {
  if (!doc) return false
  if (o === 'BaseFeature') return doc.base
  const f = doc.features.find((x) => x.name === o)
  return !!f && (isSolid(f.type) || f.type === SKETCH || isBinder(f.type))
}
/** ShapeBinder::getFilteredReferences: the object and the elements the binder copies. The whole shape when that object's
 *  own first entry has no element, else its elements; with no Part::Feature, the first Origin feature (no elements). */
function filtered(doc: FeatureDoc | undefined, support: Ref[]): { obj: string | null; subs: string[] } {
  if (!support.length) return { obj: null, subs: [] }
  const i = support.findIndex(([o]) => isPartFeature(doc, o))
  if (i >= 0) {
    const obj = support[i][0]
    if (!support[i][1]) return { obj, subs: [] }                         // that object's own first entry has no element
    return { obj, subs: support.filter(([o, s]) => o === obj && s).map(([, s]) => s) }
  }
  const origin = support.find(([o]) => ROLES.includes(o))
  return origin ? { obj: origin[0], subs: [] } : { obj: null, subs: [] }
}
/** Body::addObject's place for a new binder: getNextSolidFeature() is the first solid feature after the Tip, and the
 *  binder goes before it (after the feature just before it); at the end when the Tip is missing or nothing solid follows. */
function insertAfter(doc: FeatureDoc): string | null {
  const names = doc.features.map((f) => f.name)
  const tip = doc.tip ? names.indexOf(doc.tip) : -1
  if (tip < 0) return names[names.length - 1] ?? null
  for (let i = tip + 1; i < doc.features.length; i++) if (isSolid(doc.features[i].type)) return doc.features[i - 1].name
  return names[names.length - 1] ?? null
}

// ── the binder's shapes, as the view draws them ────────────────────────────────────────────────────────
/** ViewProviderShapeBinder: the shape golden yellow, 60 % transparent, its lines and points orange (a datum's look).
 *  With pick, every face and edge is named for helperPicker and an edge wins over the face it bounds. */
function binderObject(m: Mesh, matrix: THREE.Matrix4, pick: string | null, color?: THREE.Color): THREE.Object3D {
  const g = new THREE.Group()
  for (const f of m.faces) {
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(f.points, 3))
    geo.setIndex(f.index)
    geo.computeVertexNormals()
    const mesh = new THREE.Mesh(geo, new THREE.MeshPhongMaterial({ color: color ?? GOLD, transparent: true, opacity: 0.4, depthWrite: false,
      side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 }))
    if (pick) mesh.userData.pickName = pick
    g.add(mesh)
  }
  for (const e of m.edges) {
    if (e.points.length < 6) continue
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(e.points, 3))
    const line = new THREE.Line(geo, new THREE.LineBasicMaterial({ color: color ?? GOLD_LINE, linewidth: 2 }))
    if (pick) { line.userData.pickName = pick; line.userData.pickPriority = 1 }
    g.add(line)
  }
  g.applyMatrix4(matrix)
  return g
}
/** The support object the panel shows (TaskShapeBinder::updateUI's setVisible): FreeCAD's grey solid, its referenced
 *  faces and edges magenta (highlightReferences), each named "@Pad.Face6" for the picker. */
function supportObject(base: string, m: Mesh, matrix: THREE.Matrix4, marked: Set<string>): THREE.Object3D {
  const g = new THREE.Group()
  for (const f of m.faces) {
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(f.points, 3))
    geo.setIndex(f.index)
    geo.computeVertexNormals()
    const mesh = new THREE.Mesh(geo, new THREE.MeshPhongMaterial({ color: marked.has(f.name) ? MAGENTA : SHAPE, side: THREE.DoubleSide,
      polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 }))
    mesh.userData.pickName = `@${base}.${f.name}`
    g.add(mesh)
  }
  for (const e of m.edges) {
    if (e.points.length < 6) continue
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(e.points, 3))
    const line = new THREE.Line(geo, new THREE.LineBasicMaterial({ color: marked.has(e.name) ? MAGENTA : LINE, linewidth: 2 }))
    line.userData.pickName = `@${base}.${e.name}`
    line.userData.pickPriority = 1
    g.add(line)
  }
  g.applyMatrix4(matrix)
  return g
}
/** The reference elements of the solid the view already shows (the Tip): magenta only, over it, nothing pickable
 *  (the model's own picking takes the clicks). */
function marksObject(m: Mesh, subs: string[], matrix: THREE.Matrix4): THREE.Object3D {
  const g = new THREE.Group(), want = new Set(subs)
  for (const f of m.faces) {
    if (!want.has(f.name)) continue
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(f.points, 3))
    geo.setIndex(f.index)
    geo.computeVertexNormals()
    g.add(new THREE.Mesh(geo, new THREE.MeshPhongMaterial({ color: MAGENTA, transparent: true, opacity: 0.6, depthWrite: false,
      side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1 })))
  }
  for (const e of m.edges) {
    if (!want.has(e.name) || e.points.length < 6) continue
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(e.points, 3))
    g.add(new THREE.Line(geo, new THREE.LineBasicMaterial({ color: MAGENTA, linewidth: 2, depthWrite: false })))
  }
  g.applyMatrix4(matrix)
  return g
}

// ── the binder in the 3D view, wherever a Body has one shown (ViewProviderShapeBinder's look) ─────────
// The server's scene draws the Body at its Tip; a binder is one of the Body's objects and is not in it, so its shape is
// asked for (`cad feature shape` on the binder, which is in the Body's Context, not among its solids) and drawn here.
const ghostMeshes = new WeakMap<FeatureDoc, Map<string, Mesh | null>>()
const ghostIds = new WeakMap<FeatureDoc, number>()
let nextGhostId = 1
const ghostId = (d: FeatureDoc) => { let i = ghostIds.get(d); if (!i) { i = nextGhostId++; ghostIds.set(d, i) } return i }
let ghostKey = ''
/** Every shown binder of every Body, in its Body's frame; the one whose task panel is open is the panel's to draw. */
function drawBinders() {
  const s = getState(), view = getView()
  if (!view) return
  const rows: { part: string; doc: FeatureDoc; f: Feature }[] = []
  for (const [part, doc] of Object.entries(s.features)) for (const f of doc.features) {
    if (!isBinder(f.type) || !featureVisible(s, part, f)) continue
    if (s.task?.kind === 'shapeBinder' && s.task.edit && s.task.body === part && s.task.other === f.name) continue
    rows.push({ part, doc, f })
  }
  const sel = rows.map((r) => s.featSel.includes(refOf(r.part, r.f.name)))
  const key = JSON.stringify([rows.map((r) => [r.part, r.f.name, r.f.support, ghostId(r.doc), bodyOfPart(s, r.part)?.matrix]), sel, s.selPrefs.color, s.slug])
  if (key === ghostKey) return
  const slug = s.slug
  const meshes = rows.map((r) => {
    const cache = ghostMeshes.get(r.doc) ?? new Map<string, Mesh | null>()
    ghostMeshes.set(r.doc, cache)
    const k = `${r.f.name}\u0000${JSON.stringify(r.f.support ?? null)}`
    const have = cache.get(k)
    if (have !== undefined) return have
    if (!slug) return null
    cache.set(k, null)                             // asked; the redraw below comes with the shape
    void api.featureShape(slug, r.part, [], r.f.name).then((res) => {
      const d = res.data ?? {}
      cache.set(k, (res.exit > 2 ? null : (d.shape as Mesh)) ?? null)
      ghostKey = ''
      drawBinders()
    }).catch(() => undefined)
    return null
  })
  ghostKey = key
  const g = new THREE.Group()
  rows.forEach((r, i) => {
    const m = meshes[i]
    if (!m) return
    const o = binderObject(m, partMatrix(bodyOfPart(s, r.part)), refOf(r.part, r.f.name), sel[i] ? new THREE.Color(s.selPrefs.color) : undefined)
    o.userData.selectable = true                   // a click on it selects its row (pd_pick.tsx's datumSelect)
    g.add(o)
  })
  view.setHelper('pd-binders', g.children.length ? g : null)
}
subscribe(drawBinders)

// ── the command (CmdPartDesignShapeBinder::activated) ─────────────────────────────────────────────────
type Pending = { part: string; name: string; support: Ref[] }
let pending: Pending | null = null
/** PartDesign_ShapeBinder: with one ShapeBinder selected, its panel ("Edit Shape Binder"); else a new binder in the active
 *  Body, its Support the selection (the Body itself is dropped from it: FreeCAD's support.removeValue(pcActiveBody)), and
 *  its panel open. OK writes it; Cancel writes nothing. */
export async function shapeBinder() {
  const s = getState()
  const part = targetBody()
  if (!part || !s.features[part]) { await messageBox('warning', 'No active body', NO_BODY); return }
  const doc = s.features[part]
  if (s.featSel.length === 1 && !s.subSel.length && !s.selected.length) {
    const [p, n] = splitRef(s.featSel[0])
    const f = p === part ? doc.features.find((x) => x.name === n) : undefined
    if (f && isBinder(f.type)) { editBinder(part, f); return }
  }
  const support = refsOfSelection(part, false)
  const name = nextName(doc, 'ShapeBinder')
  pending = { part, name, support }
  setState({ task: { kind: 'shapeBinder', body: part, other: name }, activeBody: part, selected: [], subSel: [], featSel: [] })
  showPanel('tasks')
}
/** ViewProviderShapeBinder::setEdit, and the ShapeBinder command on a selected binder: its panel on the feature. */
export function editBinder(part: string, f: Feature) {
  setState({ task: { kind: 'shapeBinder', body: part, other: f.name, edit: true }, selected: [], subSel: [], featSel: [] })
  showPanel('tasks')
}

// ── the task panel (TaskShapeBinder in "Shape Binder Parameters") ─────────────────────────────────────
/** The binder's ops as the panel has it: the support it copies, for the preview and for OK. */
function opsFor(doc: FeatureDoc, name: string, existing: Feature | undefined, support: Ref[]): FeatureOp[] {
  if (existing) return [{ op: 'set', name, props: { support } }]
  const after = insertAfter(doc)
  // no feature after the Tip to go before: the op leaves `after` out, which puts it at the end
  return [{ op: 'add', feature: { name, type: SHAPE_BINDER, support }, ...(after ? { after } : {}) }]
}

export function BinderTask({ part, name, edit }: { part: string; name: string; edit: boolean }) {
  const s = useStore((x) => x)
  const doc = s.features[part]
  const existing = edit ? doc?.features.find((f) => f.name === name) : undefined
  const fresh = useMemo(() => (!edit && pending?.part === part && pending.name === name ? pending : null), [part, name, edit])
  const [support, setSupport] = useState<Ref[]>(() => (existing ? pairs(existing.support) : fresh?.support ?? []))
  const [inText, setInText] = useState<string>(() => filtered(doc, existing ? pairs(existing.support) : fresh?.support ?? []).obj ?? '')
  const [mode, setMode] = useState<Mode>('none')
  const [row, setRow] = useState(-1)
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null)
  const [preview, setPreview] = useState<{ shape: Mesh | null; error: string | null } | null>(null)
  const [meshes, setMeshes] = useState<Record<string, Mesh>>({})
  // the mode and the support as they are now, for the clicks that come before React renders the change
  const modeRef = useRef<Mode>('none'), supportRef = useRef<Ref[]>(support)
  const begin = (m: Mode) => { modeRef.current = m; setMode(m) }
  const putSupport = (next: Ref[]) => { supportRef.current = next; setSupport(next) }
  const body = bodyOfPart(s, part)
  const cur = filtered(doc, support)
  const displayed = doc ? baseOf(doc, null) : null
  // the support object FreeCAD's updateUI makes visible: a solid, a sketch or a binder the view does not already show
  const shown = cur.obj && cur.obj !== displayed && meshable(doc, cur.obj) ? cur.obj : null
  const painting = (mode === 'add' || mode === 'remove') && !!cur.obj && cur.subs.length > 0 && meshable(doc, cur.obj)
  const paintSource = painting && cur.obj !== shown ? cur.obj : null
  const marked = mode === 'add' || mode === 'remove' ? new Set(cur.subs) : new Set<string>()

  // referenceSelected: a click on a feature, a sketch or a datum, or one of its elements, changes Support as FreeCAD
  // does. A pick it cannot take is refused silently (the C++ returns false without a message; the mode still ends).
  const take = (ref: Ref, m: Mode): boolean => {
    const [o, sub] = ref
    if (o === name) return false
    if (!isPartFeature(doc, o)) return false
    const now = filtered(doc, supportRef.current)
    if (m === 'obj') { putSupport([[o, '']]); setInText(o); setRow(-1); return true }   // refs.clear(); obj = selectedObj
    if (now.obj && o !== now.obj) return false
    if (m === 'add') {
      if (sub && now.subs.includes(sub)) return false
      // refs.push_back(subName), then Support.setValue(obj, refs): with no element the object itself (FreeCAD's link list
      // with an empty sub name is the whole object), and with the first reference the whole-object entry is replaced
      putSupport([...now.subs, sub].map((x) => [o, x] as Ref))
      setInText(o); setRow(-1)
      return true
    }
    const i = now.subs.indexOf(sub)
    if (!sub || i < 0) return false
    const rest = now.subs.filter((_, k) => k !== i)
    // PropertyLinkSubList::setValue(obj, {}) stores one link with no element: the whole object
    putSupport(rest.length ? rest.map((x) => [o, x] as Ref) : [[o, '']])
    return true
  }
  /** onSelectionChanged's AddSelection: apply the pick, then clearButtons() and exitSelectionMode() — even when it was refused. */
  const picked = (ref: Ref) => {
    const m = modeRef.current
    if (m === 'none') return
    take(ref, m)
    modeRef.current = 'none'
    setMode('none')
    setState({ selected: [], subSel: [], featSel: [] })
  }
  const pickedRef = useRef(picked)
  pickedRef.current = picked
  // the selection in the 3D view and the tree, as the C++ panel's SelectionObserver gets it
  useEffect(() => {
    let last = JSON.stringify([getState().subSel, getState().featSel, getState().selected])
    const unsub = subscribe(() => {
      const st = getState(), key = JSON.stringify([st.subSel, st.featSel, st.selected])
      if (key === last) return
      last = key
      if (modeRef.current === 'none') return
      const refs = refsOfSelection(part, false)
      if (!refs.length) return                         // a RemoveSelection: FreeCAD's observer leaves the mode alone
      pickedRef.current(refs[refs.length - 1])
    })
    return unsub
  }, [part])

  // Recompute: the binder as the panel has it, built on the server and not written (TaskDlgShapeBinder::accept's recompute)
  const seq = useRef(0)
  useEffect(() => {
    const slug = getState().slug
    if (!slug || !doc) return
    const n = ++seq.current
    const t = setTimeout(async () => {
      try {
        const r = await api.featureShape(slug, part, opsFor(doc, name, existing, support), name)
        if (n !== seq.current) return
        const d = r.data ?? {}
        setPreview({ shape: (d.shape as Mesh) ?? null, error: (d.error as string) ?? (r.exit > 2 ? String(d.message ?? r.text ?? 'failed') : null) })
      } catch (e) { if (n === seq.current) setPreview({ shape: null, error: String(e) }) }
    }, 150)
    return () => clearTimeout(t)
  }, [JSON.stringify(support)])

  // the meshes the view needs: the support object shown, and the solid the view already shows while it is highlighted
  const wanted = [shown, paintSource].filter((x): x is string => !!x).join('|')
  useEffect(() => {
    const miss = wanted ? wanted.split('|').filter((o) => !meshes[o]) : []
    if (!miss.length) return
    let live = true
    void Promise.all(miss.map(async (o) => [o, await baseMesh(part, o)] as const)).then((got) => {
      if (!live) return
      const add: Record<string, Mesh> = {}
      for (const [o, m] of got) if (m) add[o] = m
      if (Object.keys(add).length) setMeshes((x) => ({ ...x, ...add }))
    })
    return () => { live = false }
  }, [wanted, meshes, part])

  // the 3D view: the support object (FreeCAD's setVisible) with its references magenta while Add or Remove is down, and
  // the binder as it builds now, golden
  useEffect(() => {
    const view = getView()
    if (!view) return
    const g = new THREE.Group(), matrix = partMatrix(body)
    if (shown) { const m = meshes[shown]; if (m) g.add(supportObject(shown, m, matrix, marked)) }
    else if (paintSource) { const m = meshes[paintSource]; if (m) g.add(marksObject(m, cur.subs, matrix)) }
    if (preview?.shape) g.add(binderObject(preview.shape, matrix, null))
    view.setHelper('pd-binder-task', g.children.length ? g : null)
    return () => { getView()?.setHelper('pd-binder-task', null) }
  }, [shown, paintSource, JSON.stringify(cur.subs), JSON.stringify([...marked]), preview, meshes, body?.matrix])

  // the clicks on the support object shown: TaskShapeBinder's SelectionObserver, through the named helpers
  const hover = (n: string | null, refused: string | null) => {
    const p = n ? parsePick(part, n) : null
    setState({ gateMsg: refused, preselected: p ? part : null, preSub: p ? `${part}.${p.sub ? `${p.obj}.${p.sub}` : p.obj}` : null, prePoint: null })
  }
  const helper = useRef<(n: string) => void>(() => undefined)
  helper.current = (n: string) => {
    const p = parsePick(part, n)
    if (p) { picked(typeof p.ref === 'string' ? [p.ref, ''] : p.ref); return }
    const r = refOfRow(part, n)
    if (r) picked(r)
  }
  useEffect(() => {
    const view = getView()
    if (!view || !shown || mode === 'none') return
    view.helperPicker = (n: string) => helper.current(n)
    view.helperHover = hover
    return () => { const w = getView(); if (w) { w.helperPicker = null; w.helperHover = datumHover } setState({ gateMsg: null, preselected: null, preSub: null }) }
  }, [shown, mode, part])

  if (!doc) return <div className="tasks"><p className="hint">{part}: no feature list</p></div>
  const toggle = (m: Exclude<Mode, 'none'>) => {
    begin(mode === m ? 'none' : m)
    setState({ selected: [], subSel: [], featSel: [] })          // onButtonToggled: Gui::Selection().clearSelection()
  }
  const removeRow = (i: number) => {
    const now = filtered(doc, supportRef.current)
    if (!now.obj || i < 0 || i >= now.subs.length) return
    const rest = now.subs.filter((_, k) => k !== i)
    putSupport(rest.length ? rest.map((x) => [now.obj!, x] as Ref) : [[now.obj, '']])   // deleteItem's setValue(obj, subs)
    setRow(-1)
    begin('none')                                                  // deleteItem: clearButtons()
  }
  const changeText = (text: string) => {
    setInText(text)
    if (text !== '') return
    putSupport([])                                                 // supportChanged: Support.setValue(nullptr, nullptr)
    setRow(-1)
  }
  const keys = (e: RKeyboardEvent) => {
    const tag = (e.target as HTMLElement).tagName
    if (tag === 'INPUT' || tag === 'TEXTAREA') return
    if ((e.key === 'Delete' || e.key === 'Backspace') && row >= 0) { e.preventDefault(); removeRow(row) }
  }
  const ok = async () => {
    // TaskDlgShapeBinder::accept: recompute, and a binder that does not build keeps the panel open with "Input Error"
    if (preview?.error) { await messageBox('warning', 'Input Error', preview.error); return }
    const typed = inText.trim()
    let sup = support
    // accept(): with no support at all, the text in the line names an object, as a pick of it would
    if (!support.length && typed && isPartFeature(doc, typed)) sup = [[typed, '']]
    if (existing) {
      if (JSON.stringify(sup) === JSON.stringify(pairs(existing.support))) { closeTask(); return }
      const done = await applyOps(part, [{ op: 'set', name, props: { support: sup } }], { name: 'Edit Shape Binder' })
      if (!done) return
    } else {
      const after = insertAfter(doc)
      const done = await applyOps(part, [{ op: 'add', feature: { name, type: SHAPE_BINDER, support: sup }, ...(after ? { after } : {}) }],
        { name: 'Create Shape Binder' })
      if (!done) return
    }
    closeTask()
    setState({ featSel: [refOf(part, name)], selected: [] })
  }
  return (
    <div className="tasks" onKeyDown={keys}>
      <div className="tbuttons pd-buttons"><button className="qbtn default" onClick={() => void ok()}>OK</button><button className="qbtn" onClick={closeTask}>Cancel</button></div>
      <TaskBox title="Shape Binder Parameters" icon="pd-shape-binder">
        <div className="pd-form">
          <div className="tfield">
            <button className={cls('qbtn', mode === 'obj' && 'on')} aria-pressed={mode === 'obj'}
              onClick={() => toggle('obj')}>Object</button>
            <input value={inText} placeholder="No object" onChange={(e) => changeText(e.target.value)} />
          </div>
          <div className="pd-buttons">
            <button className={cls('qbtn', mode === 'add' && 'on')} aria-pressed={mode === 'add'}
              onClick={() => toggle('add')}>Add Geometry</button>
            <button className={cls('qbtn', mode === 'remove' && 'on')} aria-pressed={mode === 'remove'}
              onClick={() => toggle('remove')}>Remove Geometry</button>
          </div>
          <div className="pd-reflist" role="listbox" tabIndex={0}
            onContextMenu={(e) => { e.preventDefault(); if (row >= 0) setMenu({ x: e.clientX, y: e.clientY }) }}>
            {cur.subs.map((sub, i) => <div key={sub} role="option" aria-selected={row === i} className={cls('pd-mode', row === i && 'sel')}
              onClick={() => setRow(i)}>{sub}</div>)}
          </div>
          {menu && <div className="pd-ctx" style={{ left: menu.x, top: menu.y }} onMouseLeave={() => setMenu(null)}>
            <div className="pd-ctx-item" onClick={() => { removeRow(row); setMenu(null) }}><span>Remove</span><span className="kbd">Del</span></div>
          </div>}
          {preview?.error && <p className="pd-error">{preview.error}</p>}
        </div>
      </TaskBox>
    </div>
  )
}

// ── the property view: FreeCAD's Data tab for a binder (Base: Label, Support, TraceSupport; Placement is hidden) ──────
export function BinderProps({ part, f, set, onRename }: { part: string; f: Feature; set(props: Record<string, unknown>): void; onRename(name: string): void }) {
  const s = useStore((x) => x)
  const doc = s.features[part]
  const sup = pairs(f.support)
  const text = sup.map(([o, x]) => (x ? `${o}:${x}` : o)).join(', ')
  const copies = filtered(doc, sup)
  return (
    <Group title="Base">
      <EditRow k="Label" value={f.name} type="str" onCommit={(v) => onRename(String(v))} />
      <Row k={<span title={copies.obj ? `The binder copies ${copies.subs.length ? `${copies.obj}'s ${copies.subs.join(', ')}` : `${copies.obj} whole`}`
        : 'No shape copied: pick one in the task panel (double-click the feature)'}>Support</span>} v={text} />
      <EditRow k="Trace Support" value={f.trace_support === true} type="bool" onCommit={(v) => set({ trace_support: v })} />
    </Group>
  )
}

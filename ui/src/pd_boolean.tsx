// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/PartDesign/Gui/Command.cpp: 2008 Jürgen Riegel (CmdPartDesignBoolean, CmdPartDesignClone)
//   src/Mod/PartDesign/Gui/TaskBooleanParameters.cpp: 2013 Jan Rheinländer (the panel: Add Body, Remove Body, the list and
//     its Remove action, Type; BooleanToolSelection; TaskDlgBooleanParameters::accept and reject)
//   src/Mod/PartDesign/Gui/ViewProviderBoolean.cpp: 2013 Jan Rheinländer, 2025 Kacper Donat (claimChildren: the tools under it)
//   No copyright line in the file: src/Mod/PartDesign/Gui/TaskBooleanParameters.ui
// PartDesign's Boolean and Clone (cad_agent/feature_boolean.py), which take other Bodies. A Body here is a part module,
// so a tool or a Clone's source is another part of the project, by its name ("Body001", or "Body001.Pad001" for one of
// its features). Clone makes a new part (`cad feature clone`, "Create Clone"); Boolean opens its panel on a new feature in
// the active Body with the selected Bodies as its tools, and OK writes it ("Create Boolean").
import { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { api, resultText, type Body, type FeatureOp } from './api'
import { consoleLog, getState, report, setState, subscribe, useStore, type Feature, type FeatureDoc } from './store'
import { closeTask, getView, loadFeatures, loadHistory, showPanel } from './actions'
import { EditRow, Group, Row, TaskBox, cls, propPad } from './panels'
import { QComboBox } from './combo'
import { messageBox } from './msgbox'
import type { Entry } from './chrome'
import { applyOps, bodyOfPart, isBodyDoc, isSolid, refOf, splitRef, targetBody } from './partdesign'
import './partdesign.css'

export const BOOLEAN = 'PartDesign::Boolean', CLONE = 'PartDesign::FeatureBase'
export const isBoolean = (t: unknown) => t === BOOLEAN
export const isClone = (t: unknown) => t === CLONE
export const BOOLEAN_ICONS: Record<string, 'pd-boolean' | 'pd-clone'> = { [BOOLEAN]: 'pd-boolean', [CLONE]: 'pd-clone' }
export const BOOLEAN_KINDS: Record<string, string> = { [BOOLEAN]: 'Boolean', [CLONE]: 'Clone' }
const TYPES = ['Fuse', 'Cut', 'Common']
const NO_BODY = 'In order to use PartDesign you need an active Body object in the document. Please make one active (double click) '
  + 'or create one.\n\nIf you have a legacy document with PartDesign objects without Body, use the migrate function in PartDesign '
  + 'to put them into a Body.'
const msg = (e: unknown) => (e instanceof Error ? e.message : String(e))
const nextName = (doc: FeatureDoc, base: string) => {
  const names = new Set(doc.features.map((f) => f.name))
  if (!names.has(base)) return base
  for (let i = 1; ; i++) { const n = `${base}${String(i).padStart(3, '0')}`; if (!names.has(n)) return n }
}
/** The Bodies (part modules) a tool or a Clone's source names: "Body001" or "Body001.Pad001". */
export const linkBody = (l: unknown) => (typeof l === 'string' ? l.split('.')[0] : '')
/** A Boolean's tools, in its Group's order (ViewProviderBoolean::claimChildren shows them under it). */
export const booleanTools = (f: Feature): string[] => (Array.isArray(f.group) ? f.group.map(String) : [])

/** The Part::Features the selection holds, as links to other Bodies: a Body's row ("Body001/") or its body in the 3D view
 *  is the Body; a solid feature's row of another Body is that feature ("Body001.Pad001"). */
function selectedLinks(): string[] {
  const s = getState(), out: string[] = []
  const add = (l: string) => { if (l && !out.includes(l)) out.push(l) }
  for (const r of s.featSel) {
    const [p, n] = splitRef(r)
    const doc = s.features[p]
    if (!doc) continue
    if (!n) { add(p); continue }
    const f = doc.features.find((x) => x.name === n)
    if (f && isSolid(f.type)) add(`${p}.${n}`)
  }
  for (const b of s.selected) { const part = s.scene?.bodies.find((x) => x.name === b)?.part; if (part && s.features[part]) add(part) }
  for (const sub of s.subSel) { const part = s.scene?.bodies.find((x) => x.name === sub.slice(0, sub.lastIndexOf('.')))?.part; if (part && s.features[part]) add(part) }
  return out
}

// ── PartDesign_Clone ─────────────────────────────────────────────────────────────────────────────────────────────
/** CmdPartDesignClone::isActive: exactly one Part::Feature selected. */
export const cloneEnabled = () => selectedLinks().length === 1
/** CmdPartDesignClone: a new Body (the next free name, Body001, …) whose first feature is a Clone of the selection, its
 *  Tip; it is not made active. `cad feature clone`: one step, "Create Clone". */
export async function cloneCommand() {
  const s = getState()
  const links = selectedLinks()
  if (!s.slug || links.length !== 1) return
  const argv = ['feature', 'clone', s.slug, links[0]]
  if (s.scriptToPyConsole) consoleLog('in', `cad ${argv.join(' ')}`)
  try {
    const r = await api.cad(s.slug, argv)
    if (r.exit !== 0) { report('err', `Clone: ${resultText(r)}`); return }
    const part = String(r.data?.part ?? '')
    report('msg', `${part}: Create Clone (a Clone of ${links[0]})`)
    loadHistory()
    await loadFeatures()
    if (part) setState({ featSel: [refOf(part, 'Clone')], selected: [], subSel: [] })
  } catch (e) { report('err', `Clone: ${msg(e)}`) }
}

// ── PartDesign_Boolean ───────────────────────────────────────────────────────────────────────────────────────────
type Pending = { part: string; name: string; group: string[] }
let pending: Pending | null = null
/** CmdPartDesignBoolean: in the active Body ("Create Boolean"), its tools the selected Part::Features but the active Body
 *  itself (SELECT Part::Feature COUNT 1..), and its panel open. OK writes it; Cancel writes nothing (reject's abortCommand). */
export async function booleanCommand() {
  const s = getState()
  if (!s.slug) return
  const part = targetBody()
  if (!part || !s.features[part] || !isBodyDoc(s.features[part])) { await messageBox('warning', 'No active body', NO_BODY); return }
  const group = selectedLinks().filter((l) => linkBody(l) !== part)
  pending = { part, name: nextName(s.features[part], 'Boolean'), group }
  setState({ task: { kind: 'pdBoolean', body: part, other: pending.name }, selected: [], subSel: [], featSel: [] })
  showPanel('tasks')
}
export function editBoolean(part: string, f: Feature) {
  setState({ task: { kind: 'pdBoolean', body: part, other: f.name, edit: true }, selected: [], subSel: [], featSel: [] })
  showPanel('tasks')
}

type Mesh = { faces: { name: string; points: number[]; index: number[] }[]; edges: { name: string; points: number[] }[] }
const partMatrix = (b: Body | undefined) => { const m = new THREE.Matrix4(); if (b?.matrix?.length === 16) m.fromArray(b.matrix).transpose(); return m }
function meshObject(m: Mesh, color: number, opacity: number): THREE.Object3D {
  const g = new THREE.Group()
  for (const f of m.faces) {
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(f.points, 3))
    geo.setIndex(f.index)
    geo.computeVertexNormals()
    g.add(new THREE.Mesh(geo, new THREE.MeshPhongMaterial({ color, transparent: opacity < 1, opacity, depthWrite: opacity >= 1, side: THREE.DoubleSide })))
  }
  for (const e of m.edges) {
    if (e.points.length < 6) continue
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(e.points, 3))
    g.add(new THREE.Line(geo, new THREE.LineBasicMaterial({ color, linewidth: 2 })))
  }
  return g
}

/** TaskBooleanParameters in "Boolean Parameters", with the Preview box. */
export function BooleanTask({ part, name, edit }: { part: string; name: string; edit: boolean }) {
  const s = useStore((x) => x)
  const doc = s.features[part]
  const existing = edit ? doc?.features.find((f) => f.name === name) : undefined
  const fresh = useMemo(() => (!edit && pending?.part === part && pending.name === name ? pending : null), [part, name, edit])
  const [group, setGroup] = useState<string[]>(() => (existing ? booleanTools(existing) : fresh?.group ?? []))
  const [type, setType] = useState<string>(() => String(existing?.type1 ?? 'Fuse'))
  const [mode, setMode] = useState<'none' | 'add' | 'remove'>('none')
  const [row, setRow] = useState(-1)
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null)
  const [showFinal, setShowFinal] = useState(false)
  const [overlay, setOverlay] = useState(true)
  const [built, setBuilt] = useState<{ shape: Mesh | null; error: string | null } | null>(null)
  const ops = (): FeatureOp[] => {
    const props: Record<string, unknown> = { group, ...(type !== 'Fuse' || existing ? { type1: type } : {}) }
    if (existing) return [{ op: 'set', name, props }]
    const after = doc?.tip ?? doc?.features[doc.features.length - 1]?.name ?? null
    return [{ op: 'add', feature: { name, type: BOOLEAN, ...props }, ...(after ? { after } : {}) }, { op: 'tip', name }]
  }
  // recomputeFeature after every change: the server builds it (nothing written)
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
        setBuilt({ shape: (d.shape as Mesh) ?? null, error: (d.error as string) ?? (r.exit > 2 ? String(d.message ?? r.text ?? 'failed') : null) })
      } catch (e) { if (n === seq.current) setBuilt({ shape: null, error: String(e) }) }
    }, 150)
    return () => clearTimeout(t)
  }, [JSON.stringify(group), type])
  const body = bodyOfPart(s, part)
  useEffect(() => {
    const view = getView()
    if (!view) return
    // the result, in the preview's colours (PreviewAdditiveColor for Fuse and Common, PreviewSubtractiveColor for Cut) or
    // drawn as the result with Show final result
    const g = built?.shape && !built.error && (overlay || showFinal)
      ? meshObject(built.shape, showFinal ? 0xcccccc : type === 'Cut' ? 0xff0000 : 0x00ff99, showFinal ? 1 : 0.2) : null
    if (g) g.applyMatrix4(partMatrix(body))
    view.setHelper('pd-boolean', g)
  }, [built, overlay, showFinal, type, body?.matrix])
  useEffect(() => () => { getView()?.setHelper('pd-boolean', null) }, [])
  // Add Body / Remove Body: the next Body picked in the 3D view or the tree is added or taken out (onSelectionChanged),
  // then the button comes up (exitSelectionMode); BooleanToolSelection refuses the result Body
  useEffect(() => {
    if (mode === 'none') return
    setState({ featSel: [], selected: [], subSel: [] })
    const off = subscribe(() => {
      const links = selectedLinks()
      if (!links.length) return
      const l = linkBody(links[0]) === links[0] ? links[0] : linkBody(links[0])     // getBodyOfSelection: a feature's Body
      if (l === part) { setState({ gateMsg: 'The result Body cannot be used as a Boolean tool.', featSel: [], selected: [], subSel: [] }); return }
      if (mode === 'add') setGroup((g) => (g.includes(l) ? g : [...g, l]))
      else setGroup((g) => g.filter((x) => linkBody(x) !== l))
      setMode('none')
      setState({ featSel: [], selected: [], subSel: [] })
    })
    return () => { off?.() }
  }, [mode])

  if (!doc) return <div className="tasks"><p className="hint">{part}: no feature list</p></div>
  const ok = async () => {
    // TaskDlgBooleanParameters::accept
    if (!group.length) { await messageBox('warning', 'Empty Body List', 'The body list cannot be empty'); return }
    closeTask()
    if (existing) {
      const props: Record<string, unknown> = {}
      if (JSON.stringify(group) !== JSON.stringify(booleanTools(existing))) props.group = group
      if (type !== String(existing.type1 ?? 'Fuse')) props.type1 = type
      if (Object.keys(props).length) await applyOps(part, [{ op: 'set', name, props }], { name: `Edit ${name}` })
      return
    }
    const done = await applyOps(part, ops(), { name: 'Create Boolean' })
    if (done) setState({ featSel: [refOf(part, name)], selected: [] })
  }
  const removeRow = () => { if (row >= 0) { setGroup((g) => g.filter((_, i) => i !== row)); setRow(-1) } }
  return (
    <div className="tasks" onKeyDown={(e) => { if ((e.key === 'Delete' || e.key === 'Backspace') && row >= 0) { e.preventDefault(); removeRow() } }}>
      <div className="tbuttons pd-buttons"><button className="qbtn default" onClick={() => void ok()}>OK</button><button className="qbtn" onClick={closeTask}>Cancel</button></div>
      <TaskBox title="Boolean Parameters" icon="pd-boolean">
        <div className="pd-form" data-panel="boolean">
          <div className="pd-row2">
            <button className={cls('qbtn', mode === 'add' && 'on')} data-qf="buttonBodyAdd" aria-pressed={mode === 'add'} onClick={() => setMode(mode === 'add' ? 'none' : 'add')}>Add Body</button>
            <button className={cls('qbtn', mode === 'remove' && 'on')} data-qf="buttonBodyRemove" aria-pressed={mode === 'remove'} onClick={() => setMode(mode === 'remove' ? 'none' : 'remove')}>Remove Body</button>
          </div>
          <div className="pd-reflist" role="listbox" tabIndex={0} data-qf="listWidgetBodies"
            onContextMenu={(e) => { e.preventDefault(); setMenu({ x: e.clientX, y: e.clientY }) }}>
            {group.map((g, i) => <div key={g} role="option" aria-selected={row === i} className={cls('pd-mode', row === i && 'sel')} onClick={() => setRow(i)}>{g}</div>)}
          </div>
          {menu && <div className="pd-ctx" style={{ left: menu.x, top: menu.y }} onMouseLeave={() => setMenu(null)}>
            <div className="pd-ctx-item" onClick={() => { removeRow(); setMenu(null) }}><span>Remove</span><span className="kbd">Del</span></div>
          </div>}
          <QComboBox data-qf="comboType" value={type} onChange={(e) => setType(e.target.value)}>
            {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}</QComboBox>
          {built?.error && <p className="pd-error">{built.error}</p>}
        </div>
      </TaskBox>
      <TaskBox title="Preview" icon="pd-boolean">
        <label className="tcheck"><input type="checkbox" checked={showFinal} onChange={(e) => setShowFinal(e.target.checked)} /> Show final result</label>
        <label className="tcheck"><input type="checkbox" checked={overlay} onChange={(e) => setOverlay(e.target.checked)} /> Show preview overlay</label>
      </TaskBox>
    </div>
  )
}

// ── menus, tree, property view ───────────────────────────────────────────────────────────────────────────────────
export function booleanEntries(hasDoc: boolean): { clone: Entry; boolean: Entry } {
  return {
    clone: { label: 'Clone', icon: 'pd-clone', cmd: 'PartDesign_Clone', disabled: !cloneEnabled(), title: 'Copies a solid object parametrically as the base feature of a new body', onSelect: () => void cloneCommand() },
    boolean: { label: 'Boolean Operation', icon: 'pd-boolean', cmd: 'PartDesign_Boolean', disabled: !hasDoc, title: 'Applies boolean operations with the selected objects and the active body', onSelect: () => void booleanCommand() },
  }
}
/** The Data tab of a Boolean (Base: Type, Label, Group, Suppressed; Part Design: Refine, Fuzzy Tolerance) or a Clone
 *  (Base: Base Feature, Placement, Label, Suppressed), as the real FreeCAD 26.3 lists them (ui/scripts/fcpdlast.json). */
export function BooleanProps({ f, set, onRename }: { part: string; f: Feature; set(props: Record<string, unknown>): void; onRename(name: string): void }) {
  const label = <EditRow k="Label" value={f.name} type="str" onCommit={(n) => onRename(String(n))} />
  const suppressed = <Row k={<span title="Read-only: FEATURES has no suppressed state">Suppressed</span>} v="false" />
  if (isClone(f.type)) return <Group title="Base">
    <Row k={<span title="Read-only: the Clone's source, chosen by the command">Base Feature</span>} v={String(f.base_feature ?? '')} />
    <Row k="Placement" v="[(0.00 0.00 1.00); 0.00°; (0.00 mm  0.00 mm  0.00 mm)]" />{label}{suppressed}</Group>
  return <>
    <Group title="Base">
      <div className="prow" tabIndex={0}><span className="pk" style={propPad(0)}>Type</span>
        <span className="pv"><QComboBox className="qselect-pv" value={String(f.type1 ?? 'Fuse')} onChange={(e) => set({ type1: e.target.value })}>{TYPES.map((t) => <option key={t}>{t}</option>)}</QComboBox></span></div>
      {label}
      <Row k={<span title="Read-only: Add Body and Remove Body in the task panel (double-click the feature)">Group</span>} v={booleanTools(f).join(' ')} />
      {suppressed}
    </Group>
    <Group title="Part Design">
      <EditRow k="Refine" value={f.refine !== false} type="bool" onCommit={(n) => set({ refine: n })} />
      <Row k={<span title="Read-only: the booleans run at OCCT's own tolerance">Fuzzy Tolerance</span>} v="0" />
    </Group>
  </>
}
/** A Boolean's tools as rows under it (claimChildren), each selecting its Body's row. */
export function booleanChildRows(f: Feature): { link: string; label: string }[] {
  return booleanTools(f).map((l) => ({ link: l, label: l.includes('.') ? l.split('.')[1] : l }))
}
void Row

// Tools menu additions past Clarify Selection (src/Gui/Workbench.cpp's Tools menu at FreeCAD
// main 3160daf1e2b6): Std_DlgParameter (Dialogs/DlgParameterImp.cpp), Std_SceneInspector
// (SceneInspector.cpp), Std_DependencyGraph/Std_ExportDependencyGraph (GraphvizView.cpp,
// CommandDoc.cpp) and Std_ViewLoadImage (CommandView.cpp, ImageView.cpp). All but Load Image are
// QDialogs/an MDI view in FreeCAD; here, like Std_UnitsCalculator and Std_DlgPreferences already
// do, they go through the one Tasks panel this UI has (panels.tsx's task switch). Load Image has
// no dialog of its own in FreeCAD either, beyond the file picker.
import { useMemo, useState } from 'react'
import { closeTask, getView, openTask } from './actions'
import type { Body } from './api'
import { ContextMenu, type Entry } from './chrome'
import { QComboBox } from './combo'
import { cls, TaskBox } from './panels'
import { getState, report, saved, setState, useStore, type State } from './store'
import type { SceneNode } from './viewer'

// ── Std_DlgParameter (Dialogs/DlgParameterImp.cpp): the Parameter Editor ────────────────────
// FreeCAD's dialog shows the real ParameterGrp tree (User parameter: BaseApp/Preferences/…); the
// nearest thing here is the "cadui.*" keys the `saved` helper (store.ts) writes to localStorage.
// So the tree below is built from localStorage itself, not from a hand-picked guess at what's
// in it — new keys this UI starts saving later show up under General for free. A leaf's type
// (DlgParameterImp.cpp's Boolean/Integer/Unsigned/Float/Text) comes from the live value's own
// JS type for everything this UI already reads; Unsigned only ever comes from "New Unsigned
// Item" (plain numbers can't tell Integer and Unsigned apart), so new items remember their
// chosen type explicitly, in the "custom" entry below.
const STORE_PREFIX = 'cadui.'
type PType = 'bool' | 'int' | 'uint' | 'float' | 'text'
const TYPE_LABEL: Record<PType, string> = { bool: 'Boolean', int: 'Integer', uint: 'Unsigned', float: 'Float', text: 'Text' }
type PLeaf = { name: string; type: PType; value: unknown; custom: boolean; write(v: unknown): void; remove?(): void; rename?(n: string): void }
type PGroup = { name: string; path: string; custom: boolean; groups: PGroup[]; leaves: PLeaf[] }
/** A user-created item (ParameterGroup::onCreateSubgroup / ParameterValue::onCreateXxxItem): kept
 *  in one "custom" blob keyed by "Group/Path/ItemName" so a freshly invented group needs no extra
 *  bookkeeping key of its own — it exists exactly as long as it has an item in it, same as a real
 *  ParameterGrp with nothing but sub-groups in it isn't very visitable either. */
type CustomEntry = { t: PType; v: unknown }

// .pgrid's own .prow/.phead are 2-column (see tools.css); inline so the 3-column Name/Type/Value
// layout is right even before that CSS is merged into freecad.css.
const COLS3 = { gridTemplateColumns: '34% 22% 44%' } as const
const isPlainObject = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v)
function inferType(v: unknown): PType {
  if (typeof v === 'boolean') return 'bool'
  if (typeof v === 'number') return Number.isInteger(v) ? 'int' : 'float'
  return 'text'
}
/** After writing straight to localStorage (saved.set does the same), patch the live State too
 *  when a key of the same name exists there — "changes applied live to the store", for every
 *  key this covers without having to list them one by one. */
function applyLive(storageKey: string) {
  const st = getState() as unknown as Record<string, unknown>
  if (Object.prototype.hasOwnProperty.call(st, storageKey)) {
    setState({ [storageKey]: saved.get(storageKey, st[storageKey]) } as Partial<State>)
  }
}
/** Maps a top-level `saved` key with a plain value, or whose object's own fields should show
 *  directly (no extra group named after the key itself), to FreeCAD's real preference group
 *  names (confirmed against DlgSettings*.ui/PreferencePages at this commit). Not listed → General
 *  — "anything else under a sensible group" is General's whole job here. */
const GROUP_RULES: Record<string, string[]> = {
  units: ['Units'], naviCube: ['NaviCube'], cubePos: ['NaviCube', 'cubePos'], tree: ['TreeView'],
  recordGuiCommands: ['Macro'], guiAsComment: ['Macro'], recentMacros: ['Macro'],
  recentFiles: ['RecentFiles'], statusBar: ['StatusBar'], toolbars: ['MainWindow', 'Toolbars'],
  showFPS: ['View'], disableTouchTilt: ['View'], newDocCameraScale: ['View'], axes: ['View'],
  homeView: ['View'], animate: ['View'], nav: ['View'], placementRotationMethod: ['View'],
  corner: ['View', 'Corner'], axisColors: ['View', 'AxisColors'], rotationCenter: ['View', 'RotationCenter'],
  navPrefs: ['View', 'Navigation'], snap: ['View', 'Snap'],
  editMode: ['General'], slug: ['General'],
}
/** Same, for a dotted key ("measure.autoSave"): the part before the first dot picks the group;
 *  the rest is the leaf's own name. */
const DOTTED_GROUP: Record<string, string[]> = {
  tree: ['TreeView'], measure: ['View', 'Measure'], shot: ['View', 'SaveImage'],
  console: ['General', 'Console'], report: ['General', 'Report'], props: ['PropertyView'],
  split: ['MainWindow', 'Splitters'],
}

function objectFieldLeaf(storageKey: string, field: string, value: unknown, bump: () => void): PLeaf {
  return {
    name: field, type: inferType(value), value, custom: false,
    write: (v) => {
      const cur = saved.get<Record<string, unknown>>(storageKey, {})
      saved.set(storageKey, { ...cur, [field]: v })
      applyLive(storageKey)
      bump()
    },
  }
}
function dottedLeaf(rawKey: string, value: unknown, bump: () => void): PLeaf {
  return { name: rawKey.slice(rawKey.indexOf('.') + 1), type: inferType(value), value, custom: false,
    write: (v) => { saved.set(rawKey, v); bump() } }
}
function primitiveLeaf(rawKey: string, value: unknown, bump: () => void): PLeaf {
  return { name: rawKey, type: inferType(value), value, custom: false,
    write: (v) => { saved.set(rawKey, v); applyLive(rawKey); bump() } }
}
function customLeaf(fullPath: string, entry: CustomEntry, bump: () => void): PLeaf {
  return {
    name: fullPath.slice(fullPath.lastIndexOf('/') + 1), type: entry.t, value: entry.v, custom: true,
    write: (v) => {
      const all = saved.get<Record<string, CustomEntry>>('custom', {})
      all[fullPath] = { t: entry.t, v }
      saved.set('custom', all)
      bump()
    },
    remove: () => {
      const all = saved.get<Record<string, CustomEntry>>('custom', {})
      delete all[fullPath]
      saved.set('custom', all)
      bump()
    },
    rename: (n) => {
      const all = saved.get<Record<string, CustomEntry>>('custom', {})
      const parent = fullPath.slice(0, fullPath.lastIndexOf('/'))
      const next = parent ? `${parent}/${n}` : n
      if (all[next]) return // ParameterGroup::onCreateSubgroup's "already exists" guard, applied to rename too
      all[next] = all[fullPath]
      delete all[fullPath]
      saved.set('custom', all)
      bump()
    },
  }
}

function buildTree(bump: () => void): PGroup {
  const root: PGroup = { name: 'User parameter', path: '', custom: false, groups: [], leaves: [] }
  const group = (path: string[], customIfNew = false): PGroup => path.reduce((g, name) => {
    let next = g.groups.find((x) => x.name === name)
    if (!next) {
      next = { name, path: g.path ? `${g.path}/${name}` : name, custom: customIfNew, groups: [], leaves: [] }
      g.groups.push(next)
    }
    return next
  }, root)

  const keys = Object.keys(localStorage).filter((k) => k.startsWith(STORE_PREFIX) && k !== `${STORE_PREFIX}custom`)
    .map((k) => k.slice(STORE_PREFIX.length)).sort()
  for (const rawKey of keys) {
    let value: unknown
    try { value = JSON.parse(localStorage.getItem(STORE_PREFIX + rawKey) ?? 'null') } catch { value = localStorage.getItem(STORE_PREFIX + rawKey) }
    const dot = rawKey.indexOf('.')
    if (dot !== -1) {
      group(DOTTED_GROUP[rawKey.slice(0, dot)] ?? ['General']).leaves.push(dottedLeaf(rawKey, value, bump))
      continue
    }
    const g = group(GROUP_RULES[rawKey] ?? ['General'])
    if (isPlainObject(value)) for (const [k, v] of Object.entries(value)) g.leaves.push(objectFieldLeaf(rawKey, k, v, bump))
    else g.leaves.push(primitiveLeaf(rawKey, value, bump))
  }
  const custom = saved.get<Record<string, CustomEntry>>('custom', {})
  for (const [fullPath, entry] of Object.entries(custom)) {
    const segs = fullPath.split('/')
    segs.pop()
    group(segs, true).leaves.push(customLeaf(fullPath, entry, bump))
  }
  const sortGroup = (g: PGroup) => {
    g.groups.sort((a, b) => a.name.localeCompare(b.name))
    g.leaves.sort((a, b) => a.name.localeCompare(b.name))
    g.groups.forEach(sortGroup)
  }
  sortGroup(root)
  return root
}

const validName = (s: string) => /^[0-9A-Za-z ]+$/.test(s)
/** ParameterValue::onCreateXxxItem: name first, then the value, as two plain prompts —
 *  DlgParameterImp.cpp's own dialogs (QInputDialog) are just as plain. */
function createLeaf(g: PGroup, type: PType, bump: () => void) {
  const name = prompt(`New ${TYPE_LABEL[type]} Item\nEnter the name:`)?.trim()
  if (!name) return
  if (!validName(name)) { alert(`Invalid key name '${name}'`); return }
  const fullPath = g.path ? `${g.path}/${name}` : name
  const all = saved.get<Record<string, CustomEntry>>('custom', {})
  if (all[fullPath]) { alert(`The item '${name}' already exists.`); return }
  const raw = prompt(type === 'bool' ? 'Enter the value (true/false):' : type === 'text' ? 'Enter text:' : 'Enter number:',
    type === 'bool' ? 'false' : type === 'text' ? '' : '0')
  if (raw === null) return
  let v: unknown
  if (type === 'bool') v = raw.trim().toLowerCase() === 'true'
  else if (type === 'text') v = raw
  else { const n = Number(raw); if (Number.isNaN(n)) return; v = type === 'float' ? n : type === 'uint' ? Math.max(0, Math.round(n)) : Math.round(n) }
  all[fullPath] = { t: type, v }
  saved.set('custom', all)
  bump()
}
function addSubGroup(g: PGroup, bump: () => void) {
  const name = prompt('New Sub-Group\nEnter the name:')?.trim()
  if (!name) return
  if (!validName(name)) { alert(`Invalid key name '${name}'`); return }
  createLeaf({ ...g, path: g.path ? `${g.path}/${name}` : name } as PGroup, 'text', bump)
}
function removeGroupCustom(g: PGroup, bump: () => void) {
  if (!confirm('Remove this parameter group?')) return
  const all = saved.get<Record<string, CustomEntry>>('custom', {})
  const prefix = `${g.path}/`
  for (const k of Object.keys(all)) if (k.startsWith(prefix)) delete all[k]
  saved.set('custom', all)
  bump()
}
function renameGroupCustom(g: PGroup, name: string, bump: () => void) {
  const all = saved.get<Record<string, CustomEntry>>('custom', {})
  const parent = g.path.slice(0, g.path.lastIndexOf('/'))
  const oldPrefix = `${g.path}/`, newPrefix = `${parent ? `${parent}/` : ''}${name}/`
  const next: Record<string, CustomEntry> = {}
  for (const [k, v] of Object.entries(all)) next[k.startsWith(oldPrefix) ? newPrefix + k.slice(oldPrefix.length) : k] = v
  saved.set('custom', next)
  bump()
}

const newEntries = (g: PGroup, bump: () => void): Entry[] => [
  { label: 'New String Item', onSelect: () => createLeaf(g, 'text', bump) },
  { label: 'New Float Item', onSelect: () => createLeaf(g, 'float', bump) },
  { label: 'New Integer Item', onSelect: () => createLeaf(g, 'int', bump) },
  { label: 'New Unsigned Item', onSelect: () => createLeaf(g, 'uint', bump) },
  { label: 'New Boolean Item', onSelect: () => createLeaf(g, 'bool', bump) },
]
/** ParameterValue's menuEdit: Change Value, Remove/Rename Key (Key disabled for a real app
 *  setting — this UI's own code reads those by their fixed name, so renaming or removing one
 *  would just make it stop being read, silently; FreeCAD's own dialog has no such guard, but a
 *  user-created item has no code depending on its name, so those stay fully editable), New. */
const leafEntries = (g: PGroup, leaf: PLeaf, startEdit: () => void, bump: () => void): Entry[] => [
  { label: 'Change Value', bold: true, onSelect: startEdit },
  'sep',
  { label: 'Remove Key', disabled: !leaf.custom, onSelect: () => leaf.remove?.() },
  { label: 'Rename Key', disabled: !leaf.custom, onSelect: () => {
    const n = prompt('Rename Key\nEnter the name:', leaf.name)?.trim()
    if (n && n !== leaf.name && validName(n)) leaf.rename?.(n)
  } },
  'sep',
  { label: 'New', sub: newEntries(g, bump) },
]
/** ParameterGroup's menuEdit: Expand/Collapse, Add Sub-Group, Remove/Rename Group (disabled for
 *  the fixed groups above — Units, View, … — same reasoning as Remove/Rename Key). Export/Import
 *  Parameter (to an .FCParam file) are dropped: n/a with no filesystem access from a browser. */
const groupEntries = (g: PGroup, open: boolean, toggle: () => void, bump: () => void): Entry[] => [
  { label: open ? 'Collapse' : 'Expand', disabled: !g.groups.length, onSelect: toggle },
  'sep',
  { label: 'Add Sub-Group', onSelect: () => addSubGroup(g, bump) },
  { label: 'Remove Group', disabled: !g.custom, onSelect: () => removeGroupCustom(g, bump) },
  { label: 'Rename Group', disabled: !g.custom, onSelect: () => {
    const n = prompt('Rename Group\nEnter the name:', g.name)?.trim()
    if (n && n !== g.name && validName(n)) renameGroupCustom(g, n, bump)
  } },
]

/** A value cell: click (or the context menu's Change Value) edits it in place, FreeCAD's type
 *  handling per ParameterText/Int/UInt/Float/Bool::changeValue — a plain field for Text/Integer/
 *  Unsigned/Float (QInputDialog::getText/getInt/getDouble there), a two-way choice for Boolean
 *  (QInputDialog::getItem there). */
function PValueCell({ leaf, editing, onEditingChange }: { leaf: PLeaf; editing: boolean; onEditingChange(v: boolean): void }) {
  const commit = (raw: string) => {
    let v: unknown
    if (leaf.type === 'bool') v = raw === 'true'
    else if (leaf.type === 'float') v = Number(raw)
    else if (leaf.type === 'uint') v = Math.max(0, Math.round(Number(raw)))
    else if (leaf.type === 'int') v = Math.round(Number(raw))
    else { try { v = JSON.parse(raw) } catch { v = raw } }
    if (typeof v === 'number' && Number.isNaN(v)) { onEditingChange(false); return }
    leaf.write(v)
    onEditingChange(false)
  }
  const shown = typeof leaf.value === 'string' ? leaf.value : JSON.stringify(leaf.value)
  if (!editing) return <span className="pv edit" onClick={() => onEditingChange(true)}>{shown}</span>
  if (leaf.type === 'bool') {
    return (
      <QComboBox autoFocus defaultValue={String(leaf.value)} onChange={(e) => commit(e.target.value)} onBlur={() => onEditingChange(false)}>
        <option value="true">true</option><option value="false">false</option>
      </QComboBox>
    )
  }
  return (
    <input autoFocus defaultValue={shown} type={leaf.type === 'text' ? undefined : 'number'} step={leaf.type === 'float' ? 'any' : 1}
      onBlur={(e) => commit(e.currentTarget.value)}
      onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur(); if (e.key === 'Escape') onEditingChange(false) }} />
  )
}

function GroupRow({ g, depth, selected, onSelect, open, onToggle, onMenu, bump }:
  { g: PGroup; depth: number; selected: PGroup; onSelect(g: PGroup): void; open: Set<string>
    onToggle(path: string): void; onMenu(at: { x: number; y: number }, entries: Entry[]): void; bump(): void }) {
  const isOpen = open.has(g.path)
  return (
    <>
      <div className={cls('trow', selected === g && 'sel')} onClick={() => onSelect(g)}
        onContextMenu={(e) => { e.preventDefault(); onSelect(g); onMenu({ x: e.clientX, y: e.clientY }, groupEntries(g, isOpen, () => onToggle(g.path), bump)) }}>
        <span className="tlab" style={{ paddingLeft: depth * 14 }}>
          {g.groups.length
            ? <span className={cls('twisty', isOpen && 'open')} onClick={(e) => { e.stopPropagation(); onToggle(g.path) }} />
            : <span className="tindent" />}
          <span className="tname">{g.name}</span>
        </span>
      </div>
      {isOpen && g.groups.map((c) => (
        <GroupRow key={c.path} g={c} depth={depth + 1} selected={selected} onSelect={onSelect} open={open} onToggle={onToggle} onMenu={onMenu} bump={bump} />
      ))}
    </>
  )
}

export function ParameterEditorTask() {
  const [tick, setTick] = useState(0)
  const bump = () => setTick((t) => t + 1)
  const tree = useMemo(() => buildTree(bump), [tick]) // eslint-disable-line react-hooks/exhaustive-deps
  const [selectedPath, setSelectedPath] = useState('')
  const [open, setOpen] = useState<Set<string>>(() => new Set(tree.groups.map((g) => g.path)))
  const [editingKey, setEditingKey] = useState<string | null>(null)
  const [menu, setMenu] = useState<{ at: { x: number; y: number }; entries: Entry[] } | null>(null)
  const findGroup = (g: PGroup, path: string): PGroup | null => g.path === path ? g : g.groups.map((c) => findGroup(c, path)).find(Boolean) ?? null
  const selected = (selectedPath && findGroup(tree, selectedPath)) || tree.groups[0] || tree
  const toggle = (path: string) => setOpen((s) => { const n = new Set(s); if (n.has(path)) n.delete(path); else n.add(path); return n })
  const showMenu = (at: { x: number; y: number }, entries: Entry[]) => setMenu({ at, entries })

  return (
    <div className="tasks">
      <TaskBox title="Parameter Editor" icon="dlg-parameter">
        <p className="hint">User parameter: BaseApp/Preferences — this UI's own saved settings
          (localStorage, the "cadui." keys), shown and edited the way FreeCAD's Parameter Editor
          shows its ParameterGrp tree.</p>
        <div className="tree" style={{ maxHeight: 160, marginBottom: 8 }}>
          {tree.groups.map((g) => (
            <GroupRow key={g.path} g={g} depth={0} selected={selected} onSelect={(x) => setSelectedPath(x.path)} open={open} onToggle={toggle} onMenu={showMenu} bump={bump} />
          ))}
        </div>
        <div className="pgrid p3" onContextMenu={(e) => {
          e.preventDefault()
          showMenu({ x: e.clientX, y: e.clientY }, newEntries(selected, bump))
        }}>
          <div className="phead" style={COLS3}><span>Name</span><span>Type</span><span>Value</span></div>
          {!selected.leaves.length
            ? <p className="hint">No entries. Right-click for New.</p>
            : selected.leaves.map((leaf) => {
                const key = `${selected.path}/${leaf.name}`
                return (
                  <div key={leaf.name} className="prow" style={COLS3}
                    onContextMenu={(e) => { e.preventDefault(); e.stopPropagation(); showMenu({ x: e.clientX, y: e.clientY }, leafEntries(selected, leaf, () => setEditingKey(key), bump)) }}>
                    <span className="pk">{leaf.name}</span>
                    <span className="pv">{TYPE_LABEL[leaf.type]}</span>
                    <PValueCell leaf={leaf} editing={editingKey === key} onEditingChange={(v) => setEditingKey(v ? key : null)} />
                  </div>
                )
              })}
        </div>
      </TaskBox>
      <div className="tbuttons"><button className="qbtn default" onClick={closeTask}>Close</button></div>
      {menu && <ContextMenu at={menu.at} entries={menu.entries} onClose={() => setMenu(null)} />}
    </div>
  )
}
export const editParameters = () => openTask('parameterEditor', '') // Std_DlgParameter

// ── Std_SceneInspector (SceneInspector.cpp's DlgInspector) ──────────────────────────────────
function SceneRow({ node, depth }: { node: SceneNode; depth: number }) {
  const [open, setOpen] = useState(depth < 2) // DlgInspector::setNode expands to depth 3 (0-based here)
  return (
    <>
      <div className="trow">
        <span className="tlab" style={{ paddingLeft: depth * 14 }}>
          {node.children.length
            ? <span className={cls('twisty', open && 'open')} onClick={() => setOpen(!open)} />
            : <span className="tindent" />}
          <span className="tname">{node.type}{node.name ? ` "${node.name}"` : ''}</span>
        </span>
      </div>
      {open && node.children.map((c, i) => <SceneRow key={i} node={c} depth={depth + 1} />)}
    </>
  )
}
export function SceneInspectorTask() {
  const [tick, setTick] = useState(0)
  const tree = useMemo(() => getView()?.sceneTree() ?? null, [tick])
  return (
    <div className="tasks">
      <TaskBox title="Scene Inspector" icon="scene-inspector">
        <p className="hint">The three.js scene under the 3D view, node type and name per row — as
          SceneInspector.cpp's dialog shows Coin's own scene graph in FreeCAD.</p>
        <div className="tree" style={{ maxHeight: 280 }}>
          {!tree ? <p className="hint">No 3D view.</p> : <SceneRow node={tree} depth={0} />}
        </div>
      </TaskBox>
      <div className="tbuttons">
        <button className="qbtn" onClick={() => setTick((t) => t + 1)}>Refresh</button>
        <button className="qbtn default" onClick={closeTask}>Close</button>
      </div>
    </div>
  )
}
export const sceneInspector = () => openTask('sceneInspector', '') // Std_SceneInspector

// ── Std_DependencyGraph / Std_ExportDependencyGraph (GraphvizView.cpp, CommandDoc.cpp) ──────
// FreeCAD shells out to Graphviz (dot/unflatten) to lay out the document's real object graph and
// shows the resulting SVG, zoomable, in its own MDI view (GraphvizView). There's no Graphviz
// binary to call from a browser, and no Python-level object graph here either — the nearest
// thing this project has is each body's `part`/`used_by` (api.ts's Body), so that's what's
// drawn: one simple layered graph, laid out by hand instead of by `dot`, body name to body name,
// an edge for each "is used by". Shown in the one Tasks panel this UI has, not a separate view/
// tab — see ui/PARITY.md.
export type DepGraph = { nodes: { name: string; x: number; y: number }[]; edges: { from: string; to: string }[]; width: number; height: number }
const COL_W = 170, ROW_H = 44, PAD = 50, NODE_W = 120, NODE_H = 26
export function buildDependencyGraph(bodies: Body[]): DepGraph {
  const names = bodies.map((b) => b.name)
  const edges = bodies.flatMap((b) => (b.used_by ?? []).filter((u) => names.includes(u)).map((to) => ({ from: b.name, to })))
  const adj = new Map<string, string[]>()
  for (const e of edges) adj.set(e.from, [...(adj.get(e.from) ?? []), e.to])
  const indeg = new Map<string, number>(names.map((n) => [n, 0]))
  for (const e of edges) indeg.set(e.to, (indeg.get(e.to) ?? 0) + 1)
  const layer = new Map<string, number>(names.map((n) => [n, 0]))
  const queue = names.filter((n) => !indeg.get(n))
  const seen = new Set(queue)
  // Longest-path layering (Kahn-style); the guard keeps a cyclic graph (not expected for parts,
  // but cheap to guard) from looping forever.
  for (let qi = 0, guard = 0; qi < queue.length && guard < names.length * names.length + 10; qi++, guard++) {
    const n = queue[qi]
    for (const m of adj.get(n) ?? []) {
      layer.set(m, Math.max(layer.get(m) ?? 0, (layer.get(n) ?? 0) + 1))
      if (!seen.has(m)) { seen.add(m); queue.push(m) }
    }
  }
  for (const n of names) if (!seen.has(n)) layer.set(n, 0) // a cycle with no in-degree-0 entry: all at layer 0
  const byLayer = new Map<number, string[]>()
  for (const n of names) { const l = layer.get(n) ?? 0; byLayer.set(l, [...(byLayer.get(l) ?? []), n]) }
  const nodes = [...byLayer.entries()].sort((a, b) => a[0] - b[0])
    .flatMap(([l, ns]) => ns.map((n, i) => ({ name: n, x: PAD + l * COL_W, y: PAD + i * ROW_H })))
  const maxLayer = Math.max(0, ...byLayer.keys()), maxRows = Math.max(1, ...[...byLayer.values()].map((a) => a.length))
  return { nodes, edges, width: PAD * 2 + maxLayer * COL_W + NODE_W, height: PAD * 2 + (maxRows - 1) * ROW_H + NODE_H }
}
export function DependencyGraphTask() {
  const scene = useStore((s) => s.scene)
  const [tick, setTick] = useState(0)
  const graph = useMemo(() => buildDependencyGraph(scene?.bodies ?? []), [scene, tick])
  const pos = new Map(graph.nodes.map((n) => [n.name, n]))
  return (
    <div className="tasks">
      <TaskBox title="Dependency Graph" icon="dependency-graph">
        <p className="hint">The project's bodies and parts, and which uses which (a body's
          "used by") — GraphvizView.cpp's job, with `used_by` standing in for FreeCAD's real
          object dependencies.</p>
        {!graph.nodes.length ? <p className="hint">No bodies in the project.</p> : (
          <div className="depgraph-scroll">
            {/* Colours are inline (not just in tools.css) so the graph reads correctly even
                before that CSS is merged into freecad.css. */}
            <svg width={graph.width} height={graph.height} className="depgraph-svg">
              <defs>
                <marker id="dep-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                  <path d="M0,0 L10,5 L0,10 z" fill="var(--text, #000)" />
                </marker>
              </defs>
              {graph.edges.map((e, i) => {
                const a = pos.get(e.from), b = pos.get(e.to)
                if (!a || !b) return null
                return <line key={i} x1={a.x + NODE_W} y1={a.y + NODE_H / 2} x2={b.x} y2={b.y + NODE_H / 2}
                  stroke="var(--text, #000)" strokeOpacity={0.55} markerEnd="url(#dep-arrow)" />
              })}
              {graph.nodes.map((n) => (
                <g key={n.name} transform={`translate(${n.x},${n.y})`}>
                  <rect width={NODE_W} height={NODE_H} rx={4} fill="var(--lighten2, #f8f8f8)" stroke="var(--darken4, #bdbdbd)" />
                  <text x={NODE_W / 2} y={NODE_H / 2 + 4} textAnchor="middle" fill="var(--text, #000)" fontSize={11}>{n.name}</text>
                </g>
              ))}
            </svg>
          </div>
        )}
      </TaskBox>
      <div className="tbuttons">
        <button className="qbtn" onClick={() => setTick((t) => t + 1)}>Refresh</button>
        <button className="qbtn" onClick={exportDependencyGraph}>Export…</button>
        <button className="qbtn default" onClick={closeTask}>Close</button>
      </div>
    </div>
  )
}
export const dependencyGraph = () => openTask('dependencyGraph', '') // Std_DependencyGraph

function downloadText(name: string, text: string, type: string) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([text], { type }))
  a.download = name
  a.click()
  URL.revokeObjectURL(a.href)
}
/** FreeCAD's own Std_ExportDependencyGraph only writes the Graphviz (.gv) source (doc->
 *  exportGraphviz); since this UI already draws the graph as SVG rather than calling `dot` on
 *  that source, it saves both. */
function toDot(bodies: Body[], g: DepGraph): string {
  const lines = ['digraph Dependencies {', '  rankdir=LR;', '  node [shape=box];']
  for (const b of bodies) lines.push(`  "${b.name}";`)
  for (const e of g.edges) lines.push(`  "${e.from}" -> "${e.to}";`)
  lines.push('}')
  return lines.join('\n')
}
function toSvgString(g: DepGraph): string {
  const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;')
  const pos = new Map(g.nodes.map((n) => [n.name, n]))
  const edges = g.edges.map((e) => {
    const a = pos.get(e.from), b = pos.get(e.to)
    if (!a || !b) return ''
    return `<line x1="${a.x + NODE_W}" y1="${a.y + NODE_H / 2}" x2="${b.x}" y2="${b.y + NODE_H / 2}" stroke="#000" stroke-opacity="0.6" marker-end="url(#arrow)" />`
  }).join('')
  const nodes = g.nodes.map((n) =>
    `<g transform="translate(${n.x},${n.y})"><rect width="${NODE_W}" height="${NODE_H}" rx="4" fill="#f8f8f8" stroke="#bdbdbd" />` +
    `<text x="${NODE_W / 2}" y="${NODE_H / 2 + 4}" text-anchor="middle" font-size="11" font-family="sans-serif">${esc(n.name)}</text></g>`
  ).join('')
  return `<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" width="${g.width}" height="${g.height}" ` +
    `viewBox="0 0 ${g.width} ${g.height}"><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" ` +
    `orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" /></marker></defs>${edges}${nodes}</svg>`
}
export function exportDependencyGraph() { // Std_ExportDependencyGraph
  const bodies = getState().scene?.bodies ?? []
  if (!bodies.length) { report('warn', 'Export Dependency Graph: no project open'); return }
  const graph = buildDependencyGraph(bodies)
  downloadText('dependency-graph.gv', toDot(bodies, graph), 'text/vnd.graphviz')
  downloadText('dependency-graph.svg', toSvgString(graph), 'image/svg+xml')
  report('msg', 'Exported dependency-graph.gv and dependency-graph.svg')
}

// ── Std_ViewLoadImage (CommandView.cpp): load an image into the 3D view ─────────────────────
let imageInput: HTMLInputElement | null = null
export function loadImage() { // Std_ViewLoadImage
  if (!imageInput) {
    imageInput = document.createElement('input')
    imageInput.type = 'file'
    imageInput.accept = 'image/*'
    imageInput.style.display = 'none'
    document.body.appendChild(imageInput)
    imageInput.addEventListener('change', () => {
      const f = imageInput!.files?.[0]
      imageInput!.value = ''
      if (!f) return
      const reader = new FileReader()
      reader.onload = () => {
        getView()?.setImagePlane(String(reader.result))
        report('msg', `Loaded ${f.name} as an image plane in the 3D view (session-only)`)
      }
      reader.readAsDataURL(f)
    })
  }
  imageInput.click()
}

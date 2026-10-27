// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Assembly/InitGui.py: 2023 Ondsel
//   src/Mod/Assembly/CommandCreateAssembly.py: 2023 Ondsel
//   src/Mod/Assembly/CommandInsertLink.py: 2023 Ondsel
//   src/Mod/Assembly/CommandCreateJoint.py: 2023 Ondsel
//   src/Mod/Assembly/CommandSolveAssembly.py: 2023 Ondsel
//   src/Mod/Assembly/CommandExportASMT.py: 2023 Ondsel
//   src/Mod/Assembly/JointObject.py: 2023 Ondsel
//   src/Mod/Assembly/UtilsAssembly.py: 2023 Ondsel
//   src/Mod/Assembly/Gui/ViewProviderAssembly.cpp: 2023 Ondsel
//   src/Mod/Assembly/Gui/TaskAssemblyMessages.cpp: 2025 Pierre-Louis Boyer
//   src/Gui/View3DInventorViewer.cpp: 2004 Jürgen Riegel
//   src/Base/Rotation.cpp: 2006 Werner Mayer
//   No copyright line in the file: src/Mod/Assembly/Gui/Resources/panels/TaskAssemblyCreateJoint.ui,
//       src/Mod/Assembly/Gui/Resources/panels/TaskAssemblyInsertLink.ui
// The Assembly workbench, for the project's Assembly (assembly.py's ASSEMBLY: cad_agent/assembly_wb.py): the workbench's
// Assembly menu and its Assembly and Assembly Joints toolbars, the commands as FreeCAD's (Assembly_InsertLink,
// Assembly_CreateJoint<Type>, Assembly_ToggleGrounded, Assembly_SolveAssembly, Assembly_ExportASMT ...), the tree of the
// Assembly (its Joints group, the joints, the components), TaskAssemblyCreateJoint (picks in the 3D view, the panel's
// fields shown per type as adaptUi shows them, the solve previewed before OK), the Insert Component panel, the Solver
// messages panel, the property view of a joint, and dragging a part with the solver while the Assembly is in edit
// (ViewProviderAssembly::findDragMode, initMove, tryMouseMove, endMove), which runs FreeCAD's solver in the page
// (ondsel.ts). Every edit is `cad assembly apply` on the server (POST /api/<slug>/assembly), one undo step; the server
// replays JointObject.py's sequence (presolve, solve, accept) and writes the solved placements back.
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import * as THREE from 'three'
import { api, resultText } from './api'
import { consoleLog, getState, report, setState, useStore } from './store'
import { closeTask, getView, loadHistory, openTask, select } from './actions'
import { Icon, type IconName } from './icons'
import { cls, Group, Row, TaskBox } from './panels'
import { QuantityBox, LENGTH, ANGLE, NUMBER } from './qsb'
import { axisAngleOf, quatOfYpr, yprOfQuat } from './rotation'
import { QComboBox } from './combo'
import { messageBox } from './msgbox'
import type { Entry } from './chrome'
import type { TreeCtx } from './partdesign'
import { loadAssemblySolver, type AsmDoc, type AsmResult, type Plc } from './ondsel'
import type { NavEvent, V2 } from './nav'

// ── the model (cad_agent/assembly_edit.py's read/solved) ──────────────────────────────────────────────────────────
export interface AsmObj { name: string; kind: 'Link' | 'GroundedJoint' | 'Joint' | 'RigidGroupJoint'; type: string; label?: string | null; [k: string]: unknown }
export interface AsmRow {
  name: string; label: string; type: string; depth: number; icon: string
  linked_object?: string; grounded?: boolean; joint_type?: string; suppressed?: boolean; object_to_ground?: string
  members?: string[]
}
export interface AsmView {
  project: string; assembly: boolean; objects: AsmObj[]; tree: AsmRow[]
  placements?: Record<string, Plc>
  jcs?: Record<string, { placement1: Plc; placement2: Plc; global1: Plc; global2: Plc }>
  solver?: AsmDoc
  status?: { state: string; text: string; link: string } | null
  messages?: { kind: string; text: string }[]
  dof?: number | null
  done?: string[]
}
type Ref = [string, string[]]

export const JOINT_TYPES = ['Fixed', 'Revolute', 'Cylindrical', 'Slider', 'Ball', 'Distance', 'Parallel', 'Perpendicular', 'Angle',
  'RackPinion', 'Screw', 'Gears', 'Belt'] as const
export type JointType = (typeof JOINT_TYPES)[number]
// JointObject.py's lists
const USING_ANGLE = ['Angle'], USING_DISTANCE = ['Distance', 'RackPinion', 'Screw', 'Gears', 'Belt'], USING_DISTANCE2 = ['Gears', 'Belt']
const NO_NEGATIVE_DISTANCE = ['Gears', 'Belt'], USING_OFFSET = ['Fixed', 'Revolute'], USING_ROTATION = ['Fixed', 'Slider']
const USING_REVERSE = ['Fixed', 'Revolute', 'Cylindrical', 'Slider', 'Distance', 'Parallel']
const USING_LIMIT_LENGTH = ['Cylindrical', 'Slider'], USING_LIMIT_ANGLE = ['Revolute', 'Cylindrical']
const JOINT_MENU: Record<JointType, [string, string]> = {   // GetResources: MenuText and Accel
  Fixed: ['Fixed Joint', 'F'], Revolute: ['Revolute Joint', 'R'], Cylindrical: ['Cylindrical Joint', 'C'], Slider: ['Slider Joint', 'S'],
  Ball: ['Ball Joint', 'B'], Distance: ['Distance Joint', 'D'], Parallel: ['Parallel Joint', 'N'], Perpendicular: ['Perpendicular Joint', 'M'],
  Angle: ['Angle Joint', 'X'], RackPinion: ['Rack and Pinion Joint', 'Q'], Screw: ['Screw Joint', 'W'], Gears: ['Gears Joint', 'T'], Belt: ['Belt Joint', 'L'],
}
const jointIcon = (t: string): IconName => (`as-${t}` in ICONS ? `as-${t}` : 'as-Fixed') as IconName
const ICONS: Record<string, true> = Object.fromEntries(JOINT_TYPES.map((t) => [`as-${t}`, true]))

const msg = (e: unknown) => (e instanceof Error ? e.message : String(e))
/** A QComboBox of items, by index. */
function Combo({ value, items, onChange, name }: { value: number; items: readonly string[]; onChange(i: number): void; name?: string }) {
  return <QComboBox data-qf={name} value={String(value)} onChange={(e) => onChange(Number(e.target.value))}>
    {items.map((t, i) => <option key={t} value={i}>{t}</option>)}</QComboBox>
}
export const asmObject = (v: AsmView | null | undefined, name: string) => v?.objects.find((o) => o.name === name)
export const components = (v: AsmView | null | undefined) => (v?.objects ?? []).filter((o) => o.kind === 'Link')
export const isComponent = (name: string) => components(getState().assembly).some((o) => o.name === name)
const labelOf = (o: AsmObj) => (typeof o.label === 'string' && o.label ? o.label : o.name)

/** `cad assembly show`: the Assembly, recomputed, into the store (null when the project has none). */
export async function loadAssembly() {
  const slug = getState().slug
  if (!slug) return
  try {
    const r = await api.assembly(slug)
    if (slug !== getState().slug) return
    if (r.exit !== 0) { setState({ assembly: null }); if (r.data?.error) report('warn', `Assembly: ${resultText(r)}`); return }
    const v = r.data as unknown as AsmView
    setState((s) => ({ assembly: v.assembly ? v : null, asmSel: s.asmSel.filter((n) => !!asmObject(v, n) || n === 'Assembly' || n === 'Joints'),
      asmActive: s.asmActive && v.assembly }))
    for (const m of v.messages ?? []) report(levelOf(m.kind), m.text)
  } catch (e) { report('err', `Assembly: ${msg(e)}`) }
}
/** A Console line's level: PrintError, PrintWarning, PrintMessage. */
const levelOf = (kind: string) => (kind === 'error' ? 'err' : kind === 'message' ? 'msg' : 'warn')
/** `cad assembly apply`: one undo step named `name` (FreeCAD's transaction), echoed to the Python console's
 *  counterpart as the command line. The Assembly after it goes into the store. */
export async function applyAssembly(ops: Record<string, unknown>[], name?: string): Promise<AsmView | null> {
  const s = getState()
  if (!s.slug) return null
  if (s.scriptToPyConsole) consoleLog('in', `cad assembly apply ${s.slug} --ops '${JSON.stringify(ops)}'${name ? ` --name '${name}'` : ''}`)
  try {
    const r = await api.applyAssembly(s.slug, ops, name)
    if (r.exit !== 0) { report('err', `${name ?? 'Assembly'}: ${resultText(r)}`); return null }
    const doc = r.data?.doc as unknown as AsmView
    setState({ assembly: doc?.assembly ? doc : null })
    for (const m of doc?.messages ?? []) report(levelOf(m.kind), m.text)
    report('msg', String(r.data?.step ?? name ?? 'Assembly'))
    loadHistory()
    return doc
  } catch (e) { report('err', `${name ?? 'Assembly'}: ${msg(e)}`); return null }
}
/** The ops' result without writing anything (a panel's preview before OK). */
async function previewAssembly(ops: Record<string, unknown>[]): Promise<AsmView | null> {
  const s = getState()
  if (!s.slug) return null
  try {
    const r = await api.applyAssembly(s.slug, ops, undefined, true)
    if (r.exit !== 0) { report('warn', resultText(r)); return null }
    return r.data?.doc as unknown as AsmView
  } catch (e) { report('warn', msg(e)); return null }
}

// ── placements: the scene's, and the view drawn at a solve's ─────────────────────────────────────────────────────
const plcMatrix = (p: Plc) => new THREE.Matrix4().compose(new THREE.Vector3(...p.base), new THREE.Quaternion(...p.rotation), new THREE.Vector3(1, 1, 1))
function sceneMatrix(name: string): THREE.Matrix4 | null {
  const b = getState().scene?.bodies.find((x) => x.name === name) as { matrix?: number[] | null } | undefined
  if (!b?.matrix || b.matrix.length !== 16) return null
  return new THREE.Matrix4().set(...(b.matrix as [number, number, number, number, number, number, number, number, number, number, number, number, number, number, number, number]))
}
/** The components drawn where `placements` puts them (a preview; null: where the scene has them). */
export function showPlacements(placements: Record<string, Plc> | null) {
  const view = getView()
  if (!view) return
  if (!placements) { view.placeBodies(null); return }
  const deltas: Record<string, THREE.Matrix4> = {}
  for (const [n, p] of Object.entries(placements)) {
    const m0 = sceneMatrix(n)
    if (m0) deltas[n] = plcMatrix(p).multiply(m0.clone().invert())
  }
  view.placeBodies(deltas)
}

// ── Base::Placement and Base::Rotation, as far as the drag uses them ───────────────────────────────────────────
type V3 = [number, number, number]
const add = (a: V3, b: V3): V3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]]
const sub = (a: V3, b: V3): V3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
const dot = (a: V3, b: V3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
const cross = (a: V3, b: V3): V3 => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
const len = (a: V3) => Math.sqrt(dot(a, a))
const scale = (a: V3, k: number): V3 => [a[0] * k, a[1] * k, a[2] * k]
type Q4 = [number, number, number, number]
const qnorm = (q: Q4): Q4 => { const n = Math.hypot(...q); return n > 0 ? [q[0] / n, q[1] / n, q[2] / n, q[3] / n] : q }
/** Rotation::multRight (normalised, as setValue normalises). */
const qmul = (a: Q4, b: Q4): Q4 => {
  const [x0, y0, z0, w0] = a, [x1, y1, z1, w1] = b
  return qnorm([w0 * x1 + x0 * w1 + y0 * z1 - z0 * y1, w0 * y1 - x0 * z1 + y0 * w1 + z0 * x1, w0 * z1 + x0 * y1 - y0 * x1 + z0 * w1, w0 * w1 - x0 * x1 - y0 * y1 - z0 * z1])
}
const qinv = (q: Q4): Q4 => [-q[0], -q[1], -q[2], q[3]]
function qrot(q: Q4, v: V3): V3 {
  const [x, y, z, w] = q, x2 = x * x, y2 = y * y, z2 = z * z, w2 = w * w
  return [(x2 + w2 - y2 - z2) * v[0] + 2 * (x * y - z * w) * v[1] + 2 * (x * z + y * w) * v[2],
    2 * (x * y + z * w) * v[0] + (w2 - x2 + y2 - z2) * v[1] + 2 * (y * z - x * w) * v[2],
    2 * (x * z - y * w) * v[0] + 2 * (x * w + y * z) * v[1] + (w2 - x2 - y2 + z2) * v[2]]
}
/** Rotation(axis, angle) (setValue(axis, angle): not normalised). */
function qaxis(axis: V3, angle: number): Q4 {
  const the = angle - Math.floor(angle / (2 * Math.PI)) * (2 * Math.PI)
  const n = len(axis), a = n > 0 ? scale(axis, 1 / n) : [0, 0, 1] as V3, s = Math.sin(the / 2)
  return [a[0] * s, a[1] * s, a[2] * s, Math.cos(the / 2)]
}
/** Rotation::setValue(rotateFrom, rotateTo). */
function qfromto(u0: V3, v0: V3): Q4 {
  const u = scale(u0, 1 / len(u0)), v = scale(v0, 1 / len(v0)), d = dot(u, v), w = cross(u, v)
  if (len(w) === 0) {
    if (d > 0) return [0, 0, 0, 1]
    let t = cross(u, [1, 0, 0]); if (len(t) < 2.220446049250313e-16) t = cross(u, [0, 1, 0])
    return qnorm([t[0], t[1], t[2], 0])
  }
  return qaxis(w, Math.acos(d))
}
interface P { pos: V3; rot: Q4 }
const P0: P = { pos: [0, 0, 0], rot: [0, 0, 0, 1] }
const pmul = (a: P, b: P): P => ({ pos: add(a.pos, qrot(a.rot, b.pos)), rot: qmul(a.rot, b.rot) })
const pinv = (a: P): P => { const r = qinv(a.rot); return { pos: scale(qrot(r, a.pos), -1), rot: r } }
const ofPlc = (p: Plc): P => ({ pos: [...p.base] as V3, rot: [...p.rotation] as Q4 })
const toPlc = (p: P): Plc => ({ base: [...p.pos] as V3, rotation: [...p.rot] as Q4 })
/** Vector3::GetAngle and GetAngleOriented. */
function angleOf(a: V3, b: V3) {
  const l1 = len(a), l2 = len(b)
  if (l1 <= 2.220446049250313e-16 || l2 <= 2.220446049250313e-16) return NaN
  const d = dot(a, b) / l1 / l2
  return d <= -1 ? Math.PI : d >= 1 ? 0 : Math.acos(d)
}
function angleOriented(a: V3, b: V3, norm: V3) { const g = angleOf(a, b); return dot(cross(a, b), norm) < 0 ? 2 * Math.PI - g : g }

// ── the menu, the toolbars, the commands (InitGui.py, the Command*.py files) ─────────────────────────────────────
const NA = (label: string, icon: IconName, cmd: string, why: string): Entry => ({ label, icon, cmd, disabled: true, title: `n/a: ${why}` })
function asmState() {
  const s = getState()
  const v = s.assembly
  const active = !!v && s.asmActive && !s.task                      // UtilsAssembly.isAssemblyCommandActive
  // isCreateJointActive / CommandToggleGrounded: an active assembly with a component at least
  return { s, v, has: !!v, active, parts: active && components(v).length >= 1, doc: !!s.slug }
}
/** Activate the Assembly (Assembly_ActivateAssembly, a double-click on it): it is in edit, parts drag with the solver. */
export function activateAssembly(on = true) {
  setState({ asmActive: on })
  if (on) report('msg', 'Assembly: in edit (drag a part to move it with the solver; Escape leaves)')
}
async function createAssembly() {
  const { has } = asmState()
  if (has) return void messageBox('warning', 'New Assembly', 'Sub-assemblies (an Assembly in the active one) are not ported: a sub-project is assembly.py\'s SUBASSEMBLIES.')
  if (await applyAssembly([{ op: 'new' }], 'New assembly')) activateAssembly(true)
}
async function solveAssembly() {
  if (!asmState().has) return
  await applyAssembly([{ op: 'solve' }], 'Solve Assembly')
}
async function toggleGrounded() {
  const { s, v } = asmState()
  const comps = s.selected.filter((n) => isComponent(n))
  const joints = s.asmSel.filter((n) => asmObject(v, n)?.kind === 'GroundedJoint')
  const names = [...comps, ...joints.map((n) => String(asmObject(v, n)!.object_to_ground))]
  if (!names.length) return void messageBox('warning', 'Toggle Grounded', 'Select the part to ground, please.')
  await applyAssembly(names.map((name) => ({ op: 'ground', name })), 'Toggle grounded')
}
/** Assembly_CreateJointRigidGroup: the selected components locked together (createJointRigidGroupJoint); fewer than
 *  two, the Console's warning and nothing made. */
async function createRigidGroup() {
  const { s } = asmState()
  const parts = s.selected.filter((n) => isComponent(n))
  if (!s.selected.length) return
  if (parts.length < 2) return void report('warn', 'Select at least 2 components to create a rigid group')
  await applyAssembly([{ op: 'rigid', parts }], 'Create Rigid Group')
}
async function exportAsmt() {
  const s = getState()
  if (!s.slug) return
  try {
    const r = await api.cad(s.slug, ['assembly', 'asmt', s.slug])
    if (r.exit !== 0) { report('err', `Export ASMT File: ${resultText(r)}`); return }
    const blob = new Blob([String(r.data?.asmt ?? '')], { type: 'text/plain' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob); a.download = `${s.slug}.asmt`; a.click()
    setTimeout(() => URL.revokeObjectURL(a.href), 1000)
  } catch (e) { report('err', `Export ASMT File: ${msg(e)}`) }
}
/** Assembly_SelectJointsOfComponent: the joints of the selected components selected in the tree. */
function selectJointsOf() {
  const { s, v } = asmState()
  const comps = new Set(s.selected.filter((n) => isComponent(n)))
  const joints = (v?.objects ?? []).filter((o) => (o.kind === 'Joint' && [o.reference1, o.reference2].some((r) => Array.isArray(r) && comps.has(String(r[0]))))
    || (o.kind === 'GroundedJoint' && comps.has(String(o.object_to_ground)))).map((o) => o.name)
  setState({ asmSel: joints, featSel: [] })
}
export function openJoint(type: JointType, edit?: string) {
  if (!asmState().has) return
  openTask('assembly', 'joint', edit ? `${type}:${edit}` : type)
}
// isCreateJointActive is false: why the joint commands are greyed
const NO_JOINT = 'needs an active assembly with a component (double-click the Assembly, then Insert Component)'
function jointEntries(): Entry[] {
  const { parts: active } = asmState()
  return JOINT_TYPES.filter((t) => t !== 'Gears' && t !== 'Belt').map((t) => ({ label: JOINT_MENU[t][0], icon: jointIcon(t), cmd: `Assembly_CreateJoint${t}`,
    kbd: JOINT_MENU[t][1], disabled: !active, title: active ? undefined : NO_JOINT, onSelect: () => openJoint(t) }))
}
function gearEntries(): Entry[] {
  const { parts: active } = asmState()
  return (['Gears', 'Belt'] as const).map((t) => ({ label: JOINT_MENU[t][0], icon: jointIcon(t), cmd: `Assembly_CreateJoint${t}`, kbd: JOINT_MENU[t][1],
    disabled: !active, title: active ? undefined : NO_JOINT, onSelect: () => openJoint(t) }))
}
function insertEntries(): Entry[] {
  const { active } = asmState()
  return [
    { label: 'Insert Component', icon: 'as-insert', cmd: 'Assembly_InsertLink', kbd: 'I', disabled: !active, onSelect: () => openTask('assembly', 'insert', 'insert') },
    NA('New Part', 'std-part', 'Assembly_InsertNewPart', 'a component is a part file of the project: make the part (File > New), then insert it'),
  ]
}
/** The Assembly toolbar's and menu's commands (cmdList of InitGui.py), the menu-only ones and the joints'. */
function cmdList(): Entry[] {
  const { has, active, doc } = asmState()
  const ins = insertEntries()
  return [
    // EnforceOneAssemblyRule: with an assembly that is not active, no second root one; with one in edit, a sub-assembly
    { label: 'New Assembly', icon: 'as-assembly', cmd: 'Assembly_CreateAssembly', kbd: 'A', disabled: !doc || (has && !getState().asmActive), onSelect: () => void createAssembly() },
    { label: 'Insert Component', icon: 'as-insert', cmd: 'Assembly_Insert', sub: ins },
    NA('Link Arrays', 'link', 'Part_LinkArrays', 'link arrays are not ported: insert the part several times'),
    { label: 'Solve Assembly', icon: 'as-solve', cmd: 'Assembly_SolveAssembly', kbd: 'Z', disabled: !has || !active, onSelect: () => void solveAssembly() },
    NA('Exploded View', 'as-exploded', 'Assembly_CreateView', 'exploded views are not ported yet (poses show the machine moved: CADAgent_Pose)'),
    NA('Snapshot', 'shot', 'Assembly_CreateSnapshot', 'snapshots are not ported'),
    NA('Simulation', 'as-simulation', 'Assembly_CreateSimulation', 'simulations (motions) are not ported'),
    NA('Bill of Materials', 'as-bom', 'Assembly_CreateBom', 'the bill of materials is `cad bom` (CAD Agent > Bill of Materials)'),
  ]
}
function jointsToolbar(): Entry[] {
  const { parts } = asmState()
  const g = gearEntries()
  return [
    { label: 'Toggle Grounded', icon: 'as-ground', cmd: 'Assembly_ToggleGrounded', kbd: 'G', disabled: !parts, onSelect: () => void toggleGrounded() },
    // IsActive: isAssemblyCommandActive and assembly_has_at_least_n_parts(2)
    { label: 'Create Rigid Group', icon: 'as-rigid', cmd: 'Assembly_CreateJointRigidGroup', kbd: 'Y', disabled: !(asmState().active && components(asmState().v).length >= 2),
      title: asmState().active && components(asmState().v).length >= 2 ? undefined : 'needs an active assembly with 2 components at least', onSelect: () => void createRigidGroup() },
    'sep', ...jointEntries().slice(0, 5), 'sep', ...jointEntries().slice(5, 9), 'sep', ...jointEntries().slice(9),
    { label: 'Gears/Belt Joint', icon: 'as-Gears', cmd: 'Assembly_CreateJointGearBelt', sub: g },
  ]
}
/** The "&Assembly" menu (InitGui.py: cmdList + cmdListMenuOnly + Separator + cmdListJoints). */
export function assemblyMenu(): Entry[] {
  const { s, has, active } = asmState()
  return [
    ...cmdList(),
    { ...(NA('Go to Linked Assembly', 'link', 'Assembly_LinkSelectLinked', 'sub-assemblies (AssemblyLink) are not ported') as Exclude<Entry, 'sep'>), kbd: 'S, G' },
    { label: 'Export ASMT File', icon: 'as-asmt', cmd: 'Assembly_ExportASMT', disabled: !active, onSelect: () => void exportAsmt() },
    { label: 'Select Component Joints', icon: 'as-select-joints', cmd: 'Assembly_SelectJointsOfComponent', disabled: !has || !s.selected.some(isComponent),
      onSelect: selectJointsOf },
    'sep', ...jointsToolbar(),
  ]
}
export function assemblyToolbars(): [string, Entry[]][] {
  return [['Assembly', cmdList()], ['Assembly Joints', jointsToolbar()]]
}
export function assemblyMenus() {
  const plain = (es: Entry[]): unknown[] => es.map((e) => (e === 'sep' ? { sep: true } : { text: e.label, cmd: e.cmd ?? null, enabled: !e.disabled, ...(e.sub ? { menu: plain(e.sub) } : {}) }))
  return { assembly: plain(assemblyMenu()), toolbars: assemblyToolbars().map(([title, es]) => ({ title, buttons: plain(es) })) }
}
export function assemblyCommands(): [string, Exclude<Entry, 'sep'>][] {
  const out: [string, Exclude<Entry, 'sep'>][] = []
  const walk = (es: Entry[]) => { for (const e of es) { if (e === 'sep') continue; if (e.cmd && e.onSelect && !out.some(([c]) => c === e.cmd)) out.push([e.cmd, e]); if (e.sub) walk(e.sub) } }
  walk(assemblyMenu())
  out.push(['Assembly_ActivateAssembly', { label: 'Activate Assembly', icon: 'as-activate', cmd: 'Assembly_ActivateAssembly', disabled: !asmState().has || getState().asmActive, onSelect: () => activateAssembly(true) }])
  return out
}
export const assemblyRun = (cmd: string) => assemblyCommands().find(([c]) => c === cmd)?.[1].onSelect?.()
export const assemblyEnabled = (cmd: string) => { const e = assemblyCommands().find(([c]) => c === cmd)?.[1]; return !!e && !e.disabled }

// ── the tree (the Assembly, its Joints group, the joints, the components) ────────────────────────────────────────
function rowIcon(r: AsmRow): IconName {
  if (r.type === 'Assembly::AssemblyObject') return 'as-assembly'
  if (r.type === 'Assembly::JointGroup') return 'as-joints'
  if (r.type === 'App::Origin') return 'std-origin'
  if (r.type === 'App::Line') return 'std-axis'
  if (r.type === 'App::Plane') return 'std-plane'
  if (r.type === 'App::Point') return 'std-point'
  if (r.type === 'GroundedJoint') return 'as-ground'
  if (r.type === 'RigidGroupJoint') return 'as-rigid'
  if (r.type === 'Joint') return jointIcon(r.joint_type ?? 'Fixed')
  return 'link'
}
/** The Assembly's rows, as FreeCAD's tree shows an Assembly: under it the Joints group (its GroundedJoints and joints, in
 *  the group's order) and the components, each an App::Link (the part it links in the Description column). */
export function AssemblyRows({ ctx, onMenu }: { ctx: TreeCtx; onMenu(at: { x: number; y: number }): void }) {
  const v = useStore((s) => s.assembly), asmSel = useStore((s) => s.asmSel), selected = useStore((s) => s.selected), active = useStore((s) => s.asmActive)
  const hidden = useStore((s) => s.hidden), pre = useStore((s) => s.preselected)
  const [open, setOpen] = useState<Record<string, boolean>>({ Assembly: true, Joints: true, Origin: false })
  if (!v) return null
  const pickRow = (name: string, e: React.MouseEvent) => {
    ctx.cancelPreselect()
    if (treePick?.(name)) return                    // a joint panel's selection observer takes a tree selection too
    if (isComponent(name)) { select(name, e.metaKey || e.ctrlKey); setState({ asmSel: [], featSel: [] }); return }
    select(null)
    setState((s) => ({ asmSel: e.metaKey || e.ctrlKey ? (s.asmSel.includes(name) ? s.asmSel.filter((x) => x !== name) : [...s.asmSel, name]) : [name], featSel: [] }))
  }
  const rows: ReactNode[] = []
  for (const r of v.tree) {
    const under = r.depth === 2 ? (r.type.startsWith('App::') && r.type !== 'App::Link' ? 'Origin' : 'Joints') : null
    if (under && !open[under]) continue
    if (r.depth >= 1 && !open.Assembly) continue
    const isComp = r.type === 'App::Link'
    const sel = isComp ? selected.includes(r.name) : asmSel.includes(r.name)
    const off = isComp && hidden.includes(r.name)
    const twisty = r.type === 'Assembly::AssemblyObject' || r.type === 'Assembly::JointGroup' || r.type === 'App::Origin'
    const desc = isComp ? (r.linked_object ?? '') : r.type === 'Joint' ? (r.joint_type ?? '') : r.type === 'GroundedJoint' ? (r.object_to_ground ?? '') : ''
    rows.push(
      <div key={r.name} className={cls('trow', 'asrow', sel && 'sel', pre === r.name && 'pre', off && 'hid', r.suppressed && 'hid')} data-ref={`assembly/${r.name}`} data-name={isComp ? r.name : undefined}
        onClick={(e) => pickRow(r.name, e)} onMouseEnter={() => ctx.enter(isComp ? r.name : null)}
        onDoubleClick={() => {
          if (r.type === 'Assembly::AssemblyObject') activateAssembly(!getState().asmActive)
          else if (r.type === 'Joint') openJoint((r.joint_type ?? 'Fixed') as JointType, r.name)
        }}
        onContextMenu={(e) => { e.preventDefault(); if (!sel) pickRow(r.name, e); onMenu({ x: e.clientX, y: e.clientY }) }}>
        <span className="tlab"><span className="pdindent" style={{ width: 6 + 12 * r.depth }} />
          {twisty ? <span className={cls('twisty', open[r.name] ? 'open' : '')} onClick={(e) => { e.stopPropagation(); setOpen((o) => ({ ...o, [r.name]: !o[r.name] })) }} /> : <span className="tindent" />}
          <span className="ticon"><Icon name={rowIcon(r)} size={ctx.iconSize} />{r.grounded && <Icon name="as-ground" className="tov" size={10} />}</span>
          <span className="tname" style={r.type === 'Assembly::AssemblyObject' && active ? { fontWeight: 700 } : undefined}>{r.label}</span></span>
        {ctx.showDesc && <span className="tdesc">{desc}</span>}
        {ctx.showInternal && <span className="tdesc">{r.name}</span>}
      </div>)
  }
  return <>{rows}</>
}
/** The tree's context menu on Assembly rows. */
export function assemblyTreeEntries(): Entry[] {
  const { s, v } = asmState()
  const sel = s.asmSel.map((n) => asmObject(v, n)).filter((o): o is AsmObj => !!o)
  const one = sel.length === 1 ? sel[0] : null
  return [
    ...(s.asmSel.includes('Assembly') ? [{ label: s.asmActive ? 'Leave Edit Mode' : 'Activate Assembly', icon: 'as-activate' as IconName, onSelect: () => activateAssembly(!s.asmActive) }] : []),
    { label: 'Edit', disabled: one?.kind !== 'Joint', onSelect: () => one && openJoint(String(one.joint_type) as JointType, one.name) },
    { label: one?.suppressed ? 'Unsuppress' : 'Suppress', disabled: one?.kind !== 'Joint' && one?.kind !== 'RigidGroupJoint',
      onSelect: () => one && void applyAssembly([{ op: 'set', name: one.name, props: { suppressed: !one.suppressed } }], 'Toggle suppress') },
    // ViewProviderRigidGroupJoint.setupContextMenu
    ...(one?.kind === 'RigidGroupJoint' ? [{ label: 'Update Stored Positions', icon: 'as-rigid' as IconName,
      onSelect: () => void (one.suppressed ? applyAssembly([{ op: 'update_rigid', name: one.name }], 'Update Stored Positions')
        : report('warn', "Assembly: 'updateStoredPositions' is only available while suppressed.")) }] : []),
    { label: 'Rename', kbd: 'F2', disabled: !one, onSelect: () => one && renameObject(one.name) },
    { label: 'Delete', kbd: 'Del', disabled: !sel.length, onSelect: () => void deleteAssemblyObjects(sel.map((o) => o.name)) },
  ]
}
async function renameObject(name: string) {
  const o = asmObject(getState().assembly, name)
  if (!o) return
  const to = window.prompt('Label', labelOf(o))
  if (to === null || to === labelOf(o)) return
  await applyAssembly([{ op: 'label', name, to }], `Rename ${name}.Label`)
}
export async function deleteAssemblyObjects(names: string[]) {
  if (!names.length) return
  await applyAssembly(names.map((name) => ({ op: 'delete', name })), 'Delete')
  setState({ asmSel: [] })
}

// ── the panels ──────────────────────────────────────────────────────────────────────────────────────────────────
/** TaskAssemblyMessages ("Solver messages"): ViewProviderAssembly::UpdateSolverInformation's line. */
export function SolverMessages() {
  const v = useStore((s) => s.assembly)
  if (!v) return null
  const st = v.status ?? { state: 'empty', text: 'Empty Assembly', link: '' }
  return <TaskBox title="Solver messages" icon="as-assembly">
    <div className="as-solver" data-state={st.state}>
      <span>{st.text}</span>{st.link && <a href="#" onClick={(e) => { e.preventDefault(); selectByLink(st.state) }}>{st.link}</a>}
    </div>
  </TaskBox>
}
function selectByLink(state: string) {
  const v = getState().assembly
  if (!v) return
  if (state === 'conflicting_constraints') {
    const m = /\((.*)\)/.exec(v.status?.link ?? '')
    const labels = (m?.[1] ?? '').split(', ')
    setState({ asmSel: v.objects.filter((o) => labels.includes(labelOf(o))).map((o) => o.name), featSel: [] })
  }
}
/** The task watchers of InitGui.py (Create, Activate, Insert, Grounding, Constraints, Tools, Simulation), shown in the
 *  Tasks panel with no task open, each a box of its commands; the Solver messages panel with them while the Assembly
 *  is in edit. */
export function AssemblyWatchers() {
  const v = useStore((s) => s.assembly), active = useStore((s) => s.asmActive), slug = useStore((s) => s.slug)
  useStore((s) => s.selected)
  if (!slug) return null
  const cmds = Object.fromEntries(assemblyCommands())
  const box = (title: string, names: string[]) => <TaskBox title={title} icon="as-assembly">
    {names.map((c, i) => c === 'Separator' ? <hr key={i} /> : cmds[c] ? <button key={c} className="qbtn as-watch" data-cmd={c} disabled={cmds[c].disabled}
      onClick={() => cmds[c].onSelect?.()}><Icon name={cmds[c].icon ?? 'as-assembly'} size={16} /> {cmds[c].label}</button>
      : <button key={c} className="qbtn as-watch" data-cmd={c} disabled><Icon name="as-assembly" size={16} /> {NOT_HERE[c] ?? c}</button>)}
  </TaskBox>
  const n = components(v).length
  const grounded = (v?.objects ?? []).some((o) => o.kind === 'GroundedJoint')
  const motion = (v?.objects ?? []).some((o) => o.kind === 'Joint' && ['Revolute', 'Slider', 'Cylindrical'].includes(String(o.joint_type)))
  return <>
    {!v && box('Create', ['Assembly_CreateAssembly'])}
    {v && !active && box('Activate', ['Assembly_ActivateAssembly'])}
    {v && active && box('Insert', ['Assembly_InsertLink', 'Assembly_InsertNewPart'])}
    {v && active && n >= 1 && !grounded && box('Grounding', ['Assembly_ToggleGrounded'])}
    {v && active && n >= 2 && box('Constraints', ['Assembly_CreateJointFixed', 'Assembly_CreateJointRevolute', 'Assembly_CreateJointCylindrical',
      'Assembly_CreateJointSlider', 'Assembly_CreateJointBall', 'Separator', 'Assembly_CreateJointDistance', 'Assembly_CreateJointParallel',
      'Assembly_CreateJointPerpendicular', 'Assembly_CreateJointAngle'])}
    {v && active && n >= 1 && box('Tools', ['Assembly_CreateView', 'Assembly_CreateBom'])}
    {v && active && motion && box('Simulation', ['Assembly_CreateSimulation'])}
    {v && active && <SolverMessages />}
  </>
}
/** The watchers' commands that are greyed here (assemblyMenu's NA entries have no onSelect). */
const NOT_HERE: Record<string, string> = { Assembly_InsertNewPart: 'New Part', Assembly_CreateView: 'Exploded View',
  Assembly_CreateBom: 'Bill of Materials', Assembly_CreateSimulation: 'Simulation' }
export function AssemblyTask({ body, other }: { body: string; other: string }) {
  if (body === 'insert') return <InsertTask />
  const [type, edit] = other.split(':')
  return <JointTask key={other} type0={type as JointType} edit={edit} />
}

/** TaskAssemblyInsertLink: the project's parts; each one clicked goes in (OK inserts them, the first one of an
 *  ungrounded Assembly grounded: GroundFirstPart). */
function InsertTask() {
  const features = useStore((s) => s.features), scene = useStore((s) => s.scene)
  const [filter, setFilter] = useState('')
  const [picked, setPicked] = useState<string[]>([])
  const parts = useMemo(() => [...new Set([...Object.keys(features), ...(scene?.bodies.map((b) => b.part).filter((p): p is string => !!p) ?? [])])].sort(), [features, scene])
  const shown = parts.filter((p) => !filter || p.toLowerCase().includes(filter.toLowerCase()))
  const counts = (p: string) => picked.filter((x) => x === p).length
  const ok = async () => {
    closeTask()
    if (!picked.length) return
    await applyAssembly(picked.map((part) => ({ op: 'insert', part })), 'Insert Component')
  }
  return <div className="tasks as-task" data-task="insert">
    <TaskBox title="Insert" icon="as-insert">
      <input className="qline" data-qf="filterPartList" placeholder="Search parts..." value={filter} onChange={(e) => setFilter(e.target.value)} />
      <div className="as-list" data-qf="partList">
        {shown.map((p) => <div key={p} className="as-item" onClick={() => setPicked((x) => [...x, p])}>
          <Icon name="part" size={16} /> {p}{counts(p) ? ` (${counts(p)} inserted)` : ''}</div>)}
      </div>
      <div className="tfield"><span>Cannot find the part?</span><button className="qbtn" disabled title="n/a: a component is a part file of this project">Open File</button></div>
      <label className="tcheck" data-qf="CheckBox_ShowOnlyParts"><input type="checkbox" disabled /> Show only parts</label>
      <label className="tcheck" data-qf="CheckBox_RigidSubAsm"><input type="checkbox" checked disabled /> Rigid sub-assemblies</label>
    </TaskBox>
    <div className="tbuttons pd-buttons">
      <button className="qbtn default" onClick={() => void ok()}>OK</button>
      <button className="qbtn" onClick={() => closeTask()}>Cancel</button>
    </div>
  </div>
}

/** The JCS preview (SoSwitchMarker): three axes at a placement. */
function jcsMarker(p: Plc, size: number): THREE.Object3D {
  const g = new THREE.Group()
  const m = plcMatrix(p)
  const axis = (dir: V3, color: number) => {
    const geo = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0, 0, 0), new THREE.Vector3(...scale(dir, size))])
    const l = new THREE.Line(geo, new THREE.LineBasicMaterial({ color, depthTest: false }))
    l.renderOrder = 998
    return l
  }
  g.add(axis([1, 0, 0], 0xff0000), axis([0, 1, 0], 0x00ff00), axis([0, 0, 1], 0x0000ff))
  g.applyMatrix4(m)
  g.userData.cadHelper = true
  return g
}

/** An offset as the panel edits it: Base, and the rotation as yaw, pitch, roll (Rotation::getYawPitchRoll). */
interface Off { pos: V3; ypr: V3 }
const OFF0: Off = { pos: [0, 0, 0], ypr: [0, 0, 0] }
const isOff0 = (o: Off) => o.pos.every((x) => x === 0) && o.ypr.every((x) => x === 0)
/** A placement literal of the file ((x, y, z), (yaw, pitch, roll) or a quaternion) as an Off. */
function offOf(v: unknown): Off {
  if (!Array.isArray(v) || v.length !== 2) return OFF0
  const [pos, rot] = v as [number[], number[]]
  if (rot.length === 3) return { pos: [...pos] as V3, ypr: [...rot] as V3 }
  return { pos: [...pos] as V3, ypr: yprOfQuat(new THREE.Quaternion(rot[0], rot[1], rot[2], rot[3])) }
}
interface JointVals {
  angle: number; distance: number; distance2: number; off1: Off; off2: Off
  limits: [boolean, boolean, boolean, boolean]; lengthMin: number; lengthMax: number; angleMin: number; angleMax: number
  reverse: boolean; advanced: boolean; touched1: boolean; touched2: boolean
}
// The Assembly's Origin features as the tree names them, with their Labels (App::Origin's)
const ORIGIN_LABELS: Record<string, string> = { X_Axis: 'X-axis', Y_Axis: 'Y-axis', Z_Axis: 'Z-axis', XY_Plane: 'XY-plane', XZ_Plane: 'XZ-plane',
  YZ_Plane: 'YZ-plane', Origin001: 'Origin-Point' }
/** A tree click while a joint's panel is open: the panel takes it as a selection (a feature of the Assembly's Origin). */
let treePick: ((row: string) => boolean) | null = null
/** ViewProviderAssembly::isolateComponents (IsolateMode Transparent, Wireframe, Hidden) and clearIsolate: the components
 *  other than `keep` faded to the default appearance at 80% transparency, made invisible but for their lines, or hidden,
 *  and not selectable; the state before restored on clear. */
let isolated: { hidden: string[]; unselectable: string[]; view: ReturnType<typeof getState>['view'] } | null = null
function clearIsolate() {
  if (!isolated) return
  setState({ hidden: isolated.hidden, unselectable: isolated.unselectable, view: isolated.view })
  isolated = null
}
function isolateComponents(keep: string[], mode: number) {
  clearIsolate()
  const s = getState()
  const others = components(s.assembly).map((o) => o.name).filter((n) => !keep.includes(n))
  if (mode === 3 || !others.length) return
  isolated = { hidden: s.hidden, unselectable: s.unselectable, view: s.view }
  // Hidden: Visibility is whether the component is isolated, and nothing else changes
  if (mode === 2) { setState({ hidden: [...new Set([...s.hidden.filter((n) => !keep.includes(n)), ...others])] }); return }
  const view = { ...s.view }
  for (const n of others) view[n] = { ...view[n], transparency: mode === 0 ? 80 : 100, shapeColor: 0xcccccc }
  setState({ view, hidden: s.hidden.filter((n) => !keep.includes(n)), unselectable: [...new Set([...s.unselectable, ...others])] })
}
/** TaskPlacement opened on a joint's Offset1 or Offset2 (UtilsAssembly.openEditingPlacementDialog, modal, its Selected
 *  points button hidden): Translation, Center, Rotation by axis and angle or Euler angles, Reset, OK/Apply/Cancel. */
function OffsetDialog({ title, value, onApply, onClose }: { title: string; value: Off; onApply(o: Off): void; onClose(): void }) {
  const q0 = quatOfYpr(...value.ypr), aa0 = axisAngleOf(q0)
  const [f, setF] = useState({ pos: value.pos, cnt: [0, 0, 0] as V3, axis: aa0.axis as V3, angle: aa0.angle, ypr: value.ypr })
  const [mode, setMode] = useState<'axis' | 'euler'>('axis')
  const rot = () => mode === 'euler' ? quatOfYpr(...f.ypr)
    : new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(...f.axis).lengthSq() < 1e-12 ? new THREE.Vector3(0, 0, 1) : new THREE.Vector3(...f.axis).normalize(), f.angle * Math.PI / 180)
  // Placement(position, rotation, center): p -> R (p - c) + c + position, so Base = position + c - R c
  const result = (): Off => {
    const q = rot(), c = new THREE.Vector3(...f.cnt)
    const base = new THREE.Vector3(...f.pos).add(c).sub(c.clone().applyQuaternion(q))
    return { pos: base.toArray().map((x) => Math.round(x * 1e9) / 1e9 + 0) as V3, ypr: yprOfQuat(q).map((x) => Math.round(x * 1e9) / 1e9 + 0) as V3 }
  }
  const setAt = (k: 'pos' | 'cnt' | 'axis' | 'ypr', i: number) => (x: number) => setF((y) => ({ ...y, [k]: y[k].map((t, j) => (j === i ? x : t)) as V3 }))
  const xyz = (k: 'pos' | 'cnt') => ['X', 'Y', 'Z'].map((l, i) => <label key={l} className="tfield"><span>{l}</span><QuantityBox value={f[k][i]} dims={LENGTH} onChange={setAt(k, i)} /></label>)
  return createPortal(<div className="msgbox-back" onKeyDown={(e) => { e.stopPropagation(); if (e.key === 'Escape') onClose() }}>
    <div className="msgbox as-placement" role="dialog" aria-label={title} data-dialog="TaskPlacement">
      <div className="msgbox-title">Placement</div>
      <div className="tasks">
        <div className="tcols">
          <fieldset className="tgroup tg"><legend>Translation</legend>{xyz('pos')}</fieldset>
          <fieldset className="tgroup tg"><legend>Center</legend>{xyz('cnt')}</fieldset>
        </div>
        <fieldset className="tgroup tg"><legend>Rotation</legend>
          <QComboBox value={mode} onChange={(e) => {
            const m = e.target.value as 'axis' | 'euler', q = rot()
            if (m === 'euler') setF((x) => ({ ...x, ypr: yprOfQuat(q) }))
            else { const a = axisAngleOf(q); setF((x) => ({ ...x, axis: a.axis as V3, angle: a.angle })) }
            setMode(m)
          }}><option value="axis">Rotation axis and angle</option><option value="euler">Euler angles (Z–Y′–X″)</option></QComboBox>
          {mode === 'axis' ? <>
            <div className="tfield top"><span>Axis</span><span className="tstack">{[0, 1, 2].map((i) => <span key={i}><QuantityBox value={f.axis[i]} dims={NUMBER} onChange={setAt('axis', i)} /></span>)}</span></div>
            <label className="tfield"><span>Angle</span><QuantityBox value={f.angle} dims={ANGLE} onChange={(x) => setF((y) => ({ ...y, angle: x }))} /></label></>
            : ['Yaw (around Z-axis)', 'Pitch (around Y-axis)', 'Roll (around X-axis)'].map((l, i) =>
              <label key={l} className="tfield"><span>{l}</span><QuantityBox value={f.ypr[i]} dims={ANGLE} onChange={setAt('ypr', i)} /></label>)}
        </fieldset>
        <div className="hbox spread"><span /><button className="qbtn" onClick={() => setF({ pos: [0, 0, 0], cnt: [0, 0, 0], axis: [0, 0, 1], angle: 0, ypr: [0, 0, 0] })}>Reset</button></div>
      </div>
      <div className="msgbox-buttons">
        <button className="qbtn default" onClick={() => { onApply(result()); onClose() }}>OK</button>
        <button className="qbtn" onClick={() => onApply(result())}>Apply</button>
        <button className="qbtn" onClick={onClose}>Cancel</button>
      </div>
    </div>
  </div>, document.body)
}
const fmtPy = (x: number) => (Number.isInteger(x) ? `${x}.0` : String(x))
/** TaskAssemblyCreateJoint: the joint's type, its two picks (a face, an edge or a vertex of two components, or a feature
 *  of the Assembly's Origin picked in the tree; the vertex or centre nearest the click, as findElementClosestVertex takes
 *  it), the fields adaptUi shows for the type, Reverse and Rotate, the limits, Show advanced offsets' Offset1/2 editors
 *  (TaskPlacement), Isolate; the solve previewed from the second pick on, written at OK. */
function JointTask({ type0, edit }: { type0: JointType; edit?: string }) {
  const v = useStore((s) => s.assembly)
  const existing = edit ? asmObject(v, edit) : undefined
  const [type, setType] = useState<JointType>(type0)
  const [refs, setRefs] = useState<Ref[]>(() => existing ? [existing.reference1, existing.reference2].filter(Array.isArray).map((r) => [String((r as unknown[])[0]), [...((r as unknown[])[1] as string[])]] as Ref) : [])
  const [vals, setVals] = useState<JointVals>(() => ({
    angle: Number(existing?.angle ?? 0), distance: Number(existing?.distance ?? (NO_NEGATIVE_DISTANCE.includes(type0) ? 1 : 0)),
    distance2: Number(existing?.distance2 ?? (type0 === 'Gears' || type0 === 'Belt' ? 1 : 0)),
    off1: offOf(existing?.offset1), off2: offOf(existing?.offset2),
    limits: [!!existing?.enable_length_min, !!existing?.enable_length_max, !!existing?.enable_angle_min, !!existing?.enable_angle_max],
    lengthMin: Number(existing?.length_min ?? 0), lengthMax: Number(existing?.length_max ?? 0), angleMin: Number(existing?.angle_min ?? 0),
    angleMax: Number(existing?.angle_max ?? 0), reverse: false, advanced: false, touched1: false, touched2: false,
  }))
  const [isolate, setIsolate] = useState(0)
  const [dialog, setDialog] = useState<0 | 1 | 2>(0)
  const [preview, setPreview] = useState<AsmView | null>(null)
  const timer = useRef<number | undefined>(undefined)
  const set = (p: Partial<JointVals>) => setVals((x) => ({ ...x, ...p }))
  const lit = (o: Off) => [o.pos, o.ypr]
  const props = (): Record<string, unknown> => {
    const p: Record<string, unknown> = {}
    if (USING_ANGLE.includes(type)) p.angle = vals.angle
    if (USING_DISTANCE.includes(type)) p.distance = vals.distance
    if (USING_DISTANCE2.includes(type)) p.distance2 = vals.distance2
    // the simple fields write Offset2.Base.z and its yaw; the advanced editors the whole of Offset1 and Offset2
    if (vals.touched2 ? !isOff0(vals.off2) || existing?.offset2 : (USING_OFFSET.includes(type) && vals.off2.pos[2]) || (USING_ROTATION.includes(type) && vals.off2.ypr[0])) {
      p.offset2 = vals.touched2 ? lit(vals.off2) : [[0, 0, USING_OFFSET.includes(type) ? vals.off2.pos[2] : 0], [USING_ROTATION.includes(type) ? vals.off2.ypr[0] : 0, 0, 0]]
    }
    if (vals.touched1 && (!isOff0(vals.off1) || existing?.offset1)) p.offset1 = lit(vals.off1)
    if (USING_LIMIT_LENGTH.includes(type) || USING_LIMIT_ANGLE.includes(type)) {
      const [a, b, c, d] = vals.limits
      Object.assign(p, { enable_length_min: a, enable_length_max: b, enable_angle_min: c, enable_angle_max: d })
      if (a) p.length_min = vals.lengthMin
      if (b) p.length_max = vals.lengthMax
      if (c) p.angle_min = vals.angleMin
      if (d) p.angle_max = vals.angleMax
    }
    return p
  }
  const ops = (): Record<string, unknown>[] => {
    if (refs.length !== 2) return []
    if (existing) return [{ op: 'edit', name: existing.name, ref1: refs[0], ref2: refs[1], props: { ...props(), ...(type !== existing.joint_type ? { joint_type: type } : {}) }, reverse: vals.reverse }]
    return [{ op: 'joint', type, ref1: refs[0], ref2: refs[1], props: { ...props(), ...(vals.reverse ? { reverse: true } : {}) } }]
  }
  // the solve as setJointConnectors and the fields' onChanged leave it: previewed, nothing written
  useEffect(() => {
    clearTimeout(timer.current)
    const o = ops()
    if (!o.length) { setPreview(null); showPlacements(null); return }
    timer.current = window.setTimeout(async () => {
      const d = await previewAssembly(o)
      setPreview(d)
      showPlacements(d?.placements ?? null)
    }, 150)
    return () => clearTimeout(timer.current)
  }, [JSON.stringify(refs), JSON.stringify(vals), type])
  // updateIsolation: the two picks' moving parts isolated (the Origin is no component), cleared with fewer picks
  useEffect(() => {
    if (refs.length === 2) isolateComponents([...new Set(refs.map((r) => r[0]))], isolate)
    else clearIsolate()
  }, [JSON.stringify(refs), isolate])
  useEffect(() => () => clearIsolate(), [])
  // the JCS markers of the picks
  useEffect(() => {
    const view = getView()
    if (!view) return
    const g = preview?.jcs?.[existing?.name ?? ''] ?? null
    const root = new THREE.Group()
    const size = 10
    if (g) { root.add(jcsMarker(g.global1, size)); root.add(jcsMarker(g.global2, size)) }
    else for (const r of pickedJcs.current) root.add(jcsMarker(r, size))
    view.setHelper?.('as-jcs', root.children.length ? root : null)
  }, [preview, refs])
  const pickedJcs = useRef<Plc[]>([])
  const refsRef = useRef(refs)
  refsRef.current = refs
  /** TaskAssemblyCreateJoint.addSelection: no more than 2, never twice the same moving part. */
  const add = async (comp: string, element: string, point: THREE.Vector3 | null) => {
    const cur = refsRef.current
    if (cur.length >= 2 || cur.some((r) => r[0] === comp)) return
    const s = getState()
    try {
      const r = await api.assemblyJcs(s.slug!, comp, element, point ? point.toArray() : null, type)
      if (r.exit !== 0) { report('warn', resultText(r)); return }
      const subs = (r.data?.subs as string[]) ?? [element, element]
      pickedJcs.current = [...pickedJcs.current.slice(0, cur.length), r.data?.global as Plc]
      setRefs((x) => (x.length >= 2 || x.some((y) => y[0] === comp) ? x : [...x, [comp, subs]]))
    } catch (e) { report('err', msg(e)) }
  }
  // picks in the 3D view (through MakeJointSelGate) and of the Origin's features in the tree
  useEffect(() => {
    const view = getView()
    if (!view) return
    view.pointPicker = async (body, point, subName) => {
      if (!body || !subName || !isComponent(body)) { report('warn', 'Select 2 elements from 2 separate parts'); return }
      if (getState().unselectable.includes(body)) return
      await add(body, subName, point)
    }
    treePick = (row) => {
      if (!(row in ORIGIN_LABELS)) return false
      void add('Origin', `${row}.`, null)
      return true
    }
    return () => { view.pointPicker = null; treePick = null; view.setHelper?.('as-jcs', null); showPlacements(null) }
  }, [type])
  const accept = async () => {
    if (refs.length !== 2) { report('warn', 'Select 2 elements from 2 separate parts'); return }
    const o = ops()
    clearIsolate()
    closeTask()
    showPlacements(null)
    await applyAssembly(o, existing ? `Edit ${labelOf(existing)} Joint` : `Create ${type0} Joint`)
  }
  const reject = () => { clearIsolate(); closeTask(); showPlacements(null) }
  /** updateJointList: the object's Label, and the element when there is one. */
  const featName = (r: Ref) => {
    if (r[0] === 'Origin') { const d = r[1][0].replace(/\.$/, ''); return ORIGIN_LABELS[d] ?? d }
    const o = asmObject(v, r[0])
    const el = r[1][0] ? `.${r[1][0].split('.').filter(Boolean).pop()}` : ''
    return `${o ? labelOf(o) : r[0]}${el}`
  }
  const needLimits = USING_LIMIT_LENGTH.includes(type) || USING_LIMIT_ANGLE.includes(type)
  const distanceLabel = type === 'Distance' ? 'Distance' : type === 'Gears' || type === 'Belt' ? 'Radius 1' : type === 'Screw' ? 'Thread pitch' : 'Pitch radius'
  const Q = ({ label, labelName, value, dims, onChange, name, min, max, disabled }: { label: string; labelName?: string; value: number; dims: typeof LENGTH
    onChange(x: number): void; name: string; min?: number; max?: number; disabled?: boolean }) =>
    <label className="tfield">{label ? <span data-qf={labelName}>{label}</span> : null}<span data-qf={name}><QuantityBox key={`${name}:${value}`} value={value} dims={dims} min={min} max={max} disabled={disabled} onChange={onChange} /></span></label>
  const limit = (i: 0 | 1 | 2 | 3, text: string, box: string, spin: string, value: number, dims: typeof LENGTH, onValue: (x: number) => void, minmax?: [number, number]) =>
    <div className="as-limit">
      <label className="tcheck" data-qf={box}><input type="checkbox" checked={vals.limits[i]} onChange={(e) => { const l = [...vals.limits] as JointVals['limits']; l[i] = e.target.checked; set({ limits: l }) }} /> {text}</label>
      <Q label="" name={spin} value={value} dims={dims} disabled={!vals.limits[i]} min={minmax?.[0]} max={minmax?.[1]} onChange={onValue} />
    </div>
  // updateOffsetWidgets: the buttons show Base as Python prints a Vector's coordinates
  const offText = (o: Off) => `(${o.pos.map(fmtPy).join(', ')})`
  // the panel's rows top to bottom as TaskAssemblyCreateJoint.ui lays them out and adaptUi shows them (fcassembly.json)
  return <div className="tasks as-task" data-task="joint">
    <TaskBox title="Joint" icon={jointIcon(type)}>
      <Combo name="jointType" value={JOINT_TYPES.indexOf(type)} items={JOINT_TYPES} onChange={(i) => setType(JOINT_TYPES[i])} />
      <div className="as-list" data-qf="featureList">
        {refs.map((r, i) => <div key={i} className="as-item" title="Remove (Delete)" onContextMenu={(e) => { e.preventDefault(); setRefs((x) => x.filter((_, k) => k !== i)) }}
          onKeyDown={(e) => { if (e.key === 'Delete') setRefs((x) => x.filter((_, k) => k !== i)) }} tabIndex={0}>{featName(r)}</div>)}
      </div>
      {USING_REVERSE.includes(type) && <div className="tbuttons">
        <button className="qbtn" data-qf="PushButtonReverse" title="Reverse the direction of the joint" onClick={() => set({ reverse: !vals.reverse })}>Reverse</button>
        <button className="qbtn" data-qf="PushButtonRotate90" title="Rotate the joint 90 degrees" onClick={() => set({ off2: { ...vals.off2, ypr: [(vals.off2.ypr[0] + 90) % 360, vals.off2.ypr[1], vals.off2.ypr[2]] } })}>Rotate</button>
      </div>}
      {USING_ANGLE.includes(type) && <Q label="Angle" labelName="angleLabel" name="angleSpinbox" value={vals.angle} dims={ANGLE} onChange={(x) => set({ angle: x })} />}
      {USING_DISTANCE.includes(type) && <Q label={distanceLabel} labelName="distanceLabel" name="distanceSpinbox" value={vals.distance} dims={LENGTH} min={NO_NEGATIVE_DISTANCE.includes(type) ? 1e-7 : undefined} onChange={(x) => set({ distance: x })} />}
      {USING_DISTANCE2.includes(type) && <Q label="Radius 2" labelName="distanceLabel2" name="distanceSpinbox2" value={vals.distance2} dims={LENGTH} min={1e-7} onChange={(x) => set({ distance2: x })} />}
      {!vals.advanced && USING_OFFSET.includes(type) && <Q label="Offset" labelName="offsetLabel" name="offsetSpinbox" value={vals.off2.pos[2]} dims={LENGTH} onChange={(x) => set({ off2: { ...vals.off2, pos: [0, 0, x] } })} />}
      {!vals.advanced && USING_ROTATION.includes(type) && <Q label="Rotation" labelName="rotationLabel" name="rotationSpinbox" value={vals.off2.ypr[0]} dims={ANGLE} onChange={(x) => set({ off2: { ...vals.off2, ypr: [x, vals.off2.ypr[1], vals.off2.ypr[2]] } })} />}
      {vals.advanced && <>
        <label className="tfield"><span data-qf="offset1Label">Offset1</span><button className="qbtn" data-qf="offset1Button" onClick={() => setDialog(1)}>{offText(vals.off1)}</button></label>
        <label className="tfield"><span data-qf="offset2Label">Offset2</span><button className="qbtn" data-qf="offset2Button" onClick={() => setDialog(2)}>{offText(vals.off2)}</button></label>
      </>}
      <label className="tcheck" data-qf="advancedOffsetCheckbox"><input type="checkbox" checked={vals.advanced} onChange={(e) => set({ advanced: e.target.checked })} /> Show advanced offsets</label>
      {needLimits && <fieldset className="tgroup" data-qf="groupBox_limits"><legend>Limits</legend>
        {USING_LIMIT_LENGTH.includes(type) && <>
          {limit(0, 'Min length', 'limitCheckbox1', 'limitLenMinSpinbox', vals.lengthMin, LENGTH, (x) => set({ lengthMin: x }))}
          {limit(1, 'Max length', 'limitCheckbox2', 'limitLenMaxSpinbox', vals.lengthMax, LENGTH, (x) => set({ lengthMax: x }))}
        </>}
        {USING_LIMIT_ANGLE.includes(type) && <>
          {limit(2, 'Min angle', 'limitCheckbox3', 'limitRotMinSpinbox', vals.angleMin, ANGLE, (x) => set({ angleMin: x }), [-180, 180])}
          {limit(3, 'Max angle', 'limitCheckbox4', 'limitRotMaxSpinbox', vals.angleMax, ANGLE, (x) => set({ angleMax: x }), [-180, 180])}
        </>}
      </fieldset>}
      {USING_DISTANCE2.includes(type) && <label className="tcheck" data-qf="reverseRotCheckbox"><input type="checkbox" checked={type === 'Gears'}
        onChange={(e) => setType(e.target.checked ? 'Gears' : 'Belt')} /> Reverse rotation</label>}
      <label className="tfield"><span data-qf="isolateLabel2">Isolate</span><Combo name="isolateType" value={isolate} items={['Transparent', 'Wireframe', 'Hidden', 'Disabled']} onChange={setIsolate} /></label>
    </TaskBox>
    {preview?.status && <TaskBox title="Solver messages" icon="as-assembly"><div className="as-solver" data-state={preview.status.state}>{preview.status.text}{preview.status.link}</div></TaskBox>}
    <div className="tbuttons pd-buttons">
      <button className="qbtn default" onClick={() => void accept()}>OK</button>
      <button className="qbtn" onClick={reject}>Cancel</button>
    </div>
    {dialog !== 0 && <OffsetDialog title={dialog === 1 ? 'Offset1' : 'Offset2'} value={dialog === 1 ? vals.off1 : vals.off2}
      onApply={(o) => set(dialog === 1 ? { off1: o, touched1: true } : { off2: o, touched2: true })} onClose={() => setDialog(0)} />}
  </div>
}

// ── the property view of an Assembly object ──────────────────────────────────────────────────────────────────────
type PropKind = 'Length' | 'Angle' | 'bool' | 'enum' | 'link' | 'placement' | 'jcs' | 'str'
// The property view's rows of a joint, group by group and with the names it shows (PropertyItem::propertyName splits the
// camel case: JointType is "Joint Type"), as fcassembly.json's props_joint has them
const PROP_ROWS: [group: string, shown: string, key: string, kind: PropKind][] = [
  ['Base', 'Label', 'label', 'str'], ['Base', 'Suppressed', 'suppressed', 'bool'],
  ['Joint', 'Angle', 'angle', 'Angle'], ['Joint', 'Distance', 'distance', 'Length'], ['Joint', 'Distance2', 'distance2', 'Length'],
  ['Joint', 'Joint Type', 'joint_type', 'enum'],
  ['Joint Connector 1', 'Detach1', 'detach1', 'bool'], ['Joint Connector 1', 'Offset1', 'offset1', 'placement'],
  ['Joint Connector 1', 'Placement1', 'placement1', 'jcs'], ['Joint Connector 1', 'Reference1', 'reference1', 'link'],
  ['Joint Connector 2', 'Detach2', 'detach2', 'bool'], ['Joint Connector 2', 'Offset2', 'offset2', 'placement'],
  ['Joint Connector 2', 'Placement2', 'placement2', 'jcs'], ['Joint Connector 2', 'Reference2', 'reference2', 'link'],
  ['Limits', 'Angle Max', 'angle_max', 'Angle'], ['Limits', 'Angle Min', 'angle_min', 'Angle'], ['Limits', 'Enable Angle Max', 'enable_angle_max', 'bool'],
  ['Limits', 'Enable Angle Min', 'enable_angle_min', 'bool'], ['Limits', 'Enable Length Max', 'enable_length_max', 'bool'],
  ['Limits', 'Enable Length Min', 'enable_length_min', 'bool'], ['Limits', 'Length Max', 'length_max', 'Length'], ['Limits', 'Length Min', 'length_min', 'Length'],
]
/** PropertyPlacementItem's text: [(axis); angle°; (x mm  y mm  z mm)]. */
function plcText(p: Plc | null): string {
  const pos = p?.base ?? [0, 0, 0], q = p?.rotation ?? [0, 0, 0, 1]
  const w = Math.max(-1, Math.min(1, q[3])), angle = 2 * Math.acos(Math.abs(w)), s = Math.sqrt(Math.max(0, 1 - w * w)) * Math.sign(w || 1)
  const axis = s < 1e-9 ? [0, 0, 1] : [q[0] / s, q[1] / s, q[2] / s]
  const f = (x: number) => (Math.abs(x) < 0.005 ? 0 : x).toFixed(2)
  return `[(${axis.map(f).join(' ')}); ${f(angle * 180 / Math.PI)}°; (${pos.map((x) => `${f(x)} mm`).join('  ')})]`
}
/** The part file's placement literal ((x, y, z), (yaw, pitch, roll) or a quaternion) as a Placement. */
function plcOfLiteral(v: unknown): Plc | null {
  if (!Array.isArray(v) || v.length !== 2) return null
  const [pos, rot] = v as [number[], number[]]
  if (rot.length === 4) return { base: pos as V3, rotation: rot as Q4 }
  const q = new THREE.Quaternion().setFromEuler(new THREE.Euler(THREE.MathUtils.degToRad(rot[2]), THREE.MathUtils.degToRad(rot[1]), THREE.MathUtils.degToRad(rot[0]), 'ZYX'))
  return { base: pos as V3, rotation: [q.x, q.y, q.z, q.w] }
}
/** A joint's properties as the property view groups them; a GroundedJoint's ObjectToGround; a component's LinkedObject
 *  and Placement. Edits are `cad assembly set`, one undo step ("Edit Joint.Distance"), then a recompute. */
export function AssemblyProps({ name }: { name: string }) {
  const v = useStore((s) => s.assembly)
  const o = asmObject(v, name)
  if (!o) return null
  const commit = (key: string, prop: string, value: unknown) =>
    void applyAssembly([{ op: 'set', name, props: { [key]: value } }], `Edit ${name}.${prop.replace(/ /g, '')}`)
  if (o.kind === 'GroundedJoint') return <><Group title="Base"><Row k="Label" v={labelOf(o)} /></Group>
    <Group title="Ground"><Row k="Object To Ground" v={String(o.object_to_ground)} /></Group></>
  if (o.kind === 'RigidGroupJoint') {
    // RigidGroupJoint's properties (RigidPlacements is hidden), Suppressed from its SuppressibleExtension
    const members = (o.objects_to_rigid_group as string[] | undefined) ?? []
    const lab = (n: string) => { const x = asmObject(v, n); return x ? labelOf(x) : n }
    return <><Group title="Base"><Row k="Label" v={labelOf(o)} />
      <div className="prow" data-prop="Suppressed"><span className="pk">Suppressed</span><span className="pv"><input type="checkbox" checked={!!o.suppressed}
        onChange={(e) => commit('suppressed', 'Suppressed', e.target.checked)} /></span></div></Group>
      <Group title="RigidGroup"><Row k="Objects To Rigid Group" v={`[${members.map(lab).join(', ')}]`} /></Group></>
  }
  if (o.kind === 'Link') return <><Group title="Base"><Row k="Placement" v={plcText(v?.placements?.[name] ?? null)} /><Row k="Label" v={labelOf(o)} /></Group>
    <Group title="Link"><Row k="Linked Object" v={String(o.linked_object)} /></Group></>
  const groups = [...new Set(PROP_ROWS.map((r) => r[0]))]
  const text = (r: (typeof PROP_ROWS)[number]) => {
    const val = r[2] === 'label' ? labelOf(o) : o[r[2]]
    if (r[3] === 'link') return Array.isArray(val) ? `${val[0]} [${(val[1] as string[]).join(', ')}]` : ''
    if (r[3] === 'placement') return plcText(plcOfLiteral(val))
    if (r[3] === 'jcs') return plcText(v?.jcs?.[name]?.[r[2] as 'placement1' | 'placement2'] ?? null)
    return String(val ?? '')
  }
  return <>{groups.map((g) => <Group key={g} title={g}>{PROP_ROWS.filter((r) => r[0] === g).map((r) => {
    if (r[3] === 'bool') return <div key={r[1]} className="prow" data-prop={r[1]}><span className="pk">{r[1]}</span><span className="pv"><input type="checkbox" checked={!!o[r[2]]} onChange={(e) => commit(r[2], r[1], e.target.checked)} /></span></div>
    if (r[3] === 'enum') return <div key={r[1]} className="prow" data-prop={r[1]}><span className="pk">{r[1]}</span><span className="pv"><Combo value={JOINT_TYPES.indexOf(o.joint_type as JointType)} items={JOINT_TYPES} onChange={(i) => commit(r[2], r[1], JOINT_TYPES[i])} /></span></div>
    if (r[3] === 'Length' || r[3] === 'Angle') return <div key={r[1]} className="prow" data-prop={r[1]}><span className="pk">{r[1]}</span><span className="pv">
      <QuantityBox key={`${r[1]}:${String(o[r[2]])}`} value={Number(o[r[2]] ?? 0)} dims={r[3] === 'Angle' ? ANGLE : LENGTH} onChange={(x: number) => commit(r[2], r[1], x)} /></span></div>
    return <Row key={r[1]} k={r[1]} v={text(r)} />
  })}</Group>)}</>
}

// ── dragging a part with the solver (ViewProviderAssembly) ───────────────────────────────────────────────────────
type DragMode = 'None' | 'Translation' | 'TranslationNoSolve' | 'RotationOnPlane' | 'TranslationOnAxis' | 'TranslationOnAxisAndRotationOnePlane' | 'TranslationOnPlane' | 'Ball'
interface Drag {
  mode: DragMode; docs: { obj: string; plc: P }[]; jcs: P; ungrounded: boolean
  initialPosition: V3; initialPositionRot: V3; prevPosition: V3; initialUngrounded: V3
  solver: Awaited<ReturnType<typeof loadAssemblySolver>> | null; handle: ReturnType<Awaited<ReturnType<typeof loadAssemblySolver>>['drag']> | null
  placements: Record<string, Plc>; moved: boolean; rigid: boolean
}
let drag: Drag | null = null
/** The view's projections (View3DInventorViewer::getPointOnFocalPlane, getPointOnXYPlaneOfPlacement, getPointOnLine). */
function rayOf(pos: V2) {
  const r = getView()?.rayAt(pos)
  return r ? { o: r.origin.toArray() as V3, d: r.direction.toArray() as V3 } : null
}
function linePlane(o: V3, d: V3, n: V3, at: V3): V3 | null {
  const den = dot(n, d)
  if (Math.abs(den) < 1e-12) return null
  return add(o, scale(d, dot(n, sub(at, o)) / den))
}
function focalPlane(): { n: V3; at: V3 } | null {
  const f = getView()?.focalTarget()
  return f ? { n: f.dir.toArray() as V3, at: f.point.toArray() as V3 } : null
}
function pointOnFocalPlane(pos: V2): V3 | null {
  const r = rayOf(pos), f = focalPlane()
  return r && f ? linePlane(r.o, r.d, f.n, f.at) : null
}
function pointOnXYPlaneOf(pos: V2, plc: P): V3 | null {
  const r = rayOf(pos)
  return r ? linePlane(r.o, r.d, qrot(plc.rot, [0, 0, 1]), plc.pos) : null
}
function pointOnLine(pos: V2, center: V3, axis: V3): V3 | null {
  const f = focalPlane(), onFocal = pointOnFocalPlane(pos)
  if (!f || !onFocal) return null
  const n = scale(f.n, 1 / len(f.n))
  if (Math.abs(dot(axis, n)) > 1 - 1e-6) return onFocal
  const proj = (p: V3) => sub(p, scale(n, dot(n, sub(p, f.at))))
  const a = proj(center), b = proj(add(center, axis)), ab = sub(b, a)
  const onLine = add(a, scale(ab, dot(sub(onFocal, a), ab) / dot(ab, ab)))
  // intersection(onLine, onLine + n, center, center + axis)
  const da = n, db = axis, dc = sub(center, onLine), dab = cross(da, db)
  const s = dot(cross(dc, db), dab) / dot(dab, dab)
  return add(onLine, scale(da, s))
}
/** ViewProviderAssembly::findDragMode, on the page's own solver (its queries are AssemblyObject's). */
async function findDragMode(part: string, doc: AsmDoc, solver: NonNullable<Drag['solver']>): Promise<Omit<Drag, 'initialPosition' | 'initialPositionRot' | 'prevPosition' | 'initialUngrounded' | 'solver' | 'handle' | 'placements' | 'moved' | 'rigid'>> {
  const q = (op: string, ...args: string[]) => solver.query(doc, op, ...args)
  const plcOf = (n: string): P => { const p = doc.parts.find((x) => x.name === n)?.placement; return p ? ofPlc(p) : P0 }
  let docs = [{ obj: part, plc: plcOf(part) }]
  const addParts = (names: string[]) => { for (const n of names) if (!docs.some((d) => d.obj === n)) docs.push({ obj: n, plc: plcOf(n) }) }
  let ungrounded = false
  let [joint, pName] = q('getJointOfPartConnectingToGround', part) as [string, string]
  if (!joint) {
    [joint, pName] = q('getJointOfPartForUngroundedDrag', part) as [string, string]
    if (!joint) {
      addParts(q('getDownstreamParts', part, '') as string[])
      return { mode: 'TranslationNoSolve', docs, jcs: P0, ungrounded }
    }
    ungrounded = true
    addParts(q('getDownstreamParts', part, '') as string[])
  }
  let jt = doc.joints.find((j) => j.name === joint)
  if (jt?.type === 'Fixed') {
    const [up, j2, n2] = q('getUpstreamMovingPart', part, '') as [string, string, string]
    if (!j2) return { mode: 'Translation', docs, jcs: P0, ungrounded }
    docs = []
    if (!up) return { mode: 'None', docs, jcs: P0, ungrounded }
    docs.push({ obj: up, plc: plcOf(up) })
    joint = j2; pName = n2
    jt = doc.joints.find((j) => j.name === joint)
  }
  if (!jt) return { mode: 'Translation', docs, jcs: P0, ungrounded }
  const ref = pName === 'Reference1' ? jt.reference1 : jt.reference2
  const jcsPlc = ofPlc(pName === 'Reference1' ? jt.placement1 : jt.placement2)
  // getJcsGlobalPlc: the part's placement, the referenced object's in it (a datum, a sub-assembly's child), the JCS
  const jcs = pmul(ref ? plcOf(ref.part) : P0, ref?.obj ? pmul(ofPlc(ref.obj), jcsPlc) : jcsPlc)
  if (!ungrounded) addParts(q('getDownstreamParts', docs[0].obj, joint) as string[])
  const mode: DragMode = jt.type === 'Revolute' ? 'RotationOnPlane' : jt.type === 'Slider' ? 'TranslationOnAxis'
    : jt.type === 'Cylindrical' ? 'TranslationOnAxisAndRotationOnePlane' : jt.type === 'Ball' ? 'Ball'
      : jt.type === 'Distance' && ['PlanePlane', 'Other'].includes(String(q('getDistanceType', joint))) ? 'TranslationOnPlane' : 'Translation'
  return { mode, docs, jcs, ungrounded }
}
async function initMove(part: string, pos: V2) {
  const v = getState().assembly
  if (!v?.solver) return false
  const solver = await loadAssemblySolver()
  const doc = v.solver
  if (doc.parts.find((p) => p.name === part)?.grounded) return false      // canDragObjectIn3d: not a grounded part
  const m = await findDragMode(part, doc, solver)
  if (m.mode === 'None' || !m.docs.length) return false
  // requiresRigidSolveForMove: a rigid group's member is moved by a full solve on each move (its group follows)
  const rigid = !!solver.query(doc, 'requiresRigidSolveForMove', ...m.docs.map((x) => x.obj))
  const d: Drag = { ...m, initialPosition: [0, 0, 0], initialPositionRot: [0, 0, 0], prevPosition: [0, 0, 0], initialUngrounded: [0, 0, 0],
    solver, handle: null, placements: Object.fromEntries(doc.parts.map((p) => [p.name, p.placement])), moved: false, rigid }
  const axisZ = qrot(d.jcs.rot, [0, 0, 1])
  if (d.ungrounded) d.initialUngrounded = pointOnFocalPlane(pos) ?? [0, 0, 0]
  if (d.mode === 'RotationOnPlane') d.initialPositionRot = pointOnXYPlaneOf(pos, d.jcs) ?? [0, 0, 0]
  else if (d.mode === 'TranslationOnAxis') d.initialPosition = pointOnLine(pos, d.jcs.pos, axisZ) ?? [0, 0, 0]
  else if (d.mode === 'TranslationOnAxisAndRotationOnePlane') {
    d.initialPositionRot = pointOnXYPlaneOf(pos, d.jcs) ?? [0, 0, 0]
    d.initialPosition = pointOnLine(pos, d.jcs.pos, axisZ) ?? [0, 0, 0]
  } else if (d.mode === 'TranslationOnPlane') d.initialPosition = pointOnXYPlaneOf(pos, d.jcs) ?? [0, 0, 0]
  else { d.initialPosition = pointOnFocalPlane(pos) ?? [0, 0, 0]; d.prevPosition = d.initialPosition }
  if (d.mode !== 'TranslationNoSolve' || rigid) d.handle = solver.drag(doc, d.docs.map((x) => x.obj))      // SolveOnMove: preDrag
  drag = d
  return true
}
function moveTo(pos: V2) {
  const d = drag
  if (!d) return
  let newPos: V3 | null = null, newPosRot: V3 | null = null
  let dragJcs = d.jcs
  let ungroundedDelta: V3 = [0, 0, 0]
  if (d.ungrounded) {
    const cur = pointOnFocalPlane(pos)
    if (cur) ungroundedDelta = sub(cur, d.initialUngrounded)
    dragJcs = { pos: add(d.jcs.pos, ungroundedDelta), rot: d.jcs.rot }
  }
  const axisZ = qrot(d.jcs.rot, [0, 0, 1])
  if (d.mode === 'RotationOnPlane') newPosRot = pointOnXYPlaneOf(pos, d.jcs)
  else if (d.mode === 'TranslationOnAxis') newPos = pointOnLine(pos, d.jcs.pos, axisZ)
  else if (d.mode === 'TranslationOnAxisAndRotationOnePlane') { newPosRot = pointOnXYPlaneOf(pos, d.jcs); newPos = pointOnLine(pos, d.jcs.pos, axisZ) }
  else if (d.mode === 'TranslationOnPlane') newPos = pointOnXYPlaneOf(pos, d.jcs)
  else newPos = pointOnFocalPlane(pos)
  const set: Record<string, Plc> = {}
  d.docs.forEach((m, k) => {
    let plc = m.plc
    if (d.ungrounded) {
      plc = { pos: add(plc.pos, ungroundedDelta), rot: plc.rot }
      if (k !== 0) { set[m.obj] = toPlc(plc); return }
    }
    if (d.mode === 'RotationOnPlane' && newPosRot) {
      const center = d.jcs.pos, norm = qrot(d.jcs.rot, [0, 0, -1])
      const angle = angleOriented(sub(newPosRot, center), sub(d.initialPositionRot, center), norm)
      const rotated = pmul(dragJcs, { pos: [0, 0, 0], rot: qaxis([0, 0, 1], angle) })
      plc = pmul(rotated, pinv(pmul(pinv(plc), dragJcs)))
    } else if (d.mode === 'Ball' && newPos) {
      const center = d.jcs.pos, u = sub(d.initialPosition, center), w = sub(newPos, center)
      if (len(u) > 1e-7 && len(w) > 1e-7) {
        const rotated = { pos: dragJcs.pos, rot: qmul(qfromto(u, w), dragJcs.rot) }
        plc = pmul(rotated, pinv(pmul(pinv(plc), dragJcs)))
      }
    } else if (d.mode === 'TranslationOnAxis' && newPos) plc = { pos: add(plc.pos, sub(newPos, d.initialPosition)), rot: plc.rot }
    else if (d.mode === 'TranslationOnAxisAndRotationOnePlane' && newPos && newPosRot) {
      const delta = sub(newPos, d.initialPosition)
      plc = { pos: add(plc.pos, delta), rot: plc.rot }
      const newJcs = { pos: add(dragJcs.pos, delta), rot: dragJcs.rot }
      const center = add(d.jcs.pos, delta), norm = qrot(newJcs.rot, [0, 0, -1])
      const angle = angleOriented(sub(newPosRot, center), sub(d.initialPositionRot, center), norm)
      const rotated = pmul(newJcs, { pos: [0, 0, 0], rot: qaxis([0, 0, 1], angle) })
      plc = pmul(rotated, pinv(pmul(pinv(plc), newJcs)))
    } else if (d.mode === 'TranslationOnPlane' && newPos) plc = { pos: add(plc.pos, sub(newPos, d.initialPosition)), rot: plc.rot }
    else if (newPos) {                         // Translation / TranslationNoSolve: by the step since the last move
      const cur = ofPlc(d.placements[m.obj])
      plc = { pos: add(cur.pos, sub(newPos, d.prevPosition)), rot: plc.rot }
    }
    set[m.obj] = toPlc(plc)
  })
  if (newPos) d.prevPosition = newPos
  Object.assign(d.placements, set)
  if (d.handle) {
    try {
      const r: AsmResult = d.rigid ? d.handle.rigidStep(set) : d.handle.step(set)
      if (!r.drag_failed) Object.assign(d.placements, r.placements)
    } catch { /* a step that fails is ignored, as doDragStep does */ }
  }
  d.moved = true
  showPlacements(d.placements)
}
async function endMove() {
  const d = drag
  drag = null
  if (!d) return
  try { d.handle?.end() } catch { /* postDrag */ }
  if (!d.moved) { showPlacements(null); return }
  const before = getState().assembly?.solver?.parts ?? []
  const changed = Object.fromEntries(Object.entries(d.placements).filter(([n, p]) => {
    const b = before.find((x) => x.name === n)?.placement
    return !b || JSON.stringify(b) !== JSON.stringify(p)
  }))
  if (Object.keys(changed).length) await applyAssembly([{ op: 'drag', placements: changed }], 'Move part')
  showPlacements(null)
}
/** The view's events while the Assembly is in edit: a press on a component that can move starts the drag, the moves
 *  drag it, the release ends it (writing where the parts are, "Move part"). */
export function assemblyViewHook(ev: NavEvent): boolean {
  const s = getState()
  if (!s.asmActive || s.task || !s.assembly) return false
  if (ev.type === 'key' && (ev as { key?: string }).key === 'Escape') { activateAssembly(false); return true }
  if (ev.type === 'press' && ev.button === 1) {
    const h = getView()?.hitAtPos(ev.pos)
    if (!h || !isComponent(h.body)) return false
    pending = { part: h.body, pos: ev.pos }
    return false
  }
  if (ev.type === 'move' && pending && !drag && !starting) {
    const p = pending
    if (Math.abs(ev.pos[0] - p.pos[0]) + Math.abs(ev.pos[1] - p.pos[1]) < 3) return false
    starting = true
    void initMove(p.part, p.pos).finally(() => { starting = false })
    return true
  }
  if (ev.type === 'move' && drag) { moveTo(ev.pos); return true }
  if (ev.type === 'release' && ev.button === 1) {
    pending = null
    if (drag) { void endMove(); return true }
  }
  return false
}
let pending: { part: string; pos: V2 } | null = null
let starting = false

// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/CAM/InitGui.py: 2014 Yorik van Havre
//   src/Mod/CAM/Path/Main/Gui/Job.py: 2017 sliptonic
//   src/Mod/CAM/Path/Main/Gui/JobCmd.py: 2017 sliptonic
//   src/Mod/CAM/Path/Main/Gui/JobDlg.py: 2018 sliptonic
//   src/Mod/CAM/Path/Op/Gui/Base.py: 2017 sliptonic
//   src/Mod/CAM/Path/Dressup/Gui/Tags.py: 2017 sliptonic
//   src/Mod/CAM/Path/Dressup/Gui/DogboneII.py: 2022 sliptonic
//   src/Mod/CAM/Path/Post/Command.py: 2015 Dan Falck
//   src/Mod/CAM/Gui/ViewProviderPath.cpp: 2014 Yorik van Havre
//   src/Gui/propertyeditor/PropertyItem.cpp: 2004 Werner Mayer
//   src/Gui/Tree.cpp: 2004 Jürgen Riegel
// The CAM workbench, for the project's jobs (cam/<Job>.py: cad_agent/cam.py, docs/EDITING_PLAN.md "CAM in a project"):
// the CAM menu and its four toolbars as InitGui.py sets them up (every command this app does not run greyed, with the
// reason), the commands that make jobs, operations and dress-ups as FreeCAD's do (the same names and undo steps: the
// server runs FreeCAD's own Create()), the jobs in the tree (ViewProviderJob.claimChildren, a dress-up claiming its base
// op), the property view of each object (PropertyEditor: FreeCAD's groups and display names over the properties FreeCAD's
// code made) and each operation's toolpath in the 3D view as ViewProviderPath draws it (feed moves in the path colour,
// rapid moves red). Every edit is `cad cam apply` on the server (POST /api/<slug>/cam/<job>), one undo step; the toolpaths
// are recomputed there by FreeCAD's CAM code. The dialogs and task panels are cam_tasks.tsx's.
import { useState, useSyncExternalStore, type ReactNode } from 'react'
import * as THREE from 'three'
import { resultText, type CadResult } from './api'
import { consoleLog, getState, report, setState, subscribe } from './store'
import { getView, loadHistory, openTask } from './actions'
import { Icon, type IconName } from './icons'
import { cls, EditRow, Group, Row } from './panels'
import { ContextMenu, type Entry } from './chrome'
import { messageBox } from './msgbox'
import * as quantity from './quantity'
import { parseExpr, toText } from './expr'
import { partMatrix } from './part_pick'
import { QComboBox } from './combo'

// ── the model (cad_agent/cam_edit.py's read: cam_doc.CamDocument.result for one job) ───────────────────────────────
export type CamProp = { name: string; type: string; group: string; doc: string; mode: string[]; value: unknown; enums: string[] | null; expression: string | null }
export type CamHole = { feature: string; part: string; sub: string; diameter: number | null; x: number | null; y: number | null; blind: boolean | null; enabled: boolean }
export type CamObj = { name: string; label: string; type: string; kind: string | null; icon: string | null; file: string | null; props: CamProp[]
  valid: boolean; status: string | null; commands?: [string, Record<string, number>][]; features?: number; enum_labels?: Record<string, [string, string][]>; holes?: CamHole[] }
export type CamNode = { name: string; label: string; kind: string | null; icon: string | null; children: CamNode[] }
export type CamJob = { file: string; name: string; label: string; tree: CamNode; stock: number[] | null; model: string[]; operations: string[] }
export type CamEntry = { kind: string; name: string; props: Record<string, unknown> }
export type CamDoc = { project: string; job: string; entries: CamEntry[]
  result?: { job: CamJob | null; objects: CamObj[]; messages: { kind: string; text: string }[]; errors: { object: string; error: string }[] } }

type CamState = { jobs: string[]; docs: Record<string, CamDoc>; sel: string[]; busy: boolean }
let st: CamState = { jobs: [], docs: {}, sel: [], busy: false }
const subs = new Set<() => void>()
export const camState = () => st
export function setCam(p: Partial<CamState> | ((s: CamState) => Partial<CamState>)) {
  st = { ...st, ...(typeof p === 'function' ? p(st) : p) }
  subs.forEach((f) => f())
}
export function useCam<T>(sel: (s: CamState) => T): T {
  return useSyncExternalStore((f) => { subs.add(f); return () => { subs.delete(f) } }, () => sel(st))
}

const msg = (e: unknown) => (e instanceof Error ? e.message : String(e))
const enc = encodeURIComponent
async function http(method: 'GET' | 'POST', path: string, body?: unknown): Promise<CadResult> {
  const r = await fetch(path, method === 'GET' ? {} : { method, headers: { 'Content-Type': 'application/json', 'X-CAD': '1' }, body: JSON.stringify(body ?? {}) })
  const text = await r.text()
  let j: CadResult
  try { j = JSON.parse(text) } catch { throw new Error(text.slice(0, 300)) }
  if (!r.ok) throw new Error((j as unknown as { error?: string }).error || r.statusText)
  return j
}
/** A selection reference: "Job/Profile". */
export const camRef = (job: string, name: string) => `${job}/${name}`
export const splitCamRef = (ref: string): [string, string] => { const i = ref.indexOf('/'); return [ref.slice(0, i), ref.slice(i + 1)] }
export const camObj = (job: string, name: string): CamObj | undefined => st.docs[job]?.result?.objects.find((o) => o.name === name)
export const propOf = (o: CamObj | undefined, name: string): CamProp | undefined => o?.props.find((p) => p.name === name)
export const valueOf = (o: CamObj | undefined, name: string): unknown => propOf(o, name)?.value
/** A quantity property's number (mm, mm/s, degrees). */
export const numOf = (o: CamObj | undefined, name: string): number => {
  const v = valueOf(o, name) as { value?: number } | number | undefined
  return typeof v === 'number' ? v : Number(v?.value ?? 0)
}
const OPS = ['Profile', 'PocketShape', 'MillFace', 'Drilling']
const DRESSUPS = ['DressupTag', 'DressupDogbone']
export const isOp = (o: CamObj | undefined) => !!o && (OPS.includes(o.kind ?? '') || DRESSUPS.includes(o.kind ?? ''))

// ── loading and editing ─────────────────────────────────────────────────────────────────────────────────────────
let loading = 0
/** `cad cam ls`, then each job recomputed (`cad cam show`). */
export async function loadCam() {
  const slug = getState().slug
  if (!slug) { setCam({ jobs: [], docs: {}, sel: [] }); return }
  const n = ++loading
  try {
    const r = await http('GET', `/api/${enc(slug)}/cam`)
    if (n !== loading || slug !== getState().slug) return
    const jobs = ((r.data?.jobs ?? []) as { job: string }[]).map((j) => j.job)
    const docs: Record<string, CamDoc> = {}
    for (const j of jobs) {
      try {
        const d = await http('GET', `/api/${enc(slug)}/cam/${enc(j)}`)
        if (d.exit === 0) docs[j] = d.data as unknown as CamDoc
        else report('warn', `${j}: ${resultText(d)}`)
      } catch (e) { report('err', `${j}: ${msg(e)}`) }
    }
    if (n !== loading || slug !== getState().slug) return
    setCam((s) => ({ jobs, docs, sel: s.sel.filter((ref) => { const [j, o] = splitCamRef(ref); return !!docs[j]?.result?.objects.some((x) => x.name === o) }) }))
    drawToolpaths()
  } catch (e) { report('err', `CAM: ${msg(e)}`) }
}

/** `cad cam apply`: the ops (cam_edit.py's: new_job, tool, op, dressup, set, delete, label) as one undo step named as
 *  FreeCAD's transaction; amend folds them into the step before (a task panel's Apply, then its OK). The job's document as
 *  the server recomputed it, or null when it refused. */
export async function applyCam(job: string, ops: Record<string, unknown>[], name?: string, amend = false): Promise<CamDoc | null> {
  const s = getState()
  if (!s.slug) return null
  if (s.scriptToPyConsole) consoleLog('in', `cad cam apply ${s.slug} ${job} --ops '${JSON.stringify(ops)}'${name ? ` --step '${name}'` : ''}${amend ? ' --amend' : ''}`)
  setCam({ busy: true })
  try {
    const r = await http('POST', `/api/${enc(s.slug)}/cam/${enc(job)}`, { ops, ...(name ? { name } : {}), ...(amend ? { amend: true } : {}) })
    if (r.exit !== 0) { report('err', `${name ?? 'CAM'}: ${resultText(r)}`); return null }
    const doc = r.data?.doc as CamDoc | undefined
    if (doc) setCam((x) => ({ docs: { ...x.docs, [job]: doc }, jobs: x.jobs.includes(job) ? x.jobs : [...x.jobs, job].sort() }))
    for (const m of doc?.result?.messages ?? []) report(m.kind === 'Err' ? 'err' : 'warn', m.text.trim())
    loadHistory()
    drawToolpaths()
    return doc ?? null
  } catch (e) { report('err', `${name ?? 'CAM'}: ${msg(e)}`); return null } finally { setCam({ busy: false }) }
}

// the project changed: its jobs
let lastSlug: string | null = null
subscribe(() => { const s = getState(); if (s.slug !== lastSlug) { lastSlug = s.slug; setCam({ jobs: [], docs: {}, sel: [] }); void loadCam() } })

/** Document::getUniqueObjectName over the project's one document: every job's objects and the parts. */
export function uniqueName(base: string): string {
  const taken = new Set<string>([...st.jobs, ...Object.values(st.docs).flatMap((d) => d.result?.objects.map((o) => o.name) ?? []),
    ...(getState().scene?.bodies.map((b) => b.part ?? b.name) ?? [])])
  if (!taken.has(base)) return base
  for (let i = 1; ; i++) { const n = `${base}${String(i).padStart(3, '0')}`; if (!taken.has(n)) return n }
}
/** PathUtils.findParentJob of a selection reference. */
export const jobOfRef = (ref: string) => splitCamRef(ref)[0]
/** The parts the 3D view has selected (the plate itself, or its faces): part name and sub-elements. */
export function partSelection(): [string, string[]][] {
  const s = getState()
  const out: [string, string[]][] = []
  const add = (part: string, sub?: string) => {
    let g = out.find((x) => x[0] === part)
    if (!g) { g = [part, []]; out.push(g) }
    if (sub && !g[1].includes(sub)) g[1].push(sub)
  }
  for (const r of s.subSel ?? []) {
    const dot = r.lastIndexOf('.')
    const b = s.scene?.bodies.find((x) => x.name === r.slice(0, dot))
    if (b?.part) add(b.part, r.slice(dot + 1))
  }
  for (const n of s.selected) { const b = s.scene?.bodies.find((x) => x.name === n); if (b?.part) add(b.part) }
  return out
}

// ── the commands (InitGui.py's lists; each FreeCAD command's GetResources and IsActive) ─────────────────────────
type Cmd = { text: string; tip: string; icon?: IconName; accel?: string; run?: () => void | Promise<void>; active: () => boolean; why?: string }
const haveDoc = () => !!getState().slug
const haveJob = () => st.jobs.length > 0
const selObjs = () => st.sel.map((r) => { const [j, n] = splitCamRef(r); return camObj(j, n) }).filter(Boolean) as CamObj[]
/** PathDressup.selection: exactly one operation (or dress-up) selected. */
const dressupBase = (): [string, CamObj] | null => {
  if (st.sel.length !== 1) return null
  const [j, n] = splitCamRef(st.sel[0])
  const o = camObj(j, n)
  return o && isOp(o) ? [j, o] : null
}
const NOT_HERE = (what: string) => `not in this app: ${what}`
const na = (text: string, tip: string, icon: IconName | undefined, why: string, accel?: string): Cmd => ({ text, tip, icon, accel, active: () => false, why })
/** The job the op commands add to: the one selected, else the only one (PathUtils.UserInput.chooseJob asks when there are more). */
export function targetJob(): string | null {
  for (const r of st.sel) return jobOfRef(r)
  return st.jobs.length === 1 ? st.jobs[0] : st.jobs[0] ?? null
}
async function newOp(kind: string, transaction: string) {
  const job = targetJob()
  if (!job) return
  const base = kind === 'Profile' && !partSelection().some(([, s]) => s.length) ? null : partSelection().filter(([, s]) => s.length)
  const before = new Set(st.docs[job]?.result?.objects.map((o) => o.name) ?? [])
  const doc = await applyCam(job, [{ op: 'op', type: kind, ...(base && base.length ? { base } : {}) }], transaction)
  const made = doc?.result?.objects.find((o) => o.kind === kind && !before.has(o.name))
  if (made) { setCam({ sel: [camRef(job, made.name)] }); setState({ selected: [], subSel: [] }); openTask('cam', job, `op:${made.name}:create`) }
}
async function newDressup(kind: string, transaction: string) {
  const b = dressupBase()
  if (!b) return
  const [job, base] = b
  const before = new Set(st.docs[job]?.result?.objects.map((o) => o.name) ?? [])
  const doc = await applyCam(job, [{ op: 'dressup', type: kind, base: base.name }], transaction)
  const made = doc?.result?.objects.find((o) => o.kind === kind && !before.has(o.name))
  if (!made) return
  setCam({ sel: [camRef(job, made.name)] })
  // Tags.Create opens the HoldingTags panel (its own "Edit HoldingTags Dress-up" step); DogboneII.Create opens none
  if (kind === 'DressupTag') openTask('cam', job, `tag:${made.name}:create`)
}
const TIP = (t: string) => t
export const CAM_CMDS: Record<string, Cmd> = {
  CAM_Job: { text: 'New Job', tip: TIP('Creates a CAM job'), icon: 'cam-CAM_Job', accel: 'P, J', active: haveDoc, run: () => openTask('cam', '', 'jobcreate') },
  CAM_Workplane: na('Work Plane', 'Create a named work plane on the Job, from a selected planar face or at the Job origin.', 'cam-CAM_Area_Workplane', NOT_HERE('every job machines in its XY plane')),
  CAM_Sanity: na('Sanity Check', 'Checks the CAM job for common errors', 'cam-CAM_Sanity', NOT_HERE('the sanity report'), 'P, S'),
  CAM_Post: { text: 'Post Process', tip: 'Post Processes the selected Job', icon: 'cam-CAM_Post', accel: 'P, P', active: () => st.sel.length > 0, run: () => openTask('cam', jobOfRef(st.sel[0]), 'post') },
  CAM_PostSelected: na('Post Process Selected', 'Post Processes the selected operations', 'cam-CAM_PostSelected', NOT_HERE('Post Process posts the whole job'), 'P, O'),
  CAM_ExportTemplate: na('Export Template', 'Exports the CAM job as a template to be used for other jobs', 'cam-CAM_ExportTemplate', NOT_HERE('job templates')),
  CAM_SimulatorGL: na('CAM Simulator', 'Simulates G-code on stock', 'cam-CAM_SimulatorGL', NOT_HERE('simulation is cut; the 3D view draws each toolpath'), 'P, N'),
  CAM_Simulator: na('Legacy CAM Simulator', 'Simulates G-code on stock', 'cam-CAM_Simulator', NOT_HERE('simulation is cut; the 3D view draws each toolpath'), 'P, M'),
  CAM_Inspect: na('Inspect Toolpath', 'Inspects the contents of a toolpath object', 'cam-CAM_Inspect', NOT_HERE('`cad cam show --commands` lists every command'), 'P, I'),
  CAM_SelectLoop: na('Finish Selecting Loop', 'Completes the selection of edges or faces that forms a loop.', 'cam-CAM_SelectLoop', NOT_HERE('loop selection'), 'P, L'),
  CAM_OpActiveToggle: { text: 'Toggle Operation', tip: 'Toggles the active state of the operation', icon: 'cam-CAM_OpActive', accel: 'P, X',
    active: () => selObjs().length > 0 && selObjs().every((o) => propOf(o, 'Active')),
    run: async () => { for (const r of st.sel) { const [j, n] = splitCamRef(r); const o = camObj(j, n); if (o) await applyCam(j, [{ op: 'set', name: n, props: { Active: !valueOf(o, 'Active') } }], 'Toggle Operation') } } },
  CAM_ToolBitLibraryOpen: na('Toolbit Library Manager', 'Opens an editor to manage toolbit libraries', 'cam-CAM_ToolTable', NOT_HERE('add a library bit with `cad cam tool SLUG JOB --bit 5mm_Endmill`')),
  CAM_ToolBitDock: na('Add Toolbit…', 'Opens the toolbit selection dialog', 'cam-CAM_ToolBit', NOT_HERE('add a library bit with `cad cam tool SLUG JOB --bit 5mm_Endmill`'), 'P, T'),
  CAM_Profile: { text: 'Profile', tip: 'Profile entire model, selected face(s) or selected edge(s)', icon: 'cam-CAM_Profile', active: haveJob, run: () => newOp('Profile', 'Create Profile') },
  CAM_Pocket_Shape: { text: 'Pocket Shape', tip: 'Creates a pocket toolpath from a face or faces', icon: 'cam-CAM_Pocket', active: haveJob, run: () => newOp('PocketShape', 'Create Pocket Shape') },
  CAM_MillFacing: na('Mill Facing', 'Create a Mill Facing Operation to machine the top surface of stock', 'cam-CAM_Face', NOT_HERE('Mill Facing; the Face op (MillFace) is `cad cam op SLUG JOB MillFace`')),
  CAM_Helix: na('Helix', 'Creates a Helical toolpath from the features of a base object', 'cam-CAM_Helix', NOT_HERE('Helix')),
  CAM_Adaptive: na('Adaptive', 'Adaptive clearing and profiling', 'cam-CAM_Adaptive', NOT_HERE('Adaptive (its TechDraw outline is not ported)')),
  CAM_Slot: na('Slot', 'Create a single horizontal slot between two points.', 'cam-CAM_Slot', NOT_HERE('Slot')),
  // registered by Path/Op/Gui/MillFace.py but on no menu or toolbar in 3160daf1e2b6 (Mill Facing is): run from the console
  CAM_MillFace: { text: 'Face', tip: 'Create a Facing Operation from a model or face', icon: 'cam-CAM_Face', active: haveJob, run: () => newOp('MillFace', 'Create MillFace') },
  CAM_Drilling: { text: 'Drilling', tip: 'Creates a Drilling toolpath from the features of a base object', icon: 'cam-CAM_Drilling', active: haveJob, run: () => newOp('Drilling', 'Create Drilling') },
  CAM_ThreadMilling: na('Thread Milling', 'Creates a Thread Milling toolpath from features of a base object', 'cam-CAM_ThreadMilling', NOT_HERE('Thread Milling')),
  CAM_Engrave: na('Engrave', 'Creates an Engraving toolpath around a Draft ShapeString', 'cam-CAM_Engrave', NOT_HERE('Engrave')),
  CAM_Deburr: na('Deburr', 'Creates a Deburr toolpath along Edges or around Faces', 'cam-CAM_Deburr', NOT_HERE('Deburr')),
  CAM_Vcarve: na('Vcarve', 'Creates a medial line engraving toolpath', undefined, NOT_HERE('Vcarve')),
  CAM_Pocket3D: na('3D Pocket', 'Creates a 3D Pocket toolpath from a face or faces', 'cam-CAM_3DPocket', NOT_HERE('3D Pocket')),
  CAM_DressupArray: na('Array', 'Creates an array from a selected toolpath', 'cam-CAM_Dressup', NOT_HERE('the Array dress-up')),
  CAM_DressupAxisMap: na('Axis Map', 'Remaps one axis to another', 'cam-CAM_Dressup', NOT_HERE('the Axis Map dress-up')),
  CAM_DressupPathBoundary: na('Boundary', 'Creates a boundary dress-up from a selected toolpath', 'cam-CAM_Dressup', NOT_HERE('the Boundary dress-up')),
  CAM_DressupPathBoundary2: na('Boundary2', 'Creates a boundary dress-up from a selected toolpath', 'cam-CAM_Dressup', NOT_HERE('the Boundary2 dress-up')),
  CAM_DressupDogbone: { text: 'Dogbone', tip: 'Creates a dogbone dress-up object from a selected toolpath', icon: 'cam-CAM_Dressup', active: () => !!dressupBase(), run: () => newDressup('DressupDogbone', 'Create Dogbone Dress-up') },
  CAM_DressupDragKnife: na('Drag Knife', 'Modifies a toolpath to add dragknife corner actions', 'cam-CAM_Dressup', NOT_HERE('the Drag Knife dress-up')),
  CAM_DressupLeadInOut: na('Lead In/Out', 'Creates entry and exit motions for a selected path', 'cam-CAM_Dressup', NOT_HERE('the Lead In/Out dress-up')),
  CAM_DressupMirror: na('Mirror', 'Creates mirror of a selected path', 'cam-CAM_Dressup', NOT_HERE('the Mirror dress-up')),
  CAM_DressupPlungeMilling: na('Plunge Milling', 'Creates plunge milling for a selected path', 'cam-CAM_Dressup', NOT_HERE('the Plunge Milling dress-up')),
  CAM_DressupRampEntry: na('Ramp Entry', 'Creates a ramp entry dress-up object from a selected toolpath', 'cam-CAM_Dressup', NOT_HERE('the Ramp Entry dress-up')),
  CAM_DressupTag: { text: 'Tag', tip: 'Creates a tag dress-up object from a selected toolpath', icon: 'cam-CAM_Dressup', active: () => !!dressupBase(), run: () => newDressup('DressupTag', 'Create a Tag dressup') },
  CAM_DressupZCorrect: na('Z Depth Correction', 'Corrects Z depth using a probe map', 'cam-CAM_Dressup', NOT_HERE('the Z Depth Correction dress-up')),
  CAM_Comment: na('Comment', 'Adds a Comment to the CNC program', 'cam-CAM_Comment', NOT_HERE('Comment')),
  CAM_Stop: na('Stop', 'Adds an optional or mandatory stop to the program', 'cam-CAM_Stop', NOT_HERE('Stop')),
  CAM_Custom: na('Custom', 'Create custom G-code snippet', 'cam-CAM_Custom', NOT_HERE('Custom')),
  CAM_Probe: na('Probe', 'Create a Probing Grid from a job stock', 'cam-CAM_Probe', NOT_HERE('Probe')),
  CAM_OperationCopy: na('Copy Operation', 'Copies the operation in the job', 'cam-CAM_OpCopy', NOT_HERE('Copy Operation')),
  CAM_Array: na('Array', 'Creates an array from selected toolpaths', 'cam-CAM_Array', NOT_HERE('Array')),
  CAM_SimpleCopy: na('Simple Copy', 'Creates a non-parametric copy of another toolpath', 'cam-CAM_SimpleCopy', NOT_HERE('Simple Copy')),
  CAM_PropertyBag: na('Property Bag', 'Creates an object which can be used to store reference properties', undefined, NOT_HERE('Property Bag')),
}
const e = (cmd: string): Exclude<Entry, 'sep'> => {
  const c = CAM_CMDS[cmd]
  const on = c.active()
  return { label: c.text, icon: c.icon, cmd, disabled: !on, onSelect: () => { if (c.active()) void c.run?.() }, kbd: c.accel,
    title: !on && c.why ? `${c.tip}\n\n${c.why}` : c.tip }
}
const group = (label: string, cmds: string[], icon?: IconName): Exclude<Entry, 'sep'> => ({ label, icon, sub: cmds.map(e) })
// InitGui.py's lists
const PROJECT_SETUP = ['CAM_Job', 'CAM_Workplane', 'CAM_Sanity']
const POST_TOOLS = ['CAM_Post', 'CAM_PostSelected']
const TOOL_CMDS = ['CAM_Inspect', 'CAM_SelectLoop', 'CAM_OpActiveToggle']
const SIM_TOOLS = ['CAM_SimulatorGL', 'CAM_Simulator']
const TWO_D_OPS = ['CAM_Profile', 'CAM_Pocket_Shape', 'CAM_MillFacing', 'CAM_Helix', 'CAM_Adaptive', 'CAM_Slot']
const DRILLING = ['CAM_Drilling', 'CAM_ThreadMilling']
const ENGRAVE = ['CAM_Engrave', 'CAM_Deburr', 'CAM_Vcarve']
const THREE_D_OPS = ['CAM_Pocket3D']
const DRESSUP_CMDS = ['CAM_DressupArray', 'CAM_DressupAxisMap', 'CAM_DressupPathBoundary', 'CAM_DressupPathBoundary2', 'CAM_DressupDogbone', 'CAM_DressupDragKnife',
  'CAM_DressupLeadInOut', 'CAM_DressupMirror', 'CAM_DressupPlungeMilling', 'CAM_DressupRampEntry', 'CAM_DressupTag', 'CAM_DressupZCorrect']
const EXTRA = ['CAM_Comment', 'CAM_Stop', 'CAM_Custom', 'CAM_Probe']
const MODIFICATION = ['CAM_OperationCopy', 'CAM_Array', 'CAM_SimpleCopy']
/** CAMWorkbench.Initialize: the "&CAM" menu. */
export function camMenu(): Entry[] {
  return [...PROJECT_SETUP.map(e), ...POST_TOOLS.map(e), e('CAM_ExportTemplate'), 'sep', ...SIM_TOOLS.map(e), ...TOOL_CMDS.map(e),
    e('CAM_ToolBitLibraryOpen'), e('CAM_ToolBitDock'), 'sep', ...TWO_D_OPS.map(e), ...DRILLING.map(e), 'sep', ...ENGRAVE.map(e), 'sep',
    ...THREE_D_OPS.map(e), 'sep', group('Path Dressup', DRESSUP_CMDS), group('Supplemental Commands', EXTRA), group('Path Modification', MODIFICATION), 'sep',
    group('Utils', ['CAM_PropertyBag'])]
}
/** A command group (Gui::CommandActionPygroup) on a toolbar: the first command's icon, the others in its menu. */
const split = (cmd: string, label: string, cmds: string[]): Exclude<Entry, 'sep'> => {
  const first = e(cmds[0])
  return { ...first, cmd, label, split: true, sub: cmds.map(e) }
}
/** CAMWorkbench.Initialize: the Project Setup, Tool Commands, New Operations and Path Modification toolbars. */
export function camToolbars(): [string, Entry[]][] {
  return [
    ['Project Setup', [...PROJECT_SETUP.map(e), split('CAM_PostTools', 'Post process Operations', POST_TOOLS)]],
    ['Tool Commands', [split('CAM_SimTools', 'Simulators', SIM_TOOLS), ...TOOL_CMDS.map(e), e('CAM_ToolBitDock')]],
    ['New Operations', [...TWO_D_OPS.map(e), split('CAM_DrillingTools', 'Drilling Operations', DRILLING), split('CAM_EngraveTools', 'Engraving Operations', ENGRAVE), ...THREE_D_OPS.map(e)]],
    ['Path Modification', [...MODIFICATION.map(e), split('CAM_DressupTools', 'Dressup Operations', DRESSUP_CMDS)]],
  ]
}
export const CAM_TOOLBARS = ['Project Setup', 'Tool Commands', 'New Operations', 'Path Modification'] as const
export const camRun = (cmd: string) => { const c = CAM_CMDS[cmd]; if (c?.active()) void c.run?.() }
export const camEnabled = (cmd: string) => !!CAM_CMDS[cmd]?.active()
export const camCommands = (): [string, Cmd][] => Object.entries(CAM_CMDS)
/** The menu and toolbars as plain data, for camcheck.mjs (cadui.cam()). */
export function camMenus() {
  const plain = (es: Entry[]): unknown[] => es.map((x) => (x === 'sep' ? { sep: true } : { text: x.label, cmd: x.cmd ?? null, enabled: !x.disabled, kbd: x.kbd ?? null, why: x.disabled ? x.title ?? null : null, ...(x.sub ? { menu: plain(x.sub) } : {}) }))
  return { menu: plain(camMenu()), toolbars: camToolbars().map(([t, es]) => ({ title: t, buttons: plain(es) })) }
}

// ── the tree (ViewProviderJob.claimChildren and the Operations group's: cam_doc.CamDocument.tree) ───────────────
const ICONS: Record<string, IconName> = { CAM_Job: 'cam-CAM_Job', CAM_Stock: 'part', CAM_SetupSheet: 'cam-CAM_SetupSheet', CAM_ToolBit: 'cam-CAM_ToolBit',
  CAM_ToolController: 'cam-CAM_ToolController', CAM_Profile: 'cam-CAM_Profile', CAM_Pocket: 'cam-CAM_Pocket', CAM_Face: 'cam-CAM_Face', CAM_Drilling: 'cam-CAM_Drilling',
  CAM_Dressup: 'cam-CAM_Dressup', CAM_OpActive: 'cam-CAM_OpActive', CAM_BaseGeometry: 'cam-CAM_BaseGeometry', CAM_ToolTable: 'cam-CAM_ToolTable' }
const iconOf = (n: CamNode, o: CamObj | undefined): IconName => {
  if (o && isOp(o) && valueOf(o, 'Active') === false) return 'cam-CAM_InactiveOp'
  if (n.icon && ICONS[n.icon]) return ICONS[n.icon]
  return o?.type === 'App::DocumentObjectGroup' ? 'group' : 'part'
}
/** What a double click opens (the view provider's setEdit): the Job's panel (also for its stock), an op's, a tool
 *  controller's, the Holding Tags'. */
export function editCam(job: string, name: string) {
  const o = camObj(job, name)
  if (!o) return
  if (o.kind === 'Job' || o.kind === 'Stock') openTask('cam', job, 'job')
  else if (o.kind === 'ToolController') openTask('cam', job, `tc:${name}`)
  else if (o.kind === 'DressupTag') openTask('cam', job, `tag:${name}`)
  else if (o.kind && OPS.includes(o.kind)) openTask('cam', job, `op:${name}`)
}
export function camSelect(ref: string, add = false) {
  setCam((s) => ({ sel: add ? (s.sel.includes(ref) ? s.sel.filter((x) => x !== ref) : [...s.sel, ref]) : [ref] }))
  setState({ selected: [], subSel: [], featSel: [] })
}
export function CamRows({ iconSize = 16 }: { iconSize?: number }) {
  const jobs = useCam((s) => s.jobs), docs = useCam((s) => s.docs), sel = useCam((s) => s.sel)
  const [closed, setClosed] = useState<Record<string, boolean>>({})
  const [menu, setMenu] = useState<{ x: number; y: number; job: string; name: string } | null>(null)
  const rows: ReactNode[] = []
  const walk = (job: string, n: CamNode, depth: number, path: string) => {
    const key = `${path}/${n.name}`
    const ref = camRef(job, n.name)
    const o = camObj(job, n.name)
    const open = !closed[key]
    rows.push(
      <div key={key} className={cls('trow', sel.includes(ref) && 'sel')} data-cam={ref}
        onClick={(ev) => camSelect(ref, ev.ctrlKey || ev.metaKey)} onDoubleClick={() => editCam(job, n.name)}
        onContextMenu={(ev) => { ev.preventDefault(); ev.stopPropagation(); camSelect(ref); setMenu({ x: ev.clientX, y: ev.clientY, job, name: n.name }) }}>
        <span className="tlab">
          <span className="pdindent" style={{ width: 6 + 16 * (depth + 1) }} />
          {n.children.length ? <span className={cls('twisty', open && 'open')} onClick={(ev) => { ev.stopPropagation(); setClosed((c) => ({ ...c, [key]: open })) }} /> : <span className="tindent" />}
          <span className="ticon"><Icon name={iconOf(n, o)} size={iconSize} /></span>
          <span className={cls('tname', o && !o.valid && 'err')} title={o?.status ?? undefined}>{n.label}</span>
        </span>
      </div>)
    if (open) for (const c of n.children) walk(job, c, depth + 1, key)
  }
  for (const j of jobs) { const t = docs[j]?.result?.job?.tree; if (t) walk(j, t, 0, '') }
  const m = menu && camObj(menu.job, menu.name)
  return <>
    {rows}
    {menu && m && <ContextMenu at={menu} onClose={() => setMenu(null)} entries={[
      ...(m.kind && m.kind !== 'Stock' && m.kind !== 'SetupSheet' && m.kind !== 'ToolBit' && m.kind !== 'DressupDogbone' ? [{ label: 'Edit', bold: true, onSelect: () => editCam(menu.job, menu.name) }, 'sep' as const] : []),
      { label: 'Delete', icon: 'edit-delete', disabled: !deletable(m), onSelect: () => void deleteCam([camRef(menu.job, menu.name)]) },
    ]} />}
  </>
}
const deletable = (o: CamObj) => !!o.kind && (isOp(o) || o.kind === 'ToolController')
/** Std_Delete on CAM objects: an op, a dress-up or a tool controller (cam_edit refuses one another object uses). */
export async function deleteCam(refs: string[]): Promise<boolean> {
  const byJob: Record<string, string[]> = {}
  for (const r of refs) { const [j, n] = splitCamRef(r); const o = camObj(j, n); if (o && deletable(o)) (byJob[j] ??= []).push(n) }
  if (!Object.keys(byJob).length) return false
  for (const [j, names] of Object.entries(byJob)) {
    const extra: string[] = []
    for (const n of names) { const o = camObj(j, n); if (o?.kind === 'ToolController') { const bit = valueOf(o, 'Tool'); if (typeof bit === 'string') extra.push(bit) } }
    await applyCam(j, [...names, ...extra].map((n) => ({ op: 'delete', name: n })), 'Delete')
  }
  setCam({ sel: [] })
  return true
}
export async function deleteSelectedCam(): Promise<boolean> {
  if (!st.sel.length) return false
  const refs = [...st.sel]
  const bad = refs.map((r) => camObj(...splitCamRef(r))).filter((o) => o && !deletable(o))
  if (bad.length) { void messageBox('warning', 'Delete', `${bad.map((o) => o!.label).join(', ')} cannot be deleted here: a job goes with \`cad cam delete-job\`, its stock, setup sheet and groups with it.`); return true }
  return deleteCam(refs)
}

// ── the property view (PropertyEditor: groups in name order, FreeCAD's display names, PropertyItem's texts) ───────
/** PropertyItem::setPropertyName: a space before each capital that follows a small letter (a run of capitals stays). */
export function displayName(name: string): string {
  let out = '', upper = false
  for (const ch of name) {
    const isUp = ch >= 'A' && ch <= 'Z'
    if (isUp && out && !upper && !out.endsWith(' ')) out += ' '
    upper = isUp
    out += ch
  }
  return out
}
/** The property types the property view has no item for (PropertyItemFactory): never a row. */
const NO_ITEM = new Set(['App::PropertyPythonObject', 'Part::PropertyPartShape', 'Path::PropertyPath', 'App::PropertyExpressionEngine', 'Materials::PropertyMaterial'])
type Dims = quantity.Quantity['dims']
const qtext = (v: number, dims: Dims) => quantity.userString({ value: v, dims }).text
/** PropertyQuantityItem's text: the user string, an angle's ° straight after the number. */
const qprop = (v: number, dims: Dims) => qtext(v, dims).replace(/ °$/, '°')
const fx = (n: number) => (Math.abs(n) < 5e-3 ? 0 : n).toFixed(2)
const isQ = (v: unknown): v is { value: number; unit: number[] } => !!v && typeof v === 'object' && 'unit' in (v as object)
/** The labels of a job's objects, and its clones' parts (an element link names the part; FreeCAD's names the clone). */
function labelIn(job: string, name: string): string { return camObj(job, name)?.label ?? name }
function cloneOf(job: string, part: string): { name: string; label: string } {
  const doc = st.docs[job]?.result?.job
  const model = doc?.tree.children.find((c) => c.name.startsWith('Model'))
  const i = doc?.model.indexOf(part) ?? -1
  const c = i >= 0 ? model?.children[i] : undefined
  return c ? { name: c.name, label: c.label } : { name: part, label: part }
}
/** PropertyLinkListItem: one object by its label, more in brackets, the first three and "...". */
const listText = (xs: string[]) => (xs.length === 1 ? xs[0] : xs.length > 3 ? `[${xs.slice(0, 3).join(', ')} ...]` : `[${xs.join(', ')}]`)
/** What PropertyItem::toString shows for a property's value, and its expression after it. */
export function propText(job: string, p: CamProp): string {
  const v = p.value
  let s = ''
  if (isQ(v)) s = qprop(v.value, v.unit as Dims)
  else if (p.type === 'App::PropertyBool') s = v ? 'true' : 'false'
  else if (p.type === 'App::PropertyPercent') s = `${v} %`
  else if (p.type === 'App::PropertyLink' || p.type === 'App::PropertyLinkGlobal' || p.type === 'App::PropertyLinkChild') {
    if (typeof v === 'string') { const l = labelIn(job, v); s = l === v ? l : `${l} (${v})` }
  } else if (/PropertyLinkList/.test(p.type)) s = Array.isArray(v) && v.length ? listText(v.map((n) => labelIn(job, String(n)))) : ''
  else if (/PropertyLinkSubList/.test(p.type)) {
    s = (Array.isArray(v) ? v : []).map((g) => {
      const [part, subsRaw] = g as [string, string[]]
      const c = cloneOf(job, part)
      const subs = subsRaw ?? []
      return `${c.label} (${c.name}) ${subs.length > 3 ? `[${subs.slice(0, 3).join(', ')} ...]` : `[${subs.join(', ')}]`}`
    }).join(', ')
  } else if (p.type === 'App::PropertyVectorDistance' && Array.isArray(v)) s = `[${(v as number[]).map((x) => qtext(x, [1, 0, 0, 0, 0, 0, 0, 0])).join(' ')}]`
  else if (p.type === 'App::PropertyVector' && Array.isArray(v)) s = `[${(v as number[]).map(fx).join(' ')}]`
  else if (p.type === 'App::PropertyVectorList') s = Array.isArray(v) && v.length ? `[${(v[0] as number[]).map(fx).join(' ')}]${v.length > 1 ? ', ...' : ''}` : '[]'
  else if (p.type === 'App::PropertyPlacement' && v && typeof v === 'object') s = placementText(v as { base: number[]; rotation: number[] })
  else if (p.type === 'App::PropertyStringList' || p.type === 'App::PropertyIntegerList') s = Array.isArray(v) ? `[${v.join(',')}]` : ''
  else if (v === null || v === undefined) s = ''
  else s = String(v)
  if (p.expression) {
    let e = p.expression
    // the document's objects by name and label, so SetupSheet.X reads as an object's property (not the owner's path)
    const names = new Set((st.docs[job]?.result?.objects ?? []).flatMap((o) => [o.name, o.label]))
    // ObjectIdentifier::toString of Obj.prop with Obj an object of the document: written as it reads
    const resolve = (obj: { name: string }, prop: string) => ({ doc: null, obj: null, local: false, names: [obj.name, prop], sub: [], plain: names.has(obj.name) })
    try { e = toText(parseExpr(p.expression, names, undefined, resolve)) } catch { /* shown as written */ }
    s = `${s}  ( ${e} )`
  }
  return s
}
/** PropertyPlacementItem: [(axis); angle; (position)], the rotation from its quaternion. */
function placementText(pl: { base: number[]; rotation: number[] }): string {
  const [x, y, z, w] = pl.rotation ?? [0, 0, 0, 1]
  const angle = 2 * Math.acos(Math.min(1, Math.abs(w)))
  const sn = Math.sqrt(Math.max(0, 1 - w * w)) * Math.sign(w || 1)
  const axis = sn < 1e-9 ? [0, 0, 1] : [x / sn, y / sn, z / sn]
  return `[(${axis.map(fx).join(' ')}); ${fx(THREE.MathUtils.radToDeg(angle))}°; (${(pl.base ?? [0, 0, 0]).map((c) => `${fx(c)} mm`).join('  ')})]`
}
/** The property view's rows of an object: Data's groups by name and in each the properties in the order FreeCAD's code
 *  added them, Placement and Label first. */
export function propRows(o: CamObj): [string, CamProp[]][] {
  // (a property with no group is in Base, as PropertyView puts it)
  const groupOf = (p: CamProp) => p.group || 'Base'
  const shown = o.props.filter((p) => !p.mode.includes('Hidden') && !NO_ITEM.has(p.type))
  const groups = [...new Set(shown.map(groupOf))].sort()
  return groups.map((g) => {
    const ps = shown.filter((p) => groupOf(p) === g)
    const first = ['Placement', 'Label'].map((n) => ps.find((p) => p.name === n)).filter(Boolean) as CamProp[]
    return [displayName(g), [...first, ...ps.filter((p) => !first.includes(p))]]
  })
}
const EDITABLE = /PropertyBool|PropertyEnumeration|PropertyInteger|PropertyFloat|PropertyPercent|PropertyLength|PropertyDistance|PropertyAngle|PropertySpeed|PropertyString$/
const LOCKED = new Set(['CycleTime', 'OpStartDepth', 'OpFinalDepth', 'OpToolDiameter', 'OpStockZMax', 'OpStockZMin', 'ToolBitID', 'ShapeID', 'ShapeType'])
/** The selected CAM object's property view (Data tab): FreeCAD's rows; a value set clears the expression bound to it, as
 *  typing a value does. */
export function CamProps() {
  const sel = useCam((s) => s.sel)
  useCam((s) => s.docs)
  const ref = sel[sel.length - 1]
  if (!ref) return null
  const [job, name] = splitCamRef(ref)
  const o = camObj(job, name)
  if (!o) return null
  const editable = !!o.kind && !['Stock', 'SetupSheet'].includes(o.kind) && o.type !== 'App::DocumentObjectGroup'
  const set = (p: CamProp, v: unknown) => void applyCam(job, [p.name === 'Label' ? { op: 'label', name, to: String(v) } : { op: 'set', name, props: { [p.name]: v } }],
    `Edit ${o.label}.${p.name}`)
  const row = (p: CamProp): ReactNode => {
    const label = displayName(p.name)
    const text = propText(job, p)
    const ro = !editable || LOCKED.has(p.name) || p.mode.includes('ReadOnly') || !!p.expression || !EDITABLE.test(p.type)
    if (ro) return <Row key={p.name} k={<span title={p.doc || undefined}>{label}</span>} v={<span data-cam-prop={p.name}>{text}</span>} depth={1} />
    if (p.type === 'App::PropertyBool') return <EditRow key={p.name} k={label} value={p.value === true} type="bool" depth={1} onCommit={(x) => set(p, x)} />
    if (p.enums) return <div key={p.name} className="prow" tabIndex={0} title={p.doc || undefined}><span className="pk" style={{ paddingLeft: 27 }}>{label}</span>
      <span className="pv"><QComboBox className="qselect-pv" value={String(p.value)} onChange={(ev) => set(p, ev.target.value)}>{p.enums.map((x) => <option key={x}>{x}</option>)}</QComboBox></span></div>
    if (isQ(p.value)) {
      const dims = p.value.unit as Dims
      const unit = quantity.unitString(dims)
      return <EditRow key={p.name} k={label} value={p.value.value} type="float" depth={1} unit={unit}
        kind={/Angle/.test(p.type) ? 'Angle' : /Length|Distance/.test(p.type) ? 'Length' : null}
        onCommit={(x) => set(p, unit ? `${Number(x)} ${unit}` : Number(x))} />
    }
    if (/Integer|Percent/.test(p.type)) return <EditRow key={p.name} k={label} value={Number(p.value)} type="int" depth={1} onCommit={(x) => set(p, Math.round(Number(x)))} />
    if (/Float/.test(p.type)) return <EditRow key={p.name} k={label} value={Number(p.value)} type="float" depth={1} onCommit={(x) => set(p, Number(x))} />
    return <EditRow key={p.name} k={label} value={String(p.value ?? '')} type="str" depth={1} onCommit={(x) => set(p, String(x))} />
  }
  return <>{propRows(o).map(([g, ps]) => <Group key={g} title={g}>{ps.map(row)}</Group>)}</>
}
export const camPropActive = () => st.sel.length > 0
/** The property view's rows as text, for camcheck.mjs: [depth, name, value]. */
export function camPropText(job: string, name: string): [number, string, string | null][] {
  const o = camObj(job, name)
  if (!o) return []
  return propRows(o).flatMap(([g, ps]) => [[0, g, null] as [number, string, string | null], ...ps.map((p) => [1, displayName(p.name), propText(job, p)] as [number, string, string | null])])
}

// ── the toolpaths in the 3D view (ViewProviderPath: feed moves in the path colour, rapid moves red) ──────────────
/** ViewProviderPath's defaults (Preferences > CAM: DefaultNormalPathColor, DefaultRapidPathColor, DefaultPathLineWidth). */
const FEED = 0x00aa00, RAPID = 0xff0000
/** cam_doc.toolpath: a Path's moves as polylines (arcs in 10° steps, drill cycles as their moves), from (0, 0, 0). */
export function polylines(commands: [string, Record<string, number>][]): [boolean, number[][]][] {
  const out: [boolean, number[][]][] = []
  let [x, y, z] = [0, 0, 0]
  const push = (rapid: boolean, pts: number[][]) => {
    const last = out[out.length - 1]
    if (last && last[0] === rapid) last[1].push(...pts.slice(1))
    else out.push([rapid, pts])
  }
  for (const [name, p] of commands) {
    if (/^G0?[01]$/.test(name)) {
      const n = [p.X ?? x, p.Y ?? y, p.Z ?? z]
      push(/^G0?0$/.test(name), [[x, y, z], n]);
      [x, y, z] = n
    } else if (/^G0?[23]$/.test(name)) {
      const n = [p.X ?? x, p.Y ?? y, p.Z ?? z]
      const cx = x + (p.I ?? 0), cy = y + (p.J ?? 0)
      const a0 = Math.atan2(y - cy, x - cx), a1 = Math.atan2(n[1] - cy, n[0] - cx)
      let sweep = a1 - a0
      if (/^G0?2$/.test(name)) { while (sweep >= 0) sweep -= 2 * Math.PI } else { while (sweep <= 0) sweep += 2 * Math.PI }
      const r = Math.hypot(x - cx, y - cy)
      const k = Math.max(2, Math.ceil(Math.abs(sweep) / (Math.PI / 18)))
      const pts = [[x, y, z]]
      for (let i = 1; i <= k; i++) { const a = a0 + (sweep * i) / k; pts.push([cx + r * Math.cos(a), cy + r * Math.sin(a), z + ((n[2] - z) * i) / k]) }
      pts[pts.length - 1] = n
      push(false, pts);
      [x, y, z] = n
    } else if (/^G8[1-9]$/.test(name)) {
      const nx = p.X ?? x, ny = p.Y ?? y, r = p.R ?? z, bottom = p.Z ?? z
      push(true, [[x, y, z], [nx, ny, z], [nx, ny, r]])
      push(false, [[nx, ny, r], [nx, ny, bottom]])
      push(true, [[nx, ny, bottom], [nx, ny, r]]);
      [x, y, z] = [nx, ny, r]
    }
  }
  return out
}
let drawnKey = ''
/** Each job's operations (Operations.Group, the ones the tree shows: a dress-up, not its base) drawn over the part they
 *  machine, where the 3D view shows that part; an inactive op is not drawn (ViewProviderPath hides it). */
export function drawToolpaths() {
  const s = getState(), view = getView()
  if (!view) return
  const items: { job: string; op: CamObj; matrix: number[] | null | undefined }[] = []
  for (const j of st.jobs) {
    const res = st.docs[j]?.result
    const jobNode = res?.job
    if (!jobNode) continue
    const body = s.scene?.bodies.find((b) => b.part === jobNode.model[0])
    const opsNode = jobNode.tree.children.find((c) => c.name.startsWith('Operations'))
    for (const n of opsNode?.children ?? []) {
      const o = res.objects.find((x) => x.name === n.name)
      if (o?.commands && valueOf(o, 'Active') !== false) items.push({ job: j, op: o, matrix: body?.matrix })
    }
  }
  const key = JSON.stringify(items.map((i) => [i.job, i.op.name, i.op.commands?.length, i.op.commands?.[i.op.commands.length - 1], i.matrix, st.sel.includes(camRef(i.job, i.op.name))]))
  if (key === drawnKey) return
  drawnKey = key
  const g = new THREE.Group()
  for (const it of items) {
    const sel = st.sel.includes(camRef(it.job, it.op.name))
    const og = new THREE.Group()
    for (const [rapid, pts] of polylines(it.op.commands!)) {
      const geo = new THREE.BufferGeometry().setFromPoints(pts.map((p) => new THREE.Vector3(p[0], p[1], p[2])))
      const line = new THREE.Line(geo, new THREE.LineBasicMaterial({ color: sel ? (getState().selPrefs?.color ? new THREE.Color(getState().selPrefs.color).getHex() : 0x1cad1c) : rapid ? RAPID : FEED }))
      line.userData.camRapid = rapid
      og.add(line)
    }
    og.name = `cam:${it.job}/${it.op.name}`
    og.applyMatrix4(partMatrix(it.matrix ? ({ matrix: it.matrix } as never) : undefined))
    g.add(og)
  }
  view.setHelper('cam-toolpaths', g.children.length ? g : null)
}
subscribe(() => drawToolpaths())
subs.add(() => drawToolpaths())

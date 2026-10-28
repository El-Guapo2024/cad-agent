// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/CAM/Path/Main/Gui/JobDlg.py: 2018 sliptonic
//   src/Mod/CAM/Path/Main/Gui/Job.py: 2017 sliptonic
//   src/Mod/CAM/Path/Op/Gui/Base.py: 2017 sliptonic
//   src/Mod/CAM/Path/Op/Gui/Profile.py: 2017 sliptonic
//   src/Mod/CAM/Path/Op/Gui/PocketBase.py: 2017 sliptonic
//   src/Mod/CAM/Path/Op/Gui/PocketShape.py: 2017 sliptonic
//   src/Mod/CAM/Path/Op/Gui/MillFace.py: 2017 sliptonic
//   src/Mod/CAM/Path/Op/Gui/Drilling.py: 2017 sliptonic
//   src/Mod/CAM/Path/Op/Gui/CircularHoleBase.py: 2017 sliptonic; 2025 Billy Huddleston
//   src/Mod/CAM/Path/Op/Gui/FeatureExtension.py: 2019 sliptonic
//   src/Mod/CAM/Path/Tool/Gui/Controller.py: 2019 sliptonic
//   src/Mod/CAM/Path/Dressup/Gui/Tags.py: 2017 sliptonic
//   src/Mod/CAM/Path/Post/Command.py: 2015 Dan Falck
// The CAM workbench's dialogs and task panels, from FreeCAD's own .ui files (uiforms-cam.ts) bound as the panels' code
// binds them: CAM_Job's dialog (DlgJobCreate.ui, JobCreate) and the Job's panel (PathEdit.ui, TaskPanel: its Setup,
// General, Output, Tools and Workplan tabs), an operation's panel (Base.py TaskPanel: a tab per feature the op has, Base
// Geometry, Base Location, Heights, Tool Controller, then the op's own page, the last one in front), the Holding Tags
// panel (HoldingTagsEdit.ui), a tool controller's (ToolControllerEdit.ui) and CAM_Post's choice of post-processor
// (DlgSelectPostProcessor.ui). A panel's edits are sent on OK (or Apply) as one step, named as FreeCAD's transaction
// ("Edit Job", "AreaOp Operation", "Edit HoldingTags Dress-up"); Cancel of a panel that a command opened undoes the
// command's step, as FreeCAD's abortTransaction and "Uncreate" do.
import { useEffect, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { QtForm, type Bindings } from './qtform'
import { CAM_FORMS } from './uiforms-cam'
import { closeTask, doUndo, openTask } from './actions'
import { getState, report, setState } from './store'
import { Icon, type IconName } from './icons'
import { TaskBox } from './panels'
import * as quantity from './quantity'
import { SCHEMAS } from './quantity'
import { applyCam, camObj, camRef, camState, numOf, partSelection, propOf, setCam, uniqueName, useCam, valueOf, type CamObj } from './cam'

type Dims = quantity.Quantity['dims']
const LEN: Dims = [1, 0, 0, 0, 0, 0, 0, 0]
// Path/Op/Base.py's features
const F = { Tool: 0x1, Depths: 0x2, Heights: 0x4, StartPoint: 0x8, FinishDepth: 0x10, StepDown: 0x20, NoFinalDepth: 0x40, Linking: 0x80,
  BaseVertexes: 0x100, BaseEdges: 0x200, BaseFaces: 0x400, BaseModels: 0x800, Locations: 0x1000, Coolant: 0x2000, Diameters: 0x4000 }
const BASE_GEOMETRY = F.BaseVertexes | F.BaseFaces | F.BaseEdges

function Buttons({ ok, cancel, apply, okOff }: { ok(): void; cancel(): void; apply?: () => void; okOff?: boolean }) {
  return (
    <div className="tbuttons">
      <button className="qbtn default" disabled={okOff} onClick={ok}>OK</button>
      <button className="qbtn" onClick={cancel}>Cancel</button>
      {apply && <button className="qbtn" disabled={okOff} onClick={apply}>Apply</button>}
    </div>)
}
const img = (name: string, size = 16) => <img src={`./freecad-icons/cam/${name}.svg`} width={size} height={size} alt="" />

export function CamTask({ job, other }: { job: string; other: string }) {
  const [kind, name, mode] = other.split(':')
  const create = mode === 'create'
  if (kind === 'jobcreate') return <JobCreateDialog />
  if (kind === 'job') return <JobPanel key={job} job={job} create={create} />
  if (kind === 'op') return <OpPanel key={`${job}/${name}`} job={job} name={name} create={create} />
  if (kind === 'tag') return <TagPanel key={`${job}/${name}`} job={job} name={name} create={create} />
  if (kind === 'tc') return <TcPanel key={`${job}/${name}`} job={job} name={name} />
  if (kind === 'post') return <PostDialog job={job} />
  return null
}

// ── the edits a panel holds until OK: per object, FreeCAD property name -> value ─────────────────────────────────
type Pending = Record<string, Record<string, unknown>>
function usePending(job: string) {
  const [pend, setPend] = useState<Pending>({})
  const [applied, setApplied] = useState(false)
  useCam((s) => s.docs[job])
  const obj = (n: string) => camObj(job, n)
  const get = (n: string, p: string): unknown => (pend[n] && p in pend[n] ? pend[n][p] : valueOf(obj(n), p))
  const put = (n: string, p: string, v: unknown) => setPend((x) => ({ ...x, [n]: { ...x[n], [p]: v } }))
  const ops = (): Record<string, unknown>[] => Object.entries(pend).flatMap(([n, props]) => {
    const { Label, ...rest } = props
    const out: Record<string, unknown>[] = []
    if (Object.keys(rest).length) out.push({ op: 'set', name: n, props: rest })
    if (typeof Label === 'string' && Label !== obj(n)?.label) out.push({ op: 'label', name: n, to: Label })
    return out
  })
  /** The edits as the panel's step (FreeCAD's transaction), or folded into it after an Apply. */
  const send = async (step: string): Promise<boolean> => {
    const o = ops()
    if (!o.length) return true
    const doc = await applyCam(job, o, step, applied)
    if (!doc) return false
    setPend({})
    setApplied(true)
    return true
  }
  /** Cancel: what the panel applied goes (abortTransaction), and with create the command's own step too. */
  const cancel = async (create: boolean) => {
    closeTask()
    const n = (applied ? 1 : 0) + (create ? 1 : 0)
    if (n) await doUndo(n)
  }
  return { pend, get, put, send, cancel, obj, applied }
}
type P = ReturnType<typeof usePending>
/** PathGuiUtil.QuantitySpinBox over a property: its value in its unit (FreeCAD's internal mm, mm/s, °), its expression in
 *  the tool tip; a value typed clears the expression, as the property view does. */
function qbind(p: P, n: string, prop: string, extra: Record<string, unknown> = {}) {
  const o = p.obj(n)
  const pr = propOf(o, prop)
  if (!pr) return { hide: true }
  const v = p.get(n, prop) as { value?: number; unit?: number[] } | number | string
  const dims = ((pr.value as { unit?: number[] })?.unit ?? LEN) as Dims
  const unit = quantity.unitString(dims)
  const num = typeof v === 'number' ? v : typeof v === 'string' ? Number.parseFloat(v) : Number(v?.value ?? 0)
  const shown = unit === 'deg' ? ' °' : unit ? ` ${unit}` : ''
  return { value: num, suffix: shown, min: -1e9, max: 1e9, dec: 2, lazy: true, tip: [pr.doc, pr.expression ? `= ${pr.expression}` : ''].filter(Boolean).join('\n'),
    set: (x: number) => p.put(n, prop, unit ? `${x} ${unit}` : x), ...extra }
}
function cbind(p: P, n: string, prop: string, extra: Record<string, unknown> = {}) {
  const pr = propOf(p.obj(n), prop)
  // a check box the page shows for a property this op does not have (MillFace's Use Outline): unticked, and it does nothing
  if (!pr) return { value: false, off: true, why: `${p.obj(n)?.label ?? n} has no ${prop}`, ...extra }
  return { value: p.get(n, prop) === true, set: (x: boolean) => p.put(n, prop, x), ...extra }
}
/** PathGuiUtil.populateCombobox: the op's property enumerations, "raw" (text, value), else the enumeration's values. */
function ebind(p: P, n: string, prop: string, extra: Record<string, unknown> = {}) {
  const o = p.obj(n)
  const pr = propOf(o, prop)
  if (!pr) return { hide: true }
  const pairs = o?.enum_labels?.[prop] ?? (pr.enums ?? []).map((x) => [x, x] as [string, string])
  return { value: String(p.get(n, prop)), opts: pairs.map(([t, v]) => [v, t] as const), set: (x: string) => p.put(n, prop, x), ...extra }
}

// ── CAM_Job: JobCreate (DlgJobCreate.ui) ─────────────────────────────────────────────────────────────────────────
function JobCreateDialog() {
  const s = getState()
  const parts = [...new Set((s.scene?.bodies ?? []).filter((b) => b.part && b.kind !== 'bought').map((b) => b.part!))].sort()
  const preset = partSelection().map(([p]) => p)
  const [chosen, setChosen] = useState<string[]>(preset)
  const done = async (ok: boolean) => {
    if (!ok || !chosen.length) { closeTask(); return }
    const job = uniqueName('Job')
    const doc = await applyCam(job, [{ op: 'new_job', parts: chosen }], 'Create Job')
    if (!doc) { closeTask(); return }
    setCam({ sel: [camRef(job, job)] })
    setState({ selected: [], subSel: [] })
    // Job.Create: obj.ViewObject.Proxy.editObject(obj.Stock), the Job's panel
    openTask('cam', job, 'job:Stock:create')
  }
  const schema = SCHEMAS.find((x) => x.num === (getState().units?.schema ?? 0)) ?? SCHEMAS[0]
  const bind: Bindings = {
    templateGroup: {}, modelGroup: {}, unitSchemaGroup: {},
    jobTemplate: { value: 0, opts: [[0, '(none)']], off: true, why: 'job templates (job_*.json) are not read here' },
    unitSchemaCombo: { value: schema.num, opts: SCHEMAS.map((x) => [x.num, x.description] as const), off: true, why: 'the units are Preferences > General > Units' },
    modelTree: { node: <div className="qf-list" data-cam="models">
      <div className="qf-list-row"><b>Solids</b></div>
      {parts.map((pt) => <label key={pt} className="qf-list-row" style={{ paddingLeft: 18 }}>
        <input type="checkbox" checked={chosen.includes(pt)} onChange={(e) => setChosen((c) => e.target.checked ? [...c, pt] : c.filter((x) => x !== pt))} />{pt}</label>)}
    </div> },
  }
  return createPortal(
    <div className="msgbox-back" onKeyDown={(e) => { e.stopPropagation(); if (e.key === 'Escape') void done(false) }}>
      <div className="msgbox camdlg" role="dialog" aria-label="New Job" data-cam-dialog="jobcreate" style={{ minWidth: 520 }}>
        <div className="msgbox-title">New Job</div>
        <div className="camdlg-body"><QtForm form={CAM_FORMS.jobcreate} bind={bind} /></div>
        <div className="msgbox-buttons camdlg-buttons">
          <button className="qbtn" onClick={() => void done(false)}>Cancel</button>
          <button className="qbtn default" disabled={!chosen.length} onClick={() => void done(true)}>OK</button>
        </div>
      </div>
    </div>, document.body)
}

// ── the Job's panel (Job.py TaskPanel over PathEdit.ui) ─────────────────────────────────────────────────────────
const STOCK_TYPES: [string, string][] = [['CreateBox', 'Create box'], ['CreateCylinder', 'Create cylinder'], ['FromBase', "Extend model's bounding box"], ['Unknown', 'Use existing solid']]
const POSTS = ['generic', 'grbl', 'linuxcnc']
function JobPanel({ job, create }: { job: string; create: boolean }) {
  const p = usePending(job)
  const o = p.obj(job)
  const doc = camState().docs[job]
  const stock = p.obj('Stock') ?? doc?.result?.objects.find((x) => x.kind === 'Stock')
  const stockName = stock?.name ?? 'Stock'
  const tcs = doc?.result?.objects.filter((x) => x.kind === 'ToolController') ?? []
  const [tab, setTab] = useState(0)
  if (!o) return null
  const ext = (axis: string, side: string) => qbind(p, stockName, `Ext${axis}${side}`)
  const off = (why: string) => ({ off: true, why })
  const bind: Bindings = {
    pathEdit: { value: tab, set: (i: number) => setTab(i) },
    toolBox_2: {}, jobBox: {}, toolBox: {}, advancedSubTabs: {},
    stockGroup: {}, stock: { value: 'FromBase', opts: STOCK_TYPES.map(([v, t]) => [v, t] as const), off: true, why: "the stock is the model's bounding box, extended" },
    refreshStock: off('the stock follows the model at each recompute'),
    stockExtXneg: ext('X', 'neg'), stockExtXpos: ext('X', 'pos'), stockExtYneg: ext('Y', 'neg'), stockExtYpos: ext('Y', 'pos'), stockExtZneg: ext('Z', 'neg'), stockExtZpos: ext('Z', 'pos'),
    btnMaterial: off('stock materials'), pickTargetGroup: {}, pickTargetModel: off('the model is what the 3D view picks'), pickTargetStock: off('the model is what the 3D view picks'),
    modelAlignGroup: {}, modelMoveGroup: {}, linkStockAndModel: off('the model is placed by the part'),
    jobLabel: { value: String(p.get(job, 'Label') ?? o.label), set: (v: string) => p.put(job, 'Label', v) },
    jobModel: { node: <div className="qf-list" data-cam="jobModel">{(doc?.result?.job?.model ?? []).map((m) => <div key={m} className="qf-list-row">{m}</div>)}</div> },
    jobModelEdit: off('the parts a job machines are set when it is made'),
    jobDescription: { node: <textarea className="qf-text" value={String(p.get(job, 'Description') ?? '')} onChange={(e) => p.put(job, 'Description', e.target.value)} style={{ width: '100%', minHeight: 60 }} /> },
    jobMachine: { value: 0, opts: [[0, '(Legacy post-processor)']], off: true, why: 'machine definitions' }, jobMachineNew: off('machine definitions'),
    postProcessorOutputFile: { value: String(p.get(job, 'PostProcessorOutputFile') ?? ''), set: (v: string) => p.put(job, 'PostProcessorOutputFile', v) },
    postProcessorSetOutputFile: off('`cad cam post` writes out/cam/<Job>.nc'),
    postProcessor: { value: String(p.get(job, 'PostProcessor') ?? ''), opts: [['', ''], ...POSTS.map((x) => [x, x] as const)], set: (v: string) => p.put(job, 'PostProcessor', v),
      tip: "FreeCAD's linuxcnc, grbl and generic post-processors are the ones this app has" },
    postProcessorArguments: { value: String(p.get(job, 'PostProcessorArgs') ?? ''), set: (v: string) => p.put(job, 'PostProcessorArgs', v) },
    groupBox_7: {}, wcslist: { node: <div className="qf-list" data-cam="wcslist">{['G54', 'G55', 'G56', 'G57', 'G58', 'G59', 'G59.1', 'G59.2', 'G59.3', 'G59.4', 'G59.5', 'G59.6', 'G59.7', 'G59.8', 'G59.9'].map((w) =>
      <label key={w} className="qf-list-row"><input type="checkbox" checked={((p.get(job, 'Fixtures') as string[]) ?? []).includes(w)} disabled readOnly />{w}</label>)}</div> },
    orderBy: { ...ebind(p, job, 'OrderOutputBy') }, splitOutput: { ...cbind(p, job, 'SplitOutput') },
    toolControllerList: { node: <div className="qf-list" data-cam="toolControllerList"><table><thead><tr><th>Tool Controller</th><th>Number</th><th>H Feed</th><th>V Feed</th><th>Spindle</th></tr></thead>
      <tbody>{tcs.map((tc) => <tr key={tc.name} onDoubleClick={() => openTask('cam', job, `tc:${tc.name}`)}><td>{tc.label}</td><td>{String(valueOf(tc, 'ToolNumber'))}</td>
        <td>{fmt0(numOf(tc, 'HorizFeed'))}</td><td>{fmt0(numOf(tc, 'VertFeed'))}</td><td>{`${valueOf(tc, 'SpindleDir') === 'Reverse' ? '-' : '+'}${fmt0(Number(valueOf(tc, 'SpindleSpeed') ?? 0))}`}</td></tr>)}</tbody></table></div> },
    toolControllerEdit: off('double-click a tool controller'), toolControllerAdd: off('add a library bit with `cad cam tool SLUG JOB --bit 5mm_Endmill`'), toolControllerDelete: off('Delete it in the tree'),
    operationsList: { node: <div className="qf-list" data-cam="operationsList">{(doc?.result?.job?.operations ?? []).map((n) => <div key={n} className="qf-list-row">{camObj(job, n)?.label ?? n}</div>)}</div> },
    operationUp: off('the order is the order the ops were made'), operationDown: off('the order is the order the ops were made'), operationEdit: off('double-click an op in the tree'), operationDelete: off('Delete it in the tree'),
    opDefaultOp: off('the setup sheet\'s op defaults'),
  }
  const ok = async () => { if (await p.send('Edit Job')) closeTask() }
  return (
    <div className="tasks">
      <Buttons ok={() => void ok()} cancel={() => void p.cancel(create)} />
      <TaskBox title="Job Edit" icon="cam-CAM_Job"><QtForm form={CAM_FORMS.job} bind={bind} /></TaskBox>
    </div>)
}
const fmt0 = (n: number) => String(Math.round(n * 1000) / 1000)

// ── an operation's panel (Path/Op/Gui/Base.py TaskPanel) ────────────────────────────────────────────────────────
type Page = { title: string; icon: string; node: ReactNode }
function OpPanel({ job, name, create }: { job: string; name: string; create: boolean }) {
  const p = usePending(job)
  const o = p.obj(name)
  const doc = camState().docs[job]
  const [cur, setCur] = useState<number | null>(null)
  if (!o) return null
  const feat = o.features ?? 0
  const kind = o.kind ?? ''
  const pages: Page[] = []
  if (feat & BASE_GEOMETRY) pages.push({ title: 'Base Geometry', icon: 'CAM_BaseGeometry', node: kind === 'Drilling' ? <HoleGeometry p={p} job={job} o={o} /> : <BaseGeometry p={p} job={job} o={o} /> })
  // PocketShape's taskPanelBaseLocationPage is its Extensions page (Path/Op/Gui/FeatureExtension.py)
  if (feat & F.Locations && kind === 'PocketShape') pages.push({ title: 'Extensions', icon: '', node: <Extensions p={p} o={o} /> })
  else if (feat & F.Locations) pages.push({ title: 'Base Location', icon: '', node: <QtForm form={CAM_FORMS.baseloc} bind={{ baseList: { node: <div className="qf-list" data-cam="locations"><table><thead><tr><th>X</th><th>Y</th></tr></thead><tbody>
    {((p.get(name, 'Locations') as number[][]) ?? []).map((l, i) => <tr key={i}><td>{fmtQ(l[0])}</td><td>{fmtQ(l[1])}</td></tr>)}</tbody></table></div> },
    addRemoveEdit: {}, addLocation: { off: true, why: 'locations are picked in the 3D view in FreeCAD' }, removeLocation: { off: true }, editLocation: { off: true } }} /> })
  if (feat & F.Heights) pages.push({ title: 'Heights', icon: 'CAM_Heights', node: <Heights p={p} o={o} feat={feat} /> })
  if (feat & (F.Tool | F.Coolant)) pages.push({ title: 'Tool Controller', icon: 'CAM_ToolController', node: <ToolControllerPage p={p} job={job} o={o} feat={feat} /> })
  pages.push({ title: 'Operation', icon: '', node: <OpPage p={p} o={o} /> })
  const at = cur ?? pages.length - 1
  const title = { Profile: 'Profile', PocketShape: 'Pocket Shape', MillFace: 'MillFace', Drilling: 'Drilling' }[kind] ?? o.label
  const ok = async () => { if (await p.send('AreaOp Operation')) closeTask() }
  void doc
  return (
    <div className="tasks" data-cam-panel={name}>
      <Buttons ok={() => void ok()} cancel={() => void p.cancel(create)} apply={() => void p.send('AreaOp Operation')} />
      <TaskBox title={title} icon={(o.icon ? `cam-${o.icon}` : 'cam-CAM_Profile') as IconName}>
        <div className="qf-tabs">
          <div className="qf-tabbar" role="tablist">{pages.map((pg, i) => <button key={pg.title} type="button" role="tab" aria-selected={i === at} className={'qf-tab' + (i === at ? ' cur' : '')}
            data-cam-tab={pg.title} onClick={() => setCur(i)}>{pg.icon && img(pg.icon, 14)} {pg.title}</button>)}</div>
          <div className="qf-tabpage">{pages[at]?.node}</div>
        </div>
      </TaskBox>
    </div>)
}
const fmtQ = (v: number) => quantity.userString({ value: v, dims: LEN }).text
function cloneLabel(job: string, part: string): string {
  const res = camState().docs[job]?.result?.job
  const model = res?.tree.children.find((c) => c.name.startsWith('Model'))
  const i = res?.model.indexOf(part) ?? -1
  return (i >= 0 ? model?.children[i]?.label : undefined) ?? part
}
/** TaskPanelBaseGeometryPage: "<clone>.<sub>" per element; Add takes the 3D view's selection (addBase), Remove the list's,
 *  Clear all of them. */
function BaseGeometry({ p, job, o }: { p: P; job: string; o: CamObj }) {
  const base = (p.get(o.name, 'Base') as [string, string[]][]) ?? []
  const [sel, setSel] = useState<number[]>([])
  const items = base.flatMap(([part, subs]) => subs.map((s) => [part, s] as [string, string]))
  const setItems = (xs: [string, string][]) => {
    const groups: [string, string[]][] = []
    for (const [part, s] of xs) { const g = groups.find((x) => x[0] === part); if (g) g[1].push(s); else groups.push([part, [s]]) }
    p.put(o.name, 'Base', groups)
  }
  const pick = partSelection().filter(([, s]) => s.length)
  // modifyPanel: the job's other operations that hold base geometry, by label, to import from (hidden when there are none)
  const doc = camState().docs[job]
  const others = (doc?.result?.job?.operations ?? []).map((n) => camObj(job, n)).filter((x): x is CamObj => !!x && x.name !== o.name
    && Array.isArray(valueOf(x, 'Base')) && (valueOf(x, 'Base') as unknown[]).length > 0)
  const labels = others.map((x) => x.label).sort()
  const [from, setFrom] = useState(labels[0] ?? '')
  const bind: Bindings = {
    geometryImportList: labels.length ? { value: from, opts: labels.map((l) => [l, l] as const), set: (v: string) => setFrom(v) } : { hide: true },
    geometryImportButton: labels.length ? { click: () => {
      const src = others.find((x) => x.label === from)
      const add = ((valueOf(src, 'Base') as [string, string[]][]) ?? []).flatMap(([part, subs]) => subs.map((s) => [part, s] as [string, string]))
      setItems([...items, ...add.filter(([a, b]) => !items.some(([c, d]) => a === c && b === d))])
    } } : { hide: true },
    baseList: { node: <div className="qf-list" data-cam="baseList">{items.map(([part, s], i) => <div key={`${part}.${s}`} className={'qf-list-row' + (sel.includes(i) ? ' sel' : '')}
      onClick={() => setSel([i])}>{`${cloneLabel(job, part)}.${s}`}</div>)}</div> },
    addBase: { off: !pick.length, why: 'select faces or edges of the part in the 3D view', click: () => {
      const add = pick.flatMap(([part, subs]) => subs.map((s) => [part, s] as [string, string])).filter(([a, b]) => !items.some(([c, d]) => a === c && b === d))
      setItems([...items, ...add])
    } },
    deleteBase: { click: () => { setItems(items.filter((_, i) => !sel.includes(i))); setSel([]) } },
    clearBase: { click: () => { setItems([]); setSel([]) } },
    label: {},
  }
  return <QtForm form={CAM_FORMS.basegeom} bind={bind} />
}
/** TaskPanelHoleGeometryPage: a row per hole (order, feature, diameter, X, Y, blind), from the op's own holeDiameter and
 *  holePosition (cam_doc.py's "holes"). */
function HoleGeometry({ p, job, o }: { p: P; job: string; o: CamObj }) {
  const holes = o.holes ?? []
  const base = (p.get(o.name, 'Base') as [string, string[]][]) ?? []
  const pick = partSelection().filter(([, s]) => s.length)
  const bind: Bindings = {
    label_2: {}, sortMode: { ...ebind(p, o.name, 'SortingMode') }, checkBox: { value: holes.every((h) => h.enabled), off: true, why: 'every hole the op holds is drilled' },
    lineEdit: { value: '', off: true, why: 'the filter' },
    baseList: { node: <div className="qf-list" data-cam="holes"><table><thead><tr>{['#', 'Feature', 'Diameter', 'X', 'Y', 'Blind'].map((h) => <th key={h}>{h}</th>)}</tr></thead>
      <tbody>{holes.map((h, i) => <tr key={h.feature}><td>{i + 1}</td><td>{`${cloneLabel(job, h.part)}.${h.sub}`}</td><td>{h.diameter === null ? '---' : fmtQ(h.diameter)}</td>
        <td>{h.x === null ? '---' : fmtQ(h.x)}</td><td>{h.y === null ? '---' : fmtQ(h.y)}</td><td>{h.blind === null ? '---' : h.blind ? 'Yes' : 'No'}</td></tr>)}</tbody></table></div> },
    addBase: { off: !pick.length, why: 'select the holes\' faces or edges in the 3D view', click: () => {
      const groups = base.map(([a, s]) => [a, [...s]] as [string, string[]])
      for (const [part, subs] of pick) { const g = groups.find((x) => x[0] === part); if (g) for (const s of subs) { if (!g[1].includes(s)) g[1].push(s) } else groups.push([part, subs]) }
      p.put(o.name, 'Base', groups)
    } },
    deleteBase: { off: true, why: 'Clear All, then Add' }, resetBase: { off: true, why: 'auto-select' },
    clearBase: { click: () => p.put(o.name, 'Base', []) },
    label: {},
  }
  void job
  return <QtForm form={CAM_FORMS.baseholegeom} bind={bind} />
}
/** TaskPanelExtensionPage (PageOpPocketExtEdit.ui): with no extension held, "Enable extensions" is off and the rest with it
 *  (setFields: extensionEdit disabled). Choosing the edges to extend is not done here. */
function Extensions({ p, o }: { p: P; o: CamObj }) {
  const held = ((valueOf(o, 'ExtensionFeature') as unknown[]) ?? []).length > 0
  const why = 'choosing the edges a pocket extends is not done here'
  const bind: Bindings = {
    enableExtensions: { value: held, off: true, why },
    extensionEdit: { off: !held }, widget_2: {}, widget: {}, label: {},
    showExtensions: { value: false, off: true, why }, extendCorners: { value: p.get(o.name, 'ExtensionCorners') === true, off: true, why },
    defaultLength: { ...qbind(p, o.name, 'ExtensionLengthDefault'), off: true, why },
    extensionTree: { node: <div className="qf-list" data-cam="extensions" /> },
    buttonEnable: { off: true, why }, buttonDisable: { off: true, why }, buttonClear: { off: true, why },
  }
  return <QtForm form={CAM_FORMS.pocketext} bind={bind} />
}
/** TaskPanelHeightsPage: the heights and depths the op has (FeatureDepths, FeatureStepDown, FeatureFinishDepth,
 *  FeatureNoFinalDepth), the Linking group, the diagram. */
function Heights({ p, o, feat }: { p: P; o: CamObj; feat: number }) {
  const n = o.name
  const depths = !!(feat & F.Depths), final = depths && !(feat & F.NoFinalDepth), step = !!(feat & F.StepDown), finish = depths && !!(feat & F.FinishDepth)
  const strategies: [string, string][] = ['Clearance Height', 'Retract Height', 'Line of Sight', 'Tool Diameter', 'Tool Shape'].map((x) => [x, x])
  const bind: Bindings = {
    workplaneLabel: {}, workplane: { value: '', opts: [['', 'None (Job XY)']], off: true, why: 'work planes' },
    heightsDiagram: { node: img(finish ? 'CAM_HeightsDiagram' : 'CAM_HeightsDiagram_NoFinish', 120) },
    label_9: {}, label_7: {}, clearanceHeight: qbind(p, n, 'ClearanceHeight'), safeHeight: qbind(p, n, 'SafeHeight'),
    startDepth: depths ? qbind(p, n, 'StartDepth') : { hide: true }, startDepthLabel: { hide: !depths }, startDepthSet: { hide: !depths, off: true, why: 'pick a face for its depth' },
    finalDepth: final ? qbind(p, n, 'FinalDepth') : depths ? { off: true, why: 'FinalDepth cannot be modified for this operation.' } : { hide: true },
    finalDepthLabel: { hide: !depths }, finalDepthSet: { hide: !final, off: true, why: 'pick a face for its depth' },
    stepDown: step ? qbind(p, n, 'StepDown') : { hide: true }, stepDownLabel: { hide: !step },
    finishDepth: finish ? qbind(p, n, 'FinishDepth') : { hide: true }, finishDepthLabel: { hide: !finish },
    resetDefaults: { off: true, why: 'clear a value\'s expression in the property view' },
    groupBoxLinking: { hide: !(feat & F.Linking) }, labelCollisionAvoidanceStrategy: {}, labelCollisionClearance: {},
    CollisionAvoidanceStrategy: { ...ebind(p, n, 'CollisionAvoidanceStrategy'), opts: strategies.map(([v, t]) => [v, t] as const) },
    CollisionClearance: qbind(p, n, 'CollisionClearance'),
  }
  return <QtForm form={CAM_FORMS.heights} bind={bind} />
}
/** ToolControllerEditor (ToolControllerEdit.ui): the tool controller's name, number, feeds and spindle. */
function tcBind(p: P, tc: string, count = 0): Bindings {
  const o = p.obj(tc)
  if (!o) return {}
  return {
    toolControllerEditor: {}, frame: {}, groupBox_4: {}, groupBox_3: {},
    tcOperationCountLabel: count ? { text: `This tool controller is used by ${count === 1 ? '1 other operation' : `${count} other operations`}.` } : { hide: true },
    tcName: { value: String(p.get(tc, 'Label') ?? o.label), set: (v: string) => p.put(tc, 'Label', v) },
    tcNumber: { value: Number(p.get(tc, 'ToolNumber') ?? 1), min: 0, max: 9999, set: (v: number) => p.put(tc, 'ToolNumber', v) },
    horizFeed: qbind(p, tc, 'HorizFeed'), vertFeed: qbind(p, tc, 'VertFeed'), leadInFeed: qbind(p, tc, 'LeadInFeed'), leadOutFeed: qbind(p, tc, 'LeadOutFeed'),
    rampFeed: qbind(p, tc, 'RampFeed'), noEngagementFeed: qbind(p, tc, 'NoEngagementFeed'), horizRapid: qbind(p, tc, 'HorizRapid'), vertRapid: qbind(p, tc, 'VertRapid'),
    spindleSpeed: { value: Number(p.get(tc, 'SpindleSpeed') ?? 0), min: 0, max: 1e6, dec: 2, set: (v: number) => p.put(tc, 'SpindleSpeed', v) },
    spindleDirection: ebind(p, tc, 'SpindleDir'),
  }
}
/** TaskPanelToolControllerPage: the op's tool controller (and the editor of it) and its coolant mode. */
function ToolControllerPage({ p, job, o, feat }: { p: P; job: string; o: CamObj; feat: number }) {
  const doc = camState().docs[job]
  const tcs = doc?.result?.objects.filter((x) => x.kind === 'ToolController') ?? []
  const tc = String(p.get(o.name, 'ToolController') ?? '')
  const tcLabel = camObj(job, tc)?.label ?? tc
  const base = (x: CamObj) => { let b = x; for (let i = 0; i < 9 && b.kind?.startsWith('Dressup'); i++) { const n = valueOf(b, 'Base'); const nb = typeof n === 'string' ? camObj(job, n) : undefined; if (!nb) break; b = nb } return b }
  const others = (doc?.result?.job?.operations ?? []).map((n) => camObj(job, n)).filter(Boolean).map((x) => base(x!)).filter((x) => x.name !== o.name && valueOf(x, 'ToolController') === tc).length
  const coolant = !!(feat & F.Coolant)
  const modes = (valueOf(camState().docs[job]?.result?.objects.find((x) => x.kind === 'SetupSheet'), 'CoolantModes') as string[] | undefined) ?? ['None', 'Flood', 'Mist']
  const bind: Bindings = {
    frame: {}, toolControllerLabel: {},
    toolController: { value: tc, opts: [...tcs.map((t) => [t.name, t.label] as const), ['__sep', ''], ['__copy', `Copy ${tcLabel}…`], ['__new', 'New tool controller…']],
      set: (v: string) => { if (!v.startsWith('__')) p.put(o.name, 'ToolController', v); else report('warn', 'a new tool controller: `cad cam tool SLUG JOB --bit 5mm_Endmill`') } },
    coolantControllerLabel: { hide: !coolant }, coolantController: coolant ? { value: String(p.get(o.name, 'CoolantMode') ?? 'None'), opts: modes.map((m) => [m, m] as const), set: (v: string) => p.put(o.name, 'CoolantMode', v) } : { hide: true },
  }
  return <>
    <QtForm form={CAM_FORMS.tc} bind={bind} />
    {tc && camObj(job, tc) && <QtForm form={CAM_FORMS.tcedit} bind={tcBind(p, tc, others)} />}
  </>
}
/** The op's own page: Profile.py, PocketBase.py (PocketShape, MillFace), Drilling.py. */
function OpPage({ p, o }: { p: P; o: CamObj }) {
  const n = o.name
  const k = o.kind
  if (k === 'Profile') {
    const base = (p.get(n, 'Base') as [string, string[]][]) ?? []
    const hasFace = base.some(([, s]) => s.some((x) => x.startsWith('Face')))
    const passes = Number(p.get(n, 'NumPasses') ?? 1)
    const thr = numOf(o, 'RetractThreshold')
    const bind: Bindings = {
      widget: {}, widget_2: {}, cutSideLabel: {}, directionLabel: {}, extraOffsetLabel: {}, thresholdLabel: {}, numPassesLabel: {}, stepoverLabel: {},
      cutSide: ebind(p, n, 'Side'), direction: ebind(p, n, 'Direction'),
      extraOffset: qbind(p, n, 'OffsetExtra'), threshold: qbind(p, n, 'RetractThreshold'), stepover: qbind(p, n, 'Stepover', { off: passes <= 1 }),
      thresholdToggle: { click: () => p.put(n, thr === 0 ? 'ExpressionEngine' : 'RetractThreshold', thr === 0 ? { RetractThreshold: 'OpToolDiameter' } : '0 mm') },
      numPasses: { value: passes, min: 1, max: 100, set: (v: number) => p.put(n, 'NumPasses', v) },
      useCompensation: cbind(p, n, 'UseComp'), useStartPoint: cbind(p, n, 'UseStartPoint'),
      processHoles: cbind(p, n, 'processHoles', { hide: !hasFace }), processPerimeter: cbind(p, n, 'processPerimeter', { hide: !hasFace }), processCircles: cbind(p, n, 'processCircles', { hide: !hasFace }),
      setStartPoint: { off: true, why: 'set Start Point in the property view' },
    }
    return <QtForm form={CAM_FORMS.profile} bind={bind} />
  }
  if (k === 'PocketShape' || k === 'MillFace') {
    const facing = k === 'MillFace'
    const pattern = String(p.get(n, 'ClearingPattern'))
    const thr = numOf(o, 'RetractThreshold')
    const bind: Bindings = {
      facingWidget: { hide: !facing }, widget: {}, pocketWidget: {}, boundaryShape_label: {}, cutMode_label: {}, clearingPattern_label: {}, angle_label: {}, stepOver_label: {},
      extraOffset_label: {}, threshold_label: {},
      boundaryShape: facing ? ebind(p, n, 'BoundaryShape') : { hide: true },
      cutMode: ebind(p, n, 'CutMode'), clearingPattern: ebind(p, n, 'ClearingPattern'),
      angle: { value: numOf(o, 'Angle'), min: -360, max: 360, dec: 2, set: (v: number) => p.put(n, 'Angle', `${v} deg`), off: pattern === 'Offset' },
      stepOver: { value: Number(p.get(n, 'StepOver') ?? 50), min: 1, max: 100, set: (v: number) => p.put(n, 'StepOver', v) },
      extraOffset: qbind(p, n, 'ExtraOffset'), threshold: qbind(p, n, 'RetractThreshold'),
      thresholdToggle: { click: () => p.put(n, thr === 0 ? 'ExpressionEngine' : 'RetractThreshold', thr === 0 ? { RetractThreshold: 'OpToolDiameter' } : '0 mm') },
      useOutline: cbind(p, n, 'UseOutline'), clearEdges: facing ? cbind(p, n, 'ClearEdges') : { hide: true }, useRestMachining: cbind(p, n, 'UseRestMachining'),
      useStartPoint: cbind(p, n, 'UseStartPoint'), setStartPoint: { off: true, why: 'set Start Point in the property view' },
    }
    return <QtForm form={CAM_FORMS.pocket} bind={bind} />
  }
  if (k === 'Drilling') {
    const peck = p.get(n, 'PeckEnabled') === true
    const bind: Bindings = {
      frame: {}, label_strategy: {}, dwellTimelabel: {}, Offsetlabel: {}, peckDepthLabel: {}, peckRetractLabel: {},
      Strategy: ebind(p, n, 'Strategy'), KeepToolDownEnabled: cbind(p, n, 'KeepToolDown'), peckEnabled: cbind(p, n, 'PeckEnabled'),
      peckDepth: qbind(p, n, 'PeckDepth'), peckRetract: qbind(p, n, 'PeckRetract'), dwellTime: { value: Number(p.get(n, 'DwellTime') ?? 1), min: 0, max: 1e6, dec: 2, set: (v: number) => p.put(n, 'DwellTime', v) },
      dwellEnabled: cbind(p, n, 'DwellEnabled'), chipBreakEnabled: cbind(p, n, 'ChipBreakEnabled', { off: !peck }), feedRetractEnabled: cbind(p, n, 'FeedRetractEnabled'),
      ExtraOffset: ebind(p, n, 'ExtraOffset'),
    }
    return <QtForm form={CAM_FORMS.drilling} bind={bind} />
  }
  return null
}

// ── PathDressupTagTaskPanel (HoldingTagsEdit.ui) ─────────────────────────────────────────────────────────────────
function TagPanel({ job, name, create }: { job: string; name: string; create: boolean }) {
  const p = usePending(job)
  const o = p.obj(name)
  const [tags, setTags] = useState<[number, number, boolean][] | null>(null)
  const [row, setRow] = useState(-1)
  useEffect(() => {
    if (o && tags === null) {
      const pos = (valueOf(o, 'Positions') as number[][]) ?? [], dis = (valueOf(o, 'Disabled') as number[]) ?? []
      setTags(pos.map((v, i) => [v[0], v[1], !dis.includes(i)]))
    }
  }, [o, tags])
  if (!o || !tags) return null
  const fmt = (v: number) => quantity.userString({ value: v, dims: LEN }).text
  const anyOff = tags.some((t) => !t[2])
  const bind: Bindings = {
    label_2: {}, label_3: {}, label_4: {}, label_5: {}, cbTagGeneration: {},
    ifWidth: { value: fmt(numOf(o, 'Width')), set: (v: string) => p.put(name, 'Width', v) },
    ifHeight: { value: fmt(numOf(o, 'Height')), set: (v: string) => p.put(name, 'Height', v) },
    ifRadius: { value: fmt(numOf(o, 'Radius')), set: (v: string) => p.put(name, 'Radius', v) },
    dsbAngle: { value: numOf(o, 'Angle'), min: 0, max: 90, dec: 2, set: (v: number) => p.put(name, 'Angle', `${v} deg`) },
    lwTags: { node: <div className="qf-list" data-cam="tags">{tags.map(([x, y, on], i) => <label key={i} className={'qf-list-row' + (i === row ? ' sel' : '')} onClick={() => setRow(i)}>
      <input type="checkbox" checked={on} onChange={(e) => setTags(tags.map((t, j) => (j === i ? [t[0], t[1], e.target.checked] : t)))} />{`${i}: (${fmt(x)}, ${fmt(y)})`}</label>)}</div> },
    pbClear: { click: () => { setTags([]); setRow(-1) } },
    pbRemove: { off: row < 0, click: () => { setTags(tags.filter((_, i) => i !== row)); setRow(-1) } },
    pbEdit: { off: true, why: 'a tag is placed by the dress-up; remove it, or Replace Existing Tags' },
    pbAdd: { off: true, why: 'a tag is picked on the path in the 3D view in FreeCAD' },
    pbCopy: { off: true, why: 'copying another dress-up\'s tags' },
    pbSwitch: { text: anyOff ? 'Enable All' : 'Disable All', click: () => setTags(tags.map((t) => [t[0], t[1], anyOff])) },
    sbMinCount: { value: 4, off: true, why: 'the dress-up keeps its counts' }, sbMaxCount: { value: 4, off: true, why: 'the dress-up keeps its counts' },
    pbGenerate: { off: true, why: 'clear the tags and OK: the dress-up makes them again' },
  }
  const fields = () => {
    // getFields: every tag at z 0, the disabled ones by index (the panel is dirty from the start, so OK writes them)
    p.put(name, 'Positions', tags.map((t) => [t[0], t[1], 0]))
    p.put(name, 'Disabled', tags.map((t, i) => (t[2] ? -1 : i)).filter((i) => i >= 0))
  }
  const ok = async () => {
    const pos = tags.map((t) => [t[0], t[1], 0]), dis = tags.map((t, i) => (t[2] ? -1 : i)).filter((i) => i >= 0)
    const props = { ...(p.pend[name] ?? {}), Positions: pos, Disabled: dis }
    const doc = await applyCam(job, [{ op: 'set', name, props }], 'Edit HoldingTags Dress-up', p.applied)
    if (doc) closeTask()
  }
  void fields
  return (
    <div className="tasks" data-cam-panel={name}>
      <Buttons ok={() => void ok()} cancel={() => void p.cancel(create)} apply={() => { void applyCam(job, [{ op: 'set', name, props: { ...(p.pend[name] ?? {}), Positions: tags.map((t) => [t[0], t[1], 0]), Disabled: tags.map((t, i) => (t[2] ? -1 : i)).filter((i) => i >= 0) } }], 'Edit HoldingTags Dress-up', p.applied) }} />
      <TaskBox title="Holding Tags" icon="cam-CAM_Dressup"><QtForm form={CAM_FORMS.tags} bind={bind} /></TaskBox>
    </div>)
}

// ── a tool controller's panel (TaskPanel of Path/Tool/Gui/Controller.py: "Tool Controller Editor") ───────────────
function TcPanel({ job, name }: { job: string; name: string }) {
  const p = usePending(job)
  if (!p.obj(name)) return null
  const ok = async () => { if (await p.send('Edit ToolController')) closeTask() }
  return (
    <div className="tasks" data-cam-panel={name}>
      <Buttons ok={() => void ok()} cancel={() => void p.cancel(false)} />
      <TaskBox title="Tool Controller Editor" icon="cam-CAM_ToolController"><QtForm form={CAM_FORMS.tcedit} bind={tcBind(p, name)} /></TaskBox>
    </div>)
}

// ── CAM_Post (Path/Post/Command.py): the job's post-processor (or the one chosen), its G-code saved ──────────────
function PostDialog({ job }: { job: string }) {
  const o = camObj(job, job)
  const set = String(valueOf(o, 'PostProcessor') ?? '')
  const [post, setPost] = useState(set || 'linuxcnc')
  const [busy, setBusy] = useState(false)
  const run = async (chosen: string) => {
    const slug = getState().slug
    if (!slug) return
    setBusy(true)
    try {
      const r = await fetch(`/api/${encodeURIComponent(slug)}/cam/${encodeURIComponent(job)}/post`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CAD': '1' },
        body: JSON.stringify({ post: chosen }) })
      const j = await r.json()
      if (!r.ok || j.exit !== 0) { report('err', `Post Process: ${j.error ?? j.text ?? r.statusText}`); return }
      const gcode = String(j.data?.gcode ?? '')
      const a = document.createElement('a')
      a.href = URL.createObjectURL(new Blob([gcode], { type: 'text/plain' }))
      a.download = `${job}.nc`
      a.click()
      setTimeout(() => URL.revokeObjectURL(a.href), 1000)
      report('msg', `${job}: ${chosen} wrote ${gcode.split('\n').length - 1} lines (out/cam/${job}.nc)`)
      ;(window as unknown as { __camLastGcode?: string }).__camLastGcode = gcode
    } finally { setBusy(false); closeTask() }
  }
  useEffect(() => { if (set) void run(set) }, [])   // eslint-disable-line react-hooks/exhaustive-deps
  if (set) return null
  // DlgSelectPostProcessor: the posts the preferences allow, the first selected
  return createPortal(
    <div className="msgbox-back" onKeyDown={(e) => { e.stopPropagation(); if (e.key === 'Escape') closeTask() }}>
      <div className="msgbox camdlg" role="dialog" aria-label="Select Post Processor" data-cam-dialog="post">
        <div className="msgbox-title">Select Post Processor</div>
        <div className="camdlg-body"><div className="qf-list" data-cam="posts">{POSTS.map((x) => <div key={x} className={'qf-list-row' + (x === post ? ' sel' : '')} onClick={() => setPost(x)} onDoubleClick={() => void run(x)}>{x}</div>)}</div></div>
        <div className="msgbox-buttons camdlg-buttons">
          <button className="qbtn" onClick={() => closeTask()}>Cancel</button>
          <button className="qbtn default" disabled={busy} onClick={() => void run(post)}>OK</button>
        </div>
      </div>
    </div>, document.body)
}
export { Icon }

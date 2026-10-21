// SPDX-License-Identifier: LGPL-2.1-or-later
// The CAD Agent workbench: task panels for the cad-agent CLI commands that had no UI yet
// (status, done, rules, cutlist, tables, tool, bought, render, approve, page). chrome.tsx wires
// the workbench's menu, toolbar and File entries onto these; this file is just their task panels
// plus the couple of commands (Approve, the page export) that act directly instead of opening
// one. Every command here runs the CLI the way an agent in a terminal would: POST /api/cad,
// {slug, argv}, back comes {exit, data, stderr} (api.ts's CadResult).
import { useEffect, useState } from 'react'
import { api, resultText, type CadResult, type CheckRow } from './api'
import { closeTask, loadChecks, loadStatus } from './actions'
import { cls, cmdline, ruleText, TaskBox, TaskButtons, vec } from './panels'
import { QComboBox } from './combo'
import { getState, report, useStore } from './store'
import { messageBox } from './msgbox'
import { Icon } from './icons'

/** Runs one cad command for a CAD Agent task: a Report view line for the call, then its result —
 *  a plain message when it ran cleanly, a Report view error otherwise (resultText is "what a cad
 *  call said when it didn't pass"). Never throws; callers read r.exit themselves (0 ok, 1 FAIL,
 *  2 UNCHECKED, 3 usage, 4 crash) because for Check/Verify/Done a non-zero exit is the answer,
 *  not a failure to answer. Rules and Tool envelope take no project; slug is '' for those. */
export async function agentRun(argv: string[]): Promise<CadResult> {
  const line = cmdline(argv)
  report('log', line)
  try {
    const r = await api.cad(getState().slug ?? '', argv)
    // A clean run says what the command says first ("mini_machine  bill of materials: 11 lines, 11 bodies"), as
    // a terminal's first line does; a verdict or a mistake says why (resultText).
    const first = (r.text ?? '').split('\n').find((l) => l.trim())?.trim().slice(0, 160)
    report(r.exit === 0 ? 'msg' : r.exit <= 2 ? 'warn' : 'err', r.exit === 0 ? `${line}: ${first || 'done'}` : `${line}: ${resultText(r)}`)
    return r
  } catch (e) {
    const text = e instanceof Error ? e.message : String(e)
    report('err', `${line}: ${text}`)
    return { exit: 4, stderr: text }
  }
}

/** A JSON-ish value (dicts of dicts, arrays, numbers, strings) to label/value rows, for the
 *  reference-table commands (Tables, Tool envelope) whose exact shape isn't hand-modelled here.
 *  Drops null/undefined leaves so an unset optional field just doesn't show a row. */
export function flattenRows(obj: unknown, prefix = ''): [string, string][] {
  if (obj === null || obj === undefined) return []
  if (Array.isArray(obj)) return [[prefix || 'value', obj.join(', ')]]
  if (typeof obj === 'object') return Object.entries(obj as Record<string, unknown>).flatMap(([k, v]) => flattenRows(v, prefix ? `${prefix}.${k}` : k))
  return [[prefix || 'value', String(obj)]]
}

/** "width=50 thickness=6" (spaces or commas) as `--set width=50 --set thickness=6`: the trial values `cad build`, `cad render`
 *  and `cad check --part` take for one run, which write nothing (`cad set` writes). */
export const overrideArgs = (text: string): string[] => text.split(/[\s,]+/).filter((x) => x.includes('=')).flatMap((kv) => ['--set', kv])

const ORDER: Record<string, number> = { FAIL: 0, UNCHECKED: 1, PASS: 2 }
/** The same rows table ChecksView draws for checks.json, reused here so Check/Verify/Done's
 *  own task panel reads exactly like the live Checks panel. */
export function RowsTable({ rows }: { rows: CheckRow[] }) {
  const sorted = [...rows].sort((a, b) => (ORDER[a.state] ?? 3) - (ORDER[b.state] ?? 3))
  return (
    <table className="ctable wrap">
      <thead><tr><th>State</th><th>Rule</th><th>Subject</th><th>Measured</th><th>Limit</th></tr></thead>
      <tbody>{sorted.map((r, i) => (
        <tr key={i} className={'st-' + r.state.toLowerCase()} title={r.source}>
          <td className="nw"><Icon name={r.state === 'PASS' ? 'pass' : r.state === 'FAIL' ? 'fail' : 'pending'} size={14} /> {r.state}</td>
          <td>{ruleText(r)}</td><td>{r.subject}</td><td>{r.measured ?? ''}</td><td>{r.limit ?? ''}</td>
        </tr>
      ))}</tbody>
    </table>
  )
}

// ── Check, Verify, Done gate ──────────────────────────────────────────────────
const GATE_HELP: Record<'check' | 'verify' | 'done', { label: string; icon: 'recompute' | 'pass' | 'pending'; help: string }> = {
  check: { label: 'Check', icon: 'recompute', help: 'run every gate and write checks.json (or, with --part, the fast part-only rules)' },
  verify: { label: 'Verify', icon: 'pass', help: 'the verifier: rebuild from source in a fresh process, run every gate, record the verdict with hashes and git commit' },
  done: { label: 'Done Gate', icon: 'pending', help: 'the gate: exit 0 only if the last verify passed, still matches the files, ran fresh, and (in a repo) verified committed work' },
}
/** Check / Verify / Done gate: one cad command, run synchronously so its own task panel can show
 *  the verdict, same data the live Checks panel and status bar read. Also refreshes those (like
 *  Edit > Recompute and Tools > Verify do) so the rest of the UI doesn't wait on the SSE round trip. */
function GateTask({ verb }: { verb: 'check' | 'verify' | 'done' }) {
  const slug = useStore((s) => s.slug), scene = useStore((s) => s.scene)
  const [busy, setBusy] = useState(false)
  const [data, setData] = useState<Record<string, any> | null>(null)
  const [err, setErr] = useState<string | null>(null)
  // The command's own options: the views the visual gate renders and judges (`--views`), the fast loop on one part
  // (`check --part`), and the passing rows (`--all`). The first run is the default one; the options apply to Run again.
  const [views, setViews] = useState<string[]>(['iso'])
  const [only, setOnly] = useState('')
  const [all, setAll] = useState(false)
  const [fresh, setFresh] = useState(false)      // check --no-cache: every part is built from source
  const [sets, setSets] = useState('')          // check --part --set: trial values for that part, this run only
  const parts = [...new Set((scene?.bodies ?? []).map((b) => b.part).filter((p): p is string => !!p))]
  const run = async () => {
    if (!slug) return
    setBusy(true); setErr(null)
    const opts = verb === 'done' ? [] : [...(verb === 'check' && only ? ['--part', only, ...overrideArgs(sets)] : []), ...(views.length ? ['--views', views.join(',')] : []),
      ...(all ? ['--all'] : []), ...(verb === 'check' && fresh ? ['--no-cache'] : [])]
    const r = await agentRun([verb, slug, ...opts])
    setBusy(false)
    if (r.exit > 2) { setErr(resultText(r)); return }
    setData(r.data ?? {})
    loadChecks(); loadStatus()
  }
  useEffect(() => { run() }, [slug, verb])
  const rows: CheckRow[] = data?.rows ?? data?.failing ?? []
  const verdict = !data ? null : verb === 'done' ? (data.done ? 'DONE' : data.verdict ?? 'UNCHECKED')
    : rows.length ? (rows.some((r) => r.state === 'FAIL') ? 'FAIL' : rows.some((r) => r.state === 'UNCHECKED') ? 'UNCHECKED' : 'PASS') : null
  const meta = flattenRows({ verified_utc: data?.verified_utc, commit: data?.commit ? String(data.commit).slice(0, 12) : undefined, mode: data?.process?.mode })
  const g = GATE_HELP[verb]
  return (
    <div className="tasks">
      <TaskButtons onOk={closeTask} />
      <div className="tbuttons"><button className="qbtn" disabled={busy || !slug} onClick={run}>Run again</button></div>
      <TaskBox title={g.label} icon={g.icon}>
        {busy && <p className="hint">Running cad {verb}…</p>}
        {err && <p className="hint err">{err}</p>}
        {verdict && <p><span className={cls('verdict', verdict.toLowerCase())}>{verdict}</span></p>}
        {!!data?.reasons?.length && <ul className="hint">{(data.reasons as string[]).map((r, i) => <li key={i}>{r}</li>)}</ul>}
        {!!rows.length && <RowsTable rows={rows} />}
        {!busy && !err && data && !rows.length && verb !== 'done' && <p className="hint">No rows.</p>}
        {!!meta.length && <table className="ctable wrap"><tbody>{meta.map(([k, v]) => <tr key={k}><td>{k}</td><td>{v}</td></tr>)}</tbody></table>}
        <p className="hint">{g.help}</p>
      </TaskBox>
      {verb !== 'done' && <TaskBox title="Options" icon="help">
        <p className="hint" style={{ marginTop: 0 }}>Views the visual gate renders and judges:</p>
        <div className="tgrid2">{RENDER_VIEWS.map((v) => (
          <label key={v} className="tcheck"><input type="checkbox" checked={views.includes(v)}
            onChange={(e) => setViews(e.target.checked ? [...views, v] : views.filter((x) => x !== v))} /> {v}</label>))}</div>
        {verb === 'check' && <label className="tfield"><span>Part</span>
          <QComboBox className="qselect-field" value={only} onChange={(e) => setOnly(e.target.value)} title="check --part: the fast loop, one part's rules and the fit of its bodies">
            <option value="">(whole project)</option>{parts.map((p) => <option key={p} value={p}>{p}</option>)}
          </QComboBox></label>}
        {verb === 'check' && only && <label className="tfield" title="check --part --set: other values for this part for one run; nothing is written"><span>Try values</span>
          <input value={sets} onChange={(e) => setSets(e.target.value)} placeholder="width=50 thickness=6" /></label>}
        <label className="tcheck"><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> Show passing rows too</label>
        {verb === 'check' && <label className="tcheck" title="check --no-cache: build every part from source, not from the project's build cache"><input type="checkbox" checked={fresh} onChange={(e) => setFresh(e.target.checked)} /> Build every part from source</label>}
        <div className="tbuttons"><button className="qbtn" disabled={busy || !slug || !views.length} onClick={run}>Run with these</button></div>
      </TaskBox>}
    </div>
  )
}

// ── Rules ──────────────────────────────────────────────────────────────────────
type RuleRow = { name: string; scope: string; order: number; does: string }
/** `cad rules`: every registered gate and what it checks. Project-independent (no slug). */
function RulesTask() {
  const [rows, setRows] = useState<RuleRow[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const run = async () => {
    setBusy(true); setErr(null)
    const r = await agentRun(['rules'])
    setBusy(false)
    if (r.exit !== 0) { setErr(resultText(r)); return }
    setRows(r.data?.rules ?? [])
  }
  useEffect(() => { run() }, [])
  return (
    <div className="tasks">
      <TaskButtons onOk={closeTask} />
      <div className="tbuttons"><button className="qbtn" disabled={busy} onClick={run}>Run again</button></div>
      <TaskBox title="Rules" icon="help">
        {busy && <p className="hint">Running cad rules…</p>}
        {err && <p className="hint err">{err}</p>}
        {!!rows?.length && <table className="ctable wrap">
          <thead><tr><th>Rule</th><th>Scope</th><th>Order</th><th>Verifies</th></tr></thead>
          <tbody>{rows.map((r) => <tr key={r.name}><td>{r.name}</td><td>{r.scope}</td><td>{r.order}</td><td>{r.does}</td></tr>)}</tbody>
        </table>}
        <p className="hint">every registered check and what it verifies</p>
      </TaskBox>
    </div>
  )
}

// ── Cut list ─────────────────────────────────────────────────────────────────
type CutRow = { kind: string; length_mm: number | null; qty: number; total_mm: number; cost_usd: number | null }
type CutlistData = { rows: CutRow[]; total_usd: number; note: string }
/** `cad cutlist`: stock to order and cut, derived from each part's own CUTLIST, roughly priced. */
function CutlistTask() {
  const slug = useStore((s) => s.slug)
  const [data, setData] = useState<CutlistData | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const run = async () => {
    if (!slug) return
    setBusy(true); setErr(null)
    const r = await agentRun(['cutlist', slug])
    setBusy(false)
    if (r.exit !== 0) { setErr(resultText(r)); return }
    setData(r.data as CutlistData)
  }
  useEffect(() => { run() }, [slug])
  return (
    <div className="tasks">
      <TaskButtons onOk={closeTask} />
      <div className="tbuttons"><button className="qbtn" disabled={busy || !slug} onClick={run}>Run again</button></div>
      <TaskBox title="Cut list" icon="document">
        {busy && <p className="hint">Running cad cutlist…</p>}
        {err && <p className="hint err">{err}</p>}
        {data && !data.rows.length && <p className="hint">No cuttable stock: no part declares a CUTLIST.</p>}
        {!!data?.rows.length && <table className="ctable">
          <thead><tr><th>Kind</th><th>Length (mm)</th><th>Qty</th><th>Total (mm)</th><th>Cost (USD)</th></tr></thead>
          <tbody>{data.rows.map((r, i) => <tr key={i}><td>{r.kind}</td><td>{r.length_mm ?? ''}</td><td>{r.qty}</td><td>{r.total_mm}</td><td>{r.cost_usd != null ? `$${r.cost_usd.toFixed(2)}` : ''}</td></tr>)}</tbody>
        </table>}
        {data && <p className="hint">Total: ${data.total_usd.toFixed(2)} · {data.note}</p>}
      </TaskBox>
    </div>
  )
}

// ── Tables ───────────────────────────────────────────────────────────────────
const TABLE_SECTIONS = ['all', 'holes', 'taps', 'inserts', 'extrusions', 'density', 'views'] as const
/** `cad tables`: hole sizes, tap drills, insert bores, extrusions and densities the harness
 *  assumes — the numbers `cad build` and the gates use. Project-independent (no slug). */
function TablesTask() {
  const [section, setSection] = useState<(typeof TABLE_SECTIONS)[number]>('all')
  const [data, setData] = useState<Record<string, unknown> | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let live = true
    setBusy(true); setErr(null)
    agentRun(section === 'all' ? ['tables'] : ['tables', section]).then((r) => {
      if (!live) return
      if (r.exit !== 0) { setErr(resultText(r)); setData(null) } else setData(r.data ?? {})
    }).finally(() => live && setBusy(false))
    return () => { live = false }
  }, [section])
  return (
    <div className="tasks">
      <TaskButtons onOk={closeTask} />
      <TaskBox title="Tables" icon="report">
        <label className="tfield"><span>Section</span>
          <QComboBox className="qselect-field" value={section} onChange={(e) => setSection(e.target.value as (typeof TABLE_SECTIONS)[number])}>
            {TABLE_SECTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
          </QComboBox></label>
        {busy && <p className="hint">Running cad tables…</p>}
        {err && <p className="hint err">{err}</p>}
        {!!data && <table className="ctable wrap"><tbody>
          {flattenRows(data).map(([k, v]) => <tr key={k}><td>{k}</td><td>{v}</td></tr>)}
        </tbody></table>}
      </TaskBox>
    </div>
  )
}

// ── Tool envelope ──────────────────────────────────────────────────────────────
const TOOL_TYPES = ['drill', 'end_mill', 'collet_nose', 'laser_cone', 'needle'] as const
type ToolType = (typeof TOOL_TYPES)[number]
/** tooling.py's own parameters per kind (cad_agent/tooling.py): the few dimensions that are
 *  either definitional or printed on the tool, nothing invented. */
const TOOL_PARAMS: Record<ToolType, { k: string; opt?: boolean }[]> = {
  drill: [{ k: 'diameter' }, { k: 'flute' }, { k: 'shank', opt: true }, { k: 'shank_dia', opt: true }],
  end_mill: [{ k: 'diameter' }, { k: 'flute' }, { k: 'shank' }, { k: 'shank_dia', opt: true }],
  collet_nose: [{ k: 'diameter' }, { k: 'length' }, { k: 'standoff', opt: true }],
  laser_cone: [{ k: 'focal_length' }, { k: 'field' }, { k: 'lens_dia' }, { k: 'offset', opt: true }],
  needle: [{ k: 'tip_dia' }, { k: 'tip_length' }, { k: 'barrel_dia' }, { k: 'barrel_length' }, { k: 'taper', opt: true }],
}
/** `cad tool`: a generated tool envelope, measured — not a catalogue part, the space a drill, end
 *  mill, collet nose, laser cone or dispense needle needs left free. Project-independent. */
function ToolTask() {
  const [type, setType] = useState<ToolType>('drill')
  const [vals, setVals] = useState<Record<string, string>>({})
  const [data, setData] = useState<Record<string, any> | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const fields = TOOL_PARAMS[type]
  const bad = fields.some((f) => !f.opt && !vals[f.k]?.trim())
  const pick = (type: ToolType) => { setType(type); setVals({}); setData(null); setErr(null) }
  const run = async () => {
    setBusy(true); setErr(null); setData(null)
    const kv = fields.filter((f) => vals[f.k]?.trim()).map((f) => `${f.k}=${vals[f.k].trim()}`)
    const r = await agentRun(['tool', type, ...kv])
    setBusy(false)
    if (r.exit !== 0) { setErr(resultText(r)); return }
    setData(r.data ?? {})
  }
  return (
    <div className="tasks">
      <TaskButtons onOk={closeTask} />
      <div className="tbuttons"><button className="qbtn default" disabled={busy || bad} onClick={run}>Generate</button></div>
      <TaskBox title="Tool envelope" icon="body">
        <div className="tform">
          <label className="tfield"><span>Tool</span>
            <QComboBox className="qselect-field" value={type} onChange={(e) => pick(e.target.value as ToolType)}>
              {TOOL_TYPES.map((t) => <option key={t} value={t}>{t.replace('_', ' ')}</option>)}
            </QComboBox></label>
          {fields.map((f) => <label key={f.k} className="tfield"><span>{f.k}{f.opt ? ' (optional)' : ''}</span>
            <input value={vals[f.k] ?? ''} className={cls(!f.opt && !vals[f.k]?.trim() && 'bad')}
              onChange={(e) => setVals({ ...vals, [f.k]: e.target.value })} /><span className="unit">mm</span></label>)}
        </div>
        {busy && <p className="hint">Running cad tool…</p>}
        {err && <p className="hint err">{err}</p>}
        {!!data && <table className="ctable wrap"><tbody>
          {flattenRows({ bbox_mm: data.bbox_mm, z_mm: data.z_mm, corner_tilt_deg: data.corner_tilt_deg }).map(([k, v]) => <tr key={k}><td>{k}</td><td>{v}</td></tr>)}
        </tbody></table>}
        <p className="hint">generate a tool envelope and measure it</p>
      </TaskBox>
    </div>
  )
}

// ── Bought parts ───────────────────────────────────────────────────────────────
type BoughtRow = { name: string; kind: string; file: string; source: string; vendor: string | null; verified: boolean }
type BoughtInfo = { name: string; kind: string | null; source: string | null; vendor: string | null; verified: boolean; bbox_mm: number[]; origin_mm: number[]; volume_cm3: number }
/** `cad bought`: vendor STEP or measured-envelope parts, always with a source (cad_agent's
 *  provenance rule — an unsourced part fails the provenance gate). List mirrors `bought ls` /
 *  `info`; Add is the add-step/add-measured flow, also what File > Import opens (vendor STEP
 *  path + source URL is the common case there). */
function BoughtTask({ initial }: { initial: 'list' | 'add' }) {
  const slug = useStore((s) => s.slug)
  const [tab, setTab] = useState(initial)
  const [rows, setRows] = useState<BoughtRow[] | null>(null)
  const [info, setInfo] = useState<BoughtInfo | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const goTab = (t: 'list' | 'add') => { setTab(t); setErr(null) }
  const loadList = async () => {
    if (!slug) return
    setBusy(true); setErr(null); setInfo(null)
    const r = await agentRun(['bought', 'ls', slug])
    setBusy(false)
    if (r.exit !== 0) { setErr(resultText(r)); return }
    setRows(r.data?.bought ?? [])
  }
  useEffect(() => { if (tab === 'list') loadList() }, [slug, tab])
  const showInfo = async (name: string) => {
    if (!slug) return
    setErr(null)
    const r = await agentRun(['bought', 'info', slug, name])
    if (r.exit !== 0) { setErr(resultText(r)); return }
    setInfo(r.data as BoughtInfo)
  }
  // Verify: a calliper measurement of a part that came as a datasheet envelope (`cad bought verify --note`).
  const [verifying, setVerifying] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const verify = async (name: string) => {
    if (!slug || !note.trim()) return
    setBusy(true); setErr(null)
    const r = await agentRun(['bought', 'verify', slug, name, '--note', note.trim()])
    setBusy(false)
    if (r.exit !== 0) { setErr(resultText(r)); return }
    setVerifying(null); setNote('')
    loadList()
  }
  // Add tab: a vendor STEP file (the File > Import flow), or a quick datasheet envelope.
  const [mode, setMode] = useState<'step' | 'measured'>('step')
  const [f, setF] = useState({ name: '', path: '', source: '', vendor: '', l: '', w: '', h: '', holes: '', holeDia: '' })
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value })
  const stepOk = f.name.trim() && f.path.trim() && f.source.trim()
  const measuredOk = f.name.trim() && f.l.trim() && f.w.trim() && f.h.trim() && f.source.trim()
  // A file picked on this computer: a browser gives a page its bytes and never its path, so the server keeps a copy and says where.
  const pickStep = async (file: File | undefined) => {
    if (!file) return
    setBusy(true); setErr(null)
    try {
      const up = await api.upload(file)
      setF((o) => ({ ...o, path: up.path, name: o.name || up.name.replace(/\.(step|stp)$/i, '').replace(/[^A-Za-z0-9_]+/g, '_') }))
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)) }
    setBusy(false)
  }
  const add = async () => {
    if (!slug) return
    setBusy(true); setErr(null)
    // `--hole=X,Y` with an equals sign: X may be negative (add-measured's own help says so)
    const holes = f.holes.split('\n').map((l) => l.trim()).filter(Boolean).map((l) => `--hole=${l.replace(/\s+/g, ',').replace(/,+/g, ',')}`)
    const argv = mode === 'step'
      ? ['bought', 'add-step', slug, f.name.trim(), f.path.trim(), '--source', f.source.trim(), ...(f.vendor.trim() ? ['--vendor', f.vendor.trim()] : [])]
      : ['bought', 'add-measured', slug, f.name.trim(), '--size', f.l.trim(), f.w.trim(), f.h.trim(), '--source', f.source.trim(), ...(f.vendor.trim() ? ['--vendor', f.vendor.trim()] : []),
        ...holes, ...(f.holeDia.trim() ? ['--hole-dia', f.holeDia.trim()] : [])]
    const r = await agentRun(argv)
    setBusy(false)
    if (r.exit !== 0) { setErr(resultText(r)); return }
    setF({ name: '', path: '', source: '', vendor: '', l: '', w: '', h: '', holes: '', holeDia: '' })
    goTab('list')
  }
  return (
    <div className="tasks">
      <TaskButtons onOk={closeTask} />
      <div className="tbuttons">
        <button className={cls('qbtn', tab === 'list' && 'on')} onClick={() => goTab('list')}>List</button>
        <button className={cls('qbtn', tab === 'add' && 'on')} onClick={() => goTab('add')}>Add…</button>
      </div>
      {tab === 'list' ? (
        <TaskBox title="Bought parts" icon="bought">
          {busy && <p className="hint">Running cad bought ls…</p>}
          {err && <p className="hint err">{err}</p>}
          {rows && !rows.length && <p className="hint">No bought parts yet. Use Add… or File &gt; Import…</p>}
          {!!rows?.length && <table className="ctable wrap">
            <thead><tr><th>Name</th><th>Kind</th><th>Vendor</th><th>Source</th><th>Verified</th><th /></tr></thead>
            <tbody>{rows.map((b) => <tr key={b.name}>
              <td>{b.name}</td><td>{b.kind}</td><td>{b.vendor ?? ''}</td><td>{b.source}</td>
              <td>{b.verified ? 'yes' : <button className="qbtn" title="record a calliper measurement" onClick={() => { setVerifying(b.name); setNote('') }}>Verify…</button>}</td>
              <td><button className="qbtn" onClick={() => showInfo(b.name)}>Info</button></td>
            </tr>)}</tbody>
          </table>}
          {verifying && <div className="tform">
            <p className="hint">Verify {verifying}: what was measured, and how (cad bought verify --note).</p>
            <textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. 30.1 x 20.0 x 19.9 mm with a 0.01 mm calliper, three readings each" />
            <div className="tbuttons"><button className="qbtn default" disabled={busy || !note.trim()} onClick={() => verify(verifying)}>Mark verified</button>
              <button className="qbtn" onClick={() => setVerifying(null)}>Cancel</button></div>
          </div>}
          {info && <table className="ctable wrap"><tbody>
            <tr><td>Envelope</td><td>{vec(info.bbox_mm)} mm</td></tr>
            <tr><td>Origin</td><td>{vec(info.origin_mm)} mm</td></tr>
            <tr><td>Volume</td><td>{info.volume_cm3} cm³</td></tr>
          </tbody></table>}
        </TaskBox>
      ) : (
        <TaskBox title="Add a bought part" icon="bought">
          <label className="tcheck"><input type="radio" checked={mode === 'step'} onChange={() => setMode('step')} /> Vendor STEP file</label>
          <label className="tcheck"><input type="radio" checked={mode === 'measured'} onChange={() => setMode('measured')} /> Measured envelope (UNVERIFIED until measured)</label>
          <div className="tform">
            <label className="tfield"><span>Name</span><input value={f.name} onChange={set('name')} /></label>
            {mode === 'step'
              ? <>
                  <label className="tfield"><span>STEP file</span><input type="file" accept=".step,.stp,.STEP,.STP" onChange={(e) => pickStep(e.target.files?.[0])} /></label>
                  <label className="tfield"><span>or its path</span><input value={f.path} onChange={set('path')} placeholder="/path/to/part.step" /></label>
                </>
              : <>
                  <label className="tfield"><span>Length</span><input value={f.l} onChange={set('l')} /><span className="unit">mm</span></label>
                  <label className="tfield"><span>Width</span><input value={f.w} onChange={set('w')} /><span className="unit">mm</span></label>
                  <label className="tfield"><span>Height</span><input value={f.h} onChange={set('h')} /><span className="unit">mm</span></label>
                  <label className="tfield top"><span>Bolt holes</span>
                    <textarea rows={2} value={f.holes} onChange={(e) => setF({ ...f, holes: e.target.value })} placeholder={'X,Y in mm, one hole a line, e.g.\n-15.5,-15.5'} /></label>
                  <label className="tfield"><span>Hole diameter</span><input value={f.holeDia} onChange={set('holeDia')} placeholder="3.2" /><span className="unit">mm</span></label>
                </>}
            <label className="tfield"><span>Source URL</span><input value={f.source} onChange={set('source')} placeholder="the page it came from" /></label>
            <label className="tfield"><span>Vendor (optional)</span><input value={f.vendor} onChange={set('vendor')} /></label>
          </div>
          {err && <p className="hint err">{err}</p>}
          <div className="tbuttons"><button className="qbtn default" disabled={busy || !(mode === 'step' ? stepOk : measuredOk)} onClick={add}>Add</button></div>
          <p className="hint">Every bought part needs a source: the datasheet, drawing or vendor page the numbers came from.</p>
        </TaskBox>
      )}
    </div>
  )
}

// ── Render ───────────────────────────────────────────────────────────────────
const RENDER_VIEWS = ['iso', 'iso2', 'top', 'bottom', 'front', 'back', 'left', 'right'] as const
type RenderData = { png: string; subject: string; view: string }
/** `cad render`: a part, or the whole assembly, to a PNG — the same renderer the visual gate and
 *  `cad page` use. Shown inline, the way a FreeCAD preview dialog would. */
function RenderTask() {
  const slug = useStore((s) => s.slug), scene = useStore((s) => s.scene)
  const parts = [...new Set((scene?.bodies ?? []).map((b) => b.part).filter((p): p is string => !!p))]
  const [part, setPart] = useState('')
  const [view, setView] = useState<(typeof RENDER_VIEWS)[number]>('iso')
  const [tol, setTol] = useState('')
  const [sets, setSets] = useState('')
  const [data, setData] = useState<RenderData | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const run = async () => {
    if (!slug) return
    setBusy(true); setErr(null); setData(null)
    const argv = ['render', slug, ...(part ? [part] : []), '--view', view, ...(tol.trim() ? ['--tolerance', tol.trim()] : []), ...overrideArgs(sets)]
    const r = await agentRun(argv)
    setBusy(false)
    if (r.exit !== 0) { setErr(resultText(r)); return }
    setData(r.data as RenderData)
  }
  return (
    <div className="tasks">
      <TaskButtons onOk={closeTask} />
      <div className="tbuttons"><button className="qbtn default" disabled={busy || !slug} onClick={run}>Render</button></div>
      <TaskBox title="Render" icon="shot">
        <div className="tform">
          <label className="tfield"><span>Part</span>
            <QComboBox className="qselect-field" value={part} onChange={(e) => setPart(e.target.value)}>
              <option value="">(whole assembly)</option>
              {parts.map((p) => <option key={p} value={p}>{p}</option>)}
            </QComboBox></label>
          <label className="tfield"><span>View</span>
            <QComboBox className="qselect-field" value={view} onChange={(e) => setView(e.target.value as (typeof RENDER_VIEWS)[number])}>
              {RENDER_VIEWS.map((v) => <option key={v} value={v}>{v}</option>)}
            </QComboBox></label>
          <label className="tfield"><span>Tolerance (optional)</span><input value={tol} onChange={(e) => setTol(e.target.value)} placeholder="mm" /></label>
          {part && <label className="tfield" title="render --set: try values for this run; nothing is written"><span>Try values</span>
            <input value={sets} onChange={(e) => setSets(e.target.value)} placeholder="width=50 thickness=6" /></label>}
        </div>
        {busy && <p className="hint">Running cad render…</p>}
        {err && <p className="hint err">{err}</p>}
        {data && slug && <>
          <img className="agent-render-img" src={api.fileUrl(slug, data.png)} alt={data.subject} />
          <p className="hint">{data.subject} · {data.view}</p>
        </>}
      </TaskBox>
    </div>
  )
}

// ── Build part ───────────────────────────────────────────────────────────────
type BuildData = { part: string; bbox_mm: number[]; volume_cm3: number; mass_g: number | null; material: string | null; process: string | null
  build_s: number; params: Record<string, unknown>; overrides: Record<string, unknown>; doc: string }
/** `cad build`: one part module built and measured, with its size, volume, mass, material, process and build time. "Try values"
 *  builds it with other parameters for this run only (`--set`): nothing is written, which is what the Parameters panel (`cad set`)
 *  does not do. */
export function BuildTask({ part: want }: { part?: string }) {
  const slug = useStore((s) => s.slug), scene = useStore((s) => s.scene)
  const parts = [...new Set((scene?.bodies ?? []).map((b) => b.part).filter((p): p is string => !!p))]
  const [part, setPart] = useState(want && parts.includes(want) ? want : parts[0] ?? '')
  const [sets, setSets] = useState('')
  const [data, setData] = useState<BuildData | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const run = async () => {
    if (!slug || !part) return
    setBusy(true); setErr(null)
    const r = await agentRun(['build', slug, part, ...overrideArgs(sets)])
    setBusy(false)
    if (r.exit !== 0) { setErr(resultText(r)); setData(null); return }
    setData(r.data as BuildData)
  }
  useEffect(() => { if (!part && parts[0]) setPart(parts[0]) }, [parts.join(',')])
  useEffect(() => { if (part) run() }, [slug, part])
  return (
    <div className="tasks">
      <TaskButtons onOk={closeTask} />
      <div className="tbuttons"><button className="qbtn default" disabled={busy || !slug || !part} onClick={run}>Build</button></div>
      <TaskBox title="Build part" icon="body">
        <div className="tform">
          <label className="tfield"><span>Part</span>
            <QComboBox className="qselect-field" value={part} onChange={(e) => setPart(e.target.value)}>
              {!parts.length && <option value="">(no parts)</option>}{parts.map((p) => <option key={p} value={p}>{p}</option>)}
            </QComboBox></label>
          <label className="tfield" title="build --set: other values for this run only; nothing is written"><span>Try values</span>
            <input value={sets} onChange={(e) => setSets(e.target.value)} placeholder="width=50 thickness=6" /></label>
        </div>
        {busy && <p className="hint">Running cad build…</p>}
        {err && <p className="hint err">{err}</p>}
        {data && <>
          <table className="ctable wrap kv"><tbody>
            <tr><td>Size</td><td>{data.bbox_mm.join(' x ')} mm</td></tr>
            <tr><td>Volume</td><td>{data.volume_cm3} cm³</td></tr>
            <tr><td>Mass</td><td>{data.mass_g != null ? `${data.mass_g} g${data.material ? ` of ${data.material}` : ''}` : 'unknown'}</td></tr>
            <tr><td>Process</td><td>{data.process ?? 'none declared'}</td></tr>
            <tr><td>Built in</td><td>{data.build_s} s</td></tr>
            {data.doc && <tr><td>About</td><td>{data.doc}</td></tr>}
          </tbody></table>
          {!!Object.keys(data.params ?? {}).length && <table className="ctable wrap"><thead><tr><th>Parameter</th><th>Value</th></tr></thead>
            <tbody>{Object.entries(data.params).map(([k, v]) => <tr key={k} className={k in (data.overrides ?? {}) ? 'sel' : undefined}>
              <td>{k}</td><td>{String(v)}{k in (data.overrides ?? {}) ? ' (tried)' : ''}</td></tr>)}</tbody></table>}
        </>}
        <p className="hint">build one part and measure it</p>
      </TaskBox>
    </div>
  )
}

// ── Evals ────────────────────────────────────────────────────────────────────
type EvalTask = { task: string; title: string; given: string[]; reference: boolean }
type EvalScore = { task: string; verdict: string; score: number; graded: number; passed: number; skipped: number; na: number; rows: CheckRow[]; notes: string[]; seconds: number }
/** `cad eval ls|brief|score`: the eval set, design tasks each with a brief and a hidden spec, scored by the verifier. Read a
 *  brief, then score the open project against it: it is judged as a copy, the project is not touched. `cad eval run` starts a
 *  real agent on a task and spends the plan's usage, so it stays a command typed in a terminal. */
export function EvalsTask() {
  const slug = useStore((s) => s.slug), projects = useStore((s) => s.projects)
  const [tasks, setTasks] = useState<EvalTask[] | null>(null)
  const [pick, setPick] = useState<string | null>(null)
  const [brief, setBrief] = useState<string | null>(null)
  const [all, setAll] = useState(false)
  const [res, setRes] = useState<{ r: CadResult; d: EvalScore } | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const root = projects.find((p) => p.slug === slug)?.root
  useEffect(() => {
    agentRun(['eval', 'ls']).then((r) => { if (r.exit !== 0) setErr(resultText(r)); else setTasks((r.data?.tasks ?? []) as EvalTask[]) })
  }, [])
  useEffect(() => {
    setBrief(null); setRes(null)
    if (!pick) return
    let live = true
    agentRun(['eval', 'brief', pick]).then((r) => { if (live) { if (r.exit !== 0) setErr(resultText(r)); else setBrief(String(r.data?.brief ?? '')) } })
    return () => { live = false }
  }, [pick])
  const score = async () => {
    if (!pick || !slug || !root) return
    setBusy(true); setErr(null); setRes(null)
    const r = await agentRun(['eval', 'score', pick, `${root}/${slug}`, ...(all ? ['--all'] : [])])
    setBusy(false)
    if (r.exit > 2) { setErr(resultText(r)); return }
    setRes({ r, d: r.data as EvalScore })
  }
  const verdict = res?.d.verdict ?? ''
  return (
    <div className="tasks">
      <TaskButtons onOk={closeTask} />
      <TaskBox title="Evals" icon="report">
        {err && <p className="hint err">{err}</p>}
        {tasks && !tasks.length && <p className="hint">No eval tasks here.</p>}
        {!!tasks?.length && <table className="ctable wrap">
          <thead><tr><th>Task</th><th>Brief</th></tr></thead>
          <tbody>{tasks.map((t) => <tr key={t.task} className={cls(pick === t.task && 'sel')} onClick={() => setPick(t.task)} title={`${t.given.length} given files`}>
            <td>{t.task}</td><td>{t.title.replace(/^[^:]*:\s*/, '')}</td></tr>)}</tbody>
        </table>}
        <p className="hint">the eval set: design tasks scored by the verifier, so a change to cad-agent is a number. <code>cad eval run</code> starts a real agent and spends your plan's usage: run it in a terminal.</p>
      </TaskBox>
      {brief !== null && <TaskBox title={`Brief: ${pick}`} icon="document">
        <pre className="hint pre">{brief}</pre>
      </TaskBox>}
      {pick && <TaskBox title="Score" icon="pass">
        <label className="tcheck"><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> Show passing rows too</label>
        <div className="tbuttons"><button className="qbtn default" disabled={busy || !slug || !root} onClick={score}
          title={slug ? `cad eval score ${pick} ${root}/${slug}` : 'open a project first'}>Score {slug ?? 'a project'} against {pick}</button></div>
        {busy && <p className="hint">Running cad eval score…</p>}
        {res && <>
          <p><span className={cls('verdict', verdict.toLowerCase())}>{verdict}</span> {(res.d.score * 100).toFixed(1)}%, {res.d.passed} of {res.d.graded} rows pass
            {res.d.skipped || res.d.na ? ` · ${res.d.skipped} render and ${res.d.na} n/a rows not counted` : ''} · {res.d.seconds} s</p>
          {!!res.d.rows?.length && <RowsTable rows={res.d.rows} />}
          {!!res.d.notes?.length && <ul className="hint">{res.d.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>}
        </>}
      </TaskBox>}
    </div>
  )
}

// ── Approve renders, and the Review page export: these act directly, no task panel ───────────
/** Approve renders: the person's call (cad approve's own help text says so), so this always
 *  shows what would be promoted — from the last Check's visual rows — before running it. A
 *  QMessageBox question, default No (Yes/No order puts No first: msgbox.tsx focuses and
 *  Enter-activates the first button, which is how a Qt default button works). */
export async function approveRenders() {
  const s = getState()
  if (!s.slug) return
  const visual = (s.checks?.rows ?? []).filter((r) => r.check === 'visual')
  const listing = visual.length
    ? visual.map((r) => `${r.subject} (${r.rule}): ${r.measured ?? r.state}`).join('\n')
    : 'No visual checks in the last run — run Check first to see what would change.'
  const btn = await messageBox('question', 'Approve Renders', `Promote the current renders to approved baselines?\n\n${listing}`, ['No', 'Yes'])
  if (btn !== 'Yes') return
  const r = await agentRun(['approve', s.slug])
  if (r.exit <= 2) { loadChecks(); loadStatus() }
}

/** File > Export > Review page: `cad page`, this UI's equivalent of FreeCAD's WebGL HTML
 *  export — writes the shareable review page (model, gates, parts, renders), then opens it. */
export async function exportPage() {
  const s = getState()
  if (!s.slug) return report('warn', 'Export: open a project first')
  const r = await agentRun(['page', s.slug])
  if (r.exit === 0 && r.data?.index) window.open(api.fileUrl(s.slug, r.data.index), '_blank')
}

export { GateTask, RulesTask, CutlistTask, TablesTask, ToolTask, BoughtTask, RenderTask }
// BuildTask is exported where it is declared.

// The part library in the workbench: `cad lib ls|info|use|check|add`, the commands an agent runs, as one task panel with
// three pages, Browse (the catalog, one entry's facts, and copying it into the open project), Check (the store's files and
// the project's bought parts against the catalog's hashes) and Add (a vendor STEP the person downloaded and picks).
//
// What is not here is `cad lib fetch`: it downloads a file. Fetch… puts the command on the Console's line and leaves
// the Return to the person, who sees the entry's licence and where the file comes from (the Library page shows both) first.
//
// FreeCAD has the same idea twice: the Parts Library addon (a catalog of files to insert) and Assembly_InsertLink (Insert
// Component), whose icon this uses. Copying a part in is journaled by the CLI, so Edit > Undo takes it back.
import { useEffect, useMemo, useState } from 'react'
import { api, resultText, type CadResult, type CheckRow } from './api'
import { closeTask, showPanel } from './actions'
import { setState, useStore } from './store'
import { cls, TaskBox, TaskButtons } from './panels'
import { QComboBox } from './combo'
import { agentRun, flattenRows, RowsTable } from './agentwb'

type Entry = { name: string; kind: 'generator' | 'step' | 'bd_warehouse'; title: string; vendor: string | null; pn: string | null; licence: string
  geometry: string; verified: boolean; origin: string; status: string; problems: string[] }
type Param = { default: number | string | boolean | null; min: number | null; max: number | null; choices: (string | number)[] | null; unit: string | null; source: string | null }
type Info = {
  entry: { name: string; origin: string; kind: string; title: string; licence: string; geometry: string; verified: boolean; source: string; docs: string[]
    vendor: string | null; pn: string | null; attribution: string | null; material: string | null; max_temp_c: number | null; max_temp_source: string | null
    mass: Record<string, unknown> | null; datum: { move: number[]; turn: number[] } | null; url: string | null; sha256: string | null; size: number | null
    dims: Record<string, { value: unknown; source: string }>; model: Record<string, unknown>; params: Record<string, Param>; unconfirmed: string[]; notes: string[]; problems: string[] }
  status: string; fetch: { allowed: boolean; why_not: string }; store: string; in_store?: boolean
}
type Page = 'browse' | 'check' | 'add'

/** What a parameter may be, in words (library/cli.py's _span). */
const span = (p: Param) => p.choices ? `one of ${p.choices.join(', ')}` : p.min != null && p.max != null ? `${p.min} to ${p.max}`
  : p.min != null ? `at least ${p.min}` : p.max != null ? `at most ${p.max}` : 'any number'
/** An entry the project can have now: drawn by the library, or a file already in the store. */
const usable = (status: string) => status === 'ready' || status === 'in your store'

/** The catalog's entries, `cad lib ls` once and filtered here as the person types. Needs no project. */
function useCatalog() {
  const [entries, setEntries] = useState<Entry[] | null>(null)
  const [store, setStore] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const load = async () => {
    setBusy(true); setErr(null)
    const r = await agentRun(['lib', 'ls'])
    setBusy(false)
    if (r.exit !== 0) { setErr(resultText(r)); return }
    setEntries((r.data?.entries ?? []) as Entry[]); setStore(String(r.data?.store ?? ''))
  }
  useEffect(() => { load() }, [])
  return { entries, store, err, busy, load }
}

export function LibraryTask() {
  const slug = useStore((s) => s.slug)
  const [page, setPage] = useState<Page>('browse')
  const cat = useCatalog()
  const [pick, setPick] = useState<string | null>(null)
  const [addFor, setAddFor] = useState('')
  const goAdd = (entry: string) => { setAddFor(entry); setPage('add') }
  return (
    <div className="tasks">
      <TaskButtons onOk={closeTask} />
      <div className="tbuttons">
        <button className={cls('qbtn', page === 'browse' && 'on')} onClick={() => setPage('browse')}>Browse</button>
        <button className={cls('qbtn', page === 'check' && 'on')} onClick={() => setPage('check')}>Check</button>
        <button className={cls('qbtn', page === 'add' && 'on')} onClick={() => setPage('add')}>Add…</button>
      </div>
      {page === 'browse' && <Browse cat={cat} slug={slug} pick={pick} setPick={setPick} goAdd={goAdd} />}
      {page === 'check' && <CheckPage slug={slug} />}
      {page === 'add' && <AddPage cat={cat} initial={addFor} onAdded={(name) => { cat.load(); setPick(name); setPage('browse') }} />}
    </div>
  )
}

// ── Browse: ls, info, use ────────────────────────────────────────────────────────────────────────────────
function Browse({ cat, slug, pick, setPick, goAdd }: { cat: ReturnType<typeof useCatalog>; slug: string | null; pick: string | null
  setPick(n: string | null): void; goAdd(entry: string): void }) {
  const [query, setQuery] = useState('')
  const [kind, setKind] = useState('')
  const [info, setInfo] = useState<Info | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const shown = useMemo(() => {
    const word = query.trim().toLowerCase()
    return (cat.entries ?? []).filter((e) => (!kind || e.kind === kind)
      && (!word || [e.name, e.title, e.vendor, e.pn].filter(Boolean).join(' ').toLowerCase().includes(word)))
  }, [cat.entries, query, kind])
  useEffect(() => {
    setInfo(null); setErr(null)
    if (!pick) return
    let live = true
    agentRun(['lib', 'info', pick]).then((r) => {
      if (!live) return
      if (r.exit !== 0) setErr(resultText(r)); else setInfo(r.data as Info)
    })
    return () => { live = false }
  }, [pick])
  return (
    <>
      <TaskBox title="Library" icon="library">
        <div className="tform">
          <label className="tfield"><span>Search</span><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="name, vendor or part number" /></label>
          <label className="tfield"><span>Kind</span>
            <QComboBox className="qselect-field" value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="">all</option><option value="generator">generators (drawn here)</option><option value="step">STEP files</option><option value="bd_warehouse">bd_warehouse parts</option>
            </QComboBox></label>
        </div>
        {cat.busy && <p className="hint">Running cad lib ls…</p>}
        {cat.err && <p className="hint err">{cat.err}</p>}
        {cat.entries && !shown.length && <p className="hint">Nothing matches.</p>}
        {!!shown.length && <table className="ctable wrap">
          <thead><tr><th>Name</th><th>Vendor / part number</th><th>Status</th></tr></thead>
          <tbody>{shown.map((e) => (
            <tr key={e.name} className={cls(pick === e.name && 'sel', !usable(e.status) && 'dim')} onClick={() => setPick(e.name)} title={e.title}>
              <td>{e.name}<div className="sub">{e.kind} · {e.licence}</div></td><td>{[e.vendor, e.pn].filter(Boolean).join(' ') || '-'}</td><td>{e.status}</td>
            </tr>))}</tbody>
        </table>}
        {cat.store && <p className="hint">Your store: {cat.store}. The catalog holds {cat.entries?.length ?? 0} entries.</p>}
      </TaskBox>
      {err && <p className="hint err">{err}</p>}
      {info && <Detail info={info} slug={slug} goAdd={goAdd} onUsed={cat.load} />}
    </>
  )
}

function Detail({ info, slug, goAdd, onUsed }: { info: Info; slug: string | null; goAdd(entry: string): void; onUsed(): void }) {
  const e = info.entry
  const [vals, setVals] = useState<Record<string, string>>({})
  const [asName, setAsName] = useState('')
  const [replace, setReplace] = useState(false)
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState<CadResult | null>(null)
  useEffect(() => { setVals({}); setAsName(''); setReplace(false); setRes(null) }, [e.name])
  const params = Object.entries(e.params)
  const facts: [string, string][] = ([
    ['Title', e.title], ['Vendor', e.vendor ?? ''], ['Part number', e.pn ?? ''], ['Licence', e.licence],
    ['Geometry', `${e.geometry}, ${e.verified ? 'verified' : `UNCONFIRMED${e.unconfirmed.length ? ` (${e.unconfirmed.join(', ')})` : ''}`}`],
    ['Source', e.source], ['Read', e.docs.join('\n')], ['Credit', e.attribution ?? ''],
    ['Mass', e.mass ? flattenRows(e.mass).map(([k, v]) => `${k} ${v}`).join('; ') : 'none declared (no source gives one)'],
    ['Rating', e.max_temp_c != null ? `${e.max_temp_c} C: ${e.max_temp_source ?? ''}` : 'no max_temp_c declared'],
    ['Datum', e.datum ? `move ${e.datum.move.join(', ')}, turn ${e.datum.turn.join(', ')}` : ''],
    ['In your store', e.kind === 'step' ? (info.in_store ? 'yes' : 'no') : ''], ['Pinned sha256', e.sha256 ?? ''],
    ['Notes', e.notes.join('\n')], ['Faults', e.problems.join('\n')],
  ] as [string, string][]).filter(([, v]) => v)
  const use = async () => {
    if (!slug) return
    setBusy(true); setRes(null)
    const kv = params.filter(([k]) => vals[k]?.trim()).map(([k]) => `${k}=${vals[k].trim()}`)
    const r = await agentRun(['lib', 'use', slug, e.name, ...kv, ...(asName.trim() ? ['--as', asName.trim()] : []), ...(replace ? ['--replace'] : [])])
    setBusy(false); setRes(r)
    if (r.exit === 0) onUsed()
  }
  // `lib fetch` downloads a file: the command goes on the Console's line, and the Return is the person's.
  const fetchLine = () => { setState({ consoleDraft: `cad lib fetch ${e.name}` }); showPanel('console') }
  return (
    <TaskBox title={e.name} icon="library">
      <table className="ctable wrap kv"><tbody>{facts.map(([k, v]) => <tr key={k}><td>{k}</td><td style={{ whiteSpace: 'pre-line' }}>{v}</td></tr>)}</tbody></table>
      {Object.keys(e.dims).length > 0 && <details><summary>Dimensions, each with where it came from</summary>
        <table className="ctable wrap"><tbody>{Object.entries(e.dims).map(([k, d]) => <tr key={k} title={d.source}><td>{k}</td><td>{String(d.value)}</td><td>{d.source}</td></tr>)}</tbody></table></details>}
      {!usable(info.status) && <p className="hint">{info.status === 'fetch it' ? 'The file is not in your store. ' : info.status.startsWith('add') ? 'The licence does not allow a download here. ' : `${info.status}. `}
        {info.fetch.allowed ? <>Download it with <code>cad lib fetch {e.name}</code> (the licence allows it; the file is checked against the catalog's hash).</>
          : info.fetch.why_not}</p>}
      {!usable(info.status) && info.fetch.allowed && <div className="tbuttons"><button className="qbtn" onClick={fetchLine}
        title="Puts the command on the Console's line; you press Return">Fetch…</button></div>}
      {e.kind === 'step' && !info.in_store && <div className="tbuttons"><button className="qbtn" onClick={() => goAdd(e.name)}>Add the file by hand…</button></div>}
      {usable(info.status) && <>
        {!!params.length && <div className="tform">
          {params.map(([k, p]) => (
            <label key={k} className="tfield" title={p.source ?? undefined}><span>{k}</span>
              {p.choices
                ? <QComboBox className="qselect-field" value={vals[k] ?? String(p.default ?? '')} onChange={(ev) => setVals({ ...vals, [k]: ev.target.value })}>
                  {p.choices.map((c) => <option key={String(c)} value={String(c)}>{String(c)}</option>)}</QComboBox>
                : <input value={vals[k] ?? ''} placeholder={String(p.default ?? '')} onChange={(ev) => setVals({ ...vals, [k]: ev.target.value })} />}
              <span className="unit">{p.unit ?? ''}</span></label>))}
          <p className="hint">{params.map(([k, p]) => `${k}: ${span(p)}${p.unit ? ` ${p.unit}` : ''}`).join(' · ')}</p>
        </div>}
        <div className="tform">
          <label className="tfield"><span>Name in bought/</span><input value={asName} onChange={(ev) => setAsName(ev.target.value)} placeholder={e.name.replace(/-/g, '_')} /></label>
          <label className="tcheck" title="write a part the library copied in before again"><input type="checkbox" checked={replace} onChange={(ev) => setReplace(ev.target.checked)} /> Replace one copied in before</label>
        </div>
        <div className="tbuttons"><button className="qbtn default" disabled={busy || !slug} onClick={use}
          title={slug ? `cad lib use ${slug} ${e.name}` : 'open a project first'}>Use in {slug ?? 'a project'}</button></div>
        {busy && <p className="hint">Running cad lib use…</p>}
        {res && res.exit > 0 && <p className="hint err">{resultText(res)}</p>}
        {res && res.exit === 0 && <pre className="hint pre">{res.text}</pre>}
      </>}
    </TaskBox>
  )
}

// ── Check: lib check ─────────────────────────────────────────────────────────────────────────────────
function CheckPage({ slug }: { slug: string | null }) {
  const [all, setAll] = useState(false)
  const [res, setRes] = useState<{ what: string; r: CadResult } | null>(null)
  const [busy, setBusy] = useState(false)
  const run = async (project: boolean) => {
    setBusy(true); setRes(null)
    const r = await agentRun(['lib', 'check', ...(project && slug ? [slug] : []), ...(all ? ['--all'] : [])])
    setBusy(false); setRes({ what: project ? `${slug}/bought/` : 'the store', r })
  }
  const rows = (res?.r.data?.rows ?? []) as CheckRow[]
  const sum = res?.r.data?.summary as Record<string, number> | undefined
  return (
    <TaskBox title="Check" icon="library">
      <div className="tbuttons">
        <button className="qbtn" disabled={busy} onClick={() => run(false)} title="cad lib check: the store's files against the catalog's hashes">Check the store</button>
        <button className="qbtn" disabled={busy || !slug} onClick={() => run(true)} title="cad lib check PROJECT: the project's bought parts against the library">Check {slug ?? 'a project'}'s bought parts</button>
      </div>
      <label className="tcheck"><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> Show passing rows too</label>
      {busy && <p className="hint">Running cad lib check…</p>}
      {res && res.r.exit > 2 && <p className="hint err">{resultText(res.r)}</p>}
      {res && res.r.exit <= 2 && <p className="hint">{res.what}: {sum ? Object.entries(sum).filter(([, n]) => n).map(([s, n]) => `${n} ${s}`).join(', ') : 'checked'}</p>}
      {!!rows.length && <RowsTable rows={rows} />}
      {res && res.r.exit <= 2 && !rows.length && <p className="hint">Every row passes.</p>}
      <p className="hint">check the store's files against the catalog's hashes, and a project's bought parts against the library</p>
    </TaskBox>
  )
}

// ── Add: lib add ─────────────────────────────────────────────────────────────────────────────────────
const NAME = /^[a-z0-9]+(-[a-z0-9]+)*$/
/** A vendor STEP the person downloaded, picked from their disk: the page sends the bytes to the server (a browser gives a
 *  page a file's bytes and not its path), and `cad lib add` takes the path of that copy. An entry the catalog names is
 *  checked against the hash it pins; any other name is a new entry of your own store, which needs a source and may say
 *  what the vendor says of it. */
function AddPage({ cat, initial, onAdded }: { cat: ReturnType<typeof useCatalog>; initial: string; onAdded(name: string): void }) {
  const known = (name: string) => cat.entries?.find((e) => e.name === name)
  const [f, setF] = useState({ entry: initial, source: '', title: '', vendor: '', pn: '', licence: '', attribution: '', material: '', massG: '', massSource: '',
    maxTemp: '', maxTempSource: '', geometry: '', datumMove: '', datumTurn: '' })
  const [unverified, setUnverified] = useState(false)
  const [replace, setReplace] = useState(false)
  const [file, setFile] = useState<{ path: string; name: string; bytes: number } | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value })
  const k = known(f.entry.trim())
  const fresh = !k                                    // a name the catalog does not know: a new entry, with what the person knows of it
  const needs = !NAME.test(f.entry.trim()) ? 'an entry is named in lower case words joined by hyphens'
    : !file ? 'pick the STEP file' : !f.source.trim() ? 'say which page the file came from'
    : (!!f.massG.trim() !== !!f.massSource.trim()) ? 'a mass and its source go together'
    : (!!f.maxTemp.trim() !== !!f.maxTempSource.trim()) ? 'a rating and its source go together' : ''
  const pickFile = async (file: File | undefined) => {
    if (!file) return
    setBusy(true); setErr(null); setFile(null)
    try { setFile(await api.upload(file)) } catch (e) { setErr(e instanceof Error ? e.message : String(e)) }
    setBusy(false)
  }
  const add = async () => {
    if (needs || !file) return
    setBusy(true); setErr(null); setDone(null)
    const opt = (flag: string, v: string) => (v.trim() ? [flag, v.trim()] : [])
    const argv = ['lib', 'add', f.entry.trim(), file.path, '--source', f.source.trim(), ...(replace ? ['--replace'] : []),
      ...(fresh ? [...opt('--title', f.title), ...opt('--vendor', f.vendor), ...opt('--pn', f.pn), ...opt('--licence', f.licence), ...opt('--attribution', f.attribution),
        ...opt('--material', f.material), ...opt('--mass-g', f.massG), ...opt('--mass-source', f.massSource), ...opt('--max-temp-c', f.maxTemp),
        ...opt('--max-temp-source', f.maxTempSource), ...opt('--geometry', f.geometry),
        ...(f.datumMove.trim() ? [`--datum-move=${f.datumMove.trim()}`] : []), ...(f.datumTurn.trim() ? [`--datum-turn=${f.datumTurn.trim()}`] : []),
        ...(unverified ? ['--unverified'] : [])] : [])]
    const r = await agentRun(argv)
    setBusy(false)
    if (r.exit !== 0) { setErr(resultText(r)); return }
    setDone(r.text ?? 'added')
    onAdded(f.entry.trim())
  }
  return (
    <TaskBox title="Add a file" icon="library">
      <div className="tform">
        <label className="tfield"><span>STEP file</span><input type="file" accept=".step,.stp,.STEP,.STP" onChange={(e) => pickFile(e.target.files?.[0])} /></label>
        {file && <p className="hint">{file.name}, {file.bytes.toLocaleString()} bytes</p>}
        <label className="tfield"><span>Entry</span><input list="lib-step-entries" value={f.entry} onChange={set('entry')} placeholder="a catalog entry, or a new name" /></label>
        <datalist id="lib-step-entries">{(cat.entries ?? []).filter((e) => e.kind === 'step').map((e) => <option key={e.name} value={e.name} />)}</datalist>
        <label className="tfield"><span>Source</span><input value={f.source} onChange={set('source')} placeholder="the page the file came from" /></label>
      </div>
      {k && <p className="hint">{k.name} is in the catalog ({k.title}): the file is checked against the hash it pins.</p>}
      {k && k.origin !== 'shipped' && <label className="tcheck"><input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} /> Pin this file for my entry instead of the one it pins</label>}
      {fresh && f.entry.trim() && <>
        <p className="hint">A new entry in your store. What you know of the part, from the vendor:</p>
        <div className="tform">
          <label className="tfield"><span>Title</span><input value={f.title} onChange={set('title')} /></label>
          <label className="tfield"><span>Vendor</span><input value={f.vendor} onChange={set('vendor')} /></label>
          <label className="tfield"><span>Part number</span><input value={f.pn} onChange={set('pn')} /></label>
          <label className="tfield"><span>Licence</span><input value={f.licence} onChange={set('licence')} placeholder="default unknown" /></label>
          <label className="tfield"><span>Credit</span><input value={f.attribution} onChange={set('attribution')} placeholder="what its licence asks for" /></label>
          <label className="tfield"><span>Material</span><input value={f.material} onChange={set('material')} placeholder="a key of cad tables materials" /></label>
          <label className="tfield"><span>Mass</span><input value={f.massG} onChange={set('massG')} /><span className="unit">g</span></label>
          <label className="tfield"><span>Mass source</span><input value={f.massSource} onChange={set('massSource')} /></label>
          <label className="tfield"><span>Max temperature</span><input value={f.maxTemp} onChange={set('maxTemp')} /><span className="unit">C</span></label>
          <label className="tfield"><span>Rating source</span><input value={f.maxTempSource} onChange={set('maxTempSource')} /></label>
          <label className="tfield"><span>Geometry</span>
            <QComboBox className="qselect-field" value={f.geometry} onChange={(e) => setF({ ...f, geometry: e.target.value })}>
              <option value="">envelope (default)</option><option value="exact">exact</option>
            </QComboBox></label>
          <label className="tfield"><span>Datum move</span><input value={f.datumMove} onChange={set('datumMove')} placeholder="X,Y,Z mm" /></label>
          <label className="tfield"><span>Datum turn</span><input value={f.datumTurn} onChange={set('datumTurn')} placeholder="RX,RY,RZ degrees" /></label>
        </div>
        <label className="tcheck"><input type="checkbox" checked={unverified} onChange={(e) => setUnverified(e.target.checked)} /> Its dimensions are not confirmed</label>
      </>}
      {err && <p className="hint err">{err}</p>}
      {needs && <p className="hint">{needs}</p>}
      {done && <pre className="hint pre">{done}</pre>}
      <div className="tbuttons"><button className="qbtn default" disabled={busy || !!needs} onClick={add}>Add</button></div>
      <p className="hint">put a vendor STEP you downloaded by hand in your own store, checked against the catalog</p>
    </TaskBox>
  )
}

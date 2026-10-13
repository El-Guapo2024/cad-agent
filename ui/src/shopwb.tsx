// The CAD Agent workbench's shop commands: `cad bom`, `cad shop` and `cad drawing`, each a task panel that runs the
// command the way an agent in a terminal does (POST /api/cad) and shows what it answers; the drawing also opens as
// a tab beside the 3D view, the way TechDraw opens a page as an MDI view. Nothing here builds a thing itself, and
// nothing approves anything: a drawing or a shop folder written for a design nobody verified says NOT VERIFIED
// in every file, which the CLI puts there.
//
// FreeCAD's counterparts, at 3160daf1e2b6:
//   Assembly_CreateBom (src/Mod/Assembly/CommandCreateBom.py)  the BOM: its "Only parts" and "Detail sub-assemblies"
//                                                              options, the five columns it starts with, Export
//   TechDraw_PageDefault, TechDraw_ExportPageSVG / ...DXF      a drawing page, shown in an MDI view, saved as SVG or DXF
import { useEffect, useRef, useState, type FC } from 'react'
import type { IDockviewPanelProps } from 'dockview-react'
import { api, resultText, type CadResult, type CheckRow } from './api'
import { closeTask, openDrawing, select, type DrawingParams } from './actions'
import { getState, useStore } from './store'
import { cls, TaskBox, TaskButtons } from './panels'
import { QComboBox } from './combo'
import { Icon, type IconName } from './icons'
import { agentRun, RowsTable } from './agentwb'

const grams = (g: number | null | undefined) => (g == null ? 'unknown' : `${g.toFixed(2)} g`)
const bytesText = (n: number) => (n < 1024 ? `${n} B` : n < 1024 * 1024 ? `${(n / 1024).toFixed(1)} kB` : `${(n / 1024 / 1024).toFixed(1)} MB`)

/** A saved file: a download link, in the look of a button. */
function Download({ slug, path, label, icon, title }: { slug: string; path: string; label: string; icon?: IconName; title?: string }) {
  return <a className="qbtn" href={api.fileUrl(slug, path)} download title={title ?? `Save ${path}`}>{icon && <Icon name={icon} size={14} />}{label}</a>
}

/** The verdict a command's exit code is: 0 PASS, 1 FAIL, 2 UNCHECKED; 3 and 4 are not a verdict but a mistake or a crash. */
const verdictOf = (exit: number) => (exit === 0 ? 'PASS' : exit === 1 ? 'FAIL' : exit === 2 ? 'UNCHECKED' : null)

// ── Bill of Materials (cad bom) ───────────────────────────────────────────────────────────────────────
type BomLine = {
  index: string; name: string; kind: string; project: string; part: string | null; quantity: number; description: string; file_name: string
  material: string | null; process: string | null; vendor: string | null; pn: string | null; licence: string | null; source: string | null
  mass_g: number | null; mass_source: string; mass_total_g: number | null; shop_files: string[]; bodies: string[]; notes: string[]; depth: number
}
type BomData = {
  project: string; assembly: boolean; options: { only_parts: boolean; detail_subassemblies: boolean }; lines: BomLine[]
  totals: { lines: number; bodies: number; mass_known_g: number; bodies_without_mass: number; mass_complete: boolean }; files: string[]
}

/** Std Assembly_CreateBom: `cad bom`, the bill of materials of the project's assembly as a table: FreeCAD's five columns
 *  first (Index, Name, Quantity, and the file and description in the line's details), then what a shop wants of each
 *  line. A click on a line selects its bodies in the 3D view; the CSV and JSON the command wrote download from here. */
export function BomTask() {
  const slug = useStore((s) => s.slug)
  const [onlyParts, setOnlyParts] = useState(false)
  const [detail, setDetail] = useState(true)
  const [data, setData] = useState<BomData | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [pick, setPick] = useState<string | null>(null)
  const run = async () => {
    if (!slug) return
    setBusy(true); setErr(null)
    const r = await agentRun(['bom', slug, ...(onlyParts ? ['--only-parts'] : []), ...(detail ? [] : ['--flat'])])
    setBusy(false)
    if (r.exit !== 0) { setErr(resultText(r)); return }
    setData(r.data as BomData)
  }
  useEffect(() => { run() }, [slug, onlyParts, detail])
  const line = data?.lines.find((l) => l.index === pick)
  const choose = (l: BomLine) => {
    setPick(l.index)
    l.bodies.forEach((b, i) => select(b, i > 0))
  }
  const t = data?.totals
  const details: [string, string][] = !line ? [] : [
    ['Description', line.description], ['File', line.file_name], ['Material', line.material ?? ''], ['Process', line.process ?? ''],
    ['Vendor', line.vendor ?? ''], ['Part number', line.pn ?? ''], ['Licence', line.licence ?? ''], ['Source', line.source ?? ''],
    ['Mass each', `${grams(line.mass_g)}${line.mass_source ? ` (${line.mass_source})` : ''}`], ['Shop file', line.shop_files.join(', ')],
    ['Bodies', line.bodies.join(', ')], ['Notes', line.notes.join('; ')],
  ].filter(([, v]) => v) as [string, string][]
  return (
    <div className="tasks">
      <TaskButtons onOk={closeTask} />
      <div className="tbuttons"><button className="qbtn" disabled={busy || !slug} onClick={run}>Run again</button></div>
      <TaskBox title="Bill of Materials" icon="bom">
        <label className="tcheck" title="Only the parts made here and sub-assemblies, not what is bought or stock (FreeCAD's Only parts)">
          <input type="checkbox" checked={onlyParts} onChange={(e) => setOnlyParts(e.target.checked)} /> Only parts</label>
        <label className="tcheck" title="A sub-assembly's parts are listed under it (FreeCAD's Detail sub-assemblies); off, it is one line">
          <input type="checkbox" checked={detail} onChange={(e) => setDetail(e.target.checked)} /> Detail sub-assemblies</label>
        {busy && <p className="hint">Running cad bom…</p>}
        {err && <p className="hint err">{err}</p>}
        {data && !data.lines.length && <p className="hint">Nothing to list: the project has no parts.</p>}
        {!!data?.lines.length && <table className="ctable wrap">
          <thead><tr><th>#</th><th>Name</th><th>Qty</th><th>Kind</th><th>Material</th><th>Mass</th></tr></thead>
          <tbody>{data.lines.map((l) => (
            <tr key={l.index} className={cls(pick === l.index && 'sel')} onClick={() => choose(l)} title={l.description || l.source || undefined}>
              <td>{l.index}</td><td style={{ paddingLeft: 6 + l.depth * 12 }}>{l.name}</td><td>{l.quantity}</td><td>{l.kind}</td>
              <td>{l.material ?? ''}</td><td>{l.mass_total_g == null ? 'unknown' : `${l.mass_total_g.toFixed(1)} g`}</td>
            </tr>
          ))}</tbody>
        </table>}
        {t && <p className="hint">{t.lines} lines, {t.bodies} bodies, {t.mass_known_g.toFixed(2)} g known
          {t.mass_complete ? '' : `; ${t.bodies_without_mass} of ${t.bodies} bodies have no known mass, so this is not the weight of the machine`}</p>}
        {!!details.length && <table className="ctable wrap"><tbody>{details.map(([k, v]) => <tr key={k}><td>{k}</td><td>{v}</td></tr>)}</tbody></table>}
        {data && slug && <div className="tbuttons dl">
          <Download slug={slug} path="out/bom.csv" label="CSV" title="Save out/bom.csv (FreeCAD's columns first)" />
          <Download slug={slug} path="out/bom.json" label="JSON" title="Save out/bom.json" />
        </div>}
        <p className="hint">the bill of materials of the project's assembly: kind, material, process, vendor, part number, mass</p>
      </TaskBox>
    </div>
  )
}

// ── Shop files (cad shop) ─────────────────────────────────────────────────────────────────────────────
type ShopFile = { path: string; part?: string | null; format?: string; sha256: string; bytes: number }
type Manifest = { draft: boolean; verdict: string; commit: string | null; dirty: boolean; done: boolean; reasons: string[]; files: ShopFile[]; missing: string[]
  bom: { lines: number; bodies: number; mass_known_g: number }; drawings: { built: boolean; skipped?: Record<string, string>; why?: string }
  skipped: { part: string; why: string }[] }
type ShopMode = 'write' | 'draft' | 'check'
const SHOP_ARGS: Record<ShopMode, string[]> = { write: [], draft: ['--draft'], check: ['--check'] }

/** `cad shop`: write out/shop/ (DXF, 3MF, STL, STEP, drawings and the BOM, with a manifest of every file's hash) for a design
 *  that is done, or stamped NOT VERIFIED as a draft, or check that what is on disk is what a fresh run makes. What is in the
 *  folder is read from its manifest, so the panel shows it also after a restart, and each file downloads from here. */
export function ShopTask() {
  const slug = useStore((s) => s.slug)
  const [manifest, setManifest] = useState<Manifest | null | undefined>(undefined)
  const [last, setLast] = useState<{ mode: ShopMode; r: CadResult } | null>(null)
  const [busy, setBusy] = useState<ShopMode | null>(null)
  const [all, setAll] = useState(false)
  const read = async () => {
    if (!slug) return
    try {
      const r = await fetch(api.fileUrl(slug, 'out/shop/manifest.json'))
      setManifest(r.ok ? await r.json() : null)
    } catch { setManifest(null) }
  }
  useEffect(() => { setManifest(undefined); setLast(null); read() }, [slug])
  const go = async (mode: ShopMode) => {
    if (!slug || busy) return
    setBusy(mode)
    const r = await agentRun(['shop', slug, ...SHOP_ARGS[mode], ...(all ? ['--all'] : [])])
    setBusy(null); setLast({ mode, r })
    if (mode !== 'check') read()
  }
  const d = last?.r.data ?? {}
  const verdict = last ? verdictOf(last.r.exit) : null
  const rows = (d.rows ?? []) as CheckRow[]
  const diffs = (d.differences ?? []) as { path: string; why: string; detail: string }[]
  const skipped = (d.skipped ?? manifest?.skipped ?? []) as { part: string; why: string }[]
  const drawings = (d.drawings ?? manifest?.drawings) as Manifest['drawings'] | undefined
  const label: Record<ShopMode, string> = { write: 'Write files', draft: 'Write draft', check: 'Check folder' }
  return (
    <div className="tasks">
      <TaskButtons onOk={closeTask} />
      <div className="tbuttons">
        {(['write', 'draft', 'check'] as ShopMode[]).map((m) => (
          <button key={m} className={cls('qbtn', m === 'write' && 'default')} disabled={!!busy || !slug} onClick={() => go(m)}
            title={m === 'write' ? 'write out/shop/ for the design `cad done` holds' : m === 'draft' ? 'write it anyway, with NOT VERIFIED in every file'
              : 'write nothing: regenerate out/shop/ and compare it with what is on disk'}>{label[m]}</button>))}
      </div>
      <TaskBox title="Shop files" icon="export">
        <label className="tcheck"><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> Show passing rows too</label>
        {busy && <p className="hint">Running cad shop{SHOP_ARGS[busy].length ? ` ${SHOP_ARGS[busy][0]}` : ''}… It builds every part from source, so it takes a while.</p>}
        {last && last.r.exit > 2 && <p className="hint err">{resultText(last.r)}</p>}
        {last && verdict && <p><span className={cls('verdict', verdict.toLowerCase())}>{verdict}</span> {label[last.mode].toLowerCase()}
          {d.draft ? ' (NOT VERIFIED)' : ''}{typeof d.rows_total === 'number' ? `, ${d.rows_total} rows` : ''}</p>}
        {last && d.done === false && !!d.reasons?.length && <ul className="hint">{(d.reasons as string[]).map((x, i) => <li key={i}>{x}</li>)}
          <li>`cad verify` on committed work makes a design done; Write draft shows what it would send, stamped.</li></ul>}
        {!!rows.length && <RowsTable rows={rows} />}
        {!!diffs.length && <table className="ctable wrap"><thead><tr><th>File</th><th>Differs</th><th>Why</th></tr></thead>
          <tbody>{diffs.map((x) => <tr key={x.path} className="st-fail"><td>{x.path}</td><td>{x.why}</td><td>{x.detail}</td></tr>)}</tbody></table>}
        {last?.mode === 'check' && last.r.exit === 0 && <p className="hint">out/shop/ is what a fresh run writes, file by file.</p>}
        {!!skipped.length && <p className="hint">Left out: {skipped.map((s) => `${s.part} (${s.why})`).join('; ')}</p>}
        {drawings && !drawings.built && <p className="hint">Drawings: not built{drawings.why ? ` (${drawings.why})` : ''}</p>}
        {drawings?.skipped && Object.keys(drawings.skipped).length > 0 && <p className="hint">Not drawn: {Object.entries(drawings.skipped).map(([p, w]) => `${p} (${w})`).join('; ')}</p>}
        {manifest === null && <p className="hint">out/shop/ has nothing yet.</p>}
        {manifest && <>
          <p className="hint">In out/shop/: {manifest.draft ? <b>draft, {manifest.verdict}</b> : <b>{manifest.verdict}</b>}, {manifest.files.length} files, commit {manifest.commit ? manifest.commit.slice(0, 10) : 'none'}
            {manifest.dirty ? ' (uncommitted changes)' : ''}</p>
          <table className="ctable wrap">
            <thead><tr><th>File</th><th>Size</th><th /></tr></thead>
            <tbody>{[...manifest.files, { path: 'manifest.json', sha256: '', bytes: 0 } as ShopFile].map((f) => (
              <tr key={f.path}>
                <td title={f.sha256 ? `sha256 ${f.sha256}` : undefined}>{f.path}</td><td>{f.bytes ? bytesText(f.bytes) : ''}</td>
                <td className="dl">
                  {/\.(svg|pdf)$/.test(f.path) && slug && <a className="qbtn" href={api.fileUrl(slug, `out/shop/${f.path}`, true)} target="_blank" rel="noreferrer" title="Show in a browser tab">View</a>}
                  {slug && <a className="qbtn" href={api.fileUrl(slug, `out/shop/${f.path}`)} download title={`Save ${f.path}`}>Save</a>}
                </td>
              </tr>))}</tbody>
          </table>
        </>}
        <p className="hint">write out/shop/ for a verified design: DXF, 3MF, STL, STEP, drawings and the BOM</p>
      </TaskBox>
    </div>
  )
}

// ── Drawing (cad drawing) ─────────────────────────────────────────────────────────────────────────────
const SHEETS = ['auto', 'A4', 'A3', 'A2', 'A1', 'A0']
const SCALES = ['auto', '50:1', '20:1', '10:1', '5:1', '2:1', '1:1', '1:2', '1:5', '1:10', '1:20', '1:50', '1:100', '1:200', '1:500', '1:1000']
type DrawingData = { project: string; part: string; process: string; angle: string; done: boolean; reasons: string[]; stamp: string | null
  plate: string | null; sheet: { size: string; scale: string } | null; rows: CheckRow[]; rows_total: number; wrote: string[]; files: { path: string; bytes: number }[] }

/** The parts `cad drawing` can draw: made by cnc or laser_cut (a plate is judged by the command). The last Check knows each
 *  part's PROCESS; before it, any part is offered and the command says what is wrong with it. */
export function plateParts(): string[] {
  const s = getState()
  const parts = [...new Set((s.scene?.bodies ?? []).map((b) => b.part).filter((p): p is string => !!p))]
  const meta = s.checks?.parts
  const plates = meta ? parts.filter((p) => ['cnc', 'laser_cut'].includes(String(meta[p]?.process))) : parts
  return plates.length ? plates : parts
}

/** `cad drawing`: a dimensioned drawing of one machined or laser-cut plate (TechDraw's job): DXF, SVG and PDF in out/drawings/.
 *  The sheet and scale are the command's own choices unless asked for. The result opens as a tab (DrawingPanel) and downloads
 *  from here. A design nobody verified gets the drawing stamped NOT VERIFIED, and the exit says UNCHECKED, as `cad shop --draft` does. */
export function DrawingTask({ part: want }: { part?: string }) {
  const slug = useStore((s) => s.slug)
  useStore((s) => s.scene); useStore((s) => s.checks)
  const parts = plateParts()
  const [part, setPart] = useState(want && parts.includes(want) ? want : parts[0] ?? '')
  const [angle, setAngle] = useState('first')
  const [sheet, setSheet] = useState('auto')
  const [scale, setScale] = useState('auto')
  const [fmt, setFmt] = useState({ svg: true, pdf: true })
  const [all, setAll] = useState(false)
  const [res, setRes] = useState<{ r: CadResult; data: DrawingData } | null>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => { if (!part && parts[0]) setPart(parts[0]) }, [parts.join(',')])
  const run = async () => {
    if (!slug || !part) return
    setBusy(true); setRes(null)
    const formats = ['dxf', ...(fmt.svg ? ['svg'] : []), ...(fmt.pdf ? ['pdf'] : [])].join(',')
    const r = await agentRun(['drawing', slug, part, '--angle', angle, '--sheet', sheet, '--scale', scale, '--format', formats, ...(all ? ['--all'] : [])])
    setBusy(false)
    const data = (r.data ?? {}) as DrawingData
    setRes({ r, data })
    if (data.files?.some((f) => f.path.endsWith('.svg'))) {
      openDrawing({ slug, part, files: data.files.map((f) => f.path), sheet: data.sheet ? `${data.sheet.size} ${data.sheet.scale}` : null, angle: data.angle, stamp: data.stamp, nonce: Date.now() })
    }
  }
  const verdict = res ? verdictOf(res.r.exit) : null
  const written = res?.data.files ?? []
  return (
    <div className="tasks">
      <TaskButtons onOk={closeTask} okDisabled={false} />
      <div className="tbuttons"><button className="qbtn default" disabled={busy || !slug || !part} onClick={run}>Draw</button></div>
      <TaskBox title="Drawing" icon="drawing">
        <div className="tform">
          <label className="tfield"><span>Part</span>
            <QComboBox className="qselect-field" value={part} onChange={(e) => setPart(e.target.value)}>
              {!parts.length && <option value="">(no parts)</option>}
              {parts.map((p) => <option key={p} value={p}>{p}</option>)}
            </QComboBox></label>
          <label className="tfield"><span>Projection</span>
            <QComboBox className="qselect-field" value={angle} onChange={(e) => setAngle(e.target.value)} title="first angle is ISO 128-30 and TechDraw's default">
              <option value="first">first angle</option><option value="third">third angle</option>
            </QComboBox></label>
          <label className="tfield"><span>Sheet</span>
            <QComboBox className="qselect-field" value={sheet} onChange={(e) => setSheet(e.target.value)} title="auto is the smallest sheet the views fit">
              {SHEETS.map((s) => <option key={s} value={s}>{s}</option>)}
            </QComboBox></label>
          <label className="tfield"><span>Scale</span>
            <QComboBox className="qselect-field" value={scale} onChange={(e) => setScale(e.target.value)} title="a scale of ISO 5455">
              {SCALES.map((s) => <option key={s} value={s}>{s}</option>)}
            </QComboBox></label>
        </div>
        <label className="tcheck" title="the DXF is the master and is always made"><input type="checkbox" checked disabled /> DXF</label>
        <label className="tcheck"><input type="checkbox" checked={fmt.svg} onChange={(e) => setFmt({ ...fmt, svg: e.target.checked })} /> SVG (shown in a tab)</label>
        <label className="tcheck"><input type="checkbox" checked={fmt.pdf} onChange={(e) => setFmt({ ...fmt, pdf: e.target.checked })} /> PDF</label>
        <label className="tcheck"><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> Show passing rows too</label>
        {busy && <p className="hint">Running cad drawing…</p>}
        {res && res.r.exit > 2 && <p className="hint err">{resultText(res.r)}</p>}
        {res && verdict && <>
          <p><span className={cls('verdict', verdict.toLowerCase())}>{verdict}</span> {res.data.sheet ? `${res.data.sheet.size} ${res.data.sheet.scale}, ${res.data.angle} angle` : 'not drawn'}
            {res.data.stamp ? ` · ${res.data.stamp}` : ''}</p>
          {res.data.plate && <p className="hint">{res.data.plate}</p>}
          {!!res.data.rows?.length && <RowsTable rows={res.data.rows} />}
          {res.r.exit !== 0 && !written.length && !!res.data.reasons?.length && <ul className="hint">{res.data.reasons.map((x, i) => <li key={i}>{x}</li>)}</ul>}
        </>}
        {!!written.length && slug && <div className="tbuttons dl">
          {written.map((f) => {
            const ext = f.path.split('.').pop() ?? ''
            return <Download key={f.path} slug={slug} path={`out/drawings/${f.path}`} label={ext.toUpperCase()}
              icon={ext === 'dxf' ? 'export-dxf' : ext === 'svg' ? 'export-svg' : undefined} title={`Save out/drawings/${f.path} (${bytesText(f.bytes)})`} />
          })}
        </div>}
        <p className="hint">a dimensioned drawing (DXF, SVG, PDF) of one machined or laser-cut plate</p>
      </TaskBox>
    </div>
  )
}

// ── The drawing's tab (TechDraw's MDI view of a page) ─────────────────────────────────────────────────
type View = { x: number; y: number; k: number }
/** The sheet in a tab: the SVG `cad drawing` wrote, panned with a drag and zoomed with the wheel about the pointer, with
 *  Fit and the three files to save. Nothing in the SVG can run: it is an image here, and the server sends it with a policy
 *  that stops scripts when it is opened on its own. */
export const DrawingPanel: FC<IDockviewPanelProps<DrawingParams>> = (props) => {
  const [p, setP] = useState<DrawingParams>(props.params)
  useEffect(() => {
    setP(props.params)
    const sub = props.api.onDidParametersChange((np) => setP(np as DrawingParams))
    return () => sub.dispose()
  }, [props.api])
  const box = useRef<HTMLDivElement>(null)
  const img = useRef<HTMLImageElement>(null)
  const [v, setV] = useState<View>({ x: 0, y: 0, k: 1 })
  const [loaded, setLoaded] = useState(false)
  const src = `${api.fileUrl(p.slug, `out/drawings/${p.part}.svg`, true)}&v=${p.nonce}`
  const fit = () => {
    const b = box.current, i = img.current
    if (!b || !i || !i.naturalWidth) return
    const k = Math.min(b.clientWidth / i.naturalWidth, b.clientHeight / i.naturalHeight) * 0.97
    setV({ k, x: (b.clientWidth - i.naturalWidth * k) / 2, y: (b.clientHeight - i.naturalHeight * k) / 2 })
  }
  useEffect(() => { setLoaded(false) }, [src])
  useEffect(() => { if (loaded) fit() }, [loaded])
  useEffect(() => {
    const b = box.current
    if (!b) return
    const ro = new ResizeObserver(() => { if (loaded) fit() })
    ro.observe(b)
    const wheel = (e: WheelEvent) => {
      e.preventDefault()
      const r = b.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top
      setV((o) => {
        const k = Math.min(40, Math.max(0.02, o.k * Math.exp(-e.deltaY * 0.0015)))
        return { k, x: mx - ((mx - o.x) / o.k) * k, y: my - ((my - o.y) / o.k) * k }
      })
    }
    b.addEventListener('wheel', wheel, { passive: false })
    return () => { ro.disconnect(); b.removeEventListener('wheel', wheel) }
  }, [loaded])
  const drag = useRef<{ x: number; y: number } | null>(null)
  const zoom = (f: number) => {
    const b = box.current
    if (!b) return
    const mx = b.clientWidth / 2, my = b.clientHeight / 2
    setV((o) => ({ k: o.k * f, x: mx - ((mx - o.x) / o.k) * o.k * f, y: my - ((my - o.y) / o.k) * o.k * f }))
  }
  return (
    <div className="drawing">
      <div className="drawing-bar">
        <Icon name="drawing" size={16} />
        <b>{p.part}</b>
        <span>{[p.sheet, p.angle && `${p.angle} angle`].filter(Boolean).join(', ')}</span>
        {p.stamp && <span className="verdict unchecked" title="the design is not done, so every file says so">{p.stamp}</span>}
        <span className="spacer" />
        <button className="qbtn ibtn" title="Fit" onClick={fit}><Icon name="fit-all" size={14} /></button>
        <button className="qbtn ibtn" title="Zoom out" onClick={() => zoom(1 / 1.25)}><Icon name="zoom-out" size={14} /></button>
        <button className="qbtn ibtn" title="Zoom in" onClick={() => zoom(1.25)}><Icon name="zoom-in" size={14} /></button>
        {p.files.map((f) => {
          const ext = f.split('.').pop() ?? ''
          return <Download key={f} slug={p.slug} path={`out/drawings/${f}`} label={ext.toUpperCase()}
            icon={ext === 'dxf' ? 'export-dxf' : ext === 'svg' ? 'export-svg' : undefined} />
        })}
        {p.files.includes(`${p.part}.pdf`) && <a className="qbtn" href={api.fileUrl(p.slug, `out/drawings/${p.part}.pdf`, true)} target="_blank" rel="noreferrer" title="Show the PDF in a browser tab">View PDF</a>}
      </div>
      <div className="drawing-sheet" ref={box}
        onPointerDown={(e) => { drag.current = { x: e.clientX, y: e.clientY }; (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId) }}
        onPointerMove={(e) => { const d = drag.current; if (!d) return; drag.current = { x: e.clientX, y: e.clientY }; setV((o) => ({ ...o, x: o.x + e.clientX - d.x, y: o.y + e.clientY - d.y })) }}
        onPointerUp={() => { drag.current = null }} onDoubleClick={fit}>
        <img ref={img} src={src} alt={`Drawing of ${p.part}`} draggable={false} onLoad={() => setLoaded(true)}
          style={{ transform: `translate(${v.x}px, ${v.y}px) scale(${v.k})`, visibility: loaded ? 'visible' : 'hidden' }} />
      </div>
    </div>
  )
}

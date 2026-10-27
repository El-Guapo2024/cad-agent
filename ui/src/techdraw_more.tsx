// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/TechDraw/Gui/CommandAnnotate.cpp: 2019 WandererFan
//   src/Mod/TechDraw/Gui/Command.cpp: 2002 Jürgen Riegel; 2014 Luke Parry
//   src/Mod/TechDraw/Gui/CommandDecorate.cpp: 2014 Luke Parry
//   src/Mod/TechDraw/Gui/TaskLeaderLine.cpp: 2019 WandererFan
//   src/Mod/TechDraw/Gui/TaskRichAnno.cpp: 2019 WandererFan
//   src/Mod/TechDraw/Gui/TaskWeldingSymbol.cpp: 2019 WandererFan
//   src/Mod/TechDraw/Gui/SymbolChooser.cpp: 2019 WandererFan
//   src/Mod/TechDraw/Gui/TaskSurfaceFinishSymbols.cpp: 2021 Adrian Insaurralde
//   src/Mod/TechDraw/Gui/QGTracker.cpp: 2019 WandererFan
//   No copyright line in the file: src/Mod/TechDraw/Gui/TaskLeaderLine.ui, src/Mod/TechDraw/Gui/TaskRichAnno.ui,
//       src/Mod/TechDraw/Gui/TaskWeldingSymbol.ui, src/Mod/TechDraw/Gui/SymbolChooser.ui, src/Mod/TechDraw/Gui/TaskSurfaceFinishSymbols.ui
// TechDraw's leader line, rich text, symbol, weld symbol, surface finish, image and clip group tools: their commands (active
// as CommandAnnotate.cpp, Command.cpp and CommandDecorate.cpp say), the task panels of TaskLeaderLine (the tracker's clicks on
// the page, QGTracker), TaskRichAnno (placement by a click, the text edited in place with a floating toolbar and kept as
// QTextDocument::toHtml writes it), TaskWeldingSymbol with SymbolChooser and TaskSurfaceFinishSymbols, and the file choosers
// (Gui::FileDialog: FreeCAD's symbols and the project's files, or a file of the person's own through /api/upload). Each is one
// `cad techdraw apply` of the ops of cad_agent/techdraw_more.py: one undo step named as FreeCAD's transaction.
import { useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from 'react'
import { createPortal } from 'react-dom'
import { api } from './api'
import { closeTask, doUndo, openTask } from './actions'
import { getState } from './store'
import { QtForm, type Bindings } from './qtform'
import { TECHDRAW_FORMS } from './uiforms-techdraw'
import { TaskBox } from './panels'
import { messageBox } from './msgbox'
import type { IconName } from './icons'
import { applyTd, clearPreview, objOf, setTd, splitRef, tdState, useTd, activePage, openPage, refOf, type TdDoc, type TdObj } from './techdraw'

const warn = (title: string, text: string) => void messageBox('warning', title, text)
const icon = (f: string) => f as IconName
const PX = 10
export const MORE_KINDS = ['leader', 'richanno', 'weld', 'surface']
const VIEW_LIKE = new Set(['DrawViewPart', 'DrawProjGroupItem', 'DrawViewSection', 'DrawProjGroup', 'DrawViewDimension', 'DrawViewBalloon', 'DrawViewAnnotation',
  'DrawLeaderLine', 'DrawRichAnno', 'DrawViewSymbol', 'DrawWeldSymbol', 'DrawViewImage', 'DrawViewClip'])
const isDrawView = (o: TdObj | undefined) => !!o && VIEW_LIKE.has(o.kind)
const needPage = () => { const p = activePage(); if (!p) warn('No page found', 'No Drawing Pages in document.'); return p }
const res = (page: string) => tdState().docs[page]?.result as (TdDoc['result'] & Record<string, any>) | undefined // eslint-disable-line @typescript-eslint/no-explicit-any
const selObjs = () => tdState().sel.map(splitRef)

function Buttons({ ok, cancel, okOff, cancelOff }: { ok(): void; cancel(): void; okOff?: boolean; cancelOff?: boolean }) {
  return (
    <div className="tbuttons">
      <button className="qbtn default" disabled={okOff} onClick={ok}>OK</button>
      <button className="qbtn" disabled={cancelOff} onClick={cancel}>Cancel</button>
    </div>)
}

// ── Gui::FileDialog and SymbolChooser ────────────────────────────────────────────────────────────────────────────────
export type Choice = { kind: 'shipped' | 'project'; path: string } | { kind: 'local'; file: File }
type Chooser = { title: string; accept: string; shipped: string[]; project: string[]; resolve(c: Choice | null): void }
let chooser: Chooser | null = null
const chSubs = new Set<() => void>()
const setChooser = (c: Chooser | null) => { chooser = c; chSubs.forEach((f) => f()) }
/** QFileDialog::getOpenFileName: FreeCAD's own files (its symbols folder), the project's, or a file from the person's disk. */
export const chooseFile = (o: Omit<Chooser, 'resolve'>) => new Promise<Choice | null>((resolve) => setChooser({ ...o, resolve }))

type SymbolPick = { dir: string; source: string; resolve(path: string | null): void }
let symbolPick: SymbolPick | null = null
const setSymbolPick = (c: SymbolPick | null) => { symbolPick = c; chSubs.forEach((f) => f()) }
const SYMBOL_ICONS = import.meta.glob('../../cad_agent/techdraw_symbols/Welding/**/*.svg', { query: '?url', import: 'default', eager: true }) as Record<string, string>
const symbolUrl = (path: string) => SYMBOL_ICONS[`../../cad_agent/techdraw_symbols/${path}`]
const WELD_DIR = 'Welding/AWS'
/** SymbolChooser: a dialog of the symbols of a folder (lwSymbols), the folder chosen as fcSymbolDir does; a click picks one. */
export const chooseSymbol = (dir: string, source: string) => new Promise<string | null>((resolve) => setSymbolPick({ dir, source, resolve }))

export function FileChooserHost() {
  const c = useSyncExternalStore((f) => { chSubs.add(f); return () => { chSubs.delete(f) } }, () => chooser)
  const sp = useSyncExternalStore((f) => { chSubs.add(f); return () => { chSubs.delete(f) } }, () => symbolPick)
  const [sel, setSel] = useState('')
  const [dir, setDir] = useState('')
  useEffect(() => { setSel(''); }, [c])
  useEffect(() => { if (sp) setDir(sp.dir) }, [sp])
  const input = useRef<HTMLInputElement>(null)
  const files = (tdState().pages.map((p) => res(p)?.symbol_files as string[] | undefined).find(Boolean) ?? []) as string[]
  if (sp) {
    const dirs = [...new Set(files.filter((f) => f.startsWith('Welding/')).map((f) => f.slice(0, f.lastIndexOf('/'))))].sort()
    const cur = dir || sp.dir
    const items = files.filter((f) => f.slice(0, f.lastIndexOf('/')) === cur).sort((a, b) => (a.toLowerCase() < b.toLowerCase() ? -1 : 1))   // QDir::entryList: by name, ignoring case (FreeCAD lists each twice)
    const done = (p: string | null) => { setSymbolPick(null); sp.resolve(p) }
    return createPortal(
      <div className="msgbox-back" onKeyDown={(e) => { e.stopPropagation(); if (e.key === 'Escape') done(null) }}>
        <div className="msgbox" role="dialog" aria-label="Select a Symbol" style={{ width: 700, maxWidth: '90vw' }}>
          <div className="msgbox-title">Select a Symbol</div>
          <div style={{ padding: '8px 12px', display: 'flex', gap: 8, alignItems: 'center' }}>
            <span>Symbol directory</span>
            <select className="pselect" value={dir || sp.dir} onChange={(e) => setDir(e.target.value)} data-qf="fcSymbolDir" style={{ flex: 1 }}>
              {dirs.map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
          </div>
          <div data-qf="lwSymbols" style={{ display: 'flex', flexWrap: 'wrap', gap: 0, padding: '0 12px 8px', height: 300, overflow: 'auto', alignContent: 'flex-start' }}>
            {items.map((f) => (
              <div key={f} style={{ width: 75, height: 85, textAlign: 'center', cursor: 'pointer' }} onClick={() => done(f)} title={f}>
                <img src={symbolUrl(f)} width={45} height={45} alt="" style={{ marginTop: 8 }} />
                <div style={{ fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis' }}>{f.slice(f.lastIndexOf('/') + 1).replace(/\.svg$/, '')}</div>
              </div>))}
          </div>
          <div className="msgbox-buttons"><button className="qbtn" onClick={() => done(null)}>Cancel</button></div>
        </div>
      </div>, document.body)
  }
  if (!c) return null
  const done = (r: Choice | null) => { setChooser(null); c.resolve(r) }
  const pick = (v: string) => { const [k, ...rest] = v.split(':'); return { kind: k as 'shipped' | 'project', path: rest.join(':') } }
  return createPortal(
    <div className="msgbox-back" onKeyDown={(e) => { e.stopPropagation(); if (e.key === 'Escape') done(null) }}>
      <div className="msgbox" role="dialog" aria-label={c.title} style={{ width: 520, maxWidth: '90vw' }}>
        <div className="msgbox-title">{c.title}</div>
        <div style={{ padding: 10 }}>
          <select size={14} className="pselect" style={{ width: '100%' }} value={sel} onChange={(e) => setSel(e.target.value)} onDoubleClick={() => sel && done(pick(sel))}>
            {c.shipped.length > 0 && <optgroup label="FreeCAD's symbols (Mod/TechDraw/Symbols)">{c.shipped.map((f) => <option key={f} value={`shipped:${f}`}>{f}</option>)}</optgroup>}
            {c.project.length > 0 && <optgroup label="The project's files">{c.project.map((f) => <option key={f} value={`project:${f}`}>{f}</option>)}</optgroup>}
          </select>
        </div>
        <div className="msgbox-buttons">
          <button className="qbtn" onClick={() => input.current?.click()}>Browse…</button>
          <input ref={input} type="file" accept={c.accept} style={{ display: 'none' }} onChange={(e) => { const f = e.target.files?.[0]; if (f) done({ kind: 'local', file: f }) }} />
          <button className="qbtn default" disabled={!sel} onClick={() => done(pick(sel))}>Open</button>
          <button className="qbtn" onClick={() => done(null)}>Cancel</button>
        </div>
      </div>
    </div>, document.body)
}
const symbolFiles = (page: string) => (res(page)?.symbol_files as string[] | undefined) ?? []

// ── the commands ─────────────────────────────────────────────────────────────────────────────────────────────────────
const taskOpen = () => !!getState().task
function leaderCmd() {
  const page = needPage()
  if (!page) return
  if (taskOpen()) { warn('Task in progress', 'Close active task dialog and try again'); return }
  const first = selObjs()[0]
  if (!first) { warn('Wrong selection', 'You must select a base view for the line'); return }
  const o = objOf(first[0], first[1])
  if (!isDrawView(o)) { warn('Wrong selection', 'Cannot attach leader. No base view selected.'); return }
  openTask('techdraw', first[0], `leader:${first[1]}:create`)
  setTd({ sel: [] })
}
function richCmd() {
  const page = needPage()
  if (!page) return
  if (taskOpen()) { warn('Task in progress', 'Close active task dialog and try again'); return }
  const first = selObjs()[0]
  const o = first ? objOf(first[0], first[1]) : undefined
  const base = isDrawView(o) ? o!.name : 'None'
  openPage(page)
  openTask('techdraw', page, `richanno:${base}:create`)
  setTd({ sel: [] })
}
function weldCmd() {
  const page = needPage()
  if (!page) return
  if (taskOpen()) { warn('Task in progress', 'Close active task dialog and try again'); return }
  const objs = selObjs().map(([p, n]) => objOf(p, n)).filter(Boolean) as TdObj[]
  const leaders = objs.filter((o) => o.kind === 'DrawLeaderLine'), welds = objs.filter((o) => o.kind === 'DrawWeldSymbol')
  if (leaders.length !== 1 && welds.length !== 1) { warn('Wrong selection', 'Select exactly one leader line or one weld symbol'); return }
  if (leaders.length) openTask('techdraw', page, `weld:${leaders[0].name}:create`)
  else openTask('techdraw', page, `weld:${welds[0].name}:edit`)
  setTd({ sel: [] })
}
function surfaceCmd() {
  const page = needPage()
  if (!page) return
  const first = tdState().sel.map(splitRef)[0]
  let owner = page
  if (first) {
    const o = objOf(first[0], first[1])
    if (!o || !(['DrawViewPart', 'DrawProjGroupItem', 'DrawViewSection', 'DrawLeaderLine'].includes(o.kind))) {
      warn('SurfaceFinishSymbols', 'Selected object is not a part view, nor a leader line'); return }
    owner = o.name + (first[2] ? `.${first[2]}` : '')
  }
  openTask('techdraw', page, `surface:${owner}:create`)
  setTd({ sel: [] })
}
/** CommandHelpers::firstViewInSelection */
const firstView = () => { const f = selObjs().find(([p, n]) => isDrawView(objOf(p, n))); return f ? f[1] : undefined }

async function symbolCmd() {
  const page = needPage()
  if (!page) return
  const owner = firstView()
  const c = await chooseFile({ title: 'Choose an SVG file to open', accept: '.svg,.svgz,image/svg+xml', shipped: symbolFiles(page), project: [] })
  if (!c) return
  let op: Record<string, unknown>
  if (c.kind === 'local') op = { op: 'symbol', svg: await c.file.text() }
  else op = { op: 'symbol', file: c.path }
  if (owner) op.owner = owner
  const before = new Set(tdState().docs[page]?.objects.map((o) => o.name))
  const d = await applyTd(page, [op], 'Create Symbol')
  const made = d?.objects.find((o) => !before.has(o.name))
  if (made) setTd({ sel: [refOf(page, made.name)] })
}
async function imageCmd() {
  const page = needPage()
  if (!page) return
  const project = (res(page)?.project_images as string[] | undefined) ?? []
  const owner = firstView()
  const c = await chooseFile({ title: 'Select an image file', accept: '.png,.jpg,.jpeg,.bmp,image/*', shipped: [], project })
  if (!c) return
  const op: Record<string, unknown> = { op: 'image' }
  if (c.kind === 'local') { const up = await api.upload(c.file); op.upload = up.path } else op.file = c.path
  if (owner) op.owner = owner
  const before = new Set(tdState().docs[page]?.objects.map((o) => o.name))
  const d = await applyTd(page, [op], 'Create Image')
  const made = d?.objects.find((o) => !before.has(o.name))
  if (made) setTd({ sel: [refOf(page, made.name)] })
}
async function clipCmd() {
  const page = needPage()
  if (!page) return
  const before = new Set(tdState().docs[page]?.objects.map((o) => o.name))
  const d = await applyTd(page, [{ op: 'clip' }], 'Create clip')
  const made = d?.objects.find((o) => !before.has(o.name))
  if (made) setTd({ sel: [refOf(page, made.name)] })
}
async function clipAddCmd() {
  const objs = selObjs().map(([p, n]) => [p, objOf(p, n)] as const).filter(([, o]) => !!o) as (readonly [string, TdObj])[]
  if (objs.length !== 2) { warn('Wrong selection', 'Select one clip group and one view'); return }
  const clip = objs.find(([, o]) => o.kind === 'DrawViewClip'), view = objs.find(([, o]) => o.kind !== 'DrawViewClip' && isDrawView(o))
  if (!view) { warn('Wrong selection', 'Select exactly one view to add to clip group'); return }
  if (!clip) { warn('Wrong selection', 'Select exactly one clip group'); return }
  if (clip[0] !== view[0]) { warn('Wrong selection', 'Clip and view must be from same page'); return }
  await applyTd(clip[0], [{ op: 'clip_add', clip: clip[1].name, view: view[1].name }], 'Add clip group')
}
async function clipRemoveCmd() {
  const v = selObjs().map(([p, n]) => [p, objOf(p, n)] as const).find(([, o]) => isDrawView(o))
  if (!v) { warn('Wrong selection', 'Select exactly one view to remove from clip group'); return }
  const clip = tdState().docs[v[0]]?.objects.find((o) => o.kind === 'DrawViewClip' && (o.views as string[]).includes(v[1]!.name))
  if (!clip) { warn('Wrong selection', 'View does not belong to a clip'); return }
  await applyTd(v[0], [{ op: 'clip_remove', view: v[1]!.name }], 'Remove clip group')
}

/** The commands of this file by FreeCAD's name, with isActive (needPage, needView). */
export function moreActions(havePage: boolean, haveView: boolean): Record<string, [() => void, boolean]> {
  const haveClip = Object.values(tdState().docs).some((d) => d.objects.some((o) => o.kind === 'DrawViewClip'))
  return {
    TechDraw_LeaderLine: [leaderCmd, haveView], TechDraw_RichTextAnnotation: [richCmd, havePage], TechDraw_WeldSymbol: [weldCmd, haveView],
    TechDraw_SurfaceFinishSymbols: [surfaceCmd, haveView], TechDraw_Symbol: [() => void symbolCmd(), havePage], TechDraw_Image: [() => void imageCmd(), havePage],
    TechDraw_ClipGroup: [() => void clipCmd(), havePage], TechDraw_ClipGroupAdd: [() => void clipAddCmd(), havePage && haveClip],
    TechDraw_ClipGroupRemove: [() => void clipRemoveCmd(), havePage && haveClip],
  }
}
export const MORE_EDIT = {
  movable: new Set(['DrawViewSymbol', 'DrawViewImage', 'DrawViewClip', 'DrawRichAnno']),
  /** ViewProvider::doubleClicked: the panel an object opens (setEdit) */
  task(kind: string, name: string): string | null {
    if (kind === 'DrawLeaderLine') return `leader:${name}:edit`
    if (kind === 'DrawRichAnno') return `richanno:${name}:edit`
    if (kind === 'DrawWeldSymbol') return `weld:${name}:edit`
    return null
  },
}

// ── QGTracker, and the rich text's editor, drawn over the page ──────────────────────────────────────────────────────
/** The tracker's line (dashed, from the clicks to the pointer) and, for a rich text being edited, its editor at its place. */
export function TrackerOverlay({ page, width, height, sheetH }: { page: string; width: number; height: number; sheetH: number }) {
  const mode = useTd((s) => s.mode)
  const [hover, setHover] = useState<[number, number] | null>(null)
  const rich = useSyncExternalStore((f) => { richSubs.add(f); return () => { richSubs.delete(f) } }, () => richState)
  useEffect(() => { setHover(null) }, [mode])
  const pts = mode?.kind === 'track' && mode.page === page ? mode.points : null
  return (
    <>
      {pts && (
        <svg className="td-tracker" width={width} height={height} style={{ position: 'absolute', left: 0, top: 0, pointerEvents: 'none' }}>
          <polyline fill="none" stroke="#e8a000" strokeWidth={2} strokeDasharray="8 6"
            points={[...pts, ...(hover ? [hover] : [])].map(([x, y]) => `${x * PX},${(sheetH - y) * PX}`).join(' ')} />
        </svg>)}
      {pts && <TrackerMove page={page} sheetH={sheetH} onMove={setHover} />}
      {rich && rich.page === page && <RichEditor page={page} />}
    </>)
}
function TrackerMove({ onMove }: { page: string; sheetH: number; onMove(p: [number, number] | null): void }) {
  useEffect(() => {
    const h = (ev: PointerEvent) => {
      const sheet = document.querySelector('.td-sheet') as HTMLElement | null
      if (!sheet) return
      const r = sheet.getBoundingClientRect()
      const k = r.width / (sheet.offsetWidth || 1)
      const x = (ev.clientX - r.left) / k / PX, y = tdState().docs[activePage() ?? '']?.result?.height ?? 210
      onMove([x, y - (ev.clientY - r.top) / k / PX])
    }
    window.addEventListener('pointermove', h)
    return () => window.removeEventListener('pointermove', h)
  }, [onMove])
  return null
}

// ── Qt's HTML (QTextDocument::toHtml) for the rich text ─────────────────────────────────────────────────────────────
const QT_HEAD = '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN" "http://www.w3.org/TR/REC-html40/strict.dtd">\n<html><head><meta name="qrichtext" content="1" /><meta charset="utf-8" /><style type="text/css">\np, li { white-space: pre-wrap; }\nhr { height: 1px; border-width: 0; }\nli.unchecked::marker { content: "\\2610"; }\nli.checked::marker { content: "\\2612"; }\n</style></head>'
const QT_BODY = '<body style=" font-family:\'Sans Serif\'; font-size:9pt; font-weight:400; font-style:normal;">'
const QT_P = '<p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;">'
export type Run = { text: string; bold: boolean; italic: boolean; underline: boolean; color: string | null; pt: number | null }
const esc = (t: string) => t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
/** The blocks of runs as the text document writes them: a span only where a run is not the body's own format, its properties in
 *  Qt's order (font-size, font-weight, font-style, text-decoration, color). */
export function qtHtml(blocks: Run[][]): string {
  const ps = blocks.map((runs) => {
    const body = runs.filter((r) => r.text).map((r) => {
      const st = [r.pt ? `font-size:${r.pt}pt;` : '', r.bold ? 'font-weight:700;' : '', r.italic ? 'font-style:italic;' : '', r.underline ? 'text-decoration: underline;' : '',
        r.color ? `color:${r.color};` : ''].filter(Boolean).join(' ')
      return st ? `<span style=" ${st}">${esc(r.text)}</span>` : esc(r.text)
    }).join('')
    return QT_P + (body || '<br />') + '</p>'
  })
  return `${QT_HEAD}${QT_BODY}\n${ps.join('\n')}</body></html>`
}
export const EMPTY_HTML = qtHtml([[]])
/** The editor's content as runs, read from the computed styles of each text node. */
function editorBlocks(root: HTMLElement): Run[][] {
  const blocks: Run[][] = []
  const base = getComputedStyle(root)
  const hex = (c: string) => { const m = /rgba?\((\d+),\s*(\d+),\s*(\d+)/.exec(c); return m ? '#' + [1, 2, 3].map((i) => Number(m[i]).toString(16).padStart(2, '0')).join('') : null }
  const baseColor = hex(base.color)
  const walk = (n: Node, runs: Run[]) => {
    if (n.nodeType === Node.TEXT_NODE) {
      const el = n.parentElement!, cs = getComputedStyle(el)
      const pt = Math.round((9 * parseFloat(cs.fontSize)) / parseFloat(base.fontSize) * 100) / 100       // the editor's size is the body's 9 pt
      const basePt = 9
      const col = hex(cs.color)
      runs.push({ text: n.textContent ?? '', bold: Number(cs.fontWeight) >= 600 || cs.fontWeight === 'bold', italic: cs.fontStyle === 'italic', underline: cs.textDecorationLine.includes('underline'),
        color: col && col !== baseColor ? col : null, pt: pt !== basePt ? pt : null })
    } else n.childNodes.forEach((c) => walk(c, runs))
  }
  const isBlock = (n: Node) => n.nodeType === Node.ELEMENT_NODE && /^(P|DIV|LI)$/.test((n as Element).tagName)
  let loose: Run[] | null = null
  root.childNodes.forEach((n) => {
    if (isBlock(n)) { loose = null; const runs: Run[] = []; walk(n, runs); blocks.push(runs) }
    else if (n.nodeType === Node.TEXT_NODE && /^\s*$/.test(n.textContent ?? '')) { /* the whitespace between the blocks */ }
    else { if (!loose) { loose = []; blocks.push(loose) } walk(n, loose) }
  })
  return blocks.length ? blocks : [[]]
}
/** The body of an AnnoText, as the editor takes it. */
const bodyOf = (html: string) => { const m = /<body[^>]*>([\s\S]*)<\/body>/i.exec(html); return (m ? m[1] : html).trim().replace(/<\/p>\s*<p/g, '</p><p') }

type RichState = { page: string; name: string; html: string; create: boolean; started: boolean } | null
let richState: RichState = null
const richSubs = new Set<() => void>()
const setRich = (r: RichState) => { richState = r; richSubs.forEach((f) => f()) }

/** MRichTextEdit (minimal mode): a small toolbar over the text, which is edited in place. */
function RichEditor({ page }: { page: string }) {
  const r = richState!
  const ref = useRef<HTMLDivElement>(null)
  const o = objOf(page, r.name)
  const at = (res(page)?.richannos?.[r.name]?.at as [number, number] | undefined) ?? [Number(o?.x ?? 0), (res(page)?.height ?? 210) - Number(o?.y ?? 0)]
  useLayoutEffect(() => { if (ref.current && !r.started) { ref.current.innerHTML = bodyOf(String(o?.anno_text ?? EMPTY_HTML)); ref.current.focus(); { const p0 = ref.current.querySelector('p'); if (p0) { const rg = document.createRange(); rg.selectNodeContents(p0); rg.collapse(true); const sl = window.getSelection(); sl?.removeAllRanges(); sl?.addRange(rg) } } setRich({ ...r, started: true }) } }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const timer = useRef<number | undefined>(undefined)
  const push = () => {
    if (!ref.current) return
    const html = qtHtml(editorBlocks(ref.current))
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => { setRich({ ...richState!, html }); richPush(html) }, 400)
  }
  const cmd = (c: string, v?: string) => { document.execCommand('styleWithCSS', false, 'true'); document.execCommand(c, false, v); ref.current?.focus(); push() }
  const size = (pt: number) => {                   // the selection set in pt points (Qt writes font-size:{n}pt)
    const sel = window.getSelection()
    if (!sel || !sel.rangeCount || sel.isCollapsed || !ref.current?.contains(sel.anchorNode)) return
    const range = sel.getRangeAt(0)
    const span = document.createElement('span')
    span.style.fontSize = `${(pt / 9) * 31.75}px`
    span.appendChild(range.extractContents())
    range.insertNode(span)
    push()
  }
  const mw = Number(o?.max_width ?? -1)
  return (
    <div className="td-rich" style={{ position: 'absolute', left: at[0] * PX, top: at[1] * PX, width: mw > 0 ? mw * PX : undefined, minWidth: 100, zIndex: 5 }} onPointerDown={(e) => e.stopPropagation()}
      onPointerUp={(e) => e.stopPropagation()} onDoubleClick={(e) => e.stopPropagation()}>
      <div className="td-rich-bar" style={{ position: 'absolute', bottom: '100%', left: 0, display: 'flex', gap: 3, background: 'var(--primary)', border: '1px solid #8a8a8a', padding: 2, marginBottom: 6, transform: 'scale(2.5)', transformOrigin: 'bottom left', whiteSpace: 'nowrap' }}>
        <button className="qbtn" style={{ minWidth: 22, padding: 0, fontWeight: 700 }} title="Bold" onMouseDown={(e) => e.preventDefault()} onClick={() => cmd('bold')}>B</button>
        <button className="qbtn" style={{ minWidth: 22, padding: 0, fontStyle: 'italic' }} title="Italic" onMouseDown={(e) => e.preventDefault()} onClick={() => cmd('italic')}>I</button>
        <button className="qbtn" style={{ minWidth: 22, padding: 0, textDecoration: 'underline' }} title="Underline" onMouseDown={(e) => e.preventDefault()} onClick={() => cmd('underline')}>U</button>
        <input type="color" defaultValue="#000000" title="Text color" style={{ width: 24, height: 22, padding: 0 }} onMouseDown={(e) => { e.stopPropagation() }} onChange={(e) => cmd('foreColor', e.target.value)} />
        <select title="Size (pt)" defaultValue="" onMouseDown={(e) => e.stopPropagation()} onChange={(e) => { if (e.target.value) size(Number(e.target.value)); e.target.value = '' }}>
          <option value="">size</option>{[6, 8, 9, 10, 12, 14, 18, 24, 36].map((x) => <option key={x} value={x}>{x}</option>)}
        </select>
      </div>
      <div ref={ref} contentEditable suppressContentEditableWarning spellCheck={false} onInput={push} onBlur={push} style={{ fontFamily: 'Sans Serif, sans-serif', fontSize: '31.75px', color: '#000', outline: '1px dashed #e8a000', minHeight: 40, whiteSpace: 'pre-wrap', lineHeight: 1.2, background: 'rgba(255,255,255,0.6)' }} />
    </div>)
}
let richPending: ((html: string) => void) | null = null
const richPush = (html: string) => richPending?.(html)

// ── the panels ───────────────────────────────────────────────────────────────────────────────────────────────────────
const pending: Record<string, unknown> = {}
const hex = (c: number[]) => '#' + c.slice(0, 3).map((x) => Math.round(Math.max(0, Math.min(1, x)) * 255).toString(16).padStart(2, '0')).join('')
const unhex = (s: string) => [1, 3, 5].map((i) => parseInt(s.slice(i, i + 2), 16) / 255).concat([1])
const ARROWS = ['Filled arrow', 'Open arrow', 'Tick', 'Dot', 'Open circle', 'Fork', 'Filled triangle', 'None']
const STYLES = ['NoLine', 'Continuous', 'Dash', 'Dot', 'DashDot', 'DashDotDot']
const STYLE_TEXT = ['No line', 'Continuous', 'Dash', 'Dot', 'DashDot', 'DashDotDot']

export function MoreTask({ page, other }: { page: string; other: string }) {
  const [kind, name, mode] = other.split(':')
  useEffect(() => () => { clearPreview(page); if (tdState().mode?.kind === 'track' || tdState().mode?.kind === 'place') setTd({ mode: null }) }, [page])
  if (kind === 'leader') return <LeaderTask key={other} page={page} name={name} edit={mode === 'edit'} />
  if (kind === 'richanno') return <RichTask key={other} page={page} name={name} edit={mode === 'edit'} />
  if (kind === 'weld') return <WeldTask key={other} page={page} name={name} edit={mode === 'edit'} />
  if (kind === 'surface') return <SurfaceTask key={other} page={page} owner={name} />
  return null
}

/** TaskLeaderLine: "Pick Points" starts the tracker (QGTracker: clicks, a double click or a right click ends); the symbols, colour,
 *  width and style as the panel has them. OK makes the leader (createLeaderFeature: "Create Leader"); in edit, "Edit Leader". */
function LeaderTask({ page, name, edit }: { page: string; name: string; edit: boolean }) {
  const o = edit ? objOf(page, name) : undefined
  const base = edit ? String(o?.leader_parent ?? '') : name
  const [start, setStart] = useState(o ? ARROWS.indexOf(String(o.start_symbol)) : 0)
  const [end, setEnd] = useState(o ? ARROWS.indexOf(String(o.end_symbol)) : 7)
  const [color, setColor] = useState(o ? hex(o.color as number[]) : '#000000')
  const [width, setWidth] = useState(o ? Number(o.line_width) : 0.5)
  const [style, setStyle] = useState(o ? STYLES.indexOf(String(o.line_style)) : 1)
  const [phase, setPhase] = useState<'idle' | 'picking' | 'picked'>('idle')
  const [label, setLabel] = useState(edit ? 'Edit Points' : 'Pick Points')
  const [pts, setPts] = useState<[number, number][]>([])
  const common = () => ({ start_symbol: ARROWS[start], end_symbol: ARROWS[end], color: unhex(color), line_width: width, line_style: STYLES[style] })
  const op = () => (edit ? { op: 'leader_edit', name, ...common(), ...(pts.length ? { points: pts } : {}) } : { op: 'leader', view: base, points: pts, ...common() })
  const changed = edit && JSON.stringify([start, end, color, width, style]) !== JSON.stringify([ARROWS.indexOf(String(o?.start_symbol)), ARROWS.indexOf(String(o?.end_symbol)), hex((o?.color as number[]) ?? [0, 0, 0, 1]), Number(o?.line_width), STYLES.indexOf(String(o?.line_style))])
  useEffect(() => { if (phase !== 'picking' && (pts.length || changed)) void applyTd(page, [op()], undefined, true); else clearPreview(page) }, [JSON.stringify([start, end, color, width, style, pts, phase])]) // eslint-disable-line react-hooks/exhaustive-deps
  const finish = (p: [number, number][]) => { setTd({ mode: null }); setPts(p); setPhase('picked') }
  const track = () => {
    if (phase === 'picking') {                    // "Save Points": ends the tracker with what it has
      const m = tdState().mode
      if (m?.kind === 'track') { m.onFinish(m.points); setLabel(edit ? 'Edit Points' : 'Pick Points') }
      return
    }
    setPts([]); setPhase('picking'); setLabel(edit ? 'Save Changes' : 'Save Points')
    setTd({ mode: { kind: 'track', page, points: [], onChange: (p) => setTd((s) => (s.mode?.kind === 'track' ? { mode: { ...s.mode, points: p } } : {})), onFinish: finish } })
    openPage(page)
  }
  const discard = () => { setTd({ mode: null }); setPts([]); setPhase('idle'); setLabel('Edit Points') }
  const ok = async () => {
    if (!edit || changed || pts.length) await applyTd(page, [op()], edit ? 'Edit Leader' : 'Create Leader')
    clearPreview(page)
    setTd({ mode: null })
    closeTask()
  }
  const bind: Bindings = {
    tbBaseView: { node: <div style={{ padding: '2px 4px' }}>{base}</div> },
    pbTracker: { text: label, click: track, off: phase === 'picked' },
    pbCancelEdit: { click: discard, off: phase !== 'picking' },
    cboxStartSym: { value: start, opts: ARROWS.map((x, i) => [i, x] as const), set: setStart },
    cboxEndSym: { value: end, opts: ARROWS.map((x, i) => [i, x] as const), set: setEnd },
    cpLineColor: { value: color, set: setColor },
    dsbWeight: { value: width, suffix: ' mm', dec: 2, min: 0, max: 1e3, set: setWidth },
    cboxStyle: { value: style, opts: STYLE_TEXT.map((x, i) => [i, x] as const), set: setStyle },
    groupBox: {},
  }
  return (
    <div className="tasks">
      <Buttons ok={() => void ok()} cancel={() => { setTd({ mode: null }); clearPreview(page); closeTask() }} okOff={phase === 'picking'} cancelOff={phase === 'picking'} />
      <TaskBox title={edit ? 'Edit Leader Line' : 'New Leader Line'} icon={icon('td-TechDraw_LeaderLine')}><QtForm form={TECHDRAW_FORMS.leader} bind={bind} /></TaskBox>
    </div>)
}

/** TaskRichAnno: create mode waits for a click on the page (the text goes there, the object is made at once: "Create Annotation");
 *  the text is edited in place and written as the text document's HTML. Cancel of a new one takes the step back. */
function RichTask({ page, name, edit }: { page: string; name: string; edit: boolean }) {
  const [obj, setObj] = useState<string | null>(edit ? name : null)
  const o = obj ? objOf(page, obj) : undefined
  const [frame, setFrame] = useState(o ? !!o.show_frame : false)
  const [maxw, setMaxw] = useState(o ? Number(o.max_width) : -1)
  const [lw, setLw] = useState(o ? Number(o.line_width) : 0.5)
  const [ls, setLs] = useState(o ? STYLES.indexOf(String(o.line_style)) : 1)
  const [lc, setLc] = useState(o ? hex(o.line_color as number[]) : '#000000')
  const made = useRef(false)
  const props = () => ({ show_frame: frame, max_width: maxw, line_width: lw, line_style: STYLES[ls], line_color: unhex(lc) })
  const step = edit ? 'Edit Annotation' : 'Create Annotation'
  const send = async (extra: Record<string, unknown>) => {
    if (!obj) return
    await applyTd(page, [{ op: 'richanno_edit', name: obj, ...props(), ...extra }], step, false, made.current)
    made.current = true
  }
  useEffect(() => {
    richPending = (html) => void send({ text: html })
    return () => { richPending = null }
  })
  useEffect(() => {
    if (edit && obj) { setRich({ page, name: obj, html: String(o?.anno_text ?? EMPTY_HTML), create: false, started: false }); openPage(page) }
    else if (!edit) {
      openPage(page)
      setTd({ mode: { kind: 'place', page, onPlace: place } })
    }
    return () => { setRich(null); setTd({ mode: null }) }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const place = async (p: [number, number]) => {
    setTd({ mode: null })
    const parent = name !== 'None' ? name : undefined
    const before = new Set(tdState().docs[page]?.objects.map((x) => x.name))
    const d = await applyTd(page, [{ op: 'richanno', at: p, text: EMPTY_HTML, ...(parent ? { parent } : {}), ...props() }], 'Create Annotation')
    const m = d?.objects.find((x) => !before.has(x.name))
    if (m) { made.current = true; setObj(m.name); setRich({ page, name: m.name, html: EMPTY_HTML, create: true, started: false }) }
  }
  const on = !!obj
  useEffect(() => { if (obj) void send({}) }, [frame, maxw, lw, ls, lc]) // eslint-disable-line react-hooks/exhaustive-deps
  const bind: Bindings = {
    leBaseView: { value: edit ? String(o?.anno_parent ?? 'None') : name },
    dsbMaxWidth: { value: maxw, suffix: ' mm', dec: 2, min: -1, max: 1e4, off: !on, set: setMaxw },
    gbFrame: { value: frame, off: !on, set: setFrame },
    dsbWidth: { value: lw, suffix: ' mm', dec: 2, min: 0, max: 1e3, off: !on || !frame, set: setLw },
    cFrameStyle: { value: ls, opts: STYLE_TEXT.map((x, i) => [i, x] as const), off: !on || !frame, set: setLs },
    cpFrameColor: { value: lc, off: !on || !frame, set: setLc },
  }
  const ok = () => { setRich(null); closeTask() }
  const cancel = () => { setRich(null); setTd({ mode: null }); closeTask(); if (!edit && made.current) void doUndo() }
  return (
    <div className="tasks">
      <Buttons ok={ok} cancel={cancel} okOff={!edit && !on} />
      <TaskBox title={edit ? 'Rich Text Editor' : 'Rich Text Creator'} icon={icon('td-TechDraw_RichTextAnnotation')}><QtForm form={TECHDRAW_FORMS.richanno} bind={bind} /></TaskBox>
    </div>)
}

type Side = { symbol: string; left: string; center: string; right: string }
const NO_SIDE: Side = { symbol: '', left: '', center: '', right: '' }
/** TaskWeldingSymbol: the arrow side's and the other side's symbol (SymbolChooser) and texts, flip, erase, field weld, all around,
 *  alternating weld and the tail text. OK makes the symbol and its two tiles ("Create Weld Symbol"); in edit, "Edit Weld Symbol". */
function WeldTask({ page, name, edit }: { page: string; name: string; edit: boolean }) {
  const doc = useTd((s) => s.docs[page])
  const w = edit ? doc?.objects.find((o) => o.name === name) : undefined
  const tiles = edit ? (doc?.objects.filter((o) => o.kind === 'DrawTileWeld' && o.tile_parent === name) ?? []) : []
  const side = (row: number): Side => { const t = tiles.find((x) => x.tile_row === row); return t ? { symbol: String(t.symbol_file ?? ''), left: String(t.left_text ?? ''), center: String(t.center_text ?? ''), right: String(t.right_text ?? '') } : NO_SIDE }
  const [arrow, setArrow] = useState<Side>(() => side(0))
  const [other, setOther] = useState<Side>(() => side(-1))
  const [flags, setFlags] = useState({ field: !!w?.field_weld, around: !!w?.all_around, alt: !!w?.alternating_weld })
  const [tail, setTail] = useState(String(w?.tail_text ?? ''))
  const [dir, setDir] = useState(WELD_DIR)
  const BLANK = 'Welding/blankTile.svg'
  const op = () => {
    const texts = (s: Side) => ({ left: s.left, center: s.center, right: s.right })
    const sd = (s: Side, always: boolean) => ({ ...texts(s), ...(s.symbol && s.symbol !== BLANK ? { symbol: s.symbol } : always ? { symbol: '' } : {}) })
    return edit ? { op: 'weld_edit', name, arrow: sd(arrow, false), other: sd(other, true), field_weld: flags.field, all_around: flags.around, alternating: flags.alt, tail_text: tail }
      : { op: 'weld', leader: name, arrow: sd(arrow, false), other: sd(other, true), field_weld: flags.field, all_around: flags.around, alternating: flags.alt, tail_text: tail }
  }
  useEffect(() => { void applyTd(page, [op()], undefined, true) }, [JSON.stringify([arrow, other, flags, tail])]) // eslint-disable-line react-hooks/exhaustive-deps
  const choose = async (which: 'arrow' | 'other') => {
    const p = await chooseSymbol(dir, which)
    if (!p) return
    if (which === 'arrow') setArrow((a) => ({ ...a, symbol: p })); else setOther((a) => ({ ...a, symbol: p }))
  }
  const symBtn = (s: Side) => (s.symbol && s.symbol !== BLANK && symbolUrl(s.symbol) ? <img src={symbolUrl(s.symbol)} width={32} height={32} alt="" /> : undefined)
  const bind: Bindings = {
    leArrowTextL: { value: arrow.left, set: (v: string) => setArrow({ ...arrow, left: v }) }, leArrowTextC: { value: arrow.center, set: (v: string) => setArrow({ ...arrow, center: v }) },
    leArrowTextR: { value: arrow.right, set: (v: string) => setArrow({ ...arrow, right: v }) },
    leOtherTextL: { value: other.left, set: (v: string) => setOther({ ...other, left: v }) }, leOtherTextC: { value: other.center, set: (v: string) => setOther({ ...other, center: v }) },
    leOtherTextR: { value: other.right, set: (v: string) => setOther({ ...other, right: v }) },
    pbArrowSymbol: { text: 'Symbol', node: symBtn(arrow), click: () => void choose('arrow') }, pbOtherSymbol: { text: 'Symbol', node: symBtn(other), click: () => void choose('other') },
    pbOtherErase: { click: () => setOther(NO_SIDE) },
    pbFlipSides: { click: () => { setArrow(other); setOther(arrow) } },
    cbFieldWeld: { value: flags.field, set: (v: boolean) => setFlags({ ...flags, field: v }) }, cbAllAround: { value: flags.around, set: (v: boolean) => setFlags({ ...flags, around: v }) },
    cbAltWeld: { value: flags.alt, set: (v: boolean) => setFlags({ ...flags, alt: v }) },
    leTailText: { value: tail, set: setTail },
    fcSymbolDir: { value: `${dir}/`, click: () => setDir((d) => (d === 'Welding/AWS' ? 'Welding/GOST' : 'Welding/AWS')) },
  }
  const ok = async () => { await applyTd(page, [op()], edit ? 'Edit Weld Symbol' : 'Create Weld Symbol'); clearPreview(page); closeTask() }
  return (
    <div className="tasks">
      <Buttons ok={() => void ok()} cancel={() => { clearPreview(page); closeTask() }} />
      <TaskBox title={edit ? 'Edit Welding Symbol' : 'Create Welding Symbol'} icon={icon('td-TechDraw_WeldSymbol')}><QtForm form={TECHDRAW_FORMS.weld} bind={bind} /></TaskBox>
    </div>)
}

// ── TaskSurfaceFinishSymbols ─────────────────────────────────────────────────────────────────────────────────────────
const RA = ['Ra50', 'Ra25', 'Ra12, 5', 'Ra6, 3', 'Ra3, 2', 'Ra1, 6', 'Ra0, 8', 'Ra0, 4', 'Ra0, 2', 'Ra0, 1', 'Ra0, 05', 'Ra0, 025']
const LAY = ['', '=', '⟂', 'X', 'M', 'C', 'R']
const GRADES = ['', 'N1', 'N2', 'N3', 'N4', 'N5', 'N6', 'N7', 'N8', 'N9', 'N10', 'N11']
/** TaskSurfaceFinishSymbols::baseSymbol: the six buttons' pictures. */
function baseIcon(i: number) {
  return (
    <svg width={50} height={64} viewBox="0 0 50 64" style={{ display: 'block' }}>
      <g fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
        <path d="M0 40L12 60L42 10" />
        {(i === 1 || i === 4) && <circle cx={12} cy={42} r={9} />}
        {(i === 2 || i === 5) && <path d="M0 40L24 40" />}
        {(i === 3 || i === 4 || i === 5) && <circle cx={42} cy={10} r={6} />}
      </g>
    </svg>)
}
function SurfaceTask({ page, owner }: { page: string; owner: string }) {
  const [icon_, setIcon] = useState(0)
  const [iso, setIso] = useState(true)
  const [method, setMethod] = useState('')
  const [ra, setRa] = useState(0)
  const [lay, setLay] = useState(0)
  const [addition, setAddition] = useState('')
  const [sample, setSample] = useState('')
  const [minR, setMinR] = useState(0)
  const [maxR, setMaxR] = useState(0)
  const [angle, setAngle] = useState('0')
  const op = () => ({ op: 'surface', owner, icon: icon_, iso, method, ra, lay: LAY[lay], addition, sample_length: sample, min_rough: GRADES[minR], max_rough: GRADES[maxR], angle: Number(angle) || 0 })
  const bind: Bindings = {
    pbIcon01: { node: baseIcon(0), click: () => setIcon(0) }, pbIcon02: { node: baseIcon(1), click: () => setIcon(1) }, pbIcon03: { node: baseIcon(2), click: () => setIcon(2) },
    pbIcon04: { node: baseIcon(3), click: () => setIcon(3) }, pbIcon05: { node: baseIcon(4), click: () => setIcon(4) }, pbIcon06: { node: baseIcon(5), click: () => setIcon(5) },
    leAngle: { value: angle, set: setAngle },
    rbISO: { value: iso, set: () => setIso(true) }, rbASME: { value: !iso, set: () => setIso(false) },
    graphicsView: { node: <SurfaceScene {...{ icon: icon_, iso, method, setMethod, ra, setRa, lay, setLay, addition, setAddition, sample, setSample, minR, setMinR, maxR, setMaxR }} /> },
  }
  const ok = async () => { await applyTd(page, [op()], 'Surface Finish Symbols'); closeTask() }
  return (
    <div className="tasks">
      <Buttons ok={() => void ok()} cancel={closeTask} />
      <TaskBox title="Surface Finish Symbols" icon={icon('td-TechDraw_SurfaceFinishSymbols')}><QtForm form={TECHDRAW_FORMS.surface} bind={bind} /></TaskBox>
    </div>)
}
type SceneP = { icon: number; iso: boolean; method: string; setMethod(v: string): void; ra: number; setRa(v: number): void; lay: number; setLay(v: number): void; addition: string
  setAddition(v: string): void; sample: string; setSample(v: string): void; minR: number; setMinR(v: number): void; maxR: number; setMaxR(v: number): void }
/** The graphics view of the panel: the symbol's picture with the editable fields where TaskSurfaceFinishSymbols puts them
 *  (QGraphicsProxyWidgets in scene units, about the view's centre). */
function SurfaceScene(p: SceneP) {
  const at = (x: number, y: number, w: number): React.CSSProperties => ({ position: 'absolute', left: x + 130, top: y + 150, width: w, height: 20, boxSizing: 'border-box' })
  const sel = (title: string, v: number, set: (v: number) => void, items: string[], x: number, y: number, w: number) => (
    <select title={title} value={v} onChange={(e) => set(Number(e.target.value))} style={at(x, y, w)}>{items.map((t, i) => <option key={i} value={i}>{t}</option>)}</select>)
  return (
    <div style={{ position: 'relative', width: 270, height: 200, margin: '0 auto' }} data-qf="surfaceScene">
      <div style={{ position: 'absolute', left: -50 + 130, top: -126 + 150, pointerEvents: 'none', zIndex: -1 }}>{baseIcon(p.icon)}</div>
      <div style={{ position: 'absolute', left: -8 + 130, top: -116 + 150, width: 98, height: 2, background: 'currentColor' }} />
      <input title="Method" value={p.method} onChange={(e) => p.setMethod(e.target.value)} style={at(2, -142, 90)} />
      <input title="Addition" value={p.addition} onChange={(e) => p.setAddition(e.target.value)} style={at(-110, -85, 25)} />
      {p.iso ? sel('Average roughness', p.ra, p.setRa, RA, 2, -113, 90)
        : <input title="Roughness sampling length" value={p.sample} onChange={(e) => p.setSample(e.target.value)} style={at(2, -113, 90)} />}
      {sel('Lay symbol', p.lay, p.setLay, LAY, -23, -85, 40)}
      {!p.iso && sel('Minimum roughness grade number', p.minR, p.setMinR, GRADES, -100, -118, 55)}
      {!p.iso && sel('Maximum roughness grade number', p.maxR, p.setMaxR, GRADES, -100, -143, 55)}
    </div>)
}

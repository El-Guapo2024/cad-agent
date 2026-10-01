// Std_DlgPreferences: DlgPreferences.ui / DlgPreferencesImp.cpp at FreeCAD main 3160daf1e2b6 — a
// modal "Preferences" window: the groups and their pages in a tree on the left (24px icons) with
// Reset under it, the page's title and "Search preferences…" over the page, OK / Apply / Cancel.
// The pages here are the ones that apply to these projects (resource.cpp registers FreeCAD's).
// Settings take effect as they change; Cancel puts back what was there when the dialog opened
// (or at the last Apply), which is what FreeCAD's deferred apply amounts to.
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { AXIS_COLOR_DEFAULTS, CORNER_POS, NAVICUBE_DEFAULTS, NOTIFY_DEFAULTS, getState, saved, setState, useStore } from './store'
import { NAV_DEFAULTS } from './nav'
import { ContextMenu, type Entry } from './chrome'
import { messageBox } from './msgbox'
import { setTreeOption } from './actions'
import { setUnits } from './commands'
import { PrefsPage } from './panels'
import { VIEW } from './theme'
import { BACKGROUND_DEFAULTS, type BackgroundMode, type BackgroundPrefs } from './background'
import { cls } from './panels'

const GROUPS: [string, string, string[]][] = [
  ['General', 'preferences-general', ['General', 'Selection', 'Notification Area', 'Report View']],
  ['Display', 'preferences-display', ['3D View', 'Navigation', 'Colors', 'Transform snap']],
  ['Python', 'preferences-python', ['Macro']],
]
const hex = (n: number) => '#' + n.toString(16).padStart(6, '0')

/** DlgSettingsSelection.ui: Viewport Selection Behavior and Tree Selection Behavior. */
function SelectionPage() {
  const tree = useStore((s) => s.tree)
  const check = (label: string, on: boolean, f?: (v: boolean) => void, tip?: string) => (
    <label className="tcheck" title={tip}><input type="checkbox" checked={on} disabled={!f} onChange={(e) => f?.(e.target.checked)} />{label}</label>)
  return (
    <div className="pref-content">
      <fieldset className="tgroup"><legend>Viewport Selection Behavior</legend>
        <div className="tfield"><span className="color-chip" style={{ background: hex(VIEW.select) }} />{check('Enable selection', true, undefined, 'Enable selection, highlighted with specified color')}</div>
        <label className="tfield"><span>Radius</span><input type="number" className="qsb" value={5} disabled title="Area for selecting elements in the 3D view. Larger value eases the selection of small elements but can make the selection less precise." /></label>
        <div className="tfield"><span className="color-chip" style={{ background: hex(VIEW.preselect) }} />{check('Enable preselection', true, undefined, 'Enable preselection, highlighted with specified color')}</div>
        {check('Preselect the object in the 3D view when hovering the cursor over the tree item', tree.preSelection, (v) => setTreeOption('preSelection', v))}
      </fieldset>
      <fieldset className="tgroup"><legend>Tree Selection Behavior</legend>
        {check('Auto switch to the 3D view containing the selected item', tree.syncView, (v) => setTreeOption('syncView', v), 'Selecting an item in the Tree View automatically activates its document and switches to its 3D view.')}
        {check('Auto expand tree item when the corresponding object is selected in the 3D view', tree.syncSelection, (v) => setTreeOption('syncSelection', v), 'Locates and reveals the selected object within the tree hierarchy. Prevents manual scrolling in deep, complex document structures.')}
        {check('Record selection in tree view in order to go back/forward using navigation button', tree.recordSelection, (v) => setTreeOption('recordSelection', v), "Enables selection history. Use 'Back' and 'Forward' navigation to toggle between previously selected objects without re-searching the tree.")}
        {check('Add checkboxes for selection in document tree', false, undefined, 'Provides persistent selection toggles for each item. Simplifies batch operations and complex multi-selection without holding modifier keys (Ctrl/Shift).')}
      </fieldset>
    </div>
  )
}
/** A PrefColorButton: the colour, a native picker over it; disabled with no setter. */
function ColorButton({ value, set, tip }: { value: string; set?: (v: string) => void; tip?: string }) {
  return (
    <label className={cls('qbtn color-btn', !set && 'disabled')} title={tip}><span className="color-chip" style={{ background: value }} />
      <input type="color" value={value} disabled={!set} onChange={(e) => set?.(e.target.value)} /></label>)
}
/** DlgSettingsViewColor.ui: Background Color, Tree View, Color Bar. The radios swap the simple
 *  colour for the gradient's (setGradientColorVisibility), the labels follow the gradient's kind,
 *  Switch swaps the first and last colours, Middle color enables the middle one. */
function ColorsPage() {
  const bg = useStore((s) => s.background), editColor = useStore((s) => s.treeEditColor)
  const set = (v: Partial<BackgroundPrefs>) => { const background = { ...getState().background, ...v }; saved.set('background', background); setState({ background }) }
  const gradient = bg.mode !== 'simple'
  const [l1, l2, l3] = bg.mode === 'radial' ? ['Central', 'Midway', 'End'] : ['Top', 'Middle', 'Bottom']
  const radio = (label: string, mode: BackgroundMode, tip: string) => (
    <label className="tcheck" title={tip}><input type="radio" checked={bg.mode === mode} onChange={() => set({ mode })} />{label}</label>)
  const na = (what: string) => `n/a: ${what}`
  return (
    <div className="pref-content">
      <fieldset className="tgroup" title="Background color for the model view"><legend>Background Color</legend>
        <div className="bg-modes">
          {radio('Simple color', 'simple', 'Background will have the selected color')}
          {radio('Linear gradient', 'linear', 'Background will have the selected color gradient')}
          {radio('Radial gradient', 'radial', 'Background will have the selected color gradient')}
          {!gradient && <ColorButton value={bg.color} set={(color) => set({ color })} tip="Background will have the selected color" />}
        </div>
        {gradient && (
          <div className="bg-grid">
            <span /><span>{l1}</span><ColorButton value={bg.top} set={(top) => set({ top })} /><span />
            <button className="qbtn" title="Switches the colors of the gradient" onClick={() => set({ top: bg.bottom, bottom: bg.top })}>Switch</button>
            <span className={cls(!bg.useMid && 'disabled')}>{l2}</span><ColorButton value={bg.mid} set={bg.useMid ? (mid) => set({ mid }) : undefined} />
            <label className="tcheck" title="Color gradient will get the selected color as middle color"><input type="checkbox" checked={bg.useMid} onChange={(e) => set({ useMid: e.target.checked })} />Middle color</label>
            <span /><span>{l3}</span><ColorButton value={bg.bottom} set={(bottom) => set({ bottom })} /><span />
          </div>)}
      </fieldset>
      <fieldset className="tgroup"><legend>Tree View</legend>
        <div className="pref-grid">
          <span>Object being edited</span>
          <ColorButton value={editColor} set={(v) => { saved.set('treeEditColor', v); setState({ treeEditColor: v }) }} tip="Background color for objects in the tree view that are currently edited" />
          <span className="disabled">Active container object</span>
          <ColorButton value="#5bb413" tip={na('no active containers (a part or a body) here')} />
        </div>
      </fieldset>
      <fieldset className="tgroup"><legend>Color Bar</legend>
        <div className="pref-grid">
          <span className="disabled">Label text color</span><ColorButton value="#212529" tip={na('no colour bars here (Mesh and FEM results)')} />
          <span className="disabled">Label text size</span><input type="number" className="qsb" value={13} disabled title={na('no colour bars here (Mesh and FEM results)')} />
        </div>
      </fieldset>
    </div>
  )
}
/** What each page's settings go back to (Reset Page / Group / All): the store's own defaults. */
const DEFAULTS: Record<string, Record<string, unknown>> = {
  General: { units: { schema: 0, decimals: 2, denominator: 8 }, toolbarIconSize: 24, recentFilesSize: 4 },
  Selection: { tree: { syncView: true, syncSelection: true, preSelection: true, recordSelection: true } },
  'Notification Area': { notifyPrefs: NOTIFY_DEFAULTS },
  '3D View': { corner: { show: true, size: 10 }, axes: false, axisColors: AXIS_COLOR_DEFAULTS, showFPS: false },
  Navigation: { nav: 'cad', animate: true, cube: true, navPrefs: NAV_DEFAULTS, homeView: 'Trimetric', newDocCameraScale: 100,
    naviCube: NAVICUBE_DEFAULTS, cubePos: CORNER_POS[1], rotationCenter: { size: 5, color: '#ff0000', alpha: 0.2 }, disableTouchTilt: true },
  Colors: { background: BACKGROUND_DEFAULTS, treeEditColor: '#00abff' },
  'Transform snap': { snap: { mm: 1, deg: 5 } },
  Macro: { recordGuiCommands: true, guiAsComment: true },
  'Report View': { reportShow: { msg: true, log: true, warn: true, err: true, critical: true }, 'report.showOn': {}, 'report.timecode': true, reportTimecode: true, 'report.colors': {} },
}
function resetPages(pages: string[]) {
  for (const p of pages) for (const [k, v] of Object.entries(DEFAULTS[p] ?? {})) {
    saved.set(k, v)
    if (k === 'units') setUnits(v as never)
    else if (k in getState()) setState({ [k]: v } as never) // the rest (snap, recentFilesSize) live in `saved` only
  }
  applyReportColors()
}
/** DlgSettingsReportView.ui: Output, Colors, Python Interpreter. */
const REPORT_COLORS = { msg: '#000000', log: '#0000ff', warn: '#ffaa00', err: '#ff0000' }
export function applyReportColors() {
  const c = { ...REPORT_COLORS, ...saved.get<Partial<typeof REPORT_COLORS>>('report.colors', {}) }
  for (const [k, v] of Object.entries(c)) document.documentElement.style.setProperty(`--r-${k}`, v)
}
function ReportViewPage() {
  const show = useStore((s) => s.reportShow), timecode = useStore((s) => s.reportTimecode)
  const [showOn, setShowOnRaw] = useState(() => ({ msg: false, log: false, warn: false, err: false, ...saved.get<Record<string, boolean>>('report.showOn', {}) }))
  const [colors, setColors] = useState(() => ({ ...REPORT_COLORS, ...saved.get<Partial<typeof REPORT_COLORS>>('report.colors', {}) }))
  const record = (l: 'msg' | 'log' | 'warn' | 'err', on: boolean) => { const reportShow = { ...getState().reportShow, [l]: on }; saved.set('reportShow', reportShow); setState({ reportShow }) }
  const showOnSet = (l: 'msg' | 'log' | 'warn' | 'err', on: boolean) => { const v = { ...showOn, [l]: on }; setShowOnRaw(v); saved.set('report.showOn', v) }
  const color = (l: keyof typeof REPORT_COLORS, v: string) => { const c = { ...colors, [l]: v }; setColors(c); saved.set('report.colors', c); applyReportColors() }
  const check = (label: string, on: boolean, f: (v: boolean) => void) => <label className="tcheck"><input type="checkbox" checked={on} onChange={(e) => f(e.target.checked)} />{label}</label>
  return (
    <div className="pref-content">
      <fieldset className="tgroup"><legend>Output</legend>
        {check('Record normal messages', show.msg, (v) => record('msg', v))}
        {check('Record log messages', show.log, (v) => record('log', v))}
        {check('Record warnings', show.warn, (v) => record('warn', v))}
        {check('Record error messages', show.err, (v) => record('err', v))}
        {check('Show report view on error', showOn.err, (v) => showOnSet('err', v))}
        {check('Show report view on warning', showOn.warn, (v) => showOnSet('warn', v))}
        {check('Show report view on normal message', showOn.msg, (v) => showOnSet('msg', v))}
        {check('Show report view on log message', showOn.log, (v) => showOnSet('log', v))}
        {check('Include a timecode for each entry', timecode, (v) => { saved.set('report.timecode', v); setState({ reportTimecode: v }) })}
      </fieldset>
      <fieldset className="tgroup"><legend>Colors</legend>
        {([['Normal messages', 'msg'], ['Log messages', 'log'], ['Warnings', 'warn'], ['Errors', 'err']] as const).map(([label, l]) => (
          <label key={l} className="tfield"><span>{label}</span><label className="qbtn color-btn"><span className="color-chip" style={{ background: colors[l] }} />
            <input type="color" value={colors[l]} onChange={(e) => color(l, e.target.value)} /></label></label>))}
      </fieldset>
      <fieldset className="tgroup"><legend>Python Interpreter</legend>
        <label className="tcheck" title="n/a: there is no Python interpreter here"><input type="checkbox" checked disabled />Redirect internal Python output to report view</label>
        <label className="tcheck" title="n/a: there is no Python interpreter here"><input type="checkbox" checked disabled />Redirect internal Python errors to report view</label>
      </fieldset>
    </div>
  )
}
const page = (name: string): ReactNode => (name === 'Selection' ? <SelectionPage /> : name === 'Report View' ? <ReportViewPage /> : name === 'Colors' ? <ColorsPage /> : <PrefsPage page={name} />)

/** What Cancel puts back: the app's own saved settings and the store fields the pages edit. */
const PREF_KEYS = ['nav', 'animate', 'cube', 'navPrefs', 'homeView', 'newDocCameraScale', 'units', 'corner', 'axes', 'axisColors',
  'showFPS', 'naviCube', 'cubePos', 'rotationCenter', 'disableTouchTilt', 'recordGuiCommands', 'guiAsComment', 'notifyPrefs', 'tree',
  'background', 'treeEditColor'] as const
function snapshot() {
  const s = getState() as unknown as Record<string, unknown>
  const saved: Record<string, string | null> = {}
  try { for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i)!; if (k.startsWith('cadui.')) saved[k] = localStorage.getItem(k) } } catch { /* no storage */ }
  return { state: Object.fromEntries(PREF_KEYS.map((k) => [k, s[k]])), saved }
}
function restore(snap: ReturnType<typeof snapshot>) {
  try {
    for (const k of Object.keys(localStorage)) if (k.startsWith('cadui.') && !(k in snap.saved)) localStorage.removeItem(k)
    for (const [k, v] of Object.entries(snap.saved)) if (v !== null) localStorage.setItem(k, v)
  } catch { /* no storage */ }
  const { units, ...rest } = snap.state as Record<string, unknown>
  setState(rest as never)
  setUnits(units as never)
}

/** DlgPreferencesImp::onButtonResetClicked: Reset Page '…', Reset Group '…', Reset All (asks first). */
function resetEntries(cur: string, done: () => void): Entry[] {
  const group = GROUPS.find(([, , ps]) => ps.includes(cur))!
  return [
    { label: `Reset Page '${cur}'`, title: `Resets the user settings for the page '${cur}'`, onSelect: () => { resetPages([cur]); done() } },
    { label: `Reset Group '${group[0]}'`, title: `Resets the user settings for the group '${group[0]}'`, onSelect: () => { resetPages(group[2]); done() } },
    { label: 'Reset All', title: 'Resets the user settings entirely', onSelect: () => {
      void messageBox('question', 'Clear User Settings', 'Clear all your user settings?\n\nAll settings will be cleared.', ['Yes', 'No'])
        .then((b) => { if (b === 'Yes') { resetPages(Object.keys(DEFAULTS)); done() } })
    } },
  ]
}

export function PreferencesDialog() {
  const open = useStore((s) => s.prefsOpen)
  const [cur, setCur] = useState('General')
  const [query, setQuery] = useState('')
  const snap = useRef<ReturnType<typeof snapshot> | null>(null)
  const index = useRef<HTMLDivElement>(null)
  const [hits, setHits] = useState<{ page: string; text: string }[]>([])
  const [resetAt, setResetAt] = useState<{ x: number; y: number } | null>(null)
  const [gen, setGen] = useState(0) // remounts the page after a reset (Transform snap keeps its own state)
  useEffect(() => { if (open) { snap.current = snapshot(); setQuery('') } }, [open])
  // DlgPreferencesImp's search: every label on every page, shown as "page" over the text.
  useEffect(() => {
    const q = query.trim().toLowerCase()
    if (!q || !index.current) { setHits([]); return }
    const out: { page: string; text: string }[] = []
    index.current.querySelectorAll<HTMLElement>('[data-page]').forEach((p) => {
      p.querySelectorAll('label, legend, span').forEach((el) => {
        const t = (el.childNodes.length && [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join('').trim()) || ''
        if (t && t.toLowerCase().includes(q) && !out.some((h) => h.page === p.dataset.page && h.text === t)) out.push({ page: p.dataset.page!, text: t })
      })
    })
    setHits(out.slice(0, 30))
  }, [query])
  const pages = useMemo(() => GROUPS.flatMap(([, , ps]) => ps), [])
  if (!open) return null
  const close = () => setState({ prefsOpen: false })
  return (
    <div className="msgbox-back" onKeyDown={(e) => { if (e.key === 'Escape') { restore(snap.current!); close() } }}>
      <div className="pref-dlg" role="dialog" aria-label="Preferences">
        <div className="msgbox-title">Preferences</div>
        <div className="pref-body">
          <div className="pref-side">
            <div className="pref-tree">
              {GROUPS.map(([g, icon, ps]) => (
                <div key={g}>
                  <div className="pref-group"><img src={`./freecad-icons/${icon}.svg`} width={24} height={24} alt="" />{g}</div>
                  {ps.map((p) => <div key={p} className={cur === p ? 'pref-item sel' : 'pref-item'} onClick={() => setCur(p)}>{p}</div>)}
                </div>
              ))}
            </div>
            <button className="qbtn" onClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); setResetAt({ x: r.left, y: r.top - 3 * 25 - 10 }) }}>Reset</button>
            {resetAt && <ContextMenu at={resetAt} onClose={() => setResetAt(null)} entries={resetEntries(cur, () => setGen((g) => g + 1))} />}
          </div>
          <div className="pref-main">
            <div className="pref-head">
              <span className="pref-header">{cur}</span>
              <span className="pref-search">
                <input type="search" placeholder="Search preferences…" value={query} onChange={(e) => setQuery(e.target.value)} />
                {hits.length > 0 && <div className="pref-hits">{hits.map((h, i) => (
                  <div key={i} className="pref-hit" onClick={() => { setCur(h.page); setQuery('') }}><b>{h.page}</b><span>{h.text}</span></div>))}</div>}
              </span>
            </div>
            <div className="pref-page" key={gen}>{page(cur)}</div>
          </div>
        </div>
        <div className="pref-buttons">
          <button className="qbtn default" onClick={close}>OK</button>
          <button className="qbtn" onClick={() => { snap.current = snapshot() }}>Apply</button>
          <button className="qbtn" onClick={() => { restore(snap.current!); close() }}>Cancel</button>
        </div>
        {/* The search index: every page rendered off screen. */}
        <div ref={index} className="pref-index" aria-hidden>{pages.map((p) => <div key={p} data-page={p}>{page(p)}</div>)}</div>
      </div>
    </div>
  )
}

// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Gui/Dialogs/DlgPreferencesImp.cpp: 2002 Jürgen Riegel; 2023 FreeCAD Project Association
//   src/Gui/resource.cpp: 2004 Werner Mayer
//   No copyright line in the file: src/Gui/Dialogs/DlgPreferences.ui, src/Gui/Stylesheets/FreeCAD.qss
// Std_DlgPreferences: DlgPreferences.ui / DlgPreferencesImp.cpp at FreeCAD main 3160daf1e2b6 — a
// modal "Preferences" window: the groups and their pages in a tree on the left (24px icons) with
// Reset under it, the page's title and "Search preferences…" over the page, OK / Apply / Cancel.
// The pages here are the ones that apply to these projects (resource.cpp registers FreeCAD's);
// each is a component of prefs-pages.tsx.
// Settings take effect as they change; Cancel puts back what was there when the dialog opened
// (or at the last Apply), which is what FreeCAD's deferred apply amounts to.
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { AXIS_COLOR_DEFAULTS, CORNER_POS, NAVICUBE_DEFAULTS, NOTIFY_DEFAULTS, SEL_DEFAULTS, TREE_UI_DEFAULTS, EDITOR_COLORS, OVERLAY_DEFAULTS, WB_DEFAULTS, getState, saved, setState, useStore } from './store'
import { NAV_DEFAULTS } from './nav'
import { ContextMenu, type Entry } from './chrome'
import { messageBox } from './msgbox'
import { setEditorPrefs } from './actions'
import { setHomeView, setUnits } from './commands'
import { BACKGROUND_DEFAULTS } from './background'
import { LIGHT_DEFAULTS } from './lights'
import {
  AdvancedPage, CachePage, ColorsPage, DocumentPage, EditorPage, GeneralPage, getServerPrefs, KeyboardPage, LightSourcesPage, loadServerPrefs, MacroPage, NavigationPage,
  NotificationAreaPage, PdfPage, PythonConsolePage, ReportViewPage, SelectionPage, setServerPref, TransformSnapPage, UIPage, View3DPage, WorkbenchesPage, applyReportColors,
} from './prefs-pages'
export { AccelEdit, applyReportColors, checkCache } from './prefs-pages' // App.tsx and customize.tsx take them from here

const GROUPS: [string, string, string[]][] = [
  ['General', 'preferences-general', ['General', 'Document', 'Selection', 'Keyboard', 'Cache', 'Notification Area', 'Report View']],
  ['Display', 'preferences-display', ['3D View', 'Light Sources', 'UI', 'Navigation', 'Colors', 'Advanced', 'Transform snap']],
  ['Workbenches', 'preferences-workbenches', ['Available Workbenches']],
  ['Import-Export', 'preferences-import-export', ['PDF']],
  ['Python', 'preferences-python', ['Macro', 'Python General', 'Editor']],
]

/** Page ids that FreeCAD shows under another name: DlgSettingsPythonConsole's title is "General". */
const LABEL: Record<string, string> = { 'Python General': 'General' }
const label = (p: string) => LABEL[p] ?? p
/** What each page's settings go back to (Reset Page / Group / All): the store's own defaults. */
const DEFAULTS: Record<string, Record<string, unknown>> = {
  General: { units: { schema: 0, decimals: 2, denominator: 8 }, toolbarIconSize: 24, recentFilesSize: 4 },
  Document: { 'server:MaxUndoSize': 20 },
  Keyboard: { shortcuts: {}, shortcutTimeout: 300 },
  Cache: { 'server:CacheLimit': 500, 'server:CachePeriod': 2 },
  Selection: { selPrefs: SEL_DEFAULTS, tree: { syncView: true, syncSelection: true, preSelection: true, recordSelection: true, checkBoxes: false } },
  'Notification Area': { notifyPrefs: NOTIFY_DEFAULTS },
  '3D View': { corner: { show: true, size: 10 }, axes: false, axisColors: AXIS_COLOR_DEFAULTS, showFPS: false },
  'Light Sources': { lights: LIGHT_DEFAULTS },
  UI: { treeUI: TREE_UI_DEFAULTS },
  Navigation: { nav: 'cad', animate: true, cube: true, navPrefs: NAV_DEFAULTS, homeView: null, newDocCameraScale: 100,
    naviCube: NAVICUBE_DEFAULTS, cubePos: CORNER_POS[1], rotationCenter: { size: 5, color: '#ff0000', alpha: 0.2 }, disableTouchTilt: true },
  Colors: { background: BACKGROUND_DEFAULTS, treeEditColor: '#00abff' },
  Advanced: { overlayPrefs: OVERLAY_DEFAULTS },
  'Transform snap': { snap: { mm: 1, deg: 5 } },
  'Available Workbenches': { wbPrefs: WB_DEFAULTS },
  Macro: { recordGuiCommands: true, guiAsComment: true, scriptToPyConsole: true },
  'Python General': { 'editor:wordWrap': true, 'editor:consoleBlock': false, 'editor:saveHistory': false },
  Editor: { 'editor:blockCursor': false, 'editor:tabSize': 4, 'editor:indentSize': 4, 'editor:spaces': true, 'editor:font': 'ui-monospace', 'editor:fontSize': 10, 'editor:colors': EDITOR_COLORS },
  'Report View': { reportShow: { msg: true, log: true, warn: true, err: true, critical: true }, 'report.showOn': {}, 'report.timecode': true, reportTimecode: true, 'report.colors': {} },
}
function resetPages(pages: string[]) {
  for (const p of pages) for (const [k, v] of Object.entries(DEFAULTS[p] ?? {})) {
    if (k.startsWith('server:')) { setServerPref(k.slice(7), v as number); continue }
    if (k.startsWith('editor:')) { setEditorPrefs({ [k.slice(7)]: v }); continue } // the two pages share one setting
    if (v === null) saved.remove(k) // a parameter that is unset by default (RemoveASCII): not stored as a value
    else saved.set(k, v)
    if (k === 'units') setUnits(v as never)
    else if (k in getState()) setState({ [k]: v } as never) // the rest (snap, recentFilesSize) live in `saved` only
  }
  applyReportColors()
}
const PAGES: Record<string, () => ReactNode> = {
  General: () => <GeneralPage />, Document: () => <DocumentPage />, Selection: () => <SelectionPage />, Keyboard: () => <KeyboardPage />, Cache: () => <CachePage />,
  'Notification Area': () => <NotificationAreaPage />, 'Report View': () => <ReportViewPage />,
  '3D View': () => <View3DPage />, 'Light Sources': () => <LightSourcesPage />, UI: () => <UIPage />, Navigation: () => <NavigationPage />, Colors: () => <ColorsPage />,
  Advanced: () => <AdvancedPage />, 'Transform snap': () => <TransformSnapPage />,
  'Available Workbenches': () => <WorkbenchesPage />, PDF: () => <PdfPage />,
  Macro: () => <MacroPage />, 'Python General': () => <PythonConsolePage />, Editor: () => <EditorPage />,
}
const page = (name: string): ReactNode => PAGES[name]()

/** What Cancel puts back: the app's own saved settings and the store fields the pages edit. */
const PREF_KEYS = ['nav', 'animate', 'cube', 'navPrefs', 'homeView', 'newDocCameraScale', 'units', 'corner', 'axes', 'axisColors',
  'showFPS', 'naviCube', 'cubePos', 'rotationCenter', 'disableTouchTilt', 'recordGuiCommands', 'guiAsComment', 'notifyPrefs', 'tree',
  'background', 'treeEditColor', 'lights', 'selPrefs', 'treeUI', 'editorPrefs', 'overlayPrefs', 'shortcuts', 'shortcutTimeout', 'wbPrefs', 'scriptToPyConsole',
  'reportShow', 'reportTimecode'] as const
function snapshot() {
  const s = getState() as unknown as Record<string, unknown>
  const saved: Record<string, string | null> = {}
  try { for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i)!; if (k.startsWith('cadui.')) saved[k] = localStorage.getItem(k) } } catch { /* no storage */ }
  return { state: Object.fromEntries(PREF_KEYS.map((k) => [k, s[k]])), saved, server: { ...getServerPrefs() } }
}
function restore(snap: ReturnType<typeof snapshot>) {
  try {
    for (const k of Object.keys(localStorage)) if (k.startsWith('cadui.') && !(k in snap.saved)) localStorage.removeItem(k)
    for (const [k, v] of Object.entries(snap.saved)) if (v !== null) localStorage.setItem(k, v)
  } catch { /* no storage */ }
  for (const [k, v] of Object.entries(snap.server)) if (getServerPrefs()[k] !== v) setServerPref(k, v)
  const { units, ...rest } = snap.state as Record<string, unknown>
  setState(rest as never)
  setUnits(units as never)
  applyReportColors()      // the Report view's colours are CSS variables set from the saved setting
}

/** DlgPreferencesImp::applyChanges: OK and Apply call saveSettings() on every page, so a page's parameter that nothing has set yet is
 *  written with what the page shows. The one that matters here is the Navigation page's Default camera orientation
 *  (NewDocumentCameraOrientation): unset it makes Home look from the Top, written it is what the combo shows, Trimetric. */
function saveSettings() {
  if (getState().homeView === null) setHomeView('Trimetric')
}

/** DlgPreferencesImp::onButtonResetClicked: Reset Page '…', Reset Group '…', Reset All (asks first). */
function resetEntries(cur: string, done: () => void): Entry[] {
  const group = GROUPS.find(([, , ps]) => ps.includes(cur))!
  return [
    { label: `Reset Page '${label(cur)}'`, title: `Resets the user settings for the page '${label(cur)}'`, onSelect: () => { resetPages([cur]); done() } },
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
  // Which groups of the tree show their pages: the one the page is in, and the ones the person opened or closed (DlgPreferencesImp
  // onStackWidgetChange collapses the others, except those the person expanded).
  const [opened, setOpened] = useState<Record<string, boolean>>({})
  const snap = useRef<ReturnType<typeof snapshot> | null>(null)
  const index = useRef<HTMLDivElement>(null)
  const [hits, setHits] = useState<{ page: string; text: string }[]>([])
  const [resetAt, setResetAt] = useState<{ x: number; y: number } | null>(null)
  const [gen, setGen] = useState(0) // remounts the page after a reset (Transform snap keeps its own state)
  // The page's own settings are taken now; the server's when they arrive (as they were then:
  // a page edit sends its own request, so it can't be what this reply holds).
  useEffect(() => {
    if (!open) return
    snap.current = snapshot(); setQuery('')
    const mine = snap.current
    void loadServerPrefs().then((p) => { if (p && snap.current === mine) mine.server = { ...p } })
  }, [open])
  // DlgPreferencesImp's search: every label on every page, shown as "group/page" over the text.
  useEffect(() => {
    const q = query.trim().toLowerCase()
    if (!q || !index.current) { setHits([]); return }
    const out: { page: string; text: string }[] = []
    index.current.querySelectorAll<HTMLElement>('[data-page]').forEach((p) => {
      p.querySelectorAll('label, button, span, .qf-gb-title').forEach((el) => {
        const t = (el.childNodes.length && [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join('').trim()) || ''
        if (t && t.toLowerCase().includes(q) && !out.some((h) => h.page === p.dataset.page && h.text === t)) out.push({ page: p.dataset.page!, text: t })
      })
    })
    setHits(out.slice(0, 30))
  }, [query])
  const pages = useMemo(() => GROUPS.flatMap(([, , ps]) => ps), [])
  if (!open) return null
  const close = () => setState({ prefsOpen: false })
  const groupOf = (p: string) => GROUPS.find(([, , ps]) => ps.includes(p))![0]
  const shows = (g: string) => opened[g] ?? g === groupOf(cur)
  const go = (p: string) => { setCur(p); setOpened((o) => { const n = { ...o }; delete n[groupOf(p)]; return n }) }
  return (
    <div className="msgbox-back" onKeyDown={(e) => { if (e.key === 'Escape') { restore(snap.current!); close() } }}>
      <div className="pref-dlg" role="dialog" aria-label="Preferences">
        <div className="msgbox-title">Preferences</div>
        <div className="pref-body">
          <div className="pref-side">
            <div className="pref-tree" role="tree">
              {GROUPS.map(([g, icon, ps]) => (
                <div key={g}>
                  <div className="pref-group" role="treeitem" aria-expanded={shows(g)} onClick={() => go(ps[0])}>
                    <span className={shows(g) ? 'pref-arrow open' : 'pref-arrow'} onClick={(e) => { e.stopPropagation(); setOpened((o) => ({ ...o, [g]: !shows(g) })) }} />
                    <img src={`./freecad-icons/${icon}.svg`} width={24} height={24} alt="" /><span>{g}</span>
                  </div>
                  {ps.map((p) => <div key={p} role="treeitem" hidden={!shows(g)} className={cur === p ? 'pref-item sel' : 'pref-item'} onClick={() => go(p)}>{label(p)}</div>)}
                </div>
              ))}
            </div>
            <button className="qbtn" onClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); setResetAt({ x: r.left, y: r.top - 3 * 25 - 10 }) }}>Reset</button>
            {resetAt && <ContextMenu at={resetAt} onClose={() => setResetAt(null)} entries={resetEntries(cur, () => setGen((g) => g + 1))} />}
          </div>
          <div className="pref-main">
            <div className="pref-head">
              <span className="pref-header">{label(cur)}</span>
              <span className="pref-search">
                <input type="search" placeholder="Search preferences…" value={query} onChange={(e) => setQuery(e.target.value)} />
                {hits.length > 0 && <div className="pref-hits">{hits.map((h, i) => (
                  <div key={i} className="pref-hit" onClick={() => { go(h.page); setQuery('') }}><b>{groupOf(h.page)}/{label(h.page)}</b><span>{h.text}</span></div>))}</div>}
              </span>
            </div>
            <div className="pref-scroll"><div className="pref-page" key={gen}>{page(cur)}</div></div>
            <div className="pref-buttons">
              <button className="qbtn" onClick={() => { saveSettings(); snap.current = snapshot() }}>Apply</button>
              <span className="pref-gap" />
              <button className="qbtn" onClick={() => { restore(snap.current!); close() }}>Cancel</button>
              <button className="qbtn default" onClick={() => { saveSettings(); close() }}>OK</button>
            </div>
          </div>
        </div>
        {/* The search index: every page rendered off screen. */}
        <div ref={index} className="pref-index" aria-hidden>{pages.map((p) => <div key={p} data-page={p}>{page(p)}</div>)}</div>
      </div>
    </div>
  )
}

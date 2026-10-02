// FreeCAD's File menu: CommandDoc.cpp's document commands plus CommandWindow.cpp's
// Std_CloseActiveWindow/Std_CloseAllWindows (Workbench.cpp puts those two in File, not Windows, at
// this commit). There's no local filesystem to open from a browser tab and no Save step (every
// edit already writes straight to its file), so New/Open/Save/Revert are reinterpreted onto the
// `cad` CLI and this app's own project list rather than ported one for one; see fileEntries below
// for exactly what maps to what.
import { useState } from 'react'
import { api, resultText, type CadResult } from './api'
import { clearRecentFiles, closeActiveWindow, closeAllWindows, closeTask, getView, hasOpenWindow, loadProjects, openProject, openTask, recentFiles } from './actions'
import { getState, report, saved, useStore } from './store'
import { messageBox } from './msgbox'
import { QComboBox } from './combo'
import { cls, TaskBox } from './panels'
import { documentInfo, exportPart } from './commands'
import { exportPage } from './agentwb'
import type { Entry } from './chrome'

const msg = (e: unknown) => (e instanceof Error ? e.message : String(e))

/** Std_Print / Std_PrintPreview / Std_PrintPdf (CommandDoc.cpp): FreeCAD prints, previews or
 *  PDF-exports the active view. This app has exactly one view type, the 3D view, so all three
 *  open its current image on a fresh tab and hand it to the browser's own print dialog — which
 *  previews before printing, and whose "Save as PDF" destination covers Export PDF too. */
export function printView() {
  const v = getView(), slug = getState().slug
  if (!v || !slug) return
  const { w, h } = v.viewPixels()
  const url = v.renderImage(w, h, 'Current', 'image/png')
  const win = window.open('', '_blank')
  if (!win) return report('warn', 'Print: the browser blocked the new tab; allow pop-ups to print')
  win.document.write(
    `<!doctype html><title>${slug}</title><style>body{margin:0}img{display:block;max-width:100%}</style>`
    + `<img src="${url}" alt="${slug}" onload="window.print()">`,
  )
  win.document.close()
}

/** The File menu (Workbench.cpp's "&File"), mapped onto `cad`: New Document/Open…/Open Recent
 *  stand in for FreeCAD's own document dialogs; Close/Close All move here from the Windows menu
 *  (at this commit Workbench.cpp's own Windows menu has no Close entries, unlike older FreeCAD);
 *  Save/Save As/Save a Copy/Save All/Revert carry FreeCAD's labels and shortcuts but stay disabled
 *  — every edit here (`cad set`/`place`/…) writes straight to its file, so there is never an
 *  unsaved document to save or a saved one to revert to; Import/Export are ours (bought parts;
 *  STEP/STL/Review page) under FreeCAD's labels; Merge Document is n/a (there's only ever one
 *  document); Exit is disabled (a browser tab can't quit the app). */
export function fileEntries(): Entry[] {
  const { slug, selected } = getState()
  const open = hasOpenWindow()
  const recent = recentFiles()
  return [
    { label: 'New Document', kbd: '⌘N', icon: 'new', onSelect: () => openTask('newDocument', '') }, // Std_New
    { label: 'Open…', kbd: '⌘O', icon: 'open', onSelect: () => openTask('openDocument', '') }, // Std_Open
    {
      label: 'Open Recent', icon: 'recent', // Std_RecentFiles: FreeCAD's numbered format ("1 name"…), 4 entries by default
      // then a separator and Clear Recent Files (QMenu hides the separator while the list is empty).
      sub: [...recent.map((s, i): Entry => ({ label: `${i + 1} ${s}`, onSelect: () => openProject(s) })), ...(recent.length ? ['sep' as const] : []),
        { label: 'Clear Recent Files', icon: 'edit-delete', onSelect: clearRecentFiles }],
    },
    'sep',
    // Std_CloseActiveWindow / Std_CloseAllWindows: Workbench.cpp lists these under File, not Windows.
    { label: 'Close', kbd: '⌘W', icon: 'win-close', disabled: !open, onSelect: closeActiveWindow },
    { label: 'Close All', icon: 'win-close-all', disabled: !open, onSelect: closeAllWindows },
    'sep',
    { label: 'Save', kbd: '⌘S', icon: 'save', disabled: true },
    { label: 'Save As…', kbd: '⇧⌘S', icon: 'save-as', disabled: true },
    { label: 'Save a Copy…', kbd: '⌥⇧⌘S', icon: 'save-copy', disabled: true },
    { label: 'Save All', icon: 'save-all', disabled: true },
    { label: 'Revert', icon: 'revert', disabled: true },
    'sep',
    { label: 'Import…', kbd: '⇧⌘I', icon: 'bought', disabled: !slug, title: 'bought parts: vendor STEP or measured, always with a source', onSelect: () => openTask('bought', '', 'import') },
    { label: 'Export…', kbd: '⌘E', icon: 'export', cmd: 'Std_Export', disabled: !slug, onSelect: exportCommand },
    { label: 'Merge Document', icon: 'merge', disabled: true }, // Std_MergeProjects: n/a, there's only ever one document
    { label: 'Document Information', icon: 'doc-info', disabled: !slug, onSelect: documentInfo }, // Std_ProjectInfo
    'sep',
    { label: 'Print', kbd: '⌘P', icon: 'print', disabled: !slug || !open, onSelect: printView },
    { label: 'Print Preview', icon: 'print-preview', disabled: !slug || !open, onSelect: printView },
    { label: 'Export PDF', icon: 'print-pdf', disabled: !slug || !open, onSelect: printView },
    'sep',
    { label: 'Exit', kbd: '⌘Q', icon: 'exit', disabled: true }, // Std_Quit: a browser tab can't quit the app
  ]
}

// ── Std_New: FreeCAD creates "Unnamed" without asking and names it only when you Save; this app
// has no Save As, so the name is asked up front (QInputDialog style: one field, Create/Cancel),
// then POST /api/init (`cad init` server-side — the lead's endpoint, not yet built) creates it and
// the result opens, standing in for FreeCAD's create-then-show-empty-document. ──
export function NewDocumentTask() {
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const create = async () => {
    const n = name.trim()
    if (!n || busy) return
    setBusy(true)
    try {
      const r: CadResult = await api.init(n)
      const slug = r.data?.slug
      if (r.exit !== 0 || !slug) { report('err', `New Document: ${resultText(r)}`); return }
      await loadProjects()
      await openProject(slug)
      closeTask()
    } catch (e) {
      report('err', `New Document: ${msg(e)}`)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="tasks">
      <TaskBox title="New Document" icon="new">
        <div className="tform">
          <input autoFocus value={name} placeholder="Unnamed" disabled={busy} onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); create() } }} />
        </div>
        {/* The first command through the warm worker waits for its kernel import: say so, as View3D's "Building the scene" does. */}
        <p className="hint">{busy ? <>Creating {name.trim()}… The first command starts the CAD kernel, which can take about 30 seconds.</>
          : <>Letters, digits, - and _ only — becomes the project's folder name (<code>cad init</code>).</>}</p>
      </TaskBox>
      <div className="tbuttons">
        <button className="qbtn default" disabled={!name.trim() || busy} onClick={create}>Create</button>
        <button className="qbtn" onClick={closeTask}>Cancel</button>
      </div>
    </div>
  )
}

// ── Std_Open: FreeCAD's native "Open File" dialog; the equivalent here is a dialog over our own
// project list (there's no local filesystem to browse from a browser tab). ──
/** Std_Export (CommandDoc.cpp): with nothing selected, a "No Selection" warning; else the save
 *  dialog with the export filters (App::Application::getExportFilters, a sorted map). Here the
 *  file goes to the browser's downloads. */
const EXPORT_FILTERS = ['STEP with colors (*.step *.stp)', 'STL Mesh (*.stl *.ast)', 'WebGL (*.html)'] as const
export function exportCommand() {
  if (!getState().selected.length) {
    void messageBox('warning', 'No Selection', 'Select objects to export before using the Export command.')
    return
  }
  openTask('export', '')
}
export function ExportTask() {
  const selected = useStore((s) => s.selected)
  const [filter, setFilter] = useState<string>(saved.get('FileExportFilter', EXPORT_FILTERS[0]))
  const go = () => {
    saved.set('FileExportFilter', filter)
    if (filter.startsWith('WebGL')) exportPage()
    else exportPart(filter.startsWith('STEP') ? 'step' : 'stl')
    closeTask()
  }
  return (
    <div className="tasks">
      <TaskBox title="Export File" icon="export">
        <label className="tfield"><span>File name:</span><input readOnly value={`${selected[0] ?? ''}.${filter.startsWith('STEP') ? 'step' : filter.startsWith('STL') ? 'stl' : 'html'}`} /></label>
        <label className="tfield"><span>Files of type:</span>
          <QComboBox value={filter} onChange={(e) => setFilter(e.target.value)}>{EXPORT_FILTERS.map((f) => <option key={f} value={f}>{f}</option>)}</QComboBox>
        </label>
      </TaskBox>
      <div className="tbuttons">
        <button className="qbtn default" onClick={go}>Save</button>
        <button className="qbtn" onClick={closeTask}>Cancel</button>
      </div>
    </div>
  )
}

export function OpenDocumentTask() {
  const projects = useStore((s) => s.projects)
  const cur = useStore((s) => s.slug)
  const [sel, setSel] = useState<string | null>(cur)
  const open = () => { if (sel) { openProject(sel); closeTask() } }
  return (
    <div className="tasks">
      <TaskBox title="Open Document" icon="open">
        {!projects.length && <p className="hint">No projects yet. Add a projects folder with `cad serve DIR`.</p>}
        {projects.map((p) => (
          <div key={p.slug} className={cls('trow', sel === p.slug && 'sel')} onClick={() => setSel(p.slug)} onDoubleClick={open}>
            <span>{p.slug}</span><span className="hint">{p.done ? 'DONE' : p.verdict ?? 'NOT VERIFIED'}</span>
          </div>
        ))}
      </TaskBox>
      <div className="tbuttons">
        <button className="qbtn default" disabled={!sel} onClick={open}>Open</button>
        <button className="qbtn" onClick={closeTask}>Cancel</button>
      </div>
    </div>
  )
}

// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Gui/CommandMacro.cpp: 2010 Werner Mayer
//   src/Gui/Workbench.cpp: 2004 Werner Mayer
//   src/Gui/TextEdit.cpp: 2004 Werner Mayer
//   No copyright line in the file: src/Gui/Dialogs/DlgMacroExecute.ui, src/Gui/PreferencePages/DlgSettingsMacro.ui
// FreeCAD's Macro menu: CommandMacro.cpp's commands, Dialogs/DlgMacroRecordImp (+ .ui),
// Dialogs/DlgMacroExecuteImp (+ .ui) and PreferencePages/DlgSettingsMacro (+ .ui). A macro here
// is a text file of `cad` commands (see api.ts's /api/macro* calls), not Python, so the parts of
// DlgMacroExecute that assume a script editor and FreeCAD's module system (System macros tab,
// Find in files, Toolbar, Download/Addon Manager, Open Folder) are n/a and left out; Execute,
// Close, Create, Edit, Rename, Duplicate and Delete are the buttons DlgMacroExecute.ui lays out
// that apply. Task panels, not separate windows, as this app already does for every other
// FreeCAD dialog (Preferences, Document information, Units converter, …).
import { useEffect, useState } from 'react'
import { api, type MacroInfo } from './api'
import { closeTask, drawingPanels, getDock, openTask, startRecording, stopRecording, editorStyle } from './actions'
import { consoleLog, getState, report, saved, useStore } from './store'
import { cls, TaskBox } from './panels'
import { messageBox } from './msgbox'
import type { Entry } from './chrome'

const msg = (e: unknown) => (e instanceof Error ? e.message : String(e))

// ── Recent Macros (Std_RecentMacros; DlgSettingsMacro.ui's "Recent Macros Menu" size, default 12) ──
/** RecentMacrosAction's size: Preferences > Macro > Size of recent macro list (RecentMacros, 12). */
const recentMax = () => saved.get('recentMacrosSize', 12)
const recentMacros = () => saved.get<string[]>('recentMacros', [])
function pushRecent(name: string) {
  saved.set('recentMacros', [name, ...recentMacros().filter((n) => n !== name)].slice(0, recentMax()))
}

/** Prints a macro run's lines like the console prints a `cad` command (commands.ts's
 *  printCadResult): the line typed, then its output or error. */
export async function runMacroToConsole(name: string) {
  const slug = getState().slug
  if (!slug) return report('warn', 'Execute macro: open a project first')
  try {
    const r = await api.runMacro(name, slug)
    for (const line of r.ran) {
      consoleLog('in', line.line)
      if (line.text?.trim()) for (const t of line.text.trimEnd().split('\n')) consoleLog(line.exit === 0 ? 'out' : 'err', t)
    }
    pushRecent(name)
    report(r.exit === 0 ? 'msg' : 'warn', `Macro "${name}": ${r.exit === 0 ? 'done' : `exit ${r.exit}`}`)
  } catch (e) {
    report('err', `Macro "${name}" failed to run: ${msg(e)}`)
  }
}

/** The Macro menu (Workbench.cpp's "&Macro"): Std_DlgMacroRecord (toggling label/icon exactly as
 *  its activated() does), Std_DlgMacroExecute, Std_RecentMacros, Std_DlgMacroExecuteDirect and
 *  Std_MacroAttachDebugger (present but disabled: no debugger here). */
/** Std_DlgMacroExecuteDirect: runs the macro open in the Edit task, if any (isActive: an editor view). */
export function executeMacroDirect() {
  const task = getState().task
  if (task?.kind === 'macroEdit') void runMacroToConsole(task.body)
}
export function macroEntries(): Entry[] {
  const recording = getState().recordingMacro
  const task = getState().task
  const editing = task?.kind === 'macroEdit' ? task.body : null
  const recent = recentMacros()
  return [
    recording
      ? { label: 'Stop Macro Recording', icon: 'macro-stop', onSelect: () => { void stopRecording() } }
      : { label: 'Record Macro', icon: 'macro-record', onSelect: () => openTask('macroRecord', '') },
    { label: 'Macros', icon: 'macros', disabled: !!recording, onSelect: () => openTask('macros', '') },
    { label: 'Recent Macros', sub: recent.map((n): Entry => ({ label: n, onSelect: () => runMacroToConsole(n) })) }, // empty, as RecentMacrosAction's, when there are none
    'sep',
    // Std_DlgMacroExecuteDirect (Ctrl+F6): FreeCAD runs whatever the active editor view holds;
    // here, whatever macro is open in the Edit task.
    { label: 'Execute Macro', kbd: '⌘F6', icon: 'macro-run', disabled: !editing, onSelect: executeMacroDirect },
    { label: 'Attach to Remote Debugger', disabled: true },
  ]
}

/** The MDI area's windows, in tab order: the Start page, the 3D view, and a tab for each drawing (shopwb.tsx's DrawingPanel). */
export function mdiWindows() {
  const dock = getDock()
  const group = (dock?.getPanel('view3d') ?? dock?.getPanel('start') ?? drawingPanels()[0])?.group
  return (group?.panels ?? []).filter((p) => p.id === 'start' || p.id === 'view3d' || p.id.startsWith('drawing:'))
}

/** The Windows menu (Workbench.cpp's "&Windows"). This UI has one document window, the 3D view tab, and a tab for each
 *  drawing; Next/Previous/Tile/Cascade stay disabled (a tab strip has no tiles), and Close and Close All moved to the File
 *  menu (filemenu.tsx) — at this commit Workbench.cpp's own Windows menu doesn't list them, unlike older FreeCAD. */
export function windowsEntries(): Entry[] {
  const windows = mdiWindows()
  return [
    // QKeySequence::NextChild / PreviousChild as the real FreeCAD binds them on macOS: Ctrl+} and Ctrl+Shift+} (⌘} and ⇧⌘}).
    { label: 'Next', kbd: '⌘}', icon: 'win-next', disabled: true },
    { label: 'Previous', kbd: '⇧⌘}', icon: 'win-prev', disabled: true },
    'sep',
    { label: 'Tile', icon: 'win-tile', disabled: true },
    { label: 'Cascade', icon: 'win-cascade', disabled: true },
    'sep',
    // Std_WindowsMenu: one checked entry per open window, "&N title" (WindowAction::onShowMenu),
    // then a separator; here there's at most one, the 3D view tab, always the active one.
    ...windows.map((w, i): Entry => ({ label: `${i + 1} ${w.api.title ?? ''}`, checked: w.api.isActive, onSelect: () => w.api.setActive() })),
    ...(windows.length ? ['sep' as const] : []),
    { label: 'Choose Open Window', icon: 'win-list', onSelect: () => openTask('windows', '') }, // Std_Windows, renamed from "Windows…"
  ]
}

// ── Std_DlgMacroRecord: DlgMacroRecord.ui (Macro Name, Macro Path, Record/Close) ──
export function MacroRecordTask() {
  const [name, setName] = useState('')
  const [dir, setDir] = useState('')
  useEffect(() => { api.macros().then((r) => setDir(r.dir)).catch(() => {}) }, [])
  const start = () => {
    const n = name.trim()
    if (!n) return
    startRecording(n)
    closeTask()
  }
  return (
    <div className="tasks">
      <TaskBox title="Macro Name" icon="macro-record">
        <div className="tform">
          <input autoFocus value={name} placeholder="MacroName" onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); start() } }} />
        </div>
      </TaskBox>
      <TaskBox title="Macro Path" icon="open">
        <p className="hint">{dir || 'the macros folder cad serve uses'}</p>
      </TaskBox>
      <div className="tbuttons">
        <button className="qbtn default" disabled={!name.trim()} onClick={start}>Record</button>
        <button className="qbtn" onClick={closeTask}>Close</button>
      </div>
    </div>
  )
}

// ── Std_DlgMacroExecute: DlgMacroExecute.ui's list, Execute/Close/Create/Delete/Edit/Rename/
// Duplicate buttons (that order, as the .ui lays them out); System macros tab, Find fields,
// Toolbar and Download buttons are n/a (no Python editor, no Addon Manager here). ──
type Prompt = { kind: 'create' | 'rename' | 'duplicate'; value: string }
export function MacrosTask() {
  const [rows, setRows] = useState<MacroInfo[]>([])
  const [sel, setSel] = useState<string | null>(null)
  const [prompt, setPrompt] = useState<Prompt | null>(null)
  const [busy, setBusy] = useState(false)
  const slug = useStore((s) => s.slug)
  const load = () => api.macros().then((r) => setRows(r.macros)).catch((e) => report('err', `Macros: ${msg(e)}`))
  useEffect(() => { load() }, [])
  const one = rows.find((r) => r.name === sel) ?? null
  // the name Duplicate offers: a macro's name is letters, digits, space, - and _ only (cad_agent/macro.py), so no "(copy)"; the first one not taken
  const copyName = (name: string) => { let n = `${name}_copy`, i = 2; while (rows.some((r) => r.name === n)) n = `${name}_copy${i++}`; return n }
  const execute = async () => {
    if (!one) return
    await runMacroToConsole(one.name)
    closeTask()
  }
  const del = async () => {
    if (!one) return
    // DlgMacroExecuteImp::onDeleteButtonClicked's own confirmation text.
    if ((await messageBox('question', 'Delete macro', `Delete the macro '${one.name}'?`, ['Yes', 'No'])) !== 'Yes') return
    setBusy(true)
    try { await api.deleteMacro(one.name); setSel(null); await load() } catch (e) { report('err', `Delete macro: ${msg(e)}`) } finally { setBusy(false) }
  }
  const confirmPrompt = async () => {
    if (!prompt) return
    const to = prompt.value.trim()
    if (!to) return
    setBusy(true)
    try {
      if (prompt.kind === 'create') { await api.saveMacro(to, `# cad macro: ${to}\n# recorded ${new Date().toISOString()}\n`); setPrompt(null); await load(); openTask('macroEdit', to); return }
      if (prompt.kind === 'rename' && one) await api.renameMacro(one.name, to)
      if (prompt.kind === 'duplicate' && one) await api.duplicateMacro(one.name, to)
      setPrompt(null)
      setSel(to)
      await load()
    } catch (e) {
      report('err', `${prompt.kind === 'create' ? 'Create' : prompt.kind === 'rename' ? 'Rename' : 'Duplicate'} macro: ${msg(e)}`)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="tasks">
      <TaskBox title="Macros" icon="macros">
        <div className="tform">
          {!rows.length && <p className="hint">No macros yet. Create one, or use Record Macro.</p>}
          {rows.map((r) => (
            <div key={r.name} className={cls('trow', sel === r.name && 'sel')} onClick={() => setSel(r.name)} onDoubleClick={execute}>
              <span>{r.name}</span><span className="hint">{r.lines} line{r.lines === 1 ? '' : 's'} · {new Date(r.modified).toLocaleString()}</span>
            </div>
          ))}
        </div>
        {prompt && (
          <div className="hbox">
            <input autoFocus value={prompt.value} onChange={(e) => setPrompt({ ...prompt, value: e.target.value })}
              onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); confirmPrompt() } else if (e.key === 'Escape') setPrompt(null) }} />
            <button className="qbtn default" disabled={busy || !prompt.value.trim()} onClick={confirmPrompt}>
              {prompt.kind === 'create' ? 'Create' : prompt.kind === 'rename' ? 'Rename' : 'Duplicate'}</button>
            <button className="qbtn" onClick={() => setPrompt(null)}>Cancel</button>
          </div>
        )}
        <div className="hbox spread">
          <div className="hbox">
            <button className="qbtn default" disabled={!one} onClick={execute}>Execute</button>
            <button className="qbtn" onClick={closeTask}>Close</button>
          </div>
          <div className="hbox">
            <button className="qbtn" disabled={busy} onClick={() => setPrompt({ kind: 'create', value: '' })}>Create</button>
            <button className="qbtn" disabled={!one || busy} onClick={del}>Delete</button>
            <button className="qbtn" disabled={!one} onClick={() => openTask('macroEdit', one!.name)}>Edit</button>
            <button className="qbtn" disabled={!one || busy} onClick={() => setPrompt({ kind: 'rename', value: one!.name })}>Rename</button>
            <button className="qbtn" disabled={!one || busy} onClick={() => setPrompt({ kind: 'duplicate', value: copyName(one!.name) })}>Duplicate</button>
          </div>
        </div>
        {!slug && <p className="hint">Execute needs an open project (macros carry an explicit project name, but run against the one open here).</p>}
      </TaskBox>
    </div>
  )
}

// ── DlgMacroExecuteImp::onEditButtonClicked, simplified to one textarea + Save (no external
// text editor here); Save returns to the Macros list, as closing the real editor would. ──
export function MacroEditTask({ name }: { name: string }) {
  const [text, setText] = useState('')
  const ed = useStore((s) => s.editorPrefs)
  const [loaded, setLoaded] = useState(false)
  const [saving, setSaving] = useState(false)
  useEffect(() => { api.macro(name).then((r) => { setText(r.text); setLoaded(true) }).catch((e) => report('err', `Edit macro: ${msg(e)}`)) }, [name])
  const save = async () => {
    setSaving(true)
    try { await api.saveMacro(name, text); report('msg', `Macro "${name}" saved.`); openTask('macros', '') }
    catch (e) { report('err', `Save macro: ${msg(e)}`) } finally { setSaving(false) }
  }
  return (
    <div className="tasks">
      <TaskBox title={`Edit macro: ${name}`} icon="macros">
        <textarea className="macro-editor" spellCheck={false} disabled={!loaded} value={text} onChange={(e) => setText(e.target.value)}
          style={editorStyle(ed) as React.CSSProperties} onKeyDown={(e) => {
            // TextEditor::keyPressEvent (TextEdit.cpp): Tab inserts IndentSize spaces, or a tab with "Keep tabs".
            if (e.key !== 'Tab' || e.shiftKey || e.metaKey || e.ctrlKey || e.altKey) return
            e.preventDefault()
            const t = e.currentTarget, ins = ed.spaces ? ' '.repeat(ed.indentSize) : '\t', a = t.selectionStart, b = t.selectionEnd
            setText(t.value.slice(0, a) + ins + t.value.slice(b))
            requestAnimationFrame(() => { t.selectionStart = t.selectionEnd = a + ins.length })
          }} />
        <p className="hint">One `cad` command per line; `# cad gui …` lines are GUI actions, commented out when recorded with Record GUI commands off.</p>
      </TaskBox>
      <div className="tbuttons">
        <button className="qbtn default" disabled={!loaded || saving} onClick={save}>Save</button>
        <button className="qbtn" onClick={() => openTask('macros', '')}>Close</button>
      </div>
    </div>
  )
}

// ── Std_Windows: DlgActivateWindowImp (a QTreeWidget of window titles, Activate/Cancel) ──
export function WindowsTask() {
  const windows = mdiWindows().filter((w) => w.id !== 'start')
  const [pick, setPick] = useState(() => (windows.find((w) => w.api.isActive) ?? windows[0])?.id ?? '')
  const panel = windows.find((w) => w.id === pick)
  const activate = () => { panel?.api.setActive(); closeTask() }
  return (
    <div className="tasks">
      <TaskBox title="Choose Window" icon="win-list">
        {windows.length
          ? windows.map((w) => <div key={w.id} className={cls('trow', w.id === pick && 'sel')} onClick={() => setPick(w.id)} onDoubleClick={activate}>
            <span>{w.api.title ?? w.id}</span><span /></div>)
          : <p className="hint">No windows open.</p>}
      </TaskBox>
      <div className="tbuttons">
        <button className="qbtn default" disabled={!panel} onClick={activate}>Activate</button>
        <button className="qbtn" onClick={closeTask}>Cancel</button>
      </div>
    </div>
  )
}

// Std_DlgCustomize: Gui/Dialogs/DlgCustomizeImp.cpp at FreeCAD main 3160daf1e2b6 — "Customize",
// its pages as resource.cpp registers them (DlgCustomToolbarsImp "Toolbars", DlgCustomActionsImp
// "Macros"; the Spaceball pages need a 3Dconnexion SDK), Help (What's This) and Close.
// Toolbars (DlgToolbars.ui): the commands (Category, search) on the left, Move Right/Left/Up/
// Down, and on the right the workbench's custom toolbars (Global or one workbench) with their
// commands, New / Rename / Delete and a check box to show each. Macros (DlgActions.ui): macro
// commands (Std_Macro_N) with Macro, Menu text, Tooltip, Status text, What's this, Accelerator
// (a ShortcutManager shortcut, keymap.ts) and Icon; Add / Remove / Replace.
import { useEffect, useMemo, useState } from 'react'
import { getState, saved, setState, subscribe, useStore, type CustomToolbar, type MacroCommand } from './store'
import { listCommands, removeDynamicCommand, setDynamicCommand } from './cmdreg'
import { cmdIcon } from './cmdicons'
import { FILES, Icon, type IconName } from './icons'
import { allWorkbenches, whatsThis } from './chrome'
import { messageBox } from './msgbox'
import { api } from './api'
import { runMacroToConsole } from './macro'
import { setShortcut, shortcutOf } from './keymap'
import { AccelEdit } from './prefs'
import { cls } from './panels'

const setToolbars = (customToolbars: CustomToolbar[]) => { saved.set('customToolbars', customToolbars); setState({ customToolbars }) }
const setMacros = (macroCommands: MacroCommand[]) => { saved.set('macroCommands', macroCommands); setState({ macroCommands }) }

// The macro commands as registry commands (CommandManager::addCommand of each MacroCommand):
// their menu text, running their macro.
let lastMacros: MacroCommand[] = []
function syncMacroCommands() {
  const now = getState().macroCommands
  if (now === lastMacros) return
  for (const m of lastMacros) if (!now.some((x) => x.name === m.name)) removeDynamicCommand(m.name)
  for (const m of now) setDynamicCommand(m.name, m.menuText, () => { void runMacroToConsole(m.macro) })
  lastMacros = now
}
syncMacroCommands()
subscribe(syncMacroCommands)

/** A command as Customize lists it: its icon (or none) and menu text. */
function CmdLabel({ cmd }: { cmd: string }) {
  if (cmd === 'Separator') return <span className="cu-cmd"><span className="cu-ico" />&lt;Separator&gt;</span>
  const m = getState().macroCommands.find((x) => x.name === cmd)
  const icon = m ? (m.pixmap as IconName) || null : cmdIcon(cmd)
  const label = m?.menuText ?? listCommands().find((c) => c.name === cmd)?.label ?? cmd
  return <span className="cu-cmd" title={cmd}><span className="cu-ico">{icon && <Icon name={icon} size={16} />}</span>{label}</span>
}

/** QInputDialog::getText. */
function InputDialog({ title, label, value, onOk, onCancel }: { title: string; label: string; value: string; onOk(v: string): void; onCancel(): void }) {
  const [v, setV] = useState(value)
  return (
    <div className="msgbox-back" onKeyDown={(e) => { e.stopPropagation(); if (e.key === 'Escape') onCancel(); else if (e.key === 'Enter') onOk(v) }}>
      <div className="msgbox cu-input" role="dialog" aria-label={title}>
        <div className="msgbox-title">{title}</div>
        <label className="sel-row"><span>{label}</span><input autoFocus value={v} onChange={(e) => setV(e.target.value)} onFocus={(e) => e.target.select()} /></label>
        <div className="msgbox-buttons"><button className="qbtn default" onClick={() => onOk(v)}>OK</button><button className="qbtn" onClick={onCancel}>Cancel</button></div>
      </div>
    </div>)
}

function ToolbarsPage() {
  const toolbars = useStore((s) => s.customToolbars), active = useStore((s) => s.workbench)
  useStore((s) => s.macroCommands)
  const [wb, setWb] = useState<string>(active)
  const [filter, setFilter] = useState('')
  const [left, setLeft] = useState<string | null>(null)
  const [right, setRight] = useState<{ tb: number; i: number | null } | null>(null)
  const [ask, setAsk] = useState<{ title: string; value: string; done(v: string): void } | null>(null)
  const cmds = useMemo(() => ['Separator', ...listCommands().map((c) => c.name)], [toolbars])
  const q = filter.trim().toLowerCase()
  const shown = cmds.filter((c) => c === 'Separator' || !q || c.toLowerCase().includes(q) || (listCommands().find((x) => x.name === c)?.label ?? '').toLowerCase().includes(q))
  // The selected workbench's toolbars, with their index in the full list.
  const mine = toolbars.map((t, k) => [t, k] as const).filter(([t]) => t.wb === wb)
  const edit = (k: number, f: (t: CustomToolbar) => CustomToolbar) => setToolbars(toolbars.map((t, j) => (j === k ? f(t) : t)))
  const dup = (name: string, except = -1) => mine.some(([t, k]) => t.name === name && k !== except)
  const named = (title: string, value: string, done: (v: string) => void, except = -1) => setAsk({ title, value, done: (v) => {
    setAsk(null)
    if (!v) return
    if (dup(v, except)) { void messageBox('warning', 'Duplicated name', `The toolbar name '${v}' is already used`); return }
    done(v)
  } })
  const sel = right ? toolbars[right.tb] : null
  const moveRight = (cmd = left) => {
    if (!cmd || !right || !sel) return
    const at = right.i === null ? sel.cmds.length : right.i + 1
    if (cmd !== 'Separator' && sel.cmds.includes(cmd)) return // a command appears once per toolbar
    edit(right.tb, (t) => ({ ...t, cmds: [...t.cmds.slice(0, at), cmd, ...t.cmds.slice(at)] }))
    setRight({ tb: right.tb, i: at })
  }
  const moveLeft = () => {
    if (!right || right.i === null) return
    edit(right.tb, (t) => ({ ...t, cmds: t.cmds.filter((_, j) => j !== right.i) }))
    setRight({ tb: right.tb, i: null })
  }
  const shift = (d: -1 | 1) => {
    if (!right || right.i === null || !sel) return
    const j = right.i + d
    if (j < 0 || j >= sel.cmds.length) return
    edit(right.tb, (t) => { const c = [...t.cmds]; [c[right.i!], c[j]] = [c[j], c[right.i!]]; return { ...t, cmds: c } })
    setRight({ tb: right.tb, i: j })
  }
  return (
    <div className="cu-toolbars">
      <div className="cu-col">
        <label className="sel-row"><span>Category</span><select value="All" title="n/a: commands here aren't grouped into categories"><option>All</option></select></label>
        <input type="search" placeholder="Type to search…" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <div className="cu-list">{shown.map((c) => (
          <div key={c} className={cls('cu-row', left === c && 'sel')} onClick={() => setLeft(c)} onDoubleClick={() => { setLeft(c); moveRight(c) }}><CmdLabel cmd={c} /></div>))}</div>
      </div>
      <div className="cu-moves">
        <button className="qbtn" title={'Moves the selected item one level down.\nThis will also change the level of the parent item.'} disabled={!left || !right} onClick={() => moveRight()}>→</button>
        <button className="qbtn" title={'Moves the selected item one level up.\nThis will also change the level of the parent item.'} disabled={right?.i == null} onClick={moveLeft}>←</button>
        <button className="qbtn" title={'Moves the selected item up.\nThe item will be moved within the hierarchy level.'} disabled={!right || right.i == null || right.i === 0} onClick={() => shift(-1)}>↑</button>
        <button className="qbtn" title={'Moves the selected item down.\nThe item will be moved within the hierarchy level.'} disabled={!right || right.i == null || !sel || right.i >= sel.cmds.length - 1} onClick={() => shift(1)}>↓</button>
      </div>
      <div className="cu-col">
        <select value={wb} onChange={(e) => { setWb(e.target.value); setRight(null) }}>
          <option value="Global">Global</option>
          {allWorkbenches().map(([k, w]) => <option key={k} value={k}>{w.label}</option>)}
        </select>
        <div className="cu-list">{mine.map(([t, k]) => (
          <div key={k}>
            <div className={cls('cu-row', right?.tb === k && right.i === null && 'sel')} onClick={() => setRight({ tb: k, i: null })}>
              <input type="checkbox" checked={t.active} onChange={(e) => edit(k, (x) => ({ ...x, active: e.target.checked }))} onClick={(e) => e.stopPropagation()} /> {t.name}</div>
            {t.cmds.map((c, i) => (
              <div key={i} className={cls('cu-row cu-child', right?.tb === k && right.i === i && 'sel')} onClick={() => setRight({ tb: k, i })}><CmdLabel cmd={c} /></div>))}
          </div>))}</div>
        <div className="cu-tbbtns">
          <button className="qbtn" onClick={() => named('New toolbar', `Custom${mine.length + 1}`, (name) => {
            setToolbars([...toolbars, { name, wb, active: true, cmds: [] }]); setRight({ tb: toolbars.length, i: null }) })}>New</button>
          <button className="qbtn" disabled={!sel} onClick={() => sel && named('Rename toolbar', sel.name, (name) => edit(right!.tb, (t) => ({ ...t, name })), right!.tb)}>Rename</button>
          <button className="qbtn" disabled={!sel} onClick={() => { if (right) { setToolbars(toolbars.filter((_, j) => j !== right.tb)); setRight(null) } }}>Delete</button>
        </div>
      </div>
      {ask && <InputDialog title={ask.title} label="Toolbar name:" value={ask.value} onOk={ask.done} onCancel={() => setAsk(null)} />}
    </div>
  )
}

const ICON_NAMES = (Object.keys(FILES) as IconName[]).sort()
function MacrosPage() {
  const macros = useStore((s) => s.macroCommands)
  useStore((s) => s.shortcuts)
  const [files, setFiles] = useState<string[]>([])
  useEffect(() => { void api.macros().then((r) => setFiles(r.macros.map((m) => m.name))).catch(() => {}) }, [])
  const blank = { macro: '', menuText: '', toolTip: '', statusTip: '', whatsThis: '', pixmap: '', accel: '' }
  const [f, setF] = useState(blank)
  const [cur, setCur] = useState<string | null>(null)
  const field = (label: string, k: 'menuText' | 'toolTip' | 'statusTip' | 'whatsThis') => (
    <><span>{label}</span><input value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></>)
  const check = async () => {
    if (!f.macro) { await messageBox('warning', 'Empty Macro', 'Specify the macro first'); return false }
    if (!f.menuText) { await messageBox('warning', 'Empty Text', 'Specify the menu text first'); return false }
    return true
  }
  const entry = (name: string): MacroCommand => ({ name, macro: f.macro, menuText: f.menuText, toolTip: f.toolTip, statusTip: f.statusTip, whatsThis: f.whatsThis, pixmap: f.pixmap })
  const add = async () => {
    if (!(await check())) return
    // CommandManager::newMacroName: Std_Macro_N, the first N not taken.
    let n = 0
    while (macros.some((m) => m.name === `Std_Macro_${n}`)) n++
    const name = `Std_Macro_${n}`
    setMacros([...macros, entry(name)])
    if (f.accel) setShortcut(name, f.accel)
    setF(blank); setCur(null)
  }
  const replace = async () => {
    if (!cur) { await messageBox('warning', 'No Item Selected', 'Select a macro item first'); return }
    if (!(await check())) return
    setMacros(macros.map((m) => (m.name === cur ? entry(cur) : m)))
    setShortcut(cur, f.accel || '')
  }
  const remove = () => {
    if (!cur) return
    setMacros(macros.filter((m) => m.name !== cur))
    setShortcut(cur, null)
    setToolbars(getState().customToolbars.map((t) => ({ ...t, cmds: t.cmds.filter((c) => c !== cur) })))
    setF(blank); setCur(null)
  }
  return (
    <fieldset className="tgroup cu-macros"><legend>Setup Custom Macros</legend>
      <div className="cu-list">{macros.map((m) => (
        <div key={m.name} className={cls('cu-row', cur === m.name && 'sel')} onClick={() => { setCur(m.name); setF({ ...m, accel: shortcutOf(m.name) }) }}><CmdLabel cmd={m.name} /></div>))}</div>
      <div className="cu-form">
        <span>Macro</span><select value={f.macro} onChange={(e) => setF({ ...f, macro: e.target.value })}><option value="" />{files.map((n) => <option key={n} value={n}>{n}</option>)}</select>
        {field('Menu text', 'menuText')}
        {field('Tooltip', 'toolTip')}
        {field('Status text', 'statusTip')}
        {field("What's this", 'whatsThis')}
        <span>Accelerator</span><AccelEdit value={f.accel} onChange={(accel) => setF({ ...f, accel })} />
        <span>Icon</span><span className="cu-pix"><select value={f.pixmap} title="Choose an icon" onChange={(e) => setF({ ...f, pixmap: e.target.value })}>
          <option value="">(none)</option>{ICON_NAMES.map((n) => <option key={n} value={n}>{n}</option>)}</select>{f.pixmap && <Icon name={f.pixmap as IconName} size={24} />}</span>
        <span /><span className="cu-tbbtns"><button className="qbtn" onClick={() => { void add() }}>Add</button><button className="qbtn" onClick={remove} disabled={!cur}>Remove</button><button className="qbtn" onClick={() => { void replace() }}>Replace</button></span>
      </div>
    </fieldset>
  )
}

export function CustomizeDialog() {
  const open = useStore((s) => s.customizeOpen)
  const [tab, setTab] = useState<'Toolbars' | 'Macros'>('Toolbars')
  if (!open) return null
  const close = () => setState({ customizeOpen: false })
  return (
    <div className="msgbox-back" onKeyDown={(e) => { if (e.key === 'Escape') close() }}>
      <div className="cu-dlg" role="dialog" aria-label="Customize">
        <div className="msgbox-title">Customize</div>
        <div className="cu-tabs" role="tablist">{(['Toolbars', 'Macros'] as const).map((t) => (
          <button key={t} role="tab" className={cls('cu-tab', tab === t && 'sel')} onClick={() => setTab(t)}>{t}</button>))}</div>
        <div className="cu-page">{tab === 'Toolbars' ? <ToolbarsPage /> : <MacrosPage />}</div>
        <div className="pref-buttons">
          <button className="qbtn" onClick={() => whatsThis()}>Help</button>
          <button className="qbtn default" onClick={close}>Close</button>
        </div>
      </div>
    </div>
  )
}

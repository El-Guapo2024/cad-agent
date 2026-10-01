import { Fragment, createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { axisAngleOf, eulerOf as eulerOfSeq, quatOfEuler as quatOfEulerSeq, quatOfYpr, yprOfQuat, type EulerSeq } from './rotation'
import type { Body, CheckRow, LogEntry, Placement, Vec3 } from './api'
import { CORNER_POS, getState, report, saved, setState, useStore, viewOf, type AxisColors, type ClipAxis, type ClipView, type HomeView, type NaviCubePrefs, type RotationCenterPrefs, type Level, type NavStyle, type ViewProps as ViewPropsT } from './store'
import { VIEW } from './theme'
import { NAV_STYLES, ORBIT_STYLES, type NavPrefs, type OrbitStyle } from './nav'
import { CadView, measurePair, subInfo, type TransformPhase } from './viewer'
import { clarifyEntries, ContextMenu, navHint, popupEntries, treeEntries, type Entry } from './chrome'
import { gotoSelection, navi, runConsole, setCorner, setHomeView, setNav, setUnits, viewHome } from './commands'
import { setNotifyPrefs } from './notifications'
import { api, resultText } from './api'
import { fromFreeCAD, placementMatrix, toFreeCAD, toPlacement } from './placement'
import * as THREE from 'three'
import { Icon, type IconName } from './icons'
import * as quantity from './quantity'
import { UNIT_TYPES, type Dims } from './units-data'
import { QuantityBox, LENGTH, ANGLE, NUMBER } from './qsb'
import { QComboBox } from './combo'
import { messageBox } from './msgbox'
import { NaviButtons } from './navicube'
import { ExpressionDialog } from './exprdialog'
import { MassTask, MeasureTask } from './measure'
import { BoughtTask, CutlistTask, GateTask, RenderTask, RulesTask, TablesTask, ToolTask } from './agentwb'
import { MacroEditTask, MacroRecordTask, MacrosTask, WindowsTask } from './macro'
import { NewDocumentTask, OpenDocumentTask, ExportTask } from './filemenu'
import { DependencyGraphTask, ParameterEditorTask, SceneInspectorTask } from './tools'
import {
  attachView, closeTask, editDefault, getView, place, placementOf, preselect, runCheck, runVerify, select, selectRange, setParams, setViewProps, showPanel,
  setOrtho, toggleVisibility,
} from './actions'

export const cls = (...a: (string | false | null | undefined)[]) => a.filter(Boolean).join(' ')
const fmtNum = (n: number) => String(Math.round(n * 1000) / 1000)
const fmtValue = (v: unknown) => (typeof v === 'number' ? fmtNum(v) : String(v))
const pad = (depth: number) => ({ paddingLeft: 18 + depth * 14 })
/** ReportView::onMessage: QTime::toString("hh:mm:ss  "), whatever the locale. */
const clock = (t: number) => { const d = new Date(t); return [d.getHours(), d.getMinutes(), d.getSeconds()].map((n) => String(n).padStart(2, '0')).join(':') }

/** A typed value from what was typed, or undefined when it doesn't parse. */
function parse(text: string, type: string): unknown {
  const t = text.trim()
  if (type === 'float') { const n = Number(t); return t && Number.isFinite(n) ? n : undefined }
  if (type === 'int') { const n = Number(t); return t && Number.isInteger(n) ? n : undefined }
  if (type === 'bool') return t === 'true' ? true : t === 'false' ? false : undefined
  return text
}

function Twisty({ open, onClick }: { open: boolean; onClick?: () => void }) {
  return <span className={cls('twisty', open && 'open')} onClick={(e) => { if (onClick) { e.stopPropagation(); onClick() } }} />
}

// ── 3D view ──────────────────────────────────────────────────────────────────
export function View3D() {
  const ref = useRef<HTMLDivElement>(null)
  const scene = useStore((s) => s.scene), building = useStore((s) => s.building)
  const err = useStore((s) => s.sceneError), slug = useStore((s) => s.slug), offline = useStore((s) => s.offline)
  const [menu, setMenu] = useState<{ at: { x: number; y: number }; entries: Entry[]; leave?: () => void } | null>(null)
  useEffect(() => {
    const host = ref.current!
    const clarifyMenu = (x: number, y: number, picks: { body: string; sub: string | null }[]) => {
      if (!picks.length) return
      const hover = (p: { body: string; sub: string | null } | null) => preselect(p?.body ?? null, null, p?.sub ?? null)
      // SelectionMenu::onPicked adds to the selection.
      const choose = (p: { body: string; sub: string | null }) => { preselect(null, null); select(p.body, true, p.sub) }
      setMenu({ at: { x, y }, entries: clarifyEntries(picks, hover, choose), leave: () => hover(null) })
    }
    const v = new CadView(host, {
      hover: preselect, pick: select, open: editDefault, info: (viewInfo) => setState({ viewInfo }), size: (w, h) => setState({ viewSize: [w, h] }),
      // NavigationStyle::openPopupMenu: the menu doesn't change the selection.
      menu: (x, y, body) => {
        const picks = v.picksAt({ x, y })
        setMenu({ at: { x, y }, entries: popupEntries(body, picks.length ? () => clarifyMenu(x, y, picks) : null) })
      },
      clarify: clarifyMenu,
      box: (names, additive) => setState((s) => additive ? { selected: [...new Set([...s.selected, ...names])] } : { selected: names, subSel: [] }),
      picked: (picked) => setState({ picked }),
    })
    attachView(v)
    return () => { attachView(null); v.dispose() }
  }, [])
  const waiting = offline ? `Can't reach cad serve at ${location.host}. Retrying every 2 seconds…`
    : !slug ? 'No project open' : err ? `${slug} did not build: ${err}`
    : building ? 'Building the scene. The first one starts the CAD kernel, about 30 seconds.' : ''
  return (
    <div className="view3d">
      <div ref={ref} className="view3d-host" />
      {!scene && waiting && <div className="view-overlay">{waiting}</div>}
      {scene && err && <div className="view-banner">Rebuild failed, showing the last good scene. {err}</div>}
      {menu && <ContextMenu at={menu.at} entries={menu.entries} onLeave={menu.leave} onClose={() => { menu.leave?.(); setMenu(null) }} />}
      {scene && <NaviButtons />}
    </div>
  )
}


// ── Selection view (Selection/SelectionView.cpp) ─────────────────────────────
/** FreeCAD's Selection view: the selection as "doc#object.element (label)"; the search box
 *  lists objects whose label matches, and Enter selects them all; double-click toggles an
 *  item, hovering preselects it, and the item menu has Select only, Deselect, Zoom fit, Go to
 *  selection, Mark to recompute and To Python console. */
export function SelectionView() {
  const slug = useStore((s) => s.slug) ?? '', selected = useStore((s) => s.selected), subSel = useStore((s) => s.subSel)
  const bodies = useStore((s) => s.scene?.bodies) ?? [], pickList = useStore((s) => s.pickList), picked = useStore((s) => s.picked)
  const [text, setText] = useState('')
  const [menu, setMenu] = useState<{ at: { x: number; y: number }; item: Item } | null>(null)
  type Item = { body: string; sub: string | null }
  const found = text ? bodies.filter((b) => b.name.toLowerCase().includes(text.toLowerCase())).map((b): Item => ({ body: b.name, sub: null })) : null
  const items: Item[] = found ?? [
    ...selected.filter((n) => !subSel.some((r) => r.startsWith(n + '.'))).map((n): Item => ({ body: n, sub: null })),
    ...subSel.map((r): Item => ({ body: r.slice(0, r.lastIndexOf('.')), sub: r.slice(r.lastIndexOf('.') + 1) })),
  ]
  const label = (i: Item) => `${slug}#${i.body}${i.sub ? '.' + i.sub : ''} (${i.body})`
  const isSel = (i: Item) => (i.sub ? subSel.includes(`${i.body}.${i.sub}`) : selected.includes(i.body) && !subSel.some((r) => r.startsWith(i.body + '.')))
  const toggle = (i: Item) => select(i.body, true, i.sub) // Gui.Selection.addSelection / removeSelection
  const only = (i: Item) => select(i.body, false, null)
  const row = (i: Item, k: number) => (
    <div key={k} className="sv-item" onDoubleClick={() => toggle(i)} onMouseEnter={() => preselect(i.body, null, i.sub)}
      onContextMenu={(e) => { e.preventDefault(); setMenu({ at: { x: e.clientX, y: e.clientY }, item: i }) }}>{label(i)}</div>)
  return (
    <div className="sv" onMouseLeave={() => preselect(null, null)}>
      <div className="sv-head">
        <input className="sv-search" placeholder="Search" title="Searches object labels" value={text} onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && found?.length) setState({ selected: found.map((f) => f.body), subSel: [] }) }}
          onBlur={() => { if (found?.length) setState({ selected: found.map((f) => f.body), subSel: [] }) }} />
        <button className="sv-clear" title="Clears the search field" onClick={() => setText('')}>×</button>
        <span className="sv-count" title="The number of selected items">{items.length}</span>
      </div>
      <div className="sv-list">{items.map(row)}</div>
      <label className="tcheck"><input type="checkbox" checked={pickList} onChange={(e) => setState({ pickList: e.target.checked, picked: [] })} /> Picked object list</label>
      {pickList && <div className="sv-list sv-picked">{picked.map((i, k) => (
        <div key={k} className={cls('sv-item', isSel(i) && 'sel')} onDoubleClick={() => toggle(i)} onMouseEnter={() => preselect(i.body, null, i.sub)}>{label(i)}</div>))}</div>}
      {menu && <ContextMenu at={menu.at} onClose={() => setMenu(null)} entries={[
        { label: 'Select Only', title: 'Selects only this object', onSelect: () => only(menu.item) },
        { label: 'Deselect', title: 'Deselects this object', onSelect: () => setState((s) => ({ selected: s.selected.filter((n) => n !== menu.item.body), subSel: s.subSel.filter((r) => !r.startsWith(menu.item.body + '.')) })) },
        { label: 'Zoom Fit', icon: 'fit-sel', title: 'Selects and fits this object in the 3D window', onSelect: () => { only(menu.item); getView()?.fitAll([menu.item.body]) } },
        { label: 'Go to Selection', icon: 'goto-sel', title: 'Selects and locates this object in the tree view', onSelect: () => { only(menu.item); gotoSelection() } },
        { label: 'Mark to Recompute', icon: 'recompute', title: 'Marks this object to be recomputed', onSelect: runCheck },
        { label: 'To Python Console', icon: 'console', title: 'Reveals this object and its subelements in the Python console.', onSelect: () => {
          setState((s) => ({ consoleDraft: [s.consoleDraft, menu.item.sub ? `${menu.item.body}.${menu.item.sub}` : menu.item.body].filter(Boolean).join(' ') })); showPanel('console') } },
      ]} />}
    </div>
  )
}

// ── Model tab: tree above, property view below ───────────────────────────────
export function ModelPanel() {
  return <Split storageKey="model" top={<ModelTree />} bottom={<PropertyView />} />
}

const RANK: Record<string, number> = { PASS: 0, 'N/A': 0, UNCHECKED: 1, FAIL: 2 }
function statesByBody(rows: CheckRow[] | undefined, bodies: Body[]) {
  const out = new Map<string, string>()
  for (const b of bodies) {
    let worst = ''
    for (const r of rows ?? []) {
      const toks = r.subject.split(/[^A-Za-z0-9_]+/)
      if (r.subject !== b.name && r.subject !== b.part && !toks.includes(b.name) && !(b.part && toks.includes(b.part))) continue
      if ((RANK[r.state] ?? 0) > (RANK[worst] ?? -1)) worst = r.state
    }
    if (worst) out.set(b.name, worst)
  }
  return out
}

function ModelTree() {
  const slug = useStore((s) => s.slug), scene = useStore((s) => s.scene), selected = useStore((s) => s.selected)
  const pre = useStore((s) => s.preselected), hidden = useStore((s) => s.hidden), checks = useStore((s) => s.checks)
  const building = useStore((s) => s.building), filter = useStore((s) => s.treeFilter), view = useStore((s) => s.view), showHidden = useStore((s) => s.treeShowHidden)
  const [docMenu, setDocMenu] = useState<{ x: number; y: number } | null>(null)
  const [emptyMenu, setEmptyMenu] = useState<{ x: number; y: number } | null>(null)
  const collapsed = useStore((s) => s.treeCollapsed), treeOpts = useStore((s) => s.tree)
  const [open, setOpenRaw] = useState(true)
  // Tree view actions > Collapse/Expand folds or opens the document.
  useEffect(() => { setOpenRaw(!collapsed) }, [collapsed])
  const setOpen = (o: boolean) => setOpenRaw(o)
  // Sync Selection: a selection made in the 3D view scrolls its item into view.
  useEffect(() => {
    if (!treeOpts.syncSelection || !selected.length) return
    if (!open) setOpenRaw(true)
    requestAnimationFrame(() => document.querySelector('.trow.sel')?.scrollIntoView({ block: 'nearest' }))
  }, [selected, treeOpts.syncSelection])
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null)
  const states = useMemo(() => statesByBody(checks?.rows, scene?.bodies ?? []), [checks, scene])
  // The object in edit (Gui::Document::getInEdit): the default edit (its parameters) or Transform.
  // TreeWidget paints it in Colors' "Object being edited" colour.
  const task = useStore((s) => s.task), editColor = useStore((s) => s.treeEditColor)
  const editing = task && (task.kind === 'params' || task.kind === 'transform') ? task.body : null

  // Tree.cpp ctor 750-752 + TreeParams.py 97-110: HideColumn/HideInternalNames both default to
  // true, so the Description and Internal name columns (and the header itself) start hidden.
  // contextMenuEvent 1334-1370: an unconditional "Tree Settings" submenu (Show Description / Show
  // Internal Name) toggles them, appended to every tree context menu, incl. empty space.
  const [showDesc, setShowDescRaw] = useState(() => !saved.get('tree.hideColumn', true))
  const [showInternal, setShowInternalRaw] = useState(() => !saved.get('tree.hideInternalNames', true))
  const setShowDesc = (v: boolean) => { setShowDescRaw(v); saved.set('tree.hideColumn', !v) }
  const setShowInternal = (v: boolean) => { setShowInternalRaw(v); saved.set('tree.hideInternalNames', !v) }
  const settingsMenu: Entry = { label: 'Tree Settings', sub: [
    { label: 'Show Description', checked: showDesc, onSelect: () => setShowDesc(!showDesc),
      title: "Shows a description column for items. An item's description can be set by editing the 'label2' property." },
    { label: 'Show Internal Name', checked: showInternal, onSelect: () => setShowInternal(!showInternal),
      title: 'Shows an internal name column for items.' },
  ] }
  const cols = 1 + (showDesc ? 1 : 0) + (showInternal ? 1 : 0)

  // Tree.cpp onItemEntered/onPreSelectTimer/leaveEvent 3732-3804 (TreeParams.py:51,57,58 for the
  // defaults): hovering an object row preselects after PreSelectionDelay (700ms) of the last
  // preselect, it fires at once instead; PreSelectionTimeout (500ms) is the debounce while
  // scanning across rows. leaveEvent clears on leaving the whole tree, not per row.
  // onItemSelectionChanged 4037-4040 cancels a pending timer once a real selection happens.
  const hoverRef = useRef<string | null>(null), preselectTime = useRef(performance.now()), preselectTimer = useRef<number | null>(null)
  const cancelPreselectTimer = () => { if (preselectTimer.current != null) { clearTimeout(preselectTimer.current); preselectTimer.current = null } }
  const firePreselect = () => {
    preselectTimer.current = null
    if (!treeOpts.preSelection || !hoverRef.current) return
    preselectTime.current = performance.now()
    preselect(hoverRef.current, null)
  }
  const onEnter = (name: string | null) => {
    hoverRef.current = name
    if (!treeOpts.preSelection) return
    cancelPreselectTimer()
    if (!name) { preselect(null, null); return }
    if (performance.now() - preselectTime.current < 700) firePreselect()
    else { preselect(null, null); preselectTimer.current = window.setTimeout(firePreselect, 500) }
  }
  return (
    <div className={cls('tree', cols === 1 && 'onecol')} tabIndex={-1} style={{ '--tree-cols': `repeat(${cols}, 1fr)` } as React.CSSProperties}
      onMouseLeave={() => { hoverRef.current = null; if (!treeOpts.preSelection) return; cancelPreselectTimer(); preselect(null, null) }}
      onContextMenu={(e) => { if (e.target !== e.currentTarget) return; e.preventDefault(); setEmptyMenu({ x: e.clientX, y: e.clientY }) }}>
      {menu && <ContextMenu at={menu} entries={[...treeEntries('object'), 'sep', settingsMenu]} onClose={() => setMenu(null)} />}
      {docMenu && <ContextMenu at={docMenu} entries={[...treeEntries('document'), 'sep', settingsMenu]} onClose={() => setDocMenu(null)} />}
      {emptyMenu && <ContextMenu at={emptyMenu} entries={[settingsMenu]} onClose={() => setEmptyMenu(null)} />}
      {filter !== null && (() => {
        // TreeWidget::itemSearch: the text names an object (its name, or <<label>>); the match is
        // scrolled to and preselected, Return selects it and closes the box. Names are offered
        // as you type (the search box's completer).
        const find = (t: string) => scene?.bodies.find((x) => x.name === t.trim() || `<<${x.name}>>` === t.trim())?.name ?? null
        return <>
          <input className="tsearch" autoFocus placeholder="Search objects" value={filter} list="tree-search-names"
            onChange={(e) => {
              cancelPreselectTimer()
              setState({ treeFilter: e.target.value })
              const hit = find(e.target.value)
              preselect(hit, null)
              if (hit) requestAnimationFrame(() => document.querySelector(`.trow[data-name="${CSS.escape(hit)}"]`)?.scrollIntoView({ block: 'nearest' }))
            }}
            onKeyDown={(e) => {
              if (e.key === 'Escape') { e.stopPropagation(); preselect(null, null); setState({ treeFilter: null }) }
              else if (e.key === 'Enter') { cancelPreselectTimer(); const hit = find(filter); if (hit) select(hit); preselect(null, null); setState({ treeFilter: null }) }
            }} />
          <datalist id="tree-search-names">{scene?.bodies.map((x) => <option key={x.name} value={x.name} />)}</datalist>
        </>
      })()}
      {(showDesc || showInternal) && (
        <div className="thead"><span>Labels &amp; Attributes</span>{showDesc && <span>Description</span>}{showInternal && <span>Internal name</span>}</div>
      )}
      {slug && (
        <div className="trow doc" onClick={() => { cancelPreselectTimer(); select(null) }} onMouseEnter={() => onEnter(null)}
          onContextMenu={(e) => { e.preventDefault(); setDocMenu({ x: e.clientX, y: e.clientY }) }}>
          <span className="tlab">
            <Twisty open={open} onClick={() => setOpen(!open)} />
            <span className="ticon"><Icon name="document" />{building && <Icon name="ov-recompute" className="tov" size={10} />}</span>
            <span className="tname">{slug}</span>
          </span>
          {showDesc && <span className="tdesc">{scene ? `${scene.bodies.length} bodies` : ''}</span>}
          {showInternal && <span className="tdesc">{slug}</span>}
        </div>
      )}
      {open && scene?.bodies.filter((b) => showHidden || viewOf({ view }, b.name).showInTree).map((b) => {
        const st = states.get(b.name), off = hidden.includes(b.name)
        const desc = [b.part && b.part !== b.name ? b.part : null, b.kind === 'bought' ? 'bought' : null,
          b.placement ? 'moved by hand' : null, st && st !== 'PASS' ? st : null].filter(Boolean).join(' · ')
        return (
          <div key={b.name} data-name={b.name} className={cls('trow', selected.includes(b.name) && 'sel', pre === b.name && 'pre', off && 'hid')}
            style={editing === b.name && !selected.includes(b.name) && pre !== b.name ? { background: editColor } : undefined}
            onClick={(e) => { cancelPreselectTimer(); if (e.shiftKey) selectRange(b.name); else select(b.name, e.metaKey || e.ctrlKey) }} onDoubleClick={() => editDefault(b.name)}
            onMouseEnter={() => onEnter(b.name)}
            onContextMenu={(e) => { e.preventDefault(); if (!getState().selected.includes(b.name)) select(b.name); setMenu({ x: e.clientX, y: e.clientY }) }}>
            <span className="tlab">
              <span className="tindent" />
              {/* DocumentObjectItem::getVisibilityIcon (TreeParams VisibilityIcon, on by default): the
                  eye drawn before the object's icon; a click on it toggles visibility (Tree.cpp). */}
              <span className="teye" title="Toggle visibility (Space)" onClick={(e) => { e.stopPropagation(); toggleVisibility([b.name]) }}
                onDoubleClick={(e) => e.stopPropagation()}><Icon name={off ? 'eye-off' : 'eye'} size={16} /></span>
              <span className="ticon">
                <Icon name={b.kind === 'bought' ? 'bought' : 'part'} />
                {st === 'FAIL' && <Icon name="ov-error" className="tov" size={10} />}
              </span>
              <span className="tname">{b.name}</span>
            </span>
            {showDesc && <span className={cls('tdesc', st === 'FAIL' && 'fail')}>{desc}</span>}
            {showInternal && <span className="tdesc">{b.name}</span>}
          </div>
        )
      })}
    </div>
  )
}

/** The property editor's expansion (PropertyEditor::setupExpansionSubmenu): a generation that
 *  Expand All / Collapse All / Expand to Default bump, and what they set groups to. */
const PropExpand = createContext<{ gen: number; open: boolean | null }>({ gen: 0, open: null })
type ExpandMode = 'default' | 'auto-expand' | 'auto-collapse'

function PropertyView() {
  const scene = useStore((s) => s.scene), selected = useStore((s) => s.selected), hidden = useStore((s) => s.hidden)
  const [tab, setTab] = useState<'view' | 'data'>('data')
  const [menu, setMenu] = useState<{ x: number; y: number; value: string | null } | null>(null)
  const [expand, setExpand] = useState({ gen: 0, open: null as boolean | null })
  const [mode, setModeRaw] = useState<ExpandMode>(() => saved.get<ExpandMode>('props.expandMode', 'default'))
  const setMode = (m: ExpandMode) => { setModeRaw(m); saved.set('props.expandMode', m) }
  // PropertyEditor.cpp ctor 110-116: FirstColumnSize, 0 = unset (use the CSS default split).
  const [colW, setColW] = useState(() => saved.get('props.firstColumnSize', 0))
  const dragged = useRef(false)
  // PropertyEditor::indexResizable (dragSensibility = 5, .h:185): the header is hidden
  // (setHeaderHidden(true), ctor 106), so the Property/Value boundary is found on the row under
  // the pointer, within 5 px of its first cell's right edge. Group rows span both columns.
  const resizable = (e: React.PointerEvent) => {
    const pk = (e.target as HTMLElement).closest('.prow')?.querySelector<HTMLElement>('.pk')
    return pk && Math.abs(pk.getBoundingClientRect().right - e.clientX) < 5 ? pk : null
  }
  // eventFilter 1509-1561: the split cursor over the boundary; a left press drags it by each
  // move's delta (never under dragSensibility*2), and FirstColumnSize is saved on release.
  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => { if (!e.buttons) e.currentTarget.style.cursor = resizable(e) ? 'col-resize' : '' }
  const onPointerDown = (e: React.PointerEvent) => {
    const pk = e.button === 0 && resizable(e)
    if (!pk) return
    e.preventDefault()
    e.stopPropagation() // the press is the drag's (eventFilter returns true), not the row's
    dragged.current = true
    let w = pk.getBoundingClientRect().width, x = e.clientX
    const move = (ev: PointerEvent) => { w = Math.max(10, w + (ev.clientX - x)); x = ev.clientX; setColW(w) }
    const up = () => {
      removeEventListener('pointermove', move); removeEventListener('pointerup', up)
      saved.set('props.firstColumnSize', w)
      setTimeout(() => { dragged.current = false })
    }
    addEventListener('pointermove', move)
    addEventListener('pointerup', up)
  }
  const b = scene?.bodies.find((x) => x.name === selected[selected.length - 1])
  // Auto Expand / Auto Collapse: a new object opens with everything expanded or collapsed.
  useEffect(() => { if (mode !== 'default') setExpand((e) => ({ gen: e.gen + 1, open: mode === 'auto-expand' })) }, [b?.name, mode])
  const bump = (open: boolean | null) => setExpand((e) => ({ gen: e.gen + 1, open }))
  /** PropertyEditor::keyPressEvent: arrows move between rows, F2 or Return edits the row. */
  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const row = (e.target as HTMLElement).closest('.prow') as HTMLElement | null
    if (!row || (e.target as HTMLElement).closest('input, select, textarea')) return
    const rows = [...e.currentTarget.querySelectorAll<HTMLElement>('.prow[tabindex]')], i = rows.indexOf(row)
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); rows[i + (e.key === 'ArrowDown' ? 1 : -1)]?.focus() }
    else if (e.key === 'F2' || e.key === 'Enter') { e.preventDefault(); row.querySelector<HTMLElement>('.pv.edit')?.click() }
  }
  return (
    <div className="props">
      <div className="pgrid" style={colW > 0 ? ({ '--pk-w': `${colW}px` } as React.CSSProperties) : undefined} onKeyDown={onKeyDown}
        onPointerMove={onPointerMove} onPointerDownCapture={onPointerDown} onClickCapture={(e) => { if (dragged.current) e.stopPropagation() }} onContextMenu={(e) => {
        e.preventDefault()
        const row = (e.target as HTMLElement).closest('.prow')
        const pv = row?.querySelector('.pv')
        const box = pv?.querySelector<HTMLInputElement>('input[type=checkbox]')
        setMenu({ x: e.clientX, y: e.clientY, value: pv ? (box ? String(box.checked) : pv.textContent ?? '') : null })
      }}>
        <PropExpand.Provider value={expand}>
          {b && (tab === 'data' ? <DataProps key={b.name + scene!.source_hash} b={b} />
            : <ViewProps b={b} off={hidden.includes(b.name)} />)}
        </PropExpand.Provider>
      </div>
      {menu && <ContextMenu at={menu} onClose={() => setMenu(null)} entries={[
        // PropertyEditor::contextMenuEvent: Copy the value under the pointer, the expansion
        // submenu, Show Hidden. Adding, renaming and deleting properties is the code's job here.
        ...(menu.value !== null ? [{ label: 'Copy', onSelect: () => navigator.clipboard?.writeText(menu.value!) } as Entry, 'sep' as Entry] : []),
        { label: 'Expand/Collapse Properties', sub: [
          { label: 'Expand to Default', onSelect: () => bump(null) },
          { label: 'Expand All', onSelect: () => bump(true) },
          { label: 'Collapse All', onSelect: () => bump(false) },
          'sep',
          { label: 'Default Expand', checked: mode === 'default', onSelect: () => setMode('default') },
          { label: 'Auto Expand', checked: mode === 'auto-expand', onSelect: () => setMode('auto-expand') },
          { label: 'Auto Collapse', checked: mode === 'auto-collapse', onSelect: () => setMode('auto-collapse') },
        ] },
        { label: 'Show Hidden', checked: false, disabled: true, title: 'These objects have no hidden properties' },
      ]} />}
      <div className="ptabs">
        <button className={cls(tab === 'view' && 'on')} onClick={() => setTab('view')}>View</button>
        <button className={cls(tab === 'data' && 'on')} onClick={() => setTab('data')}>Data</button>
      </div>
    </div>
  )
}

function Group({ title, children }: { title: string; children: ReactNode }) {
  const [open, setOpen] = useState(true)
  const ex = useContext(PropExpand)
  useEffect(() => { if (ex.gen) setOpen(ex.open ?? true) }, [ex.gen])
  return (
    <>
      {/* PropertyEditor::drawBranches paints over a group row's branch: no arrow; a double-click (QTreeView) folds it. */}
      <div className="pgroup" onDoubleClick={() => setOpen(!open)}>{title}</div>
      {open && children}
    </>
  )
}

function Row({ k, v, depth = 0 }: { k: ReactNode; v: ReactNode; depth?: number }) {
  return <div className="prow ro"><span className="pk" style={pad(depth)}>{k}</span><span className="pv">{v}</span></div>
}

type QKind = 'Length' | 'Angle'
const QDIMS: Record<QKind, quantity.Quantity['dims']> = { Length: [1, 0, 0, 0, 0, 0, 0, 0], Angle: [0, 0, 0, 0, 0, 0, 0, 1] }
/** What a PARAMS number measures: parts are in mm, so a float is a length, unless its name
 *  says it is an angle, or a ratio or count. */
export function paramKind(name: string, type: string): QKind | null {
  if (type !== 'float' && type !== 'int') return null
  if (/angle|(^|_)deg|deg($|_)|tilt|twist|draft/i.test(name)) return 'Angle'
  if (type === 'int' || /ratio|scale|factor|count|frac|percent|(^|_)n($|_)/i.test(name)) return null
  return 'Length'
}
/** The names an expression may use: the part's numeric parameters, as the quantities they are. */
function paramVars(b: Body): Record<string, quantity.Quantity> {
  return Object.fromEntries(Object.entries(b.params ?? {}).filter(([, p]) => typeof p.value === 'number')
    .map(([n, p]) => { const kd = paramKind(n, p.type); return [n, { value: p.value as number, dims: kd ? QDIMS[kd] : [0, 0, 0, 0, 0, 0, 0, 0] }] }))
}
/** A field's "=" (ExpressionSpinBox::openFormulaDialog): the Expression Editor over it, whose
 *  result becomes the field's value. */
type ExprAsk = { text: string; at: { x: number; y: number }; dims: Dims | null; apply(v: number): void }
const qText = (v: unknown, kind: QKind) => quantity.userString({ value: Number(v), dims: QDIMS[kind] }).text

/** A property the user can edit: click the value, type, Enter commits, Esc cancels. A length
 *  or angle is edited in a QuantitySpinBox (17 cm, 1/2 in, 90 °; arrows and the wheel step
 *  it), as FreeCAD's PropertyUnitItem is; "=" opens the Expression Editor over the part's
 *  other parameters (DlgExpressionInput). PARAMS keeps plain numbers, so OK writes the result. */
function EditRow({ k, value, type, onCommit, depth = 0, unit, kind, vars }:
  { k: string; value: unknown; type: string; onCommit(v: unknown): void; depth?: number; unit?: string; kind?: QKind | null; vars?: Record<string, quantity.Quantity> }) {
  const [editing, setEditing] = useState(false)
  const [expr, setExpr] = useState<{ text: string; at: { x: number; y: number } } | null>(null)
  const cancelled = useRef(false), pending = useRef<number | null>(null), cell = useRef<HTMLSpanElement>(null)
  useStore((s) => s.units) // written again in a new unit system
  if (type === 'bool') {
    // PropertyBoolItem: a check box, one click toggles.
    return (
      <div className="prow" tabIndex={0}><span className="pk" style={pad(depth)}>{k}</span>
        <span className="pv pbool"><input type="checkbox" checked={value === true} onChange={(e) => onCommit(e.target.checked)} /></span></div>
    )
  }
  const numeric = type === 'float' || type === 'int'
  const shown = kind ? qText(value, kind) : `${fmtValue(value)}${unit ? ` ${unit}` : ''}`
  const write = (v: unknown) => { if (v !== undefined && v !== value) onCommit(v) }
  const asType = (v: number) => (type === 'int' ? Math.round(v) : v)
  const commit = (text: string) => {
    let v: unknown
    try { v = parse(text.trim(), type) } catch (e) { report('err', `${k}: ${(e as Error).message}`); return }
    if (v === undefined) report('err', `${k}: ${text} is not a ${type}`)
    else write(v)
  }
  /** The Expression Editor's result. */
  const fromExpr = (v: number, text: string) => {
    const n = asType(v)
    setExpr(null)
    setEditing(false)
    report('msg', `${k} = ${text} = ${kind ? qText(n, kind) : fmtValue(n)}. PARAMS keeps plain numbers, so the value is written, not the expression.`)
    write(n)
  }
  const back = () => { setExpr(null); requestAnimationFrame(() => cell.current?.querySelector('input')?.focus()) }
  /** PropertyEditor::closeEditor with EditNextItem / EditPreviousItem: Tab commits and edits the next row. */
  const tabTo = (back: boolean) => {
    const row = cell.current?.closest('.prow') as HTMLElement | null
    requestAnimationFrame(() => {
      const rows = row ? [...(row.closest('.pgrid')?.querySelectorAll<HTMLElement>('.prow[tabindex]') ?? [])] : []
      const next = rows[rows.indexOf(row!) + (back ? -1 : 1)]
      const ed = next?.querySelector<HTMLElement>('.pv.edit')
      if (ed) ed.click(); else next?.focus()
    })
  }
  const finish = () => { setEditing(false); if (!cancelled.current && pending.current !== null) write(asType(pending.current)) }
  const openExpr = (text: string, at: { x: number; y: number }) => setExpr({ text, at })
  return (
    <div className="prow" tabIndex={0}>
      <span className="pk" style={pad(depth)}>{k}</span>
      <span ref={cell} className="pv edit" onClick={() => { if (!editing) { cancelled.current = false; pending.current = null; setEditing(true) } }}>
        {!editing ? shown
          : kind || type === 'float'
            // PropertyUnitItem / PropertyFloatItem: a spin box (QuantitySpinBox, DoubleSpinBox).
            ? <span className="pedit" onKeyDown={(e) => {
                if (e.key === 'Escape') { cancelled.current = true; setEditing(false) }
                else if (e.key === 'Tab') { e.preventDefault(); finish(); tabTo(e.shiftKey) }
              }}
                onBlur={(e) => { if (!expr && !e.currentTarget.contains(e.relatedTarget as Node | null)) finish() }}>
                <QuantityBox autoFocus value={Number(value)} dims={kind ? QDIMS[kind] : NUMBER} onChange={(v) => { pending.current = v }} onFinish={finish} onEquals={openExpr} title="Enter expression… (=)" />
              </span>
            // PropertyIntegerItem: IntSpinBox; strings: a line edit.
            : <input autoFocus defaultValue={String(value)} type={type === 'int' ? 'number' : undefined} step={type === 'int' ? 1 : undefined}
                onBlur={(e) => { if (expr) return; setEditing(false); if (!cancelled.current) commit(e.currentTarget.value) }}
                onKeyDown={(e) => {
                  if (numeric && e.key === '=') { e.preventDefault(); const r = e.currentTarget.getBoundingClientRect(); openExpr(e.currentTarget.value, { x: r.left, y: r.top }) }
                  if (e.key === 'Enter') e.currentTarget.blur()
                  if (e.key === 'Escape') { cancelled.current = true; e.currentTarget.blur() }
                  if (e.key === 'Tab') { e.preventDefault(); e.currentTarget.blur(); tabTo(e.shiftKey) }
                }} />}
      </span>
      {expr && <ExpressionDialog at={expr.at} text={expr.text} dims={kind ? QDIMS[kind] : null} vars={vars ?? {}} onOk={fromExpr} onCancel={back} />}
    </div>
  )
}

/** PropertyVectorItem::toString ("[%1 %2 %3]", QLocale 'f' at lowPrec 2) and
 *  PropertyVectorDistanceItem::toString ("[{} {} {}]", each a Length user string). */
const vecText = (v: Vec3, kind?: QKind) => `[${v.map((x) => (kind ? qText(x, kind) : x.toFixed(2))).join(' ')}]`
function VecRows({ label, v, unit, onCommit, kind, vars, depth = 0 }: { label: string; v: Vec3; unit: string; onCommit(i: number, n: number): void; kind?: QKind; vars?: Record<string, quantity.Quantity>; depth?: number }) {
  const [open, setOpen] = useState(false)
  const ex = useContext(PropExpand)
  useEffect(() => { if (ex.gen) setOpen(ex.open ?? false) }, [ex.gen])
  useStore((s) => s.units) // written again in a new unit system
  return (
    <>
      <div className="prow ro" onClick={() => setOpen(!open)}>
        <span className="pk" style={pad(depth)}><Twisty open={open} />{label}</span>
        <span className="pv">{vecText(v, kind)}</span>
      </div>
      {open && ['x', 'y', 'z'].map((ax, i) => (
        <EditRow key={ax} k={ax} depth={depth + 1} value={v[i]} type="float" unit={unit} kind={kind} vars={vars} onCommit={(n) => onCommit(i, n as number)} />
      ))}
    </>
  )
}

/** PropertyPlacementItem: one row under Base, "[(axis); angle; (x  y  z)]" (toString: the axis at
 *  lowPrec 2, the angle and the position as user strings, two spaces between the coordinates),
 *  opening onto its Angle, Axis and Position. */
function PlacementRow({ fc, vars, onCommit }: { fc: { angle: number; axis: Vec3; position: Vec3 }; vars: Record<string, quantity.Quantity>; onCommit(angle: number, axis: Vec3, position: Vec3): void }) {
  const [open, setOpen] = useState(false)
  const ex = useContext(PropExpand)
  useEffect(() => { if (ex.gen) setOpen(ex.open ?? false) }, [ex.gen])
  const at = (v: Vec3, i: number, n: number) => v.map((x, j) => (j === i ? n : x)) as Vec3
  const text = `[(${fc.axis.map((x) => x.toFixed(2)).join(' ')}); ${qText(fc.angle, 'Angle')}; (${fc.position.map((x) => qText(x, 'Length')).join('  ')})]`
  return (
    <>
      <div className="prow ro" onClick={() => setOpen(!open)}>
        <span className="pk" style={pad(0)}><Twisty open={open} />Placement</span><span className="pv">{text}</span>
      </div>
      {open && <>
        <EditRow k="Angle" depth={1} value={fc.angle} type="float" kind="Angle" vars={vars} onCommit={(v) => onCommit(v as number, fc.axis, fc.position)} />
        <VecRows label="Axis" depth={1} v={fc.axis} unit="" vars={vars} onCommit={(i, n) => onCommit(fc.angle, at(fc.axis, i, n), fc.position)} />
        <VecRows label="Position" depth={1} v={fc.position} unit="mm" kind="Length" vars={vars} onCommit={(i, n) => onCommit(fc.angle, fc.axis, at(fc.position, i, n))} />
      </>}
    </>
  )
}

/** Std_SetAppearance: TaskDisplayProperties (Mod/Material/Gui, DlgDisplayProperties.ui) — Viewing
 *  Mode, Material and Display, each change applied at once to every selected object; Close only.
 *  The material library isn't here (Default only); Custom appearance edits the shape's colour. */
export function AppearanceTask() {
  const s = useStore((st) => st), names = s.selected
  const vp = viewOf(s, names[0] ?? ''), b = s.scene?.bodies.find((x) => x.name === names[0])
  const shape = vp.shapeColor ?? (b?.color ? parseInt(b.color.slice(1), 16) : VIEW.shape) // what it shows now
  const set = (patch: Partial<ViewPropsT>) => setViewProps(names, patch)
  const colorBtn = (v: number, f: (v: number) => void) => (
    <label className="qbtn color-btn"><span className="color-chip" style={{ background: hex(v) }} />
      <input type="color" value={hex(v)} onChange={(e) => f(parseInt(e.target.value.slice(1), 16))} /></label>)
  const spin = (v: number, lo: number, hi: number, f: (v: number) => void, disabled = false) =>
    <input type="number" className="qsb" min={lo} max={hi} value={v} disabled={disabled} onChange={(e) => f(Math.min(hi, Math.max(lo, Number(e.target.value))))} />
  return (
    <div className="tasks">
      <TaskBox title="Display Properties" icon="appearance">
        <fieldset className="tgroup"><legend>Viewing Mode</legend>
          <label className="tfield"><span>Document window</span>
            <QComboBox value={vp.displayMode} onChange={(e) => set({ displayMode: e.target.value as ViewPropsT['displayMode'] })}>
              {['Flat Lines', 'Shaded', 'Wireframe', 'Points'].map((m) => <option key={m} value={m}>{m}</option>)}</QComboBox></label>
        </fieldset>
        <fieldset className="tgroup"><legend>Material</legend>
          <div className="tfield"><QComboBox value="Default" onChange={() => {}} disabled><option value="Default">Default</option></QComboBox></div>
          <label className="tfield"><span>Custom appearance</span><label className="qbtn color-btn">Appearance
            <input type="color" value={hex(shape)} onChange={(e) => set({ shapeColor: parseInt(e.target.value.slice(1), 16) })} /></label></label>
          <label className="tfield"><span>Color plot</span><button className="qbtn" disabled>Color Plot</button></label>
          <label className="tfield"><span>Line color</span>{colorBtn(vp.lineColor, (v) => set({ lineColor: v }))}</label>
          <label className="tfield"><span>Point color</span>{colorBtn(vp.pointColor, (v) => set({ pointColor: v }))}</label>
        </fieldset>
        <fieldset className="tgroup"><legend>Display</legend>
          <label className="tfield"><span>Point size</span>{spin(vp.pointSize, 1, 64, (v) => set({ pointSize: v }))}</label>
          <label className="tfield"><span>Line width</span>{spin(vp.lineWidth, 1, 64, (v) => set({ lineWidth: v }))}</label>
          <div className="tfield-col"><span>Transparency</span><span className="tfield">
            <input type="range" min={0} max={100} value={vp.transparency} onChange={(e) => set({ transparency: Number(e.target.value) })} />{spin(vp.transparency, 0, 100, (v) => set({ transparency: v }))}</span></div>
          <div className="tfield-col"><span>Line transparency</span><span className="tfield">
            <input type="range" min={0} max={100} value={0} disabled onChange={() => {}} />{spin(0, 0, 100, () => {}, true)}</span></div>
        </fieldset>
      </TaskBox>
      <div className="tbuttons"><button className="qbtn" onClick={closeTask}>Close</button></div>
    </div>
  )
}

function DataProps({ b }: { b: Body }) {
  useStore((s) => s.units) // written again in a new unit system
  const pl = placementOf(b)
  const params = Object.entries(b.params ?? {})
  const vars = paramVars(b)
  const fc = toFreeCAD(pl)
  const setFC = (angle: number, axis: Vec3, position: Vec3) => place(b.name, b.placement ? pl : null, fromFreeCAD(angle, axis, position, pl.about))
  const at = (v: Vec3, i: number, n: number) => v.map((x, j) => (j === i ? n : x)) as Vec3
  const size = b.bbox ? b.bbox[1].map((hi, i) => qText(hi - b.bbox![0][i], 'Length')).join(' x ') : '-'
  return (
    <>
      <Group title="Base">
        <PlacementRow fc={fc} vars={vars} onCommit={setFC} />
        <Row k="Label" v={b.name} />
        <Row k="Part" v={b.part ?? '-'} />
        <Row k="Kind" v={b.kind} />
        <Row k="Material" v={b.material ?? '-'} />
      </Group>
      {params.length > 0 && b.part && (
        <Group title="Parameters">
          {params.map(([k, p]) => (p.editable
            ? <EditRow key={k} k={k} value={p.value} type={p.type} kind={paramKind(k, p.type)} vars={vars} onCommit={(v) => setParams(b.part!, { [k]: p.value }, { [k]: v })} />
            : <Row key={k} k={<span title="Not a plain literal in the part file, so it can't be edited here">{k}</span>} v={fmtValue(p.value)} />))}
        </Group>
      )}
      <Group title="Shape">
        <Row k="Mass" v={b.mass_g != null ? `${b.mass_g} g` : '-'} />
        <Row k="Bounding box" v={size} />
        {b.used_by && b.used_by.length > 0 && <Row k="Used by" v={b.used_by.join(', ')} />}
      </Group>
    </>
  )
}

const hex = (n: number) => '#' + n.toString(16).padStart(6, '0')
/** The View tab (ViewProviderPartExt's properties): Display Options, Object Style and
 *  Selection, as FreeCAD lists them. An edit applies to every selected object. */
function ViewProps({ b, off }: { b: Body; off: boolean }) {
  const s = useStore((st) => st), vp = viewOf(s, b.name), names = s.selected.includes(b.name) ? s.selected : [b.name]
  const set = (patch: Partial<ViewPropsT>) => setViewProps(names, patch)
  const bool = (k: string, v: boolean, f: (v: boolean) => void) => (
    <div className="prow"><span className="pk" style={pad(0)}>{k}</span>
      <span className="pv pbool"><input type="checkbox" checked={v} onChange={(e) => f(e.target.checked)} /></span></div>)
  const choice = <T extends string>(k: string, v: T, options: readonly T[], f: (v: T) => void) => (
    <div className="prow"><span className="pk" style={pad(0)}>{k}</span>
      <span className="pv"><QComboBox className="qselect-pv" value={v} onChange={(e) => f(e.target.value as T)}>{options.map((o) => <option key={o}>{o}</option>)}</QComboBox></span></div>)
  const color = (k: string, v: number, f: (v: number) => void) => (
    <div className="prow"><span className="pk" style={pad(0)}>{k}</span>
      <span className="pv"><label className="swatch-row"><input type="color" className="pcolor" value={hex(v)} onChange={(e) => f(parseInt(e.target.value.slice(1), 16))} />[{(v >> 16) & 255}, {(v >> 8) & 255}, {v & 255}]</label></span></div>)
  const number = (k: string, v: number, lo: number, hi: number, step: number, f: (v: number) => void, unit = '') => (
    <div className="prow"><span className="pk" style={pad(0)}>{k}</span>
      <span className="pv"><input type="number" className="pnum" min={lo} max={hi} step={step} value={v}
        onChange={(e) => { const n = Number(e.target.value); if (Number.isFinite(n)) f(Math.min(hi, Math.max(lo, n))) }} />{unit}</span></div>)
  const shape = vp.shapeColor ?? (b.color ? parseInt(b.color.slice(1), 16) : VIEW.shape)
  return (
    <>
      <Group title="Display Options">
        {bool('Bounding Box', vp.boundingBox, (v) => set({ boundingBox: v }))}
        {choice('Display Mode', vp.displayMode, ['Flat Lines', 'Shaded', 'Wireframe', 'Points'] as const, (v) => set({ displayMode: v }))}
        {bool('Show In Tree', vp.showInTree, (v) => set({ showInTree: v }))}
        {bool('Show Placement', vp.showPlacement, (v) => set({ showPlacement: v }))}
        {bool('Visibility', !off, () => toggleVisibility(names))}
      </Group>
      <Group title="Object Style">
        {number('Angular Deflection', vp.angularDeflection, 1, 180, 0.05, (v) => set({ angularDeflection: v }), ' °')}
        {number('Deviation', vp.deviation, 0.01, 100, 0.01, (v) => set({ deviation: v }))}
        {choice('Draw Style', vp.drawStyle, ['Solid', 'Dashed', 'Dotted', 'Dashdot'] as const, (v) => set({ drawStyle: v }))}
        {choice('Lighting', vp.lighting, ['One side', 'Two side'] as const, (v) => set({ lighting: v }))}
        {color('Line Color', vp.lineColor, (v) => set({ lineColor: v }))}
        {number('Line Width', vp.lineWidth, 1, 64, 1, (v) => set({ lineWidth: v }))}
        {color('Point Color', vp.pointColor, (v) => set({ pointColor: v }))}
        {number('Point Size', vp.pointSize, 1, 64, 1, (v) => set({ pointSize: v }))}
        {color('Shape Appearance', shape, (v) => set({ shapeColor: v }))}
        {number('Transparency', vp.transparency, 0, 100, 1, (v) => set({ transparency: Math.round(v) }))}
      </Group>
      <Group title="Selection">
        {choice('On Top When Selected', vp.onTop, ['Disabled', 'Enabled', 'Object', 'Element'] as const, (v) => set({ onTop: v }))}
        {bool('Selectable', !s.unselectable.includes(b.name), (v) => setState((st) => ({ unselectable: v ? st.unselectable.filter((n) => !names.includes(n)) : [...new Set([...st.unselectable, ...names])] })))}
        {choice('Selection Style', vp.selectionStyle, ['Shape', 'BoundBox'] as const, (v) => set({ selectionStyle: v }))}
      </Group>
    </>
  )
}

function Split({ top, bottom, storageKey }: { top: ReactNode; bottom: ReactNode; storageKey: string }) {
  const [frac, setFrac] = useState(() => saved.get('split.' + storageKey, 0.55))
  const ref = useRef<HTMLDivElement>(null)
  const last = useRef(frac)
  last.current = frac
  const drag = (e: React.PointerEvent) => {
    e.preventDefault()
    const box = ref.current!.getBoundingClientRect()
    const move = (ev: PointerEvent) => setFrac(Math.min(0.85, Math.max(0.15, (ev.clientY - box.top) / box.height)))
    const up = () => {
      removeEventListener('pointermove', move)
      removeEventListener('pointerup', up)
      saved.set('split.' + storageKey, last.current)
    }
    addEventListener('pointermove', move)
    addEventListener('pointerup', up)
  }
  return (
    <div className="split" ref={ref}>
      <div className="split-a" style={{ height: `${frac * 100}%` }}>{top}</div>
      <div className="split-h" onPointerDown={drag} />
      <div className="split-b">{bottom}</div>
    </div>
  )
}

// ── Tasks tab ────────────────────────────────────────────────────────────────
/** TaskView::keyPressEvent: Return clicks the task's default button; Esc its Cancel or Close. */
function taskKeys(e: React.KeyboardEvent<HTMLDivElement>) {
  if (e.defaultPrevented || (e.target as HTMLElement).closest('textarea, select, button')) return
  const root = e.currentTarget
  if (e.key === 'Enter') {
    const b = root.querySelector<HTMLButtonElement>('.tbuttons .qbtn.default')
    if (b) { e.preventDefault(); if (!b.disabled) b.click() }
  } else if (e.key === 'Escape') {
    const b = [...root.querySelectorAll<HTMLButtonElement>('.tbuttons .qbtn')].find((x) => /^(Cancel|Close)$/.test(x.textContent?.trim() ?? ''))
    e.preventDefault()
    e.stopPropagation()
    if (!b) closeTask()
    else if (!b.disabled) b.click()
  }
}

export function TasksPanel() {
  return <div className="taskview" onKeyDown={taskKeys}><TaskContent /></div>
}

function TaskContent() {
  const task = useStore((s) => s.task), scene = useStore((s) => s.scene)
  if (task?.kind === 'clip') return <ClipTask />
  if (task?.kind === 'info') return <InfoTask />
  if (task?.kind === 'units') return <UnitsTask />
  if (task?.kind === 'turntable') return <TurntableTask />
  if (task?.kind === 'shot') return <ShotTask />
  if (task?.kind === 'align' && task.other) return <AlignTask movable={task.body} fixed={task.other} />
  // Measure takes parts or their faces, edges and vertices ("body.Face3").
  if (task?.kind === 'measure') return <MeasureTask />
  // CAD Agent workbench tasks (agentwb.tsx): none of these edit a body, like the ones above.
  if (task?.kind === 'check' || task?.kind === 'verify' || task?.kind === 'done') return <GateTask verb={task.kind} />
  if (task?.kind === 'rules') return <RulesTask />
  if (task?.kind === 'cutlist') return <CutlistTask />
  if (task?.kind === 'tables') return <TablesTask />
  if (task?.kind === 'tool') return <ToolTask />
  if (task?.kind === 'bought') return <BoughtTask initial={task.other === 'import' ? 'add' : 'list'} />
  if (task?.kind === 'render') return <RenderTask />
  // Macro menu (macro.tsx): Std_DlgMacroRecord, Std_DlgMacroExecute (+ its Edit button), Std_Windows.
  if (task?.kind === 'macroRecord') return <MacroRecordTask />
  if (task?.kind === 'macros') return <MacrosTask />
  if (task?.kind === 'macroEdit') return <MacroEditTask name={task.body} />
  if (task?.kind === 'windows') return <WindowsTask />
  // File menu (filemenu.tsx): Std_New, Std_Open.
  if (task?.kind === 'newDocument') return <NewDocumentTask />
  if (task?.kind === 'openDocument') return <OpenDocumentTask />
  if (task?.kind === 'export') return <ExportTask />
  if (task?.kind === 'appearance') return <AppearanceTask />
  // Tools menu (tools.tsx): Std_DlgParameter, Std_SceneInspector, Std_DependencyGraph.
  if (task?.kind === 'parameterEditor') return <ParameterEditorTask />
  if (task?.kind === 'sceneInspector') return <SceneInspectorTask />
  if (task?.kind === 'dependencyGraph') return <DependencyGraphTask />
  const b = task && scene?.bodies.find((x) => x.name === task.body)
  if (!task || !b) {
    return (
      <div className="tasks">
        <TaskBox title="No active task" icon="help">
          <p className="hint">Double-click a part in the tree or in the 3D view to edit its parameters.
            A part without parameters opens Transform instead, as in FreeCAD. To move any part, select it and use
            Transform (drag it) or Placement (type it) from the toolbar or the Edit menu.</p>
        </TaskBox>
      </div>
    )
  }
  if (task.kind === 'params') return <ParamsTask key={b.name} b={b} />
  if (task.kind === 'mass') return <MassTask />
  return task.kind === 'placement' ? <PlacementTask key={b.name} b={b} /> : <TransformTask key={b.name} b={b} />
}

export function TaskBox({ title, icon, children }: { title: string; icon: IconName; children: ReactNode }) {
  const [open, setOpen] = useState(true)
  return (
    <div className="tbox">
      <div className="tbox-head" onClick={() => setOpen(!open)}><Icon name={icon} /><span>{title}</span><Twisty open={open} /></div>
      {open && <div className="tbox-body">{children}</div>}
    </div>
  )
}

export function TaskButtons({ onOk, onApply, okDisabled }: { onOk(): void; onApply?(): void; okDisabled?: boolean }) {
  return (
    <div className="tbuttons">
      <button className="qbtn default" disabled={okDisabled} onClick={onOk}>OK</button>
      {onApply && <button className="qbtn" disabled={okDisabled} onClick={onApply}>Apply</button>}
      <button className="qbtn" onClick={closeTask}>Cancel</button>
    </div>
  )
}

function ParamsTask({ b }: { b: Body }) {
  const entries = Object.entries(b.params ?? {})
  const [vals, setVals] = useState<Record<string, string>>(() => Object.fromEntries(entries.map(([k, p]) => [k, String(p.value)])))
  const bad = entries.some(([k, p]) => p.editable && parse(vals[k], p.type) === undefined)
  const ok = async () => {
    const changed = entries.filter(([k, p]) => p.editable && parse(vals[k], p.type) !== p.value)
    if (!changed.length || !b.part) return closeTask()
    const before = Object.fromEntries(changed.map(([k, p]) => [k, p.value]))
    const after = Object.fromEntries(changed.map(([k, p]) => [k, parse(vals[k], p.type)]))
    if (await setParams(b.part, before, after)) closeTask()
  }
  return (
    <div className="tasks">
      <TaskButtons onOk={ok} okDisabled={bad} />
      <TaskBox title={`${b.part ?? b.name} parameters`} icon="body">
        {!b.part || !entries.length
          ? <p className="hint">{b.name} has no parameters{b.kind === 'bought' ? ': it is a bought part' : ''}.</p>
          : <div className="tform">{entries.map(([k, p]) => (
              <label key={k} className="tfield"><span>{k}</span>
                {p.type === 'bool'
                  ? <QComboBox className="qselect-field" value={vals[k]} disabled={!p.editable} onChange={(e) => setVals({ ...vals, [k]: e.target.value })}>
                      <option>true</option><option>false</option></QComboBox>
                  : <input value={vals[k]} disabled={!p.editable} className={cls(p.editable && parse(vals[k], p.type) === undefined && 'bad')}
                      onChange={(e) => setVals({ ...vals, [k]: e.target.value })} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); if (!bad) ok() } }} />}
              </label>))}
            </div>}
        {b.part && <p className="hint">OK writes the new values into parts/{b.part}.py with <code>cad set</code>, then the checks re-run.</p>}
      </TaskBox>
    </div>
  )
}

const D2R = THREE.MathUtils.degToRad, R2D = THREE.MathUtils.radToDeg
const quatOfTurn = (t: Vec3) => new THREE.Quaternion().setFromEuler(new THREE.Euler(D2R(t[0]), D2R(t[1]), D2R(t[2]), 'XYZ'))
const turnOfQuat = (q: THREE.Quaternion): Vec3 => { const e = new THREE.Euler().setFromQuaternion(q, 'XYZ'); return [R2D(e.x), R2D(e.y), R2D(e.z)] }
const r6 = (n: number) => Math.round(n * 1e6) / 1e6 + 0

/** Std_Placement (Gui/Placement.cpp): Translation with Axial, Center (Use center of mass,
 *  Selected points), Rotation as axis and angle or Euler angles Z-Y′-X″, Apply incremental
 *  changes, Reset. Placement(position, rotation, center) moves p to R(p − center) + center +
 *  position, which is what placements.toml holds. Edits preview live; OK or Apply writes them. */
function PlacementTask({ b }: { b: Body }) {
  const cur = placementOf(b), q0 = quatOfTurn(cur.turn), aa0 = axisAngleOf(q0), ypr0 = yprOfQuat(q0)
  // setPlacementData: the fields show the placement as position and rotation; Center starts at
  // zero (a Base::Placement has no centre), so the stored pivot is folded into the position.
  const folded = new THREE.Vector3(...cur.move).add(new THREE.Vector3(...cur.about)).sub(new THREE.Vector3(...cur.about).applyQuaternion(q0))
  const init = { pos: folded.toArray() as Vec3, cnt: [0, 0, 0] as Vec3, axis: aa0.axis, angle: aa0.angle, ypr: ypr0 }
  const [f, setF] = useState(init)
  // setupRotationMethod: the rotation input last used (Placement/RotationMethod).
  const [mode, setMode] = useState<'axis' | 'euler'>(() => (saved.get<number>('placementRotationMethod', 0) === 1 ? 'euler' : 'axis'))
  const [incr, setIncr] = useState(false), [com, setCom] = useState(false), [axial, setAxial] = useState(0)
  const refPlacement = useRef<Placement | null>(null) // handler.setRefPlacement, when incremental is turned on
  const comCache = useRef<Vec3 | null>(null) // handler.setCenterOfMass: the centre used while Use center of mass is on
  // getInvalidInput: the boxes whose text isn't a valid value.
  const [invalid, setInvalid] = useState<ReadonlySet<string>>(new Set())
  const onValid = (key: string) => (ok: boolean) => setInvalid((x) => { const n = new Set(x); if (ok) n.delete(key); else n.add(key); return n })
  const rot = (x = f) => {
    if (mode === 'euler') { const [y, p, r] = x.ypr; return quatOfYpr(y, p, r) }
    const ax = new THREE.Vector3(...x.axis)
    return new THREE.Quaternion().setFromAxisAngle(ax.lengthSq() < 1e-12 ? new THREE.Vector3(0, 0, 1) : ax.normalize(), D2R(x.angle))
  }
  /** getPlacementData: the fields as a placement (getCenterData takes the cached centre of mass
   *  while Use center of mass is on); incremental, it applies on top of the object's placement. */
  const fields = (x = f): Placement => ({ move: x.pos, turn: turnOfQuat(rot(x)), about: com && comCache.current ? comCache.current : x.cnt })
  const target = (): Placement => (incr ? toPlacement(placementMatrix(fields()).multiply(placementMatrix(cur)), cur.about) : fields())
  /** onResetButtonClicked: every quantity field to zero. */
  const zeroed = (x: typeof f) => ({ ...x, pos: [0, 0, 0] as Vec3, cnt: [0, 0, 0] as Vec3, axis: [0, 0, 0] as Vec3, angle: 0, ypr: [0, 0, 0] as Vec3 })
  const reset = () => { setF(zeroed); setAxial(0) }
  // Live preview, as PlacementHandler applies it before OK.
  useEffect(() => {
    const delta = placementMatrix(target()).multiply(placementMatrix(cur).invert())
    getView()?.previewPlacement(b.name, delta)
  }, [f, mode, incr, b.placement])
  useEffect(() => () => getView()?.previewPlacement(b.name, null), [b.name])
  const apply = async () => {
    if (invalid.size) {
      // onApply: focus the faulty box and say so.
      document.querySelector<HTMLInputElement>('.taskview .qsb input[data-invalid]')?.focus()
      await messageBox('critical', 'Incorrect Quantity', 'There are input fields with incorrect input. Ensure valid placement values!')
      return false
    }
    const t = target()
    getView()?.previewPlacement(b.name, null)
    const ok = await place(b.name, b.placement ? cur : null, { move: t.move.map(r6) as Vec3, turn: t.turn.map(r6) as Vec3, about: t.about.map(r6) as Vec3 })
    if (ok && incr) reset()
    if (ok) saved.set('placementRotationMethod', mode === 'euler' ? 1 : 0)
    return ok
  }
  const setAt = (k: 'pos' | 'cnt' | 'axis' | 'ypr', i: number) => (v: number) => setF((x) => ({ ...x, [k]: x[k].map((t, j) => (j === i ? v : t)) as Vec3 }))
  const [ask, setAsk] = useState<ExprAsk | null>(null)
  const eq = (dims: Dims | null, apply: (v: number) => void) => (text: string, at: { x: number; y: number }) => setAsk({ text, at, dims, apply })
  const box = (k: 'pos' | 'cnt' | 'axis' | 'ypr', i: number, dims: Dims, extra: { min?: number; max?: number; disabled?: boolean; title?: string } = {}) =>
    <QuantityBox value={f[k][i]} dims={dims} onChange={setAt(k, i)} onValid={onValid(`${k}${i}`)} onEquals={eq(dims.every((d) => d === 0) ? null : dims, setAt(k, i))} {...extra} />
  const xyz = (k: 'pos' | 'cnt', disabled = false) => ['X', 'Y', 'Z'].map((l, i) => (
    <label key={l} className="tfield"><span>{l}</span>{box(k, i, LENGTH, { disabled })}</label>))
  /** onCenterOfMassToggled: computeCenterOfMass over the selection (zero if it can't). */
  const useCom = async (on: boolean) => {
    setCom(on)
    if (!on) return
    const slug = getState().slug, first = getState().selected[0] ?? b.name
    const r = slug ? await api.mass(slug, [first]).catch(() => null) : null
    const c = ((r?.data?.cog as Vec3 | undefined) ?? [0, 0, 0]).slice() as Vec3
    comCache.current = c
    setF((x) => ({ ...x, cnt: c }))
  }
  /** onSelectedVertexClicked: the picked points (a vertex, or where a face or edge was
   *  clicked). One is the centre; two put the centre between them and the axis from the first
   *  to the second; three put the centre on the first and the axis normal to their plane. Two
   *  and three keep the rotation's angle. Shift copies the distance or angle. */
  const selectedPoints = (e: React.MouseEvent) => {
    const v = getView(), st = getState()
    const pts = st.subSel.map((r) => {
      const g = v?.subGeometry(r)
      if (g?.kind === 'Vertex') return g.point
      const p = st.subPts[r]
      return p ? new THREE.Vector3(p[0], p[1], p[2]) : null
    }).filter((p): p is THREE.Vector3 => !!p)
    setCom(false)
    comCache.current = null
    const angle = axisAngleOf(rot()).angle
    let center = new THREE.Vector3(), ok = true
    if (pts.length === 1) center = pts[0]
    else if (pts.length === 2) {
      center = pts[0].clone().add(pts[1]).multiplyScalar(0.5)
      const axis = pts[1].clone().sub(pts[0]), length = axis.length()
      report('msg', `Distance: ${length.toFixed(8)}`)
      if (e.shiftKey) navigator.clipboard?.writeText(fmtG(length, 8))
      else report('msg', '(Shift + click selected points button to copy distance to clipboard)')
      setF((x) => ({ ...x, axis: axis.normalize().toArray() as Vec3, angle }))
      setMode('axis')
    } else if (pts.length === 3) {
      const [bb, a, c] = pts, norm = a.clone().sub(bb).cross(c.clone().sub(bb)).normalize()
      center = bb
      report('msg', `Distance: ${a.distanceTo(c).toFixed(8)}`)
      const target = R2D(a.clone().sub(bb).normalize().angleTo(c.clone().sub(bb).normalize()))
      report('msg', `Target angle: ${target.toFixed(8)} degrees, complementary: ${(90 - target).toFixed(8)} degrees`)
      if (e.shiftKey) {
        navigator.clipboard?.writeText(fmtG(target, 8))
        report('msg', '(Angle copied to clipboard, but you might need to use a negative (-) angle sometimes.)')
      } else report('msg', '(Shift + click selected points button to copy angle to clipboard)')
      setF((x) => ({ ...x, axis: norm.toArray() as Vec3, angle }))
      setMode('axis')
    } else ok = false
    setF((x) => ({ ...x, cnt: center.toArray() as Vec3 }))
    if (!ok) {
      report('warn', 'Placement selection error.  Select either 1 or 2 points.')
      messageBox(null, '', 'Select 1, 2, or 3 points before clicking this button. A point may be on a vertex, face, or edge.  If on a face or edge the point used will be the point at the mouse position along face or edge.  If 1 point is selected it will be used as the center of rotation.  If 2 points are selected the midpoint between them will be the center of rotation and a new custom axis will be created, if needed.  If 3 points are selected the first point becomes the center of rotation and lies on the vector that is normal to the plane defined by the 3 points.  Some distance and angle information is provided in the report view, which can be useful when aligning objects.  For your convenience when Shift + click is used the appropriate distance or angle is copied to the clipboard.')
    }
  }
  const applyAxial = (e: React.MouseEvent) => {
    const { axis } = axisAngleOf(rot()), sign = e.shiftKey ? -1 : 1
    setF((x) => ({ ...x, pos: x.pos.map((p, i) => p + sign * axis[i] * axial) as Vec3 }))
  }
  return (
    <div className="tasks">
      <TaskBox title="Placement" icon="placement">
        <div className="tcols">
          <fieldset className="tgroup tg"><legend>Translation</legend>
            {xyz('pos')}
            <label className="tfield"><span>Axial</span><QuantityBox value={axial} dims={LENGTH} onChange={setAxial} onValid={onValid('axial')} onEquals={eq(LENGTH, setAxial)} /></label>
            <div className="tfield"><span /><button className="qbtn" title="Shift-click for opposite direction" onClick={applyAxial}>Apply Axial</button></div>
          </fieldset>
          <fieldset className="tgroup tg"><legend>Center</legend>
            {xyz('cnt', com)}
            <label className="tcheck"><input type="checkbox" checked={com} onChange={(e) => useCom(e.target.checked)} /> Use center of mass</label>
            <button className="qbtn" onClick={selectedPoints} title="Uses the selected vertices: one sets the center, two or three the axis">Selected Points</button>
          </fieldset>
        </div>
        <fieldset className="tgroup tg"><legend>Rotation</legend>
          <QComboBox value={mode} onChange={(e) => {
            const m = e.target.value as 'axis' | 'euler', q = rot()
            if (m === 'euler') setF((x) => ({ ...x, ypr: yprOfQuat(q) }))
            else { const { axis, angle } = axisAngleOf(q); setF((x) => ({ ...x, axis, angle })) }
            // The page left behind can't hold the dialog up.
            const gone = mode === 'euler' ? ['ypr0', 'ypr1', 'ypr2'] : ['axis0', 'axis1', 'axis2', 'angle']
            setInvalid((x) => new Set([...x].filter((k) => !gone.includes(k))))
            setMode(m)
          }}><option value="axis">Rotation axis and angle</option><option value="euler">Euler angles (Z–Y′–X″)</option></QComboBox>
          {mode === 'axis' ? <>
            <div className="tfield top"><span>Axis</span><span className="tstack">{[0, 1, 2].map((i) => <span key={i}>{box('axis', i, NUMBER)}</span>)}</span></div>
            <label className="tfield"><span>Angle</span><QuantityBox value={f.angle} dims={ANGLE} onChange={(v) => setF((x) => ({ ...x, angle: v }))} onValid={onValid('angle')} onEquals={eq(ANGLE, (v) => setF((x) => ({ ...x, angle: v })))} /></label></>
            : <>
              <label className="tfield"><span>Yaw (around Z-axis)</span>{box('ypr', 0, ANGLE, { min: -180, max: 180, title: 'Yaw (around Z-axis)' })}</label>
              <label className="tfield"><span>Pitch (around Y-axis)</span>{box('ypr', 1, ANGLE, { min: -90, max: 90, title: 'Pitch (around Y-axis)' })}</label>
              <label className="tfield"><span>Roll (around X-axis)</span>{box('ypr', 2, ANGLE, { min: -180, max: 180, title: 'Roll (around the X-axis)' })}</label></>}
        </fieldset>
        <div className="hbox spread">
          <label className="tcheck"><input type="checkbox" checked={incr} onChange={(e) => {
            // onApplyIncrementalPlacementToggled: on, the fields' placement becomes the reference and
            // they start from nothing; off, they show the change on top of that reference.
            if (e.target.checked) { refPlacement.current = fields(); reset() }
            else if (refPlacement.current) {
              const total = placementMatrix(fields()).multiply(placementMatrix(refPlacement.current))
              const p = toPlacement(total, [0, 0, 0]), q = quatOfTurn(p.turn), aa = axisAngleOf(q)
              setF((x) => ({ ...x, pos: p.move, axis: aa.axis, angle: aa.angle, ypr: yprOfQuat(q) }))
            }
            setIncr(e.target.checked)
          }} /> Apply incremental changes</label>
          <button className="qbtn" onClick={reset}>Reset</button>
        </div>
        {b.placement && <div className="tbuttons"><button className="qbtn" onClick={async () => { getView()?.previewPlacement(b.name, null); if (await place(b.name, cur, null)) closeTask() }}>Reset to the code's position</button></div>}
      </TaskBox>
      {ask && <ExpressionDialog at={ask.at} text={ask.text} dims={ask.dims} vars={paramVars(b)} onOk={(v) => { ask.apply(v); setAsk(null) }} onCancel={() => setAsk(null)} />}
      {/* TaskPlacement: ButtonPosition South. */}
      <TaskButtons onApply={apply} onOk={async () => { if (await apply()) closeTask() }} />
      <p className="hint">{b.name}: a rigid move on top of assembly.py, kept in placements.toml. The agent folds it into the code.</p>
    </div>
  )
}

export const vec = (v: number[]) => `[${v.map(fmtNum).join(', ')}]`

/** Std_ProjectInfo: what this project is, where it lives, and where it stands. */
function InfoTask() {
  const slug = useStore((s) => s.slug), projects = useStore((s) => s.projects), scene = useStore((s) => s.scene)
  const status = useStore((s) => s.status), checks = useStore((s) => s.checks)
  const p = projects.find((x) => x.slug === slug), bb = scene?.bbox
  const rows = checks?.rows ?? [], fails = rows.filter((r) => r.state === 'FAIL').length, open = rows.filter((r) => r.state === 'UNCHECKED').length
  return (
    <div className="tasks">
      <div className="tbuttons"><button className="qbtn default" onClick={closeTask}>Close</button></div>
      <TaskBox title="Document Information" icon="document">
        <table className="ctable wrap"><tbody>
          <tr><td>Name</td><td>{slug}</td></tr>
          <tr><td>Folder</td><td>{p ? `${p.root}/${slug}` : '-'}</td></tr>
          <tr><td>Parts</td><td>{scene ? `${scene.bodies.length} bodies, ${new Set(scene.bodies.map((b) => b.part).filter(Boolean)).size} part files` : '-'}</td></tr>
          <tr><td>Size</td><td>{bb ? bb[1].map((hi, i) => fmtNum(hi - bb[0][i])).join(' x ') + ' ' + (scene?.units ?? 'mm') : '-'}</td></tr>
          <tr><td>Mesh</td><td>{scene ? `${scene.triangles} triangles` : '-'}</td></tr>
          <tr><td>Checks</td><td>{rows.length ? `${rows.length} rows: ${fails} failing, ${open} unchecked` : 'not run'}</td></tr>
          <tr><td>Verdict</td><td>{status?.done ? 'done' : status?.verdict ?? 'not verified'}</td></tr>
          {status?.reasons?.map((r, i) => <tr key={i}><td /><td>{r}</td></tr>)}
          <tr><td>Source hash</td><td>{scene?.source_hash?.slice(0, 12) ?? '-'}</td></tr>
        </tbody></table>
      </TaskBox>
    </div>
  )
}

/** Std_DlgPreferences, for what this UI has: navigation, display, Transform snap. */
/** Std_DlgPreferences: the parts of FreeCAD's Navigation and 3D View pages that apply here. */
/** The Preferences dialog's pages (DlgPreferencesImp's stacked pages), one at a time. */
export function PrefsPage({ page }: { page: string }) {
  const nav = useStore((s) => s.nav), animate = useStore((s) => s.animate), cube = useStore((s) => s.cube), ortho = useStore((s) => s.ortho)
  const p = useStore((s) => s.navPrefs), home = useStore((s) => s.homeView), newDocScale = useStore((s) => s.newDocCameraScale)
  const units = useStore((s) => s.units), corner = useStore((s) => s.corner)
  const axes = useStore((s) => s.axes), axisColors = useStore((s) => s.axisColors), showFPS = useStore((s) => s.showFPS)
  const nc = useStore((s) => s.naviCube), rc = useStore((s) => s.rotationCenter), noTilt = useStore((s) => s.disableTouchTilt)
  const recordGui = useStore((s) => s.recordGuiCommands), guiAsComment = useStore((s) => s.guiAsComment)
  const np = useStore((s) => s.notifyPrefs)
  const toolbarIconSize = useStore((s) => s.toolbarIconSize)
  const [recentMacros, setRecentMacros] = useState(() => saved.get('recentMacrosSize', 12))
  const [macroDir, setMacroDir] = useState('')
  useEffect(() => { if (page === 'Macro') api.macros().then((r) => setMacroDir(r.dir)).catch(() => {}) }, [page])
  const [recentSize, setRecentSize] = useState(() => saved.get('recentFilesSize', 4))
  const [snap, setSnap] = useState(() => saved.get('snap', { mm: 1, deg: 5 }))
  const set = (k: 'animate' | 'disableTouchTilt' | 'axes' | 'showFPS' | 'recordGuiCommands' | 'guiAsComment', v: boolean) => { setState({ [k]: v }); saved.set(k, v) }
  const pref = (patch: Partial<NavPrefs>) => setState((s) => { const navPrefs = { ...s.navPrefs, ...patch }; saved.set('navPrefs', navPrefs); return { navPrefs } })
  // CornerNaviCube moves the cube to that corner (and wherever a drag had left it).
  const cubePref = (patch: Partial<NaviCubePrefs>) => setState((s) => {
    const naviCube = { ...s.naviCube, ...patch }
    saved.set('naviCube', naviCube)
    if (patch.corner === undefined) return { naviCube }
    // A corner picked here puts the cube back in it (CornerNaviCube; the drag position is cleared).
    saved.set('cubePos', CORNER_POS[patch.corner])
    return { naviCube, cubePlace: (['top-left', 'top-right', 'bottom-left', 'bottom-right'] as const)[patch.corner], cubePos: CORNER_POS[patch.corner] }
  })
  const rcPref = (patch: Partial<RotationCenterPrefs>) => setState((s) => { const rotationCenter = { ...s.rotationCenter, ...patch }; saved.set('rotationCenter', rotationCenter); return { rotationCenter } })
  const setScale = (v: number) => { setState({ newDocCameraScale: v }); saved.set('newDocCameraScale', v) }
  const setAxisColor = (k: keyof AxisColors, v: string) => setState((s) => { const axisColors = { ...s.axisColors, [k]: v }; saved.set('axisColors', axisColors); return { axisColors } })
  const num = (v: string, lo: number, hi: number, d: number) => { const n = Number(v); return Number.isFinite(n) ? Math.min(hi, Math.max(lo, n)) : d }
  // A checkable QGroupBox: its check box in the title turns the whole group on or off.
  const checkGroup = (title: string, on: boolean, toggle: (on: boolean) => void, children: ReactNode) => (
    <fieldset className="tgroup tg">
      <legend><label className="tcheck"><input type="checkbox" checked={on} onChange={(e) => toggle(e.target.checked)} /> {title}</label></legend>
      <fieldset className="tg-body" disabled={!on}>{children}</fieldset>
    </fieldset>)
  /** DlgSettingsNavigation::onMouseButtonClicked: the style's Selection, Panning, Rotation and Zooming. */
  const mouseButtons = () => {
    const n = NAV_STYLES.find((x) => x.id === nav)!
    messageBox(null, 'Mouse Buttons', `Configuration ${n.name}\n\nSelection: ${n.hints[0]}\nPanning: ${n.hints[1]}\nRotation: ${n.hints[2]}\nZooming: ${n.hints[3]}`)
  }
  return (
    <>
      {/* DlgSettingsGeneral.ui: Language and Number Format, Application, Preference Packs — what
          applies here works (units, toolbar icon size, recent file list); the rest shows, disabled. */}
      {page === 'General' && <div className="pref-content">
        <fieldset className="tgroup tg"><legend>Language and Number Format</legend>
          <label className="tfield"><span>Language</span><QComboBox className="qselect-field" value="en" disabled onChange={() => {}}><option value="en">English</option></QComboBox></label>
          <label className="tfield"><span>Default unit system</span>
            <QComboBox className="qselect-field" value={units.schema} onChange={(e) => setUnits({ schema: Number(e.target.value) })}>
              {quantity.SCHEMAS.map((x) => <option key={x.num} value={x.num}>{x.description}</option>)}
            </QComboBox></label>
          <label className="tfield"><span>Number of decimals</span>
            <input type="number" min={1} max={12} value={units.decimals} onChange={(e) => setUnits({ decimals: Math.round(num(e.target.value, 1, 12, 2)) })} /></label>
          <label className="tcheck" title="n/a: projects here carry no unit system of their own"><input type="checkbox" disabled />Ignore project unit system and use default</label>
          <label className="tfield"><span>Minimum fractional inch</span>
            <QComboBox className="qselect-field" value={units.denominator} disabled={!quantity.SCHEMAS.find((x) => x.num === units.schema)?.multLen} onChange={(e) => setUnits({ denominator: Number(e.target.value) })}>
              {[2, 4, 8, 16, 32, 64, 128].map((d) => <option key={d} value={d}>1/{d}"</option>)}
            </QComboBox></label>
          <label className="tfield"><span>Number format</span><QComboBox className="qselect-field" value="os" disabled onChange={() => {}}>
            <option value="os">Operating system</option><option value="lang">Selected language</option><option value="c">C/POSIX</option></QComboBox></label>
          <label className="tcheck"><input type="checkbox" disabled />Substitute decimal separator</label>
        </fieldset>
        <fieldset className="tgroup tg"><legend>Application</legend>
          <label className="tfield"><span>Theme</span><QComboBox className="qselect-field" value="light" disabled onChange={() => {}}><option value="light">FreeCAD Light</option></QComboBox></label>
          <span className="hint">Looking for more themes? You can obtain them using the Addon Manager.</span>
          <label className="tfield"><span>Size of toolbar icons</span>
            <QComboBox className="qselect-field" value={toolbarIconSize} onChange={(e) => { const v = Number(e.target.value); setState({ toolbarIconSize: v }); saved.set('toolbarIconSize', v) }}>
              {([['Small', 16], ['Medium', 24], ['Large', 32], ['Extra large', 48]] as const).map(([l, v]) => <option key={v} value={v}>{l} ({v}px)</option>)}
            </QComboBox></label>
          <label className="tfield"><span>Tree View and Property View mode</span><QComboBox className="qselect-field" value="combined" disabled onChange={() => {}}>
            <option value="combined">Combined</option><option value="independent">Independent</option></QComboBox></label>
          <label className="tfield"><span>Size of recent file list</span>
            <input type="number" min={0} max={12} value={recentSize} onChange={(e) => { const v = Math.round(num(e.target.value, 0, 12, 4)); setRecentSize(v); saved.set('recentFilesSize', v) }} /></label>
          {['Enable tiled background', 'Enable cursor blinking', 'Enable splash screen at start-up', 'Activate overlay panels', 'Ignore mouse wheel on hover focused input fields', 'Fine-grained recompute (experimental)'].map((t) => (
            <label key={t} className="tcheck"><input type="checkbox" disabled />{t}</label>))}
        </fieldset>
        <fieldset className="tgroup tg"><legend>Preference Packs</legend>
          <table className="pref-packs"><thead><tr><th>Name</th><th>Type</th><th>Load</th></tr></thead>
            <tbody><tr><td>FreeCAD Light</td><td>Theme</td><td><button className="qbtn" disabled>Load</button></td></tr></tbody></table>
          <div className="tbuttons">{['Import Configuration', 'Save as New', 'Manage', 'Revert'].map((t) => <button key={t} className="qbtn" disabled>{t}</button>)}</div>
        </fieldset>
      </div>}
      {/* DlgSettingsNotificationArea.ui: NotificationAreaEnabled contains Additional Data Sources,
          Notifications List and (nested) Enable Pop-Up Notifications, in that row order. */}
      {page === 'Notification Area' && <div className="pref-content">
        {checkGroup('Enable Notification Area', np.areaEnabled, (on) => setNotifyPrefs({ areaEnabled: on }), <>
          <fieldset className="tgroup tg"><legend>Additional Data Sources</legend>
            <label className="tcheck" title="Errors intended for developers will appear in the notification area">
              <input type="checkbox" checked={np.developerErrors} onChange={(e) => setNotifyPrefs({ developerErrors: e.target.checked })} /> Debug errors</label>
            <label className="tcheck" title="Warnings intended for developers will appear in the notification area">
              <input type="checkbox" checked={np.developerWarnings} onChange={(e) => setNotifyPrefs({ developerWarnings: e.target.checked })} /> Debug warnings</label>
          </fieldset>
          <fieldset className="tgroup tg"><legend>Notifications List</legend>
            <label className="tfield" title="Limits the number of notifications kept in the list (0 = no limit)"><span>Maximum notification count</span>
              <input type="number" min={0} max={10000} value={np.maxWidgetMessages} onChange={(e) => setNotifyPrefs({ maxWidgetMessages: Math.round(num(e.target.value, 0, 10000, 1000)) })} /></label>
            <label className="tcheck" title="Removes the user notifications from the list after the pop-up's maximum duration has lapsed">
              <input type="checkbox" checked={np.autoRemoveUserNotifications} onChange={(e) => setNotifyPrefs({ autoRemoveUserNotifications: e.target.checked })} /> Auto-remove user notifications</label>
          </fieldset>
          {checkGroup('Enable Pop-Up Notifications', np.popupEnabled, (on) => setNotifyPrefs({ popupEnabled: on }), <>
            <label className="tfield" title="Maximum amount of time the notification will be shown, unless dismissed by a click"><span>Maximum duration</span>
              <span className="qsuffix"><input type="number" min={0} max={120} value={np.maxDuration} onChange={(e) => setNotifyPrefs({ maxDuration: Math.round(num(e.target.value, 0, 120, 20)) })} /><span className="unit">s</span></span></label>
            <label className="tfield" title="Minimum amount of time the notification will be shown before an outside click can dismiss it"><span>Minimum duration</span>
              <span className="qsuffix"><input type="number" min={0} max={120} value={np.minDuration} onChange={(e) => setNotifyPrefs({ minDuration: Math.round(num(e.target.value, 0, 120, 5)) })} /><span className="unit">s</span></span></label>
            <label className="tfield" title="Maximum number of notifications that will be simultaneously present on the notification bubble"><span>Maximum concurrent notification count</span>
              <input type="number" min={0} max={1000} value={np.maxOpenNotifications} onChange={(e) => setNotifyPrefs({ maxOpenNotifications: Math.round(num(e.target.value, 0, 1000, 15)) })} /></label>
            <label className="tfield" title="Width of the pop-up notification bubble in pixels"><span>Notification bubble width</span>
              <span className="qsuffix"><input type="number" min={300} max={10000} value={np.notificationWidth} onChange={(e) => setNotifyPrefs({ notificationWidth: Math.round(num(e.target.value, 300, 10000, 800)) })} /><span className="unit">px</span></span></label>
            <label className="tcheck" title="Any open pop-up notifications will disappear when another window is activated">
              <input type="checkbox" checked={np.hideWhenDeactivated} onChange={(e) => setNotifyPrefs({ hideWhenDeactivated: e.target.checked })} /> Hide when other window is activated</label>
            <label className="tcheck" title="Prevent pop-up notifications from appearing when the FreeCAD window is not the active window">
              <input type="checkbox" checked={np.preventWhenInactive} onChange={(e) => setNotifyPrefs({ preventWhenInactive: e.target.checked })} /> Do not show when window is inactive</label>
          </>)}
        </>)}
      </div>}
      {page === 'Navigation' && <div className="pref-content">
        {checkGroup('Navigation Cube', cube, (on) => setState({ cube: on }), <>
          <label className="tfield" title="Number of steps by turn when using arrows (default = 8 : step angle = 360/8 = 45 deg)"><span>Steps by turn</span>
            <input type="number" min={4} max={36} value={nc.stepByTurn} onChange={(e) => cubePref({ stepByTurn: Math.round(num(e.target.value, 4, 36, 8)) })} /></label>
          <label className="tfield" title="Corner where the navigation cube is displayed"><span>Corner</span>
            <QComboBox className="qselect-field" value={nc.corner} onChange={(e) => cubePref({ corner: Number(e.target.value) as NaviCubePrefs['corner'] })}>
              {['Top left', 'Top right', 'Bottom left', 'Bottom right'].map((c, i) => <option key={c} value={i}>{c}</option>)}
            </QComboBox></label>
          <label className="tcheck" title="Rotates to nearest possible state when clicking a cube face"><input type="checkbox" checked={nc.toNearest} onChange={(e) => cubePref({ toNearest: e.target.checked })} /> Rotate to nearest</label>
          <label className="tfield" title="Font name of the navigation cube"><span>Font name</span>
            <QComboBox className="qselect-field" value={nc.font} onChange={(e) => cubePref({ font: e.target.value })}>
              <option value="">Default</option>{['Arial', 'Helvetica', 'Verdana', 'Tahoma', 'Trebuchet MS', 'Georgia', 'Times New Roman', 'Courier New'].map((f) => <option key={f}>{f}</option>)}
            </QComboBox></label>
          <label className="tfield" title="Size of the navigation cube"><span>Cube size</span>
            <span className="qsuffix"><input type="number" min={10} max={1024} step={10} value={nc.size} onChange={(e) => cubePref({ size: Math.round(num(e.target.value, 10, 1024, 132)) })} /><span className="unit">px</span></span></label>
          <label className="tfield" title="Opacity of the navigation cube when not focused"><span>Opacity when inactive</span>
            <span className="qsuffix"><input type="number" min={1} max={100} value={nc.inactiveOpacity} onChange={(e) => cubePref({ inactiveOpacity: Math.round(num(e.target.value, 1, 100, 50)) })} /><span className="unit">%</span></span></label>
          <label className="tfield" title="Base color for all elements"><span>Color</span><input type="color" value={nc.color} onChange={(e) => cubePref({ color: e.target.value })} /></label>
        </>)}
        {checkGroup('Rotation Center Indicator', p.showRotationCenter, (on) => pref({ showRotationCenter: on }), <>
          <label className="tfield" title="The size of the rotation center indicator"><span>Sphere size</span>
            <input type="number" min={1} max={100} step={0.5} value={rc.size} onChange={(e) => rcPref({ size: num(e.target.value, 1, 100, 5) })} /></label>
          <label className="tfield" title="The color of the rotation center indicator"><span>Color and transparency</span>
            <span className="hbox"><input type="color" value={rc.color} onChange={(e) => rcPref({ color: e.target.value })} />
              <input type="range" min={0} max={1} step={0.05} value={rc.alpha} onChange={(e) => rcPref({ alpha: Number(e.target.value) })} /></span></label>
        </>)}
        <fieldset className="tgroup tg"><legend>Navigation</legend>
          <label className="tfield" title="Navigation settings set"><span>3D navigation</span>
            <QComboBox className="qselect-field" value={nav} onChange={(e) => setNav(e.target.value as NavStyle)}>
              {NAV_STYLES.map((n) => <option key={n.id} value={n.id}>{n.name}</option>)}
            </QComboBox></label>
          <div className="tfield"><span /><button className="qbtn" title="Lists the mouse button configs for each chosen navigation setting" onClick={mouseButtons}>Mouse Configuration</button></div>
          <label className="tfield"><span>Orbit style</span>
            <QComboBox className="qselect-field" value={p.orbit} onChange={(e) => pref({ orbit: Number(e.target.value) as OrbitStyle })}>
              {[4, 1, 3, 2, 0].map((o) => <option key={o} value={o}>{ORBIT_STYLES[o]}</option>)}
            </QComboBox></label>
          <label className="tfield"><span>Rotation mode</span>
            <QComboBox className="qselect-field" value={p.rotationMode} onChange={(e) => pref({ rotationMode: Number(e.target.value) as 0 | 1 | 2 })}>
              <option value={0}>Window center</option><option value={1}>Drag at cursor</option><option value={2}>Object center</option>
            </QComboBox></label>
          <label className="tfield" title="Default camera orientation when creating a new document or selecting the home view"><span>Default camera orientation</span>
            <QComboBox className="qselect-field" value={home} onChange={(e) => setHomeView(e.target.value as HomeView)}>
              {['Isometric', 'Dimetric', 'Trimetric', 'Top', 'Front', 'Left', 'Right', 'Rear', 'Bottom'].map((v) => <option key={v}>{v}</option>)}
            </QComboBox></label>
          <label className="tfield" title="Sets camera zoom for new documents. The value is the diameter of the sphere to fit on the screen."><span>Camera zoom</span>
            <QuantityBox value={newDocScale} dims={LENGTH} min={0.00001} max={10000000} onChange={setScale} /></label>
          <label className="tcheck" title="Zoom operations will be performed at position of mouse pointer"><input type="checkbox" checked={p.zoomAtCursor} onChange={(e) => pref({ zoomAtCursor: e.target.checked })} /> Zoom at cursor</label>
          <label className="tfield"><span>Zoom step</span>
            <input type="number" min={0.01} max={1} step={0.05} value={p.zoomStep} onChange={(e) => pref({ zoomStep: num(e.target.value, 0.01, 1, 0.2) })} /></label>
          <label className="tcheck" title="Direction of zoom operations will be inverted"><input type="checkbox" checked={p.invertZoom} onChange={(e) => pref({ invertZoom: e.target.checked })} /> Invert zoom</label>
          <label className="tcheck" title="Prevents view tilting when pinch-zooming"><input type="checkbox" checked={noTilt} onChange={(e) => set('disableTouchTilt', e.target.checked)} /> Disable touchscreen tilt gesture</label>
          <label className="tcheck" title="Two-finger scroll on a touchpad pans the view"><input type="checkbox" checked={p.touchpadScrollPans} onChange={(e) => pref({ touchpadScrollPans: e.target.checked })} /> Touchpad scroll pans instead of zooming</label>
        </fieldset>
        <fieldset className="tgroup tg"><legend>Space Mouse</legend>
          <label className="tcheck" title="A browser can't talk to a 3D mouse's driver"><input type="checkbox" disabled /> Enable support of legacy SpaceMouse devices</label>
        </fieldset>
        {checkGroup('Animations', animate, (on) => set('animate', on), <>
          <label className="tfield" title="The duration of navigation animations in milliseconds"><span>Animation duration</span>
            <span className="qsuffix"><input type="number" min={100} max={10000} step={50} value={p.duration} onChange={(e) => pref({ duration: num(e.target.value, 100, 10000, 500) })} /><span className="unit">ms</span></span></label>
          <label className="tcheck" title="Enable spinning animations that are used in some navigation styles after dragging"><input type="checkbox" checked={p.spinning} onChange={(e) => pref({ spinning: e.target.checked })} /> Enable spinning animations</label>
        </>)}
        <fieldset className="tgroup tg"><legend>Clarify Selection</legend>
          <label className="tcheck" title="Enable Clarify Selection on long press of left mouse button"><input type="checkbox" checked={p.clarifyLongPress} onChange={(e) => pref({ clarifyLongPress: e.target.checked })} /> Enable long press clarify selection</label>
          <label className="tfield" title="Duration in seconds to hold left mouse button before triggering Clarify Selection"><span>Long press timeout</span>
            <span className="qsuffix"><input type="number" min={0.3} max={3} step={0.1} value={p.longPressTimeout} onChange={(e) => pref({ longPressTimeout: num(e.target.value, 0.3, 3, 1) })} /><span className="unit">s</span></span></label>
        </fieldset>
      </div>}
      {page === '3D View' && <div className="pref-content">
        <fieldset className="tgroup tg"><legend>General</legend>
          <label className="tcheck" title="Main coordinate system will always be shown in the lower right corner within opened files">
            <input type="checkbox" checked={corner.show} onChange={(e) => setCorner({ show: e.target.checked })} /> Show coordinate system in the corner</label>
          <label className="tfield" title="Size of main coordinate system representation in the corner, in % of the height or width of the view"><span>Relative size</span>
            <span className="qsuffix"><input type="number" min={2} max={100} disabled={!corner.show} value={corner.size} onChange={(e) => setCorner({ size: Math.round(num(e.target.value, 2, 100, 10)) })} /><span className="unit">%</span></span></label>
          <label className="tfield" title="Axis letter and FPS counter color"><span>Letter color</span><input type="color" value={axisColors.letter} onChange={(e) => setAxisColor('letter', e.target.value)} /></label>
          <label className="tfield"><span>X-axis color</span><input type="color" value={axisColors.x} onChange={(e) => setAxisColor('x', e.target.value)} /></label>
          <label className="tfield"><span>Y-axis color</span><input type="color" value={axisColors.y} onChange={(e) => setAxisColor('y', e.target.value)} /></label>
          <label className="tfield"><span>Z-axis color</span><input type="color" value={axisColors.z} onChange={(e) => setAxisColor('z', e.target.value)} /></label>
          <label className="tcheck" title="Axis cross will be shown by default at file opening or creation"><input type="checkbox" checked={axes} onChange={(e) => set('axes', e.target.checked)} /> Show axis cross by default</label>
          <label className="tcheck" title="Time needed for last operation and resulting frame rate will be shown at the lower left corner in opened files"><input type="checkbox" checked={showFPS} onChange={(e) => set('showFPS', e.target.checked)} /> Show counter of frames per second</label>
        </fieldset>
        {/* DlgSettings3DView.ui's Rendering group: OpenGL settings, fixed in a browser's WebGL. */}
        <fieldset className="tgroup tg"><legend>Rendering</legend>
          <label className="tcheck"><input type="checkbox" disabled /> Use software OpenGL</label>
          <label className="tcheck"><input type="checkbox" disabled /> Force use of OpenGL VBO (Vertex Buffer Object)</label>
          {([['Render cache', 'Auto', ['Auto', 'Distributed', 'Centralized']], ['Anti-aliasing', 'MSAA 4x', ['None', 'Line Smoothing', 'MSAA 2x', 'MSAA 4x', 'MSAA 6x', 'MSAA 8x']],
            ['Transparent objects', 'One pass', ['One pass', 'Backface pass']], ['Marker size', '9px', ['5px', '7px', '9px', '11px', '13px', '15px']]] as const).map(([label, value, opts]) => (
            <label key={label} className="tfield" title="n/a: set by the browser's WebGL"><span>{label}</span>
              <QComboBox className="qselect-field" value={value} disabled onChange={() => {}}>{opts.map((o) => <option key={o} value={o}>{o}</option>)}</QComboBox></label>))}
          <label className="tfield"><span>Eye to eye distance for stereo modes</span><input type="number" value={5} disabled /></label>
          <label className="tfield"><span>Datum size</span><span className="qsuffix"><input type="number" value={100} disabled />%</span></label>
          <label className="tfield"><span>Maximum frame rate</span><input readOnly value="No limit" disabled /></label>
        </fieldset>
        <fieldset className="tgroup tg"><legend>Camera Type</legend>
          <label className="tcheck" title="Objects will appear in a perspective projection"><input type="radio" checked={!ortho} onChange={() => setOrtho(false)} /> Perspective rendering</label>
          <label className="tcheck" title="Objects will be in orthographic projection"><input type="radio" checked={ortho} onChange={() => setOrtho(true)} /> Orthographic rendering</label>
        </fieldset>
      </div>}
      {page === 'Transform snap' && <div className="pref-content">
        <div className="tform">
          <label className="tfield"><span>Move</span><QuantityBox value={snap.mm} dims={LENGTH} min={0} max={2147483647} onChange={(mm) => setSnap((x) => { const v = { ...x, mm }; saved.set('snap', v); return v })} /></label>
          <label className="tfield"><span>Rotate</span><QuantityBox value={snap.deg} dims={ANGLE} min={0} max={360} onChange={(deg) => setSnap((x) => { const v = { ...x, deg }; saved.set('snap', v); return v })} /></label>
        </div>
      </div>}
      {/* DlgSettingsMacro.ui's "Gui Commands" group. */}
      {/* DlgSettingsMacro.ui: General Macro Settings, Macro Recording Settings (Macro Path, Gui
          Commands), Logging Commands, Recent Macros Menu. */}
      {page === 'Macro' && <div className="pref-content">
        <fieldset className="tgroup tg"><legend>General Macro Settings</legend>
          <label className="tcheck" title="n/a: macros here are cad commands, each run in its own process"><input type="checkbox" checked disabled /> Run macros in local environment</label>
        </fieldset>
        <fieldset className="tgroup tg"><legend>Macro Recording Settings</legend>
          <fieldset className="tgroup tg"><legend>Macro Path</legend>
            <input className="pref-path" readOnly value={macroDir} title="Where macros are kept (CAD_MACRO_DIR overrides it)" />
          </fieldset>
          <fieldset className="tgroup tg"><legend>Gui Commands</legend>
            <label className="tcheck" title="Recorded macros will also contain user interface commands">
              <input type="checkbox" checked={recordGui} onChange={(e) => set('recordGuiCommands', e.target.checked)} /> Record GUI commands</label>
            <label className="tcheck" title="Recorded macros will also contain user interface commands as comments">
              <input type="checkbox" checked={guiAsComment} disabled={!recordGui} onChange={(e) => set('guiAsComment', e.target.checked)} /> Record as comment</label>
          </fieldset>
        </fieldset>
        <fieldset className="tgroup tg"><legend>Logging Commands</legend>
          <label className="tcheck" title="The console echoes each edit made in the UI as its cad line"><input type="checkbox" checked disabled /> Show script commands in Python console</label>
          <label className="tcheck" title="n/a: every command is already logged to the project's .cad/log.jsonl"><input type="checkbox" disabled /> Log all commands issued by menus to file</label>
        </fieldset>
        <fieldset className="tgroup tg"><legend>Recent Macros Menu</legend>
          <label className="tfield"><span>Size of recent macro list</span>
            <input type="number" min={0} max={20} value={recentMacros} onChange={(e) => { const v = Math.round(num(e.target.value, 0, 20, 12)); setRecentMacros(v); saved.set('recentMacrosSize', v) }} /></label>
          <label className="tfield"><span>Keyboard shortcut count</span><input type="number" value={3} disabled /></label>
          <label className="tfield"><span>Keyboard Modifiers</span><input readOnly value="Ctrl+Shift+" disabled /></label>
        </fieldset>
      </div>}
    </>
  )
}

/** printf %g with Qt's exponent style, as QLocale::toString(v, 'g') writes it. */
function fmtG(v: number, p = 6) {
  if (v === 0 || !Number.isFinite(v)) return String(v)
  const e = Math.floor(Math.log10(Math.abs(v)))
  if (e >= -4 && e < p) return String(Number(v.toPrecision(p)))
  const [m, x] = v.toExponential(p - 1).split('e')
  const digits = x.replace(/^[+-]/, '').padStart(2, '0')
  return `${m.replace(/\.?0+$/, '')}e${x[0] === '-' ? '-' : '+'}${digits}`
}
/** DlgUnitsCalculator's unit categories, in its order. */
const UNIT_CATEGORIES = ['Acceleration', 'AmountOfSubstance', 'Angle', 'Area', 'Density', 'CurrentDensity', 'DissipationRate', 'DynamicViscosity',
  'ElectricalCapacitance', 'ElectricalInductance', 'ElectricalConductance', 'ElectricalResistance', 'ElectricalConductivity', 'ElectricCharge',
  'ElectricCurrent', 'ElectricPotential', 'Force', 'Frequency', 'HeatFlux', 'InverseArea', 'InverseLength', 'InverseVolume', 'KinematicViscosity',
  'Length', 'LuminousIntensity', 'Mass', 'MagneticFieldStrength', 'MagneticFlux', 'MagneticFluxDensity', 'Magnetization', 'Power', 'Pressure',
  'SpecificEnergy', 'SpecificHeat', 'Stiffness', 'Temperature', 'ThermalConductivity', 'ThermalExpansionCoefficient', 'ThermalTransferCoefficient',
  'TimeSpan', 'VacuumPermittivity', 'Velocity', 'Volume', 'VolumeFlowRate', 'VolumetricThermalExpansionCoefficient', 'Work']

/** Std_UnitsCalculator (DlgUnitsCalculatorImp.cpp): a value with its unit, shown in another
 *  unit; Enter adds the line to the history. Below, a quantity in any unit system. */
function UnitsTask() {
  const { parseQuantity, typeString, userString, SCHEMAS } = quantity
  const [input, setInput] = useState('1 cm'), [unit, setUnit] = useState('in')
  const [history, setHistory] = useState<string[]>([])
  const [schema, setSchema] = useState(-1), [decimals, setDecimals] = useState(() => quantity.unitPrefs.decimals), [cat, setCat] = useState(0)
  const [spin, setSpin] = useState<quantity.Quantity>(() => ({ value: 1, dims: typeDims(UNIT_CATEGORIES[0]) }))
  const [spinText, setSpinText] = useState<string | null>(null)
  let out = '', ok = false
  try {
    const q = parseQuantity(input)
    let target = ''
    try { target = typeString(parseQuantity(unit).dims) } catch { target = '' }
    if (unit.slice(0, 2) === 'ee' || !target) out = `unknown unit: ${unit}`
    else if (target !== typeString(q.dims)) out = 'unit mismatch'
    else {
      const value = q.value / parseQuantity('1' + unit).value
      let val = fmtG(value)
      if (!val.includes('e') && value > 0.005) val = value.toFixed(quantity.unitPrefs.decimals)
      out = `${val} ${unit}`
      ok = true
    }
  } catch (e) { out = (e as Error).message }
  const sch = schema < 0 ? quantity.unitPrefs.schema : schema
  const shown = spinText ?? userString(spin, sch, decimals).text
  return (
    <div className="tasks">
      <div className="tbuttons"><button className="qbtn default" onClick={closeTask}>Close</button></div>
      <TaskBox title="Units Converter" icon="units">
        <div className="units-line">
          <input className="units-in" value={input} title="Input the source value and unit" onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); if (ok) setHistory((h) => [...h, `${input} = ${out}`]) } }} />
          <span>as</span>
          <input className="units-unit" value={unit} title="Input the unit for the result" onChange={(e) => setUnit(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); if (ok) setHistory((h) => [...h, `${input} = ${out}`]) } }} />
          <span>=&gt;</span>
          <input className="units-out" readOnly value={out} title="Result" />
        </div>
        <textarea className="units-history" readOnly value={history.join('\n')} />
        <div className="tbuttons"><button className="qbtn" disabled={!ok} title="Copies the result to the clipboard"
          onClick={() => navigator.clipboard?.writeText(out).catch(() => report('warn', 'The browser did not allow copying'))}>Copy</button></div>
      </TaskBox>
      <TaskBox title="Quantity" icon="units">
        <label className="tfield"><span>Quantity</span><input value={shown} onFocus={() => setSpinText(shown)} onChange={(e) => setSpinText(e.target.value)}
          onBlur={() => { try { const q = parseQuantity(spinText ?? ''); if (typeString(q.dims) === typeString(spin.dims) || !typeString(q.dims)) setSpin({ value: q.value, dims: spin.dims }) } catch { /* keep the old value */ } setSpinText(null) }} /></label>
        <label className="tfield"><span>Unit system</span><QComboBox className="qselect-field" value={schema} onChange={(e) => setSchema(Number(e.target.value))}>
          <option value={-1}>Preference system</option>
          {SCHEMAS.map((x) => <option key={x.num} value={x.num}>{x.description}</option>)}</QComboBox></label>
        <label className="tfield"><span>Decimals</span><input type="number" min={2} max={12} value={decimals} onChange={(e) => setDecimals(Math.max(2, Math.min(12, Number(e.target.value) || 2)))} /></label>
        <label className="tfield"><span>Unit category</span><QComboBox className="qselect-field" value={cat} onChange={(e) => {
          const i = Number(e.target.value), dims = typeDims(UNIT_CATEGORIES[i])
          // onUnitsBoxActivated: the value is rescaled by 1000 per length power.
          setSpin((q) => ({ value: q.value * Math.pow(10, 3 * (dims[0] - q.dims[0])), dims }))
          setCat(i)
        }}>{UNIT_CATEGORIES.map((c, i) => <option key={c} value={i}>{c}</option>)}</QComboBox></label>
      </TaskBox>
    </div>
  )
}
function typeDims(name: string): quantity.Quantity['dims'] {
  const found = UNIT_TYPES.find(([n]) => n === name)
  return (found ? [...found[1]] : [0, 0, 0, 0, 0, 0, 0, 0]) as quantity.Quantity['dims']
}

/** Std_DemoMode (DemoMode.cpp), the View turntable: spin about the axis that pointed down
 *  the screen at Play, speed/10 rad/s; tilt with the angle slider; auto-play after a timeout. */
function TurntableTask() {
  const [playing, setPlaying] = useState(false), [angle, setAngle] = useState(0), [speed, setSpeed] = useState(5)
  const [timerOn, setTimerOn] = useState(false), [timeout, setTimeoutS] = useState(30), [full, setFull] = useState(false)
  const axis = useRef<THREE.Vector3 | null>(null), old = useRef(0)
  const play = (on: boolean) => {
    const v = getView()
    if (!v) return
    if (on) {
      if (!axis.current || !v.nav.animating) axis.current = v.worldDown()
      v.spinAbout(axis.current, speed / 10)
    } else v.nav.stopAnimating()
    setPlaying(on)
  }
  useEffect(() => { if (playing) play(true) }, [speed]) // a new speed restarts the spin
  useEffect(() => {
    if (!timerOn) return
    const t = setInterval(() => { if (!getView()?.nav.animating) play(true) }, timeout * 1000)
    return () => clearInterval(t)
  }, [timerOn, timeout, speed])
  useEffect(() => () => { getView()?.nav.stopAnimating(); if (document.fullscreenElement) document.exitFullscreen() }, [])
  const tilt = (v: number) => {
    getView()?.tilt(v - old.current)
    old.current = v
    setAngle(v)
    if (playing && axis.current) getView()?.spinAbout(axis.current, speed / 10)
  }
  return (
    <div className="tasks">
      <div className="tbuttons"><button className="qbtn default" onClick={closeTask}>Close</button></div>
      <TaskBox title="View Turntable" icon="turntable">
        <label className="tfield"><span>Angle</span><span className="hint">-90°</span><input type="range" min={-90} max={90} value={angle} onChange={(e) => tilt(Number(e.target.value))} /><span className="hint">90°</span></label>
        <label className="tfield"><span>Speed</span><span className="hint">Minimum</span><input type="range" min={1} max={100} value={speed} onChange={(e) => setSpeed(Number(e.target.value))} /><span className="hint">Maximum</span></label>
        <label className="tcheck"><input type="checkbox" checked={full} onChange={(e) => {
          setFull(e.target.checked)
          if (e.target.checked) document.documentElement.requestFullscreen?.(); else if (document.fullscreenElement) document.exitFullscreen()
          play(false)
        }} /> Fullscreen</label>
        <label className="tcheck"><input type="checkbox" checked={timerOn} onChange={(e) => setTimerOn(e.target.checked)} /> Enable timer</label>
        <label className="tfield"><span>Timeout</span><input type="number" min={0} max={600} disabled={!timerOn} value={timeout} onChange={(e) => setTimeoutS(Math.max(0, Math.min(600, Number(e.target.value) || 0)))} /><span className="unit">s</span></label>
        <div className="tbuttons"><button className={cls('qbtn', playing && 'on')} onClick={() => play(!playing)}>{playing ? 'Stop' : 'Play'}</button></div>
      </TaskBox>
    </div>
  )
}

/** A PNG with a tEXt chunk added (FreeCAD writes the image comment into the file). */
function pngWithComment(dataUrl: string, comment: string): string {
  const bin = atob(dataUrl.split(',')[1]), bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0))
  const text = new TextEncoder().encode(`Comment\0${comment}`)
  const chunk = new Uint8Array(12 + text.length), dv = new DataView(chunk.buffer)
  dv.setUint32(0, text.length)
  chunk.set([116, 69, 88, 116], 4) // tEXt
  chunk.set(text, 8)
  let crc = ~0 >>> 0
  for (const b of chunk.subarray(4, 8 + text.length)) { crc ^= b; for (let k = 0; k < 8; k++) crc = crc & 1 ? (crc >>> 1) ^ 0xedb88320 : crc >>> 1 }
  dv.setUint32(8 + text.length, ~crc >>> 0)
  const out = new Uint8Array(bytes.length + chunk.length)
  out.set(bytes.subarray(0, 33)) // the signature and IHDR come first
  out.set(chunk, 33)
  out.set(bytes.subarray(33), 33 + chunk.length)
  let s = ''
  for (const b of out) s += String.fromCharCode(b)
  return 'data:image/png;base64,' + btoa(s)
}
const SIZES: [string, number, number][] = [['640 x 480 (VGA)', 640, 480], ['800 x 600 (SVGA)', 800, 600], ['1024 x 768 (XGA)', 1024, 768], ['1280 x 720 (HD)', 1280, 720],
  ['1280 x 1024 (SXGA)', 1280, 1024], ['1600 x 1200 (UXGA)', 1600, 1200], ['1920 x 1080 (Full HD)', 1920, 1080], ['2560 x 1440 (QHD)', 2560, 1440], ['3840 x 2160 (4K UHD)', 3840, 2160]]

/** Std_ViewScreenShot (DlgSettingsImageImp): the image's format and size (the view's, or a
 *  standard one), background, comment and watermark, then the browser saves the file. */
function ShotTask() {
  const slug = useStore((s) => s.slug)
  const px = getView()?.viewPixels() ?? { w: 800, h: 600 }
  const [fmt, setFmt] = useState(() => saved.get('shot.format', 'png'))
  const [w, setW] = useState(px.w), [h, setH] = useState(px.h), [lock, setLock] = useState(true)
  const [bg, setBg] = useState<'Current' | 'White' | 'Black' | 'Transparent'>(() => saved.get('shot.background', 'Current'))
  const [comment, setComment] = useState(''), [mark, setMark] = useState(false)
  const types: Record<string, string> = { png: 'image/png', jpg: 'image/jpeg', webp: 'image/webp' }
  const setWidth = (v: number) => { if (lock) setH(Math.round((v * h) / w) || 1); setW(v) }
  const save = () => {
    const v = getView()
    if (!v) return
    let url = v.renderImage(w, h, fmt === 'jpg' && bg === 'Transparent' ? 'White' : bg, types[fmt])
    const finish = (u: string) => {
      if (comment && fmt === 'png') u = pngWithComment(u, comment)
      const a = document.createElement('a')
      a.href = u
      a.download = `${slug ?? 'view'}.${fmt}`
      a.click()
      saved.set('shot.format', fmt)
      saved.set('shot.background', bg)
      report('msg', `Saved image ${a.download}, ${w} x ${h}`)
      closeTask()
    }
    if (!mark) return finish(url)
    // The watermark: the application's name at the bottom right, as FreeCAD adds its own.
    const img = new Image()
    img.onload = () => {
      const c = document.createElement('canvas')
      c.width = w; c.height = h
      const g = c.getContext('2d')!
      g.drawImage(img, 0, 0)
      g.font = `${Math.max(12, Math.round(h / 40))}px sans-serif`
      g.fillStyle = bg === 'Black' ? '#ffffff' : '#000000'
      g.textAlign = 'right'
      g.fillText('cad-agent', w - 10, h - 10)
      url = c.toDataURL(types[fmt], 0.95)
      finish(url)
    }
    img.src = url
  }
  return (
    <div className="tasks">
      <div className="tbuttons"><button className="qbtn default" onClick={save}>Save</button><button className="qbtn" onClick={closeTask}>Cancel</button></div>
      <TaskBox title="Save Image" icon="shot">
        <label className="tfield"><span>Format</span><QComboBox className="qselect-field" value={fmt} onChange={(e) => setFmt(e.target.value)}>
          <option value="png">PNG files (*.png)</option><option value="jpg">JPG files (*.jpg)</option><option value="webp">WEBP files (*.webp)</option></QComboBox></label>
      </TaskBox>
      <TaskBox title="Image Dimensions" icon="views">
        <label className="tfield"><span>Width</span><input type="number" min={1} max={8192} value={w} onChange={(e) => setWidth(Math.max(1, Number(e.target.value) || 1))} /><span className="unit">px</span></label>
        <label className="tfield"><span>Height</span><input type="number" min={1} max={8192} value={h} onChange={(e) => { const v = Math.max(1, Number(e.target.value) || 1); if (lock) setW(Math.round((v * w) / h) || 1); setH(v) }} /><span className="unit">px</span></label>
        <label className="tcheck"><input type="checkbox" checked={lock} onChange={(e) => setLock(e.target.checked)} /> Keep the aspect ratio</label>
        <label className="tfield"><span>Standard sizes</span><QComboBox className="qselect-field" value="" onChange={(e) => { const s = SIZES[Number(e.target.value)]; if (s) { setW(s[1]); setH(s[2]) } }}>
          <option value="">…</option>{SIZES.map((s, i) => <option key={i} value={i}>{s[0]}</option>)}</QComboBox></label>
        <div className="hbox"><span>Aspect ratio:</span>{([['Screen', px.w / px.h], ['4:3', 4 / 3], ['16:9', 16 / 9], ['1:1', 1]] as const).map(([l, r]) => (
          <button key={l} className="qbtn ratio" onClick={() => setH(Math.max(1, Math.trunc(w / r)))}>{l}</button>))}</div>
      </TaskBox>
      <TaskBox title="Image background" icon="ds-asis">
        {(['Current', 'White', 'Black', 'Transparent'] as const).map((b) => (
          <label key={b} className="tcheck"><input type="radio" checked={bg === b} disabled={b === 'Transparent' && fmt === 'jpg'} onChange={() => setBg(b)} /> {b}</label>))}
      </TaskBox>
      <TaskBox title="Image Comment" icon="document">
        <textarea className="units-history" value={comment} placeholder={fmt === 'png' ? 'Written into the PNG file' : 'Only PNG files keep a comment'} onChange={(e) => setComment(e.target.value)} disabled={fmt !== 'png'} />
        <label className="tcheck"><input type="checkbox" checked={mark} onChange={(e) => setMark(e.target.checked)} /> Add watermark</label>
      </TaskBox>
    </div>
  )
}

const ALIGN_COLORS = [0xff0000, 0x00ff00, 0x0000ff, 0xffff00, 0x00ffff, 0xb30000, 0x00b300, 0xb3b300, 0xb30080, 0xffb300]
/** ManualAlignment's transform from picked point pairs: one pair translates, two turn the
 *  movable line onto the fixed one (transformation2x2), three or more also turn the plane
 *  (transformation3x3). Returns the move as a matrix. */
function alignTransform(mov: THREE.Vector3[], fix: THREE.Vector3[]): THREE.Matrix4 {
  const place = (rot: THREE.Quaternion, t: THREE.Vector3) => new THREE.Matrix4().compose(t, rot, new THREE.Vector3(1, 1, 1))
  const between = (a: THREE.Vector3, b: THREE.Vector3) => new THREE.Quaternion().setFromUnitVectors(a.clone().normalize(), b.clone().normalize())
  if (mov.length === 1) return place(new THREE.Quaternion(), fix[0].clone().sub(mov[0]))
  const rot = between(mov[1].clone().sub(mov[0]), fix[1].clone().sub(fix[0]))
  const plm1 = place(rot, fix[0].clone().sub(mov[0].clone().applyQuaternion(rot)))
  if (mov.length === 2) return plm1
  const n1 = mov[1].clone().sub(mov[0]).cross(mov[2].clone().sub(mov[0]))
  const n2 = fix[1].clone().sub(fix[0]).cross(fix[2].clone().sub(fix[0]))
  const rot2 = between(n1.applyQuaternion(rot), n2)
  return place(rot2, fix[0].clone().sub(fix[0].clone().applyQuaternion(rot2))).multiply(plm1)
}

/** Std_Alignment (ManualAlignment.cpp) in the one 3D view: only the two objects show;
 *  clicking the movable one adds a left-view point, the fixed one a right-view point.
 *  Align moves the movable object (a placement, undoable). */
function AlignTask({ movable, fixed }: { movable: string; fixed: string }) {
  const [mov, setMov] = useState<THREE.Vector3[]>([]), [fix, setFix] = useState<THREE.Vector3[]>([])
  const bodies = useStore((s) => s.scene?.bodies) ?? []
  useEffect(() => {
    const v = getView()
    if (!v) return
    const before = getState().hidden
    setState({ hidden: bodies.map((b) => b.name).filter((n) => n !== movable && n !== fixed), selected: [], subSel: [] })
    report('msg', 'Select at least 1 point in the left and the right view: click points on the movable and on the fixed object')
    v.pointPicker = (body, point) => {
      if (!point) return report('msg', 'No point was found on model')
      if (body === movable) setMov((m) => [...m, point.clone()])
      else if (body === fixed) setFix((f) => [...f, point.clone()])
      else return
      report('msg', `Point picked at (${point.x.toFixed(2)},${point.y.toFixed(2)},${point.z.toFixed(2)})`)
    }
    return () => { v.pointPicker = null; v.showPoints([]); setState({ hidden: before }) }
  }, [movable, fixed])
  useEffect(() => {
    getView()?.showPoints([...mov.map((p, i) => ({ p, color: ALIGN_COLORS[i % 10] })), ...fix.map((p, i) => ({ p, color: ALIGN_COLORS[i % 10] }))])
  }, [mov, fix])
  const can = mov.length >= 1 && mov.length === fix.length
  const align = async () => {
    if (mov.length < 1) return report('warn', 'Too few points picked in the left view. At least 1 points are needed.')
    if (fix.length < 1) return report('warn', 'Too few points picked in the right view. At least 1 points are needed.')
    if (mov.length !== fix.length) return report('warn', `Different number of points picked in left and right view. On the left view ${mov.length} points are picked, on the right view ${fix.length} points are picked.`)
    const b = getState().scene?.bodies.find((x) => x.name === movable)
    if (!b) return
    const before = placementOf(b), T = alignTransform(mov, fix)
    const after = toPlacement(T.multiply(placementMatrix(before)), before.about)
    report('msg', 'Try to align group of views')
    if (await place(movable, b.placement ? before : null, after)) {
      report('msg', 'The alignment has finished')
      setMov([]); setFix([])
    }
  }
  const list = (pts: THREE.Vector3[]) => pts.map((p, i) => (
    <div key={i} className="align-pt"><span className="align-dot" style={{ background: '#' + ALIGN_COLORS[i % 10].toString(16).padStart(6, '0') }} />Point_{i + 1} ({p.x.toFixed(2)}, {p.y.toFixed(2)}, {p.z.toFixed(2)})</div>))
  return (
    <div className="tasks">
      <div className="tbuttons">
        <button className="qbtn default" disabled={!can} onClick={align}>Align</button>
        <button className="qbtn" onClick={() => { report('msg', 'The alignment has been canceled'); closeTask() }}>Close</button>
      </div>
      <TaskBox title={`Movable object: ${movable}`} icon="transform">
        {list(mov)}
        <div className="tbuttons"><button className="qbtn" disabled={!mov.length} onClick={() => setMov((m) => m.slice(0, -1))}>Remove last point</button></div>
      </TaskBox>
      <TaskBox title={`Fixed object: ${fixed}`} icon="part">
        {list(fix)}
        <div className="tbuttons"><button className="qbtn" disabled={!fix.length} onClick={() => setFix((f) => f.slice(0, -1))}>Remove last point</button>
          <button className="qbtn" disabled={!mov.length && !fix.length} onClick={() => { setMov([]); setFix([]) }}>Clear</button></div>
      </TaskBox>
      <p className="hint">One pair of points moves the object; two also turn its line onto the other's; three or more also turn its plane. Pick the points in the same order on both objects.</p>
    </div>
  )
}

/** Std_ToggleClipPlane: FreeCAD's Clipping dialog. Closing it removes the planes. */
/** Std_ToggleClipPlane (Gui/Clipping.cpp and Clipping.ui): Clipping X, Y and Z, each an
 *  offset and Flip; a Custom Clipping Direction with View and Adjust to view direction. Turning
 *  an axis plane on turns the custom one off, and the other way round. The offsets start at
 *  the middle of the scene and step by a power of ten near a hundredth of its size. */
function ClipTask() {
  const clip = useStore((s) => s.clip), bb = useStore((s) => s.scene?.bbox)
  useEffect(() => () => setState({ clip: null }), [])
  if (!clip) return null
  const putAxis = (ax: 'x' | 'y' | 'z', patch: Partial<ClipAxis>) => setState((s) => {
    if (!s.clip) return {}
    const next = { ...s.clip, [ax]: { ...s.clip[ax], ...patch } }
    if (patch.on) next.view = { ...next.view, on: false } // onGroupBoxXToggled
    return { clip: next }
  })
  const putView = (patch: Partial<ClipView>) => setState((s) => {
    if (!s.clip) return {}
    const view = { ...s.clip.view, ...patch }
    const off = { on: false }
    return { clip: patch.on ? { ...s.clip, view, x: { ...s.clip.x, ...off }, y: { ...s.clip.y, ...off }, z: { ...s.clip.z, ...off } } : { ...s.clip, view } }
  })
  // The single steps: 10^int(log10(size / 100)), int truncating toward zero as C++ does.
  const size = bb ? [0, 1, 2].map((i) => bb[1][i] - bb[0][i]) : [100, 100, 100]
  const stepOf = (len: number) => (len > 0 ? Math.pow(10, Math.trunc(Math.log10(len / 100))) : 0.1)
  const steps = size.map(stepOf), viewStep = stepOf(Math.min(...size))
  const v = clip.view
  const setDir = (i: number) => (n: number) => {
    const dir = v.dir.map((x, j) => (j === i ? n : x)) as ClipView['dir']
    putView(dir.some((x) => x !== 0) ? { dir, normal: dir } : { dir }) // onDirXValueChanged: a zero normal is ignored
  }
  const fromView = () => {
    const cam = getView()?.viewer.camera?.getCamera?.() as THREE.Camera | undefined
    if (cam) putView({ normal: new THREE.Vector3(0, 0, -1).applyQuaternion(cam.quaternion).toArray() as ClipView['normal'] })
  }
  return (
    <div className="tasks">
      <div className="tbuttons"><button className="qbtn default" onClick={closeTask}>Close</button></div>
      <TaskBox title="Clipping" icon="clip">
        {(['x', 'y', 'z'] as const).map((ax, i) => {
          const c = clip[ax]
          return (
            <fieldset key={ax} className="tgroup">
              <legend><label className="tcheck"><input type="checkbox" checked={c.on} onChange={(e) => putAxis(ax, { on: e.target.checked })} /> Clipping {ax.toUpperCase()}</label></legend>
              <div className="hbox fill"><span>Offset</span>
                <QuantityBox value={c.offset} dims={NUMBER} step={steps[i]} disabled={!c.on} onChange={(n) => putAxis(ax, { offset: n })} />
                <button className="qbtn" disabled={!c.on} onClick={() => putAxis(ax, { flip: !c.flip })}>Flip</button></div>
            </fieldset>
          )
        })}
        <fieldset className="tgroup">
          <legend><label className="tcheck"><input type="checkbox" checked={v.on} onChange={(e) => putView({ on: e.target.checked })} /> Custom Clipping Direction</label></legend>
          <div className="hbox fill"><span>Offset</span>
            <QuantityBox value={v.offset} dims={NUMBER} step={viewStep} disabled={!v.on} onChange={(n) => putView({ offset: n })} />
            <button className="qbtn" disabled={!v.on || v.adjust} onClick={fromView}>View</button></div>
          <label className="tcheck"><input type="checkbox" checked={v.adjust} disabled={!v.on} onChange={(e) => putView({ adjust: e.target.checked })} /> Adjust to view direction</label>
          <fieldset className="tgroup"><legend>Direction</legend>
            <div className="tgrid3">{[0, 1, 2].map((i) => <QuantityBox key={i} value={v.dir[i]} dims={NUMBER} step={0.1} disabled={!v.on || v.adjust} onChange={setDir(i)} />)}</div>
          </fieldset>
        </fieldset>
        <p className="hint">The planes cut the view only, not the design. Close removes them.</p>
      </TaskBox>
    </div>
  )
}

/** A sub-element's placement (subObjectPlacementProvider): a vertex at its point; an edge at
 *  its middle, Z along it; a face at its centre, Z along its normal when planar. */
function elementPlacement(ref: string): THREE.Matrix4 | null {
  const info = subInfo(getView()?.subGeometry(ref) ?? null)
  if (!info) return null
  const z = info.normal ?? info.dir
  const q = z ? new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 0, 1), z.clone().normalize()) : new THREE.Quaternion()
  return new THREE.Matrix4().compose(info.center.clone(), q, new THREE.Vector3(1, 1, 1))
}
const posOf = (m: THREE.Matrix4) => new THREE.Vector3().setFromMatrixPosition(m)
const rotOf = (m: THREE.Matrix4) => new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().extractRotation(m))
const compose = (p: THREE.Vector3, q: THREE.Quaternion) => new THREE.Matrix4().compose(p, q, new THREE.Vector3(1, 1, 1))

/** Std_TransformManip (Gui/TaskTransform.cpp): the dragger's placement in a coordinate system
 *  (Local U/V/W, Global X/Y/Z, or a picked reference), with its rotation; utilities to move the
 *  object onto another object's element (matching and aligning chosen axes) and to flip it;
 *  and the dragger's snapping and origin (object origin, centre of mass, or a picked element). */
function TransformTask({ b }: { b: Body }) {
  // LastTranslationIncrement 1 mm, LastRotationIncrement 5°.
  const [snap, setSnap] = useState(() => saved.get('snap', { mm: 1, deg: 5 }))
  const [originMode, setOriginMode] = useState<'origin' | 'centroid' | 'custom'>('origin')
  const [customOrigin, setCustomOrigin] = useState<THREE.Matrix4 | null>(null)
  const [csMode, setCsMode] = useState<'local' | 'global' | 'custom'>('local')
  const [customCS, setCustomCS] = useState<THREE.Matrix4 | null>(null)
  const [alignRot, setAlignRot] = useState(false)
  const [pick, setPick] = useState<null | 'origin' | 'cs' | 'target'>(null)
  const [originRef, setOriginRef] = useState<string | null>(null), [csRef, setCsRef] = useState<string | null>(null)
  const [moveOptions, setMoveOptions] = useState(false) // frameMoveOptions, hidden until the options button is on
  const [ask, setAsk] = useState<ExprAsk | null>(null)
  const eq = (dims: Dims, apply: (v: number) => void) => (text: string, at: { x: number; y: number }) => setAsk({ text, at, dims, apply })
  const [util, setUtil] = useState({ translate: true, rotate: true, match: [true, true, true], align: [true, true, true] })
  const [dragger, setDraggerState] = useState<THREE.Matrix4 | null>(null)
  const [delta, setDelta] = useState(new THREE.Matrix4())
  const hash = useStore((s) => s.scene?.source_hash)
  const latest = useRef(b)
  latest.current = b
  const cur = placementOf(b), objRot = quatOfTurn(cur.turn), objPos = new THREE.Vector3(...cur.about).add(new THREE.Vector3(...cur.move))
  // The transform origin (updateTransformOrigin), in world space.
  const [cog, setCog] = useState<THREE.Vector3 | null>(null)
  useEffect(() => {
    if (originMode !== 'centroid' || cog) return
    const slug = getState().slug
    if (slug) api.mass(slug, [b.name]).then((r) => { if (r.data?.cog) setCog(new THREE.Vector3(...(r.data.cog as Vec3))) }).catch(() => report('warn', 'Transform: could not compute the center of mass'))
  }, [originMode])
  // TaskTransform's references: where the dragger was (referencePlacement) and how it was
  // turned (referenceRotation). The Local system (U, V, W) sits at the reference, turned as
  // the dragger is now; its angles are intrinsic X-Y'-Z'' from the reference rotation. The
  // Global and Custom systems show extrinsic X, Y, Z (eulerSequence).
  const refPos = useRef(new THREE.Vector3()), refRot = useRef(new THREE.Quaternion()), dragStart = useRef(new THREE.Quaternion())
  const fromField = useRef(false)
  const [fields, setFields] = useState<{ pos: Vec3; rot: Vec3 }>({ pos: [0, 0, 0], rot: [0, 0, 0] })
  const seq: EulerSeq = csMode === 'local' ? 'Intrinsic_XYZ' : 'Extrinsic_XYZ' // TaskTransform::eulerSequence
  const eulerOf = (q: THREE.Quaternion) => eulerOfSeq(q, seq)
  const quatOfEuler = (a: Vec3) => quatOfEulerSeq(a, seq)
  /** currentCoordinateSystem, for the dragger as it is. */
  // customCoordinateSystem: without a picked reference it is the global one.
  const csOf = (d: THREE.Matrix4) => csMode === 'custom' ? (customCS ? customCS.clone() : new THREE.Matrix4()) : csMode === 'global' ? new THREE.Matrix4() : compose(refPos.current, rotOf(d))
  const csOrigin = () => csOf(getView()?.getDragger() ?? dragger ?? new THREE.Matrix4())
  const fix = (v: number) => (Math.abs(v) < 1e-7 ? 0 : v)
  /** updatePositionAndRotationUi. */
  const fieldsOf = (d: THREE.Matrix4) => {
    const uvw = d.clone().premultiply(csOf(d).invert())
    const r = csMode === 'local' ? refRot.current.clone().invert().multiply(rotOf(d)) : rotOf(uvw)
    return { pos: posOf(uvw).toArray().map(fix) as Vec3, rot: eulerOf(r).map(fix) as Vec3 }
  }
  const resetReferences = (d: THREE.Matrix4) => { refPos.current = posOf(d); refRot.current = rotOf(d) }
  const pivot = (): THREE.Matrix4 => {
    let m = originMode === 'custom' && customOrigin ? customOrigin.clone() : compose(originMode === 'centroid' && cog ? cog : objPos, objRot)
    // isDraggerAlignedToCoordinateSystem: only for the Global and Custom systems.
    if (alignRot && csMode !== 'local') m = compose(posOf(m), rotOf(csMode === 'custom' && customCS ? customCS : new THREE.Matrix4()))
    return m
  }
  const sameRot = (a: THREE.Quaternion, c: THREE.Quaternion) => 1 - Math.abs(a.dot(c)) < 1e-7
  const onChange = (d: THREE.Matrix4, dl: THREE.Matrix4, phase: TransformPhase) => {
    setDraggerState(d.clone()); setDelta(dl.clone())
    if (phase === 'start') { dragStart.current = rotOf(d); return }
    if (phase === 'motion') {
      // dragMotionCallback: turning restarts the position reference; turning about another
      // axis restarts the rotation reference from where this drag began.
      const upd = rotOf(d)
      if (!sameRot(upd, dragStart.current)) {
        refPos.current = posOf(d)
        if (eulerOf(refRot.current.clone().invert().multiply(upd)).filter((a) => Math.abs(a) > 1e-7).length > 1) refRot.current = dragStart.current.clone()
      }
    }
    if (phase === 'finish') dragStart.current = rotOf(d)
    if (!fromField.current) setFields(fieldsOf(d))
  }
  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange
  // Attach the dragger; a rebuild (after Apply) starts it again where the body now is.
  useEffect(() => {
    const p = pivot()
    resetReferences(p)
    dragStart.current = rotOf(p)
    getView()?.startTransform({ body: b.name, pivot: p, snap, onChange: (d, dl, ph) => onChangeRef.current(d, dl, ph) })
    setDraggerState(p.clone()); setDelta(new THREE.Matrix4())
    setFields(fieldsOf(p))
    return () => getView()?.stopTransform(true)
  }, [b.name, hash])
  // A new origin moves only the dragger, not the object; the references start again.
  useEffect(() => {
    const v = getView()
    if (!v?.getDragger()) return
    const p = pivot().premultiply(delta)
    resetReferences(p)
    fromField.current = true
    v.setDragger(p, false)
    fromField.current = false
    setFields(fieldsOf(p))
  }, [originMode, customOrigin, cog, alignRot, csMode, customCS])
  useEffect(() => { getView()?.setTransformSnap(snap); saved.set('snap', snap) }, [snap])
  // Picking (setSelectionMode): a click hands its element to the pending pick.
  useEffect(() => {
    const v = getView()
    if (!v || !pick) return
    v.setDraggerPickable(false) // setSelectionMode: the dragger is UNPICKABLE while picking
    report('msg', pick === 'target' ? 'Click an element of another object to move this one onto it' : 'Click a face, edge or vertex' + (pick === 'origin' ? ` of ${b.name} for the dragger's origin` : ' for the coordinate system'))
    v.pointPicker = (body, _point, sub) => {
      if (!body || !sub) return
      const m = elementPlacement(`${body}.${sub}`)
      if (!m) return
      if (pick === 'origin') { if (body !== b.name) return report('warn', `Pick an element of ${b.name}`); setCustomOrigin(m); setOriginRef(`${body}.${sub}`); setOriginMode('custom') }
      else if (pick === 'cs') { setCustomCS(m); setCsRef(`${body}.${sub}`); setCsMode('custom') }
      else if (pick === 'target') { if (body === b.name) return report('warn', 'Pick an element of another object'); moveToTarget(m) }
      setPick(null)
    }
    return () => { v.pointPicker = null; v.setDraggerPickable(true) }
  }, [pick])
  /** Move to Other Object: the dragger takes the target's chosen position and rotation parts,
   *  in the fields' coordinate system, and the object follows (moveObjectToDragger). */
  const moveToTarget = (target: THREE.Matrix4) => {
    const v = getView(), d = v?.getDragger()
    if (!v || !d) return
    const cs = csOrigin(), csInv = cs.clone().invert()
    const dl = posOf(d.clone().premultiply(csInv)), tl = posOf(target.clone().premultiply(csInv))
    if (util.translate) (['x', 'y', 'z'] as const).forEach((k, i) => { if (util.match[i]) dl[k] = tl[k] })
    let q = rotOf(d)
    if (util.rotate && util.align.some(Boolean)) {
      const tq = rotOf(target)
      if (util.align.every(Boolean)) q = tq
      else { const i = util.align.findIndex(Boolean), ax = [new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, 1, 0), new THREE.Vector3(0, 0, 1)][i]
        q = new THREE.Quaternion().setFromUnitVectors(ax.clone().applyQuaternion(q), ax.clone().applyQuaternion(tq)).multiply(q) }
    }
    const m = compose(posOf(compose(dl, new THREE.Quaternion()).premultiply(cs)), q)
    resetReferences(m) // moveObjectToDragger
    v.setDragger(m, true)
  }
  /** onFlip: the dragger turned over (its Z reversed), the object with it. */
  const flip = () => {
    const v = getView(), d = v?.getDragger()
    if (!v || !d) return
    const m = compose(posOf(d), rotOf(d).multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI)))
    resetReferences(m)
    v.setDragger(m, true)
  }
  // updateInputLabels: U/V/W local, X/Y/Z global, X′/Y′/Z′ custom.
  const labels = csMode === 'global' ? ['X', 'Y', 'Z'] : csMode === 'custom' ? ['X′', 'Y′', 'Z′'] : ['U', 'V', 'W']
  // updateDraggerLabels: the dragger says U/V/W unless it is aligned to the chosen system.
  const aligned = alignRot && csMode !== 'local'
  useEffect(() => { getView()?.setDraggerLabels((aligned ? labels : ['U', 'V', 'W']) as [string, string, string]) }, [aligned, csMode, hash])
  /** onPositionChange: the dragger to the typed spot in the coordinate system; the object follows. */
  const setPos = (i: number) => (v: number) => {
    const d = getView()?.getDragger()
    const pos = fields.pos.map((x, j) => (j === i ? v : x)) as Vec3
    setFields((f) => ({ ...f, pos }))
    if (!d) return
    fromField.current = true
    getView()?.setDragger(compose(new THREE.Vector3(...pos).applyMatrix4(csOf(d)), rotOf(d)), true)
    fromField.current = false
  }
  /** onRotationChange: in the Local system one axis at a time, from a new reference. */
  const setRot = (i: number) => (v: number) => {
    const d = getView()?.getDragger()
    if (!d) return
    let rot = fields.rot.map((x, j) => (j === i ? v : x)) as Vec3
    if (csMode === 'local' && rot.some((x, j) => j !== i && Math.abs(x) > 1e-7)) {
      refRot.current = rotOf(d)
      rot = rot.map((x, j) => (j === i ? x : 0)) as Vec3
    }
    const base = csMode === 'local' ? refRot.current : rotOf(csOf(d))
    fromField.current = true
    getView()?.setDragger(compose(posOf(d), base.clone().multiply(quatOfEuler(rot))), true)
    fromField.current = false
    refPos.current = posOf(d) // resetReferencePlacement
    const nd = getView()?.getDragger() ?? d
    setFields({ pos: fieldsOf(nd).pos, rot })
  }
  const commit = async (close: boolean) => {
    const before = placementOf(latest.current), moved = !delta.equals(new THREE.Matrix4())
    if (moved && !(await place(b.name, latest.current.placement ? before : null, toPlacement(delta.clone().multiply(placementMatrix(before)), before.about)))) return
    if (close) { getView()?.stopTransform(false); closeTask() }
  }
  const pickButton = (what: 'origin' | 'cs') => (
    <button className="qbtn" onClick={() => setPick(pick === what ? null : what)}>{pick === what ? 'Cancel' : 'Pick Reference'}</button>)
  const refText = (what: 'origin' | 'cs', label: string | null) => (pick === what ? 'Select object, face, edge…' : label ?? '')
  return (
    <div className="tasks">
      <TaskButtons onOk={() => commit(true)} />
      <TaskBox title="Transform" icon="transform">
        <fieldset className="tgroup tg"><legend>Dragger</legend>
          <label className="tfield"><span>Mode</span><QComboBox className="qselect-field" value={originMode} onChange={(e) => { const m = e.target.value as 'origin' | 'centroid' | 'custom'; setOriginMode(m); if (m === 'custom' && !customOrigin) setPick('origin'); else if (pick === 'origin') setPick(null) }}>
            <option value="origin">Object origin</option><option value="centroid">Center of mass / centroid</option><option value="custom">Custom</option></QComboBox></label>
          {originMode === 'custom' && <div className="tfield top"><span>Reference</span><span className="tref"><input readOnly value={refText('origin', originRef)} />{pickButton('origin')}</span></div>}
          <div className="tsub">Snapping</div>
          <label className="tfield"><span>Translation</span><QuantityBox value={snap.mm} dims={LENGTH} min={0} max={2147483647} onChange={(v) => setSnap((x) => ({ ...x, mm: v }))} /></label>
          <label className="tfield"><span>Rotation</span><QuantityBox value={snap.deg} dims={ANGLE} min={0} max={360} onChange={(v) => setSnap((x) => ({ ...x, deg: v }))} /></label>
        </fieldset>
        <label className="tfield"><span>Coordinate system</span><QComboBox className="qselect-field" value={csMode} onChange={(e) => {
          const m = e.target.value as 'local' | 'global' | 'custom'
          setCsMode(m)
          if (m === 'custom' && !customCS) setPick('cs')
          else if (pick === 'cs') setPick(null)
        }}><option value="local">Local</option><option value="global">Global</option><option value="custom">Custom</option></QComboBox></label>
        {csMode === 'custom' && <div className="tfield top"><span>Reference</span><span className="tref"><input readOnly value={refText('cs', csRef)} />{pickButton('cs')}</span></div>}
        {csMode !== 'local' && <label className="tcheck"><input type="checkbox" checked={alignRot} onChange={(e) => setAlignRot(e.target.checked)} /> Align dragger rotation with selected coordinate system</label>}
        <fieldset className="tgroup tg"><legend>Translation</legend>{[0, 1, 2].map((i) => (
          <label key={i} className="tfield"><span>{labels[i]}</span><QuantityBox value={fields.pos[i]} dims={LENGTH} onChange={setPos(i)} disabled={!!pick} onEquals={eq(LENGTH, setPos(i))} /></label>))}</fieldset>
        <fieldset className="tgroup tg"><legend>Rotation</legend>{[0, 1, 2].map((i) => (
          <label key={i} className="tfield"><span>{labels[i]}</span><QuantityBox value={fields.rot[i]} dims={ANGLE} onChange={setRot(i)} disabled={!!pick} onEquals={eq(ANGLE, setRot(i))} /></label>))}</fieldset>
        <fieldset className="tgroup"><legend>Utilities</legend>
          <div className="hbox">
            <button className="qbtn grow" onClick={() => setPick(pick === 'target' ? null : 'target')}>{pick === 'target' ? 'Cancel' : 'Move to Other Object'}</button>
            <button className={cls('qbtn ibtn', moveOptions && 'on')} aria-pressed={moveOptions} title="Options" onClick={() => setMoveOptions(!moveOptions)}><Icon name="dlg-parameter" size={16} /></button>
          </div>
          {moveOptions && <div className="tframe">
            <div className="hbox">
              <label className="tcheck"><input type="checkbox" checked={util.translate} onChange={(e) => setUtil({ ...util, translate: e.target.checked })} /> Translate</label>
              <label className="tcheck"><input type="checkbox" checked={util.rotate} onChange={(e) => setUtil({ ...util, rotate: e.target.checked })} /> Rotate</label>
            </div>
            <div className="tgrid2">{[0, 1, 2].map((i) => (
              <Fragment key={i}>
                <label className="tcheck"><input type="checkbox" checked={util.match[i]} disabled={!util.translate} onChange={(e) => setUtil({ ...util, match: util.match.map((m, j) => (j === i ? e.target.checked : m)) })} /> Match {['U/X', 'V/Y', 'W/Z'][i]}</label>
                <label className="tcheck"><input type="checkbox" checked={util.align[i]} disabled={!util.rotate} onChange={(e) => setUtil({ ...util, align: util.align.map((m, j) => (j === i ? e.target.checked : m)) })} /> Align {['U/X', 'V/Y', 'W/Z'][i]}</label>
              </Fragment>))}
            </div>
          </div>}
          <div className="tframe tline" />
          <button className="qbtn" onClick={flip}>Flip</button>
        </fieldset>
      </TaskBox>
      {ask && <ExpressionDialog at={ask.at} text={ask.text} dims={ask.dims} vars={paramVars(b)} onOk={(v) => { ask.apply(v); setAsk(null) }} onCancel={() => setAsk(null)} />}
      <p className="hint">OK writes the move to placements.toml; Cancel puts the part back.</p>
    </div>
  )
}

// ── bottom panels ────────────────────────────────────────────────────────────
/** Keep a log panel on its newest line, also when its tab is brought forward. */
function useStickToBottom<T>(dep: T) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => { const el = ref.current; if (el) el.scrollTop = el.scrollHeight }, [dep])
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver(() => { el.scrollTop = el.scrollHeight })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return ref
}

// The report view starts empty each session, like FreeCAD's; the console keeps history.
const SESSION_START = Date.now() - 5000
const levelOf = (e: LogEntry): Level => (e.exit === 0 ? 'msg' : e.exit === 2 ? 'warn' : 'err')
/** ReportOutput::contextMenuEvent's message types, in its order. */
const LEVELS: Level[] = ['msg', 'log', 'warn', 'err', 'critical']
const LEVEL_NAMES: Record<Level, string> = { msg: 'Normal Messages', log: 'Log Messages', warn: 'Warnings', err: 'Errors', critical: 'Critical Messages' }

export function ReportView() {
  const messages = useStore((s) => s.messages), log = useStore((s) => s.log)
  const show = useStore((s) => s.reportShow), cleared = useStore((s) => s.reportCleared)
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null)
  const lines = useMemo(() => [
    ...log.filter((e) => Date.parse(e.t) >= SESSION_START && (e.cmd !== 'scene' || e.exit !== 0)).slice(-200)
      .map((e) => ({ t: Date.parse(e.t), level: levelOf(e), text: `cad ${e.cmd}: ${e.summary}` })),
    ...messages,
  ].filter((m) => m.t > cleared && show[m.level]).sort((a, b) => a.t - b.t), [messages, log, show, cleared])
  // Go to end (default on) keeps the newest line in view.
  const [goToEnd, setGoToEndRaw] = useState(() => saved.get('report.goToEnd', true))
  const setGoToEnd = (on: boolean) => { setGoToEndRaw(on); saved.set('report.goToEnd', on) }
  const ref = useStickToBottom(goToEnd ? lines : null)
  const toggle = (l: Level) => setState((s) => { const reportShow = { ...s.reportShow, [l]: !s.reportShow[l] }; saved.set('reportShow', reportShow); return { reportShow } })
  const timecode = useStore((s) => s.reportTimecode)
  // Show report view on: a new message of a checked level brings the report view forward.
  const [showOn, setShowOnRaw] = useState<Record<Level, boolean>>(() => ({ msg: false, log: false, warn: false, err: false, critical: false, ...saved.get<Partial<Record<Level, boolean>>>('report.showOn', {}) }))
  const setShowOn = (l: Level, on: boolean) => { const v = { ...showOn, [l]: on }; setShowOnRaw(v); saved.set('report.showOn', v) }
  const lastCount = useRef(messages.length)
  useEffect(() => {
    const fresh = messages.slice(lastCount.current)
    lastCount.current = messages.length
    // read afresh: Preferences > Report View sets these too
    const on = { ...showOn, ...saved.get<Partial<Record<Level, boolean>>>('report.showOn', {}) }
    if (fresh.some((m) => on[m.level])) showPanel('report')
  }, [messages])
  const text = () => lines.map((m) => `${clock(m.t)}  ${m.text}`).join('\n')
  return (
    <div className="report" ref={ref} onContextMenu={(e) => { e.preventDefault(); setMenu({ x: e.clientX, y: e.clientY }) }}>
      {lines.map((m, i) => <div key={i} className={'rl ' + m.level}>{timecode ? `${clock(m.t)}  ` : ''}{m.text}</div>)}
      {menu && <ContextMenu at={menu} onClose={() => setMenu(null)} entries={[
        // ReportOutput::contextMenuEvent: Options, then the edit actions.
        { label: 'Options', sub: [
          { label: 'Display Message Types', sub: LEVELS.map((l): Entry => ({ label: LEVEL_NAMES[l], checked: show[l] !== false, onSelect: () => toggle(l) })) },
          { label: 'Show Report View On', sub: LEVELS.map((l): Entry => ({ label: LEVEL_NAMES[l], checked: showOn[l], onSelect: () => setShowOn(l, !showOn[l]) })) },
          { label: 'Redirect Python Output', disabled: true, title: 'There is no Python interpreter here: the console runs cad commands' },
          { label: 'Redirect Python Errors', disabled: true, title: 'There is no Python interpreter here: the console runs cad commands' },
          { label: 'Go to End', checked: goToEnd, onSelect: () => setGoToEnd(!goToEnd) },
        ] },
        { label: 'Copy', kbd: '⌘C', onSelect: () => navigator.clipboard?.writeText(String(getSelection()) || text()) },
        { label: 'Select All', kbd: '⌘A', onSelect: () => { const r = document.createRange(); r.selectNodeContents(ref.current!); getSelection()?.removeAllRanges(); getSelection()?.addRange(r) } },
        { label: 'Clear', onSelect: () => setState({ reportCleared: Date.now() }) },
        'sep',
        { label: 'Save As…', onSelect: () => { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text()], { type: 'text/plain' })); a.download = `${getState().slug ?? 'report'}-report.txt`; a.click() } },
      ]} />}
    </div>
  )
}

/** Every cad command, the agent's and the UI's, the way FreeCAD's console echoes
 *  each GUI action as the Python it ran. */
/** FreeCAD's Python console, for `cad` (PythonConsole.cpp): every command, the agent's and the
 *  UI's, echoed as it ran; typed ones run; Up/Down walk the history; ⌘L clears; the menu
 *  has Copy, Copy command, Copy history, Save history as, Save history, Paste, Select all,
 *  Clear console, Insert file name and Word wrap. */
export function ConsoleView() {
  const log = useStore((s) => s.log), mine = useStore((s) => s.consoleLines), draft = useStore((s) => s.consoleDraft)
  const [keepHistory, setKeepHistory] = useState(() => saved.get('console.saveHistory', false))
  const history = useRef<string[]>(keepHistory ? saved.get<string[]>('console.history', []) : []), at = useRef(history.current.length)
  const input = useRef<HTMLInputElement>(null), file = useRef<HTMLInputElement>(null)
  const [cleared, setCleared] = useState(0), [wrap, setWrap] = useState(() => saved.get('console.wrap', false))
  const [menu, setMenu] = useState<{ x: number; y: number; sel: string } | null>(null)
  const entries = useMemo(() => [
    ...log.slice(-300).map((e) => ({ t: Date.parse(e.t), cmd: cmdline(e.argv), out: `# ${e.summary} (exit ${e.exit}, ${(e.ms / 1000).toFixed(1)} s)`, bad: e.exit !== 0 ? levelOf(e) : '' })),
    ...mine.map((m) => (m.kind === 'in' ? { t: m.t, cmd: m.text, out: '', bad: '' } : { t: m.t, cmd: '', out: `# ${m.text}`, bad: m.kind === 'err' ? 'err' : '' })),
  ].filter((l) => l.t > cleared).sort((a, b) => a.t - b.t), [log, mine, cleared])
  const ref = useStickToBottom(entries)
  const run = (text: string) => {
    history.current.push(text)
    at.current = history.current.length
    if (keepHistory) saved.set('console.history', history.current.slice(-100))
    setState({ consoleDraft: '' })
    runConsole(text)
  }
  const allText = () => entries.map((l) => [l.cmd && `>>> ${l.cmd}`, l.out].filter(Boolean).join('\n')).join('\n')
  const download = (name: string, text: string) => { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text], { type: 'text/plain' })); a.download = name; a.click() }
  return (
    <div className={cls('console', wrap && 'wrap')} ref={ref} onClick={() => input.current?.focus()}
      onContextMenu={(e) => {
        e.preventDefault()
        const sl = getSelection(), inside = !!sl && !sl.isCollapsed && !!ref.current?.contains(sl.anchorNode)
        setMenu({ x: e.clientX, y: e.clientY, sel: inside ? String(sl) : '' })
      }}>
      {entries.map((l, i) => (
        <div key={i} className="cl">
          {l.cmd && <div><span className="cprompt">&gt;&gt;&gt; </span>{l.cmd}</div>}
          {l.out && <div className={cls('cout', l.bad)}>{l.out}</div>}
        </div>))}
      <div className="cl cinput"><span className="cprompt">&gt;&gt;&gt; </span>
        <input ref={input} value={draft} spellCheck={false} placeholder="help"
          onChange={(e) => setState({ consoleDraft: e.target.value })}
          onKeyDown={(e) => {
            if (e.key === 'Enter') run(draft)
            else if (e.key === 'Escape' && draft) { // PythonConsole::keyPressEvent, Key_Escape
              e.preventDefault(); e.stopPropagation()
              history.current.push(draft); at.current = history.current.length
              setState((s) => ({ consoleDraft: '', consoleLines: [...s.consoleLines, { t: Date.now(), kind: 'in', text: `# ${draft}` }] }))
            }
            else if (e.key === 'ArrowUp' && history.current.length) { at.current = Math.max(0, at.current - 1); setState({ consoleDraft: history.current[at.current] }); e.preventDefault() }
            else if (e.key === 'ArrowDown') { at.current = Math.min(history.current.length, at.current + 1); setState({ consoleDraft: history.current[at.current] ?? '' }); e.preventDefault() }
            else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'l') { e.preventDefault(); setCleared(Date.now()) } // Clear Console (Ctrl+L)
          }} />
      </div>
      <input ref={file} type="file" style={{ display: 'none' }} onChange={(e) => {
        const f = e.target.files?.[0]
        if (f) setState((s) => ({ consoleDraft: `${s.consoleDraft}${JSON.stringify(f.name)}` }))
        e.target.value = ''
      }} />
      {menu && <ContextMenu at={menu} onClose={() => setMenu(null)} entries={[
        // PythonConsole::contextMenuEvent, in its order; Copy and Copy Command need a selection.
        { label: 'Copy', kbd: '⌘C', disabled: !menu.sel, onSelect: () => navigator.clipboard?.writeText(menu.sel) },
        // onCopyCommand: only the commands in the selection, without their prompts.
        { label: 'Copy Command', disabled: !menu.sel, onSelect: () => navigator.clipboard?.writeText(menu.sel.split('\n').filter((l) => l.startsWith('>>> ')).map((l) => l.slice(4)).join('\n')) },
        { label: 'Copy History', disabled: !history.current.length, onSelect: () => navigator.clipboard?.writeText(history.current.join('\n')) },
        { label: 'Save History As…', disabled: !history.current.length, onSelect: () => download(`${getState().slug ?? 'console'}-history.txt`, history.current.join('\n')) },
        { label: 'Save History', checked: keepHistory, title: 'Saves the command history across sessions', onSelect: () => {
          const on = !keepHistory
          setKeepHistory(on); saved.set('console.saveHistory', on)
          saved.set('console.history', on ? history.current.slice(-100) : [])
        } },
        'sep',
        { label: 'Paste', kbd: '⌘V', onSelect: () => navigator.clipboard?.readText().then((t) => setState((s) => ({ consoleDraft: s.consoleDraft + t }))).catch(() => report('warn', 'The browser did not allow pasting; use ⌘V in the command line')) },
        { label: 'Select All', kbd: '⌘A', disabled: !entries.length, onSelect: () => { const r = document.createRange(); r.selectNodeContents(ref.current!); getSelection()?.removeAllRanges(); getSelection()?.addRange(r) } },
        { label: 'Clear Console', kbd: '⌘L', disabled: !entries.length, onSelect: () => setCleared(Date.now()) },
        'sep',
        { label: 'Insert File Name…', onSelect: () => file.current?.click() },
        'sep',
        { label: 'Word Wrap', checked: wrap, onSelect: () => { setWrap(!wrap); saved.set('console.wrap', !wrap) } },
      ]} />}
    </div>
  )
}

export function cmdline(argv: string[]) {
  const out: string[] = []
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--json') continue
    if (argv[i] === '--projects') { i++; continue }
    out.push(/[\s"']/.test(argv[i]) ? JSON.stringify(argv[i]) : argv[i])
  }
  return 'cad ' + out.join(' ')
}

const ORDER: Record<string, number> = { FAIL: 0, UNCHECKED: 1, PASS: 2 }
export function ChecksView() {
  const checks = useStore((s) => s.checks), status = useStore((s) => s.status), busy = useStore((s) => s.busy)
  const rows = useMemo(() => [...(checks?.rows ?? [])].sort((a, b) => (ORDER[a.state] ?? 3) - (ORDER[b.state] ?? 3)), [checks])
  const pick = (subject: string) => {
    const sc = getState().scene
    const hit = sc?.bodies.find((b) => b.name === subject) ?? sc?.bodies.find((b) => b.part === subject)
    if (hit) select(hit.name)
  }
  return (
    <div className="checks">
      <div className="chead">
        <span className={cls('verdict', (status?.done ? 'pass' : status?.verdict ?? 'none').toLowerCase())}
          title={status?.reasons?.join('\n')}>{status?.done ? 'DONE' : status?.verdict ?? 'NOT VERIFIED'}</span>
        <span>{rows.length} checks, {rows.filter((r) => r.state === 'FAIL').length} failing</span>
        <span className="spacer" />
        <button className="qbtn" disabled={busy.includes('check')} onClick={runCheck}><Icon name="recompute" />Recompute</button>
        <button className="qbtn" disabled={busy.includes('verify')} onClick={runVerify}><Icon name="pass" />Verify</button>
      </div>
      <table className="ctable">
        <thead><tr><th>State</th><th>Rule</th><th>Subject</th><th>Measured</th><th>Limit</th></tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className={'st-' + r.state.toLowerCase()} onClick={() => pick(r.subject)} title={r.source}>
              <td><Icon name={r.state === 'PASS' ? 'pass' : r.state === 'FAIL' ? 'fail' : 'pending'} size={14} /> {r.state}</td>
              <td>{r.rule}</td><td>{r.subject}</td><td>{r.measured ?? ''}</td><td>{r.limit ?? ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

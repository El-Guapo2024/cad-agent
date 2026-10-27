// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Spreadsheet/Gui/Workbench.cpp: 2015 Eivind Kvedalen
//   src/Mod/Spreadsheet/Gui/Command.cpp: 2015 Eivind Kvedalen
//   src/Mod/Spreadsheet/Gui/SpreadsheetView.cpp: 2015 Eivind Kvedalen
//   src/Mod/Spreadsheet/Gui/SheetTableView.cpp: 2015 Eivind Kvedalen
//   src/Mod/Spreadsheet/Gui/SheetModel.cpp: 2015 Eivind Kvedalen
//   src/Mod/Spreadsheet/Gui/PropertiesDialog.cpp: 2015 Eivind Kvedalen
//   src/Mod/Spreadsheet/Gui/ViewProviderSpreadsheet.cpp: 2015 Eivind Kvedalen
//   No copyright line in the file: src/Mod/Spreadsheet/Gui/Sheet.ui, src/Mod/Spreadsheet/Gui/PropertiesDialog.ui
// The Spreadsheet workbench, for the project's sheets (spreadsheet/<Name>.py: cad_agent/spreadsheet*.py, docs/
// EDITING_PLAN.md "Spreadsheets in a project"): the Spreadsheet menu and toolbar as Workbench.cpp sets them up (the two
// colour pickers WorkbenchHelper adds), the commands of Command.cpp with their names, labels and undo steps, each sheet
// as an MDI view (SheetView: the Content and Alias line edits of Sheet.ui above SheetTableView: cell editing, the
// selection, Enter, Tab and the arrows, copy, cut and paste, merged cells, the row and column headers' menus and sizes),
// the cell's context menu, the Properties dialog (PropertiesDialog.ui) and Set Alias, CSV import and export, the sheets
// in the tree and the property view. What a cell shows is SheetModel::data (spreadsheet_model.ts) over the values the
// server computed; every edit is `cad sheet apply` (POST /api/<slug>/spreadsheet/<sheet>), one undo step.
import { useEffect, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore, type FC, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import type { IDockviewPanelProps } from 'dockview'
import { resultText, type CadResult } from './api'
import { consoleLog, getState, report, setState, subscribe } from './store'
import { loadHistory, openSheetWindow, sheetWindows } from './actions'
import { Icon, type IconName } from './icons'
import { cls, EditRow, Group, Row } from './panels'
import { ContextMenu, type Entry } from './chrome'
import { messageBox } from './msgbox'
import { toNumber, type Quantity } from './quantity'
import { PyError, type PyVal, type VarPath } from './expr'
import {
  AL, aliasProblem, addrText, cellView, cellsOf, colName, copyOf, DEFAULT_ALIGNMENT, DEFAULT_HEIGHT, DEFAULT_WIDTH, encodeAlignment, HEADER_WIDTH,
  headerColumn, isMerged, isValidAlias, moveKey, parseAddr, rangeSize, rangeText, spansOf, VIEW_COLUMNS, VIEW_ROWS,
  type Addr, type Clip, type Rng, type SsCell, type SsSheet,
} from './spreadsheet_model'
import './spreadsheet.css'

// ── the model: the server's sheets (spreadsheet_edit.read) ─────────────────────────────────────────────────────────
type SheetView = { cur: Addr; ranges: Rng[]; anchor: Addr; tab: number }
type ClipState = { clip: Clip; text: string; sheet: string; ranges: Rng[]; copy: boolean } | null
type SsState = { names: string[]; sheets: Record<string, SsSheet>; parts: Record<string, { params: Record<string, unknown>; bound: Record<string, unknown>; expressions: Record<string, string>; errors: Record<string, string> }>
  sel: string[]; views: Record<string, SheetView>; clip: ClipState; recompute: Record<string, string> }
let st: SsState = { names: [], sheets: {}, parts: {}, sel: [], views: {}, clip: null, recompute: {} }
const subs = new Set<() => void>()
export const ssState = () => st
export function setSs(p: Partial<SsState> | ((s: SsState) => Partial<SsState>)) {
  st = { ...st, ...(typeof p === 'function' ? p(st) : p) }
  subs.forEach((f) => f())
}
export function useSs<T>(sel: (s: SsState) => T): T {
  return useSyncExternalStore((f) => { subs.add(f); return () => { subs.delete(f) } }, () => sel(st))
}
const msg = (e: unknown) => (e instanceof Error ? e.message : String(e))
const enc = encodeURIComponent
async function http(method: 'GET' | 'POST', path: string, body?: unknown): Promise<CadResult> {
  const r = await fetch(path, method === 'GET' ? {} : { method, headers: { 'Content-Type': 'application/json', 'X-CAD': '1' }, body: JSON.stringify(body ?? {}) })
  const text = await r.text()
  let j: CadResult
  try { j = JSON.parse(text) } catch { throw new Error(text.slice(0, 300)) }
  if (!r.ok) throw new Error((j as unknown as { error?: string }).error || r.statusText)
  return j
}
const viewOf = (name: string): SheetView => st.views[name] ?? { cur: { row: 0, col: 0 }, ranges: [], anchor: { row: 0, col: 0 }, tab: 0 }
const setView = (name: string, v: Partial<SheetView>) => setSs((s) => ({ views: { ...s.views, [name]: { ...viewOf(name), ...v } } }))
type DocData = { sheets: Record<string, SsSheet>; parts: SsState['parts']; recompute: Record<string, string> }
function take(d: DocData) {
  setSs((s) => ({ sheets: d.sheets, names: Object.keys(d.sheets).sort(), parts: d.parts ?? {}, recompute: d.recompute ?? {},
    sel: s.sel.filter((n) => d.sheets[n]) }))
  for (const [k, m] of Object.entries(d.recompute ?? {})) report('warn', `${k}: ${m}`)
}

let loading = 0
/** `cad sheet ls`, then the document (`cad sheet show`: every sheet recomputed with the project's parts). */
export async function loadSheets() {
  const slug = getState().slug
  if (!slug) { setSs({ names: [], sheets: {}, parts: {}, sel: [] }); return }
  const n = ++loading
  try {
    const r = await http('GET', `/api/${enc(slug)}/spreadsheet`)
    if (n !== loading || slug !== getState().slug) return
    const names = ((r.data?.sheets ?? []) as { sheet: string }[]).map((x) => x.sheet)
    if (!names.length) { setSs({ names: [], sheets: {}, parts: r.data?.parts ?? {}, sel: [] }); return }
    const d = await http('GET', `/api/${enc(slug)}/spreadsheet/${enc(names[0])}`)
    if (n !== loading || slug !== getState().slug) return
    if (d.exit === 0) take(d.data as DocData)
    else report('err', `Spreadsheet: ${resultText(d)}`)
  } catch (e) { report('err', `Spreadsheet: ${msg(e)}`) }
}

/** `cad sheet apply`: the ops (Sheet methods, as the GUI's commands call them) as one undo step named as FreeCAD's
 *  transaction. Returns whether it was applied. */
export async function applySs(sheet: string, ops: Record<string, unknown>[], name?: string): Promise<boolean> {
  const s = getState()
  if (!s.slug) return false
  if (s.scriptToPyConsole) consoleLog('in', `cad sheet apply ${s.slug} ${sheet} --ops '${JSON.stringify(ops)}'${name ? ` --name '${name}'` : ''}`)
  try {
    const r = await http('POST', `/api/${enc(s.slug)}/spreadsheet/${enc(sheet)}`, { ops, ...(name ? { name } : {}) })
    if (r.exit !== 0) { report('err', `${name ?? 'Spreadsheet'}: ${resultText(r)}`); return false }
    const doc = r.data?.doc as (DocData & { deleted?: string }) | undefined
    if (doc?.deleted) { await loadSheets(); loadHistory(); return true }
    if (doc) take(doc)
    loadHistory()
    return true
  } catch (e) { report('err', `${name ?? 'Spreadsheet'}: ${msg(e)}`); return false }
}

// the project changed: its sheets
let lastSlug: string | null = null
subscribe(() => { const s = getState(); if (s.slug !== lastSlug) { lastSlug = s.slug; setSs({ names: [], sheets: {}, parts: {}, sel: [], views: {}, clip: null }); void loadSheets() } })

// ── the active sheet (Gui::getMainWindow()->activeWindow() as a SheetView) ─────────────────────────────────────────
export const activeSheet = (): string | null => sheetWindows().find((w) => w.active)?.sheet ?? null
/** Document::getUniqueObjectName over the project's sheets and parts (one document). */
export function uniqueName(base: string): string {
  const taken = new Set([...st.names, ...Object.keys(getState().features ?? {}), ...(getState().scene?.bodies.map((b) => b.part ?? b.name) ?? [])])
  if (!taken.has(base)) return base
  for (let i = 1; ; i++) { const n = `${base}${String(i).padStart(3, '0')}`; if (!taken.has(n)) return n }
}
/** ViewProviderSheet::doubleClicked: the Spreadsheet workbench (SwitchToWB), then the sheet's view. */
export function openSheet(name: string, switchWb = true) {
  if (switchWb) setState({ workbench: 'spreadsheet' })
  openSheetWindow(name, st.sheets[name]?.label ?? name)
}
const selectionOf = (name: string) => viewOf(name).ranges
/** SheetTableView::selectedIndexes: every selected cell (a merged cell once). */
function selectedCells(name: string): Addr[] {
  const out: Addr[] = [], seen = new Set<string>()
  for (const r of selectionOf(name)) for (const a of cellsOf(r)) { const k = addrText(a); if (!seen.has(k)) { seen.add(k); out.push(a) } }
  return out
}

// ── the commands (Command.cpp; WorkbenchHelper's colours) ──────────────────────────────────────────────────────
type Cmd = { text: string; tip: string; icon: IconName; run: () => void | Promise<void>; active: () => boolean; accel?: string }
const onSheet = () => !!activeSheet()
const forRanges = (step: string, op: (r: string) => Record<string, unknown> | null) => {
  const sh = activeSheet()
  if (!sh) return
  const ops = selectionOf(sh).map((r) => op(rangeText(r))).filter(Boolean) as Record<string, unknown>[]
  if (ops.length) void applySs(sh, ops, step)
}
const align = (word: string, step: string) => () => forRanges(step, (r) => ({ op: 'setAlignment', args: [r, word, 'keep'] }))
function style(word: 'bold' | 'italic' | 'underline', step: string) {
  return () => {
    const sh = activeSheet()
    if (!sh) return
    const cells = selectedCells(sh)
    if (!cells.length) return
    const all = cells.every((a) => { const c = st.sheets[sh]?.cells[addrText(a)]; return !c || c.raw.style.includes(word) })
    forRanges(step, (r) => ({ op: 'setStyle', args: [r, word, all ? 'remove' : 'add'] }))
  }
}
async function createSheet() {
  if (!getState().slug) { void messageBox('warning', 'No document', 'Make or open a document first'); return }
  const name = uniqueName('Spreadsheet')
  if (await applySs(name, [{ op: 'new' }], 'Create Spreadsheet')) { setSs({ sel: [name] }); openSheet(name, false) }
}
/** Spreadsheet_Import: a CSV file (Gui::FileDialog) into a new sheet, with Preferences' delimiter (tab), quote and escape. */
function importSheet() {
  if (!getState().slug) return
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.csv,text/csv,text/plain'
  input.onchange = async () => {
    const f = input.files?.[0]
    if (!f) return
    const text = await f.text()
    const name = uniqueName('Spreadsheet')
    if (await applySs(name, [{ op: 'new' }, { op: 'import', text }], 'Import Spreadsheet')) openSheet(name, false)
  }
  input.click()
}
function exportSheet() {
  const sh = activeSheet()
  const d = sh ? st.sheets[sh] : null
  if (!d) return
  const blob = new Blob([d.csv], { type: 'text/csv' })   // Sheet::exportToFile, as the server wrote it (sheet_json)
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `${d.label}.csv`
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 1000)
}
function mergeCells() {
  forRanges('Merge cells', (r) => (rangeSize(rangeOf(r)) > 1 ? { op: 'mergeCells', args: [r] } : null))
}
const rangeOf = (r: string): Rng => { const [a, b] = r.split(':').map((x) => parseAddr(x)!); return { r1: a.row, c1: a.col, r2: b.row, c2: b.col } }
function splitCell() {
  const sh = activeSheet()
  if (!sh) return
  void applySs(sh, [{ op: 'splitCell', args: [addrText(viewOf(sh).cur)] }], 'Sp&lit cell')
}
const oneCell = () => { const sh = activeSheet(); return !!sh && selectedCells(sh).length === 1 }
export const SS_CMDS: Record<string, Cmd> = {
  Spreadsheet_CreateSheet: { text: '&New Spreadsheet', tip: 'Creates a new spreadsheet', icon: 'ss-Spreadsheet', run: createSheet, active: () => !!getState().slug },
  Spreadsheet_Import: { text: '&Import Spreadsheet', tip: 'Imports a CSV file into a new spreadsheet', icon: 'ss-SpreadsheetImport', run: importSheet, active: () => !!getState().slug },
  Spreadsheet_Export: { text: '&Export Spreadsheet', tip: 'Exports the spreadsheet to a CSV file', icon: 'ss-SpreadsheetExport', run: exportSheet, active: onSheet },
  Spreadsheet_MergeCells: { text: '&Merge Cells', tip: 'Merges the selected cells', icon: 'ss-SpreadsheetMergeCells', run: mergeCells, active: () => { const sh = activeSheet(); return !!sh && selectedCells(sh).length > 1 } },
  Spreadsheet_SplitCell: { text: 'Sp&lit Cell', tip: 'Splits a previously merged cell', icon: 'ss-SpreadsheetSplitCell', run: splitCell,
    active: () => { const sh = activeSheet(); return !!sh && !!st.sheets[sh] && selectedCells(sh).length === 1 && isMerged(st.sheets[sh], viewOf(sh).cur) } },
  Spreadsheet_AlignLeft: { text: 'Align &Left', tip: 'Aligns cell contents to the left', icon: 'ss-SpreadsheetAlignLeft', run: align('left', 'Left-align cell'), active: onSheet },
  Spreadsheet_AlignCenter: { text: 'Align Horizontal &Center', tip: 'Aligns cell contents to the horizontal center', icon: 'ss-SpreadsheetAlignCenter', run: align('center', 'Center cell'), active: onSheet },
  Spreadsheet_AlignRight: { text: 'Align &Right', tip: 'Aligns cell contents to the right', icon: 'ss-SpreadsheetAlignRight', run: align('right', 'Right-align cell'), active: onSheet },
  Spreadsheet_AlignTop: { text: 'Align &Top', tip: 'Aligns cell contents to the top', icon: 'ss-SpreadsheetAlignTop', run: align('top', 'Top-align cell'), active: onSheet },
  Spreadsheet_AlignVCenter: { text: 'Align &Vertical Center', tip: 'Aligns cell contents to the vertical center', icon: 'ss-SpreadsheetAlignVCenter', run: align('vcenter', 'Vertically center cells'), active: onSheet },
  Spreadsheet_AlignBottom: { text: 'Align &Bottom', tip: 'Aligns cell contents to the bottom', icon: 'ss-SpreadsheetAlignBottom', run: align('bottom', 'Bottom-align cell'), active: onSheet },
  Spreadsheet_StyleBold: { text: '&Bold Text', tip: 'Sets the text in the selected cells bold', icon: 'ss-SpreadsheetStyleBold', run: style('bold', 'Set bold text'), active: onSheet, accel: 'Ctrl+B' },
  Spreadsheet_StyleItalic: { text: '&Italic Text', tip: 'Sets the text in the selected cells italic', icon: 'ss-SpreadsheetStyleItalic', run: style('italic', 'Set italic text'), active: onSheet, accel: 'Ctrl+I' },
  Spreadsheet_StyleUnderline: { text: '&Underline Text', tip: 'Underlines the text in the selected cells', icon: 'ss-SpreadsheetStyleUnderline', run: style('underline', 'Set underline text'), active: onSheet, accel: 'Ctrl+U' },
  Spreadsheet_SetAlias: { text: 'Set Alias', tip: 'Sets an alias for the selected cell', icon: 'ss-SpreadsheetAlias', run: () => openProps(true), active: oneCell, accel: 'Ctrl+Shift+A' },
}
const e = (cmd: string): Exclude<Entry, 'sep'> => {
  const c = SS_CMDS[cmd]
  return { label: c.text.replace(/&(.)/g, '$1'), icon: c.icon, cmd, disabled: !c.active(), onSelect: () => void c.run(), title: c.tip, kbd: c.accel?.replace('Ctrl+', '⌃').replace('Shift+', '⇧') }
}
/** Workbench::setupMenuBar: "&Spreadsheet", inserted before Windows. */
export function spreadsheetMenu(): Entry[] {
  return [e('Spreadsheet_CreateSheet'), 'sep', e('Spreadsheet_Import'), e('Spreadsheet_Export'), 'sep', e('Spreadsheet_MergeCells'), e('Spreadsheet_SplitCell'), 'sep',
    { label: 'Alignment', sub: ['Spreadsheet_AlignLeft', 'Spreadsheet_AlignCenter', 'Spreadsheet_AlignRight', 'Spreadsheet_AlignTop', 'Spreadsheet_AlignVCenter', 'Spreadsheet_AlignBottom'].map(e) },
    { label: 'Styles', sub: ['Spreadsheet_StyleBold', 'Spreadsheet_StyleItalic', 'Spreadsheet_StyleUnderline'].map(e) }]
}
/** Workbench::setupToolBars: the Spreadsheet toolbar (the colour pickers are spreadsheetColorPickers, after it). */
export function spreadsheetToolbar(): Entry[] {
  return [e('Spreadsheet_CreateSheet'), 'sep', e('Spreadsheet_Import'), e('Spreadsheet_Export'), 'sep', e('Spreadsheet_MergeCells'), e('Spreadsheet_SplitCell'), 'sep',
    ...['Spreadsheet_AlignLeft', 'Spreadsheet_AlignCenter', 'Spreadsheet_AlignRight', 'Spreadsheet_AlignTop', 'Spreadsheet_AlignVCenter', 'Spreadsheet_AlignBottom'].map(e), 'sep',
    ...['Spreadsheet_StyleBold', 'Spreadsheet_StyleItalic', 'Spreadsheet_StyleUnderline'].map(e), 'sep', e('Spreadsheet_SetAlias'), 'sep']
}
export const spreadsheetCommands = (): [string, Cmd][] => Object.entries(SS_CMDS)
export const spreadsheetRun = (cmd: string) => { const c = SS_CMDS[cmd]; if (c?.active()) void c.run() }
export const spreadsheetEnabled = (cmd: string) => !!SS_CMDS[cmd]?.active()
/** The menu and toolbar as plain data, for spreadsheetcheck.mjs (cadui.spreadsheet()). */
export function spreadsheetMenus() {
  const plain = (es: Entry[]): unknown[] => es.map((x) => (x === 'sep' ? { sep: true } : { text: x.label, cmd: x.cmd ?? null, enabled: !x.disabled, kbd: x.kbd ?? null, ...(x.sub ? { menu: plain(x.sub) } : {}) }))
  return { menu: plain(spreadsheetMenu()), toolbar: plain(spreadsheetToolbar()) }
}

// ── QtColorPicker (WorkbenchHelper::setForegroundColor / setBackgroundColor) ────────────────────────────────────
/** QtColorPicker::setStandardColors: Qt's 17 named colours. */
const STANDARD = [['#ffffff', 'White'], ['#000000', 'Black'], ['#ff0000', 'Red'], ['#800000', 'Dark red'], ['#00ff00', 'Green'], ['#008000', 'Dark green'],
  ['#0000ff', 'Blue'], ['#000080', 'Dark blue'], ['#00ffff', 'Cyan'], ['#008080', 'Dark cyan'], ['#ff00ff', 'Magenta'], ['#800080', 'Dark magenta'],
  ['#ffff00', 'Yellow'], ['#808000', 'Dark yellow'], ['#a0a0a4', 'Gray'], ['#808080', 'Dark gray'], ['#c0c0c0', 'Light gray']]
const rgbF = (hex: string) => [1, 3, 5].map((i) => Number(`0x${hex.slice(i, i + 2)}`) / 255)
function colorTo(fg: boolean, hex: string | null) {
  const sh = activeSheet()
  if (!sh) return
  if (hex === null) forRanges(fg ? 'Clear text color' : 'Clear background color', (r) => ({ op: fg ? 'clearForeground' : 'clearBackground', args: [r] }))
  else forRanges(fg ? 'Set text color' : 'Set background color', (r) => ({ op: fg ? 'setForeground' : 'setBackground', args: [r, rgbF(hex)] }))
}
/** The two QtColorPicker buttons Workbench::activated adds to the toolbar: a swatch of the last colour, a popup of the
 *  standard colours, "More..." (QColorDialog) and "Clear". */
export function ColorPickers() {
  const [open, setOpen] = useState<{ fg: boolean; x: number; y: number } | null>(null)
  const [last, setLast] = useState({ fg: '#000000', bg: '#ffffff' })
  const pick = useRef<HTMLInputElement>(null)
  const set = (fg: boolean, hex: string | null) => { if (hex) setLast((l) => ({ ...l, [fg ? 'fg' : 'bg']: hex })); colorTo(fg, hex); setOpen(null) }
  return (
    <>
      {([true, false] as const).map((fg) => (
        <button key={String(fg)} className="tb-btn ss-color" data-cmd={fg ? 'Spreadsheet_ForegroundColor' : 'Spreadsheet_BackgroundColor'}
          title={fg ? 'Sets the text color of cells' : 'Sets the background color of cells'} disabled={!onSheet()}
          onClick={(ev) => { const r = ev.currentTarget.getBoundingClientRect(); setOpen(open ? null : { fg, x: r.left, y: r.bottom + 1 }) }}>
          <span className="ss-swatch" style={{ background: fg ? last.fg : last.bg }} /><span className="tb-caret">▾</span>
        </button>))}
      <input ref={pick} type="color" style={{ display: 'none' }} onChange={(ev) => open && set(open.fg, ev.target.value)} />
      {open && createPortal(
        <div className="mb-content ctx ss-colors" style={{ left: open.x, top: open.y }} onMouseLeave={() => setOpen(null)}>
          <div className="ss-grid">{STANDARD.map(([hex, name]) => <button key={hex} title={name} style={{ background: hex }} onClick={() => set(open.fg, hex)} />)}</div>
          <div className="ss-more" onClick={() => pick.current?.click()}>More...</div>
          <div className="ss-more" onClick={() => set(open.fg, null)}>Clear</div>
        </div>, document.body)}
    </>
  )
}

// ── what the Edit menu does on a sheet (SheetView::onMsg) ───────────────────────────────────────────────────────
/** Std_Delete, Std_Cut, Std_Copy and Std_Paste while a sheet's view is active: true when the sheet took it. */
export function sheetMsg(m: 'Std_Delete' | 'Cut' | 'Copy' | 'Paste'): boolean {
  const sh = activeSheet()
  if (!sh || !st.sheets[sh]) return false
  if (m === 'Std_Delete') { deleteSelection(sh, true); return true }
  if (m === 'Copy' || m === 'Cut') { copySelection(sh, m === 'Copy'); return true }
  void pasteClipboard(sh)
  return true
}
export const sheetActive = () => !!activeSheet()

/** SheetTableView::deleteSelection ("Clear Cells"); SheetView's Std_Delete only when a selected range holds a cell. */
function deleteSelection(sh: string, onlyIfCells = false) {
  const d = st.sheets[sh]
  const ranges = selectionOf(sh)
  if (onlyIfCells && !ranges.some((r) => [...cellsOf(r)].some((a) => d.cells[addrText(a)]))) return
  void applySs(sh, ranges.map((r) => ({ op: 'clear', args: [rangeText(r)] })), 'Clear Cells')
}
function copySelection(sh: string, copy: boolean, ranges = selectionOf(sh)) {
  const { text, clip } = copyOf(st.sheets[sh], ranges)
  setSs({ clip: { clip, text, sheet: sh, ranges, copy } })
  void navigator.clipboard?.writeText(text).catch(() => {})
}
/** SheetTableView::pasteClipboard ("Paste Cell"): the copied cells at the selection's top left, tiled over it when one
 *  range was copied, relative references moved; after a Cut, the cut cells cleared. Text from outside goes cell by cell. */
async function pasteClipboard(sh: string) {
  const ranges = selectionOf(sh)
  if (!ranges.length) return
  const dst = ranges[ranges.length - 1]
  const c = st.clip
  if (c) {
    // the cells' own mime data (application/x-fc-spreadsheet); a cut is cleared from its own sheet only
    const cut = !c.copy && c.sheet === sh
    const ok = await applySs(sh, [{ op: 'paste', clip: c.clip, to: rangeText(dst), ...(cut ? { cut: c.ranges.map(rangeText) } : {}) }], 'Paste Cell')
    if (ok && !c.copy) setSs({ clip: { ...c, copy: true } })
    return
  }
  let text = ''
  try { text = (await navigator.clipboard?.readText()) ?? text } catch { /* the page may not read the clipboard */ }
  if (!text) return
  const ops: Record<string, unknown>[] = []
  text.split('\n').forEach((line, i) => line.split('\t').forEach((cell, j) => {
    const addr = addrText({ row: dst.r1 + i, col: dst.c1 + j })
    const old = st.sheets[sh].cells[addr]?.content ?? ''
    if (cell !== old) ops.push({ op: 'set', args: [addr, cell] })
  }))
  if (ops.length) await applySs(sh, ops, 'Paste Cell')
}

// ── the Properties dialog (PropertiesDialog.ui, PropertiesDialog.cpp) ───────────────────────────────────────────
type PropsAsk = { sheet: string; ranges: Rng[]; alias: boolean } | null
let propsAsk: PropsAsk = null
const propsSubs = new Set<() => void>()
function openProps(alias = false) {
  const sh = activeSheet()
  if (!sh) return
  const ranges = alias ? [{ ...selectionOf(sh)[0], r2: viewOf(sh).cur.row, c2: viewOf(sh).cur.col, r1: viewOf(sh).cur.row, c1: viewOf(sh).cur.col }] : selectionOf(sh)
  if (!ranges.length) return
  propsAsk = { sheet: sh, ranges, alias }
  propsSubs.forEach((f) => f())
}
const closeProps = () => { propsAsk = null; propsSubs.forEach((f) => f()) }
const usePropsAsk = () => useSyncExternalStore((f) => { propsSubs.add(f); return () => { propsSubs.delete(f) } }, () => propsAsk)

const hexOf = (c: number[] | null) => (c ? '#' + c.slice(0, 3).map((x) => Math.round(255 * x).toString(16).padStart(2, '0')).join('') : null)
function PropertiesDialog({ ask }: { ask: NonNullable<PropsAsk> }) {
  const d = st.sheets[ask.sheet]
  const first = ask.ranges[0]
  const c0: SsCell | undefined = d?.cells[addrText({ row: first.r1, col: first.c1 })]
  const org = {
    fg: c0?.raw.fg ?? null, bg: c0?.raw.bg ?? null, alignment: c0?.raw.alignment ?? DEFAULT_ALIGNMENT, style: [...(c0?.raw.style ?? [])].sort(),
    unit: c0?.raw.du?.text ?? '', alias: c0?.raw.alias ?? '',
  }
  const [tab, setTab] = useState(ask.alias ? 4 : 0)
  const [fg, setFg] = useState<string | null>(hexOf(org.fg))
  const [bg, setBg] = useState<string | null>(hexOf(org.bg))
  const [alignment, setAlignment] = useState(org.alignment)
  const [styleSet, setStyle] = useState<string[]>(org.style)
  const [unit, setUnit] = useState(org.unit)
  const [alias, setAlias] = useState(org.alias)
  const aliasOne = ask.ranges.length === 1 && rangeSize(ask.ranges[0]) === 1
  const problem = alias && alias !== org.alias ? aliasProblem(d, alias) : null
  const unitOk = !unit || /^[A-Za-zµ°"'/*^()0-9\- ]+$/.test(unit)   // ExpressionParser::parseUnit is the server's; the colour only
  const ok = unitOk && !problem
  const setH = (bit: number) => setAlignment((a) => (a & ~AL.HORIZONTAL) | bit)
  const setV = (bit: number) => setAlignment((a) => (a & ~AL.VERTICAL) | bit)
  const toggle = (s: string) => setStyle((x) => (x.includes(s) ? x.filter((y) => y !== s) : [...x, s].sort()))
  const apply = () => {
    const ops: Record<string, unknown>[] = []
    const f = (x: string | null) => (x ? [...rgbF(x), 1] : null)
    for (const r of ask.ranges) {
      const t = rangeText(r)
      if (alignment !== org.alignment) ops.push({ op: 'setAlignment', args: [t, encodeAlignment(alignment)] })
      if (styleSet.join('|') !== org.style.join('|')) ops.push({ op: 'setStyle', args: [t, styleSet.join('|')] })
      if (org.fg && !fg) ops.push({ op: 'clearForeground', args: [t] })
      if (fg && fg !== hexOf(org.fg)) ops.push({ op: 'setForeground', args: [t, f(fg)] })
      if (org.bg && !bg) ops.push({ op: 'clearBackground', args: [t] })
      if (bg && bg !== hexOf(org.bg)) ops.push({ op: 'setBackground', args: [t, f(bg)] })
      if (unit !== org.unit) ops.push({ op: 'setDisplayUnit', args: [t, unit] })
      if (aliasOne && alias !== org.alias) ops.push({ op: 'setAlias', args: [addrText({ row: r.r1, col: r.c1 }), alias] })
    }
    closeProps()
    if (ops.length) void applySs(ask.sheet, ops, 'Set cell properties')
  }
  const TABS = ['&Color', '&Alignment', '&Style', '&Display unit', 'A&lias']
  return createPortal(
    <div className="ss-modal" onKeyDown={(ev) => { if (ev.key === 'Escape') closeProps(); if (ev.key === 'Enter' && ok) apply() }}>
      <div className="ss-dialog" role="dialog" aria-label="Cell Properties" data-dialog="PropertiesDialog">
        <div className="ss-dtitle">Cell Properties</div>
        <div className="ss-tabs" role="tablist">{TABS.map((t, i) => (
          <button key={t} role="tab" className={cls('ss-tab', tab === i && 'sel')} disabled={i === 4 && !aliasOne} onClick={() => setTab(i)}>{t.replace('&', '')}</button>))}</div>
        <div className="ss-tabpage">
          {tab === 0 && <div className="ss-form">
            <label>Text</label><ColorField name="foregroundColor" value={fg} onChange={setFg} />
            <label>Background</label><ColorField name="backgroundColor" value={bg} onChange={setBg} />
          </div>}
          {tab === 1 && <div className="ss-form">
            <label>Horizontal</label><span className="ss-radios">
              {([['alignLeft', 'Left', AL.LEFT], ['alignHCenter', 'Center', AL.HCENTER], ['alignRight', 'Right', AL.RIGHT]] as const).map(([n, t, bit]) => (
                <label key={n}><input type="radio" name="h" data-name={n} checked={!!(alignment & bit)} onChange={() => setH(bit)} />{t}</label>))}</span>
            <label>Vertical</label><span className="ss-radios">
              {([['alignTop', 'Top', AL.TOP], ['alignVCenter', 'Center', AL.VCENTER], ['alignBottom', 'Bottom', AL.BOTTOM]] as const).map(([n, t, bit]) => (
                <label key={n}><input type="radio" name="v" data-name={n} checked={!!(alignment & bit)} onChange={() => setV(bit)} />{t}</label>))}</span>
          </div>}
          {tab === 2 && <div className="ss-form ss-checks">
            {([['styleBold', 'Bold', 'bold'], ['styleItalic', 'Italic', 'italic'], ['styleUnderline', 'Underline', 'underline']] as const).map(([n, t, s]) => (
              <label key={n}><input type="checkbox" data-name={n} checked={styleSet.includes(s)} onChange={() => toggle(s)} />{t}</label>))}
          </div>}
          {tab === 3 && <div className="ss-form">
            <label>Text for the unit</label><input data-name="displayUnit" className={cls(!unitOk && 'bad')} value={unit} onChange={(ev) => setUnit(ev.target.value)} autoFocus />
          </div>}
          {tab === 4 && <div className="ss-form">
            <label>Alias for this cell</label>
            <input data-name="alias" className={cls(problem && 'bad')} value={alias} autoFocus onChange={(ev) => setAlias(ev.target.value)}
              title={problem?.tip ?? 'Allows referring to a cell by an alias name, for example\nSpreadsheet.my_alias_name instead of Spreadsheet.B1'} />
            {problem && <span className="ss-status" data-name="aliasStatus">{problem.status}</span>}
          </div>}
        </div>
        <div className="ss-buttons"><button disabled={!ok} onClick={apply}>OK</button><button onClick={closeProps}>Cancel</button></div>
      </div>
    </div>, document.body)
}
function ColorField({ name, value, onChange }: { name: string; value: string | null; onChange(v: string | null): void }) {
  // QtColorPicker with the standard colours; its button says "Default" until a colour is set (setDefaultColor)
  return <span className="ss-colorfield" data-name={name} data-text={value ? value : 'Default'}>
    <input type="color" value={value ?? '#000000'} onChange={(ev) => onChange(ev.target.value)} />
    <span className="ss-colortext">{value ? value : 'Default'}</span>
    {value && <button onClick={() => onChange(null)} title="Clear">Clear</button>}</span>
}
/** Where the dialog and the menus of the sheet views are drawn (one per page). */
export function SpreadsheetOverlays() {
  const ask = usePropsAsk()
  return ask ? <PropertiesDialog key={`${ask.sheet}:${ask.alias}`} ask={ask} /> : null
}

// ── the sheet's window (SheetView: Sheet.ui; SheetTableView) ────────────────────────────────────────────────────
type PanelParams = { sheet: string }
const sizesOf = (d: SsSheet, rows: number, cols: number) => {
  const w: number[] = [], h: number[] = []
  for (let c = 0; c < cols; c++) w.push(d.column_widths[colName(c)] ?? DEFAULT_WIDTH)
  for (let r = 0; r < rows; r++) h.push(d.row_heights[String(r + 1)] ?? DEFAULT_HEIGHT)
  const x = [0], y = [0]
  for (const v of w) x.push(x[x.length - 1] + v)
  for (const v of h) y.push(y[y.length - 1] + v)
  return { w, h, x, y }
}
const inRanges = (rs: Rng[], r: number, c: number) => rs.some((x) => r >= x.r1 && r <= x.r2 && c >= x.c1 && c <= x.c2)
const HEAD_H = 24

export const SpreadsheetView: FC<IDockviewPanelProps<PanelParams>> = (props) => {
  const [p, setP] = useState<PanelParams>(props.params)
  useEffect(() => { const dsp = props.api.onDidParametersChange((np) => setP(np as PanelParams)); return () => dsp.dispose() }, [props.api])
  const name = p.sheet
  const d = useSs((s) => s.sheets[name])
  const view = useSs((s) => s.views[name]) ?? viewOf(name)
  const clip = useSs((s) => s.clip)
  const [edit, setEdit] = useState<{ addr: Addr; text: string } | null>(null)
  const [menu, setMenu] = useState<{ x: number; y: number; entries: Entry[] } | null>(null)
  const [scroll, setScroll] = useState({ x: 0, y: 0, w: 800, h: 600 })
  const [content, setContent] = useState('')
  const [aliasText, setAliasText] = useState('')
  const grid = useRef<HTMLDivElement>(null)
  const drag = useRef<{ from: Addr; add: boolean } | null>(null)
  const resize = useRef<{ kind: 'col' | 'row'; i: number; start: number; size: number } | null>(null)
  const [live, setLive] = useState<{ kind: 'col' | 'row'; i: number; size: number } | null>(null)
  useEffect(() => { if (d && props.api.title !== d.label) props.api.setTitle(d.label) }, [d?.label]) // eslint-disable-line react-hooks/exhaustive-deps
  const rows = Math.max(VIEW_ROWS, (d && d.used_range ? parseAddr(d.used_range[1])!.row + 1 : 0))
  const cols = Math.max(VIEW_COLUMNS, (d && d.used_range ? parseAddr(d.used_range[1])!.col + 1 : 0))
  const sz = useMemo(() => {
    const s = d ? sizesOf(d, rows, cols) : sizesOf({ column_widths: {}, row_heights: {} } as SsSheet, rows, cols)
    if (live) {
      const arr = live.kind === 'col' ? s.w : s.h
      arr[live.i] = live.size
      const acc = [0]
      for (const v of arr) acc.push(acc[acc.length - 1] + v)
      if (live.kind === 'col') s.x = acc
      else s.y = acc
    }
    return s
  }, [d, rows, cols, live])
  const cur = view.cur
  const curCell = d?.cells[addrText(cur)]
  // SheetView::updateContentLine / updateAliasLine: the current cell's content and alias
  useEffect(() => { setContent(curCell?.content ?? ''); setAliasText(curCell?.raw.alias ?? '') }, [name, cur.row, cur.col, curCell?.content, curCell?.raw.alias])
  useLayoutEffect(() => {
    const el = grid.current
    if (!el) return
    const upd = () => setScroll({ x: el.scrollLeft, y: el.scrollTop, w: el.clientWidth, h: el.clientHeight })
    upd()
    const ro = new ResizeObserver(upd)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  if (!d) return <div className="ss-view empty">Loading {name}…</div>

  const select = (to: Addr, mode: 'set' | 'extend' | 'add') => {
    const a = view.anchor
    if (mode === 'extend') {
      const r = { r1: Math.min(a.row, to.row), c1: Math.min(a.col, to.col), r2: Math.max(a.row, to.row), c2: Math.max(a.col, to.col) }
      setView(name, { ranges: [...view.ranges.slice(0, -1), expandMerged(d, r)], cur: to })
    } else if (mode === 'add') setView(name, { ranges: [...view.ranges, expandMerged(d, { r1: to.row, c1: to.col, r2: to.row, c2: to.col })], cur: to, anchor: to })
    else setView(name, { ranges: [expandMerged(d, { r1: to.row, c1: to.col, r2: to.row, c2: to.col })], cur: to, anchor: to, tab: 0 })
  }
  const hit = (cx: number, cy: number): Addr | null => {
    const el = grid.current!
    const r = el.getBoundingClientRect()
    const x = cx - r.left + el.scrollLeft - HEADER_WIDTH, y = cy - r.top + el.scrollTop - HEAD_H
    if (x < 0 || y < 0) return null
    const col = bisect(sz.x, x), row = bisect(sz.y, y)
    if (col < 0 || row < 0 || col >= cols || row >= rows) return null
    return anchorOfAddr(d, { row, col })
  }
  const commit = async (a: Addr, text: string) => {
    // SheetModel::setData: nothing when the text is the cell's content already
    const old = d.cells[addrText(a)]?.content ?? ''
    if (text === old) return
    await applySs(name, [{ op: 'set', args: [addrText(a), text] }], 'Edit cell')
  }
  const move = (key: string, mods: { shift: boolean; ctrl: boolean }) => {
    const r = moveKey(d, view.cur, key, mods, view.tab, rows, cols)
    if (mods.shift && !['Tab', 'Enter'].includes(key)) {
      // ModifyBlockSelection: the block from the anchor to the target
      const a = view.anchor
      setView(name, { ranges: [...view.ranges.slice(0, -1), { r1: Math.min(a.row, r.to.row), c1: Math.min(a.col, r.to.col), r2: Math.max(a.row, r.to.row), c2: Math.max(a.col, r.to.col) }], cur: r.to, tab: r.tab })
    } else setView(name, { ranges: [expandMerged(d, { r1: r.to.row, c1: r.to.col, r2: r.to.row, c2: r.to.col })], cur: r.to, anchor: r.to, tab: r.tab })
    scrollTo(r.to)
  }
  const scrollTo = (a: Addr) => {
    const el = grid.current
    if (!el) return
    const x0 = sz.x[a.col], x1 = sz.x[a.col + 1], y0 = sz.y[a.row], y1 = sz.y[a.row + 1]
    if (x0 < el.scrollLeft) el.scrollLeft = x0
    if (x1 + HEADER_WIDTH > el.scrollLeft + el.clientWidth) el.scrollLeft = x1 + HEADER_WIDTH - el.clientWidth
    if (y0 < el.scrollTop) el.scrollTop = y0
    if (y1 + HEAD_H > el.scrollTop + el.clientHeight) el.scrollTop = y1 + HEAD_H - el.clientHeight
  }
  const onKey = (ev: React.KeyboardEvent) => {
    if (edit) return
    const ctrl = ev.ctrlKey || ev.metaKey, mods = { shift: ev.shiftKey, ctrl }
    const nav: Record<string, string> = { Enter: 'Enter', Tab: 'Tab', ArrowLeft: 'ArrowLeft', ArrowRight: 'ArrowRight', ArrowUp: 'ArrowUp', ArrowDown: 'ArrowDown', Home: 'Home', End: 'End' }
    if (nav[ev.key]) { ev.preventDefault(); move(nav[ev.key], mods); return }
    if (ev.key === 'Escape') { setSs({ clip: null }); return }
    if (ctrl && ev.key.toLowerCase() === 'a') { ev.preventDefault(); setView(name, { ranges: [{ r1: 0, c1: 0, r2: rows - 1, c2: cols - 1 }] }); return }
    if (ctrl && ev.key.toLowerCase() === 'c') { ev.preventDefault(); copySelection(name, true); return }
    if (ctrl && ev.key.toLowerCase() === 'x') { ev.preventDefault(); copySelection(name, false); return }
    if (ctrl && ev.key.toLowerCase() === 'v') { ev.preventDefault(); void pasteClipboard(name); return }
    if (ctrl && ev.shiftKey && ev.key.toLowerCase() === 'a') { ev.preventDefault(); openProps(true); return }
    if (ctrl && ['b', 'i', 'u'].includes(ev.key.toLowerCase())) { ev.preventDefault(); spreadsheetRun({ b: 'Spreadsheet_StyleBold', i: 'Spreadsheet_StyleItalic', u: 'Spreadsheet_StyleUnderline' }[ev.key.toLowerCase()]!); return }
    if (ev.key === 'Delete' || ev.key === 'Backspace') { ev.preventDefault(); deleteSelection(name); return }
    if (ev.key === 'F2') { ev.preventDefault(); setEdit({ addr: view.cur, text: curCell?.content ?? '' }); return }
    // QAbstractItemView::AnyKeyPressed: a printable key starts editing with it
    if (ev.key.length === 1 && !ctrl && !ev.altKey) { ev.preventDefault(); setEdit({ addr: view.cur, text: ev.key }) }
  }
  const cellMenu = (x: number, y: number) => {
    const n = selectedCells(name).length
    const merged = n === 1 && isMerged(d, view.cur)
    const hasSel = view.ranges.length > 0
    const conf = view.ranges.length === 1 && rangeSize(view.ranges[0]) > 1
    setMenu({ x, y, entries: [
      { label: 'Properties', onSelect: () => openProps(false), disabled: !hasSel }, 'sep',
      { label: 'Recompute', icon: 'recompute', onSelect: () => void applySs(name, view.ranges.map((r) => ({ op: 'recomputeCells', args: [addrText({ row: r.r1, col: r.c1 }), addrText({ row: r.r2, col: r.c2 })] })), 'Recompute Cells') },
      { label: 'Bind…', disabled: true, title: 'Not in this workbench yet: DlgBindSheet binds cells to another sheet\'s' },
      { label: 'Configuration Table', disabled: true, title: conf ? 'Not in this workbench yet: DlgSheetConf' : undefined }, 'sep',
      { label: 'Merge Cells', icon: 'ss-SpreadsheetMergeCells', disabled: !(hasSel && n > 1), onSelect: mergeCells },
      { label: 'Split Cell', icon: 'ss-SpreadsheetSplitCell', disabled: !(hasSel && merged), onSelect: splitCell }, 'sep',
      { label: 'Cut', icon: 'edit-cut', disabled: !hasSel, onSelect: () => copySelection(name, false) },
      { label: 'Copy', icon: 'edit-copy', disabled: !hasSel, onSelect: () => copySelection(name, true) },
      { label: 'Paste', icon: 'edit-paste', disabled: !(hasSel && !!st.clip), onSelect: () => void pasteClipboard(name) },
      { label: 'Delete', icon: 'edit-delete', disabled: !hasSel, onSelect: () => deleteSelection(name) },
    ] })
  }
  /** The headers' menus (SheetTableView's constructor): Insert %n Rows Above / Below, Remove Rows; the columns' Left / Right. */
  const headerMenu = (kind: 'row' | 'col', i: number, x: number, y: number) => {
    const isSel = kind === 'row' ? view.ranges.some((r) => r.c1 === 0 && r.c2 === cols - 1 && i >= r.r1 && i <= r.r2) : view.ranges.some((r) => r.r1 === 0 && r.r2 === rows - 1 && i >= r.c1 && i <= r.c2)
    let ranges = view.ranges
    if (!isSel) { ranges = [kind === 'row' ? { r1: i, c1: 0, r2: i, c2: cols - 1 } : { r1: 0, c1: i, r2: rows - 1, c2: i }]; setView(name, { ranges, cur: kind === 'row' ? { row: i, col: 0 } : { row: 0, col: i } }) }
    const idx: number[] = []
    for (const r of ranges) for (let k = kind === 'row' ? r.r1 : r.c1; k <= (kind === 'row' ? r.r2 : r.c2); k++) if (!idx.includes(k)) idx.push(k)
    idx.sort((a, b) => b - a)
    const runs: [number, number][] = []
    for (const v of idx) { if (!runs.length || v < runs[runs.length - 1][0] - 1) runs.push([v, v]); else runs[runs.length - 1][0] = v }
    const n = idx.length
    const word = kind === 'row' ? 'Rows' : 'Columns'
    const at = (k: number) => (kind === 'row' ? String(k + 1) : colName(k))
    const ins = (after: boolean) => void applySs(name, runs.map(([b, e2]) => ({ op: kind === 'row' ? 'insertRows' : 'insertColumns', args: [at(after ? e2 + 1 : b), e2 - b + 1] })), `Insert ${word}`)
    const rem = () => void applySs(name, runs.map(([b, e2]) => ({ op: kind === 'row' ? 'removeRows' : 'removeColumns', args: [at(b), e2 - b + 1] })), `Remove ${word}`)
    const entries: Entry[] = runs.length <= 1
      ? [{ label: `Insert ${n} ${word} ${kind === 'row' ? 'Above' : 'Left'}`, onSelect: () => ins(false) }, { label: `Insert ${n} ${word} ${kind === 'row' ? 'Below' : 'Right'}`, onSelect: () => ins(true) }]
      : [{ label: `Insert ${n} Non-Contiguous ${word}`, onSelect: () => ins(false) }]
    setMenu({ x, y, entries: [...entries, { label: `Remove ${word}`, onSelect: rem }] })
  }
  // the visible part (QTableView draws what the viewport shows)
  const c0 = Math.max(0, bisect(sz.x, scroll.x) - 1), c1 = Math.min(cols - 1, bisect(sz.x, scroll.x + scroll.w) + 1)
  const r0 = Math.max(0, bisect(sz.y, scroll.y) - 1), r1 = Math.min(rows - 1, bisect(sz.y, scroll.y + scroll.h) + 1)
  const cells: ReactNode[] = []
  const drawn = new Set<string>()
  for (let r = r0; r <= r1; r++) {
    for (let c = c0; c <= c1; c++) {
      const a = anchorOfAddr(d, { row: r, col: c })
      const key = addrText(a)
      if (drawn.has(key)) continue
      drawn.add(key)
      const [rs, cs] = spansOf(d, a)
      const cell = d.cells[key]
      const v = cellView(cell)
      const selected = inRanges(view.ranges, a.row, a.col)
      const isCur = a.row === cur.row && a.col === cur.col
      const marked = clip && clip.sheet === name && inRanges(clip.ranges, a.row, a.col)
      const justify = v.align.includes('right') ? 'flex-end' : v.align.includes('hcenter') ? 'center' : 'flex-start'
      const valign = v.align.includes('top') ? 'flex-start' : v.align.includes('bottom') ? 'flex-end' : 'center'
      const style: React.CSSProperties = { left: HEADER_WIDTH + sz.x[a.col], top: HEAD_H + sz.y[a.row], width: sz.x[a.col + cs] - sz.x[a.col], height: sz.y[a.row + rs] - sz.y[a.row],
        justifyContent: justify, alignItems: valign, color: v.fg ?? undefined, background: v.bg ?? undefined,
        fontWeight: v.font.includes('bold') ? 700 : undefined, fontStyle: v.font.includes('italic') ? 'italic' : undefined, textDecoration: v.font.includes('underline') ? 'underline' : undefined }
      cells.push(
        <div key={key} className={cls('ss-cell', selected && 'sel', isCur && 'cur', marked && (clip!.copy ? 'copied' : 'cut'), (rs > 1 || cs > 1) && 'merged')} style={style}
          data-cell={key} data-tip={v.tooltip ?? undefined} title={v.tooltip ? v.tooltip.replace(/^<pre>|<\/pre>$/g, '') : undefined}>
          {edit && edit.addr.row === a.row && edit.addr.col === a.col
            ? <input className="ss-editor" autoFocus defaultValue={edit.text} onFocus={(ev) => { const t = ev.currentTarget; t.selectionStart = t.selectionEnd = t.value.length }}
                onKeyDown={(ev) => {
                  ev.stopPropagation()
                  if (ev.key === 'Escape') { setEdit(null); grid.current?.focus(); return }
                  if (ev.key === 'Enter' || ev.key === 'Tab') {
                    ev.preventDefault()
                    const text = ev.currentTarget.value
                    setEdit(null)
                    grid.current?.focus()
                    void commit(a, text)
                    move(ev.key, { shift: ev.shiftKey, ctrl: false })
                  }
                }}
                onBlur={(ev) => { if (edit) { const text = ev.currentTarget.value; setEdit(null); void commit(a, text) } }} />
            : <span className="ss-text">{v.display ?? ''}</span>}
        </div>)
    }
  }
  const colHeads: ReactNode[] = [], rowHeads: ReactNode[] = []
  const selCols = new Set<number>(), selRows = new Set<number>()
  for (const r of view.ranges) { for (let c = r.c1; c <= r.c2; c++) selCols.add(c); for (let k = r.r1; k <= r.r2; k++) selRows.add(k) }
  for (let c = c0; c <= c1; c++) colHeads.push(
    <div key={c} className={cls('ss-hcol', selCols.has(c) && 'sel')} style={{ left: HEADER_WIDTH + sz.x[c], width: sz.w[c], top: scroll.y }} data-col={colName(c)}
      onPointerDown={(ev) => { if (ev.button !== 0) return; setView(name, { ranges: [{ r1: 0, c1: c, r2: rows - 1, c2: c }], cur: { row: 0, col: c }, anchor: { row: 0, col: c } }) }}
      onContextMenu={(ev) => { ev.preventDefault(); headerMenu('col', c, ev.clientX, ev.clientY) }}>
      {headerColumn(c)}
      <span className="ss-resize-c" onPointerDown={(ev) => { ev.stopPropagation(); resize.current = { kind: 'col', i: c, start: ev.clientX, size: sz.w[c] }; (ev.target as Element).setPointerCapture(ev.pointerId) }}
        onPointerMove={(ev) => { const z = resize.current; if (z?.kind === 'col') setLive({ kind: 'col', i: z.i, size: Math.max(5, z.size + ev.clientX - z.start) }) }}
        onPointerUp={() => { const z = resize.current; resize.current = null; if (z && live) { void applySs(name, [{ op: 'setColumnWidth', args: [colName(z.i), live.size] }], 'Resize column') } setLive(null) }} />
    </div>)
  for (let r = r0; r <= r1; r++) rowHeads.push(
    <div key={r} className={cls('ss-hrow', selRows.has(r) && 'sel')} style={{ top: HEAD_H + sz.y[r], height: sz.h[r], left: scroll.x }} data-row={r + 1}
      onPointerDown={(ev) => { if (ev.button !== 0) return; setView(name, { ranges: [{ r1: r, c1: 0, r2: r, c2: cols - 1 }], cur: { row: r, col: 0 }, anchor: { row: r, col: 0 } }) }}
      onContextMenu={(ev) => { ev.preventDefault(); headerMenu('row', r, ev.clientX, ev.clientY) }}>
      {r + 1}
      <span className="ss-resize-r" onPointerDown={(ev) => { ev.stopPropagation(); resize.current = { kind: 'row', i: r, start: ev.clientY, size: sz.h[r] }; (ev.target as Element).setPointerCapture(ev.pointerId) }}
        onPointerMove={(ev) => { const z = resize.current; if (z?.kind === 'row') setLive({ kind: 'row', i: z.i, size: Math.max(5, z.size + ev.clientY - z.start) }) }}
        onPointerUp={() => { const z = resize.current; resize.current = null; if (z && live) { void applySs(name, [{ op: 'setRowHeight', args: [String(z.i + 1), live.size] }], 'Resize row') } setLive(null) }} />
    </div>)
  const aliasBad = aliasText && aliasText !== (curCell?.raw.alias ?? '') && !isValidAlias(d, aliasText)
  return (
    <div className="ss-view" data-sheet={name}>
      <div className="ss-lines">
        <label htmlFor={`ss-content-${name}`}>Content</label>
        <input id={`ss-content-${name}`} className="ss-content" data-name="cellContent" value={content} onChange={(ev) => setContent(ev.target.value)}
          onKeyDown={(ev) => { if (ev.key === 'Enter') { ev.preventDefault(); void commit(cur, content); grid.current?.focus() } if (ev.key === 'Escape') { setContent(curCell?.content ?? ''); grid.current?.focus() } }} />
        <label htmlFor={`ss-alias-${name}`}>Alias</label>
        <input id={`ss-alias-${name}`} className={cls('ss-alias', aliasBad && 'bad')} data-name="cellAlias" value={aliasText} onChange={(ev) => setAliasText(ev.target.value)}
          title={aliasBad ? 'Alias contains invalid characters!' : 'Refer to cell by alias, for example\nSpreadsheet.my_alias_name instead of Spreadsheet.B1'}
          onKeyDown={(ev) => { if (ev.key === 'Enter') { ev.preventDefault(); ev.currentTarget.blur() } }}
          onBlur={() => {
            // SheetView::confirmAliasChanged: setAlias when valid (else "Unable to set alias" in the Report view)
            const old = curCell?.raw.alias ?? ''
            if (aliasText === old) return
            if (aliasText && !isValidAlias(d, aliasText)) { report('err', `Unable to set alias: ${aliasText}`); return }
            void applySs(name, [{ op: 'setAlias', args: [addrText(cur), aliasText] }], 'Set alias')
            grid.current?.focus()
          }} />
      </div>
      <div ref={grid} className="ss-grid-scroll" tabIndex={0} onKeyDown={onKey}
        onScroll={(ev) => { const el = ev.currentTarget; setScroll({ x: el.scrollLeft, y: el.scrollTop, w: el.clientWidth, h: el.clientHeight }) }}
        onPointerDown={(ev) => {
          if ((ev.target as Element).closest('.ss-hcol, .ss-hrow, .ss-editor')) return
          const a = hit(ev.clientX, ev.clientY)
          if (!a) return
          if (ev.button === 2) { if (!inRanges(view.ranges, a.row, a.col)) select(a, 'set'); return }
          if (ev.button !== 0) return
          grid.current?.focus()
          const add = ev.ctrlKey || ev.metaKey
          select(a, ev.shiftKey ? 'extend' : add ? 'add' : 'set')
          drag.current = { from: a, add }
          ;(ev.currentTarget as Element).setPointerCapture(ev.pointerId)
        }}
        onPointerMove={(ev) => {
          const g = drag.current
          if (!g) return
          const a = hit(ev.clientX, ev.clientY)
          if (!a) return
          const r = { r1: Math.min(g.from.row, a.row), c1: Math.min(g.from.col, a.col), r2: Math.max(g.from.row, a.row), c2: Math.max(g.from.col, a.col) }
          setView(name, { ranges: [...viewOf(name).ranges.slice(0, -1), expandMerged(d, r)] })
        }}
        onPointerUp={() => { drag.current = null }}
        onDoubleClick={(ev) => { const a = hit(ev.clientX, ev.clientY); if (a) setEdit({ addr: a, text: d.cells[addrText(a)]?.content ?? '' }) }}
        onContextMenu={(ev) => { ev.preventDefault(); if (!(ev.target as Element).closest('.ss-hcol, .ss-hrow')) cellMenu(ev.clientX, ev.clientY) }}>
        <div className="ss-canvas" style={{ width: HEADER_WIDTH + sz.x[cols], height: HEAD_H + sz.y[rows] }}>
          {cells}
          <div className="ss-corner" style={{ left: scroll.x, top: scroll.y }} onPointerDown={() => setView(name, { ranges: [{ r1: 0, c1: 0, r2: rows - 1, c2: cols - 1 }] })} />
          {colHeads}
          {rowHeads}
        </div>
      </div>
      {menu && <ContextMenu at={{ x: menu.x, y: menu.y }} entries={menu.entries} onClose={() => setMenu(null)} />}
    </div>
  )
}
function bisect(acc: number[], v: number): number {
  let lo = 0, hi = acc.length - 1
  while (lo < hi) { const m = (lo + hi) >> 1; if (acc[m + 1] <= v) lo = m + 1; else hi = m }
  return lo
}
const anchorOfAddr = (d: SsSheet, a: Addr): Addr => { for (const [k, [rs, cs]] of Object.entries(d.merged)) { const p = parseAddr(k)!; if (a.row >= p.row && a.row < p.row + rs && a.col >= p.col && a.col < p.col + cs) return p } return a }
/** A selection that touches a merged cell takes all of it (QTableView's spans). */
function expandMerged(d: SsSheet, r: Rng): Rng {
  let out = { ...r }
  for (const [k, [rs, cs]] of Object.entries(d.merged)) {
    const p = parseAddr(k)!
    if (p.row <= out.r2 && p.row + rs - 1 >= out.r1 && p.col <= out.c2 && p.col + cs - 1 >= out.c1)
      out = { r1: Math.min(out.r1, p.row), c1: Math.min(out.c1, p.col), r2: Math.max(out.r2, p.row + rs - 1), c2: Math.max(out.c2, p.col + cs - 1) }
  }
  return out
}

// ── the tree (the document's objects: each Sheet, its icon) and the property view ───────────────────────────────
export function SpreadsheetRows({ iconSize = 16 }: { iconSize?: number }) {
  const names = useSs((s) => s.names), sheets = useSs((s) => s.sheets), sel = useSs((s) => s.sel)
  const [menu, setMenu] = useState<{ x: number; y: number; name: string } | null>(null)
  return <>
    {names.map((n) => (
      <div key={n} className={cls('trow', sel.includes(n) && 'sel')} data-ss={n}
        onClick={(ev) => { setSs((s) => ({ sel: ev.ctrlKey || ev.metaKey ? (s.sel.includes(n) ? s.sel.filter((x) => x !== n) : [...s.sel, n]) : [n] })); setState({ selected: [], featSel: [] }) }}
        onDoubleClick={() => openSheet(n)}
        onContextMenu={(ev) => { ev.preventDefault(); ev.stopPropagation(); setSs({ sel: [n] }); setMenu({ x: ev.clientX, y: ev.clientY, name: n }) }}>
        <span className="tlab"><span className="pdindent" style={{ width: 6 + 16 }} /><span className="tindent" />
          <span className="ticon"><Icon name="ss-Spreadsheet" size={iconSize} /></span>
          <span className="tname">{sheets[n]?.label ?? n}</span></span>
      </div>))}
    {menu && <ContextMenu at={menu} onClose={() => setMenu(null)} entries={[
      // ViewProviderSheet::setupContextMenu
      { label: 'Show Spreadsheet', bold: true, onSelect: () => openSheet(menu.name, false) }, 'sep',
      { label: 'Delete', icon: 'edit-delete', onSelect: () => void deleteSheet(menu.name) },
    ]} />}
  </>
}
async function deleteSheet(n: string) {
  const r = await messageBox('question', 'Delete', `Delete ${st.sheets[n]?.label ?? n}?`, ['Yes', 'No'])
  if (r === 'Yes') { await applySs(n, [{ op: 'delete' }], 'Delete'); setSs({ sel: [] }) }
}
/** Std_Delete on the tree's selected sheets. */
export async function deleteSelectedSheets(): Promise<boolean> {
  if (!st.sel.length) return false
  for (const n of [...st.sel]) await applySs(n, [{ op: 'delete' }], 'Delete')
  setSs({ sel: [] })
  return true
}
/** The selected sheet's property view (Data tab): Base's Label, as the real FreeCAD shows a Sheet (its cells are hidden
 *  properties). */
export function SpreadsheetProps() {
  const sel = useSs((s) => s.sel), sheets = useSs((s) => s.sheets)
  const n = sel[sel.length - 1]
  const d = n ? sheets[n] : undefined
  if (!d) return null
  return <Group title="Base">
    <EditRow k="Label" value={d.label} type="str" depth={1} onCommit={(v) => void applySs(n!, [{ op: 'label', to: String(v) }], `Rename ${n}.Label`)} />
  </Group>
}
export const ssPropActive = () => st.sel.length > 0

// ── a part's parameter bound to a cell (EXPRESSIONS: the property view's Expression Editor) ─────────────────────
/** The expression a part's PARAMS entry is bound to, if any. */
export const boundExpression = (part: string, param: string): string | undefined => st.parts[part]?.expressions?.[param]
/** The value the binding gives the parameter (the part's PARAMS as its EXPRESSIONS leave them). */
export const boundValue = (part: string, param: string): unknown => st.parts[part]?.bound?.[param]
export const useSsParts = () => useSs((s) => s.parts)
/** What expr.ts may read of the project's sheets: each sheet by Name and Label, its cells by address and alias. */
export function sheetObjects(): Record<string, Record<string, { kind: string; v?: number | string; dims?: number[]; s: string }>> {
  const out: Record<string, Record<string, { kind: string; v?: number | string; dims?: number[]; s: string }>> = {}
  for (const [n, d] of Object.entries(st.sheets)) {
    const props: Record<string, { kind: string; v?: number | string; dims?: number[]; s: string }> = {}
    for (const [a, c] of Object.entries(d.cells)) {
      if (!c.value) continue
      props[a] = c.value
      if (c.raw.alias) props[c.raw.alias] = c.value
    }
    out[n] = props
    if (d.label !== n && !out[d.label]) out[d.label] = props
  }
  return out
}
/** expr.ts's Env.resolve for the Expression Editor: `Spreadsheet.thick`, `<<Params>>.A1` (ObjectIdentifier: an identifier by
 *  Name, then Label; <<x>> by Label), the cell's computed value as the Python value it is; null when no sheet is named. */
export function sheetResolve(p: VarPath): { value: PyVal | Quantity; rest: string[] } | null {
  const objName = p.obj ? p.obj.name : p.names[0]
  const byLabel = !!p.obj?.str
  const d = (!byLabel && st.sheets[objName]) || Object.values(st.sheets).find((x) => x.label === objName)
  if (!d) return null
  const prop = p.obj ? p.names[0] : p.names[1]
  const rest = p.obj ? p.names.slice(1) : p.names.slice(2)
  const addr = Object.entries(d.cells).find(([, c]) => c.raw.alias === prop)?.[0] ?? prop.replace(/\$/g, '')
  const v = d.cells[addr]?.value
  if (!v) throw new PyError(`Property '${prop}' not found in '${objName}'`, 'RuntimeError')
  if (v.kind === 'int') return { value: { t: 'int', v: BigInt(Number(v.v)) }, rest }
  if (v.kind === 'float') return { value: { t: 'float', v: Number(v.v) }, rest }
  if (v.kind === 'quantity') return { value: { value: Number(v.v), dims: v.dims as Quantity['dims'] }, rest }
  if (v.kind === 'string') return { value: { t: 'str', v: String(v.v) }, rest }
  return { value: { t: 'obj', type: v.type ?? 'object', str: v.s }, rest }
}
/** Whether an expression names one of the project's sheets (so a PARAMS entry is bound to it, not set to its value). */
export function namesSheet(text: string): boolean {
  const names = Object.values(st.sheets).flatMap((d) => [d.name, d.label])
  return names.some((n) => new RegExp(`(^|[^A-Za-z0-9_])(${n.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}|<<${n.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}>>)\\s*\\.`).test(text))
}
/** FreeCAD's setExpression on a part's parameter: EXPRESSIONS written (or the entry removed). */
export async function bindParam(part: string, param: string, expression: string | null): Promise<boolean> {
  const sheet = st.names[0]
  if (!sheet) { report('err', 'The project has no spreadsheet'); return false }
  const ok = await applySs(sheet, [{ op: 'bind', part, param, expression }], 'Set expression')
  return ok
}

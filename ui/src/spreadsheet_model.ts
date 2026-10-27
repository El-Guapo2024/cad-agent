// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Spreadsheet/Gui/SheetModel.cpp: 2015 Eivind Kvedalen
//   src/Mod/Spreadsheet/Gui/SheetTableView.cpp: 2015 Eivind Kvedalen
//   src/Mod/Spreadsheet/App/PropertySheet.cpp: 2015 Eivind Kvedalen
//   src/Mod/Spreadsheet/App/Cell.cpp: 2015 Eivind Kvedalen
//   src/App/Range.cpp: 2015 Eivind Kvedalen
// What the Spreadsheet page shows of a sheet the server computed (cad_agent/spreadsheet_edit.py's sheet_json): cell
// addresses and ranges (App::CellAddress, App::Range: a range is walked column by column), what SheetModel::data gives
// for each role of a cell (display string, tooltip, colours, alignment, font), the selection's ranges and the keys that
// move the current cell (SheetTableView::selectedRanges, finishEditWithMove), the clipboard's text and cells
// (SheetTableView::_copySelection, PropertySheet::copyCells) and PropertySheet::isValidAlias.
import { userString, unitPrefs } from './quantity'
import { UNITS } from './units-data'

export type SsValue = { kind: 'int' | 'float' | 'quantity' | 'string' | 'object'; v?: number | string; dims?: number[]; s: string; type?: string }
export type SsRaw = { alignment: number; style: string[]; fg: number[] | null; bg: number[] | null; alias: string | null
  du: { text: string; dims: number[]; scaler: number } | null; dirty?: boolean }
export type SsCell = { content: string | null; value: SsValue | null; exception?: string; raw: SsRaw
  alignment?: string; style?: string; foreground_color?: string; background_color?: string; display_unit?: string; alias?: string
  row_span?: number; col_span?: number }
export type SsSheet = { name: string; label: string; type: string; cells: Record<string, SsCell>; merged: Record<string, [number, number]>
  column_widths: Record<string, number>; row_heights: Record<string, number>; errors: string[]; used_range: [string, string] | null }

export const MAX_ROWS = 16384
export const MAX_COLUMNS = 26 * 26 + 26
export const DEFAULT_WIDTH = 100   // PropertyColumnWidths::defaultWidth
export const DEFAULT_HEIGHT = 30   // PropertyRowHeights::defaultHeight
export const HEADER_WIDTH = 50     // PropertyColumnWidths::defaultHeaderWidth
/** SheetParameter's MaximumRowCount and MaximumColumnCount: what the view shows until the sheet holds more. */
export const VIEW_ROWS = 1024
export const VIEW_COLUMNS = 26

// ── CellAddress (App/Range.cpp) ─────────────────────────────────────────────────────────────────────────────────
export type Addr = { row: number; col: number }
/** CellAddress::toString's column: A..Z, then AA..ZZ. */
export const colName = (col: number) => (col < 26 ? String.fromCharCode(65 + col)
  : String.fromCharCode(65 + Math.floor((col - 26) / 26)) + String.fromCharCode(65 + ((col - 26) % 26)))
export const addrText = (a: Addr) => `${colName(a.col)}${a.row + 1}`
/** SheetModel's encodeColumn for the header (A..Z, AA..ZZ, AAA..). */
export function headerColumn(column: number): string {
  let skip = 0, next = 26, len = 1
  while (skip + next <= column) { skip += next; next *= 26; len++ }
  column -= skip
  let out = ''
  for (let i = 0; i < len; i++) { out = String.fromCharCode(65 + (column % 26)) + out; column = Math.floor(column / 26) }
  return out
}
/** stringToAddress (silent): "B3", "$B$3"; null when it is not a cell. */
export function parseAddr(s: string): Addr | null {
  const m = /^\$?([A-Z]{1,2})\$?([0-9]{1,5})$/.exec(s)
  if (!m) return null
  let col = 0
  for (const ch of m[1]) col = col * 26 + (ch.charCodeAt(0) - 64)
  const row = Number(m[2])
  if (row <= 0 || row > MAX_ROWS) return null
  return { row: row - 1, col: col - 1 }
}
export type Rng = { r1: number; c1: number; r2: number; c2: number }
export const rangeText = (r: Rng) => `${addrText({ row: r.r1, col: r.c1 })}:${addrText({ row: r.r2, col: r.c2 })}`
/** Range iteration (Range::next): down each column, then the next column. */
export function* cellsOf(r: Rng): Generator<Addr> {
  for (let c = r.c1; c <= r.c2; c++) for (let row = r.r1; row <= r.r2; row++) yield { row, col: c }
}
export const rangeSize = (r: Rng) => (r.r2 - r.r1 + 1) * (r.c2 - r.c1 + 1)

// ── the cell's look (Cell.cpp's alignment bits) ──────────────────────────────────────────────────────────────────
export const AL = { LEFT: 0x01, HCENTER: 0x02, RIGHT: 0x04, HIMPLIED: 0x08, HORIZONTAL: 0x0f, TOP: 0x10, VCENTER: 0x20, BOTTOM: 0x40, VIMPLIED: 0x80, VERTICAL: 0xf0 }
export const DEFAULT_ALIGNMENT = AL.HIMPLIED | AL.LEFT | AL.VIMPLIED | AL.VCENTER
/** Cell::encodeAlignment. */
export function encodeAlignment(a: number): string {
  let s = ''
  if (a & AL.LEFT) s += 'left'
  if (a & AL.HCENTER) s += 'center'
  if (a & AL.RIGHT) s += 'right'
  if (a & AL.HIMPLIED) s += '|himplied'
  if (a & AL.VERTICAL) s += '|'
  if (a & AL.TOP) s += 'top'
  if (a & AL.VCENTER) s += 'vcenter'
  if (a & AL.BOTTOM) s += 'bottom'
  if (a & AL.VIMPLIED) s += '|vimplied'
  return s
}

/** SheetParameter's colours as the FreeCAD Light preference pack sets them (Preferences > Spreadsheet). */
export const SS_PREFS = { aliasBg: '#bac8ff', textFg: '#212529', positiveFg: '#212529', negativeFg: '#212529', showAlias: false, aliasFormat: '%V = %A' }

export type CellView = { display: string | null; edit: string | null; tooltip: string | null; fg: string | null; bg: string | null
  align: string[]; font: string[]; error?: boolean; pending?: boolean }

/** QColor(255.0 * r, ...) of a Base::Color: each component's int conversion. */
const qcolor = (c: number[]) => '#' + c.slice(0, 3).map((x) => Math.trunc(255 * x).toString(16).padStart(2, '0')).join('') +
  (Math.trunc(255 * c[3]) === 255 ? '' : Math.trunc(255 * c[3]).toString(16).padStart(2, '0'))
/** QString::toHtmlEscaped. */
const htmlEscaped = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
/** QLocale().toString(v, 'f', decimals) in the C locale (FreeCAD's GUI runs with it): %.*f, no grouping. */
function fixed(v: number, decimals: number): string {
  if (Number.isNaN(v)) return 'nan'
  if (!Number.isFinite(v)) return v > 0 ? 'inf' : '-inf'
  return toFixedExact(v, decimals)
}
/** printf's %.*f of the double's exact value (ties to even), as Quantity::toNumber's Fixed does. */
function toFixedExact(v: number, decimals: number): string {
  // the exact decimal expansion of the double, then round half to even
  const neg = v < 0 || Object.is(v, -0)
  const view = new DataView(new ArrayBuffer(8))
  view.setFloat64(0, Math.abs(v))
  const hi = view.getUint32(0), lo = view.getUint32(4), e = (hi >>> 20) & 0x7ff
  let m = (BigInt(hi & 0xfffff) << 32n) | BigInt(lo), p = -1074
  if (e) { m |= 1n << 52n; p = e - 1075 }
  // value = m * 2^p = N / 10^k with k = max(0, -p)
  const k = p >= 0 ? 0 : -p
  const N = p >= 0 ? m << BigInt(p) : m * 5n ** BigInt(k)
  const scale = 10n ** BigInt(k)
  // round N / 10^k at `decimals`
  let q: bigint
  if (k <= decimals) q = N * 10n ** BigInt(decimals - k)
  else {
    const div = 10n ** BigInt(k - decimals)
    q = N / div
    const r = N % div, half = div / 2n
    if (r > half || (r === half && q % 2n === 1n)) q += 1n
  }
  void scale
  const t = q.toString().padStart(decimals + 1, '0')
  const body = decimals ? `${t.slice(0, -decimals)}.${t.slice(-decimals)}` : t
  return (neg ? '-' : '') + body
}

/** SheetModel::data for the roles the table draws. `c` is the cell (undefined when there is none). */
export function cellView(c: SsCell | undefined, prefs = SS_PREFS): CellView {
  const out: CellView = { display: null, edit: null, tooltip: null, fg: null, bg: null, align: [], font: [] }
  const raw: SsRaw = c?.raw ?? { alignment: DEFAULT_ALIGNMENT, style: [], fg: null, bg: null, alias: null, du: null }
  const s = c?.content ?? null
  out.edit = s
  if (!c?.exception && raw.alias) out.tooltip = raw.alias
  if (raw.bg) out.bg = qcolor(raw.bg)
  else if (raw.alias) out.bg = prefs.aliasBg
  out.font = raw.style.filter((x) => x === 'bold' || x === 'italic' || x === 'underline').sort()
  if (c?.exception) {
    out.tooltip = `<pre>${htmlEscaped(c.exception)}</pre>`
    out.display = s ?? '#ERR'
    out.fg = '#ff0000'
    out.align = ['left', 'vcenter']
    out.error = true
    return out
  }
  const a = raw.alignment
  const align: string[] = []
  for (const [bit, name] of [[AL.LEFT, 'left'], [AL.HCENTER, 'hcenter'], [AL.RIGHT, 'right'], [AL.TOP, 'top'], [AL.VCENTER, 'vcenter'], [AL.BOTTOM, 'bottom']] as const) if (a & bit) align.push(name)
  const implied = (h: string) => {
    let al = [...align]
    if (a & AL.HIMPLIED) al = [...al.filter((x) => !['left', 'hcenter', 'right'].includes(x)), h]
    if (a & AL.VIMPLIED) al = [...al.filter((x) => !['top', 'vcenter', 'bottom'].includes(x)), 'vcenter']
    return al
  }
  const fmt = (text: string) => {
    if (raw.alias && prefs.showAlias && (prefs.aliasFormat.includes('%V') || prefs.aliasFormat.includes('%A'))) return prefs.aliasFormat.replace('%A', raw.alias).replace('%V', text)
    return text
  }
  const v = c?.value ?? null
  if (!v || raw.dirty) {
    out.fg = '#0000ff'
    out.align = ['hcenter', 'vcenter']
    if (s !== null) out.display = s.startsWith('=') ? '#PENDING' : s
    out.pending = true
    return out
  }
  const fgSet = raw.fg ? qcolor(raw.fg) : null
  const decimals = unitPrefs.decimals
  if (v.kind === 'string') {
    out.fg = fgSet ?? prefs.textFg
    out.display = fmt(String(v.v))
    out.align = implied('left')
  } else if (v.kind === 'quantity') {
    const value = Number(v.v), dims = (v.dims ?? [0, 0, 0, 0, 0, 0, 0, 0]) as [number, number, number, number, number, number, number, number]
    out.fg = fgSet ?? (value < 0 ? prefs.negativeFg : prefs.positiveFg)
    out.align = implied('right')
    if (raw.du) {
      const one = dims.every((x) => x === 0), same = dims.every((x, i) => x === raw.du!.dims[i])
      out.display = fmt(one || same ? `${fixed(value / raw.du.scaler, decimals)} ${raw.du.text}` : '#ERR: unit')
    } else out.display = fmt(userString({ value, dims }).text)
  } else if (v.kind === 'int' || v.kind === 'float') {
    const d = Number(v.v)
    out.fg = fgSet ?? (d < 0 ? prefs.negativeFg : prefs.positiveFg)
    out.align = implied('right')
    if (raw.du) out.display = fmt(`${fixed(d / raw.du.scaler, decimals)} ${raw.du.text}`)
    else if (v.kind === 'float') out.display = fmt(fixed(d, decimals))
    else out.display = fmt(String(v.v))
  } else {
    out.fg = fgSet ?? prefs.textFg
    out.align = implied('hcenter')
    out.display = fmt(v.s)
  }
  return out
}

// ── the selection (SheetTableView::selectedRanges) and the keys (finishEditWithMove) ─────────────────────────────
/** The cell a merged cell's part belongs to (PropertySheet::getAnchor). */
export function anchorOf(sh: SsSheet, a: Addr): Addr {
  for (const [k, [rs, cs]] of Object.entries(sh.merged)) {
    const p = parseAddr(k)!
    if (a.row >= p.row && a.row < p.row + rs && a.col >= p.col && a.col < p.col + cs) return p
  }
  return a
}
export function spansOf(sh: SsSheet, a: Addr): [number, number] {
  const m = sh.merged[addrText(a)]
  return m ? [m[0], m[1]] : [1, 1]
}
export const isMerged = (sh: SsSheet, a: Addr) => { const p = anchorOf(sh, a); return p.row !== a.row || p.col !== a.col || !!sh.merged[addrText(a)] }
const used = (sh: SsSheet, a: Addr) => !!sh.cells[addrText(a)]

export type Mods = { shift: boolean; ctrl: boolean }
/** SheetTableView::finishEditWithMove: where Enter, Tab, the arrows, Home and End take the current cell. tab is the
 *  run of Tabs since the last Enter (tabCounter), returned updated. */
export function moveKey(sh: SsSheet, cur: Addr, key: string, mods: Mods, tab: number, rows = VIEW_ROWS, cols = VIEW_COLUMNS): { to: Addr; tab: number } {
  let r = cur.row, c = cur.col
  const [rowSpan, colSpan] = spansOf(sh, cur)
  const maxRow = rows - 1, maxCol = cols - 1
  const scan = (dr: number, dc: number) => {
    const start = { row: r, col: c }
    const startedEmpty = !used(sh, start)
    while (c + dc >= 0 && r + dr >= 0 && c + dc <= maxCol && r + dr <= maxRow) {
      r += dr; c += dc
      const empty = !used(sh, { row: r, col: c })
      if (empty && !startedEmpty) { r -= dr; c -= dc; break }
      else if (!empty && startedEmpty) break
    }
    if (r === start.row && c === start.col) { r += dr; c += dc }
    r = Math.max(0, Math.min(r, maxRow)); c = Math.max(0, Math.min(c, maxCol))
  }
  const plain = !mods.shift && !mods.ctrl
  switch (key) {
    case 'Enter':
      if (plain) { r += rowSpan; c -= tab } else if (mods.shift && !mods.ctrl) { r -= 1; c -= tab } else r += rowSpan
      tab = 0
      break
    case 'Home': r = 0; if (mods.ctrl && !mods.shift) c = 0; tab = 0; break
    case 'End': {
      for (const k of Object.keys(sh.cells)) {
        if (sh.cells[k].content === null || sh.cells[k].content === '') continue
        const a = parseAddr(k)!
        if (plain) { if (a.col === c) r = Math.max(r, a.row) } else if (mods.ctrl && !mods.shift) { r = Math.max(r, a.row); c = Math.max(c, a.col) }
      }
      tab = 0
      break
    }
    case 'ArrowLeft': if (c === 0) break; if (mods.ctrl) scan(0, -1); else c--; tab = 0; break
    case 'ArrowRight': if (c >= maxCol) break; if (mods.ctrl) scan(0, 1); else c += colSpan; tab = 0; break
    case 'ArrowUp': if (r === 0) break; if (mods.ctrl) scan(-1, 0); else r--; tab = 0; break
    case 'ArrowDown': if (r >= maxRow) break; if (mods.ctrl) scan(1, 0); else r += rowSpan; tab = 0; break
    case 'Tab': if (!mods.shift) { tab++; c += colSpan } else { tab = 0; c-- } break
  }
  const p = anchorOf(sh, { row: Math.max(0, Math.min(r, maxRow)), col: Math.max(0, Math.min(c, maxCol)) })
  return { to: { row: Math.max(0, Math.min(p.row, maxRow)), col: Math.max(0, Math.min(p.col, maxCol)) }, tab }
}

// ── the clipboard (SheetTableView::_copySelection, PropertySheet::copyCells) ────────────────────────────────────
export type Clip = { from: string; to: string; cells: Record<string, unknown>[] }[]
/** The text the clipboard gets (EditRole, a leading ' dropped, tabs between columns, newlines between rows) and the
 *  cells as copyCells writes them (the server's paste op takes them). */
export function copyOf(sh: SsSheet, ranges: Rng[]): { text: string; clip: Clip } {
  let minRow = Infinity, maxRow = 0, minCol = Infinity, maxCol = 0
  for (const r of ranges) { minRow = Math.min(minRow, r.r1); maxRow = Math.max(maxRow, r.r2); minCol = Math.min(minCol, r.c1); maxCol = Math.max(maxCol, r.c2) }
  let text = ''
  for (let i = minRow; i <= maxRow; i++) {
    for (let j = minCol; j <= maxCol; j++) {
      let cell = sh.cells[addrText({ row: i, col: j })]?.content ?? ''
      if (cell.startsWith("'")) cell = cell.slice(1)
      text += cell + (j < maxCol ? '\t' : '')
    }
    if (i < maxRow) text += '\n'
  }
  const KEYS = ['alignment', 'style', 'foreground_color', 'background_color', 'display_unit', 'alias', 'row_span', 'col_span'] as const
  const clip: Clip = ranges.map((r) => ({
    from: addrText({ row: r.r1, col: r.c1 }), to: addrText({ row: r.r2, col: r.c2 }),
    cells: [...cellsOf(r)].map(addrText).filter((a) => sh.cells[a]).map((a) => {
      const c = sh.cells[a]
      const d: Record<string, unknown> = { address: a }
      if (c.content !== null) d.content = c.content
      for (const k of KEYS) if (c[k] !== undefined) d[k] = c[k]
      return d
    }),
  }))
  return { text, clip }
}

// ── aliases (PropertySheet::isValidAlias, Sheet::isValidAlias) ───────────────────────────────────────────────────
const CONSTANTS = new Set(['pi', 'e', 'True', 'true', 'False', 'false', 'None'])
export const isUnitToken = (s: string) => Object.prototype.hasOwnProperty.call(UNITS, s) && s !== '"' && s !== "'"
export const isConstantToken = (s: string) => CONSTANTS.has(s)
export const isCellName = (s: string) => /^\$?[A-Z]{1,2}\$?[0-9]{1,5}$/.test(s) && parseAddr(s.replace(/\$/g, '')) !== null && Number(/[0-9]+$/.exec(s)![0]) <= MAX_ROWS
/** Sheet::isValidAlias: syntax, not an alias already (any cell's, the cell's own too: PropertySheet::isValidAlias), not a cell
 *  address, a unit or a constant, not one of the sheet's properties. */
export function isValidAlias(sh: SsSheet, s: string): boolean {
  if (!/^[A-Za-z][_A-Za-z0-9]*$/.test(s)) return false
  if (Object.values(sh.cells).some((c) => c.raw.alias === s)) return false
  if (isCellName(s) || isUnitToken(s) || isConstantToken(s)) return false
  return !['Label', 'Label2', 'ExpressionEngine', 'Visibility', 'cells', 'columnWidths', 'rowHeights'].includes(s)
}
/** PropertiesDialog::aliasChanged's status text and tooltip for an alias that is not valid. */
export function aliasProblem(sh: SsSheet, s: string): { status: string; tip: string } | null {
  if (!s || isValidAlias(sh, s)) return null
  if (isUnitToken(s)) return { status: 'Invalid: reserved unit token', tip: 'Alias conflicts with a reserved unit token used by expressions' }
  if (isConstantToken(s)) return { status: 'Invalid: reserved constant token', tip: 'Alias conflicts with a reserved constant token used by expressions' }
  if (Object.values(sh.cells).some((c) => c.raw.alias === s)) return { status: 'Invalid: alias already exists', tip: 'Alias already defined' }
  if (isCellName(s)) return { status: 'Invalid: alias matches cell address pattern', tip: 'Alias cannot look like a cell address such as A1 or C12' }
  if (/^[A-Za-z][_A-Za-z0-9]*$/.test(s)) return { status: 'Invalid: conflicts with existing property name', tip: 'Alias conflicts with an existing spreadsheet property name' }
  return { status: 'Invalid: bad alias syntax', tip: "Alias must start with a letter and contain only letters, digits, and '_'" }
}

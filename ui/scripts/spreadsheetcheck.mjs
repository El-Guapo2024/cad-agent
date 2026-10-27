// SPDX-License-Identifier: LGPL-2.1-or-later
// spreadsheetcheck: the Spreadsheet workbench in the page, held to the real FreeCAD's (ui/scripts/fcspreadsheet.json, written
// by fcspreadsheet.py from FreeCAD 26.3 at 3160daf1e2b6), driven on a scratch project as the recording drove FreeCAD.
//
//   NODE_PATH=<folder with playwright> node ui/scripts/spreadsheetcheck.mjs [--fc=ui/scripts/fcspreadsheet.json] [--only=SECTION,...] [--keep] [--verbose]
//
// Sections, in the recording's order (each one leaves the sheet as FreeCAD's dump left it, so the next compares alike):
//   menus      the menu bar puts Spreadsheet before Windows; the Spreadsheet menu with no sheet, with a sheet, with a range
//   toolbars   the Spreadsheet toolbar, button by button, with its two colour pickers
//   create     Spreadsheet_CreateSheet: the undo step, the window, the Content and Alias line edits, the headers and sizes
//   cells      each cell typed into the sheet (a key on the cell, Enter), display units and aliases set, then what every cell of
//              A1:C20 shows: text, tooltip, colours, alignment and font, against SheetModel::data's roles
//   lines      the Content and Alias line edits for a few current cells
//   menu       the cell's context menu for one cell, a range and a merged cell: entries and which are enabled
//   commands   each alignment and style command on a selection, merge and split: the undo step and the cells after
//   properties the Properties dialog: tabs and widgets, the alias checks, then the changes applied (Set cell properties)
//   alias      Spreadsheet_SetAlias (the dialog on its Alias tab), the Alias line edit, the Content line edit
//   clipboard  Copy, Paste, Paste over a larger range (tiled), Cut and Paste, Delete
//   headers    the row and column headers' menus, Insert Rows Above
//   keys       Enter, Tab, Shift+Tab, the arrows, Home and End: where the current cell goes
//   cycles     a second sheet whose cells read each other: what the cells show
//   undo       Std_Undo and Std_Redo
// A difference prints as FAIL; the deliberate ones (PARITY.md, "Spreadsheet workbench") as `known`. Exit 1 on a FAIL.
import { createRequire } from 'module'
import { spawn, spawnSync } from 'child_process'
import { mkdirSync, mkdtempSync, readFileSync, rmSync } from 'fs'
import { createServer } from 'net'
import { tmpdir } from 'os'
import { dirname, join, resolve } from 'path'
import { fileURLToPath } from 'url'
const require = createRequire(import.meta.url)
let chromium
try { ({ chromium } = require('playwright')) } catch { ({ chromium } = createRequire('/opt/node-tools/node_modules/')('playwright')) }

const HERE = dirname(fileURLToPath(import.meta.url))
const REPO = resolve(HERE, '..', '..')
const args = process.argv.slice(2)
const flag = (name, d) => { const a = args.find((x) => x.startsWith(`--${name}=`)); return a ? a.slice(name.length + 3) : d }
const FC = JSON.parse(readFileSync(flag('fc', join(HERE, 'fcspreadsheet.json')), 'utf8'))
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
let pass = 0, fail = 0, known = 0
const ok = (what) => { pass++; if (args.includes('--verbose')) console.log(`  ok    ${what}`) }
const bad = (what, detail = '') => { fail++; console.log(`  FAIL  ${what}${detail ? `: ${detail}` : ''}`) }
const note = (what) => { known++; console.log(`  known ${what}`) }
const check = (cond, what, detail) => (cond ? ok(what) : bad(what, detail))
const J = (x) => JSON.stringify(x)
const same = (a, b, what) => check(J(a) === J(b), what, `\n        FreeCAD ${J(b)}\n        ours    ${J(a)}`)
const ONLY = flag('only', '').split(',').filter(Boolean)
const want = (s) => !ONLY.length || ONLY.includes(s)
const clean = (t) => String(t ?? '').replace(/&(.)/g, '$1').replace(/…$/, '').trim()

// ── a scratch workbench ───────────────────────────────────────────────────────────────────────────────────────
const freePort = (from) => new Promise((res, rej) => {
  const tryPort = (p) => { if (p > from + 40) return rej(new Error('no free port')); const s = createServer(); s.once('error', () => tryPort(p + 1)); s.once('listening', () => s.close(() => res(p))); s.listen(p, '127.0.0.1') }
  tryPort(from)
})
const scratch = mkdtempSync(join(tmpdir(), 'cad-sscheck-')), warmDir = mkdtempSync(join(tmpdir(), 'cad-sscheck-warm-'))
const ROOT = join(scratch, 'root'); mkdirSync(ROOT)
for (const d of ['runtime', 'macros']) mkdirSync(join(scratch, d))
const python = process.env.CAD_PYTHON || join(REPO, '.venv', 'bin', 'python')
const env = { ...process.env, CAD_WARM_DIR: warmDir, CAD_RUNTIME_DIR: join(scratch, 'runtime'), CAD_MACRO_DIR: join(scratch, 'macros'),
  CAD_PREFS: join(scratch, 'prefs.json'), PYTHONPATH: REPO, CAD_PYTHON: python, CAD_RENDER_BACKEND: 'numpy' }
delete env.CAD_PROJECTS
const SLUG = 'Unnamed'
spawnSync(python, ['-m', 'cad_agent', '--projects', ROOT, 'init', SLUG, '--brief', 'spreadsheetcheck'], { env, cwd: REPO })
const port = await freePort(9051)
const server = spawn(python, ['-c', `import sys; from pathlib import Path; from cad_agent import serve; serve.run([Path(sys.argv[1])], host="127.0.0.1", port=${port})`, ROOT],
  { env, cwd: REPO, stdio: ['ignore', 'pipe', 'pipe'] })
await new Promise((res, rej) => {
  const t = setTimeout(() => rej(new Error('the scratch workbench did not start')), 60000)
  server.stdout.on('data', (d) => { if (/workbench: http/.test(String(d))) { clearTimeout(t); res() } })
  server.on('exit', (c) => rej(new Error(`the scratch workbench exited with ${c}`)))
})
const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] })
const ctx = await browser.newContext({ viewport: { width: 1400, height: 950 } })
await ctx.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: `http://127.0.0.1:${port}` })
const page = await ctx.newPage()
page.on('pageerror', (e) => bad('page error', e.message))
const st = (expr) => page.evaluate(expr)
const until = async (expr, what, ms = 60000) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { if (await st(expr)) return true; await sleep(200) } bad(`timed out waiting: ${what}`); return false }
const runCmd = (c) => st(`cadui.getCommand(${J(c)})?.run([])`)
const ss = () => st('cadui.ss.state()')
const sheet = async (n = 'Spreadsheet') => (await ss()).sheets[n]
const undoHead = () => st('cadui.getState().undo[0]?.name ?? null')
const undoCount = () => st('cadui.getState().undo[0]?.id ?? null')   // the journal keeps 20 steps (MaxUndoSize): its head says a step was added
/** Wait for the server's answer to the last edit: the journal grows (or the condition holds). */
const settle = async (before) => {
  if (before !== undefined && !(await until(`(cadui.getState().undo[0]?.id ?? null) !== ${J(before)}`, "the undo step", 30000)))
    console.log("        the Report view:", J(await st(`cadui.getState().messages.slice(-3).map((e) => e.text)`)))
  await sleep(400)
}
const cell = (a) => page.locator(`.ss-cell[data-cell="${a}"]`)
/** The table draws only what its viewport shows: scrolled there first. */
const scrollGrid = async (x, y) => { await st(`(() => { const g = document.querySelector('.ss-view[data-sheet="Spreadsheet"] .ss-grid-scroll'); g.scrollLeft = ${x}; g.scrollTop = ${y} })()`); await sleep(300) }
const rc = (a) => { const m = /^([A-Z]+)(\d+)$/.exec(a); let c = 0; for (const ch of m[1]) c = c * 26 + ch.charCodeAt(0) - 64; return [Number(m[2]) - 1, c - 1] }
const colName = (c) => (c < 26 ? String.fromCharCode(65 + c) : String.fromCharCode(65 + Math.floor((c - 26) / 26)) + String.fromCharCode(65 + ((c - 26) % 26)))
/** Select ranges (the selection model, as the dump's select()), the current cell the first range's top left. */
async function select(...ranges) {
  const rs = ranges.map((r) => { const [a, b = a] = r.split(':'); const [r1, c1] = rc(a), [r2, c2] = rc(b); return { r1, c1, r2, c2 } })
  await st(`cadui.ss.set((s) => ({ views: { ...s.views, Spreadsheet: { ...(s.views.Spreadsheet ?? {}), ranges: ${J(rs)}, cur: { row: ${rs[0].r1}, col: ${rs[0].c1} }, anchor: { row: ${rs[0].r1}, col: ${rs[0].c1} }, tab: 0 } } }))`)
  await sleep(120)
}
const apply = async (ops, name) => { const n = await undoCount(); await st(`cadui.ss.apply('Spreadsheet', ${J(ops)}${name ? `, ${J(name)}` : ''})`); await settle(n) }
/** A cell typed as a person types it: the cell clicked, the text keyed in, Enter (SheetModel::setData then a recompute). */
async function typeCell(a, text) {
  const n = await undoCount()
  await select(a)
  await page.locator('.ss-grid-scroll').focus()
  const [r, c] = rc(a)
  await st(`(() => { const el = document.querySelector('.ss-grid-scroll'); const d = cadui.ss.state().sheets.Spreadsheet; void d; })()`)
  await page.keyboard.type(text.slice(0, 1))
  await page.locator('.ss-editor').fill(text)
  await page.locator('.ss-editor').press('Enter')
  void r; void c
  await settle(n)
}
/** What the page draws for a cell, in SheetModel::data's terms. */
const viewOf = (a) => st(`(() => { const d = cadui.ss.state().sheets.Spreadsheet; return d ? null : null })()`).then(async () =>
  page.evaluate((addr) => {
    const el = document.querySelector(`.ss-cell[data-cell="${addr}"]`)
    if (!el) return null
    const cs = el.style
    const hex = (c) => { if (!c) return null; const m = /rgba?\((\d+), (\d+), (\d+)(?:, ([\d.]+))?\)/.exec(c); if (!m) return c; const h = [m[1], m[2], m[3]].map((x) => Number(x).toString(16).padStart(2, '0')).join(''); return '#' + h + (m[4] !== undefined && Number(m[4]) !== 1 ? Math.round(Number(m[4]) * 255).toString(16).padStart(2, '0') : '') }
    const align = [cs.justifyContent === 'flex-end' ? 'right' : cs.justifyContent === 'center' ? 'hcenter' : 'left', cs.alignItems === 'flex-start' ? 'top' : cs.alignItems === 'flex-end' ? 'bottom' : 'vcenter']
    const font = [cs.fontWeight === '700' && 'bold', cs.fontStyle === 'italic' && 'italic', cs.textDecoration.includes('underline') && 'underline'].filter(Boolean)
    const text = el.querySelector('.ss-text')?.textContent ?? ''
    return { display: text, tooltip: el.getAttribute('data-tip'), fg: hex(cs.color) || null, bg: hex(cs.background || cs.backgroundColor) || null, align, font }
  }, a))
/** FreeCAD's roles of a cell, as the page can draw them: an empty display is '', a missing colour or alignment is the cell's default. */
function fcView(v) {
  const align = v.align?.length ? [v.align.find((x) => ['left', 'hcenter', 'right'].includes(x)) ?? 'left', v.align.find((x) => ['top', 'vcenter', 'bottom'].includes(x)) ?? 'vcenter'] : ['left', 'vcenter']
  return { display: v.display ?? '', tooltip: v.tooltip ?? null, fg: v.fg, bg: v.bg, align, font: [...(v.font ?? [])].sort() }
}
const cellState = async (a) => {
  const d = await sheet()
  const c = d?.cells[a]
  if (!c) return { content: '' }
  const out = { content: c.content ?? '' }
  if (c.raw.alias) out.alias = c.raw.alias
  if (c.raw.style.length) out.style = [...c.raw.style].sort()
  if (c.alignment) out.alignment = alignSet(c.raw.alignment)
  if (c.raw.fg) out.foreground = c.raw.fg.map((x) => Math.round(x * 1e4) / 1e4)
  if (c.raw.bg) out.background = c.raw.bg.map((x) => Math.round(x * 1e4) / 1e4)
  if (c.raw.du) out.display_unit = c.raw.du.text
  return out
}
/** SheetPy::getAlignment's set. */
const alignSet = (a) => [[1, 'left'], [2, 'center'], [4, 'right'], [0x10, 'top'], [0x20, 'vcenter'], [0x40, 'bottom']].filter(([b]) => a & b).map(([, n]) => n).sort()

function compareMenu(fc, ours, what) {
  const f = fc.filter((e) => !e.sep), o = ours.filter((e) => !e.sep)
  same(o.map((e) => clean(e.text)), f.map((e) => clean(e.text)), `${what}: the entries`)
  for (const e of f) {
    const m = o.find((x) => clean(x.text) === clean(e.text))
    if (!m) continue
    if (e.menu && m.menu) { compareMenu(e.menu, m.menu, `${what} > ${clean(e.text)}`); continue }
    if (m.enabled === e.enabled) ok(`${what}: ${clean(e.text)}`)
    else if (!e.menu && clean(e.text) === 'New Spreadsheet' && !e.enabled) note(`${what}: New Spreadsheet is active here with no document open: the project is the document`)
    else if (['Import Spreadsheet'].includes(clean(e.text)) && !e.enabled) note(`${what}: ${clean(e.text)} is active here with no document open: the project is the document`)
    else bad(`${what}: ${clean(e.text)} ${e.enabled ? 'active' : 'greyed'}`, `ours ${m.enabled ? 'active' : 'greyed'}`)
  }
}
const fcMenu = (m) => m['&Spreadsheet']
async function menus(what, fc) {
  const bar = await st(`[...document.querySelectorAll('.menubar > *')].map((e) => e.textContent.trim()).filter(Boolean)`)
  const i = bar.indexOf('Spreadsheet'), w = bar.indexOf('Windows')
  check(i >= 0 && w === i + 1, `${what}: Spreadsheet sits before Windows in the menu bar`, J(bar))
  compareMenu(fcMenu(fc), (await st('cadui.spreadsheet()')).menu, `${what}: Spreadsheet menu`)
}
async function toolbar(what, fc) {
  const ours = (await st('cadui.spreadsheet()')).toolbar
  const fcb = fc[0].buttons
  same(ours.filter((b) => !b.sep).map((b) => b.cmd), fcb.filter((b) => !b.sep && b.widget !== 'QtColorPicker').map((b) => b.name), `${what}: the toolbar's commands`)
  for (const b of fcb.filter((x) => !x.sep && x.widget !== 'QtColorPicker')) {
    const o = ours.find((x) => x.cmd === b.name)
    if (!o) continue
    if (o.enabled === b.enabled) ok(`${what}: ${b.name}`)
    else if (!b.enabled && ['Spreadsheet_CreateSheet', 'Spreadsheet_Import'].includes(b.name)) note(`${what}: ${b.name} active with no document open (the project is the document)`)
    else bad(`${what}: ${b.name} ${b.enabled ? 'active' : 'greyed'}`, `ours ${o.enabled ? 'active' : 'greyed'}`)
  }
  const pickers = await st(`[...document.querySelectorAll('.ss-color')].map((b) => [b.dataset.cmd, b.title])`)
  same(pickers, fcb.filter((x) => x.widget === 'QtColorPicker').map((x) => [x.name, x.tip]), `${what}: the two colour pickers`)
}

try {
  await page.goto(`http://127.0.0.1:${port}/next/#${SLUG}`)
  await until('cadui.getState().slug === "Unnamed"', 'the project open')
  await sleep(2500)
  await st(`cadui.setState({ workbench: 'spreadsheet' })`)
  await sleep(500)
  if (want('menus')) { console.log('menus'); await menus('no sheet', FC.menus_none) }
  if (want('toolbars')) { console.log('toolbars'); await toolbar('no sheet', FC.toolbars_none) }

  // ── Spreadsheet_CreateSheet ──
  console.log('create')
  {
    const n = await undoCount()
    await runCmd('Spreadsheet_CreateSheet')
    await settle(n)
    await until(`!!document.querySelector('.ss-view[data-sheet="Spreadsheet"]')`, 'the sheet view')
    same([await undoHead()], FC.create.undo, 'the undo step')
    same((await ss()).names, FC.create.objects.map((o) => o[0]), 'the objects made')
    const tab = await st(`[...document.querySelectorAll('.dv-tab')].map((t) => t.textContent.trim()).find((x) => x.startsWith('Spreadsheet'))`)
    same(tab, FC.create.active.replace('[*]', ''), "the sheet window's title")
    same(await st(`[...document.querySelectorAll('.ss-lines label')].map((l) => l.textContent)`), FC.create.labels.map(clean), 'the line edits\' labels')
    same(await st(`document.querySelector('.ss-alias').title`), FC.create.alias_tip, "the Alias line edit's tooltip")
    const size = await st(`(() => { const c = document.querySelector('.ss-cell[data-cell="A1"]'); return [c.offsetWidth, c.offsetHeight] })()`)
    same(size, [FC.create.col_width, FC.create.row_height], 'a cell\'s default width and height')
    same(await st(`[document.querySelector('[data-col="A"]').textContent, document.querySelector('[data-row="1"]').textContent]`), [FC.create.header_h[0], FC.create.header_v[0]], 'the headers')
    if (FC.create.content_enabled === false) note('the Content line edit is enabled at once here; FreeCAD enables it when a cell is first made current')
    if (want('menus')) await menus('a sheet', FC.menus_sheet)
    if (want('toolbars')) await toolbar('a sheet', FC.toolbars_sheet)
  }

  // ── the cells ──
  const CELLS = { A1: '5', A2: '-3', A3: '2.5', A4: '-2.5', A5: '1/3', A6: '12345.678', A7: '1e-7', A8: '1e20', A9: '12,5', A10: '0.005', A11: '-0.004',
    A12: '=1/0', A13: '=nothing', A14: '=foo(', A15: "'text", A16: 'hello', A17: '=True', A18: '=None', A19: '=list(1;2)', A20: '=vector(1;2;3)',
    B1: '3 mm', B2: '1 m', B3: '=1 m * 1 m', B4: '=2 kg', B5: '=90 deg', B6: '=1 s', B7: '-3 mm', B8: '=1 mm / 1 s', B9: '=12 in', B10: '=0.5 mm',
    B11: '=1e-4 mm', B12: '=5 N', B13: '=3 mm', B14: '=4 mm', B15: '=5', B16: '=7 mm', B17: '=1.5', B18: '=2', B19: '=1 mm^3', B20: '=sqrt(2)',
    C1: '=A1 * 2', C2: '=B1 + B2', C3: '=sum(A1:A3)', C4: '=average(B1:B2)', C8: '=min(A1:A3)', C9: '=max(B1:B2)', C10: '=count(A1:A6)',
    C11: '=stddev(A1:A3)', C12: '=A15 + 1', C13: '=<<x>>', C14: '=str(B1)', C15: '=B1 > 2 mm', C16: '=A1 / 2' }
  if (want('cells') || want('lines')) {
    console.log('cells')
    // typed through the page in the first column, the rest set as ops (each cell a typing would make the same op)
    for (const [a, t] of Object.entries(CELLS)) {
      if (a === 'A1' || a === 'B1' || a === 'C1') await typeCell(a, t)
      else await apply([{ op: 'set', args: [a, t] }], 'Edit cell')
    }
    same(await undoHead(), FC.cells.undo[0], 'a typed cell is one undo step "Edit cell"')
    await apply([['B13', 'cm'], ['B14', 'in'], ['B15', 'mm'], ['B16', 's'], ['B17', 'deg'], ['B18', 'mm']].map(([a, u]) => ({ op: 'setDisplayUnit', args: [a, u] })))
    await apply([['B1', 'thick'], ['A3', 'ratio']].map(([a, al]) => ({ op: 'setAlias', args: [a, al] })))
    await sleep(500)
    for (const [a, want_] of Object.entries(FC.cells.view)) {
      const f = fcView(want_)
      const o = await viewOf(a)
      if (!o) { bad(`cell ${a}`, 'not drawn'); continue }
      if (f.display === '' && !CELLS[a]) { f.fg = o.fg; f.align = o.align }   // an empty cell: nothing is drawn of its roles
      same(o, f, `cell ${a} (${CELLS[a] ?? 'empty'})`)
    }
  }
  if (want('lines')) {
    console.log('lines')
    for (const [a, v] of Object.entries(FC.lines)) {
      await select(a)
      await sleep(150)
      same(await st(`[document.querySelector('.ss-content').value, document.querySelector('.ss-alias').value]`), [v.content, v.alias], `the line edits on ${a}`)
    }
  }
  // ── the cell's context menu ──
  if (want('menu')) {
    console.log('menu')
    const menuOf = async () => {
      await cell(await st(`(() => { const v = cadui.ss.state().views.Spreadsheet; const c = v.cur; return String.fromCharCode(65 + c.col) + (c.row + 1) })()`)).click({ button: 'right' })
      await sleep(200)
      const items = await st(`[...document.querySelectorAll('.ctx .mb-item, .ctx .mb-sep, .ctx > *')].map((e) => e.classList.contains('mb-sep') || e.tagName === 'HR' ? { sep: true } : { text: e.textContent.replace(/[⌘⌃⇧⌫].*$/, '').trim(), enabled: !e.hasAttribute('data-disabled') })`)
      await page.keyboard.press('Escape')
      return items
    }
    for (const [key, sel] of [['one', ['E1']], ['range', ['E1:F2']], ['merged', null]]) {
      if (!sel) { await apply([{ op: 'mergeCells', args: ['H1:I2'] }], 'Merge cells'); await select('H1') } else await select(...sel)
      const ours = (await menuOf()).filter((e) => !e.sep && e.text)
      const fc = FC.context_menu[key].actions.filter((e) => !e.sep)
      same(ours.map((e) => clean(e.text)), fc.map((e) => clean(e.text)), `${key}: the context menu's entries`)
      for (const e of fc) {
        const m = ours.find((x) => clean(x.text) === clean(e.text))
        if (!m) continue
        if (m.enabled === e.enabled) ok(`${key}: ${clean(e.text)}`)
        else if (['Bind…', 'Bind', 'Configuration Table'].includes(clean(e.text))) note(`${key}: ${clean(e.text)} is not ported (greyed; FreeCAD's is ${e.enabled ? 'active' : 'greyed'})`)
        else if (clean(e.text) === 'Paste' && m.enabled !== e.enabled) note(`${key}: Paste follows this page's own clipboard (FreeCAD's follows the system clipboard's text)`)
        else bad(`${key}: ${clean(e.text)} ${e.enabled ? 'active' : 'greyed'}`, `ours ${m.enabled ? 'active' : 'greyed'}`)
      }
    }
    await apply([{ op: 'splitCell', args: ['H1'] }], 'Split cell')
  }
  // ── the commands on a selection ──
  if (want('commands')) {
    console.log('commands')
    const CMDS = ['Spreadsheet_AlignLeft', 'Spreadsheet_AlignCenter', 'Spreadsheet_AlignRight', 'Spreadsheet_AlignTop', 'Spreadsheet_AlignVCenter', 'Spreadsheet_AlignBottom',
      'Spreadsheet_StyleBold', 'Spreadsheet_StyleItalic', 'Spreadsheet_StyleUnderline']
    for (const [i, cmd] of CMDS.entries()) {
      await apply([{ op: 'set', args: [`E${i + 3}`, `'${cmd.slice(12)}`] }], 'Edit cell')
      await select(`E${i + 3}:F${i + 3}`)
      const n = await undoCount()
      await runCmd(cmd)
      await settle(n)
      const f = FC.commands[cmd]
      same([await undoHead()], f.undo, `${cmd}: the undo step`)
      for (const [a, c] of Object.entries(f.cells)) same(await cellState(a), c, `${cmd}: ${a} after`)
    }
    await select('E9:F9')
    { const n = await undoCount(); await runCmd('Spreadsheet_StyleBold'); await settle(n) }
    same([await undoHead()], FC.commands.bold_again.undo, 'Bold again: the undo step')
    same(await cellState('E9'), FC.commands.bold_again.cell, 'Bold again takes bold off')
    await apply([{ op: 'set', args: ['E12', "'m"] }]); await apply([{ op: 'set', args: ['F13', "'gone"] }])
    await select('E12:F13')
    if (want('menus')) await menus('a range', FC.menus_range)
    { const n = await undoCount(); await runCmd('Spreadsheet_MergeCells'); await settle(n) }
    same([await undoHead()], FC.commands.Spreadsheet_MergeCells.undo, 'Merge Cells: the undo step')
    same((await sheet()).merged, FC.commands.Spreadsheet_MergeCells.spans, 'Merge Cells: the spans')
    same(await cellState('F13'), { content: '' }, 'Merge Cells clears the hidden cells')
    await select('E12')
    { const n = await undoCount(); await runCmd('Spreadsheet_SplitCell'); await settle(n) }
    same([await undoHead()], FC.commands.Spreadsheet_SplitCell.undo, 'Split Cell: the undo step')
    same((await sheet()).merged, FC.commands.Spreadsheet_SplitCell.spans, 'Split Cell: no spans')
  }
  // ── the Properties dialog ──
  if (want('properties')) {
    console.log('properties')
    await apply([{ op: 'set', args: ['G1', '=2 mm'] }], 'Edit cell')
    await select('G1')
    await cell('G1').click({ button: 'right' })
    await page.locator('.ctx >> text=Properties').first().click()
    await until(`!!document.querySelector('[data-dialog="PropertiesDialog"]')`, 'the dialog')
    const P = FC.properties
    same(await st(`document.querySelector('.ss-dtitle').textContent`), P.title, "the dialog's title")
    same(await st(`[...document.querySelectorAll('.ss-tab')].map((t) => t.textContent)`), P.widgets.find((w) => w.class === 'QTabWidget').tabs.map(clean), 'the tabs')
    const tabs = ['Color', 'Alignment', 'Style', 'Display unit', 'Alias']
    for (const [i, t] of tabs.entries()) {
      await page.locator('.ss-tab').nth(i).click()
      await sleep(100)
      const fcW = P.pages[`&${t}`] ?? P.pages[Object.keys(P.pages)[i]]
      const fcTexts = fcW.filter((w) => ['QLabel', 'QRadioButton', 'QCheckBox', 'QtColorPicker'].includes(w.class) && w.text).map((w) => clean(w.text))
      const ours = await st(`[...document.querySelectorAll('.ss-tabpage label, .ss-tabpage .ss-colortext')].map((e) => e.textContent.trim()).filter(Boolean)`)
      same(ours, fcTexts.filter((x) => !(t === 'Alias' && x === '')), `the ${t} tab's texts`)
      const checks = fcW.filter((w) => w.checked !== undefined && (w.class === 'QRadioButton' || w.class === 'QCheckBox')).map((w) => [w.name, w.checked])
      if (checks.length) same(await st(`[...document.querySelectorAll('.ss-tabpage input[data-name]')].filter((e) => e.type !== 'text').map((e) => [e.dataset.name, e.checked])`), checks, `the ${t} tab's buttons`)
    }
    await page.locator('.ss-tab').nth(1).click()
    await page.locator('input[data-name="alignRight"]').check()
    await page.locator('input[data-name="alignTop"]').check()
    await page.locator('.ss-tab').nth(2).click()
    await page.locator('input[data-name="styleBold"]').check()
    await page.locator('.ss-tab').nth(3).click()
    await page.locator('input[data-name="displayUnit"]').fill('cm')
    await page.locator('.ss-tab').nth(4).click()
    for (const [text, want_] of Object.entries(P.alias_checks)) {
      await page.locator('input[data-name="alias"]').fill(text)
      await sleep(60)
      const o = await st(`({ status: document.querySelector('[data-name="aliasStatus"]')?.textContent ?? '', tip: document.querySelector('input[data-name="alias"]').title, ok: !document.querySelector('.ss-buttons button').disabled })`)
      same(o, { status: want_.status, tip: want_.tip, ok: want_.ok }, `the alias "${text}"`)
    }
    const n = await undoCount()
    await page.locator('.ss-buttons button', { hasText: 'OK' }).click()
    await settle(n)
    same([await undoHead()], P.undo, 'OK: the undo step')
    same(await cellState('G1'), P.cell, 'OK: the cell after')
    const f = fcView(P.view)
    same(await viewOf('G1'), f, 'OK: what the cell shows')
    // a range: the Alias tab is greyed
    await select('G3:G4')
    await cell('G3').click({ button: 'right' })
    await page.locator('.ctx >> text=Properties').first().click()
    await sleep(200)
    same(await st(`[...document.querySelectorAll('.ss-tab')].map((t) => !t.disabled)`), FC.properties_range.widgets.find((w) => w.class === 'QTabWidget').tab_enabled.map((x, i) => (i === 4 ? false : x)), 'a range: the tabs enabled')
    if (FC.properties_range.widgets.find((w) => w.class === 'QTabWidget').tab_enabled[4]) note('a range: FreeCAD keeps the Alias tab clickable and greys its page; ours greys the tab')
    await page.locator('.ss-buttons button', { hasText: 'Cancel' }).click()
  }
  // ── Set Alias, the Alias and Content line edits ──
  if (want('alias')) {
    console.log('alias')
    await apply([{ op: 'set', args: ['G6', '4'] }], 'Edit cell')
    await select('G6')
    await runCmd('Spreadsheet_SetAlias')
    await until(`!!document.querySelector('[data-dialog="PropertiesDialog"]')`, 'the dialog')
    same(await st(`[...document.querySelectorAll('.ss-tab')].findIndex((t) => t.classList.contains('sel'))`), FC.set_alias.widgets.find((w) => w.class === 'QTabWidget').current, 'Set Alias opens the Alias tab')
    await page.locator('input[data-name="alias"]').fill('four')
    { const n = await undoCount(); await page.locator('.ss-buttons button', { hasText: 'OK' }).click(); await settle(n) }
    same([await undoHead()], FC.set_alias.undo, 'Set Alias: the undo step')
    same(await cellState('G6'), FC.set_alias.cell, 'Set Alias: the cell')
    await apply([{ op: 'set', args: ['G8', '8'] }], 'Edit cell')
    await select('G8')
    const le = page.locator('.ss-alias')
    for (const text of ['bad alias', 'eight']) {
      await le.fill(text)
      await sleep(60)
      const tip = await le.getAttribute('title')
      same({ tip, red: await le.evaluate((e) => e.classList.contains('bad')) }, { tip: FC.alias_line[text].tip, red: !!FC.alias_line[text].style }, `the Alias line edit with "${text}"`)
    }
    { const n = await undoCount(); await le.press('Enter'); await settle(n) }
    same(await cellState('G8'), FC.alias_line.cell, 'the Alias line edit sets the alias')
    if (!FC.alias_line.undo.length) note('the Alias line edit: ours is the undo step "Set alias"; FreeCAD\'s confirmAliasChanged opens no transaction')
    await select('G10')
    const ce = page.locator('.ss-content')
    await ce.fill('=eight * 2')
    { const n = await undoCount(); await ce.press('Enter'); await settle(n) }
    same([await undoHead()], FC.content_line.undo, 'the Content line edit: the undo step')
    same(await cellState('G10'), FC.content_line.cell, 'the Content line edit: the cell')
    same(await viewOf('G10'), fcView(FC.content_line.view), 'the Content line edit: what the cell shows')
  }
  // ── Copy, Paste, Cut, Delete ──
  if (want('clipboard')) {
    console.log('clipboard')
    const C = FC.copy_paste
    for (const [a, t] of [['J1', '1'], ['J2', '=J1 + 1'], ['K1', '=$J$1 * 2'], ['K2', '=sum(J1:J2)']]) await apply([{ op: 'set', args: [a, t] }], 'Edit cell')
    await apply([{ op: 'setStyle', args: ['J1', 'bold'] }])
    await select('J1:K2')
    await page.locator('.ss-grid-scroll').focus()
    await page.keyboard.press('Control+c')
    await sleep(300)
    same(await st('cadui.ss.state().clip?.text'), C.text, "Copy: the clipboard's text")
    const used = async (cols, minRow = 0) => { const d = await sheet(); const out = {}; for (const a of Object.keys(d.cells)) { if (cols.includes(a[0]) && Number(a.slice(1)) >= minRow) out[a] = await cellState(a) } return out }
    const sorted = (o) => Object.fromEntries(Object.entries(o).sort(([a], [b]) => (a < b ? -1 : 1)))
    await select('L5')
    { const n = await undoCount(); await page.keyboard.press('Control+v'); await settle(n) }
    same([await undoHead()], C.undo, 'Paste: the undo step')
    same(sorted(await used('JKLM')), sorted(C.used), 'Paste: the cells (references moved, $ kept)')
    await select('L10:O13')
    { const n = await undoCount(); await page.keyboard.press('Control+v'); await settle(n) }
    same(sorted(await used('LMNO', 10)), sorted(C.tiled), 'Paste over a larger range: tiled')
    await select('J1:J2')
    await page.keyboard.press('Control+x')
    await sleep(200)
    await select('Q1')
    { const n = await undoCount(); await page.keyboard.press('Control+v'); await settle(n) }
    same([await undoHead()], C.cut_undo, 'Cut and Paste: the undo step')
    same(sorted(await used('JKQ')), sorted(C.after_cut), 'Cut and Paste: the cells')
    await select('Q1:Q2')
    { const n = await undoCount(); await page.keyboard.press('Delete'); await settle(n) }
    same([await undoHead()], C.delete_undo, 'Delete: the undo step')
    same(sorted(await used('Q')), sorted(C.after_delete), 'Delete: the cells')
  }
  // ── the headers ──
  if (want('headers')) {
    console.log('headers')
    const H = FC.headers
    for (const [orient, n] of [['rows', 1], ['rows', 2], ['columns', 1], ['columns', 2]]) {
      if (orient === 'rows') await st(`cadui.ss.set((s) => ({ views: { ...s.views, Spreadsheet: { ...s.views.Spreadsheet, ranges: [{ r1: 14, c1: 0, r2: ${13 + n}, c2: 25 }] } } }))`)
      else await st(`cadui.ss.set((s) => ({ views: { ...s.views, Spreadsheet: { ...s.views.Spreadsheet, ranges: [{ r1: 0, c1: 18, r2: 1023, c2: ${17 + n} }] } } }))`)
      const loc = orient === 'rows' ? page.locator('[data-row="15"]') : page.locator(`[data-col="${colName(18)}"]`)
      await scrollGrid(orient === 'rows' ? 0 : 1500, orient === 'rows' ? 300 : 0)
      await loc.click({ button: 'right' })
      await sleep(200)
      const items = await st(`[...document.querySelectorAll('.ctx > *')].map((e) => e.textContent.trim()).filter(Boolean)`)
      await page.keyboard.press('Escape')
      same(items, H[`${orient}_${n}`].actions.map((a) => a.text), `the ${orient} header's menu with ${n} selected`)
    }
    for (const [a, t] of [['A25', '=A26 + 1'], ['A26', '4']]) await apply([{ op: 'set', args: [a, t] }], 'Edit cell')
    await st(`cadui.ss.set((s) => ({ views: { ...s.views, Spreadsheet: { ...s.views.Spreadsheet, ranges: [{ r1: 25, c1: 0, r2: 25, c2: 25 }] } } }))`)
    await scrollGrid(0, 600)
    await page.locator('[data-row="26"]').click({ button: 'right' })
    await sleep(200)
    { const n = await undoCount(); await page.locator('.ctx > *').first().click(); await settle(n) }
    same([await undoHead()], H.insert_undo, 'Insert Rows Above: the undo step')
    const d = await sheet()
    const a2 = {}
    for (const a of Object.keys(d.cells)) if (a.startsWith('A2')) a2[a] = await cellState(a)
    same(Object.fromEntries(Object.entries(a2).sort()), Object.fromEntries(Object.entries(H.after_insert).sort()), 'Insert Rows Above: the cells and references after')
  }
  // ── the keys ──
  if (want('keys')) {
    console.log('keys')
    await apply([{ op: 'mergeCells', args: ['T5:U6'] }], 'Merge cells')
    for (const m of FC.keys.moves) {
      await select(m.from)
      await page.locator('.ss-grid-scroll').focus()
      const key = { Return: 'Enter', Backtab: 'Shift+Tab', Left: 'ArrowLeft', Right: 'ArrowRight', Up: 'ArrowUp', Down: 'ArrowDown', Home: 'Home', End: 'End', Tab: 'Tab' }[m.key] ?? m.key
      const mod = m.mod & 0x04000000 ? 'Control+' : m.mod & 0x02000000 && m.key !== 'Backtab' ? 'Shift+' : ''
      await page.keyboard.press(mod + key)
      await sleep(120)
      const to = await st(`(() => { const c = cadui.ss.state().views.Spreadsheet.cur; return (c.col < 26 ? String.fromCharCode(65 + c.col) : '') + (c.row + 1) })()`)
      if (to === m.to) ok(`${mod}${key} from ${m.from}`)
      else if (mod === 'Control+' && key === 'ArrowDown') note(`Ctrl+Down from ${m.from}: ours goes to ${to} (SheetTableView's region scan); FreeCAD's recording stayed at ${m.to} (Qt took the key first)`)
      else bad(`${mod}${key} from ${m.from}`, `FreeCAD ${m.to}, ours ${to}`)
    }
  }
  // ── a second sheet with cycles ──
  if (want('cycles')) {
    console.log('cycles')
    const n = await undoCount()
    await st(`cadui.ss.apply('Spreadsheet001', [{ op: 'new' }, ...[['A1', '=A2 + 1'], ['A2', '=A1'], ['A3', '=A3'], ['B1', '5'], ['B2', '=B1 * 2']].map(([a, t]) => ({ op: 'set', args: [a, t] }))], 'Create Spreadsheet')`)
    await settle(n)
    await st(`(() => { cadui.ss.set({ sel: [] }); })()`)
    await page.locator('[data-ss="Spreadsheet001"]').dblclick()
    await until(`!!document.querySelector('.ss-view[data-sheet="Spreadsheet001"]')`, 'the second sheet')
    const v2 = (a) => page.evaluate((addr) => { const el = document.querySelector(`.ss-view[data-sheet="Spreadsheet001"] .ss-cell[data-cell="${addr}"]`); return el ? { display: el.querySelector('.ss-text')?.textContent ?? '', tooltip: el.getAttribute('data-tip'), fg: el.style.color } : null }, a)
    const rgb = (h) => (h ? `rgb(${[1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)).join(', ')})` : '')
    for (const [a, w] of Object.entries(FC.cycles.first)) {
      if (!w.display) continue
      same(await v2(a), { display: w.display, tooltip: w.tooltip, fg: rgb(w.fg) }, `a cycle: ${a}`)
    }
  }
  // ── undo ──
  if (want('undo')) {
    console.log('undo')
    const before = await undoHead()
    await runCmd('Std_Undo')
    await until(`cadui.getState().redo.length > 0`, 'the redo list', 30000)
    await sleep(400)
    check((await st('cadui.getState().redo[0]?.name')) === before, 'Std_Undo takes the last step back', J(await st('cadui.getState().redo.slice(0, 1)')))
    await runCmd('Std_Redo')
    await until(`cadui.getState().undo[0]?.name === ${J(before)}`, 'the step again', 30000)
    check((await undoHead()) === before, 'Std_Redo does it again')
  }
} catch (e) { bad('the check stopped', e.stack ?? String(e)) }
await browser.close()
server.kill()
if (!args.includes('--keep')) { rmSync(scratch, { recursive: true, force: true }); rmSync(warmDir, { recursive: true, force: true }) }
console.log(`spreadsheetcheck: ${pass} ok, ${known} known, ${fail} FAIL`)
process.exit(fail ? 1 : 0)

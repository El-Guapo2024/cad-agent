// SPDX-License-Identifier: LGPL-2.1-or-later
// camcheck: the CAM workbench in the page, held to the real FreeCAD's (ui/scripts/fccam.json, written by fccam.py from
// FreeCAD 26.3 at 3160daf1e2b6), driven on a scratch copy of tests/fixtures/feature_plate as the recording drove FreeCAD
// on the same plate (tests/golden/cam/breps/plate.brep).
//
//   NODE_PATH=<folder with playwright> node ui/scripts/camcheck.mjs [--fc=ui/scripts/fccam.json] [--only=SECTION,...] [--keep] [--verbose]
//
// Sections, in the recording's order (each leaves the job as FreeCAD's dump left it, so the next compares alike):
//   menus     the menu bar puts CAM before Windows; the CAM menu with no job, with a job: entries and which are active
//   toolbars  Project Setup, Tool Commands, New Operations and Path Modification, button by button (the groups' menus)
//   job       CAM_Job with the plate selected: the dialog, then the Job's panel tab by tab, OK; the undo step
//   ops       CAM_Profile, CAM_Pocket_Shape (Face17), CAM_Drilling (Face7-10), CAM_MillFace (Face5): each panel tab by tab
//             (every named widget's value, items, check state), OK; the objects made and the undo steps
//   dressups  CAM_DressupTag on Profile (the Holding Tags panel, OK), CAM_DressupDogbone on Pocket_Shape
//   tree      the job's rows in the tree
//   props     the property view of each kind of object: every row's name and text
//   tc        a tool controller's panel (a double click)
//   edit      Profile's Direction set in its panel: the step, the property, the job file, Std_Undo
//   undo      Std_Undo and Std_Redo
//   post      CAM_Post with the job selected: the post-processor's G-code (tests/golden/cam holds it to FreeCAD's)
//   view      each op's toolpath drawn in the 3D view
// A difference prints as FAIL; the deliberate ones (PARITY.md, "CAM workbench") as `known`. Exit 1 on a FAIL.
import { createRequire } from 'module'
import { spawn, spawnSync } from 'child_process'
import { cpSync, mkdirSync, mkdtempSync, readFileSync, rmSync } from 'fs'
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
const FC = JSON.parse(readFileSync(flag('fc', join(HERE, 'fccam.json')), 'utf8'))
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
const clean = (t) => String(t ?? '').replace(/&&/g, '\0').replace(/&(.)/g, '$1').replace(/\0/g, '&').replace(/…$/, '').trim()

// the commands this app runs; the rest of the CAM menu is greyed with the reason (PARITY.md)
const RUN = new Set(['CAM_Job', 'CAM_Post', 'CAM_OpActiveToggle', 'CAM_Profile', 'CAM_Pocket_Shape', 'CAM_Drilling', 'CAM_DressupTag', 'CAM_DressupDogbone', 'CAM_PostTools', 'CAM_DrillingTools', 'CAM_DressupTools'])
const GROUPS = new Set(['Path Dressup', 'Supplemental Commands', 'Path Modification', 'Utils'])

// ── a scratch workbench ───────────────────────────────────────────────────────────────────────────────────────
const freePort = (from) => new Promise((res, rej) => {
  const tryPort = (p) => { if (p > from + 40) return rej(new Error('no free port')); const s = createServer(); s.once('error', () => tryPort(p + 1)); s.once('listening', () => s.close(() => res(p))); s.listen(p, '127.0.0.1') }
  tryPort(from)
})
const scratch = mkdtempSync(join(tmpdir(), 'cad-camcheck-')), warmDir = mkdtempSync(join(tmpdir(), 'cad-camcheck-warm-'))
const ROOT = join(scratch, 'root'); mkdirSync(ROOT)
for (const d of ['runtime', 'macros']) mkdirSync(join(scratch, d))
const python = process.env.CAD_PYTHON || join(REPO, '.venv', 'bin', 'python')
const env = { ...process.env, CAD_WARM_DIR: warmDir, CAD_RUNTIME_DIR: join(scratch, 'runtime'), CAD_MACRO_DIR: join(scratch, 'macros'),
  CAD_PREFS: join(scratch, 'prefs.json'), PYTHONPATH: REPO, CAD_PYTHON: python, CAD_RENDER_BACKEND: 'numpy' }
delete env.CAD_PROJECTS
const SLUG = 'feature_plate'
cpSync(join(REPO, 'tests', 'fixtures', SLUG), join(ROOT, SLUG), { recursive: true })
spawnSync(python, ['-m', 'cad_agent', '--projects', ROOT, 'check', SLUG], { env, cwd: REPO })
const port = await freePort(9071)
const server = spawn(python, ['-c', `import sys; from pathlib import Path; from cad_agent import serve; serve.run([Path(sys.argv[1])], host="127.0.0.1", port=${port})`, ROOT],
  { env, cwd: REPO, stdio: ['ignore', 'pipe', 'pipe'] })
await new Promise((res, rej) => {
  const t = setTimeout(() => rej(new Error('the scratch workbench did not start')), 60000)
  server.stdout.on('data', (d) => { if (/workbench: http/.test(String(d))) { clearTimeout(t); res() } })
  server.on('exit', (c) => rej(new Error(`the scratch workbench exited with ${c}`)))
})
const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] })
const ctx = await browser.newContext({ viewport: { width: 1400, height: 950 }, acceptDownloads: true })
const page = await ctx.newPage()
page.on('pageerror', (e) => bad('page error', e.message))
const st = (expr) => page.evaluate(expr)
const until = async (expr, what, ms = 90000) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { if (await st(expr)) return true; await sleep(200) } bad(`timed out waiting: ${what}`); return false }
const runCmd = (c) => st(`cadui.getCommand(${J(c)})?.run([])`)
const cam = () => st('cadui.camApi.state()')
const undoNames = () => st('cadui.getState().undo.map((u) => u.name)')
const undoId = () => st('cadui.getState().undo[0]?.id ?? null')
const settle = async (before) => {
  if (!(await until(`(cadui.getState().undo[0]?.id ?? null) !== ${J(before)} && !cadui.camApi.state().busy`, 'the undo step', 120000)))
    console.log('        the Report view:', J(await st(`cadui.getState().messages.slice(-3).map((e) => e.text)`)))
  await sleep(500)
}
const body = async () => st(`cadui.getState().scene?.bodies.find((b) => b.part === 'plate')?.name ?? null`)
const selectFaces = async (faces) => { const b = await body(); await st(`(() => { cadui.camApi.set({ sel: [] }); cadui.setState({ selected: ${J(faces.length ? [] : [b])}, subSel: ${J(faces.map((f) => `${b}.${f}`))} }) })()`); await sleep(200) }

// ── the menu and toolbars ──
function compareMenu(fc, ours, what) {
  const f = fc.filter((e) => !e.sep), o = ours.filter((e) => !e.sep)
  same(o.map((e) => clean(e.text)), f.map((e) => clean(e.text)), `${what}: the entries`)
  same(o.map((e) => e.cmd ?? clean(e.text)), f.map((e) => e.name), `${what}: the commands`)
  same(o.map((e) => e.kbd || ''), f.map((e) => e.shortcut || ''), `${what}: the shortcuts`)
  for (const e of f) {
    const m = o.find((x) => (x.cmd ?? clean(x.text)) === e.name)
    if (!m) continue
    if (e.menu && m.menu) { compareMenu(e.menu, m.menu, `${what} > ${clean(e.text)}`); continue }
    if (m.enabled === e.enabled) ok(`${what}: ${e.name}`)
    else if (!RUN.has(e.name) && !m.enabled && m.why) note(`${what}: ${e.name} is greyed here (${m.why.split('\n').pop()})`)
    else bad(`${what}: ${e.name} ${e.enabled ? 'active' : 'greyed'}`, `ours ${m.enabled ? 'active' : 'greyed'}`)
  }
}
async function menus(what, fc) {
  const bar = await st(`[...document.querySelectorAll('.menubar > *')].map((e) => e.textContent.trim()).filter(Boolean)`)
  const i = bar.indexOf('CAM'), w = bar.indexOf('Windows')
  check(i >= 0 && w === i + 1, `${what}: CAM sits before Windows in the menu bar`, J(bar))
  compareMenu(fc['&CAM'], (await st('cadui.cam()')).menu, `${what}: CAM menu`)
}
async function toolbars(what, fc) {
  const ours = (await st('cadui.cam()')).toolbars
  const fcb = fc.filter((t) => ['Project Setup', 'Tool Commands', 'New Operations', 'Path Modification'].includes(t.title))
  same(ours.map((t) => t.title), fcb.map((t) => t.title), `${what}: the CAM toolbars`)
  for (const t of fcb) {
    const o = ours.find((x) => x.title === t.title)
    if (!o) continue
    same(o.buttons.filter((b) => !b.sep).map((b) => b.cmd), t.buttons.filter((b) => !b.sep).map((b) => b.name), `${what}: ${t.title}'s buttons`)
    for (const b of t.buttons.filter((x) => !x.sep)) {
      const m = o.buttons.find((x) => x.cmd === b.name)
      if (!m) continue
      if (b.menu) same(m.menu.map((x) => clean(x.text)), b.menu.filter((x) => !x.sep).map((x) => clean(x.text)), `${what}: ${b.name}'s menu`)
      if (m.enabled === b.enabled) ok(`${what}: ${b.name}`)
      else if (!RUN.has(b.name) && !m.enabled) note(`${what}: ${b.name} is greyed here`)
      else bad(`${what}: ${b.name} ${b.enabled ? 'active' : 'greyed'}`, `ours ${m.enabled ? 'active' : 'greyed'}`)
    }
  }
}

// ── a panel's widgets, as fccam_dump.py's widget_rows reads them ──
/** What the page shows for a widget of FreeCAD's form, by its object name, in the panel (or the tab's page). */
async function widget(scope, name, cls) {
  return page.evaluate(([scope, name, cls]) => {
    const root = document.querySelector(scope)
    if (!root) return null
    const el = [...root.querySelectorAll(`[data-qf="${name}"]`)].find((x) => x.offsetParent !== null)
    if (!el) return null
    const out = {}
    const input = el.matches('input') ? el : el.querySelector('input')
    const select = el.matches('button.qselect') ? el : el.querySelector('button.qselect')
    if (/ComboBox/.test(cls) && select) out.current = select.querySelector('.combo-label')?.textContent ?? ''
    else if (/CheckBox/.test(cls) && input) out.checked = input.checked
    else if (/GroupBox/.test(cls)) { out.text = el.querySelector('.qf-gb-title')?.textContent ?? ''; const c = el.querySelector('.qf-gb-title input'); if (c) out.checked = c.checked }
    else if (/SpinBox|LineEdit|InputField/.test(cls) && input) out.text = input.value
    else if (/ListWidget/.test(cls)) out.items = [...el.querySelectorAll('.qf-list-row')].map((x) => x.textContent)
    else if (/TableWidget/.test(cls)) out.rows = [...el.querySelectorAll('tbody tr')].map((tr) => [...tr.children].map((td) => td.textContent))
    else if (/PushButton|ToolButton/.test(cls)) out.text = el.textContent ?? ''
    else if (/Label/.test(cls)) out.text = el.textContent ?? ''
    out.enabled = !(el.disabled || input?.disabled || select?.disabled || el.classList.contains('off'))
    return out
  }, [scope, name, cls])
}
/** A combo box's items: its popup opened (QComboBox::showPopup), read, closed. A greyed one cannot open: null. */
async function comboItems(scope, name) {
  const b = page.locator(`${scope} button.qselect[data-qf="${name}"]`).first()
  if (!(await b.count()) || (await b.isDisabled())) return null
  await b.dispatchEvent('mousedown')
  await sleep(150)
  const items = await st('[...document.querySelectorAll(".combo-popup .combo-item")].map((e) => e.textContent)')
  await page.keyboard.press('Escape')
  await sleep(100)
  return items
}
const SKIP_CLS = /Label$|TaskHeader|ActionLabel|QToolBoxButton|TableCornerButton|IconTabWidget|QTabWidget|QFrame|QWidget$|QPushButton$|QToolButton$/
/** FreeCAD's rows of a tab against ours: each named widget's value. */
async function compareRows(scope, rows, what, skip = new Set(), knownDiff = {}) {
  const seen = new Set()
  for (const r of rows) {
    if (!r.name || r.name.startsWith('qt_') || SKIP_CLS.test(r.class) || skip.has(r.name) || seen.has(r.name)) continue
    seen.add(r.name)
    const o = await widget(scope, r.name, r.class)
    if (o && /ComboBox/.test(r.class)) o.items = await comboItems(scope, r.name)
    if (!o) { if (knownDiff[r.name]) note(`${what}: ${r.name}: ${knownDiff[r.name]}`); else bad(`${what}: ${r.name}`, 'not shown'); continue }
    const want_ = {}
    if (/ComboBox/.test(r.class)) { want_.current = r.current; want_.items = r.items }
    else if (/CheckBox/.test(r.class)) want_.checked = !!r.checked
    else if (/GroupBox/.test(r.class)) { want_.text = clean(r.text); if (r.checked !== undefined) want_.checked = r.checked }
    else if (/SpinBox|LineEdit|InputField/.test(r.class)) want_.text = r.text
    else if (/ListWidget/.test(r.class)) want_.items = r.items
    else if (/TableWidget/.test(r.class)) want_.rows = r.rows
    if (o.items === null && /ComboBox/.test(r.class)) delete want_.items   // greyed: its current text only
    const got = Object.fromEntries(Object.keys(want_).map((k) => [k, o[k]]))
    if (J(got) === J(want_)) ok(`${what}: ${r.name}`)
    else if (knownDiff[r.name]) note(`${what}: ${r.name}: ${knownDiff[r.name]}`)
    else bad(`${what}: ${r.name}`, `\n        FreeCAD ${J(want_)}\n        ours    ${J(got)}`)
  }
}
const tabTitles = (scope) => st(`[...document.querySelectorAll('${scope} [data-cam-tab]')].map((b) => b.dataset.camTab)`)
const clickTab = async (scope, title) => { await page.locator(`${scope} [data-cam-tab="${title}"]`).click(); await sleep(250) }
const okTask = async () => { await page.locator('.tasks .tbuttons .qbtn.default').first().click() }

try {
  await page.goto(`http://127.0.0.1:${port}/next/#${SLUG}`)
  await until(`cadui.getState().slug === ${J(SLUG)} && !!cadui.getState().scene`, 'the project open')
  await sleep(2500)
  await st(`cadui.setState({ workbench: 'cam' })`)
  await sleep(600)
  if (want('menus')) { console.log('menus'); await menus('no job', FC.menus_empty) }
  if (want('toolbars')) { console.log('toolbars'); await toolbars('no job', FC.toolbars_empty) }

  // ── CAM_Job ──
  console.log('job')
  {
    await selectFaces([])
    await runCmd('CAM_Job')
    await until(`!!document.querySelector('[data-cam-dialog="jobcreate"]')`, 'the New Job dialog')
    const d = FC.job_dialog
    same(await st(`document.querySelector('[data-cam-dialog="jobcreate"] .msgbox-title').textContent`), d.title, "the dialog's title")
    await compareRows('[data-cam-dialog="jobcreate"]', d.rows, 'the New Job dialog')
    same(await st(`[...document.querySelectorAll('[data-cam="models"] label')].map((l) => [l.textContent, l.querySelector('input').checked])`), [['plate', true]], 'the dialog\'s Solids: the plate, ticked as it is selected')
    const n = await undoId()
    await page.locator('[data-cam-dialog="jobcreate"] .qbtn.default').click()
    await settle(n)
    await until(`!!document.querySelector('.tasks [data-qf="pathEdit"]')`, "the Job's panel")
    const fcPanel = FC.job_panel[0]
    const tabs = await st(`[...document.querySelectorAll('.tasks [data-qf="pathEdit"] > .qf-tabbar .qf-tab')].map((b) => b.textContent)`)
    same(tabs, fcPanel.tabs.map((t) => t.tab), "the Job panel's tabs")
    const KNOWN_JOB = { postProcessor: "FreeCAD's linuxcnc, grbl and generic post-processors are the ones this app has", opDefaultOp: "the setup sheet's op defaults are not edited here",
      wcslist: 'the work coordinate systems are shown as check boxes', toolControllerList: 'a tool controller row', jobDescription: 'a text box' }
    for (const [i, t] of fcPanel.tabs.entries()) {
      await page.locator(`.tasks [data-qf="pathEdit"] > .qf-tabbar .qf-tab >> nth=${i}`).click()
      await sleep(300)
      // the Setup tab's second page and the Tools tab's second page are closed in the recording as in the page
      await compareRows('.tasks', t.rows, `Job panel ${t.tab}`, new Set(['modelRotateAxis', 'modelMoveValue', 'modelRotateValue', 'modelRotateCompound']), KNOWN_JOB)
    }
    await page.locator(`.tasks [data-qf="pathEdit"] > .qf-tabbar .qf-tab >> nth=0`).click()
    await okTask()
    await sleep(800)
    const names = await undoNames()
    same(names.slice(0, 1), FC.undo_job.slice(-1), 'the undo step of CAM_Job')
    if (FC.undo_job[0] === 'Edit Job') note('the Job panel\'s OK with nothing changed adds no step here ("Edit Job" in FreeCAD is an empty transaction)')
    same((await cam()).jobs, ['Job'], 'the job file')
    if (want('menus')) { await sleep(300); await st(`cadui.camApi.set({ sel: [] })`); await menus('a job', FC.menus_job) }
  }

  // ── the operations ──
  const OPS = [['CAM_Profile', [], 'Profile'], ['CAM_Pocket_Shape', ['Face17'], 'Pocket_Shape'], ['CAM_Drilling', ['Face7', 'Face8', 'Face9', 'Face10'], 'Drilling'], ['CAM_MillFace', ['Face5'], 'MillFace']]
  for (const [cmd, faces, made] of OPS) {
    if (!want('ops') && !want('dressups') && !want('tree') && !want('props') && !want('undo') && !want('post') && !want('view') && !want('tc') && !want('edit')) break
    console.log(cmd)
    const rec = FC[`op_${cmd}`]
    await selectFaces(faces)
    const n = await undoId()
    await runCmd(cmd)
    await settle(n)
    await until(`!!document.querySelector('.tasks[data-cam-panel="${made}"]')`, `the ${made} panel`)
    same(((await undoNames())[0]), rec.undo[1], `${cmd}: the undo step`)
    same([made], rec.made, `${cmd}: the object made`)
    const scope = `.tasks[data-cam-panel="${made}"]`
    const fcTabs = rec.panel[0].tabs
    same(await tabTitles(scope), fcTabs.map((t) => t.tab), `${cmd}: the panel's tabs`)
    same(await st(`document.querySelector('${scope} .qf-tab.cur')?.dataset.camTab`), rec.panel[0].rows.find((r) => /TabWidget/.test(r.class))?.current ?? 'Operation', `${cmd}: the tab in front`)
    if (want('ops')) {
      for (const t of fcTabs) {
        await clickTab(scope, t.tab)
        await compareRows(scope, t.rows, `${cmd} ${t.tab}`, new Set(), { workplane: 'work planes are not made here', geometryImportList: '', sortMode: '' })
      }
    }
    await clickTab(scope, fcTabs[fcTabs.length - 1].tab)
    await okTask()
    await sleep(800)
    if (rec.undo[0] === 'AreaOp Operation') note(`${cmd}: OK with nothing changed adds no step here (FreeCAD's "AreaOp Operation" is an empty transaction)`)
  }

  // ── the dress-ups ──
  if (want('dressups') || want('tree') || want('props') || want('undo') || want('post') || want('view') || want('tc') || want('edit')) {
    console.log('dressups')
    {
      const rec = FC.dressup_CAM_DressupTag
      await st(`cadui.setState({ selected: [], subSel: [] })`)
      await st(`cadui.camApi.select('Job/Profile')`)
      await sleep(200)
      const n = await undoId()
      await runCmd('CAM_DressupTag')
      await settle(n)
      await until(`!!document.querySelector('.tasks[data-cam-panel="DressupTag"]')`, 'the Holding Tags panel')
      same((await undoNames())[0], rec.undo[1], 'CAM_DressupTag: the undo step')
      const scope = '.tasks[data-cam-panel="DressupTag"]'
      const rows = rec.panel[0].rows
      await compareRows(scope, rows.filter((r) => r.name !== 'lwTags'), 'the Holding Tags panel', new Set(), { pbCopy: '' })
      const fcTags = rows.find((r) => r.name === 'lwTags').items
      const ours = await st(`[...document.querySelectorAll('[data-cam="tags"] .qf-list-row')].map((x) => x.textContent)`)
      const pos = (xs) => xs.map((x) => x.replace(/^\d+: /, '')).sort()
      same(ours.length, fcTags.length, 'the Holding Tags panel: as many tags')
      if (J(pos(ours)) === J(pos(fcTags))) ok('the Holding Tags panel: the tags')
      else note(`the Holding Tags panel: the tags sit elsewhere along the profile (${J(pos(ours))}): it starts at another of the plate's symmetric corners, where FreeCAD picks by memory address (PARITY.md)`)
      const m = await undoId()
      await okTask()
      await settle(m)
      same((await undoNames())[0], rec.undo[0], 'the Holding Tags panel: OK\'s step')
    }
    {
      const rec = FC.dressup_CAM_DressupDogbone
      await st(`cadui.camApi.select('Job/Pocket_Shape')`)
      await sleep(200)
      const n = await undoId()
      await runCmd('CAM_DressupDogbone')
      await settle(n)
      same((await undoNames())[0], rec.undo[0], 'CAM_DressupDogbone: the undo step')
      same(await st(`!!document.querySelector('.tasks[data-cam-panel]')`), rec.panel.some((p) => p.rows.length) , 'CAM_DressupDogbone opens no panel')
      same((await undoNames()).slice(0, 13), FC.undo.filter((x) => x !== 'AreaOp Operation' && x !== 'Edit Job'), 'the undo steps so far')
    }
  }

  // ── the tree ──
  if (want('tree')) {
    console.log('tree')
    const fc = FC.tree
    const i = fc.findIndex((r) => r.text === 'Job')
    const rows = []
    for (const r of fc.slice(i)) {
      if (r.depth < 1) break
      rows.push([r.text, r.depth - 1])
    }
    const ours = await st(`[...document.querySelectorAll('[data-cam]')].filter((e) => e.classList.contains('trow')).map((e) => [e.querySelector('.tname').textContent, Math.round((parseFloat(e.querySelector('.pdindent').style.width) - 6) / 16) - 1])`)
    const bitBody = rows.findIndex((r) => r[0] === 'Endmill001')
    const fcRows = bitBody >= 0 ? rows.filter((r, k) => !(k >= bitBody && r[1] > rows[bitBody - 1][1]) ) : rows
    same(ours, fcRows, "the job's rows")
    if (bitBody >= 0) note("the tool bit's Body (its Origin, Revolution and Sketch) is not shown under the bit: the bit's 3D shape is not made here")
  }

  // ── the property view ──
  if (want('props')) {
    console.log('props')
    const KNOWN_PROP = { 'Endmill.Tool Bit ID': 'a new id each time a bit is made', 'DressupTag.Positions': 'the tags start at another corner (see the Holding Tags panel)' }
    for (const key of Object.keys(FC).filter((k) => k.startsWith('props_'))) {
      const name = key.slice(6)
      const fcRows = FC[key].data[0].map((r) => [r.depth, r.name, r.depth === 0 ? null : r.value])
      const ours = await st(`cadui.camApi.props('Job', ${J(name)})`)
      if (!ours.length) { if (name === 'Endmill') note(`props ${name}`); else bad(`props ${name}`, 'no such object'); continue }
      same(ours.map((r) => [r[0], r[1]]), fcRows.map((r) => [r[0], r[1]]), `props ${name}: the rows`)
      for (const r of fcRows.filter((x) => x[0] === 1)) {
        const o = ours.find((x) => x[0] === 1 && x[1] === r[1])
        if (!o) continue
        if (o[2] === r[2]) ok(`props ${name}.${r[1]}`)
        else if (KNOWN_PROP[`${name}.${r[1]}`]) note(`props ${name}.${r[1]}: ${KNOWN_PROP[`${name}.${r[1]}`]}`)
        else bad(`props ${name}.${r[1]}`, `FreeCAD ${J(r[2])}, ours ${J(o[2])}`)
      }
    }
  }

  // ── a tool controller's panel ──
  if (want('tc')) {
    console.log('tc')
    await page.locator('[data-cam="Job/TC__5mm_Endmill"]').dblclick()
    await until(`!!document.querySelector('.tasks[data-cam-panel="TC__5mm_Endmill"]')`, "the tool controller's panel")
    await compareRows('.tasks[data-cam-panel="TC__5mm_Endmill"]', FC.tc_panel[0].rows, "the tool controller's panel")
    await page.locator('.tasks .tbuttons .qbtn').nth(1).click()
    await sleep(500)
  }

  // ── an edit through a panel: Profile's Direction (the recording edits nothing; FreeCAD's step for it is the panel's) ──
  if (want('edit')) {
    console.log('edit')
    await page.locator('[data-cam="Job/Profile"]').dblclick()
    await until(`!!document.querySelector('.tasks[data-cam-panel="Profile"]')`, "Profile's panel")
    const scope = '.tasks[data-cam-panel="Profile"]'
    await page.locator(`${scope} button.qselect[data-qf="direction"]`).dispatchEvent('mousedown')
    await sleep(150)
    await page.locator('.combo-popup .combo-item', { hasText: 'CCW' }).first().click()
    await sleep(150)
    const n = await undoId()
    await okTask()
    await settle(n)
    same((await undoNames())[0], 'AreaOp Operation', "the panel's OK: one step, TaskPanel's transaction")
    same(await st(`cadui.camApi.state().docs.Job.result.objects.find((o) => o.name === 'Profile').props.find((p) => p.name === 'Direction').value`), 'CCW', 'Profile.Direction is CCW')
    same(await st(`cadui.camApi.state().docs.Job.entries.find((e) => e.name === 'Profile').props`), { Direction: 'CCW' }, 'the job file holds it')
    const m = await undoId()
    await runCmd('Std_Undo')
    await until(`cadui.camApi.state().docs.Job?.result?.objects.find((o) => o.name === 'Profile')?.props.find((p) => p.name === 'Direction')?.value === 'CW'`, 'Std_Undo of the edit', 60000)
    void m
    ok('Std_Undo takes the edit back')
  }

  // ── undo and redo ──
  if (want('undo')) {
    console.log('undo')
    const before = (await undoNames())[0]
    await runCmd('Std_Undo')
    await until(`cadui.getState().redo.length > 0 && !cadui.camApi.state().docs.Job?.result?.objects.some((o) => o.name === 'DressupDogbone')`, 'Std_Undo', 60000)
    same(await st('cadui.getState().redo[0]?.name'), FC.undo_redo.redo_names[0], 'Std_Undo takes the last step back')
    check(before === FC.undo_redo.redo_names[0], 'the step undone is the last one')
    await runCmd('Std_Redo')
    await until(`cadui.camApi.state().docs.Job?.result?.objects.some((o) => o.name === 'DressupDogbone')`, 'Std_Redo', 60000)
    same((await undoNames())[0], FC.undo_redo.after_redo_undo[0], 'Std_Redo does it again')
  }

  // ── CAM_Post ──
  if (want('post')) {
    console.log('post')
    await st(`cadui.camApi.select('Job/Job')`)
    await sleep(200)
    await runCmd('CAM_Post')
    await until(`!!document.querySelector('[data-cam-dialog="post"]')`, 'the post-processor choice')
    same(await st(`[...document.querySelectorAll('[data-cam="posts"] .qf-list-row')].map((x) => x.textContent)`), ['generic', 'grbl', 'linuxcnc'], 'the post-processors')
    const dl = page.waitForEvent('download')
    await page.locator('[data-cam-dialog="post"] .qbtn.default').click()
    const d = await dl
    check(d.suggestedFilename() === 'Job.nc', 'the G-code is saved as Job.nc', d.suggestedFilename())
    await until(`!!window.__camLastGcode`, 'the G-code')
    const g = await st('window.__camLastGcode')
    check(/\(Begin preamble\)/.test(g) && /G81/.test(g) && /\(Begin postamble\)/.test(g), "linuxcnc's G-code: its preamble, the drill cycles, its postamble", J([/\(Begin preamble\)/.test(g), /G81/.test(g), /\(Begin postamble\)/.test(g), g.split('\n').filter((l) => /^G8|^M/.test(l)).slice(0, 6)]))
  }

  // ── the 3D view ──
  if (want('view')) {
    console.log('view')
    const drawn = await st(`(() => { const s = cadui.getView()?.viewer?.scene; const g = []; s?.traverse((o) => { if (o.name?.startsWith('cam:')) g.push(o.name) }); return g.sort() })()`)
    same(drawn, ['cam:Job/DressupDogbone', 'cam:Job/DressupTag', 'cam:Job/Drilling', 'cam:Job/MillFace'], "the toolpaths drawn: the tree's operations (a dress-up, not its base)")
  }
} catch (e) { bad('the check stopped', e.stack ?? String(e)) }
await browser.close()
server.kill()
if (!args.includes('--keep')) { rmSync(scratch, { recursive: true, force: true }); rmSync(warmDir, { recursive: true, force: true }) }
console.log(`camcheck: ${pass} ok, ${known} known, ${fail} FAIL`)
process.exit(fail ? 1 : 0)

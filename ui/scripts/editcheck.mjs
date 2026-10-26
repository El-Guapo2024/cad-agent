// SPDX-License-Identifier: LGPL-2.1-or-later
// editcheck: PartDesign editing in the page, held to the real FreeCAD's (ui/scripts/fcedit.json, written by fcedit.py from
// FreeCAD 26.3 at 3160daf1e2b6), then driven end to end.
//
//   NODE_PATH=<folder with playwright> node ui/scripts/editcheck.mjs [--fc=ui/scripts/fcedit.json] [--keep]
//
// It starts a scratch workbench of its own (a temporary projects folder with one empty project, CAD_* pointed at scratch
// paths, as wirecheck.mjs does) and, in Chromium on SwiftShader:
//   menus      the Sketch and Part Design menus, entry by entry, against FreeCAD's (text and command; what is greyed here is
//              listed, since only Body, Sketch, Pad and Pocket are built)
//   toolbars   the four PartDesign toolbars, button by button
//   flow       New Body, New Sketch (the attachment panel, XY-plane picked in the tree, OK), a rectangle written into the
//              sketch, Pad (its panel's fields and defaults against FreeCAD's, OK), a second sketch 10 mm up with a circle,
//              Pocket (its panel against FreeCAD's, OK)
//   tree       the Body's rows (text, depth, greyed for hidden, the Tip's overlay) against FreeCAD's for the same Body
//   menu       the tree's context menu on the Pad, the Sketch and the Body, against FreeCAD's
//   delete     Std_Delete on the sketch the Pad uses: FreeCAD's warning, answered No
//   tip/undo   Set Tip on the Pad (rows as FreeCAD shows them then), Undo puts the Tip back
//   edit       double-click on the Pad: its panel with its values; F2 renames
// A difference prints as FAIL; the ones that are deliberate (PARITY.md, "PartDesign") as `known`. Exit 1 on a FAIL.
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
const FC = JSON.parse(readFileSync(flag('fc', join(HERE, 'fcedit.json')), 'utf8'))
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
let pass = 0, fail = 0, known = 0
const ok = (what) => { pass++; if (args.includes('--verbose')) console.log(`  ok    ${what}`) }
const bad = (what, detail = '') => { fail++; console.log(`  FAIL  ${what}${detail ? `: ${detail}` : ''}`) }
const note = (what) => { known++; console.log(`  known ${what}`) }
const check = (cond, what, detail) => (cond ? ok(what) : bad(what, detail))
const clean = (t) => String(t ?? '').replace(/&(.)/g, '$1').trim()

// ── a scratch workbench ──────────────────────────────────────────────────────────────────────────────────────────────
const freePort = (from) => new Promise((res, rej) => {
  const tryPort = (p) => {
    if (p > from + 40) return rej(new Error('no free port'))
    const s = createServer(); s.once('error', () => tryPort(p + 1)); s.once('listening', () => s.close(() => res(p))); s.listen(p, '127.0.0.1')
  }
  tryPort(from)
})
const scratch = mkdtempSync(join(tmpdir(), 'cad-editcheck-')), warmDir = mkdtempSync('/tmp/cec')
const ROOT = join(scratch, 'root'); mkdirSync(ROOT)
for (const d of ['runtime', 'macros']) mkdirSync(join(scratch, d))
const python = process.env.CAD_PYTHON || join(REPO, '.venv', 'bin', 'python')
const env = { ...process.env, CAD_WARM_DIR: warmDir, CAD_RUNTIME_DIR: join(scratch, 'runtime'), CAD_MACRO_DIR: join(scratch, 'macros'),
  CAD_PREFS: join(scratch, 'prefs.json'), PYTHONPATH: REPO, CAD_PYTHON: python, CAD_RENDER_BACKEND: 'numpy' }
delete env.CAD_PROJECTS
spawnSync(python, ['-m', 'cad_agent', '--projects', ROOT, 'init', 'edit', '--brief', 'editcheck'], { env, cwd: REPO })
const port = await freePort(8871)
const server = spawn(python, ['-c', `import sys; from pathlib import Path; from cad_agent import serve; serve.run([Path(sys.argv[1])], host="127.0.0.1", port=${port})`, ROOT],
  { env, cwd: REPO, stdio: ['ignore', 'pipe', 'pipe'] })
await new Promise((res, rej) => {
  const t = setTimeout(() => rej(new Error('the scratch workbench did not start')), 60000)
  server.stdout.on('data', (d) => { if (/workbench: http/.test(String(d))) { clearTimeout(t); res() } })
  server.on('exit', (c) => rej(new Error(`the scratch workbench exited with ${c}`)))
})
const BASE = `http://127.0.0.1:${port}`
const post = async (path, body) => (await fetch(BASE + path, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CAD': '1' }, body: JSON.stringify(body) })).json()

const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] })
const page = await browser.newPage({ viewport: { width: 1400, height: 950 } })
page.on('pageerror', (e) => bad('page error', e.message))
const st = (expr) => page.evaluate(expr)
const until = async (expr, what, ms = 90000) => {
  const t0 = Date.now()
  while (Date.now() - t0 < ms) { if (await st(expr)) return true; await sleep(250) }
  bad(`timed out waiting: ${what}`); return false
}
try {
  await page.goto(`${BASE}/next/#edit`)
  await until('!!window.cadui && cadui.getState().slug === "edit" && !!cadui.getState().scene', 'the project to open')
  await st('cadui.setState({ workbench: "design" })')
  await sleep(300)

  // ── menus and toolbars ─────────────────────────────────────────────────────────────────────────────────────────────
  console.log('menus')
  const ours = await st('cadui.pd()')
  const GREYED = new Set(['Body', 'NewSketch', 'Pad', 'Pocket'].map((x) => `PartDesign_${x}`))
  const compare = (fc, us, where) => {
    const f = fc.filter((e) => e.sep || e.text !== undefined), u = us
    const ft = f.map((e) => (e.sep ? '---' : clean(e.text))), ut = u.map((e) => (e.sep ? '---' : e.text))
    check(JSON.stringify(ft) === JSON.stringify(ut), `${where}: the entries in FreeCAD's order`, `FreeCAD ${JSON.stringify(ft)}\n        ours    ${JSON.stringify(ut)}`)
    f.forEach((e, i) => {
      const o = u[i]
      if (e.sep || !o || o.sep) return
      if (e.menu && o.menu) compare(e.menu, o.menu, `${where} > ${clean(e.text)}`)
      const name = typeof e.name === 'string' && /_/.test(e.name) ? e.name : null
      if (name && o.cmd && name !== o.cmd) bad(`${where} > ${o.text}: command`, `${name} vs ${o.cmd}`)
      if (e.enabled && !o.enabled && !GREYED.has(name ?? '')) note(`${where} > ${o.text} greyed here (not built yet)`)
    })
  }
  compare(FC.menus['&Sketch'], ours.sketch, 'Sketch menu')
  compare(FC.menus['&Part Design'], ours.partDesign, 'Part Design menu')
  console.log('toolbars')
  for (const tb of ours.toolbars) {
    const f = FC.toolbars.find((t) => t.title === tb.title)
    if (!f) { bad(`toolbar ${tb.title}`, 'not in FreeCAD'); continue }
    const fn = f.buttons.map((b) => (b.sep ? '---' : b.name)), un = tb.buttons.map((b) => (b.sep ? '---' : b.cmd))
    check(JSON.stringify(fn) === JSON.stringify(un), `toolbar ${tb.title}: FreeCAD's buttons`, `FreeCAD ${JSON.stringify(fn)}\n        ours    ${JSON.stringify(un)}`)
  }
  for (const f of FC.toolbars.filter((t) => t.title.startsWith('Part Design'))) check(ours.toolbars.some((t) => t.title === f.title), `toolbar ${f.title} is here`)

  // ── the flow ───────────────────────────────────────────────────────────────────────────────────────────────────────
  console.log('flow')
  await page.click('.tb-btn[data-cmd="PartDesign_Body"]')
  await until('!!cadui.getState().features.Body', 'New Body')
  check(await st('cadui.getState().activeBody === "Body"'), 'New Body: Body is the active body')
  check(await st('cadui.getState().undo[0]?.name === "Add a Body"'), 'New Body: one undo step, "Add a Body"')
  await page.click('.tb-btn[data-cmd="PartDesign_CompSketches"]')
  await until('cadui.getState().task?.kind === "attach"', 'New Sketch\'s panel')
  const attach = await st('[...document.querySelectorAll(".taskview .pd-mode")].map((e) => e.textContent)')
  const fcModes = FC.pick.task[0].find((w) => w.name === 'listOfModes').items
  check(JSON.stringify(attach) === JSON.stringify(fcModes), 'New Sketch: the attachment modes with nothing picked', `${attach}`)
  check(await st('document.querySelector(".taskview .pd-attach-msg").textContent === "Not attached"'), 'New Sketch: "Not attached"')
  await st('cadui.showPanel("model")')
  await page.click('.trow[data-ref="Body/XY_Plane"]')
  await st('cadui.showPanel("tasks")')
  await sleep(300)
  const xyMsg = await st('document.querySelector(".taskview .pd-attach-msg")?.textContent ?? null')
  check(xyMsg === 'Attached with mode Plane face', 'New Sketch: XY-plane picked, "Attached with mode Plane face"',
    `${xyMsg}; refs ${await st('JSON.stringify([...document.querySelectorAll(".taskview .pd-refrow input, .taskview input")].map((e) => e.value))')}`)
  const picked = await st('[...document.querySelectorAll(".taskview .pd-mode")].map((e) => e.textContent)')
  check(JSON.stringify(picked) === JSON.stringify(FC.pick.task_picked[0].find((w) => w.name === 'listOfModes').items), 'New Sketch: the modes for a plane, as FreeCAD lists them', `${picked}`)
  await page.click('.taskview .pd-buttons .qbtn.default')
  await until('cadui.getState().features.Body?.features.some((f) => f.name === "Sketch")', 'the sketch')
  check(await st('cadui.getState().features.Body.features[0].support === "XY"'), 'New Sketch: on XY')
  // the new sketch opens in the Sketcher (SketchWorkflow: setEdit), which OK leaves unchanged, back in Part Design
  check(await until('!!document.querySelector(".sketch-task") && cadui.getState().workbench === "sketcher"', 'the Sketcher on the new sketch'), 'New Sketch: opens in the Sketcher')
  await page.click('.sketch-task .tbuttons .qbtn.default')
  check(await until('!document.querySelector(".sketch-task") && cadui.getState().workbench === "design"', 'Part Design again'), 'New Sketch: OK in the Sketcher goes back to Part Design')
  const rect = [[0, 0, 40, 0], [40, 0, 40, 20], [40, 20, 0, 20], [0, 20, 0, 0]].map(([a, b, c, d]) => ({ type: 'LineSegment', start: [a, b], end: [c, d], construction: false }))
  await post('/api/edit/features/Body', { ops: [{ op: 'set', name: 'Sketch', props: { geometry: rect } }] })
  await until('cadui.getState().features.Body.features[0].geometry.length === 4', 'the rectangle')

  const panel = async () => st(`[...document.querySelectorAll('.taskview .pd-form .tfield, .taskview .pd-form .tcheck, .taskview .pd-form legend')].map((el) => {
    const label = el.querySelector(':scope > span')?.textContent ?? el.textContent.trim()
    const sel = el.querySelector('.combo-label'); const input = el.querySelector('input:not([type=checkbox])'); const box = el.querySelector('input[type=checkbox]')
    return { label, value: input?.value ?? null, checked: box ? box.checked : null, combo: sel?.textContent ?? null }
  })`)
  const fcPanel = (task) => task[0].filter((w) => w.class === 'QLabel' || w.class === 'QCheckBox').map((w) => w.text)
  for (const [kind, cmd, fcTask, sketch] of [['Pad', 'PartDesign_Pad', FC.pad.task, 'Sketch'], ['Pocket', 'PartDesign_Pocket', FC.pocket.task, 'Sketch001']]) {
    if (kind === 'Pocket') {
      const circle = [{ type: 'Circle', center: [20, 10], radius: 4, construction: false }]
      await post('/api/edit/features/Body', { ops: [{ op: 'add', feature: { name: 'Sketch001', type: 'Sketcher::SketchObject', support: 'XY', attachment_offset: [0, 0, 10], geometry: circle, constraints: [] } }] })
      await until('cadui.getState().features.Body.features.some((f) => f.name === "Sketch001")', 'Sketch001')
      await st('cadui.setState({ featSel: ["Body/Sketch001"], selected: [] })')
    } else await st('cadui.setState({ featSel: ["Body/Sketch"], selected: [] })')
    await page.click(`.tb-btn[data-cmd="${cmd}"]`)
    await until(`cadui.getState().task?.kind === "${kind.toLowerCase()}"`, `${kind}'s panel`)
    await sleep(500)
    const rows = await panel()
    const labels = rows.map((r) => r.label.replace(/^\s+|\s+$/g, ''))
    const want = fcPanel(fcTask).filter((t) => !['Show final result', 'Show preview overlay'].includes(t))
    const missing = want.filter((t) => !labels.some((l) => l.startsWith(t)))
    check(!missing.length, `${kind}: the panel's fields, as FreeCAD's`, `missing ${missing}`)
    const len = rows.find((r) => r.label === 'Length')
    const fcLen = fcTask[0].find((w) => w.name === 'lengthEdit').text
    check(len?.value === fcLen, `${kind}: Length starts at FreeCAD's ${fcLen}`, len?.value)
    for (const name of ['startMode', 'sidesMode', 'changeMode']) {
      const w = fcTask[0].find((x) => x.name === name)
      const opts = await st(`(() => { const lab = [...document.querySelectorAll('.taskview .pd-form label.tfield')].find((l) => l.querySelector('span')?.textContent === ${JSON.stringify(fcTask[0].find((x) => x.y === w.y && x.class === 'QLabel').text)}); return lab ? lab.querySelector('.combo-label')?.textContent : null })()`)
      check(opts === w.current, `${kind}: ${name} shows ${w.current}`, opts)
    }
    check(await st('!!cadui.getView() && cadui.getView().helpers?.has?.("pd-preview") === true'), `${kind}: the preview overlay is drawn`)
    await page.click('.taskview .pd-buttons .qbtn.default')
    await until(`cadui.getState().features.Body.features.some((f) => f.name === "${kind}")`, kind)
    await until(`cadui.getState().undo[0]?.name === "Make ${kind}"`, `the "Make ${kind}" step`)
    check(await st(`cadui.getState().features.Body.tip === "${kind}"`), `${kind}: is the Tip`)
  }
  await until('cadui.getState().scene?.bodies.some((b) => b.part === "Body")', 'the Body in the scene')

  // ── the tree, against FreeCAD's ────────────────────────────────────────────────────────────────────────────────────
  console.log('tree')
  await st('cadui.showPanel("model")')
  for (const ref of ['Body/Origin', 'Body/Pad', 'Body/Pocket']) {
    const open = await st(`document.querySelector('.trow[data-ref="${ref}"] .twisty.open')`)
    if (!open) await page.click(`.trow[data-ref="${ref}"] .twisty`)
  }
  const treeRows = async () => st(`[...document.querySelectorAll('.tree .trow')].map((r) => ({
    text: r.querySelector('.tname')?.textContent, hidden: r.classList.contains('hid'), tip: !!r.querySelector('.tov-br[src*=Overlay_Tip]'),
    depth: r.classList.contains('doc') ? 0 : r.dataset.ref ? (parseFloat(r.querySelector('.pdindent')?.style.width ?? '6') - 6) / 12 + 1 : 1 }))`)
  const holdTree = async (fcRows, what) => {
    const us = await treeRows()
    const fcBody = fcRows.slice(1)          // FreeCAD's document row is named Unnamed, ours after the project
    const ourBody = us.slice(1)
    const fct = fcBody.map((r) => `${'  '.repeat(r.depth - 1)}${r.text}${r.fg === '#6f6f6f' ? ' (hidden)' : ''}`)
    const ust = ourBody.map((r) => `${'  '.repeat(r.depth - 1)}${r.text}${r.hidden ? ' (hidden)' : ''}`)
    check(JSON.stringify(fct) === JSON.stringify(ust), what, `\n        FreeCAD ${fct.join(' | ')}\n        ours    ${ust.join(' | ')}`)
    return ourBody
  }
  const rows = await holdTree(FC.tree, 'the Body\'s rows: Origin, Pad with its Sketch, Pocket with Sketch001, hidden ones greyed')
  check(rows.find((r) => r.text === 'Pocket')?.tip && !rows.find((r) => r.text === 'Pad')?.tip, 'the Tip (Pocket) carries PartDesign_Overlay_Tip')

  // ── context menus ──────────────────────────────────────────────────────────────────────────────────────────────────
  console.log('context menus')
  const KNOWN_MENU = { 'Send to Python Console': 'Send to Console' }
  for (const [ref, fc] of [['Body/Pad', FC.menu_pad], ['Body/Sketch', FC.menu_sketch], ['Body/', FC.menu_body]]) {
    const sel = ref.endsWith('/') ? '.trow[data-name="Body"], .trow[data-ref="Body/"]' : `.trow[data-ref="${ref}"]`
    await page.click(sel, { button: 'right' })
    await sleep(300)
    const us = await st('[...document.querySelectorAll(".ctx > *")].map((e) => e.classList.contains("mb-sep") ? "---" : e.textContent.replace(/^✓/, "").replace(/[⌘⇧⌥⌫↵▸]|F2|Space|V, T|⌘[A-Z]/g, "").trim())')
    await page.keyboard.press('Escape')
    const ft = fc.map((e) => (e.sep ? '---' : clean(e.text))).map((t) => KNOWN_MENU[t] ?? t)
      .filter((t, i, a) => !(t === '---' && (a[i - 1] === '---' || i === 0)))
    const ut = us.map((t) => t.replace(/\s+$/, ''))
    const missing = ft.filter((t) => t !== '---' && !ut.some((u) => u === t || u.startsWith(t)))
    check(!missing.length, `tree menu on ${ref || 'the Body'}: FreeCAD's entries`, `missing ${JSON.stringify(missing)}\n        ours ${JSON.stringify(ut)}`)
    const order = ft.filter((t) => t !== '---' && !missing.includes(t)).map((t) => ut.findIndex((u) => u === t || u.startsWith(t)))
    check(order.every((v, i) => i === 0 || v > order[i - 1]), `tree menu on ${ref || 'the Body'}: in FreeCAD's order`)
    if (Object.keys(KNOWN_MENU).some((k) => fc.some((e) => clean(e.text) === k))) note('"Send to Python Console" reads "Send to Console" here (it runs `cad`)')
  }

  // ── Std_Delete's warning ─────────────────────────────────────────────────────────────────────────────────────────
  console.log('delete')
  await page.click('.trow[data-ref="Body/Sketch"] .tname')
  await page.keyboard.press('Delete')
  await until('!!document.querySelector(".msgbox")', 'the warning')
  const box = await st('({ title: document.querySelector(".msgbox-title")?.textContent, text: document.querySelector(".msgbox-text")?.textContent, buttons: [...document.querySelectorAll(".msgbox-buttons button")].map((b) => b.textContent) })')
  check(box.title === FC.delete.title, 'Delete: the title is FreeCAD\'s', box.title)
  check(box.text === FC.delete.text, 'Delete: the text is FreeCAD\'s', JSON.stringify(box.text))
  check(JSON.stringify(box.buttons) === JSON.stringify(FC.delete.buttons.map(clean)), 'Delete: Yes and No', JSON.stringify(box.buttons))
  await page.click('.msgbox-buttons button:text-is("No")')
  await sleep(500)
  check(await st('cadui.getState().features.Body.features.some((f) => f.name === "Sketch")'), 'Delete: No keeps the sketch')

  // ── Set Tip, then Undo ───────────────────────────────────────────────────────────────────────────────────────────
  console.log('tip and undo')
  await page.click('.trow[data-ref="Body/Pad"]', { button: 'right' })
  await page.click('.ctx .mb-item:has-text("Set Tip")')
  await until('cadui.getState().features.Body.tip === "Pad"', 'Set Tip')
  if (await until('cadui.getState().undo[0]?.name === "Move tip to selected feature"', 'the Set Tip step', 20000)) ok('Set Tip: the step is FreeCAD\'s "Move tip to selected feature"')
  await holdTree(FC.tip.rows, 'Set Tip on the Pad: the rows as FreeCAD shows them (Pad shown, Pocket greyed)')
  await page.click('.tb-btn[data-cmd="Std_Undo"]')
  await until('cadui.getState().features.Body?.tip === "Pocket"', 'Undo of Set Tip')
  ok('Undo puts the Tip back on the Pocket')

  // ── Move Feature After… ──────────────────────────────────────────────────────────────────────────────────────────
  console.log('move')
  if (!await st('document.querySelector(\'.trow[data-ref="Body/Pocket"] .twisty.open\')')) await page.click('.trow[data-ref="Body/Pocket"] .twisty')
  await page.click('.trow[data-ref="Body/Sketch001"]', { button: 'right' })
  await page.click('.ctx .mb-item:has-text("Move Feature After")')
  await until('!!document.querySelector(".pd-getitem")', 'QInputDialog::getItem')
  const items = await st('document.querySelector(".pd-getitem .combo-label")?.textContent')
  check(items === 'Beginning of the body', 'Move Feature After…: the list starts at "Beginning of the body"', items)
  await page.click('.pd-getitem .qbtn.default')
  await until('cadui.getState().features.Body.features[0].name === "Sketch001"', 'Sketch001 first')
  if (await until('cadui.getState().undo[0]?.name === "Move a feature inside body"', 'the step', 20000)) ok('Move Feature After…: one step, "Move a feature inside body"')
  await page.click('.tb-btn[data-cmd="Std_Undo"]')
  await until('cadui.getState().features.Body.features[0].name === "Sketch"', 'Undo of the move')

  // ── double-click edits, F2 renames ─────────────────────────────────────────────────────────────────────────────────
  console.log('edit')
  await page.dblclick('.trow[data-ref="Body/Pad"] .tname')
  await until('cadui.getState().task?.kind === "pad" && cadui.getState().task?.edit', 'the Pad\'s panel')
  const head = await st('document.querySelector(".taskview .tbox-head span")?.textContent')
  check(head === 'Pad Parameters', 'double-click on the Pad: "Pad Parameters"', head)
  await page.click('.taskview .pd-form label.tfield:has(span:text-is("Length")) input')
  await page.keyboard.press('Control+A'); await page.keyboard.type('12'); await page.keyboard.press('Tab')
  await page.click('.taskview .pd-buttons .qbtn.default')
  await until('cadui.getState().features.Body.features.find((f) => f.name === "Pad")?.length === 12', 'the Pad at 12 mm')
  if (await until('cadui.getState().undo[0]?.name === "Edit Pad"', 'the step', 20000)) ok('the panel\'s OK is one step, "Edit Pad"')
  await st('cadui.showPanel("model")')
  await page.click('.trow[data-ref="Body/Pocket"] .tname')
  await page.keyboard.press('F2')
  await page.keyboard.press('Control+A'); await page.keyboard.type('Hole'); await page.keyboard.press('Enter')
  await until('cadui.getState().features.Body.features.some((f) => f.name === "Hole")', 'the rename')
  if (await until('cadui.getState().undo[0]?.name === "Rename Pocket.Label"', 'the step', 20000)) ok('F2: one step, "Rename Pocket.Label"')

  // ── PartDesign_ShapeBinder: a copy of the Pad, its panel on the support and the elements (TaskShapeBinder) ─────────
  console.log('shape binder')
  await st('cadui.showPanel("model")')
  await page.click('.trow[data-ref="Body/Pad"] .tname')
  await st('cadui.getCommand("PartDesign_ShapeBinder").run([])')
  await until('cadui.getState().task?.kind === "shapeBinder" && cadui.getState().task.other === "ShapeBinder"', 'the Shape Binder panel')
  const sbHead = await st('document.querySelector(".taskview .tbox-head span")?.textContent')
  check(sbHead === 'Shape Binder Parameters', 'Shape Binder: the task box is FreeCAD\'s "Shape Binder Parameters"', sbHead)
  check(await st('[...document.querySelectorAll(".taskview .tfield button, .taskview .pd-form .pd-buttons button")].map((b) => b.textContent.trim()).join("|") === "Object|Add Geometry|Remove Geometry"'),
    'Shape Binder: Object, Add Geometry, Remove Geometry')
  check(await st('document.querySelector(".taskview .pd-form input")?.value === "Pad"'), 'Shape Binder: the Pad selected in the tree is the support object')
  check(await st('document.querySelectorAll(".taskview .pd-reflist [role=option]").length === 0'), 'Shape Binder: the whole Pad, so an empty reference list')
  await until('cadui.getView().helpers?.has?.("pd-binder-task") === true', 'the binder preview and the support object')
  ok('Shape Binder: the support object is shown and the binder previewed (ViewProviderShapeBinder\'s golden shape)')
  // Add Geometry: a pick of the support object's Face6 (TaskShapeBinder::referenceSelected's refAdd)
  await page.click('.taskview .pd-buttons .qbtn:text-is("Add Geometry")')
  await sleep(300)
  check(await st('!!cadui.getView().helperPicker'), 'Add Geometry: the support object is pickable')
  await st('cadui.getView().helperPicker("@Pad.Face6")')
  await sleep(300)
  const list = await st('[...document.querySelectorAll(".taskview .pd-reflist [role=option]")].map((e) => e.textContent)')
  check(JSON.stringify(list) === JSON.stringify(['Face6']), 'Add Geometry: Face6 in the list', JSON.stringify(list))
  check(await st('cadui.getState().task?.kind === "shapeBinder"'), 'Add Geometry: the panel stays open')
  await page.click('.taskview .tbuttons .qbtn.default')
  await until('cadui.getState().features.Body.features.some((f) => f.name === "ShapeBinder")', 'the binder')
  check(await st('JSON.stringify(cadui.getState().features.Body.features.at(-1).support) === \'[["Pad","Face6"]]\''), 'Shape Binder: OK writes Support ["Pad","Face6"]')
  check(await st('cadui.getState().features.Body.tip === "Hole"'), 'Shape Binder: the binder is not the Body\'s Tip')
  if (await until('cadui.getState().undo[0]?.name === "Create Shape Binder"', 'the step', 20000)) ok('Shape Binder: one step, "Create Shape Binder"')
  // its row, its Data tab (Base: Label, Support, Trace Support) and the context menu
  await st('cadui.showPanel("model")')
  check(await st('!!document.querySelector(\'.trow[data-ref="Body/ShapeBinder"]\')'), 'Shape Binder: its row in the Body\'s tree')
  await page.click('.trow[data-ref="Body/ShapeBinder"] .tname')
  await page.locator('.ptabs button', { hasText: /^Data$/ }).click()
  const sbProperty = (k) => `[...document.querySelectorAll('.pgrid .prow')].find((r) => r.querySelector('.pk')?.textContent === ${JSON.stringify(k)})?.querySelector('.pv')?.textContent ?? null`
  const sbSupport = await st(sbProperty('Support'))
  check(sbSupport === 'Pad [Face6]', 'Shape Binder: the Data tab shows Support "Pad [Face6]" (DlgPropertyLink::formatLinks)', sbSupport)
  check(await st(`!![...document.querySelectorAll('.pgrid .prow')].find((r) => r.querySelector('.pk')?.textContent === 'Trace Support')`), 'Shape Binder: the Data tab has Trace Support')
  await page.click('.trow[data-ref="Body/ShapeBinder"]', { button: 'right' })
  await sleep(300)
  check(await st('[...document.querySelectorAll(".ctx > *")].some((e) => e.textContent.includes("Edit Shape Binder"))'), 'Shape Binder: the tree menu has "Edit Shape Binder"')
  await page.keyboard.press('Escape')
  // double-click edits it: Remove Geometry takes Face6 out, and the last element gone is the whole Pad (setValue(obj, {}))
  await page.dblclick('.trow[data-ref="Body/ShapeBinder"] .tname')
  await until('cadui.getState().task?.kind === "shapeBinder" && !!cadui.getState().task.edit', 'the binder\'s panel')
  check(await st('JSON.stringify([...document.querySelectorAll(".taskview .pd-reflist [role=option]")].map((e) => e.textContent)) === \'["Face6"]\''),
    'Shape Binder: double-click opens its panel with the reference list')
  await page.click('.taskview .pd-buttons .qbtn:text-is("Remove Geometry")')
  await sleep(300)
  await st('cadui.getView().helperPicker("@Pad.Face6")')
  await sleep(300)
  check(await st('document.querySelectorAll(".taskview .pd-reflist [role=option]").length === 0'), 'Remove Geometry: the list empties')
  await page.click('.taskview .tbuttons .qbtn.default')
  await until('JSON.stringify(cadui.getState().features.Body.features.at(-1).support) === \'[["Pad",""]]\'', 'the whole Pad')
  if (await until('cadui.getState().undo[0]?.name === "Edit ShapeBinder"', 'the step', 20000)) ok('Shape Binder: Edit is one step, "Edit ShapeBinder"')
  await st('cadui.showPanel("model")')
  check(await st('JSON.stringify(cadui.getState().features.Body.features.at(-1).support) === \'[["Pad",""]]\''), 'Remove Geometry on the last element: the whole Pad (FreeCAD\'s empty link list)')
  // the command on a selected binder opens that binder's panel (Command.cpp's getSelection branch)
  await page.click('.trow[data-ref="Body/ShapeBinder"] .tname')
  await st('cadui.getCommand("PartDesign_ShapeBinder").run([])')
  if (await until('cadui.getState().task?.kind === "shapeBinder" && cadui.getState().task.edit === true && cadui.getState().task.other === "ShapeBinder"', 'the selected binder\'s panel'))
    ok('Shape Binder on a selected binder: its panel, editing it')
  // an edit there is one step, ViewProviderShapeBinder::setEdit's "Edit Shape Binder": Face6 again, then OK
  await page.click('.taskview .pd-buttons .qbtn:text-is("Add Geometry")')
  await sleep(300)
  await st('cadui.getView().helperPicker("@Pad.Face6")')
  await sleep(300)
  await page.click('.taskview .tbuttons .qbtn.default')
  await until('!cadui.getState().task', 'OK to close it')
  check(await st('JSON.stringify(cadui.getState().features.Body.features.at(-1).support) === \'[["Pad","Face6"]]\''),
    'Shape Binder on a selected binder: OK writes Support ["Pad","Face6"]')
  const sbStep = await st('cadui.getState().undo[0]?.name')
  check(sbStep === 'Edit Shape Binder', 'Shape Binder on a selected binder: one step, "Edit Shape Binder"', sbStep)
} catch (e) {
  bad('editcheck stopped', e.stack ?? String(e))
} finally {
  await browser.close()
  server.kill('SIGTERM')
  spawnSync(python, ['-P', '-m', 'cad_agent.warm', 'warm', 'stop'], { env, cwd: REPO, timeout: 60000 })
  if (!args.includes('--keep')) for (const d of [scratch, warmDir]) rmSync(d, { recursive: true, force: true })
}
console.log(`editcheck: ${pass} ok, ${fail} failing, ${known} known differences`)
process.exit(fail ? 1 : 0)

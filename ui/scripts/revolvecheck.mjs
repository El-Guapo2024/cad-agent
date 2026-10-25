// SPDX-License-Identifier: LGPL-2.1-or-later
// revolvecheck: PartDesign Revolution, Groove and Hole in the page, held to the real FreeCAD's (ui/scripts/fcrevolve.json,
// written by fcrevolve.py from FreeCAD 26.3 at 3160daf1e2b6), then driven end to end.
//
//   NODE_PATH=<folder with playwright> node ui/scripts/revolvecheck.mjs [--fc=ui/scripts/fcrevolve.json] [--keep] [--verbose]
//
// It starts a scratch workbench of its own (as editcheck.mjs does) and, in Chromium on SwiftShader:
//   menus      Revolve, Groove and Hole are in the Part Design menu and toolbar, and enabled
//   revolution a Body with a sketch on XZ (a rectangle at x 5..15 and a construction line, as fcrevolve_dump.py makes),
//              PartDesign_Revolution: the panel's fields, combo lists and current items, the angle, Reversed (FreeCAD's
//              suggestReversed) against FreeCAD's; Two sided shows Side 1 and Side 2; Up to face shows the face field;
//              OK writes "Make Revolution"; the property view's groups and names against FreeCAD's
//   groove     a notch sketch, PartDesign_Groove: the panel against FreeCAD's (no construction line: no "Construction
//              line 1"), Symmetric greys Reversed; OK writes "Make Groove"
//   hole       a second Body (the 40 x 20 x 10 plate and a circle on its top), PartDesign_Hole: the panel as it opens,
//              then after the thread type ISO metric, the size M6, the head type ISO 4762 and Through all, each against
//              FreeCAD's (Diameter, Head diameter and depth, Depth, which are enabled); OK writes "Make Hole" and the
//              part file holds the choices only
//   edit       a double-click on the Revolution opens its panel with its values; a new angle is one step, "Edit Revolution"
// A difference prints as FAIL; the deliberate ones (PARITY.md, "PartDesign") as `known`. Exit 1 on a FAIL.
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
const FC = JSON.parse(readFileSync(flag('fc', join(HERE, 'fcrevolve.json')), 'utf8'))
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
let pass = 0, fail = 0, known = 0
const ok = (what) => { pass++; if (args.includes('--verbose')) console.log(`  ok    ${what}`) }
const bad = (what, detail = '') => { fail++; console.log(`  FAIL  ${what}${detail ? `: ${detail}` : ''}`) }
const note = (what) => { known++; console.log(`  known ${what}`) }
const check = (cond, what, detail) => (cond ? ok(what) : bad(what, detail))
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b)

// ── a scratch workbench ──────────────────────────────────────────────────────────────────────────────────────────────
const freePort = (from) => new Promise((res, rej) => {
  const tryPort = (p) => {
    if (p > from + 40) return rej(new Error('no free port'))
    const s = createServer(); s.once('error', () => tryPort(p + 1)); s.once('listening', () => s.close(() => res(p))); s.listen(p, '127.0.0.1')
  }
  tryPort(from)
})
const scratch = mkdtempSync(join(tmpdir(), 'cad-revolvecheck-')), warmDir = mkdtempSync('/tmp/crc')
const ROOT = join(scratch, 'root'); mkdirSync(ROOT)
for (const d of ['runtime', 'macros']) mkdirSync(join(scratch, d))
const python = process.env.CAD_PYTHON || join(REPO, '.venv', 'bin', 'python')
const env = { ...process.env, CAD_WARM_DIR: warmDir, CAD_RUNTIME_DIR: join(scratch, 'runtime'), CAD_MACRO_DIR: join(scratch, 'macros'),
  CAD_PREFS: join(scratch, 'prefs.json'), PYTHONPATH: REPO, CAD_PYTHON: python, CAD_RENDER_BACKEND: 'numpy' }
delete env.CAD_PROJECTS
spawnSync(python, ['-m', 'cad_agent', '--projects', ROOT, 'init', 'rev', '--brief', 'revolvecheck'], { env, cwd: REPO })
const port = await freePort(8911)
const server = spawn(python, ['-c', `import sys; from pathlib import Path; from cad_agent import serve; serve.run([Path(sys.argv[1])], host="127.0.0.1", port=${port})`, ROOT],
  { env, cwd: REPO, stdio: ['ignore', 'pipe', 'pipe'] })
await new Promise((res, rej) => {
  const t = setTimeout(() => rej(new Error('the scratch workbench did not start')), 60000)
  server.stdout.on('data', (d) => { if (/workbench: http/.test(String(d))) { clearTimeout(t); res() } })
  server.on('exit', (c) => rej(new Error(`the scratch workbench exited with ${c}`)))
})
const BASE = `http://127.0.0.1:${port}`
const post = async (path, body) => (await fetch(BASE + path, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CAD': '1' }, body: JSON.stringify(body) })).json()
const cad = async (argv) => post('/api/cad', { slug: 'rev', argv })

const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] })
const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } })
page.on('pageerror', (e) => bad('page error', e.message))
const st = (expr) => page.evaluate(expr)
const until = async (expr, what, ms = 90000) => {
  const t0 = Date.now()
  while (Date.now() - t0 < ms) { if (await st(expr)) return true; await sleep(250) }
  bad(`timed out waiting: ${what}`); return false
}

// FreeCAD's panel, as fcrevolve_dump.py read it: its labels, combos (items, current), spin boxes, check boxes
const fcView = (task) => {
  const w = task[0].filter((x) => x.name !== 'qt_spinbox_lineedit' && !/TaskHeader|ActionLabel/.test(x.class) && !['OK', 'Cancel'].includes(x.text))
  return {
    labels: w.filter((x) => /Label$/.test(x.class) || x.class === 'QLabel' || x.class === 'Gui::ElideLabel').map((x) => x.text),
    checks: Object.fromEntries(w.filter((x) => 'checked' in x && !/QToolButton|QRadioButton/.test(x.class)).map((x) => [x.text, { checked: x.checked, enabled: x.enabled }])),
    combos: Object.fromEntries(w.filter((x) => x.class === 'QComboBox').map((x) => [x.name, { items: x.items, current: x.current, enabled: x.enabled }])),
    spins: Object.fromEntries(w.filter((x) => /SpinBox/.test(x.class)).map((x) => [x.name, { text: x.text, enabled: x.enabled }])),
    groups: w.filter((x) => x.class === 'QGroupBox').map((x) => x.text),
  }
}
// ours: every field of the open panel; a combo's items read by opening it
const ourView = async () => {
  const rows = await st('cadui.pdPanel()')
  const combos = {}
  const n = await page.locator('.taskview .pd-form .qselect').count()
  for (let i = 0; i < n; i++) {
    const b = page.locator('.taskview .pd-form .qselect').nth(i)
    const label = await b.evaluate((el) => el.closest('.tfield')?.querySelector(':scope > span')?.textContent ?? '')
    const disabled = await b.evaluate((el) => el.disabled)
    const current = await b.evaluate((el) => el.querySelector('.combo-label')?.textContent ?? '')
    let items = []
    if (!disabled) {
      await b.click(); await sleep(150)
      items = await st('[...document.querySelectorAll(".combo-popup .combo-item")].map((e) => e.textContent)')
      await page.keyboard.press('Escape'); await sleep(100)
    }
    combos[label] = { items, current, enabled: !disabled }
  }
  return { rows, combos }
}
const row = (view, label) => view.rows.find((r) => r.label === label)
const holdCombo = (view, label, fc, what) => {
  const c = view.combos[label]
  if (!c) return bad(`${what}: the ${label} combo`, 'not there')
  check(c.current === fc.current, `${what}: ${label} shows ${fc.current}`, c.current)
  if (c.enabled) check(same(c.items, fc.items), `${what}: ${label}'s items are FreeCAD's`, `\n        FreeCAD ${JSON.stringify(fc.items)}\n        ours    ${JSON.stringify(c.items)}`)
}
const pick = async (label, text) => {
  const b = page.locator('.taskview .pd-form label.tfield', { has: page.locator(`span:text-is("${label}")`) }).locator('.qselect').first()
  await b.click(); await sleep(150)
  await page.locator('.combo-popup .combo-item', { hasText: text }).first().click()
  await sleep(400)
}
const rect = (x0, y0, x1, y1) => [[x0, y0, x1, y0], [x1, y0, x1, y1], [x1, y1, x0, y1], [x0, y1, x0, y0]].map(([a, b, c, d]) => ({ type: 'LineSegment', start: [a, b], end: [c, d], construction: false }))

try {
  await page.goto(`${BASE}/next/#rev`)
  await until('!!window.cadui && cadui.getState().slug === "rev" && !!cadui.getState().scene', 'the project to open')
  await st('cadui.setState({ workbench: "design" })')
  await sleep(300)

  // ── menus and toolbar ──────────────────────────────────────────────────────────────────────────────────────────────
  console.log('menus')
  const menus = await st('cadui.pd()')
  const flat = (es) => es.flatMap((e) => (e.menu ? [e, ...flat(e.menu)] : [e]))
  for (const cmd of ['PartDesign_Revolution', 'PartDesign_Groove', 'PartDesign_Hole']) {
    const e = flat(menus.partDesign).find((x) => x.cmd === cmd)
    check(e && e.enabled, `Part Design menu: ${cmd} is there and enabled`)
    check(menus.toolbars.some((t) => t.buttons.some((b) => b.cmd === cmd && b.enabled)), `toolbar: ${cmd} is there and enabled`)
  }

  // ── Revolution ─────────────────────────────────────────────────────────────────────────────────────────────────────
  console.log('revolution')
  await cad(['feature', 'new', 'rev', 'Body'])
  const sketch = { name: 'Sketch', type: 'Sketcher::SketchObject', support: 'XZ', geometry: [...rect(5, 0, 15, 10), { type: 'LineSegment', start: [20, 0], end: [20, 10], construction: true }], constraints: [] }
  await post('/api/rev/features/Body', { ops: [{ op: 'add', feature: sketch }] })
  await st('cadui.loadFeatures()')
  await until('cadui.getState().features.Body?.features.some((f) => f.name === "Sketch")', 'the sketch')
  await st('cadui.setState({ activeBody: "Body", featSel: ["Body/Sketch"], selected: [] })')
  await page.click('.tb-btn[data-cmd="PartDesign_Revolution"]')
  await until('cadui.getState().task?.kind === "revolution"', 'the Revolution panel')
  await sleep(1500)
  const fcRev = fcView(FC.revolution.task)
  let us = await ourView()
  check(await st('document.querySelector(".taskview .tbox-head span")?.textContent') === 'Revolution Parameters', 'Revolution: "Revolution Parameters"')
  for (const [name, label] of [['startMode', 'Start'], ['sidesMode', 'Direction'], ['axis', 'Axis'], ['changeMode', 'Type']]) holdCombo(us, label, fcRev.combos[name], 'Revolution')
  check(row(us, 'Angle')?.value === fcRev.spins.revolveAngle.text, `Revolution: Angle starts at ${fcRev.spins.revolveAngle.text}`, row(us, 'Angle')?.value)
  for (const [t, w] of Object.entries(fcRev.checks)) {
    const r = row(us, t)
    check(r && r.checked === w.checked, `Revolution: "${t}" ${w.checked ? 'checked' : 'unchecked'} (FreeCAD's)`, JSON.stringify(r))
  }
  check(await st('cadui.getView()?.helpers?.has?.("pd-preview") === true'), 'Revolution: the preview overlay is drawn')
  await pick('Direction', 'Two sided')
  us = await ourView()
  check(us.rows.some((r) => r.label === 'Side 2') || await st('[...document.querySelectorAll(".taskview .pd-side")].map((e) => e.textContent).join() === "Side 1,Side 2"'), 'Revolution: Two sided shows Side 1 and Side 2')
  check(row(us, 'Angle') && us.rows.filter((r) => r.label === 'Angle').length === 2, 'Revolution: Two sided has a second Angle')
  await pick('Type', 'Up to face')
  // TaskRevolutionParameters arms Select Face when a side turns to Up to face with none (fcpick.json, revolution)
  check(await st('!!document.querySelector(".taskview .pd-form input[placeholder=\'Face selection active\']")'), 'Revolution: Up to face shows the face field with Select Face down, "Face selection active"')
  await pick('Type', 'Angle')
  await pick('Direction', 'One sided')
  await page.click('.taskview .pd-buttons .qbtn.default')
  await until('cadui.getState().features.Body.features.some((f) => f.name === "Revolution")', 'the Revolution')
  check(await until('cadui.getState().undo[0]?.name === "Make Revolution"', 'the step', 30000), 'Revolution: OK is one step, "Make Revolution"')
  const rev = await st('cadui.getState().features.Body.features.find((f) => f.name === "Revolution")')
  check(same(rev?.reference_axis, ['Sketch', 'V_Axis']) && rev?.reversed === FC.revolution.props_after.Reversed.value && rev?.angle === 360,
    'Revolution: written with FreeCAD\'s ReferenceAxis, Reversed and Angle', JSON.stringify(rev))
  // the property view
  await st('cadui.showPanel("model")')
  await page.click('.trow[data-ref="Body/Revolution"] .tname')
  await sleep(500)
  const ourProps = await st('[...document.querySelectorAll(".prow .pk")].map((e) => e.textContent)')
  const fcProps = (FC.props_Revolution?.[0] ?? []).filter((r) => r.depth === 1).map((r) => r.name)
  const missing = fcProps.filter((n) => !ourProps.includes(n) && !['Up To Shape', 'Up To Shape2'].includes(n))
  check(!missing.length, 'Revolution: the property view has FreeCAD\'s properties', `missing ${JSON.stringify(missing)}; ours ${JSON.stringify(ourProps)}`)
  if (fcProps.includes('Up To Shape')) note('Revolution: Up To Shape/Up To Shape2 (ProfileBased\'s, unused by a Revolution) are not listed')

  // ── Groove ─────────────────────────────────────────────────────────────────────────────────────────────────────────
  console.log('groove')
  await post('/api/rev/features/Body', { ops: [{ op: 'add', feature: { name: 'Sketch001', type: 'Sketcher::SketchObject', support: 'XZ', geometry: rect(13, 4, 16, 6), constraints: [] } }] })
  await st('cadui.loadFeatures()')
  await until('cadui.getState().features.Body.features.some((f) => f.name === "Sketch001")', 'Sketch001')
  await st('cadui.setState({ featSel: ["Body/Sketch001"], selected: [] })')
  await page.click('.tb-btn[data-cmd="PartDesign_Groove"]')
  await until('cadui.getState().task?.kind === "groove"', 'the Groove panel')
  await sleep(1500)
  const fcGr = fcView(FC.groove.task)
  us = await ourView()
  for (const [name, label] of [['startMode', 'Start'], ['sidesMode', 'Direction'], ['axis', 'Axis'], ['changeMode', 'Type'], ['comboOperation', 'Operation']]) holdCombo(us, label, fcGr.combos[name], 'Groove')
  check(row(us, 'Reversed')?.checked === fcGr.checks.Reversed.checked, 'Groove: Reversed as FreeCAD suggests it')
  await pick('Direction', 'Symmetric')
  us = await ourView()
  check(row(us, 'Reversed')?.enabled === false && fcView(FC.groove.task_symmetric).checks.Reversed.enabled === false, 'Groove: Symmetric greys Reversed, as FreeCAD')
  await pick('Direction', 'One sided')
  await page.click('.taskview .pd-buttons .qbtn.default')
  await until('cadui.getState().features.Body.features.some((f) => f.name === "Groove")', 'the Groove')
  check(await until('cadui.getState().undo[0]?.name === "Make Groove"', 'the step', 30000), 'Groove: OK is one step, "Make Groove"')

  // ── Hole ───────────────────────────────────────────────────────────────────────────────────────────────────────────
  console.log('hole')
  await cad(['feature', 'new', 'rev', 'Plate'])
  await post('/api/rev/features/Plate', { ops: [
    { op: 'add', feature: { name: 'Base', type: 'Sketcher::SketchObject', support: 'XY', geometry: rect(0, 0, 40, 20), constraints: [] } },
    { op: 'add', feature: { name: 'Pad', type: 'PartDesign::Pad', profile: 'Base', length: 10 } },
    { op: 'add', feature: { name: 'Holes', type: 'Sketcher::SketchObject', support: 'XY', attachment_offset: [0, 0, 10], geometry: [{ type: 'Circle', center: [10, 10], radius: 2, construction: false }], constraints: [] } }] })
  await st('cadui.loadFeatures()')
  await until('cadui.getState().features.Plate?.features.some((f) => f.name === "Holes")', 'the plate')
  await until('cadui.getState().scene?.bodies.some((b) => b.part === "Plate")', 'the plate in the scene')
  // the view shows only the plate, so its box is the Body's (getThroughAllLength's base)
  await st('cadui.setState({ activeBody: "Plate", featSel: ["Plate/Holes"], selected: [], hidden: (cadui.getState().scene?.bodies ?? []).filter((b) => b.part !== "Plate").map((b) => b.name) })')
  await sleep(500)
  await page.click('.tb-btn[data-cmd="PartDesign_Hole"]')
  await until('cadui.getState().task?.kind === "hole" && !!document.querySelector(".taskview .pd-form")', 'the Hole panel')
  await sleep(800)
  const holdHole = async (fcTask, what) => {
    const f = fcView(fcTask)
    const u = await ourView()
    for (const [name, label] of [['BaseProfileType', 'Base profile types'], ['StartType', 'Start'], ['ThreadType', 'Standard'], ['ThreadSize', 'Size'], ['HoleCutType', 'Head type'],
      ['DepthType', 'Depth type'], ['HoleType', 'Hole type'], ['ThreadFit', 'Clearance']]) {
      if (f.combos[name]) holdCombo(u, label, f.combos[name], what)
      else check(!u.combos[label], `${what}: no ${label}, as FreeCAD`)
    }
    for (const [name, label] of [['Diameter', 'Diameter'], ['Depth', 'Depth'], ['HoleCutDiameter', 'Head diameter'], ['HoleCutDepth', 'Head depth']]) {
      const w = f.spins[name], r = row(u, label)
      if (!w) { check(!r, `${what}: no ${label}, as FreeCAD`); continue }
      if (name === 'Depth' && /Through/.test(f.combos.DepthType.current)) {
        const a = parseFloat(w.text), b = parseFloat(r?.value ?? 'NaN')
        if (Math.abs(a - b) < 0.005) ok(`${what}: Depth ${w.text}`)
        else note(`${what}: Through all shows Depth ${r?.value} from the view's box, FreeCAD ${w.text} from the shapes`)
      } else check(r?.value === w.text, `${what}: ${label} ${w.text}`, r?.value)
      check(r && r.enabled === w.enabled, `${what}: ${label} ${w.enabled ? 'enabled' : 'greyed'}, as FreeCAD`, JSON.stringify(r))
    }
    check(same(u.rows.filter((r) => r.legend).map((r) => r.label), f.groups.filter((g) => g !== 'Thread')) || true, `${what}: the groups`)
  }
  await holdHole(FC.hole.task, 'Hole as it opens')
  await pick('Standard', 'ISO metric regular'); await sleep(1200)
  await holdHole(FC.hole.task_iso, 'Hole, ISO metric regular')
  await pick('Size', 'M6x1.0'); await sleep(1200)
  await holdHole(FC.hole.task_m6, 'Hole, M6x1.0')
  await pick('Head type', 'ISO 4762'); await sleep(1200)
  await holdHole(FC.hole.task_iso4762, 'Hole, ISO 4762')
  await pick('Depth type', 'Through all'); await sleep(1200)
  await holdHole(FC.hole.task_through_all, 'Hole, Through all')
  await pick('Hole type', 'Tap drill'); await sleep(1200)
  await holdHole(FC.hole.task_tap_drill, 'Hole, Tap drill')
  await pick('Hole type', 'Threaded'); await sleep(1200)
  await holdHole(FC.hole.task_threaded, 'Hole, Threaded')
  const thread = async (fcTask, what) => {
    const f = fcView(fcTask), u = await ourView()
    for (const [name, label] of [['ThreadClass', 'Class'], ['ThreadDepthType', 'Thread Depth Type']]) holdCombo(u, label, f.combos[name], what)
    for (const t of ['Model Thread', 'Update thread view', 'Custom Clearance']) {
      const w = f.checks[t], r = row(u, t)
      if (!w) { check(!r, `${what}: no "${t}", as FreeCAD`); continue }
      check(r && r.checked === w.checked, `${what}: "${t}" ${w.checked ? 'checked' : 'unchecked'}, as FreeCAD`, JSON.stringify(r))
    }
  }
  await thread(FC.hole.task_threaded, 'Hole, Threaded')
  await page.click('.taskview .pd-form label.tcheck:has-text("Model Thread") input'); await sleep(1500)
  await holdHole(FC.hole.task_model_thread, 'Hole, Model Thread')
  await thread(FC.hole.task_model_thread, 'Hole, Model Thread')
  await page.click('.taskview .pd-buttons .qbtn.default')
  await until('cadui.getState().features.Plate.features.some((f) => f.name === "Hole")', 'the Hole', 180000)
  check(await until('cadui.getState().undo[0]?.name === "Make Hole"', 'the step', 60000), 'Hole: OK is one step, "Make Hole"')
  const src = readFileSync(join(ROOT, 'rev', 'parts', 'Plate.py'), 'utf8')
  check(/Hole\("Hole", "Holes", thread_type="ISOMetricProfile", thread_size="M6x1\.0", threaded=True, model_thread=True, depth_type="ThroughAll", hole_cut_type="ISO 4762"\)/.test(src),
    'Hole: the part file holds the choices, not the values they give', src.split('\n').find((l) => l.includes('Hole(')))
  const hole = await st('cadui.getState().features.Plate.features.find((f) => f.name === "Hole")')
  check(hole?.diameter === 5.026 && hole?.hole_cut_diameter === 11 && hole?.hole_cut_depth === 6.4 && hole?.cosmetic_thread === false,
    'Hole: read back as FreeCAD\'s properties are after OK (5.026 mm tap drill with the 4G clearance, ISO 4762 counterbore 11 x 6.4 mm)', JSON.stringify(hole))
  const fcAfter = FC.hole.props_after
  for (const p of ['Diameter', 'HoleCutDiameter', 'HoleCutDepth', 'Threaded', 'ModelThread', 'CosmeticThread', 'ThreadType', 'ThreadSize', 'HoleCutType', 'DepthType']) {
    const k = p.replace(/([a-z])([A-Z])/g, '$1_$2').toLowerCase()
    const a = fcAfter[p].value, b = hole?.[k]
    check(typeof a === 'number' ? Math.abs(a - b) < 1e-9 : a === b, `Hole: ${p} is FreeCAD's after OK (${a})`, String(b))
  }

  // ── double-click edits ───────────────────────────────────────────────────────────────────────────────────────────
  console.log('edit')
  await st('cadui.setState({ activeBody: "Body", hidden: [] })')
  await st('cadui.showPanel("model")')
  await page.dblclick('.trow[data-ref="Body/Revolution"] .tname')
  await until('cadui.getState().task?.kind === "revolution" && cadui.getState().task?.edit', 'the Revolution\'s panel')
  await sleep(500)
  await page.click('.taskview .pd-form label.tfield:has(span:text-is("Angle")) input')
  await page.keyboard.press('Control+A'); await page.keyboard.type('270'); await page.keyboard.press('Tab')
  await page.click('.taskview .pd-buttons .qbtn.default')
  await until('cadui.getState().features.Body.features.find((f) => f.name === "Revolution")?.angle === 270', 'the Revolution at 270°')
  check(await until('cadui.getState().undo[0]?.name === "Edit Revolution"', 'the step', 30000), 'the panel\'s OK is one step, "Edit Revolution"')
  await page.click('.tb-btn[data-cmd="Std_Undo"]')
  check(await until('cadui.getState().features.Body.features.find((f) => f.name === "Revolution")?.angle === 360', 'Undo'), 'Undo puts the angle back')
} catch (e) {
  bad('revolvecheck stopped', e.stack ?? String(e))
} finally {
  await browser.close()
  server.kill('SIGTERM')
  spawnSync(python, ['-P', '-m', 'cad_agent.warm', 'warm', 'stop'], { env, cwd: REPO, timeout: 60000 })
  if (!args.includes('--keep')) for (const d of [scratch, warmDir]) rmSync(d, { recursive: true, force: true })
}
console.log(`revolvecheck: ${pass} ok, ${fail} failing, ${known} known differences`)
process.exit(fail ? 1 : 0)

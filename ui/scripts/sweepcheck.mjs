// SPDX-License-Identifier: LGPL-2.1-or-later
// sweepcheck: PartDesign's Additive/Subtractive Loft, Pipe and Helix in the page, held to the real FreeCAD's
// (ui/scripts/fcsweep.json, written by fcsweep.py from FreeCAD 26.3 at 3160daf1e2b6), then driven end to end.
//
//   NODE_PATH=<folder with playwright> node ui/scripts/sweepcheck.mjs [--fc=ui/scripts/fcsweep.json] [--keep] [--verbose]
//
// It starts a scratch workbench of its own (as revolvecheck.mjs does) and, in Chromium on SwiftShader, builds the same
// Bodies fcsweep_dump.py built in FreeCAD, through the same commands:
//   menus     the six commands are in the Part Design menu and the modeling toolbar, in FreeCAD's order, and enabled
//   loft      a square on XY and a smaller one 20 above it selected, PartDesign_AdditiveLoft: the panel (Ruled surface,
//             Closed, the Profile, the section list) against FreeCAD's; Ruled; OK is "Make AdditiveLoft"; the part file
//             holds the call; the Body's volume is FreeCAD's; the tree claims both sketches; the property view's names
//   pipe      a circle on XY and an L-shaped path selected, PartDesign_AdditivePipe: the three boxes against FreeCAD's,
//             then after each orientation mode, Multisection and Round corner; OK; the volume
//   helix     a rectangle on XZ, PartDesign_AdditiveHelix: the proposed Pitch and Height, the Axis and Mode items, the fields
//             each mode shows, the self-intersection warning at a 1 mm pitch, Left handed, Base Z-axis; OK; the volume
//   subtractive  a 40 x 40 x 20 block in a second Body: the Subtractive Loft, Pipe and Helix panels (Operation), OK, volumes
//   edit      a double-click on the Helix opens its panel with its values; a new pitch is one step, "Edit AdditiveHelix"; Undo
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
const FC = JSON.parse(readFileSync(flag('fc', join(HERE, 'fcsweep.json')), 'utf8'))
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
let pass = 0, fail = 0, known = 0, knownFinal = 0
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
const scratch = mkdtempSync(join(tmpdir(), 'cad-sweepcheck-')), warmDir = mkdtempSync('/tmp/csw')
const ROOT = join(scratch, 'root'); mkdirSync(ROOT)
for (const d of ['runtime', 'macros']) mkdirSync(join(scratch, d))
const python = process.env.CAD_PYTHON || join(REPO, '.venv', 'bin', 'python')
const env = { ...process.env, CAD_WARM_DIR: warmDir, CAD_RUNTIME_DIR: join(scratch, 'runtime'), CAD_MACRO_DIR: join(scratch, 'macros'),
  CAD_PREFS: join(scratch, 'prefs.json'), PYTHONPATH: REPO, CAD_PYTHON: python, CAD_RENDER_BACKEND: 'numpy' }
delete env.CAD_PROJECTS
spawnSync(python, ['-m', 'cad_agent', '--projects', ROOT, 'init', 'sw', '--brief', 'sweepcheck'], { env, cwd: REPO })
const port = await freePort(8951)
const server = spawn(python, ['-c', `import sys; from pathlib import Path; from cad_agent import serve; serve.run([Path(sys.argv[1])], host="127.0.0.1", port=${port})`, ROOT],
  { env, cwd: REPO, stdio: ['ignore', 'pipe', 'pipe'] })
await new Promise((res, rej) => {
  const t = setTimeout(() => rej(new Error('the scratch workbench did not start')), 60000)
  server.stdout.on('data', (d) => { if (/workbench: http/.test(String(d))) { clearTimeout(t); res() } })
  server.on('exit', (c) => rej(new Error(`the scratch workbench exited with ${c}`)))
})
const BASE = `http://127.0.0.1:${port}`
const post = async (path, body) => (await fetch(BASE + path, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CAD': '1' }, body: JSON.stringify(body) })).json()
const cad = async (argv) => post('/api/cad', { slug: 'sw', argv })
/** The part's solid as its module builds it: (volume, faces), by the same Python the gates run. */
const built = (part) => {
  const r = spawnSync(python, ['-c', `import sys, json; ns = {}; p = sys.argv[1]; exec(compile(open(p).read(), p, "exec"), ns); s = ns["build"](**ns.get("PARAMS", {})); print(json.dumps([s.volume, len(s.faces())]))`,
    join(ROOT, 'sw', 'parts', `${part}.py`)], { env, cwd: REPO, encoding: 'utf8' })
  try { return JSON.parse(r.stdout.trim().split('\n').pop()) } catch { return [NaN, 0, r.stderr.slice(-400)] }
}
const src = (part) => readFileSync(join(ROOT, 'sw', 'parts', `${part}.py`), 'utf8')

const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] })
const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } })
page.on('pageerror', (e) => bad('page error', e.message))
const st = (expr) => page.evaluate(expr)
const until = async (expr, what, ms = 90000) => {
  const t0 = Date.now()
  while (Date.now() - t0 < ms) { if (await st(expr)) return true; await sleep(250) }
  bad(`timed out waiting: ${what}`); return false
}

// FreeCAD's panel, as fcsweep_dump.py read it, box by box: labels, check boxes, combos (by name), spin boxes, line edits,
// list widgets, group boxes, buttons
const fcView = (task) => {
  const w = task[0].filter((x) => x.name !== 'qt_spinbox_lineedit' && !/TaskHeader/.test(x.class) && !['OK', 'Cancel'].includes(x.text))
  return {
    titles: w.filter((x) => /ActionLabel/.test(x.class)).map((x) => x.text),
    labels: w.filter((x) => x.class === 'QLabel').map((x) => x.text),
    checks: Object.fromEntries(w.filter((x) => x.class === 'QCheckBox').map((x) => [x.text, { checked: x.checked, enabled: x.enabled }])),
    combos: w.filter((x) => x.class === 'QComboBox').map((x) => ({ name: x.name, items: x.items, current: x.current })),
    spins: w.filter((x) => /SpinBox/.test(x.class)).map((x) => ({ name: x.name, text: x.text })),
    edits: w.filter((x) => x.class === 'QLineEdit').map((x) => x.text),
    lists: w.filter((x) => x.class === 'QListWidget').map((x) => x.items),
    groups: w.filter((x) => x.class === 'QGroupBox').map((x) => x.text),
    buttons: w.filter((x) => x.class === 'QToolButton' && x.text).map((x) => x.text),
  }
}
// ours, the same way: the boxes' titles, the labels of the fields, check boxes, combos (items read by opening them)
const ourView = async () => {
  const v = await st(`(() => {
    const tv = document.querySelector('.taskview')
    const q = (s) => [...tv.querySelectorAll(s)]
    return {
      titles: q('.tbox-head span').map((e) => e.textContent).filter((t) => t),
      labels: q('.pd-form .tfield > span:first-child').map((e) => e.textContent),
      checks: Object.fromEntries(q('.tbox-body .tcheck').map((e) => [e.textContent.trim(), { checked: e.querySelector('input').checked, enabled: !e.querySelector('input').disabled }])),
      spins: q('.pd-form .tfield').filter((e) => e.querySelector('.qsb')).map((e) => ({ label: e.querySelector('span').textContent, text: e.querySelector('input').value })),
      edits: q('.pd-form .pd-object input').map((e) => e.value),
      lists: q('.pd-form .pd-list').map((e) => [...e.querySelectorAll('.pd-list-row')].map((r) => r.textContent)),
      groups: q('.pd-form fieldset > legend').map((e) => e.textContent),
      buttons: q('.pd-form .qbtn.ptool').map((e) => e.textContent).filter((t) => t && t !== '✕'),
      message: tv.querySelector('.pd-message')?.textContent ?? null,
    }
  })()`)
  v.combos = []
  const n = await page.locator('.taskview .pd-form .qselect').count()
  for (let i = 0; i < n; i++) {
    const b = page.locator('.taskview .pd-form .qselect').nth(i)
    const label = await b.evaluate((el) => el.closest('.tfield')?.querySelector(':scope > span')?.textContent ?? '')
    const current = await b.evaluate((el) => el.querySelector('.combo-label')?.textContent ?? '')
    await b.click(); await sleep(150)
    const items = await st('[...document.querySelectorAll(".combo-popup .combo-item")].map((e) => e.textContent)')
    await page.keyboard.press('Escape'); await sleep(100)
    v.combos.push({ label, items, current })
  }
  return v
}
/** The labels FreeCAD shows that are the fields' labels (its QLabels, its spin boxes' labels), against ours. */
const holdPanel = (us, fc, what, { skipLabels = [] } = {}) => {
  check(same(us.titles, fc.titles), `${what}: the boxes are FreeCAD's`, `\n        FreeCAD ${JSON.stringify(fc.titles)}\n        ours    ${JSON.stringify(us.titles)}`)
  const fcLabels = fc.labels.filter((l) => !skipLabels.includes(l))
  const ourLabels = us.labels.filter((l) => !skipLabels.includes(l))
  check(same(ourLabels, fcLabels), `${what}: the field labels are FreeCAD's`, `\n        FreeCAD ${JSON.stringify(fcLabels)}\n        ours    ${JSON.stringify(ourLabels)}`)
  for (const [t, c] of Object.entries(fc.checks)) {
    const o = us.checks[t]
    if (t === 'Show final result' && o && o.checked === c.checked && !o.enabled) { if (!knownFinal++) note('Show final result is greyed: the result is built when OK writes the feature (as Pad\'s panel)'); continue }
    check(o && o.checked === c.checked && o.enabled === c.enabled, `${what}: "${t}" ${c.checked ? 'checked' : 'unchecked'}${c.enabled ? '' : ', greyed'}`, JSON.stringify(o))
  }
  check(Object.keys(us.checks).every((t) => t in fc.checks), `${what}: no check box FreeCAD has not`, JSON.stringify(Object.keys(us.checks)))
  check(same(us.combos.map((c) => c.items), fc.combos.map((c) => c.items)), `${what}: the combos' items are FreeCAD's`,
    `\n        FreeCAD ${JSON.stringify(fc.combos.map((c) => c.items))}\n        ours    ${JSON.stringify(us.combos.map((c) => c.items))}`)
  check(same(us.combos.map((c) => c.current), fc.combos.map((c) => c.current)), `${what}: the combos show FreeCAD's`,
    `\n        FreeCAD ${JSON.stringify(fc.combos.map((c) => c.current))}\n        ours    ${JSON.stringify(us.combos.map((c) => c.current))}`)
  check(same(us.spins.map((x) => x.text), fc.spins.map((x) => x.text)), `${what}: the spin boxes show FreeCAD's`,
    `\n        FreeCAD ${JSON.stringify(fc.spins.map((x) => x.text))}\n        ours    ${JSON.stringify(us.spins.map((x) => x.text))}`)
  check(same(us.edits, fc.edits), `${what}: the line edits show FreeCAD's`, `FreeCAD ${JSON.stringify(fc.edits)} ours ${JSON.stringify(us.edits)}`)
  check(same(us.lists, fc.lists), `${what}: the lists are FreeCAD's`, `FreeCAD ${JSON.stringify(fc.lists)} ours ${JSON.stringify(us.lists)}`)
  check(same(us.groups, fc.groups), `${what}: the group boxes are FreeCAD's`, `FreeCAD ${JSON.stringify(fc.groups)} ours ${JSON.stringify(us.groups)}`)
  check(same(us.buttons, fc.buttons), `${what}: the selection buttons are FreeCAD's`, `FreeCAD ${JSON.stringify(fc.buttons)} ours ${JSON.stringify(us.buttons)}`)
}
const pick = async (label, text) => {
  const b = page.locator('.taskview .pd-form label.tfield', { has: page.locator(`span:text-is("${label}")`) }).locator('.qselect').first()
  await b.click(); await sleep(150)
  await page.locator('.combo-popup .combo-item', { hasText: text }).first().click()
  await sleep(400)
}
const tick = async (label) => { await page.click(`.taskview .pd-form label.tcheck:has-text("${label}") input`); await sleep(300) }
const typeIn = async (label, text) => {
  await page.click(`.taskview .pd-form label.tfield:has(span:text-is("${label}")) input`)
  await page.keyboard.press('Control+A'); await page.keyboard.type(text); await page.keyboard.press('Tab'); await sleep(400)
}
const okButton = async () => page.click('.taskview .pd-buttons .qbtn.default')
const rect = (x0, y0, x1, y1) => [[x0, y0, x1, y0], [x1, y0, x1, y1], [x1, y1, x0, y1], [x0, y1, x0, y0]].map(([a, b, c, d]) => ({ type: 'LineSegment', start: [a, b], end: [c, d], construction: false }))
const sketch = (name, support, geometry, offset) => ({ name, type: 'Sketcher::SketchObject', support, ...(offset ? { attachment_offset: offset } : {}), geometry, constraints: [] })
const addSketches = async (body, list) => {
  await post(`/api/sw/features/${body}`, { ops: list.map((f) => ({ op: 'add', feature: f })) })
  await st('cadui.loadFeatures()')
  await until(`cadui.getState().features[${JSON.stringify(body)}]?.features.some((f) => f.name === ${JSON.stringify(list[list.length - 1].name)})`, `${list.map((f) => f.name)}`)
}
const run = async (cmd, body, sel, kind = 'pdSweep') => {
  await st(`cadui.setState({ activeBody: ${JSON.stringify(body)}, featSel: ${JSON.stringify(sel.map((n) => `${body}/${n}`))}, selected: [] })`)
  await page.click(`.tb-btn[data-cmd="${cmd}"]`)
  await until(`cadui.getState().task?.kind === ${JSON.stringify(kind)} && !!document.querySelector(".taskview .pd-form")`, `the ${cmd} panel`)
  await sleep(1500)
}
const holdVolume = (part, fcVolume, what) => {
  const [v, , err] = built(part)
  check(Math.abs(v - fcVolume) <= 1e-6 * Math.abs(fcVolume), `${what}: the Body's volume is FreeCAD's (${fcVolume.toFixed(4)})`, err ?? String(v))
}
/** FreeCAD's property view: the names of the groups that have rows and of their rows. */
const fcProps = (pv) => {
  const out = []
  let g = null
  for (const r of pv[0]) {
    if (r.depth === 0) { g = { group: r.name, rows: [] }; out.push(g) } else if (g) g.rows.push(r.name)
  }
  return out.filter((x) => x.rows.length)
}
const ourProps = async (ref) => {
  await st('cadui.showPanel("model")')
  await page.click(`.trow[data-ref="${ref}"] .tname`)
  await sleep(600)
  return st(`[...document.querySelectorAll('.pgroup')].map((g) => ({ group: g.querySelector('.pgroup-head, .ghead, .prow.group .pk, .pk')?.textContent ?? '', rows: [...g.querySelectorAll('.prow:not(.group) .pk')].map((e) => e.textContent) }))`)
}
const holdProps = async (ref, pv, what) => {
  const want = fcProps(pv)
  const got = await st(`(() => { const rows = [...document.querySelectorAll('.prow .pk')].map((e) => e.textContent); return rows })()`)
  void ourProps
  const names = want.flatMap((g) => g.rows)
  const missing = names.filter((n) => !got.includes(n))
  check(!missing.length, `${what}: the property view has FreeCAD's properties`, `missing ${JSON.stringify(missing)}; ours ${JSON.stringify(got)}`)
  const order = got.filter((n) => names.includes(n))
  check(same(order, names), `${what}: in FreeCAD's order`, `\n        FreeCAD ${JSON.stringify(names)}\n        ours    ${JSON.stringify(order)}`)
}

try {
  await page.goto(`${BASE}/next/#sw`)
  await until('!!window.cadui && cadui.getState().slug === "sw" && !!cadui.getState().scene', 'the project to open')
  await st('cadui.setState({ workbench: "design" })')
  await sleep(300)

  // ── menus and toolbar ──────────────────────────────────────────────────────────────────────────────────────────────
  console.log('menus')
  const menus = await st('cadui.pd()')
  const sub = (label) => menus.partDesign.find((e) => e.text === label)?.menu ?? []
  check(same(sub('Additive Features').map((e) => e.cmd), ['PartDesign_Pad', 'PartDesign_Revolution', 'PartDesign_AdditiveLoft', 'PartDesign_AdditivePipe', 'PartDesign_AdditiveHelix']),
    'Part Design > Additive Features: FreeCAD\'s order', JSON.stringify(sub('Additive Features').map((e) => e.cmd)))
  check(same(sub('Subtractive Features').map((e) => e.cmd), ['PartDesign_Pocket', 'PartDesign_Hole', 'PartDesign_Groove', 'PartDesign_SubtractiveLoft', 'PartDesign_SubtractivePipe', 'PartDesign_SubtractiveHelix']),
    'Part Design > Subtractive Features: FreeCAD\'s order', JSON.stringify(sub('Subtractive Features').map((e) => e.cmd)))
  for (const cmd of ['PartDesign_AdditiveLoft', 'PartDesign_AdditivePipe', 'PartDesign_AdditiveHelix', 'PartDesign_SubtractiveLoft', 'PartDesign_SubtractivePipe', 'PartDesign_SubtractiveHelix']) {
    const e = [...sub('Additive Features'), ...sub('Subtractive Features')].find((x) => x.cmd === cmd)
    check(e && e.enabled, `Part Design menu: ${cmd} is there and enabled`)
    check(menus.toolbars.some((t) => t.title === 'Part Design Modeling Features' && t.buttons.some((b) => b.cmd === cmd && b.enabled)), `modeling toolbar: ${cmd} is there and enabled`)
  }

  // ── Additive Loft ────────────────────────────────────────────────────────────────────────────────────────────────────
  console.log('loft')
  await cad(['feature', 'new', 'sw', 'Body'])
  await addSketches('Body', [sketch('Sketch', 'XY', rect(-10, -10, 10, 10)), sketch('Sketch001', 'XY', rect(-5, -5, 5, 5), [0, 0, 20])])
  await run('PartDesign_AdditiveLoft', 'Body', ['Sketch', 'Sketch001'])
  holdPanel(await ourView(), fcView(FC.loft.task), 'Additive Loft')
  check(await st('cadui.getView()?.helpers?.has?.("pd-preview") === true'), 'Additive Loft: the preview overlay is drawn')
  await tick('Ruled surface')
  holdPanel(await ourView(), fcView(FC.loft.task_ruled), 'Additive Loft, Ruled')
  await okButton()
  await until('cadui.getState().features.Body.features.some((f) => f.name === "AdditiveLoft")', 'the AdditiveLoft')
  check(await until('cadui.getState().undo[0]?.name === "Make AdditiveLoft"', 'the step', 60000), 'Additive Loft: OK is one step, "Make AdditiveLoft"')
  check(src('Body').includes('AdditiveLoft("AdditiveLoft", "Sketch", sections=["Sketch001"], ruled=True)'), 'Additive Loft: the part file holds the call',
    src('Body').split('\n').find((l) => l.includes('AdditiveLoft(')))
  holdVolume('Body', FC.loft.volume, 'Additive Loft')
  await st('cadui.showPanel("model"); cadui.setState({ featSel: [] })')
  await sleep(300)
  await page.click('.trow[data-ref="Body/AdditiveLoft"] .twisty').catch(() => {})
  await sleep(300)
  const kids = await st('[...document.querySelectorAll(".trow")].map((e) => e.dataset.ref)')
  const at = kids.indexOf('Body/AdditiveLoft')
  check(at >= 0 && kids.includes('Body/Sketch') && kids.includes('Body/Sketch001') && kids.indexOf('Body/Sketch') > at && kids.indexOf('Body/Sketch001') > at,
    'Additive Loft: the tree claims the profile and the section (ViewProviderLoft::claimChildren)', JSON.stringify(kids))
  await page.click('.trow[data-ref="Body/AdditiveLoft"] .tname'); await sleep(600)
  await holdProps('Body/AdditiveLoft', FC.loft.property_view, 'Additive Loft')

  // ── Additive Pipe ────────────────────────────────────────────────────────────────────────────────────────────────────
  console.log('pipe')
  await addSketches('Body', [sketch('Sketch002', 'XY', [{ type: 'Circle', center: [0, 0], radius: 3, construction: false }], [30, 0, 0]),
    sketch('Sketch003', 'XZ', [{ type: 'LineSegment', start: [30, 0], end: [30, 30], construction: false },
      { type: 'ArcOfCircle', center: [50, 30], radius: 20, start_angle: Math.PI / 2, end_angle: Math.PI, construction: false }])])
  await run('PartDesign_AdditivePipe', 'Body', ['Sketch002', 'Sketch003'])
  holdPanel(await ourView(), fcView(FC.pipe.task), 'Additive Pipe')
  for (const [mode, key] of [['Frenet', 'task_frenet'], ['Auxiliary', 'task_auxiliary'], ['Binormal', 'task_binormal'], ['Standard', 'task_standard']]) {
    await pick('Orientation mode', mode)
    holdPanel(await ourView(), fcView(FC.pipe[key]), `Additive Pipe, ${mode}`)
  }
  await pick('Transform mode', 'Multisection')
  holdPanel(await ourView(), fcView(FC.pipe.task_multisection), 'Additive Pipe, Multisection')
  await pick('Transform mode', 'Constant')
  await pick('Corner transition', 'Round corner')
  holdPanel(await ourView(), fcView(FC.pipe.task_round), 'Additive Pipe, Round corner')
  await okButton()
  await until('cadui.getState().features.Body.features.some((f) => f.name === "AdditivePipe")', 'the AdditivePipe')
  check(await until('cadui.getState().undo[0]?.name === "Make AdditivePipe"', 'the step', 60000), 'Additive Pipe: OK is one step, "Make AdditivePipe"')
  check(src('Body').includes('AdditivePipe("AdditivePipe", "Sketch002", spine="Sketch003", transition="Round corner")'), 'Additive Pipe: the part file holds the call',
    src('Body').split('\n').find((l) => l.includes('AdditivePipe(')))
  holdVolume('Body', FC.pipe.volume, 'Additive Pipe')
  await st('cadui.showPanel("model")'); await sleep(200)
  await page.click('.trow[data-ref="Body/AdditivePipe"] .tname'); await sleep(600)
  await holdProps('Body/AdditivePipe', FC.pipe.property_view, 'Additive Pipe')

  // ── Additive Helix ───────────────────────────────────────────────────────────────────────────────────────────────────
  console.log('helix')
  await addSketches('Body', [sketch('Sketch004', 'XZ', rect(65, 0, 67, 2))])
  await run('PartDesign_AdditiveHelix', 'Body', ['Sketch004'])
  await sleep(1500)
  holdPanel(await ourView(), fcView(FC.helix.task), 'Additive Helix', { skipLabels: ['Status'] })
  for (const [mode, key] of [['Pitch-Turns-Angle', 'task_pitch_turns'], ['Height-Turns-Angle', 'task_height_turns'], ['Height-Turns-Growth', 'task_height_turns_growth'], ['Pitch-Height-Angle', 'task_pitch_height']]) {
    await pick('Mode', mode)
    holdPanel(await ourView(), fcView(FC.helix[key]), `Additive Helix, ${mode}`, { skipLabels: ['Status'] })
  }
  await tick('Left handed')
  holdPanel(await ourView(), fcView(FC.helix.task_left_handed), 'Additive Helix, Left handed', { skipLabels: ['Status'] })
  await typeIn('Pitch', '1')
  const warn = fcView(FC.helix.task_pitch_small).labels.find((l) => /Warning/.test(l))
  check((await ourView()).message === warn, `Additive Helix: a 1 mm pitch shows "${warn}"`, (await ourView()).message)
  await typeIn('Pitch', '5')
  check((await ourView()).message === '' && !fcView(FC.helix.task_pitch_back).labels.some((l) => /Warning/.test(l)), 'Additive Helix: at 5 mm the warning goes, as FreeCAD\'s')
  await pick('Axis', 'Base Z-axis')
  holdPanel(await ourView(), fcView(FC.helix.task_z_axis), 'Additive Helix, Base Z-axis', { skipLabels: ['Status'] })
  await okButton()
  await until('cadui.getState().features.Body.features.some((f) => f.name === "AdditiveHelix")', 'the AdditiveHelix')
  check(await until('cadui.getState().undo[0]?.name === "Make AdditiveHelix"', 'the step', 60000), 'Additive Helix: OK is one step, "Make AdditiveHelix"')
  const fh = FC.helix.props_after
  const hx = await st('cadui.getState().features.Body.features.find((f) => f.name === "AdditiveHelix")')
  check(Math.abs(hx.pitch - fh.Pitch.value) < 1e-9 && Math.abs(hx.height - fh.Height.value) < 1e-6 && hx.left_handed === fh.LeftHanded.value && hx.reference_axis === 'Z_Axis',
    'Additive Helix: written with FreeCAD\'s Pitch, Height, LeftHanded and ReferenceAxis', JSON.stringify(hx))
  holdVolume('Body', FC.helix.volume, 'Additive Helix')
  await st('cadui.showPanel("model")'); await sleep(200)
  await page.click('.trow[data-ref="Body/AdditiveHelix"] .tname'); await sleep(600)
  await holdProps('Body/AdditiveHelix', FC.helix.property_view, 'Additive Helix')
  const turns = await st('[...document.querySelectorAll(".prow")].find((r) => r.querySelector(".pk")?.textContent === "Turns")?.querySelector(".pv")?.textContent')
  const fcTurns = FC.helix.property_view[0].find((r) => r.name === 'Turns')?.value
  check(turns === fcTurns, `Additive Helix: Turns shows ${fcTurns}, follows from Pitch and Height (read-only)`, turns)

  // ── the subtractive ones, on a block ─────────────────────────────────────────────────────────────────────────────────
  console.log('subtractive')
  await cad(['feature', 'new', 'sw', 'Block'])
  await post('/api/sw/features/Block', { ops: [{ op: 'add', feature: sketch('Base', 'XY', rect(-20, -20, 20, 20)) },
    { op: 'add', feature: { name: 'Pad', type: 'PartDesign::Pad', profile: 'Base', length: 20 } }] })
  await addSketches('Block', [sketch('Sketch', 'XY', rect(-8, -8, 8, 8), [0, 0, -5]), sketch('Sketch001', 'XY', rect(-3, -3, 3, 3), [0, 0, 25])])
  const S = FC.subtractive
  await run('PartDesign_SubtractiveLoft', 'Block', ['Sketch', 'Sketch001'])
  holdPanel(await ourView(), fcView(S.subloft.task), 'Subtractive Loft')
  await pick('Operation', 'Common')
  holdPanel(await ourView(), fcView(S.subloft.task_common), 'Subtractive Loft, Common')
  await pick('Operation', 'Subtraction')
  await okButton()
  check(await until('cadui.getState().undo[0]?.name === "Make SubtractiveLoft"', 'the step', 60000), 'Subtractive Loft: OK is one step, "Make SubtractiveLoft"')
  holdVolume('Block', S.subloft.volume, 'Subtractive Loft')
  await addSketches('Block', [sketch('Sketch002', 'YZ', [{ type: 'Circle', center: [0, 20], radius: 3, construction: false }], [0, 0, -25]),
    sketch('Sketch003', 'XY', [{ type: 'LineSegment', start: [-25, 0], end: [25, 0], construction: false }], [0, 0, 20])])
  await run('PartDesign_SubtractivePipe', 'Block', ['Sketch002', 'Sketch003'])
  holdPanel(await ourView(), fcView(S.subpipe.task), 'Subtractive Pipe')
  await okButton()
  check(await until('cadui.getState().undo[0]?.name === "Make SubtractivePipe"', 'the step', 60000), 'Subtractive Pipe: OK is one step, "Make SubtractivePipe"')
  holdVolume('Block', S.subpipe.volume, 'Subtractive Pipe')
  await addSketches('Block', [sketch('Sketch004', 'XZ', rect(18, 0, 22, 2))])
  await run('PartDesign_SubtractiveHelix', 'Block', ['Sketch004'])
  await sleep(1500)
  holdPanel(await ourView(), fcView(S.subhelix.task), 'Subtractive Helix', { skipLabels: ['Status'] })
  await okButton()
  check(await until('cadui.getState().undo[0]?.name === "Make SubtractiveHelix"', 'the step', 60000), 'Subtractive Helix: OK is one step, "Make SubtractiveHelix"')
  holdVolume('Block', S.subhelix.volume, 'Subtractive Helix')
  await st('cadui.showPanel("model")'); await sleep(200)
  await page.click('.trow[data-ref="Block/SubtractiveHelix"] .tname'); await sleep(600)
  await holdProps('Block/SubtractiveHelix', S.subhelix.property_view, 'Subtractive Helix')

  // ── double-click edits ───────────────────────────────────────────────────────────────────────────────────────────
  console.log('edit')
  await st('cadui.setState({ activeBody: "Body" })')
  await st('cadui.showPanel("model")')
  await page.dblclick('.trow[data-ref="Body/AdditiveHelix"] .tname')
  await until('cadui.getState().task?.kind === "pdSweep" && cadui.getState().task?.edit', 'the Helix\'s panel')
  await sleep(800)
  const us = await ourView()
  check(us.spins[0]?.text === '5.00 mm' && us.checks['Left handed']?.checked === true && us.combos.find((c) => c.label === 'Axis')?.current === 'Base Z-axis',
    'edit: the Helix\'s panel opens with its values', JSON.stringify(us))
  await typeIn('Pitch', '4')
  await okButton()
  await until('cadui.getState().features.Body.features.find((f) => f.name === "AdditiveHelix")?.pitch === 4', 'the Helix at 4 mm')
  check(await until('cadui.getState().undo[0]?.name === "Edit AdditiveHelix"', 'the step', 30000), 'edit: the panel\'s OK is one step, "Edit AdditiveHelix"')
  await page.click('.tb-btn[data-cmd="Std_Undo"]')
  check(await until('Math.abs(cadui.getState().features.Body.features.find((f) => f.name === "AdditiveHelix")?.pitch - 5) < 1e-9', 'Undo'), 'Undo puts the pitch back')
} catch (e) {
  bad('sweepcheck stopped', e.stack ?? String(e))
} finally {
  await browser.close()
  server.kill('SIGTERM')
  spawnSync(python, ['-P', '-m', 'cad_agent.warm', 'warm', 'stop'], { env, cwd: REPO, timeout: 60000 })
  if (!args.includes('--keep')) for (const d of [scratch, warmDir]) rmSync(d, { recursive: true, force: true })
}
console.log(`sweepcheck: ${pass} ok, ${fail} failing, ${known} known differences`)
process.exit(fail ? 1 : 0)

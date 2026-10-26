// SPDX-License-Identifier: LGPL-2.1-or-later
// pickcheck: picking references in the 3D view and the tree while a PartDesign task panel asks for one, held to the real
// FreeCAD's (ui/scripts/fcpick.json, written by fcpick.py from FreeCAD 26.3 at 3160daf1e2b6), with the commands and menus
// around it.
//
//   NODE_PATH=<folder with playwright> node ui/scripts/pickcheck.mjs [--fc=ui/scripts/fcpick.json] [--keep] [--verbose]
//
// It starts a scratch workbench of its own (as editcheck.mjs does) with fcpick_dump.py's Body: a 40 x 20 x 5 Pad, Part
// datums (DatumPlane at z 12, DatumLine turned 30 degrees about Y), an LCS at z 9, PartDesign's own (DatumPlane001 at z 11,
// DatumLine001), a circle sketch on the Pad's top. Each pick is a real click on the element in the 3D view (the base the
// panel shows, a datum, the Origin it shows) or on its row in the tree, then the panel's widgets are read and held to
// FreeCAD's after the same pick through its selection gate:
//   pad_face      Pad, Up to face: Select Face armed; an edge refused; Face6, the datum plane, the Origin's XY plane (tree),
//                 the LCS's plane, PartDesign's plane; the datum line refused; OK builds FreeCAD's solid
//   pad_shape     Up to shape: Select Shape takes the Pad (a face of it); Select all faces off; Select picks Face6, Face1
//   pad_direction Direction/edge: Select reference…; a face refused; Pad:Edge9, the datum line, the LCS's Z axis, PartDesign's
//                 line, each kept in the combo; X, Y, Z show the direction; OK
//   revolution    Axis: Select reference…; the datum plane and a face refused; datum lines, the LCS's axis, an edge; Up to face
//   mirrored      Plane: Select reference…; an edge and a line refused; the datum plane, the LCS's YZ plane, a face, PartDesign's
//   linear        Direction: picks kept in the combo with the pattern's "object:" text; Add Feature by a click on the base,
//                 Remove Feature; Mode Spacing (Length synced); the tree's context menu has Multi-Transform
//   polar         Axis: a face and a datum plane refused; a circle and datum lines taken
//   spacing       PatternParametersWidget's on-view labels: Extent one, Spacing occurrences - 1, the -1 entries deactivated;
//                 a click edits one (Escape cancels, the global offset goes back to -1), a right click resets an override
//   draft         Neutral Plane and Pull Direction: the Origin's (tree), datums, an LCS's plane, an edge; refused ones
//   primitive     the Additive and Subtractive Primitive split buttons follow the last primitive started
//   datums        PartDesign_Plane, _Line, _Point, _CoordinateSystem: their panels, Incompatible Reference Set, OK's steps
//   delete        Std_Delete of a datum a sketch is attached to, of a Pad's sketch, of a Fillet's base: FreeCAD's question
//   select        a datum clicked in the 3D view outside any panel is selected; a dress-up's base preselects under the pointer
// A difference prints as FAIL; the deliberate ones (PARITY.md, "Picking in the 3D view") as `known`. Exit 1 on a FAIL.
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
const FC = JSON.parse(readFileSync(flag('fc', join(HERE, 'fcpick.json')), 'utf8'))
const ONLY = (flag('only', '') || '').split(',').filter(Boolean)
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
let pass = 0, fail = 0, known = 0
const ok = (what) => { pass++; if (args.includes('--verbose')) console.log(`  ok    ${what}`) }
const bad = (what, detail = '') => { fail++; console.log(`  FAIL  ${what}${detail ? `: ${detail}` : ''}`) }
const note = (what) => { known++; console.log(`  known ${what}`) }
const check = (cond, what, detail) => (cond ? ok(what) : bad(what, detail))
const same = (a, b, what) => check(JSON.stringify(a) === JSON.stringify(b), what, `\n        FreeCAD ${JSON.stringify(b)}\n        ours    ${JSON.stringify(a)}`)

// ── a scratch workbench (editcheck.mjs's) ────────────────────────────────────────────────────────────────────────────
const freePort = (from) => new Promise((res, rej) => {
  const tryPort = (p) => {
    if (p > from + 40) return rej(new Error('no free port'))
    const s = createServer(); s.once('error', () => tryPort(p + 1)); s.once('listening', () => s.close(() => res(p))); s.listen(p, '127.0.0.1')
  }
  tryPort(from)
})
const scratch = mkdtempSync(join(tmpdir(), 'cad-pickcheck-')), warmDir = mkdtempSync('/tmp/cpk')
const ROOT = join(scratch, 'root'); mkdirSync(ROOT)
for (const d of ['runtime', 'macros']) mkdirSync(join(scratch, d))
const python = process.env.CAD_PYTHON || join(REPO, '.venv', 'bin', 'python')
const env = { ...process.env, CAD_WARM_DIR: warmDir, CAD_RUNTIME_DIR: join(scratch, 'runtime'), CAD_MACRO_DIR: join(scratch, 'macros'),
  CAD_PREFS: join(scratch, 'prefs.json'), PYTHONPATH: REPO, CAD_PYTHON: python, CAD_RENDER_BACKEND: 'numpy' }
delete env.CAD_PROJECTS
spawnSync(python, ['-m', 'cad_agent', '--projects', ROOT, 'init', 'pick', '--brief', 'pickcheck'], { env, cwd: REPO })
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

const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] })
const page = await browser.newPage({ viewport: { width: 1400, height: 950 } })
page.on('pageerror', (e) => bad('page error', e.message))
const st = (expr) => page.evaluate(expr)
const until = async (expr, what, ms = 90000) => {
  const t0 = Date.now()
  while (Date.now() - t0 < ms) { if (await st(expr)) return true; await sleep(250) }
  bad(`timed out waiting: ${what}`); return false
}
const volume = () => {
  const r = spawnSync(python, ['-c', `import sys, importlib.util
spec = importlib.util.spec_from_file_location("p", sys.argv[1]); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print(round(m.build(**m.PARAMS).volume, 6))`, join(ROOT, 'pick', 'parts', 'Body.py')], { env, cwd: REPO, encoding: 'utf8' })
  return r.status === 0 ? Number(r.stdout.trim()) : null
}

// ── the page's widgets by FreeCAD's object names (data-qf), and FreeCAD's ───────────────────────────────────────────
const widget = (qf) => st(`(() => {
  const el = document.querySelector('.taskview [data-qf="${qf}"]')
  if (!el) return null
  const label = el.querySelector?.('.combo-label')
  return { text: label ? label.textContent : el.type === 'checkbox' ? el.parentElement.textContent.trim() : el.tagName === 'INPUT' ? el.value : el.textContent, placeholder: el.placeholder ?? null,
    pressed: el.getAttribute('aria-pressed') === 'true', checked: el.type === 'checkbox' ? el.checked : null, enabled: !el.disabled,
    items: el.classList.contains('pd-reflist') || el.classList.contains('pdx-list') ? [...el.querySelectorAll('[role=option], .pdx-item')].map((x) => x.textContent) : null }
})()`)
const comboItems = async (qf) => {
  const b = page.locator(`.taskview [data-qf="${qf}"]`).first()
  if (!(await b.count())) return null
  await b.click(); await sleep(150)
  const items = await st('[...document.querySelectorAll(".combo-popup .combo-item")].map((e) => e.textContent)')
  await page.keyboard.press('Escape'); await sleep(100)
  return items
}
const choose = async (qf, text) => {
  const b = page.locator(`.taskview [data-qf="${qf}"]`).first()
  await b.click(); await sleep(150)
  await page.locator('.combo-popup .combo-item', { hasText: text }).first().click()
  await sleep(500)
}
const fcSteps = (c) => FC[c].steps
const fcStep = (c, step, nth = 0) => fcSteps(c).filter((s) => s.step === step)[nth]
const fcW = (step, name) => step.task[0].find((w) => w.name === name)
/** The page's widget against FreeCAD's after the same step: text, placeholder, checked (pressed), enabled. */
async function holdWidget(c, stepName, name, what, nth = 0, keys = ['text', 'checked', 'placeholder']) {
  const fs = fcStep(c, stepName, nth)
  if (!fs) return bad(`${c}: FreeCAD has no step ${stepName}`)
  const f = fcW(fs, name), u = await widget(name)
  if (!f) return check(!u, `${what}: no ${name}, as in FreeCAD`)
  if (!u) return bad(`${what}: ${name}`, 'not in the panel')
  for (const k of keys) {
    if (k === 'text' && f.text !== undefined && f.class !== 'QComboBox') check(u.text === f.text, `${what}: ${name} reads "${f.text}"`, u.text)
    if (k === 'text' && f.class === 'QComboBox') check(u.text === f.current, `${what}: ${name} shows "${f.current}"`, u.text)
    if (k === 'checked' && f.checked !== undefined) check((u.checked ?? u.pressed) === f.checked, `${what}: ${name} ${f.checked ? 'down' : 'up'}`, JSON.stringify(u))
    if (k === 'placeholder' && f.placeholder !== undefined && f.text === '') check(u.placeholder === f.placeholder, `${what}: ${name}'s placeholder "${f.placeholder}"`, u.placeholder)
    if (k === 'enabled') check(u.enabled === f.enabled, `${what}: ${name} ${f.enabled ? 'enabled' : 'greyed'}`, String(u.enabled))
    if (k === 'items' && f.class === 'QComboBox') same(await comboItems(name), f.items, `${what}: ${name}'s items`)
    if (k === 'items' && f.class === 'QListWidget') same(u.items, f.items, `${what}: ${name}'s items`)
  }
}

// ── picks: a real click on an element the 3D view draws, or a row of the tree ───────────────────────────────────────
const VIEWS = ['Std_ViewIsometric', 'Std_ViewFront', 'Std_ViewRight', 'Std_ViewTop', 'Std_ViewRear', 'Std_ViewLeft', 'Std_ViewBottom']
async function click3d(key, name, quiet = false, hoverOnly = false) {
  for (const v of [null, ...VIEWS]) {
    if (v) { await st(`cadui.getCommand(${JSON.stringify(v)})?.run([])`); await sleep(400); await st('cadui.getCommand("Std_ViewFitAll")?.run([])'); await sleep(600) }
    const p = await st(`cadui.getView().helperPoint(${JSON.stringify(key)}, ${JSON.stringify(name)})`)
    if (!p && args.includes('--verbose')) console.log(`    ${name}: none in ${v ?? 'the view as it is'}`, await st(`(() => { const v = cadui.getView(), h = v.helpers.get(${JSON.stringify(key)}); let o = null; h?.traverse((x) => { if (x.userData.pickName === ${JSON.stringify(name)}) o = x })
      const cam = v.viewer.camera.getCamera(); const toS = v.screenOf(cam), pos = o?.geometry?.attributes?.position, V = cam.position.constructor, out = []
      for (let k = 1; pos && pos.count === 2 && k < 20; k += 3) { const s = toS(new V().fromBufferAttribute(pos, 0).lerp(new V().fromBufferAttribute(pos, 1), k / 20).applyMatrix4(o.matrixWorld)); out.push([Math.round(s.x), Math.round(s.y), ...[[0, 0], [1.5, 0], [-1.5, 0], [0, 1.5], [0, -1.5]].map(([dx, dy]) => v.helperHit({ x: s.x + dx, y: s.y + dy })?.name)]) }
      return JSON.stringify(out) })()`))
    if (p) {
      // the pointer there first: the element preselects (or the panel's gate says "Not allowed:"), then the click
      await page.mouse.move(p.x - 1, p.y); await sleep(60); await page.mouse.move(p.x, p.y)
      const t0 = Date.now()
      while (Date.now() - t0 < 2000 && !(await st(`cadui.getView().hoveredHelper() === ${JSON.stringify(name)} || /^Not allowed/.test(cadui.getState().gateMsg ?? '') || !cadui.getView().helperPicker`))) await sleep(50)
      if (args.includes('--verbose')) console.log(`    click ${name} at`, JSON.stringify(p), 'hits', JSON.stringify(await st(`cadui.getView().helperHit(${JSON.stringify(p)})`)), 'state', JSON.stringify(await st('({ gate: cadui.getState().gateMsg, task: cadui.getState().task?.kind })')))
      if (!hoverOnly) { await page.mouse.click(p.x, p.y); await sleep(500) }
      return p
    }
  }
  const why = await st(`(() => { const v = cadui.getView(); const out = {}; for (const [k, h] of v.helpers ?? []) { let n = 0, has = false; h.traverse((o) => { if (o.userData.pickName) { n++; if (o.userData.pickName === ${JSON.stringify(name)}) has = true } }); out[k] = n + (has ? ' (has it)' : '') }
    const h = v.helpers.get(${JSON.stringify(key)}); let o = null; h?.traverse((x) => { if (x.userData.pickName === ${JSON.stringify(name)}) o = x })
    const cam = v.viewer.camera.getCamera(); cam.updateMatrixWorld(); h?.updateMatrixWorld(true); const toS = v.screenOf(cam)
    const pos = o?.geometry?.attributes?.position, V = cam.position.constructor, probes = []
    for (let i = 0; pos && i < Math.min(pos.count, 6); i++) { const s = toS(new V().fromBufferAttribute(pos, i).applyMatrix4(o.matrixWorld)); probes.push([Math.round(s.x), Math.round(s.y), v.helperHit(s)?.name ?? null]) }
    return JSON.stringify(out) + ' ' + JSON.stringify(probes) + ' canvas ' + JSON.stringify(v.viewer.renderer.domElement.getBoundingClientRect()) })()`)
  if (quiet) return null
  bad(`${name}: not found in any standard view to click`, why)
  if (flag('shots', '')) await page.screenshot({ path: join(flag('shots', ''), `pickcheck-${name.replace(/\W+/g, '_')}.png`) })
  return null
}
/** Where FreeCAD's step picked an object, our click: the base's element, a datum, an LCS's feature, or the Origin. */
async function pickLike(obj, sub) {
  const ofLcs = /^(X_Axis|Y_Axis|Z_Axis|XY_Plane|XZ_Plane|YZ_Plane)00\d$/.exec(obj)
  if (ofLcs) {
    const p = await click3d('pd-datums', `Body/LCS/${ofLcs[1]}`, true)
    if (p) return p
    note(`LCS ${ofLcs[1]}: no point in the 3D view is it alone; picked by its row in the tree`)
    await treeRow(`LCS/${ofLcs[1]}`)
    return true
  }
  if (/^(X_Axis|Y_Axis|Z_Axis|XY_Plane|XZ_Plane|YZ_Plane)$/.test(obj)) {
    const shown = await st(`!!cadui.getView().helperPoint('pd-pick-origin', ${JSON.stringify(obj)})`)
    if (shown) return click3d('pd-pick-origin', obj)
    await treeRow(obj)
    return true
  }
  if (!sub) {
    // a datum where no click in any view is its alone (lines leaving the origin a few degrees apart): its row in the tree,
    // which the panel takes through the same gate, as FreeCAD's does
    const p = await click3d('pd-datums', `Body/${obj}`, true)
    if (p) return p
    note(`${obj}: no point in the 3D view is it alone; picked by its row in the tree`)
    await treeRow(obj)
    return true
  }
  return click3d('pd-pick', `@${obj}.${sub}`)
}
/** A click on a row of the tree: the combo view's Model tab, the Origin unfolded when the row is one of it, then Tasks again. */
async function treeRow(name) {
  await page.click('.dv-tab:has-text("Model")'); await sleep(300)
  if (!(await st(`!!document.querySelector('.pdrow[data-ref="Body/${name}"]')`))) {
    const folder = name.includes("/") ? `Body/${name.split("/")[0]}` : "Body/Origin"     // an LCS's feature: under its LCS
    await page.locator(`.pdrow[data-ref="${folder}"] .twisty`).first().click(); await sleep(300)
  }
  await page.locator(`.pdrow[data-ref="Body/${name}"]`).first().click(); await sleep(500)
  await page.click('.dv-tab:has-text("Tasks")'); await sleep(300)
}
const waitBase = () => until('!!cadui.getView().helpers?.get?.("pd-pick")', 'the base shown to pick from', 20000)
const feature = (name) => st(`(() => { const d = cadui.getState().features.Body; const f = d.features.find((x) => x.name === ${JSON.stringify(name)}); return f ? JSON.parse(JSON.stringify(f)) : null })()`)
const closeTask = async () => { await st('cadui.setState({ task: null })'); await sleep(400) }

// ── the Body ─────────────────────────────────────────────────────────────────────────────────────────────────────────
const rect = (x0, y0, x1, y1) => [[x0, y0, x1, y0], [x1, y0, x1, y1], [x1, y1, x0, y1], [x0, y1, x0, y0]].map(([a, b, c, d]) => ({ type: 'LineSegment', start: [a, b], end: [c, d], construction: false }))
const circle = (x, y, r) => [{ type: 'Circle', center: [x, y], radius: r, construction: false }]
const datums = [
  { name: 'DatumPlane', type: 'Part::DatumPlane', map_mode: 'Deactivated', placement: [[0, 0, 12], [0, 0, 0]] },
  { name: 'DatumLine', type: 'Part::DatumLine', map_mode: 'Deactivated', placement: [[0, 0, 0], [0, 30, 0]] },
  { name: 'LCS', type: 'Part::LocalCoordinateSystem', map_mode: 'Deactivated', placement: [[0, 0, 9], [0, 0, 0]] },
  { name: 'DatumPlane001', type: 'PartDesign::Plane', map_mode: 'Deactivated', placement: [[0, 0, 11], [0, 0, 0]] },
  { name: 'DatumLine001', type: 'PartDesign::Line', map_mode: 'Deactivated', placement: [[0, 0, 0], [0, 20, 0]] },
]
/** fcpick_dump.py's setup, with `extra` features after it. */
async function setup(extra = []) {
  const doc = await st('cadui.getState().features.Body ?? null')
  const ops = (doc?.features ?? []).slice().reverse().map((f) => ({ op: 'delete', name: f.name }))
  const sk = (name, geometry, off = null, support = 'XY') => ({ name, type: 'Sketcher::SketchObject', support, ...(off ? { attachment_offset: off } : {}), geometry, constraints: [] })
  ops.push({ op: 'add', feature: sk('Sketch', rect(0, 0, 40, 20)) }, { op: 'add', feature: { name: 'Pad', type: 'PartDesign::Pad', profile: 'Sketch', length: 5 } },
    ...datums.map((d) => ({ op: 'add', feature: d })), ...extra.map((f) => ({ op: 'add', feature: f.type === 'sketch' ? sk(f.name, f.geometry, f.off, f.support) : f })))
  const r = await post('/api/pick/features/Body', { ops })
  check(r.data?.built === true, 'setup: the Body builds', JSON.stringify(r).slice(0, 400))
  await until(`cadui.getState().features.Body?.features?.length === ${2 + datums.length + extra.length}`, 'the Body in the page')
  await st('cadui.setState({ workbench: "design", activeBody: "Body", featSel: [], selected: [], subSel: [] })')
  await until('cadui.getState().scene?.bodies.some((b) => b.part === "Body")', 'the Body in the scene')
  await sleep(800)
}
const top = (name = 'Sketch001', x = 10, y = 10, r = 3) => ({ type: 'sketch', name, geometry: circle(x, y, r), off: [0, 0, 5] })
async function run(cmd, featSel = [], subSel = []) {
  await st(`cadui.setState({ featSel: ${JSON.stringify(featSel)}, subSel: ${JSON.stringify(subSel)}, selected: [] })`)
  await st(`cadui.getCommand(${JSON.stringify(cmd)}).run([])`)
  await until('!!document.querySelector(".taskview .tbuttons")', `${cmd}'s panel`)
  await sleep(600)
}
const okTask = async () => { await page.click('.taskview .tbuttons .qbtn.default'); await sleep(400) }
const stepName = () => st('cadui.getState().undo[0]?.name ?? null')

/** One case: each FreeCAD step after a pick, ours after the same click. `widgets` are the names to hold. */
async function picks(c, widgets, arm) {
  for (const [i, s] of fcSteps(c).entries()) {
    const m = /^pick (\S+)(?: (\S+))?$/.exec(s.step) ?? /^button\w+ pick (\S+)(?: (\S+))?$/.exec(s.step)
    if (m) {
      await pickLike(m[1], m[2] ?? '')
      for (const w of widgets) await holdWidget(c, s.step, w, `${c}: after "${s.step}"`, fcSteps(c).filter((x, k) => k < i && x.step === s.step).length)
    } else if (arm[s.step]) {
      await arm[s.step]()
      for (const w of widgets) await holdWidget(c, s.step, w, `${c}: after "${s.step}"`, fcSteps(c).filter((x, k) => k < i && x.step === s.step).length)
    }
  }
}

try {
  await page.goto(`${BASE}/next/#pick`)
  await until('!!window.cadui && cadui.getState().slug === "pick" && !!cadui.getState().scene', 'the project to open')
  await st('cadui.setState({ workbench: "design" })')
  await page.click('.tb-btn[data-cmd="PartDesign_Body"]')
  await until('!!cadui.getState().features.Body', 'New Body')
  // the 3D view in front of the Start page (its tab, "pick : 1"): the picks are clicks in it
  await page.click('.dv-tab:has-text("pick")').catch(() => page.click('text=pick : 1'))
  await sleep(500)
  const want = (c) => !ONLY.length || ONLY.includes(c)

  // ── Pad: Up to face ────────────────────────────────────────────────────────────────────────────────────────────
  if (want('pad_face')) {
    console.log('pad_face')
    await setup([top()])
    await run('PartDesign_Pad', ['Body/Sketch001'])
    await choose('changeMode', 'Up to face')
    for (const w of ['buttonFace', 'lineFaceName']) await holdWidget('pad_face', 'type up to face', w, 'pad_face: Type Up to face')
    await waitBase()
    const W = ['buttonFace', 'lineFaceName']
    await picks('pad_face', W, { 'Select Face': async () => { await page.click('.taskview [data-qf="buttonFace"]'); await sleep(500); await waitBase() } })
    await okTask()
    await until('cadui.getState().features.Body.features.some((f) => f.name === "Pad001")', 'Pad001 made')
    const f = await feature('Pad001')
    same(f?.up_to_face, FC.pad_face.finish.props.UpToFace[0], 'pad_face: OK writes FreeCAD\'s UpToFace')
    check(await stepName() === FC.pad_face.finish.undo[0], `pad_face: the step is "${FC.pad_face.finish.undo[0]}"`, await stepName())
    const v = volume()
    check(v !== null && Math.abs(v - FC.pad_face.finish.volume) < 1e-4 * FC.pad_face.finish.volume, `pad_face: the solid's volume is FreeCAD's ${FC.pad_face.finish.volume}`, String(v))
  }

  // ── Pad: Up to shape ───────────────────────────────────────────────────────────────────────────────────────────
  if (want('pad_shape')) {
    console.log('pad_shape')
    await setup([top()])
    await run('PartDesign_Pad', ['Body/Sketch001'])
    await choose('changeMode', 'Up to shape')
    const W = ['buttonShape', 'checkBoxAllFaces', 'buttonShapeFace', 'listWidgetReferences']
    for (const w of W) await holdWidget('pad_shape', 'type up to shape', w, 'pad_shape: Type Up to shape')
    const shapeName = async (step) => {
      const fs = fcW(fcStep('pad_shape', step), 'lineShapeName'), u = await widget('lineShapeName')
      check((u?.text ?? '').split('#')[1] === fs.text.split('#')[1] && !!u?.text === !!fs.text, `pad_shape: after "${step}": lineShapeName names "${fs.text}" (the document's name and the shape)`, u?.text)
    }
    await page.click('.taskview [data-qf="buttonShape"]'); await sleep(400)
    await waitBase()
    for (const w of ['buttonShape']) await holdWidget('pad_shape', 'Select Shape', w, 'pad_shape: Select Shape')
    await click3d('pd-pick', '@Pad.Face6')
    for (const w of ['buttonShape', 'checkBoxAllFaces']) await holdWidget('pad_shape', 'pick Pad Face6', w, 'pad_shape: a click on the Pad', 0)
    await shapeName('pick Pad Face6')
    await page.click('.taskview [data-qf="checkBoxAllFaces"]'); await sleep(400)
    for (const w of ['checkBoxAllFaces', 'buttonShapeFace']) await holdWidget('pad_shape', 'All faces off', w, 'pad_shape: All faces off')
    await page.click('.taskview [data-qf="buttonShapeFace"]'); await sleep(400)
    await holdWidget('pad_shape', 'Select Faces', 'buttonShapeFace', 'pad_shape: Select')
    await waitBase()
    await click3d('pd-pick', '@Pad.Face6')
    await holdWidget('pad_shape', 'pick Pad Face6', 'listWidgetReferences', 'pad_shape: Face6', 1, ['items'])
    await click3d('pd-pick', '@Pad.Face1')
    await holdWidget('pad_shape', 'pick Pad Face1', 'listWidgetReferences', 'pad_shape: Face1', 0, ['items'])
    note('pad_shape: OK is not pressed: up to Face6 (the profile\'s own plane) and Face1 FreeCAD adds nothing (volume 4000), feature.py\'s fuse fails there')
    await closeTask()
  }

  // ── Pad: Direction/edge ────────────────────────────────────────────────────────────────────────────────────────
  if (want('pad_direction')) {
    console.log('pad_direction')
    await setup([top()])
    await run('PartDesign_Pad', ['Body/Sketch001'])
    await holdWidget('pad_direction', 'open', 'directionCB', 'pad_direction: open', 0, ['text', 'items'])
    check(!(await widget('checkBoxAlongDirection')), 'pad_direction: "Length along sketch normal" hidden for the sketch normal, as in FreeCAD')
    const vec = async (step, nth) => {
      const fs = fcSteps('pad_direction').filter((s) => s.step === step)[nth]
      const want = ['XDirectionEdit', 'YDirectionEdit', 'ZDirectionEdit'].map((n) => Math.round(Number(fcW(fs, n).text) * 100) / 100)
      const got = await Promise.all(['XDirectionEdit', 'YDirectionEdit', 'ZDirectionEdit'].map(async (n) => Math.round(Number((await widget(n))?.text) * 100) / 100))
      same(got, want, `pad_direction: after "${step}": the direction X, Y, Z`)
      await holdWidget('pad_direction', step, 'XDirectionEdit', `pad_direction: after "${step}"`, nth, ['enabled'])
      await holdWidget('pad_direction', step, 'checkBoxAlongDirection', `pad_direction: after "${step}"`, nth, ['checked', 'enabled'])
    }
    let sel = 0, picked = {}
    for (const [i, s] of fcSteps('pad_direction').entries()) {
      if (s.step === 'Select reference…') {
        await choose('directionCB', 'Select reference…')
        await waitBase()
        await holdWidget('pad_direction', s.step, 'directionCB', 'pad_direction: Select reference…', sel, ['text'])
        await vec(s.step, sel)
        sel++
      }
      const m = /^pick (\S+)(?: (\S+))?$/.exec(s.step)
      if (m) {
        const nth = picked[s.step] = (picked[s.step] ?? -1) + 1
        await pickLike(m[1], m[2] ?? '')
        await holdWidget('pad_direction', s.step, 'directionCB', `pad_direction: after "${s.step}"`, nth, ['text', 'items'])
        await vec(s.step, nth)
      }
      void i
    }
    // FreeCAD's last pick is PartDesign's line; OK writes it as the ReferenceAxis
    await choose('directionCB', 'DatumLine001')
    await okTask()
    await until('cadui.getState().features.Body.features.some((f) => f.name === "Pad001")', 'Pad001 made')
    same((await feature('Pad001'))?.reference_axis, FC.pad_direction.finish.props.ReferenceAxis[0], 'pad_direction: OK writes FreeCAD\'s ReferenceAxis')
    const v = volume()
    check(v !== null && Math.abs(v - FC.pad_direction.finish.volume) < 1e-4 * FC.pad_direction.finish.volume, `pad_direction: the solid's volume is FreeCAD's ${FC.pad_direction.finish.volume}`, String(v))
  }

  // ── Revolution: the axis, Up to face ───────────────────────────────────────────────────────────────────────────
  if (want('revolution')) {
    console.log('revolution')
    await setup([{ type: 'sketch', name: 'Sketch001', geometry: rect(45, 0, 50, 8), support: 'XZ' },
      { name: 'DatumLine002', type: 'Part::DatumLine', map_mode: 'Deactivated', placement: [[42, 0, 0], [0, 0, 0]] }])
    await run('PartDesign_Revolution', ['Body/Sketch001'])
    await holdWidget('revolution', 'open', 'axis', 'revolution: open', 0, ['text', 'items'])
    let sel = 0
    const picked = {}
    for (const s of fcSteps('revolution')) {
      if (s.step === 'Select reference…') {
        await choose('axis', 'Select reference…')
        await waitBase()
        await holdWidget('revolution', s.step, 'axis', 'revolution: Select reference…', sel++, ['text'])
      }
      const m = /^pick (\S+)(?: (\S+))?$/.exec(s.step)
      if (m && s.props.Type === 'Angle') {
        const nth = picked[s.step] = (picked[s.step] ?? -1) + 1
        await pickLike(m[1], m[2] ?? '')
        await holdWidget('revolution', s.step, 'axis', `revolution: after "${s.step}"`, nth, ['text', 'items'])
      }
    }
    await choose('changeMode', 'Up to face')
    for (const w of ['buttonFace', 'lineFaceName']) await holdWidget('revolution', 'type up to face', w, 'revolution: Type Up to face')
    await click3d('pd-pick', '@Pad.Face2')
    for (const w of ['buttonFace', 'lineFaceName']) await holdWidget('revolution', 'pick Pad Face2', w, 'revolution: Face2')
    await closeTask()
  }

  // ── Mirrored, LinearPattern, PolarPattern ───────────────────────────────────────────────────────────────────────
  const pocket = (second) => [top('Sketch001', 8, 10, 3), { name: 'Pocket', type: 'PartDesign::Pocket', profile: 'Sketch001', length: 5 },
    ...(second ? [top('Sketch002', 30, 10, 2), { name: 'Pocket001', type: 'PartDesign::Pocket', profile: 'Sketch002', length: 5 }] : [])]
  async function transformed(c, cmd, combo, base, after) {
    console.log(c)
    await setup(pocket(c === 'linear'))
    await run(cmd, ['Body/Pocket'])
    await holdWidget(c, 'open', combo, `${c}: open`, 0, ['text', 'items'])
    let sel = 0
    const picked = {}
    for (const s of fcSteps(c)) {
      if (s.step === 'Select reference…') {
        await choose(combo, 'Select reference…')
        await waitBase()
        await holdWidget(c, s.step, combo, `${c}: Select reference…`, sel++, ['text'])
      }
      const m = /^pick (\S+)(?: (\S+))?$/.exec(s.step)
      if (m && !after?.stop?.(s)) {
        const nth = picked[s.step] = (picked[s.step] ?? -1) + 1
        await pickLike(m[1], m[2] ?? '')
        await holdWidget(c, s.step, combo, `${c}: after "${s.step}"`, nth, ['text', 'items'])
      }
      if (after?.stop?.(s)) break
    }
    await after?.rest?.()
  }
  if (want('mirrored')) {
    await transformed('mirrored', 'PartDesign_Mirrored', 'comboPlane', 'Pocket')
    await okTask()
    await until('cadui.getState().features.Body.features.some((f) => f.name === "Mirrored")', 'the Mirrored')
    same((await feature('Mirrored'))?.mirror_plane, FC.mirrored.finish.props.MirrorPlane[0], 'mirrored: OK writes FreeCAD\'s MirrorPlane')
    const v = volume()
    check(v !== null && Math.abs(v - FC.mirrored.finish.volume) < 1e-4 * FC.mirrored.finish.volume, `mirrored: the solid's volume is FreeCAD's ${FC.mirrored.finish.volume}`, String(v))
  }
  if (want('linear')) {
    await transformed('linear', 'PartDesign_LinearPattern', 'comboDirection', 'Pocket001', {
      stop: (s) => s.step === 'Add Feature',
      rest: async () => {
        const W = ['buttonAddFeature', 'buttonRemoveFeature', 'listWidgetFeatures']
        await page.click('.taskview [data-qf="buttonAddFeature"]'); await sleep(400)
        for (const w of W) await holdWidget('linear', 'Add Feature', w, 'linear: Add Feature', 0, ['checked', 'enabled', 'items'])
        await waitBase()
        await click3d('pd-pick', '@Pocket001.Face3')
        for (const w of W) await holdWidget('linear', 'pick Pocket001 Face3', w, 'linear: a click on the base adds it', 0, ['checked', 'enabled', 'items'])
        await page.click('.taskview [data-qf="buttonRemoveFeature"]'); await sleep(400)
        for (const w of W) await holdWidget('linear', 'Remove Feature', w, 'linear: Remove Feature', 0, ['checked', 'enabled'])
        await waitBase()
        await click3d('pd-pick', '@Pocket001.Face3')
        for (const w of W) await holdWidget('linear', 'pick Pocket001 Face3 (remove)', w, 'linear: a click on it removes it', 0, ['checked', 'enabled', 'items'])
        await choose('comboMode', 'Spacing')
        const fs = fcW(fcStep('linear', 'Mode Spacing'), 'spinSpacing')
        const ours = await st(`(() => { const f = [...document.querySelectorAll('.taskview .tfield')].find((x) => x.querySelector(':scope > span')?.textContent === 'Spacing'); return f?.querySelector('input')?.value ?? null })()`)
        check(ours === fs.text, `linear: Mode Spacing shows the synced spacing ${fs.text}`, ours)
        await okTask()
        await until('cadui.getState().features.Body.features.some((f) => f.name === "LinearPattern")', 'the LinearPattern')
        const lp = await feature('LinearPattern')
        same(lp?.direction, FC.linear.finish.props.Direction[0], 'linear: OK writes FreeCAD\'s Direction')
        same(lp?.originals, FC.linear.finish.props.Originals, 'linear: and its Originals')
        // the tree's context menu on the pattern, and on the Pad: Multi-Transform after Move Feature After…
        await page.click(".dv-tab:has-text(\"Model\")"); await sleep(300)
        for (const [row, fcm] of [["LinearPattern", FC.linear.context_menu], ["Pad", FC.linear.context_menu_pad]]) {
          await page.locator(`.pdrow[data-ref="Body/${row}"]`).first().click({ button: 'right' }); await sleep(400)
          const items = await st('[...document.querySelectorAll(".ctx .ctx-item")].map((e) => e.textContent.trim())')
          const i = fcm.findIndex((e) => e.text === 'Move Feature After…')
          const has = fcm[i + 1]?.text === 'Multi-Transform'
          check(items.some((t) => t.startsWith('Multi-Transform')) === has, `linear: the tree's menu on ${row} ${has ? 'has' : 'has no'} Multi-Transform, as FreeCAD's`, JSON.stringify(items.slice(0, 12)))
          await page.keyboard.press('Escape'); await sleep(200)
        }
      },
    })
  }
  if (want('polar')) {
    await transformed('polar', 'PartDesign_PolarPattern', 'comboDirection', 'Pocket')
    await okTask()
    await until('cadui.getState().features.Body.features.some((f) => f.name === "PolarPattern")', 'the PolarPattern')
    same((await feature('PolarPattern'))?.axis, FC.polar.finish.props.Axis[0], 'polar: OK writes FreeCAD\'s Axis')
  }

  // ── the patterns' on-view spacing labels (PatternParametersWidget's EditableDatumLabels) ─────────────────────────
  if (want('spacing')) {
    console.log('spacing')
    const labelState = () => st(`(() => { const g = cadui.getView()?.helpers?.get?.('pd-spacing'); return g ? JSON.parse(JSON.stringify(g.userData.labels)) : null })()`)
    const hex = (h) => [1, 3, 5].map((i) => Math.round((parseInt(h.slice(i, i + 2), 16) / 255) * 1e4) / 1e4)
    const r4 = (x) => (typeof x === 'number' ? Math.round(x * 1e4) / 1e4 : x)
    /** Ours against FreeCAD's SoDatumLabels: text, points and colour; an ANGLE's radius and start angle too (a DISTANCE's
     *  param1/2 are EditableDatumLabel's own text offsets). */
    const sameLabels = (ours, fcl, what) => same(
      (ours ?? []).map((l) => ({ text: l.text, points: l.points.map((p) => p.map(r4)), color: hex(l.color), kind: l.kind,
        radius: l.kind === 'ANGLE' ? r4(l.radius) : undefined, start: l.kind === 'ANGLE' ? r4(l.start) : undefined })),
      fcl.map((l) => ({ text: l.text[0], points: l.points.map((p) => p.map(r4)), color: l.color, kind: l.type === 1 ? 'DISTANCE' : 'ANGLE',
        radius: l.type === 0 ? r4(l.param1) : undefined, start: l.type === 0 ? r4(l.param2) : undefined })), what)
    /** The labels run on past the body (a 100 mm pattern on a 40 mm Body), off the canvas after a Fit All: zoom out
     *  about the view's middle until the first two are there to click, as a person would. */
    const showLabels = async () => {
      const c = await st(`(() => { const r = cadui.getView().viewer.renderer.domElement.getBoundingClientRect(); return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) } })()`)
      await page.mouse.move(c.x, c.y)
      for (let k = 0; k < 16; k++) {
        if (await st('!!cadui.getView().helperPoint("pd-spacing", "spacing:0") && !!cadui.getView().helperPoint("pd-spacing", "spacing:1")')) return true
        await page.mouse.wheel(0, 120); await sleep(350)
      }
      return bad('spacing: the labels never came into the view to click')
    }
    const openLabel = async (i) => {
      const p = await st(`cadui.getView().helperPoint('pd-spacing', 'spacing:${i}')`)
      if (!p) { bad(`spacing: no point in the view clicks label ${i}`); return null }
      await page.mouse.click(p.x, p.y); await sleep(400)
      return page.locator('body > .ovp-box')
    }
    const noBox = () => st('!document.querySelector("body > .ovp-box")')

    await setup(pocket(true))
    await run('PartDesign_LinearPattern', ['Body/Pocket001'])
    await until('!!cadui.getView().helpers?.get?.("pd-spacing")', 'the linear spacing labels', 20000)
    sameLabels(await labelState(), FC.spacing.open.labels, 'spacing: open: FreeCAD\'s one Extent label')
    const occ = page.locator('.taskview .tfield:has(> span:text-is("Occurrences")) input').first()
    await occ.fill('4'); await sleep(600)
    sameLabels(await labelState(), fcStep('spacing', 'Occurrences 4').labels, 'spacing: Occurrences 4: still the Extent label')
    await choose('comboMode', 'Spacing')
    sameLabels(await labelState(), fcStep('spacing', 'Mode Spacing').labels, 'spacing: Mode Spacing: occurrences - 1 labels at the global offset')
    await showLabels()
    // a click on a label edits it: EditableDatumLabel's spinbox opens with the label's text, Enter writes it
    let box = await openLabel(0)
    if (box && await box.count()) {
      check(await box.inputValue() === '33.33 mm', 'spacing: the spinbox opens with the label\'s "33.33 mm"', await box.inputValue())
      check(await st('document.activeElement === document.querySelector("body > .ovp-box")'), 'spacing: the spinbox takes the focus')
      await box.fill('20 mm'); await page.keyboard.press('Enter'); await sleep(700)
      check(await noBox(), 'spacing: Enter closes the spinbox')
      sameLabels(await labelState(), fcStep('spacing', 'Spacings 20').labels, 'spacing: 20 mm: its own spacing, the others after it')
    } else bad('spacing: a click on a label opens EditableDatumLabel\'s spinbox')
    // Escape (the focus leaving does too) cancels: nothing is written
    box = await openLabel(1)
    if (box && await box.count()) {
      await box.fill('50 mm'); await page.keyboard.press('Escape'); await sleep(400)
      check(await noBox(), 'spacing: Escape closes the spinbox')
      sameLabels(await labelState(), fcStep('spacing', 'Spacings 20').labels, 'spacing: Escape writes nothing')
    } else bad('spacing: a click on the second label opens its spinbox')
    // Direction 2 (parametersWidget2): its labels after Direction 1's, from the same start point; off again after
    await page.locator('.taskview label.tcheck:has-text("Direction 2") input').first().check(); await sleep(500)
    const occ2 = page.locator('.taskview .tfield:has(> span:text-is("Occurrences")) input').nth(1)
    if (await occ2.count()) {
      await occ2.fill('3'); await sleep(700)
      sameLabels(await labelState(), fcStep('spacing', 'Occurrences2 3').labels, 'spacing: Direction 2, Occurrences 3: its Extent label after Direction 1\'s')
    } else bad('spacing: Direction 2 has an Occurrences field')
    await page.locator('.taskview label.tcheck:has-text("Direction 2") input').first().uncheck(); await sleep(500)
    sameLabels(await labelState(), fcStep('spacing', 'Spacings 20').labels, 'spacing: Direction 2 off: Direction 1\'s labels alone')
    // onSpacingLabelRightClicked: "Reset spacing" on an override only; a -1 label keeps the view's own menu
    const menu = async (i) => {
      const p = await st(`cadui.getView().helperPoint('pd-spacing', 'spacing:${i}')`)
      if (!p) { bad(`spacing: no point in the view right-clicks label ${i}`); return [] }
      await page.mouse.click(p.x, p.y, { button: 'right' }); await sleep(500)
      return st('[...document.querySelectorAll(".ctx .ctx-item")].map((e) => e.textContent.trim())')
    }
    let items = await menu(0)
    check(items.includes('Reset spacing'), 'spacing: a right click on a label with an override offers "Reset spacing"', JSON.stringify(items))
    if (items.includes('Reset spacing')) {
      await page.locator('.ctx .ctx-item', { hasText: 'Reset spacing' }).first().click(); await sleep(600)
      sameLabels(await labelState(), fcStep('spacing', 'Mode Spacing').labels, 'spacing: "Reset spacing" puts the global offset back')
    }
    items = await menu(1)
    check(!items.includes('Reset spacing'), 'spacing: a right click on a label at the global offset offers no reset', JSON.stringify(items))
    await page.keyboard.press('Escape'); await sleep(200)
    // an entered spacing equal to the global offset is -1 again (onSpacingLabelClicked's editingFinished)
    const sp = page.locator('.taskview .tfield:has(> span:text-is("Spacing")) input').first()
    await sp.fill('25 mm'); await sleep(700)
    sameLabels(await labelState(), [
      { text: ['25.00 mm'], points: [[30, 10, 2.5], [55, 10, 2.5]], color: [0.5255, 0.5569, 0.5882], type: 1 },
      { text: ['25.00 mm'], points: [[55, 10, 2.5], [80, 10, 2.5]], color: [0.5255, 0.5569, 0.5882], type: 1 },
      { text: ['25.00 mm'], points: [[80, 10, 2.5], [105, 10, 2.5]], color: [0.5255, 0.5569, 0.5882], type: 1 },
    ], 'spacing: a global offset of 25 mm redraws the labels')
    box = await openLabel(0)
    if (box && await box.count()) {
      await box.fill('25 mm'); await page.keyboard.press('Enter'); await sleep(700)
      const l = await labelState()
      check(l?.[0]?.color === '#868e96', 'spacing: 25 mm, the global offset, keeps the label at -1', JSON.stringify(l?.[0]))
    } else bad('spacing: a click on a label at the global offset opens its spinbox')
    await closeTask()
    // the polar pattern: an ANGLE label per gap, at the projected start angle about the axis
    await setup(pocket(false))
    await run('PartDesign_PolarPattern', ['Body/Pocket'])
    await until('!!cadui.getView().helpers?.get?.("pd-spacing")', 'the polar spacing labels', 20000)
    sameLabels(await labelState(), FC.spacing.polar.open.labels, 'spacing: polar open: FreeCAD\'s Extent label')
    const pocc = page.locator('.taskview .tfield:has(> span:text-is("Occurrences")) input').first()
    await pocc.fill('4'); await sleep(600)
    const polarStep = (name) => FC.spacing.polar.steps.find((x) => x.step === name)
    sameLabels(await labelState(), polarStep('Occurrences 4').labels, 'spacing: polar Occurrences 4: still the Extent label')
    await choose('comboMode', 'Angular Spacing')
    sameLabels(await labelState(), polarStep('Angular Spacing').labels, 'spacing: Angular Spacing: occurrences - 1 labels at the global angle')
    await showLabels()
    box = await openLabel(0)
    if (box && await box.count()) {
      check(await box.inputValue() === '120.00°', 'spacing: polar: the spinbox opens with "120.00°"', await box.inputValue())
      await box.fill('30°'); await page.keyboard.press('Enter'); await sleep(700)
      sameLabels(await labelState(), polarStep('Spacings 30').labels, 'spacing: polar 30°: its own angle, the others after it')
    } else bad('spacing: a click on a polar label opens its spinbox')
    await closeTask()
  }

  // ── Draft: neutral plane, pull direction ───────────────────────────────────────────────────────────────────────
  if (want('draft')) {
    console.log('draft')
    await setup()
    await st('cadui.setState({ subSel: [cadui.getState().scene.bodies.find((b) => b.part === "Body").name + ".Face1"], featSel: [] })')
    await st('cadui.getCommand("PartDesign_Draft").run([])')
    await until('!!document.querySelector(".taskview .pd-refsel")', 'the Draft panel')
    await sleep(800)
    for (const s of fcSteps('draft')) {
      if (s.step === 'Preview') { await page.click('.taskview .pd-refsel'); await sleep(400); continue }
      if (s.step === 'buttonPlane' || s.step === 'buttonLine') {
        await page.locator(`.taskview button:text-is("${s.step === 'buttonPlane' ? 'Neutral Plane' : 'Pull Direction'}")`).click(); await sleep(500)
        await until('!!cadui.getView().helpers?.get?.("pd-dressup")', 'the base', 20000)
        continue
      }
      const m = /^(button\w+) pick (\S+)(?: (\S+))?$/.exec(s.step)
      if (!m) continue
      const [, , obj, sub] = m
      if (sub) await click3d('pd-dressup', sub)
      else await pickLike(obj, '')
      for (const [w, lbl] of [['linePlane'], ['lineLine']]) {
        void lbl
        const fw = fcW(s, w), u = await widget(w)
        check(u?.text === fw.text, `draft: after "${s.step}": ${w} reads "${fw.text}"`, u?.text)
      }
    }
    note('draft: OK is not pressed: FreeCAD keeps the Draft on PartDesign\'s plane and Pad:Edge9 in error, a part file only takes one that builds')
    await closeTask()
  }

  // ── the toolbar's primitive groups ─────────────────────────────────────────────────────────────────────────────
  if (want('primitive')) {
    console.log('primitive')
    await setup()
    const icon = (cmd) => st(`document.querySelector('.tb-split[data-split="${cmd}"] .tb-btn img, .tb-split[data-split="${cmd}"] .tb-btn svg use')?.getAttribute('src') ?? document.querySelector('.tb-split[data-split="${cmd}"] .tb-btn')?.innerHTML ?? null`)
    const fp = FC.primitive
    const box = await icon('PartDesign_CompPrimitiveAdditive')
    check(!!box && fp.before.PartDesign_CompPrimitiveAdditive.popup === 'MenuButtonPopup', 'primitive: Additive Primitive is a split button (MenuButtonPopup), as in FreeCAD')
    await st('cadui.getCommand("PartDesign_AdditiveCylinder").run([])'); await until('!!document.querySelector(".taskview .tbuttons")', 'the cylinder\'s panel')
    await okTask(); await sleep(1500)
    const cyl = await icon('PartDesign_CompPrimitiveAdditive')
    check(fp.after.PartDesign_CompPrimitiveAdditive.icon === fp.before.PartDesign_CompPrimitiveAdditive.icons[1] && cyl !== box && /Cylinder/i.test(String(cyl)),
      'primitive: after Additive Cylinder the button shows the cylinder, as FreeCAD\'s', String(cyl).slice(0, 120))
    await st('cadui.getCommand("PartDesign_SubtractiveCone").run([])'); await until('!!document.querySelector(".taskview .tbuttons")', 'the cone\'s panel')
    await page.click('.taskview .tbuttons .qbtn:not(.default)'); await sleep(800)
    const cone = await icon('PartDesign_CompPrimitiveSubtractive')
    check(fp.after_sub_cancel.PartDesign_CompPrimitiveSubtractive.icon === fp.before.PartDesign_CompPrimitiveSubtractive.icons[3] && /Cone/i.test(String(cone)),
      'primitive: a cancelled Subtractive Cone still becomes the button\'s, as FreeCAD\'s', String(cone).slice(0, 120))
    await page.click('.tb-split[data-split="PartDesign_CompPrimitiveAdditive"] .tb-btn:not(.tb-drop)'); await sleep(800)
    check(await st('cadui.getState().task?.other === "PartDesign::AdditiveCylinder"'), 'primitive: a click on the button runs the cylinder again')
    await closeTask()
  }

  // ── PartDesign's datum commands ────────────────────────────────────────────────────────────────────────────────
  if (want('datums')) {
    console.log('datums')
    await setup()
    let boxes = 0
    for (const [key, cmd, sel] of [['PartDesign_Plane', 'PartDesign_Plane', []], ['PartDesign_CoordinateSystem', 'PartDesign_CoordinateSystem', []],
      ['PartDesign_Line_Edge9', 'PartDesign_Line', ['Edge9']], ['PartDesign_Point_Vertex1', 'PartDesign_Point', ['Vertex1']], ['PartDesign_Plane_Face6', 'PartDesign_Plane', ['Face6']]]) {
      const fc = FC.datums[key]
      const body = await st('cadui.getState().scene.bodies.find((b) => b.part === "Body").name')
      await st(`cadui.setState({ featSel: [], selected: [], subSel: ${JSON.stringify(sel.map((s) => `${body}.${s}`))} })`)
      await st(`cadui.getCommand(${JSON.stringify(cmd)}).run([])`)
      await until('cadui.getState().task?.kind === "attach"', `${cmd}'s panel`)
      await sleep(1500)
      const head = await st('document.querySelector(".taskview .tbox-head span")?.textContent ?? null')
      const want = { PartDesign_Plane: 'Datum Plane Parameters', PartDesign_Line: 'Datum Line Parameters', PartDesign_Point: 'Datum Point Parameters', PartDesign_CoordinateSystem: 'Local Coordinate System Parameters' }[cmd]
      check(head === want, `datums: ${key}: the panel is TaskDatumParameters' "${want}"`, head)
      const fmsg = fc.task[0].find((w) => w.name === 'message').text
      await until(`document.querySelector('.taskview .pd-attach-msg')?.textContent === ${JSON.stringify(fmsg)}`, 'the message', 8000)
      check(await st('document.querySelector(".taskview .pd-attach-msg")?.textContent') === fmsg, `datums: ${key}: "${fmsg}"`, await st('document.querySelector(".taskview .pd-attach-msg")?.textContent'))
      const modes = await st('[...document.querySelectorAll(".taskview .pd-modes [role=option]")].map((e) => e.textContent)')
      same(modes, fc.task[0].find((w) => w.name === 'listOfModes').items, `datums: ${key}: the modes`)
      await okTask()
      if (fc.after.MapMode === 'Deactivated') {
        const fb = FC.datums.message_boxes[boxes++]
        await until('!!document.querySelector(".msgbox")', 'Incompatible Reference Set', 10000)
        check(await st('document.querySelector(".msgbox .msgbox-title")?.textContent') === fb.title, `datums: ${key}: OK asks "${fb.title}"`)
        check((await st('document.querySelector(".msgbox .msgbox-body")?.textContent'))?.includes(fb.text.slice(0, 60)), `datums: ${key}: with FreeCAD's words`)
        await page.locator('.msgbox .qbtn', { hasText: 'Yes' }).click(); await sleep(400)
      }
      await until(`cadui.getState().features.Body.features.some((f) => f.name === ${JSON.stringify(fc.in_edit)})`, `${fc.in_edit} made`, 20000)
      const f = await feature(fc.in_edit)
      check(f?.type === fc.type, `datums: ${key}: makes ${fc.type} ${fc.in_edit}`, JSON.stringify(f).slice(0, 200))
      if (f) same((await stepName()), fc.undo[0], `datums: ${key}: the step`)
      if (f && fc.after.MapMode !== 'Deactivated') same(f.map_mode ?? null, fc.after.MapMode, `datums: ${key}: attached with FreeCAD's mode`)
      if (f) { await post('/api/pick/features/Body', { ops: [{ op: 'delete', name: fc.in_edit }] }); await until(`!cadui.getState().features.Body.features.some((x) => x.name === ${JSON.stringify(fc.in_edit)})`, 'the datum gone again', 20000) }
      await sleep(800)
    }
  }

  // ── Std_Delete of features still referenced ────────────────────────────────────────────────────────────────────
  if (want('delete')) {
    console.log('delete')
    for (const victim of ['DatumPlane', 'Sketch001', 'Pad001', 'Pad']) {
      const fd = FC.delete[victim], fb = FC.delete.message_boxes[['DatumPlane', 'Sketch001', 'Pad001', 'Pad'].indexOf(victim)]
      await setup([{ type: 'sketch', name: 'Sketch001', geometry: circle(10, 10, 3) },
        { name: 'Pad001', type: 'PartDesign::Pad', profile: 'Sketch001', length: 2 }, { name: 'Fillet', type: 'PartDesign::Fillet', base: ['Pad001', ['Edge1']], radius: 0.5 }])
      await post('/api/pick/features/Body', { ops: [{ op: 'set', name: 'Sketch001', props: { support: null, attachment_support: [['DatumPlane', '']], map_mode: 'FlatFace' } }] })
      await sleep(1200)
      await closeTask(); await page.keyboard.press("Escape"); await sleep(200)
      await st(`cadui.setState({ featSel: ["Body/${victim}"], selected: [], subSel: [] })`); await sleep(300)
      await st('cadui.getCommand("Std_Delete").run([])'); await sleep(600)
      await until('!!document.querySelector(".msgbox")', 'Object Dependencies', 10000)
      check(await st('document.querySelector(".msgbox .msgbox-title")?.textContent') === fb.title, `delete: ${victim}: FreeCAD asks "${fb.title}"`)
      const body = await st('document.querySelector(".msgbox .msgbox-body")?.textContent')
      check(body?.replace(/\s+/g, ' ').trim() === fb.text.replace(/\s+/g, ' ').trim(), `delete: ${victim}: with FreeCAD's words and dependents`, `\n        FreeCAD ${JSON.stringify(fb.text)}\n        ours    ${JSON.stringify(body)}`)
      await page.locator('.msgbox .qbtn', { hasText: 'Yes' }).click(); await sleep(2500)
      const left = await st('cadui.getState().features.Body.features.map((f) => f.name)')
      const gone = !left.includes(victim)
      const broken = Object.entries(fd.objects).filter(([, o]) => !o.valid).map(([n, o]) => `${n} (${o.status.split(':')[0]})`)
      if (broken.length) {
        check(!gone, `delete: ${victim}: refused, as FreeCAD's delete leaves ${broken.join(', ')} in error`, JSON.stringify(left))
        note(`delete: ${victim}: FreeCAD deletes it and keeps ${broken.join(', ')} in error; a part file only takes a Body that builds`)
        continue
      }
      check(gone, `delete: ${victim}: deleted after Yes, as in FreeCAD`, JSON.stringify(left))
      same(left.filter((n) => n !== 'Origin'), fd.left, `delete: ${victim}: what is left`)
      if (victim === 'DatumPlane') {
        const sk = await feature('Sketch001')
        check(!(sk?.attachment_support?.length), 'delete: DatumPlane: the sketch has no support left, as in FreeCAD')
        check(JSON.stringify(sk?.placement?.[0]) === '[0,0,12]' && /Pos=\(0,0,12\)/.test(fd.sketch_placement), 'delete: DatumPlane: the sketch stays at z 12, as FreeCAD keeps its Placement', JSON.stringify(sk?.placement))
        note('delete: DatumPlane: the sketch\'s Map Mode is Deactivated here, FlatFace with no support in FreeCAD (the part file has no unsupported FlatFace)')
      }
      if (victim === 'Pad001') same((await feature('Fillet'))?.base?.[0], fd.objects.Fillet.Base[0], 'delete: Pad001: the Fillet\'s Base follows to the solid before, as in FreeCAD')
    }
  }

  // ── selection outside the panels, preselection ─────────────────────────────────────────────────────────────────
  if (want('select')) {
    console.log('select')
    await page.goto(`${BASE}/next/#pick`); await until('!!window.cadui && cadui.getState().slug === "pick" && !!cadui.getState().scene', 'the project again')
    await st('cadui.setState({ workbench: "design" })'); await page.click('.dv-tab:has-text("pick")').catch(() => {}); await sleep(500)
    await setup()
    await closeTask()
    const p = await click3d('pd-datums', 'Body/DatumPlane')
    if (args.includes('--verbose')) console.log('    select probe', await st(`(() => { const v = cadui.getView(); const h = v.helperHit(${JSON.stringify(p)}); return JSON.stringify({ select: !!v.helperSelect, picker: !!v.helperPicker, hit: h, featSel: cadui.getState().featSel }) })()`))
    check(p && await st('cadui.getState().featSel.includes("Body/DatumPlane")'), 'select: a click on the datum plane in the 3D view selects it, as in FreeCAD')
    // a dress-up's base preselects under the pointer while Select is down; an element the gate refuses does not
    await st('cadui.setState({ featSel: [], subSel: [] })')
    await st('cadui.getCommand("PartDesign_Fillet").run([])')
    await until('!!document.querySelector(".taskview .pd-refsel")', 'the Fillet panel')
    await until("!!cadui.getView().helpers?.get?.(\"pd-dressup\")", "the base", 20000)
    await click3d("pd-dressup", "Face6", false, true)
    await sleep(300)
    check(await st('cadui.getView().hoveredHelper()') === 'Face6', 'select: the Fillet\'s base preselects Face6 under the pointer')
    check(/Preselected: pick\.Body\.Pad\.Face6/.test(await st('document.querySelector(".statusbar, .status-bar, footer")?.textContent ?? ""')), 'select: the status bar says "Preselected: …Pad.Face6"',
      await st('document.querySelector(".statusbar, .status-bar, footer")?.textContent?.slice(0, 120) ?? ""'))
    await closeTask()
  }
} catch (e) {
  bad('pickcheck crashed', e.stack)
} finally {
  console.log(`\npickcheck: ${pass} ok, ${fail} FAIL, ${known} known`)
  await browser.close()
  server.kill()
  if (!args.includes('--keep')) { rmSync(scratch, { recursive: true, force: true }); rmSync(warmDir, { recursive: true, force: true }) }
  process.exit(fail ? 1 : 0)
}

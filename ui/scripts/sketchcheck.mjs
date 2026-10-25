// SPDX-License-Identifier: LGPL-2.1-or-later
// The workbench's Sketcher against the real FreeCAD's: ui/scripts/sketchref.json is what FreeCAD 26.3 does
// (fcsketch.py --ref), and this does the same in a running workbench and says where the two differ.
//   node ui/scripts/sketchcheck.mjs [URL] [PROJECT] [--only CASE,...] [--suite main,AREA,...] [--no-chrome] [--shots DIR]
// It checks the edit mode's toolbars (each command and group, in order) and the Sketch menu, the colours sketchdraw.ts
// draws with against FreeCAD's parameters, the datum dialogs' titles, and for every case of sketchcases.json the
// geometry (to a quarter of a millimetre: one pixel of the view is 0.16 mm), the constraints (type and arguments; a
// dimension's value to 0.3 mm or 0.01 rad) and the solver's message the clicks, keys and selections make. The view is
// sized and the camera set as fcsketch_dump.py sets FreeCAD's (sketchcases.json's camera, FreeCAD's viewport size), the
// commands run by name (`cad gui run`, as Gui.runCommand there), the clicks are real pointer events.
// Point it at a workbench serving a SCRATCH copy of the project: it opens and leaves sketches there.
// Needs Playwright (npm i -g playwright, or NODE_PATH to one) with a Chromium.
import { createRequire } from 'module'
import { readFileSync, mkdirSync, readdirSync } from 'fs'
import { fileURLToPath } from 'url'
const require = createRequire(import.meta.url)
let chromium
try { ({ chromium } = require('playwright')) } catch { ({ chromium } = createRequire('/opt/node-tools/node_modules/')('playwright')) }
const argv = process.argv.slice(2)
const flag = (name) => { const i = argv.indexOf(name); if (i < 0) return null; const v = argv[i + 1]; argv.splice(i, 2); return v }
const only = (flag('--only') ?? '').split(',').filter(Boolean), shots = flag('--shots')
const suites = (flag('--suite') ?? '').split(',').filter(Boolean)
const noChrome = argv.includes('--no-chrome'); if (noChrome) argv.splice(argv.indexOf('--no-chrome'), 1)
const [BASE = 'http://127.0.0.1:8733/next/', PROJECT = 'arduino_car'] = argv
const here = (f) => fileURLToPath(new URL(f, import.meta.url))
const REF = JSON.parse(readFileSync(here('sketchref.json'), 'utf8'))
const origin = new URL(BASE).origin
const problems = [], notes = []
// The case files: sketchcases.json (FreeCAD's answers in sketchref.json, with the toolbars, menu and colours) and
// sketchcases-AREA.json (answers in sketchref-AREA.json), each with its own camera; --suite AREA,... runs only those.
const SUITES = readdirSync(here('.')).filter((f) => /^sketchcases(-[\w-]+)?\.json$/.test(f)).sort()
  .filter((f) => !suites.length || suites.includes(f === 'sketchcases.json' ? 'main' : f.slice('sketchcases-'.length, -5)))
  .map((f) => {
    const refFile = f.replace('sketchcases', 'sketchref')
    let ref = { cases: {}, dialogs: [] }
    try { ref = JSON.parse(readFileSync(here(refFile), 'utf8')) } catch { notes.push(`${f}: no ${refFile} yet (fcsketch.py --cases ${f} --ref)`) }
    return { file: f, refFile, cases: JSON.parse(readFileSync(here(f), 'utf8')), ref }
  })
const bad = (what) => { problems.push(what); console.log(`DIFF ${what}`) }

const b = await chromium.launch({ args: ['--use-angle=swiftshader', '--use-gl=angle', '--enable-unsafe-swiftshader'] })
const p = await b.newPage({ viewport: { width: 1400, height: 900 } })
const errs = []; p.on('pageerror', (e) => errs.push(e.message)); p.on('console', (m) => { if (m.type() === 'error') console.log('console error:', m.text().slice(0, 300)) })
const api = async (path, body) => {
  const r = await fetch(origin + path, body ? { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CAD': '1' }, body: JSON.stringify(body) } : {})
  return r.json()
}
const gui = (cmd, args) => api('/api/gui/do', { slug: PROJECT, cmd, args })
await p.goto(`${BASE}#${encodeURIComponent(PROJECT)}`, { waitUntil: 'load' })
for (let i = 0; i < 240 && !(await p.evaluate((slug) => !!window.cadui && window.cadui.getState().slug === slug && !!window.cadui.getState().scene, PROJECT)); i++) await p.waitForTimeout(250)
await p.evaluate(() => window.cadui.showPanel('view3d')) // the 3D view in front of the Start page
await p.waitForTimeout(500)
// the 3D view as large as FreeCAD's was (fcsketch_dump.py measured its viewport)
const gl = async () => p.evaluate(() => {
  const c = [...document.querySelectorAll('canvas')].sort((a, b) => b.clientWidth * b.clientHeight - a.clientWidth * a.clientHeight)[0]
  const r = c.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }
})
let box = await gl()
const [vw, vh] = REF.viewport
for (let i = 0, size = { width: 1400, height: 900 }; i < 4 && (Math.round(box.w) !== vw || Math.round(box.h) !== vh); i++) {
  size = { width: Math.round(size.width + vw - box.w), height: Math.round(size.height + vh - box.h) }
  await p.setViewportSize(size); await p.waitForTimeout(800)
  box = await gl()
}
notes.push(`3D view ${Math.round(box.w)}x${Math.round(box.h)} (FreeCAD's ${vw}x${vh})`)

let colours = 0
if (!noChrome) {
// ── the Sketcher workbench, a sketch in edit: toolbars and menu ──────────────────────────────────────────────────
await gui('run', ['Sketcher_EditSketch', 'Sketch', '{}'])
await p.waitForSelector('.sketch-task', { timeout: 10000 })
await p.waitForTimeout(600)
const ours = await p.evaluate(() => [...document.querySelectorAll('[data-toolbar]')].map((t) => ({
  title: t.getAttribute('data-toolbar'),
  items: [...t.children].filter((c) => !c.classList.contains('tb-grip')).map((c) => c.classList.contains('tb-sep') ? 'sep'
    : c.classList.contains('tb-split') ? { group: c.querySelector('[data-group]').getAttribute('data-group') } : c.getAttribute('data-cmd')),
})))
for (const [ti, tb] of ours.entries()) {
  for (const [k, it] of tb.items.entries()) {
    if (typeof it !== 'object') continue
    await p.locator(`[data-toolbar="${tb.title}"] [data-group-menu="${it.group}"]`).click()
    await p.waitForTimeout(80)
    it.items = await p.evaluate(() => [...document.querySelectorAll('.ctx > *')].map((e) => e.classList.contains('mb-sep') ? 'sep' : e.getAttribute('data-cmd')))
    await p.keyboard.press('Escape'); await p.waitForTimeout(50)
    // the Escape that closes a menu must not leave the sketch: the edit is still on
    if (!(await p.locator('.sketch-task').count())) { bad('Escape on a toolbar menu left the sketch'); await gui('run', ['Sketcher_EditSketch', 'Sketch', '{}']); await p.waitForTimeout(800) }
    tb.items[k] = it; ours[ti] = tb
  }
}
const same = (a, b) => (b === '' ? true : typeof a === 'string' || typeof b === 'string' ? a === b
  : (a.group ?? a.menu) === (b.group ?? b.menu) && a.items.length === b.items.length && a.items.every((x, i) => same(x, b.items[i])))
const show = (x) => (typeof x === 'string' ? x : `${x.group ?? x.menu}[${x.items.map(show).join(' ')}]`)
for (const want of REF.toolbars.filter((t) => ['Edit Mode', 'Geometries', 'Constraints', 'Sketcher Tools', 'B-Spline Tools', 'Visual Helpers'].includes(t.title))) {
  const got = ours.find((t) => t.title === want.title)
  if (!got) { bad(`toolbar ${want.title} missing`); continue }
  if (got.items.length !== want.items.length || !got.items.every((x, i) => same(x, want.items[i])))
    bad(`toolbar ${want.title}:\n   ours     ${got.items.map(show).join(' ')}\n   FreeCAD  ${want.items.map(show).join(' ')}`)
}
if (ours.map((t) => t.title).join() !== 'Edit Mode,Geometries,Constraints,Sketcher Tools,B-Spline Tools,Visual Helpers') bad(`edit-mode toolbars: ${ours.map((t) => t.title).join(', ')}`)
// the Sketch menu, its submenus opened one by one
await p.locator('.menubar .mb-trigger', { hasText: /^Sketch$/ }).click(); await p.waitForTimeout(150)
const readMenu = async () => p.evaluate(() => {
  const menus = [...document.querySelectorAll('.mb-content')], m = menus[menus.length - 1]
  return [...m.children].map((e) => e.classList.contains('mb-sep') ? 'sep' : e.getAttribute('data-cmd') ?? { menu: e.textContent.replace('▸', '').trim() })
})
const menu = await readMenu()
// Esc while a menu is open closes it; one more would leave the sketch (LeaveSketchWithEscape), as in FreeCAD
const closeMenus = async () => { for (let i = 0; i < 4 && (await p.locator('.mb-content').count()); i++) { await p.keyboard.press('Escape'); await p.waitForTimeout(80) } }
const reopen = async () => {
  await closeMenus()
  await p.locator('.menubar .mb-trigger', { hasText: /^Sketch$/ }).click(); await p.waitForTimeout(150)
}
for (const [k, it] of menu.entries()) {
  if (typeof it !== 'object') continue
  await reopen()
  await p.locator('.mb-content .mb-item', { hasText: it.menu }).first().hover(); await p.waitForTimeout(250)
  it.items = await readMenu()
  for (const [j, sub] of it.items.entries()) {
    if (typeof sub !== 'object') continue
    await p.locator('.mb-content .mb-item', { hasText: sub.menu }).last().hover(); await p.waitForTimeout(250)
    sub.items = await readMenu(); it.items[j] = sub
  }
  menu[k] = it
}
await closeMenus()
const wantMenu = REF.sketch_menu
if (menu.length !== wantMenu.length || !menu.every((x, i) => same(x, wantMenu[i])))
  bad(`Sketch menu:\n   ours     ${menu.map(show).join(' ')}\n   FreeCAD  ${wantMenu.map(show).join(' ')}`)
const empty = await p.locator('.sketch-task .sk-status').innerText()
if (empty !== REF.message_empty.status) bad(`empty sketch message: ${empty} (FreeCAD: ${REF.message_empty.status})`)
await gui('run', ['Sketcher_CancelSketch']); await p.waitForTimeout(400)

// ── colours: sketchdraw.ts's COLORS against FreeCAD's parameters (packed RGBA) ───────────────────────────────────
const draw = readFileSync(here('../src/sketchdraw.ts'), 'utf8')
const ourColor = (key) => { const m = new RegExp(`\\b${key}: hex\\(0x([0-9a-f]{6})\\)`).exec(draw); return m ? parseInt(m[1], 16) : null }
const COLOR_KEYS = { EditedEdgeColor: 'curve', ConstructionColor: 'construction', InternalAlignedGeoColor: 'internal', FullyConstraintElementColor: 'fullyElement',
  FullyConstraintConstructionElementColor: 'fullyConstruction', FullyConstrainedColor: 'fully', InvalidSketchColor: 'invalid', ConstrainedDimColor: 'constrDim',
  ConstrainedIcoColor: 'constrIco', NonDrivingConstrDimColor: 'nonDriving', DeactivatedConstrDimColor: 'deactivated', ExprBasedConstrDimColor: 'exprBased',
  ExternalColor: 'external', HighlightColor: 'preselect', SelectionColor: 'select', CursorTextColor: 'cursorText', CursorCrosshairColor: 'crosshair',
  GridLineColor: 'grid', GridDivLineColor: 'gridDiv' }
for (const [param, key] of Object.entries(COLOR_KEYS)) {
  const fc = REF.params[param]
  if (fc == null) continue
  colours++
  const want = fc >>> 8, got = ourColor(key)
  if (got !== want) bad(`colour ${param}: ours #${(got ?? 0).toString(16).padStart(6, '0')}, FreeCAD #${want.toString(16).padStart(6, '0')}`)
}
} // !noChrome

// ── the cases ────────────────────────────────────────────────────────────────────────────────────────────────────
const KEY = { Escape: 'Escape', Delete: 'Delete', Return: 'Enter', M: 'm', Tab: 'Tab', Backspace: 'Backspace' }
const dialogs = []
const near = (a, b, tol) => Math.abs(a - b) <= tol
function sameGeo(a, b) {
  if (a.type !== b.type || !!a.construction !== !!b.construction) return false
  const P = (u, v) => near(u[0], v[0], 0.25) && near(u[1], v[1], 0.25)
  if (a.type === 'Point') return P(a.at, b.at)
  if (a.type === 'LineSegment') return P(a.start, b.start) && P(a.end, b.end)
  const d = (x, y) => Math.abs(Math.atan2(Math.sin(x - y), Math.cos(x - y)))
  const range = () => a.start_angle === undefined || (d(a.start_angle, b.start_angle) < 0.02 && d(a.end_angle, b.end_angle) < 0.02)
  if (a.type === 'BSplineCurve') {
    const all = (u, v, f) => u.length === v.length && u.every((x, i) => f(x, v[i]))
    return a.degree === b.degree && !!a.periodic === !!b.periodic && all(a.poles, b.poles, P) && all(a.mults, b.mults, (x, y) => x === y)
      && all(a.weights, b.weights, (x, y) => near(x, y, 0.25)) && all(a.knots, b.knots, (x, y) => near(x, y, 1e-6))
  }
  if (a.type === 'Ellipse' || a.type.startsWith('ArcOf') && a.type !== 'ArcOfCircle') {
    const r = a.type === 'ArcOfParabola' ? near(a.focal, b.focal, 0.25) : near(a.major_radius, b.major_radius, 0.25) && near(a.minor_radius, b.minor_radius, 0.25)
    return P(a.center, b.center) && r && d(Math.atan2(a.x_axis[1], a.x_axis[0]), Math.atan2(b.x_axis[1], b.x_axis[0])) < 0.02 && range()
  }
  if (!P(a.center, b.center) || !near(a.radius, b.radius, 0.25)) return false
  return a.type === 'Circle' || range()
}
const sameCons = (a, b) => a.type === b.type && a.args.join() === b.args.join()
  && (b.value === undefined || near(a.value ?? NaN, b.value, a.type === 'Angle' ? 0.01 : 0.3))
const fmtC = (c) => `${c.type}(${c.args.join(',')}${c.value !== undefined ? `=${+c.value.toFixed(4)}` : ''})`
const fmtG = (g) => g.type === 'Point' ? `Point(${g.at.map((v) => v.toFixed(2))})` : g.type === 'LineSegment' ? `Line(${g.start.map((v) => v.toFixed(2))} ${g.end.map((v) => v.toFixed(2))})`
  : g.type === 'BSplineCurve' ? `BSpline(d${g.degree}${g.periodic ? ' periodic' : ''} ${g.poles.map((q) => q.map((v) => v.toFixed(2)).join(',')).join(' ')} w${g.weights.map((v) => +v.toFixed(3)).join(',')} k${g.knots.map((v) => +v.toFixed(3)).join(',')} m${g.mults.join(',')})`
  : g.x_axis ? `${g.type}(${g.center.map((v) => v.toFixed(2))} ${g.focal !== undefined ? `f${g.focal.toFixed(2)}` : `r${g.major_radius.toFixed(2)},${g.minor_radius.toFixed(2)}`} x${g.x_axis.map((v) => v.toFixed(3))}${g.start_angle !== undefined ? ` ${g.start_angle.toFixed(3)}..${g.end_angle.toFixed(3)}` : ''})`
  : `${g.type}(${g.center.map((v) => v.toFixed(2))} r${g.radius.toFixed(2)}${g.start_angle !== undefined ? ` ${g.start_angle.toFixed(3)}..${g.end_angle.toFixed(3)}` : ''})`
if (shots) mkdirSync(shots, { recursive: true })
let passed = 0, run = 0, known = 0
// Cases where FreeCAD's GUI is not repeatable. An under-constrained sketch's solution depends on the order of
// PlaneGCS's unknowns, which FreeCAD takes from their memory addresses (tests/golden/sketcher/make.py says more).
// c-parallel (7 DoF): FreeCAD's GUI recorded line 1 mirrored about its middle; freecadcmd at the same commit, our
// native build and our wasm build all give the other, equally valid, answer for the same two lines and Parallel.
// A case may say why it is known to differ ("known": "reason") in its case file too.
const KNOWN = { 'c-parallel': 'FreeCAD\'s GUI gives line 1 mirrored; freecadcmd gives ours (under-constrained, memory order)' }
for (const suite of SUITES) {
const { cases: CASES, ref: SREF, file: SFILE, refFile: RFILE } = suite
const [cx, cy] = CASES.camera.center, H = CASES.camera.height
const camera = `#Inventor V2.1 ascii\nOrthographicCamera {\n viewportMapping ADJUST_CAMERA\n position ${cx} ${cy} 100\n orientation 0 0 1 0\n nearDistance 0\n farDistance 200\n aspectRatio 1\n focalDistance 100\n height ${H}\n}\n`
for (const [k, c] of CASES.cases.entries()) {
  if (only.length && !only.includes(c.name)) continue
  if (c.known) KNOWN[c.name] = c.known
  const want = SREF.cases[c.name]
  if (!want) { notes.push(`${c.name}: no FreeCAD answer in ${RFILE} (${SFILE})`); continue }
  run++
  // the case's preferences ("params", as fcsketch_dump.py's set_params sets FreeCAD's), put back after it
  const oldParams = c.params ? await p.evaluate((ps) => window.cadui.setSketcherParams?.(ps) ?? null, c.params) : null
  let name = `S${k}`, off = [0, 0] // where the sketch's origin sits in the scene (a plate part's placement)
  if (c.plate) {
    // a Body part of its own: the 40 x 20 x 5 plate (a rectangle on XY, padded 5 mm) and the case's sketch S on its top
    // face (Pad.Face6, FlatFace), as fcsketch_dump.py's plate_sketch makes it; opened from the tree, as a double-click
    // opens a Body's sketch
    name = 'S'
    const part = `Plate${k}x${Date.now().toString(36)}` // a part of its own each run
    await api('/api/cad', { slug: PROJECT, argv: ['feature', 'new', PROJECT, part] })
    const L = (a, b) => ({ type: 'LineSegment', start: a, end: b, construction: false })
    const ops = [
      { op: 'add', feature: { name: 'Sketch', type: 'Sketcher::SketchObject', support: 'XY', geometry: [L([0, 0], [40, 0]), L([40, 0], [40, 20]), L([40, 20], [0, 20]), L([0, 20], [0, 0])], constraints: [] } },
      { op: 'add', feature: { name: 'Pad', type: 'PartDesign::Pad', profile: 'Sketch', length: 5 } },
      { op: 'add', feature: { name: 'S', type: 'Sketcher::SketchObject', attachment_support: [['Pad', 'Face6']], map_mode: 'FlatFace', geometry: [], constraints: [] } }]
    const r = await api(`/api/${encodeURIComponent(PROJECT)}/features/${part}`, { ops })
    if (r.exit > 2) { bad(`${c.name}: the plate was not made: ${JSON.stringify(r).slice(0, 300)}`); continue }
    for (let i = 0; i < 80 && !(await p.evaluate((pt) => !!window.cadui.getState().features[pt]?.features.find((f) => f.name === 'S')?.attached
      && !!window.cadui.getState().scene?.bodies.some((b) => b.part === pt), part)); i++) await p.waitForTimeout(250)
    // the server checks the new part and the scene reloads: wait until that has settled, or it moves the camera later
    for (let i = 0, last = '', same = 0; i < 120 && same < 8; i++) {
      const now = await p.evaluate(() => JSON.stringify([window.cadui.getState().scene?.source_hash, window.cadui.getState().scene?.bodies.length, window.cadui.getState().busy]))
      same = now === last ? same + 1 : 0; last = now; await p.waitForTimeout(250)
    }
    await p.evaluate(() => window.cadui.showPanel('model')); await p.waitForTimeout(300)
    const row = p.locator(`[data-ref="${part}/S"]`)
    if (!(await row.count())) { const pad = p.locator(`[data-ref="${part}/Pad"] .twisty`); if (await pad.count()) await pad.first().click() }
    const m = await p.evaluate((pt) => window.cadui.getState().scene?.bodies.find((b) => b.part === pt)?.matrix ?? null, part)
    if (m?.length === 16) off = [m[3], m[7]] // the project lays its parts out side by side; the sketch's camera follows
    await p.dblclick(`.trow[data-ref="${part}/S"] .tname`)
    await p.evaluate(() => window.cadui.showPanel('view3d'))
  } else {
    // the last case's sketch is closed first (a CancelSketch the page has not taken yet)
    for (let t = 0; t < 20 && (await p.locator('.sketch-task').count()); t++) { if (t % 5 === 0) await gui('run', ['Sketcher_CancelSketch']); await p.waitForTimeout(300) }
    await gui('run', ['Sketcher_EditSketch', name, JSON.stringify(c.setup ?? {})])
  }
  try { await p.waitForSelector('.sketch-task', { timeout: 10000 }) } catch {
    // once more (a command the page had not taken yet), then the case is a difference rather than the end of the run
    if (process.env.SKETCHCHECK_TRACE) console.log('  retry', JSON.stringify((await api(`/api/gui?slug=${PROJECT}`)).sketch?.name), await p.evaluate(() => [...document.querySelectorAll('.ctx, .mb-content, .msgbox-back')].map((e) => e.className).join()))
    let open = c.plate ? await p.waitForSelector('.sketch-task', { timeout: 20000 }).then(() => true, () => false) : false
    for (let t = 0; t < 3 && !open && !c.plate; t++) {
      await gui('run', ['Sketcher_CancelSketch']); await p.waitForTimeout(1000)
      await gui('run', ['Sketcher_EditSketch', name, JSON.stringify(c.setup ?? {})])
      open = await p.waitForSelector('.sketch-task', { timeout: 20000 }).then(() => true, () => false)
    }
    if (!open) { bad(`${c.name}: the sketch did not open`); continue }
  }
  await p.waitForTimeout(800) // the view turning to the sketch (an animation, then the fit)
  // the camera FreeCAD's had, set again until it stays (the turn's animation may still be running)
  for (let i = 0; i < 20; i++) {
    await gui('view', [camera.replace(`position ${cx} ${cy} 100`, `position ${cx + off[0]} ${cy + off[1]} 100`)]); await p.waitForTimeout(300)
    const cam = await p.evaluate(() => window.cadui.getView()?.getCamera() ?? '')
    const pos = /position\s+(\S+)\s+(\S+)/.exec(cam), h = /height\s+(\S+)/.exec(cam)
    if (pos && h && Math.abs(+pos[1] - cx - off[0]) < 1e-3 && Math.abs(+pos[2] - cy - off[1]) < 1e-3 && Math.abs(+h[1] - H) < 1e-3) break
  }
  box = await gl()
  const s = box.h / H
  const scr = ([x, y]) => [box.x + box.w / 2 + (x - cx) * s, box.y + box.h / 2 - (y - cy) * s]
  const move = async (q, ms = 80) => { const [x, y] = scr(q); await p.mouse.move(x, y); await p.waitForTimeout(ms) }
  const dialog = async () => {
    const d = p.locator('.datum-dlg')
    if (await d.count()) { dialogs.push({ case: c.name, title: await d.locator('.msgbox-title').innerText() }); await d.locator('.qbtn.default').click(); await p.waitForTimeout(120) }
    // a case's "msgbox": the question's button of that text (fcsketch_dump.py presses FreeCAD's)
    const q = p.locator('.msgbox[role="alertdialog"]')
    if (c.msgbox && await q.count()) {
      dialogs.push({ case: c.name, title: await q.locator('.msgbox-title').innerText() })
      await q.locator('.msgbox-buttons button', { hasText: new RegExp(`^${c.msgbox}$`) }).click(); await p.waitForTimeout(150)
    }
  }
  // ── the task panel's lists ("panel" steps: sketchcases-panels.json says what each does) ──
  const panelRecord = {}, stepErrors = []
  const ctxEntries = () => p.evaluate(() => [...document.querySelectorAll('.ctx > *')].map((e) => e.classList.contains('mb-sep') ? 'sep'
    : { text: [...e.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join('').trim(), enabled: !e.hasAttribute('data-disabled'),
      bold: e.classList.contains('bold'), checked: !!e.querySelector('.mb-check') }))
  const pickCtx = async (label) => {
    const i = (await ctxEntries()).findIndex((e) => e !== 'sep' && e.text === label)
    if (i < 0) throw new Error(`no menu entry ${label}`)
    await clickAt(p.locator('.ctx > *').nth(i))
  }
  // a pointer click at the element's middle, with modifier keys held (Playwright's own click waits for the layout to
  // stand still, which the docked panels' relayouts may not give it)
  const clickAt = async (loc, { button = 'left', modifiers = [], count = 1 } = {}) => {
    const b = await loc.boundingBox()
    if (!b) throw new Error('not visible')
    for (const m of modifiers) await p.keyboard.down(m)
    await p.mouse.move(b.x + b.width / 2, b.y + b.height / 2); await p.waitForTimeout(30)
    if (count === 2) await p.mouse.dblclick(b.x + b.width / 2, b.y + b.height / 2, { button })
    else await p.mouse.click(b.x + b.width / 2, b.y + b.height / 2, { button })
    for (const m of modifiers) await p.keyboard.up(m)
  }
  const panelStep = async (st) => {
    const box = p.locator(`.sketch-task [data-box="${st.panel}"]`), list = box.locator('[data-list]')
    const modifiers = st.mod === 'ctrl' ? ['Control'] : st.mod === 'shift' ? ['Shift'] : []
    if ('row' in st) {
      const row = list.locator(`li[data-row="${st.row}"]`)
      await row.evaluate((e) => e.scrollIntoView({ block: 'nearest' }))
      const target = st.panel === 'elements' && st.sub && st.sub !== 'label' ? row.locator(`[data-sub="${st.sub}"]`) : row.locator('.skp-text')
      const editing = async () => (await row.locator('[data-rename]').count()) > 0
      if ('check' in st) { const cb = row.locator('input[data-check]'); if ((await cb.isChecked()) !== st.check) await clickAt(cb) }
      else if ('menu' in st) {
        await clickAt(target, { button: 'right', modifiers }); await p.waitForTimeout(120)
        if (st.record) (panelRecord.menus ??= []).push(await ctxEntries())
        if (st.menu) await pickCtx(st.menu)
        else await p.keyboard.press('Escape')
        await p.waitForTimeout(150)
      } else if (st.dblclick) { await clickAt(target, { modifiers, count: 2 }); await p.waitForTimeout(150) }
      else if (!(await editing())) { await clickAt(target, { modifiers }); await p.waitForTimeout(100) }
      if ('rename' in st) {
        if (!(await editing())) { await list.press('F2'); await p.waitForTimeout(100) }
        const ed = row.locator('[data-rename]')
        await ed.fill(st.rename); await ed.press('Enter'); await p.waitForTimeout(120)
      }
    } else if (st.empty) {
      const b = await list.boundingBox()
      await p.mouse.click(b.x + b.width / 2, b.y + b.height - 3); await p.waitForTimeout(100)
    } else if ('filter' in st) {
      await clickAt(box.locator('[data-panel-filter]')); await p.waitForTimeout(100)
      const cb = p.locator(`[data-filter-popup="${st.panel}"] [data-filter-item="${st.filter}"] input`)
      const want = st.checked ?? !(await cb.isChecked())
      if ((await cb.isChecked()) !== want) await clickAt(cb)
      await p.keyboard.press('Escape'); await p.waitForTimeout(100)
    } else if ('filterBox' in st) {
      const cb = box.locator('[data-panel-filterbox]')
      if ((await cb.isChecked()) !== !!st.filterBox) await clickAt(cb)
      await p.waitForTimeout(100)
    } else if ('setting' in st) {
      await clickAt(box.locator('[data-panel-settings]')); await p.waitForTimeout(100)
      const e = (await ctxEntries()).find((x) => x !== 'sep' && x.text === st.setting)
      if (e && (st.checked === undefined || e.checked !== !!st.checked)) await pickCtx(st.setting)
      else await p.keyboard.press('Escape')
      await p.waitForTimeout(100)
    } else if (st.button) { await clickAt(box.locator({ showHideButton: '[data-panel-showhide]' }[st.button])); await p.waitForTimeout(120) }
  }
  for (const st of c.steps) {
    if (st.cmd) {
      await gui('run', [st.cmd]); await p.waitForTimeout(120)
      // the step's "dialog": the named fields of the dialog the command opens, set before it is accepted
      if (st.dialog) {
        for (let i = 0; i < 20 && !(await p.locator('.datum-dlg').count()); i++) await p.waitForTimeout(100)
        for (const [name, v] of Object.entries(st.dialog)) {
          const f = p.locator(`.datum-dlg [data-qf="${name}"]`).first()
          if (typeof v === 'boolean') { if ((await f.isChecked()) !== v) await f.click() }
          else { const t = f.locator('input'); await t.click(); await t.press('Control+a'); await t.type(String(v)); await t.press('Tab') }
        }
      }
    }
    else if (st.move) await move(st.move)
    else if (st.click) { await move([st.click[0] + 0.7, st.click[1] + 0.4]); await move(st.click); await p.mouse.down(); await p.waitForTimeout(60); await p.mouse.up(); await p.waitForTimeout(120) }
    else if (st.drag) {
      const [a, z] = st.drag
      await move(a); await p.mouse.down(); await p.waitForTimeout(60)
      for (let i = 1; i <= 6; i++) await move([a[0] + (z[0] - a[0]) * i / 6, a[1] + (z[1] - a[1]) * i / 6])
      await p.mouse.up(); await p.waitForTimeout(120)
    } else if (st.key) { await p.keyboard.press(KEY[st.key] ?? st.key); await p.waitForTimeout(80) }
    // typed where the focus is: an on-view parameter's box takes digits (fcsketch_dump.py's "type" and "fkey")
    else if (st.type) { await p.keyboard.type(st.type, { delay: 40 }); await p.waitForTimeout(80) }
    else if (st.fkey) { await p.keyboard.press((st.ctrl ? 'Control+' : '') + (KEY[st.fkey] ?? st.fkey)); await p.waitForTimeout(100) }
    else if (st.widget) { // a control of the Tool Parameters box, by its name in SketcherToolDefaultWidget.ui
      const w = p.locator(`[data-tool-widget="${st.widget.name}"]`).first()
      if ('checked' in st.widget) { if ((await w.isChecked()) !== !!st.widget.checked) await w.click() }
      else if ('index' in st.widget) await w.selectOption({ index: st.widget.index })
      else if ('value' in st.widget) { await w.click(); await w.press('Control+a'); await w.type(String(st.widget.value)); await w.press('Enter') }
      await p.waitForTimeout(120)
    }
    else if (st.select) { await gui('select', st.select); await p.waitForTimeout(80) }
    else if (st.pick) { await gui('select', [st.pick]); await p.waitForTimeout(1500) } // a model element: the projection is the server's
    else if ('clear' in st) { await gui('clear', []); await p.waitForTimeout(80) }
    else if (st.panel) { try { await panelStep(st) } catch (e) { if (process.env.SKETCHCHECK_TRACE) console.log('  at', await p.evaluate((r) => { const li = document.querySelector(`.sketch-task [data-box="${r.panel}"] li[data-row="${r.row}"]`); if (!li) return 'no row'; const b = li.getBoundingClientRect(); const t = document.elementFromPoint(b.x + b.width / 2, b.y + b.height / 2); return JSON.stringify(b) + ' ' + (t?.outerHTML.slice(0, 200)) }, st)); stepErrors.push(`${JSON.stringify(st)}: ${String(e.message).split('\n').filter((l, i) => i === 0 || /intercepts|not stable|not visible|outside/.test(l)).slice(0, 3).join(' ')}`) } }
    await dialog()
    await p.evaluate(() => new Promise((r) => requestAnimationFrame(() => r(0)))) // the page has handled the step (a frame) before the next
    if (process.env.SKETCHCHECK_TRACE) console.log('  trace', JSON.stringify(st), JSON.stringify((await api(`/api/gui?slug=${PROJECT}`)).sketch?.geometry), JSON.stringify(await p.evaluate(() => window.cadui.getState().hints)), await p.evaluate(() => [...document.querySelectorAll('.ctx, .mb-content, .msgbox-back')].map((e) => e.className + ':' + e.textContent.slice(0, 120)).join() + ' / ' + document.activeElement?.tagName + '.' + document.activeElement?.className))
  }
  await p.waitForTimeout(250)
  if (shots) await p.screenshot({ path: `${shots}/${c.name}.png` })
  const got = (await api(`/api/gui?slug=${encodeURIComponent(PROJECT)}`)).sketch
  const diffs = []
  if (!got || got.name !== name) diffs.push(`the sketch in edit is ${got?.name ?? 'none'}`)
  else {
    const g = got.geometry, gw = want.geometry
    if (g.length !== gw.length || !g.every((x, i) => sameGeo(x, gw[i]))) diffs.push(`geometry\n     ours     ${g.map(fmtG).join(' ')}\n     FreeCAD  ${gw.map(fmtG).join(' ')}`)
    const cs = got.constraints, cw = want.constraints
    if (cs.length !== cw.length || !cs.every((x, i) => sameCons(x, cw[i]))) diffs.push(`constraints\n     ours     ${cs.map(fmtC).join(' ')}\n     FreeCAD  ${cw.map(fmtC).join(' ')}`)
    const m = `${got.message.status}${got.message.link}`, mw = `${want.message.status}${want.message.link}`
    if (m !== mw) diffs.push(`message: ${m} (FreeCAD: ${mw})`)
    if (want.external) { // ExternalGeo after the axes, and ExternalGeometry's references
      const e = (got.external ?? []).map((x) => ({ ...x, construction: undefined })), ew = want.external
      if (e.length !== ew.length || !e.every((x, i) => sameGeo(x, ew[i]))) diffs.push(`external geometry\n     ours     ${e.map(fmtG).join(' ')}\n     FreeCAD  ${ew.map(fmtG).join(' ')}`)
      const r = JSON.stringify(got.external_geometry ?? []), rw = JSON.stringify(want.external_geometry)
      if (r !== rw) diffs.push(`external references: ${r} (FreeCAD: ${rw})`)
    }
  }
  // "check": ["widget", "ovp"]: the Tool Parameters box (title, each control's label, items, state) and the on-view
  // parameters' texts and which has the focus, as FreeCAD showed them at the end of the steps
  if (c.check?.includes('widget')) {
    const tw = await p.evaluate(() => window.cadui.sketchToolWidget?.() ?? null), tww = want.tool_widget ?? null
    const norm = (w) => w && JSON.stringify({ title: w.title, controls: w.controls.map((x) => ({ ...x, value: x.value === undefined ? undefined : +x.value.toFixed(4) })) })
    if (norm(tw) !== norm(tww)) diffs.push(`tool widget\n     ours     ${norm(tw)}\n     FreeCAD  ${norm(tww)}`)
  }
  if (c.check?.includes('ovp')) {
    // the boxes as a set (Qt lists them in the order they were made), each number to 0.3 (a pixel of the cursor is 0.16
    // mm), the unit and which one has the focus exactly
    const o = await p.evaluate(() => window.cadui.sketchOvps?.() ?? []), ow = want.ovp ?? []
    const parse = (x) => { const m = /^(-?[\d.]+)\s*(.*)$/.exec(x.text.trim()); return { v: m ? +m[1] : NaN, u: m ? m[2] : x.text, f: !!x.focus } }
    const left = ow.map(parse)
    const ok = o.length === ow.length && o.map(parse).every((a) => { const k = left.findIndex((b) => b.u === a.u && b.f === a.f && Math.abs(b.v - a.v) <= 0.3); if (k < 0) return false; left.splice(k, 1); return true })
    const show = (l) => l.map((x) => `${x.text}${x.focus ? '*' : ''}`).join(', ')
    if (!ok) diffs.push(`on-view parameters: ${show(o)} (FreeCAD: ${show(ow)})`)
  }
  // "check": ["panel", "state"]: what the task panel's lists show (each constraint row's text, hidden, checked, selected
  // and tooltip; each element row's GeoId, hidden and selected), the selection, the context menus a step recorded; and
  // each constraint's name, driving, active and virtual space states and its expression
  for (const e of stepErrors) diffs.push(`step ${e}`)
  if (c.check?.includes('panel')) {
    const o = await p.evaluate(() => window.cadui.sketchPanel?.() ?? null), w = want.panel ?? {}
    if (!o) diffs.push('no panel')
    else {
      const rowsC = (l) => JSON.stringify((l ?? []).map((r) => ({ text: r.text, hidden: r.hidden, checked: r.checked, selected: r.selected, tip: r.tip })))
      if (w.constraints && rowsC(o.constraints) !== rowsC(w.constraints)) diffs.push(`constraints list\n     ours     ${rowsC(o.constraints)}\n     FreeCAD  ${rowsC(w.constraints)}`)
      const rowsE = (l) => JSON.stringify((l ?? []).map((r) => ({ id: r.id, hidden: r.hidden, selected: r.selected })))
      if (w.elements && rowsE(o.elements) !== rowsE(w.elements)) diffs.push(`elements list\n     ours     ${rowsE(o.elements)}\n     FreeCAD  ${rowsE(w.elements)}`)
      // (FreeCAD names an element the Elements list selected in lower case, as SketchObject::convertSubName gives it)
      const selN = (l) => JSON.stringify((l ?? []).map((x) => x.toLowerCase()).sort())
      if (selN(o.selection) !== selN(w.selection)) diffs.push(`selection: ${JSON.stringify(o.selection)} (FreeCAD: ${JSON.stringify(w.selection ?? [])})`)
      const menu = (m) => JSON.stringify((m ?? []).map((l) => l.map((e) => (e === 'sep' ? e : `${e.text}${e.enabled ? '' : ' (off)'}${e.bold ? ' (bold)' : ''}`))))
      if (w.menus && menu(panelRecord.menus) !== menu(w.menus)) diffs.push(`context menus\n     ours     ${menu(panelRecord.menus)}\n     FreeCAD  ${menu(w.menus)}`)
    }
  }
  if (c.check?.includes('state') && got) {
    const st = (l) => JSON.stringify(l.map((k) => ({ name: k.name ?? '', driving: k.driving !== false, active: k.active !== false, virtual: !!k.virtual_space, expr: k.expr ?? '' })))
    if (st(got.constraints) !== st(want.constraints)) diffs.push(`constraint states\n     ours     ${st(got.constraints)}\n     FreeCAD  ${st(want.constraints)}`)
  }
  if (c.check?.length) await p.evaluate(() => window.cadui.sketchPanelReset?.())
  if (oldParams) await p.evaluate((ps) => window.cadui.setSketcherParams?.(ps), oldParams)
  if (diffs.length && KNOWN[c.name]) { known++; console.log(`known ${c.name}: ${KNOWN[c.name]}`) }
  else if (diffs.length) bad(`${c.name}: ${diffs.join('\n   ')}`)
  else { passed++; console.log(`OK   ${c.name}`) }
  // leave without saving, whatever the case left behind (a tool, a dialog)
  for (let i = 0; i < 3 && (await p.locator('.datum-dlg').count()); i++) await p.locator('.datum-dlg .qbtn').last().click()
  await gui('run', ['Sketcher_CancelSketch']); await p.waitForTimeout(300)
  // leaving takes longer after a big sketch: the next case's Edit Sketch is ignored while this one is still in edit
  for (let i = 0; i < 50 && (await p.locator('.sketch-task').count()); i++) await p.waitForTimeout(100)
  for (let i = 0; i < 3 && (await p.locator('.sketch-task').count()); i++) { notes.push(`${c.name}: Cancel sent again (the sketch was still in edit)`); await p.waitForTimeout(1000); await gui('run', ['Sketcher_CancelSketch']); await p.waitForTimeout(500) }
}
for (const d of SREF.dialogs ?? []) {
  if (only.length && !only.includes(d.case)) continue
  const o = dialogs.find((x) => x.case === d.case)
  if (!o) bad(`${d.case}: FreeCAD asks for the datum (${d.title}), we do not`)
  else if (o.title !== d.title) bad(`${d.case}: datum dialog "${o.title}" (FreeCAD: "${d.title}")`)
}
}
const allDialogs = SUITES.flatMap((s) => s.ref.dialogs ?? [])
for (const o of dialogs) if (!allDialogs.some((d) => d.case === o.case)) bad(`${o.case}: we ask for the datum (${o.title}), FreeCAD does not`)
for (const e of errs) bad(`page error: ${e}`)
for (const n of notes) console.log(`note ${n}`)
console.log(`sketchcheck: ${passed}/${run} cases as FreeCAD, ${known} known, ${colours} colours, ${problems.length} differences`)
process.exitCode = problems.length ? 1 : 0
await b.close()

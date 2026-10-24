// SPDX-License-Identifier: LGPL-2.1-or-later
// attachcheck: attachment in the page, held to the real FreeCAD's (ui/scripts/fcattach.json, written by fcattach.py from
// FreeCAD 26.3 at 3160daf1e2b6's GUI).
//
//   NODE_PATH=<folder with playwright> node ui/scripts/attachcheck.mjs [--fc=ui/scripts/fcattach.json] [--verbose]
//
// It starts a scratch workbench of its own (a temporary projects folder, CAD_* pointed at scratch paths, as editcheck.mjs
// does) with a Body holding the same 40 x 20 x 5 plate fcattach_dump.py makes, and in Chromium on SwiftShader does what
// that script did in FreeCAD:
//   sketch_on_face   the Pad's Face6 selected, New Sketch: the sketch, its support, mode, placement and transaction
//   datum_*          Edit > Create > Datums' commands with a selection (a face, two vertices, an edge) and without (then a
//                    pick in the tree or the 3D view, and Flip sides): the Attachment panel (its message, the reference
//                    buttons and lines, the mode list), then OK: the datum's type, name, mode, support, placement, and
//                    the transaction's name; Cancel makes nothing
//   edit             the first datum's double-click: the panel with its values
//   tree             the Body's rows with the datums (and the LCS's)
// A difference prints as FAIL, the deliberate ones (PARITY.md) as `known`. Exit 1 on a FAIL.
import { createRequire } from 'module'
import { spawn, spawnSync } from 'child_process'
import { mkdirSync, mkdtempSync, readFileSync } from 'fs'
import { createServer } from 'net'
import { tmpdir } from 'os'
import { dirname, join, resolve } from 'path'
import { fileURLToPath } from 'url'
const require = createRequire(import.meta.url)
const { chromium } = require('playwright')

const HERE = dirname(fileURLToPath(import.meta.url))
const REPO = resolve(HERE, '..', '..')
const args = process.argv.slice(2)
const flag = (name, d) => { const a = args.find((x) => x.startsWith(`--${name}=`)); return a ? a.slice(name.length + 3) : d }
const FC = JSON.parse(readFileSync(flag('fc', join(HERE, 'fcattach.json')), 'utf8'))
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
let pass = 0, fail = 0, known = 0
const ok = (what) => { pass++; if (args.includes('--verbose')) console.log(`  ok    ${what}`) }
const bad = (what, detail = '') => { fail++; console.log(`  FAIL  ${what}${detail ? `: ${detail}` : ''}`) }
const note = (what) => { known++; console.log(`  known ${what}`) }
const check = (cond, what, detail) => (cond ? ok(what) : bad(what, detail))

// ── a scratch workbench, with the plate ─────────────────────────────────────────────────────────────────────────
const freePort = (from) => new Promise((res, rej) => {
  const tryPort = (p) => {
    if (p > from + 40) return rej(new Error('no free port'))
    const s = createServer(); s.once('error', () => tryPort(p + 1)); s.once('listening', () => s.close(() => res(p))); s.listen(p, '127.0.0.1')
  }
  tryPort(from)
})
const scratch = mkdtempSync(join(tmpdir(), 'cad-attachcheck-')), warmDir = mkdtempSync('/tmp/cac')
const ROOT = join(scratch, 'root'); mkdirSync(ROOT)
for (const d of ['runtime', 'macros']) mkdirSync(join(scratch, d))
const python = process.env.CAD_PYTHON || join(REPO, '.venv', 'bin', 'python')
const env = { ...process.env, CAD_WARM_DIR: warmDir, CAD_RUNTIME_DIR: join(scratch, 'runtime'), CAD_MACRO_DIR: join(scratch, 'macros'),
  CAD_PREFS: join(scratch, 'prefs.json'), PYTHONPATH: REPO, CAD_PYTHON: python, CAD_RENDER_BACKEND: 'numpy' }
delete env.CAD_PROJECTS
const cad = (...argv) => spawnSync(python, ['-m', 'cad_agent', '--projects', ROOT, ...argv], { env, cwd: REPO, encoding: 'utf8' })
cad('init', 'att', '--brief', 'attachcheck')
cad('feature', 'new', 'att', 'Body')
const rect = [[[0, 0], [40, 0]], [[40, 0], [40, 20]], [[40, 20], [0, 20]], [[0, 20], [0, 0]]].map(([a, b]) => ({ type: 'LineSegment', start: a, end: b, construction: false }))
const cons = [0, 1, 2, 3].map((i) => ({ type: 'Coincident', args: [i, 2, (i + 1) % 4, 1], driving: true, name: '' }))
cad('feature', 'apply', 'att', 'Body', '--ops', JSON.stringify([
  { op: 'add', feature: { name: 'Sketch', type: 'Sketcher::SketchObject', support: 'XY', geometry: rect, constraints: cons } },
  { op: 'add', feature: { name: 'Pad', type: 'PartDesign::Pad', profile: 'Sketch', length: 5 } }]))
const port = await freePort(8911)
const server = spawn(python, ['-c', `import sys; from pathlib import Path; from cad_agent import serve; serve.run([Path(sys.argv[1])], host="127.0.0.1", port=${port})`, ROOT],
  { env, cwd: REPO, stdio: ['ignore', 'pipe', 'pipe'] })
await new Promise((res, rej) => {
  const t = setTimeout(() => rej(new Error('the scratch workbench did not start')), 60000)
  server.stdout.on('data', (d) => { if (/workbench: http/.test(String(d))) { clearTimeout(t); res() } })
  server.on('exit', (c) => rej(new Error(`the scratch workbench exited with ${c}`)))
})
const BASE = `http://127.0.0.1:${port}`

const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] })
const page = await browser.newPage({ viewport: { width: 1400, height: 950 } })
page.on('pageerror', (e) => bad('page error', e.message))
const st = (expr) => page.evaluate(expr)
const until = async (expr, what, ms = 60000, quiet = false) => {
  const t0 = Date.now()
  while (Date.now() - t0 < ms) { if (await st(expr)) return true; await sleep(200) }
  if (!quiet) bad(`timed out waiting: ${what}`)
  return false
}

// ── the panel, as fcattach_dump.py's task_widgets reads FreeCAD's ───────────────────────────────────────────────────
const fcPanel = (task) => {
  const w = task?.[0] ?? []
  const get = (name) => w.find((x) => x.name === name)
  return { message: get('message')?.text, buttons: [1, 2, 3, 4].map((i) => [get(`buttonRef${i}`)?.text, get(`buttonRef${i}`)?.enabled]),
    lines: [1, 2, 3, 4].map((i) => get(`lineRef${i}`)?.text), modes: get('listOfModes')?.items, offset: get('labelOffsetX')?.enabled }
}
const ourPanel = () => st(`(() => {
  const tv = document.querySelector('.taskview') ?? document
  const rows = [...tv.querySelectorAll('.tfield')].filter((r) => r.querySelector('button.qbtn') && r.querySelector('input'))
  return { message: tv.querySelector('.pd-attach-msg')?.textContent, buttons: rows.map((r) => [r.querySelector('button').textContent, !r.querySelector('button').disabled]),
    lines: rows.map((r) => r.querySelector('input').value), modes: [...tv.querySelectorAll('.pd-mode')].map((e) => e.textContent),
    offset: !tv.querySelector('fieldset.tgroup')?.disabled }
})()`)
async function comparePanel(fc, where) {
  const want = fcPanel(fc)
  // the panel settles when the server's attacher has answered: wait for FreeCAD's message and list, then compare all
  await until(`(() => { const m = document.querySelector('.taskview .pd-attach-msg')?.textContent; const l = [...document.querySelectorAll('.taskview .pd-mode')].map((e) => e.textContent)
    return m === ${JSON.stringify(want.message)} && JSON.stringify(l) === ${JSON.stringify(JSON.stringify(want.modes))} })()`, `${where}: the panel`, 15000, true)
  const got = await ourPanel()
  for (const k of ['message', 'buttons', 'lines', 'modes', 'offset']) {
    check(JSON.stringify(got[k]) === JSON.stringify(want[k]), `${where}: ${k}`, `\n        FreeCAD ${JSON.stringify(want[k])}\n        ours    ${JSON.stringify(got[k])}`)
  }
}
/** FreeCAD's AttachmentSupport as the part file names it: (Origin, "XY_Plane.") is the origin's XY_Plane itself. */
const fcSupport = (sup) => sup.flatMap(([o, subs]) => subs.map((s) => (o === 'Origin' ? [s.replace(/\.$/, '').replace(/^Origin001$/, 'Origin'), ''] : [o, s])))
const samePlacement = (a, b, tol = 1e-9) => a && b && a[0].every((x, i) => Math.abs(x - b[0][i]) <= tol * Math.max(1, Math.abs(b[0][i])))
  && Math.abs(Math.abs(a[1].reduce((s, x, i) => s + x * b[1][i], 0)) - 1) < tol
async function compareMade(fc, where) {
  for (const want of fc.made) {
    if (!await until(`cadui.getState().features.Body?.features.some((f) => f.name === ${JSON.stringify(want.name)} && f.attached)`, `${where}: ${want.name}`)) continue
    const f = await st(`cadui.getState().features.Body.features.find((f) => f.name === ${JSON.stringify(want.name)})`)
    check(f.type === want.type, `${where}: ${want.name} is a ${want.type}`, f.type)
    check((f.attached.map_mode ?? f.map_mode) === want.map_mode, `${where}: ${want.name}'s MapMode ${want.map_mode}`, f.attached.map_mode)
    check(JSON.stringify(f.attachment_support) === JSON.stringify(fcSupport(want.support)), `${where}: ${want.name}'s AttachmentSupport`,
      `${JSON.stringify(f.attachment_support)} vs FreeCAD's ${JSON.stringify(want.support)}`)
    check(!!f.map_reversed === !!want.reversed, `${where}: ${want.name}'s MapReversed`)
    const pl = f.attached.placement
    check(samePlacement([pl.position, pl.rotation], want.placement), `${where}: ${want.name}'s Placement`, `${JSON.stringify([pl.position, pl.rotation])} vs ${JSON.stringify(want.placement)}`)
  }
  if (fc.undo?.length) {
    const got = await st('cadui.getState().undo[0]?.name')
    if (fc.made.length) check(got === fc.undo[0], `${where}: the step is FreeCAD's "${fc.undo[0]}"`, got)
  }
}
const pickRow = async (ref) => { await st('cadui.showPanel("model")'); await page.click(`.trow[data-ref="${ref}"]`); await st('cadui.showPanel("tasks")') }
const bodyName = () => st('cadui.getState().scene?.bodies.find((b) => b.part === "Body")?.name')
async function selectSubs(subs) {
  const b = await bodyName()
  await st('cadui.select(null)')
  for (const [i, sub] of subs.entries()) await st(`cadui.select(${JSON.stringify(b)}, ${i > 0}, ${JSON.stringify(sub)})`)
}
const ok_ = async () => { await page.click('.taskview .pd-buttons .qbtn.default'); await until('!cadui.getState().task', 'the panel to close') }

try {
  await page.goto(`${BASE}/next/#att`)
  await until('!!window.cadui && cadui.getState().slug === "att" && !!cadui.getState().scene?.bodies.some((b) => b.part === "Body")', 'the plate')
  await st('cadui.setState({ workbench: "design", activeBody: "Body" })')
  await sleep(500)

  console.log('sketch on a face')
  await selectSubs(['Face6'])
  await st('cadui.newSketch()')
  await compareMade(FC.sketch_on_face, 'New Sketch on Face6')
  check(await until('cadui.getState().workbench === "sketcher"', 'the Sketcher', 30000, true), 'New Sketch on Face6: opens in the Sketcher')
  await st('document.querySelector(".sketch-task .qbtn")?.click()')       // Close
  await until('cadui.getState().workbench === "design"', 'Part Design again', 30000, true)

  const datum = async (key, type, opts = {}) => {
    console.log(key)
    const fc = FC[key]
    await st('cadui.setState({ featSel: [], selected: [], subSel: [] })')
    if (opts.sel) await selectSubs(opts.sel)
    await st(`cadui.createDatum(${JSON.stringify(type)})`)
    await until('cadui.getState().task?.kind === "attach"', `${key}: the panel`)
    await comparePanel(fc.task, `${key}`)
    if (opts.pick) { await opts.pick(); await comparePanel(fc.task_picked, `${key} after the pick`) }
    if (opts.flip) { await page.click('.taskview .tcheck input'); await comparePanel(fc.task_flipped, `${key} flipped`) }
    if (opts.cancel) {
      const n = await st('cadui.getState().features.Body.features.length')
      await page.click('.taskview .pd-buttons .qbtn:not(.default)')
      await sleep(500)
      check(await st(`cadui.getState().features.Body.features.length === ${n}`), `${key}: Cancel makes nothing`)
      return
    }
    await ok_()
    await compareMade(fc, key)
  }
  await datum('datum_plane_face', 'Part::DatumPlane', { sel: ['Face2'] })
  await datum('datum_plane_pick', 'Part::DatumPlane', { pick: () => pickRow('Body/XY_Plane'), flip: true })
  await datum('datum_line_vertices', 'Part::DatumLine', { sel: ['Vertex1', 'Vertex6'] })
  await datum('datum_point_edge', 'Part::DatumPoint', { sel: ['Edge4'] })
  await datum('lcs_pick', 'Part::LocalCoordinateSystem', { pick: async () => { await selectSubs(['Vertex6']) } })
  await datum('cancel', 'Part::DatumPlane', { sel: ['Face1'], cancel: true })

  console.log('edit')
  await st('cadui.setState({ featSel: [], selected: [], subSel: [] })')
  await st('cadui.editAttachment("Body", "DatumPlane")')
  await until('cadui.getState().task?.kind === "attach"', 'the edit panel')
  await comparePanel(FC.edit.task, 'Edit Attachment of DatumPlane')
  await page.click('.taskview .pd-buttons .qbtn:not(.default)')

  console.log('tree')
  await st('cadui.showPanel("model")')
  await st('cadui.setState({ featSel: [] })')
  for (const row of await st('[...document.querySelectorAll(".trow.pdrow .twisty")].map((t, i) => i)')) void row
  await page.evaluate(() => { for (const t of document.querySelectorAll('.trow.pdrow .twisty:not(.open)')) t.click() })
  await sleep(400)
  await page.evaluate(() => { for (const t of document.querySelectorAll('.trow.pdrow .twisty:not(.open)')) t.click() })
  await sleep(400)
  const ours = await st('[...document.querySelectorAll(".trow.pdrow")].map((r) => r.querySelector(".tname")?.textContent ?? r.querySelector("input")?.value)')
  const fcRows = FC.tree.filter((r) => r.depth >= 2 || r.text === 'Body').map((r) => r.text)
  const datumRows = (rows) => rows.filter((t) => /^(Datum|LCS|X-axis0|Y-axis0|Z-axis0|XY-plane0|XZ-plane0|YZ-plane0|Origin-Point0)/.test(t))
  check(JSON.stringify(datumRows(ours)) === JSON.stringify(datumRows(fcRows)), 'tree: the datums\' rows, and the LCS\'s, as FreeCAD shows them',
    `\n        FreeCAD ${JSON.stringify(datumRows(fcRows))}\n        ours    ${JSON.stringify(datumRows(ours))}`)
} catch (e) {
  bad('attachcheck stopped', e.stack ?? String(e))
} finally {
  await browser.close()
  server.kill()
}
console.log(`attachcheck: ${pass} ok, ${fail} failing, ${known} known differences`)
process.exit(fail ? 1 : 0)

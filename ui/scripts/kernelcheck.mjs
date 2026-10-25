// SPDX-License-Identifier: LGPL-2.1-or-later
// kernelcheck: what cad_agent's kernel round adds to PartDesign's panels (a Pocket's Start Reference, Taper angle and
// Operation Common; Multi-Transform's Add Scale Transformation), held to the real FreeCAD's (ui/scripts/fckernel.json,
// written by fckernel.py from FreeCAD 26.3 at 3160daf1e2b6), then driven end to end.
//
//   NODE_PATH=<folder with playwright> node ui/scripts/kernelcheck.mjs [--fc=ui/scripts/fckernel.json] [--keep] [--verbose]
//
// It starts a scratch workbench of its own (as revolvecheck.mjs does) and, in Chromium on SwiftShader:
//   pocket  a Body as fckernel_dump.py makes it (a 40 x 20 x 10 plate, a circle r 6 on its top), PartDesign_Pocket: the
//           Start combo, the Taper angle and the Operation as the panel opens; Start Reference shows the Reference row with
//           FreeCAD's "Cancel" and "Select face, plane..."; a click on the plate's Face6 makes it "Pad:Face6" and the button
//           "Pick Reference"; a 10 degree taper, Common, Through all (the taper stays), Two sided (Side 2's taper shows),
//           One sided; OK is "Make Pocket" and the feature has FreeCAD's StartType, StartReference, TaperAngle, Operation,
//           Type after OK; the Body builds; the property view shows Taper Angle, Taper Angle2 (read-only), Operation and
//           Start Reference as FreeCAD's does
//   multi   PartDesign_MultiTransform on the Pocket: the list's context menu; Add Scale Transformation adds "Scale" with
//           Factor 2 and Occurrences 2; OK is "Make MultiTransform" and the Body builds; the Scale's property view starts
//           with Factor and Occurrences, as FreeCAD's
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
const FC = JSON.parse(readFileSync(flag('fc', join(HERE, 'fckernel.json')), 'utf8'))
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
let pass = 0, fail = 0, known = 0
const ok = (what) => { pass++; if (args.includes('--verbose')) console.log(`  ok    ${what}`) }
const bad = (what, detail = '') => { fail++; console.log(`  FAIL  ${what}${detail ? `: ${detail}` : ''}`) }
const note = (what) => { known++; console.log(`  known ${what}`) }
const check = (cond, what, detail) => (cond ? ok(what) : bad(what, detail))
const same = (a, b, what) => check(JSON.stringify(a) === JSON.stringify(b), what, `\n        FreeCAD ${JSON.stringify(b)}\n        ours    ${JSON.stringify(a)}`)
const qty = (t) => String(t ?? '').replace(/\s+/g, '')        // "10.00 °" and "10.00°" are the same text

// ── a scratch workbench ──────────────────────────────────────────────────────────────────────────────────────────────
const freePort = (from) => new Promise((res, rej) => {
  const tryPort = (p) => {
    if (p > from + 40) return rej(new Error('no free port'))
    const s = createServer(); s.once('error', () => tryPort(p + 1)); s.once('listening', () => s.close(() => res(p))); s.listen(p, '127.0.0.1')
  }
  tryPort(from)
})
const scratch = mkdtempSync(join(tmpdir(), 'cad-kernelcheck-')), warmDir = mkdtempSync('/tmp/ckc')
const ROOT = join(scratch, 'root'); mkdirSync(ROOT)
for (const d of ['runtime', 'macros']) mkdirSync(join(scratch, d))
const python = process.env.CAD_PYTHON || join(REPO, '.venv', 'bin', 'python')
const env = { ...process.env, CAD_WARM_DIR: warmDir, CAD_RUNTIME_DIR: join(scratch, 'runtime'), CAD_MACRO_DIR: join(scratch, 'macros'),
  CAD_PREFS: join(scratch, 'prefs.json'), PYTHONPATH: REPO, CAD_PYTHON: python, CAD_RENDER_BACKEND: 'numpy' }
delete env.CAD_PROJECTS
spawnSync(python, ['-m', 'cad_agent', '--projects', ROOT, 'init', 'kern', '--brief', 'kernelcheck'], { env, cwd: REPO })
const port = await freePort(8961)
const server = spawn(python, ['-c', `import sys; from pathlib import Path; from cad_agent import serve; serve.run([Path(sys.argv[1])], host="127.0.0.1", port=${port})`, ROOT],
  { env, cwd: REPO, stdio: ['ignore', 'pipe', 'pipe'] })
await new Promise((res, rej) => {
  const t = setTimeout(() => rej(new Error('the scratch workbench did not start')), 60000)
  server.stdout.on('data', (d) => { if (/workbench: http/.test(String(d))) { clearTimeout(t); res() } })
  server.on('exit', (c) => rej(new Error(`the scratch workbench exited with ${c}`)))
})
const BASE = `http://127.0.0.1:${port}`
const post = async (path, body) => (await fetch(BASE + path, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CAD': '1' }, body: JSON.stringify(body) })).json()
const cad = async (argv) => post('/api/cad', { slug: 'kern', argv })

const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] })
const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } })
page.on('pageerror', (e) => bad('page error', e.message))
const st = (expr) => page.evaluate(expr)
const until = async (expr, what, ms = 90000) => {
  const t0 = Date.now()
  while (Date.now() - t0 < ms) { if (await st(expr)) return true; await sleep(250) }
  bad(`timed out waiting: ${what}`); return false
}
const qf = (name) => st(`(() => { const e = document.querySelector('.taskview [data-qf="${name}"]'); if (!e) return null
  const input = e.tagName === 'INPUT' ? e : e.querySelector('input')
  return { text: e.tagName === 'BUTTON' ? e.textContent : (e.querySelector('.combo-label')?.textContent ?? input?.value ?? ''), placeholder: input?.placeholder ?? null } })()`)
const comboItems = async (name) => {
  await page.click(`.taskview [data-qf="${name}"]`); await sleep(150)
  const items = await st('[...document.querySelectorAll(".combo-popup .combo-item")].map((e) => e.textContent)')
  await page.keyboard.press('Escape'); await sleep(100)
  return items
}
const pick = async (label, text) => {
  const b = page.locator('.taskview .pd-form label.tfield', { has: page.locator(`span:text-is("${label}")`) }).locator('.qselect').first()
  await b.click(); await sleep(150)
  await page.locator('.combo-popup .combo-item', { hasText: text }).first().click()
  await sleep(400)
}
const pickQf = async (name, text) => {
  await page.click(`.taskview [data-qf="${name}"]`); await sleep(150)
  await page.locator('.combo-popup .combo-item', { hasText: text }).first().click()
  await sleep(400)
}
const rect = (x0, y0, x1, y1) => [[x0, y0, x1, y0], [x1, y0, x1, y1], [x1, y1, x0, y1], [x0, y1, x0, y0]].map(([a, b, c, d]) => ({ type: 'LineSegment', start: [a, b], end: [c, d], construction: false }))
const propRows = () => st('[...document.querySelectorAll(".prow")].map((r) => ({ name: r.querySelector(".pk")?.textContent ?? "", ro: !!r.querySelector(".pk span[title^=\'Read-only\']"), value: r.querySelector(".pv")?.textContent ?? "" }))')
const fcRows = (dump) => (dump?.[0] ?? []).filter((r) => r.depth === 1)

try {
  await page.goto(`${BASE}/next/#kern`)
  await until('!!window.cadui && cadui.getState().slug === "kern" && !!cadui.getState().scene', 'the project to open')
  await st('cadui.setState({ workbench: "design" })')
  await sleep(300)

  // ── Pocket: Start Reference, Taper angle, Operation ─────────────────────────────────────────────────────────────────
  console.log('pocket')
  const P = FC.pocket
  await cad(['feature', 'new', 'kern', 'Plate'])
  await post('/api/kern/features/Plate', { ops: [
    { op: 'add', feature: { name: 'Sketch', type: 'Sketcher::SketchObject', support: 'XY', geometry: rect(0, 0, 40, 20), constraints: [] } },
    { op: 'add', feature: { name: 'Pad', type: 'PartDesign::Pad', profile: 'Sketch', length: 10 } },
    { op: 'add', feature: { name: 'Sketch001', type: 'Sketcher::SketchObject', support: 'XY', attachment_offset: [0, 0, 10], geometry: [{ type: 'Circle', center: [20, 10], radius: 6, construction: false }], constraints: [] } }] })
  await st('cadui.loadFeatures()')
  await until('cadui.getState().features.Plate?.features.some((f) => f.name === "Sketch001")', 'the plate')
  await until('cadui.getState().scene?.bodies.some((b) => b.part === "Plate")', 'the plate in the scene')
  await st('cadui.setState({ activeBody: "Plate", featSel: ["Plate/Sketch001"], selected: [] })')
  await page.click('.tb-btn[data-cmd="PartDesign_Pocket"]')
  await until('document.querySelector(".taskview .tbox-head span")?.textContent === "Pocket Parameters"', 'the Pocket panel')
  await sleep(600)
  same((await qf('startMode'))?.text, P.task.startMode.current, 'Pocket: Start as it opens')
  same(await comboItems('startMode'), P.task.startMode.items, 'Pocket: the Start list (Reference enabled)')
  same(qty((await qf('taperEdit'))?.text), qty(P.task.taperEdit.text), 'Pocket: Taper angle as it opens')
  same((await qf('comboOperation'))?.text, P.task.comboOperation.current, 'Pocket: Operation as it opens')
  same(await comboItems('comboOperation'), P.task.comboOperation.items, 'Pocket: the Operation list')
  check(!(await qf('lineStartReference')), 'Pocket: no Reference row for Profile plane, as FreeCAD')
  await pickQf('startMode', 'Reference')
  for (const [step, fc] of [['Start Reference', P.task_reference]]) {
    const line = await qf('lineStartReference'), btn = await qf('buttonStartReference')
    same([line?.text, line?.placeholder], [fc.lineStartReference.text, fc.lineStartReference.placeholder], `Pocket, ${step}: the reference line picks at once`)
    same(btn?.text, fc.buttonStartReference.text, `Pocket, ${step}: the button says "${fc.buttonStartReference.text}"`)
    check(!!(await qf('startOffset')) || (await st('[...document.querySelectorAll(".taskview .tfield > span")].some((e) => e.textContent === "Offset")')), `Pocket, ${step}: Offset shows too, as FreeCAD`)
  }
  // a click on the plate's top face in the 3D view (the Tip is the Pad)
  const bodyName = await st('cadui.getState().scene.bodies.find((b) => b.part === "Plate").name')
  await st(`cadui.setState({ subSel: ["${bodyName}.Face6"], selected: [] })`)
  await sleep(500)
  {
    const line = await qf('lineStartReference'), btn = await qf('buttonStartReference')
    same([line?.text, line?.placeholder], [P.task_pick.lineStartReference.text, P.task_pick.lineStartReference.placeholder], 'Pocket: the picked face is "Pad:Face6"')
    same(btn?.text, P.task_pick.buttonStartReference.text, 'Pocket: the button is back to "Pick Reference"')
  }
  await st('cadui.setState({ subSel: [] })')
  await page.click('.taskview [data-qf="taperEdit"] input')
  await page.keyboard.press('Control+A'); await page.keyboard.type('10'); await page.keyboard.press('Tab')
  await sleep(300)
  same(qty((await qf('taperEdit'))?.text), qty(P.task_taper.taperEdit.text), 'Pocket: Taper angle 10°')
  await pickQf('comboOperation', 'Common')
  same((await qf('comboOperation'))?.text, P.task_common.comboOperation.current, 'Pocket: Operation Common')
  await pick('Type', 'Through all')
  check(!!(await qf('taperEdit')) === !!P.task_through_all.taperEdit, 'Pocket: Through all keeps the Taper angle, as FreeCAD')
  await pick('Direction', 'Two sided')
  check(!!(await qf('taperEdit2')) === !!P.task_two_sided.taperEdit2, 'Pocket: Two sided shows Side 2\'s Taper angle, as FreeCAD')
  same(qty((await qf('taperEdit2'))?.text), qty(P.task_two_sided.taperEdit2?.text), 'Pocket: Side 2\'s Taper angle starts at 0')
  await pick('Direction', 'One sided')
  check(!(await qf('taperEdit2')) && !P.task_one_sided.taperEdit2, 'Pocket: One sided hides Side 2\'s Taper angle')
  await page.click('.taskview .pd-buttons .qbtn.default')
  await until('cadui.getState().features.Plate.features.some((f) => f.name === "Pocket")', 'the Pocket')
  check(await until('cadui.getState().undo[0]?.name === "Make Pocket"', 'the step', 60000), 'Pocket: OK is one step, "Make Pocket"')
  const pk = await st('cadui.getState().features.Plate.features.find((f) => f.name === "Pocket")')
  const A = P.props_after
  same([pk?.start_type, pk?.start_reference, pk?.taper_angle, pk?.operation, pk?.type1, pk?.side_type],
    [A.StartType.value, [A.StartReference.value[0], A.StartReference.value[1][0]], A.TaperAngle.value, A.Operation.value, A.Type.value, A.SideType.value],
    'Pocket: written with FreeCAD\'s StartType, StartReference, TaperAngle, Operation, Type, SideType after OK')
  const src = readFileSync(join(ROOT, 'kern', 'parts', 'Plate.py'), 'utf8')
  check(/Pocket\("Pocket", "Sketch001", type="ThroughAll", start_type="Reference", start_reference=\("Pad", "Face6"\), taper_angle=10(\.0)?, operation="Common"\)/.test(src),
    'Pocket: the part file\'s line', src.split('\n').find((l) => l.includes('Pocket(')))
  // the build, asked with an op that changes nothing: the Tip set where it is
  const build = async () => cad(['feature', 'apply', 'kern', 'Plate', '--ops', JSON.stringify([{ op: 'tip', name: (await st('cadui.getState().features.Plate.tip')) }])])
  { const r = await build(); check(r.data?.built === true || r.built === true, 'Pocket: the Body builds', JSON.stringify(r).slice(0, 400)) }
  // the property view
  await st('cadui.showPanel("model")')
  await page.click('.trow[data-ref="Plate/Pocket"] .tname')
  await sleep(600)
  const ours = await propRows(), fcp = fcRows(FC.props_Pocket)
  for (const n of ['Taper Angle', 'Taper Angle2', 'Operation', 'Start Type', 'Start Reference']) {
    const o = ours.find((r) => r.name === n || r.name.endsWith(n)), f = fcp.find((r) => r.name === n)
    if (!o || !f) { bad(`Pocket's property view: ${n}`, `ours ${JSON.stringify(o)} FreeCAD ${JSON.stringify(f)}`); continue }
    if (n === 'Start Reference') {
      same(o.value, f.value, 'Pocket\'s property view: Start Reference shows "Pad [Face6]"')
      if (f.editable && o.ro) note('Start Reference: FreeCAD edits the link in the property view; here it is picked in the panel')
      continue
    }
    if (n !== 'Operation' && n !== 'Start Type') same(qty(o.value), qty(f.value), `Pocket's property view: ${n} ${f.value}`)
    same(!o.ro, f.editable, `Pocket's property view: ${n} ${f.editable ? 'editable' : 'read-only'}, as FreeCAD`)
  }

  // ── Multi-Transform: Add Scale Transformation ──────────────────────────────────────────────────────────────────────
  console.log('multi')
  const M = FC.multi
  await st('cadui.setState({ featSel: ["Plate/Pocket"], selected: [], subSel: [] })')
  await page.click('.tb-btn[data-cmd="PartDesign_MultiTransform"]')
  await until('cadui.getState().task?.kind === "pdTransform"', 'the Multi-Transform panel')
  await sleep(400)
  await page.click('.taskview [data-qf="listTransformFeatures"]', { button: 'right' })
  await sleep(300)
  const menu = await st('[...document.querySelectorAll(".ctx > *")].filter((e) => !e.classList.contains("mb-sep")).map((e) => ({ text: e.textContent.trim(), enabled: !e.classList.contains("dis") && !e.getAttribute("aria-disabled") }))')
  same(menu.map((e) => e.text), M.actions.filter((a) => !a.separator).map((a) => a.text), 'Multi-Transform: the context menu, entry by entry')
  same(menu.find((e) => e.text === 'Add Scale Transformation')?.enabled, true, 'Multi-Transform: Add Scale Transformation enabled')
  await page.click('.ctx .mb-item:has-text("Add Scale Transformation")')
  await sleep(500)
  same(await st('[...document.querySelectorAll(".taskview [data-qf=listTransformFeatures] .pdx-item")].map((e) => e.textContent)'), M.transformations, 'Multi-Transform: Add Scale Transformation adds "Scale"')
  same(Number((await qf('spinFactor'))?.text), parseFloat(M.task.spinFactor.text), 'Multi-Transform: the Scale\'s Factor')
  same(Number((await qf('spinOccurrences'))?.text), Number(M.task.spinOccurrences.text), 'Multi-Transform: the Scale\'s Occurrences')
  // a factor of 2 cuts the whole plate away, in FreeCAD too (an empty Body, which a part file does not take): 0.5
  await page.fill('.taskview [data-qf="spinFactor"]', '0.5'); await sleep(300)
  await page.click('.taskview .pdx-sub .qbtn:text-is("OK")')
  await page.click('.taskview .pd-buttons .qbtn.default')
  if (!await until('cadui.getState().features.Plate.features.some((f) => f.name === "MultiTransform")', 'MultiTransform', 60000))
    console.log('        report:', JSON.stringify(await st('(cadui.getState().report ?? cadui.getState().log ?? []).slice(-5)')), JSON.stringify(await st('cadui.getState().task')))
  check(await until('cadui.getState().undo[0]?.name === "Make MultiTransform"', 'the step', 60000), 'Multi-Transform: OK is one step, "Make MultiTransform"')
  const mt = await st('cadui.getState().features.Plate.features.find((f) => f.name === "MultiTransform")')
  const sc = mt?.transformations?.[0]
  same([sc?.name, sc?.type, sc?.factor, sc?.occurrences], [M.new[0][0], M.new[0][1], 0.5, M.props_scale.Occurrences.value], 'Multi-Transform: its Scale is FreeCAD\'s (name, type, Occurrences) with Factor 0.5')
  { const r = await build(); check(r.data?.built === true || r.built === true, 'Multi-Transform: the Body builds', JSON.stringify(r).slice(0, 400)) }
  // the Scale's property view
  await st('cadui.showPanel("model")')
  const scaleRow = await st('!!document.querySelector(\'.trow[data-ref="Plate/Scale"] .tname\')')
  if (!scaleRow) await page.click('.trow[data-ref="Plate/MultiTransform"] .twisty').catch(() => {})
  await sleep(300)
  await page.click('.trow[data-ref="Plate/Scale"] .tname').catch(() => {})
  await sleep(600)
  const ourBase = (await propRows()).map((r) => r.name.replace(/\s+$/, ''))
  const fcBase = fcRows(FC.props_Scale).slice(0, 6).map((r) => r.name)
  same(ourBase.slice(0, 6), fcBase, 'Scale\'s property view: Base starts Factor, Occurrences, Originals, Transform Mode, Label, Suppressed')
} catch (e) {
  bad('kernelcheck stopped', e.stack ?? String(e))
} finally {
  await browser.close()
  server.kill('SIGTERM')
  spawnSync(python, ['-P', '-m', 'cad_agent.warm', 'warm', 'stop'], { env, cwd: REPO, timeout: 60000 })
  if (!args.includes('--keep')) for (const d of [scratch, warmDir]) rmSync(d, { recursive: true, force: true })
}
console.log(`kernelcheck: ${pass} ok, ${fail} failing, ${known} known differences`)
process.exit(fail ? 1 : 0)

// SPDX-License-Identifier: LGPL-2.1-or-later
// dressupcheck: PartDesign's dress-up features (Fillet, Chamfer, Draft, Thickness) in the page, held to the real FreeCAD's
// (ui/scripts/fcdressup.json, written by fcdressup.py from FreeCAD 26.3 at 3160daf1e2b6), and driven end to end.
//
//   NODE_PATH=<folder with playwright> node ui/scripts/dressupcheck.mjs [--fc=ui/scripts/fcdressup.json] [--keep] [--verbose]
//
// It starts a scratch workbench of its own (as editcheck.mjs does) with one project holding a Body per case, each a
// 40 x 20 x 5 Pad as fcdressup_dump.py makes it, and in Chromium on SwiftShader:
//   menu      Part Design > Dress-Up Features and the Dress-Up toolbar against FreeCAD's (text, command)
//   cases     the case's edges or faces selected on the Body (or the Body whole, or nothing), the command's toolbar button:
//             the panel's title, Select's text (Select, or Confirm Selection when FreeCAD starts selecting), the
//             references' list, the fields and check boxes with FreeCAD's labels, defaults and states, the list's actions;
//             Select pressed, then a real click on an element of the base in the 3D view adds it to the list as FreeCAD's
//             pick does, a second click on it takes it off, a third puts it back; Confirm Selection; OK: the feature's
//             Base, the Tip, the undo step's name ("Make Fillet") and the solid's volume against FreeCAD's; the property
//             view's groups and rows against FreeCAD's
//   edit      a double-click on the Fillet: its panel with its references, the radius changed, OK is one step, "Edit Fillet"
// Exit 1 on a FAIL.
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
const FC = JSON.parse(readFileSync(flag('fc', join(HERE, 'fcdressup.json')), 'utf8'))
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
let pass = 0, fail = 0, known = 0
const ok = (what) => { pass++; if (args.includes('--verbose')) console.log(`  ok    ${what}`) }
const bad = (what, detail = '') => { fail++; console.log(`  FAIL  ${what}${detail ? `: ${detail}` : ''}`) }
const note = (what) => { known++; console.log(`  known ${what}`) }
const check = (cond, what, detail) => (cond ? ok(what) : bad(what, detail))
const clean = (t) => String(t ?? '').replace(/&(.)/g, '$1').trim()
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b)

// ── a scratch workbench, one Body per case ───────────────────────────────────────────────────────────────────────────
const CASES = [ // [case in fcdressup.json, part, command, selection: subs | 'whole' | [], the element picked while selecting]
  ['fillet', 'P_fillet', 'PartDesign_Fillet', ['Edge1'], 'Edge2'],
  ['fillet_all', 'P_fillet_all', 'PartDesign_Fillet', 'whole', null],
  ['chamfer', 'P_chamfer', 'PartDesign_Chamfer', ['Edge4'], 'Edge7'],
  ['draft', 'P_draft', 'PartDesign_Draft', ['Face1'], 'Face2'],
  ['thickness', 'P_thickness', 'PartDesign_Thickness', ['Face6'], 'Face1'],
  ['none_fillet', 'P_none', 'PartDesign_Fillet', [], null],
]
const freePort = (from) => new Promise((res, rej) => {
  const tryPort = (p) => {
    if (p > from + 40) return rej(new Error('no free port'))
    const s = createServer(); s.once('error', () => tryPort(p + 1)); s.once('listening', () => s.close(() => res(p))); s.listen(p, '127.0.0.1')
  }
  tryPort(from)
})
const scratch = mkdtempSync(join(tmpdir(), 'cad-dressupcheck-')), warmDir = mkdtempSync('/tmp/cdc')
const ROOT = join(scratch, 'root'); mkdirSync(ROOT)
for (const d of ['runtime', 'macros']) mkdirSync(join(scratch, d))
const python = process.env.CAD_PYTHON || join(REPO, '.venv', 'bin', 'python')
const env = { ...process.env, CAD_WARM_DIR: warmDir, CAD_RUNTIME_DIR: join(scratch, 'runtime'), CAD_MACRO_DIR: join(scratch, 'macros'),
  CAD_PREFS: join(scratch, 'prefs.json'), PYTHONPATH: REPO, CAD_PYTHON: python, CAD_RENDER_BACKEND: 'numpy' }
delete env.CAD_PROJECTS
const cad = (...a) => spawnSync(python, ['-m', 'cad_agent', '--projects', ROOT, ...a], { env, cwd: REPO, encoding: 'utf8' })
cad('init', 'dress', '--brief', 'dressupcheck')
const rect = [[0, 0, 40, 0], [40, 0, 40, 20], [40, 20, 0, 20], [0, 20, 0, 0]].map(([a, b, c, d]) => ({ type: 'LineSegment', start: [a, b], end: [c, d], construction: false }))
const coinc = [0, 1, 2, 3].map((i) => ({ type: 'Coincident', args: [i, 2, (i + 1) % 4, 1] }))
for (const [, part] of CASES) {
  cad('feature', 'new', 'dress', part)
  const ops = [{ op: 'add', feature: { name: 'Sketch', type: 'Sketcher::SketchObject', support: 'XY', geometry: rect, constraints: coinc } },
    { op: 'add', feature: { name: 'Pad', type: 'PartDesign::Pad', profile: 'Sketch', length: 5 } }]
  const r = cad('feature', 'apply', 'dress', part, '--ops', JSON.stringify(ops))
  if (r.status > 2) bad(`making ${part}`, r.stdout + r.stderr)
}
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
const until = async (expr, what, ms = 90000) => {
  const t0 = Date.now()
  while (Date.now() - t0 < ms) { if (await st(expr)) return true; await sleep(250) }
  bad(`timed out waiting: ${what}`); return false
}
const volume = (part) => {
  const r = spawnSync(python, ['-c', `import sys, importlib.util
spec = importlib.util.spec_from_file_location("p", sys.argv[1]); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print(round(m.build(**m.PARAMS).volume, 6))`, join(ROOT, 'dress', 'parts', `${part}.py`)], { env, cwd: REPO, encoding: 'utf8' })
  return r.status === 0 ? Number(r.stdout.trim()) : null
}
// the panel as a person reads it, in order: the title, Select, the list, labels with their values and check boxes
const panel = () => st(`(() => {
  const tv = document.querySelector('.taskview')
  if (!tv) return null
  const heads = [...tv.querySelectorAll('.tbox-head span')].map((e) => e.textContent).filter((t) => t)
  const select = tv.querySelector('.pd-refsel')
  const fields = [...tv.querySelectorAll('.pd-form .tfield, .pd-form .tcheck, .tbox-body > .tcheck')].map((el) => {
    const box = el.querySelector('input[type=checkbox]'); const input = el.querySelector('input:not([type=checkbox])'); const combo = el.querySelector('.combo-label')
    const btn = el.querySelector(':scope > button')
    return { label: (el.querySelector(':scope > span')?.textContent ?? btn?.textContent ?? el.textContent).trim(), value: input?.value ?? null, combo: combo?.textContent ?? null,
      checked: box ? box.checked : null, enabled: box ? !box.disabled : null }
  })
  return { heads, select: select ? { text: select.textContent, pressed: select.getAttribute('aria-pressed') === 'true', enabled: !select.disabled } : null,
    list: [...tv.querySelectorAll('.pd-reflist [role=option]')].map((e) => e.textContent), listEnabled: tv.querySelector('.pd-reflist')?.getAttribute('aria-disabled') !== 'true', fields }
})()`)
const listOf = async () => (await panel())?.list ?? []
// FreeCAD's widgets read the same way: labels (with the widget right of them), buttons, check boxes
function fcPanel(task) {
  const ws = task[0]
  const out = { heads: ws.filter((w) => w.class.endsWith('ActionLabel')).map((w) => w.text), select: ws.find((w) => w.name === 'buttonRefSel'),
    list: ws.find((w) => w.name === 'listWidgetReferences'), fields: [] }
  for (const w of ws) {
    if (w.class === 'QLabel' && w.text) {
      const right = ws.filter((x) => x !== w && Math.abs(x.y - w.y) < 12 && x.x > w.x && x.class !== 'QLabel').sort((a, b) => a.x - b.x)[0]
      out.fields.push({ label: w.text, value: right?.class === 'QLineEdit' || right?.class?.endsWith('QuantitySpinBox') ? right.text : null, combo: right?.class === 'QComboBox' ? right.current : null, items: right?.items ?? null })
    } else if (w.class === 'QCheckBox') out.fields.push({ label: w.text, checked: w.checked, enabled: w.enabled })
    else if (w.class === 'QToolButton' && w.text && w.name !== 'buttonRefSel') out.fields.push({ label: w.text, button: true })
  }
  return out
}
function holdPanel(us, fcTask, what) {
  const fc = fcPanel(fcTask)
  check(same(us.heads, fc.heads), `${what}: the task boxes ${fc.heads.join(', ')}`, JSON.stringify(us.heads))
  check(us.select?.text === fc.select.text, `${what}: the select button reads "${fc.select.text}"`, us.select?.text)
  check(us.select?.enabled === fc.select.enabled, `${what}: Select ${fc.select.enabled ? 'enabled' : 'greyed'}`, String(us.select?.enabled))
  check(same(us.list, fc.list.items), `${what}: the references' list ${JSON.stringify(fc.list.items)}`, JSON.stringify(us.list))
  check(us.listEnabled === fc.list.enabled, `${what}: the list ${fc.list.enabled ? 'enabled' : 'greyed'}`)
  for (const f of fc.fields) {
    const u = us.fields.find((x) => x.label === f.label || x.label.startsWith(f.label))
    if (!u) { bad(`${what}: "${f.label}"`, `not in the panel: ${JSON.stringify(us.fields.map((x) => x.label))}`); continue }
    if (f.checked !== undefined) check(u.checked === f.checked && u.enabled === f.enabled, `${what}: "${f.label}" ${f.checked ? 'checked' : 'unchecked'}${f.enabled ? '' : ', greyed'}`, JSON.stringify(u))
    if (f.value) check(u.value === f.value, `${what}: "${f.label}" starts at ${f.value}`, u.value)
    if (f.combo) check(u.combo === f.combo, `${what}: "${f.label}" shows ${f.combo}`, u.combo)
  }
  return fc
}
const VIEWS = ['Std_ViewIsometric', 'Std_ViewFront', 'Std_ViewRight', 'Std_ViewTop', 'Std_ViewRear', 'Std_ViewLeft', 'Std_ViewBottom']
async function clickElement(name) {
  for (const v of [null, ...VIEWS]) {
    if (v) { await st(`cadui.getCommand(${JSON.stringify(v)})?.run([])`); await sleep(500); await st('cadui.getCommand("Std_ViewFitAll")?.run([])'); await sleep(700) }
    if (args.includes('--verbose')) console.log('    camera', v, await st('JSON.stringify(cadui.getView().viewer.camera.getCamera().position)'))
    const p = await st(`cadui.getView().helperPoint('pd-dressup', ${JSON.stringify(name)})`)
    if (p) { await page.mouse.move(p.x, p.y); await sleep(120); await page.mouse.click(p.x, p.y); await sleep(250); return true }
  }
  const why = await st(`(() => { const v = cadui.getView(), h = v.helpers?.get('pd-dressup'); if (!h) return 'no helper'; const names = []; h.traverse((o) => { if (o.userData.pickName) names.push(o.userData.pickName) }); return names.length + ' named: ' + names.slice(0, 30).join(' ') })()`)
  const probe = await st(`(() => { try { const v = cadui.getView(), h = v.helpers.get('pd-dressup'); let o = null; h.traverse((x) => { if (x.userData.pickName === ${JSON.stringify(name)}) o = x });
    const cam = v.viewer.camera.getCamera(); cam.updateMatrixWorld(); const toS = v.screenOf(cam); const pos = o.geometry.attributes.position;
    const V = h.position.constructor; const a = new V().fromBufferAttribute(pos, 0).add(new V().fromBufferAttribute(pos, 1)).multiplyScalar(0.5).applyMatrix4(o.matrixWorld); const sc = toS(a);
    const r = v.viewer.renderer.domElement.getBoundingClientRect();
    v.ray.setFromCamera({ x: ((sc.x - r.left) / r.width) * 2 - 1, y: -((sc.y - r.top) / r.height) * 2 + 1 }, cam);
    const raw = v.ray.intersectObjects([h], true).slice(0, 5).map((x) => [x.object.type, x.object.userData.pickName, x.distance]);
    return { a: a.toArray(), sc, raw, wpp: v.worldPerPixel(cam, r.height), mw: o.matrixWorld.elements.slice(12, 15) } } catch (e) { return String(e.stack) } })()`)
  if (args.includes('--verbose')) await page.screenshot({ path: join(tmpdir(), `dressupcheck-${name}.png`) })
  bad(`${name}: not found in any standard view to click`, why + ' ' + JSON.stringify(probe))
  return false
}

try {
  await page.goto(`${BASE}/next/#dress`)
  await until('!!window.cadui && cadui.getState().slug === "dress" && !!cadui.getState().scene', 'the project to open')
  await until(`${JSON.stringify(CASES.map((c) => c[1]))}.every((p) => cadui.getState().features[p]?.features.length === 2 && cadui.getState().scene.bodies.some((b) => b.part === p))`, 'the Bodies')
  await st('cadui.setState({ workbench: "design" })')
  await sleep(300)
  // the 3D view in front of the Start page (its tab, "dress : 1"): the picks are clicks in it
  await page.click('.dv-tab:has-text("dress")').catch(() => page.click('text=dress : 1'))
  await sleep(500)

  // ── menu and toolbar ───────────────────────────────────────────────────────────────────────────────────────────────
  console.log('menu')
  const ours = await st('cadui.pd()')
  const sub = ours.partDesign.find((e) => e.text === 'Dress-Up Features')?.menu ?? []
  check(same(FC.menu.menu.map((e) => [clean(e.text), e.name]), sub.map((e) => [e.text, e.cmd])), 'Dress-Up Features: FreeCAD\'s entries and commands', JSON.stringify(sub.map((e) => e.text)))
  for (const e of sub) if (e.cmd !== 'PartDesign_Defeaturing') check(e.enabled, `${e.text}: enabled with a document open (CmdPartDesign${e.text}::isActive: hasActiveDocument)`)
  note('Defeaturing stays greyed: not built yet')
  const tb = ours.toolbars.find((t) => t.title === 'Part Design Dress-Up Features')
  check(same(FC.menu.toolbar.map((b) => b.name), tb?.buttons.map((b) => b.cmd)), 'the Dress-Up toolbar: FreeCAD\'s buttons', JSON.stringify(tb?.buttons.map((b) => b.cmd)))

  // ── each command, as fcdressup_dump.py ran it ──────────────────────────────────────────────────────────────────────
  for (const [key, part, cmd, sel, pick] of CASES) {
    const fc = FC[key]
    console.log(key)
    const bodyName = await st(`cadui.getState().scene.bodies.find((b) => b.part === ${JSON.stringify(part)}).name`)
    const subSel = Array.isArray(sel) ? sel.map((s) => `${bodyName}.${s}`) : []
    // this Body alone in the view, fitted, as FreeCAD's document holds it alone
    await st(`cadui.setState({ hidden: cadui.getState().scene.bodies.map((b) => b.name).filter((n) => n !== ${JSON.stringify(bodyName)}) })`)
    await sleep(300)
    await st('cadui.getCommand("Std_ViewFitAll")?.run([])')
    await sleep(600)
    await st(`cadui.setState({ activeBody: ${JSON.stringify(part)}, featSel: [], subSel: ${JSON.stringify(subSel)}, selected: ${sel === 'whole' ? JSON.stringify([bodyName]) : '[]'} })`)
    await page.click(`.tb-btn[data-cmd="${cmd}"]`)
    const kind = cmd.slice('PartDesign_'.length).toLowerCase()
    if (!await until(`cadui.getState().task?.kind === "${kind}"`, `${key}: the panel`)) continue
    await until('cadui.getView().helpers?.has?.("pd-dressup") === true', `${key}: the base drawn`, 60000)
    await sleep(600)
    holdPanel(await panel(), fc.task, `${key}`)
    check(await st(`cadui.getState().hidden.includes(${JSON.stringify(bodyName)})`), `${key}: the Body's Tip is hidden and its base drawn while the panel is open (showPreviousFeature)`)
    if (fc.task_select) {
      const now = await panel()
      if (!now.select.pressed) await page.click('.taskview .pd-refsel')
      await sleep(400)
      check((await panel()).select.text === 'Confirm Selection', `${key}: Select pressed reads "Confirm Selection"`)
      if (pick) {
        if (await clickElement(pick)) {
          await until(`(() => { const l = [...document.querySelectorAll('.taskview .pd-reflist [role=option]')].map((e) => e.textContent); return l.includes(${JSON.stringify(pick)}) })()`, `${key}: ${pick} in the list`, 10000)
          check(same(await listOf(), fc.picked[1]), `${key}: a click on ${pick} in the 3D view adds it, as FreeCAD's pick: ${JSON.stringify(fc.picked[1])}`, JSON.stringify(await listOf()))
          await clickElement(pick)
          check(same(await listOf(), fc.picked_twice[1]), `${key}: a second click takes it off: ${JSON.stringify(fc.picked_twice[1])}`, JSON.stringify(await listOf()))
          await clickElement(pick)
        }
      }
      await page.click('.taskview .pd-refsel')
      await sleep(300)
      check((await panel()).select.text === 'Select', `${key}: Confirm Selection goes back to "Select"`)
    }
    await sleep(500)
    await page.click('.taskview .pd-buttons .qbtn.default')
    const name = fc.in_edit
    if (!fc.after.valid) {
      // FreeCAD keeps the feature in error; here the panel says why and stays (a part file only takes a Body that builds)
      await until('!!document.querySelector(".msgbox")', `${key}: the error`, 20000)
      const text = await st('document.querySelector(".msgbox-text")?.textContent')
      if (fc.after.status) check(text === fc.after.status, `${key}: OK says FreeCAD's error, "${fc.after.status}"`, text)
      else note(`${key}: FreeCAD's error has no text (OCCT's StdFail_NotDone); ours says "${text}"`)
      note(`${key}: FreeCAD makes ${name} and marks it in error; here OK is refused with the same message (PARITY.md)`)
      await page.click('.msgbox-buttons button')
      await page.click('.taskview .pd-buttons .qbtn:not(.default)')
      await sleep(500)
      check(await st(`!cadui.getState().features[${JSON.stringify(part)}].features.some((f) => f.name === ${JSON.stringify(name)})`), `${key}: Cancel writes nothing`)
      continue
    }
    await until(`cadui.getState().features[${JSON.stringify(part)}]?.features.some((f) => f.name === ${JSON.stringify(name)})`, `${key}: ${name} written`)
    await until(`cadui.getState().undo[0]?.name === ${JSON.stringify(fc.undo_names_after[0])}`, `${key}: the "${fc.undo_names_after[0]}" step`, 30000)
    const f = await st(`cadui.getState().features[${JSON.stringify(part)}].features.find((f) => f.name === ${JSON.stringify(name)})`)
    check(same(f?.base, fc.after.base), `${key}: Base ${JSON.stringify(fc.after.base)}`, JSON.stringify(f?.base))
    check(await st(`cadui.getState().features[${JSON.stringify(part)}].tip === ${JSON.stringify(fc.after.tip)}`), `${key}: ${fc.after.tip} is the Tip`)
    check(await st(`cadui.getState().undo[0]?.name === ${JSON.stringify(fc.undo_names_after[0])}`), `${key}: one undo step, "${fc.undo_names_after[0]}"`)
    if (fc.after.valid && fc.after.volume) {
      const v = volume(part)
      check(v !== null && Math.abs(v - fc.after.volume) <= 1e-5 * fc.after.volume, `${key}: the solid's volume is FreeCAD's ${fc.after.volume}`, String(v))
    } else note(`${key}: FreeCAD's ${name} is not valid (${fc.after.status || 'touched'}); the part file keeps it the same way`)
    // the property view
    await st('cadui.showPanel("model")')
    await page.click(`.trow[data-ref="${part}/${name}"] .tname`)
    await sleep(500)
    const rows = await st('[...document.querySelectorAll(".pgroup, .prow .pk")].map((e) => e.classList.contains("pgroup") ? "#" + e.textContent : e.textContent)')
    const fcRows = fc.property_view[0]
    const want = []
    for (let i = 0; i < fcRows.length; i++) {
      const r = fcRows[i]
      // the top rows are the groups; FreeCAD's PropertyEditor keeps the groups of objects shown before, empty: left out
      if (r.depth === 0) { if (i + 1 < fcRows.length && fcRows[i + 1].depth === 1) want.push('#' + r.name) } else want.push(r.name)
    }
    check(same(rows, want), `${key}: the property view's groups and rows, as FreeCAD's`, `\n        FreeCAD ${want.join(' | ')}\n        ours    ${rows.join(' | ')}`)
  }

  // ── edit: a double-click on the Fillet ────────────────────────────────────────────────────────────────────────────
  console.log('edit')
  await st('cadui.showPanel("model")')
  await page.dblclick('.trow[data-ref="P_fillet/Fillet"] .tname')
  await until('cadui.getState().task?.kind === "fillet" && cadui.getState().task?.edit', 'the Fillet\'s panel')
  await sleep(600)
  const p = await panel()
  check(same(p.list, FC.fillet.after.base[1]), 'double-click on the Fillet: its references', JSON.stringify(p.list))
  check(p.select.text === 'Select', 'double-click on the Fillet: not selecting (it has references)')
  await page.click('.taskview .pd-form label.tfield:has(span:text-is("Radius")) input')
  await page.keyboard.press('Control+A'); await page.keyboard.type('2'); await page.keyboard.press('Tab')
  await sleep(300)
  await page.click('.taskview .pd-buttons .qbtn.default')
  await until('cadui.getState().features.P_fillet.features.find((f) => f.name === "Fillet")?.radius === 2', 'the Fillet at 2 mm')
  if (await until('cadui.getState().undo[0]?.name === "Edit Fillet"', 'the step', 20000)) ok('the panel\'s OK is one step, "Edit Fillet"')
  await page.click('.tb-btn[data-cmd="Std_Undo"]')
  await until('cadui.getState().features.P_fillet.features.find((f) => f.name === "Fillet")?.radius === 1', 'Undo of the edit')
  ok('Undo puts the radius back')
} catch (e) {
  bad('dressupcheck stopped', e.stack ?? String(e))
} finally {
  await browser.close()
  server.kill('SIGTERM')
  spawnSync(python, ['-P', '-m', 'cad_agent.warm', 'warm', 'stop'], { env, cwd: REPO, timeout: 60000 })
  if (!args.includes('--keep')) for (const d of [scratch, warmDir]) rmSync(d, { recursive: true, force: true })
}
console.log(`dressupcheck: ${pass} ok, ${fail} failing, ${known} known differences`)
process.exit(fail ? 1 : 0)

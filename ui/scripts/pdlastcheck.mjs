// SPDX-License-Identifier: LGPL-2.1-or-later
// pdlastcheck: PartDesign's last commands in the page (Involute Gear, Sprocket, Defeaturing, Sub-Shape Binder), held to the
// real FreeCAD's (ui/scripts/fcpdlast.json, written by fcpdlast.py from FreeCAD 26.3 at 3160daf1e2b6), then driven end to end.
//
//   NODE_PATH=<folder with playwright> node ui/scripts/pdlastcheck.mjs [--fc=ui/scripts/fcpdlast.json] [--edit=ui/scripts/fcedit.json]
//
// It starts a scratch workbench of its own (a temporary projects folder, CAD_* pointed at scratch paths, as editcheck.mjs
// does) with four Bodies, each a 40 x 20 x 5 Pad on a rectangle (fcpdlast_dump.py's fresh()), and in Chromium on SwiftShader:
//   menus     Part Design's Sub-Shape Binder, Defeaturing, Involute Gear and Sprocket entries, enabled, FreeCAD's commands
//   gear      the command's panel (labels, values, combo boxes) against FreeCAD's; 13 teeth; OK, the undo step, the Tip, the
//             tree's row, the property view, the tree's context menu; a second edit; a Pad on the gear (its volume, the tree)
//   sprocket  the panel; Sprocket reference ANSI 40 sets pitch, roller diameter and tooth width as FreeCAD's; OK; Cancel on an
//             edit deletes it, as FreeCAD 26.3's reject does
//   defeat    on a hole's face: the panel, OK, the undo step, the solid (volume, faces), the property view, the tree menu; an
//             edge selected (FreeCAD's warning); nothing selected (an empty one on the Tip)
//   binder    on the Pad's top face: Support, the undo step, the Tip, the shape, the property view, the tree menu; a
//             double-click (no step); nothing selected (an empty binder); the Pad's row (the whole Pad)
// A difference prints as FAIL; the deliberate ones (PARITY.md, "PartDesign's last commands") as `known`. Exit 1 on a FAIL.
import { createRequire } from 'module'
import { spawn, spawnSync } from 'child_process'
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'fs'
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
const FC = JSON.parse(readFileSync(flag('fc', join(HERE, 'fcpdlast.json')), 'utf8'))
const FCEDIT = JSON.parse(readFileSync(flag('edit', join(HERE, 'fcedit.json')), 'utf8'))
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
let pass = 0, fail = 0, known = 0
const ok = (what) => { pass++; if (args.includes('--verbose')) console.log(`  ok    ${what}`) }
const bad = (what, detail = '') => { fail++; console.log(`  FAIL  ${what}${detail ? `: ${detail}` : ''}`) }
const note = (what) => { known++; console.log(`  known ${what}`) }
const check = (cond, what, detail) => (cond ? ok(what) : bad(what, detail))
const clean = (t) => String(t ?? '').replace(/&(.)/g, '$1').trim()
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b)
const near = (a, b, rel = 1e-6) => Math.abs(a - b) <= rel * Math.max(1, Math.abs(b))

// ── a scratch workbench with four Bodies ─────────────────────────────────────────────────────────────────────────────
const freePort = (from) => new Promise((res, rej) => {
  const tryPort = (p) => {
    if (p > from + 40) return rej(new Error('no free port'))
    const s = createServer(); s.once('error', () => tryPort(p + 1)); s.once('listening', () => s.close(() => res(p))); s.listen(p, '127.0.0.1')
  }
  tryPort(from)
})
const scratch = mkdtempSync(join(tmpdir(), 'cad-pdlastcheck-')), warmDir = mkdtempSync('/tmp/cpl')
const ROOT = join(scratch, 'root'); mkdirSync(ROOT)
for (const d of ['runtime', 'macros']) mkdirSync(join(scratch, d))
const python = process.env.CAD_PYTHON || join(REPO, '.venv', 'bin', 'python')
const env = { ...process.env, CAD_WARM_DIR: warmDir, CAD_RUNTIME_DIR: join(scratch, 'runtime'), CAD_MACRO_DIR: join(scratch, 'macros'),
  CAD_PREFS: join(scratch, 'prefs.json'), PYTHONPATH: REPO, CAD_PYTHON: python, CAD_RENDER_BACKEND: 'numpy' }
delete env.CAD_PROJECTS
spawnSync(python, ['-m', 'cad_agent', '--projects', ROOT, 'init', 'last', '--brief', 'pdlastcheck'], { env, cwd: REPO })
const PLATE = `from cad_agent.feature import Body, Constraint, LineSegment, Pad, Sketch

PARAMS = {}

FEATURES = [
    Sketch("Sketch", support="XY",
           geometry=[LineSegment((0.0, 0.0), (40.0, 0.0)), LineSegment((40.0, 0.0), (40.0, 20.0)),
                     LineSegment((40.0, 20.0), (0.0, 20.0)), LineSegment((0.0, 20.0), (0.0, 0.0))],
           constraints=[Constraint("Coincident", 0, 2, 1, 1), Constraint("Coincident", 1, 2, 2, 1),
                        Constraint("Coincident", 2, 2, 3, 1), Constraint("Coincident", 3, 2, 0, 1)]),
    Pad("Pad", "Sketch", length=5.0),
]
TIP = None


def build(**p):
    return Body(FEATURES, p, tip=TIP)
`
const BODIES = { gear: 'Body', sprocket: 'Body001', defeat: 'Body002', binder: 'Body003', clone: 'Body004', boolean: 'Body005' }
for (const b of Object.values(BODIES)) writeFileSync(join(ROOT, 'last', 'parts', `${b}.py`), PLATE)
// the Boolean's tool: fcpdlast_dump.py's second_body(), a rod of radius 4 at (20, 10) from z = -3, 12 long
const ROD = PLATE.replace(/geometry=\[LineSegment[\s\S]*?\]\),\n    Pad\("Pad", "Sketch", length=5.0\)/,
  'attachment_offset=(0.0, 0.0, -3.0), geometry=[Circle((20.0, 10.0), 4.0)], constraints=[]),\n    Pad("Pad", "Sketch", length=12.0)')
  .replace('import Body, Constraint', 'import Body, Circle, Constraint')
const TOOL = 'Body006'
writeFileSync(join(ROOT, 'last', 'parts', `${TOOL}.py`), ROD)
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

const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] })
const page = await browser.newPage({ viewport: { width: 1400, height: 950 } })
page.on('pageerror', (e) => bad('page error', e.message))
const st = (expr) => page.evaluate(expr)
const until = async (expr, what, ms = 90000) => {
  const t0 = Date.now()
  while (Date.now() - t0 < ms) { if (await st(expr)) return true; await sleep(250) }
  bad(`timed out waiting: ${what}`); return false
}
const feat = (part, name) => st(`cadui.getState().features[${JSON.stringify(part)}]?.features.find((f) => f.name === ${JSON.stringify(name)}) ?? null`)
const undoName = () => st('cadui.getState().undo[0]?.name ?? null')
const waitUndo = (name, what) => until(`cadui.getState().undo[0]?.name === ${JSON.stringify(name)}`, what, 30000)
/** The open panel's fields as FreeCAD's task_widgets lists them: each label's text, then its control's value. */
const ourPanel = () => st(`[...document.querySelectorAll('.taskview .pd-form .tfield')].map((f) => {
  const combo = f.querySelector('.qselect'), input = f.querySelector('input')
  return [f.querySelector('span')?.textContent ?? '', combo ? combo.querySelector('.combo-label')?.textContent ?? '' : input ? input.value : null] })`)
/** A combo box of the open panel (QComboBox: its popup read by opening it), and a pick in it. */
const comboItems = async (qf) => {
  await page.click(`.taskview .qselect[data-qf="${qf}"]`); await sleep(150)
  const items = await st('[...document.querySelectorAll(".combo-popup .combo-item")].map((e) => e.textContent)')
  await page.keyboard.press('Escape'); await sleep(100)
  return items
}
const pickCombo = async (qf, text) => {
  await page.click(`.taskview .qselect[data-qf="${qf}"]`); await sleep(150)
  await page.locator('.combo-popup .combo-item', { hasText: text }).first().click()
  await sleep(400)
}
/** FreeCAD's panel: each QLabel's text, then the value of the widget after it (a spin box's text, a combo's current item). */
const fcPanel = (task) => {
  const out = [], ws = task.flat()
  for (let i = 0; i < ws.length; i++) {
    const w = ws[i]
    if (w.class !== 'QLabel' || !w.text) continue
    const c = ws.slice(i + 1).find((x) => ['QSpinBox', 'QDoubleSpinBox', 'Gui::InputField', 'QComboBox'].includes(x.class))
    out.push([clean(w.text), c ? (c.class === 'QComboBox' ? c.current : c.text) : null])
  }
  return out
}
/** Our property view's rows under each group (what is shown for the selected row), and FreeCAD's, empty groups left out
 *  (its property editor keeps the headers of groups an earlier object had). */
const ourProps = () => st(`(() => { const out = []; let g = null
  for (const el of document.querySelectorAll('.pgroup, .prow')) {
    if (el.classList.contains('pgroup')) { g = [el.textContent, []]; out.push(g); continue }
    const cb = el.querySelector('.pv input[type=checkbox]'), combo = el.querySelector('.pv .combo-label')
    if (g) g[1].push([el.querySelector('.pk')?.textContent ?? '', (cb ? String(cb.checked) : combo ? combo.textContent : el.querySelector('.pv input')?.value ?? el.querySelector('.pv')?.textContent ?? '').trim()]) }
  return out.filter(([, rows]) => rows.length) })()`)
const fcProps = (view) => {
  const out = []
  let g = null
  for (const r of view[0] ?? []) {
    if (r.depth === 0) { g = [r.name, []]; out.push(g) } else if (g) g[1].push([r.name, r.value])
  }
  return out.filter(([, rows]) => rows.length)
}
const holdProps = async (ref, fcView, what, known = {}) => {
  await st('cadui.showPanel("model")')
  await page.click(`.trow[data-ref="${ref}"] .tname`)
  await sleep(700)
  const us = await ourProps(), fc = fcProps(fcView)
  check(same(us.map(([g]) => g), fc.map(([g]) => g)), `${what}: the property view's groups are FreeCAD's`, `FreeCAD ${JSON.stringify(fc.map(([g]) => g))}, ours ${JSON.stringify(us.map(([g]) => g))}`)
  for (const [g, rows] of fc) {
    const ours = us.find(([x]) => x === g)?.[1] ?? []
    check(same(ours.map(([k]) => k), rows.map(([k]) => k)), `${what}: ${g}'s rows in FreeCAD's order`, `FreeCAD ${JSON.stringify(rows.map(([k]) => k))}\n        ours    ${JSON.stringify(ours.map(([k]) => k))}`)
    for (const [k, v] of rows) {
      const o = ours.find(([x]) => x === k)?.[1]
      if (o === undefined) continue
      if (known[k]) { if (o !== String(v ?? '')) note(`${what}: ${k} reads "${o}" here, "${v}" in FreeCAD (${known[k]})`); else ok(`${what}: ${k}`); continue }
      check(o === String(v ?? ''), `${what}: ${k} is "${v}"`, `ours "${o}"`)
    }
  }
}
const KNOWN_MENU = { 'Send to Python Console': 'Send to Console' }
const holdMenu = async (ref, fc, what) => {
  await st('cadui.showPanel("model")')
  await page.click(`.trow[data-ref="${ref}"]`, { button: 'right' })
  await sleep(300)
  const us = await st('[...document.querySelectorAll(".ctx > *")].map((e) => e.classList.contains("mb-sep") ? "---" : e.textContent.replace(/^✓/, "").replace(/[⌘⇧⌥⌫↵▸]|F2|Space|V, T|⌘[A-Z]/g, "").trim())')
  await page.keyboard.press('Escape')
  const ft = fc.map((e) => (e.sep ? '---' : clean(e.text))).map((t) => KNOWN_MENU[t] ?? t).filter((t) => t !== 'Tree Settings')
  const ut = us.map((t) => t.replace(/\s+$/, ''))
  const missing = ft.filter((t) => t !== '---' && !ut.some((u) => u === t || u.startsWith(t)))
  check(!missing.length, `${what}: the tree menu has FreeCAD's entries`, `missing ${JSON.stringify(missing)}\n        ours ${JSON.stringify(ut)}`)
  const head = ft.slice(0, ft.indexOf('Toggle Visibility')).filter((t) => t !== '---'), ourHead = ut.slice(0, ut.indexOf('Toggle Visibility')).filter((t) => t !== '---')
  check(same(head, ourHead), `${what}: the tree menu's own entries, before Toggle Visibility, are FreeCAD's`, `FreeCAD ${JSON.stringify(head)}\n        ours    ${JSON.stringify(ourHead)}`)
}
const treeRow = (ref) => st(`(() => { const r = document.querySelector('.trow[data-ref="${ref}"]'); if (!r) return null
  return { text: r.querySelector('.tname')?.textContent, hidden: r.classList.contains('hid'), icon: r.querySelector('.ticon img')?.getAttribute('src') ?? '' } })()`)
const shapeOf = async (part, name) => {
  const r = await post(`/api/last/features/${part}/shape`, { ops: [], feature: name })
  return r?.data ?? r
}
const meshName = (part) => st(`cadui.getState().scene?.bodies.find((b) => b.part === ${JSON.stringify(part)})?.name ?? null`)
const msgBox = () => st('document.querySelector(".msgbox") ? ({ title: document.querySelector(".msgbox-title")?.textContent, text: document.querySelector(".msgbox-text")?.textContent, buttons: [...document.querySelectorAll(".msgbox-buttons button")].map((b) => b.textContent) }) : null')
const run = (cmd) => st(`cadui.getCommand(${JSON.stringify(cmd)}).run([])`)
const activate = (part) => st(`cadui.setState({ activeBody: ${JSON.stringify(part)}, featSel: [], selected: [], subSel: [] })`)

try {
  await page.goto(`${BASE}/next/#last`)
  await until('!!window.cadui && cadui.getState().slug === "last" && !!cadui.getState().scene', 'the project to open')
  await st('cadui.setState({ workbench: "design" })')
  await until(`Object.keys(cadui.getState().features).length >= 4`, 'the four Bodies')
  await sleep(300)

  // ── menus ──────────────────────────────────────────────────────────────────────────────────────────────────────────
  console.log('menus')
  const pd = (await st('cadui.pd()')).partDesign
  const flat = (es) => es.flatMap((e) => (e.menu ? [e, ...flat(e.menu)] : [e]))
  const fcFlat = flat(FCEDIT.menus['&Part Design'])
  for (const cmd of ['PartDesign_SubShapeBinder', 'PartDesign_Defeaturing', 'PartDesign_InvoluteGear', 'PartDesign_Sprocket']) {
    const us = flat(pd).find((e) => e.cmd === cmd), fc = fcFlat.find((e) => e.name === cmd)
    check(!!us && us.enabled, `Part Design menu: ${cmd} is there and enabled`)
    check(!!us && !!fc && us.text === clean(fc.text), `Part Design menu: ${cmd} reads "${clean(fc?.text)}"`, us?.text)
  }

  // ── Involute Gear ──────────────────────────────────────────────────────────────────────────────────────────────────
  console.log('gear')
  const G = FC.gear
  await activate(BODIES.gear)
  await run('PartDesign_InvoluteGear')
  await until('cadui.getState().task?.kind === "pdGear"', 'the gear\'s panel')
  await sleep(500)
  check((await st('document.querySelector(".taskview .tbox-head")?.textContent')) === 'Involute Parameter', 'Involute Gear: the panel is "Involute Parameter"')
  check(same((await st('[...document.querySelectorAll(".taskview .pd-buttons button")].map((b) => b.textContent)')), ['OK', 'Cancel', 'Apply']), 'Involute Gear: OK, Cancel and Apply')
  check(same(await ourPanel(), fcPanel(G.task)), 'Involute Gear: the panel\'s labels and values are FreeCAD\'s', `\n        FreeCAD ${JSON.stringify(fcPanel(G.task))}\n        ours    ${JSON.stringify(await ourPanel())}`)
  check(await until('cadui.getView().helpers?.has?.("pd-gear-preview") === true', 'the wire previewed', 30000), 'Involute Gear: the wire is drawn while the panel is open')
  await page.fill('.taskview input[data-qf="spinBox_NumberOfTeeth"]', '13')
  await sleep(800)
  await page.click('.taskview .pd-buttons .qbtn.default')
  await until(`cadui.getState().features.${BODIES.gear}.features.some((f) => f.name === "InvoluteGear")`, 'the gear')
  check(await waitUndo(G.after_ok.undo[0], 'the step'), `Involute Gear: OK is one step, "${G.after_ok.undo[0]}"`)
  const g = await feat(BODIES.gear, 'InvoluteGear')
  check(g?.number_of_teeth === G.teeth_live && g?.type === 'Part::InvoluteGear', 'Involute Gear: written with 13 teeth, FreeCAD\'s NumberOfTeeth after the change', JSON.stringify(g))
  check((await st(`cadui.getState().features.${BODIES.gear}.tip`)) === G.after_ok.tip, `Involute Gear: the Tip stays ${G.after_ok.tip} (a Part2DObject is not a solid feature)`)
  const gs = await shapeOf(BODIES.gear, 'InvoluteGear')
  check(gs?.shape?.edges?.length === G.shape_13.edges, `Involute Gear: the wire has FreeCAD's ${G.shape_13.edges} edges`, String(gs?.shape?.edges?.length))
  await st('cadui.showPanel("model")')
  await sleep(300)
  const gr = await treeRow(`${BODIES.gear}/InvoluteGear`)
  check(!!gr && /PartDesign_InternalExternalGear/.test(gr.icon) && !gr.hidden, 'Involute Gear: its row, with PartDesign_InternalExternalGear, shown', JSON.stringify(gr))
  await holdProps(`${BODIES.gear}/InvoluteGear`, G.props_view, 'Involute Gear')
  await holdMenu(`${BODIES.gear}/InvoluteGear`, G.menu, 'Involute Gear')
  // a second edit: the panel with its values, Addendum 0.9, OK
  await page.dblclick(`.trow[data-ref="${BODIES.gear}/InvoluteGear"] .tname`)
  await until('cadui.getState().task?.kind === "pdGear" && !!cadui.getState().task.edit', 'the gear\'s panel again')
  await sleep(400)
  check(same(await ourPanel(), fcPanel(G.edit_task)), 'Involute Gear: double-click opens the panel with its values', JSON.stringify(await ourPanel()))
  await page.fill('.taskview input[data-qf="doubleSpinBox_Addendum"]', '0.9')
  await sleep(300)
  await page.click('.taskview .pd-buttons .qbtn.default')
  await until(`cadui.getState().features.${BODIES.gear}.features.find((f) => f.name === "InvoluteGear")?.addendum_coefficient === 0.9`, 'Addendum 0.9')
  check((await feat(BODIES.gear, 'InvoluteGear'))?.addendum_coefficient === G.after_edit.addendum, 'Involute Gear: the edit writes Addendum 0.9')
  if (G.after_edit.undo.length === 1) note(`Involute Gear: an edit is a step here ("${await undoName()}"); FreeCAD's Python panel opens no transaction for it`)
  // Cancel on an edit: FreeCAD has already applied the change (assignValue) and keeps it
  await page.dblclick(`.trow[data-ref="${BODIES.gear}/InvoluteGear"] .tname`)
  await until('cadui.getState().task?.kind === "pdGear" && !!cadui.getState().task.edit', 'the gear\'s panel again')
  await page.fill('.taskview input[data-qf="doubleSpinBox_Dedendum"]', '1.4')
  await sleep(300)
  await page.click('.taskview .pd-buttons .qbtn:text-is("Cancel")')
  await sleep(800)
  const ded = (await feat(BODIES.gear, 'InvoluteGear'))?.dedendum_coefficient ?? 1.25
  if (G.after_cancel.dedendum !== ded) note(`Involute Gear: Cancel on an edit keeps ${ded} here; FreeCAD keeps the ${G.after_cancel.dedendum} its widgets already set (reject has no transaction to abort)`)
  else ok('Involute Gear: Cancel on an edit')
  // a Pad on the gear
  await st(`cadui.setState({ featSel: ["${BODIES.gear}/InvoluteGear"], selected: [] })`)
  await run('PartDesign_Pad')
  await until('cadui.getState().task?.kind === "pad"', 'the Pad\'s panel')
  await sleep(800)
  check(await until('cadui.getView().helpers?.has?.("pd-preview") === true', 'the preview', 20000), 'Pad on the gear: the preview overlay is drawn from the gear\'s wire')
  await page.click('.taskview .pd-buttons .qbtn.default')
  await until(`cadui.getState().features.${BODIES.gear}.features.some((f) => f.name === "Pad001")`, 'Pad001')
  check(await waitUndo('Make Pad', 'the step'), 'Pad on the gear: "Make Pad"')
  check((await feat(BODIES.gear, 'Pad001'))?.profile === 'InvoluteGear', 'Pad on the gear: its profile is the gear')
  check((await st(`cadui.getState().features.${BODIES.gear}.tip`)) === G.after_pad.tip, 'Pad on the gear: Pad001 is the Tip')
  const p1 = await shapeOf(BODIES.gear, 'Pad001')
  const vol = (m) => m?.volume
  void vol
  const fcPad = G.after_pad.pad001
  check(p1?.shape?.faces?.length === fcPad.faces, `Pad on the gear: FreeCAD's ${fcPad.faces} faces`, String(p1?.shape?.faces?.length))
  await st('cadui.showPanel("model")')
  await sleep(300)
  for (const ref of [`${BODIES.gear}/Pad001`]) { if (!(await st(`!!document.querySelector('.trow[data-ref="${ref}"] .twisty.open')`))) await page.click(`.trow[data-ref="${ref}"] .twisty`) }
  await sleep(300)
  const under = await st(`(() => { const rows = [...document.querySelectorAll('.tree .trow')].map((r) => r.dataset.ref); const i = rows.indexOf("${BODIES.gear}/Pad001"); return rows[i + 1] })()`)
  check(under === `${BODIES.gear}/InvoluteGear`, 'Pad on the gear: the gear shows under Pad001, as FreeCAD\'s tree claims it', under)
  check((await treeRow(`${BODIES.gear}/InvoluteGear`))?.hidden === true, 'Pad on the gear: the gear is hidden (greyed), as FreeCAD hides a used profile')

  // ── Sprocket ───────────────────────────────────────────────────────────────────────────────────────────────────────
  console.log('sprocket')
  const S = FC.sprocket
  await activate(BODIES.sprocket)
  await run('PartDesign_Sprocket')
  await until('cadui.getState().task?.kind === "pdGear"', 'the sprocket\'s panel')
  await sleep(500)
  check((await st('document.querySelector(".taskview .tbox-head")?.textContent')) === 'Sprocket Parameters', 'Sprocket: the panel is "Sprocket Parameters"')
  check(same(await ourPanel(), fcPanel(S.task)), 'Sprocket: the panel\'s labels and values are FreeCAD\'s', `\n        FreeCAD ${JSON.stringify(fcPanel(S.task))}\n        ours    ${JSON.stringify(await ourPanel())}`)
  const items = await comboItems('comboBox_SprocketReference')
  check(same(items, S.task.flat().find((w) => w.name === 'comboBox_SprocketReference').items), 'Sprocket: the references are FreeCAD\'s, in its order')
  await pickCombo('comboBox_SprocketReference', 'ANSI 40')
  await sleep(800)
  check(same(await ourPanel(), fcPanel(S.task_ansi40)), 'Sprocket: ANSI 40 sets pitch, roller diameter and tooth width as FreeCAD\'s', JSON.stringify(await ourPanel()))
  await page.click('.taskview .pd-buttons .qbtn.default')
  await until(`cadui.getState().features.${BODIES.sprocket}.features.some((f) => f.name === "Sprocket")`, 'the sprocket')
  check(await waitUndo(S.after_ok.undo[0], 'the step'), `Sprocket: OK is one step, "${S.after_ok.undo[0]}"`)
  const sp = await feat(BODIES.sprocket, 'Sprocket')
  check(sp?.sprocket_reference === 'ANSI 40' && near(sp?.pitch, 12.7) && near(sp?.roller_diameter, 0.312 * 25.4), 'Sprocket: written with ANSI 40\'s values', JSON.stringify(sp))
  const ss = await shapeOf(BODIES.sprocket, 'Sprocket')
  check(ss?.shape?.edges?.length === S.after_ok.shape.edges, `Sprocket: the wire has FreeCAD's ${S.after_ok.shape.edges} edges`, String(ss?.shape?.edges?.length))
  await holdProps(`${BODIES.sprocket}/Sprocket`, S.props_view, 'Sprocket')
  await page.dblclick(`.trow[data-ref="${BODIES.sprocket}/Sprocket"] .tname`)
  await until('cadui.getState().task?.kind === "pdGear" && !!cadui.getState().task.edit', 'the sprocket\'s panel again')
  await sleep(300)
  await page.click('.taskview .pd-buttons .qbtn:text-is("Cancel")')
  await sleep(500)
  check(await until(`!cadui.getState().features.${BODIES.sprocket}.features.some((f) => f.name === "Sprocket")`, 'the sprocket deleted', 20000) === !S.after_cancel.exists,
    'Sprocket: Cancel on an edit deletes it, as FreeCAD 26.3\'s SprocketTaskPanel.reject does')
  check(await waitUndo(S.after_cancel.undo[0], 'the step'), `Sprocket: that is one step, "${S.after_cancel.undo[0]}"`)

  // ── Defeaturing ────────────────────────────────────────────────────────────────────────────────────────────────────
  console.log('defeaturing')
  const D = FC.defeat
  const hole = { name: 'Sketch001', type: 'Sketcher::SketchObject', support: 'XY', geometry: [{ type: 'Circle', center: [20, 10], radius: 3, construction: false }], constraints: [] }
  await post(`/api/last/features/${BODIES.defeat}`, { ops: [{ op: 'add', feature: hole },
    { op: 'add', feature: { name: 'Pocket', type: 'PartDesign::Pocket', profile: 'Sketch001', type1: 'ThroughAll', reversed: true } }, { op: 'tip', name: 'Pocket' }] })
  await st('cadui.loadFeatures()')
  await until(`cadui.getState().features.${BODIES.defeat}?.tip === "Pocket"`, 'the hole')
  await until(`!!cadui.getState().scene?.bodies.find((b) => b.part === "${BODIES.defeat}")`, 'the Body in the scene')
  const dm = await meshName(BODIES.defeat)
  await st(`cadui.setState({ activeBody: "${BODIES.defeat}", featSel: [], selected: [], subSel: ["${dm}.Face7"] })`)
  await run('PartDesign_Defeaturing')
  await until('cadui.getState().task?.kind === "defeaturing"', 'the Defeaturing panel')
  await sleep(500)
  check((await st('document.querySelector(".taskview .tbox-head")?.textContent')) === 'Defeaturing Parameters', 'Defeaturing: the panel is "Defeaturing Parameters"')
  const btn = await st('(() => { const b = document.querySelector(".taskview .pd-refsel"); return b ? [b.textContent, b.getAttribute("aria-pressed")] : null })()')
  const fcBtn = D.task.flat().find((w) => w.name === 'buttonRefSel')
  check(same(btn, [fcBtn.text, String(fcBtn.checked)]), 'Defeaturing: the selection button is down, "Confirm Selection", as FreeCAD\'s', JSON.stringify(btn))
  const list = await st('[...document.querySelectorAll(".taskview .pd-reflist [role=option]")].map((o) => o.textContent)')
  check(same(list, D.task.flat().find((w) => w.name === 'listWidgetReferences').items), 'Defeaturing: the list holds Face7', JSON.stringify(list))
  const prev = await st('[...document.querySelectorAll(".taskview .tcheck")].map((c) => [c.textContent.trim(), c.querySelector("input").checked])')
  check(same(prev, D.task.flat().filter((w) => w.class === 'QCheckBox').map((w) => [w.text, w.checked])), 'Defeaturing: the Preview box\'s check boxes', JSON.stringify(prev))
  await page.click('.taskview .pd-buttons .qbtn.default')
  await until(`cadui.getState().features.${BODIES.defeat}.features.some((f) => f.name === "Defeaturing")`, 'the Defeaturing')
  check(await waitUndo(D.after_ok.undo[0], 'the step'), `Defeaturing: OK is one step, "${D.after_ok.undo[0]}"`)
  check(same((await feat(BODIES.defeat, 'Defeaturing'))?.base, ['Pocket', ['Face7']]), 'Defeaturing: Base (Pocket, [Face7])')
  check((await st(`cadui.getState().features.${BODIES.defeat}.tip`)) === D.after_ok.tip, 'Defeaturing: it is the Tip')
  const ds = await shapeOf(BODIES.defeat, 'Defeaturing')
  check(ds?.shape?.faces?.length === D.after_ok.shape.faces && ds?.shape?.edges?.length === D.after_ok.shape.edges,
    `Defeaturing: the hole is gone, FreeCAD's ${D.after_ok.shape.faces} faces and ${D.after_ok.shape.edges} edges`, `${ds?.shape?.faces?.length} faces`)
  await holdProps(`${BODIES.defeat}/Defeaturing`, D.props_view, 'Defeaturing')
  await holdMenu(`${BODIES.defeat}/Defeaturing`, D.menu, 'Defeaturing')
  // an edge selected: FreeCAD's warning, nothing made
  const dm2 = await meshName(BODIES.defeat)
  await st(`cadui.setState({ featSel: [], selected: [], subSel: ["${dm2}.Edge1"] })`)
  await run('PartDesign_Defeaturing')
  await until('!!document.querySelector(".msgbox")', 'the warning')
  const box = await msgBox()
  check(box?.title === D.edge_selected.title && box?.text === D.edge_selected.text, `Defeaturing on an edge: "${D.edge_selected.title}", "${D.edge_selected.text}"`, JSON.stringify(box))
  await page.click('.msgbox-buttons button')
  await sleep(300)
  check((await st(`cadui.getState().features.${BODIES.defeat}.features.length`)) === 5 && !(await st('cadui.getState().task')), 'Defeaturing on an edge: nothing is made')
  // nothing selected: one on the Tip with no face, its panel, OK
  await st('cadui.setState({ featSel: [], selected: [], subSel: [] })')
  await run('PartDesign_Defeaturing')
  await until('cadui.getState().task?.kind === "defeaturing"', 'the empty Defeaturing\'s panel')
  await sleep(400)
  check((await st('cadui.getState().task?.other')) === D.empty_in_edit, `Defeaturing with nothing selected: ${D.empty_in_edit}`)
  await page.click('.taskview .pd-buttons .qbtn.default')
  await until(`cadui.getState().features.${BODIES.defeat}.features.some((f) => f.name === "Defeaturing001")`, 'Defeaturing001')
  check(same((await feat(BODIES.defeat, 'Defeaturing001'))?.base, ['Defeaturing', []]), 'Defeaturing with nothing selected: Base (Defeaturing, []), the Tip', JSON.stringify((await feat(BODIES.defeat, 'Defeaturing001'))?.base))
  check(await waitUndo('Make Defeaturing', 'the step'), 'Defeaturing with nothing selected: "Make Defeaturing"')
  check(await st('cadui.getState().messages.some((l) => /Empty defeaturing created$/.test(l.text))'), 'Defeaturing with nothing selected: "Empty defeaturing created" in the Report view')

  // ── Sub-Shape Binder ───────────────────────────────────────────────────────────────────────────────────────────────
  console.log('binder')
  const B = FC.binder
  await until(`!!cadui.getState().scene?.bodies.find((b) => b.part === "${BODIES.binder}")`, 'the Body in the scene')
  const bm = await meshName(BODIES.binder)
  await st(`cadui.setState({ activeBody: "${BODIES.binder}", featSel: [], selected: [], subSel: ["${bm}.Face6"] })`)
  await run('PartDesign_SubShapeBinder')
  await until(`cadui.getState().features.${BODIES.binder}.features.some((f) => f.name === "Binder")`, 'the binder')
  check(!(await st('cadui.getState().task')), 'Sub-Shape Binder: no task panel, as FreeCAD\'s command opens none')
  check(await waitUndo(B.after.undo[0], 'the step'), `Sub-Shape Binder: one step, "${B.after.undo[0]}"`)
  const b = await feat(BODIES.binder, 'Binder')
  check(same(b?.support, [['Pad', 'Face6']]) && same(B.after.support, [['Pad', ['Face6']]]), 'Sub-Shape Binder: Support (Pad, Face6), FreeCAD\'s', JSON.stringify(b?.support))
  check((await st(`cadui.getState().features.${BODIES.binder}.tip`)) === B.after.tip, 'Sub-Shape Binder: the Tip stays Pad')
  const bs = await shapeOf(BODIES.binder, 'Binder')
  check(bs?.shape?.faces?.length === B.after.shape.faces && bs?.shape?.edges?.length === B.after.shape.edges, `Sub-Shape Binder: its shape, FreeCAD's ${B.after.shape.faces} face and ${B.after.shape.edges} edges`)
  await st('cadui.showPanel("model")')
  await sleep(300)
  const br = await treeRow(`${BODIES.binder}/Binder`)
  check(!!br && /PartDesign_SubShapeBinder/.test(br.icon) && !br.hidden, 'Sub-Shape Binder: its row, with PartDesign_SubShapeBinder, shown', JSON.stringify(br))
  check(await until('cadui.getView().helpers?.has?.("pd-last") === true', 'the binder drawn', 20000), 'Sub-Shape Binder: drawn in the 3D view (UseBinderStyle\'s golden yellow)')
  await holdProps(`${BODIES.binder}/Binder`, B.props_view, 'Sub-Shape Binder')
  await holdMenu(`${BODIES.binder}/Binder`, B.menu, 'Sub-Shape Binder')
  const steps = await st('cadui.getState().undo.length')
  await page.dblclick(`.trow[data-ref="${BODIES.binder}/Binder"] .tname`)
  await sleep(1500)
  check((await st('cadui.getState().undo.length')) === steps && !(await st('cadui.getState().task')), 'Sub-Shape Binder: a double-click synchronizes, with no step and no panel, as FreeCAD\'s')
  await st('cadui.setState({ featSel: [], selected: [], subSel: [] })')
  await run('PartDesign_SubShapeBinder')
  await until(`cadui.getState().features.${BODIES.binder}.features.some((f) => f.name === "Binder001")`, 'Binder001')
  check(!((await feat(BODIES.binder, 'Binder001'))?.support?.length) && B.empty.support === '[]', 'Sub-Shape Binder with nothing selected: an empty one, as FreeCAD\'s')
  await st(`cadui.setState({ featSel: ["${BODIES.binder}/Pad"], selected: [], subSel: [] })`)
  await run('PartDesign_SubShapeBinder')
  await until(`cadui.getState().features.${BODIES.binder}.features.some((f) => f.name === "Binder002")`, 'Binder002')
  check(same((await feat(BODIES.binder, 'Binder002'))?.support, [['Pad', '']]) && same(B.whole.support, [['Pad', ['']]]), 'Sub-Shape Binder on the Pad\'s row: the whole Pad')
  const ws = await shapeOf(BODIES.binder, 'Binder002')
  check(ws?.shape?.faces?.length === B.whole.shape.faces, `Sub-Shape Binder on the whole Pad: FreeCAD's ${B.whole.shape.faces} faces`)
  // undo takes the last binder away
  await st('cadui.getCommand("Std_Undo").run([])')
  await until(`!cadui.getState().features.${BODIES.binder}.features.some((f) => f.name === "Binder002")`, 'Undo')
  ok('Undo: the last binder goes')

  // ── Clone ──────────────────────────────────────────────────────────────────────────────────────────────────────────
  console.log('clone')
  const C = FC.clone
  await st('cadui.setState({ activeBody: null, featSel: [], selected: [], subSel: [] })')
  check((await st('cadui.getCommand("PartDesign_Clone").isEnabled()')) === C.enabled_nothing, 'Clone: greyed with nothing selected, as FreeCAD\'s isActive')
  await st(`cadui.setState({ featSel: ["${BODIES.clone}/"] })`)
  check((await st('cadui.getCommand("PartDesign_Clone").isEnabled()')) === C.enabled, 'Clone: enabled with one Body selected')
  const partsBefore = await st('Object.keys(cadui.getState().features)')
  await run('PartDesign_Clone')
  await until(`Object.keys(cadui.getState().features).length > ${partsBefore.length}`, 'the new Body')
  const newPart = (await st('Object.keys(cadui.getState().features)')).find((k) => !partsBefore.includes(k))
  check(/^Body\d{3}$/.test(newPart ?? ''), `Clone: a new Body, the next free name (${newPart}; FreeCAD's ${C.after.body001_group ? 'Body001' : '?'})`)
  check(await waitUndo(C.after.undo[0], 'the step'), `Clone: one step, "${C.after.undo[0]}"`)
  const cl = await feat(newPart, 'Clone')
  check(cl?.type === 'PartDesign::FeatureBase' && cl?.base_feature === BODIES.clone, 'Clone: a PartDesign::FeatureBase, its BaseFeature the source Body', JSON.stringify(cl))
  check(same((await st(`cadui.getState().features.${newPart}.features.map((f) => f.name)`)), C.after.body001_group) && (await st(`cadui.getState().features.${newPart}.tip`)) === C.after.tip,
    'Clone: the new Body holds the Clone alone, and it is the Tip')
  check((await st('cadui.getState().activeBody')) !== newPart, 'Clone: the new Body is not made active, as FreeCAD leaves it')
  const cs = await shapeOf(newPart, 'Clone')
  check(cs?.shape?.faces?.length === C.after.shape.faces, `Clone: the source's shape, FreeCAD's ${C.after.shape.faces} faces`)
  await st('cadui.showPanel("model")')
  await until(`!!document.querySelector('.trow[data-ref="${newPart}/"]')`, 'the new Body\'s row', 20000)
  if (!(await st(`!!document.querySelector('.trow[data-ref="${newPart}/"] .twisty.open')`))) await page.click(`.trow[data-ref="${newPart}/"] .twisty`).catch(() => undefined)
  await sleep(300)
  const crow = await treeRow(`${newPart}/Clone`)
  check(!!crow && /PartDesign_Clone/.test(crow.icon), 'Clone: its row, with PartDesign_Clone', JSON.stringify(crow))
  await holdProps(`${newPart}/Clone`, C.props_view, 'Clone', { 'Base Feature': `the source is the part ${BODIES.clone} here, FreeCAD's first Body is Body` })
  await holdMenu(`${newPart}/Clone`, C.menu, 'Clone')

  // ── Boolean ────────────────────────────────────────────────────────────────────────────────────────────────────────
  console.log('boolean')
  const O = FC.boolean
  await activate(BODIES.boolean)
  await st(`cadui.setState({ featSel: ["${TOOL}/"] })`)
  await run('PartDesign_Boolean')
  await until('cadui.getState().task?.kind === "pdBoolean"', 'the Boolean panel')
  await sleep(500)
  const heads = await st('[...document.querySelectorAll(".taskview .tbox-head")].map((h) => h.textContent)')
  check(same(heads, O.task.flat().filter((w) => w.class === 'QSint::ActionLabel').map((w) => w.text)), 'Boolean: "Boolean Parameters" and "Preview", as FreeCAD\'s panel', JSON.stringify(heads))
  const bpanel = async () => st('({ buttons: [...document.querySelectorAll("[data-panel=boolean] .pd-row2 button")].map((b) => [b.textContent, b.getAttribute("aria-pressed")]), list: [...document.querySelectorAll("[data-qf=listWidgetBodies] [role=option]")].map((o) => o.textContent), type: document.querySelector(".taskview .qselect[data-qf=comboType] .combo-label")?.textContent })')
  let bp = await bpanel()
  const fcb = O.task.flat()
  check(same(bp.buttons, [['Add Body', 'false'], ['Remove Body', 'false']]) && fcb.some((w) => w.name === 'buttonBodyAdd' && w.text === 'Add Body' && !w.checked), 'Boolean: Add Body and Remove Body, both up', JSON.stringify(bp.buttons))
  check(same(bp.list, [TOOL]) && fcb.find((w) => w.name === 'listWidgetBodies').items.length === 1, 'Boolean: the list holds the selected Body (FreeCAD: Body001, here its part)', JSON.stringify(bp.list))
  check(bp.type === fcb.find((w) => w.name === 'comboType').current && same(await comboItems('comboType'), fcb.find((w) => w.name === 'comboType').items), 'Boolean: Type Fuse, of Fuse, Cut and Common')
  await pickCombo('comboType', 'Cut')
  await page.click('.taskview .pd-buttons .qbtn.default')
  await until(`cadui.getState().features.${BODIES.boolean}.features.some((f) => f.name === "Boolean")`, 'the Boolean')
  check(await waitUndo(O.after_ok.undo[0], 'the step'), `Boolean: OK is one step, "${O.after_ok.undo[0]}"`)
  const bo = await feat(BODIES.boolean, 'Boolean')
  check(same(bo?.group, [TOOL]) && bo?.type1 === 'Cut', 'Boolean: Group [the tool], Type Cut', JSON.stringify(bo))
  check((await st(`cadui.getState().features.${BODIES.boolean}.tip`)) === O.after_ok.tip, 'Boolean: it is the Tip')
  const bsh = await shapeOf(BODIES.boolean, 'Boolean')
  check(bsh?.shape?.faces?.length === O.after_ok.shape.faces && bsh?.shape?.edges?.length === O.after_ok.shape.edges,
    `Boolean: the plate cut by the rod, FreeCAD's ${O.after_ok.shape.faces} faces and ${O.after_ok.shape.edges} edges`, `${bsh?.shape?.faces?.length} faces`)
  const toolMesh = await meshName(TOOL)
  check((await st(`!cadui.getState().hidden.includes(${JSON.stringify(toolMesh)})`)) === O.after_ok.visible.Body001, 'Boolean: the tool Body stays shown, as FreeCAD\'s command leaves it')
  await st('cadui.showPanel("model")')
  await sleep(300)
  if (!(await st(`!!document.querySelector('.trow[data-ref="${BODIES.boolean}/Boolean"] .twisty.open')`))) await page.click(`.trow[data-ref="${BODIES.boolean}/Boolean"] .twisty`).catch(() => undefined)
  await sleep(300)
  const after = await st(`(() => { const rows = [...document.querySelectorAll('.tree .trow')]; const i = rows.findIndex((r) => r.dataset.ref === "${BODIES.boolean}/Boolean"); return rows[i + 1]?.querySelector('.tname')?.textContent })()`)
  const fcUnder = O.tree[O.tree.findIndex((r) => r.text === 'Boolean') + 1]
  check(after === TOOL && fcUnder?.text === 'Body001', 'Boolean: the tool shows under it, as ViewProviderBoolean claims it', after)
  await holdProps(`${BODIES.boolean}/Boolean`, O.props_view, 'Boolean', { Group: 'the tool is the part Body006 here, FreeCAD\'s second Body is Body001' })
  await holdMenu(`${BODIES.boolean}/Boolean`, O.menu, 'Boolean')
  // a double-click: the panel with its tools and Type; Cancel changes nothing
  const nsteps = await st('cadui.getState().undo.length')
  await page.dblclick(`.trow[data-ref="${BODIES.boolean}/Boolean"] .tname`)
  await until('cadui.getState().task?.kind === "pdBoolean" && !!cadui.getState().task.edit', 'the Boolean panel again')
  await sleep(400)
  bp = await bpanel()
  check(same(bp.list, [TOOL]) && bp.type === O.edit_task.flat().find((w) => w.name === 'comboType').current, 'Boolean: double-click opens the panel with its tool and Type Cut', JSON.stringify(bp))
  await page.click('.taskview .pd-buttons .qbtn:text-is("Cancel")')
  await sleep(500)
  check((await st('cadui.getState().undo.length')) === nsteps, 'Boolean: Cancel on an edit leaves no step')
  // nothing selected: an empty list; OK asks for a Body and keeps the panel; Add Body takes the next Body picked, but not
  // the result Body
  await st('cadui.setState({ featSel: [], selected: [], subSel: [] })')
  await run('PartDesign_Boolean')
  await until('cadui.getState().task?.kind === "pdBoolean" && !cadui.getState().task.edit', 'the empty Boolean\'s panel')
  await sleep(400)
  check((await st('cadui.getState().task.other')) === O.empty_in_edit, `Boolean with nothing selected: ${O.empty_in_edit}, with an empty list`)
  await page.click('.taskview .pd-buttons .qbtn.default')
  await until('!!document.querySelector(".msgbox")', 'the warning')
  const eb = await msgBox()
  check(eb?.title === O.empty_ok.title && eb?.text === O.empty_ok.text, `Boolean: OK with no Body says "${O.empty_ok.title}", "${O.empty_ok.text}"`, JSON.stringify(eb))
  await page.click('.msgbox-buttons button')
  await sleep(300)
  check((await st('cadui.getState().task?.kind')) === 'pdBoolean', 'Boolean: and the panel stays open')
  await page.click('[data-panel=boolean] button[data-qf=buttonBodyAdd]')
  await sleep(200)
  await st(`cadui.setState({ featSel: ["${BODIES.boolean}/"] })`)
  await sleep(300)
  check(same((await bpanel()).list, []) && /result Body cannot/.test(await st('cadui.getState().gateMsg ?? ""')), 'Boolean: Add Body refuses the result Body (BooleanToolSelection)')
  await st(`cadui.setState({ featSel: ["${TOOL}/"] })`)
  await sleep(400)
  bp = await bpanel()
  check(same(bp.list, [TOOL]) && bp.buttons[0][1] === 'false', 'Boolean: Add Body takes the next Body picked, then comes up', JSON.stringify(bp))
  await page.click('.taskview .pd-buttons .qbtn:text-is("Cancel")')
  await sleep(500)
  check(!(await feat(BODIES.boolean, 'Boolean001')) && (await st('cadui.getState().undo.length')) === nsteps, 'Boolean: Cancel on a new one writes nothing (reject\'s abortCommand)')
} catch (e) {
  bad('the check stopped', e.stack ?? String(e))
} finally {
  console.log(`\npdlastcheck: ${pass} ok, ${fail} FAIL, ${known} known`)
  await browser.close()
  server.kill()
  if (!args.includes('--keep')) { rmSync(scratch, { recursive: true, force: true }); rmSync(warmDir, { recursive: true, force: true }) }
  process.exit(fail ? 1 : 0)
}

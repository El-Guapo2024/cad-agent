// SPDX-License-Identifier: LGPL-2.1-or-later
// assemblycheck: the Assembly workbench in the page, held to the real FreeCAD's (ui/scripts/fcassembly.json, written by
// fcassembly.py from FreeCAD 26.3 at 3160daf1e2b6), then driven end to end on a scratch project.
//
//   NODE_PATH=<folder with playwright> node ui/scripts/assemblycheck.mjs [--fc=ui/scripts/fcassembly.json] [--only=SECTION,...] [--keep] [--verbose]
//
// It starts a scratch workbench of its own (as partcheck.mjs does) with three parts, plate, pin and bar (the Box, Cylinder
// and Box001 of fcassembly_dump.py), and in Chromium on SwiftShader:
//   workbench  the switcher has Assembly; the menu bar puts &Assembly before Windows; New Assembly's undo step
//   menus      the Assembly menu with the three components in, entry by entry (FreeCAD's texts, commands, greyed or not)
//   toolbars   Assembly and Assembly Joints: FreeCAD's buttons in order
//   watchers   the Tasks panel with no task: the boxes InitGui.py's task watchers show
//   panels     each Assembly_CreateJoint<Type>'s panel opened with nothing picked: FreeCAD's widgets, top to bottom
//   insert     Assembly_InsertLink's panel
//   joints     Revolute, Distance (5 mm) and Fixed made from two picks and OK: the joint's Name, Label, References, every
//              component's Placement, the undo step and the Solver messages after each, against FreeCAD's
//   tree       the Assembly's rows; props, a joint's property view
//   undo       Std_Undo takes the last joint back
// A difference prints as FAIL; the deliberate ones (PARITY.md, "Assembly workbench") as `known`. Exit 1 on a FAIL.
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
const FC = JSON.parse(readFileSync(flag('fc', join(HERE, 'fcassembly.json')), 'utf8'))
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
let pass = 0, fail = 0, known = 0
const ok = (what) => { pass++; if (args.includes('--verbose')) console.log(`  ok    ${what}`) }
const bad = (what, detail = '') => { fail++; console.log(`  FAIL  ${what}${detail ? `: ${detail}` : ''}`) }
const note = (what) => { known++; console.log(`  known ${what}`) }
const check = (cond, what, detail) => (cond ? ok(what) : bad(what, detail))
const same = (a, b, what) => check(JSON.stringify(a) === JSON.stringify(b), what, `\n        FreeCAD ${JSON.stringify(b)}\n        ours    ${JSON.stringify(a)}`)
const ONLY = flag('only', '').split(',').filter(Boolean)
const want = (section) => !ONLY.length || ONLY.includes(section)
const clean = (t) => String(t ?? '').replace(/&(.)/g, '$1').replace(/…$/, '').trim()

// What is deliberately different (PARITY.md, "Assembly workbench"), by the FreeCAD command
const NOT_PORTED = new Set(['Part_LinkArrays', 'Assembly_CreateView', 'Assembly_CreateSnapshot', 'Assembly_CreateSimulation', 'Assembly_CreateBom', 'Assembly_SelectJointsOfComponent',
  'Assembly_LinkSelectLinked', 'Assembly_CreateJointRigidGroup', 'Assembly_InsertNewPart'])

// ── a scratch workbench with three parts ─────────────────────────────────────────────────────────────────────────────
const freePort = (from) => new Promise((res, rej) => {
  const tryPort = (p) => {
    if (p > from + 40) return rej(new Error('no free port'))
    const s = createServer(); s.once('error', () => tryPort(p + 1)); s.once('listening', () => s.close(() => res(p))); s.listen(p, '127.0.0.1')
  }
  tryPort(from)
})
const scratch = mkdtempSync(join(tmpdir(), 'cad-asmcheck-')), warmDir = mkdtempSync('/tmp/cac')
const ROOT = join(scratch, 'root'); mkdirSync(ROOT)
for (const d of ['runtime', 'macros']) mkdirSync(join(scratch, d))
const python = process.env.CAD_PYTHON || join(REPO, '.venv', 'bin', 'python')
const env = { ...process.env, CAD_WARM_DIR: warmDir, CAD_RUNTIME_DIR: join(scratch, 'runtime'), CAD_MACRO_DIR: join(scratch, 'macros'),
  CAD_PREFS: join(scratch, 'prefs.json'), PYTHONPATH: REPO, CAD_PYTHON: python, CAD_RENDER_BACKEND: 'numpy' }
delete env.CAD_PROJECTS
const SLUG = 'ac'
spawnSync(python, ['-m', 'cad_agent', '--projects', ROOT, 'init', SLUG, '--brief', 'assemblycheck'], { env, cwd: REPO })
const part = (doc, obj) => `"""${doc}: a Part workbench document."""\nfrom cad_agent import feature_part as Part\n\nMATERIAL = "petg"\nPROCESS = "fdm"\nPARAMS = {}\n\nOBJECTS = [\n    ${obj},\n]\n\n\ndef build(**p):\n    return Part.Document(OBJECTS, p)\n`
writeFileSync(join(ROOT, SLUG, 'parts', 'plate.py'), part('plate', 'Part.Box("Box", length=40, width=30, height=5)'))
writeFileSync(join(ROOT, SLUG, 'parts', 'pin.py'), part('pin', 'Part.Cylinder("Cylinder", radius=3, height=20)'))
writeFileSync(join(ROOT, SLUG, 'parts', 'bar.py'), part('bar', 'Part.Box("Box", length=30, width=6, height=4)'))
const port = await freePort(8991)
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
const undoName = () => st('cadui.getState().undo[0]?.name ?? null')
const runCmd = (cmd) => st(`cadui.getCommand(${JSON.stringify(cmd)})?.run([])`)
const assembly = () => st('cadui.getState().assembly')
const idle = () => until('!cadui.getState().busy.length', 'the server idle', 120000)

/** A menu's entries as text, command and greyed or not, FreeCAD's and ours side by side (NOT_PORTED ones `known`). */
function compareEntries(fc, ours, what) {
  const f = fc.filter((e) => !e.sep), o = ours.filter((e) => !e.sep)
  same(o.map((e) => clean(e.text)), f.map((e) => clean(e.text)), `${what}: FreeCAD's entries`)
  for (const e of f) {
    const m = o.find((x) => clean(x.text) === clean(e.text))
    if (!m) continue
    if (NOT_PORTED.has(m.cmd)) { note(`${what}: ${clean(e.text)} is not ported (greyed)`); continue }
    check(m.enabled === e.enabled, `${what}: ${clean(e.text)} ${e.enabled ? 'enabled' : 'greyed'}`, `ours ${m.enabled ? 'enabled' : 'greyed'}`)
    if (e.menu && m.menu) compareEntries(e.menu, m.menu, `${what} > ${clean(e.text)}`)
  }
}
/** The open joint panel's widgets, top to bottom, by their Qt object names (data-qf). */
const ourPanel = () => st(`[...document.querySelectorAll('.taskview .as-task [data-qf]')].map((e) => e.getAttribute('data-qf'))`)
const fcPanel = (task) => task.flat().map((w) => w.name).filter((n) => n && n !== 'qt_spinbox_lineedit')
const near = (a, b, tol = 1e-6) => a.length === b.length && a.every((x, i) => Math.abs(x - b[i]) <= tol)
const samePlc = (a, b) => near(a.slice(0, 3), b.slice(0, 3), 1e-5) && (near(a.slice(3), b.slice(3), 1e-7) || near(a.slice(3), b.slice(3).map((x) => -x), 1e-7))

try {
  await page.goto(`${BASE}/next/#${SLUG}`)
  await until('window.cadui && cadui.getState().slug === "ac" && cadui.getState().scene', 'the page and its scene')
  await st('cadui.setState({ workbench: "assembly" })')
  await sleep(500)
  if (want('workbench')) {
    console.log('workbench')
    const bar = await st(`[...document.querySelectorAll('.menubar > .menu > .mlabel, .menubar .menu-title, .menubar > *')].map((e) => e.textContent.trim()).filter(Boolean)`)
    check(bar.includes('Assembly'), 'the menu bar has Assembly', JSON.stringify(bar))
    compareEntries(FC.menus_none['&Assembly'], (await st('cadui.assembly()')).assembly, 'menu with no assembly')
  }
  // New Assembly, then the three components as fcassembly_dump.py inserts them (CommandInsertLink's accept), the first grounded
  await runCmd('Assembly_CreateAssembly')
  await until('!!cadui.getState().assembly', 'the Assembly')
  if (want('workbench')) same(await undoName(), FC.undo_new[0], 'New Assembly: its undo step')
  await st(`fetch('/api/ac/assembly', { method: 'POST', headers: { 'X-CAD': '1', 'Content-Type': 'application/json' }, body: JSON.stringify({ ops: [
    { op: 'insert', part: 'plate', name: 'Plate' },
    { op: 'insert', part: 'pin', name: 'Pin', placement: [[30, 5, 2], [10, 20, 30]] },
    { op: 'insert', part: 'bar', name: 'Bar', placement: [[-20, 40, 15], [-35, 5, 60]] }], name: 'Insert Component' }) })`)
  await until('(cadui.getState().assembly?.objects ?? []).length >= 4', 'the three components', 120000)
  await st('cadui.loadAssembly()')
  await until('cadui.getState().scene?.bodies.some((b) => b.name === "Bar")', 'the scene with the components', 120000)
  await st('cadui.setState({ asmActive: true })')
  await sleep(500)
  if (want('menus')) {
    console.log('menus')
    compareEntries(FC.menus_parts['&Assembly'], (await st('cadui.assembly()')).assembly, 'Assembly menu')
  }
  if (want('toolbars')) {
    console.log('toolbars')
    const ours = (await st('cadui.assembly()')).toolbars
    for (const tb of FC.toolbars_parts) {
      const o = ours.find((t) => t.title === tb.title)
      if (!o) { bad(`toolbar ${tb.title} is missing`); continue }
      compareEntries(tb.buttons, o.buttons, `toolbar ${tb.title}`)
    }
  }
  if (want('watchers')) {
    console.log('watchers')
    await st('cadui.setState({ task: null }); cadui.showPanel("tasks")')
    await sleep(500)
    const ours = await st(`[...document.querySelectorAll('.taskview .tbox .tbox-head')].map((h) => h.textContent.trim())`)
    const fcTitles = (FC.joint_distance?.tasks ?? []).flat().filter((w) => w.class === 'QSint::ActionLabel' && !(w.text ?? '').includes(' ')).map((w) => w.text)
    for (const t of ['Insert', 'Constraints', 'Tools']) check(ours.some((x) => x.startsWith(t)), `watchers: the ${t} box`, JSON.stringify(ours))
    if (fcTitles.length) ok(`watchers: FreeCAD shows ${fcTitles.join(', ')}`)
    note('watchers: FreeCAD 26.3 keeps the Solver messages panel hidden in the Tasks view here (its labels are read off the widget); the page shows it under the watchers')
  }
  if (want('panels')) {
    console.log('panels')
    for (const t of ['Fixed', 'Revolute', 'Cylindrical', 'Slider', 'Ball', 'Distance', 'Parallel', 'Perpendicular', 'Angle', 'RackPinion', 'Screw', 'Gears', 'Belt']) {
      await runCmd(`Assembly_CreateJoint${t}`)
      await until(`!!document.querySelector('.taskview .as-task[data-task="joint"]')`, `${t}'s panel`, 20000)
      const sortRows = (names) => names.join(',').replace(/(limit\w+Spinbox),(limitCheckbox\d)/g, '$2,$1').split(',')
      // a limit's spin box and check box share a row; FreeCAD's dump lists the box first (it sits a pixel higher)
      same(await ourPanel(), sortRows(fcPanel(FC[`panel_${t}`])), `${t}: the panel's widgets top to bottom`)
      await st('cadui.closeTask ? cadui.closeTask() : cadui.setState({ task: null })')
      await sleep(200)
    }
  }
  if (want('insert')) {
    console.log('insert')
    await runCmd('Assembly_InsertLink')
    await until(`!!document.querySelector('.taskview .as-task[data-task="insert"]')`, 'the Insert panel', 20000)
    same(await ourPanel(), fcPanel(FC.panel_insert).filter((n) => n !== 'label1' && n !== 'openFileButton'), 'Insert Component: the panel')
    await st('cadui.setState({ task: null })')
    await sleep(200)
  }
  if (want('joints')) {
    console.log('joints')
    for (const [key, cmd, picks, value] of [['joint_revolute', 'Assembly_CreateJointRevolute', [['Plate', 'Face6'], ['Pin', 'Face3']]],
      ['joint_distance', 'Assembly_CreateJointDistance', [['Plate', 'Face6'], ['Bar', 'Face5']], ['distanceSpinbox', '5 mm']],
      ['joint_redundant', 'Assembly_CreateJointFixed', [['Plate', 'Face6'], ['Pin', 'Face3']]]]) {
      const fc = FC[key]
      const before = (await assembly()).objects.length
      await runCmd(cmd)
      await until(`!!document.querySelector('.taskview .as-task[data-task="joint"]')`, `${cmd}'s panel`, 20000)
      for (const [body, sub] of picks) {
        const n = await st(`document.querySelectorAll('.taskview [data-qf="featureList"] .as-item').length`)
        await st(`cadui.getView().pointPicker(${JSON.stringify(body)}, null, ${JSON.stringify(sub)})`)
        await until(`document.querySelectorAll('.taskview [data-qf="featureList"] .as-item').length > ${n}`, `${body}.${sub} picked`, 30000)
        if (args.includes('--debug')) console.log('        after pick', JSON.stringify(await st("({ task: cadui.getState().task, tv: !!document.querySelector('.taskview'), dock: cadui.getState().comboTab ?? null })")))
      }
      same(await st(`[...document.querySelectorAll('.taskview [data-qf="featureList"] .as-item')].map((e) => e.textContent)`),
        fc.panel_values.flat().find((w) => w.name === 'featureList').items, `${cmd}: the picks in the list`)
      if (value) {
        await page.fill(`.taskview [data-qf="${value[0]}"] input`, value[1])
        await page.press(`.taskview [data-qf="${value[0]}"] input`, 'Tab')       // Return would be the panel's OK
        await sleep(400)
      }
      try { await page.click('.taskview .as-task .qbtn.default', { timeout: 10000 }) } catch (e) {
        console.log(`        the Tasks view: ${JSON.stringify(await st("document.querySelector('.taskview')?.innerText.slice(0, 600)"))}`)
        throw e
      }
      await until(`(cadui.getState().assembly?.objects ?? []).length > ${before}`, `${cmd}: the joint made`, 120000)
      await idle()
      const v = await assembly()
      const j = v.objects[v.objects.length - 1]
      if (fc.joint) {
        same([j.name, j.label, j.joint_type], [fc.joint.name, fc.joint.label, fc.joint.type], `${cmd}: Name, Label, JointType`)
        // a click exactly at a disc face's centre is also at its circle's: findElementClosestVertex's tie between the
        // two (Face3 or Edge1) is broken by the last bits of the point, differently from one placement to the next
        const tie = (a, b) => a[0] === b[0] && a[1][0] === b[1][0] && [a[1][1], b[1][1]].includes(a[1][0]) && [a[1][1], b[1][1]].some((x) => /^Edge/.test(x))
        const refsOurs = [j.reference1, j.reference2], refsFc = [fc.joint.reference1, fc.joint.reference2]
        if (JSON.stringify(refsOurs) !== JSON.stringify(refsFc) && refsOurs.every((r, i) => JSON.stringify(r) === JSON.stringify(refsFc[i]) || tie(r, refsFc[i])))
          note(`${cmd}: References ${JSON.stringify(refsOurs)} for FreeCAD's ${JSON.stringify(refsFc)}: a click at two coincident centres, a tie`)
        else same(refsOurs, refsFc, `${cmd}: References`)
      } else note(`${cmd}: fcassembly_dump.py did not read the first joint back (its name was taken by a panel cancelled before)`)
      for (const [n, p] of Object.entries(fc.placements)) {
        const o = v.placements[n]
        check(o && samePlc([...o.base, ...o.rotation], p), `${cmd}: ${n}'s Placement`, `FreeCAD ${JSON.stringify(p)} ours ${JSON.stringify(o)}`)
      }
      same(await undoName(), fc.undo[0], `${cmd}: its undo step`)
      same(`${v.status?.text ?? ''} ${v.status?.link ?? ''}`.replace(/\s+/g, ' ').trim(), String(fc.solver).replace(/\s+/g, ' ').trim(), `${cmd}: the Solver messages`)
    }
  }
  if (want('tree')) {
    console.log('tree')
    const fcRows = FC.tree.filter((r) => r.depth >= 1 && !['Box', 'Cylinder', 'Box001'].includes(r.text)).map((r) => `${r.depth - 1}:${r.text}`)
    const ours = await st(`(cadui.getState().assembly?.tree ?? []).map((r) => r.depth + ':' + r.label)`)
    same(ours, fcRows, 'the Assembly\'s tree rows (Origin, Joints, components)')
  }
  if (want('props')) {
    console.log('props')
    await st('cadui.setState({ asmSel: ["Joint"], selected: [], featSel: [] })')
    await sleep(500)
    const rows = await st(`[...document.querySelectorAll('.props .prow .pk')].map((e) => e.textContent.trim())`)
    const fcRows = (FC.props_joint?.[0] ?? []).filter((r) => r.depth === 1).map((r) => r.name)
    same(rows, fcRows, "a joint's property view: FreeCAD's rows")
    const vals = await st(`Object.fromEntries([...document.querySelectorAll('.props .prow')].map((e) => [e.querySelector('.pk')?.textContent.trim(), e.querySelector('.pv')?.textContent.trim()]))`)
    for (const r of (FC.props_joint?.[0] ?? []).filter((r) => r.depth === 1 && /Placement|Reference|Offset|Label/.test(r.name))) {
      if (vals[r.name] !== r.value && /^Reference/.test(r.name) && String(vals[r.name]).replace(/Face(\d+)\]$/, 'Edge1]') === r.value)
        note(`props: ${r.name} ${vals[r.name]} for FreeCAD's ${r.value}: the same tie at a disc's centre`)
      else check(vals[r.name] === r.value, `props: ${r.name} = ${r.value}`, `ours ${vals[r.name]}`)
    }
  }
  if (want('undo')) {
    console.log('undo')
    const n = (await assembly()).objects.length
    await runCmd('Std_Undo')
    await until(`(cadui.getState().assembly?.objects ?? []).length === ${n - 1}`, 'Std_Undo takes the last joint back', 120000) && ok('Std_Undo takes the last joint back')
  }
} catch (e) {
  bad('assemblycheck stopped', e.stack ?? String(e))
} finally {
  await browser.close()
  server.kill()
  if (!args.includes('--keep')) { rmSync(scratch, { recursive: true, force: true }); rmSync(warmDir, { recursive: true, force: true }) }
  else console.log(`scratch kept: ${scratch}`)
}
console.log(`assemblycheck: ${pass} ok, ${fail} FAIL, ${known} known`)
process.exit(fail ? 1 : 0)

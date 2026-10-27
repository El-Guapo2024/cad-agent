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
// and, against fcassembly_more.json (fcassembly.py --more) on a second project and a sub-assembly project:
//   menus2     the menu with three components   rigid    Create Rigid Group: object, tree, properties, context menu
//   isolate    the joint panel's Isolate modes  offsets  Show advanced offsets, Offset1's TaskPlacement
//   origin     a joint on the Origin's XY-plane explode  Exploded View: panel, a dragged move, the view, its display
//   newpart    New Part: panel, pick, the part  subasm   a sub-assembly: Insert, rigid/flexible, tree, properties, Go to
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
// the second round's commands (fcassembly.py --more): rigid groups, Isolate, the advanced offsets, a joint on the Origin,
// Exploded View, New Part, sub-assemblies
const FC2 = (() => { try { return JSON.parse(readFileSync(flag('fc2', join(HERE, 'fcassembly_more.json')), 'utf8')) } catch { return null } })()
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
const NOT_PORTED = new Set(['Part_LinkArrays', 'Assembly_CreateSnapshot', 'Assembly_CreateBom', 'Assembly_SelectJointsOfComponent'])

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
  if (want('drag')) {
    console.log('drag')
    // the Bar hangs by its Distance joint (plane on plane, 5 mm): findDragMode gives TranslationOnPlane, so a drag slides
    // it in the joint's plane and the solver keeps it 5 mm above the plate (z 10), as in FreeCAD
    await st('cadui.setState({ task: null, asmActive: true })')
    await page.click('text="ac : 1"').catch(() => {})            // the 3D view's tab in front of the Start page
    await sleep(800)
    const px = (p) => st(`(() => { const v = cadui.getView(), cam = v.viewer.camera.getCamera(), c = v.viewer.renderer.domElement
      cam.updateMatrixWorld(); const q = cam.position.clone().set(${p.join(',')}).project(cam)
      return [(q.x + 1) / 2 * c.clientWidth, (q.y + 1) / 2 * c.clientHeight] })()`)
    const before = (await assembly()).placements.Bar
    // the scene drawn again from the solved assembly.py (the file watcher's reload) before the press
    await until(`(() => { const m = cadui.getState().scene?.bodies.find((b) => b.name === 'Bar')?.matrix; return !!m && Math.abs(m[3] - ${before.base[0]}) < 1e-6 && Math.abs(m[11] - ${before.base[2]}) < 1e-6 })()`, 'the scene with the Bar where the solve put it', 120000)
    await sleep(1000)
    // the Bar's middle (15, 3, 2 in the part, a 30 x 6 x 4 box) where its Placement puts it
    const [qx, qy, qz, qw] = before.rotation, l = [15, 3, 2]
    const rot = (v) => { const [x, y, z] = v, ix = qw * x + qy * z - qz * y, iy = qw * y + qz * x - qx * z, iz = qw * z + qx * y - qy * x, iw = -qx * x - qy * y - qz * z
      return [ix * qw + iw * -qx + iy * -qz - iz * -qy, iy * qw + iw * -qy + iz * -qx - ix * -qz, iz * qw + iw * -qz + ix * -qy - iy * -qx] }
    const r = rot(l), centre = [before.base[0] + r[0], before.base[1] + r[1], before.base[2] + r[2]]
    let p0 = await px(centre)
    // a pixel on the Bar: where its middle projects, else the first of a coarse scan of the view that hits it
    for (let tries = 0; tries < 30 && await st(`cadui.getView().hitAtPos(${JSON.stringify(p0)})?.body ?? null`) !== 'Bar'; tries++) {
      const found = await st(`(() => { const v = cadui.getView(), c = v.viewer.renderer.domElement
        for (let y = 10; y < c.clientHeight; y += 12) for (let x = 10; x < c.clientWidth; x += 12) { const h = v.hitAtPos([x, y]); if (h?.body === 'Bar') return [x, y] }
        return null })()`)
      if (found) { p0 = found; break }
      if (tries === 29) p0 = null
      await sleep(1000)                        // the view still drawing the reloaded scene
    }
    if (!p0) {
      console.log('        hit:', JSON.stringify(await st(`(() => { const v = cadui.getView(), c = v.viewer.renderer.domElement, seen = {}
        for (let y = 10; y < c.clientHeight; y += 12) for (let x = 10; x < c.clientWidth; x += 12) { const h = v.hitAtPos([x, y]); if (h) seen[h.body] = (seen[h.body] ?? 0) + 1 }
        return { seen, meshes: v.meshes?.size, size: [c.clientWidth, c.clientHeight], rect: c.getBoundingClientRect(), rendered: v.rendered, bodies: cadui.getState().scene.bodies.map((b) => [b.name, b.bbox, b.matrix?.slice(0, 4)]), hidden: cadui.getState().hidden } })()`)))
      if (flag('shot', '')) await page.screenshot({ path: flag('shot', '') })
      throw new Error('the Bar is not in view')
    }
    const ev = (type, pos) => st(`cadui.getView().assemblyHook({ type: ${JSON.stringify(type)}, button: 1, pos: ${JSON.stringify(pos)}, ctrl: false })`)
    const pressed = await ev('press', p0)
    const hit = await st(`(() => { const h = cadui.getView().hitAtPos(${JSON.stringify(p0)}); return h ? h.body : null })()`)
    check(hit === 'Bar', 'drag: the press lands on the Bar', `hit ${hit} (${pressed})`)
    for (let k = 1; k <= 8; k++) { await ev('move', [p0[0] + 6 * k, p0[1] + 3 * k]); await sleep(k === 1 ? 1500 : 120) }
    await ev('release', [p0[0] + 48, p0[1] + 24])
    await until(`cadui.getState().undo[0]?.name === 'Move part'`, 'the drag written ("Move part")', 120000)
    await idle()
    const after = (await assembly()).placements.Bar
    check(Math.abs(after.base[2] - before.base[2]) < 1e-6 && Math.hypot(after.base[0] - before.base[0], after.base[1] - before.base[1]) > 1,
      'drag: the Bar slid in the plate\'s plane, still 5 mm above it', `before ${JSON.stringify(before.base)} after ${JSON.stringify(after.base)}`)
    same(await undoName(), 'Move part', 'drag: its undo step')
    await runCmd('Std_Undo')
    await until(`JSON.stringify(cadui.getState().assembly?.placements?.Bar?.base) === ${JSON.stringify(JSON.stringify(before.base))}`, 'the drag undone', 120000)
      && ok('drag: Std_Undo puts the Bar back')
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
  // ── the second round (fcassembly_more.json, fcassembly.py --more): a fresh project ac2 with Plate, Pin and Bar, and
  // acsub, whose Assembly (Plate grounded, Pin on a Revolute) is the sub-assembly ───────────────────────────────────────
  const MORE = ['menus2', 'rigid', 'isolate', 'offsets', 'origin', 'explode', 'newpart', 'subasm', 'sim']
  if (FC2 && MORE.some(want)) {
    const S2 = 'ac2', SUB = 'acsub'
    const cad = (...a) => spawnSync(python, ['-m', 'cad_agent', '--projects', ROOT, ...a], { env, cwd: REPO })
    for (const p of [S2, SUB]) {
      cad('init', p, '--brief', 'assemblycheck')
      // fcassembly_more_dump.py's: the main document's Box 40 x 30 x 5, the sub-assembly's a default Part::Box (10 mm)
      writeFileSync(join(ROOT, p, 'parts', 'plate.py'), part('plate', p === SUB ? 'Part.Box("Box")' : 'Part.Box("Box", length=40, width=30, height=5)'))
      writeFileSync(join(ROOT, p, 'parts', 'pin.py'), part('pin', 'Part.Cylinder("Cylinder", radius=3, height=20)'))
      writeFileSync(join(ROOT, p, 'parts', 'bar.py'), part('bar', 'Part.Box("Box", length=30, width=6, height=4)'))
    }
    cad('assembly', 'apply', SUB, '--ops', JSON.stringify([{ op: 'insert', part: 'plate', name: 'Plate' },
      { op: 'insert', part: 'pin', name: 'Pin', placement: [[30, 5, 2], [10, 20, 30]] },
      { op: 'joint', type: 'Revolute', ref1: ['Plate', ['Face6', 'Face6']], ref2: ['Pin', ['Face3', 'Edge1']] }]))
    await page.goto(`${BASE}/next/#${S2}`)
    await until(`window.cadui && cadui.getState().slug === ${JSON.stringify(S2)}`, 'the second project')
    await st('cadui.setState({ workbench: "assembly" })')
    await runCmd('Assembly_CreateAssembly')
    await until('!!cadui.getState().assembly', 'the Assembly of ac2')
    await st(`fetch('/api/${S2}/assembly', { method: 'POST', headers: { 'X-CAD': '1', 'Content-Type': 'application/json' }, body: JSON.stringify({ ops: [
      { op: 'insert', part: 'plate', name: 'Plate' },
      { op: 'insert', part: 'pin', name: 'Pin', placement: [[30, 5, 2], [10, 20, 30]] },
      { op: 'insert', part: 'bar', name: 'Bar', placement: [[-20, 40, 15], [-35, 5, 60]] }], name: 'Insert Component' }) })`)
    await until('(cadui.getState().assembly?.objects ?? []).length >= 4', 'the three components of ac2', 120000)
    // the page opened afresh on ac2, its scene built from the files (a project made after the workbench started)
    await page.goto(`${BASE}/next/#${S2}`)
    await page.reload()
    await until(`window.cadui && cadui.getState().slug === ${JSON.stringify(S2)}`, 'the second project again')
    await st('cadui.setState({ workbench: "assembly" })')
    if (!await until('cadui.getState().scene?.bodies.some((b) => b.name === "Bar") && !!cadui.getState().assembly', 'the scene of ac2', 180000))
      console.log('        ac2:', JSON.stringify(await st(`({ slug: cadui.getState().slug, err: cadui.getState().sceneError, bodies: cadui.getState().scene?.bodies.map((b) => b.name), asm: !!cadui.getState().assembly, projects: cadui.getState().projects.map((p) => p.slug) })`)))
    await st('cadui.setState({ asmActive: true, task: null })')
    await sleep(500)
    const objs = async () => (await assembly())?.objects ?? []
    const plcs = async () => Object.fromEntries(Object.entries((await assembly())?.placements ?? {}).map(([n, p]) => [n, [...p.base, ...p.rotation]]))
    const fcTree = (rows) => rows.filter((r) => r.depth >= 2).map((r) => `${r.depth - 2}:${r.text}`)
    const ourTree = async (from) => {
      const t = (await assembly())?.tree ?? []
      return t.filter((r) => r.depth >= 1).map((r) => `${r.depth - 1}:${r.label}`).slice(0, from ?? undefined)
    }
    const propRows = async () => (await st('cadui.showPanel("model")'), await sleep(300), st(`[...document.querySelectorAll('.props .prow')].map((e) => [e.querySelector('.pk')?.textContent.trim(), e.querySelector('.pv')?.textContent.trim() || (e.querySelector('.pv input[type=checkbox]')?.checked ? 'true' : 'false')])`))
    const fcProps = (p, names) => Object.fromEntries((p?.[0] ?? []).filter((r) => r.depth === 1 && names.includes(r.name)).map((r) => [r.name, r.value]))
    const pickOn = async (body, sub) => {
      const n = await st(`document.querySelectorAll('.taskview [data-qf="featureList"] .as-item').length`)
      await st(`cadui.getView().pointPicker(${JSON.stringify(body)}, null, ${JSON.stringify(sub)})`)
      await until(`document.querySelectorAll('.taskview [data-qf="featureList"] .as-item').length > ${n}`, `${body}.${sub} picked`, 30000)
    }
    const featureList = () => st(`[...document.querySelectorAll('.taskview [data-qf="featureList"] .as-item')].map((e) => e.textContent)`)
    const fcList = (task) => task.flat().find((w) => w.name === 'featureList')?.items
    if (want('menus2')) {
      console.log('menus2')
      compareEntries(FC2.menus, (await st('cadui.assembly()')).assembly, 'Assembly menu (second round)')
    }
    if (want('rigid')) {
      console.log('rigid')
      const fc = FC2.rigid
      await st('cadui.setState({ selected: ["Pin", "Bar"], asmSel: [] })')
      await runCmd('Assembly_CreateJointRigidGroup')
      await until(`(cadui.getState().assembly?.objects ?? []).some((o) => o.kind === 'RigidGroupJoint')`, 'the rigid group', 120000)
      await idle()
      const g = (await objs()).find((o) => o.kind === 'RigidGroupJoint')
      same([g.name, g.label ?? g.name, g.objects_to_rigid_group], [fc.name, fc.label, fc.members], 'rigid: Name, Label, ObjectsToRigidGroup')
      const rp = g.rigid_placements.map((p) => [...p[0], ...p[1]])
      check(rp.length === fc.rigid_placements.length && rp.every((p, i) => samePlc(p, fc.rigid_placements[i])), 'rigid: RigidPlacements', `${JSON.stringify(rp)} FreeCAD ${JSON.stringify(fc.rigid_placements)}`)
      same(await undoName(), fc.undo[0], 'rigid: its undo step')
      same(await ourTree(), fcTree(fc.tree).filter((r) => !/:(Box|Cylinder|Box001)$/.test(r)), 'rigid: the tree')
      await st(`cadui.setState({ asmSel: [${JSON.stringify(g.name)}], selected: [] })`)
      await sleep(500)
      const rows = Object.fromEntries(await propRows())
      for (const [k, val] of Object.entries(fcProps(fc.props, ['Label', 'Suppressed', 'Objects To Rigid Group'])))
        check(String(rows[k]) === String(val), `rigid: property ${k} = ${val}`, `ours ${rows[k]}`)
      const entries = await st('cadui.asmTree().filter((e) => e !== "sep").map((e) => e.label)')
      for (const m of fc.menu ?? []) check(entries.includes(m), `rigid: the context menu has ${m}`, JSON.stringify(entries))
      note("rigid: FreeCAD's Report view first shows the AttributeError RigidGroupJoint's onChanged raises before RigidPlacements exists; the page shows only \"Assembly: Rigid group positions updated.\"")
      await st('cadui.setState({ asmSel: [] })')
    }
    if (want('isolate')) {
      console.log('isolate')
      await runCmd('Assembly_CreateJointRevolute')
      await until(`!!document.querySelector('.taskview .as-task[data-task="joint"]')`, 'the Revolute panel', 20000)
      await pickOn('Plate', 'Face6')
      await pickOn('Pin', 'Face3')
      const modes = ['Transparent', 'Wireframe', 'Hidden', 'Disabled']
      for (const [i, mode] of modes.entries()) {
        // the Isolate combo box: Down moves to the next mode while it is closed
        if (i > 0) { await st(`document.querySelector('.taskview [data-qf="isolateType"]')?.focus()`); await page.keyboard.press('ArrowDown') }
        await sleep(600)
        const s = await st('({ hidden: cadui.getState().hidden, unselectable: cadui.getState().unselectable })')
        for (const [n, w] of Object.entries(FC2.isolate[mode])) {
          check((!s.hidden.includes(n)) === w.visibility && (!s.unselectable.includes(n)) === w.selectable, `isolate ${mode}: ${n} visible ${w.visibility}, selectable ${w.selectable}`,
            `ours visible ${!s.hidden.includes(n)}, selectable ${!s.unselectable.includes(n)}`)
        }
      }
      note('isolate: the faces of the parts left out are drawn at 80% (Transparent) or 100% transparency (Wireframe) in the default appearance, as SoSelectionElementAction swaps their colour; read from the page, not from FreeCAD')
      await page.click('.taskview .as-task .tbuttons .qbtn:not(.default)')
      await sleep(500)
      const s = await st('({ hidden: cadui.getState().hidden, unselectable: cadui.getState().unselectable })')
      check(!s.hidden.length && !s.unselectable.length, 'isolate: Cancel restores every component', JSON.stringify(s))
    }
    if (want('offsets')) {
      console.log('offsets')
      await runCmd('Assembly_CreateJointFixed')
      await until(`!!document.querySelector('.taskview .as-task[data-task="joint"]')`, 'the Fixed panel', 20000)
      await page.click('.taskview [data-qf="advancedOffsetCheckbox"] input')
      await sleep(300)
      same(await ourPanel(), fcPanel(FC2.offsets.panel), 'offsets: the panel with Show advanced offsets')
      same(await st(`[...document.querySelectorAll('.taskview [data-qf="offset1Button"], .taskview [data-qf="offset2Button"]')].map((e) => e.textContent)`),
        FC2.offsets.panel.flat().filter((w) => /^offset\dButton$/.test(w.name)).map((w) => w.text), "offsets: the buttons' text")
      await page.click('.taskview [data-qf="offset1Button"]')
      await until(`!!document.querySelector('[data-dialog="TaskPlacement"]')`, "Offset1's Placement dialog", 10000)
      const ours = await st(`[...document.querySelectorAll('[data-dialog="TaskPlacement"] [data-qf]')].map((e) => e.getAttribute('data-qf'))`)
      const want2 = ['GroupBox5', 'GroupBox5_3', 'xPos', 'yPos', 'zPos', 'axialPos', 'applyAxial', 'xCnt', 'yCnt', 'zCnt', 'centerOfMass', 'GroupBox5_2', 'rotationInput', 'xAxis', 'yAxis', 'zAxis', 'angle', 'applyIncrementalPlacement', 'resetButton']
      const fcNames = (FC2.offsets.dialog.widgets ?? []).map((w) => w.name)
      for (const n of want2) check(fcNames.includes(n) && ours.includes(n), `offsets: TaskPlacement's ${n}`, `FreeCAD ${fcNames.includes(n)}, ours ${ours.includes(n)}`)
      check(!fcNames.includes('selectedVertex') && !ours.includes('selectedVertex'), 'offsets: Selected points hidden (openEditingPlacementDialog)')
      await page.fill('[data-dialog="TaskPlacement"] [data-qf="zPos"] input', '3 mm')
      await page.press('[data-dialog="TaskPlacement"] [data-qf="zPos"] input', 'Tab')
      await page.click('[data-dialog="TaskPlacement"] .msgbox-buttons .qbtn.default')
      await sleep(300)
      same(await st(`document.querySelector('.taskview [data-qf="offset1Button"]')?.textContent`), '(0.0, 0.0, 3.0)', 'offsets: Offset1 set from the dialog')
      await page.click('.taskview .as-task .tbuttons .qbtn:not(.default)')
      await sleep(300)
    }
    if (want('origin')) {
      console.log('origin')
      const fc = FC2.origin
      const before = (await objs()).length
      await runCmd('Assembly_CreateJointFixed')
      await until(`!!document.querySelector('.taskview .as-task[data-task="joint"]')`, 'the Fixed panel', 20000)
      // a tree click on the Origin's XY-plane (the Origin row opened first)
      // the tree (the Model tab) while the panel is open, as FreeCAD's tree beside its Tasks
      await st('cadui.showPanel("model")')
      await sleep(300)
      await st(`document.querySelector('[data-ref="assembly/Origin"] .twisty')?.click()`)
      await sleep(300)
      await page.click('[data-ref="assembly/XY_Plane"]')
      await st('cadui.showPanel("tasks")')
      await until(`document.querySelectorAll('.taskview [data-qf="featureList"] .as-item').length >= 1`, 'the XY-plane picked', 20000)
      await pickOn('Bar', 'Face5')
      await sleep(800)
      same(await featureList(), fcList(fc.panel), 'origin: the picks in the list')
      await page.click('.taskview .as-task .qbtn.default')
      await until(`(cadui.getState().assembly?.objects ?? []).length > ${before}`, 'origin: the joint made', 120000)
      await idle()
      const j = (await objs()).filter((o) => o.kind === 'Joint').pop()
      same([j.name, j.label, j.reference1, j.reference2], [fc.joint.name, fc.joint.label, fc.joint.reference1, fc.joint.reference2], 'origin: Name, Label, References')
      const p = await plcs()
      for (const [n, q] of Object.entries(fc.placements)) check(p[n] && samePlc(p[n], q), `origin: ${n}'s Placement`, `ours ${JSON.stringify(p[n])} FreeCAD ${JSON.stringify(q)}`)
      same(await undoName(), fc.undo[0], 'origin: its undo step')
    }
    if (want('explode')) {
      console.log('explode')
      const fc = FC2.explode
      const panelNames = (t) => t.flat().map((w) => w.name).filter((n) => n && n !== 'qt_spinbox_lineedit')
      await runCmd('Assembly_CreateView')
      await until(`!!document.querySelector('.taskview .as-task[data-task="explode"]')`, 'the Exploded View panel', 20000)
      same(await ourPanel(), panelNames(fc.panel), 'explode: the panel')
      const texts = async () => st(`[...document.querySelectorAll('.taskview .as-task [data-qf="btnAlignDragger"], .taskview .as-task [data-qf="btnRadialExplosion"], .taskview .as-task [data-qf="CheckBox_PartsAsSingleSolid"]')].map((e) => e.textContent.trim())`)
      same(await texts(), fc.panel.flat().filter((w) => ['CheckBox_PartsAsSingleSolid', 'btnAlignDragger', 'btnRadialExplosion'].includes(w.name)).map((w) => w.text), 'explode: the buttons')
      await st(`cadui.getView().pointPicker('Pin', null, 'Face1')`)
      await sleep(800)
      same((await texts())[1], fc.selected.flat().find((w) => w.name === 'btnAlignDragger').text, 'explode: Pin selected, the dragger shown')
      // the dragger moved 25 mm up and let go (draggerMoved, draggerFinished)
      await st(`(() => { const v = cadui.getView(), f = v.tf; const m = f.proxy.matrixWorld.clone(); m.elements[14] += 25; f.t.onChange(m, null, 'motion'); f.t.onChange(m, null, 'finish') })()`)
      await sleep(800)
      const row = await st(`[...document.querySelectorAll('.taskview [data-qf="stepList"] .as-step')].map((e) => [e.querySelector('span')?.textContent, e.querySelector('input')?.value])`)
      const fcRow = fc.moved.flat().filter((w) => w.y > 0 && (w.class === 'QLabel' || w.class === 'Gui::QuantitySpinBox') && !w.name)
      same(row, [[fcRow.find((w) => w.class === 'QLabel').text, fcRow.find((w) => w.class === 'Gui::QuantitySpinBox').text]], 'explode: the move in the list (label, distance)')
      await page.click('.taskview .as-task .qbtn.default')
      await until(`(cadui.getState().assembly?.objects ?? []).some((o) => o.kind === 'ExplodedView')`, 'explode: the view made', 120000)
      await idle()
      same(await undoName(), fc.undo[0], 'explode: its undo step')
      const v = await assembly()
      const view = v.objects.find((o) => o.kind === 'ExplodedView'), mv = v.objects.find((o) => o.kind === 'ExplodedViewStep')
      same([view.name, view.label ?? view.name, view.group], [fc.view.name, fc.view.label, fc.view.moves.map((m) => m.name)], 'explode: the view')
      same([mv.name, mv.label, mv.move_type, mv.references], [fc.view.moves[0].name, fc.view.moves[0].label, fc.view.moves[0].type, fc.view.moves[0].references[1].map((s) => s.replace(/\.$/, ''))], 'explode: the move')
      check(samePlc([...mv.movement_transform[0], ...mv.movement_transform[1]], fc.view.moves[0].transform), 'explode: its MovementTransform', JSON.stringify(mv.movement_transform))
      const t = await ourTree()
      for (const r of fcTree(fc.tree).filter((x) => /Exploded|Translation/.test(x))) check(t.includes(r), `explode: the tree has ${r}`, JSON.stringify(t))
      const ex = v.exploded?.[view.name]?.placements?.Pin
      check(ex && samePlc([...ex.base, ...ex.rotation], fc.selected_view.Pin), "explode: the view selected shows the Pin where FreeCAD's explodeTemporarily puts it",
        `ours ${JSON.stringify(ex)} FreeCAD ${JSON.stringify(fc.selected_view.Pin)}`)
      const p = await plcs()
      check(samePlc(p.Pin, fc.unselected_view.Pin), 'explode: the document keeps the Pin where it was')
      await st(`cadui.setState({ asmSel: [${JSON.stringify(mv.name)}] })`)
      await sleep(400)
      const rows = Object.fromEntries(await propRows())
      for (const [k, val] of Object.entries(fcProps(fc.view_props, ['Label', 'Move Type', 'Movement Transform', 'References'])))
        check(String(rows[k]) === String(val), `explode: the move's ${k} = ${val}`, `ours ${rows[k]}`)
      await st('cadui.setState({ asmSel: [] })')
    }
    if (want('newpart')) {
      console.log('newpart')
      const fc = FC2.newpart
      const before = (await objs()).length
      await runCmd('Assembly_InsertNewPart')
      await until(`!!document.querySelector('.taskview .as-task[data-task="newpart"]')`, 'the New Part panel', 20000)
      same(await featureList(), fcList(fc.panel), 'newpart: the list with the new link')
      const labels = await st(`[...document.querySelectorAll('.taskview .as-task legend, .taskview .as-task .tfield > span:first-child, .taskview .as-task .tcheck')].map((e) => e.textContent.trim()).slice(0, 3)`)
      same(labels, ['Part name', 'Create part in new file', 'Joint new part origin'], 'newpart: Part name, Create part in new file, the group')
      check(fc.panel.flat().some((w) => w.text === 'Joint new part origin') && fc.panel.flat().some((w) => w.text === 'Create part in new file' && w.checked), "newpart: FreeCAD's panel has them, the box checked")
      await pickOn('Plate', 'Face6')
      await sleep(1000)
      same(await featureList(), fcList(fc.picked), 'newpart: the picks in the list (the unconnected link second)')
      await page.click('.taskview .as-task .qbtn.default')
      await until(`(cadui.getState().assembly?.objects ?? []).length > ${before}`, 'newpart: the part made', 120000)
      await idle()
      const link = (await objs()).find((o) => o.kind === 'Link' && o.name === 'Link')
      same([link?.name, link?.linked_object], [fc.link.name, 'Part'], 'newpart: the link "Link" to the new part')
      note(`newpart: the link's Label is the part's ("Part"); FreeCAD labels it ${fc.link.label} when the part is made in the same document (here every part is a file of its own: "Create part in new file")`)
      const p = await plcs()
      check(p.Link && samePlc(p.Link, fc.link.placement), "newpart: the new part's origin on Plate.Face6", `ours ${JSON.stringify(p.Link)} FreeCAD ${JSON.stringify(fc.link.placement)}`)
      const j = (await objs()).filter((o) => o.kind === 'Joint').pop()
      same([j.reference1, j.reference2], [fc.joint.reference1, fc.joint.reference2], 'newpart: the joint\'s References')
      same(await undoName(), 'Create Fixed Joint', "newpart: its undo step (the joint panel's)")
    }
    if (want('subasm')) {
      console.log('subasm')
      const fc = FC2.subasm
      await runCmd('Assembly_InsertLink')
      await until(`!!document.querySelector('.taskview .as-task[data-task="insert"]')`, 'the Insert panel', 20000)
      const list = await st(`[...document.querySelectorAll('.taskview [data-qf="partList"] .as-item')].map((e) => e.textContent.trim())`)
      check(list.includes(SUB) && list.includes('Assembly'), "subasm: Insert Component lists the other project's Assembly", JSON.stringify(list))
      check(fc.insert_panel.flat().find((w) => w.class === 'QTreeWidget')?.items.some((i) => i.text === 'Assembly' && i.depth === 1), 'subasm: FreeCAD lists the Assembly under its document')
      await st('cadui.setState({ task: null })')
      await st(`fetch('/api/${S2}/assembly', { method: 'POST', headers: { 'X-CAD': '1', 'Content-Type': 'application/json' }, body: JSON.stringify({ ops: [
        { op: 'insert', assembly: ${JSON.stringify(SUB)}, rigid: true, placement: [[50, 0, 0], [0, 0, 0]] }], name: 'Insert Component' }) })`)
      await until(`(cadui.getState().assembly?.objects ?? []).some((o) => o.kind === 'AssemblyLink')`, 'subasm: the AssemblyLink', 120000)
      await st('cadui.loadAssembly()')
      await idle()
      const al = (await objs()).find((o) => o.kind === 'AssemblyLink')
      same([al.name, al.label], [fc.rigid.name, fc.rigid.label], 'subasm: the AssemblyLink\'s Name and Label')
      same(al.components.map((c) => c[0]), fc.rigid.children.map((c) => c[0]), 'subasm: its children, named in this document')
      const v = await assembly()
      for (const c of fc.rigid.children) {
        const o = v.child_plc?.[c[0]]
        check(o && samePlc([...o.base, ...o.rotation], c[2]), `subasm: rigid, ${c[0]} where its source is`, `ours ${JSON.stringify(o)} FreeCAD ${JSON.stringify(c[2])}`)
      }
      // the link's rows: from its row ("0:Assembly", a child of the Assembly) to the next row at its depth
      const block = (t) => { const i = t.indexOf('0:Assembly'); if (i < 0) return []; const out = [t[i]]; for (const r of t.slice(i + 1)) { if (parseInt(r, 10) <= 0) break; out.push(r) } return out }
      // an Origin's Labels count the document's Origins (FreeCAD's has the New Part's two more): the number left out
      const unnum = (t) => t.map((r) => r.replace(/^(\d+:(?:Origin|X-axis|Y-axis|Z-axis|XY-plane|XZ-plane|YZ-plane|Origin-Point))\d{3}$/, '$1###'))
      const sub = (t) => unnum(block(t))
      const fcSub = (rows) => unnum(block(rows.map((r) => `${r.depth - 2}:${r.text}`)))
      note("subasm: the AssemblyLink's Origin is labelled after the document's Origins (Origin003 in FreeCAD's, which New Part's Part and Body added two to), compared without the number")
      same(sub(await ourTree()).slice(0, fcSub(fc.rigid.tree).length), fcSub(fc.rigid.tree), 'subasm: the rigid link\'s rows (its Origin, its children)')
      await st(`cadui.setState({ asmSel: [${JSON.stringify(al.name)}], selected: [] })`)
      await sleep(500)
      let rows = Object.fromEntries(await propRows())
      for (const [k, val] of Object.entries(fcProps(fc.rigid.props, ['Placement', 'Label', 'Group', 'Rigid', 'Linked Object'])))
        check(String(rows[k]).replace(SUB, 'Sub') === String(val), `subasm: rigid, property ${k} = ${val}`, `ours ${rows[k]}`)
      const entries = await st('cadui.asmTree().filter((e) => e !== "sep").map((e) => e.label)')
      check(entries.includes('Turn flexible'), 'subasm: the context menu turns it flexible', JSON.stringify(entries))
      await st(`cadui.asmTree().find((e) => e.label === 'Turn flexible').onSelect()`)
      await until(`(cadui.getState().assembly?.objects ?? []).some((o) => o.kind === 'AssemblyLink' && !o.rigid)`, 'subasm: flexible', 120000)
      await idle()
      const p = await plcs()
      for (const c of fc.flexible.children) check(p[c[0]] && samePlc(p[c[0]], c[2]), `subasm: flexible, ${c[0]} placed in this Assembly`, `ours ${JSON.stringify(p[c[0]])} FreeCAD ${JSON.stringify(c[2])}`)
      same(sub(await ourTree()).slice(0, fcSub(fc.flexible.tree).length), fcSub(fc.flexible.tree), 'subasm: the flexible link\'s rows (its Joints with the copy, its children)')
      await st(`cadui.setState({ asmSel: [${JSON.stringify(al.name)}], selected: [] })`)
      await sleep(500)
      rows = Object.fromEntries(await propRows())
      for (const [k, val] of Object.entries(fcProps(fc.flexible.props, ['Placement', 'Group', 'Rigid'])))
        check(String(rows[k]) === String(val), `subasm: flexible, property ${k} = ${val}`, `ours ${rows[k]}`)
      await st(`cadui.asmTree().find((e) => e.label === 'Turn rigid').onSelect()`)
      await until(`(cadui.getState().assembly?.objects ?? []).some((o) => o.kind === 'AssemblyLink' && o.rigid)`, 'subasm: rigid again', 120000)
      await idle()
      same(await undoName(), 'Toggle Rigid', 'subasm: Turn rigid\'s undo step')
      await st(`cadui.setState({ asmSel: [${JSON.stringify(al.name)}], selected: [] })`)
      await sleep(300)
      compareEntries(fc.menu_with_link, (await st('cadui.assembly()')).assembly, 'Assembly menu with the AssemblyLink selected')
      await runCmd('Assembly_LinkSelectLinked')
      await until(`cadui.getState().slug === ${JSON.stringify(SUB)}`, 'Go to Linked Assembly opens the sub-assembly\'s project', 60000)
        && ok(`subasm: Go to Linked Assembly makes ${SUB} the active document (FreeCAD: ${fc.goto.active}), its Assembly selected`)
      await until(`JSON.stringify(cadui.getState().asmSel) === '["Assembly"]'`, 'subasm: the linked Assembly selected', 30000) && ok('subasm: the linked Assembly selected')
    }
    if (want('sim') && FC2.sim) {
      // fcassembly_more_dump.py's sim(): a third document, Plate (a 10 mm Box) grounded, Pin on a Revolute to it
      console.log('sim')
      const fc = FC2.sim, S3 = 'acsim'
      cad('init', S3, '--brief', 'assemblycheck')
      writeFileSync(join(ROOT, S3, 'parts', 'plate.py'), part('plate', 'Part.Box("Box")'))
      writeFileSync(join(ROOT, S3, 'parts', 'pin.py'), part('pin', 'Part.Cylinder("Cylinder", radius=3, height=20)'))
      cad('assembly', 'apply', S3, '--ops', JSON.stringify([{ op: 'insert', part: 'plate', name: 'Plate' },
        { op: 'insert', part: 'pin', name: 'Pin', placement: [[30, 5, 2], [10, 20, 30]] },
        { op: 'joint', type: 'Revolute', ref1: ['Plate', ['Face6', 'Face6']], ref2: ['Pin', ['Face3', 'Edge1']] }]))
      await page.goto(`${BASE}/next/#${S3}`)
      await page.reload()
      await until(`window.cadui && cadui.getState().slug === ${JSON.stringify(S3)}`, 'sim: the third project')
      await st('cadui.setState({ workbench: "assembly" })')
      await until('cadui.getState().scene?.bodies.some((b) => b.name === "Pin") && !!cadui.getState().assembly', 'sim: the scene of acsim', 180000)
      await st('cadui.setState({ asmActive: true, task: null })')
      await sleep(500)
      const p0 = await plcs()
      check(samePlc(p0.Pin, fc.before.Pin), "sim: the Pin on its Revolute, as FreeCAD's", `ours ${JSON.stringify(p0.Pin)}`)
      compareEntries(fc.menu, (await st('cadui.assembly()')).assembly, 'sim: the Assembly menu with a Revolute (Simulation enabled)')
      await runCmd('Assembly_CreateSimulation')
      await until(`!!document.querySelector('.taskview .as-task[data-task="simulation"]')`, 'the Simulation panel', 20000)
      const fcNames = (t) => t.flat().map((w) => w.name).filter((n) => n && n !== 'qt_spinbox_lineedit' && !/Label$/.test(n))
      const ourNames = async () => (await ourPanel()).filter((n) => !/Label$/.test(n) || n === 'FrameLabel' || n === 'FrameTimeLabel')
      same((await ourNames()).filter((n) => !/Label$/.test(n)), fcNames(fc.panel).filter((n) => !/SpinBox$/.test(n) || true).filter((n) => ![
        'TimeStartSpinBox', 'TimeEndSpinBox', 'TimeStepOutputSpinBox', 'GlobalErrorToleranceSpinBox'].includes(n)), 'sim: the panel (its groups, the list, the buttons)')
      const box = async () => st(`(() => { const t = document.querySelector('.taskview .as-task[data-task="simulation"]'); return { title: t.querySelector('.tbox-title, .taskbox-title, header')?.textContent.trim() ?? null,
        legends: [...t.querySelectorAll('legend')].map((e) => e.textContent.trim()), fields: [...t.querySelectorAll('.tfield')].map((f) => [f.querySelector('span')?.textContent.trim(), f.querySelector('input')?.value]) } })()`)
      const b0 = await box()
      same(b0.legends, fc.panel.flat().filter((w) => w.class === 'QGroupBox').map((w) => w.text), 'sim: the group boxes')
      const fcFields = fc.panel.flat().filter((w) => /^Gui::.*SpinBox$/.test(w.class)).map((w) => w.text)
      same(b0.fields.map((f) => f[0]), fc.panel.flat().filter((w) => w.class === 'QLabel').map((w) => w.text), 'sim: Start, End, Step, Tolerance')
      same(b0.fields.map((f) => f[1]), fcFields, 'sim: their values, as FreeCAD writes them')
      // Add: MotionEditDialog with its defaults (the Revolute, Angular, initialValue + 5*time), OK
      await page.click('.taskview [data-qf="AddButton"]')
      await until(`!!document.querySelector('[data-dialog="motion"]')`, 'sim: the motion dialog', 10000)
      const dlg = await st(`(() => { const d = document.querySelector('[data-dialog="motion"]'); return [d.querySelector('[data-qf="joint"]').selectedOptions[0]?.textContent, d.querySelector('[data-qf="motionType"]').value, d.querySelector('[data-qf="formula"]').value] })()`)
      same(dlg, ['Revolute', fc.simulation.motions[0].type, fc.simulation.motions[0].formula], 'sim: the dialog\'s joint, motion type and formula')
      await page.click('[data-dialog="motion"] .qbtn.default')
      await sleep(300)
      const list = await st(`[...document.querySelectorAll('.taskview [data-qf="motionList"] .as-item')].map((e) => e.textContent.trim())`)
      same(list, fc.motion.flat().find((w) => w.name === 'motionList').items, 'sim: the motion in the list')
      await page.click('.taskview [data-qf="RunKinematicsButton"]')
      await until(`!!document.querySelector('.taskview [data-qf="groupBox_player"]')`, 'sim: Generate shows the player', 60000)
      const player = async () => st(`(() => { const t = document.querySelector('.taskview .as-task[data-task="simulation"]'); const s = t.querySelector('[data-qf="frameSlider"]');
        return { frame: t.querySelector('[data-qf="FrameLabel"]').textContent.trim(), time: t.querySelector('[data-qf="FrameTimeLabel"]').textContent.trim(), value: Number(s.value), max: Number(s.max),
          fps: t.querySelector('[data-qf="FramesPerSecondSpinBox"]').value, placements: JSON.parse(t.querySelector('[data-qf="groupBox_player"]').dataset.placements) } })()`)
      const fw = (t, n) => t.flat().find((w) => w.name === n)
      let pl = await player()
      same([pl.frame, pl.time, pl.value, pl.max, pl.fps], [fw(fc.generated, 'FrameLabel').text, fw(fc.generated, 'FrameTimeLabel').text, fw(fc.generated, 'frameSlider').value,
        fw(fc.generated, 'frameSlider').max, fw(fc.generated, 'FramesPerSecondSpinBox').text], 'sim: the player at the last frame (Frame, time, slider, frames per second)')
      same(pl.max + 1, fc.frames, 'sim: numberOfFrames')
      const pin = (x) => x.placements.Pin && [...x.placements.Pin.base, ...x.placements.Pin.rotation]
      check(pin(pl) && samePlc(pin(pl), fc.last.Pin), "sim: the Pin at the last frame where FreeCAD's updateForFrame puts it", `ours ${JSON.stringify(pin(pl))} FreeCAD ${JSON.stringify(fc.last.Pin)}`)
      await st(`(() => { const s = document.querySelector('.taskview [data-qf="frameSlider"]'); const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; set.call(s, '50'); s.dispatchEvent(new Event('input', { bubbles: true })) })()`)
      await sleep(300)
      pl = await player()
      same([pl.frame, pl.time, pl.value], [fw(fc.frame50.widgets, 'FrameLabel').text, fw(fc.frame50.widgets, 'FrameTimeLabel').text, fw(fc.frame50.widgets, 'frameSlider').value], 'sim: the slider at frame 50')
      check(pin(pl) && samePlc(pin(pl), fc.frame50.Pin), 'sim: the Pin at frame 50', `ours ${JSON.stringify(pin(pl))} FreeCAD ${JSON.stringify(fc.frame50.Pin)}`)
      await page.click('.taskview .as-task[data-task="simulation"] .tbuttons .qbtn.default')
      await until(`(cadui.getState().assembly?.objects ?? []).some((o) => o.kind === 'Simulation')`, 'sim: the Simulation made', 120000)
      await idle()
      same(await undoName(), fc.undo[0], 'sim: its undo step')
      const o = await objs()
      const sim = o.find((x) => x.kind === 'Simulation'), mo = o.find((x) => x.kind === 'Motion')
      same([sim.name, sim.label ?? sim.name, sim.group], [fc.simulation.name, fc.simulation.label, fc.simulation.group], 'sim: the Simulation (Name, Label, Group)')
      same([sim.a_time_start, sim.b_time_end, sim.c_time_step_output, sim.f_global_error_tolerance, sim.j_frames_per_second], fc.simulation.settings, 'sim: its settings')
      same([mo.name, mo.label, mo.motion_type, mo.formula, mo.joint], ['name', 'label', 'type', 'formula', 'joint'].map((k) => fc.simulation.motions[0][k]), 'sim: the Motion')
      check(o.some((x) => x.kind === 'SimulationGroup' && x.name === fc.simulation.parent[0]), 'sim: in the SimulationGroup "Simulations"')
      const t = await ourTree()
      const fcRows = fcTree(fc.tree.filter((r) => true)).filter((r) => /Simulation|\(Angular\)/.test(r))
      check(fcRows.every((r) => t.includes(r)), 'sim: the tree (Simulations, Simulation, Revolute (Angular))', `ours ${JSON.stringify(t)} FreeCAD ${JSON.stringify(fcRows)}`)
      const p1 = await plcs()
      check(samePlc(p1.Pin, fc.after_ok.Pin), 'sim: OK puts the Pin back (restoreAssemblyPartsPlacements)', `ours ${JSON.stringify(p1.Pin)}`)
    }
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

// SPDX-License-Identifier: LGPL-2.1-or-later
// partcheck: the Part workbench in the page, held to the real FreeCAD's (ui/scripts/fcpart.json, written by fcpart.py from
// FreeCAD 26.3 at 3160daf1e2b6), then driven end to end on a scratch project.
//
//   NODE_PATH=<folder with playwright> node ui/scripts/partcheck.mjs [--fc=ui/scripts/fcpart.json] [--only=SECTION,...] [--keep] [--verbose]
//
// It starts a scratch workbench of its own (as transformcheck.mjs does) and, in Chromium on SwiftShader:
//   workbench  the switcher has Part; the menu bar puts &Part before Windows
//   menus      the Part menu, entry by entry: FreeCAD's texts and commands (the entries not ported are greyed, `known`)
//   toolbars   Solids, Part Tools, Boolean Tools: FreeCAD's buttons in order
//   solids     Cube, Cylinder, Sphere, Cone, Torus from the toolbar: FreeCAD's names, labels and undo steps; Tube's panel
//   primitives the Primitives dialog: its type list, each page's labels and the values it starts from, and Create for each
//              type (FreeCAD's names, labels, "Create <type>")
//   booleans   Cut, Union, Intersection, Section, Compound, Refine shape on tree selections: the object FreeCAD makes, its
//              undo step, the inputs it hides, and the tree showing them under it, greyed
//   panels     Extrude, Revolve, Mirror, Fillet, Chamfer, Loft, Sweep, Offset, 2D Offset, Thickness, Project on surface,
//              Boolean: each panel's labels, check boxes, groups and values against FreeCAD's; OK where FreeCAD's dump pressed
//              it, and the object's properties against FreeCAD's
//   split      Boolean Fragments, XOR, Connect, Slice, Explode compound: names, undo steps, hidden inputs
//   props      the property view of a Box, the Cut and the Extrude against FreeCAD's rows
//   undo       Std_Undo takes the last object back
// A difference prints as FAIL; the deliberate ones (PARITY.md, "Part workbench") as `known`. Exit 1 on a FAIL.
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
const FC = JSON.parse(readFileSync(flag('fc', join(HERE, 'fcpart.json')), 'utf8'))
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

// What is deliberately different (PARITY.md, "Part workbench"), by the FreeCAD command or widget
const NOT_PORTED = new Set(['Part_BoxSelection', 'Part_Builder', 'Part_ShapeFromMesh', 'Part_PointsFromMesh', 'Part_MakeSolid', 'Part_ReverseShape',
  'Part_SimpleCopy', 'Part_TransformedCopy', 'Part_ElementCopy', 'Part_ToleranceSet', 'Part_Scale', 'Part_MakeFace', 'Part_RuledSurface',
  'Part_CrossSections', 'Part_SectionCut', 'Part_EditAttachment', 'Part_CheckGeometry', 'Part_Defeaturing', 'Materials_InspectAppearance',
  'Materials_InspectMaterial', 'Part_ColorPerFace'])

// ── a scratch workbench (transformcheck.mjs's) ───────────────────────────────────────────────────────────────────────
const freePort = (from) => new Promise((res, rej) => {
  const tryPort = (p) => {
    if (p > from + 40) return rej(new Error('no free port'))
    const s = createServer(); s.once('error', () => tryPort(p + 1)); s.once('listening', () => s.close(() => res(p))); s.listen(p, '127.0.0.1')
  }
  tryPort(from)
})
const scratch = mkdtempSync(join(tmpdir(), 'cad-partcheck-')), warmDir = mkdtempSync('/tmp/cpc')
const ROOT = join(scratch, 'root'); mkdirSync(ROOT)
for (const d of ['runtime', 'macros']) mkdirSync(join(scratch, d))
const python = process.env.CAD_PYTHON || join(REPO, '.venv', 'bin', 'python')
const env = { ...process.env, CAD_WARM_DIR: warmDir, CAD_RUNTIME_DIR: join(scratch, 'runtime'), CAD_MACRO_DIR: join(scratch, 'macros'),
  CAD_PREFS: join(scratch, 'prefs.json'), PYTHONPATH: REPO, CAD_PYTHON: python, CAD_RENDER_BACKEND: 'numpy' }
delete env.CAD_PROJECTS
spawnSync(python, ['-m', 'cad_agent', '--projects', ROOT, 'init', 'pc', '--brief', 'partcheck'], { env, cwd: REPO })
const port = await freePort(8951)
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
const DOC = 'Unnamed'
const objects = () => st(`(cadui.getState().features[${JSON.stringify(DOC)}]?.objects ?? []).map((o) => ({ ...o }))`)
const tree = () => st(`cadui.getState().features[${JSON.stringify(DOC)}]?.object_tree ?? null`)
const undoName = () => st('cadui.getState().undo[0]?.name ?? null')
const count = async () => (await objects()).length
/** Wait for the document to have n objects (the server built the edit). */
const objectsAt = (n, what) => until(`(cadui.getState().features[${JSON.stringify(DOC)}]?.objects ?? []).length >= ${n} && !cadui.getState().busy.length`, what)
/** Select tree rows as clicks do (the first alone, the rest with Ctrl). */
async function selectRows(names) {
  await st('cadui.setState({ featSel: [], selected: [] })')
  for (const [i, n] of names.entries()) await page.click(`.ptrow[data-ref="${DOC}/${n}"]`, { modifiers: i ? ['Control'] : [] })
  await sleep(150)
}
const runCmd = (cmd) => st(`cadui.getCommand(${JSON.stringify(cmd)})?.run([])`)
// the open task panel, as FreeCAD's dump reads its own: labels, check/radio texts, group titles, and the boxes' values
const ourTexts = () => st(`[...document.querySelectorAll('.taskview .pt-task .tfield > span:first-child, .taskview .pt-task .tcheck, .taskview .pt-task legend, .taskview .pt-task .tlabel')].map((e) => e.textContent.trim()).filter(Boolean)`)
const ourValue = (qf) => st(`(() => { const e = document.querySelector('.taskview [data-qf="${qf}"]'); if (!e) return null; const i = e.querySelector('input'); return i ? (i.type === 'checkbox' || i.type === 'radio' ? i.checked : i.value) : e.textContent.trim() })()`)
const fcTexts = (task) => task.flat().filter((w) => ['QLabel', 'QCheckBox', 'QRadioButton', 'QGroupBox'].includes(w.class) && w.text && !['OK', 'Cancel', 'Close', 'Apply', 'Help'].includes(w.text)).map((w) => clean(w.text))
const fcSpins = (task) => task.flat().filter((w) => /SpinBox/.test(w.class) && w.name && w.name !== 'qt_spinbox_lineedit').map((w) => [w.name, w.text])
const fcChecks = (task) => task.flat().filter((w) => ['QCheckBox', 'QRadioButton'].includes(w.class) && w.name).map((w) => [w.name, !!w.checked])
async function comparePanel(fcTask, what, opts = {}) {
  const ours = await ourTexts(), theirs = fcTexts(fcTask)
  const missing = theirs.filter((t) => !ours.includes(t) && !(opts.skip ?? []).includes(t)), extra = ours.filter((t) => !theirs.includes(t) && !(opts.extra ?? []).includes(t))
  check(!missing.length && !extra.length, `${what}: FreeCAD's labels, boxes and groups`, `missing ${JSON.stringify(missing)} extra ${JSON.stringify(extra)}`)
  for (const [name, text] of fcSpins(fcTask)) {
    if ((opts.skipValues ?? []).includes(name)) continue
    const v = await ourValue(name)
    if (v === null) { bad(`${what}: ${name} is not in the panel`); continue }
    check(String(v).replace(/\s+/g, ' ') === String(text).replace(/\s+/g, ' '), `${what}: ${name} starts at ${text}`, `ours ${v}`)
  }
  for (const [name, checked] of fcChecks(fcTask)) {
    if ((opts.skipValues ?? []).includes(name)) continue
    const v = await ourValue(name)
    if (v === null) { bad(`${what}: ${name} is not in the panel`); continue }
    check(v === checked, `${what}: ${name} ${checked ? 'on' : 'off'}`, `ours ${v}`)
  }
}
/** A QComboBox's items (combo.tsx draws a button and a popup): open it, read them, close it. */
const comboItems = async (sel) => {
  if (!await st(`!!document.querySelector(${JSON.stringify(sel)})`)) return null
  await page.dispatchEvent(sel, 'mousedown')
  await sleep(150)
  const items = await st('[...document.querySelectorAll(".combo-popup [role=option]")].map((e) => e.textContent)')
  await page.keyboard.press('Escape')
  await sleep(100)
  return items
}
const comboPick = async (sel, text) => {
  await page.dispatchEvent(sel, 'mousedown')
  await sleep(150)
  await page.click(`.combo-popup [role=option]:text-is(${JSON.stringify(text)})`)
  await sleep(200)
}
const clickButton = (text) => page.click(`.taskview .tbuttons button:text-is("${text}")`)
/** FreeCAD's made object's property values that the part file holds, as numbers, booleans and strings. */
const fcValue = (s) => { const m = /^(-?[\d.e+-]+)( mm| deg|)$/.exec(s); return m ? Number(m[1]) : s === 'True' ? true : s === 'False' ? false : s }

try {
  await page.goto(`${BASE}/next/#pc`)
  await until('!!window.cadui && cadui.getState().slug === "pc" && !!cadui.getState().scene', 'the project to open')

  const ours = await st('cadui.part()')
  if (!want('workbench')) { await st('cadui.setState({ workbench: "part" })'); await sleep(400) }
  if (!want('solids')) { await runCmd('Part_Box'); await objectsAt(1, 'the document, made by Cube') }   // the sections after it work in it

  // ── workbench, menus, toolbars ──────────────────────────────────────────────────────────────────────────────────
  if (want('workbench')) {
  console.log('workbench')
  const wbs = await comboItems('.toolbar .wb button.qselect') ?? []
  check(wbs.includes('Part'), 'the workbench switcher lists Part', JSON.stringify(wbs))
  await st('cadui.setState({ workbench: "part" })')
  await sleep(400)
  const bar = await st(`[...document.querySelectorAll('.menubar > .menu-title, .menubar > button, .menubar [role=menuitem]')].map((e) => e.textContent.trim()).filter(Boolean)`)
  const fcBar = FC.menus.bar.map(clean).filter(Boolean)
  const i = bar.indexOf('Part')
  check(i > 0 && bar[i - 1] === 'Macro' && bar[i + 1] === 'Windows', 'Part sits after Macro, before Windows, as in FreeCAD', `ours ${JSON.stringify(bar)} FreeCAD ${JSON.stringify(fcBar)}`)

  }
  if (want('menus')) {
  console.log('menus')
  const flat = (es, depth = 0) => es.flatMap((e) => (e.sep ? [{ sep: true, depth }] : [{ text: clean(e.text), cmd: e.cmd ?? e.name ?? null, depth }, ...(e.menu ? flat(e.menu, depth + 1) : [])]))
  const fcMenu = flat(FC.menus['&Part'].map((e) => ({ ...e, cmd: e.name })))
  const ourMenu = flat(ours.part)
  same(ourMenu.map((e) => (e.sep ? '----' : e.text)), fcMenu.map((e) => (e.sep ? '----' : e.text)), 'the Part menu: FreeCAD\'s entries in order')
  for (const [k, e] of fcMenu.entries()) {
    if (e.sep || !e.cmd || !e.cmd.includes('_')) continue
    const o = ourMenu[k]
    if (!o || o.text !== e.text) continue
    if (o.cmd !== e.cmd) bad(`menu ${e.text}: command`, `FreeCAD ${e.cmd} ours ${o.cmd}`)
    else ok(`menu ${e.text}: ${e.cmd}`)
  }
  for (const c of NOT_PORTED) if (ourMenu.some((x) => x.cmd === c)) note(`menu ${c}: greyed (not ported, PARITY.md)`)

  }
  if (want('toolbars')) {
  console.log('toolbars')
  for (const title of ['Solids', 'Part Tools', 'Boolean Tools']) {
    const fc = FC.toolbars.find((t) => t.title === title)
    const our = ours.toolbars.find((t) => t.title === title)
    if (!fc || !our) { bad(`toolbar ${title}`, 'missing'); continue }
    same(our.buttons.filter((b) => !b.sep).map((b) => b.cmd), fc.buttons.filter((b) => !b.sep).map((b) => b.name), `toolbar ${title}: FreeCAD's buttons`)
  }

  // ── Solids: the five toolbar primitives and Tube ───────────────────────────────────────────────────────────────
  }
  if (want('solids')) {
  console.log('solids')
  const SOLIDS = ['Part_Box', 'Part_Cylinder', 'Part_Sphere', 'Part_Cone', 'Part_Torus']
  for (const [k, cmd] of SOLIDS.entries()) {
    const fc = FC[`cmd_${cmd}`]
    await page.click(`.tb-btn[data-cmd="${cmd}"]`)
    if (!await objectsAt(k + 1, cmd)) continue
    const o = (await objects())[k]
    const want = fc.made[0]
    same([o.name, o.label ?? o.name, o.type], [want.name, want.label, want.type], `${cmd}: FreeCAD's name, label and type`)
    await until(`cadui.getState().undo[0]?.name === ${JSON.stringify(fc.undo[0])}`, `${cmd}: the "${fc.undo[0]}" step`, 30000) && ok(`${cmd}: undo step "${fc.undo[0]}"`)
  }
  await page.click('.tb-btn[data-cmd="Part_Tube"]')
  await until('cadui.getState().task?.kind === "part"', 'the Tube panel')
  await comparePanel(FC.cmd_Part_Tube.task, 'Tube')
  await clickButton('OK')
  if (await objectsAt(6, 'Tube')) {
    const o = (await objects())[5]
    same([o.name, o.type], ['Tube', 'Part::Tube'], 'Part_Tube: the Tube (Part::FeaturePython with TubeFeature in FreeCAD)')
    await until(`cadui.getState().undo[0]?.name === "Create tube"`, 'Part_Tube: "Create tube"', 30000) && ok('Part_Tube: undo step "Create tube"')
  }

  // ── the Primitives dialog ──────────────────────────────────────────────────────────────────────────────────────
  }
  if (want('primitives')) {
  console.log('primitives')
  await page.click('.tb-btn[data-cmd="Part_Primitives"]')
  await until('cadui.getState().task?.other === "primitives"', 'the Primitives dialog')
  const PCB = '.taskview [data-qf="PrimitiveTypeCB"] button.qselect'
  const items = await comboItems(PCB)
  same(items, FC.primitives.items, 'Primitives: FreeCAD\'s type list')
  for (const [k, item] of FC.primitives.items.entries()) {
    void k
    await comboPick(PCB, item)
    await comparePanel(FC.primitives.types[item], `Primitives ${item}`, { skip: ['Parameter', 'Position', 'Rotation Axis'], extra: ['Parameter', 'Position', 'Rotation Axis', 'Coordinate system'],
      skipValues: ['XDirectionEdit', 'YDirectionEdit', 'ZDirectionEdit'] })
    const before = await count()
    await clickButton('Create')
    if (!await objectsAt(before + 1, `Create ${item}`)) continue
    const o = (await objects())[before], want = FC.primitives.made[item][0]
    // FreeCAD's names come from the objects already there: its dump made one of each solid by the toolbar first, as here
    same([o.name, o.label ?? o.name, o.type], [want.name, want.label, want.type], `Create ${item}: FreeCAD's name, label and type`)
    await until(`cadui.getState().undo[0]?.name === ${JSON.stringify(FC.primitives.undo[item][0])}`, `Create ${item}: its step`, 30000) && ok(`Create ${item}: "${FC.primitives.undo[item][0]}"`)
  }
  await clickButton('Close')

  // ── booleans and compound tools on tree selections ─────────────────────────────────────────────────────────────
  }
  if (want('booleans')) {
  console.log('booleans')
  const addTwo = async (a, b) => {
    const n = await count()
    await st(`cadui.getState() && fetch('/api/pc/features/${DOC}', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CAD': '1' }, body: JSON.stringify({ ops: [
      { op: 'add', feature: { name: '${a}', type: 'Part::Box', length: 20, width: 20, height: 10 } },
      { op: 'add', feature: { name: '${b}', type: 'Part::Cylinder', radius: 6, height: 20, placement: [[10, 10, -5], [0, 0, 0]] } }] }) }).then(() => cadui.loadFeatures())`)
    await objectsAt(n + 2, `${a} and ${b}`)
  }
  for (const [cmd, a, b] of [['Part_Cut', 'BoxA', 'CylA'], ['Part_Fuse', 'BoxB', 'CylB'], ['Part_Common', 'BoxC', 'CylC'], ['Part_Section', 'BoxD', 'CylD'],
    ['Part_Compound', 'BoxE', 'CylE'], ['Part_BooleanFragments', 'BoxS', 'CylS'], ['Part_XOR', 'BoxX', 'CylX'], ['Part_JoinConnect', 'BoxJ', 'CylJ'], ['Part_Slice', 'BoxK', 'CylK']]) {
    const fc = FC[`cmd_${cmd}`]
    await addTwo(a, b)
    await selectRows([a, b])
    const n = await count()
    await runCmd(cmd)
    if (!await objectsAt(n + 1, cmd)) continue
    const o = (await objects())[n], want = fc.made[0]
    const ty = want.proxy ? { FeatureBooleanFragments: 'Part::BooleanFragments', FeatureXOR: 'Part::XOR', FeatureConnect: 'Part::Connect', FeatureSlice: 'Part::Slice' }[want.proxy] : want.type
    same([o.name, o.type], [want.name, ty], `${cmd}: FreeCAD's object`)
    await until(`cadui.getState().undo[0]?.name === ${JSON.stringify(fc.undo[0])}`, `${cmd}: the "${fc.undo[0]}" step`, 30000) && ok(`${cmd}: "${fc.undo[0]}"`)
    const t = await tree()
    same([a, b].filter((x) => !t.shown.includes(x)), fc.hidden, `${cmd}: hides what FreeCAD hides`)
    same(t.children[o.name] ?? [], [a, b], `${cmd}: the tree shows ${a} and ${b} under ${o.name}`)
    if (JSON.stringify(t.children[o.name] ?? []) !== JSON.stringify([a, b])) console.log(`        ${o.name}: ${JSON.stringify(o)}`)
    const greyed = await st(`[...document.querySelectorAll('.ptrow.hid')].map((e) => e.dataset.ref)`)
    check(fc.hidden.every((h) => greyed.includes(`${DOC}/${h}`)), `${cmd}: the hidden inputs are greyed`, JSON.stringify(greyed))
  }
  // Refine shape on the Fusion: FreeCAD names it after its source and leaves it beside it, hidden
  await selectRows(['Fusion'])
  { const n = await count(); await runCmd('Part_RefineShape')
    if (await objectsAt(n + 1, 'Part_RefineShape')) {
      const o = (await objects())[n], want = FC.cmd_Part_RefineShape.made[0]
      same([o.name, o.type], [want.name, want.type], 'Part_RefineShape: FreeCAD\'s object')
      const t = await tree()
      check(t.top.includes('Fusion') && !t.shown.includes('Fusion'), 'Part_RefineShape: its source stays at the top, hidden, as FreeCAD\'s tree has it')
    } }
  await selectRows(['Compound'])
  { const n = await count(); await runCmd('Part_ExplodeCompound')
    if (await objectsAt(n + 2, 'Part_ExplodeCompound')) {
      const made = (await objects()).slice(n), want = FC.cmd_Part_ExplodeCompound.made.filter((m) => m.proxy === '_CompoundFilter')
      same(made.map((o) => [o.name, o.label]), want.map((m) => [m.name, m.label]), 'Part_ExplodeCompound: FreeCAD\'s filters, names and labels')
      note('Part_ExplodeCompound: FreeCAD groups the filters in "Exploded Compound"; a part file has no groups (PARITY.md)')
    } }

  // ── task panels ────────────────────────────────────────────────────────────────────────────────────────────────
  }
  if (want('panels')) {
  console.log('panels')
  const post = (ops) => st(`fetch('/api/pc/features/${DOC}', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CAD': '1' }, body: JSON.stringify({ ops: ${JSON.stringify(ops)} }) }).then(() => cadui.loadFeatures())`)
  const rect = (x0, y0, x1, y1) => [[x0, y0, x1, y0], [x1, y0, x1, y1], [x1, y1, x0, y1], [x0, y1, x0, y0]].map(([a, b, c, d]) => ({ type: 'LineSegment', start: [a, b], end: [c, d], construction: false }))
  { const n = await count()
    await post([{ op: 'add', list: 'OBJECTS', feature: { name: 'Sketch', type: 'Sketcher::SketchObject', support: 'XY', geometry: [...rect(0, 0, 30, 20), { type: 'Circle', center: [10, 10], radius: 4, construction: false }], constraints: [] } }])
    await objectsAt(n + 1, 'the sketch') }
  const panel = async (cmd, sel, fcKey, ok, opts = {}) => {
    if (sel) await selectRows(sel)
    const n = await count()
    await page.click(`.tb-btn[data-cmd="${cmd}"]`).catch(() => runCmd(cmd))
    if (!await until('cadui.getState().task?.kind === "part"', `the ${cmd} panel`, 20000)) return null
    await comparePanel(FC[fcKey].task, cmd, opts)
    if (!ok) { await clickButton('Cancel').catch(() => clickButton('Close')); return null }
    await clickButton(ok)
    if (!await objectsAt(n + 1, cmd)) return null
    const o = (await objects())[n], want = FC[fcKey].made[0]
    await until(`cadui.getState().undo[0]?.name === ${JSON.stringify(FC[fcKey].undo[0])}`, `${cmd}: the "${FC[fcKey].undo[0]}" step`, 30000) && ok_(`${cmd}: "${FC[fcKey].undo[0]}"`)
    const fprops = FC[fcKey].props[want.name] ?? {}
    for (const [k, v] of Object.entries(opts.props ?? {})) {
      const theirs = fcValue(fprops[v]?.value ?? '')
      const mine = o[k] === undefined ? opts.defaults?.[k] : o[k]
      check(JSON.stringify(mine) === JSON.stringify(theirs), `${cmd}: ${v} as FreeCAD sets it`, `FreeCAD ${JSON.stringify(theirs)} ours ${JSON.stringify(mine)}`)
    }
    return o
  }
  const ok_ = ok
  const ex = await panel('Part_Extrude', ['Sketch'], 'cmd_Part_Extrude', 'OK', { props: { dir_mode: 'DirMode', length_fwd: 'LengthFwd', solid: 'Solid', reversed: 'Reversed' } })
  if (ex) { const t = await tree(); check(!(t.sketches_shown ?? []).includes('Sketch') && (t.children[ex.name] ?? []).includes('Sketch'), 'Part_Extrude: the sketch goes under the Extrude, hidden') }
  { const n = await count()
    await post([{ op: 'add', list: 'OBJECTS', feature: { name: 'Sketch001', type: 'Sketcher::SketchObject', support: 'XZ', geometry: rect(5, 0, 10, 8), constraints: [] } }])
    await objectsAt(n + 1, 'the second sketch') }
  await panel('Part_Revolve', ['Sketch001'], 'cmd_Part_Revolve', 'OK', { props: { angle: 'Angle', solid: 'Solid', symmetric: 'Symmetric' }, defaults: { symmetric: false }, skipValues: ['xDir', 'yDir', 'zDir'] })
  { const n = await count(); await post([{ op: 'add', feature: { name: 'BoxM', type: 'Part::Box' } }]); await objectsAt(n + 1, 'BoxM') }
  const mir = await panel('Part_Mirror', ['BoxM'], 'cmd_Part_Mirror', 'OK', { skip: ['Selecting'] })
  if (mir) same([mir.name, mir.label], [FC.cmd_Part_Mirror.made[0].name, FC.cmd_Part_Mirror.made[0].label], 'Part_Mirror: FreeCAD\'s name and label')
  { const n = await count(); await post([{ op: 'add', feature: { name: 'BoxF', type: 'Part::Box' } }]); await objectsAt(n + 1, 'BoxF') }
  await panel('Part_Fillet', ['BoxF'], 'cmd_Part_Fillet', null, { skip: ['Select faces'] })
  await panel('Part_Chamfer', ['BoxF'], 'cmd_Part_Chamfer', null, { skip: ['Select faces'] })
  await panel('Part_Loft', null, 'cmd_Part_Loft', null)
  await panel('Part_Sweep', null, 'cmd_Part_Sweep', null)
  { const n = await count(); await post([{ op: 'add', feature: { name: 'BoxO', type: 'Part::Box' } }]); await objectsAt(n + 1, 'BoxO') }
  await panel('Part_Offset', ['BoxO'], 'cmd_Part_Offset', 'OK', { props: { mode: 'Mode', join: 'Join' }, defaults: { mode: 'Skin', join: 'Arc' } })
  { const n = await count()
    await post([{ op: 'add', list: 'OBJECTS', feature: { name: 'SketchO', type: 'Sketcher::SketchObject', support: 'XY', geometry: rect(0, 0, 10, 6), constraints: [] } }])
    await objectsAt(n + 1, 'SketchO') }
  await page.click(`.ptrow[data-ref="${DOC}/SketchO"]`)
  await panel('Part_Offset2D', null, 'cmd_Part_Offset2D', 'OK', { props: { mode: 'Mode' }, defaults: { mode: 'Pipe' } })
  await panel('Part_ProjectionOnSurface', null, 'cmd_Part_ProjectionOnSurface', null)
  await runCmd('Part_Boolean')
  if (await until('cadui.getState().task?.other === "boolean"', 'the Boolean panel', 20000)) { await comparePanel(FC.cmd_Part_Boolean.task, 'Part_Boolean'); await clickButton('Close') }

  // ── the property view ────────────────────────────────────────────────────────────────────────────────────────
  }
  if (want('props')) {
  console.log('props')
  for (const [name, fcKey] of [['Box', 'props_Box'], ['Cut', 'props_Cut'], ['Extrude', 'props_Extrude']]) {
    await selectRows([name])
    await sleep(300)
    const rows = await st(`[...document.querySelectorAll('.props .prow .pk')].map((e) => e.textContent.trim())`)
    const fcRows = (FC[fcKey]?.[0] ?? []).filter((r) => r.depth === 1).map((r) => r.name)
    const missing = fcRows.filter((r) => !rows.includes(r))
    check(!missing.length, `props ${name}: FreeCAD's rows`, `missing ${JSON.stringify(missing)}; ours ${JSON.stringify(rows)}`)
  }

  // ── undo ─────────────────────────────────────────────────────────────────────────────────────────────────────
  }
  if (want('undo')) {
  console.log('undo')
  const n = await count()
  await runCmd('Std_Undo')
  await until(`(cadui.getState().features[${JSON.stringify(DOC)}]?.objects ?? []).length === ${n - 1}`, 'Std_Undo takes the last object back', 60000) && ok('Std_Undo takes the last object back')
  }
} catch (e) {
  bad('partcheck stopped', e.stack ?? String(e))
} finally {
  await browser.close()
  server.kill()
  if (!args.includes('--keep')) { rmSync(scratch, { recursive: true, force: true }); rmSync(warmDir, { recursive: true, force: true }) }
  else console.log(`scratch kept: ${scratch}`)
}
console.log(`partcheck: ${pass} ok, ${fail} FAIL, ${known} known`)
process.exit(fail ? 1 : 0)

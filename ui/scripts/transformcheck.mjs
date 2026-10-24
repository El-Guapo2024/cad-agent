// SPDX-License-Identifier: LGPL-2.1-or-later
// transformcheck: Mirror, Linear Pattern, Polar Pattern, Multi-Transform and the 16 primitives in the page, held to the real
// FreeCAD's (ui/scripts/fctransform.json, written by fctransform.py from FreeCAD 26.3 at 3160daf1e2b6; the menus from
// ui/scripts/fcedit.json), then driven end to end.
//
//   NODE_PATH=<folder with playwright> node ui/scripts/transformcheck.mjs [--fc=ui/scripts/fctransform.json] [--keep] [--verbose]
//
// It starts a scratch workbench of its own (as editcheck.mjs does) and, in Chromium on SwiftShader:
//   setup      the Body FreeCAD's dump has: Sketch (40 x 20) padded 5 mm, Sketch001 (a circle r 3 at (8, 10), 5 mm up) pocketed
//   menus      Part Design > Transformation Features and the two primitive groups: FreeCAD's entries and commands, enabled
//   commands   Mirror, Linear Pattern, Polar Pattern with the Pocket selected: each panel's title, mode radios, originals, its
//              fields, combo items and current item, values, against FreeCAD's; the preview overlay drawn; OK writes FreeCAD's
//              transaction ("Make Mirrored") with the properties FreeCAD's command sets, and the feature is the Tip
//   multi      Multi-Transform: the Transformations list and its context menu, Add Mirror Transformation and Add Linear Pattern
//              with FreeCAD's names and fields, OK
//   whole      Polar Pattern with nothing selected: Transform body, the Origin-only axis list
//   edit       double-click on the Mirrored and the LinearPattern: their panels as FreeCAD shows them, Cancel writes nothing
//   primitives each Additive and Subtractive primitive from its toolbar group: its panel's fields and values, the Attachment
//              panel's modes, OK ("Make additive Box"), FreeCAD's names (Box, Cylinder, …, Box001, …)
//   tree       the Body's rows after all of it, against FreeCAD's
//   props      the property view of the Mirrored, the LinearPattern, the PolarPattern and a Box against FreeCAD's rows
//   undo       Std_Undo takes the last primitive back
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
const FC = JSON.parse(readFileSync(flag('fc', join(HERE, 'fctransform.json')), 'utf8'))
const FCMENU = JSON.parse(readFileSync(join(HERE, 'fcedit.json'), 'utf8'))
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
let pass = 0, fail = 0, known = 0
const ok = (what) => { pass++; if (args.includes('--verbose')) console.log(`  ok    ${what}`) }
const bad = (what, detail = '') => { fail++; console.log(`  FAIL  ${what}${detail ? `: ${detail}` : ''}`) }
const note = (what) => { known++; console.log(`  known ${what}`) }
const check = (cond, what, detail) => (cond ? ok(what) : bad(what, detail))
const same = (a, b, what) => check(JSON.stringify(a) === JSON.stringify(b), what, `\n        FreeCAD ${JSON.stringify(b)}\n        ours    ${JSON.stringify(a)}`)
const clean = (t) => String(t ?? '').replace(/&(.)/g, '$1').trim()

// ── a scratch workbench (editcheck.mjs's) ────────────────────────────────────────────────────────────────────────────
const freePort = (from) => new Promise((res, rej) => {
  const tryPort = (p) => {
    if (p > from + 40) return rej(new Error('no free port'))
    const s = createServer(); s.once('error', () => tryPort(p + 1)); s.once('listening', () => s.close(() => res(p))); s.listen(p, '127.0.0.1')
  }
  tryPort(from)
})
const scratch = mkdtempSync(join(tmpdir(), 'cad-transformcheck-')), warmDir = mkdtempSync('/tmp/ctc')
const ROOT = join(scratch, 'root'); mkdirSync(ROOT)
for (const d of ['runtime', 'macros']) mkdirSync(join(scratch, d))
const python = process.env.CAD_PYTHON || join(REPO, '.venv', 'bin', 'python')
const env = { ...process.env, CAD_WARM_DIR: warmDir, CAD_RUNTIME_DIR: join(scratch, 'runtime'), CAD_MACRO_DIR: join(scratch, 'macros'),
  CAD_PREFS: join(scratch, 'prefs.json'), PYTHONPATH: REPO, CAD_PYTHON: python, CAD_RENDER_BACKEND: 'numpy' }
delete env.CAD_PROJECTS
spawnSync(python, ['-m', 'cad_agent', '--projects', ROOT, 'init', 'tr', '--brief', 'transformcheck'], { env, cwd: REPO })
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
// FreeCAD's panel, as fctransform_dump.py read it: the first task box's widgets, OK/Cancel and the preview box left out
const fcWidgets = (task) => task.flat().filter((w) => !(w.class === 'QPushButton' && ['OK', 'Cancel'].includes(w.text)))
const fcWidget = (task, name) => fcWidgets(task).find((w) => w.name === name)
const fcTexts = (task, cls) => fcWidgets(task).filter((w) => cls.includes(w.class) && w.text).map((w) => clean(w.text))
/** The page's open combo items: open it, read the popup, close it. */
const comboItems = async (sel) => {
  const has = await st(`!!document.querySelector(${JSON.stringify(sel)})`)
  if (!has) return null
  await page.dispatchEvent(sel, 'mousedown')
  await sleep(150)
  const items = await st('[...document.querySelectorAll(".combo-popup [role=option]")].map((e) => e.textContent)')
  await page.keyboard.press('Escape')
  await sleep(100)
  return items
}
const comboCurrent = (sel) => st(`document.querySelector(${JSON.stringify(sel)})?.querySelector('.combo-label')?.textContent ?? null`)
const ourTexts = () => st(`[...document.querySelectorAll('.taskview .tbox')].slice(0, 1).flatMap((b) => [...b.querySelectorAll('.tfield > span:first-child, .tcheck, legend, .tlabel, .pdx-buttons .qbtn')].map((e) => e.textContent.trim()).filter(Boolean))`)
const ourHeads = () => st('[...document.querySelectorAll(".taskview .tbox-head > span:first-of-type")].map((e) => e.textContent)')
const ourList = (qf) => st(`[...(document.querySelector('.taskview [data-qf="${qf}"]')?.querySelectorAll('.pdx-item') ?? [])].map((e) => e.textContent)`)
const radios = () => st(`[...document.querySelectorAll('.taskview input[type=radio]')].map((r) => ({ text: r.parentElement.textContent.trim(), checked: r.checked }))`)
const boxValue = (label) => st(`(() => { const l = [...document.querySelectorAll('.taskview .tfield')].find((x) => x.querySelector(':scope > span')?.textContent === ${JSON.stringify(label)}); return l ? l.querySelector('input')?.value ?? null : null })()`)
const feature = (name) => st(`(() => { const d = cadui.getState().features.Body; const f = d.features.find((x) => x.name === ${JSON.stringify(name)}); return f ? JSON.parse(JSON.stringify(f)) : null })()`)

try {
  await page.goto(`${BASE}/next/#tr`)
  await until('!!window.cadui && cadui.getState().slug === "tr" && !!cadui.getState().scene', 'the project to open')
  await st('cadui.setState({ workbench: "design" })')
  await sleep(300)

  // ── setup: FreeCAD's Body ──────────────────────────────────────────────────────────────────────────────────────────
  console.log('setup')
  await page.click('.tb-btn[data-cmd="PartDesign_Body"]')
  await until('!!cadui.getState().features.Body', 'New Body')
  const rect = [[0, 0, 40, 0], [40, 0, 40, 20], [40, 20, 0, 20], [0, 20, 0, 0]].map(([a, b, c, d]) => ({ type: 'LineSegment', start: [a, b], end: [c, d], construction: false }))
  const circle = [{ type: 'Circle', center: [8, 10], radius: 3, construction: false }]
  const r = await post('/api/tr/features/Body', { ops: [
    { op: 'add', feature: { name: 'Sketch', type: 'Sketcher::SketchObject', support: 'XY', geometry: rect, constraints: [] } },
    { op: 'add', feature: { name: 'Pad', type: 'PartDesign::Pad', profile: 'Sketch', length: 5 } },
    { op: 'add', feature: { name: 'Sketch001', type: 'Sketcher::SketchObject', support: 'XY', attachment_offset: [0, 0, 5], geometry: circle, constraints: [] } },
    { op: 'add', feature: { name: 'Pocket', type: 'PartDesign::Pocket', profile: 'Sketch001', length: 5 } }] })
  check(r.data?.built === true, 'setup: the Body builds', JSON.stringify(r).slice(0, 300))
  await until('cadui.getState().features.Body?.features?.length === 4', 'the Body in the page')
  await st('cadui.setState({ workbench: "design", activeBody: "Body" })')
  await until('cadui.getState().scene?.bodies.some((b) => b.part === "Body")', 'the Body in the scene')

  // ── menus ──────────────────────────────────────────────────────────────────────────────────────────────────────────
  console.log('menus')
  const ours = await st('cadui.pd()')
  const sub = (menu, label) => menu.find((e) => e.text === label || clean(e.text) === label)?.menu
  for (const label of ['Transformation Features', 'Additive Primitive', 'Subtractive Primitive']) {
    const fc = sub(FCMENU.menus['&Part Design'], label).filter((e) => !e.sep)
    const us = sub(ours.partDesign, label).filter((e) => !e.sep)
    same(us.map((e) => [e.text, e.cmd]), fc.map((e) => [clean(e.text), e.name]), `Part Design > ${label}: FreeCAD's entries and commands`)
    check(us.every((e) => e.enabled), `Part Design > ${label}: every entry enabled, as in FreeCAD`)
  }
  const tb = ours.toolbars.find((t) => t.title === 'Part Design Modeling Features').buttons
  const fctb = FCMENU.toolbars.find((t) => t.title === 'Part Design Modeling Features').buttons
  for (const g of ['PartDesign_CompPrimitiveAdditive', 'PartDesign_CompPrimitiveSubtractive']) {
    const u = tb.find((b) => b.cmd === g), f = fctb.find((b) => b.name === g)
    check(!!u && u.enabled, `toolbar ${g}: there and enabled`)
    same(u?.menu?.map((e) => e.cmd), f.menu.map((e) => e.name), `toolbar ${g}: its drop-down, as FreeCAD's`)
  }

  // ── the three transformed features from the toolbar, the Pocket selected ──────────────────────────────────────────
  const KIND = { Mirrored: 'Mirrored', LinearPattern: 'LinearPattern', PolarPattern: 'PolarPattern' }
  for (const kind of Object.keys(KIND)) {
    console.log(kind)
    const fc = FC[kind]
    await st('cadui.setState({ featSel: ["Body/Pocket"], selected: [], subSel: [] })')
    await page.click(`.tb-btn[data-cmd="PartDesign_${kind}"]`)
    await until('cadui.getState().task?.kind === "pdTransform"', `${kind}'s panel`)
    await sleep(500)
    const heads = await ourHeads()
    same(heads, fcTexts(fc.task, ['QSint::ActionLabel']), `${kind}: the panel's boxes`)
    same(await radios(), fcWidgets(fc.task).filter((w) => w.class === 'QRadioButton').map((w) => ({ text: w.text, checked: w.checked })), `${kind}: Transform body / Transform tool shapes`)
    same(await ourList('listWidgetFeatures'), fcWidget(fc.task, 'listWidgetFeatures').items, `${kind}: the originals list`)
    const texts = await ourTexts()
    const want = fcTexts(fc.task, ['QLabel', 'QCheckBox', 'QPushButton', 'QGroupBox']).filter((t) => !['Show final result', 'Show preview overlay'].includes(t))
    const missing = want.filter((t) => !texts.includes(t))
    check(!missing.length, `${kind}: the panel's labels, as FreeCAD's`, `missing ${JSON.stringify(missing)}; ours ${JSON.stringify(texts)}`)
    for (const name of ['comboPlane', 'comboDirection', 'comboMode']) {
      const w = fcWidget(fc.task, name)
      if (!w) continue
      same(await comboItems(`.taskview [data-qf="${name}"]`), w.items, `${kind}: ${name}'s items`)
      same(await comboCurrent(`.taskview [data-qf="${name}"]`), w.current, `${kind}: ${name} shows ${w.current}`)
    }
    for (const [label, name] of [['Length', 'spinExtent'], ['Total Angle', 'spinExtent'], ['Occurrences', 'spinOccurrences']]) {
      const w = fcWidget(fc.task, name)
      const lab = fcWidgets(fc.task).find((x) => x.class === 'QLabel' && x.text === label)
      if (!w || !lab) continue
      same(await boxValue(label), w.text, `${kind}: ${label} starts at FreeCAD's ${w.text}`)
    }
    check(await st('!!cadui.getView()?.helpers?.has?.("pd-preview")'), `${kind}: the preview overlay is drawn`)
    await page.click('.taskview .pd-buttons .qbtn.default')
    await until(`cadui.getState().features.Body.features.some((f) => f.name === "${kind}")`, kind)
    await until(`cadui.getState().undo[0]?.name === "${fc.undo[0]}"`, `the "${fc.undo[0]}" step`)
    check(await st(`cadui.getState().features.Body.tip === "${fc.tip}"`), `${kind}: is the Tip, as in FreeCAD`)
    await until(`cadui.getState().featSel[0] === "Body/${kind}"`, `${kind} selected after OK`, 20000)
    const f = await feature(kind)
    if (!f) continue
    const v = fc.props.values
    if (kind === 'Mirrored') same(f.mirror_plane, ['Sketch001', 'V_Axis'], 'Mirrored: MirrorPlane is the sketch\'s V_Axis, as the command sets it')
    if (kind === 'LinearPattern') {
      same([f.direction, f.direction2, f.length, f.occurrences, f.mode], [['Sketch001', 'H_Axis'], ['Sketch001', 'V_Axis'], parseFloat(v.Length), Number(v.Occurrences), v.Mode],
        'LinearPattern: Direction, Direction2, Length, Occurrences, Mode as the command sets them')
    }
    if (kind === 'PolarPattern') same([f.axis, f.angle, f.occurrences], [['Sketch001', 'N_Axis'], parseFloat(v.Angle), Number(v.Occurrences)], 'PolarPattern: Axis, Angle, Occurrences as the command sets them')
    same([f.originals, f.transform_mode, f.refine], [['Pocket'], v.TransformMode, v.Refine === 'True'], `${kind}: Originals, Transform Mode, Refine`)
  }

  // ── Multi-Transform ────────────────────────────────────────────────────────────────────────────────────────────────
  console.log('MultiTransform')
  {
    const fc = FC.MultiTransform
    await st('cadui.setState({ featSel: ["Body/Pocket"], selected: [], subSel: [] })')
    await page.click('.tb-btn[data-cmd="PartDesign_MultiTransform"]')
    await until('cadui.getState().task?.kind === "pdTransform"', 'the Multi-Transform panel')
    await sleep(400)
    same(await ourHeads(), fcTexts(fc.task, ['QSint::ActionLabel']), 'Multi-Transform: the panel\'s boxes')
    same(await ourList('listTransformFeatures'), fcWidget(fc.task, 'listTransformFeatures').items, 'Multi-Transform: the empty list says "Right-click to add a transformation"')
    await page.click('.taskview [data-qf="listTransformFeatures"]', { button: 'right' })
    await sleep(300)
    const menu = await st('[...document.querySelectorAll(".ctx > *")].filter((e) => !e.classList.contains("mb-sep")).map((e) => ({ text: e.textContent.trim(), enabled: !e.classList.contains("dis") && !e.getAttribute("aria-disabled") }))')
    same(menu.map((e) => e.text), fc.context_menu.map((e) => e.text), 'Multi-Transform: the list\'s context menu, entry by entry')
    if (fc.context_menu.find((e) => e.text === 'Add Scale Transformation')?.enabled) note('Add Scale Transformation is greyed: PartDesign::Scaled is not in feature_transform.py')
    await page.click('.ctx .mb-item:has-text("Add Mirror Transformation")')
    await sleep(400)
    same(await ourList('listTransformFeatures'), fcWidget(fc.task_mirror, 'listTransformFeatures').items, 'Multi-Transform: Add Mirror Transformation adds "Mirror"')
    same(await comboItems('.taskview .pdx-sub [data-qf="comboPlane"]'), fcWidget(fc.task_mirror, 'comboPlane').items, 'Multi-Transform: the Mirror\'s plane list')
    same(await comboCurrent('.taskview .pdx-sub [data-qf="comboPlane"]'), fcWidget(fc.task_mirror, 'comboPlane').current, 'Multi-Transform: the Mirror on the sketch\'s V axis')
    await page.click('.taskview .pdx-sub .qbtn:text-is("OK")')
    await page.click('.taskview [data-qf="listTransformFeatures"]', { button: 'right' })
    await page.click('.ctx .mb-item:has-text("Add Linear Pattern")')
    await sleep(400)
    same(await ourList('listTransformFeatures'), fcWidget(fc.task_linear, 'listTransformFeatures').items, 'Multi-Transform: Add Linear Pattern adds "Linear_Pattern"')
    same(await comboCurrent('.taskview .pdx-sub [data-qf="comboDirection"]'), fcWidget(fc.task_linear, 'comboDirection').current, 'Multi-Transform: the Linear_Pattern along the sketch\'s H axis')
    same(await boxValue('Length'), fcWidget(fc.task_linear, 'spinExtent').text, 'Multi-Transform: the Linear_Pattern\'s Length')
    await page.click('.taskview .pdx-sub .qbtn:text-is("OK")')
    await page.click('.taskview .pd-buttons .qbtn.default')
    await until('cadui.getState().features.Body.features.some((f) => f.name === "MultiTransform")', 'MultiTransform')
    await until('cadui.getState().featSel[0] === "Body/MultiTransform"', 'MultiTransform selected after OK', 20000)
    await until(`cadui.getState().undo[0]?.name === "${fc.undo_after[0]}"`, `the "${fc.undo_after[0]}" step`)
    const mt = await feature('MultiTransform')
    same(mt.transformations.map((t) => t.name), fc.transformations2, 'Multi-Transform: its transformations, FreeCAD\'s names')
    const lp = mt.transformations[1], fp = fc.sub_props.Linear_Pattern.values
    same([lp.length, lp.occurrences], [parseFloat(fp.Length), Number(fp.Occurrences)], 'Multi-Transform: the Linear_Pattern\'s Length and Occurrences, as FreeCAD\'s panel sets them')
  }

  // ── Transform body: nothing selected ───────────────────────────────────────────────────────────────────────────────
  console.log('whole shape')
  {
    const fc = FC.whole_shape
    await st('cadui.setState({ featSel: [], selected: [], subSel: [] })')
    await page.click('.tb-btn[data-cmd="PartDesign_PolarPattern"]')
    await until('cadui.getState().task?.kind === "pdTransform"', 'the Polar Pattern panel')
    await sleep(300)
    same(await radios(), fcWidgets(fc.task).filter((w) => w.class === 'QRadioButton').map((w) => ({ text: w.text, checked: w.checked })), 'Transform body: checked, as FreeCAD\'s command sets it')
    check(await st('[...document.querySelectorAll(".taskview .pdx-buttons .qbtn")].every((b) => b.disabled)'), 'Transform body: Add Feature and Remove Feature greyed')
    same(await comboItems('.taskview [data-qf="comboDirection"]'), fcWidget(fc.task, 'comboDirection').items, 'Transform body: the axis list has the Origin\'s axes only')
    same(await comboCurrent('.taskview [data-qf="comboDirection"]'), fcWidget(fc.task, 'comboDirection').current, 'Transform body: about the Z axis')
    await page.click('.taskview .pd-buttons .qbtn.default')
    await until('cadui.getState().features.Body.features.some((f) => f.name === "PolarPattern001")', 'PolarPattern001')
    await until('cadui.getState().featSel[0] === "Body/PolarPattern001"', 'PolarPattern001 selected after OK', 20000)
    same((await feature('PolarPattern001'))?.transform_mode, 'Whole shape', 'Transform body: PolarPattern001\'s TransformMode is "Whole shape"')
  }

  // ── double-click: the panels again ─────────────────────────────────────────────────────────────────────────────────
  console.log('edit')
  for (const name of ['Mirrored', 'LinearPattern', 'MultiTransform']) {
    const fc = FC[`edit_${name}`]
    await st('cadui.showPanel("model")')
    await page.dblclick(`.trow[data-ref="Body/${name}"] .tname`)
    await until('cadui.getState().task?.kind === "pdTransform" && cadui.getState().task?.edit', `${name}'s panel`)
    await sleep(300)
    same(await ourHeads(), fcTexts(fc.task, ['QSint::ActionLabel']), `double-click on ${name}: its panel`)
    same(await ourList('listWidgetFeatures'), fcWidget(fc.task, 'listWidgetFeatures').items, `double-click on ${name}: its originals`)
    for (const n of ['comboPlane', 'comboDirection']) {
      const w = fcWidget(fc.task, n)
      if (w) same(await comboCurrent(`.taskview [data-qf="${n}"]`), w.current, `double-click on ${name}: ${n} shows ${w.current}`)
    }
    if (name === 'MultiTransform') same(await ourList('listTransformFeatures'), fcWidget(fc.task, 'listTransformFeatures').items, 'double-click on MultiTransform: its transformations')
    const steps = await st('cadui.getState().undo.length')
    await page.click('.taskview .pd-buttons .qbtn:text-is("Cancel")')
    await sleep(300)
    check(await st(`cadui.getState().undo.length === ${steps} && !cadui.getState().task`), `double-click on ${name}: Cancel writes nothing`)
  }

  // ── the primitives, from their toolbar groups ──────────────────────────────────────────────────────────────────────
  console.log('primitives')
  for (const side of ['Additive', 'Subtractive']) {
    for (const shape of ['Box', 'Cylinder', 'Sphere', 'Cone', 'Ellipsoid', 'Torus', 'Prism', 'Wedge']) {
      const fc = FC[`prim_${side}${shape}`]
      await st('cadui.setState({ featSel: [], selected: [], subSel: [] })')
      await page.click(`.tb-btn[data-cmd="PartDesign_CompPrimitive${side}"]`)
      await page.click(`.ctx .mb-item:has-text("${side} ${shape}")`)
      await until('cadui.getState().task?.kind === "pdPrimitive"', `${side} ${shape}'s panel`)
      await sleep(250)
      same(await ourHeads(), fcTexts(fc.task, ['QSint::ActionLabel']), `${side} ${shape}: the panel's boxes`)
      const first = fcWidgets(fc.task).slice(0, fcWidgets(fc.task).findIndex((w) => w.class === 'QSint::ActionLabel' && w.text === 'Attachment'))
      const fcLabels = first.filter((w) => w.class === 'QLabel').map((w) => w.text)
      const fcValues = first.filter((w) => /QuantitySpinBox|QSpinBox/.test(w.class)).map((w) => w.text)
      const usLabels = await st(`[...document.querySelectorAll('.taskview .tbox')][0].querySelectorAll('.tfield > span:first-child').length ? [...[...document.querySelectorAll('.taskview .tbox')][0].querySelectorAll('.tfield > span:first-child')].map((e) => e.textContent).filter(Boolean) : []`)
      const usValues = await st(`[...[...document.querySelectorAll('.taskview .tbox')][0].querySelectorAll('.tfield input')].map((e) => e.value)`)
      same(usLabels, fcLabels, `${side} ${shape}: the fields' labels`)
      same(usValues, fcValues, `${side} ${shape}: FreeCAD's defaults`)
      if (side === 'Subtractive') same(await comboCurrent('.taskview [data-qf="comboOperation"]'), fcWidget(fc.task, 'comboOperation').current, `${side} ${shape}: Operation`)
      const modes = await st('[...document.querySelectorAll(".taskview .pd-mode")].map((e) => e.textContent)')
      same(modes, fcWidget(fc.task, 'listOfModes').items, `${side} ${shape}: the attachment modes`)
      check(await st('document.querySelector(".taskview .pd-attach-msg")?.textContent === "Not attached"'), `${side} ${shape}: "Not attached"`)
      await page.click('.taskview .pd-buttons .qbtn.default')
      await until(`cadui.getState().features.Body.features.some((f) => f.name === "${fc.new[0]}")`, `${fc.new[0]}`, 120000)
      await until(`cadui.getState().undo[0]?.name === "${fc.undo[0]}"`, `the "${fc.undo[0]}" step`, 60000)
      await until(`cadui.getState().featSel[0] === "Body/${fc.new[0]}"`, `${fc.new[0]} selected`, 20000)
    }
  }

  // ── the tree, against FreeCAD's ────────────────────────────────────────────────────────────────────────────────────
  console.log('tree')
  await st('cadui.showPanel("model")')
  for (const ref of ['Body/Origin', 'Body/Pad', 'Body/Pocket', 'Body/MultiTransform']) {
    const open = await st(`document.querySelector('.trow[data-ref="${ref}"] .twisty.open')`)
    if (!open) await page.click(`.trow[data-ref="${ref}"] .twisty`)
  }
  await sleep(300)
  const us = await st(`[...document.querySelectorAll('.tree .trow')].map((r) => ({ text: r.querySelector('.tname')?.textContent, hidden: r.classList.contains('hid'),
    depth: r.classList.contains('doc') ? 0 : r.dataset.ref ? (parseFloat(r.querySelector('.pdindent')?.style.width ?? '6') - 6) / 12 + 1 : 1 }))`)
  const fct = FC.tree.slice(1).map((x) => `${'  '.repeat(x.depth - 1)}${x.text}`)
  const ust = us.slice(1).map((x) => `${'  '.repeat(x.depth - 1)}${x.text}`)
  same(ust, fct, 'the Body\'s rows after all of it, as FreeCAD\'s')
  const icons = await st('[...document.querySelectorAll(".tree .trow")].map((r) => r.querySelector(".ticon img")?.getAttribute("src") ?? "")')
  check(icons.some((s) => s.includes('PartDesign_Mirrored')) && icons.some((s) => s.includes('PartDesign_SubtractiveWedge')) && icons.some((s) => s.includes('PartDesign_MultiTransform')),
    'the tree shows the features\' own icons (ViewProviderTransformed, ViewProviderPrimitive)')

  // ── the property view ──────────────────────────────────────────────────────────────────────────────────────────────
  console.log('props')
  for (const [name, fcName] of [['Mirrored', 'props_Mirrored'], ['LinearPattern', 'props_LinearPattern'], ['PolarPattern', 'props_PolarPattern'], ['MultiTransform', 'props_MultiTransform'], ['Box', 'props_Box'], ['Box001', 'props_Box001']]) {
    await page.click(`.trow[data-ref="Body/${name}"] .tname`)
    await sleep(400)
    const rows = await st(`[...document.querySelectorAll('.props .pgroup, .props .prow')].map((e) => e.classList.contains('pgroup') ? { group: e.textContent } : { name: e.querySelector('.pk')?.textContent })`)
    // FreeCAD's dump lists groups left from the other objects with no rows; keep its groups that have rows
    const fcRows = FC[fcName][0]
    const fcGroups = []
    for (const x of fcRows) { if (x.depth === 0) fcGroups.push({ group: x.name, rows: [] }); else fcGroups[fcGroups.length - 1].rows.push(x.name) }
    const want = fcGroups.filter((g) => g.rows.length)
    const got = []
    for (const x of rows) { if (x.group !== undefined) got.push({ group: x.group, rows: [] }); else if (got.length) got[got.length - 1].rows.push(x.name) }
    const gotHere = got.filter((g) => g.rows.length)
    const extra = name.startsWith('Box') ? 'Placement' : null
    const gotNoExtra = gotHere.map((g) => ({ ...g, rows: g.rows.filter((r) => r !== extra) }))
    same(gotNoExtra.map((g) => [g.group, g.rows]), want.map((g) => [g.group, g.rows]), `${name}: the property view's groups and rows, as FreeCAD's`)
    if (extra) note(`${name}: Placement is shown in Base (FreeCAD hides it; with no Attacher here it is how a primitive is placed)`)
  }

  // ── undo ───────────────────────────────────────────────────────────────────────────────────────────────────────────
  console.log('undo')
  await page.click('.tb-btn[data-cmd="Std_Undo"]')
  await until('!cadui.getState().features.Body.features.some((f) => f.name === "Wedge001")', 'Undo of the last primitive')
  ok('Undo takes the last primitive (Wedge001) back')
} catch (e) {
  bad('transformcheck stopped', e.stack ?? String(e))
} finally {
  await browser.close()
  server.kill('SIGTERM')
  spawnSync(python, ['-P', '-m', 'cad_agent.warm', 'warm', 'stop'], { env, cwd: REPO, timeout: 60000 })
  if (!args.includes('--keep')) for (const d of [scratch, warmDir]) rmSync(d, { recursive: true, force: true })
}
console.log(`transformcheck: ${pass} ok, ${fail} failing, ${known} known differences`)
process.exit(fail ? 1 : 0)

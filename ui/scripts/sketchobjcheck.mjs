// SPDX-License-Identifier: LGPL-2.1-or-later
// sketchobjcheck: the Sketcher's commands on sketch objects in the page (Mirror, Merge, Reorient, Attach, Validate
// Sketch), held to the real FreeCAD's (ui/scripts/fcsketchobj.json, written by fcsketchobj.py from FreeCAD 26.3 at
// 3160daf1e2b6's GUI).
//
//   NODE_PATH=<folder with playwright> node ui/scripts/sketchobjcheck.mjs [--fc=ui/scripts/fcsketchobj.json] [--verbose]
//
// It starts a scratch workbench of its own (a temporary projects folder, CAD_* pointed at scratch paths, as
// attachcheck.mjs does) holding the document fcsketchobj_dump.py makes (a Body with the 40 x 20 x 5 plate, Sketch001
// on the XZ plane, Sketch002 on the Pad's top face with external geometry, Sketch003 flipped with an arc and Sketch004
// with that arc, a reversed one, as external geometry, each with FreeCAD's solved geometry), and
// in Chromium on SwiftShader does what that script did in FreeCAD: selects rows of the tree (or the Pad's face), runs
// the command from the Sketcher toolbar, answers its dialogs, and compares the dialogs' contents, what was made or
// changed (geometry, constraints, placement, attachment), the step's name and the commands' enabled state; each case
// is undone after it. A difference prints as FAIL, the deliberate ones (ui/PARITY.md) as `known`. Exit 1 on a FAIL.
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
const FC = JSON.parse(readFileSync(flag('fc', join(HERE, 'fcsketchobj.json')), 'utf8'))
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
let pass = 0, fail = 0, known = 0
const ok = (what) => { pass++; if (args.includes('--verbose')) console.log(`  ok    ${what}`) }
const bad = (what, detail = '') => { fail++; console.log(`  FAIL  ${what}${detail ? `: ${detail}` : ''}`) }
const note = (what) => { known++; console.log(`  known ${what}`) }
const check = (cond, what, detail) => (cond ? ok(what) : bad(what, detail))
const same = (a, b, what) => check(JSON.stringify(a) === JSON.stringify(b), what, `\n        FreeCAD ${JSON.stringify(b)}\n        ours    ${JSON.stringify(a)}`)

// ── a scratch workbench holding FreeCAD's document ──────────────────────────────────────────────────────────────
const freePort = (from) => new Promise((res, rej) => {
  const tryPort = (p) => {
    if (p > from + 40) return rej(new Error('no free port'))
    const s = createServer(); s.once('error', () => tryPort(p + 1)); s.once('listening', () => s.close(() => res(p))); s.listen(p, '127.0.0.1')
  }
  tryPort(from)
})
const scratch = mkdtempSync(join(tmpdir(), 'cad-sketchobjcheck-')), warmDir = mkdtempSync('/tmp/cso')
const ROOT = join(scratch, 'root'); mkdirSync(ROOT)
for (const d of ['runtime', 'macros']) mkdirSync(join(scratch, d))
const python = process.env.CAD_PYTHON || join(REPO, '.venv', 'bin', 'python')
const env = { ...process.env, CAD_WARM_DIR: warmDir, CAD_RUNTIME_DIR: join(scratch, 'runtime'), CAD_MACRO_DIR: join(scratch, 'macros'),
  CAD_PREFS: join(scratch, 'prefs.json'), PYTHONPATH: REPO, CAD_PYTHON: python, CAD_RENDER_BACKEND: 'numpy' }
delete env.CAD_PROJECTS
const cad = (...argv) => spawnSync(python, ['-m', 'cad_agent', '--projects', ROOT, ...argv], { env, cwd: REPO, encoding: 'utf8' })

/** FreeCAD's constraint fields as a part file's constraint (Sketcher.Constraint's argument forms). */
function argsOf(c) {
  const [f, fp, s, sp] = c.elements
  const t = c.type
  const args = t === 'Coincident' ? [f, fp, s, sp] : ['Horizontal', 'Vertical', 'Radius', 'Diameter', 'Block'].includes(t) && s === -2000 ? [f]
    : t === 'PointOnObject' ? [f, fp, s] : t === 'Distance' && s === -2000 ? [f] : ['Distance', 'DistanceX', 'DistanceY'].includes(t) && sp === 0 && fp === 0 ? [f, s]
      : ['DistanceX', 'DistanceY'].includes(t) && s === -2000 ? [f, fp] : [f, fp, s, sp]
  return { type: t, args, ...(c.value !== undefined ? { value: c.value } : {}), driving: c.driving, name: c.name }
}
/** A part file's constraint as FreeCAD's fields (ConstraintPyImp's forms, for the types these sketches hold). */
function fieldsOf(c) {
  const a = c.args, U = -2000
  let el
  if (c.type === 'Coincident' || a.length === 4) el = [a[0], a[1], a[2], a[3], U, 0]
  else if (a.length === 1) el = [a[0], 0, U, 0, U, 0]
  else if (a.length === 2) el = ['DistanceX', 'DistanceY'].includes(c.type) ? [a[0], a[1], U, 0, U, 0] : [a[0], 0, a[1], 0, U, 0]
  else el = [a[0], a[1], a[2], 0, U, 0]
  return { type: c.type, elements: el, ...(c.value !== undefined ? { value: c.value } : {}), name: c.name ?? '', driving: c.driving !== false }
}
const geoOf = (g) => ({ ...g, construction: !!g.construction })
const setup = FC.setup
const sketchFeature = (name, extra) => ({ name, type: 'Sketcher::SketchObject', ...extra, geometry: setup[name].geometry.map(geoOf),
  constraints: setup[name].constraints.map(argsOf) })
cad('init', 'sko', '--brief', 'sketchobjcheck')
cad('feature', 'new', 'sko', 'Body')
const r1 = cad('feature', 'apply', 'sko', 'Body', '--ops', JSON.stringify([
  { op: 'add', feature: sketchFeature('Sketch', { support: 'XY' }) },
  { op: 'add', feature: { name: 'Pad', type: 'PartDesign::Pad', profile: 'Sketch', length: 5 } },
  { op: 'add', feature: sketchFeature('Sketch001', { support: 'XZ', attachment_offset: [0, 0, 3] }) },
  { op: 'add', feature: sketchFeature('Sketch002', { attachment_support: [['Pad', 'Face6']], map_mode: 'FlatFace', external_geometry: [['Pad', FC.top_edge]] }) },
  { op: 'add', feature: sketchFeature('Sketch003', { attachment_support: [['XY_Plane', '']], map_mode: 'FlatFace', map_reversed: true }) },
  { op: 'add', feature: sketchFeature('Sketch004', { support: 'XY', attachment_offset: [0, 0, 7], external_geometry: [['Sketch003', 'Edge1']] }) }]))
if (r1.status > 2) { console.log(r1.stdout, r1.stderr); process.exit(1) }
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
page.on('pageerror', (e) => bad('page error', process.env.DEBUG ? e.stack : e.message))
if (process.env.DEBUG) page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') console.log('  console', m.type(), m.text().slice(0, 600)) })
const st = (expr) => page.evaluate(expr)
const until = async (expr, what, ms = 60000, quiet = false) => {
  const t0 = Date.now()
  while (Date.now() - t0 < ms) { if (await st(expr)) return true; await sleep(200) }
  if (!quiet) bad(`timed out waiting: ${what}`)
  return false
}
const features = () => st('cadui.getState().features.Body.features')
const feature = async (name) => (await features()).find((f) => f.name === name)
const undoName = () => st('cadui.getState().undo?.[0]?.name')

// ── selecting, the toolbar, the dialogs ─────────────────────────────────────────────────────────────────────────
/** The tree's rows selected, in this order (as a click and Ctrl+clicks leave State.featSel; Sketch sits under Pad). */
async function selectRows(names) {
  await st(`cadui.setState({ featSel: ${JSON.stringify(names.map((n) => `Body/${n}`))}, selected: [], subSel: [] })`)
  await sleep(300)
}
async function selectFace(sub) {
  await st('cadui.setState({ featSel: [], selected: [], subSel: [] })')
  const b = await st('cadui.getState().scene?.bodies.find((b) => b.part === "Body")?.name')
  await st(`cadui.select(${JSON.stringify(b)}, false, ${JSON.stringify(sub)})`)
  await sleep(200)
}
const COMMANDS = ['Sketcher_MapSketch', 'Sketcher_ReorientSketch', 'Sketcher_ValidateSketch', 'Sketcher_MergeSketches', 'Sketcher_MirrorSketch']
const enabledNow = () => st(`Object.fromEntries(${JSON.stringify(COMMANDS)}.map((c) => [c, !document.querySelector('[data-toolbar="Sketcher"] [data-cmd="' + c + '"]')?.disabled]))`)
let B0 = null
const runCmd = async (cmd) => { B0 = await top(); await page.click(`[data-toolbar="Sketcher"] [data-cmd="${cmd}"]`); await sleep(300) }
/** The open dialog as fcsketchobj_dump.py reads FreeCAD's: title, group title, label, radios, check boxes, combo. */
const dialog = () => st(`(() => {
  const d = document.querySelector('.msgbox[role="dialog"], .msgbox[role="alertdialog"]')
  if (!d) return null
  return { title: d.querySelector('.msgbox-title')?.textContent ?? '', group: d.querySelector('legend')?.textContent ?? null,
    label: d.querySelector('.qlabel')?.textContent ?? d.querySelector('.msgbox-text')?.textContent ?? null,
    radios: [...d.querySelectorAll('input[type=radio]')].map((r) => [r.parentElement.textContent.trim(), r.checked]),
    checks: [...d.querySelectorAll('input[type=checkbox]')].map((r) => [r.parentElement.textContent.trim(), r.checked]),
    items: [...d.querySelectorAll('select option')].map((o) => o.textContent), current: d.querySelector('select')?.selectedOptions[0]?.textContent ?? null,
    buttons: [...d.querySelectorAll('.msgbox-buttons button')].map((b) => b.textContent), preview: d.querySelector('[data-preview]')?.dataset.preview ?? null }
})()`)
const fcDialog = (d) => {
  const w = d.widgets
  return { title: d.title, group: w.find((x) => x.class === 'QGroupBox')?.title ?? null,
    label: d.class === 'QMessageBox' ? d.text : w.find((x) => x.class === 'QLabel' && x.text && x.text !== 'Offset')?.text ?? null,
    radios: w.filter((x) => x.class === 'QRadioButton').map((x) => [x.text, x.checked]), checks: w.filter((x) => x.class === 'QCheckBox').map((x) => [x.text, x.checked]),
    items: w.find((x) => x.class === 'QComboBox')?.items ?? [], current: w.find((x) => x.class === 'QComboBox')?.current ?? null,
    buttons: d.buttons ?? w.filter((x) => x.class === 'QPushButton').map((x) => x.text.replace('&', '')) }
}
async function compareDialog(fc, where) {
  if (!await until('!!document.querySelector(".msgbox")', `${where}: the dialog`, 10000)) return
  const got = await dialog(), want = fcDialog(fc)
  for (const k of ['title', 'group', 'label', 'radios', 'checks', 'items', 'current', 'buttons']) same(got[k], want[k], `${where}: ${k}`)
}
const clickDialog = async (text) => { await page.click(`.msgbox-buttons button:text-is("${text}")`); await sleep(300) }
const pickRadio = async (text) => { await page.click(`.msgbox label.tcheck:has-text("${text}") input`); await sleep(100) }
const pickItem = async (text) => { await page.selectOption('.msgbox select', { label: text }); await sleep(100) }
const steps = () => st('cadui.getState().undo.length')
const top = () => st('cadui.getState().undo[0]?.id ?? null')
/** Until the command's step is in the journal (its POST answered, the list read back). */
const settle = async (id, name) => { await until(`(cadui.getState().undo[0]?.id ?? null) !== ${JSON.stringify(id)}` + (name ? ` && cadui.getState().undo[0]?.name === ${JSON.stringify(name)}` : ''), 'the step', 30000, true); await sleep(800) }
/** Edit > Undo until the journal is back to n steps (each case starts from the same document). */
async function restore(id) {
  for (let i = 0; i < 12 && (await top()) !== id; i++) {
    const k = await top()
    await st('cadui.getCommand("Std_Undo").run([])')
    await until(`cadui.getState().undo[0]?.id !== ${JSON.stringify(k)}`, 'an undo', 20000, true)
    await sleep(600)
  }
}

// ── what was made or changed ────────────────────────────────────────────────────────────────────────────────────
const close = (a, b, tol) => Math.abs(a - b) <= tol * Math.max(1, Math.abs(b))
function sameGeometry(ours, theirs, tol = 1e-7) {
  if (ours.length !== theirs.length) return `${ours.length} geometries, FreeCAD ${theirs.length}`
  for (const [i, g] of ours.entries()) {
    const t = theirs[i]
    if (g.type !== t.type || !!g.construction !== !!t.construction) return `geometry ${i}: ${g.type}${g.construction ? ' (construction)' : ''}, FreeCAD ${t.type}${t.construction ? ' (construction)' : ''}`
    for (const k of Object.keys(t)) {
      if (k === 'type' || k === 'construction') continue
      const a = [g[k]].flat(), b = [t[k]].flat()
      if (a.length !== b.length || a.some((x, j) => !close(x, b[j], tol))) return `geometry ${i} ${k}: ${JSON.stringify(g[k])}, FreeCAD ${JSON.stringify(t[k])}`
    }
  }
  return ''
}
function sameConstraints(ours, theirs) {
  const a = ours.map(fieldsOf), b = theirs.map((c) => ({ type: c.type, elements: c.elements, ...(c.value !== undefined ? { value: c.value } : {}), name: c.name, driving: c.driving }))
  if (a.length !== b.length) return `${JSON.stringify(a.map((c) => c.type))}, FreeCAD ${JSON.stringify(b.map((c) => c.type))}`
  for (const [i, c] of a.entries()) {
    const t = b[i]
    if (c.type !== t.type || JSON.stringify(c.elements) !== JSON.stringify(t.elements) || c.name !== t.name || c.driving !== t.driving
      || (t.value !== undefined && !close(Number(c.value), t.value, 1e-9))) return `constraint ${i}: ${JSON.stringify(c)}, FreeCAD ${JSON.stringify(t)}`
  }
  return ''
}
const samePlacement = (pl, want, tol = 1e-7) => pl && pl.position.every((x, i) => Math.abs(x - want.position[i]) <= tol)
  && Math.abs(Math.abs(pl.rotation.reduce((s, x, i) => s + x * want.rotation[i], 0)) - 1) < tol
async function compareSketch(name, want, where) {
  if (!await until(`cadui.getState().features.Body.features.some((f) => f.name === ${JSON.stringify(name)} && f.attached)`, `${where}: ${name}`, 30000)) return
  const f = await feature(name)
  if (process.env.DEBUG) console.log(where, await st(`JSON.stringify([cadui.getState().messages.slice(-4).map((m) => m.text), cadui.getState().undo.slice(0, 4).map((u) => u.name), cadui.getState().features.Body.features.find((f) => f.name === "Sketch001")?.attachment_support])`))
  check(!sameGeometry(f.geometry, want.geometry), `${where}: ${name}'s geometry`, sameGeometry(f.geometry, want.geometry))
  check(!sameConstraints(f.constraints, want.constraints), `${where}: ${name}'s constraints`, sameConstraints(f.constraints, want.constraints))
  check(samePlacement(f.attached.placement, want.placement), `${where}: ${name}'s Placement`, `${JSON.stringify(f.attached.placement?.position)} ${JSON.stringify(f.attached.placement?.rotation)} vs ${JSON.stringify(want.placement)}`)
  const sup = (f.attachment_support ?? []).map(([o, s]) => [o, [s]])
  same(sup, want.support.map(([o, s]) => [o, s]), `${where}: ${name}'s AttachmentSupport`)
  if ((f.map_mode ?? 'Deactivated') === want.map_mode) ok(`${where}: ${name}'s MapMode`)
  else if (want.map_mode === 'FlatFace' && !want.support.length && f.map_mode === 'Deactivated') note(`${where}: ${name}'s MapMode is Deactivated where FreeCAD keeps FlatFace with no support (it places nothing either way)`)
  else bad(`${where}: ${name}'s MapMode`, `${f.map_mode} vs ${want.map_mode}`)
  if (want.external?.length) same((f.external_geometry ?? []).map(([o, s]) => [o, s]), want.external, `${where}: ${name}'s external geometry`)
}
async function compareStep(fc, where) {
  if (!fc.undo.length) return
  check(await until(`cadui.getState().undo?.[0]?.name === ${JSON.stringify(fc.undo[0])}`, `${where}: the step`, 20000, true),
    `${where}: the step is FreeCAD's "${fc.undo[0]}"`, await undoName())
}

try {
  await page.goto(`${BASE}/next/#sko`)
  await until('!!window.cadui && cadui.getState().slug === "sko" && !!cadui.getState().scene?.bodies.some((b) => b.part === "Body")', 'the plate')
  await st('cadui.setState({ workbench: "design", activeBody: "Body" })')
  await until("!!cadui.getView()?.renderer || !!document.querySelector(\"canvas\")", "the 3D view", 30000, true)
  await sleep(3000)
  await st('cadui.setState({ workbench: "sketcher" })')
  await until('cadui.getState().features.Body?.features.length === 6', 'the Body')
  await sleep(800)
  const N = (await features()).length, S0 = await top()

  console.log('enabled')
  for (const [label, sel] of [['nothing', []], ['one sketch', ['Sketch001']], ['two sketches', ['Sketch', 'Sketch001']], ['the pad', ['Pad']]]) {
    await selectRows(sel)
    const got = await enabledNow(), want = Object.fromEntries(COMMANDS.map((c) => [c, FC.enabled[label][c]]))
    same(got, want, `enabled with ${label} selected`)
  }
  await selectFace('Face6')
  same(await enabledNow(), Object.fromEntries(COMMANDS.map((c) => [c, FC.enabled['a face'][c]])), 'enabled with a face selected')

  console.log('mirror')
  for (const [key, sel, choice] of [['mirror_x', ['Sketch001'], 'X-axis'], ['mirror_y_two', ['Sketch', 'Sketch001'], 'Y-axis'], ['mirror_origin', ['Sketch002'], 'Origin'],
    ['mirror_external', ['Sketch002'], 'Y-axis']]) {
    const fc = FC[key]
    await selectRows(sel)
    await runCmd('Sketcher_MirrorSketch')
    await compareDialog(fc.dialogs[0], key)
    await pickRadio(choice)
    await clickDialog('OK')
    await settle(B0, fc.undo[0])
    for (const m of fc.made) {
      await compareSketch(m.name, m, key)
      if (m.body === null) note(`${key}: ${m.name} goes into the Body; FreeCAD makes it at the document's top level (a part file is a Body)`)
    }
    await compareStep(fc, key)
    await restore(S0)
  }
  await selectRows(['Sketch001'])
  await runCmd('Sketcher_MirrorSketch')
  await compareDialog(FC.mirror_cancel.dialogs[0], 'mirror_cancel')
  await clickDialog('Cancel')
  check((await features()).length === N, 'mirror_cancel: Cancel makes nothing')

  console.log('merge')
  for (const [key, sel] of [['merge_two', ['Sketch001', 'Sketch']], ['merge_external', ['Sketch002', 'Sketch001']]]) {
    const fc = FC[key]
    await selectRows(sel)
    await runCmd('Sketcher_MergeSketches')
    await settle(B0, fc.undo[0])
    for (const m of fc.made) {
      await compareSketch(m.name, m, key)
      const names = (await features()).map((f) => f.name)
      check(names.indexOf(m.name) === m.index, `${key}: ${m.name} is the Body's object ${m.index}`, names.indexOf(m.name))
    }
    await compareStep(fc, key)
    await restore(S0)
  }

  console.log('reorient')
  {
    const fc = FC.reorient_no
    await selectRows(['Sketch001'])
    await runCmd('Sketcher_ReorientSketch')
    await compareDialog(FC.reorient_yes.dialogs[0], 'reorient: the question')
    await clickDialog('No')
    check(!(await dialog()), 'reorient_no: No ends it')
    void fc
  }
  for (const [key, sketch, plane, reverse, offset] of [['reorient_yes', 'Sketch001', 'YZ-plane', true, 12.5], ['reorient_xz', 'Sketch002', 'XZ-plane', false, -4]]) {
    const fc = FC[key]
    await selectRows([sketch])
    await runCmd('Sketcher_ReorientSketch')
    await until('!!document.querySelector(".msgbox")', `${key}: the question`, 10000)
    await clickDialog('Yes')
    await compareDialog(fc.dialogs[1], key)
    await pickRadio(plane)
    if (reverse) { await page.click('.msgbox label.tcheck:has-text("Reverse direction") input'); await sleep(100) }
    const pre = fc.dialogs[1].preview_after ? { XY: ['view-top', 'view-bottom'], XZ: ['view-front', 'view-rear'], YZ: ['view-right', 'view-left'] }[plane.slice(0, 2)][reverse ? 1 : 0] : null
    if (pre) same((await dialog()).preview, pre, `${key}: the preview shows ${pre}`)
    await page.fill('.msgbox .hbox.fill input', `${offset} mm`)
    await page.press('.msgbox .hbox.fill input', 'Tab')
    await clickDialog('OK')
    await settle(B0, fc.undo[0])
    for (const [n, m] of Object.entries(fc.changed)) await compareSketch(n, m, key)
    await compareStep(fc, key)
    check(await until('cadui.getState().workbench === "sketcher" && !!document.querySelector(".sketch-task")', `${key}: opened`, 30000, true) === !!fc.in_edit,
      `${key}: the sketch opens in edit (setEdit), as in FreeCAD`)
    await st('document.querySelector(".sketch-task .qbtn:not(.default)")?.click()')
    await sleep(1500)
    await restore(S0)
  }

  {
    const fc = FC.reorient_cancel
    await selectRows(['Sketch002'])
    await runCmd('Sketcher_ReorientSketch')
    await until('!!document.querySelector(".msgbox")', 'reorient_cancel: the question', 10000)
    await clickDialog('Yes')
    await until('!!document.querySelector(".msgbox[data-dialog]")', 'reorient_cancel: the orientation', 10000)
    await clickDialog('Cancel')
    await settle(B0, 'Detach sketch')
    for (const [n, m] of Object.entries(fc.changed)) await compareSketch(n, m, 'reorient_cancel')
    if (!fc.undo.length) note('reorient_cancel: FreeCAD clears AttachmentSupport before the dialog, outside any transaction (undo does not bring it back); here it is the step "Detach sketch"')
    await restore(S0)
  }

  console.log('map')
  {
    const fc = FC.map_face
    await selectFace('Face6')
    await runCmd('Sketcher_MapSketch')
    await compareDialog(fc.dialogs[0], 'map_face: the sketches')
    await pickItem('Sketch001')
    await clickDialog('OK')
    await compareDialog(fc.dialogs[1], 'map_face: the method')
    await clickDialog('OK')
    await settle(B0, fc.undo[0])
    for (const [n, m] of Object.entries(fc.changed)) await compareSketch(n, m, 'map_face')
    await compareStep(fc, 'map_face')
    await restore(S0)
  }
  {
    const fc = FC.map_detach
    await selectFace('Face2')
    await runCmd('Sketcher_MapSketch')
    await pickItem('Sketch002'); await clickDialog('OK')
    await compareDialog(fc.dialogs[1], 'map_detach: the method')
    await pickItem('Do not attach'); await clickDialog('OK')
    await settle(B0, fc.undo[0])
    for (const [n, m] of Object.entries(fc.changed)) await compareSketch(n, m, 'map_detach')
    await compareStep(fc, 'map_detach')
    await restore(S0)
  }
  {
    await selectFace('Face6')
    await runCmd('Sketcher_MapSketch')
    await pickItem('Sketch'); await clickDialog('OK')
    await sleep(1500)
    check(!(await dialog()), 'map_circular: the Pad depends on Sketch, so no method is asked for (Circular dependencies are not allowed)')
    const log = await st('JSON.stringify(cadui.getState().messages.slice(-3).map((m) => m.text))')
    check(/Circular dependencies are not allowed/.test(log), 'map_circular: FreeCAD\'s warning', log)
  }
  {
    const fc = FC.map_self
    await selectRows(['Sketch001'])
    await runCmd('Sketcher_MapSketch')
    await compareDialog(fc.dialogs[0], 'map_self: the sketches')
    await pickItem('Sketch002'); await clickDialog('OK')
    await compareDialog(fc.dialogs[1], 'map_self: the method')
    await clickDialog('Cancel')
  }

  console.log('validate')
  for (const key of ['validate_sketch001', 'validate_sketch002', 'validate_sketch004']) {
    const fc = FC[key], sketch = `Sketch${key.slice(-3)}`
    await selectRows([sketch])
    await runCmd('Sketcher_ValidateSketch')
    await until('!!document.querySelector("[data-task=sketchValidate]")', `${key}: the panel`)
    const panel = () => st(`(() => { const t = document.querySelector('[data-task=sketchValidate]'); return {
      groups: [...t.querySelectorAll('fieldset > legend')].map((l) => l.textContent),
      buttons: [...t.querySelectorAll('button[data-name]')].map((b) => [b.dataset.name, b.textContent, !b.disabled]),
      combo: [...t.querySelectorAll('datalist option')].map((o) => o.value), current: t.querySelector('[data-name=comboBoxTolerance]').value,
      check: [t.querySelector('[data-name=checkBoxIgnoreConstruction]').parentElement.textContent.trim(), t.querySelector('[data-name=checkBoxIgnoreConstruction]').checked],
      title: t.querySelector('.tbox-head')?.textContent, close: t.querySelector('.tbuttons button')?.textContent } })()`)
    const fcPanel = (w) => ({ groups: w.filter((x) => x.class === 'QGroupBox').map((x) => x.title),
      buttons: w.filter((x) => x.class === 'QPushButton' && x.name).map((x) => [x.name, x.text, x.enabled]),
      combo: w.find((x) => x.name === 'comboBoxTolerance').items, current: w.find((x) => x.name === 'comboBoxTolerance').current,
      check: [w.find((x) => x.name === 'checkBoxIgnoreConstruction').text, w.find((x) => x.name === 'checkBoxIgnoreConstruction').checked],
      title: w.find((x) => x.class === 'QSint::ActionLabel')?.text, close: w.find((x) => x.class === 'QPushButton' && !x.name)?.text })
    const got = await panel(), want = fcPanel(fc.panel)
    for (const k of Object.keys(want)) same(got[k], want[k], `${key}: the panel's ${k}`)
    for (const step of fc.steps) {
      if (step.error) continue
      const b = step.button
      const enabled = await st(`!document.querySelector('[data-task=sketchValidate] button[data-name=${b}]').disabled`)
      const before = await top(), writes = step.undo.length > 0 && !['orientLockEnable', 'orientLockDisable'].includes(b)
      const unchanged = JSON.stringify(step.sketch.constraints) === JSON.stringify(fc.steps[fc.steps.indexOf(step) - 1]?.sketch.constraints ?? null)
      if (enabled) {
        await page.click(`[data-task=sketchValidate] button[data-name=${b}]`)
        if (step.dialogs.length) { await compareDialog(step.dialogs[0], `${key} ${b}: the question`); await clickDialog('Yes') }
        await sleep(300)
        await until('document.querySelector("[data-task=sketchValidate]")?.dataset.busy === "false"', `${key} ${b}: the answer`, 60000)
        if (writes && !unchanged) await settle(before)
      }
      const now = (await panel()).buttons, fcNow = fcPanel(step.panel).buttons
      same(now, fcNow, `${key} after ${b}: the buttons' state`)
      const f = await feature(sketch)
      check(f.constraints.length === step.sketch.constraints.length && f.geometry.length === step.sketch.geometry.length,
        `${key} after ${b}: ${step.sketch.geometry.length} geometries and ${step.sketch.constraints.length} constraints`, `${f.geometry.length} and ${f.constraints.length}`)
      if (writes && unchanged && (await top()) === before) note(`${key} ${b}: FreeCAD opens "${step.undo[0]}" though nothing changes; a change that changes nothing makes no step here`)
      else if (writes) {
        await compareStep(step, `${key} ${b}`)
        if (b === 'swapReversed') {                // port_reversedExternalArcs: the constraints swapped, the sketch solved
          const g = await feature(sketch)
          check(!sameConstraints(g.constraints, step.sketch.constraints), `${key} ${b}: the constraints`, sameConstraints(g.constraints, step.sketch.constraints))
          check(!sameGeometry(g.geometry, step.sketch.geometry), `${key} ${b}: the geometry`, sameGeometry(g.geometry, step.sketch.geometry))
          const n = await st('JSON.stringify(cadui.getState().messages.slice(-3).map((m) => m.text))')
          check(n.includes('changes were made to constraints linking to endpoints of reversed arcs'), `${key} ${b}: the notification`, n)
        }
      }
      else if (step.undo.length) note(`${key} ${b}: FreeCAD opens "${step.undo[0]}" for a change that does not stay (changeConstraintsLocking puts the old constraints back); here nothing is written`)
    }
    await page.click('[data-task=sketchValidate] .tbuttons button')
    await restore(S0)
  }
} catch (e) {
  bad('sketchobjcheck stopped', e.stack ?? String(e))
} finally {
  await browser.close()
  server.kill()
}
console.log(`sketchobjcheck: ${pass} ok, ${fail} failing, ${known} known differences`)
process.exit(fail ? 1 : 0)

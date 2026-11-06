// SPDX-License-Identifier: LGPL-2.1-or-later
// draftcheck: the Draft workbench in the page, driven end to end on a scratch project (FreeCAD 26.3 at 3160daf1e2b6
// for the command names, texts and property rows: ui/src/draft_cmds.ts and draft_props.ts come from it).
//
//   NODE_PATH=<folder with playwright> node ui/scripts/draftcheck.mjs [--keep] [--verbose] [--shot=PNG]
//
//   workbench  the switcher has Draft; the menu bar has Drafting, Annotation, Modification and Utilities
//   menus      Drafting and Modification list FreeCAD's commands in init_tools.py's order, with their menu texts
//   make       Rectangle, Circle, Wire and Point from their panels; Ortho Array, Clone and Path Array from the selection:
//              the object, its name and type, its undo step, and the document building with it
//   edit       Std_Edit on the rectangle opens its panel with its values; OK writes the change
//   props      the rectangle's property view has FreeCAD's rows
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
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
let pass = 0, fail = 0, known = 0
const ok = (what) => { pass++; if (args.includes('--verbose')) console.log(`  ok    ${what}`) }
const bad = (what, detail = '') => { fail++; console.log(`  FAIL  ${what}${detail ? `: ${detail}` : ''}`) }
const note = (what) => { known++; console.log(`  known ${what}`) }
const check = (cond, what, detail) => (cond ? ok(what) : bad(what, detail))
const same = (a, b, what) => check(JSON.stringify(a) === JSON.stringify(b), what, `\n        FreeCAD ${JSON.stringify(b)}\n        ours    ${JSON.stringify(a)}`)
// ── a scratch workbench (transformcheck.mjs's) ───────────────────────────────────────────────────────────────────────
const freePort = (from) => new Promise((res, rej) => {
  const tryPort = (p) => {
    if (p > from + 40) return rej(new Error('no free port'))
    const s = createServer(); s.once('error', () => tryPort(p + 1)); s.once('listening', () => s.close(() => res(p))); s.listen(p, '127.0.0.1')
  }
  tryPort(from)
})
const scratch = mkdtempSync(join(tmpdir(), 'cad-draftcheck-')), warmDir = mkdtempSync('/tmp/cdc')
const ROOT = join(scratch, 'root'); mkdirSync(ROOT)
for (const d of ['runtime', 'macros']) mkdirSync(join(scratch, d))
const python = process.env.CAD_PYTHON || join(REPO, '.venv', 'bin', 'python')
const env = { ...process.env, CAD_WARM_DIR: warmDir, CAD_RUNTIME_DIR: join(scratch, 'runtime'), CAD_MACRO_DIR: join(scratch, 'macros'),
  CAD_PREFS: join(scratch, 'prefs.json'), PYTHONPATH: REPO, CAD_PYTHON: python, CAD_RENDER_BACKEND: 'numpy' }
delete env.CAD_PROJECTS
spawnSync(python, ['-m', 'cad_agent', '--projects', ROOT, 'init', 'pc', '--brief', 'draftcheck'], { env, cwd: REPO })
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
const DOC = 'Unnamed'
const objects = () => st(`(cadui.getState().features[${JSON.stringify(DOC)}]?.objects ?? []).map((o) => ({ ...o }))`)
const tree = () => st(`cadui.getState().features[${JSON.stringify(DOC)}]?.object_tree ?? null`)
const undoName = () => st('cadui.getState().undo[0]?.name ?? null')
const count = async () => (await objects()).length
/** Wait for the document to have n objects (the server built the edit). */
const objectsAt = (n, what) => until(`(cadui.getState().features[${JSON.stringify(DOC)}]?.objects ?? []).length >= ${n} && !cadui.getState().busy.length`, what)
/** Select objects as tree clicks do (featSel: the tree's selection; partcheck.mjs drives the clicks themselves). */
async function selectRows(names) {
  await until('!cadui.getState().busy.length', 'the last edit to settle', 60000)
  await sleep(800)                 // addObject selects what it made once its edit is in: after that, not before
  const want = JSON.stringify(names.map((n) => `${DOC}/${n}`))
  await st(`cadui.setState({ featSel: ${want} })`)
  await until(`JSON.stringify(cadui.getState().featSel) === ${JSON.stringify(want)}`, `${names.join(', ')} selected`, 5000)
}
const runCmd = (cmd) => st(`cadui.getCommand(${JSON.stringify(cmd)})?.run([])`)
const clickButton = (text) => page.click(`.taskview .tbuttons button:text-is("${text}")`)
const setQ = async (qf, v) => { await page.fill(`.taskview [data-qf="${qf}"] input`, String(v)); await page.press(`.taskview [data-qf="${qf}"] input`, 'Tab'); await sleep(100) }
const obj = async (name) => (await objects()).find((o) => o.name === name)
const noErrors = () => st(`JSON.stringify(cadui.getState().features[${JSON.stringify(DOC)}]?.errors ?? {})`)
const DRAWING = ['Draft_Line', 'Draft_Wire', 'Draft_Fillet', 'Draft_ArcTools', 'Draft_Circle', 'Draft_Ellipse', 'Draft_Rectangle', 'Draft_Polygon',
  'Draft_BSpline', 'Draft_BezierTools', 'Draft_Point', 'Draft_Facebinder', 'Draft_ShapeString', 'Draft_Hatch']

try {
  await page.goto(`${BASE}/next/#pc`)
  await until('!!window.cadui && cadui.getState().slug === "pc" && !!cadui.getState().scene', 'the project to open')

  console.log('workbench')
  await st('cadui.setState({ workbench: "draft" })')
  await sleep(400)
  const bar = await st(`[...document.querySelectorAll('.menubar > .menu-title, .menubar > button, .menubar [role=menuitem]')].map((e) => e.textContent.trim()).filter(Boolean)`)
  for (const m of ['Drafting', 'Annotation', 'Modification', 'Utilities']) check(bar.includes(m), `the menu bar has ${m}`, JSON.stringify(bar))
  check(bar.indexOf('Utilities') < bar.indexOf('Windows'), 'the Draft menus come before Windows', JSON.stringify(bar))

  console.log('menus')
  const data = await st('cadui.draft()')
  const drafting = data.menus.find((m) => m.title === 'Drafting').entries.map((e) => e.cmd)
  same(drafting, DRAWING, 'Drafting: init_tools.py\'s drawing commands')
  const tb = data.toolbars.map((t) => t.title)
  same(tb, ['Draft Creation', 'Draft Annotation', 'Draft Modification', 'Draft Utility'], 'the toolbars')
  const rect = data.menus.find((m) => m.title === 'Drafting').entries.find((e) => e.cmd === 'Draft_Rectangle')
  check(rect.text === 'Rectangle' && rect.enabled, 'Rectangle: its menu text, enabled', JSON.stringify(rect))
  const arrays = data.menus.find((m) => m.title === 'Modification').entries.find((e) => e.cmd === 'Draft_ArrayTools')
  check(arrays?.menu?.some((e) => e.cmd === 'Draft_OrthoArray'), 'Modification: Array Tools has Array', JSON.stringify(arrays))
  check(!arrays.menu.find((e) => e.cmd === 'Draft_OrthoArray').enabled, 'Array is greyed with nothing selected')

  console.log('make')
  await runCmd('Draft_Rectangle')
  await until('!!document.querySelector(\'.taskview [data-task="draft-Draft_Rectangle"]\')', 'the Rectangle panel')
  if (args.includes('--debug')) console.log('   task', JSON.stringify(await st('cadui.getState().task')), JSON.stringify(await st('Object.keys(cadui.getState().features)')), JSON.stringify(await st('cadui.getState().messages?.slice(-3) ?? cadui.getState().log?.slice(-3)')), await st('document.querySelector(".taskview")?.innerHTML.slice(0, 300)'))
  await setQ('length', 30); await setQ('height', 12)
  await clickButton('OK')
  await objectsAt(1, 'the rectangle')
  const r = await obj('Rectangle')
  check(r?.type === 'Draft::Rectangle' && r.length === 30 && r.height === 12, 'Rectangle: Draft::Rectangle, 30 x 12', JSON.stringify(r))
  check(await undoName() === 'Rectangle', 'its undo step is "Rectangle"', await undoName())
  await runCmd('Draft_Circle')
  await until('!!document.querySelector(\'.taskview [data-task="draft-Draft_Circle"]\')', 'the Circle panel')
  await setQ('radius', 4); await setQ('posX', 50)
  await clickButton('OK')
  await objectsAt(2, 'the circle')
  const c = await obj('Circle')
  check(c?.radius === 4 && JSON.stringify(c.placement?.[0]) === '[50,0,0]', 'Circle: radius 4 at (50, 0, 0)', JSON.stringify(c))
  await runCmd('Draft_Wire')
  await until('!!document.querySelector(\'.taskview [data-task="draft-Draft_Wire"]\')', 'the Wire panel')
  await page.fill('.taskview [data-qf="points"]', '0, 20\n10, 20\n10, 30, 5')
  await clickButton('OK')
  await objectsAt(3, 'the wire')
  const w = await obj('Wire')
  check(JSON.stringify(w?.points) === '[[0,20,0],[10,20,0],[10,30,5]]', 'Wire: its three points', JSON.stringify(w))
  await runCmd('Draft_Point')
  await until('!!document.querySelector(\'.taskview [data-task="draft-Draft_Point"]\')', 'the Point panel')
  await setQ('x', 1); await setQ('y', 2); await setQ('z', 3)
  await clickButton('OK')
  await objectsAt(4, 'the point')
  check((await obj('Point'))?.z === 3, 'Point: at (1, 2, 3)', JSON.stringify(await obj('Point')))

  await selectRows(['Rectangle'])
  await runCmd('Draft_OrthoArray')
  if (args.includes('--debug')) console.log('   array', JSON.stringify(await st('cadui.getState().task')), JSON.stringify(await st('cadui.getState().featSel')), JSON.stringify(await st('cadui.getState().messages.slice(-3).map((m) => m.text)')), await st('cadui.getCommand("Draft_OrthoArray")?.enabled?.()'), await st('typeof cadui.getCommand("Draft_OrthoArray")'))
  await until('!!document.querySelector(\'.taskview [data-task="draft-Draft_OrthoArray"]\')', 'the Array panel')
  await setQ('number_x', 3); await setQ('interval_xX', 40)
  await clickButton('OK')
  await objectsAt(5, 'the array')
  const a = await obj('Array')
  check(a?.type === 'Draft::Array' && a.base === 'Rectangle' && a.number_x === 3 && a.interval_x?.[0] === 40, 'Array: of Rectangle, 3 along X at 40', JSON.stringify(a))
  check(!(await tree())?.shown?.includes('Rectangle'), 'the array hides its base', JSON.stringify(await tree()))
  await selectRows(['Circle'])
  await runCmd('Draft_Clone')
  await objectsAt(6, 'the clone')
  check(JSON.stringify((await obj('Clone'))?.objects) === '["Circle"]', 'Clone: of Circle', JSON.stringify(await obj('Clone')))
  await selectRows(['Point', 'Wire'])
  await runCmd('Draft_PathArray')
  await objectsAt(7, 'the path array')
  const pa = await obj('PathArray')
  check(pa?.base === 'Point' && pa.path_object === 'Wire', 'Path Array: Point along Wire', JSON.stringify(pa))
  await until(`!cadui.getState().busy.length`, 'the document to build')
  check(await noErrors() === '{}', 'the document builds with no error', await noErrors())

  console.log('edit')
  const seen = await st('cadui.getState().messages.length')
  await st(`cadui.editObject?.(${JSON.stringify(DOC)}, 'Rectangle')`)
  if (!await st('!!document.querySelector(\'.taskview [data-task="draft-Draft_Rectangle"]\')')) {
    await page.dblclick(`.ptrow[data-ref="${DOC}/Rectangle"] .tname`)
  }
  await until('!!document.querySelector(\'.taskview [data-task="draft-Draft_Rectangle"]\')', 'Std_Edit opens the Rectangle panel')
  const lv = await st('document.querySelector(\'.taskview [data-qf="length"] input\')?.value')
  check(/^30(\.0+)?\s*mm$/.test(String(lv)), 'the panel shows its length', lv)
  await setQ('length', 25)
  await clickButton('OK')
  await until(`(cadui.getState().features[${JSON.stringify(DOC)}]?.objects ?? []).find((o) => o.name === 'Rectangle')?.length === 25`, 'OK sets the length') && ok('OK sets the length')
  const r2 = await obj('Rectangle')
  check(r2.make_face !== false && r2.height === 12, 'and leaves the rest as it was', JSON.stringify(r2))
  await until('!cadui.getState().busy.length', 'the edit to build')
  const errs = await st(`cadui.getState().messages.slice(${seen}).filter((l) => l.level === "err").map((l) => l.text)`)
  check(!errs.length, 'no error in the Report view', JSON.stringify(errs))
  const scene = await st('cadui.getState().messages.filter((l) => /^Scene:/.test(l.text)).at(-1)?.text ?? ""')
  check(/ [1-9]\d* triangles/.test(scene), 'the faces are drawn', scene)

  console.log('props')
  await selectRows(['Rectangle'])
  await sleep(400)
  const rows = await st(`[...document.querySelectorAll('.props .prow .pk')].map((e) => e.textContent.trim())`)
  if (args.includes('--debug')) console.log('   props', JSON.stringify(await st('cadui.getState().task')), JSON.stringify(await st('cadui.getState().featSel')), await st('!!document.querySelector(".props")'), await st('document.querySelector(".props")?.innerHTML.slice(0, 400)'), JSON.stringify(await st('cadui.getState().selected')))
  for (const k of ['Length', 'Height', 'Fillet Radius', 'Chamfer Size', 'Make Face', 'Rows', 'Columns', 'Placement', 'Label'])
    check(rows.includes(k), `props: ${k}`, JSON.stringify(rows))
  if (flag('shot', '')) { await st('cadui.getCommand("Std_ViewFitAll")?.run([])'); await sleep(1500); await page.screenshot({ path: flag('shot', '') }); console.log(`screenshot: ${flag('shot', '')}`) }
} catch (e) {
  bad('draftcheck stopped', e.stack ?? String(e))
} finally {
  await browser.close()
  server.kill()
  if (!args.includes('--keep')) { rmSync(scratch, { recursive: true, force: true }); rmSync(warmDir, { recursive: true, force: true }) }
  else console.log(`scratch kept: ${scratch}`)
}
console.log(`draftcheck: ${pass} ok, ${fail} FAIL, ${known} known`)
process.exit(fail ? 1 : 0)

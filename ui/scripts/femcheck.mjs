// SPDX-License-Identifier: LGPL-2.1-or-later
// femcheck: the FEM workbench in the page (FreeCAD 26.3 at 3160daf1e2b6 for the menus, toolbars and command texts:
// ui/src/fem_cmds.ts comes from it), driven on a scratch project with a cantilever part (its FEM list).
//
//   NODE_PATH=<folder with playwright> FREECAD_BIN=<folder with gmsh and ccx> node ui/scripts/femcheck.mjs [--keep]
//
//   workbench  the switcher has FEM; Model, Mesh, Solve, Results and Utilities come before Windows; FreeCAD's toolbars
//   solve      Run Solver on the cantilever: the Report view has FreeCAD's results (tests/golden/fem/freecad.json)
//   panels     the same cantilever made in the task panels from a part with no FEM list, then solved: FreeCAD's results
//   results    Show Result: the values, the colours, the part hidden meanwhile, the displacement scaled
//   thermal    tests/golden/fem's thermomech made in the panels: FreeCAD's displacement, stress and temperatures
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
const scratch = mkdtempSync(join(tmpdir(), 'cad-femcheck-')), warmDir = mkdtempSync('/tmp/cfc')
const ROOT = join(scratch, 'root'); mkdirSync(ROOT)
for (const d of ['runtime', 'macros']) mkdirSync(join(scratch, d))
const python = process.env.CAD_PYTHON || join(REPO, '.venv', 'bin', 'python')
const env = { ...process.env, CAD_FEM_THREADS: "1", PATH: [process.env.FREECAD_BIN, process.env.PATH].filter(Boolean).join(":"), CAD_WARM_DIR: warmDir, CAD_RUNTIME_DIR: join(scratch, 'runtime'), CAD_MACRO_DIR: join(scratch, 'macros'),
  CAD_PREFS: join(scratch, 'prefs.json'), PYTHONPATH: REPO, CAD_PYTHON: python, CAD_RENDER_BACKEND: 'numpy' }
delete env.CAD_PROJECTS
spawnSync(python, ['-m', 'cad_agent', '--projects', ROOT, 'init', 'pc', '--brief', 'femcheck'], { env, cwd: REPO })
// the cantilever of tests/golden/fem as a part file: a Part box and its FEM list (tests/test_feature_fem.py's)
writeFileSync(join(ROOT, 'pc', 'parts', 'bar.py'), `"""bar: a steel cantilever."""
from cad_agent import feature_fem as Fem
from cad_agent import feature_part as Part

PARAMS = {}
OBJECTS = [Part.Box("Box", length=100, width=10, height=10)]

FEM = [
    Fem.SolverCalculiX("CalculiXccxTools"),
    Fem.MaterialSolid("Material", youngs_modulus="210000 MPa", poisson_ratio=0.30, density="7900 kg/m^3"),
    Fem.ConstraintFixed("Fixed", [("Box", "Face1")]),
    Fem.ConstraintForce("Force", [("Box", "Face2")], force="100 N", direction=("Box", "Edge5"), reversed=True),
    Fem.MeshGmsh("Mesh", "Box", characteristic_length_max="5 mm"),
]


def build(**p):
    return Part.Document(OBJECTS, p)
`)
writeFileSync(join(ROOT, 'pc', 'parts', 'warm.py'), `"""warm: a box for the thermal analysis."""
from cad_agent import feature_part as Part

PARAMS = {}
OBJECTS = [Part.Box("Box", length=100, width=10, height=10)]


def build(**p):
    return Part.Document(OBJECTS, p)
`)
writeFileSync(join(ROOT, 'pc', 'parts', 'blank.py'), `"""blank: the same box, no analysis yet."""
from cad_agent import feature_part as Part

PARAMS = {}
OBJECTS = [Part.Box("Box", length=100, width=10, height=10)]


def build(**p):
    return Part.Document(OBJECTS, p)
`)
const port = await freePort(9031)
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
// a QComboBox (combo.tsx) chosen by its item's text (pdlastcheck.mjs's)
const pickCombo = async (qf, text) => {
  await page.click(`.qselect[data-qf="${qf}"]`); await sleep(150)
  await page.locator('.combo-popup .combo-item', { hasText: text }).first().click()
  await sleep(400)
}
const FCJ = JSON.parse(readFileSync(join(REPO, 'tests', 'golden', 'fem', 'freecad.json'), 'utf8'))

try {
  console.log('workbench')
  await page.goto(`${BASE}/next/#pc`)
  await until('!!window.cadui && cadui.getState().slug === "pc" && !!cadui.getState().scene', 'the project to open')
  await st('cadui.setState({ workbench: "fem" })')
  await sleep(400)
  const bar = await st(`[...document.querySelectorAll('.menubar > .menu-title, .menubar > button, .menubar [role=menuitem]')].map((e) => e.textContent.trim()).filter(Boolean)`)
  for (const m of ['Model', 'Mesh', 'Solve', 'Results', 'Utilities']) check(bar.includes(m), `the menu bar has ${m}`, JSON.stringify(bar))
  check(bar.indexOf('Utilities') < bar.indexOf('Windows'), 'the FEM menus come before Windows', JSON.stringify(bar))
  const data = await st('cadui.fem()')
  same(data.toolbars.map((t) => t.title), ['Model', 'Electromagnetic Boundary Conditions', 'Fluid Boundary Conditions', 'Geometrical Analysis Features',
    'Mechanical Boundary Conditions and Loads', 'Thermal Boundary Conditions and Loads', 'Mesh', 'Solve', 'Results', 'Utilities'], 'FreeCAD\'s toolbars')
  const solve = data.menus.find((m) => m.title === 'Solve').entries
  const run = solve.find((e) => e.cmd === 'FEM_SolverRun')
  check(run?.text === 'Run Solver' && run.enabled, 'Solve > Run Solver, enabled', JSON.stringify(run))
  check(solve.find((e) => e.cmd === 'FEM_CompSolvers')?.menu?.some((e) => e.cmd === 'FEM_SolverCalculiX'), 'Solvers has CalculiX')

  console.log('solve')
  await st(`cadui.setState({ featSel: ['bar/Box'] })`)
  const n = await st('cadui.getState().messages.length')
  await runCmd('FEM_SolverRun')
  await until(`cadui.getState().messages.slice(${n}).some((m) => /max von Mises/.test(m.text) || m.level === 'err')`, 'the solver to finish', 300000)
  const msgs = await st(`cadui.getState().messages.slice(${n}).map((m) => m.level + ': ' + m.text)`)
  const line = msgs.find((m) => /max von Mises/.test(m)) ?? ''
  const want = FCJ.cantilever
  check(line.includes(`${want.nodes} nodes`) && line.includes(want.max_displacement.toPrecision(6)) && line.includes(want.max_von_mises.toPrecision(6)),
    'Run Solver: FreeCAD\'s nodes, displacement and stress', JSON.stringify(msgs))

  console.log('panels')
  // the same cantilever, this time from a part with no FEM list, every object made in the panels
  await st(`cadui.setState({ featSel: ['blank/Box'], selected: [], task: null })`)
  await until(`!!cadui.getState().features.blank`, 'the blank part to load', 30000)
  const qf = (name) => `[data-qf="${name}"]`
  const open = async (cmd, task) => { await runCmd(cmd); await page.waitForSelector(`[data-task="${task}"]`, { timeout: 15000 }) }
  const pick = async (name) => {
    await until(`!!cadui.getView().helperPicker && [...cadui.getView().helpers.values()].some((g) => { let f = false; g.traverse((o) => { if (o.userData.pickName === ${JSON.stringify(name)}) f = true }); return f })`, `${name} to be pickable`, 30000)
    await st(`cadui.getView().helperPicker(${JSON.stringify(name)})`); await sleep(120)
  }
  const accept = async () => { await page.click(`[data-task="fem-object"] ${qf('ok')}`); await page.waitForSelector('[data-task="fem-analysis"]', { timeout: 15000 }); await page.waitForSelector(qf('run'), { timeout: 15000 }) }
  const srcNow = () => readFileSync(join(ROOT, 'pc', 'parts', 'blank.py'), 'utf8')
  await open('FEM_Analysis', 'fem-analysis')
  await page.waitForSelector(qf('empty'), { timeout: 15000 })
  ok('the new analysis is empty')
  await runCmd('FEM_SolverCalculiX')
  await page.waitForSelector('[data-name="CalculiXccxTools"]', { timeout: 30000 })
  await open('FEM_MaterialSolid', 'fem-object'); await accept()
  await open('FEM_ConstraintFixed', 'fem-object'); await pick('@Box.Face1')
  check(await page.$('[data-ref="Box:Face1"]') !== null, 'a face picked is listed'); await accept()
  await open('FEM_ConstraintForce', 'fem-object'); await pick('@Box.Face2')
  await page.fill(qf('spinForce'), '100 N')
  await page.click(qf('buttonDirection')); await pick('@Box.Edge5')
  same(await page.inputValue(qf('lineDirection')), 'Box:Edge5', 'Direction takes the next pick')
  check(await page.$('[data-ref="Box:Edge5"]') === null, 'the direction pick is not a reference')
  await page.click(`${qf('checkReverse')}, label:has-text("Reverse direction") input`); await accept()
  await open('FEM_MeshGmshFromShape', 'fem-object')
  await page.fill(qf('qsb_max_size'), 'five'); await page.click(`[data-task="fem-object"] ${qf('ok')}`); await sleep(400)
  check(await page.$('[data-task="fem-object"]') !== null, 'a size with no unit is refused')
  await page.fill(qf('qsb_max_size'), '5 mm'); await accept()
  const made = srcNow()
  check(/Fem\.ConstraintForce\("ConstraintForce", \[\("Box", "Face2"\)\], force="100 N", direction=\("Box", "Edge5"\), reversed=True\)/.test(made), 'the part file has the force as written by hand', made)
  // a pressure added and deleted leaves the file as it was; undo takes back a step
  await open('FEM_ConstraintPressure', 'fem-object'); await pick('@Box.Face6'); await page.fill(qf('if_pressure'), '2 MPa'); await accept()
  check(srcNow().includes('Fem.ConstraintPressure("ConstraintPressure", [("Box", "Face6")], pressure="2 MPa")'), 'Pressure Load is in the part file')
  await page.click(`[data-name="ConstraintPressure"] ${qf('delete')}`)
  await until(`!document.querySelector('[data-name="ConstraintPressure"]') || true`, 'delete', 2000); await sleep(1500)
  same(srcNow(), made, 'deleting the object puts the file back')
  // editing keeps what the panel did not touch
  await page.click(`[data-name="ConstraintForce"] ${qf('edit')}`)
  await page.waitForSelector(qf('spinForce'), { timeout: 15000 })
  same(await page.inputValue(qf('spinForce')), '100 N', 'Edit shows the object\'s values')
  same(await page.inputValue(qf('lineDirection')), 'Box:Edge5', 'Edit shows the direction')
  await page.fill(qf('spinForce'), '200 N'); await accept()
  check(srcNow() === made.replace('force="100 N"', 'force="200 N"'), 'Edit changes only that property', srcNow())
  await page.click(`[data-name="ConstraintForce"] ${qf('edit')}`)
  await page.waitForSelector(qf('spinForce'), { timeout: 15000 }); await page.fill(qf('spinForce'), '100 N'); await accept()
  same(srcNow(), made, 'and back')
  const n2 = await st('cadui.getState().messages.length')
  await st(`cadui.setState({ featSel: ['blank/Box'] })`)
  await runCmd('FEM_SolverRun')
  await until(`cadui.getState().messages.slice(${n2}).some((m) => /max von Mises/.test(m.text) || m.level === 'err')`, 'the panels\' solver to finish', 300000)
  const msgs2 = await st(`cadui.getState().messages.slice(${n2}).map((m) => m.level + ': ' + m.text)`)
  const line2 = msgs2.find((m) => /max von Mises/.test(m)) ?? ''
  check(line2.includes(`${want.nodes} nodes`) && line2.includes(want.max_displacement.toPrecision(6)) && line2.includes(want.max_von_mises.toPrecision(6)),
    'the analysis made in the panels gives FreeCAD\'s nodes, displacement and stress', JSON.stringify(msgs2))

  console.log('results')
  await open('FEM_ResultShow', 'fem-result')
  await page.waitForSelector(qf('le_max'), { timeout: 30000 })
  check((await page.inputValue(qf('le_max'))).startsWith(want.max_von_mises.toPrecision(6)), 'the panel\'s maximum is FreeCAD\'s von Mises', await page.inputValue(qf('le_max')))
  const helper = `cadui.getView().helpers.get('fem-result').children[0]`
  await until(`!!cadui.getView().helpers.get('fem-result')`, 'the result to be drawn', 15000)
  const colours = () => st(`new Set(Array.from(${helper}.geometry.attributes.color.array).map((x) => x.toFixed(2))).size`)
  check(await colours() > 10, 'the mesh is coloured by the values', String(await colours()))
  const lo = () => st(`Math.min(...Array.from(${helper}.geometry.attributes.position.array).filter((_, i) => i % 3 === 2))`)
  const z0 = await lo()
  const hiddenNow = await st(`cadui.getState().hidden.slice()`)
  const blankBody = await st(`cadui.getState().scene.bodies.filter((b) => b.part === 'blank').map((b) => b.name)`)
  check(blankBody.length > 0 && blankBody.every((b) => hiddenNow.includes(b)), 'the part is hidden while its result shows', JSON.stringify(hiddenNow))
  await page.click(`${qf('rb_abs_displacement')}, label:has-text("Displacement magnitude") input`); await sleep(200)
  check((await page.inputValue(qf('le_max'))).startsWith(want.max_displacement.toPrecision(6)), 'Displacement magnitude: FreeCAD\'s maximum', await page.inputValue(qf('le_max')))
  await page.click(`${qf('cb_show_displacement')}, label:has-text("Show") input`); await page.fill(qf('sb_displacement_factor'), '10'); await sleep(200)
  const z1 = await lo()
  await page.click(`${qf('rb_z_displacement')} input`); await sleep(200)
  const dz = Math.abs(parseFloat(await page.inputValue(qf('le_min'))))
  check(dz > 0 && Math.abs(Math.abs(z1 - z0) - 10 * dz) < 1e-3, 'Show at factor 10 moves the lowest point by ten times its Z displacement', `${z0} -> ${z1}, Displacement Z ${dz}`)
  await page.click('[data-task="fem-result"] .tbuttons .qbtn')
  await page.waitForSelector('[data-task="fem-analysis"]', { timeout: 15000 })
  check(!await st(`!!cadui.getView().helpers.get('fem-result')`), 'Close takes the result away')
  const back = await st(`cadui.getState().hidden.slice()`)
  check(blankBody.every((b) => !back.includes(b)), 'and shows the part again', JSON.stringify(back))

  console.log('thermal')
  // tests/golden/fem's thermomech, made in the panels on a fresh box: the solver switched to thermomech, the material's
  // thermal properties, two temperatures and the initial temperature
  await st(`cadui.setState({ featSel: ['warm/Box'], selected: [], task: null })`)
  await until(`!!cadui.getState().features.warm`, 'the warm part to load', 30000)
  await open('FEM_Analysis', 'fem-analysis')
  await runCmd('FEM_SolverCalculiX'); await page.waitForSelector('[data-name="CalculiXccxTools"]', { timeout: 30000 })
  await page.click(`[data-name="CalculiXccxTools"] ${qf('edit')}`); await page.waitForSelector(qf('AnalysisType'), { timeout: 15000 })
  await pickCombo('AnalysisType', 'thermomech'); await accept()
  await open('FEM_MaterialSolid', 'fem-object')
  await page.fill(qf('qsb_thermal_conductivity'), '50 W/m/K'); await page.fill(qf('qsb_expansion_coefficient'), '12 um/m/K'); await page.fill(qf('qsb_specific_heat'), '500 J/kg/K')
  await accept()
  await open('FEM_ConstraintFixed', 'fem-object'); await pick('@Box.Face1'); await accept()
  await open('FEM_ConstraintTemperature', 'fem-object'); await pick('@Box.Face1'); await page.fill(qf('qsb_temperature'), '373 K'); await accept()
  await open('FEM_ConstraintTemperature', 'fem-object'); await pick('@Box.Face2'); await page.fill(qf('qsb_temperature'), '293 K'); await accept()
  await open('FEM_ConstraintInitialTemperature', 'fem-object'); await page.fill(qf('if_temperature'), '293 K'); await accept()
  await open('FEM_MeshGmshFromShape', 'fem-object'); await page.fill(qf('qsb_max_size'), '5 mm'); await accept()
  const warm = readFileSync(join(ROOT, 'pc', 'parts', 'warm.py'), 'utf8')
  check(warm.includes('Fem.SolverCalculiX("CalculiXccxTools", analysis_type="thermomech")') && warm.includes('Fem.ConstraintTemperature("ConstraintTemperature001", [("Box", "Face2")], temperature="293 K")'),
    'the part file has the thermal analysis', warm)
  const tm = FCJ.thermomech, n3 = await st('cadui.getState().messages.length')
  await runCmd('FEM_SolverRun')
  await until(`cadui.getState().messages.slice(${n3}).some((m) => /max von Mises/.test(m.text) || m.level === 'err')`, 'the thermal solve', 300000)
  const line3 = (await st(`cadui.getState().messages.slice(${n3}).map((m) => m.level + ': ' + m.text)`)).find((m) => /max von Mises/.test(m)) ?? ''
  check(line3.includes(`${tm.nodes} nodes`) && line3.includes(tm.max_displacement.toPrecision(6)) && line3.includes(tm.max_von_mises.toPrecision(6))
    && line3.includes(`temperature ${tm.min_temperature.toPrecision(6)} to ${tm.max_temperature.toPrecision(6)} K`), 'the thermal analysis made in the panels gives FreeCAD\'s results', line3)
  await open('FEM_ResultShow', 'fem-result'); await page.waitForSelector(qf('rb_temperature'), { timeout: 30000 })
  await page.click(`${qf('rb_temperature')} input`); await sleep(200)
  check((await page.inputValue(qf('le_max'))).startsWith(tm.max_temperature.toPrecision(6)), 'Show Result: Temperature, FreeCAD\'s maximum', await page.inputValue(qf('le_max')))
  await page.click('[data-task="fem-result"] .tbuttons .qbtn'); await page.waitForSelector('[data-task="fem-analysis"]', { timeout: 15000 })
  // Gravity is added without a panel, as FreeCAD's command does; its Edit has the acceleration and direction
  await runCmd('FEM_ConstraintSelfWeight'); await page.waitForSelector('[data-name="ConstraintSelfWeight"]', { timeout: 30000 })
  check(readFileSync(join(ROOT, 'pc', 'parts', 'warm.py'), 'utf8').includes('Fem.ConstraintSelfWeight("ConstraintSelfWeight")'), 'Gravity Load adds a self weight')
} catch (e) {
  bad('femcheck stopped', e.stack ?? String(e))
} finally {
  await browser.close()
  server.kill()
  if (!args.includes('--keep')) { rmSync(scratch, { recursive: true, force: true }); rmSync(warmDir, { recursive: true, force: true }) }
  else console.log(`scratch kept: ${scratch}`)
}
console.log(`femcheck: ${pass} ok, ${fail} FAIL, ${known} known`)
process.exit(fail ? 1 : 0)

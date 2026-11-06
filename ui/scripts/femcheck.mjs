// SPDX-License-Identifier: LGPL-2.1-or-later
// femcheck: the FEM workbench in the page (FreeCAD 26.3 at 3160daf1e2b6 for the menus, toolbars and command texts:
// ui/src/fem_cmds.ts comes from it), driven on a scratch project with a cantilever part (its FEM list).
//
//   NODE_PATH=<folder with playwright> FREECAD_BIN=<folder with gmsh and ccx> node ui/scripts/femcheck.mjs [--keep]
//
//   workbench  the switcher has FEM; Model, Mesh, Solve, Results and Utilities come before Windows; FreeCAD's toolbars
//   solve      Run Solver on the cantilever: the Report view has FreeCAD's results (tests/golden/fem/freecad.json)
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

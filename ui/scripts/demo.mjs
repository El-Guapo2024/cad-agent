// SPDX-License-Identifier: MIT
// demo: the scripted demo flow, a bracket from an empty project to a drawing and G-code, driven in the page as a person
// would (toolbar buttons, task panels, OK), paced for an audience and recorded as a backup video.
//
//   NODE_PATH=<folder with playwright> node ui/scripts/demo.mjs [--record=DIR] [--pace=1.0] [--headed] [--keep] [--runs=N]
//
// It starts a scratch workbench (a temporary projects folder, as editcheck.mjs does) and runs, in Chromium:
//   1  New Body, New Sketch on the XY plane (the attachment panel, OK), the profile written into it: a 60 x 40 plate
//   2  Pad (its panel, OK)
//   3  a second sketch 20 mm up with a circle, Pocket through the plate (its panel, OK; 30 mm deep)
//   4  Fillet on the plate's four vertical edges (the panel, OK), radius 5
//   5  a parameter edit: the Pad's Length 10 -> 15 in the property view's terms (one undo step), the part rebuilt
//   6  a TechDraw page from the ISO A4 template, a view of the part (TaskProjGroup, OK), the page exported as PDF
//   7  CAM: a Job on the part (the New Job dialog, the Job's panel, OK), a Profile around it (its panel, OK), CAM_Post
//      with grbl: the G-code saved
// Each step is checked (the feature made and valid, the file written) and timed; --runs=N repeats the whole flow (a
// demo has to run smoothly every time). --record=DIR keeps a video of each run (Playwright's recordVideo, .webm) and
// the PDF, the G-code and a still after each step. Exit 1 when a step fails.
import { spawn, spawnSync } from 'child_process'
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, renameSync, rmSync } from 'fs'
import { createServer } from 'net'
import { tmpdir } from 'os'
import { dirname, join } from 'path'
import { fileURLToPath } from 'url'
import { createRequire } from 'module'

const require = createRequire(import.meta.url)
const { chromium } = require('playwright')
const REPO = join(dirname(fileURLToPath(import.meta.url)), '..', '..')
const arg = (k, d) => { const a = process.argv.find((x) => x.startsWith(`--${k}=`)); return a ? a.slice(k.length + 3) : d }
const flag = (k) => process.argv.includes(`--${k}`)
const RECORD = arg('record', null), PACE = Number(arg('pace', '1.0')), RUNS = Number(arg('runs', '1'))
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const beat = (ms = 900) => sleep(ms * PACE)              // a pause the audience can follow
let fail = 0
const ok = (what) => console.log(`  ok    ${what}`)
const bad = (what, detail = '') => { fail++; console.log(`  FAIL  ${what}${detail ? `: ${detail}` : ''}`) }
const check = (cond, what, detail) => (cond ? ok(what) : bad(what, detail))

// ── a scratch workbench ──────────────────────────────────────────────────────────────────────────────────────────────
const freePort = (from) => new Promise((res, rej) => {
  const tryPort = (p) => {
    if (p > from + 40) return rej(new Error('no free port'))
    const s = createServer(); s.once('error', () => tryPort(p + 1)); s.once('listening', () => s.close(() => res(p))); s.listen(p, '127.0.0.1')
  }
  tryPort(from)
})
const scratch = mkdtempSync(join(tmpdir(), 'cad-demo-')), warmDir = mkdtempSync('/tmp/cdm')
const ROOT = join(scratch, 'root'); mkdirSync(ROOT)
for (const d of ['runtime', 'macros']) mkdirSync(join(scratch, d))
const python = process.env.CAD_PYTHON || join(REPO, '.venv', 'bin', 'python')
const env = { ...process.env, CAD_WARM_DIR: warmDir, CAD_RUNTIME_DIR: join(scratch, 'runtime'), CAD_MACRO_DIR: join(scratch, 'macros'),
  CAD_PREFS: join(scratch, 'prefs.json'), PYTHONPATH: REPO, CAD_PYTHON: python, CAD_RENDER_BACKEND: 'numpy' }
delete env.CAD_PROJECTS
const port = await freePort(8891)
const server = spawn(python, ['-c', `import sys; from pathlib import Path; from cad_agent import serve; serve.run([Path(sys.argv[1])], host="127.0.0.1", port=${port})`, ROOT],
  { env, cwd: REPO, stdio: ['ignore', 'pipe', 'pipe'] })
await new Promise((res, rej) => {
  const t = setTimeout(() => rej(new Error('the scratch workbench did not start')), 60000)
  server.stdout.on('data', (d) => { if (/workbench: http/.test(String(d))) { clearTimeout(t); res() } })
  server.on('exit', (c) => rej(new Error(`the scratch workbench exited with ${c}`)))
})
const BASE = `http://127.0.0.1:${port}`
const browser = await chromium.launch({ headless: !flag('headed'), args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] })

async function run(n) {
  const slug = `bracket${n}`
  spawnSync(python, ['-m', 'cad_agent', '--projects', ROOT, 'init', slug, '--brief', 'demo: a bracket plate'], { env, cwd: REPO })
  const vdir = RECORD ? join(RECORD, `run${n}`) : null
  if (vdir) mkdirSync(vdir, { recursive: true })
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true,
    ...(vdir ? { recordVideo: { dir: vdir, size: { width: 1440, height: 900 } } } : {}) })
  const page = await ctx.newPage()
  page.on('pageerror', (e) => bad('page error', e.message))
  const st = (expr) => page.evaluate(expr)
  const until = async (expr, what, ms = 120000) => {
    const t0 = Date.now()
    while (Date.now() - t0 < ms) { if (await st(expr)) return true; await sleep(250) }
    bad(`timed out waiting: ${what}`); return false
  }
  const post = async (path, body) => (await fetch(BASE + path, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CAD': '1' }, body: JSON.stringify(body) })).json()
  const runCmd = (cmd) => st(`cadui.getCommand(${JSON.stringify(cmd)})?.run([])`)
  const idle = () => until('!cadui.getState().busy.length', 'the server idle')
  const fit = async () => { await st('cadui.getCommand("Std_ViewFitAll")?.run([])'); await beat(600) }
  const times = []
  const step = async (name, fn) => {
    const t0 = Date.now()
    console.log(name)
    try { await fn() } catch (e) { bad(`${name}: ${e.message.split('\n')[0]}`) }
    times.push([name, (Date.now() - t0) / 1000])
    if (vdir) await page.screenshot({ path: join(vdir, `${name.split(' ')[0]}.png`) })   // a still per step
  }
  const feature = (name) => st(`cadui.getState().features.Body?.features.find((f) => f.name === ${JSON.stringify(name)}) ?? null`)
  const valid = async (name) => { const f = await feature(name); return !!f && !f.error && !f.invalid }

  await page.goto(`${BASE}/next/#${slug}`)
  await until(`!!window.cadui && cadui.getState().slug === ${JSON.stringify(slug)} && !!cadui.getState().scene`, 'the project to open')
  await st('cadui.setState({ workbench: "design" })')
  await beat()

  await step('1 body and sketch', async () => {
    await page.click('.tb-btn[data-cmd="PartDesign_Body"]')
    await until('!!cadui.getState().features.Body', 'New Body')
    await beat()
    await page.click('.tb-btn[data-cmd="PartDesign_CompSketches"]')
    await until('cadui.getState().task?.kind === "attach"', "New Sketch's panel")
    await st('cadui.showPanel("model")')
    await page.click('.trow[data-ref="Body/XY_Plane"]')
    await st('cadui.showPanel("tasks")')
    await beat()
    await page.click('.taskview .pd-buttons .qbtn.default')
    await until('!!document.querySelector(".sketch-task")', 'the Sketcher')
    const rect = [[0, 0, 60, 0], [60, 0, 60, 40], [60, 40, 0, 40], [0, 40, 0, 0]].map(([a, b, c, d]) => ({ type: 'LineSegment', start: [a, b], end: [c, d], construction: false }))
    await post(`/api/${slug}/features/Body`, { ops: [{ op: 'set', name: 'Sketch', props: { geometry: rect } }] })
    await until('cadui.getState().features.Body.features[0].geometry.length === 4', 'the profile')
    await beat(1400)
    await page.click('.sketch-task .tbuttons .qbtn.default')
    await until('!document.querySelector(".sketch-task") && cadui.getState().workbench === "design"', 'Part Design again')
    check(await valid('Sketch'), 'the sketch on XY with a 60 x 40 profile')
  })
  await step('2 pad', async () => {
    await st('cadui.setState({ featSel: ["Body/Sketch"], selected: [] })')
    await page.click('.tb-btn[data-cmd="PartDesign_Pad"]')
    await until('cadui.getState().task?.kind === "pad"', "Pad's panel")
    await beat(1400)
    await page.click('.taskview .pd-buttons .qbtn.default')
    await until('cadui.getState().features.Body.tip === "Pad"', 'the Pad')
    await until('cadui.getState().scene?.bodies.some((b) => b.part === "Body")', 'the part in the 3D view')
    await fit()
    check(await valid('Pad'), 'Pad: a 10 mm plate')
  })
  await step('3 pocket', async () => {
    const circle = [{ type: 'Circle', center: [30, 20], radius: 8, construction: false }]
    await post(`/api/${slug}/features/Body`, { ops: [{ op: 'add', feature: { name: 'Sketch001', type: 'Sketcher::SketchObject', support: 'XY', attachment_offset: [0, 0, 20], geometry: circle, constraints: [] } }] })
    await until('cadui.getState().features.Body.features.some((f) => f.name === "Sketch001")', 'Sketch001')
    await beat()
    await st('cadui.setState({ featSel: ["Body/Sketch001"], selected: [] })')
    await page.click('.tb-btn[data-cmd="PartDesign_Pocket"]')
    await until('cadui.getState().task?.kind === "pocket"', "Pocket's panel")
    await beat(1400)
    // the sketch above the plate and 30 mm deep: still a hole through when the plate gets thicker (step 5)
    await page.click('.taskview .pd-buttons .qbtn.default')
    await until('cadui.getState().features.Body.tip === "Pocket"', 'the Pocket')
    await post(`/api/${slug}/features/Body`, { ops: [{ op: 'set', name: 'Pocket', props: { length: 30 } }] })
    await idle()
    check(await valid('Pocket'), 'Pocket: a 16 mm hole through the plate')
  })
  await step('4 fillet', async () => {
    const body = await st('cadui.getState().scene.bodies.find((b) => b.part === "Body").name')
    // the plate's four vertical corner edges, numbered as the 3D view numbers them (TopExp::MapShapes)
    const py = `import json, sys
from OCP.BRep import BRep_Tool
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopExp import TopExp
from OCP.TopoDS import TopoDS
from pathlib import Path
from cad_agent import state
from cad_agent.feature import _subs
state.ROOT = Path(sys.argv[2])
solid, _ = state.build_part(sys.argv[1], "Body")
out = []
for i, e in enumerate(_subs(solid.wrapped, TopAbs_EDGE)):
    e = TopoDS.Edge(e)
    a, b = BRep_Tool.Pnt_s(TopExp.FirstVertex_s(e)), BRep_Tool.Pnt_s(TopExp.LastVertex_s(e))
    if abs(a.X() - b.X()) < 1e-6 and abs(a.Y() - b.Y()) < 1e-6 and abs(a.Z() - b.Z()) > 5 and (abs(a.X()) < 1e-6 or abs(a.X() - 60) < 1e-6):
        out.append(f"Edge{i + 1}")
print(json.dumps(out))`
    const r = spawnSync(python, ['-c', py, slug, ROOT], { env, cwd: REPO })
    const pick = JSON.parse(String(r.stdout).trim().split('\n').pop() || '[]')
    check(pick.length === 4, "the plate's four vertical edges", String(r.stderr).slice(-300))
    await st(`cadui.setState({ activeBody: "Body", featSel: [], subSel: ${JSON.stringify(pick.map((e) => `${body}.${e}`))}, selected: [] })`)
    await page.click('.tb-btn[data-cmd="PartDesign_Fillet"]')
    await until('cadui.getState().task?.kind === "fillet"', "Fillet's panel")
    await beat(1400)
    await page.click('.taskview .pd-buttons .qbtn.default')
    await until('cadui.getState().features.Body.tip === "Fillet"', 'the Fillet')
    await post(`/api/${slug}/features/Body`, { ops: [{ op: 'set', name: 'Fillet', props: { radius: 5 } }] })
    await idle()
    await beat()
    check(await valid('Fillet'), `Fillet on ${pick.join(', ')}`)
  })
  await step('5 parameter edit', async () => {
    await post(`/api/${slug}/features/Body`, { ops: [{ op: 'set', name: 'Pad', props: { length: 15 } }] })
    await until('Number(cadui.getState().features.Body.features.find((f) => f.name === "Pad")?.length) === 15', 'Length 15')
    await idle()
    await beat(1400)
    check(await valid('Fillet'), 'Pad Length 10 -> 15: the part rebuilt, the Fillet still valid')
  })
  await step('6 drawing', async () => {
    await st('cadui.setState({ workbench: "techdraw" })')
    await beat()
    const r = await post(`/api/${slug}/techdraw/Page`, { ops: [{ op: 'new_page', template: 'ISO/A4_Landscape_TD.svg' }], name: 'Insert Page using Template' })
    check(r.exit === 0, 'a page from the ISO A4 template', JSON.stringify(r).slice(0, 200))
    await until('cadui.td.state().pages.includes("Page")', 'the page')
    const body = await st('cadui.getState().scene.bodies.find((b) => b.part === "Body").name')
    await st(`cadui.setState({ selected: [${JSON.stringify(body)}] })`)
    await runCmd('TechDraw_View')
    await until('cadui.getState().task?.kind === "techdraw"', 'TaskProjGroup')
    await beat(1400)
    await page.click('.tasks .tbuttons .qbtn.default')
    await idle()
    await st('cadui.td.select(null)')            // the view's lines, not the selection's highlight
    await beat(1400)
    const dl = page.waitForEvent('download', { timeout: 120000 })
    await runCmd('TechDraw_ExportPagePDF')
    const d = await dl
    const pdf = join(scratch, `${slug}.pdf`)
    await d.saveAs(pdf)
    check(readFileSync(pdf).subarray(0, 5).toString() === '%PDF-', 'the page exported as PDF', d.suggestedFilename())
    if (vdir) copyFileSync(pdf, join(vdir, 'Page.pdf'))
  })
  await step('7 cam', async () => {
    await page.locator('.dv-tab', { hasText: `${slug} : 1` }).first().click()        // back to the 3D view
    await st(`cadui.setState({ workbench: 'cam' })`)
    await beat()
    const body = await st('cadui.getState().scene.bodies.find((b) => b.part === "Body").name')
    await st(`(() => { cadui.camApi.set({ sel: [] }); cadui.setState({ selected: [${JSON.stringify(body)}], subSel: [] }) })()`)
    await runCmd('CAM_Job')
    await until(`!!document.querySelector('[data-cam-dialog="jobcreate"]')`, 'the New Job dialog')
    await beat()
    await page.locator('[data-cam-dialog="jobcreate"] .qbtn.default').click()
    await until(`!!document.querySelector('.tasks [data-qf="pathEdit"]')`, "the Job's panel")
    await beat()
    await page.locator('.tasks .tbuttons .qbtn.default').first().click()
    await idle()
    await st(`cadui.setState({ selected: [${JSON.stringify(body)}], subSel: [] })`)
    await runCmd('CAM_Profile')
    await until(`!!document.querySelector('.tasks[data-cam-panel="Profile"]')`, 'the Profile panel')
    await beat(1400)
    await page.locator('.tasks .tbuttons .qbtn.default').first().click()
    await idle()
    await fit()
    await beat(1400)
    await st(`cadui.camApi.select('Job/Job')`)
    await runCmd('CAM_Post')
    await until(`!!document.querySelector('[data-cam-dialog="post"]')`, 'the post-processor choice')
    await page.locator('[data-cam="posts"] .qf-list-row', { hasText: 'grbl' }).click()
    await beat()
    const dl = page.waitForEvent('download', { timeout: 120000 })
    await page.locator('[data-cam-dialog="post"] .qbtn.default').click()
    const d = await dl
    const nc = join(scratch, `${slug}.nc`)
    await d.saveAs(nc)
    const g = readFileSync(nc, 'utf8')
    check(/G0|G1/.test(g) && g.split('\n').length > 20, "grbl G-code for the Profile, saved", `${d.suggestedFilename()}, ${g.split('\n').length} lines`)
    if (vdir) copyFileSync(nc, join(vdir, 'Job.nc'))
  })
  await beat(1500)
  const video = page.video()
  await ctx.close()
  if (video && vdir) { const p = await video.path(); renameSync(p, join(vdir, 'demo.webm')) }
  console.log(`run ${n}: ${times.map(([s, t]) => `${s.split(' ')[0]} ${t.toFixed(1)} s`).join(', ')}, total ${times.reduce((a, [, t]) => a + t, 0).toFixed(1)} s`)
}

try {
  for (let n = 1; n <= RUNS; n++) await run(n)
} finally {
  await browser.close()
  server.kill()
  if (!flag('keep')) { rmSync(scratch, { recursive: true, force: true }); rmSync(warmDir, { recursive: true, force: true }) }
}
console.log(`demo: ${RUNS} run(s), ${fail} FAIL`)
process.exit(fail ? 1 : 0)

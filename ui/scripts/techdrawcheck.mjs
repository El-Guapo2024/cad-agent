// SPDX-License-Identifier: LGPL-2.1-or-later
// techdrawcheck: the TechDraw workbench in the page, held to the real FreeCAD's (ui/scripts/fctechdraw.json, written by
// fctechdraw.py from FreeCAD 26.3 at 3160daf1e2b6), then driven end to end on a scratch project.
//
//   NODE_PATH=<folder with playwright> node ui/scripts/techdrawcheck.mjs [--fc=ui/scripts/fctechdraw.json] [--only=SECTION,...] [--keep] [--verbose]
//
// It starts a scratch workbench of its own (as assemblycheck.mjs does) with the parts plate and bracket, the BREPs of
// tests/golden/techdraw (the same shapes fctechdraw_dump.py drew), and in Chromium on SwiftShader repeats what the
// recording did, step for step:
//   menus      the menu bar puts TechDraw before Windows; the TechDraw menu with no page, with a page, with an edge
//              selected, entry by entry (FreeCAD's texts and commands; greyed or not, the commands not ported `known`)
//   toolbars   the ten toolbars, button by button
//   page       TechDraw_PageDefault: its objects, the window's title, the undo step
//   view       TechDraw_View with plate selected: TaskProjGroup ("New View") widget by widget, OK, the view made
//   projgroup  TechDraw_ProjectionGroup from the Top camera, Right and Top ticked, OK: every item's Name, Label,
//              Direction and place
//   sections   TechDraw_SectionView on View with each arrow: the panel, then SectionNormal, Direction, XDirection,
//              Rotation, Label and place of each section
//   dims       the View from above, then each dimension command on the recording's selection (an edge clicked in the
//              page): Type, FormatSpec, X, Y, value and text, the undo step; TaskDimension's widgets
//   annotate   TechDraw_Annotation and TechDraw_Balloon (a click on the view)
//   tree       the page's rows; props, each object's property view against FreeCAD's rows
//   undo       Std_Undo takes the balloon back and Std_Redo brings it again
//   annot      the tools of the Add Vertices and Add Lines menus, the Centerlines toolbar and the eraser (ui/scripts/fctechdraw_annot.json):
//              each entry's state for a selection, the task panels' widgets and first values, what the tool makes, the undo step
//   hatch      TechDraw_GeometricHatch and TechDraw_Hatch (ui/scripts/fctechdraw_hatch.json): the wrong selections, the panels' widgets and
//              first values, what OK makes (the object, the drawn lines), the undo steps
//   more       the leader line, rich text, symbol, weld symbol, surface finish, image and clip tools (ui/scripts/fctechdraw_more.json): the wrong selections,
//              the panels' widgets, the clicks on the page, what each makes (properties, tree place), the undo steps, the property view's rows (with annot)
//   export     TechDraw_ExportPageSVG: the file's page size
// A difference prints as FAIL; the deliberate ones (PARITY.md, "TechDraw") as `known`. Exit 1 on a FAIL.
import { createRequire } from 'module'
import { spawn, spawnSync } from 'child_process'
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'fs'
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
const FC = JSON.parse(readFileSync(flag('fc', join(HERE, 'fctechdraw.json')), 'utf8'))
const ANNOT = JSON.parse(readFileSync(flag('annot', join(HERE, 'fctechdraw_annot.json')), 'utf8'))
const HATCH = JSON.parse(readFileSync(flag('hatch', join(HERE, 'fctechdraw_hatch.json')), 'utf8'))
const MORE = JSON.parse(readFileSync(flag('more', join(HERE, 'fctechdraw_more.json')), 'utf8'))
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
let pass = 0, fail = 0, known = 0
const ok = (what) => { pass++; if (args.includes('--verbose')) console.log(`  ok    ${what}`) }
const bad = (what, detail = '') => { fail++; console.log(`  FAIL  ${what}${detail ? `: ${detail}` : ''}`) }
let quiet = false
const note = (what) => { known++; if (!quiet) console.log(`  known ${what}`) }
const check = (cond, what, detail) => (cond ? ok(what) : bad(what, detail))
const same = (a, b, what) => check(JSON.stringify(a) === JSON.stringify(b), what, `\n        FreeCAD ${JSON.stringify(b)}\n        ours    ${JSON.stringify(a)}`)
const near = (a, b, tol = 1e-6) => Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((x, i) => Math.abs(x - b[i]) <= tol)
const ONLY = flag('only', '').split(',').filter(Boolean)
const want = (s) => !ONLY.length || ONLY.includes(s)
const clean = (t) => String(t ?? '').replace(/&(.)/g, '$1').replace(/…$/, '').trim()

// Commands that are greyed here on purpose (PARITY.md, "TechDraw"): everything the menus list that is not ported
const PORTED = new Set(['TechDraw_PageDefault', 'TechDraw_PageTemplate', 'TechDraw_RedrawPage', 'TechDraw_FillTemplateFields', 'TechDraw_ExportPageSVG',
  'TechDraw_ExportPageDXF', 'TechDraw_ExportPagePDF', 'TechDraw_View', 'TechDraw_ProjectionGroup', 'TechDraw_SectionView', 'TechDraw_SectionGroup',
  'TechDraw_Dimension', 'TechDraw_CompDimensionTools', 'TechDraw_LengthDimension', 'TechDraw_HorizontalDimension', 'TechDraw_VerticalDimension',
  'TechDraw_RadiusDimension', 'TechDraw_DiameterDimension', 'TechDraw_AngleDimension', 'TechDraw_3PtAngleDimension', 'TechDraw_Balloon',
  'TechDraw_Annotation', 'TechDraw_ToggleFrame', 'TechDraw_CosmeticVertex', 'TechDraw_CosmeticVertexGroup', 'TechDraw_Midpoints', 'TechDraw_Quadrants',
  'TechDraw_2PointCosmeticLine', 'TechDraw_CosmeticCircle', 'TechDraw_CenterLineGroup', 'TechDraw_FaceCenterLine', 'TechDraw_2LineCenterLine',
  'TechDraw_2PointCenterLine', 'TechDraw_CosmeticEraser', 'TechDraw_DecorateLine', 'TechDraw_Hatch', 'TechDraw_GeometricHatch',
  'TechDraw_LeaderLine', 'TechDraw_RichTextAnnotation', 'TechDraw_WeldSymbol', 'TechDraw_SurfaceFinishSymbols', 'TechDraw_Symbol', 'TechDraw_Image', 'TechDraw_ClipGroup'])

// ── a scratch workbench with the two parts ───────────────────────────────────────────────────────────────────────
const freePort = (from) => new Promise((res, rej) => {
  const tryPort = (p) => { if (p > from + 40) return rej(new Error('no free port')); const s = createServer(); s.once('error', () => tryPort(p + 1)); s.once('listening', () => s.close(() => res(p))); s.listen(p, '127.0.0.1') }
  tryPort(from)
})
const scratch = mkdtempSync(join(tmpdir(), 'cad-tdcheck-')), warmDir = mkdtempSync('/tmp/cat')
const ROOT = join(scratch, 'root'); mkdirSync(ROOT)
for (const d of ['runtime', 'macros']) mkdirSync(join(scratch, d))
const python = process.env.CAD_PYTHON || join(REPO, '.venv', 'bin', 'python')
const env = { ...process.env, CAD_WARM_DIR: warmDir, CAD_RUNTIME_DIR: join(scratch, 'runtime'), CAD_MACRO_DIR: join(scratch, 'macros'),
  CAD_PREFS: join(scratch, 'prefs.json'), PYTHONPATH: REPO, CAD_PYTHON: python, CAD_RENDER_BACKEND: 'numpy' }
delete env.CAD_PROJECTS
const SLUG = 'tc'
spawnSync(python, ['-m', 'cad_agent', '--projects', ROOT, 'init', SLUG, '--brief', 'techdrawcheck'], { env, cwd: REPO })
const part = (name) => {
  copyFileSync(join(REPO, 'tests', 'golden', 'techdraw', 'breps', `${name}.brep`), join(ROOT, SLUG, 'parts', `${name}.brep`))
  writeFileSync(join(ROOT, SLUG, 'parts', `${name}.py`), `"""${name}: the golden BREP (tests/golden/techdraw), the shape FreeCAD drew."""\nfrom pathlib import Path\nfrom build123d import import_brep\n\nMATERIAL = "al6061"\nPROCESS = "cnc"\nPARAMS = {}\n\n\ndef build(**p):\n    return import_brep(str(Path(__file__).with_suffix(".brep")))\n`)
}
part('plate'); part('bracket')
const port = await freePort(9011)
const server = spawn(python, ['-c', `import sys; from pathlib import Path; from cad_agent import serve; serve.run([Path(sys.argv[1])], host="127.0.0.1", port=${port})`, ROOT],
  { env, cwd: REPO, stdio: ['ignore', 'pipe', 'pipe'] })
await new Promise((res, rej) => {
  const t = setTimeout(() => rej(new Error('the scratch workbench did not start')), 60000)
  server.stdout.on('data', (d) => { if (/workbench: http/.test(String(d))) { clearTimeout(t); res() } })
  server.on('exit', (c) => rej(new Error(`the scratch workbench exited with ${c}`)))
})
const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] })
const page = await browser.newPage({ viewport: { width: 1400, height: 950 } })
page.on('pageerror', (e) => bad('page error', e.message))
const st = (expr) => page.evaluate(expr)
const until = async (expr, what, ms = 90000) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { if (await st(expr)) return true; await sleep(250) } bad(`timed out waiting: ${what}`); return false }
const runCmd = (c) => st(`cadui.getCommand(${JSON.stringify(c)})?.run([])`)
const td = () => st('cadui.td.state()')
const objs = async () => (await td()).docs.Page?.objects ?? []
const obj = async (n) => (await objs()).find((o) => o.name === n)
const undoHead = () => st('cadui.getState().undo[0]?.name ?? null')
const idle = () => until('!cadui.getState().busy.length', 'the server idle', 120000)
const select = (refs) => st(`cadui.td.select(null); ${refs.map((r, i) => `cadui.td.select(${JSON.stringify(r)}, ${i > 0})`).join(';')}`)

/** A menu's entries, FreeCAD's and ours side by side by command (texts, then greyed or not). */
function compareMenu(fc, ours, what) {
  const f = fc.filter((e) => !e.sep), o = ours.filter((e) => !e.sep)
  same(o.map((e) => clean(e.text)), f.map((e) => clean(e.text)), `${what}: the entries`)
  for (const e of f) {
    const m = o.find((x) => clean(x.text) === clean(e.text))
    if (!m) continue
    if (e.menu && m.menu) { compareMenu(e.menu, m.menu, `${what} > ${clean(e.text)}`); continue }
    if (m.enabled === e.enabled) { ok(`${what}: ${clean(e.text)}`); continue }
    if (!PORTED.has(m.cmd)) note(`${what}: ${clean(e.text)} is not ported (greyed; FreeCAD's is ${e.enabled ? 'active' : 'greyed'})`)
    else bad(`${what}: ${clean(e.text)} ${e.enabled ? 'active' : 'greyed'}`, `ours ${m.enabled ? 'active' : 'greyed'}`)
  }
}
const fcMenu = (m) => m['Tech&Draw'] ?? m.TechDraw ?? Object.values(m).find(Array.isArray)
function compareToolbars(fc, ours, what) {
  same(ours.map((t) => t.title), fc.map((t) => t.title), `${what}: the toolbars`)
  for (const t of fc) {
    const o = ours.find((x) => x.title === t.title)
    if (!o) continue
    same(o.buttons.filter((b) => !b.sep).map((b) => b.cmd), t.buttons.filter((b) => !b.sep).map((b) => b.name), `${what}: ${t.title}'s buttons`)
  }
}
/** The open panel's widgets by their Qt object names, FreeCAD's (those it shows) and ours (data-qf, not hidden). */
const ourPanel = () => st(`[...document.querySelectorAll('.tasks [data-qf]:not(.qf-line)')].map((e) => e.getAttribute('data-qf')).filter((n) => n && !n.includes('::'))`)
const fcPanel = (p) => (Array.isArray(p[0]) ? p.flat() : p).map((w) => w.name).filter((n) => n && n !== 'qt_spinbox_lineedit' && !n.startsWith('qt_'))
const sorted = (a) => [...new Set(a)].sort()
const made = (k) => { const m = FC[k]?.made ?? []; return Array.isArray(m) ? m : [m] }

try {
  await page.goto(`http://127.0.0.1:${port}/next/#${SLUG}`)
  await until(`window.cadui && cadui.getState().slug === "${SLUG}" && cadui.getState().scene?.bodies.length >= 2`, 'the page and its scene')
  await st('cadui.setState({ workbench: "techdraw" })')
  await sleep(500)
  if (want('menus')) {
    console.log('menus')
    const bar = await st(`[...document.querySelectorAll('.menubar > *')].map((e) => e.textContent.trim()).filter(Boolean)`)
    const i = bar.indexOf('TechDraw'), w = bar.indexOf('Windows')
    check(i >= 0 && i === w - 1, 'the menu bar puts TechDraw before Windows', JSON.stringify(bar))
    compareMenu(fcMenu(FC.menus_nopage), (await st('cadui.techdraw()')).menu, 'TechDraw menu, no page')
    compareToolbars(FC.toolbars_nopage, (await st('cadui.techdraw()')).toolbars, 'toolbars, no page')
  }
  // ── TechDraw_PageDefault ──
  await runCmd('TechDraw_PageDefault')
  await until('cadui.td.state().pages.includes("Page")', 'the page')
  if (want('page')) {
    console.log('page')
    const os = await objs()
    same(os.map((o) => [o.name, o.label ?? o.name, o.type_id]), made('page_default').map((o) => [o.Name, o.Label, o.TypeId]), 'New Page: the objects')
    same(await undoHead(), FC.page_default.undo.head[0], 'New Page: the undo step')
    const tabs = await st(`[...document.querySelectorAll('.dv-tab')].map((t) => t.textContent.trim())`)
    check(tabs.includes('Page'), 'New Page: the page\'s window', JSON.stringify(tabs))
  }
  if (want('menus')) {
    compareMenu(fcMenu(FC.menus_page), (await st('cadui.techdraw()')).menu, 'TechDraw menu, a page')
    compareToolbars(FC.toolbars_page, (await st('cadui.techdraw()')).toolbars, 'toolbars, a page')
  }
  // ── TechDraw_View ──
  await st('cadui.setState({ selected: ["plate"] })')
  await runCmd('TechDraw_View')
  await until('cadui.getState().task?.kind === "techdraw"', 'TaskProjGroup')
  await sleep(800)
  if (want('view')) {
    console.log('view')
    same(sorted(await ourPanel()), sorted(fcPanel(FC.view_panel)), 'New View: TaskProjGroup\'s widgets')
    const title = await st(`document.querySelector('.tasks .tbox-head span')?.textContent`)
    same(title, 'New View', 'New View: the panel\'s title')
  }
  await page.click('.tasks .tbuttons .qbtn.default'); await idle(); await sleep(500)
  if (want('view')) {
    const o = await obj('View'), f = made('view_made')[0]
    same([o.kind, o.label ?? o.name], [f.TypeId.split('::')[1], f.Label], 'New View: the object')
    check(near(o.direction, f.Direction) && near(o.x_direction, f.XDirection) && o.x === f.X && o.y === f.Y, 'New View: Direction, XDirection, X, Y',
      JSON.stringify([o.direction, o.x_direction, o.x, o.y]))
    same(await undoHead(), FC.view_made.undo.head[0], 'New View: the undo step')
  }
  if (want('view')) {
    // a click on an edge in the page selects it (QGIEdge), as the recording's selection of Edge2; and a click beside the
    // lines, the view (its frame)
    const box = await page.locator(`[data-view="View"][data-sub="Edge2"]`).first().boundingBox()
    await page.mouse.click(box.x + box.width * 0.25, box.y + box.height / 2)
    await sleep(300)
    same((await td()).sel, ['Page/View.Edge2'], 'a click on Edge2 selects it')
    await page.mouse.click(box.x + box.width * 0.25, box.y - 12)
    await sleep(300)
    same((await td()).sel, ['Page/View'], 'a click inside the view\'s frame selects the view')
  }
  // ── TechDraw_ProjectionGroup, from the Top camera as the recording's (its anchor's Direction) ──
  await runCmd('Std_ViewTop'); await sleep(1200)
  await st('cadui.setState({ selected: ["plate"] })')
  await runCmd('TechDraw_ProjectionGroup')
  await until('cadui.getState().task?.other?.startsWith("projgroup:ProjGroup")', 'the projection group\'s panel')
  await sleep(800)
  if (want('projgroup')) {
    console.log('projgroup')
    same(sorted(await ourPanel()), sorted(fcPanel(FC.projgroup_panel)), 'Projection Group: TaskProjGroup\'s widgets')
  }
  for (const box of ['chkView3', 'chkView8']) { await page.click(`[data-qf="${box}"] input`); await sleep(1500) }
  await page.click('.tasks .tbuttons .qbtn.default'); await idle(); await sleep(800)
  if (want('projgroup')) {
    for (const f of made('projgroup_made')) {
      const o = await obj(f.Name)
      if (!o) { bad(`Projection Group: ${f.Name}`, 'not made'); continue }
      check((o.label ?? o.name) === f.Label, `Projection Group: ${f.Name}'s Label`, `${o.label} vs ${f.Label}`)
      if (f.Direction) check(near(o.direction, f.Direction, 1e-6), `Projection Group: ${f.Name}'s Direction`, `${o.direction} vs ${f.Direction}`)
      const pos = (await td()).docs.Page.result.views[f.Name]
      const g = (await td()).docs.Page.result.views.ProjGroup
      if (pos && f.TypeId.endsWith('Item')) check(Math.abs(pos.x - g.x - f.X) < 1e-6 && Math.abs(pos.y - g.y - f.Y) < 1e-6, `Projection Group: ${f.Name}'s X, Y`, `${pos.x - g.x}, ${pos.y - g.y} vs ${f.X}, ${f.Y}`)
    }
    same(await undoHead(), FC.projgroup_made.undo.head[0], 'Projection Group: the undo step')
  }
  // ── TechDraw_SectionView, each arrow ──
  if (want('sections')) console.log('sections')
  for (const [key, arrow, symbol] of [['section_made', 'pbRight', 'A'], ['section_up_made', 'pbUp', ''], ['section_left_made', 'pbLeft', ''], ['section_down_made', 'pbDown', '']]) {
    await select(['Page/View'])
    await runCmd('TechDraw_SectionView')
    await until('cadui.getState().task?.other?.startsWith("section:")', 'TaskSectionView')
    await sleep(600)
    if (want('sections') && key === 'section_made') {
      // CompassWidget and VectorEditWidget, which the panel's code adds to its layouts, are not ported (the four arrows are)
      const COMPASS = ['compassControlLabel', 'dsbAngle', 'pbCCWAdvance', 'pbCWAdvance', 'leVectorDisplay', 'lvectorName', 'tbExpand']
      same(sorted(await ourPanel()), sorted(fcPanel(FC.section_panel).filter((n) => !COMPASS.includes(n))), 'Section View: TaskSectionView\'s widgets')
      note('Section View: the compass and the view direction box (CompassWidget, VectorEditWidget) are not ported')
    }
    if (symbol) await page.fill('[data-qf="leSymbol"]', symbol)
    await page.click(`[data-qf="${arrow}"]`); await sleep(1500)
    await page.click('.tasks .tbuttons .qbtn.default'); await idle(); await sleep(500)
    if (!want('sections')) continue
    const f = made(key)[0], o = await obj(f.Name)
    if (!o) { bad(`${arrow}: ${f.Name}`, 'not made'); continue }
    check(near(o.section_normal, f.SectionNormal, 1e-9) && near(o.direction, f.Direction, 1e-9) && near(o.x_direction, f.XDirection, 1e-9),
      `${arrow}: SectionNormal, Direction, XDirection`, JSON.stringify([o.section_normal, o.direction, o.x_direction]))
    same([o.rotation, o.label, o.section_symbol, o.section_direction, o.x, o.y, o.caption], [f.Rotation, f.Label, f.SectionSymbol, f.SectionDirection, f.X, f.Y, f.Caption],
      `${arrow}: Rotation, Label, SectionSymbol, SectionDirection, X, Y, Caption`)
    const head = await undoHead()
    if (head === f.undo?.head?.[0]) ok(`${arrow}: the undo step`)
    else note(`${arrow}: one undo step "${head}" (FreeCAD commits two, "Create Section View" then "Edit Section View")`)
  }
  // ── the dimensions, on the View from above ──
  await st(`cadui.td.apply("Page", [{ op: "set", name: "View", props: { direction: ${JSON.stringify(FC.view_top.Direction)} } }], "Edit View.Direction")`)
  await idle(); await sleep(800)
  if (want('menus')) {
    await select(['Page/View.Edge2'])
    compareMenu(fcMenu(FC.menus_edge_selected), (await st('cadui.techdraw()')).menu, 'TechDraw menu, an edge selected')
  }
  if (want('dims')) console.log('dims')
  const DIMS = { dim_horizontal: 'TechDraw_HorizontalDimension', dim_vertical: 'TechDraw_VerticalDimension', dim_length: 'TechDraw_LengthDimension',
    dim_radius: 'TechDraw_RadiusDimension', dim_diameter: 'TechDraw_DiameterDimension', dim_two_vertex: 'TechDraw_LengthDimension' }
  for (const [key, cmd] of Object.entries(DIMS)) {
    const f = FC[key].dimensions[0]
    const refs = f.References2D.flatMap(([v, subs]) => subs.map((s) => `Page/${v}.${s}`))
    await select(refs)
    await runCmd(cmd); await idle(); await sleep(600)
    if (!want('dims')) continue
    const o = await obj(f.Name), m = (await td()).docs.Page.result.dimensions[f.Name]
    if (!o || !m) { bad(`${key}: ${f.Name}`, 'not made'); continue }
    same([o.dim_type, o.format_spec, o.measure_type], [f.Type, f.FormatSpec, f.MeasureType], `${key}: Type, FormatSpec, MeasureType`)
    check(Math.abs(o.x - f.X) < 1e-6 && Math.abs(o.y - f.Y) < 1e-6, `${key}: X, Y`, `${o.x}, ${o.y} vs ${f.X}, ${f.Y}`)
    check(Math.abs(m.value - f.getRawValue) < 1e-9 && m.unaltered === f.getText, `${key}: the value and getText`, `${m.value} ${m.unaltered}`)
    same(await undoHead(), FC[key].undo.head[0], `${key}: the undo step`)
  }
  if (want('dims')) {
    await page.locator('text[data-dim="Dimension"]').first().dblclick()   // ViewProviderDimension::doubleClicked
    await sleep(800)
    same(sorted(await ourPanel()), sorted(fcPanel(FC.dimension_panel.panel ?? FC.dimension_panel)), 'TaskDimension\'s widgets')
    await st('cadui.setState({ task: null })')
    note('Drag Dimension: FreeCAD commits a "Drag Dimension" step when the next command runs; nothing moves here')
  }
  // ── the bracket's view and its angle ──
  await st('cadui.setState({ selected: ["bracket"] })')
  await runCmd('TechDraw_View'); await until('cadui.getState().task?.kind === "techdraw"', 'TaskProjGroup')
  await page.click('.tasks .tbuttons .qbtn.default'); await idle(); await sleep(500)
  {
    const f = FC.dim_angle.dimensions[0]
    await select(f.References2D.flatMap(([v, subs]) => subs.map((s) => `Page/${v}.${s}`)))
    await runCmd('TechDraw_AngleDimension'); await idle(); await sleep(500)
    const o = await obj(f.Name), m = (await td()).docs.Page.result.dimensions[f.Name]
    if (want('dims')) {
      if (!o || !m) bad('dim_angle', 'not made')
      else {
        same([o.dim_type, o.format_spec, o.x, o.y], [f.Type, f.FormatSpec, f.X, f.Y], 'dim_angle: Type, FormatSpec, X, Y')
        check(Math.abs(m.value - f.getRawValue) < 1e-9 && m.unaltered === f.getText, 'dim_angle: the value and getText', `${m.value} ${m.unaltered}`)
      }
    }
  }
  // ── TechDraw_Annotation, TechDraw_Balloon ──
  await select([])
  await runCmd('TechDraw_Annotation'); await idle(); await sleep(500)
  if (want('annotate')) {
    console.log('annotate')
    const f = made('annotation_made')[0], o = await obj(f.Name)
    same(o && [o.name, o.label ?? o.name, o.text, o.x, o.y], [f.Name, f.Label, f.Text, f.X, f.Y], 'Annotation: Name, Label, Text, X, Y')
    same(await undoHead(), FC.annotation_made.undo.head[0], 'Annotation: the undo step')
  }
  await select(['Page/View'])
  await runCmd('TechDraw_Balloon'); await sleep(300)
  {
    // the recording's click: page point (163.5, 120), 15 mm right of and above the view's centre
    const r = await st(`(() => { const s = document.querySelector('.td-svg svg').getBoundingClientRect(); return [s.left, s.top, s.width, s.height] })()`)
    await page.mouse.click(r[0] + 163.5 / 297 * r[2], r[1] + (210 - 120) / 210 * r[3]); await idle(); await sleep(600)
  }
  if (want('annotate')) {
    const f = made('balloon_made')[0], o = await obj(f.Name)
    same(o && [o.name, o.source_view, o.text, o.bubble_shape, o.end_type], [f.Name, f.SourceView, f.Text, f.BubbleShape, f.EndType],
      'Balloon: Name, SourceView, Text, BubbleShape, EndType')
    same(await undoHead(), FC.balloon_made.undo.head[0], 'Balloon: the undo step')
  }
  // ── the tree and the property view ──
  if (want('tree')) {
    console.log('tree')
    const fcRows = FC.tree.filter((r) => r.depth >= 1).filter((r, i, a) => { const p = a.findIndex((x) => x.text === 'Page'); return a.indexOf(r) >= p })
    const pageAt = fcRows.findIndex((r) => r.text === 'Page')
    const fcPage = fcRows.slice(pageAt).filter((r, i, a) => i === 0 || r.depth > 1).map((r) => [r.text, r.depth - 1])
    const ours = (await td()).docs.Page.tree.map((r) => [r.label, r.depth])
    same(ours, fcPage, 'the page\'s rows')
  }
  if (want('props')) {
    console.log('props')
    for (const [name, key] of [['Page', 'props_Page'], ['Template', 'props_Template'], ['View', 'props_View'], ['ProjGroup', 'props_ProjGroup'],
      ['SectionView', 'props_SectionView'], ['Dimension', 'props_Dimension'], ['Annotation', 'props_Annotation']]) {
      await select([`Page/${name}`]); await sleep(300)
      const rows = await st(`[...document.querySelectorAll('.props .pgroup, .props .prow .pk')].map((e) => (e.classList.contains('pgroup') ? '#' : '') + e.textContent.trim())`)
      const data = FC[key].data[0] && Array.isArray(FC[key].data[0]) ? FC[key].data[0] : FC[key].data
      same(rows, data.map((r) => (r.depth === 0 ? '#' : '') + r.name), `${name}'s property view`)
    }
  }
  // ── Std_Undo, Std_Redo ──
  if (want('undo')) {
    console.log('undo')
    await runCmd('Std_Undo'); await until('!cadui.td.state().docs.Page.objects.some((o) => o.name === "Balloon")', 'the balloon taken back', 30000)
    check(!(await obj('Balloon')), 'Std_Undo takes the balloon back')
    await runCmd('Std_Redo'); await until('cadui.td.state().docs.Page.objects.some((o) => o.name === "Balloon")', 'the balloon again', 30000)
    check(!!(await obj('Balloon')), 'Std_Redo brings it again')
  }
  // ── the annotation tools, on the View from above (ui/scripts/fctechdraw_annot.json) ──
  if (want('annot')) try {
    console.log('annot')
    const fcText = (panel, name) => { for (const tv of panel) for (const w of tv) if (w.name === name) return w.text }
    const ourText = (name) => st(`(() => { const e = document.querySelector('.tasks [data-qf="${name}"]'); return !e ? undefined : e.matches('input') ? e.value : e.querySelector('input')?.value ?? e.textContent })()`)
    const fillQ = async (name, text) => { const sel = `.tasks [data-qf="${name}"] input`; await page.fill(sel, text); await page.locator(sel).evaluate((e) => e.blur()); await sleep(250) }
    const okTask = async () => {
      try { await page.click('.tasks .tbuttons .qbtn.default', { timeout: 8000 }) } catch (e) { console.log(await st(`document.querySelector('.tasks')?.outerHTML.slice(0, 1500) ?? document.body.innerText.slice(0, 600)`)); throw e }
      await idle(); await sleep(500)
    }
    const cancelTask = async () => { await page.click('.tasks .tbuttons .qbtn:not(.default)'); await idle(); await sleep(500) }
    const msgText = async () => { await until('!!document.querySelector(".msgbox")', 'a message', 8000); const t = await st('document.querySelector(".msgbox-text")?.textContent'); await page.click('.msgbox-buttons button'); await sleep(200); return t }
    const undoNames = () => st('cadui.getState().undo.slice(0, 5).map((u) => u.name)')
    const open = async (cmd, refs, kind) => {
      await select(refs)
      await runCmd(cmd)
      await until(`cadui.getState().task?.other?.startsWith("${kind}:")`, `${cmd}'s panel`)
      await sleep(600)
    }
    const geometry = async (rec, what) => {
      const v = (await td()).docs.Page.result.views.View
      const fe = rec.edges, fv = rec.vertices
      if (v.edges.length !== fe.length || v.vertices.length !== fv.length) { bad(`${what}: the geometry`, `${v.edges.length} edges and ${v.vertices.length} vertices, FreeCAD ${fe.length} and ${fv.length}`); return }
      const s = v.scale
      let why = ''
      v.edges.forEach((e, i) => {
        if (why) return
        if (!near([e.start[0] / s, -e.start[1] / s], fe[i].start.slice(0, 2), 1e-4) || !near([e.end[0] / s, -e.end[1] / s], fe[i].end.slice(0, 2), 1e-4))
          why = `Edge${i}: ours ${JSON.stringify([e.start, e.end])} FreeCAD ${JSON.stringify([fe[i].start, fe[i].end])}`
      })
      v.vertices.forEach((p, i) => { if (!why && !near([p.x / s, -p.y / s], fv[i].slice(0, 2), 1e-4)) why = `Vertex${i}: ours ${JSON.stringify([p.x, p.y])} FreeCAD ${JSON.stringify(fv[i])}` })
      check(!why, `${what}: the edges and vertices, in FreeCAD's numbering`, why)
    }
    const panelNames = async (key, what) => same(sorted(await ourPanel()), sorted(fcPanel(ANNOT[key].panel)), `${what}: the panel's widgets`)
    const firstValues = async (key, names, what) => {
      for (const n of names) same(await ourText(n), fcText(ANNOT[key].panel, n), `${what}: ${n}`)
    }
    const stepIs = async (key, what, ours) => {
      const head = await undoHead(), f = ANNOT[key].undo.head[0]
      if (f === undefined) note(`${what}: no undo step in FreeCAD (a property edit outside a transaction); here "${head}"`)
      else same(head, f, `${what}: the undo step`)
      void ours
    }
    const NAMES = ['Hatching', 'Centerlines/Threading', 'Annotations', 'Add Lines', 'Add Vertices', 'Remove Cosmetic Object']
    // the menus and toolbars for each selection
    for (const [key, refs] of [['states_none', []], ['states_view', ['Page/View']], ['states_edge', ['Page/View.Edge2']], ['states_two_edges', ['Page/View.Edge0', 'Page/View.Edge4']],
      ['states_two_vertices', ['Page/View.Vertex1', 'Page/View.Vertex6']], ['states_face', ['Page/View.Face0']]]) {
      await select(refs)
      quiet = key !== 'states_none'
      const t = await st('cadui.techdraw()')
      compareMenu(ANNOT[key].menu, t.menu.filter((e) => !e.sep && NAMES.includes(clean(e.text))), `${key} (${refs.join(', ') || 'nothing'})`)
      compareToolbars(ANNOT[key].toolbars, t.toolbars.filter((x) => ANNOT[key].toolbars.some((y) => y.title === x.title)), key)
      quiet = false
    }
    // Cosmetic Vertex
    await open('TechDraw_CosmeticVertex', ['Page/View'], 'cosvertex')
    await panelNames('cosvertex', 'Cosmetic Vertex')
    same(await st(`document.querySelector('.tasks .tbox-head span')?.textContent`), 'New Cosmetic Vertex', 'Cosmetic Vertex: the panel\'s title')
    await firstValues('cosvertex', ['dsbX', 'dsbY'], 'Cosmetic Vertex')
    await fillQ('dsbX', '5 mm'); await fillQ('dsbY', '6 mm')
    await okTask()
    await geometry(ANNOT.cosvertex.view, 'Cosmetic Vertex')
    await stepIs('cosvertex', 'Cosmetic Vertex')
    await open('TechDraw_CosmeticVertex', ['Page/View'], 'cosvertex')
    await cancelTask()
    check(!(await st('cadui.getState().task')), 'Cosmetic Vertex: Cancel closes the panel')
    // Midpoint and Quadrant Vertices
    await select(['Page/View.Edge2']); await runCmd('TechDraw_Midpoints'); await idle(); await sleep(500)
    await geometry(ANNOT.midpoints.view, 'Midpoint Vertices'); await stepIs('midpoints', 'Midpoint Vertices')
    await select(['Page/View.Edge5']); await runCmd('TechDraw_Quadrants'); await idle(); await sleep(500)
    await geometry(ANNOT.quadrants.view, 'Quadrant Vertices'); await stepIs('quadrants', 'Quadrant Vertices')
    await select(['Page/View']); await runCmd('TechDraw_Midpoints')
    same(await msgText(), ANNOT.midpoints_nothing.dialogs[0].text, 'Midpoint Vertices: nothing selected')
    // Cosmetic Line through 2 points
    await open('TechDraw_2PointCosmeticLine', ['Page/View.Vertex1', 'Page/View.Vertex6'], 'cosline')
    await panelNames('cosline', 'Cosmetic Line')
    await firstValues('cosline', ['qsbx1', 'qsby1', 'qsbz1', 'qsbx2', 'qsby2', 'qsbz2'], 'Cosmetic Line')
    await fillQ('qsbx2', '12 mm'); await fillQ('qsby2', '9 mm')
    await okTask()
    await geometry(ANNOT.cosline.view, 'Cosmetic Line'); await stepIs('cosline', 'Cosmetic Line')
    await select(['Page/View.Vertex1']); await runCmd('TechDraw_2PointCosmeticLine')
    same(await msgText(), ANNOT.cosline_wrong.dialogs[0].text, 'Cosmetic Line: one vertex')
    await open('TechDraw_2PointCosmeticLine', ['Page/View.Edge6'], 'cosline')
    same(await st(`document.querySelector('.tasks .tbox-head span')?.textContent`), 'Edit Cosmetic Line', 'Cosmetic Line: the edit panel\'s title')
    await firstValues('cosline_edit', ['qsbx1', 'qsby1', 'qsbx2', 'qsby2'], 'Cosmetic Line, edit')
    await fillQ('qsby1', '-3 mm')
    await okTask()
    await geometry(ANNOT.cosline_edit.view, 'Cosmetic Line, edit'); await stepIs('cosline_edit', 'Cosmetic Line, edit')
    // Cosmetic Circle
    await open('TechDraw_CosmeticCircle', ['Page/View.Vertex6', 'Page/View.Vertex8'], 'coscircle')
    await panelNames('coscircle', 'Cosmetic Circle')
    await firstValues('coscircle', ['qsbCenterX', 'qsbCenterY', 'qsbCenterZ', 'qsbRadius', 'qsbStartAngle', 'qsbEndAngle'], 'Cosmetic Circle')
    await fillQ('qsbRadius', '3 mm')
    await okTask()
    await geometry(ANNOT.coscircle.view, 'Cosmetic Circle'); await stepIs('coscircle', 'Cosmetic Circle')
    await open('TechDraw_CosmeticCircle', ['Page/View.Vertex1', 'Page/View.Vertex4'], 'coscircle')
    await page.click('[data-qf="rbArc"] input'); await sleep(300)
    await fillQ('qsbStartAngle', '10'); await fillQ('qsbEndAngle', '100')
    await okTask()
    await geometry(ANNOT.coscircle_arc.view, 'Cosmetic Arc')
    await open('TechDraw_CosmeticCircle', ['Page/View.Edge8'], 'coscircle')
    same(await st(`document.querySelector('.tasks .tbox-head span')?.textContent`), 'Edit Cosmetic Circle', 'Cosmetic Circle: the edit panel\'s title')
    await firstValues('coscircle_edit', ['qsbCenterX', 'qsbCenterY', 'qsbRadius', 'qsbStartAngle', 'qsbEndAngle'], 'Cosmetic Circle, edit')
    await fillQ('qsbRadius', '6 mm')
    await okTask()
    await geometry(ANNOT.coscircle_edit.view, 'Cosmetic Circle, edit')
    // Centerlines: made when the panel opens, changed live, one undo step
    {
      const n0 = await undoNames()
      await open('TechDraw_2LineCenterLine', ['Page/View.Edge0', 'Page/View.Edge4'], 'centerline')
      await panelNames('cl2lines', 'Centerline Between 2 Lines')
      same(await undoHead(), 'Create Centerline', 'Centerline Between 2 Lines: made when the panel opens')
      await firstValues('cl2lines', ['qsbHorizShift', 'qsbVertShift', 'qsbExtend'], 'Centerline Between 2 Lines')
      same(await st(`document.querySelector('.tasks [data-qf="cboxStyle"] .combo-label')?.textContent`), 'Symmetry', 'Centerline Between 2 Lines: the style box opens on Symmetry')
      await fillQ('qsbVertShift', '1.5 mm'); await fillQ('qsbHorizShift', '-2 mm'); await fillQ('qsbRotate', '10'); await fillQ('qsbExtend', '2 mm'); await fillQ('dsbWeight', '0.7 mm')
      await okTask()
      await geometry(ANNOT.cl2lines.view, 'Centerline Between 2 Lines')
      same((await undoNames()).slice(1), n0.slice(0, 4), 'Centerline Between 2 Lines: one undo step for the line and its changes')
      same(await undoHead(), ANNOT.cl2lines.undo.head[0], 'Centerline Between 2 Lines: the undo step')
      await open('TechDraw_2PointCenterLine', ['Page/View.Vertex3', 'Page/View.Vertex8'], 'centerline')
      await okTask()
      await geometry(ANNOT.cl2points.view, 'Centerline Between 2 Points')
      // Cancel takes the new line back
      const n1 = await undoNames()
      await open('TechDraw_2LineCenterLine', ['Page/View.Edge2', 'Page/View.Edge3'], 'centerline')
      same(await st(`document.querySelector('.tasks [data-qf="rbHorizontal"] input')?.checked`), true, 'Centerline Between 2 Lines: two horizontal lines make it horizontal (checkPathologicalEdges)')
      await fillQ('qsbExtend', '2 mm')
      await cancelTask(); await sleep(2500)
      await geometry(ANNOT.cl2lines_cancel.view, 'Centerline Between 2 Lines, Cancel')
      same((await undoNames()).slice(0, 4), n1.slice(0, 4), 'Centerline Between 2 Lines, Cancel: no step is left')
      await select(['Page/View.Edge2']); await runCmd('TechDraw_2LineCenterLine')
      same(await msgText(), ANNOT.cl2lines_wrong.dialogs[0].text, 'Centerline Between 2 Lines: one line that is not a centerline')
      await open('TechDraw_FaceCenterLine', ['Page/View.Face0'], 'centerline')
      await panelNames('clface', 'Centerline on Face')
      same(await st(`document.querySelector('.tasks [data-qf="rbAligned"] input')?.disabled`), true, 'Centerline on Face: Aligned is off')
      await okTask()
      await geometry(ANNOT.clface.view, 'Centerline on Face')
      await open('TechDraw_FaceCenterLine', ['Page/View.Face1'], 'centerline')
      await okTask()
      await geometry(ANNOT.clface_hole.view, 'Centerline on Face, the hole')
      await open('TechDraw_2LineCenterLine', ['Page/View.Edge9'], 'centerline')
      same(await st(`document.querySelector('.tasks .tbox-head span')?.textContent`), 'Edit Centerline', 'Centerline: the edit panel\'s title')
      await firstValues('cl_edit_existing', ['qsbHorizShift', 'qsbVertShift', 'qsbRotate', 'qsbExtend'], 'Centerline, edit')
      note('Centerline, edit: FreeCAD\'s style box shows Format.Style (Hidden), not the line number the panel set (Symmetry); this shows the line number')
      await cancelTask()
    }
    // a face is picked by a click inside it (QGIFace): a point of the plate where a face is on top
    {
      const at = await st(`(() => { const f = document.querySelector('[data-view="View"][data-sub="Face0"]'); const b = f.getBoundingClientRect()
        for (let i = 1; i < 30; i++) for (let j = 1; j < 30; j++) { const x = b.left + b.width * i / 30, y = b.top + b.height * j / 30
          const e = document.elementFromPoint(x, y); const sub = e?.getAttribute('data-sub'); if (/^Face/.test(sub ?? '')) return [x, y, sub, e.getAttribute('data-view')] }
        return null })()`)
      check(!!at, 'a point of the view where a face is on top')
      if (at) { await page.mouse.click(at[0], at[1]); await sleep(300); same((await td()).sel, [`Page/${at[3]}.${at[2]}`], 'a click inside a face picks it') }
    }
    // Line Decoration
    await open('TechDraw_DecorateLine', ['Page/View.Edge0', 'Page/View.Edge1'], 'linedecor')
    await panelNames('decorate_hlr', 'Edit Line Appearance')
    await firstValues('decorate_hlr', ['dsb_Weight', 'le_Lines'], 'Edit Line Appearance')
    same(await st(`document.querySelector('.tasks [data-qf="cb_Style"] .combo-label')?.textContent`), 'Hidden', 'Edit Line Appearance: the style box opens on Hidden')
    await page.click('.tasks [data-qf="cb_Style"]'); await page.locator('.combo-popup .combo-item', { hasText: /^Center$/ }).first().click(); await sleep(300); await fillQ('dsb_Weight', '0.9 mm'); await page.click('.tasks [data-qf="cb_Visible"] input'); await sleep(300)
    await okTask()
    await until('(cadui.td.state().docs.Page.objects.find((o) => o.name === "View")?.geom_formats ?? []).length === 2', 'the GeomFormats', 15000)
    check(((await obj('View')).geom_formats ?? []).length === 2, 'Edit Line Appearance: a GeomFormat for each HLR edge', JSON.stringify((await obj('View')).geom_formats))
    await select(['Page/View']); await runCmd('TechDraw_DecorateLine')
    same(await msgText(), ANNOT.decorate_view_only.dialogs[0].text, 'Edit Line Appearance: a view and no lines')
    // the eraser
    for (const [key, ref] of [['edge', 'Page/View.Edge6'], ['centerline', 'Page/View.Edge8'], ['vertex', 'Page/View.Vertex9'], ['hlr_edge', 'Page/View.Edge0']]) {
      await select([ref]); await runCmd('TechDraw_CosmeticEraser'); await idle(); await sleep(500)
      await geometry(ANNOT.eraser[key].view, `Remove Cosmetic Object (${key})`)
    }
    await select([]); await runCmd('TechDraw_CosmeticEraser')
    same(await msgText(), 'Nothing selected', 'Remove Cosmetic Object: nothing selected')
    note('Edit Line Appearance and Remove Cosmetic Object make no undo step in FreeCAD (no transaction is open); each is a step here')
    if (want('annot') || want('hatch')) await hatchChecks()
  } catch (e) { bad('the annot part stopped', String(e.message).split('\n')[0]) }
  // ── hatching (ui/scripts/fctechdraw_hatch.json) ──
  async function hatchChecks() {
    console.log('hatch')
    const fcText = (panel, name) => { for (const tv of panel) for (const w of tv) if (w.name === name) return w.text ?? w.current }
    const ourText = (name) => st(`(() => { const e = document.querySelector('.tasks [data-qf="${name}"]'); return !e ? undefined : e.matches('input') ? e.value : e.querySelector('.combo-label')?.textContent ?? e.querySelector('input')?.value ?? e.textContent })()`)
    const okTask = async () => { await page.click('.tasks .tbuttons .qbtn.default', { timeout: 8000 }); await idle(); await sleep(500) }
    const made = (name) => until(`cadui.td.state().docs.Page.objects.some((o) => o.name === "${name}")`, `${name} in the page`, 20000)
    const msgText = async () => { await until('!!document.querySelector(".msgbox")', 'a message', 8000); const t = await st('document.querySelector(".msgbox-text")?.textContent'); await page.click('.msgbox-buttons button'); await sleep(200); return t }
    const open = async (cmd, refs, kind) => { await select(refs); await runCmd(cmd); await until(`cadui.getState().task?.other?.startsWith("${kind}:")`, `${cmd}'s panel`); await sleep(600) }
    await select([]); await runCmd('TechDraw_GeometricHatch')
    same(await msgText(), HATCH.wrong_nothing.dialogs[0].text, 'Geometric Hatch: nothing selected')
    await select(['Page/View']); await runCmd('TechDraw_Hatch')
    same(await msgText(), HATCH.wrong_view_only.dialogs[0].text, 'Image Hatch: a view and no face')
    await select(['Page/View.Edge2']); await runCmd('TechDraw_GeometricHatch')
    same(await msgText(), HATCH.wrong_edge.dialogs[0].text, 'Geometric Hatch: an edge')
    // the geometric hatch
    await open('TechDraw_GeometricHatch', ['Page/View.Face0'], 'geomhatch')
    for (const n of ['cbName', 'sbScale', 'sbWeight', 'dsbRotation', 'dsbOffsetX', 'dsbOffsetY'])
      same(await ourText(n), n === 'cbName' ? 'Diamond' : fcText(HATCH.geomhatch.panel, n), `Geometric Hatch: ${n}`)
    same(await st(`document.querySelector('.tasks .tbox-head span')?.textContent`), 'Geometric Hatch', 'Geometric Hatch: the panel title')
    await okTask()
    await made('GeomHatch'); await sleep(500)
    const g = (await obj('GeomHatch'))
    check(g?.name_pattern === 'Diamond' && g.faces?.[0] === 'Face0' && g.source === 'View', 'Geometric Hatch: the object', JSON.stringify(g))
    same(await undoHead(), HATCH.geomhatch.undo.head[0], 'Geometric Hatch: the undo step')
    const lines = ((await td()).docs.Page.result.hatches?.GeomHatch?.faces?.Face0?.lines ?? []).length
    same(await st(`document.querySelectorAll('[data-hatch="GeomHatch"]').length`), lines, 'Geometric Hatch: the lines drawn')
    check(lines > 0, 'Geometric Hatch: the face has lines')
    // the image hatch
    await open('TechDraw_Hatch', ['Page/View.Face1'], 'hatch')
    same(await st(`document.querySelector('.tasks .tbox-head span')?.textContent`), 'Create Face Hatch', 'Image Hatch: the panel title')
    for (const n of ['sbScale', 'dsbRotation', 'dsbOffsetX', 'dsbOffsetY']) same(await ourText(n), fcText(HATCH.hatch.panel, n), `Image Hatch: ${n}`)
    await okTask()
    await made('Hatch'); await sleep(500)
    const h = await obj('Hatch')
    check(h?.faces?.[0] === 'Face1' && h.hatch_pattern === 'simple.svg', 'Image Hatch: the object', JSON.stringify(h))
    same(await undoHead(), 'Create Hatch', 'Image Hatch: the undo step')
    check((await st(`document.querySelectorAll('[data-hatch="Hatch"]').length`)) >= 1, 'Image Hatch: drawn')
    // a face that has a hatch gets the new one (FreeCAD: Remove old hatch, then Create Hatch)
    await open('TechDraw_Hatch', ['Page/View.Face1'], 'hatch')
    await okTask()
    same((await td()).docs.Page.objects.filter((o) => o.kind === 'DrawHatch').length, 1, 'Image Hatch: a face already hatched has the new hatch only')
    note('Image Hatch: FreeCAD makes "Remove old hatch", "Create Hatch" and several "Update Hatch" steps; this is one "Create Hatch" step')
  }
  // ── the leader line, rich text, symbol, weld, surface finish, image and clip tools (ui/scripts/fctechdraw_more.json) ──
  async function moreChecks() {
    console.log('more')
    const fcText = (panel, name) => { for (const tv of panel) for (const w of tv) if (w.name === name) return w.text ?? w.current }
    const ourText = (name) => st(`(() => { const e = document.querySelector('.tasks [data-qf="${name}"]'); return !e ? undefined : e.matches('input') ? e.value : e.querySelector('.combo-label')?.textContent ?? e.querySelector('input')?.value ?? e.textContent })()`)
    const okTask = async () => { await page.click('.tasks .tbuttons .qbtn.default', { timeout: 8000 }); await idle(); await sleep(500) }
    const cancelTask = async () => { await page.click('.tasks .tbuttons .qbtn:not(.default)'); await idle(); await sleep(500) }
    const msgText = async () => { await until('!!document.querySelector(".msgbox")', 'a message', 8000); const t = await st('document.querySelector(".msgbox-text")?.textContent'); await page.click('.msgbox-buttons button'); await sleep(200); return t }
    const open = async (cmd, refs, kind) => { await select(refs); await runCmd(cmd); await until(`cadui.getState().task?.other?.startsWith("${kind}:")`, `${cmd}'s panel`); await sleep(600) }
    const taskTitle = () => st(`document.querySelector('.tasks .tbox-head span')?.textContent`)
    const names = async () => (await objs()).map((o) => o.name)
    const count = (kind) => st(`cadui.td.state().docs.Page.objects.filter((o) => o.kind === "${kind}").length`)
    /** waits (the machine may be busy) until the page has n objects of a kind */
    const have = async (kind, n) => { await until(`cadui.td.state().docs.Page.objects.filter((o) => o.kind === "${kind}").length >= ${n}`, `${n} ${kind}`, 60000); await sleep(300) }
    const newest = async (before) => (await objs()).filter((o) => !before.includes(o.name))
    // the widgets FreeCAD's dump does not list (a QTextBrowser, a FileChooser, the form's root, a graphics view)
    const UNLISTED = ['tbBaseView', 'fcSymbolDir', 'TaskWeldingSymbol', 'graphicsView', 'surfaceScene']
    const ourNames = async () => (await ourPanel()).filter((n) => !UNLISTED.includes(n))
    const panelNames = async (rec, what) => same(sorted(await ourNames()), sorted(fcPanel(rec.panel)), `${what}: the panel's widgets`)
    const errs = () => st(`cadui.getState().messages.filter((m) => m.level === 'err').map((m) => m.text).slice(-3)`)
    const showErrs = async (what) => { const e = await errs(); if (e.length) console.log(`  (${what}: ${JSON.stringify(e)})`) }
    const sheetPx = async (x, y) => {
      const r = await st(`(() => { const e = document.querySelector('.td-sheet').getBoundingClientRect(); return [e.left, e.top, e.width, e.height] })()`)
      const res = (await td()).docs.Page.result
      return [r[0] + (x / res.width) * r[2], r[1] + (1 - y / res.height) * r[3]]
    }
    const REC = MORE
    // the menus: every new command is active with a page and a view (as the recording's states are)
    for (const key of ['states_none', 'states_view', 'states_edge']) {
      await select(key === 'states_view' ? ['Page/View'] : key === 'states_edge' ? ['Page/View.Edge2'] : [])
      const ours = await st('cadui.techdraw()')
      const flat = (es, acc = {}) => { for (const e of es) { if (e.sep) continue; if (e.cmd) acc[e.cmd] = e.enabled; if (e.menu) flat(e.menu, acc) } return acc }
      const f = flat(ours.menu)
      const fc = {}; const fl = (es) => { for (const e of es) { if (e.sep) continue; if (e.menu) fl(e.menu); else fc[e.name] = e.enabled } }; fl(REC[key].menu)
      for (const c of ['TechDraw_LeaderLine', 'TechDraw_RichTextAnnotation', 'TechDraw_WeldSymbol', 'TechDraw_SurfaceFinishSymbols', 'TechDraw_Symbol', 'TechDraw_Image', 'TechDraw_ClipGroup'])
        check(f[c] === fc[c], `${key}: ${c} is ${fc[c] ? 'active' : 'greyed'}`, `ours ${f[c]}`)
    }
    // ── Leader Line ──
    await select([]); await runCmd('TechDraw_LeaderLine')
    same(await msgText(), REC.leader_wrong_nothing.dialogs[0].text, 'Leader Line: nothing selected')
    await open('TechDraw_LeaderLine', ['Page/View'], 'leader')
    await panelNames(REC.leader.panel ? REC.leader : REC.leader, 'Leader Line')
    same(await taskTitle(), 'New Leader Line', 'Leader Line: the panel title')
    for (const n of ['cboxStartSym', 'cboxEndSym', 'cboxStyle', 'dsbWeight']) same(await ourText(n), fcText(REC.leader.panel, n), `Leader Line: ${n}`)
    await page.click('[data-qf="pbTracker"]'); await sleep(300)
    same(await ourText('pbTracker'), 'Save Points', 'Leader Line: Pick Points becomes Save Points')
    check(await st(`document.querySelector('.tasks .tbuttons .qbtn.default').disabled`), 'Leader Line: OK is off while points are picked')
    const view = (await td()).docs.Page.result.views.View
    const pts = [[view.x - 28, view.y - 5], [view.x - 8, view.y + 20], [view.x + 22, view.y + 20]]
    for (let i = 0; i < pts.length; i++) {
      const [px, py] = await sheetPx(...pts[i])
      await page.mouse.click(px, py); await sleep(150)
    }
    { const [px, py] = await sheetPx(...pts[2]); await page.mouse.dblclick(px, py); await sleep(400) }
    check(!(await st(`document.querySelector('.tasks .tbuttons .qbtn.default').disabled`)), 'Leader Line: OK is on once the points are saved')
    check(await st(`document.querySelector('[data-qf="pbTracker"]').disabled`), 'Leader Line: Save Points is off after the double click')
    await page.selectOption('[data-qf="cboxEndSym"] select', '0').catch(() => {})
    await okTask(); await have('DrawLeaderLine', 1)
    const l = await obj('LeaderLine')
    check(!!l && l.way_points.length === 3 && Math.abs(l.way_points[1][0] - 20) < 0.6 && Math.abs(l.way_points[1][1] + 25) < 0.6, 'Leader Line: WayPoints are the clicks, relative to the first',
      JSON.stringify(l?.way_points))
    check(!!l && Math.abs(l.x - (pts[0][0] - view.x)) < 0.6 && Math.abs(l.y - (pts[0][1] - view.y)) < 0.6, 'Leader Line: X, Y relative to the view', `${l?.x}, ${l?.y}`)
    same(await undoHead(), REC.leader.undo.head[0], 'Leader Line: the undo step')
    same(await st(`cadui.td.state().docs.Page.tree.find((r) => r.name === 'LeaderLine')?.depth`), REC.leader_nopoints.tree.find((r) => r.text === 'LeaderLine').depth - 1, 'Leader Line: under its view in the tree')
    check((await st(`document.querySelectorAll('[data-name="LeaderLine"]').length`)) > 0, 'Leader Line: drawn on the page')
    // Cancel makes nothing
    await open('TechDraw_LeaderLine', ['Page/View'], 'leader'); const nb = (await names()).length; await cancelTask()
    same((await names()).length, nb, 'Leader Line: Cancel makes nothing')
    // edit: a double click on the leader (setEdit)
    await page.locator('[data-td="Page/LeaderLine"]').dblclick(); await sleep(800)
    same(await taskTitle(), 'Edit Leader Line', 'Leader Line: the edit panel')
    await okTask()
    // ── a leader on a view at scale 0.5 turned 30 degrees, from the recorded points ──
    await st(`cadui.td.apply("Page", [{ op: "set", name: "View", props: { scale_type: "Custom", scale: 0.5, rotation: 30 } }], "Edit View.Scale")`); await idle()
    const sc = REC.leader_scaled
    await st(`cadui.td.apply("Page", [{ op: "leader", view: "View", points: ${JSON.stringify(sc.edit.points)} }], "Create Leader")`); await idle(); await sleep(400)
    { const ls = (await objs()).filter((o) => o.kind === 'DrawLeaderLine').pop(), f = sc.made[0]
      check(Math.abs(ls.x - f.X) < 1e-9 && Math.abs(ls.y - f.Y) < 1e-9 && ls.way_points.every((p, i) => near(p, f.WayPoints[i], 1e-9)), 'Leader Line at scale 0.5, turned 30 degrees: X, Y, WayPoints', JSON.stringify([ls.x, ls.y, ls.way_points])) }
    await st(`cadui.td.apply("Page", [{ op: "set", name: "View", props: { scale_type: "Page", rotation: 0 } }], "Edit View.Scale")`); await idle()
    // ── Rich Text ──
    await select(['Page/View']); await runCmd('TechDraw_RichTextAnnotation')
    await until('cadui.getState().task?.other?.startsWith("richanno:")', 'the rich text panel'); await sleep(500)
    same(await taskTitle(), 'Rich Text Creator', 'Rich Text: the panel title')
    for (const n of ['dsbMaxWidth', 'dsbWidth']) check(await st(`!!document.querySelector('[data-qf="${n}"] input')?.disabled`), `Rich Text: ${n} is off before the text is placed`)
    const before = await names()
    { const [px, py] = await sheetPx(200, 60); await page.mouse.click(px, py) }
    await until('cadui.td.state().docs.Page.objects.some((o) => o.kind === "DrawRichAnno")', 'the annotation', 20000); await sleep(600)
    const ra = (await newest(before))[0]
    check(!!ra && ra.anno_parent === 'View' && Math.abs(ra.x - 200) < 0.6 && Math.abs(ra.y - 60) < 0.6, 'Rich Text: made where the click was, on the base view', JSON.stringify([ra?.x, ra?.y, ra?.anno_parent]))
    same(await undoHead(), REC.richanno_plain.undo.head[0], 'Rich Text: the undo step')
    same(ra.anno_text, REC.richanno_plain.made[0].AnnoText.replace('Hello rich text', '<br />'), 'Rich Text: the empty text, as the text document writes it')
    await page.keyboard.type('Hello rich text'); await sleep(1200)
    same((await obj(ra.name)).anno_text, REC.richanno_plain.made[0].AnnoText, 'Rich Text: the text typed, as the text document writes it')
    await st(`(() => { const e = document.querySelector('.td-rich [contenteditable]'); e.focus(); document.execCommand('selectAll') })()`); await page.click('.td-rich-bar button[title="Bold"]'); await sleep(1200)
    check((await obj(ra.name)).anno_text.includes('<span style=" font-weight:700;">Hello rich text</span>'), 'Rich Text: bold is a span with font-weight:700', (await obj(ra.name)).anno_text.slice(-260))
    await okTask()
    same(await undoHead(), 'Create Annotation', 'Rich Text: OK keeps the one step')
    await page.locator(`[data-td="Page/${ra.name}"]`).dblclick(); await sleep(700)
    same(await taskTitle(), 'Rich Text Editor', 'Rich Text: the edit panel'); await cancelTask()
    // ── Symbol ──
    await select([]); await runCmd('TechDraw_Symbol')
    await until('!!document.querySelector(".msgbox")', 'the file chooser')
    same(await st('document.querySelector(".msgbox-title")?.textContent'), REC.symbol_page.file_dialogs[0].title, 'Insert SVG: the file dialog\'s title')
    await page.selectOption('.msgbox select', 'shipped:misc/North.svg'); await page.click('.msgbox-buttons .qbtn.default'); await have('DrawViewSymbol', 1)
    { const s = (await objs()).filter((o) => o.kind === 'DrawViewSymbol').pop(), f = REC.symbol_page.made[0]
      check(s.symbol.length === f.Symbol.length && s.symbol === f.Symbol, 'Insert SVG: the symbol is the file\'s text')
      same([s.x, s.y, s.owner, s.scale_type, s.name], [f.X, f.Y, f.Owner, f.ScaleType, f.Name], 'Insert SVG: X, Y, Owner, ScaleType, Name')
      same(await undoHead(), REC.symbol_page.undo.head[0], 'Insert SVG: the undo step') }
    await select(['Page/View']); await runCmd('TechDraw_Symbol'); await until('!!document.querySelector(".msgbox")', 'the file chooser')
    await page.selectOption('.msgbox select', 'shipped:other/Diameter.svg'); await page.click('.msgbox-buttons .qbtn.default'); await have('DrawViewSymbol', 2)
    { const s = (await objs()).filter((o) => o.kind === 'DrawViewSymbol').pop(), f = REC.symbol_owner.made[0]
      same([s.x, s.y, s.owner], [f.X, f.Y, f.Owner], 'Insert SVG on a view: X, Y, Owner (0, 0 about the view)') }
    // ── Weld Symbol ──
    await select([]); await runCmd('TechDraw_WeldSymbol')
    same(await msgText(), REC.weld_wrong_nothing.dialogs[0].text, 'Weld Symbol: nothing selected')
    await open('TechDraw_WeldSymbol', ['Page/LeaderLine'], 'weld')
    same(sorted(await ourNames()), sorted(fcPanel(REC.weld.panel).filter((n) => n)), 'Weld Symbol: the panel\'s widgets')
    same(await taskTitle(), 'Create Welding Symbol', 'Weld Symbol: the panel title')
    await page.click('[data-qf="pbArrowSymbol"]'); await until('!!document.querySelector(".msgbox")', 'SymbolChooser')
    same(await st('document.querySelector(".msgbox-title")?.textContent'), 'Select a Symbol', 'Weld Symbol: SymbolChooser\'s title')
    same(await st(`[...document.querySelectorAll('[data-qf="lwSymbols"] div > div:last-child')].map((e) => e.textContent)`), [...new Set(REC.weld.choosers[0].items)], 'Weld Symbol: SymbolChooser lists the AWS symbols')
    note('Weld Symbol: FreeCAD\'s SymbolChooser lists each symbol twice (the folder is loaded twice); once here')
    await page.click('[data-qf="lwSymbols"] [title="Welding/AWS/filletDown.svg"]'); await sleep(300)
    await page.fill('[data-qf="leArrowTextL"]', '3'); await page.fill('[data-qf="leArrowTextC"]', '(2)'); await page.fill('[data-qf="leArrowTextR"]', '5')
    await page.fill('[data-qf="leOtherTextL"]', '4'); await page.fill('[data-qf="leTailText"]', 'T1')
    await page.click('[data-qf="pbOtherSymbol"]'); await until('!!document.querySelector(".msgbox")', 'SymbolChooser')
    await page.click('[data-qf="lwSymbols"] [title="Welding/AWS/VUp.svg"]'); await sleep(300)
    await page.click('[data-qf="cbFieldWeld"] input'); await page.click('[data-qf="cbAllAround"] input')
    await okTask(); await have('DrawWeldSymbol', 1); await showErrs('weld')
    { const f = REC.weld.made, tw = await obj('TileWeld'), tw1 = await obj('TileWeld001'), w = await obj('WeldSymbol')
      same([tw?.left_text, tw?.center_text, tw?.right_text, tw?.tile_row, tw?.tile_parent], [f[0].LeftText, f[0].CenterText, f[0].RightText, f[0].TileRow, f[0].TileParent], 'Weld Symbol: the arrow side\'s tile')
      same([tw1?.left_text, tw1?.tile_row], [f[1].LeftText, f[1].TileRow], 'Weld Symbol: the other side\'s tile')
      check(tw?.symbol_file.endsWith('filletDown.svg') && tw1?.symbol_file.endsWith('VUp.svg'), 'Weld Symbol: the symbols chosen', JSON.stringify([tw?.symbol_file, tw1?.symbol_file]))
      same([w?.tail_text, w?.all_around, w?.field_weld, w?.alternating_weld, w?.leader], [f[2].TailText, f[2].AllAround, f[2].FieldWeld, f[2].AlternatingWeld, f[2].Leader], 'Weld Symbol: the symbol\'s properties')
      same(await undoHead(), REC.weld.undo.head[0], 'Weld Symbol: the undo step')
      const rows = (await td()).docs.Page.tree
      for (const n of ['LeaderLine', 'WeldSymbol', 'TileWeld', 'TileWeld001']) same(rows.find((r) => r.name === n)?.depth, REC.weld.tree.find((r) => r.text === n).depth - 1, `Weld Symbol: ${n}'s place in the tree`) }
    await st(`cadui.td.select("Page/WeldSymbol")`); await runCmd('TechDraw_WeldSymbol'); await until('cadui.getState().task?.other?.startsWith("weld:WeldSymbol:edit")', 'the weld edit panel'); await sleep(500)
    same(await taskTitle(), 'Edit Welding Symbol', 'Weld Symbol: the edit panel')
    same(await ourText('leTailText'), 'T1', 'Weld Symbol: the edit panel shows the tail text')
    await page.fill('[data-qf="leTailText"]', 'T2'); await okTask()
    same(await undoHead(), REC.weld_edit.undo.head[0], 'Weld Symbol: the edit\'s undo step')
    same((await obj('WeldSymbol')).tail_text, 'T2', 'Weld Symbol: the edit')
    // ── Surface Finish Symbol ──
    await select(['Page/Page']); await runCmd('TechDraw_SurfaceFinishSymbols')
    same(await msgText(), REC.surface_wrong_page.dialogs[0].text, 'Surface Finish Symbol: a page selected')
    await open('TechDraw_SurfaceFinishSymbols', [], 'surface')
    same(sorted(await ourNames()), sorted(fcPanel(REC.surface_none.panel)), 'Surface Finish Symbol: the panel\'s widgets')
    same(await taskTitle(), 'Surface Finish Symbols', 'Surface Finish Symbol: the panel title')
    const nsurf = await st(`cadui.td.state().docs.Page.objects.filter((o) => o.name.startsWith('SurfaceSymbol')).length`)
    await okTask(); await until(`cadui.td.state().docs.Page.objects.filter((o) => o.name.startsWith('SurfaceSymbol')).length > ${nsurf}`, 'the surface symbol', 60000); await showErrs('surface')
    { const s = (await objs()).filter((o) => o.name.startsWith('SurfaceSymbol')).pop(), f = REC.surface_none.made[0]
      same([s.owner, s.x, s.y, s.symbol], [f.Owner, f.X, f.Y, f.Symbol], 'Surface Finish Symbol: the page\'s centre, and the symbol\'s text')
      same(await undoHead(), REC.surface_none.undo.head[0], 'Surface Finish Symbol: the undo step') }
    for (const [key, ref] of [['surface_vertex', 'Page/View.Vertex1'], ['surface_edge', 'Page/View.Edge2'], ['surface_face', 'Page/View.Face0']]) {
      const nsf = await st(`cadui.td.state().docs.Page.objects.filter((o) => o.name.startsWith('SurfaceSymbol')).length`)
      await open('TechDraw_SurfaceFinishSymbols', [ref], 'surface')
      const f = REC[key].made[0]
      if (REC[key].edit) {
        const e = REC[key].edit
        if (e.iso) { /* the first recording's ISO values */ }
      }
      await okTask(); await until(`cadui.td.state().docs.Page.objects.filter((o) => o.name.startsWith('SurfaceSymbol')).length > ${nsf}`, 'the surface symbol', 60000)
      const s = (await objs()).filter((o) => o.name.startsWith('SurfaceSymbol')).pop()
      check(Math.abs(s.x - f.X) < 0.01 && Math.abs(s.y - f.Y) < 0.01 && s.owner === f.Owner, `Surface Finish Symbol on ${ref.split('.')[1]}: placed at the element`, `${s.x}, ${s.y} vs ${f.X}, ${f.Y}`)
    }
    // ── Image ──
    writeFileSync(join(ROOT, SLUG, 'pic.png'), Buffer.from(REC.image_png_b64, 'base64'))
    await st('cadui.td.load()'); await idle(); await sleep(500)
    await select([]); await runCmd('TechDraw_Image'); await until('!!document.querySelector(".msgbox")', 'the image chooser')
    same(await st('document.querySelector(".msgbox-title")?.textContent'), REC.image_page.file_dialogs[0].title, 'Bitmap Image: the file dialog\'s title')
    await page.selectOption('.msgbox select', 'project:pic.png'); await page.click('.msgbox-buttons .qbtn.default'); await have('DrawViewImage', 1)
    { const im = (await objs()).filter((o) => o.kind === 'DrawViewImage').pop(), f = REC.image_page.made[0]
      same([im.x, im.y, im.owner, im.width, im.height, im.scale_type], [f.X, f.Y, f.Owner, f.Width, f.Height, f.ScaleType], 'Bitmap Image: X, Y, Owner, Width, Height, ScaleType')
      same(await undoHead(), REC.image_page.undo.head[0], 'Bitmap Image: the undo step')
      check((await st(`document.querySelectorAll('[data-name="${im.name}"] image, image[href^="data:image/png"]').length`)) > 0, 'Bitmap Image: drawn') }
    // ── Clip Group ──
    await select(['Page/View']); await runCmd('TechDraw_ClipGroupAdd')
    same(await msgText(), 'Select one clip group and one view', 'Add View To Clip Group: a view alone')
    await select([]); await runCmd('TechDraw_ClipGroup'); await have('DrawViewClip', 1)
    { const c = (await objs()).filter((o) => o.kind === 'DrawViewClip').pop(), f = REC.clip.made[0]
      same([c.x, c.y, c.width, c.height, c.show_frame], [f.X, f.Y, f.Width, f.Height, f.ShowFrame], 'Clip Group: X, Y, Width, Height, ShowFrame')
      same(await undoHead(), REC.clip.undo.head[0], 'Clip Group: the undo step')
      await st(`cadui.td.apply("Page", [{ op: "set", name: "${c.name}", props: { width: 60, height: 40, show_frame: true } }], "Edit Clip.Width")`); await idle()
      await select(['Page/' + c.name, 'Page/View']); await runCmd('TechDraw_ClipGroupAdd'); await idle(); await sleep(500)
      const v = await obj('View'), cc = await obj(c.name)
      same([v.x, v.y, cc.views], [REC.clip_after_add.view.X, REC.clip_after_add.view.Y, REC.clip_after_add.clip.Views], 'Add View To Clip Group: the view\'s X, Y and the clip\'s Views')
      same(await undoHead(), REC.clip_add.undo.head[0], 'Add View To Clip Group: the undo step')
      await select(['Page/View']); await runCmd('TechDraw_ClipGroupRemove'); await idle(); await sleep(500)
      same((await obj(c.name)).views, REC.clip_after_remove.clip.Views, 'Remove From Clip Group: the clip\'s Views')
      same(await undoHead(), REC.clip_remove.undo.head[0], 'Remove From Clip Group: the undo step') }
    // ── the tree and the property view ──
    for (const [key, name] of [['props_DrawLeaderLine_LeaderLine', 'LeaderLine'], ['props_DrawWeldSymbol_WeldSymbol', 'WeldSymbol'], ['props_DrawViewClip_Clip', 'Clip']]) {
      await select([`Page/${name}`]); await sleep(400)
      const rows = await st(`[...document.querySelectorAll('.prop-group .pk, .prow .pk')].map((e) => e.textContent.trim())`)
      const fc = (REC[key].data[0] ?? []).filter((r) => r.depth === 1).map((r) => r.name)
      check(fc.every((n) => rows.includes(n)), `${name}: the property view has FreeCAD's rows`, JSON.stringify(fc.filter((n) => !rows.includes(n))))
    }
    note('Leader Line: the points are edited by picking them again (Edit Points), not by dragging the line\'s markers (QGEPath)')
    note('Rich Text: the toolbar has bold, italic, underline, colour and size only; the text is laid out by an estimated advance, not Qt\'s metrics')
    note('Insert SVG, Bitmap Image: the file dialog is a list of FreeCAD\'s symbols and the project\'s files with Browse… for a file of the person\'s own')
  }
  if (want('more')) await moreChecks()
  // ── the SVG export ──
  if (want('export')) {
    console.log('export')
    const r = await st(`fetch('/api/cad', { method: 'POST', headers: { 'X-CAD': '1', 'Content-Type': 'application/json' }, body: JSON.stringify({ slug: '${SLUG}', argv: ['techdraw', 'export', '${SLUG}', 'Page', '--format', 'svg'] }) }).then((r) => r.json())`)
    const svg = readFileSync(join(ROOT, SLUG, 'out', 'techdraw', 'Page.svg'), 'utf8')
    const head = (s) => ['width', 'height', 'viewBox'].map((a) => (s.match(new RegExp(`<svg[^>]*\\s${a}="([^"]*)"`)) ?? [])[1])
    same(head(svg), head(FC.page_svg), 'the exported SVG\'s page size')
    void r
  }
} catch (e) { bad('the check stopped', e.stack ?? String(e)) }
await browser.close()
server.kill()
if (!args.includes('--keep')) { rmSync(scratch, { recursive: true, force: true }); rmSync(warmDir, { recursive: true, force: true }) }
console.log(`techdrawcheck: ${pass} ok, ${known} known, ${fail} FAIL`)
process.exit(fail ? 1 : 0)

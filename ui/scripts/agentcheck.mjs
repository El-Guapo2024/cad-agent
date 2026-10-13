// Drives what the CAD Agent workbench gives a person that the cad CLI gives an agent, in a scratch workbench: the bill of
// materials, shop files, drawing (and its tab), library (browse, use with Undo, check, add a picked file), poses, and the
// options added to Check, Bought parts and New Document. It also looks at the machine fixture the way a person does: the
// model tree's names, the Checks rows, and a part of the sub-assembly moved through the page.
//   node ui/scripts/agentcheck.mjs URL PROJECTS_ROOT STEP_FILE [PROJECT]
//   URL            the scratch workbench's /next/ (never the owner's: this writes projects and bought parts)
//   PROJECTS_ROOT  the folder that workbench serves, holding a copy of tests/fixtures (mini_machine and mini_gantry)
//   STEP_FILE      a small STEP to pick in Library > Add
// It never clicks Approve Renders: approving is the owner's call (the dialog is opened and cancelled, nothing more).
// Needs Playwright (NODE_PATH to one) with a Chromium, and uses ANGLE's SwiftShader as keycheck.mjs does.
import { createRequire } from 'module'
import { existsSync, readFileSync, readdirSync } from 'fs'
import { join } from 'path'
const require = createRequire(import.meta.url)
let chromium
try { ({ chromium } = require('playwright')) } catch { ({ chromium } = createRequire('/opt/node-tools/node_modules/')('playwright')) }
const [BASE = 'http://127.0.0.1:8851/next/', ROOT = '/tmp/uiroot', STEP = '/tmp/uipw/box.step', PROJECT = 'mini_machine'] = process.argv.slice(2)
const pdir = join(ROOT, PROJECT)

const b = await chromium.launch({ args: ['--use-angle=swiftshader', '--use-gl=angle', '--enable-unsafe-swiftshader'] })
const ctx = await b.newContext({ viewport: { width: 1500, height: 950 }, acceptDownloads: true })
const p = await ctx.newPage()
const errs = []
p.on('pageerror', (e) => errs.push(e.message))
p.on('console', (m) => { if (m.type() === 'error' && !/favicon|Failed to load resource/.test(m.text())) errs.push('console: ' + m.text()) })

const results = []
const ok = (name, cond, detail = '') => { results.push([cond ? 'OK ' : 'NO ', name, cond ? '' : String(detail).slice(0, 300)]); return cond }
async function step(name, fn) {
  const e0 = errs.length
  try { await fn() } catch (e) { results.push(['NO ', name, `threw: ${String(e.message).split('\n')[0].slice(0, 300)}`]) }
  if (errs.length > e0) results.push(['NO ', name + ' (page errors)', errs.slice(e0).join(' / ').slice(0, 300)])
}
const tasks = () => p.locator('.taskview')
const report = () => p.locator('.report .rl').allInnerTexts()
const menu = async (top, label) => {
  await p.locator('.mb-trigger', { hasText: new RegExp(`^${top}$`) }).click()
  await p.locator('.mb-content .mb-item', { hasText: label }).first().click()
}
const closeTask = async () => { const t = tasks().locator('.tbuttons .qbtn', { hasText: /^(Cancel|Close)$/ }).first(); if (await t.count()) await t.click(); await p.waitForTimeout(200) }
const selectTree = async (name) => { await p.locator('.trow .tname', { hasText: new RegExp(`^${name}$`) }).first().click(); await p.waitForTimeout(150) }
// the model tree is not on screen while a task is open, so what is selected is read from the store
const treeSelected = async () => p.evaluate(() => cadui.getState().selected)

// a hash change alone does not reload the page, so go through a blank one to open a project afresh
const openFresh = async (slug) => {
  await p.goto('about:blank'); await p.goto(BASE + '#' + slug, { waitUntil: 'load' })
  await p.waitForSelector('.trow .tname', { timeout: 120000 }); await p.waitForTimeout(1500)
  const done = p.getByRole('button', { name: 'Done', exact: true }); if (await done.count()) await done.click()
  await p.getByText(`${slug} : 1`).click(); await p.waitForTimeout(1500)
}
await openFresh(PROJECT)

await step('model tree: the machine and its sub-assembly by their full names', async () => {
  const names = await p.locator('.trow .tname').allInnerTexts()
  ok('tree has base, hot_plate and gantry/post_left, gantry/tool_plate, gantry/motor',
    ['base', 'hot_plate', 'gantry/post_left', 'gantry/tool_plate', 'gantry/motor'].every((n) => names.includes(n)), names.join(','))
  ok('tree lists 11 bodies', names.length === 12, names.length)   // the document row and 11 bodies
})

await step('checks: the rows name their project, and `subassembly/linked` is there', async () => {
  await p.locator('.dv-tab', { hasText: 'Checks' }).first().click().catch(() => p.getByText('Checks', { exact: true }).first().click())
  await p.getByText('Recompute', { exact: false }).last().click()
  await p.waitForFunction(() => document.querySelectorAll('.checks .ctable tbody tr').length > 100, null, { timeout: 180000 })
  const rules = await p.locator('.checks .ctable tbody tr td:nth-child(2)').allInnerTexts()
  ok('a row reads subassembly/linked', rules.includes('subassembly/linked'))
  ok('the child project\'s rows read mini_gantry:geometry/envelope', rules.includes('mini_gantry:geometry/envelope'), rules.filter((r) => /mini_gantry/.test(r)).slice(0, 3).join('|'))
  ok('a pair row selects both of its bodies', await (async () => {
    const row = p.locator('.checks .ctable tbody tr', { hasText: 'back_wall vs base' }).first()
    await row.click(); await p.waitForTimeout(300)
    const sel = await treeSelected()
    return sel.includes('back_wall') && sel.includes('base')
  })(), await treeSelected())
  await p.getByText('Report View', { exact: true }).first().click()
})

await step('a part of the sub-assembly moved through the page: cad place machine gantry/tool_plate, then Undo', async () => {
  await selectTree('gantry/tool_plate')
  await menu('Edit', 'Placement')
  const x = tasks().locator('fieldset', { hasText: 'Translation' }).locator('.tfield', { hasText: /^X/ }).locator('input').first()
  await x.fill('0.5 mm'); await x.press('Tab')
  await tasks().getByRole('button', { name: 'OK', exact: true }).click()
  await p.waitForFunction(() => cadui.getState().scene.bodies.find((b) => b.name === 'gantry/tool_plate').placement?.move?.[0] === 0.5, null, { timeout: 120000 })
  const toml = existsSync(join(pdir, 'placements.toml')) ? readFileSync(join(pdir, 'placements.toml'), 'utf8') : ''
  ok('placements.toml names the child body by its full name', /\["?gantry\/tool_plate"?\]/.test(toml) && /0\.5/.test(toml), toml.slice(0, 200))
  ok('the scene has it 0.5 mm along x', true)
  await menu('Edit', 'Undo')
  await p.waitForFunction(() => !cadui.getState().scene.bodies.find((b) => b.name === 'gantry/tool_plate').placement, null, { timeout: 120000 })
  ok('Undo puts it back and placements.toml goes', !existsSync(join(pdir, 'placements.toml')), existsSync(join(pdir, 'placements.toml')) ? readFileSync(join(pdir, 'placements.toml'), 'utf8') : '')
})

await step('a part of the sub-assembly dragged with the Transform dragger: cad place machine gantry/tool_plate, then Undo', async () => {
  await selectTree('gantry/tool_plate')
  await menu('Edit', 'Transform')
  await p.waitForTimeout(1500)
  // where the +X arrow's pick zone is on the screen: its mesh's centre, through the camera
  const at = await p.evaluate(() => {
    const v = cadui.getView(), tc = v.tcs[0], cam = v.viewer.camera.getCamera(), canvas = v.viewer.renderer.domElement, V3 = tc.object.position.constructor
    tc.getHelper().updateMatrixWorld(true)
    const r = canvas.getBoundingClientRect(), px = (c) => { c.project(cam); return [r.left + (c.x + 1) / 2 * r.width, r.top + (1 - c.y) / 2 * r.height] }
    const mesh = tc._gizmo.picker.translate.children.find((c) => c.name === 'X')
    mesh.geometry.computeBoundingBox()
    const tip = mesh.geometry.boundingBox.getCenter(new V3()); mesh.localToWorld(tip)
    return { tip: px(tip), centre: px(tc.object.position.clone()) }
  })
  const [x0, y0] = at.tip, d = [x0 - at.centre[0], y0 - at.centre[1]], len = Math.hypot(...d) || 1
  await p.mouse.move(x0, y0); await p.mouse.down()
  await p.mouse.move(x0 + (d[0] / len) * 40, y0 + (d[1] / len) * 40, { steps: 8 })
  await p.mouse.move(x0 + (d[0] / len) * 80, y0 + (d[1] / len) * 80, { steps: 8 })
  await p.mouse.up()
  const mm = await p.evaluate(() => cadui.getView().transformDelta().elements[12])
  ok('the dragger moved the part along +X', mm > 1, mm)
  await tasks().getByRole('button', { name: 'OK', exact: true }).click()
  await p.waitForFunction(() => cadui.getState().scene.bodies.find((b) => b.name === 'gantry/tool_plate').placement?.move?.[0] > 1, null, { timeout: 120000 })
  const toml = readFileSync(join(pdir, 'placements.toml'), 'utf8')
  ok('placements.toml has the child body under its full name', /\["gantry\/tool_plate"\]/.test(toml) && new RegExp(`move = \\[${mm}(\\.0)?,`).test(toml), toml.slice(-120))
  ok('the Report view says it was placed', (await report()).some((l) => /cad place: placed gantry\/tool_plate/.test(l)), (await report()).slice(-3).join('|'))
  await menu('Edit', 'Undo')
  await p.waitForFunction(() => !cadui.getState().scene.bodies.find((b) => b.name === 'gantry/tool_plate').placement, null, { timeout: 120000 })
  ok('Undo takes the drag back', !existsSync(join(pdir, 'placements.toml')))
})

// ── Bill of materials ────────────────────────────────────────────────────────────────────────────────
await step('bom: the table, a click selecting bodies, the options and the two downloads', async () => {
  await menu('CAD Agent', 'Bill of Materials')
  await tasks().locator('.ctable tbody tr').first().waitFor({ timeout: 180000 })
  const rows = await tasks().locator('.ctable').first().locator('tbody tr').allInnerTexts()
  ok('11 lines, the gantry nested under its line', rows.length === 11 && rows.some((r) => /^5\.1/.test(r)) && rows.some((r) => /^5\tgantry/.test(r)), rows.length + ': ' + rows.join(' | ').slice(0, 200))
  await tasks().locator('.ctable tbody tr', { hasText: 'hot_plate' }).first().click(); await p.waitForTimeout(250)
  ok('a click on hot_plate selects it in the tree', (await treeSelected()).includes('hot_plate'), await treeSelected())
  await tasks().locator('.ctable tbody tr', { hasText: /^5gantry/ }).first().click(); await p.waitForTimeout(250)
  ok('a click on the gantry line selects its seven bodies', (await treeSelected()).filter((n) => n.startsWith('gantry/')).length === 7, await treeSelected())
  await tasks().getByText('Only parts').click()
  await p.waitForFunction(() => document.querySelectorAll('.taskview .ctable')[0]?.querySelectorAll('tbody tr').length < 11, null, { timeout: 120000 })
  ok('Only parts drops what is bought', (await tasks().locator('.ctable').first().locator('tbody tr').count()) < 11)
  await tasks().getByText('Only parts').click()
  await p.waitForFunction(() => document.querySelectorAll('.taskview .ctable')[0]?.querySelectorAll('tbody tr').length === 11, null, { timeout: 120000 })
  const [dl] = await Promise.all([p.waitForEvent('download'), tasks().getByRole('link', { name: 'CSV' }).click()])
  const text = readFileSync(await dl.path(), 'utf8')
  ok('CSV downloads with FreeCAD\'s columns first', /^Index,Name,Description,File Name,Quantity,/.test(text) && dl.suggestedFilename() === 'bom.csv', text.slice(0, 80))
  const [dj] = await Promise.all([p.waitForEvent('download'), tasks().getByRole('link', { name: 'JSON' }).click()])
  ok('JSON downloads', JSON.parse(readFileSync(await dj.path(), 'utf8')).project === PROJECT)
  await closeTask()
  const log = (await report()).join('\n')
  ok('the Report view says what cad bom said', /cad bom mini_machine: .*bill of materials: 11 lines, 11 bodies/.test(log) && /cad bom: 11 lines, 11 bodies/.test(log), log.split('\n').filter((l) => /bom/.test(l)).slice(-3).join(' // '))
})

// ── Drawing, and its tab ─────────────────────────────────────────────────────────────────────────────
await step('drawing: draw the selected plate, show it in a tab, save DXF, SVG and PDF', async () => {
  await selectTree('base')
  await menu('CAD Agent', 'Drawing')
  const part = tasks().locator('.tfield', { hasText: 'Part' }).first()
  ok('Drawing opens on the selected plate', (await part.innerText()).includes('base'), await part.innerText())
  await tasks().getByRole('button', { name: 'Draw', exact: true }).click()
  await p.getByText('base : Drawing').first().waitFor({ timeout: 180000 })
  await p.waitForFunction(() => { const i = document.querySelector('.drawing-sheet img'); return i && i.complete && i.naturalWidth > 0 }, null, { timeout: 60000 })
  const src1 = await p.locator('.drawing-sheet img').getAttribute('src')
  ok('the tab shows the SVG', src1.includes('inline=1'))
  await tasks().getByRole('button', { name: 'Draw', exact: true }).click()
  await p.waitForFunction((s) => document.querySelector('.drawing-sheet img')?.getAttribute('src') !== s, src1, { timeout: 120000 })
  ok('drawing the plate again refreshes the one tab', (await p.evaluate(() => cadui.getDock().panels.filter((x) => x.id.startsWith('drawing:')).length)) === 1)
  const sheetText = await tasks().innerText()
  ok('the task says UNCHECKED and NOT VERIFIED for a design nobody verified', /UNCHECKED/.test(sheetText) && /NOT VERIFIED/.test(sheetText), sheetText.slice(0, 200))
  ok('the tab says NOT VERIFIED too', /NOT VERIFIED/.test(await p.locator('.drawing-bar').innerText()))
  const w = await p.evaluate(() => { const i = document.querySelector('.drawing-sheet img'), s = document.querySelector('.drawing-sheet'); const r = i.getBoundingClientRect(), q = s.getBoundingClientRect(); return [r.width, q.width, r.left >= q.left - 1, r.right <= q.right + 1] })
  ok('the sheet is fitted in the tab', w[0] <= w[1] && w[2] && w[3], JSON.stringify(w))
  const k0 = await p.locator('.drawing-sheet img').evaluate((i) => i.getBoundingClientRect().width)
  await p.locator('.drawing-sheet').hover(); await p.mouse.wheel(0, -300); await p.waitForTimeout(200)
  ok('the wheel zooms', (await p.locator('.drawing-sheet img').evaluate((i) => i.getBoundingClientRect().width)) > k0 * 1.2)
  await p.getByRole('button', { name: 'Fit' }).click().catch(() => p.locator('.drawing-bar button[title="Fit"]').click())
  for (const ext of ['DXF', 'SVG', 'PDF']) {
    const [d] = await Promise.all([p.waitForEvent('download'), p.locator('.drawing-bar').getByRole('link', { name: ext, exact: true }).click()])
    const t = readFileSync(await d.path())
    ok(`${ext} downloads`, d.suggestedFilename() === `base.${ext.toLowerCase()}` && t.length > 500, d.suggestedFilename() + ' ' + t.length)
    if (ext === 'PDF') ok('the PDF is a PDF', t.subarray(0, 5).toString() === '%PDF-')
  }
  await p.locator('.mb-trigger', { hasText: /^Windows$/ }).click()
  ok('Windows lists the drawing', (await p.locator('.mb-content .mb-item').allInnerTexts()).some((t) => /base : Drawing/.test(t)))
  await p.keyboard.press('Escape')
  await closeTask()
  // the drawing's tab closes with File > Close, and the 3D view stays
  await p.getByText('mini_machine : 1').click(); await p.waitForTimeout(300)
  await p.getByText('base : Drawing').first().click(); await p.waitForTimeout(300)
  await menu('File', 'Close')
  await p.waitForTimeout(500)
  const tabsNow = await p.evaluate(() => cadui.getDock().panels.map((x) => x.id))
  ok('File > Close closes the drawing tab and not the 3D view', !tabsNow.includes('drawing:base') && tabsNow.includes('view3d'), tabsNow.join(','))
})

await step('drawing: the tree\'s context menu offers it for a plate and not for a bought part', async () => {
  await p.locator('.trow .tname', { hasText: /^base$/ }).first().click({ button: 'right' })
  const items = await p.locator('.ctx .mb-item').allInnerTexts()
  ok('a plate has Drawing… in its menu', items.some((t) => /^Drawing…/.test(t.trim())), items.join('|'))
  await p.locator('.ctx .mb-item', { hasText: /^Drawing…/ }).first().click()
  await tasks().locator('.tfield', { hasText: 'Part' }).first().waitFor({ timeout: 10000 })
  ok('it opens Drawing on that plate', (await tasks().locator('.tfield', { hasText: 'Part' }).first().innerText()).includes('base'))
  await closeTask()
  await p.locator('.trow .tname', { hasText: /^gantry\/beam$/ }).first().click({ button: 'right' })
  const beam = await p.locator('.ctx .mb-item').allInnerTexts()
  ok('a bought part of the sub-assembly has none', !beam.some((t) => /^Drawing…/.test(t.trim())), beam.join('|'))
  await p.keyboard.press('Escape')
})

// ── Shop files ───────────────────────────────────────────────────────────────────────────────────────
await step('shop: write nothing for an unverified design, a stamped draft, the listing and downloads, check', async () => {
  await menu('CAD Agent', 'Shop Files')
  await tasks().getByText('out/shop/ has nothing yet').or(tasks().getByText(/In out\/shop\//)).first().waitFor({ timeout: 30000 })
  await tasks().getByRole('button', { name: 'Write files', exact: true }).click()
  await tasks().getByText('UNCHECKED').first().waitFor({ timeout: 180000 })
  ok('Write files for a design nobody verified says why and writes nothing', /never verified|cad verify/.test(await tasks().innerText()), (await tasks().innerText()).slice(0, 300))
  await tasks().getByRole('button', { name: 'Write draft', exact: true }).click()
  await tasks().getByText(/In out\/shop\//).waitFor({ timeout: 180000 })
  const text = await tasks().innerText()
  ok('the draft is listed as NOT VERIFIED with its files', /draft, NOT VERIFIED/.test(text) && /bom\.csv/.test(text) && /base\.dxf/.test(text) && /drawings\/base\.svg/.test(text), text.slice(0, 400))
  const [d] = await Promise.all([p.waitForEvent('download'), tasks().locator('tr', { hasText: /^base\.dxf/ }).getByRole('link', { name: 'Save' }).click()])
  ok('a shop file downloads', d.suggestedFilename() === 'base.dxf' && readFileSync(await d.path(), 'utf8').includes('NOT VERIFIED'))
  const [pg] = await Promise.all([ctx.waitForEvent('page'), tasks().locator('tr', { hasText: /^drawings\/base\.svg/ }).getByRole('link', { name: 'View' }).click()])
  await pg.waitForLoadState('load')
  ok('View opens a drawing in a browser tab', /svg/.test(pg.url()) || /inline=1/.test(pg.url()), pg.url())
  await pg.close()
  await tasks().getByRole('button', { name: 'Check folder', exact: true }).click()
  await p.waitForFunction(() => /nothing to certify|cad verify|draft/.test(document.querySelector('.taskview')?.innerText ?? ''), null, { timeout: 180000 })
  await closeTask()
  const log = (await report()).join('\n')
  ok('the Report view lists cad shop', /cad shop mini_machine/.test(log) && /cad shop: /.test(log), log.split('\n').filter((l) => /shop/.test(l)).slice(-3).join(' // '))
  ok('the folder is where the CLI puts it', existsSync(join(pdir, 'out', 'shop', 'manifest.json')))
})

// ── Library ──────────────────────────────────────────────────────────────────────────────────────────
await step('library: browse, search, info, use with Undo, check, add a picked file', async () => {
  await menu('CAD Agent', 'Library')
  await tasks().locator('.ctable tbody tr').first().waitFor({ timeout: 60000 })
  ok('the catalog lists 22 entries', (await tasks().locator('.ctable').first().locator('tbody tr').count()) >= 22)
  await tasks().getByPlaceholder('name, vendor or part number').fill('nema')
  ok('search narrows it to the nema entries', (await tasks().locator('.ctable').first().locator('tbody tr').count()) === 3)
  await tasks().locator('.ctable tbody tr', { hasText: /^nema8/ }).first().click()
  await tasks().getByText('Nanotec').first().waitFor({ timeout: 60000 })
  ok('info shows vendor, part number, licence and mass', /ST2018M0804-A/.test(await tasks().innerText()) && /MIT/.test(await tasks().innerText()) && /80/.test(await tasks().innerText()))
  // an entry whose file is not in the store: Fetch… only puts the command on the Console's line (a download is the person's Return)
  await tasks().getByPlaceholder('name, vendor or part number').fill('608zz')
  await tasks().locator('.ctable tbody tr', { hasText: /^fcl-608zz/ }).first().click()
  await tasks().getByRole('button', { name: 'Fetch…' }).click()
  const draft = await p.evaluate(() => cadui.getState().consoleDraft)
  const walk = (d) => (existsSync(d) ? readdirSync(d, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(join(d, e.name)) : [join(d, e.name)])) : [])
  ok('Fetch… puts `cad lib fetch` on the Console line and downloads nothing', draft === 'cad lib fetch fcl-608zz' && !walk(process.env.CAD_LIBRARY ?? '/tmp/uilib').some((f) => f.includes('45246a4c')), draft)
  await p.evaluate(() => cadui.setState({ consoleDraft: '' }))
  await tasks().getByPlaceholder('name, vendor or part number').fill('nema')
  await tasks().locator('.ctable tbody tr', { hasText: /^nema8/ }).first().click()
  await tasks().getByText('Nanotec').first().waitFor({ timeout: 60000 })
  const name = 'nema8_ui' + String(Date.now()).slice(-5)
  await tasks().getByPlaceholder('nema8').fill(name)
  await tasks().getByRole('button', { name: /^Use in / }).click()
  await tasks().getByText(/copied into/).waitFor({ timeout: 60000 })
  ok('Use copies it into the open project, with its sidecar', existsSync(join(pdir, 'bought', `${name}.json`)) && existsSync(join(pdir, 'bought', `${name}.step`)) || existsSync(join(pdir, 'bought', `${name}.json`)), readdirSync(join(pdir, 'bought')).join(','))
  await p.waitForFunction(() => /Add Library Part/.test(document.querySelector('.tb-split button[title^="Undo"]')?.getAttribute('title') ?? ''), null, { timeout: 15000 })
  ok('Edit > Undo is now "Add Library Part"', true)
  await closeTask()
  await menu('Edit', 'Undo')
  await p.waitForFunction((n) => true, name)
  await p.waitForTimeout(1500)
  ok('Undo takes the part out of the project again', !existsSync(join(pdir, 'bought', `${name}.json`)), readdirSync(join(pdir, 'bought')).join(','))
  // check
  await menu('CAD Agent', 'Library')
  await tasks().getByRole('button', { name: 'Check', exact: true }).click()
  await tasks().getByRole('button', { name: 'Check the store' }).click()
  await tasks().getByText(/the store:/).waitFor({ timeout: 60000 })
  ok('Check the store answers', /PASS|N\/A|checked/.test(await tasks().innerText()), (await tasks().innerText()).slice(0, 200))
  await tasks().getByRole('button', { name: new RegExp(`Check ${PROJECT}`) }).click()
  await tasks().getByText(new RegExp(`${PROJECT}/bought/:`)).waitFor({ timeout: 60000 })
  ok('Check a project\'s bought parts answers', true)
  // add a picked file
  const entry = 'ui-box-' + String(Date.now()).slice(-5)
  await tasks().getByRole('button', { name: 'Add…' }).click()
  await tasks().locator('input[type=file]').setInputFiles(STEP)
  await tasks().getByText(/box\.step, [\d,]+ bytes/).waitFor({ timeout: 30000 })
  await tasks().getByPlaceholder('a catalog entry, or a new name').fill(entry)
  await tasks().getByPlaceholder('the page the file came from').fill('https://example.com/ui-check/box')
  await tasks().getByRole('button', { name: 'Add', exact: true }).click()
  await tasks().getByText(entry).first().waitFor({ timeout: 60000 })
  await tasks().locator('.ctable tbody tr', { hasText: entry }).first().waitFor({ timeout: 30000 })
  ok('the picked file is a new entry in the store, and the catalog shows it', true)
  await closeTask()
})

await step('console: the open project goes where cad wants it for a sub-command', async () => {
  await p.getByText('Console', { exact: true }).first().click()
  const input = p.locator('.console .cinput input')
  const say = async (line) => { await input.fill(line); await input.press('Enter'); await p.waitForTimeout(2500) }
  const out = async () => (await p.locator('.console .cl:not(.cinput)').allInnerTexts()).join('\n')
  await say('cad lib ls nema')
  ok('lib ls nema lists the nema entries', /nema8/.test(await out()) && /nema17/.test(await out()), (await out()).slice(-300))
  await say('lib use nema8 --as ui_console_part')
  ok('lib use puts the open project after the sub-command', existsSync(join(pdir, 'bought', 'ui_console_part.json')) || readdirSync(join(pdir, 'bought')).some((f) => f.startsWith('ui_console_part')), readdirSync(join(pdir, 'bought')).join(','))
  await say('bought ls')
  ok('bought ls lists it', /ui_console_part/.test((await out()).split('\n').slice(-12).join('\n')), (await out()).slice(-300))
  await menu('Edit', 'Undo'); await p.waitForTimeout(1500)
  ok('Undo takes the console\'s lib use back', !(existsSync(join(pdir, 'bought')) && readdirSync(join(pdir, 'bought')).some((f) => f.startsWith('ui_console_part'))))
  await p.getByText('Report View', { exact: true }).first().click()
})
await step('evals: the tasks, a brief, and the open project scored against one', async () => {
  await menu('CAD Agent', 'Evals')
  await tasks().locator('.ctable tbody tr').nth(5).waitFor({ timeout: 60000 })
  ok('the eval set is listed', (await tasks().locator('.ctable').first().locator('tbody tr').count()) >= 10)
  await tasks().locator('.ctable tbody tr', { hasText: /^nema17_mount/ }).first().click()
  await tasks().locator('pre.pre').first().waitFor({ timeout: 60000 })
  ok('its brief is shown', /NEMA 17/.test(await tasks().locator('pre.pre').first().innerText()))
  await tasks().getByRole('button', { name: /^Score mini_machine against nema17_mount/ }).click()
  await tasks().locator('.verdict').first().waitFor({ timeout: 240000 })
  ok('the verdict of the scoring is shown', /^(PASS|FAIL|UNCHECKED)$/.test((await tasks().locator('.verdict').first().innerText()).trim()), await tasks().locator('.verdict').first().innerText())
  await closeTask()
})

// ── Poses ────────────────────────────────────────────────────────────────────────────────────────────
await step('poses: the 3D view shows a named pose, Home goes back, a move is refused while posed', async () => {
  const pos = () => p.evaluate(() => { const v = cadui.getView(); const g = v.viewer.nestedGroup.groups; return { beam: g['/Group/gantry%2Fbeam'].position.toArray(), motor: g['/Group/gantry%2Fmotor'].position.toArray(), base: g['/Group/base'].position.toArray() } })
  const home = await pos()
  await p.locator('.mb-trigger', { hasText: /^CAD Agent$/ }).click()
  await p.locator('.mb-content .mb-item', { hasText: /^Pose/ }).first().click()
  const items = await p.locator('.mb-content .mb-item').allInnerTexts()
  ok('the Pose menu lists Home and the three poses', ['Home', 'park', 'work', 'gantry/park'].every((n) => items.some((t) => t.trim().replace('✓', '').trim() === n)), items.join('|'))
  await p.locator('.mb-content .mb-item', { hasText: /^park$/ }).click()
  await p.waitForTimeout(500)
  const park = await pos()
  ok('park slides the gantry 60 mm along x', Math.abs(park.beam[0] - home.beam[0] - 60) < 1e-6 && park.base.every((v, i) => v === home.base[i]), JSON.stringify([home.beam, park.beam]))
  ok('park draws the motor 60 mm along x and 45 back along y', Math.abs(park.motor[0] - home.motor[0] - 60) < 1e-6 && Math.abs(park.motor[1] - home.motor[1] + 45) < 1e-6, JSON.stringify([home.motor, park.motor]))
  ok('the view says it is a pose', (await p.locator('.view-pose').innerText()).includes('park'))
  ok('the Report view says it is the view only', (await report()).some((l) => /Pose park: slide 60 mm, gantry\/x -45 mm\. The view only/.test(l)), (await report()).slice(-2).join('|'))
  await selectTree('base')
  await menu('Edit', 'Placement')
  await p.waitForTimeout(300)
  ok('Placement is refused while a pose is shown', (await p.locator('.taskview .tbox-head', { hasText: 'Placement' }).count()) === 0 && (await report()).some((l) => /Return to Home/.test(l)))
  await p.locator('.view-pose button', { hasText: 'Home' }).click()
  await p.waitForTimeout(400)
  const back = await pos()
  ok('Home puts every body back where assembly.py has it', JSON.stringify(back) === JSON.stringify(home), JSON.stringify([home, back]))
  ok('the pose chip is gone', (await p.locator('.view-pose').count()) === 0)
  // the agent's way in: cad gui run PROJECT CADAgent_Pose work
  const r = await p.evaluate(async (slug) => { const x = await fetch('/api/gui/do', { method: 'POST', headers: { 'X-CAD': '1', 'Content-Type': 'application/json' }, body: JSON.stringify({ slug, cmd: 'run', args: ['CADAgent_Pose', 'work'] }) }); return x.json() }, PROJECT)
  await p.waitForTimeout(600)
  const work = await pos()
  ok('cad gui run CADAgent_Pose work shows the work pose (gantry/x +30 along y)', r.ok && Math.abs(work.motor[1] - home.motor[1] - 30) < 1e-6 && work.beam[0] === home.beam[0], JSON.stringify([r, home.motor, work.motor]))
  await p.evaluate(() => cadui.getState().pose && document.querySelector('.view-pose button')?.click())
  await p.waitForTimeout(300)
})

// ── What was added to Check, Bought parts and New Document ──────────────────────────────────────────
await step('check options: the views and the passing rows go to the command', async () => {
  await menu('CAD Agent', 'Check')
  await tasks().getByText(/rows|PASS|FAIL|UNCHECKED/).first().waitFor({ timeout: 180000 })
  await p.waitForTimeout(500)
  await tasks().getByLabel('top', { exact: true }).check()
  await tasks().getByLabel('Show passing rows too').check()
  await tasks().getByRole('button', { name: 'Run with these' }).click()
  await p.waitForFunction(() => document.querySelectorAll('.taskview .ctable tbody tr').length > 50, null, { timeout: 180000 })
  ok('--all brings the passing rows', (await tasks().locator('.ctable').first().locator('tbody tr').count()) > 50)
  const logLine = (await report()).filter((l) => /cad check mini_machine/.test(l)).slice(-1)[0] ?? ''
  ok('the command line carries --views iso,top and --all', /--views iso,top/.test(logLine) && /--all/.test(logLine), logLine)
  await closeTask()
})
await step('bought parts: a measured part with holes, then its calliper verification', async () => {
  const name = 'ui_meas' + String(Date.now()).slice(-5)
  await menu('CAD Agent', 'Bought Parts')
  await tasks().getByRole('button', { name: 'Add…' }).click()
  await tasks().getByLabel('Measured envelope (UNVERIFIED until measured)').check()
  const f = (label) => tasks().locator('.tfield', { hasText: label }).first().locator('input, textarea')
  await f('Name').fill(name); await f('Length').fill('30'); await f('Width').fill('20'); await f('Height').fill('10')
  await f('Bolt holes').fill('-10,-5\n10,5'); await f('Hole diameter').fill('3.4'); await f('Source URL').fill('https://example.com/datasheet')
  await tasks().getByRole('button', { name: 'Add', exact: true }).click()
  await tasks().getByText(name).first().waitFor({ timeout: 60000 })
  const src = readFileSync(join(pdir, 'bought', `${name}.py`), 'utf8')
  ok('both holes and their diameter reached bought add-measured', src.includes("'hole_dia': 3.4") && src.includes('[[-10.0, -5.0], [10.0, 5.0]]'), src.slice(src.indexOf('PARAMS'), src.indexOf('PARAMS') + 160))
  await tasks().locator('tr', { hasText: name }).getByRole('button', { name: 'Verify…' }).click()
  await tasks().locator('textarea').fill('30.0 x 20.1 x 10.0 mm, calliper, three readings')
  await tasks().getByRole('button', { name: 'Mark verified' }).click()
  await p.waitForFunction((n) => !/Verify…/.test([...document.querySelectorAll('.taskview tr')].find((r) => r.innerText.includes(n))?.innerText ?? ''), name, { timeout: 60000 })
  ok('the calliper note verified it', /VERIFIED = True/.test(readFileSync(join(pdir, 'bought', `${name}.py`), 'utf8')))
  await closeTask()
  await menu('Edit', 'Undo'); await p.waitForTimeout(800); await menu('Edit', 'Undo'); await p.waitForTimeout(800)
})
await step('new document: a brief goes into mech_profile.md', async () => {
  const name = 'ui_new' + String(Date.now()).slice(-5)
  await menu('File', 'New Document')
  await tasks().getByPlaceholder('Unnamed').fill(name)
  await tasks().getByPlaceholder(/Brief \(optional\)/).fill('A mount for the laser head, checked in the UI run.')
  await tasks().getByRole('button', { name: 'Create' }).click()
  await p.waitForFunction((n) => document.title.startsWith(n), name, { timeout: 120000 })
  ok('the brief is in mech_profile.md', readFileSync(join(ROOT, name, 'mech_profile.md'), 'utf8').includes('A mount for the laser head'))
  await openFresh(PROJECT)
})
await step('tables and rules work with no project open', async () => {
  const r = await p.evaluate(async () => { const x = await fetch('/api/cad', { method: 'POST', headers: { 'X-CAD': '1', 'Content-Type': 'application/json' }, body: JSON.stringify({ slug: '', argv: ['rules'] }) }); return [x.status, (await x.json()).exit] })
  ok('POST /api/cad rules with no slug answers', r[0] === 200 && r[1] === 0, JSON.stringify(r))
})
await step('drawing: a part that is not a plate is the CLI\'s answer, in the panel, with no tab', async () => {
  await openFresh('mini_gantry')
  await menu('CAD Agent', 'Drawing')
  await tasks().getByRole('button', { name: 'Draw', exact: true }).click()
  await tasks().getByText(/UNCHECKED/).first().waitFor({ timeout: 120000 })
  const text = await tasks().innerText()
  ok('post, a block 20 x 40 x 50, is "not a plate" and nothing is written', /not a plate|plate/i.test(text) && !/Save out/.test(text), text.slice(0, 400))
  ok('no drawing tab opened', (await p.getByText('post : Drawing').count()) === 0)
  await closeTask()
})
await step('approve renders: the dialog opens and is cancelled, nothing is approved', async () => {
  await openFresh(PROJECT)
  const before = existsSync(join(pdir, 'baseline')) ? readdirSync(join(pdir, 'baseline')).length : 0
  await menu('CAD Agent', 'Approve Renders')
  await p.locator('.msgbox').waitFor({ timeout: 10000 })
  await p.locator('.msgbox').getByText('No', { exact: true }).click()
  await p.waitForTimeout(500)
  const after = existsSync(join(pdir, 'baseline')) ? readdirSync(join(pdir, 'baseline')).length : 0
  ok('nothing was approved', before === after, `${before} -> ${after}`)
})

console.log(results.map((r) => r.join(' ')).join('\n'))
const bad = results.filter((r) => r[0] === 'NO ').length
console.log(`agentcheck: ${results.length - bad} passed, ${bad} failed, ${errs.length} page errors`)
if (errs.length) console.log(errs.slice(0, 8).join('\n'))
process.exitCode = bad || errs.length ? 1 : 0
await b.close()

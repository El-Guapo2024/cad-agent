// Our workbench's screenshots, for the side-by-side with FreeCAD's (fcshots.py makes those): ours-<thing>.png at 1280 x 800.
//   NODE_PATH=<folder with playwright> node ui/scripts/oursshots.mjs URL PROJECT OUT_DIR [--only start,part,...] [--scale 1]
// URL is a workbench serving SCRATCH copies only (`bin/cad --projects <scratch> serve --port <yours>`; never the owner's ports).
// Each shot starts in a fresh browser context, so no saved setting of an earlier one reaches the next. The shots: start,
// start-cards (the first-start setup done), part (a part selected: the tree, the property view, the 3D view), navicube
// (the cube cropped; --scale 3 for a close-up), treemenu (the tree's context menu on a part), prefs-<page> (the Preferences
// dialog, cropped to the dialog, as FreeCAD's is its own window), report (the Report view with a message of each kind), sel (the 3D
// view in the isometric view, the part `chassis` unselected, preselected, selected, and both: ours-sel-<state>.png, to be read against
// fcmeasure.py's freecad-sel-<state>.png: a face of a selected object is #11ffff there, a preselected one #19b5df).
// Playwright drives the page with synthetic events: the pointer of the Mac is never moved.
import { createRequire } from 'module'
const require = createRequire(import.meta.url)
let chromium
try { ({ chromium } = require('playwright')) } catch { ({ chromium } = createRequire('/opt/node-tools/node_modules/')('playwright')) }
const args = process.argv.slice(2)
const opt = (name, d) => { const i = args.indexOf('--' + name); if (i < 0) return d; const [, v] = args.splice(i, 2); return v }
const ONLY = new Set((opt('only', '') || '').split(',').filter(Boolean))
const SCALE = Number(opt('scale', '1'))
const [BASE, PROJECT, OUT] = args
if (!BASE || !PROJECT || !OUT) { console.error('usage: oursshots.mjs URL PROJECT OUT_DIR [--only a,b] [--scale 1]'); process.exit(2) }
const want = (n) => !ONLY.size || ONLY.has(n)
const url = BASE.replace(/#.*$/, '').replace(/\/?$/, '/') // .../next/
const PAGES = [['general', 'General'], ['3dview', '3D View'], ['navigation', 'Navigation'], ['colors', 'Colors'], ['reportview', 'Report View']]
// WebGL on ANGLE's SwiftShader, as keycheck.mjs does (headless Chromium's own software fallback can freeze the first click on the 3D view).
const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--use-gl=angle', '--enable-unsafe-swiftshader'] })
const errs = []
const open = async (hash = '') => {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: SCALE })
  const p = await ctx.newPage()
  p.on('pageerror', (e) => errs.push(e.message))
  await p.goto(url + hash, { waitUntil: 'load' })
  await p.waitForTimeout(3500)
  return { ctx, p }
}
const to3d = async (p) => { await p.getByText(`${PROJECT} : 1`).first().click(); await p.waitForTimeout(3500) }
const out = (n) => `${OUT}/ours-${n}.png`
const done = []
const step = async (name, fn) => {
  if (!(want(name) || (name === 'prefs' && [...ONLY].some((o) => o.startsWith('prefs'))))) return
  try { await fn(); done.push(name) } catch (e) { errs.push(`${name}: ${e.message.split('\n')[0]}`) }
}

await step('start', async () => {
  const { ctx, p } = await open('')
  await p.screenshot({ path: out('start') })
  const b = p.getByRole('button', { name: 'Done', exact: true })
  // the page's own mouse, moved off the cards before the shot: a card's title (its path) would show as a tooltip over it
  if (await b.count()) { await b.click(); await p.mouse.move(700, 790); await p.waitForTimeout(1800); await p.screenshot({ path: out('start-cards') }) }
  await ctx.close()
})

// a part selected, as fcshots_dump.py's `part`: the default orientation fitted, the tree row and the Data tab
const selectPart = async (p) => {
  await to3d(p)
  await p.locator('.trow', { hasText: 'chassis' }).first().click()
  await p.waitForTimeout(1500)
}
await step('part', async () => {
  const { ctx, p } = await open('#' + PROJECT)
  await selectPart(p)
  await p.screenshot({ path: out('part') })
  await ctx.close()
})

await step('navicube', async () => {
  const { ctx, p } = await open('#' + PROJECT)
  await selectPart(p)
  const box = await p.locator('.navi-box').boundingBox()
  // FreeCAD's grab is the 150 px square at the top right of its 3D view; the same corner of ours
  const view = await p.locator('canvas').first().boundingBox()
  const s = 150
  const clip = { x: Math.round(view.x + view.width - s), y: Math.round(view.y), width: s, height: s }
  await p.screenshot({ path: out('navicube'), clip })
  await p.screenshot({ path: out('navicube-box'), clip: { x: Math.max(0, box.x - 6), y: Math.max(0, box.y - 6), width: box.width + 12, height: box.height + 12 } })
  await ctx.close()
})

await step('treemenu', async () => {
  const { ctx, p } = await open('#' + PROJECT)
  await selectPart(p)
  await p.locator('.trow', { hasText: 'chassis' }).first().click({ button: 'right' })
  await p.waitForTimeout(800)
  await p.screenshot({ path: out('treemenu') })
  await ctx.close()
})

await step('prefs', async () => {
  const { ctx, p } = await open('#' + PROJECT)
  await to3d(p)
  await p.keyboard.press('Meta+Comma')
  await p.waitForSelector('.pref-dlg', { timeout: 10000 })
  await p.waitForTimeout(800)
  for (const [key, label] of PAGES) {
    if (ONLY.size && !ONLY.has('prefs') && !ONLY.has('prefs-' + key)) continue
    await p.locator('.pref-item', { hasText: new RegExp('^' + label + '$') }).first().click()
    await p.waitForTimeout(700)
    await p.locator('.pref-dlg').screenshot({ path: out('prefs-' + key) })
  }
  await p.screenshot({ path: out('prefs-window') })
  await ctx.close()
})

// a toolbar button's tooltip (FreeCAD's QToolTip after the 700 ms wake-up), the toolbars and the tooltip cropped
await step('tooltip', async () => {
  const { ctx, p } = await open('#' + PROJECT)
  const btn = p.locator('button[title="Fit all (V, F)"]').first()
  await btn.hover()
  await p.waitForTimeout(1500)
  await p.screenshot({ path: out('tooltip'), clip: { x: 0, y: 24, width: 720, height: 140 } })
  await ctx.close()
})

await step('report', async () => {
  const { ctx, p } = await open('#' + PROJECT)
  await to3d(p)
  await p.locator('.trow', { hasText: 'chassis' }).first().click()
  await p.waitForTimeout(800)
  // A warning and an error, as fcshots_dump.py prints in FreeCAD's report view: the page's own message list (store.ts report()),
  // written with the setState the console exposes, since no gentle command here makes the CLI fail on cue.
  await p.evaluate(() => cadui.setState((s) => ({ messages: [...s.messages,
    { t: Date.now(), level: 'warn', text: '2 unchecked' },
    { t: Date.now(), level: 'err', text: 'wheel_left was placed, but a fit check fails: overlap 469.841 mm^3' }] })))
  await p.waitForTimeout(800)
  await p.screenshot({ path: out('report') })
  await ctx.close()
})

// the selection colours as the 3D view draws them: the same isometric view as fcmeasure_dump.py's, the 3D view only
await step('sel', async () => {
  const { ctx, p } = await open('#' + PROJECT)
  await to3d(p)
  await p.evaluate(() => cadui.getView().viewDir('iso'))
  await p.waitForTimeout(1500)
  await p.evaluate(() => cadui.getView().fitAll())
  await p.waitForTimeout(1500)
  const states = { none: { selected: [], preselected: null }, preselected: { selected: [], preselected: 'chassis' },
    selected: { selected: ['chassis'], preselected: null }, 'selected-and-preselected': { selected: ['chassis'], preselected: 'chassis' } }
  const view = await p.locator('canvas').first().boundingBox()
  for (const [name, st] of Object.entries(states)) {
    await p.evaluate((x) => cadui.setState(x), st)
    await p.waitForTimeout(900)
    await p.screenshot({ path: out(`sel-${name}`), clip: { x: view.x + 20, y: view.y + 20, width: view.width - 40, height: view.height - 40 } })
  }
  await ctx.close()
})

console.log(`oursshots: ${done.join(', ')} -> ${OUT}`)
if (errs.length) console.log('oursshots: problems:\n  ' + errs.join('\n  '))
await browser.close()

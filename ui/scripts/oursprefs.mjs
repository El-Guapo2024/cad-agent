// Every Preferences page of the workbench, read off the page the way fcprefs.py reads the real FreeCAD's (fcprefsdiff.py compares the two).
//   NODE_PATH=<folder with playwright> node ui/scripts/oursprefs.mjs URL PROJECT OUT_DIR [--only general,navigation] [--tall 1900] [--shots]
// PROJECT is a project name, or - for none. URL is a workbench serving SCRATCH copies only (`bin/cad --projects <scratch> serve --port <yours>`; never the owner's ports). A fresh
// browser context, so no saved setting reaches the page: the defaults it shows are the defaults of a first start. Writes OUT_DIR/oursprefs.json:
// the dialog's metrics, and per page every widget that has an object name (data-qf: the form's widgets by the name FreeCAD's .ui gives
// them) with its rectangle in the page's coordinates, text, state and value; --shots also writes ours-prefs-<page>.png (the dialog) and
// ours-prefs-<page>-tall.png (tall enough for the page not to scroll). Playwright drives the page with synthetic events: the pointer of the
// Mac is never moved.
import { createRequire } from 'module'
import { mkdirSync, writeFileSync } from 'fs'
const require = createRequire(import.meta.url)
let chromium
try { ({ chromium } = require('playwright')) } catch { ({ chromium } = createRequire('/opt/node-tools/node_modules/')('playwright')) }
const args = process.argv.slice(2)
const opt = (name, d) => { const i = args.indexOf('--' + name); if (i < 0) return d; const [, v] = args.splice(i, 2); return v }
const flag = (name) => { const i = args.indexOf('--' + name); if (i < 0) return false; args.splice(i, 1); return true }
const ONLY = new Set((opt('only', '') || '').split(',').filter(Boolean))
const TALL = Number(opt('tall', '1900'))
const SHOTS = flag('shots')
const [BASE, PROJECT, OUT] = args
if (!BASE || !PROJECT || !OUT) { console.error('usage: oursprefs.mjs URL PROJECT OUT_DIR [--only a,b] [--tall 1900] [--shots]'); process.exit(2) }
mkdirSync(OUT, { recursive: true })
const url = BASE.replace(/#.*$/, '').replace(/\/?$/, '/')
// our page labels, by the key fcprefs_dump.py names them
const PAGES = [['general', 'General', 0], ['document', 'Document'], ['selection', 'Selection'], ['keyboard', 'Keyboard'], ['cache', 'Cache'], ['notificationarea', 'Notification Area'],
  ['reportview', 'Report View'], ['3dview', '3D View'], ['lightsources', 'Light Sources'], ['ui', 'UI'], ['navigation', 'Navigation'], ['colors', 'Colors'], ['advanced', 'Advanced'],
  ['workbenches', 'Available Workbenches'], ['pdf', 'PDF'], ['macro', 'Macro'], ['pythongeneral', 'General', 1], ['editor', 'Editor']]
// scrollbars shown (headless Chromium hides them): a page that scrolls is narrower by one, as in FreeCAD's dialog
const browser = await chromium.launch({ ignoreDefaultArgs: ['--hide-scrollbars'], args: ['--use-angle=swiftshader', '--use-gl=angle', '--enable-unsafe-swiftshader'] })
const ctx = await browser.newContext({ viewport: { width: 1400, height: TALL + 140 }, deviceScaleFactor: 1 })
const p = await ctx.newPage()
const errs = []
p.on('pageerror', (e) => errs.push(e.message))
p.on('console', (m) => { if (m.type() === 'error' && !/favicon|Failed to load resource/.test(m.text())) errs.push('console: ' + m.text()) })
await p.goto(url + (PROJECT === '-' ? '' : '#' + PROJECT), { waitUntil: 'load' })   // '-': no project (the Start page), which spares the CAD worker
await p.waitForTimeout(3500)
await p.evaluate(() => cadui.setState({ prefsOpen: true }))
await p.waitForSelector('.pref-dlg', { timeout: 10000 })
await p.waitForTimeout(800)

/** The dump script runs in the page: widgets of the open page by object name, with the rectangle in the page's own coordinates. */
const dump = () => p.evaluate(() => {
  const page = document.querySelector('.pref-page .qf-page') ?? document.querySelector('.pref-page')
  const o = page.getBoundingClientRect()
  const widgets = {}
  const hidden = (el) => !!el.closest('[hidden]') || getComputedStyle(el).display === 'none'
  for (const el of document.querySelectorAll('.pref-page [data-qf]')) {
    const name = el.dataset.qf
    const r = el.getBoundingClientRect()
    const w = { rect: [Math.round(r.x - o.x), Math.round(r.y - o.y), Math.round(r.width), Math.round(r.height)], visible: !hidden(el) && r.width > 0 && r.height > 0, tip: el.getAttribute('title') ?? el.getAttribute('data-fc-title') ?? '' }
    const cs = getComputedStyle(el)
    w.font = cs.fontSize
    if (el.matches('.qf-gb')) { w.kind = 'group'; w.title = el.querySelector('.qf-gb-title')?.textContent?.trim(); const c = el.querySelector('.qf-gb-title input'); if (c) { w.checkable = true; w.checked = c.checked; w.disabled = c.disabled } }
    else if (el.matches('.qf-check')) { const i = el.querySelector('input'); w.kind = i.type; w.text = el.textContent.trim(); w.checked = i.checked; w.disabled = i.disabled }
    else if (el.matches('.qf-label')) { w.kind = 'label'; w.text = el.textContent.trim(); w.disabled = el.classList.contains('off') }
    else if (el.matches('.qf-spin')) { const i = el.querySelector('input'); w.kind = 'spin'; w.text = i.value; w.disabled = i.disabled }
    else if (el.matches('.qf-combo')) { w.kind = 'combo'; w.text = el.querySelector('.combo-label')?.textContent ?? ''; w.disabled = el.disabled }
    else if (el.matches('.qf-btn, .qf-tool')) { w.kind = 'button'; w.text = el.textContent.trim(); w.disabled = el.disabled }
    else if (el.matches('.qf-color')) { w.kind = 'color'; w.disabled = el.querySelector('button').disabled; w.color = el.querySelector('.qf-swatch')?.style.background ?? '' }
    else if (el.matches('.qf-edit')) { w.kind = 'edit'; w.text = el.value; w.disabled = el.disabled }
    else if (el.matches('.qf-sheet')) { w.kind = 'sheet'; w.text = el.textContent.trim().slice(0, 200) }
    else if (el.matches('.qf-node')) { w.kind = 'node'; w.text = el.textContent.trim().slice(0, 200) }
    else w.kind = 'other'
    widgets[name] = w
  }
  return { page: { rect: [0, 0, Math.round(o.width), Math.round(o.height)] }, widgets }
})

const dialog = await p.evaluate(() => {
  const r = (sel) => { const e = document.querySelector(sel); if (!e) return null; const b = e.getBoundingClientRect(), d = document.querySelector('.pref-dlg').getBoundingClientRect(); return [Math.round(b.x - d.x), Math.round(b.y - d.y), Math.round(b.width), Math.round(b.height)] }
  return { size: r('.pref-dlg').slice(2), sidebar: r('.pref-side'), tree: r('.pref-tree'), header: r('.pref-header'), search: r('.pref-search input'), scroll: r('.pref-scroll'), reset: r('.pref-side > .qbtn'),
    buttons: [...document.querySelectorAll('.pref-buttons .qbtn')].map((b) => { const bb = b.getBoundingClientRect(), d = document.querySelector('.pref-dlg').getBoundingClientRect(); return { text: b.textContent, rect: [Math.round(bb.x - d.x), Math.round(bb.y - d.y), Math.round(bb.width), Math.round(bb.height)] } }),
    rows: [...document.querySelectorAll('.pref-group, .pref-item')].filter((e) => !e.closest('[hidden]') && !e.hidden).map((e) => { const bb = e.getBoundingClientRect(), t = document.querySelector('.pref-tree').getBoundingClientRect(); return { text: e.textContent.trim(), group: e.classList.contains('pref-group'), rect: [Math.round(bb.x - t.x), Math.round(bb.y - t.y), Math.round(bb.width), Math.round(bb.height)] } }) }
})
const res = { dialog, pages: {}, errors: errs }

for (const [key, label, nth = 0] of PAGES) {
  if (ONLY.size && !ONLY.has(key)) continue
  // the tree shows only the open group's pages: pick the page the way a click does (a click on a hidden row is a script's, not a person's)
  await p.evaluate(([l, n]) => { const items = [...document.querySelectorAll('.pref-item')].filter((e) => e.textContent.trim() === l); items[n].click() }, [label, nth])
  await p.waitForTimeout(700)
  // the dialog at its natural size, then tall enough for the page not to scroll
  await p.evaluate(() => { const d = document.querySelector('.pref-dlg'); d.style.width = '966px'; d.style.height = '928px' })
  await p.waitForTimeout(300)
  if (SHOTS) await p.locator('.pref-dlg').screenshot({ path: `${OUT}/ours-prefs-${key}.png` })
  // the rectangles are read at the natural size, as fcprefs.py reads the real dialog's
  res.pages[key] = await dump()
  res.pages[key].header = await p.locator('.pref-header').textContent()
  await p.evaluate((h) => { const d = document.querySelector('.pref-dlg'); d.style.height = (h + 28) + 'px'; d.style.maxHeight = 'none' }, TALL)
  await p.waitForTimeout(500)
  if (SHOTS) await p.locator('.pref-dlg').screenshot({ path: `${OUT}/ours-prefs-${key}-tall.png` })
  await p.evaluate(() => { const d = document.querySelector('.pref-dlg'); d.style.height = ''; d.style.width = ''; d.style.maxHeight = '' })
}
writeFileSync(`${OUT}/oursprefs.json`, JSON.stringify(res, null, 1))
console.log(`oursprefs: ${Object.keys(res.pages).length} pages -> ${OUT}/oursprefs.json`)
if (errs.length) console.log('oursprefs: problems:\n  ' + errs.join('\n  '))
await browser.close()

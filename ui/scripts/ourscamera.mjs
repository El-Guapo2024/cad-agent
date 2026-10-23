// Measures what our view does with the Custom default camera orientation, the way fcbehave.py's section "custom_camera" measures
// FreeCAD's (fcbehave_dump.py custom_camera): for each View/Custom Q0..Q3 the orientation of a new view and of Home from the Front
// view; then the Camera Settings dialog the Navigation page opens when Custom is picked (what it shows, what typing 0.12345 and -1.5
// and Current View put in it, what OK keeps, and Home after the Preferences dialog's OK). Writes OUT.json and, given FreeCAD's file,
// prints where the two differ.
//   NODE_PATH=<folder with playwright> node ui/scripts/ourscamera.mjs URL PROJECT OUT.json [fcbehave.json]
// URL is a workbench serving SCRATCH copies only; each case is a fresh browser context, whose storage holds the parameters.
import { createRequire } from 'module'
import { readFileSync, writeFileSync } from 'fs'
const require = createRequire(import.meta.url)
let chromium
try { ({ chromium } = require('playwright')) } catch { ({ chromium } = createRequire('/opt/node-tools/node_modules/')('playwright')) }
const [BASE, PROJECT, OUT, FC] = process.argv.slice(2)
if (!BASE || !PROJECT || !OUT) { console.error('usage: ourscamera.mjs URL PROJECT OUT.json [fcbehave.json]'); process.exit(2) }
const url = BASE.replace(/#.*$/, '').replace(/\/?$/, '/')
// the same cases as fcbehave_dump.py's CUSTOM_QS
const CASES = [['near unit', [0.1, 0.2, 0.3, 0.9]], ['right', [0.5, 0.5, 0.5, 0.5]], ['not unit', [1, 1, 0, 0]], ['zero', [0, 0, 0, 0]],
  ['negative w', [0.2, -0.3, 0.1, -0.9]], ['unset', null]]
const b = await chromium.launch({ args: ['--use-angle=swiftshader', '--use-gl=angle', '--enable-unsafe-swiftshader'] })
const errs = []
async function page(params) {
  const ctx = await b.newContext({ viewport: { width: 1280, height: 800 } })
  await ctx.addInitScript((kv) => { for (const [k, v] of Object.entries(kv)) localStorage.setItem('cadui.' + k, JSON.stringify(v)) }, params)
  const p = await ctx.newPage()
  p.on('pageerror', (e) => errs.push(e.message))
  await p.goto(url + '#' + PROJECT, { waitUntil: 'load' })
  await p.waitForTimeout(3500)
  await p.getByText(`${PROJECT} : 1`).first().click()
  await p.waitForTimeout(3000)
  return { ctx, p }
}
const settle = async (p) => {
  for (let i = 0; i < 80; i++) { const s = await p.evaluate(() => cadui.getView().probe()); if (s && !s.animating && !s.pendingFrame) break; await p.waitForTimeout(100) }
  await p.waitForTimeout(200)
}
const q = (p) => p.evaluate(() => cadui.getView().probe().camera)
const home = async (p) => {
  await p.evaluate(() => cadui.getView().viewDir('front')); await settle(p)
  await p.evaluate(() => document.activeElement?.blur?.()); await p.keyboard.press('Home'); await settle(p)
  return q(p)
}
const out = { cases: {} }
for (const [name, cq] of CASES) {
  const { ctx, p } = await page(cq ? { homeView: 'Custom', customCamera: cq } : { homeView: 'Custom' })
  const r = { new_document: await q(p) }
  r.home = await home(p)
  out.cases[name] = r
  await ctx.close()
}
// the dialog, from a profile whose orientation is Top, with the camera at Trimetric
{
  const { ctx, p } = await page({ homeView: 'Top' })
  await p.evaluate(() => cadui.getView().viewDir('trimetric')); await settle(p)
  const d = { camera_before_dialog: await q(p) }
  await p.evaluate(() => cadui.setState({ prefsOpen: true })); await p.waitForTimeout(500)
  await p.locator('.pref-group', { hasText: 'Display' }).first().click(); await p.waitForTimeout(300)
  await p.locator('.pref-item', { hasText: /^Navigation$/ }).first().click(); await p.waitForTimeout(500)
  const combo = p.locator('.pref-page [data-qf="comboNewDocView"]').first()
  d.combo_before = (await combo.innerText()).trim()
  await combo.focus(); await p.keyboard.type('Custom'); await p.waitForTimeout(400)
  const dlg = p.locator('.camdlg')
  const read = () => dlg.locator('.qf-spin input').evaluateAll((es) => es.map((e) => e.value))
  d.opened = { title: (await dlg.locator('.msgbox-title').innerText()).trim(), spin_text: await read(), labels: await dlg.locator('label, .qf-label, [data-qf^="label"]').allInnerTexts(),
    buttons: await dlg.locator('button.qf-btn, .camdlg-buttons button').allInnerTexts(), group: (await dlg.locator('.qf-gb-title').innerText()).trim() }
  const typeIn = async (i, text) => { const e = dlg.locator('.qf-spin input').nth(i); await e.fill(text); await e.press('Tab') }
  await typeIn(0, '0.12345'); await typeIn(1, '-1.5')
  d.typed_text = await read()
  await dlg.locator('[data-qf="currentView"]').click(); await p.waitForTimeout(200)
  d.current_view_text = await read()
  await dlg.locator('.camdlg-buttons button', { hasText: 'OK' }).click(); await p.waitForTimeout(300)
  d.combo_after = (await combo.innerText()).trim()
  d.params_before_ok = await p.evaluate(() => ({ orientation: cadui.getState().homeView, q: cadui.getState().customCamera }))
  await p.locator('.pref-buttons button', { hasText: /^OK$/ }).click(); await p.waitForTimeout(300)
  d.params_after_ok = await p.evaluate(() => ({ orientation: cadui.getState().homeView, q: cadui.getState().customCamera }))
  d.home_after_ok = await home(p)
  out.dialog = d
  await ctx.close()
}
out.errors = errs
writeFileSync(OUT, JSON.stringify(out, null, 1))
await b.close()

if (FC) {
  const fc = JSON.parse(readFileSync(FC, 'utf8')).custom_camera
  // a rotation and its negative are the same turn: the angle between them, in degrees
  // (both normalized first: a float32 quaternion is unit only to about 1e-8, which acos near 1 turns into a hundredth of a degree)
  const n = (v) => { const l = Math.hypot(...v); return v.map((x) => x / l) }
  const qd = (a, c) => { const [x, y] = [n(a), n(c)]; const d = Math.abs(x[0] * y[0] + x[1] * y[1] + x[2] * y[2] + x[3] * y[3]); return (2 * Math.acos(Math.min(1, d)) * 180) / Math.PI }
  const f = (v) => v.map((x) => x.toFixed(4)).join(' ')
  let bad = 0
  const row = (label, o, c) => {
    const zero = c.every((x) => x === 0) // Coin keeps a zero quaternion (drawn as Top); ours is Top's unit one
    const diff = zero ? qd(o, [0, 0, 0, 1]) : qd(o, c), ok = diff < 1e-3
    if (!ok) bad++
    console.log(`${ok ? '   ok' : ' DIFF'}  ${label.padEnd(34)} ours ${f(o)} | FreeCAD ${f(c)}${zero ? ' (zero: compared with Top)' : ''}${ok ? '' : `  ${diff.toFixed(4)} deg`}`)
  }
  for (const [name] of CASES) {
    row(`${name}: new view`, out.cases[name].new_document, fc.cases[name].new_document)
    row(`${name}: Home from Front`, out.cases[name].home, fc.cases[name].home)
  }
  const o = out.dialog, c = fc.dialog
  const same = (label, a, x) => { const ok = JSON.stringify(a) === JSON.stringify(x); if (!ok) bad++; console.log(`${ok ? '   ok' : ' DIFF'}  ${label.padEnd(34)} ours ${JSON.stringify(a)} | FreeCAD ${JSON.stringify(x)}`) }
  same('dialog title', o.opened.title, c.opened.title)
  same('dialog group', o.opened.group, c.opened.groups.map((g) => g.title)[0])
  same('dialog shows', o.opened.spin_text, c.opened.spin.map((s) => s.text))
  same('typed 0.12345, -1.5', o.typed_text.slice(0, 2), c.typed.slice(0, 2).map((v) => v.toFixed(2)))
  same('Current View', o.current_view_text, c.current_view_text)
  same('combo before / after', [o.combo_before, o.combo_after], [c.combo_before, c.combo_after])
  same('written on OK', [o.params_after_ok.orientation, o.params_after_ok.q], [c.params_after_ok.orientation, c.params_after_ok.q])
  row('Home after OK', o.home_after_ok, c.home_after_ok)
  console.log(`${bad} differ${errs.length ? `; page errors: ${errs.join('; ')}` : ''}`)
}

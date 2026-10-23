// SPDX-License-Identifier: LGPL-2.1-or-later
// Our NaviCube's shots, the same as navishots_dump.py takes of FreeCAD's: OUT/ours-<shot>.png, the 180 px square at the top
// right of the 3D view.  NODE_PATH=<folder with playwright> node ui/scripts/navishots_ours.mjs URL PROJECT OUT SHOTS_JSON
// URL is a workbench serving SCRATCH copies only (never the owner's ports); navishots.py passes SHOTS_JSON.
import { createRequire } from 'module'
const require = createRequire(import.meta.url)
const { chromium } = require('playwright')
const [BASE, PROJECT, OUT, SHOTS] = process.argv.slice(2)
const shots = JSON.parse(SHOTS)
// WebGL on ANGLE's SwiftShader, as keycheck.mjs and oursshots.mjs do.
const b = await chromium.launch({ args: ['--use-angle=swiftshader', '--use-gl=angle', '--enable-unsafe-swiftshader'] })
const ctx = await b.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 })
const p = await ctx.newPage()
const errs = []
p.on('pageerror', (e) => errs.push(e.message))
await p.goto(BASE.replace(/#.*$/, '').replace(/\/?$/, '/') + '#' + PROJECT, { waitUntil: 'load' })
await p.waitForSelector('.trow .tname', { timeout: 120000 }); await p.waitForTimeout(1500)
{ const done = p.getByRole('button', { name: 'Done', exact: true }); if (await done.count()) await done.click() }
await p.getByText(`${PROJECT} : 1`).first().click(); await p.waitForTimeout(2500)
await p.evaluate(() => cadui.setState({ animate: false }))
const host = await p.locator('.view3d-host canvas').first().boundingBox()
const cx = host.x + host.width - 72, cy = host.y + 72
const clip = { x: host.x + host.width - 180, y: host.y, width: 180, height: 180 }
const shot = async (name) => { await p.waitForTimeout(500); await p.screenshot({ path: `${OUT}/ours-${name}.png`, clip }) }
const ISO = [0.424708, 0.17592, 0.339851, 0.820473]
for (const [name, q] of Object.entries(shots.orient)) {
  if (q === 'persp') await p.evaluate(() => cadui.getView().setOrtho(false))
  await p.evaluate((q) => cadui.getView().orient(q.map((c) => c / Math.hypot(...q))), q === 'persp' ? ISO : q)
  await p.waitForTimeout(800)
  await p.mouse.move(host.x + host.width / 2, host.y + host.height / 2); await shot(name + '-away')
  await p.mouse.move(cx, cy); await shot(name + '-near')
  if (q === 'persp') await p.evaluate(() => cadui.getView().setOrtho(true))
}
await p.evaluate((q) => cadui.getView().orient(q), ISO)
await p.waitForTimeout(800)
for (const [name, [dx, dy]] of Object.entries(shots.hover)) { await p.mouse.move(cx + dx, cy + dy); await shot(name) }
if (errs.length) console.error(errs.join('\n'))
await b.close()

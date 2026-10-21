// Measures our 3D view the way fcbehave.py measures FreeCAD's, through cadui.getView().probe(): the camera orientation
// after each standard view, the default orientation and Home, rotate left and right, the zoom a wheel notch and the zoom
// keys make, and the settings the Navigation page starts with. Writes OUT.json (same names as fcbehave.json) and prints a
// comparison with it when given the FreeCAD file.
//   NODE_PATH=<folder with playwright> node ui/scripts/oursbehave.mjs URL PROJECT OUT.json [fcbehave.json]
// URL is a workbench serving SCRATCH copies only. It changes only the view. The pointer of the Mac is never moved.
import { createRequire } from 'module'
import { readFileSync, writeFileSync } from 'fs'
const require = createRequire(import.meta.url)
let chromium
try { ({ chromium } = require('playwright')) } catch { ({ chromium } = createRequire('/opt/node-tools/node_modules/')('playwright')) }
const [BASE, PROJECT, OUT, FC] = process.argv.slice(2)
if (!BASE || !PROJECT || !OUT) { console.error('usage: oursbehave.mjs URL PROJECT OUT.json [fcbehave.json]'); process.exit(2) }
const url = BASE.replace(/#.*$/, '').replace(/\/?$/, '/')
const b = await chromium.launch({ args: ['--use-angle=swiftshader', '--use-gl=angle', '--enable-unsafe-swiftshader'] })
const ctx = await b.newContext({ viewport: { width: 1280, height: 800 } })
const p = await ctx.newPage()
const errs = []; p.on('pageerror', (e) => errs.push(e.message))
await p.goto(url + '#' + PROJECT, { waitUntil: 'load' })
await p.waitForTimeout(3500)
await p.getByText(`${PROJECT} : 1`).first().click()
await p.waitForTimeout(4000)

// Fit All is a few timed steps (nav.ts), not an animation `probe().animating` reports: wait until the camera has stopped.
const still = async (page) => {
  let last = '', same = 0
  for (let i = 0; i < 60 && same < 3; i++) {
    const s = await page.evaluate(() => { const v = cadui.getView().probe(); return JSON.stringify([v.zoom, v.position, v.target]) })
    same = s === last ? same + 1 : 0; last = s
    await page.waitForTimeout(250)
  }
}
const probe = () => p.evaluate(() => cadui.getView().probe())
const settle = async () => {
  for (let i = 0; i < 80; i++) { const s = await probe(); if (s && !s.animating && !s.pendingFrame) break; await p.waitForTimeout(100) }
  await p.waitForTimeout(200)
}
const snap = async () => {
  const s = await probe()
  const q = s.camera, v = (a, k) => a // keep the raw numbers
  // direction the camera looks along (-z of its frame) and its up (y), from the quaternion
  const rot = ([x, y, z, w], [a, b, c]) => { const ux = y * c - z * b, uy = z * a - x * c, uz = x * b - y * a; const tx = 2 * ux, ty = 2 * uy, tz = 2 * uz; return [a + w * tx + (y * tz - z * ty), b + w * ty + (z * tx - x * tz), c + w * tz + (x * ty - y * tx)] }
  return { q, dir: rot(q, [0, 0, -1]), up: rot(q, [0, 1, 0]), position: s.position, target: s.target, zoom: s.zoom, ortho: s.ortho, cube: s.cube }
}
const out = { errors: {} }
out.initial = await snap()
// every standard view starts from the same view (front) and, as FreeCAD's, keeps the zoom and the target
const viewNames = { viewFront: 'front', viewTop: 'top', viewRight: 'right', viewRear: 'rear', viewBottom: 'bottom', viewLeft: 'left', viewIsometric: 'iso', viewDimetric: 'dimetric', viewTrimetric: 'trimetric' }
out.views = {}
for (const [fc, name] of Object.entries(viewNames)) {
  await p.evaluate(() => cadui.getView().viewDir('front')); await settle()
  const before = await snap()
  await p.evaluate((n) => cadui.getView().viewDir(n), name); await settle()
  const s = await snap(); s.zoom_before = before.zoom; s.target_before = before.target
  out.views[fc] = s
}
// Home (the Home key: the default orientation, fitted), from the front view
const press = async (k) => { await p.evaluate(() => document.activeElement?.blur?.()); await p.keyboard.press(k) }
await p.evaluate(() => cadui.getView().viewDir('front')); await settle()
await press('Home'); await settle()
out.home = await snap()
// rotate left and right, from the front view
out.rotates = {}
for (const [fc, key] of [['viewRotateLeft', 'Shift+ArrowLeft'], ['viewRotateRight', 'Shift+ArrowRight']]) {
  await p.evaluate(() => cadui.getView().viewDir('front')); await settle()
  await press(key); await settle()
  out.rotates[fc] = await snap()
}
// zoom: a wheel notch over the middle of the view (Playwright's wheel: a page event, the pointer does not move)
const box = await p.locator('canvas').first().boundingBox()
const cx = box.x + box.width / 2, cy = box.y + box.height / 2
await p.evaluate(() => cadui.getView().viewDir('iso')); await settle()
await p.evaluate(() => cadui.getView().fitAll()); await settle(); await still(p)
const z = async () => (await probe()).zoom
const z0 = await z()
await p.mouse.move(cx, cy)
await p.mouse.wheel(0, -120); await p.waitForTimeout(400)
const z1 = await z()
// the page's zoom is the camera's zoom (bigger = closer); FreeCAD's number is the height (smaller = closer): 1/ratio
out.zoom = { wheel_up_1: { z0, z1, height_ratio: z0 / z1 } }
await p.mouse.wheel(0, 120); await p.waitForTimeout(400)
const z2 = await z()
out.zoom.wheel_down_1_after_up_1 = { ratio_vs_h1: z1 / z2 }
for (let i = 0; i < 5; i++) { await p.mouse.wheel(0, -120); await p.waitForTimeout(150) }
await p.waitForTimeout(300)
const z3 = await z()
out.zoom.wheel_up_5_more = { ratio_vs_h2: z2 / z3 }
await p.evaluate(() => cadui.getView().fitAll()); await settle(); await still(p)
const z4 = await z()
await press('Meta+Equal'); await p.waitForTimeout(500)
const z5 = await z()
await press('Meta+Minus'); await p.waitForTimeout(500)
const z6 = await z()
out.zoom.zoomIn = { ratio: z4 / z5 }
out.zoom.zoomOut_after_zoomIn = { ratio_vs_zoomIn: z5 / z6 }
// settings the Navigation page starts with
out.nav_state = await p.evaluate(() => { const s = cadui.getState(); return { navCube: s.naviCube, nav: s.navPrefs, homeView: s.homeView, newDocCameraScale: s.newDocCameraScale, rotationCenter: s.rotationCenter, disableTouchTilt: s.disableTouchTilt } })
// CAD style's mouse (middle drag pans, middle+left or middle+right rotates) at the size of FreeCAD's 3D view, which the angles
// depend on: the page is resized until its canvas is the viewer fcbehave.py recorded (1014 x 661 in its 1280 x 800 window).
{
  const fcFile = FC ? JSON.parse(readFileSync(FC, 'utf8')) : null
  const [vw, vh] = fcFile?.drags?.viewer ?? [1014, 661]
  let W = 1280 + (vw - 936), H = 800 + (vh - 463)
  const ctx2 = await b.newContext({ viewport: { width: W, height: H } })
  const q = await ctx2.newPage()
  await q.goto(url + '#' + PROJECT, { waitUntil: 'load' })
  await q.waitForTimeout(3500)
  await q.getByText(`${PROJECT} : 1`).first().click()
  await q.waitForTimeout(3500)
  let box = await q.locator('canvas').first().boundingBox()
  for (let i = 0; i < 3; i++) {
    W += Math.round(vw - box.width); H += Math.round(vh - box.height)
    await q.setViewportSize({ width: W, height: H }); await q.waitForTimeout(1500)
    box = await q.locator('canvas').first().boundingBox()
  }
  const probe2 = () => q.evaluate(() => cadui.getView().probe())
  const settle2 = async () => { for (let i = 0; i < 80; i++) { const s = await probe2(); if (s && !s.animating && !s.pendingFrame) break; await q.waitForTimeout(100) } await q.waitForTimeout(250) }
  const qangle = (a, c) => { const d = Math.abs(a[0] * c[0] + a[1] * c[1] + a[2] * c[2] + a[3] * c[3]); return (2 * Math.acos(Math.min(1, d)) * 180) / Math.PI }
  const worldH = () => q.evaluate(() => { const c = cadui.getView().cameraParts().cam; return (c.top - c.bottom) / c.zoom })
  const cx = box.x + box.width / 2, cy = box.y + box.height / 2
  out.drags = { viewer: [Math.round(box.width), Math.round(box.height)] }
  for (const [name, buttons, dx, dy] of [['MMB drag right 100 (pan)', ['middle'], 100, 0], ['MMB+LMB drag right 100 (rotate)', ['middle', 'left'], 100, 0],
    ['MMB+LMB drag down 100 (rotate)', ['middle', 'left'], 0, 100], ['MMB+RMB drag right 100 (rotate)', ['middle', 'right'], 100, 0]]) {
    await q.evaluate(() => cadui.getView().viewDir('iso')); await settle2()
    await q.evaluate(() => cadui.getView().fitAll()); await settle2(); await still(q)
    const s0 = await probe2(), h0 = await worldH()
    await q.mouse.move(cx, cy)
    for (const bt of buttons) await q.mouse.down({ button: bt })
    for (let i = 1; i <= 20; i++) { await q.mouse.move(cx + (dx * i) / 20, cy + (dy * i) / 20); await q.waitForTimeout(25) }
    for (const bt of [...buttons].reverse()) await q.mouse.up({ button: bt })
    await q.waitForTimeout(500)
    const s1 = await probe2()
    out.drags[name] = { angle_deg: qangle(s0.camera, s1.camera), moved_in_view_heights: Math.hypot(...s1.position.map((v, i) => v - s0.position[i])) / h0 }
  }
  await ctx2.close()
}
writeFileSync(OUT, JSON.stringify(out, null, 1))
if (errs.length) console.log('page errors:', errs)
await b.close()

if (FC) {
  const fc = JSON.parse(readFileSync(FC, 'utf8'))
  const qd = (a, b) => { const d = Math.abs(a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]); return (2 * Math.acos(Math.min(1, d)) * 180) / Math.PI }
  const f = (x) => (x == null ? '-' : Number(x).toFixed(4))
  console.log('view'.padEnd(24), 'angle diff (deg)', ' ours dir', '| FreeCAD dir')
  for (const k of [...Object.keys(viewNames), 'viewDefaultOrientation']) {
    // viewDefaultOrientation() is what a new view looks along (the NewDocumentCameraOrientation or, unset, Trimetric); Home has its own fallback (Top)
    const o = k === 'viewDefaultOrientation' ? out.initial : out.views[k], c = fc.views[k]
    if (!o || !c) continue
    console.log(k.padEnd(24), qd(o.q, c.q).toFixed(5).padStart(12), ' ', o.dir.map(f).join(' '), '|', c.dir.map(f).join(' '))
  }
  for (const k of ['viewRotateLeft', 'viewRotateRight']) console.log(k.padEnd(24), qd(out.rotates[k].q, fc.rotates[k].q).toFixed(5).padStart(12), ' ', out.rotates[k].dir.map(f).join(' '), '|', fc.rotates[k].dir.map(f).join(' '))
  console.log('home vs FreeCAD Home    ', qd(out.home.q, fc.home.q).toFixed(5), ' (FreeCAD Home from the front view)', fc.home.q.map(f).join(' '), '| ours', out.home.q.map(f).join(' '))
  console.log('zoom: ours', JSON.stringify(out.zoom), '\n      FreeCAD', JSON.stringify(Object.fromEntries(Object.entries(fc.zoom).filter(([k]) => k !== 'trackpad_scroll_60').map(([k, v]) => [k, v.ratio ?? v.ratio_vs_h1 ?? v.ratio_vs_h2 ?? v.ratio_vs_zoomIn]))))
  for (const k of Object.keys(out.drags)) {
    if (k === 'viewer') { console.log('mouse drags at the viewer size: ours', out.drags.viewer.join(' x '), 'FreeCAD', (fc.drags?.viewer ?? []).join(' x ')); continue }
    const o = out.drags[k], c = fc.drags?.[k]
    // a pan is judged by how far the view moved (in view heights), a rotation by the angle it turned through
    console.log(k.padEnd(34), /pan/.test(k)
      ? `moved (view heights) ours ${o.moved_in_view_heights.toFixed(4)} FreeCAD ${c ? c.moved_in_view_heights.toFixed(4) : '-'}`
      : `angle (deg) ours ${o.angle_deg.toFixed(3)} FreeCAD ${c ? c.angle_deg.toFixed(3) : '-'}`)
  }
}

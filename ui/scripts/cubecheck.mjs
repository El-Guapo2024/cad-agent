// Checks the NaviCube (the cube in the 3D view's corner, and the buttons around it) against the camera it turns, in a
// scratch workbench: every cube action, from several starting orientations (home, the standard views, one rolled in its
// plane, an oblique one, one a cube drag left), through the page's own mouse and key paths. After each action it asserts
// what a person would call "the view is right":
//   - the cube matches the camera: its orientation is the camera's inverse now, in the last frame drawn, and in every
//     frame drawn during the action (the page records that: see CadView.probe), and the last frame is the camera as it is;
//   - the camera is consistent: its `up` is its orientation's y axis, the focal point lies on its view axis;
//   - a face, edge or corner click lands on FreeCAD's standard upright orientation for that pick (NaviCube.cpp's
//     getFaceRotation, written out here from the C++), a standard view key on Camera.cpp's exact rotation, an arrow or the
//     backside button on the start turned about the screen's axis by 360/NaviStepByTurn (180), a roll on the start with only
//     its up vector turned (same view direction, position and focal point);
//   - a rotation leaves the focal point and the distance to it alone, also with frames 170 ms apart (a slow machine).
// Then the same with no wait between two actions (the second acts on where the first is going), the preference
// NaviRotateToNearest (off by default, on when asked for, and what an older version stored), the cube in a perspective view,
// and the owner's own sequence (the FRONT face, roll right, key 1).
//   node ui/scripts/cubecheck.mjs URL [PROJECT]
//   URL      a scratch workbench's /next/ (never the owner's: this opens a project and changes its view)
//   PROJECT  a project it serves (default mini_machine, from tests/fixtures)
// It changes only the view: no project file, no placement. Needs Playwright (NODE_PATH to one) with a Chromium, on ANGLE's
// SwiftShader as keycheck.mjs does. The mouse is Playwright's own, in the browser: the real pointer never moves.
import { createRequire } from 'module'
const require = createRequire(import.meta.url)
let chromium
try { ({ chromium } = require('playwright')) } catch { ({ chromium } = createRequire('/opt/node-tools/node_modules/')('playwright')) }
const [BASE = 'http://127.0.0.1:8851/next/', PROJECT = 'mini_machine'] = process.argv.slice(2)

// ── vectors, quaternions (x, y, z, w; camera to world, as three.js and Coin have them) ────────────────
const PI = Math.PI, R2 = Math.SQRT1_2
const ANGLE_TOL = 1e-4          // degrees: an orientation that is exact
const MM_TOL = 1e-3             // mm: a focal point or a distance that did not move
const dot3 = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
const cross3 = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
const add3 = (...vs) => vs.reduce((s, v) => [s[0] + v[0], s[1] + v[1], s[2] + v[2]], [0, 0, 0])
const sub3 = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
const scale3 = (a, k) => [a[0] * k, a[1] * k, a[2] * k]
const neg3 = (a) => scale3(a, -1)
const len3 = (a) => Math.hypot(a[0], a[1], a[2])
const unit3 = (a) => scale3(a, 1 / len3(a))
const dist3 = (a, b) => len3(sub3(a, b))
const angle3 = (a, b) => Math.atan2(len3(cross3(a, b)), dot3(a, b))       // radians
const qmul = ([ax, ay, az, aw], [bx, by, bz, bw]) => [aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx, aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz]
const qconj = ([x, y, z, w]) => [-x, -y, -z, w]
const qunit = (q) => { const l = Math.hypot(...q); return q.map((v) => v / l) }
const qangle = (a, b) => { const d = qmul(qunit(a), qconj(qunit(b))); return (2 * Math.atan2(Math.hypot(d[0], d[1], d[2]), Math.abs(d[3])) * 180) / PI }   // degrees, either sign
const qrot = (q, v) => { const u = q.slice(0, 3), t = scale3(cross3(u, v), 2); return add3(v, scale3(t, q[3]), cross3(u, t)) }
const qaxis = (axis, deg) => { const h = (deg * PI) / 360, a = unit3(axis); return [a[0] * Math.sin(h), a[1] * Math.sin(h), a[2] * Math.sin(h), Math.cos(h)] }
/** The rotation whose columns (the camera's x, y and z axes in the world) are X, Y and Z. */
const basisQ = (X, Y, Z) => {
  const m = [[X[0], Y[0], Z[0]], [X[1], Y[1], Z[1]], [X[2], Y[2], Z[2]]], tr = m[0][0] + m[1][1] + m[2][2]
  if (tr > 0) { const s = 2 * Math.sqrt(tr + 1); return [(m[2][1] - m[1][2]) / s, (m[0][2] - m[2][0]) / s, (m[1][0] - m[0][1]) / s, s / 4] }
  if (m[0][0] > m[1][1] && m[0][0] > m[2][2]) { const s = 2 * Math.sqrt(1 + m[0][0] - m[1][1] - m[2][2]); return [s / 4, (m[0][1] + m[1][0]) / s, (m[0][2] + m[2][0]) / s, (m[2][1] - m[1][2]) / s] }
  if (m[1][1] > m[2][2]) { const s = 2 * Math.sqrt(1 + m[1][1] - m[0][0] - m[2][2]); return [(m[0][1] + m[1][0]) / s, s / 4, (m[1][2] + m[2][1]) / s, (m[0][2] - m[2][0]) / s] }
  const s = 2 * Math.sqrt(1 + m[2][2] - m[0][0] - m[1][1]); return [(m[0][2] + m[2][0]) / s, (m[1][2] + m[2][1]) / s, s / 4, (m[1][0] - m[0][1]) / s]
}
/** A camera text (Issue Camera Position's) turned to look along the orientation `q`, keeping what else it says. */
const withOrientation = (text, q) => {
  const n = qunit(q), a = 2 * Math.acos(Math.max(-1, Math.min(1, n[3]))), s = Math.sin(a / 2) || 1
  return text.replace(/orientation .*/, `orientation ${n[0] / s} ${n[1] / s} ${n[2] / s}  ${a}`)
}

// ── what FreeCAD says ─────────────────────────────────────────────────────────────────────────────
// Camera.cpp (3160daf1e2b6): the standard views, as Coin's x, y, z, w.
const STD = {
  top: [0, 0, 0, 1], bottom: [1, 0, 0, 0], front: [R2, 0, 0, R2], rear: [0, R2, R2, 0], right: [0.5, 0.5, 0.5, 0.5], left: [-0.5, 0.5, 0.5, -0.5],
  iso: [0.424708, 0.17592, 0.339851, 0.820473], dimetric: [0.567952, 0.103751, 0.146726, 0.803205], trimetric: [0.446015, 0.119509, 0.229575, 0.856787],
}
const KEY_VIEW = { 0: 'iso', 1: 'front', 2: 'top', 3: 'right', 4: 'rear', 5: 'bottom', 6: 'left' }      // Std_ViewIsometric ... Std_ViewLeft
// NaviCube.cpp getFaceRotation, makeFaceRotation(x, z, rotZ): the face's screen x axis, the axis the camera sits on (the pick's own
// direction) and a roll. The camera's axes are x and y = x cross -z, rolled by rotZ about z. FreeCAD chose the table so that every
// pick but TOP and BOTTOM looks upright (the world's z up the screen).
const ex = [1, 0, 0], ey = [0, 1, 0], ez = [0, 0, 1]
const FACES = {
  Top: [ex, ez, 0], Front: [ex, neg3(ey), 0], Left: [neg3(ey), neg3(ex), 0], Rear: [neg3(ex), ey, 0], Right: [ey, ex, 0], Bottom: [ex, neg3(ez), 0],
  FrontTopRight: [add3(neg3(ex), neg3(ey)), add3(ex, neg3(ey), ez), PI], FrontTopLeft: [add3(neg3(ex), ey), add3(neg3(ex), neg3(ey), ez), PI],
  FrontBottomRight: [add3(ex, ey), add3(ex, neg3(ey), neg3(ez)), 0], FrontBottomLeft: [add3(ex, neg3(ey)), add3(neg3(ex), neg3(ey), neg3(ez)), 0],
  RearTopRight: [add3(ex, neg3(ey)), add3(ex, ey, ez), PI], RearTopLeft: [add3(ex, ey), add3(neg3(ex), ey, ez), PI],
  RearBottomRight: [add3(neg3(ex), ey), add3(ex, ey, neg3(ez)), 0], RearBottomLeft: [add3(neg3(ex), neg3(ey)), add3(neg3(ex), ey, neg3(ez)), 0],
  FrontTop: [ex, add3(ez, neg3(ey)), 0], FrontBottom: [ex, add3(neg3(ez), neg3(ey)), 0], RearBottom: [ex, add3(ey, neg3(ez)), PI], RearTop: [ex, add3(ey, ez), PI],
  RearRight: [ez, add3(ex, ey), PI / 2], FrontRight: [ez, add3(ex, neg3(ey)), PI / 2], FrontLeft: [ez, add3(neg3(ex), neg3(ey)), PI / 2], RearLeft: [ez, add3(ey, neg3(ex)), PI / 2],
  TopLeft: [ey, add3(ez, neg3(ex)), PI], TopRight: [ey, add3(ex, ez), 0], BottomRight: [ey, add3(ex, neg3(ez)), 0], BottomLeft: [ey, add3(neg3(ez), neg3(ex)), PI],
}
const faceQ = ([x, z, rot]) => {
  const Z = unit3(z), X0 = unit3(x), Y0 = unit3(cross3(X0, neg3(Z)))
  return basisQ(add3(scale3(X0, Math.cos(rot)), scale3(Y0, -Math.sin(rot))), add3(scale3(X0, Math.sin(rot)), scale3(Y0, Math.cos(rot))), Z)
}
const PICK = {}                                                          // "x,y,z" (as CadView.cubePicks names a pick) -> { name, q }
for (const [name, f] of Object.entries(FACES)) PICK[f[1].map(Math.sign).join(',')] = { name, q: faceQ(f) }
const nonzero = (k) => k.split(',').filter((c) => c !== '0').length    // 1 a face, 2 an edge, 3 a corner

// ── the page ─────────────────────────────────────────────────────────────────────────────────────
const b = await chromium.launch({ args: ['--use-angle=swiftshader', '--use-gl=angle', '--enable-unsafe-swiftshader'] })
// A tall 3D view, as the owner's was: the cube sits in the top right corner of something much taller than wide.
const VIEWPORT = { width: 1200, height: 1400 }
const errs = []
const watchErrors = (page) => {
  page.on('pageerror', (e) => errs.push(e.message))
  page.on('console', (m) => { if (m.type() === 'error' && !/favicon|Failed to load resource/.test(m.text())) errs.push('console: ' + m.text()) })
}
const results = []
const ok = (name, cond, detail = '') => { results.push({ name, pass: !!cond, detail: cond ? '' : String(detail).slice(0, 500) }); return !!cond }
async function step(name, fn) {
  const e0 = errs.length, n0 = results.length, t0 = Date.now()
  try { await fn() } catch (e) { ok('ran to the end', false, String(e.message).split('\n')[0]) }
  if (errs.length > e0) ok('no page errors', false, errs.slice(e0).join(' / '))
  const mine = results.slice(n0)
  console.log(`${mine.every((r) => r.pass) ? 'ok  ' : 'FAIL'} ${name}: ${mine.filter((r) => r.pass).length}/${mine.length} (${((Date.now() - t0) / 1000).toFixed(0)} s)`)
  for (const r of mine) if (!r.pass) console.log(`       NO  ${r.name}${r.detail ? ' -- ' + r.detail : ''}`)
}

const ctx = await b.newContext({ viewport: VIEWPORT })
const p = await ctx.newPage()
watchErrors(p)
await p.goto('about:blank'); await p.goto(BASE + '#' + PROJECT, { waitUntil: 'load' })
await p.waitForSelector('.trow .tname', { timeout: 120000 }); await p.waitForTimeout(1500)
{ const done = p.getByRole('button', { name: 'Done', exact: true }); if (await done.count()) await done.click() }
await p.getByText(`${PROJECT} : 1`).click(); await p.waitForTimeout(2500)

const probe = () => p.evaluate(() => cadui.getView().probe())
const watch = () => p.evaluate(() => cadui.getView().probe(true))
const picks = () => p.evaluate(() => cadui.getView().cubePicks())
const prefs = (patch) => p.evaluate((patch) => cadui.setState((s) => ({ navPrefs: { ...s.navPrefs, ...(patch.navPrefs ?? {}) }, naviCube: { ...s.naviCube, ...(patch.naviCube ?? {}) } })), patch)
await watch()

/** Wait until the view has stopped: no animation, no change waiting for its frame, and the last frame drawn is the camera as it is. */
async function settle(maxMs = 40000) {
  const t0 = Date.now()
  let stable = 0
  while (Date.now() - t0 < maxMs) {
    const s = await probe(), d = s.drawn
    const drawn = d && qangle(d.camera, s.camera) < 1e-9 && dist3(d.position, s.position) < 1e-9 && d.zoom === s.zoom
    if (!s.animating && !s.pendingFrame && drawn) { if (++stable >= 3) return s } else stable = 0
    await p.waitForTimeout(80)
  }
  const s = await probe(), d = s.drawn
  throw new Error(`the view did not settle in ${maxMs} ms: animating ${s.animating}, a frame pending ${s.pendingFrame}, the last frame is ${qangle(d.camera, s.camera)} deg and ${dist3(d.position, s.position)} mm from the camera, zoom ${d.zoom} against ${s.zoom}`)
}
const click = async (x, y) => { await p.mouse.move(x, y); await p.mouse.down(); await p.mouse.up() }
const clickPick = async (key, { twice = false } = {}) => {
  const at = (await picks())[key]
  await click(at.x, at.y)
  if (twice) { await p.waitForTimeout(40); await click(at.x, at.y) }
}
const dragPick = async (key, dx, dy) => {
  const at = (await picks())[key]
  await p.mouse.move(at.x, at.y); await p.mouse.down()
  await p.mouse.move(at.x + dx / 2, at.y + dy / 2, { steps: 4 }); await p.mouse.move(at.x + dx, at.y + dy, { steps: 4 })
  await p.mouse.up()
}
/** Press on a pick and drag the pointer to a place on the screen, in steps, and let go there. */
const dragPickTo = async (key, x, y) => {
  const at = (await picks())[key]
  await p.mouse.move(at.x, at.y); await p.mouse.down()
  await p.mouse.move((at.x + x) / 2, (at.y + y) / 2, { steps: 4 }); await p.mouse.move(x, y, { steps: 4 })
  await p.mouse.up()
}
const btn = (cls) => p.locator(`.navi.${cls}`).click()
const key = (k) => p.keyboard.press(k)
/** A key as a person presses it: after a click in the 3D view, which gives the view's own element the keyboard
 *  (three-cad-viewer focuses its container on mousedown). Without that click the keys reach the page's keymap even
 *  while the library's own shortcuts sit on that element, which turned `2` in the top view into the bottom. */
const keyInView = async (k) => {
  const c = await p.locator('.view3d-host canvas').boundingBox()
  if (c) { await p.mouse.click(c.x + 8, c.y + c.height - 8); await p.mouse.move(1, 1) }
  await p.keyboard.press(k)
}
/** The face that looks most squarely at the viewer, as a pick key. */
const bestFace = (here) => Object.entries(here).filter(([k, v]) => nonzero(k) === 1 && v.open).sort((a, c) => c[1].facing - a[1].facing)[0][0]
/** Put the camera back to a saved one (what `cad gui view` does with Issue Camera Position's text), at once. */
const restore = async (text) => { await p.evaluate((t) => cadui.getView().setCamera(t), text); return settle() }

/** What is wrong with the camera and the cube in this reading: they must agree, and the camera must agree with itself. */
function consistency(s) {
  const bad = [], a = qangle(s.cube, qconj(s.camera)), d = s.drawn
  if (a > ANGLE_TOL) bad.push(`the cube is ${a.toFixed(4)} deg off the camera`)
  if (d.worst > ANGLE_TOL) bad.push(`a frame drew the cube ${d.worst.toFixed(4)} deg off the camera it was drawn with`)
  if (qangle(d.camera, s.camera) > 1e-6 || qangle(d.cube, qconj(d.camera)) > ANGLE_TOL) bad.push('the last frame drawn is not the camera and cube as they are')
  if (angle3(s.up, qrot(s.camera, [0, 1, 0])) > 1e-6) bad.push('the camera up is not its orientation\'s y axis')
  if (angle3(sub3(s.position, s.target), qrot(s.camera, [0, 0, 1])) > 1e-6) bad.push('the focal point is not on the view axis')
  return bad
}
const focal = (s) => dist3(s.position, s.target)
const turned = (axis, deg) => (S) => qmul(S.camera, qaxis(axis, deg))      // the start turned about one of the camera's own axes
/** Run one action from a start: put the camera back, run it, wait for the view to stop, and judge it. `expect` is the orientation it must
 *  reach (a quaternion, or a function of the start's reading), `keepsTarget` that a rotation must leave the focal point, the distance
 *  to it and the zoom alone, `extra(s, S)` any more problems. */
async function act(label, start, run, { expect = null, keepsTarget = true, extra = null } = {}) {
  const t0 = Date.now()
  const S = await restore(start.text)
  await watch()
  await run(S)
  const s = await settle()
  const bad = consistency(s)
  if (expect) { const q = typeof expect === 'function' ? expect(S) : expect, a = qangle(s.camera, q); if (a > ANGLE_TOL) bad.push(`the camera is ${a.toFixed(4)} deg off the orientation expected`) }
  if (keepsTarget) {
    if (dist3(s.target, S.target) > MM_TOL) bad.push(`the focal point moved ${dist3(s.target, S.target).toFixed(3)} mm`)
    if (Math.abs(focal(s) - focal(S)) > MM_TOL) bad.push(`the distance to the focal point changed by ${(focal(s) - focal(S)).toFixed(3)} mm`)
    if (s.zoom !== S.zoom) bad.push('the zoom changed')
  }
  if (extra) bad.push(...extra(s, S))
  ok(`${label} from ${start.name}`, bad.length === 0, bad.join('; '))
  if (process.env.CUBECHECK_TIMING) console.log(`      ${((Date.now() - t0) / 1000).toFixed(1)} s  ${label} from ${start.name}${bad.length ? '  NO' : ''}`)
  return s
}
const slowFrames = (ms) => p.evaluate((ms) => {
  if (!window.__realRaf) { window.__realRaf = window.requestAnimationFrame.bind(window); window.__realCaf = window.cancelAnimationFrame.bind(window) }
  const timers = new Map(); let n = 0
  window.requestAnimationFrame = ms ? (cb) => { const id = 1e6 + ++n; timers.set(id, setTimeout(() => { timers.delete(id); window.__realRaf(cb) }, ms)); return id } : window.__realRaf
  window.cancelAnimationFrame = ms ? (id) => { if (timers.has(id)) { clearTimeout(timers.get(id)); timers.delete(id) } else window.__realCaf(id) } : window.__realCaf
}, ms)

// ── starts ───────────────────────────────────────────────────────────────────────────────────────
const STEP = 45                                                          // NaviStepByTurn 8
const startAt = async (name, make) => {
  await key('Home'); await settle()
  await make()
  await settle()
  return { name, text: await p.evaluate(() => cadui.getView().getCamera()) }
}
const STARTS = [
  ['home (trimetric)', async () => {}],
  ['the front view', () => key('1')],
  ['the front view rolled 45 deg', async () => { await key('1'); await settle(); await btn('rr') }],
  ['the top view', () => key('2')],
  ['the rear view', () => key('4')],
  ['the bottom view', () => key('5')],
  ['the left view', () => key('6')],
  ['an oblique view, rolled', async () => { await key('0'); await settle(); await btn('n'); await settle(); await btn('e'); await settle(); await btn('rl') }],
  ['a view a cube drag left', () => dragPick('0,-1,0', -60, 40)],
]

await step('setup', async () => {
  const dims = await p.evaluate(() => { const g = cadui.getView().gizmo, r = g._domElement.getBoundingClientRect(), c = cadui.getView().viewer.renderer.domElement.getBoundingClientRect(); return { cube: [r.left, r.top, r.width, r.height], canvas: [c.left, c.top, c.width, c.height] } })
  ok('the 3D view is tall and the cube sits in its top right corner', dims.canvas[3] > dims.canvas[2] && dims.cube[0] + dims.cube[2] > dims.canvas[0] + dims.canvas[2] - 30 && dims.cube[1] < dims.canvas[1] + 30, JSON.stringify(dims))
  const s = await settle()
  ok('the page starts in the default view (Trimetric) with the cube matching it', qangle(s.camera, STD.trimetric) < 1e-3 && consistency(s).length === 0, consistency(s).join('; '))
  ok('there are 26 picks on the cube', Object.keys(await picks()).length === 26)
  ok('the oracle has FRONT, TOP and LEFT as Camera.cpp does', qangle(PICK['0,-1,0'].q, STD.front) < 1e-6 && qangle(PICK['0,0,1'].q, STD.top) < 1e-6 && qangle(PICK['-1,0,0'].q, STD.left) < 1e-6 && qangle(PICK['0,1,0'].q, STD.rear) < 1e-6 && qangle(PICK['1,0,0'].q, STD.right) < 1e-6 && qangle(PICK['0,0,-1'].q, STD.bottom) < 1e-6)
  ok('and every pick but TOP and BOTTOM comes out upright (the world z up the screen)', Object.entries(PICK).filter(([k]) => k !== '0,0,1' && k !== '0,0,-1').every(([, v]) => qrot(v.q, [0, 1, 0])[2] > 0))
  ok('and every pick looks along its own direction', Object.entries(PICK).every(([k, v]) => angle3(qrot(v.q, [0, 0, 1]), k.split(',').map(Number)) < 1e-9))
})
// An animation of 150 ms is one or two frames: plenty for the bulk. The timing sections below use 500 ms.
await prefs({ navPrefs: { duration: 150 } })

const STARTED = []
await step('every cube action from every start', async () => {
  const seen = new Set()
  for (const [name, make] of STARTS.slice(+(process.env.CUBECHECK_FROM ?? 0), +(process.env.CUBECHECK_STARTS ?? STARTS.length))) {
    const st = await startAt(name, make)
    STARTED.push(st)
    const here = await picks()
    // Face, edge and corner clicks: the standard upright orientation of the pick, whatever roll the view had.
    for (const k of Object.keys(here).sort()) {
      if (here[k].facing < 0.4 || !here[k].open) continue       // nearly edge-on (a corner at 0.3 is a sliver no click finds), or under one of the buttons around the cube
      seen.add(k)
      await act(`click ${PICK[k].name}`, st, () => clickPick(k), { expect: PICK[k].q, extra: (s) => (s.drawn.pick === k ? [] : [`the click landed on ${s.drawn.pick}, not ${k}`]) })
    }
    // The four arrows: the start turned about the screen's own axis by one step.
    await act('arrow up', st, () => btn('n'), { expect: turned(ex, STEP) })
    await act('arrow down', st, () => btn('s'), { expect: turned(ex, -STEP) })
    await act('arrow left', st, () => btn('w'), { expect: turned(ey, STEP) })
    await act('arrow right', st, () => btn('e'), { expect: turned(ey, -STEP) })
    // The two rolls: only the up vector turns; the view direction, the position and the focal point stay.
    for (const [cls, label, deg] of [['rl', 'roll left', -STEP], ['rr', 'roll right', STEP]]) {
      await act(label, st, () => btn(cls), {
        expect: turned(ez, deg),
        extra: (s, S) => {
          const bad = [], up0 = qrot(S.camera, [0, 1, 0]), up1 = qrot(s.camera, [0, 1, 0]), by = (angle3(up0, up1) * 180) / PI
          if (angle3(qrot(S.camera, [0, 0, -1]), qrot(s.camera, [0, 0, -1])) > 1e-6) bad.push('the view direction changed')
          if (dist3(s.position, S.position) > MM_TOL) bad.push(`the camera position moved ${dist3(s.position, S.position).toFixed(3)} mm`)
          if (Math.abs(by - STEP) > 1e-4) bad.push(`the up vector turned ${by.toFixed(4)} deg, not ${STEP}`)
          if ((deg > 0) !== (dot3(cross3(up0, up1), qrot(S.camera, [0, 0, 1])) > 0)) bad.push('rolled the wrong way')
          return bad
        },
      })
    }
    await act('backside', st, () => btn('back'), { expect: turned(ey, 180) })
    // Std_ViewRotateLeft and Right (Shift+Left, Shift+Right) are the roll by a quarter turn.
    await act('rotate left (shift+left)', st, () => key('Shift+ArrowLeft'), { expect: turned(ez, -90) })
    await act('rotate right (shift+right)', st, () => key('Shift+ArrowRight'), { expect: turned(ez, 90) })
    // Home: the default orientation, then the whole model fitted.
    await act('home', st, () => btn('home'), { expect: STD.trimetric, keepsTarget: false })
    // Standard views by key keep the focal point, the distance and the zoom (View3DPy::viewFront turns the camera only).
    for (const k of ['0', '1', '2', '3', '4', '5', '6']) await act(`key ${k} (${KEY_VIEW[k]})`, st, () => key(k), { expect: STD[KEY_VIEW[k]] })
    // A double click on a face: the same orientation, and the middle of the model brought to the middle of the view.
    const face = bestFace(here)
    await act(`double click ${PICK[face].name}`, st, () => clickPick(face, { twice: true }), {
      expect: PICK[face].q, keepsTarget: false,
      extra: (s, S) => {
        const bad = []
        if (!s.sceneCenter || dist3(s.target, s.sceneCenter) > MM_TOL) bad.push(`the focal point is ${s.sceneCenter ? dist3(s.target, s.sceneCenter).toFixed(3) : '?'} mm from the middle of the model`)
        if (Math.abs(focal(s) - focal(S)) > MM_TOL) bad.push('the distance to the focal point changed')
        return bad
      },
    })
    // A drag on a face orbits the model's bounding sphere, and is not a click.
    await act('cube drag', st, () => dragPick(face, -45, 30), {
      keepsTarget: false,
      extra: (s, S) => {
        const bad = [], a = qangle(s.camera, S.camera), depth = dot3(sub3(s.sceneCenter, s.position), qrot(s.camera, [0, 0, -1]))
        if (a < 5) bad.push(`the view hardly turned (${a.toFixed(2)} deg)`)
        if (Object.values(PICK).some((v) => qangle(s.camera, v.q) < 1e-3)) bad.push('the drag ended on a standard orientation, like a click')
        if (depth < 1.05 * s.sceneRadius - 1e-3) bad.push(`the camera is inside 1.05 radii of the model (${depth.toFixed(1)} < ${(1.05 * s.sceneRadius).toFixed(1)})`)
        return bad
      },
    })
  }
  ok('the clicks between them reached all 26 picks', seen.size === 26, `${seen.size} of 26; missing ${Object.keys(PICK).filter((k) => !seen.has(k)).join(' ')}`)
})

// ── the same, with frames 170 ms apart: a slow machine must end on the same view ─────────────────
await step('rotations on slow frames keep the focal point (frames 170 ms apart, animations of 500 ms)', async () => {
  await prefs({ navPrefs: { duration: 500 } })
  await slowFrames(170)
  for (const st of [STARTED[0], STARTED[2], STARTED[7]]) {
    await restore(st.text)
    const face = bestFace(await picks())
    await act(`click ${PICK[face].name}`, st, () => clickPick(face), { expect: PICK[face].q })
    await act('arrow up', st, () => btn('n'), { expect: turned(ex, STEP) })
    await act('roll right', st, () => btn('rr'), { expect: turned(ez, STEP) })
    await act('backside', st, () => btn('back'), { expect: turned(ey, 180) })
    await act('key 1 (front)', st, () => key('1'), { expect: STD.front })
    await act('key 0 (iso)', st, () => key('0'), { expect: STD.iso })
  }
  await slowFrames(0)
})

// ── actions with no wait between them: the second acts on where the first is going ──────────────────
await step('actions with no wait between them end where the last one points', async () => {
  const [home, front, rolled, oblique] = [STARTED[0], STARTED[1], STARTED[2], STARTED[7]]
  const quick = async (title, start, run, expect, frames, keepsTarget = true) => {
    if (frames) await slowFrames(frames)
    await act(`${title}${frames ? ` (frames ${frames} ms apart)` : ''}`, start, run, { expect, keepsTarget })
    if (frames) await slowFrames(0)
  }
  for (const frames of [0, 170]) {
    await quick('click FRONT, at once roll right', home, async () => { await clickPick('0,-1,0'); await btn('rr') }, () => qmul(STD.front, qaxis(ez, STEP)), frames)
    await quick('click FRONT, at once roll left twice', home, async () => { await clickPick('0,-1,0'); await btn('rl'); await btn('rl') }, () => qmul(STD.front, qaxis(ez, -2 * STEP)), frames)
    await quick('key 1, at once arrow right', home, async () => { await key('1'); await btn('e') }, () => qmul(STD.front, qaxis(ey, -STEP)), frames)
    await quick('three arrows up in a row', home, async () => { await btn('n'); await btn('n'); await btn('n') }, turned(ex, 3 * STEP), frames)
    await quick('roll right, at once arrow left', oblique, async () => { await btn('rr'); await btn('w') }, (S) => qmul(qmul(S.camera, qaxis(ez, STEP)), qaxis(ey, STEP)), frames)
    await quick('backside twice', rolled, async () => { await btn('back'); await btn('back') }, (S) => S.camera, frames)
    await quick('click FRONT, at once key 2', home, async () => { await clickPick('0,-1,0'); await key('2') }, STD.top, frames)
    await quick('roll right three times, at once click FRONT', front, async () => { await btn('rr'); await btn('rr'); await btn('rr'); await clickPick('0,-1,0') }, STD.front, frames)
    await quick('home, at once roll right', front, async () => { await btn('home'); await btn('rr') }, () => qmul(STD.trimetric, qaxis(ez, STEP)), frames, false)
    await quick('click TOP, at once key 0', home, async () => { await clickPick('0,0,1'); await key('0') }, STD.iso, frames)
  }
})

// ── a cube drag that ends away from the cube ─────────────────────────────────────────────────────────
await step('a cube drag ends where the button comes up: nothing follows the mouse afterwards', async () => {
  const home = STARTED[0]
  const view = await p.evaluate(() => { const r = cadui.getView().viewer.renderer.domElement.getBoundingClientRect(), g = cadui.getView().gizmo._domElement.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height, cube: [g.left + g.width / 2, g.top + g.height / 2] } })
  const wander = [[view.x + view.w / 2, view.y + view.h / 2], [view.x + 150, view.y + 400], [view.x + view.w - 40, view.y + 600], view.cube, [view.cube[0] - 40, view.cube[1] + 30], [view.x + 300, view.y + view.h - 100]]
  // The drag lets go over the 3D view away from the cube (where the navigation stops the pointerup it takes for its own), over the
  // cube, and over the model tree beside the view.
  for (const [where, to] of [['over the 3D view, far from the cube', [view.x + view.w / 2 - 200, view.y + 500]], ['over the cube', [view.cube[0] - 25, view.cube[1] + 18]], ['over the model tree', [60, 300]]]) {
    await restore(home.text)
    await p.evaluate(() => cadui.setState({ selected: ['base'], subSel: [] }))
    await watch()
    await dragPickTo('0,-1,0', ...to)
    const turned = await settle()
    const bad = consistency(turned)
    for (const [x, y] of wander) { await p.mouse.move(x, y); await p.waitForTimeout(100) }
    const s = await settle()
    if (qangle(s.camera, turned.camera) > 1e-9 || dist3(s.position, turned.position) > 1e-9) bad.push(`the view turned by itself with the mouse, ${qangle(s.camera, turned.camera).toFixed(3)} deg`)
    if (s.animating) bad.push('an animation is running')
    ok(`a drag from FRONT let go ${where}: the view stays where the drag left it`, bad.length === 0, bad.join('; '))
    ok(`and the selection is still there`, (await p.evaluate(() => cadui.getState().selected.join(','))) === 'base', await p.evaluate(() => cadui.getState().selected.join(',')))
    // and the next click on the cube is the click it looks like
    const face = bestFace(await picks())
    await clickPick(face)
    const c = await settle()
    ok(`then a click on ${PICK[face].name} is the ${PICK[face].name} view`, qangle(c.camera, PICK[face].q) < ANGLE_TOL && consistency(c).length === 0, `${qangle(c.camera, PICK[face].q).toFixed(3)} deg off; ${consistency(c).join('; ')}`)
  }
  await p.evaluate(() => cadui.setState({ selected: [] }))
})

// ── a turn while Fit All is still moving the camera ───────────────────────────────────────────────
await step('a turn started during Fit All is not carried off by what is left of the fit', async () => {
  const home = STARTED[0]
  for (const [label, turn, want] of [['roll right', (v) => v.turn('z', 45), (S) => qmul(S.camera, qaxis(ez, STEP))], ['arrow up', (v) => v.turn('x', 45), (S) => qmul(S.camera, qaxis(ex, STEP))], ['key 1', (v) => v.viewDir('front'), () => STD.front]]) {
    const S = await restore(home.text)
    await watch()
    // fitAll's first step runs at once, the nine others 20 ms apart: the turn comes in between, in the same task.
    const mid = await p.evaluate((turn) => { const v = cadui.getView(); v.fitAll(); const at = v.probe().target; (0, eval)(`(${turn})`)(v); return at }, turn.toString())
    const s = await settle()
    const bad = consistency(s), a = qangle(s.camera, want(S))
    if (a > ANGLE_TOL) bad.push(`the camera is ${a.toFixed(4)} deg off the orientation expected`)
    if (dist3(s.target, mid) > MM_TOL) bad.push(`the focal point went ${dist3(s.target, mid).toFixed(3)} mm from where the turn found it`)
    ok(`${label} the moment after Fit All begins`, bad.length === 0, bad.join('; '))
  }
})

// ── what the page does to the camera by itself ────────────────────────────────────────────────────
await step('the view survives what the page does on its own: a scene reload, a resize, the projection, the cube hidden', async () => {
  const [home, rolled, oblique] = [STARTED[0], STARTED[2], STARTED[7]]
  const reload = () => p.evaluate(() => cadui.getView().show(cadui.getState().scene, true))   // what a live reload of the project does
  const unchanged = (s, S) => {
    const bad = consistency(s)
    if (qangle(s.camera, S.camera) > ANGLE_TOL) bad.push(`the orientation changed by ${qangle(s.camera, S.camera).toFixed(4)} deg`)
    if (dist3(s.target, S.target) > 0.01) bad.push(`the focal point moved ${dist3(s.target, S.target).toFixed(3)} mm`)
    return bad
  }
  await prefs({ navPrefs: { duration: 500 } })
  // A reload keeps the camera, its up vector (which three-cad-viewer sets to z in the new one) and the cube matching it.
  for (const st of [home, rolled, oblique]) {
    const S = await restore(st.text)
    await watch()
    await reload()
    const s = await settle()
    const bad = unchanged(s, S)
    if (dist3(s.position, S.position) > 0.01 || s.zoom !== S.zoom) bad.push('the position or the zoom changed')
    ok(`a scene reload keeps the view from ${st.name}`, bad.length === 0, bad.join('; '))
  }
  // A reload while a view animation runs: the animation carries on, on the new camera, and arrives (it used to turn the old one).
  for (const [label, run, want] of [
    ['key 1', () => key('1'), () => STD.front], ['click FRONT', () => clickPick('0,-1,0'), () => STD.front], ['key 0', () => key('0'), () => STD.iso],
    ['roll right', () => btn('rr'), (S) => qmul(S.camera, qaxis(ez, STEP))], ['backside', () => btn('back'), (S) => qmul(S.camera, qaxis(ey, 180))],
  ]) {
    for (const frames of [0, 170]) {
      if (frames) await slowFrames(frames)
      const S = await restore(home.text)
      await watch()
      await run(S)
      await p.waitForTimeout(120)
      await reload()
      const s = await settle(), bad = unchanged(s, { ...S, camera: want(S) })
      ok(`${label}, then a scene reload 120 ms in${frames ? ` (frames ${frames} ms apart)` : ''}: the view arrives`, bad.length === 0, bad.join('; '))
      if (frames) await slowFrames(0)
    }
  }
  // The projection changed while a view animation runs: the same.
  for (const [label, keys] of [['key 1, at once perspective', ['v', 'p']], ['key 1, perspective, at once orthographic', ['v', 'p', 'v', 'o']]]) {
    const S = await restore(home.text)
    await watch()
    await key('1')
    for (const k of keys) await key(k)
    const s = await settle(), bad = unchanged(s, { ...S, camera: STD.front })
    ok(`${label}: the view arrives`, bad.length === 0, bad.join('; '))
    await key('v'); await key('o'); await settle()
  }
  // A resize, and the cube hidden and shown: the camera is not touched, the cube still matches it.
  const S = await restore(rolled.text)
  await watch()
  await p.setViewportSize({ width: 1000, height: 1100 })
  let s = await settle()
  ok('a smaller window keeps the view, and the cube is still in the corner', unchanged(s, S).length === 0 && (await p.evaluate(() => { const c = cadui.getView().viewer.renderer.domElement.getBoundingClientRect(), g = cadui.getView().gizmo._domElement.getBoundingClientRect(); return g.right <= c.right + 1 && g.top >= c.top - 1 && g.top < c.top + 40 })), unchanged(s, S).join('; '))
  await p.setViewportSize(VIEWPORT)
  s = await settle()
  ok('and the window back again', unchanged(s, S).length === 0, unchanged(s, S).join('; '))
  await p.evaluate(() => cadui.setState({ cube: false })); await settle()
  await p.evaluate(() => cadui.setState({ cube: true })); await watch()
  s = await settle()
  ok('the cube hidden and shown again matches the camera', unchanged(s, S).length === 0, unchanged(s, S).join('; '))
})

// ── the owner's own sequence ──────────────────────────────────────────────────────────────────────
await step('the owner\'s sequence: the FRONT face, roll right, key 1', async () => {
  for (const wait of [true, false]) {
    const how = wait ? 'one at a time' : 'quickly'
    const S = await restore(STARTED[0].text)
    await watch()
    await clickPick('0,-1,0')
    if (wait) {
      const a = await settle()
      ok(`${how}: FRONT is the exact front view, and the cube shows FRONT face-on`, qangle(a.camera, STD.front) < ANGLE_TOL && qangle(a.cube, qconj(STD.front)) < ANGLE_TOL && consistency(a).length === 0, `${qangle(a.camera, STD.front).toFixed(3)} deg off; ${consistency(a).join('; ')}`)
    }
    await btn('rr')
    const c = await settle(), want = qmul(STD.front, qaxis(ez, STEP))
    ok(`${how}: the roll right is the front view turned in its plane by one step, and only that`, qangle(c.camera, want) < ANGLE_TOL && angle3(qrot(c.camera, [0, 0, -1]), [0, 1, 0]) < 1e-6 && dist3(c.target, S.target) < MM_TOL && consistency(c).length === 0, `${qangle(c.camera, want).toFixed(3)} deg off; focal point ${dist3(c.target, S.target).toFixed(3)} mm moved; ${consistency(c).join('; ')}`)
    await key('1')
    const d = await settle()
    ok(`${how}: key 1 is exactly the front view, no roll, and the cube shows FRONT face-on`, qangle(d.camera, STD.front) < ANGLE_TOL && angle3(d.up, [0, 0, 1]) < 1e-6 && qangle(d.cube, qconj(STD.front)) < ANGLE_TOL && consistency(d).length === 0, `${qangle(d.camera, STD.front).toFixed(3)} deg off; ${consistency(d).join('; ')}`)
  }
})

// ── NaviRotateToNearest ───────────────────────────────────────────────────────────────────────────
await step('NaviRotateToNearest: off unless asked for, and kept as a preference', async () => {
  ok('it is off by default', (await p.evaluate(() => cadui.getState().naviCube.toNearest)) === false)
  const rolledFront = async (deg) => {      // the front view, turned in its plane by `deg`, as the page's camera
    await restore(STARTED[1].text)
    const text = await p.evaluate(() => cadui.getView().getCamera())
    await restore(withOrientation(text, qmul(STD.front, qaxis(ez, deg))))
    await watch()
  }
  // Off: FRONT is the same upright front view from every roll.
  for (const deg of [0, 20, 45, 60, 90, 135, 180, 270]) {
    await rolledFront(deg)
    await clickPick('0,-1,0')
    const s = await settle()
    ok(`off: FRONT from the front view rolled ${deg} deg is the upright front view`, qangle(s.camera, STD.front) < ANGLE_TOL && consistency(s).length === 0, `${qangle(s.camera, STD.front).toFixed(3)} deg off; ${consistency(s).join('; ')}`)
  }
  // On, as FreeCAD has it: the roll nearest the camera's, in steps of 90 degrees.
  await prefs({ naviCube: { toNearest: true } })
  ok('it can be turned on', (await p.evaluate(() => cadui.getState().naviCube.toNearest)) === true)
  for (const deg of [0, 20, 44, 60, 100, 140, 200, 260, 350]) {
    const want = (Math.round(deg / 90) * 90) % 360
    await rolledFront(deg)
    await clickPick('0,-1,0')
    const s = await settle(), q = qmul(STD.front, qaxis(ez, want))
    ok(`on: FRONT from the front view rolled ${deg} deg is the front view rolled ${want} deg`, qangle(s.camera, q) < ANGLE_TOL && consistency(s).length === 0, `${qangle(s.camera, q).toFixed(3)} deg off; ${consistency(s).join('; ')}`)
  }
  await prefs({ naviCube: { toNearest: false } })
})

// ── the stored preference of an older version ─────────────────────────────────────────────────────────
await step('the preference stored by an older version does not keep the old default on', async () => {
  // Every save wrote the whole object, so this is what a person who once changed the cube's size has stored.
  const OLD = { stepByTurn: 8, corner: 1, toNearest: true, font: '', size: 150, inactiveOpacity: 50, color: '#f2f2f2', showCS: true }
  const load = async (stored) => {
    const c2 = await b.newContext({ viewport: VIEWPORT })
    if (stored) await c2.addInitScript((s) => { try { localStorage.setItem('cadui.naviCube', JSON.stringify(s)) } catch { /* no storage */ } }, stored)
    const page = await c2.newPage(); watchErrors(page)
    await page.goto(BASE, { waitUntil: 'load' }); await page.waitForFunction(() => window.cadui?.getState, null, { timeout: 60000 })
    const nc = await page.evaluate(() => cadui.getState().naviCube)
    await c2.close()
    return nc
  }
  const fresh = await load(null)
  ok('a fresh browser: Rotate to nearest is off', fresh.toNearest === false, JSON.stringify(fresh))
  const old = await load(OLD)
  ok('an older whole-object save with it on: off now, and its other settings kept', old.toNearest === false && old.size === 150, JSON.stringify(old))
  const chosen = await load({ ...OLD, v: 2 })
  ok('a save of this version with it on: on', chosen.toNearest === true && chosen.size === 150, JSON.stringify(chosen))
  const sparse = await load({ size: 160 })
  ok('a save of only some settings: the default for the rest', sparse.toNearest === false && sparse.size === 160 && sparse.stepByTurn === 8, JSON.stringify(sparse))
})

// ── Steps by turn ─────────────────────────────────────────────────────────────────────────────────
await step('NaviStepByTurn: the arrows and rolls turn 360 over it', async () => {
  const home = STARTED[0]
  await prefs({ naviCube: { stepByTurn: 12 } })
  await act('arrow up, 12 steps', home, () => btn('n'), { expect: turned(ex, 30) })
  await act('roll right, 12 steps', home, () => btn('rr'), { expect: turned(ez, 30) })
  await prefs({ naviCube: { stepByTurn: 4 } })
  await act('arrow left, 4 steps', home, () => btn('w'), { expect: turned(ey, 90) })
  await prefs({ naviCube: { stepByTurn: 8 } })
})

// ── the same cube in a perspective view ───────────────────────────────────────────────────────────
await step('the cube in a perspective view', async () => {
  await key('v'); await key('p')
  await key('Home'); await settle()
  ok('the view is perspective', (await probe()).ortho === false)
  const st = { name: 'home, perspective', text: await p.evaluate(() => cadui.getView().getCamera()) }
  await act('click FRONT', st, () => clickPick('0,-1,0'), { expect: STD.front })
  await act('arrow right', st, () => btn('e'), { expect: turned(ey, -STEP) })
  await act('roll left', st, () => btn('rl'), { expect: turned(ez, -STEP) })
  await act('key 3 (right)', st, () => key('3'), { expect: STD.right })
  await act('click TOP, roll right, key 1', st, async () => { await clickPick('0,0,1'); await btn('rr'); await key('1') }, { expect: STD.front })
  await key('v'); await key('o')
  await key('Home'); await settle()
  ok('and back to orthographic', (await probe()).ortho === true)
})

// ── the view keys after a click in the 3D view, where the keyboard then is ─────────────────────────────
await step('the view keys after a click in the 3D view: no shortcuts of the viewer library get in first', async () => {
  const home = STARTED[0]
  for (const k of ['0', '1', '2', '3', '4', '5', '6']) await act(`click in the view, key ${k} (${KEY_VIEW[k]})`, home, () => keyInView(k), { expect: STD[KEY_VIEW[k]] })
  await act('click in the view, key 2 twice: still the top', home, async () => { await keyInView('2'); await settle(); await keyInView('2') }, { expect: STD.top })
  await act('click in the view, key 1 twice: still the front', home, async () => { await keyInView('1'); await settle(); await keyInView('1') }, { expect: STD.front })
})

console.log('')
const failed = results.filter((r) => !r.pass)
console.log(`cubecheck: ${results.length - failed.length} passed, ${failed.length} failed, ${errs.length} page errors`)
if (errs.length) console.log(errs.slice(0, 8).join('\n'))
process.exitCode = failed.length || errs.length ? 1 : 0
await b.close()

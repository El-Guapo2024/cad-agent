// Checks nav.ts's gestures and clicks: FreeCAD's NavigationStylePinchTest cases against our
// pinchAction, processClickEvent's double-click deferral, and pinches, pans and twists driven
// through bindNavigation with fake pointer, wheel and Safari gesture events.
// Run from ui/: node scripts/navcheck.mjs   (exit 1 on a failure)
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const UI = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const vite = await import('vite')
await vite.build({ configFile: false, root: UI, publicDir: false, logLevel: 'error',
  build: { ssr: 'src/nav.ts', outDir: 'node_modules/.navcheck', emptyOutDir: true, rollupOptions: { output: { entryFileNames: 'nav.mjs' } } } })
const bundle = pathToFileURL(path.join(UI, 'node_modules/.navcheck/nav.mjs')).href
const THREE = await import('three')

globalThis.window = globalThis
globalThis.requestAnimationFrame = (f) => setTimeout(() => f(performance.now()), 16)
globalThis.cancelAnimationFrame = (id) => clearTimeout(id)
globalThis.addEventListener = () => {}
globalThis.removeEventListener = () => {}
/** nav.ts reads the platform once, at import: load a copy per platform. */
const load = async (mac) => {
  Object.defineProperty(globalThis, 'navigator', { value: { platform: mac ? 'MacIntel' : 'Win32', userAgent: '' }, configurable: true, writable: true })
  return import(`${bundle}?${mac ? 'mac' : 'win'}`)
}

let failures = 0, passes = 0
const check = (name, ok, detail = '') => { if (ok) passes++; else { failures++; console.log(`FAIL ${name}${detail ? ': ' + detail : ''}`) } }
const near = (a, b, tol = 1e-5) => Math.abs(a - b) <= tol
/** a - b as an angle in [-π, π). */
const turn = (a, b) => { const d = a - b; return d - 2 * Math.PI * Math.floor((d + Math.PI) / (2 * Math.PI)) }
const deg = (r) => `${(r * 180 / Math.PI).toFixed(4)}°`

const W = 800, H = 600
function rig(N, { style = 'cad', tilt = true, prefs = {} } = {}) {
  const cam = new THREE.OrthographicCamera(-4, 4, 3, -3, 0.1, 100)
  cam.position.set(0, 0, 10); cam.lookAt(0, 0, 0); cam.updateMatrixWorld()
  const tgt = new THREE.Vector3()
  const log = { scene: [], cleared: 0, popups: 0, bands: 0 }
  const host = {
    camera: () => cam, target: () => tgt, size: () => [W, H], changed: () => {},
    scenePoint: () => null, sceneBox: () => null, draggerUnderCursor: () => false,
    scene: (ev) => { log.scene.push(`${ev.type}${ev.button ?? ''}`); return false },
    clearSelection: () => { log.cleared++ }, popup: () => { log.popups++ }, band: (a) => { if (a) log.bands++ },
    boxSelect: () => {}, clarify: () => {}, marker: () => {}, cursor: () => {}, viewAll: () => {}, orient: () => {},
    prefs: () => ({ ...N.NAV_DEFAULTS, clarifyLongPress: false, ...prefs, animate: false, disableTouchTilt: tilt }),
  }
  const nav = new N.Navigation(host)
  nav.setStyle(style)
  // The DOM side: a canvas filling the element, client y down.
  const canvas = { getBoundingClientRect: () => ({ left: 0, top: 0, width: W, height: H }), setPointerCapture() {}, style: {} }
  const listeners = {}
  const el = { style: {}, addEventListener: (t, f) => (listeners[t] ??= []).push(f), removeEventListener() {} }
  N.bindNavigation(nav, el, (t) => t === canvas, () => canvas, () => false)
  let T = 1000
  const fire = (type, props = {}) => {
    const e = { type, timeStamp: (T += 20), target: canvas, ctrlKey: false, metaKey: false, shiftKey: false, altKey: false,
      stopPropagation() {}, preventDefault() {}, ...props }
    for (const f of listeners[type] ?? []) f(e)
  }
  const finger = (type, id, x, y) => fire(type, { pointerId: id, pointerType: 'touch', clientX: x, clientY: y, button: type === 'pointermove' ? -1 : 0, buttons: type === 'pointerup' ? 0 : 1 })
  /** Where a world point shows, in client pixels. */
  const screen = (x, y, z = 0) => { cam.updateMatrixWorld(); const v = new THREE.Vector3(x, y, z).project(cam); return [(v.x + 1) / 2 * W, (1 - v.y) / 2 * H] }
  /** The on-screen direction of the world's x axis, radians counter-clockwise: a twist turns it, a pan doesn't. */
  const dir = () => { const [ax, ay] = screen(0, 0), [bx, by] = screen(1, 0); return Math.atan2(-(by - ay), bx - ax) }
  return { nav, cam, tgt, log, fire, finger, screen, dir, get mode() { return nav.viewerMode } }
}

for (const mac of [true, false]) {
  const N = await load(mac)
  const P = mac ? 'mac' : 'win'

  // ── FreeCAD's NavigationStylePinchTest.cpp, case by case ──────────────────
  const upd = (deltaZoom, deltaAngle, native = false) => ({ state: 'update', curCenter: [0, 0], deltaCenter: [0, 0], deltaZoom, deltaAngle, fromNativeGesture: native })
  for (const state of ['start', 'end']) {
    const a = N.pinchAction({ ...upd(2, 1), state }, false)
    check(`${P} onlyUpdateEventsMoveTheCamera (${state})`, !a.zoom && !a.rotate)
  }
  { const a = N.pinchAction(upd(0, 0.5), false); check(`${P} aRotateOnlyEventDoesNotZoom`, !a.zoom && a.rotate) }
  { const a = N.pinchAction(upd(1.5, 0), false); check(`${P} aZoomOnlyEventDoesNotRotate`, a.zoom && !a.rotate) }
  { const a = N.pinchAction(upd(-0.5, 0), false); check(`${P} aNegativeZoomFactorIsIgnored`, !a.zoom) }
  { const a = N.pinchAction(upd(2, 0), false); check(`${P} pinchingOutZoomsIn`, a.zoom && a.zoomLogFactor === -Math.fround(Math.log(2))) }
  { const i = N.pinchAction(upd(2, 0), false), o = N.pinchAction(upd(0.5, 0), false); check(`${P} pinchingInZoomsOutBySymmetricAmount`, o.zoomLogFactor === -i.zoomLogFactor) }
  { const a = N.pinchAction(upd(2, 0.5), true); check(`${P} aTouchscreenPinchObeysTheTiltPreference`, a.zoom && !a.rotate) }
  { const a = N.pinchAction(upd(2, 0.5, true), true); check(`${P} aTrackpadRotateIsNotBlockedByTheTouchscreenTiltPreference`, a.zoom && a.rotate && a.rotateAngle === Math.fround(0.5)) }

  // ── processClickEvent: a press within the double-click interval waits for its release ──
  {
    const r = rig(N, { style: 'cad' })
    const ev = (type, t, x = 400, y = 300) => r.nav.processEvent({ type, button: 1, pos: [x, y], t, ctrl: false, shift: false, alt: false })
    ev('press', 0); ev('release', 0.05)
    check(`${P} click 1 reaches the scene at once`, r.log.scene.join() === 'press1,release1', r.log.scene.join())
    r.log.scene = []
    ev('press', 0.2)
    check(`${P} a quick second press is held back`, r.log.scene.length === 0, r.log.scene.join())
    ev('release', 0.25)
    check(`${P} the held press goes ahead of its release`, r.log.scene.join() === 'press1,release1', r.log.scene.join())
    r.log.scene = []
    ev('press', 0.5); ev('release', 0.55) // 0.3 s after the held press: still a candidate
    check(`${P} a third quick press is held too`, r.log.scene.join() === 'press1,release1')
    r.log.scene = []
    ev('press', 2); check(`${P} a slow press goes at once`, r.log.scene.join() === 'press1', r.log.scene.join())
    ev('release', 2.05)
    // A drag box clears the candidate: the next quick press goes at once.
    r.log.scene = []
    ev('press', 3); r.nav.processEvent({ type: 'move', pos: [460, 360], t: 3.1, ctrl: false, shift: false, alt: false }); ev('release', 3.15, 460, 360)
    const boxed = r.log.bands > 0
    r.log.scene = []
    ev('press', 3.3)
    check(`${P} a drag box is no click candidate`, boxed && r.log.scene.join() === 'press1', `bands=${r.log.bands} scene=${r.log.scene.join()}`)
  }

  // ── a touchscreen: two fingers pinch (QPinchGesture) ──────────────────────
  {
    const r = rig(N, { style: 'cad' })
    r.finger('pointerdown', 1, 300, 300)
    check(`${P} one finger is the left button`, r.log.scene.join() === 'press1', r.log.scene.join())
    r.finger('pointerdown', 2, 500, 300)
    const z0 = r.cam.zoom
    r.finger('pointermove', 2, 700, 300) // the spread doubles, about (500, 300)
    check(`${P} spreading two fingers zooms in by their ratio`, near(r.cam.zoom / z0, 2, 1e-4), `zoom ${r.cam.zoom / z0}`)
    const [cx] = r.screen(0, 0)
    r.finger('pointermove', 1, 400, 300); r.finger('pointermove', 2, 800, 300) // the centre moves right by 100 px
    const [cx2] = r.screen(0, 0)
    check(`${P} two fingers moving pan the view with them`, near(cx2 - cx, 100, 0.5), `moved ${cx2 - cx}`)
    const q = r.cam.quaternion.clone()
    r.finger('pointermove', 2, 400 + 400 * Math.cos(Math.PI / 6), 300 - 400 * Math.sin(Math.PI / 6))
    check(`${P} DisableTouchTilt blocks a touchscreen twist`, r.cam.quaternion.angleTo(q) < 1e-9)
    r.finger('pointerup', 2, 0, 0); r.finger('pointerup', 1, 0, 0)
    check(`${P} a pinch ends without a click`, !r.log.scene.includes('release1') && r.log.cleared === 0, `${r.log.scene.join()} cleared=${r.log.cleared}`)
    // The next touch is the mouse again.
    r.log.scene = []
    r.finger('pointerdown', 3, 300, 300); r.finger('pointerup', 3, 300, 300)
    check(`${P} after a pinch one finger clicks again`, r.log.scene.join() === 'press1,release1', r.log.scene.join())
  }
  {
    const r = rig(N, { style: 'cad', tilt: false })
    r.finger('pointerdown', 1, 300, 300); r.finger('pointerdown', 2, 500, 300)
    const d0 = r.dir()
    // Turn finger 2 a quarter turn counter-clockwise about finger 1, on screen.
    r.finger('pointermove', 2, 300, 100)
    check(`${P} a counter-clockwise twist turns the model counter-clockwise`, near(turn(r.dir(), d0), Math.PI / 2, 1e-4), `turned ${deg(turn(r.dir(), d0))}`)
  }

  // ── the Gesture style: FreeCAD's GestureState, but not on a Mac ────────────
  {
    const r = rig(N, { style: 'gesture' })
    r.finger('pointerdown', 1, 300, 300); r.finger('pointerdown', 2, 500, 300)
    check(`${P} gesture style: a pinch ${mac ? 'leaves the mode alone (Mac bypass)' : 'pans (GestureState)'}`, r.mode === (mac ? 'IDLE' : 'PANNING'), r.mode)
    const z0 = r.cam.zoom
    r.finger('pointermove', 2, 700, 300)
    check(`${P} gesture style: the pinch zooms`, near(r.cam.zoom / z0, 2, 1e-4), `${r.cam.zoom / z0}`)
    r.finger('pointerup', 2, 0, 0)
    check(`${P} gesture style: the end goes idle`, r.mode === 'IDLE', r.mode)
    r.finger('pointerup', 1, 0, 0)
    check(`${P} gesture style: no click after the pinch`, !r.log.scene.some((s) => s.startsWith('press') || s.startsWith('release')), r.log.scene.join())
  }

  // ── Maya-Gesture: its own pinch, DRAGGING while it lasts, no tilt preference ──
  {
    const r = rig(N, { style: 'mayagesture', tilt: true })
    r.finger('pointerdown', 1, 300, 300); r.finger('pointerdown', 2, 500, 300)
    check(`${P} maya: a pinch drags`, r.mode === 'DRAGGING', r.mode)
    const q = r.cam.quaternion.clone()
    r.finger('pointermove', 2, 300, 100)
    check(`${P} maya: a touchscreen twist turns even with DisableTouchTilt`, near(r.cam.quaternion.angleTo(q), Math.PI / 2, 1e-4), `${r.cam.quaternion.angleTo(q)}`)
    r.finger('pointerup', 2, 0, 0)
    check(`${P} maya: the end selects`, r.mode === 'SELECTION', r.mode)
    r.finger('pointerup', 1, 0, 0)
  }

  // ── trackpads: Ctrl+wheel (Chrome, Firefox), Safari's gesture events ───────
  {
    const r = rig(N, { style: 'mayagesture' })
    const z0 = r.cam.zoom
    r.fire('wheel', { clientX: 400, clientY: 300, deltaX: 0, deltaY: -50.5, deltaMode: 0, ctrlKey: true })
    check(`${P} ctrl+wheel: a pinch zooms by exp(-deltaY/100)`, near(r.cam.zoom / z0, Math.exp(0.505), 1e-4), `${r.cam.zoom / z0}`)
    check(`${P} ctrl+wheel: the pinch starts a gesture (maya drags)`, r.mode === 'DRAGGING', r.mode)
    await new Promise((res) => setTimeout(res, 260))
    check(`${P} ctrl+wheel: the pinch ends when the wheel stops`, r.mode === 'SELECTION', r.mode)
  }
  {
    const r = rig(N, { style: 'cad', tilt: true })
    const z0 = r.cam.zoom
    r.fire('gesturestart', { clientX: 400, clientY: 300, scale: 1, rotation: 0 })
    const d0 = r.dir()
    r.fire('gesturechange', { clientX: 400, clientY: 300, scale: 2, rotation: 30 }) // Safari: clockwise positive
    r.fire('gestureend', { clientX: 400, clientY: 300, scale: 2, rotation: 30 })
    check(`${P} safari: a pinch zooms by the scale's step`, near(r.cam.zoom / z0, 2, 1e-4), `${r.cam.zoom / z0}`)
    check(`${P} safari: a clockwise twist turns the model clockwise, despite DisableTouchTilt`, near(turn(r.dir(), d0), -Math.PI / 6, 1e-4), `turned ${deg(turn(r.dir(), d0))}`)
  }
  {
    const r = rig(N, { style: 'cad' })
    const d0 = r.dir(), z0 = r.cam.zoom
    r.fire('wheel', { clientX: 400, clientY: 300, deltaX: 0, deltaY: 180.5, deltaMode: 0, altKey: true })
    const d1 = r.dir()
    check(`${P} alt+scroll: rolls a degree per 4 px, no zoom`, near(turn(d1, d0), 180.5 * Math.PI / 720, 1e-4) && r.cam.zoom === z0, `turned ${deg(turn(d1, d0))} zoom ${r.cam.zoom / z0}`)
    r.fire('wheel', { clientX: 400, clientY: 300, deltaX: 0, deltaY: -100, deltaMode: 0, altKey: true, wheelDeltaY: 120 })
    check(`${P} alt+wheel: a notch away turns 15° clockwise`, near(turn(r.dir(), d1), -Math.PI / 12, 1e-4), `turned ${deg(turn(r.dir(), d1))}`)
  }
}

console.log(`navcheck: ${passes} passed, ${failures} failed`)
process.exit(failures ? 1 : 0)

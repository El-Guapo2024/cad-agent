// FreeCAD's mouse navigation, ported from src/Gui/Navigation/ at FreeCAD main
// 3160daf1e2b6 (LGPL-2.1-or-later): NavigationStyle's pan, zoom and orbit with
// FCSphereSheetProjector over Coin's SbSphereSheetProjector (BSD-3-Clause), the
// view animations of NavigationAnimation.cpp, the twelve styles' event handling,
// and the long-press Clarify Selection of View3DInventorViewer's event filter.
//
// Coin's mouse buttons: 1 left, 2 right, 3 middle. Pixel positions count from the
// bottom left. FreeCAD's Ctrl is Cmd on a Mac, as Qt maps it.
import * as THREE from 'three'

export type NavStyleId = 'blender' | 'cad' | 'gesture' | 'mayagesture' | 'opencascade' | 'openinventor'
  | 'openscad' | 'revit' | 'siemensnx' | 'solidworks' | 'tinkercad' | 'touchpad'

/** Each style's name and its mouseButtons() hints: select, pan, rotate, zoom. */
export const NAV_STYLES: { id: NavStyleId; name: string; hints: [string, string, string, string] }[] = [
  { id: 'blender', name: 'Blender', hints: ['Press left mouse button', 'Press Shift and middle mouse button', 'Press middle mouse button', 'Scroll mouse wheel'] },
  { id: 'cad', name: 'CAD', hints: ['Press left mouse button', 'Press middle or ctrl+right mouse button', 'Press middle+left, middle+right or shift+right mouse button',
    'Scroll mouse wheel or keep middle button depressed while doing a left or right click and move the mouse up or down'] },
  { id: 'gesture', name: 'Gesture', hints: ['Tap OR click left mouse button.', 'Drag screen with two fingers OR press right mouse button.',
    'Drag screen with one finger OR press left mouse button. In Sketcher and other edit modes, hold Alt in addition.',
    'Pinch (place two fingers on the screen and drag them apart from or towards each other) OR scroll mouse wheel OR PgUp/PgDown on keyboard.'] },
  { id: 'mayagesture', name: 'Maya-Gesture', hints: ['Tap OR click left mouse button.', 'Drag screen with two fingers OR press Alt + middle mouse button.',
    'Drag screen with one finger OR press Alt + left mouse button. In Sketcher and other edit modes, hold Alt in addition.',
    'Pinch (place two fingers on the screen and drag them apart from or towards each other) OR scroll mouse wheel OR press Alt + right mouse button OR PgUp/PgDown on keyboard.'] },
  { id: 'opencascade', name: 'OpenCascade', hints: ['Press left mouse button', 'Press Ctrl and middle mouse button', 'Press Ctrl and right mouse button', 'Press Ctrl and left mouse button'] },
  { id: 'openinventor', name: 'OpenInventor', hints: ['Press Ctrl and left mouse button', 'Press middle mouse button', 'Press left mouse button', 'Scroll mouse wheel'] },
  { id: 'openscad', name: 'OpenSCAD', hints: ['Press left mouse button', 'Press right mouse button and move mouse', 'Press left mouse button and move mouse', 'Press middle mouse button or SHIFT and right mouse button'] },
  { id: 'revit', name: 'Revit', hints: ['Press left mouse button', 'Press middle mouse button', 'Press Shift and middle mouse button', 'Scroll middle mouse button'] },
  { id: 'siemensnx', name: 'Siemens NX', hints: ['Press left mouse button', 'Press middle+right click', 'Press middle mouse button', 'Scroll mouse wheel'] },
  { id: 'solidworks', name: 'SolidWorks', hints: ['Press left mouse button', 'Press Ctrl and middle mouse button', 'Press middle mouse button', 'Scroll mouse wheel'] },
  { id: 'tinkercad', name: 'TinkerCAD', hints: ['Press left mouse button', 'Press middle mouse button', 'Press right mouse button', 'Scroll mouse wheel'] },
  { id: 'touchpad', name: 'Touchpad', hints: ['Press left mouse button', 'Press Shift button', 'Press Alt button', 'Press Ctrl and Shift buttons'] },
]
/** The styles whose long-press Clarify Selection needs Ctrl (clarifySelectionMode()). */
const CLARIFY_CTRL: NavStyleId[] = ['openinventor', 'gesture', 'openscad']

/** NavigationStyle::OrbitStyle, in FreeCAD's order. */
export const ORBIT_STYLES = ['Turntable', 'Trackball', 'Free Turntable', 'Trackball Classic', 'Rounded Arcball'] as const
export type OrbitStyle = 0 | 1 | 2 | 3 | 4

/** The View preferences the navigation reads, with FreeCAD's defaults. */
export type NavPrefs = {
  orbit: OrbitStyle // OrbitStyle, 4 Rounded Arcball
  rotationMode: 0 | 1 | 2 // RotationMode: window centre, drag at cursor, object centre
  sensitivity: number // Sensitivity, 2
  invertZoom: boolean // InvertZoom
  zoomAtCursor: boolean // ZoomAtCursor
  zoomStep: number // ZoomStep, 0.2
  showRotationCenter: boolean // ShowRotationCenter
  duration: number // AnimationDuration, ms
  spinning: boolean // UseSpinningAnimations
  touchpadScrollPans: boolean // TouchpadScrollPans, on by default on a Mac
  clarifyLongPress: boolean // EnableLongPressClarifySelection
  longPressTimeout: number // LongPressTimeout, s
}
export const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent)
export const NAV_DEFAULTS: NavPrefs = {
  orbit: 4, rotationMode: 0, sensitivity: 2, invertZoom: true, zoomAtCursor: true, zoomStep: 0.2, showRotationCenter: true,
  duration: 500, spinning: false, touchpadScrollPans: isMac, clarifyLongPress: true, longPressTimeout: 1,
}

type Mode = 'IDLE' | 'INTERACT' | 'ZOOMING' | 'BOXZOOM' | 'PANNING' | 'DRAGGING' | 'SPINNING' | 'SELECTION'
export type V2 = [number, number]
/** An input event as Coin sees it. */
export type NavEvent = {
  type: 'press' | 'release' | 'move' | 'key'
  button?: 1 | 2 | 3
  /** KeyboardEvent.key; Control means FreeCAD's Ctrl (Cmd on a Mac). */
  key?: string
  down?: boolean
  pos: V2
  t: number // seconds
  ctrl: boolean
  shift: boolean
  alt: boolean
}

type Cam = THREE.OrthographicCamera | THREE.PerspectiveCamera
/** What the navigation needs from the 3D view. */
export interface NavHost {
  camera(): Cam | null
  /** The focal point: the orbit controls' target. */
  target(): THREE.Vector3 | null
  size(): V2
  /** The camera moved: sync the controls and the cube, redraw. */
  changed(): void
  /** The model point under a pixel, if any (SoRayPickAction). */
  scenePoint(pos: V2): THREE.Vector3 | null
  sceneBox(): THREE.Box3 | null
  draggerUnderCursor(): boolean
  /** Hand an event to the scene graph (selection, preselection, the dragger); true if it used it. */
  scene(ev: NavEvent): boolean
  clearSelection(): void
  popup(pos: V2): void
  /** The rubber band while box-selecting, null when done. */
  band(a: V2 | null, b?: V2): void
  boxSelect(a: V2, b: V2, additive: boolean): void
  clarify(pos: V2): void
  /** Show the rotation centre marker there, or hide it. */
  marker(p: THREE.Vector3 | null): void
  cursor(css: string): void
  viewAll(): void
  orient(name: 'iso' | 'trimetric' | 'top'): void
  prefs(): NavPrefs & { animate: boolean }
}

const DCI = 0.4 // QApplication::doubleClickInterval, s
const DRAG_DISTANCE = 10 // QApplication::startDragDistance, px
const HOLD_TIMEOUT = 0.63 // QTapAndHoldGesture::timeout() * 0.9, s
const SPHERE_RADIUS = 0.8 // FCSphereSheetProjector::defaultSphereRadius
const X = new THREE.Vector3(1, 0, 0), Y = new THREE.Vector3(0, 1, 0), Z = new THREE.Vector3(0, 0, 1)
const viewDir = (q: THREE.Quaternion) => new THREE.Vector3(0, 0, -1).applyQuaternion(q)
const axisAngle = (q: THREE.Quaternion): [THREE.Vector3, number] => {
  const w = Math.min(1, Math.max(-1, q.w)), angle = 2 * Math.acos(w), s = Math.sqrt(1 - w * w)
  return [s < 1e-9 ? Z.clone() : new THREE.Vector3(q.x / s, q.y / s, q.z / s), angle]
}
const rot = (axis: THREE.Vector3, angle: number) => new THREE.Quaternion().setFromAxisAngle(axis.clone().normalize(), angle)
const inOutCubic = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2)
const cursorUrl = (n: string) => `url(./freecad-icons/cursor-${n}.svg) 8 8, auto`
const CURSOR: Record<Mode, string> = {
  IDLE: 'default', INTERACT: 'default', DRAGGING: cursorUrl('rotate'), SPINNING: cursorUrl('rotate'), ZOOMING: cursorUrl('zoom'),
  PANNING: cursorUrl('pan'), BOXZOOM: 'crosshair', SELECTION: 'pointer',
}

/** FCSphereSheetProjector: screen points in the unit view volume ortho(-1, 1, -1, 1,
 *  -1, 1) onto a sphere and sheet around `c`; rotations come out in camera axes. */
class Projector {
  orbit: OrbitStyle = 4
  c = new THREE.Vector3()
  r = SPHERE_RADIUS
  last = new THREE.Vector3()
  /** The camera's inverse orientation, for the turntable's up axis (setWorkingSpace). */
  worldToScreen = new THREE.Quaternion()

  project(p: V2): THREE.Vector3 {
    const x = 2 * p[0] - 1, y = 2 * p[1] - 1
    const d = Math.hypot(x - this.c.x, y - this.c.y)
    let z: number
    if (this.orbit !== 4) {
      // SbSphereSheetProjector: the sphere out to 45°, then the hyperbolic sheet r²/2d.
      z = d < this.r * Math.cos(Math.PI / 4) ? Math.sqrt(this.r * this.r - d * d) : (this.r * this.r * 0.5) / d
    } else {
      // Rounded Arcball: sphere, fillet and plane, in "squished space".
      const border = 0.5, ra = 1 + border, ri = 2 / (ra + 1 / ra), ds = d * ra
      if (ds > ra) z = 0
      else if (ds < ri) z = Math.sqrt(1 - ds * ds)
      else { const dr = ra - ds, a = border * (1 + border / 2); z = a - Math.sqrt((a + dr) * (a - dr)) }
    }
    this.last.set(x, y, this.c.z + z)
    return this.last.clone()
  }

  /** projectAndGetRotation: from the last projected point to this one. */
  rotationTo(p: V2): THREE.Quaternion {
    const from = this.last.clone(), to = this.project(p)
    return this.rotation(from, to)
  }

  rotation(p1: THREE.Vector3, p2: THREE.Vector3): THREE.Quaternion {
    const a = p1.clone().sub(this.c).normalize(), b = p2.clone().sub(this.c).normalize()
    const r = new THREE.Quaternion().setFromUnitVectors(a, b) // SbRotation(point1 - planePoint, point2 - planePoint)
    if (this.orbit === 0 || this.orbit === 2) return this.turntable(r, p1, p2)
    if (this.orbit === 3) return this.classic(p1, p2)
    return r
  }

  private turntable(r: THREE.Quaternion, p1: THREE.Vector3, p2: THREE.Vector3) {
    let angle = axisAngle(r)[1]
    const dif = p1.clone().sub(p2)
    if (Math.abs(dif.y) > Math.abs(dif.x)) return rot(X, dif.y < 0 ? -angle : angle)
    const z = Z.clone().applyQuaternion(this.worldToScreen)
    if (z.y < 0 ? dif.x < 0 : dif.x > 0) angle = -angle
    return rot(z, angle)
  }

  private classic(p1: THREE.Vector3, p2: THREE.Vector3) {
    const dif = p1.clone().sub(p2)
    return rot(Y, -dif.x).multiply(rot(X, dif.y)) // Coin's zrot * yrot: about x first, then y
  }
}

type Anim = { stop(finished: boolean): void }

export class Navigation {
  style: NavStyleId = 'cad'
  private mode: Mode = 'IDLE'
  private viewing = false
  private b1 = false
  private b2 = false
  private b3 = false
  private ctrl = false
  private shift = false
  private alt = false
  private last: V2 = [0, 0] // lastmouseposition, normalized
  private mouse: V2 = [0, 0]
  private hasDragged = false
  private hasPanned = false
  private hasZoomed = false
  private lockButton1 = false
  private lockrecenter = false
  private centerTime = 0
  private blockPan = false
  private plane = new THREE.Plane(Z.clone(), 0) // panningplane
  private log: { pos: V2; t: number }[] = []
  private center = new THREE.Vector3()
  private centerFound = false
  private centerAtCursor = false
  private selStart: V2 | null = null
  private box: { a: V2; b: V2; additive: boolean } | null = null
  private proj = new Projector()
  private spinInc = { axis: Z.clone(), angle: 0, n: 0 }
  private anim: Anim | null = null
  private raycaster = new THREE.Raycaster()
  private state = 'Idle' // the Gesture and Siemens NX state machines
  private base: V2 = [0, 0]
  private since = 0
  private postponed: NavEvent[] = []
  private rollDir = 0
  private maya = { complex: false, broken: false, downPos: [0, 0] as V2, consumed: [] as NavEvent[], inGesture: false }
  private longPress = 0
  private swallow = false
  private longPressAt: V2 = [0, 0]
  /** The dragger took the press: DOM events go to it until the buttons are up. */
  interact = false

  constructor(private host: NavHost) {}

  // ── NavigationStyle's camera operations ───────────────────────────────────
  private parts() {
    const cam = this.host.camera(), tgt = this.host.target()
    return cam && tgt ? { cam, tgt } : null
  }
  private get prefs() { return this.host.prefs() }
  private ortho(cam: Cam): cam is THREE.OrthographicCamera { return (cam as THREE.OrthographicCamera).isOrthographicCamera === true }
  normalize(pos: V2): V2 {
    const [w, h] = this.host.size()
    return [pos[0] / Math.max(w - 1, 1), pos[1] / Math.max(h - 1, 1)]
  }
  private linePlane(plane: THREE.Plane, p: V2): THREE.Vector3 | null {
    const cam = this.host.camera()
    if (!cam) return null
    cam.updateMatrixWorld()
    this.raycaster.setFromCamera(new THREE.Vector2(2 * p[0] - 1, 2 * p[1] - 1), cam)
    const r = this.raycaster.ray, den = plane.normal.dot(r.direction)
    if (Math.abs(den) < 1e-12) return null
    return r.origin.clone().addScaledVector(r.direction, -(r.origin.dot(plane.normal) + plane.constant) / den)
  }
  private focalPlane() {
    const p = this.parts()
    return p ? new THREE.Plane().setFromNormalAndCoplanarPoint(viewDir(p.cam.quaternion), p.tgt) : new THREE.Plane(Z.clone(), 0)
  }
  private setupPanningPlane() { this.plane = this.focalPlane() }

  /** panCamera: move the camera by the difference of two screen points on a plane. */
  private panCamera(plane: THREE.Plane, curr: V2, prev: V2) {
    const p = this.parts()
    if (!p || (curr[0] === prev[0] && curr[1] === prev[1])) return
    const a = this.linePlane(plane, curr), b = this.linePlane(plane, prev)
    if (!a || !b) return
    const d = a.sub(b)
    p.cam.position.sub(d)
    p.tgt.sub(d)
    if (this.mode !== 'IDLE') this.hasPanned = true
    this.host.changed()
  }

  /** zoom: exp(diff) times the view height (orthographic) or the focal distance. */
  private zoom(diff: number) {
    const p = this.parts()
    if (!p) return
    this.stopAnimating()
    const m = Math.exp(diff)
    if (this.ortho(p.cam)) { p.cam.zoom /= m; p.cam.updateProjectionMatrix() }
    else {
      const fd = p.tgt.distanceTo(p.cam.position) * m
      if (Number.isFinite(fd) && fd < 1e19) p.cam.position.copy(p.tgt).addScaledVector(viewDir(p.cam.quaternion), -fd)
    }
    if (this.mode !== 'IDLE') this.hasZoomed = true
    this.host.changed()
  }
  private zoomByCursor(thispos: V2, prevpos: V2) {
    const v = (thispos[1] - prevpos[1]) * 10
    this.zoom(this.prefs.invertZoom ? -v : v)
  }
  /** doZoom with a wheel delta (120 a notch), honouring InvertZoom. */
  doZoomSteps(delta: number, pos: V2) {
    const v = (this.prefs.zoomStep * delta) / 120
    this.doZoom(this.prefs.invertZoom ? -v : v, pos)
  }
  /** doZoom: zoom, keeping the point under the cursor fixed when ZoomAtCursor is on. */
  doZoom(logfactor: number, pos: V2) {
    if (Math.abs(logfactor) > 4) return
    const at = this.prefs.zoomAtCursor
    if (at) this.panCamera(this.focalPlane(), [0.5, 0.5], pos)
    this.zoom(logfactor)
    if (at) this.panCamera(this.focalPlane(), pos, [0.5, 0.5])
  }
  zoomIn() { this.zoom(-this.prefs.zoomStep) }
  zoomOut() { this.zoom(this.prefs.zoomStep) }
  /** doRotate: roll about the view direction, at the cursor. */
  private doRotate(angle: number, pos: V2) {
    const p = this.parts()
    if (!p) return
    const at = this.prefs.zoomAtCursor
    if (at) this.panCamera(this.focalPlane(), [0.5, 0.5], pos)
    const q = p.cam.quaternion.clone()
    p.cam.quaternion.copy(rot(viewDir(q), angle).multiply(q))
    p.cam.up.copy(Y).applyQuaternion(p.cam.quaternion)
    if (at) this.panCamera(this.focalPlane(), pos, [0.5, 0.5])
    this.host.changed()
  }

  private setRotationCenter(c: THREE.Vector3) {
    this.center.copy(c)
    this.centerFound = true
    const p = this.parts()
    if (p && !this.ortho(p.cam)) {
      // A perspective camera focuses at the rotation centre's depth, so zoom works there.
      const d = viewDir(p.cam.quaternion)
      p.tgt.copy(p.cam.position).addScaledVector(d, c.clone().sub(p.cam.position).dot(d))
    }
  }

  /** reorientCamera: turn by `r` (camera axes) about a centre, keeping the focal distance. */
  private reorient(r: THREE.Quaternion, center?: THREE.Vector3) {
    const p = this.parts()
    if (!p) return
    const c = center ?? p.tgt.clone()
    const cur = p.cam.quaternion.clone(), next = cur.clone().multiply(r)
    const fd = p.tgt.clone().sub(p.cam.position).dot(viewDir(cur))
    const rel = p.cam.position.clone().sub(c).applyQuaternion(cur.clone().invert())
    p.cam.quaternion.copy(next)
    p.cam.position.copy(c).add(rel.applyQuaternion(next))
    p.cam.up.copy(Y).applyQuaternion(next)
    p.tgt.copy(p.cam.position).addScaledVector(viewDir(next), fd)
    this.host.changed()
  }

  private spinOnce(pointerpos: V2, lastpos: V2) {
    const p = this.parts()
    if (!p) return
    let sensitivity = this.prefs.sensitivity
    const pr = this.proj
    // Trackball styles orbit a picked point: centre the sphere on it on screen.
    if (pr.orbit !== 0 && pr.orbit !== 2 && this.prefs.rotationMode !== 0 && this.centerFound && this.centerAtCursor) {
      const s = this.center.clone().project(p.cam)
      const len = Math.hypot(s.x, s.y), scale = 1 + len
      pr.c.set(s.x, s.y, 0)
      pr.r = SPHERE_RADIUS * scale
      sensitivity *= scale
    } else { pr.c.set(0, 0, 0); pr.r = SPHERE_RADIUS }
    pr.worldToScreen.copy(p.cam.quaternion).invert()
    pr.project(lastpos)
    let r = pr.rotationTo(pointerpos)
    if (sensitivity > 1) { const [axis, a] = axisAngle(r); r = rot(axis, a * sensitivity) }
    r.invert()
    this.reorient(r, this.prefs.rotationMode !== 0 && this.centerFound ? this.center : undefined)
    // Average the last few increments, for a spin animation on release.
    const [axis, a] = axisAngle(r)
    const n = this.spinInc.n
    this.spinInc = { axis, angle: (this.spinInc.angle * n + a) / (n + 1), n: Math.min(3, n + 1) }
  }
  /** spin: orbit from the previous logged position to the pointer. */
  private spin(pointerpos: V2) {
    if (this.log.length < 2) return
    const lastpos = this.normalize(this.log[1].pos)
    if (this.proj.orbit === 2) { const mid: V2 = [lastpos[0], pointerpos[1]]; this.spinOnce(pointerpos, mid); this.spinOnce(mid, lastpos) }
    else this.spinOnce(pointerpos, lastpos)
    if (this.mode !== 'IDLE') this.hasDragged = true
  }
  private spinSimplifiedOnce(cur: V2, prev: V2) {
    const p = this.parts()
    if (!p) return
    this.proj.worldToScreen.copy(p.cam.quaternion).invert()
    this.proj.project(prev)
    let r = this.proj.rotationTo(cur)
    const s = this.prefs.sensitivity
    if (s > 1) { const [axis, a] = axisAngle(r); r = rot(axis, a * s) }
    r.invert()
    this.reorient(r, this.prefs.rotationMode !== 0 && this.centerFound ? this.center : undefined)
  }
  /** spin_simplified: orbit from one pointer position to the next. */
  private spinSimplified(cur: V2, prev: V2) {
    if (this.proj.orbit === 2) { const mid: V2 = [prev[0], cur[1]]; this.spinSimplifiedOnce(cur, mid); this.spinSimplifiedOnce(mid, prev) }
    else this.spinSimplifiedOnce(cur, prev)
    this.hasDragged = true
  }

  private addToLog(pos: V2, t: number) {
    if (this.log.length && pos[0] === this.log[0].pos[0] && pos[1] === this.log[0].pos[1]) return
    this.log.unshift({ pos, t })
    if (this.log.length > 16) this.log.pop()
  }

  /** doSpin: after a quick release, keep turning (UseSpinningAnimations). */
  private doSpin(): boolean {
    if (this.log.length < 3 || !this.prefs.spinning || performance.now() / 1000 - this.log[0].t >= 0.1) return false
    const from = this.proj.project(this.normalize(this.log[2].pos)), to = this.proj.project(this.last)
    const r = this.proj.rotation(from, to).invert()
    const dt = this.log[0].t - this.log[2].t
    const [axis, a] = axisAngle(r)
    const radians = a * (0.2 / dt)
    if (radians > 0.01 && dt < 0.3) { this.startSpinning(axis, radians * 5); return true }
    return false
  }

  /** saveCursorPosition: where the next orbit turns about (RotationMode). */
  private saveCursorPosition(pos: V2) {
    this.centerAtCursor = false
    const p = this.parts()
    if (!p) return
    const mode = this.prefs.rotationMode
    if (mode === 0) { this.setRotationCenter(p.tgt.clone()); return }
    const hit = this.host.scenePoint(pos)
    if (hit) { this.setRotationCenter(hit); this.centerAtCursor = true; return }
    if (mode === 1) { const c = this.linePlane(this.focalPlane(), this.normalize(pos)); if (c) this.setRotationCenter(c) }
    else { const box = this.host.sceneBox(); if (box && !box.isEmpty()) this.setRotationCenter(box.getCenter(new THREE.Vector3())) }
  }

  /** lookAtPoint: make the point under the cursor the centre of the view. */
  private lookAtPoint(pos: V2) {
    const p = this.parts()
    if (!p) return
    const point = this.host.scenePoint(pos) ?? this.linePlane(this.plane, this.normalize(pos))
    if (!point) return
    this.translateCamera(point.clone().sub(p.tgt))
    this.center.copy(point)
    this.centerFound = true
  }

  private setViewing(on: boolean) {
    if (this.viewing === on) return
    this.setViewingMode(on ? 'IDLE' : 'INTERACT')
    this.viewing = on
  }

  private setViewingMode(newmode: Mode) {
    const old = this.mode
    if ((old === 'IDLE' && newmode !== 'IDLE') || (newmode === 'IDLE' && !this.b1 && !this.b2 && !this.b3)) {
      this.hasPanned = this.hasDragged = this.hasZoomed = false
    }
    if (newmode === old) {
      if (newmode === 'DRAGGING' && this.centerFound) this.showMarker(true)
      return
    }
    if (newmode === 'DRAGGING') {
      this.stopAnimating()
      this.showMarker(true)
      this.proj.project(this.last)
      this.log = []
    } else if (newmode === 'PANNING') { this.stopAnimating(); this.setupPanningPlane() }
    else if (newmode === 'ZOOMING' || newmode === 'BOXZOOM') this.stopAnimating()
    if (old === 'DRAGGING' || old === 'SPINNING') this.showMarker(false)
    if (old === 'SPINNING') this.stopAnimating()
    this.host.cursor(CURSOR[newmode])
    this.mode = newmode
  }
  private showMarker(on: boolean) {
    this.host.marker(on && this.prefs.showRotationCenter && this.centerFound ? this.center.clone() : null)
  }

  // ── animations (NavigationAnimation.cpp) ──────────────────────────────────
  stopAnimating() {
    const a = this.anim
    this.anim = null
    a?.stop(false)
  }
  get animating() { return this.anim !== null }

  /** FixedTimeAnimation: turn to an orientation about a centre while translating,
   *  InOutCubic over AnimationDuration. Without animations it jumps. */
  startAnimation(q1: THREE.Quaternion, center: THREE.Vector3, translation: THREE.Vector3, done?: () => void) {
    const p = this.parts()
    if (!p) return
    this.stopAnimating()
    const fd = p.tgt.clone().sub(p.cam.position).dot(viewDir(p.cam.quaternion))
    const q0 = p.cam.quaternion.clone()
    const world = q1.clone().multiply(q0.clone().invert())
    let [axisW, angle] = axisAngle(world)
    if (angle > Math.PI) angle -= 2 * Math.PI
    const axis = axisW.applyQuaternion(q0.clone().invert())
    const put = (k: number, prevA: number, prevT: THREE.Vector3) => {
      const a = angle * k, t = translation.clone().multiplyScalar(k)
      p.cam.position.sub(prevT)
      const cur = p.cam.quaternion.clone(), next = cur.clone().multiply(rot(axis, a - prevA))
      const rel = p.cam.position.clone().sub(center).applyQuaternion(cur.clone().invert())
      p.cam.quaternion.copy(next)
      p.cam.position.copy(center).add(rel.applyQuaternion(next)).add(t)
      p.cam.up.copy(Y).applyQuaternion(next)
      p.tgt.copy(p.cam.position).addScaledVector(viewDir(next), fd)
      return { a, t }
    }
    const end = (last: { a: number; t: THREE.Vector3 }) => {
      p.cam.quaternion.copy(q1)
      p.cam.up.copy(Y).applyQuaternion(q1)
      p.cam.position.add(translation.clone().sub(last.t))
      p.tgt.copy(p.cam.position).addScaledVector(viewDir(q1), fd)
      this.host.changed()
      done?.()
    }
    const ms = this.prefs.duration
    if (!this.prefs.animate || ms <= 0 || document.visibilityState !== 'visible') {
      // setCameraOrientation's direct path: the new orientation about the centre, plus the move.
      end(put(1, 0, new THREE.Vector3()))
      return
    }
    const start = performance.now()
    let prev = { a: 0, t: new THREE.Vector3() }, frame = 0, live = true
    const step = () => {
      if (!live) return
      const k = Math.min(1, (performance.now() - start) / ms)
      if (k >= 1) { this.anim = null; end(prev); return }
      prev = put(inOutCubic(k), prev.a, prev.t)
      this.host.changed()
      frame = requestAnimationFrame(step)
    }
    this.anim = { stop: (finished) => { live = false; cancelAnimationFrame(frame); if (finished) end(prev) } }
    step()
  }

  /** translateCamera (lookAtPoint and Fit): animated like a view change. */
  private translateCamera(t: THREE.Vector3) {
    const p = this.parts()
    if (p) this.startAnimation(p.cam.quaternion.clone(), p.tgt.clone(), t)
  }

  /** SpinningAnimation: keep turning about an axis (camera axes), `velocity` rad/s. */
  spinAnimation(axis: THREE.Vector3, velocity: number) { this.startSpinning(axis, velocity) }
  private startSpinning(axis: THREE.Vector3, velocity: number) {
    this.stopAnimating()
    let t0 = performance.now(), frame = 0, live = true
    this.setViewing(true)
    this.setViewingMode('SPINNING')
    const step = () => {
      if (!live) return
      const now = performance.now()
      this.reorient(rot(axis, (velocity * (now - t0)) / 1000))
      t0 = now
      frame = requestAnimationFrame(step)
    }
    this.anim = { stop: () => { live = false; cancelAnimationFrame(frame); if (this.mode === 'SPINNING') this.setViewingMode(this.viewing ? 'IDLE' : 'INTERACT') } }
    frame = requestAnimationFrame(step)
  }

  // ── events ────────────────────────────────────────────────────────────────
  /** NavigationStyle::processEvent: the rubber band first, then the style; a left
   *  click on nothing clears the selection unless Ctrl is down. */
  processEvent(ev: NavEvent): boolean {
    this.mouse = ev.type === 'key' ? this.mouse : ev.pos
    if (ev.type === 'key') ev = { ...ev, pos: this.mouse }
    this.longPressFilter(ev)
    // The press that opened Clarify Selection ends in its menu, not in a click.
    if (this.swallow && ev.type === 'release' && ev.button === 1) { this.swallow = false; return true }
    if (this.box) return this.boxEvent(ev)
    // SoQTQuarterAdaptor::processSoEvent sits above every style: on a plain arrow-key keydown
    // it pans and consumes the event right there, before any NavigationStyle runs at all — so
    // this must be checked before processSoEvent below, not gated on its result. (Dispatching
    // to the style first would break under OpenInventor: InventorNavigationStyle::processSoEvent
    // returns true for anything outside SELECTION/editing, which would swallow the key.) Shift+
    // Left/Right and Ctrl/Cmd+arrows are shortcuts (Std_ViewRotateLeft/Right,
    // Std_DockOverlayToggle*), so they never reach here at all.
    if (ev.type === 'key' && ev.down && !ev.ctrl && !(ev.shift && (ev.key === 'ArrowLeft' || ev.key === 'ArrowRight'))) {
      const d = ({ ArrowLeft: [-0.1, 0], ArrowUp: [0, 0.1], ArrowRight: [0.1, 0], ArrowDown: [0, -0.1] } as Record<string, V2>)[ev.key ?? '']
      if (d) { this.moveCameraScreen(d); return true }
    }
    const curmode = this.mode
    const processed = this.processSoEvent(ev)
    if ((curmode === 'SELECTION' || curmode === 'IDLE') && !processed && ev.type === 'release' && ev.button === 1 && !ev.ctrl) this.host.clearSelection()
    return processed
  }

  /** moveCameraScreen: the camera moves by the focal-plane step from the view's centre to
   *  the centre plus `d` (normalized, y up), backwards. */
  moveCameraScreen(d: V2) { this.panCamera(this.focalPlane(), [0.5 + d[0], 0.5 + d[1]], [0.5, 0.5]) }

  /** The rubber band of a drag box selection (BoxSelectSelection). */
  private boxEvent(ev: NavEvent): boolean {
    const box = this.box!
    if (ev.type === 'move') { box.b = ev.pos; this.host.band(box.a, box.b); return true }
    if (ev.type === 'key' && ev.key === 'Escape' && ev.down) { this.box = null; this.host.band(null); this.resetButtonState(); return true }
    if (ev.type === 'release' && ev.button === 1) {
      this.box = null
      this.host.band(null)
      this.b1 = false
      this.host.boxSelect(box.a, ev.pos, box.additive)
      if (!this.b1 && !this.b2 && !this.b3 && this.mode !== 'IDLE') this.setViewingMode('IDLE')
      return true
    }
    if (ev.type === 'press' || ev.type === 'release') this.syncButtons(ev)
    return true
  }

  resetButtonState() {
    this.b1 = this.b2 = this.b3 = false
    this.setViewingMode('IDLE')
  }

  /** The View3DInventorViewer event filter's long press: Clarify Selection. */
  private longPressFilter(ev: NavEvent) {
    if (ev.type === 'press' && ev.button === 1) {
      clearTimeout(this.longPress)
      const p = this.prefs
      if (!p.clarifyLongPress || (CLARIFY_CTRL.includes(this.style) && !ev.ctrl) || this.host.draggerUnderCursor()) return
      this.longPressAt = ev.pos
      this.longPress = window.setTimeout(() => { this.resetButtonState(); this.swallow = true; this.host.clarify(this.longPressAt) }, p.longPressTimeout * 1000)
    } else if (ev.type === 'release' && ev.button === 1) clearTimeout(this.longPress)
    else if (ev.type === 'move' && Math.abs(ev.pos[0] - this.longPressAt[0]) + Math.abs(ev.pos[1] - this.longPressAt[1]) > 5) clearTimeout(this.longPress)
  }

  /** NavigationStyle::processSoEvent: the wheel, else the scene graph. */
  private baseEvent(ev: NavEvent): boolean {
    const processed = this.host.scene(ev)
    if (processed && ev.type === 'press' && ev.button === 1 && this.mode === 'SELECTION') {
      this.selStart = null
      this.setViewingMode('INTERACT')
    }
    return processed
  }

  /** ViewerEventFilter::isUnwantedHorizontalScroll's `touchpad && touchpadScrollPans()` half,
   *  for the DOM wheel handler (bindNavigation can't reach the private `prefs` getter). */
  touchpadScrollPans() { return this.prefs.touchpadScrollPans }
  /** A mouse wheel or touchpad scroll (processWheelEvent). `delta` is 120 a notch;
   *  `pixels` is a touchpad's movement, y up. */
  wheel(pos: V2, delta: number, pixels: V2 | null, shift: boolean, ctrl: boolean, begin: boolean) {
    const precise = pixels !== null
    const action = !precise || !this.prefs.touchpadScrollPans || ctrl ? 'zoom' : shift ? 'orbit' : 'pan'
    if (begin) this.saveCursorPosition(pos)
    if (action === 'orbit') { const c: V2 = [0.5, 0.5], d = this.normalize(pixels!); this.spinSimplified([c[0] + d[0], c[1] + d[1]], c) }
    else if (action === 'pan') { this.setupPanningPlane(); this.panCamera(this.plane, this.normalize(pixels!), [0, 0]) }
    else this.doZoomSteps(delta, this.normalize(pos))
  }
  /** A pinch: zoom by -log(scale) at its centre (processPinchEvent/pinchAction's zoom half).
   *  Missing: pinchAction's pan-by-deltaCenter and rotate-by-deltaAngle (gated by
   *  DisableTouchTilt, default true, unless fromNativeGesture) halves. The browser's only
   *  pinch signal here is a synthesized Ctrl+wheel event (a trackpad gesture the OS turns
   *  into wheel deltas) with just a scale delta — no gesture centre movement or twist angle,
   *  which FreeCAD gets from Coin's two-finger touch gesture. Reproducing those needs real
   *  two-pointer tracking (two live pointerIds in bindNavigation, to compute a centre delta
   *  and angle each update) instead of the wheel event this reads. */
  pinch(pos: V2, logfactor: number) { this.doZoom(logfactor, this.normalize(pos)) }

  private processKeyboardEvent(ev: NavEvent): boolean {
    // NavigationStyle::processKeyboardEvent's PAGE_UP/PAGE_DOWN cases don't check press vs
    // release (the `press` bool is computed but unused there), so both fire a zoom step.
    if (ev.key === 'PageUp') { this.doZoomSteps(120, this.normalize(ev.pos)); return true }
    if (ev.key === 'PageDown') { this.doZoomSteps(-120, this.normalize(ev.pos)); return true }
    if (ev.down && ['s', 'S', 'Home', 'ArrowLeft', 'ArrowUp', 'ArrowRight', 'ArrowDown'].includes(ev.key ?? '')) this.setViewing(true)
    if (this.style === 'siemensnx' && ev.down) {
      // SiemensNXNavigationStyle::processKeyboardEvent (Home and End stay FreeCAD's shortcuts).
      if ((ev.key === 'f' || ev.key === 'F') && ev.ctrl) { this.host.viewAll(); return true }
      if (ev.key === 'F8') { this.host.orient('top'); return true }
    }
    return false
  }

  private syncButtons(ev: NavEvent) {
    const press = ev.type === 'press'
    if (ev.button === 1) this.b1 = press
    else if (ev.button === 2) this.b2 = press
    else if (ev.button === 3) this.b3 = press
  }
  private syncModifierKeys(ev: NavEvent) { this.ctrl = ev.ctrl; this.shift = ev.shift; this.alt = ev.alt }

  private processClickEvent(_ev: NavEvent): boolean { return false }

  private isDraggerUnder() { return this.host.draggerUnderCursor() }

  /** tryStartBoxSelection: a left drag past the drag distance starts a rubber band. */
  private tryStartBoxSelection(start: V2 | null, ev: NavEvent, additive: boolean): boolean {
    if (!start || this.box || this.isDraggerUnder()) return false
    if (Math.hypot(ev.pos[0] - start[0], ev.pos[1] - start[1]) <= DRAG_DISTANCE) return false
    clearTimeout(this.longPress)
    this.host.scene({ ...ev, type: 'move', pos: [-1e6, -1e6] }) // rmvPreselect
    this.box = { a: start, b: ev.pos, additive }
    this.selStart = null
    this.host.band(start, ev.pos)
    return true
  }
  private handleSelectionDragMotion(ev: NavEvent, set: (m: Mode) => void, additive: boolean, allowBox = true): boolean {
    if (this.host.scene(ev) && this.interact) { set('INTERACT'); return true }
    return allowBox && this.tryStartBoxSelection(this.selStart, ev, additive)
  }

  private processSoEvent(ev: NavEvent): boolean {
    switch (this.style) {
      case 'gesture': return this.gesture(ev)
      case 'mayagesture': return this.mayaGesture(ev)
      case 'siemensnx': return this.siemensNX(ev)
      default: return this.classic(ev)
    }
  }

  // ── the button-combination styles ─────────────────────────────────────────
  /** Blender, CAD, OpenCascade, OpenInventor, OpenSCAD, Revit, SolidWorks, TinkerCAD
   *  and Touchpad: each style's processSoEvent, one after the other. */
  private classic(ev: NavEvent): boolean {
    const s = this.style
    if (!this.animating && this.viewing) this.setViewing(false)
    const posn = this.normalize(ev.pos), prev = this.last
    this.last = posn
    let processed = false, triedSelectionDrag = false
    const curmode = this.mode
    let newmode: Mode = curmode
    this.syncModifierKeys(ev)
    const press = ev.type === 'press', release = ev.type === 'release', button = ev.type === 'press' || ev.type === 'release'
    const quick = () => ev.t - this.centerTime < DCI
    const toDrag = () => { newmode = 'DRAGGING'; this.saveCursorPosition(ev.pos); this.centerTime = ev.t; processed = true }
    const dragged = () => this.hasDragged || this.hasPanned || this.hasZoomed
    /** The right click's menu, unless the button was navigating. */
    const popup = (except: Mode[]) => { if (!except.includes(this.mode)) this.host.popup(ev.pos) }
    const ZPD: Mode[] = ['ZOOMING', 'PANNING', 'DRAGGING']

    if (ev.type === 'key') processed = this.processKeyboardEvent(ev)

    if (button && ev.button === 1) {
      if (s === 'openinventor') {
        this.b1 = press
        if (press && ev.shift && this.mode !== 'SELECTION') { this.centerTime = ev.t; this.setupPanningPlane(); this.lockrecenter = false }
        else if (release && ev.shift && this.mode !== 'SELECTION') { if (quick() && !this.lockrecenter) { this.lookAtPoint(ev.pos); processed = true } }
        else if (press && this.mode === 'IDLE') { this.setViewing(true); processed = true; this.lockrecenter = true }
        else if (release && this.mode === 'DRAGGING') { this.setViewing(false); processed = true; this.lockrecenter = true }
        else processed = this.processClickEvent(ev)
      } else {
        if (s !== 'tinkercad') this.lockrecenter = true
        this.b1 = press
        if (s !== 'openscad') this.selStart = press ? ev.pos : null
        const panzoom = this.mode === 'PANNING' || this.mode === 'ZOOMING'
        if ((s === 'opencascade' || s === 'openscad') && release && this.mode === 'ZOOMING') { newmode = 'IDLE'; processed = true }
        else if ((s === 'opencascade' || s === 'openscad') && release && this.mode === 'DRAGGING') { this.setViewing(false); processed = true }
        else if (['blender', 'cad', 'revit', 'solidworks', 'touchpad'].includes(s) && press && panzoom) toDrag()
        else if (s === 'cad' && release && this.mode === 'DRAGGING') { if (quick()) newmode = 'ZOOMING'; processed = true }
        else if (['blender', 'revit', 'solidworks'].includes(s) && release && this.mode === 'DRAGGING') processed = true
        else processed = this.processClickEvent(ev)
      }
    }

    if (button && ev.button === 2) {
      const panzoom = this.mode === 'PANNING' || this.mode === 'ZOOMING'
      switch (s) {
        case 'tinkercad':
          this.b2 = press
          if (press && curmode === 'IDLE') { this.saveCursorPosition(ev.pos); this.centerTime = ev.t; processed = true }
          else if (release && dragged()) processed = true
          else if (release) { newmode = 'IDLE'; popup(['ZOOMING', 'PANNING']); processed = true }
          break
        case 'cad':
          this.lockrecenter = true
          if (release && dragged()) processed = true
          if (release) popup(ZPD)
          if (press && panzoom) toDrag()
          else if (release && this.mode === 'DRAGGING') { if (quick()) newmode = 'ZOOMING'; processed = true }
          this.b2 = press
          break
        case 'openscad':
          this.lockrecenter = true
          this.b2 = press
          if (release && dragged()) processed = true
          else if (release) popup(['ZOOMING', 'DRAGGING'])
          if (press && panzoom) toDrag()
          else if (release && this.mode === 'DRAGGING') { newmode = 'IDLE'; processed = true }
          break
        case 'opencascade':
          this.lockrecenter = true
          if (release && dragged()) processed = true
          else if (release) popup(ZPD)
          if (press && panzoom) toDrag()
          else if (release && this.mode === 'DRAGGING') { newmode = 'IDLE'; processed = true }
          this.b2 = press
          break
        case 'openinventor':
          this.lockrecenter = true
          if (release && dragged()) processed = true
          else if (release) popup(ZPD)
          this.b2 = press
          break
        default: // Blender, Revit, SolidWorks, Touchpad
          this.lockrecenter = true
          if (release && dragged()) processed = true
          else if (release) popup(ZPD)
          if (press && panzoom) toDrag()
          this.b2 = press
      }
    }

    if (button && ev.button === 3) {
      switch (s) {
        case 'touchpad': break // no middle button
        case 'tinkercad':
          this.b3 = press
          if (press) { this.centerTime = ev.t; this.setupPanningPlane() }
          else if (curmode === 'PANNING') { newmode = 'IDLE'; processed = true }
          break
        case 'openscad':
          this.b3 = press
          if (press) { this.centerTime = ev.t; this.setupPanningPlane(); this.lockrecenter = false }
          else if (curmode === 'PANNING') { newmode = 'IDLE'; processed = true }
          break
        case 'opencascade':
          if (press) { this.centerTime = ev.t; this.setupPanningPlane(); this.lockrecenter = false }
          else if (this.mode === 'PANNING') { newmode = 'IDLE'; processed = true }
          this.b3 = press
          break
        default: // Blender, CAD, OpenInventor, Revit, SolidWorks: a quick middle click centres the view there
          if (press) { this.centerTime = ev.t; this.setupPanningPlane(); this.lockrecenter = false }
          else if (quick() && !this.lockrecenter) { this.lookAtPoint(ev.pos); processed = true }
          this.b3 = press
      }
    }

    const CTRL = 4, SHIFT = 8, ALT = 32, B1 = 1, B2 = 16, B3 = 2
    const comboOf = () => (this.b1 ? B1 : 0) | (this.b2 ? B2 : 0) | (s === 'touchpad' ? 0 : this.b3 ? B3 : 0)
      | (this.ctrl ? CTRL : 0) | (this.shift ? SHIFT : 0) | (s === 'touchpad' && this.alt ? ALT : 0)

    if (ev.type === 'move') {
      if (s !== 'tinkercad') this.lockrecenter = true
      if (s === 'openscad') {
        if (curmode === 'SELECTION') {
          if (this.b1 && this.isDraggerUnder()) newmode = 'INTERACT'
          else { newmode = 'DRAGGING'; this.saveCursorPosition(ev.pos); this.centerTime = ev.t }
        } else if (curmode === 'ZOOMING') { const v = (posn[1] - prev[1]) * 10; this.zoom(this.prefs.invertZoom ? -v : v); processed = true }
        else if (curmode === 'PANNING') { this.panCamera(this.plane, posn, prev); processed = true }
        else if (curmode === 'DRAGGING') { this.addToLog(ev.pos, ev.t); this.spin(posn); processed = true }
      } else if (s !== 'openinventor' && this.mode === 'SELECTION' && this.b1 && !(s === 'opencascade' && this.ctrl)) {
        triedSelectionDrag = true
        processed = this.handleSelectionDragMotion(ev, (m) => { newmode = m }, s === 'opencascade' ? false : this.ctrl)
      } else if (this.mode === 'ZOOMING' && s !== 'tinkercad') {
        if (s === 'opencascade') { const v = (posn[0] - prev[0]) * 10; this.zoom(this.prefs.invertZoom ? -v : v) }
        else this.zoomByCursor(posn, prev)
        processed = true
      } else if (this.mode === 'PANNING') {
        if (s === 'touchpad') { if (!this.blockPan) this.panCamera(this.plane, posn, prev); this.blockPan = false }
        else this.panCamera(this.plane, posn, prev)
        processed = true
      } else if (this.mode === 'DRAGGING') { this.addToLog(ev.pos, ev.t); this.spin(posn); processed = true }
      else if (s === 'opencascade' && comboOf() === (CTRL | B1)) newmode = 'ZOOMING'
    }

    const combo = comboOf()
    const lockCase0 = () => { newmode = 'IDLE'; if (this.lockButton1) { this.lockButton1 = false; if (curmode !== 'SELECTION') processed = true } }
    const selectCase = () => {
      if (newmode === 'INTERACT') return
      newmode = curmode === 'SPINNING' || (this.lockButton1 && curmode !== 'SELECTION') ? 'IDLE' : 'SELECTION'
    }
    const dragCase = () => { if (newmode !== 'DRAGGING') this.saveCursorPosition(ev.pos); newmode = 'DRAGGING' }
    switch (s) {
      case 'blender':
        if (combo === 0) { if (curmode !== 'SPINNING') lockCase0() }
        else if (combo === B1 || combo === (CTRL | B1)) selectCase()
        else if (combo === (B1 | B2) || combo === (SHIFT | B3)) newmode = 'PANNING'
        else if (combo === B3) dragCase()
        else if (combo === (CTRL | SHIFT | B2) || combo === (CTRL | B3)) newmode = 'ZOOMING'
        else if ((curmode === 'PANNING' || curmode === 'ZOOMING') && !this.b3) newmode = 'IDLE'
        break
      case 'cad':
        if (combo === 0) { if (curmode !== 'SPINNING') lockCase0() }
        else if (combo === B1 || combo === (CTRL | B1)) selectCase()
        else if (combo === B3) {
          if (curmode !== 'SPINNING' && newmode !== 'ZOOMING') {
            newmode = 'PANNING'
            if (curmode === 'DRAGGING' && this.doSpin()) newmode = 'SPINNING'
          }
        }
        else if (combo === (CTRL | B2)) newmode = 'PANNING'
        else if (combo === (SHIFT | B2)) dragCase()
        else if (combo === (CTRL | SHIFT | B2)) newmode = 'ZOOMING'
        break
      case 'revit':
        if (combo === 0) { if (curmode !== 'SPINNING') lockCase0() }
        else if (combo === B1 || combo === (CTRL | B1)) selectCase()
        else if (combo === (B1 | B2) || combo === B3) newmode = 'PANNING'
        else if (combo === (SHIFT | B3)) dragCase()
        else if (combo === (CTRL | SHIFT | B2) || combo === (CTRL | B3)) newmode = 'ZOOMING'
        else if ((curmode === 'DRAGGING' || curmode === 'ZOOMING') && !this.b3) newmode = 'IDLE'
        break
      case 'solidworks':
        if (combo === 0) { if (curmode !== 'SPINNING') lockCase0() }
        else if (combo === B1 || combo === (CTRL | B1)) selectCase()
        else if (combo === (SHIFT | B3)) newmode = 'ZOOMING'
        else if (combo === B3) dragCase()
        else if (combo === (CTRL | B3)) newmode = 'PANNING'
        else if ((curmode === 'PANNING' || curmode === 'ZOOMING') && !this.b3) newmode = 'IDLE'
        break
      case 'touchpad':
        if (combo === 0) { if (curmode !== 'SPINNING') newmode = 'IDLE' }
        else if (combo === B1 || combo === (CTRL | B1)) { if (newmode !== 'INTERACT') newmode = curmode === 'SPINNING' ? 'IDLE' : 'SELECTION' }
        else if (combo === CTRL) newmode = 'IDLE'
        else if (combo === SHIFT) { if (newmode === 'DRAGGING') processed = true; newmode = 'PANNING'; if (this.mode !== 'PANNING') this.blockPan = true }
        else if (combo === ALT) dragCase()
        else if (combo === (CTRL | SHIFT) || combo === (CTRL | SHIFT | B1)) { if (newmode === 'ZOOMING') processed = true; newmode = 'ZOOMING' }
        break
      case 'tinkercad':
        if (combo === 0) { if (curmode !== 'SPINNING') newmode = 'IDLE' }
        else if (combo === B1 || combo === (CTRL | B1)) { if (newmode !== 'INTERACT') newmode = 'SELECTION' }
        else if (combo === B2) dragCase()
        else if (combo === B3) newmode = 'PANNING'
        break
      case 'opencascade':
        if (combo === 0) { if (curmode !== 'SPINNING') newmode = 'IDLE' }
        else if (combo === (CTRL | B1) || combo === B1) { if (newmode !== 'ZOOMING' && newmode !== 'INTERACT') newmode = 'SELECTION' }
        else if (combo === (CTRL | B3) || combo === B3) newmode = 'PANNING'
        else if (combo === (CTRL | B2)) dragCase()
        else if (combo === B2) newmode = 'IDLE'
        break
      case 'openscad':
        if (combo === 0) { if (curmode !== 'SPINNING') newmode = 'IDLE' }
        else if (combo === B1) { if (newmode !== 'DRAGGING' && newmode !== 'INTERACT') newmode = 'SELECTION' }
        else if (combo === B2) newmode = 'PANNING'
        else if (combo === B3 || combo === (SHIFT | B2) || combo === (SHIFT | B3)) newmode = 'ZOOMING'
        break
      case 'openinventor':
        if (combo === 0) { if (curmode !== 'SPINNING') { newmode = 'IDLE'; if (curmode === 'DRAGGING' && this.doSpin()) newmode = 'SPINNING' } }
        else if (combo === B1) { if (curmode !== 'SELECTION') dragCase() }
        else if (combo === B3 || combo === (CTRL | SHIFT) || combo === (CTRL | SHIFT | B1)) newmode = 'PANNING'
        else if (combo === CTRL || combo === (CTRL | B1) || combo === SHIFT || combo === (SHIFT | B1)) newmode = 'SELECTION'
        else if (combo === (B1 | B3) || combo === (CTRL | B3) || combo === (CTRL | SHIFT | B2)) newmode = 'ZOOMING'
        break
    }

    if (this.b1 && (this.b2 || this.b3 || (s === 'opencascade' && this.ctrl) || (s === 'touchpad' && this.alt))) {
      if (s === 'cad' || s === 'opencascade') this.selStart = null
      if (['blender', 'cad', 'revit', 'solidworks'].includes(s)) this.lockButton1 = true
      processed = true
    }
    if (newmode === 'IDLE' && !this.b1 && !this.b2 && !this.b3) this.hasPanned = this.hasDragged = this.hasZoomed = false
    if (newmode !== curmode) this.setViewingMode(newmode)

    if (s === 'openinventor') {
      if ((curmode === 'SELECTION' || newmode === 'SELECTION') && !processed) return this.baseEvent(ev)
      return true
    }
    if (!processed && (s === 'openscad' || !triedSelectionDrag)) processed = this.baseEvent(ev)
    return processed
  }

  // ── Gesture (GestureNavigationStyle.cpp, a state machine) ─────────────────
  private mbstate() { return (this.b1 ? 0x100 : 0) | (this.b3 ? 0x010 : 0) | (this.b2 ? 0x001 : 0) }

  private gesture(ev: NavEvent): boolean {
    if (!this.animating && this.viewing) this.setViewing(false)
    if (ev.type === 'release' && ((ev.button === 1 && !this.b1) || (ev.button === 2 && !this.b2) || (ev.button === 3 && !this.b3))) return true
    if (ev.type === 'press' || ev.type === 'release') this.syncButtons(ev)
    this.syncModifierKeys(ev)
    const r = { processed: false, propagated: false }
    const isPress = (b: number) => ev.type === 'press' && ev.button === b
    const isRelease = (b: number) => ev.type === 'release' && ev.button === b
    const button = ev.type === 'press' || ev.type === 'release'
    const mb = this.mbstate()
    const refire = () => {
      for (const p of this.postponed) this.baseEvent(p)
      this.postponed = []
      r.processed = this.baseEvent(ev)
      r.propagated = true
    }
    const enter = (st: string) => {
      this.postponed = st === 'AwaitingMove' ? this.postponed : []
      this.state = st
      if (st === 'Idle') this.setViewingMode('IDLE')
      else if (st === 'AwaitingMove') { this.setViewingMode('IDLE'); this.base = ev.pos; this.since = ev.t }
      else if (st === 'Rotate') { this.saveCursorPosition(ev.pos); this.setViewingMode('DRAGGING'); this.base = ev.pos }
      else if (st === 'Pan' || st === 'StickyPan') { this.setViewingMode('PANNING'); this.base = ev.pos; this.setupPanningPlane() }
      else if (st === 'Tilt') { const p = this.parts(); if (p) this.setRotationCenter(p.tgt.clone()); this.setViewingMode('DRAGGING'); this.base = ev.pos; this.setupPanningPlane() }
      else if (st === 'Interact') this.setViewingMode('INTERACT')
    }
    const roll = () => {
      if (mb === 0x101) { if (isPress(1)) this.rollDir = -1; if (isPress(2)) this.rollDir = +1 }
      // GestureRollFwdCommand / GestureRollBackCommand are empty by default.
      return (isRelease(1) && mb === 0x001) || (isRelease(2) && mb === 0x100)
    }
    switch (this.state) {
      case 'Idle': {
        if (isPress(1) && mb === 0x100 && this.isDraggerUnder()) { enter('Interact'); break }
        if ((isPress(1) && mb === 0x100) || (isPress(2) && mb === 0x001)) { this.postponed.push(ev); r.processed = true; enter('AwaitingMove'); break }
        if (isPress(3) && mb === 0x010) { r.processed = true; this.setupPanningPlane(); this.lookAtPoint(ev.pos); enter('AwaitingRelease'); break }
        if (ev.type === 'key') {
          r.processed = true
          if ((ev.key === 'h' || ev.key === 'H') && !ev.down) { this.setupPanningPlane(); this.lookAtPoint(ev.pos) }
          else if (ev.key === 'PageUp' && !ev.down) this.doZoomSteps(120, this.normalize(ev.pos))
          else if (ev.key === 'PageDown' && !ev.down) this.doZoomSteps(-120, this.normalize(ev.pos))
          else r.processed = false
        }
        break
      }
      case 'AwaitingMove': {
        const long = ev.t - this.since >= HOLD_TIMEOUT
        r.processed = button || ev.type === 'move'
        if (isRelease(2) && mb === 0) { this.host.popup(ev.pos); enter('Idle'); break }
        if (roll()) { enter('AwaitingRelease'); break }
        if (button && mb === 0) {
          if (long) { this.host.popup(ev.pos); enter('Idle') }
          else { this.setViewingMode('SELECTION'); refire(); enter('Idle') }
          break
        }
        if (isPress(3)) { refire(); enter('Idle'); break }
        if (button) this.postponed.push(ev)
        if (ev.type === 'move' && Math.hypot(ev.pos[0] - this.base[0], ev.pos[1] - this.base[1]) > DRAG_DISTANCE) {
          if (mb === 0x100 && ev.shift && this.tryStartBoxSelection(this.base, ev, ev.ctrl)) { r.processed = true; this.postponed = []; this.state = 'Idle'; break }
          if (mb === 0x100) {
            if (!long) { if (!ev.alt) { this.postponed = []; enter('Rotate') } else { refire(); enter('Idle') } }
            else { this.postponed = []; enter('StickyPan') }
          } else if (mb === 0x001) { this.postponed = []; enter('Pan') }
          else if (mb === 0x101) { this.postponed = []; enter('Tilt') }
          else { refire(); enter('Idle') }
        }
        break
      }
      case 'Rotate':
        if (button) { r.processed = true; if (mb === 0x101) { enter('Tilt'); break } if (mb === 0) { enter('Idle'); break } }
        if (ev.type === 'move') { r.processed = true; this.spinSimplified(this.normalize(ev.pos), this.normalize(this.base)); this.base = ev.pos }
        break
      case 'Pan':
        if (button) { r.processed = true; if (mb === 0x101) { enter('Tilt'); break } if (mb === 0) { enter('Idle'); break } }
        if (ev.type === 'move') { r.processed = true; this.panCamera(this.plane, this.normalize(ev.pos), this.normalize(this.base)); this.base = ev.pos }
        break
      case 'StickyPan':
        if (button) { r.processed = true; if (isRelease(1)) { this.b2 = false; enter('Idle'); break } }
        if (ev.type === 'move') { r.processed = true; this.panCamera(this.plane, this.normalize(ev.pos), this.normalize(this.base)); this.base = ev.pos }
        break
      case 'Tilt':
        if (button) {
          r.processed = true
          if (mb === 0x001) { enter('Pan'); break }
          if (mb === 0x100) { enter('Rotate'); break }
          if (mb === 0) { enter('Idle'); break }
        }
        if (ev.type === 'move') {
          r.processed = true
          const dx = this.normalize(ev.pos)[0] - this.normalize(this.base)[0]
          this.doRotate(dx * -2, [0.5, 0.5])
          this.base = ev.pos
        }
        break
      case 'AwaitingRelease':
        if (button) { r.processed = true; if (mb === 0) { enter('Idle'); break } roll() }
        if (ev.type === 'move') r.processed = true
        break
      case 'Interact':
        if (button) { r.processed = false; if (mb === 0) { enter('Idle'); break } }
        break
    }
    if (!r.propagated && !r.processed) return this.baseEvent(ev)
    return r.processed
  }

  // ── Maya-Gesture (MayaGestureNavigationStyle.cpp) ─────────────────────────
  private mayaGesture(ev: NavEvent): boolean {
    if (!this.animating && this.viewing) this.setViewing(false)
    const m = this.maya
    const button = ev.type === 'press' || ev.type === 'release', press = ev.type === 'press'
    const posn = this.normalize(ev.pos), prev = this.last
    if (button || ev.type === 'move') this.last = posn
    const curmode = this.mode
    const count = () => +this.b1 + +this.b2 + +this.b3
    if (count() >= 2) m.complex = true
    if (count() === 0) { m.complex = false; m.consumed = [] }
    this.syncModifierKeys(ev)
    if (button) this.syncButtons(ev)
    if (count() >= 2) m.complex = true
    if (button || ev.type === 'move') m.broken ||= Math.hypot(ev.pos[0] - m.downPos[0], ev.pos[1] - m.downPos[1]) >= DRAG_DISTANCE
    let processed = false, propagated = false
    const replay = () => { for (const e of m.consumed) this.baseEvent(e); m.consumed = [] }

    if (ev.type === 'key' && (ev.key === 'h' || ev.key === 'H')) {
      processed = true
      if (!ev.down) { this.setupPanningPlane(); this.lookAtPoint(ev.pos) }
      return processed
    }
    switch (curmode) {
      case 'SELECTION':
      case 'IDLE':
      case 'INTERACT': {
        if (ev.type === 'key') {
          if (['s', 'S', 'Home', 'ArrowLeft', 'ArrowUp', 'ArrowRight', 'ArrowDown'].includes(ev.key ?? '')) { processed = this.baseEvent(ev); propagated = true }
          else if (ev.key === 'PageUp' && ev.down) { this.doZoomSteps(120, posn); processed = true }
          else if (ev.key === 'PageDown' && ev.down) { this.doZoomSteps(-120, posn); processed = true }
          if (processed) return processed
        }
        if (button && (ev.button === 1 || ev.button === 2)) {
          if (press) {
            if (m.complex && m.broken) { /* a two-button drag goes on */ }
            else { m.downPos = ev.pos; m.broken = false; this.setupPanningPlane(); m.consumed.push(ev); processed = true }
          } else {
            if (ev.button === 2 && !m.complex) { processed = true; this.host.popup(ev.pos) }
            if (!processed) { replay(); processed = this.baseEvent(ev); propagated = true }
          }
        }
        if (button && ev.button === 3) {
          if (press && this.alt) this.setViewingMode('PANNING')
          else if (press) { this.setupPanningPlane(); this.lookAtPoint(ev.pos) }
          processed = true
        }
        if (ev.type === 'move') {
          if (m.broken && (this.b1 || this.b2) && m.consumed.length > 0) {
            if (this.b1 && this.shift && !this.b2 && !this.b3 && this.tryStartBoxSelection(m.downPos, ev, this.ctrl)) { m.consumed = []; processed = true }
            else if ((this.b1 && this.alt) || (this.b2 && this.alt)) {
              m.consumed = []
              this.saveCursorPosition(ev.pos)
              this.setViewingMode(this.b1 ? 'DRAGGING' : 'ZOOMING')
              processed = true
            } else { replay(); processed = this.baseEvent(ev); propagated = true }
          }
          if (m.consumed.length > 0) processed = true
        }
        break
      }
      case 'DRAGGING':
      case 'ZOOMING':
      case 'PANNING': {
        if (button) {
          if (this.b1 || this.b2) {
            // setViewingMode runs either way (re-shows the rotation-centre marker at the just-
            // updated centre even when both buttons were already down): only which centring
            // call precedes it differs.
            if (this.b1 && this.b2) this.setRotationCenter(this.parts()?.tgt.clone() ?? new THREE.Vector3())
            else this.saveCursorPosition(ev.pos)
            this.setViewingMode(this.b1 ? 'DRAGGING' : 'PANNING')
            processed = true
          } else { this.setViewingMode('IDLE'); processed = true }
        }
        if (ev.type === 'move' && m.broken) {
          if (curmode === 'ZOOMING') { this.zoomByCursor(posn, prev); processed = true }
          else if (curmode === 'PANNING') { this.panCamera(this.plane, posn, prev); processed = true }
          else if (curmode === 'DRAGGING') {
            if (this.b1 && this.b2) this.doRotate((posn[0] - prev[0]) * -2, [0.5, 0.5])
            else this.spinSimplified(posn, prev)
            processed = true
          }
        }
        break
      }
      case 'SPINNING':
        if (!processed && (button || ev.type === 'key')) this.setViewingMode('SELECTION')
        break
    }
    if (!processed && !propagated) processed = this.baseEvent(ev)
    return processed
  }

  // ── Siemens NX (SiemensNXNavigationStyle.cpp, a state machine) ────────────
  private siemensNX(ev: NavEvent): boolean {
    if (!this.animating && this.viewing) this.setViewing(false)
    this.syncModifierKeys(ev)
    const r = { processed: false }
    if (ev.type === 'key') r.processed = this.processKeyboardEvent(ev)
    const button = ev.type === 'press' || ev.type === 'release'
    if (button) this.syncButtons(ev)
    const isPress = (b: number) => ev.type === 'press' && ev.button === b
    const isRelease = (b: number) => ev.type === 'release' && ev.button === b
    const keyPress = (k: string) => ev.type === 'key' && ev.down && ev.key === k
    const keyRelease = (k: string) => ev.type === 'key' && !ev.down && ev.key === k
    const none = !this.b1 && !this.b2 && !this.b3
    const enter = (st: string) => {
      this.state = st
      if (st === 'Idle') this.setViewingMode('IDLE')
      else if (st === 'AwaitingMove') { this.setViewingMode('DRAGGING'); this.base = ev.pos; this.since = ev.t }
      else if (st === 'Rotate') { this.saveCursorPosition(ev.pos); this.setViewingMode('DRAGGING'); this.base = ev.pos }
      else if (st === 'Pan') { this.setViewingMode('PANNING'); this.base = ev.pos; this.centerTime = ev.t; this.setupPanningPlane() }
      else if (st === 'Zoom') { this.setViewingMode('ZOOMING'); this.base = ev.pos }
    }
    if (!r.processed) {
      switch (this.state) {
        case 'Idle':
          if (isRelease(2) && this.mbstate() === 0) this.host.popup(ev.pos)
          if (isPress(3)) {
            if (ev.shift) { r.processed = true; enter('Pan') }
            // IdleState::react: ev.isDownButton(BUTTON3DOWN) is an exact match on mbstate, so a
            // fresh middle-button press only starts navigation when no other button is already down.
            else if (this.mbstate() === 0x010) { r.processed = true; enter('AwaitingMove') }
          }
          break
        case 'AwaitingMove':
          r.processed = button || ev.type === 'move'
          if (ev.type === 'move') enter('Rotate')
          else if (isPress(2) && this.b3) enter('Pan')
          else if (keyPress('Shift')) { r.processed = true; enter('Pan') }
          else if (isPress(1) && this.b3) enter('Zoom')
          else if (keyPress('Control')) { r.processed = true; enter('Zoom') }
          else if (isRelease(3) && none) {
            if (ev.t - this.since < DCI) { r.processed = true; this.lookAtPoint(ev.pos) }
            enter('Idle')
          }
          break
        case 'Rotate':
          if (ev.type === 'move') { this.addToLog(ev.pos, ev.t); this.spin(this.normalize(ev.pos)); r.processed = true }
          if (isPress(2) && this.b3) { r.processed = true; enter('Pan') }
          else if (keyPress('Shift')) { r.processed = true; enter('Pan') }
          else if (isPress(1) && this.b3) { r.processed = true; enter('Zoom') }
          else if (keyPress('Control')) { r.processed = true; enter('Zoom') }
          else if (isRelease(3) && none) { r.processed = true; enter('Idle') }
          break
        case 'Pan':
          if (ev.type === 'move') { r.processed = true; this.panCamera(this.plane, this.normalize(ev.pos), this.normalize(this.base)); this.base = ev.pos }
          if (isRelease(2) && this.b3) { r.processed = true; enter('Rotate') }
          else if (keyRelease('Shift') && this.b3) { r.processed = true; enter('Rotate') }
          else if (isRelease(3)) { r.processed = true; enter('Idle') }
          break
        case 'Zoom':
          if (ev.type === 'move') { r.processed = true; this.zoomByCursor(this.normalize(ev.pos), this.normalize(this.base)); this.base = ev.pos }
          if (isRelease(1) && this.b3) { r.processed = true; enter('Rotate') }
          else if (keyRelease('Control') && this.b3) { r.processed = true; enter('Rotate') }
          else if (isRelease(3)) { r.processed = true; enter('Idle') }
          break
      }
    }
    if (!r.processed) return this.baseEvent(ev)
    return r.processed
  }

  // ── orbit drag (the NaviCube's drag: beginOrbitDrag / updateOrbitDrag) ───
  private orbitDrag: { center: THREE.Vector3; minDistance: number; sensitivity: number } | null = null
  /** Orbit about the model's bounding sphere, kept at least minDistanceFactor radii away. */
  beginOrbitDrag(sphere: THREE.Sphere | null, minDistanceFactor: number, sensitivity: number) {
    this.stopAnimating()
    const p = this.parts()
    if (!p) return
    this.orbitDrag = { center: sphere ? sphere.center.clone() : p.tgt.clone(), minDistance: sphere ? Math.max(0, minDistanceFactor) * sphere.radius : 0, sensitivity: Math.max(0, sensitivity) }
    this.applyOrbitDragConstraints()
  }
  updateOrbitDrag(cur: V2, prev: V2) {
    const od = this.orbitDrag
    if (!od) return
    const scale = (q: V2): V2 => [0.5 + od.sensitivity * (q[0] - 0.5), 0.5 + od.sensitivity * (q[1] - 0.5)]
    const c = scale(cur), pr = scale(prev)
    const once = (a: V2, b: V2) => {
      const p = this.parts()
      if (!p) return
      this.proj.worldToScreen.copy(p.cam.quaternion).invert()
      this.proj.project(b)
      let r = this.proj.rotationTo(a)
      const s = this.prefs.sensitivity
      if (s > 1) { const [axis, ang] = axisAngle(r); r = rot(axis, ang * s) }
      this.reorient(r.invert(), od.center)
    }
    if (this.proj.orbit === 2) { const mid: V2 = [pr[0], c[1]]; once(c, mid); once(mid, pr) } else once(c, pr)
    this.applyOrbitDragConstraints()
    this.hasDragged = true
  }
  endOrbitDrag() { this.orbitDrag = null }
  /** applyOrbitDragCameraConstraints: no closer than minDistance, focused at the centre's depth. */
  private applyOrbitDragConstraints() {
    const p = this.parts(), od = this.orbitDrag
    if (!p || !od) return
    const d = viewDir(p.cam.quaternion)
    let depth = od.center.clone().sub(p.cam.position).dot(d)
    if (od.minDistance > 0 && depth < od.minDistance) { p.cam.position.addScaledVector(d, -(od.minDistance - depth)); depth = od.minDistance }
    if (depth > 0) p.tgt.copy(p.cam.position).addScaledVector(d, depth)
    this.host.changed()
  }

  /** Switching styles starts the new one idle (NavigationStyle::operator=). */
  setStyle(s: NavStyleId) {
    if (s === this.style) return
    this.style = s
    this.state = 'Idle'
    this.postponed = []
    this.box = null
    this.host.band(null)
    this.b1 = this.b2 = this.b3 = false
    this.interact = false
    this.setViewingMode('IDLE')
  }
  setOrbit(o: OrbitStyle) { this.proj.orbit = o }
  get viewerMode() { return this.mode }
}

// ── the DOM side: pointer, wheel and key events into Coin's ────────────────
/** Turns the canvas's DOM events into NavEvents. Events go on to the canvas (the
 *  dragger, three-cad-viewer's hover info) only when the navigation leaves them. */
export function bindNavigation(nav: Navigation, el: HTMLElement, isCanvas: (t: EventTarget | null) => boolean,
  canvas: () => HTMLCanvasElement | null, draggerHot: () => boolean): () => void {
  let mask = 0 // DOM buttons held: 1 left, 2 right, 4 middle
  let macRight = false // a Mac's Ctrl+click, held: the left button acts as the right
  let over = false
  let lastWheel = 0
  const coinButton = (domBit: number) => (domBit === 1 ? 1 : domBit === 2 ? 2 : 3) as 1 | 2 | 3
  const mods = (e: MouseEvent | KeyboardEvent) => ({ ctrl: isMac ? e.metaKey : e.ctrlKey, shift: e.shiftKey, alt: e.altKey })
  const posOf = (e: MouseEvent): V2 => {
    const c = canvas()
    if (!c) return [0, 0]
    const r = c.getBoundingClientRect()
    return [e.clientX - r.left, r.height - 1 - (e.clientY - r.top)]
  }
  const t = (e: Event) => e.timeStamp / 1000
  /** Browsers fold a second button into pointermove: diff the held buttons, then move. */
  const pointer = (e: PointerEvent) => {
    let buttons = e.buttons
    if (isMac && e.type === 'pointerdown' && e.button === 0 && e.ctrlKey && !e.metaKey && !(mask & 1)) macRight = true
    if (macRight) { buttons = buttons & 1 ? (buttons & ~1) | 2 : buttons & ~1; if (!(e.buttons & 1)) macRight = false }
    const changed = mask ^ buttons, out: NavEvent[] = []
    for (const bit of [1, 2, 4]) {
      if (changed & bit) out.push({ type: buttons & bit ? 'press' : 'release', button: coinButton(bit), pos: posOf(e), t: t(e), ...mods(e) })
    }
    mask = buttons
    if (e.type === 'pointermove' && !changed) out.push({ type: 'move', pos: posOf(e), t: t(e), ...mods(e) })
    return out
  }
  const onPointer = (e: PointerEvent) => {
    const onCanvas = isCanvas(e.target)
    if (e.type === 'pointerdown' && !onCanvas) return
    if (e.type !== 'pointerdown' && !mask && !onCanvas && !nav.interact) return
    over = onCanvas || mask !== 0
    // A press on a dragger handle: the whole drag is the dragger's (isDraggerUnderCursor).
    if (e.type === 'pointerdown' && !mask && e.button === 0 && draggerHot()) nav.interact = true
    if (nav.interact) {
      mask = e.buttons
      if (!mask) nav.interact = false
      return
    }
    for (const ev of pointer(e)) nav.processEvent(ev)
    if (e.type === 'pointerdown') { try { canvas()?.setPointerCapture(e.pointerId) } catch { /* gone */ } }
    // Hover moves reach the canvas (the dragger's highlight, the viewer's hover info); nothing else does.
    if (!(e.type === 'pointermove' && !mask)) e.stopPropagation()
  }
  const onWheel = (e: WheelEvent) => {
    if (!isCanvas(e.target)) return
    e.preventDefault()
    e.stopPropagation()
    const wd = (e as WheelEvent & { wheelDeltaY?: number }).wheelDeltaY
    // A touchpad (Qt's precise scroll): fine pixel steps, not 120 a notch.
    const precise = wd ? wd === -3 * e.deltaY : e.deltaMode === 0 && (e.deltaX !== 0 || !Number.isInteger(e.deltaY))
    const begin = e.timeStamp - lastWheel > 200
    lastWheel = e.timeStamp
    const pos = posOf(e), m = mods(e)
    if (precise && e.ctrlKey) { nav.pinch(pos, e.deltaY * 0.01); return } // a pinch arrives as Ctrl+wheel
    // isUnwantedHorizontalScroll: suppressed unless it's a precise touchpad AND TouchpadScrollPans
    // is on (so a horizontal-dominant touchpad swipe is also filtered when the pref is off).
    if ((!precise || !nav.touchpadScrollPans()) && Math.abs(e.deltaX) > Math.abs(e.deltaY)) return
    // Qt's angleDelta: 120 a notch, positive away from the user.
    const delta = wd && Math.abs(wd) % 120 === 0 ? -Math.sign(e.deltaY) * Math.abs(wd)
      : e.deltaMode === 1 ? -e.deltaY * 40 : e.deltaMode === 2 ? -e.deltaY * 800
      : Math.abs(e.deltaY) < 50 ? -Math.sign(e.deltaY) * 120 : -e.deltaY * 1.2
    nav.wheel(pos, delta, precise ? [-e.deltaX, e.deltaY] : null, m.shift, m.ctrl, begin)
  }
  const onMenu = (e: MouseEvent) => { if (isCanvas(e.target)) { e.preventDefault(); e.stopPropagation() } }
  const onKey = (e: KeyboardEvent) => {
    const el2 = e.target as HTMLElement | null
    if (!over || el2?.closest?.('input, textarea, select, [contenteditable="true"]')) return
    const key = e.key === 'Meta' ? (isMac ? 'Control' : 'Meta') : e.key === 'Control' ? (isMac ? 'Meta' : 'Control') : e.key
    nav.processEvent({ type: 'key', key, down: e.type === 'keydown', pos: [0, 0], t: t(e), ...mods(e) })
  }
  const onLeave = () => { over = false }
  el.addEventListener('pointerdown', onPointer, true)
  el.addEventListener('pointermove', onPointer, true)
  el.addEventListener('pointerup', onPointer, true)
  el.addEventListener('pointercancel', onPointer, true)
  el.addEventListener('wheel', onWheel, { capture: true, passive: false })
  el.addEventListener('contextmenu', onMenu, true)
  el.addEventListener('pointerleave', onLeave)
  addEventListener('keydown', onKey)
  addEventListener('keyup', onKey)
  return () => {
    el.removeEventListener('pointerdown', onPointer, true)
    el.removeEventListener('pointermove', onPointer, true)
    el.removeEventListener('pointerup', onPointer, true)
    el.removeEventListener('pointercancel', onPointer, true)
    el.removeEventListener('wheel', onWheel, true)
    el.removeEventListener('contextmenu', onMenu, true)
    el.removeEventListener('pointerleave', onLeave)
    removeEventListener('keydown', onKey)
    removeEventListener('keyup', onKey)
  }
}

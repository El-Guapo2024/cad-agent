import * as THREE from 'three'
import { Display, Viewer, decodeInstancedFormat } from 'three-cad-viewer'
import { TransformControls } from 'three/addons/controls/TransformControls.js'
import { Line2 } from 'three/addons/lines/Line2.js'
import { LineGeometry } from 'three/addons/lines/LineGeometry.js'
import { LineMaterial } from 'three/addons/lines/LineMaterial.js'
import { LineSegments2 } from 'three/addons/lines/LineSegments2.js'
import { LineSegmentsGeometry } from 'three/addons/lines/LineSegmentsGeometry.js'
import { ViewportGizmo } from 'three-viewport-gizmo'
import { Navigation, bindNavigation, type NavPrefs, type V2 } from './nav'
import { AxisCross } from './axiscross'
import { toNumber, userString } from './quantity'
import { placementMatrix } from './placement'

/** The placement indicator's axis label: white text (labelFontSize 9) on the axis colour. */
function labelSprite(text: string, color: string): THREE.Sprite {
  const c = document.createElement('canvas'); c.width = 32; c.height = 32
  const x = c.getContext('2d')!
  x.fillStyle = color; x.beginPath(); x.roundRect(4, 6, 24, 20, 3); x.fill()
  x.fillStyle = '#fff'; x.font = 'bold 18px sans-serif'; x.textAlign = 'center'; x.textBaseline = 'middle'; x.fillText(text, 16, 17)
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(c), depthTest: false }))
  sp.scale.setScalar(0.4)
  return sp
}

import { toUnicodeSuperscript } from './superscript'
import type { Scene, Vec3 } from './api'
import { getState, saved, setState, subscribe, viewOf, type Clip, type Corner, type CubeOffset, type CubePlace, type CubePos, type DrawStyle, type HomeView, type NaviCubePrefs, type NavStyle, type ViewProps } from './store'
import { VIEW } from './theme'
import { gradientMesh, type BackgroundPrefs } from './background'
import { LightRig, type LightPrefs } from './lights'

const RENDER = {
  // The viewer's own two lights are off: LightRig is FreeCAD's (Preferences > Light Sources).
  ambientIntensity: 0, directIntensity: 0, metalness: 0.3, roughness: 0.65,
  edgeColor: VIEW.line, defaultOpacity: 0.5, normalLen: 0,
}

// FreeCAD's default orbit style is Rounded Arcball (OrbitStyle 4 in
// View3DSettings.cpp); three-cad-viewer's Holroyd trackball is that kind of arcball.
const ORBIT = { control: 'trackball', holroyd: true }
// What each draw style shows of a body: [faces, edges].
/** What each Part display mode shows (ViewProviderPartExt::attach): [faces, edges, vertices]. */
const DISPLAY: Record<ViewProps['displayMode'], [number, number, boolean]> = {
  'Flat Lines': [1, 1, true], Shaded: [1, 0, false], Wireframe: [0, 1, true], Points: [0, 0, true],
}
/** FreeCAD Light's BoundingBoxColor. SelectionStyle=BoundBox and Std_SelBoundingBox both draw
 *  the ordinary highlight/selection colours (SoFCSelectionRoot::_renderPrivate) — there is no
 *  separate "bbox selection colour". */
const BBOX_COLOR = 0x495057
/** NaviCube.cpp's OffsetX/OffsetY (we don't expose them as a separate preference, so this is
 *  our own fixed stand-in for that 0-default); its size, corner and colours are preferences. */
const CUBE_OFFSET = 10

/** NaviCubeImplementation::handleResize (NaviCube.cpp:887-898): OffsetX/Y plus a margin of
 *  0.55 cube-radii on every side (so the cube can't clip the viewport edge) — clamped to half
 *  the view, like FreeCAD. The extra +12 at the bottom is this port's own menu-button row. */
function cubeArea(w: number, h: number, size: number) {
  const x = Math.min(CUBE_OFFSET + size * 0.55, w / 2)
  const top = Math.min(CUBE_OFFSET + size * 0.55, h / 2)
  const bottom = Math.min(CUBE_OFFSET + 12 + size * 0.55, h / 2)
  return { left: x, right: x, top, bottom, areaW: Math.max(1, w - 2 * x), areaH: Math.max(1, h - top - bottom) }
}
/** NaviCubeImplementation::mousePressed/populateRenderParams (NaviCube.cpp:461-466): relPos
 *  (here CubePos) scaled into the padded area gives the cube's on-screen centre. three-
 *  viewport-gizmo only has 9 fixed placements, not a continuous position, so we pick the
 *  nearest one (by thirds of the view) and set the offset from ITS anchor edge(s) to land the
 *  cube exactly on that centre — placement and offset keep in step as CubePos moves, so the
 *  cube reads as continuous even though it's technically re-anchored at each third crossed. */
export function cubeLayout(pos: CubePos, w: number, h: number, size: number): { placement: CubePlace; offset: CubeOffset } {
  const a = cubeArea(w, h, size)
  const cx = a.left + pos.x * a.areaW, cy = a.top + pos.y * a.areaH
  const hz = cx < w / 3 ? 'left' : cx > (2 * w) / 3 ? 'right' : 'center'
  const vz = cy < h / 3 ? 'top' : cy > (2 * h) / 3 ? 'bottom' : 'center'
  return {
    placement: `${vz}-${hz}` as CubePlace,
    offset: {
      left: hz === 'right' ? 0 : hz === 'center' ? cx - w / 2 : cx - size / 2,
      right: hz === 'right' ? w - cx - size / 2 : 0,
      top: vz === 'bottom' ? 0 : vz === 'center' ? cy - h / 2 : cy - size / 2,
      bottom: vz === 'bottom' ? h - cy - size / 2 : 0,
    },
  }
}
/** SoNaviCube::buildAxisSection (Gui/Inventor/SoNaviCube.cpp:765-812): a small 3-axis tripod at
 *  one corner of the cube, colour AxisXColor/YColor/ZColor (axiscross.ts's AXIS_COLORS), shown
 *  when ShowCS is on (View3DSettings.cpp ShowCS, default true). Coordinates are the exact ones
 *  FreeCAD uses for its own ±1 cube; three-viewport-gizmo's cube faces also sit at exactly ±1
 *  (its face meshes are positioned at `±1` on their axis), so they carry over unscaled. Added as
 *  a child of the gizmo itself (a plain Object3D), so it turns with the cube for free — the
 *  library sets the gizmo's own quaternion to the camera's inverse every update, exactly like
 *  SoNaviCube's rootTransform.
 *  Each segment is a line plus a point at each of its 2 vertices (SoIndexedLineSet + SoPointSet
 *  sharing one vertex list), both sized `borderWidth * 2` (updateAxes, lines 1124-1126;
 *  BorderWidth default 1.1 -> ~2.2px) — a plain THREE.Line/LineBasicMaterial can't render a
 *  solid width in WebGL (clamped to 1px hairlines), so this uses three's fat-line materials
 *  (sized in screen pixels) for the line, and a round point sprite at the same pixel size
 *  standing in for SoPointSet's cap at each end. */
const SHOWCS_WIDTH_PX = 2.2 // BorderWidth (NaviCube.cpp:148, default 1.1) * 2.0F
let showCSDotTex: THREE.Texture | null = null
/** The round point FreeCAD's SoPointSet draws at each ShowCS segment end (no canvas texture in
 *  Coin itself — GL_POINTS with pointSize there; a filled-circle sprite is the closest match a
 *  THREE.Points/PointsMaterial pairing can render at a literal pixel size). */
function dotTexture() {
  if (showCSDotTex) return showCSDotTex
  const cv = document.createElement('canvas')
  cv.width = cv.height = 16
  const ctx = cv.getContext('2d')!
  ctx.fillStyle = '#fff'
  ctx.beginPath(); ctx.arc(8, 8, 7, 0, Math.PI * 2); ctx.fill()
  showCSDotTex = new THREE.CanvasTexture(cv)
  return showCSDotTex
}
function buildShowCS(resW: number, resH: number) {
  const grp = new THREE.Group(), a = -1.1, b = -1.05, c = 0.5, ac = getState().axisColors
  const segs: [THREE.Vector3, THREE.Vector3, string, 'x' | 'y' | 'z'][] = [
    [new THREE.Vector3(b, a, a), new THREE.Vector3(c, a, a), ac.x, 'x'],
    [new THREE.Vector3(a, b, a), new THREE.Vector3(a, c, a), ac.y, 'y'],
    [new THREE.Vector3(a, a, b), new THREE.Vector3(a, a, c), ac.z, 'z'],
  ]
  for (const [p0, p1, color, axis] of segs) {
    // regress3-viewer.md #3: buildAxisSection (SoNaviCube.cpp:765-812) adds no SoDepthBuffer
    // override, so the tripod uses Coin's default depth test against the cube's own faces —
    // unlike the corner cross, which explicitly disables it (View3DInventorViewer.cpp:607-609).
    const lineMat = new LineMaterial({ color, transparent: true, linewidth: SHOWCS_WIDTH_PX })
    lineMat.resolution.set(resW, resH)
    const line = new Line2(new LineGeometry().setFromPoints([p0, p1]), lineMat)
    line.renderOrder = 1000
    line.userData.axis = axis
    grp.add(line)
    const caps = new THREE.Points(new THREE.BufferGeometry().setFromPoints([p0, p1]),
      new THREE.PointsMaterial({ color, map: dotTexture(), size: SHOWCS_WIDTH_PX, sizeAttenuation: false, transparent: true }))
    caps.renderOrder = 1000
    caps.userData.axis = axis
    grp.add(caps)
  }
  return grp
}
const STYLE: Record<DrawStyle, [number, number]> = {
  asis: [1, 1], points: [0, 0], wireframe: [0, 1], hiddenline: [1, 1], noshading: [1, 1], shaded: [1, 0], flatlines: [1, 1],
}

type Applied = {
  selected: string[] | null; preselected: string | null; hidden: string[] | null; style: DrawStyle | null; cube: boolean
  view: Record<string, Partial<ViewProps>> | null; selBoxes: boolean | null; axes: boolean | null; showFPS: boolean | null
  clip: Clip | null | undefined; preSub: string | null | undefined; subSel: string[] | null; nav: NavStyle | null; navPrefs: NavPrefs | null
  corner: Corner | null; naviCube: NaviCubePrefs | null; background: BackgroundPrefs | null
}
const UNAPPLIED = { selected: null, preselected: null, hidden: null, style: null, view: null, selBoxes: null, axes: null, showFPS: null, clip: undefined, preSub: undefined, subSel: null, nav: null, navPrefs: null, corner: null, naviCube: null, background: null }

const R2 = Math.SQRT1_2
/** FreeCAD's standard view rotations (src/Gui/Camera.cpp; x, y, z, w). */
const ROTATION: Record<ViewDir, [number, number, number, number]> = {
  top: [0, 0, 0, 1], bottom: [1, 0, 0, 0], front: [R2, 0, 0, R2], rear: [0, R2, R2, 0],
  right: [0.5, 0.5, 0.5, 0.5], left: [-0.5, 0.5, 0.5, -0.5], iso: [0.424708, 0.17592, 0.339851, 0.820473],
  dimetric: [0.567952, 0.103751, 0.146726, 0.803205], trimetric: [0.446015, 0.119509, 0.229575, 0.856787],
}
const TRIMETRIC = ROTATION.trimetric
const HOME_DIR: Record<HomeView, ViewDir> = {
  Isometric: 'iso', Dimetric: 'dimetric', Trimetric: 'trimetric', Top: 'top', Front: 'front', Left: 'left', Right: 'right', Rear: 'rear', Bottom: 'bottom',
}

export type ViewDir = 'iso' | 'dimetric' | 'trimetric' | 'front' | 'top' | 'right' | 'rear' | 'bottom' | 'left'
export type Transform = {
  body: string
  /** Where the dragger sits on the body (its transform origin), in world space. */
  pivot: THREE.Matrix4
  snap: { mm: number; deg: number }
  /** As a drag starts, moves and ends, and after setDragger: the dragger's world placement,
   *  and the body's world move since the dragger was attached. */
  onChange(dragger: THREE.Matrix4, delta: THREE.Matrix4, phase: TransformPhase): void
}
export type TransformPhase = 'start' | 'motion' | 'finish' | 'set'
/** SceneInspector.cpp's DlgInspector, ported for three.js: one row per Coin node there, one
 *  row per THREE.Object3D here (CadView.sceneTree). */
export type SceneNode = { type: string; name: string; children: SceneNode[] }
type Handlers = {
  /** `sub` is FreeCAD's sub-element name under the pointer: Face3, Edge7, Vertex2. */
  hover(body: string | null, point: number[] | null, sub: string | null): void
  pick(body: string | null, additive: boolean, sub: string | null, point?: number[] | null): void
  open(body: string): void
  info(text: string): void
  /** The visible width and height of the view, in mm. */
  size?(w: number, h: number): void
  /** The right-click menu, at a client position, over a part (or nothing). */
  menu?(x: number, y: number, body: string | null): void
  /** Std_ClarifySelection: everything under the cursor, to choose from. */
  clarify?(x: number, y: number, picks: { body: string; sub: string | null }[]): void
  /** A box selection finished: the parts, and whether Ctrl added them. */
  box?(names: string[], additive: boolean): void
  /** Everything under the cursor at a pick, for the Selection view's picked object list. */
  picked?(picks: { body: string; sub: string | null }[]): void
}

/** Drawn, so pickable: three-cad-viewer hides faces and edges through material.visible. */
const shown = (o: THREE.Object3D | null) => {
  const m = (o as any)?.material
  if (m && !Array.isArray(m) && m.visible === false) return false
  for (; o; o = o.parent) if (!o.visible) return false
  return true
}

// ── Measure/Gui's ViewProviderMeasure* look (drawMeasure) ───────────────────────────────────
/** Measure/App/Preferences.cpp: defaultLineColor 0x3CF00000 (60,240,0 — the low byte is unused;
 *  ViewProviderMeasureBase::onChanged (lines 294-316) only ever reads .r/.g/.b off these),
 *  defaultArrowHeight/Radius 18/6 px (ViewProviderMeasureAngle's cones, via SoScreenSpaceScale
 *  "1 unit = 1 pixel"); Gui::ViewParams MarkerSize 9 px (the CROSS marker at a raw point). */
const MEASURE_COLOR = 0x3cf000
const MARKER_PX = 9, ARROW_HEIGHT_PX = 18, ARROW_RADIUS_PX = 6
/** positionAnno's default, un-dragged dimension-line gap ("0.1 * getViewScale()") stands in as
 *  a constant pixel offset — we have no draggable label to read a real one back from. Exported:
 *  ViewProviderMeasureAngle.cpp:644's default arc radius is the exact same "0.1*getViewScale()"
 *  expression, so measure.tsx reuses this one constant instead of a second magic number. */
export const DIM_GAP_PX = 20
/** ViewProviderMeasure::getTextPosition (ViewProviderMeasureBase.cpp ~752-766): the generic
 *  view providers' (Length/Position/Diameter/Radius/Area/Geometric Center) own label offset —
 *  a literal SbVec2s(30,30), screen pixels up-and-right of the anchor (Coin viewport space has
 *  +y up) — unlike DIM_GAP_PX above, this one has no approximation involved. */
const LABEL_OFFSET_PX = 30
const CONE_UP = new THREE.Vector3(0, 1, 0)

/** ViewProviderMeasureDistance::getTextDirection (lines 285-307): a direction perpendicular to
 *  the measured line, chosen from whichever cardinal axis isn't parallel to it, flipped to lean
 *  toward +Z — used to offset the dimension line and extension lines off the raw points. */
function measureTextDir(dir: THREE.Vector3) {
  const z = new THREE.Vector3(0, 0, 1)
  let perp = dir.clone().cross(new THREE.Vector3(1, 0, 0))
  if (perp.lengthSq() < 1e-9) perp = dir.clone().cross(new THREE.Vector3(0, 1, 0))
  if (perp.lengthSq() < 1e-9) perp = dir.clone().cross(z)
  perp.normalize()
  return perp.dot(z) < 0 ? perp.negate() : perp
}
let measureCrossTex: THREE.Texture | null = null
/** Gui::Inventor::MarkerBitmaps CROSS, the SoMarkerSet FreeCAD draws at each raw measured point
 *  (ViewProviderMeasureDistance.cpp:385-391) — a small screen-aligned "+", built once and tinted
 *  per use via PointsMaterial.color. */
function crossTexture() {
  if (measureCrossTex) return measureCrossTex
  const cv = document.createElement('canvas')
  cv.width = cv.height = 16
  const ctx = cv.getContext('2d')!
  ctx.strokeStyle = '#fff'
  ctx.lineWidth = 2.5
  ctx.beginPath(); ctx.moveTo(8, 1); ctx.lineTo(8, 15); ctx.moveTo(1, 8); ctx.lineTo(15, 8); ctx.stroke()
  measureCrossTex = new THREE.CanvasTexture(cv)
  return measureCrossTex
}

/**
 * three-cad-viewer, driven the way FreeCAD's 3D view behaves: hovering
 * preselects, a click selects (Cmd/Ctrl adds), a click on empty space clears,
 * a double-click opens the part's edit task, and a navigation cube sits top
 * right. The viewer's own tree and toolbar are off; the React panels replace them.
 */
export class CadView {
  readonly viewer: any
  private display: any
  private gizmo: ViewportGizmo | null = null
  private cross = new AxisCross()
  private rendered = false
  private meshes = new Map<string, THREE.Mesh[]>() // each part's faces (front and back meshes)
  private edges = new Map<string, THREE.Object3D[]>() // and its edge lines
  private verts = new Map<string, THREE.Points[]>() // and its vertices
  private overlays: THREE.Object3D[] = []
  /** three-cad-viewer numbers faces, then edges, then vertices in one run; FreeCAD
   *  numbers each from 1. These are the offsets per part. */
  private bases = new Map<string, { Face: number; Edge: number; Vertex: number }>()
  private ray = new THREE.Raycaster()
  private applied: Applied = { ...UNAPPLIED, cube: true }
  private boxHelpers: THREE.Object3D[] = []
  /** The live (unsaved) measurement: its points (plus, for Angle, the vertex its spokes start
   *  from) and the drawn group. Survives a scene reload (index() only clears measureObj) so
   *  sync() can rebuild it once the new scene is ready, same pattern as before this file tracked
   *  saved measurements too. */
  private measureGeom: { pts: number[][]; vertex?: number[] } | null = null
  private measureObj: THREE.Object3D | null = null
  /** regress3-viewer.md #1/#6: the label anchor drawMeasure actually computed for the live
   *  measurement (getTextPosition's far end, or Distance's offset dimension-line midpoint) —
   *  null for Angle, or when nothing is drawn, and the caller then keeps its own anchor. */
  private measureLabelAnchor: THREE.Vector3 | null = null
  /** regress3-viewer.md #2: every saved ("kept") measurement gets its own permanent group
   *  (ViewProviderMeasureBase.cpp gives each Measure object its own scene node, ctor lines
   *  81-243) instead of sharing the one slot above. */
  private keptGeoms: { pts: number[][]; vertex?: number[] }[] = []
  private keptObjs: THREE.Object3D[] = []
  private working: { pos: THREE.Vector3; up: THREE.Vector3; target: THREE.Vector3; zoom: number } | null = null
  private hoverFrame = 0
  readonly nav: Navigation
  /** While set, a left click hands the point under it here instead of selecting. */
  pointPicker: ((body: string | null, point: THREE.Vector3 | null, sub: string | null) => void) | null = null
  private markerGroup: THREE.Group | null = null
  private lastClient: { x: number; y: number } | null = null
  private marker: THREE.Mesh | null = null
  /** Std_ViewLoadImage: the one session-only image plane, if loaded (never saved). */
  private imagePlane: THREE.Mesh | null = null
  private bandEl: HTMLDivElement | null = null
  private pending = false
  private hooked = false
  private tcs: TransformControls[] = []
  private tf: { t: Transform; group: THREE.Object3D; groupStart: THREE.Matrix4; proxy: THREE.Object3D; proxyStart: THREE.Matrix4 } | null = null
  private dragLabels: { sprite: THREE.Sprite; canvas: HTMLCanvasElement; ctx: CanvasRenderingContext2D }[] = []
  private cleanup: (() => void)[] = []
  /** NaviCubeDraggableCmd: a drag on the cube moves it instead of orbiting. */
  private cubeDraggable = false
  /** NaviRotateToNearest (default on): a click snaps to the nearest roll of the face. */
  private naviRotateToNearest = true
  /** mouseDown, for the opacity fade: true for the whole life of a cube press. */
  private cubeActive = false
  /** The whole cube's last-applied opacity factor (mouseMoved's hovering ? 1 : InactiveOpacity). */
  private cubeFade = 1
  /** SoNaviCube's ShowCS tripod, a child of the gizmo so it turns with the cube for free. */
  private cubeAxes: THREE.Group | null = null
  /** AxisXColor/Y/Z live on the library's own AxesHelper (Std_AxisCross) and on cubeAxes'
   *  materials too; cached (and, for the former, keyed to the helper instance, since the
   *  library rebuilds it with its own default colours on every show()) so re-applying them
   *  every frame in hookRender is normally a no-op. */
  private bigAxesRef: unknown = null
  private bigAxesColorKey = ''
  private showCSColorKey = ''
  /** View3DInventorViewer's fpsCounter/fpsUpdateTimer: the lower-left label and its 4 Hz
   *  (250 ms) refresh. fpsDrawTime/fpsFrameTime (addFrametime) accumulate every on-screen
   *  frame regardless of ShowFPS, same as FreeCAD's paintEvent. */
  private fpsEl: HTMLDivElement | null = null
  private fpsTimer: ReturnType<typeof setInterval> | null = null
  private fpsDrawTime = 0
  private fpsFrameTime = 0
  private fpsLastEnd = 0
  private fpsColor = ''

  constructor(private host: HTMLElement, private on: Handlers) {
    host.replaceChildren()            // a remount (hot reload) must not stack a second viewer
    this.display = new Display(host, {
      cadWidth: host.clientWidth || 800, height: host.clientHeight || 600,
      treeWidth: 0, glass: true, tools: false, theme: 'light', pinning: false,
    } as any)
    this.viewer = new Viewer(this.display, { up: 'Z', ...ORBIT } as any, () => {})
    const ro = new ResizeObserver(() => { this.fit(); this.scaleMarker(); this.scalePlacementIndicators() })
    ro.observe(host)
    const add = <K extends keyof HTMLElementEventMap>(k: K, f: (e: HTMLElementEventMap[K]) => void) => {
      host.addEventListener(k, f)
      this.cleanup.push(() => host.removeEventListener(k, f))
    }
    // FreeCAD's navigation drives the camera; three-cad-viewer's controls get no input.
    this.nav = new Navigation({
      camera: () => this.cameraParts()?.cam ?? null,
      target: () => this.cameraParts()?.controls.target ?? null,
      size: () => { const c = this.viewer.renderer?.domElement as HTMLCanvasElement | undefined; return [c?.clientWidth || 1, c?.clientHeight || 1] },
      changed: () => this.cameraChanged(),
      scenePoint: (pos) => this.hitAt(this.client(pos))?.point ?? null,
      sceneBox: () => this.box(),
      draggerUnderCursor: () => this.tcs.some((tc) => (tc as any).axis),
      scene: (ev) => this.sceneEvent(ev),
      clearSelection: () => this.on.pick(null, false, null),
      // openPopupMenu: the last-preselected object, not a fresh pick at the click point.
      popup: (pos) => { const c = this.client(pos); this.on.menu?.(c.x, c.y, getState().preselected ?? this.hitAt(c)?.body ?? null) },
      band: (a, b) => this.drawBand(a, b),
      boxSelect: (a, b, additive) => this.on.box?.(this.bodiesIn(this.client(a), this.client(b)), additive),
      clarify: (pos) => { const c = this.client(pos); this.on.clarify?.(c.x, c.y, this.picksAt(c)) },
      marker: (p) => this.showMarker(p),
      cursor: (css) => { const c = this.viewer.renderer?.domElement as HTMLElement | undefined; if (c) c.style.cursor = css },
      viewAll: () => this.fitAll(),
      orient: (name) => this.orient(name === 'iso' ? ROTATION.iso : name === 'top' ? ROTATION.top : TRIMETRIC),
      prefs: () => ({ ...getState().navPrefs, animate: getState().animate, disableTouchTilt: getState().disableTouchTilt }),
    })
    const track = (e: PointerEvent) => { if (this.onCanvas(e)) this.lastClient = { x: e.clientX, y: e.clientY } }
    host.addEventListener('pointermove', track, true)
    this.cleanup.push(() => host.removeEventListener('pointermove', track, true))
    // NaviCube.cpp's mouseMoved hovering test: at the window level, since the cube's own
    // (library-drawn) area may not be the element under the pointer.
    const cubeFade = (e: PointerEvent) => this.updateCubeFade(e.clientX, e.clientY)
    addEventListener('pointermove', cubeFade)
    this.cleanup.push(() => removeEventListener('pointermove', cubeFade))
    this.cleanup.push(bindNavigation(this.nav, host, (t) => t === this.viewer.renderer?.domElement,
      () => this.viewer.renderer?.domElement ?? null, () => this.tcs.some((tc) => (tc as any).axis)))
    add('dblclick', (e) => {
      const h = this.onCanvas(e) ? this.hitAt({ x: e.clientX, y: e.clientY }) : null
      if (h) this.on.open(h.body)
    })
    // The viewer describes the edge or face under the mouse in a status line of
    // its own; FreeCAD puts that in the status bar, so move it there.
    const line = host.querySelector('.tcv_status_line')
    if (line) {
      const mo = new MutationObserver(() => this.on.info(line.textContent?.trim() ?? ''))
      mo.observe(line, { childList: true, characterData: true, subtree: true })
      this.cleanup.push(() => mo.disconnect())
    }
    this.cleanup.push(() => ro.disconnect(), subscribe(() => this.sync()))
  }

  dispose() {
    this.stopTransform(true)
    this.cleanup.forEach((f) => f())
    this.gizmo?.dispose()
    this.cross.dispose()
    this.setImagePlane(null)
    if (this.fpsTimer) clearInterval(this.fpsTimer)
    try { this.viewer.dispose() } catch { /* already gone */ }
    this.host.replaceChildren()
  }

  show(sc: Scene, keepView: boolean) {
    const cam = keepView && this.rendered ? this.viewer.getCameraLocationSettings() : null
    const tf = this.tf?.t
    this.stopTransform(false)
    if (this.rendered) this.viewer.clear()
    this.viewer.render(decodeInstancedFormat(sc.viewer as any), RENDER, { up: 'Z', ...ORBIT, ortho: getState().ortho, ...(cam ?? {}) })
    this.rendered = true
    this.applyBackground(getState().background)
    this.applyLights(getState().lights)
    this.index(sc)
    // The viewer settles its own size a frame or two after render; fit after it.
    this.fit()
    requestAnimationFrame(() => requestAnimationFrame(() => this.fit()))
    setTimeout(() => this.fit(), 300)
    // A new view looks along the default camera orientation (viewDefaultOrientation), fitted.
    if (!cam) {
      this.viewer.presetCamera('iso')
      this.jumpTo(new THREE.Quaternion(...ROTATION[HOME_DIR[getState().homeView]]))
      // View3DInventorPy::setDefaultCameraHeight (Std_New): NewDocumentCameraScale places the
      // camera before there's anything to fit; fitAll below overrides it as soon as a body
      // exists (it no-ops on an empty scene), so this only matters for a genuinely empty doc.
      this.defaultCameraHeight(getState().newDocCameraScale)
      this.fitAll(undefined, true)
    }
    this.hookRender()
    if (getState().cube) this.attachGizmo()
    this.sync()
    if (tf) this.startTransform(tf)       // back on the rebuilt body, from where it now is
    // Orbiting and zooming with the mouse change what the view spans too.
    this.lockControls()
    this.emitSize()
    // Std_ViewLoadImage: this.viewer.clear() above drops anything added straight to the scene,
    // same as the transform proxy (stopTransform/startTransform); re-add so an edit elsewhere
    // doesn't silently lose the image. Still session-only: nothing here is ever saved.
    if (this.imagePlane) this.viewer.scene?.add(this.imagePlane)
  }

  /** three-cad-viewer's orbit controls: kept for their target, never for input. */
  private lockControls() {
    const cc = this.viewer.controls?.controls
    if (!cc || cc === this.watched) return
    Object.defineProperty(cc, 'enabled', { get: () => false, set: () => {}, configurable: true })
    cc.addEventListener('change', () => this.emitSize())
    this.watched = cc
  }

  /** The navigation moved the camera: sync the controls and the cube, then draw once a frame. */
  private cameraChanged() {
    if (this.pending) return
    this.pending = true
    requestAnimationFrame(() => {
      this.pending = false
      const cc = this.viewer.controls?.controls
      if (cc) {
        // Drop any drag the controls saw (a dragger's), so update() only syncs.
        cc._holroydStart?.copy?.(cc._holroydEnd); cc._movePrev?.copy?.(cc._moveCurr)
        cc._zoomStart?.copy?.(cc._zoomEnd); cc._panStart?.copy?.(cc._panEnd)
        cc.update()
      }
      this.gizmo?.update()
      this.scaleMarker()
      this.scalePlacementIndicators()
      // The camera the person sees, for the agent (`cad gui state`): once it settles.
      clearTimeout(this.camTimer)
      this.camTimer = window.setTimeout(() => { const c = this.getCamera(); if (c && c !== getState().cameraNode) setState({ cameraNode: c }) }, 400)
      this.placeLabels()
      // Clipping's moveCallback: the custom plane keeps facing along the view.
      const clip = getState().clip
      if (clip?.view?.on && clip.view.adjust) this.applyClip(clip)
      this.redraw()
      this.emitSize()
    })
  }

  /** Coin's pixel position (from the bottom left of the canvas) as a client position. */
  private client(pos: V2) {
    const c = this.viewer.renderer?.domElement as HTMLCanvasElement | undefined
    const r = c?.getBoundingClientRect() ?? { left: 0, top: 0, height: 0 }
    return { x: r.left + pos[0], y: r.top + r.height - 1 - pos[1] }
  }

  /** What the scene graph does with an event the navigation passes on: hovering
   *  preselects, a left release selects (SoFCUnifiedSelection), Ctrl toggles. */
  private sceneEvent(ev: { type: string; button?: number; pos: V2; ctrl: boolean }): boolean {
    if (this.nav.interact) return ev.type !== 'move'
    if (ev.type === 'move') {
      cancelAnimationFrame(this.hoverFrame)
      const c = this.client(ev.pos)
      this.hoverFrame = requestAnimationFrame(() => {
        const h = this.hitAt(c)
        this.on.hover(h?.body ?? null, h ? h.point.toArray() : null, h?.sub ?? null)
      })
      return false
    }
    if (ev.type === 'release' && ev.button === 1 && this.pointPicker) {
      // Manual alignment takes clicks as picked points (ManualAlignment::probePickedCallback).
      const h = this.hitAt(this.client(ev.pos))
      this.pointPicker(h?.body ?? null, h?.point ?? null, h?.sub ?? null)
      return true
    }
    if (ev.type === 'release' && ev.button === 1) {
      if (getState().pickList) this.on.picked?.(this.picksAt(this.client(ev.pos), 1))
      const h = this.hitAt(this.client(ev.pos))
      if (h) { this.on.pick(h.body, ev.ctrl, h.sub, h.point.toArray()); return true }
      return ev.ctrl
    }
    return false
  }

  /** View3DInventorViewer::showRotationCenter (View3DInventorViewer.cpp:2257-2318): a sphere
   *  (SoSphere, radius 1) in an SoShapeScale (scaleFactor = RotationCenterSize, i.e. its radius
   *  is that many pixels regardless of zoom — scaleMarker ports that via worldPerPixel), emissive
   *  colour RotationCenterColor with its alpha as transparency. nav.ts's Navigation already
   *  ports when it shows/hides (the DRAGGING-state enter/exit in setViewingMode, NavigationStyle.
   *  cpp:2167-2228) and the ShowRotationCenter on/off check; only the look was still hardcoded. */
  private showMarker(p: THREE.Vector3 | null) {
    if (this.marker) { this.viewer.scene?.remove(this.marker); this.marker = null }
    if (p && this.viewer.scene) {
      const rc = getState().rotationCenter
      const m = new THREE.Mesh(new THREE.SphereGeometry(1, 16, 12), new THREE.MeshBasicMaterial({ color: rc.color, transparent: true, opacity: rc.alpha, depthTest: false }))
      m.position.copy(p)
      m.renderOrder = 999
      m.userData.cadHelper = true
      this.viewer.scene.add(m)
      this.marker = m
      this.scaleMarker()
    }
    this.redraw()
  }
  private scaleMarker() {
    const cam = this.viewer.camera?.getCamera?.(), c = this.viewer.renderer?.domElement as HTMLCanvasElement | undefined
    if (this.marker && cam && c?.clientHeight) this.marker.scale.setScalar(getState().rotationCenter.size * this.worldPerPixel(cam, c.clientHeight))
  }

  /** The rubber band of a drag box selection. */
  private drawBand(a: V2 | null, b?: V2) {
    if (!a || !b) { this.bandEl?.remove(); this.bandEl = null; return }
    if (!this.bandEl) { this.bandEl = document.createElement('div'); this.bandEl.className = 'box-band nav-band'; this.host.appendChild(this.bandEl) }
    const p = this.client(a), q = this.client(b), r = this.host.getBoundingClientRect()
    Object.assign(this.bandEl.style, { display: 'block', left: `${Math.min(p.x, q.x) - r.left}px`, top: `${Math.min(p.y, q.y) - r.top}px`,
      width: `${Math.abs(q.x - p.x)}px`, height: `${Math.abs(q.y - p.y)}px` })
  }

  private box() {
    const box = new THREE.Box3(), hidden = getState().hidden
    for (const [name, list] of this.meshes) if (!hidden.includes(name)) list.forEach((m) => box.expandByObject(m))
    return box.isEmpty() ? null : box
  }

  private lightRig: LightRig | null = null
  private lightsApplied: LightPrefs | null = null
  /** View3DSettings' light sources on a (new) scene; they follow the camera at every render. */
  private applyLights(p: LightPrefs) {
    const scene = this.viewer.scene as THREE.Scene | undefined
    if (!scene) return
    if (this.lightRig && this.lightRig.head.parent !== scene) { this.lightRig.dispose(); this.lightRig = null }
    if (!this.lightRig) {
      const rig = this.lightRig = new LightRig(scene, p)
      scene.onBeforeRender = (_r, _s, camera) => rig.follow(camera)
    } else this.lightRig.apply(p)
    this.lightsApplied = p
  }
  private bgMesh: THREE.Mesh | null = null
  /** View3DSettings' background: a simple colour clears the view; a gradient is
   *  SoFCBackgroundGradient's mesh, drawn first in the scene. */
  private applyBackground(b: BackgroundPrefs) {
    if (this.bgMesh) {
      this.bgMesh.removeFromParent()
      this.bgMesh.geometry.dispose()
      ;(this.bgMesh.material as THREE.Material).dispose()
      this.bgMesh = null
    }
    try { this.viewer.renderer.setClearColor(b.color, 1) } catch { /* keep the viewer's own */ }
    if (b.mode !== 'simple' && this.viewer.scene) { this.bgMesh = gradientMesh(b); this.viewer.scene.add(this.bgMesh) }
  }

  /** FreeCAD's Transform (Std_TransformManip) with its SoTransformDragger: arrows and rings
   *  together on a pivot; the body follows the pivot. */
  startTransform(t: Transform) {
    this.stopTransform(true)
    const b = getState().scene?.bodies.find((x) => x.name === t.body)
    const g = b ? (this.viewer.nestedGroup?.groups?.[b.path] as THREE.Object3D | undefined) : undefined
    const cam = this.viewer.camera?.getCamera?.(), canvas = this.viewer.renderer?.domElement
    if (!g || !cam || !canvas) return
    g.updateWorldMatrix(true, false)
    const proxy = new THREE.Object3D()
    proxy.userData.cadHelper = true
    t.pivot.decompose(proxy.position, proxy.quaternion, proxy.scale)
    this.viewer.scene.add(proxy)
    proxy.updateMatrixWorld(true)
    const make = (mode: 'translate' | 'rotate') => {
      const tc = new TransformControls(cam, canvas)
      tc.setSpace('local')
      tc.setMode(mode)
      // ViewProviderDragger::setAxisColors: FreeCAD's muted axis colours (the live Preferences
      // > Display > 3D View values), not the library's own red/green/blue.
      const ac = getState().axisColors
      tc.setColors(ac.x, ac.y, ac.z, 0xffff00)
      if (mode === 'rotate') tc.setSize(1.15)
      tc.attach(proxy)
      tc.addEventListener('change', () => { this.placeDragLabels(); this.redraw() })
      tc.addEventListener('objectChange', () => { this.followDragger(); this.reportTransform('motion') })
      tc.addEventListener('dragging-changed', (e: any) => {
        for (const o of this.tcs) if (o !== tc) o.enabled = !e.value
        this.reportTransform(e.value ? 'start' : 'finish')
      })
      this.viewer.scene.add(tc.getHelper())
      return tc
    }
    this.tcs = [make('translate'), make('rotate')]
    this.tf = { t, group: g, groupStart: g.matrix.clone(), proxy, proxyStart: proxy.matrixWorld.clone() }
    this.setTransformSnap(t.snap)
  }

  /** The body's move so far: the pivot's move since it was attached. */
  transformDelta() {
    const f = this.tf
    if (!f) return new THREE.Matrix4()
    f.proxy.updateMatrixWorld(true)
    return f.proxy.matrixWorld.clone().multiply(f.proxyStart.clone().invert())
  }
  private followDragger() {
    const f = this.tf
    if (!f) return
    const parent = f.group.parent?.matrixWorld ?? new THREE.Matrix4()
    parent.clone().invert().multiply(this.transformDelta()).multiply(parent).multiply(f.groupStart)
      .decompose(f.group.position, f.group.quaternion, f.group.scale)
    f.group.updateMatrixWorld(true)
    this.redraw()
  }
  private reportTransform(phase: TransformPhase) {
    const f = this.tf
    if (f) f.t.onChange(f.proxy.matrixWorld.clone(), this.transformDelta(), phase)
  }
  /** Put the dragger at a world placement: the body goes along, or with `moveObject` false
   *  only the pivot moves (a new transform origin). */
  setDragger(m: THREE.Matrix4, moveObject: boolean) {
    const f = this.tf
    if (!f) return
    const delta = this.transformDelta()
    m.decompose(f.proxy.position, f.proxy.quaternion, f.proxy.scale)
    f.proxy.updateMatrixWorld(true)
    if (moveObject) this.followDragger()
    else f.proxyStart = delta.invert().multiply(f.proxy.matrixWorld)
    this.reportTransform('set')
    this.redraw()
  }
  getDragger() { return this.tf ? this.tf.proxy.matrixWorld.clone() : null }
  setTransformSnap(snap: Transform['snap']) {
    for (const tc of this.tcs) {
      tc.setTranslationSnap(snap.mm > 0 ? snap.mm : null)
      tc.setRotationSnap(snap.deg > 0 ? THREE.MathUtils.degToRad(snap.deg) : null)
    }
    if (this.tf) this.tf.t.snap = snap
    this.redraw()
  }
  /** TaskTransform::setSelectionMode: while picking a reference/target/custom CS, the
   *  dragger itself must be unpickable so the click reaches the geometry under it. */
  setDraggerPickable(on: boolean) {
    for (const tc of this.tcs) tc.enabled = on
  }

  /** TaskTransform::updateDraggerLabels: U/V/W by default, or the aligned coordinate
   *  system's X/Y/Z / X′/Y′/Z′, next to the dragger's arrows and rings (SoTransformDragger's
   *  xAxisLabel/yAxisLabel/zAxisLabel). Pass null to remove them. */
  setDraggerLabels(labels: [string, string, string] | null) {
    for (const l of this.dragLabels) { this.viewer.scene?.remove(l.sprite); (l.sprite.material as THREE.SpriteMaterial).map?.dispose(); l.sprite.material.dispose() }
    this.dragLabels = []
    if (!labels || !this.tf || !this.viewer.scene) return
    this.dragLabels = labels.map((text) => {
      const canvas = document.createElement('canvas')
      canvas.width = canvas.height = 64
      const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(canvas), depthTest: false, transparent: true, toneMapped: false }))
      sprite.userData.cadHelper = true
      sprite.renderOrder = 999
      this.viewer.scene.add(sprite)
      const l = { sprite, canvas, ctx: canvas.getContext('2d')! }
      this.paintDragLabel(l, text)
      return l
    })
    this.placeDragLabels()
    this.redraw()
  }
  private paintDragLabel(l: { canvas: HTMLCanvasElement; ctx: CanvasRenderingContext2D; sprite: THREE.Sprite }, text: string) {
    l.ctx.clearRect(0, 0, 64, 64)
    l.ctx.fillStyle = '#202020'
    l.ctx.font = '44px sans-serif'
    l.ctx.textAlign = 'center'
    l.ctx.textBaseline = 'middle'
    l.ctx.fillText(text, 32, 34)
    ;(l.sprite.material.map as THREE.CanvasTexture).needsUpdate = true
  }
  /** Keeps the labels beside the dragger's tips, at a constant on-screen offset and size. */
  private placeDragLabels() {
    const f = this.tf, cam = this.viewer.camera?.getCamera?.(), c = this.viewer.renderer?.domElement as HTMLCanvasElement | undefined
    if (!f || !cam || !c || !this.dragLabels.length) return
    const perPx = this.worldPerPixel(cam, c.clientHeight || 1)
    f.proxy.updateMatrixWorld(true)
    const origin = f.proxy.getWorldPosition(new THREE.Vector3()), q = f.proxy.getWorldQuaternion(new THREE.Quaternion())
    ;([[1, 0, 0], [0, 1, 0], [0, 0, 1]] as [number, number, number][]).forEach((axis, i) => {
      const dir = new THREE.Vector3(...axis).applyQuaternion(q)
      this.dragLabels[i].sprite.position.copy(origin).addScaledVector(dir, 80 * perPx)
      this.dragLabels[i].sprite.scale.setScalar(18 * perPx)
    })
  }

  /** Remove the dragger; `revert` puts the body back where it started. */
  stopTransform(revert: boolean) {
    const tcs = this.tcs, f = this.tf
    this.tcs = []
    this.tf = null
    this.setDraggerLabels(null)
    for (const tc of tcs) { tc.detach(); this.viewer.scene?.remove(tc.getHelper()); tc.dispose() }
    if (f) {
      if (revert) { f.groupStart.decompose(f.group.position, f.group.quaternion, f.group.scale); f.group.updateMatrixWorld(true) }
      this.viewer.scene?.remove(f.proxy)
    }
    this.redraw()
  }

  /** Turn to an orientation about the focal point at once (setCameraOrientation, no animation). */
  private jumpTo(q: THREE.Quaternion) {
    const p = this.cameraParts()
    if (!p) return
    const fd = p.cam.position.distanceTo(p.controls.target)
    p.cam.quaternion.copy(q)
    p.cam.up.set(0, 1, 0).applyQuaternion(q)
    p.cam.position.copy(p.controls.target).addScaledVector(new THREE.Vector3(0, 0, 1).applyQuaternion(q), fd)
    p.cam.updateMatrixWorld()
    this.cameraChanged()
  }

  /** View3DInventorPy::setDefaultCameraHeight: `scale` is the diameter (mm) of the sphere,
   *  centred at the origin, that should fill the screen — not a fit of real geometry (there's
   *  none to fit yet), just where Std_New leaves the camera before anything is modelled. */
  private defaultCameraHeight(scale: number) {
    const p = this.cameraParts()
    if (!p || scale <= 1e-7) return
    const c = p.cam as any
    let f: number
    if (c.isOrthographicCamera) {
      f = scale
      c.zoom = (c.top - c.bottom) / scale
      c.updateProjectionMatrix()
    } else {
      // heightAngle is in radians in FreeCAD; three's fov is degrees.
      f = (0.5 * scale) / Math.sin(THREE.MathUtils.degToRad(c.fov) / 2)
    }
    p.controls.target.set(0, 0, 0)
    p.cam.position.copy(p.controls.target).addScaledVector(new THREE.Vector3(0, 0, 1).applyQuaternion(p.cam.quaternion), f)
    p.cam.updateMatrixWorld()
    this.cameraChanged()
  }

  /** Std_ViewHome (View3DInventorViewer::viewHome): turn to the default orientation while
   *  moving to the middle of the model, then fit all; already there, just fit. */
  home(d: ViewDir) {
    const p = this.cameraParts()
    if (!p) return
    const q = new THREE.Quaternion(...ROTATION[d])
    if (Math.abs(q.dot(p.cam.quaternion)) > 1 - 1e-6) return this.fitAll()
    const box = this.box(), t = p.controls.target.clone()
    this.nav.startAnimation(q, t, box ? box.getCenter(new THREE.Vector3()).sub(t) : new THREE.Vector3(), () => this.fitAll())
  }

  /** Coloured dots at picked points (ManualAlignment::pickedPointsSubGraph). */
  showPoints(points: { p: THREE.Vector3; color: number }[]) {
    if (this.markerGroup) this.viewer.scene?.remove(this.markerGroup)
    this.markerGroup = null
    if (points.length && this.viewer.scene) {
      const g = new THREE.Group()
      for (const { p, color } of points) {
        const dot = new THREE.Points(new THREE.BufferGeometry().setFromPoints([p]), new THREE.PointsMaterial({ color, size: 10, sizeAttenuation: false, depthTest: false }))
        dot.renderOrder = 999
        g.add(dot)
      }
      g.userData.cadHelper = true
      this.viewer.scene.add(g)
      this.markerGroup = g
    }
    this.redraw()
  }

  private previewed: { name: string; pos: THREE.Vector3; quat: THREE.Quaternion; scale: THREE.Vector3 } | null = null
  /** The Placement dialog's live preview (PlacementHandler::applyPlacement before OK): the
   *  body drawn moved by `delta` (world), or back where it was with null. */
  previewPlacement(name: string, delta: THREE.Matrix4 | null) {
    const b = getState().scene?.bodies.find((x) => x.name === name)
    const g = b ? (this.viewer.nestedGroup?.groups?.[b.path] as THREE.Object3D | undefined) : undefined
    if (this.previewed && (!g || this.previewed.name !== name || !delta)) {
      const pg = this.viewer.nestedGroup?.groups?.[getState().scene?.bodies.find((x) => x.name === this.previewed!.name)?.path ?? ''] as THREE.Object3D | undefined
      if (pg) { pg.position.copy(this.previewed.pos); pg.quaternion.copy(this.previewed.quat); pg.scale.copy(this.previewed.scale); pg.updateMatrixWorld(true) }
      this.previewed = null
    }
    if (g && delta) {
      if (!this.previewed) this.previewed = { name, pos: g.position.clone(), quat: g.quaternion.clone(), scale: g.scale.clone() }
      const base = new THREE.Matrix4().compose(this.previewed.pos, this.previewed.quat, this.previewed.scale)
      const parent = g.parent?.matrixWorld ?? new THREE.Matrix4()
      // world delta, in the parent's frame: local' = P⁻¹ · delta · P · local
      const local = parent.clone().invert().multiply(delta).multiply(parent).multiply(base)
      local.decompose(g.position, g.quaternion, g.scale)
      g.updateMatrixWorld(true)
    }
    this.redraw()
  }

  /** The world direction that points down the screen (DemoMode's view axis). */
  worldDown() {
    const p = this.cameraParts()
    return new THREE.Vector3(0, -1, 0).applyQuaternion(p ? p.cam.quaternion : new THREE.Quaternion())
  }
  /** SpinningAnimation about a world axis, `velocity` rad/s (DemoMode::startAnimation). */
  spinAbout(worldAxis: THREE.Vector3, velocity: number) {
    const p = this.cameraParts()
    if (p) this.nav.spinAnimation(worldAxis.clone().applyQuaternion(p.cam.quaternion.clone().invert()), velocity)
  }
  /** DemoMode's angle slider: tilt about the screen's x axis by `deg`, around the focal point. */
  tilt(deg: number) {
    const p = this.cameraParts()
    if (!p) return
    const fd = p.cam.position.distanceTo(p.controls.target)
    p.cam.quaternion.multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(-1, 0, 0), THREE.MathUtils.degToRad(deg)))
    p.cam.up.set(0, 1, 0).applyQuaternion(p.cam.quaternion)
    p.cam.position.copy(p.controls.target).addScaledVector(new THREE.Vector3(0, 0, 1).applyQuaternion(p.cam.quaternion), fd)
    this.cameraChanged()
  }

  /** Std_ClarifySelection (G, G) at the pointer. */
  clarifyAtCursor() {
    if (this.lastClient) this.on.clarify?.(this.lastClient.x, this.lastClient.y, this.picksAt(this.lastClient))
  }

  /** Std_ViewFront etc.: FreeCAD only turns the camera (View3DPy.cpp setCameraOrientation);
   *  the target and the zoom stay. */
  viewDir(d: ViewDir) {
    this.orient(ROTATION[d])
  }

  /** Std_ViewFitAll / Std_ViewFitSelection (View3DInventorViewer::viewAll): keep the
   *  direction and frame the bounding sphere; with animations on, 10 steps of 20 ms. */
  fitAll(names?: string[], instant = false) {
    const p = this.cameraParts()
    if (!p) return
    const box = new THREE.Box3()
    const hidden = getState().hidden
    for (const [name, list] of this.meshes) {
      if ((names && names.length && !names.includes(name)) || hidden.includes(name)) continue
      list.forEach((m) => box.expandByObject(m))
    }
    if (box.isEmpty()) return
    this.nav.stopAnimating()
    const sphere = box.getBoundingSphere(new THREE.Sphere()), cam = p.cam, controls = p.controls
    const dir = cam.position.clone().sub(controls.target).normalize()
    const ortho = (cam as THREE.OrthographicCamera).isOrthographicCamera
    const c = cam as any
    // viewAll: a perspective camera's heightAngle always snaps back to 45° first.
    if (!ortho) { c.fov = 45; c.updateProjectionMatrix() }
    // SoCamera::viewBoundingBox: the sphere fills the shorter side.
    const aspect = ortho ? (c.right - c.left) / (c.top - c.bottom) : c.aspect
    const height = (2 * sphere.radius) / Math.min(1, aspect)
    const zoom1 = ortho ? (c.top - c.bottom) / height : cam.zoom
    const dist1 = ortho ? Math.max(sphere.radius * 6, cam.position.distanceTo(controls.target))
      : sphere.radius / Math.sin(THREE.MathUtils.degToRad(c.fov) / 2) / Math.min(1, aspect)
    const t0 = controls.target.clone(), d0 = cam.position.distanceTo(t0), z0 = cam.zoom
    const put = (k: number) => {
      controls.target.copy(t0).lerp(sphere.center, k)
      cam.position.copy(controls.target).addScaledVector(dir, d0 + (dist1 - d0) * k)
      if (ortho) { cam.zoom = z0 + (zoom1 - z0) * k; cam.updateProjectionMatrix() }
      this.cameraChanged()
    }
    if (instant || !getState().animate || document.visibilityState !== 'visible') return put(1)
    let i = 0
    const step = () => { i++; put(i / 10); if (i < 10) setTimeout(step, 20) }
    step()
  }

  setOrtho(flag: boolean) {
    const tf = this.tf?.t
    this.stopTransform(true)
    try { this.viewer.setOrtho(flag) } catch { return }
    if (getState().cube) this.attachGizmo()
    if (tf) this.startTransform(tf)
    this.redraw()
  }

  redraw() {
    try { this.viewer.update(true, false) } catch { /* not rendered yet */ }
  }

  fit() {
    const canvas = this.viewer.renderer?.domElement as HTMLElement | undefined
    if (!this.rendered || !canvas || !this.host.clientWidth) return
    // The viewer draws a frame around the canvas; give the canvas what's left.
    const b = this.host.getBoundingClientRect(), c = canvas.getBoundingClientRect()
    const first = this.host.firstElementChild as HTMLElement | null
    const r = first ? first.getBoundingClientRect() : b
    const margin = r.left - b.left
    const w = 2 * margin + (r.width - c.width), h = (c.top - b.top) + (r.bottom - c.bottom) + margin
    this.viewer.resizeCadView(Math.max(200, Math.floor(this.host.clientWidth - w)), 0,
      Math.max(200, Math.floor(this.host.clientHeight - h)), true)
    this.gizmo?.update()
    // NaviCubeImplementation::handleResize runs every render: keep the cube at the same
    // CubePos as the container is resized, not a stale pixel margin from the old size.
    if (this.gizmo) this.applyCubeLayout(getState().cubePos)
    // The ShowCS tripod's fat-line materials need the canvas size kept current too, or their
    // linewidth (a screen-pixel size) drifts off 2.2px after a resize.
    if (this.cubeAxes) {
      const w = canvas.clientWidth || 1, h = canvas.clientHeight || 1
      for (const o of this.cubeAxes.children) (o as any).material?.resolution?.set(w, h)
    }
    this.emitSize()
  }

  // ── camera commands ────────────────────────────────────────────────────────
  private cameraParts() {
    const cam = this.viewer.camera?.getCamera?.() as (THREE.OrthographicCamera | THREE.PerspectiveCamera) | undefined
    const controls = this.viewer.controls?.controls
    return cam && controls ? { cam, controls } : null
  }

  private settle() {
    this.cameraParts()?.controls.update()
    this.gizmo?.update()
    this.redraw()
    this.emitSize()
  }

  private sizeFrame = 0
  private watched: unknown = null
  /** Tell the status bar how much of the model the view spans, in mm. */
  private emitSize() {
    cancelAnimationFrame(this.sizeFrame)
    this.sizeFrame = requestAnimationFrame(() => {
      const p = this.cameraParts()
      if (!p || !this.on.size) return
      const c: any = p.cam
      if (c.isOrthographicCamera) this.on.size((c.right - c.left) / c.zoom, (c.top - c.bottom) / c.zoom)
      else {
        const h = 2 * p.cam.position.distanceTo(p.controls.target) * Math.tan(THREE.MathUtils.degToRad(c.fov) / 2)
        this.on.size(h * c.aspect, h)
      }
    })
  }

  /** Turn to an orientation and move the focal point to `target`, animated as FreeCAD's
   *  NavigationAnimation (AnimationDuration, InOutCubic). */
  private animateTo(q1: THREE.Quaternion, target: THREE.Vector3) {
    const p = this.cameraParts()
    if (p) this.nav.startAnimation(q1, p.controls.target.clone(), target.clone().sub(p.controls.target))
  }

  private applyNav(nav: NavStyle, prefs: NavPrefs) {
    this.nav.setStyle(nav)
    this.nav.setOrbit(prefs.orbit)
  }

  /** Std_BoxElementSelection (Shift+E), as applyBoxSelection with selectElement: a part
   *  wholly inside is taken whole; else its vertices inside, and its faces and edges
   *  that cross the box (dragged right to left) or whose middle is in it (left to right). */
  boxElements(done: (refs: string[], whole: string[]) => void) {
    this.rubberBand((a, b) => {
      const cam = this.viewer.camera?.getCamera?.()
      if (!cam) return done([], [])
      const x0 = Math.min(a.x, b.x), x1 = Math.max(a.x, b.x), y0 = Math.min(a.y, b.y), y1 = Math.max(a.y, b.y)
      const crossing = a.x > b.x, hidden = getState().hidden, out: string[] = [], whole: string[] = []
      const toScreen = this.screenOf(cam), v = new THREE.Vector3()
      const inside = (p: { x: number; y: number }) => p.x >= x0 && p.x <= x1 && p.y >= y0 && p.y <= y1
      /** Polygon2d::Intersect for a box and a set of segments, plus CENTER mode's test. `tri`
       *  (a face: pts/segs run in groups of 3, one triangle at a time) replaces the "is the
       *  drag box inside the aggregate bounding box" fallback with a per-triangle test, so a
       *  box sitting in a concave notch or an interior hole is correctly rejected. */
      const hits = (pts: { x: number; y: number }[], segs: [number, number][], tri?: boolean) => {
        const bb = { x0: Infinity, y0: Infinity, x1: -Infinity, y1: -Infinity }
        for (const p of pts) { bb.x0 = Math.min(bb.x0, p.x); bb.x1 = Math.max(bb.x1, p.x); bb.y0 = Math.min(bb.y0, p.y); bb.y1 = Math.max(bb.y1, p.y) }
        if (bb.x1 < x0 || bb.x0 > x1 || bb.y1 < y0 || bb.y0 > y1) return false
        if (!crossing && !inside({ x: (bb.x0 + bb.x1) / 2, y: (bb.y0 + bb.y1) / 2 })) return false
        if (pts.some(inside)) return true
        if (segs.some(([i, j]) => segBox(pts[i], pts[j], x0, y0, x1, y1))) return true
        if (!tri) return bb.x0 <= x0 && bb.x1 >= x1 && bb.y0 <= y0 && bb.y1 >= y1
        const qx = (x0 + x1) / 2, qy = (y0 + y1) / 2
        for (let k = 0; k + 2 < pts.length; k += 3) if (pointInTri(qx, qy, pts[k], pts[k + 1], pts[k + 2])) return true
        return false
      }
      for (const name of this.meshes.keys()) {
        if (hidden.includes(name) || getState().unselectable.includes(name)) continue
        const bbox = this.screenBox(name, toScreen)
        if (!bbox) continue
        if (bbox.x0 >= x0 && bbox.x1 <= x1 && bbox.y0 >= y0 && bbox.y1 <= y1) { whole.push(name); continue }
        if (bbox.x1 < x0 || bbox.x0 > x1 || bbox.y1 < y0 || bbox.y0 > y1) continue
        const base = this.bases.get(name), mesh = this.front(name)
        if (mesh) {
          mesh.updateWorldMatrix(true, false)
          const g = mesh.geometry, idx = g.index!, pos = g.attributes.position, comp = g.attributes.componentId
          const faces = new Map<number, { pts: { x: number; y: number }[]; segs: [number, number][] }>()
          for (let t = 0; t < idx.count; t += 3) {
            const id = comp.getX(idx.getX(t))
            let f = faces.get(id)
            if (!f) faces.set(id, (f = { pts: [], segs: [] }))
            const k = f.pts.length
            for (let j = 0; j < 3; j++) f.pts.push(toScreen(v.fromBufferAttribute(pos, idx.getX(t + j)).applyMatrix4(mesh.matrixWorld)))
            f.segs.push([k, k + 1], [k + 1, k + 2], [k + 2, k])
          }
          for (const [id, f] of faces) if (hits(f.pts, f.segs, true)) out.push(`${name}.Face${id - (base?.Face ?? 0)}`)
        }
        const line = (this.edges.get(name) ?? [])[0] as any
        if (line) {
          line.updateWorldMatrix(true, false)
          const g = line.geometry, ia = g.attributes.instanceStart, ib = g.attributes.instanceEnd, comp = g.attributes.componentId
          const edges = new Map<number, { pts: { x: number; y: number }[]; segs: [number, number][] }>()
          for (let i = 0; i < comp.count; i++) {
            const id = comp.getX(i)
            let e = edges.get(id)
            if (!e) edges.set(id, (e = { pts: [], segs: [] }))
            const k = e.pts.length
            e.pts.push(toScreen(v.fromBufferAttribute(ia, i).applyMatrix4(line.matrixWorld)), toScreen(v.fromBufferAttribute(ib, i).applyMatrix4(line.matrixWorld)))
            e.segs.push([k, k + 1])
          }
          for (const [id, e] of edges) if (hits(e.pts, e.segs)) out.push(`${name}.Edge${id - (base?.Edge ?? 0)}`)
        }
        const pts = (this.verts.get(name) ?? [])[0]
        if (pts) {
          pts.updateWorldMatrix(true, false)
          const comp = pts.geometry.attributes.componentId, pos = pts.geometry.attributes.position
          for (let i = 0; i < comp.count; i++) {
            if (inside(toScreen(v.fromBufferAttribute(pos, i).applyMatrix4(pts.matrixWorld)))) out.push(`${name}.Vertex${comp.getX(i) - (base?.Vertex ?? 0)}`)
          }
        }
      }
      done(out, whole)
    })
  }

  /** World point to client pixels, for the camera as it is now. */
  private screenOf(cam: THREE.Camera) {
    const c = this.viewer.renderer.domElement as HTMLCanvasElement, r = c.getBoundingClientRect()
    cam.updateMatrixWorld()
    return (p: THREE.Vector3) => { const q = p.clone().project(cam); return { x: r.left + ((q.x + 1) / 2) * r.width, y: r.top + ((1 - q.y) / 2) * r.height } }
  }
  /** A part's bounding box, projected: the 2D box around its eight corners. */
  private screenBox(name: string, toScreen: (p: THREE.Vector3) => { x: number; y: number }) {
    const box = new THREE.Box3()
    ;(this.meshes.get(name) ?? []).forEach((m) => box.expandByObject(m))
    if (box.isEmpty()) return null
    const out = { x0: Infinity, y0: Infinity, x1: -Infinity, y1: -Infinity }
    for (let i = 0; i < 8; i++) {
      const p = toScreen(new THREE.Vector3(i & 1 ? box.max.x : box.min.x, i & 2 ? box.max.y : box.min.y, i & 4 ? box.max.z : box.min.z))
      out.x0 = Math.min(out.x0, p.x); out.x1 = Math.max(out.x1, p.x); out.y0 = Math.min(out.y0, p.y); out.y1 = Math.max(out.y1, p.y)
    }
    return out
  }

  /** Look along a FreeCAD camera rotation (x, y, z, w; Camera.cpp), keeping the
   *  target and the distance. Coin and three.js cameras share their axes. */
  orient(q: [number, number, number, number]) {
    const p = this.cameraParts()
    if (!p) return
    this.animateTo(new THREE.Quaternion(...q), p.controls.target.clone())
  }

  /** Turn the view about a screen axis, in the camera's own frame as FreeCAD's
   *  NaviCube does: x tilts, y turns, z rolls. */
  turn(axis: 'x' | 'y' | 'z', deg: number) {
    const p = this.cameraParts()
    if (!p) return
    // Clicks during the animation add up (NaviCube's flatButtonTargetOrientation).
    const base = this.nav.animating && this.turnTarget ? this.turnTarget : p.cam.quaternion.clone()
    const local = new THREE.Vector3(+(axis === 'x'), +(axis === 'y'), +(axis === 'z'))
    this.turnTarget = base.clone().multiply(new THREE.Quaternion().setFromAxisAngle(local, THREE.MathUtils.degToRad(deg)))
    this.animateTo(this.turnTarget, p.controls.target.clone())
  }
  private turnTarget: THREE.Quaternion | null = null


  /** Std_ViewZoomIn / Out: one ZoomStep about the focal point (NavigationStyle::zoomIn). */
  zoomIn() { this.nav.zoomIn() }
  zoomOut() { this.nav.zoomOut() }

  storeView() {
    const p = this.cameraParts()
    if (p) this.working = { pos: p.cam.position.clone(), up: p.cam.up.clone(), target: p.controls.target.clone(), zoom: p.cam.zoom }
  }

  recallView() {
    const p = this.cameraParts(), w = this.working
    if (!p || !w) return
    p.cam.position.copy(w.pos)
    p.cam.up.copy(w.up)
    p.controls.target.copy(w.target)
    p.cam.zoom = w.zoom
    p.cam.updateProjectionMatrix()
    p.cam.lookAt(w.target)
    this.settle()
  }

  /** View3DInventorViewer's "GetCamera": the camera node as Coin writes it (SoWriteAction; floats
   *  are float32 at %.8g, the orientation axis and angle as SbRotation::getValue gives them). */
  getCamera(): string | null {
    const p = this.cameraParts()
    if (!p) return null
    const { cam, controls } = p
    const g = (n: number) => toNumber(Math.fround(n), 'Default', 8)
    const q = cam.quaternion, w = Math.fround(q.w)
    let axis = [0, 0, 1], angle = 0
    if (w >= -1 && w <= 1) {
      angle = Math.acos(w) * 2
      const scale = Math.sin(angle / 2)
      if (scale !== 0) axis = [q.x / scale, q.y / scale, q.z / scale]
      else angle = 0
    }
    const ortho = (cam as THREE.OrthographicCamera).isOrthographicCamera
    const o = cam as THREE.OrthographicCamera, pc = cam as THREE.PerspectiveCamera
    return ['#Inventor V2.1 ascii', '', '', `${ortho ? 'Orthographic' : 'Perspective'}Camera {`,
      '  viewportMapping ADJUST_CAMERA',
      `  position ${[cam.position.x, cam.position.y, cam.position.z].map(g).join(' ')}`,
      `  orientation ${axis.map(g).join(' ')}  ${g(angle)}`,
      `  nearDistance ${g(cam.near)}`,
      `  farDistance ${g(cam.far)}`,
      '  aspectRatio 1',
      `  focalDistance ${g(cam.position.distanceTo(controls.target))}`,
      ortho ? `  height ${g((o.top - o.bottom) / o.zoom)}` : `  heightAngle ${g(THREE.MathUtils.degToRad(pc.fov))}`,
      '', '}', ''].join('\n')
  }

  /** "SetCamera": take on a camera node's position, orientation, focal distance and height (or
   *  height angle). The caller switches the projection first (commands.ts applyCamera). */
  setCamera(text: string): boolean {
    const p = this.cameraParts()
    if (!p || !/\b(Orthographic|Perspective)Camera\b/.test(text)) return false
    const field = (name: string) => {
      const m = new RegExp(`\\b${name}\\s+([-+0-9.eE]+(?:\\s+[-+0-9.eE]+)*)`).exec(text)
      return m ? m[1].trim().split(/\s+/).map(Number) : null
    }
    const pos = field('position'), ori = field('orientation'), focal = field('focalDistance')?.[0]
    const height = field('height')?.[0], heightAngle = field('heightAngle')?.[0]
    const q = ori && ori.length >= 4 ? new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(ori[0], ori[1], ori[2]).normalize(), ori[3]) : p.cam.quaternion.clone()
    if (pos && pos.length >= 3) p.cam.position.set(pos[0], pos[1], pos[2])
    p.cam.up.set(0, 1, 0).applyQuaternion(q)
    const f = focal ?? p.cam.position.distanceTo(p.controls.target)
    p.controls.target.copy(p.cam.position).addScaledVector(new THREE.Vector3(0, 0, -1).applyQuaternion(q), f)
    p.cam.lookAt(p.controls.target)
    const o = p.cam as THREE.OrthographicCamera
    if (o.isOrthographicCamera && height) o.zoom = (o.top - o.bottom) / height
    if (!o.isOrthographicCamera && heightAngle) (p.cam as THREE.PerspectiveCamera).fov = THREE.MathUtils.radToDeg(heightAngle)
    p.cam.updateProjectionMatrix()
    this.settle()
    return true
  }

  /** Std_ViewScreenShot: the view as a PNG the browser saves. */
  /** View3DInventorViewer::savePicture: the view drawn at a size, on a background
   *  (Current, White, Black, Transparent), keeping the view's height; the gizmo left out. */
  renderImage(w: number, h: number, background: 'Current' | 'White' | 'Black' | 'Transparent', type: string): string {
    const r = this.viewer.renderer as THREE.WebGLRenderer, p = this.cameraParts()
    const canvas = r.domElement as HTMLCanvasElement
    if (!p) return canvas.toDataURL(type)
    const cam: any = p.cam, size = r.getSize(new THREE.Vector2()), ratio = r.getPixelRatio()
    const saved = { left: cam.left, right: cam.right, top: cam.top, bottom: cam.bottom, aspect: cam.aspect }
    const clear = r.getClearColor(new THREE.Color()), alpha = r.getClearAlpha()
    const gizmo = this.gizmo
    this.gizmo = null
    try {
      r.setPixelRatio(1)
      r.setSize(w, h, false)
      if (cam.isOrthographicCamera) { const half = (cam.top - cam.bottom) / 2, mid = (cam.left + cam.right) / 2; cam.left = mid - half * (w / h); cam.right = mid + half * (w / h) }
      else cam.aspect = w / h
      cam.updateProjectionMatrix()
      // "Current" keeps the view's background, a gradient included; the others replace it.
      const bg = background === 'White' ? 0xffffff : background === 'Black' ? 0x000000 : getState().background.color
      r.setClearColor(bg, background === 'Transparent' ? 0 : 1)
      if (this.bgMesh) this.bgMesh.visible = background === 'Current'
      r.clear(true, true, true) // three-cad-viewer draws with autoClear off
      r.render(this.viewer.scene, cam)
      return canvas.toDataURL(type, 0.95)
    } finally {
      Object.assign(cam, saved)
      cam.updateProjectionMatrix()
      r.setClearColor(clear, alpha)
      if (this.bgMesh) this.bgMesh.visible = true
      r.setPixelRatio(ratio)
      r.setSize(size.x, size.y, false)
      this.gizmo = gizmo
      this.redraw()
    }
  }
  /** The view's size in pixels (Std_ViewScreenShot's default image size). */
  viewPixels() {
    const c = this.viewer.renderer?.domElement as HTMLCanvasElement | undefined
    return { w: c?.clientWidth ?? 800, h: c?.clientHeight ?? 600 }
  }

  /** Std_BoxSelection (Shift+B): drag a rectangle over the view. Esc cancels. */
  boxSelect(done: (names: string[]) => void) {
    this.rubberBand((a, b) => done(this.bodiesIn(a, b)))
  }

  /** Std_ViewBoxZoom (Ctrl+B): drag a rectangle; the view zooms onto it (NavigationStyle::boxZoom). */
  boxZoom() {
    this.rubberBand((a, b) => {
      const p = this.cameraParts(), canvas = this.viewer.renderer?.domElement as HTMLCanvasElement | undefined
      const x0 = Math.min(a.x, b.x), x1 = Math.max(a.x, b.x), y0 = Math.min(a.y, b.y), y1 = Math.max(a.y, b.y)
      if (!p || !canvas || (x1 - x0 < 1 && y1 - y0 < 1)) return
      const r = canvas.getBoundingClientRect()
      const cx = (((x0 + x1) / 2 - r.left) / r.width) * 2 - 1, cy = 1 - (((y0 + y1) / 2 - r.top) / r.height) * 2
      const depth = p.controls.target.clone().project(p.cam).z
      const shift = new THREE.Vector3(cx, cy, depth).unproject(p.cam).sub(p.controls.target)
      p.controls.target.add(shift)
      p.cam.position.add(shift)
      const f = 1 / Math.max((x1 - x0) / r.width, (y1 - y0) / r.height)
      if ((p.cam as THREE.OrthographicCamera).isOrthographicCamera) { p.cam.zoom *= f; p.cam.updateProjectionMatrix() }
      else { const c = p.cam as THREE.PerspectiveCamera; c.fov = THREE.MathUtils.radToDeg(2 * Math.atan(Math.tan(THREE.MathUtils.degToRad(c.fov) / 2) / f)); c.updateProjectionMatrix() }
      this.settle()
    })
  }

  /** A rubber band over the view; `done` gets where the drag started and ended. */
  private rubberBand(done: (a: { x: number; y: number }, b: { x: number; y: number }) => void) {
    const overlay = document.createElement('div')
    overlay.className = 'box-select'
    const band = document.createElement('div')
    band.className = 'box-band'
    overlay.appendChild(band)
    this.host.appendChild(overlay)
    let start: { x: number; y: number } | null = null
    const finish = () => {
      overlay.remove()
      removeEventListener('keydown', esc, true)
    }
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') { e.stopPropagation(); finish() } }
    addEventListener('keydown', esc, true)
    overlay.onpointerdown = (e) => { start = { x: e.clientX, y: e.clientY }; overlay.setPointerCapture(e.pointerId) }
    overlay.onpointermove = (e) => {
      if (!start) return
      const r = overlay.getBoundingClientRect()
      Object.assign(band.style, { display: 'block', left: `${Math.min(start.x, e.clientX) - r.left}px`, top: `${Math.min(start.y, e.clientY) - r.top}px`,
        width: `${Math.abs(e.clientX - start.x)}px`, height: `${Math.abs(e.clientY - start.y)}px` })
    }
    overlay.onpointerup = (e) => {
      const a = start
      finish()
      if (a) done(a, { x: e.clientX, y: e.clientY })
    }
  }

  /** applyBoxSelection for whole parts: dragged left to right, a part is taken when its
   *  projected box is inside or its centre is; right to left, when it crosses the box. */
  private bodiesIn(a: { x: number; y: number }, b: { x: number; y: number }): string[] {
    const cam = this.viewer.camera?.getCamera?.()
    if (!cam) return []
    const x0 = Math.min(a.x, b.x), x1 = Math.max(a.x, b.x), y0 = Math.min(a.y, b.y), y1 = Math.max(a.y, b.y)
    const crossing = a.x > b.x, toScreen = this.screenOf(cam), s = getState(), out: string[] = []
    for (const name of this.meshes.keys()) {
      if (s.hidden.includes(name) || s.unselectable.includes(name)) continue
      const bb = this.screenBox(name, toScreen)
      if (!bb) continue
      if (bb.x0 >= x0 && bb.x1 <= x1 && bb.y0 >= y0 && bb.y1 <= y1) { out.push(name); continue }
      if (bb.x1 < x0 || bb.x0 > x1 || bb.y1 < y0 || bb.y0 > y1) continue
      const cx = (bb.x0 + bb.x1) / 2, cy = (bb.y0 + bb.y1) / 2
      if (crossing || (cx >= x0 && cx <= x1 && cy >= y0 && cy <= y1)) out.push(name)
    }
    return out
  }

  private labels: { el: HTMLDivElement; at: THREE.Vector3 }[] = []
  /** Measurement labels in the 3D view (ViewProviderMeasureBase's text), kept over their points. */
  showLabels(items: { text: string; at: THREE.Vector3 }[]) {
    for (const l of this.labels) l.el.remove()
    this.labels = items.map(({ text, at }) => {
      const el = document.createElement('div')
      el.className = 'measure-label'
      el.textContent = text
      this.host.appendChild(el)
      return { el, at: at.clone() }
    })
    this.placeLabels()
  }
  private placeLabels() {
    const cam = this.viewer.camera?.getCamera?.(), c = this.viewer.renderer?.domElement as HTMLCanvasElement | undefined
    if (!cam || !c || !this.labels.length) return
    cam.updateMatrixWorld()
    const r = c.getBoundingClientRect(), h = this.host.getBoundingClientRect()
    for (const l of this.labels) {
      const q = l.at.clone().project(cam)
      l.el.style.left = `${r.left - h.left + ((q.x + 1) / 2) * r.width}px`
      l.el.style.top = `${r.top - h.top + ((1 - q.y) / 2) * r.height}px`
      l.el.style.display = q.z > 1 ? 'none' : ''
    }
  }

  /** The current (live, unsaved) measurement's drawMeasure look: 1 anchor (the generic "Base"
   *  leader+marker), 2 points (Distance's dimension line) or an arc polyline (Angle) — `vertex`
   *  is Angle's own origin point, for the spoke lines (regress3-viewer.md #5); unused by the
   *  other kinds. Also called (with no vertex) by the ad hoc `cad measure` console command. */
  showMeasure(pts: number[][] | null, vertex?: number[]) {
    if (this.measureObj) this.viewer.scene?.remove(this.measureObj)
    this.measureObj = null
    this.measureLabelAnchor = null
    this.measureGeom = pts ? { pts, vertex } : null
    if (this.measureGeom) this.drawMeasure()
    this.redraw()
  }

  /** regress3-viewer.md #2: every saved ("kept") measurement's own drawMeasure geometry, kept
   *  fully visible at once instead of sharing showMeasure's single slot — FreeCAD gives each
   *  Measure object its own permanent view-provider scene node (ViewProviderMeasureBase.cpp
   *  ctor, lines 81-243). Called only from measure.tsx; the `cad measure` console command above
   *  has no concept of a saved measurement. */
  showKeptMeasures(kept: { pts: number[][]; vertex?: number[] }[]) {
    for (const o of this.keptObjs) this.viewer.scene?.remove(o)
    this.keptGeoms = kept
    this.keptObjs = this.viewer.scene ? kept.map((k) => this.buildMeasureGroup(k)?.group).filter((o): o is THREE.Group => !!o) : []
    for (const o of this.keptObjs) this.viewer.scene!.add(o)
    this.redraw()
  }

  /** regress3-viewer.md #1/#6: the label anchor drawMeasure last computed for the live
   *  measurement — null for Angle (whose own label position this pass leaves unchanged) or when
   *  nothing is drawn; measure.tsx falls back to its own anchor in that case. */
  getLabelAnchor(): THREE.Vector3 | null { return this.measureLabelAnchor }

  private drawMeasure() {
    if (!this.measureGeom || !this.measureGeom.pts.length || !this.viewer.scene) { this.measureLabelAnchor = null; return }
    const built = this.buildMeasureGroup(this.measureGeom)
    if (!built) { this.measureLabelAnchor = null; return }
    this.viewer.scene.add(built.group)
    this.measureObj = built.group
    this.measureLabelAnchor = built.labelAnchor
  }

  /** Builds one drawMeasure-look group (ViewProviderMeasureBase.cpp's per-instance scene graph)
   *  from a single measurement's points — shared by the live measurement and every saved one, so
   *  a "kept" entry looks exactly like the live measurement did when it was saved. Also returns
   *  the label's anchor: getTextPosition's far end for the 1-point "Base" look, or Distance's
   *  offset dimension-line midpoint; null for Angle. */
  private buildMeasureGroup(geom: { pts: number[][]; vertex?: number[] }): { group: THREE.Group; labelAnchor: THREE.Vector3 | null } | null {
    if (!geom.pts.length) return null
    const pts = geom.pts.map((p) => new THREE.Vector3(...p))
    const g = new THREE.Group()
    const cam = this.viewer.camera?.getCamera?.(), c = this.viewer.renderer?.domElement as HTMLCanvasElement | undefined
    const wpp = cam && c ? this.worldPerPixel(cam, c.clientHeight || 1) : 0.01
    const resW = c?.clientWidth || this.host.clientWidth || 1, resH = c?.clientHeight || this.host.clientHeight || 1
    // ViewProviderMeasureBase.cpp:399-411, applied at :184-195: pLineSeparator (the dimension
    // line / arc+arrowheads / this generic look's own single line) gets a 2px SoDrawStyle;
    // pLineSeparatorSecondary (Distance's two extension lines only) gets 1px. WebGL clamps a
    // plain THREE.Line/LineBasicMaterial to 1px hairlines regardless, so both weights use
    // three's fat-line materials (sized in screen pixels) instead.
    const matPrimary = new LineMaterial({ color: MEASURE_COLOR, linewidth: 2, depthTest: false })
    const matSecondary = new LineMaterial({ color: MEASURE_COLOR, linewidth: 1, depthTest: false })
    matPrimary.resolution.set(resW, resH)
    matSecondary.resolution.set(resW, resH)
    // The CROSS SoMarkerSet FreeCAD draws at each raw measured point (ViewParams MarkerSize).
    const marks = (at: THREE.Vector3[]) => {
      const m = new THREE.Points(new THREE.BufferGeometry().setFromPoints(at),
        new THREE.PointsMaterial({ color: MEASURE_COLOR, map: crossTexture(), size: MARKER_PX, sizeAttenuation: false, transparent: true, depthTest: false }))
      m.renderOrder = 999
      return m
    }
    let labelAnchor: THREE.Vector3 | null = null
    if (pts.length > 2) {
      // ViewProviderMeasureAngle.cpp:288-422: the arc itself (Gui::ArcEngine), plus a cone
      // arrowhead at each end, tangent to it and tipped exactly at the endpoint (the
      // SoTranslation + SoCone pair, lines 388-401), shrunk on a short arc so the two don't
      // overlap (lines 376-382's "ta=(a*b)/(3*c*d)", here from the polyline's own length).
      const line = new Line2(new LineGeometry().setFromPoints(pts), matPrimary)
      line.renderOrder = 999
      g.add(line)
      let arcLen = 0
      for (let i = 1; i < pts.length; i++) arcLen += pts[i].distanceTo(pts[i - 1])
      const h = ARROW_HEIGHT_PX * wpp, r = ARROW_RADIUS_PX * wpp
      const scale = h > 0 ? Math.min(1, arcLen / (3 * h)) : 1
      for (const [tip, prev] of [[pts[0], pts[1]], [pts[pts.length - 1], pts[pts.length - 2]]] as const) {
        const dir = tip.clone().sub(prev)
        if (dir.lengthSq() < 1e-12) continue
        dir.normalize()
        const cone = new THREE.Mesh(new THREE.ConeGeometry(r * scale, h * scale, 12), new THREE.MeshBasicMaterial({ color: MEASURE_COLOR, depthTest: false }))
        cone.position.copy(tip).addScaledVector(dir, -(h * scale) / 2) // apex (local +Y) lands on tip
        cone.quaternion.setFromUnitVectors(CONE_UP, dir)
        cone.renderOrder = 999
        g.add(cone)
      }
      // ViewProviderMeasureAngle.cpp:425-481 (pNormalsStandardSep, the common non-imgOrigin
      // case — a permanently-active SoSwitch, never "none"): two 0.8px spokes from the vertex
      // (local origin) out to each arc endpoint, completing the pie-slice outline FreeCAD always
      // draws alongside the arc (regress3 #5). Reuses matSecondary, as the audit's own
      // "linewidth:1-ish" suggestion, rather than a 3rd material just for this.
      if (geom.vertex) {
        const v = new THREE.Vector3(...geom.vertex), far = pts[pts.length - 1]
        const spokes = new LineSegments2(new LineSegmentsGeometry().setPositions(
          [v.x, v.y, v.z, pts[0].x, pts[0].y, pts[0].z, v.x, v.y, v.z, far.x, far.y, far.z]), matSecondary)
        spokes.renderOrder = 999
        g.add(spokes)
      }
    } else if (pts.length === 2) {
      // ViewProviderMeasureDistance.cpp:322-391: two extension lines from the measured points
      // out to an offset dimension line, the dimension line itself, and a CROSS SoMarkerSet
      // (Gui::ViewParams MarkerSize) at each measured point — no arrowheads on a straight
      // distance, that's Angle's thing (verified against the real ctor, not just the audit).
      // Perpendicular direction: getTextDirection (lines 285-307); the gap approximates the
      // default, un-dragged label offset (positionAnno's "0.1 * getViewScale()" — Coin's exact
      // screen-scale formula isn't reproducible without the live app, so a constant pixel gap
      // stands in for it).
      const [p0, p1] = pts, gap = measureTextDir(p1.clone().sub(p0)).multiplyScalar(DIM_GAP_PX * wpp)
      const o0 = p0.clone().add(gap), o1 = p1.clone().add(gap)
      const dimLine = new Line2(new LineGeometry().setFromPoints([o0, o1]), matPrimary)
      const extLines = new LineSegments2(new LineSegmentsGeometry().setPositions([p0.x, p0.y, p0.z, o0.x, o0.y, o0.z, p1.x, p1.y, p1.z, o1.x, o1.y, o1.z]), matSecondary)
      dimLine.renderOrder = extLines.renderOrder = 999
      g.add(dimLine, extLines, marks([p0, p1]))
      // ViewProviderMeasureDistance.cpp:537-540 positionAnno: the default label sits at
      // SbVec3f(0, 0.1*getViewScale(), 0) in the dimension's own local frame — i.e. at the
      // offset line's own midpoint, not the raw measured segment's (regress3 #6).
      labelAnchor = o0.clone().lerp(o1, 0.5)
    } else {
      // ViewProviderMeasureBase.cpp:679-718 (ViewProviderMeasure, the generic view provider
      // used by every measure kind with no specialised one of its own — Length, Position,
      // Diameter, Radius, Area, Geometric Center): a single line from the anchor (pts[0]) out
      // to the label (getTextPosition, ~752-766: 30px up-and-right of the anchor in screen
      // space) plus one CROSS marker at the anchor — previously this kind drew nothing at all.
      const p0 = pts[0]
      const right = new THREE.Vector3(), up = new THREE.Vector3(), fwd = new THREE.Vector3()
      cam?.matrixWorld.extractBasis(right, up, fwd)
      const label = p0.clone().addScaledVector(right, LABEL_OFFSET_PX * wpp).addScaledVector(up, LABEL_OFFSET_PX * wpp)
      const line = new Line2(new LineGeometry().setFromPoints([p0, label]), matPrimary)
      line.renderOrder = 999
      g.add(line, marks([p0]))
      // getTextPosition returns basePos + 30px-up-right — the line's own far end, not the
      // anchor it starts from (regress3 #1: the label must sit there, not back on the anchor).
      labelAnchor = label
    }
    return { group: g, labelAnchor }
  }

  /** Std_ToggleClipPlane: FreeCAD's Clipping dialog, X / Y / Z planes each with an
   *  offset and a flip. Points with n·p + c < 0 are cut away. */
  /** Clipping's SoClipPlanes. Coin keeps the side the normal points to (n·p ≥ d), so Clipping X
   *  at c keeps x ≥ c, and Flip keeps x ≤ c. The custom plane's normal is its Direction, the
   *  view direction after View, or the view direction as it turns (Adjust to view direction). */
  private applyClip(clip: Clip | null) {
    const planes: THREE.Plane[] = []
    if (clip) {
      ;(['x', 'y', 'z'] as const).forEach((ax, i) => {
        const c = clip[ax]
        if (!c.on) return
        const n = new THREE.Vector3(+(i === 0), +(i === 1), +(i === 2)).multiplyScalar(c.flip ? -1 : 1)
        planes.push(new THREE.Plane(n, c.flip ? c.offset : -c.offset))
      })
      const v = clip.view
      if (v?.on) {
        const cam = this.viewer.camera?.getCamera?.()
        const n = v.adjust && cam ? new THREE.Vector3(0, 0, -1).applyQuaternion(cam.quaternion) : new THREE.Vector3(...v.normal)
        if (n.lengthSq() > 0) planes.push(new THREE.Plane(n.normalize(), -v.offset))
      }
    }
    this.viewer.renderer.localClippingEnabled = planes.length > 0
    const groups = this.viewer.nestedGroup?.groups ?? {}
    for (const b of getState().scene?.bodies ?? []) {
      groups[b.path]?.traverse?.((o: any) => {
        const mats = [o.material, o.userData?.cadOrigMat].filter(Boolean)
        for (const m of mats) { m.clippingPlanes = planes.length ? planes : null; m.needsUpdate = true }
      })
    }
  }

  /** The draw styles that need other materials: Hidden line (faces in the
   *  background colour), No shading (unlit colours), Points (the mesh points). */
  private applyStyleMaterials(style: DrawStyle, hidden: string[]) {
    const swap = style === 'hiddenline' || style === 'noshading'
    for (const [name, list] of this.meshes) {
      for (const m of list) {
        const u = m.userData
        if (swap) {
          if (!u.cadOrigMat) u.cadOrigMat = m.material
          const orig = u.cadOrigMat
          const mat: THREE.MeshBasicMaterial = u.cadStyleMat ?? (u.cadStyleMat = new THREE.MeshBasicMaterial({ polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 }))
          mat.side = orig.side
          mat.color.set(style === 'hiddenline' ? VIEW.background : orig.color)
          mat.transparent = orig.transparent
          mat.opacity = orig.opacity
          mat.clippingPlanes = orig.clippingPlanes
          m.material = mat
        } else if (u.cadOrigMat) {
          m.material = u.cadOrigMat
          u.cadOrigMat = undefined
        }
        if (style === 'points' && !u.cadPoints && (u.cadOrigMat ?? m.material).side !== THREE.BackSide) {
          const pts = new THREE.Points(m.geometry, new THREE.PointsMaterial({ color: VIEW.line, size: 2, sizeAttenuation: false }))
          pts.userData.cadHelper = true
          pts.matrixAutoUpdate = false
          pts.matrix.copy(m.matrix)
          m.parent?.add(pts)
          u.cadPoints = pts
        }
        if (u.cadPoints) u.cadPoints.visible = style === 'points' && !hidden.includes(name)
      }
    }
  }

  /** Bounding boxes: each object's BoundingBox property (BoundingBoxColor), and — when
   *  Std_SelBoundingBox is on or its own SelectionStyle is BoundBox — the ordinary
   *  highlight/selection colour for a selected or merely preselected object
   *  (SoFCSelectionRoot::_renderPrivate triggers on ctx->selAll || ctx->hlAll). */
  /** ViewProviderDragger::ShowPlacement: an SoFCPlacementIndicatorKit at the object's placement,
   *  parts AxisCross (Axes | Labels | ArrowHeads) in an SoShapeScale of scaleFactor 40 — one unit is
   *  40px whatever the zoom: shafts axisLength 0.6 by axisThickness 0.065, cones arrowHeadRadius
   *  0.08125 by 3x that, labels 0.4 past the shaft centre's end, in the axis colours. */
  private placementHelpers: THREE.Group[] = []
  private camTimer = 0
  private applyPlacementIndicators() {
    for (const h of this.placementHelpers) this.viewer.scene?.remove(h)
    this.placementHelpers = []
    const s = getState()
    if (!this.viewer.scene) return
    for (const b of s.scene?.bodies ?? []) {
      if (s.hidden.includes(b.name) || !viewOf(s, b.name).showPlacement) continue
      const p = b.placement ?? {}
      const m = placementMatrix({ move: (p.move ?? [0, 0, 0]) as Vec3, turn: (p.turn ?? [0, 0, 0]) as Vec3, about: (p.about ?? b.about ?? [0, 0, 0]) as Vec3 })
      const g = new THREE.Group()
      m.decompose(g.position, g.quaternion, new THREE.Vector3())
      const AXES: [THREE.Vector3, string, string][] = [[new THREE.Vector3(1, 0, 0), s.axisColors.x, 'X'], [new THREE.Vector3(0, 1, 0), s.axisColors.y, 'Y'], [new THREE.Vector3(0, 0, 1), s.axisColors.z, 'Z']]
      for (const [dir, color, label] of AXES) {
        const turn = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir)
        const mat = new THREE.MeshBasicMaterial({ color, depthTest: false })
        const shaft = new THREE.Mesh(new THREE.CylinderGeometry(0.0325, 0.0325, 0.6, 12), mat)
        shaft.position.copy(dir).multiplyScalar(0.3); shaft.quaternion.copy(turn)
        const head = new THREE.Mesh(new THREE.ConeGeometry(0.08125, 0.24375, 16), mat)
        head.position.copy(dir).multiplyScalar(0.6); head.quaternion.copy(turn)
        const tag = labelSprite(label, color)
        tag.position.copy(dir).multiplyScalar(1.0)
        for (const o of [shaft, head, tag]) { o.renderOrder = 998; g.add(o) }
      }
      g.userData.cadHelper = true
      this.viewer.scene.add(g)
      this.placementHelpers.push(g)
    }
    this.scalePlacementIndicators()
  }
  private scalePlacementIndicators() {
    const cam = this.viewer.camera?.getCamera?.(), c = this.viewer.renderer?.domElement as HTMLCanvasElement | undefined
    if (!cam || !c || !c.clientHeight) return // hidden (another tab in front): sized when it shows
    for (const g of this.placementHelpers) g.scale.setScalar(40 * this.worldPerPixel(cam, c.clientHeight))
  }

  private applyBoxes(selected: string[], preselected: string | null, selBoxes: boolean) {
    for (const h of this.boxHelpers) this.viewer.scene?.remove(h)
    this.boxHelpers = []
    const s = getState()
    for (const n of this.meshes.keys()) {
      if (s.hidden.includes(n)) continue
      const vp = viewOf(s, n), sel = selected.includes(n), pre = !sel && n === preselected
      const boxed = selBoxes || vp.selectionStyle === 'BoundBox'
      const color = sel && boxed ? VIEW.select : pre && boxed ? VIEW.preselect : vp.boundingBox ? BBOX_COLOR : null
      if (color === null) continue
      const box = new THREE.Box3()
      ;(this.meshes.get(n) ?? []).forEach((m) => box.expandByObject(m))
      if (box.isEmpty()) continue
      const h = new THREE.Box3Helper(box, new THREE.Color(color))
      h.userData.cadHelper = true
      this.viewer.scene.add(h)
      this.boxHelpers.push(h)
    }
  }

  /** The View tab's Object Style (ViewProviderPartExt): Transparency (0-100), the
   *  ShapeAppearance colour, Lighting, LineColor, LineWidth, DrawStyle, PointColor, PointSize. */
  private applyLook(view: Record<string, Partial<ViewProps>>) {
    const s = { view }
    for (const [name, list] of this.meshes) {
      const vp = viewOf(s, name)
      const done = new Set<unknown>()
      for (const m of list) {
        const mat = (m.userData.cadOrigMat ?? m.material) as any
        if (!mat?.color || done.has(mat)) continue
        done.add(mat)
        const u = mat.userData
        if (u.cadOpacity === undefined) { u.cadOpacity = mat.opacity; u.cadTransparent = mat.transparent; u.cadDepthWrite = mat.depthWrite }
        if (u.cadBase === undefined) u.cadBase = mat.color.getHex()
        if (u.cadOriginal === undefined) u.cadOriginal = u.cadBase
        const t = Math.min(100, Math.max(0, vp.transparency)) / 100
        mat.transparent = t > 0 || u.cadTransparent
        mat.opacity = t > 0 ? 1 - t : u.cadOpacity
        mat.depthWrite = t > 0 ? false : u.cadDepthWrite
        const base = vp.shapeColor ?? u.cadOriginal
        // One-side lighting leaves the back faces unlit (dark), as Coin draws them.
        u.cadBase = mat.side === THREE.BackSide && vp.lighting === 'One side' ? new THREE.Color(base).multiplyScalar(0.25).getHex() : base
        mat.needsUpdate = true
      }
      for (const e of (this.edges.get(name) ?? []) as any[]) {
        const mat = e.material
        if (!mat) continue
        mat.userData.cadBase = vp.lineColor
        if ('linewidth' in mat) mat.linewidth = Math.max(1, vp.lineWidth)
        // DrawStyle: Coin's 16-pixel line patterns, approximated in model units.
        const dashed = vp.drawStyle !== 'Solid'
        if (dashed && !e.userData.cadDistances) { e.computeLineDistances?.(); e.userData.cadDistances = true }
        mat.dashed = dashed
        if (dashed) {
          const unit = this.dashUnit()
          const [dash, gap] = vp.drawStyle === 'Dashed' ? [4, 4] : vp.drawStyle === 'Dotted' ? [1, 1] : [6, 3]
          mat.dashSize = dash * unit
          mat.gapSize = gap * unit
          mat.dashScale = 1
        }
        mat.needsUpdate = true
      }
      for (const p of this.verts.get(name) ?? []) {
        const mat = p.material as THREE.PointsMaterial
        mat.size = Math.max(1, vp.pointSize)
        mat.color.setHex(vp.pointColor)
        mat.needsUpdate = true
      }
    }
  }
  /** About one screen pixel in model units, for dash patterns. */
  private dashUnit() {
    const cam = this.viewer.camera?.getCamera?.(), c = this.viewer.renderer?.domElement as HTMLCanvasElement | undefined
    return cam && c ? this.worldPerPixel(cam, c.clientHeight || 1) : 0.1
  }

  private onCanvas(e: Event) {
    return e.target === this.viewer.renderer?.domElement
  }

  /** What is under the pointer: the part, the point, and the sub-element. Like
   *  FreeCAD, a vertex within a few pixels wins over an edge, an edge over a face. */
  private hitAt(e: { x: number; y: number }): { body: string; point: THREE.Vector3; sub: string | null } | null {
    const canvas = this.viewer.renderer?.domElement as HTMLCanvasElement | undefined
    const cam = this.viewer.camera?.getCamera?.()
    if (!canvas || !cam || !this.meshes.size) return null
    const r = canvas.getBoundingClientRect()
    cam.updateMatrixWorld()
    this.ray.setFromCamera(new THREE.Vector2(((e.x - r.left) / r.width) * 2 - 1, -((e.y - r.top) / r.height) * 2 + 1), cam)
    const unselectable = getState().unselectable // Std_ToggleSelectability: clicks go through these
    const pick = <T extends THREE.Object3D>(m: Map<string, T[]>) => {
      const out: T[] = []
      for (const [name, list] of m) if (!unselectable.includes(name)) for (const o of list) if (shown(o)) out.push(o)
      return out
    }
    const face = this.ray.intersectObjects(pick(this.meshes), false)[0]
    const perPx = this.worldPerPixel(cam, r.height)
    // SelectionPickPolicy::getPickCandidate's closeToFirst: a fixed 0.2 model-unit radius,
    // not pixel-based, so an edge or vertex on the face we hit still counts as visible.
    const slack = 0.2
    ;(this.ray as any).camera = cam
    this.ray.params.Line2 = { threshold: 6 } as any
    this.ray.params.Points = { threshold: perPx * 6 }
    const vert = this.ray.intersectObjects(pick(this.verts), false).find((h) => !face || h.distance <= face.distance + slack)
    const edge = this.ray.intersectObjects(pick(this.edges), false).find((h) => !face || h.distance <= face.distance + slack)
    const id = (h: THREE.Intersection, i: number | null | undefined) => (h.object as any).geometry.attributes.componentId?.getX(i ?? 0) as number
    const name = (kind: 'Face' | 'Edge' | 'Vertex', body: string, cid: number) => `${kind}${cid - (this.bases.get(body)?.[kind] ?? 0)}`
    if (vert) return { body: vert.object.userData.cadBody, point: vert.point, sub: name('Vertex', vert.object.userData.cadBody, id(vert, vert.index)) }
    if (edge) return { body: edge.object.userData.cadBody, point: (edge as any).pointOnLine ?? edge.point, sub: name('Edge', edge.object.userData.cadBody, id(edge, edge.faceIndex)) }
    if (face) {
      const g = (face.object as THREE.Mesh).geometry
      const fid = g.index && face.faceIndex != null ? g.attributes.componentId?.getX(g.index.getX(face.faceIndex * 3)) : undefined
      return { body: face.object.userData.cadBody, point: face.point, sub: fid != null ? name('Face', face.object.userData.cadBody, fid) : null }
    }
    return null
  }

  /** A pick-all: every face along the ray, and the edges and vertices within the pick
   *  radius (5 px) times a multiplier (Clarify Selection's ClarifySelectionRadiusMultiplier, 5). */
  picksAt(e: { x: number; y: number }, multiplier = 5): { body: string; sub: string | null }[] {
    const canvas = this.viewer.renderer?.domElement as HTMLCanvasElement | undefined
    const cam = this.viewer.camera?.getCamera?.()
    if (!canvas || !cam) return []
    const r = canvas.getBoundingClientRect()
    cam.updateMatrixWorld()
    this.ray.setFromCamera(new THREE.Vector2(((e.x - r.left) / r.width) * 2 - 1, -((e.y - r.top) / r.height) * 2 + 1), cam)
    const s = getState(), perPx = this.worldPerPixel(cam, r.height)
    ;(this.ray as any).camera = cam
    this.ray.params.Line2 = { threshold: 5 * multiplier } as any
    this.ray.params.Points = { threshold: perPx * 5 * multiplier }
    const all = <T extends THREE.Object3D>(m: Map<string, T[]>) => {
      const out: T[] = []
      for (const [name, list] of m) if (!s.unselectable.includes(name)) for (const o of list) if (shown(o)) out.push(o)
      return out
    }
    const name = (kind: 'Face' | 'Edge' | 'Vertex', body: string, cid: number) => `${kind}${cid - (this.bases.get(body)?.[kind] ?? 0)}`
    const out: { body: string; sub: string | null }[] = [], seen = new Set<string>()
    const add = (body: string, sub: string | null) => { const k = `${body}.${sub}`; if (!seen.has(k)) { seen.add(k); out.push({ body, sub }) } }
    for (const h of this.ray.intersectObjects(all(this.meshes), false)) {
      const g = (h.object as THREE.Mesh).geometry, body = h.object.userData.cadBody
      const fid = g.index && h.faceIndex != null ? g.attributes.componentId?.getX(g.index.getX(h.faceIndex * 3)) : undefined
      if (fid != null) add(body, name('Face', body, fid))
    }
    for (const h of this.ray.intersectObjects(all(this.edges), false)) {
      const body = h.object.userData.cadBody, id = (h.object as any).geometry.attributes.componentId?.getX(h.faceIndex ?? 0)
      if (id != null) add(body, name('Edge', body, id))
    }
    for (const h of this.ray.intersectObjects(all(this.verts), false)) {
      const body = h.object.userData.cadBody, id = (h.object as any).geometry.attributes.componentId?.getX(h.index ?? 0)
      if (id != null) add(body, name('Vertex', body, id))
    }
    return out
  }

  private worldPerPixel(cam: THREE.Camera, heightPx: number) {
    const c: any = cam
    if (c.isOrthographicCamera) return (c.top - c.bottom) / c.zoom / heightPx
    const d = c.position.distanceTo(this.viewer.controls?.controls?.target ?? new THREE.Vector3())
    return (2 * d * Math.tan(THREE.MathUtils.degToRad(c.fov) / 2)) / heightPx
  }
  /** worldPerPixel at the camera's own focal/target distance — this file's stand-in for Coin's
   *  getViewScale() (see DIM_GAP_PX above). Public so measure.tsx can size the Angle arc radius
   *  the same way ViewProviderMeasureAngle.cpp:644 does. */
  viewScalePerPixel() {
    const cam = this.viewer.camera?.getCamera?.(), c = this.viewer.renderer?.domElement as HTMLCanvasElement | undefined
    return cam && c ? this.worldPerPixel(cam, c.clientHeight || 1) : 0.01
  }

  // ── sub-elements: highlight, measure, align ─────────────────────────────────
  private front(body: string) {
    return (this.meshes.get(body) ?? []).find((m) => (m.userData.cadOrigMat ?? m.material).side !== THREE.BackSide)
  }

  /** The world-space geometry of Face n, Edge n or Vertex n of a part. */
  subGeometry(ref: string): { kind: 'Face'; tris: THREE.Vector3[][] } | { kind: 'Edge'; segs: THREE.Vector3[][] } | { kind: 'Vertex'; point: THREE.Vector3 } | null {
    const dot = ref.lastIndexOf('.'), body = ref.slice(0, dot), m = /^(Face|Edge|Vertex)(\d+)$/.exec(ref.slice(dot + 1))
    if (!m) return null
    const id = Number(m[2]) + (this.bases.get(body)?.[m[1] as 'Face' | 'Edge' | 'Vertex'] ?? 0)
    if (m[1] === 'Face') {
      const mesh = this.front(body)
      if (!mesh) return null
      mesh.updateWorldMatrix(true, false)
      const g = mesh.geometry, idx = g.index!, pos = g.attributes.position, comp = g.attributes.componentId, tris: THREE.Vector3[][] = []
      for (let t = 0; t < idx.count; t += 3) {
        if (comp.getX(idx.getX(t)) !== id) continue
        tris.push([0, 1, 2].map((k) => new THREE.Vector3().fromBufferAttribute(pos, idx.getX(t + k)).applyMatrix4(mesh.matrixWorld)))
      }
      return tris.length ? { kind: 'Face', tris } : null
    }
    if (m[1] === 'Edge') {
      const line = (this.edges.get(body) ?? [])[0] as any
      if (!line) return null
      line.updateWorldMatrix(true, false)
      const g = line.geometry, a = g.attributes.instanceStart, b = g.attributes.instanceEnd, comp = g.attributes.componentId, segs: THREE.Vector3[][] = []
      for (let i = 0; i < comp.count; i++) {
        if (comp.getX(i) === id) segs.push([new THREE.Vector3().fromBufferAttribute(a, i).applyMatrix4(line.matrixWorld), new THREE.Vector3().fromBufferAttribute(b, i).applyMatrix4(line.matrixWorld)])
      }
      return segs.length ? { kind: 'Edge', segs } : null
    }
    const pts = (this.verts.get(body) ?? [])[0]
    if (!pts) return null
    pts.updateWorldMatrix(true, false)
    const comp = pts.geometry.attributes.componentId, pos = pts.geometry.attributes.position
    for (let i = 0; i < comp.count; i++) if (comp.getX(i) === id) return { kind: 'Vertex', point: new THREE.Vector3().fromBufferAttribute(pos, i).applyMatrix4(pts.matrixWorld) }
    return null
  }

  /** Highlight sub-elements the way FreeCAD does: only the face, edge or vertex. */
  private applySubs(pre: string | null, subs: string[]) {
    for (const o of this.overlays) o.parent?.remove(o)
    this.overlays = []
    const add = (ref: string, color: number) => {
      const g = this.subGeometry(ref)
      if (!g || !this.viewer.scene) return
      let o: THREE.Object3D
      if (g.kind === 'Face') {
        const geo = new THREE.BufferGeometry().setFromPoints(g.tris.flat())
        o = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 }))
      } else if (g.kind === 'Edge') {
        const mat = new LineMaterial({ color, linewidth: 4 })
        mat.resolution.set(this.viewer.renderer.domElement.clientWidth, this.viewer.renderer.domElement.clientHeight)
        o = new LineSegments2(new LineSegmentsGeometry().setPositions(g.segs.flatMap(([a, b]) => [a.x, a.y, a.z, b.x, b.y, b.z])), mat)
      } else {
        o = new THREE.Points(new THREE.BufferGeometry().setFromPoints([g.point]), new THREE.PointsMaterial({ color, size: 10, sizeAttenuation: false, depthTest: false }))
      }
      o.userData.cadHelper = true
      o.renderOrder = 5
      this.viewer.scene.add(o)
      this.overlays.push(o)
    }
    subs.forEach((r) => add(r, VIEW.select))
    if (pre && !subs.includes(pre)) add(pre, VIEW.preselect)
  }

  /** Std_AlignToSelection: look straight at a selected planar face. */
  alignTo(ref: string): boolean {
    const info = subInfo(this.subGeometry(ref))
    const p = this.cameraParts()
    if (!info?.normal || !p) return false
    const m = new THREE.Matrix4().lookAt(info.normal, new THREE.Vector3(), Math.abs(info.normal.z) > 0.99 ? new THREE.Vector3(0, 1, 0) : new THREE.Vector3(0, 0, 1))
    this.animateTo(new THREE.Quaternion().setFromRotationMatrix(m), info.center)
    return true
  }

  private index(sc: Scene) {
    this.meshes.clear()
    this.edges.clear()
    const groups = this.viewer.nestedGroup?.groups ?? {}
    for (const b of sc.bodies) {
      const faces: THREE.Mesh[] = [], edges: THREE.Object3D[] = [], verts: THREE.Points[] = []
      groups[b.path]?.traverse?.((o: any) => {
        if (/Stencil/.test(o.name ?? '') || o.userData.cadHelper) return // clipping caps, our own overlays
        o.userData.cadBody = b.name
        if (o.isLineSegments2 || o.isLineSegments || o.isLine) edges.push(o)
        else if (o.isPoints) verts.push(o)
        else if (o.isMesh) faces.push(o)
      })
      this.meshes.set(b.name, faces)
      this.edges.set(b.name, edges)
      this.verts.set(b.name, verts)
      const lowest = (o: any) => {
        const c = o?.geometry?.attributes?.componentId
        let m = Infinity
        if (c) for (let i = 0; i < c.count; i++) m = Math.min(m, c.getX(i))
        return Number.isFinite(m) ? m - 1 : 0
      }
      this.bases.set(b.name, { Face: lowest(faces[0]), Edge: lowest(edges[0]), Vertex: lowest(verts[0]) })
    }
    this.applied = { ...UNAPPLIED, cube: getState().cube }
    this.boxHelpers = []
    this.measureObj = null
    this.measureLabelAnchor = null
    this.keptObjs = [] // the old scene (and everything added to it) is already gone; sync() rebuilds from keptGeoms/measureGeom
    this.overlays = []
  }

  private sync() {
    if (!this.rendered) return
    const s = getState()
    let dirty = false
    if (s.hidden !== this.applied.hidden || s.drawStyle !== this.applied.style || s.view !== this.applied.view) { this.applyHidden(s.hidden, s.drawStyle); dirty = true }
    if (s.cube !== this.applied.cube) {
      if (s.cube) this.attachGizmo()
      else { this.gizmo?.dispose(); this.gizmo = null }
      dirty = true
    }
    let look = false
    if (s.view !== this.applied.view) { this.applyLook(s.view); look = true }
    if (s.preSub !== this.applied.preSub || s.subSel !== this.applied.subSel) { this.applySubs(s.preSub, s.subSel); dirty = true }
    if (look || s.selected !== this.applied.selected || s.preselected !== this.applied.preselected || s.drawStyle !== this.applied.style || s.subSel !== this.applied.subSel || s.preSub !== this.applied.preSub) {
      // A part selected through one of its faces shows just that face, as in FreeCAD;
      // hovering in the 3D view lights the element under the pointer, not the whole part.
      const whole = s.selected.filter((n) => !s.subSel.some((r) => r.startsWith(n + '.')))
      this.applyTints(whole, s.preSub ? null : s.preselected)
      this.applyStyleMaterials(s.drawStyle, s.hidden)
      dirty = true
    }
    if (s.clip !== this.applied.clip) { this.applyClip(s.clip); dirty = true }
    if (s.nav !== this.applied.nav || s.navPrefs !== this.applied.navPrefs) this.applyNav(s.nav, s.navPrefs)
    if (s.selBoxes !== this.applied.selBoxes || s.selected !== this.applied.selected || s.preselected !== this.applied.preselected || s.hidden !== this.applied.hidden || s.view !== this.applied.view) {
      this.applyBoxes(s.selected, s.preselected, s.selBoxes)
      this.applyPlacementIndicators()
      dirty = true
    }
    if (s.axes !== this.applied.axes) { try { this.viewer.setAxes(s.axes) } catch { /* no axes yet */ } dirty = true }
    if (s.showFPS !== this.applied.showFPS) { this.setShowFPS(s.showFPS); dirty = true }
    if (s.corner !== this.applied.corner) dirty = true
    if (s.background !== this.applied.background) { this.applyBackground(s.background); dirty = true }
    if (s.lights !== this.lightsApplied) { this.applyLights(s.lights); dirty = true }
    // Preferences > Navigation Cube: a new size, corner, colour or font rebuilds the cube.
    if (s.naviCube !== this.applied.naviCube) {
      this.naviRotateToNearest = s.naviCube.toNearest
      if (this.applied.naviCube && s.cube) { this.applied = { ...this.applied, naviCube: s.naviCube }; this.attachGizmo() }
      dirty = true
    }
    if (!this.measureObj && this.measureGeom) { this.drawMeasure(); dirty = true }
    if (!this.keptObjs.length && this.keptGeoms.length && this.viewer.scene) {
      this.keptObjs = this.keptGeoms.map((k) => this.buildMeasureGroup(k)?.group).filter((o): o is THREE.Group => !!o)
      for (const o of this.keptObjs) this.viewer.scene.add(o)
      dirty = true
    }
    this.applied = { selected: s.selected, preselected: s.preselected, hidden: s.hidden, style: s.drawStyle, cube: s.cube,
      view: s.view, selBoxes: s.selBoxes, axes: s.axes, showFPS: s.showFPS, clip: s.clip, preSub: s.preSub, subSel: s.subSel, nav: s.nav, navPrefs: s.navPrefs, corner: s.corner, naviCube: s.naviCube, background: s.background }
    if (dirty) this.redraw()
  }

  /** FreeCAD colours a selected object in the selection colour and the one under the
   *  mouse in the preselection colour; SelectionStyle BoundBox shows a box instead. With
   *  OnTopWhenSelected, a selected object draws over the others (Enabled: always; Object:
   *  when it is selected whole; Element: when one of its elements is). */
  private applyTints(selected: string[], pre: string | null) {
    const s = getState()
    for (const [name, list] of this.meshes) {
      const vp = viewOf(s, name)
      const boxed = vp.selectionStyle === 'BoundBox'
      const c = !boxed && selected.includes(name) ? VIEW.select : !boxed && name === pre ? VIEW.preselect : null
      const whole = s.selected.includes(name) && !s.subSel.some((r) => r.startsWith(name + '.'))
      const element = s.subSel.some((r) => r.startsWith(name + '.'))
      const top = vp.onTop === 'Enabled' ? whole || element : vp.onTop === 'Object' ? whole : vp.onTop === 'Element' ? element : false
      const done = new Set<unknown>()
      for (const m of [...list, ...(this.edges.get(name) ?? [])] as any[]) {
        m.renderOrder = top ? 10 : 0
        const mat = (m.userData.cadOrigMat ?? m.material) as any
        if (!mat?.color || done.has(mat)) continue
        done.add(mat)
        if (mat.userData.cadBase === undefined) mat.userData.cadBase = mat.color.getHex()
        mat.color.setHex(c ?? mat.userData.cadBase)
        if (mat.userData.cadDepthTest === undefined) mat.userData.cadDepthTest = mat.depthTest
        mat.depthTest = top ? false : mat.userData.cadDepthTest
      }
    }
  }

  /** Visibility, and what each object shows: its Display Mode when the draw style is As is,
   *  else the draw style for all (Std_DrawStyle). */
  private applyHidden(hidden: string[], style: DrawStyle) {
    const sc = getState().scene
    if (!sc) return
    const s = getState(), states: Record<string, [number, number]> = {}
    for (const b of sc.bodies) {
      const mode = DISPLAY[viewOf(s, b.name).displayMode]
      states[b.path] = hidden.includes(b.name) ? [0, 0] : style === 'asis' ? [mode[0], mode[1]] : STYLE[style]
    }
    try { this.viewer.setStates(states) } catch (e) { console.warn('setStates failed', e) }
    for (const b of sc.bodies) {
      // setOverrideMode: Hidden Line forces every object's structural mode to Shaded
      // (faces only, no point set), so it shows no vertex points either, like Shaded.
      const on = !hidden.includes(b.name) && (style === 'asis' ? DISPLAY[viewOf(s, b.name).displayMode][2] : style !== 'shaded' && style !== 'hiddenline')
      for (const p of this.verts.get(b.name) ?? []) p.visible = on
    }
  }

  private attachGizmo() {
    this.gizmo?.dispose()
    this.gizmo = null
    this.cubeAxes = null
    const cam = this.viewer.camera?.getCamera?.()
    const renderer = this.viewer.renderer
    if (!cam || !renderer) return
    // populateRenderParams: the whole cube's opacity is its BaseColor alpha (1, under
    // FreeCAD Light) at rest; updateCubeFade fades it outside its own square.
    const nc = getState().naviCube
    const { placement, offset } = cubeLayout(getState().cubePos, this.host.clientWidth || 1, this.host.clientHeight || 1, nc.size)
    const face = { color: new THREE.Color(nc.color).getHex(), opacity: 1, labelColor: 0x000000, hover: { color: VIEW.cubeHover, labelColor: 0x000000, opacity: 1 } }
    const g = new ViewportGizmo(cam, renderer, {
      type: 'cube', placement, size: nc.size, offset, container: this.host,
      font: { family: nc.font || 'Arial', weight: 400 }, // FontString (empty: createCubeFaceTextures's Arial), FontWeight default 0 (normal)
      background: { color: 0xffffff, opacity: 0, hover: { color: 0xffffff, opacity: 0 } },
      corners: { color: 0xc9d1da, opacity: 1, hover: { color: VIEW.cubeHover, opacity: 1 } },
      edges: { color: 0xd3dae2, opacity: 1, hover: { color: VIEW.cubeHover, opacity: 1 } },
      x: { ...face, label: 'RIGHT' }, nx: { ...face, label: 'LEFT' },
      y: { ...face, label: 'REAR' }, ny: { ...face, label: 'FRONT' },
      z: { ...face, label: 'TOP' }, nz: { ...face, label: 'BOTTOM' },
    } as any)
    const controls = this.viewer.controls?.controls
    if (controls) g.attachControls(controls)
    g.addEventListener('change', () => this.redraw())
    // FreeCAD's NaviCube instead of the gizmo's own click and drag (NaviCube.cpp).
    ;(g as any)._onPointerDown = (e: PointerEvent) => this.cubePress(e)
    if (nc.showCS) { this.cubeAxes = buildShowCS(renderer.domElement.clientWidth || this.host.clientWidth || 1, renderer.domElement.clientHeight || this.host.clientHeight || 1); g.add(this.cubeAxes) }
    this.gizmo = g
    this.cubeFade = 1 // fresh meshes start at the config opacity above; resync on the next pointer move
    const st = getState() // only on a change: setState re-enters sync
    if (st.cubePlace !== placement || JSON.stringify(st.cubeOffset) !== JSON.stringify(offset)) setState({ cubePlace: placement, cubeOffset: offset })
    this.hookRender()
    g.update()
  }

  /** NaviCubeImplementation::mouseMoved: the whole cube (every face/edge/corner) fades to
   *  InactiveOpacity outside its own square, and back to full while inside it or dragging it. */
  private updateCubeFade(x: number, y: number) {
    const g = this.gizmo as any
    if (!g?._domElement) return
    const r = (g._domElement as HTMLElement).getBoundingClientRect()
    const near = this.cubeActive || (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom)
    const factor = near ? 1 : getState().naviCube.inactiveOpacity / 100 // InactiveOpacity
    if (factor === this.cubeFade) return
    this.cubeFade = factor
    for (const o of (g._intersections ?? []) as THREE.Object3D[]) {
      const m = o as any
      if (m.userData) m.userData.opacity = factor
      if (m.material) m.material.opacity = factor
    }
    // updateAxes: the ShowCS tripod fades with the same factor (axisTr tracks currentOpacity).
    for (const l of this.cubeAxes?.children ?? []) { const mat = (l as any).material; if (mat) mat.opacity = factor }
    this.redraw()
  }
  isCubeDraggable() { return this.cubeDraggable }
  setCubeDraggable(on: boolean) { this.cubeDraggable = on }
  isNaviRotateToNearest() { return this.naviRotateToNearest }
  setNaviRotateToNearest(on: boolean) { this.naviRotateToNearest = on }

  /** Re-applies cubeLayout(pos, ...) to the live gizmo without rebuilding it: writes the
   *  margin three-viewport-gizmo bakes into its DOM element at construction time directly
   *  (confirmed in the library's own bundle: offset only ever becomes a CSS `margin`, nothing
   *  else reads it after that), then goes through the `placement` setter — cheap, a DOM
   *  reposition, not a geometry rebuild — so domUpdate() re-measures it for hit-testing. Mirrors
   *  the result into cubePlace/cubeOffset so navicube.tsx's button box can follow along. */
  private applyCubeLayout(pos: CubePos) {
    const g = this.gizmo as any
    if (!g) return
    const { placement, offset } = cubeLayout(pos, this.host.clientWidth || 1, this.host.clientHeight || 1, getState().naviCube.size)
    const el = g._domElement as HTMLElement | undefined
    if (el) Object.assign(el.style, { marginLeft: `${offset.left}px`, marginRight: `${offset.right}px`, marginTop: `${offset.top}px`, marginBottom: `${offset.bottom}px` })
    if (g.placement !== placement) g.placement = placement
    else g.domUpdate?.()
    const s = getState()
    if (s.cubePlace !== placement || JSON.stringify(s.cubeOffset) !== JSON.stringify(offset)) setState({ cubePlace: placement, cubeOffset: offset })
  }
  /** NaviCube.cpp's MoveNaviCube branch (mouseMoved:1246-1262) together with processSoEvent's
   *  coordinate recentring (1331-1337). mouseMoved computes `dx = x - pressPos[0]` against the
   *  original mouse-down position and adds it onto relPos every event, which looks like it
   *  would accumulate without bound — but x/y are never raw screen coordinates: its only
   *  caller, processSoEvent, recentres them on the cube's own *current* on-screen position
   *  first. Substituting that in and expanding the algebra (posAreaSize/posAreaBase are
   *  constant through a drag), relPos's own previous value cancels out of its update exactly,
   *  leaving a plain "absolute position tracked from the press point":
   *  relPos = relPosAtPress + (rawNow - rawAtPress) / posAreaSize, clamped each axis. Not a
   *  latent bug — a previous pass here read it as one and ported a last-move-to-last-move
   *  incremental delta instead (see fixes2-viewer.md #3 / regress2-viewer.md #4 for the
   *  derivation). This is the literal FreeCAD behaviour, and it has one real, reproducible
   *  consequence an incremental delta doesn't: once the pointer overshoots past a clamped edge
   *  (0 or 1), the formula still measures from the original press point, so the cube has a dead
   *  zone on reversal — it won't budge again until the pointer travels back by the full
   *  overshoot amount. */
  private placeCube(pressPos: CubePos, pressRaw: { x: number; y: number }, rawX: number, rawY: number) {
    const a = cubeArea(this.host.clientWidth || 1, this.host.clientHeight || 1, getState().naviCube.size)
    const next: CubePos = {
      x: Math.min(1, Math.max(0, pressPos.x + (rawX - pressRaw.x) / a.areaW)),
      y: Math.min(1, Math.max(0, pressPos.y + (rawY - pressRaw.y) / a.areaH)),
    }
    setState({ cubePos: next })
    saved.set('cubePos', next)
    this.applyCubeLayout(next)
  }

  private cubeClick: { key: string; t: number } | null = null
  /** The cube's pick under a pointer: the direction of the face, edge or corner. */
  private cubePick(e: PointerEvent): THREE.Vector3 | null {
    const g = this.gizmo as any
    if (!g?._camera || !g._intersections) return null
    const r = (g._domElement as HTMLElement).getBoundingClientRect()
    const ray = new THREE.Raycaster()
    ray.setFromCamera(new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), g._camera)
    const hit = ray.intersectObjects(g._intersections.filter((o: THREE.Object3D) => o.visible), false)[0]
    return hit ? hit.object.position.clone().normalize() : null
  }
  /** NaviCube::mousePressed / mouseMoved / mouseReleased: a drag past 3 px orbits the
   *  model's bounding sphere (sensitivity 0.45), or moves the cube itself with the Movable
   *  Navigation Cube option on; a click turns to the face, edge or corner, to the nearest
   *  roll (NaviRotateToNearest); clicking it twice centres too. */
  private cubePress(e: PointerEvent) {
    const g = this.gizmo as any
    if (!g || e.button !== 0) return
    const el = g._domElement as HTMLElement, start = { x: e.clientX, y: e.clientY }
    const pick = this.cubePick(e)
    if (!pick) return // PickId::None: let the event fall through to ordinary 3D navigation
    e.preventDefault()
    this.cubeActive = true
    // NaviCube.cpp mousePressed:937 (pressPos) and the cube's relPos at that same instant: the
    // whole drag is tracked from these two, not from each move event's own previous position.
    const pressCubePos = getState().cubePos
    let dragging = false, last = start
    // NaviCube.cpp:1170-1178 hasDraggedPastThreshold: std::max(3, round(3 * devicePixelRatio)),
    // so a HiDPI display needs more physical travel than 3 CSS px before a press turns into a drag.
    const dragThreshold = Math.max(3, Math.round(3 * (window.devicePixelRatio || 1)))
    const norm = (x: number, y: number): V2 => {
      const r = el.getBoundingClientRect(), size = Math.min(r.width, r.height) || 1
      return [0.5 + (x - (r.left + r.width / 2)) / size, 0.5 - (y - (r.top + r.height / 2)) / size]
    }
    const move = (ev: PointerEvent) => {
      if (!dragging && (ev.clientX - start.x) ** 2 + (ev.clientY - start.y) ** 2 >= dragThreshold * dragThreshold) {
        dragging = true
        if (!this.cubeDraggable) {
          const box = this.box()
          this.nav.beginOrbitDrag(box ? box.getBoundingSphere(new THREE.Sphere()) : null, 1.05, 0.45)
        }
      }
      if (!dragging) return
      if (this.cubeDraggable) this.placeCube(pressCubePos, start, ev.clientX, ev.clientY)
      else this.nav.updateOrbitDrag(norm(ev.clientX, ev.clientY), norm(last.x, last.y))
      last = { x: ev.clientX, y: ev.clientY }
    }
    const up = (ev: PointerEvent) => {
      removeEventListener('pointermove', move)
      removeEventListener('pointerup', up)
      this.cubeActive = false
      this.updateCubeFade(ev.clientX, ev.clientY)
      if (dragging) { if (!this.cubeDraggable) this.nav.endOrbitDrag(); this.cubeClick = null; return }
      const key = pick.toArray().map(Math.round).join(','), now = performance.now()
      const twice = !!this.cubeClick && this.cubeClick.key === key && now - this.cubeClick.t < 400
      this.cubeClick = twice ? null : { key, t: now }
      const p = this.cameraParts(), std = faceRotation(pick)
      if (!p || !std) return
      const box = this.box(), t = p.controls.target.clone()
      const q = this.naviRotateToNearest ? nearestOrientation(p.cam.quaternion, std, pick) : std
      this.nav.startAnimation(q, t, twice && box ? box.getCenter(new THREE.Vector3()).sub(t) : new THREE.Vector3())
    }
    addEventListener('pointermove', move)
    addEventListener('pointerup', up)
  }

  /** View3DInventorViewer::setEnabledFPSCounter: create/show or hide the label and its
   *  QTimer(250 ms); the measurement itself (addFrametime, in hookRender) keeps running
   *  either way, same as FreeCAD's paintEvent calling it unconditionally. */
  private setShowFPS(on: boolean) {
    if (on) {
      if (!this.fpsEl) {
        this.fpsEl = document.createElement('div')
        Object.assign(this.fpsEl.style, { position: 'absolute', left: '10px', bottom: '5px', pointerEvents: 'none', background: 'transparent' })
        this.host.appendChild(this.fpsEl)
      }
      this.fpsEl.style.display = ''
      if (!this.fpsTimer) this.fpsTimer = setInterval(() => this.updateFPSLabel(), 250)
      this.updateFPSLabel()
    } else {
      if (this.fpsTimer) { clearInterval(this.fpsTimer); this.fpsTimer = null }
      if (this.fpsEl) this.fpsEl.style.display = 'none'
    }
  }

  /** SoQTQuarterAdaptor::addFrametime: exponentially-smoothed (factor 0.7) draw time and
   *  inter-frame gap, in seconds; `drawTime` is this frame's own render duration. */
  private addFrametime(drawTime: number) {
    const FACTOR = 0.7, FIVE_SECS = 5000, now = performance.now() / 1000
    this.fpsDrawTime = drawTime * FACTOR + this.fpsDrawTime * (1 - FACTOR)
    if (this.fpsLastEnd) {
      const frameTime = Math.min(now - this.fpsLastEnd, Math.max(drawTime, FIVE_SECS))
      this.fpsFrameTime = frameTime * FACTOR + this.fpsFrameTime * (1 - FACTOR)
    }
    this.fpsLastEnd = now
  }

  /** View3DInventorViewer::updateFPSLabel: same text FreeCAD shows ("{ms} ms / {fps} fps");
   *  AxisLetterColor (reused for the FPS counter, per its own tooltip) only touched on change.
   *  View3DSettings.cpp:367-368 defaults that same preference to black for the corner-cross
   *  letters, but View3DInventorViewer.cpp:2073 defaults it to yellow specifically for this
   *  label — i.e. both only diverge from the user's own choice until they've actually set one;
   *  `saved` (unlike getState().axisColors, which AXIS_COLOR_DEFAULTS has already backed with
   *  black) still reads undefined at that point. */
  private updateFPSLabel() {
    if (!this.fpsEl) return
    const fps = this.fpsFrameTime > 0 ? 1 / this.fpsFrameTime : 0
    this.fpsEl.textContent = `${(this.fpsDrawTime * 1000).toFixed(1)} ms / ${fps.toFixed(1)} fps`
    const color = saved.get<{ letter?: string }>('axisColors', {}).letter ?? '#ffff00'
    if (color !== this.fpsColor) { this.fpsColor = color; this.fpsEl.style.color = color }
  }

  /** After every frame the viewer draws to the screen, FreeCAD's overlays: the NaviCube and
   *  the coordinate system in the corner. three-cad-viewer's own axes marker (bottom left)
   *  isn't FreeCAD's, so it isn't drawn. */
  private hookRender() {
    if (this.hooked) return
    this.hooked = true
    const r = this.viewer.renderer
    const orig = r.render.bind(r)
    let inside = false
    r.render = (scene: THREE.Scene, camera: THREE.Camera) => {
      if (scene === (this.viewer as any)._rendered?.orientationMarker?.scene) return
      // SoQTQuarterAdaptor::paintEvent: time the whole top-level, on-screen render (including
      // the overlays below), regardless of ShowFPS — only the label's own refresh is gated.
      const fpsStart = performance.now()
      orig(scene, camera)
      if (inside || r.getRenderTarget() !== null) return
      inside = true
      try {
        const corner = getState().corner, cam = this.viewer.camera?.getCamera?.(), ac = getState().axisColors
        if (corner.show && cam) this.cross.render(r, cam, corner.size, ac)
        // Std_AxisCross's big cross (the library's own AxesHelper) rebuilds itself with its
        // own default theme colours on every show(); reapply AxisX/Y/ZColor live here instead.
        try {
          const ah = this.viewer.axesHelper, key = ac.x + ac.y + ac.z
          if (ah && (ah !== this.bigAxesRef || key !== this.bigAxesColorKey)) {
            const rgb = (hex: string) => { const c = new THREE.Color(hex); return [c.r, c.g, c.b] }
            const [rx, ry, rz] = [rgb(ac.x), rgb(ac.y), rgb(ac.z)]
            ah.geometry.setColors(new Float32Array([...rx, ...rx, ...ry, ...ry, ...rz, ...rz]))
            this.bigAxesRef = ah
            this.bigAxesColorKey = key
          }
        } catch { /* not rendered yet */ }
        // SoNaviCube's ShowCS tripod (buildShowCS): same live colours, by the axis tag it set.
        if (this.cubeAxes) {
          const key = ac.x + ac.y + ac.z
          if (key !== this.showCSColorKey) {
            for (const o of this.cubeAxes.children) {
              const axis = (o as any).userData?.axis as 'x' | 'y' | 'z' | undefined, mat = (o as any).material
              if (mat?.color && axis) mat.color.set(ac[axis])
            }
            this.showCSColorKey = key
          }
        }
        if (this.tf) this.placeDragLabels()
        // The view may have been resized since the cube last measured itself, and
        // the cube restores the viewport it saw then. Measure now, and always hand
        // the next frame the whole canvas (else the model draws squeezed and off-centre).
        if (this.gizmo) { this.gizmo.domUpdate(); this.gizmo.render() }
        const size = r.getSize(new THREE.Vector2())
        r.setViewport(0, 0, size.x, size.y)
      } finally {
        inside = false
        this.addFrametime((performance.now() - fpsStart) / 1000)
      }
    }
  }

  // ── Std_ViewLoadImage (CommandView.cpp/ImageView.cpp): an image in the 3D view ──────────────
  /** Sets (or, with null, removes and disposes) the one session-only image plane. FreeCAD opens
   *  the picked file in its own 2D ImageView; this UI has a single 3D view, so the image is a
   *  textured plane dropped into it instead, flat under the model and sized to it. Never written
   *  to the project or to localStorage — gone on reload, same as FreeCAD's ImageView is outside
   *  the document and untouched by undo/redo. */
  setImagePlane(url: string | null) {
    if (this.imagePlane) {
      this.viewer.scene?.remove(this.imagePlane)
      this.imagePlane.geometry.dispose()
      const mat = this.imagePlane.material as THREE.MeshBasicMaterial
      mat.map?.dispose()
      mat.dispose()
      this.imagePlane = null
    }
    if (!url) return
    new THREE.TextureLoader().load(url, (tex) => {
      tex.colorSpace = THREE.SRGBColorSpace
      const aspect = (tex.image?.width || 1) / (tex.image?.height || 1)
      const box = this.box()
      const span = box ? box.getSize(new THREE.Vector3()).length() * 0.6 : 200
      const w = aspect >= 1 ? span : span * aspect, h = aspect >= 1 ? span / aspect : span
      const mesh = new THREE.Mesh(
        new THREE.PlaneGeometry(w, h),
        new THREE.MeshBasicMaterial({ map: tex, side: THREE.DoubleSide, transparent: true }),
      )
      mesh.name = 'Std_ViewLoadImage'
      mesh.userData.cadHelper = true
      const c = box ? box.getCenter(new THREE.Vector3()) : new THREE.Vector3()
      mesh.position.set(c.x, c.y, box ? box.min.z : 0)
      this.imagePlane = mesh
      this.viewer.scene?.add(mesh)
    })
  }

  // ── Std_SceneInspector (SceneInspector.cpp's DlgInspector) ──────────────────────────────────
  /** The scene graph as a plain tree, type + name per node (SceneModel::setNode, for Coin
   *  nodes; here, THREE.Object3D under the viewer's own scene). Everything shows, the model
   *  meshes as well as the gizmo, axis cross and any session helper (clip caps, the image
   *  plane, …) — as Coin's internal nodes all show in FreeCAD's dialog too. */
  sceneTree(): SceneNode {
    const walk = (o: THREE.Object3D): SceneNode =>
      ({ type: o.type || o.constructor.name, name: o.name || '', children: o.children.map(walk) })
    const root = this.viewer.scene as THREE.Object3D | undefined
    return root ? walk(root) : { type: 'Scene', name: '', children: [] }
  }
}

// ── Std_Measure on faces, edges and vertices ──────────────────────────────────
type Sub = ReturnType<CadView['subGeometry']>
export type SubInfo = { kind: string; text: string; points: THREE.Vector3[]; center: THREE.Vector3; normal?: THREE.Vector3; dir?: THREE.Vector3; radius?: number; area?: number; length?: number }
/** Lengths, areas and angles in the user's unit system. */
const qlen = (n: number) => userString({ value: n, dims: [1, 0, 0, 0, 0, 0, 0, 0] }).text
const qarea = (n: number) => userString({ value: n, dims: [2, 0, 0, 0, 0, 0, 0, 0] }).text
const qang = (n: number) => userString({ value: n, dims: [0, 0, 0, 0, 0, 0, 0, 1] }).text

/** What FreeCAD's Measure says about one element: a face's area (and whether it's
 *  planar), an edge's length (a line, or a circle's radius), a vertex's position. */
export function subInfo(g: Sub): SubInfo | null {
  if (!g) return null
  if (g.kind === 'Vertex') return { kind: 'Vertex', text: `(${qlen(g.point.x)}, ${qlen(g.point.y)}, ${qlen(g.point.z)})`, points: [g.point], center: g.point }
  if (g.kind === 'Face') {
    let area = 0
    const c = new THREE.Vector3(), n0 = new THREE.Vector3(), tri = new THREE.Triangle()
    let planar = true
    const pts: THREE.Vector3[] = []
    for (const [a, b, d] of g.tris) {
      tri.set(a, b, d)
      const ar = tri.getArea()
      area += ar
      c.addScaledVector(a.clone().add(b).add(d).divideScalar(3), ar)
      const n = tri.getNormal(new THREE.Vector3())
      if (n0.lengthSq() === 0) n0.copy(n)
      else if (ar > 1e-9 && Math.abs(n.dot(n0)) < 0.9999) planar = false
      pts.push(a, b, d)
    }
    c.divideScalar(area || 1)
    const shape = faceType(g.tris, planar, n0, c)
    if (shape) return { ...shape, text: `area ${qarea(area)}, ${shape.kind === 'Cylinder' || shape.kind === 'Disc' ? `diameter ${qlen(2 * shape.radius!)}` : `radius ${qlen(shape.radius!)}`}`, points: pts, area }
    return { kind: planar ? 'Plane' : 'Face', text: `area ${qarea(area)}${planar ? ', planar' : ''}`, points: pts, center: c, normal: planar ? n0 : undefined, area }
  }
  const pts = g.segs.flat(), len = g.segs.reduce((t, [a, b]) => t + a.distanceTo(b), 0)
  const dir = g.segs[0][1].clone().sub(g.segs[0][0]).normalize()
  const straight = g.segs.every(([a, b]) => Math.abs(b.clone().sub(a).normalize().dot(dir)) > 0.9999)
  const center = pts.reduce((t, p) => t.add(p), new THREE.Vector3()).divideScalar(pts.length)
  if (straight) return { kind: 'Line', text: `length ${qlen(len)}`, points: pts, center, dir, length: len }
  const [p, q, r] = [pts[0], pts[Math.floor(pts.length / 3)], pts[Math.floor((2 * pts.length) / 3)]]
  const ab = q.clone().sub(p), ac = r.clone().sub(p), n = ab.clone().cross(ac)
  if (n.lengthSq() > 1e-12) {
    const cc = p.clone().add(ac.clone().multiplyScalar(ab.lengthSq()).sub(ab.clone().multiplyScalar(ac.lengthSq())).cross(n).divideScalar(2 * n.lengthSq()))
    const rad = cc.distanceTo(p)
    if (pts.every((x) => Math.abs(x.distanceTo(cc) - rad) < rad * 0.01)) return { kind: 'Circle', text: `length ${qlen(len)}, radius ${qlen(rad)}`, points: pts, center: cc, radius: rad, length: len }
  }
  return { kind: 'Curve', text: `length ${qlen(len)}`, points: pts, center, length: len }
}

/** Jacobi eigenvalues/vectors of a symmetric 3x3 matrix, smallest first. */
function eig3(m: number[][]): { values: number[]; vectors: THREE.Vector3[] } {
  const a = m.map((r) => r.slice()), v = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
  for (let sweep = 0; sweep < 50; sweep++) {
    let off = 0
    for (let p = 0; p < 3; p++) for (let q = p + 1; q < 3; q++) off += a[p][q] ** 2
    if (off < 1e-20) break
    for (let p = 0; p < 3; p++) for (let q = p + 1; q < 3; q++) {
      if (Math.abs(a[p][q]) < 1e-30) continue
      const th = (a[q][q] - a[p][p]) / (2 * a[p][q]), t = Math.sign(th || 1) / (Math.abs(th) + Math.sqrt(th * th + 1))
      const c = 1 / Math.sqrt(t * t + 1), s = t * c
      for (let k = 0; k < 3; k++) { const akp = a[k][p], akq = a[k][q]; a[k][p] = c * akp - s * akq; a[k][q] = s * akp + c * akq }
      for (let k = 0; k < 3; k++) { const apk = a[p][k], aqk = a[q][k]; a[p][k] = c * apk - s * aqk; a[q][k] = s * apk + c * aqk }
      for (let k = 0; k < 3; k++) { const vkp = v[k][p], vkq = v[k][q]; v[k][p] = c * vkp - s * vkq; v[k][q] = s * vkp + c * vkq }
    }
  }
  return [0, 1, 2].map((i) => ({ value: a[i][i], vector: new THREE.Vector3(v[0][i], v[1][i], v[2][i]) }))
    .sort((x, y) => x.value - y.value).reduce((o, e) => { o.values.push(e.value); o.vectors.push(e.vector); return o }, { values: [] as number[], vectors: [] as THREE.Vector3[] })
}
/** Least squares for a small dense system (normal equations by Gauss elimination). */
function lsq(rows: number[][], rhs: number[]): number[] | null {
  const n = rows[0].length, A = Array.from({ length: n }, () => new Array(n + 1).fill(0))
  rows.forEach((r, k) => { for (let i = 0; i < n; i++) { for (let j = 0; j < n; j++) A[i][j] += r[i] * r[j]; A[i][n] += r[i] * rhs[k] } })
  for (let i = 0; i < n; i++) {
    let p = i
    for (let r = i + 1; r < n; r++) if (Math.abs(A[r][i]) > Math.abs(A[p][i])) p = r
    if (Math.abs(A[p][i]) < 1e-12) return null
    ;[A[i], A[p]] = [A[p], A[i]]
    for (let r = 0; r < n; r++) if (r !== i) { const f = A[r][i] / A[i][i]; for (let c = i; c <= n; c++) A[r][c] -= f * A[i][c] }
  }
  return A.map((r, i) => r[n] / r[i])
}
/** Measurement::findType for a face, from its triangles: a plane bounded by one circle is a
 *  Disc; a surface whose normals all lie across one axis and whose points sit at one distance
 *  from it is a Cylinder (a full turn) or a CylinderSection; points at one distance from a
 *  centre make a Sphere. Anything else stays a plane or a free face. */
function faceType(tris: THREE.Vector3[][], planar: boolean, n0: THREE.Vector3, centroid: THREE.Vector3): Pick<SubInfo, 'kind' | 'center' | 'radius' | 'dir' | 'normal'> | null {
  const key = (p: THREE.Vector3) => `${p.x.toFixed(5)},${p.y.toFixed(5)},${p.z.toFixed(5)}`
  const uniq = new Map<string, THREE.Vector3>()
  for (const t of tris) for (const p of t) uniq.set(key(p), p)
  const pts = [...uniq.values()]
  if (pts.length < 4) return null
  const tol = 0.01
  if (planar) {
    // A disc: the face's outline (edges used by one triangle) is one loop, all at one radius.
    const count = new Map<string, number>()
    for (const t of tris) for (let i = 0; i < 3; i++) { const a = key(t[i]), b = key(t[(i + 1) % 3]), e = a < b ? `${a}|${b}` : `${b}|${a}`; count.set(e, (count.get(e) ?? 0) + 1) }
    const bound = [...count].filter(([, c]) => c === 1).map(([e]) => e.split('|'))
    if (bound.length < 6) return null
    const parent = new Map<string, string>(), find = (x: string): string => { while (parent.get(x) !== x) x = parent.get(x)!; return x }
    for (const [a, b] of bound) { if (!parent.has(a)) parent.set(a, a); if (!parent.has(b)) parent.set(b, b); parent.set(find(a), find(b)) }
    if (new Set([...parent.keys()].map(find)).size !== 1) return null
    const ring = [...parent.keys()].map((k) => uniq.get(k)!)
    const r = ring.reduce((t, p) => t + p.distanceTo(centroid), 0) / ring.length
    if (r <= 0 || ring.some((p) => Math.abs(p.distanceTo(centroid) - r) > tol * r)) return null
    return { kind: 'Disc', center: centroid.clone(), radius: r, normal: n0.clone(), dir: n0.clone() }
  }
  // The normals' spread: a cylinder's lie across its axis (one eigenvalue near zero).
  const M = [[0, 0, 0], [0, 0, 0], [0, 0, 0]], tri = new THREE.Triangle(), nrm = new THREE.Vector3()
  for (const t of tris) {
    tri.set(t[0], t[1], t[2]); const w = tri.getArea(); if (w <= 0) continue
    tri.getNormal(nrm)
    const n = [nrm.x, nrm.y, nrm.z]
    for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) M[i][j] += w * n[i] * n[j]
  }
  const { values, vectors } = eig3(M), trace = values[0] + values[1] + values[2]
  if (trace > 0 && values[0] < 1e-4 * trace && values[1] > 0.05 * trace) {
    const a = vectors[0].normalize(), u = new THREE.Vector3(1, 0, 0)
    if (Math.abs(a.dot(u)) > 0.9) u.set(0, 1, 0)
    u.sub(a.clone().multiplyScalar(u.dot(a))).normalize()
    const v = a.clone().cross(u)
    const xy = pts.map((p) => [p.dot(u), p.dot(v)])
    const sol = lsq(xy.map(([x, y]) => [x, y, 1]), xy.map(([x, y]) => x * x + y * y))
    if (sol) {
      const cx = sol[0] / 2, cy = sol[1] / 2, r = Math.sqrt(sol[2] + cx * cx + cy * cy)
      if (r > 0 && xy.every(([x, y]) => Math.abs(Math.hypot(x - cx, y - cy) - r) <= tol * r)) {
        // A full turn (IsUClosed): no angular gap much wider than the tessellation's step.
        const ang = xy.map(([x, y]) => Math.atan2(y - cy, x - cx)).sort((p, q) => p - q)
        const gaps = ang.map((t, i) => (i ? t - ang[i - 1] : t + 2 * Math.PI - ang[ang.length - 1])).sort((p, q) => p - q)
        const full = gaps[gaps.length - 1] < 3 * Math.max(gaps[Math.floor(gaps.length / 2)], 1e-6) && gaps[gaps.length - 1] < Math.PI / 2
        const h = pts.reduce((t, p) => t + p.dot(a), 0) / pts.length
        const center = u.clone().multiplyScalar(cx).add(v.clone().multiplyScalar(cy)).add(a.clone().multiplyScalar(h))
        return { kind: full ? 'Cylinder' : 'CylinderSection', center, radius: r, dir: a.clone() }
      }
    }
  }
  // A sphere: |p|² = 2c·p + k.
  const s = lsq(pts.map((p) => [p.x, p.y, p.z, 1]), pts.map((p) => p.lengthSq()))
  if (s) {
    const c = new THREE.Vector3(s[0] / 2, s[1] / 2, s[2] / 2), r = Math.sqrt(s[3] + c.lengthSq())
    if (r > 0 && pts.every((p) => Math.abs(p.distanceTo(c) - r) <= tol * r)) return { kind: 'Sphere', center: c, radius: r }
  }
  return null
}

/** Two elements: an angle when both have a direction, else the minimum distance and where. */
export function measurePair(a: SubInfo, b: SubInfo): { text: string; line: THREE.Vector3[] | null } {
  const ax = a.normal ?? a.dir, bx = b.normal ?? b.dir
  const parts: string[] = []
  if (ax && bx) {
    const ang = THREE.MathUtils.radToDeg(Math.acos(Math.min(1, Math.abs(ax.dot(bx)))))
    parts.push(`angle ${qang(a.normal && b.normal ? ang : a.dir && b.dir ? ang : 90 - ang)}`)
  }
  let best = Infinity, pa = a.center, pb = b.center
  const A = a.points.length > 4000 ? a.points.filter((_, i) => i % Math.ceil(a.points.length / 4000) === 0) : a.points
  const B = b.points.length > 4000 ? b.points.filter((_, i) => i % Math.ceil(b.points.length / 4000) === 0) : b.points
  for (const p of A) for (const q of B) { const d = p.distanceToSquared(q); if (d < best) { best = d; pa = p; pb = q } }
  if (a.normal && b.normal && Math.abs(a.normal.dot(b.normal)) > 0.9999) {
    parts.push(`distance ${qlen(Math.abs(b.center.clone().sub(a.center).dot(a.normal)))} (parallel planes)`)
  } else if (a.kind === 'Vertex' && b.normal) {
    parts.push(`distance to the plane ${qlen(Math.abs(a.center.clone().sub(b.center).dot(b.normal)))}`)
  } else if (b.kind === 'Vertex' && a.normal) {
    parts.push(`distance to the plane ${qlen(Math.abs(b.center.clone().sub(a.center).dot(a.normal)))}`)
  } else parts.push(`minimum distance ${qlen(Math.sqrt(best))}`)
  return { text: parts.join(', '), line: [pa, pb] }
}

/** QuickMeasure (Measure/Gui/QuickMeasure.cpp): what the status bar says about the selected
 *  elements, by FreeCAD's measurement types. Whole objects give nothing (FreeCAD turned
 *  volumes off there for speed). */
export function quickMeasure(infos: SubInfo[]): string {
  const len = (n: number) => userString({ value: n, dims: [1, 0, 0, 0, 0, 0, 0, 0] }).text
  // areaStr: the area's user string with its exponent as a superscript (mm²).
  const area = (n: number) => toUnicodeSuperscript(userString({ value: n, dims: [2, 0, 0, 0, 0, 0, 0, 0] }).text)
  const ang = (n: number) => userString({ value: n, dims: [0, 0, 0, 0, 0, 0, 0, 1] }).text
  const FACE_KINDS = ['Plane', 'Face', 'Disc', 'Cylinder', 'CylinderSection', 'Sphere']
  const faces = infos.filter((i) => FACE_KINDS.includes(i.kind))
  const cyl = (i: SubInfo) => i.kind === 'Cylinder' || i.kind === 'CylinderSection'
  /** gp_Lin::Distance between two axes (parallel: their spacing; skew: the common normal). */
  const axisDistance = (p1: THREE.Vector3, d1: THREE.Vector3, p2: THREE.Vector3, d2: THREE.Vector3) => {
    const w = p2.clone().sub(p1), n = d1.clone().cross(d2)
    return n.lengthSq() < 1e-18 ? w.clone().sub(d1.clone().multiplyScalar(w.dot(d1))).length() : Math.abs(w.dot(n.normalize()))
  }
  const edges = infos.filter((i) => i.kind === 'Line' || i.kind === 'Circle' || i.kind === 'Curve')
  const verts = infos.filter((i) => i.kind === 'Vertex')
  const areaOf = (i: SubInfo) => i.area ?? 0, lengthOf = (i: SubInfo) => i.length ?? 0
  const full = (c: SubInfo) => c.kind === 'Circle' && c.radius !== undefined && Math.abs(lengthOf(c) - 2 * Math.PI * c.radius) < 0.02 * lengthOf(c)
  const minDist = (a: SubInfo, b: SubInfo) => { let best = Infinity; for (const p of a.points) for (const q of b.points) best = Math.min(best, p.distanceToSquared(q)); return Math.sqrt(best) }
  if (!infos.length || faces.length + edges.length + verts.length !== infos.length) return ''
  if (faces.length === infos.length) {
    if (faces.length === 2 && faces.every((f) => f.normal) && Math.abs(faces[0].normal!.dot(faces[1].normal!)) > 0.9999) {
      const nominal = `Nominal distance: ${len(Math.abs(faces[1].center.clone().sub(faces[0].center).dot(faces[0].normal!)))}`
      if (faces.every((f) => f.kind === 'Disc')) return `${nominal}, Axis distance: ${len(axisDistance(faces[0].center, faces[0].normal!, faces[1].center, faces[1].normal!))}` // TwoDiscs
      return nominal // TwoPlanes
    }
    if (faces.length === 2 && faces.every(cyl)) { // TwoCylinders
      const [a, b] = faces, angle = THREE.MathUtils.radToDeg(Math.acos(Math.min(1, Math.abs(a.dir!.dot(b.dir!)))))
      const head = `Total area: ${area(areaOf(a) + areaOf(b))}, Axis distance: ${len(axisDistance(a.center, a.dir!, b.center, b.dir!))}`
      return angle <= 1e-7 ? head : `${head}, Axis angle: ${ang(angle)}`
    }
    if (faces.length === 1) {
      const f = faces[0]
      if (f.kind === 'Cylinder' || f.kind === 'Disc') return `Area: ${area(areaOf(f))}, Diameter: ${len(2 * f.radius!)}`
      if (f.kind === 'CylinderSection' || f.kind === 'Sphere') return `Area: ${area(areaOf(f))}, Radius: ${len(f.radius!)}`
      return `Area: ${area(areaOf(f))}` // Plane, Cone
    }
    return `Total area: ${area(faces.reduce((t, f) => t + areaOf(f), 0))}` // Surfaces
  }
  if (edges.length === infos.length) {
    if (edges.length === 1) {
      const e = edges[0]
      if (e.kind === 'Line') return `Length: ${len(lengthOf(e))}`
      if (e.kind === 'Circle') return full(e) ? `Diameter: ${len(2 * e.radius!)}` : `Radius: ${len(e.radius!)}` // Circle, CircleArc
      return `Total length: ${len(lengthOf(e))}`
    }
    if (edges.length === 2 && edges.every((e) => e.kind === 'Line')) {
      const [a, b] = edges, cos = Math.abs(a.dir!.dot(b.dir!))
      if (cos > 0.9999) { // TwoParallelLines: the distance between the lines
        const d = b.center.clone().sub(a.center), off = d.clone().sub(a.dir!.clone().multiplyScalar(d.dot(a.dir!)))
        return `Nominal distance: ${len(off.length())}`
      }
      return `Angle: ${ang(THREE.MathUtils.radToDeg(Math.acos(Math.min(1, cos))))}, Total length: ${len(lengthOf(a) + lengthOf(b))}` // TwoLines
    }
    return `Total length: ${len(edges.reduce((t, e) => t + lengthOf(e), 0))}` // Edges
  }
  if (verts.length === 2 && infos.length === 2) return `Distance: ${len(verts[0].center.distanceTo(verts[1].center))}` // PointToPoint
  if (verts.length === 1 && infos.length === 2) {
    const v = verts[0], o = infos.find((i) => i !== v)!
    if (o.kind === 'Circle' && full(o)) return `Minimum distance: ${len(minDist(v, o))}, Center distance: ${len(v.center.distanceTo(o.center))}` // PointToCircle
    if (o.kind === 'Plane' || o.kind === 'Disc') return `Minimum distance: ${len(Math.abs(v.center.clone().sub(o.center).dot(o.normal!)))}` // PointToSurface
    if (cyl(o)) { // PointToCylinder: the distance to the axis too
      const w = v.center.clone().sub(o.center), off = w.clone().sub(o.dir!.clone().multiplyScalar(w.dot(o.dir!))).length()
      return `Minimum distance: ${len(Math.abs(off - o.radius!))}, Axis distance: ${len(off)}`
    }
    return `Minimum distance: ${len(minDist(v, o))}` // PointToEdge, PointToSurface
  }
  return ''
}

/** Does segment p-q touch the box? (Liang–Barsky clipping.) */
function segBox(p: { x: number; y: number }, q: { x: number; y: number }, x0: number, y0: number, x1: number, y1: number) {
  let t0 = 0, t1 = 1
  const dx = q.x - p.x, dy = q.y - p.y
  for (const [pp, qq] of [[-dx, p.x - x0], [dx, x1 - p.x], [-dy, p.y - y0], [dy, y1 - p.y]]) {
    if (pp === 0) { if (qq < 0) return false; continue }
    const t = qq / pp
    if (pp < 0) { if (t > t1) return false; if (t > t0) t0 = t }
    else { if (t < t0) return false; if (t < t1) t1 = t }
  }
  return true
}

/** Whether (x, y) is inside triangle a-b-c (Polygon2d::Contains for one triangle). */
function pointInTri(x: number, y: number, a: { x: number; y: number }, b: { x: number; y: number }, c: { x: number; y: number }) {
  const side = (p: { x: number; y: number }, q: { x: number; y: number }) => (x - q.x) * (p.y - q.y) - (p.x - q.x) * (y - q.y)
  const d1 = side(a, b), d2 = side(b, c), d3 = side(c, a)
  const neg = d1 < 0 || d2 < 0 || d3 < 0, pos = d1 > 0 || d2 > 0 || d3 > 0
  return !(neg && pos)
}

// ── the NaviCube's orientations (NaviCube.cpp) ───────────────────────────────
const V = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z)
/** getFaceRotation: per face, edge and corner (by its direction), the screen's x and
 *  the roll: makeFaceRotation(x, z, rotZ). */
const FACES: Record<string, [THREE.Vector3, number]> = {
  '0,0,1': [V(1, 0, 0), 0], '0,-1,0': [V(1, 0, 0), 0], '-1,0,0': [V(0, -1, 0), 0], '0,1,0': [V(-1, 0, 0), 0], '1,0,0': [V(0, 1, 0), 0], '0,0,-1': [V(1, 0, 0), 0],
  '1,-1,1': [V(-1, -1, 0), Math.PI], '-1,-1,1': [V(-1, 1, 0), Math.PI], '1,-1,-1': [V(1, 1, 0), 0], '-1,-1,-1': [V(1, -1, 0), 0],
  '1,1,1': [V(1, -1, 0), Math.PI], '-1,1,1': [V(1, 1, 0), Math.PI], '1,1,-1': [V(-1, 1, 0), 0], '-1,1,-1': [V(-1, -1, 0), 0],
  '0,-1,1': [V(1, 0, 0), 0], '0,-1,-1': [V(1, 0, 0), 0], '0,1,-1': [V(1, 0, 0), Math.PI], '0,1,1': [V(1, 0, 0), Math.PI],
  '1,1,0': [V(0, 0, 1), Math.PI / 2], '1,-1,0': [V(0, 0, 1), Math.PI / 2], '-1,-1,0': [V(0, 0, 1), Math.PI / 2], '-1,1,0': [V(0, 0, 1), Math.PI / 2],
  '-1,0,1': [V(0, 1, 0), Math.PI], '1,0,1': [V(0, 1, 0), 0], '1,0,-1': [V(0, 1, 0), 0], '-1,0,-1': [V(0, 1, 0), Math.PI],
}
/** makeFaceRotation: the camera looks along -z, with x to the right, rolled by rotZ. */
function faceRotation(dir: THREE.Vector3): THREE.Quaternion | null {
  const key = [dir.x, dir.y, dir.z].map((n) => (Math.abs(n) < 0.3 ? 0 : Math.sign(n))).join(',')
  const f = FACES[key]
  if (!f) return null
  const z = V(...(key.split(',').map(Number) as [number, number, number])).normalize(), x = f[0].clone().normalize()
  const y = x.clone().cross(z.clone().negate()).normalize()
  const c = Math.cos(f[1]), s = Math.sin(f[1])
  const X = x.clone().multiplyScalar(c).addScaledVector(y, -s), Y = x.clone().multiplyScalar(s).addScaledVector(y, c)
  return new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(X, Y, z))
}
/** getNearestOrientation: the face's view with the roll nearest the camera's, in steps
 *  of 90° (60° for a corner). */
function nearestOrientation(cam: THREE.Quaternion, std: THREE.Quaternion, dir: THREE.Vector3): THREE.Quaternion {
  const cz = V(0, 0, 1).applyQuaternion(cam), sz = V(0, 0, 1).applyQuaternion(std)
  for (const k of ['x', 'y', 'z'] as const) if (Math.abs(sz[k]) < 1e-6) sz[k] = 0
  sz.normalize()
  const inter = new THREE.Quaternion().setFromUnitVectors(cz.normalize(), sz).multiply(cam)
  const r = std.clone().multiply(inter.clone().invert())
  const w = Math.min(1, Math.max(-1, r.w)), sn = Math.sqrt(1 - w * w)
  const axis = sn < 1e-9 ? sz.clone() : V(r.x / sn, r.y / sn, r.z / sn)
  let angle = 2 * Math.acos(w)
  if (sz.dot(axis) < 0) angle = -angle
  if (angle < 0) angle += 2 * Math.PI
  const pi = Math.PI, f = 1e-5
  const corner = [dir.x, dir.y, dir.z].every((n) => Math.abs(n) > 0.3)
  if (corner) {
    angle = angle <= pi / 6 + f ? 0 : angle <= pi / 2 + f ? pi / 3 : angle < (5 * pi) / 6 - f ? (2 * pi) / 3 : angle <= pi + pi / 6 + f ? pi
      : angle < pi + pi / 2 - f ? pi + pi / 3 : angle < pi + (5 * pi) / 6 - f ? pi + (2 * pi) / 3 : 0
  } else {
    angle = angle <= pi / 4 + f ? 0 : angle <= (3 * pi) / 4 + f ? pi / 2 : angle < pi + pi / 4 - f ? pi : angle < pi + (3 * pi) / 4 - f ? pi + pi / 2 : 0
  }
  return new THREE.Quaternion().setFromAxisAngle(sz, angle).invert().multiply(std)
}

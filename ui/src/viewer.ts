// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Gui/View3DSettings.cpp: 2023 Werner Mayer
//   src/Gui/NaviCube.cpp: 2017 Kustaa Nyholm; 2026 Joao Matos
//   src/Gui/Inventor/SoNaviCube.cpp: 2025-2026 Joao Matos
//   src/Gui/View3DInventorViewer.cpp: 2004 Jürgen Riegel; 2026 Joao Matos
//   src/Gui/Camera.cpp: 2023 Werner Mayer
//   src/Gui/SceneInspector.cpp: 2008 Werner Mayer
//   src/Mod/Measure/App/Preferences.cpp: 2023 WandererFan
//   src/Mod/Measure/Gui/ViewProviderMeasureAngle.cpp: 2023 David Friedli; 2013 Thomas Anderson
//   src/Mod/Measure/Gui/ViewProviderMeasureBase.cpp: 2023 David Friedli
//   src/Mod/Measure/Gui/ViewProviderMeasureDistance.cpp: 2023 David Friedli; 2013 Thomas Anderson; 2008 Werner Mayer
//   src/Gui/View3DPy.cpp: 2002 Jürgen Riegel
//   src/Gui/CommandView.cpp: 2002 Jürgen Riegel
//   src/Gui/ImageView.cpp: 2023 Werner Mayer
//   src/Mod/Measure/Gui/QuickMeasure.cpp: 2023 Pierre-Louis Boyer
//   src/Mod/Measure/App/Measurement.cpp: 2013 Luke Parry
//   src/Mod/Part/App/PartFeature.cpp: 2002 Jürgen Riegel
//   src/App/GeoFeature.cpp: 2002 Jürgen Riegel
//   src/Base/Rotation.cpp: 2006 Werner Mayer
//   src/Mod/Part/Gui/SoBrepFaceSet.cpp: 2011 Werner Mayer; 2026 Joao Matos
//   src/Gui/View3DInventorSelection.cpp: 2022 Zheng Lei (realthunder)
import * as THREE from 'three'
import { Display, Viewer, decodeInstancedFormat } from 'three-cad-viewer'
import { TransformControls } from 'three/addons/controls/TransformControls.js'
import { Line2 } from 'three/addons/lines/Line2.js'
import { LineGeometry } from 'three/addons/lines/LineGeometry.js'
import { LineMaterial } from 'three/addons/lines/LineMaterial.js'
import { LineSegments2 } from 'three/addons/lines/LineSegments2.js'
import { LineSegmentsGeometry } from 'three/addons/lines/LineSegmentsGeometry.js'
import { NaviCubeGL } from './navicube3d'
import { Navigation, bindNavigation, type NavEvent, type NavPrefs, type V2 } from './nav'
import { doubleClickInterval } from './dblclick'
import { AxisCross } from './axiscross'
import { toNumber, userString } from './quantity'
import { placementMatrix } from './placement'
import { poseOffsets } from './poses'

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
import type { Body, Scene, Vec3 } from './api'
import { getState, saved, setState, subscribe, viewOf, type Clip, type Corner, type CubeOffset, type CubePlace, type CubePos, type DrawStyle, type HomeView, type NaviCubePrefs, type NavStyle, type ViewProps, type SelPrefs } from './store'
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
/** NaviCube.cpp's OffsetX/OffsetY: View3DSettings.cpp:607-609 reads them with a default of 0, and nothing
 *  here sets them. */
const CUBE_OFFSET = 0

/** NaviCubeImplementation::handleResize (NaviCube.cpp:887-898): the travel area's base is OffsetX/Y plus 0.55 of the cube's size
 *  (cast to int), no more than half the view; its size is what is left between the two bases. In CSS px (FreeCAD's are the
 *  widget's physical ones, cubeWidgetSize times the devicePixelRatio, which comes to the same). */
function cubeArea(w: number, h: number, size: number) {
  const bx = Math.min(Math.trunc(CUBE_OFFSET + size * 0.55), Math.trunc(w / 2))
  const by = Math.min(Math.trunc(CUBE_OFFSET + size * 0.55), Math.trunc(h / 2))
  return { left: bx, right: bx, top: by, bottom: by, areaW: Math.max(1, w - 2 * bx), areaH: Math.max(1, h - 2 * by) }
}
/** NaviCubeImplementation::syncNodeState (NaviCube.cpp:461-466): the cube's square, cubeWidgetSize across, at
 *  posX = int(relPos.x * posAreaSize.x) + posAreaBase.x - size / 2 and the same in y, which Coin counts from the bottom (relPos.y 1
 *  is the top; CubePos.y 0 is). `offset` is the square's distance from each edge of the view, `placement` the third of the view it
 *  is in (what the Preferences page's corner keeps). */
export function cubeLayout(pos: CubePos, w: number, h: number, size: number): { placement: CubePlace; offset: CubeOffset } {
  const a = cubeArea(w, h, size), half = Math.trunc(size / 2)
  const left = Math.trunc(pos.x * a.areaW) + a.left - half
  const bottom = Math.trunc((1 - pos.y) * a.areaH) + a.bottom - half
  const top = h - bottom - size, cx = left + size / 2, cy = top + size / 2
  const hz = cx < w / 3 ? 'left' : cx > (2 * w) / 3 ? 'right' : 'center'
  const vz = cy < h / 3 ? 'top' : cy > (2 * h) / 3 ? 'bottom' : 'center'
  return { placement: `${vz}-${hz}` as CubePlace, offset: { left, top, right: w - left - size, bottom } }
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

/** Preferences > Selection: SelectionColor / HighlightColor, or none while EnableSelection /
 *  EnablePreselection is off (View3DSettings' SoFCEnableSelectionAction / SoFCEnablePreselectionAction
 *  stop the highlighting). */
const selColor = () => { const p = getState().selPrefs; return p.enable ? new THREE.Color(p.color).getHex() : null }
/** The intensity of a selected object's emissive colour (see applyTints): 2 reproduces Coin's saturated sum with three's linear one. */
const SELECTED_EMISSIVE = 2
const preColor = () => { const p = getState().selPrefs; return p.enablePre ? new THREE.Color(p.preColor).getHex() : null }

const R2 = Math.SQRT1_2
/** FreeCAD's standard view rotations (src/Gui/Camera.cpp; x, y, z, w). */
const ROTATION: Record<ViewDir, [number, number, number, number]> = {
  top: [0, 0, 0, 1], bottom: [1, 0, 0, 0], front: [R2, 0, 0, R2], rear: [0, R2, R2, 0],
  right: [0.5, 0.5, 0.5, 0.5], left: [-0.5, 0.5, 0.5, -0.5], iso: [0.424708, 0.17592, 0.339851, 0.820473],
  dimetric: [0.567952, 0.103751, 0.146726, 0.803205], trimetric: [0.446015, 0.119509, 0.229575, 0.856787],
}
const TRIMETRIC = ROTATION.trimetric
const HOME_DIR: Record<Exclude<HomeView, 'Custom'>, ViewDir> = {
  Isometric: 'iso', Dimetric: 'dimetric', Trimetric: 'trimetric', Top: 'top', Front: 'front', Left: 'left', Right: 'right', Rear: 'rear', Bottom: 'bottom',
}
/** Camera::defaultOrientation(fallback) (Camera.cpp:128-180): the NewDocumentCameraOrientation parameter's rotation, or `fallback`'s
 *  while it is unset. "Custom" is View/Custom's Q0..Q3 (x, y, z, w; 0, 0, 0, 1 where unset) as float32, which SbRotation::setValue
 *  normalizes (measured in FreeCAD 26.3: (1, 1, 0, 0) is (0.7071, 0.7071, 0, 0), and the sign of w is kept). All four zero, which
 *  Coin keeps as a zero quaternion and draws as the Top view, is the Top view's unit quaternion here. */
export function defaultOrientation(fallback: Exclude<HomeView, 'Custom'>): [number, number, number, number] {
  const s = getState(), v = s.homeView ?? fallback
  if (v !== 'Custom') return ROTATION[HOME_DIR[v]]
  const f = Math.fround, q = (s.customCamera ?? [0, 0, 0, 1]).map(f)
  const len = f(Math.sqrt(f(f(f(q[0] * q[0]) + f(q[1] * q[1])) + f(f(q[2] * q[2]) + f(q[3] * q[3])))))
  return len > 0 ? q.map((x) => f(x / len)) as [number, number, number, number] : [0, 0, 0, 1]
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

/** The Sketcher's edit mode (sketcher.ts): while it is set, the 3D view's events go to it first, as Coin hands them to
 *  the view provider in edit (ViewProviderSketch's mouseButtonPressed, mouseMove, keyPressed), and it draws its overlay
 *  after every frame. */
export type SketchHook = {
  event(ev: NavEvent): boolean
  key(e: KeyboardEvent, down: boolean): boolean
  draw(ctx: CanvasRenderingContext2D, vp: { cam: THREE.Camera; w: number; h: number; hole: { x: number; y: number; w: number; h: number } | null; target: THREE.Vector3 }): void
  /** The right click's menu: the Sketcher's own, or none while a tool runs. */
  popup(): 'sketch' | 'none'
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
/** ViewProviderMeasure::getTextPosition (ViewProviderMeasureBase.cpp:769-788): the generic
 *  view providers' (Length/Position/Diameter/Radius/Area/Geometric Center) own label offset —
 *  a literal SbVec2s(30.0, 30.0) (line 784), screen pixels up-and-right of the anchor (Coin viewport space has
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
  /** The NaviCube (navicube3d.ts's SoNaviCube port), and the square of the view it is drawn in, which takes its presses. */
  private gizmo: NaviCubeGL | null = null
  private cubeEl: HTMLDivElement | null = null
  private cross = new AxisCross()
  private rendered = false
  private meshes = new Map<string, THREE.Mesh[]>() // each part's faces (front and back meshes)
  private edges = new Map<string, THREE.Object3D[]>() // and its edge lines
  private verts = new Map<string, THREE.Points[]>() // and its vertices
  private overlays: THREE.Object3D[] = []
  /** three-cad-viewer numbers faces, then edges, then vertices in one run; FreeCAD
   *  numbers each from 1. These are the offsets per part. */
  private bases = new Map<string, { Face: number; Edge: number; Vertex: number }>()
  /** Per body, its curved faces' alignment directions (Body.curved) and the inverse of its faces' world matrix when the scene was
   *  drawn, which is where scene.json's directions are: a pose or a drag since moves the group, and the directions with it. */
  private curved = new Map<string, { faces: NonNullable<Body['curved']>; home: THREE.Matrix4 }>()
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
  /** mouseDown, for the opacity fade: true for the whole life of a cube press. */
  private cubeActive = false
  /** AxisXColor/Y/Z live on the library's own AxesHelper (Std_AxisCross) and on the NaviCube's
   *  ShowCS tripod too; cached (and, for the former, keyed to the helper instance, since the
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
  private sketchHook: SketchHook | null = null
  private sketchCanvas: HTMLCanvasElement | null = null
  /** The Sketcher's context menu (ViewProviderSketch::generateContextMenu), shown by panels.tsx. */
  onSketchMenu: ((x: number, y: number) => void) | null = null

  constructor(private host: HTMLElement, private on: Handlers) {
    host.replaceChildren()            // a remount (hot reload) must not stack a second viewer
    this.display = new Display(host, {
      cadWidth: host.clientWidth || 800, height: host.clientHeight || 600,
      treeWidth: 0, glass: true, tools: false, theme: 'light', pinning: false,
    } as any)
    this.viewer = new Viewer(this.display, { up: 'Z', ...ORBIT } as any, () => {})
    // three-cad-viewer keeps keyboard shortcuts of its own on its container (its "2" is its own bottom preset) and stops
    // the key there, so FreeCAD's 0-6 never reached Std_View*: `2` in the top view showed the bottom, `1` did nothing.
    // The workbench's keymap owns the keyboard, so the library's listener comes off.
    const d = this.display as any
    if (d.container && d._handleKeyboardShortcut) d.container.removeEventListener('keydown', d._handleKeyboardShortcut)
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
      // (a sketch in edit counts as one: its presses are the Sketcher's, which keeps no long press for Clarify Selection —
      // the Sketcher takes the release, so the long press's timer would open the menu over a tool's next click)
      draggerUnderCursor: () => !!this.sketchHook || this.tcs.some((tc) => (tc as any).axis),
      scene: (ev) => this.sceneEvent(ev),
      clearSelection: () => this.on.pick(null, false, null),
      // openPopupMenu: the last-preselected object, not a fresh pick at the click point.
      popup: (pos) => {
        const c = this.client(pos)
        if (this.sketchHook) { if (this.sketchHook.popup() === 'sketch') this.onSketchMenu?.(c.x, c.y); return }
        const label = this.labelMenu ? this.helperAt(c) : null
        if (label?.startsWith('spacing:') && this.labelMenu?.(label, c.x, c.y)) return
        this.on.menu?.(c.x, c.y, getState().preselected ?? this.hitAt(c)?.body ?? null)
      },
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
    // NaviCube.cpp's mouseMoved hovering test and its hilite: at the window level, since the buttons
    // over the cube (navicube.tsx) are the elements under the pointer there, not the cube's square.
    const cubeFade = (e: PointerEvent) => this.updateCubeFade(e.clientX, e.clientY)
    addEventListener('pointermove', cubeFade)
    this.cleanup.push(() => removeEventListener('pointermove', cubeFade))
    this.cleanup.push(bindNavigation(this.nav, host, (t) => t === this.viewer.renderer?.domElement,
      () => this.viewer.renderer?.domElement ?? null, () => this.tcs.some((tc) => (tc as any).axis)))
    add('dblclick', (e) => {
      if (this.sketchHook) return // the Sketcher times its own double clicks (ViewProviderSketch's DoubleClick)
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
    this.endCubePress?.()
    this.cleanup.forEach((f) => f())
    this.gizmo?.dispose()
    this.cubeEl?.remove()
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
    // An empty project's scene has no bounding box (bb: null), and three-cad-viewer sizes its grid,
    // axes and camera from it, which then come out NaN. A new FreeCAD document is framed by
    // NewDocumentCameraScale (100 mm), so give the empty scene that much room around the origin.
    const data = sc.viewer as any
    const shown = data?.shapes && !data.shapes.bb
      ? { ...data, shapes: { ...data.shapes, bb: { xmin: -50, xmax: 50, ymin: -50, ymax: 50, zmin: -50, zmax: 50 } } } : data
    this.viewer.render(decodeInstancedFormat(shown), RENDER, { up: 'Z', ...ORBIT, ortho: getState().ortho, ...(cam ?? {}) })
    this.rendered = true
    // three-cad-viewer gives the new camera the position, orientation, target and zoom of the old one, and its own up (z): the up
    // is the orientation's y axis here, as everything that turns the camera keeps it (a recalled view, a lookAt, reads it).
    { const now = this.cameraParts(); if (cam && now) now.cam.up.set(0, 1, 0).applyQuaternion(now.cam.quaternion) }
    this.applyBackground(getState().background)
    this.applyLights(getState().lights)
    this.index(sc)
    // The groups of the scene before are gone with it, and so is what they were moved from: the pose stands again.
    this.posed.clear()
    this.setPose(getState().pose ? poseOffsets(sc, getState().pose!) : null)
    // The viewer settles its own size a frame or two after render; fit after it.
    this.fit()
    requestAnimationFrame(() => requestAnimationFrame(() => this.fit()))
    setTimeout(() => this.fit(), 300)
    // A new view looks along the default camera orientation (viewDefaultOrientation), fitted.
    if (!cam) {
      this.viewer.presetCamera('iso')
      this.jumpTo(new THREE.Quaternion(...defaultOrientation('Trimetric'))) // viewDefaultOrientation(): fallback Trimetric
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
    for (const o of this.helpers.values()) this.viewer.scene?.add(o)
  }

  /** What the page draws over the model and never picks (partdesign.tsx: the sketches shown, the Origin's planes while
   *  New Sketch picks one, a Pad's preview), by key; null removes and disposes it. Kept across a scene reload. */
  private helpers = new Map<string, THREE.Object3D>()
  setHelper(key: string, obj: THREE.Object3D | null) {
    // before the first render there is no scene (three-cad-viewer throws on viewer.scene): the helper is kept, and show()
    // adds the helpers once the scene is there (a store subscriber, the datums', can run while loadScene sets the scene)
    const scene = this.rendered ? this.viewer.scene : null
    const old = this.helpers.get(key)
    if (old) {
      if (this.hovered) { let had = false; old.traverse((o) => { if (o.userData.pickName === this.hovered) had = true }); if (had) this.hovered = null }
      scene?.remove(old)
      old.traverse((o) => {
        const m = o as THREE.Mesh
        m.geometry?.dispose()
        const mat = m.material as THREE.Material | THREE.Material[] | undefined
        ;(Array.isArray(mat) ? mat : mat ? [mat] : []).forEach((x) => { (x as THREE.SpriteMaterial).map?.dispose(); x.dispose() })
      })
      this.helpers.delete(key)
    }
    if (obj) {
      obj.userData.cadHelper = true
      // only what names itself for helperPicker (userData.pickName) can be hit
      obj.traverse((o) => { if (!o.userData.pickName) o.raycast = () => {} })
      this.helpers.set(key, obj)
      scene?.add(obj)
    }
    this.redraw()
  }
  /** While set, a left click on a helper that has a userData.pickName hands that name here. */
  helperPicker: ((name: string) => void) | null = null
  /** The on-view labels' own clicks (pd_transform.tsx's patterns' spacing labels, EditableDatumLabel): a left click on one
   *  edits it, a right click asks for its menu first (true: the menu was shown, not the view's). Names "spacing:<i>". */
  labelPick: ((name: string, x: number, y: number) => void) | null = null
  labelMenu: ((name: string, x: number, y: number) => boolean) | null = null
  /** A task panel's selection gate (pd_pick.tsx: ReferenceSelection::allow): which named helpers may be preselected and
   *  picked; a refused one gets FreeCAD's "Not allowed:" message and the forbidden cursor (SelectionSingleton::setPreselect). */
  helperGate: ((name: string) => true | string) | null = null
  /** With no picker set: a click on a named helper that asks for it (userData.selectable, a datum shown in the view)
   *  selects it, as a click on a datum does in FreeCAD; additive with Ctrl. */
  helperSelect: ((name: string, additive: boolean) => void) | null = null
  /** The helper under the pointer as it is preselected (drawn in the preselection colour), and what the status bar says. */
  helperHover: ((name: string | null, refused: string | null) => void) | null = null
  private hovered: string | null = null
  /** Preselection of a named helper (SoFCUnifiedSelection's preselect highlight): every object of that name in the
   *  preselection colour (Preferences > Display > Colors' Preselected), its own colour back when the pointer leaves. */
  private setHovered(name: string | null) {
    if (name === this.hovered) return
    const paint = (n: string | null, on: boolean) => {
      if (!n) return
      const color = new THREE.Color(getState().selPrefs.preColor)
      for (const root of this.helpers.values()) root.traverse((o) => {
        if (o.userData.pickName !== n || o.userData.preselect === false) return
        const mat = (o as THREE.Mesh).material as (THREE.Material & { color?: THREE.Color }) | undefined
        if (!mat?.color) return
        if (on) { if (!o.userData.baseColor) o.userData.baseColor = mat.color.clone(); mat.color.copy(color) }
        else if (o.userData.baseColor) { mat.color.copy(o.userData.baseColor); delete o.userData.baseColor }
      })
    }
    paint(this.hovered, false)
    this.hovered = name
    paint(name, true)
    this.redraw()
  }
  /** For scripts (pickcheck.mjs): the helper preselected now. */
  hoveredHelper(): string | null { return this.hovered }
  /** The named helper the pointer hovers, and whether the gate takes it; the preselection follows. False when no named
   *  helper is there (the model's own preselection goes on). */
  private hoverHelpers(c: { x: number; y: number }, clear?: () => void): boolean {
    const hit = this.helperPicker || this.helperSelect ? this.helperHit(c) : null
    const canvas = this.viewer.renderer?.domElement as HTMLElement | undefined
    const model = hit && !this.helperPicker ? this.hitAt(c) : null
    const cam = this.viewer.camera?.getCamera?.()
    const unforbid = () => { if (canvas && canvas.dataset.forbid) { canvas.style.cursor = ''; delete canvas.dataset.forbid } }
    if (!hit || (model && cam && this.modelInFront(cam, model, hit.distance)) || (!this.helperPicker && !hit.selectable)) {
      if (this.hovered) { this.setHovered(null); this.helperHover?.(null, null) }
      unforbid()
      return false
    }
    const ok = this.helperPicker && this.helperGate ? this.helperGate(hit.name) : true
    if (ok === true) {
      this.setHovered(hit.name)
      clear?.(); this.helperHover?.(hit.name, null)
      unforbid()
    } else {
      this.setHovered(null)
      clear?.(); this.helperHover?.(null, ok)
      if (canvas) { canvas.style.cursor = 'not-allowed'; canvas.dataset.forbid = '1' }
    }
    return true
  }
  /** Whether the model's element under the pointer is taken before a datum there: nearer by closeToFirst's 0.2, or a vertex
   *  or an edge as near as it (an edge over the face it lies on, hitAt's rule; a datum plane drawn through a corner). */
  private modelInFront(cam: THREE.Camera, model: { point: THREE.Vector3; sub: string | null }, helperDistance: number) {
    void cam
    const d = this.ray.ray.origin.distanceTo(model.point)       // from the pick ray's origin, as the hits' distances (orthographic too)
    return d < helperDistance - 0.2 || (d <= helperDistance + 0.2 && /^(Vertex|Edge)/.test(model.sub ?? ''))
  }
  private helperAt(e: { x: number; y: number }): string | null {
    return this.helperHit(e)?.name ?? null
  }
  private helperHit(e: { x: number; y: number }): { name: string; distance: number; selectable: boolean } | null {
    const canvas = this.viewer.renderer?.domElement as HTMLCanvasElement | undefined
    const cam = this.viewer.camera?.getCamera?.()
    if (!canvas || !cam || !this.helpers.size) return null
    const r = canvas.getBoundingClientRect()
    cam.updateMatrixWorld()
    this.ray.setFromCamera(new THREE.Vector2(((e.x - r.left) / r.width) * 2 - 1, -((e.y - r.top) / r.height) * 2 + 1), cam)
    // a helper line (a dress-up's base edges) within the pick radius, as hitAt picks the model's
    const perPx = this.worldPerPixel(cam, r.height), radius = getState().selPrefs.pickRadius
    this.ray.params.Line = { threshold: perPx * radius }
    const named = (o: THREE.Object3D | null) => { for (; o; o = o.parent) if (o.userData.pickName) return o; return null }
    const hits = this.ray.intersectObjects([...this.helpers.values()], true).map((h) => ({ h, o: named(h.object) })).filter((x) => x.o)
    if (!hits.length) return null
    // An on-view label (EditableDatumLabel's SoDatumLabel under an SoAnnotation) is drawn over the model with depth testing
    // off, and Coin's dragger takes a click on its text wherever a face or a datum is behind it: a named sprite wins outright.
    const label = hits.filter((x) => (x.h.object as THREE.Sprite).isSprite).sort((a, b) => a.h.distance - b.h.distance)[0]
    // userData.pickPriority: an edge over the face it bounds, within closeToFirst's 0.2 slack (hitAt's rule)
    const near = hits.filter((x) => !(x.h.distance > hits[0].h.distance + 0.2))
    near.sort((a, b) => ((b.o!.userData.pickPriority as number) ?? 0) - ((a.o!.userData.pickPriority as number) ?? 0))
    const hit = label ?? near[0], o = hit.o!
    let selectable = false
    for (let x: THREE.Object3D | null = o; x; x = x.parent) if (x.userData.selectable) selectable = true
    return { name: o.userData.pickName as string, distance: hit.h.distance, selectable }
  }
  /** For scripts (dressupcheck.mjs): a client point where a click hits the helper element named pickName (a face's triangle
   *  centre or an edge's segment middle that helperAt resolves to that name), or null when none is in view. */
  helperPoint(key: string, pickName: string): { x: number; y: number } | null {
    const root = this.helpers.get(key), cam = this.viewer.camera?.getCamera?.()
    if (!root || !cam) return null
    root.updateMatrixWorld(true)
    const toScreen = this.screenOf(cam), v = new THREE.Vector3(), w = new THREE.Vector3(), u = new THREE.Vector3()
    const cands: { x: number; y: number }[] = []
    root.traverse((o) => {
      if (o.userData.pickName !== pickName) return
      if ((o as THREE.Sprite).isSprite) { cands.push(toScreen(o.getWorldPosition(new THREE.Vector3()))); return }   // a label's text
      const g = (o as THREE.Mesh).geometry as THREE.BufferGeometry | undefined
      const pos = g?.attributes.position
      if (!pos) { cands.push(toScreen(o.getWorldPosition(new THREE.Vector3()))); return }
      if ((o as THREE.Mesh).isMesh && g!.index) {
        const idx = g!.index
        for (let t = 0; t + 2 < idx.count; t += 3) {
          v.fromBufferAttribute(pos, idx.getX(t)).add(w.fromBufferAttribute(pos, idx.getX(t + 1))).add(u.fromBufferAttribute(pos, idx.getX(t + 2))).multiplyScalar(1 / 3)
          const c0 = v.clone()
          cands.push(toScreen(v.applyMatrix4(o.matrixWorld)))
          // and toward each corner (a large face meshed as a couple of triangles may have its centres covered)
          for (let k = 0; k < 3; k++) cands.push(toScreen(new THREE.Vector3().fromBufferAttribute(pos, idx.getX(t + k)).lerp(c0, 0.4).applyMatrix4(o.matrixWorld)))
        }
      } else for (let i = 0; i + 1 < pos.count; i++) {
        // points along the segment (a datum line is one long segment, partly in front of the model)
        for (let k = 1; k < 20; k++) {
          const t = k % 2 ? 0.5 + (k >> 1) * 0.05 : 0.5 - (k >> 1) * 0.05      // from the middle out
          v.fromBufferAttribute(pos, i).lerp(w.fromBufferAttribute(pos, i + 1), t)
          cands.push(toScreen(v.applyMatrix4(o.matrixWorld)))
        }
      }
    })
    const r = (this.viewer.renderer?.domElement as HTMLCanvasElement | undefined)?.getBoundingClientRect()
    for (const c of cands) {
      if (r && (c.x < r.left + 2 || c.x > r.right - 2 || c.y < r.top + 2 || c.y > r.bottom - 2 || (c.x > r.right - 170 && c.y < r.top + 170))) continue // and not under the NaviCube
      // the same element a couple of pixels around it too (a click lands on whole pixels; an edge's pick radius is near)
      if ([[0, 0], [1.5, 0], [-1.5, 0], [0, 1.5], [0, -1.5]].every(([dx, dy]) => this.helperAt({ x: c.x + dx, y: c.y + dy }) === pickName)) return c
    }
    return null
  }
  /** The scene's box, for what is sized to the model (a Through all preview, the Origin's planes). */
  modelBox(): THREE.Box3 | null { return this.box() }
  /** A body's face meshes as the view draws them (pd_transform.tsx copies them for a Transform body preview). */
  bodyMeshes(body: string): THREE.Mesh[] { return this.meshes.get(body) ?? [] }

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
      this.updateCube()
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
    if (this.sketchHook && ev.type !== 'key' && ev.type !== 'gesture') return this.sketchHook.event(ev as NavEvent)
    if (this.nav.interact) return ev.type !== 'move'
    if (ev.type === 'move') {
      cancelAnimationFrame(this.hoverFrame)
      const c = this.client(ev.pos)
      this.hoverFrame = requestAnimationFrame(() => {
        if (this.hoverHelpers(c, () => this.on.hover(null, null, null))) return
        const h = this.hitAt(c)
        this.on.hover(h?.body ?? null, h ? h.point.toArray() : null, h?.sub ?? null)
      })
      return false
    }
    if (ev.type === 'release' && ev.button === 1 && this.labelPick) {
      const c = this.client(ev.pos), name = this.helperAt(c)
      if (name?.startsWith('spacing:')) { this.labelPick(name, c.x, c.y); return true }
    }
    if (ev.type === 'release' && ev.button === 1 && this.helperPicker) {
      // A pickable helper (an Origin plane New Sketch offers) takes the click before the model does; one the panel's
      // gate refuses is not picked ("Selection not allowed by filter", SelectionSingleton::addSelection)
      const name = this.helperAt(this.client(ev.pos))
      if (name) {
        const ok = this.helperGate ? this.helperGate(name) : true
        if (ok === true) this.helperPicker(name)
        else this.helperHover?.(null, 'Selection not allowed by filter')
        return true
      }
    }
    if (ev.type === 'release' && ev.button === 1 && !this.helperPicker && this.helperSelect) {
      // A datum shown in the view: a click on it selects it (when nothing of the model is in front of it)
      const c = this.client(ev.pos), hit = this.helperHit(c), model = hit?.selectable ? this.hitAt(c) : null
      const cam = this.viewer.camera?.getCamera?.()
      if (hit?.selectable && !(model && cam && this.modelInFront(cam, model, hit.distance))) {
        this.helperSelect(hit.name, ev.ctrl)
        return true
      }
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
    if (!this.rendered) return // the viewer's camera getter throws until the first render
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
  private selPrefsApplied: SelPrefs | null = null
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
      // SoTransformDragger's translation arrows point one way, along +X/+Y/+Z; three's gizmo has a
      // head and a pick zone at both ends. Drop the − ones (their offsets are baked into the geometry).
      if (mode === 'translate') {
        const gz = (tc as any)._gizmo, axis = { X: 'x', Y: 'y', Z: 'z' } as const
        for (const group of [gz?.gizmo?.translate, gz?.picker?.translate]) for (const o of [...(group?.children ?? [])] as THREE.Mesh[]) {
          const ax = axis[o.name as keyof typeof axis]
          if (!ax || !o.geometry) continue
          o.geometry.computeBoundingBox()
          const c = o.geometry.boundingBox!.getCenter(new THREE.Vector3())
          if (c[ax] < -1e-6) o.removeFromParent()
        }
      }
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
  home(fallback: Exclude<HomeView, 'Custom'>) {
    const p = this.cameraParts()
    if (!p) return
    const q = new THREE.Quaternion(...defaultOrientation(fallback))
    // The class's own fitAll, not attachView's recording wrapper: Home is one command, echoed as such.
    const fit = () => CadView.prototype.fitAll.call(this)
    if (Math.abs(q.dot(p.cam.quaternion)) > 1 - 1e-6) return fit()
    const box = this.box(), t = p.controls.target.clone()
    this.nav.startAnimation(q, t, box ? box.getCenter(new THREE.Vector3()).sub(t) : new THREE.Vector3(), fit)
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

  private posed = new Map<string, { pos: THREE.Vector3; quat: THREE.Quaternion; scale: THREE.Vector3 }>()
  /** CADAgent_Pose: the machine drawn at one of its named poses (poses.ts), every body an axis carries slid by `offsets`
   *  in the world; null puts them all back where assembly.py has them. A view only, as previewPlacement is: the
   *  checks, `cad measure` and `cad mass` keep judging the machine at home, and a pose of the spec is judged by its
   *  own entries (`pose = "park"`). The groups move, not the meshes, so picking, the selection boxes and fitting
   *  follow them as they follow a dragged part. */
  setPose(offsets: Record<string, Vec3> | null) {
    const groups = this.viewer.nestedGroup?.groups as Record<string, THREE.Object3D> | undefined
    for (const [path, home] of this.posed) {
      const g = groups?.[path]
      if (g) { g.position.copy(home.pos); g.quaternion.copy(home.quat); g.scale.copy(home.scale); g.updateMatrixWorld(true) }
    }
    this.posed.clear()
    for (const [name, by] of Object.entries(offsets ?? {})) {
      const b = getState().scene?.bodies.find((x) => x.name === name)
      const g = b ? groups?.[b.path] : undefined
      if (!b || !g) continue
      this.posed.set(b.path, { pos: g.position.clone(), quat: g.quaternion.clone(), scale: g.scale.clone() })
      const parent = g.parent?.matrixWorld ?? new THREE.Matrix4()
      const home = new THREE.Matrix4().compose(g.position, g.quaternion, g.scale)
      // a world translation, in the parent's frame: local' = P⁻¹ · T · P · local
      parent.clone().invert().multiply(new THREE.Matrix4().makeTranslation(by[0], by[1], by[2])).multiply(parent).multiply(home)
        .decompose(g.position, g.quaternion, g.scale)
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

  /** Std_ViewFitAll / Std_ViewFitSelection (View3DInventorViewer::viewAll / viewSelection): keep the
   *  direction and frame the bounding sphere; with animations on, 10 steps of 20 ms. `names`, the selected
   *  parts, is Fit Selection. It frames the whole of each part, as FreeCAD does at 3160daf1e2b6 whatever
   *  elements of it are selected: ViewProvider::getBoundingBox(subname) gives the part's whole box for a
   *  Face (SoBrepFaceSet::getBoundingBox is the inherited one) and, measured in the real FreeCAD, for an Edge and a
   *  Vertex too (and, for a part that has a Placement, its box without the Placement: the camera lands away from
   *  the part, which is not copied). FreeCAD's viewAll sets a perspective camera's heightAngle back to 45°
   *  first; viewSelection leaves it as it is. A perspective camera stands where the sphere fits the view's
   *  shorter side: R / tan(heightAngle / 2) from the centre (animatedViewAll, and what Coin's viewBoundingBox
   *  gives in the real FreeCAD: 232.89 for R 96.468 at 45°), not R / sin. */
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
    // viewAll: a perspective camera's heightAngle always snaps back to 45° first. viewSelection does not.
    if (!ortho && !names?.length) { c.fov = 45; c.updateProjectionMatrix() }
    // SoCamera::viewBoundingBox: the sphere fills the shorter side.
    const aspect = ortho ? (c.right - c.left) / (c.top - c.bottom) : c.aspect
    const height = (2 * sphere.radius) / Math.min(1, aspect)
    const zoom1 = ortho ? (c.top - c.bottom) / height : cam.zoom
    const dist1 = ortho ? Math.max(sphere.radius * 6, cam.position.distanceTo(controls.target))
      : sphere.radius / Math.tan(THREE.MathUtils.degToRad(c.fov) / 2) / Math.min(1, aspect)
    const t0 = controls.target.clone(), d0 = cam.position.distanceTo(t0), z0 = cam.zoom
    const put = (k: number) => {
      const now = this.cameraParts() // not the pair from the start: a scene reload in between builds a new one
      if (!now) return
      now.controls.target.copy(t0).lerp(sphere.center, k)
      now.cam.position.copy(now.controls.target).addScaledVector(dir, d0 + (dist1 - d0) * k)
      if (ortho) { now.cam.zoom = z0 + (zoom1 - z0) * k; now.cam.updateProjectionMatrix() }
      this.cameraChanged()
    }
    if (instant || !getState().animate || document.visibilityState !== 'visible') return put(1)
    // 10 steps of 20 ms, which stop when anything else starts or stops a view change (a turn, a zoom, a drag): they would go on
    // setting the position from the direction this fit began with, over a camera that has turned since.
    const stops = this.nav.stops
    let i = 0
    const step = () => { if (this.nav.stops !== stops) return; i++; put(i / 10); if (i < 10) setTimeout(step, 20) }
    step()
  }

  setOrtho(flag: boolean) {
    const tf = this.tf?.t
    this.stopTransform(true)
    try { this.viewer.setOrtho(flag) } catch { return }
    // three-cad-viewer gives the new camera its own up (z), as render() sees too: the up is the orientation's y axis here, as everything that turns the camera
    // keeps it (without this it stood until the next frame of an animation or a fit set it, which a quick key press after a view key could outrun)
    { const now = this.cameraParts(); if (now) now.cam.up.set(0, 1, 0).applyQuaternion(now.cam.quaternion) }
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
    this.updateCube()
    // NaviCubeImplementation::handleResize runs every render: keep the cube at the same
    // CubePos as the container is resized, not a stale pixel margin from the old size.
    if (this.gizmo) this.applyCubeLayout(getState().cubePos)
    this.emitSize()
    // Draw the moved cube now: a view first shown from behind another tab (the Start page) kept
    // the frame it last drew, with the cube where the old size put it, until the next redraw.
    this.redraw()
  }

  // ── camera commands ────────────────────────────────────────────────────────
  private cameraParts() {
    const cam = this.viewer.camera?.getCamera?.() as (THREE.OrthographicCamera | THREE.PerspectiveCamera) | undefined
    const controls = this.viewer.controls?.controls
    return cam && controls ? { cam, controls } : null
  }

  private settle() {
    this.cameraParts()?.controls.update()
    this.updateCube()
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

  /** The camera's orientation as Coin's (x, y, z, w): View3DInventorViewer::getCameraOrientation, for CameraDialog's Current View. */
  cameraOrientation(): [number, number, number, number] | null {
    const q = this.cameraParts()?.cam.quaternion
    return q ? [q.x, q.y, q.z, q.w] : null
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
    // NaviCube.cpp mouseReleased, flat buttons: a press while the animation before it still runs turns where that one is going
    // (flatButtonTargetOrientation), so quick presses add up. FreeCAD does that only while its own button animation runs; during a face
    // click's or a standard view's it turns the camera as it is half way, which lands on an orientation nobody asked for. Here the
    // target of whatever view animation runs is what a press adds to.
    const base = this.nav.targetOrientation ?? p.cam.quaternion.clone()
    const local = new THREE.Vector3(+(axis === 'x'), +(axis === 'y'), +(axis === 'z'))
    this.animateTo(base.clone().multiply(new THREE.Quaternion().setFromAxisAngle(local, THREE.MathUtils.degToRad(deg))), p.controls.target.clone())
  }


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

  /** View3DInventor::getCamera() (View3DInventor.cpp:558-565): the camera node as Coin writes it (SoWriteAction; floats
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

  /** View3DInventor::setCamera() (View3DInventor.cpp:567-570): take on a camera node's position, orientation, focal distance and height (or
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
      // to the label (getTextPosition, ViewProviderMeasureBase.cpp:769-788: 30px up-and-right of the anchor in screen
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
  /** Sketcher_ViewSection (TempoVis.sketchClipPlane): the sketch's own clipping plane, beside Clipping's. */
  private sectionPlane: THREE.Plane | null = null
  setSectionPlane(plane: THREE.Plane | null) { this.sectionPlane = plane; this.applyClip(getState().clip); this.redraw() }
  private applyClip(clip: Clip | null) {
    const planes: THREE.Plane[] = this.sectionPlane ? [this.sectionPlane] : []
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
    if (!this.rendered) return
    const cam = this.viewer.camera?.getCamera?.(), c = this.viewer.renderer?.domElement as HTMLCanvasElement | undefined
    if (!cam || !c || !c.clientHeight) return // hidden (another tab in front): sized when it shows
    for (const g of this.placementHelpers) g.scale.setScalar(40 * this.worldPerPixel(cam, c.clientHeight))
    // A helper's parts in an SoShapeScale (userData.shapeScale: pixels per unit, the node's scaleFactor), as the
    // datums are (Gui/ViewProviderDatum.cpp): the same size on screen at any zoom.
    const wpp = this.worldPerPixel(cam, c.clientHeight)
    for (const h of this.helpers.values()) h.traverse((o) => {
      const s = o.userData.shapeScale
      if (typeof s !== 'number') return
      // a label's sprite keeps its text's aspect ratio; anything else is square to its shapeScale
      if ((o as THREE.Sprite).isSprite) o.scale.set(s * wpp * ((o.userData.aspect as number) ?? 1), s * wpp, 1)
      else o.scale.setScalar(s * wpp)
    })
  }
  /** Size the SoShapeScale helpers now (a helper set after the last camera change). */
  rescaleHelpers() { this.scalePlacementIndicators(); this.redraw() }

  private applyBoxes(selected: string[], preselected: string | null, selBoxes: boolean) {
    for (const h of this.boxHelpers) this.viewer.scene?.remove(h)
    this.boxHelpers = []
    const s = getState()
    for (const n of this.meshes.keys()) {
      if (s.hidden.includes(n)) continue
      const vp = viewOf(s, n), sel = selected.includes(n), pre = !sel && n === preselected
      const boxed = selBoxes || vp.selectionStyle === 'BoundBox'
      const sc = selColor(), pc = preColor()
      const color = sel && boxed && sc !== null ? sc : pre && boxed && pc !== null ? pc : vp.boundingBox ? BBOX_COLOR : null
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
        mat.userData.cadBase = vp.pointColor
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

  /** What the model has at a point of the canvas (CSS pixels from its top left): the Sketcher's External Projection
   *  tool picks the Body's faces, edges and vertices while the sketch in edit takes the mouse. */
  sceneHitAt(x: number, y: number): { body: string; sub: string | null } | null {
    const r = (this.viewer.renderer?.domElement as HTMLCanvasElement | undefined)?.getBoundingClientRect()
    if (!r) return null
    const h = this.hitAt({ x: r.left + x, y: r.top + y })
    return h ? { body: h.body, sub: h.sub } : null
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
    // Preferences > Selection's PickRadius (View3DInventorViewer's pick radius, 5 px by default).
    const radius = getState().selPrefs.pickRadius
    this.ray.params.Line2 = { threshold: radius } as any
    this.ray.params.Points = { threshold: perPx * radius }
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
   *  radius (PickRadius, 5 px) times a multiplier (Clarify Selection's ClarifySelectionRadiusMultiplier, 5). */
  picksAt(e: { x: number; y: number }, multiplier = 5): { body: string; sub: string | null }[] {
    const canvas = this.viewer.renderer?.domElement as HTMLCanvasElement | undefined
    const cam = this.viewer.camera?.getCamera?.()
    if (!canvas || !cam) return []
    const r = canvas.getBoundingClientRect()
    cam.updateMatrixWorld()
    this.ray.setFromCamera(new THREE.Vector2(((e.x - r.left) / r.width) * 2 - 1, -((e.y - r.top) / r.height) * 2 + 1), cam)
    const s = getState(), perPx = this.worldPerPixel(cam, r.height)
    ;(this.ray as any).camera = cam
    const radius = s.selPrefs.pickRadius
    this.ray.params.Line2 = { threshold: radius * multiplier } as any
    this.ray.params.Points = { threshold: perPx * radius * multiplier }
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

  /** Face n of a part as world-space triangles with the mesh's own normals, so it can be lit as the part is. */
  private faceMesh(ref: string): { geo: THREE.BufferGeometry; mat: THREE.Material } | null {
    const dot = ref.lastIndexOf('.'), body = ref.slice(0, dot), m = /^Face(\d+)$/.exec(ref.slice(dot + 1))
    const mesh = m ? this.front(body) : undefined
    if (!m || !mesh) return null
    const id = Number(m[1]) + (this.bases.get(body)?.Face ?? 0)
    mesh.updateWorldMatrix(true, false)
    const g = mesh.geometry, idx = g.index!, pos = g.attributes.position, nor = g.attributes.normal, comp = g.attributes.componentId
    const nm = new THREE.Matrix3().getNormalMatrix(mesh.matrixWorld), p = new THREE.Vector3(), n = new THREE.Vector3()
    const ps: number[] = [], ns: number[] = []
    for (let t = 0; t < idx.count; t += 3) {
      if (comp.getX(idx.getX(t)) !== id) continue
      for (let k = 0; k < 3; k++) {
        const v = idx.getX(t + k)
        p.fromBufferAttribute(pos, v).applyMatrix4(mesh.matrixWorld); ps.push(p.x, p.y, p.z)
        if (nor) { n.fromBufferAttribute(nor, v).applyMatrix3(nm).normalize(); ns.push(n.x, n.y, n.z) }
      }
    }
    if (!ps.length) return null
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(ps, 3))
    if (ns.length) geo.setAttribute('normal', new THREE.Float32BufferAttribute(ns, 3))
    else geo.computeVertexNormals()
    return { geo, mat: (mesh.userData.cadOrigMat ?? mesh.material) as THREE.Material }
  }

  /** Highlight sub-elements the way FreeCAD does: only the face, edge or vertex. A face takes the colour as its
   *  diffuse colour and is lit as the part is (SoBrepFaceSet::overrideMaterialBinding gives the selected or
   *  preselected part the colour in the per-face material index, no emissive colour): the top of a box in the
   *  isometric view is #119ddf selected and #19b5df preselected for #00abff and #0ac8ff, in FreeCAD 26.3 on Linux and
   *  on a Mac. Edges and vertices are flat colours, as SoBrepEdgeSet and SoBrepPointSet draw them. */
  private applySubs(pre: string | null, subs: string[]) {
    for (const o of this.overlays) { o.parent?.remove(o); (o as any).geometry?.dispose?.(); (o as any).material?.dispose?.() }
    this.overlays = []
    const add = (ref: string, color: number) => {
      const g = this.subGeometry(ref)
      if (!g || !this.viewer.scene) return
      let o: THREE.Object3D
      const lit = g.kind === 'Face' ? this.faceMesh(ref) : null
      if (lit) {
        // the part's own material (three-cad-viewer's MeshStandardMaterial), in the colour, with nothing emitted
        const mat = lit.mat.clone() as THREE.MeshStandardMaterial
        mat.userData = {}
        mat.color?.setHex(color)
        mat.emissive?.setHex(0)
        mat.map = null; mat.vertexColors = false; mat.transparent = false; mat.opacity = 1; mat.depthTest = true
        Object.assign(mat, { side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 })
        o = new THREE.Mesh(lit.geo, mat)
      } else if (g.kind === 'Face') {
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
    const sc = selColor(), pc = preColor()
    if (sc !== null) subs.forEach((r) => add(r, sc))
    if (pre && pc !== null && !subs.includes(pre)) add(pre, pc)
  }

  /** Std_AlignToSelection (View3DInventorViewer::alignToSelection): `refs` are the selected elements ("part.Face3"),
   *  `whole` the parts selected as a whole. The camera turns to look straight at the selection from the side it is
   *  on, rolled to the quarter turn nearest its own roll, about the focal point (the view is not moved or zoomed).
   *  False when nothing selected gives a direction. */
  alignToSelection(refs: string[], whole: string[]): boolean {
    const p = this.cameraParts()
    const dir = p ? this.alignDirection(refs, whole) : null
    if (!p || !dir) return false
    const q = alignOrientation(p.cam.quaternion, dir.z, dir.x)
    this.orient([q.x, q.y, q.z, q.w])
    return true
  }

  /** The directions the alignment asks for, as alignToSelection reads them: one element gives its own (a planar face's normal and
   *  the direction of its longest straight edge, a straight edge's direction, the axis of a planar curve's plane); a part with several
   *  elements gives the sum of its faces' normals, else its edges' plane or the sum of their directions; the parts' directions add up
   *  and the camera's X is the one Base::Rotation(-Z, direction) gives. A curved face gives the surface's normal at the middle of its
   *  (u, v) range, which the mesh does not have: scene.json carries it (Body.curved). A vertex and a whole part give nothing. */
  private alignDirection(refs: string[], whole: string[]): { z: THREE.Vector3; x: THREE.Vector3 } | null {
    const items = refs.length + whole.length
    if (!items) return null
    if (items === 1) {
      const f = refs.length ? this.facingOf(refs[0]) : null
      return f ? { z: f.z, x: f.x ?? rotateFromMinusZ(f.z) } : null
    }
    const byPart = new Map<string, string[]>()
    for (const r of refs) { const b = r.slice(0, r.lastIndexOf('.')); byPart.set(b, [...(byPart.get(b) ?? []), r]) }
    for (const b of whole) byPart.set(b, [...(byPart.get(b) ?? []), '']) // a part taken whole: an item whose sub name is empty
    const sum = new THREE.Vector3()
    let valid = 0
    for (const subs of byPart.values()) {
      const z = subs.length === 1 ? (subs[0] ? this.facingOf(subs[0])?.z ?? null : null) : this.groupFacing(subs)
      if (z) { sum.add(z); valid++ }
    }
    if (!valid || sum.length() < 1e-9) return null
    const z = sum.normalize()
    return { z, x: rotateFromMinusZ(z) }
  }

  /** Part::Feature::getCameraAlignmentDirection(directionZ, subnames) for one part's elements. */
  private groupFacing(subs: string[]): THREE.Vector3 | null {
    const sum = (list: string[]) => {
      const s = new THREE.Vector3()
      let n = 0
      for (const r of list) { const f = r ? this.facingOf(r) : null; if (f) { s.add(f.z); n++ } }
      return n && s.length() > 1e-9 ? s.normalize() : null
    }
    const faces = subs.filter((r) => /\.Face\d+$/.test(r))
    if (faces.length) return sum(faces)
    const edges = subs.filter((r) => /\.Edge\d+$/.test(r))
    if (edges.length === subs.length) { // only edges: if they lie in one plane, its axis
      const axis = planeAxis(edges.flatMap((r) => { const g = this.subGeometry(r); return g?.kind === 'Edge' ? g.segs.flat() : [] }))
      if (axis) return axis
    }
    return sum(subs)
  }

  /** getCameraAlignmentDirection for one element: `z` is the direction to look along, `x` (a face only) the direction of the
   *  face's longest straight edge. */
  private facingOf(ref: string): { z: THREE.Vector3; x?: THREE.Vector3 } | null {
    const g = this.subGeometry(ref)
    if (!g || g.kind === 'Vertex') return null
    const info = subInfo(g)
    if (!info) return null
    if (g.kind === 'Face') {
      const c = this.curvedFacing(ref)
      if (c) return c
      if (!info.normal || (info.kind !== 'Plane' && info.kind !== 'Disc')) return null
      return { z: info.normal.clone().normalize(), x: this.longestStraightEdge(ref.slice(0, ref.lastIndexOf('.')), g.tris, info.normal) }
    }
    if (info.kind === 'Line' && info.dir) return { z: info.dir.clone().normalize() }
    const axis = planeAxis(g.segs.flat())
    return axis ? { z: axis } : null
  }

  /** A face that is not planar (PartFeature.cpp:1880-1933, the "Single non-planar face" branch of getCameraAlignmentDirection): the
   *  normal at the middle of its (u, v) bounds and its longest straight edge's direction, as scene.py worked them out from the
   *  shape, turned with the body's group since the scene was drawn. Null for a face scene.json does not list (a planar one). */
  private curvedFacing(ref: string): { z: THREE.Vector3; x?: THREE.Vector3 } | null {
    const dot = ref.lastIndexOf('.'), body = ref.slice(0, dot), c = this.curved.get(body), m = /^Face(\d+)$/.exec(ref.slice(dot + 1))
    const e = m && c ? c.faces[m[1]] : undefined
    const mesh = e ? this.front(body) : null
    if (!e || !c || !mesh) return null
    mesh.updateWorldMatrix(true, false)
    const turn = new THREE.Matrix4().multiplyMatrices(mesh.matrixWorld, c.home)
    const z = new THREE.Vector3(...e[0]).transformDirection(turn)
    return { z, x: e[1] ? new THREE.Vector3(...e[1]).transformDirection(turn) : undefined }
  }

  /** The longest straight edge of a planar face, by its direction: an edge of the same part that runs from one corner of the face to
   *  another in the face's plane. The first of equal lengths wins, as in TopExp_Explorer's order. */
  private longestStraightEdge(body: string, tris: THREE.Vector3[][], normal: THREE.Vector3): THREE.Vector3 | undefined {
    const corners: THREE.Vector3[] = []
    const seen = new Set<string>()
    const box = new THREE.Box3()
    for (const t of tris) for (const q of t) { box.expandByPoint(q); const k = `${q.x.toFixed(3)},${q.y.toFixed(3)},${q.z.toFixed(3)}`; if (!seen.has(k)) { seen.add(k); corners.push(q) } }
    const tol = 1e-5 * box.min.distanceTo(box.max) + 1e-3, n = normal.clone().normalize(), o = tris[0][0]
    const onFace = (q: THREE.Vector3) => Math.abs(q.clone().sub(o).dot(n)) <= tol && corners.some((c) => c.distanceTo(q) <= tol)
    let best: { len: number; dir: THREE.Vector3 } | undefined
    for (const e of this.straightEdges(body)) {
      if (e.len < 1e-9 || !onFace(e.a) || !onFace(e.b)) continue
      if (!best || e.len > best.len) best = { len: e.len, dir: e.b.clone().sub(e.a).divideScalar(e.len) }
    }
    return best?.dir
  }

  /** The straight edges of a part, in the order of their numbers, by their end points (world space), in one pass over the edge buffer. */
  private straightEdges(body: string): { a: THREE.Vector3; b: THREE.Vector3; len: number }[] {
    const line = (this.edges.get(body) ?? [])[0] as any
    if (!line) return []
    line.updateWorldMatrix(true, false)
    const g = line.geometry, A = g.attributes.instanceStart, B = g.attributes.instanceEnd, comp = g.attributes.componentId
    const by = new Map<number, { a: THREE.Vector3; b: THREE.Vector3; d?: THREE.Vector3; straight: boolean }>()
    const p = new THREE.Vector3(), q = new THREE.Vector3(), d = new THREE.Vector3()
    for (let i = 0; i < comp.count; i++) {
      p.fromBufferAttribute(A, i).applyMatrix4(line.matrixWorld)
      q.fromBufferAttribute(B, i).applyMatrix4(line.matrixWorld)
      d.copy(q).sub(p)
      const id = comp.getX(i), e = by.get(id)
      if (!e) { by.set(id, { a: p.clone(), b: q.clone(), d: d.lengthSq() > 0 ? d.clone().normalize() : undefined, straight: true }); continue }
      e.b.copy(q)
      if (d.lengthSq() === 0) continue
      d.normalize()
      if (!e.d) e.d = d.clone()
      else if (e.d.dot(d) <= 1 - 1e-9) e.straight = false
    }
    return [...by.values()].filter((e) => e.straight).map((e) => ({ a: e.a, b: e.b, len: e.a.distanceTo(e.b) }))
  }

  private index(sc: Scene) {
    this.meshes.clear()
    this.edges.clear()
    this.curved.clear()
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
      const front = this.front(b.name)
      if (b.curved && front) { front.updateWorldMatrix(true, false); this.curved.set(b.name, { faces: b.curved, home: front.matrixWorld.clone().invert() }) }
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
    // New selection colours: redraw the highlights, boxes and sub-elements below.
    if (s.selPrefs !== this.selPrefsApplied) { this.selPrefsApplied = s.selPrefs; this.applied = { ...this.applied, selected: null, subSel: null } }
    if (s.hidden !== this.applied.hidden || s.drawStyle !== this.applied.style || s.view !== this.applied.view) { this.applyHidden(s.hidden, s.drawStyle); dirty = true }
    if (s.cube !== this.applied.cube) {
      if (s.cube) this.attachGizmo()
      else { this.detachGizmo(); this.redraw() }
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
   *  when it is selected whole; Element: when one of its elements is).
   *
   *  How the colour is applied differs between the two. A preselected object gets it as its diffuse colour only
   *  (SoBrepFaceSet::overrideMaterialBinding: highlightColor for the whole shape), so it is lit like any other face: the top
   *  of a box looks #19b5df for #0ac8ff in the iso view of FreeCAD 26.3 (#1ab4e3 on the chassis here). A selected one gets
   *  it as the diffuse colour and as the EMISSIVE colour too (SoFCSelectionRoot's selAll: SoLazyElement::setEmissive, with
   *  the same diffuse override), so Coin adds the colour to the lit colour in the encoded values and every face saturates:
   *  #11ffff for #00abff on all of a box's visible faces, a cylinder and a sphere (four fifths of what it draws; the sphere's
   *  highlight is the one gradient). three adds an emissive colour in linear light, which saturates far less (G 228 where
   *  Coin has 255), so the emissive colour is taken twice (SELECTED_EMISSIVE): #15ffff on the chassis' top, the same view.
   *
   *  The vertices take the colour too, and an object preselected as a whole (from the tree, the selection view or a
   *  macro; a hover in the 3D view preselects one element) has its edges and vertices drawn over everything, its faces
   *  not: View3DInventorSelection::checkGroupOnTop puts it in pcGroupOnTopPreSel. FreeCAD 26.3 on Linux, two boxes, the
   *  far one preselected from its tree row: its edges and vertices show through the near box in #0ac8ff, its faces only
   *  where nothing is in front, lit (2026-10-23; the same with Gui.Selection.setPreselection, tp 1 or 2). */
  private applyTints(selected: string[], pre: string | null) {
    const s = getState()
    for (const [name, list] of this.meshes) {
      const vp = viewOf(s, name)
      const boxed = vp.selectionStyle === 'BoundBox'
      const isSel = !boxed && selected.includes(name)
      const c = isSel ? selColor() : !boxed && name === pre ? preColor() : null
      const whole = s.selected.includes(name) && !s.subSel.some((r) => r.startsWith(name + '.'))
      const element = s.subSel.some((r) => r.startsWith(name + '.'))
      const top = vp.onTop === 'Enabled' ? whole || element : vp.onTop === 'Object' ? whole : vp.onTop === 'Element' ? element : false
      const preTop = !isSel && c !== null && name === pre // pcGroupOnTopPreSel: the edges and vertices over everything
      const lines = new Set<unknown>([...(this.edges.get(name) ?? []), ...(this.verts.get(name) ?? [])])
      const done = new Set<unknown>()
      for (const m of [...list, ...lines] as any[]) {
        const over = top || (preTop && lines.has(m))
        m.renderOrder = over ? (top ? 10 : 20) : 0
        const mat = (m.userData.cadOrigMat ?? m.material) as any
        if (!mat?.color || done.has(mat)) continue
        done.add(mat)
        if (mat.userData.cadBase === undefined) mat.userData.cadBase = mat.color.getHex()
        mat.color.setHex(c ?? mat.userData.cadBase)
        // the lit faces (MeshStandardMaterial); the back faces and the edges are flat colours and have none
        if (mat.emissive) { mat.emissive.setHex(isSel && c !== null ? c : 0); mat.emissiveIntensity = isSel && c !== null ? SELECTED_EMISSIVE : 1 }
        if (mat.userData.cadDepthTest === undefined) mat.userData.cadDepthTest = mat.depthTest
        mat.depthTest = over ? false : mat.userData.cadDepthTest
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
    this.endCubePress?.() // a press on the cube being rebuilt has nothing to end on
    this.gizmo?.dispose()
    this.gizmo = null
    const renderer = this.viewer.renderer
    if (!this.viewer.camera?.getCamera?.() || !renderer) return
    // populateRenderParams (NaviCube.cpp:819-882): BaseColor (FreeCAD Light's #f2f2f2, opaque), HiliteColor, the font, ShowCS
    // and the axis colours; EmphaseColor follows from BaseColor (navicube3d.ts). The labels are View3DSettings.cpp's defaults.
    const nc = getState().naviCube
    this.gizmo = new NaviCubeGL({
      base: nc.color, hilite: '#' + VIEW.cubeHover.toString(16).padStart(6, '0'), font: nc.font, fontWeight: 0, showCS: nc.showCS, axis: getState().axisColors,
      labels: { front: 'FRONT', top: 'TOP', right: 'RIGHT', rear: 'REAR', bottom: 'BOTTOM', left: 'LEFT' },
    }, nc.size)
    this.showCSColorKey = ''
    // The cube's square: the element its presses land on (navicube.tsx's buttons sit above it).
    if (!this.cubeEl) {
      this.cubeEl = document.createElement('div')
      this.cubeEl.className = 'navi-cube'
      Object.assign(this.cubeEl.style, { position: 'absolute', zIndex: '4', touchAction: 'none' })
      this.cubeEl.addEventListener('pointerdown', (e) => this.cubePress(e))
      this.host.appendChild(this.cubeEl)
    }
    this.cubeEl.style.display = ''
    Object.assign(this.cubeEl.style, { width: `${nc.size}px`, height: `${nc.size}px` })
    this.gizmo.setOpacity(getState().naviCube.inactiveOpacity / 100) // hovering starts false: InactiveOpacity until the pointer comes
    this.applyCubeLayout(getState().cubePos)
    this.hookRender()
    this.updateCube()
    this.redraw()
  }
  private detachGizmo() {
    this.endCubePress?.()
    this.gizmo?.dispose()
    this.gizmo = null
    if (this.cubeEl) this.cubeEl.style.display = 'none'
  }

  /** The cube is the camera seen from outside: it takes its orientation from the camera it is drawn for (rootTransform's rotation is
   *  the camera's inverse, SoNaviCube.cpp:1035-1039). Done for every draw (hookRender), so no frame can show a cube a step behind
   *  its camera. */
  private updateCube(camera?: THREE.Camera) {
    const g = this.gizmo, cam = camera ?? this.cameraParts()?.cam
    if (!g || !cam) return
    g.quaternion.copy(cam.quaternion).invert()
  }

  /** NaviCubeImplementation::mouseMoved (NaviCube.cpp:1225-1243): the whole cube fades to InactiveOpacity unless the pointer is
   *  within its square (or a press on it is under way), and the piece or button under the pointer is drawn in HiliteColor; during a
   *  drag nothing is (dragStarted). */
  private cubeDragging = false
  private updateCubeFade(x: number, y: number) {
    const g = this.gizmo, at = this.cubeXY(x, y)
    if (!g || !at) return
    const near = this.cubeActive || (at.x >= 0 && at.x <= 1 && at.y >= 0 && at.y <= 1)
    const factor = near ? 1 : getState().naviCube.inactiveOpacity / 100 // InactiveOpacity
    const pick = this.cubeDragging || !(at.x >= 0 && at.x <= 1 && at.y >= 0 && at.y <= 1) ? null : g.pick(at.x, at.y, this.cubeOrtho())
    const a = g.setOpacity(factor), b = g.setHilite(pick)
    if (a || b) this.redraw()
  }
  isCubeDraggable() { return this.cubeDraggable }
  setCubeDraggable(on: boolean) { this.cubeDraggable = on }

  // ── test hook ──────────────────────────────────────────────────────────────
  /** What probe(true) records about the draws that follow it: how many there were, the camera and the cube of the
   *  last one, the largest angle (degrees) between the cube and the camera's inverse over all of them, and which pick
   *  the last press on the cube resolved to ("x,y,z"). */
  private drawLog: { frames: number; worst: number; camera: number[]; position: number[]; zoom: number; cube: number[]; pick: string | null } | null = null

  /** Test hook for ui/scripts/cubecheck.mjs: the camera's and the cube's orientations, as they stand and as last drawn.
   *  Gate: probe() only reads. The record of draws is kept only after probe(true) (probe(false) drops it), and the page
   *  never calls either: in normal use nothing is recorded and a draw pays one null check. It is reachable as
   *  cadui.getView().probe(), like the rest of the console's debugging API (main.tsx). */
  probe(watch?: boolean) {
    const p = this.cameraParts()
    if (!p) return null
    const cam = p.cam as THREE.OrthographicCamera | THREE.PerspectiveCamera, box = this.box()
    // The record starts from what is on screen now, so "the last draw matches the camera" holds until something moves.
    if (watch !== undefined) this.drawLog = watch ? { frames: 0, worst: 0, camera: cam.quaternion.toArray(), position: cam.position.toArray(), zoom: cam.zoom, cube: this.gizmo ? this.gizmo.quaternion.toArray() : [0, 0, 0, 1], pick: null } : null
    const sphere = box && !box.isEmpty() ? box.getBoundingSphere(new THREE.Sphere()) : null
    return {
      ortho: (cam as THREE.OrthographicCamera).isOrthographicCamera === true,
      camera: cam.quaternion.toArray(), up: cam.up.toArray(), position: cam.position.toArray(), target: p.controls.target.toArray(), zoom: cam.zoom,
      cube: this.gizmo ? this.gizmo.quaternion.toArray() : null,
      animating: this.nav.animating, pendingFrame: this.pending,
      sceneCenter: box && !box.isEmpty() ? box.getCenter(new THREE.Vector3()).toArray() : null, sceneRadius: sphere ? sphere.radius : null,
      drawn: this.drawLog ? { ...this.drawLog } : null,
    }
  }
  /** What a draw showed: the cube's orientation against the camera it was drawn with (see probe). */
  private logDraw(camera: THREE.Camera) {
    const log = this.drawLog, g = this.gizmo
    if (!log || !g) return
    const cam = camera as THREE.OrthographicCamera | THREE.PerspectiveCamera
    log.frames++
    log.worst = Math.max(log.worst, THREE.MathUtils.radToDeg(g.quaternion.clone().normalize().angleTo(cam.quaternion.clone().normalize().invert())))
    log.camera = cam.quaternion.toArray(); log.position = cam.position.toArray(); log.zoom = cam.zoom; log.cube = g.quaternion.toArray()
  }
  /** Test hook: where each pick of the cube (its 6 faces, 12 edges and 8 corners, by direction as "x,y,z") is on the
   *  screen, how squarely it faces the viewer (1 straight on, below 0 turned away), and whether a click there reaches the
   *  cube (`open`: the NaviCube's buttons are elements above the cube's square, and take a click on a pick that lies under one). */
  cubePicks(): Record<string, { x: number; y: number; facing: number; open: boolean }> {
    const g = this.gizmo, el = this.cubeEl, out: Record<string, { x: number; y: number; facing: number; open: boolean }> = {}
    if (!g || !el) return out
    this.updateCube()
    const r = el.getBoundingClientRect(), ortho = this.cubeOrtho()
    for (const pc of g.pieceList()) {
      const at = g.project(pc.centre, ortho), x = r.left + at.x * r.width, y = r.top + at.y * r.height, top = document.elementFromPoint(x, y)
      out[pc.dir.toArray().map(Math.round).join(',')] = { x, y, facing: pc.dir.clone().applyQuaternion(g.quaternion).z, open: !!top && el.contains(top) }
    }
    return out
  }
  /** Test hook: the cube's square on the page. */
  cubeRect() { return this.cubeEl?.getBoundingClientRect() ?? null }

  /** Puts the cube's square where cubeLayout(pos, ...) has it, in the canvas (the GL viewport hookRender draws it in) and as the
   *  element that takes its presses; mirrors the result into cubePlace/cubeOffset (the square's distance from each edge of the
   *  3D view's host), which navicube.tsx places its buttons by. */
  private cubeAt = { x: 0, y: 0 }
  private applyCubeLayout(pos: CubePos) {
    const canvas = this.viewer.renderer?.domElement as HTMLCanvasElement | undefined
    if (!this.gizmo || !canvas || !this.cubeEl) return
    const size = getState().naviCube.size, w = canvas.clientWidth || this.host.clientWidth || 1, h = canvas.clientHeight || this.host.clientHeight || 1
    const { placement, offset } = cubeLayout(pos, w, h, size)
    this.cubeAt = { x: offset.left, y: offset.bottom } // the viewport is counted from the canvas's bottom left
    const cr = canvas.getBoundingClientRect(), hr = this.host.getBoundingClientRect()
    const dx = cr.width ? cr.left - hr.left : 0, dy = cr.height ? cr.top - hr.top : 0
    const off = { left: offset.left + dx, top: offset.top + dy, right: this.host.clientWidth - offset.left - dx - size, bottom: this.host.clientHeight - offset.top - dy - size }
    Object.assign(this.cubeEl.style, { left: `${off.left}px`, top: `${off.top}px` })
    const s = getState()
    if (s.cubePlace !== placement || JSON.stringify(s.cubeOffset) !== JSON.stringify(off)) setState({ cubePlace: placement, cubeOffset: off })
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
  /** Where a pointer is in the cube's square: 0..1 across it, y down (processSoEvent's cube-centred coordinates, scaled). */
  private cubeXY(x: number, y: number) {
    const r = this.cubeEl?.getBoundingClientRect()
    return r && r.width ? { x: (x - r.left) / r.width, y: (y - r.top) / r.height } : null
  }
  private cubeOrtho() { return (this.cameraParts()?.cam as THREE.OrthographicCamera | undefined)?.isOrthographicCamera !== false }
  /** NaviCubeImplementation::pickFace (NaviCube.cpp:901-921): the cube's pick under a pointer, as the direction of the face, edge or
   *  corner; null for none and for a button (those are navicube.tsx's elements, which take their own clicks). */
  private cubePick(e: { clientX: number; clientY: number }): THREE.Vector3 | null {
    const g = this.gizmo, at = this.cubeXY(e.clientX, e.clientY)
    if (!g || !at || at.x < 0 || at.y < 0 || at.x > 1 || at.y > 1) return null
    const key = g.pick(at.x, at.y, this.cubeOrtho())
    return key && key.includes(',') ? new THREE.Vector3().fromArray(key.split(',').map(Number)).normalize() : null
  }
  /** NaviCube::mousePressed / mouseMoved / mouseReleased: a drag past 3 px orbits the
   *  model's bounding sphere (sensitivity 0.45), or moves the cube itself with the Movable
   *  Navigation Cube option on; a click turns to the face, edge or corner, upright (or, with
   *  NaviRotateToNearest on, to the nearest roll); clicking it twice centres too. */
  private cubePress(e: PointerEvent) {
    const g = this.gizmo, el = this.cubeEl
    if (!g || !el || e.button !== 0) return
    const start = { x: e.clientX, y: e.clientY }
    const pick = this.cubePick(e)
    if (!pick) {
      // Within the pick radius of a button's outline, just outside its element: that button, on the release (mouseReleased).
      const at = this.cubeXY(e.clientX, e.clientY), k = at ? g.pick(at.x, at.y, this.cubeOrtho()) : null
      if (k && !k.includes(',')) {
        e.preventDefault()
        el.addEventListener('pointerup', (u) => { const a = this.cubeXY(u.clientX, u.clientY); if (a && g.pick(a.x, a.y, this.cubeOrtho()) === k) (this.host.parentElement?.querySelector(`.navi.${k}`) as HTMLElement | null)?.click() }, { once: true })
      }
      return // PickId::None: let the event fall through to ordinary 3D navigation
    }
    e.preventDefault()
    this.endCubePress?.() // a press that never got its release (the gizmo was rebuilt under it)
    this.cubeActive = true
    // The press is the cube's until the button is up, wherever the pointer goes. Captured, its moves and its release are the cube's
    // own events: a drag that leaves the cube is not taken by the 3D navigation for a press on the canvas, and its pointerup is not
    // one the navigation stops on the canvas (it does, so this never ran, and every later mouse move went on orbiting the model).
    try { el.setPointerCapture(e.pointerId) } catch { /* the pointer is gone */ }
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
      if (ev.pointerId !== e.pointerId) return
      if (!(ev.buttons & 1)) return end(ev, true) // released where no pointerup reached us (outside the window, say)
      if (!dragging && (ev.clientX - start.x) ** 2 + (ev.clientY - start.y) ** 2 >= dragThreshold * dragThreshold) {
        dragging = true
        this.cubeDragging = true // dragStarted: setHilite(PickId::None) (NaviCube.cpp:1187, 1251)
        if (g.setHilite(null)) this.redraw()
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
    let ended = false
    const end = (ev: { clientX: number; clientY: number }, cancelled: boolean) => {
      if (ended) return
      ended = true
      removeEventListener('pointermove', move)
      removeEventListener('pointerup', up)
      removeEventListener('pointercancel', cancel)
      el.removeEventListener('lostpointercapture', cancel)
      try { el.releasePointerCapture(e.pointerId) } catch { /* already released */ }
      this.endCubePress = null
      this.cubeActive = false
      this.cubeDragging = false
      this.updateCubeFade(ev.clientX, ev.clientY)
      if (g.setHilite(null)) this.redraw() // mouseReleased: setHilite(PickId::None) (NaviCube.cpp:1060), until the pointer moves again
      if (dragging) { if (!this.cubeDraggable) this.nav.endOrbitDrag(); this.cubeClick = null; return }
      if (cancelled) return // a press that was taken away is not a click
      const key = pick.toArray().map(Math.round).join(','), now = performance.now()
      if (this.drawLog) this.drawLog.pick = key
      // NaviCube.cpp mouseReleased: clickTimer.elapsed() < QApplication::doubleClickInterval(), the system's (dblclick.ts).
      const twice = !!this.cubeClick && this.cubeClick.key === key && now - this.cubeClick.t < doubleClickInterval() * 1000
      this.cubeClick = twice ? null : { key, t: now }
      const p = this.cameraParts(), std = faceRotation(pick)
      if (!p || !std) return
      const box = this.box(), t = p.controls.target.clone()
      // NaviRotateToNearest (NaviCube.cpp mouseReleased) is a preference, off by default here: the pick's standard upright
      // orientation (getFaceRotation) whatever roll the view has. On, the roll nearest the camera's (getNearestOrientation), taken from
      // the orientation the camera is turning to while an animation runs, not from where it is half way.
      const q = getState().naviCube.toNearest ? nearestOrientation(this.nav.targetOrientation ?? p.cam.quaternion, std, pick) : std
      this.nav.startAnimation(q, t, twice && box ? box.getCenter(new THREE.Vector3()).sub(t) : new THREE.Vector3())
    }
    const up = (ev: PointerEvent) => { if (ev.pointerId === e.pointerId) end(ev, false) }
    const cancel = (ev: Event) => end(ev as PointerEvent, true)
    this.endCubePress = () => end({ clientX: last.x, clientY: last.y }, true)
    addEventListener('pointermove', move)
    addEventListener('pointerup', up)
    addEventListener('pointercancel', cancel)
    el.addEventListener('lostpointercapture', cancel)
  }
  /** Ends the cube press under way, if one is (see cubePress). */
  private endCubePress: (() => void) | null = null

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
        // SoNaviCube's ShowCS tripod: the same live colours (NaviCube::updateColors).
        if (this.gizmo) {
          const key = ac.x + ac.y + ac.z
          if (key !== this.showCSColorKey) { this.gizmo.setAxisColors(ac); this.showCSColorKey = key }
        }
        if (this.tf) this.placeDragLabels()
        // The NaviCube last, over the model, in its own square (SoNaviCube::renderCoin), with the camera of this draw; then the
        // next frame gets the whole canvas back.
        if (this.gizmo) {
          this.updateCube(camera)
          this.gizmo.render(r, this.cubeAt.x, this.cubeAt.y, (camera as THREE.OrthographicCamera).isOrthographicCamera === true)
          if (this.drawLog) this.logDraw(camera)
        }
        const size = r.getSize(new THREE.Vector2())
        r.setViewport(0, 0, size.x, size.y)
        if (this.sketchHook) this.drawSketchOverlay(camera)
      } finally {
        inside = false
        this.addFrametime((performance.now() - fpsStart) / 1000)
      }
    }
  }

  // ── the Sketcher's edit mode (sketcher.ts) ─────────────────────────────────────────────────────────────────────
  /** Puts the Sketcher in charge of the view's events and overlay, or (null) takes it out again. */
  setSketchHook(h: SketchHook | null) {
    this.sketchHook = h
    if (h && !this.sketchCanvas) {
      const c = document.createElement('canvas')
      c.className = 'sketch-overlay'
      Object.assign(c.style, { position: 'absolute', pointerEvents: 'none', zIndex: '3', left: '0px', top: '0px' })
      this.host.appendChild(c)
      this.sketchCanvas = c
    }
    if (!h && this.sketchCanvas) { this.sketchCanvas.remove(); this.sketchCanvas = null }
    this.redraw()
  }
  get sketchKeys() { return this.sketchHook?.key ?? null }
  /** The camera and the canvas's size, for the Sketcher's projections. */
  sketchViewport() {
    const p = this.cameraParts(), c = this.viewer.renderer?.domElement as HTMLCanvasElement | undefined
    if (!p || !c) return null
    const cr = c.getBoundingClientRect(), q = this.cubeEl?.style.display !== 'none' ? this.cubeEl?.getBoundingClientRect() : null
    return { cam: p.cam as THREE.Camera, w: c.clientWidth, h: c.clientHeight, target: p.controls.target.clone(),
      hole: q && q.width ? { x: q.left - cr.left, y: q.top - cr.top, w: q.width, h: q.height } : null }
  }
  /** The tool's cursor over the view (DrawSketchHandler's crosshair), '' for the default. */
  setSketchCursor(css: string) {
    const c = this.viewer.renderer?.domElement as HTMLElement | undefined
    if (c) c.style.cursor = css
  }
  private drawSketchOverlay(camera: THREE.Camera) {
    const cv = this.sketchCanvas, gl = this.viewer.renderer?.domElement as HTMLCanvasElement | undefined, p = this.cameraParts()
    if (!cv || !gl || !p || !this.sketchHook) return
    const hr = this.host.getBoundingClientRect(), r = gl.getBoundingClientRect(), dpr = devicePixelRatio || 1
    const w = Math.round(r.width), h = Math.round(r.height)
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr) }
    Object.assign(cv.style, { left: `${r.left - hr.left}px`, top: `${r.top - hr.top}px`, width: `${w}px`, height: `${h}px` })
    const ctx = cv.getContext('2d')
    if (!ctx) return
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    const vp = this.sketchViewport()
    if (vp) this.sketchHook.draw(ctx, { ...vp, cam: camera })
  }
  /** ViewProviderSketch::setEditViewer: the focal point onto the sketch's origin along the view, then the camera turned to
   *  the sketch (setCameraOrientation, animated as every view change), and fitted to the sketch when it has geometry
   *  (viewObjects). */
  lookAtSketch(q: [number, number, number, number], origin: THREE.Vector3, box: THREE.Box3 | null) {
    const p = this.cameraParts()
    if (!p) return
    const dir = new THREE.Vector3(0, 0, -1).applyQuaternion(p.cam.quaternion), fd = p.cam.position.distanceTo(p.controls.target)
    p.controls.target.copy(origin)
    p.cam.position.copy(origin).addScaledVector(dir, -fd)
    p.cam.updateMatrixWorld()
    this.cameraChanged()
    const fit = () => { if (box && !box.isEmpty()) this.fitBox(box) }
    const target = new THREE.Quaternion(...q)
    if (Math.abs(target.dot(p.cam.quaternion)) > 1 - 1e-9) { fit(); return }
    this.nav.startAnimation(target, origin.clone(), new THREE.Vector3(), fit)
  }
  /** View3DInventorViewer::viewBoundingBox for a box in the world: the direction kept, the box's sphere fitted. */
  fitBox(box: THREE.Box3) {
    const p = this.cameraParts()
    if (!p) return
    const sphere = box.getBoundingSphere(new THREE.Sphere()), cam = p.cam as any
    const dir = cam.position.clone().sub(p.controls.target).normalize()
    const ortho = cam.isOrthographicCamera
    const aspect = ortho ? (cam.right - cam.left) / (cam.top - cam.bottom) : cam.aspect
    const r = Math.max(sphere.radius, 1e-3)
    p.controls.target.copy(sphere.center)
    if (ortho) {
      cam.zoom = (cam.top - cam.bottom) / ((2 * r) / Math.min(1, aspect))
      cam.position.copy(sphere.center).addScaledVector(dir, Math.max(r * 6, cam.position.distanceTo(p.controls.target)))
      cam.updateProjectionMatrix()
    } else cam.position.copy(sphere.center).addScaledVector(dir, r / Math.tan(THREE.MathUtils.degToRad(cam.fov) / 2) / Math.min(1, aspect))
    this.cameraChanged()
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
    if (shape) {
      // The mesh of a round face is inscribed in it: a disc's area is pi r squared, a whole cylinder's 2 pi r times its length along the axis.
      if (shape.kind === 'Disc') area = Math.PI * shape.radius! ** 2
      else if (shape.kind === 'Cylinder') { const h = pts.map((q) => q.dot(shape.dir!)); area = 2 * Math.PI * shape.radius! * (Math.max(...h) - Math.min(...h)) }
      return { ...shape, text: `area ${qarea(area)}, ${shape.kind === 'Cylinder' || shape.kind === 'Disc' ? `diameter ${qlen(2 * shape.radius!)}` : `radius ${qlen(shape.radius!)}`}`, points: pts, area }
    }
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
    if (pts.every((x) => Math.abs(x.distanceTo(cc) - rad) < rad * 0.01)) {
      // The curve's own length, not the polyline's: the chords' central angles add up to the arc's sweep (2 pi for a whole circle).
      const exact = rad * g.segs.reduce((t, [a, b]) => t + 2 * Math.asin(Math.min(1, a.distanceTo(b) / (2 * rad))), 0)
      return { kind: 'Circle', text: `length ${qlen(exact)}, radius ${qlen(rad)}`, points: pts, center: cc, radius: rad, length: exact }
    }
  }
  return { kind: 'Curve', text: `length ${qlen(len)}`, points: pts, center, length: len }
}

// ── Std_AlignToSelection (View3DInventorViewer::alignToSelection) ─────────────
/** Base::Rotation(-UnitZ, dir).multVec(UnitX): the screen's x direction when the selection gives none (no straight edge). Parallel
 *  vectors are the constructor's special case: the same way is no turn, the opposite a half turn about -Z x X (or -Z x Y). */
export function rotateFromMinusZ(dir: THREE.Vector3): THREE.Vector3 {
  const u = new THREE.Vector3(0, 0, -1), v = dir.clone().normalize(), w = u.clone().cross(v), x = new THREE.Vector3(1, 0, 0)
  if (w.length() === 0) {
    if (u.dot(v) > 0) return x
    let t = u.clone().cross(x)
    if (t.length() < 1e-12) t = u.clone().cross(new THREE.Vector3(0, 1, 0))
    return x.applyAxisAngle(t.normalize(), Math.PI)
  }
  return x.applyAxisAngle(w.normalize(), Math.acos(Math.min(1, Math.max(-1, u.dot(v)))))
}
/** The axis of the plane the points lie in (TopoShape::findPlane), or null: too few points, all on one line, or not flat. */
function planeAxis(points: THREE.Vector3[]): THREE.Vector3 | null {
  if (points.length < 3) return null
  const c = points.reduce((t, p) => t.add(p), new THREE.Vector3()).divideScalar(points.length)
  const M = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
  for (const p of points) {
    const d = [p.x - c.x, p.y - c.y, p.z - c.z]
    for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) M[i][j] += (d[i] * d[j]) / points.length
  }
  const { values, vectors } = eig3(M)
  if (values[2] < 1e-18 || values[1] < 1e-8 * values[2] || Math.sqrt(Math.max(0, values[0])) > 1e-4 * Math.sqrt(values[2])) return null
  return vectors[0].clone().normalize()
}
/** The camera's z axis, and its dot with a direction, in float32 as Coin's SbRotation::multVec and SbVec3f::dot work. For a camera exactly across
 *  the face (a Front or Rear view and a top face) alignToSelection's choice of side, cameraZ.dot(directionZ) < 0, is decided by the rounding
 *  of those quaternions: the Front view's z axis is 6e-8 above the horizontal in float32 (so a top face is met from above, a bottom face is
 *  turned to be seen from above too). Rounding to float32 first makes the double the page holds and the float32 FreeCAD holds the same number. */
const f32 = Math.fround
const cameraZFloat32 = (q: THREE.Quaternion) => {
  const x = f32(q.x), y = f32(q.y), z = f32(q.z), w = f32(q.w)
  return new THREE.Vector3(f32(2 * f32(f32(x * z) + f32(w * y))), f32(2 * f32(f32(y * z) - f32(w * x))), f32(1 - f32(2 * f32(f32(x * x) + f32(y * y)))))
}
const dotFloat32 = (a: THREE.Vector3, b: THREE.Vector3) => f32(f32(f32(a.x * f32(b.x)) + f32(a.y * f32(b.y))) + f32(a.z * f32(b.z)))
/** What alignToSelection does once it has the directions: `dirZ` is what the camera is to look along, `dirX` the direction wanted
 *  along the screen's x. The camera stays on the side it is on (the direction is flipped when the camera's z is nearer the opposite),
 *  turns by the least angle that gets there, and is then rolled about the direction to the quarter turn nearest its own roll from
 *  dirX (the tolerance of 1e-5 rad makes ties go the same way each time), and the result is the camera's orientation. Coin's
 *  `a * b` of rotations is a first, then b. */
export function alignOrientation(cam: THREE.Quaternion, dirZ: THREE.Vector3, dirX: THREE.Vector3): THREE.Quaternion {
  const z = dirZ.clone().normalize(), x = dirX.clone().normalize()
  const camZ = new THREE.Vector3(0, 0, 1).applyQuaternion(cam)
  if (dotFloat32(cameraZFloat32(cam), z) < 0) z.negate()
  const inter = new THREE.Quaternion().setFromUnitVectors(camZ, z).multiply(cam)
  const ix = new THREE.Vector3(1, 0, 0).applyQuaternion(inter)
  let angle = Math.atan2(z.dot(x.clone().cross(ix)), x.dot(ix)) // about z, from dirX to the camera's x
  if (angle < 0) angle += 2 * Math.PI
  const pi = Math.PI, f = 0.00001
  angle = angle <= pi / 4 + f ? 0 : angle <= (3 * pi) / 4 + f ? pi / 2 : angle < pi + pi / 4 - f ? pi : angle < pi + (3 * pi) / 4 - f ? pi + pi / 2 : 0
  const X = x.applyAxisAngle(z, angle), Y = z.clone().cross(X)
  return new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(X, Y, z))
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
  /** Measurement.cpp's BRepExtrema_DistShapeShape between a point and an edge (its segments) or a face (its triangles). */
  const toEdge = (p: THREE.Vector3, e: SubInfo) => {
    let best = Infinity
    for (let i = 0; i + 1 < e.points.length; i += 2) {
      const a = e.points[i], ab = e.points[i + 1].clone().sub(a), t = Math.max(0, Math.min(1, p.clone().sub(a).dot(ab) / (ab.lengthSq() || 1)))
      best = Math.min(best, p.distanceTo(a.clone().addScaledVector(ab, t)))
    }
    return best
  }
  const toFace = (p: THREE.Vector3, f: SubInfo) => {
    let best = Infinity
    const near = new THREE.Vector3()
    for (let i = 0; i + 2 < f.points.length; i += 3) best = Math.min(best, new THREE.Triangle(f.points[i], f.points[i + 1], f.points[i + 2]).closestPointToPoint(p, near).distanceTo(p))
    return best
  }
  const circ = (i: SubInfo) => i.kind === 'Circle'
  /** The point to a circle exactly (its plane's distance and the gap between the radius and the point's distance from the axis); an arc by its mesh. */
  const toCircle = (p: THREE.Vector3, c: SubInfo) => {
    if (!full(c)) return toEdge(p, c)
    const n = axisOf(c), w = p.clone().sub(c.center), h = w.dot(n)
    return Math.hypot(h, w.clone().addScaledVector(n, -h).length() - c.radius!)
  }
  /** gp_Circ::Axis: the points of the circle or arc run counter-clockwise about it, as the curve's parameter does. */
  const axisOf = (c: SubInfo) => {
    const n = new THREE.Vector3()
    for (let i = 0; i + 1 < c.points.length; i += 2) n.add(c.points[i].clone().sub(c.center).cross(c.points[i + 1].clone().sub(c.center)))
    return n.normalize()
  }
  const angleBetween = (a: THREE.Vector3, b: THREE.Vector3) => THREE.MathUtils.radToDeg(Math.acos(Math.min(1, Math.max(-1, a.dot(b)))))
  const PARALLEL = 1e-4 // degrees: the axes of a circle and another circle or a cylinder come from meshes, not from the B-rep, which says exactly parallel
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
    if (edges.length === 2 && edges.every(circ)) { // TwoCircles (circles or arcs): the length, the distance between the centres, the angle between the axes
      const [a, b] = edges, angle = angleBetween(axisOf(a), axisOf(b)), head = `Total length: ${len(lengthOf(a) + lengthOf(b))}, Center distance: ${len(a.center.distanceTo(b.center))}`
      return angle <= PARALLEL ? head : `${head}, Axis angle: ${ang(angle)}`
    }
    if (edges.length === 2 && edges.filter(circ).length === 1) { // CircleToEdge: the circle's centre to the other edge
      const c = edges.find(circ)!, o = edges.find((e) => !circ(e))!
      return `Total length: ${len(lengthOf(c) + lengthOf(o))}, Center distance: ${len(toEdge(c.center, o))}`
    }
    return `Total length: ${len(edges.reduce((t, e) => t + lengthOf(e), 0))}` // Edges
  }
  if (faces.length === 1 && edges.length === 1 && infos.length === 2 && circ(edges[0])) {
    const f = faces[0], c = edges[0]
    if (cyl(f)) { // CircleToCylinder: the circle's centre to the cylinder's axis, and the angle between the two axes (a cylinder's axis has no sign here)
      const w = c.center.clone().sub(f.center), off = w.clone().sub(f.dir!.clone().multiplyScalar(w.dot(f.dir!))).length(), angle = angleBetween(axisOf(c), f.dir!.clone().normalize())
      const folded = Math.min(angle, 180 - angle)
      return folded <= PARALLEL ? `Center axis distance: ${len(off)}` : `Center axis distance: ${len(off)}, Axis angle: ${ang(folded)}`
    }
    return `Center surface distance: ${len(toFace(c.center, f))}` // CircleToSurface
  }
  if (verts.length === 2 && infos.length === 2) return `Distance: ${len(verts[0].center.distanceTo(verts[1].center))}` // PointToPoint
  if (verts.length === 1 && infos.length === 2) {
    const v = verts[0], o = infos.find((i) => i !== v)!
    if (circ(o)) return `Minimum distance: ${len(toCircle(v.center, o))}, Center distance: ${len(v.center.distanceTo(o.center))}` // PointToCircle (a circle or an arc)
    if (cyl(o)) { // PointToCylinder: the distance to the axis too
      const w = v.center.clone().sub(o.center), off = w.clone().sub(o.dir!.clone().multiplyScalar(w.dot(o.dir!))).length()
      return `Minimum distance: ${len(toFace(v.center, o))}, Axis distance: ${len(off)}`
    }
    if (faces.includes(o)) return `Minimum distance: ${len(toFace(v.center, o))}` // PointToSurface: to the face, not to its plane
    return `Minimum distance: ${len(toEdge(v.center, o))}` // PointToEdge
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

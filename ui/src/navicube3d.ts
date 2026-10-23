// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Gui/NaviCube.cpp: 2017 Kustaa Nyholm; 2026 Joao Matos
//   src/Gui/Inventor/SoNaviCube.cpp: 2025-2026 Joao Matos
//   src/Gui/View3DSettings.cpp: 2023 Werner Mayer
// The NaviCube as FreeCAD draws it: a port of SoNaviCube (Gui/Inventor/SoNaviCube.cpp) and of the parts of
// NaviCubeImplementation (Gui/NaviCube.cpp) that decide its look: flat chamfered faces in BaseColor, outlines and labels in
// EmphaseColor, the hovered piece in HiliteColor, the ShowCS tripod, and the nine buttons drawn as shapes around the cube.
// Line numbers are those of the files at 3160daf1e2b6. viewer.ts places it, turns it with the camera and handles its mouse;
// navicube.tsx puts a button element over each drawn button.
import * as THREE from 'three'
import { Line2 } from 'three/addons/lines/Line2.js'
import { LineGeometry } from 'three/addons/lines/LineGeometry.js'
import { LineMaterial } from 'three/addons/lines/LineMaterial.js'

// SoNaviCube.cpp:372-378, the overlay's fixed camera and the depth of the cube and its buttons.
const OVERLAY_NEAR = 0.1, OVERLAY_FAR = 10.1, OVERLAY_ORTHO_EXTENT = 2.1, OVERLAY_FOV_SCALE = 1.1, OVERLAY_CUBE_Z = -5.1
const BUTTON_HIT_SLOP = 0.015

/** The buttons, by the class name navicube.tsx gives each one, with SoNaviCube's PickId for it. */
export type NaviButton = 'n' | 's' | 'e' | 'w' | 'rl' | 'rr' | 'back' | 'home' | 'menu'
/** kButtonPickIds (SoNaviCube.cpp:122-132): ArrowNorth, ArrowSouth, ArrowEast, ArrowWest, ArrowRight, ArrowLeft, Backside, Home, ViewMenu. */
export const NAVI_BUTTONS: NaviButton[] = ['n', 's', 'e', 'w', 'rr', 'rl', 'back', 'home', 'menu']

/** One of the cube's 26 pieces: its direction (the face's z, unnormalised: "1,-1,1" for FrontTopRight) and corners. */
type Piece = { key: string; dir: THREE.Vector3; verts: THREE.Vector3[]; mesh: THREE.Mesh }
/** A button in overlay coordinates (0..1 across the cube's square, y down): its outline loops, fill triangles and hit rectangle. */
export type ButtonShape = { loops: [number, number][][]; tris: [number, number][][]; hit: { left: number; top: number; right: number; bottom: number } | null }

const V = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z)
/** A colour as Coin has it: the #rrggbb components as they are, with no colour management. The cube is drawn into a target of
 *  its own (NaviCubeGL.render) with nothing converted on the way, so its blending (InactiveOpacity, the labels' edges) works on
 *  these values, as GL's does in FreeCAD. */
const raw = (c: string) => new THREE.Color().setStyle(c, THREE.LinearSRGBColorSpace)

/** SoNaviCube::addCubeFace (SoNaviCube.cpp:1664-1711): a main face is an octagon, an edge a long quad, a corner a hexagon. */
function cubeFace(x: THREE.Vector3, z: THREE.Vector3, kind: 'main' | 'edge' | 'corner', chamfer: number): THREE.Vector3[] {
  const y = x.clone().cross(z.clone().negate())
  const m = (v: THREE.Vector3, s: number) => v.clone().multiplyScalar(s)
  const sum = (...vs: THREE.Vector3[]) => vs.reduce((a, b) => a.add(b), V(0, 0, 0))
  if (kind === 'corner') {
    const xC = m(x, chamfer), yC = m(y, chamfer), zC = m(z, 1 - 2 * chamfer)
    return [sum(zC, m(xC, -2)), sum(zC, m(xC, -1), m(yC, -1)), sum(zC, xC, m(yC, -1)), sum(zC, m(xC, 2)), sum(zC, xC, yC), sum(zC, m(xC, -1), yC)]
  }
  if (kind === 'edge') {
    const x4 = m(x, 1 - chamfer * 4), yE = m(y, chamfer), zE = m(z, 1 - chamfer)
    return [sum(zE, m(x4, -1), m(yE, -1)), sum(zE, x4, m(yE, -1)), sum(zE, x4, yE), sum(zE, m(x4, -1), yE)]
  }
  const x2 = m(x, 1 - chamfer * 2), y2 = m(y, 1 - chamfer * 2), x4 = m(x, 1 - chamfer * 4), y4 = m(y, 1 - chamfer * 4)
  const n = (v: THREE.Vector3) => m(v, -1)
  return [sum(z, n(x2), n(y4)), sum(z, n(x4), n(y2)), sum(z, x4, n(y2)), sum(z, x2, n(y4)), sum(z, x2, y4), sum(z, x4, y2), sum(z, n(x4), y2), sum(z, n(x2), y4)]
}

/** rebuildGeometry (SoNaviCube.cpp:1532-1562), in kCubeFacePickOrder: the x and z of each piece. */
function pieces(): [THREE.Vector3, THREE.Vector3, 'main' | 'edge' | 'corner'][] {
  const x = V(1, 0, 0), y = V(0, 1, 0), z = V(0, 0, 1)
  const a = (...vs: THREE.Vector3[]) => vs.reduce((p, q) => p.clone().add(q))
  const n = (v: THREE.Vector3) => v.clone().negate()
  return [
    [x, z, 'main'], [x, n(y), 'main'], [n(y), n(x), 'main'], [n(x), y, 'main'], [y, x, 'main'], [x, n(z), 'main'],
    [a(n(x), n(y)), a(x, n(y), z), 'corner'], [a(n(x), y), a(n(x), n(y), z), 'corner'], [a(x, y), a(x, n(y), n(z)), 'corner'], [a(x, n(y)), a(n(x), n(y), n(z)), 'corner'],
    [a(x, n(y)), a(x, y, z), 'corner'], [a(x, y), a(n(x), y, z), 'corner'], [a(n(x), y), a(x, y, n(z)), 'corner'], [a(n(x), n(y)), a(n(x), y, n(z)), 'corner'],
    [x, a(z, n(y)), 'edge'], [x, a(n(z), n(y)), 'edge'], [x, a(y, n(z)), 'edge'], [x, a(y, z), 'edge'],
    [z, a(x, y), 'edge'], [z, a(x, n(y)), 'edge'], [z, a(n(x), n(y)), 'edge'], [z, a(y, n(x)), 'edge'],
    [y, a(z, n(x)), 'edge'], [y, a(x, z), 'edge'], [y, a(x, n(z)), 'edge'], [y, a(n(z), n(x)), 'edge'],
  ]
}

/** SoNaviCube::addButtonFace (SoNaviCube.cpp:1738-1933): each button's points, scaled by 0.005 about its offset, mirrored or
 *  turned for the arrows that share one shape, with the triangles FreeCAD lists (the rest are ear-clipped, as
 *  triangulatePolygon2D does), and a hit rectangle for the two buttons whose loops leave gaps. */
function buttonShape(id: NaviButton): ButtonShape {
  const scale = 0.005
  let offx = 0.5, offy = 0.5
  const tf = (px: number, py: number): [number, number] => {
    let x = px * scale + offx
    const y = py * scale + offy
    if (id === 'n' || id === 'w' || id === 'rl') x = 1 - x
    return id === 's' || id === 'n' ? [y, x] : [x, y]
  }
  const loops: [number, number][][] = [], tris: [number, number][][] = []
  const loop = (pts: number[]) => { const l: [number, number][] = []; for (let i = 0; i < pts.length; i += 2) l.push(tf(pts[i], pts[i + 1])); loops.push(l); return l }
  const triangles = (l: [number, number][], idx: number[]) => { for (let i = 0; i + 2 < idx.length; i += 3) tris.push([l[idx[i]], l[idx[i + 1]], l[idx[i + 2]]]) }
  const earClip = (l: [number, number][]) => {
    for (const t of THREE.ShapeUtils.triangulateShape(l.map(([x, y]) => new THREE.Vector2(x, y)), [])) tris.push([l[t[0]], l[t[1]], l[t[2]]])
  }
  let hit: ButtonShape['hit'] = null
  const hitFromVerts = () => {
    const all = loops.flat()
    hit = { left: Math.max(0, Math.min(...all.map((p) => p[0])) - BUTTON_HIT_SLOP), top: Math.max(0, Math.min(...all.map((p) => p[1])) - BUTTON_HIT_SLOP),
      right: Math.min(1, Math.max(...all.map((p) => p[0])) + BUTTON_HIT_SLOP), bottom: Math.min(1, Math.max(...all.map((p) => p[1])) + BUTTON_HIT_SLOP) }
  }
  if (id === 'rr' || id === 'rl') {
    earClip(loop([66.6, -66.6, 58.3, -74.0, 49.2, -80.3, 39.4, -85.5, 29.0, -89.5, 25.3, -78.1, 34.3, -74.3, 42.8, -69.9, 50.8, -64.4,
      58.1, -58.1, 53.8, -53.8, 74.7, -46.8, 70.7, -70.4]))
  } else if (id === 'n' || id === 's' || id === 'e' || id === 'w') {
    const l = loop([100.0, 0.0, 80.0, -18.0, 80.0, 18.0])
    tris.push([l[0], l[1], l[2]])
  } else if (id === 'menu') {
    offx = 0.90; offy = 0.95
    triangles(loop([-13.0, -20.0, 13.0, -20.0, 13.0, -16.0, -13.0, -16.0]), [0, 1, 2, 0, 2, 3])
    triangles(loop([-13.0, -12.0, 13.0, -12.0, 0.0, 0.0]), [0, 1, 2])
    hitFromVerts()
  } else if (id === 'home') {
    offx = 0.09; offy = 0.09
    const l = loop([0.0, -18.0, 18.0, -6.0, 12.0, -6.0, 12.0, 8.0, 4.0, 8.0, 4.0, 0.0, -4.0, 0.0, -4.0, 8.0, -12.0, 8.0, -12.0, -6.0, -18.0, -6.0])
    // Two points that are not on the outline (addPoint): the door's lintel, so the door stays a cutout.
    const pts = [...l, tf(4.0, -6.0), tf(-4.0, -6.0)]
    const [roofTop, roofRight, rightWallTop, rightWallBottom, doorRightBottom, doorRightTop, doorLeftTop, doorLeftBottom, leftWallBottom, leftWallTop, roofLeft, doorRightLintel, doorLeftLintel] = pts.map((_, i) => i)
    const idx = [roofLeft, roofRight, roofTop, doorRightLintel, rightWallBottom, rightWallTop, doorRightLintel, doorRightBottom, rightWallBottom,
      leftWallTop, doorLeftBottom, doorLeftLintel, leftWallTop, leftWallBottom, doorLeftBottom, doorLeftLintel, doorRightTop, doorRightLintel,
      doorLeftLintel, doorLeftTop, doorRightTop]
    for (let i = 0; i < idx.length; i += 3) tris.push([pts[idx[i]], pts[idx[i + 1]], pts[idx[i + 2]]])
  } else if (id === 'back') {
    offx = 0.80; offy = 0.0
    triangles(loop([24.0, 21.5, 17.0, 29.1, 16.7, 25.6, 12.0, 25.3, 8.2, 24.0, 4.0, 22.0, 1.2, 19.0, 0.0, 15.0, 0.0, 10.0, 1.5, 8.1, 4.4, 6.1,
      8.0, 5.5, 14.0, 4.0, 14.6, 9.2, 10.1, 10.2, 6.0, 12.0, 3.5, 14.0, 3.4, 14.5, 6.0, 15.8, 10.0, 17.0, 16.3, 18.0, 16.3, 13.6]),
    [0, 1, 2, 0, 2, 20, 0, 20, 21, 2, 20, 3, 20, 19, 3, 3, 19, 4, 19, 18, 4, 4, 18, 5, 18, 17, 5, 5, 17, 6,
      17, 16, 6, 6, 16, 7, 16, 15, 7, 7, 15, 8, 15, 14, 8, 8, 14, 9, 14, 13, 9, 9, 13, 10, 10, 13, 11, 11, 13, 12])
    triangles(loop([18.0, 6.0, 22.6, 0.0, 22.5, 3.0, 27.0, 3.3, 31.4, 4.3, 35.0, 5.6, 37.5, 7.1, 40.0, 9.7, 40.0, 12.8, 38.5, 16.5, 36.2, 20.0,
      33.0, 21.9, 28.3, 22.9, 28.7, 16.0, 32.8, 15.0, 36.4, 12.9, 33.8, 10.8, 30.0, 9.3, 26.1, 8.5, 22.5, 8.1, 22.4, 10.8]),
    [0, 1, 2, 0, 2, 19, 0, 19, 20, 2, 19, 3, 19, 18, 3, 3, 18, 4, 18, 17, 4, 4, 17, 5, 17, 16, 5, 5, 16, 6,
      16, 15, 6, 6, 15, 7, 15, 14, 7, 7, 14, 8, 14, 13, 8, 8, 13, 9, 9, 13, 10, 10, 13, 11, 11, 13, 12])
    hitFromVerts()
  }
  return { loops, tris, hit }
}
export const BUTTON_SHAPES = Object.fromEntries(NAVI_BUTTONS.map((b) => [b, buttonShape(b)])) as Record<NaviButton, ButtonShape>

/** pointInTriangle2D (SoNaviCube.cpp:205-237). */
function inTriangle(p: [number, number], a: [number, number], b: [number, number], c: [number, number]) {
  const v0x = c[0] - a[0], v0y = c[1] - a[1], v1x = b[0] - a[0], v1y = b[1] - a[1], v2x = p[0] - a[0], v2y = p[1] - a[1]
  const d00 = v0x * v0x + v0y * v0y, d01 = v0x * v1x + v0y * v1y, d02 = v0x * v2x + v0y * v2y, d11 = v1x * v1x + v1y * v1y, d12 = v1x * v2x + v1y * v2y
  const den = d00 * d11 - d01 * d01
  if (Math.abs(den) < 1e-18) return false
  const u = (d11 * d02 - d01 * d12) / den, v = (d00 * d12 - d01 * d02) / den
  return u >= 0 && v >= 0 && u + v <= 1
}

/** Whether p is within r of the segment a-b (SoRayPickAction's pick radius on a line set). */
function nearSegment(p: [number, number], a: [number, number], b: [number, number], r: number) {
  const dx = b[0] - a[0], dy = b[1] - a[1], l2 = dx * dx + dy * dy
  const t = l2 ? Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2)) : 0
  return Math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy) <= r
}

/** convertWeights (NaviCube.cpp:655-681): FontWeight's 0-99 scale to Qt's QFont::Weight, which is the CSS one. */
function cssWeight(w: number) {
  return w >= 87 ? 900 : w >= 81 ? 800 : w >= 75 ? 700 : w >= 63 ? 600 : w >= 57 ? 500 : w >= 50 ? 400 : w >= 25 ? 300 : w >= 12 ? 200 : 100
}

/** NaviCubeImplementation::createCubeFaceTextures (NaviCube.cpp:714-790): one 192 px texture per main face, white text on clear, sized
 *  so the widest label fills it, the others no more than FontZoom (0.3) of the way to their own fill, then 0.9 of that (a 5 %
 *  margin), centred; imageVerticalBalance then moves the text so its ink sits in the middle (for these capitals, the cap height
 *  centred), which here is read from the canvas's own ink metrics instead of scanning the pixels. */
function labelTextures(labels: Record<string, string>, font: string, weight: number, fontZoom = 0.3) {
  const texSize = 192
  const family = `${font ? `"${font}"` : 'Arial'}, sans-serif` // font.fromString(FontString or "Arial"), setStyleHint(SansSerif)
  const wt = weight > 0 ? cssWeight(weight) : 400
  const cv = document.createElement('canvas')
  cv.width = cv.height = texSize
  const ctx = cv.getContext('2d')!
  ctx.font = `${wt} ${texSize}px ${family}`
  const sizes: Record<string, number> = {}
  let minFont = texSize, maxFont = 0
  for (const [k, t] of Object.entries(labels)) {
    // QFontMetrics::boundingRect(text): the advance and the line height (ascent + descent)
    const m = ctx.measureText(t), h = (m.fontBoundingBoxAscent ?? texSize * 0.905) + (m.fontBoundingBoxDescent ?? texSize * 0.212)
    sizes[k] = texSize * (texSize / Math.max(m.width, h, 1))
    minFont = Math.min(minFont, sizes[k]); maxFont = Math.max(maxFont, sizes[k])
  }
  maxFont = fontZoom > 0 ? minFont + (maxFont - minFont) * fontZoom : minFont * Math.pow(2, fontZoom)
  const out: Record<string, THREE.CanvasTexture> = {}
  for (const [k, t] of Object.entries(labels)) {
    const c = document.createElement('canvas')
    c.width = c.height = texSize
    const g = c.getContext('2d')!
    if (sizes[k] > 0.5) {
      g.font = `${wt} ${Math.min(sizes[k], maxFont) * 0.9}px ${family}`
      g.fillStyle = '#fff'
      g.textAlign = 'center'
      g.textBaseline = 'alphabetic'
      const m = g.measureText(t)
      g.fillText(t, texSize / 2, texSize / 2 + (m.actualBoundingBoxAscent - m.actualBoundingBoxDescent) / 2)
    }
    const tex = new THREE.CanvasTexture(c)
    tex.colorSpace = THREE.NoColorSpace
    tex.wrapS = tex.wrapT = THREE.ClampToEdgeWrapping
    out[k] = tex
  }
  return out
}

/** SoNaviCube::buildAxisSection (SoNaviCube.cpp:765-812): the ShowCS tripod at the cube's (-1.1, -1.1, -1.1) corner, in AxisX/Y/ZColor,
 *  each a line and a point at both of its ends, BorderWidth * 2 wide (updateAxes, :1124-1126). WebGL draws no line wider than 1 px, so
 *  the line is three's fat line, in screen pixels, and the points round sprites of the same size. Depth tested like the cube. */
const SHOWCS_WIDTH_PX = 2.2 // BorderWidth (NaviCube.cpp:148, default 1.1) * 2.0F
let dotTex: THREE.Texture | null = null
function dotTexture() {
  if (dotTex) return dotTex
  const cv = document.createElement('canvas')
  cv.width = cv.height = 16
  const ctx = cv.getContext('2d')!
  ctx.fillStyle = '#fff'
  ctx.beginPath(); ctx.arc(8, 8, 7, 0, Math.PI * 2); ctx.fill()
  dotTex = new THREE.CanvasTexture(cv)
  return dotTex
}
function buildShowCS(size: number, colors: { x: string; y: string; z: string }) {
  const grp = new THREE.Group(), a = -1.1, b = -1.05, c = 0.5
  const segs: [THREE.Vector3, THREE.Vector3, 'x' | 'y' | 'z'][] = [[V(b, a, a), V(c, a, a), 'x'], [V(a, b, a), V(a, c, a), 'y'], [V(a, a, b), V(a, a, c), 'z']]
  for (const [p0, p1, axis] of segs) {
    const lineMat = new LineMaterial({ color: raw(colors[axis]), transparent: true, linewidth: SHOWCS_WIDTH_PX })
    lineMat.resolution.set(size, size)
    const line = new Line2(new LineGeometry().setFromPoints([p0, p1]), lineMat)
    line.userData.axis = axis
    line.renderOrder = 1
    grp.add(line)
    const caps = new THREE.Points(new THREE.BufferGeometry().setFromPoints([p0, p1]),
      new THREE.PointsMaterial({ color: raw(colors[axis]), map: dotTexture(), size: SHOWCS_WIDTH_PX, sizeAttenuation: false, transparent: true }))
    caps.userData.axis = axis
    caps.renderOrder = 1
    grp.add(caps)
  }
  return grp
}

export type NaviCubeStyle = {
  /** BaseColor, #rrggbb (FreeCAD Light: #f2f2f2, opaque). */
  base: string
  /** HiliteColor (2867003391 = #aae2ff). */
  hilite: string
  font: string
  fontWeight: number
  showCS: boolean
  axis: { x: string; y: string; z: string }
  labels: { front: string; top: string; right: string; rear: string; bottom: string; left: string }
}

/** SoNaviCube: the cube's scene, drawn into its own square of the view after the model, with a fixed camera of its own. */
export class NaviCubeGL {
  /** rootTransform's rotation: the camera's inverse (updateCameraAndTransform, SoNaviCube.cpp:1035-1039). */
  readonly quaternion = new THREE.Quaternion()
  private scene = new THREE.Scene()
  private root = new THREE.Group()
  private buttons = new THREE.Scene()
  private ortho = new THREE.OrthographicCamera(-OVERLAY_ORTHO_EXTENT, OVERLAY_ORTHO_EXTENT, OVERLAY_ORTHO_EXTENT, -OVERLAY_ORTHO_EXTENT, OVERLAY_NEAR, OVERLAY_FAR)
  // buildCamerasAndStyle (:583-586): heightAngle = 2 atan(tan(pi / 8) * 1.1), aspect 1.
  private persp = new THREE.PerspectiveCamera(THREE.MathUtils.radToDeg(2 * Math.atan(Math.tan(Math.PI / 8) * OVERLAY_FOV_SCALE)), 1, OVERLAY_NEAR, OVERLAY_FAR)
  // The buttons' plane in overlay coordinates: getPlanePoint puts each point at the same place on the screen for both cameras.
  private flat = new THREE.OrthographicCamera(0, 1, 1, 0, -1, 1)
  private pieces: Piece[] = []
  private faceMats: THREE.MeshBasicMaterial[] = []
  private edgeMat: THREE.LineBasicMaterial
  private labelMats: THREE.MeshBasicMaterial[] = []
  private buttonFill = new Map<NaviButton, THREE.MeshBasicMaterial>()
  private outlineMats: THREE.LineBasicMaterial[] = []
  private axes: THREE.Group | null = null
  private hilite: string | null = null
  private opacity = 1
  private ownTextures: THREE.Texture[] = []
  private base = new THREE.Color()
  private hiliteColor = new THREE.Color()
  /** EmphaseColor: black on a light BaseColor, white on a dark one (View3DSettings.cpp, the EmphaseColor branch of parameterChanged). */
  private emph = new THREE.Color()

  constructor(readonly style: NaviCubeStyle, readonly size: number, chamfer = 0.12) {
    this.base.copy(raw(style.base))
    this.hiliteColor.copy(raw(style.hilite))
    this.emph.set(this.base.r + this.base.g + this.base.b >= 1.5 ? 0x000000 : 0xffffff)
    this.scene.add(this.root)
    // Every material is a blended one, so three draws them in renderOrder (the scene graph's order), with InactiveOpacity
    // applied as alpha (beginOverlayPass: BLEND transparency, BASE_COLOR light model: no lighting).
    const basic = (o: THREE.MeshBasicMaterialParameters = {}) => new THREE.MeshBasicMaterial({ transparent: true, toneMapped: false, ...o })
    // buildCubeSection (:590-698): one face set with a polygon offset of 1, 1 (so the edges and labels draw on top), culled.
    const edgePts: THREE.Vector3[] = []
    for (const [x, z, kind] of pieces()) {
      const verts = cubeFace(x, z, kind, chamfer)
      const geo = new THREE.BufferGeometry().setFromPoints(verts)
      geo.setIndex(verts.slice(2).flatMap((_, i) => [0, i + 1, i + 2])) // SoShapeHints CONVEX: a fan
      const mat = basic({ color: this.base, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1, side: THREE.FrontSide })
      const mesh = new THREE.Mesh(geo, mat)
      mesh.renderOrder = 2
      this.faceMats.push(mat)
      const key = [z.x, z.y, z.z].join(',')
      mesh.userData.key = key
      this.root.add(mesh)
      this.pieces.push({ key, dir: z.clone(), verts, mesh })
      // rebuildGeometry (:1599-1617): every other side of each piece, (0, 1), (2, 3), ...: the lines between the pieces.
      for (let i = 0; i + 1 < verts.length; i += 2) edgePts.push(verts[i], verts[i + 1])
    }
    // updateEdges (:1087-1096): EmphaseColor, BorderWidth wide (1.1, which GL draws 1 px wide, as WebGL's lines are).
    this.edgeMat = new THREE.LineBasicMaterial({ color: this.emph, transparent: true, toneMapped: false })
    const edges = new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(edgePts), this.edgeMat)
    edges.renderOrder = 3
    this.root.add(edges)
    // setLabelQuad (:1620-1649) and the labels' group (:700-762): a quad 1 - 2 chamfer across, on each main face, depth tested
    // but not written, offset -1, -1; the white text is modulated by EmphaseColor (SoTexture2::MODULATE).
    const L = style.labels
    const tex = labelTextures({ front: L.front, top: L.top, right: L.right, rear: L.rear, bottom: L.bottom, left: L.left }, style.font, style.fontWeight)
    this.ownTextures.push(...Object.values(tex))
    const quads: [string, THREE.Vector3, THREE.Vector3][] = [['top', V(1, 0, 0), V(0, 0, 1)], ['front', V(1, 0, 0), V(0, -1, 0)], ['left', V(0, -1, 0), V(-1, 0, 0)],
      ['rear', V(-1, 0, 0), V(0, 1, 0)], ['right', V(0, 1, 0), V(1, 0, 0)], ['bottom', V(1, 0, 0), V(0, 0, -1)]]
    for (const [name, xv, zv] of quads) {
      const yv = xv.clone().cross(zv.clone().negate()), x2 = xv.clone().multiplyScalar(1 - chamfer * 2), y2 = yv.clone().multiplyScalar(1 - chamfer * 2)
      const q = [zv.clone().sub(x2).sub(y2), zv.clone().add(x2).sub(y2), zv.clone().add(x2).add(y2), zv.clone().sub(x2).add(y2)]
      const geo = new THREE.BufferGeometry().setFromPoints(q)
      geo.setAttribute('uv', new THREE.Float32BufferAttribute([0, 0, 1, 0, 1, 1, 0, 1], 2))
      geo.setIndex([0, 1, 2, 0, 2, 3])
      const mat = basic({ color: this.emph, map: tex[name], depthWrite: false, polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1, side: THREE.DoubleSide })
      this.labelMats.push(mat)
      const mesh = new THREE.Mesh(geo, mat)
      mesh.renderOrder = 4
      this.root.add(mesh)
    }
    if (style.showCS) { this.axes = buildShowCS(size, style.axis); this.root.add(this.axes) }
    // buildButtonsSection (:814-948): no depth test, the fill in BaseColor (HiliteColor when hovered), the outline in EmphaseColor.
    for (const id of NAVI_BUTTONS) {
      const shape = BUTTON_SHAPES[id]
      const fill = basic({ color: this.base, depthTest: false, depthWrite: false, side: THREE.DoubleSide })
      this.buttonFill.set(id, fill)
      const pts = shape.tris.flat().map(([x, y]) => V(x, 1 - y, 0))
      const mesh = new THREE.Mesh(new THREE.BufferGeometry().setFromPoints(pts), fill)
      mesh.renderOrder = 10
      this.buttons.add(mesh)
      for (const l of shape.loops) {
        const om = new THREE.LineBasicMaterial({ color: this.emph, transparent: true, depthTest: false, depthWrite: false, toneMapped: false })
        this.outlineMats.push(om)
        const line = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(l.map(([x, y]) => V(x, 1 - y, 0))), om)
        line.renderOrder = 11
        this.buttons.add(line)
      }
    }
  }

  dispose() {
    const free = (o: THREE.Object3D) => o.traverse((c) => { const m = c as THREE.Mesh; m.geometry?.dispose(); const mat = m.material as THREE.Material | undefined; mat?.dispose() })
    free(this.scene); free(this.buttons)
    if (this.quad) free(this.quad)
    this.target?.dispose()
    for (const t of this.ownTextures) t.dispose()
  }

  /** The 26 pieces: key ("x,y,z" of the piece's direction) and its centre in the cube's own coordinates. */
  pieceList() {
    return this.pieces.map((p) => ({ key: p.key, dir: p.dir.clone().normalize(), centre: p.verts.reduce((a, v) => a.add(v), V(0, 0, 0)).divideScalar(p.verts.length) }))
  }

  /** Where a point of the cube lands in the cube's square, 0..1 with y down, for the camera kind given. */
  project(local: THREE.Vector3, ortho: boolean) {
    this.syncRoot()
    const cam = ortho ? this.ortho : this.persp
    const p = local.clone().applyMatrix4(this.root.matrixWorld).project(cam)
    return { x: (p.x + 1) / 2, y: (1 - p.y) / 2 }
  }

  private syncRoot() {
    this.root.quaternion.copy(this.quaternion)
    this.root.position.set(0, 0, OVERLAY_CUBE_Z)
    this.root.updateMatrixWorld(true)
  }

  /** SoNaviCube::pickAt (:1372-1489) at (x, y), 0..1 across the square with y down: the buttons' hit rectangles first, then what a
   *  ray meets, the front-most face first: a button's fill, or the cube piece's key. */
  pick(x: number, y: number, ortho: boolean): string | null {
    for (const id of NAVI_BUTTONS) { const h = BUTTON_SHAPES[id].hit; if (h && x >= h.left && x <= h.right && y >= h.top && y <= h.bottom) return id }
    // The buttons lie at z -4, in front of the cube (OVERLAY_BUTTON_Z): a ray meets them first, their fill or, within the pick
    // radius of 1 px of pickFace's doubled viewport (half a pixel here), their outline.
    const r = 0.5 / this.size
    for (const id of NAVI_BUTTONS) {
      const s = BUTTON_SHAPES[id]
      if (s.tris.some((t) => inTriangle([x, y], t[0], t[1], t[2])) || s.loops.some((l) => l.some((a, i) => nearSegment([x, y], a, l[(i + 1) % l.length], r)))) return id
    }
    this.syncRoot()
    const ray = new THREE.Raycaster()
    ray.setFromCamera(new THREE.Vector2(x * 2 - 1, 1 - y * 2), ortho ? this.ortho : this.persp)
    const hit = ray.intersectObjects(this.pieces.map((p) => p.mesh), false)[0]
    return hit ? hit.object.userData.key as string : null
  }

  /** setHilite: the piece or button under the pointer, drawn in HiliteColor (updateCube :1042-1085, updateButtons :1141-1199). */
  setHilite(key: string | null) {
    if (key === this.hilite) return false
    this.hilite = key
    this.applyColors()
    return true
  }

  /** populateRenderParams' opacity: 1 while the pointer is over the cube's square, InactiveOpacity away from it. */
  setOpacity(o: number) {
    if (o === this.opacity) return false
    this.opacity = o
    this.applyColors()
    return true
  }

  private applyColors() {
    const o = this.opacity
    this.pieces.forEach((p, i) => { const m = this.faceMats[i]; m.color.copy(p.key === this.hilite ? this.hiliteColor : this.base); m.opacity = o })
    this.edgeMat.opacity = o
    for (const m of this.labelMats) m.opacity = o
    for (const m of this.outlineMats) m.opacity = o
    for (const [id, m] of this.buttonFill) { m.color.copy(id === this.hilite ? this.hiliteColor : this.base); m.opacity = o }
    for (const c of this.axes?.children ?? []) { const m = (c as THREE.Mesh).material as THREE.Material; m.opacity = o }
  }

  setAxisColors(c: { x: string; y: string; z: string }) {
    for (const o of this.axes?.children ?? []) { const axis = o.userData.axis as 'x' | 'y' | 'z'; ((o as THREE.Mesh).material as THREE.MeshBasicMaterial).color.copy(raw(c[axis])) }
  }

  /** SoNaviCube::renderCoin (:1325-1355): into the square at (x, y) (CSS px from the canvas's bottom left), clear only the depth
   *  there (clearOverlayDepth), draw the cube with the camera of the view's kind, then the buttons. */
  //  The cube is drawn first into a target of its own, the square's size in device pixels, without multisampling (FreeCAD's
  //  3D view has Anti-Aliasing None by default, so its 1 px outlines are hard edged; the page's canvas is multisampled), cleared
  //  to transparent, then laid over the view as it is (premultiplied: the target's colour already carries its alpha).
  private target: THREE.WebGLRenderTarget | null = null
  private quad: THREE.Scene | null = null
  render(renderer: THREE.WebGLRenderer, x: number, y: number, ortho: boolean) {
    this.syncRoot()
    const s = this.size, n = Math.max(1, Math.round(s * renderer.getPixelRatio()))
    if (!this.target || this.target.width !== n) {
      this.target?.dispose()
      this.target = new THREE.WebGLRenderTarget(n, n, { samples: 0, depthBuffer: true, minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter, generateMipmaps: false })
      this.quad?.traverse((c) => { ((c as THREE.Mesh).material as THREE.Material | undefined)?.dispose() })
      this.quad = new THREE.Scene()
      this.quad.add(new THREE.Mesh(new THREE.PlaneGeometry(1, 1).translate(0.5, 0.5, 0), new THREE.ShaderMaterial({
        uniforms: { map: { value: this.target.texture } },
        vertexShader: 'varying vec2 vUv; void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
        fragmentShader: 'uniform sampler2D map; varying vec2 vUv; void main() { gl_FragColor = texture2D(map, vUv); }',
        transparent: true, depthTest: false, depthWrite: false,
        blending: THREE.CustomBlending, blendSrc: THREE.OneFactor, blendDst: THREE.OneMinusSrcAlphaFactor,
        blendSrcAlpha: THREE.OneFactor, blendDstAlpha: THREE.OneMinusSrcAlphaFactor,
      })))
    }
    const autoClear = renderer.autoClear, prev = renderer.getRenderTarget(), clear = renderer.getClearColor(new THREE.Color()), clearA = renderer.getClearAlpha()
    const vp = renderer.getViewport(new THREE.Vector4())
    renderer.autoClear = false
    renderer.setRenderTarget(this.target)
    // The whole target; Line2 takes its resolution from this viewport (onBeforeRender), so the ShowCS lines are BorderWidth * 2 px.
    renderer.setViewport(0, 0, s, s)
    renderer.setClearColor(0x000000, 0)
    renderer.clear(true, true, true) // clearOverlayDepth, and no colour: the target starts clear
    renderer.render(this.scene, ortho ? this.ortho : this.persp)
    renderer.render(this.buttons, this.flat)
    renderer.setRenderTarget(prev)
    renderer.setClearColor(clear, clearA)
    renderer.setViewport(x, y, s, s)
    renderer.render(this.quad!, this.flat)
    renderer.autoClear = autoClear
    renderer.setViewport(vp)
  }
}
